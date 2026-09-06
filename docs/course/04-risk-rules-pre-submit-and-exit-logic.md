# 课 04:风控前置 + 出场逻辑(事件引擎)(票 #5)

> 上一课结束时:事件引擎能跑回测——策略提交 Decimal 订单意图,bar 闭环结算挂单/限价/止损,产出成交与权益曲线;风控只是一条预埋的缝(stub 测试)。
> 本课结束时:引擎有了纪律层——五条内置 RiskRule 在订单提交前拦下不合格意图(命中即短路、拒单显式入结果),出场判定替策略盯持仓(止损/止盈/移动止损/超时平仓/信号反转),五类出场原因的中文文案成为运行时契约,平仓成交带着原因落在缝 2 上。

## 本课目标

课 03 的引擎「会跑但没刹车」:策略说要买就买,浮亏到天荒地老也不平仓。本课把参照物 `src/risk/manager.py` 的五条内置规则挂上预埋的风控缝,再把参照物放在滚动引擎里的出场判定(`backtest/rolling/risk/position.py` 的 `check_exit`)适配到事件引擎——票文一句话:风控前置 + 出场逻辑,都长在事件引擎上。

两个验收标准:

1. **AC1**:每条风控规则至少一条触发测试,拦截时订单不产生成交;
2. **AC2**:每个出场原因至少一条路径测试并断言中文文案(ADR-0005)。

## 动手前的三个问题

1. 风控闸门为什么在「提交时」和「挂单触发当根」各问一次,而不是提交时一次放行?
2. 五条规则「命中即短路」——规则在列表里的顺序为什么仍然重要?
3. 出场判定为什么不放进策略函数、也不在判定里扣手续费?

(答案都在下文。)

## 核心概念

- **风控前置**(词汇表:事件引擎的定义成分)——引擎接受任何意图之前先问闸门;本课落地 `risk.py`:五条规则 + `RiskManager` 组合器。
- **RiskRule**——一条规则的形状:`rule_id` + `check(intent, *, ctx, portfolio, candle) -> RiskCheck`。**rule_id 是运行时契约**:五个 id 逐字照抄参照物(`MAX_POSITION_PCT` / `MAX_DAILY_LOSS_PCT` / `MAX_SLIPPAGE_PCT` / `ABNORMAL_ORDERBOOK` / `EMERGENCY_HALT`),课 06 的回测后 findings 层要按 id 与这里的运行时拦截去重(研报 §3.6「两套风控 ID 重叠」的坑)。
- **RiskManager**——规则集的串联器:逐条问,**第一条命中即短路**。它结构化满足课 03 预埋的 `RiskGate` 协议(协议本课从 `RiskManager` 改名 `RiskGate`,把名字让给参照物同名的实现)。
- **出场判定(check_exit)**——纯函数:持仓 + 现价 + 信号分 + bar 序号 → 出不出、为什么。优先级固定:移动止损 → 止损 → 止盈 → 超时平仓 → 信号反转(保命的先判,落袋的后判)。
- **ExitManager**——引擎侧接线:看成交(开仓/清仓)、爬峰值、逐根问一次 check_exit;命中就以市价单平掉全部持仓。
- **出场原因(运行时契约)**——`止损/止盈/移动止损/超时平仓/信号反转` 五个词,ADR-0005 点名它是参照物契约的一部分:改一个字 = 改契约,测试逐字断言锁死。
- **缝 2(引擎结果)**——本课一切断言仍落在这里:风控拦截进 `risk_rejections`(带 rule_id 与中文理由),出场平仓进 `trades`(带 `exit_reason` 字段)。

## 一起实现:红绿实录

本课切了五刀(风控组合器与仓位闸 → 回撤/振幅闸 → 异常 K 线/紧急停止 → check_exit 纯函数 → 引擎集成),五刀全绿后按双轴评审又修了一轮。**实现侧五刀全部一次绿;唯一一次意外红在刀 1 的测试导入面**(详见下)。与课 03 相反——那次三次红全在手算,这次手算一次没错:本课的独立事实源是参照物源码本身,断言照它的语义写,没有中间商。

### 刀 1:RiskManager 短路契约 + MaxPositionRule(AC1)

