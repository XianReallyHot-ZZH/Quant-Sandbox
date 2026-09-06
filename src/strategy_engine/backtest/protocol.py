"""订单意图值对象:策略面对引擎说话的词汇表。

``OrderIntent`` 是**意图**,不是成交:策略只描述想要什么(方向、类型、
Decimal 数量、可选的限价/触发价、有效期);至于能不能成交、何时成交、
以什么价成交,全由 bar 循环决定。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OrderSide(str, Enum):
    # str + Enum 混入:枚举成员本身就是字符串,f-string、比较、拼接都按
    # "buy"/"sell" 用,同时保留「只能是这几个值」的枚举约束。
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"  # 市价单:立刻按市价成交
    LIMIT = "limit"  # 限价单:指定价格,价格触及时按限价成交
    STOP = "stop"  # 止损单:价格穿越触发价后按市价逻辑成交
    STOP_LIMIT = "stop_limit"  # 止损限价单:本引擎按参照物语义视同 stop(限价腿不建模)


class TimeInForce(str, Enum):
    GTC = "GTC"  # 撤销前有效(Good-Till-Cancelled):一直挂在簿上等
    IOC = "IOC"  # 立即成交否则取消(Immediate-or-Cancel):当根不成交即丢弃
    FOK = "FOK"  # 全部立即成交否则取消(Fill-or-Kill):整单全成或全撤


# 「吃流动性」的单(market/stop/stop_limit)按 taker 费率;「挂出来的」
# 限价单按 maker 费率。这是费用分层的唯一事实源——不许在别处再写一份
# 字符串集合。frozenset = 不可变集合,防止运行中被改动。
TAKER_ORDER_TYPES = frozenset({OrderType.MARKET, OrderType.STOP, OrderType.STOP_LIMIT})


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """一条订单意图(frozen 值对象):构造之后不许改——要改就换新意图。"""

    symbol: str
    side: OrderSide
    type: OrderType
    qty: Decimal
    price: Decimal | None = None  # 限价单的限价;市价单没有
    stop_price: Decimal | None = None  # 止损/止损限价单的触发价
    time_in_force: TimeInForce = TimeInForce.GTC
