# T04 evidence: RED → GREEN

Card: `.agenticdoc/mw-decision-dashboard/tasks/T04-dp-contracts.md`
Key: mw-decision-dashboard (AC-009 / AC-011, VC-009)

## 1. RED (before the implementation)

cwd `packages/multi-workers`, new behavioural suite written first:

```
python -m pytest test_decision_dashboard_contracts.py -q
→ 110 failed, 9 passed in 1.47s
```

Representative RED assertions (recorded verbatim from that run):

```
E  AssertionError: dp4-failure-handling: no required_state_fields
E  assert ()
test_decision_dashboard_contracts.py:355: AssertionError

E  AttributeError: module 'decision_points' has no attribute 'OPTIONAL_STATE_FIELDS'.
E     Did you mean: 'OPTIONAL_STATE_PATHS'?
test_decision_dashboard_contracts.py:365
```

The 9 tests that already passed were the preserved-dp (dp1/dp2/dp3/dp25) and
"scaffold is not sendable" assertions, i.e. behaviour that existed before T04.

## 2. GREEN

cwd `packages/multi-workers` (card acceptance command):

```
python -m pytest test_decision_dashboard_contracts.py test_decide_registry_contract.py \
  test_decide_registry_export.py test_decide_registry_ts_lock.py \
  test_decision_points.py test_decision_book.py -q
→ 44 failed, 351 passed in 15.12s      (full log: pytest-acceptance.txt)
```

All 44 remaining failures are the two blocked foreign writes (see
`blocked-dp19-foreign-write.md`); nothing else fails:

* 43 × `test_decide_registry_contract.py` offline probe
  (`mw._DP_VERIFY_STATE_VALUES` has no value for the new business paths →
  `unusable config: … no probe value for required state path 'failure.kind'`),
* 1 × `test_decision_book.py::test_decide_book_template_is_book_new_output`
  (the shipped `decide_book_template.json` must be regenerated after dp6 gained
  its business fields).

New suite alone: `119 passed` (`pytest -q test_decision_dashboard_contracts.py`).

## 3. [VERIFY] VC-009 metrics — real source

`[VERIFY] VC-009: dp_count=25 identity_only_passes=0 bad_type_passes=0 mirror_drift=0`

| metric | source (test node id, all passing) |
|---|---|
| `dp_count=25` | `test_decision_dashboard_contracts.py::test_all_25_registered_dps_have_a_business_contract` |
| `identity_only_passes=0` | `…::test_identity_only_state_is_refused_with_zero_send[dp4..dp24]` (21 params, each asserts `input-incomplete` + `backend.calls == []`); mirrored at book level by `test_decision_book.py::test_check_book_rejects_identity_only_state_for_a_typed_dp` |
| `bad_type_passes=0` | `…::test_unknown_business_key_is_refused`, `…::test_wrong_array_element_type_is_refused`, `…::test_illegal_enum_value_is_refused`, `…::test_over_limit_array_is_refused`, `…::test_over_long_element_and_string_are_refused`, `…::test_negative_count_is_refused_but_signed_delta_is_not`, `…::test_cross_field_facts_are_validated`, and `…::test_invalid_business_book_sends_nothing_via_cli` (real `mw decide run --book` gate, rc=2, zero HTTP) |
| `mirror_drift=0` | `test_decide_registry_ts_lock.py::test_generated_registry_matches_a_fresh_render` + `::test_generator_check_mode_is_clean`; `test_decide_registry_export.py::test_export_is_byte_identical_to_a_regeneration` |
| `legal fields still send` | `…::test_a_legally_filled_state_still_reaches_the_transport[all 25]` (25 params) |
| `full book passes` | `…::test_a_fully_filled_book_passes_check_book[all 25]` (25 params) |
| `dp17 17AC / 128 cap` | `…::test_dp17_covers_17_acs_and_uses_the_wide_array_cap` |
| `signed delta` | `…::test_dp23_delta_bytes_is_a_signed_integer` |
| `budget independent` | `…::test_total_budget_stays_independent_of_the_field_limits` (128 legal 100-byte AC ids → `input-oversize`, zero HTTP) |
| `dp2 optional closed set` | `…::test_dp2_optional_progress_fields_are_a_declared_closed_set`, `…::test_optional_fields_are_legal_and_need_no_evidence` |
| `gate enum authority` | `…::test_dp15_gate_kind_enum_is_the_gate_authority` (`== autopilot.gates.GATE_KINDS`) |
| `preserved dps` | `…::test_preserved_dps_keep_their_frozen_required_tuples` |

Verbose log of the metric-bearing tests: `pytest-vc009-metrics.txt`
(`82 passed, 37 deselected`).

## 4. npm run check / tsgo (cwd repo root)

```
npm run check                → exit 1   (npm-run-check.txt, full stdout+stderr)
  biome: "Checked 1194 files … No fixes applied. Found 3 warnings. Found 2 infos."
  the 4 diagnostics are all in files this card did not touch:
    packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts:45  noUnusedImports
    packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts:606 useOptionalChain
    packages/coding-agent/test/suite/mwoc-w2-contract-judgment.test.ts:130 useTemplate
    packages/coding-agent/test/suite/mwoc-w3-ledger-extractor.test.ts:216 useOptionalChain
  (biome --error-on-warnings aborts the && chain before tsgo)
node_modules/.bin/tsgo --noEmit        → exit 0   (tsgo-noemit.txt, empty)
npm run check:ts-imports               → exit 0   (npm-check-ts-imports.txt)
npm run check:browser-smoke            → exit 0   (npm-check-browser-smoke.txt)
```

The generated TS module was made formatter-stable (`lineWidth`/`indentWidth`
read from `biome.json`), so `biome check --write` no longer rewrites it; the
first `npm run check` of this session did rewrite it, which is why
`test_decide_registry_ts_lock.py` now also guards the formatter shape.
