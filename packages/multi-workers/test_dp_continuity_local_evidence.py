"""T03 — dedicated tests for decision_local_evidence.py (schema v1).

Scope: L1 isolation.  Tests use verbatim frozen T01 JSON fixtures, isolated
real files under ``tmp_path`` and an INJECTED fake ``HostEvidenceAdapter``.  No
real provider/DP/LLM, no product VC, no paid token.  Cross-language parity is
checked against the CURRENT frozen TS module (``shared/decision-handoff.ts``)
via Node strip-types import AND against verbatim frozen field lists; T02's
unfinished bytes are never imported.  A handwritten fixture is NEVER counted as
L2 product evidence.

Acceptance: ``python -m pytest -q test_dp_continuity_local_evidence.py``.
"""

from __future__ import annotations

import ctypes
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from dataclasses import replace

import pytest

import decision_local_evidence as m

# ── verbatim frozen JSON fixtures (T01-contract.md §4; pure parse examples) ──

SELECTION_JSON = r'''{
  "schema_version": 1,
  "kind": "local-selection",
  "origin": "local-decision",
  "source": "pm",
  "local_ref": "local:T01:1",
  "parent_decision_ref": { "kind": "dp", "decision_id": "dp-auto:2026-11-12T04:00:00Z" },
  "feedback_ref": "fb:20261112-1",
  "matter_ref": "matter:T01",
  "host_binding": {
    "role": "pm",
    "owner": "WENBOZHOU-PC5:13148",
    "claim_id": "claim:1",
    "key": "mw-pm-dp-continuity",
    "binding_version": "v3",
    "observed_at": "2026-11-12T12:30:00+08:00"
  },
  "matter_version": "v3",
  "material_digest": "sha256:material",
  "basis_digest": "sha256:basis",
  "selected_action": "continue",
  "selected_basis_id": "b1",
  "budget_ref": "budget:T01",
  "action_state": "planned",
  "business_completed": false,
  "result_consumer": "pm-orchestrator:ack",
  "created_at": "2026-11-12T12:30:00+08:00"
}'''

EXECUTION_JSON = r'''{
  "schema_version": 1,
  "kind": "local-execution",
  "origin": "local-decision",
  "source": "pm",
  "local_ref": "local:T01:1",
  "host_binding": {
    "role": "pm",
    "owner": "WENBOZHOU-PC5:13148",
    "claim_id": "claim:1",
    "key": "mw-pm-dp-continuity",
    "binding_version": "v3",
    "observed_at": "2026-11-12T12:30:00+08:00"
  },
  "action_ref": "tool_call:read:7",
  "result_ref": "tool_result:read:7",
  "executor": "pm-orchestrator",
  "target_digest": "sha256:target",
  "observed_effect": "two reads recorded",
  "effect_state": "known",
  "verified_by": "target-verifier:1",
  "budget_ref": "budget:T01",
  "created_at": "2026-11-12T12:30:00+08:00"
}'''

MATTER_BUDGET_JSON = r'''{
  "schema_version": 1,
  "budget_ref": "budget:T01",
  "matter_ref": "matter:T01",
  "parent_matter_ref": "matter:parent",
  "deadline": "2026-11-12T13:00:00+08:00",
  "max_steps": 3,
  "no_progress_limit": 2,
  "remaining_cost": 5,
  "steps_consumed": 1,
  "cost_consumed": 1,
  "no_progress_count": 0,
  "source_refs": ["tasks/T01-local-contract.md:timeout=90", "run.json:remaining"]
}'''

DP_REF = {"kind": "dp", "decision_id": "dp-auto:2026-11-12T04:00:00Z"}
LOCAL_REF = {"kind": "local", "local_ref": "local:T01:1"}

KEY = "mw-pm-dp-continuity"
PM_REF = "local:T01:1"
WORKER_TASK = "w1"
WORKER_RUN = "run1"

# Verbatim frozen closed sets / field lists from decision-handoff.ts (T01).  The
# SCHEMA_V1 parity test asserts the Python reader has not drifted a single byte.
FROZEN = {
    "id": "decision-handoff/v1",
    "schema_version": 1,
    "records": ["decision-feedback", "pm-disposition", "local-selection", "local-execution", "matter-budget"],
    "feedback_categories": ["answer", "advisory", "service-unavailable", "input-gap", "uncertain-answer", "binding-invalid", "integrity-error", "authority-required", "effect-unknown", "cancelled", "budget-exhausted", "exemption", "unclassified"],
    "effect_states": ["none", "known", "unknown"],
    "stop_scopes": ["none", "service-request", "worker-run", "matter", "pm-or-key", "user-global", "unknown"],
    "pm_disposition_kinds": ["self-decide", "collect-evidence", "reconcile", "replan", "await-worker", "await-external", "stopped", "resource-limited"],
    "pm_disposition_statuses": ["planned", "running", "observed", "superseded", "waiting", "stopped"],
    "local_sources": ["pm", "worker-local"],
    "forbidden_dp_fields": ["decision_id", "answers", "available", "business_decisions", "business_decision", "decision_lifecycle", "receipt", "request_ref", "model_called", "decision_ref"],
    "local_selection_fields": ["schema_version", "kind", "origin", "source", "local_ref", "parent_decision_ref", "feedback_ref", "matter_ref", "host_binding", "matter_version", "material_digest", "basis_digest", "selected_action", "selected_basis_id", "budget_ref", "action_state", "business_completed", "result_consumer", "created_at"],
    "local_execution_fields": ["schema_version", "kind", "origin", "source", "local_ref", "host_binding", "action_ref", "result_ref", "executor", "target_digest", "observed_effect", "effect_state", "verified_by", "budget_ref", "created_at"],
    "matter_budget_fields": ["schema_version", "budget_ref", "matter_ref", "parent_matter_ref", "deadline", "max_steps", "no_progress_limit", "remaining_cost", "steps_consumed", "cost_consumed", "no_progress_count", "source_refs"],
    "decision_ref_kinds": ["dp", "local"],
    "verification_scope": "shape-only",
    "host_source_verified": False,
}


# ── helpers ────────────────────────────────────────────────────────────────

def _sel_obj() -> dict:
    return json.loads(SELECTION_JSON)


def _exec_obj() -> dict:
    return json.loads(EXECUTION_JSON)


def _worker_sel_obj() -> dict:
    obj = _sel_obj()
    obj["source"] = "worker-local"
    hb = dict(obj["host_binding"])
    hb["role"] = "coding"
    hb["task_key"] = WORKER_TASK
    hb["run_id"] = WORKER_RUN
    obj["host_binding"] = hb
    return obj


def _parse_sel(obj: dict) -> m.LocalSelectionRecord:
    result = m.parse_local_selection_record(obj)
    assert result.ok and result.value is not None, result.issues
    return result.value


def _parse_exec(obj: dict) -> m.LocalExecutionRecord:
    result = m.parse_local_execution_record(obj)
    assert result.ok and result.value is not None, result.issues
    return result.value


def _live_budget(budget_ref: str = "budget:T01") -> dict:
    """A CURRENT, finite, non-exhausted budget from real card/run refs.  The
    frozen MATTER_BUDGET_JSON has a past deadline (it is a shape-only fixture);
    a real current budget must not be exhausted, so tests use a live deadline."""
    return {
        "schema_version": 1,
        "budget_ref": budget_ref,
        "matter_ref": "matter:T01",
        "parent_matter_ref": "matter:parent",
        "deadline": "2099-01-01T00:00:00+00:00",
        "max_steps": 5,
        "no_progress_limit": 3,
        "remaining_cost": 5,
        "steps_consumed": 1,
        "cost_consumed": 1,
        "no_progress_count": 0,
        "source_refs": ["tasks/T03:timeout=55", "run.json:remaining"],
    }


