# 课 02:合成价格生成器 + 来源卡 + manifest 格式(票 #3)

> 上一课结束时:跑道铺好了——verify 机器验收全绿、端口与配置层就位,但仓库没有任何量化能力,也没有一行数据。
> 本课结束时:`data/teaching_sample/` 出现第一个数据集——381 个工作日的合成日线、一份虚构资产档案带 3 张来源卡、一份 sha256 manifest;`python3 -m data.generator` 重跑逐字节一致,篡改任何数据文件都会被 verify 点名 FAIL。

## 本课目标

后面所有课(M1 教学回测、滚动引擎、审计、投资门)都要吃同一份行情数据。这份数据从哪来?参照物的答案是:**教学样本 100% 合成**——闭式三角函数公式生成,确定性可复现(研报 §6.8),真实数据只出现在投资门且刻意冻结。本课学这套数据工程的三件套:

1. **生成器**——固定种子闭式公式,规模与参照物同构(381 个工作日),重跑逐字节一致。
2. **资产档案 + 来源卡**——虚构教学资产的「户口本」,附 3 张带日期/标题/证据的来源卡:研究结论从此有引用依据。
3. **manifest**——本项目数据工程的固定格式(ADR-0004):数据文件旁一律放 `manifest.json`,记 `source`/`generated_at`/每文件 sha256。此后投资门冻结数据集(课 19)、dashboard 台账(课 24)都长这个形。

## 动手前的三个问题

1. 既然是合成数据,为什么还要 sha256 manifest?合成器都能重跑,谁还篡改得了它?(提示:manifest 锁的不是「能不能再生」,而是「仓里这份」与「公式产的那份」是不是同一份——手改一个数字,哪道检查会叫?)
2. 「确定性」有几种来源?参照物的生成器**连种子都没有**(纯闭式公式),我们的票文却要求「固定种子」——种子在哪里是必要的?
3. `generated_at` 如果用「写文件的时刻」,会砸坏哪条验收标准?一个钉死的时间戳,诚实吗?

(答案都在下文。)

## 核心概念

