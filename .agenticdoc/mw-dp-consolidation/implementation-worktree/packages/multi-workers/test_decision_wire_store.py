"""
test_decision_wire_store.py - T02 side-ledger store (mw-decision-dashboard).

Covers design §4.4 (event schema), §9 (capture/redact/limit/lock/short-write/
tail/fsync/read-side) and the RQ5 corrections:

* one explicit WireScope + CallState per logical call; ContextVar is only the
  in-process transport, ``None`` means zero writes (probe paths stay silent);
* ``call_id`` is created by the logical call, ``attempt_index`` only by the
  transport hook - the store never invents an id;
* a missing secret redactor is fail-closed: metadata only, never the raw text;
* redact first, then truncate by *bytes* of the chosen encoding, then scrub a
  partial secret left at either boundary; the persisted hash is the hash of the
  stored text, never of the raw wire bytes;
* the serialized JSON line (not the text segment) is what must fit 64 KiB;
* append = short lock budget + tail newline repair + short-write loop + fsync,
  failures aggregated into one warning per logical call and never raised into
  the caller's business result;
* the reader tolerates bad JSON, bad UTF-8, unknown schema, oversized lines,
  half lines and rotation.

Every fixture is an isolated tmp tree. No production archive / authority /
signoff / triage path is read or written here; no network, no shared service.
"""
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import decision_wire as wire
import mw_common

SECRET = "TEST-SECRET-abcdef0123456789"
SECRET_B = SECRET.encode()

# A realistic >= 120 char, non-periodic credential. The bounded 64 char tail
# window that P0-1 reported can only pass by luck on a periodic value, so every
# long-secret fixture below uses this one and asserts len >= 120.
LONG_SECRET = (
    "sk-live-4f9c2b7e-Authorization-Bearer-"
    "0123456789abcdefghijklmnopqrstuvwxyz"
    "QWERTYUIOPASDFGHJKLZXCVBNM-abcdefghij"
    "9d8c7b6a5f4e3d2c1b0a"
)
LONG_SECRET_B = LONG_SECRET.encode()


def _no_secret_prefix_at_tail(text: str, secret: str) -> bool:
    """True when no 1..len(secret)-1 char secret prefix ends ``text``."""
    return not any(text.endswith(secret[:size]) for size in range(1, len(secret)))


def _symlink_dir(target: pathlib.Path, link: pathlib.Path) -> None:
    """Real symlink fixture; explicit skip (never a junction stand-in) elsewhere."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):  # pragma: no cover - platform
        pytest.skip("directory symlinks are not available on this platform")
    if os.path.realpath(link) != os.path.realpath(target):  # pragma: no cover - platform
        pytest.skip("directory symlinks are not honoured on this platform")


class WarningSink:
    """Collects the aggregated capture warnings instead of writing to stderr."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


@pytest.fixture
def warnings() -> WarningSink:
    return WarningSink()


@pytest.fixture
def redactor() -> wire.SubstringRedactor:
    return wire.SubstringRedactor([SECRET])


@pytest.fixture
def scope(tmp_path: pathlib.Path, redactor: wire.SubstringRedactor, warnings: WarningSink) -> wire.WireScope:
    return wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="proj-test",
        redact=redactor,
        warn=warnings,
    )


def _read_lines(path: pathlib.Path) -> list[bytes]:
    return path.read_bytes().split(b"\n")[:-1]


def _rows(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in _read_lines(path)]


def _write_lines(path: pathlib.Path, lines: list[bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(line + b"\n" for line in lines))


def _event_bytes(row: dict) -> bytes:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# ── identity: UUID logical ids, attempt index owned by CallState ────────────

def test_new_call_ids_are_uuid4_hex_and_unique():
    calls = [wire.new_call() for _ in range(5)]
    for state in calls:
        assert re.fullmatch(r"[0-9a-f]{32}", state.call_id)
        assert uuid.UUID(state.call_id).version == 4
        assert state.attempts_started == 0
    assert len({state.call_id for state in calls}) == 5


def test_call_state_attempt_index_is_per_call():
    first = wire.new_call()
    second = wire.new_call()
    assert [first.next_attempt() for _ in range(3)] == [1, 2, 3]
    assert first.attempts_started == 3
    assert second.next_attempt() == 1


# ── WireScope: explicit sink, production/test separation, fail-closed ───────

def test_scope_requires_explicit_sink_and_project_id(tmp_path):
    with pytest.raises(wire.WireScopeError):
        wire.WireScope(sink=None, project_id="proj")
    with pytest.raises(wire.WireScopeError):
        wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="")
    with pytest.raises(wire.WireScopeError):
        wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="proj", scope_kind="other")


def test_test_scope_refuses_the_production_ledger(tmp_path):
    control = tmp_path / "proj"
    production = wire.production_wire_sink(control)
    with pytest.raises(wire.WireScopeError):
        wire.WireScope(
            sink=production,
            project_id="proj",
            scope_kind="test",
            submission_id="sub-1",
        )
    with pytest.raises(wire.WireScopeError):
        wire.WireScope(
            sink=control / ".agenticdoc" / "_autopilot" / "other.jsonl",
            project_id="proj",
            scope_kind="test",
            submission_id="sub-1",
        )


def test_test_scope_is_fail_closed_but_production_is_best_effort(tmp_path, redactor):
    test = wire.test_scope(
        tmp_path / "decide-test", project_id="proj", submission_id="sub-1", redact=redactor
    )
    prod = wire.production_scope(tmp_path / "proj", project_id="proj", redact=redactor)
    assert test.scope_kind == "test"
    assert test.fail_closed is True
    assert prod.scope_kind == "production"
    assert prod.fail_closed is False


def test_project_id_is_stable_and_path_independent(tmp_path, monkeypatch):
    control = tmp_path / "proj"
    control.mkdir()
    pid = wire.project_id_for(control)
    assert re.fullmatch(r"[0-9a-f]{16}", pid)
    assert pid == wire.project_id_for(control / ".")
    assert pid == wire.project_id_for(str(control).upper())
    monkeypatch.chdir(tmp_path)
    assert pid == wire.project_id_for("proj")
    assert wire.project_id_for(tmp_path / "other") != pid


def test_sink_helpers_point_at_the_documented_paths(tmp_path):
    control = tmp_path / "proj"
    assert wire.production_wire_sink(control) == (
        control / ".agenticdoc" / "_autopilot" / "decisions-wire.jsonl"
    )
    assert wire.production_lifecycle_sink(control) == (
        control / ".agenticdoc" / "_autopilot" / "decision-lifecycle.jsonl"
    )
    assert wire.test_wire_sink(tmp_path / "decide-test") == (
        tmp_path / "decide-test" / "wire.jsonl"
    )


# ── context: explicit binding, default None, reset on exit ──────────────────

def test_scope_and_call_context_default_to_none():
    assert wire.current_scope() is None
    assert wire.current_call() is None


def test_use_binds_and_resets_scope_and_call(scope):
    call = wire.new_call()
    with wire.use(scope, call) as (bound_scope, bound_call):
        assert bound_scope is scope
        assert bound_call is call
        assert wire.current_scope() is scope
        assert wire.current_call() is call
    assert wire.current_scope() is None
    assert wire.current_call() is None


