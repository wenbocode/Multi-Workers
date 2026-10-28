# T-04b: L3 结算层（worker 接线）—— task.md claims 解析、self-check、`[CLAIMS]` 证据行（coding）

- Key: claim-driven-review
- type: coding

> 拆分说明：原 T-04 拆成 T-04a（只读面，已完成）/ T-04b（本卡）。**本卡只能在 `ds-w8-decision-type`（另一窗口，改写 `worker/worker-mode.ts`）结束之后派发**，否则会互相覆盖。

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」）。
- 设计依据：`design.md` §3.3（后半）、§5（G2）、D-003/D-004/D-008。
- 上游事实（`evidence/research/spec-rq2-seams-20261020.md` §2.1/§3.1/§5.4）：
  - `finishSuccess()` 顺序：`hasDeliverableEvidence`（3831-3833）→ `judgeRecovery`（3846）→ `appendMechanicalContextSources`（3850-3865）→ `readTerminalGaps`（3866-3871）→ `exitCode`（3872）→ `taskDone`（3906）→ `writeOutputGuarded`（3910-3925）→ `recordEnd`（3948）。**行号可能因另一窗口的合并而漂移，以函数名为锚点重新定位**。
  - `selfCheckSent`（3332 定义、3994-3995 判用）是一次性状态，复用不新增。
  - `[END]` 两侧锚定正则：`shared/heartbeat.ts:93`、`packages/multi-workers/mw_common.py:2768` → 新增独立行，**不得扩 `[END]`**。
  - task.md 的 caps 解析在 `650-657`，`TaskMeta` 在 `531-534`。
  - `fetches` 口径 = `[FLOW] tool_call` 读类计数（只含放行），不是 `read-scope` 的 `allowedCalls`。
- 依赖：T-04a 已实现 `parseVerdictTable` / `claimCoverage` / `TerminalGaps.claimGaps`；T-01 的 `parseClaimsBlock` 从 `shared/dispatch-card.ts` import。

## 要求

1. `TaskMeta` 加可选 `claims?: Claim[]`；`parseTaskMd` 解析 task.md 里的 `<!-- mw-claims: v1 -->` 块（复用 T-01 的 `parseClaimsBlock`），块缺失时字段不设。
2. `finishSuccess()`：把 `meta.claims` 传给 `readTerminalGaps`；`exitCode` 沿用既有折叠（`delivered && gaps.ok`），**不新增判定点、不改判定顺序**。
3. `settleOrSelfCheck`（3962-4008 附近）：把 claim 相关缺项与既有 `currentRecoveryMissing` **分开渲染、共用触发条件与 `selfCheckSent`**；文案必须点名首个缺失 claim id。
4. 新 trace 行（在 `recordEnd` 之前写一次）：`[CLAIMS] <iso> claims=<n> closed=<n> partial=<n> unverified=<n> fetches=<n>`；无 claims 块时**不写该行**。`fetches` 用 `[FLOW] tool_call` 读类计数。
4b. **run.json 的 `claims` 子对象由本卡写入**（实测：run.json 是 worker 侧 `recordEnd` 写的，不是 launcher）：键固定为 `{total, closed, partial, unverified, fetches, tokens}`，`tokens` 不可归因时为 `null`；无 claims 块时**不写该键**（T-05 的 `readRunClaims` 已按“缺键即 null”实现）。
5. AC-008 在结算侧的三条：`unverified` 占比 > 40%（review 角色 ≤ 60%）时不得判 PASS；`Σ取数 ≤ min(Σ预算, fileCap)` 且 ≤ trace 读类计数；同一 claim 的裁决若引用上轮产物，必须有 `carried-from:`。
6. 新增 `test/suite/claim-bypass.test.ts`：AC-008 六条各一负例（构造合规但空跑的产出断言被拦）；`[CLAIMS]` 行格式一正一反；无 claims 卡不写该行。
7. 不改既有测试断言；`finishSuccess` 在无 claims 时的行为逐字节不变。
8. 测试追加：`run.json` 的 `claims` 子对象（有 claims 时五键齐全、不可归因时 `tokens=null`、无 claims 时不写该键）写入与回读各一例。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/claim-bypass.test.ts`

## 写入禁止面

- `worker/output-writer.ts`、`worker/output-sections.ts`（T-04a 已定稿）、`pm/**`、`shared/**`、`autopilot/**`、`packages/multi-workers/**`、`dist/**`

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-bypass.test.ts test/suite/claim-coverage.test.ts test/suite/dispatch-recovery-terminal.test.ts
cd ../..
npm run check
```

## 改动历史

- 2026-10-21 创建（T-04 拆分而来）

## 交付格式

`output.md` 四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段给：`worker-mode.ts` 的改动点（函数名 + 行号）、`[CLAIMS]` 行原文样例、三支测试输出摘要。
