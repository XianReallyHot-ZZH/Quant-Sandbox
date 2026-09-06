"""出场判定:止损/止盈/移动止损/超时平仓/信号反转(票 #5 AC2)。

对照参照物 ``backtest/rolling/risk/position.py`` 的 ``check_exit`` 同构
复现,优先级顺序照抄:移动止损 → 止损 → 止盈 → 超时平仓 → 信号反转
(保命的单先判,落袋的单后判)。出场原因的中文文案是运行时契约
(ADR-0005):改一个字就是改契约,必须有测试锁死。

单位约定:出场阈值是**百分比**(``3`` = 3%),与风控阈值的分数制
(``0.03`` = 3%)不同——参照物两处单位不一致,我们照抄并在课 04 文档
点破。前半是 check_exit 纯函数的判定;后半过引擎(缝 2):出场必须
以「带 exit_reason 的平仓成交」出现在 BacktestResult 上。
"""

from decimal import Decimal

import pytest

from engine_testkit import SYMBOL, TF, T0, T1, T2, make_candle
from strategy_engine.backtest.engine import BacktestEngine
from strategy_engine.backtest.exits import ExitConfig, TrackedPosition, check_exit
from strategy_engine.backtest.models import RiskCheck, render_result
from strategy_engine.backtest.risk import KillSwitch, RiskManager


def make_position(entry: str = "100", entry_idx: int = 0, peak: str | None = None) -> TrackedPosition:
    """一手多头跟踪仓:默认 100 入场、第 0 根入场、峰值 = 入场价。"""
    return TrackedPosition(
        entry_price=Decimal(entry), entry_idx=entry_idx, peak_price=Decimal(peak or entry)
    )


def test_stop_loss_fires_below_threshold() -> None:
    """止损:入场 100、价 94 → pnl -6% ≤ -3% → 出场,文案「止损」。"""
    decision = check_exit(
        make_position(), Decimal("94"), None, bar_idx=5, config=ExitConfig(stop_loss_pct=Decimal("3"))
    )
    assert decision.should_exit is True
    assert decision.reason == "止损"


def test_take_profit_fires_above_threshold() -> None:
    """止盈:入场 100、价 106 → pnl +6% ≥ 5% → 出场,文案「止盈」。"""
    decision = check_exit(
        make_position(),
        Decimal("106"),
        None,
        bar_idx=5,
        config=ExitConfig(take_profit_pct=Decimal("5")),
    )
    assert decision.should_exit is True
    assert decision.reason == "止盈"


def test_trailing_stop_fires_when_price_falls_off_peak() -> None:
    """移动止损:峰值 120、回撤阈值 5% → 触发线 114;价 113 ≤ 114 → 出场。
    此时 pnl = +13% 并未触及止损/止盈——这是移动止损自己的路径。"""
    decision = check_exit(
        make_position(peak="120"),
        Decimal("113"),
        None,
        bar_idx=5,
        config=ExitConfig(trailing_stop_pct=Decimal("5")),
    )
    assert decision.should_exit is True
    assert decision.reason == "移动止损"


def test_trailing_stop_takes_priority_over_fixed_stop() -> None:
    """优先级契约:价 90 同时满足移动止损(峰值 110、3% → 触发线 106.7)
    与固定止损(pnl -10% ≤ -5%)——先判的是移动止损。"""
    decision = check_exit(
        make_position(peak="110"),
        Decimal("90"),
        None,
        bar_idx=5,
        config=ExitConfig(stop_loss_pct=Decimal("5"), trailing_stop_pct=Decimal("3")),
    )
    assert decision.reason == "移动止损"


def test_time_stop_fires_at_max_hold_bars() -> None:
    """超时平仓:第 0 根入场、最长持有 2 根,第 2 根检查时 bars_held=2
    → 出场;价格若无恙,前面的价差类条件都不命中。"""
    decision = check_exit(
        make_position(),
        Decimal("101"),
        None,
        bar_idx=2,
        config=ExitConfig(max_hold_bars=2),
    )
    assert decision.should_exit is True
    assert decision.reason == "超时平仓"


def test_signal_reversal_fires_on_non_positive_score() -> None:
    """信号反转:多头遇到 ≤ 0 的信号分 → 出场(参照物阈值硬编码 0,
    LONG 在 score ≤ 0 时离场);正分不出场。"""
    config = ExitConfig()
    assert check_exit(make_position(), Decimal("100"), Decimal("-1"), 3, config).reason == "信号反转"
    assert check_exit(make_position(), Decimal("100"), Decimal("0"), 3, config).reason == "信号反转"
    assert check_exit(make_position(), Decimal("100"), Decimal("0.5"), 3, config).should_exit is False


