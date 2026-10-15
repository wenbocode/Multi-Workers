# T-DR4: 检查点判据（writeless 落盘信号）与看门狗不变量设计

- Key: mw-worker-output-contract
- 任务: T-DR4-checkpoint-invariants（research，只读仓库 + 写本任务目录与唯一证据文件）
- 唯一证据文件: `.agenticdoc/mw-worker-output-contract/evidence/research/design-rq4-checkpoint-invariants-20261014.md`
- 卡: `tasks/T-DR4-checkpoint-invariants.md`（sha256 `c56df4b101e4cb8cbb2f5b792ea57724fe60c0449a6c0ce979a2147c4d3d67cd`）
- 上游: spec §1.5 P5 / §1.6 S5 / §3 **AC-009** / §4 R5,R9；`evidence/research/spec-rq4-checkpoint-settle-20261014.md`
- 方法边界: 静态读取源码与已落盘工件 + `文件:行号`/字节核对；**未修改仓库任何文件**；**未跑任何测试**（禁全量 `./test.sh`、禁 build/install/git 变更）；所有命令为只读查询。

## 0. 结论与决策

| 问题 | 决策 |
|---|---|
| Q1 修入参 vs 改判据 | **混合，判据为主**：不重定义 `writes`/`uniq_targets`（保持字段语义与全部既有断言）；新增一组**与账本同源**的落盘信号（`landed`/`lastLandingAgeMs`/`artifactPresent`/`progressDone`）供 `computeRisk` 的 writeless 分支消费。 |
| Q1 同源与去重 | 计数来源 = `parseWriteFileEvents`（`shared/change-ledger.ts:148`），与 D3 账本同一语法（`formatWriteFileEvent` :115）；按归一化后的**不同路径**计数（解析器自带 `seen` 去重 :150-157），不叠加 `[TOOL] worker_file`，不按通道重复计数。 |
| Q2 computeRisk | 单个导出函数，新增可选字段；`s.landed === undefined` ⇒ 原三支逐字节不变（write 角色零变化）。writeless：产物在盘 ⇒ `low`；零落盘且过锚点 ⇒ `high`；落盘但陈旧且无产物 ⇒ 按 `repeatTop>=4`/phases 停滞取 `mid`，否则 `low`。 |
| Q3 `[CHECKPOINT]` 字段 | 在**同一行尾部**追加可选字段 `land=<n> last_land=<s>s|- artifact=<yes|no> done=<yes|no>`，**仅 writeless 角色**输出（write 角色行字节不变）；`CHECKPOINT_LINE_RE` 用可选非捕获组扩展，旧行/新行都可解析；**不新增 trace 行**。 |
| Q4 不变量 | idle(10m)/wall(默认60m)/deadline steer 三段的输入与 `risk` 无耦合（逐段证据见 §4）；checkpoint 节奏与每拍行数不变；steer 发送**不**按 `risk` 门控。 |
| Q5 steer 文案 | writeless 分支**需要改**（否则提示语仍把 `writes=0` 当发散，与判据自相矛盾）；coding 分支字节不变；`deliverAs:"followUp"` 不变；`CKPT <n>m converging=yes|no` 指令不变（否则 `progressDone` 解析器失效）。 |
| Q6 AC-009 测试 | 双层：`computeRisk` 纯函数用例（正/负/边界）+ 一个 wjg-w12 形态的 fake-timer 夹具回放；另加 3 例 writeless 看门狗不变性用例；既有 5 条 legacy `computeRisk` 断言与字节锚定断言全列回归清单。 |

## 1. 修法路径的决策

### 1.1 现状事实（设计前提，逐条给坐标）

`[CHECKPOINT]` 的写/读两段计数只认 `write`/`edit` 工具：

- `worker-mode.ts:260-262`（原文）：
```
const READ_TOOLS = new Set(["read", "grep", "find", "ls", "glob"]);
/** Write-ish tools for checkpoint convergence signals. */
const WRITE_TOOLS = new Set(["write", "edit"]);
```
- 采样点 `worker-mode.ts:2345-2353` 只在上述两个集合命中时改变 `writeCount`/`writeTargets`：
```
		if (READ_TOOLS.has(event.toolName)) {
			readCount++;
			if (target) readCounts.set(target, (readCounts.get(target) ?? 0) + 1);
		} else if (WRITE_TOOLS.has(event.toolName)) {
			writeCount++;
			if (target) writeTargets.add(target);
			pendingWriteTargets.set(event.toolCallId, target);
```
- 检查点把这两个计数器原样送入判据与行（`worker-mode.ts:2515-2529`）：`writes: writeCount`、`uniqTargets: writeTargets.size`。
- `worker_file` 只在 writeless 角色注册（`worker-mode.ts:2131-2134`：`const hasWriteTools = toolsForType(meta.type).includes("write"); if (!hasWriteTools) { … registerWorkerFileTool … }`），且**不进** `WRITE_TOOLS` ⇒ writeless 角色的 `writes=0`/`uniq_targets=0` 是结构性恒真（**入参缺陷**，非规则缺陷）。

但三条落盘通道**都已经进账本** `[WRITE_FILE]`：

- `write`/`edit` 成功：`worker-mode.ts:2385-2389`（`appendWriteFileEvent(tracePath, repoRelativePath(writeTarget))`）。
- `bash` 已知写目标成功：`worker-mode.ts:2390-2400`（循环 `for (const bashTarget of bashWrites ?? [])`）。
- `worker_file` 成功：`worker-file-tool.ts:82`（`appendWriteFileEvent(path.join(taskDir, "trace.log"), repoRelativePath(target));`）。

账本语法/解析的唯一来源是 `shared/change-ledger.ts`：

- `:115` `export function formatWriteFileEvent(filePath: string): string`
- `:123` `export function appendWriteFileEvent(tracePath: string, filePath: string): void`
- `:135` `const WRITE_FILE_LINE_RE = /^\[WRITE_FILE\][ \t]+path=(.+?)[ \t]*$/;`
- `:148-160` `parseWriteFileEvents`：`seen` Set 去重后按出现顺序返回**不同**路径。

实测反证（wjg-w12，本仓工件）：`trace.log` 4 条 `[WRITE_FILE]` = 3×`progress.md` + 1×`report-negative-space-audit-20261013.md`，恰对应 4 次 `worker_file` 调用；`report-…md` 37,149 B 于 `17:32:12` 落盘；检查点 `17:33:36` 仍写 `reads=111 writes=0 phases=- uniq_targets=0 repeat_top=16 risk=mid`。命令与输出见 §7「证据」。

