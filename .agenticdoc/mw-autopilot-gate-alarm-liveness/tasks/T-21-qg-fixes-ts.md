# T-21 — 修 QG 缺陷（TS 面）：R-1 白名单收窄 / R-2 monitor partial 静默 / R-3 吞错

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-001, AC-003, AC-012, AC-013
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t18-adversarial-qg/report.md`（**R-1 / R-2 / R-3**，含最小复现与 `path:line`）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（**阻塞必须可见**：队列不可读时显示"0 pending"是本 key 要消灭的头号静默；**真实越界写入必须仍被发现**）。
- QG 判定（`workers/mwgal-t18-adversarial-qg/report.md`，逐条对账表）：
  - **R-1（高，可构造）**：`shared/change-ledger.ts` 的 `INFRA_DIR_SEGMENTS = ["_autopilot", ".mw"]`（≈`:295`）按**路径段**豁免 ⇒ 声明写 `_autopilot/gates/gate-0007.md`、`_autopilot/_roadmap.md`、`auto-decisions.jsonl` 等**框架文件**不再进 `extra`。QG 给出的反例：coding worker 报告 `## 改动清单` 写 `- .agenticdoc/_autopilot/gates/gate-0007.md（直接应答了该 gate）` 且 trace 无写入事件 ⇒ **判为 infra、不报红**。
  - **R-2（中）**：`autopilot/monitor.ts` 在 `queueState="partial"` 且**可读 pending gate 数为 0** 时仍渲染 `gates: 0 pending`（与"真的没有 pending"无法区分）。
  - **R-3（中）**：`autopilot/status-model.ts` 的 `listGates` 对 `readdir` 非 ENOENT 失败走 `catch { return { gates: [], errors: [] } }` ⇒ **错误被吞**，`/autopilot status` 面静默 0 pending。
- 已落基线（不得回退）：T-17b 的 `INFRA_BASENAMES`（文件级清单）与运行期实证 —— `serve.meta`、`_index.parallel` 这类**框架写**的文件必须**仍**归 infra（T-16 终态曾因此被误判 4 条，其中 2 条属此列）；T-17c 的"**不存在 ⇒ 非写入**"（`unresolvable`）与 `## Ledger Unresolvable`；T-10/T-10b/T-14b 的状态面与 110 列 fit ladder 契约（DRIFT/reason/age 永不被丢、`+N` 留痕）。

## 要求

1. **R-1：把豁免从"整树"改为"文件级"**
   - 删除 `INFRA_DIR_SEGMENTS`（`["_autopilot", ".mw"]`）造成的**整树**豁免；豁免只保留**文件级**（`INFRA_BASENAMES` + 必要的 basename 正则），以覆盖**框架自身写**的文件（如 `serve.meta`、`_workers.parallel`、`_index.parallel`、`run.json`、`trace.log`、`output.md`、`report.md`、timeline/ledger、`pm-state.md` 等）。
   - **必须保证**：worker 声明写 `.../_autopilot/gates/gate-XXXX.md`（**磁盘上真实存在**的框架文件）⇒ 判为 `declared`-but-unrecorded ⇒ **报红**（这正是 QG 的反例，须转为回归用例）。
   - **必须保证**：T-16 终态那 4 条误判里属"框架写文件"的两条（`serve.meta`、`_index.parallel`）**仍归 infra**（不得因收窄而回归）。
   - 对"存在但是 worker 本不该写"的框架文件，报红是正确的**意图**：它是越界信号，不是噪音。若你认为某类文件必须豁免，必须在报告中给出**理由 + 该文件由谁写 + 为何 worker 写它不构成越界**。
2. **R-2：`partial` + 0 可读不得渲染成"0 pending"**
   - 面板必须把"**真的 0 个 pending**"与"**读不到（n 个失败）**"区分开：后者必须显式显示不可读状态（含失败计数/samples），且在 110 列预算内**不被丢**（可压缩编码，但不得消失）。
   - 不得违反既有契约：`reason`/DRIFT/age 三件套、`+N` 留痕、`GateView` 精确锁（`autopilot-console.test.ts:384-389`）不得动。
3. **R-3：错误不得被吞**
   - `status-model.listGates`（或等价路径）遇到 `readdir` 失败必须把错误**暴露到可见面**（`errors` 非空 ⇒ console/monitor 可见），**不得**静默返回空队列；区分"空目录"（合法 0 pending）与"读不到"。
4. **回归测试（必须内建，含 QG 的最小复现）**：① R-1 反例 ⇒ 报红；② `serve.meta`/`_index.parallel` ⇒ infra（不回归）；③ T-17/T-17b/T-17c 既有语料全绿；④ R-2：partial + 0 可读 ⇒ 面板显式不可读（非 "0 pending"）；⑤ R-3：非 ENOENT readdir 失败 ⇒ errors 可见；⑥ 空的 gates 目录 ⇒ 合法 "0 pending"（不得误报不可读）。
5. 不新增 config 键（AC-011）；不放宽既有判据（P-03）；不改 `GateView`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
- 新增：`packages/coding-agent/test/suite/mwgal-t21-qg-fixes.test.ts`
- 既有 TS 测试中因本卡行为必须更新的期望（逐条说明；不得改弱断言）

## 写入禁止面

- `packages/multi-workers/**`（T-22 正在改 Python 面）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/**`
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`（**逐条核对输出的 `Test Files N passed (N)` 与预期文件数一致**）：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t21-qg-fixes.test.ts test/suite/mwgal-t17-ledger-role-aware.test.ts test/suite/mwgal-t17b-ledger-infra-writes.test.ts test/suite/mwgal-t17c-ledger-unresolvable.test.ts test/suite/mwgal-t10-state-surface.test.ts test/suite/mwgal-t10b-presentation-budget.test.ts test/suite/mwgal-t14b-monitor-blocker-class.test.ts test/suite/autopilot-console.test.ts test/suite/autopilot-gate-presentation.test.ts`

## 改动历史

（填写：豁免从整树到文件级的边界、被明确判为"必须报红"的框架文件清单及理由、R-2 不可读状态的呈现形态与预算处理、R-3 错误暴露路径、回归语料对照。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 证据`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
