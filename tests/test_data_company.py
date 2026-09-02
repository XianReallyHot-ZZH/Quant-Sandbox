"""Fictional asset profile, source cards, and the committed dataset trio (ticket #3 AC3).

The asset profile and its three dated source cards are handwritten narrative
data (research report §6.8: the reference's company.json is handwritten too);
this test freezes their structure so drift breaks loudly. The committed trio
(prices.csv + company.json + manifest.json) must stay internally consistent:
regenerating the sample reproduces the committed bytes, and the manifest
verifies clean.
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
        date.fromisoformat(card["date"])  # raises unless ISO
        assert card["title"].strip()
        assert card["evidence"].strip()


def test_profile_numbers_agree_with_generated_sample() -> None:
    """A handwritten profile must not drift from the formula that mints the CSV."""
    snapshot = load_profile()["market_snapshot"]
    rows = prices_csv_text().splitlines()[1:]
    assert snapshot["sample_days"] == ROW_COUNT == len(rows)
    assert snapshot["first_close"] == float(rows[0].rsplit(",", 1)[1])
    assert snapshot["last_close"] == float(rows[-1].rsplit(",", 1)[1])


def test_minted_dataset_is_self_consistent(tmp_path) -> None:
    """The mint path reproduces the CSV bytes and leaves a clean manifest behind."""
    (tmp_path / "company.json").write_bytes(PROFILE_PATH.read_bytes())
    mint_sample(tmp_path)
    assert (tmp_path / "prices.csv").read_text(encoding="utf-8") == prices_csv_text()
    assert verify_manifest(tmp_path) == []


def test_committed_trio_is_internally_consistent() -> None:
    """What is committed under data/teaching_sample is exactly what the formula mints."""
    assert (DATASET_DIR / "prices.csv").read_text(encoding="utf-8") == prices_csv_text()
    assert verify_manifest(DATASET_DIR) == []
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == MANIFEST_SOURCE
    assert manifest["generated_at"] == GENERATED_AT
