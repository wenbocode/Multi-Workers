# T-22 ORPHANED 准入证据放宽（index 行 ∨ 该 key 自身 owner 痕迹）+ 未登记 key 的可操作收口

- Key: mw-dispatch-card-gate｜Wave: 14（与 T-20/T-21 并行）｜type: coding

## 上下文（PM 裁定修正，用户质询后成立）
T-19 把 ORPHANED 准入定为"**已登记于 `_index.parallel`**"。这条**会漏掉两类真丢档**，属 PM 裁定缺陷，现修正：

- **(b) 登记行丢失**：index/timeline 轮转、并发整文件重写覆盖 ⇒ 行没了但 key 一直在跑（有 owner 痕迹）；
- **(c) 登记未完成**：`dispatch_worker(key=…)` 先建目录后登记，两步非原子，中间崩溃 ⇒ 目录+工作齐备但无行。

这两类的正当修复需求真实存在；被否决的只是"**扫描自动建档**"这个 actor（`_index.parallel` 的行携带 Phase/ClaimId/Deps 等**跨窗口协调事实**，扫描推不出 ⇒ 猜着写比不写更坏；且无主跨 key 写触 AC-019）。**PM 裁定：准入证据放宽，但不得自动登记。**

T-19 现状（终态，可直接复用）：`index-store.ts::conductorClaimState`（`free|live|dead|stale`）、`pm-orchestrator.ts` 的 `synthesizeEnvelopeFallback`/`repairDispatchOrphanedKey`/`orphaned-keys` notice（均**不写** `_index.parallel`）。

## 要求（逐条可验收）

1. **准入证据放宽**：ORPHANED = 有未派发工作 ∧ 无活 claim ∧ 无活运行 ∧ **有 owner 证据**；其中
   `有 owner 证据 = _index.parallel 有该 key 行 ∨ 该 key 自身存在 owner 痕迹`。
   - owner 痕迹的判据必须**明确、可测**：至少包含 `<key>/pm-state.md` 中的 `- Claim-Id:` 或 `- Phase:` 行，或 `<key>/workers/**/trace.log` 存在；把最终判据写进报告。
   - **只有目录、无任何 owner 痕迹** ⇒ **不是 ORPHANED**（见第 3 条）。
2. **可修复**：满足放宽后准入的 key 走 T-19 既有 **claim-free 修复派发**：**绝不写** `_index.parallel`；修复后该 key 的 conductor **仍 eligible**（沿用 T-19 断言口径）。
3. **无 owner 痕迹但有工作的 key ⇒ 只告警、绝不写**：产生一条**可操作**通知（notice 类文案，不得用"已拒绝"字样），内容包括：key、它在哪个路径有未派发工作、以及**需人工执行的确切动作**（`switch_key <key>` 或 `dispatch_worker(key=<key>)` 建档）；每 session 每 key 一次；该 key 的任何文件**writer=0**。
4. **禁止自动登记**：任何路径都不得因本卡新增对 `_index.parallel` 的写入（要求有测试断言：触发上述场景后 index 行数/内容不变）。
5. **测试**（新建 `packages/coding-agent/test/suite/mwds-t22-orphan-evidence.test.ts`）：
   - ① 有 owner 痕迹（`pm-state.md` Claim-Id）但**无 index 行** ⇒ 判 ORPHANED 且可修复；修复后 **index 未新增行**、claim 未置、conductor eligible=1；
   - ② 无 owner 痕迹、有工作 ⇒ 仅告警一次，writer=0，index 行数不变；
   - ③ 有 index 行且无活 claim（T-19 既有路径）⇒ 行为与 T-19 一致（回归）；
   - ④ 有活 claim ⇒ writer=0（AC-019 不变）；
   - ⑤ 告警限频（同 key 多次 tick 只一次）。
6. **回归**：`test/suite/mwds-t19-orphan-ownership.test.ts`（13 用例）、`worker-crosskey-readonly.test.ts`、`worker-store.test.ts`、`run-store.test.ts` 全绿（不得弱化既有断言；若 T-19 的 13 用例中有与本卡准入条件冲突者，**先报告再改**，不得直接放宽）。

## 交付格式
- 写入允许面：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`、`shared/index-store.ts`、新建 `packages/coding-agent/test/suite/mwds-t22-orphan-evidence.test.ts`。
- 写入禁止面：`pm/ui-bridge.ts`（T-21 在写）、`shared/change-ledger.ts`（T-21）、`worker/output-writer.ts`（T-21）、`packages/multi-workers/**`、`test/extensions/**`、`.agenticdoc/**`（除本 worker 目录 taskDir）。
- 验收命令（在 `packages/coding-agent` 下）：
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t22-orphan-evidence.test.ts` 全绿；
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t19-orphan-ownership.test.ts test/suite/worker-crosskey-readonly.test.ts test/suite/worker-store.test.ts test/suite/run-store.test.ts` 全绿；
  - `npm run check` 退出码 0；若 biome 会改写你写面之外的文件，**先停下在报告中说明**。
- 报告须含：结论、证据（原始命令与输出；owner 痕迹判据原文；①~⑤ 场景输出；index 未变的断言）、改动清单、残留与未验证、上下文来源清单。
- 不做 cutover；不改 task 卡；不得弱化或删除既有断言；如认为卡有误，在报告中提出供 PM 裁定。
