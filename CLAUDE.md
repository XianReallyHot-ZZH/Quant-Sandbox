# Quant-Sandbox

量化研究实验沙盒:对参照物的学习型复现,41 课、零依赖纯标准库。理解本项目的第一入口是 [CONTEXT.md](CONTEXT.md)(全局决策速查 + 词汇表),决策理由见 [docs/adr/](docs/adr/)。

## 硬约束(违反即测试红 / verify FAIL)

- **零依赖**:产品代码(`src/`、`app.py`、`verify.py`)只 import 标准库与首方模块,唯一 dev 依赖是 pytest(Python 3.11+)。`tests/test_stdlib_only.py` 以 AST 守卫——引入 numpy/pandas 等任何第三方包立即红(ADR-0002)。
- **Decimal 纪律**:账本与成交层无 float(float 在构造口即被拒);统计层才允许 float(课 03)。
- **中文即契约**:用户可见文案(print、报错、报告)用中文且被测试字符串断言锁死——改措辞就是改契约(ADR-0005)。标识符保持英文;注释/docstring 中文、详实、面向 Python 初学者(ADR-0008)。
- **反静默**:跳过的检查显式 `SKIPPED` 并说明原因;记账拒单显式入结果;新产物落地必须同步补断言,否则 `verify.py` 立即 FAIL(ADR-0006)。

## 常用命令

```bash
python -m pytest    # 全量测试(开发过程中跑单测试文件即可)
python verify.py    # 机器验收合同;任何时刻停下,仓库都要能跑、能 verify(ADR-0001)
python app.py       # 产品入口(骨架)
```

Windows/GitBash 适配:命令名是 `python`(非 `python3`);中文输出乱码时给 Python 加 `-X utf8`;PYTHONPATH 用引号包住分号形式,如 `PYTHONPATH='src;tests'`。

## 课程工作流

推进节奏固化为两个技能(`.claude/skills/`):`/lesson <票号>` 实现一课,`/learn <票号>` 学习一课。**课 N = Issue #N+1**(课 01 = #2)。

- 一张课票 = 一次 `/lesson` 会话 = 一个 commit;commit 走 conventional 风格(`feat:`/`docs:`),实现课的 commit 信息含 `Closes #<N>`。
- `/lesson` 收口时同步两处进度:根 README(进度、课表、测试数、能力清单)与 `docs/course/README.md` 勾选对应课行。
- 路径常量一律 `from paths import ...`(`src/paths.py` 是唯一事实源),禁手拼相对路径。

## 参照物

`vendors/web3-quant-sandbox`(git submodule)是只读对照物:禁改、禁拷其代码与数据文件。仓库缺它也完全可用,不必为了跑测试去拉取 submodule。

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (`XianReallyHot-ZZH/Quant-Sandbox`), managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five canonical default triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
