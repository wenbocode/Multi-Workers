import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.js";
import { acquireLock } from "../shared/file-lock.js";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.js";
const TARGET_DPS = ["dp-pm-steer", "dp-auto"];
const INTENT_STATUSES = ["prepared", "requesting", "answered", "failed", "executed"];
const TASK_STATUSES = [
    "not-queued",
    "pending",
    "running",
    "done",
    "failed",
    "needs-clarification",
    "lost",
    "unknown",
];
const BINDING_FIELDS = [
    "parent_ref",
    "parent_logical_id",
    "parent_decision_id",
    "parent_matter_version",
    "material_version",
    "basis_version",
    "target_dp",
    "owner_key",
    "task_key",
    "restricted_action",
    "restricted_executor",
];
// Python's decision_wire emits UUID.hex; Node's randomUUID uses hyphens.
// The ledger lookup below always compares the original token exactly.
const UUID_PATTERN = /^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/i;
const TOKEN_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_.:@+-]{0,127}$/;
const FAILURE_CODES = new Set([
    "provider-unavailable",
    "disabled",
    "timeout",
    "unavailable",
    "bad-response",
    "invalid-request-result",
    "request-threw",
    "request-failed",
    "upstream-error",
    "role-forbidden",
    "unauthorized",
    "budget-exhausted",
]);
function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}
function nonEmpty(value) {
    return typeof value === "string" && value.trim() !== "" && !value.includes("\0");
}
function isBoundPm(value) {
    return (isRecord(value) &&
        value.role === "pm" &&
        nonEmpty(value.key) &&
        nonEmpty(value.window_id) &&
        Object.keys(value).length === 3);
}
function parseIntent(file) {
    let value;
    try {
        value = JSON.parse(fs.readFileSync(file, "utf8"));
    }
    catch {
        return undefined;
    }
    if (!isRecord(value))
        return undefined;
    const keys = [
        "parent_ref",
        "parent_decision_id",
        "parent_matter_version",
        "material_version",
        "basis_version",
        "owner_key",
        "restricted_action",
        "restricted_executor",
    ];
    if (value.schema_version !== 1 || keys.some((key) => !nonEmpty(value[key])))
        return undefined;
    if (!nonEmpty(value.parent_logical_id) || !UUID_PATTERN.test(value.parent_logical_id))
        return undefined;
    if (!TARGET_DPS.includes(value.target_dp))
        return undefined;
    if (!INTENT_STATUSES.includes(value.status))
        return undefined;
    if (!isBoundPm(value.prepared_by))
        return undefined;
    if (value.task_key !== null && !nonEmpty(value.task_key))
        return undefined;
    for (const key of ["request_ref", "answer", "failure_reason"]) {
        if (value[key] !== null && !nonEmpty(value[key]))
            return undefined;
    }
    if (value.action_evidence !== undefined && !nonEmpty(value.action_evidence))
        return undefined;
    const answered = value.status === "answered" || value.status === "executed";
    if (answered) {
        if (!validAnswer(value.target_dp, value.request_ref, value.answer))
            return undefined;
    }
    else if (value.request_ref !== null || value.answer !== null)
        return undefined;
    if ((value.status === "failed") !== (value.failure_reason !== null))
        return undefined;
    if ((value.status === "executed") !== (value.action_evidence !== undefined))
        return undefined;
    return value;
}
function validAnswer(dp, ref, answer) {
    if (!nonEmpty(ref) || !TOKEN_PATTERN.test(ref) || !ref.startsWith(`${dp}:`))
        return false;
    if (!nonEmpty(answer) || !TOKEN_PATTERN.test(answer))
        return false;
    return dp === "dp-auto" || DECIDE_REGISTRY[dp].fixedChoiceIds.includes(answer);
}
function safeFailure(reason) {
    return typeof reason === "string" && FAILURE_CODES.has(reason) ? reason : "request-failed";
}
function samePm(left, right) {
    return left.role === right.role && left.key === right.key && left.window_id === right.window_id;
}
function bindingMatches(intent, expected) {
    return BINDING_FIELDS.every((field) => intent[field] === expected[field]);
}
// Use the managed Python reader for the actual lifecycle path, damaged rows and
// the current schema. Return only the outcome of the join, never ledger contents.
const CHECK_RECEIPT = `
import json, pathlib, sys
import decision_wire as wire
scope, dirname, project_id, expected_parent, i = json.load(sys.stdin)
root = pathlib.Path(dirname).resolve(strict=True)
if scope == "production":
    sink = wire.production_lifecycle_sink(root)
    project_id = wire.project_id_for(root)
else:
    sink = wire.test_lifecycle_sink(root)
    wire.WireScope._refuse_production_paths(sink)
if not sink.is_file() or sink.resolve(strict=True) != sink or sink.is_symlink():
    sys.exit(1)
batch = wire.read_events(sink)
if any((batch.stats.bad_json, batch.stats.bad_utf8, batch.stats.unknown_schema,
        batch.stats.oversized_line, batch.stats.incomplete_tail)):
    sys.exit(1)
rows = [r for r in batch.events if r.get("scope") == scope and r.get("project_id") == project_id
        and r.get("origin") == "decision-lifecycle" and r.get("key") == i["owner_key"]]
parent = [r for r in rows if r.get("kind") == "record-start"
          and r.get("decision_id") == i["parent_decision_id"] and r.get("logical_id") == i["parent_logical_id"]]
gate = [r for r in rows if r.get("kind") == "request" and r.get("decision_id") == i["parent_decision_id"]
        and r.get("logical_id") == i["parent_logical_id"] and r.get("dp") == "dp-gate-approve"
        and r.get("available") is True and r.get("business_decisions") == 1]
choice = {"dp-pm-steer": "steer", "dp-auto": "need_fix"}[i["target_dp"]]
if len(parent) != 1 or len(gate) != 1 or gate[0].get("choice") != choice:
    sys.exit(1)
if expected_parent is not None:
    notes = [r for r in rows if r.get("kind") == "note" and r.get("decision_id") == i["parent_decision_id"]
             and r.get("logical_id") == i["parent_logical_id"]]
    if (len(notes) != 1 or notes[0].get("pm_note") != expected_parent["pmNote"]
            or ("stageNoteEvent" in expected_parent and notes[0].get("event_id") != expected_parent["stageNoteEvent"])
            or gate[0].get("basis_text") != expected_parent["modelBasis"]):
        sys.exit(1)
if i["request_ref"] is None:
    seen = any(r.get("kind") == "request" and r.get("parent_ref") == i["parent_decision_id"]
               and r.get("dp") == i["target_dp"] for r in rows)
    sys.exit(1 if seen else 0)
requests = [r for r in rows if r.get("kind") == "request" and r.get("decision_id") == i["request_ref"]
            and r.get("task_key") == i["task_key"] and r.get("parent_ref") == i["parent_decision_id"]
            and r.get("dp") == i["target_dp"] and r.get("available") is True and r.get("business_decisions") == 1]
if len(requests) != 1 or requests[0].get("choice") != i["answer"]:
    sys.exit(1)
if scope == "production" and requests[0].get("basis_catalog_sha256") != i["basis_version"]:
    sys.exit(1)
logical_id = requests[0]["logical_id"]
starts = [r for r in rows if r.get("kind") == "record-start" and r.get("logical_id") == logical_id
          and r.get("initiator_role") == "pm" and r.get("task_key") == i["task_key"]]
if len(starts) != 1:
    sys.exit(1)
if i["action_evidence"] is not None:
    effects = [r for r in rows if r.get("kind") == "lifecycle" and r.get("lifecycle") == "executed"
               and r.get("logical_id") == logical_id and r.get("task_key") == i["task_key"]
               and r.get("decision_id") == i["request_ref"] and r.get("event_id") == i["action_evidence"]
               and r.get("action") == i["restricted_action"]
               and r.get("actor") == {"kind": "system", "id": i["restricted_executor"]}]
    if len(effects) != 1 or i["restricted_action"] != i["answer"]:
        sys.exit(1)
print(json.dumps(requests[0]["basis_id"]))
`;
function recorded(scope, intent, action) {
    const mw = findMwPy();
    if (scope === undefined || mw === null || (action !== undefined && !TOKEN_PATTERN.test(action)))
        return undefined;
    const args = "projectDir" in scope
        ? ["production", scope.projectDir, null, scope.parentEvidence ?? null]
        : ["test", scope.isolatedTestRoot, scope.projectId, null];
    const read = spawnSync(PYTHON_EXE, ["-B", "-X", "utf8", "-c", CHECK_RECEIPT], {
        cwd: path.dirname(mw),
        stdio: ["pipe", "pipe", "ignore"],
        encoding: "utf8",
        windowsHide: true,
        input: JSON.stringify([...args, { ...intent, action_evidence: action ?? null }]),
    });
    if (read.status !== 0)
        return undefined;
    if (intent.request_ref === null)
        return {};
    try {
        const basisId = JSON.parse(read.stdout);
        return nonEmpty(basisId) ? { basisId } : undefined;
    }
    catch {
        return undefined;
    }
}
function result(state, opts = {}) {
    return {
        state,
        request_started: false,
        duplicate: false,
        parent_released: false,
        ...opts,
    };
}
function writeIntent(file, intent) {
    const dir = path.dirname(file);
    const temporary = path.join(dir, `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`);
    let fd;
    try {
        fd = fs.openSync(temporary, "wx");
        fs.writeFileSync(fd, `${JSON.stringify(intent, null, 2)}\n`, "utf8");
        fs.fsyncSync(fd);
        fs.closeSync(fd);
        fd = undefined;
        fs.renameSync(temporary, file);
    }
    finally {
        if (fd !== undefined)
            fs.closeSync(fd);
        try {
            fs.unlinkSync(temporary);
        }
        catch {
            // The atomic rename consumed the temporary file.
        }
    }
}
function validateOwner(intent, boundPm) {
    if (boundPm === null)
        return result("blocked", { reason: "pm-window-unbound" });
    if (!samePm(intent.prepared_by, boundPm) || intent.owner_key !== boundPm.key) {
        return result("blocked", { reason: "pm-identity-mismatch" });
    }
    return undefined;
}
/**
 * Resume one already-prepared PM follow-up. The intent file is coordination
 * state only: the real request still goes through the injected decision client.
 * A persisted `requesting` state is deliberately unknown after a crash, because
 * the filesystem and remote request are not one transaction.
 */
