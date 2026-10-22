# Decision Review — mw-decision-substitution execute

> 机器生成（`mw decide report`），数据源 `H:\git\Multi-Workers\.agenticdoc\_autopilot\decisions.jsonl`，只读 fold，**不作门控**。
> generated_at: 2026-10-21T15:41:35Z

## 概览

| 指标 | 值 |
| --- | --- |
| N（有效 settle，剔 inconclusive/pending） | 1 |
| decision groups / 档案行 | 29 / 35 |
| 已决策 / 自动生效(acted) / 上抛人 | 3 / 0 / 2 |
| override | 0（rate=0.0%） |
| 一致率 Wilson 95% 下界 | 20.7% |
| nc_raw / nc_human（dp3） | 1 / 1 |
| 链断裂 / 跳过行 | 0 / 0 |

outcomes: ok=1, rework=0, rollback=0, inconclusive=0, pending=28

**数据不足，不结论**（N=1 < 5）：以下内容仅供观察，不构成调整依据。

## 判据表

| decision_id | dp | answer | confidence | mode | acted | outcome | override |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dp1-dispatch-type:mw-decision-substitution | dp1-dispatch-type | triage_type=research; triage_risk=low | 0.53 | auto | no | ok | no |
| dp1-dispatch-type:refresh@2026-10-21T03:39:33+00:00 | dp1-dispatch-type | (无 decide 行) | - | - | - | pending | no |
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
| dp25-signoff-conclusion:mw-decision-substitution@2026-10-21T15:40:32+00:00 | dp25-signoff-conclusion | q-conclusion=narrow | 0.7 | auto | no | pending | no |
| dp3-worker-clarify:mw-decision-substitution | dp3-worker-clarify | answer_kind=intent; answerable=0.04; candidate=c1 | 0.46 | auto | no | pending | no |
| dp3-worker-clarify:refresh@2026-10-21T03:39:33+00:00 | dp3-worker-clarify | (无 decide 行) | - | - | - | pending | no |
| dp3-worker-clarify:signoff@mw-decision-substitution@2026-10-21T15:31:29Z | dp3-worker-clarify | (无 decide 行) | - | - | - | pending | no |
| dp3-worker-clarify:signoff@mw-decision-substitution@2026-10-21T15:40:33Z | dp3-worker-clarify | (无 decide 行) | - | - | - | pending | no |
| dp4-failure-handling:refresh@2026-10-21T03:39:33+00:00 | dp4-failure-handling | (无 decide 行) | - | - | - | pending | no |
| dp5-test-triage:refresh@2026-10-21T03:39:33+00:00 | dp5-test-triage | (无 decide 行) | - | - | - | pending | no |
| dp6-qg-verdict:refresh@2026-10-21T03:39:33+00:00 | dp6-qg-verdict | (无 decide 行) | - | - | - | pending | no |
| dp7-gate-failure:refresh@2026-10-21T03:39:33+00:00 | dp7-gate-failure | (无 decide 行) | - | - | - | pending | no |
| dp8-scope-change:refresh@2026-10-21T03:39:33+00:00 | dp8-scope-change | (无 decide 行) | - | - | - | pending | no |
| dp9-model-select:refresh@2026-10-21T03:39:33+00:00 | dp9-model-select | (无 decide 行) | - | - | - | pending | no |

## 逐决策

### dp1-dispatch-type:mw-decision-substitution
- decide: ts=2026-10-21T07:04:42+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: ok (settled_by=pm-auto)
- note: confidence=0.53

### dp1-dispatch-type:refresh@2026-10-21T03:39:33+00:00
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

### dp25-signoff-conclusion:mw-decision-substitution@2026-10-21T15:40:32+00:00
- decide: ts=2026-10-21T15:40:33+00:00 available=True authority=advisory acted=False mode=auto
- outcome: pending (settled_by=-)
- note: intent=answer

### dp3-worker-clarify:mw-decision-substitution
- decide: ts=2026-10-21T03:39:56+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: pending (settled_by=-)
- note: confidence=0.46

### dp3-worker-clarify:refresh@2026-10-21T03:39:33+00:00
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp3-worker-clarify:signoff@mw-decision-substitution@2026-10-21T15:31:29Z
- decide: （缺失，孤立的 override/settle 行）
- outcome: pending (settled_by=-)

### dp3-worker-clarify:signoff@mw-decision-substitution@2026-10-21T15:40:33Z
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

suggest: none (N=1 < 5, 数据不足，不结论)

## 无法关联项

- dp1-dispatch-type:mw-decision-substitution: PM-local decision (task_key=null)
