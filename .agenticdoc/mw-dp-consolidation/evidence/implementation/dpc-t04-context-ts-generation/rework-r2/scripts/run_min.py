#!/usr/bin/env python3
"""Run one command in the minimal, evidence-local environment of this R2 task.

Usage: python run_min.py <log-name> <argv...>

- HOME/USERPROFILE/TEMP/TMP point at rework-r2/env (no live user config);
- provider/worker/project config env (PI_*, MW_*, *_API_KEY, *_TOKEN, ...) is
  dropped, so a test cannot inherit a live provider or worker identity;
- PYTHONDONTWRITEBYTECODE=1 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1;
- stdout/stderr + rc are captured verbatim to rework-r2/logs/<log-name>.log.

Read-only towards the product tree except what the command itself writes.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
REWORK = HERE.parent.parent
MW = HERE.parents[5] / "implementation-worktree/packages/multi-workers"

DROP = re.compile(
    r"^(PI_|MW_|TIMI|OPENAI|ANTHROPIC|GOOGLE|GEMINI|AZURE|DASHSCOPE|DEEPSEEK|"
    r"MOONSHOT|QWEN|ZHIPU|OPENROUTER|GROQ|MISTRAL|PROVIDER|WORKER|PROJECT_|"
    r"PYTHONSTARTUP|PYTHONPATH|PYTEST_ADDOPTS)",
    re.IGNORECASE,
)
KEEP_SECRET_SHAPED = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)


def minimal_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if DROP.match(key) or KEEP_SECRET_SHAPED.search(key):
            continue
        env[key] = value
    home = REWORK / "env" / "home"
    temp = REWORK / "env" / "temp"
    home.mkdir(parents=True, exist_ok=True)
    temp.mkdir(parents=True, exist_ok=True)
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        TEMP=str(temp),
        TMP=str(temp),
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONIOENCODING="utf-8",
        # The original test compares `subprocess.run(..., text=True).stdout` with
        # the artifact's UTF-8 text without passing an explicit encoding, so the
        # parent-side pipe decoding uses the process locale. On this Windows box
        # that is GBK (see logs/00a-...), which cannot decode the em dash and the
        # Chinese notes in the generated module. UTF-8 mode is the documented
        # environment of this run, not a change to the test's assertion.
        PYTHONUTF8="1",
    )
    return env


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    name = sys.argv[1]
    argv = sys.argv[2:]
    env = minimal_env()
    result = subprocess.run(
        argv, cwd=MW, env=env, capture_output=True, text=True, errors="backslashreplace"
    )
    log = REWORK / "logs" / f"{name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"# cmd: {' '.join(argv)}\n"
        f"# cwd: {MW}\n"
        f"# HOME/USERPROFILE={env['HOME']}\n# TEMP={env['TEMP']}\n"
        f"# PYTHONDONTWRITEBYTECODE={env['PYTHONDONTWRITEBYTECODE']} "
        f"PYTEST_DISABLE_PLUGIN_AUTOLOAD={env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']} "
        f"PYTHONUTF8={env['PYTHONUTF8']} PYTHONIOENCODING={env['PYTHONIOENCODING']}\n"
        f"# rc={result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n"
    )
    log.write_text(body, encoding="utf-8")
    print(f"{name}: rc={result.returncode} log={log}")
    if result.returncode != 0:
        print("--- stdout ---")
        print(result.stdout)
        print("--- stderr ---")
        print(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
