# D-RQ2 wire evidence and decision lifecycle

type: research

## 上下文
- Goal `.agenticdoc/goal.md`；锁定 `.agenticdoc/mw-decision-dashboard/spec.md` AC-003/005/012/013/014/016；design.md 是候选不是编码授权。
- `packages/multi-workers/decision_backends.py:612` build_payload；`:627` decode；`decision.py:1227` evidence；`decision_points.py:2023` _archive_decision。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:986` append_settle 生产调用（按符号定位，行号可能漂移）；spec RQ-2 与 RQ-3 有矛盾。

## 要求
只读枚举所有真实决策发送入口及传输函数，设计在发送/读取实际字节边界捕获请求/原始返回/HTTP status/content-type/attempt/latency/usage 的 seam，不重新 build_payload 冒充实际发送。比较新旁账与旧 archive schema 变更两案，给字段、writer/reader/缺失行为、锁/原子发布/限长/脱敏/采集失败策略、call_id 与 decision_id 的不同粒度/重试关系，以及未来调用决策本快照来源（非 book 生产调用如何如实保存材料）。枚举 TS dp1/dp2/dp3/dp25/ask_decision 的采纳/消费/应答、人工回答/覆盖/授权/签收/gate 答复的全部生产写入点（未知不得猜），提出统一事件来源语义。复核 settle 矛盾，以确切调用点为准。规定来源 human/model/system/unknown、建议/吸收/执行分离，历史 inferred/call-only/缺原文诚实显示。检查旧签收/hash链边界，不静默改变生产门禁。按文件分工提供后续编码写面建议和真实路径测试，不只手搭字段。
禁止改代码、配置、档案，禁止网络/真实模型调用；大型源分页阅读相关函数，避免重复 dump。

## 唯一证据文件
.agenticdoc/mw-decision-dashboard/evidence/research/design-wire-lifecycle-records-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/evidence/research/design-wire-lifecycle-records-20261022.md`
- `.agenticdoc/mw-decision-dashboard/workers/dd-drq2-records/**`

## 写入禁止面
- 所有代码、配置、其他 key/任务、design.md/spec.md。

## 交付格式
证据 ≤300 行，先结论、事实 path:line、schema 两案/推荐、逐字段写者读者、调用点矩阵、VC建议、未覆盖。report.md 四段结论/证据/残留与未验证/上下文来源 ≤80 行；先骨架落盘。每次 read ≤150 行并完整分页阅读相关函数；stdout ≤30 行；不全量测试。pi API 涉及时先完整读相关官方 docs 与交叉引用。
