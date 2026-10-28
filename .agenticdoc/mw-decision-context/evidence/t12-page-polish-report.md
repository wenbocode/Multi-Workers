# T12 current discussion implementation

## Authority / scope
User confirmed page refinements and requested implementation, then continued. Existing key claimed, EXECUTE audit PASS. T10/T11 stopped/acked; PM single writer, no dispatch/provider/service/build/install/browser/framework/commit. Independent safe auto-restart remains unimplemented and outside T12.

## Landed source
- dashboard HTML/CSS/JS: monitor URL port, history default 5, vertically full-width DAG/detail, concise withholding notice instead of facet/filter/read-statistics diagnostics.
- Primary business state editor, native complete questions, advanced local book/provenance explanation. Static labels exposed as editable criteria; dp3 single-source unchanged.
- decision_points: static choice criteria descriptions may change for one observation only; exact allowed option keys, qid/type/choices/labels remain fixed. Non-empty bounded string and NUL validation; known-secret gates preserved. Normalized criteria shared by preview and send. Production registry unchanged.
- Observation DAG input uses this submission's actual untruncated request capture state, never current editor. Request/response node details use shared readable capture renderer and raw-copy behavior. Missing receipt and non-executed action remain honest. No recorded policy threshold is invented.
- Invalid primary material JSON blocks sending the earlier valid book. Valid reload/edit resets block.
- Migrated only obsolete limit=50/debug prose test expectations; retained real facets/filter/paging/auth/secret/XSS/no-production-write assertions.

## Fresh behavioral evidence
Full raw stdout/stderr and UTC/argv/cwd/exit envelopes in evidence/ui-recovery/:
- t12-criteria-red: backend 4F28P, edited static criteria rejected by instructions-only gate; secret case could not reach secret gate.
- t12-criteria-green: backend32P, contract48P, assets9P, workbench17P, exits0.
- t12-dag-red: UI1F18P, clicked input body absent.
- t12-dag-green: UI20P, workbench17P, dashboard contracts119P, exits0. Includes actual loopback submit -> submission detail/history/dps routes -> shipped DOM clicks; provider calls only private synthetic HTTP.
- t12-editor-red: invalid business editor still submitted old book, 1F. Fixed in source.
- t12-final: UI21P/backend32P/contract48P/assets9P/workbench17P/dashboard contracts119P, exits0; playground1F12P solely obsolete limit=50 route.
- t12-playground-green: migrated old route/statistics assertions, playground13P exit0.
- Latest distinct seven-file total 259 passed, zero remaining failures in those files. No full suites executed.

## Full check (NOT green)
evidence/t12-protected-check.py copied 11,668 tracked/untracked nonignored working-tree files with source hashes, reused existing node_modules read-only junction, isolated HOME and removed secret/proxy env. Ran full npm run check in copy. At 2026-10-23T10:11:21.661700Z -> 10:11:23.633101Z exit1:
- biome checked1210 files, no fixes applied, 3 warnings +2 infos in mwoc-matrix-t07.test.ts, mwoc-w2-contract-judgment.test.ts, mwoc-w3-ledger-extractor.test.ts.
- Files outside T12 write scope; not modified to chase check. npm chain stopped at biome, so pinned deps/imports/shrinkwrap/install-lock/typecheck/browser-smoke did not run in this attempt.
- No copied formatter changes, original_changed_during_check=[]; original workspace bytes not touched by check.
Full stdout/stderr/metadata/source-hashes at evidence/t12-check/. This is copied-worktree full check evidence, not direct in-place check or successful quality closure.

## Remaining / limits
Actual browser visuals, current user monitor reload/deployment, formal24AC reconciliation/review/quality, original TS encoding uncertainty, framework finalize gate adaptation remain pending. Observation decision threshold unavailable in submission projection is explicitly unknown; this patch does not invent or persist new policy facts. Auto-restart not implemented. EXECUTE unchanged; no claim of whole-key completion.
