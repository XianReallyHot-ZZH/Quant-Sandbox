"""回测后风险检查 findings 层(票 #6 AC4,课 05)。

对照参照物 ``src/risk/simulation.py``(研报 §3.6 #3)同构复现。要理解
的问题:**同一个 rule id 存在两层风控**——

- 运行时层(pre_trade):订单提交前被 ``RiskManager`` 拦下,发生在
  引擎里(课 04),拒单已带 rule_id 落在 payload 的 ``risk_rejections``;
- 复盘层(post_backtest):回测跑完后从**指标**反推的问题(回撤过深、
  跑输基准、过度换手),这里补看。

``MAX_DAILY_LOSS_PCT`` 两层都有份:运行时的峰值回撤闸如果已经在拦,
复盘层就**不再**重复报同一事实——按 rule_id 去重,同一问题只出现一次、
阶段以先发生的 pre_trade 为准。不去重的后果是报告里同一条规则出现两
次,读的人不知道是两回事还是一件事(参照物专门写了 ``simulation.py``
的去重段,我们照学)。

与参照物的两处刻意差异:

1. **回撤符号口径自适应**:payload 里 ``maximum_drawdown_pct`` 以负数
   呈现(亏损记负,课 05 runner 口径);参照物的复盘判断写了
   ``drawdown < 0 and abs(drawdown) >= ...`` 双保险。我们直接比
   ``abs(drawdown)``——符号约定是口径的事,阈值判断不该依赖它。
2. **消息文案是中文且被测试锁死**(ADR-0005);参照物中英混排。

severity 是机器标签(与 rule_id 一样走英文):critical(紧急停止)/
warning(四条内置规则)/ info(其他与提示类)。phase 与 source 标注
findings 的来源层:``pre_trade`` + ``event_engine/runtime`` 或
``post_backtest`` + ``event_engine/post_backtest``。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

# rule_id 的唯一事实源在运行时规则层(课 04):本模块按 id 去重、排严重度
# 阶梯,引用同一批常量——字符串只活在 risk.py 一处。
from strategy_engine.backtest.risk import (
    ABNORMAL_CANDLE_RULE_ID,
    EMERGENCY_HALT_RULE_ID,
    MAX_DRAWDOWN_RULE_ID,
    MAX_POSITION_RULE_ID,
    MAX_SLIPPAGE_RULE_ID,
)

# 内置四条(紧急停止除外)→ warning;不在表里的按 info(向前兼容新规则)。
_WARNING_RULE_IDS = frozenset(
    {MAX_POSITION_RULE_ID, MAX_DRAWDOWN_RULE_ID, MAX_SLIPPAGE_RULE_ID, ABNORMAL_CANDLE_RULE_ID}
)


@dataclass(frozen=True, slots=True)
class RiskFinding:
    """一条风险发现:规则、严重度、人话消息、来源、阶段、次数。

    ``count`` 对运行时拦截是「同规则拦了几笔」;复盘层的 finding 不分组,
    恒为 1。frozen 值对象;``asdict`` 转成 dict 进 payload/报告。
    """

    rule_id: str
    severity: str
    message: str
    source: str
    phase: str = "post_backtest"
    count: int = 1


def _severity_for_rule(rule_id: str) -> str:
    """rule id → 严重度:紧急停止 critical,内置四条 warning,其余 info。"""
    if rule_id == EMERGENCY_HALT_RULE_ID:
        return "critical"
    if rule_id in _WARNING_RULE_IDS:
        return "warning"
    return "info"


def _runtime_findings(rejections: list[dict]) -> list[RiskFinding]:
    """把运行时拦截按 rule_id 分组:每规则一条 finding,count 计数,
    消息取**第一条**拒单的理由(最早的现场)并附总数。"""
    if not rejections:
        return []
    counts = Counter(item["rule_id"] for item in rejections)
    sample_by_rule: dict[str, dict] = {}
    for item in rejections:
        # setdefault 只在键首次出现时写入 → 保留第一条作样本。
        sample_by_rule.setdefault(item["rule_id"], item)
    findings: list[RiskFinding] = []
    # 按 rule_id 排序:输出顺序确定,报告逐字节可复现。
    for rule_id, count in sorted(counts.items()):
        sample = sample_by_rule[rule_id]
        suffix = f"(共拦截 {count} 笔)" if count > 1 else ""
        findings.append(
            RiskFinding(
                rule_id=rule_id,
                severity=_severity_for_rule(rule_id),
                message=f"{sample['reason']}{suffix}",
                source="event_engine/runtime",
                phase="pre_trade",
                count=count,
            )
        )
    return findings


def evaluate_backtest_risk(
    backtest: dict, *, max_drawdown_pct: float = 15.0
) -> list[dict]:
    """合并两层风控,产出回测的完整 findings 清单(list[dict],JSON-ready)。

    只读 payload 的三个键:``metrics``、``curve``、``risk_rejections``——
    不碰引擎内部对象,任何能给出这三个键的回测结果都能复盘(对账桥、
    滚动引擎 payload 之后的课复用同一入口)。
    """
    findings: list[RiskFinding] = []
    findings.extend(_runtime_findings(backtest.get("risk_rejections") or []))

    metrics = backtest["metrics"]
    runtime_rule_ids = {finding.rule_id for finding in findings}

    # 复盘门一:最大回撤。payload 口径是负百分比(亏损记负),阈值判断
    # 取绝对值、不依赖符号;消息里报幅度(自然读法)。运行时已拦过同
    # id 的,跳过——去重,同一事实只报一次。
    drawdown = metrics["maximum_drawdown_pct"]
    if abs(drawdown) >= max_drawdown_pct and MAX_DRAWDOWN_RULE_ID not in runtime_rule_ids:
        findings.append(
            RiskFinding(
                rule_id=MAX_DRAWDOWN_RULE_ID,
                severity="warning",
                message=(
                    f"最大回撤 {abs(drawdown):g}% 达到复盘阈值 {max_drawdown_pct:g}%:"
                    "若该策略接入实时引擎,峰值回撤闸会在回撤中拦下新开仓。"
                ),
                source="event_engine/post_backtest",
            )
        )

    # 复盘门二:跑输买入持有——info 级提示(不是错误,是「该参数组合
    # 可能不适合此区间」的证据)。
    if metrics["strategy_return_pct"] < metrics["buy_hold_return_pct"]:
        findings.append(
            RiskFinding(
                rule_id="STRATEGY_UNDERPERFORM",
                severity="info",
                message=(
                    f"策略收益 {metrics['strategy_return_pct']:g}% 低于买入持有"
                    f" {metrics['buy_hold_return_pct']:g}%,当前参数组合可能不适合该样本区间。"
                ),
                source="event_engine/post_backtest",
            )
        )

    # 复盘门三:过度换手——成交笔数超过样本天数的一半,警示频繁进出。
    sample_days = len(backtest["curve"])
    if metrics["trade_count"] > sample_days // 2:
        findings.append(
            RiskFinding(
                rule_id="EXCESSIVE_TURNOVER",
                severity="warning",
                message=(
                    f"交易动作 {metrics['trade_count']} 次已超过样本长度"
                    f" {sample_days} 天的一半,可能存在过度换手。"
                ),
                source="event_engine/post_backtest",
            )
        )

    return [asdict(finding) for finding in findings]
