# RQ-2 调研：工具层 guard 与 mw 侧实现接缝

- key: `mw-worktree-junction-guard`
- worker: `wjg-rq2-guard-seams`
- type: research · 纯只读（未改任何生产文件；未执行任何破坏性 git 命令；未建 worktree）
- 调研日期: 2026-10-09
- 唯一产出: `.agenticdoc/mw-worktree-junction-guard/evidence/research/spec-guard-and-mw-seams-20261009.md`
- 相关事实基线（可直接引用）: `.agenticdoc/mw-workspace-incident-probe/evidence/{in1-junction-incident-20261009.md,in2-file-vanish-incident-20261009.md,incidents-timeline-20261009.md}`

结论全部附 `文件:行号` 与原文摘录；未找到的写「未找到」，不用推测补洞。

---

## 0. 结论摘要

| # | 问题 | 结论 |
|---|---|---|
| 1 | guard 实现在哪 | TS 侧 `packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts`，注册函数 `registerProtectedConfigGuard(pi)`（`:247-274`），注册点 `index.ts:42`（`activate()` 内、双加载 flag 之后、PM/Worker 模式分支之前 → 三模式全覆盖）。匹配是**文本启发式正则**，不是 AST；bash 侧 `checkProtectedBashCommand`（`:191-222`）。 |
| 2 | 拦截点 | Extension API 的 `pi.on("tool_call", handler)`（`types.ts:1236`），返回 `ToolCallEventResult = { block?: boolean; reason?: string }`（`types.ts:1071-1074`）。**没有结构化错误码**，只有 `block + reason` 字符串。`event.input` 可原地改写（命令改写）；`block` 在同一事件的多 handler 链上**短路**（`runner.ts:945-947`）。 |
| 3 | 报错文本规范 | `<guard-id>: blocked <tool/命令类别> (<命中引用>) with <写构造>. <GUARD_EXPLANATION>`；`GUARD_EXPLANATION` 固定四段：保护对象/共享范围 → 为什么危险（引事故）→ 读放行 → 正确做法。 |
| 4 | Python 侧接缝 | `mw.py:_parse_args`（`:5324-5659`）argparse `sub.add_subparsers(dest="subcommand", required=True)` + 每个子命令 `sub.add_parser`，再在 `if __name__` 的 `dispatch` dict（`:5639-5658`）映射到 `cmd_*`。doctor 挂载点 = `mw_common.doctor_report`（`:2957-2996`）注册 `_doctor_*` 段 + `_doctor_issues`（`:2780`）产出 issue + `format_doctor_text`（`:2999`）渲染文本（或 `mw.py cmd_doctor` 额外 `print`，`:530-532`）。 |
| 5 | 探测原语 | **仓库内没有**任何 junction/reparse point 工具函数或测试助手（`packages/**` 生产源码实测 0 命中）→ **需新建**。操作系统原语可用：Python `os.path.isjunction`（3.12+，本机 3.14.3 = True）、`os.lstat().st_file_attributes` / `.st_reparse_tag`、`stat.IO_REPARSE_TAG_MOUNT_POINT`。可复用的命令解析件：`implementation-gate.ts` 的 `parseBashSegments`（私有，`:361`）与导出的 `checkBashWriteTarget`（`:612`）。 |
| 6 | 测试基线 | TS: `test/extensions/agent-team-loop-protected-config.test.ts`（纯函数，11 tests）+ `test/suite/xkey-gate-guard-coverage.test.ts`（**真实 tool_call 派发**，含 faux provider + `BashOperations` 记录器 + env test hook）。Python: `test_doctor_gates.py`（doctor 段/issue/exit code + `capsys`）、`test_protected_config.py`、`test_rag_cli.py`（CLI 子命令 + `subprocess` 真退出码）。 |

---

## 1. guard 的实现在哪（Q1）

### 1.1 文件与函数

`packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts`（全文 274 行）。关键符号：

- `PROTECTED_CONFIG_FILES`（`:43`）：
  ```ts
  const PROTECTED_CONFIG_FILES = ["auth.json", "models.json", "settings.json", "oauth.json"] as const;
  ```
- `GUARD_EXPLANATION`（`:51-57`）— 见 §3。
- `resolveAgentDir(env)`（`:96-102` 附近；env 覆盖 `PI_CODING_AGENT_DIR`，否则 `~/.pi/agent`）。
- `isProtectedConfigPath(agentDir, rawPath, cwd)`（`:111-115`）：write/edit 路径判定。
- `BashGuardVerdict`（`:177-184`）与 `checkProtectedBashCommand(agentDir, command)`（`:191-222`）：bash 命令判定。
- `recordProtectedBlockTrace(toolName, detail, taskPathEnv)`（`:224-241`）：worker 模式把一条 `[PROTECTED_CONFIG]` 追加到 `dirname(PI_WORKER_TASK)/trace.log`。
- `registerProtectedConfigGuard(pi)`（`:247-274`）：唯一的注册入口。

