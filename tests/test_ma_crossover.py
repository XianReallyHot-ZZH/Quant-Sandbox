"""双均线交叉策略(票 #6,课 05)。

策略的公开缝是 ``make_ma_crossover_strategy(short, long)`` 返回的
StrategyFn:短均线上穿长均线 → 全仓买入;下穿 → 清仓卖出;窗口未填满或
持平时不下单。全部断言走引擎结果缝(缝 2):跑真实 bar 循环,看成交。
手算样例:收盘 100,100,100,110,120(short=2/long=3)——第 4 根
short=(100+110)/2=105 > long=(100+100+110)/3≈103.33,金叉成立。
"""

from decimal import Decimal

from engine_testkit import SYMBOL, T0, T1, T2, T3, T4, T5, TF, make_candle
from strategy_engine.backtest.engine import BacktestEngine
from strategy_engine.strategies.ma_crossover import make_ma_crossover_strategy


def _run(closes: list[str], short: int, long: int):
    """小工具:按收盘价序列造 K 线,用双均线策略跑一遍,返回结果。"""
    stamps = [T0, T1, T2, T3, T4, T5][: len(closes)]
    candles = [make_candle(ts, close) for ts, close in zip(stamps, closes)]
    engine = BacktestEngine(
        strategy_fn=make_ma_crossover_strategy(short, long),
        initial_capital=Decimal("10000"),
    )
    return engine.run(candles, SYMBOL, TF)


def test_no_order_before_windows_fill_or_on_flat_cross() -> None:
    """窗口未填满(前两根)与均线持平时(第 3 根 100 = 100)都不下单。"""
    result = _run(["100", "100", "100"], short=2, long=3)
    assert result.trades == []


def test_golden_cross_buys_full_cash_and_holds() -> None:
    """金叉当根全仓买入,此后持有不动。数量 = 现金/收盘 **按 8 位步长
    向下取整**(10000/110 = 90.90909090…→ 90.90909090):不取整的除法
    尘埃会让成本越过现金、被记账层拒单——真样本上踩过的坑。"""
    result = _run(["100", "100", "100", "110", "120"], short=2, long=3)
    assert len(result.trades) == 1
    (trade,) = result.trades
    assert trade.side == "buy"
    assert trade.ts == T3  # 第 4 根(T3)金叉成立并在当根成交
    assert trade.qty == Decimal("90.90909090")
    assert trade.price == Decimal("110")


def test_death_cross_sells_entire_position() -> None:
    """死叉当根清仓:卖出数量等于持仓数量,成交价 = 当根收盘。"""
    result = _run(["100", "100", "100", "110", "120", "90"], short=2, long=3)
    assert [t.side for t in result.trades] == ["buy", "sell"]
    sell = result.trades[1]
    assert sell.ts == T5
    assert sell.qty == result.trades[0].qty  # 清仓:卖掉全部持仓
    assert sell.price == Decimal("90")
    # 已实现盈亏 = (卖价 − 入场均价) × 数量;入场均价即金叉那根的买价 110。
    entry = result.trades[0].price
    assert sell.realized_pnl == (Decimal("90") - entry) * sell.qty
