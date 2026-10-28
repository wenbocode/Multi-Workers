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
import { type TaskStateSnapshot } from "./decision-task-state.ts";
/** Registered tool name (referenced by `activeToolsForType` wiring in index.ts). */
export declare const ASK_DECISION_TOOL = "ask_decision";
/** The receipt op: the asking agent records what it ACTUALLY did with a
 * selection (`executed`) and when this round of handling is done (`settled`).
 * It never records on the model's return alone (AC-014). */
export declare const DECISION_RECEIPT_TOOL = "decision_receipt";
/** Hard client-side wall for one `mw decide run` child (design D-017/D-006). */
export declare const ASK_DECISION_TIMEOUT_MS = 20000;
/** Same-dp blocks inside one turn before the tool loop is terminated. */
export declare const ASK_DECISION_MAX_BLOCKED_PER_TURN = 2;
/** The only failure action the model is ever told about (spec §5.1 fail-closed). */
export declare const ASK_DECISION_BLOCKED_ACTION = "blocked-ask-human";
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
/** The real initiating role of a decision (lowercase: the vocabulary of the
 * Python lifecycle writer `decision_lifecycle.INITIATOR_ROLES`). The role is
 * structural — taken from the window that registered the tool, never from a
 * model-supplied parameter. */
export type DecisionToolRole = "pm" | "coding" | "research" | "review";
/** `unknown` is the honest role of a worker whose card cannot be read; Python
 * accepts it (`INITIATOR_ROLES`) and it never impersonates the PM. */
export type DecisionInitiatorRole = DecisionToolRole | "unknown";
/** Only the PM may prepare these decisions (design D003/§4.4): a worker that
 * reaches the entry with one of them is refused with ZERO spawn — a model must
 * never borrow the PM's checkpoint or sign-off conclusion. */
export declare const ASK_DECISION_PM_ONLY_DP_IDS: readonly ["dp2-checkpoint-split", "dp25-signoff-conclusion"];
/** The dps whose material is the approved business contract (T01): the caller
 * supplies every field verbatim on the local envelope. Every other dp keeps
 * the legacy L0/L1 state path byte-identical. */
export declare const ASK_DECISION_MATERIAL_DP_IDS: readonly ["dp2-checkpoint-split", "dp3-worker-clarify", "dp25-signoff-conclusion"];
/** dp3 native dynamic-choice protocol (`decision_points.dynamic_choices_value_error`). */
export declare const DP3_ID = "dp3-worker-clarify";
export declare const DP3_HANDLING_MIN_OPTIONS = 2;
export declare const DP3_HANDLING_MAX_OPTIONS = 5;
export declare const DP3_HANDLING_LABEL_MAX = 80;
/** TS-local refusal reasons (never produced by the Python service, D-028). */
export declare const ASK_DECISION_REASON_ROLE_FORBIDDEN = "role-forbidden";
export declare const ASK_DECISION_REASON_UNKNOWN_DECISION = "unknown-decision";
export declare const ASK_DECISION_REASON_UNKNOWN_ACTION = "unknown-action";
/** Record version of the local envelope (design §4.1; T02's
 * `decision_lifecycle.RECORD_VERSION`). The meta never reaches the model. */
export declare const DECISION_RECORD_VERSION = 2;
export type AskDecisionMode = "auto" | "suggest";
/** `answers` is the registry question set echoed by the service: question id →
 * `{value, confidence?}`. Mutable JSON only. */
export type AskDecisionAnswers = Record<string, {
    value: unknown;
    confidence?: number | null;
}>;
/** The native choice resolved back to the candidate the ORIGINAL asker sent.
 * `label`/`description` are present only when this tool holds the candidate
 * list itself (dp3's `handling_options`); dp2/dp25 labels stay in the Python
 * registry and are never re-declared here. */
