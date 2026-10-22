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
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Type } from "typebox";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.js";
import { controlRootFromTaskPath } from "../shared/paths.js";
import { canonicalStateBytes, MAX_STRUCTURED_STATE_BYTES, validateStructuredState } from "./triage-client.js";
/** Registered tool name (referenced by `activeToolsForType` wiring in index.ts). */
export const ASK_DECISION_TOOL = "ask_decision";
/** Hard client-side wall for one `mw decide run` child (design D-017/D-006). */
export const ASK_DECISION_TIMEOUT_MS = 20_000;
/** Same-dp blocks inside one turn before the tool loop is terminated. */
export const ASK_DECISION_MAX_BLOCKED_PER_TURN = 2;
/** The only failure action the model is ever told about (spec §5.1 fail-closed). */
export const ASK_DECISION_BLOCKED_ACTION = "blocked-ask-human";
/** Client-side canonical state budget (spec AC-013 / §5.4). Same number as the
 * structured-input contract, taken from it instead of restated here. */
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
    if (input.taskKey !== undefined && input.taskKey !== "") {
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
const PYTHON_AUTO_FILLED_FIELDS = new Set(["questions_version"]);
/**
 * The refusal list `decide_for` step 5 would produce for `dp` and `state` —
 * field names only (L0), empty when the state is sendable. For dp1/dp2/dp3 the
 * field set is exactly `decision_points._missing_required(build_state(...))`
 * (verified against Python 2026-10-20); the order follows the triage-client
 * validator (universal block, then the dp block).
 *
 * Delegates to `pm/triage-client.ts` (`validateStructuredState`, whose
 * `REQUIRED_FIELDS_BY_DP` is the single structured-input table, D6 Q5.1); for
 * dp1/dp2/dp3 that union is exactly `decision_points.REQUIRED_STATE_FIELDS`,
 * which is why the id set of the gated dps is pinned to the Python source by
 * the suite. Every other dp is not gated on required fields by the registry, so
 * it is never pre-refused here (over-gating would be its own authority drift).
 */
export function missingDecisionStateFields(dp, state) {
    if (!ASK_DECISION_ENFORCED_STATE_DP_IDS.includes(dp))
        return [];
    return validateStructuredState(dp, state).filter((field) => !PYTHON_AUTO_FILLED_FIELDS.has(field));
}
/** Serialise the request envelope (single line; questions come from the
 * registry because `--dp` is always given, design D-027). */
export function buildDecisionRequestJson(state) {
    return JSON.stringify({ state });
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
            stdio: ["ignore", "pipe", "pipe"],
        });
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
/** Build the `python -X utf8 mw.py decide run ...` argv (design D-003: the
 * state rides `--request-file`, argv carries only routing). The caller prepends
 * {@link PYTHON_EXE}; this list is platform-independent on purpose. */
export function buildDecideArgv(mwPy, request, requestFile) {
    return [
        "-X",
        "utf8",
        mwPy,
        "decide",
        "run",
        `--project=${request.projectDir}`,
        "--dp",
        request.dp,
        "--request-file",
        requestFile,
        "--json",
    ];
}
/** Write the request JSON to a private temp dir and return `{dir, file}`. */
function writeRequestFile(input) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-decide-"));
    const file = path.join(dir, "request.json");
    fs.writeFileSync(file, input, { encoding: "utf8", mode: 0o600 });
    return { dir, file };
}
/**
 * The real child: reuse mw-runner's interpreter/path resolution, write the
 * request to a temp file, await the async spawn, always clean the temp file up.
 */
export const runDecideMw = async (request, signal) => {
    const mwPy = findMwPy();
    if (!mwPy)
        return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
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
/** Parse a child's stdout: the whole payload first, then its last non-empty
 * line (mirrors `triage-client.ts:parseJsonPayload`; never throws). */
export function parseDecisionJson(stdout) {
    const candidates = [stdout.trim()];
    const lastLine = stdout.trim().split("\n").at(-1)?.trim();
    if (lastLine !== undefined && lastLine !== candidates[0])
        candidates.push(lastLine);
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
 * Ask one decision point. Never throws: every failure (unregistered dp,
 * structurally incomplete state, missing mw.py, timeout, non-zero exit,
 * unparsable JSON, absent answer) returns the structured unavailable payload
 * plus the fixed directive.
 *
 * It performs no authorization check of its own: `decide_for` owns
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
    const requestJson = buildDecisionRequestJson(state);
    const runner = input.runner ?? runDecideMw;
    const request = {
        projectDir: input.projectDir,
        dp,
        input: requestJson,
        timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
    };
    let raw;
    try {
        raw = await runner(request, input.signal);
    }
    catch {
        return unavailable("upstream-error", dp, true);
    }
    if (raw.timedOut)
        return unavailable("timeout", dp, true);
    if (raw.error !== undefined)
        return unavailable("upstream-error", dp, true);
    if (raw.status !== 0)
        return unavailable("upstream-error", dp, true);
    const response = parseDecisionJson(raw.stdout);
    if (response === undefined)
        return unavailable("bad-response", dp, true);
    const latency = typeof response.latency_ms === "number" ? response.latency_ms : Date.now() - started;
    if (response.available !== true) {
        const rawReason = typeof response.reason === "string" ? response.reason : "";
        const reason = ASK_DECISION_PYTHON_REASONS.has(rawReason) ? rawReason : "upstream-error";
        // The child's own 7-value escalation verdict travels beside (never instead
        // of) the frozen legacy reason (D-021 / D-030).
        const escalated = typeof response.escalated_reason === "string" && response.escalated_reason !== ""
            ? response.escalated_reason
            : undefined;
        return unavailable(reason, dp, true, { escalated_reason: escalated });
    }
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
}, { additionalProperties: false });
/**
 * Register `ask_decision` for the worker branch (design Q1 §1.3/§5.2).
 *
 * Visibility: the tool is registered unconditionally inside the worker
 * activation and then appended to the per-turn active set by a
 * `before_agent_start` handler registered AFTER `workerModeActivate` has
 * installed its own handler, so the append wins over the role allowlist
 * recomputation. It never enters `TOOL_ALLOWLISTS` (T-17 Python parity lock)
 * and is never registered in PM mode.
 */