- **教学样本**——合成价格序列(自写生成器,固定种子,确定性),对应参照物 `data/prices.csv` 的角色;**禁止拷贝参照物的数据文件**(CONTEXT.md 词汇表)。本课落成 `data/teaching_sample/`。
- **manifest 合同**——数据集目录的指纹台账:`source`/`generated_at`/`files`(每文件 sha256),这是项目固定格式(ADR-0004)。校验函数重算每个摘要,分歧按文件名逐条报告。
- **来源卡**——研究结论的引用依据(dated 事实卡):`id`/`date`/`title`/`evidence`,结构被契约测试冻结(CONTEXT.md 词汇表)。
- **确定性 = 结构 + 种子**——闭式公式部分天生确定(无时钟、无随机源);种子随机项的确定性靠把种子钉成常量。两者缺一,「重跑逐字节一致」就破。
- **铸造(mint)**——生成 CSV + 刷新 manifest 的写入动作;与之相对,**审计**是 verify 缝的独立重算。写入者自己查自己,查出来的永远是绿的(见「踩过的坑」)。
- **缝(seam)**——本课数据合同落在两条缝上:数据解析缝的契约测试面(票 #1 明文豁免「manifest sha256 用字符串/哈希断言锁死」),与 verify 缝(票 #3 写的「缝 6(数据合同)」——数据合同第一次被 verify 观察)。

## 一起实现:红绿实录

本课切了三刀(每刀对一条验收标准),双轴评审后修了一轮——其中一刀的测试预期连红两次,红出了本课最值钱的教训。

### 刀 1:生成器确定性(AC1)

- **红**:`test_regeneration_is_byte_identical` + 形状契约(381 行、仅工作日、两位小数、日期严格递增)+ 种子活性(换种子必须换输出)。`ModuleNotFoundError: No module named 'data'`。
- **断言来自哪里**:AC1 原文;381/仅工作日来自研报 §6.8(参照物 381 行、仅工作日);种子活性是自加的防守——**死种子(常量被无视)会让 AC1 空过**:重跑当然一致,因为输出根本不依赖种子。
- **绿**:`src/data/generator.py`——自己的公式(基线 `42.0 + i*0.028` + 三个正弦周期 + 一个 `max(0,·)²` 回撤项 + `random.Random(SEED)` 冲击项),窗口 2025-03-03 → 2026-08-17,实测价格区间 40.59–55.38。学的是参照物 `generate_prices_sample.py` 的思路,常数全是自己的。

### 刀 2:manifest 合同(AC2)

- **红**:五条——干净目录零问题;篡改被点名;缺失被点名;manifest 本身缺失是问题;manifest 非法 JSON 是问题。`ImportError: cannot import name 'build_manifest'`。
- **断言来自哪里**:AC2(「对被篡改文件报错」);「按文件名报告」来自票 #1 契约测试条款;中文问题串来自 ADR-0005(用户可见文案)。
- **绿**:`src/data/manifest.py`:`sha256_file`/`build_manifest`/`write_manifest`/`verify_manifest`,返回中文问题列表(空列表 = 全部一致)。

### 刀 3:铸造 + 资产档案 + 来源卡(AC3)

- **红**:档案结构冻结(顶层键集合、快照键集合逐一相等)、3 张卡 `S1/S2/S3` 且每张键集合恰好 `{id,date,title,evidence}`、档案数字与公式输出交叉一致(`sample_days`/`first_close`/`last_close`)、提交的三件套内部自洽。`data/teaching_sample/` 整个不存在。
- **绿**:手写 `company.json`(虚构资产 `QUANT-DEMO/USDT`;S1 记生成方式,S2 记复现学习对象,S3 记假设与边界——「不进入实盘执行」),跑 `python3 -m data.generator` 铸出 `prices.csv` + `manifest.json` 入库。**收尾亲手跑了一遍 AC1 的字面验收**:铸进两个 /tmp 目录,`diff -r` 为零。

### 评审修的一轮(双轴报告之后)

Standards 轴抓到死代码,Spec 轴抓到 AC1 测弱——处置如下:

1. **`verify_manifest` 没有生产调用方**(撞课 01「`load_env()` 死代码」先例)。修法同课 01:接线,而非删功能——`verify.py` 新增 `check_teaching_sample`,数据合同从此在 verify 缝(缝 6)被观察。这正好把票文「缝 6(数据合同)」坐实:本课的合同测试面本来就是票 #1 豁免的,但「校验函数被谁调用」必须在缝上。
2. **AC1 原来只测了纯函数两次**——`prices_csv_text()` 调两遍挡不住铸造路径上的墙钟。补 `test_mint_reruns_are_byte_identical`:两个目录各铸一次、原地再铸一次,三个文件逐字节比对。
3. **`main` 的铸后自检是同源重算,测试预期连红两次**。第一次红:我篡改 `prices.csv` 后调 `main` 期望 FAIL,结果 `main` 先铸造(把篡改**修复**了)再校验,返回 0;第二次红:改篡改 `company.json`,结果 manifest 会把它的新摘要一起刷新,还是 0。看清结构:`main` 里那段铸后 [FAIL] 分支**不可达**——manifest 刚从同一批字节建出来,重算必绿。修法:删掉假安全网,`main` 缩成纯铸造(失败路径只剩「手写档案缺失」→ 退出码 1),审计归 verify.py。
4. **manifest 形制冻结测试补上**(Standards 轴:裸 dict 流转)。选了行为测试(键集合 + 64 位十六进制摘要),没上 TypedDict——仓库没有类型检查工具链,类型注解零运行时保护,行为测试才是本项目计量单位。
5. 杂项:测试助手 `mint_dataset` 改名 `mint_tmp_dataset`(与生产 `mint_sample` 区分);提交态 manifest 的 `source` 补断言;`mint_sample` docstring 写明「档案由人手写,本模块永不写它」;`main` 的文件计数从返回的 manifest 派生(原来硬编码「2 个」)。

**判不修的三条,理由如下**:`weekday < 5` 断言保留——它是工件级契约(研报 §6.8「仅工作日」),断在输出字节上,独立事实源不是代码;manifest 覆盖手写档案 + 铸造强制档案先存在——票文没要求,但**不被 manifest 覆盖的文件正是篡改最容易藏身的地方**(ADR-0004「数据文件旁一律放 manifest」);校验函数返回问题列表而非抛异常——两个调用方(CLI、verify)各自把它变成显式失败,且列表能一次收集**全部**被篡改文件,抛异常会在第一个就短路。

## 关键决策与出处

- **自写闭式公式 + 固定种子,不拷贝参照物任何数据文件**:ADR-0004 #1;参照物做法研报 §6.8(其 `prices.csv` 100% 合成)。Spec 轴实测:两份 `prices.csv`/`company.json` 的 sha256 互异,公式、窗口、符号名均为自写。
- **规模同构:381 个工作日**:研报 §6.8(参照物样本 381 行、仅工作日)。
- **manifest 固定格式 `source`/`generated_at`/`files{sha256}`**:ADR-0004(「数据文件旁一律放 manifest——成为本项目数据工程的固定格式」)+ 票 #3;与参照物投资门 manifest 同型,但每个文件带 sha256(票文明文要求)。
- **`generated_at` 钉死为数据集版本身份,不写时钟**:AC1(逐字节一致)禁墙钟;公式或窗口变更时人工 bump,写入时永不刷新。这是合成数据与抓取数据的诚实差异——参照物的 `generated_at` 是真实抓取时刻,我们的「生成时刻」只对版本有意义。
- **种子必须被证明是活的**:票 #1 Testing Decisions(「统计结论靠固定种子做数值级确定性断言」)——后续审计课全押在种子确定性上,本课先立「死种子会被抓住」的先例。
- **手写资产档案 + 3 张来源卡、结构冻结**:研报 §6.8(参照物 `company.json` 手写,S1–S3 含 `date`/`title`/`evidence`);叙事内容归数据、不归代码。
- **CLI 修复 / verify 审计分工**:ADR-0006(verify = 交付物完整性的机器验收);写入者不审计自己。
- **中文用户可见文案(CLI 输出、manifest 问题串、档案内容)/ 英文标识符与注释**:ADR-0005。

## 踩过的坑

- **同源重算是假安全网**:「写完立刻校验」看着稳健,但 manifest 由同一批字节建出,重算永远绿——它检查的是「我写的函数没坏」,不是「数据没被动过」。真审计必须独立于写入路径(verify.py 读盘重算)。这个坑是我自己写的测试连红两次才看清的:测试没错,是设计有死分支。
- **「重跑两次」有强弱两读**:纯函数调两遍(弱,挡不住 I/O 路径的时钟)vs 铸造两目录逐字节 diff(强)。票文要的是后者,第一版只给了前者——Spec 轴抓的。
- **修复式写入会吞掉篡改**:`main` 先铸造后校验,意味着它「拥有」的文件被篡改后会被静默修复。这不是 bug 是分工,但必须写下来,否则读者会误以为 CLI 是校验工具。
- **钉死时间戳的诚实性**:第一反应是「`generated_at` 该用 `datetime.now()`」——那 AC1 立刻碎。钉死不是撒谎:对合成数据,有意义的不是「哪秒写的」,而是「哪一版公式铸的」。

## 验收练习

```bash
# 练习 1:机器验收(verify 三项实跑全 PASS,含本课新增的教学样本检查)
python3 verify.py
# 预期输出(逐行):
# [PASS] 必需文件清单 — 7 个必需文件齐全
# [SKIPPED] 研究报告安全文案 — 研究报告尚未组装(课 06 落地后启用)
# [SKIPPED] 冻结数据集校验 — 冻结数据集尚未抓取(课 19 落地后启用)
# [PASS] 教学样本数据集 — manifest.json sha256 全部一致
# [PASS] 全量 pytest — 34 passed in 0.1s
# 已跑 3 项(通过 3、失败 0),跳过 2 项。
# Quant-Sandbox 校验通过。

# 练习 2:重铸(AC1:逐字节一致;顺带看 CLI 输出)
cp -r data/teaching_sample /tmp/mint_a && cp -r data/teaching_sample /tmp/mint_b
PYTHONPATH=src python3 -c "from pathlib import Path; from data.generator import mint_sample; mint_sample(Path('/tmp/mint_a')); mint_sample(Path('/tmp/mint_b'))"
diff -r /tmp/mint_a /tmp/mint_b && diff -r /tmp/mint_a data/teaching_sample && echo 逐字节一致
# 预期输出:逐字节一致(diff 无任何差异行)

# 练习 3:篡改检测(AC2:被点名的报错)
cp -r data/teaching_sample /tmp/tamper && printf '2020-01-01,1.00\n' >> /tmp/tamper/prices.csv
PYTHONPATH=src python3 -c "from pathlib import Path; from data.manifest import verify_manifest; print(*verify_manifest(Path('/tmp/tamper')), sep='\n')"
# 预期输出:sha256 不一致(文件在入库后被改动?):prices.csv

# 练习 4:篡改连 verify 都逃不掉(改完务必还原!)
printf 'x' >> data/teaching_sample/prices.csv && python3 verify.py; git checkout data/teaching_sample/prices.csv
# 预期:verify 输出 [FAIL] 教学样本数据集 — … prices.csv,退出码 1;还原后恢复全绿

# 练习 5:来源卡与全量测试(AC3)
python3 -m pytest tests/test_data_company.py -q
# 预期输出:5 passed(结构冻结、3 张卡、档案数字与公式交叉一致、三件套自洽)
```

## 下节课预告

课 03:事件引擎核心——`QUANT-DEMO/USDT` 的 381 根日线终于有消费者了:Decimal 订单意图、挂单/限价/止损语义,事件引擎的第一块骨头(票 #4)。
