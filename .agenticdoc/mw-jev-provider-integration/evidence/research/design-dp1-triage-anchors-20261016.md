# DP-1 派发前分诊：判定链与可接入锚点（RQ-D1）

- key: mw-jev-provider-integration · worker: jev-d1-triage-anchors · 2026-10-16 · type: research
- 方法：只读调研，未改任何源码/配置，未执行 git 写操作。全部结论来自对源码文件的完整阅读；行号以当前工作区为准（实现时需复核）。
- 路径缩写：`ui-bridge.ts` = `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`；`dispatch-models.ts` = `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts`；`worker-mode.ts` = `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`；`output-writer.ts` = `.../worker/output-writer.ts`；`heartbeat.ts` = `.../shared/heartbeat.ts`；`task-frontmatter.ts` = `.../shared/task-frontmatter.ts`；`pm-orchestrator.ts` = `.../pm/pm-orchestrator.ts`；`dispatch.py` = `packages/multi-workers/autopilot/dispatch.py`；`conductor.py` = `packages/multi-workers/autopilot/conductor.py`；`mw_common.py` = `packages/multi-workers/mw_common.py`；`timeline.py` = `packages/multi-workers/autopilot/timeline.py`；`mw.py` / `launcher.py` = `packages/multi-workers/`。

---

## Q1 任务类型如何确定

### TS 侧（PM 派发面）

- 判定源与顺序：**调用参数显式声明优先，无推断**。
  - `dispatch_worker` 工具（ui-bridge.ts:2235 注册）解构参数 `task_key / card_path / description / cli / model / model_reason / type / images / key / allow_foreign_write`（ui-bridge.ts:2297-2308），type 传入 `resolveDispatchType(cli, type ?? "")`（ui-bridge.ts:2346）。
  - `/worker` 命令（registerWorkerCommands ui-bridge.ts:2790）的 `--type` 旗标走同一函数（ui-bridge.ts:2858）。
  - `resolveDispatchType`（ui-bridge.ts:1215-1238）：显式值必须 ∈ `DISPATCHABLE_TYPES`（dispatch-models.ts:75，= coding / review / research / rag-research / vision，注释明示 rag-research 被 Python 侧 `conductor_dispatchable=False` 拒绝）；**省略 type 的兜底 = legacy cli 映射**：pi→coding、claude→review、codex→codex（ui-bridge.ts:1221-1223，保持旧派发字节不变）；非法值拒绝派发（ui-bridge.ts:1224-1230）。
- role 映射（仅决定 dispatch.yml 角色与覆盖审批，不改 type）：`DISPATCH_ROLE_BY_TYPE`（dispatch-models.ts:56-69，10 个 type→4 个 role）；`roleForTaskType`（dispatch-models.ts:78-80）**未知 type 兜底 = "coding"**。
- worker 读侧（task.md `type:` 头是全链唯一事实源）：`readTaskType`（task-frontmatter.ts:141-157）只读 header 区 `type:` 行，provenance source ∈ header / body / missing / invalid；header 缺失但正文有 `type:` 时 source="body"，框架**忽略 body 值**并写 `[HEADER] body-type-ignored count=… escaped=<bool> role=<role>` 审计行（worker-mode.ts:806-815，appendHeaderAudit :795-823；越权升级判定 findTypeEscalation task-frontmatter.ts:167-180）；未注册 type 兜底 = fallback 工具集 + `[HEADER] unregistered-type-fallback` 审计行（worker-mode.ts:817-821）。conductor 来源的 task 另有 worker 侧二次校验 `dispatchRefusal`（worker-mode.ts:826-840：origin=conductor 且类型未注册 → 拒绝运行，双保险 D-107）。

### Python 侧（conductor 自动派发面）

