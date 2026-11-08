"""Codex PM entry point for card-backed development and independent verification."""
from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import tempfile

import mw_common
from autopilot import config, gates, roadmap, state

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) or value.endswith(".") or Path(value).is_reserved():
        raise ValueError(f"Invalid key or card name: {value!r}")
    return value


def child(root: Path, *parts: str) -> Path:
    """Coordination artifacts are local to this key, including existing junctions."""
    path = root.joinpath(*parts)
    if path.resolve() != path:
        raise ValueError(f"Linked coordination path: {path}")
    return path


def key_state(project: Path, key: str, claim_id: str | None = None) -> dict:
    matches = [row for row in state.read_index(project) if row["key"] == key]
    if len(matches) != 1:
        raise ValueError(f"Expected one registered key: {key}")
    row = matches[0]
    if claim_id is not None:
        claim = row["claim_id"]
        if claim != claim_id:
            raise ValueError("Claim changed; recover the current key before writing")
        pm = child(project, ".agenticdoc", key, "pm-state.md").read_text(encoding="utf-8")
        if (row["status"] != "active" or row["phase"].upper() not in {"EXECUTE", "VERIFY"}
                or f"- Claim-Id: {claim}" not in pm.splitlines()
                or f"- Phase: {row['phase'].upper()}" not in pm.splitlines()):
            raise ValueError("An active, matching AgenticTask claim in EXECUTE or VERIFY is required")
        host, _, pid = claim.rpartition(":")
        if (host.casefold() != socket.gethostname().casefold() or not pid.isdecimal()
                or mw_common.process_alive_state(int(pid)) != "dead"):
            raise ValueError(f"Key belongs to another PM: {claim}")
    return row


def acceptance_argv(text: str) -> list[str]:
    sections = re.findall(r"^## 验收命令[ \t]*\r?\n\s*```json[ \t]*\r?\n(.*?)\r?\n```[ \t]*$",
                          text, re.DOTALL | re.MULTILINE)
    if len(sections) != 1:
        raise ValueError("The card must declare one JSON argv block under ## 验收命令")
    argv = json.loads(sections[0])
    if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and "\x00" not in v for v in argv) or not argv[0]:
        raise ValueError("Acceptance command must be a nonempty JSON array of strings")
    return argv


def queue(project: Path) -> list[dict]:
    data = mw_common.parse_workers_queue(mw_common.workers_path(project))
    if data["unparsable"]:
        raise ValueError("Unreadable MW queue rows; inspect mw doctor before continuing")
    return data["rows"]


def run_binding(task_dir: Path) -> dict | None:
    task = child(task_dir, "task.md")
    output = child(task_dir, "output.md")
    if not task.is_file() or not output.is_file() or not output.stat().st_size:
        return None
    return {"task_sha256": mw_common.sha256_eol_normalized(task),
            "output_sha256": mw_common.sha256_eol_normalized(output)}


def snapshot(key_dir: Path, task: str, row: dict | None) -> dict:
    task_dir = child(key_dir, "workers", identifier(task))
    task_file = child(task_dir, "task.md")
    if row and Path(row["task_path"]).resolve() != task_file:
        raise ValueError(f"Unexpected queue path for {task}")
    queue_status = row["status"] if row else None
    artifacts = {}
    for name in ("task.md", "output.md", "report.md", "trace.log", "worker.log", "run.json"):
        path = child(task_dir, name)
        if path.is_file():
            artifacts[name] = str(path)
    product_status = mw_common.read_run_status(task_dir)
    if "run.json" in artifacts and not product_status:
        product_status = "unreadable"
    evidence = child(key_dir, "evidence", "codex-pm", task)
    runs = sorted(evidence.glob("*/result.json"))
    verification = "unverified"
    if runs:
        last = json.loads(child(evidence, runs[-1].parent.name, "result.json").read_text(encoding="utf-8"))
        if not isinstance(last, dict):
            raise ValueError(f"Invalid verification record: {runs[-1]}")
        verification = last.get("verdict", "incomplete")
        statuses = {s for s in (queue_status, product_status) if s}
        if verification == "passed" and (last.get("binding") != run_binding(task_dir) or statuses != {"done"}):
            verification = "stale"
    card = mw_common.read_task_header_scalar(task_file.read_text(encoding="utf-8"), "card_path") if task_file.is_file() else None
    return {"task": task, "card": card, "queue": queue_status, "run": product_status, "artifacts": artifacts,
            "verification": verification, "checks": [str(path) for path in runs]}


