# RQ-2b 证据：真正的派发输入 `workers/*/task.md` 的结构实况与生成模板

- key: `mw-dispatch-card-gate` ／ 阶段：SPEC ／ worker: `mwd-rq2b-dispatch-input-format`
- 语料：`H:\git\Multi-Workers\.agenticdoc\*\workers\*\task.md`（全仓全部 key，逐张清点见附录 A）
- 仓库基线：`git rev-parse HEAD` = `6c5189831e938712040b84e0db0b6fadb1a3d1d8`（`git rev-parse --short HEAD` = `6c5189831`）
- 环境：Windows；bash 后端 PowerShell 5.1；Python 3.14.3；Node v24.19.0（`node_modules\.bin\tsx.cmd` 直跑 TS 源模块）
- 唯一写入：本文件。其他 key 只读；无 git 写操作；未跑全量 vitest/pytest、`npm run check`、`build`、`mw build`。

## 0. 方法与环境记录

### 0.1 临时脚本写面（守卫原文，与 RQ-2 同）

任务书要求临时脚本写 `.tmp/`。实测被守卫拦截：

```
write-scope: blocked bash write to .tmp: outside the worker write surface [rule=scope];
allowed: H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2b-dispatch-input-format or H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\evidence
```

因此全部脚本与中间产物落在 worker 自身目录
`.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2b-dispatch-input-format/`：

| 文件 | 作用 |
|---|---|
| `scan_like_rq2.py` | **RQ-2 的 `scan4.py` 逐字节复制**，仅改 3 处（glob→`workers/*/task.md`、OUT 目录、key 取目录层级），保证分类器与 RQ-2 完全同口径 |
| `scan4-report.txt` | 矩阵 A/B/C、门槛 T1/T1e/T2、尺寸分布、失败清单 |
| `scan4-cards.tsv` | 343 行逐卡布尔值（RQ-2 列集） |
| `scan4-variants.txt` | 节标题频次（RQ-2 口径：H2+ 且正文非空） |
| `analyze.py` / `analyze-report.txt` | 清点、全层级标题频次、标题集众数、type 分布、写面 marker 一致性 |
| `inventory.tsv` | 附录 A 的逐张清点数据源 |
| `sets.py` | H2+ 标题集多样性 / 尺寸 |
| `probe-type-consistency.mts` / `probe-type-consistency.json` | **直接 import 生产代码**（`readTaskType` / `judgeWriteIntent` / `collectWriteIntentHits` / `isWritelessRole` / `isShellRole` / `toolsForType`）跑全语料 type 一致性回放 |
| `compare-recorded.py` / `recorded-type-compare.txt` | 卡内 `type:` vs 框架记录的 `run.json.kind` / `trace.log [START] type=` |
| `sample.py` | 抽样明细 |

### 0.2 判定口径（与 RQ-2 完全一致）

`scan_like_rq2.py` = RQ-2 `scan4.py` 的副本，三段判定沿用同一套：

- 标题侧（H2 及以下、正文非空的节）**前缀匹配**（先剥编号前缀），族归属顺序 `交付 → 背景/问题/现状 → 目标/描述/输入 → 要求/验收/…`；
- 段落侧兜底：`ctx-sem`（背景/动机/原因/由于/现状…或键值 bullet 键名）、`req-sem`（`AC-\d+`/`VC-\d+` 或键值 bullet）、`deliv-sem`（`report.md|progress.md|output.md|evidence/|回执` 或键值 bullet）；
- **矩阵 A** = 只认显式 H2+ 标题（ctx = ctx-strong 族）；**矩阵 B** = ctx 放宽到 ctx-strong ∪ ctx-intent；**矩阵 C** = 标题或段落语义。

### 0.3 语料基数差异说明

RQ-1（同日、更早）报告现存 `task.md` **342** 个（`corpus_py_md5_eq_ts_md5=342/342`）。本 RQ 同一 glob 实测 **343** 个：其中 `.agenticdoc/mw-claude-mirror-parity/workers/`（3 张，含本 key 运行期前后新建）在 RQ-1 时点尚未全部落盘。差异是语料增长，不是口径差异；本 RQ 以 343 为分母。

## 1. 语料清点

### 1.1 命令与原始输出

```powershell
(Get-ChildItem .agenticdoc -Recurse -Filter task.md |
  Where-Object { $_.FullName -match '\\workers\\[^\\]+\\task\.md$' }).Count
# -> 343
```

`scan_like_rq2.py` 原始输出首行：

```
corpus: H:\git\Multi-Workers\.agenticdoc\*\workers\*\task.md
cards: 343  keys: 34  bytes: 1085416
```

标题/序列统计（`sets.py`）：

```
files=343 total_bytes=1085416 bytes_min=37 bytes_p50=3119 bytes_max=9464 lines_min=3 lines_p50=24 lines_max=89
distinct H2+ title-sets: 57 (empty excluded: 56)
H2+ count histogram: {"0": 259, "1": 3, "2": 2, "3": 14, "4": 9, "5": 34, "6": 9, "7": 7, "8": 2, "9": 3, "10": 1}
```

H2 **恰好**层级直方图（RQ-2 口径，`scan4-report.txt`）：

```
H2-count histogram: {"0": 259, "1": 3, "2": 2, "3": 16, "4": 12, "5": 34, "6": 10, "7": 5, "8": 1, "9": 1}
cards with H2 count == 0: 259
cards with H2 count <= 2: 264
cards with H2 count >= 5: 51
  bytes of H2==0 group: min=37 p50=3021 max=8586
```

尺寸分布：

```
min = 37   p5 = 473   p25 = 2373   p50 = 3119   p75 = 3916   p95 = 5458   max = 9464
lines min/p5/p25/p50 = 3/9/18/24
cards < 400 bytes: 16   < 800: 20   < 1000: 21   < 1500: 29   < 15 lines: 48   < 20 lines: 117   < 30 lines: 221   < 40 lines: 297
```

### 1.2 计数矩阵（与 RQ-2 同口径，可直接对照）

**矩阵 A：只认显式 H2+ 标题，上下文 = ctx-strong 族**

| ctx | req | deliv | 卡数 | 占比 |
|---|---|---|---|---|
| 0 | 0 | 0 | 266 | 77.6% |
| 0 | 0 | 1 | 15 | 4.4% |
| 0 | 1 | 0 | 13 | 3.8% |
| 0 | 1 | 1 | 28 | 8.2% |
| 1 | 0 | 0 | 1 | 0.3% |
| 1 | 0 | 1 | 16 | 4.7% |
| 1 | 1 | 0 | 2 | 0.6% |
| 1 | 1 | 1 | 2 | 0.6% |

单槽 yes：ctx 21/343 = **6.1%**，req 45/343 = **13.1%**，deliv 61/343 = **17.8%**。

**矩阵 B：上下文槽放宽到 `ctx-strong ∪ ctx-intent`（目标/描述/输入）**

| ctx | req | deliv | 卡数 | 占比 |
|---|---|---|---|---|
| 0 | 0 | 0 | 265 | 77.3% |
| 0 | 0 | 1 | 13 | 3.8% |
| 0 | 1 | 0 | 11 | 3.2% |
| 0 | 1 | 1 | 27 | 7.9% |
| 1 | 0 | 0 | 2 | 0.6% |
| 1 | 0 | 1 | 18 | 5.2% |
| 1 | 1 | 0 | 4 | 1.2% |
| 1 | 1 | 1 | 3 | 0.9% |

单槽 yes：ctx 27/343 = **7.9%**，req 45/343 = 13.1%，deliv 61/343 = 17.8%。

**矩阵 C：标题 或 段落语义**

| ctx | req | deliv | 卡数 | 占比 |
|---|---|---|---|---|
| 0 | 0 | 0 | 17 | 5.0% |
| 0 | 0 | 1 | 49 | 14.3% |
| 0 | 1 | 0 | 25 | 7.3% |
| 0 | 1 | 1 | 85 | 24.8% |
| 1 | 0 | 0 | 1 | 0.3% |
| 1 | 0 | 1 | 22 | 6.4% |
| 1 | 1 | 0 | 4 | 1.2% |
| 1 | 1 | 1 | 140 | 40.8% |

单槽 yes：ctx 167/343 = **48.7%**，req 254/343 = **74.1%**，deliv 296/343 = **86.3%**。

**门槛对照（RQ-2 的定义逐字复用）**

| 门槛 | 本 RQ：`workers/*/task.md` | RQ-2：`tasks/*.md` |
|---|---|---|
| **T1 严**（背景族 + req族 + deliv族 三个显式 H2，节正文非空） | pass **2** / fail **341** = **99.4% 不合规** | pass 44 / fail 301 = 87.2% |
| **T1e 中**（ctx-strong∪目标∪描述∪输入 + req + deliv 显式 H2） | pass **3** / fail **340** = **99.1%** | pass 108 / fail 237 = 68.7% |
| **T2 宽**（每一类"标题或有语义"） | pass **140** / fail **203** = **59.2%** | pass 273 / fail 72 = 20.9% |
| T2 宽（只算 ≥800 字节卡） | pass **160** / fail **183** = 53.4% | pass … / fail 65 = 18.8% |

**对照结论（关键）**：真正的派发输入比 RQ-2 测的 `tasks/*.md` **更不合规**——严格口径下 343 张里只有 **2 张**（0.6%）三段齐备，最宽口径下仍有 **203 张（59.2%）**不齐。**"卡片必然含三段"在派发输入上是纯假设。**

T1 通过的那 2 张：

```
.agenticdoc/…（见 scan4-report.txt "== T1 fail list ==" 的补集；bytes min=3813 p50=4065）
T1-pass cards: bytes min=3813 p50=4065  |  T1-fail: bytes min=37 p50=3111
```

### 1.3 分 key 计数（34 key，合计 343）

