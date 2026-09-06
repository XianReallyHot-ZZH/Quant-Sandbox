"""缝:config.settings —— 端口与产品身份(CONTEXT.md 改进 ②)。

独立事实源:默认端口 8766 + 环境变量覆盖来自 CONTEXT.md 决策表(参照物
硬编码 8765;错开一位使两者可同机并存对照);QuantSandbox/1.0 身份串
来自票 #2。
"""

import pytest

from config.settings import (
    APP_IDENTITY,
    DEFAULT_PORT,
    PORT_ENV_VAR,
    app_port,
)


def test_default_port_is_8766(monkeypatch) -> None:
    # 删掉环境里可能有的端口变量,断言兜到默认值。
    monkeypatch.delenv(PORT_ENV_VAR, raising=False)
    assert DEFAULT_PORT == 8766
    assert app_port() == 8766


def test_port_env_var_overrides_default(monkeypatch) -> None:
    # setenv 临时设一个环境变量(测试结束自动还原)。
    monkeypatch.setenv(PORT_ENV_VAR, "9000")
    assert app_port() == 9000


def test_port_env_var_must_be_an_integer(monkeypatch) -> None:
    # pytest.raises:断言「这段代码会抛出这个异常」;match 参数用正则
    # 再卡一道报错文案,防止异常对但理由错。
    monkeypatch.setenv(PORT_ENV_VAR, "abc")
    with pytest.raises(ValueError, match=PORT_ENV_VAR):
        app_port()


def test_port_env_var_must_be_within_range(monkeypatch) -> None:
    monkeypatch.setenv(PORT_ENV_VAR, "70000")
    with pytest.raises(ValueError, match=PORT_ENV_VAR):
        app_port()


def test_app_identity_string() -> None:
    assert APP_IDENTITY == "QuantSandbox/1.0"
