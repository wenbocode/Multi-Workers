"""Behaviour tests for the single decision lifecycle writer (T02).

Contract under test (design D004 §4.1/4.2, AC-010/012/014/016/019/020):

* ``DecisionMeta`` is the local envelope meta only: ``record_version=2``,
  ``logical_id``, ``key``, nullable ``task_key``, ``initiator_role``, nullable
  ``retry_of``. It is never part of the material sent to a model.
* a ``record-start`` fact persists the version/association *before* any
  transport call, so a failed capture is still a v2 record and a missing wire
  row never makes a record legacy;
* one logical id per real decision, every stage fact carries it;
* ``consumed`` (received) / ``executed`` (action happened) / ``settled`` (this
  processing result) / ``signoff`` (the signoff file really succeeded) stay
  distinct words, one event per action, deduplicated by ``event_id`` only -
  never by ``(decision_id, lifecycle word)``;
* the managed store is the only writer (lock + fsync + tail repair); failures
  come back as a structured value and are never reported as recorded;
* structural values, keys and errors take the injected known-secret boundary,
  free text is redacted before clipping (AC-019);
* invalid input writes nothing (AC-020).

No real credential, network, LLM, browser, build or service is touched.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
import pathlib
import re
import sys

import pytest

import decision
import decision_lifecycle as lifecycle
import decision_points
import decision_wire as wire

# Synthetic, deliberately distinctive values (never real credentials).
SECRET = "Sk-9Qz7Lm2Xr5Tb8Vc3Nd6Hf1Gj4Kp0Ws"
LONG_SECRET = "Zq7Xw3Vb9Kp2Lm5Rt8Yc4Nd6Hf1Gj0SaWq3Er7Ty1Ui5Op9As4Df8"  # 64 chars
SHA256 = "a" * 64


@pytest.fixture()
def redactor() -> wire.SecretRedactor:
    return wire.SubstringRedactor([SECRET, LONG_SECRET])


@pytest.fixture()
def warnings() -> list[str]:
    return []


@pytest.fixture()
def store(tmp_path, redactor, warnings) -> lifecycle.LifecycleStore:
    return lifecycle.LifecycleStore.test(
        tmp_path / "decide-test",
        project_id="proj-test",
        redact=redactor,
        warn=warnings.append,
    )


def _meta(**overrides) -> lifecycle.DecisionMeta:
    kwargs = {"task_key": "task-a", "initiator_role": "pm"}
    kwargs.update(overrides)
    return lifecycle.DecisionMeta.create(kwargs.pop("key", "mw-demo"), **kwargs)


def _rows(store: lifecycle.LifecycleStore) -> list[dict]:
    return lifecycle.read_lifecycle(store).events


def _raw(store: lifecycle.LifecycleStore) -> bytes:
    return store.sink.read_bytes()


# ── DecisionMeta: v2, explicit identity, never model material ───────────────


def test_meta_is_record_version_two_and_model_excluded():
    meta = lifecycle.DecisionMeta.create(
        "mw-demo", task_key=None, initiator_role="pm", retry_of=None
    )
    assert meta.record_version == 2
    assert re.fullmatch(r"[0-9a-f]{32}", meta.logical_id)
    assert meta.as_meta() == {
        "record_version": 2,
        "logical_id": meta.logical_id,
        "key": "mw-demo",
        "task_key": None,
        "initiator_role": "pm",
        "retry_of": None,
    }
    assert tuple(meta.as_meta()) == lifecycle.META_KEYS
    # meta is the local envelope only: no model state key rides along.
    assert "model" not in meta.as_meta()
    assert "state" not in meta.as_meta()


@pytest.mark.parametrize("role", ["boss", "", "PM"])
def test_meta_rejects_an_unknown_initiator_role(role):
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.DecisionMeta.create("mw-demo", initiator_role=role)
    assert "initiator_role" in str(caught.value)


@pytest.mark.parametrize("key", ["", "../x", "a/b", ".hidden", "-lead"])
def test_meta_rejects_a_key_that_is_not_one_directory_name(key):
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.DecisionMeta.create(key)
    assert "key" in str(caught.value)


def test_meta_round_trips_through_the_local_envelope():
    meta = _meta()
    envelope = meta.as_envelope({"task_goal": "ship it"})
    assert envelope["meta"] == meta.as_meta()
    assert envelope["material"] == {"task_goal": "ship it"}
    assert lifecycle.DecisionMeta.from_envelope(envelope) == meta


@pytest.mark.parametrize(
    "envelope",
    [
        {},
        {"material": {}},
        {"meta": {"key": "mw-demo"}, "material": {}},
        {
            "meta": {
                "record_version": 1,
                "logical_id": "a" * 32,
                "key": "mw-demo",
                "task_key": None,
                "initiator_role": "pm",
                "retry_of": None,
            },
            "material": {},
        },
        {
            "meta": {
                "record_version": 2,
                "logical_id": "a" * 32,
                "key": "mw-demo",
                "task_key": None,
                "initiator_role": "pm",
                "retry_of": None,
                "wired": True,
            },
            "material": {},
        },
    ],
)
def test_envelope_meta_is_required_and_closed(envelope):
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.DecisionMeta.from_envelope(envelope)


# ── record-start: version + association without any wire row ────────────────


def test_record_start_persists_version_and_association_without_wire(store):
    meta = _meta()
    result = lifecycle.record_start(store, meta)

    assert result.status == "written"
    assert result.recorded is True
    assert result.error_class is None
    assert not (store.sink.parent / "wire.jsonl").exists()

    rows = _rows(store)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "record-start"
    assert row["schema_version"] == 1
    assert row["record_version"] == 2
    assert row["logical_id"] == meta.logical_id
    assert row["key"] == "mw-demo"
    assert row["task_key"] == "task-a"
    assert row["initiator_role"] == "pm"
    assert row["retry_of"] is None
    assert row["decision_id"] is None  # the start fact precedes the call
    assert row["scope"] == "test"
    assert row["project_id"] == "proj-test"
    # "new record, failed capture" is v2 because of this fact, not because of a wire row.
    assert lifecycle.versioned_logical_ids(rows) == frozenset({meta.logical_id})


def test_record_start_is_idempotent_by_event_id(store):
    meta = _meta()
    first = lifecycle.record_start(store, meta)
    assert first.recorded
    before = _raw(store)

    second = lifecycle.record_start(store, meta)

    assert second.status == "duplicate"
    assert second.recorded is True
    assert second.event_id == first.event_id
    assert _raw(store) == before
    assert len(_rows(store)) == 1


def test_two_tasks_under_one_key_do_not_collide_and_absent_task_stays_null(store):
    first = lifecycle.DecisionMeta.create("mw-demo", task_key="task-a", initiator_role="pm")
    second = lifecycle.DecisionMeta.create("mw-demo", task_key="task-b", initiator_role="coding")
    absent = lifecycle.DecisionMeta.create("mw-demo", task_key=None, initiator_role="unknown")
    assert len({first.logical_id, second.logical_id, absent.logical_id}) == 3

    for meta in (first, second, absent):
        assert lifecycle.record_start(store, meta).recorded

    by_id = {row["logical_id"]: row for row in _rows(store)}
    assert by_id[first.logical_id]["task_key"] == "task-a"
    assert by_id[second.logical_id]["task_key"] == "task-b"
    assert by_id[absent.logical_id]["task_key"] is None
    # never inferred: exactly the one caller that passed null has null
    assert sum(1 for row in by_id.values() if row["task_key"] is None) == 1


# ── stages: one logical id, distinct words, event-id idempotency ────────────


def test_stages_share_one_logical_id_and_stay_distinct(store):
    meta = _meta()
    assert lifecycle.record_start(store, meta).recorded
    assert lifecycle.record_consumed(
        store, meta, decision_id="dp1:aaa", dp="dp1", answer="coding", answer_source="api"
    ).recorded
    assert lifecycle.record_executed(
        store, meta, decision_id="dp1:aaa", dp="dp1", action="type-read", result="read the type"
    ).recorded
    assert lifecycle.record_executed(
        store, meta, decision_id="dp1:aaa", dp="dp1", action="pm-handoff", result="handed to PM"
    ).recorded
    assert lifecycle.record_settled(
        store, meta, decision_id="dp1:aaa", dp="dp1", outcome="ok"
    ).recorded
    assert lifecycle.record_signoff(
        store,
        meta,
        decision_id="dp1:aaa",
        dp="dp1",
        evidence_path="workers/t02/evidence/sign-final.md",
        evidence_sha256=SHA256,
    ).recorded

    rows = _rows(store)
    assert {row["logical_id"] for row in rows} == {meta.logical_id}
    stages = [row["lifecycle"] for row in rows if row["kind"] == "lifecycle"]
    assert stages == ["consumed", "executed", "executed", "settled", "signoff"]

    settled = next(row for row in rows if row.get("lifecycle") == "settled")
    assert settled["outcome"] == "ok"
    # the current reader validates ``settled.result`` as the outcome vocabulary
    assert settled["result"] == "ok"

    executed = [row for row in rows if row.get("lifecycle") == "executed"]
    assert [row["action"] for row in executed] == ["type-read", "pm-handoff"]
    assert {row["event_id"] for row in executed} != {None}

    signoff = next(row for row in rows if row.get("lifecycle") == "signoff")
    assert signoff["evidence_path"] == "workers/t02/evidence/sign-final.md"
    assert signoff["evidence_sha256"] == SHA256

    consumed = next(row for row in rows if row.get("lifecycle") == "consumed")
    assert consumed["answer"] == "coding"
    assert consumed["answer_source"] == "api"


def test_consumed_is_not_completion(store):
    meta = _meta()
    lifecycle.record_start(store, meta)
    result = lifecycle.record_consumed(store, meta, decision_id="dp3:bbb", dp="dp3")
    assert result.recorded
    rows = _rows(store)
    assert [row.get("lifecycle") for row in rows] == [None, "consumed"]
    assert not any(row.get("lifecycle") in ("settled", "signoff") for row in rows)


def test_retry_gets_a_new_logical_id_and_keeps_the_prior_bytes(store):
    meta = _meta()
    lifecycle.record_start(store, meta)
    lifecycle.record_settled(store, meta, decision_id="dp25:ccc", dp="dp25", outcome="rework")
    before = _raw(store)

    retry = lifecycle.DecisionMeta.create(
        "mw-demo", task_key="task-a", initiator_role="pm", retry_of=meta.logical_id
    )
    assert retry.logical_id != meta.logical_id
    assert lifecycle.record_start(store, retry).recorded

    assert _raw(store).startswith(before)
    start = next(row for row in _rows(store) if row["logical_id"] == retry.logical_id)
    assert start["kind"] == "record-start"
    assert start["retry_of"] == meta.logical_id
    assert lifecycle.versioned_logical_ids(_rows(store)) == frozenset(
        {meta.logical_id, retry.logical_id}
    )


def test_same_event_id_is_idempotent_but_a_second_event_is_not_swallowed(store):
    meta = _meta()
    event_id = "evt-consumed-0001"
    first = lifecycle.record_consumed(
        store, meta, decision_id="dp3:ddd", dp="dp3", event_id=event_id
    )
    assert first.status == "written"
    before = _raw(store)

    again = lifecycle.record_consumed(
        store, meta, decision_id="dp3:ddd", dp="dp3", event_id=event_id
    )
    assert again.status == "duplicate"
    assert again.event_id == event_id
    assert _raw(store) == before
    assert len(_rows(store)) == 1

    # Same decision + same word, different event: a second real action, not a duplicate.
    second = lifecycle.record_consumed(store, meta, decision_id="dp3:ddd", dp="dp3")
    assert second.status == "written"
    assert second.event_id != event_id
    rows = _rows(store)
    assert len(rows) == 2
    assert [row["lifecycle"] for row in rows] == ["consumed", "consumed"]
    assert _raw(store).startswith(before)


# ── invalid input: zero writes, honest refusal (AC-020) ────────────────────


def _assert_nothing_written(store: lifecycle.LifecycleStore) -> None:
    assert not store.sink.exists()
    assert _rows(store) == []


@pytest.mark.parametrize("outcome", ["done", "OK", "", None])
def test_settled_requires_a_declared_outcome(store, outcome):
    meta = _meta()
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_settled(store, meta, decision_id="dp2:eee", dp="dp2", outcome=outcome)
    assert "outcome" in str(caught.value)
    _assert_nothing_written(store)


@pytest.mark.parametrize("action", ["did-stuff", "", "narrow "])
def test_executed_requires_a_declared_action(store, action):
    meta = _meta()
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_executed(store, meta, decision_id="dp2:eee", dp="dp2", action=action)
    assert "action" in str(caught.value)
    _assert_nothing_written(store)


def test_settled_does_not_accept_an_executed_action_or_a_file_evidence(store):
    meta = _meta()
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_lifecycle(
            store,
            meta,
            stage="settled",
            decision_id="dp2:eee",
            dp="dp2",
            outcome="ok",
            action="narrow",
        )
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_lifecycle(
            store,
            meta,
            stage="settled",
            decision_id="dp2:eee",
            dp="dp2",
            outcome="ok",
            evidence_path="x.md",
        )
    _assert_nothing_written(store)


@pytest.mark.parametrize(
    "evidence_path",
    ["/etc/passwd", "../escape.md", "a\\b.md", "a//b.md", "", "a/\x00b"],
)
def test_signoff_refuses_an_unsafe_evidence_path(store, evidence_path):
    meta = _meta()
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_signoff(
            store,
            meta,
            decision_id="dp25:fff",
            dp="dp25",
            evidence_path=evidence_path,
            evidence_sha256=SHA256,
        )
    assert "evidence_path" in str(caught.value)
    _assert_nothing_written(store)


@pytest.mark.parametrize("digest", ["a" * 63, "A" * 64, "", "z" * 64])
def test_signoff_refuses_a_non_sha256_digest(store, digest):
    meta = _meta()
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_signoff(
            store,
            meta,
            decision_id="dp25:fff",
            dp="dp25",
            evidence_path="sign.md",
            evidence_sha256=digest,
        )
    assert "evidence_sha256" in str(caught.value)
    _assert_nothing_written(store)


@pytest.mark.parametrize(
    "decision_id", ["", "dp3/nested", "dp3..x", "d" * 300, "no-separator", "\x00dp3:x"]
)
def test_stage_writes_refuse_an_invalid_decision_id(store, decision_id):
    meta = _meta()
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_consumed(store, meta, decision_id=decision_id, dp="dp3")
    assert "decision_id" in str(caught.value)
    _assert_nothing_written(store)


def test_dp_must_match_the_decision_id_prefix(store):
    meta = _meta()
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_consumed(store, meta, decision_id="dp25:ggg", dp="dp3")
    assert "dp" in str(caught.value)
    _assert_nothing_written(store)


@pytest.mark.parametrize("event_id", ["", "has space", 'q"uote', "x" * 200])
def test_event_id_must_be_a_ledger_token(store, event_id):
    meta = _meta()
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_consumed(
            store, meta, decision_id="dp3:xxx", dp="dp3", event_id=event_id
        )
    assert "event_id" in str(caught.value)
    _assert_nothing_written(store)


def test_signoff_requires_the_file_evidence_arguments(store):
    meta = _meta()
    with pytest.raises(TypeError):
        lifecycle.record_signoff(store, meta, decision_id="dp25:hhh", dp="dp25")  # type: ignore[call-arg]
    _assert_nothing_written(store)


# ── known-secret boundaries: values, keys, errors, long tail (AC-019) ───────


def test_known_secret_in_structural_values_is_refused_without_echo(store):
    # Meta creation has no known set yet (the redactor is injected at the store),
    # so the boundary that refuses a secret-bearing key is the write itself.
    meta = lifecycle.DecisionMeta.create("k-" + SECRET)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_start(store, meta)
    assert "key" in str(caught.value)

    clean = _meta()
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_signoff(
            store,
            clean,
            decision_id="dp25:iii",
            dp="dp25",
            evidence_path="workers/" + SECRET + "/sign.md",
            evidence_sha256=SHA256,
        )
    assert "evidence_path" in str(caught.value)
    secret_errors = [str(caught.value)]

    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_consumed(
            store, clean, decision_id="dp3:" + SECRET, dp="dp3"
        )
    assert "decision_id" in str(caught.value)
    secret_errors.append(str(caught.value))

    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_executed(
            store, clean, decision_id="dp3:jjj", dp="dp3", action="clarify", event_id=SECRET
        )
    assert "event_id" in str(caught.value)
    secret_errors.append(str(caught.value))

    for message in secret_errors:
        assert SECRET not in message
        assert SECRET not in repr(message)
    _assert_nothing_written(store)


def test_known_secret_in_free_text_is_redacted_before_it_is_stored(store):
    meta = _meta()
    lifecycle.record_start(store, meta)
    lifecycle.record_consumed(
        store,
        meta,
        decision_id="dp3:jjj",
        dp="dp3",
        reason="caller pasted " + SECRET + " here",
        answer="answer " + SECRET,
    )
    lifecycle.record_executed(
        store,
        meta,
        decision_id="dp3:jjj",
        dp="dp3",
        action="clarify",
        result="context " + SECRET,
    )
    raw = _raw(store)
    assert SECRET.encode() not in raw

    rows = _rows(store)
    consumed = next(row for row in rows if row.get("lifecycle") == "consumed")
    assert consumed["reason"] == "caller pasted <redacted> here"
    assert consumed["answer"] == "answer <redacted>"
    executed = next(row for row in rows if row.get("lifecycle") == "executed")
    assert executed["result"] == "context <redacted>"


def test_long_secret_tail_is_never_persisted_by_a_clip(store):
    meta = _meta()
    lifecycle.record_start(store, meta)
    lifecycle.record_executed(
        store,
        meta,
        decision_id="dp3:kkk",
        dp="dp3",
        action="clarify",
        result="x" * 500 + LONG_SECRET,
        reason="y" * 500 + LONG_SECRET,
    )
    raw = _raw(store)
    assert LONG_SECRET.encode() not in raw
    # no cut prefix of the long secret survives the 512-byte free-text clip
    for size in range(6, len(LONG_SECRET) + 1):
        assert LONG_SECRET[:size].encode() not in raw


def test_a_symlinked_sink_is_refused(tmp_path, redactor):
    target = tmp_path / "elsewhere.jsonl"
    target.write_text("", encoding="utf-8")
    root = tmp_path / "decide-test"
    root.mkdir()
    link = root / "lifecycle.jsonl"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")
    with pytest.raises(wire.WireScopeError):
        lifecycle.LifecycleStore.test(root, project_id="p", redact=redactor)
    assert target.read_bytes() == b""


# ── failure semantics: structured failure, never a fake "recorded" ─────────


def test_failed_write_is_reported_and_the_failure_sidecar_is_separate(tmp_path, redactor):
    store = lifecycle.LifecycleStore.test(
        tmp_path / "decide-test",
        project_id="proj-test",
        redact=redactor,
        lock_budget_s=0.05,
        lock_retries=2,
        warn=lambda line: None,
    )
    store.sink.parent.mkdir(parents=True)
    lock = store.sink.with_name(store.sink.name + ".lock")
    lock.write_text("held", encoding="utf-8")

    meta = _meta()
    result = lifecycle.record_start(store, meta)

    assert result.status == "failed"
    assert result.recorded is False
    assert result.error_class == "lock-timeout"
    assert result.error_recorded is True
    assert not store.sink.exists()
    # a failed feedback write can never say the report was recorded
    assert lifecycle.versioned_logical_ids(_rows(store)) == frozenset()

    sidecar = wire.read_events(store.error_sink).events
    assert len(sidecar) == 1
    row = sidecar[0]
    assert row["kind"] == "lifecycle-error"
    assert row["logical_id"] == meta.logical_id
    assert row["stage"] == "record-start"
    assert row["error_class"] == "lock-timeout"
    assert row["attempted_event_id"] == result.event_id
    assert SECRET not in store.error_sink.read_text(encoding="utf-8")


def test_unreadable_ledger_is_reported_not_faked(tmp_path, redactor):
    root = tmp_path / "decide-test"
    root.mkdir()
    (root / "lifecycle.jsonl").mkdir()  # a directory where the ledger should be
    store = lifecycle.LifecycleStore.test(
        root, project_id="proj-test", redact=redactor, warn=lambda line: None
    )
    meta = _meta()

    result = lifecycle.record_start(store, meta)

    assert result.status == "failed"
    assert result.recorded is False
    assert result.error_class == "dedupe"
    assert result.error_recorded is True
    with pytest.raises(OSError):
        lifecycle.read_lifecycle(store)


def test_a_reader_only_row_without_a_v2_start_is_not_versioned(tmp_path):
    # Reader unit test: hand-filled rows are allowed here only.
    scope = wire.WireScope(
        sink=tmp_path / "lifecycle.jsonl", project_id="p", redact=wire.SubstringRedactor([SECRET])
    )
    legacy = wire.record_start_event(
        scope, logical_id="a" * 32, record_version=1, initiator_role="unknown"
    )
    assert wire.append_event(scope, legacy).written
    failed_capture = wire.lifecycle_event(
        scope, lifecycle="consumed", logical_id="b" * 32, reason="hand-filled reader row"
    )
    assert wire.append_event(scope, failed_capture).written

    rows = wire.read_events(tmp_path / "lifecycle.jsonl").events
    assert len(rows) == 2
    # a v1 start fact and a failed capture are not new v2 records
    assert lifecycle.versioned_logical_ids(rows) == frozenset()


def test_production_writer_facts_are_consumed_by_the_current_history_reader(tmp_path, redactor):
    import decision_history

    control = tmp_path / "proj"
    (control / ".agenticdoc").mkdir(parents=True)
    store = lifecycle.LifecycleStore.production(control, redact=redactor, warn=lambda line: None)
    assert store.sink == control / ".agenticdoc" / "_autopilot" / "decision-lifecycle.jsonl"

    meta = _meta()
    assert lifecycle.record_start(store, meta).recorded
    assert lifecycle.record_consumed(
        store, meta, decision_id="dp1:zzz", dp="dp1", answer="coding", answer_source="api"
    ).recorded
    assert lifecycle.record_settled(
        store, meta, decision_id="dp1:zzz", dp="dp1", outcome="ok"
    ).recorded

    # the real production path, read back by the real (unmodified) history reader
    snapshot = decision_history.load_history(control, redact=redactor)
    assert snapshot.stats.unknown_kind == 0
    assert snapshot.stats.unknown_lifecycle == 0
    assert snapshot.stats.lifecycle_damaged == 0
    record = next(row for row in snapshot.records if row.decision_id == "dp1:zzz")
    assert record.key == "mw-demo"
    assert record.task_key == "task-a"
    assert record.stages["consumed"].state == "recorded"
    assert record.stages["settled"].state == "recorded"
    assert record.stages["settled"].result == "ok"


# ── isolation: no credential/config read, synthetic HOME only ──────────────


def test_writer_reads_no_credential_files_outside_the_synthetic_home(
    tmp_path, redactor, monkeypatch
):
    home = tmp_path / "home"
    auth = home / ".pi" / "agent" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text('{"timi": {"key": "synthetic-not-real"}}', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    opened: list[str] = []
    real_path_open = pathlib.Path.open
    real_builtin_open = builtins.open
    real_os_open = os.open

    def path_open(self, *args, **kwargs):
        opened.append(str(self))
        return real_path_open(self, *args, **kwargs)

    def builtin_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_builtin_open(file, *args, **kwargs)

    def os_open(path, *args, **kwargs):
        opened.append(str(path))
        return real_os_open(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", path_open)
    monkeypatch.setattr(builtins, "open", builtin_open)
    monkeypatch.setattr(io, "open", builtin_open)
    monkeypatch.setattr(os, "open", os_open)

    store = lifecycle.LifecycleStore.test(
        tmp_path / "decide-test", project_id="proj-test", redact=redactor, warn=lambda line: None
    )
    meta = _meta()
    assert lifecycle.record_start(store, meta).recorded
    assert lifecycle.record_settled(
        store, meta, decision_id="dp2:lll", dp="dp2", outcome="ok"
    ).recorded

    touched = [pathlib.Path(path).as_posix() for path in opened]
    assert not any(path.endswith("auth.json") for path in touched)
    assert str(store.sink) in opened  # the spy did observe the real ledger write


# ── T10: real request / PM note / basis provenance / task terminal ─────────
#
# Contract under test (design §4.6, spec AC-007/AC-049/AC-050/AC-051):
# * a request fact keeps transport facts and the one business decision apart -
#   a transport success with zero business decisions is not an approval;
# * the selected basis is the PM-prepared catalogue item, its provenance is
#   re-checked by the single preparation authority and its digest is recorded;
# * the PM note is its own fact with its own pre-submission time and only a PM
#   record may author it - the model's basis and the note never mix;
# * a later `before` cannot replace the creation fact's snapshot (no backfill),
#   and `null` stays distinct from `[]`;
# * the task terminal needs its own real observation, never ``settled``;
# * a successor request links a really recorded parent and is written once.

DP = "dp-pm-steer"
PREPARED_AT = "2026-10-27T08:15:00+00:00"
BASIS_TEXT = "the task card already carries the split"


def _state(status="running", *, source="agent-report", observed_at="2026-10-27T08:00:00+00:00", completed=None, remaining=None, blockers=None):
    return dict(
        status=status,
        source=source,
        observed_at=observed_at,
        completed=completed,
        remaining=remaining,
        blockers=blockers,
    )


def _material():
    return {
        "task_goal": "ship the split",
        "task_requirements": "keep both files",
        "task_deliverables": "two patches",
    }


def _preparation(choice="narrow", prepared_at=PREPARED_AT):
    return {
        "basis_catalog": [
            {
                "id": "b-narrow",
                "text": BASIS_TEXT,
                "material_refs": ["task_goal"],
                "applies_to": [choice, "split"],
            },
            {
                "id": "b-split",
                "text": "the remaining work is two independent files",
                "material_refs": ["task_requirements"],
                "applies_to": ["split"],
            },
        ],
        "prepared_at": prepared_at,
    }


def _result(**over):
    base = {
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


def _started(store, **meta_kw):
    meta = _meta(**meta_kw)
    assert lifecycle.record_start(store, meta).recorded
    return meta


def _decision_id(meta, dp=DP):
    return f"{dp}:{meta.logical_id}"


def _row(store, kind):
    matches = [row for row in _rows(store) if row.get("kind") == kind]
    assert len(matches) == 1, f"expected one {kind} row, got {len(matches)}"
    return matches[0]


def test_a_transport_success_without_a_business_decision_is_not_an_approval(store):
    meta = _started(store)
    refused = _result(
        choice=None,
        basis_id=None,
        basis_text=None,
        basis_source=None,
        business_decisions=0,
        reason="bad-response",
        attempts=1,
        transport_attempts=2,
    )
    result = lifecycle.record_request(
        store,
        meta,
        decision_id=_decision_id(meta),
        result=refused,
        material=_material(),
        preparation=_preparation(),
    )
    assert result.recorded is True

    row = _row(store, "request")
    assert row["available"] is True  # the wire really answered
    assert row["transport_attempts"] == 2 and row["attempts"] == 1
    assert row["business_decisions"] == 0  # ... and no business decision was made
    assert row["choice"] is None and row["basis_id"] is None
    assert row["basis_text"] is None and row["basis_catalog_sha256"] is None
    assert row["reason"] == "bad-response"
    # transport facts never fabricate an action, settlement, sign-off or terminal
    assert {item.get("kind") for item in _rows(store)} == {"record-start", "request"}


def test_a_business_decision_records_the_selected_pm_basis_and_its_digest(store):
    meta = _started(store)
    preparation = _preparation()
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=_decision_id(meta),
        result=_result(),
        material=_material(),
        preparation=preparation,
    ).recorded

    row = _row(store, "request")
    assert row["business_decisions"] == 1
    assert row["choice"] == "narrow"
    assert row["basis_id"] == "b-narrow"
    assert row["basis_text"] == BASIS_TEXT
    assert row["basis_source"] == "pm-prepared"
    assert row["prepared_at"] == PREPARED_AT
    canonical = json.dumps(
        preparation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert row["basis_catalog_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert row["logical_id"] == meta.logical_id
    assert row["task_key"] == "task-a"


def test_a_replayed_result_is_a_record_without_a_new_business_decision(store):
    meta = _started(store)
    replay = _result(
        choice=None,
        basis_id=None,
        basis_text=None,
        basis_source=None,
        business_decisions=0,
        reason=None,
        attempts=0,
        transport_attempts=0,
        replayed=True,
    )
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=_decision_id(meta),
        result=replay,
        material=_material(),
        preparation=_preparation(),
    ).recorded
    row = _row(store, "request")
    assert row["replayed"] is True
    assert row["business_decisions"] == 0 and row["choice"] is None
    # a replay is not a settlement/approval either
    assert not any(item.get("business_decisions") == 1 for item in _rows(store))


@pytest.mark.parametrize(
    "over,field",
    [
        ({"replayed": True, "business_decisions": 1}, "replayed"),
        ({"available": False, "business_decisions": 1}, "available"),
        ({"reason": "timeout", "business_decisions": 1}, "reason"),
        ({"attempts": 0, "business_decisions": 1}, "attempts"),
        ({"basis_source": "model", "business_decisions": 1}, "basis_source"),
        (
            {
                "choice": None,
                "basis_id": None,
                "basis_text": None,
                "basis_source": None,
                "business_decisions": 0,
                "reason": None,
            },
            "reason",
        ),
        (
            {
                "replayed": True,
                "business_decisions": 0,
                "reason": "timeout",
                "choice": None,
                "basis_id": None,
                "basis_text": None,
                "basis_source": None,
                "attempts": 0,
                "transport_attempts": 0,
            },
            "reason",
        ),
    ],
)
def test_request_refuses_a_split_that_is_not_a_real_prepared_outcome(store, over, field):
    meta = _started(store)
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            store,
            meta,
            decision_id=_decision_id(meta),
            result=_result(**over),
            material=_material(),
            preparation=_preparation(),
        )
    assert field in str(caught.value)
    assert _raw(store) == before  # zero writes, prior bytes untouched


@pytest.mark.parametrize(
    "over,prepare,materialize,field",
    [
        ({"basis_id": "b-missing"}, True, True, "basis_id"),
        ({"choice": "escalate"}, True, True, "basis_id"),
        ({"basis_text": "the model said this was fine"}, True, True, "basis_text"),
        ({}, False, True, "preparation"),
        ({}, True, False, "material"),
    ],
)
def test_the_selected_basis_must_come_from_the_submitted_preparation(
    store, over, prepare, materialize, field
):
    meta = _started(store)
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            store,
            meta,
            decision_id=_decision_id(meta),
            result=_result(**over),
            material=_material() if materialize else None,
            preparation=_preparation() if prepare else None,
        )
    assert field in str(caught.value)
    assert _raw(store) == before


def test_a_retired_entry_id_cannot_be_recorded_as_a_request(store):
    meta = _started(store)
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            store,
            meta,
            decision_id=f"dp1-dispatch-type:{meta.logical_id}",
            result=_result(dp="dp1-dispatch-type"),
            material=_material(),
            preparation=_preparation(),
        )
    assert "dp" in str(caught.value)
    assert _raw(store) == before


def test_the_prepared_at_must_be_the_preparation_time_not_the_write_clock(store):
    meta = _started(store)
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            store,
            meta,
            decision_id=_decision_id(meta),
            result=_result(prepared_at="2026-10-27T09:99:00+00:00"),
            material=_material(),
            preparation=_preparation(),
        )
    assert "prepared_at" in str(caught.value)
    assert _raw(store) == before


def test_the_pm_note_is_stored_separately_from_the_model_basis(store):
    meta = _started(store)
    decision_id = _decision_id(meta)
    note_text = "matter: split the file; action: narrow; end when both patches land"
    assert lifecycle.record_note(
        store,
        meta,
        decision_id=decision_id,
        pm_note=note_text,
        prepared_at=PREPARED_AT,
    ).recorded
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
    ).recorded

    note = _row(store, "note")
    request = _row(store, "request")
    assert note["pm_note"] == note_text
    assert note["prepared_at"] == PREPARED_AT
    assert note["note_source"] == "pm-prepared"
    assert "basis_id" not in note and "choice" not in note
    assert "pm_note" not in request
    assert request["basis_id"] == "b-narrow"
    assert note["logical_id"] == request["logical_id"] == meta.logical_id


def test_a_non_pm_record_cannot_write_a_pm_note(store):
    meta = _started(store, initiator_role="coding")
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_note(
            store,
            meta,
            decision_id=_decision_id(meta),
            pm_note="a worker must not speak for the PM",
            prepared_at=PREPARED_AT,
        )
    assert "initiator_role" in str(caught.value)
    assert _raw(store) == before


def test_a_later_before_is_refused_while_the_creation_snapshot_can_be_repeated(store):
    recorded_before = _state("not-queued", source="worker-registry", completed=[], remaining=None, blockers=[])
    meta = _started(store, task_before=recorded_before)
    decision_id = _decision_id(meta)
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
        task_before=recorded_before,
    ).recorded
    row = _row(store, "request")
    assert row["task_before"] == recorded_before
    assert row["task_before"]["completed"] == []
    assert row["task_before"]["remaining"] is None

    before_bytes = _raw(store)
    current_state = _state("running", completed=["read the card"], remaining=["split the file"])
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            store,
            meta,
            decision_id=decision_id,
            result=_result(),
            material=_material(),
            preparation=_preparation(),
            event_id="t10-backfill",
            task_before=current_state,
        )
    assert "task_before" in str(caught.value)
    assert _raw(store) == before_bytes


def test_a_before_cannot_be_added_after_the_creation_fact(store):
    meta = _started(store)  # the creation fact recorded no before snapshot
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_note(
            store,
            meta,
            decision_id=_decision_id(meta),
            pm_note="note without a before",
            prepared_at=PREPARED_AT,
            task_before=_state(),
        )
    assert "task_before" in str(caught.value)


def test_terminal_requires_its_own_real_observation_and_never_follows_from_settled(store):
    before = _state("running", completed=[], remaining=["split the file"], blockers=None)
    meta = _started(store, task_before=before)
    decision_id = _decision_id(meta)
    assert lifecycle.record_request(
        store, meta, decision_id=decision_id, result=_result(), material=_material(), preparation=_preparation()
    ).recorded
    assert lifecycle.record_executed(
        store, meta, decision_id=decision_id, dp=DP, action="split", result="split the file"
    ).recorded
    assert lifecycle.record_settled(
        store, meta, decision_id=decision_id, dp=DP, outcome="ok"
    ).recorded
    # a settled round is not a task terminal
    assert not any(row.get("kind") == "terminal" for row in _rows(store))

    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_terminal(
            store, meta, decision_id=decision_id, terminal="completed", reason="done", task_after=None
        )
    assert "task_after" in str(caught.value)

    too_early = dict(before, observed_at="2026-10-27T07:00:00+00:00")
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_terminal(
            store, meta, decision_id=decision_id, terminal="completed", reason="done", task_after=too_early
        )

    after = _state("done", source="dispatch-result", completed=["two patches"], remaining=[], blockers=[])
    result = lifecycle.record_terminal(
        store,
        meta,
        decision_id=decision_id,
        terminal="completed",
        reason="both patches landed",
        evidence="workers/t10/evidence/report.md:12",
        task_after=after,
    )
    assert result.recorded is True
    row = _row(store, "terminal")
    assert row["terminal"] == "completed"
    assert row["reason"] == "both patches landed"
    assert row["task_after"] == after
    assert "done" not in row  # no fabricated completion flag

    # the recorded after observation is now a floor for any later observation
    earlier = _state("done", observed_at="2026-10-27T07:30:00+00:00")
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_terminal(
            store, meta, decision_id=decision_id, terminal="incomplete", reason="late retry", task_after=earlier
        )

    assert lifecycle.record_terminal(
        store, meta, decision_id=decision_id, terminal="completed", reason="both patches landed", task_after=after
    ).duplicate


def test_terminal_refuses_an_undeclared_value_or_a_missing_reason(store):
    meta = _started(store)
    after = _state("done")
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_terminal(
            store, meta, decision_id=_decision_id(meta), terminal="done", reason="x", task_after=after
        )
    assert "terminal" in str(caught.value)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_terminal(
            store, meta, decision_id=_decision_id(meta), terminal="completed", reason="", task_after=after
        )
    assert "reason" in str(caught.value)
    assert not any(row.get("kind") == "terminal" for row in _rows(store))


def test_a_taskless_decision_cannot_claim_a_task_terminal(store):
    meta = _started(store, task_key=None)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_terminal(
            store,
            meta,
            decision_id=_decision_id(meta),
            terminal="completed",
            reason="nothing to terminate",
            task_after=_state("done"),
        )
    assert "task_key" in str(caught.value)


def test_a_successor_request_links_a_recorded_parent_and_is_written_once(store):
    parent = _started(store)
    parent_id = f"dp-gate-approve:{parent.logical_id}"
    assert lifecycle.record_settled(
        store, parent, decision_id=parent_id, dp="dp-gate-approve", outcome="ok"
    ).recorded

    child = _started(store)
    child_id = _decision_id(child)
    first = lifecycle.record_request(
        store,
        child,
        decision_id=child_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
        parent_ref=parent_id,
    )
    assert first.recorded is True
    assert _row(store, "request")["parent_ref"] == parent_id
    before = _raw(store)

    again = lifecycle.record_request(
        store,
        child,
        decision_id=child_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
        parent_ref=parent_id,
    )
    assert again.status == "duplicate"
    assert _raw(store) == before  # no second successor request, no extra approval
    # the parent's own rows were not rewritten as a "release"
    parent_stages = [row.get("lifecycle") for row in _rows(store) if row.get("decision_id") == parent_id]
    assert parent_stages == ["settled"]


def test_an_unrecorded_or_cross_key_parent_ref_is_refused(store):
    child = _started(store)
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            store,
            child,
            decision_id=_decision_id(child),
            result=_result(),
            material=_material(),
            preparation=_preparation(),
            parent_ref="dp-gate-approve:not-recorded-anywhere",
        )
    assert "parent_ref" in str(caught.value)
    assert _raw(store) == before

    other = lifecycle.DecisionMeta.create("mw-other", task_key="task-a", initiator_role="pm")
    other_id = f"dp-gate-approve:{other.logical_id}"
    assert lifecycle.record_start(store, other, decision_id=other_id).recorded
    assert lifecycle.record_settled(
        store, other, decision_id=other_id, dp="dp-gate-approve", outcome="ok"
    ).recorded
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            store,
            child,
            decision_id=_decision_id(child),
            result=_result(),
            material=_material(),
            preparation=_preparation(),
            parent_ref=other_id,
        )
    assert "parent_ref" in str(caught.value)
    assert _raw(store) == before


def test_note_and_request_rows_take_the_known_secret_boundary(store):
    meta = _started(store)
    decision_id = _decision_id(meta)
    assert lifecycle.record_note(
        store,
        meta,
        decision_id=decision_id,
        pm_note="approve: caller pasted " + SECRET,
        prepared_at=PREPARED_AT,
    ).recorded
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
    ).recorded
    raw = _raw(store)
    assert SECRET.encode() not in raw
    assert _row(store, "note")["pm_note"] == "approve: caller pasted <redacted>"

    before = raw
    for field, over in (("choice", {"choice": SECRET, "basis_id": "b-narrow"}),):
        with pytest.raises(lifecycle.LifecycleInputError) as caught:
            lifecycle.record_request(
                store,
                meta,
                decision_id=decision_id,
                result=_result(**over),
                material=_material(),
                preparation=_preparation(),
                event_id="t10-secret-choice",
            )
        assert field in str(caught.value)
        assert SECRET not in str(caught.value)
        assert _raw(store) == before


def test_an_over_long_note_is_refused_not_truncated(store):
    meta = _started(store)
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_note(
            store,
            meta,
            decision_id=_decision_id(meta),
            pm_note="x" * (wire.NOTE_TEXT_BYTES + 1),
            prepared_at=PREPARED_AT,
        )
    assert "pm_note" in str(caught.value)
    assert "not truncated" in str(caught.value)
    assert _raw(store) == before


def test_null_and_empty_progress_axes_stay_distinct_in_the_new_facts(store):
    before = _state("not-queued", source="worker-registry", completed=[], remaining=None, blockers=[])
    meta = _started(store, task_before=before)
    decision_id = _decision_id(meta)
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
        task_before=before,
    ).recorded
    after = _state("needs-clarification", completed=None, remaining=[], blockers=["waiting for review"])
    assert lifecycle.record_terminal(
        store,
        meta,
        decision_id=decision_id,
        terminal="incomplete",
        reason="review still pending",
        task_after=after,
    ).recorded

    request = _row(store, "request")
    terminal = _row(store, "terminal")
    assert request["task_before"]["completed"] == []
    assert request["task_before"]["remaining"] is None
    assert terminal["task_after"]["completed"] is None
    assert terminal["task_after"]["remaining"] == []


def test_the_new_facts_are_read_by_the_current_history_reader(tmp_path, redactor):
    import decision_history

    control = tmp_path / "proj"
    (control / ".agenticdoc").mkdir(parents=True)
    store = lifecycle.LifecycleStore.production(control, redact=redactor, warn=lambda line: None)
    before = _state("running", completed=[], remaining=["split"], blockers=None)
    meta = _meta(task_before=before)
    decision_id = _decision_id(meta)
    assert lifecycle.record_start(store, meta, decision_id=decision_id).recorded
    assert lifecycle.record_note(
        store, meta, decision_id=decision_id, pm_note="prepared note", prepared_at=PREPARED_AT
    ).recorded
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
        task_before=before,
    ).recorded
    assert lifecycle.record_executed(
        store, meta, decision_id=decision_id, dp=DP, action="split", result="split the file"
    ).recorded
    assert lifecycle.record_settled(store, meta, decision_id=decision_id, dp=DP, outcome="ok").recorded
    after = _state("done", source="dispatch-result", completed=["two patches"], remaining=[], blockers=[])
    assert lifecycle.record_terminal(
        store, meta, decision_id=decision_id, terminal="completed", reason="landed", task_after=after
    ).recorded

    snapshot = decision_history.load_history(control, redact=redactor)
    assert snapshot.stats.unknown_kind == 0
    assert snapshot.stats.unknown_lifecycle == 0
    assert snapshot.stats.lifecycle_damaged == 0
    assert snapshot.stats.invalid_ids == 0
    assert snapshot.stats.unlinked_events == 0
    assert snapshot.stats.foreign_rows == 0
    assert snapshot.stats.lifecycle_events >= 6
    record = next(item for item in snapshot.records if item.decision_id == decision_id)
    assert record.key == "mw-demo"
    assert record.stages["executed"].state == "recorded"
    assert record.stages["settled"].state == "recorded"
    kinds = [row.get("kind") for row in _rows(store)]
    assert kinds.count("note") == 1
    assert kinds.count("request") == 1
    assert kinds.count("terminal") == 1


# ── T10 R2 (stage A): regressions for the audited lifecycle gaps ───────────
#
# Each block below pins one *specification* fact from the PM disposition
# (evidence/implementation/t05-t10-audit-disposition-20261028/report.md §B) with
# the real writer and the real single-source validators - no stub, no shadow
# module, no fake implementation:
#
# * S1 - a transport refusal and the later real business decision of the same
#   request are different facts, so the deterministic ``event_id`` of the first
#   must not swallow the second; an identical repeat stays idempotent and a
#   *different* choice has to be visible instead of a silent ``duplicate``;
# * S3 - ``dp-auto`` may only record an answer that is one of the PM-prepared
#   ``handling_options``; a missing or invalid candidate set cannot legalise an
#   invented choice, while a choice inside a valid set still records;
# * S5 - ``executed``/``settled`` follow the same non-decreasing ``observed_at``
#   rule the terminal already enforces, and a failed round is never reported as
#   an executed fact;
# * S7 - repeating the creation fact's ``before`` (AC-050: echo, never backfill)
#   also has to work when that snapshot contained a known secret, without ever
#   storing the secret; ``None`` and ``[]`` stay distinct;
# * S4 - a Windows case variant of ``.agenticdoc`` is the same production tree,
#   so the test-scope guard must refuse it (the exact-case path is the control);
# * S9 - the writer's consumed producer fields/reasons stay a subset of the
#   frozen producer tuple and the same frozen reason set (one source only).
#
# Test-only additions. On the current product the S1/S3/S5/S7/S4 items are
# expected red and the controls green; this worker did not execute them.

AUTO_DP = "dp-auto"


def _auto_candidate(candidate_id, label):
    return {
        "id": candidate_id,
        "label": label,
        "description": f"prepared handling {candidate_id}",
        "consequence": f"what follows from {candidate_id}",
        "risk": "bounded by the current gate",
        "conditions": "the PM-prepared gate",
    }


def _auto_material(options):
    return {
        "question": "which prepared handling option applies now?",
        "background": {
            "task_goal": "keep the task moving",
            "current_state": "one blocking fact is known",
            "tried": "the direct path was tried",
            "unknowns": "the remaining cost is unknown",
            "constraints": "no new authority is granted",
        },
        "handling_options": options,
    }


def _auto_preparation(choice, basis_id="b-auto", text="the selected handling option"):
    return {
        "basis_catalog": [
            {
                "id": basis_id,
                "text": text,
                "material_refs": ["question"],
                "applies_to": [choice],
            }
        ],
        "prepared_at": PREPARED_AT,
    }


def _auto_result(choice, basis_id="b-auto", text="the selected handling option"):
    return _result(dp=AUTO_DP, choice=choice, basis_id=basis_id, basis_text=text)


def test_a_refused_request_does_not_swallow_the_later_real_choice(store):
    """S1: the refusal's event id must not hide the later real business choice."""
    meta = _started(store)
    decision_id = _decision_id(meta)
    refused = _result(
        choice=None,
        basis_id=None,
        basis_text=None,
        basis_source=None,
        business_decisions=0,
        reason="bad-response",
        attempts=1,
        transport_attempts=2,
    )
    first = lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=refused,
        material=_material(),
        preparation=_preparation(),
    )
    assert first.recorded is True
    assert _row(store, "request")["business_decisions"] == 0

    second = lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
    )

    requests = [row for row in _rows(store) if row.get("kind") == "request"]
    real = [
        row
        for row in requests
        if row.get("business_decisions") == 1 and row.get("choice") == "narrow"
    ]
    conflict_visible = second.status == "failed" and "conflict" in str(second.error_class)
    assert real or conflict_visible, (
        "S1: the refusal's event id swallowed the later real business decision "
        f"(status={second.status!r}, "
        f"business_decisions={[row.get('business_decisions') for row in requests]})"
    )
    # the refusal row is a recorded fact of its own: it is never rewritten
    assert requests[0].get("reason") == "bad-response"


