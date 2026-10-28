# T-10 `planReviewSplit` 组合器（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding
- 依赖：T-01（开关）、T-03/T-06（提取）、T-04（装箱）、T-07/T-09（manifest）全部 done

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（PM 管多 worker 并行；拆与不拆必须是**可见的、可回退的决定**）。
- `plan` 档的定义（`design.md` §2.2）：产出 manifest 与一条回执行，**不派发任何子卡、不建子卡目录、不写队列行**。
- 本卡只做**纯组合器**（一个函数把四块零件串起来 + 回执行字符串），**不碰 `pm/ui-bridge.ts`**；
  派发链接线是下一张卡（T-11）。
- 零件接口：
  - `shared/review-split.ts` → `resolveReviewSplit(projectDir, env)`、`REVIEW_SPLIT_MODES`
  - `shared/claim-extract.ts` → `extractClaims(input)` → `{claims, gaps, sourceRows}`
  - `shared/claim-pack.ts` → `packClaims(claims, opts)` → `{units, packing, gaps}`
  - `shared/split-manifest.ts` → `buildSplitManifest(input)`、`serializeSplitManifest(m)`
  - `shared/dispatch-card.ts:1042` → `claimBudgetCaps(claims)` → `{fileCap, byteCap}`

## 要求

新增 `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-plan.ts`：

1. `planReviewSplit(input: ReviewSplitPlanInput): ReviewSplitPlan`，`input`：
   ```ts
   { taskKey: string; projectDir: string; cardText: string; mode: "plan" | "on" }
   ```
2. **清单来源**（按顺序，取第一个非空）：
   - 卡文里有 `<!-- mw-claims: v1 -->` 块且解析出 ≥1 条 claim → 直接用
     （`parseClaimsBlock`，`block.claims`）；
   - 否则**确定性降级**：扫描 `## 检查项` / `## 审查要求` / `## 要求` 三个标题下的列表项，
     取**含 `path:line` 或 `path:a-b`** 的条目作为 `findings` 行：
     `{ text: 去列表符号后的整行, locator: 该行内第一个 path:line, judgement: "manual: " + 截断到 80 字的条目 }`；
     一个条目都没有 → 返回 `{ mode, receipt: "[review-split] mode=... units=0 claims=0 gap=no-source", ... }`
     并带 gap `extract:no-source`（**不得**凭空造 claim）。
3. 组合：`extractClaims(...)`（仅降级路径）→ `packClaims` → `buildSplitManifest`：
   - `units[*]`：`taskKey = "<taskKey>-u<k>"`、`writeFace = "workers/<taskKey>-u<k>"`、
     `text` 用 `serializeUnitCardText()`（本文件内的小函数：把该单元的 claims 渲染成
     `| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |` 七列表，**逐字复用**母卡单元格，
     不要重写文本）；
   - `l0`：`asks` = 降级路径下的条目总数、`mapped` = 成功变成 claim 的数量、
     `unmapped` = 每条的截断摘要（`asks - mapped` 必须等于 `unmapped.length`）。
4. 回执行（**逐字**格式，便于以后统计）：
   ```
   [review-split] mode=<plan|on> units=<K> claims=<n> cap=<parentFileCap> capSum=<Σ unit fileCap> inflation=<ratio 2 位小数> l0=<mapped>/<asks> l1=<ok|gaps:n>
   ```
   `l1` 的 `n` = `packGaps.length + manifestGaps.length`（manifest 用 `verifySplitManifest` 自检）。
5. `ReviewSplitPlan = { mode; receipt: string; manifest?: SplitManifest; manifestText?: string; gaps: string[] }`。
   纯函数：不读写文件、不调模型、不抛异常（P-048）；`mode` 非法值由调用方保证（本函数只接受 plan/on）。

## 交付格式

- 新增 `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-plan.ts`
- 新增测试 `packages/coding-agent/test/suite/review-split-plan.test.ts`，至少 8 条：
  ① 带 claims 块的 11 条卡 → units ≥ 1 且 `ids` 并集等于原 11 条；② 回执行前缀/字段名逐字匹配正则；
  ③ `l0` 的映射算术自洽（`asks-mapped == unmapped.length`）；
  ④ 散文卡（`## 检查项` 下 4 条带 `path:line` 的条目）→ 产出 4 条 manual claim + `extract:falsifier-missing` 计数；
  ⑤ 一个条目都不含 `path:line` → `units=0` + `extract:no-source`，且**不抛异常**；
  ⑥ `inflation` = `capSum / cap` 且 `cap = 0` 时不除零（输出 `inflation=0.00`）；
  ⑦ manifest 自检 `l1=ok`（诚实构建时）；⑧ 幂等（同一输入两次 `receipt` 相同）。
- 报告 `report.md` 四段；`## 未覆盖面声明` 必须写明"未接 `ui-bridge`，plan 尚未真实落盘"。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-plan.ts`
- `packages/coding-agent/test/suite/review-split-plan.test.ts`

## 写入禁止面

- `pm/ui-bridge.ts`（下一张卡）、任何其他既有文件、`.mw/**`、`.agenticdoc/**`、`dist/**`

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/review-split-plan.test.ts`（≥8 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡（M1 组合器） | design.md §2.2、AC-S2 |
