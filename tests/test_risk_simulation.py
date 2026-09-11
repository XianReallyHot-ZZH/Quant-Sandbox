"""回测后风险检查 findings 层(票 #6 AC4,课 05)。

公开缝:``evaluate_backtest_risk(backtest_payload, *, max_drawdown_pct=15.0)
-> list[dict]``。它把两层风控**合并成一份 findings**:运行时拦截
(pre_trade,订单提交前被 RiskManager 拦下)按 rule_id 分组计数;回测后
复盘门(post_backtest)再补看回撤 / 跑赢基准 / 换手率。两层共用
``MAX_DAILY_LOSS_PCT`` 这条 rule id——运行时已拦过的,复盘层**不再重复
报告**(按 rule id 去重,研报 §3.6 #3 点破的参照物坑,对照
``src/risk/simulation.py:62-68`` 同构复现)。消息文案是中文运行时契约
(ADR-0005),本文件逐条锁死。
"""

from backtest.runner import load_teaching_sample, run_teaching_backtest
from risk.simulation import evaluate_backtest_risk


def make_payload(
    *,
    strategy: float = 10.0,
    buy_hold: float = 5.0,
    drawdown: float = -3.0,
    trade_count: int = 4,
    days: int = 100,
    rejections: list[dict] | None = None,
) -> dict:
    """造一个最小的回测 payload:findings 层只读 metrics、curve、
    risk_rejections 三个键,其余从简。"""
    return {
        "metrics": {
            "strategy_return_pct": strategy,
            "buy_hold_return_pct": buy_hold,
            "maximum_drawdown_pct": drawdown,
            "trade_count": trade_count,
        },
        "curve": [{"date": f"2025-01-{i:02d}"} for i in range(1, days + 1)],
        "risk_rejections": rejections or [],
    }


def rejection(rule_id: str, reason: str = "示例拒单理由") -> dict:
    return {"date": "2025-04-16", "symbol": "QUANT-DEMO/USDT", "side": "buy", "rule_id": rule_id, "reason": reason}


def test_runtime_rejections_grouped_by_rule_id_with_counts() -> None:
    """运行时拦截按 rule_id 分组:同规则多条 → 一条 finding、count 计数、
    消息带「共拦截 N 笔」;来源与阶段如实标注 pre_trade。"""
    payload = make_payload(
        rejections=[
            rejection("MAX_DAILY_LOSS_PCT", "权益 9000 较峰值 10000 回撤 10%,达到上限 10%"),
            rejection("MAX_DAILY_LOSS_PCT", "权益 8900 较峰值 10000 回撤 11%,达到上限 10%"),
            rejection("MAX_SLIPPAGE_PCT", "当根振幅 3% 超过上限 2%"),
        ]
    )
    findings = evaluate_backtest_risk(payload)
    by_id = {item["rule_id"]: item for item in findings}
    assert set(by_id) == {"MAX_DAILY_LOSS_PCT", "MAX_SLIPPAGE_PCT"}
    grouped = by_id["MAX_DAILY_LOSS_PCT"]
    # 分组取**第一条**拒单的理由作样本消息,再补计数后缀。
    assert grouped["count"] == 2
    assert grouped["message"].startswith("权益 9000 较峰值 10000 回撤 10%,达到上限 10%")
    assert grouped["message"].endswith("(共拦截 2 笔)")
    assert grouped["phase"] == "pre_trade"
    assert grouped["source"] == "event_engine/runtime"
    assert grouped["severity"] == "warning"
    single = by_id["MAX_SLIPPAGE_PCT"]
    assert single["count"] == 1
    assert single["message"] == "当根振幅 3% 超过上限 2%"  # 单条不加计数后缀


def test_drawdown_finding_dedups_against_runtime_interception() -> None:
    """AC4 核心:回撤 ≥ 阈值、且运行时已经以同一 rule_id(MAX_DAILY_LOSS_PCT)
    拦截过 → 复盘层**不再**追加同 id 的 post_backtest finding——同一事实
    只报一次,阶段以先发生的 pre_trade 为准。"""
    payload = make_payload(
        drawdown=-17.5,
        rejections=[rejection("MAX_DAILY_LOSS_PCT", "权益回撤达到上限")],
    )
    findings = evaluate_backtest_risk(payload)
    dd_findings = [item for item in findings if item["rule_id"] == "MAX_DAILY_LOSS_PCT"]
    assert len(dd_findings) == 1
    assert dd_findings[0]["phase"] == "pre_trade"


