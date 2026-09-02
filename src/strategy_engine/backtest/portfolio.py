"""Portfolio accounting: cash, positions, realized PnL, equity.

All-Decimal bookkeeping — the reference engine (research report §3.6) keeps
cash/position/equity in Decimal and so do we; float is only allowed later,
at the metrics layer. User-visible error copy is Chinese (ADR-0005) and is
asserted by tests: changing the wording is a contract change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class Position:
    symbol: str
    qty: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    def mark_to_market(self, last_price: Decimal) -> Decimal:
        """Unrealized PnL against the average entry price."""
        if self.qty == 0:
            return Decimal("0")
        return (last_price - self.avg_entry_price) * self.qty


@dataclass
class Portfolio:
    initial_cash: Decimal
    cash: Decimal = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.initial_cash, Decimal):
            raise TypeError("initial_cash 必须是 Decimal(拒绝 float 入账)")
        self.cash = self.initial_cash

    def apply_buy(self, symbol: str, qty: Decimal, price: Decimal, fee: Decimal) -> None:
        if qty <= 0 or price <= 0:
            raise ValueError("买入数量与价格必须为正")
        cost = qty * price + fee
        if cost > self.cash:
            raise ValueError(f"现金不足:需要 {cost},持有 {self.cash}")
        pos = self.positions.setdefault(symbol, Position(symbol=symbol))
        new_qty = pos.qty + qty
        pos.avg_entry_price = (
            (pos.avg_entry_price * pos.qty + price * qty) / new_qty if new_qty > 0 else Decimal("0")
        )
        pos.qty = new_qty
        self.cash -= cost

    def apply_sell(self, symbol: str, qty: Decimal, price: Decimal, fee: Decimal) -> Decimal:
        if qty <= 0 or price <= 0:
            raise ValueError("卖出数量与价格必须为正")
        pos = self.positions.get(symbol)
        if pos is None or pos.qty < qty:
            held = pos.qty if pos is not None else Decimal("0")
            raise ValueError(f"持仓不足:需卖出 {qty} {symbol},持有 {held}")
        proceeds = qty * price - fee
        realized = (price - pos.avg_entry_price) * qty - fee
        pos.qty -= qty
        pos.realized_pnl += realized
        if pos.qty == 0:
            pos.avg_entry_price = Decimal("0")
        self.cash += proceeds
        return realized

    def position(self, symbol: str) -> Position:
        """The position for ``symbol`` — a fresh flat one if never traded."""
        return self.positions.get(symbol, Position(symbol=symbol))

    def equity(self, last_prices: dict[str, Decimal]) -> Decimal:
        """Cash plus positions marked at ``last_prices`` (cost basis if unpriced)."""
        position_value = sum(
            (pos.qty * last_prices.get(symbol, pos.avg_entry_price) for symbol, pos in self.positions.items()),
            start=Decimal("0"),
        )
        return self.cash + position_value
