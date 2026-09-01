# 调查报告：`vendors/web3-quant-sandbox`

> 上游仓库：https://github.com/congde/web3-quant-sandbox （MIT License，作者 Yuan Congde / 袁从德）
> 本报告面向「没读过该项目、将要复现它的工程师」，是复现工作的输入材料。

---

## 摘要（TL;DR）

**它是什么：** 一个「Codex 交付课程」的配套可运行沙箱 —— 单进程纯标准库 Python HTTP 服务器（`app.py`，944 行，非 FastAPI）+ React 19/Vite 前端，把行情总览、机会雷达、因子挖掘、数据源监控、策略回测、统计审计、模拟交易工作站、受限策略 DSL、研究报告和一套教学学堂塞进同一个本地应用（`127.0.0.1:8765`）。约 55+ 个 JSON 端点、19 条前端路由、30 个注册策略。

**最反直觉的技术决定：** `src/` 的 19,914 行 Python **只 import 标准库** —— 没有 pandas/numpy/scipy/requests/httpx/TA-Lib。手写了技术指标库、遗传规划、岭回归（高斯消元）、bootstrap IC 置信区间、PBO/DSR/CPCV。`requirements.txt` 的 5 个依赖里只有 pytest 是产品测试必需的，dotenv/PyYAML 都有 `try/except ImportError` 纯 Python fallback。

**最重要的工程想法（值得照抄）：** 「可追溯的研究结论」被做成了可机器验收的软件 —— 来源卡 + 不可移除的安全警告文案（`verify.py:59-71` 字符串断言锁死）、`src/risk/execution_boundary.py` 把「想下单」建模成可分类请求并硬性降级、`src/backtest/trials.py` 59,881 行的多重检验账本喂给 DSR、`src/backtest/investment_gate.py`（732 行）实现**预注册的策略晋升合同**：冻结策略指纹 + 数据质量校验 + 12 道硬门 + 前向验证状态机，终点永远是 `REQUEST_HUMAN_REVIEW`。

**规模：** 460 个文件。Python 46,433 行、前端 TS/TSX/CSS 34,112 行、测试 3,576 行（226 个函数）、Markdown 2,935 行、数据约 24MB。**但其中 `scripts/` 的 21,778 行里约 19,444 行（89%）是课件插图工程，与产品无关**；前端 10,749 行是纯静态教学内容。**真正的复现目标约 22,000 行 Python。**

**最大的文档-代码落差：** `prd.md` / `product-brief.md` / `plan.md` 描述的第一版（35 天样本、1 个策略、1 个端点）**已不存在** —— `src/` 在 2026-06-12 才出现，三周内从 0 长到 114 个 py 文件，而这三份文档停在 6/21-7/21。当前功能清单应以 `README.md:148-160` 为准。其余落差见 §6（`outputs/` 不存在、`docs/v2/` 私有导致整块检查被静默跳过、README「169 个公式」与源码实测 146 不符、`eval-rubric.md` 的 5 维评分没有代码实现）。

**复现最低外部依赖 = 零**（本人已实测 `report_cli.py` 在干净环境纯 stdlib 跑通）。

---

## 0. 研究基准

| 项 | 值 |
|---|---|
| 子模块 commit | `a6cc399d715f540110ed1aea4eb3bbe536a2f29b` |
| 短 hash / 日期 | `a6cc399` 2026-08-19 20:08:26 +0800 |
| HEAD 提交信息 | `feat: deepen quant academy and factor research` |
| 提交总数 | 94（2026-06-06 → 2026-08-19，约 2.5 个月） |
| 工作区状态 | clean（无本地改动） |
| 引用方式 | `相对路径:行号`，相对于子模块根目录 `vendors/web3-quant-sandbox/` |

**本报告所有结论只对应上述 commit。** 该仓库 2.5 个月内 94 次提交、月度分布为 2026-06: 43 / 2026-07: 43 / 2026-08: 8，属于高速演化中的项目，任何「文档 vs 代码」结论都随时间漂移。

**证据标注约定**
- 「**代码证实**」= 本人在该 commit 下读到代码/数据并可直接给出行号。
- 「**⚠ 文档宣称，代码未见佐证**」= 文档里写了，但我在代码里找不到对应实现，或实现与文档描述明显不符。

---

## 1. 定位

### 1.1 它为谁解决什么问题

| 维度 | 内容 | 出处 |
|---|---|---|
| 目标用户 | ① 想零资金风险学习 Web3 量化与程序化交易的新手；② 需要本地回测/风控审计样例的开发者；③ Codex 课程学员；④ 想搭私有模拟交易面板的工程师 | `README.md:275-280` |
| 核心问题 | 学习者能找到大量 Web3 市场观点，却难以区分「有来源的事实 / 解释 / 历史模拟 / 未来不确定性」 | `prd.md:3-5` |
| 一句话定位 | 离线优先的 Web3 量化研究沙箱：把行情总览、机会雷达、因子挖掘、数据源监控、策略回测、风险审计、模拟交易工作站、策略 DSL 和研究报告放进同一个本地应用 | `README.md:5` |
| 商业/课程背景 | 这是一个「Codex 交付课程」的配套工作区（companion workspace），教程正文与可运行沙箱被当作同一件产品 | `AGENTS.md:3-5` |

### 1.2 产品边界（这是理解全项目的钥匙）

`prd.md` / `product-brief.md` 把第一版边界收得极窄：

- 一个**虚构**教学资产 `示例协议（WEB3-DEMO/USDT）`、固定日线样本、三张来源卡（`product-brief.md:19-24`）
- 一个双均线交叉策略，与 buy-and-hold 对比（`product-brief.md:22-23`）
- 明确 **Prohibited**：交易所连接、钱包签名、真实订单、实时行情依赖、自动实盘执行、仓位建议、收益承诺（`product-brief.md:30-33`）

**这套边界在代码里是硬约束、不是口号：**

- `src/research/report.py:29-33` 每份报告都硬编码三条警告：「研究与模拟项目，不进入实盘执行。」「仅使用虚构 Web3 资产与固定离线历史样本。」「项目不连接交易所账户，也不能执行交易。」
- `verify.py:59-71` 在验收时**字符串匹配**检查这些边界文案存在，缺一个就 `SystemExit`。也就是说「安全文案」是被 CI 级别的验收锁死的。
- `src/risk/execution_boundary.py:38-44`：任何 `capability == "real_order"` 或 `requested_action == "real_order"` 的请求一律 `blocked`；`dry_run_order` 若非 `simulation_only` 或未经 `human_confirmed`，会被**降级**为 `research_record`（`src/risk/execution_boundary.py:46-65`）。
- `src/backtest/investment_gate.py:272,360,370,380,416`：`"live_trading_authorized": False` 五处硬编码。
- 全仓 grep `market_buy|place_order|create_order` 只命中 `src/strategy_engine/ai_trading_api.py:12-27`，它只是构造 `OrderIntent` 值对象给模拟器用，没有 broker client、没有网络、没有凭证。

**结论：** 这是一个「教学产品 + 研究工具」的混合体。它的工程亮点不在量化策略本身（策略都很基础），而在于**把「可追溯的研究流程」做成了可执行、可验收、可审计的软件**——来源卡、假设声明、风险检查、多重检验账本、DSL 前视偏差 lint、promotion 状态机，全是围绕「让一个结论可以被第三方复核」这个目标建的。

---

## 2. 功能清单

入口形态共三种：**React Web UI（19 条路由）**、**JSON API（约 55+ 端点）**、**CLI（3 个脚本 + Makefile 任务）**。

### 2.1 核心功能（产品主张的主路径）

| # | 功能 | Web 入口 | API 入口 | 实现位置 |
|---|---|---|---|---|
| 1 | 市场总览：多资产行情 / K 线 / 交易信号 / 风险摘要 | `/trading`（`App.tsx:66`） | `GET /api/market/tickers`、`/api/market/candles`、`/api/market/ticker`、`/api/market/kline-analysis` | `app.py:422-461`；`src/dashboard/market.py`、`kline_analysis.py`；前端 `src/web/src/pages/trading/DashboardPage.tsx` |
| 2 | 机会雷达：资金/趋势/链上/风险信号扫描，区分热路径、冷路径、风控阻断 | `/radar`（`App.tsx:84`） | `GET /api/dashboard/opportunity-scan` | `src/dashboard/opportunity.py`（150 行）；`app.py:410-416` |
| 3 | 因子挖掘：GP/ML/模板/LLM 四路候选生成 + IC/IR/p 值/bootstrap 验证 | `/factor-mining`（`App.tsx:88`） | `POST /api/dashboard/factor-mine`、`POST /api/dashboard/factor-mine/backtest` | `src/factor_mining/`（12 文件 2641 行）；`app.py:245-251, 579` |
| 4 | 策略回测：单策略 / 策略对比 / 窗口对比 / walk-forward / 组合 / 稳健性 / CPCV | `/backtests`（`App.tsx:90`） | `POST /api/dashboard/backtest`、`/compare`、`/windows`、`/walk-forward`、`/portfolio`、`/robustness`、`/cpcv`、`/audit` | `src/backtest/rolling/`；`app.py:498-557` |
| 5 | 风控中心：回撤/止损/拒单/CPCV/PBO/DSR | `/risk`（`App.tsx:94`） | 复用 backtest audit 系列端点 | `src/risk/`（6 文件 881 行）+ `src/backtest/audit/`（4 文件） |
| 6 | 模拟交易工作站：K 线主画布 + dry-run 票据 + 证据面板 | `/live-trading`（`App.tsx:92`） | `POST /api/strategy/backtest`、`POST /api/validate-strategy` | 前端 `src/web/src/pages/trading/LiveTradingPage.tsx`；后端 `app.py:647-702` |
| 7 | 策略 DSL：AST 白名单 + import 限制 + 前视偏差检查 + 编译验证 | `/strategy`（`App.tsx:98`） | `POST /api/validate-strategy`（`app.py:178,589-646`） | `src/strategy_engine/dsl/`（4 文件） |
| 8 | 市场情报 / 研究报告：研究摘要、来源卡、可选 LLM 信号分析 | `/research`（`App.tsx:96`） | `GET /api/report`、`GET /api/dashboard/research-draft`、`/llm-signal-analysis` | `src/research/report.py`（34 行）+ `src/dashboard/llm_signal.py` |
| 9 | 数据源监控：离线样本 / 在线快照 / API 状态 / 研究草稿门禁 | `/data-sources`（`App.tsx:86`） | `GET /api/dashboard/sources/status`、`/api/dashboard/snapshots`、`/api/dashboard/research-draft-gate` | `src/dashboard/snapshot.py`、`catalog.py`、`api.py:752-860` |

### 2.2 外围 / 辅助功能

