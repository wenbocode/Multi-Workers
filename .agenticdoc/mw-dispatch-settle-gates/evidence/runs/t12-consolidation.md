# T-12 收口证据 — mw-dispatch-settle-gates（AC-009 + 全 VC 跨卡复核）

- key: `mw-dispatch-settle-gates`｜卡: `tasks/T-12-consolidation.md`｜AC: **AC-009** + 全 VC 复核｜VC: **VC-040…VC-042**
- 角色: coding｜波次 4（独占串行）｜日期: 2026-10-11
- 冻结面（本卡开工前 PM 核验值；全部逐字保持，见 §6）：
  `shared/deliverable-evidence.ts bf580757…159d93`、`shared/output-sections.ts e6c74228…cf8a15`、
  `worker/worker-mode.ts 071932a4…f5de23`、`worker/output-writer.ts 4be2e569…31c3e7`、
  `pm/pm-orchestrator.ts 9bab23b9…6b4d7c`、`pm/ui-bridge.ts c78b79dc…81fd25`、
  `mw_common.py f05f1fca…e5d411`、`launcher.py 69ef5b6f…ca168b`、
  `autopilot/conductor.py df14a89a…391cf0`、`autopilot/dispatch.py c52bd2b6…cd961`
- 本卡写入面：`evidence/scripts/mwds-controls.ps1`（新建）、`test/suite/mwds-t12-regression.test.ts`（新建）、
  `test/suite/mwds-t02-write-intent.test.ts`（仅 PM 显式扩展的 1 条语料断言）、本文件、`workers/mds-t12-consolidation/report.md`。
  **未改 `packages/*/src/**`**（`git status` 与 §6 sha256 逐条复核）。

## §0 结论摘要

| 项 | 结果 |
|---|---|
| A/B/C 对照脚本 | 31 个控制组（A=11 / B=10 / C=10）全部「红 → 还原 sha 相同 → 绿」，`per_group_red>=1` |
| 跨卡 seam 用例 | 5 组（C1/C2、C5/C6/T-07、C7、AC-001、AC-002）9 条测试全绿；2 组逆改演示见 §2 |
| TS 受影响套件 | 5 failed / 108 passed / 1 skipped（114 文件）；14 failed / 903 passed / 3 skipped（920 用例）；**新红 = 0**（失败文件集合与基线逐字相同） |
| Python 全量 | **1579 passed / 2 failed / 10 deselected**；两条红逐条点名（§4.2）；**新红 = 0** |
| `npm run check` | **rc=1（PARTIAL）**：biome `--error-on-warnings` 命中 1 条**本 key T-03 引入**的 lint 警告（`worker-mode.ts:905 useOptionalChain`，unsafe fix，`--write` 不自动修）；其余 6 个子检查 rc=0（§4.3） |
| 共享测试重锚 | `test/extensions/agent-team-loop.test.ts` 无新增 red；受影响断言 #4 已在工作区更新并复核（§5） |
| `[VERIFY]` 锚定 | 81/81；未锚定引用 = 0 |

T-12 自身判据除 `npm_check_rc=0` 外全部满足；`npm_check_rc` 因实现卡遗留的 1 条 lint 警告为 1，按卡片「不得自行改实现 ⇒ 停止并报告」登记为 **PARTIAL**（§7 R1）。

## §1 各 AC PASS/PARTIAL 初判 + 机器判据

