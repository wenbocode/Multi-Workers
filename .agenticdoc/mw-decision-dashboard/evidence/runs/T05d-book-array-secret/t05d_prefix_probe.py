"""Archived probe: what the *pre-fix* gate did with a credential inside a dp25 array.

The fix is already in the working tree, so the probe restores the pre-fix
``_check_secrets`` (flatten-based, string leaves only) in memory, then runs the
real dp25 producer state + a synthetic secret in ``escalated_reasons`` through
the observation seam with a ``FakeBackend``. No source file is modified and no
credential is real: the pre-fix gate is simulated, the send path is the real one.
"""

import json
import pathlib
import sys
import tempfile
from typing import Mapping

sys.path.insert(0, str(pathlib.Path("packages/multi-workers").resolve()))

import decision  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

import test_decision_input_contract_migration as t05c  # noqa: E402


def legacy_check_secrets(book: Mapping, state: Mapping):
    """Verbatim pre-fix logic (baseline sha256 4e6394a1…): only flat string leaves."""
    issues = []
    flat = books._flatten(state)
    for path, value in flat.items():
        if not isinstance(value, str) or not value:
            continue
        if decision._redact(value) != value:
            issues.append(
                books.Issue(
                    "book-secret", f"state.{path}", "credential-looking text; redact before sending"
                )
            )
    context = book.get("context") if isinstance(book.get("context"), Mapping) else {}
    for slot, content in context.items():
        for text in books._context_strings(content):
            if text and decision._redact(text) != text:
                issues.append(
                    books.Issue(
                        "book-secret",
                        f"context.{slot}",
                        "credential-looking text; redact before sending",
                    )
                )
                break
    return issues


def main() -> None:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t05d-probe-"))
    project, state = t05c.real_signoff_state(tmp)
    state["escalated_reasons"] = [f"escalated for {t05c.TEST_SECRET}"]
    assert dpts.state_field_issues(t05c.DP25, state) == (), "probe fixture must be legal"
    book = t05c._book(t05c.DP25, state)

    books._check_secrets = legacy_check_secrets  # simulate the pre-fix gate only
    pre_fix_issues = books.check_book(book, project_dir=project)

    root = tmp / "run"
    scope = t05c._scope(root)
    backend = decision.FakeBackend([t05c._ok(t05c._dp25_answers())])
    outcome = dpts.decide_for(
        t05c.DP25,
        state,
        project,
        client=t05c._client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=book, submission_id=t05c.SUB),
    )
    snapshots = t05c._of_kind(decision_wire.test_wire_sink(root), "book-snapshot")
    sent_state = backend.calls[0]["state"] if backend.calls else None
    result = {
        "pre_fix_book_issues": [[issue.code, issue.path] for issue in pre_fix_issues],
        "pre_fix_book_accepted": not pre_fix_issues,
        "outcome_status": outcome.status,
        "outcome_reason": outcome.escalated_reason,
        "backend_calls": len(backend.calls),
        "book_snapshots": len(snapshots),
        "secret_in_sent_state": bool(
            sent_state and t05c.TEST_SECRET in json.dumps(sent_state)
        ),
        "secret_in_snapshot": bool(
            snapshots and t05c.TEST_SECRET in ((snapshots[0].get("book") or {}).get("text") or "")
        ),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
