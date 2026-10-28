# T13 — DP test interaction feedback (PM direct execution)

Goal: .agenticdoc/goal.md. User confirmed continuation of refresh/button/DAG/one-second status request.

Parallel analysis: tab selection, operation feedback, polling and DOM harness share decision_dashboard.js; one PM writer, serial RED/GREEN integration. No dispatch/provider calls. Existing workers terminal/acked. Phase EXECUTE; audit PASS.

References: packages/multi-workers/decision_dashboard.js:2294 scaffoldSelected, :2363 sendSubmit, :2920 selectTab; packages/multi-workers/decision_dashboard.html:92 test panel; packages/multi-workers/decision_playground.py:1777 recorded running state.

Requirements:
- Explicit refresh for current tab, using existing memory token (not browser reload).
- Enter DP test tab: close history dialog, read test metadata/history, show selected test DAG or honest empty test DAG; no model POST.
- Scaffold/validate/submit/retry: immediate and terminal status, corresponding DAG update and test operation feedback. Scaffold/preview/local refusals clearly labelled page-local, zero model calls, not persisted backend decision records.
- From submission start through completion: every 1000ms read-only refresh history/current submission, no overlapping poll rounds, no automatic submit/retry. Stop on terminal result; fail honestly; retain final detail. Preserve selected node detail across refresh.
- Identity/options/auth/redaction/budget/observe-only/no-production-write contracts unchanged.

Allowed source: decision_dashboard.html/js/css; test_decision_context_readable_ui.py; test_decision_dashboard_assets.py and test_decision_dashboard_playground.py only obsolete read-on-tab expectations and new route fixtures. Task/evidence/PM progress documents within this key.
Forbidden: shared monitor/service operations, real browser/Jev/provider, config/framework, build/install/commit, foreign files.
Acceptance: isolated synthetic DOM/deferred responses/fake clock and existing targeted suites; full raw logs+metadata; protected npm run check on latest byte copy, no foreign fixes. Source acceptance is not deployment or whole-key closure.
