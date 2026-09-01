# ADR-0004: 数据策略 = 教学样本合成 + 投资门真实重抓冻结

- 状态:Accepted(2026-09-01)
- 关联:ADR-0002(零依赖离线)、ADR-0006(verify 校验 manifest);报告 §4.1、§6.8、§8.5 #5/#8

## 背景

参照物三种数据并存且易混淆:`prices.csv` 全合成(闭式三角函数,确定性);`investment_gate/*.csv` 真实 Binance 日线(5×1000 根,sha256 manifest,刻意冻结使验收可复现);dashboard 的 fixture 层合成 / snapshot 层真实(§6.8)。`data/` 的再分发无单独 ToS 声明,MIT 只覆盖代码(§8.5 #5)。

## 决策

1. **教学样本**:自写合成生成器(固定种子、闭式公式,学 `generate_prices_sample.py` 思路),不拷贝参照物的任何数据文件。
2. **投资门数据集**:自写抓取脚本直连 Binance 公共 API(无密钥)重新获取 5 个 symbol × 1000 根日线,冻结入仓 + `manifest.json`(sha256/`generated_at`/来源 URL)。抓取时点是我们自己的,不继承参照物的窗口。
3. **dashboard fixture**:自建合成 fixture;snapshot 层(auto/live 模式)按 ADR-0007 同样的「默认沉默」姿态后置。
4. **试验账本从空开始**:不复用参照物的 59,881 行 `backtest_trials.jsonl`——多重检验历史是它的研究过程,不是我们的(§6.8 ⚠)。

## 后果

- 换来:「冻结数据集 + manifest + 指纹,验收不依赖活网络」这门实践被完整学习,且无再分发风险。
- 付出:多一个抓取脚本 + 网络一次性依赖(抓取动作本身允许联网,验收不允许)。
- 数据文件旁一律放 manifest——成为本项目数据工程的固定格式。
