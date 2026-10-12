# IN-3 影响评估：当前产物受损面与可恢复性

- **key**：mw-gate-verdict-hardening　**日期**：2026-10-10 11:40（本地 UTC+8）
- **配套文档**：`evidence/incident-in3-queue-reenqueue-20261010.md`（机制与根因）
- **口径**：只读审计。窗口 W1 = 10-09 20:05–20:55（第 1 次整表重建的下游重跑）、W2 = 10-10 10:50–11:45（第 2 次）。**本 key 未改生产代码、未回滚任何他人文件**
- **审计脚本**（已归档，可重跑）：`evidence/scripts/in3-impact-audit.py`、`evidence/scripts/in3-source-attrib.py`（均为只读）

---

## 0. 结论先行

| 维度 | 判定 |
|---|---|
| 影响等级 | **中高，但可恢复**：波及 30+ key 的 504 份产品文件，**未发现截断/损坏**，且受影响的产品文档**绝大多数在 git 里**（82 份均为 tracked），事故前版本可逐文件取回 |
| 最危险的一类 | **review / verify / quality-gate 类产品**（30 份）：它们的产品**就是判定**，重跑版可能与原判定不同；其中 `mw-vision-role/achieved.md` 属交付声明级 |
| 源码面 | 内容级影响很小：窗口内 `packages/**` 仅 **12** 个文件有 diff（其余 1,308 个只是 mtime 被批量触碰，内容 = HEAD）。**无证据**表明旧改动被重放进源码，但**无法排除**（归属无法二分） |
| 无备份的一类 | **新 key 目录是 untracked**（本 key、`mw-workspace-incident-probe`、`mw-worktree-junction-guard`、`mw-dual-workspace`、以及 1 份 `mw-rag-integration` 新证据）⇒ 事故前版本**无 git 恢复路径** |
| 处置建议 | **不要由单个 session 批量 `git checkout` 回滚**（82 份里混有各 key 合法的在写工作）；改为各 key PM 按本清单自查；新 key 目录纳入版本控制 |

---

## 1. 面 A：`.agenticdoc` 产物（主要受损面）

### 1.1 规模

