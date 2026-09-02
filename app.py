"""Quant-Sandbox product entry point (repo root is the product root)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from config.env import load_env  # noqa: E402
from config.settings import APP_IDENTITY, DEFAULT_PORT, PORT_ENV_VAR, app_port  # noqa: E402


def main() -> int:
    load_env()
    port = app_port()
    print(f"{APP_IDENTITY} · 量化研究实验沙盒")
    print(f"端口 {port}(默认 {DEFAULT_PORT},环境变量 {PORT_ENV_VAR} 可覆盖)")
    print("HTTP 服务将在后续课程落地;当前为骨架。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