- **红**:`ModuleNotFoundError`(risk 模块不存在)。
- **断言来自哪里**:参照物 `manager.py` 语义——买 60@100 成交后名义 6000 > 上限 5000 → 拦;「命中即短路」用计数器规则验证(拦截规则之后的那条,`checked` 必须保持 0);放行路径(4900 ≤ 5000 正常成交)防规则误伤。
- **绿**:实现一次过。**但意外红了一次**:测试文件头一把导入了全部五个规则名,而本刀只实现了两个——`ImportError: cannot import name 'AbnormalCandleRule'`。修法是收窄导入面到本刀已存在的符号。教训:**切片切的是测试文件的全部,不只是测试函数**;导入清单写到了未来,红就不能说明「本刀的实现错了」。
- 顺手改:engine 的协议从 `RiskManager` 改名 `RiskGate`(它自己的 docstring 本来就写着「风控闸门」),给参照物同名的组合器让位。改名前 grep 过全仓:无人按名导入,零波及。

### 刀 2:MaxDrawdownRule + MaxSlippageRule(AC1)

- **红**:`ImportError`。
- **断言来自哪里**:回撤闸的有状态性——bar1 权益 10000 记为峰值,买 10@100 后 bar2 收 85 → 权益 9850、回撤 1.5% ≥ 1% → bar2 的买入被拦(手算);**卖出永远放行**(回撤里焊死逃生门是最坏的设计,参照物同款);振幅闸 (110−90)/100 = 20% > 10% 拦、平 K 线放行。
- **绿**:一次过。8 passed。

### 刀 3:AbnormalCandleRule + KillSwitch + float 边界(AC1)

- **红**:`ImportError`。
- **断言来自哪里**:三种异常形态各有路径——零成交量但 H≠L(行情损坏/停牌)、H=L 却有量(陈旧行情)、相邻收盘跳动 30% > 10%;**挂单复查时点的「上一根收盘价」**专设一条测试:结算发生在 history 追加当根之前、提交发生在之后,规则内部取「history 里最后一根**不是当根对象**」的收盘价,两种时点必须指向同一根 bar;KillSwitch trip 后一刀切、reset 后恢复;四个阈值构造点全部拒绝 float(TypeError,中文文案)。
- **绿**:一次过。15 passed。测试脚手架顺手给 `make_candle` 加了 `volume` 关键字(默认 "1" 而非压平——「零成交量的 K 线」是本刀要造的异常形态,值得显式传 "0")。

### 刀 4:check_exit 纯函数 + ExitConfig(AC2)

- **红**:`ImportError`(exits 模块不存在)。
- **断言来自哪里**:参照物 `position.py` 逐条对照——止损:入场 100、价 94 → 浮亏 6% ≤ −3%;止盈:+6% ≥ 5%;移动止损:峰值 120、阈值 5% → 触发线 114,价 113 命中且此时浮盈 +13%(不与止损/止盈混);**优先级测试**:价 90 同时满足移动止损与固定止损,先判的必须赢;超时:第 0 根入场、上限 2 根,第 2 根命中;信号反转:多头遇 ≤ 0 的信号分离场(参照物阈值硬编码 0),正分离场为否;`sig_score=None` = 不给信号 → 反转分支整体跳过(我们的适配,参照物总有 float 信号)。
- **绿**:一次过。9 passed。

### 刀 5:引擎集成——ExitManager + trade.exit_reason(AC2)

- **红**:9 个引擎级测试全红(9 个纯函数测试照绿)——集成未实现,红得精确。
- **断言来自哪里**:票文指定缝 2——出场必须以「带 exit_reason 的平仓成交」出现在 `BacktestResult`。五个原因各一条引擎级路径(止损场景断言到权益 9940 的手算全链);**入场当根不查出场**专设一条:限价 95 在 bar2 结算成交、当根收 90 虽已浮亏 5.26% 但跳过,bar3 才出「止损」(与「决策根/结算根分离」同一哲学,参照物由循环顺序天然保证);**出场单过同一道风控闸**:拉闸后出场被拦、仓位保留、下一根条件仍在继续重试;渲染稳定性:同输入两遍 `render_result` 逐字节一致,trade 行尾出现 `exit=止损` 且仅一笔带。
- **绿**:一次过。18 passed。三处落码:`models.py` 给 `BacktestTrade` 加 `exit_reason`(默认空串,老构造零扰动)、`exits.py` 加 `ExitManager`、`engine.py` 把检查插进循环(history 追加之后、策略之前——信号函数与策略看同一份含当根的 history)。

### 评审修的一轮(双轴报告之后)

Spec 轴:AC1/AC2 覆盖核对无缺口。Standards/实现轴修了 6 处:

1. **exits.py 模块头引错节号**(研报告「§3.6」)→ §3.5(check_exit 在关键抽象表);
2. **risk.py 去重注记引错节号**(「§6.5」)→ §3.6;
3. **ExitConfig docstring「0 = 该项停用」以偏概全** → 只有移动止损/超时把 0 当停用;止损/止盈给 0 是「一到 0% 就出场」的极端配置,不是关掉(参照物语义照抄,但文档必须说清);
4. **MaxDrawdownRule 的 `_peak` 跨 run 保留无警示** → docstring 补注:峰值活在规则实例里,不随 `engine.run` 重置,确定性重跑要每次新构规则集(参照物同病,判代码不修、文档必须修);
5. **测试文件残留 TDD 过程语言**(「在下一个切片」)+ 未用导入 `T3` + 分裂的 import 行 → 清理;
6. **exits.py 模块头「集成在 engine.py」措辞误导** → ExitManager 本体在 exits.py,接线在 engine.py。

**判不修的五条**:`patch_threshold`/`RiskThresholdPatchError`(参照物给 LLM 阈值补丁留的口子,归课 36 LLM 接线,非本票 AC);SHORT 方向出场(事件引擎记账层禁负持仓,归课 10/11 滚动引擎);五规则出厂预设工厂(非 AC,M1 课自己配);拒单文案里 Decimal 尾零(`1.500%`——断言按子串设计,格式化收敛是过度工程);MaxPositionRule 会拦下「本将被记账层拒的超卖」(参照物同构的双层防线,拦下是更早、更可读的拒绝)。

## 关键决策与出处

- **rule_id 逐字照抄参照物**:运行时契约,课 06 findings 层按 id 去重依赖它(研报 §3.6);包括沿用名不副实的 `MAX_DAILY_LOSS_PCT`(名字说日损、实现是峰值回撤)——同构优先于命名洁癖。
- **拒单理由中文**:ADR-0005(参照物是英文,此处是文案层的有意分歧);测试逐字/子串断言锁死。
- **阈值必须是 Decimal,构造点 TypeError**:参照物把 float 阈值静默 `Decimal(str(...))` 转换(潜在泄漏);我们拒——课 03 评审修④「float 拦在构造口」的同一条边界,从 bps 延伸到全部阈值。
- **单位照抄参照物的不一致**:风控阈值是分数(`0.05` = 5%),出场阈值是百分比(`5` = 5%)——参照物两处本就不同(研报 §3.5 对照可证),同构复现优先,课文档点破。
- **出场优先级:移动止损 → 止损 → 止盈 → 超时 → 反转**:参照物 `check_exit` 原序,有测试冻结。
- **判定里不扣费**:参照物 net_pnl 里减 commission/slippage;我们的成本已由费/滑点模型体现在成交价上,判定里再扣 = 双重计费。判定只回答「该不该出、为什么」。
- **sig_score=None 的语义**:参照物总有 float 信号分;事件引擎的策略未必给信号,None = 反转分支跳过(而非把 0 当信号)——`check_exit` 纯函数保持参照物形状,引擎侧由 `signal_fn` 是否存在把关。
- **只做多**:事件引擎 `Portfolio` 禁负持仓(课 03「持仓不足」拒单),出场逻辑无 SHORT 分支;空头归滚动引擎课。
- **出场从次根生效**:入场当根跳过检查(参照物由循环顺序天然保证,事件引擎的结算成交可能与出场检查同根,显式判 `bar_idx == entry_idx`);呼应课 03「决策根与结算根分离」。
- **出场单过同一道风控闸**:平仓也走 `_submit` 全流程——紧急停止连出场也拦(这正是 kill switch 的语义),被拦则下一根重试。
- **`RiskGate` 改名**:协议让名给参照物同名的 `RiskManager` 组合器;改名前 grep 全仓确认无人按名导入。
- **`exit_reason` 只渲染在平仓成交行尾**:老格式零扰动;缝 2 的稳定渲染(课 03 AC1)延续。

## 踩过的坑

