# T11a RED evidence (real runs)

cwd: `packages/multi-workers` (all runs). UTC: 2026-10-22T10:36Z..10:46Z.
Command: `python -m pytest test_decision_dashboard_assets.py -q`.

## RED-1: pre-implementation (assets and wiring absent)

```
7 failed, 1 passed in 0.45s
```

Root causes (observed):
- `AttributeError: module 'decision_monitor' has no attribute 'ASSET_DIR'`
  for the asset-route, no-inline-copy, history-marks and three DOM tests: the
  monitor only served the placeholder inline page and did not forward
  `filters_withheld` / `filters_basis`.
- the old placeholder page had no two-tab skeleton, no JS, no CSS file.

## RED-2: first GREEN attempt after monitor wiring + new assets

```
3 failed, 5 passed
```

Observed root causes:
- `assert 'document.write' not in js` — the JS header comment itself named the
  forbidden construct; removed from the prose (the code never had it).
- `decide_archive.DecisionArchiveError: available decision requires answer` —
  the test fixture seeded one archive row without an answer; fixture fixed.

## RED-3: real T07/T02 API shape mismatches

```
2 failed, 6 passed
```

Observed root causes:
- `TypeError: record_attempt_start() missing 1 required keyword-only argument:
  'url_path'` (real writer signature) — fixture fixed.
- the two decisions tests reached the same fixture error.

## RED-4: pagination assertion vs. the actual request

```
1 failed, 7 passed
```

Observed root cause: the page requested `limit=50` (documented default) while
the mock payload had been captured with `limit=1`. Fixed by seeding 55 real
records and capturing the genuine default page + `offset=50` page over HTTP,
so pagination is exercised with the shipped default.

## RED-5: detail assertion vs. real field names

```
1 failed
```

Observed root causes (two iterations):
- the filter-output policy is an English `filters_basis` statement; the test
  asserted the Chinese word 依据. Test now asserts 筛选输出策略 + the policy
  name (the policy text itself is rendered verbatim).
- per-attempt `usage` in the fold is a bare counter map (no `recorded` flag);
  the renderer treated it as "未记录". The renderer now accepts a bare counter
  map as recorded (counters only) and keeps the record-level
  `usage.missing` list as the "未补 0" statement.

## GREEN (see green-acceptance.log)

```
112 passed, 1 skipped in 25.63s
exit=0
```
