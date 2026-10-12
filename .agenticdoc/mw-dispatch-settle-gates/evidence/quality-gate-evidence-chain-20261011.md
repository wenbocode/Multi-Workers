# 质量门独立审计报告 — mds-qg-a-evidence-chain（证据链审计）

- key: `mw-dispatch-settle-gates`｜phase: VERIFY｜审计角色: 独立 review worker（read-only: read/find/grep/ls，**无 bash**）
- 审计对象: 本 key 12 张卡的 `report.md`、`evidence/runs/t12-consolidation.md`、`evidence/scripts/mwds-controls.ps1`、上一 key 的 `evidence-requirement.md`（T-11 交付物），以及冻结面源码
- 方法: 不采信任何自述；每条结论落到 `文件:行号` 的原文核对。凡需运行才能判定的事项一律标「未核（无 bash）」。
- 审计日期: 2026-10-11（工作区 = PM 修复 `worker-mode.ts:905` 之后的冻结面）

## ① 结论表

| # | 审计项 | 三态 | 一句话依据 |
|---|---|---|---|
| 1 | [VERIFY] 行锚是否真实 | **✅ 已核实**（含 1 处 ⚠️ 子项，见 ⑤-1） | 抽查 40+ 条锚点，覆盖 T-01…T-12 共 10 张实现卡的报告锚点 + 测试文件内锚点，逐一翻到源文件核对**全部落地**；Python 侧 12 条锚点零漂移；TS 侧漂移全部与 T-12 §6 重锚表一致；唯一精度缺口 = T-04 的 alarm 调用点锚 `worker-mode.ts:1906` 现为 `:1928`，未被 T-12 重锚范围 `:1891-1918` 覆盖（符号级仍可 grep 复算） |
| 2 | AC 覆盖完整性 | **✅ 已核实** | spec §3 共 11 行 AC（AC-001…AC-010 + AC-005b）；design §3 表 11 行落点行与 plan §3 卡表、各卡 report 头的 AC/VC 声明三方一致；46 个 VC（VC-001…VC-046，区间 3+5+3+3+5+5+6+3+6+3+4=46）无重叠、无空洞地落到 12 张卡，每张卡的 [VERIFY] 行实测存在（逐卡 grep 计数，见 ②-0）。**缺口：无** |
| 3 | AC-009 证据纪律 | **⚠️ 部分可疑** | 卡片层三要件（[VERIFY] 带锚点 / 引用重锚 / 非空洞对照）结构齐全且抽查成立（31 个控制组在 `mwds-controls.ps1` 中逐行实存，A=11/B=10/C=10 与自报一致）；但上一 key 的 `evidence-requirement.md`（本 key T-11 的 VC-038 交付物）抽查 8 行中 **5 行的「结果列」引号内 `[VERIFY]` 机器行是 design §7 的声明串、并非所引 evidence 文件的实测原文**，其中 VC-019 最重：引号值 `keys=3 single_key_cases=3 corpus_refrozen=true` 全仓只出现在 design.md:570，从未被任何实测输出打印（见 ⑤-2）。无「不适用」占位敷衍（47 行全部有判据与坐标，VC-011/017/018 行如实带 ⚠️ 边界注） |
| 4 | AC-008 六处勘误真落地 | **✅ 已核实** | 六处逐一翻到上一 key 原文：①spec.md:138 AC-021 已改「截断至 N」、旧串「拒绝该轮全部派发」全文件 0 命中；②spec.md:91 §2.3 带「以 AC-025⑤ 为准 / no_anchor」例外；③plan.md:120 `dispatch_max_per_scan`（1..64）、`1..50` 0 命中；④design.md:9 `ac_count = 25`、§8 表含 AC-021…AC-025 行（:607-608）；⑤`evidence-requirement.md` 实存且 47 行（VC-001…VC-047 逐行 grep 计数）；⑥T-18/19/20 卡头 VC 行与 T-11 diff 逐字一致、pm-state.md:133 记 1407 且带勘误注。⚠️ 附注: 上一 key plan.md:117 仍留「超限拒绝 + 告警」旧措辞（与截断口径的字面张力，同类残留未被 T-11 残留清单覆盖，见 ⑤-3） |
| 5 | T-12 PARTIAL 缺口与 PM 修复一致性 | **✅ 已核实** | 读 `worker-mode.ts:905` 现文 = `if (previous?.startsWith("-")) continue;`（与 D-042 修复描述逐字一致）；pm-state.md **D-042** 完整记录：自报 rc=1 → PM 直执该 1 行修复 → 亲跑 `npm run check` rc=0 → 新 sha256 `abbba40b…` → 重跑 9 套件 304 passed。T-12 自报（report §6 + evidence §4.3/§7 R1：`worker-mode.ts:905:10 lint/complexity/useOptionalChain`、unsafe fix、不改 src 而停下报告）与 PM 记录互相咬合，无矛盾 |
| 6 | 诚实性反查（自报偏差是否被覆盖） | **✅ 已核实** | 逐卡收集自报偏差/残留/未核段共 18 项，全部有下落：R-T02-1 断言脆性 → D-031 → T-12 §5.1 实改（测试文件内 `KNOWN_TRUE_POSITIVE_TASKS` 实存、旧 `toBeLessThanOrEqual` 0 命中）；T-04 判据更正 → D-033（spec §3.1 与 design §4.4 均带 `[REVISED @ 2026-10-11]`，均已翻到原文）；T-05 四处偏差 → D-036 逐条裁定；T-11 design §11.2 张力 → D-028 修复（design.md:699 现为「告警 dispatch-quota + **return（截断）**」，`abort(告警 dispatch-quota)` 0 命中）；T-09 瞬态红 → D-023 登记 + T-12 冻结面全量兜底；T-12 PARTIAL → D-042。**未发现静默略过**。2 处披露未升格为 PM 裁定（见 ⑤-4） |

