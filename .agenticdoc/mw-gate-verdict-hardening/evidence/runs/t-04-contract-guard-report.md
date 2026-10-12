# T-04 report: G3 `authorizes` field + `contract_guard` module

- Key: `mw-gate-verdict-hardening` (phase=EXECUTE)
- Card: `.agenticdoc/mw-gate-verdict-hardening/tasks/T-04-contract-guard.md`
- Worker task: `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-t04-contract-guard/task.md`
- Baseline HEAD: `776b82d7f`
- Baseline working tree for the write surface: `git status --porcelain -- packages/multi-workers/autopilot/gates.py packages/multi-workers/autopilot/contract_guard.py` -> empty (both clean at start)
- AC: AC-009, AC-011, AC-013 · VC: VC-012, VC-015
- Result: **PASS**, all three `[VERIFY]` commands green; three non-hollow counterfactuals each turn their named test red.

## 1. Deliverables

### 1.1 `packages/multi-workers/autopilot/gates.py` (appended only, nothing reordered)

| What | Coordinate |
|---|---|
| Docstring: `authorizes` contract field + closed set documented | `gates.py:36-43` |
| `"authorizes"` added to `_JSON_LIST_FIELDS` (single-line JSON array) | `gates.py:171` |
| `AUTHORIZES_ACTIONS = frozenset({"retry", "contract-change"})` (closed set; `install` excluded) | `gates.py:180` |
| `Gate.authorizes: list[str] | None = None` dataclass field (append-only) | `gates.py:263` |
| Parse-surface membership check accepts `_JSON_LIST_FIELDS` names (keeps the frozen 40-name order) | `gates.py:504-508` |
| Member/type validation at parse time, fail-closed (unknown member => `GateFormatError`) | `gates.py:659-676` |
| Wiring into the constructed `Gate` | `gates.py:717` |

Untouched by construction: `_REQUIRED_FIELDS` stays the exact 6-field frozenset (import-time assert at `gates.py:148-153` still holds); no schema v3; `create()`/`_gate_file_content` do **not** render `authorizes` (the 13-key create lock at `test_autopilot_gates.py:216-230` is intact). Empty array / absent field both mean "no authorization" (fail-closed).

### 1.2 `packages/multi-workers/autopilot/contract_guard.py` (new, pure module, root injected)

| Responsibility (card bullet) | Coordinate |
|---|---|
| AC row regex `^\|\s*(AC-\d{3})\s*\|\s*(.*?)\s*\|\s*$` + line scan | `contract_guard.py:70`, `parse_acs` `:86` |
| VC block regex (semantics of `.tmp/msc-gen-evidence-req.py:parse_vcs`, no path dependency) | `contract_guard.py:75-78`, `parse_vcs` `:102` |
| canonical sha (per-id `id + "\x1f" + text`; stable sorted family digest) | `:121` `canonical_sha`, `:133` `family_sha`, `:157` `extract_contract` |
| Freeze sidecar `<key>/evidence/contract-freeze.json` read/write (design D-015 shape) | `:174` `freeze_path`, `:183` `build_freeze`, `:203` `read_freeze`, `:232` `write_freeze`, `:247` `freeze_contract` |
| Change detection: current text vs freeze => added/removed/changed id sets | `:265` `ContractDiff`, `:292` `diff_contract` |
| Authorization lookup: `status=="approved"` ∧ `authorizes ∋ contract-change` ∧ `gate.key==key`; no kind binding; never reads `note`/`answered_by` | `:322` `gate_authorizes_contract_change`, `:334` `authorizing_gates`, `:350` `find_authorizing_gate` |
| Composed verdict for T-10/T-11 (`ok`, `no_anchor`, `changed_ids`, `carrier`, `reasons`) | `:361` `ContractVerdict`, `:384` `evaluate` |

Contract compliance:
- No `subject_sha256`, no `git diff` (grep: `contract_guard.py` has 0 hits for either).
- No `import conductor` (guard test `test_contract_guard_never_imports_conductor`).
- No module-level file access; all IO through injected `key_dir`/`gates_dir`.
- Missing/corrupt freeze sidecar => `read_freeze` returns `None` and `evaluate` returns `ok=True, no_anchor=True, reasons=("no-freeze",)` - no exception (zero disturbance decided by T-10/T-11).

### 1.3 `packages/multi-workers/test_autopilot_contract_guard.py` (new, 15 tests)

Covers VC-012 (closed set / array / fail-closed), VC-015 (prose note is not an authorization source), AC-013 (frozen 40-name order + 6 required fields + create() renders 13 keys and no `authorizes`), AC/VC parsing, canonical sha stability, freeze round-trip + unusable-sidecar handling, diff, and the `evaluate` verdict paths (no-anchor / refused / authorized-with-carrier).

## 2. `[VERIFY]` (commands verbatim, real output)

```
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gates.py test_autopilot_gate_schema_v2.py -q -p no:randomly
.................................................................        [100%]
65 passed in 0.21s
```

```
> cd packages/multi-workers && python -X utf8 -c "from autopilot import gates, contract_guard; assert 'authorizes' in gates._JSON_LIST_FIELDS; assert len(gates._REQUIRED_FIELDS)==6; print('ok')"
ok
```

```
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_contract_guard.py -q -p no:randomly
...............                                                          [100%]
15 passed in 0.09s
```

The `[VERIFY]` markers printed by the test run (`-s`):

```
[VERIFY] VC-012: closed_set=2 listed_only=true
[VERIFY] VC-015: authorized=false
[VERIFY] VC-016: required_fields=6 create_keys=13 authorizes_rendered=false
[VERIFY] VC-012: freeze_schema=1 spec_ids=3 design_ids=2
[VERIFY] VC-014: refused=true changed_ids=1 classified=true
```

