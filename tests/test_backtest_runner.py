"""M1 教学回测 runner + 指标层(票 #6,缝 2 + 指标数值冻结)。

公开缝:``run_teaching_backtest(prices, *, short, long, ...) -> payload dict``——
读收盘价样本,经事件引擎跑双均线,组装一份 JSON-ready 的回测 payload。
指标函数在 ``backtest.metrics``:Decimal 全程(回撤/Calmar),Sharpe 是
统计层、按逐 bar 权益收益算 float(口径与未来滚动引擎隔离,字段名
``equity_curve_sharpe``,ADR-0003)。

手算样例贯穿全文件:收盘 100,100,100,110,120(short=2/long=3)——
第 4 根金叉全仓买入(10000/110 股 @110),持有到期末按 120 估值:
期末权益 10000×120/110 = 10909.09、策略收益 9.09%、买入持有 20.00%、
超额 −10.91%(金叉晚了一根,错过了 100→110 那一段——双均线追涨的
天性)、零回撤(权益一路不回头的下界情形)、Calmar 按口径定义为 0。
Sharpe 手推:收益序列 {0,0,0,r} 的 mean/std 恒为 1/2,故 = 0.5×√252 ≈ 7.94。
"""

import io
import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backtest.metrics import calmar_ratio, equity_curve_sharpe, maximum_drawdown
from backtest.runner import Price, load_prices, load_teaching_sample, run_teaching_backtest
from backtest.runner import main as runner_main
from strategy_engine.backtest.models import ConstantBpsFee, ConstantBpsSlippage
from strategy_engine.backtest.risk import KillSwitch, RiskManager

D = Decimal


def make_prices(closes: list[str], *, start: str = "2025-01-01") -> list[Price]:
    """小工具:从 start 起连续日期配上收盘价,造一份最小价格样本。"""
    first = date.fromisoformat(start)
    return [
        Price((first + timedelta(days=idx)).isoformat(), Decimal(close))
        for idx, close in enumerate(closes)
    ]


# ---------- 指标层:手算冻结 ----------


def test_maximum_drawdown_hand_computed() -> None:
    """权益 100→120→90→130:峰值 120 跌到 90,回撤 30/120 = 0.25;
    后面新高不回撤。全程 Decimal,无 float 噪声。"""
    assert maximum_drawdown([D("100"), D("120"), D("90"), D("130")]) == D("0.25")
    assert maximum_drawdown([D("100"), D("50")]) == D("0.5")
    # 单调上行(或持平):从未低于峰值,回撤为 0。
    assert maximum_drawdown([D("100"), D("100"), D("130")]) == D("0")


def test_calmar_ratio_pure_form_and_zero_drawdown() -> None:
    """Calmar = 总收益% / |最大回撤%|(同一回测期、不做年度化,「纯 Calmar」
    口径,参照物 runner.py 注释同款);零回撤时按定义记 0。"""
    assert calmar_ratio(D("24"), D("-12")) == D("2")
    assert calmar_ratio(D("24"), D("0")) == D("0")
    assert calmar_ratio(D("-24"), D("-12")) == D("-2")


def test_equity_curve_sharpe_edge_cases_and_hand_value() -> None:
    """退化情形(样本不足 / 零波动)一律 0.0;正常样本手算:
    权益 100→110→115.5,收益 {0.1, 0.05}:mean 0.075、样本方差 0.00125、
    std = 0.025√2 → Sharpe = (0.075/(0.025√2))×√252 = 3/√2×√252 ≈ 33.67。"""
    assert equity_curve_sharpe([]) == 0.0
    assert equity_curve_sharpe([100.0]) == 0.0
    assert equity_curve_sharpe([100.0, 110.0]) == 0.0  # 只有一期收益
    assert equity_curve_sharpe([100.0, 100.0, 100.0]) == 0.0  # 零波动
    assert equity_curve_sharpe([100.0, 110.0, 115.5]) == pytest.approx(
        (0.075 / (0.025 * math.sqrt(2))) * math.sqrt(252), abs=0.01
    )


# ---------- runner:payload 结构与对比字段(AC2)----------


