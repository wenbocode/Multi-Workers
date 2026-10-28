# T05q evidence notes - what these logs contain

## Isolation (every run)

- Wrapper `workers/dd-coverage-convergence/run_round.py` removes every
  credential-shaped child-env name (`*_API_KEY|_TOKEN|_KEY|_SECRET|_PASSWORD`
  and `TIMI_*`), points `HOME`/`USERPROFILE` at a throw-away tmp dir, drops
  `PYTHONPATH`, and records the removed names in each log header.
- The new test file is hermetic per test: an autouse fixture removes the whole
  credential-shaped env set, points `HOME`/`USERPROFILE` into `tmp_path`,
  patches `decision_backends._auth_json_path` to a tmp file *before* any read,
  and the discovery spy aborts if the path a discovery would read is not inside
  that tmp home.
- No real `~/.pi/agent/auth.json`, no real credential, no Jev/paid model, no
  browser, no service. The only sockets are stdlib `http.server` instances
  bound to `127.0.0.1:0`.
- Fixture values are fabricated: `zqsent-9182736450` (sent Authorization),
  `zqlegacy-5647382910` (legacy timi leg), `zqenv-8273645910` (ambient env),
  `plain-material-abcdef` (allowed text). They share no 4-character window with
  each other on purpose, so a fragment assertion cannot false-positive on the
  allowed text. They are NOT masked: pytest quotes them verbatim in failing
  assertions and that quote *is* the RED evidence. No real credential value
  appears anywhere.

## RED rounds (all before the implementation edit)

- `logs/red-01..red-05-*.log` are test-authoring iterations, each recording
  `[DEPS BEFORE] == [DEPS AFTER]` (source untouched): fixture fragment
  collisions with `plain-t05q-material-0123456789`, points rows read from
  `evidence.jsonl` instead of `wire.jsonl`, and `KnownSecretRedactor` wrongly
  listed as a capture filter. Only test bytes changed between them.
- `logs/red-06-coverage-safety.log` ran an earlier test-bytes version
  (`ac0af8f3`): 15 failed / 5 passed with the same pre-change source.
- **`logs/red-07-coverage-safety-final-bytes.log` is the authoritative RED**: it
  runs the *shipped* test bytes (`a5fcf413...`) against the pre-change source
  (`decision.py 106ebaef...`, `decision_points.py 0693a98c...`), UTC
  10:46:41-10:46:48, **17 failed / 5 passed**. The 17 = 5 predicate + 2
  gate-shaped + 5 client-entry + 5 points-entry failures, exactly one per leak
  class:
  1. `hits-lie-keeps-value` - client: `requests=1, captured_rows=3,
     stored_value=True, stored_long_tail=True, stored_legacy=True`; points:
     `requests=1, rows=5, stored_value=True, stored_legacy=True`.
  2. `prefix-only` - same stored raw facts.
  3. `partial-tail` - `stored_value=False, stored_long_tail=True`: the full
     value was replaced but the tail reached the ledger. This is the exact case
     "`value not in output`" cannot see, i.e. the reviewer's suggested fix alone
     would not have closed F-1.
  4. `no-hits-trivial-change` - `hits`-less result whose text merely changed;
     the value (fragment) was still stored.
  5. `missing-scrub` - complete value redaction but no `scrub_tail_prefix`:
     `requests=1, capture_status='ok'`, ~no captured rows, i.e. the call
     reported success while the capture silently stored nothing (T05p F-2).
  The 5 passing tests are the preservation side (trusted/wrapped filters keep
  working, plus the long-tail scrub of a complete filter).

## GREEN / acceptance

- `logs/green-01/green-02` were test-side corrections (a gate-shaped
  `KnownSecretRedactor` was still listed as trusted; a refused points call does
  leave its decision row, just no attempt/book material).
- `logs/green-03-coverage-safety.log`: new file alone, 22 passed, exit 0, with
  the same final test bytes and post-change source.
