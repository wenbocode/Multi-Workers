"""What does the seam emit for a missing-required vs a typed dp25 refusal?

Runs the same real-no-P0 dp25 state through ``decide_for`` (book path) for the
missing/typed cases and prints the wire event kinds plus the ``decision-end``
fields that describe the snapshot, so the report can state the pre-existing
behaviour instead of guessing.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

MW = pathlib.Path("packages/multi-workers")
sys.path.insert(0, str(MW))

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

DP25 = "dp25-signoff-conclusion"
KEY = "k-probe"
SUB = "sub-probe"


def events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    for case in ("missing", "null", "string"):
        root = pathlib.Path(tempfile.mkdtemp())
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
        state = decide_signoff.signoff_state(decide_signoff.collect(project, KEY), KEY)
        if case == "missing":
            state.pop("p0_open")
        elif case == "null":
            state["p0_open"] = None
        else:
            state["p0_open"] = "dp8-scope-change"
        book = {
            "schema_version": books.BOOK_SCHEMA_VERSION,
            "decision_point": DP25,
            "state": state,
            "notes": {"evidence": {p: "cmd: true" for p in dpts.REQUIRED_STATE_FIELDS[DP25]}},
        }
        redactor = decision.credential_redactor(
            extra_secrets=(), env={}, auth_path=pathlib.Path("no-such-auth.json")
        )
        scope = decision_wire.test_scope(
            root / "wire",
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
        outcome = dpts.decide_for(
            DP25,
            state,
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
        )
        sink = decision_wire.test_wire_sink(root / "wire")
        rows = events(sink)
        kinds = [row.get("kind") for row in rows]
        ends = [row for row in rows if row.get("kind") == "decision-end"]
        print(case, "->", outcome.escalated_reason, "| calls:", len(backend.calls))
        print("  detail:", outcome.detail)
        print("  event kinds:", kinds)
        print(
            "  decision-end book_ref/archive/capture:",
            [(row.get("book_ref"), row.get("archive_state"), row.get("capture_status")) for row in ends],
        )


main()
