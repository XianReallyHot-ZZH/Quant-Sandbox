"""Seam: app.main — product entry point (skeleton: reports identity and port; HTTP lands later).

The port is observable end to end: .env file → load_env() → app_port() → banner.
"""

import config.env
from app import main


def test_main_reports_identity_and_default_port(capsys, monkeypatch) -> None:
    monkeypatch.delenv("QUANT_SANDBOX_PORT", raising=False)

    code = main()

    out = capsys.readouterr().out
    assert code == 0
    assert "QuantSandbox/1.0" in out
    assert "8766" in out


def test_main_takes_port_from_env_file(tmp_path, monkeypatch, capsys) -> None:
    # Isolate the .env lookup to tmp_path so the developer's real repo .env
    # cannot leak into the test.
    monkeypatch.setattr(config.env, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("QUANT_SANDBOX_PORT", raising=False)
    (tmp_path / ".env").write_text('QUANT_SANDBOX_PORT="9001"\n', encoding="utf-8")

    main()

    assert "9001" in capsys.readouterr().out
