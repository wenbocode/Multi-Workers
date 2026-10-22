# Decision Review — mw-signoff-decide-only verify

> 机器生成（`mw decide report`），数据源 `H:\git\Multi-Workers\.agenticdoc\_autopilot\decisions.jsonl`，只读 fold，**不作门控**。
> generated_at: 2026-10-22T12:47:29Z

## 概览

| 指标 | 值 |
| --- | --- |
| N（有效 settle，剔 inconclusive/pending） | 0 |
| decision groups / 档案行 | 29 / 50 |
| 已决策 / 自动生效(acted) / 上抛人 | 2 / 0 / 0 |
| override | 0（rate=0.0%） |
| 一致率 Wilson 95% 下界 | - |
| nc_raw / nc_human（dp3） | 0 / 0 |
| 链断裂 / 跳过行 | 0 / 0 |

outcomes: ok=0, rework=0, rollback=0, inconclusive=0, pending=29

**数据不足，不结论**（N=0 < 5）：以下内容仅供观察，不构成调整依据。

## 判据表

| decision_id | dp | answer | confidence | mode | acted | outcome | override |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dp1-dispatch-type:refresh@2026-10-21T03:39:33+00:00 | dp1-dispatch-type | (无 decide 行) | - | - | - | pending | no |
| dp1-dispatch-type:signoff@mw-signoff-decide-only@2026-10-22T12:45:45Z | dp1-dispatch-type | (无 decide 行) | - | - | - | pending | no |
| dp1-dispatch-type:signoff@mw-signoff-decide-only@2026-10-22T12:46:34Z | dp1-dispatch-type | (无 decide 行) | - | - | - | pending | no |
| dp10-dependency:refresh@2026-10-21T03:39:33+00:00 | dp10-dependency | (无 decide 行) | - | - | - | pending | no |
| dp11-credential:refresh@2026-10-21T03:39:33+00:00 | dp11-credential | (无 decide 行) | - | - | - | pending | no |
| dp12-destructive:refresh@2026-10-21T03:39:33+00:00 | dp12-destructive | (无 decide 行) | - | - | - | pending | no |
| dp13-commit-release:refresh@2026-10-21T03:39:33+00:00 | dp13-commit-release | (无 decide 行) | - | - | - | pending | no |
| dp14-rule-conflict:refresh@2026-10-21T03:39:33+00:00 | dp14-rule-conflict | (无 decide 行) | - | - | - | pending | no |
| dp15-autopilot-gate:refresh@2026-10-21T03:39:33+00:00 | dp15-autopilot-gate | (无 decide 行) | - | - | - | pending | no |
| dp16-goal:refresh@2026-10-21T03:39:33+00:00 | dp16-goal | (无 decide 行) | - | - | - | pending | no |
| dp17-spec-lock:refresh@2026-10-21T03:39:33+00:00 | dp17-spec-lock | (无 decide 行) | - | - | - | pending | no |
| dp18-claim:refresh@2026-10-21T03:39:33+00:00 | dp18-claim | (无 decide 行) | - | - | - | pending | no |
| dp19-foreign-write:refresh@2026-10-21T03:39:33+00:00 | dp19-foreign-write | (无 decide 行) | - | - | - | pending | no |
| dp2-checkpoint-split:refresh@2026-10-21T03:39:33+00:00 | dp2-checkpoint-split | (无 decide 行) | - | - | - | pending | no |
| dp20-stage-close:refresh@2026-10-21T03:39:33+00:00 | dp20-stage-close | (无 decide 行) | - | - | - | pending | no |
| dp21-refine:refresh@2026-10-21T03:39:33+00:00 | dp21-refine | (无 decide 行) | - | - | - | pending | no |
| dp22-debug-plan:refresh@2026-10-21T03:39:33+00:00 | dp22-debug-plan | (无 decide 行) | - | - | - | pending | no |
| dp23-snapshot:refresh@2026-10-21T03:39:33+00:00 | dp23-snapshot | (无 decide 行) | - | - | - | pending | no |
| dp24-pi-trust:refresh@2026-10-21T03:39:33+00:00 | dp24-pi-trust | (无 decide 行) | - | - | - | pending | no |
| dp25-signoff-conclusion:mw-signoff-decide-only@2026-10-22T12:45:44+00:00 | dp25-signoff-conclusion | q-conclusion=narrow | 1.0 | auto | no | pending | no |
| dp25-signoff-conclusion:mw-signoff-decide-only@2026-10-22T12:46:32+00:00 | dp25-signoff-conclusion | q-conclusion=narrow | 1.0 | auto | no | pending | no |
| dp25-signoff-conclusion:refresh@2026-10-21T16:22:39+00:00 | dp25-signoff-conclusion | (无 decide 行) | - | - | - | pending | no |
| dp3-worker-clarify:refresh@2026-10-21T03:39:33+00:00 | dp3-worker-clarify | (无 decide 行) | - | - | - | pending | no |
| dp4-failure-handling:refresh@2026-10-21T03:39:33+00:00 | dp4-failure-handling | (无 decide 行) | - | - | - | pending | no |
| dp5-test-triage:refresh@2026-10-21T03:39:33+00:00 | dp5-test-triage | (无 decide 行) | - | - | - | pending | no |
| dp6-qg-verdict:refresh@2026-10-21T03:39:33+00:00 | dp6-qg-verdict | (无 decide 行) | - | - | - | pending | no |
| dp7-gate-failure:refresh@2026-10-21T03:39:33+00:00 | dp7-gate-failure | (无 decide 行) | - | - | - | pending | no |
| dp8-scope-change:refresh@2026-10-21T03:39:33+00:00 | dp8-scope-change | (无 decide 行) | - | - | - | pending | no |
| dp9-model-select:refresh@2026-10-21T03:39:33+00:00 | dp9-model-select | (无 decide 行) | - | - | - | pending | no |

## 逐决策

### dp1-dispatch-type:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp1-dispatch-type:signoff@mw-signoff-decide-only@2026-10-22T12:45:45Z
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp1-dispatch-type:signoff@mw-signoff-decide-only@2026-10-22T12:46:34Z
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp10-dependency:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp11-credential:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp12-destructive:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp13-commit-release:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp14-rule-conflict:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp15-autopilot-gate:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp16-goal:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp17-spec-lock:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp18-claim:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp19-foreign-write:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp2-checkpoint-split:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp20-stage-close:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp21-refine:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp22-debug-plan:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp23-snapshot:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp24-pi-trust:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp25-signoff-conclusion:mw-signoff-decide-only@2026-10-22T12:45:44+00:00
- decide: ts=2026-10-22T12:45:45+00:00 available=True authority=advisory acted=False mode=auto
- outcome: pending (settled_by=-)
- note: intent=answer

### dp25-signoff-conclusion:mw-signoff-decide-only@2026-10-22T12:46:32+00:00
- decide: ts=2026-10-22T12:46:34+00:00 available=True authority=advisory acted=False mode=auto
- outcome: pending (settled_by=-)
- note: intent=answer

### dp25-signoff-conclusion:refresh@2026-10-21T16:22:39+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp3-worker-clarify:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp4-failure-handling:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp5-test-triage:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp6-qg-verdict:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp7-gate-failure:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp8-scope-change:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp9-model-select:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

## 分歧样例

- （无 override / rollback / 人工授权变更）

## 候选调整

suggest: none (N=0 < 5, 数据不足，不结论)

## 无法关联项

- （无显式登记的无法关联项）
