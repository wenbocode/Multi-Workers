"""Local decision drafts. A repair handle addresses one value in one owner's draft."""

import copy
import datetime
import hashlib
import json
import os
import re
import uuid

import decision
from mw_common import acquire_lock, release_lock
from pm_state import atomic_write, child


FIELDS = {"material", "preparation", "context", "evidence_refs", "question", "note", "task_before"}
EDITABLE = {"material", "preparation", "context", "evidence_refs", "task_before"}
MISSING = object()
REPAIR_LIMIT = 3


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def locate(book, path):
    value = book
    for part in path:
        if isinstance(value, list) and isinstance(part, int) and 0 <= part < len(value):
            value = value[part]
        elif isinstance(value, dict):
            value = value.get(part, MISSING)
        else:
            return MISSING
    return value


def targets(book, issue):
    field = issue.get("field", "")
    if not isinstance(field, str) or issue.get("code") == "qg-independent-review-required":
        return []
    refs = book.get("evidence_refs")
    if not isinstance(refs, list):
        refs = []
    if issue.get("code") == "evidence-range-out-of-bounds":
        matches = [ref for ref in refs if isinstance(ref, dict) and ref.get("field") == field
                   and ref.get("lines") == issue.get("requested_lines")]
        if len(matches) > 1:
            matches = [ref for ref in matches if ref.get("path") == issue.get("path")]
        if len(matches) == 1 and isinstance(matches[0].get("path"), str):
            ref = matches[0]
            index = refs.index(ref)
            return [(["evidence_refs", index, "lines", name], f"evidence_refs[{index}].lines.{name}")
                    for name in ("start", "end")]
    path = [int(index) if index else name for name, index in re.findall(r"([\w-]+)|\[(\d+)\]", field)]
    if not path:
        return []
    if path[0] not in EDITABLE:
        if path[0] in {"meta", "parent_decision_ref", "actor_role", "model_context"}:
            return []
        path.insert(0, "preparation" if path[0] in {"prepared_at", "basis_catalog"} else "material")
    if "<" in field:
        return []
    return [(path, field)]


def lineage(versions, path):
    # An index remains meaningful until an edit replaces the row or its container.
    return [versions.get(json.dumps(path[:n]), 0) for n in range(1, len(path))]


def correction(state, path, label):
    before = locate(state["book"], path)
    expected = None if before is MISSING else digest(before)
    parents = lineage(state["versions"], path)
    handle = digest([state["id"], path, expected, parents])
    state["handles"][handle] = {"path": path, "before": expected, "label": label, "parents": parents}
    return {"repair_id": handle, "field": label}


def merge(state, changes):
    candidate = copy.deepcopy(state["book"])
    versions = state["versions"].copy()
    conflicts = []
    for edit in changes:
        handle = state["handles"].get(edit["repair_id"])
        if handle is None:
            raise ValueError("unknown repair id for this draft")
        path = handle["path"]
        current = locate(candidate, path)
        value = edit["value"]
        same_row = lineage(versions, path) == handle["parents"]
        if same_row and current is not MISSING and digest(current) == digest(value):
            continue
        if not same_row or (None if current is MISSING else digest(current)) != handle["before"]:
            conflicts.append({**correction(state, path, handle["label"]),
                              **({"current": current} if current is not MISSING else {})})
            continue
        parent = candidate
        for part in path[:-1]:
            if isinstance(parent, dict) and isinstance(part, str):
                parent = parent.setdefault(part, {})
            else:
                parent = locate(parent, [part])
        leaf = path[-1]
        if isinstance(parent, dict) and isinstance(leaf, str):
            parent[leaf] = value
        elif isinstance(parent, list) and isinstance(leaf, int) and 0 <= leaf < len(parent):
            parent[leaf] = value
        else:
            raise ValueError("repair target no longer exists; inspect the current draft")
        key = json.dumps(path)
        versions[key] = versions.get(key, 0) + 1
    if not conflicts:
        state["book"] = candidate
        state["versions"] = versions
    return conflicts


def progress_key(issue):
    fields = [repair["field"] for repair in issue.get("repairs", [])]
    return [issue.get("code"), issue["field"], fields or issue.get("path")]


