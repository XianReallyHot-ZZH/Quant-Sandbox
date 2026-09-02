"""Teaching-sample generator contract: determinism and shape (ticket #3 AC1).

AC1: rerunning the generator must produce byte-identical output, so the
sample may depend only on the closed-form formula and the pinned seed —
never on the wall clock or an unseeded RNG. Scale is isomorphic to the
reference teaching sample (381 weekday closes, research report §6.8).
"""

import re
from datetime import date
from io import StringIO

from data.generator import (
    DATASET_DIR,
    ROW_COUNT,
    SEED,
    START_DATE,
    main,
    mint_sample,
    prices_csv_text,
    sample_rows,
)

ROW_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2},\d+\.\d{2}$")


def test_regeneration_is_byte_identical() -> None:
    """Two consecutive generations agree byte for byte (AC1)."""
    assert prices_csv_text() == prices_csv_text()


def _with_profile(directory) -> None:
    """Copy the handwritten profile in — minting requires it but never writes it."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "company.json").write_bytes((DATASET_DIR / "company.json").read_bytes())


def test_mint_reruns_are_byte_identical(tmp_path) -> None:
    """AC1 on the full mint path: a rerun — elsewhere and in place — rewrites identical bytes.

    A wall clock anywhere on the write path would show up here as a diff.
    """
    first, second = tmp_path / "first", tmp_path / "second"
    _with_profile(first)
    _with_profile(second)
    mint_sample(first)
    mint_sample(second)
    mint_sample(first)  # in-place rerun: the acceptance's literal "重跑两次"
    for name in ("prices.csv", "manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_main_mints_and_reports_success(tmp_path) -> None:
    _with_profile(tmp_path)
    stream = StringIO()
    assert main(tmp_path, stream) == 0
    assert f"{ROW_COUNT} 行" in stream.getvalue()


def test_main_fails_without_the_handwritten_profile(tmp_path) -> None:
    """Minting requires the profile but never writes it; missing input exits 1."""
    stream = StringIO()
    assert main(tmp_path, stream) == 1
    assert "company.json" in stream.getvalue()


def test_sample_shape_matches_reference_scale() -> None:
    """Header + 381 weekday closes, two-decimal prices, strictly increasing dates."""
    rows = sample_rows()
    assert len(rows) == ROW_COUNT
    dates = [date_text for date_text, _ in rows]
    assert dates[0] == START_DATE.isoformat()
    assert all(prior < later for prior, later in zip(dates, dates[1:]))
    for date_text, price_text in rows:
        weekday = date.fromisoformat(date_text).weekday()
        assert weekday < 5, f"{date_text} is not a weekday"
        assert ROW_PATTERN.match(f"{date_text},{price_text}"), price_text


def test_seed_participates_in_output() -> None:
    """A different seed must change the output — a dead seed would let AC1 pass vacuously."""
    assert sample_rows(seed=1) != sample_rows(seed=SEED)
