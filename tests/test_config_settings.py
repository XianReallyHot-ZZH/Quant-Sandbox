"""Seam: config.settings — port and product identity (CONTEXT.md improvement #2).

Independent source of truth: default port 8766 + env-var override come from
the CONTEXT.md decision table (the reference hardcodes 8765; offset by one so
both can run side by side); the QuantSandbox/1.0 identity comes from ticket #2.
"""

import pytest

from config.settings import (
    APP_IDENTITY,
    DEFAULT_PORT,
    PORT_ENV_VAR,
    app_port,
)


def test_default_port_is_8766(monkeypatch) -> None:
    monkeypatch.delenv(PORT_ENV_VAR, raising=False)
    assert DEFAULT_PORT == 8766
    assert app_port() == 8766


def test_port_env_var_overrides_default(monkeypatch) -> None:
    monkeypatch.setenv(PORT_ENV_VAR, "9000")
    assert app_port() == 9000


def test_port_env_var_must_be_an_integer(monkeypatch) -> None:
    monkeypatch.setenv(PORT_ENV_VAR, "abc")
    with pytest.raises(ValueError, match=PORT_ENV_VAR):
        app_port()


def test_port_env_var_must_be_within_range(monkeypatch) -> None:
    monkeypatch.setenv(PORT_ENV_VAR, "70000")
    with pytest.raises(ValueError, match=PORT_ENV_VAR):
        app_port()


def test_app_identity_string() -> None:
    assert APP_IDENTITY == "QuantSandbox/1.0"
