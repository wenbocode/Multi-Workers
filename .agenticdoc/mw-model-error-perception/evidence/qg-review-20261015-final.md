# QG Review (final): mw-model-error-perception — 前次 ⚠️ 处置核验 + mini-key 独立复核 + 全 key 终态复扫

- 日期：2026-10-15
- 审计卡：`.agenticdoc/mw-model-error-perception/tasks/QG-review-2.md`（sha256 `8cd8d862…`）；执行者 `qg-review-mep-final2`（type: review，只读）
- 模式：**只读 + 读码推演**。未重跑任何测试/门禁（review 角色无 bash），门禁结论引用 `evidence/quality-gate-report-20261015.md`（T-07）与 pm-state Evidence Ledger；**正则等价性为静态读码推演**（不可执行），mini-key 的执行型探针结论引用 mini-spec §Outcome。
- 三态：✅ 通过 / ⚠️ 有条件通过（列欠债）/ ❌ 未通过（列修复项）。
- 本文件是本卡唯一写入物（写面内）。

## 0. 汇总与结论

| Q | 维度 | 判定 | 一句话 |
|---|------|------|--------|
| Q1 | 前次 QG 六项 ⚠️ 处置核验 | ✅ | 6/6 按声明落盘兑现（2 条残余观察，非未兑现） |
| Q2 | mini-key `mw-review-schema-lookaround` 独立复核 | ⚠️ | 等价性成立（差异集恰为「≥3 点全点段」，安全收紧）；防回归断言钉死；2 处文档表述不精确 |
| Q3 | `snapshot()` 适配授权 | ✅ | 保持测试原意、最小、mini-spec 已留痕 |
| Q4 | AC-001~010 终态证据链复扫 | ✅ | **10✅ / 0⚠️ / 0❌**（较前次：AC-002 已由 ⚠️→✅）；2 条覆盖欠债另列 |
| Q5 | dist 生效确认 | ✅ | 三处产物 schema 无 lookaround；生产链 7 个进程（12:53 起）**零 502** |
| Q6 | 写面纪律 | ⚠️ | mini-key/PM 直执改动均在声明面内；无 git 访问，未提交集合为替代证据 |

**结论：⚠️ 有条件通过 —— ✅4 / ⚠️2 / ❌0。** 前次 6 项 ⚠️ 全部兑现、无一项需要回滚；新 mini-key 的根因修复在 源码 / repo bundle / 全局 bundle / 生产链 四层确认生效，且本会话自身即为「同模型预算耗尽 → 备用链降级」的运行期实证；7 条欠债全为文档表述、审计呈现与验证口径类，不影响运行时行为。

## 1. Q1 — 前次 QG 六项 ⚠️ 处置核验（逐项对磁盘实况）

| 前次欠债 | 处置声明（卡面） | 磁盘实况 | 判定 |
|----------|------------------|----------|------|
| D1 spec §2.2 / AC-002 与 design §1/§3.1/§4 未随 D3 回填 | spec 顶部修订索引 + AC-002 回填 run=1；design 顶部修订索引指向 §2 D3 | `spec.md:2` 修订索引逐字存在（含「AC-002 的『连续失败计数』按此读作 run=1」）；`spec.md:76` AC-002 新文本（「本次失败序号——D3 修订后每进程恒为 run=1，跨进程次数由 launcher `[MODEL_RETRY]` 承载」）；`design.md:2` 同型索引。§1/§3.1/§2.2 正文仍为 pre-D3 文本，但已被文首索引显式降级为历史文本（见 O-1） | ✅ |
| D2 phased 面（AC-003/AC-010）无用例 | 待 print-mode 修复 key 补 | `key-decision.md` 裁决 5 明确登记为「验证欠债」（未伪装已覆盖）；代码侧 `worker-mode.ts:3837-3857` 的早退序本会话已复核 | ✅（转后续 key） |
| D3 `autopilot-protocol.test.ts` 改动无授权/无留痕 | key-decision 裁决 4 补记授权 | `key-decision.md`「PM 直执裁决记录」第 4 条存在：同一根因（他窗 4980da301 `mw_run_detached`）、冻结表逐字未动、10/10 + biome clean | ✅ |
| D4 `mwoc-matrix-t07.test.ts` 被本 key `biome --write` 附带格式化 | 裁决 5 归属他窗（csg）实质变更 + 格式化混合 | `key-decision.md` 裁决 5 末句落盘（「经 git diff 核实…归属他窗、本 key 不回退不认领」）。**该 git 核实本审计无法复现**（无 bash）→ O-2 | ✅（附不可复现声明） |
| D5 契约呈现偏差（`[FLOW]` 包裹 + 双时间戳 / `FALLBACK_MODELS/_INDEX` 无消费方 / `attempt=` 槽位序） | 三项登记偏差、接受不处理 | `key-decision.md` 裁决 5 逐项列名并裁定「接受不处理」；本会话在生产 trace 中复核到 `[FLOW] … [MODEL_ERR] …` 双时间戳形态（`workers/qg-review-mep-final2/trace.log:122`），与接受项一致 | ✅（已裁定接受） |
| D6 AC-001 性能上界未实测 | 记为验证欠债 | `key-decision.md` 裁决 5 落盘 | ✅ |