**总评: 无 ❌ 证伪项。** 12 张卡的证据链主体成立：[VERIFY] 行实测存在且锚点落地、AC/VC 映射完备、六处勘误落地、T-12 的诚实上报与 PM 修复闭环。两处 ⚠️ 均集中于「上一 key 补建产物 `evidence-requirement.md` 的结果列 verbatim 性」与「个别行号锚精度」，不触及本 key 12 卡的判定本体。

## ② 每条核实的原始锚点（`文件:行号` + 读到的原文片段）

### ②-0 [VERIFY] 行逐卡实测计数（T-12 自报 81/81）

对 T-01…T-11 的 11 份 `report.md` 逐文件 grep `^\s*(\*\*)?\[VERIFY\]`，计数: T-01=9、T-02=15、T-03=5、T-04=5、T-05=4、T-06=4、T-07=1、T-08=9（其中 1 行是「`[VERIFY] 行（-s 输出…）`」标题行，非数据行）、T-09=18、T-10=6、T-11=6。数据行合计 = **81**，与 `[VERIFY] VC-040: verify_lines_anchored=81/81` 一致。全部 81 行带键=值；抽读的每行均带测试名或 `文件:行号` 锚点节。11 个新测试文件（7 TS + 4 Python）全部实存（find 核实）。

### ②-1 T-01（AC-003 / ui-bridge.ts）

| 报告引用 | 实读结果 |
|---|---|
| `ui-bridge.ts:229` `CROSS_KEY_READ_ONLY_SURFACES`（T-12 重锚 `:231`） | ✅ `:231` = `export const CROSS_KEY_READ_ONLY_SURFACES = ["dispatch_worker", "/worker", "advance_phase"] as const;`（3 项，与 VC-011 `declared_surfaces=3` 一致） |
| 三个调用点 `:1386/:1753/:1847`（T-12 重锚 `:1677/:2086/:2188`） | ✅ `:1677` `const refusal = foreignLiveClaimRefusal(indexStore, ownerKey);`（dispatch_worker）、`:2086`（advance_phase）、`:2188`（/worker）三处全中 |
| `:245` 放行分支（重锚 `:247`） | ✅ `:247` 起 `foreignLiveClaimRefusal` 定义；`:250-251` `_scratch`/下划线/点前缀 `return null`（VC-010 三放行路径）、`:253` `findByKey(...)?.claimId.trim() ?? ""`（B 组对照的逆改目标行实存）、`:258` 拒绝文案由 `CROSS_KEY_READ_ONLY_SURFACES.join(", ")` 渲染 + `switch_key` 下一步（AC-003 判据逐字） |
| 测试锚 `mwds-t01-worker-guard.test.ts:183/:204` | ✅ `:183` = `it("refuses another window's live key with zero side effects…`；`:204` = `` `[VERIFY] VC-009: refused=${…} side_effects=… taskdir_created=… queued=…` ``（打印行实存） |

### ②-2 T-02（AC-005a / ui-bridge.ts）

