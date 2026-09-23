# Research: 验证与文档面（design）

> RQ-D3（mw-worker-progress-persist）：VC-001~VC-011 怎么被机器判定、新用例挂在哪、VC-011 的 e2e 怎么做。
> 只读调研；本文件是唯一写入物。基线底稿：`evidence/research/design-worker-progress-persist-baseline-2026-09-23.md`。

## 决策问题

1. `worker-mode.ts` / `output-writer.ts` 可测导出与既有测试覆盖（每个导出 → 文件/用例）。
2. 不 spawn 真 worker 时如何 hermetically 驱动 worker-mode；「检查点时刻写了哪一行到哪个文件」的最小 harness 形态；何时必须真进程。
3. `test/suite/` 与扩展测试目录的命名约定；本 key 新增/需改的测试文件清单（每个文件对应哪些 VC）。
4. Python parity 用例的 pytest 调用与 Windows 基线口径（89 项是否含 parity）。
5. VC-011 的 e2e 可执行步骤草案（命令 + 断言 + 产物路径 + 前置）。
6. CHANGELOG / 文档落点；`progress.md` grep 命中哪些陈述需要与实现同步。

## 调研方法与出处

- 全文 `read`：`worker/worker-mode.ts`（1073 行）、`worker/output-writer.ts`、`rag/tools.ts`（apply/register 段）、`core/extensions/types.ts`（ToolDefinition/ToolExecutionEndEvent）、`core/agent-session.ts`（tool hooks/事件透传）、`core/extensions/wrapper.ts`、`core/tools/tool-definition-wrapper.ts`、`packages/agent/src/agent-loop.ts`、`node_modules/@earendil-works/pi-agent-core/dist/types.d.ts`。
- 全文 `read`：`test/extensions/agent-team-loop.test.ts`（watchdog/checkpoint 段）、`test/suite/autopilot-protocol.test.ts`、`test/suite/rag-tools.test.ts`（CapturingApi）、`test/suite/agent-team-loop-implementation-gate.test.ts`（真管道范式）、`test/suite/rag-research-doc.test.ts`、`test/suite/harness.ts`、`test/suite/README.md`。
- 全文 `read`：`packages/multi-workers/test_autopilot_l0.py`、`test_autopilot_dispatch.py`、`test_rag_research.py`、`test_e2e_real.py`、`pytest.ini`、`launcher.py`（_build_env/_build_command/cmd_serve）、`mw.py`（cmd_build/_deploy_bundle/cmd_serve）、`mw_common.py`（workers_path）。
- 只读命令：`rg -n 'checkpointAnchorMs|steerAtMs|resolveBudgetMs|toolsForType|resolveIdleMs|DEFAULT_*|activeToolsForType|appendProgressLine|worker_file' packages/coding-agent/test packages/multi-workers`；`rg -n 'progress\.md' packages/...`；`python -m pytest --collect-only -q test_autopilot_l0.py test_autopilot_dispatch.py test_rag_research.py`（27 collected）。
- 基线口径：`AGENTS.md:35`、`.agenticdoc/ai-baseline-repair/evidence/runs/attribution-2026-09-10.md`（B/A' 类失败文件清单）。

## 发现

### 1. 可导入性：导出 ↔ 既有用例覆盖

`worker-mode.ts` 已有导出（`rg -n '^export'`）：`toolsForType:89`、`DEFAULT_BUDGET_MS:99`、`DEFAULT_IDLE_MS:105`、`resolveBudgetMs:112`、`resolveIdleMs:120`、`checkpointAnchorMs:128`、`steerAtMs:133`、`computeRisk:161`、`parseTaskMd:203`、`evidencePhase:469`、`emitRagRequiredMissing:536`、`workerModeActivate:555`。

