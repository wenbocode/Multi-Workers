# Mini-Spec: mw-goal-gate-write-intent

- Date: 2026-10-16
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop

## Problem

用户报告「现在读取 goal.md 也会被拦，只有写需要被拦」：实际是在 pi 窗口读/引用
`.agenticdoc/goal.md` 时弹出 yes/no 确认框（worker 无 UI 时直接 block）。

goal.md 是项目级目标锚点，**读是常态**：goal 对齐、worker 每 phase 记录 goal mtime
到 trace.log、`/goal` 工作流评审都要读它。门禁在全局 pi 扩展
`~/.pi/agent/extensions/goal.ts`（仓库外，AgenticTask clone commit 67508e5 装入），
其 bash 判定是「命令里出现 goal.md + 命中写模式」，两条过宽：

- interpreter 分支 `(python|node|perl|ruby|awk|pwsh|powershell) ... goal.md`
  → `python -X utf8 -c "print(open('.agenticdoc/goal.md').read())"`、
  `node -e 'fs.readFileSync(".agenticdoc/goal.md")'`、`pwsh -c "Get-Content goal.md"`
  全部被判为写；
- `(mv|move|rm|del|cp|copy|Move-Item|...) ... goal.md`
  → `cp goal.md /tmp/bak`（只读备份）也被判为写。

实证：`.agenticdoc/**/trace.log` 共 8 处 `[TOOL_ERR] ... 只读的项目目标锚点`，
紧跟的多是只读解释器命令（`python -X utf8 -c "`、`node -e 'const fs=require("node:fs")`），
分布在 mw-worker-output-contract / mw-autopilot-slot-capacity / mw-done-closure-repair /
mw-autopilot-gate-alarm-liveness 的 worker trace。

同时 `Q-GOAL-1`（`.agenticdoc/_scratch/quality-gate-drift-guard-20260902.md`）记录：
该门禁**在仓库外、无永久回归测试**。本次一并落地：门禁进仓库成为可管理模板 +
安装钩子 + 回归向量测试。

## Change

- 新增仓库模板 `packages/multi-workers/goal.ts`（goal.md 加载/注入 + 写入门禁），
  纯判定块以 ASCII 哨兵 `GOAL-GATE-CLASSIFIER-BEGIN` / `GOAL-GATE-CLASSIFIER-END`
  标记，块内不依赖 pi runtime（可被测试原样抽取执行）。
- 判定口径改为**写意图精确**（引号感知分段后逐段判定）：
  1. 重定向目标是 goal.md（`> goal.md` / `>> .agenticdoc/goal.md` / `2> goal.md`）
  2. 首词是覆盖/删除/移动/改名类动词且段内出现 goal.md（`rm|del|mv|move|ren|...|
     Set-Content|Add-Content|Out-File|tee|truncate|Remove-Item|Move-Item|Rename-Item|
     New-Item|...`）；复制类（`cp|copy|Copy-Item|rsync|install|xcopy|robocopy|scp`）
     只在 goal.md 位于**目标位**时算写（`cp goal.md /tmp/bak` 是读）
  3. 原地编辑 `sed -i` / `perl -i` / `ruby -i` 涉及 goal.md
  4. `git checkout|restore|reset|clean|apply|stash` 涉及 goal.md（会回写工作树）
  5. 内联解释器（`-c`/`-e`/`--eval`/heredoc）同时出现 goal.md 与写标记
     （`write_text|writeFileSync|appendFileSync|open(...,'w'|'a'|'x')|unlink|os.remove|
     shutil.copy|truncate|Set-Content|...`）；刻意不收裸 `'w'`/`'a'` 字面量
  其余（cat/type/Get-Content、只读 python/node/perl、grep/git log/diff/show、
  `cp` 出去备份、`sed -n`）一律放行。
  write/edit 工具门禁不变：写仍拦（交互弹确认框、无 UI block）、读一律不问。
- `mw.py`：新增 `_goal_gate_install()`（幂等：相同内容跳过、漂移副本覆盖），在
  `mw setup` 与 `mw build --install`（`_deploy_bundle`）的扩展安装点调用，与
  `_agentictask_update_install` 同机制同位置。
- 测试 `packages/multi-workers/test_goal_gate.py`：安装三态（缺失安装 / 幂等 /
  漂移覆盖）+ 读/写向量回归（抽取模板哨兵之间的判定块、写临时 `.mts`、由
  `node --experimental-strip-types` 执行；缺 node / 缺哨兵 fail-closed）。
- 文档与台账：`packages/multi-workers/CHANGELOG.md` [Unreleased]；
  `_scratch/quality-gate-drift-guard-20260902.md` 的 Q-GOAL-1 标记关闭。