### 1.2 决策：混合，且判据为主

- **(ii) 改判据（主）**：检查点真正想问的是「这个 writeless run 有没有在产出」，而不是「它调没调 write 工具」。落盘信号 = 账本事件 + 磁盘产物 + 完成记录，三者都与工具名解耦。
- **(i) 修入参（辅，且只加新信号）**：把「成功落盘」这一根因纳入判据输入，但**不**把它塞回 `writes`/`uniq_targets`。理由：
  1. `writes` 已被 `[CHECKPOINT]` 行、`CheckpointInfo`、PM 升级文案与多条 pinned 测试（§3.3）当作「write/edit 调用数」消费；重定义会同时改观测语义与断言文本。
  2. 用 `bash` 命令文本抽取出的候选目标（`extractBashWriteCandidates`，`worker-mode.ts:1554`）当写计数，会把 P4/R9 已知的乱码目标当落地（`wfg-rq2` 的 `path=`:1175``、`wfg-rq3` 的 `path=, .agenticdoc/_aut + opilot)`），从而**用假证据压掉真发散**——spec §1.7 第 4 条明确禁止。
  3. 账本已是三条通道的公共出口；改判据只需读账本，不需要在 `tool_execution_start` 再加计数分支。
- AC-009 的「根因须同时处理（修入参或改判据二者至少一处）」由此满足：根因（检查点从未看见 `worker_file`）在**新信号**里被处理，且该信号与账本同源。

### 1.3 混合方案的边界（硬约束）

1. **不改** `WRITE_TOOLS`/`READ_TOOLS`；**不改** `tool_execution_start` 的分支（不给 `worker_file` 加计数）。
2. **不改** `writeCount`/`writeTargets`/`readCounts` 的任何写入点；新信号是**派生物**，不进 `[CHECKPOINT]` 的既有字段。
3. **只读**账本：检查点路径调 `parseWriteFileEvents`，绝不调用 `appendWriteFileEvent`（不得自造账本）。
4. `computeRisk` 只新增 writeless 分支；`s.landed === undefined` 时必须走原三支（write 角色零变化）。
5. **不新增 trace 行、不新增定时器/轮询**（spec §2.2）；新字段追加在既有 `[CHECKPOINT]` 行尾部。
6. **不按 `risk` 门控 steer 发送**（§4.1 的不变量理由）。
7. 产物存在性用 `findNonEmptyReport`（`deliverable-evidence.ts:105`）复用 settle 的同一判据，不另写第二份白名单。

### 1.4 与账本（D3）同源与去重

- 同源：`landed` 只由 `parseWriteFileEvents(traceText)` 得到（`change-ledger.ts:148`）。`formatWriteFileEvent`（:115）是写侧唯一格式源，`WRITE_FILE_LINE_RE`（:135）是读侧唯一语法，二者与 settle 的 `diffLedger`/`readTerminalGaps` 完全相同。
- 去重：`parseWriteFileEvents` 返回**不同路径**（`:150-157` 的 `seen`）。wjg-w12 的 3 次 `progress.md` 追加 ⇒ `landed` 计 1 个 `progress.md` 目标，不是 3。
- 防重复：`worker_file` / `write`/`edit` / `bash` 每次**成功**调用各在**唯一**调用点写 1 条事件（`worker-file-tool.ts:82`、`worker-mode.ts:2385-2400`）；解析器按路径去重 ⇒ 同一文件被多通道写也只算一个目标。**禁止**再加入 `[TOOL] worker_file` 作为第二来源（那会与账本重复计数）。
- 账本不可判（AC-017 的 `unjudgeable`）时的兜底：`artifactPresent` 走磁盘真值——`findNonEmptyReport(taskDir)`（`deliverable-evidence.ts:105-119`）+ 对 landed 目标的存在性 `stat` + `<key>/evidence/**` 的**有界**新近遍历。真实产物即使漏了事件也会被磁盘信号救回，不落入 `high`。
- **不改** `unjudgeable` 的既有定义位置（AC-017 属另一任务）；检查点只是**消费**账本。

### 1.5 判据落点的 I/O 预算

- 位置：`writeCheckpoint()` 内（`worker-mode.ts:2510`），仅当 `!hasWriteTools` 时计算信号；write 角色零额外 I/O。
- 每次检查点（锚点一次 + 每 10m 一次）新增：读 `trace.log`、读 `progress.md`、对 landed 目标 `statSync`、有界遍历 `<key>/evidence/**`（建议：深度 ≤5、条目上限 500、跳过目录/符号链接）。单拍成本与 `readTerminalGaps` 同级，不新增线程/定时器。
- 新增模块建议：`worker/landing-signals.ts`（导出 `collectLandingSignals`），避免让 `output-writer.ts` 再增依赖；`writeCheckpoint` 导入它。它只依赖 `change-ledger.ts` 与 `deliverable-evidence.ts`（后者已经导入 `worker-file-tool.ts`，无环）。

## 2. `computeRisk` 新规格

### 2.1 新入参（可选，保证向后兼容）

```ts
export interface ConvergenceSignals {
	elapsedMs: number;
	anchorMs: number;
	writes: number;
	phasesTotal: number;
	phasesDone: number;
	repeatTop: number;
	/** Writeless-only landing signals (design DR4). Undefined ⇒ legacy rule. */
	landed?: number;                 // distinct recorded landing targets
	lastLandingAgeMs?: number;       // now - newest existing landing mtime; undefined = none known
	artifactPresent?: boolean;       // a non-empty product exists on disk
	progressDone?: boolean;          // progress.md carries a completion record
}
```

`landed === undefined` 是 write 角色路径；`landed` 一旦给出（即使为 0）即进入 writeless 分支。

### 2.2 新规则（替换/扩展，逐分支）

