# 证据：运行期写面闸扩到全角色的插入点（RQ-D2 / T-W-D2）

- key: mw-write-face-guard
- phase: DESIGN
- 日期: 2026-10-14
- 角色: research（只读，未改任何生产文件）
- 唯一交付: 本文件（`.agenticdoc/mw-write-face-guard/evidence/research/design-runtime-guard-20261014.md`）
- 上游: `spec.md`（AC-004/007/010/011/013）、`design.md`（D-001..D-009）、`evidence/research/design-rq-plan-20261014.md`
- 方法: 全仓只读检索 + 只读脚本解析源码（未执行真实 agent 工具调用、未跑测试套件）。所有判据 = `文件:行号` + 原文；未找到者写"未找到（命令 + 输出）"。所有行号来自本轮源码解析，逐条已复核。

## §0 结论先行

1. **现状**：运行期写面闸只有一条 —— `worker-mode.ts:2216-2265` 的 bash 守卫；安装条件 `isShellRole(meta.type) && isWritelessRole(meta.type)`（`worker-mode.ts:2202-2203`），今天只命中 `research`（实测 shell∩writeless = 1）。`write`/`edit` 在 worker 运行期**零写面守卫**（`worker-mode.ts` 里 `pi.on("tool_call")` 只有 2 处：`2165` 读面、`2218` bash 写面）。
2. **推荐插入点 = 留在 `workerModeActivate` 闭包内（IP-1b）**：新增一个覆盖 `write`/`edit` 的 `tool_call` 分支（读 `event.input.path`），并把 bash 守卫安装条件从 `isShellRole && isWritelessRole` 放宽到 `isShellRole`；判定与词法**复用现有 `extractBashWriteCandidates`/`checkBashWriteScopeTarget`**（`worker-mode.ts:1554/1606`），不引入第三份词法。
3. **不得复用 `shared/implementation-gate.ts` 的 target 侧 lexer**：它按"是否仓库代码路径"过滤（`implementation-gate.ts:147` `isCodePathAbs`），且自述漏面为 python -c / 预写脚本 / find -delete / tar / PowerShell cmdlets（`implementation-gate.ts:25-27`）——与 AC-004/AC-010 要覆盖的路径方向相反。
4. **朴素放宽（只改 `2203` 一行）会立刻误拦**：现有 deny 面含绝对 `packages/**`（`worker-mode.ts:1579`），默认面 = taskDir + `<key>/evidence`（`worker-mode.ts:1637`）；coding/repair/phase-writer/vision 的合法工作面恰是 `packages/**`。放宽前必须先做**角色类别化的 deny/默认面**（§4.2）。
5. **`research` 既有行为可逐字保持**，前提是采用 IP-1b（加分支、不合并 handler、config 不变）；差异表见 §4.3。
6. **载体已缓存**：`meta` 在 `workerModeActivate` 入口解析一次（`worker-mode.ts:1902`），`meta.writeScope` 在闭包内（`worker-mode.ts:322/434-465`）。新增 `write_face:` 只需扩 `parseTaskMd`，运行期**零额外 I/O**。
7. **本轮新实测**：现行守卫对**只读命令**仍会假阻（E3 家族可在当前修订复现）——§3.3 第 3 条给了本轮自己的 trace 原文。

## §1 现有 research 分支的完整形状

### 1.1 闸装在哪（工具工厂 / hook）

- 安装条件（`worker-mode.ts:2202-2215`）：
```
	const bashWriteScopeConfig: BashWriteScopeConfig | undefined =
		isShellRole(meta.type) && isWritelessRole(meta.type)
			? {
					projectRoot: process.cwd(), // launcher spawns workers with cwd = project root
					taskDir,
					keyDir: path.dirname(meta.agenticdocRoot),
					trueRoot: meta.trueAgenticdocRoot,
					writeScope: meta.writeScope,
				}
			: undefined;
```
- 注册处（`worker-mode.ts:2216-2218`）：
```
	if (bashWriteScopeConfig) {
		const config = bashWriteScopeConfig;
		pi.on("tool_call", (event) => {
```
- 角色能力判据（`worker-mode.ts:150-161`）：`isShellRole` = ``activeToolsForType(taskType).includes("bash")``；`isWritelessRole` = ``!tools.includes("write") && !tools.includes("edit")``。
- 工具允许表（`worker-mode.ts:73-107`）：``research: ["read", "find", "grep", "ls", "bash"]``。
- 全局其它写闸在 `index.ts` 注册，早于 worker 分支（`index.ts:43/50/60/70`，worker 分支 `index.ts:73`）；`workerModeActivate` 内在读面（`2165`）之后才注册写面（`2218`）。tool_call handler 语义 = 全部跑、首个 block 生效（`core/extensions/runner.ts:934-952`）。

