"""CLI-level evidence: a real "no open P0" dp25 book passes ``mw decide book check``.

Hermetic: the whole run happens in a tmp dir, ``HOME``/``USERPROFILE`` point at
it, every credential-ish env var is removed, and no real archive/credential is
read. The book is built from the real producer (``decide_signoff.collect`` over
an ``decide_archive`` fixture), never hand-written. Also checks that the editor
scaffold for dp25 is still refused (``[]`` for ``p0_open`` is legal, the rest of
the scaffold is not).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

MW = pathlib.Path("packages/multi-workers").resolve()
sys.path.insert(0, str(MW))

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402

KEY = "k-t05h-cli"
DP25 = "dp25-signoff-conclusion"
CRED_SUFFIXES = ("_API_KEY", "_TOKEN", "_KEY", "_SECRET", "_PASSWORD")


def run_cli(args: list[str], cwd: pathlib.Path, home: pathlib.Path) -> subprocess.CompletedProcess:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().endswith(CRED_SUFFIXES)
        and name not in ("TIMI_API_TOKEN", "PI_CODING_AGENT", "AI_AGENT", "PI_WORKER_TASK")
    }
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, str(MW / "mw.py"), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> None:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t05h-cli-"))
    project = tmp / "proj"
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
    book = {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": DP25,
        "state": state,
        "notes": {"evidence": {p: "cmd: true" for p in dpts.REQUIRED_STATE_FIELDS[DP25]}},
    }
    book_path = tmp / "book-dp25-no-p0.json"
    book_path.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("producer p0_open:", state["p0_open"], "rows_total:", state["rows_total"])
    good = run_cli(["decide", "book", "check", str(book_path), "--project", str(project), "--json"], tmp, tmp)
    print("real no-P0 book  -> exit", good.returncode)
    print("  stdout:", " ".join(good.stdout.split())[:400])
    print("  stderr:", " ".join(good.stderr.split())[:200])

    scaffold = books.scaffold_book(DP25)
    scaffold_path = tmp / "scaffold-dp25.json"
    scaffold_path.write_text(json.dumps(scaffold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bad = run_cli(["decide", "book", "check", str(scaffold_path), "--project", str(project), "--json"], tmp, tmp)
    payload = json.loads(bad.stdout) if bad.stdout.strip().startswith("{") else {}
    codes = sorted({f"{issue['code']}:{issue['path']}" for issue in payload.get("issues", [])})
    print("dp25 scaffold    -> exit", bad.returncode)
    print("  p0_open issue:", [c for c in codes if "p0_open" in c])
    print("  first issues:", codes[:6])
    print("  home used:", tmp)


main()
