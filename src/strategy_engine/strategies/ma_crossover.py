"""双均线交叉策略:事件引擎的第一个策略(票 #6,研报 §4.2 路径 A)。

对照参照物 ``src/strategy_engine/strategies/ma_crossover.py`` 同构复现:
**多头 only** 的均线交叉——短简单均线(SMA)上穿长 SMA 视为看多,下穿
视为看空;看多且空仓时**全仓**买入(数量 = 现金 / 当根收盘),看空且
持仓时清仓卖出。均线用 ``ctx.history``(已含当根)的收盘价计算,窗口
含当根——与引擎「策略看到当根」的语义一致。

与参照物保持一致的两个教学取舍(也写进课 05 的假设说明行):

1. **全仓进出**:不做仓位 sizing。零成本下没问题;一旦挂上非零费率或
   滑点模型,「现金 / 收盘价」数量的买单会因费用把现金打穿而被记账层
   拒单(显式进入 ``fill_rejections``,不会被静默吞掉)——仓位 sizing
   与成本模型的配合是课 11 滚动引擎成本预设的课题。
2. **SMA 每根重算**:``closes[-window:]`` 切片求和,O(窗口长) 而非
   O(1);381 根教学样本毫秒级,可读性优先(参照物同款)。

与参照物的一处刻意修复:**买入数量按 8 位小数向下取整**(交易所数量
步长的惯例)。不取整时,``现金 / 收盘`` 的 28 位舍入乘回价格可能比
现金高出几个「尘埃」单位,全仓买单会被记账层以「现金不足」拒掉——
本课在真教学样本上真实踩到(差 2×10⁻²¹,见课 05 文档「踩过的坑」)。
参照物引擎吞掉这类异常、静默丢单;我们把拒单显式入结果,再在源头
取整,让「全仓」语义每根都成立。
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_DOWN, Decimal

from strategy_engine.backtest.candles import Candle
from strategy_engine.backtest.engine import StrategyContext
from strategy_engine.backtest.protocol import OrderIntent

# 策略函数的类型就是引擎的 StrategyFn;这里再起个别名让本模块自洽。
MaCrossoverFn = Callable[[StrategyContext, Candle], OrderIntent | None]

# 数量步长:8 位小数(多数交易所的精度惯例)。
QTY_STEP = Decimal("1E-8")


def sma(closes: list[Decimal], window: int) -> Decimal | None:
    """收盘价序列**末尾** window 根的简单均线;窗口未填满返回 None。

    这是全仓库 SMA 的唯一事实源:策略判定(本模块)与 runner 的曲线
    列(``backtest.runner.moving_average`` 切片后委托到这里)算的是同
    一个公式——曲线上的均线就是驱动决策的那条,不会出现「决策用一条、
    画图用另一条」的分叉。

    ``sum(..., start=Decimal("0"))``:从 Decimal 零起加,保证结果仍是
    Decimal;除以 ``Decimal(window)`` 而不是 int,让除法走 Decimal 精度。
    """
    if len(closes) < window:
        return None
    sample = closes[-window:]
    return sum(sample, start=Decimal("0")) / Decimal(window)


def make_ma_crossover_strategy(short: int, long: int) -> MaCrossoverFn:
    """工厂:按窗口参数造一个双均线策略函数。

    参数只在这里绑定一次,返回的 ``on_tick`` 闭包(记住了 short/long 的
    内层函数)直接喂给 ``BacktestEngine.strategy_fn``。
    """

    def on_tick(ctx: StrategyContext, candle: Candle) -> OrderIntent | None:
        # history 已含当根:策略站在「此刻」用截至当根的收盘价算均线。
        closes = [bar.close for bar in ctx.history]
        short_ma = sma(closes, short)
        long_ma = sma(closes, long)
        if short_ma is None or long_ma is None:
            # 任一窗口未填满:连「有没有金叉」都无从谈起,直接观望。
            return None

        position = ctx.position()
        should_hold = short_ma > long_ma

        if should_hold and position.qty == 0:
            # 金叉 + 空仓 → 全仓买入。两道护栏(现金为正、价格为正)照抄
            # 参照物:防呆除零,正常样本碰不到。
            if ctx.portfolio.cash <= 0 or candle.close <= 0:
                return None
            # 全仓数量 = 现金 / 收盘,再按步长**向下**取整(ROUND_DOWN =
            # 朝零方向,对正数即地板):宁可少买一粒尘埃,也不让乘回的
            # 成本越过现金被拒。见模块 docstring 的修复说明。
            qty = (ctx.portfolio.cash / candle.close).quantize(QTY_STEP, rounding=ROUND_DOWN)
            return ctx.order_intent("buy", qty, type="market")

        if not should_hold and position.qty > 0:
            # 死叉 + 持仓 → 清仓卖出。
            return ctx.order_intent("sell", position.qty, type="market")

        # 其余情形(看多已持仓 / 看空已空仓):维持现状,不下单。
        return None

    return on_tick
