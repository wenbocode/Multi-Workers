# T04 blocked item: dp19-foreign-write (two artifacts outside the declared write face)

Card write face: `decision_points.py`, `decision_book.py`, `scripts/gen_decide_registry_ts.py`,
`decide_registry.json`, `decide-registry.generated.ts`, the six test files, this worker dir,
`evidence/runs/T04-*`.

Adding the 25-DP typed contract makes two shipped artifacts stale. Both are consumed by
tests inside the card's own acceptance command, so the card cannot be "green" without them.

## Decision request (2026-10-22)

```
ask_decision dp=dp19-foreign-write trigger=dd-dp-contracts
→ {"available":false,"unavailable":"disabled","action":"blocked-ask-human","escalated_reason":"disabled"}
UNAVAILABLE(disabled): the gated action stays blocked; do not work around it.
Status: blocked on decision dp19-foreign-write.
```

No foreign file was written. The payloads are prepared here so a human/PM can apply them
(or grant the write face) after the ruling.

## 1. `packages/multi-workers/mw.py` — `_DP_VERIFY_STATE_VALUES`

Why: `mw._dp_verify_state()` raises `ValueError("no probe value for required state path …")`
for every required path missing from that table, so `mw decide dp verify` (and the
`test_decide_registry_contract.py` offline probe) reports `unusable config` for dp4..dp24.

Minimal change: insert the 82 entries from
`proposed-mw-probe-values.txt` immediately before the closing `}` of the dict. No logic,
signature or behaviour change; values are minimal legal facts (cross-field consistent:
`failure.attempt <= failure.limit`, `stage.tasks_done <= stage.tasks_total`,
`spec.ac_changed ⊆ spec.ac_ids`, `len(qg.checks_failed) <= qg.checks_total`).

Proof that this is exactly the blocker (in-memory patch of the imported module, no file
written): `proposed-foreign-writes-proof.txt`

```
probe_ok=25/25 failures=[]
template_matches_scaffold=True
```

## 2. `packages/multi-workers/decide_book_template.json`

Why: `test_decision_book.py::test_decide_book_template_is_book_new_output` requires the
shipped template to equal `decision_book.scaffold_book()` output for dp3 and dp6; dp6 now
carries its four `qg.*` business fields + evidence slots.

Minimal change: replace the file with `proposed-decide_book_template.json`
(byte-for-byte what the existing renderer produces, dp3 unchanged apart from CRLF/LF
normalisation: the file is written with LF and a trailing newline).

## What is *not* blocked and still needs a PM decision (reported, not edited)

1. `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`
   `REQUIRED_FIELDS_BY_DP` rows for `dp4`/`dp5`/`dp6`/`dp13` still name the pre-card
   vocabulary (`failure.test_name`, `closure`, …). `test_decide_registry_contract.py`
   freezes them (`TS_STALE_ROWS`) so a new one-sided drift is red; aligning them is
   TS-owner work (T09).
2. `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`
   `ASK_DECISION_ENFORCED_STATE_DP_IDS` lists only dp1/dp2/dp3/dp25.
   `test/suite/decision-tool.test.ts > ask_decision registry parity > pins the
   client-side required-field dp set` now fails (1 failed | 22 passed, see
   `vitest-decision-tool-downstream.txt`): the list must grow to all 25 ids.
3. `packages/multi-workers/autopilot/dispatch.py` treats "dp declares
   `required_state_fields`" as "dp is card-overridable"; after T04 that is all 25 dps.
   `test_dispatch_decide_prepare.py::test_dp_without_required_state_fields_is_refused`
   now fails (1 failed | 314 passed in the bounded decide-related suite, see
   `pytest-downstream-adjacent.txt`). This is a deliberate consequence of design §4.5,
   but the gate's intent ("only dps with a book can be dispatched") needs a PM ruling.
