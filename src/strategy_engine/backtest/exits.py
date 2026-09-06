"""出场判定:止损/止盈/移动止损/超时平仓/信号反转(研报 §3.5 关键抽象表)。

对照参照物 ``backtest/rolling/risk/position.py`` 的 ``check_exit`` 同构
复现。参照物把出场逻辑放在滚动引擎里(float、按单笔 Trade 记账);本
模块把它适配到事件引擎的 Decimal 世界——判定纯函数 ``check_exit`` +
引擎侧接线的 ``ExitManager``(本模块定义,``engine.py`` 的 bar 循环
每根来问一次)。

与参照物的三处刻意差异:

1. **全程 Decimal**:参照物是 float 的 ``(price-entry)/entry*100``;
   我们同样算百分比,但每一步都是 Decimal,无二进制噪声。
2. **不在此处扣费**:参照物的 net_pnl 里减了 commission/slippage;我们
   的成本已经由引擎的成本模型(费 + 滑点)在成交价上体现,再扣一次
   就是双重计费。这里只回答「该不该出场、为什么」。
3. **sig_score 可为 None**:参照物总有一个 float 信号分(阈值硬编码 0,
   多头在 score ≤ 0 就离场);事件引擎的策略未必给信号,None 表示
   「不给信号」→ 反转分支整体跳过,而不是把 0 当信号。

单位约定:出场阈值是**百分比**(``3`` = 3%),与风控阈值
(``risk.py``,分数制 ``0.03`` = 3%)不同——照抄参照物(它两处单位
本就不一致),对照源码时注意区分。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from strategy_engine.backtest.candles import Candle

if TYPE_CHECKING:
    # 只在类型检查时导入:运行期 engine 会导入本模块,若本模块又运行期
    # 导入 engine 就成了循环依赖。``from __future__ import annotations``
    # 让下面的注解全部变成字符串,运行期不求值。
    from strategy_engine.backtest.engine import StrategyContext

# 信号函数的形状:吃 (上下文, 当前K线),吐一个信号分(正 = 看多,
# 非正 = 看平/看空)。给引擎的 exit 集成用;纯函数 check_exit 只收数。
# 注:类型别名在运行期求值,所以参数用字符串前向引用。
SignalFn = Callable[["StrategyContext", Candle], Decimal]

_HUNDRED = Decimal("100")
_ZERO = Decimal("0")


def _require_decimal(name: str, value: Decimal) -> None:
    """构造点边界:阈值不是 Decimal 就炸(拒绝 float 入账本)。"""
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} 必须是 Decimal(拒绝 float 入账)")


@dataclass(frozen=True, slots=True)
class ExitConfig:
    """出场参数(单位:百分比,``3`` = 3%)。

    「0 = 停用」只对**移动止损**和**超时平仓**成立(参照物用 0 当关
    扳);止损/止盈没有停用值——给 0 不是关掉,而是「浮亏/浮盈一到
    0% 就出场」的极端配置,慎用。

    默认值照抄参照物 ``BacktestConfig``:止损 3%、止盈 5%、移动止损与
    超时停用——教学上「最常被问到的默认组合」先给出厂值。
    """

    stop_loss_pct: Decimal = Decimal("3")
    take_profit_pct: Decimal = Decimal("5")
    trailing_stop_pct: Decimal = Decimal("0")  # 0 = 停用
    max_hold_bars: int = 0  # 0 = 停用

    def __post_init__(self) -> None:
        for name in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct"):
            _require_decimal(name, getattr(self, name))


@dataclass(slots=True)
class TrackedPosition:
    """一个被跟踪的多头仓位:入场价、入场 bar 序号、见过的最高价。

    事件引擎的 ``Portfolio.Position`` 管账(数量/均价/已实现),这里只
    补它没有的「时间维度」:第几根入场、峰值爬到哪了——超时与移动
    止损都靠这两个数。峰值只升不降(多头视角)。
    """

    entry_price: Decimal
    entry_idx: int
    peak_price: Decimal

    def ratchet_peak(self, price: Decimal) -> None:
        """峰值只升不降——这就是「移动」止损里那个跟着价格爬的锚。"""
        if price > self.peak_price:
            self.peak_price = price

    def unrealized_pct(self, price: Decimal) -> Decimal:
        """多头浮动盈亏(百分比):(现价 − 入场价) / 入场价 × 100。"""
        return (price - self.entry_price) / self.entry_price * _HUNDRED


@dataclass(frozen=True, slots=True)
class ExitCheck:
    """一次出场判定的回答:该不该出、为什么出。"""

    should_exit: bool
    reason: str = ""


def check_exit(
    position: TrackedPosition,
    price: Decimal,
    sig_score: Decimal | None,
    bar_idx: int,
    config: ExitConfig,
) -> ExitCheck:
    """按固定优先级检查全部出场条件(顺序 = 参照物,保命的先判):

    移动止损 → 止损 → 止盈 → 超时平仓 → 信号反转。

    事件引擎只做多(记账层不允许负持仓),所以没有参照物里的 SHORT
    分支——空头出场留给滚动引擎课(课 05)。
    """
    pnl = position.unrealized_pct(price)

    # --- 移动止损:从峰值回撤超过阈值就离场,锁住已有利润 ---
    if config.trailing_stop_pct > _ZERO and position.peak_price > _ZERO:
        trail_ref = position.peak_price * (_HUNDRED - config.trailing_stop_pct) / _HUNDRED
        if price <= trail_ref:
            return ExitCheck(True, "移动止损")

    # --- 固定止损:浮亏超过阈值,先保命 ---
    if pnl <= -config.stop_loss_pct:
        return ExitCheck(True, "止损")

    # --- 固定止盈:浮盈达到阈值,落袋为安 ---
    if pnl >= config.take_profit_pct:
        return ExitCheck(True, "止盈")

    # --- 超时平仓:持有满 max_hold_bars 根还没走出行情,认赔时间 ---
    bars_held = bar_idx - position.entry_idx
    if config.max_hold_bars > 0 and bars_held >= config.max_hold_bars:
        return ExitCheck(True, "超时平仓")

    # --- 信号反转:策略给了信号且已不偏多 → 离场(不给信号 = 跳过) ---
    if sig_score is not None and sig_score <= _ZERO:
        return ExitCheck(True, "信号反转")

    return ExitCheck(False)


class ExitManager:
    """引擎侧的出场集成:盯着成交开仓/清仓,逐根问一次 check_exit。

    职责切分(参照物把这段循环写在引擎里,我们抽成独立对象):
    ``Portfolio`` 管账,``TrackedPosition`` 记时间维度(入场 bar、峰值),
    ``check_exit`` 做纯判定,本类负责把三者接到引擎的 bar 循环上——
    每根先爬峰值再判定,与参照物 ``update_peak_price`` → ``check_exit``
    的调用顺序一致。
    """

    def __init__(self, config: ExitConfig, signal_fn: SignalFn | None = None) -> None:
        self.config = config
        self.signal_fn = signal_fn
        self._tracked: TrackedPosition | None = None

    @property
    def tracked(self) -> TrackedPosition | None:
        """当前跟踪中的仓位(没有开仓时为 None)——测试观察口。"""
        return self._tracked

    def note_fill(
        self,
        side: str,
        fill_price: Decimal,
        position_qty: Decimal,
        avg_entry_price: Decimal,
        bar_idx: int,
    ) -> None:
        """每笔成交后由引擎回话:仓位还剩多少、当前均价、第几根。

        - 买后仍有仓:开仓(首次)或重锚均价(金字塔加仓),峰值随成
          交价抬升;入场 bar 序号只在首次开仓时记——加仓不算「重新入场」。
        - 卖后仍有仓:部分减仓,跟踪不重置(入场时间与峰值保持)。
        - 仓位归零:清跟踪,下一次开仓从头再来。
        """
        if position_qty <= 0:
            self._tracked = None
            return
        if side == "sell":
            return
        if self._tracked is None:
            self._tracked = TrackedPosition(
                entry_price=avg_entry_price, entry_idx=bar_idx, peak_price=fill_price
            )
        else:
            self._tracked.entry_price = avg_entry_price
            self._tracked.ratchet_peak(fill_price)

    def check(self, candle: Candle, bar_idx: int, ctx: StrategyContext) -> str | None:
        """本根是否该出场:返回出场原因,或 None(继续持有)。

        入场当根直接跳过——参照物由循环顺序天然保证「出场从次根起」,
        事件引擎的结算成交可能与出场检查同根,这里显式判 bar_idx。
        """
        tracked = self._tracked
        if tracked is None or bar_idx == tracked.entry_idx:
            return None
        # 先爬峰值再判定(参照物同序):本根收盘新高先记下来,触发线随之抬高。
        tracked.ratchet_peak(candle.close)
        sig_score = self.signal_fn(ctx, candle) if self.signal_fn is not None else None
        decision = check_exit(tracked, candle.close, sig_score, bar_idx, self.config)
        return decision.reason if decision.should_exit else None
