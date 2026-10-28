# claim-driven-review-orchestration —— 断言驱动审查的编排层与拆分保真度

- Key: claim-driven-review-orchestration
- 上游 key：`claim-driven-review`（EXECUTE→VERIFY 已完成，四层交付 + 端到端 `exit=0`）
- 相位：SPEC（research 在跑，本文的 AC 在 research 回读后修订）

## §0 Goal Alignment

- 目标锚点：`.agenticdoc/goal.md` ——「一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目，
  解决单 Agent 长上下文溢出和无法并行的问题」；上游 `claim-driven-review/achieved.md` 已给出实测基线：
  真实 review 工具调用中位 **52**（max 98）、上下文中位 **110,666**（峰值 253,273），断言卡降到 **16 / 35,782**。
- 本 key 对齐的是**并行审查**这一支，且以真实 review 为输入（不是合成卡）：
  一个真实 review（散文 brief 或 findings 清单）能自动转成可机检的覆盖清单 → 拆成取证单元 → 汇合后仍是原来那次审查。
- 预期收益：
  1. 单次审查的墙钟从"一条长链"变成"⌈n/5⌉ 条并行短链"，每单元独立超时/独立失败，不互相拖死；
  2. `tokens_per_closed_claim` 在两个拆法之间可比，让"要不要拆"从信念变成数字；
  3. 拆分的语义损失变成可机检的 gap，而不是靠人读 merge 报告相信它没漏。

## §1 背景与现状（实测）

上游已交付并验证（`claim-driven-review/evidence/t07-e2e-results-20261022.md`）：

| 层 | 状态 |
|---|---|
| L1 契约（claims 块解析/判据集/预算推导） | 已交付，`shared/dispatch-card.ts:724/985/1042` |
| L2 派发（read_scope + caps + 回执行） | 已交付，`pm/ui-bridge.ts:2834/2965`；Python 镜像 `dispatch.py:654/711/735` |
| L3 结算（七列表 + 覆盖判据 + 终态折叠） | 已交付，`worker/worker-mode.ts:1034`、`output-sections.ts:625` |
| L4 度量（`[CLAIMS]` + `run.json.claims` + `n/a` 降级） | 已交付，`usage.py:1007` |
| 端到端 | 5 claims → `exit=0`，13 次放行取数，`closed=5 / unverified=0` |

未达成（上游 `verify.md` 明确列出）：

- **AC-004 编排**：`triage → 扇出 → merge` 不存在，`claims > 5` 不拒也不拆。
  今天一张 20-claim 卡会被照派，`fileCap = min(30, 6×20) = 30` → 每条 1.5 次取数，必然大面积
  `unverified: budget`。这是本 key 要修的主线。
- **AC-005(a) 并排比较**：无法比较，因为不存在第二种拆法。
- **AC-006 灰度基线**：advisory 零拒绝已验，但"前后退出码分布不变"没有对照样本。
- **用户新增要求**：没有任何东西衡量「拆出去的子卡合起来是否还等于原来那张 review」。

## §2 范围

**做**：拆分门禁与扇出、merge 单元的语义、拆分保真度判据、两种拆法的度量对照、灰度基线取证。

**不做**：改动 L1/L3 已交付的判据语义（只在必要时**新增** token，不改既有 12 个 gap token 的含义）；
不引入中心化调度器（协调只走文件，`goal.md` GC-5）；不改任何角色的工具集（GC-2）。

## §2.0 拆分的前提：覆盖清单（claims 是导出物，不是手写物）

**问题**：真实 review 的卡是散文（「审一下 X 模块有没有 Y 类问题」），没有 claims 块。
若拆分要求「先有断言块」，则真实 review 永远拆不了——功能空转。

**回答**：拆分的前提不是「断言块」，而是**一份可机检的覆盖清单**；断言块只是这份清单的落地格式。
因此本 key 增加 **阶段 0（提取）**：把真实 brief 变成清单，再做扇出。

