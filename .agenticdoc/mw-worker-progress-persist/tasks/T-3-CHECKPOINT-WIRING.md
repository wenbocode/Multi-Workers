# Task T-3: 检查点接线与角色分化

## 元信息
- Stage: 2
- 依赖: T-1（`appendProgressLine`/`formatMachineCheckpoint`，已落地）、T-2（`WORKER_FILE_TOOL`/`registerWorkerFileTool`）
- 风险: 高（触及 coding 角色既有 steer 文本、active tool 集合计算、4 个既有 fake-pi 测试文件的期望集）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-007, AC-008]
- vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-007, VC-008]

## 背景（实测）

- `worker-mode.ts:886-924` `writeCheckpoint()`：先 `appendCheckpoint`（trace.log `[CHECKPOINT]`，`:899-907`），再无条件 steer（`:915-923`，`deliverAs:"followUp"`）「请立即自评收敛性，把一行追加到 `${taskDir}/progress.md`」——对只读角色是不可能完成的指令（事故根因）。注释在 `:909-914`，文本在 `:916-922`。
- `worker-mode.ts:926-933` `scheduleCheckpoint`（锚点 `min(30m, budget/2)`，刷新 `CHECKPOINT_REFRESH_MS=10m`）；deadline steer 在 `:940-945`（`deliverAs:"steer"`，**不要动**）。
- `worker-mode.ts:138-140`：`READ_TOOLS`/`WRITE_TOOLS`；`:776-781` 计数分支；`toolTarget` 在 `:333-345`（只认 `path`/`command`/`pattern`/`query`）。
- `worker-mode.ts:49-90`：`TOOL_ALLOWLISTS` 与 `toolsForType` 被 `packages/multi-workers/test_autopilot_l0.py:215-239`（正则解析 TS 源）+ `:292`（源码子串断言）锁定 parity；`test/suite/rag-research-doc.test.ts:37,107` 直接 import `toolsForType` → **函数体与导出名逐字保留**。
- `rag/tools.ts:22`（import）、`:400-407`（`applyRagTools`，`:402` 为 `rt === null` 分支、`:406` 为 RAG enabled）——**两分支都要改**。
- pi 核心：`registerTool → refreshTools → agent-session.ts:2527-2546` 会自动把新注册工具加入 active 集合 → 最终集合由 `before_agent_start` 的重算保证，**断言必须在 `before_agent_start` 之后**（范式 `test/suite/autopilot-protocol.test.ts:252-253`）。
- 注册点精确锚点：`workerTaskDir` 在 `:667`，RAG `try/catch` 在 `:668-677` → 新注册调用放在 **`:677` 之后、`:697` 的 `before_agent_start` 之前**。
- 开工前必读：`evidence/research/design-verify-collection-parity-2026-09-23.md`（F1~F6）、`evidence/research/design-verify-tool-contract-2026-09-23.md`（F1/F2/F5）、`evidence/research/design-verify-test-harness-2026-09-23.md`（§2 harness 形态、§3 必改测试清单、§6 文档落点）。

## 交付物

