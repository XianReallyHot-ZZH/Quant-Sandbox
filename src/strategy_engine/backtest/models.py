"""成交成本模型与引擎结果值对象。

引擎结果是本票声明的缝(缝 2):策略提交的订单意图以 ``BacktestTrade``
行 + 逐 bar 权益轨迹的形式回来,全程 Decimal——float 只允许出现在以后
课程的指标层,绝不允许进入这里携带的账目。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from strategy_engine.backtest.candles import Candle
from strategy_engine.backtest.protocol import TAKER_ORDER_TYPES, OrderIntent, OrderSide


class FeeModel(Protocol):
    """手续费模型接口:一笔成交该收多少费。Protocol = 结构化鸭子类型,
    不需要继承——方法签名对得上的任何类都算实现。"""

    def calc(self, intent: OrderIntent, fill_price: Decimal) -> Decimal: ...


class SlippageModel(Protocol):
    """滑点模型接口:这笔单实际按什么价成交。"""

    def fill_price(self, intent: OrderIntent, candle: Candle) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class ZeroFee:
    """教学默认:零成本(研报 §3.6 引擎默认)。"""

    def calc(self, intent: OrderIntent, fill_price: Decimal) -> Decimal:
        return Decimal("0")


@dataclass(frozen=True, slots=True)
class ZeroSlippage:
    """零滑点:市价/止损单按当根收盘价成交。"""

    def fill_price(self, intent: OrderIntent, candle: Candle) -> Decimal:
        return candle.close


@dataclass(frozen=True, slots=True)
class ConstantBpsFee:
    """最小成本模型:限价成交收 maker 基点,市价/止损收 taker 基点。

    bps 参数必须是 Decimal——传 float 等于把二进制噪声直接灌进账本
    (``Decimal(0.1) != Decimal("0.1")``),所以在构造点就拦下。
    """

    maker_bps: Decimal = Decimal("10")
    taker_bps: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        # __post_init__:dataclass 生成的 __init__ 跑完后自动调用的钩子,
        # 最适合做「构造即校验」。
        for name in ("maker_bps", "taker_bps"):
            if not isinstance(getattr(self, name), Decimal):
                raise TypeError(f"{name} 必须是 Decimal(拒绝 float 入账)")

    def calc(self, intent: OrderIntent, fill_price: Decimal) -> Decimal:
        # 吃流动性的单按 taker,挂出的限价按 maker;TAKER_ORDER_TYPES
        # 是唯一事实源,这里只查表、不重写。
        bps = self.taker_bps if intent.type in TAKER_ORDER_TYPES else self.maker_bps
        # 费 = 名义金额 × 基点 / 10000(1 bps = 万分之一)。
        return intent.qty * fill_price * bps / Decimal("10_000")


@dataclass(frozen=True, slots=True)
class ConstantBpsSlippage:
    """恒定不利滑点(基点):以限价或收盘价为基准,朝不利于自己的方向偏。"""

    bps: Decimal = Decimal("5")

    def __post_init__(self) -> None:
        if not isinstance(self.bps, Decimal):
            raise TypeError("bps 必须是 Decimal(拒绝 float 入账)")

    def fill_price(self, intent: OrderIntent, candle: Candle) -> Decimal:
        ref = intent.price if intent.price is not None else candle.close
        shift = self.bps / Decimal("10_000")
        # 买入往上偏(买贵),卖出往下偏(卖便宜)——滑点永远在伤害你。
        if intent.side == OrderSide.BUY:
            return ref * (Decimal("1") + shift)
        return ref * (Decimal("1") - shift)


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    """一笔已成交的记录(落在结果缝上)。"""

    ts: datetime
    symbol: str
    side: str
    qty: Decimal
    price: Decimal
    fee: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True, slots=True)
class RiskCheck:
    """风控闸门被问到某条意图时给出的回答:放不放行、命中的规则号、理由。"""

    allowed: bool
    rule_id: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RiskRejection:
    """一次成交前的风控拦截(规则集在下一课 #5 落地)。"""

    ts: datetime
    symbol: str
    side: str
    rule_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class FillRejection:
    """记账层拒绝一笔成交——显式记录,绝不静默丢弃(ADR-0006)。"""

    ts: datetime
    symbol: str
    side: str
    reason: str


@dataclass
class BacktestResult:
    """一次 run 的完整结果:成交列表、逐 bar 权益曲线、两类拒单。

    字段用 default_factory=list:每个实例各拿一份新列表——可变默认值
    必须走工厂函数,直接写 =list 会让所有实例共享同一个列表。
    """

    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    risk_rejections: list[RiskRejection] = field(default_factory=list)
    fill_rejections: list[FillRejection] = field(default_factory=list)


def render_result(result: BacktestResult) -> str:
    """一次运行的稳定文本渲染——AC1「逐字节一致重跑」比对的对象。

    这里只允许出现有序列表和值对象,绝不掺墙钟时间或无序遍历,
    所以相等的运行必然渲染出相等的字节。
    """
    lines = [f"trades {len(result.trades)}"]
    lines.extend(
        (
            f"trade {t.ts.isoformat()} {t.symbol} {t.side} "
            f"qty={t.qty} price={t.price} fee={t.fee} realized={t.realized_pnl}"
        )
        for t in result.trades
    )
    lines.append(f"equity_curve {len(result.equity_curve)}")
    lines.extend((f"equity {ts.isoformat()} {equity}" for ts, equity in result.equity_curve))
    lines.append(f"fill_rejections {len(result.fill_rejections)}")
    lines.extend(
        (f"fill_rejection {r.ts.isoformat()} {r.symbol} {r.side} {r.reason}")
        for r in result.fill_rejections
    )
    lines.append(f"risk_rejections {len(result.risk_rejections)}")
    lines.extend(
        (f"risk_rejection {r.ts.isoformat()} {r.symbol} {r.side} {r.rule_id} {r.reason}")
        for r in result.risk_rejections
    )
    return "\n".join(lines) + "\n"