| 路径 | 输入 | 谁做 | 成本 | 适用 |
|---|---|---|---|---|
| **E1 结构化提取**（零 LLM） | QG findings 列表 / spec AC 行 / diff hunk / 反模式 grep 命中 | 确定性代码 | ≈0 | 已有清单来源的 review |
| **E2 triage 单元提取** | 散文 brief + 变更面索引（diff stat / 符号表），**不读全仓** | 一个受限 research 单元（只读，预算 ≤12 次读） | 一个单元的固定开销 | 真实散文卡（主路径） |
| **E3 范围切保底** | 文件/模块清单 | PM | ≈0 | 完全无法断言化（「看看有没有问题」） |

E3 **不算「达成拆分」**：必须标 `fidelity=unverifiable`，每单元交付「覆盖了哪些面 / 没覆盖哪些」，
merge 只合并清单、不逐字搬运、不做逐字对账。

**阶段 0 计入预算**（AC-E5）：否则「拆卡省钱」是假的。

### 三层保真（把闸门放在最前面）

- **L0 brief → claims**：brief 的每个要求项要么映射到 ≥1 个 claim id，要么显式声明「不可断言化 + 原因」。
  真实 review 的真正闸门在这一层；L1/L2 只在 L0 成立后才有意义。
- **L1 claims → units**：AC-004…AC-007（集合 / 要素 / 结构 / 搬运边界）。
- **L2 units → merge**：AC-008（裁决搬运对账）。

### E（清单怎么来）与 L（守恒什么）是两条轴

| | **L0** brief → 清单 | **L1** 清单 → 单元 | **L2** 单元 → merge |
|---|---|---|---|
| **E1 结构化** | 源行 ↔ claim 双向计数（`extract:lost-source-row` / `extract:foreign-locator`） | 完整适用 | 完整适用 |
| **E2 散文提取** | asks（**确定性抽取**）↔ claims（LLM 产出）→ `extract:unmapped-ask` | 完整适用 | 完整适用 |
| **E3 范围切** | 退化：要求项 → 文件组（弱） | **空**（无 claim 可守恒）→ `fidelity=unverifiable` | 退化：只合并覆盖面清单 |

**L0 的左侧不得由 LLM 抽取**，否则 L0 退化为 LLM 自证（提取单元抽的 asks 与它自己抽的 claims 互证，两边都漏的那部分永远不报）。
确定性规则：brief 的列表项、`要/需/检查/确认/覆盖/是否/不得/至少` 祈使句、显式路径引用。

### 变更面与 claim 的两类来源

| 类 | 内容 | 来源 | 覆盖率可否机算 |
|---|---|---|---|
| **A 变更对账** | 每个 hunk 是否被断言覆盖（改了什么 / 与声明一致吗 / 测试与调用点跟上吗） | E1 从 diff 机械生成（`path:a-b` 定位免费、幂等） | **可**：被覆盖变更行 / 总变更行 |
| **B 缺陷发现** | 「这里有并发问题吗」「这个错误分支漏了吗」 | 只能 E2（读逻辑）或人工 | 不可，靠 L0 映射声明 |

E1 与 E3 的区别：E1 切的是**清单**（每条带 hunk 边界，可守恒），E3 切的是**代码**（无条目，不可守恒）。

## §3 验收标准（AC）

### 阶段 0：提取（真实 review 能否拆卡的关键）