- 判定源：**各循环调用点的硬编码字面量**，与卡片 frontmatter / 任何分诊判断无关：
  - `roadmap-writer`：conductor.py:1204（`_dispatch_roadmap_writer`）
  - `phase-writer`：conductor.py:1647（`_advance_key`）、:2075（`execute_loop`）、:5435（`_xkey_proposal_one`）
  - `verifier`：conductor.py:1723（`_advance_key` 的 L2 门；read_scope 强制含 `.agenticdoc/<key>` 与 `.agenticdoc/goal.md`）
  - `reviewer`：conductor.py:2665 / :2715 / :2750 / :2822（`_verify_loop` L3 各轮与重试支）
  - `repair`：conductor.py:2867（`_verify_loop` 修复支）
- 校验与兜底：`dispatch()`（dispatch.py:1335）在 :1421-1427 用 `REGISTRY`（dispatch.py:85-128，Python 侧 7 个 type：roadmap-writer / phase-writer / verifier / reviewer / repair / rag-research / vision；`DispatchType.conductor_dispatchable` :82）拒绝未知类型；PM-only 类型（rag-research 等）在 :1431-1436 拒绝；verifier 强制非空 read_scope（:1437-1442）。
- role 映射：`TASK_TYPE_TO_ROLE`（mw_common.py:144-156，与 TS 镜像）；消费点 dispatch.py:216 为 `.get(task_type, task_type)`。**注意不对称**：Python 未知 type 的 role 兜底 = type 本身，TS `roleForTaskType` 未知兜底 = "coding"（dispatch-models.ts:78）；launcher 侧 `resolve_dispatch_model` 也是 `.get(task_type, "coding")`（dispatch-models.ts:50-53 注释声明）。

### 结论（Q1）

TS 侧 type 的唯一判定源是 **PM 调用参数**（显式 > legacy cli 映射），写进 task.md `type:` 头后成为全链事实源，worker 读侧对 body 冒出的 type 只审计不采纳；Python 侧 type 是**各循环的编译期字面量**，不存在"分诊"。未知 type：TS 派发面拒绝（非法值）/ legacy 映射（空值），worker 读侧 fallback 工具集 + 审计行，Python 侧 dispatch 直接拒绝。

---

## Q2 风险等级现状

**结论：派发面上不存在显式风险等级字段。** task.md 头字段全集（Python `render_task_md` dispatch.py:852-1003；TS `writeDispatchTaskMd` ui-bridge.ts:2180-2233）、`_workers.parallel` 行字段（reconcile_orphans 的 serialize_entry conductor.py:6489-6503；dispatch.py:1520-1530）、`DispatchType`/`REGISTRY`（dispatch.py:71-128）均无 risk 字段；multi-workers Python 全库检索 "risk" 仅命中 docs（dual-toolchain-practice-guide.md:365-366，实践案例叙述）与一条 T-19 注释（conductor.py:8301）。watchdog 也不消费任何 risk：idle 看门狗 DEFAULT_IDLE_MS（worker-mode.ts:241，PI_WORKER_IDLE_MS 可调 :255-259）、工具空闲 :275-281、墙钟预算 :247-256，全部与 checkpoint risk 无耦合。

最接近的三个替代物（按接近程度排序）：

