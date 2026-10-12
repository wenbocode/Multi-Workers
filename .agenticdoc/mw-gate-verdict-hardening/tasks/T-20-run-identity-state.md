# T-20: G6-B 运行身份 + 产物自带终态

- 波次: **4** · 依赖: **T-15**（`worker-store.ts`）、**T-18**（`launcher.py`）
- 写面（独占）: `.../shared/run-store.ts`（**新模块**）、`.../shared/worker-store.ts`、`.../worker/worker-mode.ts`、`packages/multi-workers/launcher.py`
- AC: **AC-022** · VC: **VC-032 / VC-033 / VC-042 / VC-043 / VC-044 / VC-045**
- 基线: `10446aefb`

## 问题（用户要求②③）

- 任务的终态**只存在于队列台账**（`_workers.parallel` 的 `status` 列）。台账被重建/丢行 ⇒ 任务"复活"（IN-3：252 个已终态任务被重跑）。
- 事故实测的活体样本（`_incidents/.../04-residue-scan-20261010.md`）：`msc-t14-docs-dist-regression` 的台账行在 `11:20:40` 已是 `done`，而它的重跑进程仍在跑，并在 `11:45:40 **覆写**了 `output.md`（6,410 B → 7,074 B）——**台账说完了，产物还在被改，无人知道哪份是终稿**。
- 用户要求：产物必须**自带状态**；`done` 的任务**不得重启**；需要补充则**新起一个 worker**（身份不可复用）。

## 交付

1. 新模块 `run-store.ts`（纯函数 + 注入 fs）：
   - `runPath(taskDir)`、`readRunState(taskDir)`、`isTerminal(state)`（`done|failed|lost`）、`writeRunState(taskDir, patch)`（**best-effort**，异常吞掉 + `trace.log` 留痕）。
2. `run.json` schema 1（写在 `workers/<task>/run.json`）：
   `{ schema: 1, task_key, run_id, owner_key, kind, status: "pending"|"running"|"done"|"failed"|"needs-clarification"|"lost", started_at, ended_at, exit, supersedes, artifacts: string[], pid?, last_heartbeat_at? }`
   - `run_id` 每次运行新生成（`<task_key>@<iso>` 或 uuid）；**写者 = worker 自身**（`worker-mode.ts`：启动写 `running`、settle/exit 写终态；心跳更新 `last_heartbeat_at`）。
   - `output.md` 首行写人读标记 `<!-- mw-run: <task_key>@<run_id> status=<status> -->`。
3. 派发判据（T-17 的第 3 步）**优先**读 `run.json` 终态：`done` 且**无 `supersedes`** ⇒ **拒派**（AC-022）。
4. `supersedes`：新任务 `task.md` 头可声明 `supersedes: <旧 task_key>`；此时允许派发（写自己的 `run.json`），**旧目录只读**（写前校验旧目录已有终态；若旧目录终态且新任务未声明 `supersedes` ⇒ 拒绝）。
5. `launcher.py`：`_reconcile_orphans`（`:555-621`）扩展为"进程不在 ∧ `run.json.status == "running"` ⇒ 写 `lost`（**保留现场**，不代写 `done`、不改产物）"。

## 契约（冻结）

- **worker 自写**：终态不得由 launcher/PM 代写 `done`；launcher 只允许补 `lost`。
- **best-effort**：`run.json` 写失败**不得**阻断 `output.md` / `report.md` 落盘（R15）。
- **零回填**：无 `run.json` 的历史任务行为与今日一致（不得批量补写历史目录，P-018）。
- `readRunState` 对坏 JSON 必须返回"无信息"（不得抛异常打断派发循环），并由 doctor 报 `run-ledger-conflict`（T-18）。

## 实施记录（2026-10-10，PM 直执，基线 `776b82d7f`）

实际落地与卡的差异（均有理由，已记 design D-029/D-030/D-031 与回执 §4）：

1. **同一 task_key 一律拒重跑**（卡字面暗示“终态 + `supersedes` 可重跑同目录”）：事故实证 `msc-t14` 台账 `done` 而重跑进程 11:45:40 覆写了它的 `output.md` ⇒ 允许同目录重跑就是把“无人知道哪份是终稿”制度化。`supersedes` 只用于**新 task_key 指向已终态旧目录**。
2. **marker 位置**：写在 **harness 段首行**（空产物即文件首行；agent 写过产物时居 `---` 之下），不夺占 agent 写的 `VERDICT=`/`TASKS=` 首行（D-117 契约，`agent-team-loop.test.ts:445` 精确断言）。这需要动 `output-writer.ts`（**范围变更**：`WriteOutputOpts.runMarker`）。
3. **终态集** = `done|failed|needs-clarification|lost`（TS/Python 恒等），而非卡里写的 `done|failed|lost`；`needs-clarification` 也是 worker 自宣告的结束态。
4. **PM 不写 `pending` `run.json`**（设计 §11.2 伪代码第 6 步未实现）：保持“worker 自写”单一写者；“已派发未启动”由台账行表达。
5. **`[END]` 优先于陈旧的 `running`**（不降级为 `lost`）：`lost` 只用于“无终止证据”方向。
6. **T-19 第 3 项补完**：`out-of-scope` 聚合告警实装（spec R7 要求，已在 VC-046 锁）。
7. **`lost` 状态传播**：`WorkerStatus` / `isTerminal` / `ui-bridge`（字形、ack 可受理、待处理区、排序、详情行）/ `mw_common._TERMINAL_STATUSES` ——否则 lost 行会永久显示为活动且不可 ack。

## [VERIFY]

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/run-store.test.ts          # 15 passed
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-run-identity.test.ts # 6 passed
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-guard.test.ts # 16 passed
cd ../multi-workers
python -X utf8 -m pytest test_run_identity.py -q -p no:randomly                        # 9 passed
python -X utf8 -m pytest test_launcher.py -q -p no:randomly -k Reconcile                # 7 passed
python -X utf8 -m pytest -q -p no:randomly                                              # 2 failed / 1423 passed（2 红 = 基线既有红）
npm run check                                                                          # 通过
```

## 非空洞对照（`evidence/scripts/t20-controls.ps1`，A~G 七组均转红 + `restored: True`）

| 控制 | 变异 | 指名用例 | 结果 |
|---|---|---|---|
| A | `if (false && kind === "terminal")`（台账重新压过产物）| 接线用例 `never re-queues a task whose own run already ended` | 1 failed |
| B | `targetKind` 恒为 `"unknown"`（抽掉 `supersedes` 放行路径）| `dispatches a replacement run that declares supersedes` | 1 failed |
| C | `if (false && targetKind !== "terminal")`（允许替换活着的运行）| `refuses to supersede a run that is not finished` | 1 failed |
| D | `writeRunState` 失败改为 `throw` | `still writes output.md when the run record cannot be written`（R15）| 1 failed |
| E | 去掉 `outOfScope.push` | `reports the keys it did not scan`（D-031）| 1 failed |
| F | launcher 忽略 `run.json` 终态 | `test_run_json_terminal_converges_stuck_row` | 1 failed |
| G | `mark_run_lost` 写 `done` | `test_run_json_running_with_output_md_becomes_lost` | 1 failed |

## 回执

`evidence/runs/t-20-run-identity-report.md`（含只读面实测与 6 条残余）。
