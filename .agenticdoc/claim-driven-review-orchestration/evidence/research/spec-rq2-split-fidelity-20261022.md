# RQ-2 拆分保真度（split fidelity）——「子卡合起来还是原来那张 review」的机检判据

- Key: `claim-driven-review-orchestration` · 卡: `tasks/RQ-2-split-fidelity.md` · 角色: research（只读仓库，唯一证据文件即本文件）
- 目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」→ 本文把它延伸到"拆分后的子任务是否仍覆盖原任务的语义"）
- 上游契约（只读，未改）：`shared/dispatch-card.ts:535/724/985/1042`、`worker/output-sections.ts:374/625`、`worker/worker-mode.ts:1034`（实为 `:1056`）、
  语料 `.agenticdoc/claim-driven-review/evidence/research/spec-rq3-claim-taxonomy-20261020.md`（104 个判定单元）
- 本文全部数字由本文 §4 的口径在 104 单元语料上算出（命令见 §7）；**没有任何判据被实现、被跑过**——这是纸面判据 + 语料算术，不是实测通过率（见 §6）。

## 0. 结论

1. **拆分损失面必须按"可搬运的实体"来判，不能按"文本相似度"来判**：唯一站得住的不变量是
   `子卡行的六要素 ≡ 母卡行（归一化后）` 与 `merge 行的五列 ≡ 某个子单元行（逐字）`。两条都是**恒等式**，不是启发式；
   启发式（相似度、同义词、mtime）在上游已有 0% 精度前科（`carried-from` 的 mtime 版，`t07-e2e-results-20261022.md` §缺陷 1）。
2. **`claimCoverage` 的 12 个 token 里 11 个可以直接复用到 merge 表，2 个必须豁免**：
   `claims:fetches:<sum>><cap>` 与 `claims:fetches:<sum>>trace:<n>` 在 merge 模式**必然误报**（算术见 §3.3：20 claim 拆 4×5，Σ取数 52 > cap 30，> trace 4）；
   `claim:<id>:self-evidence` 会把合法的"证据列里引子报告"误判为自证（`^report.*\.md$` 命中 `workers/<task>-u1/report.md`）——
   修法是列级约定（子报告路径只写进 `原因` 列的 `carried-from:`，证据列只放搬运过来的原始 ref），不改判据。
3. **AC-007 的 `Σ预算` 守恒是恒真的，`每单元 ≤ 40` 是死条款**：语料实测每单元 `Σ预算` 落在 **1..9**（均值 4.64），
   而 cap 是 40；`Σ预算` 只由 (行类型, 行数) 决定，而这两者已被 AC-004/AC-005 的 id 集合与类型列钉死 ⇒ `split:budget-drift` 无独立判别力。
   真正的预算损失面是**派生根 cap 的膨胀**：11 张卡 `Σ min(30,6n) = 330`，切成 28 个单元后 `Σ = 624`（**1.89×**），
   `calls/claim` 从 3.17 变 6.00。这是设计意图（D-014），所以它该被**记账**（AC-010 的输入），不该被当 gap 拦。
4. **「统一 5 条/单元」不是语义常数，是预算模型的悬崖**：`callCap/perClaim = 30/6 = 5`。唯一真实 5-claim 卡（T-07a，Σ预算 10）
   正是这个常数被标定的样本。它在四种形状上必然出错（§4.6）：`struct` 枚举 N≥5（29 个 struct 单元里 16 个，55.2%）、
   枚举源需运行时执行（5/29，17.2%）、`manual` 密度 >1/3（11 张卡里 5 张，45.5%）、21 行大表（REFV H1/H2，22 槽永远装不进 5 槽）。
   按 5 条硬切：104 claim → 28 单元（17 满 / 11 欠 / 6 单条）；若按 RQ-3 自己的建议把 struct 展开成父+子行（24 个已知 N 合计 219 个子行），
   则是 **338 个 id → 72 个单元**，其中 **20/29 个父被切散**（16 个因 N≥5 必然切散）。
5. **合法的"降级"不存在于 merge 层**：同一 claim id 只落在一个单元（AC-004 已定 id 井、互不相交），所以 merge 对一个 id 没有任何"聚合"自由度——
   它只能**搬运**。因此 `closed→unverified`、`成立→无法判定`、`grep→manual` 在 merge 层一律是改写，与方向无关；
   合法的"预算耗尽"必须**在子单元的裁决里已经写着** `unverified(budget)`，merge 逐字copy。
   一句话不变量：**merge 不得是裁决第一次改变的地方**（`verdict_first_seen_at == unit`）。
6. **拆分保真度只能在三个点上判，缺一个就有洞**：PM 派发期（计划态，零副作用）、merge 结算期（搬运对账）、PM 收敛期（`[SPLIT]` 审计行）。
   只做 merge 期：一个单元没派发出去 → 它的 id 不在 merge 表里，而 merge 的"母卡 id 集"若是 PM 生成物（manifest），
   就可能与母卡同步漂移；只做派发期：merge 重写无法发现。manifest + 双向集合 + 搬运逐字，三者互为闭包。
7. **判据命名必须开新前缀**：`split:`（母卡↔子卡映射，PM 侧）与 `merge:`（搬运，worker 侧），不复用也不新增 `claim:`/`claims:` token；
   唯一的例外是 AC-001 已定的 `claims:count:<n>>5`——它是**卡属性**（一张卡该不该拆），不是映射关系，留在 `claims:` 家族是对的（§3.4）。

## 1. 结论表（① 损失面 → 判据 token → 挂哪侧 → 复用/新增）

`侧`：**P** = 母卡派发期（PM，判"拆分计划/子卡文本"，零副作用）；**M** = merge 结算期（worker，判 merge 表 vs 子报告）；
**P3** = PM 收敛期（只写 `[SPLIT]` 审计行，不产生新判据）。

| # | 损失面 | 判据 token | 侧 | 复用/新增 | 档位 |
|---|---|---|---|---|---|
| S-01 | 扇出的单元没落盘 / 没被 manifest 承认 / 单元号撞车 | `split:manifest:<detail>`（`missing` \| `unit-missing:<k>` \| `unit-extra:<task_key>` \| `unit-duplicate:<k>` \| `digest:<a>/<b>`） | P | 新增 | structural |
| S-02 | claim 漏（母卡有、子卡并集无） | `split:missing:<id>` | P | 新增（spec AC-004 已定名） | structural |
| S-03 | claim 重（同一 id 进两个单元，或一个单元内出现两次） | `split:duplicate:<id>` | P | 新增（spec AC-004） | structural |
| S-04 | claim 新增（scope creep，子卡 id ∉ 母卡） | `split:extra:<id>` | P | 新增（spec AC-004） | structural |
| S-05 | 六要素被改写（类型/陈述/反证条件/定位/判据/预算） | `split:mutated:<id>:<field>` | P | 新增（spec AC-005） | structural（机械切片）／advisory（人工切片） |
| S-06 | `struct` 父行与其 `C-01.3` 子行跨单元 | `split:orphan-child:<id>` | P | 新增（spec AC-006） | structural |
| S-07 | 同一 claim 的多条定位被拆到两个单元（= 一条母卡 claim 被物化成 ≥2 个新 id） | `split:split-locator:<id>` | P | 新增（spec AC-006，**触发条件重新定义**，见 §2.7） | structural |
| S-08 | 派生根预算膨胀（`Σ预算` 不变，可花的取数变多） | `split:cap-inflation:<parent>:<pcap>-><sumcap>` | P3 | 新增（本 RQ） | **审计行**，不计 gap |
| S-09 | 切片造出一张必被 G1 拒的子卡（如 manual 密度越界） | `split:unit-infeasible:<k>:<rule>`（rule ∈ `manual-overflow` \| `budget-sum` \| `claim-gaps`） | P | 新增；detail 复用 G1 token 的 rule 名 | structural（enforce 期） |
| S-10 | `Σ预算` 漂移 | `split:budget-drift:<parent>-><sum>` | P | **spec 已定名，但判为冗余**（§2.10 给出恒真证明），建议只做诊断字段 | 诊断 |
| S-11 | 卡"该不该拆"的信号 | `claims:count:<n>>5` | P | 复用 AC-001 已定名（不新造 `split:count`） | advisory / enforce 两档 |
| M-01 | merge 表整体缺失 | `claims:missing-table` | M | **复用** | structural |
| M-02 | merge 表漏行 / 多行 | `claim:<id>:missing-row`、`claims:extra-row:<id>` | M | **复用**（不新增 spec 的 `merge:<id>:missing\|extra`） | structural |
| M-03 | 单行裁决合法性（闭集、映射、证据、原因、自证、struct、取数、同义反复） | `claim:<id>:{verdict,finding,verdict-finding,evidence,reason,self-evidence,struct-held,budget,tautology}` | M | **复用**（9 个） | 混合（见 §3.2） |
| M-04 | 搬运无凭证（复制却不写来源） | `claim:<id>:carried-from` | M | **复用**（把"沉默"变成"声明"） | structural |
| M-05 | 搬运被改写（五列不逐字） | `merge:rewritten:<id>:<field-list>` | M | 新增（spec `merge:rewritten:<id>` 的**超集**，前缀兼容） | structural |
| M-06 | 方向性升级（`unverified→closed`、`部分成立→成立`） | `merge:upgraded:<id>:<from>-><to>` | M | 新增 | structural |
| M-07 | 方向性降级（`closed→unverified`、`成立→无法判定`） | `merge:downgraded:<id>:<from>-><to>` | M | 新增 | structural |
| M-08 | 搬运指针无效（`carried-from:` 指向的不是该 id 的行 / 子报告里找不到该行） | `merge:carry:<id>:<detail>`（`no-marker` \| `bad-pointer:<path:line>` \| `unresolved` \| `ambiguous`） | M | 新增 | structural（`no-marker` advisory） |
| M-09 | 母卡级未结算占比 | `claims:unverified-ratio:<u>/<n>><limit>%` | M | **复用**（这才是它该待的地方：n = 母卡 id 数） | structural |
| M-10 | merge 模式的取数总量 | `claims:fetches:<sum>><cap>`、`claims:fetches:<sum>>trace:<n>` | M | **不可复用**：merge 模式必须豁免（§3.3） | — |
| M-11 | 显式重判（合法但必须留痕） | `merge:rejudged:<id>` | M | 新增（**审计行**，不计 gap） | 审计 |