```ts
const LAND_FRESH_FLOOR_MS = 60_000;
/** Freshness window for a landing: one third of the anchor, floored at 1m.
 * Default anchor 30m ⇒ 10m (= the checkpoint refresh cadence). */
export function landFreshMs(anchorMs: number): number {
	return Math.max(LAND_FRESH_FLOOR_MS, Math.round(anchorMs / 3));
}

export function computeRisk(s: ConvergenceSignals): "low" | "mid" | "high" {
	// ── writeless path (taken only when the caller supplied landing signals)
	if (s.landed !== undefined) {
		const stalled = s.phasesTotal > 0 && s.phasesDone === 0 && s.elapsedMs >= s.anchorMs;
		// W2a — a non-empty product on disk is the strongest convergence evidence
		// and outranks a missed ledger event (channel-independent ground truth).
		if (s.artifactPresent === true) return "low";
		// W1 — nothing landed at all past the anchor = pure exploration (unchanged intent).
		if (s.landed === 0 && s.elapsedMs >= s.anchorMs) return "high";
		// W2b — a fresh landing plus the role's own "converging=yes" note.
		const fresh = s.lastLandingAgeMs !== undefined && s.lastLandingAgeMs <= landFreshMs(s.anchorMs);
		if (s.landed > 0 && fresh && s.progressDone === true) return "low";
		// W3/W4 — landed-but-stale, or landed nothing before the anchor: only
		// read-spin / stalled phases are mid, everything else is low.
		return stalled || s.repeatTop >= 4 ? "mid" : "low";
	}
	// ── write roles: byte-for-byte the pre-change rule
	if (s.writes === 0 && s.elapsedMs >= s.anchorMs) return "high";
	if ((s.phasesTotal > 0 && s.phasesDone === 0 && s.elapsedMs >= s.anchorMs) || s.repeatTop >= 4) return "mid";
	return "low";
}
```

分支语义表：

| 分支 | 判据 | 取值 | 与旧规则关系 |
|---|---|---|---|
| W2a | `artifactPresent === true`（非空产物在盘） | `low` | 新增；对 wjg-w12 是唯一生效分支 |
| W1 | `landed === 0 && elapsedMs >= anchorMs` | `high` | 旧 `writes===0 && past anchor` 的 writeless 等价物（意图不变） |
| W2b | `landed > 0 && fresh(≤ anchor/3, ≥1m) && progressDone` | `low` | 新增；给「刚落盘但尚无产物文件」的收尾窗口 |
| W3 | `landed > 0` 且不满足 W2 | `stalled \|\| repeatTop>=4 ? mid : low` | 旧的 `repeatTop>=4`/phases 停滞保留，但**被 W2a/W2b 优先压过** |
| W4 | `landed === 0 && elapsedMs < anchorMs` | `stalled?`（不可能）`repeatTop>=4 ? mid : low` | 同旧规则的锚点前行为 |

阈值与理由：
- `landFreshMs = max(60s, anchor/3)`。默认 `anchor = min(30m, budget/2) = 30m` ⇒ 10m，正好是 `CHECKPOINT_REFRESH_MS`（`worker-mode.ts:208`）——「上次检查点以来落过盘」= 新鲜。小预算冒烟（budget 2m ⇒ anchor 60s）⇒ 20s→floor 60s，仍可测。
- `repeatTop >= 4` 沿用旧值（`worker-mode.ts:285`），不引入新魔法数。
- `phases` 停滞沿用旧的 `phasesTotal>0 && phasesDone===0 && elapsed>=anchor` 语义。

### 2.3 落盘信号的采集规格（`collectLandingSignals`）

输入：`taskDir`、`keyDir`（`.agenticdoc/<key>`）、`projectRoot`（`process.cwd()`，launcher 保证 worker cwd=项目根）、`startedAtMs`、`nowMs`、`traceText`、`progressText`。

1. `targets = parseWriteFileEvents(traceText)`；`landed = targets.length`。
2. `abs = targets.map(t => path.isAbsolute(t) ? t : path.resolve(projectRoot, t))`。
3. `existing = abs.filter(p => { const s = statSync(p); return s.isFile() && s.size > 0; })`（best-effort，异常即跳过）。
4. `artifactPresent = findNonEmptyReport(taskDir) !== undefined
   || existing.some(p => path.basename(p) !== "progress.md")
   || recentEvidence(keyDir, startedAtMs).length > 0`。
5. `recentEvidence`：有界遍历 `<keyDir>/evidence/**`，保留 `isFile() && size>0 && mtimeMs >= startedAtMs`（复用 R1 反伪造的 run-start 口径，`deliverable-evidence.ts:160-176` 同思路）。
6. `lastLandingAgeMs = nowMs - max(mtimeMs over existing ∪ recentEvidence)`；集合为空 ⇒ `undefined`。
7. `progressDone = /(^|\n)(?:##\s*完成记录|CKPT\s+\d+m\s+(?!\[machine\])(?=[^\n]*converging=yes))/.test(progressText)`。第二条正是 steer 要求 agent 写的那一行（`worker-mode.ts:182-190`），`(?!\[machine\])` 排除框架机器行（`output-writer.ts:504`）。

`recentEvidence` 关闭 RQ-4 §2 的 S-d 盲区（全仓无按 run 窗口枚举 `evidence/` 的代码）与 S-h 盲区（`collectArtifacts` 不列 `report-<slug>.md`，`run-store.ts`）。**该遍历只读，不写任何文件。**

### 2.4 writeless 与 write 角色共用同一函数

**共用**。`computeRisk` 保持唯一导出与唯一实现；角色切分放在调用方（`writeCheckpoint`，已有 `!hasWriteTools` 分支，`worker-mode.ts:2131/2536`）。理由：

- `computeRisk` 是既有导出 API，被 5 条单测直接锁定（`agent-team-loop.test.ts:4061-4117`）；拆成第二个函数会复制分支结构并分裂测试面。
- 可选字段让「角色差异」变成入参差异，write 角色传 `undefined` 时行为逐字节不变（§4.5）。
- 机器行与尾字段的门控都复用同一个 `!hasWriteTools`，保证「有 `[machine]` 行 ⇔ 有尾字段」，不产生第三种组合。

### 2.5 6 个历史实例的预期 `risk` 变化

实例集合取自 spec §1.5 P1/P5 的语料：`wjg-w12-negative-space-audit`、`wjg-qg-evidence-closure`、`wjg-w15-delta-adversarial`、`wfg-rq2-enforcement`、`wfg-rq3-safety`、`wfg-rq-d2-runtime-guard`。逐条核对（`run.json` + `task.md` + `trace.log` + 目录）：

