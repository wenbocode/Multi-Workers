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
import io
import json
import os
import pathlib
import re
import sys

import pytest

import decision_lifecycle as lifecycle
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
