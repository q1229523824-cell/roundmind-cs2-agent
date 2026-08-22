"""把 CS2 Source 2 Demo 转换成 RoundMind 的结构化比赛记录。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from chapter07_cs2_coach.models import DemoPlayerOption, MatchRecord


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


def _number(row: Mapping[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        try:
            value = row.get(key)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _round_index(row: Mapping[str, Any]) -> int:
    return _integer(row, "total_rounds_played", "round", default=-1)


def _same_player(value: Any, player_name: str) -> bool:
    return str(value or "").casefold() == player_name.casefold()


def _same_identity(
    row: Mapping[str, Any],
    role: str,
    player_name: str,
    player_steamid: str | None,
) -> bool:
    steamid = _text(row, f"{role}_steamid")
    if player_steamid and steamid:
        return steamid == player_steamid
    return _same_player(row.get(f"{role}_name"), player_name)


def _opposing_teams(row: Mapping[str, Any]) -> bool:
    attacker_team = _text(row, "attacker_team_name", "attacker_team_num")
    user_team = _text(row, "user_team_name", "user_team_num")
    return not attacker_team or not user_team or attacker_team != user_team


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


def _find_player(
    players: Iterable[Mapping[str, Any]],
    requested: str,
    requested_steamid: str | None = None,
) -> DemoPlayerOption:
    options = [
        DemoPlayerOption(
            name=_text(item, "name", "player_name"),
            steamid=_text(item, "steamid", "steam_id", "xuid"),
        )
        for item in players
        if _text(item, "name", "player_name")
        and _text(item, "steamid", "steam_id", "xuid")
    ]
    if requested_steamid:
        exact_id = [item for item in options if item.steamid == requested_steamid]
        if len(exact_id) == 1:
            return exact_id[0]
    exact = [item for item in options if item.name.casefold() == requested.casefold()]
    if len(exact) == 1:
        return exact[0]
    partial = [item for item in options if requested.casefold() in item.name.casefold()]
    if len(partial) == 1:
        return partial[0]
    preview = "、".join(item.name for item in options[:10]) or "未读取到玩家"
    raise DemoParseError(f"找不到唯一玩家“{requested}”。Demo 中的玩家：{preview}")


class CS2DemoMatchParser:
    """只提取 Agent 需要的回合事实，避免加载全量逐 Tick 数据。"""

    def __init__(self, parser_factory: ParserFactory | None = None) -> None:
        self._parser_factory = parser_factory or _default_parser_factory

    def list_players(self, path: Path) -> list[str]:
        """读取 Demo 名单，供前端让用户选择自己的游戏昵称。"""
        return [item.name for item in self.list_player_options(path)]

    def list_player_options(self, path: Path) -> list[DemoPlayerOption]:
        """读取昵称与 SteamID，使用稳定 ID 区分同名玩家。"""
        try:
            parser = self._parser_factory(str(path))
            header = dict(parser.parse_header())
            if "PBDEMS2" not in str(header.get("demo_file_stamp", "")):
                raise DemoParseError("文件不是有效的 CS2 Source 2 Demo。")
            options = sorted(
                {
                    (
                        _text(item, "name", "player_name"),
                        _text(item, "steamid", "steam_id", "xuid"),
                    )
                    for item in _records(parser.parse_player_info())
                    if _text(item, "name", "player_name")
                    and _text(item, "steamid", "steam_id", "xuid")
                },
                key=lambda item: (item[0].casefold(), item[1]),
            )
        except DemoParseError:
            raise
        except Exception as error:
            raise DemoParseError(
                "Demo 无法读取玩家名单，可能来自暂不兼容的 CS2 版本或文件不完整。"
            ) from error
        if not options:
            raise DemoParseError("Demo 中没有读取到玩家名单。")
        return [DemoPlayerOption(name=name, steamid=steamid) for name, steamid in options[:20]]

    def parse(
        self,
        path: Path,
        player_name: str,
        player_steamid: str | None = None,
    ) -> MatchRecord:
        try:
            parser = self._parser_factory(str(path))
            header = dict(parser.parse_header())
            stamp = str(header.get("demo_file_stamp", ""))
            if "PBDEMS2" not in stamp:
                raise DemoParseError("文件不是有效的 CS2 Source 2 Demo。")

            selected = _find_player(
                _records(parser.parse_player_info()), player_name, player_steamid
            )
            extra_player = ["team_name", "steamid"]
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
                    "player_blind",
                    player=extra_player,
                    other=["total_rounds_played", "blind_duration"],
                )
            )
            freeze_ends = _records(
                parser.parse_event("round_freeze_end", other=extra_other)
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
        tick_rows = self._round_start_player_ticks(parser, freeze_ends, selected)

        rounds: list[dict[str, Any]] = []
        for fallback_index, round_end in enumerate(round_ends):
            round_index = _integer(round_end, "round", default=0) - 1
            if round_index < 0:
                round_index = _round_index(round_end) - 1
            if round_index < 0:
                round_index = fallback_index
            round_deaths = sorted(
                death_by_round.get(round_index, []),
                key=lambda item: _integer(item, "tick"),
            )
            player_tick = tick_rows.get(round_index, {})
            side = self._player_side(player_tick, round_deaths, selected)
            winner = _winner_side(round_end.get("winner"))
            opening = "none"
            first = next((item for item in round_deaths if _opposing_teams(item)), None)
            if first:
                if _same_identity(first, "attacker", selected.name, selected.steamid):
                    opening = "won"
                elif _same_identity(first, "user", selected.name, selected.steamid):
                    opening = "lost"

            player_death = next(
                (
                    item
                    for item in round_deaths
                    if _same_identity(item, "user", selected.name, selected.steamid)
                ),
                None,
            )
            rounds.append(
                {
                    "number": len(rounds) + 1,
                    "side": side,
                    "won": winner == side if winner else False,
                    "kills": sum(
                        _same_identity(item, "attacker", selected.name, selected.steamid)
                        and not _same_identity(item, "user", selected.name, selected.steamid)
                        and _opposing_teams(item)
                        for item in round_deaths
                    ),
                    "assists": sum(
                        _same_identity(item, "assister", selected.name, selected.steamid)
                        for item in round_deaths
                    ),
                    "died": player_death is not None,
                    "damage": min(
                        1000,
                        sum(
                            max(0, _integer(item, "dmg_health", "damage"))
                            for item in hurt_by_round.get(round_index, [])
                            if _same_identity(item, "attacker", selected.name, selected.steamid)
                            and not _same_identity(item, "user", selected.name, selected.steamid)
                            and _opposing_teams(item)
                        ),
                    ),
                    "opening_duel": opening,
                    "was_traded": self._was_traded(player_death, round_deaths),
                    "utility_damage": min(
                        500,
                        sum(
                            max(0, _integer(item, "dmg_health", "damage"))
                            for item in hurt_by_round.get(round_index, [])
                            if _same_identity(item, "attacker", selected.name, selected.steamid)
                            and self._is_utility_damage(item)
                            and _opposing_teams(item)
                        ),
                    ),
                    "enemies_flashed": min(
                        5,
                        self._effective_enemy_flashes(
                            blind_by_round.get(round_index, []), selected
                        ),
                    ),
                    "equipment_value": min(
                        20000,
                        max(
                            0,
                            _integer(
                                player_tick,
                                "current_equip_value",
                                "round_start_equip_value",
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
        safe_player = re.sub(r"[^a-zA-Z0-9_-]+", "-", selected.steamid).strip("-")[:24]
        return MatchRecord.model_validate(
            {
                "match_id": f"dem-{digest}-{safe_player}",
                "player_name": selected.name,
                "player_steamid": selected.steamid,
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
    def _round_start_player_ticks(
        parser: DemoParserProtocol,
        freeze_ends: list[dict[str, Any]],
        player: DemoPlayerOption,
    ) -> dict[int, dict[str, Any]]:
        ticks = [_integer(item, "tick") for item in freeze_ends]
        try:
            rows = _records(
                parser.parse_ticks(
                    ["team_name", "current_equip_value", "round_start_equip_value"],
                    ticks=ticks,
                )
            )
        except Exception:
            return {}
        tick_to_round = {
            _integer(event, "tick"): _round_index(event) for event in freeze_ends
        }
        return {
            tick_to_round[_integer(row, "tick")]: row
            for row in rows
            if _integer(row, "tick") in tick_to_round
            and (
                _text(row, "steamid") == player.steamid
                or _same_player(_text(row, "name", "player_name"), player.name)
            )
        }

    @staticmethod
    def _player_side(
        tick_row: Mapping[str, Any],
        deaths: list[dict[str, Any]],
        player: DemoPlayerOption,
    ) -> str:
        if tick_row:
            return _normalize_side(_text(tick_row, "team_name", "team_num"))
        for death in deaths:
            if _same_identity(death, "attacker", player.name, player.steamid):
                return _normalize_side(
                    _text(death, "attacker_team_name", "attacker_team_num")
                )
            if _same_identity(death, "user", player.name, player.steamid):
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

    @staticmethod
    def _effective_enemy_flashes(
        events: Iterable[Mapping[str, Any]],
        player: DemoPlayerOption,
    ) -> int:
        """统计有效敌方闪白：至少 1 秒，并按受害者与 tick 去重。"""

        unique: set[tuple[int, str]] = set()
        for event in events:
            if not _same_identity(event, "attacker", player.name, player.steamid):
                continue
            attacker_team = _text(event, "attacker_team_name", "attacker_team_num")
            user_team = _text(event, "user_team_name", "user_team_num")
            if attacker_team and user_team and attacker_team == user_team:
                continue
            if "blind_duration" in event and _number(event, "blind_duration") < 1.0:
                continue
            victim = _text(event, "user_steamid", "user_name")
            unique.add((_integer(event, "tick"), victim))
        return len(unique)
