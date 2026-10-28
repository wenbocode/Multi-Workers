/**
 * pm/decision-tool.ts — the `ask_decision` tool: the ONLY LLM-facing channel
 * for asking an external decision point (mw-decision-substitution T-05, spec
 * DS-7/DS-10, design D-017, D4 research Q1..Q6).
 *
 * Contract
 * - Input: `dp` (enum of the registry ids this module holds as constants),
 *   `trigger` (audit label: `<task_key>` | `<task_key>#ckpt<N>` | `ts`; the
 *   decision id itself is resolved by Python, see below), optional `question`
 *   (one question id) and optional `note` (L0/L1 summary).
 * - Output text: ONE line of JSON
 *   `{available, decision_id, mode, acted, answers, confidence_source, latency_ms}`
 *   on success; on failure `{available:false, unavailable:<reason>,
 *   action:"blocked-ask-human"}` plus `escalated_reason` (the child's own
 *   7-value vocabulary) and/or `missing_fields` when they apply, followed by a
 *   fixed second line that forbids guessing. The model sees this text verbatim
 *   as the tool result, so both shapes are deterministic (no prose rewriting,
 *   design Q2 §2.4).
 * - `execute` runs `python -X utf8 mw.py decide run --project=<dir> --dp <id>
 *   --request-file <tmp> --json` with an ASYNC spawn and a hard 20 s wall
 *   (design D-017: a synchronous child inside a tool call would freeze the
 *   event loop, the heartbeat and trace writes). The request JSON travels in a
 *   temp file, never on argv (spec D-003).
 * - Failure shape: a SERVICE failure is DATA (`available:false` + directive) —
 *   it must not throw, or the model would lose the "do not guess" instruction.
 *   Only argument misuse (the TypeBox enum) is rejected by the loop's
 *   `validateToolArguments`, because `AgentToolResult`
 *   (`packages/agent/src/types.ts:355-368`) has no `isError` field; `execute`
 *   throwing is the only other way to surface a hard error.
 *
 * Authorization, `mode` and `acted` (D-036 / D-041)
 * - A structured request (`--dp <registry id>`, no `questions`) makes
 *   `mw decide run` call `decision_points.decide_for(..., intent="answer")`,
 *   which is the single authority: it reads `.mw/decide-points.json` itself
 *   (step 2), resolves the mode (step 3) and archives one row per decision
 *   (`packages/multi-workers/mw.py:_decide_run`). Its JSON therefore carries
 *   `decision_id` / `mode` / `acted` / `escalated_reason`
 *   (`_decide_run_payload`, T-02b).
 * - This module consumes those four keys verbatim. It never reads the
 *   authorization table, never derives `mode` from a tier default and never
 *   turns `mode` into `acted`: D-041 makes `acted` a consuming-side fact, and
 *   an `intent="answer"` decision is archived with `acted=false` (D-035) no
 *   matter what the mode is.
 * - `trigger` is an audit label for the trace line and the directives only. The
 *   authoritative `decision_id` is `<dp>:<trigger_id>` resolved by Python from
 *   the state's `key`/`task_key` (`decision_points.py:Trigger.resolved_id`), so
 *   a locally concatenated id would drift from the archive row.
 * - Nothing here writes config or the archive: Python stays the single writer
 *   (D-005).
 *
 * Structured state (spec §5.4 L0/L1, D6 Q5.1)
 * - {@link buildDecisionState} fills only what this call site knows
 *   (`v`/`dp`/`key`/`task_key`/`task_summary`). `decide_for` step 5 refuses a
 *   state that misses one of the registry's `REQUIRED_STATE_FIELDS`
 *   (`packages/multi-workers/decision_points.py:626`), so for the dps that map
 *   covers (dp1/dp2/dp3) the tool refuses **before** the spawn and reports the
 *   field names (names only: L0) instead of spending a round trip on a state
 *   Python can only answer with `input-incomplete`/`bad-response` (MAJOR-2).
 * - The field table itself is not copied: the check reuses
 *   `pm/triage-client.ts`'s structured-state validator and
 *   `REQUIRED_FIELDS_BY_DP` (single source). Only the id set of the dps the
 *   registry gates is held here, pinned to the Python source by the suite.
 *
 * Anti-retry (spec §5.3 / design Q3 §3.3)
 * - A per-dp block counter is scoped to one agent turn (`turn_start` resets it).
 *   Reaching {@link ASK_DECISION_MAX_BLOCKED_PER_TURN} marks the tool result
 *   `terminate: true` and appends a terminal directive, so the tool loop stops
 *   instead of the model re-asking forever. Every block/answer leaves one
 *   machine line in the worker's trace.log.
 */
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Type } from "typebox";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.js";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.js";
import { controlRootFromTaskPath } from "../shared/paths.js";
import { readTaskType } from "../shared/task-frontmatter.js";
import { AGENT_TASK_STATE_SCHEMA, copyTaskState, isTaskStateSnapshot, } from "./decision-task-state.js";
import { canonicalStateBytes, MAX_STRUCTURED_STATE_BYTES, validateStructuredState } from "./triage-client.js";
/** Registered tool name (referenced by `activeToolsForType` wiring in index.ts). */
export const ASK_DECISION_TOOL = "ask_decision";
/** The receipt op: the asking agent records what it ACTUALLY did with a
 * selection (`executed`) and when this round of handling is done (`settled`).
 * It never records on the model's return alone (AC-014). */
export const DECISION_RECEIPT_TOOL = "decision_receipt";
/** Hard client-side wall for one `mw decide run` child (design D-017/D-006). */
export const ASK_DECISION_TIMEOUT_MS = 20_000;
/** Same-dp blocks inside one turn before the tool loop is terminated. */
export const ASK_DECISION_MAX_BLOCKED_PER_TURN = 2;
/** The only failure action the model is ever told about (spec §5.1 fail-closed). */
export const ASK_DECISION_BLOCKED_ACTION = "blocked-ask-human";
/** Client-side canonical state budget for the LEGACY structured path only
 * (spec AC-013 / §5.4). Same number as the structured-input contract, taken
 * from it instead of restated here.
 *
 * It deliberately does NOT gate business material: the four material dps
 * (dp1/dp2/dp3/dp25) are bounded by the single published authority,
 * `decision_points.MAX_STATE_BYTES` (8192B), which refuses the WHOLE material
 * with zero POST and never truncates it. Mirroring that number here would be a
 * second authority, and lowering it would silently shrink real task material
 * the service already accepted (T08 gap 1). */
export const ASK_DECISION_MAX_STATE_BYTES = MAX_STRUCTURED_STATE_BYTES;
/** L1 note cap carried as `task_summary` (matches the Python field validator). */
const NOTE_MAX_BYTES = 600;
/** `key` / `task_key` field cap in the Python state schema. */
const TASK_KEY_MAX_BYTES = 48;
/**
 * The 25 decision-point ids, copied verbatim from
 * `packages/multi-workers/decision_points.py:DP_REGISTRY` (the authority). The
 * suite asserts both the id set and the tier map against that file, so a
 * drift shows up as a red test, not as a silently unregistered call.
 */
export const ASK_DECISION_DP_IDS = [
    "dp1-dispatch-type",
    "dp2-checkpoint-split",
    "dp3-worker-clarify",
    "dp4-failure-handling",
    "dp5-test-triage",
    "dp6-qg-verdict",
    "dp7-gate-failure",
    "dp8-scope-change",
    "dp9-model-select",
    "dp10-dependency",
    "dp11-credential",
    "dp12-destructive",
    "dp13-commit-release",
    "dp14-rule-conflict",
    "dp15-autopilot-gate",
    "dp16-goal",
    "dp17-spec-lock",
    "dp18-claim",
    "dp19-foreign-write",
    "dp20-stage-close",
    "dp21-refine",
    "dp22-debug-plan",
    "dp23-snapshot",
    "dp24-pi-trust",
    "dp25-signoff-conclusion",
];
/** Registry ids whose `decide_for` step 5 enforces `REQUIRED_STATE_FIELDS`
 * (`packages/multi-workers/decision_points.py:626`). Only these dps may be
 * refused client-side on a missing field: every other dp requires nothing
 * beyond the state builder's `v`/`dp`/`questions_version`, so pre-gating it
 * here would over-gate a call the authority accepts. The id set is pinned to
 * the Python source by `decision-tool.test.ts`; the **field** names themselves
 * come from `pm/triage-client.ts` and are never copied. */
export const ASK_DECISION_ENFORCED_STATE_DP_IDS = [
    "dp1-dispatch-type",
    "dp2-checkpoint-split",
    "dp3-worker-clarify",
    // mw-decision-substitution W9: the sign-off conclusion dp (spec §15 AC-027).
    "dp25-signoff-conclusion",
];
/** Frozen transport reasons (`decision.py:REASON_CODES`). A reason outside this
 * set is normalised to `upstream-error` exactly like `decision.py` does. */
export const ASK_DECISION_PYTHON_REASONS = new Set([
    "disabled",
    "entry-unavailable",
    "timeout",
    "rate-limited",
    "upstream-error",
    "bad-response",
    "unsupported-question-type",
    "budget-exhausted",
]);
/** TS-local refusal reasons (never produced by the Python service; the T-04
 * precedent D-028 keeps them distinct from the frozen 8-value set). */