| # | 功能 | 入口 | 实现位置 | 备注 |
|---|---|---|---|---|
| 10 | **公益学堂（Academy）**：量化数学、机器学习、回测、K 线、诊断、资产管理、风控七类课程 | `/academy`、`/math-learning`、`/machine-learning`、`/diagnosis-learning`、`/asset-management-learning`、`/backtest-learning`、`/risk-learning`、`/kline-learning`（`App.tsx:68-82`） | 纯前端 `src/web/src/pages/learning/`，35 个文件 10,749 行（含 CSS） | **这是前端最大的单一模块**，无后端依赖。公式数核实见 §6.4 |
| 11 | 策略实验室：策略资产 / 版本 / 实验 / paper-run 的 SQLite 仓储 + LLM 提案/解释/修复/诊断 | `POST/GET/PUT/DELETE /api/strategy-lab/*` | `src/strategy_lab/`（7 文件 561 行）+ `app.py:115-321` | 7 张 SQLite 表（`repository.py:30-102`），见 §6.8 |
| 12 | 知识图谱：节点/边/证据的 CRUD + 抽取 ingest + 候选审核 + 审计 | `POST/GET/PUT/DELETE /api/dashboard/web3/knowledge-graph/*` | `src/dashboard/knowledge_graph.py`（998 行）、`graph_ingestion.py`（254 行）、`graph_scheduler.py` | 前端 `src/web/src/pages/research/KnowledgeGraphView.tsx` |
| 13 | Web3 主题研究 / 宏观观测 | `/research` 内 tab | `src/dashboard/web3_intelligence.py`（504 行） | |
| 14 | CLI 研究报告 | `python report_cli.py --format summary|json --short N --long M` | `report_cli.py:15-49` → `src/research/report.py:build_report` | **纯 stdlib 可运行**，见 §4.4 |
| 15 | 快照抓取 / fixture 同步 | `dashboard_snapshot.py --mode auto`；`scripts/build_dashboard_fixtures.py` | `src/dashboard/refresh.py:refresh_all`、`fixture_builder.py` | 见 §4.1 数据模式 / §6.8 |
| 16 | 投资门（Investment Gate）：预注册的策略晋升验收合同 | `GET /api/dashboard/backtest/investment-gate` | `src/backtest/investment_gate.py`（732 行，src 里最大的单文件） | 见 §4.2 |
| 17 | PIT（point-in-time）教学工具 | `GET /api/dashboard/backtest/pit` | `src/data/pit.py`（89 行） | **教学存根**，2 条硬编码样例记录（`src/data/pit.py:41-62`） |
| 18 | 课程/课件工程脚本 | `scripts/` 下 70 个脚本 | 见 §5.3 / §7 | **不属于产品运行时** |
| 19 | Codex skills | `skills/` 3 个技能 | 见 §7 | 文档型，非运行时 |

### 2.3 明确**不在**功能清单里的东西（对复现者同样重要）

- 不连接真实交易所账户或钱包（`README.md:313`）
- 不提交真实订单（`README.md:315`）
- 不做收益预测 / 投资建议（`prd.md:13-15`）
- 没有 MongoDB / Redis / FastAPI / 消息队列 —— `plan.md:62` 明确记录了「FastAPI + MongoDB」方案被**否决**的理由（需要密钥与运维，偏离课程目标）
- 没有 pandas / numpy / scipy —— 见 §3.3

---

## 3. 架构

### 3.1 顶层形态：单进程、前后端一体、零框架

`app.py`（944 行）是一个**纯标准库**的 `http.server.ThreadingHTTPServer`：

- `app.py:14-15`：`HOST = "127.0.0.1"`、`PORT = 8765`
- `app.py:67-70`：`class SandboxHTTPServer(ThreadingHTTPServer)`，`allow_reuse_address = True`、`daemon_threads = True`
- `app.py:73-74`：`Handler(BaseHTTPRequestHandler)`，`server_version = "Web3ResearchSandbox/1.0"`
- 同一进程内既服务 `src/web/static/` 的构建产物（`app.py:159-174`），又处理 `/api/*` JSON 请求；未命中的路径回退到 `index.html`（SPA history 路由 fallback，`app.py:152-157`）
- `app.py:90-95`：启动前 `assert_port_available()` 主动探测端口，冲突时报「Stop other app.py instances」

没有 WSGI/ASGI 层、没有框架、没有中间件。所有路由分发都是 `if parsed.path == "...":` 的手写链（GET `app.py:109-156`）+ 一个 dict of lambdas（dashboard 子路由 `app.py:385-580`）。

### 3.2 模块划分与职责

| 模块 | 文件数 / 行数 | 职责 | 关键入口 |
|---|---|---|---|
| `src/backtest/` | 46 / 6,805 | 回测域：教学回测、滚动窗口引擎、统计审计、投资门、试验账本 | `rolling/service.py:execute_backtest` |
| `src/dashboard/` | 36 / 6,908 | 行情数据域：数据源适配、离线优先/快照、机会扫描、K 线分析、知识图谱、LLM 信号 | `api.py`（1,049 行，34 条路由） |
| `src/factor_mining/` | 12 / 2,641 | 因子挖掘域：GP/ML/模板/LLM 候选生成与评估 | `service.py:run_factor_mining` |
| `src/strategy_engine/` | 15 / 1,585 | 事件驱动回测引擎 + 受限策略 DSL | `backtest/engine.py`、`dsl/validator.py` |
| `src/risk/` | 6 / 881 | 风控规则、执行边界、模拟风险门 | `manager.py`、`execution_boundary.py` |
| `src/strategy_lab/` | 7 / 561 | 策略资产仓储（SQLite）+ LLM 协作 + 实验运行器 | `repository.py`、`experiments/runner.py` |
| `src/ta/` | 2 / 141 | 技术指标 | `core.py` |
| `src/research/` | 3 / 88 | 研究报告组装（极薄） | `report.py:build_report`（34 行） |
| `src/data/` | 2 / 89 | PIT 教学存根 | `pit.py` |
| `src/config/` | 3 / 207 | 环境变量 / 可选上游配置 | `env.py:load_env` |
| `src/web/` | TS/TSX/CSS 34,112 行 | React 前端 | `src/App.tsx` |
| 顶层 | 1,125 行 | `app.py`(944) + `verify.py`(90) + `report_cli.py`(53) + `dashboard_snapshot.py`(38) | |

### 3.3 技术栈与关键依赖（含 import 证据）

**后端：Python 3.11+，`src/` 只 import 标准库。** 这是本项目最反直觉、也最值得复现者注意的技术决定。

对 `src/` 全量 grep 顶层 import 得到的非相对模块集合里，**没有任何第三方包**（只有 `__future__, abc, ast, collections, concurrent, copy, csv, dataclasses, datetime, decimal, email, enum, functools, hashlib, hmac, html, importlib, itertools, json, logging, math, os, pathlib, random, re, sqlite3, ssl, statistics, sys, threading, time, types, typing, urllib, uuid, xml`）。

`requirements.txt` 全文只有 5 行，逐项核对实际用途：

| 依赖 | 实际用途 | 代码证据 | 是否必需 |
|---|---|---|---|
| `pytest>=8.0.0` | 跑 `tests/`（226 个测试函数） | `tests/*.py` 里唯一第三方 import | **跑测试必需**；产品运行不需要 |
| `python-dotenv>=1.0.0` | 加载 `.env` | `src/config/env.py:43-49` 用 `try: from dotenv import load_dotenv / except ImportError` 包住，失败则走手写解析器 `_parse_env_file` | **可选**，有纯 Python fallback |
| `PyYAML>=6.0.0` | 读 sibling `../web3-trading/conf/default.yaml` 的默认值 | `src/config/web3_trading.py:35-39` 同样 `try/except ImportError` 返回 `{}` | **可选**，且仅当 sibling 目录存在时才有意义 |
| `matplotlib>=3.8.0` | 生成课件插图 | 只在 `scripts/generate_chapter*.py` 等 20+ 个课件脚本里 | **产品不需要** |
| `Pillow>=10.0.0` | 同上（图像处理） | 只在 `scripts/` 课件脚本里 | **产品不需要** |

`scripts/` 里另有 `numpy`、`fitz`(PyMuPDF)、`nbformat`/`nbclient` 的 import，全部属于课件/笔记本工程，不属于产品。

**前端：** `src/web/package.json`（实测读取）

- 运行时：`react ^19.2.0`、`react-dom ^19.2.0`、`react-router-dom ^7.13.1`、`antd ^5.29.3`、`@ant-design/icons ^6.1.0`、`lightweight-charts ^4.2.2`、`rc-table ^7.54.0`
- 构建期：`vite ^7.2.2`、`@vitejs/plugin-react ^5.1.0`、`typescript ~5.9.3`
- 无测试框架（没有 vitest/jest），**前端零测试**
- `src/web/static/` 是**已提交进仓库**的 Vite 构建产物（2.5MB：`index-uTshpbKv.js` 2.24MB + `index-CsGlvMeA.css` 335KB）——复现者如果不装 Node，直接用这份产物也能跑

### 3.4 端到端数据流

以「用户在 `/backtests` 跑一次回测」为例：

```
浏览器 (React BacktestsPage.tsx)
  → POST /api/dashboard/backtest?symbol=...&strategy=...
    → app.py:498  send_dashboard_api() 的 routes dict
      → backtest.rolling.service.execute_backtest()      (service.py:176)
        → load_candles()                                  (service.py:140)
            ← data/dashboard/*.json (fixture)
            ← data/dashboard/snapshots/*.json (snapshot)
            ← 在线 API（仅 auto/live 模式）
        → registry.get_strategy(name)                     (registry.py:16)
        → engine.run_backtest()  异步生成器核心循环        (rolling/engine.py)
            → compute_all_indicators()  预计算            (rolling/indicators.py)
            → strategy.generate_signal(candles, idx, params, indicators)
            → risk/position.py:check_exit()  出场判定
            → metrics.compute_metrics()                   (rolling/metrics.py:118)
        → trials.get_ledger().record()  写入多重检验账本    (trials.py)
        → audit/*  (可选：PBO / DSR / CPCV / robustness)
  ← JSON payload（含 metrics / equity curve / trades / assumptions / warnings）
```

研究报告路径（`report_cli.py` / `GET /api/report`）则短得多：

```
report_cli.py → research.report.build_report(short, long)   (report.py:10)
  ← data/company.json (来源卡)
  ← data/prices.csv   (381 个交易日)
  → backtest.runner.run_backtest()  → strategy_engine.backtest.engine.BacktestEngine
  → risk.simulation.evaluate_backtest_risk()
  → {research, backtest, risk_checks, fusion, warnings}
```

### 3.5 关键抽象 / 接口

