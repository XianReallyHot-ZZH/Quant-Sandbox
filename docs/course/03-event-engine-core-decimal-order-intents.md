# 课 03:事件引擎核心(Decimal 订单意图)(票 #4)

> 上一课结束时:仓库有了第一个数据集——381 根合成日线 + 虚构资产档案 + sha256 manifest,但没有任何东西消费它。
> 本课结束时:`src/strategy_engine/backtest/` 立起第一台回测机——策略提交 Decimal 订单意图,引擎按 bar 闭环结算挂单/限价/止损,产出成交轨迹与逐 bar 权益曲线;同一输入逐字节同输出,记账层从构造口到结果树无一处 float。

## 本课目标

九大核心功能的第一块骨头:回测。参照物有两套引擎(研报 §3.6),ADR-0003 决定双引擎都做、先做事件引擎——它承担 M1 教学回测与 DSL 编译落点。本课把它的核心五件按票文落地:

1. **订单意图值对象**——冻结的 `OrderIntent`:side/type/qty + 可选 price/stop_price + time_in_force。策略只声明「想要什么」。
2. **bar 闭环**——每根 K 线固定次序:结算挂单簿 → 喂策略 → 提交意图 → 记权益;GTC 限价/止损在挂单簿里等未来的根。
3. **成交模型(含最小成本)**——FeeModel/SlippageModel 两个 Protocol,零成本教学默认 + bps 费/滑点。
4. **组合记账**——现金/持仓/均价/已实现盈亏/权益,全 Decimal。
5. **确定性**——同一输入逐字节同输出(AC1),为此给结果配了稳定文本形 `render_result`。

## 动手前的三个问题

1. 订单为什么是「意图」而不是「成交」?策略函数每根 bar 至多返回一个冻结值对象——谁决定它是否、何时、以什么价变成成交?
2. GTC 限价单提交的那一根,最低价已经触及限价了,为什么最早也要下一根才成交?
3. 「记账层无 float」为什么要把 float 拦在构造口(TypeError),而不是让它迟爆在第一笔算术上?

(答案都在下文。)

## 核心概念

- **事件引擎**(词汇表)——`strategy_engine` 式:Decimal 订单意图、挂单/限价/止损语义、风控前置(ADR-0003:承担 M1 教学回测与 DSL 编译落点)。本课落地 `protocol/candles/portfolio/models/engine` 五模块。
- **订单意图(OrderIntent)**——冻结值对象,是「想下单」的分类学:风控拿它做前置检查,成交模型拿它算费,记账拿它入账。
- **bar 闭环**——`run()` 的循环骨架;决策根与结算根分离是它的关键性质(见刀 3)。
- **挂单簿(pending book)**——GTC 限价/止损的栖息地,`pending_orders_snapshot()` 可观察;风控在触发当根**复查**(不是提交时一次放行)。
- **成交模型**——`FeeModel.calc(intent, fill_price)` 与 `SlippageModel.fill_price(intent, candle)` 两个 Protocol;零成本是教学默认,bps 是最小成本(研报 §3.6 引擎同款)。
- **组合记账(Portfolio)**——现金、持仓(`Position`:数量/均价/已实现)、逐 bar 权益;无价时按成本价(均价)计。
- **缝 2(引擎结果)**——`BacktestResult`:trades / equity_curve / risk_rejections / fill_rejections。本课一切断言落在这个面上(票文指定)。
- **render_result**——结果的稳定文本形,AC1 的 diff 单位;机器面工件,token 是英文——一旦进研究报告即成用户可见文案,转中文契约(ADR-0005 的边界在「用户可见」)。

## 一起实现:红绿实录

本课切了五刀(记账 → market 主循环 → 限价/止损 → 成本与拒单 → 确定性),五刀全绿后按双轴评审又修了一轮。**实现侧五刀全部一次绿;本会话三次意外红,全红在测试侧**——这是本课最意外的实录,也是「学习优先」在工作流上的样子:动手前精读了参照物 638 行引擎源码,实现照搬语义不发明。

### 刀 1:Portfolio 记账层(手算样例,AC3)

