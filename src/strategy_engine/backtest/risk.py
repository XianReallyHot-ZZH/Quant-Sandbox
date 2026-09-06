"""五条内置风控规则 + 命中即短路的 RiskManager(研报 §3.5 关键抽象表)。

对照参照物 ``src/risk/manager.py`` 同构复现:五条规则的 ``rule_id``
逐字相同——它们是运行时契约,课 06 的回测后风险 findings 层要按
rule_id 与这里的运行时拦截去重(研报 §3.6 两套风控 ID 重叠的坑)。
与参照物的两处刻意差异:

1. **拒单理由是中文**(ADR-0005):参照物是英文;我们的用户可见
   文案一律中文,且有测试断言锁死。
2. **阈值必须是 Decimal**:参照物把 float 阈值静默 ``Decimal(str(...))``
   转换;我们在构造点直接 ``TypeError`` 拒绝——与课 03 成本模型的
   bps 参数同一条「float 不入账本」边界。

单位约定(照抄参照物,包括它不自洽的地方):风控阈值是**分数**
(``0.05`` = 5%),而出场配置 ``exits.ExitConfig`` 用的是**百分比**
(``5`` = 5%)。对照参照物源码时注意区分,课 04 文档有展开。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from strategy_engine.backtest.candles import Candle
from strategy_engine.backtest.engine import StrategyContext
from strategy_engine.backtest.models import RiskCheck
from strategy_engine.backtest.portfolio import Portfolio
from strategy_engine.backtest.protocol import OrderIntent, OrderSide

# 全放行的单例:放行时不需要 rule_id/reason,frozen 值对象可以整个仓库
# 共享一个,少造对象也少一次构造开销。
_ALLOWED = RiskCheck(allowed=True)


def _require_decimal(name: str, value: Decimal) -> None:
    """构造点边界:阈值不是 Decimal 就炸(拒绝 float 入账本)。"""
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} 必须是 Decimal(拒绝 float 入账)")


class RiskRule(Protocol):
    """一条风控规则的形状:带 rule_id,能对一条意图给出放行/拦截。

    和 ``engine.RiskGate`` 一样是结构化鸭子类型——不用继承,签名对得上
    就算实现(测试里的 stub 正是这么用的)。
    """

    rule_id: str

    def check(
        self,
        intent: OrderIntent,
        *,
        ctx: StrategyContext,
        portfolio: Portfolio,
        candle: Candle,
    ) -> RiskCheck: ...


@dataclass(frozen=True, slots=True)
class MaxPositionRule:
    """单标的仓位上限:按成交后的名义价值(数量 × 当根收盘价)封顶。

    卖单天然减仓,一样过这道闸——但 ``abs(post_qty)`` 只会变小,实际
    不会被它拦下(空仓环境下不存在负持仓)。
    """

    max_notional_usd: Decimal
    rule_id: str = "MAX_POSITION_PCT"

    def __post_init__(self) -> None:
        _require_decimal("max_notional_usd", self.max_notional_usd)

    def check(
        self,
        intent: OrderIntent,
        *,
        ctx: StrategyContext,
        portfolio: Portfolio,
        candle: Candle,
    ) -> RiskCheck:
        position = portfolio.position(intent.symbol)
        # 成交后数量 = 现有 + 买入量,或 − 卖出量;名义价值按当根收盘价估。
        delta = intent.qty if intent.side == OrderSide.BUY else -intent.qty
        post_qty = position.qty + delta
        notional = abs(post_qty) * candle.close
        if notional > self.max_notional_usd:
            return RiskCheck(
                allowed=False,
                rule_id=self.rule_id,
                reason=(
                    f"成交后名义价值 {notional} 超过上限 {self.max_notional_usd}"
                    f"({position.qty} + {delta} = {post_qty} × {candle.close})"
                ),
            )
        return _ALLOWED


@dataclass(slots=True)
class MaxDrawdownRule:
    """权益回撤闸:权益从本规则见过的峰值跌超阈值后,拦下买入。

    有状态:``_peak`` 随每次 check 抬升(只升不降)。卖出永远放行——
    回撤里要允许离场,否则把逃生门也焊死了。rule_id 沿用参照物的
    ``MAX_DAILY_LOSS_PCT``(名字说的是「日损」,实现是峰值回撤——
    参照物如此,保持同构以便对照;课 06 按 id 去重也依赖它)。

    注意:峰值活在规则实例里,**不随 ``engine.run`` 重置**——同一个
    规则对象跨多次 run 会带着旧峰值走(参照物同病)。要确定性重跑,
    每次给引擎配新构造的规则集。
    """

    max_drawdown_pct: Decimal
    rule_id: str = "MAX_DAILY_LOSS_PCT"
    _peak: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        _require_decimal("max_drawdown_pct", self.max_drawdown_pct)

    def check(
        self,
        intent: OrderIntent,
        *,
        ctx: StrategyContext,
        portfolio: Portfolio,
        candle: Candle,
    ) -> RiskCheck:
        if intent.side == OrderSide.SELL:
            return _ALLOWED
        equity = portfolio.equity({intent.symbol: candle.close})
        if equity > self._peak:
            self._peak = equity
        if self._peak <= 0:
            return _ALLOWED
        drawdown = (self._peak - equity) / self._peak
        if drawdown >= self.max_drawdown_pct:
            # 阈值是分数,展示时 ×100 变成百分数;Decimal 全程精确。
            return RiskCheck(
                allowed=False,
                rule_id=self.rule_id,
                reason=(
                    f"权益 {equity} 较峰值 {self._peak} 回撤 {drawdown * Decimal('100')}%,"
                    f"达到上限 {self.max_drawdown_pct * Decimal('100')}%"
                ),
            )
        return _ALLOWED


@dataclass(frozen=True, slots=True)
class MaxSlippageRule:
    """当根振幅闸:(最高 − 最低) / 收盘 超过阈值说明这根 bar 流动性
    糟糕,任何新单都先拦下来。买卖同样受检(滑点不挑方向)。"""

    max_spread_pct: Decimal
    rule_id: str = "MAX_SLIPPAGE_PCT"

    def __post_init__(self) -> None:
        _require_decimal("max_spread_pct", self.max_spread_pct)

    def check(
        self,
        intent: OrderIntent,
        *,
        ctx: StrategyContext,
        portfolio: Portfolio,
        candle: Candle,
    ) -> RiskCheck:
        if candle.close <= 0:
            return _ALLOWED
        spread = (candle.high - candle.low) / candle.close
        if spread > self.max_spread_pct:
            return RiskCheck(
                allowed=False,
                rule_id=self.rule_id,
                reason=(
                    f"当根振幅 {spread * Decimal('100')}% 超过上限 "
                    f"{self.max_spread_pct * Decimal('100')}%"
                    f"(H={candle.high} L={candle.low} C={candle.close})"
                ),
            )
        return _ALLOWED


@dataclass(frozen=True, slots=True)
class AbnormalCandleRule:
    """异常 K 线闸:识别三种「这根 bar 不可信」的形态,任何新单先拦。

    1. 零成交量但 H≠L——没有成交却出了价格,行情损坏或停牌;
    2. H=L 却有成交量——价格纹丝不动却有量,疑似陈旧/伪造行情;
    3. 相邻收盘跳动超过阈值——价格突变,数据缺口或极端事件的信号。

    「上一根收盘价」的取法有个小机关:风控被问的时点有两处——提交时点
    ``ctx.history`` 已含当根,结算时点(挂单复查)还没含。这里取
    「history 里最后一根**不是当根** ``candle``」的收盘价,让两种时点
    都稳定指向同一根:真正的前一根。
    """

    max_price_jump_pct: Decimal
    rule_id: str = "ABNORMAL_ORDERBOOK"

    def __post_init__(self) -> None:
        _require_decimal("max_price_jump_pct", self.max_price_jump_pct)

    @staticmethod
    def _previous_close(ctx: StrategyContext, candle: Candle) -> Decimal | None:
        """倒着找第一根「不是当根对象」的 K 线的收盘价;没有前史返回 None。"""
        for seen in reversed(ctx.history):
            if seen is not candle:
                return seen.close
        return None

    def check(
        self,
        intent: OrderIntent,
        *,
        ctx: StrategyContext,
        portfolio: Portfolio,
        candle: Candle,
    ) -> RiskCheck:
        if candle.volume <= 0 and candle.high != candle.low:
            return RiskCheck(
                allowed=False,
                rule_id=self.rule_id,
                reason=f"零成交量但价格非平(H={candle.high} L={candle.low})——行情可能损坏或已停牌",
            )

        if candle.high == candle.low and candle.volume > 0:
            return RiskCheck(
                allowed=False,
                rule_id=self.rule_id,
                reason=f"当根零波动(H=L={candle.high})却有成交量 {candle.volume}——疑似陈旧行情",
            )

        prev_close = self._previous_close(ctx, candle)
        if prev_close is not None and prev_close > 0:
            jump = abs(candle.close - prev_close) / prev_close
            if jump > self.max_price_jump_pct:
                return RiskCheck(
                    allowed=False,
                    rule_id=self.rule_id,
                    reason=(
                        f"相邻收盘跳动 {jump * Decimal('100')}% 超过上限 "
                        f"{self.max_price_jump_pct * Decimal('100')}%({prev_close} → {candle.close})"
                    ),
                )
        return _ALLOWED


@dataclass(slots=True)
class KillSwitch:
    """紧急停止:一旦 ``trip`` 被调用,之后所有订单一律拦下,直到
    ``reset``。它本身不做判断——由外部(监控、人工、更高层的规则)在
    认为该停机时拉闸。出场单同样会被它拦(闸门不分进出)。"""

    rule_id: str = "EMERGENCY_HALT"
    tripped: bool = False
    tripped_reason: str = ""

    def trip(self, reason: str) -> None:
        """拉闸(只记第一次原因;重复 trip 不覆盖最初的理由)。"""
        if not self.tripped:
            self.tripped = True
            self.tripped_reason = reason

    def reset(self) -> None:
        """恢复:清掉闸态,允许后续订单重新过检。"""
        self.tripped = False
        self.tripped_reason = ""

    def check(
        self,
        intent: OrderIntent,
        *,
        ctx: StrategyContext,
        portfolio: Portfolio,
        candle: Candle,
    ) -> RiskCheck:
        if self.tripped:
            return RiskCheck(
                allowed=False,
                rule_id=self.rule_id,
                reason=f"紧急停止已触发:{self.tripped_reason}",
            )
        return _ALLOWED


class RiskManager:
    """把一列规则串成一道闸:逐条问,**第一条命中即短路**返回。

    满足 ``engine.RiskGate`` 协议(结构化匹配),所以直接挂到
    ``BacktestEngine.risk_manager`` 上用。
    """

    def __init__(self, rules: list[RiskRule] | None = None) -> None:
        self._rules: list[RiskRule] = list(rules) if rules else []

    def add_rule(self, rule: RiskRule) -> None:
        self._rules.append(rule)

    @property
    def rules(self) -> tuple[RiskRule, ...]:
        """当前规则序列(短路顺序就是列表顺序)。"""
        return tuple(self._rules)

    def check(
        self,
        intent: OrderIntent,
        *,
        ctx: StrategyContext,
        portfolio: Portfolio,
        candle: Candle,
    ) -> RiskCheck:
        for rule in self._rules:
            result = rule.check(intent, ctx=ctx, portfolio=portfolio, candle=candle)
            if not result.allowed:
                return result
        return _ALLOWED