```
_scratch                          6
agent-team-loop                   1
autopilot-monitor                 2
goal-autopilot                   12
mw-autopilot-slot-capacity       47
mw-autopilot-stall-feedback       2
mw-autopilot-verify-cli          26
mw-claude-mirror-parity           3
mw-crosskey-risk-escalation       2
mw-dispatch-card-gate             4
mw-dispatch-flow-fixes            4
mw-dispatch-reliability           8
mw-dispatch-settle-gates         18
mw-done-closure-repair            7
mw-dual-workspace                 1
mw-gate-verdict-hardening        28
mw-guard-form-hardening          36
mw-implementation-gate            3
mw-l3-fail-marker-forms           7
mw-partition-parent-extended      2
mw-rag-config-guide               3
mw-rag-integration               21
mw-rag-integration-fix            5
mw-rag-window-parity              6
mw-target-partition              16
mw-vision-role                   30
mw-widget-terminal-lifecycle      5
mw-worker-progress-persist        8
mw-worker-timeout-convergence     1
mw-worker-tree-kill               3
mw-worker-visibility-gate         5
mw-workspace-incident-probe       3
mw-worktree-junction-guard        2
xkey-repair-mechanism            16
```

逐张 `key | task_key | 字节 | 行数 | 有上下文段 | 有要求段 | 有交付物段` 见**附录 A**（矩阵 A 口径）。

## 2. 结构齐一性

### 2.1 节标题频次（全层级，`analyze.py`）

`distinct heading titles: 195`。出现率 ≥3 张卡的标题（完整表见 `analyze-report.txt`）：

| 卡数 | 次数 | 层级(次) | 标题 |
|---|---|---|---|
| 33 | 33 | 1:5,2:28 | 交付 |
| 22 | 22 | 2:22 | 判定纪律 |
| 22 | 22 | 2:22 | 禁止 |
| 19 | 19 | 2:19 | 唯一权威 |
| 19 | 19 | 2:19 | 环境增量 |
| 15 | 15 | 1:5,2:10 | 约束 |
| 14 | 14 | 2:14 | 纪律 |
| 11 | 11 | 2:11 | 背景 |
| 8 | 8 | 2:8 | 交付物（唯一写入 = worker_file file="report.md" …） |
| 8 | 8 | 1:1,2:7 | 硬约束 |
| 7 | 7 | 2:7 | 完成动作 |
| 7 | 7 | 1:5,2:2 | 必须回答 |
| 7 | 7 | 2:7 | 权威任务书（先完整阅读） |
| 5 | 5 | 1:5 | 目标 |
| 5 | 5 | 2:5 | 硬规则 |
| 5 | 5 | 2:5 | 验收（真实执行，output 贴原始输出） |
| 5 | 5 | 2:5 | 验证（必须全绿才算完成） |

即：**出现率最高的三个标题是「交付」9.6%、「判定纪律」6.4%、「禁止」6.4%**；RQ-2 三段槽位里没有任何一个槽位标题进入前 3。头部只有一个"交付"（且它落在 deliv 族）出现率近 10%，"背景"仅 3.2%。

### 2.2 节标题集合的众数与出现率

按"每张卡的 H2+ 标题集合"统计（`sets.py` / `analyze.py`）：

- **众数 = 空集 `[]`：259/343 = 75.5%**（`distinct H2+ title-sets: 57`，其中 56 个非空集，全部是"每张卡自成一套"的长尾）。
- 第二众数 = `["交付","判定纪律","唯一权威","环境增量","禁止"]`：19 张 = 5.5%（同一批 PM 手写卡的复制粘贴家族）。
- 第三 = 4 张（1.2%），第四/五 = 3 张（0.9%）…

```
 259 cards ( 75.5%)  set=[]
  19 cards (  5.5%)  set=["交付","判定纪律","唯一权威","环境增量","禁止"]
   4 cards (  1.2%)  set=["交付物（唯一写入 = worker_file file=\"report.md\"，…）","纪律","背景"]
   3 cards (  0.9%)  set=["Step 1 — …","Step 2 — …","Step 3 — …","Step 4 — …","Step 5 — …","工作流定义（必须先完整阅读）","输出与纪律"]
   3 cards (  0.9%)  set=["产出（只允许这 2 个新文件）","关键语义","完成动作","权威任务书（先完整阅读）","约束","验证（必须全绿才算完成）"]
```

### 2.3 结论（结构齐一性）

**不齐一，而且不是"格式略有差异"，是"多数文件根本没有节结构"。**

- 259/343（75.5%）的派发任务书**一个 H2 都没有**（纯自由文本：`type:` 一行 + 空行 + 一大段散文）。这是 PM 把 `dispatch_worker` 的 `description` 原样落盘的直接结果（见 §3）。
- 剩余 84 张里，**没有一对完全相同的标题集能覆盖到 20% 以上**；除了 19 张同一批复制粘贴的卡，其余是 56 个互不相同的集合（长尾）。
- 三段语义在**最宽口径**下也只有 40.8% 的卡齐备 → 任何"标题齐一性"门槛在当前语料上都是大面积拒绝。
- 因此：**派发输入不存在可依赖的既有结构契约**；想保证三段，只能从**生成端**（§3/§4）而不是校验端拿。

## 3. 生成路径

### 3.1 三个生产写入点（完整坐标）

| # | 生产者 | 写点（`文件:行号`） | 覆盖哪些卡 |
|---|---|---|---|
| 1 | PM 交互 `dispatch_worker` 工具 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1780` `writeDispatchTaskMd` → **`1806`** `fs.writeFileSync(taskMdPath, content, "utf8")` | 全语料主体 |
| 2 | PM 交互 `/worker` 命令 | 同一 `writeDispatchTaskMd`（调用在 `ui-bridge.ts:2502`；命令注册 `registerWorkerCommands` 在 `2355`） | `manual-<epoch>` 系列（本语料 4 张） |
| 3 | autopilot conductor（Python） | `packages/multi-workers/autopilot/dispatch.py:290` `render_task_md` → 调用 `611` → 落盘 **`625`** `task_md.write_text(content, encoding="utf-8", newline="\n")` | 本语料 **0 张**（见 §3.5） |

**服务层（`mw` 队列消费）不生成 `task.md`**：`packages/multi-workers/launcher.py` 全文无 `write_text`/`render_task_md`（实测 grep 0 命中）；它只在 spawn 前 `_read_task_md_fields`（`launcher.py:143`）读 `type:`/`model:` 与 `_require_task_file`（`launcher.py:495`）查存在性。

**写后二次注入（仍是代码，但发生在入队时）**：
`pm/task-dispatcher.ts:241` `injectWorkspaceProfile(taskPath)`（由 `dispatchTask` 在 `288-292` 调用）会读回 task.md，按需追加 workspace profile 块 / RAG 块，并在 `285` `fs.writeFileSync(taskPath, out, "utf8")` 重写。本语料 0 张带 `mw-profile` / `mw-rag: v1` 标记（RAG 未启用、非 partition 模式）。

**第 4 条（非代码）路径：手写/手改**。实测存在：
- `.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md`：首行 `# Smoke: AC-016 re-run after dist rebuild`，**无 `type:`**（首非空行不是 key 形状）；
- `.agenticdoc/mw-worker-timeout-convergence/workers/smoke-watchdog/task.md`、`.agenticdoc/mw-worker-tree-kill/workers/smoke-tree-kill-1/task.md`：带 `timeout: 2` 头（两个生产者都不会写 `timeout:` 到 TS 侧头里）；
- 4 张卡有**重复 `type:` 头**，其中 1 张冲突（见 §5.2）。

### 3.2 TS 模板原文（逐行抄录）

`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`

**(a) frontmatter 组装** — `planDispatchFrontmatter`（`1190`；`headLines` 在 `1228`）：

```ts
	const headLines = [`type: ${input.taskType}`];
	if (input.phase !== undefined && input.phase.length > 0) headLines.push(`phase: ${input.phase}`);
	if (imagesField !== undefined) headLines.push(`images: ${imagesField}`);
	const typeLines = `${headLines.join("\n")}\n`;
	…
	if (autoRouteSource) {
		const routeReason = reason
			? `${reason}; auto-route: ${autoRouteSource} -> vision`
			: `auto-route: ${autoRouteSource} -> vision`;
		const routeLines = [...headLines, `model: ${effective}`, `model-reason: ${routeReason}`];
		return { ok: true, frontmatter: `${routeLines.join("\n")}\n`, … };
	}
	if (!requested) {
		return { ok: true, frontmatter: typeLines, … };
	}
	…
	const lines = [...headLines];
	if (requested) lines.push(`model: ${requested}`);
	if (reason) lines.push(`model-reason: ${reason}`);
	return { ok: true, frontmatter: `${lines.join("\n")}\n`, … };
```

**(b) 头行合并** — `mergeWriteScope`（`1765`）/ `mergeAllowForeignWrite`（`1756`）：

```ts
function mergeAllowForeignWrite(frontmatter: string, allowed: boolean | undefined): string {
	if (!allowed || /^allow_foreign_write:/m.test(frontmatter)) return frontmatter;
	return `${frontmatter.replace(/\r?\n$/, "")}\nallow_foreign_write: true\n`;
}

function mergeWriteScope(frontmatter: string, writeScope: string | undefined): string {
	const line = (writeScope ?? "").trim();
	if (!line) return frontmatter;
	return `${frontmatter.replace(/\r?\n$/, "")}\n${line}\n`;
}
```

`renderDefaultWriteScope`（`1717`）：

```ts
export function renderDefaultWriteScope(ownerKey: string, taskKey: string): string {
	return `write_scope: .agenticdoc/${ownerKey}/workers/${taskKey}, .agenticdoc/${ownerKey}/evidence`;
}
```

**(c) 唯一写点与正文装配** — `writeDispatchTaskMd`（`1780`；装配 `1804`，落盘 `1806`）：

```ts
	const frontmatter = mergeAllowForeignWrite(
		mergeWriteScope(input.frontmatter, input.writeScope),
		input.allowForeignWrite,
	);
	const taskDir = workerTaskDir(deps.agenticdocRoot, deps.ownerKey, input.taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	const taskMdPath = path.join(taskDir, "task.md");
	const plain = `${frontmatter}\n${input.body}\n`;
	const content = input.injectWriteSurface ? applyWriteSurfaceContract(plain, input.type, input.writeScope) : plain;
	fs.writeFileSync(taskMdPath, content, "utf8");
```

