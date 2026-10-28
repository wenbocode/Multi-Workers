"""Freeze original source bytes and run named tests with isolated credentials/HOME."""
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

key = pathlib.Path(__file__).resolve().parent.parent
root = key.parent.parent
package = root / "packages/multi-workers"
if sys.argv[1] == "baseline":
    target = key / "evidence/baseline"
    target.mkdir(parents=True, exist_ok=True)
    rows = {}
    for name in ("decision_monitor.py", "mw.py"):
        data = (package / name).read_bytes()
        copy = target / name
        if copy.exists():
            raise RuntimeError("baseline already frozen; refusing overwrite")
        copy.write_bytes(data)
        rows[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "crlf": data.count(b"\r\n")}
    (target / "hashes.json").write_text(json.dumps(rows, indent=2), encoding="utf-8", newline="\n")
    for label, args in (("status", ["status", "--porcelain=v1"]), ("diff", ["diff", "--", "packages/multi-workers/decision_monitor.py", "packages/multi-workers/mw.py"])):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
        (target / (label + ".raw")).write_bytes(result.stdout)
    print(json.dumps(rows))
else:
    label = sys.argv[1]
    files = sys.argv[2:]
    assert files and all(re.fullmatch(r"test_[A-Za-z0-9_]+\.py(?:::[A-Za-z0-9_]+)?", name) for name in files)
    out = key / "evidence/runs" / label
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="monitor-restart-isolated-") as tmp:
        home = pathlib.Path(tmp) / "home"
        home.mkdir()
        env = {k: v for k, v in os.environ.items() if not any(word in k.upper() for word in ("SECRET", "TOKEN", "API_KEY", "CREDENTIAL", "PROXY")) and k not in ("PI_WORKER_TASK", "MW_MONITOR_BROWSER", "MW_MONITOR_BROWSER_PROFILE")}
        env.update(HOME=str(home), USERPROFILE=str(home), PI_CODING_AGENT_DIR=str(home / "agent"), APPDATA=str(home / "appdata"), LOCALAPPDATA=str(home / "local"), PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        rows = []
        for name in files:
            log_name = name.replace("::", "__")
            argv = [sys.executable, "-X", "utf8", "-m", "pytest", "-q", "-s", name]
            start = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with (out / (log_name + ".stdout.log")).open("wb") as stdout, (out / (log_name + ".stderr.log")).open("wb") as stderr:
                result = subprocess.run(argv, cwd=package, env=env, stdout=stdout, stderr=stderr, timeout=180, check=False)
            row = {"argv": argv, "cwd": str(package), "start_utc": start, "end_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "exit_code": result.returncode}
            rows.append(row)
            print(json.dumps(row))
            print((out / (log_name + ".stdout.log")).read_text(encoding="utf-8"), end="")
            print((out / (log_name + ".stderr.log")).read_text(encoding="utf-8"), end="", file=sys.stderr)
        (out / "metadata.json").write_text(json.dumps(rows, indent=2), encoding="utf-8", newline="\n")
        sys.exit(1 if any(row["exit_code"] for row in rows) else 0)