| 实例 | type | 运行时长 | anchor | 观测 `[CHECKPOINT]` | 旧 risk | 落盘事实 | 新 risk | 变化 |
|---|---|---|---|---|---|---|---|---|
| wjg-w12 | review | 33.1m | 30m | 1 条 | mid | `[WRITE_FILE]`=4，distinct=2（progress.md、report-…md 37,149 B），report mtime 17:32:12（检查点前 84s），progress.md 有 `CKPT 30m converging=yes` | **low** | **mid→low（AC-009 正例）** |
| wjg-qg | review | 16.3m | 30m | 0 条 | 无 | `[WRITE_FILE]`=1（report-quality-gate-report-…md） | 未触发（N/A） | 运行 < anchor，无检查点 |
| wjg-w15 | review | 27.4m | 30m | 0 条 | 无 | `[WRITE_FILE]`=3，distinct=2（progress.md、report-delta-adversarial-audit-…md） | 未触发（N/A） | 运行 < anchor |
| wfg-rq2 | research | 7.0m | 30m | 0 条 | 无 | `[WRITE_FILE]`=2，均为 P4 伪路径（`:1175`、`:1184`） | 未触发（N/A） | 运行 < anchor；AC-017 后伪事件会被抑制 |
| wfg-rq3 | research | 12.0m | 30m | 0 条 | 无 | `[WRITE_FILE]`=2，均为伪路径（`, .agenticdoc/_aut + opilot)`，distinct=1） | 未触发（N/A） | 运行 < anchor |
| wfg-rq-d2 | research | 10.8m | 30m | 0 条 | 无 | `[WRITE_FILE]`=4，distinct=2（report.md、evidence/research/design-runtime-guard-…md） | 未触发（N/A） | 运行 < anchor |

结论：**6 例中只有 wjg-w12 有一个可重放的 `risk` 观测**，其变化 mid→low 正是 AC-009 要求的正例；其余 5 例运行时长均小于 30m 锚点，从未写过 `[CHECKPOINT]` 行，因此新判据**未被行使**，不存在「预期变化」（对它们做任何预测都只是假设，已在 §2.5 标注为 N/A，不充当证据）。这也说明 AC-009 的语料回放只需要 1 个真实正例 + 1 个构造负例，而不需要 6 例全跑。

## 3. `[CHECKPOINT]` 行新字段与解析器兼容

### 3.1 新格式（同一行尾部追加，仅 writeless）

```
[CHECKPOINT] <iso> elapsed=<s>s reads=<n> writes=<n> phases=<d/t|-> uniq_targets=<n> repeat_top=<k> risk=<low|mid|high> land=<n> last_land=<n>s|- artifact=<yes|no> done=<yes|no>
```

- `land` = distinct 落盘目标数（= `landed`）。
- `last_land` = 距最近一次落盘的秒数；`land>0` 但无现存目标（曾写后删）时为 `-`。
- `artifact` = `findNonEmptyReport`/目标存在性/evidence 新近遍历的合并判定。
- `done` = `progressDone`。
- **write 角色不输出尾字段**，行保持与今日逐字节一致（理由：`writes` 字段语义不变；避免 `agent-team-loop.test.ts:4144` 的字节锚定与 `pm/` 消费者文本变化）。

wjg-w12 在新规则下的等价行：

```
[CHECKPOINT] 2026-10-13T17:33:36.128Z elapsed=1800s reads=111 writes=0 phases=- uniq_targets=0 repeat_top=16 risk=low land=2 last_land=84s artifact=yes done=yes
```

### 3.2 解析器改动（`shared/heartbeat.ts:84-85`）

现状（原文）：
```
const CHECKPOINT_LINE_RE =
	/^\[CHECKPOINT\] (\S+) elapsed=(\d+)s reads=(\d+) writes=(\d+) phases=(\S+) uniq_targets=(\d+) repeat_top=(\d+) risk=(low|mid|high)$/;
```
改为（尾字段整体可选）：
```
const CHECKPOINT_LINE_RE =
	/^\[CHECKPOINT\] (\S+) elapsed=(\d+)s reads=(\d+) writes=(\d+) phases=(\S+) uniq_targets=(\d+) repeat_top=(\d+) risk=(low|mid|high)(?: land=(\d+) last_land=(\S+) artifact=(yes|no) done=(yes|no))?$/;
```
`CheckpointInfo` 追加可选字段（旧行/旧 bundle 解析后为 `undefined`）：
```ts
	land?: number;
	lastLandingS?: number;      // "84s" -> 84; "-" -> undefined
	artifactPresent?: boolean;  // "yes"/"no"
	progressDone?: boolean;
```
`readTaskProgress` 的赋值块（`heartbeat.ts:160-171`）增加 4 个条件赋值；缺失尾字段时不设值。

### 3.3 兼容性核对（逐消费者）

| 消费者 | 位置 | 为何不受影响 |
|---|---|---|
| PM 发散升级 | `pm/pm-orchestrator.ts:1417-1419`（`ifs (!ck || ck.risk === "low") continue;`） | 只读 `ck.risk`；新字段被忽略。**建议**（非必须）在 `:1426-1431` 的文案里补 `落盘 land=… 产物=…`，否则 PM 读到 `writes=0` 仍可能自行推断发散。 |
| widget 聚合 `risk=high:K` | `pm/ui-bridge.ts:881`（`checkpoint?.risk === "high"`） | 只读 `risk`。 |
| watch 行 ⚠ 徽标 | `test/extensions/agent-team-loop.test.ts:4171` 断言 `ck30m high⚠` | 只读 `risk`。 |
| `[machine]` 行 | `output-writer.ts:503-507` | **本次不改**，`MACHINE_LINE_RE`（checkpoint-wiring 测试）与 `VC-001/002/003` 不受影响。 |
| 字节锚定测试 | `agent-team-loop.test.ts:4144`（`toMatch` 无尾字段） | 该测试直接调 `appendCheckpoint` 且不传新字段 ⇒ 不产生尾字段 ⇒ 仍匹配。 |
| 原始行夹具 | `agent-team-loop.test.ts:4229/4282/4322/4375/4429`、`watch-aggregate.test.ts:151+` | 手写 `[CHECKPOINT]` 行不带尾字段 ⇒ 可选组不匹配 ⇒ 仍解析。 |
| Python / `mw doctor` | RQ-4 §5：0 处引用 `[CHECKPOINT]`/`computeRisk` | 无影响。 |

