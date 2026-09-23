# 质检报告：mw-worker-progress-persist

日期：2026-09-23　阶段：VERIFY → DONE　PM 窗口：`WENBOZHOU-PC4:93144`

## 1. 结论

**通过（PASS-with-gaps 已收口）**。11 条 AC 全部有机器证据；11 条 VC 逐条独立复现；3 条核心守卫经变异反例验证（全部变红 + 逐字节复原）；真模型端到端冒烟 PASS。

遗留（登记不修、均有理由）：

| ID | 内容 | 影响 | 处置 |
|----|------|------|------|
| R-4 | 窄工具落盘不计入 `writes`（D-108 有意设计），只读角色 `writes=0` 使 `computeRisk` 仍可能判 `mid/high` | PM 升级判据偏保守（实测冒烟 `reads=16 writes=0 risk=high`） | 判据不变（GC-4）；`progress.md` 自评行 + `[TOOL] worker_file` 提供区分证据；已写入 design §9 与 practice guide §7 |
| R-5 | `writeWorkerFile` 写层不重复校验 `content` 非空（空内容由 schema `minLength: 1` 拦） | 真实调用必经 pi 的 TypeBox 校验 | 写层守卫只覆盖安全属性（文件名白名单）；已在 PM 复核日志登记 |
| — | ~~未执行 `mw build --install`~~ **已于 2026-09-23 17:07 执行**（用户授权）：`python mw.py build --install` EXIT=0；全局 bundle 与仓库 bundle SHA256 相同（`A7FCC952…64C`）、含 `worker_file`×5 / `[machine]`×1；用已安装 bundle 真模型 re-smoke PASS（机器行 + `[TOOL] worker_file report.md` + `[TOOL] worker_file progress.md` + `exit=0`） | 已关闭 |

## 2. 交付面（写入范围）

