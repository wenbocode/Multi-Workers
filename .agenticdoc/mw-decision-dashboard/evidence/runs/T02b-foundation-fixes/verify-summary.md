# T02b foundation fixes - verify summary

cwd `packages/multi-workers` unless stated. All commands run on Windows (PowerShell),
no network, no paid model, no build, no commit.

## RED (tests written first, run against the audited implementation)

| command | exit | result | log |
|---|---|---|---|
| `python -m pytest test_decision_wire_store.py test_decision_roots_locks.py -q` | 1 | `33 failed, 85 passed` | `red-pytest.txt` |
| temp-copy re-check with the pre-fix scrub (`revert-scrub-repro.py`): `python -m pytest test_decision_wire_store.py -q -k "long_secret or longer_than_read_window or one_to_three"` | 1 | `8 failed, 2 passed` | `red-pytest-scrub-recheck.txt` |

Why two RED artifacts: `decision_wire.py` is untracked, so git cannot return the
audited version. `red-pytest.txt` is the real pre-fix run for the whole set. Two
fixtures were then strengthened (default-caps leftover length, UTF8 trim
construction), so `revert-scrub-repro.py` re-applies ONLY the pre-fix tail scrub
(fixed 64 char window, `min_prefix=4`) to a **temp copy**
(`%TEMP%/t02b-red`, worktree untouched) and re-runs the long-secret subset: every
long-secret / short-tail test is RED against the defect and GREEN against the fix.
The 2 passing cases there are the fixture self-check and the "fully present secret
is redacted" control.

Representative RED assertion messages (measured, not inferred):
- `AssertionError: 1 char tail was kept` (1-3 char leftover, old `min_prefix=4`).
- `assert False is True` for `cap.boundary_scrubbed` with 90 / 80 / 204 secret
  characters retained at the segment / UTF8-trim / default-caps boundaries.
- `TypeError: lock_owner_state() got an unexpected keyword argument 'alive_state_probe'`
  and `AttributeError: process_alive_state` (pre-fix P1-4 API absent).
- `assert [None] is None` / `"bogus_key" in str(exc.value)` failures for the
  metadata + unknown-key contract tests.

## GREEN

| command | exit | result | log |
|---|---|---|---|
| `python -m pytest test_decision_wire_store.py test_decision_roots_locks.py test_decide_backends.py -q` (acceptance) | 0 | `177 passed in 1.70s` | `green-pytest.txt` |
| `python -m pytest test_decision_wire_store.py test_decision_roots_locks.py -q` (repeat) | 0 | `118 passed in 1.55s` | `green-pytest-repeat.txt` |
| `python -m pytest test_decision_wire_store.py test_decision_roots_locks.py test_decide_backends.py test_decision_wire_transport.py test_decide.py test_decision_dashboard_contracts.py test_decision_book.py test_decision_context.py test_common.py test_doctor_activation.py test_doctor_autopilot.py test_serve_doctor.py test_autopilot_stall.py -q` | 0 | `650 passed in 74.68s` | `regression-neighbours-pytest.txt` |

`test_decision_wire_transport.py` belongs to the parallel T03 worker: it was run
**read-only** and was not edited. All of its tests pass, i.e. this card's API
changes did not break the transport wiring.

Test inventory: `test_decision_wire_store.py` 54 -> 78, `test_decision_roots_locks.py`
27 -> 40; full names in `test-names.txt`.

## `npm run check` steps (repo root)

`npm run check` itself starts with `biome check --write .`, which rewrites
`packages/coding-agent/test/suite/mwoc-*.test.ts` - files outside this card's
write face (pre-existing 3 warnings / 2 infos at a100012f7). Following the
T01/T02 precedent, biome was run read-only and every remaining step was run
individually; full output in `npm-check-steps.txt`.

| step | exit |
|---|---|
| `npx biome check --error-on-warnings .` (read-only variant) | 1 (only the 5 pre-existing mwoc findings; `biome-readonly-check.txt`) |
| `npm run check:pinned-deps` | 0 |
| `npm run check:ts-imports` | 0 |
| `npm run check:shrinkwrap` | 0 |
| `npm run check:install-lock:coding-agent` | 0 |
| `npx tsgo --noEmit` | 0 |
| `npm run check:browser-smoke` | 0 |

`npx biome check ... <the four Python files>` reports `Checked 0 files`: biome
ignores Python, so no formatter can touch this card's files
(`biome-readonly-check-mine.txt`).

## Spy metrics (P1-2)

`mw_common.acquire_lock` monkeypatched with a counting wrapper, `time.monotonic`
around each event:

| scenario | acquire calls | elapsed | assertions |
|---|---|---|---|
| same call, 2 events, foreign lock held | 1 (2nd event: 0) | 2nd < 0.05s | `error_class=circuit-open`, 1 warning, 2 error entries, `capture_status=failed` |
| scope unit (submission-start/end), foreign lock held | 1 | 2nd < 0.05s | 1 warning, both `failed` |
| single lock-timeout event | 1 | < 0.6s (250ms budget + slack) | foreign lock kept, sink not created |

## [VERIFY] facts (source = the tests/logs above)

- `T02b-long-secret`: persisted_secret_prefix_chars=0; min_prefix=1; full-suffix
  scan over the whole stored text; `boundary_scrubbed=true` on both cuts.
- `T02b-metadata`: secret occurrences in event JSON = 0 for lifecycle / attempt-end
  / submission / nested `policy`; redact-before-clip ordering asserted; without a
  redactor free text is omitted while enums/ids/numbers survive.
- `T02b-breaker`: second event acquire calls = 0 (was 1); elapsed < 0.05s.
- `T02b-isolation`: symlinked production sink/evidence refused, zero files created
  during validation, canonical `project_id` equal through a symlink.
- `T02b-owner`: ACCESS_DENIED -> unknown, GetExitCodeProcess failure -> unknown,
  ERROR_INVALID_PARAMETER -> dead, raising/None probe -> unknown,
  `_is_alive`/`check_pid` semantics unchanged.
- `T02b-p2`: shrunk line status = partial, unknown builder keys raise,
  orphan attempt-end leaves `attempts_started == 0`.