### 3.4 被否决的替代方案

- **独立新行**（如 `[LANDING]`）：spec §2.2 禁止每个检查点增加 trace 行数；且需要新的解析入口。
- **只改 `[machine]`（progress.md）而 trace 行不动**：PM 升级读的是 trace 行（`readTaskProgress`），改机器行对机器判据无效；且会翻转 `MACHINE_LINE_RE`/VC-001。
- **尾字段设为必填**：会让旧 bundle 的 `[CHECKPOINT]` 行解析失败 ⇒ `readTaskProgress().checkpoint` 变 `undefined` ⇒ PM 发散升级**静默消失**（回归）。必须可选。

## 4. 不变量证明（逐条证据）

### 4.1 activity idle 看门狗（10m）

- 调度与判据：`worker-mode.ts:2589-2646`。输入只有：`taskDone`、`now - lastActivityAt`（`:2594`）、in-flight 工具表 `freshestInFlightTool()`（`:2600-2603`）、`toolIdleMs`（`:2604`）、`idleMs`（`:2621`）、`lastDeltaAt`（`:2627`）、`lastToolAt`（`:2641`）。**全程不读 `risk`/`writes`/`writeCount`/`lastCheckpoint`/落盘信号。**
- 唯一间接耦合：`writeCheckpoint()` 末尾无条件 `pi.sendUserMessage(..., {deliverAs:"followUp"})`（`worker-mode.ts:2556-2566`），该 followUp 回合产生 `turn_start`/`message_start` ⇒ `touch()` 顺延 `lastActivityAt` 一拍（RQ-4 §6 已述）。本次设计**保留无条件发送**（§5.4），因此顺延次数不变；新增的 4 个信号只进 `computeRisk` 返回值与该行文本，不进该函数的控制流门控。
- 锁定测试（现存，必须保持通过）：`agent-team-loop.test.ts:4512`（`AC-001: no activity for idleMs kills…`，断言 `exit(1)` + `idle: no activity for 60s` + `output.md` 不含 `checkpoint:`）、`:4538`（token 增量不杀）、`:4577`（多 phases 仍覆盖）。

### 4.2 墙钟看门狗（默认 60m）

- `budgetMs = resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS)`（`worker-mode.ts:2450`，实现 `:212-217`，默认 `DEFAULT_BUDGET_MS = 60*60_000`，`:199`）。
- `wallTimer = setTimeout(..., budgetMs)`（`:2650-2654`），handler 只读 `lastActivityAt`。
- **无 `risk` 输入。** 锁定测试：`agent-team-loop.test.ts:4604`（`AC-002/003/004: deadline steer, checkpoint steer and wall kill fire in order…`，断言 `wall: budget 180s exceeded` + `exit(1)`）。

### 4.3 deadline steer（预算尾段）

- `steerAtMs(budgetMs) = max(1s, budgetMs - min(5m, budget/4))`（`worker-mode.ts:255-257`），`steerTimer` 在 `:2577-2587` 触发，文案为常量 + 预算余量，**不含 `risk`**；`deliverAs:"steer"`。
- 锁定测试：同上 `:4604`，断言 `[mw deadline]` 消息 `deliverAs === "steer"`。

### 4.4 checkpoint 节奏与 trace 行数

- 唯一调度器 `scheduleCheckpoint`（`:2568-2576`）：首拍 `riskAnchorMs`（`= min(30m, max(1s, budget/2))`，`:250-252`），此后固定 `CHECKPOINT_REFRESH_MS`（`:208`，10m）。本次不改这两个常量，不改 `scheduleCheckpoint`。
- `writeCheckpoint` 仍写：1 条 `[CHECKPOINT]`（`:2523`）+ 仅 writeless 的 1 条 `[machine]`（`:2536-2537`）+ 1 条 steer（`:2556`）。行数不变（spec §2.2）。
- 锁定测试：`checkpoint-wiring.test.ts` `VC-001/VC-002`（"exactly one `[machine]` line"）与 `agent-team-loop.test.ts:4120`（appendCheckpoint 解析）。

### 4.5 write 角色字节兼容

- `s.landed === undefined` ⇒ `computeRisk` 走原三支（代码逐字相同）。
- `appendCheckpoint` 尾字段只在 `!hasWriteTools` 时组装 ⇒ coding/repair/roadmap-writer 等行不变。
- 锁定测试：`agent-team-loop.test.ts:4061-4117`（5 条 legacy `computeRisk` 断言）、`agent-team-loop.test.ts:4144`（行字节正则）、`checkpoint-wiring.test.ts` `VC-003`（type=coding 无 `[machine]` 行）、`VC-004`（coding steer 与冻结基线逐字节相同）。

### 4.6 「3 例看门狗行为不变」的验证方式

见 §6.5：对 writeless（`type: research`）新增 3 条 fake-timer 用例——正常活跃、真挂死、预算尾段——断言的重点是**时序/退出码/`[TIMEOUT]`/steer 顺序**，与 `risk` 取值无关；同时保留现存 3 条 coding 用例作为对照。

## 5. steer 文案

### 5.1 现状（`worker-mode.ts:170-190`）

- `hasWriteTools === true`：字节冻结基线，要求 agent 自己用 write 工具把 `CKPT <n>m converging=yes|no eta≈<X>m <理由>` 追加到 `progress.md`。
- `hasWriteTools === false`（writeless）：说明「检查点机器证据（reads/writes/phases/risk）已由框架写入 `progressPath`」，要求用 `worker_file` 或回复给出一行 `CKPT <n>m converging=yes|no …`。

### 5.2 是否需要改：**需要（仅 writeless 分支）**

- 现文案把 `writes` 当作主要机器证据。改判据后，writeless 的收敛信号是「落盘 + 产物 + 完成记录」；若文案仍只报 `reads/writes/phases/risk`，agent 看到 `writes=0` 会继续按 P5 的失效模式自判发散并展开新工作——提示语与判据自相矛盾。
- 改动仅限 `hasWriteTools === false` 分支；`true` 分支**逐字节不动**（`VC-004` 基线）。

### 5.3 改法（最小编辑）

在 writeless 分支的 `检查点机器证据（reads/writes/phases/risk）已由框架写入 …` 处改为点明落盘信号与角色事实，例如：

