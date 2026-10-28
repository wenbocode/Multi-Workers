# T07 history-fold verify summary

cwd for every Python step: `packages/multi-workers` (unless stated). Evidence dir:
`.agenticdoc/mw-decision-dashboard/evidence/runs/T07-history-fold/`.
All stdout+stderr saved untruncated; no tail was used to store a log.

## Behaviour tests

| Step | Command | exit | Result | Log |
|---|---|---:|---|---|
| RED 1 (skeleton, 22 behaviours) | `python -m pytest test_decision_history.py -q` | 1 | `22 failed in 0.67s`, every failure `NotImplementedError` | `red-pytest-initial.txt` |
| RED 2 (authority/sign-off behaviours) | `python -m pytest test_decision_history.py -q` | 1 | `2 failed, 21 passed` — dp prefix for ledger-only rows; sign-off-only key | `red-pytest-authority-signoff.txt` |
| GREEN acceptance | `python -m pytest test_decision_history.py -q` | 0 | `23 passed` | `pytest-green-acceptance.txt` |
| GREEN repeat (same command, new socket-free run) | `python -m pytest test_decision_history.py -q` | 0 | `23 passed` | `pytest-green-repeat.txt` |
| Test names | `python -m pytest test_decision_history.py -q --collect-only` | 0 | `23 tests collected` | `test-names.txt` |
| Neighbours (read dependencies unchanged) | `python -m pytest test_decide_archive.py test_decide_signoff.py -q` | 0 | `110 passed` | `neighbour-pytest-archive-signoff.txt` |
| Mutation check (3 reverted behaviours, isolated copies) | `python mutate_and_run.py` | 0 | each mutant exit 1, exactly the intended test fails; "all mutants killed" | `mutant-check.txt`, `mutant-*.txt`, `mutate_and_run.py` |
| Production-byte isolation | `python isolation_check.py` | 0 | 4 production ledgers sha256 identical before/after `23 passed` | `production-bytes-isolation.txt`, `isolation_check.py` |

## Repository check (`npm run check`, cwd repo root)

`npm run check` starts with `biome check --write .`, which rewrites
`packages/coding-agent/test/suite/mwoc-*.test.ts` (other sessions' uncommitted
files, T01/T02b/T02c/T03 baseline), so the sub-steps were run **without
`--write`** (documented deviation, same as T02c). T15 owns the full command.

| Sub-step | exit | Note | Log |
|---|---:|---|---|
| `npx biome check --error-on-warnings .` | 1 | 3 warnings + 2 infos, all pre-existing `mwoc-*.test.ts` (other sessions; baseline); no Python file is scanned | `check-biome-readonly.txt` |
| `npm run check:pinned-deps` | 0 | | `check-pinned-deps.txt` |
| `npm run check:ts-imports` | 0 | | `check-ts-imports.txt` |
| `npm run check:shrinkwrap` | 0 | | `check-shrinkwrap.txt` |
| `npm run check:install-lock:coding-agent` | 0 | | `check-install-lock.txt` |
| `npx tsgo --noEmit` | 0 | no output (empty log is the pass evidence; exit recorded here) | `check-tsgo-noemit.txt` |
| `npm run check:browser-smoke` | 0 | | `check-browser-smoke.txt` |

## [VERIFY] indicators and their real sources

Read-side indicators only; the VC verdicts also need T08/T09/T10/T11/T13.

| Indicator | Value (asserted here) | Assertion |
|---|---|---|
| filter_mismatches | 0 | `test_filters_are_exact_and_pagination_is_lossless` (exact set equality + lossless paging) |
| test_rows_in_production | 0 | `test_default_history_is_cross_key_production_only`, `test_production_and_test_statistics_are_split` |
| pending_stages_labelled | true | `test_stages_are_separate_and_missing_ones_are_not_recorded`, `test_open_attempt_without_end_is_pending_not_delivered` |
| false_consumption | 0 | `test_adopted_does_not_imply_consumed_or_executed` |
| fabricated_raw | 0 | `test_capture_markers_are_per_row_and_never_relabelled` (`byte_exact=false`, `text_omitted=true`, no reconstructed field) |
| inferred_unlabelled | 0 | `test_unlinked_calls_are_not_attached_to_the_nearest_decision`, `test_unknown_lifecycle_word_is_not_a_stage` |
| false_execution | 0 | `test_stages_are_separate_and_missing_ones_are_not_recorded` (executed needs acted/actual_action) |
| machine_as_human | 0 | `test_machine_rows_are_never_labelled_human` |
| archive_roots / foreign_reads_writes | 1 / 0 | `test_history_reads_only_the_control_root`, `production-bytes-isolation.txt` |
| logical vs http attempts | separate fields, no backfill | `test_logical_calls_and_http_attempts_are_counted_separately`, `test_missing_wire_attempts_is_not_backfilled` |