def test_use_resets_on_exception(scope):
    with pytest.raises(RuntimeError, match="boom"):
        with wire.use(scope, wire.new_call()):
            raise RuntimeError("boom")
    assert wire.current_scope() is None
    assert wire.current_call() is None


def test_call_context_creates_a_fresh_call(scope):
    with wire.call_context() as call:
        assert isinstance(call, wire.CallState)
        assert wire.current_call() is call
    assert wire.current_call() is None


def test_nested_use_restores_the_outer_binding(tmp_path, redactor):
    outer = wire.WireScope(sink=tmp_path / "a.jsonl", project_id="p", redact=redactor)
    inner = wire.WireScope(sink=tmp_path / "b.jsonl", project_id="p", redact=redactor)
    outer_call = wire.new_call()
    inner_call = wire.new_call()
    with wire.use(outer, outer_call):
        with wire.use(inner, inner_call):
            assert (wire.current_scope(), wire.current_call()) == (inner, inner_call)
        assert (wire.current_scope(), wire.current_call()) == (outer, outer_call)
    assert (wire.current_scope(), wire.current_call()) == (None, None)


def test_thread_context_does_not_inherit_binding(scope):
    def probe():
        return wire.current_scope(), wire.current_call()

    with wire.use(scope, wire.new_call()):
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(probe).result() == (None, None)

        def bound():
            with wire.use(scope, wire.new_call()):
                return wire.current_scope() is scope

        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(bound).result() is True


# ── event schema (design §4.4) ──────────────────────────────────────────────

def test_event_has_schema_and_common_fields(scope):
    event = wire.build_event(scope, "decision-end", fields={"status": "ok"})
    assert event["schema_version"] == wire.SCHEMA_VERSION == 1
    assert uuid.UUID(event["event_id"]).version == 4
    assert event["kind"] == "decision-end"
    assert event["scope"] == "production"
    assert event["project_id"] == "proj-test"
    assert event["origin"] == "unknown"
    assert event["ts"].endswith("+00:00")
    assert re.search(r"T\d\d:\d\d:\d\d\.\d{3}", event["ts"])
    for name in (
        "key",
        "task_key",
        "decision_id",
        "call_id",
        "submission_id",
        "actor",
        "answer_source",
        "capture_status",
    ):
        assert name in event, name
        assert event[name] is None, name
    assert event["status"] == "ok"


def test_event_rejects_unknown_kind(scope):
    with pytest.raises(wire.WireScopeError):
        wire.build_event(scope, "probe", fields={})


def test_event_rejects_unknown_fields(scope):
    # A misspelled key used to become a silent null (lost provenance). Internal
    # builders are all in-repo, so the store fails closed instead of guessing.
    with pytest.raises(wire.WireScopeError) as exc:
        wire.build_event(
            scope,
            "decision-end",
            fields={"status": "ok", "bogus_key": "x", "actor_id": "nope"},
        )
    assert "bogus_key" in str(exc.value)
    assert "actor_id" in str(exc.value)


def test_attempt_event_requires_a_call_state(scope):
    with pytest.raises(wire.WireScopeError):
        wire.attempt_start_event(scope, None, request=b"x", url_path="/v1/decisions")


def test_transport_hook_without_a_call_is_a_silent_skip(scope):
    result = wire.record_attempt_start(scope, None, request=b"x", url_path="/v1/decisions")
    assert result.status == "skipped"
    assert result.event_id is None
    assert not scope.sink.exists()


def test_attempt_index_increments_per_post_not_per_call(scope):
    call = wire.new_call()
    first = wire.record_attempt_start(scope, call, request=b'{"a":1}', url_path="/v1/decisions")
    second = wire.record_attempt_start(scope, call, request=b'{"a":2}', url_path="/v1/decisions")
    assert (first.status, second.status) == ("written", "written")
    starts = [row for row in _rows(scope.sink) if row["kind"] == "attempt-start"]
    assert [row["attempt_index"] for row in starts] == [1, 2]
    assert {row["call_id"] for row in starts} == {call.call_id}
    assert call.attempts_started == 2


def test_decision_event_uses_the_last_call_of_its_scope(tmp_path, redactor):
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    fresh = wire.decision_end_event(scope, status="ok", archive="created")
    assert fresh["call_id"] is None

    call = wire.new_call()
    wire.record_attempt_start(scope, call, request=b"x", url_path="/v1/decisions")
    after = wire.decision_end_event(scope, status="ok", archive="created")
    assert after["call_id"] == call.call_id


def test_serialized_shrink_never_persists_a_secret_prefix(tmp_path, redactor):
    # The 75% cut lands inside the 8-byte secret prefix at position 600.
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=redactor,
        segment_cap=24576,
        line_cap=1200,
    )
    payload = b"a" * 600 + SECRET_B[:8] + b"b" * 200
    event = wire.book_snapshot_event(scope, book=payload)
    line, fitted = wire.serialize_event(scope, event)
    book = fitted["book"]
    assert isinstance(book, dict)
    assert book["boundary_scrubbed"] is True
    assert len(line) <= 1200
    if isinstance(book["text"], str):
        assert not any(
            book["text"].endswith(SECRET[:size]) for size in range(4, len(SECRET))
        )


def test_event_actor_and_answer_source_are_explicit(scope):
    event = wire.build_event(
        scope,
        "lifecycle",
        fields={"lifecycle": "human-answer", "reason": "manual"},
        actor=("human", "user-explicit"),
        answer_source="model",
    )
    assert event["actor"] == {"kind": "human", "id": "user-explicit"}
    assert event["answer_source"] == "model"


# ── capture: decode, redact, truncate, hash, honesty flags ──────────────────

def test_capture_byte_exact_plain_text(scope):
    raw = b'{"state":"ok"}'
    cap = scope.capture(raw)
    assert cap.text == '{"state":"ok"}'
    assert cap.encoding == "utf-8"
    assert cap.wire_len == len(raw) == cap.stored_len
    assert cap.captured_redacted_sha256 == hashlib.sha256(raw).hexdigest()
    assert cap.byte_exact is True
    assert cap.redactions == 0
    assert cap.truncated is cap.read_capped is cap.decode_errors is False
    assert cap.boundary_scrubbed is False
    assert cap.text_omitted is False


def test_capture_redacts_before_truncating(tmp_path, redactor):
    # A cap shorter than the secret proves the order: truncate-first would
    # persist a secret prefix, redact-first stores the placeholder only.
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor, segment_cap=20
    )
    raw = SECRET_B + b"x" * 100
    cap = scope.capture(raw)
    assert cap.redactions == 1
    assert SECRET not in cap.text
    assert cap.truncated is True
    assert cap.byte_exact is False
    stored = cap.text.encode(cap.encoding)
    assert cap.stored_len == len(stored) == len(stored[:20])
    assert cap.captured_redacted_sha256 == hashlib.sha256(stored).hexdigest()


def test_capture_counts_every_occurrence(scope):
    cap = scope.capture(SECRET_B + b"|" + SECRET_B)
    assert cap.redactions == 2
    assert SECRET not in cap.text