- **AC-E1 结构化提取（零 LLM）**：从 QG findings / spec AC 行 / **diff hunk** / 反模式命中生成 claims，
  每条带 `定位` + 机检 `判据` + `预算`；产出必须过 `claimsGaps` 的**其余**结构规则。
  **反证条件口径**（T-03 实测的契约冲突）：`antiPatternHits` / `diffHunks` 可派生**具体**反证条件
  （`在 path:line 处找不到 <pattern>` / `该 hunk 未体现陈述的改动`）；`findings` / `acRows` / 任何 `manual`
  不得派生，缺则保留 claim 并每条计 `extract:falsifier-missing:<id>`，在 L0 与 plan 回执行里显示。
  **禁止**为迁就 E1 放宽 `claimsGaps`（反证条件是「可证伪断言」的核心）。
  同一输入两次提取结果稳定（幂等）。
  源侧对账：每条源行至少映射到 1 条 claim（`extract:lost-source-row`），claim 的 `定位` 必须在源集合内
  （`extract:foreign-locator`）。变更面生成的只算 **A 类（变更对账）**，必须与 B 类分开记账，
  A 类覆盖率 = 被覆盖变更行 / 总变更行（可精确计算，`extract:thin` 用同一分子分母）。
- **AC-E2 散文 brief 提取**：一个受限 triage 单元（只读，≤12 次读、≤10 分钟）读「brief + 变更面索引」，
  产出 claims 块。产出不过 `claimsGaps` → 重提一次（同预算）→ 仍不过则降级 E3 并在接单里记 `extract:degraded`。
  **它不得直接开始审查**（只提清单，不判定）。
- **AC-E3 范围切保底**：按文件/模块切时，卡上必须写 `fidelity=unverifiable`，每单元交付覆盖面清单，
  merge 只合并清单。不得把 E3 产物当成「已验证拆分」报成达成。
- **AC-E4 L0 保真**：brief 的要求项 ↔ claim id 双向映射；有要求项没映射且未声明原因 → `extract:unmapped-ask`；
  claims 密度过低（变更面过大而断言过少）→ `extract:thin:<lines-per-claim>`。
- **AC-E5 阶段 0 计费**：triage/提取单元的 token与调用计入对照臂的 `Σtokens`，不得当免费前置。

### L1/L2 与度量

### 拆分门禁与扇出

- **AC-001 拆分信号**：`claims > 5` 的卡在派发期被识别为「需拆分」。落点：`claimsGaps`（`dispatch-card.ts:985`）的 advisory 数组，
  新增独立 token `claims:count:<n>>5`，**不与** `claims:budget-sum` 同轴（RQ-1 §3）。`n>5` 正是 `fileCap/n < 6` 的第一个整数。
  advisory 模式进 warnings 照派，enforce 模式拒绝且零副作用（无 taskDir / 无 task.md / 无队列行）。
  注意：加这条之后 `budget-sum>40` 作为「拆分信号」变冗余（只余卡形 lint 作用），不得两条并列当拆分依据。
- **AC-002 扇出**：一个逻辑审查任务拆成 `K` 个取证单元 + 1 个 merge 单元；**单元 = claim 簇的装箱**，不是 id 的定宽切片。
  约束（RQ-2 §4.6）：(a) 簇原子性 —— `struct` 父行 + 全部子行 + 该 claim 的全部 `定位` 必须同一单元；
  (b) `Σ预算`（manual=2）≤ 8；(c) 每单元 ≥ 1 条 `cmd/grep/struct`；
  (d) `K = ⌈Σ槽/5⌉` 只作**下界**，实际 K 由装箱结果决定。每个取证单元一张子卡
  （自带 claims 块 + 自己的 `read_scope`/caps）；task_key 可从母卡机械还原（`<task>-u<k>` / `<task>-merge`）；
  **手工 `dispatch_worker` 与 conductor 两条通道产出字节级同构的子卡**。
