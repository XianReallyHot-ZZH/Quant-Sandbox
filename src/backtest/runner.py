"""M1 教学回测 runner:双均线 × 事件引擎 × 教学样本(票 #6,课 05)。

对照参照物 ``src/backtest/runner.py``(研报 §4.2 路径 A)同构复现:
读收盘价 CSV → 包成引擎 K 线 → 事件引擎跑双均线 → 组装 JSON-ready 的
payload(参数 / 样本 / 指标 / 成交 / 曲线 / 两类拒单 / 风控规则清单 /
中文假设说明行)。命令行演示入口:``PYTHONPATH=src python -m backtest.runner``。

与参照物的刻意差异:

1. **假设说明行从实际配置生成**(票 AC3):参照物的 assumptions 是写死
   的英文模板,换了成本模型也照说 "zero fee and zero slippage"——会
   撒谎;我们的每一行都由真正跑过的对象渲染,配置变文案变,测试锁死。
2. **指标口径在命名层隔离**(ADR-0003):Sharpe 叫 ``equity_curve_sharpe``
   (逐 bar 权益收益、√252 年度化——教学样本是工作日日线;参照物沿用
   加密惯例 √365),绝不再用一个裸的 ``sharpe_ratio`` 等未来滚动引擎
   来撞名(研报 §3.6 #2 的坑)。
3. **记账拒单也进 payload**:参照物的教学 payload 只有风控拒单;我们
   把 ``fill_rejections``(现金不足/持仓不足等)一并报出——反静默
   (ADR-0006),全仓策略挂上非零成本后发生了什么,一眼可见。
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TextIO

from backtest.metrics import calmar_ratio, equity_curve_sharpe, maximum_drawdown
from data.generator import DATASET_DIR, PRICES_NAME, SYMBOL
from strategy_engine.backtest.candles import Candle
from strategy_engine.backtest.engine import BacktestEngine, RiskGate
from strategy_engine.backtest.models import (
    ConstantBpsFee,
    ConstantBpsSlippage,
    FeeModel,
    SlippageModel,
    ZeroFee,
    ZeroSlippage,
)
from strategy_engine.backtest.risk import default_risk_manager
from strategy_engine.strategies.ma_crossover import make_ma_crossover_strategy, sma

INITIAL_CAPITAL = Decimal("10000")
TIMEFRAME = "1d"
# payload 的引擎身份标记:课 06 的研究报告与课 37 的对账桥都按它认口径。
ENGINE_ID = "event-driven"
# 收盘价合成 K 线的高低带(对照参照物 runner.py:high = close×1.002,
# low = close×0.998):只有收盘价来自样本,高低带是教学用合成振幅。
HIGH_BAND = Decimal("1.002")
LOW_BAND = Decimal("0.998")
_TWO_PLACES = Decimal("0.01")
_FOUR_PLACES = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class Price:
    """一行价格样本:(ISO 日期文本, Decimal 收盘价)。

    收盘价从 CSV 文本**直接**进 Decimal,不过 float——样本精度就是
    文本里那两位小数,任何二进制中转都是无缘无故的噪声。
    """

    date: str
    close: Decimal


def load_prices(path: Path) -> list[Price]:
    """读 ``date,close`` 两列 CSV;文件不存在时中文报错(ADR-0005)。"""
    if not path.is_file():
        raise FileNotFoundError(f"价格样本缺失:{path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            Price(row["date"], Decimal(row["close"]))
            for row in csv.DictReader(handle)
        ]


def load_teaching_sample() -> list[Price]:
    """读仓库提交的教学样本(课 02 铸造、manifest 锁 sha256)。

    路径常量从 ``data.generator`` 取——数据集的位置只有一个事实源,
    这里绝不手拼相对路径。
    """
    return load_prices(DATASET_DIR / PRICES_NAME)


def moving_average(closes: list[Decimal], window: int, index: int) -> Decimal | None:
    """截至 ``index``(含)的收盘价里,末尾 ``window`` 根的简单均线。

    委托到 ``ma_crossover.sma``(SMA 唯一事实源):曲线列画的均线与
    驱动决策的是同一条、同一精度,不会出现「决策一条、画图一条」。
    """
    return sma(closes[: index + 1], window)


def prices_to_candles(prices: list[Price]) -> list[Candle]:
    """收盘价序列 → 引擎 K 线:开=收、高=收×1.002、低=收×0.998、量=1。"""
    candles: list[Candle] = []
    for item in prices:
        candles.append(
            Candle(
                ts=datetime.fromisoformat(item.date),
                open=item.close,
                high=item.close * HIGH_BAND,
                low=item.close * LOW_BAND,
                close=item.close,
                volume=Decimal("1"),
            )
        )
    return candles


def _describe_fee(model: FeeModel) -> str:
    """把实际挂上的费率模型说成人话;不认识的自定义模型只报类型名,
    绝不冒充「零费率」——假设行必须与真实配置一致(票 AC3)。"""
    if isinstance(model, ZeroFee):
        return "零费率"
    if isinstance(model, ConstantBpsFee):
        return f"费率 maker {model.maker_bps}bps / taker {model.taker_bps}bps"
    return f"自定义费率模型({type(model).__name__})"


def _describe_slippage(model: SlippageModel) -> str:
    """同 ``_describe_fee``:滑点模型的人类可读描述。"""
    if isinstance(model, ZeroSlippage):
        return "零滑点"
    if isinstance(model, ConstantBpsSlippage):
        return f"滑点 {model.bps}bps(恒定不利方向)"
    return f"自定义滑点模型({type(model).__name__})"


def _assumption_lines(
    *,
    short: int,
    long: int,
    prices: list[Price],
    fee_model: FeeModel,
    slippage_model: SlippageModel,
    rules: tuple,
) -> list[str]:
    """人类可读的中文假设说明行(payload 的 ``assumptions`` 字段)。

    每一行都从**真正跑过的配置**渲染:窗口、成本模型实例、K 线合成带、
    样本区间、指标口径、风控规则清单(规则序列由调用方解析一次传入)。
    改任何一处配置,对应行随之变化,并被测试断言锁死(票 #6 AC3 /
    ADR-0005 文案即契约)。
    """
    rule_ids = "、".join(rule.rule_id for rule in rules) if rules else "未挂任何规则"
    return [
        "引擎:事件驱动回测引擎(Decimal 订单意图,市价单按当根收盘价成交,决策根与结算根分离)。",
        f"策略:双均线交叉,短窗 {short} / 长窗 {long}(简单移动平均,窗口含当根收盘)。",
        f"成本:{_describe_fee(fee_model)}、{_describe_slippage(slippage_model)}。",
        f"K 线:由收盘价合成(开=收,高=收×{HIGH_BAND},低=收×{LOW_BAND},量=1;仅收盘价来自样本)。",
        f"样本:{SYMBOL},{prices[0].date} → {prices[-1].date},{len(prices)} 根 {TIMEFRAME} 日线(固定种子合成,虚构资产)。",
        (
            "指标口径:Sharpe 按逐 bar 权益收益、√252 年度化(字段名 equity_curve_sharpe,"
            "与滚动引擎口径隔离);Calmar = 总收益% / |最大回撤%|;最大回撤以负百分比呈现。"
        ),
        f"运行时风控:{len(rules)} 条规则({rule_ids}),订单提交前逐条过闸、命中即拦。",
        "边界:历史样本表现不能预测未来收益;本回测仅用于离线教学研究,不构成投资建议,不进入实盘执行。",
    ]


def _quantize2(value: Decimal) -> float:
    """Decimal → 两位小数的 float:payload 数值(指标/权益)的统一出口。

    名字只说「量化到两位」,不说单位——它既量化百分比,也量化权益金额
    与 Calmar 比值。先在 Decimal 侧 ``quantize``(默认 ROUND_HALF_EVEN)
    再转 float:舍入发生在十进制世界,float 只是最后一步的表示;两边跑
    同一确定性计算,转出来的 float 逐位相同,冻结断言才站得住。
    """
    return float(value.quantize(_TWO_PLACES))


def run_teaching_backtest(
    prices: list[Price],
    *,
    short: int = 3,
    long: int = 7,
    fee_model: FeeModel | None = None,
    slippage_model: SlippageModel | None = None,
    risk_manager: RiskGate | None = None,
) -> dict:
    """跑一遍 M1 教学回测,返回 JSON-ready payload。

    参数缺省即教学默认:短窗 3 / 长窗 7、零费率零滑点、五规则风控闸。
    三个 ``None`` 在这里落成具体对象(而不是让引擎吃 None)——假设
    说明行要描述**实例**,配置先定型,文案才不撒谎。
    """
    if short < 2 or long <= short:
        raise ValueError(f"双均线窗口须满足 2 ≤ 短窗 < 长窗,收到 short={short}, long={long}")
    if len(prices) <= long:
        raise ValueError(f"样本行数不足:{len(prices)} 行,长窗 {long} 根均线需要更多样本")

    fee = fee_model if fee_model is not None else ZeroFee()
    slippage = slippage_model if slippage_model is not None else ZeroSlippage()
    gate = risk_manager if risk_manager is not None else default_risk_manager(
        initial_capital=INITIAL_CAPITAL
    )

    candles = prices_to_candles(prices)
    engine = BacktestEngine(
        strategy_fn=make_ma_crossover_strategy(short, long),
        initial_capital=INITIAL_CAPITAL,
        fee_model=fee,
        slippage_model=slippage,
        risk_manager=gate,
    )
    result = engine.run(candles, symbol=SYMBOL, timeframe=TIMEFRAME)
    return _assemble_payload(
        result,
        prices,
        candles,
        short=short,
        long=long,
        fee_model=fee,
        slippage_model=slippage,
        risk_manager=gate,
    )


def _assemble_payload(
    result,
    prices: list[Price],
    candles: list[Candle],
    *,
    short: int,
    long: int,
    fee_model: FeeModel,
    slippage_model: SlippageModel,
    risk_manager: RiskGate,
) -> dict:
    """把引擎结果 + 样本组装成 payload(dict 原生类型,可直接 json.dumps)。

    Decimal → float 的转换只发生在这里(payload 边界):指标先在
    Decimal 侧算到底、两位小数量化,曲线/成交行直接 ``float()``。
    """
    closes = [item.close for item in prices]
    equities = [equity for _, equity in result.equity_curve]
    date_by_ts = {candle.ts: item.date for candle, item in zip(candles, prices)}

    def date_of(ts: datetime) -> str:
        """成交/拒单时间 → 日期文本;对不上时退 ISO 日期(防御分支)。"""
        return date_by_ts.get(ts, ts.date().isoformat())

    # ---- 指标:全部先在 Decimal 里算完,出口才量化 ----
    final_equity = equities[-1]
    strategy_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * Decimal("100")
    buy_hold_return = (closes[-1] / closes[0] - Decimal("1")) * Decimal("100")
    excess = strategy_return - buy_hold_return
    # 回撤只算一次:Calmar 与 payload 共用同一个未量化值。
    drawdown_pct = -maximum_drawdown(equities) * Decimal("100")
    calmar = calmar_ratio(strategy_return, drawdown_pct)
    sharpe = equity_curve_sharpe([float(equity) for equity in equities])
    if drawdown_pct == 0:
        # 防 "-0.00":回撤为零时量化可能带出负号零,JSON 里会渲染成
        # "-0.00",观感误导;abs() 把负号零归一成 0.00。
        drawdown_pct = abs(drawdown_pct)
    drawdown_pct = drawdown_pct.quantize(_TWO_PLACES)

    metrics = {
        "strategy_return_pct": _quantize2(strategy_return),
        "buy_hold_return_pct": _quantize2(buy_hold_return),
        "excess_vs_buy_hold_pct": _quantize2(excess),
        "maximum_drawdown_pct": float(drawdown_pct),
        "calmar_ratio": _quantize2(calmar),
        "equity_curve_sharpe": round(sharpe, 2),
        "trade_count": len(result.trades),
        "final_equity": _quantize2(final_equity),
    }

    curve = []
    for index, item in enumerate(prices):
        short_ma = moving_average(closes, short, index)
        long_ma = moving_average(closes, long, index)
        curve.append(
            {
                "date": item.date,
                "close": float(item.close),
                "short_ma": (
                    float(short_ma.quantize(_FOUR_PLACES)) if short_ma is not None else None
                ),
                "long_ma": float(long_ma.quantize(_FOUR_PLACES)) if long_ma is not None else None,
                "equity": _quantize2(equities[index]),
            }
        )

    trades = [
        {
            "date": date_of(trade.ts),
            "action": trade.side,
            "qty": float(trade.qty),
            "price": float(trade.price),
            "fee": float(trade.fee),
            "realized_pnl": float(trade.realized_pnl),
            "exit_reason": trade.exit_reason,
        }
        for trade in result.trades
    ]
    risk_rejections = [
        {
            "date": date_of(r.ts),
            "symbol": r.symbol,
            "side": r.side,
            "rule_id": r.rule_id,
            "reason": r.reason,
        }
        for r in result.risk_rejections
    ]
    # 记账层拒单(现金不足/持仓不足)一并报出:反静默(ADR-0006),
    # 对照参照物教学 payload 只报风控拒案的取舍,见模块 docstring 第 3 条。
    fill_rejections = [
        {
            "date": date_of(r.ts),
            "side": r.side,
            "reason": r.reason,
        }
        for r in result.fill_rejections
    ]
    # RiskGate 协议不保证有 rules 属性;我们的 RiskManager 提供(课 04)。
    # 拿不到就如实报空清单,不猜。这里解析一次,假设行与 risk_rules 共用。
    rules = tuple(getattr(risk_manager, "rules", ()))
    risk_rules = [rule.rule_id for rule in rules]

    return {
        "engine": ENGINE_ID,
        "parameters": {"short_window": short, "long_window": long},
        "sample": {
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "rows": len(prices),
            "first_date": prices[0].date,
            "last_date": prices[-1].date,
        },
        "metrics": metrics,
        "trades": trades,
        "curve": curve,
        "risk_rejections": risk_rejections,
        "fill_rejections": fill_rejections,
        "risk_rules": risk_rules,
        "assumptions": _assumption_lines(
            short=short,
            long=long,
            prices=prices,
            fee_model=fee_model,
            slippage_model=slippage_model,
            rules=rules,
        ),
    }


def main(stream: TextIO = sys.stdout) -> int:
    """命令行演示:默认参数跑一遍 M1 教学回测,打印摘要与风险 findings。

    ``PYTHONPATH=src python -m backtest.runner``。报告的正式组装是课 06
    的职责;这里只把「回测 + 回测后风险检查」两层各跑一次,演示 M1
    切片闭环——所以 findings 层的 import 放在函数体内,runner 模块级
    不依赖它(依赖方向:编排报告的活留给报告层)。
    """
    from risk.simulation import evaluate_backtest_risk

    prices = load_teaching_sample()
    payload = run_teaching_backtest(prices)
    findings = evaluate_backtest_risk(payload)
    metrics = payload["metrics"]
    params = payload["parameters"]
    print(
        f"教学回测(M1):双均线 {params['short_window']}/{params['long_window']}"
        f" vs 买入持有({payload['sample']['rows']} 根日线)",
        file=stream,
    )
    print(
        f"策略收益 {metrics['strategy_return_pct']}%"
        f" | 买入持有 {metrics['buy_hold_return_pct']}%"
        f" | 超额 {metrics['excess_vs_buy_hold_pct']}%",
        file=stream,
    )
    print(
        f"最大回撤 {metrics['maximum_drawdown_pct']}%"
        f" | Calmar {metrics['calmar_ratio']}"
        f" | Sharpe(权益曲线口径,√252) {metrics['equity_curve_sharpe']}",
        file=stream,
    )
    print(f"成交 {metrics['trade_count']} 笔 | 期末权益 {metrics['final_equity']}", file=stream)
    if findings:
        summary = "、".join(f"{item['rule_id']}({item['severity']})" for item in findings)
        print(f"风险检查:{len(findings)} 条 findings:{summary}", file=stream)
    else:
        print("风险检查:0 条 findings。", file=stream)
    print(f"假设与边界共 {len(payload['assumptions'])} 行,全文见 payload['assumptions']。", file=stream)
    return 0


if __name__ == "__main__":
    # 直接 `python -m backtest.runner` 运行时执行;被 import 时不会执行。
    raise SystemExit(main())