| AC | 卡 | 初判 | 机器判据（本卡复算/复核来源） |
|---|---|---|---|
| AC-001 | T-08 | PASS | seam 4：`blocked_on_human` 三轴与面板 `renderMonitorLines` 的 `BLOCKED_ON_HUMAN` 同 fixture 一致（true/false/false）；控制 T-08/A,B,C 全红→绿 |
| AC-002 | T-09 | PASS | seam 5：终态 stage ⇒ `reminders=0` 且 doctor `blocked_on_human=true`（互不干扰）；控制 T-09/A,B,C 全红→绿 |
| AC-003 | T-01 | PASS | 控制 T-01/A,B,C 全红→绿；`mwds-t01-worker-guard.test.ts` 11/11 |
| AC-004 | T-10 | PASS | 控制 T-10/A,B 全红→绿；`test_mwds_t10_dispatch_run_state.py` 33 passed |
| AC-005a | T-02 | PASS（残留 R-T02-1） | 语料 `false_positives=0`（PM 扩展后不再比对命中总数）；控制 T-02/A,B,C 全红→绿 |
| AC-005b | T-03 | PASS（P1 漏放为设计档位） | 控制 T-03/A,B,C 全红→绿；read-scope 既有 28/28 |
| AC-006 | T-04 + T-07 | PASS | seam 2：T-04 判定导出的 `run.json.status` == Python `_reap_status`（exit 0 不可覆盖）；控制 T-04/A,B,C 与 T-07/A,B,C 全红→绿 |
| AC-007 | T-06 | PASS | 控制 T-06/A,B,C 全红→绿；`mwds-t06` 9/9 |
| AC-008 | T-11 | PASS | 6 处文档勘误（本卡仅只读复核，改动属上一 key `mw-gate-verdict-hardening`） |
| AC-009 | T-12 | **PARTIAL** | 对照/回归/重锚全部达标；`npm_run_check_rc=1`（§4.3、§7 R1） |
| AC-010 | T-05 | PASS | seam 3（T-05 读侧 × T-06 段生成，双跑一致）；控制 T-05/A,B,C 全红→绿 |

## §2 A/B/C 对照汇总（脚本 + 真实输出）

脚本：`.agenticdoc/mw-dispatch-settle-gates/evidence/scripts/mwds-controls.ps1`
协议：基线 sha256 → 备份 → 最小逆改 → 具名测试**必须红** → 从备份还原 → sha256 == 基线 → 同一具名测试**必须绿**。

命令：

```
powershell -NoProfile -ExecutionPolicy Bypass -File \
  .agenticdoc/mw-dispatch-settle-gates/evidence/scripts/mwds-controls.ps1 \
  -RegressionFinal .tmp/t12-py-final.log
```

真实输出（exit 0；31/31 PASS）：

