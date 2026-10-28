"""test_decision_required_refusal.py — required-refusal zero snapshot, on the
T01 four-part dp25 contract.

Two narrow defects are pinned here, both found by the independent T05h review
(``N1``/``N5``) and re-anchored on the new material contract:

* **N1** — a required field that is *missing*, ``null`` or blank is refused at
  step 5 with ``input-incomplete``, but that branch called
  ``capture.remember_state`` **without** setting ``material_refused``, so the
  refused candidate was still written as a ``book-snapshot`` with a
  ``book_ref``. The typed contract (step 5b) and the observation book (step 6b)
  already refuse with zero snapshot; the required branch was the odd one out.
  The rule pinned here is: refused material is never stored, while the
  ``decision-end`` fact (status / reason / no archive) is kept. Authorization,
  the budget and the *legal* oversize candidate retention are unchanged.
* **N5** — the retired dp25 ``p0_open`` array used to declare no
  ``item_type`` / ``max_items`` / ``item_max_bytes``, so ``[1]``, 33 elements and
  a 129-byte element passed the typed gate and the book. T01 replaced that field
  with the four-part material: ``verification_evidence.verified`` /
  ``verification_evidence.unverified`` / ``unfinished_impact`` are free-text
  evidence arrays that declare ``item_type: string`` and ``empty_is_value`` but
  deliberately no per-array cap. The honest boundary is the single published
  material budget (``decision_points.MAX_STATE_BYTES`` = 8192B): an over-budget
  array is refused WHOLE as ``input-oversize`` with zero POST and zero
  truncation, while 33 short items / one 129-byte item stay legal (no invented
  cap is reintroduced). Wrong types and blank items still refuse at the typed
  gate.

Hermetic: tmp projects, tmp ``HOME``/``USERPROFILE``, a tmp ``auth.json`` path,
every credential-shaped env var removed, a read spy installed *before* the
resolution it observes, ``decision.FakeBackend``, isolated test scopes, no
network, no real credentials, no production archive.
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
CASES_DIR = PACKAGE_DIR / "decide_cases"
REGISTRY_JSON = PACKAGE_DIR / "decide_registry.json"
GENERATED_TS = (
    PACKAGE_DIR.parent
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "decide-registry.generated.ts"
)

DP25 = "dp25-signoff-conclusion"
KEY = "k-t05k"
SUB = "sub-t05k"
#: A value that must never be stored once the material it lives in is refused.
MATERIAL_MARKER = "marker-t05k-refused-material"
#: Synthetic tmp credential; never a real one.
SYNTHETIC_KEY = "sk-t05k-synthetic-0123456789abcdef"
DP25_ARRAYS = (
    "unfinished_impact",
    "verification_evidence.unverified",
    "verification_evidence.verified",
)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    """No ambient credential, no real home, no real auth file."""
    for name in tuple(os.environ):
        if name.upper().endswith(decision._CRED_ENV_SUFFIXES):
            monkeypatch.delenv(name, raising=False)
    leftover = [
        name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)
    ]
    assert leftover == [], f"ambient credential env vars survived: {leftover}"
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(
        db, "_auth_json_path", lambda: home / ".pi" / "agent" / "auth.json"
    )
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Hermetic helpers (the shipped four-part case is the real material)
# ---------------------------------------------------------------------------


def _redactor(extra: tuple[str, ...] = ()) -> object:
    redactor = decision.credential_redactor(
        extra_secrets=extra,
        env={},
        auth_path=pathlib.Path("no-such-auth.json"),
    )
    assert redactor is not None, "the side ledger module must be importable in tests"
    return redactor


def _scope(root: pathlib.Path, extra: tuple[str, ...] = ()):
    return decision_wire.test_scope(
        root,
        project_id=decision_wire.project_id_for(root),
        submission_id=SUB,
        redact=_redactor(extra),
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )


def _rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _of_kind(path: pathlib.Path, kind: str) -> list[dict]:
    return [row for row in _rows(path) if row.get("kind") == kind]


def _snapshot_body(event: dict) -> dict:
    text = (event.get("book") or {}).get("text")
    assert isinstance(text, str) and text, f"no snapshot text in {event}"
    return json.loads(text)


def _real_state() -> dict:
    doc = json.loads((CASES_DIR / "dp25.json").read_text(encoding="utf-8"))
    return copy.deepcopy(doc["book"]["state"])


def _book(state: dict) -> dict:
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": DP25,
        "state": state,
        "notes": {
            "evidence": {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[DP25]}
        },
    }


def _ok() -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers={"q-conclusion": {"value": "continue", "confidence": 0.9}},
        latency_ms=2,
        detail="",
    )


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "proj"
    project.mkdir()
    return project


def _decide(
    project: pathlib.Path,
    root: pathlib.Path,
    state: dict,
    *,
    mode: str,
    extra_secrets: tuple[str, ...] = (),
):
    """Run one dp25 decision in ``plain`` / ``observation`` / ``book`` mode."""
    assert mode in ("plain", "observation", "book")
    scope = _scope(root, extra_secrets)
    backend = decision.FakeBackend([_ok()])
    client = decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=True), backend=backend, wire_scope=scope
    )
    observation = None
    if mode != "plain":
        observation = dpts.Observation(
            scope=scope,
            book=_book(state) if mode == "book" else None,
            submission_id=SUB,
        )
    outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=observation,
    )
    return outcome, backend, decision_wire.test_wire_sink(root)


# ---------------------------------------------------------------------------
# N5: the registry declares the honest boundary (one authority, no hand copy)
# ---------------------------------------------------------------------------


def test_dp25_arrays_declare_the_honest_boundary() -> None:
    exported_doc = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    exported_point = {row["id"]: row for row in exported_doc["points"]}[DP25]
    exported_fields = {
        row["name"]: row for row in exported_point["required_state_fields"]
    }
    for path in DP25_ARRAYS:
        spec = dpts.STATE_FIELD_DESCRIPTIONS[path]
        assert spec["type"] == "array", path
        assert spec["item_type"] == "string", path
        # T05h's field-level rule is untouched: [] stays a real value.
        assert spec["empty_is_value"] is True, path
        # No invented per-array cap: free-text evidence is bounded by the whole
        # material budget (MAX_STATE_BYTES), which refuses instead of truncating.
        assert "max_items" not in spec, path
        assert "item_max_bytes" not in spec, path
        assert "enum" not in spec, path

        exported = dpts.snapshot_field_dict(path)
        assert exported["item_type"] == "string", path
        assert exported["empty_is_value"] is True, path
        assert "max_items" not in exported, path
        assert "item_max_bytes" not in exported, path

        registry_row = exported_fields[path]
        assert registry_row["item_type"] == "string", path
        assert registry_row["empty_is_value"] is True, path
        assert "max_items" not in registry_row, path


def test_generated_ts_mirror_carries_the_same_contract() -> None:
    text = GENERATED_TS.read_text(encoding="utf-8")
    for path in DP25_ARRAYS:
        start = text.index(f'name: "{path}"')
        block = text[start : text.index("},", start)]
        assert 'itemType: "string"' in block, (path, block)
        assert "emptyIsValue: true" in block, (path, block)
        assert "maxItems" not in block, (path, block)
        assert "itemMaxBytes" not in block, (path, block)


def test_real_four_part_material_fits_the_registry(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    state = _real_state()
    assert dpts.state_field_issues(DP25, state) == ()
    assert dpts.state_unknown_key_issues(DP25, state, allow_context=True) == ()
    assert books.check_book(_book(state), project_dir=project) == []


# ---------------------------------------------------------------------------
# N5: illegal arrays refuse with zero send / zero snapshot; legal ones do not
# ---------------------------------------------------------------------------


ILLEGAL_DP25_ARRAYS = (
    ("integer-items", "verification_evidence.verified", [1]),
    ("null-item", "verification_evidence.verified", [None]),
    ("object-item", "verification_evidence.verified", [{}]),
    ("empty-item", "verification_evidence.verified", [""]),
    ("not-an-array", "unfinished_impact", {"x": 1}),
    ("string-value", "verification_evidence.unverified", "no"),
)


@pytest.mark.parametrize(
    ("case", "path", "value"),
    ILLEGAL_DP25_ARRAYS,
    ids=[item[0] for item in ILLEGAL_DP25_ARRAYS],
)
def test_illegal_dp25_arrays_refuse_with_zero_send_and_zero_snapshot(
    case: str, path: str, value: object, tmp_path: pathlib.Path
) -> None:
    project = _project(tmp_path)
    state = _real_state()
    dpts._set_path(state, path, value)

    issues = dpts.state_field_issues(DP25, state)
    assert issues, f"{case}: the typed contract must bind this value"
    assert any(
        issue_path == path or issue_path.startswith(f"{path}[")
        for issue_path, _detail in issues
    ), (case, issues)
    # The book agrees with the seam (one authority, no second schema).
    assert any(
        issue.path == f"state.{path}" or issue.path.startswith(f"state.{path}[")
        for issue in books.check_book(_book(state), project_dir=project)
    ), case

    for mode in ("plain", "book"):
        root = tmp_path / f"run-{case}-{mode}"
        outcome, backend, sink = _decide(project, root, state, mode=mode)
        assert outcome.escalated_reason == "input-incomplete", (case, mode, outcome.detail)
        assert path in outcome.detail, (case, mode, outcome.detail)
        assert backend.calls == [], f"{case}/{mode}: illegal material reached the transport"
        assert _of_kind(sink, "book-snapshot") == [], f"{case}/{mode}: illegal material stored"
        ends = _of_kind(sink, "decision-end")
        assert len(ends) == 1, (case, mode, ends)
        assert ends[0]["book_ref"] is None, (case, mode, ends[0])
        assert ends[0]["status"] == "escalated"
        assert outcome.snapshot_ref is None


LEGAL_DP25_ARRAYS = (
    ("empty-verified", "verification_evidence.verified", []),
    ("empty-unfinished", "unfinished_impact", []),
    ("real-item", "unfinished_impact", ["documented follow-up: no delivery impact"]),
    ("many-33", "unfinished_impact", [f"item-{index}" for index in range(33)]),
    ("long-129", "verification_evidence.verified", ["x" * 129]),
)


@pytest.mark.parametrize(
    ("case", "path", "value"),
    LEGAL_DP25_ARRAYS,
    ids=[item[0] for item in LEGAL_DP25_ARRAYS],
)
def test_legal_dp25_arrays_still_send_and_snapshot(
    case: str, path: str, value: object, tmp_path: pathlib.Path
) -> None:
    """``[]``, real items, 33 short items and a 129-byte item stay legal.

    The retired T05h caps are not reintroduced; the whole-material budget is the
    only boundary (pinned by the over-budget case below).
    """
    project = _project(tmp_path)
    state = _real_state()
    dpts._set_path(state, path, value)
    assert dpts.state_field_issues(DP25, state) == (), case
    assert books.check_book(_book(state), project_dir=project) == [], case
    root = tmp_path / f"run-{case}"
    outcome, backend, sink = _decide(project, root, state, mode="book")
    assert outcome.status == "suggested", (case, outcome.detail)
    assert len(backend.calls) == 1, case
    sent = backend.calls[0]["state"]
    assert dpts._lookup(sent, path) == value, case
    snapshots = _of_kind(sink, "book-snapshot")
    assert len(snapshots) == 1, (case, snapshots)
    assert _snapshot_body(snapshots[0])["state"] == sent
    assert snapshots[0]["book_ref"] == outcome.snapshot_ref


def test_over_budget_material_is_refused_whole_without_truncation(
    tmp_path: pathlib.Path,
) -> None:
    """The honest N5 boundary: the published 8192B material budget."""
    project = _project(tmp_path)
    state = _real_state()
    state["unfinished_impact"] = ["x" * 9000]
    assert dpts.state_field_issues(DP25, state) == ()
    root = tmp_path / "run-oversize"
    outcome, backend, sink = _decide(project, root, state, mode="book")

    assert outcome.escalated_reason == "input-oversize", outcome.detail
    assert f"> {dpts.MAX_STATE_BYTES}B" in outcome.detail, outcome.detail
    assert backend.calls == [], "over-budget material must never reach the transport"
    assert list(outcome.truncated or ()) == [], "the material is never truncated"
    snapshots = _of_kind(sink, "book-snapshot")
    assert len(snapshots) == 1, "an oversize candidate is legal material, kept for the human"
    assert _snapshot_body(snapshots[0])["state"] == dpts.model_state_for(DP25, state)


# ---------------------------------------------------------------------------
# N1: a required refusal stores no snapshot, the decision-end fact stays
# ---------------------------------------------------------------------------


def _defect(case: str, state: dict) -> str:
    """Apply one required-field defect and return the field the refusal must name."""
    # The marker rides a LEGAL field: it must not reach the ledger when the
    # material is refused for a different required path.
    state["delivery_goal"] = MATERIAL_MARKER
    if case == "missing":
        state.pop("unfinished_impact")
        return "unfinished_impact"
    if case == "null":
        state["verification_evidence"]["verified"] = None
        return "verification_evidence.verified"
    assert case == "blank"
    state["actual_completion"] = "   "
    return "actual_completion"


@pytest.mark.parametrize("case", ["missing", "null", "blank"])
@pytest.mark.parametrize("mode", ["plain", "observation", "book"])
def test_required_refusal_stores_no_snapshot_and_keeps_the_decision_end_fact(
    case: str, mode: str, tmp_path: pathlib.Path
) -> None:
    project = _project(tmp_path)
    state = _real_state()
    field = _defect(case, state)
    root = tmp_path / f"run-{case}-{mode}"

    outcome, backend, sink = _decide(project, root, state, mode=mode)

    assert outcome.escalated_reason == "input-incomplete", (case, mode, outcome.detail)
    assert field in outcome.detail, (case, mode, outcome.detail)
    assert backend.calls == [], f"{case}/{mode}: refused material reached the transport"
    assert _of_kind(sink, "book-snapshot") == [], (
        f"{case}/{mode}: the refused candidate was stored as a snapshot"
    )
    ends = _of_kind(sink, "decision-end")
    assert len(ends) == 1, (case, mode, ends)
    assert ends[0]["status"] == "escalated"
    assert ends[0]["escalated_reason"] == "input-incomplete"
    assert ends[0]["book_ref"] is None, (case, mode, ends[0])
    assert ends[0]["archive"] in (None, "not-attempted"), (case, mode, ends[0])
    assert outcome.snapshot_ref is None
    # The refused candidate's own material is nowhere in the ledger.
    assert MATERIAL_MARKER not in sink.read_text(encoding="utf-8"), (case, mode)


def test_required_refusal_and_typed_refusal_share_the_same_ledger_shape(
    tmp_path: pathlib.Path,
) -> None:
    """The two refusal gates differ in the message, not in what they store."""
    project = _project(tmp_path)
    required = _real_state()
    required.pop("unfinished_impact")
    typed = _real_state()
    typed["verification_evidence"]["verified"] = "no"

    shapes = []
    for label, state in (("required", required), ("typed", typed)):
        root = tmp_path / f"run-{label}"
        outcome, backend, sink = _decide(project, root, state, mode="book")
        assert outcome.escalated_reason == "input-incomplete", label
        assert backend.calls == []
        shapes.append([row.get("kind") for row in _rows(sink)])
        assert _of_kind(sink, "book-snapshot") == [], label
    assert shapes[0] == shapes[1] == ["decision-end"], shapes


def test_required_refusal_never_reads_or_stores_a_real_credential(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read spy is installed before the resolution it observes.

    The only credential that exists is the synthetic tmp ``auth.json``; the
    refused call must resolve exactly that (spy evidence) and the refused
    material plus its credential must never reach the ledger or the detail.
    """
    auth_path = pathlib.Path(os.environ["HOME"]) / ".pi" / "agent" / "auth.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    nested: dict = {db.TIMI_AUTH_FIELD[-1]: SYNTHETIC_KEY}
    for part in reversed(db.TIMI_AUTH_FIELD[:-1]):
        nested = {part: nested}
    auth_path.write_text(json.dumps(nested), encoding="utf-8", newline="\n")

    original = db.resolve_timi_api_key
    calls: list[object] = []

    def spy(env: dict | None = None, auth_path: pathlib.Path | None = None):
        value = original(env, auth_path)
        if env is None and auth_path is None:
            # A real ambient resolution (the seam's own), not the test redactor
            # built from an explicit env/path.
            calls.append(value)
        return value

    monkeypatch.setattr(db, "resolve_timi_api_key", spy)

    project = _project(tmp_path)
    state = _real_state()
    field = _defect("missing", state)
    root = tmp_path / "run-spy"
    outcome, backend, sink = _decide(
        project, root, state, mode="book", extra_secrets=(SYNTHETIC_KEY,)
    )

    assert calls, "the seam resolved no credential at all: the spy never saw the read"
    assert calls == [SYNTHETIC_KEY], (
        "the refusal must freeze the one tmp credential, never a second/real one: "
        f"{calls}"
    )
    assert outcome.escalated_reason == "input-incomplete"
    assert field in outcome.detail
    assert backend.calls == []
    text = sink.read_text(encoding="utf-8")
    assert SYNTHETIC_KEY not in text
    assert SYNTHETIC_KEY not in outcome.detail
    assert _of_kind(sink, "book-snapshot") == []
    assert _of_kind(sink, "decision-end")[0]["book_ref"] is None
