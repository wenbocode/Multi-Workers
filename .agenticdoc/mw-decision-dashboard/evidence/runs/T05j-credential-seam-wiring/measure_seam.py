"""measure_seam.py - T05j before/after metrics for the credential seam.

Runs three production-shaped scenarios against the package directory given as
``argv[1]`` (a baseline copy or the working tree) and prints **booleans/counts
only**: no credential value, no path, no rendered message. The scenarios are

``cli_book``      - ``mw decide run --book`` against a real loopback server,
                    rotating ``auth.json`` right after the first discovery;
``points_prod``   - ``decision_points.decide_for`` without a caller client
                    (production scope + constructed client), same rotation;
``observation``   - ``decide_for`` with a caller-owned test scope whose redactor
                    was built while the credential was still the old value, then
                    rotated before the decision.

Usage: ``python measure_seam.py <package-dir>``
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import threading

PACKAGE = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(PACKAGE))

import argparse  # noqa: E402
import http.server  # noqa: E402

import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire as wire  # noqa: E402
import mw  # noqa: E402

DP3 = "dp3-worker-clarify"
OLD = "measure-seam-old-0123456789"
NEW = "measure-seam-new-0123456789"

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
    "TIMI_BASE_URL",
)

ANSWERS = {
    "answer_kind": {"type": "choice", "choice": "fact", "confidence": 0.9},
    "answerable": {"type": "noul", "noul": 0.9},
    "candidate": {"type": "choice", "choice": "c1", "confidence": 0.9},
}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        self.rfile.read(length)
        authorization = self.headers.get("Authorization") or ""
        self.server.authorizations.append(authorization)
        payload = json.dumps(
            {
                "model": "jev-latest",
                "answers": ANSWERS,
                "note": f"used {authorization}",
            }
        ).encode("utf-8")
        step = self.server.steps.pop(0) if len(self.server.steps) > 1 else 200
        self.send_response(int(step))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def log_message(self, fmt, *args):  # noqa: A003
        return


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.authorizations: list[str] = []
        self.steps: list[int] = []

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_auth(path: pathlib.Path, key: str) -> None:
    _write(path, json.dumps({"timi": {"key": key}}))


def _project(root: pathlib.Path, base_url: str) -> pathlib.Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "notes.txt").write_text("line1\n", encoding="utf-8", newline="\n")
    _write(
        root / ".mw" / "decide.json",
        json.dumps(
            {
                "enabled": True,
                "base_url": base_url,
                "model": "jev-latest",
                "timeout_s": 5.0,
                "max_retries": 2,
                "backoff_base_s": 0,
            }
        ),
    )
    _write(
        root / ".mw" / "decide-points.json",
        json.dumps(
            {
                "version": 1,
                "points": {
                    point.id: {"tier": point.tier, "enabled": True, "mode": "auto"}
                    for point in dpts.DP_REGISTRY
                },
            }
        ),
    )
    dpts.clear_points_config_cache()
    return root


def _state() -> dict:
    return {
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
        "key": "k-measure",
        "phase": "EXECUTE",
        "task_type": "coding",
        "risk": "low",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "measure the seam",
        "ambiguity": {"kind": "fact", "question": "which file?"},
        "local_candidates": [{"id": "c1", "label": "candidate"}],
    }


def _book() -> dict:
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": DP3,
        "state": _state(),
        "notes": {"evidence": {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[DP3]}},
    }


def _args(root: pathlib.Path, book_path: pathlib.Path) -> argparse.Namespace:
    return argparse.Namespace(
        subcommand="decide",
        decide_action="run",
        project=str(root),
        json=True,
        request_file=None,
        dp=None,
        book=str(book_path),
    )


def _rotate_after_first(auth: pathlib.Path):
    """Rotate the auth.json right after the *first* real discovery.

    Returns ``(calls, restore)``: the resolved values (never printed) and the
    undo for the module attribute this scenario patched.
    """
    original = db.resolve_timi_api_key
    calls: list[str | None] = []

    def spy(env=None, auth_path=None):
        value = original(env, auth_path)
        if env is None and auth_path is None:
            calls.append(value)
            if len(calls) == 1:
                _write_auth(auth, NEW)
        return value

    db.resolve_timi_api_key = spy

    def restore() -> None:
        db.resolve_timi_api_key = original

    return calls, restore


def _sink_metrics(sink: pathlib.Path, sent: str | None) -> dict:
    raw = sink.read_bytes() if sink.exists() else b""
    return {
        "sink_exists": bool(raw),
        "sink_contains_sent_value": bool(sent) and sent.encode() in raw,
        "sink_contains_rotated_value": NEW.encode() in raw,
        "sink_has_redaction": b"<redacted>" in raw,
    }


def _report(name: str, **fields) -> dict:
    return {"scenario": name, **fields}


def scenario_cli_book(tmp: pathlib.Path, server: Server) -> dict:
    auth = tmp / "home" / ".pi" / "agent" / "auth.json"
    _write_auth(auth, OLD)
    db._auth_json_path = lambda: auth
    project = _project(tmp / "cli", server.base_url)
    book_path = project / "book.json"
    _write(book_path, json.dumps(_book()))
    calls, restore = _rotate_after_first(auth)
    server.steps = [500, 200]
    server.authorizations = []
    try:
        rc = mw.cmd_decide(_args(project, book_path))
    finally:
        restore()
    first = calls[0] if calls else None
    sent = server.authorizations
    metrics = {
        "rc": rc,
        "resolutions": len(calls),
        "posts": len(sent),
        "distinct_authorizations": len(set(sent)),
        "every_attempt_sent_first_value": bool(sent) and all(v == first for v in sent),
    }
    metrics.update(_sink_metrics(wire.production_wire_sink(project), first))
    return _report("cli_book", **metrics)


def scenario_points_prod(tmp: pathlib.Path, server: Server) -> dict:
    auth = tmp / "home2" / ".pi" / "agent" / "auth.json"
    _write_auth(auth, OLD)
    db._auth_json_path = lambda: auth
    project = _project(tmp / "points", server.base_url)
    calls, restore = _rotate_after_first(auth)
    server.steps = [500, 200]
    server.authorizations = []
    try:
        dpts.decide_for(DP3, _state(), project, intent="answer")
    finally:
        restore()
    first = calls[0] if calls else None
    sent = server.authorizations
    metrics = {
        "resolutions": len(calls),
        "posts": len(sent),
        "distinct_authorizations": len(set(sent)),
        "every_attempt_sent_first_value": bool(sent) and all(v == first for v in sent),
    }
    metrics.update(_sink_metrics(wire.production_wire_sink(project), first))
    return _report("points_prod", **metrics)


def scenario_observation(tmp: pathlib.Path, server: Server) -> dict:
    auth = tmp / "home3" / ".pi" / "agent" / "auth.json"
    _write_auth(auth, OLD)
    db._auth_json_path = lambda: auth
    project = _project(tmp / "obs", server.base_url)
    cfg = decision.DecisionConfig(
        enabled=True,
        extras={"base_url": server.base_url},
        timeout_s=5.0,
        max_retries=2,
        backoff_base_s=0.0,
    )
    root = tmp / "obs-run"
    root.mkdir(parents=True, exist_ok=True)
    # The caller's own filter knows the *old* value only.
    caller = decision.credential_redactor(
        cfg, extra_secrets=(OLD,), env={}, auth_path=tmp / "no-auth.json"
    )
    scope = wire.test_scope(
        root,
        project_id=wire.project_id_for(root),
        submission_id="sub-measure",
        redact=caller,
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )
    client = decision.DecisionClient(
        cfg=cfg, backend=db.TimiDecisionsBackend(), wire_scope=scope
    )
    _write_auth(auth, NEW)  # rotation between the caller's set and the decision
    server.steps = [200]
    server.authorizations = []
    observation = dpts.Observation(scope=scope, submission_id="sub-measure")
    refused = False
    outcome_status = None
    try:
        outcome = dpts.decide_for(
            DP3,
            _state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=observation,
        )
        outcome_status = outcome.status
    except decision.DecisionInputError:
        refused = True
    text = ""
    for item in sorted(root.rglob("*")):
        if item.is_file():
            text += item.read_text(encoding="utf-8", errors="replace")
    return _report(
        "observation",
        refused_incomplete_capture=refused,
        decision_status=outcome_status,
        posts=len(server.authorizations),
        rotated_value_stored_in_ledger=NEW in text,
        old_value_stored_in_ledger=OLD in text,
    )


def main() -> int:
    for name in CRED_ENV_VARS:
        os.environ.pop(name, None)
    os.environ["HOME"] = str(pathlib.Path(tempfile.mkdtemp()))
    os.environ["USERPROFILE"] = os.environ["HOME"]
    server = Server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    tmp = pathlib.Path(tempfile.mkdtemp())
    out = []
    try:
        for scenario in (scenario_cli_book, scenario_points_prod, scenario_observation):
            try:
                out.append(scenario(tmp, server))
            except Exception as exc:  # noqa: BLE001 - report the class, never the value
                out.append({"scenario": scenario.__name__, "error": type(exc).__name__})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