| 抽象 | 定义 | 说明 |
|---|---|---|
| `Strategy` ABC | `src/backtest/rolling/strategies/base.py:25-78` | 4 个方法：`generate_signal(candles, idx, params, indicators) -> Signal`（抽象）、`default_params()`（抽象）、`param_grid()`（walk-forward 搜索空间）、`prepare()`（批量预计算钩子）+ `is_incremental()` / `backtest_config_overrides()`。**注册 30 个策略类**（`registry.py` 实测），含 MA/BOLL/RSI/MACD/ADX/资金费率/regime/10 个 MLTemporal*/10 个 MinedFactor*/buy-and-hold |
| `StrategyFn` | `src/strategy_engine/backtest/engine.py:56` | `Callable[[StrategyContext, Candle], OrderIntent | None]` —— 第二套引擎的策略接口 |
| `RiskRule` 协议 | `src/risk/manager.py` | 5 条内置规则，命中即短路（`manager.py:281-298`） |
| `ExecutionRequest` | `src/risk/execution_boundary.py` | 把「想下单」建模成一个可分类的请求对象 |
| `TrialRecord` | `src/backtest/trials.py:16-29` | 多重检验账本条目 `{source, strategy_key, sharpe_ratio, total_return_pct, params, total_trades, timestamp}` |
| `StrategySpec` | `src/strategy_lab/llm/proposer.py` | LLM 产出/人工审核的策略规格，带 `review_required: True` |

### 3.6 ⚠ 架构上的「双引擎」与「双口径」——复现者必须知道

代码里**同时存在两套回测引擎、两种 Sharpe 口径、两套风险规则 ID**：

1. **两套引擎**
   - `strategy_engine.backtest.engine.BacktestEngine`：`Decimal` 订单意图驱动、有挂单/限价/止损语义、风控前置检查（`engine.py:89-122`）
   - `backtest.rolling.engine.run_backtest`：`float` 信号驱动的 bar 循环，所有审计/优化器都基于它
   - `src/backtest/bridge.py:42` 专门提供 `compare_engines()` 来对账两者；`src/backtest/research_path.py` 的教学路径会同时跑两个
2. **两种 Sharpe**
   - `strategy_engine/backtest/models.py:102`：按逐 bar 权益收益、mean/std×√n
   - `backtest/rolling/metrics.py:38`：按逐笔交易 PnL 计算
   - 两者数值不可直接比较
3. **两套风控 ID 重叠**：运行时 `MAX_DAILY_LOSS_PCT`（交易前拦截，`src/risk/manager.py:75`）vs 回测后复盘的 `MAX_DAILY_LOSS_PCT` finding（`src/risk/simulation.py:64-80`），靠 rule id 在 `simulation.py:62-68` 去重
4. **两套 rubric 同名冲突**：`eval-rubric.md` 是 5 维 0-2 分的人工评分表；而 `src/dashboard/signal_eval.py:6-12` 的 `RUBRIC_WEIGHTS` 是另一套 5 维加权 100 分制（`json_valid:20, evidence_refs:25, admits_missing_data:20, direction_stable:15, clear_summary:20`），用于给 LLM 信号打分。**两者没有任何代码关联**，仅靠 `tests/test_eval_version_contract.py:7` 各自固定。

---

## 4. 复现关键点

### 4.1 数据来源

#### 本地数据（默认路径，复现最低要求）

| 文件 | 内容 | 格式 / 规模 | 生成方式 |
|---|---|---|---|
| `data/prices.csv` | 教学资产 WEB3-DEMO/USDT 收盘价 | 2 列 `date,close`，**381 行**，2025-01-02 → 2026-06-18（仅工作日），8.69 → 13.58 | `scripts/generate_prices_sample.py:26-33` —— **100% 合成**：闭式三角函数和 `8.20 + i*0.0165` 加三个正弦周期、一个 `max(0,·)²` 修正项、一个冲击项，`round(...,2)`。非真实行情 |
| `data/company.json` | 虚构公司 + 市场快照 + **3 张来源卡**（S1/S2/S3，含 `date`/`title`/`evidence`） | 60 行 JSON（实测读取） | 手写 |
| `data/investment_gate/{BTC,ETH,SOL,XRP,BNB}USDT.csv` | 真实 Binance 日线 OHLCV | 9 列，每个 1000 行，2023-10-27 → 2026-07-22（实测） | `scripts/build_investment_gate_dataset.py`（直连 Binance） |
| `data/investment_gate/manifest.json` | 各 CSV 的 sha256 + `generated_at` | JSON | 同上 |
| `data/investment_gate/forward_plan.json` / `acceptance_certificate.json` | 预注册前向验证计划 / 验收证书 | JSON | `investment_gate.py:424-431` 写出 |
| `data/backtest_trials.jsonl` | 全局多重检验账本 | **59,881 行**（实测 `wc -l`），15MB | `src/backtest/trials.py:record()` 追加 |
| `data/strategy_lab.db` | 策略实验室 SQLite | 7 张表，84KB，**几乎为空**（`strategies` 1 行、`strategy_versions` 5 行、其余 0 行）—— 种子示例库；测试都在 `tmp_path` 自建 | `src/strategy_lab/repository.py:26-104` |
| `data/dashboard/*.json` | **10 个 fixture = 合成、手工整理的离线样本**（`source: "fixture"`），例如 `market_tickers.json` 102 个 ticker、`market_candles.json` BTC-USDT 1day、`opportunity_scan.json` 扫了 7 个 symbol、`onchain.json` 恐贪 12 "Extreme Fear" | **不是真实行情快照** | `scripts/build_dashboard_fixtures.py` + `src/dashboard/fixture_builder.py`（`_write_fixture` 强制 `source:"fixture"`，`:14-23`；`_synthetic_candles()` `:114`） |
| `data/dashboard/snapshots/*.json` | **21 个「最新快照」= 真实联网抓取的市场数据**：`binance_markets.json` 632KB / `count: 3670` / `provider:"binance"`、`valuescan_token_full__symbol=BTC.json` 734KB、`valuescan_global.json` 354KB、`market_tickers.json` 250KB 等 | `source: "snapshot"`，含 `snapshot.origin` | `src/dashboard/snapshot.py:save_snapshot` |
| `data/dashboard/manifest.json` | 数据集元数据台账 | `updated_at: 2026-08-01T10:15:38Z`，各数据集 `layer/origin/complete/updated_at` | `src/dashboard/catalog.py:save_manifest` |

**数据 license / 获取限制：** 仓库 `LICENSE` 只覆盖代码（MIT）。`data/` 里的 Binance/ValueScan/KuCoin 抓取数据**没有单独的再分发声明** —— 复现者若重新分发这些 CSV/JSON 需自行评估各数据源的 ToS。`data/prices.csv` 和 `data/company.json` 是合成/虚构的，无限制。

#### 外部 API（可选，默认关闭）

全部出站流量走一个模块 `src/dashboard/http_client.py`，**用 `urllib.request`（标准库），不是 requests/httpx**（`http_client.py:5-6`）。

| # | 数据源 | 默认 Base URL | 认证 | 密钥必需？ | 代码位置 |
|---|---|---|---|---|---|
| 1 | KuCoin 公共行情 | `https://api.kucoin.com` | 无 | 否 | `src/dashboard/market.py:14,184,250,288,369` |
| 2 | Binance 公共行情 | `https://api.binance.com` | 可选 `X-MBX-APIKEY`（`market.py:32-34`） | 否 | `src/dashboard/market.py:15,202,238,263,326` |
| 3 | Alternative.me 恐贪指数 | `https://api.alternative.me/fng/` | 无 | 否 | `src/dashboard/market.py:10-13,95-98` |
| 4 | **ValueScan Open API** | `https://api.valuescan.io/api/open/v1` | **HMAC-SHA256 签名**：`X-API-KEY` + `X-TIMESTAMP` + `X-SIGN = hmac(secret, ts+body)`（`valuescan.py:32-37,50-55`） | **是**（`VS_OPEN_API_KEY` / `VS_OPEN_SECRET_KEY`） | `src/dashboard/valuescan.py`（311 行，约 20 个封装方法） |
| 5 | DexScan DEX 数据 | `https://kcapi.dexscan.trade` | `API-KEY` 头 | 可选 | `src/dashboard/dexscan.py:9,24,40-41` |
| 6 | GDELT DOC 2.0 | `https://api.gdeltproject.org/api/v2/doc/doc` | 无 | 否 | `src/dashboard/news.py:30,98,217-224` |
| 7 | 8 个 RSS 源（cointelegraph / theblock / decrypt / cryptoslate / cryptopolitan / bitcoinmagazine / beincrypto / ethereum blog） | 硬编码于 `WEB3_RSS_FEEDS` | 无 | 否 | `src/dashboard/news.py:15-29,196-214` |
| 8 | DeepSeek（OpenAI 兼容） | `https://api.deepseek.com` | `Authorization: Bearer $OPENAI_API_KEY` | LLM 功能必需 | `src/dashboard/llm_signal.py:34-43,87-116` |
| 9 | web3-trading sibling 服务 | `http://127.0.0.1:{port}` | 无 | 否 | `src/dashboard/upstream.py:19-38`、`src/config/web3_trading.py:54-78` |

**失败处理（复现者必须照抄的行为契约）：**

- **没有重试。** `http_get_text` 单次调用，`HTTPError` → `RuntimeError(f"HTTP {code}: {body[:300]}")`，`URLError` → `RuntimeError(reason)`（`http_client.py:17-21,43-47`）
- 超时由调用方逐点指定（恐贪 8s、交易所 10-15s、RSS 12s、GDELT 15s、LLM 90s）
- 上层统一防御：ValueScan/DexScan 吞掉 `RuntimeError` 返回 `{"code":-1,...}`（`valuescan.py:58-59`）；新闻逐源捕获并记录 `{ok:False, error}` 卡片（`news.py:212-213`）；API 层捕 `Exception` 后回退离线并标注 `live_error: True`（`api.py:57-58,694-695`）

#### 数据模式状态机（离线优先的核心）

`DASHBOARD_DATA_MODE`（默认 **`offline`**，`src/dashboard/mode.py:12-18`）：

| 值 | `prefer_offline()` | `serve_offline_first()` | `background_refresh_enabled()` | `try_live_public()` |
|---|---|---|---|---|
| `offline` | ✓ | ✓ | ✗ | ✗ |
| `auto` | ✗ | ✓ | ✓ | ✓ |
| `live` | ✗ | ✗ | ✗ | ✓ |

读取优先级链在 `src/dashboard/snapshot.py:load_offline`（`snapshot.py:183-211`）：

```
完整 fixture → 完整 snapshot(variant key) → 完整 snapshot(canonical key)
→ 不完整 snapshot → 不完整 fixture
```

请求级编排（`src/dashboard/api.py` 各端点重复的模板，以 `onchain` 为例 `api.py:197-241`）：

