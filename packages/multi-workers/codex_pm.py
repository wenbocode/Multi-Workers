"""Codex PM entry point for card-backed development and independent verification."""
from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
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
import change_set
import decision_signoff_result
from autopilot import active_projection, config, contract_guard, gates, roadmap

if os.name == "nt":
    import msvcrt
else:
    import fcntl

LITE_WORKFLOW = "codex-lite"
LITE_PHASES = ("SPEC", "EXECUTE", "VERIFY", "DONE")
NO_CLAIM = "—"
SOURCE_EXCLUDES = {".git", ".agenticdoc", ".mw", ".pi", ".tmp", ".usage", "node_modules",
                   "__pycache__", ".pytest_cache", "dist", "coverage"}


def section(text: str, heading: str) -> str:
    stripped = re.sub(r"<!--[\s\S]*?-->", "", text)
    headings = list(re.finditer(r"^(#{1,2})[ \t]+(.+?)[ \t]*\r?$", stripped, re.MULTILINE))
    matches = [index for index, match in enumerate(headings) if match[1] == "##" and match[2] == heading]
    if len(matches) > 1:
        raise ValueError(f"Duplicate section: {heading}")
    if not matches:
        return ""
    position = matches[0]
    end = headings[position + 1].start() if position + 1 < len(headings) else len(stripped)
    return stripped[headings[position].end():end].strip()


