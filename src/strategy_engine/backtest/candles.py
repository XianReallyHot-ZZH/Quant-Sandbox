"""The bar the engine loops over."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Candle:
    """One OHLCV bar; prices are Decimal (ADR-0002 hand-written numerics)."""

    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
