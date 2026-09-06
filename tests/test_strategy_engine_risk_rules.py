"""五条内置风控规则 + 命中即短路的 RiskManager(票 #5 AC1)。

规则集对照参照物 ``src/risk/manager.py`` 同构复现:rule_id 逐字相同
(它们是运行时契约,课 06 的风险 findings 层要按 id 与这里的拦截去重);
拒单理由是中文(ADR-0005)。阈值单位与参照物一致——风控阈值是**分数**
(0.05 = 5%),与出场配置的百分比(5 = 5%)不同,这一点在课 04 文档
里专门点破。每条规则至少一条触发测试:拦截时订单不产生成交,拒单显式
入结果(ADR-0006 不静默跳过)。
"""

from decimal import Decimal

import pytest

from engine_testkit import SYMBOL, TF, T0, T1, make_candle
from strategy_engine.backtest.engine import BacktestEngine
from strategy_engine.backtest.risk import (
    AbnormalCandleRule,
    KillSwitch,
    MaxDrawdownRule,
    MaxPositionRule,
    MaxSlippageRule,
    RiskManager,
)


def buy_on_first_bar(ctx, candle):
    return ctx.order_intent("buy", 1) if len(ctx.history) == 1 else None


def test_max_position_blocks_when_post_fill_notional_exceeds_cap() -> None:
    """MAX_POSITION_PCT:买 60@100 成交后名义 6000 > 上限 5000 → 拦截;
    无成交、无记账拒单,risk_rejections 记 rule_id 与中文理由。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 60) if len(ctx.history) == 1 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([MaxPositionRule(max_notional_usd=Decimal("5000"))]),
    )
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "100")], SYMBOL, TF)
    assert result.trades == []
    assert result.fill_rejections == []
    assert result.equity_curve == [(T0, Decimal("10000")), (T1, Decimal("10000"))]
    assert [(r.ts, r.rule_id) for r in result.risk_rejections] == [(T0, "MAX_POSITION_PCT")]
    assert "名义价值" in result.risk_rejections[0].reason


def test_max_position_allows_order_below_cap() -> None:
    """放行路径:成交后名义 4900 ≤ 5000 → 正常成交,risk_rejections 空。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 49) if len(ctx.history) == 1 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([MaxPositionRule(max_notional_usd=Decimal("5000"))]),
    )
    result = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert [t.side for t in result.trades] == ["buy"]
    assert result.risk_rejections == []


def test_manager_short_circuits_on_first_hit() -> None:
    """「命中即短路」契约:第一条规则拦下后,后面的规则不再被问。
    计数器规则放在拦截规则之后,checked 必须保持 0。"""

    class CountingRule:
        rule_id = "COUNTING"

        def __init__(self) -> None:
            self.checked = 0

        def check(self, intent, *, ctx, portfolio, candle):
            self.checked += 1
            from strategy_engine.backtest.models import RiskCheck

            return RiskCheck(allowed=True)

    class BlockingRule:
        rule_id = "BLOCK"

        def check(self, intent, *, ctx, portfolio, candle):
            from strategy_engine.backtest.models import RiskCheck

            return RiskCheck(allowed=False, rule_id="BLOCK", reason="测试拦截")

    counting = CountingRule()
    engine = BacktestEngine(
        strategy_fn=buy_on_first_bar,
        risk_manager=RiskManager([BlockingRule(), counting]),
    )
    result = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert counting.checked == 0
    assert result.risk_rejections[0].rule_id == "BLOCK"


def test_empty_manager_allows_everything() -> None:
    """空规则集 = 全放行:无拒单、正常成交(RiskManager 可安全空挂)。"""
    engine = BacktestEngine(strategy_fn=buy_on_first_bar, risk_manager=RiskManager())
    result = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert [t.side for t in result.trades] == ["buy"]
    assert result.risk_rejections == []