- **红**:`ModuleNotFoundError`(模块尚不存在,8 条测试收集失败)。
- **断言来自哪里**:手算——10000 起步,买 5@100 无费再买 5@104 费 2 → 均价 102、现金 8978;满仓卖 10@110 费 1.10 → 已实现 78.90、现金 10076.90;部分卖出均价不动;无价按成本计;AC3「无 float」→ 现金/均价/已实现/权益全 `isinstance(…, Decimal)`;中文错误文案 ADR-0005。
- **绿**:实现一次写对,但**测试连红两次,两次都是我的手算错**:9500−520−2 写成 4298(实为 8978);(110−102)×10−1.10 写成 76.90(实为 78.90)。救场的是「表达式重算 + 手算字面量」双断言——两者互相监督,一矛盾即暴露。

### 刀 2:引擎主循环 + market 路径

- **红**:`ImportError`(candles/engine/models 尚不存在)。
- **断言来自哪里**:手算样例 #1(零成本):买 10@100 卖 10@110 → 已实现 100、终值权益 10100、权益曲线逐点 [(T0,10000),(T1,10100)];循环次序——bar1 的成交 bar2 的 `ctx.position()` 可见、history 含当根;`order_intent` 辅助把数字经 `str→Decimal`(float 永不入账);空 K 线中文 `ValueError`。
- **绿**:一次过。非 market 类型暂以 `raise 暂不支持的订单类型` 占位——刀 3 的替换点。

### 刀 3:限价/止损路径(AC2)

- **红**:8 条测试全红(引擎尚无挂单机制)。
- **断言来自哪里**:AC2 原文双路径;手算样例 #2(限价买 5@95,94–97 根按 **95**(非收盘)成交,现金 9525、权益 9525+5×96=10005)与 #3(bar1 买 10@100,bar2 挂卖止损 @95 未触发,bar3 low 94 触发按收盘 96 成交,已实现 (96−100)×10=−40);「GTC 提交当根不结算」「买入止损看 high」来自参照物 engine 语义(研报 §3.6);挂单簿可观察(`pending_orders_snapshot`)与重跑不串味是自加防守。
- **绿**:一次过。三个问题的第二个在此:GTC 当根不结算,因为策略是看完整根才决策的——若同根又按同根区间成交,决策与成交挤在同一根里,是轻度前视。参照物的「决策根与结算根分离」就是这个意思。

### 刀 4:成本模型 + 显式拒单 + 风控缝

- **红**:`ImportError: ConstantBpsFee`。
- **断言来自哪里**:手算样例 #4(taker 10bps:买 10@100 费 1.00、卖 10@110 费 1.10、已实现 98.90、终值 10097.90;maker 5bps:475×5/10000=0.2375;滑点 5bps:买 100×1.0005=100.05、卖 99.95);「拒单显式入结果」是本课立的新改进(CONTEXT 改进③):参照物把现金不足的成交静默吞掉,我们记进 `fill_rejections`——ADR-0006「不静默跳过」的哲学从 verify 延伸到引擎;风控缝用 stub(真五规则归 #5)。
- **绿**:实现一次过,但**有一条测试自相矛盾红了一次**:stub 设计成「首根放行、其后全拦」,断言却按「全拦」写(零成交)。拆成 `AlwaysBlock`/`AllowOnlyFirstBar` 两个 stub 后绿。

### 刀 5:确定性渲染(AC1)+ 无 float 走查(AC3b)

- **红**:`ImportError: render_result`。
- **断言来自哪里**:AC1 原文;**场景前提测试**(该场景必须真产生 1 成交 + 2 记账拒单 + 4 权益点,否则逐字节一致是空洞的)与负对照(换一个收盘价,渲染必须变);无 float 走查 = 递归遍历 `BacktestResult` 数据类树,任何位置不许出现 `float` 实例。
- **绿**:一次过。场景:bar1 市价买 10;bar2 挂限价买 100@95;bar3 挂卖止损 15@91;bar4(low 89)限价触及但需 9504.75 > 现金 8999(拒)、止损触发但卖 15 > 持有 10(拒)。收尾把渲染跑两遍 diff——**跨进程也逐字节一致**(验收练习 1 即此命令)。

### 评审修的一轮(双轴报告之后)

