"""引擎测试文件共用的脚手架:一个 K 线工厂 + 各场景复用的常量
(评审期抽取——当时四个测试文件已各自长出逐字节相同的副本)。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from strategy_engine.backtest.candles import Candle

SYMBOL = "QUANT-DEMO/USDT"
TF = "1d"
# 六个时间戳常量,对应场景里连续的六根日 bar(课 05 起双均线场景用到后两根)。
T0 = datetime(2025, 3, 3)
T1 = datetime(2025, 3, 4)
T2 = datetime(2025, 3, 5)
T3 = datetime(2025, 3, 6)
T4 = datetime(2025, 3, 7)
T5 = datetime(2025, 3, 10)


def make_candle(
    ts: datetime,
    close: str,
    *,
    low: str | None = None,
    high: str | None = None,
    volume: str = "1",
) -> Candle:
    """造一根 K 线:open/high/low 默认全部压平成 close,需要时再用关键字
    参数覆盖——多数场景只关心收盘价,这样一行就能造一根可用的 bar。
    volume 单独默认为 "1"(而非压平),因为「零成交量的 K 线」是风控
    规则要识别的异常形态,值得显式传 "0" 进来。"""
    close_dec = Decimal(close)
    return Candle(
        ts=ts,
        open=close_dec,
        high=Decimal(high) if high is not None else close_dec,
        low=Decimal(low) if low is not None else close_dec,
        close=close_dec,
        volume=Decimal(volume),
    )
