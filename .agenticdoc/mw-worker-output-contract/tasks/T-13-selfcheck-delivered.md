# T-13 · 自检回合条件改「已交付」+ TS 侧 S2 清单全角色注入（选项 C，D-015 裁决）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「phase 门禁」「项目级目标对齐」——`exit=2` 是 PM 唯一能看见的产物质量信号；自检回合的目的是**减少假 `exit=2`**，而不是绕过 `no-product` 告警）。
- **背景（D-015 已裁决，选项 C）**：T-05 实现里有两处收窄，为保住写面外钉死测试而缩小了新行为，与卡/设计字面不一致：
  1. **AC-003 TS 半边收窄**：`pm/ui-bridge.ts` 的 `renderCardSeedSections` 实际条件为 `sections.type !== undefined && isWritelessRole(sections.type)`，导致**经 PM（TS 路径）派发的 coding 卡不带 S2 清单**；卡原文门控是「`card is not None`」。当时为避开 `test/suite/dispatch-card-injection.test.ts`（对 coding fixture 逐字节钉死，不在 T-05 写面）。
  2. **AC-004 自检回合收窄**：`worker/worker-mode.ts::settleOrSelfCheck` 实际要求 `judgedProductFile(taskDir) !== undefined` 才发回合，导致 **reply-only 的被判 run（产物 = settle 回复，无 report 文件）拿不到修复回合**，直接 `exit=2`；R8 明确登记了这 3 处既有用例预期要改。PM 已核实 `dispatch-recovery-terminal.test.ts:162` 与 `output-recovery-contract.test.ts:282` 正是该形态（delivered=true，靠回复里的 machine signal，无产物文件）。
- **选项 C 的口径（PM 已核实机制，写死在这里，不要自行发挥）**：
  - 回合条件从「有产物文件」改为「**已交付**」，与 `finishSuccess` 用**同一谓词**：`isDelivered = isWritelessRole(meta.type) ? hasDeliverableEvidence(taskDir, lastAssistantText).delivered : true`（写角色经 `hasReportProduct` 守卫，delivered 恒 true）。
  - **未交付**（`no-product` 形态）**不发回合、保持立即 `no-product` 裁决**（AC-006/C5 告警不被延后）——这是选项 C 与选项 B 的分界线，必须保住。
  - 回合仍受 `judgeRecoveryHere()`（即 `judgedType !== undefined && (isWritelessRole || hasReportProduct)`）与 `substantive.length > 0` 与 `!selfCheckSent`（每进程一次）约束。
- **已知会变的用例（R8 登记，预期内）**：`test/suite/dispatch-recovery-terminal.test.ts:162`（delivered 但 reply-判）与 `test/suite/output-recovery-contract.test.ts:282`（同形态）——从「单 settle 终态 NC」改为「首 settle 发回合（run.json 保持 running）→ 第二次 settle 落终态」。`mwoc-w2` 的 AC-002 表全部为 file-backed（`report:`/`output:` 夹具，且已是两次 settle 模式），PM 已核**不变**。
- **未交付用例必须原样绿**：`test/suite/mwds-t04-deliverable.test.ts:401`（undelivered read-only settle ⇒ `exit=2` + `no-product:` + 一条告警）、`mwds-t03` 的未交付用例等。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（**仅** `settleOrSelfCheck` 的回合条件）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（**仅** `renderCardSeedSections` 的注入条件）
- `packages/coding-agent/test/suite/mwoc-w2-contract-judgment.test.ts`
- `packages/coding-agent/test/suite/dispatch-card-injection.test.ts`（T-13 加入写面：更新 coding fixture 的 `expected` 字节）
- `packages/coding-agent/test/suite/output-recovery-contract.test.ts`（R8 登记）
- `packages/coding-agent/test/suite/dispatch-recovery-terminal.test.ts`（R8 登记）

## 写入禁止面