| 导出（worker-mode.ts:line） | 覆盖测试 file:line | 断言 |
|---|---|---|
| `toolsForType` :89 | `test/suite/rag-research-doc.test.ts:37,107-112` | `rag-research` 11 工具 order-exact |
| `DEFAULT_BUDGET_MS` :99 | `test/extensions/agent-team-loop.test.ts:3585-3589` | =60m |
| `DEFAULT_IDLE_MS` :105 | `agent-team-loop.test.ts:3596-3599` | =10m |
| `resolveBudgetMs` :112 | `agent-team-loop.test.ts:3585-3593` | task.md > env > default，垃圾值回退 |
| `resolveIdleMs` :120 | `agent-team-loop.test.ts:3596-3601`；`test/suite/rag-e2e-slow.test.ts:38,222` | env 有效值/垃圾回退 |
| `checkpointAnchorMs` :128 | `agent-team-loop.test.ts:3604-3612` | min(30m, budget/2)，clamp 1s |
| `steerAtMs` :133 | `agent-team-loop.test.ts:3604-3612` | budget − min(5m, budget/4) |
| `computeRisk` :161 | `agent-team-loop.test.ts:3630-3687` | high/mid/low 全分支 |
| `parseTaskMd` :203 | `agent-team-loop.test.ts:3615-3628`；`test/suite/autopilot-protocol.test.ts:411-432` | timeout/taskKey/agenticdocRoot、D-116 双根 |
| `evidencePhase` :469 | `test/suite/rag-required.test.ts:24,152-154` | ""/undefined → `unknown` |
| `emitRagRequiredMissing` :536 | `test/suite/rag-required.test.ts:23,397+` | required 判定与行发出 |
| `workerModeActivate` :555 | `agent-team-loop.test.ts:3877-4050`（watchdog 集成）、`:2760-2780`、`:4203-4220`；`test/suite/autopilot-protocol.test.ts:220-231`；`autopilot-read-scope.test.ts:450,750,807`；`cross-drive-worker.test.ts:181`；`dual-root-worker.test.ts:97,175`；`rag-required.test.ts:120`；`rag-e2e-slow.test.ts:184`；`agent-team-loop-worker-tree-kill.test.ts:82`、`-live.test.ts:112`；`agent-team-loop-output.test.ts:151` | 端到端 fake-pi 驱动（见 §2） |

`output-writer.ts` 导出：`headline:35`、`writeOutput:45`、`appendTrace:91`、`appendStart:115`、`appendModel:128`、`appendPhase:133`、`appendTool:148`、`appendToolError:157`、`appendTimeout:170`、`appendCheckpoint:191`、`appendError:204`、`appendEnd:223`、`appendGoalCheck`、`appendHeartbeat:245`。覆盖集中于：
- `headline`/`writeOutput`：`test/extensions/agent-team-loop-output.test.ts:19,35-134`（TL;DR/D-117 合并）。
- `appendCheckpoint`/`appendTimeout`/`appendStart`/`appendEnd`/`appendHeartbeat`：`agent-team-loop.test.ts:3689-3738`、`:2175`、`:2275`、`:2321` 等；解析侧锁定在 `shared/heartbeat.ts`（`CHECKPOINT_LINE_RE` 等）。
- 结论：本 key 新增 `appendProgressLine` / `formatMachineCheckpoint` 后，**没有既有测试需要改格式**（新增导出，不改既有行）。

**可测性结论**：本 key 需要测的全部逻辑（检查点定时器回调、steer 文本、集合计算、窄工具 execute、append-only 写入器）都在 `workerModeActivate` 闭包或可导出纯函数中，**无需改可见性即可测**；唯一要新增的导出是 design §4.1 已列的 `activeToolsForType`、`isAllowedWorkerFile`、`formatMachineCheckpoint`、`appendProgressLine`。

### 2. hermetic 驱动方式与最小 harness

既有三种 hermetic 形态（都不 spawn 真 worker、都不走网络）：

