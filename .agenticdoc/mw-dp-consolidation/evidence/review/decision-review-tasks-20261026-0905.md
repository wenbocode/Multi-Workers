# Decision Review — mw-dp-consolidation tasks

> 机器生成（`mw decide report`），数据源 `H:\git\Multi-Workers\.agenticdoc\_autopilot\decisions.jsonl`，只读 fold，**不作门控**。
> generated_at: 2026-10-26T01:05:28Z

## 概览

| 指标 | 值 |
| --- | --- |
| N（有效 settle，剔 inconclusive/pending） | 9 |
| decision groups / 档案行 | 45 / 87 |
| 已决策 / 自动生效(acted) / 上抛人 | 20 / 0 / 7 |
| override | 0（rate=0.0%） |
| 一致率 Wilson 95% 下界 | 70.1% |
| nc_raw / nc_human（dp3） | 0 / 0 |
| 链断裂 / 跳过行 | 0 / 0 |

outcomes: ok=9, rework=0, rollback=0, inconclusive=0, pending=36

## 判据表

| decision_id | dp | answer | confidence | mode | acted | outcome | override |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dp1-dispatch-type:05f9dcd7-efa7-4287-a0af-2485530431d7 | dp1-dispatch-type | triage_type=research | 0.95 | auto | no | ok | no |
| dp1-dispatch-type:11cdb8cb-1b7d-49d6-adf8-2ed64ae01498 | dp1-dispatch-type | triage_type=research | 0.67 | auto | no | pending | no |
| dp1-dispatch-type:1c7eea2f-3311-4c43-ab73-a6797af3fa9b | dp1-dispatch-type | triage_type=research | 0.97 | auto | no | ok | no |
| dp1-dispatch-type:231a7018-7701-40de-8dd1-ac227b9b639a | dp1-dispatch-type | triage_type=research | 0.62 | auto | no | pending | no |
| dp1-dispatch-type:3267234f-a597-434f-ac9a-213e4f2dd942 | dp1-dispatch-type | triage_type=research | 0.53 | auto | no | pending | no |
| dp1-dispatch-type:3a003b5e-4150-4b27-ae1c-322a293a2ec5 | dp1-dispatch-type | triage_type=research | 0.89 | auto | no | ok | no |
| dp1-dispatch-type:45d4d6e4-ecf6-4bcf-bfec-11490075ee5d | dp1-dispatch-type | triage_type=research | 0.98 | auto | no | ok | no |
| dp1-dispatch-type:46a0b6c2-e2f2-4f1e-bd77-e5b058884844 | dp1-dispatch-type | triage_type=research | 0.97 | auto | no | ok | no |
| dp1-dispatch-type:56ca64ea-c7ff-4570-99ef-310ff194203c | dp1-dispatch-type | triage_type=research | 0.95 | auto | no | pending | no |
| dp1-dispatch-type:69142b5b-733d-49cb-9edb-a54f41d1f082 | dp1-dispatch-type | triage_type=research | 0.85 | auto | no | ok | no |
| dp1-dispatch-type:6c85d942-a7f4-42f1-a0d5-06ed86e642b2 | dp1-dispatch-type | triage_type=review | 0.49 | auto | no | pending | no |
| dp1-dispatch-type:735e59e6-0ade-4cbd-849c-07323f8cd1a4 | dp1-dispatch-type | triage_type=research | 0.94 | auto | no | pending | no |
| dp1-dispatch-type:75128bf8-1fa1-42ff-ae81-d2bd98c73dee | dp1-dispatch-type | triage_type=research | 0.8 | auto | no | pending | no |
| dp1-dispatch-type:89b11325-34d5-4632-8aae-f8c9a466a8af | dp1-dispatch-type | triage_type=research | 0.98 | auto | no | ok | no |
| dp1-dispatch-type:a0b2f243-db96-4695-97db-59960ca7d280 | dp1-dispatch-type | triage_type=review | 0.51 | auto | no | pending | no |
| dp1-dispatch-type:a674da9d-d267-43a0-9c27-f7eb3906eef8 | dp1-dispatch-type | triage_type=research | 0.95 | auto | no | ok | no |
| dp1-dispatch-type:dfa3087d-db56-4e0d-bd33-e6cad5f8a5e3 | dp1-dispatch-type | triage_type=research | 0.91 | auto | no | ok | no |
| dp1-dispatch-type:e3450d66-30a6-4b8f-82b6-f408b322119e | dp1-dispatch-type | triage_type=research | 0.67 | auto | no | pending | no |
| dp1-dispatch-type:e7700ede-e626-4300-bf62-e3819aeb69cf | dp1-dispatch-type | triage_type=research | 0.88 | auto | no | pending | no |
| dp1-dispatch-type:fbbf1f4b-c111-448a-b1f4-90be7e47ce37 | dp1-dispatch-type | triage_type=research | 0.48 | auto | no | pending | no |
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
| dp25-signoff-conclusion:refresh@2026-10-21T16:22:39+00:00 | dp25-signoff-conclusion | (无 decide 行) | - | - | - | pending | no |
| dp3-worker-clarify:refresh@2026-10-21T03:39:33+00:00 | dp3-worker-clarify | (无 decide 行) | - | - | - | pending | no |
| dp4-failure-handling:refresh@2026-10-21T03:39:33+00:00 | dp4-failure-handling | (无 decide 行) | - | - | - | pending | no |
| dp5-test-triage:refresh@2026-10-21T03:39:33+00:00 | dp5-test-triage | (无 decide 行) | - | - | - | pending | no |
| dp6-qg-verdict:refresh@2026-10-21T03:39:33+00:00 | dp6-qg-verdict | (无 decide 行) | - | - | - | pending | no |
| dp7-gate-failure:refresh@2026-10-21T03:39:33+00:00 | dp7-gate-failure | (无 decide 行) | - | - | - | pending | no |
| dp8-scope-change:refresh@2026-10-21T03:39:33+00:00 | dp8-scope-change | (无 decide 行) | - | - | - | pending | no |
| dp9-model-select:refresh@2026-10-21T03:39:33+00:00 | dp9-model-select | (无 decide 行) | - | - | - | pending | no |

