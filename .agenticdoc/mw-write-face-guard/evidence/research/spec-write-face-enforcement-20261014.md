# RQ-W2 证据：派发层插入点与重叠判定可行性

- key: mw-write-face-guard
- 卡: `tasks/T-W2-write-face-enforcement.md` (card_sha256 `c4394e60c9bf5f931eb7c4f62e8868b5c78204bfca84366b97cf4ba048ee7860`)
- 角色: 只读取证；唯一写面 = 本文件
- 采集时间: 2026-10-14
- 全仓只读（含 dist / `.mw` / 其它 key）

---

## 0. 结论先行

1. **两条通道不共用同一个底层函数，各有一个"队列写咽喉"。**
   - conductor 通道：13 处调用点全部汇入 `packages/multi-workers/autopilot/dispatch.py:964 def dispatch(...)`。
   - PM 通道：两个入口 `dispatch_worker` 工具（`pm/ui-bridge.ts:2203`）与 `/worker` 命令（`pm/ui-bridge.ts:2764`），外加后台 orphan 修复 `pm-orchestrator.ts:925`，三者全部汇入 `pm/task-dispatcher.ts:288 dispatchTask` → `shared/worker-store.ts:190 WorkerStore.upsert`。
   - 跨语言不共用（Python vs TS），任何判定必须双边实现并冻结 parity（P-021）。

2. **判定所需数据今天不在队列行里。** `_workers.parallel` 只有 9 列
   `task_key | status | cli | provider | task_path | dispatched_at | updated_at | model | origin`（`mw_common.py:1738-1739`、`worker-store.ts:32-33`），
   没有任何写面列或写面载荷。写面的唯一机器载体是 task.md 的 `write_scope:` 头，
   而它**只由 PM 路径对 writeless+shell 角色渲染**（`ui-bridge.ts:2431`/`2925` 调 `renderDefaultWriteScope`），
   conductor 的 `render_task_md` 根本不接受也不渲染 `write_scope`（`dispatch.py:742` 参数表无此字段）。

3. **"写面 glob 交集"不是既有语义，需要新建。** 既有读面/写面匹配都是"单条具体路径是否落在集合内"的
   判定（minimatch 双基 + realpath 前缀 containment），没有 glob×glob 交集算子。
   复用 minimatch 可行，但必须显式处理三处分歧：大小写（glob 敏感 / containment 在 win32 不敏感）、
   根锚定（root 相对 vs 绝对 vs realpath）、`a/**` 不含 `a` 本身的特例。

4. **最稳的并发安全点不是"派发前"，而是"持 `.mw/workers.lock` 的队列 RMW 内"**
   （Python `dispatch.py:1156-1184`；TS `worker-store.ts:190`）。派发前的检查都不持锁，
   存在 check-then-act 竞态；launcher spawn 前（`launcher.py:1806-1858`）虽是最后一道，但拒绝只能落成 `failed` 行。

---

## 1. 输入与种子复核

| 种子断言 | 复核结果 | 证据 |
|---|---|---|
| conductor 多处 `dispatch.dispatch(...)`（`:1196` 等） | 确认，`conductor.py` 内共 **13** 处 | 见 §1.1 |
| `dispatch.dispatch` 定义在 `dispatch.py:964` 起 | 确认 | `dispatch.py:964 def dispatch(` |
| PM 入口 `pm/ui-bridge.ts:2201` | 确认（工具注册块 `:2199-2201`，`name: "dispatch_worker"` 在 `:2203`） | `ui-bridge.ts:2203 name: "dispatch_worker",` |
| 队列唯一消费者 `launcher.py:819-841` | **偏差：该行号区间当前是 envelope 判据代码，不是 spawn。** spawn 循环实际在 `_poll_once` 内 `launcher.py:1806-1858`，队列读取在 `:1776` | `launcher.py:1707 def _poll_once(`、`:1776 entries = _parse_workers_file(...)`、`:1858 _spawn(...)` |
| 行渲染/解析 `mw_common.py` | 确认 | `mw_common.py:1747 parse_worker_line` / `:1829 parse_workers_file` / `:2152 upsert_worker_row` |

> 种子行号属"可引用但必须复看"项；已按当前工作树复核，偏差如实记录，未做推测补齐。

### 1.1 conductor 派发入口清单（13 处，同一底层 `dispatch.dispatch`）