```
try_cached_first()                        (resolve.py:20-42)
  ├─ offline: 直接 load_offline()
  ├─ auto: 要求 complete_offline；若 background_refresh_enabled() 则 schedule_background_refresh()
  └─ 未命中 → _try_upstream() → prefer_offline? load_offline
            → try_live_public? 打真实 API
            → 异常 → annotate_cached(load_offline(...))  标 live_error
```

写入门禁：`maybe_persist()`（`src/dashboard/persist.py:18-25`）只在 `source ∈ {"live","web3-trading-upstream"}`、无 `live_error`、且通过 `is_complete()`（`catalog.py:82-89`，逐数据集定义于 `DATASET_CHECKS` `catalog.py:57-79`）时落盘。`save_snapshot` 一次写两份：`snapshots/history/{name}/{ISO时间戳}.json`（不可变追加）+ `snapshots/{name}.json`（最新指针）（`snapshot.py:78-122`）。

### 4.2 回测 / 评估流程

#### 策略如何定义

两条完全独立的路径：

**A. 教学双均线（第一版合同的核心，PRD 验收对象）**
`src/backtest/runner.py`：`load_prices()` 读 CSV（`:26-36`）→ `prices_to_candles()` 把收盘价包成 `Candle`（high=close×1.002, low=close×0.998, volume=1，`:62-80`）→ `strategy_engine.backtest.engine.BacktestEngine` 事件驱动跑 → `_format_engine_result()` 补上 `short_ma/long_ma/equity` 曲线。指标：`maximum_drawdown`（`:46-52`）、`calmar_ratio`（`:55-59`，注释明确说明「Adapted from web3-trading's pure Calmar metric for negative drawdown」）、`sharpe_ratio`（`src/backtest/metrics.py:6`）。

**B. 滚动窗口策略族（30 个）**
实现 `Strategy` ABC（`base.py:25-78`），引擎是异步生成器 `rolling/engine.py`。文件头注释自述其设计灵感来自「Claude Code's Agent Loop (src/query.ts queryLoop)」：异步生成器 yield 进度事件、预计算指标 O(1) 查表、pre/post trade hooks、出场逻辑委托给 `risk/position.py`（`rolling/engine.py:1-28`）。含成交量驱动的动态滑点模型 `_compute_dynamic_slippage`（`engine.py:47-80`）。

**C. LLM/DSL 策略**：经 `src/strategy_engine/dsl/loader.py:compile_strategy` 在受限命名空间内 `exec`（见 §4.6）。

#### 回测如何执行（`rolling/service.py:execute_backtest`，`:176` 起）

1. `load_candles()`（`:140`）从 fixture/snapshot 拿 K 线，`_normalize_fixture_candles()`（`:115`）归一字段
2. `_build_config()`（`:59`）合并成本预设（`cost_presets.py`：`teaching`/`realistic`/`perp` 三档，`:7-32`）
3. 引擎跑完 → `compute_metrics()` → `trials.get_ledger().record()` 写账本
4. 返回 payload，附带 `_base_assumptions()`（`:85`）生成的人类可读假设说明行

#### 指标如何计算

- 单策略：总收益、最大回撤、Sharpe、Sortino、Calmar、胜率、盈亏比（`compute_profit_factor`）、Monte Carlo 95 分位（`rolling/metrics.py:38-118`）
- 稳健性：`audit/robustness.py:run_parameter_sensitivity` —— 对每个数值默认参数 ±20% 扰动重跑，`stability_score = stable/tested`，阈值 0.6（`:81-89`）
- **PBO**（backtest overfitting）：`audit/pbo.py:49` —— 参数网格抽样上限 12（seed 7）、分 4-8 块、组合数上限 20（seed 11），IS 最优在 OOS 落后或 IS Sharpe 超 OOS 0.5 记一次失败。**注意：这是简化的 rank-based PBO，不是 Bailey et al. 的完整 CSCV/logit-λ 统计量**
- **DSR**（deflated Sharpe ratio）：`audit/dsr.py` —— 全仓最「教科书」的模块，含 skew/kurtosis 方差估计、Euler–Mascheroni 极值公式、有理逼近的 `_norm_ppf`（`:13-101`）。**⚠ 非标准选择**：`audit_sharpe` 在日线数据下把 `sample_length` 强制抬到 ≥252（`dsr.py:114-115`），复现者需决定是否保留
- **CPCV**：`audit/cpcv.py:24` —— 分 4-8 组、枚举 C(6,2) 组合、抽样上限 `max_paths=15`（seed 19）、按 timeframe 加 embargo（15m→4 bar, 1h→2, 4h/1d→1）。代码自述「Not a full purged label overlap removal — bar-level signals only」
- **Walk-forward**：`rolling/optimization/walk_forward.py:18` —— 滚动窗口网格搜索，`test_size = max(min_context+5, n/(windows+1))`，含两个抗过拟合装置：早停（训练集前半 Sharpe < -2.0 即跳过，`:93-111`）和跨窗口最优参数多数投票（`Counter`，`:188-192`）；网格抽样上限 500（seed 42）

#### 评估标准：`eval-rubric.md` 与代码的关系

**⚠ 这是文档与代码关系最弱的一环，复现者不要误判。**

`eval-rubric.md` 定义 5 个维度（Source traceability / Backtest reproducibility / Risk communication / Safety boundary / Handoff），每维 0-2 分，并要求「Do not expand automation unless all five dimensions score 2」。

代码对它的关系**只有两个「存在性检查」**：

- `verify.py:44` 把 `eval-rubric.md` 列入必需文件清单
- `tests/test_final_acceptance_contract.py:74-81` 只断言文件文本包含 `"Safety boundary"`、`"Handoff"`、`"Do not expand automation unless all five dimensions score 2"` 这几个字符串

**没有任何代码实现这个 0-2 评分。** 它是给人类评审员用的流程文档。真正在代码里落地的「rubric」是另一套 —— `src/dashboard/signal_eval.py:6-12` 的 `RUBRIC_WEIGHTS`（百分制加权，用于给 LLM 信号打分），两者仅同名、无关联（见 §3.6 第 4 点）。

#### 真正机器化的评估：投资门（Investment Gate）

`src/backtest/investment_gate.py`（732 行）才是代码里最接近「评估标准」的东西 —— 一个**预注册的、确定性的策略晋升合同**：

- 冻结的 `STRATEGY_SPEC`（regime_trend v1.1.0，5 个 symbol，`:33-72`）
- 在 `data/investment_gate/*.csv` 上跑，先做数据质量校验：重复、时间单调、86400s 间隔、OHLC 合理性、不得有晚于 `generated_at` 的行、日期范围对齐（`:97-173`）
- 然后 12 道硬门（`:208-263`）：组合收益 ≥5%、Sharpe ≥0.60、回撤 ≤15%、已实现波动 ≤20% 目标、开发窗稳定性、≥3/5 资产为正、≥30 笔交易、跑赢 buy-and-hold ≥10pp、最差资金费率压力情景收益 ≥5%、总敞口 ≤1.0、全部 4 个预声明参数邻域盈利
- 组合构建是 **60-bar 滞后的逆波动率加权 + 周度再平衡 + 20% 波动率目标**，只用每根 bar 之前的数据（`_lagged_risk_budget_weights`，`:593-630`）
- `strategy_fingerprint()`（sha256 of sorted spec，`:301-309`）+ `evaluate_forward_validation`（`:312-421`）：前向 bar 若与 `data/investment_gate/forward_plan.json` 的指纹不符直接 `BLOCKED_SPEC_DRIFT`；状态机 `BLOCKED_SPEC_DRIFT / WAITING_FOR_DATA / BLOCKED_DATA_ALIGNMENT / COLLECTING / FORWARD_PASSED / FORWARD_FAILED`，要求 ≥90 根前向 bar，终点永远是 `REQUEST_HUMAN_REVIEW`，**绝不自动晋升**

### 4.3 测试策略

| 项 | 实测值 |
|---|---|
| 测试文件 | 40 个（`tests/*.py`） |
| 测试函数 | **226 个**（`grep '^def test_'`） |
| 测试代码量 | 3,576 行 |
| 需 `courseware` marker 的测试 | 仅 2 个（`tests/test_final_acceptance_contract.py:64-71` 断言 `docs/v2/*.md` 覆盖章节 0-35、`tests/test_chapter_implementation_matrix.py:8-11`），需要私有 `docs/v2/` 目录 —— **该目录不存在**（gitignored，见 §6.3），因此在公开 checkout 上**这两个测试无法通过**，只能被过滤掉 |
| 跑法 | `pytest tests -q -m "not courseware"`（`verify.py:73-84` 就是这么调的）；`pytest.ini` 只声明了 `courseware` 这一个 marker |
| 需要外部服务？ | **否。** 全部离线。所有 `src/dashboard/*` 的网络调用都被默认的 `DASHBOARD_DATA_MODE=offline` 挡住（`src/dashboard/mode.py:12-18`） |
| 需要真实外网？ | **否。** `grep 'http://|https://|urlopen' tests/` 只命中用作惰性测试数据的字符串字面量（如 `https://example.com/rss`）。唯一用 `urllib` 的 `tests/test_app_server.py` 打的是**本机随机端口**上自己起的真实 server（`:16` 用 `importlib` 加载 `app.py`，`:34-54` 起线程服务，15 个测试打 `127.0.0.1:{port}`，含一个 POST 会**真的执行用户提供的 DSL 策略代码** `:204-216`） |
| 估算时长 | **30-90 秒**（未实测，推断依据见 §7）。成本大头：server 启动、`evaluate_investment_gate()` 跑 5×1000 根 K 线、GP/ML 搜索、三个测试重复跑 `run_research_path(include_audit=True)` |
| conftest | 只有 9 行：把 `src/` 塞进 `sys.path`（`tests/conftest.py:5-9`）。**没有 fixture，没有 mock 框架，没有 marker** |

**测试的三种性质**（复现者应理解这个配比）：

1. **真逻辑测试**：`test_project.py`（教学回测的确定性、指标字段、非法参数抛 `ValueError`）、`test_backtest_audit.py`、`test_factor_mining.py`、`test_risk_manager.py`、`test_ml_temporal_strategy.py` 等
2. **HTTP 集成测试**：`test_app_server.py` —— 起真 server、打真 socket
3. **「合同测试」（contract tests）**：大量 `test_*_contract.py`（`test_approval_gate_contract.py`、`test_failure_recovery_contract.py`、`test_final_acceptance_contract.py`、`test_integration_path_contract.py`、`test_simulation_system_contract.py`、`test_snapshot_automation_contract.py`、`test_skill_contracts.py`、`test_chapter_implementation_matrix.py`）。这些主要**检查文件存在性 / 文档文本包含特定字符串 / 代码结构**，是这门课程「交付物完整性」的机器化验收，不是行为测试。**复现者不应把这部分视为需要等量复刻的质量屏障。**

