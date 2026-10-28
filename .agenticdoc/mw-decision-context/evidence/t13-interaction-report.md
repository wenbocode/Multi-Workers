# T13 — test interaction source verification

## Scope / root cause
User requested explicit refresh, test-tab DAG switching, scaffold/preview/submit/retry feedback, and one-second running status refresh. Existing selectTab intentionally read nothing; scaffold/validate only wrote editor/output; sendSubmit refreshed history once after response and never opened its detail. No running poll existed.
Single PM writer: dashboard HTML/JS/CSS and readable UI/assets/playground tests. Baseline raw bytes/hash and git status: evidence/t13-baseline/. No worker dispatch, real provider/browser, deployment, shared monitor/service operation, build/install/commit or framework/config edits.

## Source behavior
- Header `dashboard-refresh` reuses memory token to read current tab data, not browser reload.
- Enter test tab closes production dialog, reads DP/history and opens explicit selected/latest test submission detail; empty history shows explicitly local unstarted ten-node graph.
- Scaffold/validate have immediate and terminal status, local operation feedback (20 entries, page memory only), input/preview DAG. Preview request is labelled unsent, never rendered as actual wire capture.
- Submit/retry immediately disable conflicting controls and show pending decide node. Each 1000ms timer reads history/current submission sequentially, never overlaps a poll round, never sends a model POST. Terminal projection or POST completion stops timer; epoch checks discard late history/detail results. Selected node detail and pressed state survive refresh.
- Terminal POST result automatically reads history and that submission detail. Busy/refusal/transport failures stay failures or unknown; no automatic retry. Existing same-book id dedupe and explicit new-id/retry_of remain.
- Actual observation nodes still come from captured request/response of that submission. Local preparation feedback is distinctly not backend decision/production record. DP/case changes update local test graph; conflicting changes refused during active submit.

## Verification
Initial TDD: evidence/ui-recovery/t13-red-* = 3 failures / 21 passes (missing refresh, no local DAG/feedback, no poll). First implementation = 23P/1F, only prior route-allowlist needed read-only submission-detail migration. Neighboring assets/playground failed old read-nothing-on-tab expectations; migrated assertions preserve GET-only/auth/no-submit boundaries, and replay added explicit empty history entry for new tab GET.
Fresh final seven distinct files, all exit 0 (evidence/ui-recovery/t13-final-metadata.json and full stdout/stderr):
- readable UI 27P (six new tests incl parameterized late history/detail, nonoverlap and read failure);
- assets 9P; workbench 17P; dashboard contracts 119P; playground 13P;
- readable backend 32P; context contract 48P;
- total 265P. Synthetic deferred responses/fake 1000ms timer exercise shipped DOM/JS. Race additions are postimplementation regression verification, not claimed test-first RED.

Protected full `npm run check` latest source byte-copy: evidence/t13-check/metadata.json, stdout.log, stderr.log, source-hashes.json. 2026-10-23T12:10:55Z–12:10:56Z, exit1. 11,693 copied files; formatter_changes=[]; original_changed_during_check=[]. Biome1210 files: 3 warnings/2 infos in outside-card mwoc-matrix-t07.test.ts, mwoc-w2-contract-judgment.test.ts, mwoc-w3-ledger-extractor.test.ts. Later chained checks not executed; no foreign edits applied.

## Outstanding / boundaries
No actual browser visual or live-monitor acceptance; no latest deployment. Local operation feedback survives only this page session; scaffold/preview do not become persisted model-decision records. Poll interval is 1000ms between completed rounds to avoid piling requests up on a slow monitor. Full check remains blocked by outside-scope diagnostics. Whole-key review/24AC reconciliation, framework finalize permission, original TS byte uncertainty and separate approved auto-restart task remain pending. EXECUTE unchanged.