其余一切路径。特别地：`worker-mode.ts` 的抽取器/记账段（T-02）、检查点段（T-04）、`judgeRecoveryHere`/`finishSuccess`/`readTerminalGaps` 语义、`output-writer.ts`、`output-sections.ts`、`shared/**`、`packages/multi-workers/**`、`mwds-t03-bash-write-scope.test.ts`、`mwds-t04-deliverable.test.ts`、`agent-team-loop*.test.ts`、`worker-file-tool.test.ts` 一律只读。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **回合条件（选项 C 核心）**：`settleOrSelfCheck` 的回合条件由 `judgedProductFile(taskDir) !== undefined` 改为与 `finishSuccess` **同一** `hasDeliverableEvidence(taskDir, lastAssistantText).delivered`（writeless 角色）+ 保留外层 `judgeRecoveryHere()`、`substantive.length > 0`、`!selfCheckSent`。注释更新为「有东西可修就给一次机会；未交付保持立即 no-product 裁决」。
2. **未交付不动**：`mwds-t04:401` 形态（undelivered）在改动后仍 `exit=2`、`no-product:`、恰 1 条告警、**无**自检回合 —— 给原始断言输出。
3. **R8 两处用例改两次 settle 流**：`dispatch-recovery-terminal:162` 与 `output-recovery-contract:282` 改为「首 settle ⇒ `run.json.status === "running"`、`sendUserMessage` 恰 1 次且 `deliverAs === "followUp"`、trace 落 `recovery-gap` 行；第二次 settle（补全）⇒ `exit=0` /（补同一缺口）⇒ 终态 NC 且 `缺失段：` 逐字」。**列出全部被改动的用例，逐条说明为何改**；除这两处与下述枚举外任何新增红 ⇒ 停手上报。
4. **`mwoc-w2` AC-002 表逐条复核**：确认 file-backed 用例在选项 C 下结论不变（PM 已核，但你要重跑给出原始输出）；若发现任一 AC-002 行因「已交付」条件改变结论，逐条登记并改（该文件在本卡写面内），并在证据里说明。
5. **TS 侧注入全角色**：`renderCardSeedSections` 的条件改为 `sections.type !== undefined ? recoveryContractSection(sections.type) : ""`（即门控 =「card 有 type」；`recoveryContractSection` 对契约外 type 本就返回 `""`，故无契约角色不受影响）。删除 `isWritelessRole` 收窄。
6. **`dispatch-card-injection.test.ts` 更新**：coding fixture 的 `expected` 字节加入 `## 交付段契约（本角色）` 块（base four + `改动清单`，即 `recoveryContractSection("coding")` 的逐字输出）；`card=None`/无 type 的构造保持 pre-T-05 字节（不含清单）。给出改前/改后 `expected` 的 diff 摘要。
7. **幂等**：`applyCardSeedSections`/`renderCardSeedSections` 二次应用字节不动点、标题恰 1 个；与 T-06 Python 注入同节不重复（已有测试，重跑确认）。
8. **不回归**（给原始条数）：`mwoc-w2`（改后仍全绿，条数可增）、`dispatch-card-injection`、`output-recovery-contract`、`dispatch-recovery-terminal`、`mwds-t03` **63/63**、`mwds-t04` **19/19**、`mwds-t02` 38/39、`agent-team-loop` 196/197、`worker-file-tool` 7/9（后三者红 = DR6 HEAD 既存）、`npx tsgo --noEmit` = 0。
9. 开工前 `git status` + mtime 确认无第三方编辑 `worker-mode.ts` / `ui-bridge.ts`；若有，停下并在「残留与未验证」报告。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令 + 原始输出**：选项 C 回合条件的实现 diff、R8 两处用例改前/改后断言输出、`mwds-t04:401` 未交付形态原始输出、`mwoc-w2` AC-002 表逐条结论、`dispatch-card-injection` 改前/改后 expected diff、幂等输出、八组套件条数、`tsgo` 退出码。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w2-contract-judgment.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-injection.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/output-recovery-contract.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-recovery-terminal.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t04-deliverable.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t02-write-intent.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts
npx tsgo --noEmit
```

## 改动历史

- 2026-10-14 D-015（用户已按推荐）：T-05 的两处收窄按**选项 C** 处置 —— 回合条件改「已交付」（未交付保持立即 no-product）+ TS 侧注入全角色；R8 登记的两文件用例改为两次 settle 流；`dispatch-card-injection.test.ts` 加入写面更新 expected。
