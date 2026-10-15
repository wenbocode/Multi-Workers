# Research T-RQ4: `[CHECKPOINT]` 判据与 settle 前自检的插入点

- Key: mw-worker-output-contract
- 任务: T-RQ4-checkpoint-settle（research，只读）
- 卡: `.agenticdoc/mw-worker-output-contract/tasks/T-RQ4-checkpoint-settle.md`（sha256 d9c55992fa89e90b…）
- 时间: 2026-10-14
- 方法边界: 仅静态读取源码与已落盘工件 + 行号/字节核对；未运行任何测试、未执行 npm/git 变更操作、未改仓库任何文件。

## 0. 结论先行

1. `[CHECKPOINT]` 只有**时间触发**（`setTimeout`），无事件触发：首拍 `checkpointAnchorMs(budgetMs)=min(30m, max(1s, budget/2))`，之后每 10m 刷新（`worker-mode.ts:250-252`、`:2568-2576`）。
2. `reads`/`writes`/`uniq_targets`/`repeat_top` 只统计 `read|grep|find|ls|glob` 与 `write|edit` 两类**工具调用**（`worker-mode.ts:260-262`、`:2317-2323`、`:2345-2353`）；`worker_file` 不在任一集合 ⇒ 对 writeless 角色 `writes`/`uniq_targets` **恒为 0**。
3. `computeRisk` 规则（`worker-mode.ts:283-286`）：`high` = `writes===0 && elapsed>=anchor`；`mid` = （`phasesTotal>0 && phasesDone===0 && elapsed>=anchor`）或 `repeatTop>=4`；否则 `low`。writeless 的失真是**入参**问题而非规则问题：即使边界判成 `high` 仍是“发散”误判。
4. `wjg-w12-negative-space-audit` 直接反证：产物 `report-negative-space-audit-20261013.md`（37,149 B）`17:32:12` 落盘、trace 已有 2 条 `[WRITE_FILE]`，而 `17:33:36` 检查点仍写 `writes=0 uniq_targets=0 risk=mid`。
5. settle 判定顺序在 `finishSuccess()` 内：`hasDeliverableEvidence`(2720) → `readTerminalGaps`(2740) → `exitCode`(2746) → `writeOutputGuarded`(2761，**先判后写**) → `recordEnd`(2802)。判定读 `report.md` → `output.md` → 最终回复，**不读 `report-<slug>.md`**（`output-writer.ts:140-147`）——这是“实质交付被判缺段”的结构性缺口。
6. 插入点两个、互不重叠：**I1** 在 `agent_settled`(2806 起) 触发一次 `followUp` 自检回合（复用既有 phase 机器模式）；**I2** 在 `finishSuccess()` 的 `clearInterval(heartbeat)`(2713) 与 `const evidence`(2720) 之间做机械段自动补齐。改 `risk` **不影响** idle/wall 两段（各自只读 `lastActivityAt`/`budgetMs`）。

## 1. `[CHECKPOINT]` 的完整生成链

### 1.1 常量与锚点

- `worker-mode.ts:199` `export const DEFAULT_BUDGET_MS = 60 * 60_000;`（墙钟兜底 60m）
- `worker-mode.ts:205` `export const DEFAULT_IDLE_MS = 10 * 60_000;`（activity idle 10m）
- `worker-mode.ts:207` `const CHECKPOINT_ANCHOR_MS = 30 * 60_000;`
- `worker-mode.ts:208` `const CHECKPOINT_REFRESH_MS = 10 * 60_000;`
- `worker-mode.ts:250-252`：
```
export function checkpointAnchorMs(budgetMs: number): number {
	return Math.min(CHECKPOINT_ANCHOR_MS, Math.max(1_000, Math.round(budgetMs / 2)));
}
```
- `worker-mode.ts:212-217` `resolveBudgetMs`：task.md `timeout:` > `PI_WORKER_TIMEOUT_MS` > `DEFAULT_BUDGET_MS`。
- `worker-mode.ts:2450` `const budgetMs = resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS);`
- `worker-mode.ts:2456` `const riskAnchorMs = checkpointAnchorMs(budgetMs);`

### 1.2 触发条件：只有时间

- `worker-mode.ts:2568-2575`（唯一调度器）：
```
	function scheduleCheckpoint(delayMs: number): void {
		checkpointTimer = setTimeout(() => {
			if (taskDone) return;
			writeCheckpoint();
			scheduleCheckpoint(CHECKPOINT_REFRESH_MS);
		}, delayMs);
		checkpointTimer.unref();
	}
```
- `worker-mode.ts:2576` `scheduleCheckpoint(riskAnchorMs);`
- 全文件仅此 2 处调用 `scheduleCheckpoint`（grep `scheduleCheckpoint` = :2568/:2572/:2576），`writeCheckpoint` 只在 :2571 被调用 ⇒ **无事件触发路径**。`taskDone` 守卫保证 settle 后不再写（:2570）。