@contextlib.contextmanager
def dispatch_lock(project: Path, task: str):
    # A process dying during a dispatch releases this OS lock. The stable lock
    # file is deliberately kept so all waiters continue locking the same inode.
    lock = child(project, ".mw", "codex-pm", task + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def dispatch(project: Path, key: str, stem: str, task: str, claim_id: str) -> dict:
    card = child(project, ".agenticdoc", key, "tasks", stem + ".md")
    acceptance_argv(card.read_text(encoding="utf-8"))
    key_dir = card.parent.parent
    task_file = child(key_dir, "workers", task, "task.md")
    with dispatch_lock(project, task):
        owner = key_state(project, key, claim_id)
        if owner["phase"].upper() != "EXECUTE":
            raise ValueError("Dispatch requires EXECUTE")
        existing = next((r for r in queue(project) if r["task_key"] == task), None)
        if existing:
            result = snapshot(key_dir, task, existing)
            digest = mw_common.read_task_header_scalar(task_file.read_text(encoding="utf-8"), "card_sha256")
            if mw_common.sha256_eol_normalized(card) != digest or result["card"] != f"tasks/{card.name}":
                raise ValueError("Task identity already exists with a different card; use a new card for rework")
            return {"reused": True, **result}
        # A framework claim command is short-lived. Its exited PID cannot keep
        # an enabled conductor from dispatching the same plan under an ap- ID.
        plan = roadmap.roadmap_path(project)
        if plan.is_file() and config.load_config(project).get("enabled"):
            if key in roadmap.stage_of_key(roadmap.load_roadmap(plan)):
                raise ValueError("Autopilot owns this roadmap key; use status to follow the conductor's workers")
        workspace = mw_common.workspace_root(mw_common.load_target_config(project))
        payload = {"key": key, "task_key": task, "card_path": str(card), "cli": "pi", "type": "coding",
                   "description": f"Implement tasks/{card.name}. Record changes, checks and residual issues in output.md.\n"
                                  f"PM verification cwd: {json.dumps(workspace)}"}
        proc = subprocess.run(["node", str(Path(__file__).with_name("codex_dispatch.mjs").resolve())],
                              input=json.dumps(payload), cwd=project, capture_output=True, encoding="utf-8", errors="replace")
        row = next((r for r in queue(project) if r["task_key"] == task), None)
        if proc.returncode or not row:
            raise ValueError((proc.stderr if proc.returncode else proc.stdout).strip() or "Dispatch did not enqueue a worker")
        return {"reused": False, "receipt": proc.stdout.strip(), **snapshot(key_dir, task, row)}


def verify(project: Path, key_dir: Path, task: str, claim_id: str, argv: list[str]) -> tuple[dict, int]:
    key_state(project, key_dir.name, claim_id)
    row = next((r for r in queue(project) if r["task_key"] == task), None)
    result = snapshot(key_dir, task, row)
    statuses = {s for s in (result["queue"], result["run"]) if s}
    task_dir = child(key_dir, "workers", task)
    binding = run_binding(task_dir)
    if statuses != {"done"} or not binding:
        raise ValueError("Verification requires a completed worker and nonempty output.md")
    task_text = (task_dir / "task.md").read_text(encoding="utf-8")
    if argv != acceptance_argv(task_text):
        raise ValueError("Verification argv differs from the dispatched acceptance command")
    cwd = mw_common.workspace_root(mw_common.load_target_config(project))
    pinned = re.findall(r"^PM verification cwd: (.+)$", task_text, re.MULTILINE)
    if len(pinned) != 1 or Path(json.loads(pinned[0])).resolve() != Path(cwd).resolve():
        raise ValueError("Verification workspace differs from the dispatched workspace")
    folder = child(key_dir, "evidence", "codex-pm", task)
    folder.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(dir=folder, prefix=f"{time.time_ns()}-"))
    log = evidence / "command.log"
    report = {"key": key_dir.name, "task": task, "argv": argv, "cwd": str(cwd), "binding": binding,
              "started": datetime.datetime.now(datetime.UTC).isoformat(), "verdict": "incomplete",
              "exit_code": None, "log": str(log)}
    destination = evidence / "result.json"
    tmp = evidence / "result.tmp"
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    os.replace(tmp, destination)
    with log.open("wb") as stream:
        try:
            code = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT).returncode
        except OSError as exc:
            stream.write(str(exc).encode("utf-8"))
            code = 127
    verdict = "passed" if code == 0 else "failed"
    latest = next((r for r in queue(project) if r["task_key"] == task), None)
    terminal = {s for s in (latest["status"] if latest else None, mw_common.read_run_status(task_dir)) if s}
    if binding != run_binding(task_dir) or terminal != {"done"}:
        verdict = "stale"
    try:
        key_state(project, key_dir.name, claim_id)
    except ValueError as exc:
        verdict = "stale"
        report["reason"] = str(exc)
    report.update(exit_code=code, verdict=verdict, finished=datetime.datetime.now(datetime.UTC).isoformat())
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    os.replace(tmp, destination)
    return {**report, "evidence": str(destination)}, 0 if verdict == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("dispatch", "status", "verify"):
        command = sub.add_parser(action)
        command.add_argument("--project", type=Path, default=Path.cwd())
        command.add_argument("--key", required=True)
        if action != "status":
            command.add_argument("--card", required=True, help="Task card filename stem under <key>/tasks/")
            command.add_argument("--claim-id", required=True, help="ClaimId returned by AgenticTask claim")
        if action == "verify":
            command.add_argument("argv", nargs=argparse.REMAINDER, help="-- PROGRAM ARG ... from the dispatched card")
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    key = identifier(args.key)
    key_dir = child(project, ".agenticdoc", key)
    owner = key_state(project, key)
    code = 0
    if args.action == "status":
        workers = {r["task_key"]: r for r in queue(project) if mw_common.worker_owner_key(r) == key}
        tasks = set(workers)
        for path in child(key_dir, "workers").glob("*/task.md"):
            tasks.add(path.parent.name)
        pending = gates.pending_gates(project / ".agenticdoc" / "_autopilot" / "gates")
        result = {"key": key, "phase": owner["phase"], "claim": owner["claim_id"], "pm_state": str(key_dir / "pm-state.md"),
                  "cards": sorted(str(p) for p in child(key_dir, "tasks").glob("*.md")),
                  "pending_gates": [{"id": g.id, "question": g.question, "path": str(g.path)} for g in pending if g.key == key],
                  "tasks": [snapshot(key_dir, task, workers.get(task)) for task in sorted(tasks)]}
    else:
        stem = identifier(args.card)
        task = f"pm-{len(key)}-{key}-{stem}"
        if args.action == "dispatch":
            result = dispatch(project, key, stem, task, args.claim_id)
        else:
            argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            result, code = verify(project, key_dir, task, args.claim_id, argv)
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, config.ConfigError, roadmap.RoadmapError, mw_common.TargetConfigError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)
