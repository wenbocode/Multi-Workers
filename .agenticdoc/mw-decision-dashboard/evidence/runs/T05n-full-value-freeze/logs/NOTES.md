# T05n evidence notes - what these logs contain

- Every run used `HOME`/`USERPROFILE` pointed into the pytest `tmp_path`, the
  whole credential-shaped env set removed (every name ending in
  `_API_KEY|_TOKEN|_KEY|_SECRET|_PASSWORD`), and
  `decision_backends._auth_json_path` patched to a tmp file *before* the first
  read. The autouse fixture asserts the redirect and that no credential-shaped
  env name survived; the discovery spy aborts if the resolved auth path is not
  the tmp one. No real `~/.pi/agent/auth.json` and no real credential is read by
  any run in this directory.
- The only credentials involved are fabricated fixtures
  (`t05n-sent-a-...`, `t05n-env-old-b-...`, `t05n-env-new-c-...`,
  `t05n-cfg-old-b-...`, `t05n-cfg-new-c-...`). They are **NOT masked** in
  `logs/red-0*.log`: pytest quotes them verbatim in the failing assertion
  (`assert 't05n-env-old-b-...' not in ...`, `"redactions":0`), and that quote is
  exactly the RED evidence. Nothing here is claimed to be masked; no real
  credential value appears in these logs.
- `logs/red-01.log`: first RED round (final test bytes x baseline
  `decision.py`/`decision_points.py`). Assertion order was then adjusted so the
  leak/coverage assertions run before the frozen-API assertion; `red-01` is kept
  for traceability, `red-02` is the reported authoritative RED (7 failed /
  1 passed, all failures on the vulnerable faces).
- `baseline/modules/` is the throw-away import root for the RED round and the
  baseline single-test reproduction: copies of the pre-change sibling modules
  (`decision.py 583f0815...`, `decision_points.py f5e028b7...`) plus the final
  test file used as its harness.
- `logs/adjacent-suites.log` / `adjacent-suites-final.log`: all
  `test_decision_*.py` + `test_decide_*.py` + `test_dispatch_decide_prepare.py`.
  The single failure (`test_dp_without_required_state_fields_is_refused`) is
  pre-existing: `logs/adjacent-baseline-single.log` reproduces it identically
  against `baseline/modules/`, so it is not a regression of this card.
- `logs/check-biome-readonly.log`: `npx biome check --error-on-warnings .`
  (read-only, no `--write`). exit=1 from the pre-existing
  `packages/coding-agent/test/suite/mwoc-*.test.ts` baseline (3 warnings + 2
  infos), unrelated to this Python-only card. The full `npm run check` (biome
  `--write`, `tsgo`, `browser-smoke`) was **not** run and is not equivalent.
- No `build`, no full-package pytest, no real timi/Jev/browser/service call, no
  commit. Only 127.0.0.1 loopback HTTP servers.
