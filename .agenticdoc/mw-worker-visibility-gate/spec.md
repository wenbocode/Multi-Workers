# Spec: mw-worker-visibility-gate

> Key: mw-worker-visibility-gate
> 创建时间: 2026-09-23
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「在 pi coding agent 之上构建一个 Agent Team 协作框架，让一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目」中的两块：
  1. **文件驱动的去中心化协调**（_workers.parallel / _index.parallel / goal.md）——派发门禁是协调面的一部分，它现在把"新 key 的调研工作"逼出 key（逼到 `_scratch`），等于让协调面自身制造孤儿任务；
  2. **Worker 执行过程中追踪 goal 一致性**——面板看不见的 worker 无法被 PM 追踪，跨 key 派发的 worker 现在既不在面板、也不触发发散升级。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器——协调一律通过文件系统（`_workers.parallel` / `_index.parallel` + 文件锁），本 key 的所有判定必须可由"读文件"复现；
  - GC-2: 不修改 pi 核心——所有改动落在 `packages/coding-agent/src/extensions/agent-team-loop/**`（Extension API 面）；
  - GC-3: 工具白名单按任务类型不变——`TOOL_ALLOWLISTS` / `toolsForType` / Python dispatch REGISTRY 逐字不动；
  - GC-4: goal.md 低churn——本 key 不修改 goal.md。
- 冲突：无。
- 预期收益：本 key 达成后对项目目标的具体贡献（可观察、可验证；done 时在 achieved.md 对照判定）
  - **收益 1（可观察）**：新 key 在 SPEC 相位即可承载调研型 worker——`dispatch_worker` 在 design.md 缺失但 spec 侧文档齐备时放行，`_scratch` 不再是"新 key 调研"的必经逃生门。判定方式：构造一个 phase=SPEC 且 design.md 缺失的 key，dispatch 一次 worker，返回非 blocked 且 `<key>/workers/<task>/task.md` 存在（AC-001）。
  - **收益 2（可观察）**：面板对"本窗口派发但他键所有"的任务有且仅有一行聚合提示，含 owner key、状态计数与 risk=high 数量；PM 不需要 `list_tasks` 也能发现跨 key 的发散/失败。判定方式：构造 watched key ≠ 派发 key 的场景，断言面板行（AC-006~AC-009）。
  - **收益 3（可观察）**：claim 身份不再分叉——TS takeover 后 `pm-state.md` 的 `- Claim-Id:` 与索引行 Claim 列逐字相等，且后续按 pm-state 判 liveness 的代码不会误判抢占。判定方式：takeover 后逐字比较两处值（AC-010）。

## §1 功能概述

### 1.1 目标

修三个彼此独立但同源于一次真实事故的协调面缺陷（2026-09-23，PC3 窗口，key `h0h1-decision-baseline`）：

1. **派发门禁与相位脱钩**：`dispatchDocGaps()` 一次性要求 spec + design 两侧全部文档与证据，与 owner key 的当前相位无关。新 key 在 SPEC 相位永远过不了 → 关键工作被 `_scratch` 兜底，证据落在 key 而 task/queue 落在 `_scratch`，追溯链断开；更糟的是 `design-*` 证据本应由 design 阶段派出的 research worker 产出，而该 worker 恰被这条门禁挡住 —— 门禁制造了自指循环，只能靠手写"零调研声明"绕过。
2. **面板与他键任务不可见**：`mw-task-scope-isolation` 已把 `list_tasks` / `ack_worker_result` 的可见面扩到"本窗口派发过的 task_key"（`ownedByThisWindow`），但底栏面板 `renderWatchLines()` 仍只用 `ownerKeyOf(e) === key`，且函数签名拿不到 `dispatchedTaskKeys`。结果是同一批队列行"工具看得见、面板看不见"。
3. **claim 身份双写分叉**：`- Claim-Id:` 有两个写入者、两套 pid 语义——`update_index.py claim` 用短命 python 进程的 `host:os.getpid()`，`switch_key`/`IndexStore.claim` 用 pi 窗口进程的 pid 重写索引行而不动 pm-state。索引行是权威（`implementation-gate.ts` / `claimState` 都读它），pm-state 只是镜像，但没有任何机制保证两者同值。

### 1.2 技术栈 / 语言

TypeScript（pi Extension API，Node strip-only 可擦除语法）+ 既有 vitest 测试面。本 key **零 Python 行为改动**（框架脚本属另一个 git 仓库，见 §1.4）。

### 1.3 核心用户场景

1. 场景 A：PM 新建 key 后处于 SPEC 相位，需要先派 2 个调研 worker 收集 design 侧证据 —— 期望派发成功并落在本 key 下。
2. 场景 B：PM 因为门禁或临时原因把 worker 派到 `_scratch`（或另一个 key），随后在同一窗口工作 —— 期望底栏面板给出"另有 N 个任务在别的 key 下"的聚合提示，含失败/高风险信号，而不是静默为空。
3. 场景 C：另一个窗口接管同一 key（takeover）后，本窗口审计 pm-state 与索引 —— 期望两处 claim 值一致，且能明确知道"索引行才是权威"。
4. 场景 D：既有流程回归 —— coding 类型在 SPEC 相位照旧可派（历史口径 P-007：审查/调研任务以 `type: coding` 派发以获得落盘能力），本次改动不得把它变成硬拒绝。