def repair_step(state, result, evidence, before):
    loop = state["repair_loop"]
    previous = loop.get("result")
    status = result["status"]
    if status not in {"needs-repair", "ready"}:
        return result
    revision = digest([state["book"], evidence, result.get("snapshot")])
    if previous and revision in loop["seen"] and status != "ready":
        return {**previous, "replayed": True}
    loop["seen"].append(revision)
    if previous and previous["status"] == "needs-repair" and before != state["book"]:
        old_issues = previous["issues"]
        active = {digest(progress_key(issue)) for issue in result["issues"]}
        resolved = False
        still_open = False
        changed_fields = []
        for issue in old_issues:
            edits = []
            for item in issue.get("repairs", []):
                path = state["handles"][item["repair_id"]]["path"]
                old, new = locate(before, path), locate(state["book"], path)
                if old != new:
                    edits.append({"field": item["field"], "before": digest(old) if old is not MISSING else None,
                                  "after": digest(new) if new is not MISSING else None})
            if not edits:
                continue
            changed_fields.extend(edits)
            if digest(progress_key(issue)) in active:
                still_open = True
            elif status == "ready" or (not result.get("truncated") and issue.get("check") in result.get("checks", [])):
                resolved = True
        if resolved:
            loop["failures"] = 0
            loop["attempts"] = []
        elif still_open:
            loop["failures"] += 1
            loop["attempts"].append({"revision": revision, "changes": changed_fields,
                                     "issues": [progress_key(issue) for issue in result["issues"]]})
    if status == "ready":
        loop.update(failures=0, attempts=[], seen=[])
    else:
        loop["had_gap"] = True
    if loop["failures"] >= REPAIR_LIMIT:
        result.update(status="paused", attempts=loop["attempts"])
        loop["paused_at"] = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    result["consecutive_no_progress"] = loop["failures"]
    loop["result"] = result
    return result


def next_step(result, ref, role):
    status = result["status"]
    if status == "paused":
        return {"owner": "pm", "action": "review-material-recovery", "draft_ref": ref,
                "done_when": "New evidence for the remaining gap or explicit recovery approval is recorded."}
    if status == "review":
        return {"owner": role, "action": "review-draft", "draft_ref": ref,
                "done_when": "Confirm the changed evidence or resolve the field conflict, then resubmit the draft."}
    if status != "needs-repair":
        return None
    for issue in result["issues"]:
        if issue.get("repairs"):
            return {"owner": role, "action": "repair-material", "draft_ref": ref,
                    "field": issue["field"], "repairs": issue["repairs"],
                    "done_when": "Resubmit the corrected draft and verify that this diagnostic is resolved."}
        if issue.get("code") == "qg-independent-review-required":
            return {"owner": "pm", "action": "collect-independent-review", "draft_ref": ref,
                    "field": issue["field"],
                    "done_when": "Record an independent review bound to the current key and criteria, then resubmit this draft."}
    return {"owner": role, "action": "inspect-material", "draft_ref": ref, "field": result["issues"][0]["field"],
            "done_when": "Verify the cited requirement and supply a supported correction."}


def replace_book(state, book):
    before = state["book"]
    if book is None or before == book:
        return
    state["book"] = book
    for field in before.keys() | book.keys():
        if locate(before, [field]) != locate(book, [field]):
            key = json.dumps([field])
            state["versions"][key] = state["versions"].get(key, 0) + 1


def save_draft(path, state):
    encoded = json.dumps(state, ensure_ascii=False).encode()
    if len(encoded) > 2 * 1024 * 1024:
        raise ValueError("draft exceeds storage limit")
    atomic_write(path, encoded, expected=None)


