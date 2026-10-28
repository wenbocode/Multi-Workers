# RQ15 联合设计取证：PM 窗口事件 / 业务准备 / 固定直调或路由 / gate steer-need_fix 后继 / 动作与回执接口

> 类型：research（只读取证）。基线：`.agenticdoc/goal.md`、`mw-dp-consolidation/spec.md`（53AC 已锁，DESIGN 未授权实施）。
> 本文只给现状事实、方案比较与设计建议；不宣称设计通过、未实施任何改动、未跑测试、不构成 AC/QG/签收证据。

## 结论

- 事件→PM 的通道已存在且是"模型上下文注入"，不是人工审批通道：轮询循环用 `deliverPmAlert`（`pi.sendMessage(..., {triggerTurn:true})`）唤醒 PM，信息性通知走无 turn 的 `displaySummary`；工具结果文本本身也直接进模型上下文。因此同事项不需要再用 sendUserMessage 复述一次审批请求（AC-049 的"不重复组织"有现成落点）。
- 材料/关联/回执链路目前只有一条真实生产链：dp1（派发）与 dp2/dp3/dp25（业务材料）。证据点：`buildDecisionToolMeta` 每调用铸新 `logical_id`，四材料 dp 走 stdin envelope，`consumed` 由消费者自动写，`executed`/`settled` 只能由本窗口 `decision_receipt` 写，且只对本窗口 `asked` map 内的 decision_id 生效。
- 目标态缺口是真实的，不是命名问题：Python 注册表仍是 25 个旧 id（`decision_points.py:576-885`），无 dp-route/dp-auto/dp-pm-steer/dp-w-type/dp-w-check-task；gate 运行面仍是二值 `approve|reject`（`autopilot/console.ts:460`、`autopilot/gate-writer.ts:32,170`、`status-model.ts:697`），dp15 注册问句仍是 `continue|narrow|revoke`（`decision_points.py:768-775`）。即 SPEC 的 steer/need_fix 后继请求今天没有 producer。
- 角色资格只做了单向硬门：只有 dp2/dp25 拒绝非 PM（`decision-tool.ts:214,1228`），**没有**"PM 不得调用 Worker 专属 dp"的反向门（当前 PM 可调 dp3）。AC-041 的"不冒充 Worker 判断"需要新增该方向，不能靠命名迁移自动得到。
- 方案取舍建议（设计建议，未批准）：固定节点直调 + 临时问题单次路由 + gate 的 steer/need_fix 只产出"后继入口建议"，由 PM 自行准备材料并发起；框架不得代发后继请求，也不得把 gate 选择当成已完成整改。

## 证据

### 1. 读取范围（全文 / 部分 / 未覆盖）

- 全文：`packages/coding-agent/src/extensions/agent-team-loop/index.ts`（96 行，注册入口两条分支）。
- 全文：`pm/decision-tool.ts`（1932 行，`ask_decision` + `decision_receipt` 唯一 LLM 面）。
- 全文：`pm/pm-orchestrator.ts`（2680 行，PM 窗口激活、轮询、事件注入、settle）。
- 部分：`pm/ui-bridge.ts`（5086 行；已读 `195-554`、`595-755`、`3300-3460`，并用符号索引定位其余相关面；未逐行读全文——见"残留"）。
- 未读：`pm/task-dispatcher.ts`、`pm/triage-client.ts`、`packages/multi-workers/*.py` 实现体（只按行取证常量/注册表/问句）、任何纯测试文件（按需未读）。

### 2. 现状事实（producer → writer → consumer → caller）

**事件送达（producer=框架轮询，consumer=PM 模型）**
- `pm/pm-orchestrator.ts:2091` `startWorkerPollLoop`；`2220` 检查点 risk=mid/high 的 PM 唤醒；`2296` 终态回读 `deliverWorkerResult`；`2366` gate pending 提醒。
- `pm/ui-bridge.ts:201` `displaySummary`（`pi.sendMessage`，无 turn，纯上下文）、`218` `deliverPmAlert`（`{triggerTurn:true}`，空闲 PM 起一轮 / 流式中 steer 进当前轮）、`232` `deliverWorkerResult` 复用同一通道。
- 结论性事实：`sendUserMessage`/`sendMessage` 写的是模型上下文；`ask_decision` 的返回值同样以工具结果文本进入上下文（`decision-tool.ts:1835` 注册，`1946-1962` 返回 `content:[{type:"text"}]`）。同 (decision_id, stage) 的事实在两条通道各说一遍，只会让模型重复组织审批。

