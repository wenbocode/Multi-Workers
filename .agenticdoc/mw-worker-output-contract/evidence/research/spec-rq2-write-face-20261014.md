# RQ2 证据：写面分层与 worker_file 放宽的全部改动点

- Key: mw-worker-output-contract
- 任务: T-RQ2-write-face / worker `woc-rq2-write-face`（type: research，只读研究）
- 唯一证据文件: `.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq2-write-face-20261014.md`
- 边界：未修改仓库任何文件（`git status --short` 下本 RQ 涉及的源/测试文件均为 clean）；未跑 npm install/ci、git checkout/reset/clean/stash、npm run build、全量 ./test.sh
- 起始坐标复核：全部命中（`worker-file-tool.ts:42/63/82`、`worker-mode.ts:723/1604-1660`）

## 结论

1. 角色工具集的唯一决定处是 `worker-mode.ts:73-106` 的 `TOOL_ALLOWLISTS`（11 键，实测其中 5 键 writeless）；运行时由 `activeToolsForType`（:145-148）为 writeless 角色追加 `worker_file`，在 `worker-mode.ts:2131-2134` 注册、在 `before_agent_start`（:2154-2156）经 `rag/tools.ts:402/406` 落到 `pi.setActiveTools`（`core/agent-session.ts:928-938`）。`.mw/dispatch.yml` 只声明 `models:`（role→model 值），不声明任何工具、也没有任何工具入口。
2. `worker_file` 是纯 basename 通道：`WORKER_FILE_NAME_RE`（`worker-file-tool.ts:42`）→ `isAllowedWorkerFile`（:48-50）→ `writeWorkerFile`（:56-84，落盘路径 `path.join(taskDir, file)` 在 :73）→ 成功事件 `appendWriteFileEvent`（:82）→ 拒绝文案 `file name not allowed`（:63）→ `execute` 抛错（:117）。`taskDir` 来自 `PI_WORKER_TASK` 的 `path.dirname`（`worker-mode.ts:1896/1918`，注册点用 :2116 的同值）。
3. 壳层写面 `checkBashWriteScopeTarget`（`worker-mode.ts:1606-1662`）判定顺序为 **deny 表（:1568-1582，6 条）→ 默认面 taskDir + `<key>/evidence`（:1626/1638-1646）→ `write_scope:` 收窄（:1648-1661）**；`allow-unknown` 是「目标不可静态判定」的 fail-open 档（:1613-1621），不是 block 规则；trace 格式见 :1695-1714 / :1718-1732。
4. 核心改动点：**worker_file 通道 16 处（A1-A16）+ 派发期 PM 侧 6 处（B1-B6）+ 派生 bundle 1 处（D1）+ 测试 11 处（C1-C11）**。其中 B1 是端到端必需项而非可选项：`ui-bridge.ts:1707-1722` 的派发期 `judgeWriteTarget` 同样只认 taskDir + basename，**今天就会把 review/verifier 卡里写本 key `evidence/**` 的订单判为不可满足**（已实测复现，见 §5.1-（5））。
5. `Tool write not found` 的文案生成处是 **pi 核心 `packages/agent/src/agent-loop.ts:611`**；扩展侧无法改写模型可见文本（`tool_result` 钩子只由 `finalizeExecutedToolCall` 触发，而 not-found 走 `kind:"immediate"` 分支不经过它）。因此 AC-007 必须先钉死「文案」指哪一层（§6.4 给出三个候选及其代价）。
6. 现有测试实测：`agent-team-loop-worker-file-tool.test.ts` 7 通过 / 2 失败（**改动前既存**：:82 的 `[WRITE_FILE]` 会在 taskDir 生成 `trace.log`，而 :177/:285 的目录快照未计入）；`mwds-t02-write-intent.test.ts` 38/39（1 例失败正是 P2 的反向证据：`wjg-qg-evidence-closure` 声明写本 key 的 evidence 被判越界）。两者均为 HEAD 状态，非本 RQ 引入。

## 证据

> 格式映射：派发卡的「0 结论先行」= 上面的 `## 结论`；`## 1…N` 逐问作答 = 本节 §1-§6；「未找到清单 / 未覆盖面声明」= 本节末两小节；`output.md` 要求的四段 = `## 结论` / `## 证据` / `## 残留与未验证` / `## 上下文来源`。

### §1 角色工具集的决定处

**1.1 唯一工具表 —— `worker-mode.ts:73-76`**（共 11 键，`fallback` 是内部桶）

```
73: const TOOL_ALLOWLISTS: Record<string, string[]> = {
74: 	coding: ["read", "write", "edit", "bash", "find", "grep", "ls"],
75: 	review: ["read", "find", "grep", "ls"],
76: 	research: ["read", "find", "grep", "ls", "bash"],
```

其余键：`roadmap-writer`(write,no-bash) / `phase-writer`(write,bash) / `verifier`(writeless) / `reviewer`(writeless) / `repair`(write,bash) / `rag-research`(writeless,11 键) / `vision`(write,bash) / `fallback`(write,bash)。

实测（命令与输出见「测量」）：

```
coding writer shell 7 | review writeless no-bash 4 | research writeless shell 5
roadmap-writer writer no-bash 6 | phase-writer writer shell 7 | verifier writeless no-bash 4
reviewer writeless no-bash 4 | repair writer shell 7 | rag-research writeless no-bash 11
vision writer shell 7 | fallback writer shell 7
keys= 11 writeless= 5 ['rag-research', 'research', 'review', 'reviewer', 'verifier']
```

**1.2 追加与角色判定**

