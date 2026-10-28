"""measure_refresh.py - T05i credential-refresh granularity measurement.

Runs the same synthetic rotation scenario against either the baseline copies
(``baseline/decision.py`` + ``baseline/decision_backends.py``) or the current
``packages/multi-workers`` modules and prints one JSON object of *metrics only*:
counts and same/different booleans. No credential value is printed or written.

Scenarios (real stdlib HTTP on 127.0.0.1:0, synthetic tmp auth.json):

* one logical call, 500 -> 500 -> 200, auth.json rotated to B when the first
  POST arrives: how often is the credential resolved, how many distinct
  Authorization values does the server see, and is the echoed value redacted?
* two logical calls, A then (rotated) B: is the second call refreshed, and is
  B redacted by the second call's capture?

Usage (from packages/multi-workers):
    python <evidence>/measure_refresh.py --variant baseline
    python <evidence>/measure_refresh.py --variant final
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import pathlib
import sys
import tempfile
import threading

PACKAGES = pathlib.Path(__file__).resolve().parents[5] / "packages" / "multi-workers"
BASELINE = pathlib.Path(__file__).resolve().parent / "baseline"

SECRET_A = "timi-rotate-a-0123456789abcdef"
SECRET_B = "timi-rotate-b-0123456789abcdef"
QUESTIONS = {"probe": {"type": "noul", "instructions": "Is this probe request well formed?"}}


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        length = int(self.headers.get("Content-Length") or "0")
        self.rfile.read(length)
        authorization = self.headers.get("Authorization") or ""
        server = self.server
        server.authorizations.append(authorization)
        if server.rotate_on_first and len(server.authorizations) == 1:
            _write_auth(server.auth_path, SECRET_B)
        body = json.dumps(
            {
                "model": "jev-latest",
                "answers": {"probe": {"type": "noul", "noul": 0.91}},
                "note": f"used {authorization}",
            }
        ).encode("utf-8")
        status = 500 if len(server.authorizations) <= server.failures else 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def log_message(self, fmt: str, *args: object) -> None:
        return


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, auth_path: pathlib.Path) -> None:
        super().__init__(address, _Handler)
        self.authorizations: list[str] = []
        self.rotate_on_first = False
        self.failures = 0
        self.auth_path = auth_path

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"


def _write_auth(path: pathlib.Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timi": {"key": key}}), encoding="utf-8", newline="\n")


def _scope(decision_wire, root: pathlib.Path):
    return decision_wire.WireScope(
        sink=root / "wire.jsonl",
        project_id="proj-t05i-measure",
        scope_kind="production",
        origin="measure",
        decision_id="dec-measure",
        evidence_path=root / "triage.jsonl",
        warn=lambda message: None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("baseline", "final"), required=True)
    args = parser.parse_args()

    for name in ("TIMI_API_KEY", "TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        os.environ.pop(name, None)
    os.environ.pop("TIMI_BASE_URL", None)

    sys.path.insert(0, str(PACKAGES))

    if args.variant == "baseline":
        # The baseline copies must win over the working-tree modules.
        sys.path.insert(0, str(BASELINE))

    import decision  # noqa: PLC0415 - variant-dependent import
    import decision_backends  # noqa: PLC0415
    import decision_wire  # noqa: PLC0415

    resolutions: list[str | None] = []
    original = decision_backends.resolve_timi_api_key

    def spy(env=None, auth_path=None):
        value = original(env, auth_path)
        resolutions.append(value)
        return value

    decision_backends.resolve_timi_api_key = spy

    root = pathlib.Path(tempfile.mkdtemp(prefix="t05i-measure-"))
    auth_path = root / "auth.json"
    decision_backends._auth_json_path = lambda: auth_path

    def cfg(server: _Server):
        return decision.DecisionConfig(
            enabled=True,
            extras={"base_url": server.base_url},
            timeout_s=5.0,
            max_retries=2,
            backoff_base_s=0.0,
        )

    metrics: dict[str, object] = {"variant": args.variant}

    # Scenario 1: rotation inside one logical call (500, 500, 200).
    _write_auth(auth_path, SECRET_A)
    resolutions.clear()
    server1 = _Server(("127.0.0.1", 0), auth_path)
    server1.failures = 2
    server1.rotate_on_first = True
    thread = threading.Thread(target=server1.serve_forever, daemon=True)
    thread.start()
    try:
        scope1 = _scope(decision_wire, root / "one")
        client1 = decision.DecisionClient(
            cfg(server1), decision_backends.TimiDecisionsBackend(), wire_scope=scope1
        )
        result1 = client1.decide({"note": "one"}, QUESTIONS)
        raw1 = scope1.sink.read_bytes() if scope1.sink.exists() else b""
        metrics["one_call"] = {
            "attempts": result1["attempts"],
            "available": result1["available"],
            "resolutions": len(resolutions),
            "post_count": len(server1.authorizations),
            "distinct_authorization_values": len(set(server1.authorizations)),
            "all_attempts_same_authorization": len(set(server1.authorizations)) == 1,
            "capture_carries_any_secret": (
                SECRET_A.encode() in raw1 or SECRET_B.encode() in raw1
            ),
        }
    finally:
        server1.shutdown()
        server1.server_close()
        thread.join(timeout=5)

    # Scenario 2: two logical calls, A then B (rotation picked up by call 2).
    _write_auth(auth_path, SECRET_A)
    resolutions.clear()
    server2 = _Server(("127.0.0.1", 0), auth_path)
    server2.failures = 0
    thread = threading.Thread(target=server2.serve_forever, daemon=True)
    thread.start()
    try:
        scope2 = _scope(decision_wire, root / "two")
        client2 = decision.DecisionClient(
            cfg(server2), decision_backends.TimiDecisionsBackend(), wire_scope=scope2
        )
        first = client2.decide({"note": "first"}, QUESTIONS)
        _write_auth(auth_path, SECRET_B)
        second = client2.decide({"note": "second"}, QUESTIONS)
        raw2 = scope2.sink.read_bytes() if scope2.sink.exists() else b""
        metrics["two_calls"] = {
            "available": [first["available"], second["available"]],
            "resolutions": len(resolutions),
            "first_call_used_a": server2.authorizations[0] == SECRET_A,
            "second_call_used_rotated": server2.authorizations[1] == SECRET_B,
            "one_authorization_per_call": len(set(server2.authorizations)) == 2
            and len(server2.authorizations) >= 2,
            "capture_carries_any_secret": (
                SECRET_A.encode() in raw2 or SECRET_B.encode() in raw2
            ),
        }
    finally:
        server2.shutdown()
        server2.server_close()
        thread.join(timeout=5)

    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