### 1.2 注册点（扩展名 / 工具名 / 三模式覆盖）

`packages/coding-agent/src/extensions/agent-team-loop/index.ts:42`：

```ts
	// Cross-window config guard (2026-09-15 incident: a session cleared
	// ~/.pi/agent/auth.json and every live window lost its credentials).
	// Registered in EVERY mode — PM, worker, and plain interactive windows —
	// after the double-load flag so a duplicate bundle copy cannot double-
	// register the listener. Hard block on write/edit/bash targeting the
	// protected agent config; reads pass through.
	registerProtectedConfigGuard(pi);
```

位置语义（`index.ts`）：`:36-40` 为同进程双 bundle 防重入 flag（`ACTIVATION_FLAG`），`:42` 注册 protected-config，`:49` 注册 `registerXkeyGateGuard`，`:59` 注册 `registerImplementationGate`，全部在 `:61` 的 `if (process.env.PI_WORKER_TASK)` 模式分支**之前** ⇒ PM / Worker / 普通交互三模式全覆盖。三个 `register*(pi)` 调用实测 = 3。

工具名覆盖（`protected-config.ts:249-271`）：仅 `"write"` / `"edit"`（判 `event.input.path`）与 `"bash"`（判 `event.input.command`）；其余（含全部读类）一律 `return undefined` 放行。

### 1.3 匹配方式 = 文本启发式，不是 AST

- write/edit：`path.resolve(cwd, expandTildePath(rawPath))` 后与受保护集合**折叠比较**（Windows 下 `fold` 即 `toLowerCase`，`:60-62`）——路径相等判定（`:111-114`）。
- bash：先做引用展开 `expandCommandReferences`（`~`、`$HOME`、`${HOME}`、`%USERPROFILE%`、`$env:USERPROFILE`、`PI_CODING_AGENT_DIR` 各拼写，`:117-134`），再 `toForwardSlashes(fold(...))` 得扫描文本；然后 fail-closed：**命中受保护引用 + 任一写构造**即 block（`:191-216`）。写构造正则集合：`WRITE_VERB_RE`、`POWERSHELL_WRITE_RE`、`SED_IN_PLACE_RE`、`FIND_WRITE_RE`、`REDIRECT_RE`、内联代码 `INLINE_CODE_RE` + `INLINE_WRITE_MARKER_RE`（`:136-174`）。
- 模块自述边界（`:32-33`）：`"This is a text-level heuristic, not a sandbox:"`。

### 1.4 如何阻止执行并生成报错（block 机制全景）

扩展返回 `{ block: true, reason }`，pi 核心的短路链（全部实测行号）：

1. `packages/coding-agent/src/core/extensions/runner.ts:932-953` `emitToolCall`——同一事件的所有 handler 顺序 `await`；`runner.ts:945-947` 命中 `result.block` 立即 `return`（短路，后续 handler 不再执行）：
   ```ts
   				if (handlerResult) {
   					result = handlerResult as ToolCallEventResult;
   					if (result.block) {
   						return result;
   					}
   				}
   ```
2. `packages/coding-agent/src/core/agent-session.ts:480-498` `_installAgentToolHooks`——把 `agent.beforeToolCall` 接到 `runner.emitToolCall`：
   ```ts
   		this.agent.beforeToolCall = async ({ toolCall, args }) => {
   			const runner = this._extensionRunner;
   			if (!runner.hasHandlers("tool_call")) {
   				return undefined;
   			}
   			try {
   				return await runner.emitToolCall({
   					type: "tool_call",
   					toolName: toolCall.name,
   					toolCallId: toolCall.id,
   					input: args as Record<string, unknown>,
   				});
   ```
3. `packages/agent/src/agent-loop.ts:636-641` `prepareToolCall`——`beforeResult?.block` 时**不执行工具**，直接构造 `isError` 工具结果：
   ```ts
   			if (beforeResult?.block) {
   				return {
   					kind: "immediate",
   					result: createErrorToolResult(beforeResult.reason || "Tool execution was blocked"),
   					isError: true,
   				};
   			}
   ```

⇒ `reason` 作为 `isError` 工具结果回到 LLM 当轮上下文，模型当轮即可读到（因此 `reason` 必须是可行动指引）。

### 1.5 可复制的骨架（形状来自 `protected-config.ts:247-274`，非新增文件）

