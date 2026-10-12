# T-20 回执：G6-B 运行身份 + 产物自带终态（run.json）

- key: `mw-gate-verdict-hardening` · 日期: 2026-10-10 · 基线 HEAD: `776b82d7f`
- 执行方式：**PM 直执**（D-014 硬门禁批次内）
- 覆盖 AC：**AC-022**（产物自带终态 / 身份不可复用），并补齐 **AC-019** 的可见性条款（T-19 卡第 3 项）
- 对应 IN-3 放大器：**F2**（派发判据只看台账行 ⇒ 已终态任务复活）、**F4 的后果面**（台账 `done` 而重跑进程仍在写 `output.md`）

---

## 1. 变更清单

| 文件 | 变更 | 关联 |
|---|---|---|
| `.../shared/run-store.ts`（**新**，9.3 KB） | `runPath` / `readRunState`（坏 JSON ⇒ 无信息）/ `runStateKind` / `isTerminalRunStatus` / `newRunId` / `runMarker` / `collectArtifacts` / `writeRunState`（原子 + best-effort + `trace.log` 留痕）/ `parseSupersedes` / `evaluateRunIdentity` | AC-022 |
| `.../worker/worker-mode.ts` | 启动写 `running`（`run_id`/`owner_key`/`kind`/`pid`/`supersedes`/`started_at`）；`finishRun()` 在**每条退出路径**写终态（`recordEnd` / 两条启动拒绝 / `process.on("exit")` 兜底）；心跳刷新 `last_heartbeat_at`；`markOutcome()` 让 `output.md` marker 与落盘状态永不分叉；`task.md` 只读一次（复用给 read-scope parent root） | AC-022、R15 |
| `.../worker/output-writer.ts` | `WriteOutputOpts.runMarker`（**范围变更**，见 §4 偏离 2）：写进 **harness 段首行**，不夺占 agent 写的机器可读首行 | D-117 兼容 |
| `.../shared/worker-store.ts` | `WorkerStatus` += `lost` | 跨语言一致性 |
| `.../pm/pm-orchestrator.ts` | `DispatchScanOptions.runState` → **`runVerdict`**（懒读 `task.md`）；`agent_settled` 接真实 `evaluateRunIdentity`；告警新增 **`out-of-scope`** 与 **`run-ledger-conflict`**；`flushScanAlarms()` 在 `finally` 前统一发（覆盖 early return）；`isTerminal` += `lost` | AC-022、AC-019 |
| `.../pm/ui-bridge.ts` | `lost` 全表面：字形 `!`、ack 可受理、进入「unhandled 待处理区」、状态排序/聚合、终态详情行（Exit Reason → worker.log 尾巴 → 兜底文案） | D-022 可见性 |
| `packages/multi-workers/launcher.py` | `_reconcile_orphans` 判据加序：`[END]` → **`run.json` 终态**（台账只是滞后）→ **`run.json` 活动 ⇒ `lost`**（有 `output.md` 即时判定，否则仍走静默窗口 + 另一活 launcher 让位）→ `output.md` ⇒ `failed`（原样）→ 静默 ⇒ `failed`（原样） | AC-022 |
| `packages/multi-workers/mw_common.py` | 新 `mark_run_lost()`（**launcher 唯一允许**的 run.json 写入：只加 `status=lost` + `ended_at`，保留 `run_id`/`artifacts`/`supersedes`/`pid`，丢弃陈旧 `exit`）；`_TERMINAL_STATUSES`（两处）+= `lost` | AC-022 |

新增/扩展测试（**22 例**）：

- `test/suite/run-store.test.ts`（**新 15 例**）：无信息语义、终态/活动/未知分类（含未来状态不楔死派发）、原子写 + 失败不抛 + 留痕、`run_id` 唯一性与 marker、`supersedes` 头解析（不吃正文里的同名字样）、`evaluateRunIdentity` 全矩阵 + 懒读断言。
- `test/suite/worker-run-identity.test.ts`（**新 6 例**）：启动 `running` 身份、settle 写 `done`+marker、**agent 写的 `VERDICT=` 首行不被夺占**、`supersedes` 落进记录、启动拒绝写 `failed` 终态、run.json 不可写时 `output.md` 仍落盘（R15）。
- `test/suite/worker-dispatch-guard.test.ts`（+5 例）：terminal/live 候选拒绝 + 冲突告警、真实 `pmActivate` 接线的四种场景（终态拒派、活动拒派、`supersedes` 放行且旧目录字节/mtime 不变、supersede 目标未终态拒派）、`out-of-scope` 聚合告警。
- `packages/multi-workers/test_run_identity.py`（**新 9 例**）：跨语言终态集恒等、`lost` 进台账终态集、`read_run_status` 认 worker 写的形状、坏记录无信息、`mark_run_lost` 保留现场/丢陈旧 exit/失败安全。
- `packages/multi-workers/test_launcher.py`（+7 例，`TestReconcileRunState`）：run.json 终态收敛滞后台账（含 `needs-clarification`）、活动 + output.md ⇒ `lost`（并写回 run.json，产物字节不变）、活动 + 无 output + 陈旧 ⇒ `lost`、活动 + 新鲜 ⇒ 不动、`[END]` 胜过陈旧 `running`、`lost` 属台账终态。