裁决 4 / 裁决 5 其余落点核对：`pm-state.md` §3 Evidence Ledger 含「全量门禁（T-07）」PASS 一条；QG 结论条落在 §7 Process Log（`20:15 QG 审计 … 11✅/6⚠️/0❌`）——内容齐备但未落在 Ledger 节（O-3）；快照区 `Updated: 19:57` 早于 20:15 的 QG 条目（O-4）。

**Q1 判定：✅**（未兑现项 = 0）。

## 2. Q2 — mini-key 独立复核（`mw-review-schema-lookaround`）

### 2.1 等价性读码推演（本审计自构用例矩阵）

两个候选段正则（`WORKER_FILE_EVIDENCE_SEG`，嵌在 `(?:\.agenticdoc/[A-Za-z0-9._-]+/)?evidence/SEG(?:/SEG)*` 内，前缀键段类两边**完全未变**）：

- OLD = `(?!\.{1,2}(?:/|$))[A-Za-z0-9._-]+`
- NEW = `[A-Za-z0-9._-]*[A-Za-z0-9_-][A-Za-z0-9._-]*`（`write-surface.ts:68`）

推演关键（逐条读码，非执行）：负向前瞻 `\.{1,2}(?:/|$)` 只在「段首 1~2 个点后紧跟 `/` 或输入末尾」时失败 ⇒ OLD 的段接受集 = `[A-Za-z0-9._-]+` **减去字面量 {`.`, `..`}**；NEW 的段接受集 = `[A-Za-z0-9._-]+` **减去全部点串**（`.`、`..`、`...` …）。故 **NEW ⊆ OLD**、`NEW \ OLD = ∅`、`OLD \ NEW = {长度 ≥3 的全点段}`（如 `...`、`....`）。因为路径语言是段语言的 `^…(?:/SEG)*$` 组合且两边的段边界（`/`、`$`）与前缀键段类相同，差异只在「某路径的唯一可用解析必须消费一个 ≥3 点全点段」时出现。

| # | 用例（file 值） | OLD | NEW | 一致 | 说明 |
|---|-----------------|-----|-----|------|------|
| 1 | `progress.md` / `report.md` / `report-f1.md` / `report.r1.md` | ✓ | ✓ | ✓ | 走 basename 备选支（未改） |
| 2 | `evidence/research/notes.md` | ✓ | ✓ | ✓ | 多段、合法 |
| 3 | `evidence/a/b/c/d.md` | ✓ | ✓ | ✓ | 深度无界 |
| 4 | `.agenticdoc/k/evidence/x.md` | ✓ | ✓ | ✓ | 项目根前缀（key 段类未改） |
| 5 | `.agenticdoc/mw-model-error-perception/evidence/research/notes.md` | ✓ | ✓ | ✓ | 真实 key 名 |
| 6 | `evidence/.notes.md` | ✓ | ✓ | ✓ | 点前缀、含非点字符 |
| 7 | `evidence/.-x` / `evidence/..a` / `evidence/....a` | ✓ | ✓ | ✓ | 去点后仍有非点字符 |
| 8 | `evidence/-` / `evidence/_` / `evidence/a.b.c` / `evidence/a./b` | ✓ | ✓ | ✓ | 单字符 / 尾点段 |
| 9 | `evidence/.` | ✗ | ✗ | ✓ | 全点段（长度 1） |
| 10 | `evidence/..` | ✗ | ✗ | ✓ | 全点段（长度 2） |
| 11 | `evidence/./x`、`evidence/../x`、`evidence/a/../b` | ✗ | ✗ | ✓ | lookahead 的 `/` 分支拒 |
| 12 | `evidence//x`（空段）、`evidence/x/`（尾随 `/`）、`evidence`（目录本身） | ✗ | ✗ | ✓ | 段至少 1 字符 |
| 13 | `Evidence/x`、`evidence/Evidence/x` | ✗ | ✗ | ✓ | 大小写敏感（无 `i` 标志） |
| 14 | `evidence\..\x`、`evidence/..\x` | ✗ | ✗ | ✓ | 反斜杠不在段字符集内 |
| **15** | **`evidence/...`** | **✓** | **✗** | **✗（唯一差异类）** | OLD 误放行全点段；NEW 正确拒绝（安全收紧） |
| **16** | **`evidence/..../x`**、**`evidence/a/.../b`** | **✓** | **✗** | **✗（同 #15）** | 同上 |
| 17 | `.agenticdoc/../evidence/x` | ✓ | ✓ | ✓ | 前缀键段类未变 ⇒ 两边都放行；运行时 `judgeWriteTarget` 归一化后不在 evidence 面内 ⇒ 仍 fail-closed（旧既有属性，未变） |

