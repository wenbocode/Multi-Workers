# T22 行动反馈的任务前后状态

## type
coding（PM串行执行；暂停worker派发，避免隐式dp1请求）

## 上下文
- goal.md: .agenticdoc/goal.md，真实可追踪协作，不造执行成功。
- 用户明确同意并入mw-decision-context，补执行端前后快照与默认任务变化展示；旧记录缺失不回填。
- packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:365–434 只记录answer/action/outcome，:3231–3239检查新任务目录、:3358–3407真实派发/拒绝。
- packages/multi-workers/decision_lifecycle.py:245–327 meta和:631–760生命周期无任务快照；decision_history.py:3138–3199只投影executed/settled。

## 要求
- 追加AC025/026，原24AC不改；生产本地envelope/生命周期保存结构化task_before/task_after，不发给模型。
- 默认行动反馈=决策前（执行状态/已完成/待处理/阻塞/当时记录时间）→实际处理→决策后→变化说明。空字段显示未记录，明确[]为真实无该项；source为agent-report时标Agent报告，不声称系统观察。
- status闭集not-queued/pending/running/done/failed/needs-clarification/lost/unknown；source worker-registry/dispatch-result/agent-report；observed_at为带时区ISO。completed/remaining/blockers各为string[]或null，null=未采集，[]≠null。
- dp1在真正请求前采集同task/同owner当前队列状态，拒绝/成功后再采集。队列缺失/异常/损坏/冲突/链接不假装未入队；先记录unknown。成功派发不当运行/完成；拒绝不覆盖已存在的其它任务状态。
- 单次logical_id精确关联、观察只显示未执行业务、不从现在补过去。before仅record-start的原始快照，after仅本次真实反馈携带的快照；不把action结果自动推成task状态。
- generic Agent工具接受显式报告快照，但不改dp2/3/25执行权限、不新增自动处理。不关联task则拒绝快照。
- typed校验/写侧与公开读侧脱敏/幂等/错误不回显/无当前凭证发现/浏览器GET只读。

## 并行性分析
- 模型输入隔离/状态采集/读侧DOM可分别调研，但隐式dp1副作用限制worker；PM直接读取。
- 契约→writer→producer→reader/DOM有串行依赖；所有源码单PM写者，验证串行；不动其它key或共享服务。

## 写入允许面
- packages/multi-workers/decision_task_state.py
- packages/multi-workers/decision_lifecycle.py
- packages/multi-workers/decision_wire.py
- packages/multi-workers/decision_history.py
- packages/multi-workers/mw.py
- packages/multi-workers/decision_dashboard.js
- packages/multi-workers/test_decision_task_state.py
- packages/multi-workers/test_decision_task_state_ui.py
- packages/coding-agent/src/extensions/agent-team-loop/pm/decision-task-state.ts
- packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts
- packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts
- packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
- packages/coding-agent/test/suite/decision-task-state.test.ts
- 本key spec.md/design.md/plan.md/pm-state.md、tasks/T22-task-state-transition.md、evidence/t22-*

## 写入禁止面
其它源码/旧测试/framework/registry/config/生产ledger/共享服务/凭证/其它key/他窗口dirty变更；不得build/install/commit/真实模型/browser。

## 验收命令
- 新Python/DOM/TS指定文件先RED后GREEN（隔离HOME和合成凭证/faux runner）；邻接命名测试串行复验。
- npm run check字节保护副本，全输出，不套用formatter或擅修卡外诊断。

## 交付格式
结构化schema与实际producer→writer→history→DOM证据；状态缺失/同task跨key/队列不确定/读侧红action/秘密安全/零业务执行；基线字节/完整日志/未覆盖面。不得以局部绿称整key完成。

## 改动历史
- 用户确认合并；开始契约/首写基线，尚未实施源码（该时点记录）。
- 2026-10-24：源码接通producer→writer→history→DOM，新18P/7P/9P。队列缺失为unknown；read-side安全过滤与未记录分别显示；after同creation关联/时间顺序校验。
- 证据：evidence/t22-task-state-report.md、t22-source-integrity.json、ui-recovery/t22-*、t22-ts/*。
- 待处理：独立review/26AC/完整check与真实browser。首次副本的五个本次文件格式差异未经单独确认被应用，违背“不套用formatter”；详见报告，待用户选择保留或精确撤回；最后副本新增的一份TS测试格式差异未应用。不签收/DONE。