def test_an_identical_repeated_business_request_stays_idempotent(store):
    """S1 control: the same content twice is one fact, not two."""
    meta = _started(store)
    decision_id = _decision_id(meta)
    first = lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
    )
    assert first.status == "written" and first.recorded is True
    before = _raw(store)

    again = lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
    )
    assert again.status == "duplicate" and again.recorded is True
    assert again.event_id == first.event_id
    assert _raw(store) == before
    assert len([row for row in _rows(store) if row.get("kind") == "request"]) == 1


def test_a_different_choice_for_the_same_request_stays_visible(store):
    """S1: different content under the same request id is never a silent duplicate."""
    meta = _started(store)
    decision_id = _decision_id(meta)
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
    ).recorded is True

    split = _result(
        choice="split",
        basis_id="b-split",
        basis_text="the remaining work is two independent files",
    )
    second = lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=split,
        material=_material(),
        preparation=_preparation(),
    )

    requests = [row for row in _rows(store) if row.get("kind") == "request"]
    written_second = len(requests) == 2 and requests[1].get("choice") == "split"
    conflict_visible = second.status == "failed" and "conflict" in str(second.error_class)
    assert written_second or conflict_visible, (
        "S1: a different business choice was reported as a duplicate without any "
        f"conflict signal (status={second.status!r}, "
        f"choices={[row.get('choice') for row in requests]})"
    )


