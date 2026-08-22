"""RoundMind 的本地启动入口。"""

from __future__ import annotations

import argparse

from chapter07_cs2_coach.runtime import CS2CoachRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="RoundMind CS2 智能复盘教练")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument(
        "--use-llm-planner",
        action="store_true",
        help="允许把问题和基础统计发送给 DeepSeek，由模型选择只读工具。",
    )
    args = parser.parse_args()

    import uvicorn

    from chapter07_cs2_coach.api import create_app

    runtime = CS2CoachRuntime.create(use_llm_planner=args.use_llm_planner)
    uvicorn.run(create_app(runtime), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