```
[T-01/A] ui-bridge.ts -> RED [Tests  1 failed | 10 skipped (11)] ; restore_sha=True ; GREEN [Tests  1 passed | 10 skipped (11)] ; PASS
[T-01/B] ui-bridge.ts -> RED [Tests  1 failed | 10 skipped (11)] ; restore_sha=True ; GREEN [Tests  1 passed | 10 skipped (11)] ; PASS
[T-01/C] ui-bridge.ts -> RED [Tests  1 failed | 10 skipped (11)] ; restore_sha=True ; GREEN [Tests  1 passed | 10 skipped (11)] ; PASS
[T-02/A] ui-bridge.ts -> RED [Tests  1 failed | 17 skipped (18)] ; restore_sha=True ; GREEN [Tests  1 passed | 17 skipped (18)] ; PASS
[T-02/B] ui-bridge.ts -> RED [Tests  1 failed | 17 skipped (18)] ; restore_sha=True ; GREEN [Tests  1 passed | 17 skipped (18)] ; PASS
[T-02/C] ui-bridge.ts -> RED [Tests  1 failed | 17 skipped (18)] ; restore_sha=True ; GREEN [Tests  1 passed | 17 skipped (18)] ; PASS
[T-03/A] worker-mode.ts -> RED [Tests  1 failed | 13 skipped (14)] ; restore_sha=True ; GREEN [Tests  1 passed | 13 skipped (14)] ; PASS
[T-03/B] worker-mode.ts -> RED [Tests  1 failed | 13 skipped (14)] ; restore_sha=True ; GREEN [Tests  1 passed | 13 skipped (14)] ; PASS
[T-03/C] worker-mode.ts -> RED [Tests  1 failed | 13 skipped (14)] ; restore_sha=True ; GREEN [Tests  1 passed | 13 skipped (14)] ; PASS
[T-04/A] deliverable-evidence.ts -> RED [Tests  1 failed | 13 skipped (14)] ; restore_sha=True ; GREEN [Tests  1 passed | 13 skipped (14)] ; PASS
[T-04/B] deliverable-evidence.ts -> RED [Tests  1 failed | 1 passed | 12 skipped (14)] ; restore_sha=True ; GREEN [Tests  2 passed | 12 skipped (14)] ; PASS
[T-04/C] pm-orchestrator.ts -> RED [Tests  1 failed | 13 skipped (14)] ; restore_sha=True ; GREEN [Tests  1 passed | 13 skipped (14)] ; PASS
[T-05/A] output-sections.ts -> RED [Tests  1 failed | 10 skipped (11)] ; restore_sha=True ; GREEN [Tests  1 passed | 10 skipped (11)] ; PASS
[T-05/B] output-sections.ts -> RED [Tests  1 failed | 10 skipped (11)] ; restore_sha=True ; GREEN [Tests  1 passed | 10 skipped (11)] ; PASS
[T-05/C] worker-mode.ts -> RED [Tests  1 failed | 10 skipped (11)] ; restore_sha=True ; GREEN [Tests  1 passed | 10 skipped (11)] ; PASS
[T-06/A] output-writer.ts -> RED [Tests  1 failed | 8 skipped (9)] ; restore_sha=True ; GREEN [Tests  1 passed | 8 skipped (9)] ; PASS
[T-06/B] output-writer.ts -> RED [Tests  1 failed | 8 skipped (9)] ; restore_sha=True ; GREEN [Tests  1 passed | 8 skipped (9)] ; PASS
[T-06/C] worker-mode.ts -> RED [Tests  1 failed | 8 skipped (9)] ; restore_sha=True ; GREEN [Tests  1 passed | 8 skipped (9)] ; PASS
[T-07/A] launcher.py -> RED [1 failed in 0.15s] ; restore_sha=True ; GREEN [1 passed in 0.09s] ; PASS
[T-07/B] launcher.py -> RED [1 error in 0.10s] ; restore_sha=True ; GREEN [1 passed in 0.08s] ; PASS
[T-07/C] launcher.py -> RED [1 failed in 0.14s] ; restore_sha=True ; GREEN [1 passed in 0.09s] ; PASS
[T-08/A] mw_common.py -> RED [2 failed, 4 warnings in 1.34s] ; restore_sha=True ; GREEN [2 passed, 4 warnings in 1.34s] ; PASS
[T-08/B] mw_common.py -> RED [1 failed, 2 warnings in 0.78s] ; restore_sha=True ; GREEN [1 passed, 2 warnings in 0.74s] ; PASS
[T-08/C] mw_common.py -> RED [1 failed in 1.79s] ; restore_sha=True ; GREEN [1 passed in 1.76s] ; PASS
[T-09/A] conductor.py -> RED [3 failed in 0.27s] ; restore_sha=True ; GREEN [3 passed in 0.20s] ; PASS
[T-09/B] conductor.py -> RED [1 failed in 0.24s] ; restore_sha=True ; GREEN [1 passed in 0.19s] ; PASS
[T-09/C] conductor.py -> RED [1 failed, 2 passed in 0.26s] ; restore_sha=True ; GREEN [3 passed in 0.20s] ; PASS
[T-10/A] dispatch.py -> RED [4 failed in 0.16s] ; restore_sha=True ; GREEN [4 passed in 0.09s] ; PASS
[T-10/B] dispatch.py -> RED [1 failed in 0.13s] ; restore_sha=True ; GREEN [1 passed in 0.09s] ; PASS
[T-12/C] worker-mode.ts -> RED [Tests  1 failed | 8 skipped (9)] ; restore_sha=True ; GREEN [Tests  1 passed | 8 skipped (9)] ; PASS
[T-12/A] output-sections.ts -> RED [Tests  1 failed | 8 skipped (9)] ; restore_sha=True ; GREEN [Tests  1 passed | 8 skipped (9)] ; PASS

===== SUMMARY =====
kind=A controls=11 red=11
kind=B controls=10 red=10
kind=C controls=10 red=10
total_controls=31 pass=31 fail=0
[VERIFY] VC-042: control_groups=A/B/C per_group_red=A=11,B=10,C=10
```