@pytest.mark.parametrize(
    "material,choice",
    [
        ({"question": "which prepared handling option applies now?"}, "c-ghost"),
        (_auto_material([_auto_candidate("c-one", "the only option")]), "c-one"),
    ],
    ids=["no-handling-options", "single-candidate-set"],
)
def test_a_dp_auto_choice_outside_the_prepared_candidates_is_not_recorded(
    store, material, choice
):
    """S3: an illegal dp-auto answer is refused before anything is recorded."""
    meta = _started(store)
    decision_id = f"{AUTO_DP}:{meta.logical_id}"
    before = _raw(store)
    with pytest.raises(lifecycle.LifecycleInputError) as caught:
        lifecycle.record_request(
            store,
            meta,
            decision_id=decision_id,
            result=_auto_result(choice),
            material=material,
            preparation=_auto_preparation(choice),
        )
    message = str(caught.value)
    assert "handling_options" in message or "choice" in message or "material" in message
    assert _raw(store) == before


def test_a_dp_auto_choice_inside_the_prepared_candidates_is_recorded(store):
    """S3 control: a real prepared candidate is still a recordable business fact."""
    meta = _started(store)
    decision_id = f"{AUTO_DP}:{meta.logical_id}"
    material = _auto_material(
        [
            _auto_candidate("c-a", "take the prepared option a"),
            _auto_candidate("c-b", "take the prepared option b"),
        ]
    )
    result = lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_auto_result("c-a"),
        material=material,
        preparation=_auto_preparation("c-a"),
    )
    assert result.recorded is True
    row = _row(store, "request")
    assert row["dp"] == AUTO_DP
    assert row["business_decisions"] == 1
    assert row["choice"] == "c-a" and row["basis_id"] == "b-auto"
    assert row["basis_source"] == "pm-prepared"


