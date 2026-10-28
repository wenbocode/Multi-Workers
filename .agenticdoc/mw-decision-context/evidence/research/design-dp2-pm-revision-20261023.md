# Research: dp2 PM主动触发修订

## 事实来源
用户在设计讨论中修订：dp2用于PM判断任务处理/拆分，只由PM触发，背景可带worker执行情况；随后明确保留decide_registry.json的dp2-checkpoint-split问题设定：收窄/拆分/直执/高风险给人。
源码只读 `.agenticdoc/goal.md:1` 目标；`packages/multi-workers/decide_registry.json:254-271` 当前问题，read工具读取UTF-8核实，PowerShell Select-String中文乱码不是源文件乱码。

## 保留的精确问题
- id: checkpoint_action；type: choice。
- instructions: 以当前进度，这一步该继续、拆小、直接执行还是上抛人？
- choices: narrow, split, direct-exec, escalate。
- labels: 收窄到剩余预算内能完成的一小块 / 拆成多个任务重派 / PM 自己直接做完 / 风险高到必须问人。
- 保留问题不等保留旧自动调用、旧业务state或自动narrow消费。instructions含继续不新增continue标签。

## 修订与方案取舍
- AC004编号不变，按锁定修订协议标REVISED，内容替换为PM触发、可选worker背景、原问题保持、零自动调用/执行。
- D003旧自评等待/异常计数方案撤回；两个候选“保持/拆分”和“继续/收窄/拆分/交回PM”均撤回。
- dp2必需任务目标/要求/交付物与PM决策背景；worker执行情况可选，无worker/无自评不拒绝，也不编造关联。
- high-risk由PM问用户；direct-exec由PM在已有授权及写面协调后落实，不自动杀worker或执行。收窄若改验收目标仍需用户确认。
- watchdog/检查点自身告警保持，移除其自动dp2调用与自动narrow消费者，实施需明确认领回归。

## 并行分析及未验证
此次只需同步同一dp2语义的spec/design/VC/evidence，文档耦合PM串行修改；无新增未知研究问题，0新worker，不重开研究循环。
原研究/收敛笔记保留历史，本文覆盖其dp2建议。无源码修改、运行模型、测试、browser/build/install/commit；其余设计尚待审核，不自动推进PLAN。