即 **`task.md` 字节 = `frontmatter + "\n" + body + "\n"`（可选：在 frontmatter 后插入 write-surface 段）**，而 `body` 就是工具参数 `description` 原文（`dispatch_worker` 在 `ui-bridge.ts:2026-2035` 传 `body: description`；`/worker` 在 `2502-2511` 传 `body: description`）。**除头行与 write-surface 段外，模板不注入任何节标题。**

**(d) 唯一"注入段"模板** — `renderWriteSurfaceContract`（`1722`）+ `applyWriteSurfaceContract`（`1745`）：

```ts
export function renderWriteSurfaceContract(type: string, writeScope: string | undefined): string {
	const scope = (writeScope ?? "").trim().replace(/^write_scope:\s*/, "");
	const allowed = scope
		? `本任务目录下的 worker_file（progress.md | report.md | report-<slug>.md）；write_scope: ${scope}`
		: "本任务目录下的 worker_file（progress.md | report.md | report-<slug>.md）";
	const denied =
		"本任务目录之外的任何路径（pm-state.md、workers/_workers*、_index.parallel、其他 key、packages/**、.git/**）";
	const consequence = isShellRole(type)
		? "运行期 bash 写面守卫 block + [TOOL_ERR] + trace 审计行"
		: "运行期写面守卫拒绝；回复文本仍会被框架写入 output.md";
	return [
		WRITE_SURFACE_MARKER,
		`- 允许写：${allowed}`,
		`- 不得写：${denied}`,
		`- 越界后果：${consequence}`,
		WRITE_SURFACE_MARKER_END,
	].join("\n");
}

export function applyWriteSurfaceContract(taskMdText: string, type: string, writeScope: string | undefined): string {
	const section = renderWriteSurfaceContract(type, writeScope);
	const cleaned = taskMdText.replace(WRITE_SURFACE_SECTION_RE, "");
	const blank = cleaned.search(/\n\s*\n/);
	if (blank === -1) return `${section}\n\n${cleaned}`;
	const head = cleaned.slice(0, blank).replace(/\n+$/, "");
	const rest = cleaned.slice(blank).replace(/^\n+/, "");
	return `${head}\n\n${section}\n\n${rest}`;
}
```

> **这段就是"生成端注入三段"的现成先例**：`applyWriteSurfaceContract` 已经有"删除旧 marker 区 → 重新插入到 frontmatter 之后"的幂等插入机制（`WRITE_SURFACE_SECTION_RE` 在 `1467`，marker 常量在 `1340/1341`），可直接复用来注入上下文/要求/交付物三段。

### 3.3 Python conductor 模板原文（逐行抄录）

`packages/multi-workers/autopilot/dispatch.py:290` `render_task_md`，模板体 `347-378`：

```python
    lines = [
        "---",
        f"type: {task_type}",
    ]
    if phase:
        lines.append(f"phase: {phase}")
    if images:   # None / "" -> zero bytes (AC-009); declared -> images: yes|no
        lines.append(f"images: {images}")
    if model:
        lines.append(f"model: {model}")
    lines += [
        "origin: conductor",
        f"loop: {loop}",
        f"attempt: {attempt}",
    ]
    if worker_timeout_min is not None:
        lines.append(f"timeout: {int(worker_timeout_min)}")
    if read_scope:
        lines.append("read_scope:")
        lines.extend(f"  - {item}" for item in read_scope)
    if read_file_cap is not None:
        lines.append(f"l2_read_file_cap: {int(read_file_cap)}")
    if read_byte_cap is not None:
        lines.append(f"l2_read_byte_cap: {int(read_byte_cap)}")
    if deny_globs:
        lines.append("deny_globs:")
        lines.extend(f"  - '{item}'" for item in deny_globs)
    lines += ["---", "", prompt.strip(), ""]
    content = "\n".join(lines) + "\n"
    if profile_block is not None:
        content = content.rstrip() + "\n\n" + profile_block + "\n"
    return _inject_rag_block(content, rag_config, task_meta, task_type)
```

正文同样是自由文本：`prompt.strip()`（`374`）。conductor 侧还有 `_inject_rag_block`（`185`）追加 `<!-- mw-rag: v1 -->` 块。

### 3.4 模板当前注入了哪些字段（全语料实测频次）

对 343 张卡的头区（前 40 行）逐字段计数：

| 字段 | 有该行的卡数 | 生产者 |
|---|---|---|
| `type:` | **342** / 343 | TS `planDispatchFrontmatter`（或 conductor） |
| `phase:` | 47 | TS（`dispatchPhase` 读 `pm-state.md`） |
| `images:` | 25 | TS（`images` 参数 / 自动探测） |
| `model:` | 17 | TS（显式 override） |
| `model-reason:` | 4 | TS（override 必须给理由） |
| `write_scope:` | **8** | TS（仅 `writeless && shell` = `research`） |
| `allow_foreign_write:` | **0** | TS 逃生舱，语料未被使用 |
| `timeout:` | 2（均手写） | conductor 才会写；本语料两条是手改 |
| `read_scope:` / `deny_globs:` / `origin:` / `loop:` / `attempt:` | 0 / 0 / 1 / 0 / 0 | conductor 字段，本语料基本没有 |
| write-surface 段 marker `<!-- mw-write-surface: v1 -->` | **9**（8 张真注入 + 1 张正文引用该字符串） | TS `applyWriteSurfaceContract` |

**没有任何字段承载"上下文/要求/交付物"**——三段在生产者侧不存在对应的 dispatch 参数，也没有模板占位。

### 3.5 语料归属推断（谁写的）

| 信号 | 实测 | 推断 |
|---|---|---|
| 首行 `---` 围栏（conductor 模板 `348` 必然产出） | **0 / 343** | **没有一张卡由 Python conductor 模板生成**；342 张首行是 `type:`，符合 TS 写点 |
| `origin: conductor`（conductor `358` 必然写） | 头区仅 1 张（且是正文行，非真头） | 同上 |
| `manual-<epoch>` task_key（`/worker` 的 `manual-${Date.now()}`，`ui-bridge.ts:2436`） | 4 张 | 这 4 张确定来自 `/worker` |
| 首非空行不是 `type:` | 1 张（`smoke-ac016b`） | 手写 |
| 重复 `type:` 头 | 4 张（其中 1 张值冲突） | 手改（模板只写一次） |
| 头区 `timeout: 2` | 2 张 | 手改（TS 不写该头） |

**结论**：本语料 343 张，全部由 **TS 侧唯一写点 `writeDispatchTaskMd`** 生成或在其产物上手改；**conductor 路径在当前语料上 0 样本**（但代码存在，改动必须覆盖）。因此"派发输入格式"的可用控制点就是 `ui-bridge.ts:1780`（+ `task-dispatcher.ts:241`）与 `autopilot/dispatch.py:290` 两处。

## 4. 可生成性结论（关键）

### 4.1 能否在生成端保证每个 `task.md` 都含三段

**能——对工具产出的卡；不能——对手写的卡。前提与代价如下。**

**能，而且是最省的一条路**，理由：

1. **正文完全由机器拼装**：`writeDispatchTaskMd`（`ui-bridge.ts:1780-1807`）唯一的正文来源是调用方传入的 `body`；没有任何"工具之外"的部分。把 `body` 从 `description`（1 个自由文本）换成 3 个参数（`context`/`requirements`/`deliverables`）后，三段就是**由构造保证**的，不需要事后校验、不存在误报。
2. **已有现成的幂等段注入机制**：`applyWriteSurfaceContract`（`1745`）+ `WRITE_SURFACE_SECTION_RE`（`1467`）已经实现"删旧段 → 插到 frontmatter 之后"，可直接泛化为 `renderBodySections(sections)` 注入固定三段。
3. **两个交互入口共用同一写点**：`dispatch_worker`（`2026`）与 `/worker`（`2502`）都调 `writeDispatchTaskMd`，改一处即两入口一致（满足 P-04）；`task-dispatcher.ts:241` 的二次注入点也在同一条链上。
4. **conductor 侧同样可改**：`prompt` 换成 3 段后 `render_task_md`（`374`）拼 `prompt` 的位置改为拼三段。

**不能的边界（必须显式承认）**：

- **手写/手改旁路无法在生成端拦**：`smoke-ac016b`（无 `type:`）、`review-mw-worker-tree-kill`（重复冲突 `type:`）、2 张手写 `timeout:` 头证明 PM 会用 `write`/bash 直接落卡。生成端只能保证"经工具产出的卡"，对旁路只能靠**事后门禁**（即本 key 的 G2）或核对-回填。
- **自由文本参数改成必填三段会改变 PM 的使用面**：现有 219 张 `coding` 卡的 `description` 是"目标 + 步骤 + 交付"混写的一大段；要求 3 个必填参数会强制 PM 拆段，属于行为变更（不是纯内部重构）。
- **若坚持只保留 `description` 单参数**，模板最多只能注入**空标题骨架**（`## 上下文` / `## 要求` / `## 交付物` + 空正文），这**不满足"段非空"**，等于没有保证；所以必须要么加参数，要么在 `description` 内部约定分隔符（如 `--- 要求 ---`）并做写前校验——后者仍是"校验"而非"构造保证"。

### 4.2 实现点坐标与最小改动估计

