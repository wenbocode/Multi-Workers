# PM State: mw-task-scope-isolation

## 1. Snapshot
- Key: mw-task-scope-isolation
- Phase: DONE
- Next Action: 收尾（achieved.md + quality-gate 报告 → done）
- Started: 2026-09-23 17:11
- Updated: 2026-09-23 17:14
- Completed: 2026-09-23 17:14

## 2. Task Status
- T-01 归属模型 + `list_tasks` scope: done（`ownedByThisWindow` + 三档 scope + owner 前缀 + 空结果指引 + 派发记账）
- T-02 ack 收窄: done（`ackTasks` 第 4 参 scope，`ack_worker_result` 与 `/mw ack` 同谓词）
- T-03 回归/变更记录/验证: done（既有用例适配 4 处 + 新用例 3 个 + CHANGELOG）

## 3. Evidence Ledger
- 2026-09-23 17:12 **PASS** 目标用例：`agent-team-loop.test.ts -t "task scope isolation"` → 3 passed（AC-001..004 一例、AC-005/006 一例、AC-007 一例）。
- 2026-09-23 17:13 **PASS** 全文件回归：173 passed / 0 failed（基线 170 + 新增 3；含被有意适配的 VC-004/VC-005/VC-011）。
- 2026-09-23 17:14 **PASS** `npm run check` exit 0：biome 1087 files no fixes、pinned-deps、ts-imports、shrinkwrap / install-lock up to date、tsgo --noEmit 无输出、browser-smoke 通过。
- 2026-09-23 17:18 **PASS** `mw build --install` exit 0（bundle 910,510 B；repo dist 同步重建）；grep 确认 `ownedByThisWindow`/`dispatchedTaskKeys` 同时进入全局 bundle（:19243/:19822）与 repo dist（:188/:926）。
- 2026-09-23 17:19 **PASS** 实机 L2（默认 scope 隔离）：新 `pi -p` 进程调 `list_tasks`（无参）→ `No tasks found for this window (watched key: (none))` + `switch_key` / `scope: "all"` 指引，未泄露本项目任何其它 key 的任务。
- 2026-09-23 17:20 **PASS** 实机 L2（全项目视野）：同方式调 `list_tasks(scope:"all")` → `mw-dispatch-reliability :: mw-dr-glm53 | done | pi | acked`，owner 前缀与 acked 徽标在线。
- 2026-09-23 17:11 **PASS** key 建立与声明：写 spec 前已核完全部代码事实（F-1..F-11 见 evidence/research/spec-task-scope-isolation-2026-09-23.md），实施严格晚于 key 建立。
- 2026-09-23 17:12 **PASS** 修复记录：首轮 check 被 biome `noAssignInExpressions` 拦住（`(watch.dispatchedTaskKeys ??= new Set()).add(...)`）→ 改为显式 if 赋值；次轮 tsgo 报 `reply()` 返回类型被放宽为 `type: string` → 补显式返回类型注解。两次均为机械修复，语义未变。
- 2026-09-23 17:36 **欠债** 多窗口并发未实测（非阻塞）。
- 2026-09-23 17:18 旧欠债（bundle 未重建 + 实机未目视）已闭环：重建 + 两次真实进程验证。

## 4. Hypothesis Queue
- H-1（已证）：归属判定不需要新数据——`ownerKeyOf(taskPath)` 足以得到 owner key，与 widget 同口径（AC-001/AC-002 双口径用例通过）。
- H-2（已证）：单靠 `watch.key` 不足以覆盖"自己派发的"——显式跨 key 派发默认落到别的 owner key（F-11）；进程内记账后在 `mine` 中可见（AC-007 通过）。
- H-3（已证）：ack 侧车是项目级文件，但收窄**写入路径**即可阻断跨窗口清理，无需拆文件（AC-005 证明另一 key 的未 ack 行不被清）。
- H-4（未证，非阻塞）：多窗口真实并发下的效果（两窗口同时 ack）未做并发实测；写入仍持 `.mw/workers.lock`（沿用既有协议），仅覆盖范围变窄。

## 5. Decisions
- 2026-09-23 选"owner key + 进程内派发记账"而非给 `_workers.parallel` 加 dispatcher 列：后者要同步 Python 侧解析与并发重写协议，收益不抵成本（design D-1）。
- 2026-09-23 `ackTasks` 用 `scope?: { watch, agenticdocRoot }` 而不是纯谓词：拒绝文案需要 owner key 与本地 key，谓词无法提供；不传 scope 则保持旧行为，既有单测零改动（design D-4）。
- 2026-09-23 `dispatchedTaskKeys` 设为**可选**字段：测试与其它调用点以字面量构造 `PmWatchState`（≥6 处），必填会扩散改动面（design-evidence 表）。
- 2026-09-23 默认值取 `mine`（用户确认），`scope:"all"` 作为逃逸口保留全局视野；未知 scope 报错而不静默降级为 all（fail-closed）。
- 2026-09-23 `/mw ack` 也一并收窄（用户确认"配套"）：新增 `watch`/`agenticdocRoot` 两个必填参数，3 个调用点同步更新。

## 6. Turn End Records
| # | 问题 | 回答 |
|---|------|------|
| 1 | 顶层目标 | 多窗口并行时，任务清单与 ack 通道按窗口隔离 |
| 2 | 新增证据 | 3 新用例 + 173 回归 + `npm run check` exit 0 |
| 3 | 假设变化 | H-1/H-2/H-3 证实；H-4 标注未证非阻塞 |
| 4 | 需重开的 done 任务 | 无 |
| 5 | 阻塞点 | 无；实机目视需 bundle 重建（非阻塞） |
| 6 | 需新增/拆分 Task | 无 |
| 7 | 下一动作 | achieved.md + quality-gate 报告 → advance done |
| 8 | 是否已写入 pm-state.md | 是 |
| 9 | 可提炼 pattern | "共享文件 + 每窗口语义"→ 收窄写入路径而非拆存储 |

## 7. Process Log
- 2026-09-23 17:11 建 key（spec.md 写入触发自动接管）→ design + 设计证据 → tasks T-01..T-03 → `advance_phase execute` → 实现（ui-bridge + pm-orchestrator）→ 补测试 → check 修两处机械问题 → 全绿 → 收尾。
- 2026-09-23 17:19/17:20 L2 实机验证两条路径（默认 scope 隔离 + all 的 owner/acked 渲染），bundle 已在 17:18 重建并生效。
- 2026-09-23 17:13 实施晚于 key 建立（spec/design/tasks 先于首行代码），符合实施准入门禁。