- `worker-mode.ts:136-138` `toolsForType`（`TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback ?? []`）
- `worker-mode.ts:145-148` `activeToolsForType`：`return base.includes("write") ? base : [...base, WORKER_FILE_TOOL];` ← **worker_file 只在这里进入工具面**
- `worker-mode.ts:151-153` `isShellRole`；`:158-161` `isWritelessRole`（`!tools.includes("write") && !tools.includes("edit")`）
- `worker-mode.ts:112-114` `isRegisteredType`（`taskType !== "fallback" && taskType in TOOL_ALLOWLISTS`）→ conductor 派发的 fail-closed 门 `:652-671 dispatchRefusal`
- `worker-mode.ts:258-262` `READ_TOOLS` / `WRITE_TOOLS`（**`worker_file` 不在任一集合内**，见 A13）

**1.3 注册与运行时应用**

- 注册门 `worker-mode.ts:2131-2134`：

```
2131: 	const hasWriteTools = toolsForType(meta.type).includes("write");
2132: 	if (!hasWriteTools) {
2133: 		registerWorkerFileTool(pi, workerTaskDir);
2134: 	}
```

（注释 :2127-2130 声明这是「结构性镜像 `registerRagTools` 的 disabled→skip」，且刻意放在 RAG try/catch 之外）

- 运行时应用 `worker-mode.ts:2148-2156` → `rag/tools.ts:400-407`：

```
402: 		pi.setActiveTools(activeToolsForType(type));
406: 	pi.setActiveTools([...new Set([...activeToolsForType(type), ...ragToolNamesForType(rt, type)])]);
```

- 落地点 `core/agent-session.ts:928-938` `setActiveToolsByName`（注释：「Only tools in the registry can be enabled. Unknown tool names are ignored.」）；接线 `:2400 setActiveTools: (toolNames) => this.setActiveToolsByName(toolNames)`；API 声明 `core/extensions/types.ts:1339-1340`

**1.4 `.mw/dispatch.yml` 只声明了什么**

- Python 读取器 `mw_common.py:224-256`：只取 `data.get("models", {})`；role 必须 ∈ `DISPATCH_ROLES = ("main", "coding", "review", "research", "vision")`（`:143`）。文件里任何非 `models` 顶层键被静默忽略；没有工具字段。
- TS 读取器 `shared/dispatch-models.ts::readRoleModel`：手写解析，只认 `models:` 块（含 BOM 处理），用途是选模型，不是选工具。
- 实测本仓 `.mw/dispatch.yml` 全文 = `models:` 下 4 行（coding/main/research/review → `timi/*`），无第二类键。
- 启动器只注入 `PI_WORKER_TASK`（`launcher.py:290/308/317/340/368`），命令行无任何工具参数；`launcher.py:234-235` 注释亦声明工具白名单是 pi worker-mode 的能力。

**1.5 Python 侧并存的工具声明（运行时不用，但被 parity 锁）**

- `autopilot/dispatch.py:72` `REGISTRY`（7 个 conductor 类型）、`:147-150 tool_set`、`:153-155 registry_snapshot`
- 锁：`test_autopilot_l0.py:233-260`（7 键 order-exact 对比 TS 源码文本）、`test_mwpp_collection_parity.py:66-90`（11 键全表快照）→ **不得**把 `worker_file` 写进 `TOOL_ALLOWLISTS`（见 C10）

**1.6 `worker_file` 对哪些 type 注册**

由 1.2+1.3 直接推出，实测 5/11：`review`、`verifier`、`reviewer`、`research`、`rag-research`。其中只有 `research` 同时是 shell 角色（受 AC-005b 壳层守卫）；`rag-research` 既无 shell 也无 write，唯一写通道就是 worker_file。

### §2 worker_file 的完整实现与调用点

**2.1 注册与参数 —— `worker-file-tool.ts:87-124`**

```
 89: 		name: WORKER_FILE_TOOL,            // = "worker_file" (:31)
 91: 		description:
 92: 			"Write a short text file into this worker's own task directory. Only progress.md, report.md " +
 93: 			"and report-<slug>.md are accepted as basenames (no directories, no separators). Use " +
 95: 			"capped at 64 KiB of UTF-8 bytes; a rejected call writes nothing.",
 96: 		promptGuidelines: [
 97: 			"Use worker_file to persist progress notes and reports when the task role has no write/edit tool; " +
 98: 				"the file must be progress.md, report.md or report-<slug>.md (basename only, slug up to 41 chars).",
103: 				file: Type.String({
104: 					pattern: WORKER_FILE_NAME_RE.source,
105: 					description: "Basename only: progress.md | report.md | report-<slug>.md",
106: 				}),
108: 				mode: Type.Optional(Type.Union([Type.Literal("append"), Type.Literal("write")])),
110: 			{ additionalProperties: false },
```

**2.2 校验、写盘、事件 —— `worker-file-tool.ts:42-84`**

```
 42: export const WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/;
 48: export function isAllowedWorkerFile(name: string): boolean {
 49: 	return WORKER_FILE_NAME_RE.test(name);
 62: 	if (!isAllowedWorkerFile(file)) {
 63: 		return { ok: false, reason: `file name not allowed: ${JSON.stringify(file)}` };
 65: 	const bytes = Buffer.byteLength(content, "utf8");
 66: 	if (bytes > WORKER_FILE_MAX_BYTES) {          // 64 * 1024, :34
 72: 	fs.mkdirSync(taskDir, { recursive: true });
 73: 	const target = path.join(taskDir, file);
 74: 	if (mode === "append") {
 75: 		fs.appendFileSync(target, content, "utf8");
 77: 		fs.writeFileSync(target, content, "utf8");
 82: 	appendWriteFileEvent(path.join(taskDir, "trace.log"), repoRelativePath(target));
 83: 	return { ok: true, path: target, bytes };
```

