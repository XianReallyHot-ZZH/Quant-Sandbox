"""Limit and stop order semantics through the results seam (ticket #4 AC2).

GTC limit orders rest until some later bar's range crosses them (earliest
fill is the bar *after* submission); IOC limits fill on the submission bar
or die; stops trigger on the bar range crossing the stop price and fill at
the slippage price. Hand-computed example #2: resting limit buy 5@95 fills
on a 94–97 bar → cash 9525, equity 9525+5*96 = 10005.
"""

from decimal import Decimal

from engine_testkit import SYMBOL, TF, T0, T1, T2, make_candle
from strategy_engine.backtest.engine import BacktestEngine


def test_limit_buy_fills_at_limit_price_when_crossed() -> None:
    """手算样例 #2:bar1 挂限价买 5@95(GTC);bar2 最低 94 触及 → 按 95 成交
    (不是收盘价),现金 10000-475 = 9525,bar2 权益 9525+5*96 = 10005。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 5, "limit", price=95) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy, initial_capital=Decimal("10000"))
    result = engine.run(
        [make_candle(T0, "100"), make_candle(T1, "96", low="94", high="97")], SYMBOL, TF
    )
    assert [(t.ts, t.side, t.qty, t.price, t.realized_pnl) for t in result.trades] == [
        (T1, "buy", Decimal("5"), Decimal("95"), Decimal("0"))
    ]
    assert result.equity_curve == [(T0, Decimal("10000")), (T1, Decimal("10005"))]


def test_gtc_limit_does_not_fill_on_its_own_submission_bar() -> None:
    """GTC 限价单提交当根不结算:即使 bar1 最低价已触及,最早也在 bar2 成交。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1, "limit", price=95) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy)
    result = engine.run(
        [make_candle(T0, "100", low="94"), make_candle(T1, "100", low="94")], SYMBOL, TF
    )
    assert [t.ts for t in result.trades] == [T1]


def test_limit_buy_never_crossed_never_fills_and_stays_pending() -> None:
    """AC2 不成交路径:限价买 @90,最低价始终在 94 之上 → 零成交、权益不动、
    挂单仍在挂单簿里。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 2, "limit", price=90) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy, initial_capital=Decimal("10000"))
    result = engine.run(
        [make_candle(T0, "100", low="94"), make_candle(T1, "99", low="94")], SYMBOL, TF
    )
    assert result.trades == []
    assert result.equity_curve == [(T0, Decimal("10000")), (T1, Decimal("10000"))]
    pending = engine.pending_orders_snapshot()
    assert [p.price for p in pending] == [Decimal("90")]
    assert [p.qty for p in pending] == [Decimal("2")]


def test_ioc_limit_fills_on_submission_bar_or_dies() -> None:
    """IOC:提交当根可触及(bar1 low 94 ≤ 95)→ 立即按限价成交;不可触及
    (bar2 low 97 > 96)→ 直接丢弃,不进挂单簿。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1, "limit", price=95, time_in_force="IOC")

    engine = BacktestEngine(strategy_fn=strategy)
    result = engine.run(
        [make_candle(T0, "100", low="94"), make_candle(T1, "99", low="97")], SYMBOL, TF
    )
    assert [(t.ts, t.price) for t in result.trades] == [(T0, Decimal("95"))]
    assert engine.pending_orders_snapshot() == []


def test_sell_stop_hand_example_fills_at_close() -> None:
    """手算样例 #3:bar1 市价买 10@100;bar2 挂卖出止损 @95(最低 99 未触发);
    bar3 最低 94 触发 → 按收盘 96 成交,已实现 (96-100)*10 = -40,现金 9960。"""

    def strategy(ctx, candle):
        if len(ctx.history) == 1:
            return ctx.order_intent("buy", 10)
        if len(ctx.history) == 2:
            return ctx.order_intent("sell", 10, "stop", stop_price=95)
        return None

    engine = BacktestEngine(strategy_fn=strategy, initial_capital=Decimal("10000"))
    result = engine.run(
        [
            make_candle(T0, "100"),
            make_candle(T1, "99"),
            make_candle(T2, "96", low="94", high="97"),
        ],
        SYMBOL,
        TF,
    )
    assert [(t.ts, t.side, t.price, t.realized_pnl) for t in result.trades] == [
        (T0, "buy", Decimal("100"), Decimal("0")),
        (T2, "sell", Decimal("96"), Decimal("-40.00")),
    ]
    assert result.equity_curve == [
        (T0, Decimal("10000")),
        (T1, Decimal("9990")),
        (T2, Decimal("9960")),
    ]
    assert engine.pending_orders_snapshot() == []


def test_untriggered_stop_rests_in_pending_book() -> None:
    """未触发的止损单留在挂单簿,不产生成交。"""

    def strategy(ctx, candle):
        return ctx.order_intent("sell", 1, "stop", stop_price=50) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy)
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "99", low="94")], SYMBOL, TF)
    assert result.trades == []
    assert [p.stop_price for p in engine.pending_orders_snapshot()] == [Decimal("50")]


def test_buy_stop_triggers_when_high_crosses() -> None:
    """买入止损:bar 最高价上穿 stop 价触发,按收盘价(ZeroSlippage)成交。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1, "stop", stop_price=105) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy)
    result = engine.run(
        [make_candle(T0, "100"), make_candle(T1, "106", high="107", low="99")], SYMBOL, TF
    )
    assert [(t.ts, t.price) for t in result.trades] == [(T1, Decimal("106"))]


def test_rerun_starts_from_a_clean_pending_book() -> None:
    """同一引擎实例可重复 run:挂单簿与结果不跨运行串味。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1, "limit", price=90) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy)
    first = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    second = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert first.trades == second.trades == []
    assert len(engine.pending_orders_snapshot()) == 1


def test_stop_limit_triggers_on_stop_and_ignores_the_limit_leg() -> None:
    """stop_limit 沿用参照物语义:触发看 stop_price(最低 94 ≤ 95)、按收盘
    成交(96,而非限价 99),限价腿不建模——同构行为在此冻结。bar1 买 2@100,
    bar3 触发卖出 → 已实现 (96-100)*2 = -8.00。"""

    def strategy(ctx, candle):
        if len(ctx.history) == 1:
            return ctx.order_intent("buy", 2)
        if len(ctx.history) == 2:
            return ctx.order_intent("sell", 2, "stop_limit", stop_price=95, price=99)
        return None

    engine = BacktestEngine(strategy_fn=strategy, initial_capital=Decimal("10000"))
    result = engine.run(
        [
            make_candle(T0, "100"),
            make_candle(T1, "99"),
            make_candle(T2, "96", low="94", high="97"),
        ],
        SYMBOL,
        TF,
    )
    assert [(t.side, t.price, t.realized_pnl) for t in result.trades] == [
        ("buy", Decimal("100"), Decimal("0")),
        ("sell", Decimal("96"), Decimal("-8.00")),
    ]
    assert engine.pending_orders_snapshot() == []