```ts
export function registerXxxGuard(pi: ExtensionAPI): void {
	pi.on("tool_call", (event) => {
		if (event.toolName === "write" || event.toolName === "edit") {
			const rawPath = event.input.path;
			if (typeof rawPath === "string" && rawPath !== "" && isXxxPath(rawPath)) {
				recordXxxBlockTrace(event.toolName, rawPath);
				return { block: true, reason: `xxx-guard: blocked ${event.toolName} of ${rawPath}. ${GUARD_EXPLANATION}` };
			}
			return undefined;
		}
		if (event.toolName === "bash") {
			const command = event.input.command;
			if (typeof command === "string" && command !== "") {
				const verdict = checkXxxBashCommand(command);
				if (verdict.prohibited) {
					recordXxxBlockTrace(event.toolName, command);
					return { block: true, reason: verdict.reason };
				}
			}
			return undefined;
		}
		return undefined;
	});
}
```

**注意（对 G1 直接相关）**：现有 protected-config 判定是**纯文本**、不做文件系统 I/O。G1 需要在 block 前**扫描目标树下的 reparse point** ⇒ 必须在 handler 内做 fs 遍历。该 handler 允许异步/同步 fs（`ExtensionHandler` 返回 `Promise<R|void> | R | void`，`runner.emitToolCall` 会 `await`），且仓内已有 handler 内做 fs 读的先例：`implementation-gate.ts:761` 注册的 handler → `gateDecision` → `fs.readdirSync`（`:247`）/`fs.statSync`（`:107`、`:257`）。故 G1 的 fs 扫描在既有接缝内可行。

---

## 2. 拦截点有哪些可用（Q2）

### 2.1 Extension API 的 tool-call hook（唯一可用落点）

`packages/coding-agent/src/core/extensions/types.ts`：

- `:853-861`：
  ```ts
  interface ToolCallEventBase {
  	type: "tool_call";
  	toolCallId: string;
  }

  export interface BashToolCallEvent extends ToolCallEventBase {
  	toolName: "bash";
  	input: BashToolInput;
  }
  ```
- `:899-903`（注释即契约）：
  ```
   * Fired before a tool executes. Can block.
   *
   * `event.input` is mutable. Mutate it in place to patch tool arguments before execution.
   * Later `tool_call` handlers see earlier mutations. No re-validation is performed after mutation.
  ```
- `:1071-1074`：
  ```ts
  export interface ToolCallEventResult {
  	/** Block tool execution. To modify arguments, mutate `event.input` in place instead. */
  	block?: boolean;
  	reason?: string;
  }
  ```
- `:1188`：`export type ExtensionHandler<E, R = undefined> = (event: E, ctx: ExtensionContext) => Promise<R | void> | R | void;`
- `:1236`：`on(event: "tool_call", handler: ExtensionHandler<ToolCallEvent, ToolCallEventResult>): void;`

`BashToolInput` 形状（`packages/coding-agent/src/core/tools/bash.ts:39-42`，`Static<typeof bashSchema>`）：
```ts
const bashSchema = Type.Object({
	command: Type.String({ description: "Bash command to execute" }),
	timeout: Type.Optional(Type.Number({ description: "Timeout in seconds (optional, no default timeout)" })),
});
```

### 2.2 是"包在 bash 工具外层"还是 hook？

**是 Extension API 的 tool-call hook**，不是 bash 工具外层包装。注册点全在扩展 `activate()` 内。

### 2.3 既有的"拒绝/改写"约定

- **拒绝**：`{ block: true, reason: string }`（见 §1.4 短路链）。**没有**结构化错误码/错误类型——只有布尔 + 字符串。
- **改写**：`event.input` 可变（`types.ts:901`），且后续 handler 看得到前面的 mutation；但 mutation 后**不再复验**（`types.ts:902`）。仓内没有任何 handler 使用改写通道来"改命令"，全部只用 block（实测 5 个 `pi.on("tool_call")` handler 均返回 `undefined` 或 `{block, reason}`）。

现有 5 个 `tool_call` handler（`packages/coding-agent/src` 实测 5 处）：

| 文件:行 | 覆盖工具 | 备注 |
|---|---|---|
| `shared/protected-config.ts:249` | write/edit/bash | 路径集合 + bash 写构造 |
| `shared/xkey-gate-guard.ts:255` | write/edit/bash | `.agenticdoc/_autopilot/**`（xkey 子树除外）；与 G1 同族 |
| `shared/implementation-gate.ts:761` | write/edit/bash | **handler 内做 fs 读**（readdirSync/statSync） |
| `shared/pm-state-guard.ts:118` | （按 reason 判定） | `:121` `return reason ? { block: true, reason } : undefined;` |
| `worker/worker-mode.ts:869` | read 系工具防火墙 | worker 模式注册 |

