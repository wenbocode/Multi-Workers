# 写面数据源现状（RQ-W1 / T-W1）

- Key: mw-write-face-guard
- 任务: `.agenticdoc/mw-write-face-guard/tasks/T-W1-write-face-sources.md`（card_sha256 a6c9483c…）
- 取证范围: 全仓只读（含 `packages/*/dist`、`.agenticdoc/**`、`.mw/`）
- 取证命令形态（三种口径，勿混用）：
  - **G** = `rg -n --no-heading -F TERM --glob '!node_modules' --glob '!.git' --glob '!*.map' .` —— **非隐藏路径**（rg 默认不搜 dotfile/dot-dir，因此 G **不含** `.agenticdoc/`、`.mw/`、`.pi/`）
  - **Gwide** = 同上再加 `--no-ignore --hidden` —— 含 `.agenticdoc/**` 等隐藏路径
  - **P** = 同 G 但路径限定为 `packages/coding-agent/src packages/multi-workers/autopilot packages/multi-workers/launcher.py packages/multi-workers/mw_common.py`（生产代码面）
- 只读声明: 本文件是本次唯一写入；未修改任何生产代码

---

## §0 结论先行

**RQ-W1 答案：今天不存在统一的"worker 允许写哪些路径"机器可读载体。** 存在 **3 个互不相通的 write 面载体 + 1 个只判存在性的散文槽位**，另有 1 个读者只读结构不读内容的契约块：

| # | 载体 | 形态 | 生产端 | 解析端 | 运行期消费端 | 语义 |
|---|------|------|--------|--------|--------------|------|
| W1 | task.md frontmatter `write_scope:` | 单行逗号表 / YAML 块表 | `pm/ui-bridge.ts::renderDefaultWriteScope`（**仅 writeless+shell 角色**，`ui-bridge.ts:2432`、`:2926`） | `worker/worker-mode.ts::parseTaskMd`（`:440-466`） | `worker-mode.ts:2216-2266` bash 写面守卫（**仅 `isShellRole && isWritelessRole`**，config 构造 `:2202-2215`） | "本 worker 自己目录 + key evidence/**" |
| W2 | gate frontmatter v2 `write_scope` | 单行 JSON 数组 | 无生产写入方：`gates.create`（`:457-464`）参数无该字段；本仓 gate 队列目录不存在（0 个 gate 文件） | `autopilot/gates.py:175`（`_JSON_LIST_FIELDS`）→ `:790 optional_json("write_scope")` | `autopilot/conductor.py:6518-6526` `blast_radius ⊆ write_scope` | xkey 授权命题，**不是任务书写面** |
| W3 | 任务卡 envelope 槽位 `写入允许面` / `写入禁止面` | 散文 heading / bullet / 任意命中 | 人或 PM 写卡；缺失时兜底骨架（`dispatch.py:442-443`、`launcher.py:1074-1075`、`pm-orchestrator.ts:773-774`） | `shared/dispatch-card.ts:251-252`（TS）、`launcher.py:622-623`（Python 镜像） | `dispatch-card.ts:457 typeExtrasMissing` / `launcher.py:771 type_extras_missing`：**只判"出现/未出现"，从不解析内容** | 契约完整性，非路径表 |
| W4 | C2 契约块 `<!-- mw-write-surface: v1 -->` | 3 行散文 | `pm/ui-bridge.ts::renderWriteSurfaceContract`（`:1784-1800`）、`applyWriteSurfaceContract`（`:1807-1815`） | `worker-mode.ts::writeSurfaceMarkerState`（`:355-362`） | `worker-mode.ts:2021-2027`：**只判 marker 对结构 ok/malformed，不解析三行内容** | 人读提示 + 渲染漂移审计 |

"写面重叠拒绝"（AC-002）在派发层**完全不存在**：`_workers.parallel` 行 schema 只有 9 列（`mw_common.py:1747-1770`、`shared/worker-store.ts:110`），没有写面载荷；`dispatch.py::dispatch` 与 `pm/ui-bridge.ts::dispatch_worker` 均无任何写面交集判定。

**唯一端到端机器可读的三段式是"读面"**（`read_scope` / `deny_globs`）：渲染 `dispatch.py:857-866` → 解析 `worker-mode.ts:406-431` → 运行期 `read-scope.ts:167-215`。写面若要做机器契约，现有可复用范式就是这一条链路（`spec.md §5` 已如此指向）。

**与上游结论的关系**：`.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-worker-serialization-20260926.md:126` 记录的"`write_scope` / `写面` 在**生产代码零命中**"**已过期**。今天 `write_scope` 在 P 面有 36 次命中 / 7 个文件（见 §1.3），来源是 key `mw-dispatch-settle-gates`（T-02/T-03，2026-10-10/11）落地的 C1/C2/C3 写面契约。该结论仍正确的部分是：**任务书写面机器契约与派发层写面重叠判定确实为零**——但"零命中"本身不再成立。

---

## §1 逐字段穷举（声明处 / 渲染处 / 解析处 / 运行期消费处）

### 1.1 `read_scope`

**计数**：G = 37 文件 / 191 命中；P = 7 文件 / 56 命中。

**声明处**
- `packages/multi-workers/autopilot/dispatch.py:748`（`render_task_md` 形参）
  ```
      read_scope: Sequence[str] = (),
  ```
- `packages/multi-workers/autopilot/dispatch.py:65`（角色表字段）
  ```
      requires_read_scope: bool
  ```