**材料准备与关联（producer=调用窗口）**
- `decision-tool.ts:678-701` `buildDecisionToolMeta`：每次真实调用铸新 `logical_id`，`task_key` 可为 null（PM 无任务决策），不推断"最近任务"。
- `1294-1372` `runMaterialAskDecision`：先按生成注册表校验材料（`validateDecisionMaterial`），缺字段 `input-incomplete` + 字段名且零 spawn；`key` 空则拒绝；随后 stdin 发送，解析 `selection`，再自动写 `consumed`（`1358`）。
- `1385-1530` `runSignoffAskDecision`：dp25 走 `mw decide sign --stdin`，finalize 由同一调用签收，`second_approval` 恒 0；continue/user-confirm 不回传签收文件而回传 handoff。
- `889-930` `writeDecisionLifecycle`：唯一 Python 生命周期写者的客户端；超时/非零/不可解析/`recorded:false` 一律 `failed`，不抛、不伪造；`duplicate` 保留为事实。
- `1830` `const asked = new Map<...>()`：`executed`/`settled` 只对**本进程本窗口**问过的 decision_id 生效（`2000-2040`）；进程重启后同一 decision_id 无法再回执（真实限制，非缺陷判断）。
- `715-730` `initiatorRoleFromWorkerTask`：worker 角色取自己任务卡 `type:`，读不到即 `unknown`；PM 分支在 `index.ts:102` 以结构常量 `"pm"` 注册。
- `214` + `1228`：`ASK_DECISION_PM_ONLY_DP_IDS = [dp2, dp25]`，`isPmOnlyDp(dp) && role !== "pm"` → `role-forbidden`、零 spawn。**反向（PM 调 Worker dp）无门**。

**dp1 完整生产链（可作后继设计的参照实现）**
- producer：`ui-bridge.ts:603` `computeDispatchTriage` 由 `1872`（`planDispatchFrontmatter` 内）调用；材料取派发卡三段原文（`344-359`），无摘要。
- 采纳判定：`296-309` `dispatchDecisionOf`——只有 `mode=auto` + `triage_type` 与实派类型相同 + 有 decision_id 才写 `decision:` 头行；suggest/不一致不采纳（D-041 消费侧事实）。
- writer：`3025` `writeDispatchTaskMd` → `3078` `mergeDecisionHeader`（`2337`）把 decision_id 落到任务卡头；Python 侧仍只写 archive/ledger。
- 真实动作：`3120` `dispatch_worker` 工具（PM 的既有权限面），`3316-3455` 组装 plan → 写 task.md → `dispatchTask`；落地后 `3395`/拒绝后 `3426` 分别写 `executed`+`settled` 或只写 `settled=rework`。
- consumer/投影：`3357` `emitDispatchTriage`（台账 + 仅不一致时唤醒 PM）、`3442` `appendTriageReceipt`、`485-535` `writeDp1DispatchFeedback`。
- 关联/幂等种子：`409-450` `buildDp1LifecycleFact`，`event_id = dp1:<logical_id>:<stage>`（同写重放→duplicate）。

**gate 与路由现状**
- `autopilot/console.ts:198-226`（动作文案表）、`460`（只接受 approve|reject）；`autopilot/gate-writer.ts:32,170`；`status-model.ts:697` `GATE_STATUSES=["pending","approved","rejected"]`。
- dp15 注册问句 `gate_decision: ["continue","narrow","revoke"]`（`decision_points.py:768-775`）——与 SPEC 的 approve/steer/need_fix/reject 不同，也不是别名。
- `decision_points.py` 只有 25 个 `dpN-*` id；`shared/decide-registry.generated.ts:37-660` 同集合。无 `dp-route` / `dp-auto`。

**PM 侧可观测面现状**
- `decision-tool.ts:1808-1828`：`tracePath` 仅在 `PI_WORKER_TASK` 存在时派生；PM 分支不传 taskPath → PM 的 ask/receipt **不写 trace.log**，只在 session transcript + Python archive 留痕。

