"""test_decision_cli_config_snapshot.py: T05g, one config snapshot per command.

Review N2 (T05e, P3/边界): ``mw decide run --book`` / ``mw decide ask --book``
resolved ``.mw/decide.json`` twice: once inside ``mw._book_secret_redactor`` for
the book gate's known-secret set and once for the client that resolves the
Authorization value and sends the request. A credential rotated between those
two reads was absent from the gate set while the client sent with it, so a book
carrying the *live* credential passed the gate and reached the transport.

The contract pinned here (card T05g): both sides of one command share the same
``decision.DecisionConfig`` snapshot, and a rotation is picked up by the *next*
command. The tests are behavioural:

* a spy replaces ``DecisionConfig.from_project``: the first read returns cfg A,
  every later read returns cfg B (the rotation), so a second read is visible;
* a spy on ``decision.known_secret_redactor`` records the cfg the gate used;
* ``decision.FakeBackend`` records the cfg the transport actually sent with.

Nothing here reads a real credential or opens a socket: env credential names are
removed, ``decision_backends._auth_json_path`` points at a tmp path *before* any
test body runs, and only synthetic values are used.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

DP3 = "dp3-worker-clarify"
MW_PY = pathlib.Path(__file__).resolve().parent / "mw.py"

#: The value ``.mw/decide.json`` carries when the command starts (snapshot A).
SNAPSHOT_SECRET = "snap-cfg-a-0123456789abcdef"
#: The value rotated in *between* the two reads the old code performed (cfg B).
ROTATED_SECRET = "snap-cfg-b-0123456789abcde"
#: Never matches ``sk-``/``Bearer``/the ambient env heuristics.
UNKNOWN_SECRET = "plain-material-0123456789abcdef"

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    """No ambient credential and no real ``~/.pi/agent/auth.json``, ever."""
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        decision_backends, "_auth_json_path", lambda: tmp_path / "no-auth.json"
    )
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Fixtures: repo-like project, legal dp3 book, CLI argv namespaces
# ---------------------------------------------------------------------------


def _write_decide(root: pathlib.Path, **fields) -> pathlib.Path:
    path = root / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": True, **fields}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _enable_all(root: pathlib.Path) -> None:
    path = root / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "points": {
                    point.id: {"tier": point.tier, "enabled": True, "mode": "auto"}
                    for point in dpts.DP_REGISTRY
                },
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    dpts.clear_points_config_cache()


def _project(tmp_path: pathlib.Path, **decide_fields) -> pathlib.Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "notes.txt").write_text(
        "line1\nline2\nline3\nline4\nline5\n", encoding="utf-8", newline="\n"
    )
    _write_decide(root, **decide_fields)
    _enable_all(root)
    return root


def _dp3_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
        "key": "k-t05g",
        "phase": "EXECUTE",
        "task_type": "coding",
        "risk": "mid",
        "risk_source": "pm-label",
        "authority_tier": "P2",
        "task_summary": "worker asks which file holds the decide-points table",
        "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
        "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
    }
    state.update(overrides)
    return state


def _book(dp_id: str, state: dict) -> dict:
    evidence = {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "notes": {"evidence": evidence},
    }


def _write_book(root: pathlib.Path, book: dict, name: str = "book.json") -> pathlib.Path:
    path = root / name
    path.write_text(
        json.dumps(book, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _args(action: str, root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {"subcommand": "decide", "decide_action": action, "project": str(root), "json": False}
    base.update(kw)
    return argparse.Namespace(**base)


def _run_args(root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {"json": True, "request_file": None, "dp": None, "book": None}
    base.update(kw)
    return _args("run", root, **base)


def _ask_args(root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "state": None,
        "state_file": None,
        "book": None,
        "noul": [],
        "noul_criteria": [],
        "choice": [],
        "score": [],
        "model": None,
        "json": False,
    }
    base.update(kw)
    return _args("ask", root, **base)


def _book_args(root: pathlib.Path, action: str, **kw) -> argparse.Namespace:
    return _args("book", root, book_action=action, **kw)


def _ok(answers: dict) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers=answers,
        latency_ms=2,
        detail="",
    )


def _dp3_answers() -> dict:
    return {
        "answer_kind": {"value": "fact", "confidence": 0.9},
        "answerable": {"value": 0.9},
        "candidate": {"value": "c1", "confidence": 0.9},
    }


# ---------------------------------------------------------------------------
# Observation seams: the rotation spy, the gate-cfg spy, the fake transport
# ---------------------------------------------------------------------------


class _RotationSpy:
    """``DecisionConfig.from_project`` stand-in: cfg A first, cfg B afterwards.

    Recording ``reads`` makes a second resolution of the same command visible:
    any code path that read the config again would send with cfg B while the
    gate kept cfg A (the N2 window).
    """

    def __init__(self, first: decision.DecisionConfig, later: decision.DecisionConfig) -> None:
        self.first = first
        self.later = later
        self.reads: list[decision.DecisionConfig] = []

    def __call__(self, project_root: object = None, *args, **kwargs):
        cfg = self.first if not self.reads else self.later
        self.reads.append(cfg)
        return cfg, None


def _install_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_RotationSpy, list]:
    """Rotate after the first config read; record the cfg the gate was built on."""
    spy = _RotationSpy(
        decision.DecisionConfig(enabled=True, extras={"api_key": SNAPSHOT_SECRET}),
        decision.DecisionConfig(enabled=True, extras={"api_key": ROTATED_SECRET}),
    )
    monkeypatch.setattr(decision.DecisionConfig, "from_project", spy)
    gate_cfgs: list = []
    original = decision.known_secret_redactor

    def gate_spy(cfg: object = None, **kwargs):
        gate_cfgs.append(cfg)
        return original(cfg, **kwargs)

    monkeypatch.setattr(decision, "known_secret_redactor", gate_spy)
    return spy, gate_cfgs


def _install_backend(monkeypatch: pytest.MonkeyPatch, answers: dict) -> decision.FakeBackend:
    """A fake backend through the client's documented factory seam."""
    fake = decision.FakeBackend([_ok(answers)])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: fake)
    return fake


