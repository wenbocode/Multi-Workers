# FIX-D：dp1 采纳判定的分歧闸 + dp3 超限拒发用 `input-oversize`（QG MINOR-1 + MINOR-5）

- type: coding
- owner key: mw-decision-substitution
- 来源：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md` §B minor 第 1、5 条

## 上下文

QG 复审 4 条 major 已由 FIX-A/FIX-B/FIX-C 修完，剩两条**不影响 fail-safe 但污染度量/措辞**的小口子，收尾前一并收掉。

**MINOR-1（影响一致率分子，度量会虚高）**
`dispatchDecisionOf`（`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:264`）只要 `available && mode === "auto" && triage_type && decision_id` 就标 `acted:true` 并写 `decision:` 头行。但 dp1 的派发**从不按建议改 type**（AC-014：建议不改派发），所以 `triage_type ≠ 实派 type` 的**分歧样本也会被标成"已采纳"**，以 `outcome=ok` 进入一致率分子 → 报告的一rate 虚高。
T-04c 定的语义是「派发方**采纳了该类型**」，所以分歧（disagreement）不该算采纳。

现有测试 `test/suite/decision-association.test.ts:667-720` 只覆盖 agree / suggest / unavailable，**缺 disagree + auto 用例**，所以这个分支从来没被钉过。

**MINOR-5（措辞与契约不符）**
`compileDp3` 的 3a 分支（`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4847` 附近）在 canonical state > 2000B 时 `escalate("input-incomplete", "3a", …)`，而 D-028 规定超限用 `input-oversize`；`Dp3EscalatedReason` 类型（`:4427` 附近）里压根没有该成员。只影响 trace 措辞（请求没发出、无档案行），不改行为。

## 要求

1. **MINOR-1**：`dispatchDecisionOf` 增加分歧闸——`mode === "auto"` 且 `triage_type` 与实派 type **不一致**时**不采纳**：`acted=false`、**不写** `decision:` 头行（与 suggest 同型：答案与 decision_id 仍留 trace）。实派 type 的可得性是前提，若该函数在写入头行的时刻拿不到实派 type，就把判定挪到能拿到的落点（例如 `mergeDecisionHeader` 调用处，`ui-bridge.ts:1885` 区域），但**不得**用「未知即已采纳」兜底。
2. 采纳判定的三态要写清并测：`agree + auto` → acted=true 且写头行；`disagree + auto` → acted=false 且**无**头行；`mode=suggest`（任意 type）→ acted=false 且无头行。
3. **MINOR-5**：`Dp3EscalatedReason` 加 `input-oversize`，3a 超限分支改用它；确认 `escalated_reason` 的 7 值词表在**档案/CLI**侧不因此变宽（`input-oversize` 是 worker 侧本地拒发原因，不是 Python `ESCALATED_REASONS` 成员——若两者共用一个 TS 类型，则拆开而不是原地加宽；这点必须显式回答）。
4. 测试：
   - `decision-association.test.ts` 加 `disagree + auto`（断言 `acted=false`、无 `decision:` 头行、trace 仍带 `decision_id`）与既有 agree/suggest 三态并列。
   - `dp3-answer.test.ts` 加超限用例（state > 2000B → trace 出现 `input-oversize`、零 spawn），既有 19 例保持绿。
5. 不得引入 `any`；只准用可擦除 TS 语法；不得改动 FIX-A/FIX-B/FIX-C 已收敛的契约（`decision-tool.ts`、`pm-orchestrator.ts` 的 dp2 段、`xkey-gate-guard.ts` 不在写面内）。

## 交付格式

- 三态映射表：`(mode, triage_type vs dispatched) → acted / 头行`，每条给 `path:line`。
- MINOR-5 的词表问题显式回答：`input-oversize` 加在哪个类型上、是否影响 Python 侧词表。
- 测试计数行（两个套件）+ `npx tsgo --noEmit` rc。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 待修：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:264`（`dispatchDecisionOf`）、`:1885`（`mergeDecisionHeader`，如需换落点）
- 待修：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4847`（3a 超限分支）、`:4427`（`Dp3EscalatedReason`）
- 契约：`.agenticdoc/mw-decision-substitution/design.md`（D-028 超限拒发、D-041 acted 由消费侧给出）；现有反面覆盖 `packages/coding-agent/test/suite/decision-association.test.ts:667`

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/decision-association.test.ts`
- `packages/coding-agent/test/suite/dp3-answer.test.ts`

## 写入禁止面

- 其它任何 `src/**`、`test/**`（尤其 `pm/decision-tool.ts`、`pm/pm-orchestrator.ts`、`shared/xkey-gate-guard.ts`、`shared/heartbeat.ts`）
- `packages/multi-workers/**`、`.agents/**`、`.claude/**`
- `docs/**`、`CHANGELOG`、`.agenticdoc/**`（除 `workers/fix-qg-minor15/**` 自身运行目录）
- 禁止 `git` 任何写操作；禁止 `npm run check` / `biome --write`（会改写其它会话在途文件）

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-association.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/dp3-answer.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
npx tsgo --noEmit
npx biome check src/extensions/agent-team-loop/pm/ui-bridge.ts src/extensions/agent-team-loop/worker/worker-mode.ts test/suite/decision-association.test.ts test/suite/dp3-answer.test.ts
```

全绿且 `tsgo` rc=0 才算完成；红就停下报告，不要放宽断言。

## 改动历史

- 2026-10-20 建卡：来源 QG MINOR-1（`ui-bridge.ts:264` 分歧样本被计为采纳）+ MINOR-5（3a 超限用 `input-incomplete`，D-028 要求 `input-oversize`）。