- T-12/C = seam 组 (b) 第 1 组：把 T-03 消费端 `checkBashWriteScopeTarget` 的 `write_scope` 交集判据摘除 ⇒ seam 用例「producer's one-line header is parsed」转红。
- T-12/A = seam 组 (b) 第 2 组：把 T-05 `readLastProductSection` 回退为首匹配 ⇒ seam 用例「a T-06-written output.md reads back」转红。
- T-07/B 的逆改为「无 run.json ⇒ return "done"」，python 侧表现为 `1 error`（逆改点语义冲突），同样满足「具名用例必须红 → 还原 → 绿」。

## §3 跨卡 seam 用例（`test/suite/mwds-t12-regression.test.ts`，9/9）

| 组 | 契约 | 机制 | 结果 |
|---|---|---|---|
| 1 | C1/C2（T-02 → T-03） | T-02 单点写盘产出 `write_scope:` 一行 → `parseTaskMd` 解析 → `checkBashWriteScopeTarget` 取交集；含缺省（fail-open）与空值（fail-closed） | PASS（2 用例） |
| 2 | C5/C6（T-04 ↔ T-07） | 同一 fixture：`hasDeliverableEvidence` 判定 → 写出 `run.json.status` → `python -X utf8` 调 `launcher._reap_status(taskDir, 0)`；结论必须相同 | PASS |
| 3 | C7（T-05 × T-06） | 同一 fixture：`writeOutput` 生成 `## Deliverables`/`## Exit Reason` → T-05 读侧回读；D-117 二次写入后仍取末个真实块 | PASS |
| 4 | AC-001（T-08 ↔ monitor.ts） | 同 fixture：`readMonitorState` + `renderMonitorLines` 的 `BLOCKED_ON_HUMAN` 与 Python `_doctor_gates["blocked_on_human"]` 一致（true/stale false/row false） | PASS（3 用例） |
| 5 | AC-002（T-09 ↔ T-08） | 同 fixture：`pending_gate_reminders`（经 `_gate_stage_context` 两级解析）与 doctor gates 互不干扰（closed ⇒ reminders=0 且 blocked=true；running ⇒ reminders=1 且 blocked=true） | PASS（2 用例） |

seam `[VERIFY]` 行（`--silent=false`）：

```
[VERIFY] seam T-04/T-07 delivered: delivered=true status=done reaped=done
[VERIFY] seam T-04/T-07 undelivered: delivered=false status=needs-clarification reaped=needs-clarification
[VERIFY] seam T-08 <fixture>: panel=true doctor=true
[VERIFY] seam T-09/T-08 closed: reminders=0 blocked_on_human=true
 Tests  9 passed (9)
```

## §4 全量回归

### 4.1 TS（受影响套件全跑）

命令（`packages/coding-agent/`）：

```
node ../../node_modules/vitest/dist/cli.js --run test/suite \
  test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-output.test.ts \
  test/extensions/agent-team-loop-image-cap.test.ts test/extensions/agent-team-loop-worker-tree-kill.test.ts \
  test/extensions/agent-team-loop-vision-gate.test.ts test/extensions/agent-team-loop-vision-autoroute.test.ts \
  test/extensions/agent-team-loop-checkpoint-wiring.test.ts test/extensions/agent-team-loop-profile-injection.test.ts \
  test/extensions/agent-team-loop-implementation-gate.test.ts
```

