# T-06 E1 反证条件契约修正（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding
- 依赖：T-03（`shared/claim-extract.ts`）done
- 性质：**修 PM 卡的设计错误**，不是 worker 的偏差

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（Worker 追踪 goal 一致性——清单里的每条断言都必须"可证伪"，否则一致性无从谈起）。
- T-03 的卡写了"`falsifier` 统一填 `""`"和"产出必须过 `claimsGaps`"，两者**互斥**：
  `claimsGaps` 在 `shared/dispatch-card.ts:1004` 把 `falsifier === ""` 判为结构性 gap（`claim:<id>:falsifier`），
  且不受 `enforce` 影响。worker 如实上报了这个冲突，没有偷偷绕开。
- 决策（PM）：**不放宽校验器**（反证条件是"可证伪断言"的核心，放宽等于把契约做软）；
  改为让 E1 对**机器类来源**派生**具体**的反证条件，对**人判类来源**要求上游提供，缺了如实计数。

## 要求

修改 `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-extract.ts`：

1. 四种来源行的类型都增加可选 `falsifier?: string`；有值就原样使用（trim）。
2. 允许派生（必须**具体可执行**，不得是"判据不成立"这类同义反复）：
   - `antiPatternHits` → `在 <path:line> 处找不到 <pattern>`
   - `diffHunks` → `该 hunk 未体现陈述的改动（符号未改 / 改在其它定位）`
3. **禁止派生**（缺就必须上报，不许编）：
   - `findings` / `acRows` 行、以及任何 `type === "manual"` 的 claim；
   - 缺 falsifier 时：**保留该 claim**（不丢覆盖），并 `gaps.push("extract:falsifier-missing:<id>")`。
4. 结构校验口径改为：调用 `claimsGaps` 后，把返回里以 `:falsifier` 结尾的 gap **换成** `extract:falsifier-missing:<id>`
   （两者一一对应，避免同一问题两种措辞），其余 gap 原样透传。
   `extract:falsifier-missing` 不得导致 throw，也不得导致 claim 被丢弃。
5. **`struct` 前缀规范化**：`type === "struct"` 时判据前缀必须是规范形 `shape:`；
   输入写成 `fs:` / `struct:` 时改写为 `shape:`（保留其余文本），避免 `claim:<id>:type-prefix` 假告警。
   `cmd:`/`grep:`/`manual:` 同样允许小写规范形，其它前缀不改写。
6. 其余行为（幂等、id 分配、定位、`extract:lost-source-row`、`extract:foreign-locator`）保持不变。

## 交付格式

- 改 `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-extract.ts`
- 改 `packages/coding-agent/test/suite/claim-extract.test.ts`（保留原 11 条，新增至少 5 条）：
  ① finding 带 falsifier 原样保留；② finding 缺 falsifier → 保留 claim + `extract:falsifier-missing:C-0x`；
  ③ antiPatternHit 派生 `在 path:line 处找不到 <pattern>`；④ diffHunk 派生的反证条件不含"判据不成立"字样；
  ⑤ `fs:` 前缀被规范成 `shape:` 且不产生 `type-prefix` gap。
- 报告 `report.md` 四段；`## 证据` 里贴出"原 11 条 + 新增 5 条"的实际 passed 数。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-extract.ts`
- `packages/coding-agent/test/suite/claim-extract.test.ts`

## 写入禁止面

- `shared/dispatch-card.ts`（**禁止**为迁就 E1 放宽 `claimsGaps`）
- 其他 `packages/**`、`.mw/**`、`.agenticdoc/**`、`dist/**`

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-extract.test.ts`（≥16 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡：T-03 上报的 `falsifier=""` × `claimsGaps` 契约冲突 | `dispatch-card.ts:1004`、T-03 report |