def _authorization(cfg: object) -> str | None:
    """The Authorization value this cfg would send (cfg.api_key / extras)."""
    return decision_backends._cfg_get(cfg, "api_key")


def _evidence_files(root: pathlib.Path) -> list[pathlib.Path]:
    base = root / ".agenticdoc"
    if not base.exists():
        return []
    return [path for path in base.rglob("*") if path.is_file()]


def _evidence_text(root: pathlib.Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in _evidence_files(root)
    )


def _evidence_rows(root: pathlib.Path) -> list[dict]:
    rows: list[dict] = []
    for path in _evidence_files(root):
        if path.suffix != ".jsonl":
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _assert_zero_send(root: pathlib.Path, fake: decision.FakeBackend, secret: str) -> None:
    """The refusal happened before the transport and left no trace of the value."""
    assert fake.calls == [], "the book gate let material reach the transport"
    assert not (root / books.RECEIPTS_RELATIVE_PATH).exists()
    assert not (root / ".agenticdoc" / "_autopilot" / "decisions.jsonl").exists()
    rows = _evidence_rows(root)
    assert [row for row in rows if row.get("kind") in ("attempt-start", "book-snapshot")] == []
    assert secret not in _evidence_text(root)


# ---------------------------------------------------------------------------
# N2: the gate set and the sent Authorization value come from one snapshot
# ---------------------------------------------------------------------------


def test_run_book_gate_and_transport_use_one_config_snapshot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`run --book`: the client must send with the cfg the gate was built on."""
    project = _project(tmp_path)
    spy, gate_cfgs = _install_rotation(monkeypatch)
    fake = _install_backend(monkeypatch, _dp3_answers())
    path = _write_book(project, _book(DP3, _dp3_state(task_summary=f"rotated in {ROTATED_SECRET}")))

    rc = mw.cmd_decide(_run_args(project, book=str(path)))
    captured = capsys.readouterr()

    assert rc == 0, captured.err
    assert len(spy.reads) >= 2, "the rotation spy never rotated: the command read once"
    assert gate_cfgs, "the book gate was not built on an explicit config snapshot"
    assert fake.calls, "a legal book was not sent"
    gate_cfg = gate_cfgs[0]
    sent_cfg = fake.calls[0]["cfg"]
    assert sent_cfg is gate_cfg, (
        "the book gate and the transport used two different config reads "
        f"(gate={_authorization(gate_cfg)!r}, sent={_authorization(sent_cfg)!r})"
    )
    assert _authorization(sent_cfg) == SNAPSHOT_SECRET
    assert SNAPSHOT_SECRET not in captured.out and SNAPSHOT_SECRET not in captured.err
    assert ROTATED_SECRET not in captured.out and ROTATED_SECRET not in captured.err


def test_ask_book_gate_and_transport_use_one_config_snapshot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`ask --book`: same single-snapshot obligation on the human face."""
    project = _project(tmp_path)
    spy, gate_cfgs = _install_rotation(monkeypatch)
    fake = _install_backend(monkeypatch, {"urgent": {"value": 0.9}})
    path = _write_book(project, _book(DP3, _dp3_state(task_summary=f"rotated in {ROTATED_SECRET}")))

    rc = mw.cmd_decide(
        _ask_args(project, book=str(path), noul=["urgent=is this urgent"], json=True)
    )
    captured = capsys.readouterr()

    assert rc == 0, captured.err
    assert len(spy.reads) >= 2, "the rotation spy never rotated: the command read once"
    assert gate_cfgs and fake.calls
    gate_cfg = gate_cfgs[0]
    sent_cfg = fake.calls[0]["cfg"]
    assert sent_cfg is gate_cfg, (
        "the book gate and the ask transport used two different config reads "
        f"(gate={_authorization(gate_cfg)!r}, sent={_authorization(sent_cfg)!r})"
    )
    assert _authorization(sent_cfg) == SNAPSHOT_SECRET
    assert SNAPSHOT_SECRET not in captured.out and SNAPSHOT_SECRET not in captured.err


