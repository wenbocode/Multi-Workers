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
import { type TLiteral, Type } from "typebox";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
/** Registered tool name (referenced by `activeToolsForType` wiring in index.ts). */
export declare const ASK_DECISION_TOOL = "ask_decision";
/** Hard client-side wall for one `mw decide run` child (design D-017/D-006). */
export declare const ASK_DECISION_TIMEOUT_MS = 20000;
/** Same-dp blocks inside one turn before the tool loop is terminated. */
export declare const ASK_DECISION_MAX_BLOCKED_PER_TURN = 2;
/** The only failure action the model is ever told about (spec §5.1 fail-closed). */
export declare const ASK_DECISION_BLOCKED_ACTION = "blocked-ask-human";
/** Client-side canonical state budget (spec AC-013 / §5.4). Same number as the
 * structured-input contract, taken from it instead of restated here. */
export declare const ASK_DECISION_MAX_STATE_BYTES = 2000;
/**
 * The 25 decision-point ids, copied verbatim from
 * `packages/multi-workers/decision_points.py:DP_REGISTRY` (the authority). The
 * suite asserts both the id set and the tier map against that file, so a
 * drift shows up as a red test, not as a silently unregistered call.
 */
export declare const ASK_DECISION_DP_IDS: readonly ["dp1-dispatch-type", "dp2-checkpoint-split", "dp3-worker-clarify", "dp4-failure-handling", "dp5-test-triage", "dp6-qg-verdict", "dp7-gate-failure", "dp8-scope-change", "dp9-model-select", "dp10-dependency", "dp11-credential", "dp12-destructive", "dp13-commit-release", "dp14-rule-conflict", "dp15-autopilot-gate", "dp16-goal", "dp17-spec-lock", "dp18-claim", "dp19-foreign-write", "dp20-stage-close", "dp21-refine", "dp22-debug-plan", "dp23-snapshot", "dp24-pi-trust", "dp25-signoff-conclusion"];
export type AskDecisionDpId = (typeof ASK_DECISION_DP_IDS)[number];
/** Registry ids whose `decide_for` step 5 enforces `REQUIRED_STATE_FIELDS`
 * (`packages/multi-workers/decision_points.py:626`). Only these dps may be
 * refused client-side on a missing field: every other dp requires nothing
 * beyond the state builder's `v`/`dp`/`questions_version`, so pre-gating it
 * here would over-gate a call the authority accepts. The id set is pinned to
 * the Python source by `decision-tool.test.ts`; the **field** names themselves
 * come from `pm/triage-client.ts` and are never copied. */
export declare const ASK_DECISION_ENFORCED_STATE_DP_IDS: readonly ["dp1-dispatch-type", "dp2-checkpoint-split", "dp3-worker-clarify", "dp25-signoff-conclusion"];
/** Frozen transport reasons (`decision.py:REASON_CODES`). A reason outside this
 * set is normalised to `upstream-error` exactly like `decision.py` does. */
export declare const ASK_DECISION_PYTHON_REASONS: ReadonlySet<string>;
/** TS-local refusal reasons (never produced by the Python service; the T-04
 * precedent D-028 keeps them distinct from the frozen 8-value set). */
export declare const ASK_DECISION_REASON_INPUT_INCOMPLETE = "input-incomplete";
export declare const ASK_DECISION_REASON_INPUT_OVERSIZE = "input-oversize";
/** Fixed phrase every unavailable payload carries (spec AC-005: no default
 * action, no guessing). */
export declare const ASK_DECISION_GUESS_DIRECTIVE = "\u4E0D\u8981\u81EA\u884C\u731C\u6D4B";
export type AskDecisionMode = "auto" | "suggest";
/** `answers` is the registry question set echoed by the service: question id →
 * `{value, confidence?}`. Mutable JSON only. */
export type AskDecisionAnswers = Record<string, {
    value: unknown;
    confidence?: number | null;
}>;
export interface AskDecisionAvailable {
    available: true;
    decision_id: string;
    mode: AskDecisionMode;
    acted: boolean;
    answers: AskDecisionAnswers;
    confidence_source: string;
    latency_ms: number;
}
export interface AskDecisionUnavailable {
    available: false;
    unavailable: string;
    action: typeof ASK_DECISION_BLOCKED_ACTION;
    /** The child's own escalation verdict (`decision_points.ESCALATED_REASONS`,
     * 7 values) passed through verbatim. `unavailable` keeps the frozen legacy
     * transport vocabulary; the two coexist, neither is folded into the other
     * (D-021 / `_DECIDE_RUN_REASON_MAP`). */
    escalated_reason?: string;
    /** State fields the registry requires and this call site could not supply
     * (names only, L0). Only present on a zero-spawn `input-incomplete` refusal. */
    missing_fields?: string[];
}
export type AskDecisionPayload = AskDecisionAvailable | AskDecisionUnavailable;
/** Result of one tool attempt: the payload plus the exact text handed back. */
export interface AskDecisionOutcome {
    payload: AskDecisionPayload;
    /** Single-line JSON, plus the fixed directive line when unavailable. */
    text: string;
    /** False means the tool refused before any spawn (unregistered dp /
     * structurally incomplete state). Never a local authorization verdict. */
    spawned: boolean;
}
/** True for the 25 ids the tool exposes (and therefore for every id Python can
 * resolve); the enum itself is pinned to `DP_REGISTRY` by the suite. */
