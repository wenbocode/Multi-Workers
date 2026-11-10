"""T23: production CLI/book/stdin/replay entry validation (eight active entries).

Hermetic: temporary project, fake decision client (no provider, no network) and
real production lifecycle writer. The suite proves the request contract, the
explicit refusal of the 25 retired ids on every request face, the replay path,
and the null-vs-empty task snapshot distinction. It never executes a gate,
sign-off or other business action.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout

import pytest

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))  # noqa: E402

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision  # noqa: E402
import decision_book  # noqa: E402
import decision_lifecycle  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_signoff_result  # noqa: E402
import decision_wire  # noqa: E402
import mw  # noqa: E402
from autopilot import closure as _autopilot_closure  # noqa: E402
from autopilot import config as _autopilot_config  # noqa: E402
from autopilot import conductor as _autopilot_conductor  # noqa: E402
from autopilot import gates as _autopilot_gates  # noqa: E402
from autopilot import roadmap as _autopilot_roadmap  # noqa: E402

PREPARED_AT = "2026-11-08T10:00:00+00:00"
TASK_AT = "2026-11-08T09:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixtures: legal material/preparation per active entry (shapes mirror the
# protocol registry; this file owns its own copies).
# ---------------------------------------------------------------------------


def _business_question_id(dp_id: str) -> str:
    return str(dpts.get_decision_point(dp_id).questions[0]["id"])


def _auto_candidates() -> list[dict]:
    return [
        {
            "id": candidate_id,
            "label": f"candidate {candidate_id}",
            "description": f"prepared handling {candidate_id}",
            "consequence": f"what follows from {candidate_id}",
            "risk": "bounded by the existing write face",
            "conditions": "only inside the already granted budget",
        }
        for candidate_id in ("patch-now", "ask-user", "rollback")
    ]


def _material(dp_id: str) -> dict:
    base = {
        "dp-w-type": {
            "task_goal": "ship the protocol entry",
            "task_requirements": "eight entries only",
            "task_deliverables": "registry + snapshot + tests",
            "images_required": False,
        },
        "dp-pm-steer": {
            "task_goal": "converge the task",
            "task_requirements": "keep the goal",
            "task_deliverables": "a real next action",
            "pm_decision_background": "budget is tight, the main line is unchanged",
        },
        "dp-w-check-task": {
            "task_goal": "finish the assigned slice",
            "reachability_facts": "the write face is free and the budget is enough",
            "completed": "read the files",
            "remaining": "write the test",
            "blockers": "none",
            "constraints": "existing task budget only",
        },
        "dp-QG": {
            "review_requirements": "all listed acceptance checks pass",
            "review_evidence": ["cmd: python -m pytest"],
            "review_findings": "no unresolved blocking finding",
            "uncovered_scope": "live deployment is out of scope",
        },
        "dp-gate-approve": {
            "gate_background": "stage close needs one decision",
            "current_state": "required keys are signed, integration check is green",
            "condition_evidence": ["evidence.txt:1"],
            "pm_note": {
                "subject": "close stage S1",
                "planned_action": "record the stage close only",
                "basis": {
                    "goal": "spec 1.1",
                    "evidence": "evidence.txt:1",
                    "budget": "unchanged hard budget",
                    "authority": "existing key authorization",
                },
            },
        },
        "dp-sign-key": {
            "delivery_goal": "deliver the eight-entry protocol",
            "actual_completion": "registry and snapshot are in place",
            "verification_evidence": {"verified": [], "unverified": []},
            "unfinished_impact": [],
        },
        "dp-auto": {
            "question": "the worker hit a write-face conflict",
            "background": {
                "task_goal": "keep the task moving",
                "current_state": "the conflicting file is claimed by another key",
                "tried": "asked the other window, no answer yet",
                "unknowns": "whether the other claim is still live",
                "constraints": "no new write permission is available",
            },
            "handling_options": _auto_candidates(),
        },
        "dp-route": {
            "decision_actor": "PM",
            "decision_object": "the next step of this task",
            "question": "which entry owns this temporary question",
        },
    }
    return json.loads(json.dumps(base[dp_id]))


def _preparation(dp_id: str, material: dict) -> dict:
    legal = list(dpts.resolve_entry_choices(dp_id, material))
    first_ref = next(iter(material))
    return {
        "basis_catalog": [
            {
                "id": "b-primary",
                "text": "PM-prepared reason drawn from the submitted material",
                "material_refs": [first_ref],
                "applies_to": legal,
            },
            {
                "id": "b-secondary",
                "text": "PM-prepared alternative reason",
                "material_refs": [first_ref],
                "applies_to": legal[-1:],
            },
        ],
        "prepared_at": PREPARED_AT,
    }


@pytest.fixture(autouse=True)
def _all_entries_enabled(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable all eight entries in this isolated project table (fixture only).

    The same fixture writes the real bound-actor facts: one active PM key row
    whose live claim is this very test process, and one real worker run (card
    header type, worker-written run.json, queue row) under its own owner key.
    A caller may not just declare a role in JSON; the CLI resolves these files.
    """
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    points = {
        dp_id: {
            "tier": dpts.get_decision_point(dp_id).tier,
            "enabled": True,
            "mode": "auto",
            "note": "t23 isolated fixture",
        }
        for dp_id in dpts.ACTIVE_DP_IDS
    }
    table = {
        "version": 1,
        "updated_at": "2026-11-08T00:00:00Z",
        "updated_by": "human",
        "points": points,
    }
    path = tmp_path / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    dpts.clear_points_config_cache()
    _bind_pm_claim(tmp_path)
    _append_index_row(tmp_path, "key-worker", claim="—")
    _write_worker_runtime(tmp_path)


_INDEX_HEADER = (
    "# Index Parallel",
    "",
    "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
    "|-----|--------|-------|---------|------|------|---------|",
)
_WORKERS_HEADER = "# mw-queue:v2"


def _index_path(project: pathlib.Path) -> pathlib.Path:
    return project / ".agenticdoc" / "_index.parallel"