export const ASK_DECISION_REASON_INPUT_INCOMPLETE = "input-incomplete";
export const ASK_DECISION_REASON_INPUT_OVERSIZE = "input-oversize";
/** Fixed phrase every unavailable payload carries (spec AC-005: no default
 * action, no guessing). */
export const ASK_DECISION_GUESS_DIRECTIVE = "不要自行猜测";
/** Only the PM may prepare these decisions (design D003/§4.4): a worker that
 * reaches the entry with one of them is refused with ZERO spawn — a model must
 * never borrow the PM's checkpoint or sign-off conclusion. */
export const ASK_DECISION_PM_ONLY_DP_IDS = ["dp2-checkpoint-split", "dp25-signoff-conclusion"];
/** The dps whose material is the approved business contract (T01): the caller
 * supplies every field verbatim on the local envelope. Every other dp keeps
 * the legacy L0/L1 state path byte-identical. */
export const ASK_DECISION_MATERIAL_DP_IDS = [
    "dp2-checkpoint-split",
    "dp3-worker-clarify",
    "dp25-signoff-conclusion",
];
/** dp3 native dynamic-choice protocol (`decision_points.dynamic_choices_value_error`). */
export const DP3_ID = "dp3-worker-clarify";
export const DP3_HANDLING_MIN_OPTIONS = 2;
export const DP3_HANDLING_MAX_OPTIONS = 5;
export const DP3_HANDLING_LABEL_MAX = 80;
/** TS-local refusal reasons (never produced by the Python service, D-028). */
export const ASK_DECISION_REASON_ROLE_FORBIDDEN = "role-forbidden";
export const ASK_DECISION_REASON_UNKNOWN_DECISION = "unknown-decision";
export const ASK_DECISION_REASON_UNKNOWN_ACTION = "unknown-action";
/** Record version of the local envelope (design §4.1; T02's
 * `decision_lifecycle.RECORD_VERSION`). The meta never reaches the model. */
export const DECISION_RECORD_VERSION = 2;
// ── Structured state: per-dp required fields (single source: triage-client) ──
function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}
/** True for the 25 ids the tool exposes (and therefore for every id Python can
 * resolve); the enum itself is pinned to `DP_REGISTRY` by the suite. */
export function isRegisteredDp(dp) {
    return ASK_DECISION_DP_IDS.includes(dp);
}
// ── Request envelope ────────────────────────────────────────────────────────
/** Code-point-safe UTF-8 truncation (never splits a surrogate pair). */
export function truncateUtf8(text, maxBytes) {
    if (Buffer.byteLength(text, "utf8") <= maxBytes)
        return text;
    let out = "";
    let used = 0;
    for (const char of text) {
        const size = Buffer.byteLength(char, "utf8");
        if (used + size > maxBytes)
            break;
        out += char;
        used += size;
    }
    return out;
}
/**
 * Build the bounded structured `state` sent to the service (spec §5.4 L0/L1).
 *
 * Only registry-schema keys this call site actually knows are used
 * (`schema_version`/`decision_point`/`key`/`task_key`/`task_summary`): the dp's own required block
 * (`phase`/`risk`/`scope.*`/`progress.*`/`ambiguity.*`, ...) has no honest
 * source here, so it stays absent and {@link missingDecisionStateFields}
 * reports it instead of the envelope inventing values. Python fills
 * `questions_version` from the registry (`decision_points._state_builder`).
 * L2 material (code, transcripts, absolute paths) has no key to ride and the
 * prompt guidelines forbid putting it in `note`.
 */
export function buildDecisionState(input) {
    const state = { schema_version: 2, decision_point: input.dp };
    if (input.taskKey !== undefined && input.taskKey !== null && input.taskKey !== "") {
        const key = truncateUtf8(input.taskKey, TASK_KEY_MAX_BYTES);
        state.key = key;
        state.task_key = key;
    }
    if (input.note !== undefined && input.note.trim() !== "") {
        state.task_summary = truncateUtf8(input.note.trim(), NOTE_MAX_BYTES);
    }
    return state;
}
/** Fields the client-side check must not ask for: Python's `_state_builder`
 * fills `questions_version` from the registry (`decision_points.py:278`), so it
 * is never missing at step 5 and the caller cannot supply it. */
const PYTHON_AUTO_FILLED_FIELDS = new Set([
    "questions_version",
    "schema_version",
    "decision_point",
]);
/**
 * The refusal list `decide_for` step 5 would produce for `dp` and `state` —
 * field names only (L0), empty when the state is sendable.
 *
 * The field list is the GENERATED REGISTRY (`DECIDE_REGISTRY`, from
 * `decision_points.REQUIRED_STATE_FIELDS`), never a second local table: the four
 * DPs moved to the business contract in T01, so the old structured-input table
 * (`triage-client.REQUIRED_FIELDS_BY_DP`) no longer describes them. Identity
 * keys Python fills itself are not the caller's to supply.
 */
export function missingDecisionStateFields(dp, state) {
    if (!isMaterialStateDp(dp)) {
        // The other 21 dps keep the pre-existing structured-input table (their
        // contract did not change in T01); over-gating them here would narrow a
        // call Python already accepts.
        if (!ASK_DECISION_ENFORCED_STATE_DP_IDS.includes(dp))
            return [];
        return validateStructuredState(dp, state).filter((field) => !PYTHON_AUTO_FILLED_FIELDS.has(field));
    }
    const entry = DECIDE_REGISTRY[dp];
    if (entry === undefined)
        return [];
    const missing = [];
    for (const field of entry.requiredStateFields) {
        if (PYTHON_AUTO_FILLED_FIELDS.has(field.name))
            continue;
        const value = readMaterialPath(state, field.name);
        if (value === undefined || value === null)
            missing.push(field.name);
        else if (field.type === "string" && (typeof value !== "string" || value.trim() === "")) {
            missing.push(field.name);
        }
    }
    return missing;
}
/** Serialise the request envelope (single line; questions come from the
 * registry because `--dp` is always given, design D-027). */
export function buildDecisionRequestJson(state) {
    return JSON.stringify({ state });
}
/** True when `dp` is one the PM alone may prepare (checkpoint / sign-off). */
export function isPmOnlyDp(dp) {
    return ASK_DECISION_PM_ONLY_DP_IDS.includes(dp);
}
/** True when `dp` carries the business material contract instead of the legacy
 * L0/L1 `task_summary` state. */
export function isMaterialDp(dp) {
    return ASK_DECISION_MATERIAL_DP_IDS.includes(dp);
}
/** The dps whose field contract T01 replaced with the four-dp business schema:
 * the three workers' material dps plus dp1 (the PM dispatch producer, whose
 * material belongs to T03 but whose required fields are the same registry). */
function isMaterialStateDp(dp) {
    return isMaterialDp(dp) || dp === "dp1-dispatch-type";
}
/** Look one registry path (dotted) up in a material/state object. */
function readMaterialPath(source, dotted) {
    let current = source;
    for (const segment of dotted.split(".")) {
        if (!isRecord(current))
            return undefined;
        current = current[segment];
    }
    return current;
}
/** Read the declared business paths of a material object (registry order). */
export function missingMaterialPaths(dp, material) {
    const entry = DECIDE_REGISTRY[dp];
    if (entry === undefined)
        return ["dp"];
    const missing = [];
    for (const field of entry.requiredStateFields) {
        if (readMaterialPath(material, field.name) === undefined)
            missing.push(field.name);
    }
    return missing;
}
function pushFieldIssue(issues, field, value) {
    switch (field.type) {
        case "string":
            if (typeof value !== "string" || value.trim() === "") {
                issues.push({ field: field.name, rule: "must be a non-empty string" });
            }
            return;
        case "array":
            if (!Array.isArray(value)) {
                issues.push({ field: field.name, rule: "must be an array" });
                return;
            }
            if (field.itemType === "string" && value.some((item) => typeof item !== "string" || item.trim() === "")) {
                issues.push({ field: field.name, rule: "every item must be a non-empty string" });
            }
            return;
        case "object":
            if (!isRecord(value))
                issues.push({ field: field.name, rule: "must be an object" });
            return;
        default:
            if (value === undefined || value === null) {
                issues.push({ field: field.name, rule: "must be present" });
            }
            return;
    }
}
/** dp3 native dynamic candidates: 2..5 problem-specific options, contiguous
 * `c1..cN`, single-line labels <= 80 chars, non-empty descriptions, distinct
 * labels (mirror of `decision_points.dynamic_choices_value_error`). */
