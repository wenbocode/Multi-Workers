"""T05k baseline probe: what the unmodified seam/contract does today.

Two questions, both printed as facts (no assertion, no fix):

N1  required missing / null / empty-string: is the refused candidate still
    stored as a ``book-snapshot`` with a ``book_ref``?
N5  dp25 ``p0_open``: does the typed contract bind the array shape (item type /
    item count / item bytes), or is the producer's element space unbounded?

Read-only: tmp projects, tmp HOME/auth, credential env removed, FakeBackend,
test-scope wire sink, no network.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
MW = REPO / "packages" / "multi-workers"
sys.path.insert(0, str(MW))

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

DP25 = "dp25-signoff-conclusion"
KEY = "k-t05k-probe"
SUB = "sub-t05k-probe"


def _hermetic(root: pathlib.Path) -> None:
    for name in tuple(os.environ):
        if name.upper().endswith(decision._CRED_ENV_SUFFIXES):
            os.environ.pop(name, None)
    os.environ["HOME"] = str(root)
    os.environ["USERPROFILE"] = str(root)
    decision_backends._auth_json_path = lambda: root / "no-auth.json"


def _rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _signoff_state(root: pathlib.Path) -> tuple[pathlib.Path, dict]:
    _hermetic(root)
    project = root / "proj"
    (project / ".agenticdoc" / KEY).mkdir(parents=True)
    decide_archive.append_decide(
        decide_signoff.archive_path(project),
        available=True,
        reason=None,
        answer={"x": {"value": 1}},
        authority="binding",
        escalated_reason=None,
        acted=True,
        actual_action="steer",
        dp="dp3-worker-clarify",
        key=KEY,
        task_key="task-1",
        trigger_id="t1",
        state={"schema_version": 2, "decision_point": "dp3-worker-clarify"},
        questions_version="q-0123abcd",
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    return project, decide_signoff.signoff_state(decide_signoff.collect(project, KEY), KEY)


def _run(project: pathlib.Path, root: pathlib.Path, state: dict, *, with_book: bool):
    scope_root = root / ("book" if with_book else "plain")
    redactor = decision.credential_redactor(
        extra_secrets=(), env={}, auth_path=pathlib.Path("no-such-auth.json")
    )
    scope = decision_wire.test_scope(
        scope_root,
        project_id=decision_wire.project_id_for(project),
        submission_id=SUB,
        redact=redactor,
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )
    backend = decision.FakeBackend(
        [
            decision.BackendOutcome(
                available=True,
                reason=None,
                retryable=False,
                answers={"q-conclusion": {"value": "continue", "confidence": 0.9}},
                latency_ms=1,
                detail="",
            )
        ]
    )
    client = decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=True), backend=backend, wire_scope=scope
    )
    book = None
    if with_book:
        book = {
            "schema_version": books.BOOK_SCHEMA_VERSION,
            "decision_point": DP25,
            "state": state,
            "notes": {"evidence": {p: "cmd: true" for p in dpts.REQUIRED_STATE_FIELDS[DP25]}},
        }
    observation = (
        dpts.Observation(scope=scope, book=book, submission_id=SUB) if with_book else None
    )
    outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=observation,
    )
    rows = _rows(decision_wire.test_wire_sink(scope_root))
    ends = [row for row in rows if row.get("kind") == "decision-end"]
    return outcome, backend, [row.get("kind") for row in rows], ends


def main() -> None:
    for case, mutate in (
        ("missing", lambda state: state.pop("p0_open", None)),
        ("null", lambda state: state.__setitem__("p0_open", None)),
        ("empty-string", lambda state: state.__setitem__("key", "  ")),
        ("legal-[]", lambda state: None),
    ):
        for with_book in (False, True):
            root = pathlib.Path(tempfile.mkdtemp())
            project, real = _signoff_state(root)
            state = dict(real)
            mutate(state)
            outcome, backend, kinds, ends = _run(project, root, state, with_book=with_book)
            print(
                f"N1 {case:12s} book={with_book!s:5s} -> {outcome.escalated_reason} "
                f"| calls={len(backend.calls)} | kinds={kinds}"
            )
            print(f"    snapshot_ref={outcome.snapshot_ref!r} detail={outcome.detail[:90]}")
            print(
                "    decision-end book_ref/archive/capture="
                f"{[(row.get('book_ref'), row.get('archive_state'), row.get('capture_status')) for row in ends]}"
            )

    print()
    print("N5 p0_open spec:", dpts.STATE_FIELD_DESCRIPTIONS["p0_open"])
    root = pathlib.Path(tempfile.mkdtemp())
    project, real = _signoff_state(root)
    samples = [
        ("[]", []),
        ("legal-id", ["dp8-scope-change"]),
        ("[1]", [1]),
        ("[None]", [None]),
        ("[{}]", [{}]),
        ("['<tbd>']", ["<tbd>"]),
        ("33 ids", [f"dp{i}-x" for i in range(33)]),
        ("129B item", ["x" * 129]),
    ]
    for label, value in samples:
        state = dict(real)
        state["p0_open"] = value
        typed = dpts.state_field_issues(DP25, state)
        book = {
            "schema_version": books.BOOK_SCHEMA_VERSION,
            "decision_point": DP25,
            "state": state,
            "notes": {"evidence": {p: "cmd: true" for p in dpts.REQUIRED_STATE_FIELDS[DP25]}},
        }
        book_issues = [(issue.code, issue.path) for issue in books.check_book(book)]
        print(f"N5 {label:12s} typed={typed} book={book_issues}")


main()
