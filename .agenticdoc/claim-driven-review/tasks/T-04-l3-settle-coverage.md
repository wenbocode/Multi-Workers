# T-04: L3 结算层 —— 断言覆盖判据、self-check、`[CLAIMS]` 证据行（coding）

- Key: claim-driven-review
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」；断言裁决必须可回读、可判定）。
- 设计依据：`design.md` §2.2、§3.3、§5（G2）、§7 D-003/D-004/D-008。
- 上游事实（`evidence/research/spec-rq2-seams-20261020.md` §2.1/§2.2，不要重新调研）：
  - `finishSuccess()` 的判定顺序与行号：`hasDeliverableEvidence`（3831-3833）→ `judgeRecovery`（3846）→ `appendMechanicalContextSources`（3850-3865）→ `readTerminalGaps`（3866-3871）→ `exitCode`（3872）→ `taskDone`（3906）→ `writeOutputGuarded`（3910-3925）→ `recordEnd`（3948）。
  - 判据必须折进 `readTerminalGaps`（`output-writer.ts:357-425`），**不能放在 `taskDone` 之后**（会与已定稿的产物分叉）。
  - self-check 一次性状态是 `selfCheckSent`（`worker-mode.ts:3332` 定义、`3994-3995` 判用）；复用，不新增状态。
  - `[END]` 行有两侧锚定正则（`heartbeat.ts:93`、`mw_common.py:2768`）→ **绝不扩 `[END]`**，新增独立行。
  - `fetches` 口径 = `[FLOW] tool_call` 的读类计数（只含放行），与 `read-scope` 的 `allowedCalls` 不同。
  - task.md 的 caps 解析在 `worker-mode.ts:650-657`，`TaskMeta` 在 `531-534`。
- 契约来源：`evidence/research/spec-rq3-claim-taxonomy-20261020.md` §5（七列 schema、裁决闭集、证据语法、7 词原因闭集、容差）、§4（B-1…B-10 反绕过）、§6（manual 档位）。**以该文件为准逐条实现，不要自创字段名**。
- 依赖：T-01 已导出 `parseClaimsBlock` / `CLAIM_TYPES` / `UNVERIFIED_REASONS`；本卡从 `shared/dispatch-card.ts` import（同包内相对路径），不得复制常量。

## 要求

1. `worker/output-sections.ts`：
   - 新增导出 `parseVerdictTable(text)`（H2 `## 断言裁决`，复用现有 fence/别名判定器 `:128-188`）与 `claimCoverage(claims, table)`。
   - 覆盖判据（缺项文案即有判据）：缺表 `claims:missing-table`；卡内多出 `claim:<id>:missing-row`；表内多出 `claims:extra-row:<id>`；`claim:<id>:verdict`（不在 `closed|partial|unverified`）；`claim:<id>:finding`（不在 `成立|不成立|无法判定`）；`claim:<id>:evidence`（closed/partial 缺证据）；`claim:<id>:reason`（unverified 原因不在 7 词闭集）；`claim:<id>:struct-held`（struct 行计入 closed 分子）；`claim:<id>:self-evidence`（唯一证据落在自证集合）。
2. `worker/output-writer.ts`：
   - `TerminalGaps`（`:49-110`）加 `claimGaps: string[]`（可选，默认 `[]`）；`ok` 在 `:423` 追加 `&& claimGaps.length === 0`。
   - `## Questions` 首行（`:448`）在有 claimGaps 时追加 `未裁决断言：<前 3 条 id>…`。
   - 不改变无 claims 时的任何既有输出字节。
3. `worker/worker-mode.ts`：
   - `TaskMeta` 加可选 `claims`；`parseTaskMd` 读到 claims 块时填充（放在 `:650-657` 的 caps 解析旁）。
   - `finishSuccess` 里把 claims 块传给 `readTerminalGaps`（第 6 步），`exitCode`（3872）沿用既有折叠，不加新判定点。
   - `settleOrSelfCheck`（3962-4008）：把 `currentClaimGaps` 与既有 `currentRecoveryMissing` 分开渲染、共用触发条件与 `selfCheckSent`。
   - 新 trace 行（`recordEnd` 之前写一次）：`[CLAIMS] <iso> claims=<n> closed=<n> partial=<n> unverified=<n> fetches=<n>`；`fetches` 用 `[FLOW] tool_call` 的读类计数。无 claims 块时**不写该行**。
   - AC-008 六条：自证集合排除、`unverified > 40%` 时不得判 PASS（review 角色阈值 60%）、`Σ取数 ≤ min(Σ预算, fileCap)` 且 ≤ trace 读类计数、struct 行不计 closed 分子、`[ENVELOPE_FALLBACK]` 的 extras 视为缺失（本卡只需在 claims 相关路径上判前四条；extras 那条由 T-02 负责）、复用裁决须 `carried-from:`。
4. 测试：
   - 新增 `test/suite/claim-coverage.test.ts`：缺表/缺行/多行/坏裁决/坏判定/缺证据/坏原因/struct 吞并/自证证据各一例；self-check 只触发一次（第二次直接 `exit 2`）；`exitCode=2` 且 `## Questions` 首行点名。
   - 新增 `test/suite/claim-bypass.test.ts`：AC-008 六条各一负例（构造合规但空跑的产出，断言被拦）。
   - 既有 `dispatch-recovery-terminal.test.ts`、`mwoc-*` 用例不得改断言。
5. 若 `TerminalGaps` 被其他测试手工构造，全部改为可选字段（默认 `[]`），不得要求调用方补参。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/claim-coverage.test.ts`
- `packages/coding-agent/test/suite/claim-bypass.test.ts`

## 写入禁止面

- `shared/**`、`pm/**`、`autopilot/**`、`packages/multi-workers/**`、`dist/**`

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-coverage.test.ts test/suite/claim-bypass.test.ts test/suite/dispatch-recovery-terminal.test.ts
cd ../..
npm run check
```

三条文件 0 fail；`npm run check` 全量输出 0 诊断。

## 改动历史

- 2026-10-21 创建（无既有改动）

## 交付格式

`output.md` 四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段给：三文件的改动行号与新增导出、`[CLAIMS]` 行原文样例、两条测试文件的用例计数与输出摘要。残留段写明：`fetches` 与 `allowedCalls` 的口径差异、未覆盖的 merge 单元子行 id 冲突。