### 1.3 计算 `elapsed/reads/writes/uniq_targets/repeat_top`

- `worker-mode.ts:2510-2532`（`writeCheckpoint` 关键段）：
```
	function writeCheckpoint(): void {
		const elapsedMs = Date.now() - startedAt;
		let repeatTop = 0;
		for (const n of readCounts.values()) repeatTop = Math.max(repeatTop, n);
		const phasesStr = phaseTotal > 0 ? `${completedPhaseIdx}/${phaseTotal}` : "-";
		const risk = computeRisk({ elapsedMs, anchorMs: riskAnchorMs, writes: writeCount,
			phasesTotal: phaseTotal, phasesDone: completedPhaseIdx, repeatTop });
		appendCheckpoint(meta.taskKey, meta.agenticdocRoot, {
			elapsedMs, reads: readCount, writes: writeCount, phases: phasesStr,
			uniqTargets: writeTargets.size, repeatTop, risk });
```
- 数据来源与计数器声明 `worker-mode.ts:2317-2323`：`toolCallCount`、`toolsUsed`、`readCount`、`writeCount`、`writeTargets: Set<string>`、`readCounts: Map<string, number>`。
- 采样点 `worker-mode.ts:2341-2353`（`tool_execution_start`）：
```
		const target = toolTarget(event.args);
		if (READ_TOOLS.has(event.toolName)) {
			readCount++;
			if (target) readCounts.set(target, (readCounts.get(target) ?? 0) + 1);
		} else if (WRITE_TOOLS.has(event.toolName)) {
			writeCount++;
			if (target) writeTargets.add(target);
			pendingWriteTargets.set(event.toolCallId, target);
		}
```
- 集合定义 `worker-mode.ts:260-262`：
```
const READ_TOOLS = new Set(["read", "grep", "find", "ls", "glob"]);
const WRITE_TOOLS = new Set(["write", "edit"]);
```
- `target` 由 `toolTarget(args)` 抽取（`worker-mode.ts:539-553`，取 `path|command|pattern|query|file` 第一行）。
- `reads = readCount`（**调用计数**，非去重文件数）；`uniq_targets = writeTargets.size`（仅 write/edit 的去重 target）；`repeat_top = max(readCounts.values())`。`worker_file` 与 `bash` 均不进这两个计数器。

### 1.4 `risk` 判定规则（`worker-mode.ts:283-286`，逐字）

```
export function computeRisk(s: ConvergenceSignals): "low" | "mid" | "high" {
	if (s.writes === 0 && s.elapsedMs >= s.anchorMs) return "high";
	if ((s.phasesTotal > 0 && s.phasesDone === 0 && s.elapsedMs >= s.anchorMs) || s.repeatTop >= 4) return "mid";
	return "low";
}
```
- `high`：零 write/edit 调用 **且** 原始毫秒 `elapsedMs >= anchorMs`。
- `mid`：（有 phases 且 0 完成 且过锚点）**或** 任一 target 被读 ≥4 次（`repeatTop>=4`，**锚点前也可触发**）。
- `low`：其余（含 `writes>0` 但未过锚点、无 phases）。
- `high` 先判，`mid` 次之；`writes===0 && repeatTop>=4` 且未过锚点时也是 `mid`。

### 1.5 落盘与 PM 侧消费

- 行格式 `worker/output-writer.ts:474-484` `appendCheckpoint`：`[CHECKPOINT] <iso> elapsed=<s>s reads=<n> writes=<n> phases=<d/t|-> uniq_targets=<n> repeat_top=<k> risk=<low|mid|high>`；解析正则 `shared/heartbeat.ts:84-85`（锚定 `^…$`）。
- writeless 额外机器行 `worker-mode.ts:2536-2548`：`!hasWriteTools` 时 `appendProgressLine(formatMachineCheckpoint(...))`（`CKPT <n>m [machine] …`，`output-writer.ts:495-505`），显示用。
- `triggerTurn` 升级 PM 路径：PM 轮询 `pm/pm-orchestrator.ts:1417-1419`
```
				const ck = readTaskProgress(path.dirname(entry.taskPath))?.checkpoint;
				if (!ck || ck.risk === "low") continue;
				escalated.add(entry.taskKey);
```
  然后 `:1426` `deliverPmAlert(pi, …发散风险…)` → `pm/ui-bridge.ts:175-185` `pi.sendMessage({...}, { triggerTurn: true })`。即：`risk!=low` + 归属（watch key ∪ 本窗口派发）→ 每任务一次唤醒。`lastCheckpoint` 另用于 `timeoutExit` 的详情串（`worker-mode.ts:2485-2487`）。

## 2. writeless 角色的「已落盘」可用信号（逐条判定）

前提：`isWritelessRole`（`worker-mode.ts:158-161`）为真时注册 `worker_file`（`:2132-2134`），其写路径内部**会**落 `[WRITE_FILE]`（`worker-file-tool.ts:82`）。

