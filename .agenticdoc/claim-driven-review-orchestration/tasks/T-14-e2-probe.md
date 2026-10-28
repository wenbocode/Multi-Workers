# T-14 E2 可行性探针：一张真实 QG 卡能否被 LLM 提成**机检** claims（research）

- Key: claim-driven-review-orchestration
- 里程碑：M1 判决（拆分是否成立）
- type: research
- 依赖：T-13 done（确定性路径已到极限）

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（拆不拆由数据与真实输入决定，不由"我造好了"决定）。
- 实测结论：`.agenticdoc/claim-driven-review-orchestration/evidence/m1-exit-probe-20261022.md` §6。
  确定性路径（E1）在四张真实 QG 卡上给出 claims，但**每一张卡的每一个单元都是 `manual-only`**：

  ```
  T-QG-evidence-closure  units=12 claims=34 l0=6/17 fals=34 l1=gaps:13 inflation=6.20
    └─ split:unit-infeasible:1..12:manual-only（12 个单元全部不可行）
  ```
  即：确定性提取只能把「逐条判 AC」拆成「逐条判 AC 的更小块」，**没有一条可机检断言**，
  而装箱规则要求每单元 ≥1 条机检 claim → 拆分在门禁意义上不成立。
- spec 的 AC-E2 是**唯一未验证的路径**：一个受限 triage 单元（≤12 次读）读「brief + 变更面/被审面索引」，
  产出 claims 块。它到底是能产出 `grep:`/`struct:`/`cmd:` 这类可机检断言，还是只能产出换皮的 manual 断言？
  **这是本轮唯一的开放问题。**

## 你的任务（只做一件事）

对**一张**真实卡做 E2 提取实验：`.agenticdoc/mw-worktree-junction-guard/tasks/T-QG-evidence-closure.md`
（配套：`.agenticdoc/mw-worktree-junction-guard/spec.md`、该 key 的 `design.md`/`achieved.md`）。

预算：**≤12 次文件读**（自己数，报告里写实际次数）。不要写任何文件，不要执行命令。

## 要求

1. **先读卡，列 ask**：把这张卡要求审查者做的事，拆成 ask 清单（W1…Wn），标注每条 ask 的来源行。
2. **再提 claims**（这是核心）：对每条 ask 提可证伪断言，**严格按**既有 claims 契约填七列
   （`claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算`），类型只能是 `cmd` / `grep` / `struct` / `manual`，
   判据前缀必须是 `cmd:` / `grep:` / `shape:` / `manual:`。
   规则（`shared/dispatch-card.ts:985` 的 `claimsGaps` 是判据，读它确认）：
   - `grep:` 判据必须能在被指定的定位上**直接执行**并给出确定结论；
   - `shape:` 判据必须是可读文件/结构的形状断言（存在性、行数、字段存在、导出名）；
   - `manual:` 只用于**确实无法机检**的判定，且必须写**具体**反证条件（不是"判据不成立"）；
   - 每条 claim 必须带 `定位`（`path:line` 或 `path:a-b`）。
3. **自评机检率**：给出 `机检 claim 数 / 总 claim 数`，并逐条标注"我认为这是机检还是换皮 manual"。
4. **诚实记账**：哪几条 ask 你**提不出**机检断言、为什么（缺坐标 / 需要运行 / 需要判断）。
   不要为了凑数把 manual 包装成 `grep:`——那样的断言会在结算期被 `claim:<id>:tautology` 或
   `claim:<id>:judgement` 判掉，等于白干。
5. **代价估算**：为产出这些 claim，你实际的读取次数与"如果自己直接审这张卡"（不拆）相比，
   信息量是变多还是变少？给出定性判断 + 理由（这是判断拆分是否划算的关键）。

## 交付格式

报告 `report.md`，含：
- `## 结论`：一句话回答「E2 能否为这张卡产出**至少 5 条机检 claim**」，并给机检率。
- `## ask 清单`（W1…Wn + 来源行）
- `## claims 块`（完整七列表，**可直接粘进卡**，用 `<!-- mw-claims: v1 -->` 包裹）
- `## 逐条自评`（机检 / 换皮 manual / 提不出，逐条理由）
- `## 代价估算`
- `## 未覆盖面声明`

不得写除本 worker 目录外的任何文件。

## 唯一证据文件

`.agenticdoc/claim-driven-review-orchestration/workers/<task_key>/report.md`（只此一份产物；不新建其它文件）。

## 种子

- `.agenticdoc/claim-driven-review-orchestration/evidence/m1-exit-probe-20261022.md`（实测数据）
- `.agenticdoc/mw-worktree-junction-guard/tasks/T-QG-evidence-closure.md`（被处理对象）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:985`（`claimsGaps` 判据）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/claim-extract.ts:1`（E1 已能产出的形态）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡 | `evidence/m1-exit-probe-20261022.md` §6（12/12 单元 manual-only） |