def test_max_drawdown_blocks_buy_after_equity_falls_from_peak() -> None:
    """MAX_DAILY_LOSS_PCT(有状态):bar1 权益 10000 记为峰值;bar1 买 10@100
    后 bar2 收 85 → 权益 9000+850=9850,回撤 150/10000=1.5% ≥ 上限 1%
    → bar2 的买入被拦;无成交增量,拒单 rule_id + 中文理由入结果。"""

    def strategy(ctx, candle):
        if len(ctx.history) == 1:
            return ctx.order_intent("buy", 10)
        if len(ctx.history) == 2:
            return ctx.order_intent("buy", 1)
        return None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([MaxDrawdownRule(max_drawdown_pct=Decimal("0.01"))]),
    )
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "85")], SYMBOL, TF)
    # bar1 的买入发生在峰值刚记下、回撤为 0 时,照常成交。
    assert [t.side for t in result.trades] == ["buy"]
    assert [(r.ts, r.rule_id) for r in result.risk_rejections] == [(T1, "MAX_DAILY_LOSS_PCT")]
    assert "回撤" in result.risk_rejections[0].reason


def test_max_drawdown_never_blocks_sells() -> None:
    """回撤中卖出(减仓/出场)不受限:bar2 跌破阈值后卖 10 仍成交——
    风控拦开仓,不拦离场。"""

    def strategy(ctx, candle):
        if len(ctx.history) == 1:
            return ctx.order_intent("buy", 10)
        if len(ctx.history) == 2:
            return ctx.order_intent("sell", 10)
        return None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([MaxDrawdownRule(max_drawdown_pct=Decimal("0.01"))]),
    )
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "85")], SYMBOL, TF)
    assert [t.side for t in result.trades] == ["buy", "sell"]
    assert result.risk_rejections == []


def test_max_slippage_blocks_when_intra_bar_spread_exceeds_cap() -> None:
    """MAX_SLIPPAGE_PCT:当根振幅 (110-90)/100 = 20% > 上限 10% → 买入
    被拦,拒单理由给出 H/L/C 三个数。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1) if len(ctx.history) == 1 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([MaxSlippageRule(max_spread_pct=Decimal("0.1"))]),
    )
    result = engine.run([make_candle(T0, "100", low="90", high="110")], SYMBOL, TF)
    assert result.trades == []
    assert [(r.rule_id) for r in result.risk_rejections] == ["MAX_SLIPPAGE_PCT"]
    assert "振幅" in result.risk_rejections[0].reason


def test_max_slippage_allows_flat_candle() -> None:
    """放行路径:平 K 线(H=L=C)振幅 0 → 正常成交。"""
    engine = BacktestEngine(
        strategy_fn=buy_on_first_bar,
        risk_manager=RiskManager([MaxSlippageRule(max_spread_pct=Decimal("0.1"))]),
    )
    result = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert [t.side for t in result.trades] == ["buy"]
    assert result.risk_rejections == []


def test_abnormal_candle_blocks_zero_volume_with_price_range() -> None:
    """ABNORMAL_ORDERBOOK 形态一:零成交量但 H≠L——行情损坏或停牌的
    典型特征,买入被拦。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1) if len(ctx.history) == 1 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([AbnormalCandleRule(max_price_jump_pct=Decimal("0.1"))]),
    )
    result = engine.run([make_candle(T0, "100", low="99", volume="0")], SYMBOL, TF)
    assert result.trades == []
    assert [r.rule_id for r in result.risk_rejections] == ["ABNORMAL_ORDERBOOK"]
    assert "零成交量" in result.risk_rejections[0].reason