多个 handler 在同一事件上天然叠加；`block` 短路（`runner.ts:945-947`）⇒ 新 guard 与既有 guard 共存无需协调，只是"谁先 block 谁的 reason 生效"（当前注册序：protected-config → xkey → implementation-gate）。

---

## 3. 报错文本规范（Q3）

### 3.1 bash 命令的报错（`protected-config.ts:211-217`）

```ts
	const refText = refs.length > 0 ? refs.join(", ") : ".pi/agent (path assembled inside inline code)";
	return {
		prohibited: true,
		reason:
			`protected-config: blocked a bash command referencing cross-window config (${refText}) ` +
			`with a write construct (${constructs.join(", ")}). ${GUARD_EXPLANATION}`,
	};
```

### 3.2 write/edit 的报错（`protected-config.ts:254-257`）

```ts
				return {
					block: true,
					reason: `protected-config: blocked ${event.toolName} of ${rawPath}. ${GUARD_EXPLANATION}`,
				};
```

### 3.3 `GUARD_EXPLANATION` 的四段结构（`protected-config.ts:51-57`，逐字）

```ts
const GUARD_EXPLANATION =
	"~/.pi/agent/{auth,models,settings,oauth}.json are cross-window config shared by every live pi session " +
	"(credentials hot-reload per window). Modifying them from a running session breaks the other windows " +
	"(2026-09-15 incident: clearing auth.json broke every open window with 'Provider is not configured'). " +
	"Reads are allowed. To change credentials/models/settings: close pi windows and edit from a plain " +
	"terminal, or use pi /login (core flow, outside the tool layer).";
```

结构 = **① 保护对象 + 共享范围**（"are cross-window config shared by every live pi session"）→ **② 为什么危险 + 事故引用**（"breaks the other windows (2026-09-15 incident: ...)"）→ **③ 读放行**（"Reads are allowed."）→ **④ 唯一正确做法**（"close pi windows and edit from a plain terminal, or use pi /login"）。

### 3.4 同族第二例（`xkey-gate-guard.ts`，可作风格交叉验证）

- 命令报错（`:219-220`）：
  ```ts
  			`xkey-gate-guard: blocked a bash command referencing the autopilot directory (${refs.join(", ")}) ` +
  			`with a write construct (${constructs.join(", ")}). ${GUARD_EXPLANATION}`,
  ```
- write/edit（`:262`）：`` reason: `xkey-gate-guard: blocked ${event.toolName} of ${rawPath}. ${GUARD_EXPLANATION}`, ``
- 其 `GUARD_EXPLANATION`（`:70-...`）同样是四段：保护对象/谁写 → agent 不得写 → **给出替代通道**（"write .agenticdoc/_autopilot/xkey/evidence/<request_id>/proposal.md instead"）→ "Reads remain allowed."

**G1 照抄要点**：报错前缀应为稳定 guard id（如 `worktree-guard:`）；命中详情要含**被检出链接路径与目标**（AC-002）；正确做法段必须给出可直接照抄的 `mw worktree rm <path>`（G2）。

---

## 4. Python 侧接缝（Q4）

### 4.1 `mw.py` 子命令注册（argparse 结构）

`packages/multi-workers/mw.py`：

- `:5324-5326`：
  ```python
  def _parse_args() -> argparse.Namespace:
      parser = argparse.ArgumentParser(description="Multi-Workers service manager")
      sub = parser.add_subparsers(dest="subcommand", required=True)
  ```
- 顶层子命令：`sub.add_parser("serve"/"start"/"stop"/"status")`（`:5332-5335`）、`doctor_p = sub.add_parser("doctor", ...)`（`:5339`）、`target_p`（`:5352`）、`partition_p`（`:5375`）、`model_p`（`:5402`）、`autopilot_p`（`:5422`）、`init_p`（`:5464`）、`pull_p`/`push_p`（`:5474`/`:5484`）、`setup_p`（`:5491`）、`bootstrap_p`（`:5502`）、`build_p`（`:5522`）、`update_env_p`（`:5533`）、`toolchain_p = sub.add_parser("ue-toolchain", ...)`（`:5547`）、`rag_p = sub.add_parser("rag", ...)`（`:5581`）。
- 二级子命令范式（`mw worktree add/rm` 可照抄）：
  - `target_sub = target_p.add_subparsers(dest="target_action", required=True)`（`:5356`），随后 `target_sub.add_parser(action, ...)`（`:5357`/`:5372`）。
  - `_RAG_ACTIONS` dict + 单入口 `cmd_rag`（`:2243-2252`）：
    ```python
    def cmd_rag(args: argparse.Namespace) -> int:
        return _RAG_ACTIONS[args.rag_action](args)

    _RAG_ACTIONS = {
        "init": _cmd_rag_init,
        "list": _cmd_rag_list,
        "probe": _cmd_rag_probe,
        "audit": _cmd_rag_audit,
        "sync": _cmd_rag_sync,
    }
    ```
  - `cmd_autopilot` 的 if-chain 范式（`:3553-3571`）：`if args.autopilot_action == "gates": ...; if args.autopilot_action != "verify": print("[mw autopilot] Error: unknown action ...", file=sys.stderr); return 1; ...`。