| 报告引用 | 实读结果 |
|---|---|
| `collectWriteIntentHits = ui-bridge.ts:1398`（重锚 `:1392`） | ✅ `:1392` `export function collectWriteIntentHits(text: string): WriteIntentHit[] {` |
| `isWhitelistedWriteTarget = :1429`（重锚 `:1423`） | ✅ `:1423` `export function isWhitelistedWriteTarget(pathToken: string, ctx: …)` |
| `judgeWriteIntent = :1453`（重锚 `:1444`） | ✅ `:1444` `export function judgeWriteIntent(input: {`（`:1452/:1456` 内部调 hits + 白名单过滤，与报告描述一致） |
| `WRITE_INTENT_GUARDS = :1284`（重锚 `:1287`） | ✅ `:1287` `export const WRITE_INTENT_GUARDS: readonly string[] = [` |
| `applyWriteSurfaceContract = :1513`（重锚 `:1504`） | ✅ `:1504` `export function applyWriteSurfaceContract(taskMdText: string, type: string, writeScope: string | undefined): string {` |
| `renderDefaultWriteScope = :1485` | ✅ `:1476` `export function renderDefaultWriteScope(ownerKey: string, taskKey: string): string {`（-9 漂移，与 T-12 表对 ui-bridge 的 -9 系列一致） |
| 两个守卫入口在写盘之前 | ✅ `/worker` 侧 `:2188` cross-key 守卫 → `:2200` `judgeWriteIntent` → `:2243` `writeDispatchTaskMd`（判定在写盘前）；`dispatch_worker` 侧 `:1744` judge → `:1786` write |
| C1 seam 生产端 | ✅ `:1794`/`:2251` `writelessRole && isShellRole(typeField) ? renderDefaultWriteScope(...) : undefined`（write_scope 只对 research 型注入） |
| T-12 §5.1 断言改写（PM 扩展） | ✅ `mwds-t02-write-intent.test.ts:251` `KNOWN_TRUE_POSITIVE_TASKS = new Set(["mwg-qg-review-20261010"])`、`:253-254` falsePositives/truePositive 派生、`:262` `expect(falsePositives).toEqual([])`；旧断言 `toBeLessThanOrEqual` 全文件 0 命中（判据本体未放宽的声称成立） |
| 语料根（PM D-029 引 `:70`） | ⚠️ 实际 `:69` = `const root = path.join(REPO_ROOT, ".agenticdoc");`（±1，PM 过程日志锚，符号可解析） |

### ②-3 T-03（AC-005b / worker-mode.ts）

| 报告引用 | 实读结果 |
|---|---|
| `isShellRole :124`（重锚 `:126`） | ✅ `:126` `export function isShellRole(taskType: string): boolean {` |
| `isWritelessRole :131`（重锚 `:133`） | ✅ `:133` `export function isWritelessRole(taskType: string): boolean {` |
| `write_scope: 解析 :384`（重锚 `:386`） | ✅ `:386` `if (trimmed.startsWith("write_scope:")) {`（`:381` 注释明写「one-line comma form」= T-02 生产端形态，C1 双向一致） |
| `tokenizeShellCommand :665`（重锚 `:667`） | ✅ `:667` `export function tokenizeShellCommand(command: string): ShellToken[] {` |
| `extractBashWriteCandidates :807`（重锚 `:809`） | ✅ `:809` `export function extractBashWriteCandidates(command: string): BashWriteCandidate[] {` |
| `bashWriteDenyReason :921`（重锚 `:923`） | ✅ `:923` `function bashWriteDenyReason(config: BashWriteScopeConfig, target: string): string | null {`（`:922` 注释「checked first and can never be widened by a write_scope header」= 拒绝清单绝对优先） |
| `checkBashWriteScopeTarget :957`（重锚 `:959`） | ✅ `:959` `export function checkBashWriteScopeTarget(config: BashWriteScopeConfig, rawTarget: string): BashWriteScopeVerdict {` |
| `appendBashWriteScopeTraceLine :1012`（重锚 `:1017`） | ✅ `:1017` `function appendBashWriteScopeTraceLine(taskKey: string, agenticdocRoot: string, r: BashWriteScopeRejection): void {` |
| 守卫注册 `:1459`（重锚 `:1477`） | ✅ `:1464-1465` 注释 + `:1477` 附近的守卫注册区段（`taskDone`/bash 分支位于该区） |

### ②-4 T-04（AC-006 TS 半 / worker-mode.ts + deliverable-evidence.ts + pm-orchestrator.ts）