| 步骤 | 坐标 | 改动 | 量级 |
|---|---|---|---|
| 1. 新增段渲染函数（3 个固定 H2 + 空段校验） | `ui-bridge.ts` 紧邻 `renderWriteSurfaceContract:1722` | 新函数 `renderTaskBodySections()`；复用 `applyWriteSurfaceContract` 的插入定位 | ~30–50 行 |
| 2. 写点装配改为插段 | `writeDispatchTaskMd:1780`，装配 `1804` | `plain` 由 `${frontmatter}\n${body}\n` 改为 `${frontmatter}\n${sections}\n`（或复用 `applyWriteSurfaceContract`） | ~10 行 |
| 3. `dispatch_worker` 参数面 | `ui-bridge.ts:1830-1893`（`parameters`）+ `1881`（`execute` 解构）+ `2026-2035`（调用） | 新增 `context`/`requirements`/`deliverables`（或 1 个 `sections` 对象），全部 `Type.String()` 必填 | ~30 行 |
| 4. `/worker` 参数解析 | `ui-bridge.ts:2355` 起的 `handler`（`2368`）+ `2502-2511` | 同上（可选：保留 `description` 作为三段合并的兼容入口） | ~30 行 |
| 5. conductor 模板 | `autopilot/dispatch.py:290-378` | `prompt` 拆 3 段，`374` 处拼段 | ~25 行 |
| 6. 断言/金样本更新 | TS：`test/extensions/agent-team-loop.test.ts`、`test/suite/mwds-t01-worker-guard.test.ts`、`mwds-t02-write-intent.test.ts`、`mwds-t03-bash-write-scope.test.ts`、`mwds-t12-regression.test.ts`（5 文件，含 `writeDispatchTaskMd(` 直接调用与字节断言）；Python：`test_autopilot_attribution.py`、`test_autopilot_conductor_exec.py`、`test_autopilot_dispatch.py`、`test_autopilot_readcap_injection.py`、`test_mwds_t10_dispatch_run_state.py`、`test_rag_launcher.py`、`test_rag_phase.py`（7 文件，`render_task_md` 字节金样本） | 更新期望字节/入参 | 12 文件，多为逐字面量替换 |

**总量级：生产代码 ~100–145 行（跨 TS/Python 两处），金样本测试 12 个文件。** 无 frontmatter/消费者解析改动（type/tools/write_scope 一律不动），因此**不需要** cutover 迁移数据；只需 rebuild+restart 两侧进程（P-01 仍适用）。

### 4.3 替代方案（若不加参数）

- **写前校验而非构造保证**：在 `writeDispatchTaskMd` 之前对 `description` 跑"三段标题齐备 + 非空"判定，不合规即拒绝（并在拒绝文本里给出三段骨架模板）。代价：这是**门禁**不是保证，且当前语料 99.4% 不合规 ⇒ 会大面积拒绝（除非只对"新派发"生效 + 历史卡豁免）。
- **纯注入骨架 + 内容归属不变**：模板固定写 `## 上下文` / `## 要求` / `## 交付物` 三个标题，把 `description` 整体塞进"要求"，另两段留空——不满足"段非空"，只能骗过标题匹配，不应采用。
- **接受"卡 = 自由文本"，把门禁收到别处**：只强制 `type:` + 写面（`write_scope:`/C2 marker），三段作为 PM 自律。这等于本 key 的 G2 失效，与 T-20 事故的教训（"纸面要求"）冲突，不推荐。

## 5. 一致性抽样核对（`type:` vs 记录的角色/工具）

### 5.1 全量机器核对（生产代码回放，`probe-type-consistency.mts`）

```
[VERIFY] corpus=343
[VERIFY] by_type={"":1,"coding":219,"research":94,"review":28,"vision":1}
[VERIFY] type_source_missing=1 bom_stripped=7
[VERIFY] writeless_noshell(review-like)=28 hit_books=10 violation_books=1 judge_refuse=1
  [VERIFY] violation: .agenticdoc/mw-gate-verdict-hardening/workers/mwg-qg-review-20261010/task.md type=review -> .agenticdoc/mw-gate-verdict-hardening/evidence/quality-gate-report-review-20261010.md
[VERIFY] writeless_shell(research-like)=94 hit_books=0 violation_books=0 (not refused by design; contract section is the channel)
[VERIFY] write_roles=221 judge_untouched=true
[VERIFY] writeless_without_marker=114 write_role_with_marker=1 research_without_write_scope_header=86
  [VERIFY] write_role_marker_anomaly: .agenticdoc/mw-dispatch-settle-gates/workers/mds-t02-write-intent/task.md type=coding
```

- `type:` 分布：`coding` 219（63.8%）、`research` 94（27.4%）、`review` 28（8.2%）、`vision` 1、**缺失 1**。全部 342 个有 `type:` 的值都在 `TOOL_ALLOWLISTS` 内（无 `unknown_type`）；`fallback`/conductor 类型（`verifier`/`repair`/`phase-writer`/`roadmap-writer`）**0 例**。
- **role/tools 派生一致**：`roleForTaskType` / `TASK_TYPE_TO_ROLE` 对 342 张都能给出角色；`isWritelessRole` 得 122 张（review 28 + research 94），`isShellRole` 得 94+219+1+1 = 315 张。与 RQ-1 §3"两侧映射逐键相等、白名单运行时单一实现"一致。
- **写面判据（AC-005a）**：review 类 28 张里只有 **1 张**（`mwg-qg-review-20261010`）被生产判据判为违规——正是 RQ-2 测试锁定的**已知真阳性**（它要求把报告写到 `<key>/evidence/`），`false_positive=0`。research 类 94 张 hit=0（设计上不拒，走契约段）。
- **C2 契约段覆盖不一致**：`injectWriteSurface = isWritelessRole` ⇒ 期望 122 张 writeless 卡都有 marker，实测只有 **8 张（全为 `research`）**；**114 张缺**。`write_scope:` 头同理只 8 张（`research`），`research` 类还有 86 张没有该头。说明该注入是**近期才上线**（`mw-dispatch-settle-gates` T-02/T-03），历史卡未回填。
- `write_role_with_marker=1` 是**假阳性**：`mds-t02-write-intent/task.md`（`type: coding`）在散文里引用 `marker `<!-- mw-write-surface: v1 -->`` 字符串，不是注入。

### 5.2 抽样 12 张明细

| # | `task.md`（相对仓库根） | `type:` | source | writeless/shell | tools（运行时白名单） | C2 marker | `write_scope:` | judgeWriteIntent | 与记录一致？ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `packages/...` → `.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2b-dispatch-input-format/task.md` | research | header | true / true | read,find,grep,ls,bash | ✅ | ✅ | ok | ✅ |
| 2 | `.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2-card-corpus/task.md` | research | header | true / true | read,find,grep,ls,bash | ✅ | ✅ | ok | ✅ |
| 3 | `.agenticdoc/mw-claude-mirror-parity/workers/mwp-rq3c-distribution-path/task.md` | research | header | true / true | read,find,grep,ls,bash | ✅ | ✅ | ok | ✅ |
| 4 | `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-rq1-concurrency-anchors/task.md` | research | header | true / true | read,find,grep,ls,bash | ❌ | ❌ | ok | ✅（旧卡，未回填） |
| 5 | `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-qg-review-20261010/task.md` | review | header | true / false | read,find,grep,ls | ❌ | ❌ | **refuse**（写 `…/evidence/quality-gate-report-review-20261010.md`） | ⚠️ 角色与卡的写指令**冲突**（已知真阳性） |
| 6 | `.agenticdoc/_scratch/workers/manual-1789974535494/task.md` | review | header | true / false | read,find,grep,ls | ❌ | ❌ | ok | ✅ |
| 7 | `.agenticdoc/mw-dispatch-settle-gates/workers/mds-t02-write-intent/task.md` | coding | header | false / true | read,write,edit,bash,find,grep,ls | ✅（正文引用，非注入） | ❌ | n/a（写角色不判） | ✅ |
| 8 | `.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md` | **coding**（头区首值） | header | false / true | read,write,edit,bash,find,grep,ls | ❌ | ❌ | n/a | ❌ **不一致**：正文第二个 `type: review`，worker 实跑记录 `type=review` |
| 9 | `.agenticdoc/mw-worker-timeout-convergence/workers/smoke-watchdog/task.md` | coding | header | false / true | read,write,edit,bash,find,grep,ls | ❌ | ❌ | n/a | ✅（手写，带手写 `timeout: 2`） |
| 10 | `.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md` | **（缺失）** | **missing** | false / true | read,write,edit,bash,find,grep,ls（fallback） | ❌ | ❌ | n/a | ❌ **不一致**：trace 记录 `type=default` ⇒ 回退 full 工具集（RQ-1 A10） |
| 11 | `.agenticdoc/goal-autopilot/workers/t03-roadmap/task.md` | coding | header | false / true | read,write,edit,bash,find,grep,ls | ❌ | ❌ | n/a | ✅ |
| 12 | `.agenticdoc/mw-vision-role/workers/mvr-r1-live-vision-red/task.md` | vision | header | false / true | read,write,edit,bash,find,grep,ls | ❌ | ❌ | n/a | ✅ |

### 5.3 `type:` 与框架**记录**值的对拍（`compare-recorded.py`）

对每个 task dir 读 `run.json.kind` 与 `trace.log` 的 `[START] … type=`，与卡内 `type:` 首值比较：

```
total=343  has_run_json=44  has_trace_start=332  match=330  mismatch=2  no_record=11
MISMATCH ('.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md', '', '', 'default')
MISMATCH ('.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md', 'coding', '', 'review')
```

- **330/332 有 trace 的卡一致**（99.4%）⇒ 正常情况下 `type:` 是可靠的"卡 → 角色/工具"唯一入口（与 RQ-1 §3 结论一致）。
- 2 例不一致都不是工具生成的卡：
  - `smoke-ac016b`：无 `type:`，worker 记录 `type=default` → `toolsForType` 回退 full（含 write/edit/bash）。这是 RQ-1 A10 的现场实例。
  - `review-mw-worker-tree-kill`：文件头区首 `type: coding`、正文第二行 `type: review`；H1 是 `# Review: …`。**worker 实跑记录的是 `review`**（2026-09-19，旧 `parseTaskMd` 的全文 last-wins 扫描），而现行单一解析源 `readTaskType`（`shared/task-frontmatter.ts:141`）取**头区首值**⇒ 今天同一文件会解析为 `coding` 并拿到 write/edit/bash。task.md mtime `09/19/2026 22:47:34`，trace `[START] 2026-09-19T14:47:37.443Z`（= 本地 22:47:37），即**卡在派发前 3 秒就是这个双 header 形态**。这正是 `task-frontmatter.ts` 头部注释记载的那次 A8 事故（"the old full-text last-wins scan … let a body line (`type: coding`) hand a `review` task the write/edit/bash surface"）的语料残留，方向相反。
