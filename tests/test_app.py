"""缝:app.main —— 产品入口(骨架阶段:报身份与端口;HTTP 后续课程落地)。

端口是端到端可观察的:.env 文件 → load_env() → app_port() → 横幅输出。
"""

import config.env
from app import main


def test_main_reports_identity_and_default_port(capsys, monkeypatch) -> None:
    # capsys:pytest 夹具,捕获 print 输出;monkeypatch:临时改环境,测试
    # 结束自动还原。delenv 先删掉可能存在的端口变量,保证测的是默认 8766。
    monkeypatch.delenv("QUANT_SANDBOX_PORT", raising=False)

    code = main()

    out = capsys.readouterr().out
    assert code == 0
    assert "QuantSandbox/1.0" in out
    assert "8766" in out


def test_main_takes_port_from_env_file(tmp_path, monkeypatch, capsys) -> None:
    # 把 .env 的查找范围隔离到 tmp_path(pytest 提供的临时目录夹具),
    # 开发者仓库里真实的 .env 才不会泄漏进测试。
    # monkeypatch.setattr 换掉 config.env 模块里的 PROJECT_ROOT——
    # env.py 靠它定位 .env,换成临时目录即完成隔离。
    monkeypatch.setattr(config.env, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("QUANT_SANDBOX_PORT", raising=False)
    (tmp_path / ".env").write_text('QUANT_SANDBOX_PORT="9001"\n', encoding="utf-8")

    main()

    assert "9001" in capsys.readouterr().out