def test_executed_and_settled_observations_stay_non_decreasing(store):
    """S5: executed/settled observations are non-decreasing like the terminal."""
    before = _state("running", completed=[], remaining=["split the file"], blockers=None)
    meta = _started(store, task_before=before)
    decision_id = _decision_id(meta)
    # legal control: an increasing observation order is still accepted
    assert lifecycle.record_executed(
        store,
        meta,
        decision_id=decision_id,
        dp=DP,
        action="split",
        result="split the file",
        task_after=_state(observed_at="2026-10-27T09:00:00+00:00"),
    ).recorded is True
    assert lifecycle.record_settled(
        store,
        meta,
        decision_id=decision_id,
        dp=DP,
        outcome="ok",
        task_after=_state(
            "done", source="dispatch-result", observed_at="2026-10-27T10:00:00+00:00"
        ),
    ).recorded is True
    before_bytes = _raw(store)

    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_settled(
            store,
            meta,
            decision_id=decision_id,
            dp=DP,
            outcome="rework",
            event_id="t10-order-settled",
            task_after=_state(
                "done", source="dispatch-result", observed_at="2026-10-27T09:30:00+00:00"
            ),
        )
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_executed(
            store,
            meta,
            decision_id=decision_id,
            dp=DP,
            action="continue",
            result="older observation",
            event_id="t10-order-executed",
            task_after=_state(observed_at="2026-10-27T09:15:00+00:00"),
        )
    assert _raw(store) == before_bytes