文件头注释 :6-10 明确「The tool takes a *basename* only: no path parsing exists, so … every path variant (`../x.md`, `a/b.md`, `C:\abs\x.md`, `\\unc\share\x.md`) are rejected by one regex before any `fs.*` call. Rejection is fail-closed」。`WORKER_FILE_MAX_BYTES` 上限与 `mode` 默认值语义见 :18-21。

**2.3 失败形态 —— `worker-file-tool.ts:112-123`**

```
115: 			const r = writeWorkerFile(taskDir, params.file, params.content, mode);
116: 			if (!r.ok) {
117: 				throw new Error(`worker_file rejected: ${r.reason}`);
118: 			}
120: 				content: [{ type: "text", text: `wrote ${r.bytes} bytes to ${r.path} (${mode})` }],
```

抛错（而不是返回 `{isError}`）是 `[TOOL_ERR]` 能出现的前提，注释 :12-16 已声明。

**2.4 taskDir 从哪来**

- `worker-mode.ts:1893` `const taskPathEnv = process.env.PI_WORKER_TASK;` → `:1896 path.resolve(...)`
- `worker-mode.ts:1918` `const taskDir = path.dirname(taskPath);`
- `worker-mode.ts:2116` `const workerTaskDir = path.dirname(taskPath);`（传给注册 :2133）
- `worker-mode.ts:508-510`（`parseTaskMd` 内）：`agenticdocRoot = path.dirname(path.dirname(taskPath))`、`taskKey = path.basename(path.dirname(taskPath))`、`trueAgenticdocRoot = path.dirname(path.dirname(agenticdocRoot))`
- 因此 `taskDir = <project>/.agenticdoc/<ownerKey>/workers/<taskKey>`，证据面 = `path.join(path.dirname(meta.agenticdocRoot), "evidence")`（与壳层 :2207 的 `keyDir: path.dirname(meta.agenticdocRoot)` 同式）

**2.5 调用点清单（grep 实测）**

```
packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts:87  (定义)
packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2133    (唯一生产调用)
packages/coding-agent/test/extensions/agent-team-loop-worker-file-tool.test.ts:93  (测试)
packages/multi-workers/dist/extensions/agent-team-loop.js:16848 / :19108            (打包产物)
```

`worker-file-tool.ts` 被 3 处 import：`worker-mode.ts:69`、`pm/ui-bridge.ts:65`、`shared/deliverable-evidence.ts:43`（后两处用 `WORKER_FILE_NAME_RE` 做 basename 判定：`ui-bridge.ts:1715`、`deliverable-evidence.ts:113`）。

### §3 壳层写面全貌

**3.1 配置形态 —— `worker-mode.ts:745-759`**

```
748: 	/** Own task dir (`.agenticdoc/<key>/workers/<taskKey>`), absolute. */
749: 	taskDir: string;
750: 	/** Own key dir (`.agenticdoc/<key>`), absolute. */
753: 	keyDir: string;
755: 	trueRoot: string;
756: 	/** `write_scope:` entries (project-root relative): undefined = header
757: 	 * absent (the default surface), [] = present-but-blank (fail-closed). */
758: 	writeScope: string[] | undefined;
```

构造点 `worker-mode.ts:2202-2211`（仅在 `isShellRole(meta.type) && isWritelessRole(meta.type)` 为真时存在；`projectRoot: process.cwd()`）。

**3.2 判定顺序 —— `worker-mode.ts:1606-1662`**

```
1606: export function checkBashWriteScopeTarget(
1613: 	if (!verbatim) {                     // (0) 不可静态判定 → allow-unknown（fail-open）
1621: 			rule: "allow-unknown", detail: "target-not-statically-determinable", risk,
1624: 	const allowedLabel = `${config.taskDir} or ${evidenceDir}`;
1626: 	const denied = bashWriteDenyReason(config, target);
1627: 	if (denied !== null) { … rule: "deny", detail: `denied:${denied}` … }        // (1) deny 绝对优先
1638: 	if (!isSameOrUnder(config.taskDir, target) && !isSameOrUnder(evidenceDir, target)) {
1641: 			detail: "outside-allowed-surface", rule: "scope",                        // (2) 默认面之外
1648: 		config.writeScope !== undefined &&
1649: 		!config.writeScope.some((entry) => matchesWriteScopeEntry(config, entry, target))
1655: 			detail: "outside-declared-write-scope", rule: "write-scope",             // (3) 声明收窄
1662: 	return { allowed: true, target: rawTarget };
```

`evidenceDir = path.join(config.keyDir, "evidence")`（:1625）。

**3.3 deny 表 6 条 —— `worker-mode.ts:1568-1582`**

```
1570: 	if (samePath(target, path.join(config.keyDir, "pm-state.md"))) return "pm-state.md";
1571: 	if (isSameOrUnder(workersDir, target)) { … if (firstSegment.startsWith("_workers")) return "workers/_workers*"; }
1574: 	if (samePath(target, path.join(config.trueRoot, "_index.parallel"))) return "_index.parallel";
1575: 	if (isSameOrUnder(config.trueRoot, target) && !isSameOrUnder(config.keyDir, target)) {
1576: 		return "other key dir / .agenticdoc root";
1578: 	if (isSameOrUnder(path.join(config.projectRoot, "packages"), target)) return "packages/**";
1579: 	if (isSameOrUnder(path.join(config.projectRoot, ".git"), target)) return ".git/**";
```

注释 :1566-1567：「The deny list is checked first and can never be widened by a `write_scope:` header.」

**3.4 `write_scope:` 收窄 —— `worker-mode.ts:1584-1599`**

```
1584: function matchesWriteScopeEntry(config, entry, absoluteTarget): boolean {
1586: 	if (normalized === "") return false;
1587: 	if (GLOB_MAGIC_RE.test(normalized)) {        // 支持 glob（minimatch 双基准 + 尾部 /** 剥离）
1592: 	return isSameOrUnder(normalizeForCompare(config.projectRoot, normalized), absoluteTarget);
```