测试断言里包含**中文用户可见字符串**（如边界文案、门标签）—— 这些属于可观测 API 契约的一部分，改文案会破坏测试。

### 4.4 部署形态

**`app.py` 是什么：** 一个**标准库 HTTP 服务器**（不是 FastAPI/Flask/Streamlit），单进程多线程，同端口服务静态文件 + JSON API。启动：

```bash
python scripts/course.py setup   # 建 .venv + pip install + npm ci + npm run build
python app.py                    # 或 make setup && python app.py
# → http://127.0.0.1:8765
```

**各入口角色：**

| 入口 | 角色 | 关键行为 |
|---|---|---|
| `app.py` | 本地服务 | 944 行，路由分发 + 静态服务，`:67-70` ThreadingHTTPServer |
| `verify.py` | **产品验收入口**（90 行） | ① `npm ci` + `npm run build` 构建前端（`:24-33`）② 检查 10 个必需文件存在（`:38-49`）③ `build_report()` 后字符串匹配 9 个必需片段——含 3 条安全文案和 `ai-trading/event-driven`、`web3-trading` 等来源标记（`:59-71`）④ 跑 `pytest tests -q -m "not courseware"`（`:73-84`）。**注意：它会联网跑 npm** |
| `report_cli.py` | 终端快速复现（53 行） | `--short/--long/--format`。**纯 stdlib，无需任何 pip 依赖**（本人已实测跑通：`strategy_return_pct=-15.35% buy_hold_return_pct=56.27% maximum_drawdown_pct=-17.67% trade_count=14`，默认 short=3/long=7） |
| `dashboard_snapshot.py` | 快照抓取（38 行） | `--mode auto|live|offline`、`--dry-run`；调 `refresh_all()`（`src/dashboard/refresh.py:80-161`，会**临时改写 `os.environ["DASHBOARD_DATA_MODE"]`** 并在 `finally` 还原） |
| `scripts/course.py` | 跨平台任务运行器（213 行） | `setup / verify / check / snapshot / build-fixtures / sync-fixtures / save-offline-data / implementation-matrix / asset-audit / teaching-plots / courseware-check / lab-10`，路由表在 `:165-179` |
| `Makefile` | 只有 5 个 target：`setup / check / verify / courseware-check / teaching-plots`，全部转发给 `scripts/course.py` | |

**`make check` vs `make verify`**：`check()`（`scripts/course.py:182-197`）先跑 verify，若 `docs/v2/` 存在则追加 implementation-matrix / asset-audit / courseware-check；**若不存在则打印 "Skipping private courseware checks" 并直接通过**。也就是说公开 checkout 上 `make check ≈ make verify`。

### 4.5 外部服务依赖清单（复现时必须替代或 mock 的东西）

| 依赖 | 何时才需要 | 不配置时的行为 | 复现建议 |
|---|---|---|---|
| `VS_OPEN_API_KEY` / `VS_OPEN_SECRET_KEY` | ValueScan 深度数据（AI Picks、资金流、持仓、社媒情绪） | `configured()` 返回 False（`valuescan.py:27-29`），走离线 fixture/snapshot | **可完全跳过**，用仓库自带 fixture |
| `DEX_API_KEY` | DexScan DEX 热度 | 头省略，走离线 | 可跳过 |
| `OPENAI_API_KEY` / `OPENAI_API_BASE` / `OPENAI_MODEL`（默认 `deepseek-v4-pro`）/ `OPENAI_API_TIMEOUT`（默认 90s） | `/research` 的 LLM 信号分析、策略实验室的 propose/explain/repair/diagnose、因子挖掘的 LLM 候选、知识图谱抽取 | **全面优雅降级**：`llm_signal.py:202-209` 无 key 时返回规则引擎基线并标注 `"未配置 OPENAI_API_KEY；使用多维规则引擎生成信号。"`；`strategy_lab/llm/proposer.py:59-81` 与 `advisor.py:19-44` 返回 `deterministic_fallback` | 可跳过，但建议 mock 一个 OpenAI 兼容端点来测 LLM 路径 |
| `WEB3_TRADING_UPSTREAM` + `WEB3_TRADING_BASE_URL`（或 sibling `../web3-trading/` 目录） | 把 dashboard 请求代理到 sibling 生产服务 | 默认 `never`，`upstream_enabled()` False | **可完全跳过**。`.env.example:3` 明说 "this repository runs without it" |
| `KUCOIN_PUBLIC_API_BASE` / `BINANCE_PUBLIC_API_BASE` / `BINANCE_API_KEY` / `FEAR_GREED_API` | `DASHBOARD_DATA_MODE=auto|live` 时 | 默认 `offline`，不发出任何请求 | 可跳过；要测则建议用 `respx`/本地 stub |
| Node.js 18+ / npm | `verify.py` 与 `scripts/course.py setup` 会跑 `npm ci && npm run build` | `src/web/static/` 已提交，**可跳过前端构建直接跑** | 复现早期可跳过 Node |
| `.env` 文件 | 可选 | `load_env()`（`config/env.py:24-62`）按顺序找 `../web3-trading/.env` → `$WEB3_TRADING_ENV` → `./.env`，**后找到的覆盖先找到的**（`override=True` 给最后一个/local） | 无 `.env` 也能跑 |
| `python-dotenv` / `PyYAML` | 可选 | 均有 `try/except ImportError` 纯 Python fallback（`config/env.py:43-49`、`config/web3_trading.py:35-39`） | 可不装 |

**复现最低外部依赖 = 零。** `report_cli.py` 本人在干净环境下（仅 stdlib + pytest 未装）直接跑通。

### 4.6 安全 / 沙箱模型（复现时值得照抄的设计）

`src/strategy_engine/dsl/` 的三层模型（`validator.py:1-11`、`loader.py:1-28` 自述）：

1. **白名单单一事实源** `safelist.py`
   - `ALLOWED_IMPORTS`：`__future__, decimal, math, statistics, datetime, typing, dataclasses, json, enum, collections, ai_trading, ai_trading.api`（`:13-31`）
   - `DENIED_IMPORTS`：`os, sys, subprocess, socket, urllib*, requests, http*, asyncio.subprocess, ctypes, importlib, _thread, threading, multiprocessing, concurrent, ast, code, codeop, pickle, shelve, dbm, shutil, pathlib, tempfile`（`:33-62`）
   - `DENIED_BUILTINS`：`eval, exec, compile, __import__, open, input, globals, locals, vars, memoryview, breakpoint`（`:64-78`）
   - `DENIED_ATTRS`：`__globals__, __class__, __bases__, __subclasses__, __builtins__, __import__, __loader__, __spec__, __code__, __closure__, __dict__` + `system, popen, execvp, execvpe, spawn, spawnv, fork`（`:80-103`）
   - 合同常量：必须定义 `on_tick(ctx, candle)`，代码 ≤500 行（`:105-107`）
2. **AST 静态校验** `validator.py:validate_strategy_code`（`:182`）—— 返回**全部**违规（不是首个），带 `line/col/rule/message/suggestion` + `ast_hash`（`ast.dump` 的 SHA-256，对空白/注释稳定，`:176-179`）。规则 id：`too_long / syntax_error / denied_import / unauthorized_import / denied_builtin / denied_attribute / denied_call / wrong_signature / missing_on_tick`
3. **前视偏差 lint** `lookahead.py` —— **刻意与安全校验分离**（「is it safe」 vs 「does it peek at the future」，`:6-15`），且姿态是「宁可误报不可漏报」（`:17-22`）。4 条规则：
   - `L001`（error）：属性名匹配 `future_/tomorrow_/next_bar/next_candle/lookahead/peek_` 前缀（`:81-94,123-147`）
   - `L002`（error）：`.shift(-N)`；`L003`（error）：`np.roll(arr, -N)` —— 位置参数和 `periods=`/`shift=` kwargs 都查（`:99-103,151-201`）
   - `L004`（warning）：对 `history`/`ctx.history` 的正整数索引（`:109,205-230`）
   - 入口 `check_lookahead_bias(code) -> LookaheadReport`，`clean` = 无 error 级 findings（`:284-297`）。docstring 自己承认：它不是证明，抓不到藏在 helper 函数里的偏差（`:24-31`）

**⚠ 信任边界必须如实复现：** `loader.py:121` 的 `compile_strategy` 是**同进程 `exec`**，只是重建了不含 `DENIED_BUILTINS` 的 `__builtins__` + 只解析白名单的守卫 `__import__`（`:90-118,145-148`），并把 `ai_trading.api` alias 到 `strategy_engine.ai_trading_api`（`:69-87`）。文档说的第三层「Docker 沙箱」**不在这个代码树里** —— 这是部署边界，不是代码边界。

---

## 5. 规模感（复现工作量估算依据）

### 5.1 总量

| 维度 | 数值 |
|---|---|
| 仓库文件总数（不含 `.git`、`node_modules`） | 460 |
| Python 总行数（不含 `src/web/`，不含构建产物） | **46,433** |
| 前端 TS + TSX + CSS | 6,050 + 15,309 + 12,773 = **34,112** |
| Markdown 文档 | 29 个文件，**2,935** 行 |
| JSON（不含 `package-lock.json`、构建产物） | 128,361 行（大头是数据文件） |
| CSV | 5,391 行 |
| 数据目录体积 | `data/` 约 24MB（`backtest_trials.jsonl` 15MB + `dashboard/` 3.2MB + `investment_gate/` 672KB） |
| 前端构建产物 | 2.5MB（已提交） |
| Git 提交数 | 94（2.5 个月） |

### 5.2 Python 按目录拆分

| 目录 | 文件数 | 行数 | 占 Python 总量 |
|---|---|---|---|
| `src/backtest/` | 46 | 6,805 | 14.7% |
| `src/dashboard/` | 36 | 6,908 | 14.9% |
| `src/factor_mining/` | 12 | 2,641 | 5.7% |
| `src/strategy_engine/` | 15 | 1,585 | 3.4% |
| `src/risk/` | 6 | 881 | 1.9% |
| `src/strategy_lab/` | 7 | 561 | 1.2% |
| `src/ta/` + `src/research/` + `src/data/` + `src/config/` | 10 | 525 | 1.1% |
| **`src/` 小计** | **133** | **19,914** | **42.9%** |
| `scripts/` | 79 | 21,778 | 46.9% |
| `tests/` | 40 | 3,576 | 7.7% |
| 顶层（app.py 等 4 个） | 4 | 1,125 | 2.4% |
| `docs/` | 1 | 40 | 0.1% |

### 5.3 核心逻辑 vs 脚手架 —— 这是最重要的结论

