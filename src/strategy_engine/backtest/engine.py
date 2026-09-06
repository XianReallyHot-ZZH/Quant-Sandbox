"""事件驱动的 bar 循环(研报 §3.6,引擎 #1)。

每根 K 线的处理次序:先让**之前挂着的订单**对着本根的高低区间结算,
再把本根 K 线交给策略看(history 已包含当根),最后处理策略返回的
意图——市价单立刻按滑点价成交,限价/止损单各按自己的语义走。权益在
每根收盘时记一笔,所以 bar *t* 上决定的成交,最迟在 bar *t+1* 的结算
后状态里可见。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from strategy_engine.backtest.candles import Candle
from strategy_engine.backtest.exits import ExitConfig, ExitManager, SignalFn
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
    """策略在当前 bar 上被允许看到的一切。"""

    symbol: str
    timeframe: str
    portfolio: Portfolio
    # history 每根 append 一次;策略读 len(ctx.history) 就知道现在是第几根。
    history: list[Candle] = field(default_factory=list)

    def position(self, symbol: str | None = None) -> PortfolioPosition:
        # 不传 symbol 就看当前标的——给策略一个便捷入口,不必直接摸 portfolio。
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
        """数字一律经 ``str`` 转 Decimal——float 永远进不了账本。

        Decimal(0.1) 会把 float 的二进制误差原样带进来(它不等于
        Decimal("0.1"));先过一遍 str 再进 Decimal,策略随手传的 1.5
        也能被精确解读。
        """
        return OrderIntent(
            symbol=self.symbol,
            side=OrderSide(side),
            type=OrderType(type),
            qty=Decimal(str(qty)),
            price=Decimal(str(price)) if price is not None else None,
            stop_price=Decimal(str(stop_price)) if stop_price is not None else None,
            time_in_force=TimeInForce(time_in_force),
        )


# 策略函数的形状:吃 (上下文, 当前K线),吐一条订单意图或 None(不下单)。
# Callable[...] 是标准库里描述「可调用物签名」的类型标注。
StrategyFn = Callable[[StrategyContext, Candle], OrderIntent | None]


class RiskGate(Protocol):
    """成交前的风控闸门:引擎接受任何意图之前先问它;课 04(#5)的
    ``risk.RiskManager`` 与五条内置规则就是标准实现。Protocol = 结构化
    鸭子类型——不用继承,只要 check 方法签名对得上,任何对象都能当
    闸门用(测试里的 stub 正是这么做的)。"""

    def check(
        self, intent: OrderIntent, *, ctx: StrategyContext, portfolio: Portfolio, candle: Candle
    ) -> "RiskCheck": ...


@dataclass(slots=True)
class _PendingOrder:
    """一条挂在簿上的订单:意图 + 提交时间。"""

    intent: OrderIntent
    submitted_ts: datetime


@dataclass
class BacktestEngine:
    """事件引擎本体:三个成本/风控件都是可替换的缝,默认零费零滑点无风控。"""

    strategy_fn: StrategyFn
    initial_capital: Decimal = Decimal("10000")
    fee_model: FeeModel = field(default_factory=ZeroFee)
    slippage_model: SlippageModel = field(default_factory=ZeroSlippage)
    risk_manager: RiskGate | None = None  # 标准实现:risk.RiskManager(课 04)
    # 出场策略(课 04):给了配置,引擎每根替策略盯持仓——条件命中就
    # 市价平掉全部仓位,成交带出场原因。signal_fn 给「信号反转」供分。
    exit_config: ExitConfig | None = None
    signal_fn: SignalFn | None = None
    # init=False:这几个字段不出现在构造参数里,由引擎自己维护;名字前
    # 的下划线表示「内部状态,外部只读快照」。
    _pending: list[_PendingOrder] = field(default_factory=list, init=False)
    _risk_rejections: list[RiskRejection] = field(default_factory=list, init=False)
    _fill_rejections: list[FillRejection] = field(default_factory=list, init=False)
    _exit_manager: ExitManager | None = field(default=None, init=False)
    _bar_idx: int = field(default=-1, init=False)

    def pending_orders_snapshot(self) -> list[OrderIntent]:
        """仍在挂着的意图——最后一根结算后的挂单簿快照。"""
        return [entry.intent for entry in self._pending]

    def run(self, candles: list[Candle], symbol: str, timeframe: str) -> BacktestResult:
        """跑一遍回测:逐根「结算挂单 → 出场检查 → 给策略看 → 提交意图 → 记权益」。"""
        if not candles:
            raise ValueError("K 线序列不能为空")

        portfolio = Portfolio(initial_cash=self.initial_capital)
        ctx = StrategyContext(symbol=symbol, timeframe=timeframe, portfolio=portfolio)
        trades: list[BacktestTrade] = []
        equity_curve: list[tuple[datetime, Decimal]] = []
        # run 开头重置运行期状态:同一实例可以重复 run,不跨运行串味
        # (出场跟踪也一并重建,峰值/入场 bar 不带到下一次)。
        self._pending = []
        self._risk_rejections = []
        self._fill_rejections = []
        self._exit_manager = ExitManager(self.exit_config, self.signal_fn) if self.exit_config else None

        for bar_idx, candle in enumerate(candles):
            # bar_idx 记在引擎上,成交回话(note_fill)要用它记入场 bar。
            self._bar_idx = bar_idx
            # 次序即语义:先结算上一根留下的挂单,策略才看到「含当根」的
            # history——当根提交的限价单最早也要到下一根才可能成交。
            self._settle_pending(candle, portfolio, trades, ctx)
            ctx.history.append(candle)
            # 出场检查放在策略之前、history 追加之后:信号函数与策略看到
            # 同一份(含当根)的 history;当根新开的仓最迟次根才被检查。
            if self._exit_manager is not None:
                reason = self._exit_manager.check(candle, bar_idx, ctx)
                if reason is not None:
                    self._close_position_for_exit(reason, candle, portfolio, trades, ctx)
            intent = self.strategy_fn(ctx, candle)
            if intent is not None:
                self._submit(intent, candle, portfolio, trades, ctx)
            # 权益 = 现金 + 持仓按当根收盘价重估;每根记一笔,连成权益曲线。
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
        """问风控闸门;不放行就把拒单记进 _risk_rejections 并返回 False。"""
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
        exit_reason: str = "",
    ) -> None:
        """策略刚返回的意图从这里进入引擎:先验形、再过风控、再按类型分发。

        ``exit_reason`` 非空表示这是引擎自己发起的平仓单(策略不知道
        出场条件命中了);只有市价路径会用它,成交后随 BacktestTrade 落
        在结果缝上。"""
        # 验形:限价单必须有限价,止损类必须有触发价;缺了就显式拒单
        # (不许无声消失,ADR-0006)。
        if intent.type == OrderType.LIMIT and intent.price is None:
            self._record_fill_rejection(intent, candle, "限价单缺少价格")
            return
        if intent.type in {OrderType.STOP, OrderType.STOP_LIMIT} and intent.stop_price is None:
            self._record_fill_rejection(intent, candle, "止损单缺少触发价")
            return

        if not self._risk_allows(intent, candle, ctx, portfolio):
            return

        if intent.type == OrderType.MARKET:
            # 市价单不等:立刻按滑点模型的价成交。
            self._fill_at_price(
                intent,
                candle,
                self.slippage_model.fill_price(intent, candle),
                portfolio,
                trades,
                exit_reason=exit_reason,
            )
            return

        if intent.type == OrderType.LIMIT and intent.time_in_force in {
            TimeInForce.IOC,
            TimeInForce.FOK,
        }:
            # 立即成交否则取消:提交当根的波动范围能触及就成交,否则丢弃
            # ——本引擎的成交是原子的(整单一次全成),所以 IOC 与 FOK
            # 在这里行为一致。
            if intent.price is not None and self._limit_crossable(intent, candle):
                self._fill_at_price(intent, candle, intent.price, portfolio, trades)
            return

        # 其余(普通 GTC 限价、止损、止损限价)入簿,等后面的 bar 结算。
        self._pending.append(_PendingOrder(intent=intent, submitted_ts=candle.ts))

    def _settle_pending(
        self,
        candle: Candle,
        portfolio: Portfolio,
        trades: list[BacktestTrade],
        ctx: StrategyContext,
    ) -> None:
        """把在簿订单逐条对着本根区间试成交;没成交过的留在簿上。"""
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
        """试着让一条在簿订单在本根成交;返回 True 表示它离开挂单簿。"""
        intent = entry.intent

        if intent.type == OrderType.LIMIT:
            # 限价:本根区间触及限价才成交,成交价就是限价本身。
            if not self._limit_crossable(intent, candle):
                return False
            # 触发时点再过一次风控:挂单风控在成交时点生效,而非提交时
            # 点一次性放行。
            if not self._risk_allows(intent, candle, ctx, portfolio):
                return True
            self._fill_at_price(intent, candle, intent.price, portfolio, trades)
            return True

        if intent.type in {OrderType.STOP, OrderType.STOP_LIMIT}:
            # 参照物引擎把 stop_limit 当 stop 处理(限价腿不建模)——刻意
            # 保持同构,并有测试冻结这一行为。
            if not self._stop_triggered(intent, candle):
                return False
            if not self._risk_allows(intent, candle, ctx, portfolio):
                return True
            # 止损触发后按市价逻辑走:滑点模型的价(默认即当根收盘价)。
            self._fill_at_price(
                intent, candle, self.slippage_model.fill_price(intent, candle), portfolio, trades
            )
            return True

        # 不认识的类型(理论上到不了这里)直接出簿,不挂死在簿上。
        return True

    @staticmethod
    def _limit_crossable(intent: OrderIntent, candle: Candle) -> bool:
        """限价是否被本根触及:买单看最低价 ≤ 限价;卖单看最高价 ≥ 限价。"""
        if intent.price is None:
            return False
        if intent.side == OrderSide.BUY:
            return bool(candle.low <= intent.price)
        return bool(candle.high >= intent.price)

    @staticmethod
    def _stop_triggered(intent: OrderIntent, candle: Candle) -> bool:
        """触发价是否被本根穿越:买止损看最高价上穿;卖止损看最低价下穿。"""
        if intent.stop_price is None:
            return False
        if intent.side == OrderSide.BUY:
            return bool(candle.high >= intent.stop_price)
        return bool(candle.low <= intent.stop_price)

    def _close_position_for_exit(
        self,
        reason: str,
        candle: Candle,
        portfolio: Portfolio,
        trades: list[BacktestTrade],
        ctx: StrategyContext,
    ) -> None:
        """出场条件命中:以市价单平掉当前全部持仓,原因随成交入结果。

        平仓单与策略的单走同一条路——同样过风控闸门(紧急停止连出场
        也拦,这正是它的语义);被拦则仓位保留,下一根条件仍在会重试。
        """
        qty = portfolio.position(ctx.symbol).qty
        if qty <= 0:
            return
        intent = OrderIntent(
            symbol=ctx.symbol,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            qty=qty,
        )
        self._submit(intent, candle, portfolio, trades, ctx, exit_reason=reason)

    def _record_fill_rejection(self, intent: OrderIntent, candle: Candle, reason: str) -> None:
        """把一次记账/验形拒单记进结果(中文理由,ADR-0005/0006)。"""
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
        exit_reason: str = "",
    ) -> None:
        """按给定成交价过账:算费、改账、记一笔 BacktestTrade。"""
        fee = self.fee_model.calc(intent, fill_price)
        try:
            if intent.side == OrderSide.BUY:
                portfolio.apply_buy(intent.symbol, intent.qty, fill_price, fee)
                realized = Decimal("0")  # 买入不实现盈亏(还没卖)
            else:
                realized = portfolio.apply_sell(intent.symbol, intent.qty, fill_price, fee)
        except ValueError as error:
            # 参照物引擎在这里静默吞掉异常;我们把拒单显式记进结果
            # (ADR-0006 不静默跳过)。
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
                exit_reason=exit_reason,
            )
        )
        # 成交回话给出场跟踪:开仓/加仓/清仓,它据此维护时间维度状态。
        if self._exit_manager is not None:
            position = portfolio.position(intent.symbol)
            self._exit_manager.note_fill(
                intent.side.value,
                fill_price,
                position.qty,
                position.avg_entry_price,
                self._bar_idx,
            )