**3.5 `allow-unknown` 的语义与条件**

- 条件：`verbatim === false`（词含实时展开 `$`、反引号、`*?[{`、未引用前导 `~`）—— 由词法器 `:791-862` 计算并随候选传出。
- 语义：**allowed=true + rule="allow-unknown"**，不阻断（`worker-mode.ts:719-726` 注释：「Tier P1 (design DD-03): the failure mode is a MISS — an exotic write slips through — never a false block」）。
- 残留风险标记：basename 为 `pm-state.md` 或以 `_workers` 开头时 `risk: "deny-basename"`（`:1615-1620`）。
- 审计：调用侧 `:2224-2237` 先计数 `writeScopeCounts.allowUnknown += 1`，再写 `[WRITE_SCOPE] … blocked=false rule=allow-unknown …`。

**3.6 `[WRITE_SCOPE]` trace 行格式 —— `worker-mode.ts:1695-1714`**

```
1703: 			`[WRITE_SCOPE] ${r.ts} write-scope blocked=${String(r.blocked)} ${risk}rule=${r.rule} detail=${r.detail} ` +
1704: 				`pattern=${r.pattern} target=${r.target} cmd=${summary}\n`,
```

`risk=` 仅在设定时出现（:1700）。汇总行 `:1718-1732`：`[WRITE_SCOPE_SUMMARY] allow=${allowDetermined} deny=${deny} allow-unknown=${allowUnknown}`（`recordEnd` 处调用，`:2449-2452` 附近）。逃生门行 `:1737-1749`：`[ESCAPE_HATCH] allow_foreign_write=<task_key> target=<path>`。

**3.7 `write_scope:` 任务头的解析处 —— `worker-mode.ts:440-465`（`parseTaskMd` 内）**

```
440: 		if (trimmed.startsWith("write_scope:")) {
441: 			const rest = trimmed.slice("write_scope:".length).trim();
442: 			if (rest) {                                   // 一行逗号形式
443: 				writeScope = rest.split(",").map((item) => item.trim())…
450: 			} else {
451: 				writeScope = [];                          // present-but-blank ⇒ fail-closed
452: 				inWriteScopeList = true;                  // 亦接受 YAML block-list
```

字段声明 `:319-322`（`writeScope?: string[]`），返回 `:529`。

**3.8 生产者 —— `pm/ui-bridge.ts`**

- `:1779-1781 renderDefaultWriteScope`：`` `write_scope: .agenticdoc/${ownerKey}/workers/${taskKey}, .agenticdoc/${ownerKey}/evidence` ``
- 调用点 `:2432`（`dispatch_worker`）与 `:2926`（`/worker`），条件同为 `writelessRole && isShellRole(typeField)` ⇒ **实际只有 research 会拿到 C1 头**（review/verifier/reviewer/rag-research 没有 `write_scope:`，因此只走壳层默认面，而它们多半连 bash 都没有）。
- 写入前合并 `:1827-1831 mergeWriteScope`；字段声明 `:2157-2159`。
- 契约段 `:1784-1801 renderWriteSurfaceContract`；标记常量 `:1394-1395`；幂等套用 `:1807-1815 applyWriteSurfaceContract`。

### §4 改动点清单（可直接转 tasks；只列位置与语义，不写实现）

**A. worker_file 通道（本 RQ 核心，16 项）**

| # | 位置 | 需要做什么（语义） |
|---|---|---|
| A1 | `worker-file-tool.ts:42` | `WORKER_FILE_NAME_RE` 保持 basename-only 语义**不变**（它同时被 :104 schema、`deliverable-evidence.ts:113`、`ui-bridge.ts:1715` 复用）。路径域不得靠扩宽本正则表达，须新增独立常量/函数 |
| A2 | `worker-file-tool.ts:47-50` | `isAllowedWorkerFile` 保持 basename-only；新增路径域解析纯函数（建议 `resolveWorkerFileTarget(ctx, file)`），ctx 含 `taskDir`、`ownerKeyDir`、`projectRoot`、可选 `writeScope`。判定顺序须与壳层同构：绝对/UNC/盘符 → 拒；含 `..` 段 → 拒（先于 containment）；无分隔符 → basename 白名单；否则 → containment 到 `<key>/evidence`；deny 表兜底（deny 优先）。**未定项**：允许的相对基准是 project-root 形式（`.agenticdoc/<key>/evidence/**`，与 `write_scope` 渲染一致）还是 key 相对（`evidence/**`）——须先裁决 |
| A3 | `worker-file-tool.ts:56-61` | `writeWorkerFile` 签名增加证据面入参（ownerKeyDir/evidenceDir 或 ctx 对象） |
| A4 | `worker-file-tool.ts:62-64` | 拒绝文案必须能区分「basename 不在白名单」与「路径越界」两类（AC-006 要求留可辨 trace）；当前只有一种 `file name not allowed: <json>` |
| A5 | `worker-file-tool.ts:72` | `mkdirSync` 目标改为「解析后目标的父目录」（evidence 下的子目录如 `research/` 需要创建） |
| A6 | `worker-file-tool.ts:73` | `path.join(taskDir, file)` → 解析器给出的 target |
| A7 | `worker-file-tool.ts:82` | trace 仍写 `taskDir/trace.log`（不变）；是否在事件里区分写入域见 A16 |
| A8 | `worker-file-tool.ts:87` | `registerWorkerFileTool(pi, taskDir)` 增参；调用点 `worker-mode.ts:2133` 同步 |
| A9 | `worker-file-tool.ts:91-95` | description（AC-007 第二处）必须同时说明两个域 |
| A10 | `worker-file-tool.ts:96-100` | promptGuidelines 同步（现文写死「basename only」，会与放宽后的 schema 冲突） |
| A11 | `worker-file-tool.ts:103-106` | `file` 的 schema `pattern` 改为「basename 或 evidence 相对路径」的合并表达式；需新增导出常量并同步 `worker-file-tool.test.ts:327` 的单源断言；`:105` 描述同步 |
| A12 | `worker-mode.ts:2131-2134` | 计算并传入 `keyDir = path.dirname(meta.agenticdocRoot)`、`evidenceDir = path.join(keyDir, "evidence")`（与 :2207 同式）；（可选）传 `meta.writeScope` |
| A13 | `worker-mode.ts:262` + `:2334-2364` + `:2352-2389` | `worker_file` 目前既不在 `WRITE_TOOLS` 也不在 `pendingWriteTargets`，成功写只靠工具自身 :82 的事件；放宽后须决定是否把该通道并入 writeCount/writeTargets（AC-009/S5 的 writeless 判据要读「最近写事件」）。至少不得回归 |
| A14 | `worker-mode.ts:1568-1582` / `ui-bridge.ts:1643-1668` | deny 表已有两份；新增 worker_file 守卫会成为第三份 → 抽到 `shared/` 纯模块。**依赖方向约束**：`worker-file-tool.ts` 被 `worker-mode.ts:69`/`ui-bridge.ts:65`/`deliverable-evidence.ts:43` import，共享模块不得反向 import 这三者 |
| A15 | `worker-mode.ts:1648-1661` + `:1584-1599` | 裁决 `write_scope:` 是否约束 worker_file。若否，声明收窄的 write_scope 会被宽通道绕过（违反 §2.3 意图）；若是，需复用/抽出 `matchesWriteScopeEntry` |
| A16 | `worker-mode.ts:2389-2390` + `output-writer.ts:440-446` | 拒绝路径的 trace 二选一：沿用 `[TOOL_ERR] worker_file <reason>`（则 A4 文案必须自解释），或新增 `[WRITE_SCOPE]` 风格审计行（复用 :1695-1714 格式，加 tool/domain 字段） |