1. **checkpoint 收敛风险（运行期信号，非派发期输入）**
   - 产生者：worker 运行时框架（非 worker 自评）。`computeRisk`（worker-mode.ts:351-370）由机器信号算出 low/mid/high：elapsed vs anchor、writes=0、phase 进度停滞、repeat_top≥4；writeless 角色换用落盘信号（landed / artifactPresent / progressDone，LandingSignals worker-mode.ts:373-383，W1-W4 规则 :340-350）。自评只提供 `converging=yes` 佐证（PROGRESS_DONE_RE worker-mode.ts:382-383）。
   - 节奏：30 分钟锚 + 10 分钟刷新（CHECKPOINT_ANCHOR_MS / CHECKPOINT_REFRESH_MS worker-mode.ts:243-244；anchor = min(30m, budget/2)，checkpointAnchorMs :287）。
   - 落盘：trace.log `[CHECKPOINT] … risk=<low|mid|high>` 行（appendCheckpoint output-writer.ts:672-710；writeless 变体 appendLandingCheckpoint worker-mode.ts:3339-3357 直写 trace.log，追加 land=/last_land=/artifact=/done= 字段）+ progress.md `[machine]` 行（worker-mode.ts:3413-3425，writeCheckpoint :3376-3436）。回读协议 CHECKPOINT_LINE_RE（heartbeat.ts:94-96）。
   - 消费点：(a) PM watch widget 运行行 `ck<N>m <risk>⚠`（ui-bridge.ts:787-791）；(b) 其他 key 汇总 `risk=high:<K>`（ui-bridge.ts:839-898，:894 读 readTaskProgress().checkpoint.risk）；(c) **PM 升级**：pm-orchestrator.ts:1636-1660 每 tick 扫 running 行，risk 非 low 且属本窗口（watched key ∪ 本窗口派发）→ 每任务一次升级，走 `deliverPmAlert`（triggerTurn 唤醒 PM 判断 continue / descope / kill+split / takeover，pm-orchestrator.ts:1643-1646 与 ui-bridge.ts:189-197）；low 只进 widget（:1642-1643 注释）。这正是 goal.md Key Constraints "mid/high risk 经 triggerTurn 升级 PM" 的实现位置。
2. **phase（派发时刻唯一与任务成熟度相关的显式信号）**：`dispatchPhase`（ui-bridge.ts:1244-1252）/ `_owner_phase`（dispatch.py:136-158）读 owner key pm-state.md 的 `- Phase:` 行；未知 phase 不写字段（永不猜测，T-14）。DP-1 在派发时刻能拿到的"风险代理"只有它 + 卡片/描述文本。
3. **write-scope 残余风险（审计面，与分诊无关）**：`risk=deny-basename`（worker-mode.ts:2224、:2335、:2356-2365 `[WRITE_SCOPE]` 行）→ `write-scope-risk` 告警（pm-orchestrator.ts:531-534 kind 定义、:651-679 recordWriteScopeResidualRisks）。

DP-1 若需要"风险等级"作为 Jev 输入：现状只能喂 phase + 卡片/正文文本；checkpoint risk 是运行期反馈回路（可作为 Jev 后续波的 state 增强，不是 DP-1 的输入）。

---

## Q3 派发前一刻可用的输入数据面

TS `dispatch_worker`（ui-bridge.ts:2235-2494）在 `planDispatchFrontmatter` 调用点（:2440）已持有：

- 入参全集：task_key、card_path、description（任务正文全文）、cli、model、model_reason、type（请求值）、images、key（owner key）、allow_foreign_write（ui-bridge.ts:2297-2308）。
- ownerPhase：owner key 当前 phase（:2356，dispatchPhase 读 pm-state.md）。
- cardGate：派发卡完整校验产物 `{headerPath, sha256, sections}`（readDispatchCard 调用 :2394-2402；函数 ui-bridge.ts:2112-2145；sections 含 type + 上下文/要求/交付格式 + 类型特有节；信封种子强制"goal.md 引用 + 至少一个 path:line 引用"，refusal 文本 ui-bridge.ts:2147-2157 明示）。
- indexStore：`_index.parallel` 行（owner key 解析 resolveOwnerKeyWithSync :2318；跨键守卫 foreignLiveClaimRefusal :2325）。索引行携带 Phase/ClaimId/Deps 事实（pm-orchestrator.ts:500-504 注释："a guessed index row would invent Phase/ClaimId/Deps facts"）——即依赖数据可从 indexStore 拿。
- 其他：ragCheck（:2312）、写意图判定 judgeWriteIntent（:2377-2392）、docs gate dispatchDocGaps（:2357-2363，phase 分层）。