- 11 张 `no_record`：卡目录无 `run.json` 也无 `trace.log`（未跑或产物被清理）。

### 5.4 一致性结论

- **角色/工具侧**：`type:` → 角色/白名单的映射本身完全自洽（342/342 在册，0 unknown），写面判据 0 新假阳性——**RQ-1 §3 的结论在 343 张全量上复现成立**。
- **记录侧**：330/332 一致；2 例分歧都出现在**非工具生成的卡**上（1 例无 `type:` fail-open，1 例重复冲突 header）。⇒ 一致性风险不在"映射"，而在"卡是不是由代码写的"。
- **契约段侧**：C2 注入只覆盖 8/122 期望卡（6.6%），`research` 的 `write_scope:` 头覆盖 8/94（8.5%）——**"生成端保证"目前只是对新卡生效，历史卡靠回填**。这直接支撑 §4 的"生成端 + 历史豁免"路径。

## 6. 未验证怀疑清单

1. **手写/手改卡的比例未精确界定**。仅证明至少 6 张（`smoke-ac016b` 无 type、`smoke-watchdog`/`smoke-tree-kill-1` 手写 timeout、`review-mw-worker-tree-kill` 等 4 张重复 header）。TS 写点与手写产物的**唯一区分特征**是"首行是否 `type:`"，而手写者也可模仿。没有来源戳（如 `origin:`）就分不清。
2. **`timeout: 2`（分钟）是否真被消费、是否会造成 worker 被 2 分钟杀**未验证（属 mw-worker-timeout-convergence 范围；本 RQ 只证明该头不是模板产物）。
3. **`write_role_with_marker=1` 的归类**依赖"marker 字符串是否出现在正文"这一粗暴判据；我没有区分"注入段"与"散文引用"的通用方法（`applyWriteSurfaceContract` 的 marker 对之外没有别的结构化证据）。8 张真注入的判定依据是"marker 对 + `write_scope:` 头同时存在且 type=research"。
4. **T2（宽口径）59.2% 不合规里混有"其实写了但没被识别"的卡**：段落语义层的兜底规则召回/精确率未标定（与 RQ-2 §6 同一局限）。只读文件、无 ground truth，无法给出真实合规率的上界/下界。
5. **`409` 记忆口径的 `keys=34` 包含 `_scratch`**；`_scratch` 的 6 张卡在语义上不是 key 级派发，是否应计入分母由 SPEC 决定。
6. **生成端改为三段必填参数对 PM 行为的影响未评估**（§4.1 的"行为变更"）：没有统计 PM 实际调用 `dispatch_worker` 时 `description` 的长度/结构分布与拆分成本。
7. **conductor 路径 0 样本**：`render_task_md` 的改动与验证不在本语料可覆盖范围内（没有 `origin: conductor` 的卡可回归）；若改 conductor 模板，需要另外造 e2e 样本（`test_autopilot_e2e.py` 有 stub worker 可用，未跑）。
8. **`task-dispatcher.ts:241` 二次注入是否会覆盖/打乱新注入的三段**未实测；只读了 `injectWorkspaceProfile` 的 marker→EOF 替换语义（理论上它在文件尾部追加，不会动 frontmatter 后的段）。
9. **RQ-1 的 342 vs 本 RQ 的 343**：差异归因于 `mw-claude-mirror-parity` 的新建卡，但没有逐文件 diff 证明，只是同一 glob 的计数差 + 该 key 目录为未跟踪新目录（`git status` 显示 `?? .agenticdoc/mw-claude-mirror-parity/`）。
10. **附录 A 的"有上下文/要求/交付物段"是矩阵 A 口径**（只认显式 H2+ 标题族）；它与"人读是否觉得写了这三件事"不等价（宽口径见矩阵 C）。

## 附录 A：逐张清点表（343，`key | task_key | 字节 | 行数 | 有上下文段 | 有要求段 | 有交付物段`）

口径：与矩阵 A 相同（显式 H2+ 标题族 + 节正文非空）；`Y`/`-` 表示有/无。数据源 `.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2b-dispatch-input-format/inventory.tsv`（另有 `ctx_ext_B`/`ctx_sem`/`req_sem`/`deliv_sem`/`nh2`/`origin`/`fence_fm`/`type` 列）。

