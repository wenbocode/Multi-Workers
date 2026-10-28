# T-03 E1 结构化提取：`shared/claim-extract.ts`（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`；本卡实现 spec 的 **AC-E1（结构化提取，零 LLM）**。
- 为什么需要它：真实 review 的卡是散文，没有 claims 块；拆分的真实前提是"先有一份可机检覆盖清单"。
  E1 是其中最便宜的一档：从**已有清单来源**机械生成断言，不调模型。
- 复用既有契约，不要重新发明：
  - `Claim` 接口与 `parseClaimsBlock`：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:724`
  - `claimsGaps`（判据前缀/同义反复/定位行段校验）：同文件 `:985`
  - `CLAIM_TYPES`（`cmd|grep|struct|manual`）：同文件 `:535`
- 设计依据 `design.md` §2.1 与 spec §2.0「A 类 / B 类」：变更面（diff hunk）生成的属于 **A 类（变更对账）**。

## 要求

新文件 `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-extract.ts`：

1. 输入类型（全部可选，按固定顺序消费：`findings` → `acRows` → `diffHunks` → `antiPatternHits`）：
   - `findings: Array<{ text: string; locator: string; judgement: string }>`（QG finding 行）
   - `acRows: Array<{ text: string; locator: string; judgement: string }>`（spec AC 行）
   - `diffHunks: Array<{ path: string; start: number; end: number; statement: string; judgement?: string }>`
   - `antiPatternHits: Array<{ path: string; line: number; pattern: string; judgement?: string }>`
2. 输出 `{ claims: Claim[]; gaps: string[]; sourceRows: number }`：
   - id 按来源顺序确定性分配 `C-01`、`C-02`…（两位；超过 99 用三位）；
   - `type` 由 `judgement` 前缀决定：`cmd:` → `cmd`、`grep:` → `grep`、`fs:`/`struct:` → `struct`、
     其余（含 `manual:`、无前缀）→ `manual`；`diffHunks` 无 `judgement` 时默认 `manual`，
     但必须带 `statement`（由调用方给出"该 hunk 应该证明什么"）；
   - `locator`：findings/acRows 原样；`diffHunks` → `path:start-end`；`antiPatternHits` → `path:line`；
   - `falsifier` 统一填 `""`（E1 不编造反证条件）；`budget` 默认 1（diff hunk 默认 2，因为它通常要看改动上下文）。
3. **源侧对账**（AC-E1 的机检）：
   - 任一输入行没能产出 claim → `gaps.push("extract:lost-source-row:<index>")`（index 为该来源内的 0-based 序号）；
   - claim 的 `locator` 文件路径不属于输入给的路径集合 → `extract:foreign-locator:<id>`；
   - 产出后调用 `claimsGaps` 校验；把它返回的 errors 原样透传进 `gaps`（**不要自己重写校验**）。
4. **幂等**：同一输入连续调用两次，`JSON.stringify` 深度相等（不含时间戳/随机）。
5. **纯函数**：不读文件、不写文件、不调模型、不抛异常（P-048：坏输入产出 gap 而不是 throw）。

## 交付格式

- 新增 `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-extract.ts`
- 新增测试 `packages/coding-agent/test/suite/claim-extract.test.ts`，至少 8 条：
  ① findings 两条 → C-01/C-02 类型正确；② diffHunk 定位为 `path:a-b`；③ antiPattern → `path:line`；
  ④ 空输入 → 空 claims 无 gap；⑤ 幂等（两次结果深等）；⑥ lost-source-row（空 statement 的 hunk 被丢弃）；
  ⑦ foreign-locator；⑧ 全角冒号/空白容错不产生假 gap。
- 报告 `report.md` 四段：`## 结论` `## 证据` `## 未覆盖面声明` `## 上下文来源`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-extract.ts`
- `packages/coding-agent/test/suite/claim-extract.test.ts`

## 写入禁止面

- `shared/dispatch-card.ts` 及其他任何既有文件、`.agenticdoc/**`、`.mw/**`、`dist/**`

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-extract.test.ts`（8 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡（M1 拆分） | spec AC-E1、design §2.1、dispatch-card.ts:724/985 |