**`scripts/` 的 21,778 行里，约 19,444 行（89%）是课件/插图工程，与产品运行时无关。** 实测：79 个脚本中 70 个匹配 `chapter|figure|course|asset_|drawio|codex|courseware|publish|tables|heading|promote_legacy|sanitize|restructure|wire_|prune_wired|rename_|guide_figure|qbot|fix_`；产品相关脚本只有 10 个、共约 847 行（`build_dashboard_fixtures.py`、`build_investment_gate_dataset.py`、`build_investment_gate_notebook.py`、`generate_prices_sample.py`、`backtest_lab.py`、`course.py` 等）。最大的三个脚本 `promote_legacy_chapters.py`（1,511 行）、`generate_qbot_teaching_plots.py`（1,308 行）、`generate_supplementary_diagrams.py`（1,244 行）全是课件生成器。

**因此「真正的产品代码」规模是：**

| 类别 | 行数 | 说明 |
|---|---|---|
| 产品 Python（`src/` 19,914 + 顶层 1,125 + 产品脚本 ~847） | **~21,900** | 复现目标 |
| 产品前端（`src/web/src/` 34,112） | ~34,100 | 其中 `pages/learning/` 10,749 行是**纯静态教学内容**（公式、课程文案、CSS），不含逻辑 |
| 测试 | 3,576（226 个函数） | 其中合同测试约占一半 |
| 课件脚本 + 课件文档 | ~19,444 + docs | **可整体丢弃** |
| Markdown 文档 | 2,935 | 其中根目录 10 份产品文档约 800 行，`docs/samples/` 是教学样例工件 |

**核心逻辑 vs 脚手架大致是 55,000 vs 22,000（含前端教学内容）。** 若只复现后端研究能力（不含 React 前端、不含 Academy），有效目标约 **22,000 行 Python**。

### 5.4 复杂度分布：哪些是薄封装，哪些是真复杂度

最大的 15 个 Python 文件（实测）：

| 文件 | 行数 | 复杂度判断 |
|---|---|---|
| `src/dashboard/api.py` | 1,049 | **中等**：34 条路由的参数解析 + 回退编排，重复模式多，体力活 |
| `src/dashboard/knowledge_graph.py` | 998 | 中等：CRUD + 持久化 + 审计 |
| `src/factor_mining/service.py` | 838 | **高**：4 种挖掘模式编排、train/val/test 切分、Bonferroni 审计、stability report、research gate |
| `src/backtest/investment_gate.py` | 732 | **高**：预注册合同、数据质量校验、12 道门、滞后逆波动率组合构建、指纹状态机 |
| `src/backtest/rolling/service.py` | 662 | 中高：回测服务门面 |
| `src/backtest/rolling/strategies/ml_temporal.py` | 563 | 中：10 个 ML 变体 |
| `src/dashboard/web3_intelligence.py` | 504 | 中 |
| `src/backtest/rolling/indicators.py` | 495 | **高**：全部技术指标的手写实现（无 TA-Lib/pandas） |
| `src/dashboard/market.py` | 391 | 中：KuCoin/Binance 双适配 |
| `src/backtest/rolling/engine.py` | 367 | **高**：异步生成器核心循环、动态滑点、hook 生命周期 |
| `src/factor_mining/features.py` | 366 | **高**：约 70 个 point-in-time 特征 |
| `src/strategy_lab/repository.py` | 329 | 中：7 张表 + 状态机 |
| `src/risk/engine_schema.py` | 309 | 低：DDL 字符串 + 纯函数 |

**薄封装、可快速复现（约占产品代码 30%）：**
- `src/research/`（88 行）—— `report.py:build_report` 只有 34 行
- `src/data/pit.py`（89 行）—— 教学存根，2 条硬编码样例
- `src/ta/`（141 行）
- `src/strategy_lab/`（561 行）
- `src/config/`（207 行）
- `app.py` 的路由层 —— 模式高度重复

**真正的复杂度所在（约占 40%，建议按此分配工作量）：**
1. `src/backtest/rolling/indicators.py` + `engine.py` + `risk/position.py` —— 手写指标库 + 确定性回测循环（无 pandas/numpy，所有数值逻辑裸写）
2. `src/factor_mining/` —— 手写遗传规划（表达式树 + 锦标赛选择 + 子树交换）、手写岭回归（高斯消元）、moving-block bootstrap IC 置信区间
3. `src/backtest/audit/` + `optimization/walk_forward.py` —— PBO/DSR/CPCV 的统计学实现
4. `src/strategy_engine/dsl/` —— AST 白名单校验器 + 前视偏差 linter + 受限命名空间编译器
5. `src/backtest/investment_gate.py` —— 预注册合同 + 指纹状态机
6. `src/dashboard/` 的离线优先数据层 —— fixture/snapshot/live 三层回退 + 完整性判定 + 持久化门禁 + manifest 台账

**几乎零复杂度但工作量大（约占 30%）：**
- `src/web/src/pages/learning/` 10,749 行 —— 纯教学内容
- `src/dashboard/api.py` 34 条路由的参数解析样板
- 合同测试

---

## 6. 文档宣称 vs 代码现实的落差

> 这一节是给复现者的避坑清单。按严重程度排序。

### 6.1 🔴 最大落差：`prd.md` / `product-brief.md` / `plan.md` 描述的是「已不存在的第一版」

这三份文档描述的产品是：**一个虚构资产、一份 35 天价格样本、一个双均线策略、一个 `/api/report` 端点**。

- `plan.md:31`：「交付 `data/prices.csv`（**35 个交易日**收盘价，确定性样本）」
- `plan.md:38`：「默认参数 short=3、long=7」
- `product-brief.md:21`：「One fictional teaching asset」「One moving-average crossover strategy」

**代码现实：** `data/prices.csv` 实测 **381 个交易日**（2025-01-02 → 2026-06-18）；`data/company.json:12` 自报 `"sample_days": 381`；`src/backtest/rolling/registry.py` 注册了 **30 个策略**；`app.py` 暴露约 **55+ 个 API 端点**；前端 **19 条路由**。

git 历史解释了原因：`src/` 目录在 2026-06-12（`1927d8a` "Move runnable product to src/ with web3-trading dashboard replication and offline snapshots"）才开始存在，到 2026-06-30 已膨胀到 **114 个 py 文件**——三周内从 0 到 114。而 `prd.md`/`eval-rubric.md` 最后一次实质修改停在 2026-07-21（还是一次 revert），`product-brief.md` 停在 2026-06-21。**第一版合同被冻结，代码自己长成了另一个东西。**

> **复现建议：** 把 `prd.md`/`product-brief.md`/`plan.md` 当作「MVP 合同」和「安全边界宪法」来读（这部分仍然 100% 有效且被 `verify.py` 锁死），**不要**当作当前功能清单。当前功能清单以 `README.md:148-160` 的「主要能力」表为准（该表 2026-08-18 更新，与代码一致度高）。

### 6.2 🔴 `README.md:272` 宣称 `outputs/` 目录，实际不存在