- 入口 dispatch：`:5637-5659`：
  ```python
  if __name__ == "__main__":
      args = _parse_args()
      dispatch = {
          "serve": cmd_serve,
          ...
          "rag": cmd_rag,
      }
      sys.exit(dispatch[args.subcommand](args))
  ```

已有 `mw worktree` 子命令：**未找到**（`packages/multi-workers/*.py` + `autopilot/*.py` grep `worktree` 仅命中 `test_autopilot_readcap_injection.py:915-918` 的 `render_task_md` 参数校验，非子命令）⇒ G2 属新建。

### 4.2 "打印 + 退出码"约定

- `cmd_*` 一律 `-> int`，`main` 用 `sys.exit(...)`；`0` = 成功/健康，`1` = 失败/有 issue。
- 错误打印到 stderr 并返回 1，范式（`mw.py:624-628`，`_target_set`）：
  ```python
  def _target_set(project_dir: pathlib.Path, args: argparse.Namespace) -> int:
      game = pathlib.Path(args.game).resolve()
      if not game.is_dir():
          print(f"[mw target set] Error: game root not found: {game}", file=sys.stderr)
          return 1
  ```
- 机器可读出口用 `--json`（如 `doctor` `:5333`、`autopilot gates --json` `:5431`、`rag list --json`）。

### 4.3 `mw doctor` 的检查挂载点（`_doctor_*` 函数与注册处）

doctor 有两层：

**(a) 核心段（`mw_common.doctor_report`，`:2957-2996`）** — 每段一个 `_doctor_<name>(project_dir) -> dict`，在 `doctor_report` 内依次调用并放到 `report[...]`：

```python
    report["service"] = _doctor_service(project_dir)          # :2975
    ...
    report["target"] = _doctor_target(project_dir)            # :2984
    report["autopilot"] = _doctor_autopilot(project_dir)      # :2985
    report["gates"] = _doctor_gates(project_dir)              # :2986
    report["dispatch"] = _doctor_dispatch(project_dir)        # :2987
    report["pi_shell"] = ensure_pi_shell_path(env=os.environ, fix=fix)  # :2988
    issues, suggestions = _doctor_issues(report)              # :2994
    report["summary"] = {"healthy": not issues, "issues": issues, "suggestions": suggestions}  # :2995
```

`mw_common.py` 内 `_doctor_*` 生产函数实测 12 个：`_doctor_dispatch:1260`、`_doctor_service:1876`、`_doctor_proxy:1886`、`_doctor_orphan:1895`、`_doctor_proxy_log:1914`、`_doctor_launcher_log:1940`、`_doctor_queue:2154`、`_doctor_bundle:2180`、`_doctor_autopilot:2222`、`_doctor_gates:2689`、`_doctor_issues:2780`、`_doctor_target:4206`。

`_doctor_issues(report)`（`:2780-2955`）是 issue/suggestion 的唯一汇聚点：`issues` 会翻转 `summary.healthy` ⇒ 决定 `mw doctor` 退出码 1；`suggestions` 只打印。范式（`:2813-2818`）：
```python
    for err in gates_section.get("parse_errors") or []:
        issues.append(
            f"gate file invalid: {err['path']} ({err['error']}) - "
            "fix the frontmatter or move the file out of _autopilot/gates"
        )
```

文本渲染在 `format_doctor_text`（`:2999-3155`）：只在条件成立时追加行（zero-perturbation 范式，如 `gates:` 行由 `_gates_text_alerted` 守卫，`:3114-3127`）。