export declare function isRegisteredDp(dp: string): dp is AskDecisionDpId;
/** Code-point-safe UTF-8 truncation (never splits a surrogate pair). */
export declare function truncateUtf8(text: string, maxBytes: number): string;
export interface AskDecisionStateInput {
    dp: string;
    note?: string;
    taskKey?: string;
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
export declare function buildDecisionState(input: AskDecisionStateInput): Record<string, unknown>;
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
export declare function missingDecisionStateFields(dp: string, state: Record<string, unknown>): string[];
/** Serialise the request envelope (single line; questions come from the
 * registry because `--dp` is always given, design D-027). */
export declare function buildDecisionRequestJson(state: Record<string, unknown>): string;
export interface RawDecideResult {
    status: number | null;
    stdout: string;
    stderr: string;
    /** Spawn-level failure text (missing mw.py, ENOENT, aborted, ...). */
    error?: string;
    timedOut: boolean;
}
export interface SpawnWithTimeoutOptions {
    timeoutMs?: number;
    signal?: AbortSignal;
}
/**
 * Spawn `argv` (no shell) and race it against a hard wall-clock timeout.
 *
 * `timedOut:true` means the child was killed after `timeoutMs`. The promise
 * settles on `close` (stdio drained); a killed child that never emits `close`
 * is force-resolved after a short grace so a tool call can never hang.
 */
export declare function spawnWithTimeout(argv: string[], options?: SpawnWithTimeoutOptions): Promise<RawDecideResult>;
export interface DecideRunRequest {
    projectDir: string;
    dp: string;
    /** Request JSON (state envelope) — written to a temp file, never argv. */
    input: string;
    timeoutMs: number;
}
/** Injectable runner (tests replace this; production uses {@link runDecideMw}). */
export type DecideRunner = (request: DecideRunRequest, signal?: AbortSignal) => Promise<RawDecideResult>;
/** Build the `python -X utf8 mw.py decide run ...` argv (design D-003: the
 * state rides `--request-file`, argv carries only routing). The caller prepends
 * {@link PYTHON_EXE}; this list is platform-independent on purpose. */
export declare function buildDecideArgv(mwPy: string, request: DecideRunRequest, requestFile: string): string[];
/**
 * The real child: reuse mw-runner's interpreter/path resolution, write the
 * request to a temp file, await the async spawn, always clean the temp file up.
 */
export declare const runDecideMw: DecideRunner;
/** Parse a child's stdout: the whole payload first, then its last non-empty
 * line (mirrors `triage-client.ts:parseJsonPayload`; never throws). */
export declare function parseDecisionJson(stdout: string): Record<string, unknown> | undefined;
/** The fixed no-guessing line appended to every unavailable payload. */
export declare function unavailableDirective(reason: string, dp: string): string;
/** Terminal directive emitted once a dp hits the per-turn block cap. */
export declare function terminalDirective(dp: string, blocks: number): string;
export interface AskDecisionInput {
    projectDir: string;
    dp: string;
    /** Audit label for the trace line only; the decision id comes from Python. */
    trigger: string;
    question?: string;
    note?: string;
    /** Owner key, carried as `key`/`task_key` in the state when known. */
    taskKey?: string;
    /** Runner override (tests); the real async child when omitted. */
    runner?: DecideRunner;
    timeoutMs?: number;
    signal?: AbortSignal;
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
export declare function runAskDecision(input: AskDecisionInput): Promise<AskDecisionOutcome>;
export interface DecisionBlockCounter {
    /** Start a new turn: every per-dp count returns to zero. */
    reset(): void;
    /** Count one blocked attempt for `dp`; returns the new count. */
    recordBlock(dp: string): number;
    /** Drop the count for `dp` (a successful answer resolves the block). */
    clear(dp: string): void;
    countFor(dp: string): number;
}
/** Per-dp, per-turn block counter (design Q3 §3.3). One instance per worker
 * window; `turn_start` calls {@link DecisionBlockCounter.reset}. */
export declare function createDecisionBlockCounter(): DecisionBlockCounter;
export interface AskDecisionToolOptions {
    /** Control workspace root (`.agenticdoc`'s parent). Defaults to the root
     * derived from `PI_WORKER_TASK`, else `process.cwd()`. */
    projectDir?: string;
    /** Worker task.md path (`PI_WORKER_TASK`); anchors trace.log + the key. */
    taskPath?: string;
    /** Explicit trace.log path (tests). */
    tracePath?: string;
    /** Runner override (tests). */
    runner?: DecideRunner;
    /** Timeout override (tests); production is {@link ASK_DECISION_TIMEOUT_MS}. */
    timeoutMs?: number;
}
export interface AskDecisionToolHandle {
    projectDir: string;
    tracePath?: string;
    counter: DecisionBlockCounter;
}
/** DP enum schema. A tuple cast keeps `Static` at the literal union — a plain
 * mapped array widens to `TSchema[]` and `Static` would collapse to `never`. */
type AskDecisionDpLiteral = TLiteral<AskDecisionDpId>;
/** Tool parameter schema (exported so tests can assert the dp enum surface). */
export declare const ASK_DECISION_PARAMETERS: Type.TObject<{
    dp: Type.TUnion<[AskDecisionDpLiteral, ...AskDecisionDpLiteral[]]>;
    trigger: Type.TString;
    question: Type.TOptional<Type.TString>;
    note: Type.TOptional<Type.TString>;
}>;
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
export declare function registerAskDecisionTool(pi: ExtensionAPI, options?: AskDecisionToolOptions): AskDecisionToolHandle;
export {};
//# sourceMappingURL=decision-tool.d.ts.map