### 1.2 读什么输入

- 只读 `event.toolName === "bash"` 与 `event.input.command`（`worker-mode.ts:2219-2223`）：
```
			if (event.toolName !== "bash") return undefined;
			const command = (event.input as { command?: unknown } | undefined)?.command;
			if (typeof command !== "string" || command.trim() === "") return undefined;
```
- 逐 target 判（`worker-mode.ts:2222`）：`for (const candidate of extractBashWriteCandidates(command)) {`。
- 不看 `write`/`edit`/`worker_file`。

### 1.3 怎么写拒绝

- bash 守卫返回插件 block（`worker-mode.ts:2263`）：`return { block: true, reason: verdict.reason };`
- block → 核心转 tool error：`packages/agent/src/agent-loop.ts:636-641`（`createErrorToolResult(beforeResult.reason || "Tool execution was blocked")`, `isError: true`）→ `tool_execution_end.isError` → `appendToolError`（`worker-mode.ts:2390`；实现 `output-writer.ts:440-446`，格式 `[TOOL_ERR] ts <tool> <前120字符>`）。
- `worker_file` 是另一形状（throw）：`worker-file-tool.ts:112-115`（`throw new Error("worker_file rejected: ...")`），失败形状说明见 `worker-file-tool.ts:9-14`。

### 1.4 trace 落什么行

- 每条 block / allow-unknown 落 `[WRITE_SCOPE]`（`worker-mode.ts:1695-1715`）：
```
			`[WRITE_SCOPE] ${r.ts} write-scope blocked=${String(r.blocked)} ${risk}rule=${r.rule} detail=${r.detail} ` +
				`pattern=${r.pattern} target=${r.target} cmd=${summary}\n`,
```
- 每个受保 run 末落一行 `[WRITE_SCOPE_SUMMARY]`（`worker-mode.ts:1718-1729`）：`` `[WRITE_SCOPE_SUMMARY] allow=${counts.allowDetermined} deny=${counts.deny} allow-unknown=${counts.allowUnknown}` ``；只在 `recordEnd` 里当 `bashWriteScopeConfig` 存在时写（`worker-mode.ts:2426-2428`）。
- escape hatch 落 `[ESCAPE_HATCH]`（`worker-mode.ts:1737-1749`）：`` `[ESCAPE_HATCH] allow_foreign_write=${taskKey} target=${target}` ``。
- 纯读/不可分类命令不落 audit 行（`worker-mode.ts:1691-1694` 注释："Pure-read/unclassified commands never reach here (no audit noise ...)"）。

### 1.5 白名单 / 默认面 / deny 面 / 判定顺序

- 词法：`tokenizeShellCommand`（`worker-mode.ts:791`）+ `extractBashWriteCandidates`（`worker-mode.ts:1554-1559`）；空结果 = 未识别为写 = 放行（`worker-mode.ts:1552-1553`："An empty result means 'not a recognized write' — the caller must allow it (P1, DD-03)."）。
- 判定顺序（`checkBashWriteScopeTarget`，`worker-mode.ts:1606-1662`）：
  1. `!verbatim` → `allow-unknown` 放行（`worker-mode.ts:1611-1623`）：注释"a non-verbatim target is not statically determinable (`allow-unknown`, fail-open)"（`1611-1613`）。
  2. deny 面优先（`worker-mode.ts:1625-1636`）：`bashWriteDenyReason`（`worker-mode.ts:1568-1582`）六类 —— `pm-state.md`、`workers/_workers*`、`_index.parallel`、其它 key / `.agenticdoc` root、`packages/**`（`1579`）、`.git/**`。注释（`1566-1567`）："The deny list is checked first and can never be widened by a `write_scope:` header."
  3. 默认面（`worker-mode.ts:1637-1648`）：`const evidenceDir = path.join(config.keyDir, "evidence");`，`!isSameOrUnder(config.taskDir, target) && !isSameOrUnder(evidenceDir, target)` → block `rule=scope`。即默认面 = `taskDir` ∪ `<keyDir>/evidence`。
  4. `write_scope:` 收窄（`worker-mode.ts:1649-1661`）：`config.writeScope !== undefined && !config.writeScope.some(...)` → block `rule=write-scope`。