> `[mw checkpoint] 运行 …（总预算 …）。检查点机器证据（reads/writes/phases/risk + 落盘 land/最近落盘时长/产物存在性）已由框架写入 <progressPath>。本角色没有 write/edit 工具，`writes=0` 属正常；框架判据看的是落盘事件与产物，不是你用没用 write 工具。请立即自评收敛性：用 worker_file 工具把一行自评写入该文件，或在本回复中直接给出一行 `CKPT <n>m converging=yes|no eta≈<X>m <一句话理由>`。若不收敛：立即收窄范围，优先保证已完成部分可交付，不要展开新工作。`

必须保留（测试与解析依赖）：
- 字面 `worker_file`（`VC-004` 断言 `toContain("worker_file")`，实际用 `opts.narrowTool` 插值）。
- 字面 `converging=yes|no`（`VC-004` 断言；同时是 `progressDone` 解析器的输入端）。
- `progressPath` 值（`VC-004` 断言 `PROGRESS_SAMPLE` 出现）。
- 不得出现「追加到 …progress.md」这一 write 工具句式（`VC-004` 的 `not.toMatch(/追加到.*progress\.md/)`）。

### 5.4 明确不改的部分

- 发送时机与 `deliverAs`：仍在 `writeCheckpoint` 内无条件发送、仍 `deliverAs:"followUp"`。**不**按 `risk` 门控发送（否则会改变 idle 的 `lastActivityAt` 顺延次数，破坏 §4.1 的不变量论证）。
- `CKPT <n>m converging=…` 的自评行格式：它是 `progressDone` 的唯一机读输入，改动会使 AC-009 正例失去判据。

## 6. AC-009 的测试形态

### 6.1 用例文件与夹具

- **纯函数层（主锁）**：`packages/coding-agent/test/extensions/agent-team-loop.test.ts` 的 `AC-004: computeRisk`（现 `:4061-4117`）同 describe 内新增 writeless 用例，或新建 `test/extensions/agent-team-loop-checkpoint-invariants.test.ts`。无需 fs/timers，确定性最高。
- **夹具回放层（集成）**：`test/extensions/agent-team-loop-checkpoint-wiring.test.ts` 已具备 `fakeWorkerPi()` + `startWorker()` + `trickleToAnchor()` + `vi.useFakeTimers()` 全套（`:120-186`），**直接复用**在同一文件新增 describe。夹具为 wjg-w12 形态：
  - `task.md`：`type: review\ntimeout: 2\n\nreview\n`（anchor = min(30m, 60s) = 60s）。
  - 预置 `report-negative-space-audit-20261013.md`（非空，mtime = now-84s）。
  - 预置 `progress.md`：`## 完成记录（2026-10-13）\n…\nCKPT 30m converging=yes eta≈0m 任务已完成…`。
  - 预置 `trace.log`：4 条 `[WRITE_FILE] path=<taskDir 相对>/progress.md|report-…md`（3＋1，模拟 wjg-w12）。
  - 断言 `readTaskProgress(taskDir).checkpoint` 的新字段。
- **看门狗不变性 3 例**：`test/extensions/agent-team-loop.test.ts` 的 watchdog describe（`:4505` 起）或新文件 `agent-team-loop-watchdog-invariants.test.ts`。

（若按仓库 `AGENTS.md` 的 regression 约定归档：主回归可放 `test/suite/regressions/woc-ac009-checkpoint-landing.test.ts`；但集成夹具依赖 `fakeWorkerPi`/fake timers，放 `test/extensions/` 与现有检查点套件同源更合适。二者择一，建议 extensions 侧。）

### 6.2 场景 A（已落盘 → `risk≠mid`，目标 `low`）

夹具：`landed=2`、`artifactPresent=true`、`lastLandingAgeMs≈84_000`、`progressDone=true`、`repeatTop=16`、`elapsedMs>anchor`。

断言：
```ts
expect(computeRisk({ elapsedMs: 31*60_000, anchorMs: 30*60_000, writes: 0, phasesTotal: 0, phasesDone: 0,
  repeatTop: 16, landed: 2, lastLandingAgeMs: 84_000, artifactPresent: true, progressDone: true })).toBe("low");
```
集成侧：
```ts
const ck = readTaskProgress(taskDir)?.checkpoint;
expect(ck?.risk).toBe("low");                       // AC-009 正例（PM 可见路径）
expect(ck?.land).toBe(2);
expect(ck?.artifactPresent).toBe(true);
expect(ck?.progressDone).toBe(true);
expect(ck?.risk !== "mid").toBe(true);              // AC-009 字面
expect(traceLine).toMatch(/risk=low land=2 last_land=\d+s artifact=yes done=yes$/);
// 升级链不触发：pm-orchestrator 的门禁 `ck.risk === "low"` ⇒ continue
```
> 说明：AC-009 字面写「`risk≠mid`」。本设计把目标钉在 `low`（产物在盘=收敛），并显式验证 `high` 也不出现——否则「≠mid」会被 `high` 蒙混，而 `high` 同样会 `triggerTurn` 唤醒 PM（`pm-orchestrator.ts:1417-1426`），等于没修。

### 6.3 场景 B（零落盘、无完成记录 → `≥mid`）

夹具：`landed=0`、`artifactPresent=false`、`progressDone=false`、`repeatTop=4`（或 0）、`elapsedMs>anchor`。

断言：
```ts
expect(computeRisk({ elapsedMs: 31*60_000, anchorMs: 30*60_000, writes: 0, phasesTotal: 0, phasesDone: 0,
  repeatTop: 4, landed: 0, lastLandingAgeMs: undefined, artifactPresent: false, progressDone: false })).toBe("high");
```
集成侧：同一 review 夹具去掉 report/progress 完成记录，`trace.log` 只留 0 条 `[WRITE_FILE]`；断言 `ck?.risk === "high"`（≥mid）、`land=0 artifact=no done=no`、且升级门禁 `risk !== "low"` 会命中。

边界补充用例（防回归）：
- 锚点前零落盘：`elapsedMs=20m, anchor=30m, landed:0, repeatTop:1` ⇒ `low`（旧行为不变）。
- 落盘但陈旧且无产物：`elapsedMs=31m, landed:1, lastLandingAgeMs=25m, artifactPresent:false, progressDone:false, repeatTop:1` ⇒ `mid`。
- write 角色向后兼容：原 5 条 legacy 断言逐条保持（`landed` 缺省 ⇒ 原分支）。