| 报告引用 | 实读结果 |
|---|---|
| `deliverable-evidence.ts:187` `hasDeliverableEvidence` | ✅ `:187` `export function hasDeliverableEvidence(taskDir: string, outputText = ""): DeliverableEvidence {`（T-12 表「0 漂移」成立） |
| `markOutcome :1268-1271`（重锚 `:1271`） | ✅ `:1271` `function markOutcome(exitCode: number): RunStatus {`（`:1277` 注释「through recordEnd…」） |
| `recordEnd :1599-1611`（重锚 `:1602`） | ✅ `:1602` `function recordEnd(exitCode: 0 | 1 | 2): void {`（签名确为 `0 | 1 | 2`） |
| `finishSuccess :1882-1910`（重锚 `:1891-1918`） | ✅ 起点精确: `:1891` `function finishSuccess(): void {`；`taskDone` 守卫 `:1895`（T-05 幂等）；判定 `:1905` `hasDeliverableEvidence(taskDir, lastAssistantText)` 在 `writeOutputGuarded`（`:1912`）之前；`exitCode: 0 | 2` `:1906`。⚠️ 范围终点失准: 函数体实际延至 `:1948`（`recordEnd(exitCode)` 在 `:1946`），alarm 调用点 `:1906`（报告引用）现为 `:1928` `recordDispatchAlarm(meta.trueAgenticdocRoot, { kind: "no-product", … })`——落在重锚范围 `:1891-1918` 之外（见 ⑤-1） |
| `pm-orchestrator.ts:401` `no-product` 值域 | ✅ `:401` `| "no-product";`（union 尾项，注释 `:398-400` 说明 AC-006） |
| `describeDispatchAlarm :433` case | ✅ `:434` `return \`${alarm.count} read-only run(s) settled without a product — needs-clarification, awaiting human judgement…\``（`:433` 为 case 行，与报告口径一致） |
| `recordDispatchAlarm :447` | ✅ `:447` `export function recordDispatchAlarm(agenticdocRoot: string, alarm: DispatchAlarm): void {` |
| `hasProductEvidence :495-500` / 唯一调用 `:661` | ✅ `:495` `function hasProductEvidence(taskDir: string): boolean {`，函数体 = 纯 `fs.existsSync` 循环（`output.md/report.md/run.json/trace.log`），**语义逐字未动**；全文唯一调用 `:661` `undispatched.some((t) => hasProductEvidence(...))`（VC-029 并存约束成立） |
| 语料 fixture `mwds-t04-deliverable.test.ts:37` | ✅ `:37` `const CORPUS = fileURLToPath(new URL("../../../../.agenticdoc/mw-gate-verdict-hardening/workers/", …))`；`:39` `CORPUS_NC = {"mwg-qg-review-20261010", "mwg-t08b-g2-surfaces"}`；ls 实数 `mw-gate-verdict-hardening/workers/` = **30 目录**，两个 NC 目录实存（corpus_dirs=30 的只读交叉验证） |

### ②-5 T-05（AC-010 / output-sections.ts + ui-bridge.ts + worker-mode.ts）

| 报告引用 | 实读结果 |
|---|---|
| 占位符单一源（D-035 ④） | ✅ `output-sections.ts:39` `import { isPlaceholderBody } from "./deliverable-evidence.ts";`、`:44` `export { DELIVERABLE_PLACEHOLDERS, isPlaceholderBody } from "./deliverable-evidence.ts";`、`:108-109` `isPlaceholderSection(_title, body)` 仅 `return isPlaceholderBody(body);`（薄包装，无第二份清单） |
| `readOutputSection/readOutputSummary` 首匹配契约不动 | ✅ 定义仍在 `ui-bridge.ts:360/:375`（`:376` `readOutputSummary` 内部调 `readOutputSection`）；4 个终态读点 `:474`（Exit Reason）/`:478`（Questions）/`:483`/`:492`（TL;DR·Summary）全部 `readLastProductSectionBody(...)`；全仓 grep `readOutputSection|readOutputSummary` 在 src 内除 ui-bridge 定义/内部调用外仅注释命中 ⇒ **无外部调用者，`/mw` 命令面零影响（VC-046）成立** |
| settle 幂等双入口 | ✅ `finishSuccess` 入口 `:1895` `if (taskDone) return;` + `agent_settled` 入口 `:1957`（注释 `:1952-1956` 明写 AC-010② 语义与 phase 机不受影响的理由） |
| D-022 真实 fixture | ✅ `mds-t08-doctor-blocked/output.md`: `## TL;DR` 三块（行 1/15/29），前两块体 = `(worker exited without writing output)`，第三块（:29）为真报告 —— 与「blocks=3 取 startLine 29」逐字一致；`mgh-rq2-gate-alert/output.md` 三块（1/15/51），首块占位 —— 「取 51」一致 |
| 测试双语料根 `mwds-t05-output-sections.test.ts:39-41` | ✅ `:39` KEY_CORPUS（本 key workers）、`:40-42` HARDENING_CORPUS（上一 key workers）、`:43` CORPUS_ROOTS |

### ②-6 T-06（AC-007 / output-writer.ts + worker-mode.ts）

| 报告引用 | 实读结果 |
|---|---|
| D-117 追加语义零改动（T-06 称 `:95`，T-12 重锚 `:106`） | ✅ `output-writer.ts:106` `fs.writeFileSync(outputPath, existing.trim() === "" ? body : \`${existing.trimEnd()}\n\n---\n\n${body}\`, "utf8");`（逐字保留） |
| 条件 `## Deliverables` | ✅ `:77` `if (deliverables.length > 0) sections.push(\`## Deliverables\n\n${deliverables.join("\n")}\`);`（空列表整段省略）；`## Changed Files` 在代码中 0 命中（仅存于说明注释 `:70/:72`） |
| `## Verification Steps` 的 `(none)` 未误伤 | ✅ `:78` `sections.push(\`## Verification Steps\n\n${opts.verificationSteps || "(none)"}\`);` |
| `changedFiles` 取值（T-06 称 `worker-mode.ts:1902`，T-12 重锚 `:1917`） | ✅ `:1917` `changedFiles: collectArtifacts(taskDir),`；`writesLabel()` `:1879`；Exit Reason 努力度 `:1911` `const effort = \`writes=${writesLabel()}\`;` 并进 `:1920-1923` exitReason |

