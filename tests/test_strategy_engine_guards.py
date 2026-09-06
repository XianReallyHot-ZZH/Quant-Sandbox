"""成交成本、显式拒单与成交前风控缝(票 #4)。

最小成本模型按基点计费、参数必须 Decimal——参照物把 float bps 直接喂
给 ``Decimal``(一处潜在泄漏);我们收 Decimal,成交路径全程无 float。
记账拒单(现金/持仓不足)显式记进结果而非静默丢弃,这是 ADR-0006
「不静默跳过」的哲学;风控缝本身用 stub 测试——五条真规则在下一课
(#5)落地。
"""

from decimal import Decimal

import pytest

from engine_testkit import SYMBOL, TF, T0, T1, T2, make_candle
from strategy_engine.backtest.engine import BacktestEngine
from strategy_engine.backtest.models import (
    ConstantBpsFee,
    ConstantBpsSlippage,
    RiskCheck,
    ZeroFee,
)


class StubRiskManager:
    """永远拦截的假风控;顺手数一数自己被问了几次。"""

    def __init__(self) -> None:
        self.checked = 0

    def check(self, intent, *, ctx, portfolio, candle) -> RiskCheck:
        self.checked += 1
        return RiskCheck(allowed=False, rule_id="STUB_RULE", reason="测试拦截")


class AllowOnlyFirstBar:
    """提交当根放行,之后任何一次复查都拦。"""

    def check(self, intent, *, ctx, portfolio, candle) -> RiskCheck:
        return RiskCheck(allowed=candle.ts == T0, rule_id="STUB_RULE", reason="测试拦截")


def test_market_round_trip_with_taker_fees_matches_hand_example() -> None:
    """手算样例 #4(taker 10bps):买 10@100 费 1000*10/10000 = 1.00,现金 8999、
    bar1 权益 9999;卖 10@110 费 1.10 → 已实现 (110-100)*10-1.10 = 98.90,
    现金 10097.90。"""

    def strategy(ctx, candle):
        if len(ctx.history) == 1:
            return ctx.order_intent("buy", 10)
        if ctx.position().qty > 0:
            return ctx.order_intent("sell", 10)
        return None

    engine = BacktestEngine(
        strategy_fn=strategy,
        initial_capital=Decimal("10000"),
        fee_model=ConstantBpsFee(taker_bps=Decimal("10")),
    )
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "110")], SYMBOL, TF)
    assert [(t.side, t.fee, t.realized_pnl) for t in result.trades] == [
        ("buy", Decimal("1.00"), Decimal("0")),
        ("sell", Decimal("1.10"), Decimal("98.90")),
    ]
    assert result.equity_curve == [(T0, Decimal("9999")), (T1, Decimal("10097.90"))]


def test_limit_fill_pays_maker_fee() -> None:
    """限价成交走 maker 费率:买 5@95、maker 5bps → 费 475*5/10000 = 0.2375。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 5, "limit", price=95) if len(ctx.history) == 1 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        fee_model=ConstantBpsFee(maker_bps=Decimal("5"), taker_bps=Decimal("10")),
    )
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "96", low="94")], SYMBOL, TF)
    assert result.trades[0].fee == Decimal("0.2375")


def test_bps_slippage_shifts_market_fill_price() -> None:
    """ConstantBpsSlippage 5bps:买按 close*1.0005 = 100.05 成交,卖按
    close*0.9995 = 99.95 成交。"""

    def strategy(ctx, candle):
        if len(ctx.history) == 1:
            return ctx.order_intent("buy", 1)
        if len(ctx.history) == 2:
            return ctx.order_intent("sell", 1)
        return None

    engine = BacktestEngine(
        strategy_fn=strategy,
        initial_capital=Decimal("10000"),
        fee_model=ZeroFee(),
        slippage_model=ConstantBpsSlippage(Decimal("5")),
    )
    result = engine.run(
        [make_candle(T0, "100"), make_candle(T1, "100"), make_candle(T2, "100")],
        SYMBOL,
        TF,
    )
    assert [t.price for t in result.trades] == [Decimal("100.05"), Decimal("99.95")]


def test_insufficient_cash_is_recorded_not_silently_dropped() -> None:
    """买 200@100 需 20000 > 现金 10000 → 无成交,但拒单显式入结果
    (ADR-0006:不静默跳过),权益不动。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 200) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy, initial_capital=Decimal("10000"))
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "100")], SYMBOL, TF)
    assert result.trades == []
    assert result.equity_curve == [(T0, Decimal("10000")), (T1, Decimal("10000"))]
    assert [(r.ts, r.symbol, r.side, r.reason) for r in result.fill_rejections] == [
        (T0, SYMBOL, "buy", "现金不足:需要 20000,持有 10000")
    ]


