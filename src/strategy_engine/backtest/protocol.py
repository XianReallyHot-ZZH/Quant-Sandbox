"""Order-intent value objects: the strategy-facing vocabulary of the engine.

``OrderIntent`` is an *intent*, never a fill: strategies describe what they
want (side, type, Decimal qty, optional limit/stop price, time in force)
and the bar loop decides if and when it executes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


# Market-like types take liquidity; resting limits make it. Single source of
# truth for fee tiers — never re-encode these as a set of strings.
TAKER_ORDER_TYPES = frozenset({OrderType.MARKET, OrderType.STOP, OrderType.STOP_LIMIT})


@dataclass(frozen=True, slots=True)
class OrderIntent:
    symbol: str
    side: OrderSide
    type: OrderType
    qty: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