| # | 信号 | 代码位置 | 对 writeless 是否可得 | 判定依据 |
|---|---|---|---|---|
| S-a | trace `[WRITE_FILE] path=…`（`worker_file` 写的 report/progress） | `worker-file-tool.ts:82` → `change-ledger.ts:123`；消费 `change-ledger.ts:148` `parseWriteFileEvents` | **可得（是）** | wjg-w12 trace 实测 4 条，含 `report-negative-space-audit-20261013.md` 与 3 条 `progress.md`；`readTerminalGaps` 已读 trace（`output-writer.ts:204`） |
| S-b | trace `[TOOL] <ts> worker_file <basename>` | `worker-mode.ts:2360` → `output-writer.ts:431` | **可得（是）** | wjg-w12 trace 实测 4 条 `[TOOL] … worker_file …`（`toolTarget` 抽 `file` 参数，:539-553） |
| S-c | 任务目录产物存在性 `report.md`/`report-<slug>.md` | `deliverable-evidence.ts:105` `findNonEmptyReport`；`run-store.ts:119` `collectArtifacts` | **部分可得** | `findNonEmptyReport` 认 `report-<slug>.md`（是）；`collectArtifacts` **只列 `output.md`/`report.md`/`progress.md`/`phase-*`/`stage-*`**，不列 `report-<slug>.md`（否）——wjg-w12 `run.json.artifacts` = `["output.md","progress.md"]`，不含 37,149 B 报告 |
| S-d | `<key>/evidence/**` 产物存在性（目录枚举） | 无枚举器：仅 `deliverable-evidence.ts:153` `findReferencedEvidence`（需正文引用）与 `change-ledger.ts` `resolveDeliverablePath`（需报告文本 token） | **不可得（否）** | 两份实现都以“文本引用”为入口，全仓未见按 run 窗口扫描 `evidence/` 目录的代码 |
| S-e | `progress.md` 框架机器完成行 `CKPT <n>m [machine] … risk=…` | `worker-mode.ts:2536-2548` → `output-writer.ts:495-505` | **可得（是）** | writeless 每次检查点框架直写；wjg-w12 `progress.md` 实测该行 |
| S-f | `progress.md` agent 自评行 `CKPT <n>m converging=yes/no …` | 引导文案 `worker-mode.ts:182-190`（经 `worker_file` append 或回复） | **可得但不可机读（否）** | 全仓无解析器：grep `converging` 仅命中引导串（:182/:188）；`readTaskProgress` 正则不含它 |
| S-g | `[CHECKPOINT]` 行本身 | `worker-mode.ts:2523-2531` | **可得但字段失真（否）** | `writes`/`uniq_targets` 恒 0（§1.3）；`repeat_top` 反映读重复度，与“是否已落盘”无关 |
| S-h | `run.json.artifacts` | `worker-mode.ts:2009`/`finishRun` → `collectArtifacts` | **部分可得** | 同 S-c 盲区（`report-<slug>.md` 缺失）；wjg-w12 实测漏报 37,149 B 报告 |
| S-i | `run.json.status`/`exit`/`last_heartbeat_at` | `run-store.ts`（`writeRunState`）；`worker-mode.ts:2412-2430` `recordEnd`/`finishRun` | **可得（是）** | 每 run 全量写；wjg-w12 = `needs-clarification`/`exit 2`/`last_heartbeat_at 17:36:36` |
| S-j | `unjudgeable` 的**机器**信号 | 仅 `output-writer.ts:357-358` 写 `## Ledger Unjudgeable` **产品段** | **trace 不可得（否）** | `writeOutput` 只为 malformed/infra/unresolvable 写 `[FLOW]` trace 行（`output-writer.ts:283`/`:296`/`:311`），`unjudgeable` **无 trace 行** |

直接反证数据（wjg-w12）：`[WRITE_FILE]` 4 条、`[TOOL] worker_file` 4 条、`[CHECKPOINT]` 1 条（`elapsed=1800s reads=111 writes=0 uniq_targets=0 repeat_top=16 risk=mid`），报告 37,149 B 于 `17:32:12` 落盘而检查点在 `17:33:36`（更晚）。`reads=111` 与该 trace 的工具计数完全吻合：`read 46 + grep 51 + find 9 + ls 5 = 111`（`worker_file 4` 不计）。

关于 `risk=mid`（而非按 §1.4 期望的 `high`）的机械解释（有界，非推测）：`[START] ts=17:03:36.137Z`、checkpoint `ts=17:33:36.128Z`，差 = 1,799,991 ms，比 `anchorMs=1,800,000` **小 9 ms**；`elapsed` 字段是 `Math.round(elapsedMs/1000)=1800`，因此 `high` 的 `elapsedMs >= anchorMs` 为假，`mid` 由 `repeatTop=16>=4` 命中。两者（`mid` 或 `high`）都属“发散”误判——本条的要点是**入参 `writes=0` 恒真**，不是规则分支。

