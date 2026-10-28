# KDR: claim-driven-review

## R（需求）

- 技术栈: TypeScript（agent-team-loop 扩展）+ Python（mw），无 pi 核心改动
- 边界: 不做 review 工具集变更、不做循环内压缩、不做自动修复
- 关键约束: 成本必须与"断言数量"绑定而非与仓库规模绑定；`unverified` 不得退化为静默 PASS；派发拒绝零副作用

## A（架构）→ system-design 追加

- 四层：L1 契约（`shared/dispatch-card.ts`：`parseClaimsBlock`/`claimsGaps`/`claimBudgetCaps`）→ L2 派发（`pm/ui-bridge.ts:2585` gate + `mergeReadScope`；`autopilot/dispatch.py` 的 `dispatch_card` 回 claims、`_read_scope_caps` 下移到 1495 之后）→ L3 结算（`output-writer.ts:357-425` 的 `TerminalGaps.claimGaps` + `worker-mode.ts:3872` 折叠 + 独立 `[CLAIMS]` trace 行）→ L4 度量（`run.json` 子对象 + `usage.py` + `status-model.ts`）。
- 数据只走两种文件：卡文 claims 块（注入 task.md）与产物 `## 断言裁决` 七列表；结算不回读卡文件（D-002）。
- 复用 `review` 类型，不新增类型（D-001）；不给 review 配 `bash`，`cmd` 类断言由 PM 预执行落盘证据（D-005，待确认）。
- 灰度：`CLAIM_GATE_DEFAULT=advisory` 常量 + `MW_CLAIM_GATE=enforce` 环境变量，两侧同名同义（D-006，待确认）。

## I（实施）→ PM 执行中追加

## D（执行中的决策/修订）

- **D-011**（已落）advisory 零拒绝：结构性 gap 也只进 `warnings`，不拒派发。理由：P-048 实测 schema 过严 → 连续误拒 → 30 分钟零产出。
- **D-012**（已落）`read_scope` = key 目录 + goal 锚点 + 每条 claim 的 `定位`（去 `:line`/`:a-b`/`#id`，拒绝对路径与 `..`）。原实现只给 key 目录，断言指向 `packages/**` 时 review 单元读不到。
- **D-013**（已落）声明了 claims 块但解析为 0 条时**不得静默**：`claimsDeclared` 区分「无块」与「有块零解析」，后者输出 `claims=0(unparsed)` 且解析错误进 `warnings`。
- **D-014**（本轮，T-07 实测驱动）三处结算缺陷，由 T-08 修：
  1. **`carried-from` 判据换掉 mtime**。原判据「证据文件 mtime < task.md mtime」在 T-07 首轮精度 **0%**：C-01/C-03 判 `closed` 且引真实源码，仅因文件早于 task.md 就被判复用。新判据：「该行引用的文件本轮**未被放行读过**」——这才是「复用了别人的阅读」的可观测信号（`[TOOL] read <path>` 带路径）。
  2. **预算公式补回 `perClaim`**：`fileCap = min(callCap, perClaim × n)` = 5 条 → 30。原式 `min(30, Σ预算)` 里 `Σ预算` 是 1/claim 的**权重**，不是取数次数，导致 5 条 grep claim 只有 5 次配额、第 5 次工具调用后彻底饥饿（`5/5 calls already allowed`）。`CLAIM_BUDGET.perClaim = 6` 此前是死代码；`6 × 5 = 30 = callCap` 证明原意如此。`Σ预算 ≤ 40` 门禁职责不变。
  3. **`fetches` 只计放行**。`readCount++` 在 `tool_execution_start`（早于 guard），实测 `fetches=12 > fileCap=5`，把 7 次被拒调用也算进去了，会让 `tokens_per_closed_claim` 的分母虚高。新增 `allowedReads` 走 read-scope 放行分支；`readCount` 原口径保留（checkpoint/重复读检测用）。
- **D-015** 文档纠错：`grep`/`find`/`ls` **与 `read` 共用**调用配额（只有字节不计），上一轮 README 写的「unrestricted」是错的。

（execute 进行中：T-01..T-06、T-07a 已完成；T-07b 真跑暴露缺陷 → T-08）
