"""Shared scaffolding for the engine test files: a bar factory and the
constants every scenario reuses (extracted during review — four files had
grown byte-identical copies)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from strategy_engine.backtest.candles import Candle

SYMBOL = "QUANT-DEMO/USDT"
TF = "1d"
T0 = datetime(2025, 3, 3)
T1 = datetime(2025, 3, 4)
T2 = datetime(2025, 3, 5)
T3 = datetime(2025, 3, 6)


def make_candle(
    ts: datetime, close: str, *, low: str | None = None, high: str | None = None
) -> Candle:
    """A bar whose open/high/low collapse onto close unless overridden."""
    close_dec = Decimal(close)
    return Candle(
        ts=ts,
        open=close_dec,
        high=Decimal(high) if high is not None else close_dec,
        low=Decimal(low) if low is not None else close_dec,
        close=close_dec,
        volume=Decimal("1"),
    )
