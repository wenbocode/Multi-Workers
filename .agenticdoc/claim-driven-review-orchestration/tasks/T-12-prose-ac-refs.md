# T-12 散文降级补 AC 引用解析（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1 出口补齐（实测暴露的缺口）
- type: coding
- 依赖：T-10（`pm/review-split-plan.ts`）、T-11（`pm/review-split-gate.ts`）done

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（拆不拆必须由**真实输入**决定，而不是合成卡自证）。
- 实测证据：`.agenticdoc/claim-driven-review-orchestration/evidence/m1-exit-probe-20261022.md`。
  四张**真实** review 卡里三张散文卡全部 `units=0 claims=0 gap=no-source`，原因不是实现 bug，而是降级规则
  要求"条目自带 `path:line`"，而 QG 卡的写作习惯是**定位写在「上下文/被审对象」、要求写在「要求/审计目标」**：

  ```
  T-QG-evidence-closure.md   [要求] asks=12 withLocator=0     AC refs: AC-001,003,008,009,012,013
  QG-review-2.md             [要求（这是本轮的核心）] asks=11 withLocator=0
  ```
- 可用的确定性桥（**不许用 LLM、不许猜**）：条目引用 `AC-<n>` 时，用该 key `spec.md` 里该 AC 的行号做定位；
  条目写 `AC-001 到 AC-013` 区间时，按区间**逐条展开**（"每条 AC 都要给判定"正是 merge 要核的守恒项）。
- 另有 T-10 的一个真 bug：no-source 分支 `asks=12 mapped=0` 但 `unmapped=[]`，违反 `asks - mapped === unmapped.length`。

## 要求

### A. `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-plan.ts`

1. `PLAN_HEADINGS` 增加 `"审计目标"`（保留既有前缀匹配，`要求（这是本轮的核心）` 仍算 `要求`）。
2. 输入增加 `acIndex?: Record<string, string>`（AC id → 形如 `spec.md:42` 的定位），可选。
3. 每个 ask 条目的 claim 派生顺序（先命中先生效）：
   1. 条目自带 `path:line` / `path:a-b` → 同现状；
   2. 条目含**区间** `AC-(\d{3})\s*(到|至|~|～|-|–|—)\s*AC-(\d{3})` → 展开区间内每个 id
      （升序、含两端、上限 200 个；超出则只取前 200 并加 `extract:range-truncated:<n>`），
      **每个 id 一条 acRow**（`locator = acIndex[id]`，判据 `manual: <条目摘要> [<id>]`）；
   3. 条目含 `AC-\d{3}` 单引用 → 一条 acRow（同上）；
   4. 都不满足 → 该条目进 `unmapped`。
   `acIndex` 里查不到的 id → 该 id 不产 claim，并追加 `extract:ac-unresolved:<id>`。
4. **`l0` 语义改为「ask 覆盖率」**（多值映射）：
   `asks` = ask 条目数；`mapped` = **产生了至少 1 条 claim 的条目数**；`unmapped` = 产生 0 条的条目摘要。
   不变式 `asks - mapped === unmapped.length` 在**所有分支**（含 no-source）必须成立。
   `claims` 可以大于 `mapped`（一条"判 AC-001..AC-013"展开成 13 条），模块注释要写明这一点。
5. `no-source` 判定改为"没有任何条目产出 claim"（不再看有无内联定位）；该分支的 `unmapped`
   必须装**全部**条目摘要（这就是上面那个 bug 的修法）。
6. 纯函数、幂等、不抛异常；其余（id 分配、单元卡渲染、回执行措辞）不变。

### B. `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-gate.ts`

7. `planReviewSplitGate` 构造 `acIndex` 并传入：
   - 读 `<agenticdocRoot>/<ownerKey>/spec.md`（存在才读，读不到 → 空表，不报错）；
   - 对每个 `AC-\d{3}` 取**首次出现**的 1-based 行号，记 `"<相对 projectDir 的 spec.md 路径 或 spec.md>:<line>"`；
   - 不得读其它文件、不得跑命令。

## 交付格式

- 改上面两个源文件；补测试：
  - `test/suite/review-split-plan.test.ts` 新增 ≥8 条：区间展开（13 条）、单引用、
    `acIndex` 缺失 → `extract:ac-unresolved` 且条目进 `unmapped`、
    `审计目标` 段被扫描、`要求（…）` 前缀仍匹配、no-source 分支 `unmapped` 装全部摘要、
    区间上限截断、幂等；
  - `test/suite/review-split-gate.test.ts` 新增 ≥2 条：临时 `spec.md` 提供 `AC-001..AC-013` →
    manifest `ids` ≥ 5 且每条 `<taskKey>-u<k>` 唯一；`spec.md` 缺失 → 仍写出 manifest、不抛。
- 报告 `report.md` 四段；`## 证据` 里贴出"散文卡式 fixture → 回执行"的实跑行。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-plan.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-gate.ts`
- `packages/coding-agent/test/suite/review-split-plan.test.ts`
- `packages/coding-agent/test/suite/review-split-gate.test.ts`

## 写入禁止面

- `pm/ui-bridge.ts`、`shared/**`、`.mw/**`、`.agenticdoc/**`、`dist/**`、其他任何文件

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/review-split-plan.test.ts test/suite/review-split-gate.test.ts`
（`review-split-plan` ≥20 passed、`review-split-gate` ≥10 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡：真实 QG 卡 `units=0`（定位与要求不同段）+ `l0` 算术 bug | `evidence/m1-exit-probe-20261022.md`、`review-split-plan.ts:216`（`scanChecklistEntries`） |