export async function resumeDecisionFollowup(input) {
    const lockPath = `${input.intent_path}.lock`;
    const expected = { ...input.expected };
    let release = await acquireLock(lockPath);
    let intent;
    try {
        intent = parseIntent(input.intent_path);
        if (intent === undefined)
            return result("blocked", { reason: "intent-invalid" });
        const ownerProblem = validateOwner(intent, input.bound_pm);
        if (ownerProblem !== undefined)
            return ownerProblem;
        if (!bindingMatches(intent, expected))
            return result("blocked", { reason: "version-mismatch" });
        if (intent.status === "requesting")
            return result("unknown", { reason: "request-outcome-unknown" });
        if (intent.status === "answered" || intent.status === "executed") {
            const receipt = recorded(input.lifecycle, intent, intent.action_evidence);
            if (!receipt) {
                return result("unknown", { reason: "successor-receipt-unverified", duplicate: true });
            }
            return result(intent.status, {
                request_ref: intent.request_ref ?? undefined,
                answer: intent.answer ?? undefined,
                basis_id: receipt.basisId,
                duplicate: true,
            });
        }
        if (intent.status === "failed") {
            return result("failed", { reason: safeFailure(intent.failure_reason), duplicate: true });
        }
        let taskStatus;
        try {
            taskStatus = input.observe_task(intent.owner_key, intent.task_key);
        }
        catch {
            return result("unknown", { reason: "task-observation-unavailable" });
        }
        if (taskStatus === "pending" || taskStatus === "running") {
            return result("in-progress", { reason: `task-${taskStatus}` });
        }
        if (taskStatus !== "not-queued")
            return result("unknown", { reason: "task-unknown" });
        if (input.lifecycle && "projectDir" in input.lifecycle && !input.lifecycle.parentEvidence)
            return result("blocked", { reason: "parent-evidence-missing" });
        if (!recorded(input.lifecycle, intent))
            return result("blocked", { reason: "parent-or-successor-not-clear" });
        intent = { ...intent, status: "requesting", request_ref: null, answer: null, failure_reason: null };
        writeIntent(input.intent_path, intent);
    }
    finally {
        release();
    }
    let requested;
    try {
        requested = await input.request(structuredClone(intent));
    }
    catch {
        requested = { available: false, reason: "request-threw" };
    }
    release = await acquireLock(lockPath);
    try {
        const current = parseIntent(input.intent_path);
        if (current === undefined ||
            !bindingMatches(current, expected) ||
            !samePm(current.prepared_by, intent.prepared_by) ||
            validateOwner(current, input.bound_pm)) {
            return result("unknown", { reason: "intent-changed-after-request", request_started: true });
        }
        if (current.status !== "requesting") {
            return result("unknown", { reason: "request-state-changed", request_started: true });
        }
        if (!requested?.available) {
            const reason = safeFailure(requested?.reason);
            writeIntent(input.intent_path, { ...current, status: "failed", failure_reason: reason });
            return result("failed", { reason, request_started: true });
        }
        if (!validAnswer(current.target_dp, requested.request_ref, requested.answer)) {
            writeIntent(input.intent_path, { ...current, status: "failed", failure_reason: "invalid-request-result" });
            return result("failed", { reason: "invalid-request-result", request_started: true });
        }
        const answered = {
            ...current,
            status: "answered",
            request_ref: requested.request_ref,
            answer: requested.answer,
            failure_reason: null,
        };
        const receipt = recorded(input.lifecycle, answered);
        if (!receipt) {
            return result("unknown", { reason: "successor-receipt-unverified", request_started: true });
        }
        writeIntent(input.intent_path, answered);
        return result("answered", {
            request_ref: requested.request_ref,
            answer: requested.answer,
            basis_id: receipt.basisId,
            request_started: true,
        });
    }
    finally {
        release();
    }
}
/** Record a real, already-performed follow-up action. This never performs the
 * action and never releases the parent gate; later consumers must independently
 * validate the action evidence and gate conditions. */