def lite_document(key_dir: Path, *, ready: bool = False) -> tuple[str, dict[str, str], list[str]]:
    text = child(key_dir, "codex_doc.md").read_text(encoding="utf-8")
    metadata = {}
    visible = re.sub(r"<!--[\s\S]*?-->", "", text)
    for name in ("Workflow", "Key", "Phase", "Claim-Id", "Status"):
        matches = re.findall(r"^- " + re.escape(name) + r":[ \t]*(.*?)[ \t]*$", visible, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError(f"codex_doc.md must declare exactly one {name}")
        metadata[name] = matches[0]
    if (metadata["Workflow"] != LITE_WORKFLOW or metadata["Key"] != key_dir.name
            or metadata["Phase"] not in LITE_PHASES
            or metadata["Status"] not in {"active", "idle"}
            or metadata["Claim-Id"] != ("codex" if metadata["Status"] == "active" else NO_CLAIM)
            or (metadata["Phase"] == "DONE" and metadata["Status"] != "idle")):
        raise ValueError("Invalid Codex lightweight task metadata")
    criteria = re.findall(r"^- (AC-\d{3}):[ \t]*\S.*$", section(text, "验收标准"), re.MULTILINE)
    if len(set(criteria)) != len(criteria):
        raise ValueError("Duplicate acceptance criterion in codex_doc.md")
    if ready and (not criteria or any(not section(text, h) for h in ("目标", "范围", "接续须知"))):
        raise ValueError("codex_doc.md requires nonempty 目标/范围/验收标准/接续须知 and numbered AC-NNN")
    return text, metadata, criteria


def is_lite(key_dir: Path) -> bool:
    doc = child(key_dir, "codex_doc.md")
    return doc.is_file() and bool(re.search(r"^- Workflow:[ \t]*codex-lite[ \t]*$",
                                           re.sub(r"<!--[\s\S]*?-->", "", doc.read_text(encoding="utf-8")),
                                           re.MULTILINE))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def lite_transition(project: Path, key: str, action: str, phase: str | None = None) -> dict:
    """Own one key under the existing index lock, preserving every other row."""
    root = child(project, ".agenticdoc")
    key_dir = child(root, key)
    lock = child(project, ".mw", "index.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    mw_common.acquire_lock(lock, deadline_s=10)
    try:
        index = child(root, "_index.parallel")
        raw = index.read_bytes() if index.is_file() else b""
        lines = raw.decode("utf-8").splitlines(keepends=True)
        rows = active_projection.strict_rows_with_lines(lines)
        # Validate the entire active set before creating any task artifacts.
        active_projection.projection_text(row for _, row, _, _ in rows)
        matches = [entry for entry in rows if active_projection.normalize_key(entry[1]["key"]) == key.lower()]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous duplicate key: {key}")
        existing = matches[0] if matches else None
        journal = child(project, ".mw", "codex-pm", key.lower() + ".pending.json")
        recovered = False
        if journal.is_file():
            pending = json.loads(journal.read_text(encoding="utf-8"))
            actual = existing[1] if existing else None
            if not isinstance(pending, dict) or pending.get("key", "").lower() != key.lower():
                raise ValueError("Invalid Codex state recovery journal")
            if actual == pending.get("desired"):
                stored_key = actual["key"]
                atomic_text(child(root, stored_key, "codex_doc.md"), pending["document"])
                atomic_text(child(root, stored_key, "pm-state.md"), pending["stub"])
                active_projection.write_projection(project, active_projection.projection_text_from_lines(lines))
                journal.unlink()
                recovered = True
            elif actual == pending.get("previous"):
                journal.unlink()
            else:
                raise ValueError("Claim changed during partial-write recovery; refusing to overwrite another PM")
        stamp = datetime.datetime.now(datetime.UTC).isoformat()
        if existing is None:
            if action != "init":
                raise ValueError(f"Expected one registered key: {key}")
            if key_dir.exists():
                raise ValueError("Existing task directory cannot be adopted as codex-lite")
            template = child(root, "templates", "codex_doc.md")
            if not template.is_file():
                template = Path(__file__).with_name("templates") / "codex_doc.md"
            text = template.read_text(encoding="utf-8").replace("<key>", key)
            # Machine fields are initialized here, not inferred from prose.
            for name, value in {"Workflow": LITE_WORKFLOW, "Key": key, "Phase": "SPEC",
                                "Claim-Id": "codex", "Status": "active"}.items():
                if len(re.findall(r"^- " + re.escape(name) + r":.*$", text, re.MULTILINE)) != 1:
                    raise ValueError(f"Codex template requires one {name} machine field; update the project template")
                text = re.sub(r"^- " + re.escape(name) + r":.*$", f"- {name}: {value}", text, flags=re.MULTILINE)
            phase = "SPEC"
            status = "active"
            claim = "codex"
            cells = [key, status, phase, claim, NO_CLAIM, "Codex lightweight task", stamp]
        else:
            position, row, cells, ending = existing
            key = row["key"]
            key_dir = child(root, key)
            text, metadata, _ = lite_document(key_dir, ready=action in {"advance", "done"})
            if row["claim_id"] not in {"codex", NO_CLAIM, "", "-"}:
                raise ValueError("Claim changed; key belongs to another PM")
            if row["status"] == "active" and row["claim_id"] != "codex":
                raise ValueError("Active task is not claimed by Codex")
            if row["phase"] not in LITE_PHASES or len(cells) != 7:
                raise ValueError("Expected a seven-column Codex lightweight key")
            if action not in {"claim", "init"}:
                if any(metadata[field] != row[column] for field, column in
                       (("Phase", "phase"), ("Status", "status"), ("Claim-Id", "claim_id"))):
                    raise ValueError("Codex task state differs from index; run claim to recover")
                if row["status"] != "active" or row["claim_id"] != "codex":
                    raise ValueError("An active Codex claim is required")
            phase = phase or row["phase"]
            if row["phase"] == "DONE":
                if action == "init" or (action == "claim" and recovered):
                    return row
                raise ValueError("Completed tasks cannot be reclaimed or changed")
            if action == "advance" and LITE_PHASES.index(phase) < LITE_PHASES.index(row["phase"]):
                raise ValueError("Codex phase regression is not allowed")
            if action == "done":
                if row["phase"] != "VERIFY":
                    raise ValueError("Completion requires VERIFY")
                phase = "DONE"
            status = "idle" if action in {"done", "release"} else "active"
            claim = NO_CLAIM if status == "idle" else "codex"
            cells = list(cells)
            cells[1:4] = [status, phase, claim]
            cells[-1] = stamp
        for name, value in {"Phase": phase, "Status": status, "Claim-Id": claim}.items():
            text = re.sub(r"^- " + re.escape(name) + r":.*$", f"- {name}: {value}", text, flags=re.MULTILINE)
        stub = (f"# PM State: {key}\n\n- Key: {key}\n- Claim-Id: {claim}\n- Phase: init\n"
                f"- PM mode: codex\n- Workflow: {LITE_WORKFLOW}\n")
        rendered = "| " + " | ".join(cells) + " |"
        if existing is None:
            if not lines:
                lines = ["# Index Parallel\n\n| Key | Status | Phase | ClaimId | Deps | Desc | Updated |\n",
                         "|-----|--------|-------|---------|------|------|---------|\n"]
            if not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(rendered + "\n")
        else:
            lines[position] = rendered + ending
        projection = active_projection.projection_text_from_lines(lines)
        # Authority commits first; later IO failure is explicitly partial and
        # a durable, key-scoped journal repairs mirrors from that exact commit.
        desired = dict(zip(("key", "status", "phase", "claim_id", "deps", "desc", "updated"), cells))
        atomic_text(journal, json.dumps({"key": key, "previous": existing[1] if existing else None,
                                        "desired": desired, "document": text, "stub": stub}, ensure_ascii=False))
        try:
            atomic_text(index, "".join(lines))
            atomic_text(child(key_dir, "codex_doc.md"), text)
            atomic_text(child(key_dir, "pm-state.md"), stub)
            active_projection.write_projection(project, projection)
        except (OSError, active_projection.ActiveProjectionError) as exc:
            raise RuntimeError("PARTIAL WRITE: retry init/claim to reconcile the index and Codex mirrors") from exc
        journal.unlink()
        return {"key": key, "status": status, "phase": phase, "claim_id": claim}
    finally:
        mw_common.release_lock(lock)


def contract_hash(key_dir: Path) -> str:
    text, _, _ = lite_document(key_dir, ready=True)
    return hashlib.sha256("\n".join(section(text, h) for h in ("目标", "范围", "验收标准")).encode()).hexdigest()


def source_hash(cwd: Path) -> str:
    """Bind checks to current sources, excluding task state and generated files."""
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=cwd, capture_output=True, timeout=20)
    if result.returncode == 0 and result.stdout:
        candidates = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
    else:
        candidates = []
        for directory, names, files in os.walk(cwd):
            names[:] = [name for name in names if name not in SOURCE_EXCLUDES]
            candidates.extend(str((Path(directory) / name).relative_to(cwd)) for name in files)
        candidates.sort()
    digest = hashlib.sha256()
    for name in candidates:
        file = cwd / name
        if any(part in SOURCE_EXCLUDES for part in Path(name).parts) or not file.is_file():
            continue
        digest.update(name.replace("\\", "/").encode())
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()


def current_basis(key_dir: Path, cwd: Path) -> dict[str, str]:
    return {"contract_sha256": contract_hash(key_dir), "source_sha256": source_hash(cwd)}


def selected_criteria(key_dir: Path, requested: list[str], card_text: str = "") -> list[str]:
    _, _, declared = lite_document(key_dir, ready=True)
    selected = requested or sorted(set(re.findall(r"\bAC-\d{3}\b", card_text)))
    if not selected or not set(selected) <= set(declared):
        raise ValueError("Verification must name declared acceptance criteria with --ac AC-NNN")
    return sorted(set(selected))

def identifier(value: str, *, key: bool = False) -> str:
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) or value.endswith(".")
            or Path(value).is_reserved() or (key and active_projection.key_name_refusal(value) is not None)):
        raise ValueError(f"Invalid key or card name: {value!r}")
    return value


