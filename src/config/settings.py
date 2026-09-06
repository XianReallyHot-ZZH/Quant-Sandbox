"""产品身份与运行时设置。

CONTEXT.md 有意改进 ②:默认端口 8766、环境变量可覆盖——参照物把 8765
硬编码在 app.py 里,我们错开一位,两边就能在同一台机器上同时跑起来
对照。用户可见文案用中文(ADR-0005)。
"""

from __future__ import annotations

import os

APP_NAME = "QuantSandbox"
APP_VERSION = "1.0"
# 运行时身份串,票 #2 指定为 "QuantSandbox/1.0"(HTTP 头/日志里不含
# 连字符的惯例);CONTEXT.md 里的产品/仓名拼写是 "Quant-Sandbox"——
# 两个都有出处,并排注明在此。
APP_IDENTITY = f"{APP_NAME}/{APP_VERSION}"

DEFAULT_PORT = 8766
PORT_ENV_VAR = "QUANT_SANDBOX_PORT"


def app_port() -> int:
    """HTTP 端口:默认 8766,环境变量 ``QUANT_SANDBOX_PORT`` 可覆盖。"""
    raw = os.environ.get(PORT_ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        # from None 把「int() 转换失败」的底层异常链藏掉,只留这条中文
        # 报错给用户——报错本身是用户可见文案(ADR-0005)。
        raise ValueError(f"环境变量 {PORT_ENV_VAR} 不是合法整数:{raw!r}") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"环境变量 {PORT_ENV_VAR} 超出端口范围 1-65535:{port}")
    return port