def test_selling_without_position_is_recorded_as_fill_rejection() -> None:
    """无持仓卖出 → 持仓不足拒单,中文文案入结果。"""

    def strategy(ctx, candle):
        return ctx.order_intent("sell", 1) if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy)
    result = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert result.trades == []
    assert "持仓不足" in result.fill_rejections[0].reason


def test_risk_block_prevents_fill_and_is_recorded() -> None:
    """风控缝:命中即拦截 — 无成交、无记账拒单,risk_rejections 带 rule_id。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1) if len(ctx.history) == 1 else None

    risk = StubRiskManager()
    engine = BacktestEngine(strategy_fn=strategy, risk_manager=risk)
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "100")], SYMBOL, TF)
    assert risk.checked == 1
    assert result.trades == []
    assert result.fill_rejections == []
    assert [(r.ts, r.rule_id, r.reason) for r in result.risk_rejections] == [
        (T0, "STUB_RULE", "测试拦截")
    ]
    assert result.equity_curve == [(T0, Decimal("10000")), (T1, Decimal("10000"))]


def test_risk_rechecks_resting_orders_at_fill_time() -> None:
    """挂单在触发当根复查风控:bar1 放行入簿,bar2 触及时被拦 → 拒单出簿、
    无成交(挂单风控在成交时点生效,而非提交时点一次性放行)。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 5, "limit", price=95) if len(ctx.history) == 1 else None

    risk = AllowOnlyFirstBar()
    engine = BacktestEngine(strategy_fn=strategy, risk_manager=risk)
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "96", low="94")], SYMBOL, TF)
    assert result.trades == []
    assert engine.pending_orders_snapshot() == []
    assert [(r.ts, r.rule_id) for r in result.risk_rejections] == [(T1, "STUB_RULE")]


def test_float_bps_is_rejected_at_the_boundary() -> None:
    """AC3 入口面:float bps 在构造点即 TypeError——Decimal(0.1) 的二进制噪
    声不许靠近账本。"""
    with pytest.raises(TypeError, match="maker_bps 必须是 Decimal"):
        ConstantBpsFee(maker_bps=0.5)
    with pytest.raises(TypeError, match="bps 必须是 Decimal"):
        ConstantBpsSlippage(5.0)


def test_priceless_limit_is_rejected_explicitly() -> None:
    """缺价限价单不允许无声消失(ADR-0006):提交即拒,中文理由入结果,
    不进挂单簿。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1, "limit") if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy)
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "100")], SYMBOL, TF)
    assert result.trades == []
    assert engine.pending_orders_snapshot() == []
    assert [(r.ts, r.reason) for r in result.fill_rejections] == [(T0, "限价单缺少价格")]


def test_stopless_stop_is_rejected_explicitly() -> None:
    """缺触发价止损单同上一条:显式拒,不挂簿。"""

    def strategy(ctx, candle):
        return ctx.order_intent("sell", 1, "stop") if len(ctx.history) == 1 else None

    engine = BacktestEngine(strategy_fn=strategy)
    result = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert result.trades == []
    assert [(r.ts, r.reason) for r in result.fill_rejections] == [(T0, "止损单缺少触发价")]