Python `dispatch()`（dispatch.py:1335）在 `render_task_md`（:1488-1502）前持有：owner / stem / task_type（字面量）/ prompt（卡片正文或合成信封）/ loop / attempt / read_scope / model / card（`dispatch_card` :569 或 `synthesized_card` :778）/ `_owner_phase`（:136-158）/ target config（:1445-1458）/ rag config（:1477）/ timeout 与 read caps（:1471-1474）。conductor 侧没有 PM 窗口上下文；卡片为合成信封时正文最简（synthesized_card :778-819）。

---

## Q4 既有"派发前校验/注入"挂点盘点

TS：

- `validateModelValue` 调用点：ui-bridge.ts:1305（`planDispatchFrontmatter` 内部，定义于 dispatch-models.ts:167-204）、ui-bridge.ts:3340（`/mw model set` 时校验角色值）。
- `planDispatchFrontmatter` 调用点：ui-bridge.ts:2440（dispatch_worker）、:2938（/worker）——**两个 PM 入口共享的唯一模型/能力计划点**（函数 ui-bridge.ts:1257-1420+：role 解析 :1277、images 三态判定 :1285-1297、validateModelValue :1305、vision 自动路由 :1318-1333、能力门 :1336-1352、覆盖需 model_reason :1378-1385）。
- 注入链 `writeDispatchTaskMd`（ui-bridge.ts:2180-2233）：write_scope 合并、allow_foreign_write 合并、卡片头（card_path / card_sha256 / envelope_producer）+ 卡片种子节、write-surface 契约节注入。
- 派发守卫链顺序（dispatch_worker）：rag gate :2312 → owner key :2318 → 跨键 :2325 → cli :2334 → type :2346 → docs gate :2356-2363 → taskDir 冲突 :2370-2376 → 写意图 :2377-2392 → 卡片 G-1 :2394-2402 → 模型 plan :2440-2454 → writeDispatchTaskMd :2456 → dispatchTask 入队 :2473 → 回执 :2491。全部在**任何 fs 写之前**，拒绝零副作用。

Python（`dispatch()` 校验/注入链，dispatch.py:1400-1530）：

- run.json 状态 :1400-1419 → REGISTRY 未知类型 :1421-1427 → conductor_dispatchable :1431-1436 → verifier read_scope :1437-1442 → target config :1445-1458 → scope/deny_globs 展开 :1459-1460 → RAG 配置（不阻断）:1477 → profile_block :1480-1495 → caps/timeout :1471-1474 → 卡片或合成信封 :1476-1487 → render_task_md :1488-1502 → **workers.lock 临界区**（:1519 起）写 task.md + queue row。
- `render_task_md` 注入清单（:852-1003）：type（:947）、card_path/card_sha256（:949-956）、phase、images、model、envelope_producer、origin/loop/attempt、timeout、read_scope、l2_read_file_cap/l2_read_byte_cap、deny_globs、write_face 行、正文（信封三节 + §1.2 类型补全 `_envelope_card_body` :681-749 + 恢复契约节 `recovery_contract_section` :655-679，`RECOVERY_CONTRACT_TYPES` :637-653）、profile_block、RAG block（`_inject_rag_block` :199-222）。信封校验 `dispatch_card`（:569-614）、`_write_face_verdict`（:1215）。

**天然适合挂一次外部决策调用的点**（同步、失败可忽略、不改派发结果）：

- TS：`planDispatchFrontmatter` 入口（ui-bridge.ts:1257）——单点覆盖两个 PM 入口；建议只并入 `echo` / 回执文本即可，不改任何 frontmatter 字段。
- Python：`dispatch()` 的 REGISTRY 校验之后、workers.lock 临界区之前（dispatch.py:1427-1470 之间）——**绝不可放临界区内**（同步 HTTP 会拉长锁持有）。

---

## Q5 旁路建议的落点候选

