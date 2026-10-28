# Design: claim-driven-review

> Key: claim-driven-review
> 输入：`evidence/research/spec-rq1-review-corpus-20261020.md`（成本标定）、`spec-rq2-seams-20261020.md`（接缝）、`spec-rq3-claim-taxonomy-20261020.md`（分类法与反例）
> 约束：GC-1 不改 pi 核心；GC-2 不改任何角色工具集（决定 D-005）；GC-3 拒绝零副作用；GC-5 无中心调度器

## 1. 架构总览

四层，每层一个落点，中间只通过两种文件传递：**卡文（claims 块）** 与 **产物（## 断言裁决 表）**。

```
card (.md)                       task.md                         output.md
  <!-- mw-claims: v1 -->   ──注入──>  <!-- mw-claims: v1 -->  ──读取──>  ## 断言裁决 (7 列)
        │                                  │                              │
   L1 parseClaimsBlock              L3 parseClaimsBlock            L3 parseVerdictTable
        │                                  │                              │
   L2 claimsGaps (G1)               L3 claimGaps (G2)         ──────>  compare(卡, 表)
   + claimBudgetCaps → read_scope caps ─────────────────────────────>  TerminalGaps.claimGaps
                                                                              │
                                                                    [CLAIMS] trace + run.json
                                                                              │
                                                                    L4 usage.py / status-model.ts
```

关键取舍：**claims 块随 task.md 一起注入**（`pm/ui-bridge.ts:2333/2372` 的种子注入旁），结算期只读 task.md，不回读卡文件。理由是卡文件可能在 run 期间被 PM 改写（RQ-2 §2.3），而 `card_sha256:` 校验回读的成本高于注入。

## 2. 数据契约

### 2.1 卡内 claims 块（L1）

```markdown
<!-- mw-claims: v1 -->
| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |
| --- | --- | --- | --- | --- | --- | --- |
| C-01 | grep | `decision-tool.ts` 不再读取 `.mw/decide-points.json` | 出现 `readFileSync` 命中该路径 | `pm/decision-tool.ts` | grep: ... => count=0 | 2 |
| C-02 | struct | 覆盖表 6 行齐全 | 缺任一行 | `evidence/qg-report.md` | shape: … x 6 | 1 |
| C-03 | cmd | 定向用例仍绿 | 给出 rc≠0 | `evidence/claims/qg-20261021.md#C-03` | cmd: node … --run test/x.test.ts => rc=0 | 1 |
| C-04 | manual | 修复未引入新的 fail-open | 枚举出任意新 fail-open | 本次 diff | manual: … => 由 PM 裁决 | 2 |
```

- `id`：`^C-\d{2,3}$`。子行 `C-01.3` 只允许父为 `struct`（RQ-3 §5.1 / B-10）。
- `定位` 按类型分化：`grep`/`struct` → `path[:a-b]`；`cmd` → `evidence/claims/<file>#<claim-id>`（D-005：PM 预执行落盘，review 只读）；`manual` → `path:line` 指向需人工裁决的产物，或 `-`。
- `类型` 自报 ∈ `cmd|grep|struct|manual`，且必须与 `判据` 前缀一致（`cmd:` / `grep:` / `shape:` / `manual:`）。分类器**不推断**（一致率 63.5%，RQ-3 §2.4）。
- 预算：manual 记 2，其余记 1；`Σ预算 ≤ 40`；`manual 条数 ≤ min(4, ceil(n/3))`。
- 关闭块的写法：`<!-- /mw-claims -->`，容错为「直到下一个 H2 或文件尾」。

### 2.2 产物裁决表（L3）

七列 `claim | 类型 | 裁决 | 判定 | 证据 | 取数 | 原因`，`裁决 ∈ {closed,partial,unverified}`、`判定 ∈ {成立,不成立,无法判定}` 两列分置（RQ-3 §5.1）。证据语法与 `unverified` 7 词闭集见 RQ-3 §5.3/§5.4，**常量必须在 TS/Python 各一份并被平价测试锁住**（先例 `decision_points.py:111-120` 的 `ESCALATED_REASONS`）。

