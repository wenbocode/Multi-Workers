# RQ2 CLI starter/publication/races
- type: research

## 上下文
Goal: .agenticdoc/goal.md. Owning spec: .agenticdoc/mw-monitor-auto-restart/spec.md AC001–008. Source anchors packages/multi-workers/mw.py:5565 _monitor_open, :5301 _monitor_read_recorded, :5708 _monitor_stop. User approved compatible reuse / authenticated incompatible graceful replacement, no strong kill/live-state delete. RQ1 handles server lifecycle.

## 要求
Read full relevant files. Trace bare monitor/open/--no-open/status/stop and detached starter identity publication, locks, failure cleanup, concurrency races, existing targeted test seams. Recommend minimal design and file-isolated implementation boundaries including API contract with decision_monitor.py, exact citations. Do not implement/run any browser/shared service/live monitor/provider/model/build/install/commit/config/framework. Read-only source; testing proposals only.

## 唯一证据文件
.agenticdoc/mw-monitor-auto-restart/evidence/research/spec-cli-20261024.md

## 交付格式
Write only unique evidence above. Facts vs recommendations vs unknowns, path:line references, known tests/missing safety cases, minimal code surface. No other output writes except framework-generated report/output.