function checkHandlingOptions(value, issues) {
    if (!Array.isArray(value))
        return;
    if (value.length < DP3_HANDLING_MIN_OPTIONS) {
        issues.push({
            field: "handling_options",
            rule: `needs at least ${DP3_HANDLING_MIN_OPTIONS} distinguishable candidates`,
        });
    }
    if (value.length > DP3_HANDLING_MAX_OPTIONS) {
        issues.push({
            field: "handling_options",
            rule: `expected at most ${DP3_HANDLING_MAX_OPTIONS} candidates`,
        });
    }
    const labels = new Set();
    value.forEach((raw, index) => {
        const item = isRecord(raw) ? raw : undefined;
        if (item === undefined) {
            issues.push({ field: `handling_options[${index}]`, rule: "must be an {id,label,description} object" });
            return;
        }
        for (const unknownKey of Object.keys(item)) {
            if (unknownKey !== "id" && unknownKey !== "label" && unknownKey !== "description") {
                issues.push({ field: `handling_options[${index}].${unknownKey}`, rule: "not a candidate field" });
            }
        }
        const expectedId = `c${index + 1}`;
        if (item.id !== expectedId) {
            issues.push({
                field: `handling_options[${index}].id`,
                rule: `must be the contiguous candidate id ${expectedId}`,
            });
        }
        const label = item.label;
        if (typeof label !== "string" || label.trim() === "") {
            issues.push({ field: `handling_options[${index}].label`, rule: "must be a non-empty string" });
        }
        else {
            if (/[\r\n]/.test(label)) {
                issues.push({ field: `handling_options[${index}].label`, rule: "must be a single line" });
            }
            if (label.length > DP3_HANDLING_LABEL_MAX) {
                issues.push({
                    field: `handling_options[${index}].label`,
                    rule: `must be at most ${DP3_HANDLING_LABEL_MAX} characters`,
                });
            }
            if (labels.has(label)) {
                issues.push({
                    field: `handling_options[${index}].label`,
                    rule: "must differ from every other candidate label",
                });
            }
            labels.add(label);
        }
        const description = item.description;
        if (typeof description !== "string" || description.trim() === "") {
            issues.push({ field: `handling_options[${index}].description`, rule: "must be a non-empty string" });
        }
    });
}
/**
 * Validate one dp's business material against the generated registry.
 *
 * Every field, and the closed key set, comes from `DECIDE_REGISTRY`
 * (`modelStateFields` + `requiredStateFields`/`optionalStateFields`) — the one
 * authority T01 publishes — so a renamed field shows up here as a refusal, not
 * as a second contract drifting from Python. The material is returned VERBATIM
 * (no truncation, no default, no invention): necessary material that cannot be
 * sent is refused as `input-oversize` by the caller instead. Unknown facts stay
 * `unknown` in the text the agent wrote; this function never derives one.
 */
export function validateDecisionMaterial(dp, material) {
    const entry = DECIDE_REGISTRY[dp];
    const paths = entry?.modelStateFields;
    if (entry === undefined || paths === undefined) {
        return { ok: false, issues: [{ field: "dp", rule: "no material contract for this dp" }] };
    }
    if (!isRecord(material)) {
        return { ok: false, issues: [{ field: "material", rule: "must be an object" }] };
    }
    const issues = [];
    const allowedTop = new Set(paths.map((item) => item.split(".")[0]));
    for (const key of Object.keys(material)) {
        if (!allowedTop.has(key)) {
            issues.push({ field: key, rule: "not in required_state_fields (closed key set)" });
        }
    }
    // Nested containers may only carry declared children (background.*,
    // verification_evidence.*).
    const containers = new Map();
    for (const item of paths) {
        const [head, child] = item.split(".");
        if (head === undefined || child === undefined)
            continue;
        const children = containers.get(head) ?? new Set();
        children.add(child);
        containers.set(head, children);
    }
    for (const [container, children] of containers) {
        const value = material[container];
        if (!isRecord(value))
            continue;
        for (const key of Object.keys(value)) {
            if (!children.has(key)) {
                issues.push({ field: `${container}.${key}`, rule: "not in required_state_fields (closed key set)" });
            }
        }
    }
    for (const field of entry.requiredStateFields) {
        pushFieldIssue(issues, field, readMaterialPath(material, field.name));
    }
    for (const field of entry.optionalStateFields) {
        const value = readMaterialPath(material, field.name);
        if (value !== undefined && value !== null)
            pushFieldIssue(issues, field, value);
    }
    if (paths.includes("handling_options"))
        checkHandlingOptions(material.handling_options, issues);
    if (issues.length > 0)
        return { ok: false, issues };
    return { ok: true, material };
}
/** Build the local envelope metadata for ONE new decision.
 *
 * `logical_id` is minted here, so a caller cannot accidentally reuse a previous
 * decision's id; `retry_of` is explicit (a retry mints a new id and points at
 * the previous one). `task_key` stays `null` when the decision has no task.
 */
export function buildDecisionToolMeta(input) {
    const taskKey = input.taskKey?.trim() ?? "";
    const retryOf = input.retryOf?.trim() ?? "";
    return {
        record_version: DECISION_RECORD_VERSION,
        logical_id: randomUUID(),
        key: input.key.trim(),
        task_key: taskKey === "" ? null : taskKey,
        initiator_role: input.initiatorRole,
        retry_of: retryOf === "" ? null : retryOf,
        ...(input.taskBefore === undefined ? {} : { task_before: copyTaskState(input.taskBefore) }),
    };
}
/** Assemble the `{material, meta}` envelope after a last closed-set check. */
export function buildDecisionEnvelope(input) {
    const validated = validateDecisionMaterial(input.dp, input.material);
    if (!validated.ok) {
        throw new Error(`decision material for ${input.dp} is not sendable: ${validated.issues[0]?.field ?? "?"}`);
    }
    return { material: validated.material, meta: input.meta };
}
/** The worker's real initiating role, read from its own card's `type:`.
 *
 * A card that cannot be read, or a type outside coding/research/review, is
 * `unknown` — the tool never upgrades a role to make a PM-only dp callable. */
export function initiatorRoleFromWorkerTask(taskPath) {
    if (taskPath === undefined || taskPath === "")
        return "unknown";
    let text;
    try {
        text = fs.readFileSync(taskPath, "utf8");
    }
    catch {
        return "unknown";
    }
    const type = readTaskType(text).type;
    return type === "coding" || type === "research" || type === "review" ? type : "unknown";
}
/** Resolve dp3's native `handling` answer to the candidate the asker supplied. */
export function resolveHandlingSelection(answers, options) {
    if (!isRecord(answers) || !Array.isArray(options))
        return undefined;
    const entry = answers.handling;
    const value = isRecord(entry) ? entry.value : undefined;
    if (typeof value !== "string" || value === "")
        return undefined;
    for (const raw of options) {
        if (!isRecord(raw) || raw.id !== value)
            continue;
        const label = typeof raw.label === "string" ? raw.label : undefined;
        const description = typeof raw.description === "string" ? raw.description : undefined;
        return { question: "handling", id: value, label, description };
    }
    return undefined;
}
/** The selection a four-dp answer names, or `undefined` when the child answered
 * a question set this contract no longer owns. */
function buildSelection(dp, answers, material) {
    if (dp === DP3_ID)
        return resolveHandlingSelection(answers, material.handling_options);
    const question = Object.keys(answers)[0];
    if (question === undefined)
        return undefined;
    const value = answers[question]?.value;
    if (typeof value !== "string" || value.trim() === "")
        return undefined;
    return { question, id: value };
}
/** The fixed material-preparation prompts handed to the asking agent
 * (design §2 "固定提示"). They are part of the tool contract, not UI copy. */
export const DECISION_MATERIAL_PROMPTS = {
    dp3: "dp3: 先写问题原文（question），再填 background{task_goal,current_state,decision_reason,constraints_impact}" +
        "，最后针对这个问题给 2..5 个可区分的处理候选 handling_options[{id:c1..cN,label<=80,description}]；" +
        "未知显式写未知，不检索旧答案替代生成，不预先替模型选。",
    dp2: "dp2（仅 PM）：按任务原文填 task_goal/task_requirements/task_deliverables 与 pm_decision_background" +
        "（为什么现在需要判断继续/拆小/直执/上抛人，以及约束）；有 worker 时才填真实的 worker_execution" +
        "（done/remaining/blocked/tried 与时间预算），没有就不填。",
    dp25: "dp25（仅 PM）：按四部分整理 delivery_goal（含用户验收条件）、actual_completion、" +
        "verification_evidence{verified,unverified}、unfinished_impact；[] 表示真实无该项；" +
        "产物与证据写具体出处，不用任务数或完成声明代证据。",
};
// ── Feedback: `mw decide lifecycle --stdin` (T02 writer, AC-014) ─────────────
/** The closed action set of T02's `decision_lifecycle.EXECUTED_ACTIONS`. An
 * action outside it is never recorded ("未知动作只未记录"). */
export const DECISION_EXECUTED_ACTIONS = [
    "type-read",
    "pm-handoff",
    "clarify",
    "narrow",
    "split",
    "direct-exec",
    "escalate",
    "continue",
    "user-confirm",
    "record",
];
/** The closed outcome set of T02's `decision_lifecycle.OUTCOMES`. */
export const DECISION_OUTCOMES = ["pending", "ok", "rework", "rollback", "inconclusive"];
/** Hard wall for one feedback child: a feedback write must never stall a tool. */
export const DECISION_LIFECYCLE_TIMEOUT_MS = 10_000;
/** Build `python -X utf8 mw.py decide lifecycle --stdin --json ...` (T05
 * contract). `--json` makes the writer report its own `recorded`/`status`, so a
 * consumer never infers success from exit code 0 (a `duplicate` replay is a
 * recorded fact too, and the payload says which one it was). */
