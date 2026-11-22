"""T15-M3G: native review terminal observation -- real-process positives/negatives.

FIXTURE BOUNDARY (read before interpreting any result):

* The CHANNEL is the real production implementation in
  :mod:`review_observation`: a Windows named-pipe server instance with
  ``GetNamedPipeClientProcessId`` peer identity (or a POSIX ``socketpair`` with
  ``SO_PEERCRED``), a real framed protocol and the real current-lifetime
  registry/consumption checks.
* The children are REAL separate OS processes that connect over that channel;
  the payload *content* they deliver is authored by this test. That is a
  channel/identity fixture: it is NOT a business review, NOT a native reviewer
  model run, NOT a QG PASS, NOT a sign and NOT a Done result. Every accepted
  observation here is refused by the product unless the caller supplies its own
  current facts.
* The file-only / pre-read / post-read / grandchild / duplicate / conflict /
  abnormal-exit / oversized / disconnected / restart cases are the negatives
  that a hash, a path, a PID field or a typed JSON verdict must not survive.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest

import review_observation as ro

REVIEW_TASK = "T15-M3G-review-fixture"
OWNER_KEY = "mw-pm-dp-continuity-fixture"
REVIEW_RUN = f"{REVIEW_TASK}@2026-11-20T06:30:00.000Z"
IMPLEMENTER_TASK = "T15-M3G-impl-fixture"
IMPLEMENTER_RUN = f"{IMPLEMENTER_TASK}@2026-11-20T06:00:00.000Z"
NOW_MS = int(time.time() * 1000)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iso(ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


REPORT = b"# review report\n\nverdict: pass\n"


def payload(
    *,
    report: bytes = REPORT,
    verdict: str = "pass",
    owner_key: str = OWNER_KEY,
    task_key: str = REVIEW_TASK,
    run_id: str = REVIEW_RUN,
    implementer_task_key: str = IMPLEMENTER_TASK,
    implementer_run_id: str = IMPLEMENTER_RUN,
    started_ms: int | None = None,
    delivered_ms: int | None = None,
    reviewed_ms: int | None = None,
    status: str = "done",
    claim_id: str = "WENBOZHOU-PC5:63456",
    parent_run_id: str = "parent-run-fixture-1",
    local_ref: str = "local:T15-M3G:fixture",
    **overrides: Any,
) -> bytes:
    started_ms = started_ms if started_ms is not None else NOW_MS - 300_000
    delivered_ms = delivered_ms if delivered_ms is not None else NOW_MS - 60_000
    reviewed_ms = reviewed_ms if reviewed_ms is not None else NOW_MS - 120_000
    body: dict[str, Any] = {
        "schema_version": ro.SCHEMA_VERSION,
        "kind": ro.KIND,
        "protocol": ro.PROTOCOL,
        "delivered_at": _iso(delivered_ms),
        "run": {
            "owner_key": owner_key,
            "task_key": task_key,
            "run_id": run_id,
            "kind": "review",
            "status": status,
            "started_at": _iso(started_ms),
            "ended_at": _iso(delivered_ms),
            "pid": os.getpid(),
        },
        "dispatch": {
            "claim_id": claim_id,
            "parent_run_id": parent_run_id,
            "card_path": f"tasks/{OWNER_KEY}-review-card.md",
            "card_sha256": _sha(b"card-bytes"),
            "envelope_sha256": _sha(b"envelope-bytes"),
            "implementer_task_key": implementer_task_key,
            "implementer_run_id": implementer_run_id,
            "local_ref": local_ref,
            "execution_ref": "tool_result:tc-1",
            "tool_call_ref": "tool_call:tc-1",
            "material_digest": _sha(b"material"),
            "basis_digest": _sha(b"basis"),
            "goal_digest": _sha(b"goal"),
        },
        "review": {
            "role": "review",
            "verifier_ref": "independent-review:current-refs@local-qg-consumer-v1",
            "verdict": verdict,
            "reviewed_at": _iso(reviewed_ms),
            "findings": ["reviewed AC-004/AC-006 against the current action"],
            "unresolved_findings": [],
            "refs": ["local:T15-M3G:fixture#review"],
        },
        "report": {"path": "report.md", "sha256": _sha(report), "b64": base64.b64encode(report).decode("ascii")},
    }
    body.update(overrides)
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def expectations(**overrides: Any) -> ro.CurrentExpectations:
    values: dict[str, Any] = dict(
        owner_key=OWNER_KEY,
        task_key=REVIEW_TASK,
        run_id=REVIEW_RUN,
        claim_id="WENBOZHOU-PC5:63456",
        parent_run_id="parent-run-fixture-1",
        card_sha256=_sha(b"card-bytes"),
        material_digest=_sha(b"material"),
        basis_digest=_sha(b"basis"),
        goal_digest=_sha(b"goal"),
        local_ref="local:T15-M3G:fixture",
        execution_ref="tool_result:tc-1",
        tool_call_ref="tool_call:tc-1",
        implementer_task_key=IMPLEMENTER_TASK,
        implementer_run_id=IMPLEMENTER_RUN,
        execution_created_at=_iso(NOW_MS - 240_000),
        budget_deadline=_iso(NOW_MS + 3_600_000),
        stopped=False,
    )
    values.update(overrides)
    return ro.CurrentExpectations(**values)


# ── real child processes ───────────────────────────────────────────────────

_CHILD_SCRIPT = textwrap.dedent(
    """
    import json, os, subprocess, sys, time

    spec, payload_path, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    kind, _, value = spec.partition(":")
    body = open(payload_path, "rb").read()

    def frame(data):
        return len(data).to_bytes(4, "big") + data

    def open_pipe():
        # Connect to the server instance with a BOUNDED busy retry.
        # A one-instance server is listening again only after it has read the
        # previous frame and disconnected; a client that connects in that window
        # gets ERROR_PIPE_BUSY. WaitNamedPipe semantics, bounded in wall clock:
        # the retry is finite so a broken server cannot hang the child.
        deadline = time.time() + 10.0
        while True:
            try:
                if kind == "windows-named-pipe":
                    return open(value, "wb", buffering=0)
                return os.fdopen(int(value), "wb", buffering=0)
            except OSError as exc:
                busy = getattr(exc, "winerror", None) in (231, 2, 3) or exc.errno == 22
                if time.time() >= deadline or not busy:
                    raise
                time.sleep(0.02)

    def send(data):
        handle = open_pipe()
        handle.write(frame(data))
        handle.flush()
        handle.close()

    if mode == "forged_grandchild_then_real":
        # A model-capable shell would be this grandchild: a real process, a real
        # connection, a valid payload -- and the wrong PID.
        subprocess.run([sys.executable, "-c", CHILD_INLINE, spec, payload_path, "real"], check=True)
        send(body)
        sys.exit(0)
    if mode == "grandchild_only":
        subprocess.run([sys.executable, "-c", CHILD_INLINE, spec, payload_path, "real"], check=True)
        sys.exit(0)
    if mode == "duplicate":
        send(body)
        send(body)
        sys.exit(0)
    if mode == "conflict":
        # A DISTINCT second terminal delivery: the report bytes really differ and
        # the payload is internally consistent (its own b64 + sha256), so the
        # refusal must be a conflict, not a duplicate.
        send(body)
        send(open(sys.argv[4], "rb").read())
        sys.exit(0)
    if mode == "exit3":
        send(body)
        sys.exit(3)
    if mode == "disconnect":
        open_pipe().close()
        sys.exit(0)
    if mode == "oversize":
        handle = open_pipe()
        handle.write((ro_limit := int(sys.argv[4])).to_bytes(4, "big"))
        handle.flush()
        time.sleep(0.2)
        handle.close()
        sys.exit(0)
    if mode == "none":
        sys.exit(0)
    if mode == "real_then_wait":
        send(body)
        time.sleep(float(sys.argv[4]) if len(sys.argv) > 4 else 20.0)
        sys.exit(0)
    send(body)
    sys.exit(0)
    """
)

_INLINE = textwrap.dedent(
    """
    import os, sys
    spec, payload_path, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    kind, _, value = spec.partition(":")
    body = open(payload_path, "rb").read()
    frame = len(body).to_bytes(4, "big") + body
    if kind == "windows-named-pipe":
        handle = open(value, "wb", buffering=0)
    else:
        handle = os.fdopen(int(value), "wb", buffering=0)
    handle.write(frame)
    handle.flush()
    handle.close()
    """
).replace("CHILD_INLINE", "x")

_CHILD_SOURCE = _CHILD_SCRIPT.replace("CHILD_INLINE", json.dumps(_INLINE))


def spawn_child(tmp_path: Path, spec: ro.EndpointSpec, body: bytes, mode: str, *extra: str) -> subprocess.Popen:
    payload_path = tmp_path / f"payload-{os.urandom(4).hex()}.json"
    payload_path.write_bytes(body)
    script = tmp_path / "native-child.py"
    if not script.exists():
        script.write_text(_CHILD_SOURCE, encoding="utf-8")
    spec_text = f"{spec.kind}:{spec.value}"
    return subprocess.Popen([sys.executable, "-B", str(script), spec_text, str(payload_path), mode, *extra])


def run_delivery(
    tmp_path: Path,
    body: bytes,
    *,
    mode: str = "real",
    exit_wait_s: float = 30.0,
    spec_override: ro.EndpointSpec | None = None,
    extra: tuple[str, ...] = (),
    second_body: bytes | None = None,
) -> tuple[ro.HostObservationChannel, ro.EndpointSpec, list[bytes]]:
    """Create the endpoint, spawn the real child, wait for exit + payloads."""
    if spec_override is None:
        channel = ro.HostObservationChannel.create()
        spec = channel.spec
    else:
        channel = ro.HostObservationChannel(ro.EndpointSpec("posix-socketpair", spec_override.value), "posix")
        spec = spec_override
    extra = tuple(extra)
    if second_body is not None:
        second_path = tmp_path / f"payload-second-{os.urandom(4).hex()}.json"
        second_path.write_bytes(second_body)
        extra = extra + (str(second_path),)
    proc = spawn_child(tmp_path, spec, body, mode, *extra)
    channel.start(proc.pid)
    deadline = time.time() + exit_wait_s
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.02)
    # Give the reader a final chance to drain before the exit is published.
    time.sleep(0.15)
    code = proc.poll()
    if code is None:
        proc.kill()
        code = proc.wait(timeout=10)
    if channel._sock is not None:  # posix: reader is blocked in recv until close
        frames = channel.frames
        channel.close()
    else:
        frames = channel.frames
        channel.close()
    # Cleanup control for every delivery case: the host must be able to prove the
    # reader left its I/O loop and that no child is left behind.
    assert channel.reader_terminated
    assert channel._thread is not None and not channel._thread.is_alive()
    assert proc.poll() is not None
    return channel, spec, [f for f in frames]


# ── positive: a real child terminal delivery ───────────────────────────────


@pytest.mark.skipif(sys.platform != "win32", reason="the native positive runs on the Windows named-pipe path")
def test_real_child_terminal_delivery_is_accepted_and_consumed(tmp_path: Path) -> None:
    channel, _spec, frames = run_delivery(tmp_path, payload())
    assert channel.refusals == []
    assert len(frames) == 1
    assert channel.sender_pid is not None
    report_dir = tmp_path / "report.md"
    report_dir.write_bytes(REPORT)
    registry = ro.NativeObservationRegistry()
    observation = registry.apply(
        frames[0],
        child_pid=channel.sender_pid,
        sender_pid=channel.sender_pid,
        exit_code=0,
        started_at=_iso(NOW_MS - 300_000),
        ended_at=_iso(NOW_MS),
    )
    assert observation.verdict == "pass"
    assert observation.report_bytes == REPORT
    consumed = ro.consume_current_native_review(
        registry,
        observation.observation_id,
        expectations(),
        now_ms=NOW_MS,
        disk_report_bytes=report_dir.read_bytes(),
    )
    assert consumed.observation_id == observation.observation_id


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for the cross-language producer")
@pytest.mark.skipif(sys.platform != "win32", reason="the cross-language producer runs on the Windows named-pipe path")
def test_real_node_producer_over_the_real_channel(tmp_path: Path) -> None:
    """The production writer is TypeScript (worker-mode.ts). Its client primitive
    (`net.connect` to the pipe + framed write) is exercised by a REAL node
    child here, so the cross-language contract is not a Python-only fiction."""
    body = payload()
    payload_path = tmp_path / "payload-node.json"
    payload_path.write_bytes(body)
    script = tmp_path / "native-child.mjs"
    script.write_text(
        textwrap.dedent(
            """
            import fs from "node:fs";
            import net from "node:net";
            const [spec, payloadPath] = process.argv.slice(2);
            const value = spec.slice("windows-named-pipe:".length);
            const body = fs.readFileSync(payloadPath);
            const header = Buffer.alloc(4);
            header.writeUInt32BE(body.length, 0);
            const socket = net.connect(value);
            socket.on("connect", () => socket.end(Buffer.concat([header, body])));
            socket.on("error", (err) => {
              process.stderr.write(String(err));
              process.exit(70);
            });
            socket.on("close", () => process.exit(0));
            """
        ),
        encoding="utf-8",
    )
    channel = ro.HostObservationChannel.create()
    proc = subprocess.Popen(["node", str(script), f"{channel.spec.kind}:{channel.spec.value}", str(payload_path)])
    channel.start(proc.pid)
    deadline = time.time() + 60
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.02)
    time.sleep(0.2)
    frames = channel.frames
    sender = channel.sender_pid
    refusals = list(channel.refusals)
    channel.close()
    proc.wait(timeout=20)
    assert refusals == []
    assert sender == proc.pid
    assert len(frames) == 1
    observation = ro.NativeObservationRegistry().apply(
        frames[0],
        child_pid=proc.pid,
        sender_pid=proc.pid,
        exit_code=0,
        started_at=_iso(NOW_MS - 300_000),
        ended_at=_iso(NOW_MS),
    )
    assert observation.report_bytes == REPORT


# ── negatives: substitution / forgery ─────────────────────────────────────


@pytest.mark.skipif(sys.platform != "win32", reason="the forged grandchild runs on the Windows named-pipe path")
def test_forged_delivery_from_a_grandchild_is_refused_and_the_real_one_still_accepted(tmp_path: Path) -> None:
    channel, _spec, frames = run_delivery(tmp_path, payload(), mode="forged_grandchild_then_real")
    assert any(refusal.gaps == ("channel-foreign-sender",) for refusal in channel.refusals)
    foreign = [r.sender_pid for r in channel.refusals if r.gaps == ("channel-foreign-sender",)]
    assert foreign and foreign[0] not in (None, channel.sender_pid)
    assert len(frames) == 1
    registry = ro.NativeObservationRegistry()
    observation = registry.apply(
        frames[0],
        child_pid=channel.sender_pid,
        sender_pid=channel.sender_pid,
        exit_code=0,
        started_at=_iso(NOW_MS - 300_000),
        ended_at=_iso(NOW_MS),
    )
    assert observation.sender_pid == channel.sender_pid


def test_a_file_only_substitution_is_not_a_delivery(tmp_path: Path) -> None:
    """A pre-written review-verdict.json/report.md and a zero-exit child mint nothing."""
    task_dir = tmp_path / "workers" / REVIEW_TASK
    task_dir.mkdir(parents=True)
    (task_dir / "report.md").write_bytes(REPORT)
    (task_dir / "review-verdict.json").write_text(
        json.dumps({"kind": "independent-review-verdict", "verdict": "pass"}), encoding="utf-8"
    )
    registry = ro.NativeObservationRegistry()
    assert len(registry) == 0
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.consume_current_native_review(
            registry,
            _sha(b"any"),
            expectations(),
            now_ms=NOW_MS,
            disk_report_bytes=REPORT,
        )
    assert excinfo.value.gaps == ("observation-not-current",)
    assert (task_dir / "review-verdict.json").exists()


def test_apply_refuses_a_sender_that_is_not_the_child(tmp_path: Path) -> None:
    registry = ro.NativeObservationRegistry()
    with pytest.raises(ro.ObservationRefused) as excinfo:
        registry.apply(
            payload(),
            child_pid=4242,
            sender_pid=4243,
            exit_code=0,
            started_at=_iso(NOW_MS - 300_000),
            ended_at=_iso(NOW_MS),
        )
    assert excinfo.value.gaps == ("channel-foreign-sender",)


def test_a_self_review_payload_is_refused() -> None:
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.parse_native_review_payload(payload(implementer_task_key=REVIEW_TASK, implementer_run_id=REVIEW_RUN))
    assert excinfo.value.gaps == ("payload-self-review",)


def test_a_non_review_run_payload_is_refused() -> None:
    body = json.loads(payload())
    body["run"]["kind"] = "coding"
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.parse_native_review_payload(json.dumps(body).encode())
    assert excinfo.value.gaps == ("payload-role",)


def test_a_payload_that_recomputes_its_own_report_digest_is_still_not_a_delivery(tmp_path: Path) -> None:
    """The strongest forged-shape case: a complete, self-consistent payload with a
    recomputed report digest, delivered by a process that is not the child."""
    forged_report = b"# forged\n\nverdict: pass\n"
    channel = ro.HostObservationChannel.create()
    proc = subprocess.Popen(
        [sys.executable, "-B", "-c", "import time; time.sleep(30)"] if sys.platform == "win32" else [sys.executable, "-c", "import time; time.sleep(30)"]
    )
    channel.start(proc.pid)
    # The test process itself (a different PID) writes a valid payload.
    time.sleep(0.2)
    if sys.platform == "win32":
        with open(channel.spec.value, "wb", buffering=0) as handle:
            handle.write(ro.frame_payload(payload(report=forged_report)))
    time.sleep(0.5)
    assert channel.frames == []
    assert channel.refusals and channel.refusals[0].gaps == ("channel-foreign-sender",)
    channel.close()
    proc.kill()
    proc.wait(timeout=10)


# ── negatives: lifecycle / duplicate / conflict / exit ────────────────────


@pytest.mark.skipif(sys.platform != "win32", reason="the duplicate delivery runs on the Windows named-pipe path")
def test_a_duplicate_delivery_poisons_the_run(tmp_path: Path) -> None:
    channel, _spec, frames = run_delivery(tmp_path, payload(), mode="duplicate")
    assert len(frames) == 2
    registry = ro.NativeObservationRegistry()
    first = registry.apply(
        frames[0],
        child_pid=channel.sender_pid,
        sender_pid=channel.sender_pid,
        exit_code=0,
        started_at=_iso(NOW_MS - 300_000),
        ended_at=_iso(NOW_MS),
    )
    assert registry.get(first.observation_id) is not None
    with pytest.raises(ro.ObservationRefused) as excinfo:
        registry.apply(
            frames[1],
            child_pid=channel.sender_pid,
            sender_pid=channel.sender_pid,
            exit_code=0,
            started_at=_iso(NOW_MS - 300_000),
            ended_at=_iso(NOW_MS),
        )
    assert excinfo.value.gaps == ("observation-duplicate",)
    # The poisoned run keeps nothing: a duplicate does not leave the first valid.
    assert len(registry) == 0
    with pytest.raises(ro.ObservationRefused):
        ro.consume_current_native_review(
            registry, first.observation_id, expectations(), now_ms=NOW_MS, disk_report_bytes=REPORT
        )


@pytest.mark.skipif(sys.platform != "win32", reason="the conflicting delivery runs on the Windows named-pipe path")
def test_a_conflicting_second_delivery_poisons_the_run(tmp_path: Path) -> None:
    """FIRST valid delivery succeeds; a DISTINCT second delivery poisons it.

    The first apply must succeed (it is the real terminal delivery), the second
    must be refused as a conflict, and the poisoning must remove the first so a
    later consumption cannot use it. No first-success is hidden inside a raises
    block.
    """
    conflict_report = b"# review report\n\nverdict: pass (second terminal delivery)\n"
    channel, _spec, frames = run_delivery(
        tmp_path, payload(), mode="conflict", second_body=payload(report=conflict_report)
    )
    assert len(frames) == 2
    assert frames[0] != frames[1]
    registry = ro.NativeObservationRegistry()
    first = registry.apply(
        frames[0],
        child_pid=channel.sender_pid,
        sender_pid=channel.sender_pid,
        exit_code=0,
        started_at=_iso(NOW_MS - 300_000),
        ended_at=_iso(NOW_MS),
    )
    assert registry.get(first.observation_id) is not None
    assert registry.for_run(OWNER_KEY, REVIEW_TASK, REVIEW_RUN) is not None
    with pytest.raises(ro.ObservationRefused) as excinfo:
        registry.apply(
            frames[1],
            child_pid=channel.sender_pid,
            sender_pid=channel.sender_pid,
            exit_code=0,
            started_at=_iso(NOW_MS - 300_000),
            ended_at=_iso(NOW_MS),
        )
    assert excinfo.value.gaps == ("observation-conflict",)
    # The first success is not silently kept after the conflict.
    assert len(registry) == 0
    with pytest.raises(ro.ObservationRefused) as consumed:
        ro.consume_current_native_review(
            registry, first.observation_id, expectations(), now_ms=NOW_MS, disk_report_bytes=REPORT
        )
    assert consumed.value.gaps == ("observation-not-current",)


@pytest.mark.skipif(sys.platform != "win32", reason="the abnormal-exit child runs on the Windows named-pipe path")
def test_a_non_zero_exit_mints_no_observation(tmp_path: Path) -> None:
    channel, _spec, frames = run_delivery(tmp_path, payload(), mode="exit3")
    assert len(frames) == 1
    registry = ro.NativeObservationRegistry()
    with pytest.raises(ro.ObservationRefused) as excinfo:
        registry.apply(
            frames[0],
            child_pid=channel.sender_pid,
            sender_pid=channel.sender_pid,
            exit_code=3,
            started_at=_iso(NOW_MS - 300_000),
            ended_at=_iso(NOW_MS),
        )
    assert excinfo.value.gaps == ("run-exit-nonzero",)


@pytest.mark.skipif(sys.platform != "win32", reason="the disconnecting child runs on the Windows named-pipe path")
def test_a_disconnect_before_the_frame_is_insufficient(tmp_path: Path) -> None:
    channel, _spec, frames = run_delivery(tmp_path, payload(), mode="disconnect")
    assert frames == []
    assert channel.frames == []
    # A disconnect is a refused delivery, never an empty-but-acceptable verdict.
    assert channel.refusals or channel.error is not None


@pytest.mark.skipif(sys.platform != "win32", reason="the oversized frame runs on the Windows named-pipe path")
def test_an_oversized_frame_is_refused(tmp_path: Path) -> None:
    channel, _spec, frames = run_delivery(
        tmp_path,
        payload(),
        mode="oversize",
        extra=(str(ro.MAX_PAYLOAD_BYTES + 1),),
    )
    assert frames == []
    assert any("payload-too-large" in refusal.gaps for refusal in channel.refusals) or (
        channel.error is not None and "payload-too-large" in channel.error.gaps
    )


def test_the_payload_encoder_enforces_the_bound() -> None:
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.frame_payload(b"x" * (ro.MAX_PAYLOAD_BYTES + 1))
    assert excinfo.value.gaps == ("payload-too-large",)


@pytest.mark.skipif(sys.platform != "win32", reason="the cleanup proofs run on the Windows named-pipe path")
def test_close_terminates_the_reader_and_leaves_no_reader_or_child(tmp_path: Path) -> None:
    """The lifecycle control for the original Windows hang.

    A real child delivers one valid frame and stays alive; the host then closes
    the channel while the reader is parked waiting for the next connection. The
    close must be FINITE (wall-bounded), the reader must prove termination, the
    pipe handle must be released only afterwards, and the child must be reaped.
    """
    channel = ro.HostObservationChannel.create()
    assert channel.spec.kind == "windows-named-pipe"
    # A real child delivers one frame and then STAYS ALIVE, so the reader is
    # parked in the accept wait when the host closes the channel.
    proc = spawn_child(tmp_path, channel.spec, payload(), "real_then_wait", "20")
    try:
        channel.start(proc.pid)
        deadline = time.time() + 20
        while time.time() < deadline and not channel.frames:
            time.sleep(0.02)
        assert len(channel.frames) == 1
        assert proc.poll() is None
        started = time.time()
        channel.close()
        close_s = time.time() - started
        # Bounded: the original defect hung here until the outer 25s timeout.
        assert close_s < 10.0, f"close() took {close_s:.3f}s"
        assert channel.reader_terminated
        assert channel._thread is not None and not channel._thread.is_alive()
        assert channel.error is None
        assert not channel._server._handle_open  # handle closed only after the witness
    finally:
        proc.kill()
        proc.wait(timeout=10)
    assert proc.poll() is not None


@pytest.mark.skipif(sys.platform != "win32", reason="the cleanup proofs run on the Windows named-pipe path")
def test_close_before_any_connection_is_finite(tmp_path: Path) -> None:
    """Closing a channel nobody ever connected to must not wait on I/O."""
    channel = ro.HostObservationChannel.create()
    channel.start(0)
    time.sleep(0.05)
    started = time.time()
    channel.close()
    assert time.time() - started < 10.0
    assert channel.reader_terminated
    assert channel._thread is not None and not channel._thread.is_alive()
    assert channel.frames == []
    assert channel.error is None


@pytest.mark.skipif(sys.platform != "win32", reason="the child-without-frame case runs on the Windows named-pipe path")
def test_a_child_that_never_writes_a_frame_is_not_a_delivery(tmp_path: Path) -> None:
    channel, _spec, frames = run_delivery(tmp_path, payload(), mode="none", exit_wait_s=10)
    assert frames == []
    assert channel.sender_pid is None
    registry = ro.NativeObservationRegistry()
    assert len(registry) == 0
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.consume_current_native_review(
            registry, _sha(b"nothing"), expectations(), now_ms=NOW_MS, disk_report_bytes=REPORT
        )
    assert excinfo.value.gaps == ("observation-not-current",)


@pytest.mark.skipif(sys.platform != "win32", reason="the duplicate-frame control runs on the Windows named-pipe path")
def test_one_valid_frame_is_accepted_once_and_a_second_is_visible(tmp_path: Path) -> None:
    """One frame is one delivery; a resent frame is a second delivery, not a no-op."""
    channel, _spec, frames = run_delivery(tmp_path, payload(), mode="duplicate")
    assert len(frames) == 2
    assert frames[0] == frames[1]
    registry = ro.NativeObservationRegistry()
    observation = registry.apply(
        frames[0],
        child_pid=channel.sender_pid,
        sender_pid=channel.sender_pid,
        exit_code=0,
        started_at=_iso(NOW_MS - 300_000),
        ended_at=_iso(NOW_MS),
    )
    assert observation.report_bytes == REPORT
    with pytest.raises(ro.ObservationRefused) as excinfo:
        registry.apply(
            frames[1],
            child_pid=channel.sender_pid,
            sender_pid=channel.sender_pid,
            exit_code=0,
            started_at=_iso(NOW_MS - 300_000),
            ended_at=_iso(NOW_MS),
        )
    assert excinfo.value.gaps == ("observation-duplicate",)


def test_an_unsupported_peer_identity_primitive_fails_closed() -> None:
    """No peer-credential primitive => no authenticated delivery (safe insufficient).

    A plain AF_INET socket exposes no peer PID on either platform, so the real
    function must refuse instead of inventing an identity from an address or a
    PID field.
    """
    import socket as _socket

    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        with pytest.raises(ro.ObservationRefused) as excinfo:
            ro._posix_peer_pid(sock)
        assert excinfo.value.gaps == ("peer-identity-unavailable",)
    finally:
        sock.close()


# ── negatives: currentness of a later consumption ────────────────────────


def _accepted(tmp_path: Path) -> tuple[ro.NativeObservationRegistry, str]:
    channel, _spec, frames = run_delivery(tmp_path, payload())
    assert len(frames) == 1
    registry = ro.NativeObservationRegistry()
    observation = registry.apply(
        frames[0],
        child_pid=channel.sender_pid,
        sender_pid=channel.sender_pid,
        exit_code=0,
        started_at=_iso(NOW_MS - 300_000),
        ended_at=_iso(NOW_MS),
    )
    return registry, observation.observation_id


@pytest.mark.skipif(sys.platform != "win32", reason="the accepted observation uses the Windows channel")
@pytest.mark.parametrize(
    "override, gap",
    [
        ({"claim_id": "WENBOZHOU-PC5:99999"}, "currentness-claim-id"),
        ({"parent_run_id": "other-parent"}, "currentness-parent-run-id"),
        ({"run_id": "other-run"}, "currentness-run-id"),
        ({"local_ref": "local:other"}, "currentness-local-ref"),
        ({"material_digest": "f" * 64}, "currentness-material-digest"),
        ({"basis_digest": "e" * 64}, "currentness-basis-digest"),
        ({"goal_digest": "d" * 64}, "currentness-goal-digest"),
        ({"implementer_run_id": "other-impl"}, "currentness-implementer-run-id"),
        ({"stopped": True}, "stopped"),
        ({"execution_created_at": "not-a-time"}, "execution-created-at-invalid"),
        ({"budget_deadline": _iso(NOW_MS - 1000)}, "budget-expired"),
    ],
)
def test_a_later_consumption_rechecks_the_current_facts(
    tmp_path: Path, override: dict[str, Any], gap: str
) -> None:
    registry, observation_id = _accepted(tmp_path)
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.consume_current_native_review(
            registry,
            observation_id,
            expectations(**override),
            now_ms=NOW_MS,
            disk_report_bytes=REPORT,
        )
    assert excinfo.value.gaps == (gap,)


@pytest.mark.skipif(sys.platform != "win32", reason="the accepted observation uses the Windows channel")
def test_a_report_edited_after_delivery_is_refused(tmp_path: Path) -> None:
    registry, observation_id = _accepted(tmp_path)
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.consume_current_native_review(
            registry,
            observation_id,
            expectations(),
            now_ms=NOW_MS,
            disk_report_bytes=b"# review report\n\nverdict: pass (edited)\n",
        )
    assert excinfo.value.gaps == ("report-changed-after-delivery",)


@pytest.mark.skipif(sys.platform != "win32", reason="the accepted observation uses the Windows channel")
def test_a_restarted_host_restores_no_authority(tmp_path: Path) -> None:
    _registry, observation_id = _accepted(tmp_path)
    fresh = ro.NativeObservationRegistry()
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.consume_current_native_review(
            fresh, observation_id, expectations(), now_ms=NOW_MS, disk_report_bytes=REPORT
        )
    assert excinfo.value.gaps == ("observation-not-current",)


@pytest.mark.skipif(sys.platform != "win32", reason="the accepted observation uses the Windows channel")
def test_invalidate_drops_an_observation_when_its_scope_changes(tmp_path: Path) -> None:
    registry, observation_id = _accepted(tmp_path)
    # The predicate is the CURRENT-fact test, not a row field comparison: this
    # record's claim is no longer the live claim, so it must be dropped.
    assert registry.invalidate(lambda record: record.claim_id == "WENBOZHOU-PC5:63456") == 1
    assert len(registry) == 0
    with pytest.raises(ro.ObservationRefused):
        ro.consume_current_native_review(
            registry, observation_id, expectations(), now_ms=NOW_MS, disk_report_bytes=REPORT
        )


@pytest.mark.skipif(sys.platform != "win32", reason="the accepted observation uses the Windows channel")
def test_a_review_into_the_future_or_before_the_execution_is_refused(tmp_path: Path) -> None:
    channel, _spec, frames = run_delivery(
        tmp_path, payload(reviewed_ms=NOW_MS + 600_000, delivered_ms=NOW_MS - 60_000)
    )
    registry = ro.NativeObservationRegistry()
    observation = registry.apply(
        frames[0],
        child_pid=channel.sender_pid,
        sender_pid=channel.sender_pid,
        exit_code=0,
        started_at=_iso(NOW_MS - 300_000),
        ended_at=_iso(NOW_MS),
    )
    with pytest.raises(ro.ObservationRefused) as excinfo:
        ro.consume_current_native_review(
            registry, observation.observation_id, expectations(), now_ms=NOW_MS, disk_report_bytes=REPORT
        )
    assert excinfo.value.gaps == ("review-future",)