### 3. 事实 / 目标 / 方案 / 权限未定（分开）

| 类别 | 内容 |
|---|---|
| 已观测事实 | 上述 path:line；gate 二值；注册表 25 旧 id；PM 无 trace；`asked` 进程内；反向角色门缺失；dp15 问句与 SPEC 选项不同 |
| 已锁定目标（spec） | 八入口、四选项语义、steer/need_fix 交 PM 发起后继、选择≠执行、同事项不重复审批、失败默认阻塞 |
| 候选方案（本文提出，未批准） | §4 的 A/B/C/D 及接口建议 |
| 权限未定 | 新增 id/字段/schema、注册表迁移、PM 侧新写面、session entry 承载 ask-join、AC 通过判定——均未获授权，本文不实施 |

### 4. 方案比较（至少两种；含被否方案）

| 维度 | A 固定直调（现状扩展） | B 每事路由优先 | C 混合（建议） | D 框架代发后继（否） |
|---|---|---|---|---|
| PM 准备 | 固定提示按 dp 生成材料；PM 直填 | 先答主体/对象/问题，再答目标 dp 材料（两次） | 固定节点直调；临时问题一次路由；后继走目标 dp | 框架据 gate 答案自行组材料 |
| 角色资格 | 结构角色已具备（`index.ts:82-102`），但仅单向门 | 路由不得授角色，需额外主体校验 | 沿用结构角色 + 补反向门 | 机器无角色资格，违反"选择≠请求" |
| 关联/幂等 | 每调用新 `logical_id`，event_id 派生 | 两次调用两个 decision_id，需显式关联（否则同事项双批） | 路由本身一条、业务一条，用 `route_decision_id` 关联 | 无 PM 上下文材料，只能造 |
| 失败面 | `input-incomplete`/UNAVAILABLE 已 fail-closed | 路由成功但业务失败 → 两次失败面，需分别呈现 | 同上，但固定节点不付路由成本 | 失败无法归因到 PM |
| AC-040/041/049 | 041 满足（零强制路由）；040 缺 | 040 满足；041 有"强制路由"风险 | 同时满足，且 049 由 PM 发起 | 违反 049/041 |
| 成本 | 1 次调用 | 2 次（临时问题可接受，固定节点浪费） | 按节点类型分派 | 省 PM turn，但伪造主体 |

- 方案 A 的证据支撑：`decision-tool.ts` 的单入口 + 每 dp 固定提示（`DECISION_MATERIAL_PROMPTS`）已是"固定格式直调"。
- 方案 B 的必要性：SPEC §1.5 要求临时问题先整理再路由；但把路由也用于固定节点会违反 AC-041 的"额外强制路由次数为 0"。
- 方案 D 被否的硬理由：gate 答案不携带 dp-pm-steer 需要的四项材料（目标/真实执行/约束/在途写面），框架无写面权限也不持有 PM 上下文（`pm-orchestrator.ts:2081-2090` 的 RETIRED 注释记录了同类越权的历史教训）。

### 5. 推荐设计（建议，未批准）

**(1) 事件层**：事件只作为带 join key 的只读事实注入。需要判断的（检查点风险、终态回读、gate pending）用 `deliverPmAlert`；纯信息用 `displaySummary`。同一 `(decision_id, stage)` 只投递一次；不得为"补一次提醒"再注入第二段审批请求。

**(2) 业务准备**：材料 schema 继续由生成注册表单一权威（`DECIDE_REGISTRY`），PM 按固定提示逐字段填；未知保持 unknown，缺字段零 spawn 拒绝并回报字段名；不得用当前状态回填历史。

**(3) 固定直调 / 临时路由**：固定业务节点（派发、编排、签收、gate、QG）直调；临时问题由 PM 整理"决策主体 / 判断对象 / 具体问题 / 2..5 可区分候选"后经 dp-route 选入口；route 的答复只能是一个入口 id + 依据，**不得携带业务结论**，业务结论必须由所选入口自己的调用产生。复合问题先拆成独立事项，每事一次。