def _binding_from(hb: m.HostBinding, **kw) -> m.TrustedBinding:
    return m.TrustedBinding(
        authority=kw.get("authority", m.AUTHORITATIVE_BINDING_KIND),
        coordination_row_ref=kw.get("coordination_row_ref", "workers.parallel:row:7"),
        is_active=kw.get("is_active", True),
        active_row_count=kw.get("active_row_count", 1),
        role=hb.role, binding_version=hb.binding_version, observed_at=hb.observed_at,
        owner=hb.owner, claim_id=hb.claim_id, key=hb.key,
        task_key=hb.task_key, run_id=hb.run_id,
    )


def _ctx_from(sel: m.LocalSelectionRecord, **overrides) -> m.TrustedContext:
    parent = None
    if sel.parent_decision_ref is not None:
        parent = {"kind": "dp", "decision_id": sel.parent_decision_ref.decision_id}
    ctx = m.TrustedContext(
        binding=_binding_from(sel.host_binding),
        matter_ref=sel.matter_ref,
        matter_version=sel.matter_version,
        material_digest=sel.material_digest,
        basis_digest=sel.basis_digest,
        target_digest="sha256:target",
        budget=_live_budget(sel.budget_ref),
        parent_decision_ref=parent,
    )
    for key, value in overrides.items():
        ctx = replace(ctx, **{key: value})
    return ctx


def _evidence_for(rec: m.LocalExecutionRecord, **kw) -> m.ActionResultEvidence:
    return m.ActionResultEvidence(
        action_receipt_ref=kw.get("action_receipt_ref", rec.action_ref),
        result_receipt_ref=kw.get("result_receipt_ref", rec.result_ref),
        verifier_receipt_ref=kw.get("verifier_receipt_ref", rec.verified_by),
        observed_object_digest=kw.get("observed_object_digest", rec.target_digest),
        confirmed=kw.get("confirmed", True),
    )


class FakeAdapter(m.HostEvidenceAdapter):
    """Injected trusted-host boundary for L1 isolation tests.  NOT production
    wiring (that is T07/T08).  All facts here are explicit test data."""

    def __init__(self, ctx, evidence=None):
        self.ctx = ctx
        self.evidence = evidence

    def current_context(self):
        return self.ctx

    def verify_execution(self, record, target_digest):
        return self.evidence


def _write(root: pathlib.Path, source: str, local_ref: str, sel_raw, exec_raw=None,
           *, key: str = KEY, task_key: str | None = None) -> pathlib.Path:
    encoded = m.encode_local_ref(local_ref)
    if source == "pm":
        base = root / key / "evidence" / "decision-handoffs"
    else:
        base = root / key / "workers" / task_key / "local-decisions"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{encoded}.json").write_bytes(
        sel_raw if isinstance(sel_raw, bytes) else sel_raw.encode("utf-8"))
    if exec_raw is not None:
        (base / f"{encoded}.execution.json").write_bytes(
            exec_raw if isinstance(exec_raw, bytes) else exec_raw.encode("utf-8"))
    return base


def _all_files(root: pathlib.Path) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# ── cross-language consistency (TS frozen module + verbatim fixtures) ──────

def test_schema_v1_matches_verbatim_frozen_summary():
    assert m.SCHEMA_V1 == FROZEN
    # byte-level field lists are the frozen contract itself
    assert tuple(m.SCHEMA_V1["local_selection_fields"]) == m.LOCAL_SELECTION_FIELDS
    assert tuple(m.SCHEMA_V1["local_execution_fields"]) == m.LOCAL_EXECUTION_FIELDS
    assert tuple(m.SCHEMA_V1["forbidden_dp_fields"]) == m.FORBIDDEN_LOCAL_DP_FIELDS
    # a pure success is shape-only; never a host-source proof
    assert m.SCHEMA_V1["verification_scope"] == "shape-only"
    assert m.SCHEMA_V1["host_source_verified"] is False


def test_schema_v1_parity_with_current_frozen_ts_module():
    """Node 22+/24 strip-types import of the CURRENT frozen TS module.  Skips
    (does not fail) when Node/strip-types or the frozen file is unavailable."""
    ts = (pathlib.Path(__file__).resolve().parents[1]
          / "coding-agent" / "src" / "extensions" / "agent-team-loop"
          / "shared" / "decision-handoff.ts")
    if not ts.is_file():
        pytest.skip("frozen TS module not present")
    p = ts.as_posix()
    url = ("file://" + p) if p.startswith("/") else ("file:///" + p)
    script = f"import({url!r}).then(x=>process.stdout.write(JSON.stringify(x.SCHEMA_V1))).catch(e=>{{console.error(e.message);process.exit(3)}})"
    try:
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("node strip-types import unavailable")
    if proc.returncode != 0:
        pytest.skip("node strip-types import unsupported: " + proc.stderr.strip()[:200])
    ts_schema = json.loads(proc.stdout)
    assert ts_schema == m.SCHEMA_V1, "Python SCHEMA_V1 drifted from frozen TS SCHEMA_V1"


# ── pure parse: exact frozen examples ──────────────────────────────────────

def test_frozen_selection_and_decision_refs_parse():
    r = m.parse_local_selection_json(SELECTION_JSON)
    assert r.ok and r.value is not None, r.issues
    assert r.value.kind == "local-selection" and r.value.action_state == "planned"
    assert r.value.business_completed is False
    assert r.value.parent_decision_ref == m.DpDecisionRef(decision_id="dp-auto:2026-11-12T04:00:00Z")
    assert m.parse_decision_ref(DP_REF).value == m.DpDecisionRef(decision_id="dp-auto:2026-11-12T04:00:00Z")
    assert m.parse_decision_ref(LOCAL_REF).value == m.LocalDecisionRef(local_ref="local:T01:1")


def test_frozen_execution_and_budget_parse():
    e = m.parse_local_execution_json(EXECUTION_JSON)
    assert e.ok and e.value is not None, e.issues
    assert e.value.effect_state == "known" and e.value.verified_by == "target-verifier:1"
    b = m.validate_matter_budget(json.loads(MATTER_BUDGET_JSON))
    assert b.ok and b.value is not None, b.issues
    assert b.value.source_refs == ("tasks/T01-local-contract.md:timeout=90", "run.json:remaining")


def test_every_success_is_shape_only_every_failure_is_fillable():
    successes = [
        m.parse_local_selection_json(SELECTION_JSON),
        m.parse_local_execution_json(EXECUTION_JSON),
        m.validate_matter_budget(json.loads(MATTER_BUDGET_JSON)),
        m.parse_decision_ref(DP_REF), m.parse_decision_ref(LOCAL_REF),
        m.parse_host_binding(_sel_obj()["host_binding"]),
    ]
    for s in successes:
        assert s.ok
        assert s.verification == "shape-only"
        assert s.host_source_verified is False
    failure = m.parse_local_selection_record({"schema_version": 1})
    assert not failure.ok and failure.authority_required is False


# ── pure parse: DecisionRef discriminated / local_ref is never a DP id ─────

def test_decision_ref_discriminated_and_routing():
    assert m.route_decision_ref(DP_REF).value == "dp"
    assert m.route_decision_ref(LOCAL_REF).value == "local"
    # a local ref has NO decision_id and never routes to the DP join
    local = m.parse_decision_ref(LOCAL_REF).value
    assert isinstance(local, m.LocalDecisionRef) and not hasattr(local, "decision_id")
    # malformed discriminator variants
    bad = [
        {"kind": "dp"}, {"kind": "local"}, {"kind": "dp", "local_ref": "x"},
        {"kind": "local", "decision_id": "x"},
        {"kind": "dp", "decision_id": "x", "available": True},
        {"kind": "other", "decision_id": "x"},
        {"kind": "local", "local_ref": ""}, "local:T01:1", None,
    ]
    for value in bad:
        assert not m.parse_decision_ref(value).ok, value


def test_local_ref_never_becomes_a_dp_id_in_a_record():
    obj = _sel_obj()
    obj["parent_decision_ref"] = {"kind": "local", "local_ref": "local:T01:1"}
    assert not m.parse_local_selection_record(obj).ok  # parent must be a real dp ref
    obj2 = _sel_obj()
    obj2["decision_id"] = "local:T01:1"  # DP impersonation
    assert not m.parse_local_selection_record(obj2).ok
    # parsed local record exposes local_ref, never a decision_id/available/model_called
    rec = _parse_sel(_sel_obj())
    for forbidden in ("decision_id", "available", "model_called", "business_decisions", "host_source_verified"):
        assert not hasattr(rec, forbidden)
    assert rec.local_ref == "local:T01:1"