def child(root: Path, *parts: str) -> Path:
    """Coordination artifacts are local to this key, including existing junctions."""
    path = root.joinpath(*parts)
    existing = path
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    if existing.resolve() != existing:
        raise ValueError(f"Linked coordination path: {path}")
    return path


def key_state(project: Path, key: str, claim_id: str | None = None) -> dict:
    authority = child(project, ".agenticdoc", "_index.parallel")
    rows = active_projection.strict_rows_from_bytes(authority.read_bytes() if authority.is_file() else b"")
    matches = [row for row in rows if active_projection.normalize_key(row["key"]) == key.lower()]
    if len(matches) != 1:
        raise ValueError(f"Expected one registered key: {key}")
    row = matches[0]
    key_dir = child(project, ".agenticdoc", row["key"])
    if is_lite(key_dir):
        _, metadata, _ = lite_document(key_dir, ready=claim_id is not None)
        if any(metadata[field] != row[column] for field, column in
               (("Phase", "phase"), ("Status", "status"), ("Claim-Id", "claim_id"))):
            raise ValueError("Codex task state differs from index; run claim to recover")
        if claim_id is not None and (claim_id != "codex" or row["claim_id"] != claim_id or row["status"] != "active"):
            raise ValueError("An active, matching Codex claim is required")
        return row
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
    card_text = card.read_text(encoding="utf-8")
    acceptance_argv(card_text)
    key_dir = card.parent.parent
    lite = is_lite(key_dir)
    task_type = mw_common.read_task_type(card_text).type
    if task_type != "coding" and not (lite and task_type == "review"):
        raise ValueError("A coding card is required, or a review card for a Codex lightweight key")
    task_file = child(key_dir, "workers", task, "task.md")
    with dispatch_lock(project, task):
        owner = key_state(project, key, claim_id)
        phase = owner["phase"].upper()
        if phase != "EXECUTE" and not (lite and task_type == "review" and phase == "VERIFY"):
            raise ValueError("Dispatch requires EXECUTE; Codex lightweight review also supports VERIFY")
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
        assignment = (f"Independently review tasks/{card.name}. Record findings and limitations in report.md."
                      if task_type == "review" else
                      f"Implement tasks/{card.name}. Record changes, checks and residual issues in output.md.")
        payload = {"key": key, "task_key": task, "card_path": str(card), "cli": "pi", "type": task_type,
                   "description": f"{assignment}\n"
                                  f"PM verification cwd: {json.dumps(workspace)}"}
        if lite:
            payload.update(workflow=LITE_WORKFLOW, claim_id=claim_id)
        proc = subprocess.run(["node", str(Path(__file__).with_name("codex_dispatch.mjs").resolve())],
                              input=json.dumps(payload), cwd=project, capture_output=True, encoding="utf-8", errors="replace")
        row = next((r for r in queue(project) if r["task_key"] == task), None)
        if proc.returncode or not row:
            raise ValueError((proc.stderr if proc.returncode else proc.stdout).strip() or "Dispatch did not enqueue a worker")
        return {"reused": False, "receipt": proc.stdout.strip(), **snapshot(key_dir, task, row)}


