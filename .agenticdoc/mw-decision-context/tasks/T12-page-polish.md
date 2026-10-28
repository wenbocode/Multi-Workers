# T12 — confirmed readable page revision (PM direct execution)

Goal: .agenticdoc/goal.md; approved user request 2026-10-23 “确认” and “先把当前讨论内容，修改并落地”.

Parallel analysis: UI files share one renderer/editor/test harness and require one PM writer. Criteria normalization backend can be inspected independently but joint API/editor acceptance is serial. No worker dispatch (avoids unauthorized automatic provider calls); T10/T11 stopped and acked. Phase stays EXECUTE.

References: packages/multi-workers/decision_dashboard.js:153 (page size), :531 (diagnostics), :2504 (question editor); packages/multi-workers/decision_points.py:1383 (instructions-only override).

Confirmed requirements:
- actual monitor port shown in header, no token/fragment display;
- history default five entries, normal paging/filter facets preserved;
- graphical DAG above full-width selected node details (both production/test);
- remove inline facets/filter/stats diagnostics; safety withholding gets concise notice, underlying facts retained;
- explain evidence as local provenance, not file-reading/model material; book advanced container separate from editable business state and questions;
- show complete instructions/options/criteria including native labels-based static questions and scaffold; static criteria descriptions editable per observation with fixed qids/types/option allowlists, dp3 candidates state-only; preview/send same authority;
- retain auth/secret/budget and no-production-write gates.

Write scope for this card: decision_dashboard.html/js/css; test_decision_context_readable_ui.py; decision_points.py; test_decision_context_readable_backend.py; test_decision_context_contract.py (approved override assertion migration only); test_decision_dashboard_assets.py, test_decision_context_workbench.py and test_decision_dashboard_playground.py (migrate obsolete 50-row/debug-prose expectations, retain security/facet/pagination assertions). Original files frozen before PM edits. No build/install/browser/provider/shared monitor/service/config/framework/commit. Auto-restart separately queued under mw-monitor-auto-restart; not mixed into this card.

Acceptance: RED before behavior changes; individual isolated suites full raw UTF8 logs+UTC/argv/cwd/exit. npm run check required after changes, preserve foreign bytes if formatter touches them. No deployment/24AC closure claimed.
