# T05m evidence logs — what they contain

- Runs were made with `HOME`/`USERPROFILE` pointed at a throw-away directory
  (`$env:TEMP\t05m-home`), the credential-shaped env set removed, and
  `decision_backends._auth_json_path` patched to a tmp file (in the new test
  file by the autouse `auth_json` fixture, in `measure_bare_scope.py` before the
  first read). No real `~/.pi/agent/auth.json` and no real credential is read by
  any run in this directory.
- The only credentials involved are fabricated fixtures
  (`timi-bare-sent-a-…`, `timi-bare-legacy-b-…`, `timi-bare-rotated-c-…`,
  `timi-rotate-a/b-…` from the T05i file). **They are NOT masked in
  `logs/red-*.log`**: pytest quotes them inside assertion messages
  (`assert b'timi-bare-legacy-b-…' not in b'{"schema_version":1,…`), which is
  exactly the evidence for the RED state. Nothing here is claimed to be masked;
  no real credential value appears in these logs.
- `logs/red-01.log`: first RED attempt (new tests, baseline production code).
  Assertion order was then adjusted so the leak assertions run before the
  discovery-count assertions — `red-01` is kept for traceability, `red-02`/
  `red-03` are the reported RED rounds.
- `logs/measure-baseline.json` is produced by
  `workers/dd-bare-scope-known-set/measure_bare_scope.py <baseline/modules>`
  (identical script, pre-change `decision.py`, verified sha256 `9de7683c…`);
  `logs/measure-final.json` by the same script against the final tree.
- `baseline/modules/` is the throw-away import root used for that baseline
  measurement (copies of the unchanged sibling modules + the pre-change
  `decision.py` + the final test file used as its harness, sha256 `1216ec45…`).
- `logs/check-biome-readonly.log`: `npx biome check --error-on-warnings .`
  (read-only, no `--write`). The failure is the pre-existing
  `packages/coding-agent/test/suite/mwoc-*.test.ts` baseline (3 warnings +
  2 infos), unrelated to this Python-only card. The full `npm run check`
  (biome `--write`, `tsgo`, `browser-smoke`) was **not** run and is not
  equivalent.
