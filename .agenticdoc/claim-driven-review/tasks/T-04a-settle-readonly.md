# T-04a: L3 结算层（只读面）—— 裁决表解析、TerminalGaps.claimGaps、Questions 行（coding）

- Key: claim-driven-review
- type: coding

> 拆分说明：原 T-04 拆成 T-04a / T-04b。原因：`worker/worker-mode.ts` 正被另一窗口的 `ds-w8-decision-type` 实时改写（mtime 17:19），本卡只碰两个未被动过的文件，避免互相覆盖。

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」；断言裁决必须可回读）。
- 设计依据：`design.md` §2.2、§3.3（前半）、§5（G2）、D-003。
- 上游事实（`evidence/research/spec-rq2-seams-20261020.md` §2.1/§2.2）：
  - `TerminalGaps` 定义在 `worker/output-writer.ts:49-110`；`ok` 折叠在 `:423`；`## Questions` 首行由 `gapNote` 生成（`:448`）。
  - `readTerminalGaps`（`:357-425`）是唯一判定点，内部调用 `checkRecovery`（`:388`）与 `diffLedger`（`:393`）。
  - `worker-mode.ts` 的 `exitCode` 折叠在 `:3872`（**本卡不改**，T-04b 负责）。
  - 机械回填 `appendMechanicalContextSources` 在 `readTerminalGaps` 之前（`:3850-3865`），本卡不要动顺序。
- 契约来源：`evidence/research/spec-rq3-claim-taxonomy-20261020.md` §5（七列、裁决闭集、证据语法、7 词原因、容差）、§4（B-1/B-4 自证集合、B-10 struct 吞并）。
- 依赖：T-01 已在 `shared/dispatch-card.ts` 导出 `parseClaimsBlock` / `CLAIM_TYPES` / `UNVERIFIED_REASONS`（`:525-600`、`:714`）。**从 `shared/dispatch-card.ts` import，不要复制常量**；`worker/` 依赖 `shared/` 是既有方向。

## 要求

1. `worker/output-sections.ts` 新增导出：
   - `parseVerdictTable(text)`：定位 H2 `## 断言裁决`（含别名，复用文件内既有 `h2Headings`/fence 状态机 `:128-188`），解析七列 `claim|类型|裁决|判定|证据|取数|原因`；列序任意、多余列忽略、全角归一、fence 内不计；解析失败的行进 `errors`。
   - `claimCoverage(claims, table)`：返回 `string[]`，判据与文案：
     - `claims:missing-table`（无表）
     - `claim:<id>:missing-row` / `claims:extra-row:<id>`
     - `claim:<id>:verdict`（不在 `closed|partial|unverified`）、`claim:<id>:finding`（不在 `成立|不成立|无法判定`）
     - `claim:<id>:verdict-finding`（映射不一致：closed→成立/不成立；unverified→无法判定；partial→部分成立）
     - `claim:<id>:evidence`（closed/partial 无证据；证据 ref 语法不符；`path` 不存在；`line > 行数`；`b-a > 200`）
     - `claim:<id>:reason`（unverified 原因不在 7 词闭集）
     - `claim:<id>:self-evidence`（唯一证据落在自证集合 `{report*.md, output.md, progress.md, task.md}`）
     - `claim:<id>:struct-held`（`类型=struct` 的行计入 closed 分子）
     - `claim:<id>:budget`（`取数` > `min(Σ预算, 30)`）
     - `claim:<id>:tautology`（`陈述` 与 `反证条件` 去否定后相似度 ≥ 0.90，复用 T-01 的判定口径，调用 T-01 导出的函数，不重写）
2. `worker/output-writer.ts`：
   - `TerminalGaps` 加 `claimGaps?: string[]`（**可选**，默认 `[]`，既有手工构造点不需要改）；`ok` 在 `:423` 追加 `&& (claimGaps?.length ?? 0) === 0`。
   - `readTerminalGaps` 的入参加可选 `claims?: Claim[]`（缺省 undefined → 完全不判 claims，行为与改动前逐字节相同）。
   - `## Questions` 首行（`:448`）：有 claimGaps 时追加 `未裁决断言：<前 3 条 id>…`；无 claimGaps 时输出不变。
3. 新增测试 `test/suite/claim-coverage.test.ts`：上列 11 类判据各一正一反；`claims` 缺省时 `TerminalGaps` 与改动前逐字段相同；`## Questions` 行格式；证据语法（`path:line`、`path:a-b`、`cmd => rc=0`、行段越界、路径不存在、自证路径）。
4. 不改既有测试断言；`checkRecovery` 的语义（`worker/output-sections.ts:190-216`）与 `RECOVERY_SECTIONS` 保持不动。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
- `packages/coding-agent/test/suite/claim-coverage.test.ts`

## 写入禁止面

- `worker/worker-mode.ts`（**另一窗口正在改**，T-04b 负责）、`pm/**`、`shared/**`、`autopilot/**`、`packages/multi-workers/**`、`dist/**`

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-coverage.test.ts test/suite/dispatch-recovery-terminal.test.ts
cd ../..
npm run check
```

`dispatch-recovery-terminal.test.ts` 不得改断言而必须通过。`npm run check` 若有 `mwoc-*.test.ts` 的既有 3 warning/2 info（基线，HEAD 同样红），只报告不算失败，但必须给出你的两个文件 0 诊断的证据。

## 改动历史

- 2026-10-21 创建（T-04 拆分而来）

## 交付格式

`output.md` 四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段给：新增导出与行号、11 类判据的用例计数、两条命令输出摘要。残留段写明：`worker-mode.ts` 的接线尚未完成（T-04b）、`fetches` 口径差异。