# ── pure parse: closed sets / bool-as-int / NaN / unknown / duplicate keys ──

@pytest.mark.parametrize("mutate", [
    lambda o: o.update(schema_version=2),
    lambda o: o.update(schema_version="1"),
    lambda o: o.update(kind="local-execution"),
    lambda o: o.update(origin="dp"),
    lambda o: o.update(source="dp"),
    lambda o: o.update(action_state="known"),
    lambda o: o.update(business_completed=True),
    lambda o: o.__setitem__("host_binding", {**o["host_binding"], "role": "root"}),
    lambda o: o.update(created_at="not-a-timestamp"),
])
def test_closed_sets_and_required_literals_rejected(mutate):
    obj = _sel_obj()
    mutate(obj)
    assert not m.parse_local_selection_record(obj).ok


@pytest.mark.parametrize("mutate", [
    lambda o: o.update(effect_state="none"),
    lambda o: o.update(effect_state="unknown2"),
    lambda o: o.update(schema_version=None),
])
def test_execution_closed_sets_rejected(mutate):
    obj = _exec_obj()
    mutate(obj)
    assert not m.parse_local_execution_record(obj).ok


def test_python_bool_as_int_rejected():
    sel = _sel_obj()
    sel["schema_version"] = True  # True == 1 in Python; TS true !== 1
    assert not m.parse_local_selection_record(sel).ok
    sel2 = _sel_obj()
    sel2["business_completed"] = 0  # 0 == False but must be literally False
    assert not m.parse_local_selection_record(sel2).ok
    for key in ("max_steps", "no_progress_limit", "remaining_cost", "steps_consumed", "cost_consumed", "no_progress_count"):
        b = _live_budget()
        b[key] = True
        assert not m.validate_matter_budget(b).ok, key


@pytest.mark.parametrize("raw", [
    '{"schema_version":NaN,"kind":"local-selection"}',
    '{"schema_version":Infinity,"kind":"local-selection"}',
    '{"schema_version":-Infinity,"kind":"local-selection"}',
    '{"schema_version":1e400,"kind":"local-selection"}',
])
def test_nan_infinity_json_rejected(raw):
    with pytest.raises(m.StrictJsonError) as exc:
        m.loads_strict_json(raw)
    assert exc.value.code in ("non-finite-number", "bad-json")
    assert not m.parse_local_selection_json(raw).ok


def test_nan_infinity_python_value_rejected():
    b = _live_budget()
    b["remaining_cost"] = float("nan")
    assert not m.validate_matter_budget(b).ok
    b2 = _live_budget()
    b2["remaining_cost"] = float("inf")
    assert not m.validate_matter_budget(b2).ok


def test_unknown_key_rejected():
    obj = _sel_obj()
    obj["surprise"] = 1
    r = m.parse_local_selection_record(obj)
    assert not r.ok
    assert any(i.rule == "not a declared schema v1 field" for i in r.issues)
    # unknown nested host-binding key
    obj2 = _sel_obj()
    obj2["host_binding"] = {**obj2["host_binding"], "extra": "x"}
    assert not m.parse_local_selection_record(obj2).ok


def test_present_null_optional_is_not_absent():
    obj = _sel_obj()
    obj["feedback_ref"] = None  # present null is rejected, not guessed as unknown
    assert not m.parse_local_selection_record(obj).ok
    obj2 = _sel_obj()
    del obj2["feedback_ref"]  # genuinely absent is fine
    assert m.parse_local_selection_record(obj2).ok


def test_duplicate_json_keys_rejected():
    raw = '{"schema_version":1,"schema_version":1}'
    with pytest.raises(m.StrictJsonError) as exc:
        m.loads_strict_json(raw)
    assert exc.value.code == "duplicate-json-key"
    # duplicate keys inside a real selection JSON (nested too)
    dup = SELECTION_JSON.replace('"matter_ref": "matter:T01",', '"matter_ref": "matter:T01","matter_ref": "matter:T01",')
    r = m.parse_local_selection_json(dup)
    assert not r.ok
    assert any(i.rule == "duplicate-json-key" for i in r.issues)


def test_forbidden_dp_fields_rejected():
    for field in m.FORBIDDEN_LOCAL_DP_FIELDS:
        obj = _sel_obj()
        obj[field] = True
        r = m.parse_local_selection_record(obj)
        assert not r.ok, field
        assert any("forbidden DP impersonation" in i.rule for i in r.issues), field
    for field in m.FORBIDDEN_LOCAL_DP_FIELDS:
        obj = _exec_obj()
        obj[field] = "x"
        assert not m.parse_local_execution_record(obj).ok, field


def test_selection_masquerading_as_execution_rejected():
    # selection carrying execution facts -> unknown keys
    obj = _sel_obj()
    obj.update(action_ref="tool_call:read:7", result_ref="tool_result:read:7", verified_by="v")
    assert not m.parse_local_selection_record(obj).ok
    # a selection object is not a valid execution record
    assert not m.parse_local_execution_record(_sel_obj()).ok
    # an execution object is not a valid selection record
    assert not m.parse_local_selection_record(_exec_obj()).ok


def test_execution_requires_action_result_verifier():
    for key in ("action_ref", "result_ref", "executor", "target_digest", "observed_effect", "verified_by", "budget_ref", "host_binding"):
        obj = _exec_obj()
        del obj[key]
        assert not m.parse_local_execution_record(obj).ok, key


def test_is_json_value_and_encode_local_ref():
    assert m.is_json_value({"a": [1, True, None, "x"]})
    assert not m.is_json_value(float("nan"))
    assert not m.is_json_value({"a": float("inf")})
    cyc = []
    cyc.append(cyc)
    assert not m.is_json_value(cyc)
    enc = m.encode_local_ref("local:T01:1")
    assert "=" not in enc and "/" not in enc and "+ " not in enc
    assert enc == "bG9jYWw6VDAxOjE"
    assert m.encode_local_ref("local:T01:2") != enc
    for bad in ("", "   ", "\x00a", "x" * 400, None, 5):
        with pytest.raises(m.StrictJsonError):
            m.encode_local_ref(bad)


# ── read-only path / bad JSON / locks / unstable reads ─────────────────────

def test_path_traversal_and_bad_components(tmp_path):
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    assert "bad-key" in m.read_local_evidence(tmp_path, "..", "pm", PM_REF).failure_codes
    assert "bad-key" in m.read_local_evidence(tmp_path, "a/b", "pm", PM_REF).failure_codes
    assert "bad-source" in m.read_local_evidence(tmp_path, KEY, "bogus", PM_REF).failure_codes
    assert "bad-task-key" in m.read_local_evidence(tmp_path, KEY, "worker-local", PM_REF, task_key="../x").failure_codes
    assert "bad-task-key" in m.read_local_evidence(tmp_path, KEY, "worker-local", PM_REF, task_key=None).failure_codes
    assert "bad-ref" in m.read_local_evidence(tmp_path, KEY, "pm", "").failure_codes
    # direct containment check on a path that leaves the root
    with pytest.raises(m._StrictFailure) as exc:
        m._assert_path_chain_safe(tmp_path, tmp_path / ".." / "elsewhere" / "x.json")
    assert exc.value.code in ("path-outside-base", "path-traversal")


def test_redirect_rejected(tmp_path, monkeypatch):
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    monkeypatch.setattr(m, "_is_redirect", lambda p: True)
    r = m.read_local_evidence(tmp_path, KEY, "pm", PM_REF)
    assert "path-redirect" in r.failure_codes and r.selection is None


def test_wrong_file_kind_rejected(tmp_path):
    # a directory where a regular file is expected
    d = tmp_path / KEY / "evidence" / "decision-handoffs" / (m.encode_local_ref(PM_REF) + ".json")
    d.mkdir(parents=True, exist_ok=True)
    with pytest.raises(m._StrictFailure) as exc:
        m._stable_read_bytes(d)
    assert exc.value.code == "wrong-file-kind"