export function buildLifecycleArgv(mwPy, projectDir) {
    return ["-X", "utf8", mwPy, "decide", "lifecycle", `--project=${projectDir}`, "--stdin", "--json"];
}
/** The real feedback child: the payload rides stdin, never argv. */
export const runLifecycleMw = async (request) => {
    const mwPy = findMwPy();
    if (!mwPy)
        return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
    return spawnWithTimeout([PYTHON_EXE, ...buildLifecycleArgv(mwPy, request.projectDir)], {
        timeoutMs: request.timeoutMs,
        stdin: request.input,
    });
};
// ── dp25: one judgment that really signs (T05 `decide sign --stdin`) ────────
/** The dp25 sign-off conclusion point (the managed PM sign path). */
export const DP25_ID = "dp25-signoff-conclusion";
/** The three conclusions T05 accepts (`decision_signoff_result.CONCLUSIONS`). */
export const DECISION_SIGNOFF_CONCLUSIONS = ["finalize", "continue", "user-confirm"];
/** Build `python -X utf8 mw.py decide sign <key> --stdin --json`.
 *
 * `--stdin` selects T05's versioned PM-material path; WITHOUT it the command
 * falls back to the legacy signoff-only auto path, which has no typed material
 * and therefore cannot be this feature's writer. */
export function buildSignArgv(mwPy, key, projectDir) {
    return ["-X", "utf8", mwPy, "decide", "sign", key, `--project=${projectDir}`, "--stdin", "--json"];
}
/** The real sign child: the envelope rides stdin, never argv. */
export const runSignMw = async (request) => {
    const mwPy = findMwPy();
    if (!mwPy)
        return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
    return spawnWithTimeout([PYTHON_EXE, ...buildSignArgv(mwPy, request.key, request.projectDir)], {
        timeoutMs: request.timeoutMs,
        stdin: request.input,
    });
};
/** Write one feedback fact through the single Python lifecycle writer.
 *
 * Never throws and never claims success: a timeout, a non-zero exit, a missing
 * CLI, an unparsable receipt or `recorded:false` all become `status:"failed"`
 * with the child's own class, so the caller can report "反馈缺失" instead of
 * fabricating the row. A `duplicate` receipt is reported as `duplicate` (the
 * same event replayed), never silently rewritten to `written`.
 *
 * Exported because the dp1 dispatch consumer is a second real writer face: one
 * CLI writer implementation serves dp1, dp3 and dp25.
 */
export async function writeDecisionLifecycle(projectDir, envelope, runner = runLifecycleMw) {
    const stage = envelope.stage;
    try {
        const raw = await runner({
            projectDir,
            input: JSON.stringify(envelope),
            timeoutMs: DECISION_LIFECYCLE_TIMEOUT_MS,
        });
        if (raw.timedOut)
            return { stage, status: "failed", recorded: false, reason: "timeout" };
        if (raw.error !== undefined)
            return { stage, status: "failed", recorded: false, reason: "unavailable" };
        const receipt = parseDecisionJson(raw.stdout);
        if (receipt === undefined) {
            return { stage, status: "failed", recorded: false, reason: raw.status === 0 ? "bad-response" : "cli-error" };
        }
        if (receipt.recorded !== true) {
            const errorClass = typeof receipt.error_class === "string" ? receipt.error_class : "rejected";
            return { stage, status: "failed", recorded: false, reason: errorClass };
        }
        const status = receipt.status === "duplicate" ? "duplicate" : "written";
        return { stage, status, recorded: true };
    }
    catch {
        return { stage, status: "failed", recorded: false, reason: "runner-threw" };
    }
}
/** Cap on captured child output so a runaway child cannot exhaust memory. */
const MAX_CHILD_OUTPUT_BYTES = 1_048_576;
/**
 * Spawn `argv` (no shell) and race it against a hard wall-clock timeout.
 *
 * `timedOut:true` means the child was killed after `timeoutMs`. The promise
 * settles on `close` (stdio drained); a killed child that never emits `close`
 * is force-resolved after a short grace so a tool call can never hang.
 */
export function spawnWithTimeout(argv, options = {}) {
    const timeoutMs = options.timeoutMs ?? ASK_DECISION_TIMEOUT_MS;
    return new Promise((resolve) => {
        let settled = false;
        let stdout = "";
        let stderr = "";
        let timedOut = false;
        let spawnError;
        let wallTimer;
        let graceTimer;
        const finish = (status) => {
            if (settled)
                return;
            settled = true;
            if (wallTimer !== undefined)
                clearTimeout(wallTimer);
            if (graceTimer !== undefined)
                clearTimeout(graceTimer);
            options.signal?.removeEventListener("abort", onAbort);
            const result = { status, stdout, stderr, timedOut };
            if (spawnError !== undefined)
                result.error = spawnError;
            resolve(result);
        };
        const append = (current, chunk) => {
            if (Buffer.byteLength(current, "utf8") >= MAX_CHILD_OUTPUT_BYTES)
                return current;
            return current + chunk;
        };
        const child = spawn(argv[0], argv.slice(1), {
            windowsHide: true,
            stdio: [options.stdin === undefined ? "ignore" : "pipe", "pipe", "pipe"],
        });
        if (options.stdin !== undefined) {
            // The whole request rides stdin: no temp file, nothing on argv.
            child.stdin?.on("error", () => {
                // A child that exits before reading its stdin is not a spawn failure.
            });
            child.stdin?.end(options.stdin, "utf8");
        }
        const kill = () => {
            try {
                // SIGKILL maps to TerminateProcess on Windows; no grandchildren are
                // left behind by `mw decide run` (it is a single Python process).
                child.kill("SIGKILL");
            }
            catch {
                // Already gone — `close` will settle the promise.
            }
            // A process killed mid-write may hold stdio open; never hang the tool.
            graceTimer = setTimeout(() => finish(child.exitCode), 2_000);
        };
        const onAbort = () => {
            if (settled)
                return;
            spawnError = "aborted";
            kill();
        };
        child.stdout?.setEncoding("utf8");
        child.stderr?.setEncoding("utf8");
        child.stdout?.on("data", (chunk) => {
            stdout = append(stdout, chunk);
        });
        child.stderr?.on("data", (chunk) => {
            stderr = append(stderr, chunk);
        });
        child.on("error", (err) => {
            spawnError = err.message;
            finish(null);
        });
        child.on("close", (code) => finish(code));
        if (options.signal !== undefined) {
            if (options.signal.aborted)
                onAbort();
            else
                options.signal.addEventListener("abort", onAbort, { once: true });
        }
        wallTimer = setTimeout(() => {
            if (settled)
                return;
            timedOut = true;
            kill();
        }, timeoutMs);
    });
}
/** Build the `python -X utf8 mw.py decide run ...` argv.
 *
 * `viaStdin` (the four-dp envelope) carries routing only: the whole
 * `{material, meta}` payload rides stdin. The legacy path keeps riding a temp
 * `--request-file` (design D-003). The caller prepends {@link PYTHON_EXE}; this
 * list is platform-independent on purpose. */
export function buildDecideArgv(mwPy, request, requestFile) {
    const routing = ["-X", "utf8", mwPy, "decide", "run", `--project=${request.projectDir}`, "--dp", request.dp];
    if (request.viaStdin === true)
        return [...routing, "--stdin", "--json"];
    return [...routing, "--request-file", requestFile ?? "", "--json"];
}
/** Write the request JSON to a private temp dir and return `{dir, file}`. */
function writeRequestFile(input) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-decide-"));
    const file = path.join(dir, "request.json");
    fs.writeFileSync(file, input, { encoding: "utf8", mode: 0o600 });
    return { dir, file };
}
/**
 * The real child: reuse mw-runner's interpreter/path resolution. The four-dp
 * envelope is piped on stdin (`--stdin`); the legacy path writes the request to
 * a temp file and always cleans it up.
 */
export const runDecideMw = async (request, signal) => {
    const mwPy = findMwPy();
    if (!mwPy)
        return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
    if (request.viaStdin === true) {
        return spawnWithTimeout([PYTHON_EXE, ...buildDecideArgv(mwPy, request)], {
            timeoutMs: request.timeoutMs,
            signal,
            stdin: request.input,
        });
    }
    let files;
    try {
        files = writeRequestFile(request.input);
    }
    catch (err) {
        return {
            status: null,
            stdout: "",
            stderr: "",
            error: err instanceof Error ? err.message : String(err),
            timedOut: false,
        };
    }
    try {
        return await spawnWithTimeout([PYTHON_EXE, ...buildDecideArgv(mwPy, request, files.file)], {
            timeoutMs: request.timeoutMs,
            signal,
        });
    }
    finally {
        try {
            fs.rmSync(files.dir, { recursive: true, force: true });
        }
        catch {
            // Best effort: a leaked temp dir is not worth failing the tool call.
        }
    }
};
// ── Response mapping ────────────────────────────────────────────────────────
function asAnswers(value) {
    if (!isRecord(value))
        return undefined;
    const answers = {};
    for (const [qid, raw] of Object.entries(value)) {
        if (!isRecord(raw) || !("value" in raw))
            continue;
        const entry = { value: raw.value };
        if (typeof raw.confidence === "number" && Number.isFinite(raw.confidence))
            entry.confidence = raw.confidence;
        answers[qid] = entry;
    }
    return Object.keys(answers).length > 0 ? answers : undefined;
}
/** Parse a child's stdout: the whole payload first, then each non-empty line
 * from the last one backwards (a child may print a diagnostic after its JSON
 * receipt). Never throws. */
