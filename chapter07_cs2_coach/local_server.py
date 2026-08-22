"""启动仅监听本机的 RoundMind Demo 解析网页。"""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("端口必须在 1024 到 65535 之间。")
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        timer = threading.Timer(1.0, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()
    print(f"RoundMind 本地模式：{url}")
    print("Demo 仅通过本机回环地址传输，不会上传到 Render。按 Ctrl+C 停止。")
    uvicorn.run(
        "chapter07_cs2_coach.api:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