| # | file:line | 外层函数 | 触发条件（读码） | owner key | type | read_scope |
|---|---|---|---|---|---|---|
| 1 | `conductor.py:1196` | `_dispatch_roadmap_writer` (`:1168`) | `_roadmap.md` 缺失或需 stage 提案，且该 stage 提案未在飞且 attempt<2 | `dispatch.SCRATCH_OWNER`（`_scratch`） | `roadmap-writer` | `[".agenticdoc"]` |
| 2 | `conductor.py:1605` | `_advance_key` (`:1577`) | 阶段 artifact 缺失 → phase-writer | owner `key` | `phase-writer` | 无 |
| 3 | `conductor.py:1643` | `_advance_key` | 上轮 verifier 完成、同轮 fix 行缺失（l2-fix） | `key` | `phase-writer` | 无 |
| 4 | `conductor.py:1679` | `_advance_key` | L1 有 blocking gap 且预算未耗尽 → L2 adjudication | `key` | `verifier` | `[".agenticdoc/<key>", ".agenticdoc/goal.md"]` |
| 5 | `conductor.py:1788` | `execute_loop` (`:1737`) | EXECUTE 波：plan 顺序里首个未 done、无在飞、预算未尽的 task | `key` | `phase-writer`（coding 工具集） | 无 |
| 6 | `conductor.py:2369` | `_verify_loop` (`:2330`) | `round_no == 0` → 首轮 L3 reviewer | `key` | `reviewer` | `[".agenticdoc/<key>", ".agenticdoc/goal.md"]` |
| 7 | `conductor.py:2419` | `_verify_loop` | L3 流中止（aborted）且 reroll 预算未尽 | `key` | `reviewer` | 同 |
| 8 | `conductor.py:2454` | `_verify_loop` | L3 无裁决（no-verdict）且 `used < l3_limit` | `key` | `reviewer` | 同 |
| 9 | `conductor.py:2486` | `_verify_loop` | L3 判定源取证可疑（suspect）且 `used < l3_limit` | `key` | `reviewer` | 同 |
| 10 | `conductor.py:2526` | `_verify_loop` | done-gate 因 achieved 草稿被 vocabulary 拒绝 → reprompt | `key` | `reviewer` | 同 |
| 11 | `conductor.py:2571` | `_verify_loop` | L3 below → repair（本轮回合未 done、无在飞、预算未尽） | `key` | `repair` | 无 |
| 12 | `conductor.py:2579` | `_verify_loop` | repair 已完成 → 下一轮 L3 review | `key` | `reviewer` | `[".agenticdoc/<key>", ".agenticdoc/goal.md"]` |
| 13 | `conductor.py:5098` | `_xkey_proposal_one` (`:5050`) | xkey ticket `status=approved` 且 proposal.md 缺失、未在飞、attempt 未尽 | `ticket["source_key"]`（可跨 key） | `phase-writer` | 无 |

**共用底层**：13 处全部 `result = dispatch.dispatch(project_root, owner, stem, type, prompt, loop=..., attempt=..., [read_scope=...], timeline=st.timeline)`，
定义于 `dispatch.py:964`；无第二实现。

**触发条件里可用的输入**：`owner`、`stem`、`task_type`、`prompt`、`loop`、`attempt`、`read_scope`；
`dispatch.dispatch` 内部还能拿到 `REGISTRY[task_type].tools`（`dispatch.py:1039` `entry = REGISTRY.get(task_type)`）、
`card_path`（`dispatch.py:556 dispatch_card`）与写出的 `task_md` 绝对路径。
**看不到**：队列当前全量行（`dispatch.dispatch` 写前不读队列，唯一读是写后回读校验 `dispatch.py:1189`）。

### 1.2 PM 派发入口清单

| # | file:line | 入口 | 触发条件 | 可见输入 | 是否共用底层 |
|---|---|---|---|---|---|
| P1 | `pm/ui-bridge.ts:2203` | `dispatch_worker` 工具 | agent 调用工具；经 rag gate / cross-key guard / write-intent / docs gate / card gate / model plan 后写 task.md 并入队 | `ownerKey`(resolveOwnerKeyWithSync)、`task_key`、`type`、`card_path`、`cli/provider/model`、`description` | 是，→ `writeDispatchTaskMd` (`:2150`) + `dispatchTask` (`task-dispatcher.ts:288`) |
| P2 | `pm/ui-bridge.ts:2764` | `/worker` 命令 | 用户敲 `/worker ... --card ...` | 同上（命令行解析）+ `--key` | 是，同 P1（`:2918` `writeDispatchTaskMd`、`:2935` `dispatchTask`） |
| P3 | `pm/pm-orchestrator.ts:925` | orphan 修复 `dispatchOrphanCandidates`→`dispatchTask` | 后台扫描发现 `{key}/workers/<tk>/task.md` 已存在但队列无行 | `taskKey`、`taskMdPath`、`queue.rows`（`:953 readQueue()`） | 是，`dispatchTask` |

