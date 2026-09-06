"""Quant-Sandbox 产品入口(仓库根即产品根)。"""

from __future__ import annotations

import sys
from pathlib import Path

# 把 src/ 插到模块搜索路径最前——直接 `python3 app.py` 运行时,src 下的
# config、data 等包才能被 import(测试里这件事由 pytest.ini 的
# pythonpath 配置完成,这里是为「脱离 pytest 直接运行」兜底)。
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from config.env import load_env  # noqa: E402
from config.settings import APP_IDENTITY, DEFAULT_PORT, PORT_ENV_VAR, app_port  # noqa: E402
# ↑ noqa: E402 告诉 linter:「import 不在文件顶部是故意的」——上面两行
#   import 必须排在 sys.path 引导之后,否则找不到包。


def main() -> int:
    """入口主函数:装 .env → 问端口 → 打印横幅;返回进程退出码。"""
    # 先 load_env 再问端口:端口可能来自 .env(加载顺序即优先级,
    # 见 src/config/env.py)。
    load_env()
    port = app_port()
    # 以下 print 是用户可见文案:中文(ADR-0005),措辞变更 = 契约变更。
    print(f"{APP_IDENTITY} · 量化研究实验沙盒")
    print(f"端口 {port}(默认 {DEFAULT_PORT},环境变量 {PORT_ENV_VAR} 可覆盖)")
    print("HTTP 服务将在后续课程落地;当前为骨架。")
    return 0


if __name__ == "__main__":
    # 作为脚本直接运行时才执行;被 import 时(例如测试调 main())不会执行。
    # SystemExit(main()) 把 main 的返回码变成进程退出码(0 = 成功)。
    raise SystemExit(main())
