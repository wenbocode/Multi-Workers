# T-01: L1 契约层 —— claims 块解析、校验、预算推导（coding）

- Key: claim-driven-review
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「解决单 Agent 长上下文溢出和无法并行的问题」；本任务只做契约层，不改任何行为开关）。
- 设计依据：`.agenticdoc/claim-driven-review/design.md` §2、§3.1、§7 D-001/D-005/D-007。
- 上游实测（**不要重新调研**）：
  - 每 worker 5 条 claim、30 次取数、393,216 B 累计字节上限（`evidence/research/spec-rq1-review-corpus-20261020.md` §5）。
  - 判定单元四类分布 cmd 21 / grep 28 / struct 29 / manual 26（`spec-rq3-claim-taxonomy-20261020.md` §1.2）；自动分类一致率仅 63.5%，故**只校验自报类与前缀一致**（同文件 §2.4）。
  - 现有卡 gate 的插入点与拒绝形态：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:2585`、`:2188`、`:2603-2616`（`evidence/research/spec-rq2-seams-20261020.md` §1.3/§1.4）。
- 现状：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts` 已有 `TYPE_EXTRA_SECTIONS`（`:194-198`）、`DISPATCH_TYPE_VOCABULARY`（`:221-232`）、`isKnownDispatchType`（`:461-466`）；`worker/output-sections.ts:128-188` 已有 fence 状态机与 H2 别名判定器（**不要从 `shared/` 反向 import `worker/`**）。

## 要求

1. 在 `shared/dispatch-card.ts` 新增并导出（命名与顺序即 T-06 平价锁的判据，不得改名）：
   - `CLAIM_TYPES = ["cmd","grep","struct","manual"] as const`
   - `UNVERIFIED_REASONS = ["budget","no-access","not-found","ambiguous","environment","out-of-scope","awaiting-input"] as const`
   - `CLAIM_GATE_DEFAULT = "advisory" as const`
   - `CLAIM_BUDGET = { perClaim: 6, callCap: 30, hardCap: 35, claimByteCap: 65536, byteCapMax: 393216 } as const`
   - `parseClaimsBlock(text: string): ClaimBlock`（`{ present: boolean; claims: Claim[]; errors: string[] }`）
   - `claimsGaps(block: ClaimBlock, opts: { projectDir: string; enforce: boolean }): string[]`
   - `claimBudgetCaps(claims: Claim[]): { fileCap: number; byteCap: number }`
2. `parseClaimsBlock` 的解析契约：
   - 区块起止：`<!-- mw-claims: v1 -->` … `<!-- /mw-claims -->`；缺结束标记时容错到下一个 H2 或文件尾。
   - 表格七列 `claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算`；列顺序任意、多余列忽略、表头别名 `claim|断言|Claim`；全角 `：｜` 归一到半角；fenced code block 内的表不计。
   - `claim` 形如 `C-01`；子行 `C-01.3` 仅在父 claim 类型为 `struct` 时合法。
   - 不可解析的行进 `errors`（`claim:<row>:unparsable`），**不抛异常**（P-048：schema 过严导致连续误拒）。
3. `claimsGaps` 的判据（返回项形态固定，供 T-02 拼拒绝文案）：
   - `claim:<id>:type`（类型缺失/不在闭集）、`claim:<id>:statement`、`claim:<id>:falsifier`、`claim:<id>:locator`、`claim:<id>:judgement`、`claim:<id>:budget`
   - `claim:<id>:type-prefix`（判据前缀与自报类不一致；`cmd:`/`grep:`/`shape:`/`manual:`）
   - `claim:<id>:locator-unresolved`（`symbol` 定位、文件不存在、路径在 projectDir 外——`statSync` 失败一律归此项，**只有 `enforce` 时才进返回值**；advisory 下改由 `warnings` 返回）
   - `claim:<id>:locator-range`（目标文件 > 32768 B 时 `定位` 必须是 `path:a-b` 行段）
   - `claim:<id>:tautology`（`陈述` 与 `反证条件` 去否定词后 token 相似度 ≥ 0.90，且 `判据` 中不含任何未出现在 `陈述` 里的 artifact token）
   - `claims:budget-sum:<n>>40`、`claims:manual-overflow:<k>/<n>`（manual 条数 > `min(4, ceil(n/3))`）
   - `cmd` 类 `定位` 必须是 `evidence/claims/<file>#<claim-id>` 形态，否则 `claim:<id>:cmd-locator`（D-005：PM 预执行落盘）
   - `判据: cmd: TBD(<name>)` 视为合法（不报 gap）
4. `claimBudgetCaps`：`fileCap = Math.min(CLAIM_BUDGET.callCap, Σ(类型==="manual" ? 2 : 1))`、`byteCap = Math.min(CLAIM_BUDGET.byteCapMax, CLAIM_BUDGET.claimByteCap * claims.length)`；claims 为空时返回 `{ fileCap: 0, byteCap: 0 }`。
5. `enforce` 只控制"是否把 warning 升级为 gap"：`opts.enforce === false` 时，第 3 条中 `locator-unresolved`、`locator-range`、`tautology`、`cmd-locator`、`claims:*` 全部降为 warning（返回空数组）；结构性缺失（`type/statement/falsifier/locator/judgement/budget`）在两种模式下都是 gap。
6. 新增测试 `packages/coding-agent/test/suite/claim-block.test.ts`：至少覆盖 ① 正常 3 行解析；② 列序打乱 + 别名 + 全角；③ fenced block 内表不计；④ 子行 `C-01.3`（父 struct 通过 / 父 grep 拒）；⑤ 七种结构性缺失各一条；⑥ `enforce=false` 时五类软 gap 降级；⑦ `cmd: TBD(...)` 放行；⑧ 预算求和（含 manual 记 2）与两个上限；⑨ 同义反复正反例各一；⑩ 大文件无行段 → `locator-range`。
7. 不新增依赖，不用 `any`；只用可擦除语法（无 enum/namespace/参数属性）。文件超 500 行时按"解析 / 校验 / 预算"三段分区注释。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`
- `packages/coding-agent/test/suite/claim-block.test.ts`

## 写入禁止面

- `pm/**`、`worker/**`、`autopilot/**`、`packages/multi-workers/**`、`dist/**`、`CHANGELOG.md`、`README.md`（这些由 T-02…T-06 负责）

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-block.test.ts
cd ../..
npm run check
```

两条都必须 0 fail / 0 诊断（`npm run check` 输出全量，不截断）。

## 改动历史

- 2026-10-21 创建（无既有改动）

## 交付格式

`output.md` 必带四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段给出：新增导出清单（名字 + 行号）、测试用例数、两条验收命令的原样输出摘要。残留段必须写明未覆盖的解析形态。
