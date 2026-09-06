# Quant-Sandbox

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Dependencies](https://img.shields.io/badge/依赖-纯标准库-success)
![License](https://img.shields.io/badge/License-Apache--2.0-green)

量化研究实验沙盒 —— 一门 41 课的复现式学习课程,以零依赖纯标准库的方式重建一台量化研究机的九大核心功能。

> **这是什么**:对参照项目 [`congde/web3-quant-sandbox`](https://github.com/congde/web3-quant-sandbox)(commit `a6cc399`,以 git submodule 挂在 `vendors/` 下,只读)的**学习型复现**。我们学习它的思路与方法,代码全部自写,未拷贝其任何代码或数据文件。产物是「学会了」的证明,不是商品。

> **⚠️ 重要声明**:本项目仅用于教学与研究。行情数据为**虚构资产 `QUANT-DEMO/USDT` 的合成数据**(固定种子闭式公式生成),不代表任何真实代币、协议或交易所;一切输出**不构成投资建议**;本项目的边界是离线研究,**不进入实盘执行**。

## 课程进度:4 / 41

每节课 = 一张 GitHub Issue = 一次实现会话 = 一个 commit,配套教学文档进 `docs/course/`:

| 课程 | 内容 | 教学文档 |
|---|---|---|
| 课 01 | 仓库骨架 + config/paths + pytest 接线 + verify 占位 | [docs/course/01-…](docs/course/01-repo-skeleton-and-verify-placeholder.md) |
| 课 02 | 合成价格生成器 + 来源卡 + manifest 格式 | [docs/course/02-…](docs/course/02-synthetic-price-generator-source-cards-and-manifest.md) |
| 课 03 | 事件引擎核心(Decimal 订单意图) | [docs/course/03-…](docs/course/03-event-engine-core-decimal-order-intents.md) |
| 课 04 | 风控前置 + 出场逻辑 | [docs/course/04-…](docs/course/04-risk-rules-pre-submit-and-exit-logic.md) |

完整 41 课路线(双引擎、统计审计、投资门、因子挖掘、受限 DSL……)见课程目录:[docs/course/README.md](docs/course/README.md)。

## 快速开始

要求:**Python 3.11+**,无任何第三方运行时依赖;唯一开发依赖是 pytest。

```bash
git clone https://github.com/XianReallyHot-ZZH/Quant-Sandbox.git
cd Quant-Sandbox
# 可选:连同参照物一起克隆(本项目没有它也完全可用)
# git clone --recurse-submodules https://github.com/XianReallyHot-ZZH/Quant-Sandbox.git

python -m pytest      # 全量测试
python app.py         # 产品入口(骨架):报身份与端口
python verify.py      # 机器验收:文件清单 / 数据集 sha256 / 全量测试
```

> Windows 下中文输出乱码时,给 Python 加 `-X utf8`(如 `python -X utf8 verify.py`);部分系统上命令名是 `python3`。

三条命令的预期(数字随课程增长):

```text
$ python -m pytest
107 passed

$ python app.py
QuantSandbox/1.0 · 量化研究实验沙盒
端口 8766(默认 8766,环境变量 QUANT_SANDBOX_PORT 可覆盖)
HTTP 服务将在后续课程落地;当前为骨架。

$ python verify.py
[PASS] 必需文件清单 — 7 个必需文件齐全
[SKIPPED] 研究报告安全文案 — 研究报告尚未组装(课 06 落地后启用)
[SKIPPED] 冻结数据集校验 — 冻结数据集尚未抓取(课 19 落地后启用)
[PASS] 教学样本数据集 — manifest.json sha256 全部一致
[PASS] 全量 pytest — 107 passed
```

注意那两行 `SKIPPED`:被跳过的检查**必须显式打印并说明原因**,受检产物一旦落地而断言未写则立即 FAIL——「verify 全绿」在本项目里是诚实的信号(ADR-0006)。

重新铸造教学样本(重跑逐字节一致):

```bash
PYTHONPATH=src python -m data.generator
# Windows CMD:  set PYTHONPATH=src && python -m data.generator
# PowerShell:   $env:PYTHONPATH='src'; python -m data.generator
```

## 已落地的能力

- **教学样本数据集** —— 381 个工作日的合成日线(固定种子闭式公式,重跑逐字节一致),虚构资产档案 + 来源卡,`manifest.json` 记每个文件的 sha256;篡改任何数据文件都会被 verify 点名。
- **事件驱动回测引擎** —— Decimal 订单意图(market/limit/stop/stop-limit,GTC/IOC/FOK),挂单簿语义(限价挂着等未来的 bar 触及,决策根与结算根分离防前视)，bps 费用与滑点模型,全 Decimal 组合记账(现金/加权均价/已实现盈亏/逐 bar 权益)，记账拒单显式入结果而非静默吞掉。
- **风控前置 + 出场纪律** —— 五条内置 RiskRule(仓位上限 / 峰值回撤熔断 / 振幅闸 / 异常 K 线闸 / 紧急停止)挂在订单提交前,`RiskManager` 命中即短路,拒单带 rule_id 与中文理由;出场判定五级阶梯(移动止损 → 止损 → 止盈 → 超时平仓 → 信号反转),平仓成交带中文出场原因,出场单同样过风控闸。
- **机器验收合同(verify)** —— 必需文件清单、数据集指纹、全量 pytest 三类检查已实跑,两类显式 SKIPPED 等待对应课程。

## 设计原则(速览)

| 原则 | 一句话 | 出处 |
|---|---|---|
| 学习优先 | 过程课程化:票=课=Issue=会话=commit;任何时刻停下,仓库都能跑、能 verify | [ADR-0001](docs/adr/0001-learning-first-course-format.md) |
| 零依赖 | 纯标准库 + 唯一 dev 依赖 pytest,数值全手写 | [ADR-0002](docs/adr/0002-pure-stdlib-zero-dependency.md) |
| 双引擎 | 事件引擎(教学/DSL)+ 滚动引擎(审计主力)+ 对账桥 | [ADR-0003](docs/adr/0003-dual-engines-with-reconciliation-bridge.md) |
| 数据纪律 | 教学样本合成 + 冻结真实数据集,数据旁必有 sha256 manifest | [ADR-0004](docs/adr/0004-synthetic-teaching-plus-frozen-real-datasets.md) |
| 文案即契约 | 用户可见文案中文且被测试锁死;标识符英文,注释中文详实 | [ADR-0005](docs/adr/0005-chinese-user-facing-copy-as-contract.md) / [ADR-0008](docs/adr/0008-chinese-teaching-comments.md) |
| 反静默 | 跳过的检查显式 SKIPPED;产物落地而断言未写即 FAIL;拒单显式入结果 | [ADR-0006](docs/adr/0006-verify-contract-with-explicit-skipped.md) |
| 优雅降级 | LLM 无密钥时走确定性回退,产品完整可用 | [ADR-0007](docs/adr/0007-llm-graceful-degradation.md) |
| Decimal 纪律 | 账本与成交层无 float(float 在构造口即被拒),统计层才允许 | 课 03 |

## 仓库结构

```text
Quant-Sandbox/
├── app.py                  # 产品入口(骨架)
├── verify.py               # 机器验收合同
├── src/
│   ├── paths.py            # 布局常量(单一事实源)
│   ├── config/             # .env 加载 + 端口/身份
│   ├── data/               # 教学样本生成器 + manifest 契约
│   └── strategy_engine/    # 事件驱动回测引擎
├── tests/                  # 全部测试(只落六条公共缝)
├── data/teaching_sample/   # 教学样本三件套 + sha256 manifest
├── docs/
│   ├── course/             # 41 课教学文档(随课产出)
│   ├── adr/                # 8 份架构决策记录
│   ├── research/           # 参照物调查报告(744 行)
│   └── agents/             # 仓库协作约定
├── CONTEXT.md              # 单一上下文:全局决策、词汇表、课程主序
└── vendors/                # 参照物(submodule,只读)
```

## 文档导航

- [CONTEXT.md](CONTEXT.md) —— 全局决策速查表、词汇表、课程主序;理解本项目的第一入口
- [docs/research/web3-quant-sandbox.md](docs/research/web3-quant-sandbox.md) —— 对参照物的调查报告(架构、落差清单、风险表)
- [docs/adr/](docs/adr/) —— 全部架构决策及其理由
- [docs/course/README.md](docs/course/README.md) —— 41 课目录与进度

## 开发工作流

单人学习仓库,以 GitHub Issues 推进(见 [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md)),推进与学习各配一个 Claude Code 技能:

- **`/lesson <票号>`** —— 实现一课:装载票文 → TDD 红绿 → 双轴代码评审 → 趁热写教学文档 → 收口
- **`/learn <票号>`** —— 学习一课:以「站」为单位交互式走读已实现的课程(与 `/lesson` 同号必指同一节课)

两技能位于 `.claude/skills/`,是本仓库推进节奏的固化。

## License

[Apache-2.0](LICENSE)

## 致谢

本项目是 [`congde/web3-quant-sandbox`](https://github.com/congde/web3-quant-sandbox) 的学习型复现:研读其架构与方法后自研重写,包括数据(其教学样本同为合成,我们的公式、窗口与参数均为自写)。参照物以 git submodule 形式挂在 `vendors/` 下仅供对照,只读、不修改、不发布。