**(a) fake-timer worker 驱动** —— `test/extensions/agent-team-loop.test.ts:3877-3920`：`fakeWorkerPi()`（`:3878`，只捕获 `on`/`sendUserMessage(text,options)`）+ `startWatchdogTask(root,taskKey,body)`（`:3907`）写 `root/key-a/workers/<taskKey>/task.md`、设 `PI_WORKER_TASK`、`PI_WORKER_IDLE_MS=60000`，`await workerModeActivate(pi)`。`vi.useFakeTimers()` + `vi.advanceTimersByTime(...)` 推进检查点/墙钟，断言 `taskDir/trace.log`、`output.md`、捕获的 `sent`（`sent[].options.deliverAs`）。`process.exit` 用 `vi.spyOn` 顶掉。**检查点集成（VC-001/002/003/004）直接复用此形状**。

**(b) capturing-ExtensionAPI 单元驱动** —— `test/suite/rag-tools.test.ts:63-97` 的 `CapturingApi`（`registerTool`/`setActiveTools`/`getActiveTools`/`getAllTools`/`on`）+ `toolOf(capture,name)`，直接 `await toolOf(...).execute(id, params, undefined, undefined)`。**窄工具 execute 与白名单矩阵（VC-005/006 文件面）用此形状**。

**(c) 真 pi 管道 harness** —— `test/suite/harness.ts::createHarness`（faux provider）+ `test/suite/agent-team-loop-implementation-gate.test.ts:120-160` 范式：`extensionFactories:[(pi)=>{...}]` → `harness.setResponses([fauxAssistantMessage([fauxToolCall(name, args)], {stopReason:"toolUse"}), ...])` → `await harness.session.prompt(...)` → 工具真实执行、真实 `tool_execution_start/end` 落到 worker-mode 的 trace handler。**VC-005/006 的 `[TOOL]`/`[TOOL_ERR]` 证据行必须用此形状**（见下方纠错）。

**最小可行 harness（断言「检查点时刻写入哪一行到哪个文件」）**＝(a)＋一行断言：

```ts
// 复用 agent-team-loop.test.ts:3878/3907 的 fakeWorkerPi + startWatchdogTask
vi.useFakeTimers();
const { emit, sent } = await startWatchdogTask(root, "t-ckpt", "type: review\ntimeout: 2\n\nreview\n");
// budget=120s → checkpointAnchorMs=60s；必须持续喂活动，避免 60s idle 先杀（同 :4014 用例）
for (let t = 0; t < 8; t++) { vi.advanceTimersByTime(15_000); emit("message_update"); } // t=120s
const progress = fs.readFileSync(path.join(root, "key-a", "workers", "t-ckpt", "progress.md"), "utf8");
expect(progress).toMatch(/^CKPT \d+m \[machine\] ts=\S+ reads=\d+ writes=\d+ phases=\S+ repeat_top=\d+ risk=(low|mid|high)$/m);
// steer 分化（VC-004）：sent 里 [mw checkpoint] 文本不含 /追加到.*progress\.md/
```

要点（均有既有先例）：
- 检查点用 `timeout: 2` 头把 anchor 缩到 60s（`checkpointAnchorMs` 对 budget/2 缩放，`agent-team-loop.test.ts:3608-3610` 已锁）。
- **必须喂活动**：`advanceTimersByTime` 期间不 emit 会让 idle watchdog 在 60s 先杀（`agent-team-loop.test.ts:3922-3947`）；`t-order` 用例（`:4014-4048`）演示了 trickle 写法。
- `appendProgressLine` 的 append-only（VC-002）用单元直调 3 次 + 预置 sentinel 断言，比推 3 次 10m 刷新（anchor 30m + 2×10m）更省、更稳；集成层再覆盖 1 次即可。
- `[VERIFY]` 证据行用 `process.stdout.write`（suite 配置会吞绿用例的 `console.log`，见 `rag-tools.test.ts:44-51`）。

