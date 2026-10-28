# D-RQ4 人工记录与根归属负空间核查

type: research

## 上下文
- goal `.agenticdoc/goal.md`；spec `.agenticdoc/mw-decision-dashboard/spec.md` AC-003/014/002/008；合并稿 design.md §4.3/3.1 是待核查方案，不是实现授权。
- `packages/multi-workers/decide_signoff.py:287` collect control_root；`packages/multi-workers/decide_archive.py:1024` append_override；`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:986` settle入口，按符号复核。
- 已有 D-RQ2 证据完整，请先读它；已确认人工override/直接answer无生产入口，当前不能靠UI显示补齐AC-014。

## 要求
只读核查两类设计缺口：(1) 新增 record answer/override 记录型CLI的最小真实契约，比较复用append_override与独立lifecycle两案，目标decision/call/questions_version/动态候选/理由校验、答复与覆盖如何能如实关联，不能把记录当授权或业务消费；明确内部TS生产adopted/consumed/responded事件写入seam与来源控制，尤其dp1/2/3/25，不以fixture字段代替真接线。(2) 已有control/target/partition/project resolver链，monitor CLI、Python sidecar、TS subprocess如何传同一根，不能HTTP任意路径。给精准函数、path:line、字段writer/reader、最小签名、风险与真实入口VC。指出design合并稿中不可行或语义过度承诺项，禁止只赞同方案。不得改代码/配置/档案，禁止真实模型/网络调用。

## 唯一证据文件
.agenticdoc/mw-decision-dashboard/evidence/research/design-human-roots-gap-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/evidence/research/design-human-roots-gap-20261022.md`
- `.agenticdoc/mw-decision-dashboard/workers/dd-drq4-human-roots/**`

## 写入禁止面
- 所有源代码/配置/生产档案/其他key/相位文档。

## 交付格式
唯一证据≤220行：结论、两案、path:line事实、接口及真实写者/读者、VC、未覆盖；report.md四段结论/证据/残留/上下文来源≤50行。先骨架落盘。每次read≤150行，相关函数完整分页阅读；不全量dump、不做测试/网络。pi扩展API若涉及先完整阅读相关官方docs与交叉引用。
