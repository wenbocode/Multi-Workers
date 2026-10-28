# RQ1 identity and graceful lifecycle
- type: research

## 上下文
Goal: .agenticdoc/goal.md. Owning spec: .agenticdoc/mw-monitor-auto-restart/spec.md AC001–008. Source anchors packages/multi-workers/decision_monitor.py:2663 ensure_instance and :2539 AttachedInstance.stop. User approved incompatible authenticated graceful stop→confirmed shutdown→new start, compatible reuse, fail closed, no force kill/delete-live-state. PM serial phase docs.

## 要求
Read full relevant files. Trace compatibility vs identity/auth, stale/live/unknown, lock ownership, actual shutdown confirmation, races and test seams. Produce minimal design recommendations and exact path:line evidence, risky assumptions/unknowns. Do not implement or run real service/browser/model/provider/build/install/commit/config/framework. Do not operate user's monitor/shared serve. Read-only source; if testing needed describe plan only. Other research focuses CLI starter/publication.

## 唯一证据文件
.agenticdoc/mw-monitor-auto-restart/evidence/research/spec-lifecycle-20261024.md

## 交付格式
Write only unique evidence above. Facts vs recommendations vs unknowns; file:line citations; minimal viable changes and tests. No source writes, no other evidence target. Report/output may be framework-generated.
