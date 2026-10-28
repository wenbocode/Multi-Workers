"""T10 readable backend: readable policy facts, input material and question overrides.

Behaviour contracts under test (evidence/design-workbench-readable-revision.md,
spec AC-015 REVISED / AC-021..AC-024; card T10-readable-backend):

* the *effective* confidence threshold of one decision is persisted in the
  decision's own recorded facts and ``decision_history`` exposes a readable
  ``policy_result`` (``reason`` / ``selection`` / ``confidence`` /
  ``min_confidence`` / ``disposition`` / ``basis``) on the ``decide`` node. An
  old record without a recorded threshold is explicitly unknown - the reader
  never resolves the *current* config to fill the gap, never calls HTTP 200 an
  API failure, and never lowers the threshold policy;
* the ``input`` node exposes ``material``: only the business state of the
  actually stored book snapshot. The stored capture copy (and its redaction
  marks) stay; nothing widens the known-secret output;
* the four offline cases carry complete native ``questions``; ``scaffold`` /
  ``validate`` / the case expose the default questions and the final
  ``request_preview`` = ``{model, state, questions}`` built by the *same*
  payload builder that the send path uses (no second model request, no model
  call at preview time);
* ``validate(dp, book, questions=None)`` and a submit request may carry
  ``questions``; without them the previous behaviour is unchanged. Question
  overrides are strictly validated (legal type/instructions/criteria, the DP's
  own question mapping, the legal choice set) and are observation-only. dp3
  keeps ``state.handling_options`` as the only candidate source: conflicting
  criteria are refused explicitly, matching ones normalise to the state
  rendering, and the preview equals the bytes actually sent. The typed state
  contract, the 8192B budget and the known-secret gates stay in force.

Everything runs on a synthetic HOME, an isolated ``tmp_path`` control root and a
random-port loopback fixture; no real credential, provider, browser, build,
install, commit or service is touched.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import pathlib
import threading

import pytest

import decide_archive
import decision
import decision_backends
import decision_lifecycle as lifecycle
import decision_monitor
import decision_playground
import decision_points as dpts
import decision_wire as wire

import test_decision_monitor as monitor_suite

DP1 = "dp1-dispatch-type"
DP2 = "dp2-checkpoint-split"
DP3 = "dp3-worker-clarify"
DP25 = "dp25-signoff-conclusion"
CASE_DPS = (DP1, DP2, DP3, DP25)

API_KEY = "sk-t10-backend-fixture-0123456789abcdef"
SECRET = "T10-READABLE-SECRET-0123456789"
HOST = decision_monitor.HOST
PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]

#: Files no test in this card may change (production tree byte guard).
PRODUCTION_TREE = (
    PACKAGE_DIR / "decide_cases" / "dp1.json",
    PACKAGE_DIR / "decide_cases" / "dp2.json",
    PACKAGE_DIR / "decide_cases" / "dp3.json",
    PACKAGE_DIR / "decide_cases" / "dp25.json",
    PACKAGE_DIR / "decide_registry.json",
    PACKAGE_DIR / "decision_dashboard.html",
    PACKAGE_DIR / "decision_dashboard.js",
    PACKAGE_DIR / "decision_dashboard.css",
)

_QUIET: list[str] = []


def _quiet(message: str) -> None:
    _QUIET.append(message)


def _tree() -> dict[str, str]:
    return {
        str(path.relative_to(REPO_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PRODUCTION_TREE
    }


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated HOME + no ambient credential discovery + fresh config cache."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in list(os.environ):
        if name.upper().endswith(decision._CRED_ENV_SUFFIXES) or name in (
            "TIMI_API_KEY",
            "TYPESAFE_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
        ):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        decision_backends, "_auth_json_path", lambda: tmp_path / "no-auth.json"
    )
    dpts.clear_points_config_cache()
    _QUIET.clear()
    before = _tree()
    yield
    dpts.clear_points_config_cache()
    assert _tree() == before, "the production case/asset tree must not change"


# ---------------------------------------------------------------------------
# History fixtures: real writers, isolated control roots
# ---------------------------------------------------------------------------


def _root(tmp_path: pathlib.Path, name: str = "proj") -> pathlib.Path:
    root = tmp_path / name
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    return root


def _meta(key: str = "mw-alpha", task_key: str | None = "dc-t10"):
    return lifecycle.DecisionMeta.create(key, task_key=task_key, initiator_role="pm")


def _store(root: pathlib.Path) -> lifecycle.LifecycleStore:
    return lifecycle.LifecycleStore.production(
        root, redact=wire.SubstringRedactor((SECRET,)), warn=_quiet
    )


def _scope(
    root: pathlib.Path,
    *,
    decision_id: str,
    dp: str,
    key: str | None = "mw-alpha",
    task_key: str | None = "dc-t10",
    redact: object = None,
) -> wire.WireScope:
    return wire.WireScope(
        sink=wire.production_wire_sink(root),
        project_id=wire.project_id_for(root),
        scope_kind="production",
        origin="producer",
        decision_id=decision_id,
        dp=dp,
        key=key,
        task_key=task_key,
        actor_kind="system",
        actor_id="producer",
        redact=redact if redact is not None else wire.SubstringRedactor((SECRET,)),
        warn=_quiet,
    )


def _add_call(root: pathlib.Path, *, decision_id: str, dp: str, **kwargs: object) -> None:
    scope = _scope(root, decision_id=decision_id, dp=dp)
    call = wire.new_call()
    wire.record_attempt_start(
        scope, call, request=b'{"model":"jev-latest"}', url_path="/v1/decisions", model="jev-latest"
    )
    wire.record_attempt_end(
        scope,
        call,
        response=b'{"model":"jev-latest","answers":{}}',
        latency_ms=11,
        http_status=200,
        content_type="application/json",
        usage={"input_tokens": 5, "output_tokens": 3},
    )
    fields = {
        "attempts": 1,
        "wire_attempts": 1,
        "latency_ms": 11,
        "available": True,
        "answers_present": True,
        "confidence": 0.62,
        "confidence_source": "api",
        "transport": "timi-decisions",
        "model": "jev-latest",
    }
    fields.update(kwargs)
    wire.append_event(scope, wire.call_end_event(scope, call, **fields))


def _add_snapshot(
    root: pathlib.Path,
    *,
    decision_id: str,
    dp: str,
    state: dict,
    policy: dict | None = None,
    redact: object = None,
) -> None:
    document = {
        "kind": "input-state",
        "decision_id": decision_id,
        "dp": dp,
        "questions_version": dpts.get_decision_point(dp).questions_version,
        "state_digest": "0123456789abcdef",
        "candidates": {},
        "state": state,
    }
    if policy is not None:
        document["policy"] = policy
    body = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
    scope = _scope(root, decision_id=decision_id, dp=dp, redact=redact)
    wire.append_event(
        scope,
        wire.book_snapshot_event(scope, book=body, book_ref="state-1", book_version="input-memory"),
    )


def _add_decision_end(
    root: pathlib.Path,
    *,
    decision_id: str,
    dp: str,
    status: str,
    escalated_reason: str | None,
    mode: str = "auto",
    intent: str = "decide",
) -> None:
    scope = _scope(root, decision_id=decision_id, dp=dp)
    wire.append_event(
        scope,
        wire.decision_end_event(
            scope,
            status=status,
            escalated_reason=escalated_reason,
            archive="created",
            state_digest="0123456789abcdef",
            questions_version=dpts.get_decision_point(dp).questions_version,
            mode=mode,
            intent=intent,
        ),
    )


def _append_archive(
    root: pathlib.Path,
    *,
    dp: str,
    trigger_id: str,
    policy: dict | None = None,
    acted: bool = False,
    authority: str = "human",
    escalated_reason: str | None = "low-confidence",
    confidence: float | None = 0.62,
    answer: dict | None = None,
) -> str:
    decision_id = f"{dp}:{trigger_id}"
    kwargs: dict[str, object] = {}
    if policy is not None:
        kwargs["policy"] = policy
    decide_archive.append_decide(
        root / ".agenticdoc" / "_autopilot" / "decisions.jsonl",
        dp=dp,
        key="mw-alpha",
        task_key="dc-t10",
        trigger_id=trigger_id,
        state={"task_goal": "readable"},
        questions_version=dpts.get_decision_point(dp).questions_version,
        available=confidence is not None,
        authority=authority,
        answer=answer
        if answer is not None
        else {"triage_type": {"value": "research", "confidence": 0.62}},
        reason=None,
        escalated_reason=escalated_reason,
        acted=acted,
        actual_action=None,
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        attempts=1,
        latency_ms=12,
        confidence=confidence,
        confidence_source="api",
        now="2026-10-23T07:49:40+00:00",
        **kwargs,
    )
    return decision_id


def _record(root: pathlib.Path, decision_id: str):
    import decision_history

    snapshot = decision_history.load_history(root, redact=wire.SubstringRedactor((SECRET,)))
    for record in snapshot.records:
        if record.scope == "production" and record.decision_id == decision_id:
            return record
    raise AssertionError(f"record not found: {decision_id}")


def _nodes(record) -> dict[str, dict]:
    payload = record.as_dict(detail=True)
    workbench = payload["workbench"]
    return {node["id"]: node for node in workbench["nodes"]}


def _all_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# 1. The decide node carries the recorded policy result
# ---------------------------------------------------------------------------


def test_decide_node_exposes_the_recorded_low_confidence_policy_result(tmp_path):
    """The real live-record shape: HTTP 200, confidence .62 < recorded .70."""
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    lifecycle.record_start(store, meta)
    decision_id = _append_archive(
        root,
        dp=DP1,
        trigger_id="live-1",
        policy={"min_confidence": 0.7, "max_questions": 8, "timeout_s": 20},
    )
    _add_call(root, decision_id=decision_id, dp=DP1)
    _add_decision_end(
        root, decision_id=decision_id, dp=DP1, status="escalated", escalated_reason="low-confidence"
    )
    lifecycle.record_consumed(store, meta, decision_id=decision_id, dp=DP1, answer="research")

    nodes = _nodes(_record(root, decision_id))
    decide = nodes["decide"]
    policy_result = decide["detail"]["policy_result"]

    assert decide["status"] == "failed", "the four main states stay a closed set"
    assert policy_result["disposition"] == "not-adopted", (
        "a low-confidence policy refusal is not an API failure"
    )
    assert policy_result["reason"] == "low-confidence"
    assert policy_result["selection"] == "research", (
        "the single answered question is shown as its recorded value"
    )
    assert policy_result["confidence"] == 0.62
    assert policy_result["confidence_source"] == "api"
    assert policy_result["min_confidence"] == 0.7
    basis = " ".join(policy_result["basis"])
    assert "archive.decide.policy.min_confidence" in basis
    assert "archive.decide.confidence" in basis
    assert "current" not in basis

    # The HTTP 200 fact is still preserved (nothing is renamed an API failure).
    attempts = nodes["response"]["detail"]["attempts"]
    assert [attempt["http_status"] for attempt in attempts] == [200]
    assert nodes["request"]["status"] == "observed"


def test_a_snapshot_recorded_threshold_is_used_and_the_observation_is_not_adopted(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    lifecycle.record_start(store, meta)
    decision_id = f"{DP3}:observe-1"
    lifecycle.record_lifecycle(
        store,
        meta,
        stage="consumed",
        decision_id=decision_id,
        dp=DP3,
        answer="c1",
    )
    _add_snapshot(
        root,
        decision_id=decision_id,
        dp=DP3,
        state={"question": "which option?"},
        policy={"min_confidence": 0.75, "max_questions": 8, "timeout_s": 20},
    )
    _add_call(root, decision_id=decision_id, dp=DP3)
    _add_decision_end(
        root,
        decision_id=decision_id,
        dp=DP3,
        status="suggested",
        escalated_reason=None,
        intent="answer",
    )

    policy_result = _nodes(_record(root, decision_id))["decide"]["detail"]["policy_result"]
    assert policy_result["min_confidence"] == 0.75
    assert "ledger.book-snapshot.policy.min_confidence" in " ".join(policy_result["basis"])
    assert policy_result["disposition"] == "suggested"
    assert policy_result["confidence"] == 0.62


def test_an_old_record_without_a_threshold_is_explicitly_unknown(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Never fill a missing historical threshold from the current configuration."""
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    lifecycle.record_start(store, meta)
    decision_id = f"{DP2}:old-1"
    lifecycle.record_consumed(store, meta, decision_id=decision_id, dp=DP2, answer="narrow")
    _add_call(root, decision_id=decision_id, dp=DP2)
    _add_decision_end(
        root, decision_id=decision_id, dp=DP2, status="escalated", escalated_reason="low-confidence"
    )

    def _must_not_resolve(*args: object, **kwargs: object):
        raise AssertionError("the reader must not resolve the current threshold policy")

    monkeypatch.setattr(dpts, "resolve_policy", _must_not_resolve)
    monkeypatch.setattr(dpts, "MIN_CONFIDENCE", 0.01, raising=False)

    policy_result = _nodes(_record(root, decision_id))["decide"]["detail"]["policy_result"]
    assert policy_result["min_confidence"] is None
    assert policy_result["disposition"] == "not-adopted"
    assert any("no threshold recorded" in item for item in policy_result["basis"])
    assert policy_result["confidence"] == 0.62, "the recorded confidence stays readable"


