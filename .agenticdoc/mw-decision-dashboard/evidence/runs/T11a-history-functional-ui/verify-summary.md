# T11a verify summary

UTC of the final runs: 2026-10-22T10:46Z..10:48Z.

## Acceptance command (task card)

```
cwd: packages/multi-workers
argv: python -m pytest test_decision_dashboard_assets.py test_decision_monitor.py test_decision_history.py -q
exit: 0
result: 112 passed, 1 skipped in 26.09s
log: green-acceptance.log
```

The skip is the suite's existing platform-conditioned skip (not a new test).

## New behaviour suite

```
cwd: packages/multi-workers
argv: python -m pytest test_decision_dashboard_assets.py -q
exit: 0
result: 9 passed in 7.11s
log: green-assets-only.log
```

9 tests: asset routes/no-inline-copy/no-token/no-model; static security shape;
history envelope filter marks (redacted + fail-closed); boot/list/pagination/
filter/detail DOM; inferred/unknown/missing renderer contract; bootstrap
failure; no-boot-code page.

## Adjacent dashboard suites (regression check)

```
cwd: packages/multi-workers
argv: python -m pytest test_decision_dashboard_contracts.py test_decision_observation.py -q
exit: 0
result: 249 passed in 1.31s
log: green-adjacent.log
```

## Root read-only substeps

```
cwd: repo root
argv: npx biome check --error-on-warnings .      (read-only, no --write)
exit: 1
result: Checked 1195 files. 3 warnings + 2 infos, all in
        packages/coding-agent/test/suite/mwoc-*.test.ts (files not in this
        worker's write face, changed by another session).
log: readonly-biome.log

argv: node scripts/check-pinned-deps.mjs          exit 0
argv: node scripts/check-ts-relative-imports.mjs  exit 0
```

`npm run check` itself uses `biome check --write` and was not executed (it
would rewrite other sessions' files); a full check was therefore NOT run, and
this report does not claim one.

## DOM harness invocation (per scenario)

```
cwd:  <pytest tmp_path>/dom
argv: node <pytest tmp_path>/dom/dom_harness.cjs \
        <repo>/packages/multi-workers/decision_dashboard.html \
        <repo>/packages/multi-workers/decision_dashboard.js \
        <pytest tmp_path>/dom/scenario.json
exit: asserted 0 by _run_dom (node prints one JSON line: ok=true + snapshots)
```

The harness itself is embedded in `test_decision_dashboard_assets.py` and the
scenario JSON only carries the real HTTP payloads captured in the same test.

## Runtimes

- Node v24.19.0 (DOM harness; no npm install, no new dependency)
- Python 3.14.3
- node-version.txt

## File hashes (sha256, bytes)

See hashes.txt. Summary:

```
c6e8e11f... 98610  packages/multi-workers/decision_monitor.py
1e268500...  4275  packages/multi-workers/decision_dashboard.html
5cbac255... 41792  packages/multi-workers/decision_dashboard.js
540497bd...  3568  packages/multi-workers/decision_dashboard.css
e2360f82... 42456  packages/multi-workers/test_decision_dashboard_assets.py
```

## Write-face check

`git status --porcelain` shows only the five paths above as new/untracked in
this write face (`decision_monitor.py` is an untracked new file from T10 in this
worktree). No history/provider/decision/points/TS/dependency/dist file touched.