def _append_index_row(
    project: pathlib.Path,
    key: str,
    *,
    claim: str,
    status: str = "active",
) -> None:
    path = _index_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else list(_INDEX_HEADER)
    lines.append(
        f"| {key} | {status} | EXECUTE | {claim} | — | t23 fixture | 2026-11-09T00:00:00Z |"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _bind_pm_claim(
    project: pathlib.Path, key: str = "key-1", *, claim: str | None = None
) -> None:
    _append_index_row(
        project, key, claim=claim or f"{socket.gethostname()}:{os.getpid()}"
    )


def _worker_task_path(project: pathlib.Path, owner: str = "key-worker", task: str = "task-1") -> pathlib.Path:
    return project / ".agenticdoc" / owner / "workers" / task / "task.md"


def _write_worker_runtime(
    project: pathlib.Path,
    *,
    owner: str = "key-worker",
    task: str = "task-1",
    role: str = "coding",
    run_status: str = "running",
    queue_status: str = "running",
    pid: int | None = None,
) -> pathlib.Path:
    """The real worker runtime facts: task.md header, run.json, trace, queue row."""
    task_dir = project / ".agenticdoc" / owner / "workers" / task
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    task_md.write_text(
        f"---\ntype: {role}\n---\n# {task}\n", encoding="utf-8", newline="\n"
    )
    worker_pid = os.getpid() if pid is None else pid
    (task_dir / "trace.log").write_text(
        f"[START] pid={worker_pid}\n", encoding="utf-8", newline="\n"
    )
    run = {
        "schema": 1,
        "task_key": task,
        "run_id": f"{task}@2026-11-09T00:00:00Z",
        "owner_key": owner,
        "kind": role,
        "status": run_status,
        "started_at": "2026-11-09T00:00:00Z",
        "pid": worker_pid,
        "artifacts": [],
    }
    (task_dir / "run.json").write_text(
        json.dumps(run, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    queue = project / ".agenticdoc" / "_workers.parallel"
    rows = queue.read_text(encoding="utf-8").splitlines() if queue.is_file() else [_WORKERS_HEADER]
    rows = [row for row in rows if not row.startswith(f"{task} |")]
    rows.append(
        f"{task} | {queue_status} | pi | timi | {task_md.resolve()} | "
        "2026-11-09T00:00:00Z | 2026-11-09T00:00:00Z |  | manual"
    )
    queue.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    return task_md


def _task_before(*, completed: object = None, status: str = "running") -> dict:
    return {
        "status": status,
        "source": "agent-report",
        "observed_at": TASK_AT,
        "completed": completed,
        "remaining": ["write the test"],
        "blockers": None,
    }


def _initiator_role(dp_id: str) -> str:
    """The real lifecycle role: PM, or a Worker's own card type."""
    return "coding" if dpts.ENTRY_ROLES[dp_id] == "worker" else "pm"


def _default_key(dp_id: str) -> str:
    return "key-worker" if dpts.ENTRY_ROLES[dp_id] == "worker" else "key-1"


def _meta(
    dp_id: str,
    logical_id: str,
    *,
    key: str | None = None,
    task_key: str | None = "task-1",
    task_before: dict | None = None,
) -> dict:
    meta = {
        "record_version": 2,
        "logical_id": logical_id,
        "key": _default_key(dp_id) if key is None else key,
        "task_key": task_key,
        "initiator_role": _initiator_role(dp_id),
        "retry_of": None,
    }
    if task_before is not None:
        meta["task_before"] = task_before
    return meta


def _envelope(
    dp_id: str,
    logical_id: str,
    *,
    key: str | None = None,
    task_key: str | None = "task-1",
    task_before: dict | None = None,
    preparation: dict | None = None,
    material: dict | None = None,
    **extra,
) -> dict:
    body = _material(dp_id) if material is None else material
    return {
        "material": body,
        "preparation": _preparation(dp_id, body) if preparation is None else preparation,
        "meta": _meta(
            dp_id,
            logical_id,
            key=key,
            task_key=task_key,
            task_before=task_before,
        ),
        **extra,
    }


# ---------------------------------------------------------------------------
# Fake decision client: records every call; never touches a provider.
# ---------------------------------------------------------------------------


class FakeCalls:
    def __init__(self) -> None:
        self.prepared: list[dict] = []
        self.decide: list[dict] = []
        self.fail_prepared: BaseException | None = None

    def result(self, dp: str, material: dict, preparation: dict) -> dict:
        legal = list(dpts.resolve_entry_choices(dp, material))
        choice = legal[0]
        basis = preparation["basis_catalog"][0]
        answers = {
            _business_question_id(dp): {"type": "choice", "choice": choice, "confidence": 0.9},
            "basis_id": {"type": "choice", "choice": basis["id"], "confidence": 0.9},
        }
        return {
            "dp": dp,
            "available": True,
            "replayed": False,
            "choice": choice,
            "basis_id": basis["id"],
            "basis_text": basis["text"],
            "basis_source": dpts.BASIS_SOURCE,
            "prepared_at": preparation["prepared_at"],
            "reason": None,
            "issues": [],
            "detail": "",
            "answers": answers,
            "attempts": 1,
            "transport_attempts": 1,
            "business_decisions": 1,
            "transport": "fake",
            "model": "fake-model",
            "confidence_source": "unknown",
            "latency_ms": 1,
        }


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeCalls:
    calls = FakeCalls()

    def fake_request_prepared(
        self,
        dp,
        material,
        preparation,
        *,
        actor_role=None,
        logical_id=None,
        replay_check=None,
    ):
        calls.prepared.append(
            {
                "dp": dp,
                "material": json.loads(json.dumps(material)),
                "preparation": json.loads(json.dumps(preparation)),
                "actor_role": actor_role,
                "logical_id": logical_id,
            }
        )
        if calls.fail_prepared is not None:
            raise calls.fail_prepared
        return calls.result(dp, material, preparation)

    def fake_decide(self, state, questions, dp=None):
        calls.decide.append({"state": state, "questions": questions, "dp": dp})
        return {"available": True, "answers": {"legacy": {"value": "x"}}, "reason": None}

    monkeypatch.setattr(mw.decision.DecisionClient, "request_prepared", fake_request_prepared)
    monkeypatch.setattr(mw.decision.DecisionClient, "decide", fake_decide)
    return calls


# ---------------------------------------------------------------------------
# Invocation helpers
# ---------------------------------------------------------------------------


def _args(action: str, project: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": action,
        "project": str(project),
        "json": True,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _invoke(
    action: str,
    project: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdin: str | None = None,
    stdin_flag: bool = False,
    worker_task: str | pathlib.Path | None = "auto",
    **kw,
) -> tuple[int, str, str]:
    args = _args(action, project, **kw)
    args.stdin = stdin_flag
    if worker_task == "auto":
        # A worker-only entry is invoked from the real worker runtime; every
        # other entry runs without an inherited worker flag.
        worker_task = (
            _worker_task_path(project) if kw.get("dp") == "dp-w-check-task" else None
        )
    if worker_task is None:
        monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    else:
        monkeypatch.setenv("PI_WORKER_TASK", str(worker_task))
    out, err = io.StringIO(), io.StringIO()
    if stdin is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    with redirect_stdout(out), redirect_stderr(err):
        rc = mw.cmd_decide(args)
    return rc, out.getvalue(), err.getvalue()


def _payload(text: str) -> dict:
    stripped = text.strip()
    assert stripped, f"expected a JSON payload, got {text!r}"
    return json.loads(stripped)


def _lifecycle_events(project: pathlib.Path) -> list[dict]:
    sink = decision_wire.production_lifecycle_sink(project)
    if not sink.is_file():
        return []
    return [json.loads(line) for line in sink.read_text(encoding="utf-8").splitlines() if line.strip()]


def _book_file(project: pathlib.Path, dp_id: str, *, meta: dict | None = None, **overrides) -> pathlib.Path:
    project.mkdir(parents=True, exist_ok=True)
    # Keep evidence resolution inside this fixture even under a real checkout.
    (project / ".git").mkdir(exist_ok=True)
    evidence = project / "evidence.txt"
    evidence.write_text("line one\nline two\n", encoding="utf-8", newline="\n")
    material = _material(dp_id) if "material" not in overrides else overrides.pop("material")
    book = {
        "schema_version": 3,
        "decision_point": dp_id,
        "material": material,
        "preparation": _preparation(dp_id, material),
        "context": {},
        "notes": {"evidence": {path: "evidence.txt:1" for path in dpts.REQUIRED_STATE_FIELDS.get(dp_id, ())}},
    }
    if meta is not None:
        book["meta"] = meta
    book.update(overrides)
    path = project / f"book-{dp_id.replace(':', '_')}.json"
    path.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def _valid_book_meta(dp_id: str, logical_id: str, *, key: str = "key-1") -> dict:
    return {
        "key": key,
        "task_key": "task-1",
        "logical_id": logical_id,
        "actor_role": dpts.ENTRY_ROLES[dp_id],
    }


# ---------------------------------------------------------------------------
# AC-001/AC-004: every active entry is callable through the prepared stdin path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_each_active_entry_accepts_the_prepared_envelope(
    dp_id: str, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    envelope = _envelope(dp_id, f"logical-{dp_id}")
    rc, out, err = _invoke(
        "run",
        tmp_path,
        monkeypatch,
        stdin=json.dumps(envelope),
        stdin_flag=True,
        dp=dp_id,
        dp_id=None,
        request_file=None,
        book=None,
    )
    assert rc == 0, err or out
    payload = _payload(out)
    if dp_id == "dp-gate-approve":
        # P0 stays human-only for the answer face; the registry id is active but
        # the CLI does not promote it to a machine-callable request.
        assert payload["available"] is False
        assert payload["reason"] == "disabled"
        assert fake.prepared == []
        return
    assert payload["available"] is True, payload
    assert payload["decision_id"] == f"{dp_id}:logical-{dp_id}"
    assert payload["dp"] == dp_id
    assert payload["acted"] is False
    assert payload["mode"] in ("auto", "suggest")
    assert payload["business_decisions"] == 1
    assert len(fake.prepared) == 1
    assert fake.prepared[0]["dp"] == dp_id
    assert fake.decide == []


# ---------------------------------------------------------------------------
# AC-002/AC-003: the 25 retired ids are refused on every request face, with
# zero model calls, zero business decisions and zero new lifecycle rows.
# ---------------------------------------------------------------------------


def test_all_25_retired_ids_are_rejected_on_every_request_face(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    before = len(_lifecycle_events(tmp_path))
    retired = sorted(dpts.RETIRED_DP_IDS)
    assert len(retired) == 25
    envelope = _envelope("dp-w-type", "retired-replay-target")
    for old_id in retired:
        # 1. prepared stdin
        rc, out, _ = _invoke(
            "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
            stdin_flag=True, dp=old_id, dp_id=None, request_file=None, book=None,
        )
        assert rc == 2
        assert "retired" in out
        # 1b. an old-id request in the pre-consolidation {material, meta} shape
        #     is still refused as retired, not as a missing-preparation error.
        legacy_envelope = {
            "material": {},
            "meta": _meta("dp-w-type", "retired-legacy-shape"),
        }
        rc, out, _ = _invoke(
            "run", tmp_path, monkeypatch, stdin=json.dumps(legacy_envelope),
            stdin_flag=True, dp=old_id, dp_id=None, request_file=None, book=None,
        )
        assert rc == 2
        assert "retired" in out
        # 2. structured request
        rc, _, err = _invoke(
            "run", tmp_path, monkeypatch,
            stdin=json.dumps({"state": {}}), stdin_flag=False,
            dp=old_id, dp_id=None, request_file=None, book=None,
        )
        assert rc == 2
        assert "retired" in err
        # 3. legacy caller-questions request
        rc, out, _ = _invoke(
            "run", tmp_path, monkeypatch,
            stdin=json.dumps({"state": "legacy", "questions": {"q": {"type": "noul"}}}),
            stdin_flag=False, dp=old_id, dp_id=None, request_file=None, book=None,
        )
        assert rc == 2
        assert "retired" in out
        # 4. book file
        book = _book_file(tmp_path, "dp-w-type")
        data = json.loads(book.read_text(encoding="utf-8"))
        data["decision_point"] = old_id
        book.write_text(json.dumps(data), encoding="utf-8", newline="\n")
        rc, _, err = _invoke(
            "run", tmp_path, monkeypatch,
            stdin_flag=False, dp=None, dp_id=None, request_file=None, book=str(book),
        )
        assert rc == 2
        assert "retired" in err
        # 5. book new
        rc, _, err = _invoke("book", tmp_path, monkeypatch, book_action="new", dp=old_id, out=None)
        assert rc == 2
        assert "retired" in err
        # 6. book check
        rc, out, _ = _invoke(
            "book", tmp_path, monkeypatch, book_action="check", file=str(book)
        )
        assert rc == 2
        assert "retired" in out
        # 7. lifecycle replay against an old id
        rc, out, _ = _invoke(
            "lifecycle", tmp_path, monkeypatch,
            stdin=json.dumps(
                {
                    "meta": _meta("dp-w-type", "retired-replay-target", task_before=None),
                    "decision_id": f"{old_id}:retired-replay-target",
                    "dp": old_id,
                    "stage": "consumed",
                    "answer": "approve",
                }
            ),
            stdin_flag=True, request_file=None,
        )
        assert rc == 2
        assert "retired" in out
    assert fake.prepared == []
    assert fake.decide == []
    assert len(_lifecycle_events(tmp_path)) == before


def test_retired_id_with_an_existing_logical_id_is_not_replayed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    envelope = _envelope("dp-w-type", "shared-logical")
    rc, _, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-w-type", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    assert len(fake.prepared) == 1
    before = len(_lifecycle_events(tmp_path))
    # A retired id may not reuse that historical logical id as a success.
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp1-dispatch-type", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "retired" in out
    assert len(fake.prepared) == 1
    assert len(_lifecycle_events(tmp_path)) == before


# ---------------------------------------------------------------------------
# AC-012/AC-043: invalid material/preparation/role/context blocks before the
# creation fact and the model call.
# ---------------------------------------------------------------------------


def test_stdin_requires_preparation_and_complete_contract(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    good = _envelope("dp-pm-steer", "contract-logical")
    missing = dict(good)
    missing.pop("preparation")
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(missing),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "preparation" in out
    assert fake.prepared == []
    assert _lifecycle_events(tmp_path) == []

    bad_material = _envelope("dp-pm-steer", "contract-logical")
    bad_material["material"].pop("task_goal")
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(bad_material),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "task_goal" in out
    assert fake.prepared == []
    assert _lifecycle_events(tmp_path) == []

    bad_basis = _envelope("dp-pm-steer", "contract-logical")
    bad_basis["preparation"]["basis_catalog"][0]["applies_to"] = ["invented-choice"]
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(bad_basis),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "preparation" in out or "applies_to" in out
    assert fake.prepared == []
    assert _lifecycle_events(tmp_path) == []


def test_worker_only_entry_refuses_a_pm_envelope(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    envelope = _envelope("dp-w-check-task", "role-logical")
    envelope["meta"]["initiator_role"] = "pm"
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "role-forbidden" in out or "actor_role" in out
    assert fake.prepared == []
    assert _lifecycle_events(tmp_path) == []


def test_invalid_context_is_refused_before_any_send(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    envelope = _envelope("dp-pm-steer", "context-logical", context={"not-a-slot": "x"})
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "context" in out
    assert fake.prepared == []
    assert _lifecycle_events(tmp_path) == []


def test_transport_exception_is_reported_without_a_fabricated_decision(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    fake.fail_prepared = RuntimeError("boom")
    envelope = _envelope("dp-pm-steer", "exception-logical")
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    payload = _payload(out)
    assert payload["available"] is False
    assert payload["reason"] == "upstream-error"
    assert payload["business_decisions"] == 0
    assert payload["decision_id"] is None
    assert fake.prepared  # the call really happened; the result is a refusal


# ---------------------------------------------------------------------------
# Replay and parent reference: the host claim is verified against the ledger.
# ---------------------------------------------------------------------------


def test_same_logical_id_replays_without_a_second_send(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    envelope = _envelope("dp-pm-steer", "replay-logical")
    rc, first, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    assert len(fake.prepared) == 1
    before = len(_lifecycle_events(tmp_path))
    rc, second, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    payload = _payload(second)
    assert payload["replayed"] is True
    assert payload["available"] is True
    assert payload["mode"] in ("auto", "suggest")
    assert payload["answers"] is not None
    assert payload["answers"][_business_question_id("dp-pm-steer")]["choice"] == payload["choice"]
    assert payload["decision_id"] == _payload(first)["decision_id"]
    assert payload["business_decisions"] == 1
    assert len(fake.prepared) == 1
    assert len(_lifecycle_events(tmp_path)) == before


def test_valid_parent_reference_is_recorded_only_after_ledger_proof(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    parent_envelope = _envelope("dp-pm-steer", "parent-logical")
    rc, parent_out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(parent_envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    parent_id = _payload(parent_out)["decision_id"]
    child_envelope = _envelope(
        "dp-pm-steer", "child-logical", parent_decision_ref=parent_id
    )
    rc, child_out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(child_envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    assert _payload(child_out)["available"] is True
    request_rows = [
        row
        for row in _lifecycle_events(tmp_path)
        if row.get("kind") == "request" and row.get("logical_id") == "child-logical"
    ]
    assert request_rows
    assert request_rows[-1]["parent_ref"] == parent_id


@pytest.mark.parametrize(
    "parent_ref",
    ["dp-pm-steer:not-in-this-ledger", "not-a-decision-id"],
)
def test_fabricated_parent_reference_is_refused_before_a_send(
    parent_ref: str,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeCalls,
) -> None:
    envelope = _envelope(
        "dp-pm-steer", "fabricated-parent-child", parent_decision_ref=parent_ref
    )
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "parent_decision_ref" in out
    assert fake.prepared == []
    assert _lifecycle_events(tmp_path) == []


def test_cross_key_parent_reference_is_refused(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    _bind_pm_claim(tmp_path, "other-key")
    parent_envelope = _envelope("dp-pm-steer", "other-key-parent", key="other-key")
    rc, parent_out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(parent_envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    parent_id = _payload(parent_out)["decision_id"]
    child_envelope = _envelope(
        "dp-pm-steer", "key-mismatch-child", key="key-1", parent_decision_ref=parent_id
    )
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(child_envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "same key" in out
    assert len(fake.prepared) == 1


def test_start_only_parent_is_not_a_business_decision(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    cfg = decision.DecisionConfig(project_root=tmp_path)
    snapshot = decision.credential_snapshot(cfg)
    redactor = decision.credential_redactor(cfg, snapshot=snapshot)
    store = decision_lifecycle.LifecycleStore.production(tmp_path, redact=redactor)
    meta = decision_lifecycle.DecisionMeta(
        key="key-1",
        logical_id="start-only-logical",
        initiator_role="pm",
        task_key="task-1",
    )
    decision_lifecycle.record_start(
        store, meta, decision_id="dp-pm-steer:start-only-logical"
    )
    child = _envelope(
        "dp-pm-steer",
        "start-only-child",
        parent_decision_ref="dp-pm-steer:start-only-logical",
    )
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(child),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "business request" in out
    assert fake.prepared == []


# ---------------------------------------------------------------------------
# The book path: active id/contract, real prepared layers, explicit refusal of
# legacy shapes, and a receipt on the production writer.
# ---------------------------------------------------------------------------


def test_book_path_sends_the_prepared_layers(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    book = _book_file(tmp_path, "dp-QG", meta=_valid_book_meta("dp-QG", "book-logical"))
    rc, out, err = _invoke(
        "run", tmp_path, monkeypatch, stdin_flag=False, dp=None, dp_id=None,
        request_file=None, book=str(book),
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["available"] is True
    assert payload["decision_id"] == "dp-QG:book-logical"
    assert len(fake.prepared) == 1
    assert fake.prepared[0]["dp"] == "dp-QG"
    assert fake.prepared[0]["preparation"]["prepared_at"] == PREPARED_AT
    receipts = tmp_path / ".agenticdoc" / "_autopilot" / "book-receipts.jsonl"
    assert receipts.is_file()
    receipt = json.loads(receipts.read_text(encoding="utf-8").splitlines()[-1])
    assert receipt["decision_id"] == "dp-QG:book-logical"
    assert receipt["file_sha256"]


@pytest.mark.parametrize("diagnostic", ["unknown-key", "schema-value", "decision-point-value"])
def test_book_run_schema_diagnostics_redact_configured_secret(
    diagnostic: str, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    secret = "configuredT24CredentialOnly7d93a2"
    _write_decide_config(tmp_path, api_key=secret)
    book = _book_file(tmp_path, "dp-QG", meta=_valid_book_meta("dp-QG", "schema-secret"))
    data = json.loads(book.read_text(encoding="utf-8"))
    if diagnostic == "unknown-key":
        data[secret] = "unexpected field"
        expected = "unknown top-level keys"
    elif diagnostic == "schema-value":
        data["schema_version"] = secret
        expected = "schema_version"
    else:
        data["decision_point"] = secret
        expected = "unknown decision point id"
    book.write_text(json.dumps(data), encoding="utf-8", newline="\n")
    backend_calls = _no_backend(monkeypatch)
    snapshots: list[object] = []
    original_snapshot = decision.credential_snapshot

    def capture_snapshot(cfg):
        assert cfg.extras["api_key"] == secret
        snapshot = original_snapshot(cfg)
        snapshots.append(snapshot)
        return snapshot

    monkeypatch.setattr(decision, "credential_snapshot", capture_snapshot)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    rc, out, err = _invoke(
        "run", tmp_path, monkeypatch, stdin_flag=False, dp=None, dp_id=None,
        request_file=None, book=str(book),
    )
    assert rc == 2
    assert "mw decide run" in err
    assert "book-schema" in err
    assert expected in err
    assert str(book) in err
    assert secret not in out + err
    assert len(snapshots) == 1
    assert fake.prepared == [] and fake.decide == []
    assert backend_calls == []
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before, "schema refusal must not write receipts or business state"
    receipts = tmp_path / ".agenticdoc" / "_autopilot" / "book-receipts.jsonl"
    if receipts.exists():
        assert secret not in receipts.read_text(encoding="utf-8")


def test_book_without_local_meta_cannot_submit_a_real_request(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    book = _book_file(tmp_path, "dp-QG")
    rc, _, err = _invoke(
        "run", tmp_path, monkeypatch, stdin_flag=False, dp=None, dp_id=None,
        request_file=None, book=str(book),
    )
    assert rc == 2
    assert "meta" in err
    assert fake.prepared == []


def test_book_legacy_state_and_caller_questions_are_refused(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    book = _book_file(
        tmp_path, "dp-QG", meta=_valid_book_meta("dp-QG", "book-legacy")
    )
    data = json.loads(book.read_text(encoding="utf-8"))
    data["questions"] = {"q": {"type": "noul"}}
    book.write_text(json.dumps(data), encoding="utf-8", newline="\n")
    rc, _, err = _invoke(
        "run", tmp_path, monkeypatch, stdin_flag=False, dp=None, dp_id=None,
        request_file=None, book=str(book),
    )
    assert rc == 2
    assert "questions" in err
    assert fake.prepared == []

    legacy = _book_file(
        tmp_path, "dp-QG", meta=_valid_book_meta("dp-QG", "book-legacy")
    )
    data = json.loads(legacy.read_text(encoding="utf-8"))
    data["state"] = data.pop("material")
    legacy.write_text(json.dumps(data), encoding="utf-8", newline="\n")
    rc, _, err = _invoke(
        "run", tmp_path, monkeypatch, stdin_flag=False, dp=None, dp_id=None,
        request_file=None, book=str(legacy),
    )
    assert rc == 2
    assert "state" in err or "book" in err
    assert fake.prepared == []


def test_book_new_and_check_classify_active_and_retired(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc, out, _ = _invoke("book", tmp_path, monkeypatch, book_action="new", dp="dp-w-type", out=None)
    assert rc == 0
    skeleton = _payload(out)
    assert skeleton["decision_point"] == "dp-w-type"
    assert "material" in skeleton and "preparation" in skeleton
    assert "meta" not in skeleton

    book = _book_file(tmp_path, "dp-w-type", meta=_valid_book_meta("dp-w-type", "book-check"))
    rc, out, _ = _invoke("book", tmp_path, monkeypatch, book_action="check", file=str(book))
    assert rc == 0
    assert _payload(out)["ok"] is True


# ---------------------------------------------------------------------------
# Legacy free-form questions: kept as a query, never a DP submission.
# ---------------------------------------------------------------------------


def test_legacy_questions_cannot_target_an_active_entry(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps({"state": "legacy", "questions": {"q": {"type": "noul"}}}),
        stdin_flag=False, dp="dp-w-type", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "active entry" in out
    assert fake.decide == []
    assert fake.prepared == []


def test_legacy_non_dp_queries_never_send_without_operator_confirmation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    """A bare/arbitrary legacy label is a query, not an agent-callable DP.

    The ordinary run process cannot turn `questions` plus a label (including the
    old bare `dp1`) or a worker/RPC caller into a model request: only the
    registered operator host may send the frozen draft after human confirmation.
    """
    _write_decide_config(tmp_path)
    submitted: list[bytes] = []

    def unavailable(project_id, payload, *, timeout_ms=5000):
        submitted.append(bytes(payload))
        return {"ok": False, "reason": "host-unavailable"}

    monkeypatch.setattr(mw.operator_authority, "submit_ask", unavailable)
    backend_calls = _no_backend(monkeypatch)
    for label in ("dp1", "dp-legacy", "dp2-worker-clarify"):
        rc, out, err = _invoke(
            "run", tmp_path, monkeypatch,
            stdin=json.dumps({"state": "legacy", "questions": {"q": {"type": "noul"}}}),
            stdin_flag=False, dp=label, dp_id=None, request_file=None, book=None,
        )
        assert rc == 2
        assert out.strip() == ""
        assert "host-unavailable" in err
        assert fake.decide == []
        assert fake.prepared == []
    assert backend_calls == []
    assert len(submitted) == 3  # only the host guard/sender may ever send


def test_legacy_non_dp_query_submits_the_exact_frozen_draft_once(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    _write_decide_config(tmp_path)
    submitted: list[tuple[str, bytes]] = []

    def fake_submit(project_id, payload, *, timeout_ms=5000):
        submitted.append((project_id, bytes(payload)))
        return {
            "ok": True,
            "id": _PENDING_ID,
            "state": "pending",
            "sha256": "b" * 64,
        }

    monkeypatch.setattr(mw.operator_authority, "submit_ask", fake_submit)
    backend_calls = _no_backend(monkeypatch)
    questions = {
        "triage_type": {"type": "choice", "choices": ["coding", "research", "review"]}
    }
    state = "card body\nsecond line"
    rc, out, err = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps({"state": state, "questions": questions}),
        stdin_flag=False, dp="dp1", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["state"] == "pending"
    assert payload["id"] == _PENDING_ID
    assert "--result" in payload["next"]
    assert payload["frozen_bytes"] == len(submitted[0][1])
    frozen = submitted[0][1]
    draft = json.loads(frozen.decode("utf-8"))
    assert draft["purpose"] == "ask"
    assert draft["questions"] == questions
    assert draft["state"] == state
    assert mw.operator_ask_validate(tmp_path, frozen) is True
    assert fake.decide == []
    assert fake.prepared == []
    assert backend_calls == []


def test_legacy_query_only_the_authorized_host_sends_the_original_once(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_decide_config(tmp_path)
    submitted: list[bytes] = []
    monkeypatch.setattr(
        mw.operator_authority,
        "submit_ask",
        lambda project_id, payload, *, timeout_ms=5000: (
            submitted.append(bytes(payload))
            or {"ok": True, "id": _PENDING_ID, "state": "pending", "sha256": "c" * 64}
        ),
    )
    questions = {"q": {"type": "noul"}}
    rc, out, err = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps({"state": "legacy", "questions": questions}),
        stdin_flag=False, dp="dp1", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0, err or out
    frozen = submitted[0]

    factory_calls: list[object] = []
    fake = decision.FakeBackend(
        [
            decision.BackendOutcome(
                available=True,
                reason=None,
                retryable=False,
                answers={"q": {"value": 0.75, "confidence": None}},
                latency_ms=3,
                detail="",
            )
        ]
    )

    def factory(cfg):
        factory_calls.append(cfg)
        return fake

    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", factory)

    # An ordinary CLI call, a worker/RPC caller or a forged callback cannot send.
    monkeypatch.setattr(mw.operator_host, "authorized_callback", lambda *args: False)
    with pytest.raises(mw._OperatorAskError):
        mw.operator_ask_frozen(tmp_path, frozen)
    assert factory_calls == []

    # Only the registered host callback sends the same frozen query, exactly once.
    monkeypatch.setattr(mw.operator_host, "authorized_callback", lambda *args: True)
    result = mw.operator_ask_frozen(tmp_path, frozen)
    assert len(fake.calls) == 1
    assert fake.calls[0]["state"] == "legacy"
    assert fake.calls[0]["questions"] == questions
    assert result["answers"]["q"]["value"] == 0.75
    assert set(result) == {"model", "usage", "latency_ms", "answers"}


# ---------------------------------------------------------------------------
# AC-051: null vs [] stays distinct in the recorded snapshot, and the sign-key
# arrays refuse null while accepting a real [].
# ---------------------------------------------------------------------------


def test_task_before_null_and_empty_stay_distinct(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    none_envelope = _envelope(
        "dp-pm-steer", "snapshot-none", task_before=_task_before(completed=None)
    )
    empty_envelope = _envelope(
        "dp-pm-steer", "snapshot-empty", task_before=_task_before(completed=[])
    )
    assert _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(none_envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )[0] == 0
    assert _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(empty_envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )[0] == 0
    starts = {
        row["logical_id"]: row
        for row in _lifecycle_events(tmp_path)
        if row.get("kind") == "record-start"
    }
    assert starts["snapshot-none"]["task_before"]["completed"] is None
    assert starts["snapshot-empty"]["task_before"]["completed"] == []


def test_sign_key_arrays_refuse_null_but_accept_empty(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    invalid = _envelope("dp-sign-key", "sign-null")
    invalid["material"]["verification_evidence"]["verified"] = None
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(invalid),
        stdin_flag=True, dp="dp-sign-key", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "verification_evidence.verified" in out
    assert fake.prepared == []

    valid = _envelope("dp-sign-key", "sign-empty")
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(valid),
        stdin_flag=True, dp="dp-sign-key", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0, out
    assert _payload(out)["available"] is True
    assert len(fake.prepared) == 1


# ---------------------------------------------------------------------------
# Classification sanity: the book registry view is the same eight entries.
# ---------------------------------------------------------------------------


def test_book_registry_view_is_exactly_the_eight_entries() -> None:
    assert tuple(decision_book.registry_points()) == dpts.ACTIVE_DP_IDS
    assert all(not decision_book.is_retired(dp_id) for dp_id in dpts.ACTIVE_DP_IDS)
    assert all(decision_book.is_retired(dp_id) for dp_id in dpts.RETIRED_DP_IDS)


# ---------------------------------------------------------------------------
# T24: isolated human ask (frozen bytes + host guard/sender) and the read-only
# typed sign-off validator. Nothing here sends to a provider or treats role/
# token/TTY as a human.
# ---------------------------------------------------------------------------

_PENDING_ID = "0123456789abcdef0123456789abcdef"
_ASK_QUESTIONS = {
    "urgent": {"type": "noul", "instructions": "is this urgent"},
    "dept": {
        "type": "choice",
        "criteria": {"billing": "支付", "technical": None},
        "choices": ["billing", "technical"],
        "labels": {"billing": "支付", "technical": None},
    },
    "effort": {"type": "score", "criteria": ["小", "中", "大"], "min": 0, "max": 2},
}


def _write_decide_config(project: pathlib.Path, **fields: object) -> None:
    data: dict = {
        "enabled": True,
        "transport": "timi-decisions",
        "model": "jev-latest",
    }
    data.update(fields)
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8", newline="\n")


def _ask_kwargs(**overrides: object) -> dict:
    base: dict = {
        "state": None,
        "state_file": None,
        "book": None,
        "noul": [],
        "noul_criteria": [],
        "choice": [],
        "score": [],
        "model": None,
        "result": None,
    }
    base.update(overrides)
    return base


def _frozen_ask(
    project: pathlib.Path,
    *,
    state: str = "original bytes",
    questions: dict | None = None,
    model: str = "jev-latest",
) -> bytes:
    cfg = mw._decide_config_snapshot(project)
    assert cfg is not None
    return mw._operator_ask_frozen_draft(
        project, cfg, dict(questions or _ASK_QUESTIONS), state, model
    )


def _no_backend(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def factory(cfg):
        calls.append({"cfg": cfg})
        raise AssertionError("this path must not build a provider backend")

    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", factory)
    return calls


def test_ask_submits_exact_frozen_bytes_and_never_calls_the_model(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_decide_config(tmp_path)
    submitted: list[tuple[str, bytes]] = []

    def fake_submit(project_id, payload, *, timeout_ms=5000):
        submitted.append((project_id, bytes(payload)))
        return {
            "ok": True,
            "id": _PENDING_ID,
            "state": "pending",
            "sha256": "a" * 64,
        }

    monkeypatch.setattr(mw.operator_authority, "submit_ask", fake_submit)
    _no_backend(monkeypatch)
    state = "first line\n第二行 with tabs\tand \"quotes\""
    rc, out, err = _invoke(
        "ask",
        tmp_path,
        monkeypatch,
        **_ask_kwargs(
            state=state,
            noul=["urgent=is this urgent"],
            choice=["dept=billing:支付,technical"],
            score=["effort=小,中,大"],
            json=True,
        ),
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["id"] == _PENDING_ID
    assert payload["state"] == "pending"
    assert "--result" in payload["next"]
    assert submitted and submitted[0][0] == decision_wire.project_id_for(tmp_path)
    frozen = submitted[0][1]
    draft = json.loads(frozen.decode("utf-8"))
    assert list(draft) == [
        "schema",
        "purpose",
        "project_id",
        "transport",
        "model",
        "destination",
        "questions",
        "state",
    ]
    assert draft["schema"] == 1 and draft["purpose"] == "ask"
    assert draft["state"] == state
    assert list(draft["questions"]) == ["urgent", "dept", "effort"]
    assert draft["questions"]["dept"]["criteria"] == {
        "billing": "支付",
        "technical": None,
    }
    assert mw.operator_ask_validate(tmp_path, frozen) is True
    assert len(frozen) == payload["frozen_bytes"]


def test_ask_without_a_host_never_falls_back_to_a_direct_send(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_decide_config(tmp_path)
    monkeypatch.setattr(
        mw.operator_authority,
        "submit_ask",
        lambda *args, **kwargs: {"ok": False, "reason": "host-unavailable"},
    )
    backend_calls = _no_backend(monkeypatch)
    rc, out, err = _invoke(
        "ask",
        tmp_path,
        monkeypatch,
        **_ask_kwargs(state="s", noul=["urgent=is this urgent"]),
    )
    assert rc == 2
    assert out.strip() == ""
    assert "host-unavailable" in err
    assert "no direct fallback" in err
    assert backend_calls == []


def test_operator_ask_validate_refuses_drift_forgeries_and_bad_material(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_decide_config(tmp_path)
    legal = _frozen_ask(tmp_path)
    assert mw.operator_ask_validate(tmp_path, legal) is True

    def refused(raw: bytes) -> None:
        assert mw.operator_ask_validate(tmp_path, raw) is False

    draft = json.loads(legal.decode("utf-8"))
    wrong_project = dict(draft, project_id="0" * 16)
    refused(json.dumps(wrong_project).encode("utf-8"))
    drift = dict(draft, destination=draft["destination"] + "/other")
    refused(json.dumps(drift).encode("utf-8"))
    wrong_transport = dict(draft, transport="other-transport")
    refused(json.dumps(wrong_transport).encode("utf-8"))
    wrong_schema = dict(draft, schema=2)
    refused(json.dumps(wrong_schema).encode("utf-8"))
    wrong_purpose = dict(draft, purpose="h12")
    refused(json.dumps(wrong_purpose).encode("utf-8"))
    extra = dict(draft, extra=True)
    refused(json.dumps(extra).encode("utf-8"))
    refused(b'{"schema":1,"schema":1}')
    refused(b"not-json")
    refused(b"\xff")
    refused(b"")
    too_many = dict(draft, questions={**draft["questions"], "more": {"type": "noul", "instructions": "x"}})
    _write_decide_config(tmp_path, max_questions=1)
    refused(json.dumps(too_many).encode("utf-8"))
    _write_decide_config(tmp_path)
    bad_type = dict(draft, questions={"q": {"type": "box", "instructions": "x"}})
    refused(json.dumps(bad_type).encode("utf-8"))
    bad_score = dict(draft, questions={"q": {"type": "score", "instructions": "x", "criteria": ["one"], "min": 0, "max": 0}})
    refused(json.dumps(bad_score).encode("utf-8"))
    _write_decide_config(tmp_path, api_key="sk-" + "t24secret" * 4)
    leak = dict(draft, state="state carries sk-" + "t24secret" * 4)
    refused(json.dumps(leak, ensure_ascii=False).encode("utf-8"))


def test_operator_ask_frozen_requires_the_authorized_host_callback(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_decide_config(tmp_path)
    frozen = _frozen_ask(tmp_path)
    backend_calls = _no_backend(monkeypatch)
    monkeypatch.setattr(mw.operator_host, "authorized_callback", lambda *args: False)
    with pytest.raises(mw._OperatorAskError):
        mw.operator_ask_frozen(tmp_path, frozen)
    assert backend_calls == []

    # A forged ContextVar frame is still not the live service callback.
    token = mw.operator_host._CALL.set(
        (tmp_path.resolve(), "ask", frozen, None, lambda *_: True)
    )
    try:
        with pytest.raises(mw._OperatorAskError):
            mw.operator_ask_frozen(tmp_path, frozen)
    finally:
        mw.operator_host._CALL.reset(token)
    assert backend_calls == []

    # The real callback passes; only then does the frozen request reach the one
    # existing backend, and the returned shape is the original Ask shape.
    monkeypatch.setattr(mw.operator_host, "authorized_callback", lambda *args: True)
    fake = decision.FakeBackend(
        [
            decision.BackendOutcome(
                available=True,
                reason=None,
                retryable=False,
                answers={
                    "urgent": {"value": 0.87, "confidence": None},
                    "dept": {"value": "billing", "confidence": 0.9},
                    "effort": {
                        "value": 1,
                        "confidence": 0.8,
                        "legend": {"0": "小", "1": "中", "2": "大"},
                    },
                },
                latency_ms=5,
                detail="",
            )
        ]
    )
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: fake)
    result = mw.operator_ask_frozen(tmp_path, frozen)
    assert set(result) == {"model", "usage", "latency_ms", "answers"}
    assert result["answers"]["dept"]["value"] == "billing"
    assert len(fake.calls) == 1
    assert fake.calls[0]["state"] == "original bytes"


def test_ask_result_reads_the_original_shape_and_never_sends(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_decide_config(tmp_path)
    backend_calls = _no_backend(monkeypatch)
    answers = {
        "urgent": {"value": 0.87, "confidence": None},
        "dept": {
            "value": "billing",
            "confidence": 0.9,
            "probabilities": {"billing": 0.9, "technical": 0.1},
        },
    }
    reply = {
        "ok": True,
        "id": _PENDING_ID,
        "state": "applied",
        "result": {"model": "fake-model", "usage": None, "latency_ms": 9, "answers": answers},
    }
    monkeypatch.setattr(mw.operator_authority, "ask_result", lambda *args, **kwargs: reply)
    rc, out, err = _invoke(
        "ask", tmp_path, monkeypatch, **_ask_kwargs(result=_PENDING_ID, json=True)
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["answers"] == answers
    assert payload["model"] == "fake-model"
    assert "decision_id" not in payload
    assert backend_calls == []

    rc, out, err = _invoke(
        "ask", tmp_path, monkeypatch, **_ask_kwargs(result=_PENDING_ID, json=False)
    )
    assert rc == 0, err or out
    assert "[noul]" in out and "[choice]" in out
    assert "decision_id" not in out
    assert backend_calls == []

    pending = dict(reply, state="pending", result=None)
    monkeypatch.setattr(mw.operator_authority, "ask_result", lambda *args, **kwargs: pending)
    rc, out, _ = _invoke(
        "ask", tmp_path, monkeypatch, **_ask_kwargs(result=_PENDING_ID, json=True)
    )
    assert rc == 0
    assert _payload(out)["answers"] is None

    for state in ("failed", "expired", "reserved", "unknown"):
        monkeypatch.setattr(
            mw.operator_authority,
            "ask_result",
            lambda *args, _state=state, **kwargs: dict(reply, state=_state, result=None),
        )
        rc, out, err = _invoke(
            "ask", tmp_path, monkeypatch, **_ask_kwargs(result=_PENDING_ID)
        )
        assert rc == 2
        assert out.strip() == ""
        assert state in err

    # An applied state without a real answer object is not invented.
    monkeypatch.setattr(
        mw.operator_authority,
        "ask_result",
        lambda *args, **kwargs: dict(reply, result={"model": "m", "answers": None}),
    )
    rc, out, _ = _invoke("ask", tmp_path, monkeypatch, **_ask_kwargs(result=_PENDING_ID))
    assert rc == 2
    assert out.strip() == ""

    # A non-id cannot be forwarded as an operation identity.
    called: list[str] = []
    monkeypatch.setattr(
        mw.operator_authority,
        "ask_result",
        lambda *args, **kwargs: called.append("called") or reply,
    )
    rc, _, _ = _invoke("ask", tmp_path, monkeypatch, **_ask_kwargs(result="not-an-id"))
    assert rc == 2 and called == []
    assert backend_calls == []


# ---------------------------------------------------------------------------
# T24: the legal dp-gate-approve request is not permanently blocked by the
# retired dp15 P0 label; no release is produced here (the effect consumer owns
# that), and a missing/invalid policy still blocks before the model.
# ---------------------------------------------------------------------------


def _write_policy(project: pathlib.Path, *, scope: list[str]) -> None:
    doc = {
        "schema_version": 1,
        "authority_ref": "grant-t24",
        "scope": scope,
        "hard_limits": [
            {"unit": "round", "limit": 2, "usage_source": "task-card-rounds"}
        ],
    }
    path = project / ".agenticdoc" / "_autopilot" / "decision-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def test_gate_approve_request_needs_a_usable_policy_and_releases_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    envelope = _envelope("dp-gate-approve", "gate-logical")
    # No policy: the P0 request stays human-only (zero model, zero release).
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-gate-approve", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    assert _payload(out)["available"] is False
    assert fake.prepared == []

    # A policy that does not grant the gate action is not a grant either.
    _write_policy(tmp_path, scope=["key:key-1"])
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-gate-approve", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    assert _payload(out)["available"] is False
    assert fake.prepared == []

    # A usable policy granting action:gate-approve lets the real prepared
    # request run; the answer is only a judgment (acted=False, no execution and
    # no lifecycle/sign-off row), never a release.
    _write_policy(tmp_path, scope=["key:key-1", "action:gate-approve"])
    rc, out, err = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-gate-approve", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["available"] is True
    assert payload["acted"] is False
    assert payload["business_decisions"] == 1
    assert len(fake.prepared) == 1
    rows = _lifecycle_events(tmp_path)
    assert all(row.get("kind") in ("record-start", "request") for row in rows)
    assert not (tmp_path / ".mw" / "decide-points.json").read_text(encoding="utf-8").count(
        "gate-effect"
    )


# ---------------------------------------------------------------------------
# T24: typed apply refuses a key-signoff product; the read-only validator CLI
# sees exactly the T22 writer's result (same decision, no second approval).
# ---------------------------------------------------------------------------

_SIGN_KEY = "key-1"
_SIGN_LOGICAL = "sign-logical-1"


def _sign_material() -> dict:
    return {
        "delivery_goal": "deliver the T24 CLI wiring",
        "actual_completion": "ask freeze/sign validator wired",
        "verification_evidence": {
            "verified": ["pytest test_dp_consolidation_cli.py"],
            "unverified": ["live operator host"],
        },
        "unfinished_impact": ["framework sign gate stays T25"],
    }


def _sign_project(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    project = tmp_path / "project"
    key_dir = project / ".agenticdoc" / _SIGN_KEY
    (key_dir / "evidence" / "review").mkdir(parents=True)
    _write_decide_config(project)
    _bind_pm_claim(project, _SIGN_KEY)
    import decide_archive

    decide_archive.append_decide(
        key_dir.parent / "_autopilot" / "decisions.jsonl",
        dp="dp-QG",
        key=_SIGN_KEY,
        task_key="task-1",
        trigger_id="t24-sign",
        state={"schema_version": 2, "decision_point": "dp-QG"},
        questions_version="q-0123abcd",
        available=True,
        answer={"q-verdict": {"value": "pass", "confidence": 0.9}},
        authority="binding",
        acted=True,
        actual_action="record the QG pass verdict",
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    return project, key_dir


def _sign_envelope(logical_id: str) -> dict:
    material = _sign_material()
    return {
        "material": material,
        "preparation": _preparation("dp-sign-key", material),
        "meta": {
            "record_version": 2,
            "logical_id": logical_id,
            "key": _SIGN_KEY,
            "task_key": "task-1",
            "initiator_role": "pm",
            "retry_of": None,
        },
    }


def _sign_args(project: pathlib.Path, **kw) -> dict:
    base = {
        "key_pos": _SIGN_KEY,
        "key": None,
        "retry_write": None,
        "validate": None,
        "auto": False,
        "disable": False,
        "reason": None,
        "allow_empty": False,
        "dry_run": False,
    }
    base.update(kw)
    return base


def _answer_backend(conclusion: str) -> "decision.FakeBackend":
    def answer(state, questions, cfg):
        business_id = _business_question_id("dp-sign-key")
        assert set(questions) == {business_id, "basis_id"}, questions
        assert state["material"] == _sign_material()
        assert state["preparation"] == _preparation("dp-sign-key", _sign_material())
        return decision.BackendOutcome(
            available=True,
            reason=None,
            retryable=False,
            answers={
                business_id: {"value": conclusion, "confidence": 0.9},
                "basis_id": {"value": "b-primary", "confidence": 0.9},
            },
            latency_ms=5,
            detail="",
        )

    return decision.FakeBackend([answer])


def test_sign_finalize_is_one_judgment_one_write_and_the_validator_reads_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, key_dir = _sign_project(tmp_path)
    fake = _answer_backend("finalize")
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: fake)
    envelope = _sign_envelope(_SIGN_LOGICAL)
    rc, out, err = _invoke(
        "sign",
        project,
        monkeypatch,
        stdin=json.dumps(envelope),
        stdin_flag=True,
        **_sign_args(project, json=True),
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["conclusion"] == "finalize"
    assert payload["signoff_status"] == "written"
    assert payload["second_approval"] == 0
    signoff = key_dir / "evidence" / "review" / "sign-final.md"
    assert signoff.is_file()
    assert len(fake.calls) == 1
    validation = decision_signoff_result.validate_key_signoff(
        key_dir,
        _SIGN_KEY,
        _sign_material(),
        _sign_material()["verification_evidence"],
    )
    assert validation.signs_key is True
    assert validation.closes_stage is False

    # Same decision: read the typed result through the read-only `--validate`
    # CLI face (same validator, zero writes, zero new model calls).
    validator_input = project / "validator.json"
    validator_input.write_text(
        json.dumps(
            {
                "material": _sign_material(),
                "current_evidence": _sign_material()["verification_evidence"],
                "expected_logical_id": _SIGN_LOGICAL,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
        newline="\n",
    )
    before = signoff.read_bytes()
    rc, out, err = _invoke(
        "sign",
        project,
        monkeypatch,
        **_sign_args(project, validate=str(validator_input), json=True),
    )
    assert rc == 0, err or out
    typed = _payload(out)
    assert typed["signs_key"] is True
    assert typed["logical_id"] == _SIGN_LOGICAL
    assert typed["second_approval"] == 0
    assert signoff.read_bytes() == before
    assert len(fake.calls) == 1

    # A different evidence snapshot is not a current sign-off; the read-only
    # face refuses and still writes nothing.
    rc, out, _ = _invoke(
        "sign",
        project,
        monkeypatch,
        stdin=json.dumps(envelope),
        stdin_flag=True,
        **_sign_args(project, json=True),
    )
    assert rc == 0, out
    assert _payload(out)["signoff_status"] == "existing"
    assert _payload(out)["model_called"] is False
    assert len(fake.calls) == 1

    validator_input.write_text(
        json.dumps(
            {
                "material": _sign_material(),
                "current_evidence": {"verified": [], "unverified": []},
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    rc, out, _ = _invoke(
        "sign",
        project,
        monkeypatch,
        **_sign_args(project, validate=str(validator_input), json=True),
    )
    assert rc == 2
    assert _payload(out)["signs_key"] is False
    assert signoff.read_bytes() == before


def test_sign_continue_writes_no_signoff_and_typed_apply_refuses_key_signoff(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, key_dir = _sign_project(tmp_path)
    fake = _answer_backend("continue")
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: fake)
    rc, out, err = _invoke(
        "sign",
        project,
        monkeypatch,
        stdin=json.dumps(_sign_envelope("sign-continue")),
        stdin_flag=True,
        **_sign_args(project, json=True),
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["conclusion"] == "continue"
    assert payload["signoff_status"] == "not-required"
    assert payload["handoff"]["signoff_writes"] == 0
    assert not (key_dir / "evidence" / "review" / "sign-final.md").exists()

    # A typed key-signoff file can never be consumed as an authority change.
    signoff = key_dir / "evidence" / "review" / "sign-final.md"
    signoff.write_text(
        "product_type: key-signoff\nrecord_version: 2\ndp: dp-sign-key\n"
        "conclusion: finalize\n",
        encoding="utf-8",
        newline="\n",
    )
    points = project / ".mw" / "decide-points.json"
    before = points.read_bytes() if points.exists() else None
    import argparse

    for var in decide_signoff.AGENT_SESSION_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    args = argparse.Namespace(
        subcommand="decide",
        decide_action="dp",
        dp_action="apply",
        project=str(project),
        sign_file=str(signoff),
        json=False,
    )
    out_io, err_io = io.StringIO(), io.StringIO()
    with redirect_stdout(out_io), redirect_stderr(err_io):
        rc = mw.cmd_decide(args)
    assert rc == 2
    assert "key-signoff" in err_io.getvalue() or "typed product" in err_io.getvalue()
    assert "nothing was written" in err_io.getvalue()
    assert (points.read_bytes() if points.exists() else None) == before


# ─────────────────────────────────────────────────────────────────────────────
# T24 sign producer admission and dry-run regressions.


def _sign_tree_bytes(project: pathlib.Path) -> dict[str, bytes]:
    return {
        str(item.relative_to(project)): item.read_bytes()
        for item in project.rglob("*")
        if item.is_file()
    }


@pytest.mark.parametrize("legacy_shape", [False, True])
@pytest.mark.parametrize("actor", ["worker", "self-pm", "unbound", "no-preparation"])
def test_sign_refuses_unproven_producers_without_model_or_writes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, actor: str, legacy_shape: bool
) -> None:
    project, _key_dir = _sign_project(tmp_path)
    envelope = _sign_envelope(f"sign-refused-{actor}")
    worker_task = None
    if actor in ("worker", "self-pm"):
        worker_task = _write_worker_runtime(project, owner=_SIGN_KEY)
        if actor == "worker":
            envelope["meta"]["initiator_role"] = "coding"
    elif actor == "unbound":
        _index_path(project).unlink()
    if actor == "no-preparation" or legacy_shape:
        envelope.pop("preparation")
    backend_calls = _no_backend(monkeypatch)
    before = _sign_tree_bytes(project)
    rc, out, err = _invoke(
        "sign", project, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, worker_task=worker_task,
        **_sign_args(project, json=True),
    )
    assert rc == 2, out or err
    assert backend_calls == []
    assert _sign_tree_bytes(project) == before


@pytest.mark.parametrize("conclusion", ["finalize", "continue", "user-confirm"])
def test_prepared_pm_sign_returns_the_real_same_call_answers(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, conclusion: str
) -> None:
    project, key_dir = _sign_project(tmp_path)
    backend = _answer_backend(conclusion)
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    envelope = _sign_envelope(f"prepared-{conclusion}")
    rc, out, err = _invoke(
        "sign", project, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, **_sign_args(project, json=True),
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert len(backend.calls) == 1
    assert payload["basis_id"] == "b-primary"
    assert payload["answers"][_business_question_id("dp-sign-key")]["value"] == conclusion
    assert payload["answers"]["basis_id"]["value"] == "b-primary"
    assert payload["second_approval"] == 0
    assert decide_signoff.signoff_path(project, _SIGN_KEY).exists() == (conclusion == "finalize")
    record = decision_signoff_result.read_result(key_dir, envelope["meta"]["logical_id"])
    assert record is not None
    assert record.conclusion == conclusion
    if conclusion != "finalize":
        assert payload["handoff"]["kind"] == conclusion
        assert payload["handoff"]["signoff_writes"] == 0


@pytest.mark.parametrize("retry", [False, True])
def test_sign_dry_run_stdin_and_retry_have_zero_side_effects(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, retry: bool
) -> None:
    project, key_dir = _sign_project(tmp_path)
    logical = "dry-run-result"
    if retry:
        # Direct typed-record fixture; this does not claim producer authorization.
        material = _sign_material()
        record = decision_signoff_result.build_result(
            key_dir, key=_SIGN_KEY, logical_id=logical,
            decision_id=f"dp-sign-key:{logical}", conclusion="finalize",
            material=material, facts=decide_signoff.collect(project, _SIGN_KEY),
            transport="fake", model="fake-model", confidence_source="unknown",
            initiator_role="pm", task_key="task-1", snapshot_material=material,
        )
        decision_signoff_result.write_result(
            key_dir, record, redact=decision.known_secret_redactor()
        )
    backend_calls = _no_backend(monkeypatch)
    before = _sign_tree_bytes(project)
    rc, out, err = _invoke(
        "sign", project, monkeypatch,
        stdin=json.dumps(_sign_envelope(logical)), stdin_flag=True,
        **_sign_args(project, json=True, dry_run=True, retry_write=logical if retry else None),
    )
    assert rc == 0, err or out
    assert backend_calls == []
    assert _sign_tree_bytes(project) == before


@pytest.mark.parametrize("damage", ["worker", "unbound", "stale-basis"])
def test_sign_retry_checks_actual_actor_and_current_basis_before_writing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    project, key_dir = _sign_project(tmp_path)
    logical = "retry-admission"
    material = _sign_material()
    (key_dir / "spec.md").write_text(
        "| AC-001 | original acceptance |\n", encoding="utf-8", newline="\n"
    )
    # A direct typed-record fixture exercises retry admission, without claiming
    # that this fixture was produced by an authorized formal CLI request.
    record = decision_signoff_result.build_result(
        key_dir, key=_SIGN_KEY, logical_id=logical,
        decision_id=f"dp-sign-key:{logical}", conclusion="finalize",
        material=material, facts=decide_signoff.collect(project, _SIGN_KEY),
        transport="fake", model="fake-model", confidence_source="unknown",
        initiator_role="pm", task_key="task-1", snapshot_material=material,
    )
    decision_signoff_result.write_result(
        key_dir, record, redact=decision.known_secret_redactor()
    )
    worker_task = None
    if damage == "worker":
        worker_task = _write_worker_runtime(project, owner=_SIGN_KEY)
    elif damage == "unbound":
        _index_path(project).unlink()
    else:
        (key_dir / "spec.md").write_text(
            "| AC-001 | changed acceptance |\n", encoding="utf-8", newline="\n"
        )
    backend_calls = _no_backend(monkeypatch)
    before = _sign_tree_bytes(project)
    rc, out, err = _invoke(
        "sign", project, monkeypatch, worker_task=worker_task,
        **_sign_args(project, json=True, retry_write=logical),
    )
    assert rc == 2, out or err
    assert backend_calls == []
    assert _sign_tree_bytes(project) == before


# T26 pm gate entry: the real PM CLI entries (prepare / stage-close material).
# Child processes inherit the test process as their live claim (ppid), exactly
# like the PM extension invoking mw.py.
# ─────────────────────────────────────────────────────────────────────────────

def _pm_cli_run(*argv, cwd=None):
    env = {**os.environ}
    env.pop("PI_WORKER_TASK", None)
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1")
    return subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(PACKAGE_DIR / "mw.py"), *argv],
        cwd=str(cwd or PACKAGE_DIR), env=env, text=True, encoding="utf-8",
        capture_output=True, check=False,
    )


def _pm_cli_project(tmp_path):
    root = tmp_path / "project"
    _autopilot_config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    owner = "owner"
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc/_index.parallel").write_text(
        f"| {owner} | active | EXECUTE | {claim} | - | test | now |\n", encoding="utf-8")
    (root / ".agenticdoc/goal.md").write_text("# Deliver the agreed feature\n", encoding="utf-8")
    target = _autopilot_roadmap.roadmap_path(root)
    target.write_text(
        "## Stage 1: Integration\n> goal: Ship the verified feature\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        f"| {owner} | implement | - |\n", encoding="utf-8")
    st = _autopilot_conductor.ConductorState(
        _autopilot_conductor.timeline.Timeline(
            _autopilot_conductor.timeline.timeline_path(root)), None)
    _autopilot_conductor._create_stage_confirm_gate(
        root, st, _autopilot_roadmap.load_roadmap(target).stages[0])
    trigger = [g for g in _autopilot_gates.enumerate(_autopilot_conductor.gates_dir(root))
               if g.historical and g.kind == "stage-confirm"][-1]
    book = json.loads((PACKAGE_DIR / "decide_cases/dp-gate-approve.json").read_text(encoding="utf-8"))["book"]
    book_path = root / ".agenticdoc/_autopilot/gate-book.json"
    book_path.parent.mkdir(parents=True, exist_ok=True)
    book_path.write_text(json.dumps({"dp": "dp-gate-approve", "book": book}, ensure_ascii=False),
                         encoding="utf-8", newline="\n")
    return root, owner, claim, trigger, book_path, target


def test_autopilot_gate_prepare_cli_binds_the_current_pm_once(tmp_path):
    root, owner, _claim, trigger, book_path, target = _pm_cli_project(tmp_path)
    before = target.read_bytes()
    result = _pm_cli_run(
        "autopilot", "gate", "prepare", "--project", str(root), "--key", owner,
        "--trigger", trigger.id, "--book", str(book_path))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    prepared = _autopilot_gates.parse(_autopilot_conductor.gates_dir(root) / (payload["gate_id"] + ".md"))
    assert prepared.historical is False and prepared.transport == "pending"
    assert prepared.matter_ref == payload["matter_ref"]
    assert payload["sidecar"].endswith(".json")
    assert pathlib.Path(payload["sidecar"]).is_file()
    assert target.read_bytes() == before
    assert _autopilot_gates.parse(trigger.path).status == "pending"
    replay = _pm_cli_run(
        "autopilot", "gate", "prepare", "--project", str(root), "--key", owner,
        "--trigger", trigger.id, "--book", str(book_path))
    assert replay.returncode == 0 and json.loads(replay.stdout)["gate_id"] == prepared.id


def test_autopilot_gate_run_cli_is_reachable_and_refuses_an_unreadable_book(tmp_path):
    root, owner, _claim, trigger, _book_path, target = _pm_cli_project(tmp_path)
    before = target.read_bytes()
    result = _pm_cli_run(
        "autopilot", "gate", "run", "--project", str(root), "--key", owner,
        "--trigger", trigger.id, "--book", str(root / "missing-book.json"))
    assert result.returncode == 1
    assert "unreadable prepared book" in result.stderr
    assert target.read_bytes() == before
    assert _autopilot_gates.parse(trigger.path).status == "pending"


def _pm_cli_sign_key(project, key, material, logical_id="logical-cli-t26"):
    key_dir = project / ".agenticdoc" / key
    (key_dir / "evidence" / "review").mkdir(parents=True, exist_ok=True)
    decide_archive.append_decide(
        decide_signoff.archive_path(project), dp="dp-QG", key=key, task_key="task-cli-t26",
        trigger_id=logical_id, state={"schema_version": 2, "decision_point": "dp-QG"},
        questions_version="q-0123abcd", available=True,
        answer={"q-verdict": {"value": "pass", "confidence": 0.9}},
        authority="binding", acted=True, actual_action="record the QG pass verdict",
        mode="auto", transport="timi-decisions", model="jev-latest", confidence_source="api")
    facts = decide_signoff.collect(project, key)
    record = decision_signoff_result.build_result(
        key_dir, key=key, logical_id=logical_id,
        decision_id=f"{decision_signoff_result.DP_ID}:{logical_id}", conclusion="finalize",
        material=material, facts=facts, transport="timi-decisions", model="jev-latest",
        confidence_source="api", task_key="task-cli-t26", initiator_role="pm",
        snapshot_material=material)
    decision_signoff_result.write_result(key_dir, record, redact=decision.known_secret_redactor())
    text = decide_signoff.render(facts, "finalize", None, key, "-", result=record)
    decide_signoff.write_signoff(project, key, text)
    return key_dir


def test_autopilot_stage_close_material_cli_writes_only_a_current_submission(tmp_path):
    root = tmp_path / "project"
    _autopilot_config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    owner = "key-cli-t26"
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc/_index.parallel").write_text(
        f"| {owner} | active | EXECUTE | {claim} | - | test | now |\n", encoding="utf-8")
    target = _autopilot_roadmap.roadmap_path(root)
    target.write_text(
        "## Stage 1: Integration\n> goal: Ship the verified feature\n> status: running\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        f"| {owner} | implement | - |\n", encoding="utf-8")
    material = {
        "delivery_goal": "deliver the CLI material producer",
        "actual_completion": "producer and its current-evidence check landed",
        "verification_evidence": {"verified": ["pytest"], "unverified": []},
        "unfinished_impact": [],
    }
    _pm_cli_sign_key(root, owner, material)
    submission = root / ".agenticdoc/_autopilot/stage-close-submission.json"
    submission.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1, "stage": 1, "source": "pm-current",
        "submitted_at": "2026-11-09T00:00:00+00:00",
        "key_signoffs": {owner: {"matter": material,
                                 "evidence": material["verification_evidence"]}},
    }
    submission.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    result = _pm_cli_run("autopilot", "stage-close-material", "--project", str(root),
                         "--stage", "1", "--key", owner, "--input", str(submission))
    assert result.returncode == 0, result.stderr
    written = _autopilot_closure.stage_close_material_path(root, 1)
    assert written.is_file()
    assert _autopilot_closure.stage_close_check(root, 1, [owner]).ok is True
    before = written.read_bytes()
    payload["source"] = "record.material"
    submission.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    refused = _pm_cli_run("autopilot", "stage-close-material", "--project", str(root),
                          "--stage", "1", "--key", owner, "--input", str(submission))
    assert refused.returncode == 1 and written.read_bytes() == before



def test_autopilot_family_cli_is_reachable_and_refuses_an_unreadable_book(tmp_path):
    root, owner, _claim, _trigger, _book_path, target = _pm_cli_project(tmp_path)
    before = target.read_bytes()
    result = _pm_cli_run(
        "autopilot", "family", "run", "--project", str(root), "--key", owner,
        "--family", "goal-adoption", "--book", str(root / "missing-family-book.json"))
    assert result.returncode == 1
    assert "unreadable prepared book" in result.stderr
    assert target.read_bytes() == before


def test_autopilot_halted_recovery_cli_reads_a_view_without_a_source(tmp_path):
    root, owner, _claim, _trigger, _book_path, target = _pm_cli_project(tmp_path)
    before = target.read_bytes()
    result = _pm_cli_run(
        "autopilot", "halted-recovery", "view", "--project", str(root), "--key", owner)
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False and payload["reason"]
    assert target.read_bytes() == before


# ---------------------------------------------------------------------------
# T23 bound actor: the real process/key/task identity gates every prepared
# request before credentials, the replay lookup, the ledger and the model.
# The PM's independent actor-before counterexample (meta initiator_role='pm' in
# an unbound process or an unrelated worker) is refused here.
# ---------------------------------------------------------------------------


def _assert_no_prepared_failure(
    project: pathlib.Path, fake: FakeCalls, *, before_events: int
) -> None:
    assert fake.prepared == []
    assert fake.decide == []
    assert len(_lifecycle_events(project)) == before_events


def test_unbound_process_cannot_claim_pm_from_the_meta(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    _index_path(tmp_path).unlink()
    before = len(_lifecycle_events(tmp_path))

    def credential_read(*args, **kwargs):
        raise AssertionError("credentials must not be read before the actor proof")

    monkeypatch.setattr(mw, "_decide_config_snapshot", credential_read)
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps(_envelope("dp-pm-steer", "unbound-pm")),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    payload = _payload(out)
    assert payload["reason"] == "actor-unbound"
    assert payload["available"] is False
    assert payload["business_decisions"] == 0
    assert payload["record_start"] == "not-recorded"
    _assert_no_prepared_failure(tmp_path, fake, before_events=before)


def test_worker_cannot_pretend_to_be_the_pm(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    before = len(_lifecycle_events(tmp_path))
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps(_envelope("dp-pm-steer", "worker-as-pm", key="key-worker")),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
        worker_task=_worker_task_path(tmp_path),
    )
    assert rc == 2
    payload = _payload(out)
    assert payload["reason"] == "role-forbidden"
    assert payload["business_decisions"] == 0
    _assert_no_prepared_failure(tmp_path, fake, before_events=before)


def test_pm_cannot_impersonate_the_workers_own_judgment(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    before = len(_lifecycle_events(tmp_path))
    envelope = _envelope("dp-w-check-task", "pm-as-worker", key="key-1")
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
        worker_task=None,
    )
    assert rc == 2
    payload = _payload(out)
    assert payload["reason"] == "role-forbidden"
    _assert_no_prepared_failure(tmp_path, fake, before_events=before)


@pytest.mark.parametrize(
    "claim",
    [
        f"other-window.invalid:{os.getpid()}",
        f"{socket.gethostname()}:{99999999}",
    ],
)
def test_foreign_or_dead_claim_is_not_the_pm(
    claim: str,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeCalls,
) -> None:
    _index_path(tmp_path).unlink()
    _bind_pm_claim(tmp_path, claim=claim)
    before = len(_lifecycle_events(tmp_path))
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps(_envelope("dp-QG", "foreign-claim")),
        stdin_flag=True, dp="dp-QG", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert _payload(out)["reason"] == "actor-unbound"
    _assert_no_prepared_failure(tmp_path, fake, before_events=before)


def test_retired_id_is_still_refused_before_any_actor_binding(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    _index_path(tmp_path).unlink()
    before = len(_lifecycle_events(tmp_path))
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps(_envelope("dp-w-type", "retired-no-actor")),
        stdin_flag=True, dp="dp1-dispatch-type", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "retired" in out
    assert _payload(out)["reason"] == "entry-unavailable"
    _assert_no_prepared_failure(tmp_path, fake, before_events=before)


def test_replay_requires_the_same_live_actor(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    envelope = _envelope("dp-pm-steer", "replay-actor")
    rc, _, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0
    assert len(fake.prepared) == 1
    before = len(_lifecycle_events(tmp_path))
    _index_path(tmp_path).unlink()
    _bind_pm_claim(tmp_path, claim=f"{socket.gethostname()}:{99999999}")
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-pm-steer", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert _payload(out)["reason"] == "actor-unbound"
    assert _payload(out)["replayed"] is False
    assert len(fake.prepared) == 1
    assert len(_lifecycle_events(tmp_path)) == before


def test_worker_runtime_must_match_its_own_task_run_and_queue(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    _write_worker_runtime(tmp_path, queue_status="done")
    before = len(_lifecycle_events(tmp_path))
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps(_envelope("dp-w-check-task", "queue-mismatch")),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert "queue" in _payload(out)["detail"]
    _assert_no_prepared_failure(tmp_path, fake, before_events=before)

    _write_worker_runtime(tmp_path, run_status="done")
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps(_envelope("dp-w-check-task", "run-mismatch")),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert _payload(out)["reason"] == "actor-unbound"
    assert len(fake.prepared) == 0
    assert len(_lifecycle_events(tmp_path)) == before

    _write_worker_runtime(tmp_path, role="review")
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps(_envelope("dp-w-check-task", "type-mismatch")),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert _payload(out)["reason"] == "role-forbidden"
    assert len(fake.prepared) == 0
    assert len(_lifecycle_events(tmp_path)) == before


def test_the_workers_own_check_task_stays_legal_and_fire_and_forget(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, fake: FakeCalls
) -> None:
    envelope = _envelope("dp-w-check-task", "worker-own-check")
    rc, out, err = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["available"] is True
    assert payload["acted"] is False
    assert payload["business_decisions"] == 1
    assert len(fake.prepared) == 1
    assert fake.prepared[0]["actor_role"] == "worker"
    assert fake.prepared[0]["logical_id"] == "worker-own-check"


# Registered autopilot dispatch types are legitimate worker card types. Their
# lifecycle role mirrors the TS `dp3TaskType` (write/edit tool -> coding, else
# research); they never enter the lifecycle enum as a raw dispatch type.
_FRAMEWORK_CARD_ROLES = {
    "roadmap-writer": "coding",
    "phase-writer": "coding",
    "verifier": "research",
    "reviewer": "research",
    "repair": "coding",
    "rag-research": "research",
    "vision": "coding",
    "decide_prepare": "research",
}


@pytest.mark.parametrize(
    ("card_type", "expected_role"), sorted(_FRAMEWORK_CARD_ROLES.items())
)
def test_registered_framework_types_bind_to_their_lifecycle_role(
    card_type: str,
    expected_role: str,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeCalls,
) -> None:
    """AC-003: no registered framework worker type is lost to the actor gate."""
    _write_worker_runtime(tmp_path, role=card_type)
    envelope = _envelope("dp-w-check-task", f"framework-{card_type}")
    envelope["meta"]["initiator_role"] = expected_role
    rc, out, err = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
    )
    assert rc == 0, err or out
    payload = _payload(out)
    assert payload["available"] is True
    assert payload["business_decisions"] == 1
    assert len(fake.prepared) == 1
    assert fake.prepared[0]["actor_role"] == "worker"
    assert fake.prepared[0]["logical_id"] == f"framework-{card_type}"


@pytest.mark.parametrize(
    ("card_type", "submitted_role"),
    [
        ("vision", "research"),
        ("verifier", "coding"),
        ("roadmap-writer", "review"),
    ],
)
def test_framework_type_still_requires_the_real_lifecycle_role(
    card_type: str,
    submitted_role: str,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeCalls,
) -> None:
    """Normalisation identifies the role; the meta declaration must still match."""
    _write_worker_runtime(tmp_path, role=card_type)
    before = len(_lifecycle_events(tmp_path))
    envelope = _envelope("dp-w-check-task", f"mismatch-{card_type}")
    envelope["meta"]["initiator_role"] = submitted_role
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    assert _payload(out)["reason"] == "role-forbidden"
    _assert_no_prepared_failure(tmp_path, fake, before_events=before)


@pytest.mark.parametrize(
    "card_type", ["fallback", "decision", "pm", "not-a-registered-type"]
)
def test_unregistered_fallback_retired_or_pm_types_stay_unbound(
    card_type: str,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeCalls,
) -> None:
    """AC-003: no fallback bucket, alias or PM value becomes a worker role."""
    _write_worker_runtime(tmp_path, role=card_type)
    before = len(_lifecycle_events(tmp_path))
    rc, out, _ = _invoke(
        "run", tmp_path, monkeypatch,
        stdin=json.dumps(_envelope("dp-w-check-task", f"bad-type-{card_type}")),
        stdin_flag=True, dp="dp-w-check-task", dp_id=None, request_file=None, book=None,
    )
    assert rc == 2
    payload = _payload(out)
    assert payload["reason"] == "actor-unbound"
    assert "type" in payload["detail"]
    _assert_no_prepared_failure(tmp_path, fake, before_events=before)


def _cli_decide_run(
    project: pathlib.Path,
    dp_id: str,
    envelope: dict,
    *,
    worker_task: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    env.pop("PI_WORKER_TASK", None)
    if worker_task is not None:
        env["PI_WORKER_TASK"] = str(worker_task)
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1")
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            str(PACKAGE_DIR / "mw.py"),
            "decide",
            "run",
            dp_id,
            f"--project={project}",
            "--stdin",
            "--json",
        ],
        cwd=str(PACKAGE_DIR),
        env=env,
        input=json.dumps(envelope),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_direct_parent_bridge_claim_is_accepted_in_a_real_child_process(
    tmp_path: pathlib.Path,
) -> None:
    """The CLI child's PPID is the claimed PM window (T19 bridge convention)."""
    envelope = _envelope("dp-pm-steer", "bridge-child")
    envelope["material"].pop("task_goal")
    result = _cli_decide_run(tmp_path, "dp-pm-steer", envelope)
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["reason"] == "input-incomplete"
    assert "task_goal" in result.stdout
    assert "actor-unbound" not in result.stdout
    assert "role-forbidden" not in result.stdout


def test_direct_parent_worker_run_pid_is_accepted_in_a_real_child_process(
    tmp_path: pathlib.Path,
) -> None:
    task = _worker_task_path(tmp_path)
    run = json.loads((task.parent / "run.json").read_text(encoding="utf-8"))
    assert run["pid"] == os.getpid()
    envelope = _envelope("dp-w-check-task", "worker-child")
    envelope["material"].pop("completed")
    result = _cli_decide_run(tmp_path, "dp-w-check-task", envelope, worker_task=task)
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["reason"] == "input-incomplete"
    assert "completed" in result.stdout
    assert "actor-unbound" not in result.stdout
    assert "role-forbidden" not in result.stdout