- **AC-002a 汇合与串行守卫（RQ-1 实测的两个硬约束）**：
  ① **手工通道没有 join**（`pm/ui-bridge.ts:3086`；`_workers.acked` 是已消费侧车、`_workers.stale.parallel` 是回收，都不是 join），
  而 conductor 的 `deps:` → `frontier` → `done_stems` 已是可复用的 join（`task_graph.py:595`、`conductor.py:2010-2055`）；
  ② **同 key serial-only 守卫会吃掉并行**：子卡未声明 `write_face:` 时，`writeFaceVerdict → undeclared` 会拒掉同 key 的第 2 个派发
  （`task-dispatcher.ts:447-459`，已实测 `write-face-pm-gate.test.ts:422-435`），5 个子卡退化为串行。
  因此：每张子卡必须声明**互不重叠**的 `write_face`；且 writeless 角色的**运行时不看 `write_face`**
  （`worker-mode.ts:3422` 仅在 `roleClass === "writable"` 时解析），仍按 own taskDir + `<key>/evidence/**` 放行 ⇒
  子单元的产出必须落在**各自 taskDir**，不得共用 `<key>/evidence/**`，否则门禁放的并行会在运行时撞同一批文件。
- **AC-002b 拆分清单（manifest）**：派发期生成一份机器可读的拆分计划（母卡 id → 单元），
  merge 的「母卡 id 集」**必须取自 manifest，不得由 merge 自己重建**（RQ-2 §0.6：否则母卡漂移无法发现）。
  manifest 与子卡不一致 → `split:manifest:<detail>`；单元无法满足装箱约束 → `split:unit-infeasible:<k>:<rule>`。
  manifest 必须记母卡 `card_sha256` 与各子卡 sha（今天子/母卡 **sha 无链**，RQ-1 §6.3）；
  母卡不得继续留在 `tasks/` 可被当单元派发（需一个 `split_plan:` 标记或移入子目录）。
- **AC-003 merge 单元语义**：merge 单元的 `read_scope` **只放** `workers/<task>-u*/report.md`（文件级条目，**无 glob，必须逐文件枚举**，
  `read-scope.ts:89` `isSameOrUnder`），并额外的放自己的 `task.md`，`l2_read_file_cap ≥ k+2`（RQ-1 §4.2）；
  `worker_file` 只能写自己 taskDir，天然不改写兄弟 report。它不改代码、不重判断言；其产出是母卡 claim 数的**全量汇总表**；
  终态另记一条机器行 `[SPLIT] <iso> parent=<task> units=<k> claims=<n> fidelity=<ok|gaps>`。

### 拆分保真度（用户新增）

- **AC-004 claim 集合守恒**：`∪子卡 claim id ≡ 母卡 claim id`，且两两不相交。
  漏（`split:missing:<id>`）、重（`split:duplicate:<id>`）、新增（`split:extra:<id>`）三种各一条负例。
- **AC-005 要素守恒**：六要素（`类型/陈述/反证条件/定位/判据/预算`）在子卡中归一化后**逐字不变**
  （归一化只允许去 tick、折叠空白、统一全角半角；不允许同义改写）。
  任一列漂移 → `split:mutated:<id>:<field>`，带母卡原文与子卡现值。
- **AC-006 结构守恒**：`struct` 父行与其 `C-01.x` 子行必须在同一单元；同一 claim 的多条 `定位` 不得跨单元
  → `split:orphan-child:<id>`、`split:split-locator:<id>`。
- **AC-007 派生根 cap 记账（不是 gap）**：`Σ预算` 守恒是**恒等式**（只由行类型与行数决定，而这两者已被 AC-004/AC-005 钉死），
  不作为判据（RQ-2 §2.8 已证）。真实损失面是**派生根 cap 膨胀**：11 张卡 `Σ min(30,6n) = 330` → 切 28 单元后 `Σ = 624`（1.89×），
  `calls/claim` 由 3.17 变 6.00。这是 D-014 的设计意图，因此记一条审计行 `split:cap-inflation:<ratio>` 供 AC-010 定价，**不得拦截**。