**B. 派发期 PM 侧（端到端必需，6 项）**

| # | 位置 | 需要做什么 |
|---|---|---|
| B1 | `ui-bridge.ts:1707-1722 judgeWriteTarget` | 在 :1713（own taskDir）之后、basename 通道之前加证据面一步：`ctx.keyDir` 存在且 `isSameOrUnder(path.join(ctx.keyDir,"evidence"), target)` → `{allowed:true, shape}`。**不加则 review/verifier 卡声明写本 key evidence 会在派发期被拒**（§5.1-(5) 实测） |
| B2 | `ui-bridge.ts:1564-1569 PmWriteSurfaceCtx` | 无需新字段（`keyDir` 已在）；确认派发路径传入（`:2352-2358` 已传 keyDir/trueRoot） |
| B3 | `ui-bridge.ts:1766-1775 writeIntentRefusal` | Fix 文本第 1 条（:1771）只给 `report.md`，需加入 evidence 形式 |
| B4 | `ui-bridge.ts:2432` + `:2926` | `writeScope` 渲染条件 `writelessRole && isShellRole(typeField)`：若 A15 采用「write_scope 约束 worker_file」，非 shell 的 writeless 角色也需要 C1 头 |
| B5 | `ui-bridge.ts:1784-1801 renderWriteSurfaceContract` | :1787-1788「允许写」需加入 evidence 面；:1789-1790「不得写」需明确「其他 key 的 evidence 仍禁」 |
| B6 | `ui-bridge.ts:1698-1706` | 判定顺序注释随 B1 同步（该注释是 AC-003/AC-004 的语义文档） |

**C. 测试（11 项）**

| # | 位置 | 动作 |
|---|---|---|
| C1 | `test/extensions/agent-team-loop-worker-file-tool.test.ts:177`、`:285` | 目录快照必须把 `trace.log` 计入（**改动前既存失败 2 例**，实测 7/9） |
| C2 | 同文件 `:194-206` | 12 例 `REJECTED_FILES` 必须保持 12/12 拒绝（AC-006「basename 白名单既有用例仍通过」的背书集） |
| C3 | 同文件 `:327` | schema 单源断言（`pattern === WORKER_FILE_NAME_RE.source`）随 A11 重构为「basename 正则仍在合并表达式中」的可证形式 |
| C4 | `test/suite/change-ledger.test.ts:195-230` | 成功 1 事件 / 越界 0 事件保持；新增 evidence 路径的成功事件用例 |
| C5 | `test/suite/mwds-t02-write-intent.test.ts:334-346` | B1 后语料 `violations` 应归零 → `:346 expect(truePositive).toHaveLength(1)` 需重基线（实测今天 38/39，失败即此例） |
| C6 | 同文件 `:580-582` | `.agenticdoc/k/evidence/x.md === false` 必须翻为 true（或改用具 keyDir 的 ctx 重写该断言） |
| C7 | `test/suite/mwds-t03-bash-write-scope.test.ts:186-291` | 不变，作为通道两侧语义对齐的反向对照（deny 5+1、allowed 5、reads 10、unclassifiable 3；实测 63/63） |
| C8 | `test/extensions/agent-team-loop-checkpoint-wiring.test.ts:312-370` | active set 与注册门断言应保持绿（放宽不新增工具名；实测与 change-ledger 合跑 22/22） |
| C9 | `test/suite/autopilot-protocol.test.ts:245-252`、`:344-369` | 与 Python REGISTRY 的 active set parity 保持绿 |
| C10 | `test_autopilot_l0.py:233-260`、`test_mwpp_collection_parity.py:66-90` | 它们解析 `TOOL_ALLOWLISTS` 源码文本；A1 不动表则保持绿（把 worker_file 写进表会双红） |
| C11 | 新增 `test/suite/regressions/<issue>-write-face-evidence.test.ts` | evidence 接受 + §5.2 越界类 + 12 basename 拒绝 + fail-closed「不建目录、不改字节」 |