def test_capture_without_redactor_omits_text_fail_closed(tmp_path, warnings):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl", project_id="p", redact=None, warn=warnings
    )
    cap = scope.capture(SECRET_B)
    assert cap.text is None
    assert cap.text_omitted is True
    assert cap.captured_redacted_sha256 is None
    assert cap.stored_len == 0
    assert cap.wire_len == len(SECRET_B)
    assert cap.byte_exact is False

    call = wire.new_call()
    result = wire.record_attempt_start(scope, call, request=SECRET_B, url_path="/v1/decisions")
    assert result.status == "written"
    assert SECRET_B not in scope.sink.read_bytes()
    row = _rows(scope.sink)[0]
    assert row["request"]["text"] is None
    assert row["request"]["text_omitted"] is True
    assert row["capture_status"] == "failed"


def test_persisted_ledger_never_contains_the_secret(scope):
    call = wire.new_call()
    wire.record_attempt_start(
        scope, call, request=(SECRET + "|" + SECRET).encode(), url_path="/v1/decisions"
    )
    wire.record_attempt_end(
        scope, call, response=SECRET_B * 2, latency_ms=3, http_status=200
    )
    data = scope.sink.read_bytes()
    assert SECRET_B not in data
    rows = _rows(scope.sink)
    assert rows[0]["request"]["redactions"] == 2
    assert rows[1]["response"]["redactions"] == 2
    assert {row["capture_status"] for row in rows} == {"partial"}


def test_capture_invalid_utf8_uses_lossless_latin1(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor, segment_cap=4096
    )
    raw = b"\xff\xfe{\"a\":1}"
    cap = scope.capture(raw)
    assert cap.encoding == "latin-1"
    assert cap.decode_errors is True
    assert cap.byte_exact is False
    assert cap.text.encode("latin-1") == raw
    assert cap.wire_len == cap.stored_len


def test_capture_truncates_at_the_byte_segment_cap(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor, segment_cap=64
    )
    cap = scope.capture("中".encode() * 100)
    assert cap.truncated is True
    assert cap.stored_len <= 64
    stored = cap.text.encode(cap.encoding)
    assert stored == "中".encode() * (64 // 3)
    assert cap.captured_redacted_sha256 == hashlib.sha256(stored).hexdigest()


def test_capture_scrubs_a_secret_split_at_the_segment_boundary(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor, segment_cap=64
    )
    raw = b"a" * (64 - 8) + SECRET_B[:8] + b"zzzz"
    cap = scope.capture(raw)
    stored = cap.text.encode(cap.encoding)
    assert len(stored) <= 64
    assert cap.truncated is True
    assert cap.boundary_scrubbed is True
    assert not stored.endswith(SECRET_B[:8])


def test_capture_scrubs_a_secret_split_at_the_read_boundary(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor, segment_cap=64
    )
    head_cap = scope.segment_cap + scope.read_window
    raw = b"a" * (head_cap - 8) + SECRET_B[:8] + b"zzzz"
    cap = scope.capture(raw)
    assert cap.read_capped is True
    assert cap.boundary_scrubbed is True
    assert SECRET_B[:8] not in cap.text.encode(cap.encoding)


def test_capture_of_none_is_not_recorded(scope):
    assert scope.capture(None) is None
    row = wire.attempt_start_event(scope, wire.new_call(), request=None, url_path="/x")
    assert row["request"] is None


def test_capture_hash_never_hashes_the_raw_wire_bytes(scope):
    cap = scope.capture(SECRET_B + b"x" * 100)
    assert cap.captured_redacted_sha256 != hashlib.sha256(SECRET_B + b"x" * 100).hexdigest()
    assert cap.captured_redacted_sha256 == hashlib.sha256(
        cap.text.encode(cap.encoding)
    ).hexdigest()


# ── serialized line limit (64 KiB after JSON, not per segment) ─────────────

def test_serialized_line_shrinks_text_until_it_fits(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=redactor,
        segment_cap=24576,
        line_cap=4096,
    )
    call = wire.new_call()
    event = wire.attempt_start_event(
        scope, call, request=b"z" * 200000, url_path="/v1/decisions"
    )
    line, fitted = wire.serialize_event(scope, event)
    assert len(line) <= 4096
    assert line.endswith(b"\n")
    row = json.loads(line.decode("utf-8"))
    assert row["request"]["truncated"] is True
    assert row["request"]["byte_exact"] is False
    assert row["request"]["stored_len"] == len(row["request"]["text"].encode("utf-8"))
    assert row["request"]["captured_redacted_sha256"] == hashlib.sha256(
        row["request"]["text"].encode("utf-8")
    ).hexdigest()
    assert len(fitted["request"]["text"].encode("utf-8")) < 24576


def test_serialized_line_omits_text_when_metadata_alone_is_too_big(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=redactor,
        segment_cap=24576,
        line_cap=900,
    )
    event = wire.build_event(
        scope, "book-snapshot", fields={"book": scope.capture(b"b" * 24576)}
    )
    line, fitted = wire.serialize_event(scope, event)
    assert len(line) <= 900
    row = json.loads(line.decode("utf-8"))
    assert row["book"]["text"] is None
    assert row["book"]["text_omitted"] is True
    assert row["book"]["captured_redacted_sha256"] is None


def test_serialized_line_falls_back_to_a_minimal_capture_failed_row(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=redactor,
        segment_cap=24576,
        line_cap=50,
    )
    event = wire.build_event(
        scope, "book-snapshot", fields={"book": scope.capture(b"b" * 24576)}
    )
    line, fitted = wire.serialize_event(scope, event)
    row = json.loads(line.decode("utf-8"))
    assert row["line_error"] == "line-cap"
    assert row["capture_status"] == "failed"
    assert len(line) == len(_event_bytes(row)) + 1


def test_serialized_line_keeps_cjk_unescaped_and_has_no_inner_newline(scope):
    event = wire.build_event(
        scope, "book-snapshot", fields={"book": scope.capture("中文\n正文")}
    )
    line, _ = wire.serialize_event(scope, event)
    assert "中文".encode("utf-8") in line
    assert line.count(b"\n") == 1


# ── append: lock budget, tail repair, short write, fsync, warnings ──────────

def test_append_event_writes_one_jsonl_line(scope):
    call = wire.new_call()
    result = wire.record_attempt_end(
        scope,
        call,
        response=b'{"ok":true}',
        latency_ms=7,
        http_status=200,
        content_type="application/json",
    )
    assert result.status == "written"
    assert result.event_id is not None
    lines = _read_lines(scope.sink)
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event_id"] == result.event_id
    assert row["kind"] == "attempt-end"
    assert row["http_status"] == 200
    assert row["usage"] is None
    assert row["usage_source"] == "not-recorded"
    assert row["response"]["byte_exact"] is True


def test_append_short_write_loop_completes_the_line(scope, monkeypatch):
    real_write = os.write
    calls = {"n": 0}

    def trickle(fd, data):
        chunk = bytes(data)[:7]
        calls["n"] += 1
        return real_write(fd, chunk)

    monkeypatch.setattr(os, "write", trickle)
    call = wire.new_call()
    result = wire.record_attempt_start(scope, call, request=b'{"a":1}', url_path="/x")
    assert result.status == "written"
    assert calls["n"] > 1
    rows = _rows(scope.sink)
    assert len(rows) == 1
    assert rows[0]["request"]["text"] == '{"a":1}'


def test_append_fsyncs_before_releasing(scope, monkeypatch):
    real_fsync = os.fsync
    seen: list[int] = []

    def spy(fd):
        seen.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", spy)
    wire.record_attempt_start(scope, wire.new_call(), request=b"x", url_path="/x")
    assert seen


def test_append_terminates_a_dangling_tail_without_truncating(scope):
    scope.sink.parent.mkdir(parents=True, exist_ok=True)
    scope.sink.write_bytes(b'{"old":')
    wire.record_attempt_start(scope, wire.new_call(), request=b"x", url_path="/x")

    data = scope.sink.read_bytes()
    assert data.startswith(b'{"old":\n')
    assert data.endswith(b"\n")
    read = wire.read_events(scope.sink)
    assert read.stats.bad_json == 1
    assert len(read.events) == 1


def test_append_lock_timeout_is_reported_and_keeps_the_foreign_lock(scope):
    scope.sink.parent.mkdir(parents=True, exist_ok=True)
    lock = scope.sink.with_name(scope.sink.name + ".lock")
    lock.write_text("held", encoding="utf-8")

    started = time.monotonic()
    result = wire.record_attempt_start(scope, wire.new_call(), request=b"x", url_path="/x")
    elapsed = time.monotonic() - started

    assert result.status == "failed"
    assert result.error_class == "lock-timeout"
    # The documented budget is 250ms; 0.6s only leaves scheduler/CI slack. A
    # loose 2s bound would also pass while the 250ms budget was ignored.
    assert elapsed < 0.6, f"lock budget ignored: waited {elapsed:.3f}s"
    assert lock.exists()
    assert not scope.sink.exists()
    assert scope.capture_status == "failed"


def _lock_spy(monkeypatch, calls: list[float]) -> None:
    real = mw_common.acquire_lock

    def spy(*args, **kwargs):
        calls.append(time.monotonic())
        return real(*args, **kwargs)

    monkeypatch.setattr(mw_common, "acquire_lock", spy)


def test_append_failure_warns_once_per_logical_call(scope, warnings, monkeypatch):
    scope.sink.parent.mkdir(parents=True, exist_ok=True)
    (scope.sink.with_name(scope.sink.name + ".lock")).write_text("held", encoding="utf-8")
    calls: list[float] = []
    _lock_spy(monkeypatch, calls)
    call = wire.new_call()
    first = wire.record_attempt_start(scope, call, request=b"x", url_path="/x")
    second = wire.record_attempt_end(scope, call, response=b"y", latency_ms=1, http_status=200)

    assert (first.status, second.status) == ("failed", "failed")
    assert len(warnings.messages) == 1
    assert SECRET not in warnings.messages[0]
    assert len(scope.errors) == 2
    assert scope.capture_status == "failed"
    # Design §9: after the first capture failure of a logical call, stop waiting
    # on the lock again (the second event never acquires).
    assert len(calls) == 1
    assert second.error_class == "circuit-open"


def test_failed_call_never_waits_on_the_lock_again(scope, warnings, monkeypatch):
    scope.sink.parent.mkdir(parents=True, exist_ok=True)
    (scope.sink.with_name(scope.sink.name + ".lock")).write_text("held", encoding="utf-8")
    calls: list[float] = []
    _lock_spy(monkeypatch, calls)
    call = wire.new_call()

    wire.record_attempt_start(scope, call, request=b"x", url_path="/x")
    started = time.monotonic()
    second = wire.record_attempt_end(
        scope, call, response=b"y", latency_ms=1, http_status=200
    )
    elapsed = time.monotonic() - started

    assert second.status == "failed"
    assert len(calls) == 1, "the same logical call re-acquired the lock after a failure"
    assert elapsed < 0.05, f"circuit breaker still waited {elapsed:.3f}s"
    assert len(warnings.messages) == 1


def test_scope_level_failure_does_not_repeat_the_lock_budget(tmp_path, redactor, warnings, monkeypatch):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=redactor,
        warn=warnings,
        scope_kind="test",
        submission_id="sub-1",
    )
    scope.sink.parent.mkdir(parents=True, exist_ok=True)
    (scope.sink.with_name(scope.sink.name + ".lock")).write_text("held", encoding="utf-8")
    calls: list[float] = []
    _lock_spy(monkeypatch, calls)

    first = wire.append_event(
        scope, wire.submission_start_event(scope, dp="dp4-failure-handling")
    )
    started = time.monotonic()
    second = wire.append_event(
        scope, wire.submission_end_event(scope, outcome="record-failed")
    )
    elapsed = time.monotonic() - started

    assert (first.status, second.status) == ("failed", "failed")
    assert len(calls) == 1
    assert elapsed < 0.05
    assert len(warnings.messages) == 1