## 2. 设计要点

1. **单一写者**：worker 写 `running` 与全部终态；launcher **只能**补 `lost`（D-023）。PM 侧不写 `pending`（见 §4 偏离 4）。
2. **读侧只认证据**：`readRunState` 对缺失/坏 JSON/非对象/无 `status` 一律「无信息」，未知状态串也归为无信息（未来新增状态不会楔死派发）；「无信息」= 与 T-20 之前完全相同的行为（零回填，P-018）。
3. **拒派方向 fail-closed**：自己的 `run.json` 终态 ⇒ 拒（同一 task_key 只跑一次）；自己的 `run.json` 活动 ⇒ 拒（丢失的台账行不能变成第二个写者）；`supersedes: X` 而 X 未知/未终态 ⇒ 拒（活着的运行不得被静默替换）。
4. **marker 与状态同源**：`markOutcome()` 在产物写之前把结果映射进内存状态，marker 与 `run.json` 不可能一个说 `done` 一个说 `running`（IPC 之前那个 `status=running` 的分叉就是这条修掉的）。
5. **告警不刷屏**：`out-of-scope` / `run-ledger-conflict` 都按「每次扫描聚合一条 + 接线侧每 session 每 kind 一次」；`run-ledger-conflict` 的 detail 带**去重后的原因集合**（`run-terminal` / `run-active` / `supersede-unknown` / `supersede-not-terminal`）与前 3 个 task_key。
6. **只读面零写盘**（真实项目实测见 §5）：doctor 不建 run.json、不碰产物。

## 3. `[VERIFY]` 实测

```
cd packages/multi-workers
python -X utf8 -m pytest test_run_identity.py -q -p no:randomly            → 9 passed
python -X utf8 -m pytest test_launcher.py -q -p no:randomly -k Reconcile   → 7 passed（TestReconcileRunState）
python -X utf8 -m pytest test_run_identity.py test_launcher.py -q -p no:randomly
                                                                           → 102 passed
python -X utf8 -m pytest -q -p no:randomly                                 → 2 failed / 1423 passed / 10 deselected
                                                                             （2 红 = 开工前基线既有红）

cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/run-store.test.ts
                                                                           → 15 passed
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-run-identity.test.ts
                                                                           → 6 passed
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-guard.test.ts
                                                                           → 16 passed
node ../../node_modules/vitest/dist/cli.js --run <34 个导入 status-model/pm-orchestrator/
    worker-store/ui-bridge/run-store/worker-mode 的测试>                     → 33 passed | 1 skipped（exit 0）
                                                                             Tests 488 passed | 2 skipped
npm run check                                                              → 通过（exit 0，No fixes applied）
```

**基线对照**：开工前 Python 红集 = `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` +
`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`，本次全量跑的二红与之完全一致。

## 4. 与卡片的偏离（逐条记录，均有理由）

| # | 卡片原文 | 实际实现 | 理由 |
|---|---|---|---|
| 1 | 「`done` 且**无 `supersedes`** ⇒ 拒派」（暗示同目录 + `supersedes` 可重跑） | 自己目录终态 ⇒ **一律拒**；`supersedes` 只作用于**被替换的那个目录**（新 task_key 是新目录） | 用户要求③ + 事故实证：`msc-t14` 的台账行 `11:20:40` 已 `done`，重跑进程仍在 `11:45:40` 覆写它的 `output.md`。允许同目录重跑就是把「产物被改、无人知道哪份是终稿」制度化 |
| 2 | 「`output.md` **首行**写 `<!-- mw-run: … -->`」 | marker 写在 **harness 段首行**：空产物时就是文件首行；agent 自己写过产物时，harness 段在 `---` 之下 | D-117 契约：agent 写的 `VERDICT=`/`TASKS=` 必须是文件首行（`test/extensions/agent-team-loop.test.ts:445` 精确断言）。marker 夺占首行会静默破坏 L3 判定读取 |
| 3 | 卡片 `isTerminal(state)` 写作 `done\|failed\|lost` | 终态集 = `done\|failed\|needs-clarification\|lost`（TS + Python 恒等） | `needs-clarification` 同样是 worker 自己宣告的结束态，必须与 Python `RUN_TERMINAL_STATUSES`（T-18 已落地）一致，否则两侧判据分叉 |
| 4 | 设计 §11.2 伪代码第 6 步「`upsert(pending)` + **`writeRunState(pending)`**」 | **未实现** PM 侧 `pending` 写 | 保持「worker 自写」的单一写者契约（同目录两个写者正是事故形状）；「已派发未启动」由台账 `pending` 行表达，产物只承载身份与终态 |
| 5 | — | `[END]` 阳性证据**优先于**陈旧的 `running` `run.json`（不降级为 `lost`） | `[END]` 是 worker 到达终止写路径的直接证据；降级会丢失真实信息。`lost` 只用于「没有终止证据」的方向 |
| 6 | T-19 卡实现记录曾把第 3 项（`out-of-scope` 告警）改成「不单独告警」 | **改为实现**（每扫描一条聚合告警） | spec 风险 R7（第 169 行）明确要求「被跳过的候选写 `phase:"dispatch-alarm"/kind="out-of-scope"`」。卡片的单方面收窄与冻结需求冲突，以 spec 为准；成本仅每 session 一行 |