结论：**`NEW ⊆ OLD` 且丢失的合法路径 = 0**；唯一差异是 #15/#16 的退化段类（旧放行 → 新拒绝）。该差异在 mini-spec 同句已声明（「全点串不可匹配」+ Outcome「旧正则误放行全点段」），属**刻意收紧**，且收紧面只在 schema 预过滤层（见 2.3）⇒ 无功能回退风险。**等价性声明成立**（「逐字符等价」应读作「在合法/白名单路径上等价」）。

### 2.2 防回归断言与 CHANGELOG

- `agent-team-loop-worker-file-tool.test.ts:43` `LOOKAROUND_RE = /\(\?[=!<]/` 覆盖全部四种环视（`(?=`/`(?!`/`(?<=`/`(?<!` 均以 `(?[=!<]` 命中）；`:344` 先钉 `pattern === WORKER_FILE_PATH_RE.source`（非空），`:348`/`:349` 再断言 schema pattern 与 regex source 均不含环视 ⇒ **钉死有效，且非空洞断言**（若 pattern 缺失，`:344` 先失败，不会静默通过）。**无 lookaround 的 schema 属单一工具面**：全仓 `pattern:` 检索仅 `worker-file-tool.ts:151` 一处携带 JSON-schema `pattern`（`core/tools/find.ts:29-36` 的 `pattern` 是普通字符串参数）⇒ 502 类缺陷在工具面已闭合。
- `coding-agent/CHANGELOG.md:103`（[Unreleased] ### Fixed）成稿与实现相符：根因（`WORKER_FILE_PATH_RE.source` 内嵌带负向前瞻的 evidence 段）、现象（Azure `invalid_json_schema: regex lookaround is not supported`，首个 LLM 调用 502、零工具调用）、修法（段需 ≥1 非点字符）、防回归断言、快照过滤。**唯一措辞不精确**：`identical semantics` 未点明 #15 的收紧（O-5）。

### 2.3 mini-spec 声明核对（含 1 处不精确）

| mini-spec 声明 | 实况 | 判定 |
|----------------|------|------|
| Change 1「该常量同时供**运行时校验**与 schema pattern，一处改两生效」 | `WORKER_FILE_PATH_RE` 的仓库内消费点仅 `worker-file-tool.ts:151`（工具 schema `pattern`）；运行时判定走 `judgeWriteTarget` + `isAllowedWorkerFileName`，**不使用该正则**（`write-surface.ts:72/75`、`worker-file-tool.ts:105`） | ⚠️ 表述不精确（O-6）：实际影响面比声明**更小**（纯 schema 层收紧），反而强化「无运行时回归」结论 |
| Change 2 防回归断言 | 见 2.2 | ✅ |
| Change 3 CHANGELOG | 见 2.2 | ✅（措辞 see O-5） |
| AC-1 等价性探针 22/22 | 本审计以 17 行矩阵读码复推，结论一致（差异集恰为 #15/#16）；执行型探针不可复跑（无 bash） | ✅（本审计侧为读码推演） |
| AC-3「套件 9/9 全绿 + 8 套件 196 passed + 1 既有失败（mwds-t02 漂移）」 | 无法复跑；`worker-file-tool` 套件确为 9 个 `it`（5 个 describe）；mwds-t02 漂移按卡面豁免 | ✅（引用） |
| Outcome「旧常量下该套件 3 failed，新常量 2 failed」 vs AC-3「1 既有失败」 | 两处计数未给出各自命令/时点，字面不可对齐 | ⚠️ 报告口径不闭合（O-7），不影响结论 |

**Q2 判定：⚠️**（等价性成立、断言与 CHANGELOG 主体准确；2 处表述不精确 + 1 处计数不闭合，均为呈现类）。

## 3. Q3 — `snapshot()` 适配授权核验

