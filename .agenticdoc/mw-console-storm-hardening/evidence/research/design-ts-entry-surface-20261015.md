# RQ-2 调研：agent-team-loop TS 入口面（run-detached 暴露形态）

- key: mw-console-storm-hardening · T-02 RQ-2 · type: research
- 日期: 2026-10-15（调研当日，T-01/T-03 并行）
- 只读调研；本文件为唯一写面。所有论断带 `路径:行号` 锚点。

## 结论

- **D1 recommended=both**：注册 LLM 可调工具 `mw_run_detached` + 复用现有 `/mw` 命令增加 `run-detached` 子命令，两者共用一个内部函数 `runDetachedMw()`（`shared/mw-runner.ts`）。理由：AC-008 要求"PM/Worker 会话内可发起"，两个会话的发起者都是 LLM agent，agent 只能调工具（不能敲 slash command）；而 `/mw` 已是面向人/PM 的 mw.py 薄包装（`ui-bridge.ts:3440-3442`），加一个 sub 成本极低；双入口共用内部函数避免漂移——与 `dispatch_worker` 工具 + `/worker` 命令共用 `planDispatchFrontmatter` 的既有模式完全一致（`ui-bridge.ts:2223` 注释 "Shared by the dispatch_worker tool and /worker so the two entries can never drift"）。
- **D2**：工具名 `mw_run_detached`；schema：`cmd: string[]`（必填 argv，`--` 与 flag 契约在 Python 侧，TS 透传）、`cwd?`、`log?`、`marker?`、`timeout_min?`；结果：content 文本 + `details: {marker, log_path, pid?, ok}`。注册函数 `registerRunDetachedTool(pi, projectDir)`，落点在 pmActivate（`pm-orchestrator.ts:1757-1764` 注册块，紧邻 `registerMwTools` 于 1760）与 workerModeActivate（`worker-mode.ts:2788` `registerWorkerFileTool` 同位置）双调用。
- **D3 worker_mode_ok=yes**：`index.ts:72-76` 按 `PI_WORKER_TASK` 分流，worker 模式不进入 `pmActivate`，PM 侧注册（`/mw`、`dispatch_worker`、`mw_status`、`ack_worker_result` 等）结构性缺席——`ui-bridge.ts:2499-2500` 明示 "worker mode never registers tools"。解法照抄 `registerRagTools` 双调用先例（`pm-orchestrator.ts:1769` + `worker-mode.ts:2773`）：新入口在两个 activate 路径都注册。worker 侧激活面必须走 `activeToolsForType`（`worker-mode.ts:167-170`，TS 侧专属，`worker_file` 同款），**不得**进 `TOOL_ALLOWLISTS`（`worker-mode.ts:41-49` 注释：T-17 L0 与 `packages/multi-workers/autopilot/dispatch.py` REGISTRY 字节级 parity）。仅对带 bash 的 shell 角色（coding/research/vision/repair 等）激活；read-only 角色（review/verifier/reviewer）不给 spawn 工具——否则绕开只拦截 bash tool call 的 AC-005b bash write-surface guard（`worker-mode.ts:1379-1390`）。worker bash 兜底路径亦成立：shell 角色可直接 `python mw.py run-detached -- <cmd...>`（透传；flag 契约 AC-003 在 Python 侧锁定，`spec.md:89`，TS 不需关心 windows console 语义）。
- **D4 build_step=mw-build-only**：esbuild `bundle:true`、entry 固定 `agent-team-loop/index.ts`（`mw.py:4642, 4662-4663`）——入口图内任何新 import 自动进 bundle，无需 settings 注册（bundle 由 pi 从全局/本地 extensions 目录自动发现，`mw.py:4823/5010`）。`mw build --install` 内的 `_rebuild_pi_dist()`（`npm run build`，`mw.py:4751-4762`、`_deploy_bundle` 于 `mw.py:4806-4813`）属同一 mw build 步骤。`spec.md:38` 明确"仅入口暴露层，构建走现有 esbuild bundle 流程"。

## 证据

### 1. 注册点清单表（agent-team-loop registerTool/registerCommand/pi.on 全量）

grep `registerCommand|registerTool|registerShortcut|pi.on(` 于 `packages/coding-agent/src/extensions/agent-team-loop/`。

