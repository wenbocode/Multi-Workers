# T-03 · 终端回读推送域：`notified` 后移 + C1/C3 拆分 + 未读数（W5）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「文件驱动的去中心化协调」「Worker 之间不直接通信」）——PM 是唯一消费者，终态回读是 PM 侧唯一观测通道；缺失它等于 Worker 结果不可见。
- 现状（**已确证，不要重复发现**）：`pm/pm-orchestrator.ts` 的终态投递门禁里，`notified.add`（`:1512`）**早于** owner key 门禁（`:1517-1520`）⇒ 一条 owner key ≠ 当前 watch key 的终态行被**记账为已推送**但**从未投递**；之后接管该 key 时 `notified.has(...)` 命中，永远不补推。（`spec.md` P6 + `evidence/readback-push-scope-gap-20261014.md`。）
- 现场复现：`evidence/readback-push-scope-repro-20261014.mts`（探针）——`P3`（接管后推送数）实测为 0；探针 `:150` 的断言 `step4 === 1 && had("b2")` 是**探针自身的断言债**（修后 `step3` 也会投递 ⇒ `step4` 变 2）。
- 设计落点（`design.md` §7，逐字照办）：
  ```
  notified.has(...) || !isTerminal(...)                 -> 不变（投递水位）
  if (!watch.key)      { notified.add(k); continue; }    -> C3：静默但继续记账
  if (owner !== watch.key) { continue; }                 -> C1：不记账
  notified.add(k)                                        -> 后移到 owner 门禁之后
  recordWriteScopeResidualRisks(...)                     -> 仍受 notified 每任务一次保护
  ```
- **硬约束（R5）**：`notified` 同时承担 `recordWriteScopeResidualRisks` 每任务只记一次的界（代码注释明写 `notified above bounds it`）⇒ **C3 分支（`!watch.key`）必须继续记账**，禁止把 `notified.add` 朴素后移到整条门禁之后（否则残留风险记录每 tick 重放；既有测试 `agent-team-loop.test.ts:2077` 会红）。
- AC-012 取**方案 B**（`design.md` §7）：不补推开窗即终态的行，机械判据 = widget 尾行 `N unread`（方案 A 被 AC-011(b)「P1/P2/P5/P6 不变」排除）。
- AC-013：无 watch key 时只渲染单行 widget（`N>0` 才有，`N=0` 清空），**不发消息**；既有 `messages === []` 锁不破。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/test/suite/mwoc-t01-readback-delivery.test.ts`（新建）
- `.agenticdoc/mw-worker-output-contract/evidence/readback-push-scope-repro-20261014.mts`（探针断言改写）

## 写入禁止面

其余一切路径。特别地：`pm/ui-bridge.ts`（**本卡只读**：widget 渲染函数 `applyWatchWidget` 归 T-01 的写面，本卡只从 `pm-orchestrator.ts` 传入额外的尾行文本）、`shared/ack-store.ts`、`shared/worker-store.ts`、`worker/**`、`packages/multi-workers/**` 全部只读。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **C1/C3 拆分**：`owner key !== watch.key` ⇒ **不记账、不投递**；`!watch.key` ⇒ 继续记账 + 静默（保持既有 `:2077` 断言通过）。`notified.add` 只允许出现在 owner 门禁通过之后与 C3 分支内。
2. **去重键 = `taskKey`**（与既有 `notified` 语义一致）；新增 `readbackDelivered` **只作未读数依据**，**不参与投递抑制**。
3. **`ackStore` 不参与投递抑制**：`done` 行本不需要 ack；「未 ack 即补推」会无界重投；`ackedAt` 会被 re-ack 重写 ⇒ ack 是「处理水位」，不是「投递账本」。把 `notified` 与 `ackStore` 的语义分工写进**模块级注释**（AC-012 明确要求）。
4. **AC-011(a)**：接管后补推**恰好 1 次**（`P3` 由 0 变 1）。若 `P3` 仍为 0 ⇒ 停手上报，不要用别的手段糊过去（说明 C1 不是主因）。
5. **AC-011(c)**：先把探针 `:150` 的断言改写为 `had("b2")` 或相对式 `step4 === step3 + 1`（断言债，不是行为回归），再跑探针证明 (a)。
6. **AC-011(d)**：既有测试 `packages/coding-agent/test/extensions/agent-team-loop.test.ts` 中「无 watch key 期间终态行不得复活」那条（`:2053-2085`，断言在 `:2077`）保持通过 —— 用**用例名**锚定，不要用行号。
7. **AC-012/AC-013**：无 watch key 且存在「终态 + 未推送 + 未 ack」行时，widget 尾行出现 `N unread`（`N>0` 出现、`N=0` 不出现/清空）；不发消息。把判据写进新测试的断言里。
8. **R5 的 I/O 面**：门禁之前只允许内存/纯计算（`recordWriteScopeResidualRisks`、`readOutputBody`、`readSpawnFailure` 等一律保持在门禁之后）。
9. `git diff --stat` 收尾只应含允许面文件。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令 + 原始输出**：探针改写前后的 `P1..P6` 原始输出（改前值可用 PM 在 `evidence/readback-push-scope-gap-20261014.md` 记录的数字，改后必须是实跑）、新测试条数与结果、既有 `:2077` 用例原始通过输出、`N unread` 的 widget 尾行原始文本。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-t01-readback-delivery.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
```

（`agent-team-loop.test.ts` 在 HEAD 有 **1 条既存红**（`:6381`，他 key 锚点）——列名单报基线，不要修。已知 `agent-team-loop.test.ts:2053-2085` 那条是本卡必须保持通过的锁。）

## 改动历史

- 2026-10-14 spec 阶段 RQ-5：原文确认 `notified.add` 早于 owner 门禁；`recordWriteScopeResidualRisks` 与 `readOutputBody` 全在门禁之后；既有测试 `:2077` 存在。据此修正 AC-011 并加 (c)/(d)。
- design 阶段 DR5：给出 C1/C3 拆分、去重键、`ackStore` 语义边界与 AC-012 方案 B 的取舍。
