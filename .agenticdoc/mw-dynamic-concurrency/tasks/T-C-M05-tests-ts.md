type: coding
key: mw-dynamic-concurrency
batch: B3
card: T-C-M05-tests-ts
phase: execute
goal: .agenticdoc/goal.md

# T-C-M05 · MDC 测试（TS 半边：VC-107 面板口径 + VC-108 两侧 parity）

## 上下文

- 目标（本 key）：autopilot 并发改为**依赖前沿驱动、按前沿动态最大化**；配置降级为"上界"，面板必须能一眼看出**上界 / 本 tick 有效并发 / 前沿大小**三个量（AC-005），且**在飞口径与 conductor 单源**（AC-012）。
- 本卡是 MDC 的 **B3（TS 半边）**：只加**测试**，不改任何生产代码。Python 半边（VC-101/102/103/104）由并行卡片 `T-C-M05-tests-python.md` 负责，两边文件集互不相交。
- 已落地的生产行为（**你只做验证**）：
  - 面板：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:968` `slotsCap = config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys`；`:991` `slotsUsed: busyKeys.size`（**key 数**）；`:994` `slotsEffective: Math.min(slotsCap, frontierSize)`；`:995` `frontierSize`；渲染 `:1289-1292` `autopilot: cap <cap> | eff <eff> (frontier <n>)`。
  - 在飞口径（M-03/D-106）：`monitor.ts:518-528` 用 `!TERMINAL_WORKER_STATUSES.has(status) ∧ workerBelongsToKey(entry, owner)` 建 `conductorInflightKeys`；`shared/worker-store.ts:65-70` 的 `workerBelongsToKey` 本身是 `workerOrigin === "conductor" && workerOwnerKey === key`（D-019）⇒ `pending` **计入**、`manual` **不占槽**；Python 侧同形（`mw_common.row_belongs_to` = `worker_is_conductor ∧ worker_owner_key == key`）。
  - 配置默认值/范围：`autopilot/status-model.ts:141-142`（`max_parallel_keys: 8`、`max_workers_per_key: 4`）与 `:202-203`（两者 `[1, null]`）；Python 对应 `packages/multi-workers/autopilot/config.py:91-92` / `:127-128`；冻结语料 `packages/multi-workers/test/fixtures/autopilot-config-corpus.json`（77 例）。
  - `frontierSize` 是 conductor 真实 `|F|` 的**上界**（TS 不读 claim），已在 `monitor.ts:951-953` 注释声明；断言时按各自 `|F|` 口径比，不要假定两者恒等。

## 要求

新增**一个** TS 测试文件，把下列两条 VC 各写成**具名测试**：

1. **VC-107 面板三量同快照复算（AC-005/AC-012）**：
   - 由同一份输入快照（同一 `WorkerStore` 行集 + 同一 config + 同一 roadmap）复算：`slotsCap` = 配置上界；`frontierSize` = 该快照的前沿大小；`slotsEffective === Math.min(slotsCap, frontierSize)`；`slotsUsed` = 有在飞行的 **key 数**（不是行数）；
   - 覆盖口径边界的**可判别正反例**：① `pending` 行 ⇒ 该 key 计入 `slotsUsed`；② `origin=manual` 行 ⇒ **不计入**；③ 终态行（`done`/`failed`）⇒ 不计入；④ `manual` + conductor 行混在同一 key ⇒ 该 key 只算一次；
   - 渲染行必须能读到三量（`cap … | eff … (frontier …)`）。
2. **VC-108 两侧 parity 逐字段（P-021）**：
   - 断言 TS 侧 `DEFAULT_CONFIG` 与范围表**逐字段**等于 Python 侧冻结值（`max_parallel_keys` 默认 8 / `[1, null]`；`max_workers_per_key` 默认 4 / `[1, null]`）；
   - 用**冻结语料**（只读）断言关键行的判决：`range-max-parallel-low`（`max_parallel_keys: 1` 现在**必须被接受**）、`range-max-parallel-min`、以及新的 `partial-key-max_workers_per_key` 行；**不要**断言语料文件整体 sha（会随重冻而脆），改为断言"这些具名 case 存在且判决符合预期"；
   - 证据里给出一张**冻结值清单表**（字段 / TS 值 / Python 值 / 语料 case）。

约束：`vitest` 必须带**显式文件参数**（P-032）；不得 `.skip`/`.only`/`.todo`；不得放宽既有断言；不得改任何生产文件。

## 交付格式

- 新测试文件 `packages/coding-agent/test/suite/autopilot-concurrency-panel.test.ts`（唯一代码写面）。
- 唯一证据文件 `.agenticdoc/mw-dynamic-concurrency/evidence/M-05-tests-ts.md`，含：
  1. 原始 vitest 输出（tail + 通过数）与你运行时的**显式文件参数**；
  2. 四个口径边界正反例的实测值（`slotsUsed` 在 `pending` / `manual` / 终态 / 混合四种输入下的数值）；
  3. VC-108 的冻结值清单表；
  4. 与 M-02/M-03 已吸收结论的一致性说明（口径来源指向 `worker-store.ts:65-70` 与 `mw_common.row_belongs_to`）。
- `output.md` 按五段契约（含 `[VERIFY]` 行）。

## 写入允许面

- `packages/coding-agent/test/suite/autopilot-concurrency-panel.test.ts`（新建）
- `.agenticdoc/mw-dynamic-concurrency/evidence/M-05-tests-ts.md`（唯一证据文件）

## 写入禁止面

- **任何生产代码**：`packages/coding-agent/src/**`（含 `monitor.ts`、`status-model.ts`、`console.ts`、`worker-store.ts`）、所有 Python
- **任何既有测试文件**（要加断言就加到你的新文件里）
- `packages/multi-workers/test/fixtures/*.json`（冻结语料，**只读**）
- `dist/**`、`npm run check`（P-017）、无文件参数 vitest（P-032）、任何 git 写操作
- 不得删除/跳过/放宽既有断言

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-concurrency-panel.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-concurrency-panel.test.ts test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts test/suite/autopilot-monitor.test.ts
npx tsgo --noEmit
```

## 改动历史

- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:968` `slotsCap`——VC-107
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:991` `slotsUsed: busyKeys.size`——VC-107（key 数口径）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:994-995` `slotsEffective` / `frontierSize`——VC-107
- `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts:65-70` `workerBelongsToKey`（D-019：origin 过滤在谓词内部）——VC-107 的正反例依据
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:141-142` / `:202-203` 默认值与范围——VC-108
- `packages/multi-workers/test/fixtures/autopilot-config-corpus.json`（只读语料，`range-max-parallel-low` 等具名 case）——VC-108
