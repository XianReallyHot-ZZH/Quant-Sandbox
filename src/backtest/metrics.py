"""M1 指标层:最大回撤 / Calmar / 权益曲线 Sharpe(票 #6,课 05)。

口径声明(ADR-0003:两套引擎的指标字段**不可共用命名**)——本模块只
服务事件引擎的**逐 bar 权益曲线**口径:

- **最大回撤**:权益从运行峰值跌到谷底的最大跌幅,返回分数(≥ 0,
  ``0.25`` = 25%);Decimal 全程,无二进制噪声。
- **Calmar** = 总收益% ÷ |最大回撤%|,同一回测期、不做年度化——
  「纯 Calmar」口径,对照参照物 ``runner.py`` 注释 "Adapted from
  web3-trading's pure Calmar metric";零回撤时按定义记 0。
- **Sharpe**:按**逐 bar 权益收益**算(mean/std × √periods_per_year),
  函数名与 payload 字段名都叫 ``equity_curve_sharpe``。参照物的两套
  引擎都叫 ``sharpe_ratio``、数值却不可直接比较(研报 §3.6 #2:一套按
  逐 bar 权益、一套按逐笔交易 PnL)——我们在**命名层**就把口径隔开,
  未来滚动引擎的 Sharpe 会叫别的名字。年度化系数默认 √252:教学样本
  是工作日日线(不含周末),取金融惯例 252 个交易日/年;参照物用 √365
  (加密市场「全年无休」惯例,但它的教学样本同样只有工作日)——这里
  刻意选 252 并声明。

Decimal 纪律(课 03 边界):回撤与 Calmar 在 Decimal 里算到底;Sharpe
要开方,属于**统计层**——float 自本模块起被允许(CLAUDE.md「统计层才
允许 float」),但绝不回流账本。
"""

from __future__ import annotations

import math
from decimal import Decimal


def maximum_drawdown(equities: list[Decimal]) -> Decimal:
    """权益序列的最大回撤(分数,≥ 0):逐点抬峰值,记最大跌幅。

    ``peak`` 只升不降;除法 ``(peak - value) / peak`` 走 Decimal 默认
    28 位精度——样本里任何除不尽都不会引入 float 噪声。空序列与纯上行
    序列都返回 0。
    """
    if not equities:
        return Decimal("0")
    peak = equities[0]
    worst = Decimal("0")
    for value in equities:
        if value > peak:
            peak = value
        # peak ≤ 0 时分母无意义(权益非正 = 已经全亏),跳过该点不比较。
        if peak > 0:
            drawdown = (peak - value) / peak
            if drawdown > worst:
                worst = drawdown
    return worst


def calmar_ratio(total_return_pct: Decimal, maximum_drawdown_pct: Decimal) -> Decimal:
    """纯 Calmar:总收益% ÷ |最大回撤%|(同一回测期,不年度化)。

    回撤为零时记 0 而不是除零——「没跌过」给不出有意义的收益/风险比,
    与参照物 ``runner.py:calmar_ratio`` 行为一致。
    """
    if maximum_drawdown_pct == 0:
        return Decimal("0")
    return total_return_pct / abs(maximum_drawdown_pct)


def equity_curve_sharpe(
    equity_values: list[float], *, periods_per_year: int = 252
) -> float:
    """按逐 bar 权益收益算的年度化 Sharpe(统计层,float)。

    步骤:逐期简单收益 → 样本方差(n−1 分母,与参照物 ``metrics.py``
    同款)→ std → mean/std × √periods_per_year。退化情形(权益不足两
    期、收益不足两期、零波动)一律 0.0——给不出有意义的比值,宁可
    诚实报 0,不造数。
    """
    if len(equity_values) < 2:
        return 0.0
    returns = [
        equity_values[index] / equity_values[index - 1] - 1
        for index in range(1, len(equity_values))
    ]
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((value - mean_r) ** 2 for value in returns) / (len(returns) - 1)
    std_r = math.sqrt(variance) if variance > 0 else 0.0
    if std_r == 0.0:
        return 0.0
    return (mean_r / std_r) * math.sqrt(periods_per_year)
