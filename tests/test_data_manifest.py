"""sha256 manifest contract: tamper detection (ticket #3 AC2, ADR-0004).

Every dataset directory carries a manifest.json next to its data files,
recording source, generated_at and one sha256 per covered file. The verify
function recomputes every digest and reports each divergence by name —
tampering must surface as a named problem, never as silence.
"""

import json
import re

from data.manifest import build_manifest, verify_manifest, write_manifest


def mint_tmp_dataset(tmp_path) -> None:
    """Write a two-file dataset plus its manifest, the way the generator CLI will."""
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
    """ADR-0004's fixed format: source/generated_at plus one 64-hex digest per file."""
    (tmp_path / "prices.csv").write_text("date,close\n", encoding="utf-8")
    manifest = build_manifest(
        source="synthetic:test",
        generated_at="2026-09-02T00:00:00Z",
        files={"prices.csv": tmp_path / "prices.csv"},
    )
    assert set(manifest) == {"source", "generated_at", "files"}
    for digest in manifest["files"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", digest), digest


def test_clean_dataset_verifies_with_no_problems(tmp_path) -> None:
    mint_tmp_dataset(tmp_path)
    assert verify_manifest(tmp_path) == []


def test_tampered_file_is_reported_by_name(tmp_path) -> None:
    mint_tmp_dataset(tmp_path)
    prices = tmp_path / "prices.csv"
    prices.write_text(
        prices.read_text(encoding="utf-8") + "2025-03-04,44.10\n", encoding="utf-8"
    )
    problems = verify_manifest(tmp_path)
    assert any("prices.csv" in problem for problem in problems), problems


def test_missing_listed_file_is_reported_by_name(tmp_path) -> None:
    mint_tmp_dataset(tmp_path)
    (tmp_path / "company.json").unlink()
    problems = verify_manifest(tmp_path)
    assert any("company.json" in problem for problem in problems), problems


def test_missing_manifest_is_itself_a_problem(tmp_path) -> None:
    assert verify_manifest(tmp_path) != []


def test_malformed_manifest_is_reported(tmp_path) -> None:
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    problems = verify_manifest(tmp_path)
    assert problems and all("manifest.json" in problem for problem in problems), problems