| key | task_key | bytes | lines | ctx | req | deliv |
|---|---|---|---|---|---|---|
| _scratch | manual-1789974535494 | 93 | 3 | - | - | - |
| _scratch | manual-1789974660966 | 37 | 3 | - | - | - |
| _scratch | manual-1789974753377 | 102 | 5 | - | - | - |
| _scratch | mw-dr-autodispatch | 83 | 4 | - | - | - |
| _scratch | w1-pi-extension-interception | 2019 | 19 | - | - | - |
| _scratch | w2-p002-guard-precedent | 1838 | 19 | - | - | - |
| agent-team-loop | ga-spec-review-1 | 2411 | 16 | - | - | - |
| autopilot-monitor | t01-monitor-module | 2073 | 14 | - | - | - |
| autopilot-monitor | t02-verification | 1721 | 15 | - | - | - |
| goal-autopilot | ga-spec-design-review-2 | 5611 | 44 | - | - | - |
| goal-autopilot | t03-roadmap | 2803 | 34 | - | Y | - |
| goal-autopilot | t04-timeline | 3001 | 37 | - | Y | - |
| goal-autopilot | t05-gates | 3019 | 36 | - | Y | - |
| goal-autopilot | t08-audit | 3289 | 38 | - | Y | - |
| goal-autopilot | t13-read-scope | 4197 | 38 | - | Y | - |
| goal-autopilot | t14-protocol | 4071 | 37 | - | Y | - |
| goal-autopilot | t15-console | 4443 | 47 | - | Y | - |
| goal-autopilot | t18-quality-gate-2 | 4059 | 45 | - | - | Y |
| goal-autopilot | t18-quality-gate-3 | 4330 | 45 | - | - | Y |
| goal-autopilot | t18-quality-gate-4 | 4401 | 41 | - | - | Y |
| goal-autopilot | t18-quality-gate | 3813 | 45 | - | - | Y |
| mw-autopilot-slot-capacity | msc-d1-gate-propositions | 3057 | 19 | - | - | - |
| mw-autopilot-slot-capacity | msc-d2-deferred-review-state | 3755 | 22 | - | - | - |
| mw-autopilot-slot-capacity | msc-d3-consumption-record | 3724 | 20 | - | - | - |
| mw-autopilot-slot-capacity | msc-d4-evidence-provenance | 3273 | 18 | - | - | - |
| mw-autopilot-slot-capacity | msc-d5-auto-decision-controls | 4029 | 19 | - | - | - |
| mw-autopilot-slot-capacity | msc-d6-gate-schema-presentation | 3071 | 18 | - | - | - |
| mw-autopilot-slot-capacity | msc-d7-watchdog-and-serial | 3542 | 18 | - | - | - |
| mw-autopilot-slot-capacity | msc-qg-quality-gate | 4786 | 39 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq1-concurrency-anchors | 3090 | 18 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq10-auto-gate-boundary | 3779 | 18 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq11-auto-gate-guardrails | 4118 | 29 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq12-gate-selfverifiable | 3428 | 18 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq13-gate-defer-safety | 3455 | 20 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq14-gate-review-material | 3494 | 18 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq2-capacity-constraints | 3443 | 18 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq3-slot-utilization | 3297 | 27 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq4-change-space | 3589 | 25 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq5-worker-serialization | 3806 | 19 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq6-stalled-slot-release | 3447 | 17 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq7-panel-divergence | 3435 | 16 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq8-unattended-gates | 4430 | 21 | - | - | - |
| mw-autopilot-slot-capacity | msc-rq9-cap-breach-attribution | 4118 | 22 | - | - | - |
| mw-autopilot-slot-capacity | msc-t01-conductor-guards | 2005 | 29 | - | - | - |
| mw-autopilot-slot-capacity | msc-t02-ts-event-parity | 2177 | 31 | - | - | - |
| mw-autopilot-slot-capacity | msc-t03-gate-schema-v2 | 3027 | 32 | - | - | - |
| mw-autopilot-slot-capacity | msc-t04-idle-heartbeat | 2455 | 31 | - | - | - |
| mw-autopilot-slot-capacity | msc-t05-consumption-carrier | 2607 | 35 | - | - | - |
| mw-autopilot-slot-capacity | msc-t06-evidence-provenance | 3006 | 34 | - | - | - |
| mw-autopilot-slot-capacity | msc-t07-auto-decision-core | 4412 | 39 | - | - | - |
| mw-autopilot-slot-capacity | msc-t08-pending-review | 4573 | 37 | - | - | - |
| mw-autopilot-slot-capacity | msc-t09-ts-presentation | 3518 | 35 | - | - | - |
| mw-autopilot-slot-capacity | msc-t10-guard-coverage | 2354 | 29 | - | - | - |
| mw-autopilot-slot-capacity | msc-t11-parity-corpus | 3035 | 34 | - | - | - |
| mw-autopilot-slot-capacity | msc-t12-attribution-timeout | 2930 | 34 | - | - | - |
| mw-autopilot-slot-capacity | msc-t13-doctor-cli | 3618 | 34 | - | - | - |
| mw-autopilot-slot-capacity | msc-t14-docs-dist-regression | 4017 | 30 | - | - | - |
| mw-autopilot-slot-capacity | msc-t15-count-locks | 2844 | 35 | - | - | - |
| mw-autopilot-slot-capacity | msc-t16-attribution-delegation | 3680 | 35 | - | - | - |
| mw-autopilot-slot-capacity | msc-t17-ts-count-locks | 2493 | 29 | - | - | - |
| mw-autopilot-slot-capacity | msc-t18-gate-default-bypass | 3511 | 32 | - | - | - |
| mw-autopilot-slot-capacity | msc-t19-case2-producer | 4312 | 35 | - | - | - |
| mw-autopilot-slot-capacity | msc-t20-reason-code-scope | 5092 | 44 | - | - | - |
| mw-autopilot-slot-capacity | msc-t21-defer-ledger | 5320 | 45 | - | - | - |
| mw-autopilot-slot-capacity | msc-t22-evidence-line-audit | 3299 | 38 | - | - | - |
| mw-autopilot-slot-capacity | msc-t23-status-parity-lock | 2458 | 15 | - | - | - |
| mw-autopilot-slot-capacity | msc-t23b-status-parity-lock | 3111 | 21 | - | - | - |
| mw-autopilot-slot-capacity | msc-t24-crosskey-prose | 3109 | 13 | - | - | - |
| mw-autopilot-stall-feedback | mw-stall-feedback-l3-review-a2 | 3039 | 32 | Y | - | - |
| mw-autopilot-stall-feedback | mw-stall-feedback-l3-review | 3516 | 24 | Y | - | Y |
| mw-autopilot-verify-cli | design-rqd1-cache-pickup | 2569 | 20 | - | - | - |
| mw-autopilot-verify-cli | design-rqd2-machine-layer | 3028 | 19 | - | - | - |
| mw-autopilot-verify-cli | design-rqd3-cwd-root-anchor | 2971 | 17 | - | - | - |
| mw-autopilot-verify-cli | design-rqd4-write-lock | 2743 | 15 | - | - | - |
| mw-autopilot-verify-cli | design-rqd5-dist-anchor-guard | 3555 | 15 | - | - | - |
| mw-autopilot-verify-cli | design-rqd6-crosslang-consistency | 3593 | 19 | - | - | - |
| mw-autopilot-verify-cli | mavc-t01-config-basics | 2754 | 24 | - | - | - |
| mw-autopilot-verify-cli | mavc-t01b-narrow-default-merge | 3383 | 18 | - | - | - |
| mw-autopilot-verify-cli | mavc-t02-effective-config | 3761 | 33 | - | - | - |
| mw-autopilot-verify-cli | mavc-t02b-layering-rule | 3993 | 41 | - | - | - |
| mw-autopilot-verify-cli | mavc-t02c-self-sufficient-values | 3432 | 25 | - | - | - |
| mw-autopilot-verify-cli | mavc-t03-mw-common | 3361 | 26 | - | - | - |
| mw-autopilot-verify-cli | mavc-t03b-top-import-doctor-layer | 3195 | 22 | - | - | - |
| mw-autopilot-verify-cli | mavc-t04-ts-mirror-lock | 3132 | 17 | - | - | - |
| mw-autopilot-verify-cli | mavc-t05-mw-cli | 4075 | 29 | - | - | - |
| mw-autopilot-verify-cli | mavc-t06-conductor-root-anchor | 4175 | 20 | - | - | - |
| mw-autopilot-verify-cli | mavc-t07-crosslang-parity | 4349 | 31 | - | - | - |
| mw-autopilot-verify-cli | mavc-t07b-parity-view-split | 3922 | 23 | - | - | - |
| mw-autopilot-verify-cli | mavc-t08-update-env-recurrence | 4389 | 22 | - | - | - |
| mw-autopilot-verify-cli | mavc-t09-cwd-placeholder-table | 3296 | 21 | - | - | - |
| mw-autopilot-verify-cli | mavc-t10-docs-dist-regression | 6130 | 38 | - | - | - |
| mw-autopilot-verify-cli | mavc-t11-serve-partial-config | 3298 | 23 | - | - | - |
| mw-autopilot-verify-cli | spec-rq1-mw-cli-patterns | 1801 | 16 | - | - | - |
| mw-autopilot-verify-cli | spec-rq2-config-write-contract | 1963 | 15 | - | - | - |
| mw-autopilot-verify-cli | spec-rq3-dist-rebuild | 2036 | 17 | - | - | - |
| mw-autopilot-verify-cli | spec-rq4-verify-cmd-portability | 2357 | 15 | - | - | - |
| mw-claude-mirror-parity | mwp-rq1c-mirror-inventory | 2550 | 24 | - | - | - |
| mw-claude-mirror-parity | mwp-rq2c-mirror-semantics | 2416 | 23 | - | - | - |
| mw-claude-mirror-parity | mwp-rq3c-distribution-path | 2564 | 24 | - | - | - |
| mw-crosskey-risk-escalation | mwcre-t1-crosskey-escalation | 2586 | 30 | - | - | - |
| mw-crosskey-risk-escalation | mwcre-t3-verify | 2141 | 19 | - | - | - |
| mw-dispatch-card-gate | mwd-rq1-dispatch-path | 2950 | 26 | - | - | - |
| mw-dispatch-card-gate | mwd-rq2-card-corpus | 3097 | 27 | - | - | - |
| mw-dispatch-card-gate | mwd-rq2b-dispatch-input-format | 3497 | 26 | - | - | - |
| mw-dispatch-card-gate | mwd-rq3-gate-layer | 3346 | 28 | - | - | - |
| mw-dispatch-flow-fixes | code-review-1 | 1747 | 18 | - | - | - |
| mw-dispatch-flow-fixes | ga-spec-review-2 | 778 | 9 | - | - | - |
| mw-dispatch-flow-fixes | smoke-ac015-ac016 | 123 | 3 | - | - | - |
| mw-dispatch-flow-fixes | smoke-ac016b | 116 | 4 | - | - | - |
| mw-dispatch-reliability | mw-dr-glm53 | 83 | 4 | - | - | - |
| mw-dispatch-reliability | mw-dr-keyed-probe | 77 | 4 | - | - | - |
| mw-dispatch-reliability | mw-dr-live-claude2 | 368 | 3 | - | - | - |
| mw-dispatch-reliability | mw-dr-live-claude3 | 245 | 3 | - | - | - |
| mw-dispatch-reliability | mw-dr-live-claude4 | 179 | 3 | - | - | - |
| mw-dispatch-reliability | mw-dr-live-claude | 131 | 4 | - | - | - |
| mw-dispatch-reliability | mw-dr-live-ok | 80 | 4 | - | - | - |
| mw-dispatch-reliability | mw-dr-pi-timi-test | 162 | 5 | - | - | - |
| mw-dispatch-settle-gates | mds-drq1-write-surface | 5230 | 50 | Y | - | Y |
| mw-dispatch-settle-gates | mds-drq2-settle-read | 5609 | 46 | Y | - | Y |
| mw-dispatch-settle-gates | mds-qg-a-evidence-chain | 3687 | 20 | - | - | - |
| mw-dispatch-settle-gates | mds-qg-b-code-adversarial | 4197 | 23 | - | - | - |
| mw-dispatch-settle-gates | mds-rq1-stage-terminality | 3865 | 42 | Y | - | Y |
| mw-dispatch-settle-gates | mds-rq2-product-contract | 5018 | 47 | Y | - | Y |
| mw-dispatch-settle-gates | mds-t01-crosskey-guard | 1567 | 10 | - | - | - |
| mw-dispatch-settle-gates | mds-t02-write-intent | 2383 | 14 | - | - | - |
| mw-dispatch-settle-gates | mds-t03-bash-write-scope | 1661 | 10 | - | - | - |
| mw-dispatch-settle-gates | mds-t04-deliverable-gate | 2623 | 14 | - | - | - |
| mw-dispatch-settle-gates | mds-t05-output-sections | 2367 | 15 | - | - | - |
| mw-dispatch-settle-gates | mds-t06-output-informativeness | 2109 | 16 | - | - | - |
| mw-dispatch-settle-gates | mds-t07-reap-productfirst | 1520 | 10 | - | - | - |
| mw-dispatch-settle-gates | mds-t08-doctor-blocked | 1291 | 10 | - | - | - |
| mw-dispatch-settle-gates | mds-t09-gate-stage | 1503 | 10 | - | - | - |
| mw-dispatch-settle-gates | mds-t10-dispatch-runstate | 1430 | 10 | - | - | - |
| mw-dispatch-settle-gates | mds-t11-docs-errata | 1640 | 10 | - | - | - |
| mw-dispatch-settle-gates | mds-t12-consolidation | 3232 | 19 | - | - | - |
| mw-done-closure-repair | dcr-review-spec-design | 3125 | 28 | - | - | - |
| mw-done-closure-repair | dcr-rq1-return-path | 2302 | 15 | - | - | - |
| mw-done-closure-repair | dcr-rq2-marker-mechanics | 2552 | 17 | - | - | - |
| mw-done-closure-repair | dcr-rq3-reprompt-loop | 2959 | 17 | - | - | - |
| mw-done-closure-repair | dcr-t02-closure-module | 4476 | 28 | - | - | - |
| mw-done-closure-repair | dcr-t03t05-conductor | 5408 | 61 | - | - | - |
| mw-done-closure-repair | dcr-t06t08-exec-tests | 4396 | 40 | - | - | - |
| mw-dual-workspace | qg-review-mw-dual-workspace | 4386 | 36 | - | - | - |
| mw-gate-verdict-hardening | mgh-drq1-l3-wiring | 3735 | 19 | - | - | - |
| mw-gate-verdict-hardening | mgh-drq2-reminder-wiring | 4037 | 19 | - | - | - |
| mw-gate-verdict-hardening | mgh-drq3-authz-wiring | 4748 | 19 | - | - | - |
| mw-gate-verdict-hardening | mgh-rq1-l3-abort | 2522 | 18 | - | - | - |
| mw-gate-verdict-hardening | mgh-rq2-gate-alert | 2317 | 19 | - | - | - |
| mw-gate-verdict-hardening | mgh-rq3-gate-authz | 3001 | 19 | - | - | - |
| mw-gate-verdict-hardening | mgh-rq4-monitor-freeze | 4425 | 21 | - | - | - |
| mw-gate-verdict-hardening | mgh-rq5-launcher-requeue | 3672 | 21 | - | - | - |
| mw-gate-verdict-hardening | mwg-qg-review-20261010 | 9464 | 79 | - | - | - |
| mw-gate-verdict-hardening | mwg-qg2a-evidence-chain | 5458 | 55 | - | Y | Y |
| mw-gate-verdict-hardening | mwg-qg2b-code-adversarial | 7135 | 59 | - | - | Y |
| mw-gate-verdict-hardening | mwg-t01-l3-aborted | 4290 | 34 | - | - | - |
| mw-gate-verdict-hardening | mwg-t02-config-keys | 3885 | 37 | - | - | - |
| mw-gate-verdict-hardening | mwg-t03-event-names | 3074 | 32 | - | - | - |
| mw-gate-verdict-hardening | mwg-t04-contract-guard | 4803 | 42 | - | - | - |
| mw-gate-verdict-hardening | mwg-t05-ts-mirror | 4419 | 38 | - | - | - |
| mw-gate-verdict-hardening | mwg-t06-l3-tests | 3535 | 30 | - | - | - |
| mw-gate-verdict-hardening | mwg-t07-gate-reminder | 5001 | 38 | - | - | - |
| mw-gate-verdict-hardening | mwg-t08-g2-surfaces | 5164 | 38 | - | - | - |
| mw-gate-verdict-hardening | mwg-t08b-g2-surfaces | 5305 | 39 | - | - | - |
| mw-gate-verdict-hardening | mwg-t09-pm-consumer | 4767 | 37 | - | - | - |
| mw-gate-verdict-hardening | mwg-t10-g3-done-guard | 5575 | 41 | - | - | - |
| mw-gate-verdict-hardening | mwg-t11-g3-cli-doctor | 5531 | 44 | - | - | - |
| mw-gate-verdict-hardening | mwg-t12-g3-writer-g4-rearm | 5561 | 41 | - | - | - |
| mw-gate-verdict-hardening | mwg-t13-g4-freshness | 5063 | 40 | - | - | - |
| mw-gate-verdict-hardening | mwg-t14-count-locks | 6648 | 50 | - | - | - |
| mw-gate-verdict-hardening | mwg-t16-docs-closure | 4816 | 29 | - | - | - |
| mw-gate-verdict-hardening | mwg-t23-g3-anchor | 5960 | 49 | - | - | - |
| mw-guard-form-hardening | mwgf-cutover-smoke2 | 2619 | 37 | - | Y | Y |
| mw-guard-form-hardening | mwgf-cutover-smoke3 | 3813 | 47 | Y | Y | Y |
| mw-guard-form-hardening | mwgf-cutover-smoke | 2753 | 39 | - | Y | Y |
| mw-guard-form-hardening | mwgf-drq1-write-guard-design | 3372 | 28 | - | - | Y |
| mw-guard-form-hardening | mwgf-drq2-target-axis-design | 3723 | 32 | Y | - | Y |
| mw-guard-form-hardening | mwgf-drq3-role-key-design | 4196 | 33 | Y | - | Y |
| mw-guard-form-hardening | mwgf-qga-code-adversarial | 3550 | 23 | - | - | Y |
| mw-guard-form-hardening | mwgf-qga2-code-adversarial | 3130 | 24 | Y | - | Y |
| mw-guard-form-hardening | mwgf-qga3-final-adversarial | 2838 | 22 | - | - | Y |
| mw-guard-form-hardening | mwgf-qgb-evidence-chain | 4073 | 25 | - | Y | Y |
| mw-guard-form-hardening | mwgf-qgb2-evidence-recheck | 4065 | 25 | Y | Y | Y |
| mw-guard-form-hardening | mwgf-qgb3-final-recheck | 3632 | 21 | - | - | Y |
| mw-guard-form-hardening | mwgf-rq1-form-inventory | 2873 | 29 | Y | - | Y |
| mw-guard-form-hardening | mwgf-rq2-direction-contract | 2465 | 19 | Y | - | Y |
| mw-guard-form-hardening | mwgf-rq3-path-resolution | 3384 | 21 | Y | - | Y |
| mw-guard-form-hardening | mwgf-rq4-taskmd-corpus | 3073 | 20 | Y | - | Y |
| mw-guard-form-hardening | mwgf-rq5-key-identity | 3178 | 24 | Y | - | Y |
| mw-guard-form-hardening | mwgf-t01-form-inventory | 2143 | 27 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t02-verbatim-contract | 3119 | 31 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t03-audit-alarm | 3212 | 33 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t04-shape-judge | 2632 | 29 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t06-task-frontmatter | 2299 | 30 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t07-parser-single-source | 3107 | 32 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t08-python-parity | 3040 | 30 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t09-key-identity | 3169 | 32 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t10-branch-coverage | 4117 | 36 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t11-assertion-quality | 2764 | 30 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t12-contract-docs | 3301 | 30 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t13-closure-evidence | 3974 | 30 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t14-python-callsite | 3263 | 32 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t15-python-claim | 3197 | 32 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t16-claim-family-gate | 3760 | 34 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t17-repair-reanchor | 3830 | 32 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t18-exe-wrapper-vc-labels | 3125 | 30 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t19-residual-fixes | 3479 | 31 | - | Y | Y |
| mw-guard-form-hardening | mwgf-t20-final-fixes | 3241 | 31 | - | Y | Y |
| mw-implementation-gate | t1t2-gate-module | 3567 | 23 | - | - | - |
| mw-implementation-gate | t3-gate-suite-tests | 4099 | 26 | - | - | - |
| mw-implementation-gate | t4-skill-trigger-words | 1866 | 16 | - | - | - |
| mw-l3-fail-marker-forms | fmr-review-spec-design | 3709 | 21 | - | - | - |
| mw-l3-fail-marker-forms | fmr-rq1-code-facts | 3374 | 18 | - | - | - |
| mw-l3-fail-marker-forms | fmr-rq2-fail-corpus | 3021 | 17 | - | - | - |
| mw-l3-fail-marker-forms | fmr-rq3-negative-corpus | 3227 | 22 | - | - | - |
| mw-l3-fail-marker-forms | fmr-t01-l1-truth-table | 5437 | 43 | - | - | - |
| mw-l3-fail-marker-forms | fmr-t02-conductor-impl | 8586 | 56 | - | - | - |
| mw-l3-fail-marker-forms | fmr-t03-l2-scenarios | 5183 | 30 | - | - | - |
| mw-partition-parent-extended | mwppe-quality-gate | 5048 | 34 | - | - | - |
| mw-partition-parent-extended | test-hello-world-glm53 | 473 | 12 | - | - | - |
| mw-rag-config-guide | mw-rag-cfg-t21-init | 2292 | 22 | - | - | - |
| mw-rag-config-guide | mw-rag-cfg-t22-manual | 2954 | 28 | - | - | - |
| mw-rag-config-guide | mw-rag-cfg-t23-verify | 2521 | 26 | - | - | - |
| mw-rag-integration-fix | mw-rag-fix-t15-role-defaults | 2716 | 28 | - | - | - |
| mw-rag-integration-fix | mw-rag-fix-t16-py-role-unreachable | 2302 | 25 | - | - | - |
| mw-rag-integration-fix | mw-rag-fix-t17-docs-bundle | 2718 | 26 | - | - | - |
| mw-rag-integration-fix | mw-rag-fix-t18-verify | 2909 | 29 | - | - | - |
| mw-rag-integration-fix | mw-rag-fix-t19-defaults-parity | 2833 | 33 | - | - | - |
| mw-rag-integration | mw-rag-integration-design-critique | 5026 | 62 | - | - | Y |
| mw-rag-integration | mw-rag-integration-design-review | 6073 | 65 | - | - | Y |
| mw-rag-integration | mw-rag-integration-ref-verify | 5201 | 53 | - | - | Y |
| mw-rag-integration | mw-rag-qg-review-a | 3916 | 35 | - | - | Y |
| mw-rag-integration | mw-rag-qg-review-b | 4339 | 39 | - | - | Y |
| mw-rag-integration | mw-rag-qg-review-c | 6444 | 39 | - | Y | - |
| mw-rag-integration | mw-rag-qg-review | 6155 | 54 | - | Y | Y |
| mw-rag-integration | mw-rag-t01-ts-config | 1796 | 19 | - | - | - |
| mw-rag-integration | mw-rag-t02-adapter | 1902 | 20 | - | - | - |
| mw-rag-integration | mw-rag-t03-transport | 2217 | 21 | - | - | - |
| mw-rag-integration | mw-rag-t04-tools | 3284 | 29 | - | - | - |
| mw-rag-integration | mw-rag-t05-evidence | 3519 | 29 | - | - | - |
| mw-rag-integration | mw-rag-t06-py-config | 1363 | 12 | - | - | - |
| mw-rag-integration | mw-rag-t07-py-inject | 2650 | 21 | - | - | - |
| mw-rag-integration | mw-rag-t08-py-cli | 2605 | 22 | - | - | - |
| mw-rag-integration | mw-rag-t09-research | 3710 | 32 | - | - | - |
| mw-rag-integration | mw-rag-t10-audit | 3259 | 26 | - | - | - |
| mw-rag-integration | mw-rag-t11-verify | 3915 | 20 | - | - | - |
| mw-rag-integration | mw-rag-t12-parity-lock | 2912 | 22 | - | - | - |
| mw-rag-integration | mw-rag-t13-toolmap | 3101 | 22 | - | - | - |
| mw-rag-integration | mw-rag-t14-phase-axis | 3258 | 22 | - | - | - |
| mw-rag-window-parity | mw-rwp-qg-review | 2630 | 17 | - | - | - |
| mw-rag-window-parity | mw-rwp-t1-skill-dir-parity | 1703 | 17 | - | - | - |
| mw-rag-window-parity | mw-rwp-t2-mw-rag-cmd | 2168 | 18 | - | - | - |
| mw-rag-window-parity | mw-rwp-t3-doctor-rag-row | 2125 | 18 | - | - | - |
| mw-rag-window-parity | mw-rwp-t4-verify | 2413 | 19 | - | - | - |
| mw-rag-window-parity | mw-rwp-t5-verify-delta | 1926 | 19 | - | - | - |
| mw-target-partition | mwtp-e2e-spawn | 4263 | 32 | - | - | - |
| mw-target-partition | mwtp-final-fixes-3 | 3992 | 36 | - | - | - |
| mw-target-partition | mwtp-final-fixes | 1516 | 12 | - | - | - |
| mw-target-partition | mwtp-final-review-2 | 3749 | 24 | - | - | - |
| mw-target-partition | mwtp-final-review-3 | 3266 | 19 | - | - | - |
| mw-target-partition | mwtp-final-review | 5562 | 59 | - | - | Y |
| mw-target-partition | mwtp-s0-baseline | 4407 | 41 | - | - | - |
| mw-target-partition | mwtp-s1-parse-retry | 6822 | 49 | - | - | - |
| mw-target-partition | mwtp-s1-parse | 6383 | 45 | - | - | - |
| mw-target-partition | mwtp-s2-dispatch | 1689 | 15 | - | - | - |
| mw-target-partition | mwtp-s3-cli | 6516 | 50 | - | - | - |
| mw-target-partition | mwtp-s4-verify | 4170 | 38 | - | - | - |
| mw-target-partition | mwtp-verify-gate-2 | 826 | 9 | - | - | - |
| mw-target-partition | mwtp-verify-gate | 3525 | 27 | - | - | - |
| mw-target-partition | review-mw-target-partition-design | 4031 | 45 | Y | - | Y |
| mw-target-partition | review-mw-target-partition-spec | 3793 | 43 | Y | - | Y |
| mw-vision-role | mvr-d1-doctor-show-output-contract | 2637 | 20 | - | - | - |
| mw-vision-role | mvr-d2-python-probe-contract | 2918 | 21 | - | - | - |
| mw-vision-role | mvr-d3-images-header-writer-python | 2923 | 21 | - | - | - |
| mw-vision-role | mvr-d4-ts-gate-autoroute-interface | 3479 | 21 | - | - | - |
| mw-vision-role | mvr-d5-verification-feasibility | 3197 | 26 | - | - | - |
| mw-vision-role | mvr-fix1-doctor-vision-scoped-suggestion | 3085 | 41 | - | - | - |
| mw-vision-role | mvr-r1-live-vision-red | 675 | 11 | - | - | - |
| mw-vision-role | mvr-rq1-role-type-plumbing | 3163 | 19 | - | - | - |
| mw-vision-role | mvr-rq2-capability-gate-hooks | 3071 | 19 | - | - | - |
| mw-vision-role | mvr-rq3-images-header-contract | 2753 | 19 | - | - | - |
| mw-vision-role | mvr-rq4-vision-io-and-candidates | 2699 | 16 | - | - | - |
| mw-vision-role | mvr-rq5-awareness-surface | 3729 | 27 | - | - | - |
| mw-vision-role | mvr-t01-python-role-type-registry | 1766 | 23 | - | - | - |
| mw-vision-role | mvr-t02-ts-role-type-allowlist | 1978 | 22 | - | - | - |
| mw-vision-role | mvr-t03-parity-refreeze | 3045 | 29 | - | - | - |
| mw-vision-role | mvr-t04-image-capability-fn | 2858 | 34 | - | - | - |
| mw-vision-role | mvr-t05-images-header-write-side | 1798 | 23 | - | - | - |
| mw-vision-role | mvr-t06-dispatch-capability-gate | 5286 | 48 | - | Y | - |
| mw-vision-role | mvr-t07-auto-route-model-only | 4583 | 47 | - | Y | - |
| mw-vision-role | mvr-t08-python-render-images | 2318 | 27 | - | - | - |
| mw-vision-role | mvr-t09-worker-image-cap-backstop | 3557 | 33 | - | - | - |
| mw-vision-role | mvr-t10-python-model-probe | 3109 | 36 | - | - | - |
| mw-vision-role | mvr-t11-model-set-capability-refusal | 3330 | 47 | - | Y | - |
| mw-vision-role | mvr-t12-capability-visibility | 4891 | 53 | - | Y | - |
| mw-vision-role | mvr-t13-pm-awareness-texts | 4041 | 43 | - | Y | - |
| mw-vision-role | mvr-t14-verification-closeout | 3003 | 32 | - | Y | Y |
| mw-vision-role | mvr-t16-quality-gate-review | 4704 | 35 | - | - | - |
| mw-vision-role | mvr-t17-fix-description-optional | 2267 | 23 | - | - | - |
| mw-vision-role | mvr-t18-vc003-vc007-evidence | 2723 | 31 | - | - | - |
| mw-vision-role | mvr-t19-evidence-refresh | 2960 | 23 | - | - | - |
| mw-widget-terminal-lifecycle | wtl-t01-ack-store | 1440 | 11 | - | - | - |
| mw-widget-terminal-lifecycle | wtl-t02-mw-common | 1832 | 16 | - | - | - |
| mw-widget-terminal-lifecycle | wtl-t03-tldr | 1881 | 14 | - | - | - |
| mw-widget-terminal-lifecycle | wtl-t04-starter | 1338 | 13 | - | - | - |
| mw-widget-terminal-lifecycle | wtl-t08-reconcile | 3188 | 23 | - | - | - |
| mw-worker-progress-persist | mwpp-d1-tool-contract | 2789 | 21 | - | - | - |
| mw-worker-progress-persist | mwpp-d2-collection-parity | 2711 | 22 | - | - | - |
| mw-worker-progress-persist | mwpp-d3-test-harness | 3099 | 21 | - | - | - |
| mw-worker-progress-persist | mwpp-t1-progress-writer | 1617 | 14 | - | - | - |
| mw-worker-progress-persist | mwpp-t2-worker-file-tool | 1554 | 14 | - | - | - |
| mw-worker-progress-persist | mwpp-t3-checkpoint-wiring | 2456 | 16 | - | - | - |
| mw-worker-progress-persist | mwpp-t5-real-smoke | 1291 | 11 | - | - | - |
| mw-worker-progress-persist | mwpp-t6-independent-verify | 1772 | 15 | - | - | - |
| mw-worker-timeout-convergence | smoke-watchdog | 378 | 11 | - | - | - |
| mw-worker-tree-kill | manual-1789974567567 | 118 | 5 | - | - | - |
| mw-worker-tree-kill | review-mw-worker-tree-kill | 4317 | 89 | Y | - | Y |
| mw-worker-tree-kill | smoke-tree-kill-1 | 402 | 13 | - | - | - |
| mw-worker-visibility-gate | mwvg-t1-phase-docs-gate | 1836 | 20 | - | - | - |
| mw-worker-visibility-gate | mwvg-t2-pm-state-claim | 2078 | 21 | - | - | - |
| mw-worker-visibility-gate | mwvg-t3-wiring | 2739 | 27 | - | - | - |
| mw-worker-visibility-gate | mwvg-t5-verify | 2527 | 19 | - | - | - |
| mw-worker-visibility-gate | mwvg-t6-claim-insert | 2510 | 24 | - | - | - |
| mw-workspace-incident-probe | inc1-junction-forensics | 2373 | 23 | - | Y | Y |
| mw-workspace-incident-probe | inc2-vanish-forensics | 2610 | 19 | - | Y | Y |
| mw-workspace-incident-probe | wip-qg-review | 2558 | 28 | - | Y | Y |
| mw-worktree-junction-guard | wjg-rq1-junction-semantics | 2526 | 25 | Y | Y | - |
| mw-worktree-junction-guard | wjg-rq2-guard-seams | 2485 | 19 | Y | Y | - |
| xkey-repair-mechanism | xkey-rm-rq1-code-facts | 2583 | 17 | - | - | - |
| xkey-repair-mechanism | xkey-rm-rq2-incident-corpus | 3162 | 21 | - | - | - |
| xkey-repair-mechanism | xkey-rm-rq3-reusable-parts | 2236 | 19 | - | - | - |
| xkey-repair-mechanism | xkey-rm-rqd1-registration-carrier | 3254 | 22 | - | - | - |
| xkey-repair-mechanism | xkey-rm-rqd2-ledger-ticket-shapes | 3435 | 25 | - | - | - |
| xkey-repair-mechanism | xkey-rm-rqd3-boundary-apply | 3984 | 23 | - | - | - |
| xkey-repair-mechanism | xkey-rm-rqd4-human-only-answer | 3930 | 27 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t01-core-module | 1597 | 9 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t02-l1-tests | 1505 | 11 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t03-conductor-mount | 2264 | 17 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t04-ts-guard | 1670 | 11 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t04b-ts-config-mirror | 1474 | 11 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t05-l2-e2e-replay | 1809 | 13 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t06-apply-verify-close | 1749 | 11 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t07-unskip-verified | 1272 | 13 | - | - | - |
| xkey-repair-mechanism | xkey-rm-t08-dispatch-proposal | 2015 | 11 | - | - | - |
| **合计 343** |  |  |  | **21 (6.1%)** | **45 (13.1%)** | **61 (17.8%)** |

## 附录 B：复现命令与产物清单

```powershell
# 语料清点
(Get-ChildItem .agenticdoc -Recurse -Filter task.md | Where-Object { $_.FullName -match '\\workers\\[^\\]+\\task\.md$' }).Count   # 343

# 矩阵 A/B/C（RQ-2 同一分类器的副本）
python .agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2b-dispatch-input-format\scan_like_rq2.py
# -> cards=343 T1fail=341 T1efail=340 T2fail=203 T2fail_ge800=183 h2zero=259

# 清点 + 标题 + type 分布
python .agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2b-dispatch-input-format\analyze.py
python .agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2b-dispatch-input-format\sets.py

# 生产代码回放（type 一致性）
node_modules\.bin\tsx.cmd .agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2b-dispatch-input-format\probe-type-consistency.mts

# 卡内 type vs 框架记录值
python .agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2b-dispatch-input-format\compare-recorded.py
```

产物（均在 `.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2b-dispatch-input-format/`）：
`scan4-report.txt`、`scan4-cards.tsv`、`scan4-variants.txt`、`inventory.tsv`、`analyze-report.txt`、
`recorded-type-compare.txt`、`probe-type-consistency.json`、各 `.py`/`.mts` 脚本。