## 3. settle 路径的顺序与插入点（核心交付）

### 3.1 现状顺序（agent 收尾 → output.md → 判定 → exitCode）

1. `worker-mode.ts:2395-2407` `pi.on("agent_end")`：只把最后一条 assistant 文本存入 `lastAssistantText`（:2394）。**此步无任何判定。**
2. `worker-mode.ts:2806` `pi.on("agent_settled")`：handler 入口；`if (taskDone) return;`（:2811）。
3. `worker-mode.ts:2822`（无 phases）或 `:2856`（phases 全部完成）调用 `finishSuccess()`。
4. `finishSuccess()`（`worker-mode.ts:2707`）内部：
   - a. `taskDone=true`；`clearWatchdogTimers()`；`clearInterval(heartbeat)`（:2711-2713）
   - b. `const evidence = isWritelessRole(meta.type) ? hasDeliverableEvidence(taskDir, lastAssistantText) : {delivered:true,…}`（:2720-2722）——`delivered` 语义 = “本 run 是否留下交付物”，来源三通道：非空 `report.md|report-<slug>.md` → 产品文本（`output.md` 优先，否则最终回复）含非占位 `## TL;DR/## Summary` 且命中机器信号/存在的 `evidence/**` 引用 → `run.json.artifacts` 非 `output.md`（`deliverable-evidence.ts:187-210`）。
   - c. `reportProduct = fs.statSync(<taskDir>/report.md).size > 0`（:2734-2739）——只 `report.md`，不含 `report-<slug>.md`。
   - d. `const gaps = readTerminalGaps({taskKey, agenticdocRoot, summary: buildSummary(), judgeRecovery: isWritelessRole(meta.type) || reportProduct})`（:2740-2745）。内部：`agentProductText(dir, summary)` 依次取 `report.md` → `output.md` → summary（`output-writer.ts:140-147`、:202）；`checkRecovery(productText, type)`（:203，`output-sections.ts:120-124`）；`diffLedger(productText, traceText, {role, deliverableDir, runStartedAtMs, projectRoot})`（:208）；`ok = missingSections==0 && extra==0 && unjudgeableFiles==0`（:238）。
   - e. `const exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2;`（:2746）
   - f. `writeOutputGuarded({…, exitCode, terminalGaps: gaps, …})`（:2761-2778）→ `writeOutput`（`output-writer.ts:242`）；`outputPath = <taskDir>/output.md`（:246）；因传了 `terminalGaps`，**不再重判**（:257-259），直接拼 harness 段并 append/覆盖（:370-372）。**判定在先、output.md 落在后。**
   - g. `recordEnd(exitCode)`（:2802）→ `[END]`（`output-writer.ts:526-538`）、`finishRun` 写 `run.json`（:2018-2024）。
5. 兜底：`process.on("exit")` 若 `!outputWritten` 则以 exit=1 补写（`worker-mode.ts:2091-2110`）。

结构性缺口（实证）：`hasDeliverableEvidence` 认 `report-<slug>.md`（wjg-w12 因此 `delivered=true`），但 `checkRecovery` 只看 `report.md`/`output.md`/回复 ⇒ wjg-w12 被判 `missing section(s): 结论, 证据, 残留与未验证, 上下文来源, 未覆盖面声明`、`exit=2`（`output.md` 首行 `<!-- mw-run: … status=needs-clarification -->`、`## Questions` 实测）。

### 3.2 插入点清单（可直接落 tasks）

**I1 — settle 前自检回合（S2 / AC-004）**
- 位置：`worker-mode.ts:2806-2823`（`agent_settled` handler 内），在 `:2811` `if (taskDone) return;` 之后、`:2822` `finishSuccess()` 之前（无 phases 分支），以及 `:2856` 最终 `finishSuccess()` 之前（多 phases 分支）。
- 原文（插入点前后）：
```
2806	pi.on("agent_settled", () => {
2807		try {
2811			if (taskDone) return;
2812			if (!initialSettled) {
2813				initialSettled = true;
2814				// Initial task prompt (from pi -p) has settled
2815				if (phases && phases.length > 0) {
2816					appendPhase(meta.taskKey, meta.agenticdocRoot, "start", 1, phases.length, phases[0].name);
2817					pi.sendUserMessage(phases[0].prompt);
2818					nextPhaseIdx = 1;
2819					return;
2820				}
2821				// No phases — write output and let pi exit naturally
2822				finishSuccess();
2823				return;
```
- 机制：用一次性标志（如 `let selfChecked = false`）在 `finishSuccess()` 之前计算结构化缺口（缺段名列表或 `ok`）；非 `ok` 且未自检过时 `pi.sendUserMessage(<缺口清单 + 可复制 `## <段名>`>, {deliverAs:"followUp"})` 后 `return`（**不**调 `finishSuccess`）。下一拍 settle 再走 `finishSuccess()`。该 sendUserMessage-from-settle 模式**已在生产路径使用**（:2817 与 :2848），无需新机制；`taskDone` 仍为 false，看门狗覆盖该额外回合。需保证多 phases 时 `initialSettled` 不复位。
- 可解析 trace 行（AC-004）：在同处或 `finishSuccess` 内用 `appendTrace(meta.taskKey, meta.agenticdocRoot, "settle-selfcheck missing=<…>|ok")`（`output-writer.ts:374-382`）。`[CHECKPOINT]` 正则锚定，新增行类型不会干扰 `readTaskProgress`。

