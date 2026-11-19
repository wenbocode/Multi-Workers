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
    return {"task": task, "run_id": rid, "status": status, "category": category,
            "elapsed_seconds": elapsed, "timeout_minutes": timeout,
            "card": card, "started": started, "ended": ended,
            "artifacts": [p for p in ("output.md", "report.md", "progress.md", "run.json", "trace.log")
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
    return {"issue": record["id"], "snapshot": snapshot, "state": record["state"], "facts": facts,
            "acceptance": acceptance, "coverage": coverage, "closure": closure,
            "live_workers": [r["task_key"] for r in rows if r["status"] in {"pending", "running"}]}


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
    roots = cards.write_face_roots(project)
    return write_face.parse_write_face(cards.render_write_face_line(entries or []), base=str(project),
                                       roots=roots, case_insensitive=os.name == "nt",
                                       canonicalize=cards.canonical_write_face_path if roots else None)


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
            raise ValueError(f"{stem}: invalid write face")
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
        gate = admission(project, key_dir.name, current["facts"]["task"], source_ref)
        if gate and gate.startswith("replan-dependency-pending:"):
            inherited = gate.partition(":")[2].split(",")
            for stem in ordered:
                waiting[stem].extend(inherited)
    known_resources = {card_identity(f"tasks/{u['id']}.md"): u.get("resources") for r in records(key_dir)
                       if r["state"] == "applied" for u in r["plan"]["units"]}
    for live in current["live_workers"]:
        head = body(key_dir / "workers" / identifier(live) / "task.md")
        roots = cards.write_face_roots(project)
        face = write_face.parse_write_face(head, base=str(project), case_insensitive=os.name == "nt",
                                           roots=roots, canonicalize=cards.canonical_write_face_path if roots else None)
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
    if action == "schedule":
        return
    ref = record["decision_id"]
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
            return {"issue": result["issue"], "snapshot": result["snapshot"], "state": result["state"],
                    "facts": {field: facts[field] for field in ("task", "status", "category")},
                    "acceptance": result["acceptance"], "coverage": result["coverage"],
                    "evidence_refs": {name: file.relative_to(project).as_posix()
                                      for name, file in references.items() if file.is_file() and file.resolve() == file}}
        if op not in ("preview", "apply"):
            raise ValueError("unknown replan operation")
        target = local(key_dir / "evidence" / "replan" / (identifier(req["issue"]) + ".json"))
        record = json.loads(body(target))
        if record["state"] == "applied" and op == "apply" and req["version"] == record["version"]:
            receipt(project, record, req["claim"])
            return {"state": "applied", "version": record["version"], "decision_id": record.get("decision_id")}
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
                                                        ("plan", "version", "snapshot", "decision_id", "action_evidence")})
            record.update(state="previewed", source=current["facts"], plan=plan, version=verdict["version"], snapshot=req["snapshot"])
            save(target, record)
            return {**verdict, "snapshot": current["snapshot"], "issue": record["id"],
                    "live_workers": current["live_workers"]}
        if req["version"] != record["version"] or req["version"] != verdict["version"]:
            raise ValueError("stale plan version")
        if plan["action"] != "schedule" and record["source"]["task"] in current["live_workers"]:
            raise ValueError("source worker is still in flight")
        action = plan["action"]
        if action != "schedule":
            _, events = decision(project, key, record["source"], verdict, req["decision_id"])
            if action in {"direct-exec", "escalate"} and not any(
                    e.get("kind") == "lifecycle" and e.get("lifecycle") == "executed" and e.get("action") == action
                    and e.get("event_id") == req.get("action_evidence") for e in events):
                raise ValueError("actual takeover or escalation needs its executed decision_receipt event_id")
        for unit in plan["units"]:
            path = source_card(key_dir, f"tasks/{unit['id']}.md")
            if path.exists() and (record["state"] != "publishing" or body(path) != card_text(record, unit)):
                raise ValueError(f"card collision: {path.name}")
        record.update(state="publishing", key=key, decision_id=req.get("decision_id"), action_evidence=req.get("action_evidence"))
        save(target, record)
        for unit in plan["units"]:
            path = source_card(key_dir, f"tasks/{unit['id']}.md")
            if not path.exists():
                publish_new(path, card_text(record, unit))
        record["state"] = "applied"
        save(target, record)
        receipt(project, record, req["claim"])
        return {"state": "applied", **verdict, "decision_id": record["decision_id"]}


def admission(project: Path, owner: str, task: str, ref: str, *, attempt: int = 1,
              card_hash: str | None = None, supersedes: str | None = None) -> str | None:
    """Called under workers.lock before any dispatch writes. No nested lock."""
    ref = card_identity(ref)
    key_dir = local(project / ".agenticdoc" / identifier(owner))
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
    done = set()
    for row in rows:
        folder = key_dir / "workers" / identifier(row["task_key"])
        head = body(folder / "task.md")
        used = card_identity(mw_common.read_task_header_scalar(head, "card_path") or "")
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
    # A dependent keeps its original edge when an upstream card is split again.
    replacements = {by_card[r["source"]["card"]][1]["id"]: {u["id"] for u in r["plan"]["units"]}
                    for r in known if r["state"] == "applied" and r["plan"]["action"] in {"split", "narrow"}
                    and r["source"]["card"] in by_card
                    and all(str(ref).startswith("evidence/") for ref in r["plan"].get("retained", {}).values())}
    while newly_done := {stem for stem, children in replacements.items() if children <= done} - done:
        done.update(newly_done)
    dependencies = set(unit["depends_on"])
    parent_ref = record["source"]["card"]
    while parent_ref in by_card:
        parent, original = by_card[parent_ref]
        dependencies.update(original["depends_on"])
        parent_ref = parent["source"]["card"]
    missing = dependencies - done
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
        else:
            result = {"ok": True, **execute(project, req)}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, CycleError) as exc:
        result = {"ok": False, "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