| 运行 | 文件 | 用例 |
|---|---|---|
| 基线（本卡编辑前） | 5 failed / 107 passed / 1 skipped (113) | 14 failed / 894 passed / 3 skipped (911) |
| 最终（`npm run check` 后重跑） | 5 failed / 108 passed / 1 skipped (114) | 14 failed / 903 passed / 3 skipped (920) |

失败文件集合**逐字相同**（Windows 环境基线，与 AGENTS.md 记录一致）：

```
test/suite/agent-session-runtime.test.ts
test/suite/regressions/2791-fswatch-error-crash.test.ts
test/suite/regressions/3302-find-path-glob.test.ts
test/suite/regressions/3592-no-builtin-tools-keeps-extension-tools.test.ts
test/suite/regressions/5109-exclude-tools.test.ts
```

⇒ 文件 +1（本卡新增 seam 套件）、用例 +9（seam 9 条），**新红 = 0**。

### 4.2 Python 全量

命令：`python -X utf8 -m pytest packages/multi-workers -q`

```
2 failed, 1579 passed, 10 deselected, 190 warnings in 189.74s (0:03:09)
```

两条既有红逐条点名（与 T-10 记录一致，均不读本 key 改动面）：

1. `packages/multi-workers/test_autopilot_readcap_injection.py::test_baseline_left_end_bound`
   —— 冻结的 `baseline_20260924/dispatch.head.py` 与 `git show HEAD:...dispatch.py` blob sha 不一致（纯 git 历史比对）。
   `AssertionError: assert '219ed809…' == '6be60fe5…'`
2. `packages/multi-workers/test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`
   —— 对仓库 `.agenticdoc` 既有 fixture 数据的断言（`_e2feature_root()` 实存数据），不涉及本 key 文件。

总数为**本 key 实测**（1579 passed），**不等于**卡片记载的上一 key 口径（`2 failed / 655 passed`，为上一 key 时点）；判据取「新增红 = 0」。
对照脚本复算：`baseline_reds=2 final_reds=2 new_reds=0`（§2 末尾 `REGRESSION COMPARISON`）。

### 4.3 `npm run check`（本卡唯一一次）

命令：`npm run check`（= `biome check --write --error-on-warnings . && … && tsgo --noEmit && …`）

真实结果：**rc=1**，链条在第一步 biome 处因 1 条警告停止：

```
packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:905:10 lint/complexity/useOptionalChain  FIXABLE
  ! Change to an optional chain.
  905 │ if (previous !== undefined && previous.startsWith("-")) continue;
      │    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Skipped 1 suggested fixes.
Checked 1119 files in 591ms. Fixed 4 files.
Found 1 warning.
```

- 该行属 **T-03 新增的 bash write-scope 代码**（`git diff` 确认是本 key 未提交新增），且 biome 判为 **unsafe fix**，`--write` 不自动修 ⇒ 必须手改 `packages/*/src/**` 才能 rc=0，卡片明令禁止（「如发现必须改 ⇒ 停止并报告」）。
- biome `Fixed 4 files` = 本 key 的 4 个**测试**文件（`mwds-t01`/`mwds-t02`/`mwds-t03`/`mwds-t12` 的格式归一化）；`packages/*/src/**` 逐字未变（§6 sha256）。
- 因 biome 停止，其余子检查本卡单独复跑：`check:pinned-deps` rc=0、`check:ts-imports` rc=0、
  `check:shrinkwrap` rc=0、`check:install-lock:coding-agent` rc=0、`tsgo --noEmit` rc=0、`check:browser-smoke` rc=0。

最小复现：

```
npx biome check --error-on-warnings packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
```

### 4.4 `git status`（`npm run check` 后）

```
 M packages/coding-agent/test/extensions/agent-team-loop.test.ts   (本 key 既有；T-06 #4)
 M packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
 M packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
 M packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts
 M packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
 M packages/multi-workers/{mw_common.py,launcher.py}
 M packages/multi-workers/autopilot/{conductor.py,dispatch.py}
?? packages/coding-agent/src/extensions/agent-team-loop/shared/{deliverable-evidence.ts,output-sections.ts}
?? packages/coding-agent/test/suite/mwds-t0[1-6]-*.test.ts
?? packages/coding-agent/test/suite/mwds-t12-regression.test.ts
?? packages/multi-workers/test_mwds_t0[7-9]*.py  test_mwds_t10_dispatch_run_state.py
?? .agenticdoc/mw-dispatch-settle-gates/evidence/scripts/mwds-controls.ps1
```