| 面 | 写入 API（path:line） | PM 是否自然看到 |
|---|---|---|
| 派发回执文本 | dispatch_worker 工具返回值 ui-bridge.ts:2491-2494（已拼 `modelPlan.echo`）；/worker `ctx.ui.notify` ui-bridge.ts:2982 | **是（最自然）**：这是 PM 刚发起的工具调用的返回文本，直接进它的上下文 |
| PM 主动唤醒 | `deliverPmAlert`（ui-bridge.ts:189-197，sendMessage + triggerTurn:true；finish/中期升级共用通道） | **是**：唯一能唤醒 idle PM 的通道；代价是消耗一个 agent turn，不宜每派发一次都发 |
| autopilot ledger 派发告警 | `recordDispatchAlarm`（pm-orchestrator.ts:623-646）→ `.agenticdoc/_autopilot/auto-decisions.jsonl`，`phase:"dispatch-alarm"` 行（:620 注释：决策消费者按 `phase=="decide"` 过滤，不会误读） | 部分：持久、doctor/人可查，但**不主动**进 PM 上下文；须配合 deliverPmAlert 才"自然看到" |
| worker trace.log 机器行 | `appendCheckpoint`（output-writer.ts:672-710）、`appendHeaderTraceLine`（worker-mode.ts:781-793）、`[WRITE_SCOPE]` 行（:2356-2365）；PM 读回 `readTaskProgress`（heartbeat.ts:112-152） | 派发**后**可见（widget/升级消费）；派发前 trace.log 不存在（worker 未启动）。但"派发前写 trace.log 审计行"已有先例：orphan repair 的 `[ENVELOPE_FALLBACK]`（pm-orchestrator.ts:1046-1051） |
| autopilot timeline 事件 | `Timeline.append`（timeline.py:308；类 :282、路径 :123）；查询 `query_events` :422 / `tail_events` :472；CLI `mw.py:2579` query_events | conductor 侧建议的自然落点；PM 不主动看到（gate-reminder 通道 readGateReminders→deliverPmAlert，pm-orchestrator.ts:1604-1616，只覆盖 gate 类 ledger 行，另接需改水位逻辑） |
| launcher.log | `.mw/launcher.log`（mw.py:281-285，每 serve 截断；路径 mw_common.py:2594）；写法先例：模型覆盖行 launcher.py:220-226 | 否：仅 doctor 检查（mw_common.py:3887 FATAL 行、:4086 错误计数），PM 日常不读 |
| `.mw/` 下通用报告文件 | 不存在通用报告面（doctor 输出走 CLI stdout） | — |

结论：本波"旁路建议必须 PM 可见"的最小组合 = **回执 echo（TS 入口，天然可见）+ recordDispatchAlarm（持久留痕）**；conductor 侧 = **timeline 事件 + 可选 gate-reminder 式唤醒**。

---

## DP-1 可插入点候选表

| 候选 | 位置 | 同步成本 | 失败影响 | 是否改变派发行为 |
|---|---|---|---|---|
| A. `planDispatchFrontmatter` 入口挂 Jev 调用 | ui-bridge.ts:1257（两个 PM 入口共用：:2440 / :2938） | 每次 PM 派发一次同步 HTTP，阻塞工具调用，须设短超时 | 包 try/catch 失败忽略 → 建议缺失，派发照常（与 validateModelValue 的 fail-open 风格一致，dispatch-models.ts:180-186） | 否（建议只进 echo/回执/ledger，不写 type/role/model 字段） |
| B. dispatch_worker handler 内、writeDispatchTaskMd 之前 | ui-bridge.ts:约 2436（cardGate :2394 之后、:2440 前后） | 同 A；此处数据面最全（description 全文 + card sections + ownerPhase + index 行）；与 A 二选一即可 | 同 A；且发生在任何 fs 写之前，拒绝零副作用 | 否 |
| C. `dispatch()` 校验段（REGISTRY 检查后、临界区前） | dispatch.py:1427-1470 之间 | conductor tick 内一次同步 HTTP；**绝不可进 :1519 起的 workers.lock 临界区** | 失败忽略 → conductor 行为不变；建议走 `Timeline.append`（timeline.py:308） | 否 |
| D. 建议"PM 可见"的投递面（与 A/B/C 配合，非独立挂点） | 回执 ui-bridge.ts:2491/:2982；`recordDispatchAlarm` pm-orchestrator.ts:623；`deliverPmAlert` ui-bridge.ts:189 | 低（本地 append + 可选一次 triggerTurn） | 写失败 best-effort（pm-orchestrator.ts:643-646 已是既有契约） | 否 |