| 文件 | 类型 | 内容 |
|------|------|------|
| `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts` | 改 | `formatMachineCheckpoint` / `appendProgressLine`（纯追加） |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts` | 新 | 窄工具 `worker_file`（basename-only、单一来源正则、`throw` 失败形状） |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 改 | `activeToolsForType`、`checkpointSteerText`、机器行落盘、条件注册、`toolTarget` 带文件名、注释 |
| `packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts` | 改 | 两分支改用 `activeToolsForType`（集合计算单一来源） |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | 改 | 升级消息措辞（只读角色另有框架机器行） |
| `packages/coding-agent/test/extensions/agent-team-loop-worker-progress.test.ts` | 新 | VC-001/002 单元 |
| `packages/coding-agent/test/extensions/agent-team-loop-worker-file-tool.test.ts` | 新 | VC-005/006 工具层（12 反例 × 4 层） |
| `packages/coding-agent/test/extensions/agent-team-loop-checkpoint-wiring.test.ts` | 新 | VC-001~007 + 真管道 `[TOOL]`/`[TOOL_ERR]`（含 schema 拒绝路径） |
| `packages/coding-agent/test/suite/{autopilot-protocol,autopilot-read-scope,cross-drive-worker,dual-root-worker}.test.ts` | 改 | `registerTool` stub + 只读类型期望集（保留既有断言与三子串） |
| `packages/multi-workers/test_mwpp_collection_parity.py` | 新 | 10-key TS 白名单快照（复用 `_parse_ts_allowlists`） |
| 两包 `CHANGELOG.md` `[Unreleased]` | 改 | coding-agent `Added` / multi-workers `Changed` |
| `packages/multi-workers/docs/dual-toolchain-practice-guide.md` §7 | 改 | 发散判据改写 + 只读角色口径 |

零 Python 行为改动；`TOOL_ALLOWLISTS` / `toolsForType` / `test_autopilot_l0.py` 逐字未动；未 commit。

## 3. AC ↔ 证据

| AC | 证据 | 判定 |
|----|------|------|
| AC-001 | `[VERIFY] VC-001: progress_exists=true machine_lines=1`（fake-timer review 驱动到锚点） | PASS |
| AC-002 | `[VERIFY] VC-002: machine_lines=1 sentinel_first=true` + `machine_lines=3 sentinel_first=true`（append-only 单元直调） | PASS |
| AC-003 | `[VERIFY] VC-003: machine_lines=0`（`type: coding` 同锚点无机器行） | PASS |
| AC-004 | `[VERIFY] VC-004: writeless_write_instr=false coding_identical=true`；T-6 用 `git show HEAD` 基线归一化比对 `NORMALIZED_EQUAL: true`（132 字符逐字同） | PASS |
| AC-005 | `[VERIFY] VC-005: append_ok=true report_ok=true tool_line=true`（真管道 `[TOOL] worker_file progress.md`） | PASS |
| AC-006 | `[VERIFY] VC-006: rejections=12 new_files=0 schema_rejections=12`；真管道 `[TOOL_ERR] worker_file`（execute 抛错 + schema 拒绝两条路径各一例）；目录集合不变 | PASS |
| AC-007 | `[VERIFY] VC-007: table_unchanged=true extra_only_writeless=true types=10` | PASS |
| AC-008 | Python parity 4 文件 28 passed；`test_autopilot_l0.py` 逐字节未改（守卫断言空） | PASS |
| AC-009 | `npm run check` EXIT=0；受影响面 10 文件 94 passed / 1 skipped（T-6 独立跑 13 文件 430 passed + 8 文件 83 passed/1 skipped）；Windows 89 项基线不含本次触达文件 | PASS |
| AC-010 | 两包 CHANGELOG `[Unreleased]` 各有条目；`rg 'progress\.md'` 全部命中逐处核对成立（`pm-orchestrator.ts:556` 措辞已同步） | PASS |
| AC-011 | 真模型 `timi/deepseek-v4.1-flash` `type: review`：`progress.md` 机器行（框架）+ 自评行（模型经 `worker_file`）、终稿无「无法写入/代为追加」、`exit=0` | PASS |

## 4. 独立验证（T-6）与变异反例

- T-6 判定：**PASS-with-gaps**（11/11 VC，9 PASS + 2 PASS-with-note，0 FAIL）。
- M-1 放宽正则 → `worker-file-tool.test.ts` 6 failed；M-2 去掉角色门禁 → `checkpoint-wiring` VC-003 红；M-3 把 `worker_file` 塞进 `TOOL_ALLOWLISTS.review` → 新 Python 快照用例 + `test_autopilot_l0.py::test_vc023_worker_fail_closed` 双红。三处复原后 sha256 与改前逐字节相等（`git status` 起止逐行相同）。
- T-6 提出的 G1（schema 拒绝路径缺真管道用例）已由 PM 补齐：`agent-team-loop-checkpoint-wiring.test.ts` 新增用例（`file: "task.md"` → `isError=true` + `[TOOL_ERR] worker_file` + `task.md` 内容与目录集合不变），现 10/10 绿。G2（证据文件字节数笔误 672→571）已改；G3（`pm-orchestrator` 措辞）已改并回归 170 passed；G4 = R-4。

## 5. 关键根因与设计修正（写进证据，便于复用）

1. **`AgentToolResult` 没有 `isError` 字段**：返回 `{isError:true}` 会被忽略，`tool_execution_end.isError` 只在 `execute` 抛错（`agent-loop.ts:696-704`）或校验失败（`:508-514`）时为 true。窄工具必须 `throw`，否则拒绝留痕永不出现。
2. **TypeBox schema 默认不拒额外字段、`Value.Convert` 不套用 `default`**：`additionalProperties:false` 与 `mode` 默认值都必须在代码里落地。
3. **`maxLength` 计 UTF-16 code unit**：64 KiB 上限必须用 `Buffer.byteLength`。
4. **`PI_WORKER_TASK` 必须是绝对 task.md 路径**：相对值会在任何 agent turn 之前 `exit 1`（冒烟中实测）。
5. 新增 `registerTool` 会打红 4 个既有 fake-pi 测试（其中 `autopilot-protocol.test.ts` 还是 Python parity 的子进程对象），必须同批同步。

## 6. 未做/未覆盖

- ~~未 `mw build --install`~~ 已执行并复验（见 §1 残留表末行）：源码与 bundle 两条路径都有真模型 PASS 证据。
- 未跑全量 `./test.sh`（按仓库纪律用定向命令 + `npm run check`；T-6 覆盖受影响面）。
- 未提交。
