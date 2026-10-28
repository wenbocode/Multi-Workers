"""test_decision_required_refusal.py — card T05k: required-refusal zero snapshot
and the dp25 ``p0_open`` typed array contract.

Two narrow defects are pinned here, both found by the independent T05h review
(``N1``/``N5``) rather than introduced by this card:

* **N1** — a required field that is *missing*, ``null`` or blank is refused at
  step 5 with ``input-incomplete``, but that branch called
  ``capture.remember_state`` **without** setting ``material_refused``, so the
  refused candidate was still written as a ``book-snapshot`` with a
  ``book_ref``. The typed contract (step 5b) and the observation book (step 6b)
  already refuse with zero snapshot; the required branch was the odd one out.
  The rule pinned here is: refused material is never stored, while the
  ``decision-end`` fact (status / reason / no archive) is kept. Authorization,
  the budget and the *legal* oversize candidate retention are unchanged.
* **N5** — ``dp25-signoff-conclusion``'s required ``p0_open`` array declared no
  ``item_type`` / ``max_items`` / ``item_max_bytes``, so ``[1]``, 33 elements and
  a 129-byte element passed both the typed gate and the book. The real producer
  (``decide_signoff._p0_open``) writes ``sorted`` P0 dp-id strings (10 of them
  today, max 19 B), so the unified array boundary (32 items / string / 128 B)
  fits with headroom. ``empty_is_value`` stays: ``[]`` is still the real "no P0
  open" value. No enum is invented — the field stays an open dp-id string list.

Hermetic: tmp projects, tmp ``HOME``/``USERPROFILE``, a tmp ``auth.json`` path,
every credential-shaped env var removed, a read spy installed *before* the
resolution it observes, ``decision.FakeBackend``, isolated test scopes, no
network, no real credentials, no production archive.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
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
# Hermetic helpers (real producer state, never a hand-written guess)
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


def _signoff_project(
    tmp_path: pathlib.Path, *, enable_p0: bool = False
) -> pathlib.Path:
    """A tmp AgenticTask key with one real archive row (the dp25 producer input)."""
    project = tmp_path / "proj"
    (project / ".agenticdoc" / KEY / "evidence" / "review").mkdir(parents=True)
    if enable_p0:
        path = project / ".mw" / "decide-points.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        table = {
            "version": 1,
            "points": {
                point.id: {"enabled": True} for point in dpts.DP_REGISTRY if point.tier == "P0"
            },
        }
        path.write_text(json.dumps(table) + "\n", encoding="utf-8", newline="\n")
        dpts.clear_points_config_cache()
    decide_archive.append_decide(
        decide_signoff.archive_path(project),
        available=True,
        reason=None,
        answer={"x": {"value": 1}},
        authority="binding",
        escalated_reason=None,
        acted=True,
        actual_action="steer",
        dp="dp3-worker-clarify",
        key=KEY,
        task_key="task-1",
        trigger_id="t1",
        state={"schema_version": 2, "decision_point": "dp3-worker-clarify"},
        questions_version="q-0123abcd",
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    return project


def real_state(tmp_path: pathlib.Path, *, enable_p0: bool = False) -> tuple[pathlib.Path, dict]:
    project = _signoff_project(tmp_path, enable_p0=enable_p0)
    return project, decide_signoff.signoff_state(decide_signoff.collect(project, KEY), KEY)


def _book(state: dict) -> dict:
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": DP25,
        "state": state,
        "notes": {
            "evidence": {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[DP25]}
        },
    }


def _ok(_answers: dict | None = None) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers={"q-conclusion": {"value": "continue", "confidence": 0.9}},
        latency_ms=2,
        detail="",
    )


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
# N5: the registry declares the array shape (one authority, no hand-written copy)
# ---------------------------------------------------------------------------


def test_p0_open_declares_the_unified_array_bounds() -> None:
    spec = dpts.STATE_FIELD_DESCRIPTIONS["p0_open"]
    assert spec["type"] == "array"
    assert spec["max_items"] == dpts.STATE_ARRAY_MAX_ITEMS == 32
    assert spec["item_type"] == "string"
    assert spec["item_max_bytes"] == dpts.STATE_ARRAY_ITEM_MAX_BYTES == 128
    # T05h's field-level rule is untouched: [] stays the producer's real value.
    assert spec["empty_is_value"] is True
    # No invented closed set: the elements are dp ids, not an enum.
    assert "enum" not in spec

    exported = dpts.snapshot_field_dict("p0_open")
    assert exported["max_items"] == 32
    assert exported["item_type"] == "string"
    assert exported["item_max_bytes"] == 128
    assert exported["empty_is_value"] is True

    doc = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    point = {row["id"]: row for row in doc["points"]}[DP25]
    field = {row["name"]: row for row in point["required_state_fields"]}["p0_open"]
    assert field["max_items"] == 32
    assert field["item_type"] == "string"
    assert field["item_max_bytes"] == 128
    assert field["empty_is_value"] is True


def test_generated_ts_mirror_carries_the_same_bounds() -> None:
    text = GENERATED_TS.read_text(encoding="utf-8")
    start = text.index('name: "p0_open"')
    block = text[start : text.index("},", start)]
    assert "maxItems: 32" in block, block
    assert 'itemType: "string"' in block, block
    assert "itemMaxBytes: 128" in block, block
    assert "emptyIsValue: true" in block, block


def test_real_p0_producer_fits_the_declared_bounds(tmp_path: pathlib.Path) -> None:
    """The producer writes sorted registry P0 ids; they must fit with headroom."""
    ids = sorted(point.id for point in dpts.DP_REGISTRY if point.tier == "P0")
    assert all(isinstance(dp_id, str) and dp_id for dp_id in ids)
    assert len(ids) <= 25, f"the card's producer bound is <=25 P0 ids, got {len(ids)}"
    assert len(ids) <= dpts.STATE_ARRAY_MAX_ITEMS
    assert max(len(dp_id.encode("utf-8")) for dp_id in ids) <= dpts.STATE_ARRAY_ITEM_MAX_BYTES

    project, state = real_state(tmp_path, enable_p0=True)
    assert state["p0_open"] == ids, "the real producer writes the sorted P0 id list"
    assert dpts.state_field_issues(DP25, state) == ()
    assert books.check_book(_book(state), project_dir=project) == []


# ---------------------------------------------------------------------------
# N5: illegal arrays refuse with zero send / zero snapshot; legal ones do not
# ---------------------------------------------------------------------------


ILLEGAL_P0_OPEN = (
    ("integer-items", [1]),
    ("null-item", [None]),
    ("object-item", [{}]),
    ("empty-item", [""]),
    ("too-many", [f"dp{index}-item" for index in range(33)]),
    ("item-too-long", ["x" * 129]),
)


@pytest.mark.parametrize(
    ("case", "value"), ILLEGAL_P0_OPEN, ids=[item[0] for item in ILLEGAL_P0_OPEN]
)
def test_illegal_p0_open_arrays_refuse_with_zero_send_and_zero_snapshot(
    case: str, value: object, tmp_path: pathlib.Path
) -> None:
    project, real = real_state(tmp_path)
    state = dict(real)
    state["p0_open"] = value

    issues = dpts.state_field_issues(DP25, state)
    assert issues, f"{case}: the typed contract must bind this value"
    assert any(
        path == "p0_open" or path.startswith("p0_open[") for path, _detail in issues
    ), (case, issues)
    # The book agrees with the seam (one authority, no second schema).
    assert any(
        issue.path == "state.p0_open" or issue.path.startswith("state.p0_open[")
        for issue in books.check_book(_book(state), project_dir=project)
    ), case

    for mode in ("plain", "book"):
        root = tmp_path / f"run-{case}-{mode}"
        outcome, backend, sink = _decide(project, root, state, mode=mode)
        assert outcome.escalated_reason == "input-incomplete", (case, mode, outcome.detail)
        assert "p0_open" in outcome.detail, (case, mode, outcome.detail)
        assert backend.calls == [], f"{case}/{mode}: illegal material reached the transport"
        assert _of_kind(sink, "book-snapshot") == [], f"{case}/{mode}: illegal material stored"
        ends = _of_kind(sink, "decision-end")
        assert len(ends) == 1, (case, mode, ends)
        assert ends[0]["book_ref"] is None, (case, mode, ends[0])
        assert ends[0]["status"] == "escalated"
        assert outcome.snapshot_ref is None


def test_legal_p0_open_values_still_send_and_snapshot(tmp_path: pathlib.Path) -> None:
    """``[]`` (no open P0) and a real dp-id list must not be degraded by N5."""
    project, real = real_state(tmp_path)
    for label, value in (("empty", []), ("real-id", ["dp8-scope-change"])):
        state = dict(real)
        state["p0_open"] = value
        assert dpts.state_field_issues(DP25, state) == (), label
        assert books.check_book(_book(state), project_dir=project) == [], label
        root = tmp_path / f"run-{label}"
        outcome, backend, sink = _decide(project, root, state, mode="book")
        assert outcome.status == "suggested", (label, outcome.detail)
        assert len(backend.calls) == 1, label
        assert backend.calls[0]["state"]["p0_open"] == value
        snapshots = _of_kind(sink, "book-snapshot")
        assert len(snapshots) == 1, (label, snapshots)
        assert _snapshot_body(snapshots[0])["state"] == state
        assert snapshots[0]["book_ref"] == outcome.snapshot_ref


# ---------------------------------------------------------------------------
# N1: a required refusal stores no snapshot, the decision-end fact stays
# ---------------------------------------------------------------------------


def _defect(case: str, state: dict) -> str:
    """Apply one required-field defect and return the field the refusal must name."""
    state["escalated_reasons"] = [MATERIAL_MARKER]
    if case == "missing":
        state.pop("p0_open")
        return "p0_open"
    if case == "null":
        state["p0_open"] = None
        return "p0_open"
    assert case == "blank"
    state["key"] = "   "
    return "key"


@pytest.mark.parametrize("case", ["missing", "null", "blank"])
@pytest.mark.parametrize("mode", ["plain", "observation", "book"])
def test_required_refusal_stores_no_snapshot_and_keeps_the_decision_end_fact(
    case: str, mode: str, tmp_path: pathlib.Path
) -> None:
    project, real = real_state(tmp_path)
    state = dict(real)
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
    project, real = real_state(tmp_path)

    required = dict(real)
    required.pop("p0_open")
    typed = dict(real)
    typed["p0_open"] = [1]

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

    project, real = real_state(tmp_path)
    state = dict(real)
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