export interface DecisionSelection {
    question: string;
    id: string;
    label?: string;
    description?: string;
}
/** One feedback fact this consumer actually wrote / failed to write (AC-014). */
export interface DecisionFeedbackResult {
    stage: "consumed" | "executed" | "settled";
    /** The writer's own verdict. `written`/`duplicate` are recorded facts (a
     * duplicate is the SAME event replayed, never a second row); `failed` means
     * the ledger holds no fact for this stage. */
    status: "written" | "duplicate" | "failed";
    /** The writer's `recorded` flag, taken verbatim from its `--json` receipt. */
    recorded: boolean;
    reason?: string;
}
export interface AskDecisionAvailable {
    available: true;
    decision_id: string;
    /** The child's execution mode. Omitted on the dp25 sign path: `decide sign`
     * has no mode verdict, and inventing one here would misreport authority. */
    mode?: AskDecisionMode;
    acted: boolean;
    answers: AskDecisionAnswers;
    confidence_source: string;
    latency_ms: number;
    /** Set on the four-dp material path: the exact candidate the selection names. */
    selection?: DecisionSelection;
    /** Set on the four-dp material path: the automatic `consumed` write result. */
    feedback?: DecisionFeedbackResult;
    /** Set on the dp25 path: the sign CLI's own receipt (one judgment, real
     * sign-off write or a concrete PM/user handoff). */
    signoff?: DecisionSignoffResult;
}
/** The dp25 sign CLI's receipt, mapped 1:1 (no derived success).
 *
 * `status` is the CLI's `signoff_status`: `written`/`existing` mean the
 * `evidence/review/sign-final.md` file really validates for this
 * `logical_id`; `not-required` means continue/user-confirm wrote no file;
 * `failed`/`invalid-existing`/`disabled` are reported as-is. */
export interface DecisionSignoffResult {
    status: "written" | "existing" | "not-required" | "failed" | "invalid-existing" | "disabled";
    path?: string;
    /** Always 0: the one judgment IS the sign-off (no second approval). */
    second_approval: number;
    /** The persisted dp25 result record status (`written`/`existing`/`failed:*`). */
    record_status?: string;
    /** False when the CLI replayed an existing result instead of calling the
     * model (a retry of the same logical id). */
    model_called?: boolean;
    /** The lifecycle feedback aggregate the CLI recorded (`recorded`/`partial`/...). */
    feedback_status?: string;
    feedback_stages?: Array<{
        stage?: string | null;
        status?: string | null;
        event_id?: string | null;
    }>;
    problems?: string[];
    /** continue/user-confirm: the concrete next step for the PM or the user. */
    handoff?: {
        owner?: string;
        kind?: string;
        signoff_writes?: number;
        instruction?: string;
    };
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
    /** The local envelope meta this call minted (material path only). It is the
     * join key of every feedback row and is NEVER handed to the model. */
    meta?: DecisionToolMeta;
}
/** True for the 25 ids the tool exposes (and therefore for every id Python can
 * resolve); the enum itself is pinned to `DP_REGISTRY` by the suite. */