- **AC-008 裁决搬运**：merge 表的每一行必须是某子单元裁决行的**搬运**——`裁决/判定/证据/取数/原因`逐字一致；
  若重判必须显式 `re-judged` + `carried-from: <path:line>`。核心不变量：**merge 不得是裁决第一次改变的地方**
  （`verdict_first_seen_at == unit`）——同一 claim id 只落一个单元，merge 没有聚合自由度，只能搬运；
  合法的「预算耗尽」必须已在子单元裁决里写成 `unverified(budget)`。
  改写 → `merge:rewritten:<id>:<field-list>`；升/降级 → `merge:upgraded|downgraded:<id>`。
- **AC-008b merge 模式的既有判据豁免（算术不再重申）**：`claimCoverage` 的 12 个 token 中 11 个可直接复用，
  **必须豁免** `claims:fetches:<sum>><cap>` 与 `claims:fetches:<sum>>trace:<n>` —— 20 claim 拆 4×5 时
  `Σ取数 52 > cap 30 > trace 4`，二者都必然误报（RQ-2 §3.2）。
  `claim:<id>:self-evidence` 不动，靠**列级约定**消除误报：子报告路径只准写进 `原因` 列的 `carried-from:`，
  证据列只放搬运过来的原始 ref。
- **AC-009 反恒真**：AC-004…008 每条判据至少一条负例（构造"拆得干净但偷了语义"的产物，断言被拦），
  并给出诚实产出不误报的证据（用 T-07 三份真实 report 回放）。

### 度量与灰度

- **AC-010 两种拆法可比**：同一张 20-claim 卡跑 `1×20` 与 `4×5`，报表能并排给出 `tokens_per_closed_claim`。
  **分母口径（已定，RQ-3 §3.3）**：分子 = arm 内全部 attempt 的 `Σtokens`（含 merge）；
  分母 = **仅取证单元**的 `Σclosed`，**按 claim id 去重**（从各单元 `## 断言裁决` 表取 id，不依赖 `[CLAIMS]` 行——它不含 id）；
  merge 单元 `tokens` 单列 `merge_tokens`、`closed` 不进分母；同时报告敏感性口径
  `incl_merge = (Σevidence + merge) / Σclosed_dedup`，两者差值即编排开销占比。
  必须记录 `dup_closed = Σevidence closed − closed_dedup`，非 0 即扇出边界没切干净（并入 AC-004 的 `split:duplicate`）。
- **AC-010b 两臂预算对称**（**新发现，必须定**）：今天两臂读预算不对称——`1×20` 得 `min(30,120)=30`（1.5 次/claim），
  `4×5` 每单元各得 30（合计 120，6 次/claim），**差 4 倍**；直接比等于拿「预算多 4 倍的臂」去比。
  两臂必须同口径：或按母卡总量封顶（`Σ子卡 fileCap ≤ 母卡 fileCap`）、或显式报告 `fileCap_total` 与 `fetches/claim` 并声明不对称。
- **AC-010c claims 入台账**（**前置工程，比 token 归因小得多**）：`tokens_per_closed_claim` 恒 `n/a` 的真因不是 token 取不到
  （launcher spawn 的 run **485/486 = 99.79%** 可 join），而是 **launcher 的 `end` 事件不写 `claims`**
  （`launcher.py:320` 键集 `{event,exit,reconciled,run_id,status,ts,wall_s}`，`usage.py:1021` 读不到）。
  验收：`mw stats --key <k>` 的 claims 列非 0；`usage.py` 另需 **arm 级聚合**（`Σtokens/Σclosed_dedup`），现在只有 per-run。
- **AC-011 灰度基线（降级为“有功效声明”的看门狗）**：advisory 前后既有 review run 的完成率/退出码对照。
  已测（RQ-3 §5）：全库 `run.json` **409** 条，带 `mw-claims` 块 **8**（全在本项目上两个 key）vs 不带 **401**；
  review 子集 **6 vs 49**，完成率 `0.333`(n=3) vs `0.809`(n=47)，Fisher `p=0.283`——**说明不了任何事**。
  因此 AC-011 不写成“证明不变”，而写成：①附上述样本量与功效上限（n=47 只能排除 ≥27pp 的回归；
  检出 10pp 需 ≈295 attempt/臂，≈59 天/臂）；②超时**不可用 exit 码区分**（超时 = `exit=1` + trace `[TIMEOUT]`，
  无 124），统计必须按 trace 标记分类，否则“exit 分布”从一开始就是错的分类轴。