## 逐决策

### dp1-dispatch-type:05f9dcd7-efa7-4287-a0af-2485530431d7
- decide: ts=2026-10-25T16:25:06+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:11cdb8cb-1b7d-49d6-adf8-2ed64ae01498
- decide: ts=2026-10-25T16:07:03+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: pending (settled_by=-)
- note: confidence=0.67

### dp1-dispatch-type:1c7eea2f-3311-4c43-ab73-a6797af3fa9b
- decide: ts=2026-10-25T16:30:29+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:231a7018-7701-40de-8dd1-ac227b9b639a
- decide: ts=2026-10-25T02:13:13+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: pending (settled_by=-)
- note: confidence=0.62

### dp1-dispatch-type:3267234f-a597-434f-ac9a-213e4f2dd942
- decide: ts=2026-10-25T02:12:24+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: pending (settled_by=-)
- note: confidence=0.53

### dp1-dispatch-type:3a003b5e-4150-4b27-ae1c-322a293a2ec5
- decide: ts=2026-10-25T16:25:08+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:45d4d6e4-ecf6-4bcf-bfec-11490075ee5d
- decide: ts=2026-10-24T14:50:12+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:46a0b6c2-e2f2-4f1e-bd77-e5b058884844
- decide: ts=2026-10-25T02:12:21+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:56ca64ea-c7ff-4570-99ef-310ff194203c
- decide: ts=2026-10-24T14:50:14+00:00 available=True authority=advisory acted=False mode=auto
- outcome: pending (settled_by=-)
- note: intent=answer

### dp1-dispatch-type:69142b5b-733d-49cb-9edb-a54f41d1f082
- decide: ts=2026-10-25T02:12:23+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:6c85d942-a7f4-42f1-a0d5-06ed86e642b2
- decide: ts=2026-10-25T15:07:09+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: pending (settled_by=-)
- note: confidence=0.49

### dp1-dispatch-type:735e59e6-0ade-4cbd-849c-07323f8cd1a4
- decide: ts=2026-10-24T14:50:13+00:00 available=True authority=advisory acted=False mode=auto
- outcome: pending (settled_by=-)
- note: intent=answer

### dp1-dispatch-type:75128bf8-1fa1-42ff-ae81-d2bd98c73dee
- decide: ts=2026-10-25T16:07:04+00:00 available=True authority=advisory acted=False mode=auto
- outcome: pending (settled_by=-)
- note: intent=answer

### dp1-dispatch-type:89b11325-34d5-4632-8aae-f8c9a466a8af
- decide: ts=2026-10-25T16:30:31+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:a0b2f243-db96-4695-97db-59960ca7d280
- decide: ts=2026-10-25T15:07:07+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: pending (settled_by=-)
- note: confidence=0.51

### dp1-dispatch-type:a674da9d-d267-43a0-9c27-f7eb3906eef8
- decide: ts=2026-10-25T16:07:02+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:dfa3087d-db56-4e0d-bd33-e6cad5f8a5e3
- decide: ts=2026-10-25T16:07:07+00:00 available=True authority=advisory acted=False mode=auto
- outcome: ok (settled_by=pm-auto)
- note: intent=answer

### dp1-dispatch-type:e3450d66-30a6-4b8f-82b6-f408b322119e
- decide: ts=2026-10-25T16:25:05+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: pending (settled_by=-)
- note: confidence=0.67

### dp1-dispatch-type:e7700ede-e626-4300-bf62-e3819aeb69cf
- decide: ts=2026-10-25T16:07:05+00:00 available=True authority=advisory acted=False mode=auto
- outcome: pending (settled_by=-)
- note: intent=answer

### dp1-dispatch-type:fbbf1f4b-c111-448a-b1f4-90be7e47ce37
- decide: ts=2026-10-25T15:07:06+00:00 available=True authority=human acted=False mode=auto
- escalated_reason: low-confidence
- outcome: pending (settled_by=-)
- note: confidence=0.48

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

suggest: none (N=9, no threshold hit)

## 无法关联项

- （无显式登记的无法关联项）