def test_abnormal_candle_blocks_flat_price_with_volume() -> None:
    """ABNORMAL_ORDERBOOK 形态二:H=L 却有成交量——疑似陈旧行情。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1) if len(ctx.history) == 1 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([AbnormalCandleRule(max_price_jump_pct=Decimal("0.1"))]),
    )
    result = engine.run([make_candle(T0, "100", volume="5")], SYMBOL, TF)
    assert result.trades == []
    assert "零波动" in result.risk_rejections[0].reason


def test_abnormal_candle_blocks_excessive_close_to_close_jump() -> None:
    """ABNORMAL_ORDERBOOK 形态三:相邻收盘跳动 |130-100|/100 = 30% >
    上限 10% → bar2 的买入被拦(提交时点检查,history 已含当根)。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1) if len(ctx.history) == 2 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([AbnormalCandleRule(max_price_jump_pct=Decimal("0.1"))]),
    )
    result = engine.run(
        [
            make_candle(T0, "100", low="99", high="101"),
            make_candle(T1, "130", low="129", high="131"),
        ],
        SYMBOL,
        TF,
    )
    assert result.trades == []
    assert [r.ts for r in result.risk_rejections] == [T1]
    assert "跳动" in result.risk_rejections[0].reason


def test_abnormal_candle_recheck_at_settle_time_sees_same_previous_close() -> None:
    """挂单复查时点的「上一根收盘价」:结算发生在 history 追加当根**之前**,
    提交发生在**之后**——规则内部取「history 里最后一根不是当根」的收盘
    价,两种时点都指向同一根 bar1。bar2 跳动 30% → 挂单在触及当根被拦,
    出簿、无成交。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 5, "limit", price=95) if len(ctx.history) == 1 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([AbnormalCandleRule(max_price_jump_pct=Decimal("0.1"))]),
    )
    result = engine.run(
        [
            make_candle(T0, "100", low="99", high="101"),
            make_candle(T1, "130", low="94", high="131"),
        ],
        SYMBOL,
        TF,
    )
    assert result.trades == []
    assert engine.pending_orders_snapshot() == []
    assert [(r.ts, r.rule_id) for r in result.risk_rejections] == [(T1, "ABNORMAL_ORDERBOOK")]


def test_abnormal_candle_allows_well_formed_candles() -> None:
    """放行路径:有量、有波动、跳动小的 K 线序列正常成交。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 1) if len(ctx.history) == 2 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        risk_manager=RiskManager([AbnormalCandleRule(max_price_jump_pct=Decimal("0.1"))]),
    )
    result = engine.run(
        [
            make_candle(T0, "100", low="99", high="101"),
            make_candle(T1, "102", low="101", high="103"),
        ],
        SYMBOL,
        TF,
    )
    assert [t.side for t in result.trades] == ["buy"]
    assert result.risk_rejections == []


def test_kill_switch_blocks_everything_once_tripped() -> None:
    """EMERGENCY_HALT:trip 之后一刀切——买入被拦,理由带上触发原因;
    reset 之后恢复放行。"""

    switch = KillSwitch()
    switch.trip("人工触发紧急停止")
    engine = BacktestEngine(
        strategy_fn=buy_on_first_bar,
        risk_manager=RiskManager([switch]),
    )
    result = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert result.trades == []
    assert [r.rule_id for r in result.risk_rejections] == ["EMERGENCY_HALT"]
    assert "人工触发紧急停止" in result.risk_rejections[0].reason

    switch.reset()
    rerun = engine.run([make_candle(T0, "100")], SYMBOL, TF)
    assert [t.side for t in rerun.trades] == ["buy"]
    assert rerun.risk_rejections == []


def test_float_thresholds_are_rejected_at_the_boundary() -> None:
    """与课 03 的 bps 参数同一条边界:阈值传 float 直接 TypeError,
    不做静默 Decimal(str(...)) 转换(参照物会转,我们不转)。"""
    with pytest.raises(TypeError, match="max_notional_usd 必须是 Decimal"):
        MaxPositionRule(max_notional_usd=5000)
    with pytest.raises(TypeError, match="max_drawdown_pct 必须是 Decimal"):
        MaxDrawdownRule(max_drawdown_pct=0.01)
    with pytest.raises(TypeError, match="max_spread_pct 必须是 Decimal"):
        MaxSlippageRule(max_spread_pct=0.1)
    with pytest.raises(TypeError, match="max_price_jump_pct 必须是 Decimal"):
        AbnormalCandleRule(max_price_jump_pct=0.1)