def test_no_signal_score_means_no_reversal_exit() -> None:
    """sig_score=None 表示「本策略不给信号」——反转分支整体跳过,
    哪怕其余条件也都不满足也不出场。"""
    decision = check_exit(
        make_position(), Decimal("100"), None, bar_idx=9, config=ExitConfig(max_hold_bars=0)
    )
    assert decision.should_exit is False
    assert decision.reason == ""


def test_hold_within_bands_keeps_position() -> None:
    """正常持有:价差在带内、未超时、信号为正 → 不出场。"""
    decision = check_exit(
        make_position(),
        Decimal("103"),
        Decimal("1"),
        bar_idx=1,
        config=ExitConfig(
            stop_loss_pct=Decimal("3"), take_profit_pct=Decimal("5"), max_hold_bars=10
        ),
    )
    assert decision.should_exit is False


def test_exit_config_rejects_float_thresholds() -> None:
    """与风控阈值同一条边界:出场阈值传 float 构造点即 TypeError。"""
    with pytest.raises(TypeError, match="stop_loss_pct 必须是 Decimal"):
        ExitConfig(stop_loss_pct=3.0)
    with pytest.raises(TypeError, match="take_profit_pct 必须是 Decimal"):
        ExitConfig(take_profit_pct=5.0)
    with pytest.raises(TypeError, match="trailing_stop_pct 必须是 Decimal"):
        ExitConfig(trailing_stop_pct=2.0)


# ---------------------------------------------------------------------------
# 引擎集成(缝 2):出场必须以「带 exit_reason 的平仓成交」出现在结果上。
# 隔离手法:只考察一条出场路径时,把其余阈值放到够不到的地方。
# ---------------------------------------------------------------------------

# 隔离用配置:止损/止盈都推到 50%/500%,任何教学场景的价格都够不到。
FAR_AWAY = {"stop_loss_pct": Decimal("50"), "take_profit_pct": Decimal("500")}


def buy_once_then_hold(ctx, candle):
    """bar1 市价买 10,之后什么都不做——把出场决定权完全交给引擎。"""
    return ctx.order_intent("buy", 10) if len(ctx.history) == 1 else None


def test_engine_stop_loss_closes_position_with_reason() -> None:
    """止损路径(引擎级):bar1 买 10@100;bar2 收 94 → 浮亏 6% ≥ 3%,
    引擎替策略平仓:卖出成交带 exit_reason=「止损」,权益回到纯现金
    9000 + 940 = 9940。"""
    engine = BacktestEngine(
        strategy_fn=buy_once_then_hold,
        exit_config=ExitConfig(stop_loss_pct=Decimal("3")),
    )
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "94")], SYMBOL, TF)
    assert [(t.side, t.price, t.exit_reason) for t in result.trades] == [
        ("buy", Decimal("100"), ""),
        ("sell", Decimal("94"), "止损"),
    ]
    assert result.equity_curve[-1] == (T1, Decimal("9940"))


def test_engine_take_profit_closes_position_with_reason() -> None:
    """止盈路径(引擎级):bar2 收 106 → +6% ≥ 5%,平仓带「止盈」。"""
    engine = BacktestEngine(
        strategy_fn=buy_once_then_hold,
        exit_config=ExitConfig(take_profit_pct=Decimal("5")),
    )
    result = engine.run([make_candle(T0, "100"), make_candle(T1, "106")], SYMBOL, TF)
    assert result.trades[-1].exit_reason == "止盈"
    assert result.trades[-1].side == "sell"


def test_engine_trailing_stop_ratchets_then_closes() -> None:
    """移动止损路径(引擎级):bar2 收 120 峰值爬到 120 不出场;bar3 收
    112 ≤ 触发线 114 → 平仓带「移动止损」——且这笔不是止损(pnl 仍为正)。"""
    engine = BacktestEngine(
        strategy_fn=buy_once_then_hold,
        exit_config=ExitConfig(trailing_stop_pct=Decimal("5"), **FAR_AWAY),
    )
    result = engine.run(
        [make_candle(T0, "100"), make_candle(T1, "120"), make_candle(T2, "112")],
        SYMBOL,
        TF,
    )
    assert len(result.trades) == 2
    assert result.trades[-1].exit_reason == "移动止损"
    assert result.trades[-1].ts == T2


def test_engine_time_stop_closes_after_max_hold_bars() -> None:
    """超时平仓路径(引擎级):第 0 根入场、上限 2 根;bar2(bars_held=1)
    不出,bar3(bars_held=2)平仓带「超时平仓」。"""
    engine = BacktestEngine(
        strategy_fn=buy_once_then_hold,
        exit_config=ExitConfig(max_hold_bars=2, **FAR_AWAY),
    )
    result = engine.run(
        [make_candle(T0, "100"), make_candle(T1, "101"), make_candle(T2, "101")],
        SYMBOL,
        TF,
    )
    assert result.trades[-1].exit_reason == "超时平仓"
    assert result.trades[-1].ts == T2