| # | 位置 | 类别 | 内容 |
|---|------|------|------|
| 1 | `index.ts:29` | pi.on | session_shutdown 重装双载 guard |
| 2 | `index.ts:43` | 调用 | `registerProtectedConfigGuard`（EVERY mode，事件拦截器） |
| 3 | `index.ts:50` | 调用 | `registerXkeyGateGuard`（EVERY mode） |
| 4 | `index.ts:60` | 调用 | `registerImplementationGate`（EVERY mode） |
| 5 | `index.ts:70` | 调用 | `registerWorktreeJunctionGuard`（EVERY mode） |
| 6 | `index.ts:72-76` | 分支 | `PI_WORKER_TASK ? workerModeActivate : pmActivate` —— 模式分流点 |
| 7 | `pm/ui-bridge.ts:960` | registerCommand | `/pm-key` |
| 8 | `pm/ui-bridge.ts:1099` | registerCommand | `/pm-save` |
| 9 | `pm/ui-bridge.ts:1158` | registerCommand | `/mw-watch` |
| 10 | `pm/ui-bridge.ts:1188` | registerTool | `mw_status` |
| 11 | `pm/ui-bridge.ts:2234` | registerTool | `dispatch_worker`（PM agent 派发工具） |
| 12 | `pm/ui-bridge.ts:2501` | registerTool | `ack_worker_result`（2499-2500 注释："worker mode never registers tools"） |
| 13 | `pm/ui-bridge.ts:2534` | registerTool | `list_tasks` |
| 14 | `pm/ui-bridge.ts:2606` | registerTool | `switch_key` |
| 15 | `pm/ui-bridge.ts:2693` | registerTool | `advance_phase` |
| 16 | `pm/ui-bridge.ts:2799` | registerCommand | `/worker` |
| 17 | `pm/ui-bridge.ts:3440` | registerCommand | `/mw`（sub-dispatch: build/init/start/stop/status/doctor/update/target/partition/model/rag/ack，usage 行 3608） |
| 18 | `pm/pm-orchestrator.ts:1757-1764` | 调用 | pmActivate 注册全部 PM 命令/工具（仅 PM 模式） |
| 19 | `pm/pm-orchestrator.ts:1769` | 调用 | `registerRagTools(pi, projectDir)` —— PM 侧 |
| 20 | `worker/worker-mode.ts:2773` | 调用 | `registerRagTools(pi, controlRoot, hooks)` —— worker 侧（双模式先例） |
| 21 | `worker/worker-mode.ts:2788` | 调用 | `registerWorkerFileTool`（仅 writeless 角色） |
| 22 | `worker/worker-mode.ts:2810` | 调用 | `applyRagTools` 于 `before_agent_start`（allowlist 落盘） |
| 23 | `worker/worker-file-tool.ts:132` | registerTool | `worker_file`（worker 侧唯一工具注册） |
| 24 | `rag/tools.ts:247/268/285/310/328/340/366` | registerTool | `rag_search/rag_symbol/rag_graph/rag_impact/rag_sources/rag_feedback/rag_chat` |
| 25 | `rag/tools.ts:191` | fn | `registerRagTools(pi, controlRoot, hooks?)` —— PM+worker 共用 |
| 26 | `rag/tools.ts:400-407` | fn | `applyRagTools`：`setActiveTools([...activeToolsForType(type), ...ragToolNamesForType(...)])` |
| 27 | `autopilot/console.ts:106` | registerCommand | `/autopilot`（PM only） |
| 28 | `shared/implementation-gate.ts:511` | pi.on | tool_call 门禁 |
| 29 | `shared/protected-config.ts:249` | pi.on | tool_call 守卫 |
| 30 | `shared/pm-state-guard.ts:118` | pi.on | tool_call 守卫 |
| 31 | `shared/worktree-junction-guard.ts:215` | pi.on | tool_call + user_bash 守卫 |
| 32 | `shared/xkey-gate-guard.ts:255` | pi.on | tool_call 守卫 |
| 33 | `shared/dispatch-models.ts:324/328` | pi.on | session_start / model_select |

`register_points=20`（registerTool 14 + registerCommand 6 条语句；4 个 every-mode 守卫与模式分流为结构点，非工具/命令注册语句）。

### 2. pi 扩展 API 事实（docs 三方交叉）

- `docs/extensions.md:1337-1341`：`pi.registerTool(definition)`，加载期与启动后均可调用，新工具即时可调。
- `docs/extensions.md:1493`：`pi.registerCommand(name, options)`，handler `(args, ctx)`，可带 `getArgumentCompletions`。
- `docs/extensions.md:1987-1990`：工具错误须 `throw`（返回不置 isError）。
- 工具结果回传格式：`{content: [{type:"text",text}], details}`（`docs/extensions.md:1340-1344` Quick Start；`worker-file-tool.ts:143-156` 同款）。
- 参数 schema 用 typebox `Type.Object`（`docs/extensions.md:1351-1361`；`worker-file-tool.ts:96-120` 同款，`additionalProperties:false` + pattern）。
- 模式行为表（`docs/extensions.md:2746-2762`）：`ctx.mode` tui/rpc/json/print；工具在 worker 的 pi 进程里照常可用（worker 是独立 pi 进程，`goal.md:26`）。
- 与"派发后台命令并回传 marker/log 路径"最匹配的 API：`registerTool`（LLM 可调用）+ `registerCommand`（人/PM 手动），二者内部共用同一函数——`docs/extensions.md:1299` 也演示 tool→command 桥（`sendUserMessage("/reload-runtime")`）证明 agent 无法直接敲命令、必须经工具。

