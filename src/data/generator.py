"""确定性教学样本生成器(ADR-0004,票 #3)。

学参照物 ``scripts/generate_prices_sample.py`` 的思路(闭式三角函数和,
研报 §6.8),公式与时间窗都是我们自己写的——禁止拷贝参照物的任何数据
文件。产出的样本提交在 ``data/teaching_sample/`` 下,后续课程全部离线
可跑;重跑必须逐字节一致(票 #3 AC1):本模块任何地方都不许读墙钟
(当前真实时间)或使用未设种子的随机数发生器。``mint_sample``/``main``
负责写 CSV 并刷新数据集 manifest(``data.manifest``);命令行运行方式:
``python3 -m data.generator``。
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

SEED = 20260902  # 随机数种子:种子固定 ⇒ 随机序列固定 ⇒ 输出固定
START_DATE = date(2025, 3, 3)
ROW_COUNT = 381  # 与参照物教学样本规模同构(研报 §6.8)
SYMBOL = "QUANT-DEMO/USDT"
DATASET_DIR = DATA_DIR / "teaching_sample"
PRICES_NAME = "prices.csv"
COMPANY_NAME = "company.json"
# 生成时间随数据集版本固定:AC1 的「逐字节重跑」禁止读墙钟,所以铸造
# 时间戳是数据集身份的一部分——公式或时间窗变了才改它,绝不在写文件
# 时取「现在」。
GENERATED_AT = "2026-09-02T00:00:00Z"
MANIFEST_SOURCE = f"synthetic:src/data/generator.py (symbol={SYMBOL}, seed={SEED})"


def trading_days(start: date, count: int):
    """从 ``start`` 起依次产出 ``count`` 个工作日日期。

    这是一个生成器函数(体内有 yield):调用它不会立刻执行,而是返回
    一个惰性序列,被 for 循环拉动一次才算一步——要多少算多少。
    weekday() 周一=0 … 周日=6,小于 5 即周一到周五。
    """
    current = start
    yielded = 0
    while yielded < count:
        if current.weekday() < 5:
            yield current
            yielded += 1
        current += timedelta(days=1)


def sample_rows(seed: int = SEED) -> list[tuple[str, str]]:
    """收盘价样本:``(ISO 日期文本, 两位小数的价格文本)`` 的列表。"""

    def close_price(index: int, shock: float) -> str:
        # 闭式公式:线性底价 + 三个不同周期的正弦波(慢/中/快)+ 一段
        # 偶发的下沉 + 每行一点随机扰动。全部只依赖 index 与 shock,
        # 所以同种子必然同输出。
        base = 42.0 + index * 0.028
        slow = 2.30 * math.sin(index * 0.052 + 0.6)
        mid = 1.05 * math.sin(index * 0.149 + 2.0)
        fast = 0.40 * math.sin(index * 0.417 + 4.1)
        # max(0, sin(...))**2:只在正弦为正的那段缓慢下沉,像一段「行情疲软期」。
        dip = -1.35 * max(0.0, math.sin(index * 0.021 - 1.05)) ** 2
        price = max(35.0, base + slow + mid + fast + dip + shock)
        # f"{price:.2f}" 保留两位小数并转成文本(如 "44.07")——价格以
        # 文本形式落盘,后续记账层再经 Decimal 精确解读。
        return f"{price:.2f}"

    # random.Random(seed):自带独立状态的随机数发生器。不用全局 random
    # 正是为了「种子完全决定输出」,不受别处调用的影响。
    rng = random.Random(seed)
    # 扰动幅度 ±0.22(0.44 的一半);enumerate 给每个工作日配上从 0 开始的序号。
    return [
        (day.isoformat(), close_price(index, (rng.random() - 0.5) * 0.44))
        for index, day in enumerate(trading_days(START_DATE, ROW_COUNT))
    ]


def prices_csv_text(seed: int = SEED) -> str:
    """整份样本的 CSV 文本——AC1「重跑零 diff」比对的就是这个字符串。"""
    lines = ["date,close"]
    lines.extend(f"{date_text},{price}" for date_text, price in sample_rows(seed))
    return "\n".join(lines) + "\n"


def mint_sample(directory: Path = DATASET_DIR) -> dict:
    """写出 prices.csv,再对数据集目录刷新 manifest。

    company.json 是手写的叙事型资产档案,本来就活在数据集目录里(研报
    §6.8),本模块从不写它;manifest 同样把它纳入指纹,所以任何手改
    之后都要重新 mint 才能保持一致。返回刚写出的 manifest(dict)。
    """
    company = directory / COMPANY_NAME
    if not company.is_file():
        raise FileNotFoundError(f"company.json 缺失,请先手写资产档案:{company}")
    # parents=True 连父目录一起建;exist_ok=True 已存在也不报错。
    directory.mkdir(parents=True, exist_ok=True)
    # newline="\n" 钉死换行:Windows 文本写默认会把 \n 翻成 \r\n,那会
    # 让重铸的字节与入库不同,manifest 的 sha256 契约随之破裂。
    (directory / PRICES_NAME).write_text(prices_csv_text(), encoding="utf-8", newline="\n")
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
    """铸造数据集;「校验对不对」归 verify.py 管,写文件的不管审计。"""
    try:
        manifest = mint_sample(directory)
    except FileNotFoundError as error:
        # stream 参数化进来,测试才能用 StringIO 接住输出做断言。
        print(f"[FAIL] {error}", file=stream)
        return 1
    # 以下成功文案是用户可见文案(中文,ADR-0005)。
    print(
        f"已写入 {PRICES_NAME}({ROW_COUNT} 行)并刷新 manifest.json"
        f"({len(manifest['files'])} 个文件 sha256 已记录)。",
        file=stream,
    )
    return 0


if __name__ == "__main__":
    # 直接 `python3 -m data.generator` 运行时才执行 main;被 import 时不会执行。
    raise SystemExit(main())
