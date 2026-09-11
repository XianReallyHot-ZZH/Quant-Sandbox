"""风险域包:引擎外的风险复盘层(课 05 起)。

运行时风控(订单提交前的闸)在 ``strategy_engine.backtest.risk``——
它在引擎**里面**;本包放引擎**外面**的事后分析:对回测 payload 复盘,
产出 findings。两层共用 rule id 命名空间,去重逻辑见 ``simulation``。
"""