### 3. 进程派生先例（child_process）

- `shared/mw-runner.ts:12` `PYTHON_EXE = win32 ? "python" : "python3"`。
- `shared/mw-runner.ts:31-56` `findMwPy()`：MW_PY env → `.mw-py-path` sidecar → repo 相对。
- `shared/mw-runner.ts:127-134` `startMw()`：`spawn(PYTHON_EXE, [mwPy, "start", --project=...], {detached:true, stdio:"ignore", windowsHide:true})` + `unref()` —— 后台派发最接近的先例。
- `shared/mw-runner.ts:501-517` `runMwCliRaw()`：`spawnSync(PYTHON_EXE, [mwPy, sub, ...args, --project=...], {encoding:"utf8", timeout})`，stdout+stderr 合并文本返回。
- `shared/agentic-scripts.ts:1,67`、`shared/worktree-junction-guard.ts:430`、`rag/cli-bridge.ts:16,57`：均 list-args 无 shell、`windowsHide`/隐式。
- 结论：TS 侧直接 spawn `python mw.py run-detached -- <cmd...> --project=<dir>`，照抄 `startMw` 的 detached+windowsHide+unref 风格（后台派发）或 `runMwCliRaw` 的 sync 风格（等返回）；stdout 落 log、marker JSON 落盘均在 Python 侧（`spec.md:44` 场景 B），TS 只透传。Windows 隐藏语义 TS 不需关心（AC-003 已在 `spec.md:89` 锁定）。

### 4. 约束核对（实现硬规则）

| 规则 | 出处 |
|------|------|
| 无 `enum`/`namespace`/参数属性（erasable TS，strip-only） | `AGENTS.md` Code Quality |
| 仅 top-level import，无 inline `await import()` | `AGENTS.md` Code Quality |
| 无 `any` 除非必要 | `AGENTS.md`；biome `noExplicitAny` 已 off 但仍自律 |
| biome recommended + `useConst: error`、tab 缩进、lineWidth 120 | `biome.json:6-14` |
| 工具错误必须 throw 而非返回值置 isError | `docs/extensions.md:1987-1990` |
| 不透传/不重实现 Python flag 契约（AC-003） | `spec.md:89`；T-02 硬契约"TS 只是透传" |

### 5. D1-D4 结论表

| 决策 | 结论 | 依据 |
|------|------|------|
| D1 入口形态 | **both（共用一个内部函数）** | AC-008 "PM/Worker 会话内可发起"（`spec.md:94`）→ agent 只能调工具；`/mw` 已有 sub 分发（`ui-bridge.ts:3440`）；dispatch_worker//worker 双入口共享函数先例（`ui-bridge.ts:2223` 注释） |
| D2 工具定义 | `mw_run_detached`；schema 见草图；注册 `registerRunDetachedTool` 双激活路径调用 | PM 工具命名 snake_case 先例（`mw_status`/`dispatch_worker`/`worker_file`）；schema 用 typebox（`worker-file-tool.ts:96-120`） |
| D3 worker 模式 | worker_mode_ok=**yes**（双调用注册 + `activeToolsForType` 激活门控；shell 角色另有 bash 直调兜底） | `index.ts:72-76` 分流；`registerRagTools` 双调用（`pm-orchestrator.ts:1769`+`worker-mode.ts:2773`）；parity 锁（`worker-mode.ts:41-49`）；AC-005b guard 只拦 bash（`worker-mode.ts:1379-1390`） |
| D4 构建 | **mw-build-only** | esbuild entry=index.ts（`mw.py:4642/4662`）；`spec.md:38`；dist rebuild 属 `mw build --install` 内部步骤（`mw.py:4806-4813`） |

### 6. 最小实现草图（≤30 行，落点 file:line）

