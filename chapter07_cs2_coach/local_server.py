"""启动仅监听本机的 RoundMind Demo 解析网页。"""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from pathlib import Path

import uvicorn

from chapter07_cs2_coach.api import create_app


PUBLIC_WEB_URL = "https://roundmind-cs2-agent.yangmiaomiao37.chatgpt.site"


def configure_local_environment() -> None:
    """Keep the desktop parser on local, non-distributed storage backends."""

    os.environ["ROUNDMIND_LOCAL_BRIDGE"] = "true"
    os.environ["ROUNDMIND_JOB_BACKEND"] = "local"
    os.environ["ROUNDMIND_OBJECT_STORAGE"] = "local"
    os.environ["ROUNDMIND_KNOWLEDGE_BACKEND"] = "local"
    os.environ["ROUNDMIND_AUTH_REQUIRED"] = "false"
    os.environ.pop("DATABASE_URL", None)


def browser_target(local_url: str, use_local_ui: bool) -> str:
    return (
        local_url
        if use_local_ui
        else f"{PUBLIC_WEB_URL}/?processing=local#workspace"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="在本机解析 CS2 Demo，不将文件发送到 Render。"
    )
    parser.add_argument("--port", type=int, default=8765, help="本地端口，默认 8765")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动后不自动打开浏览器",
    )
    parser.add_argument(
        "--local-ui",
        action="store_true",
        help="打开后端自带的简易页面，而不是公开网站",
    )
    parser.add_argument(
        "--check-demo",
        type=Path,
        help="只检查 Demo 兼容性并读取玩家数量，不启动服务",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("端口必须在 1024 到 65535 之间。")
    url = f"http://127.0.0.1:{args.port}"
    configure_local_environment()
    if args.check_demo is not None:
        from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser

        options = CS2DemoMatchParser().list_player_options(args.check_demo.resolve())
        print(f"Demo 兼容性检查通过：读取到 {len(options)} 名玩家。")
        return
    browser_url = browser_target(url, args.local_ui)
    if not args.no_browser:
        timer = threading.Timer(1.0, webbrowser.open, args=(browser_url,))
        timer.daemon = True
        timer.start()
    print(f"RoundMind 本地模式：{url}")
    print("Demo 仅通过本机回环地址传输，不会上传到 Render。按 Ctrl+C 停止。")
    uvicorn.run(
        create_app(),
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