**I2 — 机械段 `## 上下文来源` 自动补齐（S3 / AC-005）**
- 位置：`worker-mode.ts:2713-2720` 之间（`clearInterval(heartbeat)` 之后、`const evidence` 之前）。
- 原文：
```
2711		if (taskDone) return;
2712		taskDone = true;
2713		clearWatchdogTimers();
2714		clearInterval(heartbeat);
2715		// AC-006 (contract C5): a writeless role that settles without a product is
2716		// needs-clarification, not done. Judged here — before the single write-out —
2717		// so the output.md marker, `## Questions`, run.json.status and `[END] exit=`
2718		// all carry the same verdict. Write roles are exempt: a coding run's
2719		// deliverable is the repository, not a file in its own task dir.
2720		const evidence = isWritelessRole(meta.type)
```
- 理由（代码证据）：`evidence`(2720) 与 `gaps`(2740→`agentProductText`, `output-writer.ts:202`) 都从磁盘读同一产品文本；补齐必须发生在两者之前，否则两次判定看到的文本不一致。
- 约束：必须写到 `agentProductText` 会读的文件——`report.md`（若非空）否则 `output.md`（`output-writer.ts:140-147`）。若保持现状，写 `report-<slug>.md` **无效**（不在读取列表）。配套改动二选一：(a) 把 `report-<slug>.md` 纳入 `agentProductText`，或 (b) 自检回合要求 agent 把报告落到 `report.md`。
- 次要位置（覆盖直调/测试调用方）：`output-writer.ts:257-259` 之前（`opts.terminalGaps ?? readTerminalGaps(...)` 的兜底分支）。settle 主路径已传 `terminalGaps`，故主插入点必须在 worker-mode。

**I3 — 结构化缺口回读（AC-002）**
- `writeOutput` 的缺段名已走 `## Questions` 首行（`output-writer.ts:263` `gapNote`、:347-350）；修 S1/S3 后保持一致即可；无需新位置，但 `## Questions` 文本由 `gaps.missingSections` 生成，故必须与 I2 用同一 `gaps` 对象（现状已如此：`terminalGaps: gaps` 传入）。

**I4 — 检查点入参修复（S5 / AC-009）**
- 位置：`worker-mode.ts:2515-2529`（`computeRisk` 入参与 `appendCheckpoint` 字段）。可用数据当场可得：`hasWriteTools`（:2131）、`writeTargets`（:2322）、trace 已有 `[WRITE_FILE]`（可用 `parseWriteFileEvents`，`change-ledger.ts:148`）、`fs.existsSync(<taskDir>/report*.md)`。
- 约束：`[CHECKPOINT]` 行由锚定正则解析（`heartbeat.ts:84-85`），新增字段会破坏解析 ⇒ 只能改**已有字段的取值语义**或新增独立行类型；spec §2.2 要求不增加 trace 行数。

## 4. 机械段（`## 上下文来源`）在 settle 时可得的字段

| 事实 | 字段/入口 | 读取位置 | 现状 |
|---|---|---|---|
| 卡路径 | task.md header `card_path:` | 由 `pm/ui-bridge.ts:2030-2036` `mergeCardHeader` 写入；通用读取器 `shared/task-frontmatter.ts:117` `readTaskHeaderScalar` | settle 路径**未读**（`TaskMeta` `worker-mode.ts:291-340` 无卡片字段） |
| 卡 sha256 | task.md header `card_sha256:` | 同上 | 同上（**未读**） |
| task.md 原文/路径 | `taskContent`、`taskPath` | `worker-mode.ts:1901`、`:1922`；`meta.trueAgenticdocRoot` 可用于拼 `.agenticdoc/goal.md` | 可用 |
| 读取清单（按 target 计数） | `readCounts: Map`、`toolsUsed: Set`、`readCount` | `worker-mode.ts:2319-2323`；逐次 `[TOOL]` 行 `output-writer.ts:431`（调用点 `worker-mode.ts:2360`） | 可用（未汇聚成段落） |
| 写事件清单 | `writeTargets: Set`（write/edit）；全量 `parseWriteFileEvents(traceText)`（含 `worker_file`/`bash`） | `worker-mode.ts:2322`；`change-ledger.ts:148`；trace 文本已在 `output-writer.ts:204` 读入 | 可用 |
| 产物清单 | `runState.artifacts` / `collectArtifacts(taskDir)` | `worker-mode.ts:2009`、`finishRun`；`run-store.ts:119-139` | 可用但有盲区：不列 `report-<slug>.md` |
| 已有引用/产物路径 | `findReferencedEvidence(taskDir, text)` | `deliverable-evidence.ts:153-173`（只有被正文引用才解析） | 可用（被动） |
| goal 锚点 mtime | `goalMtime(meta.trueAgenticdocRoot)` / `appendGoalCheck` | `worker-mode.ts:2845`；`output-writer.ts` `appendGoalCheck` | 可用 |
| 运行事实 | `startedAt`、`Date.now()-startedAt`、`toolCallCount`、`meta.taskKey`/`owner_key`（`runState.owner_key`，`worker-mode.ts:1936`） | `worker-mode.ts:1904`、`:2317`、`runState` | 可用 |
| 最终回复 | `lastAssistantText` | `worker-mode.ts:2394-2407` | 可用 |

