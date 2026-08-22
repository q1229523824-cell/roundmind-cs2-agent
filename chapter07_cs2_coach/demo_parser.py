"""把 CS2 Source 2 Demo 转换成 RoundMind 的结构化比赛记录。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from chapter07_cs2_coach.models import MatchRecord


class DemoParseError(ValueError):
    """可以安全展示给网页用户的 Demo 解析错误。"""


class DemoParserProtocol(Protocol):
    def parse_header(self) -> Mapping[str, Any]: ...

    def parse_player_info(self) -> Any: ...

    def parse_event(
        self,
        event_name: str,
        *,
        player: list[str] | None = None,
        other: list[str] | None = None,
    ) -> Any: ...

    def parse_ticks(self, wanted_props: list[str], *, ticks: list[int]) -> Any: ...


ParserFactory = Callable[[str], DemoParserProtocol]


def _default_parser_factory(path: str) -> DemoParserProtocol:
    try:
        from demoparser2 import DemoParser
    except ImportError as error:  # pragma: no cover - 仅在缺少可选生产依赖时触发
        raise DemoParseError("服务器尚未安装 CS2 Demo 解析组件。") from error
    return DemoParser(path)


def _records(frame: Any) -> list[dict[str, Any]]:
    """兼容 demoparser2 不同版本返回的 pandas/polars DataFrame。"""

    if frame is None:
        return []
    if isinstance(frame, list):
        return [dict(item) for item in frame]
    if hasattr(frame, "to_dicts"):
        return [dict(item) for item in frame.to_dicts()]
    if hasattr(frame, "to_dict"):
        try:
            data = frame.to_dict(orient="records")
        except TypeError:
            data = frame.to_dict()
        if isinstance(data, list):
            return [dict(item) for item in data]
    raise DemoParseError("Demo 解析器返回了无法识别的数据格式。")


def _text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _integer(row: Mapping[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        try:
            value = row.get(key)
            if value is not None:
                return int(float(value))
        except (TypeError, ValueError):
            continue
    return default


def _round_index(row: Mapping[str, Any]) -> int:
    return _integer(row, "total_rounds_played", "round", default=-1)


def _same_player(value: Any, player_name: str) -> bool:
    return str(value or "").casefold() == player_name.casefold()


def _normalize_side(value: Any) -> str:
    normalized = str(value or "").upper()
    if normalized in {"3", "CT", "COUNTERTERRORIST", "COUNTER-TERRORIST"}:
        return "CT"
    if normalized in {"2", "T", "TERRORIST"}:
        return "T"
    return "T"


def _winner_side(value: Any) -> str | None:
    normalized = str(value or "").upper()
    if normalized in {"3", "CT", "COUNTERTERRORIST", "COUNTER-TERRORIST"}:
        return "CT"
    if normalized in {"2", "T", "TERRORIST"}:
        return "T"
    return None


def _find_player(players: Iterable[Mapping[str, Any]], requested: str) -> str:
    names = sorted({_text(item, "name", "player_name") for item in players} - {""})
    exact = [name for name in names if name.casefold() == requested.casefold()]
    if exact:
        return exact[0]
    partial = [name for name in names if requested.casefold() in name.casefold()]
    if len(partial) == 1:
        return partial[0]
    preview = "、".join(names[:10]) or "未读取到玩家"
    raise DemoParseError(f"找不到唯一玩家“{requested}”。Demo 中的玩家：{preview}")


class CS2DemoMatchParser:
    """只提取 Agent 需要的回合事实，避免加载全量逐 Tick 数据。"""

    def __init__(self, parser_factory: ParserFactory | None = None) -> None:
        self._parser_factory = parser_factory or _default_parser_factory

    def parse(self, path: Path, player_name: str) -> MatchRecord:
        try:
            parser = self._parser_factory(str(path))
            header = dict(parser.parse_header())
            stamp = str(header.get("demo_file_stamp", ""))
            if "PBDEMS2" not in stamp:
                raise DemoParseError("文件不是有效的 CS2 Source 2 Demo。")

            selected = _find_player(_records(parser.parse_player_info()), player_name)
            extra_player = ["team_name", "round_start_equip_value"]
            extra_other = ["total_rounds_played"]
            deaths = _records(
                parser.parse_event(
                    "player_death", player=extra_player, other=extra_other
                )
            )
            round_ends = _records(
                parser.parse_event("round_end", other=extra_other)
            )
            hurts = _records(
                parser.parse_event(
                    "player_hurt", player=["team_name"], other=extra_other
                )
            )
            blinds = _records(
                parser.parse_event(
                    "player_blind", player=["team_name"], other=extra_other
                )
            )
        except DemoParseError:
            raise
        except Exception as error:
            raise DemoParseError(
                "Demo 无法解析，可能来自暂不兼容的 CS2 版本或文件不完整。"
            ) from error

        if not round_ends:
            raise DemoParseError("Demo 中没有读取到正式回合结束事件。")

        round_ends.sort(key=lambda item: _integer(item, "tick"))
        death_by_round = self._group_by_round(deaths)
        hurt_by_round = self._group_by_round(hurts)
        blind_by_round = self._group_by_round(blinds)
        tick_rows = self._round_end_player_ticks(parser, round_ends, selected)

        rounds: list[dict[str, Any]] = []
        for fallback_index, round_end in enumerate(round_ends):
            round_index = _round_index(round_end)
            if round_index < 0:
                round_index = fallback_index
            round_deaths = sorted(
                death_by_round.get(round_index, []),
                key=lambda item: _integer(item, "tick"),
            )
            player_tick = tick_rows.get(_integer(round_end, "tick"), {})
            side = self._player_side(player_tick, round_deaths, selected)
            winner = _winner_side(round_end.get("winner"))
            opening = "none"
            if round_deaths:
                first = round_deaths[0]
                if _same_player(first.get("attacker_name"), selected):
                    opening = "won"
                elif _same_player(first.get("user_name"), selected):
                    opening = "lost"

            player_death = next(
                (item for item in round_deaths if _same_player(item.get("user_name"), selected)),
                None,
            )
            rounds.append(
                {
                    "number": len(rounds) + 1,
                    "side": side,
                    "won": winner == side if winner else False,
                    "kills": sum(
                        _same_player(item.get("attacker_name"), selected)
                        and not _same_player(item.get("user_name"), selected)
                        for item in round_deaths
                    ),
                    "assists": sum(
                        _same_player(item.get("assister_name"), selected)
                        for item in round_deaths
                    ),
                    "died": player_death is not None,
                    "damage": min(
                        1000,
                        sum(
                            max(0, _integer(item, "dmg_health", "damage"))
                            for item in hurt_by_round.get(round_index, [])
                            if _same_player(item.get("attacker_name"), selected)
                            and not _same_player(item.get("user_name"), selected)
                        ),
                    ),
                    "opening_duel": opening,
                    "was_traded": self._was_traded(player_death, round_deaths),
                    "utility_damage": min(
                        500,
                        sum(
                            max(0, _integer(item, "dmg_health", "damage"))
                            for item in hurt_by_round.get(round_index, [])
                            if _same_player(item.get("attacker_name"), selected)
                            and self._is_utility_damage(item)
                        ),
                    ),
                    "enemies_flashed": min(
                        5,
                        sum(
                            _same_player(item.get("attacker_name"), selected)
                            and not _same_player(item.get("user_name"), selected)
                            for item in blind_by_round.get(round_index, [])
                        ),
                    ),
                    "equipment_value": min(
                        20000,
                        max(
                            0,
                            _integer(
                                player_tick,
                                "round_start_equip_value",
                                "current_equip_value",
                            ),
                        ),
                    ),
                    "clutch_attempted": False,
                    "clutch_won": False,
                }
            )

        if not any(item["kills"] or item["died"] or item["damage"] for item in rounds):
            raise DemoParseError("读取到了回合，但没有找到该玩家的有效比赛事件。")

        team_score = sum(item["won"] for item in rounds)
        with path.open("rb") as demo_file:
            digest = hashlib.sha256(demo_file.read(1024 * 1024)).hexdigest()[:12]
        safe_player = re.sub(r"[^a-zA-Z0-9_-]+", "-", selected).strip("-")[:24] or "player"
        return MatchRecord.model_validate(
            {
                "match_id": f"dem-{digest}-{safe_player}",
                "player_name": selected,
                "map_name": str(header.get("map_name") or "unknown_map")[:80],
                "team_name": "Player Team",
                "opponent_name": "Opponent Team",
                "team_score": team_score,
                "opponent_score": len(rounds) - team_score,
                "rounds": rounds,
            }
        )

    @staticmethod
    def _group_by_round(rows: Iterable[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            index = _round_index(row)
            if index >= 0:
                grouped.setdefault(index, []).append(row)
        return grouped

    @staticmethod
    def _round_end_player_ticks(
        parser: DemoParserProtocol,
        round_ends: list[dict[str, Any]],
        player_name: str,
    ) -> dict[int, dict[str, Any]]:
        ticks = [_integer(item, "tick") for item in round_ends]
        try:
            rows = _records(
                parser.parse_ticks(
                    ["team_name", "round_start_equip_value", "current_equip_value"],
                    ticks=ticks,
                )
            )
        except Exception:
            return {}
        return {
            _integer(row, "tick"): row
            for row in rows
            if _same_player(_text(row, "name", "player_name"), player_name)
        }

    @staticmethod
    def _player_side(
        tick_row: Mapping[str, Any],
        deaths: list[dict[str, Any]],
        player_name: str,
    ) -> str:
        if tick_row:
            return _normalize_side(_text(tick_row, "team_name", "team_num"))
        for death in deaths:
            if _same_player(death.get("attacker_name"), player_name):
                return _normalize_side(
                    _text(death, "attacker_team_name", "attacker_team_num")
                )
            if _same_player(death.get("user_name"), player_name):
                return _normalize_side(_text(death, "user_team_name", "user_team_num"))
        return "T"

    @staticmethod
    def _was_traded(
        player_death: Mapping[str, Any] | None,
        deaths: list[dict[str, Any]],
    ) -> bool:
        if not player_death:
            return False
        death_tick = _integer(player_death, "tick")
        killer = _text(player_death, "attacker_name")
        player_team = _text(player_death, "user_team_name", "user_team_num")
        for event in deaths:
            delta = _integer(event, "tick") - death_tick
            if delta <= 0 or delta > 640:
                continue
            if _same_player(event.get("user_name"), killer) and (
                not player_team
                or _text(event, "attacker_team_name", "attacker_team_num") == player_team
            ):
                return True
        return False

    @staticmethod
    def _is_utility_damage(event: Mapping[str, Any]) -> bool:
        weapon = _text(event, "weapon").casefold()
        return any(
            name in weapon
            for name in ("grenade", "inferno", "molotov", "incendiary")
        )