### 6.4 断言清单（可机械核对）

1. `computeRisk` 正例 `low`、负例 `high`、边界 3 例。
2. `[CHECKPOINT]` 行尾部正则 `risk=low land=2 last_land=\d+s artifact=yes done=yes$`。
3. `readTaskProgress(...).checkpoint.{risk,land,lastLandingS,artifactPresent,progressDone}` 全部断言（解析器兼容性证明）。
4. 尾字段**仅** writeless 出现：`type: coding` 夹具的行不匹配 `land=`，且与旧字节基线一致。
5. 旧行（无尾字段）仍可解析：写一条 `… risk=mid\n`，断言 `checkpoint.risk==="mid"` 且 `checkpoint.land===undefined`。

### 6.5 「3 例看门狗行为不变」的验证方式

在 fake-timer 下对 `type: research`（writeless，`PI_WORKER_IDLE_MS=60000`）各跑一例，断言只看时序与退出，不看 `risk`：

| 例 | 操作 | 断言 |
|---|---|---|
| 正常活跃 | 每 15s 发 `message_update`，跨过 anchor 与 2×idle | `exitSpy` 未被调用；trace 含 `[CHECKPOINT]`；无 `[TIMEOUT]`；`[END]` 不含 exit=1 |
| 真挂死 | 无任何事件，推进 `idleMs` | `exitSpy` 调用 `1`；trace 含 `[TIMEOUT] idle: no activity for 60s…`；`[END] exit=1` |
| 预算尾段 | budget 3m，15s×12 trickle，推进 180s | 消息顺序 `[mw checkpoint]`(followUp) → `[mw deadline]`(steer)；`wall: budget 180s exceeded`；`exit(1)` |

关键点：3 例中若发生落盘（例 1/3 可选地不落盘），`risk` 取值可不同，但**上述断言全部与 `risk` 无关**——这正是「判据改动不触碰看门狗」的可执行证明。现存 3 条 coding 对照用例（`:4512`/`:4538`/`:4604`）必须继续通过。

### 6.6 既有断言的回归清单（不得翻转）

- `agent-team-loop.test.ts:4061-4117`（5 条 legacy `computeRisk`）。
- `agent-team-loop.test.ts:4120-4152`（`appendCheckpoint` 字节正则 + `readTaskProgress` 解析）。
- `agent-team-loop.test.ts:4171`（widget ⚠）、`:4210`（PM 升级一次）、`:4407`（跨 key 低风险不投递）。
- `agent-team-loop.test.ts:4512/4538/4577`（idle）、`:4604`（checkpoint→deadline→wall 顺序）。
- `agent-team-loop-checkpoint-wiring.test.ts` 全组：`VC-001/VC-002`（一行 `[machine]`）、`VC-003`（coding 无机器行）、`VC-004`（coding steer 字节基线；writeless steer 不含 write 句式且含 `worker_file`/`converging=yes|no`）、`VC-005/VC-006`。
- `agent-team-loop-watch-aggregate.test.ts:151`（`risk=high` 计数）——若新判据使某夹具从 high 变 low，该夹具的原始行不带尾字段且 `landed` 缺省 ⇒ 仍走 legacy 分支，不翻转。

## 未覆盖面声明

- **未跑任何测试**：本任务为只读 research，禁 `./test.sh`、build、install。§6 的测试形态与回归清单来自对断言文本与实现路径的静态比对；§4 的「不变量」结论来自代码路径无共享输入，**未**用 fake timers 实证。
- **未做 6 例全量重放**：只有 wjg-w12 对本判据是可重放的 1 例；其余 5 例运行时长 < 30m 锚点、无 `[CHECKPOINT]` 行（已逐条核对 `run.json`），故不存在可观测的 `risk` 变化。
- **未读 `worker-mode.ts` 全文**：只读了与本判据相关的区段（`:140-300`、`:717-800`、`:1890-2400`、`:2440-2900`）及其调用的 helper。
- **未定 AC-017 的 `unjudgeable` 事件名/落点**：§1.4 的兜底依赖磁盘真值信号，`unjudgeable` 的机器事件形态由 T-DR3/AC-017 另定；本设计只声明「账本漏事件时用产物存在性兜底」。
- **`recentEvidence` 的有界遍历参数**（深度/条目上限/是否限 `.md`）为建议值，未实测大 `evidence/` 目录的耗时。
- **未验证部署态 bundle 与源码一致**（RQ-4 已声明同类边界）。
- **未改动仓库任何文件**；证据文件与 `report.md` 为本任务写面内的两个副本。

## 结论

选择**混合修法**：判据为主（改用与账本同源的落盘信号 + 产物存在性 + `progress.md` 完成记录），入参为辅（新增信号而非重定义 `writes`/`uniq_targets`）。`computeRisk` 保持单一导出函数，writeless 分支：产物在盘 ⇒ `low`；零落盘且过锚点 ⇒ `high`；落盘陈旧且无产物 ⇒ 按 spin/phases 停滞取 `mid`，否则 `low`；`s.landed === undefined` 时 write 角色行为逐字节不变。`[CHECKPOINT]` 行尾部追加 4 个可选字段并扩展锚定正则，旧行/新行均可解析，write 角色行不变。idle(10m)/wall(默认60m)/deadline steer 三段与 `risk` 无耦合，steer 发送不按 `risk` 门控，故不变量成立。AC-009 用「`computeRisk` 纯函数正/负/边界 + wjg-w12 形态 fake-timer 夹具 + 3 例 writeless 看门狗不变性」锁定。

## 证据

- 源码（绝对路径省略前缀 `packages/coding-agent/src/extensions/agent-team-loop/`）：
  - `worker/worker-mode.ts`：`:170-190`（steer）、`:250-257`（anchor/steer 时间）、`:260-262`（工具集）、`:283-286`（computeRisk）、`:1918`（taskDir）、`:2131-2134`（hasWriteTools/注册）、`:2341-2353`（采样）、`:2385-2400`（写事件）、`:2450/2456`（budget/anchor）、`:2508-2576`（writeCheckpoint/scheduleCheckpoint）、`:2589-2646`（idle）、`:2650-2654`（wall）。
  - `worker/worker-file-tool.ts:82`（worker_file 写事件）。
  - `shared/change-ledger.ts:115/123/135/148-160`（账本语法/解析/去重）。
  - `shared/heartbeat.ts:84-85/160-171`（CHECKPOINT_LINE_RE 与赋值块）。
  - `worker/output-writer.ts:474-489`（appendCheckpoint）、`:503-507`（formatMachineCheckpoint）。
  - `shared/deliverable-evidence.ts:105-119/153-176`（findNonEmptyReport/evidence 引用与 run-start 口径）。
  - `pm/pm-orchestrator.ts:1402-1431`（升级门禁与文案）、`pm/ui-bridge.ts:881`（聚合 `risk=high`）。