结论：`## 上下文来源` 至少能用 `card_path`（+ `card_sha256`）、读取 target 清单、`[WRITE_FILE]` 写事件、`run.json.artifacts` 四类事实凑出**非空且可核**的内容，且全部在 settle 时已在手上（无需新 I/O，除可选的 `report-<slug>.md` 枚举补盲区）。

## 5. 现有测试清单（vitest + pytest）

vitest（`packages/coding-agent/test/`）：
- `extensions/agent-team-loop.test.ts`
  - `AC-002/D-004: checkpoint anchor and steer times scale with budget`（~:4033）：`checkpointAnchorMs(60m)=30m`、`(2m)=60s`、`(6h)=30m`、`steerAtMs`。
  - `AC-004: computeRisk — high … mid … low …`（~:4061）：5 条断言（零写过锚点→high；phases 停滞→mid；`repeatTop>=4`→mid；锚点前零写→low；写推进→low）。**改 risk 规则即翻转。**
  - `AC-004: appendCheckpoint writes the structured line; readTaskProgress parses it`（~:4120）：锚定 `/^\[CHECKPOINT\] … uniq_targets=0 repeat_top=3 risk=high$/`；**改行格式即翻转**。
  - `AC-005: running widget line carries the checkpoint badge`（~:4166）：`ck30m high⚠` / `ck30m`。
  - `AC-004: poll loop wakes the PM once on a mid/high checkpoint (triggerTurn)`（~:4234）：消息含 `risk=high`、`triggerTurn=true`、不重复；**改 risk 值即翻转**。
  - `AC-004: diverging workers owned by other keys never wake this window`；`AC-001/AC-002/AC-003` 跨 key 升级三例。
  - watchdog 集成 `AC-001: no activity for idleMs kills…`（~:4523）、`AC-002/003/004: deadline steer, checkpoint steer and wall kill fire in order`（~:4615）：含 `[CHECKPOINT]`、`risk=high`、`(checkpoint: risk=high reads=0 writes=0`。
- `extensions/agent-team-loop-checkpoint-wiring.test.ts`：`VC-001/VC-002 type=review writes exactly one [machine] line at the anchor`（`MACHINE_LINE_RE` 含 `risk=(low|mid|high)`）、`VC-003 type=coding writes no [machine] line`、`VC-002 appendProgressLine is append-only`、`VC-004` steer 字节基线、`VC-007 activeToolsForType`、`VC-005/VC-006` worker_file trace。**仅当机器行格式/角色切分变化时翻转。**
- `extensions/agent-team-loop-watch-aggregate.test.ts`：`VC-009: high-risk checkpoints on cross-key running rows surface as risk=high:<K>`（:151）；**改 risk 即翻转。**
- `suite/dispatch-recovery-terminal.test.ts`：`AC-003 terminal flip …flips done -> needs-clarification and names the missing section`、`…a complete report settles done`、`…migration: a book without a header type: is never judged`、`AC-004 ledger gaps …`、`readTerminalGaps is the single verdict both the status and the product use`。**S1/S3 改动会直接翻转前两者（自动补齐会把缺 `上下文来源` 的例从 exit=2 变 exit=0）。**
- `suite/output-recovery-contract.test.ts`：`checkRecovery (AC-003)` 全组（含 `MISSING_CONTEXT_SOURCES`）；**S1/S3 改判定即翻转。**
- `suite/mwds-t04-deliverable.test.ts`：`AC-006 corpus replay`（28/2/0）、`channel order`、`AC-006 settle fold (e) exit=2 / (f) exit=0`、`AC-006 coexistence …`；**改 `hasDeliverableEvidence` 即翻转。**
- `suite/mwds-t12-regression.test.ts`、`suite/mwgal-t17-ledger-role-aware.test.ts`（`readTerminalGaps folds the outside-taskDir deliverable into a clean verdict`）、`suite/mwgal-t17b/t17c/t21` 等：与 ledger/交付判定相邻，S3 补齐可能影响其 `ok` 期望。
- `suite/rag-e2e-slow.test.ts:221` `expect(trace).toContain("[CHECKPOINT]")`（e2e，需 endpoint/auth env，不在定向套件内）。