**D. 派生产物（1 项）**

| # | 位置 | 动作 |
|---|---|---|
| D1 | `packages/multi-workers/dist/extensions/agent-team-loop.js` | 1,136,749 B 的打包副本内嵌 `worker-file-tool.ts`（实测含 `file name not allowed` 字节）。改源后必须重新生成（`mw update-env`/build），注意 `pi-dist-content` 之类的 bundle 内容检查 |

### §5 反向对照与越界用例

**5.1 现有测试清单（文件 + 用例名 + 断言要点 + 本次实测）**

1. `test/extensions/agent-team-loop-worker-file-tool.test.ts`
   - `WORKER_FILE_NAME_RE / isAllowedWorkerFile (D-102)` → `accepts the whitelist set and rejects non-whitelist neighbors`（`:128`）；断言 `report..md`/`PROGRESS.MD`/尾部空格/尾部换行全拒，且无 `g` 标志
   - `writeWorkerFile (VC-005)` → `VC-005: appends progress.md after a sentinel…`（`:151`）；断言 append 保持前序字节 + UTF-8 字节数 + 目录集
   - `worker_file rejection (VC-006)` → `all 12 illegal file values rejected at execute and schema layers, dir set unchanged`（`:189`）；12 值 = `../x.md`、`a/b.md`、`..\x.md`、`C:\abs\x.md`、`\\unc\share\x.md`、`trace.log`、`task.md`、`output.md`、`worker.log`、空串、`.md`、`report-.md`
   - `execute throws an Error instance (D-109) and writes nothing`（`:228`）；断言 `/^worker_file rejected: /`
   - `rejects fail-closed: no taskDir is created…`（`:238`）；断言非法名/超限时 `existsSync(taskDir)===false`
   - `caps content at 64 KiB UTF-8 bytes…`（`:259`）、`enforces the slug length boundary (41 allowed, 42 rejected)`（`:275`）
   - `execute defaults mode to append and reports path/bytes`（`:292`）；`schema layer accepts the legal set, rejects the 12 variants…`（`:310`）含 `:327` 单源断言
   - **实测：7 通过 / 2 失败**（失败 = :177 与 :285 的目录快照未计 `trace.log`）
2. `test/extensions/agent-team-loop-checkpoint-wiring.test.ts`
   - `activeToolsForType (VC-007)`（`:312`）：表 = 冻结 10 键快照，writeless 追加 `WORKER_FILE_TOOL`；`:325` 每个已注册 type 在 `before_agent_start` 后 active set 精确相等；`:340` 注册门 `worker.registered.includes(WORKER_FILE_TOOL)`
   - `worker_file trace evidence (VC-005/VC-006)`（`:390-470`）：合法调用落 `[TOOL] worker_file`；execute 抛错与 schema 拒绝各落一行 `[TOOL_ERR] worker_file`
   - **实测：与 change-ledger 合跑 22/22 通过**