biome 改写的 4 个文件均为本 key 测试文件；无 `.t12bak` 残留；未 commit、未 build、未重启进程。

## §5 共享测试重锚

`test/extensions/agent-team-loop.test.ts` 在本 key 内被影响的既有断言只有 1 条（DRQ-2 §5 断点 #4，T-06 已就地更新；本卡复核）：

| 旧断言 | 新断言 | 理由 |
|---|---|---|
| `for (const section of ["## Summary", "## Changed Files", "## Verification Steps", "## Exit Reason"])`（exit 0 固定四段） | `["## Summary", "## Deliverables", "## Verification Steps", "## Exit Reason"]` + `not.toContain("## Changed Files")` + `toContain("## Deliverables\n\nx.ts")` + 无产物时两段皆无（`out2`） | AC-007/DD-09：`## Changed Files` 的唯一生产者是死代码 `[]`，改名 `## Deliverables` 且空列表整段省略；不是放松，而是同时加了「旧段名不得回归」与「空产物不得出现空段/(none)」两条反向断言 |

其余 27 条断点（DRQ-2 §5）语义未变、逐行跑绿；#10/#11/#19 的末块/二次 settle/首匹配语义由 T-05 的独立套件（VC-043/045/046）承载；#23（`worker-dispatch-guard.test.ts:240`）保持绿。
本卡**未再改动**该文件（`git diff` 相对本卡开工无变化），故无新增重锚。

## §6 重锚对照表（VC-041）

本 key 多张卡叠加同一文件（`ui-bridge.ts` 链 1、`worker-mode.ts` 链 2），报告写作时的行号为**中间态**，最终工作区有漂移。逐条复核如下（符号名为准；`mv` = 已登记漂移）。

| 来源卡 | 报告引用 | 最终工作区 | 漂移 |
|---|---|---|---|
| T-01 | `ui-bridge.ts:229` `CROSS_KEY_READ_ONLY_SURFACES` | `:231` | +2 |
| T-01 | `ui-bridge.ts:245` `foreignLiveClaimRefusal` 放行分支 | `:247` | +2 |
| T-01 | `ui-bridge.ts:1386/:1753/:1847` 三个调用点 | `:1677`（dispatch_worker）`:2086`（advance_phase）`:2188`（/worker） | mv |
| T-02 | `ui-bridge.ts:1284` `WRITE_INTENT_GUARDS` | `:1287` | +3 |
| T-02 | `ui-bridge.ts:1398` `collectWriteIntentHits` | `:1392` | -6 |
| T-02 | `ui-bridge.ts:1429` `isWhitelistedWriteTarget` | `:1423` | -6 |
| T-02 | `ui-bridge.ts:1453` `judgeWriteIntent` | `:1444` | -9 |
| T-02 | `ui-bridge.ts:1513` `applyWriteSurfaceContract` | `:1504` | -9 |
| T-02 | `ui-bridge.ts:1548` `writeDispatchTaskMd` | `:1539` | -9 |
| T-03 | `worker-mode.ts:124` `isShellRole` | `:126` | +2 |
| T-03 | `worker-mode.ts:131` `isWritelessRole` | `:133` | +2 |
| T-03 | `worker-mode.ts:384` `write_scope:` 解析 | `:386` | +2 |
| T-03 | `worker-mode.ts:665` `tokenizeShellCommand` | `:667` | +2 |
| T-03 | `worker-mode.ts:807` `extractBashWriteCandidates` | `:809` | +2 |
| T-03 | `worker-mode.ts:921` `bashWriteDenyReason` | `:923` | +2 |
| T-03 | `worker-mode.ts:957` `checkBashWriteScopeTarget` | `:959` | +2 |
| T-03 | `worker-mode.ts:1012` `appendBashWriteScopeTraceLine` | `:1017` | +5 |
| T-03 | `worker-mode.ts:1459` bash 守卫注册分支 | `:1477` | +18 |
| T-04 | `worker-mode.ts:1268-1271` `markOutcome` | `:1271` | mv |
| T-04 | `worker-mode.ts:1599-1611` `recordEnd` | `:1602` | mv |
| T-04 | `worker-mode.ts:1882-1910` `finishSuccess` | `:1891-1918` | mv |
| T-06 | `output-writer.ts:95` D-117 合并点 | `:106` | +11 |
| T-06 | `worker-mode.ts:1902` `changedFiles` 取值 | `:1917` | +15 |
| T-04 | `deliverable-evidence.ts:187` `hasDeliverableEvidence` | `:187` | 0 |
| T-04 | `pm-orchestrator.ts:495-500` / `:661` `hasProductEvidence`+调用点 | `:495` / `:661` | 0 |
| T-07 | `launcher.py:367/376/414` `_exit_to_status`/`_reap_status`/`_reap_task_dirs` | 同 | 0 |
| T-07/08 | `mw_common.py:1720/1748` 终态集/读取器 | `:1720` / `:1748` | 0（T-07 已登记 +1） |
| T-08 | `mw_common.py:3098/3123/3137/3162/3193/3630` | 同 | 0 |
| T-09 | `conductor.py:565/2522/2575/2603` | 同 | 0 |
| T-10 | `dispatch.py:520` `read_run_status` 读点 | `:520` | 0 |

