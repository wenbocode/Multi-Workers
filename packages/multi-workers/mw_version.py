"""Read the active Multi-Workers installation, releases and project runtimes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""


def read_record(path: Path) -> dict:
    try:
        value = json.loads(read_text(path))
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def runtime(path: Path) -> dict:
    path = path.resolve()
    root = next((parent for parent in path.parents if parent.name == "packages"), None)
    root = root.parent if root else path
    manifest = read_record(root / "release-manifest.json")
    return {"path": str(path), "root": str(root), "release": root.name,
            "commit": manifest.get("recovery_commit") or manifest.get("commit"),
            "base_commit": manifest.get("base_commit")}


def entry_runtime(entry: Path, seen: frozenset[Path] = frozenset()) -> dict:
    entry = entry.resolve()
    result = {"entry": str(entry)}
    if entry in seen or len(seen) == 8:
        return result
    script = read_text(entry)
    # Managed Windows launchers quote their Python entry or delegate to the
    # user-level launcher. Reading the path keeps this command side-effect free.
    match = re.search(r'"([^"\r\n]*[\\/](?:mw\.py|mw\.cmd))"', script, re.I)
    if not match:
        return {**result, **runtime(entry)} if entry.name == "mw.py" else result
    target = match[1].replace("%~dp0", str(entry.parent) + os.sep)
    target = re.sub(r"%([^%]+)%", lambda value: os.environ.get(value[1], value[0]), target)
    resolved = Path(target)
    if resolved.suffix.lower() == ".cmd":
        return {**entry_runtime(resolved, seen | {entry}), **result}
    return {**result, **runtime(resolved)} if resolved.is_file() else result


def process_runtimes(pids: set[int]) -> dict[int, dict]:
    if os.name != "nt" or not pids:
        return {}
    where = " OR ".join(f"ProcessId={pid}" for pid in sorted(pids))
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             f"Get-CimInstance Win32_Process -Filter '{where}' -ErrorAction Stop | "
             "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=5, check=True, errors="replace",
        )
        records = json.loads(result.stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    known = {}
    for record in records if isinstance(records, list) else [records]:
        if not isinstance(record, dict):
            continue
        command = record.get("CommandLine") or ""
        match = re.search(r'["\s]([A-Za-z]:[\\/][^"\r\n]*?'
                          r'[\\/]packages[\\/](?:coding-agent[\\/](?:dist[\\/]cli\.js|src[\\/]cli\.ts)|'
                          r'multi-workers[\\/]mw\.py))'
                          r'(?=["\s]|$)', command, re.I)
        if match:
            known[record["ProcessId"]] = runtime(Path(match[1]))
    return known


def installed_releases(folder: Path) -> list[dict]:
    if not folder.is_dir():
        return []
    return [runtime(path) for release in sorted(folder.iterdir())
            if (path := release / "packages" / "multi-workers" / "mw.py").is_file()]


def registered_windows(home: Path) -> list[dict]:
    now = time.time_ns() // 1_000_000
    hostname = socket.gethostname().casefold()
    windows = []
    for file in sorted((home / ".mw-pm-channel").glob("*/*/*.json")):
        project = file.parent.parent.name
        if not re.fullmatch(r"[a-f0-9]{64}", project) or not re.fullmatch(r"[a-f0-9]{64}", file.stem):
            continue
        heartbeat = read_record(file)
        claim, binding, at = (heartbeat.get(field) for field in ("claim", "binding", "at"))
        if (not isinstance(claim, str) or hashlib.sha256(claim.encode()).hexdigest() != file.stem
                or not isinstance(binding, str)
                or not re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", binding)
                or type(at) is not int or not 0 <= now - at < 15_000):
            continue
        match = re.fullmatch(r"([^:]+):([1-9][0-9]*)", claim)
        pid = int(match[2]) if match and match[1].casefold() == hostname else None
        windows.append({"project_ref": project, "key": file.parent.name, "claim": claim, "pid": pid})
    return windows


def versions(project: Path, home: Path) -> dict:
    global_root = home / ".local" / "share" / "multi-workers"
    global_entry = global_root / "bin" / ("mw.cmd" if os.name == "nt" else "mw")
    terminal_entry = shutil.which("mw")
    terminal = entry_runtime(Path(terminal_entry)) if terminal_entry else None
    default = entry_runtime(global_entry) if global_entry.is_file() else None
    ext = Path(os.environ.get("PI_CODING_AGENT_DIR") or home / ".pi" / "agent") / "extensions"
    installed = read_text(ext / ".mw-py-path").strip()
    override = os.environ.get("MW_PY")
    builds = installed_releases(global_root / "releases")
    local_builds = installed_releases(project / ".mw" / "releases")
    meta = read_record(project / ".mw" / "serve.meta")
    registered = registered_windows(home)
    claims = {}
    for line in read_text(project / ".agenticdoc" / "_index.parallel").splitlines():
        cells = [part.strip() for part in line.strip("|").split("|", 5)]
        if len(cells) >= 4 and cells[1] == "active":
            match = re.fullmatch(r"[^:]+:([1-9]\d*)", cells[3])
            if match:
                claims[cells[0]] = int(match[1])
    backend_pid = meta.get("pid")
    code_dir = meta.get("code_dir")
    pids = set(claims.values())
    pids.update(window["pid"] for window in registered if window["pid"] is not None)
    if type(backend_pid) is int and backend_pid > 0:
        pids.add(backend_pid)
    observed = process_runtimes(pids)
    backend = None
    if isinstance(code_dir, str) and code_dir:
        backend = {"pid": backend_pid, **runtime(Path(code_dir) / "mw.py"), **observed.get(backend_pid, {}),
                   "observed": backend_pid in observed}
    extension = runtime(Path(installed)) if installed else None
    pm = [{"key": key, "pid": pid, **observed.get(pid, {})} for key, pid in claims.items()]
    registered = [{**window, **observed.get(window["pid"], {})} for window in registered]
    default_root = default.get("root") if default else None
    for item in (terminal, extension, backend, *pm, *registered):
        if item and item.get("root") and default_root:
            item["uses_global_default"] = Path(item["root"]) == Path(default_root)
    return {
        "project": str(project),
        "terminal": terminal,
        "global": default,
        "global_extension": extension,
        "environment_override": runtime(Path(override)) if override else None,
        "backend": backend,
        "pm": pm,
        "registered_windows": registered,
        "installed_count": len(builds),
        "installed": builds,
        "project_release_count": len(local_builds),
        "project_releases": local_builds,
    }


def display(label: str, item: dict | None) -> None:
    if not item:
        print(f"{label}: unavailable")
        return
    release = item.get("release", "runtime unavailable")
    commit = item.get("commit")
    if commit:
        release += f" ({commit[:10]})"
    elif base_commit := item.get("base_commit"):
        release += f" (base {base_commit[:10]})"
    if item.get("uses_global_default") is False:
        release += " [different from global default]"
    if item.get("observed") is False:
        release += " [service record; live process unverified]"
    print(f"{label}: {release}" if label else f"- {release}")
    if item.get("entry"):
        print(f"  entry: {item['entry']}")
    if item.get("path"):
        print(f"  path:  {item['path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, prog="mw version")
    parser.add_argument("command", nargs="?", choices=("version",), help=argparse.SUPPRESS)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--pi-window", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--pi-cli", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--pi-extension", help=argparse.SUPPRESS)
    parser.add_argument("--pi-extension-hash", help=argparse.SUPPRESS)
    parser.add_argument("--pi-python", help=argparse.SUPPRESS)
    args = parser.parse_args()
    project = args.project.resolve()
    project = next((folder for folder in (project, *project.parents)
                    if (folder / ".agenticdoc").is_dir()), project)
    report = versions(project, Path.home())
    if args.pi_window is not None:
        display("全局默认 MW", report["global"] or report["global_extension"])
        current = runtime(args.pi_cli) if args.pi_cli else {}
        default = report["global"] or report["global_extension"]
        if current.get("root") and default and default.get("root"):
            current["uses_global_default"] = Path(current["root"]) == Path(default["root"])
        display(f"当前 pi 窗口（PID {args.pi_window}）", current)
        if args.pi_extension:
            suffix = f" ({args.pi_extension_hash[:12]})" if args.pi_extension_hash else ""
            print(f"  扩展: {args.pi_extension}{suffix}")
        if args.pi_python:
            display("当前窗口使用的 MW Python", runtime(Path(args.pi_python)))
        windows = report["registered_windows"]
        print(f"已注册在线窗口（{len(windows)}）")
        for window in windows:
            label = f"{window['key']} · {window['project_ref'][:8]} · {window['claim']}"
            display(label, window)
        return
    if args.json:
        print(json.dumps(report, indent=2))
        return
    display("Terminal", report["terminal"])
    display("Global default", report["global"])
    display("Global pi extension", report["global_extension"])
    if report["environment_override"]:
        display("MW_PY override", report["environment_override"])
    print(f"Project: {report['project']}")
    display("Backend", report["backend"])
    for pm in report["pm"]:
        display(f"PM {pm['key']} (PID {pm['pid']})", pm)
    print(f"Installed global releases ({report['installed_count']}):")
    for item in report["installed"]:
        display("", item)
    if report["project_releases"]:
        print(f"Project release copies ({report['project_release_count']}):")
        for item in report["project_releases"]:
            display("", item)


if __name__ == "__main__":
    main()