3. `test/suite/change-ledger.test.ts:195-230` `producer — worker_file`：成功写恰好 1 条 `[WRITE_FILE] path=…report.md`，被拒（`../escape.md`）0 条；append 两次 2 行且不改被写文件字节
4. `test/suite/mwds-t03-bash-write-scope.test.ts`（壳层面）
   - `AC-005b deny list (VC-020)`（`:189`）：5 条 deny（pm-state.md、workers/_workers*、_index.parallel、other key dir、packages/**）+ `.git/**`（`:222`），每条 1 行 `[WRITE_SCOPE]` 且含 `rule=deny`
   - `VC-021+VC-022`（`:230`）：own taskDir/evidence 允许（含 `cp …/evidence/e.md`、`tee`、python 内联写）、10 条纯读通过、3 条不可分类通过且 0 审计噪声
   - `inline python/node read scripts pass, inline write scripts block`（`:266`）
   - `AC-005b write_scope header (VC-023)`（`:296-345`）：一行逗号形式与 block-list 形式解析、blank ⇒ `[]`、`write_scope` 收窄且不能越过 deny
   - **实测：63/63 通过**
5. `test/suite/mwds-t02-write-intent.test.ts`
   - `AC-005a whitelist (VC-015 /reverse b)`（`:566`）：basename 通过、taskDir 内通过、`.agenticdoc/k/workers/t02/report.md` 通过、**`.agenticdoc/k/evidence/x.md` 断言 false**（`:580-582`）
   - `AC-005a corpus replay (VC-015)`（`:311-347`）：命中集必须只含已知真阳性 `mwg-qg-review-20261010`
   - **实测：38 通过 / 1 失败**，失败即语料 replay：`false_positives=1 violations=2`，两条 violation 是 `mwg-qg-review-20261010` 与 `wjg-qg-evidence-closure` 各声明写**自己 key** 的 `evidence/*.md`
6. `test/suite/mwds-t21-write-intent-soundness.test.ts`（`:180` 附近）：契约段里的 `write_scope: .agenticdoc/other/evidence` 不得被计成声明（`declared` 只含真路径）
7. `test/suite/autopilot-protocol.test.ts:245-252, :344-369`：`verifier/reviewer/review/research` 的 active set = Python REGISTRY + `worker_file`
8. Python：`test_autopilot_l0.py:233-260`（7 键 parity）、`test_mwpp_collection_parity.py:66-90`（11 键快照）、`test_rag_research.py:71-86`（11 项 RAG 桶 parity）

**5.2 「越界必须失败」候选用例清单（fail-closed：不建目录、不建/不改文件、留 trace）**

1. 相对穿越：`../..`、`../../x.md`、`evidence/../../x.md`（含 `..` 段；须在 containment 之前就拒）
2. 绝对/UNC/盘符：`/etc/x.md`、`C:\abs\x.md`、`\\unc\share\x.md`
3. 其他 key：`.agenticdoc/other-key/evidence/x.md`
4. 仓库源码：`packages/coding-agent/src/x.ts`、`.git/config`
5. 框架禁写文件（本 key）：`.agenticdoc/<key>/pm-state.md`、`.agenticdoc/<key>/workers/_workers.parallel`、`.agenticdoc/_index.parallel`
6. evidence 之外的同级/邻接：`.agenticdoc/<key>/design.md`、`.agenticdoc/<key>/workers/<other-task>/report.md`
7. 语义待定：`evidence/` 本身（目录）、`evidence/..`（等价于 key 根）——需在 A2 里定义并锁进用例

以上 1-6 与壳层 t03 的 deny/default 面对齐：同一字符串在 worker_file 与 bash 两侧必须给出**一致**结论（这是「两套通道一套策略」的反向对照）。

**5.3 evidence 接受用例（必须成功）**

`.agenticdoc/<key>/evidence/x.md`、`.agenticdoc/<key>/evidence/research/spec-....md`，以及（若 A2 选定 key 相对基准）`evidence/x.md`、`<key>/evidence/research/x.md`。落盘后 `[WRITE_FILE] path=<repo 相对>` 必须出现且字节数与写入内容一致。

### §6 错误文案链

**6.1 「工具不在本角色工具面」的文案生成处**

```
packages/agent/src/agent-loop.ts:611: 			result: createErrorToolResult(`Tool ${toolCall.name} not found`),
```

（`createErrorToolResult` 定义在同文件 `:756-761`；构建产物同文 `packages/agent/dist/agent-loop.js:398`）

**6.2 到 trace 的链路**

- `packages/agent/src/agent-loop.ts:445-452`：**每个** tool call 先 emit `tool_execution_start`（即使工具未注册）
- `worker-mode.ts:2334-2362`：start 处理器计数、记 `[TOOL]` 行（`toolTarget` `:539-556` 会读 `args.file`，因此 worker_file 的参数已可见）
- `worker-mode.ts:2389-2390`：`toolErrorCount++; appendToolError(meta.taskKey, meta.agenticdocRoot, event.toolName, toolErrorText(event.result));`（`toolErrorText` `:560-565` 取结果首行）
- `worker/output-writer.ts:440-446`：`[TOOL_ERR] <ts> <toolName> <truncLine(message,120)>`

**6.3 扩展无法改写模型可见文本（关键约束）**

`tool_result` 钩子（`core/extensions/types.ts:918-958`、`:1240`；接线 `core/agent-session.ts:501-…` `afterToolCall`）只由 `agent-loop.ts:709-754 finalizeExecutedToolCall` 触发，而 not-found 走 `kind:"immediate"` 分支（`:454-461` serial、`:508-518` parallel），**不经过** `finalizeExecutedToolCall` ⇒ 扩展拿不到也改不了这条结果。

**6.4 AC-007 的候选（只列，不实现）**

1. 为 writeless 角色注册同名 `write` 桩工具，execute 抛出带替代通道的提示 → 会改变 active set，与 GC-5「不得给这两类角色增开 `write` 工具」的字面冲突，并使 C8/C9 的 parity 断言需要重写；
2. 只增强 PM 可见的 `[TOOL_ERR]` 行（`worker-mode.ts:2390` / `:560-565` 处做映射）→ 模型侧仍是核心原文，AC-007 的「文案」若指模型可见文本则不满足；
3. 把替代通道写进卡面契约段（`ui-bridge.ts:1787`）与 worker_file 的 description/promptGuidelines（`worker-file-tool.ts:91-100`）→ 不触碰工具面，属「事前指引」而非「事后文案」。

**6.5 worker_file 描述文本中列 basename 白名单的位置（AC-007 第二处）**

- `worker-file-tool.ts:91-95`（description）
- `worker-file-tool.ts:96-100`（promptGuidelines）
- `worker-file-tool.ts:103-106`（schema 的 `file.description` 在 `:105`）
- 关联：`worker-mode.ts:2559-2563` 的 checkpoint steer 文本经 `narrowTool: WORKER_FILE_TOOL` 点名该工具（放宽后措辞需一致）；`pm/ui-bridge.ts:1771` 的派发期 Fix 文本同样点名该工具。

### 未找到清单

- 字面串 `Tool write not found` 在仓库源中：**未找到**。命令 `git grep -c "Tool write not found" -- packages` → 无输出、exit=1；该串只在 `agent-loop.ts:611` 以模板形式存在（`git grep -n "Tool .* not found" -- packages/coding-agent/src packages/agent/src` → 仅 `packages/agent/src/agent-loop.ts:611`）。
- 断言 `[TOOL_ERR] … not found`（针对 write/worker_file）的测试：**未找到**。命令 `git grep -n "not found" -- packages/coding-agent/test` 的命中只有 `agent-team-loop.test.ts:648/662`（`edit` + `oldText not found in file`，与本问题无关）与一个 fixture jsonl。
- `worker_file` 在 `worker-mode.ts:2133` 之外的注册调用：**未找到**（`git grep -n "registerWorkerFileTool(" -- packages` → 定义 1 处、生产调用 1 处、测试 1 处、bundle 2 处）。
- `worker-file-tool.ts` 内任何 evidence/key/agenticdoc 相关代码：**未找到**（`git grep -n -E "evidence|keyDir|agenticdoc" -- .../worker-file-tool.ts` → exit=1，无输出）。

### 未覆盖面声明

- 未读 `pm/pm-orchestrator.ts` 的回读/`notified` 路径与 `startWorkerPollLoop`（属 AC-011/AC-012/AC-013，不在本 RQ）。
- 未评估 `collectArtifacts` / `findNonEmptyReport`（`shared/deliverable-evidence.ts:105-116`）对 evidence 产物的收集语义 ⇒ R3（「evidence 只放产物」）未验证。
- 未实现任何改动、未跑全量套件（禁止）、未重建 dist。
- 未做真实 provider 端到端（本 RQ 为静态只读 + 定向单测）。
- Windows + PowerShell 5.1：所有命令经 `python -`/`python -X utf8 -` 与 node vitest CLI 执行（CJK 以文件回读校验）；未使用 `&&`。

### 测量（命令 + 输出，供复核）

- `git diff --quiet HEAD -- <file>`（worker-file-tool.ts / 其测试 / change-ledger.ts）→ exit=0 ×3 ⇒ 上述两例失败与本 RQ 无关
- `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts` → `Tests 2 failed | 7 passed (9)`
- 同上 `test/suite/change-ledger.test.ts test/extensions/agent-team-loop-checkpoint-wiring.test.ts` → `Tests 22 passed (22)`
- 同上 `test/suite/mwds-t03-bash-write-scope.test.ts` → `Tests 63 passed (63)`
- 同上 `test/suite/mwds-t02-write-intent.test.ts` → `Tests 1 failed | 38 passed (39)`；`[VERIFY] VC-015: corpus=434 read_only_books=30 hit_files=16 hits=21 false_positives=1 violations=2`
- 运行期观测（本 RQ 自身的写面）：用含本文正文的 heredoc 写本文件时，AC-005b 壳层守卫拦截 —— `write-scope: blocked bash write to .md: outside the worker write surface [rule=scope]`。被抽取的 target 是裸 `.md`，审计字段 `pattern=redirect`（来源：正文中 report- 前缀与 slug 的尖括号枚举被拆出一个重定向目标），属 FW-009/P4 的伪目标抽取类别（误报方向）。完整审计行（`trace.log`）：`write-scope blocked=true rule=scope detail=outside-allowed-surface pattern=redirect target=.md`。据此改用 `worker_file` 写任务目录 + `cp` 落 evidence 的两步法。

## 残留与未验证

1. A2 的相对基准（project-root 相对 `.agenticdoc/<key>/evidence/**` vs key 相对 `evidence/**`）**未定** —— 设计阶段的第一个必须裁决项，schema 正则与 §5.3 用例都依赖它。
2. A15（`write_scope:` 是否约束 worker_file）**未定** —— 影响 B4 是否需要非 shell writeless 角色也渲染 C1 头。
3. AC-007 的「文案」层级（模型可见 vs PM 可见 vs 卡面事前指引）**未定** —— 决定是否触碰 GC-5 与 C8/C9。
4. `evidence/**` 内的深度、允许扩展名（R3「只放产物」）与 `evidence/` 目录本身作为目标的语义未定。
5. 未实测放宽后 worker_file 在真实 worker 进程中的行为（需实现后跑 suite 才可宣称 AC-006 通过）。
6. §5.1-(1) 的 2 例与 §5.1-(5) 的 1 例失败均为 HEAD 既存状态；本 RQ 未改动仓库，故未验证「修好后是否全绿」。
7. `pm/ui-bridge.ts` 的行号取自当前工作树：该文件在本次运行前已被另一并行 session 改了 `setWatchWidget`（`@@ -893 +893,3 @@`，+3/-1，净 +2 行），因此 §3.8 与 B1-B6 引用的 ui-bridge 行号比 HEAD 大 2；实现时应以函数名 grep 定位，不要按行号硬编码。

## 上下文来源

- 任务卡：`.agenticdoc/mw-worker-output-contract/tasks/T-RQ2-write-face.md`
- spec：`.agenticdoc/mw-worker-output-contract/spec.md`（§1.4 不收「给角色加 write」、§1.5 P2、§1.6 S4、§2.3 安全约束、§3 AC-006/AC-007）
- 目标锚点：`.agenticdoc/goal.md`（Key Constraints 的工具白名单条目）
- 源码：`worker/worker-file-tool.ts`、`worker/worker-mode.ts`、`worker/output-writer.ts`、`worker/read-scope.ts`、`shared/change-ledger.ts`、`shared/deliverable-evidence.ts`、`shared/dispatch-models.ts`、`pm/ui-bridge.ts`、`rag/tools.ts`、`core/extensions/types.ts`、`core/agent-session.ts`、`packages/agent/src/agent-loop.ts`、`autopilot/dispatch.py`、`mw_common.py`、`launcher.py`
- 测试：`test/extensions/agent-team-loop-worker-file-tool.test.ts`、`test/extensions/agent-team-loop-checkpoint-wiring.test.ts`、`test/suite/change-ledger.test.ts`、`test/suite/mwds-t02-write-intent.test.ts`、`test/suite/mwds-t03-bash-write-scope.test.ts`、`test/suite/mwds-t21-write-intent-soundness.test.ts`、`test/suite/autopilot-protocol.test.ts`、`test_mwpp_collection_parity.py`、`test_autopilot_l0.py`、`test_rag_research.py`
- 配置与产物实测：`.mw/dispatch.yml`、`packages/multi-workers/dist/extensions/agent-team-loop.js`

[VERIFY] keys=11 writeless=5 deny_rules=6 worker_file_callsites=3 change_points=A16+B6+C11+D1=34 measured=worker-file-tool_7pass2fail(HEAD) t02_38pass1fail(HEAD) t03_63pass change-ledger+checkpoint_22pass repo_files_modified=0