def test_append_creates_parent_directories(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "deep" / "nested" / "wire.jsonl", project_id="p", redact=redactor
    )
    result = wire.record_attempt_start(scope, wire.new_call(), request=b"x", url_path="/x")
    assert result.status == "written"
    assert scope.sink.exists()


def test_capture_status_distinguishes_ok_partial_and_failed(tmp_path, redactor):
    exact = wire.WireScope(sink=tmp_path / "a.jsonl", project_id="p", redact=redactor)
    partial = wire.WireScope(sink=tmp_path / "b.jsonl", project_id="p", redact=redactor)
    failed = wire.WireScope(sink=tmp_path / "c.jsonl", project_id="p", redact=None)

    assert wire.record_attempt_start(
        exact, wire.new_call(), request=b'{"a":1}', url_path="/x"
    ).capture_status == "ok"
    assert wire.record_attempt_start(
        partial, wire.new_call(), request=SECRET_B, url_path="/x"
    ).capture_status == "partial"
    assert wire.record_attempt_start(
        failed, wire.new_call(), request=b"x", url_path="/x"
    ).capture_status == "failed"


def test_merge_capture_status_prefers_the_worst_value():
    assert wire.merge_capture_status(None, None) is None
    assert wire.merge_capture_status("ok", None) == "ok"
    assert wire.merge_capture_status("ok", "partial") == "partial"
    assert wire.merge_capture_status("partial", "failed", "ok") == "failed"


def test_serialize_failure_is_failed_status_not_an_exception(scope):
    event = wire.build_event(scope, "decision-end", fields={"status": object()})
    result = wire.append_event(scope, event)
    assert result.status == "failed"
    assert result.error_class == "serialize"
    assert scope.capture_status == "failed"
    assert not scope.sink.exists()


# ── read side: bad rows, half lines, unknown schema, rotation ──────────────

def test_read_events_missing_file_is_empty(tmp_path):
    read = wire.read_events(tmp_path / "absent.jsonl")
    assert read.events == []
    assert read.stats.rows == 0
    assert read.offset == 0