`README.md` 的项目结构树里写了 `` `-- outputs/  # 生成产物 ``。实测 `ls outputs` → No such file or directory，且 `.gitignore:5` 明确忽略了 `outputs/`。这是文档模板残留。

### 6.3 🟡 `AGENTS.md` / `README.md` 宣称的 `docs/v2/` 私有课件目录，公开 checkout 里不存在

`AGENTS.md:7-8`：「examples in `docs/v2/` must match the files and commands that actually exist」；`AGENTS.md:11`：「`docs/v2/`: publishable chapter drafts」。`.gitignore:3` 忽略 `/docs/v2/`。

**后果：** `scripts/course.py` 的 `courseware-check` 会直接 `SystemExit("Private courseware is missing from docs/v2. This is expected in a public Git checkout.")`（`:151-156`）；`make check` 会跳过并打印通过（`:186-192`）；`tests/` 里 2 个 `@pytest.mark.courseware` 测试默认被 `-m "not courseware"` 排除。**所以「verify 通过」不等于「全部检查通过」—— 公开仓库上有一整块检查是静默跳过的。** 复现者要意识到这个盲区。

### 6.4 🟡 README 的「169 个核心公式 / 165 个不重复公式 / 43 份章节导学」与源码计数对不上

`README.md:14` 和 `README.md:151` 给出了非常具体的数字（169、43、165、10 章）。

代码侧：`src/web/src/pages/learning/AcademyPage.tsx:158-159` 的 `FORMULA_COUNT` / `FORMULA_CHAPTER_COUNT` 是 **`COURSES.reduce(...)` 从课程数据里动态累加**的，不是硬编码常量。`FormulaHistoryCatalog.ts:436` 有 `FORMULA_HISTORY_NAMES = new Set(HISTORY_BY_NAME.keys())`。

**对源码做直接计数（实测 `grep -o 'equation:'`）：**

| 文件 | `equation:` 出现次数 |
|---|---|
| `FormulaHandbook.tsx` | 48 |
| `FormulaHandbookAdvanced.ts` | 98 |
| **公式手册小计**（两文件在 `FormulaHandbook.tsx:15,266` 合并） | **146** |
| `KlineLearningContent.ts` | 40 |
| `MachineLearningAlgorithmDetails.ts` | 3 |
| **全部学习内容合计** | **189** |

**结论：** README 的「169」既不等于手册总数 146，也不等于全库 189，无法从源码直接复现 —— 很可能是某种去重口径或内容扩充后的过期数字（2026-08-18/19 有两个 "deepen quant academy" 提交）。**复现者应把它视为「营销圆整值」，可验证的数字是手册 146 条公式 + 每条公式在 `FormulaHistoryCatalog.ts` 里的公式史档案（提出者/背景/思想来源/推导链/传播路径/外部 `escholarship.org` 类来源 URL）。**

### 6.5 🟡 `eval-rubric.md` 的 5 维 0-2 分评分没有代码实现

见 §4.2 末尾。代码只检查文件存在 + 三个字符串。**这是「文档是流程契约、代码是另一套机器化评估（investment_gate + signal_eval）」的典型双轨。**

### 6.6 🟡 `README.md` 主要能力表漏了 `/machine-learning` 路由

`App.tsx:72` 注册了 `/machine-learning` → `MachineLearningPage`，但 `README.md:151` 的 Academy 路由列表里没有它（列了 `/academy`、`/math-learning`、`/backtest-learning`、`/kline-learning`、`/diagnosis-learning`、`/asset-management-learning`、`/risk-learning` 七个）。

### 6.7 🟢 文档**低估**了代码的地方（反向落差）

- `plan.md:75-77`：「需要 LLM、MCP、Redis、MongoDB、GitLab 或生产凭证的上游集成没有进入当前 Web3 离线教学沙盒」—— LLM 集成**已经进入了**（`src/dashboard/llm_signal.py`、`src/strategy_lab/llm/`、`src/factor_mining/llm.py`、`src/dashboard/graph_ingestion.py` 四处），只是做了优雅降级。Redis/MongoDB 确实没有。
- `playbook.md` 的「演进方向」表把「接入真实交易所或链上 API」标为「拒绝」，但 `src/dashboard/` 已经接了 KuCoin/Binance/ValueScan/DexScan/GDELT/8 个 RSS —— 靠「只读、公开、默认离线、不落交易指令」来维持边界，而不是靠「不接入」。
- `README.md` 的 mermaid 架构图（`:33-93`）把 `data/`、`snapshot/`、`sqlite`、`online` 四类存储画对了，但没画出 `data/backtest_trials.jsonl` 这个 59,881 行的多重检验账本和 `strategy_lab.db` 的 7 张表 —— 这两个是架构上真正有分量的状态存储。

### 6.8 🟢 `data/` 内容判读：哪些是源材料、哪些是运行产物

| 类别 | 文件 | 判定 |
|---|---|---|
| **源材料 —— 合成** | `data/prices.csv` | **100% 合成**，`scripts/generate_prices_sample.py:26-33` 闭式三角函数和生成，确定性可复现 |
| **源材料 —— 手写** | `data/company.json` | 虚构资产描述 + 3 张来源卡 S1-S3（dated 2026-05-31），手写 |
| **源材料 —— 真实数据（已冻结）** | `data/investment_gate/*.csv`（5 个，各 1000 行，2023-10-27 → 2026-07-22 UTC 日线，13 列原始 Binance kline 字段）+ `manifest.json`（`"source": "https://api.binance.com/api/v3/klines"`、`interval 1d`、`generated_at 2026-07-23T06:30:24Z`）+ `forward_plan.json` + `acceptance_certificate.json`（58KB，decision `PROMOTE_RESEARCH`，`live_trading_authorized: false`） | 由 `scripts/build_investment_gate_dataset.py:11-50` 抓取，`endTime` 钉死在最后一个**已收盘**的 UTC 日。模块 docstring 自述：「deliberately checked into `data/investment_gate` so that the acceptance decision is reproducible and does not depend on a live API」—— **刻意冻结以保证验收可复现** |
| **运行产物（刻意提交）—— 合成** | `data/dashboard/*.json`（10 个顶层 fixture）+ `manifest.json` | `source: "fixture"` 全程一致。`.gitignore:6-8` 注释明说：「Curated offline fixtures … committed so a fresh clone works without network access」—— **有意为之的离线优先设计**。这些是 `scripts/build_dashboard_fixtures.py` 经 `fixture_builder.py` 重建的，**不是**真实行情 |
| **运行产物（刻意提交）—— 真实数据** | `data/dashboard/snapshots/*.json`（21 个） | **真实联网抓取**：`binance_markets.json` 632KB/3670 个交易对、`valuescan_token_full__symbol=BTC.json` 734KB、`valuescan_global.json` 354KB 等 |
| **运行产物（被提交，体积大）** | `data/backtest_trials.jsonl`（59,881 行，16MB） | 多重检验账本，DSR 的 `num_trials` 来源。单行 schema 实测：`{"source":"execute_backtest","strategy_key":"ma_crossover","sharpe_ratio":0.0,"total_return_pct":-3.35,"params":{"fast_period":10,"slow_period":30,"entry_threshold":25},"total_trades":1,"timestamp":"2026-06-19T15:28:13.711879+00:00"}`。**⚠ 复现时若保留它会继承上游 6/19 以来的全部搜索历史**；`tests/test_simulation_system_contract.py:10-19` 明确断言 `run_research_path()` **不**追加到此文件（`trial_scope: "current_run_only"`） |
| **运行产物（被提交，几乎为空）** | `data/strategy_lab.db`（84KB，7 张表，1 个策略 / 5 个版本） | 种子示例库；测试在 `tmp_path` 自建 |
| **gitignored 运行时** | `data/runtime/`、`data/llm_signal_tasks/`、`data/dashboard/_*.json`、`data/dashboard/snapshots/history/`、`data/knowledge_graph.db*` | 不在仓库里；`knowledge_graph.db` 按需创建（`test_app_server.py:112-113` 断言 live 端点报告 `storage: sqlite` / `database: knowledge_graph.db`） |
| **纯文档** | `image/`（4 张截图 + 微信群二维码，README 引用的 UI 预览）、`docs/Quantknowledge/`（1 篇 748 行中文数学课 + 8 张配图，**手写源材料**，非脚本生成）、`docs/samples/`（20 个教学样例工件：部分是**刻意留空的填空模板**如 4 行的 `research-output.md`，部分是 `scripts/` 生成器的捕获输出） | **源材料**，不参与运行时 |
| **不存在** | `docs/v2/`、`outputs/`、`book/`、`vendor/`、`labs/` | 见 §6.2 / §6.3 |

`.gitattributes` 里有一条值得注意的：`data/dashboard/snapshots/*.json -text whitespace=cr-at-eol` —— 快照文件**刻意保留原始 CRLF** 以保证字节级稳定（进而保证 sha256 稳定）。

**⚠ 数据来源结论（复现者容易搞混）：** 教学主样本 `data/prices.csv` 是**合成**的；投资门样本 `data/investment_gate/*.csv` 是**真实 Binance 数据**；dashboard 的 `fixture` 层是**合成**的、`snapshot` 层是**真实**的。三者不要混为一谈。

---

## 7. 其他值得记录的观察

- **skills/ 目录**：3 个 Codex 技能（`factor-mining-research`、`research-report-check`、`web3-news-signal`），每个含 `SKILL.md`（YAML frontmatter）+ `agents/openai.yaml`（中文 `display_name`/`short_description`/`default_prompt`）+ `references/`。**`app.py` 和 `src/` 都不 import 或读取它们** —— 它们是面向 agent 的开发者文档/提示词材料，不是运行时依赖。唯一的代码反向耦合是 `tests/test_skill_contracts.py:10-33` 断言 `skills/research-report-check/SKILL.md` 文本包含 7 条英文安全短语。其中 `research-report-check/SKILL.md` 本身就是一份可复用的报告评审 rubric（要求把每条主张分类为 fact/calculation/interpretation/decision/unknown 并返回 `claim_ledger:`），**复现者值得直接借用**。
- **CI**：`.github/workflows/codex-autofix.yml` 是**唯一** workflow，文件名叫 codex-autofix 但 workflow name 实为 **"Courseware Check"**，不做任何自动修复。触发条件：`workflow_dispatch` + `pull_request`（路径过滤 `AGENTS.md / Makefile / docs/** / labs/** / skills/** / scripts/** / requirements.txt`，**不含 `src/**` 和 `tests/**`**）。单 job、`ubuntu-latest`、Python **3.12**、`pip install -r requirements.txt` → `make check`（`:15-29`）。由于公开 checkout 没有 `docs/v2/`，CI 实际执行的是「前端构建 + 224 个非 courseware 测试」，**永远不会跑那 2 个 courseware 测试**。没有前端测试（`package.json` 无 test script）、没有 lint、没有矩阵、没有缓存、不产出 artifact。**另注意：`src/**` 的改动不会触发 CI。**
- **前端零测试、零 lint、零状态库**：`package.json` 没有 test script，没有 vitest/jest，没有 ESLint，没有 Redux/Zustand。质量保障全在后端 pytest。
- **`src/web/static/` 是刻意提交的构建产物，且是必需产物**：`src/web/.gitignore` 写的是 `node_modules` / `static/*` / `!static/index.html` / `!static/assets/` / `!static/assets/*` —— 明确把构建输出反排除进版本控制，目的是让 stdlib server 在**没有 Node 工具链**的机器上也能服务 SPA。`verify.py:48` 要求 `src/web/static/index.html` 必须存在。复现者若不想引入 Node，可以直接保留这份产物。
- **测试运行时长估算**：全部 CPU-only，数据是 380-1000 行 CSV 和小 JSON；无 sleep（唯一一处 `time.sleep(0.05)` 在 `test_signal_tasks.py:30`）、无 subprocess、测试路径上不渲染 matplotlib 图。成本主要来自 `test_app_server.py` 的模块级 server 启动、`evaluate_investment_gate()` 跑 5×1000 根 K 线、`test_factor_mining.py` 的 GP/ML 搜索、以及三个测试重复跑 `run_research_path(include_audit=True)`。**推断全量 30-90 秒，远低于 2 分钟**（未实测，见附录 B）。
- **大量中文字符串是 API 契约**：错误消息（`repository.py:109` `"策略名称不能为空"`）、出场原因（`risk/position.py` 的 `止损/止盈/移动止损/超时平仓/信号反转`）、LLM prompt、边界警告文案。复现时若改成英文会破坏测试和 LLM prompt 语义。
- **确定性靠固定种子堆出来**：GP seed 42（`gp.py:30`）、bootstrap seed 42（`evaluate.py:153`）、CPCV seed 19（`cpcv.py:44`）、PBO seed 7/11（`pbo.py:25,76`）、walk-forward seed 42（`walk_forward.py:67`）。**「可复现」是该项目的核心卖点，种子是硬编码而非配置项。**
- **多层防御式编程风格统一**：几乎所有外部数据访问都是「try → 失败 → 返回上一个已知好值 + 标注原因」，从不向上抛异常导致页面崩溃。

---

## 8. 复现方案设计建议

> 以下是本报告的综合判断，与上文证据一致。按「最小可行 → 完整」分四层。

### 8.1 最小可行复现（MVP，约 1,500 行 Python + 1 份前端，1-2 天）

复刻 `prd.md` 的第一版合同 —— 这部分边界清晰、有验收标准、且 `verify.py:59-71` 给了现成的断言清单：

```
data/prices.csv (381 日, date,close)          ← 生成脚本 ~30 行
data/company.json (虚构资产 + 3 张来源卡)      ← 手写
src/backtest/runner.py    双均线 + max_drawdown + calmar
src/backtest/metrics.py   sharpe
src/strategy_engine/backtest/{candles,engine,portfolio,models}.py
                          事件驱动引擎（Decimal + OrderIntent）
src/research/report.py    build_report() → {research, backtest, risk_checks, warnings}
src/risk/simulation.py    回测后风险检查
app.py                    http.server + /api/report + 静态服务
report_cli.py             CLI
verify.py                 验收（含边界文案字符串断言）
```

**这一层就足以通过原项目的 `verify.py` 哲学**：固定样本 + 确定性回测 + 来源卡 + 不可移除的安全警告 + 自动验收。

### 8.2 第二层：研究闭环（+8,000 行，2-3 周）

按依赖顺序：

1. `src/ta/` + `src/backtest/rolling/indicators.py` —— **先做这个**。所有策略和指标都依赖它。手写（不用 pandas）是刻意选择：保证可离线、可固定结果、零重依赖。
2. `src/backtest/rolling/{models,engine,risk/position,hooks}.py` —— 异步生成器循环 + 出场逻辑。**建议照抄 `base.py` 的 Strategy ABC 签名**（`generate_signal(candles, idx, params, indicators)`），这个接口设计得很好：预计算指标做 O(1) 查表，`prepare()` 钩子支持批量预计算。
3. `src/backtest/rolling/strategies/` —— 先做 5 个基础策略（technical_signal / ma_crossover / boll_mean_reversion / rsi_mean_reversion / buy_and_hold），ML/因子系后置。
4. `src/backtest/rolling/metrics.py` + `audit/{pbo,dsr,cpcv,robustness}.py` + `optimization/walk_forward.py` —— 统计审计。**DSR 可以直接照 `dsr.py` 的公式实现**（该模块自述遵循 Bailey & López de Prado）；PBO/CPCV 要意识到原实现是「教学规模简化版」并有注释声明。
5. `src/backtest/trials.py` 多重检验账本 + `data/backtest_trials.jsonl` —— 这是把「多重检验 correction」落地的关键，工作量小（126 行）但概念价值高。
6. `src/backtest/investment_gate.py` —— 预注册合同 + 指纹状态机。**这是本项目最有原创性的工程想法，强烈建议复刻**。
7. `src/risk/` —— 5 条规则 + 执行边界。

### 8.3 第三层：数据层 + 因子挖掘（+6,000 行，2-3 周）

1. **离线优先数据层**（`src/dashboard/{snapshot,catalog,fixtures,fixture_builder,resolve,persist,mode,refresh,background,http_client}.py`，约 1,800 行）—— 这是本项目工程上最值得学的部分：fixture/snapshot/live 三层回退、per-dataset 完整性判定、一次写两份（不可变 history + 最新指针）、manifest 台账、`maybe_persist` 门禁。**建议先只做 offline 模式**，`auto`/`live` 后置。
2. `src/factor_mining/`（2,641 行）—— 手写 GP、手写岭回归、moving-block bootstrap IC。**如果允许引入 numpy/pandas/scipy，这层可以砍掉 60% 工作量**（用 `gplearn` 替代 GP、`scipy.stats.spearmanr` 替代手写、`numpy.linalg.solve` 替代高斯消元）。原项目不用库是为了零依赖离线，不是因为有性能或正确性优势。
3. `src/dashboard/api.py` + `app.py` 的 dashboard 路由 —— 样板工作。

### 8.4 第四层：策略实验室 + LLM + 前端（可选，工作量最大）

- `src/strategy_lab/` SQLite 仓储 + 状态机 + 线程池实验运行器（561 行，便宜，建议做）
- `src/strategy_engine/dsl/` AST 校验器 + 前视偏差 linter（约 700 行，概念价值高，建议做）
- LLM 集成（四处）—— **建议 mock**：定义一个 `LLMClient` 接口，无 key 时走 `deterministic_fallback`（原项目就是这么做的，`strategy_lab/llm/proposer.py:59-81`）
- React 前端 34,112 行 —— **建议完全重写或砍掉**。原前端 60% 是教学内容（Academy 10,749 行）。研究功能用 Gradio/Streamlit 或纯 JSON API + 简单页面即可。

### 8.5 风险与坑（按优先级）

| # | 风险 | 缓解 |
|---|---|---|
| 1 | **两套引擎 / 两种 Sharpe 口径**（§3.6） | 复现时**只做一套**。原项目保留两套是历史融合产物（web3-trading + ai-trading），不是设计目标。若必须两套，把 `bridge.py:compare_engines()` 一起复刻做对账 |
| 2 | **确定性承诺 vs 隐式状态**：`trials.py` 的单例**不会**在首次使用时自动从磁盘加载（`rolling/service.py:561` 的 `get_trial_audit` 才调 `load_disk()`），所以 `num_trials` 是进程局部的 —— DSR 结果会因进程生命周期不同而不同 | 复现时在进程启动就 `load_disk()`，或干脆把账本做成显式参数 |
| 3 | **`refresh_all()` 会改写 `os.environ["DASHBOARD_DATA_MODE"]`** 并在 `finally` 还原（`refresh.py:83-84,146-150`）—— 多线程下是竞态 | 复现时改成显式参数传递 |
| 4 | **中文字符串是契约** | 若要做国际化，从第一天就把文案抽成常量表 |
| 5 | **数据 license 无声明**：`data/investment_gate/*.csv` 与 `data/dashboard/snapshots/*.json` 是真实 Binance / ValueScan / KuCoin 抓取数据，`LICENSE`（MIT）只覆盖代码，`data/` 无单独再分发声明 | 重新分发前评估各数据源 ToS；教学样本可全部换成合成数据（`scripts/generate_prices_sample.py` 的思路） |
| 6 | **「verify 通过」的盲区**：公开 checkout 上 `make check` 会静默跳过整个课件检查块 | 复现时把「跳过的检查」显式打印为 SKIPPED 而非 PASSED |
| 7 | **CI 路径过滤不含 `src/**` 和 `tests/**`**（`.github/workflows/codex-autofix.yml:8-14`）：改产品代码不会触发 CI | 复现时让 CI 覆盖所有源码路径 |
| 8 | **数据来源易混淆**：`data/prices.csv` 合成、`data/investment_gate/*.csv` 真实 Binance、dashboard `fixture` 合成 / `snapshot` 真实（见 §6.8 末尾） | 在数据文件旁各放一份 `manifest.json` 记录 `source/generated_at/sha256`，学原项目的做法 |
| 9 | **`verify.py` 会联网跑 npm** | 复现的 verify 脚本应把「构建前端」和「验证产品」拆成两个入口，并允许跳过构建（`src/web/static/` 已提交） |
| 10 | **DSL 编译是同进程 `exec`** | 若要暴露给不可信用户，必须补上真正的进程级/Docker 隔离 —— 原项目文档承认这是部署边界、代码里没有 |
| 11 | **范围蔓延**：原项目 2.5 个月从「35 天样本 + 1 个策略」长到「30 个策略 + 55 个端点 + 10,000 行教学前端」 | 严格冻结 MVP 合同（学原项目：把边界写进 `prd.md` 并用 `verify.py` 字符串断言锁死安全文案） |

### 8.6 建议的模块实现顺序（依赖拓扑）

```
1. config/env.py + paths.py                       (环境与路径，207 行)
2. ta/core.py + rolling/indicators.py             (指标库，无外部依赖)
3. strategy_engine/backtest/*                      (Decimal 引擎 + 组合 + 成本模型)
4. backtest/runner.py + metrics.py                 (教学回测，PRD 验收对象)
5. research/{summary,report}.py + risk/simulation.py
6. verify.py + report_cli.py + 最小 app.py         ← 第一个可验收里程碑
7. rolling/{models,engine,hooks,risk/position}.py  (第二套引擎)
8. rolling/strategies/* (5 个基础) + registry.py
9. rolling/service.py + cost_presets.py + trials.py
10. audit/{dsr,pbo,cpcv,robustness}.py + optimization/walk_forward.py
11. investment_gate.py + data/investment_gate/*    ← 第二个可验收里程碑
12. dashboard/{mode,snapshot,catalog,resolve,persist,http_client}.py (offline only)
13. factor_mining/* (先 template + evaluate，后 gp + ml，最后 llm)
14. strategy_lab/* + strategy_engine/dsl/*
15. dashboard/{market,news,...} 外部适配器 (auto/live 模式)
16. 前端（可选）
```

**每一步都可独立验收** —— 这正是原项目 `plan.md` 的 Milestone 结构，也是它最值得复制的工程实践。

---

## 附录 A：API 端点速查

**顶层直连（`app.py`）**
- GET：`/api/report`、`/api/strategy-lab/strategies[/{id}]`、`/api/strategy-lab/experiments[/{id}]`、`/api/strategy-lab/paper-runs`
- POST：`/api/validate-strategy`、`/api/strategy/backtest`、`/api/strategy-lab/strategies`、`/api/strategy-lab/ai/{propose,explain,repair,diagnose}`、`/api/strategy-lab/experiments`、`.../cancel`、`.../versions/{id}/promote`、`.../paper-run`、`.../paper-runs/{id}/stop`、`.../strategies/{id}/versions`、`/api/dashboard/web3/knowledge-graph/{nodes,edges,evidence,ingestion/run}`、`/api/dashboard/factor-mine/backtest`
- PUT/DELETE：knowledge-graph nodes/edges/evidence、strategy-lab versions/strategies/experiments

**dashboard 子路由（`app.py:385-580`，34 条）**
`/api/dashboard/{config, sources/status, snapshots, research-draft-gate, research-draft, vs/ai-picks, vs/sector-fund, vs/token-fund, onchain, dex/trending, opportunity-scan, web3-news, web3/themes, web3/macro, web3/knowledge-graph, web3/knowledge-graph/audit, web3/knowledge-graph/ingestion, web3/knowledge-graph/candidates}`、
`/api/market/{candles, tickers, ticker, kline-analysis}`、
`/api/dashboard/{signal-analysis, llm-signal-analysis, llm-signal-analysis/poll}`、
`/api/dashboard/backtest{, /strategies, /cost-presets, /investment-gate, /audit, /robustness, /cpcv, /pit, /compare, /windows, /walk-forward, /portfolio}`、
`/api/dashboard/factor-mine`

**前端路由（`src/web/src/App.tsx:56-106`，19 条）**
`/`→`/trading`、`/dashboard`→`/trading`、`/trading`、`/academy`、`/math-learning`、`/machine-learning`、`/diagnosis-learning`、`/asset-management-learning`、`/backtest-learning`、`/risk-learning`、`/kline-learning`、`/radar`、`/data-sources`、`/factor-mining`、`/backtests`、`/live-trading`、`/risk`、`/research`、`/strategy`、`*`→`/trading`

## 附录 B：本报告未覆盖 / 低置信度项

- **前端 Academy 内容的精确公式数量**（README 称 169/165/43）—— 源码实测手册 146 条 / 全库 189 处 `equation:`，与 README 数字不一致，见 §6.4
- **各外部 API 的当前可达性与响应 schema** —— 本调查未发起任何真实网络请求，字段结构引自代码与仓库内 fixture
- **测试实际运行时长与通过率** —— 未执行 pytest（避免写入 `__pycache__`/`.pytest_cache` 污染子模块）；推断 30-90 秒，见 §7
- **唯一实测运行过的程序是 `report_cli.py`**（纯 stdlib、只读 `data/`、不写任何文件），输出见 §4.4。`app.py`、`verify.py`、pytest 均未执行
- **`scripts/` 70 个课件脚本的行为** —— 判定为与产品无关，仅做了行数统计与分类
- **`scripts/` 70 个课件脚本的行为** —— 判定为与产品无关，仅做了行数统计与分类