### 2.3 单源常量

| 常量 | TS | Python | 平价锁 |
|---|---|---|---|
| `CLAIM_TYPES` = `["cmd","grep","struct","manual"]` | `shared/dispatch-card.ts` | `autopilot/dispatch.py` | 新增 `test_claim_parity.py`（逐字） |
| `UNVERIFIED_REASONS` = 7 词 | 同上 | 同上 | 同上 |
| `CLAIM_GATE_DEFAULT` = `"advisory"` | 同上 | 同上 | 同上；运行期可被 `MW_CLAIM_GATE=enforce` 覆盖（两侧同名同义） |
| `CLAIM_BUDGET` = `{perClaim: 6, callCap: 30, hardCap: 35, claimByteCap: 65536, byteCapMax: 393216}` | `worker/read-scope.ts:31-32` 旁 | `autopilot/dispatch.py`（`_CLAIM_BUDGET`） | 同上 |

## 3. 模块划分

### 3.1 L1 契约层：`shared/dispatch-card.ts`

新增三个纯函数（无 IO）：

- `parseClaimsBlock(text): Claim[]` — 复用 `h2Headings` 的 fence 状态机（`worker/output-sections.ts:128-188`）跳过代码块；表头别名、列序任意、全角归一（P-048）。
- `claimsGaps(claims, opts): string[]` — 返回 `claim:<id>:<要素名>` 形态的缺失项，供拒绝文案直接拼接（AC-001 要求原因含 claim id）。
- `claimBudgetCaps(claims): {fileCap, byteCap}` — `fileCap = min(30, Σ预算)`、`byteCap = min(393216, 65536 × claims.length)`。常数取自 RQ-1 §5（p90 单次 4,854 tokens、安全带 <400k chars）；**否决**了 RQ-2 §3.4 的 `min(3*claims,60)`/512KiB（那是并行期按 spec 初稿写的占位值）。

文件尺寸判据（AC-001 ④）用 `fs.statSync` 在 gate 处判，不读内容；三种未覆盖形态：`symbol` 定位无文件、定位文件不存在、定位在 projectDir 之外 → 三者一律 `claim:<id>:locator-unresolved` 告警（advisory）或拒绝（enforce）。

### 3.2 L2 派发层

**TS（PM 手工 + `/worker`）** — 只动 `pm/ui-bridge.ts`：

- `readDispatchCard`（2556-2601）：`missing` 聚合处追加 `claimsGaps`（2585 之后、`if (missing.length > 0)` 之前），返回值扩为 `{claims, caps}` 放进 `DispatchCardGate`（2531-2545）。
- 新拒绝码 `dispatch-claims`（不混用 `dispatch-card`，便于 card_audit 区分），文案照 `dispatchCardRefusal`（2603-2616），保证 `nothing was written.` 尾句与零副作用。
- `writeDispatchTaskMd`（2624-2699）：新增 `mergeReadScope`（与 `mergeWriteScope` 2146 同形态：`read_scope:` block list + `l2_read_file_cap:`/`l2_read_byte_cap:` 两个 scalar），在 `2666 mkdirSync` 之前完成合并；同时把 claims 块原样注入 `mw-dispatch-card: v1` 标记区。
- **`read_scope` 条目 = 两个锚点 + 每条 claim 的 `定位` 去 span**（`.agenticdoc/<key>`、`.agenticdoc/goal.md`，再加 `定位` 去掉 `:line`/`:a-b` 与 `#<claim-id>` 后的文件路径；去重、拒绝对路径与 `..`）。没有这一条，review 单元只能读卡自己的目录，断言指向 `packages/**` 时全部退化为 `unverified: no-access` —— 而“按断言定价”的前提就是“能读到断言指向的那一个文件”。
- 两个调用点透传 caps：`2930`（工具）与 `3448`（命令）。
- 灰度：`enforce` 时进 `missing`；`advisory` 时在**有 claims 块**的前提下向回执追加一行 `[claims] ...`（无 claims 块不追加，否则 `triage-dispatch.test.ts:355-357` 的全文 `toBe` 会红）。