- 测试：`test/extensions/agent-team-loop.test.ts:4033-4160/4171/4207-4235/4407/4512-4650`；`test/extensions/agent-team-loop-checkpoint-wiring.test.ts:36-38/84-186/190-300/305-420`；`test/extensions/agent-team-loop-watch-aggregate.test.ts:151-185`。
- 历史工件（逐条命令见下）：`.agenticdoc/mw-worktree-junction-guard/workers/{wjg-w12-negative-space-audit,wjg-qg-evidence-closure,wjg-w15-delta-adversarial}/{task.md,run.json,trace.log}`；`.agenticdoc/mw-write-face-guard/workers/{wfg-rq2-enforcement,wfg-rq3-safety,wfg-rq-d2-runtime-guard}/{task.md,run.json,trace.log}`。
- 上游设计输入：`.agenticdoc/mw-worker-output-contract/spec.md`（§1.5 P5、§1.6 S5、§3 AC-009、§4 R5/R9）；`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq4-checkpoint-settle-20261014.md`。

关键命令与输出（只读）：

1) `[CHECKPOINT]`/账本计数（PowerShell）：
```
Select-String -Path .agenticdoc/mw-worktree-junction-guard/workers/wjg-w12-negative-space-audit/trace.log -Pattern '^\[CHECKPOINT\]'
→ [CHECKPOINT] 2026-10-13T17:33:36.128Z elapsed=1800s reads=111 writes=0 phases=- uniq_targets=0 repeat_top=16 risk=mid
Select-String ... -Pattern '^\[WRITE_FILE\]'
→ 4 行：progress.md ×3、report-negative-space-audit-20261013.md ×1
Select-String ... -Pattern 'worker_file'
→ 8 行 = 4×[FLOW] tool_call worker_file + 4×[TOOL] worker_file
Get-ChildItem -Filter 'report*' → 37,149 B / LastWriteTime 2026/10/14 1:32:12
```
2) 6 例 run.json 时长与 type（`ConvertFrom-Json` 后取 `started_at`/`ended_at`）：
```
wjg-w12 33.1m review / wjg-qg 16.3m review / wjg-w15 27.4m review
wfg-rq2 7.0m research / wfg-rq3 12.0m research / wfg-rq-d2 10.8m research
（6 例 task.md 均无 timeout: 头 ⇒ 默认 budget 60m ⇒ anchor min(30m,30m)=30m）
```
3) `trace.log` 的 `[START]`/`[END]`：`[START] 2026-10-13T17:03:36.137Z task=wjg-w12-negative-space-audit type=review phases=-`；`[END] 2026-10-13T17:36:42.230Z exit=2 elapsed=1986s tools=115 phases=-`。

## 残留与未验证

- AC-009 字面「`risk≠mid`」允许 `high`，与修法意图（不再视为发散）不一致；本设计把正例目标钉为 `low` 并显式排除 `high`，AC 文本建议在 tasks 阶段按此收紧（`risk === "low"`）。
- `landFreshMs = anchor/3`、`recentEvidence` 的深度/条目上限为设计建议值，未做实测标定。
- `progressDone` 的次选匹配（`## 完成记录`）是经验性标题；主匹配依赖 steer 要求的 `converging=yes` 行，若未来文案改动会静默失效——需与 §5.3 的「不得改自评行格式」约束一起维护。
- 建议但未强制：`pm-orchestrator.ts:1426` 的升级文案补 `land/artifact`，否则 PM 仍可能据 `writes=0` 自行推断发散。
- 未实测大目录下 `recentEvidence` 的每拍 I/O 成本。

## 上下文来源

- 任务与规格：`tasks/T-DR4-checkpoint-invariants.md`、`spec.md`（§1.5 P5 / §1.6 S5 / §3 AC-009 / §4 R5,R9）、`evidence/research/spec-rq4-checkpoint-settle-20261014.md`。
- 源码：`packages/coding-agent/src/extensions/agent-team-loop/` 下 `worker/worker-mode.ts`、`worker/worker-file-tool.ts`、`worker/output-writer.ts`、`worker/output-sections.ts`、`shared/change-ledger.ts`、`shared/heartbeat.ts`、`shared/deliverable-evidence.ts`、`pm/pm-orchestrator.ts`、`pm/ui-bridge.ts`。
- 测试：`packages/coding-agent/test/extensions/agent-team-loop.test.ts`、`agent-team-loop-checkpoint-wiring.test.ts`、`agent-team-loop-watch-aggregate.test.ts`。
- 历史语料工件：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-{w12,qg,w15}*/**`、`.agenticdoc/mw-write-face-guard/workers/wfg-rq*/**`。

[VERIFY] decision=hybrid(criteria-primary,input-derived); counters_unchanged=writes,uniq_targets; new_signals=landed,lastLandingAgeMs,artifactPresent,progressDone; source_of_landed=parseWriteFileEvents(change-ledger.ts:148) same grammar as formatWriteFileEvent(:115),dedup=distinct-normalized-path(:150-157); writeless_rule=s.landed!==undefined; failure_modes=high(landed0&past-anchor),mid(landed-stale-no-artifact&spin/phases); write_roles=byte-identical(landed undefined); checkpoint_line=optional-suffix(land,last_land,artifact,done) writeless-only; parser=CHECKPOINT_LINE_RE optional non-capturing group; invariants=idle(:2589-2646 only lastActivityAt/idleMs/lastDeltaAt/lastToolAt),wall(:2650-2654 only budgetMs/lastActivityAt),steer(:2577-2587 constant+budget),checkpoint cadence(:2568-2576 unchanged),steer-not-risk-gated; corpus6=wjg-w12 only has [CHECKPOINT](mid→low), other5 runtime<anchor no checkpoint; tests_designed_not_run; repo_files_unmodified=true; evidence_file_written=true