def verify(project: Path, key_dir: Path, task: str, claim_id: str, argv: list[str],
           criteria: list[str] | None = None) -> tuple[dict, int]:
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
    if is_lite(key_dir):
        report.update(criteria=selected_criteria(key_dir, criteria or [], task_text), basis=current_basis(key_dir, Path(cwd)))
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
    if "basis" in report and report["basis"] != current_basis(key_dir, Path(cwd)):
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


def run_check(project: Path, key_dir: Path, criteria: list[str], argv: list[str]) -> tuple[dict, int]:
    owner = key_state(project, key_dir.name, "codex")
    if not is_lite(key_dir) or owner["phase"] not in {"EXECUTE", "VERIFY"}:
        raise ValueError("Direct checks require a codex-lite task in EXECUTE or VERIFY")
    selected = selected_criteria(key_dir, criteria)
    if not argv or not argv[0] or any("\x00" in arg for arg in argv):
        raise ValueError("A nonempty verification command is required")
    cwd = Path(mw_common.workspace_root(mw_common.load_target_config(project)))
    basis = current_basis(key_dir, cwd)
    folder = child(key_dir, "evidence", "codex-pm", "self")
    folder.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(dir=folder, prefix=f"{time.time_ns()}-"))
    log = evidence / "command.log"
    destination = evidence / "result.json"
    report = {"key": key_dir.name, "task": None, "criteria": selected, "argv": argv, "cwd": str(cwd),
              "basis": basis, "started": datetime.datetime.now(datetime.UTC).isoformat(),
              "verdict": "incomplete", "exit_code": None, "log": str(log)}
    atomic_text(destination, json.dumps(report, indent=2))
    with log.open("wb") as stream:
        try:
            code = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT).returncode
        except OSError as exc:
            stream.write(str(exc).encode("utf-8"))
            code = 127
    verdict = "passed" if code == 0 else "failed"
    try:
        key_state(project, key_dir.name, "codex")
        if basis != current_basis(key_dir, cwd):
            verdict = "stale"
    except ValueError as exc:
        verdict = "stale"
        report["reason"] = str(exc)
    report.update(verdict=verdict, exit_code=code, finished=datetime.datetime.now(datetime.UTC).isoformat())
    atomic_text(destination, json.dumps(report, indent=2))
    return {**report, "evidence": str(destination)}, 0 if verdict == "passed" else 1


