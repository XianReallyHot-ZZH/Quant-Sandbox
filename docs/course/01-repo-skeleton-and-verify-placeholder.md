# 课 01:仓库骨架 + config/paths + pytest 接线 + verify 占位(票 #2)

> 上一课结束时:仓库只有文档——决策(CONTEXT.md、7 份 ADR)、研报、课程目录,没有一行产品代码。
> 本课结束时:`python3 verify.py` 机器验收全绿;`python3 app.py` 报出 `QuantSandbox/1.0` 身份与端口;端口默认 8766、环境变量与 `.env` 文件都能覆盖;15 个测试一条命令全绿。

## 本课目标

课程第一课是 prefactor:不写任何量化功能,先把「每课可验收」的跑道铺出来。三样东西:

1. **config/paths 层**——产品从哪个目录起、端口是多少、`.env` 怎么读。参照物把它放在 §8.6 拓扑第 1 步,理由很简单:后面所有课都要 import 它。
2. **pytest 接线**——一条命令跑全部测试,此后每张票的红绿都在这条跑道上发生。
3. **verify 占位版**——ADR-0006 的机器验收合同先立骨架:本课只实现四类检查中的「必需文件清单」和「全量 pytest」,另外两类在对应课程落地前显式打印 `SKIPPED(原因)`。这是对参照物的第一处有意改进:参照物 verify.py 在公开 checkout 上会静默跳过整块检查,「make check 通过」≠「全部检查通过」(研报 §6.3 风险 #6)。

## 动手前的三个问题

1. 为什么第一课不是回测,而是 config/paths + verify?(提示:ADR-0001 说「任何时刻停下,仓库里都是一个能跑、能 verify 的东西」——第 0 课结束时这句话靠什么成立?)
2. 一个检查被跳过时,「静默通过」和「打印 SKIPPED 及原因」差别在哪里?静默跳过会腐蚀「verify 全绿」这个信号的什么属性?
3. 参照物读 `.env` 用 `python-dotenv`,且 `try/except ImportError` 后备手写解析器(研报 §3.3)。我们直接手写解析器——零依赖换来什么、付出什么?

(答案都在下文。)

## 核心概念

- **产品根**——`app.py`/`src/`/`tests/` 所在的目录即产品根(本仓 = 仓库根,CONTEXT.md「仓库布局」行)。`src/paths.py` 用三个常量把它钉死:`PROJECT_ROOT`/`SRC_ROOT`/`DATA_DIR`。
- **缝(seam)**——测试落点的公共边界。本课程全部测试只落在六条缝上(票 #1「Testing Decisions」,已与所有者确认,不为单票新开缝):策略插件、引擎结果、统计审计、数据解析、HTTP API、verify。**能测高缝不测低缝**。本课票文只声明缝 6(verify)。
- **verify 合同**——交付物完整性的机器验收,四类检查:① 必需文件清单;② 研究报告中文安全文案字符串断言;③ 冻结数据集 manifest/sha256 校验;④ 全量 pytest(ADR-0006)。
- **SKIPPED 反静默**——被跳过的检查必须打印 `SKIPPED` 及原因;检查的目标产物一旦存在而断言未实现,必须 `FAIL`(不许装作通过)。verify 全绿从此是诚实的:要么跑了,要么明说跳了。
- **契约文案**——用户可见文案一律中文、标识符与注释一律英文(ADR-0005);文案变更 = 契约变更,必须连带测试与 verify。
- **回归锁**——落地即绿、专为「防止未来倒退」而写的测试。它与行为测试的区别:行为测试先红后绿,回归锁锁的是一条已成立的约束。

## 一起实现:红绿实录

本课切了六刀,随后按双轴评审修了一轮。如实记录:五刀的红都是「模块不存在」的收集期错误——骨架课的 red 没有戏剧性,戏剧性全在评审步。

### 刀 1:paths 布局常量

- **红**:`tests/test_paths.py` 断言 `PROJECT_ROOT` 指向仓库根(用 `pytest.ini`、`CLAUDE.md` 的存在性作独立事实源)。`ModuleNotFoundError: No module named 'paths'`。
- **断言来自哪里**:CONTEXT.md「仓库布局」行(仓库根即产品根)。
- **绿**:`pytest.ini` 写 `pythonpath = src`(pytest 接线本体),`src/paths.py` 三行常量。

### 刀 2:.env 加载器

- **红**:`load_env()` 读 key=value、去引号、后找的候选覆盖先找的、真实环境变量胜过非末位候选。`config` 包不存在。
- **断言来自哪里**:研报 §7 环境变量表——参照物 `config/env.py` 的覆盖规则(「后找到的覆盖先找到的」,local `.env` 最强),逐条镜像成测试。
- **绿**:`src/config/env.py`,纯标准库逐行解析器,不 import dotenv(ADR-0002)。

### 刀 3:端口与身份

- **红**:默认端口 8766、`QUANT_SANDBOX_PORT` 可覆盖、非整数与超范围(1–65535)要报中文 ValueError、身份串 `QuantSandbox/1.0`。五条断言全空。
- **断言来自哪里**:端口默认值与「可覆盖」来自 CONTEXT.md 全局决策表(参照物 8765 硬编码,错开一位以便同机并存对照,改进 ②);身份串来自票 #2 原文。
- **绿**:`src/config/settings.py`,`app_port()` 一个函数 + 四个常量。

### 刀 4:产品入口

- **红**:`app.main()` 应退出码 0 并打印 `QuantSandbox/1.0` 与 `8766`。`app` 模块不存在。
- **绿**:`app.py`(sys.path 引导 + `main()`),`tests/conftest.py` 把仓库根挂上 `sys.path` 让测试能 import 仓库根的入口脚本。

### 刀 5:verify 占位版(缝 6 首次亮相)

- **红**:七条断言——必需文件在仓库根 PASS、在空目录 FAIL 且列出缺失文件名;安全文案与冻结数据集在对应课程落地前 SKIPPED;格式函数明确区分「已跑 N 项 / 跳过 N 项」。
- **断言来自哪里**:票 #2 AC1(「输出明确区分已跑检查与 SKIPPED(原因)」)+ ADR-0006。
- **其中最值钱的一条**:`test_landed_artifact_without_assertion_fails_loudly`——在合成目录里放上 `src/research/report.py` 再调 `check_safety_copy`,必须 **FAIL** 而不是 SKIPPED。它把「反静默跳过」钉成了行为:课 06 研究报告落地那天,这个检查会立刻开始报警,直到字符串断言补上。
- **绿**:`verify.py`:`CheckResult` dataclass + 四个 `check_*` + `format_results`。手跑 `python3 verify.py`,AC1 当场验收:PASS/SKIPPED 各自带原因,末行汇总「已跑 2 项,跳过 2 项」。

### 刀 6:stdlib-only 回归锁(落地即绿)

唯一一刀不红:AST 扫 `src/`、`app.py`、`verify.py` 的全部 import,非 `sys.stdlib_module_names` 且非 src 下首方名即 fail。它锁的是 AC3(全程纯标准库)这条**已成立**的约束——写成先红后绿就得先故意引个第三方库,那是表演。回归锁如实以「落地即绿」入账。

### 评审修的一轮(双轴报告之后)

评审抓出四类问题,处置如下:

1. **注释语言违 ADR-0005**(注释/标识符应英文):全部模块 docstring 与注释英文化;用户可见文案(print、报错、verify 输出)保持中文。核对过参照物测试文件——确实无中文 docstring,此条按硬违例处理。
2. **两个测试落在票未声明的缝上**:`test_paths.py`(断言只是复述实现)删除;`test_config_env.py` 直接测解析器 minutiae,删除——**但它的死代码问题是真的**:`load_env()` 写完没有任何调用方,测试全绿而产品行为没变。修法是把唯一可观察的加载行为上移:`app.main()` 先 `load_env()` 再 `app_port()`,入口缝上加一条端到端测试(`.env` 文件写 `QUANT_SANDBOX_PORT="9001"` → main 打印 9001)。测试总数 22 → 15,覆盖的行为反而更硬。
3. **重复形状**:verify 两个「产物未落地 SKIPPED / 落地未实现 FAIL」检查提取成 `_deferred_check()`;根路径推导在 conftest 与回归锁里改为 `from paths import PROJECT_ROOT`(`app.py`/`verify.py` 自己的引导是入口本能,保留)。
4. **可移植性**:`PROJECT_ROOT.name == "Quant-Sandbox"` 会把 checkout 目录名焊死进测试(clone 到别的目录名就红),改为只断言身份文件存在性。

## 关键决策与出处

- **仓库根 = 产品根**:CONTEXT.md「仓库布局」行(易逆,不立 ADR)。
- **默认端口 8766 + `QUANT_SANDBOX_PORT` 覆盖**:CONTEXT.md 全局决策表改进 ②;参照物 8765 硬编码于 `app.py`(研报 §7 表)。
- **手写 .env 解析器,不引 dotenv**:ADR-0002;解析语义镜像参照物 `config/env.py`(研报 §3.3 依赖表:「可选,有纯 Python fallback」)。
- **覆盖优先级**(本课如实继承参照物,含其怪癖):默认常量 < 非末位 `.env` 候选(仅在变量未设时生效)< 真实 shell 环境变量 < 末位 local `.env`(最强)。即:开发者本机 `.env` 可以压过 shell 导出——这是参照物「local override wins」的原样语义,比较时以此为准。
- **verify 显式 SKIPPED + 产物落地即 FAIL**:ADR-0006;对参照物的有意改进 ①(研报 §8.5 #6、§6.3 风险 #6)。
- **中文用户可见文案 / 英文标识符与注释**:ADR-0005。
- **测试只落六条缝,本课只落缝 6**:票 #1「Testing Decisions」;端口单测是 AC2 的明文豁免。
- **身份串 `QuantSandbox/1.0` vs 产品名 `Quant-Sandbox`**:前者是票 #2 指定的运行时身份串(HTTP token 不含连字符的惯例),后者是 CONTEXT.md 的产品/仓库名——两个都有出处,`settings.py` 注释里并排注明。
- **骨架课 228 行产品代码,低于 ADR-0001 的 300 行下限**:如实记录,不注水——骨架课的规模由票 #2 的范围决定,为凑行数加抽象才是真违例(Speculative Generality)。

## 踩过的坑

- **测试绿 ≠ 产品对**:`load_env()` 六条测试全绿,但没有任何调用方——是评审的 Spec 轴抓出来的死代码。红绿循环只保证「测过的行为对」,不保证「测的行为被产品用到」。接线测试(.env → 端口 → 打印)才是行为真正被观察的地方。
- **目录名写进断言**:`PROJECT_ROOT.name` 断言在作者的机器上永远绿,换个 clone 目录名就红——环境相关断言要用「身份文件存在性」这类可迁移事实。
- **顺手多测了低缝**:解析器的引号/注释/覆盖 minutiae 写起来顺手,但按「能测高缝不测低缝」它们不属于任何缝。删掉时心疼了一下,换来的是测试面与产品可观察行为对齐。
- 本课五刀的红都是收集期 `ModuleNotFoundError`——顺利,如实写。骨架课的 red 本来就朴素。

## 验收练习

```bash
# 练习 1:机器验收(AC1:verify 全绿,区分已跑与 SKIPPED)
python3 verify.py
# 预期输出(逐行):
# [PASS] 必需文件清单 — 7 个必需文件齐全
# [SKIPPED] 研究报告安全文案 — 研究报告尚未组装(课 06 落地后启用)
# [SKIPPED] 冻结数据集校验 — 冻结数据集尚未抓取(课 19 落地后启用)
# [PASS] 全量 pytest — 15 passed in 0.1s
# 已跑 2 项(通过 2、失败 0),跳过 2 项。
# Quant-Sandbox 校验通过。
# (pytest 计时数字会有微小差异;SKIPPED 两行必须带原因)

# 练习 2:端口默认 8766,环境变量可覆盖(AC2)
python3 app.py
# 预期输出:端口 8766(默认 8766,环境变量 QUANT_SANDBOX_PORT 可覆盖)
QUANT_SANDBOX_PORT=9000 python3 app.py
# 预期输出:端口 9000(默认 8766,……)
QUANT_SANDBOX_PORT=abc python3 app.py
# 预期输出:ValueError: 环境变量 QUANT_SANDBOX_PORT 不是合法整数:'abc',退出码 1

# 练习 3:.env 文件也能设端口(评审后新增的接线行为)
printf 'QUANT_SANDBOX_PORT=9001\n' > .env && python3 app.py && rm .env
# 预期输出:端口 9001(local .env 是最强候选,连 shell 导出都能压过)

# 练习 4:一条命令全绿(AC3:纯标准库)
python3 -m pytest
# 预期输出:15 passed(零网络、零警告配置;唯一依赖是 pytest 本身)

# 练习 5:看看回归锁怎么工作(可选,做完还原)
#   在 src/config/settings.py 顶部加一行 import numpy,再跑 python3 -m pytest
#   预期:test_product_code_imports_only_stdlib 变红,报出 "产品代码出现非标准库 import"
```

## 下节课预告

课 02:合成价格生成器——固定种子闭式公式产出**教学样本**,第一次出现本项目数据工程的固定格式:`manifest.json` 记来源与指纹(ADR-0004)。
