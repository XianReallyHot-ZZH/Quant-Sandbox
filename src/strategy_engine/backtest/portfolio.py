"""组合记账:现金、持仓、已实现盈亏、权益。

全程 Decimal——参照物引擎(研报 §3.6)的现金/持仓/权益都放在 Decimal
里,我们同样;float 只允许出现在以后课程的指标层。用户可见的报错文案
是中文(ADR-0005)且有测试断言锁死:改措辞 = 改契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class Position:
    """一个标的的持仓:数量、平均入场价、累计已实现盈亏。"""

    symbol: str
    qty: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    def mark_to_market(self, last_price: Decimal) -> Decimal:
        """按 ``last_price`` 对平均入场价算未实现盈亏(浮动盈亏)。"""
        if self.qty == 0:
            return Decimal("0")
        return (last_price - self.avg_entry_price) * self.qty


@dataclass
class Portfolio:
    """现金 + 多标的持仓的账本;一切买/卖都从这里过账。"""

    initial_cash: Decimal
    # init=False:cash 不出现在构造参数里,由 __post_init__ 从 initial_cash 复制。
    cash: Decimal = field(init=False)
    # default_factory=dict:每个实例各拿一份新字典——可变默认值必须走
    # 工厂,直接写 =dict 会让所有实例共享同一个字典(经典 Python 陷阱)。
    positions: dict[str, Position] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 边界即闸门:float 本金在构造点就被拒,不让二进制噪声迟到爆在
        # 第一笔算术上。
        if not isinstance(self.initial_cash, Decimal):
            raise TypeError("initial_cash 必须是 Decimal(拒绝 float 入账)")
        self.cash = self.initial_cash

    def apply_buy(self, symbol: str, qty: Decimal, price: Decimal, fee: Decimal) -> None:
        """买入过账:扣现金(价 × 量 + 费),并加权更新平均入场价。"""
        if qty <= 0 or price <= 0:
            raise ValueError("买入数量与价格必须为正")
        cost = qty * price + fee
        if cost > self.cash:
            raise ValueError(f"现金不足:需要 {cost},持有 {self.cash}")
        # setdefault:持仓不存在就先造一个空仓,再在它身上累加。
        pos = self.positions.setdefault(symbol, Position(symbol=symbol))
        new_qty = pos.qty + qty
        # 平均入场价 = 加权平均:旧均价 × 旧量 + 新价 × 新量,再除以新总量。
        pos.avg_entry_price = (
            (pos.avg_entry_price * pos.qty + price * qty) / new_qty if new_qty > 0 else Decimal("0")
        )
        pos.qty = new_qty
        self.cash -= cost

    def apply_sell(self, symbol: str, qty: Decimal, price: Decimal, fee: Decimal) -> Decimal:
        """卖出过账:返回本笔的已实现盈亏;仓位清零时均价一并归零。"""
        if qty <= 0 or price <= 0:
            raise ValueError("卖出数量与价格必须为正")
        pos = self.positions.get(symbol)
        # 没持仓或卖超都属于持仓不足,统一中文报错(文案有测试锁)。
        if pos is None or pos.qty < qty:
            held = pos.qty if pos is not None else Decimal("0")
            raise ValueError(f"持仓不足:需卖出 {qty} {symbol},持有 {held}")
        proceeds = qty * price - fee
        # 已实现盈亏 = (卖价 - 平均入场价) × 数量 - 费用。
        realized = (price - pos.avg_entry_price) * qty - fee
        pos.qty -= qty
        pos.realized_pnl += realized
        if pos.qty == 0:
            pos.avg_entry_price = Decimal("0")
        self.cash += proceeds
        return realized

    def position(self, symbol: str) -> Position:
        """取 ``symbol`` 的持仓;从未交易过就返回一个全新的空仓。"""
        return self.positions.get(symbol, Position(symbol=symbol))

    def equity(self, last_prices: dict[str, Decimal]) -> Decimal:
        """权益 = 现金 + 持仓市值;``last_prices`` 没给价的按成本价(均价)计。"""
        # sum(..., start=Decimal("0")):从 Decimal 的零起加,保证结果是 Decimal。
        position_value = sum(
            (pos.qty * last_prices.get(symbol, pos.avg_entry_price) for symbol, pos in self.positions.items()),
            start=Decimal("0"),
        )
        return self.cash + position_value