```ts
// shared/mw-runner.ts（新增，紧邻 startMw:127-134 / runMwCliRaw:501-517）
export const MW_RUN_DETACHED_TOOL = "mw_run_detached";
export function runDetachedMw(projectDir: string, cmd: string[], opts: {
  cwd?: string; log?: string; marker?: string; timeoutMin?: number;
}): { marker: string; logPath: string; ok: boolean; error?: string } {
  const mwPy = findMwPy();                       // mw-runner.ts:31
  if (!mwPy) return { marker: opts.marker ?? "", logPath: "", ok: false,
    error: "Could not find mw.py — set MW_PY env var." };
  const marker = opts.marker ?? `rd-${Date.now()}`;
  const logPath = opts.log ?? path.join(projectDir, ".mw", "run", `${marker}.log`);
  const args = [mwPy, "run-detached", "--project=" + projectDir,
    ...(opts.timeoutMin ? [`--timeout=${opts.timeoutMin}`] : []),
    "--", ...cmd];                               // 透传；flag 契约 AC-003 Python 侧
  const child = spawn(PYTHON_EXE, args, {        // mw-runner.ts:12, 风格照 startMw
    cwd: opts.cwd ?? projectDir, detached: true,
    stdio: ["ignore", fs.openSync(logPath, "w"), fs.openSync(logPath, "a")],
    windowsHide: true });
  child.unref();
  return { marker, logPath, ok: true };
}

// pm/ui-bridge.ts:1760 旁（pmActivate 注册块）与 worker/worker-mode.ts:2788 旁各调一次：
// registerRunDetachedTool(pi, projectDir);
export function registerRunDetachedTool(pi: ExtensionAPI, projectDir: string): void {
  pi.registerTool({                              // docs/extensions.md:1337
    name: MW_RUN_DETACHED_TOOL, label: "mw_run_detached",
    description: "Dispatch a background command via `python mw.py run-detached -- <cmd...>`. "
      + "Returns marker + log path; poll the marker JSON for rc/wall_sec.",
    parameters: Type.Object({
      cmd: Type.Array(Type.String({ minLength: 1 }), { description: "Command argv (透传, no shell)." }),
      cwd: Type.Optional(Type.String({ description: "Working dir; default project root." })),
      log: Type.Optional(Type.String({ description: "Log file path; default .mw/run/<marker>.log." })),
      marker: Type.Optional(Type.String({ description: "Correlation marker; default generated." })),
      timeout_min: Type.Optional(Type.Number({ minimum: 1 })),
    }, { additionalProperties: false }),
    execute: async (_id, p) => {
      const r = runDetachedMw(projectDir, p.cmd, p);
      if (!r.ok) throw new Error(r.error ?? "spawn failed");   // throw → isError
      return { content: [{ type: "text",
        text: `dispatched marker=${r.marker} log=${r.logPath}` }],
        details: { marker: r.marker, log_path: r.logPath, ok: r.ok } };
    },
  });
}

// pm/ui-bridge.ts:3440 `/mw` handler 的 sub 分发中加：
// if (sub === "run-detached") { /* splitCommandLine(trimmed.slice(sub.length)) → cmd[] → runDetachedMw */ }
// 并把 "run-detached" 加进 ui-bridge.ts:3608 usage 行。

// worker 侧激活门控（worker/worker-mode.ts:167-170 activeToolsForType 扩展）：
// return base.includes("bash") ? [...base, MW_RUN_DETACHED_TOOL] : base;
// （不进 TOOL_ALLOWLISTS，parity 锁 worker-mode.ts:41-49 不动）
```

## 残留与未验证

- 未实测工具在 worker 模式下的 LLM 可见性（仅按 `applyRagTools`/`activeToolsForType` 机制推证）；AC-008 要求 suite 测试以 faux provider 断言，属实现阶段（T-03 相关）。
- `/mw run-detached` 参数解析细节（`--` 之后的原文透传 vs splitCommandLine 切词）待 Python 侧 CLI 定稿后对齐；`splitCommandLine`（`ui-bridge.ts:3126`）为可复用切词器。
- read-only 角色（review/verifier）是否需要 run-detached 能力未决——本调研建议不给（绕开 AC-005b guard 风险），若 PM 裁定需要须另行评估 spawn 工具的写入/越权面。
- `timeout_min` 透传字段名待与 Python CLI（T-01/实现任务）对齐。

## 上下文来源

- 本任务卡片：`.agenticdoc/mw-console-storm-hardening/workers/csg-t02-ts-entry/task.md`（AC-008 上下文、D1-D4）
- `tasks/T-02-RQ2-ts-entry-surface.md`（调研面、硬契约、证据格式）
- `spec.md:33,38,44,89,94`（TS 暴露、构建、场景 B、AC-003、AC-008）
- `goal.md:25`（GC-2：不修改 pi 核心，所有功能通过 Extension API 实现）
- `docs/extensions.md:1337,1493,1987,2746`（扩展 API）
- agent-team-loop 源码全目录（注册点清单表所列）
- `mw.py:4626-4663,4710-4746,4751-4813,4823,4892`（构建与部署）

```
[VERIFY] RQ2: register_points=20 recommended=both worker_mode_ok=yes build_step=mw-build-only
```