def test_a_failed_executed_round_is_never_recorded_as_executed(tmp_path, redactor):
    """S5 control: a failed round reports failure and writes no executed fact."""
    store = lifecycle.LifecycleStore.test(
        tmp_path / "decide-test",
        project_id="proj-test",
        redact=redactor,
        lock_budget_s=0.05,
        lock_retries=2,
        warn=lambda line: None,
    )
    meta = _started(store)
    decision_id = _decision_id(meta)
    lock = store.sink.with_name(store.sink.name + ".lock")
    lock.write_text("held", encoding="utf-8")

    result = lifecycle.record_executed(
        store,
        meta,
        decision_id=decision_id,
        dp=DP,
        action="record",
        result="not really executed",
    )
    assert result.status == "failed"
    assert result.recorded is False
    assert result.error_class == "lock-timeout"
    assert not any(row.get("lifecycle") == "executed" for row in _rows(store))


def test_a_secret_bearing_creation_before_can_be_repeated(store):
    """S7: the recorded before is repeatable even when it held a known secret."""
    before = _state(
        "running", completed=[SECRET + " private step"], remaining=[], blockers=None
    )
    meta = _started(store, task_before=before)
    decision_id = _decision_id(meta)

    result = lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=_result(),
        material=_material(),
        preparation=_preparation(),
        task_before=before,
    )
    assert result.recorded is True
    row = _row(store, "request")
    assert row["task_before"]["completed"] == ["<redacted> private step"]
    # a repeated snapshot keeps the recorded axes: [] is observed, None is not
    assert row["task_before"]["remaining"] == []
    assert row["task_before"]["blockers"] is None
    assert SECRET.encode() not in _raw(store)