def test_noncanonical_filename_is_never_opened(tmp_path):
    encoded = m.encode_local_ref(PM_REF)
    base = tmp_path / KEY / "evidence" / "decision-handoffs"
    base.mkdir(parents=True, exist_ok=True)
    # Noncanonical names only: padded (=), a different (extended) encoding, and
    # a lower-case-canonical lookalike with an extra char.  The reader derives
    # ONLY the canonical no-padding name and must open none of these.  (A raw
    # ref with ':' cannot even be a filename on Windows, and case variants can
    # collide on case-insensitive filesystems, so neither is used here.)
    (base / (encoded + "=.json")).write_text(SELECTION_JSON, encoding="utf-8")
    (base / (encoded + "X.json")).write_text(SELECTION_JSON, encoding="utf-8")
    (base / (encoded + ".json.bak")).write_text(SELECTION_JSON, encoding="utf-8")
    r = m.read_local_evidence(tmp_path, KEY, "pm", PM_REF)
    assert r.selection is None and "selection-not-found" in r.failure_codes


def test_bad_json_and_duplicate_keys_on_disk(tmp_path):
    _write(tmp_path, "pm", PM_REF, "{not json")
    assert "record-parse-failed" in m.read_local_evidence(tmp_path, KEY, "pm", PM_REF).failure_codes
    dup = SELECTION_JSON.replace('"matter_ref": "matter:T01",', '"matter_ref": "matter:T01","matter_ref": "matter:T01",')
    _write(tmp_path, "pm", PM_REF, dup)
    assert "record-parse-failed" in m.read_local_evidence(tmp_path, KEY, "pm", PM_REF).failure_codes


def test_lock_present_makes_snapshot_unstable(tmp_path):
    base = _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    (base / "intent.lock").write_text("busy", encoding="utf-8")
    r = m.read_local_evidence(tmp_path, KEY, "pm", PM_REF)
    assert "unstable-snapshot" in r.failure_codes and r.selection is None


def test_unstable_read_rejected(tmp_path, monkeypatch):
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    vals = iter([(0, 0, 1, 111), (0, 0, 1, 222)])
    monkeypatch.setattr(m, "_fingerprint", lambda p: next(vals))
    r = m.read_local_evidence(tmp_path, KEY, "pm", PM_REF)
    assert "unstable-read" in r.failure_codes and r.selection is None


def test_read_loads_selection_and_optional_execution_with_hashes(tmp_path):
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON, EXECUTION_JSON)
    r = m.read_local_evidence(tmp_path, KEY, "pm", PM_REF)
    assert r.ok and r.selection is not None and r.execution is not None
    assert r.host_source_verified is False and r.verification == "shape-only"
    assert r.selection_sha256 and r.execution_sha256
    assert r.selection_path.endswith(".json") and r.execution_path.endswith(".execution.json")


# ── strict verify: trusted context is mandatory, fails closed ──────────────

def test_pm_and_worker_local_sources_strict_verify(tmp_path):
    # PM (frozen example)
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    r = m.strict_verify(tmp_path, KEY, "pm", PM_REF,
                        which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    assert r.ok and r.host_source_verified is True and r.verification == "strict-verified"
    assert r.authority_required is False and len(r.checks) > 5
    # worker-local bound to current task/run
    wobj = _worker_sel_obj()
    wsel = _parse_sel(wobj)
    _write(tmp_path, "worker-local", PM_REF, json.dumps(wobj), task_key=WORKER_TASK)
    r2 = m.strict_verify(tmp_path, KEY, "worker-local", PM_REF,
                         which="selection", task_key=WORKER_TASK, adapter=FakeAdapter(_ctx_from(wsel)))
    assert r2.ok and r2.host_source_verified is True, r2.failure_codes


def test_missing_adapter_context_or_authority_fails_closed(tmp_path):
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    good = _ctx_from(sel)
    cases = [
        (None, "missing-trusted-adapter"),
        ("owner:string:not-a-capability", "missing-trusted-adapter"),
        ({}, "missing-trusted-adapter"),
        (FakeAdapter(None), "missing-trusted-context"),
    ]
    for adapter, code in cases:
        r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=adapter)
        assert not r.host_source_verified and code in r.failure_codes, (adapter, r.failure_codes)
    for authority in ("_index.md", "latest", "global", "model-supplied"):
        ctx = replace(good, binding=replace(good.binding, authority=authority))
        r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
        assert not r.host_source_verified and "non-authoritative-binding" in r.failure_codes
    ctx = replace(good, binding=replace(good.binding, active_row_count=2))
    assert "binding-not-unique" in m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx)).failure_codes
    ctx = replace(good, binding=replace(good.binding, is_active=False))
    assert "binding-not-active" in m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx)).failure_codes


def test_wrong_role_rejected(tmp_path):
    wobj = _worker_sel_obj()
    wsel = _parse_sel(wobj)
    _write(tmp_path, "worker-local", PM_REF, json.dumps(wobj), task_key=WORKER_TASK)
    good = _ctx_from(wsel)
    # worker-local cannot use a pm role
    ctx = replace(good, binding=replace(good.binding, role="pm"))
    r = m.strict_verify(tmp_path, KEY, "worker-local", PM_REF, which="selection",
                        task_key=WORKER_TASK, adapter=FakeAdapter(ctx))
    assert "source-role-mismatch" in r.failure_codes and not r.host_source_verified
    # pm source requires pm role
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    ctx2 = replace(_ctx_from(sel), binding=replace(_ctx_from(sel).binding, role="coding"))
    r2 = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx2))
    assert "source-role-mismatch" in r2.failure_codes


def test_absent_vs_present_identity_drift(tmp_path):
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    good = _ctx_from(sel)
    # ctx binding gains a task_key the record lacks -> drift
    ctx = replace(good, binding=replace(good.binding, task_key="appeared"))
    r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
    assert "binding-drift" in r.failure_codes and not r.host_source_verified
    # ctx binding drops claim_id the record has -> drift
    ctx2 = replace(good, binding=replace(good.binding, claim_id=None))
    r2 = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx2))
    assert "binding-drift" in r2.failure_codes


@pytest.mark.parametrize("which,expected", [
    ("claim_id", "binding-drift"),
    ("binding_version", "binding-drift"),
    ("matter_ref", "matter-drift"),
    ("matter_version", "matter-version-drift"),
    ("material_digest", "material-drift"),
    ("basis_digest", "basis-drift"),
    ("budget_ref", "budget-ref-drift"),
])
def test_current_evidence_drift_rejected(tmp_path, which, expected):
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    good = _ctx_from(sel)
    if which in ("claim_id", "binding_version"):
        ctx = replace(good, binding=replace(good.binding, **{which: "DRIFT"}))
    elif which == "budget_ref":
        ctx = replace(good, budget=_live_budget("budget:OTHER"))
    else:
        ctx = replace(good, **{which: "DRIFT"})
    r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
    assert expected in r.failure_codes and not r.host_source_verified, r.failure_codes


def test_parent_absent_vs_present_drift(tmp_path):
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    good = _ctx_from(sel)
    # record has parent, ctx drops it -> drift
    r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(replace(good, parent_decision_ref=None)))
    assert "parent-drift" in r.failure_codes
    # ctx parent points at a different decision -> drift
    r2 = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection",
                         adapter=FakeAdapter(replace(good, parent_decision_ref={"kind": "dp", "decision_id": "dp-auto:OTHER"})))
    assert "parent-drift" in r2.failure_codes
    # parent must be a real dp ref, never a local one
    r3 = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection",
                         adapter=FakeAdapter(replace(good, parent_decision_ref={"kind": "local", "local_ref": "local:T01:1"})))
    assert "parent-drift" in r3.failure_codes


