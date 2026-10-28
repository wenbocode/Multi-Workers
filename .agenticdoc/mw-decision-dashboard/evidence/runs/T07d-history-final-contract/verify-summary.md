# T07d verify summary (dd-history-final-contract)

| item | command / evidence | result |
|---|---|---|
| baseline (unmodified) | `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py test_decision_monitor.py -q` (`baseline/pytest-baseline-acceptance.txt`) | 207 passed, 1 skipped, exit 0 |
| baseline artifacts | `baseline/decision_history.py.before` `86a2a36d…` (2565 lines), `baseline/test_decision_history.py.before` `0d9cfe8a…` (1972 lines) | identical to the pre-change worktree (same hashes as T07c delivery) |
| RED (unmodified impl, final tests) | `red-02-new-tests-unmodified-impl.txt` | 6 failed, 45 deselected, exit 1 |
| RED import proof | `red-03-import-proof.txt` | imported `red-run/decision_history.py`; `filters_withheld`/`filters_basis`/`redactor` all absent; scrubbed capture has no `output_omitted` |
| RED reproducibility | `red-run/decision_history.py` = baseline hash; `red-run/test_decision_history.py` = delivered test hash `1825cf18…` | identical artifacts |
| new tests only | `-k page_filters_omit or page_filters_keep or capture_status_stays or empty_free_text_mapping or output_policy_documents or invalid_filter_errors` (`green-01-new-tests.txt`) | 6 passed, exit 0 |
| history suite | `python -m pytest test_decision_history.py -q` (`green-02-history-suite.txt`) | 51 passed (45 + 6), exit 0 |
| acceptance | `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py test_decision_monitor.py -q` (`green-03-acceptance.txt`) | 213 passed, 1 skipped, exit 0 |
| import proof (delivered) | `python import-proof.py` (`green-04-import-proof.txt`) | new API present; `output_omitted: True` on an omitted capture copy |
| output metric | `probe-page-output.py` (`probe-page-output.txt`) | complete page output known-secret occurrences 0 (5 page variants); `page(key=<secret>).total=1` + `filters.key=null`; legal filters unchanged; no-redactor raw contract; real production fold 38 records / 0 damaged / 0 warnings; ledger hashes unchanged |
| neighbour (read-only) | `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py test_decision_monitor.py test_decision_observation.py -q` (`neighbour-observation.txt`) | 342 passed, 1 skipped, exit 0 |
| dependency snapshot | `dependency-sha256.txt` | decision_history `bf1619d1…` (2672 lines), test `1825cf18…` (2180 lines), decision_wire `47ef6322…`, decision_monitor `2c2afb0e…`, decide_archive `57e91a1d…`, decide_signoff `05dd4f0e…`, decision.py `917706c2…`, mw_common `80af680d…`, gates `25191ec0…` |
| test inventory | `--collect-only -q` (`test-names-final.txt`) | 51 collected (45 pre-existing + 6 new) |
| biome (read-only) | `npx biome check --error-on-warnings .` (`check-biome-readonly.txt`) | exit 1; 1194 files; 3 warnings/2 infos all in pre-existing `packages/coding-agent/test/suite/mwoc-*.test.ts` (no TS touched) |
| `npm run check` (full) | not run | out of scope: 2 Python files only; a cross-package run would also cover other in-flight write faces |
| build / commit / model / network / services | not run | per card restrictions |

## What changed (behaviour)

- `HistoryPage.filters: dict[str, str | None]`; hit values are `None`, `filters_withheld` names the filter only,
  `filters_basis` states the policy. Selection still compares the raw input (`page(key=<secret>).total` unchanged).
- No redactor: filters are emitted as recorded (the previously defined contract), basis says so.
- Capture copies: read-side omission now also sets the closed-set `output_omitted=True`; the record gains
  `capture-output-omitted`. Stored `capture_status`/`wire_len`/`stored_len`/`captured_redacted_sha256` are untouched.
- `_Sanitizer.payload`: an empty free-text mapping key is dropped **and** counted in `omitted_fields`.
- `HistoryRecord` docstring states raw attributes are internal; `as_dict()`/`page()` are the safe serialisation.
- `page()` errors for a rejected filter value no longer echo the caller's value (filter name + closed set only).

## Known limits

- Only values the injected known-secret set recognises are omitted (no credential reading, no entropy guessing).
- Raw record attributes stay raw by design (documented in `HistoryRecord`).
- The monitor builds its own `filters` map from `page.filters` and does not forward `filters_withheld`/`filters_basis`;
  it also calls `load_history` without a redactor (its second layer redacts strings). Out of this card's write face.
- A consumer that ignores `byte_exact=False`/`output_omitted` can still read a stored `capture_status="ok"` as
  "complete"; the explicit fields and docstring are the documented answer, not enforcement.
- No real browser/HTTP end-to-end, no real credentials, no performance benchmark beyond the 38-record real fold.
- Windows junction/SMB/case-insensitive FS not exercised (existing symlink skips unchanged).
