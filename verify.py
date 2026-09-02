"""Quant-Sandbox deliverable-integrity acceptance (placeholder, lesson 01).

Of ADR-0006's four check categories, this lesson lands 1) required-files
inventory and 4) full pytest; 2) research-report safety copy and 3) frozen
dataset sha256 stay explicitly SKIPPED until their lessons land. Every
skipped check must print SKIPPED plus a reason — silent passes are banned.
Once a checked artifact exists but its assertion is not implemented, FAIL
immediately (anti-silent-skip; research report §8.5 #6).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PASS = "PASS"
SKIPPED = "SKIPPED"
FAIL = "FAIL"

REQUIRED_FILES = (
    "app.py",
    "pytest.ini",
    "verify.py",
    "src/paths.py",
    "src/config/__init__.py",
    "src/config/env.py",
    "src/config/settings.py",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""


def _deferred_check(name: str, artifact: Path, *, pending: str, landed: str) -> CheckResult:
    """Share the SKIPPED-until-artifact / FAIL-once-landed shape (ADR-0006 #2)."""
    if not artifact.is_file():
        return CheckResult(name, SKIPPED, pending)
    return CheckResult(name, FAIL, landed)


def check_required_files(root: Path = ROOT) -> CheckResult:
    """1) Required-files inventory."""
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    if missing:
        return CheckResult("必需文件清单", FAIL, f"缺失:{', '.join(missing)}")
    return CheckResult("必需文件清单", PASS, f"{len(REQUIRED_FILES)} 个必需文件齐全")


def check_safety_copy(root: Path = ROOT) -> CheckResult:
    """2) Chinese safety-copy assertions on the research report (assembled in lesson 06)."""
    return _deferred_check(
        "研究报告安全文案",
        root / "src" / "research" / "report.py",
        pending="研究报告尚未组装(课 06 落地后启用)",
        landed="研究报告已落地但断言未实现:请随课 06 补充安全文案字符串断言",
    )


def check_frozen_dataset(root: Path = ROOT) -> CheckResult:
    """3) Frozen-dataset manifest/sha256 check (fetched in lesson 19, ADR-0004)."""
    return _deferred_check(
        "冻结数据集校验",
        root / "data" / "investment_gate" / "manifest.json",
        pending="冻结数据集尚未抓取(课 19 落地后启用)",
        landed="manifest 已入库但校验未实现:请随课 19 补充 sha256 校验",
    )


def check_pytest(root: Path = ROOT) -> CheckResult:
    """4) Full pytest run (ADR-0006: acceptance never depends on external services)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(root / "tests"), "-q"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    output_lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    summary = output_lines[-1] if output_lines else "pytest 无输出"
    status = PASS if proc.returncode == 0 else FAIL
    return CheckResult("全量 pytest", status, summary)


def run_checks(*, run_tests: bool = True) -> list[CheckResult]:
    results = [check_required_files(), check_safety_copy(), check_frozen_dataset()]
    if run_tests:
        results.append(check_pytest())
    return results


def format_results(results: list[CheckResult]) -> str:
    lines = [f"[{r.status}] {r.name} — {r.detail}" for r in results]
    passed = sum(r.status == PASS for r in results)
    skipped = sum(r.status == SKIPPED for r in results)
    failed = sum(r.status == FAIL for r in results)
    lines.append("")
    lines.append(f"已跑 {passed + failed} 项(通过 {passed}、失败 {failed}),跳过 {skipped} 项。")
    return "\n".join(lines)


def main(*, run_tests: bool = True) -> int:
    results = run_checks(run_tests=run_tests)
    print(format_results(results))
    if any(r.status == FAIL for r in results):
        print("\nQuant-Sandbox 校验未通过。")
        return 1
    print("\nQuant-Sandbox 校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