三条入口都经 `task-dispatcher.ts:288 dispatchTask` → `:299 await store.upsert(full)`；
task.md 单一写点是 `ui-bridge.ts:2150 writeDispatchTaskMd`（`:2142-2148` 注释自称 "Both dispatch entries ... go through here"）。

**PM 侧写面输入现状**：`dispatch_worker`/`/worker` 只有在 `writelessRole && isShellRole(typeField)` 时才渲染 `write_scope:`
（`ui-bridge.ts:2430-2431`、`:2924-2925`），即 **research**（writeless+shell）才有；
coding/review/vision 无 `write_scope` 头（默认写面 = 自身 taskDir + `<key>/evidence`，由运行期 `checkBashWriteScopeTarget` 兜底）。

### 1.3 队列写者/读者总表（新列/新载荷的影响面输入）

| 语言 | 角色 | file:line | 机制 |
|---|---|---|---|
| Py | 写 | `mw_common.py:2152 upsert_worker_row`（唯一生产调用者 `dispatch.py:1174`） | `_scan_worker_lines` 保槽 + `serialize_entry` + tmp+replace |
| Py | 写(status) | `mw_common.py:2175 update_status` | 只改 status/updated_at |
| Py | 写(归档) | `mw_common.py:2213 archive_stale_entries` | 移出 stale 行 |
| Py | 读 | `mw_common.py:1747 parse_worker_line` / `:1793 parse_workers_queue` / `:1829 parse_workers_file` | 列宽硬校验 7..9 |
| Py | 读 | `launcher.py:465,1471,1739,1776,2036`；`mw_common.py:2480,2661,3396`；`mw.py:1920`；`conductor.py:620,3200,6813,6860,6983,7985` | 行 dict |
| TS | 写 | `shared/worker-store.ts:190 upsert`（经 `task-dispatcher.ts:299`） | 保槽 + `serializeWorkerLine` + tmp+rename |
| TS | 读 | `shared/worker-store.ts:168 readQueue` / `:187 readAll` | 列宽硬校验 7..9 |
| TS | 读消费 | `autopilot/monitor.ts:493`；`pm/ui-bridge.ts:645,716,1100,2519,2530,2537,2545`；`pm/pm-orchestrator.ts:953,1003,1352,1400` | 行对象字段 |
| TS | 读消费 | `pm/pm-orchestrator.ts:1003-1013` | `queue.unparsable.length > 0` → 整轮扫描中止 |
---

## 2. `_workers.parallel` 现有列与语义

### 2.1 逐列（解析函数原文）

`mw_common.py:1747-1768`：

```python
def parse_worker_line(line: str) -> dict[str, str] | None:
    ...
    parts = [p.strip() for p in stripped.split("|")]
    if len(parts) < WORKER_COLS_MIN or len(parts) > WORKER_COLS_MAX:
        return None
    return {
        "task_key": parts[0],
        "status": parts[1],
        "cli": parts[2],
        "provider": parts[3],
        "task_path": parts[4],
        "dispatched_at": parts[5],
        "updated_at": parts[6],
        "model": parts[7] if len(parts) >= 8 else "",
        "origin": parts[8] if len(parts) == 9 else "",
    }
```

`mw_common.py:1829-1842`（docstring）：列序 `task_key | status | cli | provider | task_path | dispatched_at | updated_at | model | origin`，
7/8 列 legacy 兼容，缺 origin 为 `""`（不猜）。

| 列 | 语义 | Py 解析 | TS 解析 | 承载写面？ |
|---|---|---|---|---|
| `task_key` | 队列/任务目录身份（`ap-<owner>-<stem>` 或 manual key） | `parts[0]` | `parts[0]` (`worker-store.ts:105-128`) | 否 |
| `status` | pending/running/done/failed/needs-clarification/lost | `parts[1]` | `parts[1]` | 否 |
| `cli` | worker CLI | `parts[2]` | `parts[2]` | 否 |
| `provider` | 路由 provider | `parts[3]` | `parts[3]` | 否 |
| `task_path` | task.md 绝对路径（`workerOwnerKey` 从它提取 owner key） | `parts[4]` | `parts[4]` | 间接：可从 task.md 再解析出 `write_scope:`，但**不是行列** |
| `dispatched_at` | 创建时间（envelope 判据用的唯一创建时间，`launcher.py:830`） | `parts[5]` | `parts[5]` | 否 |
| `updated_at` | 最近改写时间（reap/reconcile 会动，非创建时间） | `parts[6]` | `parts[6]` | 否 |
| `model` | 显式模型（展示运输；显式值以 task.md `model:` 为准） | `parts[7]` | `parts[7]` | 否 |
| `origin` | `conductor`/`manual`（缺失=空，TS normalize 为 `manual`） | `parts[8]` | `parts[8]` + `normalizeWorkerOrigin` | 否 |

