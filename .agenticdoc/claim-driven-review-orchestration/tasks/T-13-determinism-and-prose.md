# T-13 拆分确定性 + 散文覆盖面（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1 出口补齐（第二轮实测）
- type: coding
- 依赖：T-12 done

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（拆不拆由真实输入决定；同一张卡必须给出同一个拆法）。
- 实测证据：`.agenticdoc/claim-driven-review-orchestration/evidence/m1-exit-probe-20261022.md` §6.1 的三条缺陷。
- 缺陷 1（**最严重**）：同一张 `T-QG-evidence-closure.md`、同一批 23 条 claim，
  组合器直调 `units=8`、经门禁 `units=12`。根因：`packClaims` 按定位 token 聚簇，
  而门禁给的 `acIndex` 值是 `.agenticdoc/probe/spec.md:42`、组合器给的是 `spec.md:42` → token 不同 → 聚簇不同。
  **拆分数依赖路径拼法 = 拆法不可复现。**
- 缺陷 2：`signoff/QG-review` 的 AC 范围写在**段标题**（`## 要求（…对应 AC-001..005）`）；
  `T-18-adversarial-qg` 的 `## 要求` 是散文段落，真正的要求在 `## 必须覆盖的 10 项对抗探针`。
- 缺陷 3：AC 派生 claim 全是 manual → falsifier 必缺 → `l1` 永远不是 `ok`，字段失去判别力。

## 要求

### A. 确定性（先修这个）

1. `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-plan.ts`：
   新增 `canonicalizeLocator(locator)`：把定位规范成 `basename:line[-end]`
   （去掉目录与 `.agenticdoc/<key>/` 前缀，只留文件名 + 行号；`path/a.ts:3-5` → `a.ts:3-5`）。
   **所有**进入 `extractClaims` 的定位（内联定位与 `acIndex` 查得的值）都先过它。
2. `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-gate.ts`：
   `buildAcIndex` 产出的值也一律规范成 `spec.md:<line>`（即 `canonicalizeLocator` 之后的结果），
   不再拼相对路径。
3. 新增测试：同一张卡用两种 `acIndex` 拼法（`spec.md:42` / `.agenticdoc/x/spec.md:42`）
   → `units`、`manifest.ids`、`receipt` 全部逐字节相同。

### B. 散文覆盖面

4. ask 段判定放宽为：H2 标题**去掉括号补充后**，**包含** `要求` / `审计目标` / `检查项` / `必须覆盖` / `验收`
   任一关键词即视为 ask 段（例如 `必须覆盖的 10 项对抗探针`）。
5. 条目类型增加**段落**：ask 段内以空行分隔的非列表块也算一条 ask（去掉首尾空白与 markdown 强调标记）。
   列表项行为不变。
6. 段标题里的 AC 引用/区间视为该段条目的**默认范围**：条目自身没有 AC 引用时，继承段标题的 AC 集合
   （支持 `AC-001..005` 与 `AC-001 到 AC-005`；单引用于多引用都按 `acIndex` 解析，未解析的 id 照旧报
   `extract:ac-unresolved:<id>`）。

### C. 回执行可读性

7. `[review-split] …` 增加一个字段 `fals=<n>`（`extract:falsifier-missing` 的条数），
   位置在 `l1=` 之前；`l1` 改为**只计 packing + manifest 的结构性 gap**（不再把 falsifier 缺口算进去）。
   字段顺序固定为：`mode, units, claims, cap, capSum, inflation, l0, fals, l1`（`gap=no-source` 仍追在最后）。
   模块注释与回执行格式说明同步更新。

## 交付格式

- 改上述两个源文件；测试：
  - `test/suite/review-split-plan.test.ts` 新增 ≥6 条：两种 acIndex 拼法等价、段落条目、
    `必须覆盖…` 段被识别、段标题 AC 继承（含区间）、`fals=` 计数正确、`l1` 不再被 falsifier 缺口污染；
  - `test/suite/review-split-gate.test.ts` 新增 ≥2 条：manifest 的 `acIndex` 路径无关（两次不同 ownerKey 目录结构 → 同 units）、
    `fals=` 出现在门禁回执行里。
- 报告 `report.md` 四段；`## 证据` 贴同一张卡两种拼法的 `units/receipt` 实际输出。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-plan.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-gate.ts`
- `packages/coding-agent/test/suite/review-split-plan.test.ts`
- `packages/coding-agent/test/suite/review-split-gate.test.ts`

## 写入禁止面

- `shared/claim-pack.ts`、`shared/claim-extract.ts`、`pm/ui-bridge.ts`、`.mw/**`、`.agenticdoc/**`、`dist/**`、其他任何文件

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/review-split-plan.test.ts test/suite/review-split-gate.test.ts`
（`review-split-plan` ≥27 passed、`review-split-gate` ≥12 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡：拆分数依赖路径拼法、两张真实卡 0 claim、`l1` 与 falsifier 混淆 | `evidence/m1-exit-probe-20261022.md` §6.1 |
