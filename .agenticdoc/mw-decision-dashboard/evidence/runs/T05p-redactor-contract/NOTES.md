# T05p evidence notes - what these logs contain

## Isolation (every run)

- Wrapper `workers/dd-redactor-contract/run_round.py` removes every
  credential-shaped child-env name (`*_API_KEY|_TOKEN|_KEY|_SECRET|_PASSWORD`
  and `TIMI_*`; the two present on this host), points `HOME`/`USERPROFILE` at a
  throw-away tmp dir, drops `PYTHONPATH`, and records the removed names in each
  log header.
- The new test file is hermetic per test: an autouse fixture removes the whole
  credential-shaped env set, points `HOME`/`USERPROFILE` into `tmp_path`,
  patches `decision_backends._auth_json_path` to a tmp file *before* any read,
  and the discovery spy aborts if the path a discovery would read is not inside
  that tmp home.
- No real `~/.pi/agent/auth.json`, no real credential, no Jev/paid model, no
  browser, no service. The only sockets are stdlib `http.server` instances bound
  to `127.0.0.1:0`.
- Fixture values are fabricated (`t05p-sent-a-...`, `t05p-nonebase-p-...`,
  `t05p-legacy-b-...`, `t05p-env-ambient-d-...`). They are NOT masked: pytest
  quotes them verbatim in failing assertions and that quote *is* the RED
  evidence. No real credential value appears anywhere.

## RED rounds

- `logs/red-01-redactor-contract.log` (UTC 10:17:58-10:18:02, live pre-change
  source `decision.py c227a64b...`, first-draft test bytes `8d3fe37f...`):
  4 failed / 1 passed. The extra failure was a test-side mistake (the first
  metadata assertion read the 500 attempt's `usage`, which is legitimately
  `null`); the test bytes were corrected, no source was touched.
- `logs/red-02-redactor-contract.log` (UTC 10:18:37-10:18:40, same pre-change source
  `c227a64b...`, final test bytes `138a4a04...`): **3 failed / 2 passed**. This
  is the authoritative wall-clock RED, and it ran before the implementation
  edit. The three failures are exactly the new contract points:
  1. `known_credential_values` did not raise `TypeError` for a None-base
     snapshot (it silently returned the legacy live set);
  2. a client-only caller-owned production filter covering only the sent value
     still sent and stored the legacy timi leg RAW (the assertion message
     records `stored_legacy=True, stored_bytes=5024` - the real baseline leak);
  3. `credential_redactor`/`known_secret_redactor` derived from a None-base
     snapshot were a live redactor instead of a safe omit / fail-closed gate.
  The two passing tests were the preserved-policy test and the complete-filter
  retry test (they assert behaviour that already held and must keep holding).

## GREEN / acceptance

- `logs/green-01-redactor-contract.log`: the new file alone, `5 passed`, exit 0,
  `decision.py 106ebaef...` / test `138a4a04...` identical before and after.
- `logs/t05p-r1.log` / `logs/t05p-r2.log`: the card's exact eight-file argv, two
  independent rounds, `78 passed` each (36.89s / 36.92s), exit 0, complete
  argv/cwd/UTC/DEPS before-after/isolation headers. `t05p-r2` ran in a fresh
  process with a different tmp HOME.
- `logs/adjacent-suites.log`: all 34 `test_decision_*.py` + `test_decide_*.py`
  files (the 33 from T05o plus the new file) -> `1301 passed, 1 skipped`
  (79.92s), exit 0. (An earlier attempt died on a PowerShell argv-joining
  mistake before pytest ran; kept as
  `logs/adjacent-suites-attempt1-argv-error.log`, `[EXIT] 4`, no test ran.)

## Discovery-count facts (frozen, not live)

- None-base factory test: no discovery at all (the refusal is decided from the
  snapshot, never from cfg/env).
- Client-only caller-owned *incomplete* filter: exactly one legacy discovery
  (the coverage check must know the complete set), zero POST, zero rows.
  Retries never happen (refused before the attempt loop).
- Client-only caller-owned *complete* filter: exactly one discovery, paid by the
  caller's own `snapshot.known_superset()`; the client's verification reuses the
  memo, so two POSTs (500 then 200) still cost one freeze.
- `None` factory result handed to a production scope: the client injects from
  its own factory snapshot - one discovery, and the 500 failure output plus the
  arbitrary `usage` metadata key/value are redacted.

## Root read-only checks (no `--write`, no full `npm run check`)

- `logs/check-biome-readonly.log`: `npx biome check --error-on-warnings .`,
  exit 1 from the pre-existing `packages/coding-agent/test/suite/mwoc-*.test.ts`
  warnings/infos (3 warnings, 2 infos, 1194 files checked) - the same baseline
  T05o recorded, unrelated to this Python-only card.
- `check-pinned-deps`, `check-ts-imports`, `check-shrinkwrap`,
  `check-install-lock-coding-agent`: all exit 0.
- The full `npm run check` (biome `--write`, tsgo, browser smoke) was NOT run
  and is not equivalent. No build, no commit, no full-package pytest, no real
  model.

## Hash / diff artifacts

- `hashes/baseline.sha256`: pre-change `decision.py c227a64b...` (also archived
  byte-identical in `baseline/decision.py`).
- `hashes/final.sha256`: post-change `decision.py 106ebaef...` and the new test
  `138a4a04...`.
- `hashes/current-deps.sha256` vs the red-02 `[DEPS BEFORE]` block: the only
  differing entry is `decision.py`; every other dependency/test listed is
  byte-identical (see `hashes/out-of-write-face-unchanged.txt`).
- `diff-decision.patch`: the complete owner diff, baseline -> final (243 lines,
  no fixture value, no hardcoded key).
- `hashes/evidence-logs.sha256`: sha256 of every log in this run dir.