合计：新增 12 个 `split:` 判据（含 2 个不计 gap 的审计行）、4 个 `merge:` 规则名、复用 12 个既有 token、豁免 2 个既有 token。

## 2. 判据细则（② 每条含负例构造）

### 2.0 三个前置定义（所有判据共用）

**(a) 判据的输入是"行"，不是"文档"。** 一切比较在 `parseClaimsBlock` / `parseVerdictTable` 的输出行上做
（`Claim`：`id/type/parent/statement/falsifier/locator/judgement/budget`；`VerdictRow`：`id/type/verdict/finding/evidence/fetches/reason`）。
理由：解析器已经把全角/反引号/列序/额外列/围栏吃掉，判据若在原文上做，就要把同一套容差写第二遍（P-048 的直接教训）。

**(b) 归一化 = 解析器自身的归一化闭包，不许再多一步。** 逐字比较前只允许：

```
N0  行提取：parseClaimsBlock / parseVerdictTable（列序自由、额外列忽略、围栏内不计）
N1  去 tick（`）、折叠全角→ASCII（０-９、：、｜、U+3000）、trim      —— 即 normalizeClaimText + stripClaimTicks
N2  内部空白 [\s]+ → " "，再 trim
N3  类型列 ASCII lower-case（解析器已 lower，此处只是显式化）
N4  预算列：整数比较（前导零无关；NaN 归 G1 的结构性 gap，不归本文判决）
N5  定位列：按 [;；] 切成 ref 列表，按**集合**比较（顺序无关，重复保留）；其余列按 N2 后的整串比较
```

**明确禁止**（每一条都是"扩等价类"= 偷语义）：同义词折叠、否定词剥离（那是 `isTautologicalClaim` 的用途，不是搬运判据）、
标点剥离（`，。、：`）、引号形态归一（`「」`↔`""`）、大小写折叠（类型列以外）、行号"就近匹配"（±N 行容差）。
禁用理由可机检：**归一化必须是 `parse∘render` 的不动点**——把解析出的 `Claim[]` 按原表重渲染再解析，每格 N0..N5 后必须相等。
这个往返测试就是归一化规则的验收方式（§5 L1），也是"为什么可以逐字而不误报"的唯一理由。

**(c) 硬前提：id 井。** AC-004 已定 `∪子卡 id ≡ 母卡 id` 且两两不相交，所以**没有 id 重编号**。
本文所有 `split:orphan-child` / `split:split-locator` 的形态都由这一条决定；若设计阶段改成"每单元 C-01..C-05 重新编号"，
S-06/S-07 全部失效，必须改用"id 映射表 + 反向可还原"的口径（本文 §6 已列）。

**(d) 挂载点与门控**（决定 AC-012 零回归）：

- P 侧新增一个叶子模块 `shared/split-fidelity.ts`（纯函数 `splitGaps(plan, opts)`，只依赖 `parseClaimsBlock`），
  被 `pm/ui-bridge.ts` 的 claims gate 处调用（与 `claimsGaps` 同一处，`:2851-2905`），
  并在 `packages/multi-workers/autopilot/dispatch.py::claim_gate` 做逐字镜像（`test_claim_parity.py` 现有平价锁扩展即可覆盖）。
  **判定对象是"拆分计划"**（母卡 claims + 每个单元的 id/行分配），在写任何文件之前 ⇒ 满足 AC-001 的"零副作用"。
  同一函数再对**已落盘子卡**跑一次，即为 AC-002 的"两条通道字节级同构"审计。
- M 侧新增 `splitFidelityGaps(opts)`，与 `claimSettlementGaps` 并列注册在同一个 settle 折叠点（`worker-mode.ts:4347` 附近的 `gaps.claimGaps` 合并处），
  **仅在 `task.md` 头部声明 `split-unit: merge` 时启用**；其它任何 run 返回 `[]`（逐字节零回归）。

### 2.1 S-01 `split:manifest:<detail>`

- **损失面**：AC-004 的并集是"对声明的子卡集合"求的。子卡集合本身错了（少派一个单元、多出一个孤儿卡、两个卡抢同一个单元号、卡被改过），
  并集检查就变成**恒真**——这是整个判据族的总开关，必须先判它。
- **触发**：
  - `missing`：任务被标记为拆分（`split-units: <K>` 头）但 merge 卡/manifest 段缺失，或 K 不可解析；
  - `unit-missing:<k>`：manifest 声明 K 个单元，盘上找不到 `split-unit: k/K` 的子卡；
  - `unit-extra:<task_key>`：`workers/<parent>-u*` 下的子卡，其单元号 ∉ 1..K 或 `split-from` 不等于母卡 key；
  - `unit-duplicate:<k>`：≥2 张子卡声明同一单元号；
  - `digest:<a>/<b>`：manifest 里记录的 `claims-digest`（母卡 claims 块的 sha256 前 8 位）≠ 母卡现值。
- **负例构造**：母卡 `split-units: 4`，盘上只有 `-u1/-u2/-u3` → `split:manifest:unit-missing:4`；
  另建 `workers/<parent>-u5/task.md`（`split-unit: 5/4`）→ `split:manifest:unit-extra:<parent>-u5`。
- **零成本**：目录名 glob + 两个 `^[ \t]*split-(unit|from|units)[ \t]*:` 头正则 + 一次 `sha256(claims 块文本)`。无 LLM。
- **不误报形态**：机械切片 4 单元、4 个子卡、4 个 manifest 条目 + 正确 digest → 0；母卡未标记拆分时整个 S-01 不执行（返回 `[]`）。

### 2.2 S-02/S-03/S-04 `split:missing|duplicate|extra:<id>`

- **损失面**：(a) 漏一条断言 / 两条并一条（id 重）/ 偷加一条断言（scope creep）。
- **触发**：`P = ids(母卡)`，`U = ⊎ ids(子卡_i)`（multiset）。
  - `split:missing:<id>` for `id ∈ P \ set(U)`；
  - `split:duplicate:<id>` for `count_U(id) > 1`（含同一子卡内重复——`parseClaimsBlock` 不过早去重，`claims[]` 保留重复行，可直接数）；
  - `split:extra:<id>` for `id ∈ set(U) \ P`。
- **负例构造**（母卡 = T-07a 的真实 5 条，Σ预算 10，`t07-e2e-results-20261022.md`）：
  - u1 写 C-01..C-04、u2 写 C-01..C-03（复制粘贴错）→ `split:missing:C-05` + `split:duplicate:C-01..C-03`；
  - u2 追加 `| C-09 | manual | 顺手复核一下整体质量 | ... |` → `split:extra:C-09`。
- **零成本**：两次 `parseClaimsBlock` + 集合差/计数。无 fs 内容读（计划态）、无 LLM。
- **不误报形态**：把 5 行按 2+3 逐字节搬进两张子卡 → 三个 token 全空；把同一组行按 3+2 再搬一次 → 仍全空（切法无关）。

### 2.3 S-05 `split:mutated:<id>:<field>`

- **损失面**：(b) 六要素任一列被改写。这是最容易被"善意整理"偷掉的损失面：把 `grep:` 判据改写成 `manual:` 一句"人工确认无误"，
  六要素仍非空、语法仍合法，`claimsGaps` 一条都不报。
- **触发**：对 `id ∈ P ∩ U`，逐列比较 `type/statement/falsifier/locator/judgement/budget`（N0..N5），任一不等 → 每个 field 一条。
  `<field>` 闭集 = 这 6 个列名，不增不减。
- **负例构造**（真实母卡行 vs 被"整理"的子卡行）：
  - 母：`| C-02 | grep | 门禁默认值是 advisory，enforce 只能靠环境变量 | 默认值不是 advisory 或默认就开了 enforce | dispatch-card.ts:560-570 | grep: CLAIM_GATE_DEFAULT = "advisory" | 2 |`
  - 子：同一 id，`陈述` 改为「门禁默认应为建议模式，enforce 需显式开启」，`判据` 改为 `manual: 人工确认默认值是 advisory` →
    `split:mutated:C-02:statement` + `split:mutated:C-02:judgement` + `split:mutated:C-02:type`（三列各自一条，不合并）。
  - 格式扰动负例（**必须不报**）：同一行改成 `| C-02 ｜ grep ｜ ... ｜ 2 ｜`（全角竖线）、`判据` 列加反引号、`预算` 写 `02`、
    `定位` 两条 ref 交换顺序 → 全部 0 条。
- **零成本**：两行文本 × 6 列 × N1..N5。无 LLM。
- **档位**：`split-origin: mechanical`（PM 机械切片）⇒ structural（差异就是 bug）；`split-origin: manual`（人写子卡）⇒ 先 advisory，
  避免把"允许的补充说明"变成拒绝（P-048：schema 过严曾造成 30 分钟连续误拒）。
- **不误报形态**：机械切片把 104 个单元的行逐字节搬进 28 个子卡 → 0 条；再做 §5 L1 的格式扰动（全角/反引号/空白/预算前导零/定位换序）→ 仍 0 条。

### 2.4 S-06 `split:orphan-child:<id>`

- **损失面**：(c) `struct` 父行与其 `C-01.3` 子行不得跨单元。父行的"结构完整性"判定（`shape: report.md :: [...] x 6`）
  只有在能读到全部子行裁决时才成立；父在一单元、子在另一单元，父要么被标 `unverified(not-found)`，要么被凭空标 `closed`（B-10）。
- **触发**：对每个 `id` 形如 `C-0X.Y`：`unit(id) ≠ unit(parent(id))` → 一条；`parent(id) ∈ U` 但 `parent` 行缺失 → 归 S-02/S-04（不重复报）。
- **负例构造**：母卡 `C-02`(struct) + `C-02.1..C-02.6`；切片按 id 计数第 5 个位置切：u1 = C-01,C-02,C-02.1,C-02.2,C-02.3；
  u2 = C-02.4,C-02.5,C-02.6 → `split:orphan-child:C-02.4`、`…:C-02.5`、`…:C-02.6`（三条，一条一个 id）。
- **零成本**：id 正则 `^(C-\d{2,3})\.(\d+)$` + 单元号映射表查表。
- **不误报形态**：`C-02` 与 6 个子行**同一张子卡**（哪怕该卡共 7 个 id，超过 5）→ 0 条。注意这条判据与"每单元 5 条"天然冲突（§4.6 形状 1）。

### 2.5 S-07 `split:split-locator:<id>`

- **损失面**：(c) 同一 claim 的多条 `定位` 不得拆到两个单元。**字面触发在 id 守恒契约下不可达**：
  行是原子的、id 不重编号、`定位` 是一格 ⇒ 同一 id 的两条 locator 不可能出现在两个单元（那会先命中 S-03 duplicate）。
  所以这条判据必须按**可达机制**重新定义，否则它是一条恒不触发的死判据（这正是本文要避免的"反恒真"反面）。
- **触发（重新定义）**：存在子卡行带 `split-from: <parent_id>` 且它的 id ≠ `<parent_id>`（即一条母卡 claim 被物化成 ≥2 个新 id），
  或 `parent_id` 出现在 ≥2 个不同 id 的 `split-from` 里 → `split:split-locator:<parent_id>`。
  语义：把一条断言拆成两条新断言，等于把"一个裁决"变成"两个裁决"，覆盖数与 `tokens_per_closed_claim` 全部失真；
  合法的行级展开通道是 `struct` 子行（`C-01.3`），不是新顶级 id。
- **负例构造**：母卡 `| C-03 | grep | ... | 定位: a.ts:1-20；b.ts:7 | ... |`
  子卡写 `| C-03a | grep | 前半段… | a.ts:1-20 | ... |` + `| C-03b | grep | 后半段… | b.ts:7 | ... |`
  （两行都带 `split-from: C-03`）→ `split:split-locator:C-03`（同时会命中 `split:extra:C-03a/C-03b` + `split:missing:C-03`；
  三条一起报是对的：它们描述的是同一个动作的三个面）。
- **零成本**：扫描行的 `split-from:` 单元格 + 分组计数。
- **不误报形态**：21 行大表走 `C-01.1..C-01.21` 的 struct 子行通道 → 0 条（子行是 parent 机制，不是新 id）。

### 2.6 S-08 `split:cap-inflation`：**不是 gap，是审计行**

- **损失面**：`fileCap = min(callCap, perClaim × n)`（`dispatch-card.ts:1042`）。`Σ预算` 守恒检查看不出这个：
  11 张卡单独派发时 `Σ fileCap = 330`（3.17 calls/claim），切成 28 个单元后 `Σ = 624`（6.00 calls/claim，**1.89×**）。
  即"拆分没有改变计划，但改变了可花的钱"。
- **为什么不判 gap**：这是 D-014 的**设计意图**（每 claim 6 次取数是标定值，30 的 callCap 才是限制器）。
  把它判成 gap 会在每一个诚实拆分上误报（反恒真的正例）。所以它只出现在 `[SPLIT]` 审计行里，作为 AC-010 对照实验的输入。
- **触发（审计）**：`pcap = min(30,6·n_parent)`，`sumcap = Σ_i min(30,6·n_i)`；两者不等即写一行 `cap=<pcap>-><sumcap>`。
- **负例构造 / 不误报形态**：同一对数字（330→624）在诚实拆分上也出现 ⇒ 它本就不该 silence；验收方式是"它在诚实样本上**出现**且 `fidelity` 仍为 `ok`"。

### 2.7 S-09 `split:unit-infeasible:<k>:<rule>`

- **损失面**：切片可能造出一张**过不了母卡同一道 G1** 的子卡。注意它和 S-05 的区别：S-05 说"内容被改了"，
  这条说"内容没改，但切法使得这一片在预算/密度上不可派发"——母卡能派、切片后不能派，是**拆分的可行性损失**。
- **触发**：对每个单元 i，用**同一套 G1 判据**（`claimsGaps`，`dispatch-card.ts:985`）判其 claims 子集：
  - `claims:manual-overflow`（`manual > min(4,⌈n/3⌉)`）→ `split:unit-infeasible:<i>:manual-overflow`；
  - `claims:budget-sum`（`>40`）→ `…:budget-sum`；
  - 任一 `claim:<id>:<element>` 结构性 gap → `…:claim-gaps`。
  detail 用**闭集 rule 名**（不是原 token 全文），避免 `split:…:claims:manual-overflow:3/5` 这种四段式。
- **负例构造**（本语料没有，必须构造——这是本文对"必然出错"的唯一诚实缺口）：
  14 条 claim 的卡，其中 3 条 manual 且**相邻**：整卡 manual=3 ≤ cap(14)=4 → 母卡通过；
  按 5 条切，第 1 片 = 那 3 条 manual + 2 条 grep → manual=3 > cap(5)=2 → `split:unit-infeasible:1:manual-overflow`。
  语料上的实际违例（W15/DESIGN/CODEREV/R-02/T18 共 4 个单元）全部属于**母卡已越界**的卡（5/11 = 45.5% 母卡自己就过不了 manual-overflow），
  所以语料只证明了"5 条切片不会修复密度问题"，没证明"它会新造问题"——机制可构造，语料未覆盖（已写入 §6）。
- **零成本**：单元内按类型计数 + 与 `min(4,⌈n/3⌉)` 比大小。
- **不误报形态**：母卡 5 条 0 manual → 任意切片 0 条；母卡 20 条 6 manual（cap 6）切 4×5，其中一片 2 manual（cap 2）→ 0 条。

### 2.8 S-10 `split:budget-drift`：判为**冗余**（恒真证明）

- 命题：若 S-02/S-03/S-04 沉默（`multiset(U) = P`）且 S-05 沉默（每行 `type`/`预算` 归一化相等），
  则 `Σ预算` 必然相等。证明：`Σ预算 = Σ_rows w(type)`，`w(manual)=2`、其余 1（`dispatch-card.ts:985`）；
  两边的行 multiset 相同、每行 type 相同 ⇒ 逐行相同 ⇒ 求和相同。∎
- 结论：`split:budget-drift` 只可能在前四条**已经报错**时触发，或当 `预算` 列在某子卡丢了（那时 `claim:<id>:budget` 结构性 gap 已经报）。
  它没有独立判别力。建议：保留 spec 的 token 名做诊断字段（`budget=<p>-><s>` 进 `[SPLIT]` 行），**不进 gap 列表**。
- 这个结论本身是"反恒真"的一部分：一条永远只能在别的判据已经报错时才响的判据，等于没写。

### 2.9 S-11 `claims:count:<n>>5`（AC-001，不新造）

- 触发：`n = |P| > 5`。**它属于卡属性，不是映射关系**，所以留在 `claims:` 家族（与 `claims:budget-sum` / `claims:manual-overflow` 同族：都是"这张卡整体如何"）。
  新造一个 `split:count:` 会让同一个信号有两个 token（仓库已有 single-source 的明确教训：`ESCALATED_REASONS` / `test_claim_parity.py`）。
- 负例：5 条卡（T-07a 真实卡）→ 0；6 条卡 → `claims:count:6>5`；20 条卡 → `claims:count:20>5`（一条，不带 id 列表）。
- 零成本：`claims.length`。

### 2.10 M-05/M-06/M-07 搬运三兄弟（merge 侧核心）

- **损失面**：(d) merge 只重写不搬运；(e) 层级降级/升级/类型替换。
- **前提**：merge 卡自带 claims 块 = **manifest**（母卡 claims 行逐字节 copy + 每单元报告路径），
  因为 AC-003 限制 merge 的 `read_scope` 只能到 `workers/<parent>-u*/report.md`（文件级条目），它读不到母卡 ⇒ 母卡 id 集必须由 PM 注入 manifest。
- **对账算法（零成本，逐行）**：
  ```
  1. for id in ids(manifest):
       rows_i = [row in unit_i's ## 断言裁决 where row.id == id]   # i = unit(id) from manifest
       if len(rows_i) == 0: merge:carry:<id>:unresolved
       if len(rows_i) > 1:  merge:carry:<id>:ambiguous
       src = rows_i[0];  dst = merge row for id
       if dst missing: claim:<id>:missing-row (复用)
       diff = [f for f in (verdict,finding,evidence,fetches,reason) if NORM(dst[f]) != NORM(src[f])]
       if diff == []:
            marker = CARRIED_FROM_RE on dst.evidence+dst.reason
            if not marker: merge:carry:<id>:no-marker            # advisory
            else if pointer doesn't resolve to src's line: merge:carry:<id>:bad-pointer:<path:line>
            else: OK
       else:
            merge:rewritten:<id>:<diff.join(",")>
            direction: upgrade table → merge:upgraded:<id>:<from>-><to>
                       downgrade table → merge:downgraded:<id>:<from>-><to>
            if re-judged AND carried-from: suppress rewritten, emit merge:rejudged:<id>   # 审计行
  2. for row in merge table where row.id not in manifest: claims:extra-row:<id> (复用)
  ```
- **负例构造**（用真实数据，见 §5 L3）：
  - 源行（T-07f 真实）：`| C-02 | grep | closed | 成立 | dispatch-card.ts:561-565；dispatch.py:750 | 1 | - |`
  - merge 行 A（诚实搬运）：同五列逐字 + 原因列写 `carried-from: workers/<parent>-u1/report.md:19` → 0 条；
  - merge 行 B（重写）：`| C-02 | grep | unverified | 无法判定 | - | 0 | budget |` → `merge:rewritten:C-02:verdict,finding,evidence,fetches,reason`
    + `merge:downgraded:C-02:closed->unverified`（两条：一条说"变了"，一条说"往哪变"）；
  - merge 行 C（升级，最危险）：源 `unverified`、merge 写 `closed/成立` → `merge:rewritten:…` + `merge:upgraded:C-02:unverified->closed`；
  - merge 行 D（指针造假）：`carried-from: workers/<parent>-u1/report.md:1`（第 1 行是标题，不含该 id）→ `merge:carry:C-02:bad-pointer:…/report.md:1`。
- **零成本**：K 份子报告 + 1 份 merge 报告，`parseVerdictTable` × (K+1)，逐行字符串比较 + 一次按行读文件定位指针。无 LLM、无执行。
- **不误报形态**：merge 表由脚本把 K 份子报告的行**逐字节拼接**（这正是 spec 要求的 merge 行为）→ 0 条；
  指针逐行定位命中 → 0 条；`re-judged` + `carried-from` 齐备 → 只剩 `merge:rejudged` 审计行，`fidelity` 仍 `ok`。

### 2.11 M-08 `merge:carry` 与 M-04 `claim:<id>:carried-from` 的分工

- `claim:<id>:carried-from`（复用，`worker-mode.ts:1056` ⑥）判的是"本轮没读过被引文件却没声明搬运"；
  在 merge 单元里它**必然**对每一行成立（merge 只读子报告，不读代码），所以 merge 行必须写 `carried-from:` —— 这恰好把 ⑥ 从"惩罚"变成"强制凭证"。
- `merge:carry` 判的是"凭证本身是否有效"：没有标记（advisory）、指向的行不含该 id（structural）、子报告里根本没有该 id 的行（structural）。
  上游 `carried-from` 的 mtime 版精度 0%（T-07 实测白送 `exit 2`）证明"标记存在"远不等于"标记为真"；`bad-pointer` 是让它可验的最便宜办法。
- 负例：`carried-from: report.md`（无 `path:line`，`CARRIED_FROM_RE = /carried-from\s*:\s*\S+/i` 仍会匹配，⑥ 因此放行）→ `merge:carry:<id>:bad-pointer:`；
  这就是"正则放行、指针校验拒绝"的分层价值。

### 2.12 层级降级的合法性判定表（要求 1(e)）

| 情形 | 合法？ | 条件 | 判据 |
|---|---|---|---|
| 同一 id 的 `类型` 替换（`grep→manual`、`manual→cmd`） | **否，无例外** | 类型是契约的一部分（`CLAIM_TYPE_PREFIX` 决定 `判据` 前缀；`claim:<id>:type-prefix` 是既有判据） | `split:mutated:<id>:type`（+ 既有 `claim:<id>:type-prefix` 若前缀不符） |
| `closed → unverified` / `成立 → 无法判定`（merge 层） | **仅当子单元自己就是这么写的** | merge 逐字搬运；子单元确实没预算时，它自己写 `unverified(budget)` 并满足 ② 的事实对账 | `merge:downgraded:<id>:…`（无逐字搬运时） |
| `unverified → closed` / `无法判定 → 成立`（升级） | **否**（虚增覆盖，比降级更危险） | 只有 `re-judged` + `carried-from: <子报告:行>` 且该行确实是反例 | `merge:upgraded:<id>:…` |
| `partial → closed` | **否** | 同上 | `merge:upgraded:<id>:partial->closed` |
| 子单元预算耗尽 → 它自己判 `unverified(budget)` | **是**（且这不是拆分损失） | 复用 ② 的事实对账（`取数` 达 cap 或 trace 有 `read_scope: blocked`） | 既有 `claim:<id>:reason` + ② |
| 拆分期"预降级"（把母卡 claim 直接写成 `unverified` 而不派发） | **否** | 没有这一档；要么派发让它自己结算，要么它是漏（S-02） | `split:missing:<id>` / `split:mutated:<id>:type` |
| `manual` 在子单元被判 `unverified(ambiguous/awaiting-input)` | **是** | RQ-3 §6.2 已定 manual 只能由 worker 自判 unverified | 既有判据，无新增 |

**统一口径**：`verdict_first_seen_at == unit`。merge 层没有聚合自由度（id 井），因此任何方向的变化都是"裁决第一次在 merge 出现"——
这不是"降级是否合法"的问题，而是**provenance** 的问题。这一条把 1(e) 的三小类统一成一个判据。

## 3. 与已交付判据的关系（要求 3）

### 3.1 现有 token 清单与逐条结论

`claimCoverage`（`worker/output-sections.ts:625`，12 个）+ `claimSettlementGaps`（`worker-mode.ts:1056`，3 组）+ `claimsGaps`（`dispatch-card.ts:985`，G1 侧）：

| 现有 token | merge 复用？ | 说明 |
|---|---|---|
| `claims:missing-table` | ✅ 直接 | 无 `## 断言裁决` 段 |
| `claim:<id>:missing-row` | ✅ 直接 | 用 manifest 作 claims 输入即可 |
| `claims:extra-row:<id>` | ✅ 直接 | 同上 |
| `claim:<id>:verdict` / `:finding` / `:verdict-finding` | ✅ 直接 | 闭集与映射是行级的，与是否 merge 无关 |
| `claim:<id>:evidence` | ✅ 直接 | 搬运后的证据仍是 `path:line`/`cmdref` |
| `claim:<id>:reason` | ✅ 直接 | `unverified` 仍是 7 词闭集 |
| `claim:<id>:self-evidence` | ⚠️ 复用 + 列级约定 | 自证集合含 `^report.*\.md$`，会命中 `workers/<p>-u1/report.md`。约定：子报告路径只进 `原因` 列的 `carried-from:`，`证据` 列只放搬运过来的原始 ref ⇒ 判据零修改 |
| `claim:<id>:struct-held` | ✅ 直接 | 父 struct 行不得计 closed，搬运时同样适用 |
| `claim:<id>:budget` | ✅ 直接 | 每行 `取数 ≤ min(Σ预算,30)`；注意 merge 的 claims = manifest ⇒ Σ预算 = 母卡 Σ预算 |
| `claim:<id>:tautology` | ✅ 直接 | 卡级属性，随 manifest 一并复用 |
| `claim:<id>:carried-from` | ✅ **且变必填** | merge 行的"没读过被引文件"恒真 ⇒ 强制写标记；由 M-08 判其有效性 |
| `claims:unverified-ratio:<u>/<n>><limit>%` | ✅ **最佳落点** | n = 母卡 id 数，正是 AC-005 想要的母卡级覆盖率；review 角色 60% 上限 |
| `claims:fetches:<sum>><cap>` | ❌ **必须豁免** | 见 §3.3 |
| `claims:fetches:<sum>>trace:<n>` | ❌ **必须豁免** | 见 §3.3 |
| `claims:budget-sum:<sum>><40>` / `claims:manual-overflow:<m>/<n>` | ✅（作用于子卡） | 它们正是 S-09 的 rule 来源；子卡派发时也会各自被 G1 判一次（双保险，不是重复语义：一个是"这张子卡合不合规"，一个是"切法是否造出了不合规的子卡"） |
| `claim:<id>:{type,statement,falsifier,locator,judgement,budget}`（结构性） | ✅ 不改 | 子卡结构性 gap 说明母卡行被搬坏 |
| `claim:<row>:unparsable` | ✅ 不改 | 搬运后仍是解析问题 |

### 3.2 必须在 merge 模式豁免的两条（算术）

`claimSettlementGaps` 的 ③：`const { fileCap } = claimBudgetCaps(opts.claims)` → `min(30, 6n)`；`fetchSum = Σ row.取数`。

- 20 claim 母卡拆 4×5 个单元，每单元按 T-07 实测强度（13 次取数 / 5 claim）→ `fetchSum = 52`；
  `fileCap = min(30, 6×20) = 30` ⇒ `claims:fetches:52>30`（**必报**）；
  merge 单元只读 4 份子报告，`traceReads ≈ 4` ⇒ `claims:fetches:52>trace:4`（**必报**）。
- 这两条在单单元 run 上是正确的上界（B-6），在聚合表上语义错误：它们问的是"这个进程自己读了多少"，
  而 merge 的 `取数` 是**搬运别处的数字**。处理：`claimSettlementGaps` 增加 `mode: "unit" | "merge"`，
  merge 模式跳过 ③（③ 的逐行版本由 `claim:<id>:budget` 与 M-05 的逐字搬运共同保证：数字被改就会报 rewritten）。

### 3.3 命名方案与冲突检查

- **前缀分配**：`split:` = 母卡↔子卡映射（P 侧）；`merge:` = 搬运（M 侧）；`claim:` / `claims:` **不新增、不改义**。
  例外：AC-001 的 `claims:count:<n>>5` 已在 spec 定名且属于"卡属性"家族（与 `claims:budget-sum` 同族），保留。
- **第三段**：要么是 claim id（`^C-\d{2,3}(?:\.\d+)?$`），要么是闭集 rule 名。rule 名不得与既有 element 名重复：
  `type|statement|falsifier|locator|judgement|budget|verdict|finding|evidence|reason|self-evidence|struct-held|tautology|missing-row|carried-from`。
  已分配的 rule 名：`manifest|missing|duplicate|extra|mutated|orphan-child|split-locator|cap-inflation|unit-infeasible|budget-drift`（split）、
  `rewritten|upgraded|downgraded|carry|rejudged`（merge）。**十个 + 五个名字与上表 15 个 element 名零交集**（可机检：两个集合求交 = ∅）。
- **第四段**：`mutated` 用列名（6 个闭集）；`unit-infeasible` 用 rule 名（3 个闭集）；`carry` 用 detail（4 个闭集）；
  `cap-inflation`/`budget-drift` 用 `<a>-><b>`。第四段出现自由文本即为命名违规（可机检：`^split:mutated:C-\d{2,3}(\.\d+)?:(type|statement|falsifier|locator|judgement|budget)$`）。
- **与 spec 的兼容**：spec AC-008 的 `merge:rewritten:<id>` 是本文 `merge:rewritten:<id>:<field-list>` 的**前缀**，
  按前缀匹配的消费者不受影响；spec 的 `merge:<id>:missing|extra` **建议不实现**（与 `claim:<id>:missing-row` / `claims:extra-row:<id>` 重复，
  会让同一个洞有两个 token）。这是一处对 spec 的**显式偏离**，需要 design 阶段裁决（已在 §6 列出）。
- **平价锁**：所有新 token 必须同时出现在 `shared/dispatch-card.ts`（或新 `shared/split-fidelity.ts`）与 `autopilot/dispatch.py`，
  并由 `packages/multi-workers/test_claim_parity.py` 逐字锁定（现有先例）。
- **一处接线约束**：`worker-mode.ts::claimGapIds` 的正则是 `^claim:(C-\d{2,3}(?:\.\d+)?):`，只认 `claim:` 前缀。
  若不扩展，`merge:*` gap 不会出现在 `## Questions` 的 `unsettled claim(s): …` 列表里，只能走"整串列出"的 fallback。
  建议改为 `^(?:claim|merge):(C-\d{2,3}(?:\.\d+)?):`（一处正则，两行改动）。

### 3.4 与 `claimsGaps`（G1）的关系

`split:` 判据**不进入** `claimsGaps`：后者的输入是单张卡的文本，而 split 判据的输入是**两张以上卡的映射**。
它们共享的只有底层解析器与 id 归一化。落地位置：`pm/ui-bridge.ts` 的同一个 claims gate 调用点之后（`:2900-2910`），
产物合流成同一条拒绝文本（AC-001 的"零副作用"拒绝路径已有实现），并由 `MW_CLAIM_GATE` 同一个开关控制 advisory/enforce——
**不新增第二个开关**（D-006 的教训：两个开关就会有两个默认值）。

## 4. 104 单元语料的算术（③ 交付）

### 4.1 口径

- 语料：`spec-rq3-claim-taxonomy-20261020.md` §1.3 的 104 个判定单元（11 张卡，逐条带 `id/L/类型`），按文档顺序在**卡内**顺序切片。
- `Σ预算` 权重按 RQ-3 §6.1：`manual=2`，`cmd/grep/struct=1`（即 `dispatch-card.ts:985` 的 `budgetSum` 口径）。
- `manual` cap = `min(4, ⌈n/3⌉)`（`claimsGaps` 现实现）。
- `struct 父子对`：语料里**没有任何真实 claims 块**（RQ-3《未找到清单》#1：全仓库只有 `spec.md:77` 一处 `mw-claims`），
  所以"含 struct 父子对"无法从产物读，只能按 RQ-3 自己的 claim 化建议（M-3/§M-6/B-10：`struct` 父行 + `C-0X.Y` 子行）**展开后**计算。
  本文取 24/29 个 struct 单元的可枚举子项数 N（全部来自语料同文），5 个的 N 只能由运行时枚举源（grep/cmd）产出。

### 4.2 表 A：按 5 条/单元切分（表内顺序 = 文档顺序）

| 卡 | units | Σ预算 | chunks | 各 chunk 大小 | Σ预算/chunk | manual/chunk | struct/chunk | manual-cap 违例 |
|---|---|---|---|---|---|---|---|---|
| DS-QG2 | 16 | 19 | 4 | 5/5/5/1 | 5/5/7/2 | 0/0/2/1 | 1/1/1/0 | 0 |
| DS-QG2C | 7 | 8 | 2 | 5/2 | 5/3 | 0/1 | 0/0 | 0 |
| DS-QG2D | 11 | 11 | 3 | 5/5/1 | 5/5/1 | 0/0/0 | 0/0/1 | 0 |
| T18 | 14 | 19 | 3 | 5/5/4 | 7/6/6 | 2/1/2 | 1/1/2 | 0 |
| QG2B | 16 | 17 | 4 | 5/5/5/1 | 6/5/5/1 | 1/0/0/0 | 2/0/4/1 | 0 |
| W15 | 8 | 12 | 2 | 5/3 | 8/4 | 3/1 | 2/1 | **1** |
| ACB-V1 | 6 | 6 | 2 | 5/1 | 5/1 | 0/0 | 2/0 | 0 |
| REFV | 6 | 6 | 2 | 5/1 | 5/1 | 0/0 | 3/1 | 0 |
| DESIGN | 7 | 12 | 2 | 5/2 | 8/4 | 3/2 | 2/0 | **2** |
| R-02 | 6 | 9 | 2 | 5/1 | 7/2 | 2/1 | 2/0 | 0 |
| CODEREV | 7 | 11 | 2 | 5/2 | 9/2 | 4/0 | 0/1 | **1** |
| **合计** | **104** | **130** | **28** | — | 见下 | **26** | **29** | **4** |

汇总：
- chunk 大小分布：`5×17 / 4×1 / 3×1 / 2×3 / 1×6` ⇒ **11/28（39.3%）欠槽，6/28（21.4%）单条**。
- `Σ预算/chunk` 直方图：`1:4, 2:3, 3:1, 4:2, 5:9, 6:3, 7:3, 8:2, 9:1`，均值 **4.64**，max **9** ⇒ 与 cap 40 相差 4.4 倍，**`Σ预算 ≤ 40` 永不可能触发**。
- `manual` 分布：`0:14, 1:6, 2:5, 3:2, 4:1` ⇒ **8/28 有 ≥2 条 manual，3/28 有 ≥3 条，单单元最多 4 条**（CODEREV chunk1 = K1..K4 四条纯人工）。
- 母卡级 manual 越界：**5/11 张卡（45.5%）自己就过不了 `min(4,⌈n/3⌉)`**（T18 5/14>4、W15 4/8>3、DESIGN 5/7>3、R-02 3/6>2、CODEREV 4/7>3）。
  ⇒ 这 5 张卡今天根本不可派发，它们的 4 个违例单元是"继承"而非"切片制造"。

### 4.3 表 B：struct 展开与父子跨单元（按 RQ-3 自己的 claim 化建议展开后）

| struct 单元 | N（子项数） | N 依据（同文） | 5 槽内可否装下父+N 子 |
|---|---|---|---|
| A1 | 6 | 「4 major + 2 minor」 | 否（7 槽） |
| A6 | 3 | 「L2/L3/L5」 | 可（4 槽），需对齐 |
| A14 | 15 | 「AC-001..015」 | 否（16 槽） |
| C11 | 15 | 「12/3/0」=15 | 否 |
| D2 | 16 | 「AC-NNN」（D12 自述 16 条） | 否 |
| D10 | 5 | 「五形态」 | 否（6 槽） |
| D12 | 16 | 「16 条 AC」 | 否 |
| D14 | 5 | 「至少 5 条对抗用例」 | 否 |
| E2 | **runtime** | 「所有会写盘语句」= grep 的产出 | **不可静态判定** |
| E4 | 5 | 「五个写者」 | 否 |
| E11 | 6 | 「抽 ≥6 个」 | 否 |
| E12 | 4 | 「27/20/14/2」（按 4 个集合读；按 63 项读更差） | 可（5 槽），需对齐 |
| E13 | 8 | 「抽 ≥8 个」 | 否 |
| E15 | 2 | 「两类清单」 | 可 |
| E16 | 14 | 「14 行必须齐全」 | 否 |
| F2 | **runtime** | 「逐条给拦/放结论」= 命令集 | 不可静态判定 |
| F4 | **runtime** | 「逐条给 issue+rc」 | 不可静态判定 |
| F8 | 2 | 「分列两层」 | 可 |
| G4 | 3 | (a)(b)(c) 三条 | 可 |
| G5 | 3 | 同上 | 可 |
| H1 | 21 | 「21 条引用」（同文 M-6） | 否（22 槽） |
| H2 | 21 | 同 H1 | 否 |
| H3 | 4 | `TOOL_ALLOWLISTS` = read/find/grep/ls | 可 |
| H6 | **runtime** | 「列出来核不成的项」 | 不可静态判定 |
| I1 | 16 | 「16 条 AC」 | 否 |
| I2 | 22 | 「22 条 VC」 | 否（23 槽） |
| J1 | 1 | 单条交付要求 | 可 |
| J4 | 6 | 「六项三态」 | 否（7 槽） |
| K6 | **runtime** | 「每一个 finding」 | 不可静态判定 |

统计：
- 29 个 struct 单元：**N 已知 24 个，Σ子行 = 219**；**N 只能由运行时枚举源产出 5 个（17.2%）**。
- **N ≥ 5 的 16 个（55.2%）** ⇒ 父 + N 子占据 `N+1 > 5` 槽，无论对齐如何，**按 id 计数切片必然跨单元**（S-06 必然触发）。
- 按 5 条切片（未知 N 以 3 代替，明示假设）：338 个 id（104 + 219 + 5×3）→ **72 个单元**；**20/29 个父被切散（69.0%）**（16 个必然 + 4 个对齐相关）；
  只有 9/29 保持完整，且全部是 N ≤ 4 的小簇。
- 对照：若坚持"簇原子"打包（父+子整体移动，允许单元超过 5 个 id），**51 个单元**（vs 72），其中 **16 个单元超 5 槽**（就是那 16 个 N≥5 的簇，17~23 个 id）。

### 4.4 表 D：预算与派生 cap

| 指标 | 单卡派发（11 张） | 5 条/单元（28 个单元） | 比值 |
|---|---|---|---|
| `Σ预算`（manual=2） | 130 | 130（恒等） | 1.00 |
| `Σ fileCap = Σ min(30, 6n)` | **330** | **624** | **1.89×** |
| `calls / claim` | 3.17 | 6.00 | 1.89× |
| `Σ byteCap = Σ min(393216, 65536n)` | 4,325,376 | 6,815,744 | 1.58× |
| 每单元 `Σ预算` 上限 | 19（DS-QG2/T18） | 9（CODEREV chunk1） | — |
| 与 cap 40 的距离 | 2.1× | **4.4×** | — |

### 4.5 表 E：merge 模式的既有判据假阳性（用真实强度代入）

| 量 | 值 | 来源 |
|---|---|---|
| 20 claim 母卡拆 4×5 | 4 个单元 | AC-002 机械口径 |
| 每单元取数（按 T-07 实测强度 13/5 = 2.6/claim） | 13 | `t07-e2e-results-20261022.md` 第三轮 |
| merge 表 `Σ取数` | **52** | 搬运求和 |
| ③ 的 `fileCap`（`claimBudgetCaps(manifest)`） | 30 | `dispatch-card.ts:1042` |
| ③ 的 trace 上界（merge 只读 4 份报告） | ~4 | `allowedReads` |
| 结论 | `claims:fetches:52>30` 与 `claims:fetches:52>trace:4` **必报** | §3.2 |

### 4.6 「统一 5 条/单元」必然出错的四种形状

1. **`struct` 枚举 N ≥ 5（16/29 = 55.2%）**：父+子占 N+1 > 5 槽 ⇒ 任意对齐都跨单元 ⇒ 与 AC-006 直接冲突。
   要么违反 AC-006，要么把子行塌回父行（B-10 的"结构 claim 吞掉原子 claim"，语义丢失但判据全绿）——**两条路都丢语义**。
   这是"按数量切"与"按簇守恒"的根本冲突。
2. **N 需运行时枚举（5/29 = 17.2%）**：`「所有会写盘语句」/「每一个 finding」` 的 N 只能由 `grep`/`cmd` 产出，
   而拆发生在派发期（零副作用、未执行任何命令）⇒ **装箱问题在派发期不可解**。含这类 struct 的卡无法套用任何固定宽度规则。
3. **`manual` 密度是 n 的函数，切片会重新洗牌（5/11 卡已越界）**：`cap = min(4,⌈n/3⌉)`，n=5 时 cap=2，n=14 时 cap=4。
   同一密度在母卡里合规、在 5 槽切片里越界（可构造，见 S-09 负例）；反过来切片也可能"洗掉"越界（把 5 条 manual 分散到 5 个单元）。
   ⇒ 5 条规则既不能修复密度问题，也不能保证不制造它。
4. **尾槽与固定开销（11/28 欠槽，6/28 单条）**：每个单元都要付启动 + goal/卡读 + 交付段契约 + `[CLAIMS]` + settle；
   单元数 11 → 28（→ merge 时 29），固定开销 ×2.5。单条单元的 `fileCap = 6` 与 5 条单元相同（每 claim 恒 6），
   所以尾槽不省预算，只摊薄不了开销 ⇒ 这是 AC-010 必须定价的量，而不是"保真度"能判的量。
5. （附）**21 行大表（REFV H1/H2）**：1 条 struct 吞 21 行（5 条规则完全看不出问题），或 22 个 id 的簇（永远装不进 5 槽）。
   这类卡的"必然出错"来自**claim 粒度不均一**，任何固定宽度规则都无解。

**替代规则（给 design 的建议）**：单元 = **claim 簇的装箱**，不是 id 的定宽切片。约束：
(a) 簇原子性（父+全部子行+该 claim 的全部 locator 同一单元）；
(b) `Σ预算(manual=2) ≤ 8`（语料 5 槽实测 max 9，取 8 留 1 格给人工 claim 的上浮）；
(c) 每单元 ≥1 条 `cmd/grep/struct`（RQ-3 §6.4 反后门第 1 条）；
(d) 单元数 `K = ⌈Σ槽/5⌉` 只作下界，实际 K 由装箱结果决定（语料：28→51 之间有可行解，取决于是否展开 struct）。

## 5. 反恒真：每条判据"诚实产出不误报"的证据形态（要求 5）

统一四层协议。**不是承诺，是构造方式**；每层给出可执行形态与判据通过条件。

- **L0 空跑（no-op）**：未标记拆分的卡（`split-units` 缺失）⇒ 所有 `split:*` / `merge:*` 返回 `[]`。
  构造：取仓库现有 11 张语料卡中任意一张不带 `mw-claims` 的卡 + T-07a 的 task.md 去掉 claims 块 ⇒ 断言空。
  这条同时是 AC-012 的零回归证据（不需要新开关，gated by header）。
- **L1 格式扰动（归一化不动点）**：把母卡 claims 块按 `parse → render` 往返，再注入格式扰动（全角 `｜`/`：`、反引号、多空格、
  预算前导零 `02`、`定位` 多 ref 换序、列序调整、追加无用列、表格包进围栏外的引用块）⇒ 断言 `split:mutated` 与 `merge:rewritten` **全空**。
  通过条件：`parse(render(claims)) ≡ claims`（N0..N5 逐格相等），104 单元 + T-07a 真实卡各跑一遍。
- **L2 单点变异（差分）**：从诚实产物出发，每次只改一处（改一个词、删一行、加一行、换一个 id、把一条 evidence 指向 `report.md`），
  断言 **恰好一个** 目标 token，且 id/field 段正确，**无附带 token**（差分正交性）。每个判据至少一条变异用例；
  负例集由 §2 各条给出（共 12 条 S 侧 + 4 条 M 侧，全部可手写为 fixture 文本，无需真实 run）。
- **L3 真实回放（honest artifact）**：
  - P 侧：拿 `.agenticdoc/claim-driven-review/tasks/T-07a-e2e-review-a.md` 的真实 5 条 claims，
    机械搬进 1 张子卡（或 2+3 两张）⇒ 0 条。这是"唯一一张真实 5-claim 卡"的回放，也是 `claims:count:5>5` 不响的边界证据。
  - M 侧：拿 `.agenticdoc/claim-driven-review/workers/cdr-t07f-e2e-review-a/report.md` 的**真实七列表 5 行**作"子单元报告"，
    用脚本把这些行逐字节拼成 merge 表、每行 `原因` 列补 `carried-from: workers/cdr-t07f-e2e-review-a/report.md:<该行行号>`
    ⇒ 断言 `merge:*` 全空、`claim:*:carried-from` 不响、② 比例 0/5。这是唯一有真实证据形态的 merge 回放（上游没有 merge run，见 §6）。
  - 反向证据（诚实样本上**应该**出现、且不算失败的）：S-08 `cap-inflation` 在 330→624 上必然出现，`fidelity` 仍为 `ok`；
    M-11 `merge:rejudged` 在显式重判样本上出现，`fidelity` 仍为 `ok`。把"审计行"与"gap"混在一个计数里就是恒真化的开始。
- **L4 既有套件**：`test/suite/claim-block.test.ts`、`claim-coverage.test.ts`、`claim-bypass.test.ts`、`dispatch-claims-render.test.ts`、
  `packages/multi-workers/test_claim_dispatch.py`、`test_claim_parity.py` 必须一行不改全绿（新判据只在 gated 分支里）。

## 6. `## 未覆盖面`

- **无实现、无实测**：本文全部判据是纸面 + 语料算术；`split-fidelity.ts` / `splitFidelityGaps` 不存在（`rg "split:" packages` 0 行）。
  因此没有"通过率"，只有 L0~L4 的**验收形态**。这是 RQ-2 的卡型约束（research 只读）。
- **无真实 merge run**：上游 RQ-3《未找到清单》#2 记录 `## 断言裁决` 的实现到 2026-10-20 为 0 行（现已有 `parseVerdictTable`），
  但**没有任何一次真跑的 merge 单元**——merge 侧判据的 L3 回放只能用"单个真实子报告 + 机械拼接"模拟，拼接脚本未写（本文只写形态）。
- **struct 父子对的数量是展开后的假设值**：语料里 0 个真实 `mw-claims` 块，"29 个 struct 单元 / 219 个子行 / 338 个 id" 全是
  按 RQ-3 §M-3/§M-6 的 claim 化建议**推演**出来的，不是产物实测。若 design 决定"struct 不展开子行"，则 S-06 在母卡层面无对象（只剩 S-07 兜底），
  §4.3 的 20/29 跨单元数字相应为 0（但 B-10 的"struct 吞掉原子 claim"损失会转移到单元内，本文不判）。
- **5 个 runtime-N 的 struct 单元**（E2/F2/F4/H6/K6）里，装箱可行性未定；本文用 N=3 代替，只用于给"必然切散"一个可复现的下界，不代表真实 N。
- **`manual` 密度的新造违例没有语料样本**：4/28 违例全部属于母卡已越界的卡；"母卡合规、切片越界"只有构造负例（S-09），无真实卡佐证。
  这与 RQ-3 的抽样偏差有关（11 张卡里 5 张 manual 密度已 >1/3）。
- **未覆盖 id 重编号方案**：若设计阶段改为"每单元 C-01..C-05 重新编号 + 映射表"，S-06/S-07 的触发条件全部要重写，
  `split:mutated` 的 id 对齐也要换成映射查询。本文按 AC-004 的"id 井"口径写，**未给重编号版本**。
- **未覆盖 merge 单元自身的 claims 块形态**（spec 待决 1）：本文假设 merge 卡带 manifest claims 块（否则 `claimCoverage` 直接返回 `[]`，
  所有 merge 判据失效）。这个假设是硬前提，未经 design 确认。
- **未覆盖 `[SPLIT]` 行的解析与度量**（`usage.py` 没有 `[SPLIT]` 正则）：本文只规定 `fidelity=<ok|gaps>` 必须由同一函数产出，
  未设计它的统计口径（属 RQ-3）。
- **未覆盖跨单元证据一致性**：子单元引用同一文件的不同行段时，merge 搬运逐字即可，但如果两个单元对同一 claim 给出相反判定（id 井使这不可能），
  或两个单元引用同一行而判定相反，本文无判据。前提是 id 井成立。
- **未覆盖 Windows 路径/大小写**：`claimPathKey` 的 win32 大小写折叠未在新的指针校验（M-08 `bad-pointer`）上复核。

## 7. 证据（本文数字的复算方式）

```text
# 语料解析 + 切分算术（本文 §4.2/§4.3/§4.4 全部数字）
python - <<'PY'
import re, io
from collections import OrderedDict, Counter
t = io.open(".agenticdoc/claim-driven-review/evidence/research/spec-rq3-claim-taxonomy-20261020.md", encoding="utf-8").read()
s, e = t.index("### 1.3"), t.index("### 1.4")
card, units = None, []
for line in t[s:e].splitlines():
    m = re.match(r"^\*\*(\S+)\*\* .", line)
    if m: card = m.group(1); continue
    m = re.match(r"^- `(\w+)` L(\d+) \[(\w+)\]", line)
    if m and card: units.append((card, m.group(1), m.group(3)))
# 断言 len(units) == 104; Counter(类型) == {cmd:21, grep:28, struct:29, manual:26}
PY
# 实测输出：units=104 / 28 chunks / chunk 大小 {5:17,4:1,3:1,2:3,1:6}
#          Σ预算/chunk {1:4,2:3,3:1,4:2,5:9,6:3,7:3,8:2,9:1} mean=4.643
#          Σ fileCap 330 -> 624 (1.89x)；struct 展开 338 id -> 72 chunks，20/29 父跨单元
```

| 论断 | 锚点 / 命令 |
|---|---|
| 104 个单元、21/28/29/26 分布 | 语料 §1.2/§1.3；解析脚本复算一致 |
| 12 个 gap token | `worker/output-sections.ts:625-720`（`claims:missing-table`、`claim:<id>:missing-row`、`claims:extra-row`、`:verdict`、`:finding`、`:verdict-finding`、`:evidence`、`:reason`、`:self-evidence`、`:struct-held`、`:budget`、`:tautology`） |
| ②③⑥ 三组判据 | `worker/worker-mode.ts:1056-1150`（`claims:unverified-ratio`、`claims:fetches:<sum>><cap` / `>trace:<n>`、`claim:<id>:carried-from`） |
| `fileCap = min(30, 6n)`、`byteCap = min(393216, 65536n)` | `shared/dispatch-card.ts:1042-1050`（`CLAIM_BUDGET.perClaim=6 / callCap=30 / claimByteCap=65536 / byteCapMax=393216`） |
| `Σ预算` 权重 manual=2、cap 40、manual cap `min(4,⌈n/3⌉)` | `shared/dispatch-card.ts:985-1010`（`budgetSum += type==="manual"?2:1`；`CLAIM_BUDGET_SUM_MAX=40`；`Math.min(CLAIM_MANUAL_CAP, Math.ceil(total/3))`） |
| 归一化闭包（N1/N2） | `shared/dispatch-card.ts::normalizeClaimText` / `stripClaimTicks`（全角数字/：/｜/U+3000 + 去 tick + trim） |
| 子报告会被判自证 | `worker/output-sections.ts::SELF_EVIDENCE_BASENAMES`（`^report.*\.md$` 等）+ `isSelfEvidenceRef`（basename 比较） |
| `carried-from` 正则 | `worker/worker-mode.ts:905`（`/carried-from\s*:\s*\S+/i`） |
| 上游 mtime 版 0% 精度 | `claim-driven-review/evidence/t07-e2e-results-20261022.md`《三轮发现并修掉的缺陷》#1 |
| T-07 实测强度 13 取数 / 5 claim | 同上，第三轮 `[CLAIMS] … claims=5 closed=5 fetches=13` |
| 真实 5-claim 卡（Σ预算 10、5×grep） | `.agenticdoc/claim-driven-review/tasks/T-07a-e2e-review-a.md` 的 `<!-- mw-claims: v1 -->` 块 |
| 真实七列表（merge 回放素材） | `.agenticdoc/claim-driven-review/workers/cdr-t07f-e2e-review-a/report.md` §断言裁决（5 行，含 `；` 分隔） |
| 无真实 `mw-claims` 块 / 无真实 merge run | 语料《未找到清单》#1/#2；`rg -n "mw-claims" .agenticdoc packages` 只有 `spec.md:77` + 上游卡 |
| 新 token 不存在 | `rg -n "split:|merge:" packages` 对 `split:`/`merge:` 前缀 0 命中 |

## 8. 上下文来源

- 契约实现（全文读）：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`、
  `.../worker/output-sections.ts`、`.../worker/worker-mode.ts`（`:900-1160` 全文、`:4060-4400` 结算折叠、`:4300-4390` 终态）、
  `.../worker/read-scope.ts`（cap 与 `isSameOrUnder`）、`.../worker/output-writer.ts`（`judgedProductFile`/`agentProductText`）、
  `.../shared/deliverable-evidence.ts`、`.../pm/ui-bridge.ts`（`:2330-2965` claims gate）
- Python 侧（抽查）：`packages/multi-workers/autopilot/dispatch.py:460-560`（`CLAIM_TYPES`/`CLAIM_BUDGET`/`_CLAIM_COLUMN_ALIASES` 镜像）
- 语料：`claim-driven-review/evidence/research/spec-rq3-claim-taxonomy-20261020.md`（104 单元、§M-3/§M-6/B-10、§6 档位）、
  `claim-driven-review/evidence/t07-e2e-results-20261022.md`、`claim-driven-review/tasks/T-07a-e2e-review-a.md`、
  `claim-driven-review/workers/cdr-t07f-e2e-review-a/report.md`
- 本 key：`spec.md`（AC-004..AC-009 已定 token 名，本文沿用/偏离处均标注）、`tasks/RQ-2-split-fidelity.md`、
  `tasks/RQ-1-orchestration-seams.md`（避免重复编排面）、`tasks/RQ-3-metrics-baseline.md`（避免侵入度量）
- 测试先例：`test/suite/claim-block.test.ts`、`claim-coverage.test.ts`、`claim-bypass.test.ts`、`dispatch-claims-render.test.ts`、
  `packages/multi-workers/test_claim_parity.py`、`test_claim_dispatch.py`
- 全局纪律：`AGENTS.md`（不改 pi 核心、无 inline import、不 commit）、`.agenticdoc/goal.md`（goal 一致性追踪）