- **导入面也是切片**(刀 1 的意外红)。测试文件头 `from … import` 五个规则名,本刀只实现两个 → 收集即炸,红不能归因于实现。修法:导入清单与切片同步生长。更一般地:**红的原因要能唯一指向本刀的改动**,否则红失去了「实现错了」的证词资格。
- **隔离一条出场路径,把别的阈值放到够不到,而不是 mock 引擎**。测试里 `FAR_AWAY = {stop_loss_pct: 50, take_profit_pct: 500}`——想只测移动止损,就把止损/止盈推到教学场景价格永远够不着的地方。mock 掉引擎部件测的是「部件被 mock 成的样子」;真实引擎 + 够不到的阈值测的是「这条路径在真机器上唯一被触发」。
- **两套单位并存**。同一个仓库里 `Decimal("0.05")`(风控,分数)与 `Decimal("5")`(出场,百分比)都是「5%」——照抄参照物的代价,docstring 与本课各自声明单位。给后来者:读到 `_pct` 字段先查它住在哪个模块。
- **「0 = 停用」不是普适约定**。参照物里 trailing/超时用 0 当关扳,止损/止盈的 0 却是 hair-trigger。文档写「0 = 该项停用」时被评审抓住——概括任何约定前,逐字段对一遍源码。
- **引用要对账目录**。研报引用写错两处节号(§6.5 应为 §3.6、§3.6 应为 §3.5),评审时对着报告标题树才抓出来。来源卡纪律:引文先对目录,再对正文。

## 验收练习

```bash
# 练习 1(AC1:五条规则各至少一条触发测试,拦截不产生成交):
python -m pytest tests/test_strategy_engine_risk_rules.py -q
# 预期输出:15 passed(五规则触发 + 短路契约 + 放行路径 + float 边界)

# 练习 2(AC2:五个出场原因各至少一条路径测试并断言中文文案):
python -m pytest tests/test_strategy_engine_exits.py -q
# 预期输出:18 passed(纯函数判定/优先级 + 引擎级五路径 + 次根生效 + 风控拦出场)

# 练习 3(亲眼看一次风控拦截——中文理由 + rule_id,零成交):
PYTHONPATH="src;tests" python -c "
from decimal import Decimal
from engine_testkit import SYMBOL, TF, T0, T1, make_candle
from strategy_engine.backtest.engine import BacktestEngine
from strategy_engine.backtest.risk import MaxPositionRule, RiskManager
def strategy(ctx, candle):
    return ctx.order_intent('buy', 60) if len(ctx.history) == 1 else None
engine = BacktestEngine(strategy_fn=strategy,
                        risk_manager=RiskManager([MaxPositionRule(max_notional_usd=Decimal('5000'))]))
r = engine.run([make_candle(T0, '100'), make_candle(T1, '100')], SYMBOL, TF)
print('trades:', len(r.trades))
for x in r.risk_rejections:
    print(x.rule_id, '|', x.reason)
"
# 预期输出(第 2 行的数字手算:成交后名义 = 60 × 100 = 6000 > 5000):
# trades: 0
# MAX_POSITION_PCT | 成交后名义价值 6000 超过上限 5000(0 + 60 = 60 × 100)

# 练习 4(亲眼看一次出场——render_result 的 trade 行尾带 exit=止损):
PYTHONPATH="src;tests" python -c "
from decimal import Decimal
from engine_testkit import SYMBOL, TF, T0, T1, make_candle
from strategy_engine.backtest.engine import BacktestEngine
from strategy_engine.backtest.exits import ExitConfig
from strategy_engine.backtest.models import render_result
def strategy(ctx, candle):
    return ctx.order_intent('buy', 10) if len(ctx.history) == 1 else None
engine = BacktestEngine(strategy_fn=strategy, exit_config=ExitConfig(stop_loss_pct=Decimal('3')))
print(render_result(engine.run([make_candle(T0, '100'), make_candle(T1, '94')], SYMBOL, TF)))
"
# 预期输出(trade 第 2 行:94 较入场 100 浮亏 6% ≥ 3% → 止损;期末权益 9000 + 940 = 9940):
# trades 2
# trade 2025-03-03T00:00:00 QUANT-DEMO/USDT buy qty=10 price=100 fee=0 realized=0
# trade 2025-03-04T00:00:00 QUANT-DEMO/USDT sell qty=10 price=94 fee=0 realized=-60 exit=止损
# equity_curve 2
# equity 2025-03-03T00:00:00 10000
# equity 2025-03-04T00:00:00 9940
# fill_rejections 0
# risk_rejections 0

# 练习 5(机器验收,全量):
python verify.py
# 预期输出:[PASS] 必需文件清单、[PASS] 教学样本数据集、
#   [PASS] 全量 pytest — 107 passed、两项显式 [SKIPPED,校验通过]
```

## 下节课预告

课 05:M1 教学回测 runner——双均线策略读教学样本过本课的引擎,与买入持有对比,指标冻结断言,回测后风险 findings 按 rule_id 与本课的运行时拦截去重(票 #6,里程碑 M1 的第一块)。