pytest（`packages/multi-workers/`）：
- `test_launcher.py::TestReconcileOrphans::test_end_exit_maps_to_terminal_status`（0/1/2/3→done/failed/needs-clarification/failed）、`test_output_md_without_end_failed_unverifiable`、`test_run_json_running_with_output_md_becomes_lost`(:1363)、`test_run_json_running_stale_no_output_becomes_lost`(:1384)。**仅在 exit→status 映射变化时翻转（本 key 计划不改）。**
- `test_mwds_t07_reap_productfirst.py::TestReapStatusProductFirst`（`test_a_run_needs_clarification_outranks_exit_zero`、`test_b_run_done_with_exit_zero_is_done`、`test_c_missing_run_json_falls_back_to_exit_code`、`test_d_run_lost_is_preserved`、`test_reap_status_never_writes_run_json`）+ `TestReapProductFirstEndToEnd`。**改 worker 侧 run.json 状态语义即翻转。**
- `test_run_identity.py::test_terminal_status_sets_are_identical_across_languages`（跨语言终态集合一致）；**引入新状态即翻转。**
- `test_common.py::…::test_exit_codes_0_1_2`、`test_integration.py::…::test_exit2_needs_clarification`/`test_exit0_done_exit1_failed_with_worker_logs`、`test_task_type_parity.py`（TS/Python allowlist 一致，改工具集即翻转）。
- **0 个** pytest 用例引用 `[CHECKPOINT]`/`computeRisk`（见「未找到清单」）⇒ 检查点链无 Python 侧测试。

## 6. 与看门狗三段式的耦合

- activity idle（10m）：`worker-mode.ts:2591` `idleTimer = setInterval(() => { … }, 30_000)`；`:2594` `const idleForMs = now - lastActivityAt;`；`:2624` `if (idleForMs < idleMs) return;`。输入只有 `lastActivityAt`（由 message/turn/tool 事件 `touch()` 刷新，:2290-2315）、`idleMs`（:2451）、`toolIdleMs`（:2455）与 in-flight 工具表。**不读 `writeCount`/`lastCheckpoint`/`risk`。**
- 墙钟兜底（默认 60m）：`:2650-2654` `wallTimer = setTimeout(() => { … timeoutExit("wall", `budget ${Math.round(budgetMs/1000)}s exceeded …`) }, budgetMs);`；`budgetMs`（:2450）来自 `resolveBudgetMs`（:212-217，`DEFAULT_BUDGET_MS` :199）。**不读 risk。**
- 唯一耦合：`writeCheckpoint()` 会 `pi.sendUserMessage(…, {deliverAs:"followUp"})`（`worker-mode.ts:2558-2567`），该回合会产生 `turn_start`/`message_start` 事件从而刷新 `lastActivityAt`，使 idle 判据顺延一拍；`lastCheckpoint` 仅被 `timeoutExit` 的详情串使用（:2485-2487）。
- 因此：改 `computeRisk` 的**返回值**（比如把 writeless 的已落盘判为 `low`）**不影响** idle/wall 触发；只有当改动**抑制/增加 checkpoint steer 的发送**时，才会通过 `lastActivityAt` 间接影响 idle（且不改变阈值）；checkpoint 节奏（`CHECKPOINT_REFRESH_MS` :208、`:2572`）不变则 trace 行数不变（spec §2.2）。

## 未找到清单

- `[CHECKPOINT]`/`computeRisk` 的 Python 实现或测试：未找到。
  命令 + 输出：`git grep -n "computeRisk|CHECKPOINT" -- packages/multi-workers` → 仅 `dist/extensions/agent-team-loop.js`（TS 产物）与 `test_autopilot_xkey_registration.py:58` 的一行无关 docstring（Machine-readable checkpoint line）；无 risk 逻辑、无用例。
- `unjudgeable` 的 trace 机器行：未找到。
  证据：`worker-mode.ts:2754-2760` 只生成 `unjudgeableReason` 字符串并送入 `writeOutputGuarded` 的 `exitReason`/`## Questions`；`output-writer.ts:283/296/311` 只对 malformed/infra/unresolvable 调 `appendTrace`；grep `unjudgeable` 无 `appendTrace` 调用点。
- `progress.md` 自评 `converging=` 的解析器：未找到。
  证据：grep `converging` 仅 `worker-mode.ts:182`、`:188`（引导文案）；`shared/heartbeat.ts:80-85` 的 5 个正则均不含它。
- settle 路径读取 `card_path`/`card_sha256`：未找到。
  证据：grep `card_path|card_sha256` 仅 `pm/ui-bridge.ts`（写入）与 `shared/task-frontmatter.ts:117`（通用 scalar 读取器，唯一消费者是 `pm/task-dispatcher.ts:122` 读 `phase`）；`TaskMeta`（`worker-mode.ts:291-340`）无卡片字段。
