"""sha256 manifest 契约:篡改检测(票 #3 AC2,ADR-0004)。

每个数据集目录的数据文件旁边放一份 manifest.json,记录 source、
generated_at 和每个被覆盖文件的一个 sha256。校验函数重算每个指纹,
每处不一致都点名报出——篡改必须以「有名字的问题」浮出水面,
绝不许沉默。
"""

import json
import re

from data.manifest import build_manifest, verify_manifest, write_manifest


def mint_tmp_dataset(tmp_path) -> None:
    """按生成器 CLI 将来的做法,写一个两文件数据集 + 它的 manifest。"""
    (tmp_path / "prices.csv").write_text("date,close\n2025-03-03,44.07\n", encoding="utf-8")
    (tmp_path / "company.json").write_text('{"symbol": "QUANT-DEMO/USDT"}\n', encoding="utf-8")
    manifest = build_manifest(
        source="synthetic:src/data/generator.py",
        generated_at="2026-09-02T00:00:00Z",
        files={
            "prices.csv": tmp_path / "prices.csv",
            "company.json": tmp_path / "company.json",
        },
    )
    write_manifest(tmp_path, manifest)


def test_manifest_shape_is_frozen(tmp_path) -> None:
    """ADR-0004 的固定格式:source/generated_at + 每文件一个 64 位十六进制指纹。"""
    (tmp_path / "prices.csv").write_text("date,close\n", encoding="utf-8")
    manifest = build_manifest(
        source="synthetic:test",
        generated_at="2026-09-02T00:00:00Z",
        files={"prices.csv": tmp_path / "prices.csv"},
    )
    assert set(manifest) == {"source", "generated_at", "files"}
    for digest in manifest["files"].values():
        # fullmatch:整串必须是恰好 64 个十六进制小写字符。
        assert re.fullmatch(r"[0-9a-f]{64}", digest), digest


def test_clean_dataset_verifies_with_no_problems(tmp_path) -> None:
    mint_tmp_dataset(tmp_path)
    assert verify_manifest(tmp_path) == []


def test_tampered_file_is_reported_by_name(tmp_path) -> None:
    # 往 prices.csv 追加一行(模拟入库后被改),校验必须点名它。
    mint_tmp_dataset(tmp_path)
    prices = tmp_path / "prices.csv"
    prices.write_text(
        prices.read_text(encoding="utf-8") + "2025-03-04,44.10\n", encoding="utf-8"
    )
    problems = verify_manifest(tmp_path)
    assert any("prices.csv" in problem for problem in problems), problems


def test_missing_listed_file_is_reported_by_name(tmp_path) -> None:
    # 被 manifest 登记的文件被删了,也要点名报出。
    mint_tmp_dataset(tmp_path)
    (tmp_path / "company.json").unlink()
    problems = verify_manifest(tmp_path)
    assert any("company.json" in problem for problem in problems), problems


def test_missing_manifest_is_itself_a_problem(tmp_path) -> None:
    assert verify_manifest(tmp_path) != []


def test_malformed_manifest_is_reported(tmp_path) -> None:
    # 坏 JSON 的 manifest:问题列表非空,且每条问题都指向 manifest.json。
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    problems = verify_manifest(tmp_path)
    assert problems and all("manifest.json" in problem for problem in problems), problems