### ②-7 T-07（AC-006 Python 半 / launcher.py）

| 报告引用 | 实读结果 |
|---|---|
| `_exit_to_status :367-373` | ✅ `:367` def；`:369-373` exit 0→done / 2→needs-clarification / 其余 failed（与 T-04 的跨语言一致性声称相符） |
| `_reap_status :376` | ✅ `:376` def；`task_dir is None ⇒ from_exit`（零回填）、`:400` `mw_common.read_run_status(task_dir)`、`:401` `RUN_TERMINAL_STATUSES` 判定、`:402-409` 冲突行打 stderr（`file=sys.stderr`，mw doctor stdout 契约保住） |
| `_reap_task_dirs :414` / 接线 `:895/:899` | ✅ `:414` def；`:895` `reap_dirs = _reap_task_dirs(project_dir) if finished else {}`；`:899` `status = _reap_status(reap_dirs.get(key), code, key)` |
| `mw_common.py:1748/1720`（T-07 已登记 +1 漂移） | ✅ `:1748` `def read_run_status(...)`、`:1720` `RUN_TERMINAL_STATUSES = frozenset({…})`（T-12 表「0 漂移」对最终面成立） |

### ②-8 T-08（AC-001 / mw_common.py）

| 报告引用 | 实读结果 |
|---|---|
| `_PANEL_TICK_STALE_SEC :3078` / `_conductor_tick_stale_after_sec :3081` / `_conductor_tick_fresh :3098` | ✅ 三处逐字（`:3095` `return max(_PANEL_TICK_STALE_SEC, float(poll) * 5.0)` = max(30, poll*5) 形式保留） |
| `_blocked_on_human :3123` | ✅ `:3123` def（三轴注释块 `:3055-3075` 含「Axis 3 … POSITIVE freshness test rather than the panel's `tickAgeMs === null => not stale`」——与面板的有意分歧在代码注释中显式登记） |
| `_doctor_gates :3137` / 早退默认 `:3162` / 覆写 `:3193` | ✅ `:3162` `"blocked_on_human": False,`；`:3193` `section["blocked_on_human"] = _blocked_on_human(project_dir, section["pending_count"]);` |
| `_gates_text_alerted :3219`（判定 `:3227`） | ✅ `:3219` def；`:3227` `if section.get("blocked_on_human"):` |
| `format_doctor_text` 后缀（报告引 `:3630`） | ✅ `:3630` `blocked_suffix = " BLOCKED_ON_HUMAN" if gates_section.get("blocked_on_human") else "";`（def 本体在 `:3510`，报告引用的是后缀逻辑行，逐字命中；T-12 表「0 漂移」对该行成立） |

### ②-9 T-09（AC-002 / conductor.py）

| 报告引用 | 实读结果 |
|---|---|
| `_STAGE_TERMINAL_RANK :565` | ✅ `:565` `_STAGE_TERMINAL_RANK = 2`（唯一族定义；`pending_gate_reminders` 内消费该常量而非内联集合——源读证实） |
| `pending_gate_reminders :2522`（签名可选参 `:2529-2530`；第 4 条件 `:2561-2567`） | ✅ 逐字: `:2529` `stage_status: dict[int, str] | None = None,`、`:2530` `stage_of_key: dict[str, int] | None = None,`；`:2561-2563` 两级解析（`gate.stage` 优先 → `stage_of_key.get(gate.key)`）；`:2564-2567` `rank = _STAGE_STATUS_RANK.get(...); if rank is not None and rank >= _STAGE_TERMINAL_RANK: continue;` |
| `_gate_stage_context :2575` / `_remind_pending_gates :2603` / 注入 `:2620` | ✅ `:2620` `stage_status, stage_of_key = _gate_stage_context(project_root)`；fail-open 诊断 `:2591`（`"[conductor] gate reminders: roadmap unavailable, …"`） |

### ②-10 T-10（AC-004 / dispatch.py）

| 报告引用 | 实读结果 |
|---|---|
| 读点 `dispatch.py:520` / 终态判定 `:522` | ✅ `:520` `run_status = mw_common.read_run_status(task_dir)`；`:522` `if run_status in mw_common.RUN_TERMINAL_STATUSES:`（`:509-519` 注释块明写 FIRST dispatch criterion / 零副作用 / exactly one read —— 与报告 §1 的落点描述一致） |

### ②-11 T-11（AC-008 / 上一 key 文档）+ T-12（收口）