export function registerAskDecisionTool(pi, options = {}) {
    const taskPath = options.taskPath ?? process.env.PI_WORKER_TASK;
    const resolvedTaskPath = taskPath !== undefined && taskPath !== "" ? path.resolve(taskPath) : undefined;
    const projectDir = options.projectDir ??
        (resolvedTaskPath !== undefined ? controlRootFromTaskPath(resolvedTaskPath) : process.cwd());
    const tracePath = options.tracePath ??
        (resolvedTaskPath !== undefined ? path.join(path.dirname(resolvedTaskPath), "trace.log") : undefined);
    const taskKey = resolvedTaskPath !== undefined ? ownerKeyFromTaskPath(resolvedTaskPath) : undefined;
    const counter = createDecisionBlockCounter();
    // One turn = one retry window: the same dp gets a fresh budget per turn.
    pi.on("turn_start", () => counter.reset());
    pi.registerTool({
        name: ASK_DECISION_TOOL,
        label: ASK_DECISION_TOOL,
        description: "Ask the external decision service for a human-style ruling on a gated decision point. " +
            "Returns ONE line of JSON: {available, decision_id, mode, acted, answers, confidence_source, latency_ms}. " +
            "available=false means UNAVAILABLE: the gated action stays blocked — do NOT guess, do NOT work around it, " +
            'report "blocked on decision <dp>" and stop. The failure line also carries escalated_reason and, for ' +
            "input-incomplete, missing_fields.",
        promptSnippet: "ask_decision(dp, trigger, question?, note?) — ask the decision service before a gated action; " +
            "available=false means blocked, never guess.",
        promptGuidelines: [
            "Call ask_decision ONLY with a dp id from the enum and the trigger_id from your task context " +
                "(<task_key> or <task_key>#ckpt<N>); never invent a dp id, trigger or question id.",
            'available=false is a terminal answer for this attempt: report "blocked on decision <dp>" and wait ' +
                "for a human. Repeating the same call in one turn is cut off by the retry breaker.",
            "unavailable=input-incomplete lists missing_fields: the registry needs them and this tool cannot " +
                "produce them, so do not retry — report the block.",
            "note is an L0/L1 summary (<=600 bytes): no credentials, no user quotes, no absolute paths, no code.",
            "mode=suggest only archives an advisory row; acted is the service's verdict and never your own " +
                "inference from the mode.",
        ],
        parameters: ASK_DECISION_PARAMETERS,
        // Sequential: an ask changes gate state, so it must not race the tools
        // it authorizes (design Q1 §1.1).
        executionMode: "sequential",
        execute: async (_toolCallId, params, signal) => {
            const outcome = await runAskDecision({
                projectDir,
                dp: params.dp,
                trigger: params.trigger,
                question: params.question,
                note: params.note,
                taskKey,
                runner: options.runner,
                timeoutMs: options.timeoutMs,
                signal,
            });
            const iso = new Date().toISOString();
            if (outcome.payload.available) {
                counter.clear(params.dp);
                appendDecisionTrace(tracePath, `[DECISION] ${iso} dp=${params.dp} trigger=${params.trigger} ` +
                    `decision_id=${outcome.payload.decision_id} mode=${outcome.payload.mode} ` +
                    `acted=${String(outcome.payload.acted)} source=${outcome.payload.confidence_source} ` +
                    `latency_ms=${outcome.payload.latency_ms}`);
                return { content: [{ type: "text", text: outcome.text }], details: outcome.payload };
            }
            const reason = outcome.payload.unavailable;
            const escalated = outcome.payload.escalated_reason !== undefined
                ? ` escalated_reason=${outcome.payload.escalated_reason}`
                : "";
            const blocks = counter.recordBlock(params.dp);
            appendDecisionTrace(tracePath, `[DECISION_UNAVAILABLE] ${iso} dp=${params.dp} trigger=${params.trigger} reason=${reason}` +
                `${escalated} count=${blocks} max=${ASK_DECISION_MAX_BLOCKED_PER_TURN}`);
            if (blocks < ASK_DECISION_MAX_BLOCKED_PER_TURN) {
                return { content: [{ type: "text", text: outcome.text }], details: outcome.payload };
            }
            appendDecisionTrace(tracePath, `[DECISION_RETRY_STOP] ${iso} dp=${params.dp} trigger=${params.trigger} reason=${reason} ` +
                `count=${blocks} max=${ASK_DECISION_MAX_BLOCKED_PER_TURN}`);
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
    // Active-set append (spec §5.3 / design Q5 §5.2): runs after the worker's
    // own before_agent_start recomputation, so every role sees the tool without
    // touching TOOL_ALLOWLISTS. Idempotent — a repeated append is a no-op.
    pi.on("before_agent_start", () => {
        const active = pi.getActiveTools();
        if (active.includes(ASK_DECISION_TOOL))
            return;
        pi.setActiveTools([...active, ASK_DECISION_TOOL]);
    });
    return { projectDir, tracePath, counter };
}
//# sourceMappingURL=decision-tool.js.map