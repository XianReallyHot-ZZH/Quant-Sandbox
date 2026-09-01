# ADR-0002: 纯标准库、零第三方运行时依赖

- 状态:Accepted(2026-09-01)
- 关联:ADR-0001(学习优先);报告 §3.3、§8.3

## 背景

参照物最反直觉的技术决定:`src/` 19,914 行只 import 标准库——手写技术指标、遗传规划、岭回归(高斯消元)、bootstrap IC 置信区间、PBO/DSR/CPCV;`requirements.txt` 五项里只有 pytest 是必需的,python-dotenv/PyYAML 均有纯 Python fallback(§3.3)。报告 §8.3 估计:允许 numpy/pandas/scipy 可砍掉因子挖掘层约 60% 工作量。

## 决策

产品代码(`app.py`、`src/`)只 import Python 3.11+ 标准库;pytest 是唯一依赖(dev);手写全部指标与统计实现。不引入 pandas/numpy/scipy/gplearn,不引入 Web 框架(`http.server` 路线)。

## 后果

- 换来:可离线、结果确定、环境零摩擦、「每课可验收」成本最低;顺带继承参照物「单进程单端口本地应用」的形态。
- 付出:因子挖掘层工作量约为用库方案的 2.5 倍——**这是刻意保留的学习内容,不是负担**(ADR-0001)。
- 数字逻辑裸写,测试必须更密(数值边界用 pytest 直接锁)。