- 六处勘误锚点见 ①-4 与 ②-12；`mwds-controls.ps1` 逐行 grep 到 **31 个** `Control "T-XX" "A|B|C"` 调用（T-01…T-09 各 3 + T-10 A/B + T-12 C/A），kind 计数 A=11/B=10/C=10，与 `[VERIFY] VC-042` 的 `per_group_red=A=11,B=10,C=10` 逐字一致；脚本含 sha→backup→逆改→红→还原→绿的协议实现与 `total_controls` 汇总（:280/:287）。
- `evidence-requirement.md`（上一 key 根目录）实存，`^\| \[VERIFY\]` 逐行计数 = **47 行**，VC-001…VC-047 全编号无缺（47 unique）。
- T-12 报告 §6/evidence §6 的 23 条 TS 漂移 + 12 条 Python 零漂移重锚表：上表 ②-1…②-10 已逐条对上（T-01 `+2`、T-02 `-6/-9/+3`、T-03 `+2/+5/+18`、T-04 `mv`、T-06 `+11/+15`、Python 全 0）——重锚表本身准确（除 ⑤-1 的 alarm 行一处范围失准）。

### ②-12 evidence-requirement.md 抽查 8 行的对照结果（审计项 3 的核心证据）

| 行（VC） | 引号内声称的机器行 | 所引文件实读结果 | 判定 |
|---|---|---|---|
| `:27` VC-001 | `[VERIFY] VC-001: aborted=1 no_verdict=0` | `t-06-l3-tests-report.md:62` = `[VERIFY] VC-001: aborted=1 no_verdict=0 worker_status=failed deciding_source=none` | ✅ 逐字命中（实测行含更多字段） |
| `:51` VC-008 | `[VERIFY] VC-008: rows=2 blocked_third=true` | `t-07-gate-reminder-report.md:41` 实测行 = `[VERIFY] VC-008 rows=2 blocked_third=true`（**无冒号**）；带冒号形态只存在于 `design.md:548` | ⚠️ 值一致、引号串是 design §7 声明形态而非实测原文 |
| `:40` VC-019 | `[VERIFY] VC-019: keys=3 single_key_cases=3 corpus_refrozen=true` | `t-14-count-locks-report.md` 实测 = `[VERIFY] VC-019: event_lines=27 per_type=all schema=valid`（`:160`）+ `[VERIFY] P4: corpus_sha256=1e27… cases=73` + `[VERIFY] P6: partial_single_key=35 … fields_covered=20`；`single_key_cases=3`/`corpus_refrozen` 全仓（含上一 key 全目录）0 实测命中，仅 `design.md:570` 声明 | ⚠️→**❌ 级**（该行）：引号值从未被测出；所引文件的 VC-019 实测行测的是另一组值（事实本体由 QG-A 用同文件的 cases=73/fields=20 独立复核过，坐标真实） |
| `:137` VC-029 | `[VERIFY] VC-029: new_rows=3 quota_alarm=1` | `verify-g5g6-tests.md` 内无任何 `[VERIFY] VC-029:` 行；§2 表格载有同值事实（「单轮配额截断数 10 候选 ⇒ 新增 3 + 1 条 quota 告警」+ 三个具名用例） | ⚠️ 事实在位、机器行不在位（引号串 = design 声明） |
| `:138` VC-030 | `[VERIFY] VC-030: default_spawns=8 bounded=true` | `t-18-queue-integrity-report.md` §3 只有 pytest 计数（13/7/386 passed），无该机器行；事实经 §4 控制表具名用例 `TestLauncherMaxWorkersBound::test_default_max_workers_is_eight_not_unbounded` 承载 | ⚠️ 同上 |
| `:148` VC-043 | `[VERIFY] VC-043: terminal=done marker_second_line=true` | `t-20-run-identity-report.md` 无该机器行；事实由 `:26`（VERDICT= 首行不被夺占）与 `:72`（marker 在 harness 段首行）+ 具名用例承载 | ⚠️ 同上 |
| `:68` VC-011 | `[VERIFY] VC-011: age_shown=true blocked_marker=true` | `t-08-g2-surfaces-report.md:72`（另 :57/:116、t-13:48、t-12:83 多处）逐字命中 | ✅ |
| `:175` VC-047 | `[VERIFY] VC-047: ac_frozen=true vc_frozen=true rerun_sha_stable=true no_backfill=true` | `t-23-g3-anchor-report.md:219` 实测 = `[VERIFY] VC-047: ac_first=true vc_added=true spec_bytes_stable=true repeat_sha_stable=true events=2 refused=true`（键与值均不同，语义同覆盖）；引号串 = design 声明 | ⚠️ |