def test_read_events_reports_bad_json_bad_utf8_and_unknown_schema(tmp_path):
    sink = tmp_path / "wire.jsonl"
    valid = _event_bytes({"schema_version": 1, "event_id": "e1", "kind": "call-end"})
    _write_lines(
        sink,
        [
            valid,
            b"{bad json",
            b'\xff\xfe{"a":1}',
            _event_bytes({"schema_version": 2, "event_id": "e2"}),
            _event_bytes({"event_id": "e3"}),
            b"   ",
        ],
    )
    read = wire.read_events(sink)
    assert [row["event_id"] for row in read.events] == ["e1"]
    assert read.stats.rows == 1
    assert read.stats.bad_json == 1
    assert read.stats.bad_utf8 == 1
    assert read.stats.unknown_schema == 2
    assert read.stats.incomplete_tail == 0


def test_read_events_reports_an_incomplete_tail_and_resumes_from_it(tmp_path):
    sink = tmp_path / "wire.jsonl"
    first = _event_bytes({"schema_version": 1, "event_id": "e1", "kind": "call-end"})
    sink.write_bytes(first + b"\n" + b'{"schema_version":1,"event_id":"e2",')
    read = wire.read_events(sink)
    assert [row["event_id"] for row in read.events] == ["e1"]
    assert read.stats.incomplete_tail == 1

    with sink.open("ab") as handle:
        handle.write(b'"kind":"call-end"}\n')
    resumed = wire.read_events(sink, offset=read.offset)
    assert [row["event_id"] for row in resumed.events] == ["e2"]


def test_read_events_skips_an_oversized_line_and_continues(tmp_path):
    sink = tmp_path / "wire.jsonl"
    valid = _event_bytes({"schema_version": 1, "event_id": "e1", "kind": "call-end"})
    _write_lines(sink, [b"x" * 600, valid])
    read = wire.read_events(sink, line_cap=256)
    assert read.stats.oversized_line == 1
    assert [row["event_id"] for row in read.events] == ["e1"]


def test_read_events_detects_rotation(tmp_path):
    sink = tmp_path / "wire.jsonl"
    valid = _event_bytes({"schema_version": 1, "event_id": "e1", "kind": "call-end"})
    _write_lines(sink, [valid])
    read = wire.read_events(sink, offset=10_000)
    assert read.stats.rotated == 1
    assert [row["event_id"] for row in read.events] == ["e1"]


def test_summarize_counts_calls_attempts_and_decisions(tmp_path, redactor):
    sink = tmp_path / "wire.jsonl"
    first = wire.WireScope(
        sink=sink, project_id="p", redact=redactor, decision_id="dp4-failure-handling:t1"
    )
    second = wire.WireScope(
        sink=sink, project_id="p", redact=redactor, decision_id="dp4-failure-handling:t1"
    )
    call_a = wire.new_call()
    call_b = wire.new_call()

    wire.record_attempt_start(first, call_a, request=b"a", url_path="/x")
    wire.record_attempt_start(first, call_a, request=b"a", url_path="/x")
    wire.record_attempt_end(first, call_a, response=b"r", latency_ms=1, http_status=200)
    wire.append_event(
        first, wire.call_end_event(first, call_a, attempts=1, latency_ms=1, wire_attempts=2)
    )
    wire.append_event(first, wire.decision_end_event(first, status="ok", archive="created"))

    wire.record_attempt_start(second, call_b, request=b"b", url_path="/x")
    wire.append_event(second, wire.decision_end_event(second, status="ok", archive="replayed"))

    read = wire.read_events(sink)
    counts = wire.summarize(read.events)
    assert counts.calls == 2
    assert counts.attempts == 3
    assert counts.decisions == 1
    assert counts.events == len(read.events)
    assert counts.capture_failed == 0


# ── production / test isolation ─────────────────────────────────────────────

def test_test_scope_writes_only_its_own_sink(tmp_path, redactor):
    control = tmp_path / "proj"
    production = wire.production_wire_sink(control)
    test = wire.test_scope(
        tmp_path / "decide-test", project_id="p", submission_id="sub-1", redact=redactor
    )
    result = wire.append_event(
        test,
        wire.build_event(
            test, "submission-start", fields={"dp": "dp4-failure-handling", "outcome": "started"}
        ),
    )
    assert result.status == "written"
    assert test.sink.exists()
    assert not production.exists()
    row = _rows(test.sink)[0]
    assert row["scope"] == "test"
    assert row["submission_id"] == "sub-1"


# ── P0-1: arbitrary-length secrets at every truncation point ────────────────

def test_long_secret_fixture_is_long_enough_and_non_periodic():
    assert len(LONG_SECRET) >= 120
    # Non-periodic: no proper prefix repeats at a period <= 64, so a 64 char
    # tail window cannot match a longer leftover prefix by luck.
    for period in range(1, 65):
        assert LONG_SECRET[:64] != LONG_SECRET[period : period + 64]


def test_long_secret_is_fully_removed_when_uncut(tmp_path):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([LONG_SECRET]),
    )
    cap = scope.capture(b"before " + LONG_SECRET_B + b" after")
    assert cap.redactions == 1
    assert LONG_SECRET not in cap.text
    assert "<redacted>" in cap.text


def test_long_secret_prefix_split_at_the_segment_boundary_is_scrubbed(tmp_path):
    # 90 chars of a 130 char secret cross the segment cap: the reported defect
    # only inspects the last 64 chars, so this leftover used to be persisted.
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([LONG_SECRET]),
        segment_cap=200,
    )
    raw = b"a" * (200 - 90) + LONG_SECRET_B[:90] + b"zzzz"
    cap = scope.capture(raw)
    stored = cap.text.encode(cap.encoding)
    assert cap.truncated is True
    assert cap.boundary_scrubbed is True
    assert LONG_SECRET_B[:90] not in stored
    assert _no_secret_prefix_at_tail(cap.text, LONG_SECRET)
    assert len(stored) == 110


def test_long_secret_prefix_split_at_the_read_boundary_is_scrubbed(tmp_path):
    # read_window=0 makes the read cap identical to the segment cap, so the
    # leftover at the read boundary is exactly what reaches storage.
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([LONG_SECRET]),
        segment_cap=200,
        read_window=0,
    )
    raw = b"a" * 110 + LONG_SECRET_B[:90] + b"q" * 500
    cap = scope.capture(raw)
    assert cap.read_capped is True
    assert cap.boundary_scrubbed is True
    assert _no_secret_prefix_at_tail(cap.text, LONG_SECRET)
    assert LONG_SECRET_B[:90] not in cap.text.encode(cap.encoding)


def test_longer_than_read_window_secret_prefix_is_scrubbed_at_default_caps(tmp_path):
    # At the default caps (24 KiB segment + 4 KiB read window) a leftover prefix
    # is only reachable when it is longer than the read window. The fixed 64
    # char window is wrong for any length; this pins the generic boundary check.
    big_secret = "sk-" + "".join(f"{i:04d}" for i in range(1100))  # 4404 chars
    assert len(big_secret) > wire.READ_WINDOW_BYTES + 64
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([big_secret]),
    )
    head_cap = scope.segment_cap + scope.read_window
    # 4300 leftover chars, 4096 of them inside the read window: 204 secret chars
    # survive the segment trim, i.e. more than the 64 char window can detect.
    leftover = 4300
    raw = b"a" * (head_cap - leftover) + big_secret.encode()[:leftover] + b"q" * 1000
    cap = scope.capture(raw)
    assert cap.read_capped is True
    assert cap.boundary_scrubbed is True
    assert _no_secret_prefix_at_tail(cap.text, big_secret)
    assert cap.stored_len == head_cap - leftover