def test_run_book_refuses_the_snapshot_secret_with_zero_send(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The snapshot's own credential is refused before the transport (0 send)."""
    project = _project(tmp_path, api_key=SNAPSHOT_SECRET)
    fake = _install_backend(monkeypatch, _dp3_answers())
    path = _write_book(
        project, _book(DP3, _dp3_state(task_summary=f"use {SNAPSHOT_SECRET}"))
    )

    rc = mw.cmd_decide(_run_args(project, book=str(path)))
    captured = capsys.readouterr()

    assert rc == 2
    assert "book-secret" in captured.err
    assert SNAPSHOT_SECRET not in captured.err and SNAPSHOT_SECRET not in captured.out
    _assert_zero_send(project, fake, SNAPSHOT_SECRET)


def test_ask_book_refuses_the_snapshot_secret_with_zero_send(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path, api_key=SNAPSHOT_SECRET)
    fake = _install_backend(monkeypatch, {"urgent": {"value": 0.9}})
    path = _write_book(
        project, _book(DP3, _dp3_state(task_summary=f"use {SNAPSHOT_SECRET}"))
    )

    rc = mw.cmd_decide(_ask_args(project, book=str(path), noul=["urgent=is this urgent"]))
    captured = capsys.readouterr()

    assert rc == 2
    assert SNAPSHOT_SECRET not in captured.err and SNAPSHOT_SECRET not in captured.out
    _assert_zero_send(project, fake, SNAPSHOT_SECRET)


# ---------------------------------------------------------------------------
# book check and the per-command refresh
# ---------------------------------------------------------------------------


def test_book_check_gate_uses_the_command_snapshot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`book check` gates on the first read, one snapshot for the whole command."""
    project = _project(tmp_path)
    spy, gate_cfgs = _install_rotation(monkeypatch)
    path = _write_book(
        project, _book(DP3, _dp3_state(task_summary=f"use {SNAPSHOT_SECRET}"))
    )

    rc = mw.cmd_decide(_book_args(project, "check", file=str(path), json=True))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 2
    assert payload["issues"][0]["code"] == "book-secret"
    assert SNAPSHOT_SECRET not in captured.out and SNAPSHOT_SECRET not in captured.err
    assert len(gate_cfgs) == 1, "the checker built more than one known-secret set"
    assert gate_cfgs[0] is spy.reads[0], "the gate set came from a later config read"


def test_a_new_command_resolves_the_rotated_config(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Rotation is not a one-shot: the next command gates on the new value."""
    project = _project(tmp_path, api_key=SNAPSHOT_SECRET)
    fake = _install_backend(monkeypatch, _dp3_answers())
    before = _write_book(
        project, _book(DP3, _dp3_state(task_summary=f"use {SNAPSHOT_SECRET}")), "before.json"
    )
    assert mw.cmd_decide(_run_args(project, book=str(before))) == 2
    capsys.readouterr()

    _write_decide(project, api_key=ROTATED_SECRET)
    after = _write_book(
        project, _book(DP3, _dp3_state(task_summary=f"use {ROTATED_SECRET}")), "after.json"
    )
    rc = mw.cmd_decide(_run_args(project, book=str(after)))
    captured = capsys.readouterr()

    assert rc == 2
    assert "book-secret" in captured.err
    assert SNAPSHOT_SECRET not in captured.err and ROTATED_SECRET not in captured.err
    _assert_zero_send(project, fake, ROTATED_SECRET)


def test_a_raising_config_read_still_gates_and_sends_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A broken read must not skip the gate nor reach the transport."""

    def explode(project_root: object = None, *args, **kwargs):
        raise RuntimeError("simulated unreadable decide.json")

    project = _project(tmp_path)
    monkeypatch.setattr(decision.DecisionConfig, "from_project", explode)
    fake = _install_backend(monkeypatch, _dp3_answers())
    path = _write_book(
        project, _book(DP3, _dp3_state(task_summary="Bearer bearer-material-0123456789"))
    )

    check_rc = mw.cmd_decide(_book_args(project, "check", file=str(path), json=True))
    check_out = capsys.readouterr()
    assert check_rc == 2, "the pattern-only gate must still refuse a Bearer value"
    assert json.loads(check_out.out)["issues"][0]["code"] == "book-secret"

    legal = _write_book(project, _book(DP3, _dp3_state()), "legal.json")
    run_rc = mw.cmd_decide(_run_args(project, book=str(legal)))
    run_out = capsys.readouterr()
    assert run_rc == 0, run_out.err
    payload = json.loads(run_out.out)
    assert payload["available"] is False
    assert payload["escalated_reason"] == "unavailable"
    assert fake.calls == [], "a disabled fallback config still reached the transport"
    assert "Traceback" not in run_out.err


# ---------------------------------------------------------------------------
# Independent cold start: real CLI, isolated HOME/auth/config
# ---------------------------------------------------------------------------


def _run_child(argv: list[str], *, home: pathlib.Path) -> subprocess.CompletedProcess:
    """Child interpreter with no ambient credential and an isolated HOME.

    ``HOME``/``USERPROFILE`` redirection means the production auth.json resolver
    can only reach the synthetic fixture (never the developer's real file).
    """
    env = {name: value for name, value in os.environ.items() if name not in CRED_ENV_VARS}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, "-X", "utf8", *argv],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=env,
    )


def test_cold_start_cli_re_resolves_the_config_for_each_command(
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "home"
    (home / ".pi" / "agent").mkdir(parents=True)
    project = _project(tmp_path, api_key=SNAPSHOT_SECRET)
    base = [str(MW_PY), "decide"]

    first = _write_book(
        project, _book(DP3, _dp3_state(task_summary=f"use {SNAPSHOT_SECRET}")), "first.json"
    )
    proc = _run_child(
        base + ["book", "check", str(first), "--project", str(project), "--json"], home=home
    )
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert json.loads(proc.stdout)["issues"][0]["code"] == "book-secret"
    assert SNAPSHOT_SECRET not in proc.stdout and SNAPSHOT_SECRET not in proc.stderr

    # The next process must resolve the rotated value (a new command, a new read).
    _write_decide(project, api_key=ROTATED_SECRET)
    second = _write_book(
        project, _book(DP3, _dp3_state(task_summary=f"use {ROTATED_SECRET}")), "second.json"
    )
    rotated = _run_child(
        base + ["book", "check", str(second), "--project", str(project), "--json"], home=home
    )
    assert rotated.returncode == 2, (rotated.stdout, rotated.stderr)
    assert json.loads(rotated.stdout)["issues"][0]["code"] == "book-secret"
    assert ROTATED_SECRET not in rotated.stdout and ROTATED_SECRET not in rotated.stderr

    # `run --book` through the real argparse wiring: refused before any send.
    refusal = _run_child(
        base + ["run", "--project", str(project), "--book", str(second), "--json"], home=home
    )
    assert refusal.returncode == 2, (refusal.stdout, refusal.stderr)
    assert "nothing was sent (zero HTTP)" in refusal.stderr
    assert ROTATED_SECRET not in refusal.stdout and ROTATED_SECRET not in refusal.stderr
    assert not (project / books.RECEIPTS_RELATIVE_PATH).exists()

    # Control: material that is not a known secret still passes.
    legal = _write_book(
        project, _book(DP3, _dp3_state(task_summary=f"plain {UNKNOWN_SECRET}")), "legal.json"
    )
    passed = _run_child(
        base + ["book", "check", str(legal), "--project", str(project), "--json"], home=home
    )
    assert passed.returncode == 0, (passed.stdout, passed.stderr)
