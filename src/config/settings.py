"""Product identity and runtime settings.

CONTEXT.md improvement #2: default port 8766, overridable via env var, so the
reference project (8765, hardcoded) can run side by side on one machine.
User-visible copy is Chinese (ADR-0005).
"""

from __future__ import annotations

import os

APP_NAME = "QuantSandbox"
APP_VERSION = "1.0"
# Identity token as specified by ticket #2 ("QuantSandbox/1.0 identity");
# the product/repo name in CONTEXT.md is spelled "Quant-Sandbox".
APP_IDENTITY = f"{APP_NAME}/{APP_VERSION}"

DEFAULT_PORT = 8766
PORT_ENV_VAR = "QUANT_SANDBOX_PORT"


def app_port() -> int:
    """HTTP port: 8766 by default, overridable via ``QUANT_SANDBOX_PORT``."""
    raw = os.environ.get(PORT_ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        raise ValueError(f"环境变量 {PORT_ENV_VAR} 不是合法整数:{raw!r}") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"环境变量 {PORT_ENV_VAR} 超出端口范围 1-65535:{port}")
    return port