### 零回归

- **AC-S1 开关**：三档 `off`（默认）/ `plan` / `on`，名称带 `review`（`MW_REVIEW_SPLIT` / `REVIEW_SPLIT_DEFAULT`），
  TS 与 Python 同名同义，平价锁；优先级 env > `.mw/review-split.json` > 默认；
  `mw review-split status` 回显生效值 + 来源；`off` 下卡派发与产出与 HEAD 逐字节相同、零残留。
- **AC-S1b 命令开关**：`mw review-split set off|plan|on` 可持久化切换；`status` 纯只读（不写任何文件）；
  开关只对 `type: review` + 带清单的卡生效，其他类型记 `split:not-review:<type>` 并走原路径。
- **AC-S2 plan 档可判**：`plan` 必须产出 manifest 与回执行（单元数 / 每单元 id / `Σ预算` / cap 膨胀比 / 纸面对账），
  **不派发任何子卡**且零队列行。
- **AC-S3 预先定义的终止条件**：§5.2 四条判据写成可计算的报表行；不满足时保持 `off` 并留 negative-result 证据。
- **AC-012**：不带 claims 块的卡路径逐字节不变；既有 8 套 claims 测试（159 例）与 Python 27 例全绿；
  `l2_read_file_cap=8 / l2_read_byte_cap=65536` 旧默认值不动；`npm run check` 只余已知 5 条基线诊断。

## §4 风险与待决

- **风险（E2 提取偷走审查深度）**：triage 单元只读索引不读代码，可能提出一批「好判但无意义」的断言。
  缓解：AC-E4 的 `extract:thin` + E2 必须交「我抽不出的要求项」清单 + merge 单元回读 brief 复核 L0。
- **风险（E3 静默降级）**：范围切达不到「保真」，最容易被当成达成。
  缓解：`fidelity=unverifiable` 必须上卡且进 `[SPLIT]` 行，统计上单独一档。

- **风险（拆分成本倒挂）**：5 个小单元的固定开销（每单元一次启动 + 一次 goal/卡读取）可能吃掉并行收益；
  RQ-2 §4.6 实测：11 张卡按 5 条硬切得 28 单元（17 满 / 11 欠 / 6 单条），固定开销 ×2.5，尾槽不省预算。
  缓解：AC-010 就是要测这个；不测就不拆。
- **已澄清（原「待决 1」）**：单元宽度「5 条」不是语义常数，是 `callCap/perClaim = 30/6` 的预算悬崖；
  55.2% 的 `struct` 单元 N≥5，定宽切片必然拆散父子。改用 AC-002 的簇装箱。
- **风险（保真度判据误伤）**：上游 `carried-from` 的 mtime 判据精度 0%，教训是"判据必须能在真实产出上不误报"。
  缓解：AC-009 要求每条判据带诚实产出回放。
- **新发现（不属本 key 但必须记）**：`mw.py stats --detail --json` 在显式 `--json` 下仍会往
  `~/.mw/usage/reports/` 写 HTML（`mw.py:10381`）——只读命令带写副作用，与 GC-3 同类。建议单独立一条小修。
- **待决 1**：merge 单元是否自带 claims 块（决定它有没有 `[CLAIMS]` 行、是否进 `tokens_per_closed_claim` 分母）。
- **待决 2**：拆分是 PM 自动执行还是先给用户确认（自动 = 一次派发变 k+1 次，成本可见度变化大）。
- **待决 3**：`token 归因` 已澄清——不是"能不能 join"的问题（99.79% 可 join），而是 `launcher.end` 不写 `claims`
  与缺 arm 级聚合。待定的是：这条 wiring 修是否收进本 key（我建议收，它是 AC-010 的前置且改动面小），
  还是另开一条最小修复卡。

