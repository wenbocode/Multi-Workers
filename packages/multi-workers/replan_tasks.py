"""Durable per-run replanning and shared admission for both MW dispatchers."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

import decision as decision_config
import decision_lifecycle
import decision_wire
import mw_common
import scope_review
from autopilot import dispatch as cards
from autopilot import state, write_face


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}", value) or value.endswith("."):
        raise ValueError("invalid key, card or task identifier")
    return value


def local(path: Path) -> Path:
    if path.resolve() != path:
        raise ValueError(f"linked coordination path: {path}")
    return path


def body(path: Path) -> str:
    return local(path).read_text("utf-8-sig") if path.is_file() else ""


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save(path: Path, record: dict) -> None:
    local(path).parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def publish_new(path: Path, text: str) -> None:
    """Publish a complete file without replacing another writer's file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        # Windows rename is atomic and refuses an existing destination.
        if os.name == "nt":
            os.rename(tmp, path)
        else:
            os.link(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


@contextlib.contextmanager
def locked(path: Path):
    mw_common.acquire_lock(path, deadline_s=8)
    try:
        yield
    finally:
        mw_common.release_lock(path)


def records(key_dir: Path) -> list[dict]:
    folder = local(key_dir / "evidence" / "replan")
    return [json.loads(body(p)) for p in sorted(folder.glob("*.json"))]


def source_card(key_dir: Path, ref: str) -> Path:
    if not re.fullmatch(r"tasks/[\w.-]+\.md", ref):
        raise ValueError("source card must belong to the owner's tasks directory")
    return local(key_dir / ref)


def card_identity(ref: str) -> str:
    return ref.casefold() if os.name == "nt" else ref


OBLIGATION = re.compile(r"(?<![\w-])(?:AC|FLOW|VC)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?![\w-])")


def table_rows(markdown: str, heading: str):
    section = re.search(r"^(#{2,6})[ \t]+" + re.escape(heading) + r"[ \t]*$", markdown, re.M)
    if section:
        following = markdown[section.end():]
        end = re.search(r"^#{1," + str(len(section[1])) + r"}[ \t]+", following, re.M)
        for line in following[:end.start() if end else len(following)].splitlines():
            if line.strip().startswith("|"):
                yield [part.strip().strip("`") for part in line.strip().strip("|").split("|")]


def card_coverage(closure: dict, ref: str, markdown: str) -> set[str]:
    required = set(OBLIGATION.findall(markdown))
    if ref:
        stem = Path(ref).stem.casefold()
        aliases = {stem, stem.removeprefix("t-")}
        for obligation, (owners, _) in closure.items():
            if aliases & owners:
                required.add(obligation)
    return required | {vc for obligation in required for vc in closure.get(obligation, ((), ()))[1]}


def closure_coverage(plan: str, design: str) -> dict:
    flows = {row[0]: set(OBLIGATION.findall(row[3])) for row in table_rows(design, "必要功能路径")
             if len(row) >= 4 and row[0].startswith("FLOW-")}
    closure = {flow: (set(), checks) for flow, checks in flows.items()}
    for row in table_rows(plan, "闭环覆盖"):
        if len(row) >= 3 and OBLIGATION.fullmatch(row[0]):
            owners = {part.strip().strip("`").casefold().removeprefix("t-") for part in row[1].split(",")}
            closure[row[0]] = owners, set(OBLIGATION.findall(row[2])) | flows.get(row[0], set())
    return closure


def timestamp(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else None
        except ValueError:
            pass
    return None


def run_progress(folder: Path, run_id: object) -> dict | None:
    file = folder / "run-progress.json"
    try:
        if not isinstance(run_id, str) or not file.is_file() or local(file).stat().st_size > 64 * 1024:
            return None
        progress = json.loads(body(file))
        return progress if isinstance(progress, dict) and progress.get("run_id") == run_id else None
    except (OSError, ValueError):
        return None


def run_facts(key_dir: Path, task: str, status: str) -> dict:
    folder = local(key_dir / "workers" / identifier(task))
    try:
        raw = json.loads(body(folder / "run.json") or "{}")
    except ValueError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    envelope = body(folder / "task.md")
    output = body(folder / "output.md")
    card = card_identity(mw_common.read_task_header_scalar(envelope, "card_path") or "")
    started, ended = raw.get("started_at"), raw.get("ended_at")
    rid = raw.get("run_id")
    category = status
    deadline = (
        status == raw.get("status") == "failed"
        and raw.get("stop_kind") == "worker-deadline"
        and raw.get("task_key") == task
        and raw.get("owner_key") == key_dir.name
        and isinstance(rid, str) and rid.startswith(task + "@")
        and timestamp(rid.partition("@")[2]) is not None
    )
    if deadline:
        category = "wall-timeout"
    elapsed = None
    start, end = timestamp(started), timestamp(ended)
    if start and end and end >= start:
        elapsed = (end - start).total_seconds()
        if raw.get("status") == status == "failed" and (raw.get("model_exhausted") or raw.get("exit") == 3):
            category = "model-unavailable"
        if category == "failed" and raw.get("status") == status and raw.get("task_key") == task and rid:
            trace = local(folder / "trace.log")
            if trace.is_file():
                with trace.open(encoding="utf-8", errors="replace") as lines:
                    for line in lines:
                        match = re.match(r"^\[TIMEOUT\] (\S+) (wall|idle): ", line)
                        fired = timestamp(match[1]) if match else None
                        if fired and start <= fired <= end:
                            category = match[2] + "-timeout"
    timeout = mw_common.read_task_header_scalar(envelope, "timeout")
    if category == "done" and elapsed is not None and timeout:
        try:
            if 0 < float(timeout) * 60 < elapsed:
                category = "budget-overrun"
        except ValueError:
            pass
    if category == "failed":
        if re.search(r"^model unavailable:", output, re.M):
            category = "model-unavailable"
        else:
            log = local(folder / "worker.log")
            if log.is_file():
                with log.open("rb") as stream:
                    stream.seek(max(0, log.stat().st_size - 4096))
                    if b"[launcher] spawn failed" in stream.read(4096):
                        category = "spawn-failed"
    progress = run_progress(folder, rid) if deadline else None
    return {"task": task, "run_id": rid, "status": status, "category": category,
            **({"stop_kind": "worker-deadline", "progress_digest": digest(progress) if progress else None}
               if deadline else {}),
            "elapsed_seconds": elapsed, "timeout_minutes": timeout,
            "card": card, "started": started, "ended": ended,
            "artifacts": [p for p in ("output.md", "report.md", "progress.md", "run-progress.json", "run.json", "trace.log")
                          if (folder / p).is_file()], "output_digest": digest(output),
            "exit_reason": output.partition("## Exit Reason")[2].split("\n## ")[0].strip()[:1600]}


def remember(key_dir: Path, facts: dict) -> dict:
    # Retain the dispatched identity even for older runs without a reliable run_id.
    ticket = digest([key_dir.name, facts["task"], facts["run_id"] or facts["started"] or facts["dispatch_time"]])
    path = local(key_dir / "evidence" / "replan" / (ticket + ".json"))
    if path.is_file():
        record = json.loads(body(path))
        if record["source"] != facts and record["state"] in {"open", "previewed"}:
            record["source"] = facts
            save(path, record)
        return record
    record = {"id": ticket, "state": "open", "source": facts}
    save(path, record)
    return record


def capture(project: Path, row: dict, status: str, *, retry: bool = False) -> dict | None:
    if status not in {"failed", "lost", "needs-clarification"}:
        return None
    owner = mw_common.worker_owner_key(row)
    key_dir = local(project / ".agenticdoc" / identifier(owner))
    if Path(row["task_path"]).resolve() != key_dir / "workers" / identifier(row["task_key"]) / "task.md":
        return None
    facts = run_facts(key_dir, row["task_key"], status)
    facts["dispatch_time"] = row.get("dispatched_at")
    if retry or facts["category"] in {"wall-timeout", "idle-timeout"}:
        return remember(key_dir, facts)
    return None


def worker_rows(project: Path, key: str) -> list[dict]:
    return [r for r in mw_common.parse_workers_file(mw_common.workers_path(project))
            if mw_common.worker_owner_key(r) == key]


def inspect(project: Path, key_dir: Path, task: str | None, *, section: str = "issues",
            offset: int = 0, limit: int = 20) -> dict:
    if section not in {"issues", "cards", "workers", "applied_plans"}:
        raise ValueError("unknown inventory section")
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("offset must be a nonnegative integer; limit must be an integer from 1 to 50")
    rows = worker_rows(project, key_dir.name)
    if not task:
        items = records(key_dir)
        inventory = {"issues": [{"issue": r["id"], "task": r["source"]["task"], "state": r["state"],
                            "category": r["source"]["category"], "action": r.get("plan", {}).get("action"),
                            "needs_attention": r["state"] != "applied" or r["plan"]["action"] in {"schedule", "escalate"}}
                           for r in items],
                "cards": [p.stem for p in sorted((key_dir / "tasks").glob("*.md")) if p.stem.lower() != "readme"],
                "applied_plans": [{"version": r["version"], "source": r["source"]["task"],
                                   "dependencies": {u["id"]: u["depends_on"] for u in r["plan"]["units"]},
                                   "ready_existing": r["plan"].get("ready_existing", [])}
                                  for r in items if r["state"] == "applied"],
                "workers": [{"task": r["task_key"], "status": r["status"]} for r in rows]}
        inventory["issues"].sort(key=lambda item: not item["needs_attention"])
        inventory["workers"].sort(key=lambda item: item["status"] not in {"pending", "running"})
        total = len(inventory[section])
        return {section: inventory[section][offset:offset + limit],
                "counts": {**{name: len(values) for name, values in inventory.items()},
                           "needs_attention": sum(item["needs_attention"] for item in inventory["issues"])},
                "page": {"section": section, "offset": offset, "limit": limit, "total": total,
                         "next_offset": offset + limit if offset + limit < total else None},
                "plan_path": str(key_dir / "plan.md")}
    identifier(task)
    row = next((r for r in rows if r["task_key"] == task), None)
    if row:
        facts = run_facts(key_dir, task, row["status"])
        facts["dispatch_time"] = row.get("dispatched_at")
    else:
        ref = card_identity(f"tasks/{task}.md")
        if not source_card(key_dir, ref).is_file():
            raise ValueError("unknown source task or card")
        matches = [r for r in rows if card_identity(mw_common.read_task_header_scalar(
            body(key_dir / "workers" / identifier(r["task_key"]) / "task.md"), "card_path") or "") == ref]
        if matches:
            return inspect(project, key_dir, max(matches, key=lambda r: r["dispatched_at"])["task_key"])
        facts = {"task": task, "run_id": None, "status": "unstarted", "category": "unstarted",
                 "dispatch_time": None, "started": None, "card": ref}
    record = remember(key_dir, facts)
    return {"issue": record["id"], "state": record["state"], "facts": facts,
            **source_context(key_dir, facts),
            "live_workers": [r["task_key"] for r in rows if r["status"] in {"pending", "running"}]}


def source_context(key_dir: Path, facts: dict) -> dict:
    task = identifier(facts["task"])
    original = body(source_card(key_dir, facts["card"])) if facts["card"].startswith("tasks/") else ""
    envelope = body(key_dir / "workers" / task / "task.md")
    snapshot = digest([facts, original, envelope])
    report = key_dir / "workers" / task / "report.md"
    plan, design = body(key_dir / "plan.md"), body(key_dir / "design.md")
    closure = closure_coverage(plan, design)
    coverage = sorted(card_coverage(closure, facts["card"], original or envelope))
    snapshot_fields = [snapshot, digest(body(report)), plan, body(key_dir / "spec.md")]
    if closure or any(not item.startswith("AC-") for item in coverage):
        snapshot_fields.append(design)
    snapshot = digest(snapshot_fields)
    acceptance = [item for item in coverage if item.startswith("AC-")]
    return {"snapshot": snapshot, "acceptance": acceptance, "coverage": coverage, "closure": closure}


def retained_proof(project: Path, key_dir: Path, current: dict, retained: dict) -> dict:
    proofs = {}
    for obligation, ref in retained.items():
        if obligation not in current["coverage"]:
            raise ValueError(f"retained obligation is outside the source scope: {obligation}")
        if re.fullmatch(r"evidence/(?:[\w.-]+/)*[\w.-]+\.md", ref) and not {
                ".", ".."}.intersection(ref.split("/")):
            evidence = body(key_dir / ref)
            if any(obligation in OBLIGATION.findall(line) and re.search(r"\bPASS\b", line) and
                   not re.search(r"\b(?:FAIL|PENDING)\b", line) for line in evidence.splitlines()):
                proofs[obligation] = digest(evidence)
                continue
        elif re.fullmatch(r"tasks/[\w.-]+\.md", ref) and card_identity(ref) != current["facts"]["card"]:
            markdown = body(source_card(key_dir, ref))
            dispatched = any(card_identity(mw_common.read_task_header_scalar(
                body(key_dir / "workers" / identifier(row["task_key"]) / "task.md"), "card_path") or "")
                == card_identity(ref) for row in worker_rows(project, key_dir.name))
            if (markdown and obligation in card_coverage(current["closure"], ref, markdown)
                    and not dispatched and not admission(project, key_dir.name, Path(ref).stem, ref)):
                proofs[obligation] = digest(markdown)
                continue
        raise ValueError(f"{obligation}: expected a remaining card that owns it or key evidence recording its PASS")
    return proofs


def text_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def plan_face(project: Path, markdown: str):
    entries = cards._card_write_face_entries({"extras": cards.extract_card_extras(markdown)})
    return cards.parse_workspace_write_face(project, cards.render_write_face_line(entries or []))


def applied_lineage(known: list[dict], ref: str) -> list[tuple[dict, dict]]:
    """Walk from a published card back through replans of unstarted cards."""
    producers = {}
    for record in known:
        if record["state"] in {"applied", "publishing"}:
            for unit in record["plan"]["units"]:
                producers.setdefault(card_identity(f"tasks/{unit['id']}.md"), []).append((record, unit))
    lineage, seen = [], set()
    ref = card_identity(ref)
    while ref in producers:
        matches = producers[ref]
        if ref in seen or len(matches) != 1:
            raise ValueError("cyclic or ambiguous replan ancestry")
        record, unit = matches[0]
        if record["state"] != "applied" or record["plan"]["action"] not in {"narrow", "split"}:
            raise ValueError("incomplete applied replan ancestry")
        lineage.append((record, unit))
        seen.add(ref)
        if record["source"]["status"] != "unstarted":
            break
        ref = card_identity(record["source"]["card"])
    return lineage


def preview(project: Path, key_dir: Path, current: dict, plan: dict) -> dict:
    units = plan["units"]
    choice = plan["action"]
    if choice not in {"split", "narrow", "direct-exec", "escalate", "schedule"}:
        raise ValueError("unknown disposition")
    if not isinstance(plan.get("reason"), str) or not plan["reason"].strip():
        raise ValueError("explain the remaining work or scheduling decision")
    if not isinstance(units, list) or (choice == "split" and len(units) < 2) or (
        choice == "narrow" and len(units) != 1) or (choice not in {"narrow", "split"} and units):
        raise ValueError("split requires multiple units; narrow requires one; other actions publish no cards")
    retained = plan.get("retained", {})
    if not isinstance(retained, dict) or not all(isinstance(v, str) and v.strip() for v in retained.values()):
        raise ValueError("retained obligations require evidence or a named remaining owner")
    proofs = retained_proof(project, key_dir, current, retained)
    if units and any(ref.startswith("tasks/") for ref in retained.values()):
        source = current["facts"]["card"]
        plans = [r for r in records(key_dir) if r["state"] == "applied"]
        for record in plans:
            for unit in record["plan"]["units"]:
                ref = card_identity(f"tasks/{unit['id']}.md")
                if ref == source and any(unit["id"] in other["depends_on"] for plan in plans
                                         for other in plan["plan"]["units"]):
                    raise ValueError("a predecessor with dependents requires PASS evidence or successor coverage")
    coverage = set(retained)
    graph, faces, resources = {}, {}, {}
    source = current["facts"]
    if units and source["status"] == "unstarted":
        lineage = applied_lineage(records(key_dir), source["card"])
        if lineage:
            source = lineage[-1][0]["source"]
    deadline_parent = source["run_id"] if source.get("stop_kind") == "worker-deadline" else None
    for unit in units:
        stem = identifier(unit["id"])
        if stem.casefold() in {s.casefold() for s in graph} or stem == current["facts"]["task"]:
            raise ValueError(f"duplicate or reused task id: {stem}")
        if not text_list(unit["depends_on"]) or not text_list(unit["covers"]) or not unit["covers"]:
            raise ValueError(f"{stem}: missing acceptance or invalid dependencies")
        if unit.get("resources") is not None and not text_list(unit["resources"]):
            raise ValueError(f"{stem}: invalid exclusive resources")
        for field in ("first_check", "expected", "reuse", "markdown"):
            if not isinstance(unit.get(field), str) or not unit[field].strip():
                raise ValueError(f"{stem}: missing {field}")
        md = unit["markdown"].replace("\r\n", "\n").replace("\r", "\n")
        if deadline_parent and mw_common.read_task_header_scalar(md, "parent_worker_run") != deadline_parent:
            raise ValueError(f"{stem}: parent_worker_run must name the timed-out run {deadline_parent}")
        role = mw_common.read_task_header_scalar(md, "type")
        headings = ("上下文", "要求", "交付格式", *cards.PRODUCER_EXTRA_ITEMS.get(role, ()))
        if role not in {*cards.PRODUCER_EXTRA_ITEMS, *cards.REGISTRY} or any(
                re.search(r"^##[ \t]+" + heading + r"[ \t]*\n\s*(?!#)\S", md, re.M) is None for heading in headings):
            raise ValueError(f"{stem}: expected a dispatchable card with header and sections")
        minutes = float(mw_common.read_task_header_scalar(md, "timeout") or 0)
        if not math.isfinite(minutes) or minutes <= 0:
            raise ValueError(f"{stem}: missing positive timeout header")
        graph[stem] = set(unit["depends_on"])
        faces[stem] = plan_face(project, md)
        if isinstance(faces[stem], write_face.Refused):
            raise ValueError(f"{stem}: invalid write face: {faces[stem].code}: {faces[stem].detail}")
        resources[stem] = unit.get("resources")
        coverage.update(unit["covers"])
    structured = current["closure"] or any(not item.startswith("AC-") for item in current["coverage"])
    if (units or choice == "direct-exec" and structured) and (missing := set(current["coverage"]) - coverage):
        raise ValueError(f"unassigned acceptance or required coverage: {sorted(missing)}")
    existing = plan.get("ready_existing", [])
    if choice == "schedule":
        if not text_list(existing) or not existing or len(set(existing)) != len(existing):
            raise ValueError("name the independent existing cards to schedule")
        for stem in existing:
            ref = card_identity(f"tasks/{identifier(stem)}.md")
            path = source_card(key_dir, ref)
            if not path.is_file() or ref == current["facts"]["card"]:
                raise ValueError("schedule requires an existing independent card")
            if any(card_identity(mw_common.read_task_header_scalar(body(key_dir / "workers" / identifier(row["task_key"]) / "task.md"),
                      "card_path") or "") == ref for row in worker_rows(project, key_dir.name)):
                raise ValueError(f"{stem}: card has already been dispatched")
            reason = admission(project, key_dir.name, stem, ref)
            entries = cards._card_write_face_entries({"extras": cards.extract_card_extras(body(path))})
            conflict = cards._write_face_verdict(project, key_dir.name, stem, cards.render_write_face_line(entries or []),
                                                 card_backed=True, timeline=None)
            if reason or conflict:
                raise ValueError(f"{stem}: {reason or conflict.reason}")
    elif existing:
        raise ValueError("ready_existing belongs to schedule")
    if any(deps - graph.keys() for deps in graph.values()):
        raise ValueError("unknown dependency in proposed units")
    ordered = list(TopologicalSorter(graph).static_order())
    ancestors = {}
    for stem in ordered:
        ancestors[stem] = set(graph[stem])
        for parent in graph[stem]:
            ancestors[stem].update(ancestors[parent])
        for other in ancestors.keys() - {stem} - ancestors[stem]:
            left, right = faces[stem], faces[other]
            if (not isinstance(left, write_face.WriteFace) or not isinstance(right, write_face.WriteFace)
                    or write_face.is_overlap(write_face.overlap(left, right))
                    or resources[stem] is None or resources[other] is None
                    or set(resources[stem]).intersection(resources[other])):
                raise ValueError(f"unordered conflict or unknown resource: {other}, {stem}; declare dependency")
    waiting = {s: sorted(graph[s]) for s in ordered}
    source_ref = current["facts"]["card"]
    if source_ref:
        gate = admission(project, key_dir.name, current["facts"]["task"], source_ref, check_scope=False)
        if gate and gate.startswith("replan-dependency-pending:"):
            inherited = gate.partition(":")[2].split(",")
            for stem in ordered:
                waiting[stem].extend(inherited)
    known_resources = {card_identity(f"tasks/{u['id']}.md"): u.get("resources") for r in records(key_dir)
                       if r["state"] == "applied" for u in r["plan"]["units"]}
    for live in current["live_workers"]:
        head = body(key_dir / "workers" / identifier(live) / "task.md")
        face = cards.parse_workspace_write_face(project, head)
        held = known_resources.get(card_identity(mw_common.read_task_header_scalar(head, "card_path") or ""))
        for stem in ordered:
            if (not isinstance(face, write_face.WriteFace) or not isinstance(faces[stem], write_face.WriteFace)
                    or write_face.is_overlap(write_face.overlap(faces[stem], face))
                    or resources[stem] is None or (resources[stem] and held is None)
                    or (held and set(resources[stem]).intersection(held))):
                waiting[stem].append("live:" + live)
    version_fields = [current["issue"], current["snapshot"], plan]
    if proofs:
        version_fields.append(proofs)
    version = digest(version_fields)
    scope = scope_review.Scope(key_dir)
    if scope.reviews is not None:
        scope.check_plan()
        review = scope.review("replans", version)
        if review["anchor"] not in current["coverage"]:
            raise ValueError("scope-review: replan must retain an anchor from the original task")
        for unit in units:
            if not set(unit["covers"]).issubset(current["coverage"]):
                raise ValueError(f"scope-review: {unit['id']} adds coverage outside the original task")
    return {"version": version, "basis_id": "replan-" + version[:24], "action": choice,
            "initial_batch": existing[:1] or [s for s in ordered if not waiting[s]],
            "ready_existing": existing, "waiting": waiting}


def decision(project: Path, key: str, source: dict, prepared: dict, ref: str):
    sink = decision_wire.production_lifecycle_sink(project)
    batch = decision_wire.read_events(sink)
    stats = batch.stats
    if any((stats.bad_json, stats.bad_utf8, stats.unknown_schema, stats.oversized_line, stats.incomplete_tail)):
        raise ValueError("damaged decision lifecycle")
    expected_task = source["task"] if source["status"] != "unstarted" else None
    matches = [r for r in batch.events if r.get("kind") == "request" and r.get("origin") == "decision-lifecycle"
               and r.get("scope") == "production" and r.get("project_id") == decision_wire.project_id_for(project)
               and r.get("decision_id") == ref and r.get("dp") == "dp-pm-steer" and r.get("key") == key
               and r.get("task_key") == expected_task and r.get("available") is True and r.get("business_decisions") == 1
               and r.get("choice") == prepared["action"] and r.get("basis_id") == prepared["basis_id"]]
    if len(matches) != 1:
        raise ValueError("no matching dp-pm-steer decision for this task, branch and plan basis")
    common = [r for r in batch.events if r.get("scope") == "production" and r.get("origin") == "decision-lifecycle"
              and r.get("project_id") == matches[0]["project_id"] and r.get("decision_id") == ref
              and r.get("logical_id") == matches[0].get("logical_id") and r.get("key") == key
              and r.get("task_key") == expected_task]
    starts = [r for r in common if r["kind"] == "record-start" and r.get("initiator_role") == "pm"]
    if len(starts) != 1:
        raise ValueError("missing unique PM decision start")
    for event in common:
        if event.get("kind") != "lifecycle":
            continue
        if event.get("lifecycle") == "executed" and event.get("action") != prepared["action"]:
            raise ValueError("decision already executed with a different action")
        outcome = "pending" if prepared["action"] == "escalate" else "ok"
        if event.get("lifecycle") == "settled" and event.get("outcome") != outcome:
            raise ValueError("decision already settled with a different outcome")
    return decision_lifecycle.DecisionMeta.from_envelope({"meta": {
        field: starts[0][field] for field in ("key", "task_key", "initiator_role", "logical_id", "record_version",
                                               "retry_of", "task_before") if field in starts[0]}}), common


def receipt(project: Path, record: dict, claim: str) -> None:
    action = record["plan"]["action"]
    ref = record.get("decision_id")
    if action == "schedule" or not ref:
        return
    prepared = {"action": action, "basis_id": "replan-" + record["version"][:24]}
    meta, events = decision(project, record["key"], record["source"], prepared, ref)
    stages = {e.get("lifecycle") for e in events if e["kind"] == "lifecycle"}
    cfg, error = decision_config.DecisionConfig.from_project(project)
    if error:
        raise ValueError("decision receipt configuration unavailable")
    store = decision_lifecycle.LifecycleStore.production(project, redact=decision_config.known_secret_redactor(cfg))
    args = {"decision_id": ref, "dp": "dp-pm-steer", "actor": ("system", "pm:" + claim)}
    if "executed" not in stages:
        if not decision_lifecycle.record_executed(store, meta, action=action, result=record["version"],
                event_id="replan-exec-" + record["version"][:24], **args).recorded:
            raise ValueError("plan published; retry apply to recover execution receipt")
    if "settled" not in stages:
        if not decision_lifecycle.record_settled(store, meta, outcome="pending" if action == "escalate" else "ok",
                reason="replan handling; worker acceptance remains separate",
                event_id="replan-settle-" + record["version"][:24], **args).recorded:
            raise ValueError("plan published; retry apply to recover settlement receipt")


def card_text(record: dict, unit: dict) -> str:
    return (unit["markdown"].replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n\n## 重规划接续\n"
            + f"来源 {record['id']} / {record['version']}\n"
            + f"承接 {', '.join(unit['covers'])}\n复用 {unit['reuse']}\n"
            + f"首验 {unit['first_check']}\n预期 {unit['expected']}\n")


def execute(project: Path, req: dict) -> dict:
    key = identifier(req["key"])
    key_dir = local(project / ".agenticdoc" / key)
    op = req["operation"]
    with locked(project / ".mw" / "index.lock"), locked(mw_common.lock_path(project)):
        owners = [r for r in state.read_index(project) if r["key"].casefold() == key.casefold()]
        if (not req.get("claim") or req["claim"] in {"—", "-"} or len(owners) != 1
                or owners[0]["key"] != key or owners[0]["status"] != "active" or owners[0]["claim_id"] != req["claim"]):
            raise ValueError("current window does not own the active key")
        if op in {"inspect_deadline_recovery", "authorize_deadline_recovery"}:
            card_ref = req["card"]
            pin = cards.card_digest(source_card(key_dir, card_ref))
            approval = deadline_successor(project, key, None, card_ref, pin, req["parent"], review=True)
            historical = approval.get("historical_review")
            if not historical:
                return {"state": "review-not-required", "approval": approval}
            snapshot = digest(approval)
            if op == "inspect_deadline_recovery":
                return {"state": "review-required", "snapshot": snapshot, "approval": approval}
            if req["snapshot"] != snapshot:
                raise ValueError("deadline recovery evidence changed; inspect again")
            reason = req["recovery_reason"].strip()
            if not reason or len(reason) > 4000:
                raise ValueError("explain why the reviewed historical evidence authorizes recovery")
            target = local(key_dir / "evidence" / "deadline-recovery" / f"{snapshot}.json")
            if not target.exists():
                save(target, {"approval": approval, "reason": reason})
            else:
                saved = json.loads(body(target))
                if saved.get("approval") != approval or not saved.get("reason"):
                    raise ValueError("existing deadline recovery approval is damaged")
            return {"state": "authorized", "snapshot": snapshot, "path": target.relative_to(project).as_posix()}
        if op == "trim_inventory":
            rows = worker_rows(project, key)
            active = [{"task": row["task_key"], "status": row["status"]} for row in rows
                      if row["status"] in {"pending", "running"}]
            return {"workers": active[:20], "active_workers": len(active), "total_workers": len(rows),
                    "plan": str(key_dir / "plan.md")}
        if op == "trim_steer":
            if owners[0]["phase"].upper() != "EXECUTE":
                raise ValueError("a running Worker can only be trimmed in EXECUTE")
            current = inspect(project, key_dir, identifier(req["task"]))
            facts = current["facts"]
            if req["snapshot"] != current["snapshot"] or facts["status"] != "running" or not facts["run_id"]:
                raise ValueError("source run changed or is no longer running; inspect again")
            folder = key_dir / "workers" / facts["task"]
            run = json.loads(body(folder / "run.json"))
            if run.get("status") != "running" or run.get("run_id") != facts["run_id"]:
                raise ValueError("source run is no longer running")
            verification = req["verification"]
            if not isinstance(verification, str) or not re.fullmatch(r"[\w.:-]+(?:\|[\w.:-]+)*", verification) or len(verification) > 256:
                raise ValueError("missing minimum verification tool call ID")
            remaining, stop = (req[name].strip() for name in ("remaining", "stop"))
            if not remaining or not stop or len(remaining) + len(stop) > 4000 or "[dp2-" in remaining + stop:
                raise ValueError("name the remaining work and optional exploration to stop within 4000 characters")
            scope = scope_review.Scope(key_dir)
            if scope.reviews is not None:
                scope.check_plan()
                review = scope.review("replans", digest([current["snapshot"], remaining, stop, verification]))
                if review["anchor"] not in current["coverage"]:
                    raise ValueError("scope-review: running trim must retain an anchor from the original task")
            target = local(folder / "steer-dp2.md")
            if target.exists():
                raise ValueError("this Worker already has a steer; preserve it and check delivery")
            publish_new(target, "[dp2-narrow-request]\n"
                        f"手动 trim，最小验证 tool call {verification}。\n"
                        f"继续完成：{remaining}\n停止可选探索：{stop}\n"
                        "继续遵守原卡范围、必要交付、依赖及证据要求。\n"
                        f"必须保留：{', '.join(current['coverage']) or '原卡的必要验收项'}\n")
            return {"state": "queued", "task": facts["task"], "path": target.relative_to(project).as_posix()}
        if op == "inspect":
            for row in worker_rows(project, key):
                if row["status"] == "failed":
                    capture(project, row, row["status"])
            offset, limit = req.get("offset", 0), req.get("limit", 20)
            result = inspect(project, key_dir, req.get("task"), section=req.get("section", "issues"),
                             offset=offset, limit=limit)
            if not req.get("task"):
                return result
            facts = result["facts"]
            if facts["category"] in {"model-unavailable", "spawn-failed"}:
                target = key_dir / "evidence" / "replan" / (result["issue"] + ".json")
                record = json.loads(body(target))
                record["reviewed_infrastructure"] = facts
                save(target, record)
            # Project-relative locators keep evidence on disk while the snapshot
            # above and preview/apply still use full source files and live rows.
            worker = key_dir / "workers" / facts["task"]
            references = {name: worker / name for name in facts.get("artifacts", [])}
            references.update({"card": key_dir / facts["card"], "task.md": worker / "task.md"})
            progress = run_progress(worker, facts.get("run_id"))
            if progress is None:
                references.pop("run-progress.json", None)
            return {"issue": result["issue"], "snapshot": result["snapshot"], "state": result["state"],
                    "facts": {field: facts[field] for field in ("task", "status", "category", "run_id", "stop_kind")
                              if field in facts},
                    **({"progress": progress} if progress is not None else {}),
                    "acceptance": result["acceptance"], "coverage": result["coverage"],
                    "evidence_refs": {name: file.relative_to(project).as_posix()
                                      for name, file in references.items() if file.is_file() and file.resolve() == file}}
        if op not in ("preview", "apply"):
            raise ValueError("unknown replan operation")
        target = local(key_dir / "evidence" / "replan" / (identifier(req["issue"]) + ".json"))
        record = json.loads(body(target))
        if record["state"] == "applied" and op == "apply" and req["version"] == record["version"]:
            if (record["plan"]["action"] != "schedule" and req.get("decision_id")
                    and req["decision_id"] != record.get("decision_id")):
                raise ValueError("decision_id differs from the applied plan")
            receipt(project, record, req["claim"])
            return {"state": "applied", "version": record["version"], "decision_id": record.get("decision_id"),
                    "source": record.get("decision_source")}
        current = inspect(project, key_dir, record["source"]["task"])
        if current["issue"] != record["id"] or current["snapshot"] != req["snapshot"]:
            raise ValueError("source changed; inspect again")
        if record["state"] == "applied" and record["plan"]["action"] not in {"schedule", "escalate"}:
            raise ValueError("source already handled; select its remaining successor")
        plan = req["plan"] if op == "preview" else record["plan"]
        verdict = preview(project, key_dir, current, plan)
        if op == "preview":
            if record["state"] == "publishing":
                if record["snapshot"] == current["snapshot"]:
                    raise ValueError("resume the partially published version")
                # The queue gate still holds these reservations. Reclaim only exact
                # unpublished bytes after a fresh inspection of the changed source.
                leftovers = [(source_card(key_dir, f"tasks/{u['id']}.md"), card_text(record, u))
                             for u in record["plan"]["units"]]
                if any(p.exists() and body(p) != expected for p, expected in leftovers):
                    raise ValueError("partially published card has independent edits")
                for path, _ in leftovers:
                    path.unlink(missing_ok=True)
            for unit in plan["units"]:
                if source_card(key_dir, f"tasks/{unit['id']}.md").exists():
                    raise ValueError(f"card already exists: {unit['id']}")
            if record["state"] == "applied":
                receipt(project, record, req["claim"])
                record.setdefault("history", []).append({field: record.get(field) for field in
                                                        ("plan", "version", "snapshot", "decision_id", "action_evidence",
                                                         "decision_source", "applied_claim")})
            record.update(state="previewed", source=current["facts"], plan=plan, version=verdict["version"], snapshot=req["snapshot"])
            save(target, record)
            return {**verdict, "snapshot": current["snapshot"], "issue": record["id"],
                    "live_workers": current["live_workers"]}
        if req["version"] != record["version"] or req["version"] != verdict["version"]:
            raise ValueError("stale plan version")
        if plan["action"] != "schedule" and record["source"]["task"] in current["live_workers"]:
            raise ValueError("source worker is still in flight")
        action = plan["action"]
        decision_id = req.get("decision_id") or None
        if action == "escalate" and not decision_id:
            raise ValueError("escalate requires a matching dp-pm-steer decision_id")
        decision_source = "pm"
        if action != "schedule" and decision_id:
            _, events = decision(project, key, record["source"], verdict, decision_id)
            if action in {"direct-exec", "escalate"} and not any(
                    e.get("kind") == "lifecycle" and e.get("lifecycle") == "executed" and e.get("action") == action
                    and e.get("event_id") == req.get("action_evidence") for e in events):
                raise ValueError("actual takeover or escalation needs its executed decision_receipt event_id")
            decision_source = "dp-pm-steer"
        for unit in plan["units"]:
            path = source_card(key_dir, f"tasks/{unit['id']}.md")
            if path.exists() and (record["state"] != "publishing" or body(path) != card_text(record, unit)):
                raise ValueError(f"card collision: {path.name}")
        record.update(state="publishing", key=key, decision_id=decision_id, decision_source=decision_source,
                      applied_claim=req["claim"], action_evidence=req.get("action_evidence"))
        save(target, record)
        for unit in plan["units"]:
            path = source_card(key_dir, f"tasks/{unit['id']}.md")
            if not path.exists():
                publish_new(path, card_text(record, unit))
        record["state"] = "applied"
        save(target, record)
        receipt(project, record, req["claim"])
        return {"state": "applied", **verdict, "decision_id": decision_id, "source": decision_source}


def evidence_takeover_complete(project: Path, key_dir: Path, record: dict, parent: tuple[dict, dict],
                               rows_by_task: dict, dispatched_cards: set[str]) -> bool:
    plan = record["plan"]
    retained = plan.get("retained")
    if (plan["units"] or not isinstance(retained, dict) or not retained
            or not all(isinstance(ref, str) and ref.startswith("evidence/")
            for ref in retained.values()) or record.get("key") != key_dir.name):
        return False
    source = record["source"]
    prior, unit = parent
    try:
        if prior["state"] != "applied" or body(source_card(key_dir, source["card"])) != card_text(prior, unit):
            return False
        if source["status"] == "unstarted":
            if source["card"] in dispatched_cards or source["task"] in rows_by_task:
                return False
        else:
            row = rows_by_task.get(source["task"])
            if not row or row["status"] in {"pending", "running"}:
                return False
            facts = run_facts(key_dir, source["task"], row["status"])
            facts["dispatch_time"] = row.get("dispatched_at")
            if facts != source:
                return False
        current = source_context(key_dir, source)
        if (current["snapshot"] != record["snapshot"] or not set(unit["covers"]) <= retained.keys()
                or set(current["coverage"]) != retained.keys()):
            return False
        proofs = retained_proof(project, key_dir, {**current, "facts": source}, retained)
        return digest([record["id"], current["snapshot"], plan, proofs]) == record["version"]
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False


def unit_dependencies(by_card: dict, record: dict, unit: dict) -> set[str]:
    dependencies = set(unit["depends_on"])
    parent_ref = record["source"]["card"]
    visited = set()
    while parent_ref in by_card:
        if parent_ref in visited:
            raise ValueError("cyclic replan ancestry")
        visited.add(parent_ref)
        parent, original = by_card[parent_ref]
        dependencies.update(original["depends_on"])
        parent_ref = parent["source"]["card"]
    return dependencies


def deadline_successor(project: Path, owner: str, task: str | None, card_ref: str, pin: str, parent: str,
                       *, review: bool = False) -> dict:
    """Verify a frozen replan lineage against the exact timed-out run and live PM claim."""
    key_dir = local(project / ".agenticdoc" / identifier(owner))
    source_task = identifier(parent.partition("@")[0])
    if task is not None and identifier(task) == source_task:
        raise ValueError("deadline successor must use a new task")
    card = source_card(key_dir, card_ref)
    markdown = body(card)
    if (not markdown or cards.card_digest(card) != pin
            or mw_common.read_task_header_scalar(markdown, "parent_worker_run") != parent):
        raise ValueError("deadline successor card or parent pin changed")
    rows = worker_rows(project, owner)
    old = next((r for r in rows if r["task_key"] == source_task and r["status"] == "failed"), None)
    if old is None or Path(old["task_path"]).resolve() != key_dir / "workers" / source_task / "task.md":
        raise ValueError("deadline source has no failed queue row")
    source = run_facts(key_dir, source_task, "failed")
    source["dispatch_time"] = old.get("dispatched_at")
    if source.get("stop_kind") != "worker-deadline" or source.get("run_id") != parent:
        raise ValueError("deadline source identity changed")
    seen = {task} if task is not None else set()
    ancestor = parent
    while ancestor:
        ancestor_task = identifier(ancestor.partition("@")[0])
        if ancestor_task in seen:
            raise ValueError("invalid deadline successor ancestry")
        seen.add(ancestor_task)
        folder = key_dir / "workers" / ancestor_task
        run = json.loads(body(folder / "run.json"))
        if run.get("run_id") != ancestor or run.get("owner_key") != owner or run.get("task_key") != ancestor_task:
            raise ValueError("deadline successor ancestor identity changed")
        if run.get("aborted") is True or run.get("status") in {"canceled", "stopped", "failed-by-stop"}:
            raise ValueError(f"parent-cancel: {ancestor}")
        envelope_parent = mw_common.read_task_header_scalar(body(folder / "task.md"), "parent_worker_run")
        if "parent_worker_run" in run and run["parent_worker_run"] != envelope_parent:
            raise ValueError("deadline successor ancestor binding changed")
        ancestor = envelope_parent
    known = records(key_dir)
    lineage = applied_lineage(known, card_ref)
    if not lineage:
        raise ValueError("deadline successor requires an applied replan for this run and card")
    original = lineage[-1][0]["source"]
    # Older capture recorded the wall timeout and run identity before the
    # structured stop marker and progress digest were added to run facts.
    legacy = ("stop_kind" not in original and "progress_digest" not in original
              and original.get("category") == "wall-timeout"
              and original == {name: value for name, value in source.items()
                               if name not in {"stop_kind", "progress_digest"}})
    if original != source and not legacy:
        raise ValueError("deadline successor requires an applied replan for this run and card")
    if any(card_identity(record["source"]["card"]) == card_identity(card_ref)
           and record["state"] in {"applied", "publishing"} and record["plan"]["action"] != "schedule"
           for record in known):
        raise ValueError("deadline successor was superseded by another replan")
    index = [r for r in state.read_index(project) if r["key"].casefold() == owner.casefold()]
    if (len(index) != 1 or index[0]["key"] != owner or index[0]["status"] != "active"
            or index[0]["phase"] != "EXECUTE"):
        raise ValueError("deadline successor requires a current PM claim in EXECUTE")
    claim = index[0]["claim_id"]
    if not claim or claim in {"—", "-"}:
        raise ValueError("deadline successor PM claim is unavailable")
    dispatched_tasks = {row["task_key"] for row in rows}
    dispatched_cards = {card_identity(mw_common.read_task_header_scalar(
        body(key_dir / "workers" / identifier(row["task_key"]) / "task.md"), "card_path") or "") for row in rows}
    verified, historical = [], []
    for record, unit in lineage:
        facts = record["source"]
        if facts["status"] == "unstarted" and (
                facts["run_id"] is not None or facts["task"] in dispatched_tasks
                or card_identity(facts["card"]) in dispatched_cards):
            raise ValueError("deadline successor intermediate source is no longer unstarted")
        produced = source_card(key_dir, f"tasks/{unit['id']}.md")
        if record.get("key") != owner or body(produced) != card_text(record, unit):
            raise ValueError("deadline successor card or source evidence changed")
        observed = source if record is lineage[-1][0] else facts
        current = source_context(key_dir, observed)
        if observed != facts or current["snapshot"] != record["snapshot"]:
            historical.append({"card": f"tasks/{unit['id']}.md", "source_card": facts["card"],
                               "record": f"evidence/replan/{record['id']}.json", "recorded": record["snapshot"],
                               "observed": current["snapshot"]})
        proofs = retained_proof(project, key_dir, {**current, "facts": facts}, record["plan"].get("retained", {}))
        version_fields = [record["id"], record["snapshot"], record["plan"]]
        if proofs:
            version_fields.append(proofs)
        version = digest(version_fields)
        if record["version"] != version:
            raise ValueError("deadline successor plan version changed")
        decision_ref = record.get("decision_id")
        if not decision_ref:
            applied_claim = record.get("applied_claim")
            if (record.get("decision_source") != "pm" or not isinstance(applied_claim, str)
                    or applied_claim in {"", "—", "-"} or (not verified and applied_claim != claim)):
                raise ValueError("deadline successor PM publication belongs to another claim or is missing")
            verified.append({"card": f"tasks/{unit['id']}.md", "decision": None, "version": version})
            continue
        _, events = decision(project, owner, facts, {
            "action": record["plan"]["action"], "basis_id": "replan-" + version[:24]}, decision_ref)
        actors = []
        for stage, prefix in (("executed", "replan-exec-"), ("settled", "replan-settle-")):
            matches = [e["actor"] for e in events if e.get("kind") == "lifecycle"
                       and e.get("lifecycle") == stage and e.get("event_id") == prefix + version[:24]]
            if (len(matches) != 1 or matches[0].get("kind") != "system"
                    or not matches[0].get("id", "").startswith("pm:")):
                raise ValueError("deadline successor PM decision receipt is missing or invalid")
            actors.append(matches[0]["id"])
        if actors[0] != actors[1] or (not verified and actors[0] != "pm:" + claim):
            raise ValueError("deadline successor PM decision receipt belongs to another claim")
        verified.append({"card": f"tasks/{unit['id']}.md", "decision": decision_ref, "version": version})
    approval = {"project": str(project), "key": owner, "parent": parent, "decision": verified[0]["decision"],
                "version": verified[0]["version"], "claim": claim}
    if len(verified) > 1:
        approval["lineage"] = list(reversed(verified))
    if historical:
        approval["card"] = card_ref
        approval["pin"] = pin
        approval["historical_review"] = {"legacy_timeout": legacy, "snapshots": list(reversed(historical))}
        if not review:
            target = local(key_dir / "evidence" / "deadline-recovery" / f"{digest(approval)}.json")
            saved = json.loads(body(target) or "{}")
            if saved.get("approval") != approval or not saved.get("reason"):
                raise ValueError("deadline successor source evidence changed; inspect and authorize deadline recovery")
    return approval


def deadline_budget(project: Path, owner: str, task: str, card_ref: str, pin: str,
                    approval: dict, envelope: str) -> dict:
    """Read the fixed allocation and recheck the PM authority and durable budget event."""
    if not re.fullmatch(r"[0-9a-f]{64}", pin):
        raise ValueError("invalid deadline successor card pin")
    root = project / ".agenticdoc"
    file = local(root / "_runtime" / "fixed-child-budgets" / owner / f"deadline-{pin}.json")
    child_run = local(root / owner / "workers" / identifier(task) / "run.json")
    if (Path(str(file) + ".cancelled")).exists():
        raise ValueError("user-stop: deadline successor allocation cancelled")
    if not file.is_file() or local(Path(str(file) + ".started")).exists() or child_run.exists():
        raise ValueError("deadline successor allocation is missing or already started")
    grant = json.loads(body(file))
    if (grant.get("approval") != approval or grant.get("task") != task or grant.get("card") != card_ref
            or grant.get("pin") != pin):
        raise ValueError("deadline successor allocation binding mismatch")
    now = datetime.now().astimezone()
    deadline = timestamp(grant["deadline"])
    if (deadline is None or now >= deadline or type(grant.get("steps")) is not int or grant["steps"] < 1
            or type(grant.get("cost")) is not int or grant["cost"] < grant["steps"]):
        raise ValueError("deadline successor allocation expired or invalid")
    authority = grant["authority"]
    channel = local(Path(authority["channel"]))
    channel_id = hashlib.sha256(os.path.normcase(str(project)).encode("utf-8")).hexdigest()
    if channel != Path.home().resolve() / ".mw-pm-channel" / channel_id:
        raise ValueError("deadline successor channel belongs to another project")
    request_path, receipt_path = (local(channel / authority[name]) for name in ("request", "receipt"))
    if (not request_path.is_relative_to(channel) or not receipt_path.is_relative_to(channel)
            or request_path.parent != receipt_path.parent
            or request_path.name != f"{authority['event_id']}.request.json"
            or receipt_path.name != f"{authority['event_id']}.receipt.json"):
        raise ValueError("deadline successor channel references are invalid")
    request_bytes = deadline_authority_path(request_path).read_bytes()
    if hashlib.sha256(request_bytes).hexdigest() != authority["request_sha256"]:
        raise ValueError("deadline successor stage request changed")
    request = json.loads(request_bytes)
    receipt = json.loads(deadline_authority_path(receipt_path).read_bytes())
    binding = request["binding"]
    for record in (request, receipt):
        if (record.get("id") != authority["event_id"] or record.get("key") != owner
                or record.get("claim") != approval["claim"] or record.get("binding") != binding):
            raise ValueError("deadline successor stage binding changed")
    stage = request["stage"]
    stage_deadline = timestamp(stage["deadline"])
    if (stage.get("project_ref") != channel_id or stage.get("key") != owner
            or stage.get("card_path") != authority["stage_card"] or stage.get("card_sha256") != authority["stage_pin"]
            or receipt.get("state") != "started" or receipt.get("session") != authority["session_id"]
            or receipt.get("stage_digest") != authority["grant_digest"] or stage_deadline is None
            or deadline > stage_deadline or grant["steps"] > stage["max_steps"]
            or grant["cost"] > stage["remaining_cost"]):
        raise ValueError("deadline successor PM stage revoked or exhausted")
    child_card = body(source_card(root / owner, card_ref))
    targets = cards._card_write_face_entries({"extras": cards.extract_card_extras(child_card)})
    if targets is None or not set(targets) <= set(stage["write_face"]):
        raise ValueError("deadline successor write scope exceeds the authorized PM stage")
    if cards.parse_workspace_write_face(project, envelope) != plan_face(project, child_card):
        raise ValueError("deadline successor envelope write scope differs from its frozen card")
    if "duty" in request:
        duty = request["duty"]
        shift = duty["shift"]
        if not isinstance(shift, str) or not re.fullmatch(r"[a-z0-9-]{1,80}", shift):
            raise ValueError("invalid deadline successor duty reference")
        folder = local(root / owner / "duty" / shift)
        current = local(folder / "current.json")
        stop_hash = hashlib.sha256(current.read_bytes()).hexdigest() if current.is_file() else "missing"
        if (now.timestamp() * 1000 >= duty["until"] or (folder / "STOP").exists() or stop_hash != duty["stopHash"]):
            raise ValueError("user-stop: deadline successor duty revoked")
    stage_card = local(root / owner / authority["stage_card"])
    if (not stage_card.is_relative_to(root / owner / "tasks") or not stage_card.is_file()
            or cards.card_digest(stage_card) != authority["stage_pin"]):
        raise ValueError("deadline successor PM stage card changed")
    session = deadline_authority_path(local(Path(authority["session"])))
    if session.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("deadline successor budget journal exceeds read bound")
    reservation = "deadline:" + json.dumps([owner, pin], separators=(",", ":"))
    reservations = []
    with session.open(encoding="utf-8") as lines:
        header = json.loads(next(lines, "{}"))
        if header.get("type") != "session" or header.get("id") != authority["session_id"]:
            raise ValueError("deadline successor budget session changed")
        for line in lines:
            point = json.loads(line)
            if point.get("type") != "custom" or point.get("customType") != "mw-runtime-budget-v1":
                continue
            data = point["data"]
            if data.get("unit") != authority["unit"] or data.get("kind") != "event":
                continue
            event = data["event"]
            reserved = event["request"]
            if reserved.get("reservation_id") != reservation:
                continue
            if (data.get("key") != owner or data.get("claim_id") != approval["claim"]
                    or data.get("source_pin") != authority["stage_pin"] or event.get("kind") != "reserve-child"):
                raise ValueError("deadline successor budget reservation changed or settled")
            reservations.append(reserved)
    if (len(reservations) != 1 or reservations[0].get("deadline") != grant["deadline"]
            or reservations[0].get("cost") != grant["cost"]
            or min(reservations[0]["steps"], reservations[0]["cost"]) != grant["steps"]):
        raise ValueError("deadline successor budget reservation is missing or mismatched")
    return {"steps": grant["steps"], "deadline": grant["deadline"]}


def deadline_authority_path(file: Path) -> Path:
    # Channel paths include a project hash and two UUIDs. A long profile path
    # can exceed Win32 MAX_PATH even when the files were created by Node.
    if os.name != "nt" or len(str(file)) < 260:
        return file
    absolute = str(file)
    prefix = "\\\\?\\"
    if absolute.startswith("\\\\"):
        return Path(prefix + "UNC\\" + absolute[2:])
    return Path(prefix + absolute)


def scope_dispatch_refusal(key_dir: Path, ref: str, pin: str | None, *, allow_cardless: bool = False) -> str | None:
    if not ref and allow_cardless:
        return None
    try:
        scope = scope_review.Scope(key_dir)
        if scope.reviews is None:
            return None
        scope.check_plan()
        review = scope.check_card(ref, pin)
        anchors = scope.task_anchors.get(Path(ref).stem.casefold().removeprefix("t-"), set())
        if review["anchor"] in anchors:
            return None
        lineage = applied_lineage(records(key_dir), card_identity(ref))
        if lineage:
            record, unit = lineage[0]
            scope.review("replans", record["version"])
            if review["anchor"] in unit["covers"] and body(key_dir / ref) == card_text(record, unit):
                return None
        raise ValueError(f"{ref}: scope anchor must be assigned by the retained plan or an applied replan")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f"scope-review: {exc}"


def admission(project: Path, owner: str, task: str, ref: str, *, attempt: int = 1,
              card_hash: str | None = None, supersedes: str | None = None,
              allow_cardless: bool = False, check_scope: bool = True) -> str | None:
    """Called under workers.lock before any dispatch writes. No nested lock."""
    key_dir = local(project / ".agenticdoc" / identifier(owner))
    if check_scope and (reason := scope_dispatch_refusal(key_dir, ref, card_hash, allow_cardless=allow_cardless)):
        return reason
    ref = card_identity(ref)
    rows = worker_rows(project, owner)
    previous_task = supersedes or (re.sub(r"-a\d+$", "", task) if attempt > 1 else task)
    for row in rows:
        if row["status"] not in {"failed", "needs-clarification", "lost"}:
            continue
        old_task = row["task_key"]
        same_attempt_family = (attempt > 1 and row.get("origin") == "conductor"
                               and re.sub(r"-a\d+$", "", old_task) == previous_task)
        if old_task != task and old_task != previous_task and not same_attempt_family:
            envelope = key_dir / "workers" / identifier(old_task) / "task.md"
            if not ref or card_identity(mw_common.read_task_header_scalar(body(envelope), "card_path") or "") != ref:
                continue
        capture(project, row, row["status"], retry=True)
    known = records(key_dir)
    for record in known:
        source = record["source"]
        approved = (record["state"] == "applied" and any(ref == card_identity(f"tasks/{u['id']}.md") for u in record["plan"]["units"]))
        retry_family = attempt > 1 and re.sub(r"-a\d+$", "", source["task"]) == previous_task
        if task == source["task"] or ((previous_task == source["task"] or retry_family) and not approved) or ref and source["card"] == ref:
            if (task != source["task"] and record["state"] == "open"
                    and record.get("reviewed_infrastructure") == source):
                continue
            if (source["status"] in {"failed", "needs-clarification", "lost"}
                    or record["state"] in {"publishing", "applied"} and record["plan"]["action"] != "schedule"):
                return f"replan-required:{record['id']} source={source['task']} state={record['state']}"
    by_card = {card_identity(f"tasks/{u['id']}.md"): (r, u) for r in known if r["state"] in {"publishing", "applied"}
               for u in r["plan"]["units"]}
    if ref not in by_card:
        return None
    record, unit = by_card[ref]
    if record["state"] != "applied":
        return "replan-plan-not-published"
    path = source_card(key_dir, ref)
    if body(path) != card_text(record, unit) or (card_hash and cards.card_digest(path) != card_hash):
        return "replan-card-drift"
    try:
        lineage = applied_lineage(known, ref)
    except ValueError as exc:
        return f"replan-lineage-invalid:{exc}"
    source = lineage[-1][0]["source"]
    if (source.get("stop_kind") == "worker-deadline"
            and mw_common.read_task_header_scalar(body(path), "parent_worker_run") != source["run_id"]):
        return f"replan-deadline-parent-required:{source['run_id']}"
    done, dispatched_cards = set(), set()
    for row in rows:
        folder = key_dir / "workers" / identifier(row["task_key"])
        head = body(folder / "task.md")
        used = card_identity(mw_common.read_task_header_scalar(head, "card_path") or "")
        dispatched_cards.add(used)
        if used == ref:
            reviewed = [r for r in known if r["source"]["task"] == row["task_key"]
                        and r["state"] == "open" and r.get("reviewed_infrastructure") == r["source"]
                        and r["source"]["category"] in {"model-unavailable", "spawn-failed"}]
            if row["status"] not in {"failed", "lost"} or not reviewed or task == row["task_key"]:
                return f"replan-already-dispatched:{row['task_key']}"
        if used in by_card and row["status"] == "done" and mw_common.read_run_status(folder) == "done":
            prior, pred = by_card[used]
            expected_hash = hashlib.sha256(card_text(prior, pred).encode()).hexdigest()
            if mw_common.read_task_header_scalar(head, "card_sha256") == expected_hash:
                done.add(pred["id"])
        if row["status"] in {"pending", "running"}:
            other = by_card.get(used)
            resources = unit.get("resources")
            other_resources = other[1].get("resources") if other else None
            if resources is None or (other_resources is None and resources) or (
                    other_resources and set(resources).intersection(other_resources)):
                return f"replan-resource-busy:{row['task_key']}"
    # A dependent keeps its original edge when an upstream card is split again
    # or closed by the PM. A takeover still inherits the card's prerequisites.
    replacements = {by_card[r["source"]["card"]][1]["id"]: {u["id"] for u in r["plan"]["units"]}
                    for r in known if r["state"] == "applied" and r["plan"]["action"] in {"split", "narrow"}
                    and r["source"]["card"] in by_card
                    and all(str(ref).startswith("evidence/") for ref in r["plan"].get("retained", {}).values())}
    rows_by_task = {row["task_key"]: row for row in rows}
    for r in known:
        parent = by_card.get(r["source"]["card"])
        if (parent and r["state"] == "applied" and r["plan"]["action"] == "direct-exec"
                and evidence_takeover_complete(project, key_dir, r, parent, rows_by_task, dispatched_cards)):
            replacements.setdefault(parent[1]["id"], unit_dependencies(by_card, *parent))
    while newly_done := {stem for stem, children in replacements.items() if children <= done} - done:
        done.update(newly_done)
    missing = unit_dependencies(by_card, record, unit) - done
    return "replan-dependency-pending:" + ",".join(sorted(missing)) if missing else None


def collect_terminal(project: Path, row: dict, status: str) -> None:
    if status == "failed":
        try:
            with locked(mw_common.lock_path(project)):
                capture(project.resolve(), row, status)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"[replan] {row.get('task_key')}: collection deferred: {exc}", file=sys.stderr, flush=True)


def main() -> None:
    try:
        req = json.load(sys.stdin)
        project = Path(req["project"]).resolve(strict=True)
        if req["operation"] == "admission":
            reason = admission(project, req["key"], req["task"], req["card"], card_hash=req.get("card_hash"),
                               supersedes=req.get("supersedes"))
            result = {"ok": reason is None, "reason": reason}
        elif req["operation"] == "deadline-successor":
            result = {"ok": True, "approval": deadline_successor(
                project, req["key"], req["task"], req["card"], req["card_hash"], req["parent"])}
            if req.get("budget") is True:
                result["allocation"] = deadline_budget(
                    project, req["key"], req["task"], req["card"], req["card_hash"], result["approval"], req["envelope"])
        else:
            result = {"ok": True, **execute(project, req)}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, CycleError) as exc:
        result = {"ok": False, "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