- `packages/multi-workers/autopilot/dispatch.py:83`
  ```
      # L2 gate verdicts: review set + mandatory read_scope (D-106).
  ```
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:313-315`
  ```
  /** read_scope entries (D-106), project-root relative. Present → read
   * containment enabled; absent → zero interception (AC-012 red line). */
  readScope?: string[];
  ```
- `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:47-51`
  ```
  /** Parsed read_scope frontmatter, as enforcement config. */
  export interface ReadScopeConfig {
  	/** Scope entries (root-relative or absolute). A present-but-empty
  	 * list blocks every read-ish call (fail-closed on a misconfigured task).
  	 * null = deny-only mode: a task.md carrying deny_globs but no read_scope
  ```

**渲染处（task.md 头）**
- `packages/multi-workers/autopilot/dispatch.py:857-859`
  ```
      if read_scope:
          lines.append("read_scope:")
          lines.extend(f"  - {item}" for item in read_scope)
  ```
- 调用点 `packages/multi-workers/autopilot/dispatch.py:1118`
  ```
          task_type, prompt, loop=loop, attempt=attempt, read_scope=scope,
  ```
- 展开/去重 `packages/multi-workers/autopilot/dispatch.py:880-921`（`_expand_read_scope`：dual/partition 模式按 game root / partition root 展开并追加 control root、parent root）
- 生产调用样例 `packages/multi-workers/autopilot/conductor.py:1201`、`:1683`、`:2373`、`:2423`、`:2458`、`:2490`、`:2532`、`:2583`
- **card envelope 里没有 `read_scope` 槽位**：`shared/dispatch-card.ts` 全部命中仅为注释（`:1459` 在 status-model）与散文，无 producer 渲染

**解析处**
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:402-414`
  ```
  		// read_scope renders as a YAML block list (dispatch.py render_task_md):
  		// `  - entry` lines after a bare `read_scope:`. Any other line ends the
  		// list. `read_scope:` present-but-empty keeps the field defined — the
  		// interceptor then fails closed (everything out of scope).
  		if (trimmed === "read_scope:") {
  			readScope = [];
  			inReadScopeList = true;
  		} else if (inReadScopeList && !inPhasePrompt) {
  			if (trimmed.startsWith("- ")) {
  				const item = trimmed.slice(2).trim();
  				if (item) readScope?.push(item);
  			} else {
  				inReadScopeList = false;
  			}
  		}
  ```
- 返回 `worker-mode.ts:522`（`readScope,` 进 `TaskMeta`）
- 配置构造 `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:259-271`（`readScopeConfigFromMeta`；两者都缺 → `undefined` = 零拦截）

**运行期消费处**
- `worker-mode.ts:1973-1977`（`applyParentRootUnion(readScopeConfigFromMeta(meta), …)`）
- `worker-mode.ts:2163-2192`（`tool_call` 拦截 `read`/`ls`/`find`/`grep`）
  ```
  	if (readScopeConfig) {
  		const projectRoot = process.cwd(); // launcher spawns workers with cwd = project root (D-106 base)
  		pi.on("tool_call", (event) => {
  			if (
  				event.toolName !== "read" &&
  				event.toolName !== "ls" &&
  				event.toolName !== "find" &&
  				event.toolName !== "grep"
  			) {
  				return undefined;
  			}
  			…
  			const verdict = checkReadScopeCall(projectRoot, readScopeConfig, readScopeState, event.toolName, rawPath);
  			if (verdict.allowed) { … return undefined; }
  			…
  			return { block: true, reason: verdict.reason };
  		});
  	}
  ```
- `read-scope.ts:118-121`（`isWithinScope`）、`:167-215`（`checkReadScopeCall`，rule ∈ `scope|cap-file|cap-byte|deny-glob`）
- 双保险 fail-closed：`worker-mode.ts:665-669`（`origin: conductor` + `type: verifier` + 空 `read_scope` → 拒跑）、`dispatch.py:1055-1059`（派发期同判据）

**live 语料**：423 份 `workers/*/task.md` 中携带 `read_scope:` 头 = **0**（见 §VERIFY）。即代码三段式完整，但本工作树没有一份真实 conductor 任务书写过它。

### 1.2 `deny_globs`

**计数**：G = 40 文件 / 192 命中；P = 7 文件 / 47 命中。

**声明处**
- `packages/multi-workers/autopilot/dispatch.py:749`（`render_task_md` 形参）
  ```
      deny_globs: Sequence[str] = (),
  ```
- `packages/multi-workers/autopilot/dispatch.py:922-928`（默认来源）
  ```
  def _resolve_deny_globs(config: dict, explicit: Sequence[str] | None) -> list[str]:
      """AC-006 generation side: deny globs default from target.yml's
      ignore.deny_globs (any mode — a single-root UE project can still deny
      its DDC); an explicit per-task list (including empty) wins."""
      if explicit is not None:
          return [str(g) for g in explicit]
      return [str(g) for g in config.get("ignore", {}).get("deny_globs", [])]
  ```
- `dispatch.py:974`（`dispatch()` 形参 `deny_globs: Sequence[str] | None = None`）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:317-318`
  ```
  	/** deny_globs entries (mw-dual-workspace AC-006), minimatch dual-basis.
  	 * Present → deny firewall active even without read_scope (deny-only). */
  	denyGlobs?: string[];
  ```
- `read-scope.ts:54-57`
  ```
  	/** deny_globs frontmatter (mw-dual-workspace AC-006): minimatch globs,
  	 * dual-basis matched (see matchedDenyGlob). Deny wins over scope allow. */
  	denyGlobs: string[];
  ```

**渲染处（task.md 头）**
- `packages/multi-workers/autopilot/dispatch.py:864-866`
  ```
      if deny_globs:
          lines.append("deny_globs:")
          lines.extend(f"  - '{item}'" for item in deny_globs)
  ```
- `packages/multi-workers/autopilot/dispatch.py:1075`（`globs = _resolve_deny_globs(config, deny_globs)`）、`:1119`（`deny_globs=globs, …`）
- PM 通道等价渲染 `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts:212-213`
  ```
  function insertDenyGlobs(content: string, denyGlobs: string[]): string {
  	const block = ["deny_globs:", ...denyGlobs.map((g) => `  - '${g}'`)].join("\n");
  ```
  调用点 `:270-271`（`config.ignore.deny_globs.length > 0 && !ownDenyGlobs`）

**解析处**
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:417-431`
  ```
  		// deny_globs renders like read_scope (dispatch.py render_task_md), but
  		// entries are globs — dispatch quotes them (a leading `*` is a YAML
  		// alias marker), so strip one pair of surrounding quotes when present.
  		if (trimmed === "deny_globs:") {
  			denyGlobs = [];
  			inDenyGlobsList = true;
  		} else if (inDenyGlobsList && !inPhasePrompt) {
  			if (trimmed.startsWith("- ")) {
  				let item = trimmed.slice(2).trim();
  				if ((item.startsWith('"') && item.endsWith('"')) || (item.startsWith("'") && item.endsWith("'"))) {
  					item = item.slice(1, -1);
  				}
  				if (item) denyGlobs?.push(item);
  			} else {
  				inDenyGlobsList = false;
  			}
  		}
  ```

**运行期消费处**
- `read-scope.ts:141-166` `matchedDenyGlob`（dual-basis：绝对路径与 root 相对路径各测一次 minimatch；`/**` 尾缀额外允许目录自身）
- `read-scope.ts:175-183`（deny 先于 scope 包含性，rule `deny-glob`）
- 判定原文（`read-scope.ts:135-140`）
  ```
   * Dual-basis deny matching (mw-dual-workspace D-003, minimatch 实测):
   * a deny glob hits when it matches EITHER the normalized absolute path OR
   * the projectRoot-relative path with forward slashes. …
  ```
- 文档/语义声明 `packages/multi-workers/README.md:145`（"`ignore.deny_globs` 作为上下文防火墙（deny 优先于 allow）"）

**live 语料**：423 份 `workers/*/task.md` 中携带 `deny_globs:` 头 = **0**（见 §VERIFY）。

### 1.3 `write_scope`（三个不相通载体）

**计数**：G = 26 文件 / 116 命中；P = 7 文件 / 36 命中。

#### 1.3a task.md frontmatter `write_scope:`（C1）——生产/消费都只覆盖 writeless+shell

**声明处**
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:319-322`
  ```
  	/** write_scope entries (contract C1/T-03), project-root relative. Present →
  	 * the AC-005b bash write surface is narrowed to the intersection with the
  	 * default (own taskDir + `<key>/evidence/**`); absent → default surface. */
  	writeScope?: string[];
  ```
- `worker-mode.ts:756-758`（运行期配置字段）
- `pm/ui-bridge.ts:1777-1779`
  ```
  /** Default `write_scope:` line for a shell role (contract C1): the task's own
   * dir plus the key's evidence tree. Absent for non-shell roles. */
  export function renderDefaultWriteScope(ownerKey: string, taskKey: string): string {
  	return `write_scope: .agenticdoc/${ownerKey}/workers/${taskKey}, .agenticdoc/${ownerKey}/evidence`;
  }
  ```

**渲染处**
- `pm/ui-bridge.ts:1827-1832` `mergeWriteScope`（追加一行；空白值不改字节）
- 唯一注入点 `pm/ui-bridge.ts:2174`（`mergeWriteScope(input.frontmatter, input.writeScope)`，位于 `writeDispatchTaskMd` = 契约 C4 单一写点，`:2149-2188`）
- 两个调用方（**都按 writeless && shell 把关**）
  - `pm/ui-bridge.ts:2431-2432`（`dispatch_worker` 工具）
    ```
    					writeScope:
    						writelessRole && isShellRole(typeField) ? renderDefaultWriteScope(ownerKey, task_key) : undefined,
    ```
  - `pm/ui-bridge.ts:2925-2926`（`/worker` 命令）
- **Python 侧不渲染**：`rg -F write_scope packages/multi-workers/autopilot/dispatch.py` → 未找到（`dispatch.py` 全文无 `write_scope`）。即 conductor 派发的任务书**永远没有 `write_scope:` 头**。

**解析处**
- `worker-mode.ts:434-466`
  ```
  		// write_scope (contract C1, T-02 → T-03): the producer renders the
  		// one-line comma form (`write_scope: a, b`); the read_scope/deny_globs
  		// YAML block-list form is accepted too, so the two consumer paths cannot
  		// drift apart. A present-but-blank value stays defined as [] (fail-closed,
  		// mirroring read_scope); an absent header leaves the field undefined and
  		// the consumer falls back to the default surface.
  		if (trimmed.startsWith("write_scope:")) {
  			const rest = trimmed.slice("write_scope:".length).trim();
  			if (rest) {
  				writeScope = rest
  					.split(",")
  					.map((item) => item.trim())
  					…
  ```
  解析是**无条件**的（任何 type 都会解析 `write_scope:`），返回 `worker-mode.ts:524`。

**运行期消费处（关键缺口）**
- 消费者只有一个，且被角色门控：`worker-mode.ts:2202-2215`
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
  按 `TOOL_ALLOWLISTS`（`worker-mode.ts:73-99`）+ `activeToolsForType`（`:145-148`）、`isShellRole`（`:151`）、`isWritelessRole`（`:158`）计算，**唯一满足 shell 且 writeless 的角色是 `research`**（`research: ["read","find","grep","ls","bash"]`）。`coding` / `repair` / `phase-writer` / `vision` 有 `write`/`edit` → `bashWriteScopeConfig === undefined` → 不建守卫 → 其 `write_scope:` 头**被解析但零消费**。
- 判定原文 `worker-mode.ts:1648-1662`
  ```
  	if (
  		config.writeScope !== undefined &&
  		!config.writeScope.some((entry) => matchesWriteScopeEntry(config, entry, target))
  	) {
  		return {
  			allowed: false,
  			rule: "write-scope",
  			detail: "outside-declared-write-scope",
  			target: rawTarget,
  			reason:
  				`write-scope: blocked bash write to ${rawTarget}: outside the task's declared write_scope ` +
  				`[rule=write-scope]; allowed: ${allowedLabel}`,
  		};
  	}
  ```
  注意判定次序 `worker-mode.ts:1624-1662`：deny 表（绝对优先，`:1624-1636`）→ 默认面（`taskDir` + `<key>/evidence`，`:1637-1647`）→ 再取 `write_scope` **交集**（`:1648-1662`）。`write_scope` 只能**收窄**，永不能放宽（`:1567-1568` 注释："The deny list is checked first and can never be widened by a `write_scope:` header"）。

#### 1.3b gate frontmatter v2 `write_scope`（JSON list）——xkey 授权命题，不是任务书写面

**声明处**
- `packages/multi-workers/autopilot/gates.py:136`（`FRONTMATTER_FIELDS` 白名单）
- `packages/multi-workers/autopilot/gates.py:175`（`_JSON_LIST_FIELDS`）
- `gates.py:291`（dataclass 字段 `write_scope: list[object] | None = None`）
- TS 镜像 `autopilot/status-model.ts:808`、`:885`

**解析处**
- `gates.py:790` `write_scope=optional_json("write_scope"),`（单行 JSON 子串，失败即 `GateFormatError` 失败关闭）
- 语义注释 `gates.py:26-35`（v2 字段清单）

**消费处**
- `packages/multi-workers/autopilot/conductor.py:6514-6526`（`proposition_xkey_authorize`）
  ```
      blast = facts.get("blast_radius")
      scope = facts.get("write_scope")
      if not isinstance(blast, dict) or not isinstance(scope, list) or not scope:
          return _prop_fail("xkey-blast-radius", "blast_radius/write_scope unavailable")
      files = {str(name) for name in (blast.get("files") or [])}
      allowed = {str(name) for name in scope}
      if not files <= allowed:
          return _prop_fail(
              "xkey-blast-radius", f"{sorted(files - allowed)} outside write_scope"
          )
  ```
- 事实装配 `conductor.py:7091`（`"write_scope": gate.write_scope,`）、样例 `:6660`

#### 1.3c 任务卡 envelope 槽位（只判存在性）

- 槽位名与正则 `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:185`、`:251`
  ```
  export const CODING_EXTRA_SECTIONS = ["写入允许面", "写入禁止面", "验收命令", "改动历史"] as const;
  …
  		["写入允许面", /写入允许面|允许写入|允许写|写入范围|写面|write_scope|allow[-_ ]?write/i],
  ```
  → **`write_scope:` 在这里只是"写入允许面槽位出现"的宽正则之一**，与真正的路径表无关。
- Python 镜像 `packages/multi-workers/launcher.py:592`、`:622`
- 判定函数：`dispatch-card.ts:457-484`（`typeExtrasMissing`：`text.includes(item)` → `anyLabelMatches` → heading 命中，三档皆为"存在性"）
- 判定原文 `dispatch-card.ts:469-476`
  ```
   * "Declared" is wide on purpose (heading, bullet/field label, or the canonical
   * item name anywhere in the card): the per-type extras exist to catch an
   * omitted contract, not to police wording (P-03).
   */
  export function typeExtrasMissing(type: string, text: string): string[] {
  ```
- 调用/消费：`pm/ui-bridge.ts:2114`（工具闸门拒绝）、`pm/pm-orchestrator.ts:801`、`:868`、`launcher.py:906`、`:1120`、`:1227`、`:1832`（服务层拒绝）

#### 1.3d C2 契约块 `<!-- mw-write-surface: v1 -->`（只读结构）

- 生成 `pm/ui-bridge.ts:1784-1800`（`renderWriteSurfaceContract` 三行散文；`:1785` 用 `replace(/^write_scope:\s*/, "")` 抽出 scope 文本贴进 prose）+ `:1807-1815`（幂等注入）
- marker 常量 `pm/ui-bridge.ts:1392-1393`；idempotency 正则 `:1520`
- 解析/消费（唯一）`worker-mode.ts:355-362` `writeSurfaceMarkerState`（只数 marker 行 → `absent|ok|malformed`），消费点 `worker-mode.ts:2021-2027`
  ```
  	if (meta.writeSurfaceMarker === "malformed") {
  		appendTrace(
  			meta.taskKey,
  			meta.agenticdocRoot,
  			"[WRITE_SURFACE] contract-section markers malformed (expected exactly one ordered marker pair)",
  		);
  	}
  ```
  → 三行里的 `.agenticdoc/<key>/workers/<task>、evidence` 路径文本**没有任何代码解析**：`rg -n -F "本任务目录下的 worker_file" packages/coding-agent/src` 仅命中 `ui-bridge.ts:1787` 与 `:1788`（渲染端自身），无任何解析端命中。

**live 语料**：423 份 `workers/*/task.md` 中携带 `write_scope:` 头 = **32**；其中 **31** 份为 PM 通道渲染的 `research` 角色任务书（写面守卫真实生效者），另 1 份 `type: coding` 位于 `mw-dispatch-card-gate/evidence/runs/t08-cutover-20261012/fixture/writefile/...`（合成 fixture，且其 C2 文案 `- 允许写：本任务目录下的任何文件` 与当前渲染器 `ui-bridge.ts:1787` 的 `worker_file（progress.md | report.md | report-<slug>.md）` 不一致 → 旧版渲染产物）。非 fixture 的 31 份 100% 为 `type: research`。

### 1.4 `写面`（纯中文散文 token）

**计数**：G = 12 文件 / 26 命中；P = 4 文件 / 10 命中。

- **声明处：无。** 没有任何类型/常量/字段以 `写面` 命名。
- **渲染处（散文 token，非字段）**
  - `pm/ui-bridge.ts:1791-1793`（C2 契约块的"越界后果"行）
    ```
    	const consequence = isShellRole(type)
    		? "运行期 bash 写面守卫 block + [TOOL_ERR] + trace 审计行"
    		: "运行期写面守卫拒绝；回复文本仍会被框架写入 output.md";
    ```
  - `pm/ui-bridge.ts:2134`（工具描述里的能力说明字符串）
- **解析处（唯一机械用途：作为槽位名 `写入允许面` 的正则别名）**
  - `shared/dispatch-card.ts:251`
    ```
    		["写入允许面", /写入允许面|允许写入|允许写|写入范围|写面|write_scope|allow[-_ ]?write/i],
    ```
  - `packages/multi-workers/launcher.py:622`（同正则 Python 镜像）
- **运行期消费处**：无。`写面` 不出现在任何判定分支、trace token 或拒绝码中。
- 其余命中全部在测试/语料/注释：`test_autopilot_xkey_registration.py:128,133`（语料字符串）、`test/suite/mwds-t02-write-intent.test.ts:190,235`、`test/suite/dispatch-card-envelope.test.ts:404,417`、`test/suite/mwds-t21-write-intent-soundness.test.ts:46,77,194`。

### 1.5 `写入允许面`（C1/§1.2 slot name）

**计数**：G = 24 文件 / 55 命中；P = 5 文件 / 13 命中。

**声明处（槽位名单）**
- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:185`
  ```
  export const CODING_EXTRA_SECTIONS = ["写入允许面", "写入禁止面", "验收命令", "改动历史"] as const;
  ```
- `packages/multi-workers/autopilot/dispatch.py:405-409`（`PRODUCER_EXTRA_ITEMS`）
- `packages/multi-workers/launcher.py:592`（Python 镜像）

**渲染处（只渲染"槽位名 + 一句兜底散文"）**
- `dispatch.py:435-440`（缺失时兜底）
  ```
      if item == "写入允许面":
          return (
              f"写入允许面: {artifacts}（本轮产物）；项目源文件的改动面以「要求」段列出的"
              "清单为准，未列出的路径不写。"
          )
  ```
- `launcher.py:1074`、`pm/pm-orchestrator.ts:773`（同义兜底骨架，带 `_ENVELOPE_FALLBACK_AUDIT` 前缀）

**解析处（存在性判定）**
- `shared/dispatch-card.ts:248-256`（`TYPE_EXTRA_PATTERNS.coding[0]`）
- `shared/dispatch-card.ts:457-484`（`typeExtrasMissing`）
- `packages/multi-workers/launcher.py:619-628`、`:771-798`（`type_extras_missing`）

**运行期消费处**
- 工具层：`pm/ui-bridge.ts:2114`（`const missing = [...(envelope.type === "" ? [] : typeExtrasMissing(envelope.type, text)), ...seedItemsMissing(text)];` → 卡不全则拒绝派发、零副作用）
- 服务层：`launcher.py:906`、`:1120`、`:1227`（`_envelope_missing_items` → `classify_envelope_refusal` / `_envelope_refusal`，`:1174-1240`）与 `:1832`（poll 主循环）
- PM 兜底自检：`pm/pm-orchestrator.ts:794-809`、`:867-868`
- **关键限制**：`typeExtrasMissing` 的三档判据（`text.includes(item)` / bullet-field label 正则 / heading 前缀正则）都只回答"这个槽位是否出现"，**从不抽取槽位值里的路径**。因此 `写入允许面: 随便什么文字` 与 `写入允许面: packages/x/**, packages/y/**` 在机器上完全等价。

### 1.6 `写入禁止面`

**计数**：G = 25 文件 / 57 命中；P = 5 文件 / 12 命中。

与 1.5 完全同构（同一声明/渲染/解析/消费链路，另一个槽位）：
- 声明 `dispatch-card.ts:185`、`launcher.py:592`、`dispatch.py:405-409`
- 渲染兜底 `dispatch.py:442-443`
  ```
      if item == "写入禁止面":
          return "写入禁止面: 上述允许面之外的文件一律不写；任务书未声明的路径视为禁止。"
  ```
- 正则 `dispatch-card.ts:252` / `launcher.py:623`
  ```
  		["写入禁止面", /写入禁止面|禁止写入|禁止写|不得写|写入禁区|禁止范围|deny[-_ ]?write|forbid/i],
  ```
- 消费同 1.5；**同样只判存在性，不解析内容**。

### 1.7 `writable`

**计数**：G = 56 文件 / 93 命中；P = 16 文件 / 23 命中（case-sensitive `-F`）；加词边界 + 忽略大小写（`-i -w`）后 20 命中。
**判定：与写面语义无关。** P 面 23 条命中逐条列全（`rg -n -F writable` on P）：
- 流可写性（Node stream 属性，含 `writableLength` 子串）：`coding-agent/src/modes/rpc/rpc-client.ts:554`、`:555`、`src/main.ts:905`、`:908`
- fs 权限/健康语义：`coding-agent/src/config.ts:341`（"the install path is not writable"）、`src/core/tools/edit.ts:79`（"readable and writable"）、`src/utils/photon.ts:94`、`:105`
- 日志/IO 故障容忍（"unwritable" 子串，`-w` 不计）：`multi-workers/autopilot/timeline.py:32`、`:319`
- partition 工作区标签：`multi-workers/mw_common.py:5040`（`Parent root (extended workspace, writable):`）、`coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts:168`（同串）
- 散文/docstring：`multi-workers/mw_common.py:2647`、`multi-workers/launcher.py:860`、`multi-workers/autopilot/conductor.py:7342`（`answerer-writable`）、`multi-workers/autopilot/dispatch.py:891`、`worker/worker-mode.ts:574`、`worker/worker-file-tool.ts:37`（"writable basename set"）、`pm/ui-bridge.ts:315`、`shared/ack-store.ts:89`、`shared/run-store.ts:146`、`shared/xkey-gate-guard.ts:61`、`:98`、`:136`

**没有任何一处是写面字段名、写面判定或写面拒绝码。** G 面 93 命中（含 `dist/**` 与 `examples/**`）同样无写面语义；唯一的"写路径白名单"式命名是示例沙箱的 `allowWrite`（见 §4bis E1）。

### 1.8 `allow_write`

**计数**：G = **0 文件 / 0 命中**；P = **0 / 0**。
命令：`rg -n --no-heading -F "allow_write" --glob '!node_modules' --glob '!.git' --glob '!*.map' .` → 无输出（退出码 1）。
**唯一近名物是另一个语义的 `allow_foreign_write`**（AC-007/T-07 越界写逃生舱，是布尔值不是路径表）：
- 声明 `worker-mode.ts:330-334`
  ```
  	/** AC-007/T-07 escape hatch: task.md `allow_foreign_write: true` (the
  	 * audit-visible declaration T-02 records, also set by the
  	 * `--allow-foreign-write` dispatch flag). `true` is the only value that
  	 * opens the hatch; missing/false/any other value stays fail-closed. */
  	allowForeignWrite?: boolean;
  ```
- 解析 `worker-mode.ts:484-488`、渲染 `pm/ui-bridge.ts:1818-1823`（`mergeAllowForeignWrite`）
- 消费 `worker-mode.ts:2243-2251`（仅放宽非 `deny` 规则的目标）

---

## §2 机器可读性三态判定

判据口径：
- **是**：生产代码解析出**内容**（路径列表/glob），并在运行期或派发期按内容做判定。
- **仅存在性**：生产代码只判"该 token 是否出现"，不解析内容。
- **仅散文**：仅出现在人类可读文本 / 注释 / 测试语料，无任何生产判定分支。

| 字段/载体 | 三态 | 依据 | 内容级消费点 |
|---|---|---|---|
| `read_scope` | **是** | 渲染 `dispatch.py:857-859`；解析 `worker-mode.ts:406-414`；消费 `read-scope.ts:167-215` | 包含性判定（`isWithinScope`）+ 全部拒绝 reason |
| `deny_globs` | **是** | 渲染 `dispatch.py:864-866` / `task-dispatcher.ts:212-213`；解析 `worker-mode.ts:421-431`；消费 `read-scope.ts:141-166` | minimatch dual-basis deny |
| `write_scope`（task.md C1） | **是（角色受限）** | 渲染 `ui-bridge.ts:2174`（仅 writeless+shell）；解析 `worker-mode.ts:440-466`（无条件）；消费 `worker-mode.ts:2216-2266`（**仅 writeless+shell**） | `outside-declared-write-scope` block。**对 `coding`/`repair`/`phase-writer`/`vision` 解析后零消费** |
| `write_scope`（gate v2） | **是** | `gates.py:175,790` → `conductor.py:6518-6526` | 集合包含 `files ⊆ write_scope` |
| `write_scope`（卡 envelope） | **仅存在性** | 正则别名 `dispatch-card.ts:251` / `launcher.py:622` + `typeExtrasMissing` | 无 |
| `写入允许面` | **仅存在性** | `dispatch-card.ts:457-484`、`launcher.py:771-798` | 无（只判出现，不抽值） |
| `写入禁止面` | **仅存在性** | 同上 | 无 |
| `写面` | **仅散文** | 10 次 P 命中全部是 C2/工具描述字符串 + 正则别名 + 注释 | 无 |
| `writable` | **仅散文** | §1.7 逐条分类，无写面语义 | 无 |
| `allow_write` | **未找到**（字段不存在） | G/P 均 0 命中 | 无 |
| `mw-write-surface` 契约块路径文本 | **仅散文**（结构可判） | `worker-mode.ts:355-362` 只数 marker 行 | 无（不解析三行内容） |

---

## §3 任务书头部字段全集（worker 模式实际读取）

单一解析入口：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts::parseTaskMd`（`:364-535`），全文按行扫描（**不是** header-region 限定），仅 `type:` 走共享单源。

| 头字段 | 解析函数 file:line | 判定原文（关键分支） | 运行期用途 |
|---|---|---|---|
| `type:` | `shared/task-frontmatter.ts::readTaskType` `:141-158`（由 `worker-mode.ts:368` 调用） | `if (line.startsWith(TYPE_PREFIX) && HEADER_KEY_RE.test(line))` … 只取 header region 首个（`regionFromLines` `:95-108` + `extractTaskHeader` `:109-112`）；body 值永不返回（`source: "body"` → `type: undefined`） | 工具白名单、`dispatchRefusal`、envelope extras |
| `phase:` | `worker-mode.ts:390-393` | `if (trimmed.startsWith("phase:"))` | `phases` / phase 轴（另有 `pm/task-dispatcher.ts:122 readTaskHeaderScalar(content, "phase")`） |
| `timeout:` | `worker-mode.ts:394-397` | `const v = Number(trimmed.slice("timeout:".length).trim()); if (Number.isFinite(v) && v > 0) timeoutMin = v;` | `resolveBudgetMs`（`:212-214`，task.md > `PI_WORKER_TIMEOUT_MS` > 60m） |
| `origin:` | `worker-mode.ts:398-400` | `if (trimmed.startsWith("origin:")) origin = trimmed.slice(…).trim();` | `dispatchRefusal` 门（`origin: conductor` 才启用 fail-closed 双保险） |
| `images:` | `worker-mode.ts:401` | `if (trimmed.startsWith("images:")) images = trimmed.slice(…).trim() === "yes";` | `session_start` 图像能力 backstop（`:2040` 与 `:2061`） |
| `read_scope:` | `worker-mode.ts:406-414` | `if (trimmed === "read_scope:")` → 后继 `- ` 行为列表项；其他行终止 | `readScopeConfigFromMeta` → 读面拦截 |
| `deny_globs:` | `worker-mode.ts:421-431` | `if (trimmed === "deny_globs:")` → 同上 + 去一对引号 | 读面 deny 防火墙 |
| `write_scope:` | `worker-mode.ts:440-466` | `if (trimmed.startsWith("write_scope:"))`，支持单行逗号表 + YAML 块表 | **仅 writeless+shell**：bash 写面收窄 |
| `l2_read_file_cap:` | `worker-mode.ts:468-471` | `if (trimmed.startsWith("l2_read_file_cap:")) … v > 0` | `ReadScopeConfig.fileCap`（默认 8，`read-scope.ts:33`） |
| `l2_read_byte_cap:` | `worker-mode.ts:472-475` | `if (trimmed.startsWith("l2_read_byte_cap:")) … v > 0` | `ReadScopeConfig.byteCap`（默认 65536，`read-scope.ts:34`） |
| `rag_chat_budget:` | `worker-mode.ts:476-479`（常量 `rag/tools.ts:60`） | `if (trimmed.startsWith(RAG_CHAT_BUDGET_HEADER))` | RAG 预算 |
| `rag_time_budget_s:` | `worker-mode.ts:480-483`（常量 `rag/tools.ts:61`） | `if (trimmed.startsWith(RAG_TIME_BUDGET_HEADER))` | RAG 预算 |
| `allow_foreign_write:` | `worker-mode.ts:484-488` | `allowForeignWrite = trimmed.slice(…).trim().toLowerCase() === "true";` | 越界写逃生舱（仅放宽非 deny 规则） |
| `- name:`（phase prompt 块） | `worker-mode.ts:489-499` | `if (trimmed.startsWith("- name:"))` | `phases` 数组（非 header 字段） |
| `<!-- mw-write-surface: v1 -->`（全文 marker，非 header 字段） | `worker-mode.ts:355-362`（`writeSurfaceMarkerState`） | `lines.filter((line) => line === WRITE_SURFACE_MARKER).length` → `absent/ok/malformed` | `[WRITE_SURFACE]` 审计行（仅 malformed） |

**被渲染但 worker 模式不读的 header**（读方为 Python 服务层 / PM）：
- `model:` — `packages/multi-workers/launcher.py::_read_task_md_fields` `:179-204`（`re.search(r"^model:[ \t]*(\S+)[ \t\r]*$", …, re.MULTILINE)`）
- `card_path:` — `launcher.py:640` `_ENVELOPE_CARD_PATH_RE = re.compile(r"^card_path:[ \t]*\S", re.MULTILINE)`（消费 `:825`）
- `card_sha256:` — 渲染 `ui-bridge.ts:2033` / `dispatch.py` card 分支；无独立解析器（`shared/card-digest.ts` 只在渲染时算）
- `envelope_producer:` — `launcher.py:934-938`、`:983`、`:993`
- `loop:` / `attempt:` — 仅 `dispatch.py:852-854` 渲染，无消费者（`rg -n "^loop:|^attempt:"` 在 src 中无解析分支）

**live 语料头字段分布**（423 份 `workers/*/task.md`，实测见 §VERIFY）：`type` 422、`write_scope` 32、`images` 25、`model` 17、`phase` 55、`card_path`/`card_sha256` 64、`envelope_producer` 65、`timeout` 2、`origin` 1、`loop` 1、`attempt` 1；**`read_scope` / `deny_globs` / `l2_read_file_cap` / `l2_read_byte_cap` / `rag_chat_budget` / `rag_time_budget_s` / `allow_foreign_write` 均为 0**。

---

## §4 运行期写拦截现状

三个模块的拦截对象、匹配方式与"写在写面之外"是否命中：

### 4.1 `worker/worker-file-tool.ts` —— 只放行 basename，不认写面

- 拦截对象：`worker_file` 工具的 `file` 参数（**basename only**）。
- 匹配方式：`worker-file-tool.ts:42`
  ```
  export const WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/;
  ```
  判定原文 `:56-70`
  ```
  export function writeWorkerFile(
  	taskDir: string,
  	file: string,
  	content: string,
  	mode: WorkerFileMode,
  ): { ok: true; path: string; bytes: number } | { ok: false; reason: string } {
  	if (!isAllowedWorkerFile(file)) {
  		return { ok: false, reason: `file name not allowed: ${JSON.stringify(file)}` };
  	}
  	const bytes = Buffer.byteLength(content, "utf8");
  	if (bytes > WORKER_FILE_MAX_BYTES) {
  ```
  写入目标恒为 `path.join(taskDir, file)`（`:71-77`）——**taskDir 是调用方传入的 worker 自己目录，`write_scope` 不参与**。
- 对"写在写面之外"：**结构性不命中**。路径解析根本不存在（模块 docstring `:4-7`：`no path parsing exists, so task.md, trace.log, …, and every path variant (../x.md, a/b.md, C:\abs\x.md, \\unc\share\x.md) are rejected by one regex`）。任何带目录成分的目标被同一 regex 拒，而能通过的目标必然落在 `taskDir` 内 = 写面子集。

### 4.2 `worker/read-scope.ts` —— 只拦读，写侧零命中

- 拦截对象（由 `worker-mode.ts:2163-2172` 的 tool_call 门控）：`read` / `ls` / `find` / `grep`。`write` / `edit` / `bash` **不在其中**。
- 匹配方式：
  - deny：`matchedDenyGlob`（`read-scope.ts:141-166`），`minimatch(abs, glob) || minimatch(rel, glob)`，`/**` 尾缀额外匹配目录自身
  - 包含性：`isWithinScope`（`:118-121`）+ `normalizeForCompare`（`:100-116`，`path.resolve` → `fs.realpathSync`，缺失尾部回挂最近存在祖先的 realpath）→ `isSameOrUnder`（`:89-93`，段边界 + win32 小写）
  - 上限：`cap-file` / `cap-byte`（`:194-215`）
- 对"写在写面之外"：**未命中**（写入类工具不经过本模块；docstring `:4-5` 明确作用域是 "every read/ls/find/grep call"）。

### 4.3 `shared/implementation-gate.ts` —— 拦"无 key 的代码路径写"，不拦写面

- 拦截对象：`write` / `edit` / `bash`（`registerImplementationGate`，`:510-521`；`gateDecision` `:436-468`）
  ```
  	if (toolName !== "write" && toolName !== "edit" && toolName !== "bash") {
  		return { blocked: false, basis: "not-gated-tool" };
  	}
  ```
- 匹配方式（判据是**路径类别 + AgenticTask 授权**，不是写面）：
  - 代码路径判据 `isCodePath`（`:160-162`）→ `codePathRel`（`:140-145`）/ `isCodePathAbs`（`:147-157`）：`<root>/packages/` 下，扩展名 `.ts/.tsx/.js/.cjs/.mjs/.py`，排除 `node_modules/dist/.tmp` 段
  - bash 侧只查写结构目标：`WRITE_VERBS = new Set(["tee","cp","mv","rm","sed"])`（`:80`）+ `checkBashWriteTarget`（`:362-385`，redirect target 与 `tee/cp/mv/rm/sed -i` 操作数）
  - 放行三条件（`:35-42` docstring + `:477-486` 实现）：
    ```
    	if (hasActiveKeyClaim(root, currentClaimId())) {
    		return { blocked: false, basis: "claim", target: targets[0] };
    	}
    	const workerTask = env[ENV_WORKER_TASK];
    	if (typeof workerTask === "string" && workerTask !== "") {
    		return { blocked: false, basis: "worker-env", target: targets[0] };
    	}
    ```
- 对"写在写面之外"：**未命中**。派发 worker 进程必然带 `PI_WORKER_TASK`（`ENV_WORKER_TASK` 常量 `:70`），因此 `basis: "worker-env"` 直接放行——**任何** `packages/**` 代码路径写都不再受该门约束，与任务书 `write_scope` 无关。

### 4.4 写侧拦截汇总（"写在写面之外"能否被拦）

| 角色 | 写通道 | 运行期是否检查写面 | 结论 |
|---|---|---|---|
| `research`（shell + writeless） | `worker_file`（basename 白名单）+ `bash`（AC-005b 守卫） | **是**：`checkBashWriteScopeTarget` 三段（deny 表 → 默认面 `taskDir` + `<key>/evidence` → `write_scope` 交集），`worker-mode.ts:1606-1665` | 写面之外 bash 写 → `rule=write-scope` block + trace + `[WRITE_SCOPE_SUMMARY]` |
| `coding` / `repair` / `phase-writer` / `vision` | `write` / `edit` / `bash`（无条件） | **否**：`bashWriteScopeConfig` 因 `isWritelessRole` 为假而 `undefined`（`:2202-2215`） | 写面之外写**不被任何运行期守卫拦**；仅 `implementation-gate` 的 `packages/**` 代码路径门在无 key 时拦，且被 `PI_WORKER_TASK` 放行 |
| `review` / `verifier` / `reviewer` / `roadmap-writer` | `worker_file` 或无 bash | **否**（无 shell ⇒ 无 bash 守卫） | 同上 |

---

## §4bis 追加发现（任务书未列出，但属"写面"概念族）

### E1 `filesystem.allowWrite` / `filesystem.denyWrite`（pi 示例 sandbox 扩展，非生产接线）

- 位置：`packages/coding-agent/examples/extensions/sandbox/index.ts:26`、`:74`、`:275`、`:315`
  ```
  *   "filesystem": {
  *     "denyRead": ["~/.ssh", "~/.aws"],
  *     "allowWrite": [".", "/tmp"],
  *     "denyWrite": [".env"]
  …
  	filesystem: {
  		denyRead: ["~/.ssh", "~/.aws", "~/.gnupg"],
  		allowWrite: [".", "/tmp"],
  		denyWrite: [".env", ".env.*", "*.pem", "*.key"],
  ```
- 形态：JSON 配置（`~/.pi/agent/extensions/sandbox.json` 与 `PROJECT/.pi/sandbox.json` 合并），OS 级强制（`@anthropic-ai/sandbox-runtime`）
- **是否接线到 worker/dispatch：否。** 证据（实测计数）：
  - `SandboxManager` 在 example 之外引用 = **0**
  - 仓库内 `sandbox.json` 文件 = **0**（`.pi/` 下无该文件；`.pi/extensions/` 只有 4 个无关扩展）
  - `allowWrite` 全仓 = 4 次（全部在 example 文件内）
- 意义：这是本仓库里**唯一**形态上"机器可读写路径白名单"的既有实现，可作为未来 `write_scope` 语义（glob / 相对根 / deny 优先 / OS 级兜底）的参照物；但今天与 `agent-team-loop` 的写面链路**零耦合**，不计入 W1–W4。

### E2 `blast_radius`（gate v2 配套字段）

`gates.py:292`（`blast_radius: dict[str, object] | None`）+ `conductor.py:6518-6526`：与 gate 的 `write_scope` 成对出现，命题要求 `blast_radius.files` 是 `write_scope` 的子集。它描述**已发生的写**，不是**允许的写**，语义与任务书写面正交（是事后证据 vs 事前授权）。

### E3 运行期观察：AC-005b 写面守卫写路径误 block（本次会话 3 次，实测）

本次取证期间，AC-005b bash 写面守卫（`worker-mode.ts:2216-2266`）对一条**目的就是写本证据文件**的 bash 命令返回了 block。原始 trace 行（`workers/wfg-rq1-write-face-sources/trace.log:266`）：

```
[WRITE_SCOPE] 2026-10-13T17:17:33.570Z write-scope blocked=true rule=scope detail=outside-allowed-surface pattern=redirect target=--glob cmd=cd H:\git\Multi-Workers $path = ".agenticdoc/…/spec-write-face-sources-20261014.md" $enc = New-Object System.Text.UTF8Encoding($false) $part = @' --- ## §4bis 追加发现（…
[TOOL_ERR] 2026-10-13T17:17:33.570Z bash write-scope: blocked bash write to --glob: outside the worker write surface [rule=scope]; allowed: H:\git\…\wfg-rq1-write-face-sources or H:\git\…\evidence
```

- 提取出的"写目标"是 `--glob`，命中 pattern=`redirect`；**真实写入路径（`evidence/research/spec-write-face-sources-20261014.md`）在 write_scope 之内**，命令本身没有任何真实的重定向。
- 触发源：命令载荷文本里出现的字面量 `<term> --glob ...`（本人在 [VERIFY] 复算命令中把参数位写成尖括号占位符）。
- 最小复现（实测，本 shell 中直接执行即被 block）：
  ```
  $ Write-Output a <term> --glob x
  write-scope: blocked bash write to --glob: outside the worker write surface [rule=scope]; allowed: …\wfg-rq1-write-face-sources or …\evidence
  ```
  即：只要命令文本出现 `<W> --arg`（右尖括号后紧跟一个词），提取器就把 `--arg` 当成 redirect 目标。对照实验 `Write-Output "probe: <term> --glob '!x' done"`（整体在双引号内）**未被 block** —— 说明判定对引号状态敏感，而 PowerShell here-string（`@'…'@`）的引号状态会让载荷文本中的右尖括号被当作活跃操作符。
- 与设计契约的偏差：该守卫的 P1 契约是"失败模式是 MISS（漏判），不是 false block"（`worker-mode.ts:717-722` 注释："Tier P1 (design DD-03): the failure mode is a MISS — an exotic write slips through — never a false block"）。本次是一次**误 block**，对"research worker 需要在证据文档里引用含重定向符的 shell 片段"这一真实场景有直接代价（本次靠改写文本绕开，且本段插入时**重现了同一次误 block**）。
- 计数（本次会话结束时实测）：`trace.log` 中 `[WRITE_SCOPE]` 行 = **3 条 blocked=true**，全部由"写入载荷文本含尖括号占位符/重定向符"触发（1 条首次事件 + 2 条本段落盘尝试）；其余 `[TOOL_ERR]` 行均为 `rg` 无命中退出码 1 / PowerShell 语法错误，非守卫 block。稳定 repro：`Write-Output a <term> --glob x`。

---

## §5 残留与未验证

**R1（已知，非本次范围）** `packages/*/dist/**` 与 `src` 的行为等价性未逐行比对。dist 仅作为"命中位置"引用（例：`packages/multi-workers/dist/extensions/agent-team-loop.js:18853` 含 `outside the task's declared write_scope` 拒绝文案，dist 与 src 一致但未 diff 证明）。

**R2（已验证为否，记录判据）** 是否存在"绕过 PM 门控、在非 research 任务书上写 `write_scope:`"的生产路径：`pm/task-dispatcher.ts` 只插入 `deny_globs`（`:212-213`、`:270-271`），全文无 `write_scope` 写入；`dispatch.py` 零命中（见 RW1-07）。故 32 份 live `write_scope` 中唯一的 `type: coding` 只能是历史/合成产物（已定位为 fixture）。

**R3（部分未验证）** gate v2 `write_scope` 是否还有 `mw doctor` / roadmap / console 侧消费：`rg -n -F write_scope packages/multi-workers/launcher.py packages/multi-workers/mw_common.py` = **0**；`rg -n -F write_scope packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` = 2（`:808`、`:885`，均在字段名集合里，属"识别即保留"，未发现值级消费）。gate 队列目录 `<project>/.agenticdoc/_autopilot/gates/` 在本仓**不存在**（`gates.py:5` 定义该路径；实测 0 个 gate 文件，`.agenticdoc/_autopilot/` 只有 `auto-decisions.jsonl` 与 `timeline.jsonl`），故 live gate `write_scope` 样本 = **0**；`gates.create`（`:457-464`）构造新 gate 的参数表也不含 `write_scope`（只能由人/流程事后追加 v2 字段）。

**R4（口径说明，非缺陷）** 中文词计数用 `-F` 字面匹配，故 `写面`=26 的计数**包含** `写入允许面`/`写入禁止面` 内的子串出现（substring）。逐条引用的位置已人工去重，但计数口径为子串命中。

**R5（未验证）** `typeExtrasMissing` 的宽判据在**真实卡片语料**上的误判率未复算（`dispatch-card.ts:24` 声称以宽判据避免过阻，本任务未取得该复算证据）。

**R6（未验证）** 未运行任何测试套件；本文件全部结论为静态读取 + grep 计数，无运行期实测（无 worker 进程被启动）。

---

## §6 未覆盖面声明

以下**本次未覆盖**，不得据本文件推断：

1. `packages/*/dist/**` 与 `src` 的字节级等价性（R1）。
2. `packages/coding-agent/test/**`、`packages/multi-workers/test*/` 的断言语义；测试文件只作为"命中位置"引用，未评判其覆盖是否充分。
3. 其它 key 的 `.agenticdoc/**` 文档/证据；除 §3 的 live 语料统计外未逐个审计。
4. `mw doctor` / 队列行展示层 / `mw.py` 命令行是否有写面展示面（本次未 grep doctor 的全部输出面与 CLI 帮助）。
5. 外部工具/平台对 task.md `write_scope:`（若有）的消费。
6. `allow_write` 的其它拼写变体：本次按任务书字面量 grep（0 命中），另测了 `allowWrite`（4，全在 example）、`allow-write`（0）、`allowwrite`（0）、`writableScope`（0）。
7. PM 通道与 conductor 通道**同时**在一次派发中出现的写面合并语义（两条通道各自独立，未做交叉语料对照）。
8. 写面 glob 交集判定语义（`**` / 大小写 / Windows 分隔符）——**今天不存在该判定**，故无可审计对象；这是 `spec.md` 风险 1 的待建面。

---

## §7 [VERIFY]（数值实测打印）

```
[VERIFY] RW1-01 term_hits_G: read_scope=191 deny_globs=192 write_scope=116 写面=26 写入允许面=55 写入禁止面=57 writable=93 allow_write=0
          cmd: rg -n --no-heading -F TERM --glob '!node_modules' --glob '!.git' --glob '!*.map' .
          (G = 非隐藏路径口径；不含 .agenticdoc)
[VERIFY] RW1-01b term_hits_Gwide (加 --no-ignore --hidden): read_scope=889 write_scope=751
          (差额来自 .agenticdoc/** 的历史语料与本次各 worker 证据文件)
[VERIFY] RW1-02 term_hits_P: read_scope=56 deny_globs=47 write_scope=36 写面=10 写入允许面=13 写入禁止面=12 writable=23 writable_iw=20 allow_write=0
          cmd: 同 RW1-01，路径限定 packages/coding-agent/src packages/multi-workers/autopilot packages/multi-workers/launcher.py packages/multi-workers/mw_common.py
[VERIFY] RW1-03 task_md_total=423 (workers/*/task.md in .agenticdoc)
[VERIFY] RW1-04 task_md_headers: type=422 phase=55 timeout=2 origin=1 images=25 read_scope=0 deny_globs=0 write_scope=32
          l2_read_file_cap=0 l2_read_byte_cap=0 rag_chat_budget=0 rag_time_budget_s=0 allow_foreign_write=0
          model=17 loop=1 attempt=1 card_path=64 card_sha256=64 envelope_producer=65
[VERIFY] RW1-05 workers_parallel_rows=419 column_histogram=8cols:361 9cols:58 (no write-face column)
[VERIFY] RW1-06 write_scope producer gate: ui-bridge.ts:2432 + :2926 both `writelessRole && isShellRole(typeField)`
          TOOL_ALLOWLISTS roles satisfying shell(has bash) AND writeless(no write/edit) = 1 (research)
[VERIFY] RW1-07 dispatch_py_write_scope_hits=0 (conductor task.md never carries write_scope)
[VERIFY] RW1-08 read_scope interceptor tool names=4 (worker-mode.ts:2167-2170 read/ls/find/grep); bash write guard sites=1 (worker-mode.ts:2219)
[VERIFY] RW1-09 write_scope live task.md by type: non-fixture=31 (all type: research); fixture=1 (type: coding)
[VERIFY] RW1-10 write_scope runtime rule sites=1 (worker-mode.ts:1648-1662, rule=write-scope); gate-v2 consume sites=1 (conductor.py:6518-6526)
[VERIFY] RW1-11 gate v2 write_scope readers outside gates.py/conductor.py: launcher.py=0 mw_common.py=0; status-model.ts=2 (field-name sets only)
[VERIFY] RW1-12 sandbox example: allowWrite hits=4 (all in examples/extensions/sandbox/index.ts); SandboxManager refs outside example=0; sandbox.json files in repo=0
[VERIFY] RW1-13 allow_write=0; allowWrite=4(repo-wide, example only); allow-write=0; allowwrite=0; writableScope=0
[VERIFY] RW1-14 implementation-gate pass-on-worker: implementation-gate.ts:466-469 returns basis="worker-env" whenever PI_WORKER_TASK is non-empty
[VERIFY] RW1-15 gate queue: .agenticdoc/_autopilot/gates/ files=0 (.agenticdoc/_autopilot/ contains only auto-decisions.jsonl, timeline.jsonl); gates.create signature :457-464 has no write_scope param
[VERIFY] RW1-16 AC-005b guard false positive (this session): trace [WRITE_SCOPE] blocked=true lines=3, all with pattern=redirect target=--glob; repro `Write-Output a <term> --glob x` blocks. Guard P1 contract (worker-mode.ts:717-722) says the failure mode must never be a false block.
```

**[VERIFY] 复算命令（逐行可复现）**

```bash
rg -n --no-heading -F read_scope --glob '!node_modules' --glob '!.git' --glob '!*.map' . | wc -l
rg -l --no-ignore --hidden --no-heading '^write_scope:' .agenticdoc | wc -l
rg -l --no-ignore --hidden --no-heading '^read_scope:' .agenticdoc | wc -l
rg -l --no-ignore --hidden --no-heading '^deny_globs:' .agenticdoc | wc -l
rg -n --no-heading -F write_scope packages/multi-workers/autopilot/dispatch.py        # 空（0）
rg -n --no-heading -e 'isShellRole\(meta.type\) && isWritelessRole\(meta.type\)' packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
```