def test_run_teaching_backtest_payload_structure() -> None:
    """payload 的形状契约:引擎身份、参数、样本块、指标块、成交/曲线/
    两类拒单/风控规则清单/假设说明行,全部 JSON-ready。"""
    payload = run_teaching_backtest(make_prices(["100", "100", "100", "110", "120"]), short=2, long=3)
    assert set(payload) == {
        "engine",
        "parameters",
        "sample",
        "metrics",
        "trades",
        "curve",
        "risk_rejections",
        "fill_rejections",
        "risk_rules",
        "assumptions",
    }
    assert payload["engine"] == "event-driven"
    assert payload["parameters"] == {"short_window": 2, "long_window": 3}
    assert payload["sample"] == {
        "symbol": "QUANT-DEMO/USDT",
        "timeframe": "1d",
        "rows": 5,
        "first_date": "2025-01-01",
        "last_date": "2025-01-05",
    }
    # 默认挂五条规则的风控闸(刀 2 的工厂),rule id 清单随 payload 报出。
    assert payload["risk_rules"] == [
        "EMERGENCY_HALT",
        "MAX_POSITION_PCT",
        "MAX_DAILY_LOSS_PCT",
        "MAX_SLIPPAGE_PCT",
        "ABNORMAL_ORDERBOOK",
    ]
    assert payload["risk_rejections"] == []
    assert payload["fill_rejections"] == []
    assert payload["assumptions"] and all(isinstance(x, str) and x for x in payload["assumptions"])
    # 曲线:逐根收盘 / 两条均线 / 权益;窗口未填满处均线为 None。
    assert len(payload["curve"]) == 5
    assert payload["curve"][0] == {
        "date": "2025-01-01",
        "close": 100.0,
        "short_ma": None,
        "long_ma": None,
        "equity": 10000.0,
    }
    assert payload["curve"][3]["short_ma"] == 105.0
    assert payload["curve"][3]["long_ma"] == 103.3333  # (100+100+110)/3,四位小数
    assert payload["curve"][4]["long_ma"] == 110.0
    # 成交行:日期、方向、价格……(数量等在对比测试外,逐字段断言见下)
    assert payload["trades"][0]["date"] == "2025-01-04"
    assert payload["trades"][0]["action"] == "buy"
    assert payload["trades"][0]["price"] == 110.0


def test_metrics_compare_strategy_against_buy_and_hold() -> None:
    """AC2:双均线 vs 买入持有对比字段齐备——两边的收益率、超额、期末
    权益、交易数、回撤/Calmar/Sharpe,值全部手算冻结。"""
    payload = run_teaching_backtest(make_prices(["100", "100", "100", "110", "120"]), short=2, long=3)
    assert set(payload["metrics"]) == {
        "strategy_return_pct",
        "buy_hold_return_pct",
        "excess_vs_buy_hold_pct",
        "maximum_drawdown_pct",
        "calmar_ratio",
        "equity_curve_sharpe",
        "trade_count",
        "final_equity",
    }
    metrics = payload["metrics"]
    # 全仓买入 10000/110 股 @110,期末按 120 估值:
    # 收益 = (10000×120/110 − 10000)/10000 = 9.09%。
    assert metrics["strategy_return_pct"] == 9.09
    # 基准:120/100 − 1 = 20%;策略 110 才入场,错过 100→110 一段。
    assert metrics["buy_hold_return_pct"] == 20.0
    assert metrics["excess_vs_buy_hold_pct"] == -10.91
    assert metrics["final_equity"] == 10909.09
    assert metrics["trade_count"] == 1
    # 权益从不低于前高:回撤 0、Calmar 按口径记 0。
    assert metrics["maximum_drawdown_pct"] == 0.0
    assert metrics["calmar_ratio"] == 0.0
    # 收益序列 {0,0,0,r}:mean/std = 1/2,Sharpe = 0.5×√252 ≈ 7.94(手推)。
    assert metrics["equity_curve_sharpe"] == 7.94


def test_window_and_sample_length_validation_are_chinese() -> None:
    """参数守卫的报错是用户可见文案(ADR-0005):窗口须 2 ≤ 短 < 长;
    样本行数必须多于长窗。"""
    prices = make_prices(["100", "100", "100", "110", "120"])
    with pytest.raises(ValueError, match="双均线窗口须满足 2 ≤ 短窗 < 长窗"):
        run_teaching_backtest(prices, short=2, long=2)
    with pytest.raises(ValueError, match="双均线窗口须满足 2 ≤ 短窗 < 长窗"):
        run_teaching_backtest(prices, short=1, long=3)
    with pytest.raises(ValueError, match="样本行数不足"):
        run_teaching_backtest(prices[:3], short=2, long=3)