export declare function isRegisteredDp(dp: string): dp is AskDecisionDpId;
/** Code-point-safe UTF-8 truncation (never splits a surrogate pair). */
export declare function truncateUtf8(text: string, maxBytes: number): string;
export interface AskDecisionStateInput {
    dp: string;
    note?: string;
    taskKey?: string | null;
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
 * field names only (L0), empty when the state is sendable.
 *
 * The field list is the GENERATED REGISTRY (`DECIDE_REGISTRY`, from
 * `decision_points.REQUIRED_STATE_FIELDS`), never a second local table: the four
 * DPs moved to the business contract in T01, so the old structured-input table
 * (`triage-client.REQUIRED_FIELDS_BY_DP`) no longer describes them. Identity
 * keys Python fills itself are not the caller's to supply.
 */
export declare function missingDecisionStateFields(dp: string, state: Record<string, unknown>): string[];
/** Serialise the request envelope (single line; questions come from the
 * registry because `--dp` is always given, design D-027). */
export declare function buildDecisionRequestJson(state: Record<string, unknown>): string;
/** One refused material field. `field` is a registry path (dotted for nested
 * facts); the rule is a name, never a value — no material leaks into an
 * error payload (AC-019). */
export interface MaterialIssue {
    field: string;
    rule: string;
}
export type MaterialValidation = {
    ok: true;
    material: Record<string, unknown>;
} | {
    ok: false;
    issues: MaterialIssue[];
};
/** The local envelope metadata (design §4.1). Never part of the material. */
export interface DecisionToolMeta {
    record_version: typeof DECISION_RECORD_VERSION;
    /** One fresh UUID per real decision; every feedback row joins on it. */
    logical_id: string;
    key: string;
    /** The REAL task this decision belongs to, or `null` (a PM decision with no
     * task). Never "the latest task" by inference (AC-010). */
    task_key: string | null;
    initiator_role: DecisionInitiatorRole;
    /** Set only when this decision retries another one (new id, points at前次). */
    retry_of: string | null;
    task_before?: TaskStateSnapshot;
}
/** The stdin payload for `mw decide run <dp> --stdin` (design §4.1). */
export interface DecisionToolEnvelope {
    material: Record<string, unknown>;
    meta: DecisionToolMeta;
}
/** True when `dp` is one the PM alone may prepare (checkpoint / sign-off). */
export declare function isPmOnlyDp(dp: string): boolean;
/** True when `dp` carries the business material contract instead of the legacy
 * L0/L1 `task_summary` state. */
export declare function isMaterialDp(dp: string): boolean;
/** Read the declared business paths of a material object (registry order). */
export declare function missingMaterialPaths(dp: string, material: unknown): string[];
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
export declare function validateDecisionMaterial(dp: string, material: unknown): MaterialValidation;
/** Build the local envelope metadata for ONE new decision.
 *
 * `logical_id` is minted here, so a caller cannot accidentally reuse a previous
 * decision's id; `retry_of` is explicit (a retry mints a new id and points at
 * the previous one). `task_key` stays `null` when the decision has no task.
 */
export declare function buildDecisionToolMeta(input: {
    key: string;
    taskKey?: string | null;
    initiatorRole: DecisionInitiatorRole;
    retryOf?: string | null;
    taskBefore?: TaskStateSnapshot;
}): DecisionToolMeta;
/** Assemble the `{material, meta}` envelope after a last closed-set check. */
export declare function buildDecisionEnvelope(input: {
    dp: string;
    material: Record<string, unknown>;
    meta: DecisionToolMeta;
}): DecisionToolEnvelope;
/** The worker's real initiating role, read from its own card's `type:`.
 *
 * A card that cannot be read, or a type outside coding/research/review, is
 * `unknown` — the tool never upgrades a role to make a PM-only dp callable. */
export declare function initiatorRoleFromWorkerTask(taskPath: string | undefined): DecisionInitiatorRole;
/** Resolve dp3's native `handling` answer to the candidate the asker supplied. */
export declare function resolveHandlingSelection(answers: unknown, options: unknown): DecisionSelection | undefined;
/** The fixed material-preparation prompts handed to the asking agent
 * (design §2 "固定提示"). They are part of the tool contract, not UI copy. */
export declare const DECISION_MATERIAL_PROMPTS: {
    readonly dp3: string;
    readonly dp2: string;
    readonly dp25: string;
};
/** The closed action set of T02's `decision_lifecycle.EXECUTED_ACTIONS`. An
 * action outside it is never recorded ("未知动作只未记录"). */
export declare const DECISION_EXECUTED_ACTIONS: readonly string[];
/** The closed outcome set of T02's `decision_lifecycle.OUTCOMES`. */
export declare const DECISION_OUTCOMES: readonly string[];
/** One lifecycle fact envelope (`mw decide lifecycle --stdin`). */
export interface DecisionLifecycleEnvelope {
    meta: DecisionToolMeta;
    decision_id: string;
    dp: string | null;
    stage: "consumed" | "executed" | "settled";
    event_id: string;
    task_after?: TaskStateSnapshot;
    answer?: string;
    action?: string;
    result?: string;
    outcome?: string;
    reason?: string;
}
/** One lifecycle child invocation (stdin payload included). */
export interface LifecycleRequest {
    projectDir: string;
    input: string;
    timeoutMs: number;
}
/** Injectable lifecycle runner (tests stub this; production spawns the CLI). */
export type LifecycleRunner = (request: LifecycleRequest) => Promise<RawDecideResult>;
/** Hard wall for one feedback child: a feedback write must never stall a tool. */
export declare const DECISION_LIFECYCLE_TIMEOUT_MS = 10000;
/** Build `python -X utf8 mw.py decide lifecycle --stdin --json ...` (T05
 * contract). `--json` makes the writer report its own `recorded`/`status`, so a
 * consumer never infers success from exit code 0 (a `duplicate` replay is a
 * recorded fact too, and the payload says which one it was). */
export declare function buildLifecycleArgv(mwPy: string, projectDir: string): string[];
/** The real feedback child: the payload rides stdin, never argv. */
export declare const runLifecycleMw: LifecycleRunner;
/** The dp25 sign-off conclusion point (the managed PM sign path). */
export declare const DP25_ID = "dp25-signoff-conclusion";
/** The three conclusions T05 accepts (`decision_signoff_result.CONCLUSIONS`). */
export declare const DECISION_SIGNOFF_CONCLUSIONS: readonly string[];
/** One `mw decide sign <key> --stdin --json` invocation. */
export interface SignRequest {
    projectDir: string;
    key: string;
    input: string;
    timeoutMs: number;
}
/** Injectable sign runner (tests stub this; production spawns the CLI). */
export type SignRunner = (request: SignRequest) => Promise<RawDecideResult>;
/** Build `python -X utf8 mw.py decide sign <key> --stdin --json`.
 *
 * `--stdin` selects T05's versioned PM-material path; WITHOUT it the command
 * falls back to the legacy signoff-only auto path, which has no typed material
 * and therefore cannot be this feature's writer. */
export declare function buildSignArgv(mwPy: string, key: string, projectDir: string): string[];
/** The real sign child: the envelope rides stdin, never argv. */
export declare const runSignMw: SignRunner;
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
export declare function writeDecisionLifecycle(projectDir: string, envelope: DecisionLifecycleEnvelope, runner?: LifecycleRunner): Promise<DecisionFeedbackResult>;
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
    /** Payload piped on the child's stdin and then closed (never argv). */
    stdin?: string;
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
    /** Request JSON — piped on stdin (`viaStdin`) or written to a temp file. */
    input: string;
    timeoutMs: number;
    /** True for the four-dp material envelope: `{material, meta}` rides stdin
     * under `mw decide run <dp> --stdin` (design §4.1). The legacy 21 dps keep
     * the pre-existing `--request-file` + `{state}` path byte-identical. */
    viaStdin?: boolean;
}
/** Injectable runner (tests replace this; production uses {@link runDecideMw}). */
export type DecideRunner = (request: DecideRunRequest, signal?: AbortSignal) => Promise<RawDecideResult>;
/** Build the `python -X utf8 mw.py decide run ...` argv.
 *
 * `viaStdin` (the four-dp envelope) carries routing only: the whole
 * `{material, meta}` payload rides stdin. The legacy path keeps riding a temp
 * `--request-file` (design D-003). The caller prepends {@link PYTHON_EXE}; this
 * list is platform-independent on purpose. */