def test_drawdown_finding_fires_when_runtime_silent() -> None:
    """对照组:运行时没拦过(规则阈值更宽/未挂闸),但复盘口径下回撤
    17.5% ≥ 阈值 15% → post_backtest finding 出现,中文消息点名数字与
    「若接入实时引擎」的含义。"""
    payload = make_payload(drawdown=-17.5)
    (finding,) = evaluate_backtest_risk(payload)
    assert finding["rule_id"] == "MAX_DAILY_LOSS_PCT"
    assert finding["phase"] == "post_backtest"
    assert finding["source"] == "event_engine/post_backtest"
    assert finding["severity"] == "warning"
    assert "最大回撤 17.5%" in finding["message"]
    assert "15%" in finding["message"]
    assert "若该策略接入实时引擎" in finding["message"]


def test_underperform_and_excessive_turnover_gates() -> None:
    """另两道复盘门:跑输买入持有(info,提示参数可能不适合本区间);
    交易数超过样本天数一半(warning,过度换手)。"""
    payload = make_payload(strategy=1.86, buy_hold=24.69, days=10, trade_count=6)
    findings = evaluate_backtest_risk(payload)
    by_id = {item["rule_id"]: item for item in findings}
    assert by_id["STRATEGY_UNDERPERFORM"]["severity"] == "info"
    assert "买入持有" in by_id["STRATEGY_UNDERPERFORM"]["message"]
    turnover = by_id["EXCESSIVE_TURNOVER"]
    assert turnover["severity"] == "warning"
    assert "过度换手" in turnover["message"]


def test_clean_backtest_has_no_findings() -> None:
    """干净的回测(回撤小、跑赢基准、换手低、无拦截)→ findings 为空,
    「没有问题」也是一种要能说出的结论。"""
    assert evaluate_backtest_risk(make_payload()) == []


def test_severity_ladder_covers_all_builtin_rule_ids() -> None:
    """严重度阶梯:EMERGENCY_HALT = critical;其余四条内置规则 = warning;
    未知 id = info(向前兼容后续课程的新规则)。"""
    payload = make_payload(
        rejections=[
            rejection("EMERGENCY_HALT", "紧急停止已触发:人工拉闸"),
            rejection("MAX_POSITION_PCT"),
            rejection("ABNORMAL_ORDERBOOK"),
            rejection("SOME_FUTURE_RULE"),
        ]
    )
    severities = {item["rule_id"]: item["severity"] for item in evaluate_backtest_risk(payload)}
    assert severities["EMERGENCY_HALT"] == "critical"
    assert severities["MAX_POSITION_PCT"] == "warning"
    assert severities["ABNORMAL_ORDERBOOK"] == "warning"
    assert severities["SOME_FUTURE_RULE"] == "info"


def test_m1_default_run_surfaces_position_cap_story() -> None:
    """端到端一次:真样本默认配置(冻结指标见 test_backtest_runner)下,
    findings 应如实报出 193 次 MAX_POSITION_PCT 拦截与跑输买入持有——
    M1 的「风控前置代价」在风险层的可见性。"""
    payload = run_teaching_backtest(load_teaching_sample())
    findings = evaluate_backtest_risk(payload)
    by_id = {item["rule_id"]: item for item in findings}
    assert by_id["MAX_POSITION_PCT"]["count"] == 193
    assert by_id["MAX_POSITION_PCT"]["phase"] == "pre_trade"
    assert "STRATEGY_UNDERPERFORM" in by_id
    # 回撤 0.81% 远低于 15% 阈值,复盘层的回撤门不触发(也没有运行时拦截)。
    assert "MAX_DAILY_LOSS_PCT" not in by_id
    # 换手门:4 笔 << 381/2,不触发。
    assert "EXCESSIVE_TURNOVER" not in by_id