export function parseDecisionJson(stdout) {
    const trimmed = stdout.trim();
    const lines = trimmed.split("\n");
    const candidates = [trimmed, ...[...lines].reverse().map((line) => line.trim())];
    for (const text of candidates) {
        if (!text)
            continue;
        try {
            const parsed = JSON.parse(text);
            if (isRecord(parsed))
                return parsed;
        }
        catch {
            // Try the next candidate.
        }
    }
    return undefined;
}
/** The fixed no-guessing line appended to every unavailable payload. */
export function unavailableDirective(reason, dp) {
    const base = `UNAVAILABLE(${reason}) — ${ASK_DECISION_GUESS_DIRECTIVE}，不要执行被门控的动作，` +
        `不要用别的工具绕过，也不要重复问同一个问题。上报 "blocked on decision ${dp}" 并等待人工裁决。`;
    if (reason === "disabled") {
        return `${base} disabled ≠ approval：决策点未开启不等于放行，被门控的动作仍受其常规工具权限约束。`;
    }
    return base;
}
/** Terminal directive emitted once a dp hits the per-turn block cap. */
export function terminalDirective(dp, blocks) {
    return (`TERMINAL: "${dp}" has been blocked ${blocks} time(s) in this turn. ${ASK_DECISION_GUESS_DIRECTIVE}。` +
        `停止重试，上报 "blocked on decision ${dp}" 并结束本轮（不要再次调用 ask_decision）。`);
}
function jsonText(payload) {
    return JSON.stringify(payload);
}
function unavailable(reason, dp, spawned, extra = {}) {
    const payload = {
        available: false,
        unavailable: reason,
        action: ASK_DECISION_BLOCKED_ACTION,
    };
    if (extra.escalated_reason !== undefined)
        payload.escalated_reason = extra.escalated_reason;
    if (extra.missing_fields !== undefined && extra.missing_fields.length > 0) {
        payload.missing_fields = extra.missing_fields;
    }
    return { payload, text: `${jsonText(payload)}\n${unavailableDirective(reason, dp)}`, spawned };
}
/**
 * Ask one decision point. Never throws: every failure (unregistered dp, wrong
 * role, structurally incomplete material, missing mw.py, timeout, non-zero
 * exit, unparsable JSON, absent answer) returns the structured unavailable
 * payload plus the fixed directive.
 *
 * It performs no authorization check of its own beyond the ROLE surface
 * (a worker may not borrow the PM's dp2/dp25): `decide_for` owns
 * `enabled`/`mode`/`acted` (D-036) and this function only reports what the
 * child said.
 */
export async function runAskDecision(input) {
    const started = Date.now();
    const dp = input.dp;
    // Zero-spawn refusal for an id the registry cannot resolve. The enum in the
    // tool schema already rejects it; `runAskDecision` is also called directly.
    if (!isRegisteredDp(dp))
        return unavailable("disabled", dp, false);
    const role = input.initiatorRole ?? "unknown";
    // The originator is structural (the registering window), so a worker cannot
    // reach a PM decision point even by naming it (AC-006).
    if (isPmOnlyDp(dp) && role !== "pm")
        return unavailable(ASK_DECISION_REASON_ROLE_FORBIDDEN, dp, false);
    if (input.taskBefore !== undefined &&
        (!(input.taskKey ?? "").trim() || !isTaskStateSnapshot(input.taskBefore) || !isMaterialDp(dp)))
        return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, { missing_fields: ["meta.task_before"] });
    // dp25 is the ONE judgment that really signs (T05 `decide sign --stdin`): the
    // sign CLI calls the model itself and writes `sign-final.md` (or hands a
    // concrete next step back). Routing it through `decide run` would need a
    // second approval/sign step, which the approved design refuses.
    if (dp === DP25_ID)
        return runSignoffAskDecision(input, dp, role, started);
    if (isMaterialDp(dp))
        return runMaterialAskDecision(input, dp, role, started);
    return runLegacyAskDecision(input, dp, started);
}
/** Diagnostic for a locally refused call (no child ran). */
export function refusalOutcome(reason, dp, missing) {
    return unavailable(reason, dp, false, { missing_fields: missing });
}
/** Spawn one decision child and parse its payload; every failure is DATA. */
async function callDecideChild(dp, request, runner, signal) {
    let raw;
    try {
        raw = await runner(request, signal);
    }
    catch {
        return { ok: false, outcome: unavailable("upstream-error", dp, true) };
    }
    if (raw.timedOut)
        return { ok: false, outcome: unavailable("timeout", dp, true) };
    if (raw.error !== undefined)
        return { ok: false, outcome: unavailable("upstream-error", dp, true) };
    if (raw.status !== 0)
        return { ok: false, outcome: unavailable("upstream-error", dp, true) };
    const response = parseDecisionJson(raw.stdout);
    if (response === undefined)
        return { ok: false, outcome: unavailable("bad-response", dp, true) };
    if (response.available !== true) {
        const rawReason = typeof response.reason === "string" ? response.reason : "";
        const reason = ASK_DECISION_PYTHON_REASONS.has(rawReason) ? rawReason : "upstream-error";
        // The child's own 7-value escalation verdict travels beside (never instead
        // of) the frozen legacy reason (D-021 / D-030).
        const escalated = typeof response.escalated_reason === "string" && response.escalated_reason !== ""
            ? response.escalated_reason
            : undefined;
        return { ok: false, outcome: unavailable(reason, dp, true, { escalated_reason: escalated }) };
    }
    return { ok: true, response };
}
/** The four-dp envelope path: verbatim material + local `{material, meta}`.
 *
 * Order (design §2/§4.1): validate the material against the generated registry,
 * build the local envelope (fresh `logical_id` per real call), refuse an
 * over-budget material instead of truncating it, send, then resolve the native
 * selection back to the candidate the asker wrote and record `consumed`
 * through the single Python lifecycle writer. Nothing here executes business
 * work or writes a sign-off.
 */
async function runMaterialAskDecision(input, dp, role, started) {
    const validated = validateDecisionMaterial(dp, input.material);
    if (!validated.ok) {
        return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, {
            missing_fields: validated.issues.map((issue) => issue.field),
        });
    }
    const key = (input.key ?? "").trim();
    if (key === "")
        return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, { missing_fields: ["meta.key"] });
    const meta = buildDecisionToolMeta({
        key,
        taskKey: input.taskKey ?? null,
        initiatorRole: role,
        retryOf: input.retryOf ?? null,
        taskBefore: input.taskBefore,
    });
    const request = {
        projectDir: input.projectDir,
        dp,
        input: JSON.stringify({ material: validated.material, meta }),
        timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
        viaStdin: true,
    };
    const called = await callDecideChild(dp, request, input.runner ?? runDecideMw, input.signal);
    if (!called.ok)
        return called.outcome;
    const response = called.response;
    const answers = asAnswers(response.answers);
    if (answers === undefined)
        return unavailable("bad-response", dp, true);
    // The four authority keys are the child's verdict, taken verbatim (D-036).
    const decisionId = typeof response.decision_id === "string" ? response.decision_id : "";
    const mode = response.mode;
    const acted = response.acted;
    if (decisionId === "" || (mode !== "auto" && mode !== "suggest") || typeof acted !== "boolean") {
        return unavailable("bad-response", dp, true);
    }
    const selection = buildSelection(dp, answers, validated.material);
    if (selection === undefined) {
        // An answer set this contract does not own (old question ids) is never
        // mapped onto a candidate: that would invent the receipt (AC-006).
        return unavailable("bad-response", dp, true);
    }
    const latency = typeof response.latency_ms === "number" ? response.latency_ms : Date.now() - started;
    const payload = {
        available: true,
        decision_id: decisionId,
        mode,
        acted,
        answers,
        confidence_source: typeof response.confidence_source === "string" && response.confidence_source !== ""
            ? response.confidence_source
            : "unknown",
        latency_ms: latency,
        selection,
    };
    // The asker really received the selection => `consumed` is a fact, not a
    // completion. `executed`/`settled` stay with the explicit receipt op.
    payload.feedback = await writeDecisionLifecycle(input.projectDir, {
        meta,
        decision_id: decisionId,
        dp,
        stage: "consumed",
        event_id: `consumed-${meta.logical_id}`,
        answer: selection.id,
    }, input.lifecycleRunner ?? runLifecycleMw);
    return { payload, text: jsonText(payload), spawned: true, meta };
}
/** The dp25 sign path: ONE judgment, the CLI signs or hands over.
 *
 * The child is `mw decide sign <key> --stdin --json` (never `decide run` + a
 * second `sign` call). It records the creation fact, asks
 * `dp25-signoff-conclusion` ONCE, persists the result record, and:
 * - `finalize` → writes/validates `evidence/review/sign-final.md` and records
 *   its own consumed + signoff lifecycle facts;
 * - `continue`/`user-confirm` → zero sign-off writes, one executed fact and a
 *   concrete `handoff` for the PM/user.
 * This function only maps that receipt; it never signs, approves twice or
 * invents a mode/role verdict of its own.
 */