**没有写面列/载荷。** 实测：全仓 419 行，8 列 361 + 9 列 58，无 7 列，无 10 列（见 `[VERIFY]`）。

### 2.2 写面的既有载体（都不是队列行）

| 载体 | 生产 | 消费 | 机器可读？ | 覆盖哪条通道 |
|---|---|---|---|---|
| task.md `write_scope:` 头 | `ui-bridge.ts:1779 renderDefaultWriteScope`（仅 writeless+shell） | `worker-mode.ts:440-465 parseTaskMd` → `writeScope: string[]` | 是（逗号一行 或 YAML block list；空值=[] fail-closed） | **仅 PM 路径的 research** |
| task.md `<!-- mw-write-surface: v1 -->` 契约段 | `ui-bridge.ts:1807 applyWriteSurfaceContract` | `worker-mode.ts:355 writeSurfaceMarkerState`（只查标记结构，不解析内容） | 否（散文三行） | 仅 PM writeless 角色 |
| card extras `## 写入允许面` / `## 写入禁止面` | card 作者 | `typeExtrasMissing`（`shared/dispatch-card.ts:251-252`）**只判是否声明**；conductor 把整段当 `extras` 原样注入（`dispatch.py:480-533`），不解析 glob | 否（正文散文） | 两条通道（conductor 经 `dispatch_card` extras） |
| gate frontmatter `write_scope`（JSON list） | xkey 流程 | `gates.py:291`、`gates.py:790`、`conductor.py:6518`（blast-radius 子集校验） | 是，但语义是 **xkey gate 的变更文件清单**，与 worker 写面**同名不同义** | 与派发无关（命名冲突风险，见 §5） |

### 2.3 "新列 / 新载荷"对现有读者的影响面清单

**方案 A：新增第 10 列（如 `write_face`）**

致命点：两边列宽上限都是 9（`mw_common.py:1739 WORKER_COLS_MAX = 9`、`worker-store.ts:33 WORKER_COLS_MAX = 9`）。
实测 `parse_worker_line("... | packages/**")`（10 列）→ `None`（见 `[VERIFY]`）。因此不做双边同波升级，后果是：

1. **PM 扫描整体中止**：`pm-orchestrator.ts:1003-1013`
   ```ts
   const queue = workerStore.readQueue();
   if (queue.unparsable.length > 0) { opts.onAlarm?.({ kind: "queue-rows-unparsable", ... }); return; }
   ```
   任何 10 列行都会让 `dispatchNewTasks` 整轮不派发（IN-3 之后刻意 fail-closed）。
2. **launcher 丢行不 spawn**：`launcher.py:1776 entries = _parse_workers_file(...)` → `parse_workers_file` 只返回可解析行（`mw_common.py:1829-1842`），10 列行被丢，spawn 循环 `:1806` 永远看不到 → 静默不执行。
3. **conductor 看不到在飞行**：`conductor.py:620 rows = mw_common.parse_workers_file(...)`，丢行 → `_is_in_flight`（`:3539`）判不到 → 可能重复派发。
4. **status/归档写者保槽但不再识别**：`upsert_worker_row`/`update_status`/`archive_stale_entries` 用 `_scan_worker_lines`（未 parse 的行原样保留），不会删，但也不会更新。
5. **必须同波改动**：`mw_common.py:1738-1739`、`:1754-1768`（parse）、`:1845-1864`（serialize）、`worker-store.ts:32-33`、`:105-128`（parse）、`:130-145`（serialize），并新增 parity 测试。任何一侧漏改 = 跨语言"一方写的行另一方读不出"（IN-3 类事故）。
6. **`|` 是分隔符**：载荷里不能再出现裸 `|`（`split("|")` 无转义）；glob 一般不含 `|`，但 JSON 载荷若含 `|` 会错列。
7. **TS 监控/PM 行对象**：`monitor.ts:493`、`ui-bridge.ts:645/716/1100/2519/2530/2537/2545`、`pm-orchestrator.ts:953/1003/1352/1400` 都是行对象字段消费；新增可选字段不破坏它们（读不到就是 undefined），但 `workerOwnerKey`/`workerBelongsToKey`（`worker-store.ts:52-76`）依旧只看 `origin`+`taskPath`。
8. **doctor/只读面**：`mw_common.py:3396`、`mw.py:1920` 同样经 `parse_workers_file`；新列需在其后追加展示才可见。

**方案 B：不改列，写面从 task.md `write_scope:` 头按需解析**