def test_load_teaching_sample_reads_committed_csv() -> None:
    """教学样本装载缝:读仓库里那份 381 行 CSV(课 02 铸造、manifest 锁
    指纹),价格保持 Decimal 文本精度。"""
    prices = load_teaching_sample()
    assert len(prices) == 381
    assert prices[0] == Price("2025-03-03", Decimal("44.07"))
    assert prices[-1] == Price("2026-08-17", Decimal("54.95"))


# ---------- 假设说明行:随成本/参数变化(AC3)----------


def test_assumption_lines_track_window_parameters() -> None:
    """换窗口 → 「策略」行随之变;两份假设行清单不再相同。"""
    prices = make_prices(["100", "100", "100", "110", "120"])
    base = run_teaching_backtest(prices, short=2, long=3)
    variant = run_teaching_backtest(prices, short=3, long=4)
    assert any("短窗 2 / 长窗 3" in line for line in base["assumptions"])
    assert any("短窗 3 / 长窗 4" in line for line in variant["assumptions"])
    assert base["assumptions"] != variant["assumptions"]


def test_assumption_lines_track_cost_models() -> None:
    """默认零成本 → 「零费率、零滑点」;挂上 bps 模型 → 行文随实例变,
    且绝不再出现「零费率」——假设行描述的是真正跑过的配置。"""
    prices = make_prices(["100", "100", "100", "110", "120"])
    base = run_teaching_backtest(prices, short=2, long=3)
    assert any(line.startswith("成本:零费率、零滑点") for line in base["assumptions"])

    cost_run = run_teaching_backtest(
        prices,
        short=2,
        long=3,
        fee_model=ConstantBpsFee(maker_bps=Decimal("7"), taker_bps=Decimal("9")),
        slippage_model=ConstantBpsSlippage(bps=Decimal("3")),
    )
    assert any(
        line.startswith("成本:费率 maker 7bps / taker 9bps、滑点 3bps")
        for line in cost_run["assumptions"]
    )
    assert not any("零费率" in line for line in cost_run["assumptions"])
    # 全仓策略 + 非零成本的真实后果:费用把现金打穿,买单被记账层拒——
    # 显式进入 fill_rejections(反静默,ADR-0006),不静默吞掉。
    assert cost_run["fill_rejections"]
    assert all("现金不足" in item["reason"] for item in cost_run["fill_rejections"])
    assert cost_run["metrics"]["trade_count"] == 0


def test_assumption_lines_track_risk_gate() -> None:
    """风控行报告实际挂的规则清单:默认五条;换成只挂紧急停止 → 一条。"""
    prices = make_prices(["100", "100", "100", "110", "120"])
    base = run_teaching_backtest(prices, short=2, long=3)
    assert any(
        line.startswith(
            "运行时风控:5 条规则(EMERGENCY_HALT、MAX_POSITION_PCT、MAX_DAILY_LOSS_PCT、"
            "MAX_SLIPPAGE_PCT、ABNORMAL_ORDERBOOK)"
        )
        for line in base["assumptions"]
    )
    lean = run_teaching_backtest(
        prices, short=2, long=3, risk_manager=RiskManager([KillSwitch()])
    )
    assert any(
        line.startswith("运行时风控:1 条规则(EMERGENCY_HALT)")
        for line in lean["assumptions"]
    )


# ---------- 真教学样本:指标数值冻结(AC1)----------