## §5 开关、灰度与预先定义的终止条件

**理由**：拆分这条路是否成立目前没有证据（样本 0）。功能在验证前**不得改变默认行为**——
否则一旦路径不成立，关掉它又要改一轮。因此拆分本身带开关，且默认关闭。

### 5.0 命名与开关方式（review 专用）

这个开关**只控制 review worker 的断言扇出**，不是全局调度开关，名字里必须带 `review`：

| 面 | 名字 |
|---|---|
| 环境变量 | **`MW_REVIEW_SPLIT`** = `off|plan|on` |
| 常量 | `REVIEW_SPLIT_DEFAULT = "off"`（`shared/review-split.ts`） |
| 持久化配置 | `.mw/review-split.json`（`{"v":1,"mode":"...","updated":"..."}`） |
| 命令行 | **`mw review-split status`** / **`mw review-split set off|plan|on`** |
| 回执行 | `[review-split] mode=<m> units=<k> claims=<n> …` |
| manifest | `evidence/split/review-<task>-manifest.json` |

优先级：`MW_REVIEW_SPLIT` > `.mw/review-split.json` > 默认 `off`；`mw review-split status` 必须回显**生效值 + 来源**（env/config/default）。

生效范围：**只对 `type: review` 且带可机检清单的卡**生效。其他类型的卡即使开关为 `on` 也走原路径，
并记一行 `split:not-review:<type>` 说明为什么没拆（不得静默）。

### 5.1 三档开关（默认 `off`）

| 档 | 行为 | 派发子卡 | 产物 |
|---|---|---|---|
| **off**（默认） | 不提取、不拆、不写 manifest；卡按今天路径派发，输出逐字节不变 | 否 | 无 |
| **plan** | 跑 E1/E3 提取 + 装箱，产出 manifest 与回执行（单元数、每单元 id、`Σ预算`、cap 膨胀比、L0/L1 纸面对账结论） | **否** | `evidence/split/<task>-manifest.json` + 回执行 |
| **on** | 提取 + 派发子卡 + merge | 是 | manifest + 子卡 + merge 表 |

- 读取点：`shared/review-split.ts` 的 `REVIEW_SPLIT_DEFAULT` + `MW_REVIEW_SPLIT` + `.mw/review-split.json`；
  Python 侧同名同义；平价锁盯住（同 `CLAIM_GATE_DEFAULT` 的做法，D-006）。
- `mw review-split set` 只写 `.mw/review-split.json`（原子写），不碰队列与 task.md；
  `mw review-split status` 只读，不得产生任何写入（含 HTML 报表）。
- 记录：task.md 头 `claim_split: off|plan|on`；`[SPLIT]` 行带 `mode=`；`run.json.split_mode`。
- **off 必须零残留**：无 manifest、无子卡目录、无队列行。（GC-3）

### 5.2 关机不等于免费：先定“什么算 ok”

用一次 pilot 的 A/B（`1×n` vs `k` 单元，n ≥ 15）判，四条全过才算拆分成：

1. **保真**：L0 + L1 的 gap 均为 0（`extract:unmapped-ask`、`split:*` 全空）；
2. **成本**：每关掉一条断言的 token（无真值时退为 `fetches/closed`）≤ 单卡的 **1.2×**；
3. **墙钟**：≤ 单卡的 **0.7×**；
4. **上下文**：子单元峰值上下文 ≤ 单卡的 **60%**（这是本功能的存在理由）。

任一不满足 → **保持 `off`**，写 negative-result 证据，两周内不重复同一实验（防抖）。
四条全过且用户签字后，才允许把默认改成 `plan`；`on` 仍需显式环境变量。

> 这条直接来自 upstream AC-006 的教训：样本不足时不得声称达成（`p=0.283`）。