**Python（conductor）** — 只动 `autopilot/dispatch.py`：

- `dispatch_card`（569-601）返回 dict 加 `"claims"`（该函数已读全文，是唯一卡文本来源）。
- `_read_scope_caps`（224-270）签名加 claims，值改为 `min(30, Σ预算)` / `min(393216, 65536×n)`，且**项目层显式配置优先**（保住 263-270 的"缺键才回退"语义 → VC-007/VC-008 字节不变）。
- **顺序修正**：`1492` 的 `_read_scope_caps(project_root)` 必须下移到 `1495 dispatch_card(...)` 之后，否则拿到的是上一版卡的预算。
- `synthesized_card` 路径（777）无 `dispatch_card` → claims 为空 → 退化为旧行为（不写 caps 行，字节不变）。

### 3.3 L3 结算层

- `worker/output-sections.ts`：`parseVerdictTable(text)`（复用 fence/H2 判定器）+ `claimCoverage(claims, table)` 返回 `string[]`。
- `worker/output-writer.ts`：`TerminalGaps` 加 `claimGaps: string[]`（默认 `[]`，保持既有手构对象兼容），`ok` 在 423 追加 `&& claimGaps.length === 0`；`## Questions` 首行（448）追加「未裁决断言：…」。
- `worker/worker-mode.ts`：
  - 解析 task.md 的 claims 块（紧邻 650-657 的 caps 解析，`TaskMeta` 531-534 加 `claims`）。
  - `finishSuccess`：第 6 步 `readTerminalGaps`（3866-3871）已含 claimGaps，第 7 步 `exitCode`（3872）自然折叠，**不新增判定点**（RQ-2 §2.2 明确"之后不能放"的理由：会与 writeOutputGuarded 定稿分叉）。
  - self-check：`settleOrSelfCheck`（3962-4008）把 `currentClaimGaps` 与既有 `currentRecoveryMissing` **分开渲染、共用触发条件**，复用 `selfCheckSent`（3332 / 3994-3995）——不新增状态。
  - 新 trace 行 `[CLAIMS] ts claims=<n> closed=<> partial=<> unverified=<> fetches=<>`：**独立行，绝不扩 `[END]`**（`heartbeat.ts:93` 与 `mw_common.py:2768` 两侧锚定正则会红）。
  - `fetches` 口径写死为 `[FLOW] tool_call` 的读类计数（只含放行），与 `read-scope allowedCalls`（含被拦重试前次数）不同（RQ-2 §3.1）。

### 3.4 L4 度量层

- `run.json` 加 `claims` 子对象（`{total,closed,partial,unverified,fetches,tokens}`，`tokens: null` 表示不可归因）。
- `usage.py`：读 `[CLAIMS]` 行与 `runs.jsonl` 的 `session_id`；`tokens_per_closed_claim = Σtokens / Σclosed`，任一为 0 或不可归因 → `n/a`。
- `status-model.ts`：`KeyRounds` 旁加 `claims` 视图，面板一行 `claims 12/8c/2p/2u`（110 列内）。

## 4. 预算推导（可复算）

```
n        = claims 条数
Σ预算    = Σ(manual ? 2 : 1)            # ≤ 40，否则 G1 拒绝
fileCap  = min(30, Σ预算)                 # 次；硬上限 35 = floor(177856/4977)
byteCap  = min(393216, 65536 × n)         # B；393216 = 6×65536，位于 <400k 安全带内
可用上下文 = 200000 − 16384(reserve) − 5760(起始 prompt) = 177856
预期成本  = 5760 + fileCap × 4854(p90)    # 30 次 = 151k，占窗 76%
```

