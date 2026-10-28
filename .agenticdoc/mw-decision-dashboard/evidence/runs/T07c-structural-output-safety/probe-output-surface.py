"""T07c probe: the output policy is output-only.

Folds the same fixture twice (no redactor vs the known-secret redactor) and
prints, as machine-checkable metrics:

* internal projection (opaque ids, identities, decision ids, keys, sign-off/gate
  joins, stage states, call counts, page selection) - must be identical;
* occurrences of the credential in the serialized page/detail payloads and in
  the warnings - must be 0 with the redactor;
* the per-record structural omission marks and flags.

Run from the repo root:
    python .agenticdoc/mw-decision-dashboard/evidence/runs/T07c-structural-output-safety/probe-output-surface.py
Exit code 0 means every invariant held.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "packages" / "multi-workers"))

import test_decision_history as th  # noqa: E402  (path set up above)


class _NoAgentSession:
    """Minimal stand-in for pytest's monkeypatch in ``_add_signoff``."""

    def delenv(self, name: str, raising: bool = False) -> None:
        del raising
        os.environ.pop(name, None)


def _internals(snapshot: "th.history.HistorySnapshot") -> dict[str, object]:
    """Everything a join/id derives from - redaction must not touch it."""
    return {
        record.opaque_id: {
            "identity": record.identity,
            "decision_id": record.decision_id,
            "dp": record.dp,
            "key": record.key,
            "task_key": record.task_key,
            "signoff_key": (record.signoff or {}).get("key"),
            "gates": [gate["id"] for gate in record.gates],
            "stages": {name: fact.state for name, fact in record.stages.items()},
            "logical_calls": record.call_counts.logical_calls,
            "http_attempts": record.call_counts.actual_http_attempts,
        }
        for record in snapshot.records
    }


def _serialized(snapshot: "th.history.HistorySnapshot") -> str:
    page = snapshot.page(limit=history_max())
    return json.dumps(
        {
            "page": [record.as_dict() for record in page.records],
            "detail": [record.as_dict(detail=True) for record in snapshot.records],
            "warnings": list(snapshot.warnings),
        }
    )


def history_max() -> int:
    return 200


def main() -> int:
    failures: list[str] = []
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="t07c-probe-"))
    try:
        root, shaped, unreachable, model_only = th._structural_fixture(
            workdir, _NoAgentSession()
        )
        plain = th._snapshot(root)
        safe = th._snapshot(root, redact=th.REDACTOR)

        plain_internals = _internals(plain)
        safe_internals = _internals(safe)
        print("records without redactor :", len(plain.records))
        print("records with redactor    :", len(safe.records))
        print("internal projection equal:", plain_internals == safe_internals)
        if plain_internals != safe_internals:
            failures.append("internal projection changed under the output policy")
            print("  without:", json.dumps(plain_internals, sort_keys=True))
            print("  with   :", json.dumps(safe_internals, sort_keys=True))

        plain_text = _serialized(plain)
        safe_text = _serialized(safe)
        print("credential occurrences without redactor:", plain_text.count(th.SECRET))
        print("credential occurrences with redactor   :", safe_text.count(th.SECRET))
        if safe_text.count(th.SECRET) != 0:
            failures.append("the credential is still echoed with a redactor")
        if plain_text.count(th.SECRET) == 0:
            failures.append("the fixture no longer carries the credential (vacuous probe)")

        page_safe = th._snapshot(root, redact=th.REDACTOR).page(key=th.SECRET)
        print("page(key=<credential>) with redactor   :", page_safe.total)
        if page_safe.total != 1:
            failures.append("the internal key filter no longer selects the record")

        print("structural_withheld per identity:")
        for record in safe.records:
            print(
                "  ",
                record.identity,
                "->",
                record.redaction.structural_withheld,
                "flag:",
                "structural-secret-withheld" in record.flags,
            )
        for identity in ("decision|" + shaped, "decision|" + unreachable, "decision|" + model_only):
            record = next(item for item in safe.records if item.identity == identity)
            if record.redaction.structural_withheld <= 0:
                failures.append(f"{identity}: no structural omission was marked")
            if "structural-secret-withheld" not in record.flags:
                failures.append(f"{identity}: omission flag missing")
            if record.redaction.enabled is not True:
                failures.append(f"{identity}: marks claim redaction is disabled")

        print("no-redactor failure mode (existing contract):")
        bare = next(item for item in plain.records if item.identity == "decision|" + shaped)
        print("  structural values kept:", bare.key == th.SECRET, bare.model.value == th.SECRET)
        print("  free text withheld   :", bare.signoff["claim"] is None)
        if bare.redaction.structural_withheld != 0:
            failures.append("no-redactor mode must not report structural omissions")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