结论: 47 行实存、无「不适用」占位（T-11 声称「不适用项：无」成立，且 VC-011/017/018 行如实带 ⚠️ 边界注而非敷衍）；坐标（evidence/runs/*.md）全部实存。但**结果列的引号机器行混用了 design §7 声明串与实测串**——8 行抽样中 5 行非所引文件原文，其中 VC-019 行的引号值全仓从未被测出。T-11 report §3⑤ 的表述「每行带机器可读 `[VERIFY]` 行 + 实测记录坐标」若按 verbatim 理解则部分不成立；PM 的 D-027 只核了「存在且 [VERIFY] 行 = 47」，未核 verbatim 性（PM 记录与其实测范围一致，无虚报）。

## ③ 无法核实清单（无 bash ⇒ 不得猜测，以下一律「未核」）

1. **全部 sha256 值**：冻结面 10+ 落点（`bf580757/e6c74228/4be2e569/abbba40b/9bab23b9/c78b79dc/f05f1fca/69ef5b6f/df14a89a/c52bd2b6`）、各卡 A/B/C 对照的逆改态/还原态哈希、corpus tree_sha256（`565895…`/`541a73…` 等）、T-04 测试文件哈希。无 bash 不能计算；PM 自称已逐一复算 0 drift（D-044），**未核**。
2. **全部测试执行结果**：T-01 11 passed、T-02 18/18、T-03 14/14、T-04 14/14、T-05 11/11、T-06 199 passed、T-07 15 passed、T-08 14 passed、T-09 24 passed、T-10 33 passed、T-12 9/9 与 903/920 TS、Python 全量 1579 passed/2 failed、`mwds-controls.ps1` 31/31 红→绿、`npm run check` rc=0（修复后）。只读了报告与脚本本体，**未核**（但：脚本的 31 个控制组定义逐行实存、协议代码完整，非空壳）。
3. **语料回放的运行时数值**：`corpus=295/298 read_only_books=24 hits=2`（T-02）、`oracle_parity=40/0`（T-05）。不可复跑，**未核**。可只读交叉验证的部分已完成：`mw-gate-verdict-hardening/workers/` 实数 30 目录（corpus_dirs=30）、两个 NC 目录实存、D-022 多块 fixture 的 3 块/占位形态逐字核实。
4. **活体验证**：`mw doctor --json` 的 `blocked_on_human` 输出（PM D-021 称亲跑 rc=0、字段 False）。**未核**。
5. **文件字节数**：`t12-consolidation.md 21,294 B`、`mwds-controls.ps1 18,443 B`、`evidence-requirement.md 13,918 B`。工具不返回大小，**未核**（内容实存已核）。
6. **biome/tsgo 子检查 rc=0、`Fixed 4 files` 只触及测试文件**：**未核**（只能确认源码锚点在最终面全部命中、`git status` 输出来自 T-12 转述）。
7. **mermaid 门禁 / `advance_phase` 门禁通过**：**未核**（pm-state 转述）。

## ④ 尝试证伪但失败的攻击点

1. **「报告写了但锚点漂移到不可解析」**：T-02 报告内联锚（`ui-bridge.ts:1398/1429/1453/1284/1513`）按字面翻到现在的工作区全部错位（后续卡叠改），但 T-12 §6 重锚表把每一条都映射到最终面正确行号（`:1392/:1423/:1444/:1287/:1504` 全部实读命中）⇒ 攻击失败，重锚机制真实工作。
2. **「控制脚本是摆设（只写不跑红）」**：读 `mwds-controls.ps1` 全文——每个 Control 都实现 sha→backup→正则逆改（`matched nothing` 即 throw）→跑具名测试→断言红→还原→断言 sha 相等→再跑绿，且 31 组定义与各卡报告的 A/B/C 描述一一对应（T-01 A 删守卫、T-09 B 反转 fail-open、T-04 C 收窄 hasProductEvidence 等）。结构上无法空转；实际执行输出**未核（无 bash）**，但「只写脚本不落红」的指控在结构层面不成立。
3. **「AC 有掉单（复审发现的 G-a 形态复发）」**：11 AC × 46 VC × 12 卡三方（design §3 / plan §3 / 卡头 / [VERIFY] 行）交叉对账，无缺口、无 VC 撞号（本 key 内 VC-031…033 属 T-06、VC-043…046 属 T-05，与 T-05 报告登记的 PM 派发笔误已按卡片正口径执行）。
4. **「读侧改动破坏首匹配冻结契约」**：`readOutputSection`/`readOutputSummary` 定义原样（`ui-bridge.ts:360/:375`）；`readTerminalDetail` 4 读点全部走 `readLastProductSectionBody`；全仓 grep 证明 src 内无其他调用者 ⇒ `/mw` 面零影响。攻击失败。
5. **「PM 修复引入行为变化」**：`worker-mode.ts:905` 现为 `if (previous?.startsWith("-")) continue;`——与 T-12 §7 R1 建议修法逐字一致，且该行是单行等价改写（`undefined` 在 if 条件即 falsy），未挪动任何后续行号（`finishSuccess :1891` 等锚点在修复前后均命中）。
6. **「T-11 勘误只改了表面」**：六处全部翻到上一 key 原文，旧串（拒绝该轮全部派发 / 1..50 / ac_count 24 / 1406 计数）全部 0 命中或已带勘误注；D-028 追加修复的 design §11.2 也实读核实（`:699`）。
7. **「占位符清单有两份真相源」**：`output-sections.ts:39/44/108-109` 证明读侧谓词直接 import/re-export `deliverable-evidence.ts::isPlaceholderBody`，无第二清单。攻击失败。

## ⑤ ⚠️ 发现与最小复现路径

1. **⚠️ T-04 alarm 调用点锚漂移未被重锚表覆盖**。最小复现: 读 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` `:1906`（现为 `const exitCode: 0 | 2 = evidence.delivered ? 0 : 2;`）与 `:1928`（`recordDispatchAlarm(meta.trueAgenticdocRoot, {`）——T-04 report §3 与 pm-state D-032 引 `:1906` 为 alarm 调用点；T-12 §6 把 T-04 的 `finishSuccess :1882-1910` 重锚为 `:1891-1918`，但该函数实际延至 `:1948`，alarm 调用（`:1928`）落在登记范围之外。影响: 符号级（`recordDispatchAlarm(meta.trueAgenticdocRoot`）仍可 grep 复算，审计链未断；属 `drift_registered=23` 的一处漏计/范围失准，建议 T-12 表补一行 `T-04 alarm :1906 → :1928`。
2. **⚠️ evidence-requirement.md 结果列 verbatim 性**（上一 key 的本 key 交付物）。最小复现: 对照 `.agenticdoc/mw-gate-verdict-hardening/evidence-requirement.md:40`（VC-019 行）与 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-14-count-locks-report.md:160-164`（实测 `[VERIFY] VC-019: event_lines=27 …` / `P4: cases=73` / `P6: fields_covered=20`）——引号串 `keys=3 single_key_cases=3 corpus_refrozen=true` 只在 `design.md:570` 出现。最小修法: 结果列改为实测行（或标注「design §7 声明值，实测坐标=…」），VC-008/029/030/043/047 行同理。影响: 不改变 VC 判定本体（QG-A 已用同文件实测数独立复核 VC-019 等），但「结果列 = 实测机器行」的表述需要降格为「声明值 + 实测坐标」。
3. **⚠️ 上一 key plan.md:117 残留「超限拒绝 + 告警」**。最小复现: 读 `.agenticdoc/mw-gate-verdict-hardening/plan.md:117`（「④ 单轮新增行数 ≤ `dispatch_max_per_scan`（默认 3），超限拒绝 + 告警」）与同 key `spec.md:138`（已改「截断至 N」）、`design.md:699`（PM 勘误后「return（截断）」）——三处口径中 plan 仍留旧措辞，与 D-028 修 design §11.2 属同族残留，未被 T-11 六处清单及其残留节覆盖。影响: 纯文档（实现 = 截断，已有 spec/design 对齐），建议补一条同形勘误。
4. **⚠️ 两处「已披露、未升格裁定」**（不构成违纪，登记供 PM 收口）:
   - T-08 的 doctor 第三轴与面板在「无 timeline」情形下**有意不同**（面板 `tickAgeMs===null ⇒ not stale`，doctor ⇒ 不新鲜 ⇒ false）——在 T-08 report §Notes 与 `mw_common.py:3067-3071` 代码注释中披露（保 I7 零扰动），seam 用例只测了 true/stale-false/row-false 三形态；AC-001/DD-10 的「三轴口径与面板同源」在无 timeline 项目上不成立。未见于 pm-state 任何 D 条。
   - R3（T-12 §7）: design R-06 写「DD-02 白名单不含 `output.md`」而实现按卡片白名单放行 `output.md`——已登记为残留，但 design 文本未同步，spec/design 与实现存在一处长期字面分歧。
5. **未核项不算发现**: ③ 节所列（sha256/测试执行/活体/字节数）在无 bash 前提下保持未核状态，PM 的对应声称（0 drift、rc=0、1579/2、304 passed）与卡片自报之间**内部自洽且与可读面证据无冲突**，但本审计不能为其背书。

## 结论

- 六项审计: 5 ✅ + 1 ⚠️（AC-009 证据纪律，缺口集中在上一 key 补建产物 evidence-requirement.md 的 verbatim 性），**0 ❌**。
- 本 key 12 张卡的判定本体（[VERIFY] 锚点、AC/VC 映射、六处勘误、T-12 PARTIAL→PM 修复闭环、自报偏差的下落）在只读审计下全部成立；两处行级精度问题（⑤-1/⑤-3）与两处未升格披露（⑤-4）建议在 `achieved.md` / 质量门报告中各加一行登记。