- 改动实况：`agent-team-loop-worker-file-tool.test.ts:124-130` 单一 helper 内加白名单过滤（`.filter((f) => isAllowedWorkerFile(f))`），全部 12 处调用点共用同一 helper ⇒ 无散布改动、无断言放宽。
- **保持测试原意**：过滤谓词 = `WORKER_FILE_NAME_RE`（`progress.md`/`report.md`/`report-<slug>.md`）。而 `worker_file` **能写进任务目录**的名字集合恰为此白名单（`worker-file-tool.ts:105` 对非 evidence 面强制 basename 白名单；evidence 面落盘在 `<key>/evidence/**`，不进任务目录）⇒ 过滤后剩下的正是「worker_file 写出的文件」，仍是 `toEqual([...])` 的**精确集合**断言（多一个白名单文件仍会失败），未把断言退化成长度/包含式。
- **最小性**：1 个 helper、5 行；未动冻结表、未动 12 例拒绝矩阵、未动 schema 单源断言。
- **留痕**：mini-spec §Outcome 明确「附带 PM 直执：`snapshot()` 按 D-102 白名单过滤（他窗 progress-persist 提交 6e8ed174d 使 task 目录新增 trace.log，裸 readdir 快照被污染——同 VC-007 类基线适配，留痕本节）」；该测试文件亦在 mini-spec 的 `## Files（写入允许面）` 内。`key-decision.md` 未记该条，但卡面口径为「mini-spec/**key-decision**」（二者其一即可）⇒ 满足。
- 与门禁记录一致：T-07 §2.2 曾记该套件 2 条「沙箱内多出 trace.log」的基线失败，本次过滤即其收口；`worker-file-tool` 9/9 为 mini-spec 所报。

**Q3 判定：✅。**

## 4. Q4 — 全 key 终态证据链复扫（修订后 AC-001~010）

> 标注 `[复核]` = 本会话读码/读证据第一手确认；`[引用]` = 引用 T-07 / 前次 QG / mini-spec（本审计不重跑）。行号为当前工作树。

| AC | 判定 | 证据（实现锚点 / 测试用例 / 运行期） |
|----|------|--------------------------------------|
| AC-001 | ✅ | `worker-mode.ts:3799-3825` `modelExhaustedExit`（同步落盘 → `recordEnd(3)` → `recordEnd`→`process.exit(3)`）、`:3837-3857` 首个 error settle 直接退出（无 worker 预算、无重发）；`launcher.py:789-843`（同模型预算，`_MODEL_RETRY_RE:481` 行数推导、重启安全）、`:845-875`（链推进）；测试 `TestSameModelRetry::test_first_exit3_retries_the_same_model` / `test_budget_zero_goes_straight_to_the_chain` / `test_total_attempts_are_bounded_by_budget_and_chain`、`TestPollReapIntegration::test_exit3_redispatches_without_draining_the_pending_queue`；**运行期新证据**：同模型预算 2 次（`[MODEL_RETRY] attempt=1/2`）后 `[MODEL_FALLBACK] attempt=1` 进备链，4 进程链 13:21:06→13:40:22 = **19m16s**，全程 < 60m 墙 [复核]。快败/静默挂起两类的「<2min / ~11min」仍为结构推导（欠债 D-3） |
| AC-002 | ✅ | 新文本 `spec.md:76`（run=1 + launcher `[MODEL_RETRY]` 承载跨进程次数）；实现 `worker-mode.ts:3841-3852`（`appendTrace` + `run=1` 字面量）、`:4053-4059` 截断 200 + 省略号；`[IDLE_KILL] last_model_error=yes|no` `:2453`；**运行期**：`trace.log:122/300/467` = `[FLOW] <iso> [MODEL_ERR] <iso> model=timi/gpt-6.1-sol run=1 err=stream closed before response.completed`，三个独立进程均 `run=1` [复核]；测试 `exits 3 on the first error settle…`、`no in-flight tool + a last model error…`、`a genuinely hung in-flight tool…` |
| AC-003 | ✅ | `worker-mode.ts:3822`(`if (taskDone) return`)→`:3834-3857` error 分支位于 `initialSettled`/phase 推进/`settleOrSelfCheck` **之前**并 `return`（本会话按行序复核）；`:3813` 注释「Never reaches `finishSuccess` (AC-003)」；测试反向断言（无 `## Verification Steps`、Exit Reason 不含 `Agent settled`）；运行期：exit 3 终局均为 `failed`，无伪 done [复核]。phased 面仅代码序 + spec §4 越界声明（欠债 D-2） |
| AC-004 | ✅ | `worker-mode.ts:3819` `formatModelUnavailableReason(modelErrChain(), lastError)`（`:3790` 每模型 `runs: 1`）、`output-writer.ts:532-541`（exit 3 分支 Exit Reason 直出）；`pm-orchestrator.ts:680` 前缀常量、`:1698-1708` 零改动回读；**运行期**：`workers/qg-review-mep-final2/output.md` 的 `## Exit Reason` = `model unavailable: tried=timi/gpt-6.1-sol(1) last=stream closed before response.completed | 缺失段：…` [复核]；测试 `exits 3 …` / `renders the launcher-seeded TRIED chain …` |
| AC-005 | ✅ | `worker-mode.ts:3080`（成功边界置 `sawSuccessfulAssistant` 并清 `lastErrorInfo`）、`:3837`（仅 `lastErrorInfo !== undefined` 触发）、`:3854`（consume 置 undefined，防二次计数）；测试 `settles done without exit 3 when an error is followed by a success`（0 行 `[MODEL_ERR]`、`status=done`、无 `model_exhausted`）；跨进程侧由 `TestSameModelRetry` 覆盖 |
| AC-006 | ✅ | `pm-orchestrator.ts:682`(`K=2`)、`:686-706`(`runModelExhausted` 读失败降级 false)、`:708-715`(`isModelErrorTerminal` 双源 OR)、`:718-729`(bump/clear)、`:731-749`(`recordDispatchAlarm(kind="model-error")`)、`:1563-1567`+`:1698-1708` 轮询终态插桩；`:547-549`/`:601-604` 渲染为「提示」非「拒绝」；测试 PM 4 用例（含清零、文案、坏记录不抛）。语义说明：仅在**终态行**评估 ⇒ 链未耗尽的中途 exit 3 不计 streak，与 AC 字面（「以 model-unavailable **终结**」）一致 |
| AC-007 | ✅ | `test/suite/worker-model-error-perception.test.ts` 13 用例（5 describe：管线级 2 / 抖动 1 / 时序级 3 / PM 4 / 纯函数 3）[复核用例名]；T-07 §1：单跑 13/13、三套件 28/28、`npm run check` 子步骤 exit 0、`./test.sh` coding-agent 76 failed = AGENTS.md 基线 76（新增 0）[引用] |
| AC-008 | ✅ | `mw_common.py:365-438`（校验：task type/去重/上限 4/`*_cli` 拒绝）、`:440-465`（读软失败）、`:468+`（type→role 桶）；`launcher.py:556-585` `inject_fallback_env`、`:789-843` 同模型预算、`:845-875` 链推进（`--model` + INDEX + TRIED，`_spawn:2381-2420`）、`:2177-2183` reap 拦截；测试 `TestFallbackChain` 6 + `TestPollReapIntegration::test_chain_exhausted_lands_failed` / `test_no_fallback_exhausted_lands_failed` / `test_exit3_without_run_confirmation_lands_failed`；**运行期**：`.mw/dispatch.yml:8-10` `fallback_models.review=[timi/deepseek-v4.1-flash]` 生效（13:40 的降级即其首次实战）[复核] |
| AC-009 | ✅ | `launcher.py:829-832`(`[MODEL_RETRY]`)、`:853-856`(`[MODEL_FALLBACK-SKIP]`，`candidate=` 与主正则不互配)、`:858-862`(`[MODEL_FALLBACK] from= to= attempt=`)、`:749-774`(预校验跳过)、`:652-665`+`:807`(双确认)、`:429` 注释即「不用 `setModel` 写全局 settings」的证据；测试 `TestFallbackEnvInjection` 7 + `TestSameModelRetry::test_same_model_retry_keeps_the_model_flag`；**运行期**：`trace.log:124` `[MODEL_RETRY] … attempt=1`、`:302` `attempt=2`、`:469` `[MODEL_FALLBACK] … from=timi/gpt-6.1-sol to=timi/deepseek-v4.1-flash attempt=1`、`:472` `[MODEL] … model=deepseek-v4.1-flash`（本审计进程）[复核] |
| AC-010 | ✅ | `worker-mode.ts:3806-3813`（summary/phase 进度，`phases=-` 或 `k/N`）、`:3817`(`collectArtifacts`)、`output-writer.ts:535-541`（exit 3 亦渲染 `## Deliverables`；**仅当过滤后非空**，且排除 `output.md`/`progress.md`——本会话按行复核）；测试 `exits 3 …`（Summary `partial step done` + Deliverables `phase-1.md`）；output.md 追加型（多 run 累积，不重置）。运行期 3 次 exit 3 的产物中无 Deliverables 节，与「该进程未产出可计工件」一致 [复核] |

**Q4 判定：✅（10✅ / 0⚠️ / 0❌）**，较前次 QG 的 9✅+1⚠️ 收敛（AC-002 已回填）。

### 4.1 覆盖缺口（沿用/新增欠债，非 AC 判定失败）

| ID | 缺口 | 现状证据 | 动作 |
|----|------|----------|------|
| D-2 | 带 phases 任务书的 AC-003/AC-010 无自动化用例（`phases=k/N` 亦仅 `phases=-` 断言） | 代码序 + spec §4 print-mode 冻结越界声明 | 待 print-mode 修复 key 补（前次 D2 转移，未恶化） |
| D-3 | AC-001「<2min（快败）/ ~11min（挂起）」未实测 | 结构推导 + 新增一条 4 进程链 19m16s 运行期实例（<60m 墙） | 运行期观察项，不阻塞 |

## 5. Q5 — dist 生效确认（含生产链负/正例）

| 检查 | 结果 | 证据 |
|------|------|------|
| `packages/coding-agent/dist/.../write-surface.js` 的**工具 schema** 无环视 | ✅ | `dist/…/write-surface.js:63` `WORKER_FILE_EVIDENCE_SEG = "[A-Za-z0-9._-]*[A-Za-z0-9_-][A-Za-z0-9._-]*"`、`:64` ALT、`:66` PATH_RE；仅余两处环视属**预期无害**：`:61-62` 注释文本（说明旧 guard）、`:121` `classifyWriteTargetShape` 的 `(?![\\/])`（运行时 JS 正则，不进 tool schema）[复核] |
| repo bundle（运行期实际加载） | ✅ | `packages/multi-workers/dist/extensions/agent-team-loop.js:17161-17163` 同新常量；schema 组装点 `:19116 pattern: WORKER_FILE_PATH_RE.source` [复核] |
| **全局** bundle（`~/.pi/agent/extensions/agent-team-loop.js`） | ✅ | 同文件 `:17161` 新常量、`:19116` 引用（`mw_common.global_ext_dir()` = `~/.pi/agent/extensions`）[复核] |
| 运行期正/负例 | ✅ | **负例（修复前）**：`workers/qg-review-mep/worker.log:3` = `502 … "Invalid JSON schema: regex lookaround is not supported. Found at $.properties.file.pattern."`，`trace.log:1-6` 12:04:35 起跑 → 12:05:49 `exit=2 tools=0`。**正例（修复后）**：`qg-review-mep-final`(3) + `qg-review-mep-final2`(4) 共 7 个进程自 12:53 起**零 502**，全部通过 schema 校验进入流式（失败原因变为 `stream closed before response.completed`，属模型侧流断，与 schema 无关）[复核] |
| 本轮自我验证 | 本次派发**未**出现 `invalid_json_schema` 502 ⇒ 卡面「若仍 502 即 dist 路径未刷新」的判定分支未触发；本会话 → `[MODEL] 2026-10-15T13:40:22.811Z model=deepseek-v4.1-flash`（即被降级派发，属卡面预期） | ✅ |

**Q5 判定：✅。**

## 6. Q6 — 写面纪律（mini-key + PM 直执）

| 改动 | 声明写入面 | 实况 | 判定 |
|------|-----------|------|------|
| `src/extensions/agent-team-loop/shared/write-surface.ts`（段常量改为无环视；注释） | mini-spec `## Files` | `:66-72` 与声明一致 | ✅ |
| `test/extensions/agent-team-loop-worker-file-tool.test.ts`（`LOOKAROUND_RE` + 快照过滤） | mini-spec `## Files` | `:43`、`:124-130`、`:344-349` | ✅ |
| `packages/coding-agent/CHANGELOG.md` | mini-spec `## Files` | `:103` 一条 Fixed | ✅ |
| `dist/**` + repo/global bundle | mini-spec `## Out of Scope`（`npm run build` 用户执行） | 用户以 `mw build --install --allow-dirty` 重建（卡面声明）；三处产物内容已核（§5） | ✅（操作者动作，非 mini-key 写面） |
| 主 key 处置文档（`spec.md:2/76`、`design.md:2`、`key-decision.md` 裁决 4/5、`pm-state.md` 两条） | 前次 QG D1 归属「PM（文档，非本卡写面）」 | 均为 PM 自有 key 文档面 | ✅ |
| `.agenticdoc/mw-review-schema-lookaround/mini-spec.md` | mini 快速通道要求的留痕文件（`references/pm-mind.md:136`、`core/pm-mind.md:429-432`） | 存在且含 Mode/Files/AC/Outcome；mini 通道不要求 `_index` 登记，`_index.md`/`_index.parallel` 无该 slug 属预期（O-8） | ✅ |

**限制**：本审计**无 git 访问**（review 角色无 bash），无法给出 `git status --porcelain` 级未提交清单与其对照。替代证据：`.mw/mw.log:330` 的 code identity `commit=bf2547cce… dirty=48/52`（2026-10-15T11:04:04Z，`packages/multi-workers` tree）证明树上**先于本会话即已脏**，且**无任何 in-session 证据显示越面文件**（键目录、task 目录、evidence 目录的全量遍历中未出现声明的三文件之外的本 key 产物）。

**风险登记（非本 key 修复项）**：`--allow-dirty` 重建会把**他窗未提交的 TS** 一并编进 tracked `packages/coding-agent/dist/**` 与 repo/global bundle（脏树护栏的 R1），使 dist 的 diff 无法单独归因本 key；操作者显式选择，且 §5 已用产物内容独立验证本 key 部分。

**Q6 判定：⚠️**（声明面内合规；git 级清单缺失，以替代证据 + 限制声明收口）。

## 7. 运行期新证据（本会话派发链，前次 QG 未观测到）

| 时点 | 事件 | 证据 |
|------|------|------|
| 12:04:35→12:05:49 | `qg-review-mep` 首个 LLM 调用 502（lookaround），`exit=2 tools=0` | `workers/qg-review-mep/{worker,trace}.log` |
| 12:53:43→13:19:11 | `qg-review-mep-final`：3 进程全部 `stream closed` → 同模型预算消費 `[MODEL_RETRY] attempt=1/2` → 无备用配置 ⇒ 终态 failed | 该目录 `trace.log:1-425` |
| 13:19 后 | `.mw/dispatch.yml` 新增 `fallback_models.review`（注释即记「首个实战配置」） | `dispatch.yml:7-10` |
| 13:21:06→13:40:22 | `qg-review-mep-final2`：新 task_key ⇒ 预算重启归零 → 2 次同模型重试 → `[MODEL_FALLBACK] to=timi/deepseek-v4.1-flash attempt=1` → 本进程在备链上运行 | `trace.log:3-472`、`output.md` 3 段 `status=failed` |
| 13:40:22→ | **本审计进程运行于降级模型**（deepseek-v4.1-flash），schema 校验通过 | `trace.log:472`、`run.json` |

结论：exit 3 → 同模型预算（trace 推导、重启安全）→ 备用链推进 → `failed` 的**完整终止语义在生产链上首次跑通**；且 3 次 exit 3 的 output.md 均为 `model unavailable: …`（AC-004）+ `缺失段` 恢复提示，无伪 done（AC-003）。

## 8. 欠债 / 修复清单

| ID | 级别 | 内容 | 影响 | 建议动作 | 归属 |
|----|------|------|------|----------|------|
| O-1 | 低 | design §4 协议表仍无 `[MODEL_RETRY]` / `[MODEL_FALLBACK-SKIP]` 行；§1/§3.1/§3.2 正文仍 pre-D3（靠文首索引降级） | 只读 §3.1 实现者仍可能照旧写 followUp 重发（索引已显著提示） | 下次文档收口时在 §4 补两行、或把索引升为「本节作废」块 | PM（文档） |
| O-2 | 低 | D4 归属（`mwoc-matrix-t07.test.ts` 系他窗实质变更）依赖 PM 的 git diff 核实，本审计不可复现 | 归属存疑时可能误认领他窗改动 | 由 owner key（csg / mw-output-contract）在提交前自查 | PM |
| O-3 | 低 | QG 结论条落在 `pm-state.md` §7 Process Log 而非 §3 Evidence Ledger | 与卡面「Evidence Ledger 两条」表述不符（内容齐） | 移行或改卡面口径 | PM |
| O-4 | 低 | `pm-state.md` 快照 `Updated: 19:57` 早于 20:15 的 QG 条目 | 时间线不自洽 | 追加条目时刷新快照 | PM |
| O-5 | 低 | CHANGELOG `:103` `identical semantics` 未含 #15 的收紧（≥3 点全点段由放行→拒绝） | 措辞过宽，行为无差 | 补半句「dot-only segments now rejected at any length」 | PM |
| O-6 | 低 | mini-spec Change 1「该常量同时供运行时校验与 schema pattern」不成立（运行时走 `judgeWriteTarget`） | 表述不精确（实际影响面更小） | 改为「仅 schema 预过滤层」 | PM |
| O-7 | 低 | mini-spec Outcome「3 failed → 2 failed」与 AC-3「1 既有失败」计数不对齐 | 报告不可复算 | 附对应命令/时点 | PM |
| O-8 | 低 | mini-key 未登记进 `_index.md`，仅经 QG 卡可发现（mini 通道规则允许） | 可追溯性弱 | 如希望可检索，可在主 key `key-decision` 记一行指向该 mini-spec | PM（可选） |
| D-2 | 验证 | phased 面 AC-003/AC-010 无用例 | 回归仅靠代码序读审 | 待 print-mode 修复 key 补 | 后续 key |
| D-3 | 验证 | AC-001 快败/挂起性能上界未实测 | 指标为结构推导 | 运行期观察项（已有 19m16s 链实例） | 用户/PM |

**未通过项（❌）修复清单：无。**

## 9. 残留与未验证

- R-1：未重跑任何测试/门禁（review 角色无 bash，且卡面审计边界明示）；「13/13、70/70、28/28、新增失败 0」为引用 T-07 + pm-state，非本审计复现。
- R-2：正则等价性为**读码推演**（17 行矩阵），非执行；mini-spec 的 22/22 探针结果不可复跑。
- R-3：无 git 访问 ⇒ Q6 无法产出 `git status` 级未提交清单；O-2 的归属结论不可复现。
- R-4：`/mw restart` 后 serve 侧 Python 行为的运行期验证按卡面越界（仅 T-07 说明 + 本会话 13:21 起的 launcher 行为反证其已生效）。
- R-5：PM 告警（AC-006）端到端回路（真实终态 → streak → 告警渲染）仍只有纯函数 + 插桩点 + 本会话的终态行证据，未见真实告警渲染实例。
- R-6：mwds-t02 语料回放的既有失败（本会话新派发卡片致命中集漂移）按卡面已知漂移豁免，未复核 A/B。
- R-7：硬崩（无 `agent_end`）路径、print-mode phased 冻结缺陷本身按 spec §4 越界，未覆盖。

## 10. 上下文来源

- `.agenticdoc/goal.md`（GC-1/GC-2/GC-3）；`tasks/QG-review-2.md`（本卡）、`tasks/QG-review.md`（qg-review-mep-2 卡）
- `.agenticdoc/mw-model-error-perception/{spec,design,key-decision,pm-state,achieved}.md`、`evidence/qg-review-20261015.md`、`evidence/quality-gate-report-20261015.md`
- `.agenticdoc/mw-review-schema-lookaround/mini-spec.md`
- 代码：`packages/coding-agent/src/extensions/agent-team-loop/{shared/write-surface.ts,worker/worker-file-tool.ts,worker/worker-mode.ts,worker/output-writer.ts,pm/pm-orchestrator.ts}`、`core/tools/find.ts`
- 测试：`test/extensions/agent-team-loop-worker-file-tool.test.ts`、`test/suite/worker-model-error-perception.test.ts`、`packages/multi-workers/{test_mep_fallback_config.py,test_mep_launcher_redispatch.py}`
- 产物：`packages/coding-agent/dist/extensions/agent-team-loop/shared/write-surface.js`、`packages/multi-workers/dist/extensions/agent-team-loop.js`、`~/.pi/agent/extensions/agent-team-loop.js`
- 运行期：`.agenticdoc/mw-model-error-perception/workers/{qg-review-mep,qg-review-mep-final,qg-review-mep-final2}/{trace.log,worker.log,output.md,run.json}`、`.mw/dispatch.yml`、`.mw/mw.log`、`.agenticdoc/_workers.parallel`、`_index.parallel`
- 规范：`AGENTS.md`、`.agents/skills/agentic-task/references/pm-mind.md`（mini 快速通道）

## 11. 未覆盖面声明（审计边界）

- 未重跑任何测试/门禁命令；一切测试结论为只读引用。
- 不审计其他并行 key（csg 等）的未提交改动；mwds-t02 语料回放失败按已知漂移豁免。
- 不覆盖 `/mw restart` 后 serve 侧 Python 行为的运行时验证（launcher 重试链进程级生效由 12:53 起的运行期 trace 间接反证，非本审计实测）。
- 本审计运行在新的 dist/全局 bundle 上；本轮派发未出现 `invalid_json_schema` 502，故「dist/全局 bundle 未刷新」分支未触发。
- 不覆盖 print-mode phased 冻结缺陷、硬崩无 `agent_end` 路径、conductor `_l3_stream_aborted` 泛化（spec §4 越界项）。
