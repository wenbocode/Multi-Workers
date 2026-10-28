"""T10 R2 stage C boundary regressions: the real writer, the real lock, the real guard.

This file is *evidence*, not product code, and it is deliberately outside
``implementation-worktree``: the isolated mirror, its 14 ``.pyc`` files and the
two assigned suites must stay byte-identical, so the additional boundary
contracts live in their own suite with their own ``--basetemp``.

Scope of the appended contracts (original AC/VC are not replaced or reduced):

* AC-052 / VC-052 - replay and concurrent consumption of one event: an
  identical repeat must not add a second fact, two real facts of one request
  must both stay visible, and two writers of the same content must produce one
  row (``duplicate`` with zero bytes) no matter which one wins the append lock;
* AC-050 / VC-050 - a recorded observation is a floor for a *new* fact: an older
  ``task_after`` may not be appended after a newer recorded one, a guard refusal
  is the caller's own input error (no failure sidecar, no fabricated
  ``executed``), and a known-secret-bearing ``before`` may be re-stated exactly
  while any other snapshot is refused;
* the scope/separation controls: the production-path refusal is the *test*
  scope's rule (a production scope is not a substitute), and the suite proves
  at run time that it and the products come from the isolated tree.

Everything below uses the real ``decision_wire.append_event`` (real
``O_CREAT|O_EXCL`` lock, real dedupe scan, real ``guard`` slot) and the real
``decision_lifecycle`` writer. Nothing is stubbed, shadowed, copied or patched
except one *scheduling* wrapper in the two interleaving tests: it only holds a
thread at the append entry (a local barrier/handshake) so that two writers can
be ordered deterministically. The production code under test still runs
unmodified.

Predicted status on the current products is stated per test. **This worker did
not execute any of them** - no pytest, no collection, no product import - so
neither "green" nor "confirmed defect" is claimed here; the PM runs the suite.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import threading

import pytest

import decision_lifecycle as lifecycle
import decision_points
import decision_task_state as task_state
import decision_wire as wire

#: Synthetic, deliberately distinctive value - never a real credential.
SECRET = "Sk-4Rz8Nm2Qx6Tb1Vc9Nd3Hf7Gj5Kp0Ws"

DP = "dp-pm-steer"
PREPARED_AT = "2026-10-27T08:15:00+00:00"
BASIS_TEXT = "the task card already carries the split"
BEFORE_TS = "2026-10-27T08:00:00+00:00"
OLD_TS = "2026-10-27T09:30:00+00:00"
NEW_TS = "2026-10-27T10:00:00+00:00"

#: Every boundary test is expected to pass on the repaired products except the
#: replay item below, which states the AC-052 dedupe contract and is therefore
#: *predicted red* until the writer stops refusing an already-recorded fact.
PREDICTED_RED = (
    "test_a_recorded_fact_replays_as_a_duplicate_after_a_later_observation",
)


# ── real fixtures (real store, injected synthetic redactor) ────────────────


@pytest.fixture()
def redactor() -> wire.SecretRedactor:
    return wire.SubstringRedactor([SECRET])


def _writer(root: pathlib.Path, redactor: wire.SecretRedactor) -> lifecycle.LifecycleStore:
    """A second/third real writer over the same isolated ledger root."""
    return lifecycle.LifecycleStore.test(
        root, project_id="proj-boundary", redact=redactor, warn=lambda line: None
    )


def _meta(**overrides) -> lifecycle.DecisionMeta:
    kwargs: dict[str, object] = {"task_key": "task-a", "initiator_role": "pm"}
    kwargs.update(overrides)
    return lifecycle.DecisionMeta.create(kwargs.pop("key", "mw-boundary"), **kwargs)


def _started(store: lifecycle.LifecycleStore, **overrides) -> lifecycle.DecisionMeta:
    meta = _meta(**overrides)
    assert lifecycle.record_start(store, meta).recorded is True
    return meta


def _decision_id(meta: lifecycle.DecisionMeta) -> str:
    return f"{DP}:{meta.logical_id}"


def _state(
    status: str = "running",
    *,
    source: str = "agent-report",
    observed_at: str = BEFORE_TS,
    completed: object = None,
    remaining: object = None,
    blockers: object = None,
) -> dict[str, object]:
    return {
        "status": status,
        "source": source,
        "observed_at": observed_at,
        "completed": completed,
        "remaining": remaining,
        "blockers": blockers,
    }


def _material() -> dict[str, object]:
    return {
        "task_goal": "ship the split",
        "task_requirements": "keep both files",
        "task_deliverables": "two patches",
    }


def _preparation(choice: str = "narrow") -> dict[str, object]:
    applies = [choice] if choice == "split" else [choice, "split"]
    return {
        "basis_catalog": [
            {
                "id": "b-narrow",
                "text": BASIS_TEXT,
                "material_refs": ["task_goal"],
                "applies_to": applies,
            },
            {
                "id": "b-split",
                "text": "the remaining work is two independent files",
                "material_refs": ["task_requirements"],
                "applies_to": ["split"],
            },
        ],
        "prepared_at": PREPARED_AT,
    }


def _result(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "dp": DP,
        "available": True,
        "replayed": False,
        "choice": "narrow",
        "basis_id": "b-narrow",
        "basis_text": BASIS_TEXT,
        "basis_source": "pm-prepared",
        "prepared_at": PREPARED_AT,
        "reason": None,
        "attempts": 1,
        "transport_attempts": 1,
        "business_decisions": 1,
    }
    base.update(over)
    return base


def _refused_result() -> dict[str, object]:
    """A transport success with zero business decisions: a fact, not an approval."""
    return _result(
        choice=None,
        basis_id=None,
        basis_text=None,
        basis_source=None,
        business_decisions=0,
        reason="bad-response",
        attempts=1,
        transport_attempts=2,
    )


def _split_result() -> dict[str, object]:
    return _result(
        choice="split",
        basis_id="b-split",
        basis_text="the remaining work is two independent files",
    )


def _rows(store: lifecycle.LifecycleStore) -> list[dict[str, object]]:
    return lifecycle.read_lifecycle(store).events


def _raw(store: lifecycle.LifecycleStore) -> bytes:
    return store.sink.read_bytes()


def _error_raw(store: lifecycle.LifecycleStore) -> bytes:
    sink = store.error_sink
    if sink is None or not sink.exists():
        return b""
    return sink.read_bytes()


def _lock_path(store: lifecycle.LifecycleStore) -> pathlib.Path:
    return store.sink.with_name(store.sink.name + ".lock")


def _request_rows(store: lifecycle.LifecycleStore) -> list[dict[str, object]]:
    return [row for row in _rows(store) if row.get("kind") == "request"]


def _after_stamps(store: lifecycle.LifecycleStore) -> list[str]:
    stamps: list[str] = []
    for row in _rows(store):
        snapshot = row.get("task_after")
        if isinstance(snapshot, dict) and isinstance(snapshot.get("observed_at"), str):
            stamps.append(str(snapshot["observed_at"]))
    return stamps


# ── AC-052: two writers of the same request content ───────────────────────


def test_two_writers_recording_the_same_request_add_exactly_one_fact(
    tmp_path, redactor, monkeypatch
) -> None:
    """AC-052 / VC-052: one real fact, the other attempt is a zero-byte duplicate.

    Both writers build their row from the same content, so both derive the same
    content-addressed ``event_id``; the append lock plus the in-lock dedupe scan
    therefore has to produce ``written`` once and ``duplicate`` once. Predicted
    green on the current products (predicted by reading ``record_request`` and
    ``append_event``; not executed here).
    """
    root = tmp_path / "shared-request"
    first_writer = _writer(root, redactor)
    second_writer = _writer(root, redactor)
    meta = _started(first_writer)
    decision_id = _decision_id(meta)

    barrier = threading.Barrier(2, timeout=30)
    real_append = wire.append_event
    outcomes: dict[str, lifecycle.LifecycleResult] = {}
    errors: list[tuple[str, str, str]] = []

    def synced_append(scope, event, **kwargs):
        # Scheduling only: both writers are past their prechecks and enter the
        # real append (real lock, real dedupe, real write) together.
        barrier.wait()
        return real_append(scope, event, **kwargs)

    monkeypatch.setattr(wire, "append_event", synced_append)

    def record(name: str, writer: lifecycle.LifecycleStore) -> None:
        try:
            outcomes[name] = lifecycle.record_request(
                writer,
                meta,
                decision_id=decision_id,
                result=_result(),
                material=_material(),
                preparation=_preparation(),
            )
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append((name, type(exc).__name__, str(exc)))

    threads = [
        threading.Thread(target=record, args=("one", first_writer)),
        threading.Thread(target=record, args=("two", second_writer)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not any(thread.is_alive() for thread in threads), "a boundary writer thread hung"
    assert errors == [], f"a real writer raised instead of reporting a duplicate: {errors}"

    statuses = sorted(result.status for result in outcomes.values())
    assert statuses == ["duplicate", "written"], statuses
    assert len({result.event_id for result in outcomes.values()}) == 1
    rows = _request_rows(first_writer)
    assert len(rows) == 1, f"the same request content produced {len(rows)} rows"
    assert rows[0]["event_id"] in {result.event_id for result in outcomes.values()}
    assert _raw(first_writer).count(b"\n") == len(_rows(first_writer))
    # the first fact is never overwritten by the duplicate attempt
    assert _raw(second_writer) == _raw(first_writer)
    # the real lock is released by both writers
    assert not _lock_path(first_writer).exists()
    assert _error_raw(first_writer) == b""


@pytest.mark.parametrize("second", ["refusal", "different-choice"], ids=["refusal", "split"])
def test_a_second_real_fact_stays_visible_and_grants_no_action(
    tmp_path, redactor, second
) -> None:
    """AC-052: a different fact under the same request is not a silent duplicate.

    Both rows are real request facts, the earlier one keeps its own bytes, and
    neither of them is an executed action, a settlement, a sign-off or a task
    terminal (a request is not an execution permission). Predicted green.
    """
    writer = _writer(tmp_path / "two-facts", redactor)
    meta = _started(writer)
    decision_id = _decision_id(meta)
    first = lifecycle.record_request(
        writer,
        meta,
        decision_id=decision_id,
        result=_refused_result(),
        material=_material(),
        preparation=_preparation(),
    )
    assert first.status == "written" and first.recorded is True
    first_bytes = _raw(writer)

    follow_up = _split_result() if second == "different-choice" else _result()
    again = lifecycle.record_request(
        writer,
        meta,
        decision_id=decision_id,
        result=follow_up,
        material=_material(),
        preparation=_preparation(),
    )
    assert again.status == "written" and again.recorded is True
    assert again.event_id != first.event_id
    assert _raw(writer).startswith(first_bytes)

    rows = _request_rows(writer)
    assert len(rows) == 2, [row.get("choice") for row in rows]
    # the first fact is preserved verbatim: no rewrite of the recorded refusal
    assert rows[0]["business_decisions"] == 0 and rows[0]["reason"] == "bad-response"
    assert rows[0]["choice"] is None and rows[0]["basis_id"] is None
    # the second fact is the real business decision of the same request
    assert rows[1]["business_decisions"] == 1
    assert rows[1]["choice"] in ("narrow", "split")
    # a request fact never becomes an action/settlement/terminal
    assert not any(
        row.get("lifecycle") in ("executed", "settled", "signoff") for row in _rows(writer)
    )
    assert not any(row.get("kind") == "terminal" for row in _rows(writer))


# ── AC-052: replaying an already recorded fact ────────────────────────────


def test_a_recorded_fact_replays_as_a_duplicate_after_a_later_observation(
    tmp_path, redactor
) -> None:
    """AC-052 dedupe contract: a retry of a recorded fact is ``duplicate``.

    The T02 dedupe contract (``decision_lifecycle``/``decision_wire``
    docstrings, spec AC-052) is: deduplication is by ``event_id`` *only*, and a
    caller that retries an ambiguous write reuses the same ``event_id`` and gets
    ``status="duplicate"`` with nothing written and ``recorded`` still true.
    That must not depend on which other observations have been recorded since.

    PREDICTED RED on the current products, by reading the code - not reproduced:
    ``record_lifecycle`` runs ``_recorded_after_floor`` *before* ``_append``,
    and ``append_event`` runs ``guard()`` *before* the ``dedupe_event_id`` scan.
    A replay of the already recorded ``executed`` fact therefore raises
    ``LifecycleInputError`` (its older ``task_after`` now precedes the newer
    recorded one) instead of returning ``duplicate``.

    Root-cause hint for the next writer-side fix (this suite does not change the
    product): the already-present ``event_id`` must be honoured before the
    non-decreasing floor refuses the call - for example by resolving the
    duplicate inside the lock before the guard, or by skipping the floor when the
    event is already recorded. The S5 rule for *new* event ids must stay exactly
    as strict (see the two control tests below).

    This is not a new global id uniqueness or single-terminal rule: it only
    restates the per-``event_id`` idempotency contract that already exists.
    """
    writer = _writer(tmp_path / "replay", redactor)
    before = _state("running", completed=[], remaining=["split the file"], blockers=None)
    meta = _started(writer, task_before=before)
    decision_id = _decision_id(meta)
    executed_after = _state("running", observed_at=OLD_TS)

    first = lifecycle.record_executed(
        writer,
        meta,
        decision_id=decision_id,
        dp=DP,
        action="split",
        result="split the file",
        event_id="boundary-replay-executed",
        task_after=executed_after,
    )
    assert first.status == "written" and first.recorded is True
    settled = lifecycle.record_settled(
        writer,
        meta,
        decision_id=decision_id,
        dp=DP,
        outcome="ok",
        event_id="boundary-replay-settled",
        task_after=_state("done", source="dispatch-result", observed_at=NEW_TS),
    )
    assert settled.status == "written" and settled.recorded is True

    recorded_bytes = _raw(writer)
    recorded_errors = _error_raw(writer)
    replay = lifecycle.record_executed(
        writer,
        meta,
        decision_id=decision_id,
        dp=DP,
        action="split",
        result="split the file",
        event_id="boundary-replay-executed",
        task_after=executed_after,
    )
    assert replay.status == "duplicate", replay.status
    assert replay.recorded is True
    assert replay.event_id == first.event_id
    assert _raw(writer) == recorded_bytes, "a replay appended bytes"
    assert _error_raw(writer) == recorded_errors, "a replay wrote a failure sidecar"
    assert not _lock_path(writer).exists()


def test_a_recorded_fact_replays_as_a_duplicate_before_any_later_observation(
    tmp_path, redactor
) -> None:
    """Control: the same replay is a duplicate while no newer after is recorded.

    This isolates the replay item above: the dedupe hit works today as long as
    the non-decreasing floor cannot fire. Predicted green.
    """
    writer = _writer(tmp_path / "replay-control", redactor)
    before = _state("running", completed=[], remaining=["split the file"], blockers=None)
    meta = _started(writer, task_before=before)
    decision_id = _decision_id(meta)
    executed_after = _state("running", observed_at=OLD_TS)
    first = lifecycle.record_executed(
        writer,
        meta,
        decision_id=decision_id,
        dp=DP,
        action="split",
        result="split the file",
        event_id="boundary-replay-control",
        task_after=executed_after,
    )
    assert first.status == "written"
    recorded_bytes = _raw(writer)
    replay = lifecycle.record_executed(
        writer,
        meta,
        decision_id=decision_id,
        dp=DP,
        action="split",
        result="split the file",
        event_id="boundary-replay-control",
        task_after=executed_after,
    )
    assert replay.status == "duplicate"
    assert replay.recorded is True
    assert _raw(writer) == recorded_bytes


def test_a_new_older_observation_is_still_refused(tmp_path, redactor) -> None:
    """AC-050 control: the S5 floor keeps refusing a *new* older observation.

    Predicted green; together with the replay item this pins that the contract
    fix may not be obtained by relaxing the non-decreasing rule.
    """
    writer = _writer(tmp_path / "floor-control", redactor)
    before = _state("running", completed=[], remaining=["split the file"], blockers=None)
    meta = _started(writer, task_before=before)
    decision_id = _decision_id(meta)
    assert lifecycle.record_settled(
        writer,
        meta,
        decision_id=decision_id,
        dp=DP,
        outcome="ok",
        event_id="boundary-floor-settled",
        task_after=_state("done", source="dispatch-result", observed_at=NEW_TS),
    ).recorded is True
    recorded_bytes = _raw(writer)
    recorded_errors = _error_raw(writer)
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_executed(
            writer,
            meta,
            decision_id=decision_id,
            dp=DP,
            action="continue",
            result="an older observation",
            event_id="boundary-floor-new",
            task_after=_state("done", source="dispatch-result", observed_at=OLD_TS),
        )
    assert _raw(writer) == recorded_bytes
    assert _error_raw(writer) == recorded_errors
    assert not _lock_path(writer).exists()


# ── AC-050: two real writers, controlled interleaving and a real lock race ─


def test_a_newer_recorded_observation_blocks_an_older_append_from_a_second_writer(
    tmp_path, redactor, monkeypatch
) -> None:
    """AC-050/S5: pass the precheck, then lose the race to a newer observation.

    The older writer runs its own (real) non-decreasing precheck while the ledger
    holds only the creation fact, so that precheck passes. It is then held at the
    append entry until the second writer has really recorded its newer
    observation. The real append then runs its real in-lock guard, which must
    refuse: no row, no failure sidecar, a released lock and no fabricated
    ``executed`` fact. Predicted green on the repaired products.

    Only the *scheduling* is wrapped; the guard, the lock, the dedupe scan and
    the append are the production ones.
    """
    root = tmp_path / "controlled-interleave"
    older_writer = _writer(root, redactor)
    newer_writer = _writer(root, redactor)
    before = _state("running", completed=[], remaining=["split the file"], blockers=None)
    meta = _started(older_writer, task_before=before)
    decision_id = _decision_id(meta)

    real_append = wire.append_event
    older_at_gate = threading.Event()
    newer_recorded = threading.Event()
    outcomes: dict[str, lifecycle.LifecycleResult] = {}
    errors: list[tuple[str, str, str]] = []

    def stamp_of(event) -> object:
        snapshot = event.get("task_after") if isinstance(event, dict) else None
        return snapshot.get("observed_at") if isinstance(snapshot, dict) else None

    def gated_append(scope, event, **kwargs):
        if stamp_of(event) == OLD_TS and not newer_recorded.is_set():
            older_at_gate.set()
            if not newer_recorded.wait(30):
                raise AssertionError("the newer writer never recorded its observation")
        else:
            result = real_append(scope, event, **kwargs)
            if stamp_of(event) == NEW_TS:
                newer_recorded.set()
            return result
        return real_append(scope, event, **kwargs)

    monkeypatch.setattr(wire, "append_event", gated_append)

    def record(name: str, writer: lifecycle.LifecycleStore, observed_at: str) -> None:
        try:
            outcomes[name] = lifecycle.record_settled(
                writer,
                meta,
                decision_id=decision_id,
                dp=DP,
                outcome="ok",
                event_id=f"boundary-interleave-{name}",
                task_after=_state(
                    "done", source="dispatch-result", observed_at=observed_at
                ),
            )
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append((name, type(exc).__name__, str(exc)))

    older = threading.Thread(target=record, args=("older", older_writer, OLD_TS))
    older.start()
    assert older_at_gate.wait(30), "the older writer never reached the append entry"
    newer = threading.Thread(target=record, args=("newer", newer_writer, NEW_TS))
    newer.start()
    for thread in (older, newer):
        thread.join(60)
    assert not older.is_alive() and not newer.is_alive(), "a boundary writer thread hung"

    assert outcomes.get("newer") is not None and outcomes["newer"].status == "written"
    assert "older" not in outcomes, "the older observation was accepted after the newer one"
    assert [entry[0] for entry in errors] == ["older"], errors
    assert errors[0][1] == "LifecycleInputError", errors
    stamps = _after_stamps(older_writer)
    assert stamps == [NEW_TS], stamps
    assert OLD_TS not in json.dumps(_rows(older_writer))
    assert _error_raw(older_writer) == b"", "a guard refusal wrote a failure sidecar"
    assert not _lock_path(older_writer).exists(), "the append lock was not released"


def test_two_writers_racing_the_append_lock_never_order_an_older_observation_last(
    tmp_path, redactor, monkeypatch
) -> None:
    """AC-050/S5: whichever writer wins the real lock, file order stays increasing.

    Both writers pass their own precheck and then enter the real append together
    (a local barrier, no fake lock, no sleep). Two outcomes are correct and both
    are asserted: either both facts are recorded in non-decreasing order, or the
    older one is refused by the in-lock guard with zero bytes. What must never
    happen is an older ``task_after`` appended *after* a newer one.
    Predicted green.
    """
    root = tmp_path / "lock-race"
    older_writer = _writer(root, redactor)
    newer_writer = _writer(root, redactor)
    before = _state("running", completed=[], remaining=["split the file"], blockers=None)
    meta = _started(older_writer, task_before=before)
    decision_id = _decision_id(meta)

    barrier = threading.Barrier(2, timeout=30)
    real_append = wire.append_event
    statuses: dict[str, str] = {}
    errors: list[tuple[str, str, str]] = []

    def racing_append(scope, event, **kwargs):
        barrier.wait()
        return real_append(scope, event, **kwargs)

    monkeypatch.setattr(wire, "append_event", racing_append)

    def record(name: str, writer: lifecycle.LifecycleStore, observed_at: str) -> None:
        try:
            statuses[name] = lifecycle.record_settled(
                writer,
                meta,
                decision_id=decision_id,
                dp=DP,
                outcome="ok",
                event_id=f"boundary-race-{name}",
                task_after=_state(
                    "done", source="dispatch-result", observed_at=observed_at
                ),
            ).status
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append((name, type(exc).__name__, str(exc)))

    threads = [
        threading.Thread(target=record, args=("older", older_writer, OLD_TS)),
        threading.Thread(target=record, args=("newer", newer_writer, NEW_TS)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not any(thread.is_alive() for thread in threads), "a boundary writer thread hung"

    stamps = _after_stamps(older_writer)
    assert stamps == sorted(stamps), f"an older observation followed a newer one: {stamps}"
    assert len(stamps) >= 1
    assert len(statuses) + len(errors) == 2
    for name, error_class, _message in errors:
        assert error_class == "LifecycleInputError", (name, error_class)
        # a refused writer appended nothing
        assert statuses.get(name) is None
    if "older" in errors:
        assert OLD_TS not in json.dumps(_rows(newer_writer))
    assert _error_raw(older_writer) == b""
    assert not _lock_path(older_writer).exists(), "the append lock was not released"


# ── AC-050/AC-019: the recorded ``before``, secrets and the exact axes ─────


def test_a_known_secret_before_can_be_restated_and_is_never_stored_raw(
    tmp_path, redactor
) -> None:
    """AC-050 + AC-019: an exact re-statement is legal, the secret is not stored.

    The creation fact stored the redacted representation; the note path re-checks
    a caller's raw snapshot through the same projection, so the exact same axes
    are accepted while the secret never reaches the ledger. Predicted green.
    """
    writer = _writer(tmp_path / "secret-before", redactor)
    before = _state(
        "running", completed=[SECRET + " private step"], remaining=[], blockers=None
    )
    meta = _started(writer, task_before=before)
    decision_id = _decision_id(meta)
    result = lifecycle.record_note(
        writer,
        meta,
        decision_id=decision_id,
        pm_note="matter: split the file; action: narrow",
        prepared_at=PREPARED_AT,
        task_before=before,
    )
    assert result.recorded is True
    note = next(row for row in _rows(writer) if row.get("kind") == "note")
    assert note["task_before"]["completed"] == ["<redacted> private step"]
    # "[] observed" stays an empty list, "None" stays unrecorded
    assert note["task_before"]["remaining"] == []
    assert note["task_before"]["blockers"] is None
    assert SECRET.encode() not in _raw(writer)


@pytest.mark.parametrize(
    "changed",
    [
        "substantively-different",
        "reordered",
        "observed-list-changed-to-unrecorded",
        "unrecorded-changed-to-observed-empty",
    ],
)
def test_a_before_that_is_not_the_recorded_observation_is_refused(
    tmp_path, redactor, changed
) -> None:
    """AC-050: a backfill (any other snapshot) is refused with zero writes.

    Only the exact recorded axes are a legal repeat: a different value, a
    reordered list (a different observation) and every ``None``/``[]``
    confusion are refused, and the refusal never echoes the value.
    Predicted green.
    """
    writer = _writer(tmp_path / f"before-{changed}", redactor)
    recorded = _state(
        "not-queued",
        source="worker-registry",
        completed=["first step", "second step"],
        remaining=None,
        blockers=[],
    )
    meta = _started(writer, task_before=recorded)
    decision_id = _decision_id(meta)
    recorded_bytes = _raw(writer)

    candidate = dict(recorded)
    if changed == "substantively-different":
        candidate["completed"] = ["first step", "second step", "a later step"]
    elif changed == "reordered":
        candidate["completed"] = ["second step", "first step"]
    elif changed == "observed-list-changed-to-unrecorded":
        candidate["completed"] = None
    else:
        candidate["remaining"] = []

    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            writer,
            meta,
            decision_id=decision_id,
            result=_result(),
            material=_material(),
            preparation=_preparation(),
            task_before=candidate,
        )
    assert "task_before" in str(caught.value)
    assert _raw(writer) == recorded_bytes
    assert _error_raw(writer) == b""


def test_an_exact_before_restatement_is_accepted_with_null_and_empty_kept_apart(
    tmp_path, redactor
) -> None:
    """Legal contrast for the refusal above: the exact recorded axes are legal.

    Predicted green.
    """
    writer = _writer(tmp_path / "before-exact", redactor)
    recorded = _state(
        "not-queued",
        source="worker-registry",
        completed=[],
        remaining=None,
        blockers=[],
    )
    meta = _started(writer, task_before=recorded)
    decision_id = _decision_id(meta)
    result = lifecycle.record_request(
        writer,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
        task_before=recorded,
    )
    assert result.recorded is True
    row = next(row for row in _rows(writer) if row.get("kind") == "request")
    assert row["task_before"]["completed"] == []
    assert row["task_before"]["remaining"] is None
    assert row["task_before"]["blockers"] == []


# ── scope and provenance controls ─────────────────────────────────────────


@pytest.mark.skipif(
    os.name != "nt", reason="the case-insensitive path identity is a Windows fact"
)
def test_the_production_path_refusal_is_the_test_scopes_rule(tmp_path, redactor) -> None:
    """AC-014: a case variant of ``.agenticdoc`` is the same tree in a test scope.

    The refusal must come from the *test* scope rule, not from a production
    scope that would write the live ledger anyway: the same sink is accepted
    when it is declared as a production scope, so the contrast proves which rule
    fired. No file is created by either construction. Predicted green on the
    repaired ``decision_wire``.
    """
    sink = tmp_path / ".AgenticDoc" / "_autopilot" / "decision-lifecycle.jsonl"
    with pytest.raises(wire.WireScopeError):
        lifecycle.LifecycleStore(
            sink=sink,
            project_id="proj-boundary",
            redact=redactor,
            scope_kind="test",
            warn=lambda line: None,
        )
    production = lifecycle.LifecycleStore(
        sink=sink,
        project_id="proj-boundary",
        redact=redactor,
        scope_kind="production",
        warn=lambda line: None,
    )
    assert production.scope_kind == "production"
    assert not sink.exists()
    isolated = lifecycle.LifecycleStore.test(
        tmp_path / "isolated-root", project_id="proj-boundary", redact=redactor
    )
    assert isolated.scope_kind == "test"
    assert not isolated.sink.exists()


def test_the_boundary_suite_runs_isolated_from_the_live_repository(tmp_path) -> None:
    """AC-014: the suite and the products come from one isolated tree, under -B.

    ``--basetemp`` must live outside every ``.agenticdoc`` tree, the writer
    modules must be loaded from the isolated package directory the suite is run
    against, and the live repository copy must not be the one imported.
    Predicted green under the delivered runner.
    """
    assert sys.dont_write_bytecode is True, "the suite must run under python -B"
    suite = pathlib.Path(__file__).resolve()
    products = {
        "decision_lifecycle": pathlib.Path(lifecycle.__file__).resolve(),
        "decision_wire": pathlib.Path(wire.__file__).resolve(),
        "decision_task_state": pathlib.Path(task_state.__file__).resolve(),
        "decision_points": pathlib.Path(decision_points.__file__).resolve(),
    }
    package_dirs = {path.parent for path in products.values()}
    assert len(package_dirs) == 1, products
    package_dir = package_dirs.pop()
    assert package_dir.name == "multi-workers"
    assert package_dir.parents[0].name == "packages"
    # the products come from the isolated implementation tree, not the live one
    assert package_dir.parents[1].name == "implementation-worktree", package_dir
    # this suite is evidence: deliberately outside the mirror, and its own path
    # proves which checkout the run belongs to (no absolute path is hardcoded)
    assert package_dir not in suite.parents
    assert ".agenticdoc" in {part.lower() for part in suite.parts}
    checkout = suite.parents[7]
    live_package_dir = checkout / "packages" / "multi-workers"
    assert live_package_dir != package_dir
    assert live_package_dir not in package_dir.parents
    assert pathlib.Path.cwd().resolve() == package_dir, (
        "the boundary suite must be run from the isolated package directory"
    )
    fixture_root = pathlib.Path(tmp_path).resolve()
    assert ".agenticdoc" not in [part.lower() for part in fixture_root.parts]
    assert package_dir not in fixture_root.parents
    assert live_package_dir not in fixture_root.parents