- `logs/green-04-coverage-safety.log`: after temporarily restoring the pre-change
  source for red-07 and putting the fixed source back (hashes verified
  `c2b6d0a6...` / `d299f67e...`), the new file alone again: **22 passed**, exit 0,
  UTC 10:47:00-10:47:08. Together with red-07 this is a same-test-bytes
  RED -> GREEN pair.
- `logs/t05q-r1.log` / `logs/t05q-r2.log`: the card's exact six-file argv, two
  independent rounds, **77 passed** each (33.77s / 33.59s), exit 0, complete
  argv/cwd/UTC/isolation/DEPS-before-after headers. r2 ran in a fresh process
  with a different tmp HOME. `logs/t05q-r3.log` repeats the same argv after the
  red-07 baseline restore: **77 passed** (33.84s), exit 0.
- `logs/adjacent-decision-suites.log`: all 24 `test_decision_*.py` + the
  `test_decide_*.py` files -> `2 failed, 1329 passed, 1 skipped` (93.13s). Both
  failures are `test_decision_dashboard_assets.py` asset-byte comparisons; a
  *concurrent* session rewrote `decision_dashboard.js` at 18:43:24 local time
  inside that run window (the test compares import-time `STATIC_ASSETS` with
  on-disk bytes). `logs/dashboard-assets-recheck.log` re-runs that file alone:
  **exit 0**, so the two failures are the concurrent asset write, not this card.
  The same session also rewrote `decision_monitor.py` (`2c2afb0e` ->
  `c6e8e11f`) mid-r1; it is outside this card's write face and R1 still passed.

## Discovery-count facts (frozen, not live)

- Every refusal pays exactly one legacy discovery (the coverage check has to know
  the complete set of the unit); retries never happen (refused before the
  attempt loop); the memo is reused, so a second face costs nothing.
- A complete caller filter: one discovery, two POSTs (500 then 200) still cost
  one freeze; `ContextVar` is `None` after the call; the caller's filter object
  and the pinned snapshot are untouched.

## Long-tail proof (real boundary)

`test_client_entry_keeps_a_complete_filter_scrubbing_a_long_secret_tail` first
measures the real sent body, then sets `segment_cap`/`read_window` so the read
window cuts 8 characters into the sent secret. The stored request capture is
`read_capped=True, boundary_scrubbed=True`, ends inside the allowed prefix and
contains no 4+ character fragment of either secret - the caller's verified
`scrub_tail_prefix` did the removal at the real capture boundary.

## Root read-only checks (no `--write`, no full `npm run check`)

- `logs/root-readonly-checks.log`: `python -m compileall` exit 0; biome
  `check --error-on-warnings .` exit 1 from the pre-existing
  `packages/coding-agent/test/suite/mwoc-*.test.ts` warnings/infos (3 warnings,
  2 infos, 1195 files) - the same baseline T05p recorded, unrelated to this
  Python-only card; `check:pinned-deps` / `check:ts-imports` /
  `check:shrinkwrap` / `check:install-lock:coding-agent` all exit 0.
- The full `npm run check` (biome `--write`, tsgo, browser smoke) was NOT run
  and is not claimed. No build, no commit, no full-package pytest, no real
  model, no service, no browser.

## Hash / diff artifacts

- `hashes/baseline.sha256`: pre-change seven dependency files
  (`decision.py 106ebaef...`, `decision_points.py 0693a98c...`); the two owner
  files are archived byte-identical under `baseline/`.
- `hashes/final.sha256`: post-change seven dependency files plus the new test
  (`c2b6d0a6...` / `d299f67e...` / `a5fcf413...`); verified identical after the
  red-07 baseline restore/put-back.
- `diff-decision.patch` / `diff-decision-points.patch`: the complete owner diffs
  (204 / 68 lines), no fixture value, no hardcoded key. `final/` holds the exact
  post-change `decision.py` / `decision_points.py` bytes used by green-04 and
  r3 (working tree verified byte-identical to it).
- `decision_monitor.py` differs between baseline and final **only** because of
  the concurrent session described above; `decision.py` /
  `decision_points.py` are the only files this card changed.