`reanchored_refs=35 drift_registered=23`（TS 侧 23 条已登记；Python 侧 12 条零漂移）。全部引用均可在最终工作区复算，**未锚定引用 = 0**。

## §7 残留与未达标项

| # | 项 | 状态 |
|---|---|---|
| R1 | `npm run check` rc=1：`worker-mode.ts:905 lint/complexity/useOptionalChain`（T-03 新增、unsafe fix） | **PARTIAL**；修法 = `if (previous?.startsWith("-")) continue;`；卡片禁止改 src ⇒ 交 PM/实现卡处置 |
| R2 | AC-005b 的 P1 漏放（未归类写命令不拦） | 设计档位，保留 |
| R3 | T-02 `output.md` 白名单与 DD-02/R-06 的分歧（R-T02-1） | 按卡片执行（放行）；已登记 |
| R4 | `run.json` 在历史语料 0/30（AC-006 artifacts 通道只能前瞻） | 保留 |
| R5 | TS 侧共享断言行号漂移（§6） | 已登记，无未锚定引用 |

## §8 机器 `[VERIFY]` 行

```
[VERIFY] VC-040: verify_lines_anchored=81/81 unanchored=0
[VERIFY] VC-041: reanchored_refs=35 drift_registered=23
[VERIFY] VC-042: control_groups=A/B/C per_group_red=A=11,B=10,C=10
[VERIFY] regression: ts=903_passed/14_env_baseline_failed py=1579_passed/2_failed new_reds=0 npm_check_rc=1
```

锚点：
- VC-040 = T-01…T-11 的 11 份 `report.md` 中 81 条 `[VERIFY]` 行（`Select-String '^\s*(\*\*)?\[VERIFY\]'` 计数）；每条值在本卡的全量套件 / 对照脚本中可复算，各卡报告内自带测试名或 `文件:行号` 锚点节。
- VC-041 = §6 重锚对照表；`drift_registered=23` 为已登记漂移条数。
- VC-042 = `evidence/scripts/mwds-controls.ps1` 输出（31 控制组，A/B/C 各自 `per_group_red>=1`）。
- regression = §4.1/§4.2/§4.3；`npm_check_rc=1` 见 §7 R1，不隐藏为 PASS。