def operate(directory, binding, request, inspect, redactor, *, scope=None, recovery=None, recorded=None):
    ref = request.get("draft_ref")
    opening = ref is None
    tracked = scope is not None
    previous_ref = None
    if opening:
        ref = digest(scope)[:32] if tracked else uuid.uuid4().hex
    if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{32}", ref):
        raise ValueError("invalid draft reference")
    if tracked and ref != (canonical := digest(scope)[:32]):
        previous_ref, ref = ref, canonical
    if request.get("lookup") is True and not directory.is_dir():
        return {"status": "absent"}
    directory.mkdir(parents=True, exist_ok=True)
    path = child(directory, ref + ".json")
    lock = child(directory, ref + ".lock")
    fd = acquire_lock(lock, deadline_s=2, delete_on_close=os.name == "nt")
    try:
        new = not path.is_file() and (opening or previous_ref is not None)
        if not new:
            if not path.is_file() and request.get("lookup") is True:
                return {"status": "absent"}
            state = json.loads(path.read_bytes())
            if (state.get("scope") != scope if tracked else state["binding"] != binding):
                raise ValueError("draft belongs to another actor or matter")
            if tracked and request.get("lookup") is True:
                loop = state["repair_loop"]
                if loop.get("pending_action"):
                    return {"status": "effect-unknown", "draft_ref": ref}
                stored = loop.get("result") or {}
                matching = request.get("book") == state["book"]
                if matching and loop.get("recorded_action", {}).get("book") == digest(state["book"]):
                    return {"status": "recorded", "draft_ref": ref}
                return {"status": stored.get("status", "absent"), "draft_ref": ref,
                        "matches": matching}
            if previous_ref is not None and previous_ref != state.get("previous_ref"):
                raise ValueError("continue using the current draft reference for this matter")
        elif request.get("lookup") is True:
            return {"status": "absent"}
        book = request.get("book") if opening else None
        if opening:
            if not isinstance(book, dict) or set(book) - FIELDS:
                raise ValueError("invalid draft material")
        if new:
            if previous_ref is not None:
                state = json.loads(child(directory, previous_ref + ".json").read_bytes())
                if state["binding"] != binding or "scope" in state:
                    raise ValueError("draft belongs to another actor or matter")
                state.update(id=ref, previous_ref=previous_ref)
            else:
                state = {"id": ref, "binding": binding, "book": book, "handles": {}, "versions": {}, "snapshot": None, "evidence": {}}
            if tracked:
                state.update(scope=scope, repair_loop={"failures": 0, "attempts": [], "seen": [], "used_recovery": []})
        changes = request.get("changes", [])
        if not isinstance(changes, list) or any(not isinstance(item, dict) or set(item) != {"repair_id", "value"}
                                                or not isinstance(item["repair_id"], str) for item in changes):
            raise ValueError("changes must contain repair_id and value")
        local_issues = request.get("local_issues", [])
        if not isinstance(local_issues, list) or any(not isinstance(i, dict) or not isinstance(i.get("field"), str)
                                                      for i in local_issues):
            raise ValueError("invalid local issue list")
        if decision.secret_hit(json.dumps([state["book"], book, changes, local_issues], ensure_ascii=False), redactor):
            raise ValueError("redact credential-looking input before saving a draft")
        before = state["book"]
        loop = state.get("repair_loop")
        if loop is not None:
            pending = request.get("hold_action")
            if pending is not None:
                if not isinstance(pending, str) or not re.fullmatch(re.escape(binding[0]) + r":[A-Za-z0-9_-]{1,80}", pending):
                    raise ValueError("invalid decision action reference")
                if not loop.get("pending_action"):
                    replace_book(state, book)
                    state["snapshot"] = None
                    loop.update(pending_action=pending, result=None)
                    loop.pop("recorded_action", None)
                    save_draft(path, state)
            if pending := loop.get("pending_action"):
                action = {"owner": binding[3], "action": "reconcile-action", "action_ref": pending,
                          "draft_ref": ref, "done_when": "Verify the original decision or signed result before sending again."}
                if request.get("hold_action") is None and recorded is not None and recorded(pending):
                    loop.pop("pending_action")
                    loop["recorded_action"] = {"ref": pending, "book": digest(before)}
                    save_draft(path, state)
                    action["done_when"] = "Read the recorded result by resubmitting this draft with its original action reference."
                    return {"status": "review", "stage": "result-reconciliation", "transport": "not-sent",
                            "draft_ref": ref, "next": action}
                return {"status": "effect-unknown", "stage": "result-reconciliation", "transport": "not-sent",
                        "draft_ref": ref, "next": action}
        previous = loop.get("result") if loop else None
        if previous and previous["status"] == "paused":
            checked, current_evidence = inspect(before)
            present = {(issue.get("code"), issue["field"], issue.get("path")) for issue in checked["issues"]}
            relevant = {issue["path"] for issue in previous["issues"] if issue.get("path")
                        and (issue.get("code"), issue["field"], issue["path"]) not in present
                        and (checked["status"] == "ready" or (not checked.get("truncated")
                             and issue.get("check") in checked.get("checks", [])))}
            evidence_changed = any(old != current_evidence.get(path) and current_evidence.get(path) is not None
                                   for path, old in state["evidence"].items()
                                   if any(path.replace("\\", "/").endswith("/" + item) for item in relevant))
            approved = recovery and recovery[0] not in loop["used_recovery"] and recovery[1] >= loop["paused_at"]
            if not evidence_changed and not approved:
                return {**previous, "draft_ref": ref, "stage": "material-preparation", "transport": "not-sent",
                        "next": next_step(previous, ref, binding[3])}
            if approved:
                loop["used_recovery"].append(recovery[0])
            loop.update(failures=0, attempts=[], result=None)
        if tracked and state["binding"][4] != binding[4]:
            state["binding"] = binding
            save_draft(path, state)
            result = {"status": "review", "issues": [{"field": "draft", "issue": "verify the previous owner's draft before continuing"}]}
            return {**result, "draft_ref": ref, "stage": "material-preparation",
                    "transport": "not-sent", "next": next_step(result, ref, binding[3])}
        replace_book(state, book)
        conflicts = merge(state, changes)
        if conflicts:
            result = {"status": "review", "conflicts": conflicts, "issues": [{"field": "changes",
                      "issue": "review the current value and resubmit the intended changes"}]}
        else:
            result, evidence = inspect(state["book"])
            if "book_digest" in request and request["book_digest"] != digest(state["book"]):
                return {"draft_ref": ref, "status": "review", "transport": "not-sent",
                        "issues": [{"field": "changes", "issue": "draft changed during validation; inspect the current draft"}]}
            if opening or "book_digest" in request:
                result["issues"].extend(local_issues)
                if local_issues:
                    result.update(status="needs-repair", unchecked=["complete model request"])
            previous = state["evidence"]
            changed = [p for p in previous.keys() & evidence.keys() if previous[p] != evidence[p]]
            snapshot = result.get("snapshot")
            if not new and (changed or (before == state["book"] and state["snapshot"] and snapshot and snapshot != state["snapshot"])):
                result["status"] = "review"
                state["source_revision"] = digest([snapshot, evidence])
                result["issues"].append({"field": "evidence_refs", "issue": "review changed preparation",
                                         "changed_files": sorted(changed)})
            state.update(snapshot=snapshot, evidence=evidence)
            for issue in result["issues"]:
                repairs = [correction(state, path, label) for path, label in targets(state["book"], issue)]
                if repairs:
                    issue["repairs"] = repairs
            if tracked:
                result = repair_step(state, result, evidence, before)
                if result.get("replayed"):
                    return {**result, "draft_ref": ref, "stage": "material-preparation", "transport": "not-sent",
                            "next": next_step(result, ref, binding[3])}
        save_draft(path, state)
        next_action = next_step(result, ref, binding[3]) if tracked else None
        reviewed_action = loop.get("recorded_action", {}) if loop is not None else {}
        return {**result, "draft_ref": ref, "book": state["book"], "book_digest": digest(state["book"]),
                **({"next": next_action, "stage": "material-preparation"} if next_action is not None else {}),
                **({"repair_history": True} if loop and loop.get("had_gap") else {}),
                **({"recorded_action": reviewed_action["ref"]} if reviewed_action.get("book") == digest(state["book"]) else {}),
                **({"source_revision": state["source_revision"]} if "source_revision" in state else {}),
                "transport": "not-sent"}
    finally:
        if fd is None:
            release_lock(lock)
        else:
            os.close(fd)