**(b) `mw.py cmd_doctor` 注入段**（后来新增段的范式，`:507-533`）——`cmd_doctor` 在 `doctor_report` 之后自行注入 `report["conductor"]`（`:522`）与 `report["rag"] = _doctor_rag(project_dir)`（`:525`），JSON 直接输出整份 report；文本模式 `print(mw_common.format_doctor_text(report))`，再对注入段做**额外一行**打印（`:530-532`）：
```python
        rag = report.get("rag") or {}
        if rag.get("exists") or rag.get("enabled"):
            print(_format_rag_doctor_line(rag))
```
`_doctor_rag` 定义在 `mw.py:2256`，`_format_rag_doctor_line` 在 `mw.py:2305`。**若 G3 的 doctor 检查要最小侵入，最贴近的挂载点是 (b)**：在 `mw.py` 内定义 `_doctor_worktree_junctions(project_dir)`，`cmd_doctor` 注入 `report["worktree_junctions"]`，需要报 issue 时在 `_doctor_issues` 加一条（或作为 informational 只打印一行）。若要与核心段同构则走 (a)。

### 4.4 测试范式（pytest 文件命名、夹具、断言退出码与文本）

- `packages/multi-workers/pytest.ini`（实测）：
  ```
  [pytest]
  addopts = -m "not e2e_real and not e2e_l2"
  markers =
      e2e_real: end-to-end tests that call the real pi CLI and a real LLM (run explicitly with -m e2e_real)
      e2e_l2: L2 process-chain e2e with stub workers, no LLM/network (run explicitly with -m e2e_l2 or python test_autopilot_e2e.py)
  ```
  运行方式（README `:396`）：在 `packages/multi-workers` 下 `python -m pytest -q`。
- 文件命名：`test_<area>.py`，平铺在 `packages/multi-workers/`（实测 67 个 `test_*.py`）。与 doctor 直接相关：`test_doctor_gates.py`、`test_doctor_autopilot.py`（2 个）。
- 导入范式：`sys.path.insert(0, str(pathlib.Path(__file__).parent))` 后 `import mw` / `import mw_common`。
- 两种断言层级：
  1. **纯函数/直接调命令函数**（`test_doctor_gates.py:126-134`、`:198-227`）——构造 `argparse.Namespace(...)` 直接调 `mw.cmd_doctor(args)`，用 pytest `capsys` 读 stdout，断言 `rc == 1` 与文本片段：
     ```python
     def _doctor_args(project, as_json=False):
         return argparse.Namespace(project=str(project), providers=None, fix=False, json=as_json, stale_after=90)
     ...
     rc = mw.cmd_doctor(_doctor_args(tmp_path))
     out = capsys.readouterr().out
     assert rc == 1
     assert "fix the frontmatter" in out
     ```
  2. **真 CLI 退出码**（`test_rag_cli.py:282-293`）——`subprocess.run([sys.executable, str(MW_PY), "rag", "sync", f"--project={self.root}"], capture_output=True, text=True, timeout=60)`，断言 `result.returncode == 0`。
- 证据行惯例：测试内 `_verify(tag, **kv)` 打印 `[VERIFY] ...`（`test_doctor_gates.py:38-39`）；pytest 需 `-q -s` 才可见（P-006 记录）。
- 夹具：`tmp_path`（pytest 内置）/ `tempfile.mkdtemp` + `unittest.TestCase`（`test_rag_cli.py` 用 `unittest` 类 + `self.addCleanup`）；`monkeypatch.setenv` 隔离机器层（`test_doctor_gates.py:44-48`）。

---

## 5. 可复用的探测原语（Q5）

### 5.1 仓库内：**需新建**

grep `is_junction|st_reparse|ReparsePoint|IO_REPARSE`（不区分大小写）在 `packages/**`（排除 `node_modules|dist|.tmp|__pycache__|.pytest_cache`）生产源码 **0 命中** ⇒ 仓库内**没有任何**"枚举 reparse point / 判断 junction"的工具函数或测试助手，**需新建**。

（全仓命中 8 处，全部在 `.agenticdoc/**` 的取证/任务文档中：`mw-workspace-incident-probe/{mini-spec.md,spec.md,evidence/in1-junction-incident-20261009.md,evidence/research/spec-incident-probe-plan-20261009.md,workers/inc1-junction-forensics/task.md}` 与本任务 `task.md`——是文字描述，不是代码。）

### 5.2 操作系统原语（本机实测可用）

Python 3.14.3（`python --version`）实测：