Standards 轴:0 硬违规 + 8 判断题;Spec 轴:2 部分 + 2 存疑 + 1 自相矛盾。修了 7 处:

1. **四个测试文件的 `make_candle` + 常量逐字节重复**(Standards:Duplicated Code)→ 抽 `tests/engine_testkit.py`。
2. **taker 判定用字符串集合 `{"market","stop","stop_limit"}` 再编码 OrderType**(Standards:新增类型会静默漏判)→ `protocol.TAKER_ORDER_TYPES` frozenset,枚举单源。
3. **`risk_manager: object | None` 的契约只活在行尾注释**(Standards:与同包 FeeModel/SlippageModel Protocol 不一致)→ engine 内 `RiskManager` Protocol + `RiskCheck` 值对象,#5 的规则照此实现。
4. **float 能过构造口、迟爆 TypeError**(Spec:AC3b 的走查只盖结果树)→ `initial_cash`/`maker_bps`/`taker_bps`/`bps` 在 `__post_init__` 中文 TypeError。三个问题的第三个:迟爆只证明「迟早会炸」,且炸点离犯错点十万八千里;入口拒绝保证 float **从未入账**,报错直指写错的那一行。
5. **stop_limit 是全引擎唯一无测试的路径**(Spec)→ 补测试冻结「触发看 stop_price、按收盘成交、限价腿不建模」(参照物同款简化)。
6. **滑点测试三根 K 线 T0,T1,T1**(Spec:重复时间戳)→ 改 T2。
7. **缺价限价单挂一根后无声消失**(Spec:与改进③的理由自相矛盾)→ 提交即显式 `fill_rejections`(「限价单缺少价格」/「止损单缺少触发价」),结算侧两个死分支随之删除。此刀又红了一次 `NameError: pytest`——guards 文件原本不用 pytest,新断言要用。第四次红在测试侧。

**判不修的九条**:`equity_curve` 改名(ADR-0003 管的是 sharpe 类**口径字段**,逐 bar 轨迹不是口径;镜像参照物命名,对账桥课再议);`render_result` 英文 token(机器面工件,ADR-0005 边界在「用户可见」);`_RunState` 收拢私有方法的五元参数(参照物同构的私有管道);`side == BUY` 三处多态化(三处问的是三个不同问题:可成交性/触发/滑点方向);`order_intent` 的 `type` 遮蔽内建(参照物 API 同名,函数内不用内建 `type`,无害);models.py 兼营成本/结果/渲染(参照物同构);`ZeroFee` 声明为 dataclass(参照物同构,换来可作引擎字段统一配置);挂单触发根资金不足即出簿、现金回补不再尝试(参照物行为,经改进③已可见);跳空穿越按限价而非更优开盘价成交(参照物同款,保守方向)。

## 关键决策与出处

