"""Seam 6: verify — deliverable-integrity acceptance, placeholder edition (ADR-0006).

Contract: skipped checks must be explicit SKIPPED with a reason, never silent;
once a checked artifact exists but its assertion is unimplemented, FAIL
loudly instead of pretending to pass. Behavior is asserted on synthetic roots
— the repo-level run is verify's own job, not pytest's (ADR-0006 layering).
"""

import verify
from paths import PROJECT_ROOT
from verify import FAIL, PASS, SKIPPED, CheckResult


def _root_with_required_files(tmp_path):
    for rel in verify.REQUIRED_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    return tmp_path


def test_required_files_pass_on_complete_root(tmp_path) -> None:
    result = verify.check_required_files(_root_with_required_files(tmp_path))
    assert result.status == PASS
    assert "必需文件" in result.name


def test_required_files_fail_and_list_missing(tmp_path) -> None:
    result = verify.check_required_files(tmp_path)
    assert result.status == FAIL
    assert "app.py" in result.detail
    assert "src/paths.py" in result.detail


def test_safety_copy_skipped_until_report_lands(tmp_path) -> None:
    result = verify.check_safety_copy(tmp_path)
    assert result.status == SKIPPED
    assert "研究报告" in result.detail


def test_frozen_dataset_skipped_until_dataset_lands(tmp_path) -> None:
    result = verify.check_frozen_dataset(tmp_path)
    assert result.status == SKIPPED
    assert "冻结数据集" in result.detail


def test_landed_artifact_without_assertion_fails_loudly(tmp_path) -> None:
    # Anti-silent-skip: the day lesson 06 lands src/research/report.py, this
    # check must start failing until the string assertions are added —
    # "artifact present, check pretends to pass" is not allowed.
    (tmp_path / "src" / "research").mkdir(parents=True)
    (tmp_path / "src" / "research" / "report.py").write_text("", encoding="utf-8")
    result = verify.check_safety_copy(tmp_path)
    assert result.status == FAIL


def test_teaching_sample_fails_when_dataset_missing(tmp_path) -> None:
    result = verify.check_teaching_sample(tmp_path)
    assert result.status == FAIL
    assert "manifest.json" in result.detail


def test_teaching_sample_tamper_fails_with_named_file(tmp_path) -> None:
    dataset = tmp_path / "data" / "teaching_sample"
    dataset.mkdir(parents=True)
    for name in ("prices.csv", "company.json", "manifest.json"):
        source = PROJECT_ROOT / "data" / "teaching_sample" / name
        (dataset / name).write_bytes(source.read_bytes())
    prices = dataset / "prices.csv"
    prices.write_bytes(prices.read_bytes() + b"2020-01-01,1.00\n")
    result = verify.check_teaching_sample(tmp_path)
    assert result.status == FAIL
    assert "prices.csv" in result.detail


def test_format_distinguishes_ran_and_skipped() -> None:
    results = [
        CheckResult("已跑的检查", PASS, "通过原因"),
        CheckResult("跳过的检查", SKIPPED, "跳过原因"),
    ]
    text = verify.format_results(results)
    assert "[PASS] 已跑的检查 — 通过原因" in text
    assert "[SKIPPED] 跳过的检查 — 跳过原因" in text
    assert "已跑 1 项" in text
    assert "跳过 1 项" in text


def test_main_without_tests_exits_zero(capsys) -> None:
    code = verify.main(run_tests=False)
    out = capsys.readouterr().out
    assert code == 0
    assert "校验通过" in out
    assert "[SKIPPED]" in out
