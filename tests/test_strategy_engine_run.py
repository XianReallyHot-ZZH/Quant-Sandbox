"""Engine main loop over the results seam (ticket #4, seam 2).

The public seam is ``BacktestEngine.run(candles, symbol, timeframe) ->
BacktestResult``: strategies submit Decimal order intents, the bar loop
settles them, and fills plus the equity trajectory are asserted here.
Hand-computed example #1 (zero costs): buy 10@100 then sell 10@110 on a
10000 start realizes 100.00 and ends flat at 10100.00.
"""

from decimal import Decimal

import pytest

from engine_testkit import SYMBOL, TF, T0, T1, make_candle
from strategy_engine.backtest.engine import BacktestEngine
from strategy_engine.backtest.models import BacktestResult, ZeroFee, ZeroSlippage
from strategy_engine.backtest.protocol import OrderIntent, OrderSide, OrderType, TimeInForce


def test_market_buy_then_sell_matches_hand_example() -> None:
    """手算样例 #1(零成本):bar1 买 10@100 → 现金 9000、bar1 权益 10000;
    bar2 卖 10@110 → 已实现 (110-100)*10 = 100.00、现金 10100、bar2 权益 10100。"""

    def strategy(ctx, candle):
        if len(ctx.history) == 1:
            return ctx.order_intent("buy", 10)
        if ctx.position().qty > 0:
            return ctx.order_intent("sell", 10)
        return None

    engine = BacktestEngine(strategy_fn=strategy, initial_capital=Decimal("10000"))
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "110")], SYMBOL, TF)

    assert isinstance(result, BacktestResult)
    assert [(t.side, t.qty, t.price, t.fee, t.realized_pnl) for t in result.trades] == [
        ("buy", Decimal("10"), Decimal("100"), Decimal("0"), Decimal("0")),
        ("sell", Decimal("10"), Decimal("110"), Decimal("0"), Decimal("100.00")),
    ]
    assert [t.symbol for t in result.trades] == [SYMBOL, SYMBOL]
    assert [t.ts for t in result.trades] == [T0, T1]
    assert result.equity_curve == [(T0, Decimal("10000")), (T1, Decimal("10100"))]


def test_default_costs_are_zero_and_market_fills_at_close() -> None:
    """默认零成本模型:市价单按当根 close 成交(ZeroSlippage)。"""
    seen_prices = []

    def strategy(ctx, candle):
        seen_prices.append(candle.close)
        return ctx.order_intent("buy", 1) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy)
    result = engine.run([make_candle(T0, "42")], SYMBOL, TF)
    assert seen_prices == [Decimal("42")]
    assert result.trades[0].price == Decimal("42")
    assert isinstance(engine.fee_model, ZeroFee)
    assert isinstance(engine.slippage_model, ZeroSlippage)


def test_strategy_context_sees_history_position_and_portfolio() -> None:
    """循环次序:bar1 成交在 bar2 可见 — history 含当根、position 反映上一根成交;
    portfolio 即记账层对象。"""
    observations = []

    def strategy(ctx, candle):
        observations.append(
            (len(ctx.history), ctx.symbol, ctx.timeframe, ctx.position().qty, ctx.portfolio.cash)
        )
        return ctx.order_intent("buy", 2) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy, initial_capital=Decimal("1000"))
    engine.run([make_candle(T0, "100"), make_candle(T1, "101")], SYMBOL, TF)
    assert observations == [
        (1, SYMBOL, TF, Decimal("0"), Decimal("1000")),
        (2, SYMBOL, TF, Decimal("2"), Decimal("800")),
    ]


def test_order_intent_helper_builds_decimal_value_object() -> None:
    """order_intent 辅助:数字经 str→Decimal(无 float 入账),枚举取 wire 值。"""
    intents = []

    def strategy(ctx, candle):
        if len(ctx.history) == 1:
            intent = ctx.order_intent("buy", 1.5, "limit", price=95.5)
            intents.append(intent)
        return None

    BacktestEngine(strategy_fn=strategy).run([make_candle(T0, "100")], SYMBOL, TF)
    (intent,) = intents
    assert isinstance(intent, OrderIntent)
    assert intent.symbol == SYMBOL
    assert intent.side is OrderSide.BUY
    assert intent.type is OrderType.LIMIT
    assert intent.time_in_force is TimeInForce.GTC
    assert intent.qty == Decimal("1.5")
    assert intent.price == Decimal("95.5")
    assert intent.qty.__class__ is Decimal and intent.price.__class__ is Decimal


def test_run_rejects_empty_candles_with_chinese_copy() -> None:
    with pytest.raises(ValueError, match="K 线序列不能为空"):
        BacktestEngine(strategy_fn=lambda ctx, candle: None).run([], SYMBOL, TF)