async function runSignoffAskDecision(input, dp, role, started) {
    const validated = validateDecisionMaterial(dp, input.material);
    if (!validated.ok) {
        return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, {
            missing_fields: validated.issues.map((issue) => issue.field),
        });
    }
    const key = (input.key ?? "").trim();
    if (key === "")
        return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, { missing_fields: ["meta.key"] });
    const meta = buildDecisionToolMeta({
        key,
        taskKey: input.taskKey ?? null,
        initiatorRole: role,
        retryOf: input.retryOf ?? null,
        taskBefore: input.taskBefore,
    });
    let raw;
    try {
        raw = await (input.signRunner ?? runSignMw)({
            projectDir: input.projectDir,
            key,
            input: JSON.stringify({ material: validated.material, meta }),
            timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
        });
    }
    catch {
        return unavailable("upstream-error", dp, true);
    }
    if (raw.timedOut)
        return unavailable("timeout", dp, true);
    if (raw.error !== undefined)
        return unavailable("upstream-error", dp, true);
    const receipt = parseDecisionJson(raw.stdout);
    if (receipt === undefined)
        return unavailable("bad-response", dp, true);
    const conclusion = typeof receipt.conclusion === "string" ? receipt.conclusion : "";
    const rawStatus = typeof receipt.signoff_status === "string" ? receipt.signoff_status : "";
    const signoffStatus = rawStatus === "written" ||
        rawStatus === "existing" ||
        rawStatus === "not-required" ||
        rawStatus === "invalid-existing" ||
        rawStatus === "disabled"
        ? rawStatus
        : "failed";
    const problems = Array.isArray(receipt.problems)
        ? receipt.problems.filter((item) => typeof item === "string")
        : [];
    if (raw.status !== 0 || !DECISION_SIGNOFF_CONCLUSIONS.includes(conclusion) || signoffStatus === "failed") {
        // No fabricated success: the CLI's own problems are its stderr/receipt
        // channel. When the CLI refused the material itself (budget/shape), its
        // vocabulary is reported verbatim instead of a bare `upstream-error`, so a
        // caller can tell an over-budget refusal from a transport failure.
        const refusedOversize = problems.some((item) => item.includes(ASK_DECISION_REASON_INPUT_OVERSIZE));
        const refusedIncomplete = problems.some((item) => item.includes(ASK_DECISION_REASON_INPUT_INCOMPLETE));
        if (refusedOversize) {
            return unavailable(ASK_DECISION_REASON_INPUT_OVERSIZE, dp, true, {
                escalated_reason: ASK_DECISION_REASON_INPUT_OVERSIZE,
            });
        }
        if (refusedIncomplete) {
            return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, true, {
                escalated_reason: ASK_DECISION_REASON_INPUT_INCOMPLETE,
            });
        }
        return unavailable("upstream-error", dp, true);
    }
    const decisionId = typeof receipt.decision_id === "string" ? receipt.decision_id : "";
    if (decisionId === "")
        return unavailable("bad-response", dp, true);
    const signoff = {
        status: signoffStatus,
        second_approval: typeof receipt.second_approval === "number" ? receipt.second_approval : 0,
    };
    if (typeof receipt.signoff_path === "string" && receipt.signoff_path !== "") {
        signoff.path = receipt.signoff_path;
    }
    if (typeof receipt.record_status === "string")
        signoff.record_status = receipt.record_status;
    if (typeof receipt.model_called === "boolean")
        signoff.model_called = receipt.model_called;
    if (typeof receipt.feedback_status === "string")
        signoff.feedback_status = receipt.feedback_status;
    if (Array.isArray(receipt.feedback_stages)) {
        signoff.feedback_stages = receipt.feedback_stages.filter((item) => isRecord(item));
    }
    if (problems.length > 0)
        signoff.problems = problems;
    if (isRecord(receipt.handoff)) {
        const handoff = receipt.handoff;
        signoff.handoff = {
            owner: typeof handoff.owner === "string" ? handoff.owner : undefined,
            kind: typeof handoff.kind === "string" ? handoff.kind : undefined,
            signoff_writes: typeof handoff.signoff_writes === "number" ? handoff.signoff_writes : undefined,
            instruction: typeof handoff.instruction === "string" ? handoff.instruction : undefined,
        };
    }
    const acted = signoffStatus === "written" || signoffStatus === "existing" || signoffStatus === "not-required";
    const payload = {
        available: true,
        decision_id: decisionId,
        // `decide sign` exposes no execution mode: reporting one would be a local
        // verdict the authority never gave (mode is optional on purpose).
        acted,
        answers: { "q-conclusion": { value: conclusion } },
        // The sign receipt does not echo confidence provenance; the persisted
        // result record is the authority for it. `unknown` never gates anything.
        confidence_source: "unknown",
        latency_ms: Date.now() - started,
        selection: { question: "q-conclusion", id: conclusion },
        signoff,
    };
    return { payload, text: jsonText(payload), spawned: true, meta };
}
/** The legacy L0/L1 path of the other 21 dps (unchanged behaviour). */
async function runLegacyAskDecision(input, dp, started) {
    const state = buildDecisionState({ dp, note: input.note, taskKey: input.taskKey });
    // `decide_for` step 5 refuses a state that misses a registry-required field,
    // so report the field names (L0) instead of spending a round trip that can
    // only come back `input-incomplete`/`bad-response` (MAJOR-2).
    const missing = missingDecisionStateFields(dp, state);
    if (missing.length > 0) {
        return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, { missing_fields: missing });
    }
    if (canonicalStateBytes(state) > ASK_DECISION_MAX_STATE_BYTES) {
        return unavailable(ASK_DECISION_REASON_INPUT_OVERSIZE, dp, false);
    }
    const request = {
        projectDir: input.projectDir,
        dp,
        input: buildDecisionRequestJson(state),
        timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
    };
    const called = await callDecideChild(dp, request, input.runner ?? runDecideMw, input.signal);
    if (!called.ok)
        return called.outcome;
    const response = called.response;
    const latency = typeof response.latency_ms === "number" ? response.latency_ms : Date.now() - started;
    let answers = asAnswers(response.answers);
    if (answers === undefined)
        return unavailable("bad-response", dp, true);
    if (input.question !== undefined) {
        const picked = answers[input.question];
        if (picked === undefined)
            return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, true);
        answers = { [input.question]: picked };
    }
    // The four authority keys are the child's verdict, taken verbatim (D-036 /
    // D-041): no local id concatenation, no `mode` mirror, no `acted` derived
    // from `mode` (an `intent="answer"` decision is archived `acted=false`).
    const decisionId = typeof response.decision_id === "string" ? response.decision_id : "";
    const mode = response.mode;
    const acted = response.acted;
    if (decisionId === "" || (mode !== "auto" && mode !== "suggest") || typeof acted !== "boolean") {
        return unavailable("bad-response", dp, true);
    }
    const payload = {
        available: true,
        decision_id: decisionId,
        mode,
        acted,
        answers,
        confidence_source: typeof response.confidence_source === "string" && response.confidence_source !== ""
            ? response.confidence_source
            : "unknown",
        latency_ms: latency,
    };
    return { payload, text: jsonText(payload), spawned: true };
}
/** Per-dp, per-turn block counter (design Q3 §3.3). One instance per worker
 * window; `turn_start` calls {@link DecisionBlockCounter.reset}. */
export function createDecisionBlockCounter() {
    const counts = new Map();
    return {
        reset: () => counts.clear(),
        recordBlock: (dp) => {
            const next = (counts.get(dp) ?? 0) + 1;
            counts.set(dp, next);
            return next;
        },
        clear: (dp) => {
            counts.delete(dp);
        },
        countFor: (dp) => counts.get(dp) ?? 0,
    };
}
function ownerKeyFromTaskPath(taskPath) {
    // <control>/.agenticdoc/<key>/workers/<task>/task.md
    const key = path.basename(path.dirname(path.dirname(path.dirname(taskPath))));
    return key === "" || key === "." ? undefined : key;
}
/** The REAL task id of a worker card path (never "the latest task"). */
function workerTaskKeyFromTaskPath(taskPath) {
    const task = path.basename(path.dirname(taskPath));
    return task === "" || task === "." || task === "workers" ? undefined : task;
}
function appendDecisionTrace(tracePath, line) {
    if (tracePath === undefined)
        return;
    try {
        fs.mkdirSync(path.dirname(tracePath), { recursive: true });
        fs.appendFileSync(tracePath, `${line}\n`, "utf8");
    }
    catch {
        // Diagnostic append — a failure must never break the tool call.
    }
}
const DP_ENUM_SCHEMA = Type.Union(ASK_DECISION_DP_IDS.map((id) => Type.Literal(id)), { description: "Registered decision point id (unknown ids are rejected)" });
/** The business material of the four material dps (dp2/dp3/dp25).
 *
 * A documented, permissive object: the CLOSED key set and the per-field rules
 * are enforced by {@link validateDecisionMaterial} against the generated
 * registry (one authority), so an undeclared key is refused with its name
 * instead of a schema error the model cannot learn from. */
