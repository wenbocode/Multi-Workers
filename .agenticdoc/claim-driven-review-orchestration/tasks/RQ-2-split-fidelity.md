# RQ-2：拆分保真度 —— 怎么机检「子卡还承载原 review 的语义」（research）

- Key: claim-driven-review-orchestration
- type: research
- 唯一证据文件：`evidence/research/spec-rq2-split-fidelity-20261022.md`（只写这一个文件）

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」——把这条从"代码改动是否对齐目标"
  延伸到"拆分后的子任务是否仍覆盖原任务的语义"）。
- 用户提出的问题：现在没有任何东西衡量「拆出去的卡合起来是否等于原来那张 review」。拆分可能偷走语义：
  漏一条断言、两条并一条、把 `closed` 降级成 `unverified`、把 `manual` 悄悄换成 `grep`、
  `struct` 父行与子行被切到不同单元、merge 表只是重写而不是搬运。
- 上游契约与语料（只读，不要改）：
  - `shared/dispatch-card.ts:535` `CLAIM_TYPES`、`:724` `parseClaimsBlock`、`:985` `claimsGaps`、`:1042` `claimBudgetCaps`；
  - `worker/output-sections.ts:374` `parseVerdictTable`、`:625` `claimCoverage`（12 个 gap token 的现有词汇）；
  - `worker/worker-mode.ts:1034` `claimSettlementGaps`（②③⑥ 三个实测出来的判据）；
  - 语料：`claim-driven-review/evidence/research/spec-rq3-claim-taxonomy-20261020.md`（104 个判定单元的实证分类）。

## 要求

1. **拆分的语义损失面清单**：至少覆盖
   (a) claim 集合：漏 / 重 / 新增（scope creep）；
   (b) 单条要素：`类型/陈述/反证条件/定位/判据/预算` 六列被改写（逐字 vs 归一化后比较，给出归一化规则）；
   (c) 结构：`struct` 父行与其 `C-01.3` 子行不得跨单元；同一 claim 的多条 `定位` 不得拆到两个单元;
   (d) 裁决的搬运：merge 行只能是子单元行的搬运（裁决/判定/证据/取数/原因逐字），或显式 `re-judged` + `carried-from:`;
   (e) 层级降级：`closed → unverified`、`成立 → 无法判定`、类型替换，哪些是合法（子单元确实没预算）哪些是偷语义。
2. **每条损失面给一个可机检判据**：`token 名 / 触发条件 / 负例（构造一份会被判出的产物） / 零成本（纯文本，无 LLM）`，
   并说明挂在哪一侧（母卡派发期 = PM 侧；merge 结算期 = worker 侧）。
3. **与已交付判据的关系**：说明哪些能用现有 `claimCoverage` / `claimSettlementGaps` 直接表达（复用），
   哪些必须新增（新增的必须在 token 命名上与现有 12 个 gap token 不冲突，给出命名方案）。
4. **实证校准**：拿 `spec-rq3-claim-taxonomy` 的 104 个判定单元语料做算术——按 5 条/单元切分，有多少单元含 `struct` 父子对、
   多少条 `manual` 会被凑到同一个单元、`Σ预算` 会怎样分布；指出「统一 5 条/单元」这条规则在什么形状的卡上必然出错。
5. **反恒真**：对你提出的每条判据，说明「拿一份诚实产出跑不会误报」的证据形态（不是承诺，是给出构造方式）。

## 交付格式

`evidence/research/spec-rq2-split-fidelity-20261022.md`：
① 结论表（损失面 → 判据 token → 挂哪侧 → 复用/新增）；
② 判据细则（每条含负例构造）；
③ 104 单元语料的算术表；
④ `## 未覆盖面`。

## 写入允许面

- `.agenticdoc/claim-driven-review-orchestration/evidence/research/spec-rq2-split-fidelity-20261022.md`

## 写入禁止面

- 任何 `packages/**` 源码、`claim-driven-review/**`、其他 key、`dist/**`

## 验收命令

无（research 只读）；每条判据必须配可构造的负例，否则视为未完成。
