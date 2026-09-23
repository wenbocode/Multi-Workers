# Task T-3: 接线（门禁传相位 + 面板聚合行 + claim 同步调用点）

## 元信息
- Stage: 2（波形 2，必须在 T-1 与 T-2 完成并 ack 之后开始）
- 依赖: T-1（`dispatchDocGaps` 第三参数）、T-2（`syncPmStateClaimId`）
- 风险: 中（改两处派发入口 + 面板渲染 + 三处 claim 展示）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012]
- vc_refs: [VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012]
- 文件面（唯一）：`pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、新建 `test/extensions/agent-team-loop-watch-aggregate.test.ts`、新建 `test/extensions/agent-team-loop-pm-state-sync.test.ts`，加上 `test/extensions/agent-team-loop.test.ts` 里**唯一一处** gaps 长度断言（:1516）

## 背景（实测）

- 门禁调用点**三处**：`pm/ui-bridge.ts:1093`（`dispatch_worker` 工具）、`pm/ui-bridge.ts:1498`（另一入口）、`pm/pm-orchestrator.ts:429`（`dispatchNewTasks` 后台扫描）→ 必须同改，否则入口之间行为分叉（design D-110；第三处是 T-1 实测发现）。
- 相位读取口现成：`dispatchPhase(agenticdocRoot, ownerKey)`（`ui-bridge.ts:902`）；两处调用点都已有 `ownerKey`。
- 面板：`renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key)`（`:480`），本键行筛选在 `:495`（`const owned = workerStore.readAll().filter(...)`），行宽上限 `WATCH_LINE_MAX=110`（`:249`），既有尾部约定 `  (no worker tasks)` / `+N more`。调用点：`pm-orchestrator.ts:312`、`:531`、`:645`；测试调用点 12 处（**本任务不改那些测试**）。
- 派发登记：`watch.dispatchedTaskKeys`（`ui-bridge.ts:1153-1154`，`mw-task-scope-isolation` 引入）；工具侧所有权谓词 `ownedByThisWindow`（`:278`）。
- claim 路径：`takeOverKey`（`:231-241`，返回 `TakeoverResult`）被 `/pm-key new`（`:676`）、`/pm-key switch`（`:694`）、`switch_key` 工具（`:1299`）共用；另一条会话恢复 quiet re-claim 在 `pm-orchestrator.ts:298`（`demoteOthers:false, activate:false`）。两处都会把索引行 Claim 列改成 `self`。
- 检查点风险读取口：`readTaskProgress(path.dirname(entry.taskPath))?.checkpoint?.risk`（同文件已用）。

## 交付物

### A. 门禁传相位（三处调用点）
- 三处 `dispatchDocGaps(agenticdocRoot, ownerKey)` 改为传相位：`dispatchDocGaps(agenticdocRoot, ownerKey, dispatchPhase(agenticdocRoot, ownerKey))`（**不要**新增第二次 `StateManager` 读取；若同作用域已有 phase 变量则复用它）。`pm-orchestrator.ts:429` 处的目标 key 是扫描行里的 `entry.key`（不是 watch.key），相位从该 key 的 pm-state 读（`new StateManager(agenticdocRoot, entry.key).read().phase ?? ""`，或复用该作用域已有变量）。

### B. 面板聚合行（`renderWatchLines`）
- 签名加**可选**第六参数：`extraTaskKeys?: ReadonlySet<string>`。
- 复用**同一次** `workerStore.readAll()` 结果：本键行 `owned` 逻辑不变；另取 `elsewhere = all.filter((e) => extraTaskKeys?.has(e.taskKey) === true && ownerKeyOf(e, agenticdocRoot) !== key)`。
- `elsewhere.length === 0` → 输出与改造前**逐行完全相同**（不新增空行）。
- `elsewhere.length > 0` → 在输出**末尾追加恰好 1 行**：
  - 按 owner key 分组，组间按 `(行数 desc, owner 名 asc)` 排序，以 `, ` 连接；
  - 每组格式 `<owner>(<counts>)`，`<counts>` 只列 >0 的状态，顺序固定 `running/pending/done/failed/needs-clarification`，以 `, ` 连接；
  - 若该组内 **running 行中**存在 `readTaskProgress(...)?.checkpoint?.risk === "high"` 的行，追加 `; risk=high:<K>`（K = 组内 risk=high 的 running 行数）；
  - 整行前缀 `  ~ <N> elsewhere: `（N = `elsewhere.length`）；超过 `WATCH_LINE_MAX` 时用既有 `trunc()` 截断。
  - 例：`  ~ 4 elsewhere: _scratch(3 running, 1 failed; risk=high:1)`
- 该行必须走与本键行相同的"不折叠"路径（不进 `WATCH_HISTORY_MAX` 折叠）。

### C. claim 同步调用点（`shared/pm-state-claim.ts` 由 T-2 提供）
- `TakeoverResult` 增加可选字段 `claimSync?: PmStateClaimSyncResult`；`takeOverKey` 在 `outcome.ok` 之后调用 `syncPmStateClaimId(agenticdocRoot, key, self)` 并放进返回值（**失败不改变 `ok`**）。
- 新增导出小helper `claimSyncWarningText(key: string, sync?: PmStateClaimSyncResult): string`（`sync?.ok !== false` 时返回 `""`；否则返回一行：`WARNING: claim succeeded but <key>/pm-state.md was not synced (<reason>). The index row is authoritative.`），并在三处展示：`/pm-key new`（`:679` 附近）、`/pm-key switch`（`:704` 附近）、`switch_key` 工具返回文本（`:1323` 附近的 `text`）。
- `pm-orchestrator.ts:298` 的 quiet re-claim：`outcome.ok` 之后同样调用 `syncPmStateClaimId(...)`，失败时 `ctx.ui.notify(claimSyncWarningText(key, sync), "warning")`。
- `pm-orchestrator.ts` 三处 `renderWatchLines(...)`（`:312`、`:531`、`:645`）加第六参数 `watch.dispatchedTaskKeys`。

### D. 新测试（两个新文件，不碰既有测试文件）
`test/extensions/agent-team-loop-watch-aggregate.test.ts`：
- VC-006：watched key `key-a` 无行 + 另建 `_scratch/workers/<t>/task.md` 的 mock 队列行（`running`），`extraTaskKeys = new Set([taskKey])` → 输出中匹配 `/elsewhere/` 的行数 == 1，且该行含 `_scratch` 与 `running`，`line.length <= 110`。
- VC-007：同一场景不传第六参数 → 输出与"传空集合"两种情形都等于**不传参数时的基线数组**（用同一构造再跑一次比较逐行相等），`elsewhere` 行数 == 0。
- VC-008：跨 key 行含 `failed`（未 ack）→ 聚合行含 `failed` 且计数为实测值。
- VC-009：跨 key `running` 行的 `progress.md` 写一条机器检查点行 `risk=high`（参照 `worker/output-writer.ts` 的 `formatMachineCheckpoint` 格式或直接写等价文本）→ 聚合行同时含 `risk=high` 与 `1`。
- 既有面板语义回归：本键 `done`/终态行渲染不受影响（同一次读盘内两类行共存时，本键行集合与不传参数时逐行相等）。
- 测试构造请复用 `test/extensions/agent-team-loop.test.ts:2145` 附近的既有写法（`new WorkerStore(...)`/`dispatchTask(...)`/`IndexStore`/`AckStore`）。

`test/extensions/agent-team-loop-pm-state-sync.test.ts`：
- VC-010：真实 `takeOverKey(indexStore, "key-sync", false, root)` + 一份 CRLF 7 段 `pm-state.md` → 断言 (a) `result.claimSync?.ok === true`；(b) 文件内 `- Claim-Id:` 值 == 索引行 `findByKey("key-sync").claimId`；(c) `## ` 二级标题数 == 7；(d) `- Updated:` 行数 == 1；(e) `\r\n` 计数不变。
- VC-011：`pm-state.md` 存在但**删掉** `- Claim-Id:` 行 → `takeOverKey` 仍 `ok === true`、`claimSync.ok === false`、`claimSyncWarningText(...)` 输出**恰好 1 行**且含 `not synced`，文件**逐字节未变**。
- VC-012：`dispatch_worker` 工具入口场景：phase=SPEC 的 key（`pm-state.md` 只有 phase 行 + spec 侧四项齐备）以 `type: "coding"` 调用 `dispatch_worker` 的 `execute`（参照 `test/extensions/agent-team-loop.test.ts` 里 `dispatch_worker` 的既有测试写法）→ 返回文本**不含** `missing phase documentation`，且 `<key>/workers/<task>/task.md` 存在。
- 既有测试的**唯一窄改**：`test/extensions/agent-team-loop.test.ts:1516` 的 `expect(gates[0]?.gaps).toHaveLength(5)` → `toHaveLength(3)`，并把同行的注释改成"（goal.md 不存在 → §0 跳过；相位分层后该 key 无 pm-state → spec 层 = spec.md + spec 证据 + AC = 3）"。该用例其余断言（跳过、单次上报、文档齐备后可派发）必须保持不变且全绿；实测当前失败为 `expected ... to have a length of 5 but got 3`（172 passed / 1 failed）。
- VC-007 基线：本任务不得改动 `renderWatchLines` 既有 12 处测试调用及其断言。
- `[VERIFY]` 行用 `process.stdout.write("…\n")`，字段全部取自实测变量。

## 约束

- 只改上述 5 个文件（`pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、两个新测试，加上 `test/extensions/agent-team-loop.test.ts` 中**唯一那一处** gaps 长度断言）；**不改** `shared/phase-docs.ts`、`shared/pm-state-claim.ts`（T-1/T-2 的产物）、不改 `dist/**`、不改 Python。
- 面板既有 12 处测试调用**必须零改动**且全绿（这是 AC-007 的机器保证之一）。
- TS 只用可擦除语法；无 `any`；无 inline `import()`；顶栏 import，不写 inline `await import()`。
- 不 commit；不运行 `mw build`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-watch-aggregate.test.ts test/extensions/agent-team-loop-pm-state-sync.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-phase-docs-gate.test.ts test/extensions/agent-team-loop-pm-state-claim.test.ts
cd H:/git/Multi-Workers && npm run check
git status --short
```

## 报告要求

最终消息给出：改动文件、用例计数、每条 `[VERIFY]` 行原文、聚合行样例（含多 owner 情形）、`claimSyncWarningText` 原文、以及任何偏离 design 的实现细节。