1. `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
   - 新增 `export function activeToolsForType(type: string): string[]`：`toolsForType(type)`，当结果**不含** `write` 时追加 `WORKER_FILE_TOOL`。`toolsForType` 与 `TOOL_ALLOWLISTS` 逐字不动。
   - 新增 `export function checkpointSteerText(opts: { elapsedMs: number; budgetMs: number; progressPath: string; hasWriteTools: boolean; narrowTool: string }): string`：
     - `hasWriteTools === true`：渲染结果必须与改造前模板**逐字相等**（含 `formatHeartbeatAge`、`Math.round(elapsedMs/60_000)`、`path.join(taskDir,"progress.md")` 的运行时替换）；
     - `hasWriteTools === false`：不得出现「追加到 …progress.md」写入指令；声明检查点证据已由框架写入 `progressPath`，给出替代动作（用 `narrowTool` 追加自评行，或在回复中给出一行 `CKPT <n>m converging=yes|no eta≈<X>m <理由>`）；发送时 `deliverAs` 仍为 `"followUp"`（`agent-team-loop.test.ts:4032` 依赖该值）。
   - `writeCheckpoint()`：判据 `hasWriteTools = toolsForType(meta.type).includes("write")`；无写工具时先 `appendProgressLine(meta.taskKey, meta.agenticdocRoot, formatMachineCheckpoint({...}))`（字段与既有 `appendCheckpoint` 调用一致：elapsedMs/reads/writes/phases/repeatTop/risk），再发送 `checkpointSteerText(...)`。
   - 仅当 `!hasWriteTools` 时在 `:677`~`:697` 之间调用 `registerWorkerFileTool(pi, workerTaskDir)`。
   - 更新 `:909-914` 注释为「机器行由代码写；自评行按角色走 worker_file 或写在回复里」。
   - `toolTarget`（`:333-345`）：为 `worker_file` 补 `file` 取值，使 `[TOOL]` 行带目标文件名（对既有工具无影响）。
   - **不得**把 `WORKER_FILE_TOOL` 加进 `WRITE_TOOLS`（D-108）。
2. `packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts`
   - `:22` import 改为 `activeToolsForType`；`applyRagTools` 的 `:402` 与 `:406` 都改用 `activeToolsForType(type)`。RAG 工具名计算与语义不变。
3. 既有测试同步（**必须与实现同批**，否则 `test_autopilot_l0.py:296-311` 的子进程 vitest 会红 → VC-008 连带红）：
   - 仅需给下列 4 个 fake-`pi` 补 `registerTool: () => {}`（它们会激活无写角色）：`test/suite/autopilot-protocol.test.ts:190`、`test/suite/autopilot-read-scope.test.ts:410`、`test/suite/cross-drive-worker.test.ts:37`、`test/suite/dual-root-worker.test.ts:34`。
   - `test/suite/autopilot-protocol.test.ts` 还需把只读类型（verifier/reviewer/review/research）的 active 集合期望改为「原期望 + `worker_file`」（`:234-260`、`:335-355`）；**保留** `test_autopilot_l0.py:313-318` 要求的三个子串（`fails closed`、`GC-8/AC-012`、`exactly equal to the Python REGISTRY`）。
   - 已具备 `registerTool` 或只用 `type: coding` 的文件**不要动**（`rag-required.test.ts:93`、`rag-e2e-slow.test.ts:82`、`agent-team-loop.test.ts:4143`、`worker-tree-kill*.test.ts`、`agent-team-loop-output.test.ts`、watchdog `:3878` 的 `fakeWorkerPi`）。
4. 新增测试 `packages/coding-agent/test/extensions/agent-team-loop-checkpoint-wiring.test.ts`
   - **VC-001/002/003/004**：复用 `test/extensions/agent-team-loop.test.ts:3878`（`fakeWorkerPi`）与 `:3907`（`startWatchdogTask`）的形态：`vi.useFakeTimers()`；task.md 用 `type: review\ntimeout: 2\n`（budget=120s → anchor=60s）；推进定时器时**必须持续 `emit("message_update")` 喂活动**（否则 60s idle watchdog 先杀，见 `:4014-4048` 的 trickle 写法）；到 anchor 后读 `<taskDir>/progress.md` 断言机器行正则；`sent` 里 `[mw checkpoint]` 文本不含 `/追加到.*progress\.md/` 且含替代动作；`type: coding` 同法推 anchor 断言无 `[machine]` 行。
   - **VC-002 的 append-only 半侧**：用 T-1 已落地的 `appendProgressLine` 直调（预置 sentinel + 追加），集成层只覆盖 1 次检查点（不必推 3 次 10m 刷新）。
   - **VC-007**：逐 type（含 `rag-research`）断言 `activeToolsForType(t)` 的组合关系；并在 fake-timer 驱动里于 `before_agent_start` **之后**断言最终 active 集合；附一份硬编码的 TS 白名单快照（10 key，同 `test_autopilot_l0.py` 解析结果）。
   - **VC-005/006 的 trace 证据行**：用真 pi 管道 harness（`test/suite/harness.ts::createHarness` + `fauxToolCall("worker_file", …)`，范式 `test/suite/agent-team-loop-implementation-gate.test.ts:120-160`）断言 `[TOOL] worker_file`（合法）与 `[TOOL_ERR] worker_file`（非法，**依赖 T-2 的 `throw`**）落进 trace.log。若该 harness 成本过高，可在报告中说明并交 T-5 冒烟覆盖，但不得静默跳过。
   - `[VERIFY]` 行用 `process.stdout.write("…\n")`。
5. 新增 Python parity 快照用例 `packages/multi-workers/test_mwpp_collection_parity.py`：`from test_autopilot_l0 import _parse_ts_allowlists`（复用 helper，不得复制实现），硬编码 10-key 改造前快照（见 RQ-D2 F5）并断言逐项保序相等；**不得修改 `test_autopilot_l0.py`**（`test_rag_research.py:128-136` 有「L0 逐字节未改」守卫）。

## 约束

- 只改/新增上列文件；不改 `output-writer.ts`（T-1）、`worker-file-tool.ts`（T-2）、`dist/**`、fixtures/golden、`test_autopilot_l0.py`、`docs/**`（文档交 T-4）。
- 既有测试的改动只允许「补 `registerTool` stub + 只读类型期望集加 `worker_file` + 保留既有子串」，不得删除/放宽既有断言。
- 不重排/不美化既有代码（避免大 diff 掩盖行为变更）。
- TS 只用可擦除语法；无 `any`；无 inline `import()`。
- 不 commit；不运行 `mw build`；注意 `npm run check` 内含 `biome check --write`（会格式化），跑前确认工作区只含本 key 的预期改动。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-checkpoint-wiring.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-output.test.ts test/suite/autopilot-protocol.test.ts test/suite/autopilot-read-scope.test.ts test/suite/cross-drive-worker.test.ts test/suite/dual-root-worker.test.ts test/suite/rag-tools.test.ts test/suite/rag-research-doc.test.ts
cd ../multi-workers && python -m pytest -q -s test_autopilot_l0.py test_autopilot_dispatch.py test_rag_research.py test_mwpp_collection_parity.py
cd H:/git/Multi-Workers && npm run check
git diff --stat -- packages/multi-workers/test/fixtures packages/multi-workers/test_autopilot_l0.py   # 必须为空
```

## 报告要求

最终消息给出：改动/新增文件清单、`git show HEAD:` 基线与新 coding 分支渲染文本的逐字比对结论、无写工具分支的 steer 原文、`activeToolsForType` 逐 type 表、4 个既有测试每个「改了什么/保留了什么」、Python parity 快照结果（27+ 用例计数）、机器行样例与 `[VERIFY]` 行原文、trace 证据行是否覆盖及方式、任何偏离 design 的实现细节。