def test_old_claim_run_only_recovery_clue(tmp_path):
    wobj = _worker_sel_obj()
    wsel = _parse_sel(wobj)
    _write(tmp_path, "worker-local", PM_REF, json.dumps(wobj), task_key=WORKER_TASK)
    # an OLD-run file under another task dir with the same local_ref
    old = tmp_path / KEY / "workers" / "w0" / "local-decisions"
    old.mkdir(parents=True, exist_ok=True)
    (old / (m.encode_local_ref(PM_REF) + ".json")).write_text(json.dumps(wobj), encoding="utf-8")
    read = m.read_local_evidence(tmp_path, KEY, "worker-local", PM_REF, task_key=WORKER_TASK)
    assert any("w0" in p for p in read.recovery_clues)
    # current binding is a DIFFERENT run -> the record's old run cannot verify
    good = _ctx_from(wsel)
    ctx = replace(good, binding=replace(good.binding, run_id="run:OLD"))
    r = m.strict_verify(tmp_path, KEY, "worker-local", PM_REF, which="selection",
                        task_key=WORKER_TASK, adapter=FakeAdapter(ctx))
    assert not r.host_source_verified
    assert "worker-not-current-run" in r.failure_codes or "binding-drift" in r.failure_codes


@pytest.mark.parametrize("budget_mut,code", [
    (lambda b: b.update(max_steps=float("nan")), "invalid-budget"),
    (lambda b: b.update(remaining_cost=float("inf")), "invalid-budget"),
    (lambda b: b.update(max_steps=-1), "invalid-budget"),
    (lambda b: b.update(source_refs=[]), "invalid-budget"),
    (lambda b: b.update(remaining_cost=0), "budget-exhausted"),
    (lambda b: b.update(steps_consumed=5), "budget-exhausted"),
    (lambda b: b.update(no_progress_count=3), "budget-exhausted"),
    (lambda b: b.update(deadline="2000-01-01T00:00:00+00:00"), "budget-exhausted"),
])
def test_budget_invalid_or_exhausted_rejects_new_business(tmp_path, budget_mut, code):
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    budget = _live_budget()
    budget_mut(budget)
    ctx = replace(_ctx_from(sel), budget=budget)
    r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
    assert code in r.failure_codes and not r.host_source_verified, r.failure_codes


def test_scope_stop_not_overridden_by_timeout_or_exemption(tmp_path):
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON)
    good = _ctx_from(sel)
    # Global / key / matter stops block EVERY current record, even with a
    # service timeout and exemption (which never override a stop).
    for scope in ("user-global", "pm-or-key", "matter"):
        ctx = replace(good, stop_scope=scope, exemption_active=True, service_timeout=True)
        r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
        assert "scope-stop" in r.failure_codes and not r.host_source_verified, scope
    # T03-R1 PY05: a worker-run stop is NOT global. It must NOT stop an
    # unrelated PM record (the old assertion wrongly required this to stop).
    ctx = replace(good, stop_scope="worker-run", exemption_active=True, service_timeout=True)
    r_pm = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
    assert r_pm.ok and r_pm.host_source_verified is True and "scope-stop" not in r_pm.failure_codes, r_pm.failure_codes
    # a service-request-only stop is NOT a PM/key stop
    ctx = replace(good, stop_scope="service-request", service_timeout=True)
    r2 = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
    assert r2.ok and r2.host_source_verified is True, r2.failure_codes
    # REAL worker negative: a worker-run stop DOES stop the current worker;
    # global / key / matter stops still block it too. The stop boundary is NOT
    # weakened by the PM fix above.
    wobj = _worker_sel_obj()
    wsel = _parse_sel(wobj)
    _write(tmp_path, "worker-local", PM_REF, json.dumps(wobj), task_key=WORKER_TASK)
    for scope in ("worker-run", "user-global", "pm-or-key", "matter"):
        wctx = replace(_ctx_from(wsel), stop_scope=scope)
        rw = m.strict_verify(tmp_path, KEY, "worker-local", PM_REF, which="selection",
                             task_key=WORKER_TASK, adapter=FakeAdapter(wctx))
        assert "scope-stop" in rw.failure_codes and not rw.host_source_verified, scope


# ── strict verify: execution action/result/verifier ────────────────────────

def test_execution_strict_verify_needs_real_action_result_verifier(tmp_path):
    sel = _parse_sel(_sel_obj())
    ex = _parse_exec(_exec_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON, EXECUTION_JSON)
    ctx = _ctx_from(sel)
    # positive: real host verifier evidence
    r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="execution",
                        adapter=FakeAdapter(ctx, _evidence_for(ex)))
    assert r.ok and r.host_source_verified is True, r.failure_codes
    # missing verifier / boolean self-proof / mere file existence
    negatives = [
        (None, "missing-verifier"),
        (True, "self-proof-rejected"),  # a bare boolean is a self-proof, not evidence
        (_evidence_for(ex, confirmed=False), "action-result-unverified"),
        (_evidence_for(ex, confirmed=1), "action-result-unverified"),  # truthy non-bool
        (_evidence_for(ex, action_receipt_ref=""), "missing-action-result"),
        (_evidence_for(ex, verifier_receipt_ref="someone-else"), "verifier-mismatch"),
        (_evidence_for(ex, action_receipt_ref="tool_call:read:99"), "verifier-mismatch"),
        (_evidence_for(ex, observed_object_digest="sha256:OTHER"), "target-drift"),
    ]
    for evidence, code in negatives:
        rr = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="execution",
                             adapter=FakeAdapter(ctx, evidence))
        assert not rr.host_source_verified and code in rr.failure_codes, (evidence, rr.failure_codes)
    # current object/target digest drift in ctx
    drift = replace(ctx, target_digest="sha256:OTHER")
    rd = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="execution",
                         adapter=FakeAdapter(drift, _evidence_for(ex)))
    assert "target-drift" in rd.failure_codes and not rd.host_source_verified


def test_execution_without_original_selection_rejected(tmp_path):
    sel = _parse_sel(_sel_obj())
    ex = _parse_exec(_exec_obj())
    base = tmp_path / KEY / "evidence" / "decision-handoffs"
    base.mkdir(parents=True, exist_ok=True)
    # only the execution file, no selection file
    (base / (m.encode_local_ref(PM_REF) + ".execution.json")).write_text(EXECUTION_JSON, encoding="utf-8")
    r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="execution",
                        adapter=FakeAdapter(_ctx_from(sel), _evidence_for(ex)))
    assert "missing-selection" in r.failure_codes and not r.host_source_verified
    # mismatched selection local_ref
    sel2 = _sel_obj()
    sel2["local_ref"] = "local:T01:DIFFERENT"
    _write(tmp_path, "pm", PM_REF, json.dumps(sel2), EXECUTION_JSON)
    r2 = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="execution",
                         adapter=FakeAdapter(_ctx_from(sel), _evidence_for(ex)))
    assert not r2.host_source_verified


def test_execution_cannot_smuggle_execution_facts_into_selection(tmp_path):
    sel = _parse_sel(_sel_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON, EXECUTION_JSON)
    # a selection carrying a self-proof boolean is rejected at parse time
    obj = _sel_obj()
    obj["verified"] = True
    obj["available"] = True
    assert not m.parse_local_selection_record(obj).ok
    # strict result records real checks/codes but never mutates the frozen record
    r = m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    assert isinstance(r.value, m.LocalSelectionRecord)
    assert not hasattr(r.value, "verified") and not hasattr(r.value, "host_source_verified")
    assert r.value.local_ref == PM_REF


# ── read-only guarantee: zero writes, no repair of invalid-existing ─────────

def test_strict_verify_is_read_only_zero_writes(tmp_path):
    sel = _parse_sel(_sel_obj())
    ex = _parse_exec(_exec_obj())
    _write(tmp_path, "pm", PM_REF, SELECTION_JSON, EXECUTION_JSON)
    before = _all_files(tmp_path)
    m.read_local_evidence(tmp_path, KEY, "pm", PM_REF)
    m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    m.strict_verify(tmp_path, KEY, "pm", PM_REF, which="execution", adapter=FakeAdapter(_ctx_from(sel), _evidence_for(ex)))
    after = _all_files(tmp_path)
    assert before == after, "reader created/modified/removed a file"
    assert not any(p.name.endswith(".lock") for p in tmp_path.rglob("*")), "reader created a lock"