**关键纠错（D-109 前提不成立，必须联动 D1）**：ToolDefinition.execute 返回的 `AgentToolResult` **没有 `isError` 字段**（`node_modules/@earendil-works/pi-agent-core/dist/types.d.ts:310-325`）；`packages/agent/src/agent-loop.ts:696` 对任何「未抛出」的 execute 都返回 `{ result, isError: false }`；`isError` 只在 execute 抛出、参数校验失败、`beforeToolCall` 返回 block 时为 true（`agent-loop.ts:612-661,696`；`coding-agent/src/core/agent-session.ts:501-530` 的 afterToolCall 用 `hookResult?.isError ?? isError`，从不读 `result.isError`；`:798-806` 原样透传该 isError）。因此「返回 `{isError:true}` → tool_execution_end.isError=true」不成立。**窄工具非法请求必须 `throw new Error(reason)`**，才落到 `worker-mode.ts:786-789` 的 `[TOOL_ERR]`；合法请求返回普通结果即落 `:770-784` 的 `[TOOL]`。VC-006 的 hermetic 断言应为 `await expect(execute(...)).rejects.toThrow(/.../)`，而非断言返回对象的 isError。

`[TOOL]` 行的 target 说明：`toolTarget()`（`worker-mode.ts:186-202`）只认 `path`/`command`/`pattern`/`query`；窄工具参数是 `file`/`content`/`mode` → trace 行为 `[TOOL] <ts> worker_file`（无文件名）。VC-005 只要求 `[TOOL] worker_file` 存在，成立；若后续想要文件名可见，需在 D1 契约里补 `toolTarget` 分支（本 key 不强制）。

**何时必须真进程**：仅 VC-008 的 Python→vitest 子进程与 VC-011。VC-011 的核心断言「终稿回复不含『无法写入 progress.md / 请编排方代为追加』」是**真实模型行为**，hermetic 造不出真回复；`worker.log` 的 `done exit=0` 也来自真 pi print-mode stdout。其余（VC-001~VC-007）hermetic 充分。

### 3. 新用例落点

