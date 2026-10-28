# T02c metadata key safety - verify summary

All commands run on Windows (PowerShell 5.1, Python 3.14.3). Every log in this
directory is the complete stdout+stderr of that command (no tailing), plus the
recorded `exit=` line. No external network, no paid model, no service start/stop,
no build, no commit.

| # | command | cwd | exit | result | log |
|---|---|---|---|---|---|
| 1 | `python -m pytest test_decision_wire_store.py test_decision_wire_transport.py -q` (BEFORE the fix) | `packages/multi-workers` | 1 | `12 failed, 100 passed in 13.14s` | `red-pytest.txt` |
| 2 | `python mutant-revert-keys.py` (key policy reverted in a `%TEMP%` copy only) | repo root | 1 | `13 failed, 100 deselected in 1.52s` | `mutant-check-keys-reverted.txt` |
| 3 | `python -m pytest test_decision_wire_store.py test_decision_roots_locks.py test_decision_wire_transport.py test_decide_backends.py test_decide.py -q` (card acceptance, final) | `packages/multi-workers` | 0 | `304 passed in 13.69s` | `green-pytest-acceptance.txt` |
| 4 | `python -m pytest test_decision_wire_store.py test_decision_wire_transport.py -q` (repeat) | `packages/multi-workers` | 0 | `113 passed in 13.00s` | `green-pytest-repeat.txt` |
| 5 | `python -m pytest test_decision_wire_transport.py -q --collect-only` | `packages/multi-workers` | 0 | `25 tests collected` | `test-names.txt` |
| 6 | `npx tsgo --noEmit` | repo root | 0 | no output | `tsgo-noemit.txt` |
| 7 | `npm run check:pinned-deps` / `check:ts-imports` / `check:shrinkwrap` / `check:install-lock:coding-agent` / `check:browser-smoke` | repo root | 0 / 0 / 0 / 0 / 0 | ok | `npm-check-steps.txt` |
| 8 | `npx biome check --error-on-warnings .` (read-only) | repo root | 1 | `Checked 1194 files`; 3 warnings + 2 infos, all pre-existing `packages/coding-agent/test/suite/mwoc-*.test.ts` (same baseline as T01/T02/T02b/T03) | `npm-check-steps.txt` |

`npm run check` as one command was NOT run: its first step is
`biome check --write .`, which rewrites `packages/coding-agent/test/suite/mwoc-*.test.ts`
(outside this card's write face). Steps 7-8 are the same script minus `--write`;
that is explicitly **not** equivalent to a full `npm run check`.

## Test inventory

- `test_decision_wire_store.py`: 88 tests (was 78; +10 N-1 metadata-key tests, plus one
  old assertion strengthened from `usage["model"] is None` to `"model" not in usage`).
- `test_decision_wire_transport.py`: 25 tests (was 23; only the 2 real-HTTP metadata-key
  tests were added, no old assertion was removed or weakened).

## [VERIFY] facts (source = the logs above)

- `T02c-metadata-key`: key occurrences of the credential in persisted ledger bytes = 0
  for usage keys, nested policy keys, keys inside lists, and at the real HTTP boundary;
  both with a credential redactor and with none.
- `T02c-collision`: two keys sanitizing to the same name -> both entries absent; a
  sanitized key landing on `input_tokens` -> the genuine `input_tokens` value survives
  (no overwrite, `fabricated_usage=0`).
- `T02c-noredactor`: unknown usage/policy keys are absent (not null-valued), the four
  documented counters survive; the real response `text` stays `text_omitted=true`.
- `T02c-limits`: depth limit 8 unchanged under the key pass; a 20 KB key is clipped to
  `METADATA_KEY_LIMIT` and the row still fits a 2048-byte line cap with the token
  counts intact.
- `T02c-join`: `project_id`/`decision_id`/`call_id`/`submission_id`/`key`/`task_key`
  unchanged while a metadata key is redacted.

## Evidence corrections (N-2)

`evidence-corrections.md` in this directory: T03 = 23 tests (not 33); the archived 650
log says `74.80s` (not 74.68s); T02b's `npx tsgo --noEmit` exit is not archived in
`T02b-foundation-fixes/npm-check-steps.txt`, so it is not a reviewable pass. The T02b
report/verify-summary were NOT modified (other worker's record); step 6 above is a new
time-point run and does not backfill T02b.
