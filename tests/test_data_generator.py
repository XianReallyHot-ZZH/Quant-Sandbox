"""教学样本生成器契约:确定性与形状(票 #3 AC1)。

AC1:重跑生成器必须产出逐字节相同的输出——样本只能依赖闭式公式与
固定种子,绝不许读墙钟或用未设种子的随机数发生器。规模与参照物教学
样本同构(381 个工作日收盘价,研报 §6.8)。
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

# 每行必须是「YYYY-MM-DD,两位小数」的形状;re.compile 一次编译多处复用。
ROW_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2},\d+\.\d{2}$")


def test_regeneration_is_byte_identical() -> None:
    """AC1:连续两次生成逐字节一致。"""
    assert prices_csv_text() == prices_csv_text()


def _with_profile(directory) -> None:
    """把手写档案拷进去——铸造需要它,但从不写它。"""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "company.json").write_bytes((DATASET_DIR / "company.json").read_bytes())


def test_mint_reruns_are_byte_identical(tmp_path) -> None:
    """AC1 的完整铸造面:重跑——换地方跑、原地重跑——都写出相同字节。

    写入路径上任何一处墙钟都会在这里现形为一个 diff。
    """
    first, second = tmp_path / "first", tmp_path / "second"
    _with_profile(first)
    _with_profile(second)
    mint_sample(first)
    mint_sample(second)
    mint_sample(first)  # 原地重跑:验收原文说的「重跑两次」
    for name in ("prices.csv", "manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_minted_bytes_are_lf_only(tmp_path) -> None:
    """字节契约:铸出的文件在任何平台都是 LF——Windows 文本写默认会把
    \\n 翻成 \\r\\n,那会破坏 manifest 的跨平台 sha256(ADR-0004)。"""
    _with_profile(tmp_path)
    mint_sample(tmp_path)
    for name in ("prices.csv", "manifest.json"):
        assert b"\r" not in (tmp_path / name).read_bytes(), name


def test_main_mints_and_reports_success(tmp_path) -> None:
    _with_profile(tmp_path)
    # StringIO:内存里的「假 stdout」,让测试能接住 main 的输出做断言。
    stream = StringIO()
    assert main(tmp_path, stream) == 0
    assert f"{ROW_COUNT} 行" in stream.getvalue()


def test_main_fails_without_the_handwritten_profile(tmp_path) -> None:
    """铸造需要手写档案但从不写它;缺输入时退出码 1。"""
    stream = StringIO()
    assert main(tmp_path, stream) == 1
    assert "company.json" in stream.getvalue()


def test_sample_shape_matches_reference_scale() -> None:
    """表头 + 381 个工作日收盘价、两位小数、日期严格递增。"""
    rows = sample_rows()
    assert len(rows) == ROW_COUNT
    dates = [date_text for date_text, _ in rows]
    assert dates[0] == START_DATE.isoformat()
    # zip(dates, dates[1:]):相邻两两配对,检查严格递增。
    assert all(prior < later for prior, later in zip(dates, dates[1:]))
    for date_text, price_text in rows:
        weekday = date.fromisoformat(date_text).weekday()
        assert weekday < 5, f"{date_text} is not a weekday"
        assert ROW_PATTERN.match(f"{date_text},{price_text}"), price_text


def test_seed_participates_in_output() -> None:
    """换个种子输出必须变——种子若没参与,AC1 会「空洞地」通过。"""
    assert sample_rows(seed=1) != sample_rows(seed=SEED)