def lite_checks(project: Path, key_dir: Path) -> list[dict]:
    records = []
    files = sorted(child(key_dir, "evidence", "codex-pm").glob("*/*/result.json"))
    if not files:
        return records
    cwd = Path(mw_common.workspace_root(mw_common.load_target_config(project)))
    basis = current_basis(key_dir, cwd)
    for file in files:
        record = json.loads(child(file.parent, "result.json").read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("key") != key_dir.name:
            raise ValueError(f"Invalid verification record: {file}")
        if record.get("verdict") == "passed":
            if (record.get("basis") != basis or Path(record.get("cwd", "")).resolve() != cwd.resolve()
                    or record.get("exit_code") != 0 or not Path(record.get("log", "")).is_file()):
                record["verdict"] = "stale"
            if record.get("task"):
                task_dir = child(key_dir, "workers", identifier(record["task"]))
                latest = next((r for r in queue(project) if r["task_key"] == record["task"]), None)
                statuses = {v for v in (latest["status"] if latest else None, mw_common.read_run_status(task_dir)) if v}
                if statuses != {"done"} or record.get("binding") != run_binding(task_dir):
                    record["verdict"] = "stale"
        records.append({**record, "evidence": str(file)})
    return sorted(records, key=lambda record: record.get("started", ""))


def completion_checks(project: Path, key_dir: Path) -> list[dict]:
    document, _, criteria = lite_document(key_dir, ready=True)
    achieved = child(key_dir, "achieved.md").read_text(encoding="utf-8")
    residual = section(achieved, "遗留")
    freeze = contract_guard.read_freeze(key_dir) or {}
    signoff = None
    if freeze.get("decision_signoff") == "required":
        signoff = decision_signoff_result.validate_signoff(key_dir, key_dir.name)
        if not signoff.valid or not signoff.native_basis_verified:
            raise ValueError(f"Completion requires a current sign-off: {signoff.reason}")
    if signoff is not None and signoff.record_version == 4:
        # The independent reviewer binds achieved.md byte-for-byte. Keep
        # Codex's dispositions of historical workers in the PM document.
        residual = residual or section(document, "结案遗留")
        if not residual:
            raise ValueError("Reviewed closure requires a nonempty 结案遗留 section in codex_doc.md")
    elif not section(achieved, "系统行为变化") or not residual:
        raise ValueError("achieved.md requires nonempty 系统行为变化 and 遗留 sections")
    # A closure the PM authored must name the code paths it wrote. The reviewed
    # v4 sign-off branch above binds achieved.md byte-for-byte, so it cannot
    # require an extra section; its change set still records the coverage gap.
    if signoff is None or signoff.record_version != 4:
        declared, acknowledged = change_set.declared_paths(achieved)
        if change_set.section(achieved, "修改面") is None or (not declared and not acknowledged):
            raise ValueError("achieved.md requires a nonempty 修改面 section listing written code paths"
                             " (or an explicit no-write statement)")
    workers = [row for row in queue(project) if mw_common.worker_owner_key(row) == key_dir.name]
    if any(row["status"] not in {"done", "failed", "needs-clarification", "lost", "cancelled"} for row in workers):
        raise ValueError("Completion blocked by in-flight workers")
    pending = gates.pending_gates(project / ".agenticdoc" / "_autopilot" / "gates")
    if any(gate.key == key_dir.name for gate in pending):
        raise ValueError("Completion blocked by pending gates")
    checks = lite_checks(project, key_dir)
    latest = {}
    for record in checks:
        for criterion in record.get("criteria", []):
            latest[criterion] = record
    if any(latest.get(criterion, {}).get("verdict") != "passed" for criterion in criteria):
        raise ValueError("Every acceptance criterion needs a current passing verification")
    for row in workers:
        task_checks = [record for record in checks if record.get("task") == row["task_key"]]
        if row["status"] == "done" and task_checks and task_checks[-1]["verdict"] == "passed":
            continue
        # Failed/historical attempts must have an explicit disposition in the
        # closure record; they cannot silently disappear behind an exit code.
        if row["task_key"] not in residual:
            raise ValueError(f"Worker needs verification or a recorded disposition: {row['task_key']}")
    return checks


def complete(project: Path, key_dir: Path, summary: str) -> dict:
    if not summary.strip() or any(char in summary for char in "|\r\n"):
        raise ValueError("Completion requires a one-line --summary without table separators")
    owner = key_state(project, key_dir.name)
    if not is_lite(key_dir) or owner["phase"] not in {"VERIFY", "DONE"}:
        raise ValueError("Completion requires a codex-lite task in VERIFY")
    closure_file = child(key_dir, "evidence", "codex-pm", "completion.json")
    if owner["phase"] == "DONE":
        closure = json.loads(closure_file.read_text(encoding="utf-8"))
        if (not isinstance(closure, dict) or closure.get("key") != key_dir.name
                or not isinstance(closure.get("summary"), str) or not isinstance(closure.get("checks"), list)):
            raise ValueError("Completed task has no valid closure snapshot")
        # Completion is historical. New development cannot prevent repairing
        # the retrieval log of a task that has already passed and released.
        summary = closure["summary"]
        checks = closure["checks"]
        result = owner
    else:
        key_state(project, key_dir.name, "codex")
        checks = completion_checks(project, key_dir)
        # The change set is generated from the key's own write events, never a
        # repository comparison. It is written before the closure snapshot so
        # completion.json can point at a record that already exists.
        written = change_set.finalize(project, key_dir.name)
        atomic_text(closure_file, json.dumps({"key": key_dir.name, "summary": summary, "checks": checks,
                                             "change_set": written,
                                             "verified_at": datetime.datetime.now(datetime.UTC).isoformat()}, indent=2))
        result = lite_transition(project, key_dir.name, "done")
    # The log is a cross-key retrieval index, not another process document.
    log_lock = child(project, ".mw", "codex-project-log.lock")
    mw_common.acquire_lock(log_lock, deadline_s=10)
    try:
        log = child(project, ".agenticdoc", "_project_log.md")
        if log.is_file():
            with log.open(encoding="utf-8", newline="") as stream:
                text = stream.read()
        else:
            text = ("# Project Log\n\n| Completed | Commit | Key | 核心问题 | Supersedes |\n"
                    "|-----------|--------|-----|---------|------------|\n")
        if not any(re.match(r"^\|[^|]*\|[^|]*\|\s*" + re.escape(key_dir.name) + r"\s*\|", line)
                   for line in text.splitlines()):
            revision = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=project,
                                      capture_output=True, text=True, timeout=10)
            ref = revision.stdout.strip() if revision.returncode == 0 else "NO-GIT"
            newline = "\r\n" if "\r\n" in text else "\n"
            separator = "" if text.endswith("\n") else newline
            atomic_text(log, text + separator + f"| {datetime.datetime.now(datetime.UTC).isoformat()} | {ref} | "
                        f"{key_dir.name} | {summary} | — |{newline}")
    except OSError as exc:
        raise RuntimeError("PARTIAL WRITE: task completed, project-log update failed") from exc
    finally:
        mw_common.release_lock(log_lock)
    return {**result, "achieved": str(key_dir / "achieved.md"), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("init", "claim", "release", "advance", "check", "done", "dispatch", "status", "verify"):
        command = sub.add_parser(action)
        command.add_argument("--project", type=Path, default=Path.cwd())
        command.add_argument("--key", required=True)
        if action in {"dispatch", "verify"}:
            command.add_argument("--card", required=True, help="Task card filename stem under <key>/tasks/")
            command.add_argument("--claim-id", default="codex", help="codex for lightweight tasks; existing ClaimId for SDD")
        if action in {"verify", "check"}:
            command.add_argument("--ac", action="append", default=[], help="Acceptance criterion verified by this command")
            command.add_argument("argv", nargs=argparse.REMAINDER, help="-- PROGRAM ARG ... from the dispatched card")
        if action == "advance":
            command.add_argument("--phase", required=True, type=str.upper, choices=("EXECUTE", "VERIFY"))
        if action == "done":
            command.add_argument("--summary", required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    key = identifier(args.key, key=True)
    if args.action in {"init", "claim", "release", "advance"}:
        with dispatch_lock(project, "key-" + key.lower()):
            result = lite_transition(project, key, args.action, getattr(args, "phase", None))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    owner = key_state(project, key)
    key = owner["key"]
    key_dir = child(project, ".agenticdoc", key)
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
        if is_lite(key_dir):
            result.update(workflow=LITE_WORKFLOW, status=owner["status"], codex_doc=str(key_dir / "codex_doc.md"),
                          checks=lite_checks(project, key_dir))
            for worker in result["tasks"]:
                checks = [record for record in result["checks"] if record.get("task") == worker["task"]]
                if checks:
                    worker["verification"] = checks[-1]["verdict"]
    else:
        with dispatch_lock(project, "key-" + key.lower()):
            if args.action == "done":
                result = complete(project, key_dir, args.summary)
            elif args.action == "check":
                argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
                result, code = run_check(project, key_dir, args.ac, argv)
            else:
                stem = identifier(args.card)
                task = ("cx-" + hashlib.sha256(f"{key}/{stem}".encode()).hexdigest()[:20]
                        if is_lite(key_dir) else f"pm-{len(key)}-{key}-{stem}")
                if args.action == "dispatch":
                    result = dispatch(project, key, stem, task, args.claim_id)
                else:
                    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
                    result, code = verify(project, key_dir, task, args.claim_id, argv, args.ac)
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, config.ConfigError, roadmap.RoadmapError, mw_common.TargetConfigError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)