**(4) gate steer/need_fix 后继（AC-049 核心）**：gate 结果里携带 `recommended_entry: dp-pm-steer | dp-auto` 与理由，标注为**建议而非选择**。PM 收到后自行准备该入口的材料并发起调用；四态分开记录：
- 选择（gate）：`answers.gate_decision = steer|need_fix`，同时 `acted=false`（gate 未放行）。
- 请求（PM）：后继调用的 `decision_id`/`logical_id`，与 gate 的 `decision_id` 通过 `parent_decision_id` 关联；重复发起同 `(parent_decision_id, entry)` 应被拒或记 duplicate，不产生第二条业务事实。
- 失败：后继调用 `available:false` → 阻塞并显示 `unavailable`/`missing_fields`，`acted=false`，零副作用；不得用 gate 答案补造。
- 执行：PM 在既有权限内做真实动作（派发/写 steer 文件/收窄任务卡），再 `decision_receipt executed=<closed action>`；未执行不得回执。
- 结算：`settled` 只表示本轮处理结束（ok/rework/...），**不等于任务完成**，也不改写 gate 的未放行事实。

**(5) 关联与幂等**：join key = `(key, task_key, dp, logical_id)`；`event_id` 由 `(logical_id, stage)` 派生（沿用 dp1 的 `buildDp1LifecycleFact` 形态）。重放同事件→duplicate；实质变化（目标/授权/证据版本）才允许新 decision_id 并留 `retry_of`/`parent_decision_id`。

**(6) 写面建议（仅设计）**：业务事实仍只由 Python 单写者（`mw decide run` / `decide lifecycle` / `decide sign`）落账；PM 侧落地不需新文件——`asked` map 的 join 记录建议复用**既有 pi session entry 机制**（同 `WATCH_ENTRY_TYPE`、`GATE_REMINDER_ENTRY_TYPE` 的先例），以避免第三套账本；禁止写 `.mw/**`、`_autopilot/**`、他 key 与 `_index.parallel`。若将来要 PM 级 trace，须先单独批准新写面（当前 PM 无 `tracePath`）。

### 6. VC 断言（L0 结构 / L1 单测或 hermetic 集成 / L2 生产路径隔离测试）

| AC | L0（静态可核） | L1（faux runner / 临时项目） | L2（真实 mw.py，临时项目，无 provider） |
|---|---|---|---|
| 011 唯一归属/重放 | 每入口有 owner 表项；无同对象双入口 | 同 (object, evidence_version) 连发两次 → 1 条有效审批 + 1 duplicate | 归档行数=1，`duplicate` 可见 |
| 012 不可用阻塞 | 失败分支零副作用、无默认候选；无本地拼 id | runner 返回 timeout/非零/无 answers → `available:false`、`spawned` 如实、`acted` 不出现 | CLI 不可用（PATH 无效）→ 阻塞、archive 0 行 |
| 014 链路真实 | producer/writer/consumer 各有 path:line | 断言 consumed/executed/settled 只由各自 writer 写 | `decisions.jsonl` 三行 join 同一 logical_id，字段不互相冒充 |
| 040 路由 | route 输出仅入口 id + 依据 | 业务 dp 未被调用（spy=0） | 路由后受门控动作 0 次 |
| 041 直调/角色 | 固定节点无 route 前置；反向角色门存在 | PM 调 worker dp → 拒绝零 spawn；worker 调 PM dp → 拒绝 | 同上，archive 无新行 |
| 042 dp-auto 候选 | 只接受已准备候选 id 集合 | 篡改候选 id → 拒绝；未准备方案 0 | 选择=候选之一，acted 由服务给 |
| 043 异常对照 | 三类失败独立词汇 | 非法/缺失/不匹配选择各 0 副作用 | 服务 UNAVAILABLE 默认放行次数 0 |
| 044 dp-w-type | 候选精确 4 值；vision 能力门 | 无图像能力 → 零启动 | 派发卡 type=vision 且门禁通过才 spawn |
| 045 dp-pm-steer | 四值；不降目标约束 | 每分支产出可区分编排事实 | 选择与执行证据不同行 |
| 049 gate 后继 | gate 返回 recommendation 而非请求 | steer → PM 发起后继（可核调用）；无在途时不重复；失败/选择/执行 分别可见 | 后继调用 1 次，gate 未放行 |
| 050 执行/结算 | executed 动作闭集；task_before/after 来源 | 未执行回执 → refused；时间非递减 | 行关联同 key/task/logical_id |
| 051 null vs [] | 快照 null 与 [] 类型分离 | null 不回填、[] 不改 null | 签收材料 [] 不被改成 null |
| 052 并发/版本 | 文件锁与独占面既有协议 | 并发两次同事项 → 1 审批；双写同文件 0 | 锁文件 0 绕过，重放 duplicate |

