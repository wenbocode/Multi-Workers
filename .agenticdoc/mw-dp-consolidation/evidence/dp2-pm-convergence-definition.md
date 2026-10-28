# DP2：PM任务收敛与编排决策（已确认）

## 用户定义与确认

用户提出：PM发起，对当前状态处理；narrow为任务是否过于发散、是否先收敛回归主线；split为任务拆给不同Worker并行；direct_exec为不适合Worker、依赖当前窗口上下文正确推进；escalate为当前状态无法收敛、严重偏离目标或高风险选择需报人。

PM评估同意，并明确narrow不降低交付、direct-exec不是普通兜底、escalate须给具体风险/目标冲突及需人确认问题；用户答`确认`。

## 最新职责

**PM基于任务目标、真实执行状态与当前约束，判断应回归主线、拆分并行、由当前窗口直接执行，还是升级人工决策。**

- narrow：目标及验收不变，聚焦必要工作、优先级与执行路径，去除非必要发散。改变已确认目标/验收不是该选择自动授权的行为。
- split：拆为可独立交付的任务，由不同Worker并行推进；须有明确边界和无冲突写面，不仅是换一个Worker重试。
- direct-exec：正确推进依赖当前PM窗口上下文、难以合理隔离为Worker任务；不因Worker慢或一次失败就默认PM兜底。
- escalate：当前状态在现有条件下不能收敛、严重偏离目标，或具体高风险选择需人确认；输出为何工程补救不足、什么风险/冲突、需要人决定什么，不只写风险高。

现有运行选项ID为narrow/split/direct-exec/escalate，保持四选项集合；用户用direct_exec表达含义，本轮不据此改技术ID。

PM自行发起并吸收结果，与Worker fire-and-forget不冲突；Worker不因此同步等待PM。实际编排动作仍须协调在途任务与独占写面，答案不直接停止/改写Worker或扩权限。精确触发/材料细化、执行器、终态及反馈映射留设计。

## 静态基线与迁移限制

前轮读取`packages/multi-workers/decide_registry.json:65`起完整dp2条目：description为checkpoint拆/收/直执；四选项已存在，但narrow标签为剩余预算内完成一小块、split为拆任务重派、direct-exec为PM自己做完，均不足以准确表达本次确认。旧wiring_note不是当前自动消费事实，既有PM手动工具与自动steer退役事实见pm-question-action-context-review.md。

已有材料为task_goal/task_requirements/task_deliverables原文、pm_decision_background，存在Worker时可附真实worker_execution；角色仍仅PM。不得用当前状态回填未记录过去执行。

本轮仅职责/标签含义精化，不改源码/活registry/配置/服务/生产历史；旧mw-decision-context的独立交付和历史不回写。完整SPEC/19AC及联合设计未批准。

对齐`.agenticdoc/goal.md`：保留文件驱动协调、Worker隔离和角色/写面约束，支持按模块边界并行，不新增中心调度器。
