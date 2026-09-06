"""Quant-Sandbox 交付物完整性验收(占位版,课 01)。

ADR-0006 的四类检查中,本模块已落地 1) 必需文件清单、4) 全量 pytest,
以及自课 02 起的 3) 数据集 manifest/sha256 校验(教学样本版);3) 的
投资门版与 2) 研究报告安全文案断言在对应课程落地前显式 SKIPPED。每个
被跳过的检查必须打印 SKIPPED 及原因——禁止静默通过。一旦受检产物已
存在而断言未实现,立即 FAIL(反静默跳过;研报 §8.5 #6)。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 与 app.py 同款的引导:让 src 下的 data.manifest 可以被 import。
sys.path.insert(0, str(ROOT / "src"))

from data.manifest import verify_manifest  # noqa: E402  (需要上面的 sys.path 引导)

# 三种检查状态:PASS=跑了且通过;SKIPPED=明确跳过(必须带原因);FAIL=失败。
PASS = "PASS"
SKIPPED = "SKIPPED"
FAIL = "FAIL"

# 仓库根必须存在的文件(相对路径);课 01 AC1 的清单。
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
    """一项检查的结果:名字、状态、可选明细。frozen 值对象,可安全比较。"""

    name: str
    status: str
    detail: str = ""


def _deferred_check(name: str, artifact: Path, *, pending: str, landed: str) -> CheckResult:
    """共用形状:产物未落地 → SKIPPED;落地而断言未实现 → FAIL(ADR-0006 #2)。"""
    if not artifact.is_file():
        return CheckResult(name, SKIPPED, pending)
    return CheckResult(name, FAIL, landed)


def check_required_files(root: Path = ROOT) -> CheckResult:
    """检查 1):必需文件清单。"""
    # 列表推导式收集所有缺失项;一个不缺才 PASS。
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    if missing:
        return CheckResult("必需文件清单", FAIL, f"缺失:{', '.join(missing)}")
    return CheckResult("必需文件清单", PASS, f"{len(REQUIRED_FILES)} 个必需文件齐全")


def check_safety_copy(root: Path = ROOT) -> CheckResult:
    """检查 2):研究报告的中文安全文案断言(报告在课 06 组装)。"""
    return _deferred_check(
        "研究报告安全文案",
        root / "src" / "research" / "report.py",
        pending="研究报告尚未组装(课 06 落地后启用)",
        landed="研究报告已落地但断言未实现:请随课 06 补充安全文案字符串断言",
    )


def check_frozen_dataset(root: Path = ROOT) -> CheckResult:
    """检查 3):冻结数据集 manifest/sha256 校验(课 19 抓取,ADR-0004)。"""
    return _deferred_check(
        "冻结数据集校验",
        root / "data" / "investment_gate" / "manifest.json",
        pending="冻结数据集尚未抓取(课 19 落地后启用)",
        landed="manifest 已入库但校验未实现:请随课 19 补充 sha256 校验",
    )


def check_teaching_sample(root: Path = ROOT) -> CheckResult:
    """检查 3) 的教学样本版:第一个 manifest 数据集,课 02 落地。"""
    problems = verify_manifest(root / "data" / "teaching_sample")
    if problems:
        return CheckResult("教学样本数据集", FAIL, "; ".join(problems))
    return CheckResult("教学样本数据集", PASS, "manifest.json sha256 全部一致")


def check_pytest(root: Path = ROOT) -> CheckResult:
    """检查 4):全量 pytest(ADR-0006:验收绝不依赖外部服务)。"""
    # 起一个子进程跑本仓库的测试套件;capture_output 把输出收回来,
    # text=True 让输出按文本而非字节处理。
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(root / "tests"), "-q"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    # stdout+stderr 拼起来按行切,滤掉空行;取最后一行——pytest 的汇总行
    # (如 "15 passed in 0.1s")作为这条检查的明细。
    output_lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    summary = output_lines[-1] if output_lines else "pytest 无输出"
    # 子进程退出码 0 = 测试全绿。
    status = PASS if proc.returncode == 0 else FAIL
    return CheckResult("全量 pytest", status, summary)


def run_checks(*, run_tests: bool = True) -> list[CheckResult]:
    """依序跑全部检查;run_tests=False 供测试用(避免在 pytest 里再嵌套跑 pytest)。"""
    results = [
        check_required_files(),
        check_safety_copy(),
        check_frozen_dataset(),
        check_teaching_sample(),
    ]
    if run_tests:
        results.append(check_pytest())
    return results


def format_results(results: list[CheckResult]) -> str:
    """渲染成人读的逐行报告:每项「[状态] 名字 — 明细」,末尾汇总已跑/跳过。"""
    lines = [f"[{r.status}] {r.name} — {r.detail}" for r in results]
    # 生成器表达式数出三种状态各多少项。
    passed = sum(r.status == PASS for r in results)
    skipped = sum(r.status == SKIPPED for r in results)
    failed = sum(r.status == FAIL for r in results)
    lines.append("")
    lines.append(f"已跑 {passed + failed} 项(通过 {passed}、失败 {failed}),跳过 {skipped} 项。")
    return "\n".join(lines)


def main(*, run_tests: bool = True) -> int:
    """跑全部检查并打印报告;有任何 FAIL 就以退出码 1 结束(脚本的「红灯」)。"""
    results = run_checks(run_tests=run_tests)
    print(format_results(results))
    if any(r.status == FAIL for r in results):
        print("\nQuant-Sandbox 校验未通过。")
        return 1
    print("\nQuant-Sandbox 校验通过。")
    return 0


if __name__ == "__main__":
    # 直接 `python3 verify.py` 运行时执行;被测试 import 时不会执行。
    raise SystemExit(main())