命名约定：`test/suite/README.md` —— 广谱用例放 `test/suite/`，issue 专属放 `test/suite/regressions/<issue-number>-<slug>.test.ts`；`harness.ts` + faux provider、禁真实 API。本 key 无 GitHub issue 号，且属广谱功能（检查点/窄工具/集合），**不落 regressions/**。

建议：

| 新文件 | 覆盖 VC | harness |
|---|---|---|
| `packages/coding-agent/test/suite/worker-file-tool.test.ts` | VC-005、VC-006 | (b) `CapturingApi` 直接调 execute 断言文件/拒绝矩阵；`[TOOL]`/`[TOOL_ERR]` 行改 (c) `createHarness`+`fauxToolCall("worker_file", …)` 真管道断言 |
| `packages/coding-agent/test/suite/worker-progress-persist.test.ts` | VC-001、VC-002、VC-003、VC-004、VC-007 | (a) fake-timer worker 驱动 + 纯函数直调（`activeToolsForType` vs `toolsForType`）+ 硬编码 TS 侧白名单快照 |

**必须同步改的既有 fake pi（否则实现落地即红）**：新增 `pi.registerTool` 调用后，以下 fake 缺 `registerTool`，且这些测试会激活**无写角色**（review/verifier/rag-research）从而触发注册：
- `test/suite/autopilot-protocol.test.ts:190`（verifier/reviewer 用例 `:239-243`；也是 `test_autopilot_l0.py::test_vc023_worker_fail_closed` 子进程运行的对象 → 必须保持绿）。
- `test/suite/autopilot-read-scope.test.ts:410`（`type: verifier`，`:338,445`）。
- `test/suite/cross-drive-worker.test.ts:37`（`type: verifier`，`:153`）。
- `test/suite/dual-root-worker.test.ts:34`（`type: verifier`，`:74`）。

已具备 `registerTool` 的 fake（无需改）：`rag-required.test.ts:93`、`rag-e2e-slow.test.ts:82`、`agent-team-loop.test.ts:4143`（含 noop）。`type: coding` 的 fake（`worker-tree-kill*.test.ts`、`agent-team-loop-output.test.ts:142`、watchdog `:3878`）因结构性 gating（无写角色才注册）**不会被触发**，可不改；但若实现把注册点无条件放在 `workerModeActivate` 顶部则会连带打红这些文件——设计 D-101/§3 明确「仅当无写工具时注册」，实现需遵守。

VC-008 不新增文件（跑既有 parity）。VC-009 不新增文件（`npm run check` + `./test.sh`；注意 `npm run check` 含 `biome check --write`，会改格式，须在受控的 key 工作区内跑）。VC-010 不新增测试（CHANGELOG + 文档 grep 证据）。

### 4. Python parity 运行命令与 Windows 基线口径

- parity 三件套（VC-008）：`cd packages/multi-workers && python -m pytest test_autopilot_l0.py test_autopilot_dispatch.py test_rag_research.py -q -s`。已核实 `--collect-only` 收集 **27 项**（l0 5 + dispatch 18 + rag_research 4）。
- 全量 Python：`python -m pytest -q`（README `:352`「430+ 通过；e2e 默认 deselect」）；`pytest.ini:2` 的 `addopts = -m "not e2e_real and not e2e_l2"` 默认排除真机 e2e。
- parity 用例的额外副作用：`test_rag_research.py:134` 跑 `git diff --stat test_autopilot_l0.py` 并断言为空 → **实现期禁止改 `test_autopilot_l0.py`**；`test_autopilot_l0.py::test_vc023_worker_fail_closed`（`:279-320`）会 spawn vitest 单文件 `test/suite/autopilot-protocol.test.ts`（`node_modules/vitest/dist/cli.js --run`），故该文件的改动必须保持绿。
- **89 项基线口径**：`AGENTS.md:35` 明确 89 = `packages/agent` 13 + `packages/coding-agent` 76 的 **vitest** 环境失败；归因报告 `attribution-2026-09-10.md` 的 B/A' 失败文件清单（config/tools/model-registry/…/3592-no-builtin-tools 等）**不含 `agent-team-loop*`、`autopilot-*`、`autopilot-protocol`**。结论：**89 项不含 Python parity，也不含本 key 触达的扩展/suite 测试**。Python parity 期望 0 失败（纯 hermetic、无网络、无 Windows shell 语义依赖）；VC-009 的 `baseline_ok` 应按「agent+coding-agent 总失败数 ≤89 且新增测试全绿」判定，而不是把 parity 计入。

### 5. VC-011 的 e2e 可行性

既有 `test_e2e_real.py`（`pytestmark = e2e_real`，`:31`）的做法：手写 `.agenticdoc/_scratch/workers/<key>/task.md` + 追加 `_workers.parallel` 行（`_make_task`，`:61-89`），直接 `subprocess.Popen([python, launcher.py, --project, proj, --poll-interval, 1, --providers, providers.json])`（`:44-58`），轮询状态到 terminal（`_status`，`:91-96`），断言 `output.md`/`worker.log`/`trace.log`。**不需要 `mw serve`**（launcher 即可 spawn worker）。

派发链事实：
- `/worker` 命令（`pm/ui-bridge.ts:1353-1450`）与 `dispatch_worker` 工具（`:965-1130`）写 task.md（`planDispatchFrontmatter`，`:880-955`）并经 `dispatchTask` 落 `_workers.parallel`；`_scratch` 跳过 docs gate（`shared/phase-docs.ts:127-128`）。`/worker` **不写 `timeout:` 头** → 走 `/worker` 时短预算只能靠 env。
- 短预算两个杠杆：task.md `timeout: <分钟>` > `PI_WORKER_TIMEOUT_MS` > 默认 60m（`worker-mode.ts:112-117`，`README.md:243`）。`launcher._stripped_env`（`launcher.py:90-113`）全量继承 env 再剥凭证，故 **serve/launcher 进程上的 `PI_WORKER_TIMEOUT_MS` 会传到 worker**；PM 窗口的 env 传不过去。
- 前置：`mw build --install`（`mw.py:_deploy_bundle:3609-3633` 拷 bundle 到全局扩展目录 + 重建 coding-agent dist），否则 worker 仍跑旧 bundle；timi 凭证（env `TIMI_API_KEY` 或 `~/.pi/agent/auth.json`，`launcher._build_env:236-245`）。

**可执行步骤草案（方案 A：镜像 test_e2e_real，最可控）**
1. 前置：`cd packages/multi-workers && python mw.py build --install`；确认 timi 凭证。
2. 新建项目 `<proj>/.agenticdoc/_scratch/workers/<key>/task.md`：
   ```
   type: review
   timeout: 2

   审查 <若干文件>，逐个读取并给出结论。重点：保持读取步数 ≥5，输出简短结论。
   ```
   （`timeout: 2` → budget 120s → anchor 60s；prompt 需保证运行 >60s 才会触发机器行。）
3. 追加队列行：`_workers.parallel` 一行 `task_key|pending|pi|timi|<abs task.md>|<now>|<now>|`（照 `mw_common.serialize_entry`，见 `test_e2e_real.py:78-88`）。
4. 启动：`python launcher.py --project <proj> --poll-interval 1 --providers packages/multi-workers/providers.json`（后台）。
5. 轮询 `<proj>/.agenticdoc/_workers.parallel` 到 `done|failed|needs-clarification`（≤180s）。
6. 断言（对应 VC-011 的 `progress_lines>=1 refusal_text=false exit_ok=true`）：
   - `<taskDir>/progress.md` 存在且 `grep -cE '^CKPT [0-9]+m \[machine\]' ≥ 1` **或** `grep -c 'worker_file' trace.log ≥ 1`（工具落盘行）。
   - 终稿文本（`output.md` 的 `## Summary` 与 `worker.log` 尾部）不含 `无法写入`、`请编排方代为追加`、`代为追加`。
   - `worker.log` 含 `[worker] done exit=0`。
   产物路径：`<proj>/.agenticdoc/_scratch/workers/<key>/{task.md,progress.md,trace.log,worker.log,output.md}`。
- 注意：若 review 任务在 60s 内完成，机器行不会触发；需 prompt 强制多步读取，或把 budget 再缩（`timeout: 1` → anchor 30s）。

**方案 B（`/worker` + `mw serve`，更贴生产）**
1. `mw build --install`。
2. `PI_WORKER_TIMEOUT_MS=120000 python mw.py start --project <proj>`（或 `serve`），确保 serve 起来（`mw.py:cmd_serve:195+` 起 launcher 子进程，继承 env）。
3. PM 窗口：`/worker pi --type review --key _scratch 审查 ...`（写 task.md 入队）。
4. 断言同方案 A 的 5-6（taskDir 在 `_scratch/workers/`）。
风险：`/worker` 的 task.md 无 `timeout:`，完全依赖 serve env；且需要 PM 窗口，人工步骤更多。**推荐把方案 A 落成 `test_e2e_real.py` 的新 `e2e_real` 用例**（复用 `launcher_proc` fixture，默认被 `pytest.ini` deselect，不污染 CI），方案 B 作为现场复现脚本。

### 6. 文档 / CHANGELOG 落点

- `packages/coding-agent/CHANGELOG.md`：`[Unreleased]` 在 `:3`，含 `### Added`(:5)、`### Changed`(:28)、`### Breaking Changes`(:32)。本 key 建议：`### Added` 一条（窄工具 `worker_file` + 检查点机器行 + 角色分化 steer）；若把 `applyRagTools` 改为消费 `activeToolsForType`，可在 `### Changed` 记「集合计算单一来源」。无 API 破坏 → 不动 Breaking Changes。
- `packages/multi-workers/CHANGELOG.md`：`[Unreleased]` 在 `:3`，含 `### Added`(:5)、`### Changed`(:33)、`### Fixed`(:41)。本 key Python 行为零改动（D-106），但 AC-010 要求该包 CHANGELOG 有对应条目 → 建议 `### Changed` 记「同步 `docs/dual-toolchain-practice-guide.md` 的 progress.md 陈述」。
- `rg -n 'progress\.md' packages/multi-workers packages/coding-agent/src` 命中 4 处：
  - `worker/worker-mode.ts:909`（注释「agent appends one CKPT line」）与 `:919`（steer 模板文本）——**本 key 直接改动点**，注释需改为「机器行由代码写、自评行按角色走 worker_file/回复」。
  - `pm/pm-orchestrator.ts:556`（发散升级消息把 progress.md 当证据）——**保持有效**（机器行 + 自评行都在该文件）。
  - `docs/dual-toolchain-practice-guide.md:367`（发散判据「无 progress.md」）——**陈述将过时**：改造后只读角色任务也会自动有 progress.md，该判据需改为「progress.md 无自评行 / 只有机器行」之类。这是 packages/multi-workers 内唯一需同步的 progress.md 陈述。
  - 测试文件 `test/extensions/agent-team-loop.test.ts:3823`（断言升级消息含 progress.md）——保持有效。
- `packages/coding-agent/docs`、`README.md`、`packages/multi-workers/README.md`/`UPDATE.md`/`dispatch-table.md` 对 `progress.md` **零命中** → 无悬空符号需清。`_arch_snapshot.md:24,25`（worker 目录文件清单 / 检查点描述）在 `.agenticdoc/` 下，**不在 AC-010 的 packages 范围内**，可选同步。

## 结论 → 决策映射

| VC | 判定方式 / 落点 | 关键证据（file:line） |
|---|---|---|
| VC-001 | `test/suite/worker-progress-persist.test.ts`：(a) fake-timer 驱动 review 任务到 anchor=60s，读 `<taskDir>/progress.md` 正则断言机器行 | `agent-team-loop.test.ts:3878,3907,4014`；`worker-mode.ts:886-925`；`checkpointAnchorMs` `:128` |
| VC-002 | 同文件：`appendProgressLine` 直调 3 次 + 预置 sentinel 断言 append-only；集成层 1 次 | `output-writer.ts:104`（appendFileSync 范式） |
| VC-003 | 同文件：`type: coding` 推到 anchor，断言 `progress.md` 不存在或无 `[machine]` | `worker-mode.ts:140`（WRITE_TOOLS）、D-104 判据 `toolsForType(type).includes("write")` |
| VC-004 | 同文件：捕获 `sent[].text`；review 断言不匹配 `/追加到.*progress\.md/` 且含替代动作；coding 断言逐字等于现模板插入值 | 现模板 `worker-mode.ts:909-924` |
| VC-005 | `test/suite/worker-file-tool.test.ts`：(b) 直调 execute 断言文件增长/新建；`[TOOL]` 行用 (c) real harness `fauxToolCall("worker_file", …)` | `rag-tools.test.ts:63-97`；`agent-team-loop-implementation-gate.test.ts:120-160`；`worker-mode.ts:770-784` |
| VC-006 | 同文件：12 项非法名 → `rejects.toThrow` + 目录文件集合不变；`[TOOL_ERR]` 用 (c) 真管道（**注意必须 throw**） | 纠错见 §2；`worker-mode.ts:786-789`；`agent-session.ts:798-806`；`agent-loop.ts:696` |
| VC-007 | `worker-progress-persist.test.ts`：逐 type `activeToolsForType(t)===toolsForType(t) ∪ (无write?["worker_file"]:[])` + 硬编码 TS 快照比对；集成断言 `activeTools()` | `worker-mode.ts:89`；`rag/tools.ts:400-407`；`autopilot-protocol.test.ts:190-219,235-260` |
| VC-008 | 跑既有 parity（不新增）：`python -m pytest test_autopilot_l0.py test_autopilot_dispatch.py test_rag_research.py -q -s` | `test_autopilot_l0.py:215-239,292`；`test_rag_research.py:71-90,134` |
| VC-009 | `npm run check` + `./test.sh`，对比 89 基线；新用例单独 `node ../../node_modules/vitest/dist/cli.js --run test/suite/<新文件>` | `AGENTS.md:31-35`；`attribution-2026-09-10.md`（本 key 触达文件不在 89 清单） |
| VC-010 | 两包 CHANGELOG `[Unreleased]` 各 1 条 + `rg progress.md` 零悬空（含 practice-guide:367 改写与 worker-mode:909 注释） | `CHANGELOG.md:3-41`；grep 命中见 §6 |
| VC-011 | `test_e2e_real.py` 新 `e2e_real` 用例（方案 A）或现场脚本（方案 B），真 launcher + timi + `timeout:`/env 短预算 | `test_e2e_real.py:31,44-96`；`launcher.py:90-113,223-331,462-490`；`mw.py:3609-3633` |

**与 design 的差异 / 修正建议（逐条）**

1. **D-109 需修正（高优先，联动 D1）**：`execute` 返回 `{isError:true}` 不会置 `tool_execution_end.isError`。窄工具非法请求必须 `throw`，否则 AC-006 的「trace.log 记录拒绝行」永不出现，VC-006 会「绿但漏证据」。建议 design D-109 改为「非法请求抛出 `Error(reason)` → pi 包成 error result → `[TOOL_ERR]`」。
2. **D-101 注册点的测试影响面需显式纳入 plan**：新增 `pi.registerTool` 会打红 4 个既有 fake-pi 测试文件（§3 清单），其中 `autopilot-protocol.test.ts` 还是 Python parity 的子进程对象；plan 必须列「同步补 `registerTool`」任务，否则 VC-008 连带红。
3. **VC-002 的 3 次检查点不必强推定时器**：`CHECKPOINT_REFRESH_MS=10m` 固定（`worker-mode.ts:108`），60m 预算下推 30/40/50m 可行但笨重；建议 VC-002 以 `appendProgressLine` 单元直调锁定 append-only，集成仅覆盖 1 次检查点。design §7 VC-002 的 Output 字段可保留，判定层次标注 L1（单元）即可。
4. **VC-011 的「短预算」在 `/worker` 路径需 env**：`/worker` 不写 `timeout:`，故短预算前置是 serve/launcher 的 `PI_WORKER_TIMEOUT_MS`；若要确定性触发机器行，方案 A（手写 task.md + 直起 launcher）优于方案 B。且 prompt 必须保证运行 > anchor，否则 VC-011 假阴性——建议 task.md 用 `timeout: 2` 且 prompt 要求 ≥5 次读取。
5. **`[TOOL] worker_file` 不含文件名**：`toolTarget()` 不认 `file` 参数；VC-005 只要求工具名行，成立。若 PM 需要「写了哪个文件」可读，需在 D1 契约补 `toolTarget` 分支（本 key 非必须，标注为可选增强）。
6. **§6 Coverage Matrix 的层级标注**：F1/F2/F3 全部可 L1 hermetic 覆盖；F5（parity）没有新的 TS 快照测试需求（Python 侧已锁，TS 侧 `autopilot-protocol.test.ts` 已锁 per-type 相等）；design 若想要「表逐项不变」的 TS 侧独立声明，可在新 `worker-progress-persist.test.ts` 里加一份硬编码 TS 白名单快照（与 `autopilot-protocol.test.ts:73-81` 的 PY_REGISTRY 镜像同构），成本一行；