def test_engine_signal_reversal_closes_on_negative_score() -> None:
    """信号反转路径(引擎级):信号函数前两根给 +1,第三根转 −1 → 平仓带
    「信号反转」。信号函数与策略看到同一份 history(含当根)。"""

    def signal(ctx, candle):
        return Decimal("1") if len(ctx.history) < 3 else Decimal("-1")

    engine = BacktestEngine(
        strategy_fn=buy_once_then_hold,
        exit_config=ExitConfig(max_hold_bars=0, **FAR_AWAY),
        signal_fn=signal,
    )
    result = engine.run(
        [make_candle(T0, "100"), make_candle(T1, "100"), make_candle(T2, "100")],
        SYMBOL,
        TF,
    )
    assert result.trades[-1].exit_reason == "信号反转"
    assert result.trades[-1].ts == T2


def test_engine_without_signal_fn_never_reversal_exits() -> None:
    """不给 signal_fn:反转分支不存在——仓位一直拿到序列结束。"""
    engine = BacktestEngine(
        strategy_fn=buy_once_then_hold,
        exit_config=ExitConfig(max_hold_bars=0, **FAR_AWAY),
    )
    result = engine.run(
        [make_candle(T0, "100"), make_candle(T1, "100"), make_candle(T2, "100")],
        SYMBOL,
        TF,
    )
    assert [t.side for t in result.trades] == ["buy"]


def test_exit_not_checked_on_the_entry_bar_of_a_settled_fill() -> None:
    """入场当根不查出场:bar1 挂限价 95,bar2 低点 94 触及、结算成交
    (entry_idx=1);bar2 收 90 虽已浮亏 5.26% ≥ 5%,但当根跳过;bar3
    收 89 → 「止损」在 T2 成交。出场最迟次根生效,与挂单语义一致。"""

    def strategy(ctx, candle):
        return ctx.order_intent("buy", 10, "limit", price=95) if len(ctx.history) == 1 else None

    engine = BacktestEngine(
        strategy_fn=strategy,
        exit_config=ExitConfig(stop_loss_pct=Decimal("5"), take_profit_pct=Decimal("500")),
    )
    result = engine.run(
        [
            make_candle(T0, "100"),
            make_candle(T1, "90", low="94", high="96"),
            make_candle(T2, "89", low="88", high="90"),
        ],
        SYMBOL,
        TF,
    )
    assert [(t.ts, t.side, t.price, t.exit_reason) for t in result.trades] == [
        (T1, "buy", Decimal("95"), ""),
        (T2, "sell", Decimal("89"), "止损"),
    ]


def test_exit_blocked_by_risk_is_retried_next_bar() -> None:
    """风控闸门不分进出:出场卖单同样过检。第二问时被拉闸 → 无平仓成
    交、仓位保留,拒单记 EMERGENCY_HALT;下一根条件仍在,重试仍被拦。
    出场被拦不是丢信号——条件持续就持续重试。"""

    class TripOnSecondCheck:
        """第一次问放行;第二次问拉闸(恰好是出场卖单的风检)。"""

        rule_id = "TRIPPER"

        def __init__(self, switch: KillSwitch) -> None:
            self._switch = switch
            self._asked = 0

        def check(self, intent, *, ctx, portfolio, candle):
            self._asked += 1
            if self._asked >= 2:
                self._switch.trip("测试拉闸")
            return RiskCheck(allowed=True)

    switch = KillSwitch()
    engine = BacktestEngine(
        strategy_fn=buy_once_then_hold,
        risk_manager=RiskManager([TripOnSecondCheck(switch), switch]),
        exit_config=ExitConfig(stop_loss_pct=Decimal("3")),
    )
    result = engine.run(
        [make_candle(T0, "100"), make_candle(T1, "94"), make_candle(T2, "94")],
        SYMBOL,
        TF,
    )
    assert [t.side for t in result.trades] == ["buy"]
    assert [r.rule_id for r in result.risk_rejections] == ["EMERGENCY_HALT", "EMERGENCY_HALT"]
    assert engine.pending_orders_snapshot() == []


def test_render_result_carries_exit_reason_deterministically() -> None:
    """缝 2 的稳定渲染:出场原因出现在 trade 行尾(仅有出场的成交带),
    同输入两次运行逐字节一致。"""
    engine = BacktestEngine(
        strategy_fn=buy_once_then_hold,
        exit_config=ExitConfig(stop_loss_pct=Decimal("3")),
    )
    candles = [make_candle(T0, "100"), make_candle(T1, "94")]
    first = render_result(engine.run(candles, SYMBOL, TF))
    second = render_result(engine.run(candles, SYMBOL, TF))
    assert first == second
    assert "exit=止损" in first
    assert first.count("exit=") == 1