### 1.4 范围说明（不做什么）

- 不包含：**框架脚本（Python）改动**——`update_index.py claim` 写极简 stub（缺 `- Updated:`）、新行 Phase 列写 `—` 而 pm-state 写 `init` 这两处不一致属 `.agents/skills/agentic-task`（框架仓库 clone）的范畴，需在该仓库单独提交并推送；本 key 只做记录（§4 残留 R-2/R-3）与 TS 侧可自洽的部分。
- 不包含：monitor 的**跨 key** risk 升级投递（`pm-orchestrator.ts:541-557` 仍按 watched key 过滤）。本 key 只保证这类任务在面板上可见并携带 risk 标记（AC-009），升级投递是否跨 key 化另案决定。
- 不包含：`_scratch` 迁移/清理、`h0h1-decision-baseline` 的数据修复。
- 不包含：任何按任务类型收紧派发的门禁（决策见 §4）。

## §2 业务约束

### 2.1 平台 / 环境

Windows（本仓主开发环境）；测试面：`packages/coding-agent/test/**` 既有 vitest 配置（`test/extensions/` 与 `test/suite/`）。rc 基线：Windows 上 `packages/agent` + `packages/coding-agent` 已有 89 项环境失败（13 + 76），只比增量。

### 2.2 性能指标

- 门禁与面板逻辑必须保持纯函数式判定（读文件，无网络/无 spawn）；`renderWatchLines` 的聚合计算相对既有 `workerStore.readAll()` 不得引入第二次全量读盘（复用同一次 `readAll()` 结果）。
- 面板每行渲染长度 ≤ `WATCH_LINE_MAX`（110 字符）。

### 2.3 安全约束

- 相位判定只读 `pm-state.md`（`StateManager.read()`）与 `_index.parallel`，不得写这两个文件（phase 变更只走 `advance_phase.py`）。
- claim 同步写 `pm-state.md` 时必须是**单行原地替换**（保留 CRLF、保留 7 段模板），不得整体重写模板；失败不得阻断索引侧 claim。

### 2.4 集成依赖

- 依赖既有模块：`shared/phase-docs.ts`（`readPhaseDocs`/`phaseDocGaps`/`DOC_GATE_HINT`）、`pm/state-manager.ts`（`StateManager.read`）、`shared/index-store.ts`（`IndexStore.claim`）、`pm/ui-bridge.ts`（`renderWatchLines`/`ownedByThisWindow`/`resolveOwnerKeyWithSync`）、`pm/pm-orchestrator.ts`（面板调用点）。
- 跨语言：Python 侧 `advance_phase.py` 是 pm-state 相位的唯一写入者，本 key 不改它。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-23T09:45:00Z，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 owner key 的 phase=SPEC、spec.md ≥500B、§0 含"预期收益"、含 ≥1 条 `AC-NNN`、`evidence/research/spec-*.md` ≥1，而 `design.md` 不存在的条件下，`dispatch_worker` 返回放行结果且 `<key>/workers/<task>/task.md` 存在（本轮门禁通过） |
| AC-002 | 在 owner key 的 phase=DESIGN、`design.md` 缺失或 <500B 的条件下，`dispatch_worker` 返回 blocked，缺项列表含且仅含 design 侧缺项（`design.md missing or under 500 bytes` 出现 1 次），且不创建 `<key>/workers/<task>/` 目录 |
| AC-003 | 在 owner key 的 phase=DESIGN、`design.md` ≥500B 而 `evidence/research/design-*.md` 数量为 0 的条件下，`dispatch_worker` 返回 blocked，缺项列表含 design 证据缺项 1 条 |
| AC-004 | 在 owner key 的 phase 取值为 `—`、空串、`INIT` 或任意未知串的条件下，门禁按 SPEC 层判定：spec 侧齐备且 design.md 缺失时返回放行（AC-001 的判定路径），不产生任何 design 侧缺项 |
| AC-005 | 在 owner key 的 phase=SPEC、`spec.md` <500B 的条件下，`dispatch_worker` 返回 blocked，且缺项列表条数等于该 key 的 spec 侧缺项数、design 侧缺项数恒为 0 |
| AC-006 | 在本窗口派发的 worker 中至少 1 行 status=running 且其 owner key ≠ watched key 的条件下，`renderWatchLines` 输出中恰好 1 行聚合提示，含该 owner key 名与该状态计数，且该行长度 ≤110 字符 |
| AC-007 | 在本窗口无跨 key 派发行（或 `dispatchedTaskKeys` 未定义）的条件下，`renderWatchLines` 输出中聚合提示行数量为 0（面板输出与本改造前逐行相同） |
| AC-008 | 在跨 key 行中含 failed 或 needs-clarification 且未 ack 的行的条件下，聚合提示行的计数包含这些终态行的数量（终态不静默） |
| AC-009 | 在跨 key 的 running 行中有 N≥1 行 `progress.md` 检查点 risk=high 的条件下，聚合提示行包含 `risk=high` 字样与数量 N |
| AC-010 | 在 TS 侧对 key K 执行 claim/takeover（索引行 Claim 列被写为本窗口 id）后，K 的 `pm-state.md` 中 `- Claim-Id:` 的值与该列逐字相等，且 pm-state 的二级标题数量与 `- Updated:` 行数量均与改造前相同（模板未被重写） |
| AC-011 | 在 K 的 `pm-state.md` 存在但缺 `- Claim-Id:` 行的条件下，同步在 `- Key:` 行之后插入该行（其余字节不变，返回值 ok=true）；当 K 的 `pm-state.md` 既无 `- Claim-Id:` 也无 `- Key:` 行时，claim 仍成功且返回 1 条 warning、文件逐字节未变 [REVISED @ 2026-09-23：原语义为"缺行一律不写+warning"；依据见 design D-111] |
| AC-012 | 在 owner key 的 phase=SPEC 的条件下，`type=coding` 的 `dispatch_worker` 调用不被相位门禁拒绝（与改造前一致，回归项） |
| AC-013 | `.agenticdoc/_pitfalls.md` 新增条目正文同时含"索引行"、"两处同值"、"liveness" 三处口径，且标注日期与来源 key |

