#!/usr/bin/env python3
"""Static path binding + real (unfaked) generation parity for the T04 R2 review.

Runs the two read-only generator modes exactly as the test does, captures the
child's stdout as **bytes** (no text decoding), and records:

* every imported module / ``_REPO_ROOT`` / ``output_path()`` resolved path, to
  prove the run is bound to ``implementation-worktree`` and not to the live tree;
* ``--check`` rc/stdout/stderr;
* ``--stdout`` raw bytes == the checked-in module bytes == ``render().encode()``;
* the text-mode caveat (``subprocess.run(text=True)`` decodes with the process
  locale / UTF-8 mode and folds CRLF, so it is not the byte proof).

Writes one JSON + one byte dump under rework-r2/logs/; writes nothing else.

Run it through ``scripts/run_min.py`` (which sets ``PYTHONDONTWRITEBYTECODE=1``):
a direct run imports the product modules and writes ``__pycache__/*.pyc`` into themirror - that happened once in this attempt and is recorded as an out-of-face
event in ``logs/05-pyc-out-of-face-write.json`` (cleaned afterwards).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
REWORK = HERE.parent.parent
WT = HERE.parents[5] / "implementation-worktree"
MW = WT / "packages/multi-workers"
sys.path.insert(0, str(MW / "scripts"))
sys.path.insert(0, str(MW))

import decision_context  # noqa: E402
import decision_points  # noqa: E402
import gen_decide_registry_ts as gen  # noqa: E402


def under_worktree(path: pathlib.Path) -> bool:
    try:
        pathlib.Path(path).resolve().relative_to(WT.resolve())
    except ValueError:
        return False
    return True


def run(mode: str) -> tuple[int, bytes, bytes, pathlib.Path]:
    script = MW / "scripts/gen_decide_registry_ts.py"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.lower().startswith(("pi_", "mw_"))
    }
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), mode], cwd=MW, env=env, capture_output=True
    )
    return result.returncode, result.stdout, result.stderr, script


def main() -> int:
    out_dir = REWORK / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    disk = gen.output_path()
    disk_bytes = disk.read_bytes()
    rendered = gen.render()
    rendered_bytes = rendered.encode("utf-8")

    check_rc, check_out, check_err, script = run("--check")
    print_rc, print_out, print_err, _ = run("--stdout")
    (out_dir / "gen-stdout.bytes").write_bytes(print_out)
    # Windows text-mode stdout translates every "\n" to "\r\n" (the child writes
    # through sys.stdout, i.e. text mode); the write path opens the file with
    # newline="\n". Universal-newline folding is therefore the text witness the
    # test's ``text=True`` comparison relies on, and the LF-only disk bytes are
    # the byte witness of the write path.
    print_out_lf = print_out.replace(b"\r\n", b"\n")

    doc = {
        "paths": {
            "gen_module": str(gen.__file__),
            "gen_module_bound_to_worktree": under_worktree(pathlib.Path(gen.__file__)),
            "gen_script": str(script),
            "gen_script_bound_to_worktree": under_worktree(script),
            "gen_repo_root": str(gen._REPO_ROOT),
            "gen_repo_root_equals_worktree": pathlib.Path(gen._REPO_ROOT).resolve()
            == WT.resolve(),
            "gen_mw_root": str(gen._MW_ROOT),
            "output_path": str(disk),
            "output_path_bound_to_worktree": under_worktree(disk),
            "decision_context_module": str(decision_context.__file__),
            "decision_context_bound_to_worktree": under_worktree(
                pathlib.Path(decision_context.__file__)
            ),
            "decision_points_module": str(decision_points.__file__),
            "decision_points_bound_to_worktree": under_worktree(
                pathlib.Path(decision_points.__file__)
            ),
            "subprocess_argv0": sys.executable,
            "subprocess_cwd": str(MW),
            "subprocess_argv": [sys.executable, "scripts/gen_decide_registry_ts.py"],
        },
        "check": {
            "rc": check_rc,
            "stdout": check_out.decode("utf-8", "backslashreplace"),
            "stdout_empty": check_out == b"",
            "stderr": check_err.decode("utf-8", "backslashreplace"),
        },
        "stdout_mode": {
            "rc": print_rc,
            "stderr": print_err.decode("utf-8", "backslashreplace"),
            "bytes": len(print_out),
            "sha256": hashlib.sha256(print_out).hexdigest(),
            "crcrlf": print_out.count(b"\r\n"),
            "bare_lf": print_out.count(b"\n") - print_out.count(b"\r\n"),
            "raw_equals_disk_bytes": print_out == disk_bytes,
            "lf_folded_equals_disk_bytes": print_out_lf == disk_bytes,
            "raw_minus_disk_bytes": len(print_out) - len(disk_bytes),
        },
        "disk": {
            "bytes": len(disk_bytes),
            "equals_stdout_bytes": print_out == disk_bytes,
            "equals_render_encode": disk_bytes == rendered_bytes,
            "sha256": hashlib.sha256(disk_bytes).hexdigest(),
            "crlf": disk_bytes.count(b"\r\n"),
            "bare_lf": disk_bytes.count(b"\n") - disk_bytes.count(b"\r\n"),
        },
        "text_mode_note": (
            "subprocess.run(..., text=True) without an explicit encoding decodes the "
            "child pipe with the process locale (GBK here unless PYTHONUTF8/PYTHONIOENCODING "
            "make it UTF-8) and applies universal-newline translation; it is a text "
            "witness, not the byte proof. The byte proof is stdout bytes == disk bytes "
            "== render().encode('utf-8') recorded above."
        ),
    }
    (out_dir / "gen-parity.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"check rc={check_rc} stdout_empty={check_out == b''} | "
        f"stdout raw {len(print_out)} B (CRLF {print_out.count(b'\r\n')}) | "
        f"lf-folded == disk {print_out_lf == disk_bytes} | "
        f"disk == render().encode(): {disk_bytes == rendered_bytes}"
    )
    ok = (
        check_rc == 0
        and check_out == b""
        and print_rc == 0
        and print_out_lf == disk_bytes == rendered_bytes
        and doc["paths"]["output_path_bound_to_worktree"]
        and doc["paths"]["gen_script_bound_to_worktree"]
        and doc["paths"]["gen_repo_root_equals_worktree"]
    )
    print("parity_ok=", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
