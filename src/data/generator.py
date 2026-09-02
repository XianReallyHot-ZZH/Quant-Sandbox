"""Deterministic teaching-sample generator (ADR-0004, ticket #3).

Learns the idea of the reference project's ``scripts/generate_prices_sample.py``
(closed-form trigonometric sum, research report §6.8) and writes our own
formula and window — no reference data file is copied. The minted sample is
committed under ``data/teaching_sample/`` so later lessons run offline, and
regeneration must be byte-identical (ticket #3 AC1): nothing here may read
the wall clock or an unseeded RNG. ``mint_sample``/``main`` write the CSV and
refresh the dataset manifest (``data.manifest``) over the directory; run via
``python3 -m data.generator``.
"""

from __future__ import annotations

import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import TextIO

from data.manifest import build_manifest, write_manifest
from paths import DATA_DIR

SEED = 20260902
START_DATE = date(2025, 3, 3)
ROW_COUNT = 381  # isomorphic in scale to the reference teaching sample (§6.8)
SYMBOL = "QUANT-DEMO/USDT"
DATASET_DIR = DATA_DIR / "teaching_sample"
PRICES_NAME = "prices.csv"
COMPANY_NAME = "company.json"
# Pinned per dataset version: AC1's byte-identical rerun forbids a wall clock,
# so the mint timestamp is part of the dataset's identity — bump it when the
# formula or window changes, never at write time.
GENERATED_AT = "2026-09-02T00:00:00Z"
MANIFEST_SOURCE = f"synthetic:src/data/generator.py (symbol={SYMBOL}, seed={SEED})"


def trading_days(start: date, count: int):
    """Yield ``count`` weekday dates beginning at ``start``."""
    current = start
    yielded = 0
    while yielded < count:
        if current.weekday() < 5:
            yield current
            yielded += 1
        current += timedelta(days=1)


def sample_rows(seed: int = SEED) -> list[tuple[str, str]]:
    """Close prices as ``(iso_date, two_decimal_text)`` pairs."""

    def close_price(index: int, shock: float) -> str:
        base = 42.0 + index * 0.028
        slow = 2.30 * math.sin(index * 0.052 + 0.6)
        mid = 1.05 * math.sin(index * 0.149 + 2.0)
        fast = 0.40 * math.sin(index * 0.417 + 4.1)
        dip = -1.35 * max(0.0, math.sin(index * 0.021 - 1.05)) ** 2
        price = max(35.0, base + slow + mid + fast + dip + shock)
        return f"{price:.2f}"

    rng = random.Random(seed)
    return [
        (day.isoformat(), close_price(index, (rng.random() - 0.5) * 0.44))
        for index, day in enumerate(trading_days(START_DATE, ROW_COUNT))
    ]


def prices_csv_text(seed: int = SEED) -> str:
    """The full sample as CSV bytes — the unit AC1's diff-zero runs on."""
    lines = ["date,close"]
    lines.extend(f"{date_text},{price}" for date_text, price in sample_rows(seed))
    return "\n".join(lines) + "\n"


def mint_sample(directory: Path = DATASET_DIR) -> dict:
    """Write prices.csv, then refresh the manifest over the dataset directory.

    company.json is handwritten narrative data that already lives in the
    dataset directory (research report §6.8) and is never written by this
    module; the manifest covers it too, so any hand edit must be re-minted
    to stay consistent. Returns the manifest it wrote.
    """
    company = directory / COMPANY_NAME
    if not company.is_file():
        raise FileNotFoundError(f"company.json 缺失,请先手写资产档案:{company}")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / PRICES_NAME).write_text(prices_csv_text(), encoding="utf-8")
    manifest = build_manifest(
        source=MANIFEST_SOURCE,
        generated_at=GENERATED_AT,
        files={
            PRICES_NAME: directory / PRICES_NAME,
            COMPANY_NAME: company,
        },
    )
    write_manifest(directory, manifest)
    return manifest


def main(directory: Path = DATASET_DIR, stream: TextIO = sys.stdout) -> int:
    """Mint the dataset; auditing belongs to ``verify.py``, not to the writer."""
    try:
        manifest = mint_sample(directory)
    except FileNotFoundError as error:
        print(f"[FAIL] {error}", file=stream)
        return 1
    print(
        f"已写入 {PRICES_NAME}({ROW_COUNT} 行)并刷新 manifest.json"
        f"({len(manifest['files'])} 个文件 sha256 已记录)。",
        file=stream,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