def test_invalid_existing_file_is_not_repaired_or_overwritten(tmp_path):
    broken = b'{"schema_version":1,"kind":"local-selection","broken":'
    base = _write(tmp_path, "pm", PM_REF, broken)
    sel_path = base / (m.encode_local_ref(PM_REF) + ".json")
    r = m.read_local_evidence(tmp_path, KEY, "pm", PM_REF)
    assert r.selection is None and "record-parse-failed" in r.failure_codes
    assert sel_path.read_bytes() == broken, "reader repaired/overwrote invalid-existing"
    assert not (base / (m.encode_local_ref(PM_REF) + ".execution.json")).exists()


# ── T03-R1 acceptance-repair regressions (PM S1 reader-probe.py) ──────────
# These lock in the eight reproduced red boundaries: identity association,
# budget matter, stop scope, real T02 locks / stable snapshot, invalid-existing
# execution and final-state recheck. Each keeps a legitimate positive control.

def _r1_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Isolated .agenticdoc-style root so the T02 shared intent lock path
    (<root>/../.mw/decision-handoff-intent.lock) stays INSIDE this test's
    tmp_path and never leaks into a shared pytest parent dir."""
    return tmp_path / ".agenticdoc"


def _r1_shared_lock(root: pathlib.Path) -> pathlib.Path:
    # Exact T02 path; realpath matches the reader's root canonicalization.
    return pathlib.Path(os.path.realpath(str(root))).parent / ".mw" / "decision-handoff-intent.lock"


def test_r1_request_local_ref_binds_to_record(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    base = _write(root, "pm", PM_REF, SELECTION_JSON)
    ok = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    assert ok.ok and ok.host_source_verified is True, ok.failure_codes  # positive control
    o = _sel_obj()
    o["local_ref"] = "local:OTHER"  # valid OTHER ref placed at the requested filename
    (base / (m.encode_local_ref(PM_REF) + ".json")).write_text(json.dumps(o), encoding="utf-8")
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    assert not r.host_source_verified and "local-ref-mismatch" in r.failure_codes


def test_r1_requested_key_binds_record_and_trusted_binding(tmp_path):
    root = _r1_root(tmp_path)
    o = _sel_obj()
    o["host_binding"]["key"] = "foreign-key"
    _write(root, "pm", PM_REF, json.dumps(o))
    # The adapter's trusted binding ALSO agrees with the tampered foreign key;
    # agreeing with the wrong record cannot substitute for the requested key.
    ctx = _ctx_from(_parse_sel(o))
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
    assert not r.host_source_verified and "key-mismatch" in r.failure_codes


def test_r1_pm_path_rejects_worker_local_record(tmp_path):
    root = _r1_root(tmp_path)
    o = _worker_sel_obj()  # worker-local record, but written at the PM path
    _write(root, "pm", PM_REF, json.dumps(o))
    ctx = _ctx_from(_parse_sel(o))
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
    assert not r.host_source_verified and "source-mismatch" in r.failure_codes


def test_r1_budget_matter_must_match_current_matter(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    _write(root, "pm", PM_REF, SELECTION_JSON)
    budget = _live_budget()  # SAME budget_ref, but a DIFFERENT matter
    budget["matter_ref"] = "matter:OTHER"
    ctx = replace(_ctx_from(sel), budget=budget)
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(ctx))
    assert not r.host_source_verified and "budget-matter-drift" in r.failure_codes


def test_r1_exact_t02_locks_refuse_snapshot_read_only(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    base = _write(root, "pm", PM_REF, SELECTION_JSON)
    # 1) shared intent lock at the EXACT T02 path (not a sibling *.lock)
    shared = _r1_shared_lock(root)
    shared.parent.mkdir(parents=True, exist_ok=True)
    shared.write_text("busy", encoding="utf-8")
    before = _all_files(tmp_path)
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    assert not r.host_source_verified and "unstable-snapshot" in r.failure_codes
    assert _all_files(tmp_path) == before, "reader created/broke a lock or file"
    shared.unlink()
    # 2) per-record local lock <selection>.lock
    per = base / (m.encode_local_ref(PM_REF) + ".json.lock")
    per.write_text("busy", encoding="utf-8")
    r2 = m.read_local_evidence(root, KEY, "pm", PM_REF)
    assert "unstable-snapshot" in r2.failure_codes and r2.selection is None


def test_r1_lock_appearing_during_verification_refuses(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    _write(root, "pm", PM_REF, SELECTION_JSON)
    shared = _r1_shared_lock(root)

    class LockAppears(FakeAdapter):
        def current_context(self):
            # lock appears AFTER the initial read (during the host-context call)
            shared.parent.mkdir(parents=True, exist_ok=True)
            shared.write_text("busy", encoding="utf-8")
            return self.ctx

    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=LockAppears(_ctx_from(sel)))
    assert not r.host_source_verified and "unstable-snapshot" in r.failure_codes


def test_r1_invalid_existing_execution_is_rejected_not_absent(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    base = _write(root, "pm", PM_REF, SELECTION_JSON)  # no execution written
    exec_path = base / (m.encode_local_ref(PM_REF) + ".execution.json")
    # 1) a DIRECTORY at the optional execution path must not be treated as absent
    exec_path.mkdir()
    r = m.read_local_evidence(root, KEY, "pm", PM_REF)
    assert "wrong-file-kind" in r.failure_codes and r.execution is None
    assert exec_path.is_dir(), "reader repaired/removed invalid-existing execution"
    r2 = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    assert not r2.host_source_verified
    exec_path.rmdir()
    # 2) a broken symlink at the optional execution path is likewise rejected
    try:
        exec_path.symlink_to(base / "no-such-target")
    except (OSError, NotImplementedError):
        return  # symlinks unavailable on this host; directory case already covered
    r3 = m.read_local_evidence(root, KEY, "pm", PM_REF)
    assert r3.execution is None
    assert any(c in ("path-redirect", "wrong-file-kind") for c in r3.failure_codes)


def test_r1_stale_bytes_and_context_during_verification_refuse(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    base = _write(root, "pm", PM_REF, SELECTION_JSON)
    sel_path = base / (m.encode_local_ref(PM_REF) + ".json")
    good = _ctx_from(sel)

    class Mutating(FakeAdapter):
        def current_context(self):
            # change the on-disk record but return the OLD, matching context
            o = _sel_obj()
            o["basis_digest"] = "sha256:CHANGED"
            sel_path.write_text(json.dumps(o), encoding="utf-8")
            return self.ctx

    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=Mutating(good))
    assert not r.host_source_verified and "unstable-snapshot" in r.failure_codes

    # A trusted context that quietly changes between the verification read and
    # the FINAL recheck must not verify either (no file change involved).
    _write(root, "pm", PM_REF, SELECTION_JSON)  # reset original bytes
    drifted = replace(good, material_digest="sha256:OTHER")

    class Drifting(FakeAdapter):
        def __init__(self):
            super().__init__(good)
            self.n = 0

        def current_context(self):
            self.n += 1
            return self.ctx if self.n == 1 else drifted

    r2 = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=Drifting())
    assert not r2.host_source_verified and "context-drift" in r2.failure_codes


def test_r1_execution_request_identity_binds_both_records(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    ex = _parse_exec(_exec_obj())
    base = _write(root, "pm", PM_REF, SELECTION_JSON, EXECUTION_JSON)
    ok = m.strict_verify(root, KEY, "pm", PM_REF, which="execution",
                         adapter=FakeAdapter(_ctx_from(sel), _evidence_for(ex)))
    assert ok.ok and ok.host_source_verified is True, ok.failure_codes  # positive control
    # foreign key in BOTH records + adapter agrees -> requested key still fails
    o = _sel_obj()
    o["host_binding"]["key"] = "foreign-key"
    e = _exec_obj()
    e["host_binding"]["key"] = "foreign-key"
    (base / (m.encode_local_ref(PM_REF) + ".json")).write_text(json.dumps(o), encoding="utf-8")
    (base / (m.encode_local_ref(PM_REF) + ".execution.json")).write_text(json.dumps(e), encoding="utf-8")
    ctx = _ctx_from(_parse_sel(o))
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="execution",
                        adapter=FakeAdapter(ctx, _evidence_for(_parse_exec(e))))
    assert not r.host_source_verified and "key-mismatch" in r.failure_codes


def test_r1_windows_short_long_root_alias(tmp_path, monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows 8.3 alias is Windows-specific")
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    _write(root, "pm", PM_REF, SELECTION_JSON)
    long_root = pathlib.Path(os.path.realpath(str(root)))
    short = None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(str(long_root), buf, 1024):
            short = pathlib.Path(buf.value)
    except (OSError, AttributeError, ValueError):
        short = None
    if short is None or str(short) == str(long_root):
        pytest.skip("no distinct 8.3 short-name alias for this path")
    # A legitimate path under the short-name root alias must NOT be flagged
    # path-outside-base; root canonicalization makes it verify.
    r = m.strict_verify(short, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    assert r.ok and r.host_source_verified is True, r.failure_codes
    # A real redirect in the record chain is still refused (never trusted),
    # even through the short-name alias.
    monkeypatch.setattr(m, "_is_redirect", lambda p: True)
    r2 = m.strict_verify(short, KEY, "pm", PM_REF, which="selection", adapter=FakeAdapter(_ctx_from(sel)))
    assert not r2.host_source_verified and "path-redirect" in r2.failure_codes


def test_r1_missing_adapter_still_fails_closed(tmp_path):
    root = _r1_root(tmp_path)
    _write(root, "pm", PM_REF, SELECTION_JSON)
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=None)
    assert not r.host_source_verified and "missing-trusted-adapter" in r.failure_codes


# ── T03-R2 final-boundary regressions (S1 R1-PY02/PY03/PY04) ───────────────
# The immutable initial projection is captured before later host callbacks;
# the newly returned context receives real checks, and the last callback is
# followed by local path/byte checks only. Legal observation-time refreshes and
# a still-live deadline remain positive controls.

def test_r2_fresh_observation_and_nonexpired_deadline_still_verify(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    _write(root, "pm", PM_REF, SELECTION_JSON)
    budget = _live_budget()
    budget["deadline"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)).isoformat()
    good = replace(_ctx_from(sel), budget=budget)

    class FreshObservation(FakeAdapter):
        def __init__(self, ctx):
            super().__init__(ctx)
            self.calls = 0

        def current_context(self):
            self.calls += 1
            if self.calls == 2:
                time.sleep(0.05)
            return replace(
                self.ctx,
                binding=replace(self.ctx.binding,
                                observed_at=dt.datetime.now(dt.timezone.utc).isoformat()),
            )

    adapter = FreshObservation(good)
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=adapter)
    assert r.ok and r.host_source_verified is True, r.failure_codes
    assert adapter.calls == 2, "no host callback may follow the final local checks"
    assert not m._deadline_passed(budget["deadline"])


def test_r2_in_place_nested_mutation_refuses_and_revalidates_new_context(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    _write(root, "pm", PM_REF, SELECTION_JSON)

    class BudgetMutation(FakeAdapter):
        def __init__(self, ctx):
            super().__init__(ctx)
            self.calls = 0

        def current_context(self):
            self.calls += 1
            if self.calls == 2:
                self.ctx.budget["remaining_cost"] = 0
            return self.ctx

    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection",
                        adapter=BudgetMutation(_ctx_from(sel)))
    assert not r.host_source_verified
    assert "context-drift" in r.failure_codes and "budget-exhausted" in r.failure_codes, r.failure_codes

    class ParentMutation(FakeAdapter):
        def __init__(self, ctx):
            super().__init__(ctx)
            self.calls = 0

        def current_context(self):
            self.calls += 1
            if self.calls == 2:
                self.ctx.parent_decision_ref["decision_id"] = "dp-auto:OTHER"
            return self.ctx

    r2 = m.strict_verify(root, KEY, "pm", PM_REF, which="selection",
                         adapter=ParentMutation(_ctx_from(sel)))
    assert not r2.host_source_verified
    assert "context-drift" in r2.failure_codes and "parent-drift" in r2.failure_codes, r2.failure_codes


def test_r2_final_context_stop_and_request_association_revalidated(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    _write(root, "pm", PM_REF, SELECTION_JSON)

    class NewContext(FakeAdapter):
        def __init__(self, ctx):
            super().__init__(ctx)
            self.calls = 0

        def current_context(self):
            self.calls += 1
            if self.calls == 1:
                return self.ctx
            return replace(
                self.ctx, stop_scope="matter",
                binding=replace(self.ctx.binding, key="foreign-key"),
            )

    adapter = NewContext(_ctx_from(sel))
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=adapter)
    assert not r.host_source_verified and adapter.calls == 2
    for code in ("context-drift", "scope-stop", "key-mismatch"):
        assert code in r.failure_codes, (code, r.failure_codes)


def test_r2_deadline_expiring_during_final_callback_refuses(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    _write(root, "pm", PM_REF, SELECTION_JSON)
    budget = _live_budget()
    budget["deadline"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2)).isoformat()
    ctx = replace(_ctx_from(sel), budget=budget)

    class Waiting(FakeAdapter):
        def __init__(self, ctx):
            super().__init__(ctx)
            self.calls = 0

        def current_context(self):
            self.calls += 1
            if self.calls == 2:
                time.sleep(2.1)
            return self.ctx

    adapter = Waiting(ctx)
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=adapter)
    assert not r.host_source_verified and adapter.calls == 2, r.failure_codes
    assert "budget-exhausted" in r.failure_codes, r.failure_codes
    assert "context-drift" not in r.failure_codes, r.failure_codes
    assert m._deadline_passed(budget["deadline"]) is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction fixture")
def test_r2_real_directory_junction_with_same_bytes_refused(tmp_path):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    base = _write(root, "pm", PM_REF, SELECTION_JSON)
    sel_path = base / (m.encode_local_ref(PM_REF) + ".json")
    original_hash = m._file_hash(sel_path)
    outside = root.parent / "outside"
    held = root.parent / "original-held"

    class JunctionOnFinal(FakeAdapter):
        def __init__(self, ctx):
            super().__init__(ctx)
            self.calls = 0

        def current_context(self):
            self.calls += 1
            if self.calls == 2:
                shutil.copytree(base, outside)
                base.rename(held)
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(base), str(outside)],
                    check=True, capture_output=True, text=True,
                )
            return self.ctx

    adapter = JunctionOnFinal(_ctx_from(sel))
    try:
        r = m.strict_verify(root, KEY, "pm", PM_REF, which="selection", adapter=adapter)
        assert m._is_redirect(str(base)) is True
        assert m._file_hash(sel_path) == original_hash, "fixture must preserve byte hash"
        assert not r.host_source_verified, r.failure_codes
        assert "path-redirect" in r.failure_codes or "path-traversal" in r.failure_codes, r.failure_codes
        assert adapter.calls == 2 and held.is_dir()
    finally:
        if m._is_redirect(str(base)):
            os.rmdir(str(base))


@pytest.mark.parametrize("mutation,expected_code", [
    ("selection-bytes", "unstable-snapshot"),
    ("execution-bytes", "unstable-snapshot"),
    ("execution-kind", "wrong-file-kind"),
    ("lock", "unstable-snapshot"),
])
def test_r2_final_local_state_mutations_refuse(tmp_path, mutation, expected_code):
    root = _r1_root(tmp_path)
    sel = _parse_sel(_sel_obj())
    ex = _parse_exec(_exec_obj())
    base = _write(root, "pm", PM_REF, SELECTION_JSON, EXECUTION_JSON)
    encoded = m.encode_local_ref(PM_REF)
    sel_path = base / (encoded + ".json")
    exec_path = base / (encoded + ".execution.json")
    shared = _r1_shared_lock(root)

    class FinalMutator(FakeAdapter):
        def __init__(self, ctx):
            super().__init__(ctx, _evidence_for(ex))
            self.calls = 0
            self.verifier_calls = 0

        def current_context(self):
            self.calls += 1
            if self.calls == 2:
                if mutation == "selection-bytes":
                    obj = _sel_obj()
                    obj["basis_digest"] = "sha256:CHANGED"
                    sel_path.write_text(json.dumps(obj), encoding="utf-8")
                elif mutation == "execution-bytes":
                    obj = _exec_obj()
                    obj["observed_effect"] = "changed during final context"
                    exec_path.write_text(json.dumps(obj), encoding="utf-8")
                elif mutation == "execution-kind":
                    exec_path.unlink()
                    exec_path.mkdir()
                else:
                    shared.parent.mkdir(parents=True, exist_ok=True)
                    shared.write_text("busy", encoding="utf-8")
            return self.ctx

        def verify_execution(self, record, target_digest):
            self.verifier_calls += 1
            return self.evidence

    adapter = FinalMutator(_ctx_from(sel))
    r = m.strict_verify(root, KEY, "pm", PM_REF, which="execution", adapter=adapter)
    assert not r.host_source_verified, r.failure_codes
    assert expected_code in r.failure_codes, r.failure_codes
    assert adapter.calls == 2, "final host callback must be last"
    assert adapter.verifier_calls == 1, "final checks must not call the host verifier again"
    if mutation == "lock":
        assert shared.read_text(encoding="utf-8") == "busy", "reader must not remove a lock"
    if mutation == "execution-kind":
        assert exec_path.is_dir(), "reader must not repair an invalid-existing target"


# ── T03-R3 RV1 reader regressions (PM isolated red reproduction) ───────────
# Only the two reproduced L0/L1 interface gaps: a direct object with
# int/tuple/None dict keys must be a structural rejection, and a trusted
# parent must obey the frozen DecisionRef discriminator on BOTH the first and
# the final context. Legal dp parents and normal string-key diagnostics stay.

_R3_PARSERS = (
    ("parse_host_binding", m.parse_host_binding, _sel_obj()["host_binding"]),
    ("parse_local_selection_record", m.parse_local_selection_record, _sel_obj()),
    ("parse_local_execution_record", m.parse_local_execution_record, _exec_obj()),
    ("validate_matter_budget", m.validate_matter_budget, _live_budget()),
)


@pytest.mark.parametrize("parser_name,parser,valid", _R3_PARSERS)
@pytest.mark.parametrize("bad_key", [1, (1, "x"), None])
def test_r3_direct_object_non_string_keys_are_structural_rejections(parser_name, parser, valid, bad_key):
    positive = parser(dict(valid))
    assert positive.ok and positive.verification == "shape-only"
    assert positive.host_source_verified is False and positive.authority_required is False

    empty_bad = parser({bad_key: "x"})
    full_obj = dict(valid)
    full_obj[bad_key] = "x"
    full_bad = parser(full_obj)
    for result in (empty_bad, full_bad):
        assert result.ok is False, (parser_name, bad_key, result.issues)
        assert result.authority_required is False
        assert result.host_source_verified is False and result.verification == "shape-only"
        assert any("dict keys must be JSON strings" in i.rule for i in result.issues), \
            (parser_name, bad_key, result.issues)

    unknown = dict(valid)
    unknown["surprise"] = "x"
    string_result = parser(unknown)
    assert string_result.ok is False
    assert any(i.rule == "not a declared schema v1 field" for i in string_result.issues)
    assert not any("dict keys must be JSON strings" in i.rule for i in string_result.issues)


class _R3CountingAdapter(FakeAdapter):
    """Test-only trusted-context fake: counts host callbacks and can supply a
    different context on the second (final) callback. No production wiring."""

    def __init__(self, ctx, final_ctx=None):
        super().__init__(ctx)
        self.final_ctx = final_ctx
        self.calls = 0

    def current_context(self):
        self.calls += 1
        if self.calls == 2 and self.final_ctx is not None:
            return self.final_ctx
        return self.ctx


def _r3_parent_selection_obj() -> dict:
    obj = _sel_obj()
    obj["parent_decision_ref"] = {"kind": "dp", "decision_id": "dp:parent:1"}
    return obj


def test_r3_exact_dp_parent_positive_control(tmp_path):
    root = _r1_root(tmp_path)
    obj = _r3_parent_selection_obj()
    sel = _parse_sel(obj)
    _write(root, "pm", PM_REF, json.dumps(obj))
    ctx = _ctx_from(sel)
    adapter = _R3CountingAdapter(ctx)
    r = m.strict_verify(root, KEY, "pm", PM_REF, adapter=adapter)
    assert r.ok and r.host_source_verified is True, r.failure_codes
    assert r.verification == "strict-verified" and r.authority_required is False
    assert adapter.calls == 2, "final host callback must be last"
    parsed = m.parse_decision_ref(ctx.parent_decision_ref)
    assert parsed.ok and isinstance(parsed.value, m.DpDecisionRef)
    assert parsed.value.decision_id == "dp:parent:1"


_R3_BAD_STABLE_PARENTS = (
    {"kind": "dp", "decision_id": "dp:parent:1", "local_ref": "local:other"},
    {"kind": "dp", "decision_id": "dp:parent:1", "surprise": "extra"},
    {"kind": "local", "local_ref": "local:other"},
    {"kind": "dp", "decision_id": "dp:parent:OTHER"},
    None,
)


@pytest.mark.parametrize("bad_ref", [
    {"kind": "dp", "decision_id": "dp:parent:1", "local_ref": "local:other"},
    {"kind": "dp", "decision_id": "dp:parent:1", "surprise": "extra"},
    {"kind": "dp", "decision_id": "dp:parent:1", 7: "x"},
    {"kind": "local", "local_ref": "local:other"},
    None,
])
def test_r3_frozen_parser_rejects_malformed_parent_shapes(bad_ref):
    parsed = m.parse_decision_ref(bad_ref)
    assert not (parsed.ok and isinstance(parsed.value, m.DpDecisionRef)), (bad_ref, parsed)


@pytest.mark.parametrize("bad_parent", _R3_BAD_STABLE_PARENTS)
def test_r3_stable_bad_trusted_parent_refuses(tmp_path, bad_parent):
    root = _r1_root(tmp_path)
    obj = _r3_parent_selection_obj()
    sel = _parse_sel(obj)
    _write(root, "pm", PM_REF, json.dumps(obj))
    ctx = replace(_ctx_from(sel), parent_decision_ref=bad_parent)
    adapter = _R3CountingAdapter(ctx)
    r = m.strict_verify(root, KEY, "pm", PM_REF, adapter=adapter)
    assert not r.host_source_verified and "parent-drift" in r.failure_codes, r.failure_codes
    assert r.authority_required is False
    assert adapter.calls == 1, "an initial bad parent must not run a final host callback"


_R3_BAD_FINAL_PARENTS = (
    {"kind": "dp", "decision_id": "dp:parent:1", "local_ref": "local:other"},
    {"kind": "dp", "decision_id": "dp:parent:1", "surprise": "extra"},
    {"kind": "local", "local_ref": "local:other"},
    None,
)


@pytest.mark.parametrize("final_parent", _R3_BAD_FINAL_PARENTS)
def test_r3_final_context_bad_parent_refuses(tmp_path, final_parent):
    root = _r1_root(tmp_path)
    obj = _r3_parent_selection_obj()
    sel = _parse_sel(obj)
    _write(root, "pm", PM_REF, json.dumps(obj))
    ctx = _ctx_from(sel)
    final_ctx = replace(ctx, parent_decision_ref=final_parent)
    adapter = _R3CountingAdapter(ctx, final_ctx=final_ctx)
    r = m.strict_verify(root, KEY, "pm", PM_REF, adapter=adapter)
    assert not r.host_source_verified, r.failure_codes
    assert "parent-drift" in r.failure_codes, r.failure_codes
    assert "context-drift" in r.failure_codes, r.failure_codes
    assert r.authority_required is False
    assert adapter.calls == 2, "final host callback must be last"