export declare function buildDecideArgv(mwPy: string, request: DecideRunRequest, requestFile?: string): string[];
/**
 * The real child: reuse mw-runner's interpreter/path resolution. The four-dp
 * envelope is piped on stdin (`--stdin`); the legacy path writes the request to
 * a temp file and always cleans it up.
 */
export declare const runDecideMw: DecideRunner;
/** Parse a child's stdout: the whole payload first, then each non-empty line
 * from the last one backwards (a child may print a diagnostic after its JSON
 * receipt). Never throws. */
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
    /** Owner key, carried as `key`/`task_key` in the LEGACY state when known. */
    taskKey?: string | null;
    /** Owning AgenticTask key of the local envelope (material path). */
    key?: string;
    /** The REAL task this decision belongs to; `null` for a task-less PM decision. */
    initiatorRole?: DecisionInitiatorRole;
    /** Business material of the four material dps (dp2/dp3/dp25), verbatim. */
    material?: Record<string, unknown>;
    /** Points at the previous `logical_id` when this call retries another one. */
    retryOf?: string | null;
    taskBefore?: TaskStateSnapshot;
    /** Runner override (tests); the real async child when omitted. */
    runner?: DecideRunner;
    /** Feedback runner override (tests); the real `decide lifecycle` child when omitted. */
    lifecycleRunner?: LifecycleRunner;
    /** dp25 sign runner override (tests); the real `decide sign` child when omitted. */
    signRunner?: SignRunner;
    timeoutMs?: number;
    signal?: AbortSignal;
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
export declare function runAskDecision(input: AskDecisionInput): Promise<AskDecisionOutcome>;
/** Diagnostic for a locally refused call (no child ran). */
export declare function refusalOutcome(reason: string, dp: string, missing?: string[]): AskDecisionOutcome;
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
    /** The registering window's real role: `pm` in the PM branch, the worker's own
     * card type in the worker branch. Defaults to the card's type, else
     * `unknown` (never inferred as the PM). */
    initiatorRole?: DecisionInitiatorRole;
    /** Owning AgenticTask key when the window has no worker task path (PM). */
    key?: string;
    /** The REAL task this window works on (worker); `null`/absent for the PM. */
    taskKey?: string | null;
    /** Runner override (tests). */
    runner?: DecideRunner;
    /** Feedback runner override (tests). */
    lifecycleRunner?: LifecycleRunner;
    /** dp25 sign runner override (tests). */
    signRunner?: SignRunner;
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
    material: Type.TOptional<Type.TObject<{
        task_goal: Type.TOptional<Type.TString>;
        task_requirements: Type.TOptional<Type.TString>;
        task_deliverables: Type.TOptional<Type.TString>;
        pm_decision_background: Type.TOptional<Type.TString>;
        worker_execution: Type.TOptional<Type.TString>;
        question: Type.TOptional<Type.TString>;
        background: Type.TOptional<Type.TObject<{
            task_goal: Type.TOptional<Type.TString>;
            current_state: Type.TOptional<Type.TString>;
            decision_reason: Type.TOptional<Type.TString>;
            constraints_impact: Type.TOptional<Type.TString>;
        }>>;
        handling_options: Type.TOptional<Type.TArray<Type.TObject<{
            id: Type.TString;
            label: Type.TString;
            description: Type.TString;
        }>>>;
        delivery_goal: Type.TOptional<Type.TString>;
        actual_completion: Type.TOptional<Type.TString>;
        verification_evidence: Type.TOptional<Type.TObject<{
            verified: Type.TOptional<Type.TArray<Type.TString>>;
            unverified: Type.TOptional<Type.TArray<Type.TString>>;
        }>>;
        unfinished_impact: Type.TOptional<Type.TArray<Type.TString>>;
    }>>;
    key: Type.TOptional<Type.TString>;
    task_before: Type.TOptional<Type.TObject<{
        status: Type.TUnion<TLiteral<"done" | "failed" | "lost" | "needs-clarification" | "not-queued" | "pending" | "running" | "unknown">[]>;
        source: TLiteral<"agent-report">;
        observed_at: Type.TString;
        completed: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
        remaining: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
        blockers: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
    }>>;
    task_key: Type.TOptional<Type.TString>;
}>;
/** Receipt parameters: the ONLY way `executed`/`settled` are ever recorded. */
export declare const DECISION_RECEIPT_PARAMETERS: Type.TObject<{
    decision_id: Type.TString;
    stage: Type.TUnion<[TLiteral<"executed">, TLiteral<"settled">]>;
    action: Type.TOptional<Type.TString>;
    result: Type.TOptional<Type.TString>;
    outcome: Type.TOptional<Type.TString>;
    reason: Type.TOptional<Type.TString>;
    event_id: Type.TOptional<Type.TString>;
    task_after: Type.TOptional<Type.TObject<{
        status: Type.TUnion<TLiteral<"done" | "failed" | "lost" | "needs-clarification" | "not-queued" | "pending" | "running" | "unknown">[]>;
        source: TLiteral<"agent-report">;
        observed_at: Type.TString;
        completed: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
        remaining: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
        blockers: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
    }>>;
}>;
/** Receipt tool details: the outcome of ONE receipt attempt. */
export interface DecisionReceiptDetails {
    decision_id: string;
    dp: string | null;
    stage: string;
    status: DecisionFeedbackResult["status"] | "refused";
    unavailable?: string;
}
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
export declare function registerAskDecisionTool(pi: ExtensionAPI, options?: AskDecisionToolOptions): AskDecisionToolHandle;
export {};
//# sourceMappingURL=decision-tool.d.ts.map