| 原语 | 状态 | 值/备注 |
|---|---|---|
| `os.path.isjunction` | 存在（Python 3.12+） | `hasattr(os.path,'isjunction') = True` |
| `os.path.islink` | 存在 | 对 junction 在 Windows 上为 False（junction 非 symlink）——**不能**用 `islink` 判 junction |
| `os.lstat(...).st_file_attributes` | 存在 | 与 `stat.FILE_ATTRIBUTE_REPARSE_POINT`（=1024）按位与 |
| `os.lstat(...).st_reparse_tag` | 存在（Windows） | `stat.IO_REPARSE_TAG_MOUNT_POINT` = 2684354563；`stat.IO_REPARSE_TAG_SYMLINK` = 2684354572 |
| `os.readlink` | 存在 | 对 junction 返回其目标（`\\?\` 前缀常见） |

Node/TS 侧（`node --version` = v24.19.0）：`fs.lstatSync`、`fs.readlinkSync`、`fs.Dirent.prototype.isSymbolicLink` 均存在。Node 没有 `isJunction` 内建 ⇒ TS 侧要判 junction 需 `lstatSync(p).isSymbolicLink()` 或读 `st_file_attributes`/reparse tag（Node 未在 `fs.Stats` 暴露 reparse tag ⇒ 需原生调用或 PowerShell，属新建）。

### 5.3 可复用的命令解析件（对 G1 直接相关）

`packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts`：

- `interface BashSegment`（`:273`）与 `function parseBashSegments(command)`（`:361`）——**模块私有（未 `export`）**，引号/转义感知、处理 Windows 反斜杠路径（P-004 修复点，`BACKSLASH_ESCAPES_UNQUOTED` / `BACKSLASH_ESCAPES_DOUBLE_QUOTED` 常量在 `:330-350`），支持 `cd` 跟踪与 redirect target 分离。
- `export function checkBashWriteTarget(command, root, cwd): string[]`（`:612-637`）——公开 API，提取写目标 token 并做路径判定；其文档（`:607-611`）自述"the write-structure target arguments ... as the raw tokens appear in the command"。

⇒ G1 若需从 `git worktree remove <path>` / `Remove-Item -Recurse` / `rm -rf` 中解析目标路径，`parseBashSegments` 是最贴近的可复用件，但**当前未导出**：要么将其抽成共享模块再导出，要么在 G1 模块内镜像一份（P-004 的三种拼写回归必须带上：无引号反斜杠 / 双引号反斜杠 / 正斜杠）。

---

## 6. 既有测试基线（Q6）

### 6.1 TS / vitest

- 纯函数层基线：`packages/coding-agent/test/extensions/agent-team-loop-protected-config.test.ts`（实测 11 tests，`describe` 分组：`resolveAgentDir`/`protectedConfigPaths`/`isProtectedConfigPath`/`checkProtectedBashCommand`/`recordProtectedBlockTrace`）。运行：
  ```
  cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-protected-config.test.ts
  ```
- **真实 tool_call 派发层基线（G1 最应照抄）**：`packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts`（`test/suite/` 下）。它用 `test/suite/harness.ts` 的 `createHarness({ tools, extensionFactories })` + faux provider 走真实管线：faux provider → Agent loop → `ExtensionRunner.emitToolCall` → 真实注册的 handler → `{block, reason}` → 工具不执行（该文件头 `:1-30` 明确这一意图）；bash 后端用 `BashOperations` recorder 打断（`:124-131`），并断言：
  - 工具结果是 `isError === true` 且文本含 guard id（`:294`、`:375`）；
  - 落盘前后字节未变；
  - worker trace 行数（`[XKEY_GATE]`）；
  - 反例（lookalike / 只读命令）不被拦。
- 测试 hook 范式：guard 在**注册时**读取的 env（如 `MW_XKEY_GATE_ROOT`、`PI_WORKER_TASK`）在 `createHarness` 前设置（`xkey-gate-guard-coverage.test.ts:121-122`）。G1 同理需要一个"目标根"注入点（现有保护 guard 无此需求，因路径是常量集合）。
- 目录/命令约定（AGENTS.md）：`test/suite/` 用 `harness.ts` + faux provider，禁真实 provider/keys；issue 回归放 `test/suite/regressions/<issue>-<slug>.test.ts`；从 `packages/coding-agent` 根跑单文件 `node ../../node_modules/vitest/dist/cli.js --run <path>`。`test/extensions/` 实测 21 个 `.test.ts`。
- vitest 配置：`packages/coding-agent/vitest.config.ts`（`globals: true`、`testTimeout: 30000`、`silent: "passed-only"` ⇒ 绿灯用例 `console.log` 被吞，证据行用 `process.stdout.write`，见 P-006）。

### 6.2 Python / pytest

- doctor 段与 issue/exit-code：`packages/multi-workers/test_doctor_gates.py`（段形状/只读纪律/I1-I6/退出码/`capsys`）。
- Python 侧 guard 规则（纯解析，无文件写）：`packages/multi-workers/test_protected_config.py`（`TestAgentConfigDir`、`TestIsProtectedAgentConfig` ...）。
- 子命令 CLI + 真退出码：`packages/multi-workers/test_rag_cli.py`（`unittest` + `subprocess.run([sys.executable, MW_PY, ...])`）。
- 运行：`cd packages/multi-workers && python -m pytest -q`（默认 `-m "not e2e_real and not e2e_l2"`）；单文件 `python -m pytest -q test_doctor_gates.py`。
- 全仓非 e2e 套件入口：repo 根 `./test.sh`（内部 `env -i ... npm test`，隔离 HOME/TMP）。

### 6.3 Windows 基线提醒

AGENTS.md：`packages/agent` 与 `packages/coding-agent` 在 Windows 有 **89 项已知环境失败基线**（13 + 76），属环境噪声；G1/G2 的测试应对比该基线而非追这些失败。

---

## 7. [VERIFY] 行（本次实测打印）

```
[VERIFY] rq2_reparse_primitives_in_production=0 (pattern is_junction|st_reparse|ReparsePoint|IO_REPARSE, ci, scope packages/**, exclude node_modules|dist|.tmp|__pycache__|.pytest_cache)
[VERIFY] rq2_reparse_hits_elsewhere=8 all_in=.agenticdoc/mw-workspace-incident-probe/**+this task.md (docs only, no code)
[VERIFY] rq2_tool_call_handlers=5 files=implementation-gate.ts:761,pm-state-guard.ts:118,protected-config.ts:249,xkey-gate-guard.ts:255,worker-mode.ts:869
[VERIFY] rq2_index_register_calls=3 (registerProtectedConfigGuard/index.ts:42, registerXkeyGateGuard/index.ts:49, registerImplementationGate/index.ts:59)
[VERIFY] rq2_doctor_fns_production=13 (mw_common.py 12 + mw.py 1: _doctor_rag:2256)
[VERIFY] rq2_python=3.14.3 has_isjunction=True st_reparse_tag=True IO_REPARSE_TAG_MOUNT_POINT=2684354563 FILE_ATTRIBUTE_REPARSE_POINT=1024
[VERIFY] rq2_node=v24.19.0 fs.lstatSync=function fs.readlinkSync=function
[VERIFY] rq2_pytest_addopts=-m "not e2e_real and not e2e_l2"; markers=e2e_real,e2e_l2
[VERIFY] rq2_py_test_files=67 doctor_test_files=2 ts_extensions_test_files=21
[VERIFY] rq2_mw_worktree_subcommand=absent
[VERIFY] rq2_parseBashSegments_exported=False (implementation-gate.ts:361 module-private; checkBashWriteTarget exported at :612)
```

---

## 8. 未找到 / 缺口（诚实边界）

- 仓库内**未找到** junction/reparse point 探测工具或测试助手（§5.1）⇒ G1/G3 的探测原语**需新建**。
- 仓库内**未找到** `mw worktree` 子命令（§4.1）⇒ G2 新建。
- 仓库内**未找到**任何 guard 使用 `event.input` 改写（"命令改写"）通道；既有约定只有 `block + reason`，**无结构化错误码**（§2.3）。
- `os.path.isjunction` 是 Python 3.12+ API；仓库未声明 `python_requires`/`requires-python`（`pyproject.toml`/`setup.py`/`setup.cfg` 均未找到），本机为 3.14.3。若需兼容 3.12 以下，须回退到 `lstat().st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT` + reparse tag 判定（属实现决策，不在本 RQ 结论内）。
- Node/TS 侧没有内建 junction 判定；`fs.Stats` 不暴露 reparse tag（本机实测仅确认 `lstatSync`/`readlinkSync` 存在），TS 侧判 junction 属新建。

## 9. 对接缝的直接含义（由上述事实推出，供 design）

- G1 的落点确定：新模块 `shared/<name>.ts`，`export function registerXxxGuard(pi: ExtensionAPI)`，在 `index.ts` 与 `:42/:49/:59` 同段注册（三模式全覆盖）。判定形状照 `checkProtectedBashCommand` 返回 `{prohibited, reason}`，注册照 `:247-274`；`reason` 走 §3 四段结构并内嵌 `mw worktree rm <path>`。
- G1 需要"目标树扫描" ⇒ handler 内做 fs（`implementation-gate.ts:761`→`:247` 已有先例）；需要一个目标根注入点（照 `xkey-gate-guard.ts:resolveXkeyGateRoot` 的 env test hook，`:101-108`）。
- G2 的落点确定：`mw.py:_parse_args` 加 `worktree_p = sub.add_parser("worktree")` + `worktree_sub`（`dest="worktree_action"`），`cmd_worktree` 用 `_RAG_ACTIONS`/`cmd_autopilot` 的 action dispatch；错误走 `print(..., file=sys.stderr); return 1`；G3 的 doctor 检查走 `cmd_doctor` 注入段范式（`mw.py:522-532`）+ `_doctor_issues`/`format_doctor_text`。