# ---------------------------------------------------------------------------
# 2. The input node material is the stored snapshot business state
# ---------------------------------------------------------------------------


def test_input_material_is_the_stored_snapshot_business_state(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    lifecycle.record_start(store, meta)
    decision_id = f"{DP1}:material-1"
    lifecycle.record_consumed(store, meta, decision_id=decision_id, dp=DP1, answer="coding")
    state = {
        "task_goal": "make the workbench readable",
        "task_requirements": "keep the bounds",
        "task_deliverables": "report.md",
    }
    _add_snapshot(root, decision_id=decision_id, dp=DP1, state=state)

    input_node = _nodes(_record(root, decision_id))["input"]
    assert input_node["detail"]["material"] == state
    assert "ledger.book-snapshot.state" in " ".join(input_node["detail"]["material_basis"])
    # The underlying stored capture copy stays exactly what the writer recorded.
    assert input_node["detail"]["book"]["text"]
    assert input_node["detail"]["book"]["byte_exact"] is True


def test_input_material_never_widens_the_known_secret_output(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    lifecycle.record_start(store, meta)
    decision_id = f"{DP1}:secret-1"
    lifecycle.record_consumed(store, meta, decision_id=decision_id, dp=DP1, answer="coding")
    # The writer stored the text with a redactor that did not know this value;
    # the reader's injected known set is a superset and must omit it.
    _add_snapshot(
        root,
        decision_id=decision_id,
        dp=DP1,
        state={"task_goal": f"goal mentions {SECRET}", "task_deliverables": "report.md"},
        redact=wire.SubstringRedactor(()),
    )

    record = _record(root, decision_id)
    payload = record.as_dict(detail=True)
    assert SECRET not in _all_text(payload), "the known secret must not be echoed"
    assert record.redaction.structural_withheld >= 1
    material = _nodes(record)["input"]["detail"]["material"]
    assert material is not None
    assert "report.md" in _all_text(material), "unaffected business material stays readable"


# ---------------------------------------------------------------------------
# 3. The four offline cases carry complete native questions
# ---------------------------------------------------------------------------


def test_every_case_carries_the_complete_native_questions():
    for dp in CASE_DPS:
        case = decision_monitor.load_case(dp)
        assert case["questions"] == dpts.questions_map(dp), (
            f"{dp}: the case shell must carry the registry's native questions"
        )
        assert "questions" in json.loads(
            (PACKAGE_DIR / "decide_cases" / f"{dp.split('-')[0]}.json").read_text(
                encoding="utf-8"
            )
        )
    # questions are observation-only: the production registry is untouched.
    assert "questions" not in json.loads(
        (PACKAGE_DIR / "decide_registry.json").read_text(encoding="utf-8")
    )


def test_a_case_shell_without_questions_is_refused(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    shipped = json.loads((PACKAGE_DIR / "decide_cases" / "dp1.json").read_text(encoding="utf-8"))
    shipped.pop("questions")
    (cases_dir / "dp1.json").write_text(
        json.dumps(shipped, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(decision_monitor.CaseError) as excinfo:
        decision_monitor.load_case(DP1, cases_dir=cases_dir)
    assert excinfo.value.kind == "case-invalid"


def test_case_questions_that_are_not_the_dp_mapping_are_refused(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    shipped = json.loads((PACKAGE_DIR / "decide_cases" / "dp1.json").read_text(encoding="utf-8"))
    shipped["questions"] = {"not_a_dp_question": {"type": "choice", "instructions": "x"}}
    (cases_dir / "dp1.json").write_text(
        json.dumps(shipped, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(decision_monitor.CaseError) as excinfo:
        decision_monitor.load_case(DP1, cases_dir=cases_dir)
    assert excinfo.value.kind == "case-invalid"
    assert "questions" in str(excinfo.value), "the refusal names the question field"


# ---------------------------------------------------------------------------
# Loopback fixture: the real timi backend posts here
# ---------------------------------------------------------------------------


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    server_version = "t10-fixture"
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
                "body": raw,
            }
        )
        payload = json.loads(raw.decode("utf-8"))
        questions = payload.get("questions") if isinstance(payload.get("questions"), dict) else {}
        answers: dict[str, object] = {}
        for qid, spec in questions.items():
            spec = spec if isinstance(spec, dict) else {}
            if spec.get("type") != "choice":
                continue
            criteria = spec.get("criteria") if isinstance(spec.get("criteria"), dict) else {}
            answers[str(qid)] = {
                "type": "choice",
                "choice": next(iter(criteria), None),
                "confidence": 0.9,
            }
        body = json.dumps({"model": payload.get("model"), "answers": answers}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


class _FixtureServer:
    def __init__(self) -> None:
        self.requests: list[dict] = []
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
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index]["body"].decode("utf-8"))


def _make_project(tmp_path: pathlib.Path, fixture: _FixtureServer, name: str = "proj"):
    project = tmp_path / name
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    # The shipped case books carry ``path:line`` evidence relative to the repo
    # root. ``check_book`` anchors that root at the nearest ``.git``, so a
    # hermetic project copy is created here: the three evidence anchors (never
    # the whole repository) plus an empty ``.git`` marker that pins the root.
    (project / ".git").mkdir()
    anchors = (
        "scripts/build_decide_cases.py",
        "decision_book.py",
        "decide_registry.json",
    )
    for relative in anchors:
        source = PACKAGE_DIR / relative
        target = project / "packages" / "multi-workers" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    config = {
        "enabled": True,
        "transport": "timi-decisions",
        "model": "jev-latest",
        "timeout_s": 5,
        "max_retries": 0,
        "base_url": fixture.url,
        "api_key": API_KEY,
    }
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return project


def _playground_factory():
    def factory(control_root: pathlib.Path) -> object:
        return decision_playground.DecisionPlayground(control_root, warn=_quiet)

    return factory


class _Live:
    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.tmp_path = tmp_path
        self.fixture = _FixtureServer().start()
        self.project = _make_project(tmp_path, self.fixture)
        self.deps = decision_monitor.MonitorDeps(
            redactor=wire.SubstringRedactor((API_KEY, SECRET)),
            playground_factory=_playground_factory(),
        )

    def __enter__(self):
        self._context = monitor_suite._running(self.project, deps=self.deps)
        self.instance = self._context.__enter__()
        self.token = monitor_suite._page_token(self.instance)
        return self

    def __exit__(self, *exc_info):
        self._context.__exit__(*exc_info)
        self.fixture.stop()


def _post(live: _Live, path: str, body: dict) -> tuple[int, dict]:
    status, _headers, payload, _raw = monitor_suite._http(
        live.instance.port, "POST", path, token=live.token, origin=live.instance.origin, body=body
    )
    assert payload is not None, path
    return status, payload


def _get(live: _Live, path: str) -> tuple[int, dict]:
    status, _headers, payload, _raw = monitor_suite._http(
        live.instance.port, "GET", path, token=live.token
    )
    assert payload is not None, path
    return status, payload


def _data(payload: dict) -> dict:
    assert payload["ok"] is True, payload
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _case(live: _Live, dp: str) -> dict:
    status, payload = _get(live, f"/api/test/cases?dp={dp}")
    assert status == 200, payload
    return _data(payload)["cases"][0]


# ---------------------------------------------------------------------------
# 4. scaffold / validate expose the default questions and the final preview
# ---------------------------------------------------------------------------


def test_scaffold_exposes_the_default_questions(tmp_path):
    with _Live(tmp_path) as live:
        status, payload = _post(live, "/api/test/scaffold", {"dp": DP1})
        assert status == 200
        scaffold = _data(payload)
        assert scaffold["questions"] == dpts.questions_map(DP1)
        assert scaffold["questions_version"] == dpts.get_decision_point(DP1).questions_version
        assert live.fixture.calls == 0, "scaffold makes no model request"


def test_validate_previews_the_exact_payload_without_calling_the_model(tmp_path):
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        status, payload = _post(
            live,
            "/api/test/validate",
            {"dp": DP1, "book": case["book"], "questions": case["questions"]},
        )
        assert status == 200, payload
        data = _data(payload)
        assert data["ok"] is True, data["issues"]
        preview = data["request_preview"]
        assert set(preview) == {"model", "state", "questions"}
        assert preview["model"] == "jev-latest"
        assert set(preview["state"]) == {
            "task_goal",
            "task_requirements",
            "task_deliverables",
        }, "the preview is the real model projection, not the book wrapper"
        assert preview["questions"]["triage_type"]["type"] == "choice"
        assert preview["questions"]["triage_type"]["criteria"] == (
            dpts.questions_map(DP1)["triage_type"]["labels"]
        )
        assert live.fixture.calls == 0, "a preview never calls the model"


def test_validate_without_questions_keeps_the_previous_behaviour(tmp_path):
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        status, payload = _post(live, "/api/test/validate", {"dp": DP1, "book": case["book"]})
        assert status == 200
        data = _data(payload)
        assert data["ok"] is True
        assert data["request_preview"] is not None
        assert data["questions"] == dpts.questions_map(DP1)


# ---------------------------------------------------------------------------
# 5. Edited questions reach the real HTTP body; preview == sent bytes
# ---------------------------------------------------------------------------


def test_edited_instructions_reach_the_http_body_and_match_the_preview(tmp_path):
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        edited = json.loads(json.dumps(case["questions"], ensure_ascii=False))
        edited["triage_type"]["instructions"] = "T10 edited question: which worker type?"

        status, payload = _post(
            live,
            "/api/test/validate",
            {"dp": DP1, "book": case["book"], "questions": edited},
        )
        assert status == 200
        preview = _data(payload)["request_preview"]
        assert preview["questions"]["triage_type"]["instructions"] == (
            "T10 edited question: which worker type?"
        )

        status, payload = _post(
            live,
            "/api/test/submit",
            {
                "dp": DP1,
                "book": case["book"],
                "questions": edited,
                "submit_id": "t10-edit-1",
                "observe_only": True,
            },
        )
        assert status == 200, payload
        result = _data(payload)
        assert result["state"] == "succeeded", result
        assert live.fixture.calls == 1

        sent = live.fixture.body()
        assert sent["questions"]["triage_type"]["instructions"] == (
            "T10 edited question: which worker type?"
        )
        assert sent["state"] == preview["state"]
        assert sent["questions"] == preview["questions"]
        assert sent["model"] == preview["model"]

        # The observation's own persisted snapshot carries the applied threshold
        # (there is no archive row on this path), so a reader of that ledger can
        # report the exact policy fact instead of the current config.
        test_root = live.project / decision_playground.TEST_ROOT_RELATIVE_PATH
        rows = wire.read_events(wire.test_wire_sink(test_root)).events
        snapshot_rows = [row for row in rows if row.get("kind") == "book-snapshot"]
        assert snapshot_rows, "the observation persisted its input snapshot"
        document = json.loads(snapshot_rows[-1]["book"]["text"])
        assert document["state"] == preview["state"]
        assert document["policy"]["min_confidence"] == 0.7, (
            "the effective threshold is a persisted decision fact"
        )
        assert document["policy"]["min_confidence"] != 0.0


def test_submit_without_questions_keeps_the_registry_questions(tmp_path):
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        status, payload = _post(
            live,
            "/api/test/submit",
            {
                "dp": DP1,
                "book": case["book"],
                "submit_id": "t10-plain-1",
                "observe_only": True,
            },
        )
        assert status == 200, payload
        assert _data(payload)["state"] == "succeeded"
        sent = live.fixture.body()
        assert sent["questions"]["triage_type"]["instructions"] == (
            dpts.questions_map(DP1)["triage_type"]["instructions"]
        )


# ---------------------------------------------------------------------------
# 6. dp3: state.handling_options is the only candidate source
# ---------------------------------------------------------------------------


def _dp3_edited_case(live: _Live) -> tuple[dict, dict]:
    case = _case(live, DP3)
    book = json.loads(json.dumps(case["book"], ensure_ascii=False))
    book["state"]["handling_options"] = [
        {
            "id": "c1",
            "label": "Edited candidate one",
            "description": "first edited candidate explanation",
        },
        {
            "id": "c2",
            "label": "Edited candidate two",
            "description": "second edited candidate explanation",
        },
    ]
    return case, book


def test_dp3_stale_criteria_are_refused_before_any_send(tmp_path):
    with _Live(tmp_path) as live:
        case, book = _dp3_edited_case(live)
        stale = dict(case["questions"])
        stale["handling"] = {
            **stale["handling"],
            "criteria": {
                "c1": "展示已有 signoff 记录（只读）",
                "c2": "不展示，统一标未记录",
            },
        }
        status, payload = _post(
            live, "/api/test/validate", {"dp": DP3, "book": book, "questions": stale}
        )
        assert status == 200
        data = _data(payload)
        assert data["ok"] is False
        assert any("question-conflict" == issue["code"] for issue in data["issues"])
        assert data["request_preview"] is None

        status, payload = _post(
            live,
            "/api/test/submit",
            {
                "dp": DP3,
                "book": book,
                "questions": stale,
                "submit_id": "t10-dp3-stale",
                "observe_only": True,
            },
        )
        assert status == 200, payload
        assert _data(payload)["state"] == "rejected"
        assert live.fixture.calls == 0, "a question conflict is refused before the transport"


def test_dp3_matching_criteria_normalise_to_the_state_candidates(tmp_path):
    with _Live(tmp_path) as live:
        case, book = _dp3_edited_case(live)
        matching = dict(case["questions"])
        matching["handling"] = {
            **matching["handling"],
            "criteria": {"c1": "Edited candidate one", "c2": "Edited candidate two"},
        }
        status, payload = _post(
            live, "/api/test/validate", {"dp": DP3, "book": book, "questions": matching}
        )
        assert status == 200
        preview = _data(payload)["request_preview"]
        assert preview["questions"]["handling"]["criteria"] == {
            "c1": "Edited candidate one",
            "c2": "Edited candidate two",
        }

        status, payload = _post(
            live,
            "/api/test/submit",
            {
                "dp": DP3,
                "book": book,
                "questions": matching,
                "submit_id": "t10-dp3-ok",
                "observe_only": True,
            },
        )
        assert status == 200, payload
        assert _data(payload)["state"] == "succeeded"
        sent = live.fixture.body()
        assert sent["questions"]["handling"]["criteria"] == {
            "c1": "Edited candidate one",
            "c2": "Edited candidate two",
        }
        assert sent["questions"] == preview["questions"]


def test_dp3_state_labels_alone_regenerate_the_sent_criteria(tmp_path):
    with _Live(tmp_path) as live:
        _case, book = _dp3_edited_case(live)
        status, payload = _post(live, "/api/test/validate", {"dp": DP3, "book": book})
        assert status == 200
        preview = _data(payload)["request_preview"]
        assert preview["questions"]["handling"]["criteria"] == {
            "c1": "Edited candidate one",
            "c2": "Edited candidate two",
        }


# ---------------------------------------------------------------------------
# 7. The strict question gate; the material/budget/secret gates stay in force
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "questions, expected_path",
    [
        ({"wrong_qid": {"type": "choice", "instructions": "x"}}, "wrong_qid"),
        ({"triage_type": {"type": "score", "instructions": "x"}}, "triage_type.type"),
        ({"triage_type": {"type": "choice", "instructions": "   "}}, "triage_type.instructions"),
        (
            {"triage_type": {"type": "choice", "instructions": "x", "criteria": {"a": "b"}}},
            "triage_type.criteria",
        ),
    ],
)
def test_illegal_question_overrides_are_refused_without_a_send(
    tmp_path, questions: dict, expected_path: str
):
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        status, payload = _post(
            live, "/api/test/validate", {"dp": DP1, "book": case["book"], "questions": questions}
        )
        assert status == 200
        data = _data(payload)
        assert data["ok"] is False
        assert any(issue["path"].startswith(expected_path) for issue in data["issues"]), data[
            "issues"
        ]

        status, payload = _post(
            live,
            "/api/test/submit",
            {
                "dp": DP1,
                "book": case["book"],
                "questions": questions,
                "submit_id": "t10-bad-question",
                "observe_only": True,
            },
        )
        assert status == 200, payload
        assert _data(payload)["state"] == "rejected"
        assert live.fixture.calls == 0


def test_a_known_secret_inside_edited_questions_is_refused_before_the_send(tmp_path):
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        polluted = json.loads(json.dumps(case["questions"], ensure_ascii=False))
        polluted["triage_type"]["instructions"] = f"leak {API_KEY} here"
        status, payload = _post(
            live, "/api/test/validate", {"dp": DP1, "book": case["book"], "questions": polluted}
        )
        assert status == 200
        data = _data(payload)
        assert data["ok"] is False
        assert any("question-secret" == issue["code"] for issue in data["issues"])
        assert API_KEY not in _all_text(data), "the secret is never echoed back"
        assert live.fixture.calls == 0


def test_an_execution_key_inside_the_questions_is_refused_at_the_boundary(tmp_path):
    """The monitor is the HTTP boundary: a forbidden key inside questions is a 400."""
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        polluted = json.loads(json.dumps(case["questions"], ensure_ascii=False))
        polluted["triage_type"]["authority"] = "binding"
        status, payload = _post(
            live, "/api/test/validate", {"dp": DP1, "book": case["book"], "questions": polluted}
        )
        assert status == 400, payload
        assert payload["error"]["code"] == "forbidden-field"
        status, payload = _post(
            live,
            "/api/test/submit",
            {
                "dp": DP1,
                "book": case["book"],
                "questions": polluted,
                "submit_id": "t10-forbidden-question",
                "observe_only": True,
            },
        )
        assert status == 400, payload
        assert live.fixture.calls == 0


def test_the_typed_state_and_budget_gates_still_apply_with_question_overrides(tmp_path):
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        broken = json.loads(json.dumps(case["book"], ensure_ascii=False))
        broken["state"].pop("task_deliverables")
        status, payload = _post(
            live,
            "/api/test/validate",
            {"dp": DP1, "book": broken, "questions": case["questions"]},
        )
        assert status == 200
        data = _data(payload)
        assert data["ok"] is False
        assert data["request_preview"] is None

        oversized = json.loads(json.dumps(case["book"], ensure_ascii=False))
        oversized["state"]["task_goal"] = "x" * (dpts.MAX_STATE_BYTES + 10)
        status, payload = _post(
            live,
            "/api/test/validate",
            {"dp": DP1, "book": oversized, "questions": case["questions"]},
        )
        assert status == 200
        data = _data(payload)
        assert data["ok"] is False
        assert any(issue["code"] == "book-budget" for issue in data["issues"])
        assert live.fixture.calls == 0


def test_the_test_scope_never_touches_the_production_archive(tmp_path):
    """The whole submit flow writes only the isolated test ledger."""
    production_wire = PACKAGE_DIR.parent.parent / ".agenticdoc" / "_autopilot" / "decisions-wire.jsonl"
    before = (
        hashlib.sha256(production_wire.read_bytes()).hexdigest()
        if production_wire.exists()
        else None
    )
    with _Live(tmp_path) as live:
        case = _case(live, DP1)
        status, payload = _post(
            live,
            "/api/test/submit",
            {
                "dp": DP1,
                "book": case["book"],
                "submit_id": "t10-isolated",
                "observe_only": True,
            },
        )
        assert status == 200
        assert _data(payload)["state"] == "succeeded"
        assert not (live.project / ".agenticdoc" / "_autopilot" / "decisions.jsonl").exists()
        assert (live.project / ".mw" / "decide-test" / "evidence.jsonl").exists()
    after = (
        hashlib.sha256(production_wire.read_bytes()).hexdigest()
        if production_wire.exists()
        else None
    )
    assert after == before