拆分判定：`n > 5` → 扇出 `k = ceil(n/5)` 个取证单元 + 1 个 merge 单元。

## 5. 门禁与灰度

| 门 | 位置 | advisory | enforce |
|---|---|---|---|
| G1 卡 gate | `ui-bridge.ts:2585` / `dispatch.py:1437-1442` | 回执追加 `[claims]` 告警行 | 进 `missing`，拒绝零副作用 |
| G2 结算 gate | `output-writer.ts:423` + `worker-mode.ts:3872` | `output.md` 追加 `[claims-advisory]` 段 | `exit 2` + 一次性 self-check |
| G3 PM 收敛 | merge 单元 / 覆盖表 | 只提示 | 覆盖表 `unverified > 40%` 时不得 PASS |

`MW_CLAIM_GATE=enforce` 覆盖 `CLAIM_GATE_DEFAULT`（两侧同名同义）；按 key 灰度需要新配置键（21-key 锁代价），留到 P3。

## 6. 错误处理与边界

- 卡无 claims 块 → 全链路跳过，行为逐字节不变（AC-007）。
- claims 块畸形（表头缺失/列不足）→ `claim:<id>:row-shape`；enforce 拒绝，advisory 只告警。
- 产物无 `## 断言裁决` 且卡有 claims → self-check 一次 → `exit 2`（不新增终态、不静默 done）。
- 定位文件在 run 期间被改写导致行号漂移 → 只在声明了 `「excerpt」` 时校验命中，advisory 期只告警（B-3）。
- `symbol` 定位 / 目标在 projectDir 外 → 不可 stat，按 `locator-unresolved` 处理，不抛错。
- trace 缺 `[CLAIMS]` 行（旧 bundle）→ 度量显示 `n/a`，不推断。

## 7. 决策记录

| 编号 | 决策 | 依据 | 状态 |
|---|---|---|---|
| D-001 | 复用 `review`，不新增 `claim-review` 类型 | RQ-2 §4.1：新类型需改 6+ 文件、4 条平价测试必红；claims 与 `type:` 正交 | 采纳 |
| D-002 | claims 块注入 task.md，结算期不回读卡文件 | RQ-2 §2.3：卡可被改写，`card_sha256` 回读成本更高 | 采纳 |
| D-003 | 结算判据挂在 `readTerminalGaps` 内，`exitCode` 之前 | RQ-2 §2.2：放 `taskDone` 之后会与定稿分叉 | 采纳 |
| D-004 | `[CLAIMS]` 独立 trace 行，不扩 `[END]` | 两侧锚定正则（`heartbeat.ts:93`、`mw_common.py:2768`） | 采纳 |
| D-005 | **不给 review 加 `bash`**（已确认）。`cmd` 类断言的执行权在 PM：派发前 PM 执行该命令并把 `verb … => rc=…` 落盘到 `evidence/claims/<run>.md`；卡的 `定位` 列对 `cmd` 类必须是 `evidence/claims/<file>#<claim-id>`，review 单元只读该文件并引用行号 | GC-2；`verifier`/`reviewer` 同为 `_REVIEW_TOOLS` 无 bash 可借；预执行不新增写面也不改工具白名单 | 已确认 |
| D-006 | 灰度：`CLAIM_GATE_DEFAULT = "advisory"` 常量（TS/Python 各一份 + 平价锁）+ `MW_CLAIM_GATE=enforce` 环境变量（全局，两侧同名同义）；per-key 配置键留到 P3 | 避开 21-key 平价锁；先例 `ENVELOPE_ENFORCE_SINCE` | 已确认 |
| D-007 | 预算值取 RQ-1 标定（30 次 / 393,216 B / K=5），否决 spec 初稿与 RQ-2 占位值 | RQ-1 §5；RQ-2 与 RQ-1 并行，其 `min(3n,60)` 是初稿遗留 | 采纳 |
| D-008 | `fetches` 口径 = `[FLOW] tool_call` 读类计数 | RQ-2 §3.1：与 `allowedCalls` 不等价，必须二选一 | 采纳 |
| D-009 | `run.json` 的 `claims` 子对象归 **worker** `recordEnd` 写（不是 launcher） | `launcher.py:990-1003`：“The worker-written run.json is the product”，launcher 只读 | 采纳 |
| D-010 | T-03 实测的 3 条 pytest 红全部归因于另一窗口未提交的 `decision` 类型与冻结基线漂移，不在本 key 修复 | 逐条反证：`REGISTRY` 多出项来自 `git diff` 的 W8 hunk；`baseline_left_end_bound` 只比已提交 blob | 采纳 |
| D-011 | **advisory 零拒绝**：结构性 gap 也不进 `missing`，全进 `warnings`；只有 `enforce` 判 | P-048（schema 过严 → 连续误拒 → 30 分钟零产出）；灰度门禁若仍能拒，表格里一个拼写错误就能丢一次派发。实现：`claimsMissing = enforce ? [...errors, ...audit] : []` | 采纳（纠正 T-02 的“结构性 gap 两模式都拒”偏差） |