## §6 记忆前馈

- 拆分保真度判据是「目标一致性追踪」的一个新实例：母卡是目标，子卡是执行体，merge 是回执。
  这套「母→子→回执」的判据形态可以复用到任何 fanout（coding 卡拆模块、research 卡拆 RQ）。
- 反恒真纪律：每条新判据必须先在真实语料上跑出"不误报"，再上闸门（`carried-from` 的 0% 精度是反例）。

## §7 可复用资产

| 资产 | 位置 | 怎么用 |
|---|---|---|
| claims 契约全套 | `shared/dispatch-card.ts:724/985/1042` | 直接复用，不重写解析与判据 |
| 灰度开关形态 | `claimGateMode()` / `claim_gate()`（D-006） | `splitMode()` 照抄：常量 + env + 平价锁 |
| 读面推导 | `pm/ui-bridge.ts:2352` `claimReadScope` | 子卡 `read_scope` 同构生成 |
| 结算判据 | `output-sections.ts:625`、`worker-mode.ts:1034` | merge 复用 11 个 token，2 个显式豁免 |
| 汇合机制 | `task_graph.py:595`、`conductor.py:2010-2055` | conductor 通道用 `deps:`；手工通道用 manifest 门禁 |
| 并行守卫 | `shared/write-face.ts` + `task-dispatcher.ts:447-459` | 用逐单元 `write_face` 声明解开串行 |
| 任务卡渲染 | `pm/ui-bridge.ts:2957` `writeDispatchTaskMd` | 子卡与母卡同一渲染链 |
| 度量降级 | `usage.py:1007` `claims_metrics` | `n/a` + `attributable=false` 保留 |
| 归因口径脚本 | `.mw/runs/probe-goal-benefit.py` | arm 级报表复用其 join 逻辑 |

## §8 需规避坑点

| 坑 | 出处 | 规避 |
|---|---|---|
| schema 过严导致连续误拒、30 分钟零产出 | P-048 | 产出解析宽容（全半角、别名列、全角分隔符） |
| 判据恒真（无不判别力） | RQ-2 §2.8：`Σ预算` 守恒 | 上闸门前先做"能不能构造反例"自检 |
| 判据精度 0% | T-07：`carried-from` mtime 版全部误报 | 新判据先在真实产物上回放 |
| 复用既有 token 自带假阳性 | RQ-2 §3.2：merge 模式下 `fetches><cap` / `>trace` | 显式豁免，不改判据值 |
| 并行被 serial-only 守卫吃掉 | `task-dispatcher.ts:447-459` | 子卡必须声明不重叠 `write_face` |
| writeless 运行时不看 `write_face` | `worker-mode.ts:3422` | 产出落各自 taskDir，不共用 `evidence/**` |
| 子/母卡 sha 无链 | RQ-1 §6.3 | manifest 内录三段 sha |
| `task_graph` 命名 ambiguous | RQ-1 §6.5（`<task>-u1`/`-u2` 共享数字核心） | 子卡命名避开与母卡共享的数字核心 |
| `mw build` 只重建不安装 | T-07 实验（两次 reload 无效） | 验证新代码必须 `mw build --install` |
| 超时不可用 exit 码判 | RQ-3 §7：`exit=1` + `[TIMEOUT]`，无 124 | 统计一律按 trace 标记分类 |
| 台账 `end` 不写 `claims` | `launcher.py:320` | AC-010c 显式修，否则指标恒 `n/a` |
| 只读命令带写副作用 | `mw.py:10381`（`--json` 仍写 HTML） | 立小修；脚本避免 `--detail` |
| 基线口径混用 | `claim-driven-review/achieved.md` §4（“159”） | 所有数字必须标口径与分毘 |
| Windows 无 `grep`/`sed`；长脚本易断 | 会话实录 | 搜索用 python；多行脚本落盘再跑 |
