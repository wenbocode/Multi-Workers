# T-W-I09 · 队列文件单写者收敛（D-114）：删掉 `upsert` 的字节镜像，改走 `WorkerStore` 的锁内入口

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 常驻 mw 服务 + 多 worker 并行写同一项目；`.agenticdoc/_workers.parallel` 是两条派发通道（PM / conductor）共用的**同一份队列账本**，它出现两种合法行格式就等于账本有了两个真源（与"同文件多写者对 = 0"同一族风险）。
- **本卡根因**: B1 的 PM 侧卡（W-08）需要在**同一把 `.mw/workers.lock`** 临界区内完成"判定 + 写队列行"（AC-008 / AC-014），但它的写入面不含 `shared/worker-store.ts`，于是它在 `pm/task-dispatcher.ts:521` **复制**了一份 `WorkerStore.upsert` 的字节镜像（`upsertQueueRowLocked`：9 列 ` | `、origin 末列、同 taskKey 原地替换、空队列首行 `# mw-queue:v2`、tmp+rename），并用"结构化视图"读 `WorkerStore` 的私有字段 `filePath`/`lockPath` 来对齐路径（`task-dispatcher.ts:335` `storePaths`）。判定与写行同临界区是**对的**；复制写实现**不对**——见裁定 D-114（`design.md`）。
- **裁定**: `design.md` D-114（队列文件单写者：写入必须经由 `WorkerStore` 的同一实现，包括已持锁路径）、D-005（判定与写行同一临界区）；`spec.md` AC-008（在飞集合当场从队列重算，不加列）、AC-014（`task.md` 创建不得在锁外）。
- **定位锚点（改）**: `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts:190`（`upsert`：`const release = await acquireLock(this.lockPath)` 后进入 RMW）、`worker-store.ts:153`（`lockPath = path.join(agenticdocRoot, "..", ".mw", "workers.lock")`）、`worker-store.ts:157` 注释（"Keeping the lines verbatim is what lets `upsert` …"）。
- **定位锚点（删镜像）**: `pm/task-dispatcher.ts:521`（`upsertQueueRowLocked`）、`pm/task-dispatcher.ts:335`（`storePaths` 结构化读私有字段）、`pm/task-dispatcher.ts:291`（`dispatchTask` 取锁 → `writeFaceVerdict` → 写行）。
- **PM 实测的当前形状**: `test/suite/worker-store.test.ts`、`test/suite/write-face-pm-gate.test.ts`（19 passed，其中一条已断言"锁内行写与 `WorkerStore.upsert` 字节同形"）——**本卡把那条测试从"镜像相符"改为"调用同一入口"**。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`
- `packages/coding-agent/test/suite/worker-store.test.ts`
- `packages/coding-agent/test/suite/write-face-pm-gate.test.ts`

## 写入禁止面

其余一切路径。特别地：`pm/pm-orchestrator.ts` 只读（正处另一 key 的读回投递话题范围，本卡不许碰）；`pm/ui-bridge.ts` 只读（W-08 已交付的渲染侧，本卡不动）；`packages/multi-workers/**` 全只读；`shared/write-face.ts` 只读（算子已达标）；其他 test/suite 文件只读。**禁止 `npm run check`**（全仓 `biome --write`，多会话破坏性）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **给 `WorkerStore` 加锁内写入口**：新增一个"调用方已持有 `.mw/workers.lock`"时使用的写入口（如 `upsertWithinLock(entry)`），语义/行格式/替换规则**与 `upsert` 逐字节一致**；`upsert` 自身改为"取锁 + 调用该入口"（或抽公共私有方法两处共用），**行格式只能有一处实现**。锁语义不变：`upsert` 仍取锁，新入口**不取锁**（并在 docstring 里写明"调用方必须已持锁"）。
2. **删掉镜像**：`pm/task-dispatcher.ts` 删除 `upsertQueueRowLocked`，改为调用新入口；同时删除 `storePaths` 里"结构化读 `WorkerStore` 私有字段"的做法，改用**正式入口/公开只读访问器**（若需要锁路径用于自查，就由 `WorkerStore` 提供正式访问器；不要再读私有字段）。
3. **不得削弱既有行为**：`dispatchTask` 仍在同一临界区内完成 判定 → profile 注入 → 写行；拒绝路径仍**零副作用**（不写行、不建 taskDir）；`test/suite/write-face-pm-gate.test.ts` 的 19 条（含目录/队列快照 diff、D-003 serial-only、字段逐字对照）必须仍全绿——只有那条"字节同形"断言按第 4 条改写。
4. **测试**：
   - `test/suite/write-face-pm-gate.test.ts`：把"锁内行写是 `WorkerStore.upsert` 的字节镜像"那条改成断言**同一实现**（例如：持锁下用新入口写一行，与 `upsert` 在一份新库上写的同一行逐字节相同；并断言 `task-dispatcher.ts` 不再存在第二份行拼接实现——用导入面/源码扫描二者之一，取你实测可行的那个）。
   - `test/suite/worker-store.test.ts`：新增至少两条——(a) 新入口在**已持锁**时写入成功且行格式与 `upsert` 一致（含同行替换、origin 末列、空队列首行 `# mw-queue:v2`）；(b) `upsert` 的取锁语义未被破坏（例如新入口**不**取锁：持锁下调用不得死锁/不得自行 release）。
   - 至少一条**真实端到端**：一次 `dispatchTask` 成功派发后，队列行与 `WorkerStore.upsert` 直接写入的同一行逐字节相同。
5. 完成后 `git diff --stat` 只应含上述允许面文件（工作区里其它 session 的改动不算本卡）。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑的原始命令与原始输出**：新入口与 `upsert` 的双路径字节对照（原文）、删镜像前后的代码锚点（`file:line`）、`write-face-pm-gate` 与 `worker-store` 两个套件的条数、以及端到端那条的队列行原文。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，说明它来自 `worker/output-writer.ts` 的形态检查，**不影响判定**。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts test/suite/write-face-pm-gate.test.ts
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test/suite
```

## 改动历史

- 2026-10-14 W-08（`pm/ui-bridge.ts` + `pm/task-dispatcher.ts`）交付 PM 侧派发闸；因写入面不含 `shared/worker-store.ts`，其 §残留 3 自报"同一临界区实现方式偏离 D-005 字面"，并在 `task-dispatcher.ts:521` 留下 `upsertQueueRowLocked` 字节镜像。
- 2026-10-14 PM 裁定 D-114（队列文件单写者）并要求跟进；本卡即该跟进。
- 本卡不碰 `pm-orchestrator.ts`（`DispatchOutcome` 计数偏乐观一事由后续卡处理，见 `plan.md` §7.3）。

## 硬约束

- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）。
- 行格式只能有一处实现；不得为"跳过取锁"而复制拼接逻辑。
- 发现别处也要改，写进 `残留与未验证` 回报，不要越面修改。