- **双引擎先做事件引擎,承担 M1 与 DSL 落点**:ADR-0003 #1;研报 §3.6。
- **订单=冻结值对象、闭环次序(结算→喂→提交→记权益)、GTC 提交当根不结算、风控在触发当根复查**:参照物 `strategy_engine/backtest/engine.py` 同构(研报 §3.5 StrategyFn 接口、§3.6);`StrategyFn = Callable[[StrategyContext, Candle], OrderIntent | None]` 逐字同形。
- **最小成本 = maker/taker bps + bps 滑点**:票文「含最小成本」;费档判定收敛到 `TAKER_ORDER_TYPES`(评审修②);**bps 入参 Decimal 化**是对参照物 `Decimal(float_bps)` 潜在泄漏的堵法(评审修④)。
- **fill_rejections 显式化(改进③)+ 缺价意图显式拒**:本课新增,CONTEXT「有意改进」清单两处→三处;ADR-0006。
- **风控只留缝**:CONTEXT 词汇「风控前置」;五条 RiskRule 与出场逻辑归票 #5,`RiskManager` Protocol 是接口预埋。
- **中文错误/拒单文案、英文标识符与注释**:ADR-0005(参照物引擎错误文案是英文——此处是文案层的有意分歧,ADR-0005 明确用户可见文案以中文为准)。
- **指标(sharpe/sortino/win_rate/max_drawdown)不在本课**:归课 05 M1 runner(票 #6);ADR-0003 的口径纪律(逐 bar 权益收益 vs 逐笔 PnL)自彼时起算——本课结果树因此能整体无 float,也是 AC3b 走查能一刀切的原因。
- **AC1 的 diff 单位是 render_result**:只依赖有序列表与值对象——无墙钟、无随机源、无集合迭代(课 02「确定性=结构+种子」的结构侧);负对照防空洞(课 01「死种子」先例)。

## 踩过的坑

- **手算样例会算错**(刀 1 连错两次)。独立事实源不是免检金牌:9500−520−2 能笔误成 4298。修法不是「下次算仔细点」,而是让**表达式重算与手算字面量同时在场**——它们来自两条不同的计算路径,矛盾即其一有错。本课两次都被这对断言当场抓住。
- **stub 的行为与断言各说各话**(刀 4)。stub 写「首根放行」,断言写「零成交」——红的时候先怀疑测试:描述 stub 语义的那行注释,和用它断言世界的那行代码,是不是同一件事。
- **「值相等」≠「字面相等」**:`Decimal("1") == Decimal("1.00")` 为真——渲染输出 `fee=1` 而测试断言 `Decimal("1.00")` 也绿,靠的是数值相等;AC1 的逐字节一致性靠的是「同输入→同运算→同指数」,不是格式化对齐。若哪天渲染输出变了,先查是不是运算路径变了而不是「精度丢了」。
- **无名中依赖测试文件的私有顺序**:断言只写行为(哪个 ts、什么价、多少已实现),不写行号不写内部结构——评审重构抽 `engine_testkit` 时,39 条引擎测试无一因搬家而改断言。

## 验收练习

```bash
# 练习 1(AC1,跨进程逐字节):同一场景渲染两遍,diff 必须为零
render() { PYTHONPATH=src:tests python3 -c "
from strategy_engine.backtest.models import render_result
from test_strategy_engine_determinism import SCENARIO_CANDLES, SYMBOL, TF, make_engine
import sys
sys.stdout.write(render_result(make_engine().run(SCENARIO_CANDLES, SYMBOL, TF)))"; }
render > /tmp/run_a.txt && render > /tmp/run_b.txt && diff /tmp/run_a.txt /tmp/run_b.txt && echo 跨进程逐字节一致
# 预期输出:跨进程逐字节一致
head -6 /tmp/run_a.txt
# 预期输出(逐行):
# trades 1
# trade 2025-03-03T00:00:00 QUANT-DEMO/USDT buy qty=10 price=100 fee=1 realized=0
# equity_curve 4
# equity 2025-03-03T00:00:00 9999
# equity 2025-03-04T00:00:00 10099
# equity 2025-03-05T00:00:00 10049

# 练习 2(AC2,限价双路径 + 全部订单语义):
python3 -m pytest tests/test_strategy_engine_orders.py -q
# 预期输出:9 passed(限价成交/不成交、当根不结算、IOC 或死、止损手算、
#   未触发留簿、买入止损看 high、重跑干净、stop_limit 冻结)

# 练习 3(AC3a,手算样例与引擎一致):
python3 -m pytest tests/test_strategy_engine_portfolio.py tests/test_strategy_engine_guards.py -q
# 预期输出:19 passed(均价/已实现/权益手算、taker/maker/bps 手算、
#   滑点手算、中文文案)

# 练习 4(AC3b,float 拦在构造口):
PYTHONPATH=src python3 -c "
from strategy_engine.backtest.models import ConstantBpsFee
ConstantBpsFee(maker_bps=0.5)"
# 预期输出(末行):TypeError: maker_bps 必须是 Decimal(拒绝 float 入账)

# 练习 5(机器验收,全量):
python3 verify.py
# 预期输出:[PASS] 必需文件清单、[PASS] 教学样本数据集、
#   [PASS] 全量 pytest — 73 passed、两项显式 [SKIPPED,校验通过]
```

## 下节课预告

课 04:五条 RiskRule 挂上本课预埋的风控缝(命中即短路、拦截不产生成交),出场判定落地——止损/止盈/移动止损/超时平仓/信号反转五类出场原因的中文文案成为运行时契约(票 #5)。
