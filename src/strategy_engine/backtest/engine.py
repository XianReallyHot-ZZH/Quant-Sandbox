"""The event-driven bar loop (research report §3.6, engine #1).

Per candle: settle orders pending from earlier bars against this bar's
range, show the bar to the strategy (history includes the current candle),
then fill what it returns — market orders immediately at the slippage
price, limit/stop per their own semantics. Equity is recorded at each
close, so a fill decided on bar *t* at the latest becomes visible in bar
*t+1*'s settled state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from strategy_engine.backtest.candles import Candle
from strategy_engine.backtest.models import (
    BacktestResult,
    BacktestTrade,
    FeeModel,
    FillRejection,
    RiskCheck,
    RiskRejection,
    SlippageModel,
    ZeroFee,
    ZeroSlippage,
)
from strategy_engine.backtest.portfolio import Portfolio
from strategy_engine.backtest.portfolio import Position as PortfolioPosition
from strategy_engine.backtest.protocol import OrderIntent, OrderSide, OrderType, TimeInForce


@dataclass(slots=True)
class StrategyContext:
    """What a strategy may look at on the current bar."""

    symbol: str
    timeframe: str
    portfolio: Portfolio
    history: list[Candle] = field(default_factory=list)

    def position(self, symbol: str | None = None) -> PortfolioPosition:
        return self.portfolio.position(symbol or self.symbol)

    def order_intent(
        self,
        side: str,
        qty: Decimal | float | int,
        type: str = "market",
        price: Decimal | float | int | None = None,
        stop_price: Decimal | float | int | None = None,
        time_in_force: str = "GTC",
    ) -> OrderIntent:
        """Numbers are coerced through ``str`` so floats never enter the books."""
        return OrderIntent(
            symbol=self.symbol,
            side=OrderSide(side),
            type=OrderType(type),
            qty=Decimal(str(qty)),
            price=Decimal(str(price)) if price is not None else None,
            stop_price=Decimal(str(stop_price)) if stop_price is not None else None,
            time_in_force=TimeInForce(time_in_force),
        )


StrategyFn = Callable[[StrategyContext, Candle], OrderIntent | None]


class RiskManager(Protocol):
    """Pre-trade gate the engine consults before accepting any intent; the
    five built-in rules land in the next lesson (#5)."""

    def check(
        self, intent: OrderIntent, *, ctx: StrategyContext, portfolio: Portfolio, candle: Candle
    ) -> "RiskCheck": ...


@dataclass(slots=True)
class _PendingOrder:
    intent: OrderIntent
    submitted_ts: datetime


@dataclass
class BacktestEngine:
    strategy_fn: StrategyFn
    initial_capital: Decimal = Decimal("10000")
    fee_model: FeeModel = field(default_factory=ZeroFee)
    slippage_model: SlippageModel = field(default_factory=ZeroSlippage)
    risk_manager: RiskManager | None = None  # rules land in #5
    _pending: list[_PendingOrder] = field(default_factory=list, init=False)
    _risk_rejections: list[RiskRejection] = field(default_factory=list, init=False)
    _fill_rejections: list[FillRejection] = field(default_factory=list, init=False)

    def pending_orders_snapshot(self) -> list[OrderIntent]:
        """Intents still resting — the GTC book after the last settled bar."""
        return [entry.intent for entry in self._pending]

    def run(self, candles: list[Candle], symbol: str, timeframe: str) -> BacktestResult:
        if not candles:
            raise ValueError("K 线序列不能为空")

        portfolio = Portfolio(initial_cash=self.initial_capital)
        ctx = StrategyContext(symbol=symbol, timeframe=timeframe, portfolio=portfolio)
        trades: list[BacktestTrade] = []
        equity_curve: list[tuple[datetime, Decimal]] = []
        self._pending = []
        self._risk_rejections = []
        self._fill_rejections = []

        for candle in candles:
            self._settle_pending(candle, portfolio, trades, ctx)
            ctx.history.append(candle)
            intent = self.strategy_fn(ctx, candle)
            if intent is not None:
                self._submit(intent, candle, portfolio, trades, ctx)
            equity_curve.append((candle.ts, portfolio.equity({symbol: candle.close})))

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            risk_rejections=list(self._risk_rejections),
            fill_rejections=list(self._fill_rejections),
        )

    def _risk_allows(
        self,
        intent: OrderIntent,
        candle: Candle,
        ctx: StrategyContext,
        portfolio: Portfolio,
    ) -> bool:
        if self.risk_manager is None:
            return True
        result = self.risk_manager.check(intent, ctx=ctx, portfolio=portfolio, candle=candle)
        if result.allowed:
            return True
        self._risk_rejections.append(
            RiskRejection(
                ts=candle.ts,
                symbol=intent.symbol,
                side=intent.side.value,
                rule_id=result.rule_id,
                reason=result.reason,
            )
        )
        return False

    def _submit(
        self,
        intent: OrderIntent,
        candle: Candle,
        portfolio: Portfolio,
        trades: list[BacktestTrade],
        ctx: StrategyContext,
    ) -> None:
        if intent.type == OrderType.LIMIT and intent.price is None:
            self._record_fill_rejection(intent, candle, "限价单缺少价格")
            return
        if intent.type in {OrderType.STOP, OrderType.STOP_LIMIT} and intent.stop_price is None:
            self._record_fill_rejection(intent, candle, "止损单缺少触发价")
            return

        if not self._risk_allows(intent, candle, ctx, portfolio):
            return

        if intent.type == OrderType.MARKET:
            self._fill_at_price(
                intent, candle, self.slippage_model.fill_price(intent, candle), portfolio, trades
            )
            return

        if intent.type == OrderType.LIMIT and intent.time_in_force in {
            TimeInForce.IOC,
            TimeInForce.FOK,
        }:
            # Immediate-or-cancel: fill on this bar's range or drop — atomic
            # fills make IOC and FOK behave identically here.
            if intent.price is not None and self._limit_crossable(intent, candle):
                self._fill_at_price(intent, candle, intent.price, portfolio, trades)
            return

        self._pending.append(_PendingOrder(intent=intent, submitted_ts=candle.ts))

    def _settle_pending(
        self,
        candle: Candle,
        portfolio: Portfolio,
        trades: list[BacktestTrade],
        ctx: StrategyContext,
    ) -> None:
        if not self._pending:
            return

        still_pending: list[_PendingOrder] = []
        for entry in self._pending:
            if not self._try_fill_pending(entry, candle, portfolio, trades, ctx):
                still_pending.append(entry)
        self._pending = still_pending

    def _try_fill_pending(
        self,
        entry: _PendingOrder,
        candle: Candle,
        portfolio: Portfolio,
        trades: list[BacktestTrade],
        ctx: StrategyContext,
    ) -> bool:
        """Try to execute a resting order on ``candle``; True means it leaves the book."""
        intent = entry.intent

        if intent.type == OrderType.LIMIT:
            if not self._limit_crossable(intent, candle):
                return False
            if not self._risk_allows(intent, candle, ctx, portfolio):
                return True
            self._fill_at_price(intent, candle, intent.price, portfolio, trades)
            return True

        if intent.type in {OrderType.STOP, OrderType.STOP_LIMIT}:
            # The reference engine treats stop_limit like stop (the limit leg
            # is not modeled) — kept isomorphic on purpose, frozen by test.
            if not self._stop_triggered(intent, candle):
                return False
            if not self._risk_allows(intent, candle, ctx, portfolio):
                return True
            self._fill_at_price(
                intent, candle, self.slippage_model.fill_price(intent, candle), portfolio, trades
            )
            return True

        return True

    @staticmethod
    def _limit_crossable(intent: OrderIntent, candle: Candle) -> bool:
        if intent.price is None:
            return False
        if intent.side == OrderSide.BUY:
            return bool(candle.low <= intent.price)
        return bool(candle.high >= intent.price)

    @staticmethod
    def _stop_triggered(intent: OrderIntent, candle: Candle) -> bool:
        if intent.stop_price is None:
            return False
        if intent.side == OrderSide.BUY:
            return bool(candle.high >= intent.stop_price)
        return bool(candle.low <= intent.stop_price)

    def _record_fill_rejection(self, intent: OrderIntent, candle: Candle, reason: str) -> None:
        self._fill_rejections.append(
            FillRejection(
                ts=candle.ts,
                symbol=intent.symbol,
                side=intent.side.value,
                reason=reason,
            )
        )

    def _fill_at_price(
        self,
        intent: OrderIntent,
        candle: Candle,
        fill_price: Decimal,
        portfolio: Portfolio,
        trades: list[BacktestTrade],
    ) -> None:
        fee = self.fee_model.calc(intent, fill_price)
        try:
            if intent.side == OrderSide.BUY:
                portfolio.apply_buy(intent.symbol, intent.qty, fill_price, fee)
                realized = Decimal("0")
            else:
                realized = portfolio.apply_sell(intent.symbol, intent.qty, fill_price, fee)
        except ValueError as error:
            # The reference engine swallows this silently; we record the
            # refusal on the result instead (ADR-0006 no-silent-skip).
            self._record_fill_rejection(intent, candle, str(error))
            return

        trades.append(
            BacktestTrade(
                ts=candle.ts,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=fill_price,
                fee=fee,
                realized_pnl=realized,
            )
        )