@pytest.mark.skipif(
    os.name != "nt", reason="the case-insensitive path rule is a Windows fact"
)
@pytest.mark.parametrize(
    "relative",
    [
        (".AgenticDoc", "_autopilot", "decisions-wire.jsonl"),
        (".AgenticDoc", "lifecycle.jsonl"),
    ],
    ids=["wire-sink", "lifecycle-sink"],
)
def test_a_case_variant_agenticdoc_path_is_refused_in_test_scope(tmp_path, relative):
    """S4: on Windows a case variant is the same production tree and is refused."""
    sink = tmp_path.joinpath(*relative)
    with pytest.raises(wire.WireScopeError):
        wire.WireScope(
            sink=sink,
            project_id="proj-test",
            scope_kind="test",
            redact=wire.SubstringRedactor([SECRET]),
        )


@pytest.mark.parametrize(
    "relative",
    [
        (".agenticdoc", "_autopilot", "decisions-wire.jsonl"),
        (".agenticdoc", "lifecycle.jsonl"),
    ],
    ids=["wire-sink", "lifecycle-sink"],
)
def test_the_exact_agenticdoc_path_is_refused_in_test_scope(tmp_path, relative):
    """S4 control: the exact-case production path is already refused."""
    sink = tmp_path.joinpath(*relative)
    with pytest.raises(wire.WireScopeError):
        wire.WireScope(
            sink=sink,
            project_id="proj-test",
            scope_kind="test",
            redact=wire.SubstringRedactor([SECRET]),
        )


def test_the_writer_consumes_the_producers_frozen_prepared_contract():
    """S9: one frozen producer contract, no second vocabulary in the writer."""
    assert set(lifecycle.REQUEST_RESULT_FIELDS) <= set(decision._PREPARED_RESULT_FIELDS)
    assert lifecycle.REQUEST_REASONS == decision._PREPARED_REASONS
    assert lifecycle.BASIS_SOURCE == decision_points.BASIS_SOURCE
    # the one dynamic entry has no static menu: its legal set is the prepared set
    assert decision_points.resolve_entry_choices(AUTO_DP) == ()
    options = [
        _auto_candidate("c-a", "take the prepared option a"),
        _auto_candidate("c-b", "take the prepared option b"),
    ]
    assert decision_points.resolve_entry_choices(AUTO_DP, _auto_material(options)) == (
        "c-a",
        "c-b",
    )