def test_long_secret_prefix_split_by_the_utf8_trim_is_scrubbed(tmp_path):
    # The read window is small, so the segment trim itself cuts inside the
    # secret and leaves 80 chars at the stored tail (> the old 64 char window).
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([LONG_SECRET]),
        segment_cap=100,
        read_window=5,
    )
    filler = ("中" * 6).encode() + b"ab"  # valid UTF-8, 20 bytes
    raw = filler + LONG_SECRET_B[:85] + b"q" * 200
    cap = scope.capture(raw)
    assert cap.encoding == "utf-8"
    assert cap.read_capped is True
    assert cap.boundary_scrubbed is True
    assert _no_secret_prefix_at_tail(cap.text, LONG_SECRET)
    assert LONG_SECRET_B[:80] not in cap.text.encode("utf-8")
    assert cap.text.encode("utf-8").startswith(filler)


def test_long_secret_prefix_split_at_the_latin1_boundary_is_scrubbed(tmp_path):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([LONG_SECRET]),
        segment_cap=200,
        read_window=0,
    )
    raw = b"\xff\xfe" + b"a" * 108 + LONG_SECRET_B[:90]
    cap = scope.capture(raw)
    assert cap.encoding == "latin-1"
    assert cap.decode_errors is True
    assert cap.boundary_scrubbed is True
    stored = cap.text.encode("latin-1")
    assert LONG_SECRET_B[:90] not in stored
    assert _no_secret_prefix_at_tail(cap.text, LONG_SECRET)


def test_long_secret_prefix_split_by_the_serialized_shrink_is_scrubbed(tmp_path):
    # 75% of 920 chars lands 90 chars into the secret, i.e. deeper than 64.
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([LONG_SECRET]),
        segment_cap=24576,
        line_cap=1200,
    )
    payload = b"a" * 600 + LONG_SECRET_B[:100] + b"b" * 220
    event = wire.build_event(scope, "book-snapshot", fields={"book": scope.capture(payload)})
    line, fitted = wire.serialize_event(scope, event)
    assert len(line) <= 1200
    book = fitted["book"]
    assert isinstance(book, dict)
    assert book["boundary_scrubbed"] is True
    if isinstance(book["text"], str):
        assert _no_secret_prefix_at_tail(book["text"], LONG_SECRET)
        assert LONG_SECRET_B[:90] not in book["text"].encode("utf-8")
    assert LONG_SECRET.encode() not in line


def test_persisted_line_never_holds_a_long_secret_piece(tmp_path):
    # End to end: the written line (not only the row) must be clean.
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([LONG_SECRET]),
        segment_cap=200,
        read_window=0,
    )
    payload = b"a" * 110 + LONG_SECRET_B[:90] + b"q" * 500
    result = wire.record_attempt_start(
        scope, wire.new_call(), request=payload, url_path="/v1/decisions"
    )
    assert result.status == "written"
    data = scope.sink.read_bytes()
    for size in range(4, len(LONG_SECRET)):
        assert LONG_SECRET.encode()[:size] not in data, f"persisted {size} secret chars"


def test_one_to_three_character_boundary_tail_is_scrubbed_and_marked(tmp_path):
    for size in (1, 2, 3):
        scope = wire.WireScope(
            sink=tmp_path / f"wire-{size}.jsonl",
            project_id="p",
            redact=wire.SubstringRedactor([SECRET]),
            segment_cap=64,
        )
        raw = b"a" * (64 - size) + SECRET_B[:size]
        cap = scope.capture(raw)
        stored = cap.text.encode(cap.encoding)
        assert not stored.endswith(SECRET_B[:size]), f"{size} char tail was kept"
        assert cap.boundary_scrubbed is True
        assert len(stored) == 64 - size


# ── P1-1: free-text metadata is redacted before it is clipped ──────────────

def test_lifecycle_free_text_metadata_is_redacted(tmp_path, redactor):
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    event = wire.lifecycle_event(
        scope,
        lifecycle="human-answer",
        reason=f"because {SECRET}",
        answer=f"answer holds {SECRET}",
        evidence=f"evidence {SECRET}",
        result=f"result {SECRET}",
    )
    assert SECRET not in json.dumps(event)
    for name in ("reason", "answer", "evidence", "result"):
        assert "<redacted>" in event[name], name
    # Closed-set values survive untouched.
    assert event["lifecycle"] == "human-answer"


def test_attempt_error_and_issue_metadata_is_redacted(tmp_path, redactor):
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    call = wire.new_call()
    end = wire.attempt_end_event(
        scope,
        call,
        response=None,
        latency_ms=2,
        http_status=500,
        content_type=f"application/json; token={SECRET}",
        error_class=f"Upstream{SECRET}",
        error_detail=f"upstream said {SECRET}",
    )
    assert SECRET not in json.dumps(end)
    assert "<redacted>" in end["error_detail"]
    submit = wire.submission_end_event(
        scope, outcome="record-failed", issues=[f"issue {SECRET}"], retry_of="sub-1"
    )
    assert SECRET not in json.dumps(submit)
    assert "<redacted>" in submit["issues"][0]
    assert submit["retry_of"] == "sub-1"


def test_nested_metadata_containers_are_redacted(tmp_path, redactor):
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    call = wire.new_call()
    event = wire.call_end_event(
        scope,
        call,
        attempts=1,
        latency_ms=3,
        policy={
            "notes": [f"first {SECRET}", {"deep": f"deep {SECRET}"}],
            "budget": 3,
            "enabled": True,
        },
    )
    assert SECRET not in json.dumps(event)
    policy = event["policy"]
    assert "<redacted>" in policy["notes"][0]
    assert "<redacted>" in policy["notes"][1]["deep"]
    assert policy["budget"] == 3
    assert policy["enabled"] is True


def test_free_text_metadata_is_redacted_before_it_is_clipped(tmp_path, redactor):
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    event = wire.call_end_event(
        scope,
        wire.new_call(),
        attempts=1,
        latency_ms=1,
        reason="y" * 500 + f" {SECRET}" + "z" * 100,
    )
    reason = event["reason"]
    assert SECRET not in reason
    assert len(reason.encode("utf-8")) <= wire.REASON_LIMIT
    # Redact first, then clip: the stored prefix is the redacted text.
    assert reason.startswith("y" * 500 + " <redac")