- escape hatch（`worker-mode.ts:2248-2252`）：`if (meta.allowForeignWrite === true && verdict.rule !== "deny")` → 放行 + `[ESCAPE_HATCH]`。
- `BashWriteScopeConfig` 形状（`worker-mode.ts:747-761`）：`projectRoot / taskDir / keyDir / trueRoot / writeScope`。

### 1.6 载体解析与缓存

- `TaskMeta.writeScope?: string[]`（`worker-mode.ts:319-322`）：
```
	/** write_scope entries (contract C1/T-03), project-root relative. Present →
	 * the AC-005b bash write surface is narrowed to the intersection with the
	 * default (own taskDir + `<key>/evidence/**`); absent → default surface. */
	writeScope?: string[];
```
- 解析（`worker-mode.ts:434-465`）：一行逗号形式 `write_scope: a, b` 与 YAML 块列表 `- item` 两种；`write_scope:` 存在但空 → `[]`（fail-closed）；缺头 → `undefined`（落默认面）。
- 运行期缓存：`const meta = parseTaskMd(taskPath);`（`worker-mode.ts:1902`）+ `const taskContent = fs.readFileSync(taskPath, "utf8");`（`worker-mode.ts:1919`）——启动各一次，之后全部 tool_call 判定复用 `meta`。
- 生产端（今天的实际值）：只在 `writelessRole && isShellRole(typeField)` 时渲染（`pm/ui-bridge.ts:2431-2432` 与 `2925-2926`）；`renderDefaultWriteScope`（`pm/ui-bridge.ts:1765-1768`）输出 `write_scope: .agenticdoc/<ownerKey>/workers/<taskKey>, .agenticdoc/<ownerKey>/evidence`。

### 1.7 worker_file 通道（已结构性限位，不是缺口）

- 只接受 basename：`WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/`（`worker-file-tool.ts:42`），拒绝 `../x.md`、`a/b.md`、绝对路径（模块头 `worker-file-tool.ts:5-8`）。
- 写入固定 `taskDir/<file>`（`writeWorkerFile`，`worker-file-tool.ts:56-93`；`fs.writeFileSync(target, content, "utf8")` 在 `:77`）。
- 仅无 `write` 的角色注册它（`worker-mode.ts:2131-2133`：`const hasWriteTools = toolsForType(meta.type).includes("write"); if (!hasWriteTools) registerWorkerFileTool(pi, workerTaskDir);`）。
- ⇒ 其写面恒 ⊆ 默认面 `taskDir`，**运行期无需新增写面闸**（见 IP-5）。

### 1.8 现状覆盖面矩阵（实测，见 [VERIFY]）

- 允许表键 = 11（含内部 `fallback`）；`shell` = 6；`writeless` = 5；`shell ∩ writeless` = 1（research）⇒ 今天装闸角色数 = 1。
- `shell ∩ writable` = 5（coding / phase-writer / repair / vision / fallback）今天 bash **无写面闸**。
- `writable ∩ ¬shell` = 1（roadmap-writer）今天 `write`/`edit` 无写面闸。
- 未找到：`write`/`edit` 的运行期写面判定点。命令与输出：`rg -n 'on\(.tool_call' packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` → `2165`、`2218`（前读面后 bash，均非 write/edit）。

## §2 插入点候选（≥3）

每个候选按：覆盖工具面 / 漏掉的路径 / 是否需 worker 读自身 task.md（是否已有缓存）/ 首个失败模式。

### IP-1：留在 `workerModeActivate` 闭包内（推荐）

- **IP-1a（一行放宽）**：把 `worker-mode.ts:2203` 条件改为 `isShellRole(meta.type)`。
  - 覆盖：bash（6 个 shell 角色）。
  - 漏：`write`/`edit` 全部（仍零守卫）；bash 词法的既有漏面（§3 表：`allow-unknown` 目标、`MAX_UNWRAP_DEPTH=3`（`worker-mode.ts:875`）之外）。
  - 重读 task.md：否（meta 已缓存，`worker-mode.ts:1902`）。
  - 首个失败模式：**合法写立刻被 deny/scope 误拦** —— `packages/**` 是绝对 deny（`worker-mode.ts:1579`），默认面是 taskDir + evidence（`worker-mode.ts:1637`）；`mwds-t03` 的 VC-024 明确断言 `coding`/`repair`/`vision` 今天"registers no write-scope guard and its bash commands pass"（实测 `interceptorCount()` 断言集 `[1, 0]`），放宽即红。
- **IP-1b（新增 write/edit 分支 + 角色类别化 config，推荐）**：保留 `2216` 的 bash handler；在闭包内再加一个 `pi.on("tool_call")` 覆盖 `write`/`edit`，读 `event.input.path`（schema：write `core/tools/write.ts:15` `path`；edit `core/tools/edit.ts:46` `path`），走同一 deny/default/declared 判面（`checkBashWriteScopeTarget` 的路径版，`reason` 复用 `write-scope: ...` 文案）；bash 条件放宽到 `isShellRole` 的同时把 config 换为角色类别化（§4.2）。
  - 覆盖：`write`/`edit`（6 个 writable）+ bash（6 个 shell）。
  - 漏：bash 不可静态判定目标（`allow-unknown`，非本次扩面引入）；`worker_file`（已限位，不需要）。
  - 重读 task.md：否。
  - 首个失败模式：若 writable 角色沿用 `taskDir + evidence` 默认面，会把仓库写全部拦死；必须先落地 §4.2 的角色类别化默认面。
- **IP-1c（合并成一个 handler）**：把 `2165`/`2218` 合成一个 tool_call 分支。
  - 覆盖：同 IP-1b。
  - 重读 task.md：否。
  - 首个失败模式：改变 handler 计数与注册顺序；`mwds-t03` 的 `interceptorCount()===1/0` 断言必须先改，"research 逐字保持"从"加分支"退化为"改结构"。

### IP-2：改全局共享守卫（`index.ts:43-70` 注册链）

- 位置：`shared/implementation-gate.ts`（已注册于 `index.ts:60`）或新建 `shared/write-face-guard.ts`。
  - 覆盖：全模式（PM/interactive 也跑）`write`/`edit`/`bash`。
  - 漏：无 worker task 上下文；需自行从 `PI_WORKER_TASK` 读并解析 task.md（今天这些全局守卫不读它）。
  - 重读 task.md：**是**（新增 I/O；且 `index.ts` 注册早于 `workerModeActivate`，拿不到已解析的 `meta`）。
  - 首个失败模式：①PM/interactive 无 task → 必须整体 no-op，而写面语义是 worker-only；②`implementation-gate` 的 `worker-env` 放行在 face 判定**之前**（`implementation-gate.ts:466-469`：`if (typeof workerTask === "string" && workerTask !== "") return { blocked: false, basis: "worker-env", ... }`），要接 face 判定就得改 mw-implementation-gate 既有语义（P-018）；③`packages/**` 语义冲突同 IP-1a。

### IP-3：抽纯判定模块 `worker/write-face-guard.ts`（或 `shared/write-face.ts`）

- 位置：把 `extractBashWriteCandidates`（`1554`）/`checkBashWriteScopeTarget`（`1606`）/`bashWriteDenyReason`（`1568`）/`matchesWriteScopeEntry`（`1584`）抽成纯模块，`workerModeActivate` 只留注册薄层（照 `worker/read-scope.ts` 范式：`read-scope.ts:1-25` 自述"pure decision logic ... worker-mode.ts owns the tool_call wiring"）。
  - 覆盖：同 IP-1b；额外收益 = PM/conductor 侧派发闸（AC-001/002）可复用同一判定，降低漂移。
  - 漏：同 IP-1b。
  - 重读 task.md：否。
  - 首个失败模式：大范围移动代码会改 `worker-mode.ts` 行号，而该文件多处注释自述行号被 spec/design 钉住（`worker-mode.ts:2900-2905`："Declared after its call sites for the same AC-011 line-number reason."；`2927-2935`："Declared after its call site on purpose: AC-011 pins the line numbers that spec.md/design.md reference."）→ 引用需同步更新，diff 大、回归面广。

### IP-4（不可用于阻断）：`tool_execution_end` / `tool_result` 观测

- 位置：`worker-mode.ts:2317-2390`（记 `[WRITE_FILE]` / `[TOOL_ERR]`）。
  - 覆盖：所有工具的**事后**审计。
  - 漏：无法阻断（执行已完成）。
  - 重读 task.md：否。
  - 首个失败模式：当闸用 = 假绿（写已发生）。仅可作运行期闸的审计对账。

### IP-5（无需新增）：`worker_file`

- 已在 `worker-file-tool.ts` 结构性限位（§1.7）。
  - 首个失败模式：若再对 `worker_file` 加 face 判定，会与 basename 白名单语义重叠并新增假阻面（输入只有 basename，无路径可判）——记为"不需要"。

## §3 bash 写目标词法归属

### 3.1 两个 lexer 的差异（源码实测）

| 维度 | `shared/implementation-gate.ts`（+`shared/bash-segments.ts`） | `worker/worker-mode.ts` 写面 lexer |
|---|---|---|
| 入口 | `checkBashWriteTarget`（`implementation-gate.ts:362`）经 `parseBashSegments`（`bash-segments.ts:106`） | `tokenizeShellCommand`（`worker-mode.ts:791`）→ `extractBashWriteCandidates`（`1554`） |
| 写动词 | `const WRITE_VERBS = new Set(["tee", "cp", "mv", "rm", "sed"]);`（`implementation-gate.ts:80`） | `extractCommand` 的 31 个 case 标签（bash/sh/zsh/dash/ksh/cmd/powershell/pwsh/perl/ruby/python/python3/py/node/tee/cp/mv/rm/mkdir/touch/truncate/install/ln/rsync/dd/tar/sed/find/git/curl/wget） |
| inline 脚本 | 无 | `INLINE_WRITE_PATTERNS`（`1049`）/`PERL_INLINE_PATTERNS`（`1060`）/`RUBY_INLINE_PATTERNS`（`1064`）/`INLINE_EXEC_PATTERNS`（`1069-1073`）+ 递归 unwrap（`MAX_UNWRAP_DEPTH=3`，`worker-mode.ts:875`） |
| 目标过滤 | `isCodePathAbs`（`implementation-gate.ts:147-158`）：只 `packages/**` 的 `.ts/.tsx/.js/.cjs/.mjs/.py`，排除 node_modules/dist/.tmp | 该 worker 的 deny 面 + 默认面 + `write_scope`（`checkBashWriteScopeTarget`，`1606-1662`） |
| 不可判定目标 | 无 tier（`$var` 按字面 resolve，通常不匹配代码路径 → 静默漏） | `verbatim` 标志 → `allow-unknown` 放行 + 审计（`worker-mode.ts:787/798`，`1611-1623`） |
| 自述漏面 | "Not a sandbox: python -c inline writes, pre-written script execution, find -delete/-exec, tar, PowerShell cmdlets, and env-var path spellings are known misses, accepted as legacy gaps."（`implementation-gate.ts:25-27`） | 自述 miss 优先于误拦（`worker-mode.ts:723-726`），miss 面被 `INLINE_*`/unwrap 大幅收窄 |
| 测试锁 | implementation-gate 自有测试 | 19 行 exact-target 表 + 36 行 verbatim 语料（`test/suite/mwds-t03-bash-write-scope.test.ts`） |

### 3.2 判定

**不复用 `implementation-gate` 的 target lexer；写面守卫继续用现有写面 lexer，且只允许一份。** 理由：
1. 目标语义不同：gate 判"目标是不是仓库代码路径"（固定全局集合，`isCodePathAbs`）；写面判"目标在不在该 worker 的声明面"（per-task 集合 + deny 优先）。同一命令两侧期望不同（如 `packages/**` 在 gate 里要判，在 writeless 角色的写面里是绝对 deny）。
2. 漏面不可接受：gate 自述漏 python -c / 预写脚本 / find -delete / tar / PowerShell cmdlets，这些恰是 AC-004/AC-010 要求覆盖的。
3. 反向也不可替代：写面 lexer 不跟踪 `cd`、不做 `cp` 目录目标展开（gate 的 `verbTargets` 做了，`implementation-gate.ts:289-345`），gate 的这部分能力不应被删。
4. 仓内已有**两份** lexer（`bash-segments.ts` 供 gate/worktree guard；`worker-mode.ts` 写面 lexer）。本次扩面**不得引入第三份**；若做 consolidation，方向是把写面 lexer 提为纯模块（IP-3），而非让 gate lexer 接管。

### 3.3 必须避免的假阻形态 + 反例向量（≥5）

一手实例（必须在设计里避免）：
1. E3（`spec-write-face-sources-20261014.md` §E3）：trace 行 `[WRITE_SCOPE] ... write-scope blocked=true rule=scope detail=outside-allowed-surface pattern=redirect target=--glob`，真实写入路径在 write_scope 内、命令无真实重定向。
2. §7.8（`spec-write-face-safety-20261014.md` §7 第 8 条）：`xkey-gate-guard` 因"命令文本引用 `.agenticdoc/_autopilot` + 含写动词"误拦文档内容。反模式源码：`checkXkeyGateBashCommand`（`xkey-gate-guard.ts:195-232`）按"引用 + 写构造"文本判定（`WRITE_VERB_RE` `xkey-gate-guard.ts:167`、`REDIRECT_RE` `:174`）。
3. **本轮新实测（本 worker，只读命令被假阻）**：本轮取证中一条**只读**命令（Python 读 `worker-mode.ts` 并打印行号）被现行守卫 block。本任务目录 trace.log 原文：
   - `[WRITE_SCOPE] 2026-10-13T23:54:19.288Z write-scope blocked=true rule=scope detail=outside-allowed-surface pattern=redirect target=|| token.text === cmd=cd H:/git/Multi-Workers $code = @' import io w = io.open("packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts", encoding="utf-8")...`
   - `[TOOL_ERR] 2026-10-13T23:54:19.288Z bash write-scope: blocked bash write to || token.text ===: outside the worker write surface [rule=scope]; allowed: H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\workers\wfg-rq-d2-runtime-guard or H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\evidence`
   - 判据：`pattern=redirect` 的目标 `|| token.text ===` **横跨多词**，说明判定把命令载荷（脚本内容）当成了 shell source；受害命令只读、真实写目标不存在。⇒ E3/§7.8 家族在当前修订**仍可复现**。根因本轮未定位（见 §5）。

反例向量：

| # | 向量 | 期望 | 依据（file:line / 测试） |
|---|---|---|---|
| V1 | `Set-Content -Path o.txt -Value 'printf x > out.txt'` | 只 `o.txt`（内容里的 `>` 不是重定向） | 引号 token 语义 `worker-mode.ts:811-825`；PowerShell `-Path` 取值 `worker-mode.ts:1533-1545`；测试 `mwds-t03` T-18/B |
| V2 | `cat <<EOF > out.md`，body 含 `x > y` | 只 `out.md` | `dropHeredocBodies` `worker-mode.ts:2936-2985`；注释 `2927-2935` |
| V3 | `Write-Output a <term> --glob x` | 无候选（`--glob` 不是重定向目标） | E3 实例；重定向只在 `>` 的紧邻 token 取值 `worker-mode.ts:1217-1234`。残留见 §5.2 |
| V4 | `printf x > "$T/report.md"` | `allow-unknown`（永不阻断） | `LIVE_EXPANSION_CHARS` `worker-mode.ts:787/798`；语料 M2/M9/M10 |
| V5 | `echo "a > b"` | 无候选 | 引号分支 `worker-mode.ts:811-825`；测试 "unclassifiable commands" 组 |
| V6 | `echo x \| tee $T/report.md` | `allow-unknown`（tee case + verbatim） | `tee` case `worker-mode.ts:1349-1352`；语料 M11 |
| V7 | `[[ "$ts" > "2026-01-01" ]]` | 无候选 | `comparisonDepth` `worker-mode.ts:1205-1245` |
| V8 | `echo x 2>&1` / `>&2` / `exec 3>&-` | 无候选 | fd-dup 三态 `worker-mode.ts:1217-1234`；测试 VC-MWGF-009 |
| V9 | `Get-Content a.txt > $null` / `> /dev/null` | 无候选 | `NULL_WRITE_TARGETS` `worker-mode.ts:1024-1033`；语料 M14 |
| V10 | 命令文本只**引用** `.agenticdoc/_autopilot` + 写动词（真实目标是自己的 evidence） | 放行（target 侧判定） | 反向证据：`xkey-gate-guard.ts:195-232` 是文本判定（误拦，§7.8）；写面守卫按 target 判（`worker-mode.ts:2222`） |
| V11 | PowerShell here-string `@'...'@` 里含 `>` 字面量（本轮实例 3） | 放行（内容不是重定向） | 本轮 trace（实例 3）；**当前未通过**，是待修缺口 |

新 write/edit 分支的假阻面：`event.input.path` 是字面字符串（`core/tools/write.ts:15`、`core/tools/edit.ts:46`），无词法歧义，故 write/edit 侧假阻风险 = 默认面/deny 面配置错误（§4.2），不是词法问题。

## §4 deny 优先与默认面

### 4.1 判定顺序（现状，必须保持）

`1 不可静态判定 → allow-unknown` → `2 deny` → `3 默认面` → `4 write_scope 收窄`（`worker-mode.ts:1606-1662`）。deny 绝对优先、不可被 `write_scope` 放宽（`worker-mode.ts:1566-1567`）。

### 4.2 关键发现：默认面/deny 面必须**角色类别化**

今天的 deny 把 `packages/**` 当绝对 deny（`worker-mode.ts:1579`），默认面 = `taskDir + <key>/evidence`（`worker-mode.ts:1637`）。这套配置只对 writeless（research）成立。对 writable 角色直接套用会误拦其全部合法写（coding 的工作面就是 `packages/**`）。建议拆分（供 design 定稿）：
- `denyAlways`（全角色、跨 worker 隔离）：`pm-state.md`、`workers/_workers*`、`_index.parallel`、其它 key / trueRoot、`.git/**`。
- `denyWritelessOnly`：`packages/**`（research 不得写码）。
- `defaultFace`：writeless = `taskDir + <key>/evidence`（保持）；writable 且未声明 `write_face` = **仅 denyAlways**（等价"今天零守卫 + 新增跨 worker 硬拦"）；声明时 = `write_face` 之外的允许面。
- `declaredFace`：`write_face:` 命中时作为收窄/允许集。

（字段名由 design/spec 定；D-001 已选 `write_face:`。）

### 4.3 `research` 既有行为是否逐字保持

- 结论：采用 **IP-1b** 时，research 的 bash 路径**逐字保持**（同一 handler、同一 config、同一 trace/summary），research 无 write/edit，不被新分支影响。
- IP-1a 同样保持 research 行为，但会误拦 writable 角色。
- IP-1c 破坏"逐字"（handler 结构变）。

差异表（今天 vs 新，IP-1b）：

| 面 | 今天 | 新（IP-1b） | research 是否变 |
|---|---|---|---|
| research + bash | 守卫；config{默认面, writeScope} | 同一 handler、同一 config | **否** |
| research + write/edit | 无该工具（allowlist 不含） | 新分支存在但永不命中 | 否 |
| research + worker_file | basename 限 taskDir | 不变 | 否 |
| coding/phase-writer/repair/vision/fallback + bash | 无闸 | 新闸（角色类别化 config） | 不适用 |
| coding/... + write/edit | 无闸 | 新闸 | 不适用 |
| roadmap-writer + write/edit | 无闸（无 bash） | 新闸（write/edit 分支） | 不适用 |
| review/verifier/reviewer/rag-research | 仅 worker_file | 不变（无 bash/write/edit） | 不适用 |
| tool_call handler 数（research） | 2（read_scope 存在）或 1 | 3 或 2 | 变（新增分支，需同步测试断言） |
| `[WRITE_SCOPE_SUMMARY]` | 仅 research | 扩到所有 shell（或全部可写）角色 | research 行不变，其它角色新增行 |

> 结构面变化（handler 计数、summary 覆盖面）是 AC-004 的预期行为；`mwds-t03` 的 `interceptorCount` 与 VC-024（"coding/repair/vision 不注册 guard"）必须改断言口径，这不是行为回归。

## §5 残留与未验证

1. 本轮**未执行真实 agent 工具调用**（只读角色，除本 worker 自身的只读测量命令外），所有"拦/不拦"由源码判定路径 + 既有测试语料支撑；未重跑 `mwds-t03` 套件。
2. V3 残留：真实重定向目标是 `-` 前缀单词（如 `> --glob`）时，`worker-mode.ts:1217-1234` 仍会把它当 target；现有缓解只覆盖"内容里的 `>`"（heredoc/引号/比较上下文），没有"flag 形 target"的通用规则。未做端到端复现。
3. **实例 3 的根因未定位**：只读命令被假阻，目标 `|| token.text ===` 跨词，说明载荷文本被当 source；机制假设（PowerShell here-string `@'...'@` 不是 shell lexer 认识的引号上下文，导致引号奇偶错位、`>` 被当算子）**未验证**，不作结论。=> 待 spec/plan 排一个最小 repro。
4. `fallback` 不入 `REGISTERED_WORKER_TYPES`（`worker-mode.ts:132-135`），conductor 派发时 fail-closed；"全角色"计数含它仅为矩阵完整，实际可派发 writable+shell = coding/phase-writer/repair/vision（4 个）+ writable 无 shell = roadmap-writer（1 个）+ writeless shell = research（1 个）。
5. `write_face:` 字段尚不存在。命令与输出：`rg -n "write_face:" --glob "!node_modules" .` → exit 1，零命中（仅有 `pm-orchestrator.ts`/`launcher.py`/测试里的 "write-face" 连字符注释）。本文件的 `write_face` 语义为 `design.md` D-001 草案，非现状。
6. 载体重建：扩展以单文件 bundle 消费（`packages/multi-workers/dist/extensions/agent-team-loop.js`，由 `packages/multi-workers/build-extension.sh` 从 `index.ts` esbuild；产物路径见 `mw.py:4436`、入口见 `mw.py:4452`、构建见 `mw.py:4521`），另 `packages/coding-agent/dist` 为 tsc 产物。插入点改动必须重建两侧，否则现场跑旧逻辑；本轮只确认 bundle 含 `checkBashWriteScopeTarget`（源字符串计数），**未验证 src 与 dist 字节一致性**。
7. `allow-unknown` 的放行面未穷举（沿用 `spec-write-face-safety-20261014.md` §7 第 4 条的边界）。
8. 未取证 worker 进程外写者 / 同 uid 旁路（所有闸一致自述非 sandbox，见 `xkey-gate-guard.ts:45-47`）。

## §6 未覆盖面声明

- 未审 PM/conductor 侧派发闸（AC-001/002/003，属 spec 阶段另一 RQ 与 PM 串行）；本文件只答"运行期插入点"。
- 未审 `read_scope`/`deny_globs` 读面语义（spec §1.4 明确不动）。
- 未审写面 glob 交集算子（RQ-D1，`design-glob-intersection-20261014.md`）。
- 未审跨 key、未审 `.mw/` 其它 key 的运行期实现（只做本仓普通只读检索）。
- 未实测 Windows/POSIX 差异；`isSameOrUnder` / `normalizeForCompare` 平台分支引自源码（`read-scope.ts:89-110`）。

## 上下文来源

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `.../worker/worker-file-tool.ts`、`.../worker/read-scope.ts`、`.../worker/output-writer.ts`
- `.../shared/implementation-gate.ts`、`.../shared/bash-segments.ts`、`.../shared/xkey-gate-guard.ts`、`.../shared/protected-config.ts`、`.../shared/worktree-junction-guard.ts`
- `.../index.ts`、`.../pm/ui-bridge.ts`
- `packages/agent/src/agent-loop.ts`、`packages/coding-agent/src/core/extensions/types.ts`、`.../core/extensions/runner.ts`、`.../core/agent-session.ts`、`.../core/tools/write.ts`、`.../core/tools/edit.ts`
- `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`
- `.agenticdoc/mw-write-face-guard/spec.md`、`design.md`、`evidence/research/spec-write-face-sources-20261014.md`、`evidence/research/spec-write-face-safety-20261014.md`
- `packages/multi-workers/build-extension.sh`、`packages/multi-workers/mw.py`
- 本轮一手 trace：`.agenticdoc/mw-write-face-guard/workers/wfg-rq-d2-runtime-guard/trace.log`（`[WRITE_SCOPE]`/`[TOOL_ERR]` 于 2026-10-13T23:54:19.288Z）

## [VERIFY]

只读脚本实测打印（`python -X utf8` 解析源码文本，无运行期 agent 执行）：

- `allowlist keys = 11`：coding, review, research, roadmap-writer, phase-writer, verifier, reviewer, repair, rag-research, vision, fallback
- `shell roles = 6`：coding, research, phase-writer, repair, vision, fallback
- `writeless roles = 5`：review, research, verifier, reviewer, rag-research
- `guard installed today (shell∩writeless) = 1`：research
- `writable roles = 6`：coding, roadmap-writer, phase-writer, repair, vision, fallback
- `shell∩writable unguarded bash today = 5`：coding, phase-writer, repair, vision, fallback
- `writable∩no-bash = 1`：roadmap-writer
- `index.ts global tool_call guard registrations = 4`：ProtectedConfigGuard, XkeyGateGuard, ImplementationGate, WorktreeJunctionGuard
- `worker-mode tool_call handlers = 2`（`worker-mode.ts:2165` read-scope、`:2218` bash write-scope）
- `extractCommand write-command case labels = 31`
- `bashWriteDenyReason deny categories = 6`：pm-state.md, workers/_workers*, _index.parallel, other key dir / .agenticdoc root, packages/**（`worker-mode.ts:1579`）, .git/**
- `REQUIRED_WRITE_PATTERNS = 19`；`VERBATIM_CORPUS = 36`（must-allow 19 / must-block 14 / contract-cost 3）
- `interceptorCount assertions in mwds-t03 = [1, 0]`
- `write_face: occurrences in repo = 0`（`rg` exit 1）
- `[WRITE_SCOPE] blocked=true` rows in this worker's trace.log = 1（2026-10-13T23:54:19.288Z，只读命令假阻，实例 3；同刻 1 条 `[TOOL_ERR]`）