const MATERIAL_SCHEMA = Type.Optional(Type.Object({
    task_goal: Type.Optional(Type.String({ description: "dp2: task goal 原文" })),
    task_requirements: Type.Optional(Type.String({ description: "dp2: task requirements 原文" })),
    task_deliverables: Type.Optional(Type.String({ description: "dp2: task deliverables 原文" })),
    pm_decision_background: Type.Optional(Type.String({ description: "dp2: why a checkpoint decision is needed now, plus constraints" })),
    worker_execution: Type.Optional(Type.String({ description: "dp2: REAL worker execution (done/remaining/blocked/tried); omit when none" })),
    question: Type.Optional(Type.String({ description: "dp3: the clarifying question verbatim" })),
    background: Type.Optional(Type.Object({
        task_goal: Type.Optional(Type.String()),
        current_state: Type.Optional(Type.String()),
        decision_reason: Type.Optional(Type.String()),
        constraints_impact: Type.Optional(Type.String()),
    }, { description: "dp3: the four background facts (unknown stays unknown)" })),
    handling_options: Type.Optional(Type.Array(Type.Object({
        id: Type.String({ description: "c1..cN, contiguous" }),
        label: Type.String({ description: "single line, <= 80 chars" }),
        description: Type.String({ description: "non-empty, problem-specific; never truncated" }),
    }), { description: "dp3: 2..5 distinguishable handling candidates" })),
    delivery_goal: Type.Optional(Type.String({ description: "dp25: delivery goal incl. acceptance conditions" })),
    actual_completion: Type.Optional(Type.String({ description: "dp25: what was actually completed" })),
    verification_evidence: Type.Optional(Type.Object({
        verified: Type.Optional(Type.Array(Type.String())),
        unverified: Type.Optional(Type.Array(Type.String())),
    }, { description: "dp25: verified vs unverified evidence; [] is a real 'none'" })),
    unfinished_impact: Type.Optional(Type.Array(Type.String(), { description: "dp25: unfinished items + impact; [] is a real 'none'" })),
}, {
    description: "Business material of dp2/dp3/dp25, verbatim (see the fixed preparation prompts). " +
        "Identity/association (key, task, role, logical_id) is never part of it.",
}));
/** Tool parameter schema (exported so tests can assert the dp enum surface). */
export const ASK_DECISION_PARAMETERS = Type.Object({
    dp: DP_ENUM_SCHEMA,
    trigger: Type.String({
        minLength: 1,
        maxLength: 256,
        pattern: "^[^\\s:]+$",
        description: "Audit trigger label, e.g. <task_key> or <task_key>#ckpt3 (no ':' per D-023); " +
            "the decision id itself is resolved by the service",
    }),
    question: Type.Optional(Type.String({
        minLength: 1,
        maxLength: 64,
        description: "Single registry question id; omit for the full question set",
    })),
    note: Type.Optional(Type.String({
        maxLength: 800,
        description: "Short L0/L1 context summary (no secrets/absolute paths/code)",
    })),
    material: MATERIAL_SCHEMA,
    key: Type.Optional(Type.String({
        minLength: 1,
        maxLength: 64,
        description: "Owning AgenticTask key (PM mode: required; workers get it from their card)",
    })),
    task_before: Type.Optional(AGENT_TASK_STATE_SCHEMA),
    task_key: Type.Optional(Type.String({
        minLength: 1,
        maxLength: 64,
        description: "The REAL task this decision belongs to; omit when the decision has no task",
    })),
}, { additionalProperties: false });
/** Receipt parameters: the ONLY way `executed`/`settled` are ever recorded. */
export const DECISION_RECEIPT_PARAMETERS = Type.Object({
    decision_id: Type.String({ minLength: 1, description: "The decision this receipt is about" }),
    stage: Type.Union([Type.Literal("executed"), Type.Literal("settled")], {
        description: "executed = the action really happened; settled = this round of handling finished",
    }),
    action: Type.Optional(Type.String({ description: "executed: one closed action label (pm-handoff/clarify/narrow/...)" })),
    result: Type.Optional(Type.String({ description: "executed: what the result was based on" })),
    outcome: Type.Optional(Type.String({ description: "settled: one closed outcome (ok/rework/rollback/inconclusive/pending)" })),
    reason: Type.Optional(Type.String({ description: "settled/executed: short free-text reason" })),
    event_id: Type.Optional(Type.String({ description: "Reuse the SAME id only when retrying this very write" })),
    task_after: Type.Optional(AGENT_TASK_STATE_SCHEMA),
}, { additionalProperties: false });
/**
 * Register the shared decision tools (`ask_decision` + `decision_receipt`).
 *
 * The SAME entry serves both asking roles (design D002): the worker branch calls
 * it with the worker's own card role, the PM branch with `initiatorRole: "pm"`.
 * The role is structural, so a worker cannot reach a PM-only dp (dp2/dp25) even
 * by naming it, and no model parameter can claim to be the PM (AC-006/AC-010).
 *
 * Visibility: the tool is registered unconditionally and then appended to the
 * per-turn active set by a `before_agent_start` handler that runs AFTER the
 * worker's own handler (index.ts registers this module after
 * `workerModeActivate`), so the append wins over the role allowlist
 * recomputation. It never enters `TOOL_ALLOWLISTS` (T-17 Python parity lock).
 *
 * The process keeps one in-memory map of the decisions this window asked. The
 * receipt op resolves a `decision_id` against it, so `executed`/`settled` can
 * only ever be written for a decision this window really made (and with the
 * same `logical_id` meta).
 */