范围边界：不改 pi core；不并入 agent-team-loop 扩展（该扩展的 worker 写面守卫
`bashWriteDenyReason` 已覆盖 worker 写 goal.md，本次只解决「读被拦 + 仓库外无测试」）；
不动 goal.md 本身（低频变更，本次不修改）。

## Files

- packages/multi-workers/goal.ts（新增模板）
- packages/multi-workers/mw.py（`_goal_gate_install` + 两个安装点）
- packages/multi-workers/test_goal_gate.py（新增）
- packages/multi-workers/CHANGELOG.md
- C:\Users\wenbozhou\.pi\agent\extensions\goal.ts（本机安装副本，随模板同步）

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | 只读形态（cat/type/Get-Content、只读 python/node/perl、grep/git log/diff/show、`cp` 出去备份、`sed -n`）不触发门禁 | pytest 向量 |
| AC-002 | 写形态（重定向、Set-Content/Add-Content/Out-File/tee、rm/mv/ren、`sed -i`、`perl -i`、`git checkout\|restore`、`cp` 覆盖目标位、内联 write_text/writeFileSync/open(...,'w')）仍触发门禁 | pytest 向量 |
| AC-003 | 模板安装幂等；漂移副本被模板覆盖 | pytest |
| AC-004 | 安装后的全局副本与仓库模板逐字节一致（本机生效） | `_goal_gate_install` + diff |
| AC-005 | 判定块可被仓库内测试从模板原样抽取执行（仓库可追溯、无 pi runtime 依赖） | pytest（哨兵存在 + 抽取执行） |

## Result

- 实现完成：`packages/multi-workers/goal.ts`（仓库模板，判定块以
  `GOAL-GATE-CLASSIFIER-BEGIN/END` 标记）；`mw.py::_goal_gate_install()`
  （读取/写入字节，幂等、漂移覆盖）接入 `mw setup`(2c) 与 `_deploy_bundle`
  （`mw build --install`）。
- AC-001 / AC-002 / AC-005：`test_goal_gate.py` 8/8 通过 —— 31 条只读向量零误拦、
  30 条写入向量零漏拦、3 条非 goal 命令零误判，加哨兵/抽取契约 2 条与安装三态 3 条。
- AC-003：本机实测幂等（缺失→`installed`；二次→`up-to-date`）。
- AC-004：安装后 `~/.pi/agent/extensions/goal.ts` 与仓库模板 sha256[0:16]
  均为 `aa9a91248ab9b4f2`（字节一致，LF 保留）。
- 相邻回归：`test_mw_bootstrap.py` + `test_mw_build.py` + `test_init_source.py` 39/39；
  `test_doctor_activation.py` + `test_update_env.py` + `test_protected_config.py` 47/47。
- 全量 `packages/multi-workers` pytest：2358 passed, 10 deselected, 8 failed ——
  8 项均为本次改动无关的既有/环境基线，逐项证据：
  `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` 与
  `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`
  已在 `mw-autopilot-gate-alarm-liveness/evidence/quality-gate-report-20261013.md:143`
  登记为已知红线；`test_mwds_t10_dispatch_run_state.py` 的 dispatch card 金样本
  早于 c2d03c91a（2026-10-15 phase-writer 恢复段注入，晚于该测试最后提交
  b65380d 2026-10-13）；`test_launcher.py` / `test_task_type_parity.py` 的 BOM 用例
  依赖本工作树缺失的历史书 `.agenticdoc/mw-dispatch-reliability/workers/mw-dr-glm53/task.md`；
  `test_mwds_t27` / `test_mwds_t29` 为 node/TS parity harness；
  `test_mwgal_t13::test_process_start_ms_probe` 单跑通过（时序抖动）。
- 生效：本机全局副本已刷新为模板；pi 窗口 `/reload` 后门禁生效，worker 新 spawn 自动生效。
  `mw serve` 无需变更（门禁在 pi 进程侧）；stale serve 清理是另一件事（另案）。
- 变更文件：`packages/multi-workers/{goal.ts, test_goal_gate.py, mw.py, CHANGELOG.md}`、
  `.agenticdoc/_scratch/quality-gate-drift-guard-20260902.md`（Q-GOAL-1 关闭记录）。
- 残留：门禁逻辑未并入 agent-team-loop 扩展（该扩展的 worker 写面守卫已覆盖 worker 写
  goal.md，并入属另一个交付）；`_pitfalls.md` 未追加（该文件正被其它窗口编辑，避免污染其提交）。
- 状态：完成。
