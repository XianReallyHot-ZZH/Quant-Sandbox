---
name: lesson
disable-model-invocation: true
---

一票一课:在热上下文里实现一张课票,并把本课教学文档写出来。参数为票号;缺省时取 frontier——`gh issue list --label ready-for-agent --state open` 中编号最小、且无未关闭阻塞者的票(blocking 用 `issue_dependencies_summary.blocked_by` 判断,约定见 docs/agents/issue-tracker.md)。

## 1. 装载

按 docs/agents/issue-tracker.md 取票全文;读 CONTEXT.md 与票中点名的 ADR。完成判据:验收合同、所测缝、词汇表都在上下文里。

## 2. 实现

在票所声明的缝上按 /tdd 技能执行:红 → 绿,一切片对一条验收标准;过程中只跑单测试文件,收尾跑一次全量。commit 信息含 `Closes #<N>`(第 3 步的 Spec 轴靠它找规格来源)与 `Co-Authored-By: Claude Code <noreply@anthropic.com>` 落款。完成判据:票上每条验收标准各有一条通过中的测试,全量绿。

## 3. 评审

按 /code-review 技能,以开工前 HEAD 为固定点跑双轴;两份报告分轴呈现,发现的问题先修再继续。完成判据:两轴报告都已交付且处置完毕。

## 4. 写课(热上下文)

本会话刚发生的红绿实录是票文里没有的教材——趁它在,起草 `docs/course/<NN>-<slug>.md`(NN 取票标题前缀,slug 从标题英译),模板为 docs/course/00-template.md。要求:

- **红绿实录**只记本会话真实发生的事:实际切了几刀、哪一刀红得意外、做过哪些取舍。零虚构;顺利就写顺利。
- **关键决策**给出来源(ADR 编号 / 研报 §);措辞用 CONTEXT.md 词汇表的词。
- **验收练习**把票的验收标准改写成读者可跑的命令 + 预期输出。
- 引用测试时写行为,不写行号(行号会烂)。
- 票标题含「里程碑」→ 追加章复习节,把本章各课的验收练习串成通关路线。
- 完成判据:模板无一节留占位,无一节是空话。

## 5. 收口

在 docs/course/README.md 勾掉本课一行;同步根 README(课程进度计数、课表新增行、三条命令预期里的测试数、已落地能力清单);文档与索引一并 commit:`docs: lesson <NN> — <标题>`。

完成判据(全技能):代码与文档两个 commit 都在,全量测试绿,双轴报告已交付;然后告知用户:文档路径、票是否已随 push 关闭、下一张票的号,并提醒 /clear。