- 按 run 窗口枚举 `<key>/evidence/**` 的代码：未找到。
  证据：唯二相关实现 `deliverable-evidence.ts:153` 与 `change-ledger.ts` `resolveDeliverablePath` 都以报告文本 token 为入口。

## 未覆盖面声明

- **未跑任何测试**：本任务为只读研究边界（禁 `npm install/ci`、`git checkout/reset/clean/stash`、`npm run build`、全量 `./test.sh`）。§5 的“会翻转”结论来自对断言文本与实现路径的静态比对，未实际执行。
- **未做 6 实例全量重放**：逐字段核对的只有 `wjg-w12-negative-space-audit`；另外只对 `mw-write-face-guard` 5 条 trace 做了 `[CHECKPOINT]` 行计数（=0）。
- **未读 worker-mode.ts 全文**：只读了与本 RQ 相关的区段（:140-300、:1900-2140、:2280-2900）及其调用的 helper 模块。
- **未定位部署态差异**：`~/.pi/agent/extensions/agent-team-loop.js` 与 `packages/multi-workers/dist/...` 的 mtime 均为 2026-10-14 08:38（晚于 wjg-w12 运行），故无法排除运行期 bundle 差异；§2 对 `risk=mid` 的解释仅基于记录时间戳（1,799,991 ms vs 1,800,000 ms）与当前源码逻辑，已标注为有界解释。
- **未做的耦合实验**：未用 fake timers 实证“改 risk 不影响 idle/wall”；结论来自代码路径无共享输入（§6 已给证据）。
- **未量化** AC-010 所指“既有语料统计”的入口（不在本 RQ 范围）。

## 证据

- 源码逐条坐标见 §1~§6（文件均为 `packages/coding-agent/src/extensions/agent-team-loop/` 下）。
- 工件坐标：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w12-negative-space-audit/{trace.log,run.json,progress.md,output.md,report-negative-space-audit-20261013.md}`；`.agenticdoc/mw-write-face-guard/workers/*/trace.log`。

## 残留与未验证

- `risk=mid` 的边界解释（1,799,991 ms）未在运行期复现验证，仅由 trace 时间戳推得。
- `report-<slug>.md` 是否是 S3 补齐的目标文件（是否需要把 `agentProductText` 扩展到它）留待 design 决策；本报告只给出“现状不读它”的代码事实。
- I1 的自检回合在**多 phases** 任务上的语义（每个 phase 后自检 vs 仅最终）未定，属 design 范围。

## 上下文来源

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（:140-300、:539-553、:1900-2140、:2280-2900）
- `worker/output-writer.ts`、`worker/output-sections.ts`、`worker/worker-file-tool.ts`
- `shared/heartbeat.ts`、`shared/change-ledger.ts`、`shared/deliverable-evidence.ts`、`shared/run-store.ts`、`shared/task-frontmatter.ts`
- `pm/pm-orchestrator.ts`（:1390-1445）、`pm/ui-bridge.ts`（:150-200、:470-660、:2020-2060）
- `.agenticdoc/mw-worker-output-contract/{spec.md,tasks/T-RQ4-checkpoint-settle.md}`
- 历史工件：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w12-negative-space-audit/**`、`.agenticdoc/mw-write-face-guard/workers/*/{trace.log,run.json}`
- 测试：`packages/coding-agent/test/extensions/{agent-team-loop,agent-team-loop-checkpoint-wiring,agent-team-loop-watch-aggregate}.test.ts`、`test/suite/{dispatch-recovery-terminal,output-recovery-contract,mwds-t04-deliverable,mwds-t12-regression,mwgal-t17-ledger-role-aware}.test.ts`、`packages/multi-workers/test_{launcher,mwds_t07_reap_productfirst,run_identity,common,integration,task_type_parity}.py`

[VERIFY] checkpoint_chain: trigger=time_only(scheduleCheckpoint :2568/:2576); anchor=min(30m,budget/2)(:250-252); reads/writes tools=READ_TOOLS(5)+WRITE_TOOLS(2)(:260-262); risk_rules=3 branches(:283-286); escalation=pm-orchestrator.ts:1417-1419 -> ui-bridge.ts:175-185 triggerTurn; wjg-w12: reads=111=46+51+9+5, WRITE_FILE=4, worker_file_tool_calls=4, CHECKPOINT_lines=1, report_bytes=37149(mtime 17:32:12) vs checkpoint 17:33:36 writes=0/uniq=0/risk=mid, ts_delta_ms=1799991<anchor 1800000; mw-write-face-guard CHECKPOINT_lines=0 across 5 traces; computeRisk_unit_assertions=5; pytest_hits_on_CHECKPOINT=0; insertion_points=2 (I1 agent_settled:2811-2822, I2 finishSuccess:2713-2720)