| 指标 | 数值 | 来源 |
|---|---|---|
| W2 窗口内被写的 `.agenticdoc` 文件 | **1,011** | `.tmp/in3-impact-audit.py` |
| W1 窗口内 | 68 | 同上 |
| 其中"产品"文件（evidence/* 与 worker-product：`output.md`/`report*.md`/`progress.md`） | **504**（421 worker-product + 83 evidence） | 同上 |
| 其中运行内部件（`trace.log`/`worker.log`） | 504 | 同上 |
| 当前 `git status`（tracked 修改） | **82** `.agenticdoc` + 12 `packages` | `git status --porcelain` |
| 82 份的构成 | 67 evidence / 11 task-card / 2 phase-doc / 2 other | 同上 |

### 1.2 是否被截断（"半截产品"风险）

**未发现截断**：
- 最小的产品文件是 `progress.md`（116 B – 426 B，本身就该是小文件）；
- 窗口内被触碰的文件中 **0 字节者仅 1 个**：`mw-autopilot-slot-capacity/workers/msc-t14-docs-dist-regression/pytest-full.err.log`（运行日志，非交付物）；
- 被重写的主文档均在 10–60 KB 量级（如 `spec-slot-utilization` +334/−203、`verify-mw-vision-role` +1637/−0）。

⇒ 重跑 worker 是**跑完才写**（与 10-09 观测一致），因此本 key 之外的产物没有被"写一半"。

### 1.3 按风险分级（需要各 key 自查的最小清单）

| 级别 | 类别 | 数量 | 为什么危险 | 清单 |
|---|---|---|---|---|
| **L1** | review / verify / quality-gate / achieved 类（产品=判定） | **30 份** | 重跑版可能给出**不同判定**，与已提交结论冲突；`achieved.md` 是交付声明 | `goal-autopilot/evidence/quality-gate-report-2026-09-1{0,1}-qg.md`、`mw-crosskey-risk-escalation/evidence/verify-independent-2026-09-23.md`、`mw-partition-parent-extended/evidence/quality-gate-report-2026-09-20-worker.md`、`mw-rag-config-guide/evidence/verify-run-2026-09-22.md`、`mw-rag-integration-fix/evidence/verify-run-2026-09-22.md`、`mw-rag-integration/evidence/quality-gate-review-2026-09-22.md`、`mw-rag-window-parity/evidence/{quality-gate-report,verify-run,verify-run-delta}-2026-09-23.md`、`mw-target-partition/evidence/verify-run-2026-09-19.md`、`mw-vision-role/achieved.md`、`mw-vision-role/evidence/quality-gate-report-20260926T1850Z.md`、`mw-vision-role/evidence/reviews/qg-review-mw-vision-role-20260926.md`、`mw-vision-role/evidence/runs/verify-mw-vision-role-20260926.md`、`mw-worker-progress-persist/evidence/verify-independent-2026-09-23.md`、`mw-worker-progress-persist/evidence/verify-run-2026-09-23.md`、`mw-worker-visibility-gate/evidence/verify-independent-2026-09-23.md`、`autopilot-monitor/evidence/runs/t02-verification.md`、`mw-target-partition/evidence/e2e-spawn-2026-09-19.md` 等 |
| **L2** | research 类 evidence（`.agenticdoc/*/evidence/research/*`） | ~37 份 | 内容可为"修订稿"，与 design/spec 的锚点可能不一致（本 key 已实测：锚点漂移 ~20 处） | 见 `git status` 的 evidence 列表 |
| **L3** | task-card（11）/ phase-doc（2） | 13 | 任务卡被重跑 worker 追加"回执/复核"行；phase-doc 若被 worker 写入属治理违规（本次审计**未见** worker 写 phase-doc：2 份分别是本 key 的 `key-decision.md`（PM 自写）与事故探针的 `pm-state.md`（其 PM 自写）） | — |
| **L4** | 运行内部件（trace.log / worker.log / progress.md） | 504+ | 仅丢失"上一轮的运行痕迹"，不影响交付 | 忽略 |

### 1.4 可恢复性（关键结论）

| 类别 | 可恢复性 |
|---|---|
| `.agenticdoc/<既有 key>/**` 的 82 份 tracked 修改 | **可恢复**：`git show HEAD:<path>` 取得事故前版本；`git checkout -- <path>` 可回滚（**但不建议批量执行**，见 §0） |
| 新 key 目录（untracked） | **不可从 git 恢复**：`.agenticdoc/mw-gate-verdict-hardening/`（本 key 全部文档）、`mw-workspace-incident-probe/`、`mw-worktree-junction-guard/`、`mw-dual-workspace/evidence/quality-gate-report-2026-09-11.md`、`mw-rag-integration/evidence/verify-run-2026-10-09.md` |
| 本 key 自身 | 已人工备份 1 份（`evidence/research/_orig/spec-l3-abort-taxonomy-20261009.first-run.md`）；其余 7 份无事故前副本（其中 2 份确认为完整重跑版替代） |

---

## 2. 面 B：源码（`packages/**`）

### 2.1 内容级 vs mtime 级

| 指标 | 数值 |
|---|---|
| W2 窗口内 `packages/**` mtime 变化的文件 | **1,308** |
| 其中有**内容**差异的（tracked） | **12** |
| 其中 11:28:58 一次性批量触碰的 | 全部 `packages/agent/**`（含 `docs/harness-v2.md` 等**未改内容**）⇒ 与 IN-1/IN-2 的恢复动作同族的批量操作，不是 worker 逐文件写 |

⇒ **mtime 大范围变化 ≠ 内容受损**。以 `git diff` 为准。

### 2.2 12 份内容 diff（全部都很小）

```
2	0	packages/multi-workers/CHANGELOG.md
1	1	packages/multi-workers/UPDATE.md
8	1	packages/multi-workers/autopilot/conductor.py
11	9	packages/multi-workers/autopilot/effective_config.py
2	2	packages/multi-workers/docs/rag-config-guide.md
4	3	packages/multi-workers/mw.py
64	0	packages/multi-workers/test_autopilot_pending_review.py
6	6	packages/multi-workers/test_autopilot_xkey_registration.py
124	0	packages/multi-workers/test_common.py
60	36	packages/multi-workers/test_doctor_autopilot.py
59	1	packages/multi-workers/test_mw_autopilot_cli.py
```
（`test_common.py` 为本次事故前既有的他人脏文件，与本 key 无关，未触碰。）

### 2.3 归属判定（诚实：无法二分）

- 5 份在 **W2 窗口内被再次改写**：`conductor.py`(11:21:38)、`effective_config.py`(11:00:15)、`test_autopilot_pending_review.py`(11:21:43)、`test_doctor_autopilot.py`(11:08:03)、`test_mw_autopilot_cli.py`(10:56:36)。
- 其中 4 份**本就在 D-009 记录的"他人未提交"清单**里（`effective_config.py`、`mw.py`、`test_autopilot_xkey_registration.py`、`test_mw_autopilot_cli.py`）⇒ 它们本来就属活跃 key 的在写工作，事故只是又叠了一层写入。
- `trace.log` 的"提及"不能作为写入证据（research/review worker 会大量读这些文件）——本评估**不据此下结论**。
- **结论**：无证据表明重跑 worker 把历史改动重新打进源码；但也**无法排除**。要坐实需要各 key 自查自己任务的 `[VERIFY]`/回执，或复盘 worker 的 edit 工具调用序列。

---

## 3. 面 C：台账与协调面

| 文件 | 状态 | 说明 |
|---|---|---|
| `.agenticdoc/_workers.parallel` | 10-10 11:33:38 写；252 行；243 done / 8 failed / 1 running / 0 pending | 见 IN-3 主文档 |
| `.agenticdoc/_workers.acked` | 10-10 11:33:45 写；**261 行** | 事故前最后一条 10-09 21:11:24；W2 内被写属正常 ack 流水（含本 key `mgh-rq5` 的 ack 与他 key 的 `wjg-*`） |
| `.agenticdoc/_index.parallel` | 10-10 10:53:10 写；diff +5/−2 | 与另一 session 新建 key（`mw-worktree-junction-guard`）一致 |
| `.mw/launcher.log` / `mw.log` | 被截断重写（serve 会话级） | 正常设计 |

---

## 4. 处置建议（按优先级）

1. **不批量回滚**：82 份 tracked 修改里混有各 key 合法在写工作，单个 session 无权判定。改为**按 §1.3 的 L1 清单（30 份）派给各 key 的 PM 自查**（比对本 key 已做的锚点复核方式）。
2. **本 key 立即做**：把 L1/L2 中与本 key 相关的 2 份重跑版（`spec-l3-abort-taxonomy`、`design-g2-gate-reminder-wiring`）与已吸收内容再比对一次（已在 10-09 完成一轮锚点复核，本轮无需重复）。
3. **新 key 目录纳入版本控制**（或建立 `evidence/_orig/` 级备份约定）——这是"产物自带状态/可追溯"要求的一部分（见 spec AC-022）。
4. **源码面**：在各 key EXECUTE 前，用 `git diff` 复核自己写面内的 12 份脏文件；本 key 的写面（`conductor.py`/`monitor.ts`/`console.ts`/`status-model.ts`/`mw_common.py`/`mw.py`）中 `conductor.py`、`mw.py`、`effective_config.py` 已带他人改动 ⇒ 沿用 D-009 的门禁（EXECUTE 前须确认对方提交/释放）。
5. **告警缺口**（本次影响面之所以能这么大）：`mw doctor` 不检查"队列规模突变""证据文档在产品统计口径下的异常重写"——建议纳入 G5/G6 的观测项。

---

## 5. 本次评估**未覆盖**的面

1. `.agenticdoc/_project_log.md`、`_pitfalls.md`、`_arch_snapshot.md` 是否被重跑写入 —— 未查。
2. `~/.pi/agent/sessions/**` 的会话记录是否被污染（体积过大）—— 未查。
3. 各 key 的 `achieved.md` / `quality-gate-report` 的**语义**差异（重跑版是否更差）—— 需各 key 自查，本文只做规模与结构判定。
4. `.tmp/` 下的取证副本（`.tmp/msc-t08-verify/pristine/**` 等）是否被覆盖 —— 未查。
