"""组合记账契约:全部手算样例(票 #4 AC3)。

记账层端到端 Decimal——现金、平均入场价、已实现盈亏、权益都不是
float。下面所有期望数字都是手算出来的;用户可见报错文案按 ADR-0005
用中文。
"""

from decimal import Decimal

import pytest

from strategy_engine.backtest.portfolio import Portfolio

SYMBOL = "QUANT-DEMO/USDT"


def test_buy_updates_cash_and_average_entry() -> None:
    """手算:10000 现金,买 5@100 无费 → 现金 9500、均价 100;再买 5@104 费 2
    → 现金 9500-520-2 = 8978、持仓 10、均价 (100*5+104*5)/10 = 102。"""
    portfolio = Portfolio(initial_cash=Decimal("10000"))
    portfolio.apply_buy(SYMBOL, Decimal("5"), Decimal("100"), Decimal("0"))
    portfolio.apply_buy(SYMBOL, Decimal("5"), Decimal("104"), Decimal("2"))
    position = portfolio.position(SYMBOL)
    assert portfolio.cash == Decimal("9500") - Decimal("520") - Decimal("2")
    assert portfolio.cash == Decimal("8978")
    assert position.qty == Decimal("10")
    assert position.avg_entry_price == Decimal("102")


def test_full_sell_realizes_pnl_and_flattens_position() -> None:
    """手算:接上例持仓 10@均价102,卖 10@110 费 1.10 → 已实现 (110-102)*10-1.10
    = 78.90,现金 8978+1098.90 = 10076.90,持仓归零、均价归零。"""
    portfolio = Portfolio(initial_cash=Decimal("10000"))
    portfolio.apply_buy(SYMBOL, Decimal("5"), Decimal("100"), Decimal("0"))
    portfolio.apply_buy(SYMBOL, Decimal("5"), Decimal("104"), Decimal("2"))
    realized = portfolio.apply_sell(SYMBOL, Decimal("10"), Decimal("110"), Decimal("1.10"))
    position = portfolio.position(SYMBOL)
    assert realized == Decimal("78.90")
    assert position.realized_pnl == Decimal("78.90")
    assert portfolio.cash == Decimal("10076.90")
    assert position.qty == Decimal("0")
    assert position.avg_entry_price == Decimal("0")


def test_partial_sell_keeps_average_entry() -> None:
    """手算:买 10@100,卖 4@90 无费 → 已实现 (90-100)*4 = -40,余 6 股均价仍 100。"""
    portfolio = Portfolio(initial_cash=Decimal("10000"))
    portfolio.apply_buy(SYMBOL, Decimal("10"), Decimal("100"), Decimal("0"))
    realized = portfolio.apply_sell(SYMBOL, Decimal("4"), Decimal("90"), Decimal("0"))
    position = portfolio.position(SYMBOL)
    assert realized == Decimal("-40")
    assert position.qty == Decimal("6")
    assert position.avg_entry_price == Decimal("100")


def test_equity_marks_positions_to_last_price() -> None:
    """手算:买 5@100 后,现价 96 → 权益 9500+480 = 9980;无价时按成本价
    (均价)计 → 10000;mark_to_market = (96-100)*5 = -20。"""
    portfolio = Portfolio(initial_cash=Decimal("10000"))
    portfolio.apply_buy(SYMBOL, Decimal("5"), Decimal("100"), Decimal("0"))
    assert portfolio.equity({SYMBOL: Decimal("96")}) == Decimal("9980")
    assert portfolio.equity({}) == Decimal("10000")
    assert portfolio.position(SYMBOL).mark_to_market(Decimal("96")) == Decimal("-20")


def test_accounting_values_are_decimal_not_float() -> None:
    """AC3:记账层无 float 泄漏 — 现金/均价/已实现/权益全部是 Decimal 实例。"""
    portfolio = Portfolio(initial_cash=Decimal("10000"))
    portfolio.apply_buy(SYMBOL, Decimal("3"), Decimal("100"), Decimal("0.30"))
    realized = portfolio.apply_sell(SYMBOL, Decimal("3"), Decimal("101"), Decimal("0.30"))
    for value in (portfolio.cash, realized, portfolio.equity({SYMBOL: Decimal("101")})):
        assert isinstance(value, Decimal)


def test_buy_rejects_insufficient_cash_with_chinese_copy() -> None:
    """现金不足 → ValueError,中文文案(ADR-0005),报出需求数与持有数。"""
    portfolio = Portfolio(initial_cash=Decimal("100"))
    with pytest.raises(ValueError, match="现金不足"):
        portfolio.apply_buy(SYMBOL, Decimal("2"), Decimal("60"), Decimal("0"))


def test_sell_rejects_insufficient_position_with_chinese_copy() -> None:
    """持仓不足(无持仓 / 卖超)→ ValueError,中文文案。"""
    empty = Portfolio(initial_cash=Decimal("10000"))
    with pytest.raises(ValueError, match="持仓不足"):
        empty.apply_sell(SYMBOL, Decimal("1"), Decimal("100"), Decimal("0"))
    empty.apply_buy(SYMBOL, Decimal("2"), Decimal("50"), Decimal("0"))
    with pytest.raises(ValueError, match="持仓不足"):
        empty.apply_sell(SYMBOL, Decimal("3"), Decimal("100"), Decimal("0"))


def test_non_positive_qty_or_price_is_rejected() -> None:
    """数量或价格非正 → ValueError,中文文案。"""
    portfolio = Portfolio(initial_cash=Decimal("10000"))
    with pytest.raises(ValueError, match="必须为正"):
        portfolio.apply_buy(SYMBOL, Decimal("0"), Decimal("100"), Decimal("0"))
    with pytest.raises(ValueError, match="必须为正"):
        portfolio.apply_buy(SYMBOL, Decimal("1"), Decimal("0"), Decimal("0"))


def test_float_initial_cash_is_rejected_at_the_boundary() -> None:
    """AC3 入口面:float 本金在构造点即 TypeError(中文文案),不许迟到爆在
    第一笔算术上——记账层的无 float 保证从边界开始。"""
    with pytest.raises(TypeError, match="initial_cash 必须是 Decimal"):
        Portfolio(initial_cash=10000.0)
