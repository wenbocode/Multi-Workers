# T16 case-prefilled scaffold

User authorized immediate repair of Test4 regression. Root cause: scaffoldSelected only requested {dp}, replaced editor with server empty book and cleared caseLoaded. Prior image read and JS trace confirmed. Active key claimed; EXECUTE audit passed. Parallel analysis: JS/test single-writer PM, no dispatch/provider.

Minimal change JS only: before server scaffold, if actually loaded case.dp and book.decision_point both equal selected DP, clone loaded original book into editors, restore its questions, retain loaded-case reset provenance, reset submit id/digest and clear stale outputs. Honest local operation status/DAG, no network call. No-case or mismatched-DP still uses unchanged server scaffold path. Explicit generation restores original case content (including state/notes/handling_options); does not silently merge edits or guess facts.

Original two-file bytes/hashes t16-baseline/. Added six regressions: four native cases verify full book/state/questions and question reset, local zero-request generation, source-case immutability; two no-loaded/mismatched-DP server fallbacks verify selected DP only and no submit. RED four expected case losses, two fallback passes. Fresh GREEN five files36+9+17+119+13=194P, all exit0; raw UTF8 output and metadata ui-recovery/t16-green-*; RED ui-recovery/t16-red-*.

Protected full npm run check latest copied11738 files exit1; unchanged outside three mwoc files3warnings2infos, later checks not run. t16-check/ metadata formatter_changes=[], original_changed_during_check=[]. No foreign changes applied.

No real browser after-change, model, shared monitor operation, build/install/commit/framework/config or deployment. Source fix verified with shipped Node DOM only, not formal whole-key closure. EXECUTE unchanged.
