# T07c verify summary (dd-history-output-safety)

| item | command / evidence | result |
|---|---|---|
| baseline (unmodified) | `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py -q` (`baseline/pytest-baseline-acceptance.txt`) | 149 passed, exit 0 |
| baseline artifacts | `baseline/decision_history.py.before` `EB345E77…`, `baseline/test_decision_history.py.before` `035C0053…` (`artifact-sha256.txt`) | hashes match the pre-change worktree |
| RED (unmodified impl, delivered tests) | `red-02-structural-secret-unmodified-final-tests.txt` | 6 failed, exit 1 (value-echo assertions) |
| RED import proof | `red-02-import-proof.txt` | imported `red-run/decision_history.py`; no `_scrub_output`/`structural_withheld`/`redactor` |
| RED reproducibility | `red-run/decision_history.py` = baseline hash; `red-run/test_decision_history.py` = delivered test hash | identical artifacts |
| acceptance | `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py -q` (`green-02-acceptance.txt`) | 155 passed, exit 0 |
| history suite | `python -m pytest test_decision_history.py -q` (`green-02b-history-suite.txt`) | 45 passed, exit 0 |
| new tests only | `-k structural_known_secret or nested_capture_and_usage or structural_omission_keeps or no_redactor_keeps or secret_bearing_warning or repeated_serialization` (`green-01-new-tests.txt`) | 6 passed, exit 0 |
| test inventory | `--collect-only -q` (`test-names-final.txt`) | 45 collected (39 pre-existing + 6 new) |
| output metrics | `probe-output-surface.py` (`probe-output-surface.txt`) | secret occurrences 65 → 0; internal projection equal; `page(key=secret)=1`; withheld 25/12/5 |
| real production fold (read-only) | `probe-real-production-history.py` (`probe-real-production-history.txt`) | 38 records, 0 damaged, 0 dropped, 0 invalid_keys, 0 structural_withheld, 0 warnings, 0 detail errors |
| neighbour monitor (read-only, T10b in flight) | `python -m pytest test_decision_monitor.py -q` (`neighbour-monitor-readonly.txt`) | 52 passed, 1 skipped, exit 0; two snapshots in `neighbour-snapshot-sha256.txt` |
| neighbour consumers | `python -m pytest test_decide_sign_auto.py test_decision_wire_store.py -q` (`neighbour-consumers.txt`) | 119 passed, exit 0 |
| biome (read-only) | `npx biome check --error-on-warnings .` (`check-biome-readonly.txt`) | exit 1; 1194 files; 3 warnings/2 infos all in pre-existing `packages/coding-agent/test/suite/mwoc-*.test.ts` (no TS touched here) |
| `npm run check` (full) | not run | out of scope: 2 Python files only; cross-package run would also cover T10b's in-flight write face |
| build / commit / model / network / services | not run | per card restrictions |

## RED vs "post-fix mutant"

- `red-02-*` was produced by copying the delivered `test_decision_history.py` next to an
  unmodified copy of `decision_history.py` (`baseline/…before`) and running pytest with
  that copy first on `PYTHONPATH`; `red-02-import-proof.txt` proves the imported module
  and the absence of the new API. No fixed-then-mutated source was used.
- `red-01-*` is the earlier RED run from the same unmodified implementation with the
  first assertion set (5 failed); it is kept for traceability, `red-02` is authoritative.

## Known limits

- Only values the injected redactor recognises are omitted (reader never reads
  credentials, no entropy guessing).
- Raw record attributes (incl. `identity`, `archive`, `calls`) stay raw by design;
  consumers must serialise via `as_dict()` / `page()`.
- `page.filters` echoes caller input (not carrier bytes); the monitor's second
  redaction layer covers its string values.
- No new top-level warning for structural omissions; per-record marks only.
- Performance not benchmarked beyond the 38-record production fold.