- 影响面小（无列宽/parity 破坏），但 conductor 路径今天不渲染 `write_scope` → 需要先让 `render_task_md` 接受并渲染写面（新增参数，注意 `render_task_md` 的 byte-identity 冻结测试：`dispatch.py:770-790` docstring 明说 `card=None` 必须字节不变）。
- 消费方（判定点）要读文件：每个候选点都要 `pathlib.Path(task_path).read_text()`；launcher 已有 `_read_task_md_fields`（`launcher.py:179`）范式。
- 单一真源、两条通道天然一致（同一 task.md 格式）。

**方案 C：旁路 sidecar（如 `.agenticdoc/_workers.writeface`）**

- 不动队列列与任何现有 reader；但引入"行↔sidecar 同步"这一新的原子性面与新的 stale/lock 语义，且没有既有 lock 保护；不推荐作为首选。
---

## 3. 读面 glob 的既有匹配语义（原文 + 分歧点）

### 3.1 路由层：read_scope / deny_globs

`worker/read-scope.ts:84-128`：

```ts
const IS_WIN32 = process.platform === "win32";

export function isSameOrUnder(prefix: string, candidate: string): boolean {
	const a = IS_WIN32 ? prefix.toLowerCase() : prefix;
	const c = IS_WIN32 ? candidate.toLowerCase() : candidate;
	return c === a || c.startsWith(`${a}${path.sep}`);
}

export function normalizeForCompare(projectRoot: string, p: string): string {
	const abs = path.resolve(projectRoot, p);
	let cur = abs; const tail: string[] = [];
	for (;;) {
		try { return path.join(fs.realpathSync(cur), ...tail); }
		catch { const parent = path.dirname(cur); if (parent === cur) return abs; tail.unshift(path.basename(cur)); cur = parent; }
	}
}

export function isWithinScope(projectRoot: string, scopeEntries: string[], requestPath: string): boolean {
	const req = normalizeForCompare(projectRoot, requestPath);
	return scopeEntries.some((entry) => isSameOrUnder(normalizeForCompare(projectRoot, entry), req));
}
```

`worker/read-scope.ts:141-160`（deny glob，双基）：

```ts
export function matchedDenyGlob(projectRoot: string, denyGlobs: string[], rawPath: string): string | null {
	if (denyGlobs.length === 0) return null;
	const abs = normalizeForCompare(projectRoot, rawPath);
	const rel = path.relative(projectRoot, abs).replaceAll("\\", "/");
	for (const glob of denyGlobs) {
		if (minimatch(abs, glob) || minimatch(rel, glob)) return glob;
		if (glob.endsWith("/**")) {
			const stripped = glob.slice(0, -3);
			if (stripped !== "" && minimatch(rel, stripped)) return glob;
		}
	}
	return null;
}
```

判定顺序（`read-scope.ts:167-215 checkReadScopeCall`）：deny（deny wins）→ scope containment → file cap → byte cap。

### 3.2 写侧：write_scope（运行期 bash guard，同一语义族）

`worker/worker-mode.ts:1564` `const GLOB_MAGIC_RE = /[*?[\]{}]/;`
`worker/worker-mode.ts:1584-1604`：

```ts
function matchesWriteScopeEntry(config: BashWriteScopeConfig, entry: string, absoluteTarget: string): boolean {
	const normalized = entry.trim();
	if (normalized === "") return false;
	if (GLOB_MAGIC_RE.test(normalized)) {
		const relative = path.relative(config.projectRoot, absoluteTarget).replaceAll("\\", "/");
		const forward = absoluteTarget.replaceAll("\\", "/");
		const glob = normalized.replaceAll("\\", "/");
		if (minimatch(relative, glob) || minimatch(forward, glob)) return true;
		if (glob.endsWith("/**")) {
			const stripped = glob.slice(0, -3);
			if (stripped !== "" && (minimatch(relative, stripped) || minimatch(forward, stripped))) return true;
		}
		return false;
	}
	return isSameOrUnder(normalizeForCompare(config.projectRoot, normalized), absoluteTarget);
}
```

`checkBashWriteScopeTarget`（`worker-mode.ts:1606-1666`）判定链：deny 绝对优先 → taskDir/evidence 默认面 → 声明 `write_scope` 交集。

解析原文 `worker-mode.ts:440-465`：`write_scope:` 一行逗号形式（`a, b`）或 YAML block list；空值 = `[]`（fail-closed）；缺头 = `undefined`（默认面）。

### 3.3 实测 minimatch 语义（minimatch 10.2.5）

