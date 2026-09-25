# T-09-e2e-postfix

状态: done（2026-09-25） · 覆盖: AC-001/008 · 依赖: T-06..T-08

产出：evidence/plan-postfix-regression-20260925.md —— e2e_l2 7/7（修复前 6+1）；默认套件 927+2 外域先在（worktree 判定）；集成期发现并修复 P-013 H2 转录截断坑（stub `###` 子节 + REPROMPT_INSTRUCTION 形状约束）。

## 目标

修复后全量回归：e2e_l2 全链 + autopilot 全套件，对照基线。

## 步骤

0. **stub reviewer 分支扩展**（T-01 证据 §四）：test_autopilot_e2e.py 的 `task_type == "reviewer"` 分支增加确定性 reprompt 响应——task.md 正文含 `Rejected lines`（REPROMPT_INSTRUCTION 尾标记）时产含 `## 系统行为变化` 与 `## 遗留` 节的合规稿；否则维持现状非合规模板（首轮触发 gate-blocked）。夹具文件在包根，VC-003 扫描面之外。

1. `python -m pytest -m e2e_l2 -q`（package 根）——对照 T-01 修复前证据：若判定 (a)，此前 blocked/stall 的缺口场景现经 reprompt 修正或合规转写后全链绿；若判定 (b)，确认既有用例不受影响。
2. `python -m pytest -q`（pytest.ini 默认排除 e2e_real/e2e_l2）——对照基线：241 passed + 1 既有无关失败（test_baseline_left_end_readcap，外部锚），零新增失败。
3. 证据落 `evidence/plan-postfix-regression-20260925.md`：命令、退出码、通过数、基线差分。

## 验证

- 双跑绿 + 基线差分记录在案。