## 5. 非空洞对照（`evidence/scripts/t20-controls.ps1`，A~G 七组全红 + `restored: True`）

| 控制 | 变异 | 指名用例 | 结果 |
|---|---|---|---|
| A | `if (false && kind === "terminal")`（台账重新压过产物） | `worker-dispatch-guard` · never re-queues a task whose own run already ended | 1 failed |
| B | `targetKind` 恒为 `"unknown"`（去掉 `supersedes` 放行路径） | `worker-dispatch-guard` · dispatches a replacement run that declares supersedes | 1 failed |
| C | `if (false && targetKind !== "terminal")`（允许替换活着的运行） | `worker-dispatch-guard` · refuses to supersede a run that is not finished | 1 failed |
| D | `writeRunState` 失败改为 `throw`（阻断落盘） | `worker-run-identity` · still writes output.md when the run record cannot be written | 1 failed |
| E | 去掉 `outOfScope.push`（静默跳过） | `worker-dispatch-guard` · reports the keys it did not scan | 1 failed |
| F | launcher 忽略 `run.json` 终态 | `test_launcher.py::TestReconcileRunState::test_run_json_terminal_converges_stuck_row` | 1 failed |
| G | `mark_run_lost` 写 `done`（伪造终态） | `test_launcher.py::TestReconcileRunState::test_run_json_running_with_output_md_becomes_lost` | 1 failed |

## 6. 只读面实测（真实项目）

命令：`python -X utf8 packages/multi-workers/mw.py doctor --project H:\git\Multi-Workers --json`

| 观测 | 值 |
|---|---|
| 执行期间 `_workers.parallel` | sha256 前后一致、文件数 10 → 10 ⇒ **doctor 未写盘** |
| `queue.rows_total` / `non_terminal_count` | 253 / 1（对比 T-18 验收时的 252 / 0：**另一个窗口在两轮之间派了 1 个任务**，不是本次改动所为）|
| `unparsable_count` / `version` | 0 / 1（历史文件仍无版本头 ⇒ 无回填）|
| `run_ledger_conflict` | 0（真实项目还没有任何 `run.json`）|
| `issues` / `healthy` | `[]` / `True` |

⇒ T-20 的新判据在真实项目里**如实静默**（没有产物就按老行为），并且 `lost` 这条新状态没有让既有 253 行产生任何新 issue。

**运行态说明（未做任何重启）**：常驻 launcher/serve 是进程内已加载的旧代码，TS 侧要等 T-16 的 dist/bundle 重建才生效 ⇒ 本轮改动对历史 worker 零实时影响。

## 7. 已知残余

1. **Python conductor 的派发路径未接 run.json**：`autopilot/dispatch.py` 仍只按自己的台账/计划派发（未加「目标目录 `run.json` 终态 ⇒ 不派」判据）。TS 侧已闭合（IN-3 的真实来源）；conductor 侧属后续 key。
2. **PM 侧不写 `pending`** ⇒ 派发到 worker 启动之间的窗口里，产物状态只有台账 `pending`（有意为之，见 §4 偏离 4）。
3. **`lost` 之后的收口靠人**：`lost` 行会进 widget 的待处理区并需要 ack（有意），但没有「自动转 `failed` 供重试」的路径——按用户要求③，重试必须新 task_key + `supersedes`。
4. **`run.json` 心跳每 30s 重写**（与 trace.log 心跳同 tick）：单写者 + tmp/rename，Windows 上多写者竞态不适用；代价是目录 mtime 每 30s 变动（`_row_last_activity` 依赖它，反而更准）。
5. **`output.md` marker 不是文件首行**（agent 写过产物时）：按 §4 偏离 2 处理，`grep -n "<!-- mw-run:"` 可取。
6. **`evaluateRunIdentity` 对无 run 记录的候选会多读一次 `task.md`**（为了看 `supersedes` 头）；有 run 记录的候选零读。属可接受开销（每个候选几 KB）。
