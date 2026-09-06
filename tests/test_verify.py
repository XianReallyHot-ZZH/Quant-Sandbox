"""缝 6:verify —— 交付物完整性验收,占位版(ADR-0006)。

契约:被跳过的检查必须显式 SKIPPED 且带原因,绝不静默;一旦受检产物
已存在而断言未实现,必须大声 FAIL,不许装作通过。行为都断言在合成
目录上——仓库级的那次运行是 verify 自己的职责,不是 pytest 的
(ADR-0006 的分层)。
"""

import verify
from paths import PROJECT_ROOT
from verify import FAIL, PASS, SKIPPED, CheckResult


def _root_with_required_files(tmp_path):
    # 在临时目录里铺出全部必需文件(内容为空——检查的只是存在性)。
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
    # 空目录必然缺文件;明细必须把每个缺失文件名列出来。
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
    # 反静默跳过:课 06 落地 src/research/report.py 的那天,这个检查必须
    # 立刻开始 FAIL,直到字符串断言补上——「产物在、检查装通过」不允许。
    (tmp_path / "src" / "research").mkdir(parents=True)
    (tmp_path / "src" / "research" / "report.py").write_text("", encoding="utf-8")
    result = verify.check_safety_copy(tmp_path)
    assert result.status == FAIL


def test_teaching_sample_fails_when_dataset_missing(tmp_path) -> None:
    result = verify.check_teaching_sample(tmp_path)
    assert result.status == FAIL
    assert "manifest.json" in result.detail


def test_teaching_sample_tamper_fails_with_named_file(tmp_path) -> None:
    # 把真实三件套拷进临时目录,再往 prices.csv 追加一行——校验必须点名。
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
    # run_tests=False:不嵌套跑 pytest(那会让测试变慢且输出嵌套);
    # 即便如此,输出里也必须能看到 SKIPPED 的身影。
    code = verify.main(run_tests=False)
    out = capsys.readouterr().out
    assert code == 0
    assert "校验通过" in out
    assert "[SKIPPED]" in out
