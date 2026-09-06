"""引擎逐根循环的 bar(K 线)。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Candle:
    """一根 OHLCV K 线(开、高、低、收、量)。

    价格一律 Decimal(ADR-0002:数值全手写、零第三方依赖——不用 numpy
    也能精确算账;Decimal 的十进制运算没有 float 的二进制噪声)。
    frozen=True → 值对象,生成后不许改字段;slots=True → 不给每个实例
    建 __dict__,省内存且防手滑加新字段。
    """

    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
