"""test_decision_dashboard_playground.py - T11b: the DP test tab, end to end.

One joint HTTP + DOM suite for the delivered DP-test flow:

* the monitor's *default* dependency wiring lazily creates exactly one
  ``DecisionPlayground`` per control root (no import-time work, no credential
  discovery, no provider created by opening the page or reading history);
* ``/api/dps`` exposes all 25 registered DPs with their typed required/optional
  contracts, the book budget and the observe-only contract;
* scaffold and validate make zero HTTP requests to the model endpoint; validate
  reports ``context_sent=false`` and never claims the context text was sent;
* an explicit observe submission runs the *real* internal chain against a local
  HTTP fixture (real ``TimiDecisionsBackend``, real wire/evidence capture, a
  real loopback socket): the fixture sees the real POST with the frozen
  credential, and every ledger row carries this submission's id/call id/book
  ref - the answer is joined by explicit ids, never by "the latest call";
* the persisted result projection makes the answer readable again from
  ``/api/test/submissions/<id>`` and ``/api/test/history`` (safe, redacted, no
  raw request/response and no credential);
* duplicate submission (same ``submit_id``) adds no call, a retry uses a new id
  with an explicit ``retry_of`` link, a concurrent submission answers HTTP 409
  (never 200), and every failure stays honest (never a simulated success);
* zero-send paths: invalid book, placeholder book, smuggled execution key,
  oversized state, secret material, globally disabled transport, and an
  unwritable submission ledger all spend no model call;
* production evidence / authorization / archive bytes stay identical, the
  executor is never invoked, and no credential discovery happens at all;
* the shipped ``decision_dashboard.html/js/css`` are replayed in a Node DOM
  shim with the JSON captured *by this test* from the real monitor: the DP tab
  loads only metadata+records on an explicit click, renders typed contracts,
  P0/closed state, validate (context_sent=false), submit/duplicate/retry/409
  busy/detail answers, and never treats HTTP 200 as success.

Real browser acceptance and a real Jev call remain out of scope (not
authorized); the fixture is a local HTTP endpoint, not a stub provider.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import http.server
import json
import os
import pathlib
import subprocess
import threading

import pytest

import decision
import decision_backends
import decision_book
import decision_monitor
import decision_playground
import decision_points as dpts
import decision_wire as wire

import test_decision_dashboard_assets as assets_suite
import test_decision_monitor as monitor_suite

DP1 = "dp1-dispatch-type"
DP4 = "dp4-failure-handling"
DP8 = "dp8-scope-change"

API_KEY = "sk-t11b-fixture-key-0123456789abcdef"
SECRET = "sk-t11b-answer-secret-9f8e7d6c5b4a"
XSS = '<img src=x onerror="globalThis.PWNED=1">'

HOST = decision_monitor.HOST


# ---------------------------------------------------------------------------
# Hermetic fixture: no ambient credential discovery, no config cache
# ---------------------------------------------------------------------------


def _credential_env_names() -> tuple[str, ...]:
    return tuple(
        sorted(name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES))
    )


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    for name in _credential_env_names():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        decision_backends, "_auth_json_path", lambda: tmp_path / "no-auth.json"
    )
    discoveries: list[str] = []

    def _spy_discovery(env=None, auth_path=None):
        discoveries.append("resolve_timi_api_key")
        return None

    monkeypatch.setattr(decision_backends, "resolve_timi_api_key", _spy_discovery)
    monkeypatch.setattr(
        decision_backends, "_AUTH_DISCOVERY_SPY", discoveries, raising=False
    )
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


def _discoveries() -> list[str]:
    return decision_backends._AUTH_DISCOVERY_SPY  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Project fixture, books and hashes
# ---------------------------------------------------------------------------


def _make_project(
    tmp_path: pathlib.Path,
    name: str = "proj",
    *,
    base_url: str | None = None,
    enabled: bool = True,
) -> pathlib.Path:
    project = tmp_path / name
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    config: dict[str, object] = {
        "enabled": enabled,
        "transport": "timi-decisions",
        "model": "jev-latest",
        "timeout_s": 5,
        "max_retries": 0,
    }
    if base_url is not None:
        config["base_url"] = base_url
        config["api_key"] = API_KEY
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return project


def _write_decide_config(project: pathlib.Path, **fields: object) -> None:
    path = project / ".mw" / "decide.json"
    config: dict[str, object] = {"enabled": True, "max_retries": 0, "timeout_s": 5}
    if "api_key" not in fields:
        config["api_key"] = API_KEY
    config.update(fields)
    path.write_text(json.dumps(config, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _tree(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for item in sorted(path.rglob("*")):
        if item.is_file():
            out[item.relative_to(path).as_posix()] = hashlib.sha256(
                item.read_bytes()
            ).hexdigest()
    return out


def _state(dp: str) -> dict:
    if dp == DP1:
        # The approved dp1 contract: the complete dispatch material, nothing else.
        return {
            "schema_version": 2,
            "decision_point": DP1,
            "questions_version": dpts.get_decision_point(DP1).questions_version,
            "task_goal": "deliver the observed DP test flow with zero production writes",
            "task_requirements": "edit a shipped case, submit it, assert the real request body",
            "task_deliverables": "report.md + the observed submit result",
        }
    if dp == DP4:
        return {
            "schema_version": 2,
            "decision_point": DP4,
            "questions_version": dpts.get_decision_point(DP4).questions_version,
            "failure": {"kind": "transient", "attempt": 1, "limit": 2, "artifact_present": False},
        }
    if dp == DP8:
        return {
            "schema_version": 2,
            "decision_point": DP8,
            "questions_version": dpts.get_decision_point(DP8).questions_version,
            "scope": {
                "requested_paths": ["packages/multi-workers/decision_dashboard.js"],
                "write_scope": ["packages/multi-workers"],
                "cross_key_conflicts": [
                    "mw-decision-dashboard:packages/multi-workers/decision_monitor.py"
                ],
                "requirement_delta": "deliver the observed DP test flow with zero production writes",
            },
        }
    raise AssertionError(dp)


def _book(dp: str, state: dict | None = None, **overrides: object) -> dict:
    payload = dict(state if state is not None else _state(dp))
    payload.update(overrides)
    evidence = {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp]}
    return {
        "schema_version": decision_book.BOOK_SCHEMA_VERSION,
        "decision_point": dp,
        "state": payload,
        "notes": {"evidence": evidence},
    }


# ---------------------------------------------------------------------------
# Local HTTP fixture: the real timi backend talks to this endpoint
# ---------------------------------------------------------------------------


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    server_version = "t11b-fixture"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 15

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib
        return

    def do_POST(self) -> None:
        server: _FixtureServer = self.server.fixture  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        server.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
                "body": raw,
            }
        )
        server.received.set()
        if server.hold is not None:
            server.hold.wait(timeout=20)
        status, body = server.response_for(raw)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        with contextlib.suppress(OSError):
            self.wfile.write(body)
        self.close_connection = True


class _FixtureServer:
    """A real loopback HTTP endpoint that answers like the decisions API."""

    def __init__(self, *, extra_answer: dict | None = None) -> None:
        self.requests: list[dict] = []
        self.received = threading.Event()
        self.hold: threading.Event | None = None
        self.status = 200
        self.extra_answer = dict(extra_answer or {})
        self._server = http.server.ThreadingHTTPServer((HOST, 0), _FixtureHandler)
        self._server.daemon_threads = True
        self._server.fixture = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self._server.server_address[1]}"

    def start(self) -> "_FixtureServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def response_for(self, raw: bytes) -> tuple[int, bytes]:
        if self.status != 200:
            return self.status, json.dumps({"error": "fixture failure"}).encode("utf-8")
        payload = json.loads(raw.decode("utf-8"))
        questions = payload.get("questions") if isinstance(payload.get("questions"), dict) else {}
        answers: dict[str, object] = {}
        for qid, spec in questions.items():
            spec = spec if isinstance(spec, dict) else {}
            qtype = spec.get("type")
            if qtype == "choice":
                criteria = spec.get("criteria") if isinstance(spec.get("criteria"), dict) else {}
                choice = next(iter(criteria), None)
                entry: dict[str, object] = {"type": "choice", "choice": choice, "confidence": 0.9}
            elif qtype == "score":
                entry = {"type": "score", "score": 0, "confidence": 0.9}
            elif qtype == "noul":
                entry = {"type": "noul", "noul": 0.9}
            else:
                continue
            entry.update(self.extra_answer)
            answers[str(qid)] = entry
        body = {"model": payload.get("model"), "answers": answers}
        return 200, json.dumps(body, ensure_ascii=False).encode("utf-8")


def _playground_factory(created: list[object]):
    def factory(control_root: pathlib.Path) -> object:
        created.append(str(control_root))
        return decision_playground.DecisionPlayground(control_root, warn=lambda line: None)

    return factory


def _redactor() -> object:
    return wire.SubstringRedactor((API_KEY, SECRET))


@contextlib.contextmanager
def _live(tmp_path: pathlib.Path, *, name: str = "proj", fixture: _FixtureServer | None = None):
    fixture = fixture or _FixtureServer().start()
    project = _make_project(tmp_path, name, base_url=fixture.url)
    created: list[object] = []
    deps = decision_monitor.MonitorDeps(
        redactor=_redactor(), playground_factory=_playground_factory(created)
    )
    try:
        with monitor_suite._running(project, deps=deps) as instance:
            yield project, instance, fixture, created
    finally:
        fixture.stop()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _page_token(instance: object) -> str:
    return monitor_suite._page_token(instance)


def _post(instance: object, path: str, body: dict, token: str) -> tuple[int, dict]:
    status, _headers, payload, _raw = monitor_suite._http(
        instance.port, "POST", path, token=token, origin=instance.origin, body=body
    )
    assert payload is not None, path
    return status, payload


def _get(instance: object, path: str, token: str) -> tuple[int, dict]:
    status, _headers, payload, _raw = monitor_suite._http(
        instance.port, "GET", path, token=token
    )
    assert payload is not None, path
    return status, payload


def _ok_data(payload: dict) -> dict:
    assert payload["ok"] is True, payload
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _test_events(project: pathlib.Path) -> list[dict]:
    root = project / decision_playground.TEST_ROOT_RELATIVE_PATH
    return list(wire.read_events(wire.test_wire_sink(root)).events)


def _of_kind(project: pathlib.Path, kind: str) -> list[dict]:
    return [event for event in _test_events(project) if event.get("kind") == kind]


# ---------------------------------------------------------------------------
# 1. Default wiring: lazily unique, no discovery, no model call
# ---------------------------------------------------------------------------


def test_the_default_deps_create_one_lazy_provider_per_control_root(
    tmp_path: pathlib.Path,
) -> None:
    project = _make_project(tmp_path)
    deps = decision_monitor.MonitorDeps(playground_factory=_playground_factory([]))
    assert deps.playground is None
    first = deps.resolve_playground(project)
    second = deps.resolve_playground(project)
    assert isinstance(first, decision_playground.DecisionPlayground)
    assert first is second, "one provider per control root (busy/dedupe stay meaningful)"
    assert len(deps._resolved_playgrounds) == 1, "the cache is keyed by control root"
    assert deps.playground is None, "the injected slot stays empty (no second wiring)"

    # The command entry points (``serve``/``ensure_instance``) install the
    # shipped lazy factories; a directly constructed instance keeps the
    # explicit-injection contract (deps=None -> no provider -> 503).
    wired = decision_monitor.default_monitor_deps()
    assert wired.playground is None and wired.playground_factory is not None
    assert wired.redactor is None and wired.redactor_factory is not None
    assert decision_monitor._playground_detail(wired) is None
    assert _discoveries() == [], "wiring resolves no credential"
    provider = wired.resolve_playground(project)
    assert isinstance(provider, decision_playground.DecisionPlayground)
    assert wired.resolve_playground(project) is provider
    redactor = wired.resolve_redactor(project)
    assert redactor is not None
    assert wired.resolve_redactor(project) is redactor
    assert len(_discoveries()) == 1, "one root = one response-redactor read"

    injected = decision_monitor.MonitorInstance(project, port_range=(43170, 43171))
    try:
        assert injected.deps.playground is None
        assert injected.deps.playground_factory is None
    finally:
        assert injected.listener is None


def test_the_command_path_wiring_serves_the_whole_dp_flow(tmp_path: pathlib.Path) -> None:
    """`mw decide monitor` builds its deps here: no explicit provider injected."""
    fixture = _FixtureServer().start()
    try:
        project = _make_project(tmp_path, base_url=fixture.url)
        instance = decision_monitor.ensure_instance(project)
        try:
            assert instance.deps.playground is None
            assert instance.deps.playground_factory is not None
            assert instance.deps.redactor is None
            assert instance.deps.redactor_factory is not None
            token = _page_token(instance)
            status, payload = _get(instance, "/api/dps", token)
            assert status == 200
            assert len(_ok_data(payload)["points"]) == 25
            status, payload = _get(instance, "/api/test/history", token)
            assert status == 200
            status, payload = _post(instance, "/api/test/scaffold", {"dp": DP1}, token)
            assert status == 200
            status, payload = _post(
                instance,
                "/api/test/submit",
                {
                    "dp": DP1,
                    "book": _book(DP1),
                    "submit_id": "sub-default-1",
                    "observe_only": True,
                },
                token,
            )
            assert status == 200, payload
            result = _ok_data(payload)
            assert result["state"] == "succeeded", result
            assert result["answer_persisted"] is True
            assert fixture.calls == 1
            status, payload = _get(instance, "/api/health", token=instance.control_token)
            assert status == 200
            assert payload["data"]["playground"] == {"state": "wired", "detail": None}
        finally:
            instance.stop()
    finally:
        fixture.stop()


def test_dps_route_lists_all_25_typed_contracts_without_a_provider(tmp_path: pathlib.Path) -> None:
    project = _make_project(tmp_path)
    created: list[object] = []
    deps = decision_monitor.MonitorDeps(
        redactor=_redactor(), playground_factory=_playground_factory(created)
    )
    with monitor_suite._running(project, deps=deps) as instance:
        token = _page_token(instance)
        status, payload = _get(instance, "/api/dps", token)
        assert status == 200
        data = _ok_data(payload)
        assert len(data["points"]) == 25
        by_id = {point["id"]: point for point in data["points"]}
        assert set(by_id) == {point.id for point in dpts.DP_REGISTRY}
        for point in data["points"]:
            required = point["required_state_fields"]
            optional = point["optional_state_fields"]
            assert isinstance(required, list) and required
            for field in required + optional:
                assert isinstance(field["name"], str) and field["name"]
                assert isinstance(field["type"], str) and field["type"]
                assert isinstance(field["description"], str)
            assert point["questions_version"]
        assert by_id[DP8]["tier"] == "P0" and by_id[DP8]["default_enabled"] is False
        assert by_id[DP1]["tier"] == "P2" and by_id[DP1]["default_enabled"] is True
        assert data["budget"]["max_state_bytes"] == dpts.MAX_STATE_BYTES
        assert data["observe_only"] is True
        assert created == [], "the registry route must not create a provider"
        assert _discoveries() == []


def test_every_registered_dp_scaffolds_and_validates_without_a_call(tmp_path: pathlib.Path) -> None:
    """All 25 contracts: typed skeleton, explicit validate, zero model calls."""
    with _live(tmp_path) as (project, instance, fixture, created):
        token = _page_token(instance)
        seen: list[str] = []
        for point in dpts.DP_REGISTRY:
            status, payload = _post(instance, "/api/test/scaffold", {"dp": point.id}, token)
            assert status == 200, point.id
            scaffold = _ok_data(payload)
            assert scaffold["dp"] == point.id
            assert scaffold["book"]["decision_point"] == point.id
            required = scaffold["required_state_fields"]
            optional = scaffold["optional_state_fields"]
            assert {field["name"] for field in required} == set(
                dpts.REQUIRED_STATE_FIELDS[point.id]
            ), point.id
            assert {field["name"] for field in optional} == set(
                dpts.OPTIONAL_STATE_FIELDS.get(point.id, ())
            ), point.id
            assert all(field["type"] for field in required + optional), point.id

            status, payload = _post(
                instance,
                "/api/test/validate",
                {"dp": point.id, "book": scaffold["book"]},
                token,
            )
            assert status == 200, point.id
            report = _ok_data(payload)
            assert report["dp"] == point.id
            assert report["ok"] is False, "an untouched skeleton is never submittable"
            assert any(
                issue["code"] == "book-placeholder" for issue in report["issues"]
            ), point.id
            assert report["context_sent"] is False
            seen.append(point.id)
        assert seen == [point.id for point in dpts.DP_REGISTRY]
        assert len(created) == 1, "all 25 DPs share one provider for the control root"
        assert fixture.calls == 0, "no scaffold/validate may reach the model endpoint"
        assert _of_kind(project, "submission-start") == []


# ---------------------------------------------------------------------------
# 2. scaffold / validate: zero send, context not sent
# ---------------------------------------------------------------------------


def test_scaffold_and_validate_expose_the_questions_and_the_request_preview(
    tmp_path: pathlib.Path,
) -> None:
    """T10: default questions + the final ``{model, state, questions}`` preview."""
    with _live(tmp_path) as (project, instance, fixture, created):
        token = _page_token(instance)
        status, payload = _post(instance, "/api/test/scaffold", {"dp": DP1}, token)
        assert status == 200
        scaffold = _ok_data(payload)
        assert scaffold["questions"] == dpts.questions_map(DP1)
        assert scaffold["questions_version"] == dpts.get_decision_point(DP1).questions_version

        edited = json.loads(json.dumps(scaffold["questions"], ensure_ascii=False))
        edited["triage_type"]["instructions"] = "T10 edited: which worker type?"
        status, payload = _post(
            instance,
            "/api/test/validate",
            {"dp": DP1, "book": _book(DP1), "questions": edited},
            token,
        )
        assert status == 200
        report = _ok_data(payload)
        assert report["ok"] is True, report["issues"]
        assert report["questions_source"] == "override"
        assert report["questions"]["triage_type"]["instructions"] == (
            "T10 edited: which worker type?"
        )
        preview = report["request_preview"]
        assert set(preview) == {"model", "state", "questions"}
        assert preview["questions"]["triage_type"]["instructions"] == (
            "T10 edited: which worker type?"
        )
        assert set(preview["state"]) == {
            "task_goal",
            "task_requirements",
            "task_deliverables",
        }, "the preview carries the projected send state, not the book wrapper"
        assert preview["model"] == "jev-latest"

        # Without an override the provider keeps the registry questions; the
        # preview is still produced by the same builder (and never sends).
        status, payload = _post(
            instance, "/api/test/validate", {"dp": DP1, "book": _book(DP1)}, token
        )
        assert status == 200
        plain = _ok_data(payload)
        assert plain["ok"] is True
        assert plain["questions_source"] == "registry"
        assert plain["questions"] == dpts.questions_map(DP1)
        assert plain["request_preview"]["questions"] == {
            "triage_type": {
                "type": "choice",
                "instructions": dpts.questions_map(DP1)["triage_type"]["instructions"],
                "criteria": dpts.questions_map(DP1)["triage_type"]["labels"],
            }
        }
        assert fixture.calls == 0, "a preview never reaches the model endpoint"
        assert _of_kind(project, "attempt-start") == []


def test_scaffold_and_validate_spend_no_call_and_state_context_is_not_sent(
    tmp_path: pathlib.Path,
) -> None:
    with _live(tmp_path) as (project, instance, fixture, created):
        token = _page_token(instance)
        status, payload = _post(instance, "/api/test/scaffold", {"dp": DP1}, token)
        assert status == 200
        scaffold = _ok_data(payload)
        assert scaffold["dp"] == DP1
        assert scaffold["observe_only"] is True
        assert scaffold["book"]["decision_point"] == DP1
        required = [field["name"] for field in scaffold["required_state_fields"]]
        assert required == list(dpts.REQUIRED_STATE_FIELDS[DP1])
        assert scaffold["optional_state_fields"] == []
        assert scaffold["max_state_bytes"] == dpts.MAX_STATE_BYTES
        assert len(created) == 1, "exactly one provider is created for this control root"
        assert _discoveries() == [], "scaffold resolves no credential"

        # The untouched skeleton is refused without any request.
        status, payload = _post(
            instance, "/api/test/validate", {"dp": DP1, "book": scaffold["book"]}, token
        )
        assert status == 200
        placeholder = _ok_data(payload)
        assert placeholder["ok"] is False
        assert any(issue["code"] == "book-placeholder" for issue in placeholder["issues"])
        assert fixture.calls == 0
        assert len(_discoveries()) == 1, "one explicit validate = one credential unit"

        # The context slot belongs to the failure-carrying dp4 contract (dp1 has
        # no slot any more), and the block is listed but never sent.
        book = _book(DP4)
        book["context"] = {"error_excerpt": "worker-3: pytest exited 1"}
        book["notes"]["evidence"]["context.error_excerpt"] = "cmd: true"
        status, payload = _post(instance, "/api/test/validate", {"dp": DP4, "book": book}, token)
        assert status == 200
        report = _ok_data(payload)
        assert report["ok"] is True, report["issues"]
        assert report["context_slots"] == ["error_excerpt"]
        assert report["context_sent"] is False
        assert report["context_note"]
        assert report["state_bytes"] <= report["max_state_bytes"]
        assert report["observe_only"] is True
        assert fixture.calls == 0, "validate must never reach the model endpoint"
        assert _of_kind(project, "submission-start") == []
        assert _of_kind(project, "attempt-start") == []
        # T05l (unchanged by this card): each explicit credential unit freezes
        # its known set, and a cfg/extras key pays exactly one legacy-leg read
        # per unit. Nothing is read at import, on the registry route, or while
        # reading history (0 above), and no page load spends a unit.
        assert len(_discoveries()) == 2, _discoveries()


# ---------------------------------------------------------------------------
# 3. The real observe submission over loopback
# ---------------------------------------------------------------------------


def test_real_submit_posts_to_the_fixture_and_joins_the_answer_by_ids(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor_calls: list[object] = []

    def spy_executor(answers, trigger):
        executor_calls.append(answers)
        return "acted"

    point = dpts._REGISTRY_BY_ID[DP1]
    monkeypatch.setitem(
        dpts._REGISTRY_BY_ID, DP1, dataclasses.replace(point, executor=spy_executor)
    )

    with _live(tmp_path) as (project, instance, fixture, created):
        # Seed production facts so "unchanged" is meaningful.
        archive = project / ".agenticdoc" / "_autopilot" / "decisions.jsonl"
        archive.write_text(
            json.dumps({"seq": 1, "kind": "signoff", "outcome": "ok"}) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        signoff = project / ".agenticdoc" / "_autopilot" / "signoff.json"
        signoff.write_bytes(b'{"rows_sha256":"pre-existing","counted_rows":7}\n')
        evidence_before = _tree(project / ".agenticdoc")
        config_before = (project / ".mw" / "decide.json").read_bytes()

        token = _page_token(instance)
        # dp1 has no context slot in the approved contract: the observe book is
        # exactly the complete material (the no-context assertion below stays).
        book = _book(DP1)
        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP1, "book": book, "submit_id": "sub-live-1", "observe_only": True},
            token,
        )
        assert status == 200, payload
        result = _ok_data(payload)
        assert result["state"] == "succeeded", result
        assert result["accepted"] is True
        assert result["duplicate"] is False
        assert result["busy"] is False
        assert result["zero_call"] is False
        assert result["record_status"] == "recorded"
        assert result["observe_only"] is True
        assert result["decision_id"] == f"{DP1}:sub-live-1"
        assert isinstance(result["call_id"], str) and result["call_id"]
        assert isinstance(result["book_ref"], str) and result["book_ref"].startswith("book-")
        assert result["http_attempts"] == 1
        assert result["capture_status"] in ("ok", "partial")
        assert result["answer"] == {
            "triage_type": {"value": "coding", "confidence": 0.9},
        }
        assert result["outcome"]["status"] == "suggested"
        assert result["answer_persisted"] is True
        assert result["projection_status"] == "recorded"
        assert isinstance(result["projection_sha256"], str) and len(result["projection_sha256"]) == 64
        assert executor_calls == [], "an observation never invokes the executor"

        # The real backend made exactly one real HTTP POST with the frozen key.
        assert fixture.calls == 1
        request = fixture.requests[0]
        assert request["path"] == "/v1/decisions"
        assert request["authorization"] == API_KEY
        sent = json.loads(request["body"].decode("utf-8"))
        assert sent["model"] == "jev-latest"
        # dp1's model projection is the three business fields only (identity and
        # local association facts never reach the transport).
        assert set(sent["state"]) == {
            "task_goal",
            "task_requirements",
            "task_deliverables",
        }
        assert set(sent["questions"]) == {"triage_type"}
        assert "context" not in sent["state"], "the context block is never sent"

        # Wire/evidence rows carry this submission's explicit ids and captures.
        starts = _of_kind(project, "submission-start")
        ends = _of_kind(project, "submission-end")
        attempts = _of_kind(project, "attempt-start")
        attempt_ends = _of_kind(project, "attempt-end")
        calls = _of_kind(project, "call-end")
        decisions = _of_kind(project, "decision-end")
        assert len(starts) == 1 and len(ends) == 1
        assert len(attempts) == 1 and len(attempt_ends) == 1
        assert len(calls) == 1 and len(decisions) == 1
        for event in starts + ends + attempts + attempt_ends + calls + decisions:
            assert event["submission_id"] == "sub-live-1"
            assert event["scope"] == "test"
            assert event["decision_id"] == f"{DP1}:sub-live-1"
        for event in attempts + attempt_ends + calls + decisions:
            assert event["call_id"] == result["call_id"], event["kind"]
        assert ends[0]["book_ref"] == result["book_ref"]
        assert attempts[0]["request"]["text_omitted"] is False
        assert attempt_ends[0]["http_status"] == 200
        assert attempt_ends[0]["response"]["text_omitted"] is False
        assert attempt_ends[0]["response"]["stored_len"] > 0
        assert isinstance(attempt_ends[0]["response"]["captured_redacted_sha256"], str)
        assert calls[0]["available"] is True
        assert calls[0]["wire_attempts"] == 1
        assert decisions[0]["book_ref"] == result["book_ref"]
        assert decisions[0]["status"] == "suggested"

        # The persisted projection is the safe result only.
        sink = project / decision_playground.TEST_ROOT_RELATIVE_PATH
        projection = json.loads(
            (sink / decision_playground.RESULTS_DIR_NAME / "sub-live-1.json").read_text(
                encoding="utf-8"
            )
        )
        body = projection["projection"]
        assert body["submission_id"] == "sub-live-1"
        assert body["call_id"] == result["call_id"]
        assert body["book_ref"] == result["book_ref"]
        assert body["answer_present"] is True
        assert body["redaction"]["legs"] == ["known-secret", "capture"]
        raw_projection = json.dumps(projection, ensure_ascii=False)
        assert API_KEY not in raw_projection
        assert SECRET not in raw_projection
        assert "request" not in body
        assert set(body["outcome"]["response"]) <= {
            "available",
            "transport",
            "model",
            "attempts",
            "latency_ms",
            "reason",
            "confidence_source",
        }
        assert "\"text\"" not in raw_projection, "no raw capture text is copied"

        # Polling / re-opening / history read that answer back, by this id only.
        status, payload = _get(instance, "/api/test/submissions/sub-live-1", token)
        assert status == 200
        polled = _ok_data(payload)
        assert polled["state"] == "succeeded"
        assert polled["call_id"] == result["call_id"]
        assert polled["book_ref"] == result["book_ref"]
        assert polled["answer"] == result["answer"]
        assert polled["answer_persisted"] is True
        assert polled["outcome"]["answer"] == result["answer"]
        attempts = polled["attempts"]
        assert len(attempts) == 1, attempts
        attempt = attempts[0]
        assert attempt["method"] == "POST"
        assert attempt["url_path"] == "/v1/decisions"
        assert attempt["http_status"] == 200
        assert attempt["unfinished"] is False
        assert attempt["request"]["text_omitted"] is False
        assert json.loads(attempt["request"]["text"])["state"] == sent["state"]
        assert attempt["request"]["byte_exact"] is True
        assert attempt["response"]["text_omitted"] is False
        assert json.loads(attempt["response"]["text"])["answers"]["triage_type"]["choice"] == "coding"
        assert "context" not in json.loads(attempt["request"]["text"])["state"]

        status, payload = _get(instance, "/api/test/history", token)
        assert status == 200
        history = _ok_data(payload)
        assert history["scope"] == "test" and history["source"] == "test"
        assert history["observe_only"] is True
        assert [record["submission_id"] for record in history["records"]] == ["sub-live-1"]
        assert history["records"][0]["answer"] == result["answer"]
        listed = history["records"][0]["attempts"]
        assert len(listed) == 1
        assert listed[0]["request"].get("output_omitted") is True
        assert "text" not in listed[0]["request"], "the list view never echoes bodies"
        assert "text" not in listed[0]["response"]
        assert listed[0]["http_status"] == 200
        assert history["warnings"] == []

        # Production facts and the credential config stay byte-identical.
        assert _tree(project / ".agenticdoc") == evidence_before
        assert (project / ".mw" / "decide.json").read_bytes() == config_before
        assert len(_discoveries()) == 1, (
            "one submission = one credential unit = at most the documented T05l read; "
            "the sent Authorization still comes from the cfg key"
        )


# ---------------------------------------------------------------------------
# 4. Duplicate / retry / busy(409)
# ---------------------------------------------------------------------------


def test_duplicate_retry_and_busy_are_honest(tmp_path: pathlib.Path) -> None:
    with _live(tmp_path) as (project, instance, fixture, _created):
        token = _page_token(instance)
        book = _book(DP1)
        base = {"dp": DP1, "book": book, "observe_only": True}

        status, payload = _post(instance, "/api/test/submit", {**base, "submit_id": "sub-a"}, token)
        first = _ok_data(payload)
        assert status == 200 and first["state"] == "succeeded"
        first_call = first["call_id"]
        assert fixture.calls == 1

        status, payload = _post(instance, "/api/test/submit", {**base, "submit_id": "sub-a"}, token)
        duplicate = _ok_data(payload)
        assert status == 200
        assert duplicate["duplicate"] is True
        assert duplicate["submission_id"] == "sub-a"
        assert duplicate["call_id"] == first_call
        assert fixture.calls == 1, "a duplicate submit_id never adds a call"
        assert len(_of_kind(project, "submission-start")) == 1

        status, payload = _post(
            instance,
            "/api/test/submit",
            {**base, "submit_id": "sub-b", "retry_of": "sub-a"},
            token,
        )
        retried = _ok_data(payload)
        assert status == 200
        assert retried["state"] == "succeeded"
        assert retried["retry_of"] == "sub-a"
        assert retried["call_id"] != first_call
        assert retried["answer"] == first["answer"]
        assert fixture.calls == 2, "a retry is a new submission with a new id"
        assert len(_of_kind(project, "call-end")) == 2

        # An unknown retry target is refused with zero calls.
        status, payload = _post(
            instance,
            "/api/test/submit",
            {**base, "submit_id": "sub-c", "retry_of": "no-such-submission"},
            token,
        )
        refused = _ok_data(payload)
        assert status == 200
        assert refused["state"] == "rejected"
        assert refused["zero_call"] is True
        assert refused["record_status"] == "not-recorded"
        assert fixture.calls == 2

        # A concurrent submission answers 409 (never 200) and adds no call.
        fixture.hold = threading.Event()
        fixture.received.clear()
        held: list[dict] = []

        def _hold_submit() -> None:
            held.append(monitor_suite._http(
                instance.port,
                "POST",
                "/api/test/submit",
                token=token,
                origin=instance.origin,
                body={**base, "submit_id": "sub-busy-1"},
            )[2])

        thread = threading.Thread(target=_hold_submit, daemon=True)
        thread.start()
        assert fixture.received.wait(10), "the held submission never reached the fixture"
        status, payload = _post(
            instance, "/api/test/submit", {**base, "submit_id": "sub-busy-2"}, token
        )
        assert status == 409, payload
        assert payload["ok"] is False
        assert payload["error"]["code"] == "busy"
        busy = payload["data"]
        assert busy["state"] == "busy"
        assert busy["busy"] is True
        assert busy["accepted"] is False
        assert busy["zero_call"] is True
        assert busy["record_status"] == "not-recorded"
        assert fixture.calls == 3, "the busy refusal sent nothing"
        fixture.hold.set()
        thread.join(timeout=20)
        fixture.hold = None
        assert held and held[0]["ok"] is True
        assert _ok_data(held[0])["state"] == "succeeded"

        history_ids = [
            record["submission_id"] for record in _ok_data(_get(instance, "/api/test/history", token)[1])["records"]
        ]
        assert "sub-busy-2" not in history_ids, "a busy refusal writes no submission"


# ---------------------------------------------------------------------------
# 5. Zero-send refusals (invalid / smuggled / oversize / secret / disabled / start)
# ---------------------------------------------------------------------------


def test_invalid_smuggled_oversize_and_secret_books_spend_no_call(tmp_path: pathlib.Path) -> None:
    with _live(tmp_path) as (project, instance, fixture, _created):
        token = _page_token(instance)

        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP1, "book": decision_book.scaffold_book(DP1),
             "submit_id": "sub-placeholder", "observe_only": True},
            token,
        )
        assert status == 200
        placeholder = _ok_data(payload)
        assert placeholder["state"] == "rejected"
        assert placeholder["zero_call"] is True
        assert any(issue["code"] == "book-placeholder" for issue in placeholder["issues"])
        assert fixture.calls == 0

        smuggled_book = _book(DP1)
        smuggled_book["state"]["history"] = {"recent_done": 1, "act": True}
        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP1, "book": smuggled_book, "submit_id": "sub-smuggle", "observe_only": True},
            token,
        )
        assert status == 400, payload
        assert payload["error"]["code"] == "forbidden-field"
        assert fixture.calls == 0

        # A top-level execution field is refused by the monitor seam itself.
        status, payload = _post(
            instance,
            "/api/test/submit",
            {
                "dp": DP1,
                "book": _book(DP1),
                "submit_id": "sub-top-act",
                "observe_only": True,
                "act": "apply",
            },
            token,
        )
        assert status == 400
        assert payload["error"]["code"] == "forbidden-field"
        assert fixture.calls == 0

        over = _book(DP1)
        # One required string over the published budget: refused whole, never cut.
        over["state"]["task_goal"] = "x" * (dpts.MAX_STATE_BYTES + 1)
        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP1, "book": over, "submit_id": "sub-over", "observe_only": True},
            token,
        )
        assert status == 200
        oversized = _ok_data(payload)
        assert oversized["state"] == "rejected"
        assert oversized["zero_call"] is True
        assert any(issue["code"] == "book-budget" for issue in oversized["issues"])
        assert oversized["outcome"] is None
        assert fixture.calls == 0

        secret_book = _book(DP1)
        secret_book["state"]["task_requirements"] = "leaked " + SECRET
        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP1, "book": secret_book, "submit_id": "sub-secret", "observe_only": True},
            token,
        )
        assert status == 200
        secret = _ok_data(payload)
        assert secret["state"] == "rejected"
        assert secret["zero_call"] is True
        assert fixture.calls == 0
        assert SECRET not in json.dumps(payload, ensure_ascii=False)
        ledger = (project / decision_playground.TEST_ROOT_RELATIVE_PATH / "wire.jsonl").read_text(
            encoding="utf-8"
        )
        assert SECRET not in ledger

        # observe_only is not optional: the monitor refuses a request without it.
        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP1, "book": _book(DP1), "submit_id": "sub-noobserve"},
            token,
        )
        assert status == 400
        assert payload["error"]["code"] == "invalid-field"
        assert fixture.calls == 0


def test_globally_disabled_transport_sends_nothing(tmp_path: pathlib.Path) -> None:
    with _live(tmp_path) as (project, instance, fixture, _created):
        token = _page_token(instance)
        _write_decide_config(project, enabled=False, base_url=fixture.url)
        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP1, "book": _book(DP1), "submit_id": "sub-disabled", "observe_only": True},
            token,
        )
        assert status == 200
        result = _ok_data(payload)
        assert result["state"] in ("unavailable", "rejected", "failed")
        assert result["state"] != "succeeded"
        assert result["zero_call"] is True
        assert result["record_status"] == "recorded"
        assert result["call_id"] is None
        assert fixture.calls == 0
        assert result["outcome"]["escalated_reason"] == "unavailable"
        assert result["answer_persisted"] is False
        assert result["answer"] is None
        # The refusal itself is persisted (no answer, zero call) so re-opening
        # the detail shows the same honest facts.
        assert result["projection_status"] == "recorded"
        assert result["projection_sha256"]
        ends = _of_kind(project, "submission-end")
        assert len(ends) == 1 and ends[0]["zero_call"] is True


def test_a_failed_submission_start_means_zero_calls(tmp_path: pathlib.Path) -> None:
    with _live(tmp_path) as (project, instance, fixture, _created):
        token = _page_token(instance)
        sink = project / decision_playground.TEST_ROOT_RELATIVE_PATH
        sink.parent.mkdir(parents=True, exist_ok=True)
        sink.write_text("not a directory\n", encoding="utf-8", newline="\n")
        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP1, "book": _book(DP1), "submit_id": "sub-startfail", "observe_only": True},
            token,
        )
        assert status == 200
        result = _ok_data(payload)
        assert result["state"] == "record-failed"
        assert result["zero_call"] is True
        assert result["record_status"] == "failed"
        assert result["issues"][0]["code"] == "record-failed"
        assert fixture.calls == 0


def test_p0_observation_bypass_never_authorizes_or_executes(tmp_path: pathlib.Path) -> None:
    with _live(tmp_path) as (project, instance, fixture, _created):
        authorization = project / ".mw" / "decide-points.json"
        authorization.write_text(
            json.dumps({"version": 1, "points": {DP8: {"enabled": False, "mode": "auto"}}}) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        dpts.clear_points_config_cache()
        before = _tree(project / ".agenticdoc")
        points_before = authorization.read_bytes()
        token = _page_token(instance)
        status, payload = _post(
            instance,
            "/api/test/submit",
            {"dp": DP8, "book": _book(DP8), "submit_id": "sub-p0", "observe_only": True},
            token,
        )
        assert status == 200
        result = _ok_data(payload)
        assert result["state"] == "succeeded", result
        assert result["decision_ran"] is True
        assert fixture.calls == 1, "the human observe path may call the model"
        decisions = _of_kind(project, "decision-end")
        assert decisions[0]["status"] == "suggested"
        # The observation marker lives in the live response view.
        assert result["outcome"]["observation"]["bypassed"] is True
        assert result["outcome"]["preview"] is not None
        assert result["outcome"]["preview"]["would_act"] is False
        assert _tree(project / ".agenticdoc") == before, "no authorization/archive write"
        assert not (project / dpts.DECISIONS_RELATIVE_PATH).exists()
        assert authorization.read_bytes() == points_before, "the local points config is unchanged"


# ---------------------------------------------------------------------------
# 6. DOM replay of the JSON captured by this test
# ---------------------------------------------------------------------------


DOM_DRIVER_JS = r'''
const htmlPath = process.argv[2];
const jsPath = process.argv[3];
const scenarioPath = process.argv[4];
const scenario = JSON.parse(fs.readFileSync(scenarioPath, "utf8"));
const htmlSource = fs.readFileSync(htmlPath, "utf8");

const documentRoot = parseHTML(htmlSource);
const document = {
  readyState: "complete",
  title: "mw decide monitor",
  cookie: "",
  createElement(tag) { return new Element(tag); },
  createTextNode(text) { return new TextNode(text); },
  getElementById(id) { return findFirst(documentRoot, "#" + id); },
  querySelectorAll(selector) { return findAll(documentRoot, selector); },
  addEventListener() {},
};
document.body = findFirst(documentRoot, "body");
document.documentElement = findFirst(documentRoot, "html");

const location = {
  href: "http://127.0.0.1:43170/",
  protocol: "http:",
  host: "127.0.0.1:43170",
  hostname: "127.0.0.1",
  port: "43170",
  pathname: "/",
  search: "",
  hash: scenario.hash || "",
};
const historyApi = {
  replaceState(_state, _title, url) {
    const parsed = new URL(String(url), location.href);
    location.pathname = parsed.pathname;
    location.search = parsed.search;
    location.hash = parsed.hash;
    location.href = parsed.href;
  },
};

const fetchCalls = [];
const storageWrites = [];
function storageTrap(area) {
  return {
    getItem() { return null; },
    removeItem() {},
    setItem(key, value) { storageWrites.push({ area, key: String(key), value: String(value) }); },
    clear() { storageWrites.push({ area, key: "<clear>", value: "" }); },
  };
}
function responseFor(entry) {
  let item = entry;
  if (Array.isArray(entry)) {
    item = entry.length > 1 ? entry.shift() : entry[0];
  }
  const status = item && typeof item.status === "number" ? item.status : 200;
  const body = item ? item.body : { ok: false, data: null, error: { code: "no-mock" } };
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get() { return null; } },
    async json() { return body; },
    async text() { return JSON.stringify(body); },
  };
}
function pick(url) {
  const responses = scenario.responses || {};
  if (Object.prototype.hasOwnProperty.call(responses, url)) return responses[url];
  const keys = Object.keys(responses);
  for (const key of keys) {
    if (key.endsWith(":id")) {
      const prefix = key.slice(0, -3);
      if (url.startsWith(prefix) && url.slice(prefix.length).indexOf("/") === -1) {
        return responses[key];
      }
    }
  }
  return null;
}
async function mockFetch(input, options) {
  const raw = String(input);
  const parsed = new URL(raw, location.href);
  const url = parsed.pathname + parsed.search;
  const opts = options || {};
  fetchCalls.push({
    url,
    method: String(opts.method || "GET").toUpperCase(),
    headers: Object.assign({}, opts.headers || {}),
    body: opts.body === undefined || opts.body === null ? null : String(opts.body),
  });
  const entry = pick(url);
  if (entry === null) {
    return responseFor({ status: 404, body: { ok: false, data: null, error: { code: "unexpected-route", message: url } } });
  }
  return responseFor(entry);
}

const sandbox = {
  document,
  location,
  history: historyApi,
  fetch: mockFetch,
  URL,
  URLSearchParams,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  console: { log() {}, warn() {}, error() {} },
  localStorage: storageTrap("localStorage"),
  sessionStorage: storageTrap("sessionStorage"),
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

function textOf(id) {
  const node = document.getElementById(id);
  return node ? node.textContent : null;
}
function hasAttr(id, name) {
  const node = document.getElementById(id);
  return Boolean(node && node.hasAttribute(name));
}
function snapshot(label) {
  const rows = document.querySelectorAll('[data-testid="pg-history-row"]');
  return {
    label,
    hash: location.hash,
    href: location.href,
    fetchCalls: fetchCalls.map((call) => ({
      url: call.url,
      method: call.method,
      headers: Object.assign({}, call.headers),
      body: call.body,
    })),
    storage: storageWrites.slice(),
    bootStatus: textOf("boot-status"),
    error: textOf("error-banner"),
    historyStats: textOf("history-stats"),
    playgroundText: textOf("panel-playground"),
    pgStatus: textOf("playground-status"),
    pgMeta: textOf("pg-meta"),
    pgFields: textOf("pg-fields"),
    pgValidate: textOf("pg-validate-out"),
    pgSubmit: textOf("pg-submit-out"),
    pgSubmitId: textOf("pg-submit-id"),
    pgHistoryMeta: textOf("pg-history-meta"),
    pgHistoryRows: rows.map((row) => row.textContent),
    pgDetail: textOf("pg-detail"),
    pgDetailVisible: (textOf("pg-detail") || "").length > 0,
    playgroundVisible: !hasAttr("panel-playground", "hidden"),
    playgroundForms: document.querySelectorAll('#panel-playground form, #panel-playground input, #panel-playground button[type="submit"]').length,
    pwned: Boolean(sandbox.PWNED),
    imgCount: document.querySelectorAll("img").length,
    scriptTags: document.querySelectorAll("script").length,
    bodyText: document.body ? document.body.textContent : "",
  };
}
async function drain() {
  for (let index = 0; index < 30; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}
function find(selector) {
  const node = findFirst(documentRoot, selector);
  if (!node) throw new Error("selector not found: " + selector);
  return node;
}
async function run() {
  const vmContext = vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(jsPath, "utf8"), vmContext, { filename: jsPath, timeout: 20000 });
  await drain();
  const snapshots = [snapshot("boot")];
  for (const step of scenario.steps || []) {
    if (step.type === "click") {
      find(step.target).click();
    } else if (step.type === "setValue") {
      const node = find(step.target);
      node.value = String(step.value);
      if (step.change) node.dispatchEvent({ type: "change" });
    } else if (step.type === "snapshot") {
      snapshots.push(snapshot(step.label || "step"));
      continue;
    } else {
      throw new Error("unknown step " + JSON.stringify(step));
    }
    await drain();
    if (step.snapshot) snapshots.push(snapshot(step.snapshot));
  }
  return { ok: true, snapshots };
}
run().then((result) => {
  process.stdout.write(JSON.stringify(result));
}).catch((error) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String((error && error.stack) || error), snapshots: [] }));
  process.exitCode = 1;
});
'''


def _run_dom(tmp_path: pathlib.Path, scenario: dict) -> dict:
    node = shutil_node()
    work = tmp_path / "dom"
    work.mkdir(parents=True, exist_ok=True)
    harness = work / "dom_playground.cjs"
    harness.write_text(
        assets_suite.DOM_HARNESS_JS.split("const htmlPath =")[0] + DOM_DRIVER_JS,
        encoding="utf-8",
    )
    scenario_path = work / "scenario.json"
    scenario_path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    process = subprocess.run(
        [
            node,
            str(harness),
            str(decision_monitor.ASSET_DIR / "decision_dashboard.html"),
            str(decision_monitor.ASSET_DIR / "decision_dashboard.js"),
            str(scenario_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(work),
        timeout=180,
    )
    assert process.stdout, f"node produced no output (stderr={process.stderr})"
    assert process.returncode == 0, process.stdout + "\n--- stderr ---\n" + process.stderr
    result = json.loads(process.stdout.strip().splitlines()[-1])
    assert result.get("ok") is True, process.stdout + "\n--- stderr ---\n" + process.stderr
    return result


def shutil_node() -> str:
    import shutil

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable: the DOM behaviour cannot be exercised")
    return node


def _snapshot(result: dict, label: str) -> dict:
    for snapshot in result["snapshots"]:
        if snapshot["label"] == label:
            return snapshot
    raise AssertionError(f"missing snapshot {label}: {[s['label'] for s in result['snapshots']]}")


def _json_body(call: dict) -> dict:
    assert call["body"], call
    return json.loads(call["body"])


def test_dp_tab_dom_replays_the_captured_json_end_to_end(tmp_path: pathlib.Path) -> None:
    fixture = _FixtureServer(extra_answer={"probabilities": {"p": SECRET + XSS}}).start()
    try:
        with _live(tmp_path, fixture=fixture) as (project, instance, fixture_server, _created):
            token = _page_token(instance)
            dps = _get(instance, "/api/dps", token)[1]
            scaffold_payload = _post(instance, "/api/test/scaffold", {"dp": DP1}, token)[1]
            scaffold = _ok_data(scaffold_payload)
            book = _book(DP1)
            # dp1 declares no context slot: the book is the complete material only.
            validate_ok = _post(instance, "/api/test/validate", {"dp": DP1, "book": book}, token)[1]
            validate_placeholder = _post(
                instance,
                "/api/test/validate",
                {"dp": DP1, "book": scaffold["book"]},
                token,
            )[1]
            history_empty = _get(instance, "/api/test/history", token)[1]

            submit_ok = _post(
                instance,
                "/api/test/submit",
                {"dp": DP1, "book": book, "submit_id": "sub-dom-1", "observe_only": True},
                token,
            )[1]
            history_one = _get(instance, "/api/test/history", token)[1]
            submit_dup = _post(
                instance,
                "/api/test/submit",
                {"dp": DP1, "book": book, "submit_id": "sub-dom-1", "observe_only": True},
                token,
            )[1]
            history_two = _get(instance, "/api/test/history", token)[1]
            submit_retry = _post(
                instance,
                "/api/test/submit",
                {
                    "dp": DP1,
                    "book": book,
                    "submit_id": "sub-dom-2",
                    "retry_of": "sub-dom-1",
                    "observe_only": True,
                },
                token,
            )[1]
            history_three = _get(instance, "/api/test/history", token)[1]
            detail = _get(instance, "/api/test/submissions/sub-dom-1", token)[1]
            assert _ok_data(submit_ok)["answer_persisted"] is True
            assert _ok_data(submit_dup)["duplicate"] is True
            assert _ok_data(submit_retry)["retry_of"] == "sub-dom-1"

            # A real 409: hold one submission in the fixture, then post twice.
            fixture_server.hold = threading.Event()
            fixture_server.received.clear()
            held: list[tuple] = []

            def _held() -> None:
                held.append(
                    monitor_suite._http(
                        instance.port,
                        "POST",
                        "/api/test/submit",
                        token=token,
                        origin=instance.origin,
                        body={
                            "dp": DP1,
                            "book": book,
                            "submit_id": "sub-dom-busy-1",
                            "observe_only": True,
                        },
                    )
                )

            thread = threading.Thread(target=_held, daemon=True)
            thread.start()
            assert fixture_server.received.wait(10)
            busy_status, _headers, busy_payload, _raw = monitor_suite._http(
                instance.port,
                "POST",
                "/api/test/submit",
                token=token,
                origin=instance.origin,
                body={
                    "dp": DP1,
                    "book": book,
                    "submit_id": "sub-dom-busy-2",
                    "observe_only": True,
                },
            )
            assert busy_status == 409
            fixture_server.hold.set()
            thread.join(timeout=20)
            fixture_server.hold = None
            history_four = _get(instance, "/api/test/history", token)[1]
            assert _ok_data(held[0][2])["state"] == "succeeded"
            assert len(_ok_data(history_four)["records"]) == 3

            # A captured honest failure: transport switched off mid-session.
            _write_decide_config(project, enabled=False, base_url=fixture_server.url)
            submit_off = _post(
                instance,
                "/api/test/submit",
                {"dp": DP1, "book": book, "submit_id": "sub-dom-off", "observe_only": True},
                token,
            )[1]
            assert _ok_data(submit_off)["state"] != "succeeded"
            history_off = _get(instance, "/api/test/history", token)[1]

            scenario = {
                "hash": "#boot=t11b-dom-code",
                "responses": {
                    "/api/bootstrap": {
                        "status": 200,
                        "body": {"ok": True, "data": {"page_token": token}, "error": None, "capture_status": None},
                    },
                    "/api/history?scope=production&limit=5&offset=0": {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "data": {
                                "records": [],
                                "total": 0,
                                "limit": 50,
                                "offset": 0,
                                "has_more": False,
                                "stats": {"rows": 0, "unknown_sources": 0},
                                "warnings": [],
                                "filters": {},
                                "filters_withheld": [],
                                "filters_basis": ["no filters were applied"],
                                "redaction": {"enabled": True},
                            },
                            "error": None,
                            "capture_status": None,
                        },
                    },
                    "/api/dps": {"status": 200, "body": dps},
                    "/api/test/history": [
                        {"status": 200, "body": history_empty},
                        {"status": 200, "body": history_empty},
                        {"status": 200, "body": history_one},
                        {"status": 200, "body": history_two},
                        {"status": 200, "body": history_three},
                        {"status": 200, "body": history_four},
                        {"status": 200, "body": history_four},
                        {"status": 200, "body": history_off},
                    ],
                    "/api/test/scaffold": {"status": 200, "body": scaffold_payload},
                    "/api/test/validate": [
                        {"status": 200, "body": validate_ok},
                        {"status": 200, "body": validate_placeholder},
                    ],
                    "/api/test/submit": [
                        {"status": 200, "body": submit_ok},
                        {"status": 200, "body": submit_dup},
                        {"status": 200, "body": submit_retry},
                        {"status": busy_status, "body": busy_payload},
                        {"status": 200, "body": submit_off},
                    ],
                    "/api/test/submissions/:id": {"status": 200, "body": detail},
                    "/api/test/submissions/sub-dom-1": {"status": 200, "body": detail},
                },
                "steps": [
                    {"type": "click", "target": "#tab-playground", "snapshot": "tab"},
                    {"type": "click", "target": "#pg-load", "snapshot": "loaded"},
                    {
                        "type": "setValue",
                        "target": "#dp-select",
                        "value": DP8,
                        "change": True,
                        "snapshot": "p0",
                    },
                    {
                        "type": "setValue",
                        "target": "#dp-select",
                        "value": DP1,
                        "change": True,
                        "snapshot": "dp1",
                    },
                    {"type": "click", "target": "#pg-scaffold", "snapshot": "scaffolded"},
                    {
                        "type": "setValue",
                        "target": "#book-editor",
                        "value": json.dumps(book, ensure_ascii=False),
                    },
                    {"type": "click", "target": "#pg-validate", "snapshot": "validated"},
                    {"type": "click", "target": "#pg-submit", "snapshot": "submitted"},
                    {"type": "click", "target": "#pg-submit", "snapshot": "duplicate"},
                    {"type": "click", "target": "#pg-retry", "snapshot": "retried"},
                    {"type": "click", "target": '[data-testid="pg-history-open"]', "snapshot": "detail"},
                    {
                        "type": "setValue",
                        "target": "#book-editor",
                        "value": json.dumps(scaffold["book"], ensure_ascii=False),
                    },
                    {"type": "click", "target": "#pg-validate", "snapshot": "invalid"},
                    {"type": "click", "target": "#pg-submit", "snapshot": "busy"},
                    {"type": "click", "target": "#pg-submit", "snapshot": "unavailable"},
                ],
            }
            result = _run_dom(tmp_path, scenario)
    finally:
        fixture.stop()

    boot = _snapshot(result, "boot")
    urls = [call["url"] for call in boot["fetchCalls"]]
    assert urls == ["/api/bootstrap", "/api/history?scope=production&limit=5&offset=0"], urls
    assert boot["hash"] == ""

    tab = _snapshot(result, "tab")
    assert tab["playgroundVisible"] is True
    assert [c["url"] for c in tab["fetchCalls"][2:]] == ["/api/dps", "/api/test/history"]
    assert all(c["method"] == "GET" for c in tab["fetchCalls"][2:]), "tab entry is read-only"
    assert "加载" in (tab["pgStatus"] or "")
    assert tab["playgroundForms"] == 0
    assert tab["storage"] == []

    loaded = _snapshot(result, "loaded")
    test_reads = [c for c in loaded["fetchCalls"] if c["url"].startswith("/api/test/")]
    assert [c["url"] for c in test_reads] == ["/api/test/history", "/api/test/history"]
    dps_call = [c for c in loaded["fetchCalls"] if c["url"] == "/api/dps"][0]
    assert dps_call["headers"].get("X-MW-Monitor-Token") == token
    assert token not in dps_call["url"]
    assert "25" in (loaded["pgStatus"] or "")
    assert loaded["storage"] == []
    assert loaded["historyStats"] in (None, ""), "internal read statistics are not normal UI"

    p0 = _snapshot(result, "p0")
    assert "dp8-scope-change" in (p0["pgMeta"] or "")
    assert "P0" in (p0["pgMeta"] or "")
    assert "当前启用" in (p0["pgMeta"] or "")
    assert "false" in (p0["pgMeta"] or "")
    assert "预算 max_state_bytes" in (p0["pgMeta"] or "")
    assert "required" in (p0["pgFields"] or "") and "optional" in (p0["pgFields"] or "")
    assert "scope.requested_paths" in (p0["pgFields"] or "")
    assert "array" in (p0["pgFields"] or "")
    assert "observe_only=true" in (p0["pgMeta"] or "")
    assert p0["pgSubmit"] == "", "selecting a DP must not submit anything"

    scaffolded = _snapshot(result, "scaffolded")
    scaffold_call = [c for c in scaffolded["fetchCalls"] if c["url"] == "/api/test/scaffold"][0]
    assert scaffold_call["method"] == "POST"
    assert scaffold_call["headers"].get("X-MW-Monitor-Token") == token
    assert _json_body(scaffold_call) == {"dp": DP1}
    assert "占位符" in (scaffolded["pgStatus"] or "")
    validate_calls = [c for c in scaffolded["fetchCalls"] if c["url"] == "/api/test/validate"]
    assert validate_calls == [], "generating a skeleton must not validate automatically"

    validated = _snapshot(result, "validated")
    validate_call = [c for c in validated["fetchCalls"] if c["url"] == "/api/test/validate"][-1]
    assert validate_call["headers"].get("X-MW-Monitor-Token") == token
    sent = _json_body(validate_call)
    assert sent["dp"] == DP1 and sent["book"]["decision_point"] == DP1
    assert "通过" in (validated["pgValidate"] or "")
    assert "context_sent" in (validated["pgValidate"] or "")
    assert "false" in (validated["pgValidate"] or "")
    assert "context 原文不发送" in (validated["pgValidate"] or "")
    # dp1 declares no context slot any more: validate lists none (context_sent is false).
    assert "task_excerpt" not in (validated["pgValidate"] or "")
    submit_calls = [c for c in validated["fetchCalls"] if c["url"] == "/api/test/submit"]
    assert submit_calls == [], "validate must not submit"

    submitted = _snapshot(result, "submitted")
    submit_call = [c for c in submitted["fetchCalls"] if c["url"] == "/api/test/submit"][-1]
    assert submit_call["headers"].get("X-MW-Monitor-Token") == token
    submit_body = _json_body(submit_call)
    assert submit_body["observe_only"] is True
    assert submit_body["dp"] == DP1
    assert submit_body["submit_id"].startswith("ui-")
    first_id = submit_body["submit_id"]
    text = submitted["pgSubmit"] or ""
    assert "state=succeeded" in text
    assert "真实模型调用成功" in text
    assert "sub-dom-1" in text
    assert _ok_data(submit_ok)["call_id"] in text
    assert _ok_data(submit_ok)["book_ref"] in text
    assert "triage_type" in text and "coding" in text
    assert "answer_persisted（轮询可读回）：true" in text or "answer_persisted" in text
    assert SECRET not in text and XSS not in text, "the persisted projection is redacted"
    assert submitted["imgCount"] == 0 and submitted["pwned"] is False
    assert "共 1 条" in (submitted["pgHistoryMeta"] or "")

    duplicate = _snapshot(result, "duplicate")
    duplicate_call = [
        c for c in duplicate["fetchCalls"] if c["url"] == "/api/test/submit"
    ][-1]
    assert _json_body(duplicate_call)["submit_id"] == first_id, "the same book reuses the id"
    dup_text = duplicate["pgSubmit"] or ""
    assert "重复提交" in dup_text
    assert "未新增调用" in dup_text
    assert "not-recorded" not in dup_text

    retried = _snapshot(result, "retried")
    retry_call = [c for c in retried["fetchCalls"] if c["url"] == "/api/test/submit"][-1]
    retry_body = _json_body(retry_call)
    assert retry_body["submit_id"] != first_id
    assert retry_body["retry_of"] == first_id
    assert "retry_of=" in (retried["pgSubmitId"] or "")
    assert first_id in (retried["pgSubmitId"] or "")

    detail_snapshot = _snapshot(result, "detail")
    detail_calls = [
        c for c in detail_snapshot["fetchCalls"] if c["url"].startswith("/api/test/submissions/")
    ]
    assert detail_calls and detail_calls[-1]["url"] == "/api/test/submissions/sub-dom-1"
    assert "triage_type" in (detail_snapshot["pgDetail"] or "")
    assert "coding" in (detail_snapshot["pgDetail"] or "")
    assert "来自该 submission 的持久化安全投影" in (detail_snapshot["pgDetail"] or "")
    assert "实际请求 / 实际返回" in (detail_snapshot["pgDetail"] or "")
    assert "request（实际请求）" in (detail_snapshot["pgDetail"] or "")
    assert "response（实际返回）" in (detail_snapshot["pgDetail"] or "")
    assert "/v1/decisions" in (detail_snapshot["pgDetail"] or "")
    assert "http_status" in (detail_snapshot["pgDetail"] or "")
    assert "stored_len" in (detail_snapshot["pgDetail"] or "")
    assert "worker-3" not in (detail_snapshot["pgDetail"] or ""), (
        "the context excerpt is validated but never sent, so it cannot be in the request capture"
    )
    assert SECRET not in (detail_snapshot["pgDetail"] or "")

    invalid = _snapshot(result, "invalid")
    assert "未通过" in (invalid["pgValidate"] or "")
    assert "book-placeholder" in (invalid["pgValidate"] or "")

    busy = _snapshot(result, "busy")
    busy_text = busy["pgSubmit"] or ""
    assert "409" in busy_text
    assert "busy" in busy_text
    assert "未发起模型调用" in busy_text
    assert "真实模型调用成功" not in busy_text

    unavailable = _snapshot(result, "unavailable")
    unavailable_text = unavailable["pgSubmit"] or ""
    assert "未成功" in unavailable_text, unavailable_text
    assert "HTTP 200 不等于成功" in unavailable_text
    assert "真实模型调用成功" not in unavailable_text
    assert "unavailable" in unavailable_text
    assert _ok_data(submit_off)["state"] in unavailable_text

    for snapshot in result["snapshots"]:
        assert snapshot["storage"] == [], "the page token is never written to web storage"
        assert "boom" not in (snapshot["error"] or "")
        for call in snapshot["fetchCalls"]:
            assert call["url"] != "/api/test/submit" or call["method"] == "POST"
            assert token not in call["url"]
            assert "boot=t11b-dom-code" not in call["url"]