export async function markDecisionFollowupExecuted(input) {
    const release = await acquireLock(`${input.intent_path}.lock`);
    try {
        const intent = parseIntent(input.intent_path);
        if (intent === undefined)
            return result("blocked", { reason: "intent-invalid" });
        const ownerProblem = validateOwner(intent, input.bound_pm);
        if (ownerProblem !== undefined)
            return ownerProblem;
        if (!bindingMatches(intent, input.expected))
            return result("blocked", { reason: "version-mismatch" });
        if ((intent.status !== "answered" && intent.status !== "executed") || intent.request_ref !== input.request_ref) {
            return result("blocked", { reason: "answer-not-correlated" });
        }
        if (intent.restricted_action !== intent.answer)
            return result("blocked", { reason: "action-not-selected" });
        if (intent.status !== "executed" &&
            input.lifecycle &&
            "projectDir" in input.lifecycle &&
            !input.lifecycle.parentEvidence)
            return result("blocked", { reason: "parent-evidence-missing" });
        if (!nonEmpty(input.action_evidence) || !recorded(input.lifecycle, intent, input.action_evidence)) {
            return result("unknown", { reason: "action-evidence-unverified" });
        }
        if (intent.status === "executed") {
            return intent.action_evidence === input.action_evidence
                ? result("executed", { request_ref: input.request_ref, duplicate: true })
                : result("blocked", { reason: "action-evidence-mismatch" });
        }
        writeIntent(input.intent_path, { ...intent, status: "executed", action_evidence: input.action_evidence });
        return result("executed", { request_ref: intent.request_ref, answer: intent.answer ?? undefined });
    }
    finally {
        release();
    }
}
//# sourceMappingURL=decision-followup.js.map