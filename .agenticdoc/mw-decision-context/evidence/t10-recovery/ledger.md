# T10 indirect-write compensating ledger

Original worker terminal status remains needs-clarification, exit2; output/report/progress/run fully absorbed and acked. Four ledger gaps correspond to allowed generated case outputs, not undisclosed authority writes. Do not alter original trace/output or mark worker done.

Independent verification: ../verify-t10-recovery.py exit0. verification.json carries original13/final14 snapshot hash+bytes checks, disk14 equality, recorded generator bash commands and four generated files reproduced in memory byte-exact using the inspected final generator. This establishes current generated provenance with the before/after records; not retroactive proof that the original framework ledger was complete.

Indirect writes by dc-t10-readable-backend through scripts/build_decide_cases.py: packages/multi-workers/decide_cases/dp1.json, dp2.json, dp3.json, dp25.json. All four appear in original14-path write_face and report manifest. Generator source/bytes fully read; no live regeneration/source write for this recovery.

Independent isolated individual verification (full raw UTF8 stdout/stderr and UTC/argv/cwd/exit in ../ui-recovery/backend-final-*): readable_backend24P, history23P, contract48P, monitor55P1S, dashboard_playground13P; all exit0. Monitor skip remains declared, not treated as pass. Worker runner used errors=replace and no env scrub itself, so PM fresh isolated evidence is the accepted verification, not a claim its archive is byte-exact or all runtime credential isolation proved by runner.

Business scope still incomplete: arbitrary valid static criteria editing is refused by implementation; clicked observation DAG bodies are null. Six adjacent legacy failures predate T10 but belong to overall integration reconciliation, not noise waived by this lane. Full check/review/24AC/deployment/visual acceptance pending. Backend now stopped, no checkpoint steer/termination/re-dispatch necessary. Previously unavailable dp2 did not authorize an action; normal terminal absorption is distinct.
