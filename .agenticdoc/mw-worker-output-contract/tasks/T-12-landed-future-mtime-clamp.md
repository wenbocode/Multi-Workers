# T-12 · `landed` 上界去抖是「跳过」而非「钳制」⇒ 刚落地文件被判未落地（非确定性）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 超时看门狗：activity watchdog + 墙钟兜底 + 30 分钟收敛检查点」）——检查点判据必须**确定可复现**，否则「真挂死 vs 在推进」的判据本身不可信。
- **真实缺陷（PM 复跑实测，非猜测）**：T-04 新套件 `test/suite/mwoc-w4-checkpoint-invariants.test.ts` 在本机重现**非确定性失败**：连续 6 次单文件重跑，第 2 次 `1 failed | 18 passed`，其余 5 次 `19 passed`。失败用例与断言：
  `collectLandingSignals (ledger-sourced) > dedups repeated targets like parseWriteFileEvents and ignores [TOOL] worker_file lines`（`test/suite/mwoc-w4-checkpoint-invariants.test.ts:238`）⇒ `AssertionError: expected undefined to be defined`。
- **根因（读源码定位）**：`worker/worker-mode.ts:402`（`newestEvidenceMtimeMs`）与 `:418 collectLandingSignals` 的目标统计对「未来 mtime」采取**跳过**语义：
  - `worker-mode.ts:402`：`if (stat.size === 0 || stat.mtimeMs < startedAtMs || stat.mtimeMs > nowMs) continue;`
  - `collectLandingSignals` 内：`if (!stat.isFile() || stat.size === 0 || stat.mtimeMs > opts.nowMs) continue;`
  测试在写盘后立刻取 `nowMs: Date.now()`（`test/suite/mwoc-w4-checkpoint-invariants.test.ts:233`）。Windows NTFS 的 mtime 粒度可以落在 `Date.now()` **之后**几毫秒，于是刚写下的文件被 skip ⇒ `newestMtimeMs === undefined` ⇒ `lastLandingAgeMs === undefined` ⇒ 断言失败。
- **为什么算缺陷（而不是测试写法问题）**：未来 mtime 的**唯一**合理解释就是「刚刚落地」（时钟粒度/写入与读取的竞态）。跳过它使信号**更悲观**（丢掉一次真实落盘），与 `land` 字段「抗抖动、反映真实落盘」的意图相反；在重放场景（`nowMs` 固定为历史检查点时刻）会直接产生**不可复现的判据**。正确的处置是**钳制**：`age = max(0, nowMs - mtime)` 已把未来 mtime 归零，上界不应在钳制之前把目标整个丢掉。
- 关联：T-04 交付 `worker-mode.ts` 检查点段 + `shared/heartbeat.ts` + 该测试文件；本卡是 T-04 交付内的**上界语义修正**（其余语义不动）。T-05（settle 段）尚未开工，写面不冲突但同在 `worker-mode.ts`，故本卡先于 T-05 串行执行。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（**仅** `newestEvidenceMtimeMs` 与 `collectLandingSignals` 的未来 mtime 上界处理）
- `packages/coding-agent/test/suite/mwoc-w4-checkpoint-invariants.test.ts`

## 写入禁止面

其余一切路径。特别地：`computeRisk` 的分支与阈值、`writeCheckpoint` 的调用点、`shared/heartbeat.ts`、`shared/change-ledger.ts`（`parseWriteFileEvents` 只读）、抽取器/记账段、settle 段、I3 三段（idle / 墙钟 / deadline steer）、`pm/**`、`packages/multi-workers/**`、其它 test/suite 一律只读。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **上界改钳制**：未来 mtime（`mtimeMs > nowMs`）**不再 `continue`**，而是把该次落盘的时间钳到 `nowMs`（等价 `age = 0`）。`collectLandingSignals` 的目标统计与 `newestEvidenceMtimeMs` 的证据遍历**两处都要改**。
2. **下界保留**：`startedAtMs` 之前 mtime 的文件**仍然**不算本次落地（既有语义不变）；`size === 0` 仍不算（空文件不是产物）。
3. **确定性回归（核心）**：把现有失败用例（`test/suite/mwoc-w4-checkpoint-invariants.test.ts:210` 起）从依赖 `Date.now()` 的写法改为**显式 `nowMs`**（写盘后 `statSync` 取真实 mtime，再以 `mtime + 100` 之类的显式值调用），使其与文件系统时钟粒度**无竞态**；并新增至少 1 例「`nowMs = mtime - 1`（未来 mtime）⇒ `lastLandingAgeMs === 0` 且 `artifactPresent === true`」。
4. **稳定性证据**：同一条命令**连续 10 次**单文件重跑，贴出 10 次汇总结论（必须 10/10 全绿），并说明修复前失败率（PM 实测 1/6）。
5. **不回归**（给原始条数）：本卡测试文件（改后 ≥20 例）全绿；`change-ledger` **12/12**、`agent-team-loop-checkpoint-wiring` **10/10**、`agent-team-loop` **196/197**（1 条 `T-17/B-1 anchor integrity` 为 HEAD 既存红）、`mwds-t03-bash-write-scope` **63/63**、`mwds-t04/mwds-t05/mwds-t06/mwds-t12` **50/50**；`npx tsgo --noEmit` = 0。
6. **`risk` 行为逐条不变**：`writeless low/mid/high` 三档、write 角色 legacy 五例、AC-009 两场景、I3 三例在修复后结论**逐条不变**（本卡只改「未来 mtime 怎么算」，不改任何阈值与分支）。若你发现钳制会改变任一既有结论，停手上报并说明。
7. 开工前 `git status` + mtime 确认无第三方正在编辑 `worker-mode.ts`；若有，停下并在「残留与未验证」报告。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令 + 原始输出**：修复前失败用例的 `AssertionError` 原文（可先用 `nowMs` 显式取未来值复现，不必依赖偶发）、修复后 `nowMs = mtime - 1` 的 age/artifact 实测值、10 次连续重跑的汇总行、五组既有套件条数、`tsgo` 退出码。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w4-checkpoint-invariants.test.ts
# 连续 10 次（贴 10 行汇总）
1..10 | ForEach-Object { node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w4-checkpoint-invariants.test.ts 2>&1 | Select-String "Tests +" }
node ../../node_modules/vitest/dist/cli.js --run test/suite/change-ledger.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-checkpoint-wiring.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t04-deliverable.test.ts test/suite/mwds-t05-output-sections.test.ts test/suite/mwds-t06-output-informativeness.test.ts test/suite/mwds-t12-regression.test.ts
npx tsgo --noEmit
```

## 改动历史

- 2026-10-14 T-04 收口时 PM 复跑发现非确定性失败（6 次重跑 1 次红，`expected undefined to be defined`），定位到 `worker-mode.ts:402` 与 `collectLandingSignals` 的「未来 mtime ⇒ 跳过」上界语义；判定为 T-04 交付内缺陷（判据不可复现 + 丢真实落盘），故新建本卡，先于 T-05 串行执行。