## 8. 测试设计

| 层 | 文件 | 用例（最小集） |
|---|---|---|
| L1 解析 | `test/suite/claim-block.test.ts` | 别名/列序/全角/fence 跳过；`C-01.3` 子行规则；同义反复相似度；`cmd: TBD()` 放行 |
| L1 gate | `test/suite/dispatch-claims-gate.test.ts` | 7 种缺失形态各一条（含 `claim:C2:locator`、`claims:budget-sum:48>40`、`manual-overflow`）+ 零副作用断言 |
| L2 PM | `test/suite/dispatch-claims-render.test.ts` | `read_scope`/caps 渲染行序；caps 随 claims 变；无 claims 卡字节不变 |
| L2 Python | `test_claim_dispatch.py` | `dispatch_card` 返回 claims；`_read_scope_caps` 顺序下移；synthesized 路径退化 |
| L3 结算 | `test/suite/claim-coverage.test.ts` | 缺表/缺 id/超集/坏裁决/缺证据/自证证据/struct 吞并；self-check 仅一次；exit 2 |
| L3 反绕过 | `test/suite/claim-bypass.test.ts` | AC-008 六条各一负例 |
| L4 度量 | `test_claim_metrics.py` | `[CLAIMS]` 解析；`tokens_per_closed_claim`；不可归因 → `n/a` |
| 平价 | `test_claim_parity.py` | `CLAIM_TYPES`/`UNVERIFIED_REASONS`/`CLAIM_GATE_DEFAULT`/`CLAIM_BUDGET` 逐字 |

回归红线：T-17 平价锁、`test_mwoc_s2_sections.py`、`dispatch-card-injection.test.ts:344-483`、`triage-dispatch.test.ts:355-357`、`autopilot-read-scope.test.ts:601-625`（零拦截红线）。

## 9. 落地顺序与风险

- P1（L1+L2 只读面）：解析 + gate（advisory 恒真）+ 注入 + caps 渲染。此时无任何拒绝行为，可安全部署。
- P2（L3）：覆盖判据 + `[CLAIMS]` 行 + self-check。
- P3（enforce）：`MW_CLAIM_GATE=enforce` 试点 2 个 key，比对退出码分布（AC-006）。
- P4（L4）：度量与面板。
- 风险：`dist/` 是 tracked 产物（RQ-2 §5.4）→ 实施结束必须 `npm run build` + `/mw restart`，否则运行期不生效（done ≠ 上线）。
- 风险：conductor 的 synthesized 卡无 claims → 大面 L3 复核默认仍走旧路径，收益仅覆盖卡 backed 的派发。
