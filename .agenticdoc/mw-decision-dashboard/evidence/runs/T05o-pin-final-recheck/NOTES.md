# T05o evidence notes - what these logs contain

## Isolation (every run)

- The wrapper `workers/dd-pin-final-recheck/run_round.py` removed every
  credential-shaped variable from the child env (`*_API_KEY|_TOKEN|_KEY|_SECRET|_PASSWORD`
  and `TIMI_*`; the two present on this host were `TIMI_API_KEY` and
  `TAI_PAT_TOKEN`), pointed `HOME`/`USERPROFILE` at a throw-away tmp dir, dropped
  `PYTHONPATH`, and recorded the removed names in each log header.
- The tests themselves are hermetic per file: an autouse fixture removes the
  whole credential-shaped env set, points `HOME`/`USERPROFILE` into `tmp_path`,
  patches `decision_backends._auth_json_path` to a tmp file *before* any read,
  and the discovery spy aborts if the resolved auth path is not the tmp one
  (`test_decision_pin_contract.py` fixture + spy). The T05m/T05n six files carry
  their own equivalent fixtures.
- No real `~/.pi/agent/auth.json`, no real credential, no Jev/paid model, no
  browser, no service. The only sockets are stdlib `http.server` instances bound
  to `127.0.0.1:0`.
- Fixture values are fabricated (`t05o-sent-a-...`, `t05o-nonebase-pin-p-...`,
  `t05o-foreign-old-b-...`, `t05o-foreign-new-c-...`, `t05o-env-ambient-d-...`).
  They are NOT masked: pytest quotes them verbatim in the failing assertions and
  that quote *is* the RED evidence. No real credential value appears anywhere.

## RED rounds (all recorded, not only the authoritative one)

- `logs/red-01-pin.log` (2026-10-22T09:59:30Z, first draft test bytes
  `77d76163...`, live pre-change source): 4 failed / 2 passed. Test 3 failed
  because its first version used the wrong probe answers for the points call;
  test bytes were corrected afterwards.
- `logs/red-02-pin.log`: the corrected client-level part, but the points-preserved
  test still asserted the wrong discovery expectation; 4 failed / 2 passed.
- `logs/red-03-pin.log` (UTC 10:00:26-10:00:30, live pre-change source
  `decision.py b287339f...` / `decision_points.py b2d47748...`, test bytes
  `1d04363a...`): **3 failed / 3 passed**. This is the wall-clock RED that ran
  before the implementation edit. The three failures are exactly the new
  contract points: None-base pin sent at the client entry, points entry did not
  raise, and raw set drift between the gate and capture faces. The third
  relaxed assertion (discovery-count equality instead of `== []`) was added
  after this round; in red-03 the drift assertion fired before reaching it, so
  the RED result is unaffected.
- `logs/red-04-baseline-pin.log` (UTC 10:01:32-10:01:35): **reproduction, not a
  wall-clock pre-edit run**. It imports the archived pre-change modules
  `baseline/modules/decision.py` (`b287339f...`) and
  `baseline/modules/decision_points.py` (`b2d47748...`) with the *final* test
  bytes (`6628771d...`): 3 failed / 3 passed, same three tests. The wrapper's
  DEPS header hashes the live package tree (post-fix); the imported baseline
  hashes are recorded in `hashes/red-04-baseline-imports.sha256`. The
  `baseline/modules/` test copy is byte-identical to the final test file.
- `baseline/decision.py` / `baseline/decision_points.py` are the pre-change
  copies (also `b287339f...` / `b2d47748...`). `diff-decision.patch` and
  `diff-decision-points.patch` are the minimal owner diffs (no fixture value,
  no hardcoded key).

## GREEN rounds

- `logs/green-01-pin.log`: 5 passed / 1 failed. The failure was the (then
  over-strict) probe assertion `calls == []`; the production gate legitimately
  pays the one legacy timi leg (T05m). The test was relaxed to
  `len(calls) == discoveries_after_gate`, no source change.
- `logs/green-02-pin.log` and `logs/green-03-pin.log`: two independent runs,
  `6 passed` each, source hashes `decision.py c227a64b...` /
  `decision_points.py 0693a98c...` / test `6628771d...` identical before and
  after each run.

## T05m / T05n re-verification (new time point, two rounds each)

- Exact original six-file sets were re-run, not a subset:
  - T05m: `test_decision_bare_scope_known_set.py test_decision_known_set_snapshot.py
    test_decision_timi_credential_snapshot.py test_decision_credential_seam.py
    test_decision_book_known_secrets.py test_decision_wire_transport.py`
    -> `t05m-r1.log` 80 passed (28.32s), `t05m-r2.log` 80 passed (28.42s).
  - T05n: `test_decision_full_value_freeze.py test_decision_bare_scope_known_set.py
    test_decision_known_set_snapshot.py test_decision_credential_seam.py
    test_decision_timi_credential_snapshot.py test_decision_book_known_secrets.py`
    -> `t05n-r1.log` 63 passed (20.97s), `t05n-r2.log` 63 passed (21.05s).
- Each log carries the complete argv, cwd, UTC start/end, isolation lines, exit
  code and dependency hashes before/after. No log is tailed; pytest output is
  written in full.
- These are new-time-point results. They do NOT retro-certify the old T05m/T05n
  logs that lacked command headers (F-1 debt): the old 80/63 numbers are merely
  arithmetically consistent, not independently attested.

## Adjacent / known debt

- `logs/adjacent-suites.log`: all 33 `test_decision_*.py` + `test_decide_*.py`
  files -> `1296 passed, 1 skipped` (77.00s), exit 0.
- `logs/dispatch-decide-prepare.log`: `1 failed, 22 passed`; the failure is the
  pre-existing same-key migration debt
  `test_dispatch_decide_prepare.py::test_dp_without_required_state_fields_is_refused`
  (T05n recorded the identical failure at the same file). It is not exempted and
  not touched by this card.

## Root read-only checks (no `--write`, no full `npm run check`)

- `logs/check-biome-readonly.log`: `npx biome check --error-on-warnings .`,
  exit 1 from the pre-existing `packages/coding-agent/test/suite/mwoc-*.test.ts`
  warnings/infos (3 warnings, 2 infos, 1194 files checked). Unrelated to this
  Python-only card.
- `check-pinned-deps`, `check-ts-imports`, `check-shrinkwrap`,
  `check-install-lock-coding-agent`: all exit 0.
- The full `npm run check` (biome `--write`, `tsgo`, browser smoke) was NOT run
  and is not equivalent. No build, no commit, no full-package pytest, no real
  model.