def test_metadata_without_a_redactor_omits_free_text_but_keeps_protocol_values(tmp_path):
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=None)
    decision = wire.decision_end_event(
        scope,
        status="ok",
        archive="created",
        mode="human",
        intent="answer",
        state_digest="abc123",
        questions_version="v3",
        book_ref="book-ref",
        escalated_reason="sensitive reason",
        truncated=["a.md"],
    )
    assert decision["status"] == "ok"
    assert decision["archive"] == "created"
    assert decision["mode"] == "human"
    assert decision["intent"] == "answer"
    assert decision["state_digest"] == "abc123"
    assert decision["questions_version"] == "v3"
    assert decision["book_ref"] == "book-ref"
    assert decision["escalated_reason"] is None
    assert decision["truncated"] is None

    submit = wire.submission_end_event(
        scope, outcome="record-failed", issues=["sensitive issue"], retry_of="sub-1"
    )
    assert submit["outcome"] == "record-failed"
    assert submit["retry_of"] == "sub-1"
    assert submit["issues"] is None

    call = wire.new_call()
    end = wire.attempt_end_event(
        scope,
        call,
        response=None,
        latency_ms=1,
        http_status=500,
        error_class="response-read",
        error_detail="sensitive detail",
        usage={"input_tokens": 3, "model": "sensitive-model"},
    )
    assert end["error_class"] is None
    assert end["error_detail"] is None
    assert end["usage"]["input_tokens"] == 3
    # A mapping key is caller text too: without a redactor the closed-set token
    # counter survives, every other entry is withheld (not kept with null).
    assert "model" not in end["usage"]
    assert end["http_status"] == 500
    assert end["usage_source"] == "response-body"
    assert end["attempt_index"] == 0


def test_identity_keys_stay_join_compatible_even_if_listed_as_a_secret(tmp_path):
    # Precise boundary: identity/enum keys are the join floor and are never
    # rewritten by the store; only caller free text is redacted.
    call = wire.new_call()
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        decision_id="dec-1",
        key="dp4-failure-handling",
        task_key="T02b",
        redact=wire.SubstringRedactor([call.call_id, "dp4-failure-handling"]),
    )
    event = wire.attempt_start_event(scope, call, request=b"x", url_path="/v1/decisions")
    assert event["call_id"] == call.call_id
    assert event["decision_id"] == "dec-1"
    assert event["key"] == "dp4-failure-handling"
    assert event["task_key"] == "T02b"
    assert event["project_id"] == "p"
    assert event["kind"] == "attempt-start"
    assert uuid.UUID(event["event_id"]).version == 4


# ── P2-1: a shrunk line recomputes capture_status ─────────────────────────

def test_serialized_shrink_recomputes_capture_status(tmp_path, redactor):
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=redactor,
        segment_cap=24576,
        line_cap=1200,
    )
    call = wire.new_call()
    event = wire.attempt_end_event(
        scope, call, response=b"z" * 2000, latency_ms=1, http_status=200
    )
    assert event["capture_status"] == "ok"
    line, fitted = wire.serialize_event(scope, event)
    assert len(line) <= 1200
    assert fitted["response"]["truncated"] is True
    assert fitted["capture_status"] == "partial"
    row = json.loads(line.decode("utf-8"))
    assert row["capture_status"] == "partial"


# ── P2-3: project identity is canonical (symlink independent) ─────────────

def test_project_id_resolves_symlinked_control_to_one_identity(tmp_path):
    control = tmp_path / "proj"
    control.mkdir()
    link = tmp_path / "proj-link"
    _symlink_dir(control, link)
    assert wire.project_id_for(link) == wire.project_id_for(control)


# ── P2-5: an orphan attempt-end never raises the start counter ────────────

def test_orphan_attempt_end_does_not_raise_the_start_counter(scope):
    call = wire.new_call()
    orphan = wire.attempt_end_event(
        scope, call, response=b"x", latency_ms=1, http_status=200, attempt_index=5
    )
    assert call.attempts_started == 0
    assert orphan["attempt_index"] == 0

    call_end = wire.call_end_event(scope, call, attempts=1, latency_ms=1)
    assert call_end["wire_attempts"] == 0
    assert call_end["zero_call"] is True

    # A paired start/end still numbers normally.
    started = wire.new_call()
    start = wire.attempt_start_event(scope, started, request=b"x", url_path="/x")
    end = wire.attempt_end_event(scope, started, response=b"y", latency_ms=1, http_status=200)
    assert (start["attempt_index"], end["attempt_index"]) == (1, 1)
    assert started.attempts_started == 1
    # An end claiming a higher index than any start neither raises nor lies.
    high = wire.attempt_end_event(
        scope, started, response=b"y", latency_ms=1, http_status=200, attempt_index=9
    )
    assert high["attempt_index"] == 1
    assert started.attempts_started == 1


# ── P1-3: test sink isolation survives symlinks / junctions ────────────────

def test_test_scope_refuses_a_symlink_into_the_production_tree(tmp_path):
    control = tmp_path / "proj"
    production_dir = control / ".agenticdoc" / "_autopilot"
    production_dir.mkdir(parents=True)
    link = tmp_path / "decide-test-link"
    _symlink_dir(production_dir, link)

    with pytest.raises(wire.WireScopeError) as exc:
        wire.WireScope(
            sink=link / "wire.jsonl",
            project_id="p",
            scope_kind="test",
            submission_id="sub-1",
        )
    assert "isolated" in str(exc.value)
    # Validation never creates the target (no mkdir probe).
    assert list(production_dir.glob("wire*")) == []


def test_test_scope_refuses_a_symlinked_evidence_path_into_production(tmp_path):
    control = tmp_path / "proj"
    production_dir = control / ".agenticdoc" / "_autopilot"
    production_dir.mkdir(parents=True)
    link = tmp_path / "evidence-link"
    _symlink_dir(production_dir, link)

    with pytest.raises(wire.WireScopeError):
        wire.WireScope(
            sink=tmp_path / "wire.jsonl",
            project_id="p",
            scope_kind="test",
            submission_id="sub-1",
            evidence_path=link / "triage-decisions.jsonl",
        )
    assert list(production_dir.iterdir()) == []


def test_test_scope_accepts_a_symlinked_isolated_root(tmp_path):
    real_root = tmp_path / "real-test-root"
    real_root.mkdir()
    link = tmp_path / "test-root-link"
    _symlink_dir(real_root, link)
    scope = wire.WireScope(
        sink=wire.test_wire_sink(link),
        project_id="p",
        scope_kind="test",
        submission_id="sub-1",
        redact=wire.SubstringRedactor([SECRET]),
    )
    result = wire.append_event(
        scope, wire.submission_start_event(scope, dp="dp4-failure-handling")
    )
    assert result.status == "written"
    assert (real_root / "wire.jsonl").exists()


# ── N-1: usage/policy mapping keys are untrusted text, not schema labels ───

SECRET_ALT = "TEST-SECRET-2-0123456789abcdef"


def _usage_event(scope: wire.WireScope, usage: dict) -> dict:
    return wire.attempt_end_event(
        scope,
        wire.new_call(),
        response=b'{"usage":{}}',
        latency_ms=1,
        http_status=200,
        usage=usage,
    )


