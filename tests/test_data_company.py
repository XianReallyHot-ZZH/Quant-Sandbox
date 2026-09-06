"""虚构资产档案、来源卡与入库三件套(票 #3 AC3)。

资产档案与三张带日期的来源卡是手写的叙事数据(研报 §6.8:参照物的
company.json 也是手写);本测试冻结它们的结构,漂移即大声报错。入库
三件套(prices.csv + company.json + manifest.json)必须内部自洽:
重新生成样本必须复现入库字节,manifest 校验必须干净。
"""

import json
from datetime import date

from data.generator import (
    DATASET_DIR,
    GENERATED_AT,
    MANIFEST_SOURCE,
    ROW_COUNT,
    SYMBOL,
    mint_sample,
    prices_csv_text,
)
from data.manifest import verify_manifest

PROFILE_PATH = DATASET_DIR / "company.json"


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def test_asset_profile_structure_is_frozen() -> None:
    # set(profile) == {...}:字典的键集合必须一个不多一个不少——
    # 多一个少一个键都算结构漂移,测试即红。
    profile = load_profile()
    assert set(profile) == {
        "symbol",
        "name",
        "fictional",
        "summary",
        "market_snapshot",
        "sources",
    }
    assert profile["fictional"] is True
    assert profile["symbol"] == SYMBOL
    assert set(profile["market_snapshot"]) == {
        "period",
        "first_close",
        "last_close",
        "sample_days",
    }


def test_three_source_cards_complete_and_frozen() -> None:
    cards = load_profile()["sources"]
    assert [card["id"] for card in cards] == ["S1", "S2", "S3"]
    for card in cards:
        assert set(card) == {"id", "date", "title", "evidence"}
        date.fromisoformat(card["date"])  # 不是 ISO 日期会直接抛异常
        assert card["title"].strip()
        assert card["evidence"].strip()


def test_profile_numbers_agree_with_generated_sample() -> None:
    """手写的档案不许与铸造 CSV 的公式漂移:四个数字逐一对账。"""
    snapshot = load_profile()["market_snapshot"]
    # [1:] 跳过表头行;rsplit(",", 1) 从右边按第一个逗号切开,取出价格列。
    rows = prices_csv_text().splitlines()[1:]
    assert snapshot["sample_days"] == ROW_COUNT == len(rows)
    assert snapshot["first_close"] == float(rows[0].rsplit(",", 1)[1])
    assert snapshot["last_close"] == float(rows[-1].rsplit(",", 1)[1])


def test_minted_dataset_is_self_consistent(tmp_path) -> None:
    """铸造路径复现 CSV 字节,并留下一个校验干净的 manifest。"""
    (tmp_path / "company.json").write_bytes(PROFILE_PATH.read_bytes())
    mint_sample(tmp_path)
    assert (tmp_path / "prices.csv").read_text(encoding="utf-8") == prices_csv_text()
    assert verify_manifest(tmp_path) == []


def test_committed_trio_is_internally_consistent() -> None:
    """入库在 data/teaching_sample 下的,必须恰好是公式铸出来的那份。"""
    assert (DATASET_DIR / "prices.csv").read_text(encoding="utf-8") == prices_csv_text()
    assert verify_manifest(DATASET_DIR) == []
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == MANIFEST_SOURCE
    assert manifest["generated_at"] == GENERATED_AT
