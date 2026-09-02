"""Determinism and float-tightness of the results seam (ticket #4 AC1/AC3).

AC1: the same candles + strategy must render byte-identical output on every
run — the engine may not consult the wall clock, an unseeded RNG, or
iteration order that varies between runs. The scenario below exercises every
result section (a market fill with taker fee, a resting limit, a resting
stop, one cash-refused fill, one position-refused fill, four equity points).

Hand-check of the scenario (10000 start, taker 10bps / maker 5bps):
bar1 buy 10@100 fee 1.00 → cash 8999; bar4's settling limit 100@95 costs
9504.75 > 8999 (refused) and the stop sell 15 exceeds the 10 held (refused),
so the only trade is the first buy and equity ends 8999+10*90 = 9899.
"""

import dataclasses
from decimal import Decimal

from engine_testkit import SYMBOL, TF, T0, T1, T2, T3, make_candle
from strategy_engine.backtest.engine import BacktestEngine
from strategy_engine.backtest.models import ConstantBpsFee, render_result


SCENARIO_CANDLES = [
    make_candle(T0, "100"),
    make_candle(T1, "110", low="109"),
    make_candle(T2, "105", low="104"),
    make_candle(T3, "90", low="89"),
]


def scenario_strategy(ctx, candle):
    """bar1 market buy 10; bar2 rest a 100@95 limit; bar3 rest a sell stop 15@91."""
    bars_seen = len(ctx.history)
    if bars_seen == 1:
        return ctx.order_intent("buy", 10)
    if bars_seen == 2:
        return ctx.order_intent("buy", 100, "limit", price=95)
    if bars_seen == 3:
        return ctx.order_intent("sell", 15, "stop", stop_price=91)
    return None


def make_engine() -> BacktestEngine:
    return BacktestEngine(
        strategy_fn=scenario_strategy,
        initial_capital=Decimal("10000"),
        fee_model=ConstantBpsFee(maker_bps=Decimal("5"), taker_bps=Decimal("10")),
    )


def test_scenario_actually_exercises_all_result_sections() -> None:
    """前提保证:场景真的产生 1 笔成交、2 条记账拒单、4 个权益点、清空挂单簿。"""
    result = make_engine().run(SCENARIO_CANDLES, SYMBOL, TF)
    assert len(result.trades) == 1
    assert [(t.side, t.price, t.fee) for t in result.trades] == [("buy", Decimal("100"), Decimal("1.00"))]
    assert len(result.fill_rejections) == 2
    assert "现金不足" in result.fill_rejections[0].reason
    assert "持仓不足" in result.fill_rejections[1].reason
    assert len(result.equity_curve) == 4
    assert result.equity_curve[-1][1] == Decimal("9899")


def test_same_input_renders_byte_identical_output() -> None:
    """AC1:同一输入逐字节同输出 — 两个全新引擎实例渲染结果完全一致。"""
    first = render_result(make_engine().run(SCENARIO_CANDLES, SYMBOL, TF))
    second = render_result(make_engine().run(SCENARIO_CANDLES, SYMBOL, TF))
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


def test_rerun_on_the_same_engine_instance_is_stable() -> None:
    """AC1 的重复运行面:同一实例连跑两次,渲染逐字节一致。"""
    engine = make_engine()
    first = render_result(engine.run(SCENARIO_CANDLES, SYMBOL, TF))
    second = render_result(engine.run(SCENARIO_CANDLES, SYMBOL, TF))
    assert first == second


def test_different_input_renders_different_bytes() -> None:
    """非空洞保证:输入变了输出必须变 — 否则 AC1 恒真而无意义。"""
    changed = [make_candle(T0, "101")] + SCENARIO_CANDLES[1:]
    baseline = render_result(make_engine().run(SCENARIO_CANDLES, SYMBOL, TF))
    altered = render_result(make_engine().run(changed, SYMBOL, TF))
    assert baseline != altered


def test_render_names_every_section_with_its_count() -> None:
    text = render_result(make_engine().run(SCENARIO_CANDLES, SYMBOL, TF))
    lines = text.splitlines()
    assert lines[0] == "trades 1"
    assert "equity_curve 4" in lines
    assert "fill_rejections 2" in lines
    assert "risk_rejections 0" in lines


def test_result_tree_carries_no_floats() -> None:
    """AC3:记账层无 float 泄漏 — 递归走查结果树,任何位置都不允许 float。"""

    def walk(node: object) -> None:
        assert not isinstance(node, float), f"float leaked into the result: {node!r}"
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            for field_value in (getattr(node, f.name) for f in dataclasses.fields(node)):
                walk(field_value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(make_engine().run(SCENARIO_CANDLES, SYMBOL, TF))