def test_frozen_metrics_on_committed_teaching_sample() -> None:
    """AC1:默认参数(短 3 / 长 7、零成本、五规则风控闸)在 381 行教学
    样本上的全部指标**逐值冻结**。样本由课 02 固定种子铸造、manifest 锁
    sha256,引擎行为被课 03/04 测试锁死——三重确定性叠出这一组数,动
    任何一层(数据 / 引擎 / 策略 / 口径)都该在这里红。

    数字怎么读(课 05 的教学故事):两轮往返后权益 10185.71 > 仓位上限
    (= 初始本金 10000),此后每次全仓买入都被 MAX_POSITION_PCT 拦下
    (193 次),策略被迫空仓坐看买入持有 +24.69%——「风控前置的真实
    代价」与「全仓策略不能复利」都写在这组数字里。
    """
    payload = run_teaching_backtest(load_teaching_sample())
    assert payload["metrics"] == {
        "strategy_return_pct": 1.86,
        "buy_hold_return_pct": 24.69,
        "excess_vs_buy_hold_pct": -22.83,
        "maximum_drawdown_pct": -0.81,
        "calmar_ratio": 2.3,
        "equity_curve_sharpe": 0.77,
        "trade_count": 4,
        "final_equity": 10185.71,
    }
    # 曲线与拒单的形状一并冻结:381 根、193 条 MAX_POSITION_PCT 拦截、
    # 零记账拒单(数量按步长取整后,尘埃问题不复存在)。
    assert len(payload["curve"]) == 381
    assert len(payload["risk_rejections"]) == 193
    assert {item["rule_id"] for item in payload["risk_rejections"]} == {"MAX_POSITION_PCT"}
    assert payload["fill_rejections"] == []
    # 四笔成交:两轮完整的「买 → 卖」往返。
    assert [(t["date"], t["action"]) for t in payload["trades"]] == [
        ("2025-03-11", "buy"),
        ("2025-03-18", "sell"),
        ("2025-03-31", "buy"),
        ("2025-04-14", "sell"),
    ]


def test_payload_is_json_serializable_and_deterministic() -> None:
    """M1 验收的前提:payload 可直接 ``json.dumps``;同配置跑两遍,
    序列化字节逐位一致(没有墙钟、没有随机源,确定性可断言)。"""
    import json

    prices = load_teaching_sample()
    first = run_teaching_backtest(prices)
    second = run_teaching_backtest(prices)
    dumped_first = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert dumped_first == json.dumps(second, ensure_ascii=False, sort_keys=True)
    # ensure_ascii=False 走 UTF-8 中文直出;再验默认 dumps 也可序列化。
    json.dumps(first)


# ---------- 命令行演示入口 ----------


def test_runner_main_prints_m1_summary_with_findings() -> None:
    """``PYTHONPATH=src python -m backtest.runner`` 的输出契约:默认配置
    的 M1 摘要(指标行逐字锁)+ 风险 findings 概览,退出码 0。"""
    stream = io.StringIO()
    exit_code = runner_main(stream)
    assert exit_code == 0
    out = stream.getvalue()
    assert "教学回测(M1):双均线 3/7 vs 买入持有(381 根日线)" in out
    assert "策略收益 1.86% | 买入持有 24.69% | 超额 -22.83%" in out
    assert "最大回撤 -0.81% | Calmar 2.3 | Sharpe(权益曲线口径,√252) 0.77" in out
    assert "成交 4 笔 | 期末权益 10185.71" in out
    # 冻结故事的另一半:193 次仓位上限拦截 + 跑输基准,两条 findings。
    assert "风险检查:2 条 findings" in out
    assert "MAX_POSITION_PCT(warning)" in out
    assert "STRATEGY_UNDERPERFORM(info)" in out
    assert "假设与边界共 8 行" in out


# ---------- 文案锁的补口(ADR-0005:用户可见文案全覆盖)----------


class _FlatFee:
    """自定义费率模型(非内置类):固定收 0——结构上就不是 ZeroFee。"""

    def calc(self, intent, fill_price):
        return Decimal("0")


class _FlatSlippage:
    """自定义滑点模型(非内置类):按收盘价成交——结构上就不是 ZeroSlippage。"""

    def fill_price(self, intent, candle):
        return candle.close


def test_missing_price_file_raises_chinese_copy() -> None:
    """load_prices 的缺文件报错是用户可见文案:中文、带路径,被锁死。"""
    with pytest.raises(FileNotFoundError, match="价格样本缺失"):
        load_prices(Path("no/such/prices.csv"))


def test_assumption_lines_describe_custom_models_honestly() -> None:
    """不认识的自定义成本模型:假设行只报类型名,绝不冒充「零费率/零
    滑点」;零成本的自定义实现照样全仓成交(数量已按步长取整)。"""
    payload = run_teaching_backtest(
        make_prices(["100", "100", "100", "110", "120"]),
        short=2,
        long=3,
        fee_model=_FlatFee(),
        slippage_model=_FlatSlippage(),
    )
    assert any(
        line.startswith("成本:自定义费率模型(_FlatFee)、自定义滑点模型(_FlatSlippage)")
        for line in payload["assumptions"]
    )
    assert not any("零费率" in line or "零滑点" in line for line in payload["assumptions"])
    assert payload["metrics"]["trade_count"] == 1
    assert payload["fill_rejections"] == []
