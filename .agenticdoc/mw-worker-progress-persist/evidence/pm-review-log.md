# PM 复核日志（mw-worker-progress-persist）

只记 PM 亲自执行/复核的动作与结论；worker 自述不作为证据。

## T-1 写入器（output-writer.ts）

- 复核方式：PM 独立重跑 `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-progress.test.ts` → 5 passed；逐行读 diff（`formatMachineCheckpoint` / `appendProgressLine`），确认复用既有 `outputDir()` 目录守卫、纯 `appendFileSync`、无截断路径。
- 结论：PASS。`[VERIFY] VC-001: progress_exists=true machine_lines=1` / `[VERIFY] VC-002: machine_lines=2 sentinel_first=true`。

## T-2 窄工具（worker-file-tool.ts）

- 复核方式：PM 独立重跑 `--run test/extensions/agent-team-loop-worker-file-tool.test.ts` → 9 passed；全文读 `worker-file-tool.ts` + 测试文件关键段（12 项反例循环、schema 层 `Compile(...).Check`、`rejects.toThrow` 断言）。
- 逐项核对与 design 一致性：
  - `WORKER_FILE_NAME_RE` 无 `g` 标志（`.test()` 无 `lastIndex` 状态）、`$` 无 `m`（拒结尾换行）→ D-102 成立。
  - 失败形状为 `throw`（不是返回 `isError` 对象）→ D-109 成立（RQ-D1 F1 的坑已避开）。
  - `mode` 默认值在 `execute` 内落地；64 KiB 用 `Buffer.byteLength`；拒绝路径在任何 `fs.*` 之前（实测不建 taskDir、不建文件、不截断）→ P-003 规避成立。
  - 12 项反例在 regex、写层、execute、schema 四层均拒；写前后目录集合相等、既有 `progress.md` 内容不变。
- 结论：PASS。

## 残留（本 key 不改，登记以免静默改变语义）

| ID | 内容 | 处置 |
|----|------|------|
| R-4 | 窄工具落盘不计入 `writes`（D-108 有意设计），只读角色 `writes=0` 会让 `computeRisk` 可能持续判 `mid/high` | 保留既有 GC-4 语义；`progress.md` 自评行与 trace `[TOOL] worker_file` 提供区分证据；已在 design §9 与 practice guide §7 注明口径 |
| R-5 | `writeWorkerFile` 的写层不重复校验 `content` 非空（空内容 append 会写入 0 字节、`mode:"write"` 会清空既有报告）；非空由 schema `minLength: 1` 保证 | 真实调用必经 pi 的 TypeBox 校验（`validation.ts:287/304`），schema 层已断言拒绝；写层守卫只覆盖「文件名白名单」这一安全属性。若日后出现绕过 schema 的调用方需补写层守卫（另开 key） |

## T-3 接线（worker-mode.ts + rag/tools.ts + 4 个既有测试）

- 复核方式：PM 逐行读 `git diff`（`worker-mode.ts` +97/-...、`rag/tools.ts` 6 行）；PM 独立重跑新测试（9 passed）与 Python parity 4 文件（28 passed）。
- 逐项核对：
  - `activeToolsForType` 只在 `!base.includes("write")` 时追加 `worker_file`；`TOOL_ALLOWLISTS`/`toolsForType` 逐字未动（diff 中无相关 hunk）。
  - `rag/tools.ts` 的 `:402`（`rt === null`）与 `:406`（RAG enabled）两分支都换成 `activeToolsForType`，RAG 工具名计算未变。
  - `checkpointSteerText` 两分支：写角色文本与 `git show HEAD` 基线同值渲染 `identical=true`（worker 给的完整文本与旧模板逐字一致）；无写角色不再出现「追加到」指令，改为 `worker_file` / 回复行；`deliverAs: "followUp"` 两分支均保留。
  - 机器行只在 `!hasWriteTools` 时追加（D-104）；写路径不产生 `[machine]` 行 → `type: coding` 用例断言 `machine_lines=0` 成立。
  - 注册点在 RAG `try/catch` 之后、`before_agent_start` 之前，且仅在 `!hasWriteTools` 时调用（`worker-mode.ts:722-730`）。
  - `toolTarget` 取值链末尾追加 `file`（`worker-mode.ts:374-390`），`[TOOL]` 行因此带目标 basename；对既有 `path/command/pattern/query` 优先级无影响。
  - 4 个既有 fake-pi 测试：3 个只加 1 行 `registerTool: () => {}`；`autopilot-protocol.test.ts` 另加只读类型期望集中的 `worker_file`（+23/-... 行），既有断言与 `test_autopilot_l0.py:313-318` 要求的三个子串保留。
- PM 额外核验（worker 未覆盖、由 PM 自己读源码判定）：**schema 层拒绝也会落 `[TOOL_ERR]`**——非法文件名在 `execute` 之前就被 TypeBox 拦下，走 `agent-loop.ts:508-514`（`preparation.kind === "immediate"` → `emitToolExecutionEnd(finalized)`，`isError` 来自校验失败），因此 AC-006「拒绝可追溯」对「非法文件名」与「execute 抛错」两条路径都成立。T-3 的真管道用例只覆盖了 oversize 路径（非法文件名到不了 execute），这一点已记入 T-6 的必查项。
- PM 额外核验：read-scope 拦截器（`worker-mode.ts:761-790`）对 `read/ls/find/grep` 之外的 tool 直接 `return undefined` → `worker_file` 不会被 read scope 误拦（分区任务也能用窄工具落盘）。
- 偏离（可接受，记录）：新测试落点为 `test/extensions/agent-team-loop-checkpoint-wiring.test.ts`（design §3 曾建议 `test/suite/`；包内单一 vitest config，同一文件已直接 import `../suite/harness.ts`，无功能差异）；`hasWriteTools` 在激活期算一次并复用。
- 结论：PASS。

## T-5 真模型冒烟（VC-011）

- 复核方式：PM 直接读临时项目的真实产物（不依赖 worker 转述）：
  - `C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5/.agenticdoc/_scratch/workers/mwpp-smoke-review-b/progress.md` 两行：第 1 行 `CKPT 1m [machine] ts=2026-09-23T08:49:18.818Z reads=16 writes=0 phases=- repeat_top=2 risk=high`（框架写入），第 2 行是模型自己的 `CKPT 1m converging=yes eta≈0m …`（经 `worker_file` 追加）。
  - `trace.log` 尾部：`[FLOW] tool_call worker_file` + `[TOOL] 2026-09-23T08:49:25.856Z worker_file progress.md` + `[END] exit=0`。
  - 终稿扫描 `rg -n '无法写入|代为追加|PM 代记' output.md` → 无命中（退出码 1）；worker 另做了正对照（对照组文件命中），证明扫描本身有效。
  - 真模型：timi / deepseek-v4.1-flash；成本一次短任务。
- 结论：PASS。这是本 key 最关键的外部证据：同一场景（只读 review 角色）既落了框架机器行，也落了模型自评行，且终稿不再要求 PM 代为追加。
- 新发现（已回写任务书）：`PI_WORKER_TASK` 必须是**绝对 task.md 路径**（worker-mode 做 `path.resolve()` + `existsSync`，相对值会在任何 agent turn 前 `exit 1`）。
- R-4 得到实测印证：只读角色 `reads=16 writes=0` 仍判 `risk=high`（判据未变，属既有 GC-4 语义）。

## 其它

- design 的两处修订（D-102 分隔符放宽、D-109 失败形状）与 §4.1 收紧项来自 RQ-D1 实测，不是实现者事后适配；修订前后均有 file:line 证据。
