"""本地运行离线/可选 DeepSeek 教练，不上传原始 Demo。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chapter07_cs2_coach.coach_context import player_reference
from chapter07_cs2_coach.coach_llm import CoachService
from chapter07_cs2_coach.coach_memory import (
    CoachSession,
    CoachSessionStore,
    history_payload,
)
from chapter07_cs2_coach.models import CoachChatResponse, MatchRecord
from chapter07_cs2_coach.profile_cli import collect_demo_paths
from chapter07_cs2_coach.quality_cli import parse_matches_for_audit


DEFAULT_SESSION_DIR = Path(".agent_data/coach_sessions")


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="基于本地多场 Demo 运行教练问答。")
    parser.add_argument("--demo", action="append", default=[])
    parser.add_argument("--demo-dir", type=Path)
    parser.add_argument("--player-steamid", required=True)
    parser.add_argument("--map-name", default="de_dust2")
    parser.add_argument("--question")
    parser.add_argument("--interactive", action="store_true", help="连续提问模式")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    parser.add_argument("--output", type=Path, help="把最后一次回答保存为 JSON")
    parser.add_argument("--session-id", default="default")
    parser.add_argument("--session-dir", type=Path, default=DEFAULT_SESSION_DIR)
    parser.add_argument("--no-memory", action="store_true", help="不读取或保存会话")
    parser.add_argument("--max-files", type=int, default=20, choices=range(1, 101))
    return parser


def format_coach_report(response: CoachChatResponse) -> str:
    mode = "DeepSeek 智能教练" if response.mode == "llm" else "离线规则教练"
    lines = [
        "=" * 60,
        "RoundMind CS2 Coach",
        "=" * 60,
        f"模式：{mode}",
        f"玩家：{response.player_ref}",
        f"模型：{response.model_name or '未调用'}",
        "",
        "【教练结论】",
        response.answer.strip(),
    ]
    if response.evidence_refs:
        lines.extend(["", "【关键证据】"])
        lines.extend(f"- {item}" for item in response.evidence_refs)
    if response.knowledge_ids:
        lines.extend(["", "【知识参考】"])
        lines.extend(f"- {item}" for item in response.knowledge_ids)
    if response.follow_up_questions:
        lines.extend(["", "【你可以继续问】"])
        lines.extend(f"- {item}" for item in response.follow_up_questions)
    if response.validation_warnings:
        lines.extend(["", "【校验提示】"])
        lines.extend(f"- {item}" for item in response.validation_warnings)
    lines.append("=" * 60)
    return "\n".join(lines)


def _write_output(response: CoachChatResponse, output: Path | None) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    print(f"回答 JSON 已保存：{output.resolve()}", file=sys.stderr)


def _ask(
    service: CoachService,
    matches: list[MatchRecord],
    *,
    steamid: str,
    map_name: str,
    question: str,
    session: CoachSession | None,
    store: CoachSessionStore,
) -> CoachChatResponse:
    response = service.answer(
        matches,
        player_steamid=steamid,
        map_name=map_name,
        question=question,
        conversation_history=history_payload(session) if session else [],
    )
    if session is not None:
        store.append_exchange(session, question=question, answer=response.answer)
    return response


def _interactive_loop(
    service: CoachService,
    matches: list[MatchRecord],
    *,
    steamid: str,
    map_name: str,
    first_question: str | None,
    session: CoachSession | None,
    store: CoachSessionStore,
    output: Path | None,
) -> None:
    remembered = len(session.messages) // 2 if session else 0
    print("\nRoundMind 交互教练已启动。输入 /exit 退出，/new 清空当前会话。")
    print(f"已载入 {remembered} 轮历史对话。\n")
    pending = first_question
    while True:
        try:
            question = pending or input("你 > ").strip()
            pending = None
        except (EOFError, KeyboardInterrupt):
            print("\n会话已结束。")
            return
        if not question:
            continue
        if question.casefold() in {"/exit", "exit", "quit"}:
            print("会话已保存，再见。")
            return
        if question.casefold() == "/new":
            if session is not None:
                store.clear(
                    session_id=session.session_id,
                    player_ref=session.player_ref,
                    map_name=session.map_name,
                )
                session.messages.clear()
            print("当前会话记忆已清空。")
            continue
        response = _ask(
            service,
            matches,
            steamid=steamid,
            map_name=map_name,
            question=question,
            session=session,
            store=store,
        )
        print(f"\n教练 >\n{format_coach_report(response)}\n")
        _write_output(response, output)


def main() -> None:
    args = _argument_parser().parse_args()
    if args.interactive and args.json:
        raise SystemExit("交互模式不能与 --json 同时使用。")
    if not args.interactive and not (args.question or "").strip():
        raise SystemExit("单次问答需要提供 --question，或使用 --interactive。")
    steamid = args.player_steamid.strip()
    map_name = args.map_name.strip()
    paths = collect_demo_paths(
        [Path(item) for item in args.demo], args.demo_dir, max_files=args.max_files
    )
    if not paths:
        raise SystemExit("没有找到可读取的 .dem 文件。")
    matches, failures = parse_matches_for_audit(paths, player_steamid=steamid)
    if not matches:
        raise SystemExit("没有成功解析的比赛。")
    service = CoachService.from_environment()
    store = CoachSessionStore(args.session_dir)
    session = None
    if not args.no_memory:
        try:
            session = store.load(
                session_id=args.session_id,
                player_ref=player_reference(steamid),
                map_name=map_name,
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error
    if failures:
        print(f"提示：跳过 {len(failures)} 个无法解析的 Demo。", file=sys.stderr)
    try:
        if args.interactive:
            _interactive_loop(
                service,
                matches,
                steamid=steamid,
                map_name=map_name,
                first_question=(args.question or "").strip() or None,
                session=session,
                store=store,
                output=args.output,
            )
            return
        question = args.question.strip()
        response = _ask(
            service,
            matches,
            steamid=steamid,
            map_name=map_name,
            question=question,
            session=session,
            store=store,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    _write_output(response, args.output)
    print(response.model_dump_json(indent=2) if args.json else format_coach_report(response))


if __name__ == "__main__":
    main()