| 输入 | glob | 结果 | 说明 |
|---|---|---|---|
| `a/b/c.ts` | `a/**` | true | `**` 跨段 |
| `a` | `a/**` | **false** | `a/**` 不含 `a` 本身（两处代码都为此加 trailing `/**` 特例） |
| `A/B/C.TS` | `a/b/c.ts` | **false** | 默认**大小写敏感**（无 `nocase`） |
| `H:\git\x\a.ts`（单反斜杠） | `**/*.ts` | true | minimatch v10 默认把 `\` 当分隔符 |
| `src\a.ts` | `src/*.ts` | true | 同上 |
| `A/B` | `a/b`（`{nocase:true}`） | true | 只有显式 nocase 才不敏感 |

### 3.4 "写面 glob 交集"能否复用同一语义 —— 分歧点

既有算子全部是 **"具体路径 ∈ 集合"**，没有 **"集合 A ∩ 集合 B ≠ ∅"**。可复用 minimatch 做单 glob 与单 root 的匹配，但判定重叠必须新增算子，且必须对齐以下分歧：

| # | 分歧 | 既有读面行为 | 写面交集必须额外定义 |
|---|---|---|---|
| D-1 | **大小写** | glob 匹配大小写敏感（minimatch 默认）；但 `isSameOrUnder` 在 win32 `toLowerCase()`。同一入口两种敏感度 | 交集算子在 win32 必须统一：按 lower 归一后再比，否则 `packages/Foo/**` 与 `packages/foo/x.ts` 会被判"不重叠" |
| D-2 | **`a/**` 不含 `a`** | 靠 trailing `/**` 特例补丁（`read-scope.ts:151`、`worker-mode.ts:1592`） | 交集算子必须实现同一特例，否则 `a/**` vs `a` 会漏判 |
| D-3 | **分隔符/基** | 双基：绝对路径原样 + root 相对 `.replaceAll("\\","/")`；匹配"任一命中即命中" | 交集必须**同一基**上算（两边都 root 相对，或都绝对）；混基会产生假阴性 |
| D-4 | **锚定根** | read_scope 在 dual/partition 模式被 `_expand_read_scope`（`dispatch.py:880-921`）换成绝对 game/partition/control 根；single 模式保持相对按 worker cwd 解析 | 写面声明必须带根模式信息（single/dual/partition + root 路径），否则两 worker 的"相对"含义不同，无法比 |
| D-5 | **realpath vs 词法** | containment 走 `normalizeForCompare`（`realpathSync` + 不存在尾段挂到最深存在祖先） | 交集算子只能对**模式**做词法归一（glob 不能 realpath）；因此 runtime 真实路径与词法预判可能分歧（symlink/junction） |
| D-6 | **allow vs deny 两类集** | read_scope 是 allow containment；deny_globs 是 deny 防火墙（双基 minimatch） | 写面今天只有 allow（`write_scope`）；交集只算 allow×allow。若将来加 deny，需先算 allow 交再减 deny，顺序不能反 |
| D-7 | **`|` 分隔符** | 队列行 split("|")；glob 里一般无 `|` | 若写面进队列列，载荷不得含裸 `|` |
---

## 4. 插入点候选（>=3）

**共同前提**：判定需要"在飞集合含各自写面"。今天写面不在队列行（§2），所以每个候选都先要有一个写面载荷来源（方案 A 列 / 方案 B task.md 解析 / 方案 C sidecar）。

### 候选 C1：conductor `dispatch.dispatch` 写 task.md 之前（`dispatch.py:964`，插入点约 `:1113` 之前）

- **在飞集合**：函数本身**看不到**。调用者手里有 tick 起点快照 `rows`（`conductor.py:620`），但：
  - `dispatch.dispatch` 签名不含 `rows`（`dispatch.py:964-977`）；
  - 即使传入 `rows`，它是本 tick 起始快照，同一 tick 内先派的 key（`max_parallel_keys` 默认 2，`conductor.py:744`）不会出现在里面；
  - PM 在两次 tick 之间派的行也不在。
  - 结论：必须**当场重新 `parse_workers_file`**（可复用 `mw_common.parse_workers_queue` 以感知 unparsable）。
- **并发安全**：需持 `.mw/workers.lock`。今天 `dispatch()` 只在写行时取锁（`dispatch.py:1156 acquire_lock` → `:1184 release`），检查若放在 `:1130 task_dir.mkdir` 之前就**不在锁内**，与 PM/另一 conductor 构成 check-then-act 竞态。若把检查挪进锁内（`:1156` 之后），则 task.md 已写（`:1132`）→ 拒绝会留下孤儿 task.md（模块 docstring 说孤儿靠 reconcile 重插，语义会变成"拒绝不了"）。要真正原子，需把"读队列+判定+写 task.md+写行"整体放进锁，或先锁→判定→写。
- **首个失败模式**：写面缺失的 fail-closed（spec §2.3/AC-003）会让**所有 13 个调用点**同时拒绝——今天 conductor 渲染的 task.md 里 `write_scope` 命中为 0（`render_task_md` 不产该头），即 conductor 全线停摆。次生失败：同一 tick 快照导致的假阴性（两个重叠 worker 都派出）。
- **优点**：单点覆盖 13 个调用点；能拿到 `task_type` 与 `card_path`，与 `implementation-gate` 的 write-intent 判定同层。

### 候选 C2：PM `dispatch_worker` / `/worker` 写 task.md 之前（`ui-bridge.ts:2424` / `:2918` 之前）

- **在飞集合**：可当场 `workerStore.readQueue()`（`worker-store.ts:168`）拿全量行；写面要么从每行 `taskPath` 对应的 task.md 解析（方案 B），要么从新列读（方案 A）。
- **并发安全**：需持 `.mw/workers.lock`。今天 check（`readQueue`）与 act（`dispatchTask`→`upsert`）是两次独立取锁；两个 PM 窗口并发派发可同时通过检查（典型 TOCTOU）。要原子需自持锁做 RMW，或把判定下沉到 `WorkerStore.upsert`。
- **首个失败模式**：fail-closed 直接卡住 PM 手工派发（历史上 `write_scope` 只在 research 上有，coding 全缺）→ 手工通道全拒。次生：跨窗口竞态导致重叠双派。
- **优点**：PM 是最主要的并发派发来源（spec §1.3.2 一次派 6 个），在源头拒绝可给 PM 最可读的理由（`overlap-with:<task_key>`）；且能复用 `renderDefaultWriteScope`（`ui-bridge.ts:1779`）与 `judgeWriteIntent`（`:1741`）的既有写面上下文。

### 候选 C3：TS 队列写咽喉 `dispatchTask`/`WorkerStore.upsert`（`task-dispatcher.ts:288`、`worker-store.ts:190`）

- **在飞集合**：`upsert` 在**同一把锁内**已经做整文件 RMW（`readRawLines()` → 改 → tmp+rename），是唯一"同时看见全量队列且独占"的点。
- **并发安全**：天然在 `.mw/workers.lock` 内（`file-lock.ts` via `acquireLock`），无需额外锁；这是**最强**的原子性候选。
- **首个失败模式**：`dispatchTask` 返回 `Promise<void>`（`task-dispatcher.ts:288-300`），`upsert` 的契约是"写行"；让它们拒绝需要改返回类型 + 三个调用点（`:2203` 工具、`:2764` /worker、`pm-orchestrator.ts:925`）的 error 处理，否则拒绝只能表现为抛异常。orphan 修复（P3）也会开始拒绝，可能改变 T-19/T-24 的既有语义。
- **优点**：覆盖全部 TS 写者（含 orphan 修复），锁语义现成。**缺点**：只覆盖 PM 通道，conductor（Python）仍要一个等价的 Python 内点；且 `upsert` 是通用存储方法，写面判定侵入其职责边界。

### 候选 C4：launcher spawn 前（`launcher.py:1707 _poll_once`，spawn 循环 `:1806-1858`，插入点约 `:1831` envelope gate 同层）

- **在飞集合**：`running_procs`（本 launcher 进程已 spawn）+ `pending_queue`（`:1856` 因 cap 排队）+ 本轮 `entries`（`:1776` 新读）。这是**最接近真实并发**的视图（真正的同刻多写者只会是已 spawn 的进程）。
- **并发安全**：`_poll_once` 单线程循环，但队列读取未持 `.mw/workers.lock`（只有 `_update_status`/`archive_stale_entries` 各自短持锁）；多 launcher 进程时 `running_procs` 只见自己 → 跨 launcher 会漏判。需在判定处持锁或依赖"每项目单 launcher"的前提（存在 launcher beat，但未见互斥强制）。
- **首个失败模式**：它的拒绝路径是"落 failed 行"（与 envelope gate `:1831-1853` 同构），即拒绝=任务失败而非可重派；且此时 task.md 与队列行**已存在**，refusal 只能是事后审计，不能做到 AC-001 的"零副作用"。第二个失败模式：只看 `running_procs` 会漏掉"已 spawn 但本进程重启前"的进程。
- **优点**：是既有 envelope 服务层判据（G-3）的天然邻居，launcher 已解析 task.md（`_read_task_md_fields`，`launcher.py:179`），读 `write_scope` 成本低；能兜住"任何绕过两条通道手写队列行"的情况。

### 候选 C5（补充）：跨语言共享判定语料的"语义单源"层

不是插入位置，而是上面各点的实现约束：Python 侧（供 C1）与 TS 侧（供 C2/C3/C4）各一份判定实现，必须共享一份 parity 语料（同写面输入 → 同 overlap 结论），对齐 P-021。C4 的 Python 实现可与 C1 复用同一函数；C2/C3 的 TS 实现可与 C4 的 TS 侧（monitor 已有 TS 侧判定能力）复用。

### 4.1 候选对比

| 候选 | 覆盖通道 | 在飞行集合质量 | 需 workers.lock | 拒绝是否零副作用 | 首要失败模式 |
|---|---|---|---|---|---|
| C1 conductor `dispatch` 前 | conductor 13 点 | 差（需重读；tick 快照不可用） | 是（今天不持） | 可做到（挪到 mkdir 前） | fail-closed 令 conductor 全线停摆 |
| C2 PM 入口前 | PM 工具+/worker+orphan(部分) | 好（可重读全量） | 是（今天不持） | 可做到 | fail-closed 卡死手工通道；跨窗口 TOCTOU |
| C3 TS `dispatchTask`/`upsert` | 全部 TS 写者 | 最好（锁内全量 RMW） | 已持有 | 可做到（拒绝即不写） | 改 `void` 契约 + 影响 orphan 语义 |
| C4 launcher spawn 前 | 一切入队者（最后一道） | 最好（running_procs+pending+entries） | 需要（今天不持） | **否**（行/文件已写，只能落 failed） | 拒绝=failed 不可重派；多 launcher 漏判 |

---

## 5. 风险、残留与未验证

- **命名冲突（实测）**：`write_scope` 已有两个不相关含义——（a）task.md 的 worker 写面头（`worker-mode.ts:322/440`），（b）xkey gate frontmatter 的 JSON list（`gates.py:291/790`、`conductor.py:6518`，语义是"允许变更的文件清单"）。新写面字段若继续叫 `write_scope` 会把两者混淆；spec 待确认项"是否复用既有 `write_scope` 名"需要这条实证。
- **未验证：launcher 多进程是否被强制互斥。** 只看到 `launcher_beat_write`（`launcher.py:1719`）这一 liveness 写，未定位到"第二个 launcher 拒绝启动"的强制点。未找到明确互斥断言（`rg -n "already running|launcher.*instance|launcher.*lock" packages/multi-workers/launcher.py packages/multi-workers/mw.py` 无互斥结论；未覆盖面，不作结论）。
- **未验证：`dispatch.py:1130 task_dir.mkdir` 之后、`:1156 acquire_lock` 之前这段窗口被中止的孤儿行 reconcile 细节**，只从模块 docstring 得知"孤儿由 per-tick reconcile 重插"；是否与写面拒绝交互未验证。
- **未验证：写面 glob×glob 交集的具体算法可行性**（本 RQ 只做可行性方向判断与分歧点枚举，未写/未跑交集原型）。
- **未验证：`implementation-gate`/`change-ledger` 是否会在运行期捕获跨 worker 同文件写**（属 RQ-W3 范围，本文件只记录"派发层没有"这一事实）。

## 6. 未覆盖面声明

- 未读 `dist/` 构建产物；结论均基于 `src/`/`packages/*/` 源码（dist 可能滞后但非判据来源）。
- 未运行任何生产代码路径、未派发 worker、未改任何生产文件；唯一写面是本证据文件。
- 未覆盖 pi 核心（`packages/agent`、`packages/coding-agent/src/core`）中与队列无关的部分。
- 未覆盖 worktree 系列（`worktree_*.py`、`tree_watch.py`）与写面判定的交互。
- 未覆盖 `mw.py` doctor 的完整只读面（仅记录了它经 `parse_workers_file` 读队列，未逐字段核对新列展示需求）。

---

[VERIFY]
- queue file `.agenticdoc/_workers.parallel`: rows=419, unparsable=0, version=1, in-flight(running)=7, distinct owner keys=35; column widths `8 cols x 361`, `9 cols x 58`, no 7/10-col rows; status `{done:385, needs-clarification:24, failed:3, running:7}`; origin `{(none):361, manual:58}`
- `parse_worker_line`: 9-col line parses (origin=conductor); 10-col line (appended `packages/**`) -> `None`
- conductor `dispatch.dispatch(` call sites: 13 at `:1196,1605,1643,1679,1788,2369,2419,2454,2486,2526,2571,2579,5098`
- column-count constants: `mw_common.py:1739 WORKER_COLS_MAX = 9`; `worker-store.ts:33 const WORKER_COLS_MAX = 9`
- minimatch version 10.2.5; `minimatch("A/B/C.TS","a/b/c.ts")=false`; `minimatch("a","a/**")=false`; `minimatch("A/B","a/b",{nocase:true})=true`
- `write_scope` render hits: 0 in `dispatch.py` (render_task_md has no such parameter); PM `renderDefaultWriteScope` calls only `ui-bridge.ts:2431` and `:2925` (both `writelessRole && isShellRole`)