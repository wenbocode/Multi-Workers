# T03 wire-transport - verify summary

All commands run from `H:/git/Multi-Workers/packages/multi-workers` unless noted.
Every log below is the complete stdout+stderr of that command (nothing tailed in
the saved files; the table quotes only the summary line).

| # | command | exit | result | log |
|---|---|---|---|---|
| 1 | `python -m pytest test_decision_wire_transport.py -q` (BEFORE implementation) | 1 | `14 failed, 2 passed` - first 16 behaviours RED | `red-pytest.txt` |
| 2 | `python -m pytest test_decision_wire_transport.py -q` | 0 | `23 passed` | `green-pytest.txt` |
| 3 | `python -m pytest test_decision_wire_transport.py test_decide_backends.py test_decide.py -q` (card acceptance command) | 0 | `174 passed in 11.09s` | `green-pytest-acceptance.txt` |
| 4 | repeat of #2 (timing-flake check) | 0 | `23 passed in 10.63s` | `green-pytest-repeat.txt` |
| 5 | `python -m pytest test_decision_wire_transport.py -q --collect-only` | 0 | 23 test ids | `test-names.txt` |
| 6 | mutant check: `_begin_attempt` capture disabled | 1 | `16 failed, 7 passed` (test file is not self-fulfilling) | `mutant-check-1-capture-disabled.txt` |
| 7 | mutant check: credential-redactor injection disabled | 1 | `1 failed, 20 passed` (targeted test only) | `mutant-check-2-no-redactor-injection.txt` |
| 8 | `python -m pytest test_decide_cli.py test_decide_run_authority.py test_decide_policy.py test_decide_sign_auto.py test_decide_report.py -q` (decide consumers, own files) | 0 | `126 passed` | `regression-decide-consumers.txt` |
| 9 | `python -m pytest test_decision_wire_store.py test_decision_roots_locks.py test_decide_cli.py test_decide_run_authority.py test_decide_policy.py -q` | 1 | `4 failed, 158 passed` - all 4 in `test_decision_wire_store.py`, which another session rewrote at 12:25 (30225 -> 51128 bytes) during this run | `regression-neighbours-pytest.txt` |
| 10 | `python -m pytest test_decision_roots_locks.py test_decide_cli.py test_decide_run_authority.py test_decide_policy.py test_decide_sign_auto.py test_dispatch_decide_prepare.py -q` | 1 | `13 failed, 160 passed` - 12 new `test_decision_roots_locks.py` tests (file 14367 -> 19716 bytes at 12:25:16) + 1 stale T04 registry test | `regression-neighbours-no-t02.txt` |
| 11 | `npx biome check --error-on-warnings .` (repo root, read-only) | 1 | 3 warnings + 2 infos, all pre-existing `packages/coding-agent/test/suite/mwoc-*.test.ts` | `biome-readonly-check.txt` |
| 12 | `npm run check:pinned-deps` (repo root) | 0 | ok | `npm-check-pinned-deps.txt` |
| 13 | `npm run check:ts-imports` | 0 | ok | `npm-check-ts-imports.txt` |
| 14 | `npm run check:shrinkwrap` | 0 | ok | `npm-check-shrinkwrap.txt` |
| 15 | `npm run check:install-lock:coding-agent` | 0 | ok | `npm-check-install-lock.txt` |
| 16 | `npx tsgo --noEmit` | 0 | ok | `npm-check-tsgo.txt` |
| 17 | `npm run check:browser-smoke` | 0 | ok | `npm-check-browser-smoke.txt` |

`npm run check` itself was NOT run as one command: its first step is
`biome check --write --error-on-warnings .`, which rewrites the pre-existing
`mwoc-*.test.ts` diagnostics (outside this card's write face). Steps 11-17 are
the same script minus `--write`, with full output saved. No tailing, no
`py_compile` substitute for behaviour assertions.

## External failures (not this card's write face)

- `test_decision_wire_store.py` (T02 file) was rewritten by another session at
  2026-10-22 12:25 (sha256 prefix 84dec693570b6171, 78 tests); its new tests
  target store behaviours not yet in `decision_wire.py`, so 4 (then 21) fail.
- `test_decision_roots_locks.py` (T01 file) grew to 19716 bytes at 12:25:16 with
  12 new `mw_common` tests that are RED until that owner lands the API.
- `test_dispatch_decide_prepare.py::test_dp_without_required_state_fields_is_refused`
  is stale against the T04 registry required-field change (`decision_points.py`
  updated 12:10 by the T04 owner).
- None of these failing files import `decision.py` / `decision_backends.py`
  (`test_decision_roots_locks.py`: `mw_common`; `test_decision_wire_store.py`:
  `decision_wire` + `mw_common`; `test_dispatch_decide_prepare.py`:
  `autopilot.dispatch` -> `decision_book`, unchanged by this card).
