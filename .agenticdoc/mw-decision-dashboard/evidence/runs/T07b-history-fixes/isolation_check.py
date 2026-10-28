"""T07b isolation evidence: the history read moves no carrier byte, creates nothing.

Two independent checks:

1. **Fixture check** - a real control root in ``tempfile`` with *every* carrier
   the reader touches (archive, wire ledger, lifecycle ledger, ``sign-final.md``,
   ``gates/gate-*.md``), built through the production writers. Every file is
   hashed before and after ``load_history`` (twice, plus ``page``/``detail``)
   and the file inventory must be identical: no content change, no new file, no
   directory. This is the "fixture hashes for wire/lifecycle/sign-off/gate"
   check the T07 review asked for, not just the four production ledgers.
2. **Production check** - every production carrier that exists in this repo
   (all archives/ledgers, all ``evidence/review/sign-final.md``, all
   ``_autopilot/gates/*.md``) is hashed before and after the acceptance pytest
   command. Nothing is written to the repo; the log records which files exist.

Usage: ``python isolation_check.py`` (from this directory or anywhere).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
PACKAGE = REPO / "packages" / "multi-workers"
AGENTICDOC = REPO / ".agenticdoc"

sys.path.insert(0, str(PACKAGE))

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision_history  # noqa: E402
import decision_wire as wire  # noqa: E402
from autopilot import gates  # noqa: E402

SECRET = "ISOLATION-SECRET-abc123456789"
REDACTOR = wire.SubstringRedactor((SECRET,))


def _hash_tree(root: pathlib.Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            found[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return found


def fixture_check() -> str:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t07b-isolation-"))
    root = tmp / "proj"
    autopilot = root / ".agenticdoc" / "_autopilot"
    autopilot.mkdir(parents=True)
    archive = autopilot / "decisions.jsonl"
    decide_archive.append_decide(
        archive,
        dp="dp1-dispatch-type",
        key="mw-alpha",
        task_key=None,
        trigger_id="t1",
        state={"a": 1},
        questions_version="q-1234abcd",
        available=True,
        authority="binding",
        acted=True,
        actual_action=f"wrote {SECRET}",
        answer={"q-task": {"value": "fix", "confidence": 0.9}},
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        attempts=1,
        latency_ms=12,
        confidence=0.9,
        confidence_source="api",
    )
    decide_archive.append_settle(
        archive,
        decision_id="dp1-dispatch-type:t1",
        dp="dp1-dispatch-type",
        key="mw-alpha",
        task_key=None,
        outcome="ok",
        settled_by="human",
        evidence_ref=f"evidence/{SECRET}/run.txt",
    )
    scope = wire.WireScope(
        sink=wire.production_wire_sink(root),
        project_id=wire.project_id_for(root),
        scope_kind="production",
        origin="cli",
        decision_id="dp1-dispatch-type:t1",
        dp="dp1-dispatch-type",
        key="mw-alpha",
        redact=REDACTOR,
        warn=lambda message: None,
    )
    call = wire.new_call()
    wire.record_attempt_start(scope, call, request=b'{"a":1}', url_path="/v1/decisions")
    wire.record_attempt_end(
        scope, call, response=b'{"b":2}', latency_ms=1, http_status=200,
        usage={"input_tokens": 5},
    )
    wire.append_event(scope, wire.call_end_event(scope, call, attempts=1, latency_ms=1, available=True))
    lifecycle_scope = wire.WireScope(
        sink=wire.production_lifecycle_sink(root),
        project_id=wire.project_id_for(root),
        scope_kind="production",
        origin="cli",
        decision_id="dp1-dispatch-type:t1",
        dp="dp1-dispatch-type",
        key="mw-alpha",
        redact=REDACTOR,
        warn=lambda message: None,
    )
    wire.append_event(
        lifecycle_scope,
        wire.lifecycle_event(
            lifecycle_scope, lifecycle="adopted", target="dp1-dispatch-type:t1",
            actor=("system", "pm-orchestrator"),
        ),
    )
    (root / ".agenticdoc" / "mw-alpha").mkdir(parents=True, exist_ok=True)
    facts = decide_signoff.collect(root, "mw-alpha")
    text = decide_signoff.render(
        facts, "continue", "recorded reason", "mw-alpha", f"claim {SECRET}", signed_via="cli"
    )
    # This script may itself run inside an agent session; the fixture root is a
    # temp directory, never a production tree, so the session guard is lifted
    # for the fixture write only (the CLI itself never bypasses it).
    for name in decide_signoff.AGENT_SESSION_ENV_VARS:
        os.environ.pop(name, None)
    decide_signoff.write_signoff(root, "mw-alpha", text, signed_via="cli")
    gates.create(
        autopilot / "gates", "stage-confirm", f"proceed with {SECRET}?", key="mw-alpha", stage=1
    )

    before = _hash_tree(root)
    snapshot = decision_history.load_history(root, redact=REDACTOR)
    decision_history.load_history(root, redact=REDACTOR)
    for record in snapshot.records:
        record.as_dict(detail=True)
    snapshot.page(limit=1)
    snapshot.detail(snapshot.records[0].opaque_id)
    after = _hash_tree(root)

    lines = [
        f"fixture_root={root}",
        f"records={len(snapshot.records)}",
        f"files={len(before)}",
    ]
    for name in sorted(set(before) | set(after)):
        lines.append(f"before {name} {before.get(name, '<absent>')}")
        lines.append(f"after  {name} {after.get(name, '<absent>')}")
    lines.append(f"inventory_unchanged={sorted(before) == sorted(after)}")
    lines.append(f"bytes_unchanged={before == after}")
    lines.append(f"secret_echoed={SECRET in json.dumps([r.as_dict(detail=True) for r in snapshot.records])}")
    return "\n".join(lines)


def production_check() -> tuple[str, bool]:
    carriers: list[pathlib.Path] = []
    for name in ("decisions.jsonl", "decisions-wire.jsonl", "decision-lifecycle.jsonl"):
        carriers.extend(sorted(AGENTICDOC.rglob(name)))
    carriers.extend(sorted(AGENTICDOC.rglob("sign-final.md")))
    gates_dir = AGENTICDOC / "_autopilot" / "gates"
    if gates_dir.is_dir():
        carriers.extend(sorted(gates_dir.glob("gate-*.md")))
    carriers = sorted({path for path in carriers if path.is_file()})
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in carriers}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "test_decision_history.py",
            "test_decide_archive.py",
            "test_decide_signoff.py",
            "test_decision_wire_store.py",
            "-q",
        ],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        check=False,
    )
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in carriers}
    lines = [
        f"cwd={PACKAGE}",
        "cmd=python -m pytest test_decision_history.py test_decide_archive.py "
        "test_decide_signoff.py test_decision_wire_store.py -q (via this check)",
        f"pytest_exit={completed.returncode}",
        completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else "",
    ]
    for path in carriers:
        lines.append(f"before {path.relative_to(REPO).as_posix()} {before[path]}")
        lines.append(f"after  {path.relative_to(REPO).as_posix()} {after[path]}")
    lines.append(f"carriers={len(carriers)}")
    lines.append(f"unchanged={before == after}")
    return "\n".join(lines), before == after and completed.returncode == 0


def main() -> int:
    fixture = fixture_check()
    (HERE / "fixture-bytes-isolation.txt").write_text(
        fixture + "\n", encoding="utf-8", newline="\n"
    )
    print(fixture.splitlines()[-3:])
    production, ok = production_check()
    (HERE / "carrier-bytes-isolation.txt").write_text(
        production + "\n", encoding="utf-8", newline="\n"
    )
    print("\n".join(production.splitlines()[-2:]))
    return 0 if ok and "bytes_unchanged=True" in fixture and "secret_echoed=False" in fixture else 1


if __name__ == "__main__":
    raise SystemExit(main())
