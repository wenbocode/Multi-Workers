# T-04 簇装箱：`shared/claim-pack.ts`（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`。
- 为什么不是"5 条一刀切"：RQ-2 §4.6 实测——`struct` 父+子占 N+1 槽，N≥5 的 16/29（55.2%）会被定宽切片拆散；
  `manual` 密度是 n 的函数；17.2% 的 `struct` 需要运行时枚举，派发期不可解。
  所以单元 = **claim 簇的装箱**。语料 104 单元实测每单元 `Σ预算` 落在 1..9（均值 4.64）。
- 复用契约：`Claim` / `CLAIM_TYPES` / `claimBudgetCaps` 见
  `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:535`、`:1042`。

## 要求

新文件 `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-pack.ts`：

1. `PackOptions = { maxBudgetSum?: number; minUnits?: number }`，默认 `maxBudgetSum = 8`。
2. `packClaims(claims: Claim[], opts?: PackOptions): PackResult`，
   `PackResult = { units: PackUnit[]; packing: PackingRow[]; gaps: string[] }`，
   `PackUnit = { k: number; ids: string[]; budgetSum: number; slots: number; hasMachineClaim: boolean }`，
   `PackingRow = { cluster: string[]; unit: number; why: "struct-atomic"|"budget"|"locator"|"order" }`。
3. 约束（按优先级）：
   - **(a) 簇原子性**：`C-01.3` 这类子行必须与其父 `C-01` 同单元；同一 claim 的多条 `定位`
     （`judgement` 里出现的其它 `path:line`）不得跨单元；违反 → `split:orphan-child:<id>`。
   - **(b) 预算**：每单元 `Σ预算`（`manual` 按 2 计）≤ `maxBudgetSum`。
   - **(c) 至少一条机检 claim**：`type ∈ {cmd,grep,struct}`；某单元只有 `manual` →
     把它并入相邻单元（若并入会破 (b)，则 `split:unit-infeasible:<k>:manual-only`）。
   - **(d) 单元数下界**：`K = ceil(Σslots / 5)`，`slots` = claim 数（`manual` 算 2 槽）；
     实际 `units.length ≥ K`，不足时补 `split:unit-infeasible:<k>:below-min`。
4. 单条簇自身超预算（如一条 `manual` 链 + 子行导致 `Σ预算 > 8`）→
   `gaps.push("split:unit-infeasible:<k>:cluster-over-budget")`，并且**仍然输出该单元**（不丢 claim）。
5. 确定性：同样的 `claims` 输入永远得到同样的 `units`/`packing`（按输入顺序装箱，不做随机/排序抖动）。
6. 纯函数，不读写文件，不抛异常。

## 交付格式

- 新增 `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-pack.ts`
- 新增测试 `packages/coding-agent/test/suite/claim-pack.test.ts`，至少 8 条：
  ① 5 条 grep → 1 单元（`Σ预算 5 ≤ 8`）；② 10 条 grep → 2 单元，每个 ≤ 8；
  ③ `struct` 父 + 6 子行 7 条 → **不拆散**且只出 `cluster-over-budget` gap；
  ④ 只有 `manual` 的单元被并入相邻单元；⑤ 全是 `manual` → `manual-only` 或 `cluster-over-budget`；
  ⑥ 单元数下界 `K` 的计算与补齐；⑦ 确定性（两次深等）；⑧ `packing` 里每条 claim 恰好出现一次。
- 报告 `report.md` 四段：`## 结论` `## 证据` `## 未覆盖面声明` `## 上下文来源`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-pack.ts`
- `packages/coding-agent/test/suite/claim-pack.test.ts`

## 写入禁止面

- 任何既有文件、`.agenticdoc/**`、`.mw/**`、`dist/**`

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-pack.test.ts`（8 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡（M1 拆分） | RQ-2 §4.6、spec AC-002、dispatch-card.ts:1042 |