## §4 风险与未决项

- 风险 R-1：门禁放宽后在 SPEC 相位放行 coding 型 worker，可能被用来绕过"先写 spec"的纪律。缓解：放行仍需 spec 侧四项齐备（AC-005 保证缺 spec 就拒绝），且 design 层缺项在 DESIGN 相位仍硬拦（AC-002/003）。
- 风险 R-2（残留，需另案）：`update_index.py claim` 的 stub 缺 `- Updated:`/`- Next Action:`，首次 advance 会撞 template drift 后才升级模板；本 key 不改框架仓库。
- 风险 R-3（残留，需另案）：新 key 的索引行 Phase 列写 `—` 而 pm-state 写 `init`，两个占位符不同（本 key 通过 AC-004 让门禁对两者等价处理，但不消除分叉）。
- 未决 Q-1：monitor 的跨 key risk 升级投递是否跨 key 化（本 key 只在面板提供 risk 标记）。默认不做，待用户决定。
- 未决 Q-2：`- Claim-Id:` 是否应在 pm-state 模板中彻底移除（单一事实源最彻底做法）。本 key 取"双写 + 同值 + 索引权威"的保守路径（用户决定 D-c）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- `shared/phase-docs.ts`：`readPhaseDocs()` / `phaseDocGaps()` / `MIN_PHASE_DOC_BYTES=500` / `DOC_GATE_HINT` / `formatDocsBadge()` —— 门禁分层的唯一扩展点，无需新建文档判定逻辑。
- `pm/state-manager.ts`：`StateManager.read()`（相位唯一读取口，已用于 `dispatchPhase()`）。
- `pm/ui-bridge.ts`：`ownedByThisWindow()`（`mw-task-scope-isolation` 新引入的"本窗口所有权"谓词，B2 的聚合行复用它的语义）、`renderWatchLines()`、`WATCH_LINE_MAX`、`readTaskProgress()`（检查点读取，AC-009 复用）、`watch.dispatchedTaskKeys`（派发登记点）。
- `shared/index-store.ts`：`IndexStore.claim()`（TS 侧 claim 唯一写点，D-c 的同步挂点）。
- 测试资产：`test/extensions/agent-team-loop.test.ts`（StateManager/面板既有断言）、`test/extensions/agent-team-loop-worker-*.test.ts`（本轮新测试的邻近范式）、`packages/multi-workers/test_mwpp_collection_parity.py`（跨语言 parity 快照的写法，可借用于"索引行 ↔ pm-state 同值"的 shell 侧验证）。

### 需规避坑点

- P-005（"只有读者没有写者"的跨语言契约）：本 key 的 D-c 正是同类 —— `- Claim-Id:` 有写者（两个）但读者缺位，导致分叉无人发现。规避：AC-010/AC-011 用真实 takeover 路径断言同值，而不是只断言 helper 被调用。
- P-006（绿灯用例的日志通道可能是关闭的）：AC-001~AC-009 的验证必须在**原始输出**里 grep 到关键行（缺项列表文本 / 面板行文本），不接受"返回 ok" 这种转述式证据。
- P-007（review 无落盘通道 → 结论丢失）：本 key 派发的 worker 一律 `type: coding`（有落盘通道），并在任务书里要求把证据行写进 `output.md` + `[VERIFY]` 行。
- P-010（Python 文本模式改源码会翻转换行）：本 key 不改 Python 源码；`_pitfalls.md` 追加与 pm-state 单行同步必须保留主导换行（CRLF/LF 按读取时探测）。
- P-003（`open(p,"w")` 先截断后求值）：claim 同步与面板聚合测试都禁止用截断式写入改 pm-state。