def test_usage_mapping_keys_are_redacted_like_values(tmp_path, redactor):
    # AC-005 has no schema-label exemption for attacker-chosen keys: an endpoint
    # (or a compromised one) can put a credential in the usage key, which used to
    # bypass the value-level redaction and land verbatim in the ledger.
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    event = _usage_event(
        scope, {f"key-{SECRET}": 5, "input_tokens": 7, "output_tokens": 3}
    )
    assert SECRET not in json.dumps(event)
    assert sorted(event["usage"]) == ["input_tokens", "key-<redacted>", "output_tokens"]
    assert event["usage"]["input_tokens"] == 7
    assert event["usage"]["output_tokens"] == 3
    assert event["usage"]["key-<redacted>"] == 5


def test_policy_nested_mapping_keys_are_redacted(tmp_path, redactor):
    # Nested dictionaries *and* dictionaries inside lists are the same class of
    # caller text; the redaction must not stop at the first container level.
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    policy = {
        f"outer-{SECRET}": [{"inner-" + SECRET: [f"value {SECRET}"]}],
        "budget": 3,
    }
    event = wire.call_end_event(
        scope, wire.new_call(), attempts=1, latency_ms=1, policy=policy
    )
    assert SECRET not in json.dumps(event)
    assert event["policy"]["budget"] == 3
    assert event["policy"]["outer-<redacted>"][0]["inner-<redacted>"] == [
        "value <redacted>"
    ]


def test_metadata_mapping_keys_without_a_redactor_are_withheld(tmp_path):
    # No redactor = nothing about caller text is provable. The closed-set token
    # counters stay usable (numbers only), everything else is dropped instead of
    # being passed through as if the store knew the key.
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=None)
    event = _usage_event(scope, {SECRET: 5, "input_tokens": 3, "model": "m-1"})
    assert SECRET not in json.dumps(event)
    assert event["usage"] == {"input_tokens": 3}

    policy_event = wire.call_end_event(
        scope,
        wire.new_call(),
        attempts=1,
        latency_ms=1,
        policy={SECRET: 1, "budget": 3, "enabled": True},
    )
    assert SECRET not in json.dumps(policy_event)
    assert policy_event["policy"] == {}


def test_colliding_redacted_usage_keys_are_dropped_not_overwritten(tmp_path):
    # Two attacker keys that redact to the same placeholder must not collapse
    # into one entry: a silent dict overwrite would attribute one number to the
    # other and fake a usage fact nobody sent (VC-016 fabricated_usage=0).
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([SECRET, SECRET_ALT]),
    )
    event = _usage_event(scope, {SECRET: 111, SECRET_ALT: 222, "input_tokens": 7})
    assert SECRET not in json.dumps(event)
    assert SECRET_ALT not in json.dumps(event)
    assert event["usage"] == {"input_tokens": 7}


def test_redacted_key_colliding_with_a_token_counter_keeps_the_real_count(tmp_path):
    # A sanitized key that lands on a closed-set label must lose, never overwrite
    # the genuine token count (the fake 999 must not become input_tokens).
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor([SECRET], placeholder="input_tokens"),
    )
    event = _usage_event(scope, {"input_tokens": 7, SECRET: 999})
    assert SECRET not in json.dumps(event)
    assert event["usage"] == {"input_tokens": 7}


def test_a_counter_label_that_is_itself_a_known_secret_is_dropped(tmp_path):
    # The closed set is a label allowlist, not an AC-005 exemption: if the label
    # itself is a known credential, zero-original-occurrence wins over counting.
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=wire.SubstringRedactor(["input_tokens"]),
    )
    event = _usage_event(scope, {"input_tokens": 7, "output_tokens": 3})
    assert "input_tokens" not in json.dumps(event)
    assert event["usage"] == {"output_tokens": 3}


def test_metadata_key_sanitizing_never_rewrites_the_row_join_ids(tmp_path):
    # The join floor (row identity) is not metadata: redacting a usage key must
    # not change call/decision/submission identities or the DP key.
    call = wire.new_call()
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        decision_id="dec-1",
        key="dp4-failure-handling",
        task_key="T02c",
        submission_id="sub-1",
        redact=wire.SubstringRedactor([call.call_id, SECRET]),
    )
    event = wire.attempt_end_event(
        scope,
        call,
        response=b"{}",
        latency_ms=1,
        http_status=200,
        usage={SECRET: 5, "input_tokens": 1},
    )
    assert event["call_id"] == call.call_id
    assert event["decision_id"] == "dec-1"
    assert event["key"] == "dp4-failure-handling"
    assert event["task_key"] == "T02c"
    assert event["submission_id"] == "sub-1"
    assert SECRET not in json.dumps(event["usage"])
    assert event["usage"]["input_tokens"] == 1


def test_metadata_key_sanitizing_keeps_the_depth_limit(tmp_path, redactor):
    # The key pass must not become a new unbounded recursion: depth >= 8 is still
    # dropped, and every kept level has its key redacted.
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    node: object = f"leaf {SECRET}"
    for _ in range(10):
        node = {"k" + SECRET: node}
    event = wire.call_end_event(
        scope, wire.new_call(), attempts=1, latency_ms=1, policy=node
    )
    assert SECRET not in json.dumps(event)
    cursor: object = event["policy"]
    depth = 0
    while isinstance(cursor, dict):
        depth += 1
        assert list(cursor) == ["k<redacted>"], depth
        cursor = cursor["k<redacted>"]
    assert depth == 8
    assert cursor is None


def test_oversized_metadata_keys_are_clipped_so_the_line_budget_holds(tmp_path, redactor):
    # A key is attacker-controlled text, so it needs a bound: before the fix a
    # 20 KB key pushed the whole row into the minimal capture-failed fallback and
    # silently lost the genuine token counts.
    scope = wire.WireScope(
        sink=tmp_path / "wire.jsonl",
        project_id="p",
        redact=redactor,
        segment_cap=24576,
        line_cap=2048,
    )
    event = _usage_event(scope, {"k" * 20000: 5, "input_tokens": 7})
    line, fitted = wire.serialize_event(scope, event)
    assert len(line) <= 2048
    usage = fitted.get("usage")
    assert isinstance(usage, dict), fitted.get("line_error")
    assert usage["input_tokens"] == 7
    clipped = [key for key in usage if key != "input_tokens"]
    assert len(clipped) == 1
    assert len(clipped[0].encode("utf-8")) <= wire.METADATA_KEY_LIMIT
    assert usage[clipped[0]] == 5


def test_persisted_line_never_holds_a_usage_key_secret(tmp_path, redactor):
    # End to end at the store level: the written line (not only the row dict)
    # must be free of the credential, with the token count still readable.
    scope = wire.WireScope(sink=tmp_path / "wire.jsonl", project_id="p", redact=redactor)
    result = wire.record_attempt_end(
        scope,
        wire.new_call(),
        response=(
            '{"usage":{"' + SECRET + '":5,"input_tokens":9}}'
        ).encode(),
        latency_ms=2,
        http_status=200,
        usage={f"prefix-{SECRET}": 5, "input_tokens": 9},
    )
    assert result.status == "written"
    assert SECRET.encode() not in scope.sink.read_bytes()
    row = _rows(scope.sink)[0]
    assert row["usage"]["input_tokens"] == 9
    assert row["usage"]["prefix-<redacted>"] == 5