### 7. "当前自动 dp3 缺材料/混填"与未来角色设计必须分开（RQ15 要求 3）

- 现状事实：dp3 是 Worker 可达性 dp，但 PM 窗口同样能调用（无反向门，`decision-tool.ts:214` 仅 dp2/dp25 受限）；dp3 材料走 `input-incomplete` 零 spawn 拒绝，缺字段名可观测。
- 目标态：dp-w-check-task 是 Worker 自身判断，PM 不得代发；终态 fire-and-forget，PM 自行吸收。二者不是同一件事——不得用"当前 PM 能调 dp3"证明目标态角色设计，也不能用目标态否定今天已存在的事实记录。
- 同理：dp-pm-steer 的四选项今天在 dp2 注册表里已有（narrow/split/direct-exec/escalate），但 gate 的 steer/need_fix 后继链路是**新增**，不能因选项同名就认为接线完成。

## 残留与未验证

- `pm/ui-bridge.ts` 未逐行读完（5086 行）：只覆盖 `decision`/triage/派发/投递相关段（195-554、595-755、3300-3460）与符号索引；其余（RAG、mw 命令、doctor、decide CLI 转发等）未读，可能另有与 PM 事件相关的入口。
- 未读 `pm/task-dispatcher.ts`、`pm/triage-client.ts` 全文：`dispatchTask` 的写面判据、`triageDispatchEnvelope` 的传输细节未逐行核实。
- `packages/multi-workers/*.py` 只按行取证（注册表/常量/问句），未读 `decide_for`、`decision_lifecycle`、`decision_signoff_result` 实现体；"单写者/幂等/字段闭合"的结论来自 TS 侧注释与调用面，未在 Python 侧逐行验证。
- 未验证：PM 传入的 `key` 是否与被 watch 的 key 一致（PM 分支 `ownerKey` 未定义，`decision-tool.ts:1878` 直接采用参数），存在跨 key 记账风险；`asked` map 用 session entry 持久化的可行性未验证（仅提出机制先例）。
- 未运行任何测试/check/build；未启动服务；无额外 `ask_decision`/provider 探测。本文不构成 AC 通过、QG 或签收证据。
- 时间盒：25 分钟内完成只读取证，源码全读仅限 `decision-tool.ts` / `pm-orchestrator.ts` / `index.ts`。

## 上下文来源

- `.agenticdoc/goal.md`（Goal/Constraints；本任务锚点 `goal.md:5` 已读）。
- `.agenticdoc/mw-dp-consolidation/spec.md`（§0 Goal Alignment、§1.1 八入口、§1.2 dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key、§1.5 固定直调与 dp-route、§3 AC-011/012/014/040-045/049-052、§4 风险与未决项）。
- 本任务卡 `.agenticdoc/mw-dp-consolidation/workers/dpc-rq15-design-pm/workers/...`（seed 卡 RQ15 要求 1-5 与交付格式）。
- 源码（相对仓库根）：`packages/coding-agent/src/extensions/agent-team-loop/index.ts`、`pm/decision-tool.ts`、`pm/pm-orchestrator.ts`、`pm/ui-bridge.ts`（部分）、`autopilot/console.ts`、`autopilot/gate-writer.ts`、`autopilot/status-model.ts`、`shared/decide-registry.generated.ts`、`packages/multi-workers/decision_points.py`。
- 关联既有证据（只读引用，未改写）：`evidence/dp2-pm-convergence-definition.md`、`evidence/dp3-worker-initiated-discussion.md`、`evidence/gate-four-option-confirmation.md`、`evidence/pm-question-action-context-review.md`。