export function registerAskDecisionTool(pi, options = {}) {
    const taskPath = options.taskPath ?? process.env.PI_WORKER_TASK;
    const resolvedTaskPath = taskPath !== undefined && taskPath !== "" ? path.resolve(taskPath) : undefined;
    const projectDir = options.projectDir ??
        (resolvedTaskPath !== undefined ? controlRootFromTaskPath(resolvedTaskPath) : process.cwd());
    const tracePath = options.tracePath ??
        (resolvedTaskPath !== undefined ? path.join(path.dirname(resolvedTaskPath), "trace.log") : undefined);
    // The worker's owning key/task come from its own card path; the PM has no
    // task path, so it must pass its `key` (and a task only when it names one).
    const ownerKey = options.key ?? (resolvedTaskPath !== undefined ? ownerKeyFromTaskPath(resolvedTaskPath) : undefined);
    const workerTaskKey = options.taskKey !== undefined
        ? options.taskKey
        : resolvedTaskPath !== undefined
            ? (workerTaskKeyFromTaskPath(resolvedTaskPath) ?? null)
            : null;
    const initiatorRole = options.initiatorRole ?? initiatorRoleFromWorkerTask(resolvedTaskPath);
    const counter = createDecisionBlockCounter();
    /** The decisions this window asked (receipt lookup + the join meta). */
    const asked = new Map();
    // One turn = one retry window: the same dp gets a fresh budget per turn.
    pi.on("turn_start", () => counter.reset());
    pi.registerTool({
        name: ASK_DECISION_TOOL,
        label: ASK_DECISION_TOOL,
        description: "Ask the external decision service for a human-style ruling on a gated decision point. " +
            "Returns ONE line of JSON: {available, decision_id, mode, acted, answers, confidence_source, latency_ms}" +
            ", plus {selection, feedback} on the four-dp material path. " +
            "available=false means UNAVAILABLE: the gated action stays blocked — do NOT guess, do NOT work around it, " +
            'report "blocked on decision <dp>" and stop. The failure line also carries escalated_reason, and for ' +
            "input-incomplete, missing_fields.",
        promptSnippet: "ask_decision(dp, trigger, material?, question?, note?) — ask the decision service before a gated action; " +
            "available=false means blocked, never guess.",
        promptGuidelines: [
            "Call ask_decision ONLY with a dp id from the enum and the trigger_id from your task context " +
                "(<task_key> or <task_key>#ckpt<N>); never invent a dp id, trigger or question id.",
            'available=false is a terminal answer for this attempt: report "blocked on decision <dp>" and wait ' +
                "for a human. Repeating the same call in one turn is cut off by the retry breaker.",
            "unavailable=input-incomplete lists missing_fields: fix the named MATERIAL fields and retry once; " +
                "a missing field is never filled by inference.",
            "note is an L0/L1 summary (<=600 bytes): no credentials, no user quotes, no absolute paths, no code.",
            "mode=suggest only archives an advisory row; acted is the service's verdict and never your own " +
                "inference from the mode.",
            // ── the fixed material prompts (design §2), one per material dp ────
            DECISION_MATERIAL_PROMPTS.dp3,
            DECISION_MATERIAL_PROMPTS.dp2,
            DECISION_MATERIAL_PROMPTS.dp25,
            "task_before is an optional local Agent report of this task BEFORE the decision, never model material. Use source=agent-report, an ISO timestamp with timezone, and null for unrecorded progress; do not substitute current state for past state or invent observations.",
            "dp2/dp25 are PM decisions: a worker window is refused (role-forbidden) and must report the block " +
                "instead of asking.",
            "After the selection: act only inside your existing authority, then call decision_receipt with the " +
                "action you really performed (executed) and, when this round is handled, settled. Never receipt what " +
                "did not happen; dp25 never signs here (the sign-off writer is the CLI).",
            "dp2 handling: a narrow that changes the confirmed delivery goal still goes to the user; direct-exec " +
                "first coordinates the live worker's write surface; escalate asks the user a CONCRETE risk/authority " +
                "question. The model's choice alone never rewrites, terminates or splits a task.",
            "dp25 branches: finalize is decided AND signed by the same `mw decide sign` call - the tool writes the sign-off file itself, so never ask the PM for a second approval or a second model call; continue and user-confirm write no sign-off and end with the concrete gaps to advance or the concrete items to confirm.",
        ],
        parameters: ASK_DECISION_PARAMETERS,
        // Sequential: an ask changes gate state, so it must not race the tools
        // it authorizes (design Q1 §1.1).
        executionMode: "sequential",
        execute: async (_toolCallId, params, signal) => {
            const requestedKey = params.key ?? options.key ?? ownerKey;
            if (params.key !== undefined && ownerKey !== undefined && params.key.trim() !== ownerKey) {
                // A window never decides under another key: the association must stay
                // exact instead of being rewritten by a model parameter (AC-010).
                const refused = refusalOutcome("input-incomplete", params.dp, ["meta.key"]);
                appendDecisionTrace(tracePath, `[DECISION_UNAVAILABLE] ${new Date().toISOString()} dp=${params.dp} trigger=${params.trigger} ` +
                    "reason=input-incomplete field=meta.key count=1 max=" +
                    `${ASK_DECISION_MAX_BLOCKED_PER_TURN} role=${initiatorRole}`);
                return { content: [{ type: "text", text: refused.text }], details: refused.payload };
            }
            const requestedTask = params.task_key ?? workerTaskKey ?? null;
            if (workerTaskKey !== null && params.task_key !== undefined && params.task_key.trim() !== workerTaskKey) {
                const refused = refusalOutcome("input-incomplete", params.dp, ["meta.task_key"]);
                return { content: [{ type: "text", text: refused.text }], details: refused.payload };
            }
            const outcome = await runAskDecision({
                projectDir,
                dp: params.dp,
                trigger: params.trigger,
                question: params.question,
                note: params.note,
                material: params.material,
                key: requestedKey,
                taskKey: requestedTask,
                taskBefore: params.task_before,
                initiatorRole,
                runner: options.runner,
                lifecycleRunner: options.lifecycleRunner,
                signRunner: options.signRunner,
                timeoutMs: options.timeoutMs,
                signal,
            });
            const iso = new Date().toISOString();
            if (outcome.payload.available) {
                counter.clear(params.dp);
                if (isMaterialDp(params.dp) && outcome.meta !== undefined) {
                    // Same decision, same logical_id: the receipt joins the consume row.
                    asked.set(outcome.payload.decision_id, { meta: outcome.meta, dp: params.dp });
                }
                appendDecisionTrace(tracePath, `[DECISION] ${iso} dp=${params.dp} trigger=${params.trigger} ` +
                    `decision_id=${outcome.payload.decision_id} mode=${outcome.payload.mode ?? "-"} ` +
                    `acted=${String(outcome.payload.acted)} source=${outcome.payload.confidence_source} ` +
                    `latency_ms=${outcome.payload.latency_ms} role=${initiatorRole}` +
                    (outcome.payload.selection !== undefined ? ` selection=${outcome.payload.selection.id}` : "") +
                    (outcome.payload.feedback !== undefined
                        ? ` feedback=${outcome.payload.feedback.stage}:${outcome.payload.feedback.status}`
                        : ""));
                return { content: [{ type: "text", text: outcome.text }], details: outcome.payload };
            }
            const reason = outcome.payload.unavailable;
            const escalated = outcome.payload.escalated_reason !== undefined
                ? ` escalated_reason=${outcome.payload.escalated_reason}`
                : "";
            const blocks = counter.recordBlock(params.dp);
            appendDecisionTrace(tracePath, `[DECISION_UNAVAILABLE] ${iso} dp=${params.dp} trigger=${params.trigger} reason=${reason}` +
                `${escalated} count=${blocks} max=${ASK_DECISION_MAX_BLOCKED_PER_TURN} role=${initiatorRole}`);
            if (blocks < ASK_DECISION_MAX_BLOCKED_PER_TURN) {
                return { content: [{ type: "text", text: outcome.text }], details: outcome.payload };
            }
            appendDecisionTrace(tracePath, `[DECISION_RETRY_STOP] ${iso} dp=${params.dp} trigger=${params.trigger} reason=${reason} ` +
                `count=${blocks} max=${ASK_DECISION_MAX_BLOCKED_PER_TURN} role=${initiatorRole}`);
            // `terminate` stops the tool loop when every finalized result in the
            // batch asks for it (agent-loop.ts:582-584); ask_decision is
            // sequential, so a batch that contains it stops here.
            return {
                content: [{ type: "text", text: `${outcome.text}\n${terminalDirective(params.dp, blocks)}` }],
                details: outcome.payload,
                terminate: true,
            };
        },
    });
    // The receipt op: `consumed` is automatic (the asker received the selection);
    // `executed`/`settled` are only ever recorded here, after the real action.
    pi.registerTool({
        name: DECISION_RECEIPT_TOOL,
        label: DECISION_RECEIPT_TOOL,
        description: "Record what really happened with a decision this window asked: executed (the action happened) " +
            "and settled (this round of handling finished). Returns ONE line of JSON " +
            "{stage, status, decision_id}; status=failed means the feedback ledger rejected the write — the " +
            "action itself is not undone. An unknown decision id or action is NOT recorded.",
        promptSnippet: "decision_receipt(decision_id, stage, action?, result?, outcome?, reason?) — record the real action/closure.",
        promptGuidelines: [
            "Call decision_receipt AFTER the action really happened, with the same decision_id the ask returned.",
            "executed needs one closed action: type-read, pm-handoff, clarify, narrow, split, direct-exec, " +
                "escalate, continue, user-confirm, record.",
            "settled needs one closed outcome: pending, ok, rework, rollback, inconclusive. settled is this round, " +
                "not the whole task.",
            "Never receipt an action you did not perform; a failed receipt is reported, not retried with a new action.",
            "task_after is an optional local Agent report AFTER the actual handling, for this decision's exact task. It does not execute work. Use source=agent-report and the actual observation time; missing progress is null, not guessed. Round ok is not task done.",
        ],
        parameters: DECISION_RECEIPT_PARAMETERS,
        executionMode: "sequential",
        execute: async (_toolCallId, params) => {
            const refusal = (reason, dp) => {
                const refused = refusalOutcome(reason, dp ?? "unknown");
                return {
                    content: [{ type: "text", text: refused.text }],
                    details: {
                        decision_id: params.decision_id,
                        dp,
                        stage: params.stage,
                        status: "refused",
                        unavailable: reason,
                    },
                };
            };
            const known = asked.get(params.decision_id);
            if (known === undefined)
                return refusal(ASK_DECISION_REASON_UNKNOWN_DECISION, null);
            if (params.task_after !== undefined &&
                (known.meta.task_key === null || !isTaskStateSnapshot(params.task_after)))
                return refusal(ASK_DECISION_REASON_INPUT_INCOMPLETE, known.dp);
            const eventId = params.event_id ?? randomUUID();
            let envelope;
            if (params.stage === "executed") {
                const action = params.action ?? "";
                if (!DECISION_EXECUTED_ACTIONS.includes(action)) {
                    // "未知动作只未记录": no row, no guessing at a nearby label.
                    return refusal(ASK_DECISION_REASON_UNKNOWN_ACTION, known.dp);
                }
                envelope = {
                    meta: known.meta,
                    decision_id: params.decision_id,
                    dp: known.dp,
                    stage: "executed",
                    event_id: eventId,
                    action,
                };
                if (params.result !== undefined)
                    envelope.result = params.result;
                if (params.reason !== undefined)
                    envelope.reason = params.reason;
            }
            else {
                const outcome = params.outcome ?? "";
                if (!DECISION_OUTCOMES.includes(outcome)) {
                    return refusal(ASK_DECISION_REASON_UNKNOWN_ACTION, known.dp);
                }
                envelope = {
                    meta: known.meta,
                    decision_id: params.decision_id,
                    dp: known.dp,
                    stage: "settled",
                    event_id: eventId,
                    outcome,
                };
                if (params.reason !== undefined)
                    envelope.reason = params.reason;
            }
            if (params.task_after !== undefined)
                envelope.task_after = copyTaskState(params.task_after);
            const feedback = await writeDecisionLifecycle(projectDir, envelope, options.lifecycleRunner ?? runLifecycleMw);
            appendDecisionTrace(tracePath, `[DECISION_RECEIPT] ${new Date().toISOString()} dp=${known.dp} stage=${feedback.stage} ` +
                `status=${feedback.status} decision_id=${params.decision_id} role=${initiatorRole}`);
            const details = {
                decision_id: params.decision_id,
                dp: known.dp,
                stage: feedback.stage,
                status: feedback.status,
            };
            return { content: [{ type: "text", text: JSON.stringify(details) }], details };
        },
    });
    // Active-set append (spec §5.3 / design Q5 §5.2): runs after the worker's
    // own before_agent_start recomputation, so every role sees the tools without
    // touching TOOL_ALLOWLISTS. Idempotent — a repeated append is a no-op.
    pi.on("before_agent_start", () => {
        const active = pi.getActiveTools();
        const missing = [ASK_DECISION_TOOL, DECISION_RECEIPT_TOOL].filter((name) => !active.includes(name));
        if (missing.length === 0)
            return;
        pi.setActiveTools([...active, ...missing]);
    });
    return { projectDir, tracePath, counter };
}
//# sourceMappingURL=decision-tool.js.map