推荐：DP-1 本波挂 **A（或 B）+ D**；conductor 自动派发路径留待后续波用 **C**。

---

## 覆盖面结论（Q6）

派发入口全景与锚点覆盖：

1. **PM 手动派发 ×2**：`dispatch_worker` 工具（ui-bridge.ts:2235）与 `/worker` 命令（:2790 起；:2858 / :2938）——**都过 `planDispatchFrontmatter` → 锚点 A/B 覆盖 100%**。
2. **conductor 自动派发 ×13 个调用点**：`dispatch.dispatch(` 分布于 `_dispatch_roadmap_writer`（:1204）、`_advance_key`（:1647 / :1687 / :1723）、`execute_loop`（:2075）、`_verify_loop`（:2665 / :2715 / :2750 / :2822 / :2867 / :2875）、`_xkey_proposal_one`（:5435）——**完全绕过 TS 锚点**；只有挂 C（dispatch.py:1335）才能覆盖。类型集合：roadmap-writer / phase-writer / verifier / reviewer / repair。
3. **孤儿修复重派**：`dispatchOrphanCandidates`（pm-orchestrator.ts:1050-1113）——只把**既有** task.md 重新入队（pickWorkerRoute/readModel 读旧头 :1103-1106），**不重做分诊**，不过 planDispatchFrontmatter；仅补信封（ensureServiceEnvelope :1031-1053）。
4. **conductor 孤儿重插**：`reconcile_orphans`（conductor.py:6469-6520，`"model": ""` 在 :6500）——同样只重排队，无分诊。
5. **worker 自我分拆**：**不存在**——worker 模式不注册任何工具（ui-bridge.ts:2501-2507 ack 注释明示 "worker mode never registers tools"；worker-mode.ts 全文无 registerTool）。"分拆"经由 checkpoint 升级（pm-orchestrator.ts:1636-1660）回到 PM，由 PM 重新走入口 1，间接被 A 覆盖。

比例（结构性口径，非运行时统计）：以"发生分诊决策的新派发调用点"计，全景共 **15 个**（TS 2 + Python 13）。仅挂 A：2/15（≈13%，全部 PM 发起的派发）；**A + C：15/15（100%）**。两条重派路径（3、4）没有分诊时刻（type 已随旧 task.md 固化），DP-1 任何挂点都覆盖不到、也不需要覆盖。Jev 的 `state`+`questions` 接口在 A 处可拿到 Q3 全部输入；在 C 处输入较薄（无 PM 窗口上下文，合成信封正文最简，synthesized_card dispatch.py:778-819）。

---

## 残留与未验证

- conductor 各调用点的 loop 预算分支语义只核对了 type 字面量与所属函数，未逐分支追预算流；不影响锚点结论。
- 未运行任何派发流程实测（只读调研）；全部行号以当前工作区快照为准，实现前需复核。
- launcher 侧 `resolve_dispatch_model` 的 Python 定义未展开读（TS 注释 dispatch-models.ts:50-53 已声明其 `.get(task_type, "coding")` 兜底）；若后续波要动 launcher 链需补读 mw_common.py。
- Python/TS 未知 type 的 role 兜底不对称（type 本身 vs "coding"，Q1）是否为有意设计，未在文档中找到裁决记录。
