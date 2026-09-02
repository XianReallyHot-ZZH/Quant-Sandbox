"""Fill-cost models and the engine's result value objects.

The engine result is the ticket's declared seam (缝 2): strategies' order
intents come back as ``BacktestTrade`` rows plus a bar-by-bar equity
trajectory, all Decimal — floats appear only in the metrics layer (a later
lesson), never in the accounting carried here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from strategy_engine.backtest.candles import Candle
from strategy_engine.backtest.protocol import TAKER_ORDER_TYPES, OrderIntent, OrderSide


class FeeModel(Protocol):
    def calc(self, intent: OrderIntent, fill_price: Decimal) -> Decimal: ...


class SlippageModel(Protocol):
    def fill_price(self, intent: OrderIntent, candle: Candle) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class ZeroFee:
    """The teaching default: no costs (research report §3.6 engine defaults)."""

    def calc(self, intent: OrderIntent, fill_price: Decimal) -> Decimal:
        return Decimal("0")


@dataclass(frozen=True, slots=True)
class ZeroSlippage:
    """Market/stop fills land on the bar's close."""

    def fill_price(self, intent: OrderIntent, candle: Candle) -> Decimal:
        return candle.close


@dataclass(frozen=True, slots=True)
class ConstantBpsFee:
    """Minimal cost model: maker bps on limit fills, taker on market/stop.

    bps parameters are Decimal on purpose — passing a float here would leak
    binary noise straight into the books (``Decimal(0.1) != Decimal("0.1")``).
    """

    maker_bps: Decimal = Decimal("10")
    taker_bps: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        for name in ("maker_bps", "taker_bps"):
            if not isinstance(getattr(self, name), Decimal):
                raise TypeError(f"{name} 必须是 Decimal(拒绝 float 入账)")

    def calc(self, intent: OrderIntent, fill_price: Decimal) -> Decimal:
        bps = self.taker_bps if intent.type in TAKER_ORDER_TYPES else self.maker_bps
        return intent.qty * fill_price * bps / Decimal("10_000")


@dataclass(frozen=True, slots=True)
class ConstantBpsSlippage:
    """Constant adverse slippage in bps against the limit price or close."""

    bps: Decimal = Decimal("5")

    def __post_init__(self) -> None:
        if not isinstance(self.bps, Decimal):
            raise TypeError("bps 必须是 Decimal(拒绝 float 入账)")

    def fill_price(self, intent: OrderIntent, candle: Candle) -> Decimal:
        ref = intent.price if intent.price is not None else candle.close
        shift = self.bps / Decimal("10_000")
        if intent.side == OrderSide.BUY:
            return ref * (Decimal("1") + shift)
        return ref * (Decimal("1") - shift)


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    """One executed fill as recorded on the results seam."""

    ts: datetime
    symbol: str
    side: str
    qty: Decimal
    price: Decimal
    fee: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True, slots=True)
class RiskCheck:
    """What a risk manager answers when asked about an intent."""

    allowed: bool
    rule_id: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RiskRejection:
    """A pre-trade risk block (rule set lands in the next lesson, #5)."""

    ts: datetime
    symbol: str
    side: str
    rule_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class FillRejection:
    """The portfolio refusing a fill — explicit, never a silent drop (ADR-0006)."""

    ts: datetime
    symbol: str
    side: str
    reason: str


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    risk_rejections: list[RiskRejection] = field(default_factory=list)
    fill_rejections: list[FillRejection] = field(default_factory=list)


def render_result(result: BacktestResult) -> str:
    """A stable text rendering of a run — the unit AC1's byte-identical
    reruns diff. Only ordered lists and value objects appear here, never
    wall-clock time or unordered iteration, so equal runs render equal.
    """
    lines = [f"trades {len(result.trades)}"]
    lines.extend(
        (
            f"trade {t.ts.isoformat()} {t.symbol} {t.side} "
            f"qty={t.qty} price={t.price} fee={t.fee} realized={t.realized_pnl}"
        )
        for t in result.trades
    )
    lines.append(f"equity_curve {len(result.equity_curve)}")
    lines.extend((f"equity {ts.isoformat()} {equity}" for ts, equity in result.equity_curve))
    lines.append(f"fill_rejections {len(result.fill_rejections)}")
    lines.extend(
        (f"fill_rejection {r.ts.isoformat()} {r.symbol} {r.side} {r.reason}")
        for r in result.fill_rejections
    )
    lines.append(f"risk_rejections {len(result.risk_rejections)}")
    lines.extend(
        (f"risk_rejection {r.ts.isoformat()} {r.symbol} {r.side} {r.rule_id} {r.reason}")
        for r in result.risk_rejections
    )
    return "\n".join(lines) + "\n"
