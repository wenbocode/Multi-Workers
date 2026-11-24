"""Resume PM receipts from the lifecycle ledger and track bounded repairs."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os

import decision_drafts
import decision_lifecycle as ledger
import decision_points
from pm_state import atomic_write, child

if os.name == "nt":
    import msvcrt
else:
    import fcntl


FIELDS = {"decision_id", "stage", "event_id", "action", "outcome", "result", "reason", "task_after", "check_only"}
ORDER = {"arguments": 0, "event_id": 1, "task_after": 2, "action": 3, "outcome": 3, "reason": 4, "result": 5}
FIX = {
    "decision_id": "Use the original formal decision_id.",
    "stage": "Set stage to executed for a real action or settled for the handling result.",
    "arguments": "Remove the unsupported fields and keep the original receipt identity.",
    "check_only": "Use a boolean for check_only.",
    "event_id": "Use the original valid event_id.",
    "task_after": "Correct task_after using the actual task observation.",
    "action": "Set action to the supported label for the step actually performed.",
    "outcome": "Set outcome to the supported value for the actual handling result.",
    "reason": "Supply reason as text.",
    "result": "Supply result as text.",
}


@contextmanager
def receipt_lock(root, scope):
    directory = child(child(root, ".mw"), "decision-receipts")
    directory.mkdir(parents=True, exist_ok=True)
    lock = child(directory, scope + ".lock")
    with lock.open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(stream, fcntl.LOCK_EX)
        yield child(directory, scope + ".json")


def reply(identity, status, *, action=None, field=None, code=None, instruction=None, count=None):
    result = {**identity, "status": status}
    if code is not None:
        result["code"] = code
    if count is not None:
        result["consecutive_no_progress"] = count
    if action is not None:
        result["next"] = {"owner": "pm", "action": action, "done_when": instruction}
        if field is not None:
            result["next"]["field"] = field
        if "event_id" in identity:
            result["next"]["event_id"] = identity["event_id"]
    return result


def reconcile(identity, code):
    return reply(identity, "failed", action="reconcile-receipt", code=code,
                 instruction="Call decision_receipt with the same identity and check_only=true to check the ledger.")


def binding_refusal(identity):
    return reply(identity, "refused", action="recover-receipt-binding", code="receipt-binding",
                 field="decision_id", instruction="Verify the original accepted decision and the current key claim.")


def save(path, state):
    atomic_write(path, json.dumps(state, sort_keys=True).encode("utf-8"), expected=None)


def revision(payload, field):
    value = sorted(set(payload) - FIELDS) if field == "arguments" else payload.get(field)
    return decision_drafts.digest([field in payload, value])


def repair(path, state, identity, payload, field, instruction):
    issue = state.get("issue")
    if issue is None or ORDER[field] > ORDER[issue["field"]]:
        issue = {"field": field, "seen": [revision(payload, field)], "failures": 0}
        state["issue"] = issue
    elif field == issue["field"] and (attempt := revision(payload, field)) not in issue["seen"]:
        if issue["failures"] < decision_drafts.REPAIR_LIMIT:
            issue["seen"].append(attempt)
            issue["failures"] += 1
    state["pending"] = False
    save(path, state)
    return repair_reply(identity, issue, field, instruction)


def repair_reply(identity, issue, field, instruction):
    count = issue["failures"]
    if count >= decision_drafts.REPAIR_LIMIT:
        return reply(identity, "paused", action="review-receipt-repair", code="no-progress", field=issue["field"],
                     count=count, instruction="Verify the original receipt facts and supply a valid correction to this field.")
    return reply(identity, "refused", action="repair-receipt", field=field, code="invalid-field",
                 count=count, instruction=instruction + " Resubmit with the same decision_id, stage, and event_id.")


def local_issue(payload, meta):
    if set(payload) - FIELDS:
        return "arguments", FIX["arguments"]
    task_after = payload.get("task_after")
    if task_after is not None:
        if meta.task_key is None:
            return "task_after", "This decision has no task_key. Set task_after to null."
        if isinstance(task_after, dict) and "source" in task_after and task_after["source"] != "agent-report":
            return "task_after", "Set task_after.source to agent-report for the actual observation."
    return None


def operate(root, store, key, payload, authorized):
    stage = payload.get("stage")
    identity = {"decision_id": None, "stage": stage if stage in ("executed", "settled") else None}
    requested = payload.get("event_id")
    event_valid = True
    if requested is not None:
        try:
            ledger._check_token("event_id", requested)
            ledger._guard_secret(store, "event_id", requested)
            identity["event_id"] = requested
        except ledger.LifecycleInputError:
            event_valid = False
    try:
        decision_id = ledger._check_decision_id("decision_id", payload.get("decision_id"))
        ledger._guard_secret(store, "decision_id", decision_id)
        dp, logical_id = decision_id.split(":", 1)
        ledger._check_token("decision_id", logical_id)
        decision_points.require_active_dp(dp)
    except ValueError:
        return reply(identity, "refused", action="repair-receipt", field="decision_id", code="invalid-field",
                     instruction=FIX["decision_id"])
    identity.update(decision_id=decision_id, dp=dp)
    if identity["stage"] is None:
        return reply(identity, "refused", action="repair-receipt", field="stage", code="invalid-field",
                     instruction=FIX["stage"])
    if not event_valid:
        return reply(identity, "refused", action="repair-receipt", field="event_id", code="invalid-field",
                     instruction=FIX["event_id"])
    identity.setdefault("event_id", ledger._stable_event_id("receipt", key, decision_id, stage))
    scope = decision_drafts.digest([key, decision_id, stage])
    check = payload.get("check_only", False)
    if not isinstance(check, bool):
        return reply(identity, "refused", action="repair-receipt", field="check_only", code="invalid-field",
                     instruction=FIX["check_only"])
    if not authorized():
        return binding_refusal(identity)
    try:
        with receipt_lock(root, scope) as file:
            return submit(file, store, key, identity, payload, authorized, check, requested)
    except (OSError, ValueError):
        return reconcile(identity, "ledger-unconfirmed")


def submit(file, store, key, identity, payload, authorized, check, requested):
    state = json.loads(file.read_bytes()) if file.exists() else {}
    event = requested or state.get("event_id") or identity["event_id"]
    identity["event_id"] = event
    if not authorized():
        return binding_refusal(identity)
    try:
        meta, events = ledger.recover_pm_receipt(store, key, identity["decision_id"], identity["stage"], event)
    except ledger.LifecycleInputError as error:
        if error.code == "event-conflict":
            return reconcile(identity, error.code)
        return binding_refusal(identity)
    existing = next((row for row in events if row.get("event_id") == event), None)
    if existing is not None:
        label = "action" if identity["stage"] == "executed" else "outcome"
        if not check and existing.get(label) != payload.get(label):
            return reconcile(identity, "event-conflict")
        if state.get("event_id") == event:
            save(file, {})
        return reply(identity, "duplicate")
    if state and state["event_id"] != event:
        identity["event_id"] = state["event_id"]
        return reply(identity, "refused", action="repair-receipt", code="event-changed", field="event_id",
                     instruction=FIX["event_id"])
    if check:
        if state.get("pending"):
            state["pending"] = False
            save(file, state)
        return reply(identity, "not-recorded", action="retry-receipt", code="receipt-absent",
                     instruction="Resubmit the same verified receipt with check_only=false.")
    if state.get("pending"):
        return reconcile(identity, "ledger-unconfirmed")
    state["event_id"] = event
    issue = local_issue(payload, meta)
    if issue is not None:
        return repair(file, state, identity, payload, *issue)
    prior = state.get("issue")
    if prior and prior["failures"] >= decision_drafts.REPAIR_LIMIT:
        field = prior["field"]
        if revision(payload, field) in prior["seen"]:
            return repair_reply(identity, prior, field, FIX[field])
    if not authorized():
        return binding_refusal(identity)
    state["pending"] = True
    save(file, state)

    def authorize_append():
        if not authorized():
            raise ledger.LifecycleInputError("The PM key claim changed", code="receipt-binding")

    try:
        result = ledger.record_lifecycle(
            store, meta, **identity, authorize_append=authorize_append,
            **{field: payload[field] for field in ("action", "outcome", "result", "reason", "task_after")
               if field in payload},
        )
    except ledger.LifecycleInputError as error:
        if error.field in ORDER:
            return repair(file, state, identity, payload, error.field, f"{error}. {FIX[error.field]}")
        state["pending"] = False
        save(file, state)
        return binding_refusal(identity)
    if result.recorded:
        if result.duplicate:
            ledger.require_receipt_binding(store, meta, decision_id=identity["decision_id"],
                                           stage=identity["stage"], event_id=event)
        save(file, {})
        return reply(identity, result.status)
    return reconcile(identity, "ledger-unconfirmed")
