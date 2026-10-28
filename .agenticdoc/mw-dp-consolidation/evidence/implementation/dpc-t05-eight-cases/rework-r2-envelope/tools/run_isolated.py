"""Isolated runner for this R2-envelope evidence: private HOME/TEMP/project.

Two modes (both never touch a product file):

* ``tool <name> [args...]``  - run ``tools/<name>.py`` in-process, with sockets
  denied, cwd = this evidence dir's private ``fixture/project``.
* ``exec --label L --cwd C -- <argv...>`` - run ``argv`` as a subprocess with the
  private environment, capture stdout/stderr/rc into ``logs/``.

Every mode sets ``PYTHONDONTWRITEBYTECODE=1``/``-B`` (asserted), ``PYTHONUTF8=1``
and drops credential/proxy variables, so no pyc is written, no real network,
provider, decision CLI or service is reachable from this harness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import runpy
import socket
import subprocess
import sys

assert sys.dont_write_bytecode, "run this harness with -B / PYTHONDONTWRITEBYTECODE=1"

TOOLS = pathlib.Path(__file__).resolve().parent
EVIDENCE = TOOLS.parent
KEY = EVIDENCE.parents[3]
WT = KEY / "implementation-worktree"
PKG = WT / "packages" / "multi-workers"
FIXTURE = EVIDENCE / "fixture"
LOGS = EVIDENCE / "logs"

#: The five T10 shared inputs: their bytes must be identical around every run of
#: the assigned suite (a shared-module writer would be a real regression, not a
#: product red).
T10_DEPS = (
    "decision_wire.py",
    "decision_lifecycle.py",
    "decision_task_state.py",
    "test_decision_context_lifecycle.py",
    "test_decision_task_state.py",
)

DROP = {
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_KEY",
    "TIMI_BASE_URL",
    "MW_DECIDE_API_KEY",
    "MW_DECISION_API_KEY",
    "PI_API_KEY",
    "PI_WORKER_TASK",
    "PI_CODING_AGENT_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
}


def private_dirs() -> dict[str, pathlib.Path]:
    names = ("home", "userprofile", "temp", "tmp", "tmpdir", "project", "appdata", "localappdata")
    out = {}
    for name in names:
        path = FIXTURE / name
        path.mkdir(parents=True, exist_ok=True)
        out[name] = path
    LOGS.mkdir(parents=True, exist_ok=True)
    return out


def private_env() -> dict[str, str]:
    dirs = private_dirs()
    env = {key: value for key, value in os.environ.items() if key.upper() not in DROP}
    env.update(
        {
            "HOME": str(dirs["home"]),
            "USERPROFILE": str(dirs["userprofile"]),
            "TEMP": str(dirs["temp"]),
            "TMP": str(dirs["tmp"]),
            "TMPDIR": str(dirs["tmpdir"]),
            "APPDATA": str(dirs["appdata"]),
            "LOCALAPPDATA": str(dirs["localappdata"]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONHASHSEED": "0",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
    )
    return env


def deny_network() -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("no real network is permitted in this isolated evidence run")

    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked


def run_tool(name: str, argv: list[str]) -> int:
    path = TOOLS / f"{name}.py"
    if not path.is_file():
        print(f"missing evidence tool {path}", file=sys.stderr)
        return 2
    os.environ.clear()
    os.environ.update(private_env())
    deny_network()
    dirs = private_dirs()
    os.chdir(dirs["project"])
    sys.argv = [f"{name}.py", *argv]
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def dep_window() -> dict[str, str]:
    return {
        f"packages/multi-workers/{name}": hashlib.sha256((PKG / name).read_bytes()).hexdigest()
        for name in T10_DEPS
    }


def run_exec(label: str, cwd: pathlib.Path, argv: list[str]) -> int:
    env = private_env()
    deps_before = dep_window()
    process = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    deps_after = dep_window()
    (LOGS / f"{label}.stdout").write_text(process.stdout, encoding="utf-8", newline="\n")
    (LOGS / f"{label}.stderr").write_text(process.stderr, encoding="utf-8", newline="\n")
    meta = {
        "source": "agent-report",
        "label": label,
        "argv": argv,
        "cwd": str(cwd),
        "rc": process.returncode,
        "env": sorted(key for key in env if not key.startswith("PYTHON")),
        "python": sys.version,
        "deps_before": deps_before,
        "deps_after": deps_after,
        "T10_dependency_window_stable": deps_before == deps_after,
    }
    (LOGS / f"{label}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"[{label}] rc={process.returncode}")
    return process.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    tool = sub.add_parser("tool")
    tool.add_argument("name")
    tool.add_argument("args", nargs="*")
    exe = sub.add_parser("exec")
    exe.add_argument("--label", required=True)
    exe.add_argument("--cwd", default=str(PKG))
    exe.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.mode == "tool":
        return run_tool(args.name, args.args)
    argv = list(args.argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        parser.error("exec needs a command after --")
    return run_exec(args.label, pathlib.Path(args.cwd), argv)


if __name__ == "__main__":
    raise SystemExit(main())