Additional gate-touching regression files (not required by the card, run to bound blast radius):

```
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_consumption.py test_autopilot_gate_guards.py test_autopilot_xkey_registration.py test_autopilot_pending_review.py test_autopilot_evidence.py -q -p no:randomly
89 passed in 5.00s
```

## 3. Non-hollow counterfactuals (actual red / green)

### CF-1: remove `authorizes` from `_JSON_LIST_FIELDS` => array value must fail to parse (VC-012 red)

Temporarily deleted the `"authorizes",` entry at `gates.py:171` and re-ran the card's test file:

```
E               autopilot.gates.GateFormatError: C:\...\test_evaluate_refuses_unauthor0\gates\gate-0001.md: unknown frontmatter field 'authorizes' (line 14)
=========================== short test summary info ===========================
FAILED test_autopilot_contract_guard.py::test_vc012_authorizes_is_closed_set_json_list
FAILED test_autopilot_contract_guard.py::test_vc012_array_value_requires_json_list_registration
FAILED test_autopilot_contract_guard.py::test_vc015_approval_requires_approved_machine_field_and_key
FAILED test_autopilot_contract_guard.py::test_evaluate_refuses_unauthorized_change_and_accepts_with_carrier
4 failed, 11 passed in 0.17s
```

Restored: green (15 passed). The array form is only accepted because the field is declared as a JSON-list field.

### CF-2: widen the closed set to any string => `install` / `whatever` accepted (VC-012 red)

Temporarily disabled the out-of-set rejection at `gates.py:670-675` (`out_of_set` computed but not raised):

```
>           with pytest.raises(gates.GateFormatError):
E           Failed: DID NOT RAISE <class 'autopilot.gates.GateFormatError'>
test_autopilot_contract_guard.py:117: Failed
=========================== short test summary info ===========================
FAILED test_autopilot_contract_guard.py::test_vc012_authorizes_is_closed_set_json_list
1 failed, 14 passed in 0.15s
```

Restored: green (15 passed).

### CF-3: let the lookup read `gate.note` prose => authorization lookup returns true (VC-015 red)

Temporarily made `gate_authorizes_contract_change` (`contract_guard.py:322`) return true for a `note` containing `contract-change`:

```
>       assert refused.ok is False
E       AssertionError: assert True is False
E        +  where True = ContractVerdict(ok=True, no_anchor=False, changed_ids=('AC-001',), carrier='gate-0002', reasons=('authorized',)).ok
=========================== short test summary info ===========================
FAILED test_autopilot_contract_guard.py::test_vc015_note_prose_is_not_an_authorization_source
FAILED test_autopilot_contract_guard.py::test_evaluate_refuses_unauthorized_change_and_accepts_with_carrier
2 failed in 0.15s
```

Restored: green (15 passed). The only recognized source is the machine field; a prose note can never become the carrier.

## 4. Deviation and coordination item (must-read for T-10/T-11/T-12)

**Design D-011/§2.1 and T-04 card's parenthetical say `authorizes` is appended to `FRONTMATTER_FIELDS` (index 40, 41 names).** That is not reachable inside this card's write surface:

- `test_autopilot_gates.py:224` asserts `len(gates.FRONTMATTER_FIELDS) == 40` and is run by this card's own `[VERIFY]` command 1.
- `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:206-235` locks Python `FRONTMATTER_FIELDS` item-for-item against TS `GATE_FRONTMATTER_FIELDS` **and** `toHaveLength(40)`; it is run by T-08 and T-12 `[VERIFY]` commands.
- No card in `tasks/T-*.md` owns updating those locks (T-14's count-lock list does not include them).

Resolution used here (satisfies the card's `[VERIFY]` and every existing lock): `authorizes` is declared only in `_JSON_LIST_FIELDS` (`gates.py:171`), and the parse-surface membership check accepts `_JSON_LIST_FIELDS` names (`gates.py:508`) so the field parses without growing the frozen 40-name order. `_REQUIRED_FIELDS` stays 6, `create()` still emits 13 keys.

**Handoff: the TS mirror must implement the same shape.** For a gate file materialized with `authorizes: [...]` (T-10) to be readable by the TS console, `status-model.ts` must:
1. add `"authorizes"` to `GATE_JSON_LIST_FIELDS` (`status-model.ts:742`),
2. change the unknown-field check (`status-model.ts:811-812`) to also accept `GATE_JSON_LIST_FIELDS` members,
3. add closed-set validation + `GateRecord.authorizes`.

Do **not** add `authorizes` to `GATE_FRONTMATTER_FIELDS`; that would break the 40-name parity lock (`autopilot-gate-presentation.test.ts:206-235`) that the `[VERIFY]` sets of T-08/T-12 also run. This is the only cross-card action left for AC-009/VC-012 to hold end-to-end; flagging it as R1 for the PM so T-12 does not silently skip or diverge.

## 5. Residual risks / notes

- `evaluate` reads `spec.md` / `design.md` from the injected `key_dir`; an unreadable/missing file reads as empty text, which makes every frozen id look removed => `ok=False` (fail-closed). A missing/corrupt **freeze** is the only "no anchor" case, per the card.
- `evaluate` prefers the caller `key`, then the key recorded in the freeze, then `key_dir.name`; T-10 should pass `key=` explicitly for clarity.
- `contract_guard.py` is the only new module; `conductor -> contract_guard` stays one-way, so `contract_guard.evaluate` can be imported by conductor without a cycle.
