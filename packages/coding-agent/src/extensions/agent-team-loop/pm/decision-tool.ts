/** Registered PM/worker decision tools. One stdin envelope carries business
 * material, the independently prepared basis catalog, optional context and local
 * identity. Only the generated active entries and the registering window's role
 * can reach the service. A valid reply records consumption. Explicit receipts
 * describe subsequent actions. Signing uses its single dedicated writer. */

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { type TLiteral, Type } from "typebox";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import {
	claimedPmKey,
	type DecisionPreparation,
	decisionActorAllowed,
	decisionIdRefusal,
	type PreparedBasis,
	selectedDecisionBasis,
	validateDecisionMaterial,
} from "../shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.ts";
export { validateDecisionMaterial };
export type { MaterialIssue, MaterialValidation } from "../shared/decide-policy.ts";

import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.ts";
import { controlRootFromTaskPath } from "../shared/paths.ts";
import { readTaskType } from "../shared/task-frontmatter.ts";
import {
	AGENT_TASK_STATE_SCHEMA,
	copyTaskState,
	isTaskStateSnapshot,
	type TaskStateSnapshot,
} from "./decision-task-state.ts";
import {
	canonicalStateBytes,
	MAX_STRUCTURED_STATE_BYTES,
	prepareDecisionEnvelope,
	validateStructuredState,
} from "./triage-client.ts";

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

/** IDs and per-entry eligibility follow the generated Python contracts. */
export const ASK_DECISION_DP_IDS = Object.keys(DECIDE_REGISTRY);
export type AskDecisionDpId = string;
export const ASK_DECISION_ENFORCED_STATE_DP_IDS = ASK_DECISION_DP_IDS;

/** Frozen transport reasons (`decision.py:REASON_CODES`). A reason outside this
 * set is normalised to `upstream-error` exactly like `decision.py` does. */
export const ASK_DECISION_PYTHON_REASONS: ReadonlySet<string> = new Set([
	"disabled",
	"entry-unavailable",
	"timeout",
	"rate-limited",
	"upstream-error",
	"bad-response",
	"unsupported-question-type",
	"budget-exhausted",
	"input-incomplete",
	"input-oversize",
	"role-forbidden",
	"retired",
	"unknown-dp",
]);

/** TS-local refusal reasons (never produced by the Python service; the T-04
 * precedent D-028 keeps them distinct from the frozen 8-value set). */
export const ASK_DECISION_REASON_INPUT_INCOMPLETE = "input-incomplete";
export const ASK_DECISION_REASON_INPUT_OVERSIZE = "input-oversize";

/** Fixed phrase every unavailable payload carries (spec AC-005: no default
 * action, no guessing). */
export const ASK_DECISION_GUESS_DIRECTIVE = "不要自行猜测";

// ── Roles and per-dp permissions (AC-006 / AC-010) ──────────────────────────

/** The real initiating role of a decision (lowercase: the vocabulary of the
 * Python lifecycle writer `decision_lifecycle.INITIATOR_ROLES`). The role is
 * structural — taken from the window that registered the tool, never from a
 * model-supplied parameter. */
export type DecisionToolRole = "pm" | "coding" | "research" | "review";

/** `unknown` is the honest role of a worker whose card cannot be read; Python
 * accepts it (`INITIATOR_ROLES`) and it never impersonates the PM. */
export type DecisionInitiatorRole = DecisionToolRole | "unknown";

export const ASK_DECISION_PM_ONLY_DP_IDS = ASK_DECISION_DP_IDS.filter((dp) => DECIDE_REGISTRY[dp].roleScope === "pm");
export const ASK_DECISION_MATERIAL_DP_IDS = ASK_DECISION_DP_IDS;

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

// ── Payload shapes ──────────────────────────────────────────────────────────

export type AskDecisionMode = "auto" | "suggest";

/** `answers` is the registry question set echoed by the service: question id →
 * `{value, confidence?}`. Mutable JSON only. */
export type AskDecisionAnswers = Record<string, { value: unknown; confidence?: number | null }>;

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
	/** Set on the prepared material path: the exact candidate the selection names. */
	selection?: DecisionSelection;
	basis?: PreparedBasis;
	/** Set on the prepared material path: the automatic `consumed` write result. */
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
	feedback_stages?: Array<{ stage?: string | null; status?: string | null; event_id?: string | null }>;
	problems?: string[];
	/** continue/user-confirm: the concrete next step for the PM or the user. */
	handoff?: { owner?: string; kind?: string; signoff_writes?: number; instruction?: string };
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

// ── Structured state: per-dp required fields (single source: triage-client) ──

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** True for the active IDs the tool exposes (and therefore for every id Python can
 * resolve); the enum itself is pinned to `DP_REGISTRY` by the suite. */
export function isRegisteredDp(dp: string): dp is AskDecisionDpId {
	return (ASK_DECISION_DP_IDS as readonly string[]).includes(dp);
}

// ── Request envelope ────────────────────────────────────────────────────────

/** Code-point-safe UTF-8 truncation (never splits a surrogate pair). */
export function truncateUtf8(text: string, maxBytes: number): string {
	if (Buffer.byteLength(text, "utf8") <= maxBytes) return text;
	let out = "";
	let used = 0;
	for (const char of text) {
		const size = Buffer.byteLength(char, "utf8");
		if (used + size > maxBytes) break;
		out += char;
		used += size;
	}
	return out;
}

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
export function buildDecisionState(input: AskDecisionStateInput): Record<string, unknown> {
	const state: Record<string, unknown> = { schema_version: 2, decision_point: input.dp };
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
const PYTHON_AUTO_FILLED_FIELDS: ReadonlySet<string> = new Set([
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
export function missingDecisionStateFields(dp: string, state: Record<string, unknown>): string[] {
	if (!isMaterialStateDp(dp)) {
		// The other 21 dps keep the pre-existing structured-input table (their
		// contract did not change in T01); over-gating them here would narrow a
		// call Python already accepts.
		if (!(ASK_DECISION_ENFORCED_STATE_DP_IDS as readonly string[]).includes(dp)) return [];
		return validateStructuredState(dp, state).filter((field) => !PYTHON_AUTO_FILLED_FIELDS.has(field));
	}
	const entry = DECIDE_REGISTRY[dp];
	if (entry === undefined) return [];
	const missing: string[] = [];
	for (const field of entry.requiredStateFields) {
		if (PYTHON_AUTO_FILLED_FIELDS.has(field.name)) continue;
		const value = readMaterialPath(state, field.name);
		if (value === undefined || value === null) missing.push(field.name);
		else if (field.type === "string" && (typeof value !== "string" || value.trim() === "")) {
			missing.push(field.name);
		}
	}
	return missing;
}

/** Serialise the request envelope (single line; questions come from the
 * registry because `--dp` is always given, design D-027). */
export function buildDecisionRequestJson(state: Record<string, unknown>): string {
	return JSON.stringify({ state });
}

// ── Business material: dp2 / dp3 / dp25 (design §2, T01 registry) ────────────

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
	parent_decision_ref?: string;
	preparation: DecisionPreparation;
	context?: Record<string, unknown>;
	material: Record<string, unknown>;
	meta: DecisionToolMeta;
}

/** True when `dp` is one the PM alone may prepare (checkpoint / sign-off). */
export function isPmOnlyDp(dp: string): boolean {
	return (ASK_DECISION_PM_ONLY_DP_IDS as readonly string[]).includes(dp);
}

/** True when `dp` carries the business material contract instead of the legacy
 * L0/L1 `task_summary` state. */
export function isMaterialDp(dp: string): boolean {
	return (ASK_DECISION_MATERIAL_DP_IDS as readonly string[]).includes(dp);
}

/** The dps whose field contract T01 replaced with the four-dp business schema:
 * the three workers' material dps plus dp1 (the PM dispatch producer, whose
 * material belongs to T03 but whose required fields are the same registry). */
function isMaterialStateDp(dp: string): boolean {
	return isMaterialDp(dp);
}

/** Look one registry path (dotted) up in a material/state object. */
function readMaterialPath(source: unknown, dotted: string): unknown {
	let current: unknown = source;
	for (const segment of dotted.split(".")) {
		if (!isRecord(current)) return undefined;
		current = current[segment];
	}
	return current;
}

/** Read the declared business paths of a material object (registry order). */
export function missingMaterialPaths(dp: string, material: unknown): string[] {
	const entry = DECIDE_REGISTRY[dp];
	if (entry === undefined) return ["dp"];
	const missing: string[] = [];
	for (const field of entry.requiredStateFields) {
		if (readMaterialPath(material, field.name) === undefined) missing.push(field.name);
	}
	return missing;
}

/** Build the local envelope metadata for ONE new decision.
 *
 * `logical_id` is minted here, so a caller cannot accidentally reuse a previous
 * decision's id; `retry_of` is explicit (a retry mints a new id and points at
 * the previous one). `task_key` stays `null` when the decision has no task.
 */
export function buildDecisionToolMeta(input: {
	key: string;
	taskKey?: string | null;
	initiatorRole: DecisionInitiatorRole;
	retryOf?: string | null;
	taskBefore?: TaskStateSnapshot;
}): DecisionToolMeta {
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
export function buildDecisionEnvelope(input: {
	dp: string;
	material: Record<string, unknown>;
	meta: DecisionToolMeta;
	/** Local reference supplied by the host consuming a prepared follow-up. */
	parentDecisionRef?: string;
	preparation?: DecisionPreparation;
	context?: Record<string, unknown>;
}): DecisionToolEnvelope {
	const prepared = prepareDecisionEnvelope(
		input.dp,
		input.material,
		input.meta,
		0,
		input.preparation,
		input.context,
		input.parentDecisionRef,
	);
	if (!prepared.ok) throw new Error(`invalid decision envelope: ${prepared.reason} ${prepared.missing.join(", ")}`);
	return prepared.envelope;
}

/** The worker's real lifecycle role, read from its own card's `type:`.
 *
 * Framework types follow the approved Python `_FRAMEWORK_CARD_ROLES` mapping,
 * not the model-role buckets or the four-choice dispatch menu. Unknown, retired
 * and PM card types stay unknown; a caller option cannot upgrade the card. */
export function initiatorRoleFromWorkerTask(taskPath: string | undefined): DecisionInitiatorRole {
	if (taskPath === undefined || taskPath === "") return "unknown";
	let text: string;
	try {
		text = fs.readFileSync(taskPath, "utf8");
	} catch {
		return "unknown";
	}
	const type = readTaskType(text).type;
	switch (type) {
		case "coding":
		case "vision":
		case "repair":
		case "roadmap-writer":
		case "phase-writer":
			return "coding";
		case "research":
		case "verifier":
		case "reviewer":
		case "rag-research":
		case "decide_prepare":
			return "research";
		case "review":
			return "review";
		default:
			return "unknown";
	}
}

/** Resolve dp3's native `handling` answer to the candidate the asker supplied. */
export function resolveHandlingSelection(answers: unknown, options: unknown): DecisionSelection | undefined {
	if (!isRecord(answers) || !Array.isArray(options)) return undefined;
	const entry = answers.handling;
	const value = isRecord(entry) ? entry.value : undefined;
	if (typeof value !== "string" || value === "") return undefined;
	for (const raw of options) {
		if (!isRecord(raw) || raw.id !== value) continue;
		const label = typeof raw.label === "string" ? raw.label : undefined;
		const description = typeof raw.description === "string" ? raw.description : undefined;
		return { question: "handling", id: value, label, description };
	}
	return undefined;
}

/** The selection a four-dp answer names, or `undefined` when the child answered
 * a question set this contract no longer owns. */
function buildSelection(
	dp: string,
	answers: AskDecisionAnswers,
	material: Record<string, unknown>,
): DecisionSelection | undefined {
	if (DECIDE_REGISTRY[dp].kind === "dynamic-candidates")
		return resolveHandlingSelection(answers, material.handling_options);
	const question = DECIDE_REGISTRY[dp].businessQuestionId;
	if (question === undefined) return undefined;
	const value = answers[question]?.value;
	if (typeof value !== "string" || value.trim() === "") return undefined;
	return { question, id: value };
}

/** The fixed material-preparation prompts handed to the asking agent
 * (design §2 "固定提示"). They are part of the tool contract, not UI copy. */
export const DECISION_MATERIAL_PROMPTS = Object.fromEntries(
	Object.entries(DECIDE_REGISTRY).map(([id, entry]) => [
		id,
		`${id} (${entry.roleScope}): ${[...entry.requiredStateFields, ...entry.optionalStateFields].map((field) => `${field.name} — ${field.description}`).join("; ")}`,
	]),
);

// ── Feedback: `mw decide lifecycle --stdin` (T02 writer, AC-014) ─────────────

/** The closed action set of T02's `decision_lifecycle.EXECUTED_ACTIONS`. An
 * action outside it is never recorded ("未知动作只未记录"). */
export const DECISION_EXECUTED_ACTIONS: readonly string[] = [
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
export const DECISION_OUTCOMES: readonly string[] = ["pending", "ok", "rework", "rollback", "inconclusive"];

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
export const DECISION_LIFECYCLE_TIMEOUT_MS = 10_000;

/** Build `python -X utf8 mw.py decide lifecycle --stdin --json ...` (T05
 * contract). `--json` makes the writer report its own `recorded`/`status`, so a
 * consumer never infers success from exit code 0 (a `duplicate` replay is a
 * recorded fact too, and the payload says which one it was). */
export function buildLifecycleArgv(mwPy: string, projectDir: string): string[] {
	return ["-X", "utf8", mwPy, "decide", "lifecycle", `--project=${projectDir}`, "--stdin", "--json"];
}

/** The real feedback child: the payload rides stdin, never argv. */
export const runLifecycleMw: LifecycleRunner = async (request) => {
	const mwPy = findMwPy();
	if (!mwPy) return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
	return spawnWithTimeout([PYTHON_EXE, ...buildLifecycleArgv(mwPy, request.projectDir)], {
		timeoutMs: request.timeoutMs,
		stdin: request.input,
	});
};

// ── dp25: one judgment that really signs (T05 `decide sign --stdin`) ────────

/** The dp25 sign-off conclusion point (the managed PM sign path). */
export const DP25_ID = "dp25-signoff-conclusion";
export const SIGN_KEY_ID = "dp-sign-key";

/** The three conclusions T05 accepts (`decision_signoff_result.CONCLUSIONS`). */
export const DECISION_SIGNOFF_CONCLUSIONS: readonly string[] = ["finalize", "continue", "user-confirm"];

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
export function buildSignArgv(mwPy: string, key: string, projectDir: string): string[] {
	return ["-X", "utf8", mwPy, "decide", "sign", key, `--project=${projectDir}`, "--stdin", "--json"];
}

/** The real sign child: the envelope rides stdin, never argv. */
export const runSignMw: SignRunner = async (request) => {
	const mwPy = findMwPy();
	if (!mwPy) return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
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
export async function writeDecisionLifecycle(
	projectDir: string,
	envelope: DecisionLifecycleEnvelope,
	runner: LifecycleRunner = runLifecycleMw,
): Promise<DecisionFeedbackResult> {
	const stage = envelope.stage;
	try {
		const raw = await runner({
			projectDir,
			input: JSON.stringify(envelope),
			timeoutMs: DECISION_LIFECYCLE_TIMEOUT_MS,
		});
		if (raw.timedOut) return { stage, status: "failed", recorded: false, reason: "timeout" };
		if (raw.error !== undefined) return { stage, status: "failed", recorded: false, reason: "unavailable" };
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
	} catch {
		return { stage, status: "failed", recorded: false, reason: "runner-threw" };
	}
}

// ── Async spawn with a hard wall ────────────────────────────────────────────

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

/** Cap on captured child output so a runaway child cannot exhaust memory. */
const MAX_CHILD_OUTPUT_BYTES = 1_048_576;

/**
 * Spawn `argv` (no shell) and race it against a hard wall-clock timeout.
 *
 * `timedOut:true` means the child was killed after `timeoutMs`. The promise
 * settles on `close` (stdio drained); a killed child that never emits `close`
 * is force-resolved after a short grace so a tool call can never hang.
 */
export function spawnWithTimeout(argv: string[], options: SpawnWithTimeoutOptions = {}): Promise<RawDecideResult> {
	const timeoutMs = options.timeoutMs ?? ASK_DECISION_TIMEOUT_MS;
	return new Promise<RawDecideResult>((resolve) => {
		let settled = false;
		let stdout = "";
		let stderr = "";
		let timedOut = false;
		let spawnError: string | undefined;
		let wallTimer: NodeJS.Timeout | undefined;
		let graceTimer: NodeJS.Timeout | undefined;

		const finish = (status: number | null): void => {
			if (settled) return;
			settled = true;
			if (wallTimer !== undefined) clearTimeout(wallTimer);
			if (graceTimer !== undefined) clearTimeout(graceTimer);
			options.signal?.removeEventListener("abort", onAbort);
			const result: RawDecideResult = { status, stdout, stderr, timedOut };
			if (spawnError !== undefined) result.error = spawnError;
			resolve(result);
		};

		const append = (current: string, chunk: string): string => {
			if (Buffer.byteLength(current, "utf8") >= MAX_CHILD_OUTPUT_BYTES) return current;
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

		const kill = (): void => {
			try {
				// SIGKILL maps to TerminateProcess on Windows; no grandchildren are
				// left behind by `mw decide run` (it is a single Python process).
				child.kill("SIGKILL");
			} catch {
				// Already gone — `close` will settle the promise.
			}
			// A process killed mid-write may hold stdio open; never hang the tool.
			graceTimer = setTimeout(() => finish(child.exitCode), 2_000);
		};
		const onAbort = (): void => {
			if (settled) return;
			spawnError = "aborted";
			kill();
		};

		child.stdout?.setEncoding("utf8");
		child.stderr?.setEncoding("utf8");
		child.stdout?.on("data", (chunk: string) => {
			stdout = append(stdout, chunk);
		});
		child.stderr?.on("data", (chunk: string) => {
			stderr = append(stderr, chunk);
		});
		child.on("error", (err: Error) => {
			spawnError = err.message;
			finish(null);
		});
		child.on("close", (code: number | null) => finish(code));

		if (options.signal !== undefined) {
			if (options.signal.aborted) onAbort();
			else options.signal.addEventListener("abort", onAbort, { once: true });
		}
		wallTimer = setTimeout(() => {
			if (settled) return;
			timedOut = true;
			kill();
		}, timeoutMs);
	});
}

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
export function buildDecideArgv(mwPy: string, request: DecideRunRequest, requestFile?: string): string[] {
	const routing = ["-X", "utf8", mwPy, "decide", "run", `--project=${request.projectDir}`, "--dp", request.dp];
	if (request.viaStdin === true) return [...routing, "--stdin", "--json"];
	return [...routing, "--request-file", requestFile ?? "", "--json"];
}

/** Write the request JSON to a private temp dir and return `{dir, file}`. */
function writeRequestFile(input: string): { dir: string; file: string } {
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
export const runDecideMw: DecideRunner = async (request, signal) => {
	const refused = decisionIdRefusal(request.dp);
	if (refused || !request.viaStdin)
		return { status: 2, stdout: "", stderr: refused ?? "preparation required", timedOut: false };
	const mwPy = findMwPy();
	if (!mwPy) return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
	if (request.viaStdin === true) {
		return spawnWithTimeout([PYTHON_EXE, ...buildDecideArgv(mwPy, request)], {
			timeoutMs: request.timeoutMs,
			signal,
			stdin: request.input,
		});
	}
	let files: { dir: string; file: string };
	try {
		files = writeRequestFile(request.input);
	} catch (err) {
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
	} finally {
		try {
			fs.rmSync(files.dir, { recursive: true, force: true });
		} catch {
			// Best effort: a leaked temp dir is not worth failing the tool call.
		}
	}
};

// ── Response mapping ────────────────────────────────────────────────────────

function asAnswers(value: unknown): AskDecisionAnswers | undefined {
	if (!isRecord(value)) return undefined;
	const answers: AskDecisionAnswers = {};
	for (const [qid, raw] of Object.entries(value)) {
		if (!isRecord(raw) || !("value" in raw)) continue;
		const entry: { value: unknown; confidence?: number | null } = { value: raw.value };
		if (typeof raw.confidence === "number" && Number.isFinite(raw.confidence)) entry.confidence = raw.confidence;
		answers[qid] = entry;
	}
	return Object.keys(answers).length > 0 ? answers : undefined;
}

/** Parse a child's stdout: the whole payload first, then each non-empty line
 * from the last one backwards (a child may print a diagnostic after its JSON
 * receipt). Never throws. */
export function parseDecisionJson(stdout: string): Record<string, unknown> | undefined {
	const trimmed = stdout.trim();
	const lines = trimmed.split("\n");
	const candidates = [trimmed, ...[...lines].reverse().map((line) => line.trim())];
	for (const text of candidates) {
		if (!text) continue;
		try {
			const parsed = JSON.parse(text) as unknown;
			if (isRecord(parsed)) return parsed;
		} catch {
			// Try the next candidate.
		}
	}
	return undefined;
}

/** The fixed no-guessing line appended to every unavailable payload. */
export function unavailableDirective(reason: string, dp: string): string {
	const base =
		`UNAVAILABLE(${reason}) — ${ASK_DECISION_GUESS_DIRECTIVE}，不要执行被门控的动作，` +
		`不要用别的工具绕过，也不要重复问同一个问题。上报 "blocked on decision ${dp}" 并等待人工裁决。`;
	if (reason === "disabled") {
		return `${base} disabled ≠ approval：决策点未开启不等于放行，被门控的动作仍受其常规工具权限约束。`;
	}
	return base;
}

/** Terminal directive emitted once a dp hits the per-turn block cap. */
export function terminalDirective(dp: string, blocks: number): string {
	return (
		`TERMINAL: "${dp}" has been blocked ${blocks} time(s) in this turn. ${ASK_DECISION_GUESS_DIRECTIVE}。` +
		`停止重试，上报 "blocked on decision ${dp}" 并结束本轮（不要再次调用 ask_decision）。`
	);
}

// ── The one decision call ───────────────────────────────────────────────────

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
	/** Business material of the selected active entry, verbatim. */
	material?: Record<string, unknown>;
	/** Local reference supplied by the host consuming a prepared follow-up. */
	parentDecisionRef?: string;
	preparation?: DecisionPreparation;
	context?: Record<string, unknown>;
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

function jsonText(payload: AskDecisionPayload): string {
	return JSON.stringify(payload);
}

function unavailable(
	reason: string,
	dp: string,
	spawned: boolean,
	extra: { escalated_reason?: string; missing_fields?: string[] } = {},
): AskDecisionOutcome {
	const payload: AskDecisionUnavailable = {
		available: false,
		unavailable: reason,
		action: ASK_DECISION_BLOCKED_ACTION,
	};
	if (extra.escalated_reason !== undefined) payload.escalated_reason = extra.escalated_reason;
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
export async function runAskDecision(input: AskDecisionInput): Promise<AskDecisionOutcome> {
	const started = Date.now();
	const dp = input.dp;
	// Zero-spawn refusal for an id the registry cannot resolve. The enum in the
	// tool schema already rejects it; `runAskDecision` is also called directly.
	const refusal = decisionIdRefusal(dp);
	if (refusal) return unavailable(refusal, dp, false);
	const role = input.initiatorRole ?? "unknown";
	// The originator is structural (the registering window), so a worker cannot
	// reach a PM decision point even by naming it (AC-006).
	if (!decisionActorAllowed(dp, role) || (DECIDE_REGISTRY[dp].roleScope === "worker" && !input.taskKey?.trim()))
		return unavailable(ASK_DECISION_REASON_ROLE_FORBIDDEN, dp, false);
	if (
		input.taskBefore !== undefined &&
		(!(input.taskKey ?? "").trim() || !isTaskStateSnapshot(input.taskBefore) || !isMaterialDp(dp))
	)
		return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, { missing_fields: ["meta.task_before"] });
	// dp-sign-key is the ONE judgment that really signs (T05 `decide sign --stdin`): the
	// sign CLI calls the model itself and writes `sign-final.md` (or hands a
	// concrete next step back). Routing it through `decide run` would need a
	// second approval/sign step, which the approved design refuses.
	if (!isMaterialDp(dp)) return runLegacyAskDecision(input, dp, started);
	const meta = buildDecisionToolMeta({
		key: input.key ?? "",
		taskKey: input.taskKey,
		initiatorRole: role,
		retryOf: input.retryOf,
		taskBefore: input.taskBefore,
	});
	const prepared = prepareDecisionEnvelope(
		dp,
		input.material,
		meta,
		0,
		input.preparation,
		input.context,
		input.parentDecisionRef,
	);
	if (!prepared.ok) return unavailable(prepared.reason, dp, false, { missing_fields: prepared.missing });
	return dp === SIGN_KEY_ID
		? runSignoffAskDecision(input, dp, prepared.envelope, started)
		: runMaterialAskDecision(input, dp, prepared.envelope, started);
}

/** Diagnostic for a locally refused call (no child ran). */
export function refusalOutcome(reason: string, dp: string, missing?: string[]): AskDecisionOutcome {
	return unavailable(reason, dp, false, { missing_fields: missing });
}

interface ChildCallFailure {
	ok: false;
	outcome: AskDecisionOutcome;
}

/** Spawn one decision child and parse its payload; every failure is DATA. */
async function callDecideChild(
	dp: string,
	request: DecideRunRequest,
	runner: DecideRunner,
	signal: AbortSignal | undefined,
): Promise<{ ok: true; response: Record<string, unknown> } | ChildCallFailure> {
	let raw: RawDecideResult;
	try {
		raw = await runner(request, signal);
	} catch {
		return { ok: false, outcome: unavailable("upstream-error", dp, true) };
	}
	if (raw.timedOut) return { ok: false, outcome: unavailable("timeout", dp, true) };
	if (raw.error !== undefined) return { ok: false, outcome: unavailable("upstream-error", dp, true) };
	const response = parseDecisionJson(raw.stdout);
	if (raw.status !== 0 && response?.available !== false)
		return { ok: false, outcome: unavailable("upstream-error", dp, true) };
	if (response === undefined) return { ok: false, outcome: unavailable("bad-response", dp, true) };
	if (response.available !== true) {
		const rawReason = typeof response.reason === "string" ? response.reason : "";
		const reason = ASK_DECISION_PYTHON_REASONS.has(rawReason) ? rawReason : "upstream-error";
		// The child's own 7-value escalation verdict travels beside (never instead
		// of) the frozen legacy reason (D-021 / D-030).
		const escalated =
			typeof response.escalated_reason === "string" && response.escalated_reason !== ""
				? response.escalated_reason
				: undefined;
		return { ok: false, outcome: unavailable(reason, dp, true, { escalated_reason: escalated }) };
	}
	return { ok: true, response };
}

/** Submit the prepared envelope and correlate its selected rationale.
 *
 * Order (design §2/§4.1): validate the material against the generated registry,
 * build the local envelope (fresh `logical_id` per real call), refuse an
 * over-budget material instead of truncating it, send, then resolve the native
 * selection back to the candidate the asker wrote and record `consumed`
 * through the single Python lifecycle writer. Nothing here executes business
 * work or writes a sign-off.
 */
async function runMaterialAskDecision(
	input: AskDecisionInput,
	dp: string,
	envelope: DecisionToolEnvelope,
	started: number,
): Promise<AskDecisionOutcome> {
	const { material, preparation, meta } = envelope;
	const request: DecideRunRequest = {
		projectDir: input.projectDir,
		dp,
		input: JSON.stringify(envelope),
		timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
		viaStdin: true,
	};
	const called = await callDecideChild(dp, request, input.runner ?? runDecideMw, input.signal);
	if (!called.ok) return called.outcome;
	const response = called.response;

	if (
		response.decision_id !== `${dp}:${meta.logical_id}` ||
		(response.dp !== undefined && response.dp !== dp) ||
		(response.logical_id !== undefined && response.logical_id !== meta.logical_id)
	)
		return unavailable("bad-response", dp, true);
	const answers = asAnswers(response.answers);
	if (answers === undefined) return unavailable("bad-response", dp, true);
	// The four authority keys are the child's verdict, taken verbatim (D-036).
	const decisionId = typeof response.decision_id === "string" ? response.decision_id : "";
	const mode = response.mode;
	const acted = response.acted;
	if (decisionId === "" || (mode !== "auto" && mode !== "suggest") || acted !== false) {
		return unavailable("bad-response", dp, true);
	}
	const selection = buildSelection(dp, answers, material);
	const basis = selectedDecisionBasis(dp, material, preparation, selection?.id, answers.basis_id?.value);
	if (selection === undefined || basis === undefined) {
		// A mismatched business answer or basis is never
		// mapped onto a candidate: that would invent the receipt (AC-006).
		return unavailable("bad-response", dp, true);
	}
	const latency = typeof response.latency_ms === "number" ? response.latency_ms : Date.now() - started;
	const payload: AskDecisionAvailable = {
		available: true,
		decision_id: decisionId,
		mode,
		acted,
		answers,
		confidence_source:
			typeof response.confidence_source === "string" && response.confidence_source !== ""
				? response.confidence_source
				: "unknown",
		latency_ms: latency,
		selection,
		basis,
	};
	// The asker really received the selection => `consumed` is a fact, not a
	// completion. `executed`/`settled` stay with the explicit receipt op.
	payload.feedback = await writeDecisionLifecycle(
		input.projectDir,
		{
			meta,
			decision_id: decisionId,
			dp,
			stage: "consumed",
			event_id: `consumed-${meta.logical_id}`,
			answer: selection.id,
		},
		input.lifecycleRunner ?? runLifecycleMw,
	);
	return { payload, text: jsonText(payload), spawned: true, meta };
}

/** The dp-sign-key path: ONE judgment, the CLI signs or hands over.
 *
 * The child is `mw decide sign <key> --stdin --json` (never `decide run` + a
 * second `sign` call). It records the creation fact, asks
 * `dp-sign-key` ONCE, persists the result record, and:
 * - `finalize` → writes/validates `evidence/review/sign-final.md` and records
 *   its own consumed + signoff lifecycle facts;
 * - `continue`/`user-confirm` → zero sign-off writes, one executed fact and a
 *   concrete `handoff` for the PM/user.
 * This function only maps that receipt; it never signs, approves twice or
 * invents a mode/role verdict of its own.
 */
async function runSignoffAskDecision(
	input: AskDecisionInput,
	dp: string,
	envelope: DecisionToolEnvelope,
	started: number,
): Promise<AskDecisionOutcome> {
	const { material, preparation, meta } = envelope;
	let raw: RawDecideResult;
	try {
		raw = await (input.signRunner ?? runSignMw)({
			projectDir: input.projectDir,
			key: meta.key,
			input: JSON.stringify(envelope),
			timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
		});
	} catch {
		return unavailable("upstream-error", dp, true);
	}
	if (raw.timedOut) return unavailable("timeout", dp, true);
	if (raw.error !== undefined) return unavailable("upstream-error", dp, true);
	const receipt = parseDecisionJson(raw.stdout);
	if (receipt === undefined) return unavailable("bad-response", dp, true);
	const conclusion = typeof receipt.conclusion === "string" ? receipt.conclusion : "";
	const rawStatus = typeof receipt.signoff_status === "string" ? receipt.signoff_status : "";
	const signoffStatus: DecisionSignoffResult["status"] =
		rawStatus === "written" ||
		rawStatus === "existing" ||
		rawStatus === "not-required" ||
		rawStatus === "invalid-existing" ||
		rawStatus === "disabled"
			? rawStatus
			: "failed";
	const problems = Array.isArray(receipt.problems)
		? receipt.problems.filter((item): item is string => typeof item === "string")
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
	const basis = selectedDecisionBasis(dp, material, preparation, conclusion, receipt.basis_id);
	if (
		!basis ||
		receipt.dp !== dp ||
		receipt.logical_id !== meta.logical_id ||
		receipt.key !== meta.key ||
		decisionId !== `${dp}:${meta.logical_id}` ||
		receipt.second_approval !== 0 ||
		(conclusion === "finalize" ? !["written", "existing"].includes(signoffStatus) : signoffStatus !== "not-required")
	)
		return unavailable("bad-response", dp, true);
	const signoff: DecisionSignoffResult = {
		status: signoffStatus,
		second_approval: typeof receipt.second_approval === "number" ? receipt.second_approval : 0,
	};
	if (typeof receipt.signoff_path === "string" && receipt.signoff_path !== "") {
		signoff.path = receipt.signoff_path;
	}
	if (typeof receipt.record_status === "string") signoff.record_status = receipt.record_status;
	if (typeof receipt.model_called === "boolean") signoff.model_called = receipt.model_called;
	if (typeof receipt.feedback_status === "string") signoff.feedback_status = receipt.feedback_status;
	if (Array.isArray(receipt.feedback_stages)) {
		signoff.feedback_stages = receipt.feedback_stages.filter(
			(item): item is { stage?: string | null; status?: string | null; event_id?: string | null } => isRecord(item),
		);
	}
	if (problems.length > 0) signoff.problems = problems;
	if (isRecord(receipt.handoff)) {
		const handoff = receipt.handoff;
		signoff.handoff = {
			owner: typeof handoff.owner === "string" ? handoff.owner : undefined,
			kind: typeof handoff.kind === "string" ? handoff.kind : undefined,
			signoff_writes: typeof handoff.signoff_writes === "number" ? handoff.signoff_writes : undefined,
			instruction: typeof handoff.instruction === "string" ? handoff.instruction : undefined,
		};
	}
	const acted = signoffStatus === "written" || signoffStatus === "existing";
	const payload: AskDecisionAvailable = {
		available: true,
		decision_id: decisionId,
		// `decide sign` exposes no execution mode: reporting one would be a local
		// verdict the authority never gave (mode is optional on purpose).
		acted,
		answers: { [DECIDE_REGISTRY[dp].businessQuestionId]: { value: conclusion }, basis_id: { value: basis.id } },
		basis,
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
async function runLegacyAskDecision(input: AskDecisionInput, dp: string, started: number): Promise<AskDecisionOutcome> {
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
	const request: DecideRunRequest = {
		projectDir: input.projectDir,
		dp,
		input: buildDecisionRequestJson(state),
		timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
	};
	const called = await callDecideChild(dp, request, input.runner ?? runDecideMw, input.signal);
	if (!called.ok) return called.outcome;
	const response = called.response;
	const latency = typeof response.latency_ms === "number" ? response.latency_ms : Date.now() - started;

	let answers = asAnswers(response.answers);
	if (answers === undefined) return unavailable("bad-response", dp, true);
	if (input.question !== undefined) {
		const picked = answers[input.question];
		if (picked === undefined) return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, true);
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

	const payload: AskDecisionAvailable = {
		available: true,
		decision_id: decisionId,
		mode,
		acted,
		answers,
		confidence_source:
			typeof response.confidence_source === "string" && response.confidence_source !== ""
				? response.confidence_source
				: "unknown",
		latency_ms: latency,
	};
	return { payload, text: jsonText(payload), spawned: true };
}

// ── Anti-retry counter ──────────────────────────────────────────────────────

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
export function createDecisionBlockCounter(): DecisionBlockCounter {
	const counts = new Map<string, number>();
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

// ── Registration ────────────────────────────────────────────────────────────

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

function ownerKeyFromTaskPath(taskPath: string): string | undefined {
	// <control>/.agenticdoc/<key>/workers/<task>/task.md
	const key = path.basename(path.dirname(path.dirname(path.dirname(taskPath))));
	return key === "" || key === "." ? undefined : key;
}

/** The REAL task id of a worker card path (never "the latest task"). */
function workerTaskKeyFromTaskPath(taskPath: string): string | undefined {
	const task = path.basename(path.dirname(taskPath));
	return task === "" || task === "." || task === "workers" ? undefined : task;
}

function appendDecisionTrace(tracePath: string | undefined, line: string): void {
	if (tracePath === undefined) return;
	try {
		fs.mkdirSync(path.dirname(tracePath), { recursive: true });
		fs.appendFileSync(tracePath, `${line}\n`, "utf8");
	} catch {
		// Diagnostic append — a failure must never break the tool call.
	}
}

/** DP enum schema. A tuple cast keeps `Static` at the literal union — a plain
 * mapped array widens to `TSchema[]` and `Static` would collapse to `never`. */
type AskDecisionDpLiteral = TLiteral<AskDecisionDpId>;

const DP_ENUM_SCHEMA = Type.Union(
	ASK_DECISION_DP_IDS.map((id) => Type.Literal(id)) as [AskDecisionDpLiteral, ...AskDecisionDpLiteral[]],
	{ description: "Registered decision point id (unknown ids are rejected)" },
);

/** The material alternatives and their closed nested field sets are generated from the active registry. */
interface MaterialObjectSchema {
	type: "object";
	properties: Record<string, MaterialObjectSchema | Record<string, unknown>>;
	required: string[];
	additionalProperties: false;
}

const MATERIAL_SCHEMA = Type.Optional(
	Type.Unsafe<Record<string, unknown>>({
		anyOf: Object.entries(DECIDE_REGISTRY).map(([id, entry]) => {
			const schema: MaterialObjectSchema = {
				type: "object",
				properties: {},
				required: [],
				additionalProperties: false,
			};
			for (const field of [...entry.requiredStateFields, ...entry.optionalStateFields]) {
				const names = field.name.split(".");
				let parent = schema;
				for (const [index, name] of names.entries()) {
					if (entry.requiredStateFields.includes(field) && !parent.required.includes(name))
						parent.required.push(name);
					if (index === names.length - 1) {
						parent.properties[name] = {
							type: field.type,
							description: field.description,
							...(field.itemType ? { items: { type: field.itemType } } : {}),
							...(field.maxItems === undefined ? {} : { maxItems: field.maxItems }),
						};
					} else {
						const nested = parent.properties[name] ?? {
							type: "object",
							properties: {},
							required: [],
							additionalProperties: false,
						};
						parent.properties[name] = nested;
						parent = nested as MaterialObjectSchema;
					}
				}
			}
			return { ...schema, title: id };
		}),
		description:
			"Business material for the selected entry. Identity, preparation and optional context travel separately.",
	}),
);
const PREPARATION_SCHEMA = Type.Optional(
	Type.Object(
		{
			prepared_at: Type.String(),
			basis_catalog: Type.Array(
				Type.Object(
					{
						id: Type.String(),
						text: Type.String(),
						material_refs: Type.Array(Type.String()),
						applies_to: Type.Array(Type.String()),
					},
					{ additionalProperties: false },
				),
				{ minItems: 1 },
			),
		},
		{ additionalProperties: false },
	),
);

/** Tool parameter schema (exported so tests can assert the dp enum surface). */
export const ASK_DECISION_PARAMETERS = Type.Object(
	{
		dp: DP_ENUM_SCHEMA,
		trigger: Type.String({
			minLength: 1,
			maxLength: 256,
			pattern: "^[^\\s:]+$",
			description:
				"Audit trigger label, e.g. <task_key> or <task_key>#ckpt3 (no ':' per D-023); " +
				"the decision id itself is resolved by the service",
		}),
		question: Type.Optional(
			Type.String({
				minLength: 1,
				maxLength: 64,
				description: "Single registry question id; omit for the full question set",
			}),
		),
		note: Type.Optional(
			Type.String({
				maxLength: 800,
				description: "Short L0/L1 context summary (no secrets/absolute paths/code)",
			}),
		),
		material: MATERIAL_SCHEMA,
		preparation: PREPARATION_SCHEMA,
		context: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
		key: Type.Optional(
			Type.String({
				minLength: 1,
				maxLength: 64,
				description:
					"A key claimed by this PM window. Omit for its sole active key. Worker identity comes from its task card.",
			}),
		),
		task_before: Type.Optional(AGENT_TASK_STATE_SCHEMA),
		task_key: Type.Optional(
			Type.String({
				minLength: 1,
				maxLength: 64,
				description: "The REAL task this decision belongs to; omit when the decision has no task",
			}),
		),
	},
	{ additionalProperties: false },
);

/** Receipt parameters: the ONLY way `executed`/`settled` are ever recorded. */
export const DECISION_RECEIPT_PARAMETERS = Type.Object(
	{
		decision_id: Type.String({ minLength: 1, description: "The decision this receipt is about" }),
		stage: Type.Union([Type.Literal("executed"), Type.Literal("settled")], {
			description: "executed = the action really happened; settled = this round of handling finished",
		}),
		action: Type.Optional(
			Type.String({ description: "executed: one closed action label (pm-handoff/clarify/narrow/...)" }),
		),
		result: Type.Optional(Type.String({ description: "executed: what the result was based on" })),
		outcome: Type.Optional(
			Type.String({ description: "settled: one closed outcome (ok/rework/rollback/inconclusive/pending)" }),
		),
		reason: Type.Optional(Type.String({ description: "settled/executed: short free-text reason" })),
		event_id: Type.Optional(Type.String({ description: "Reuse the SAME id only when retrying this very write" })),
		task_after: Type.Optional(AGENT_TASK_STATE_SCHEMA),
	},
	{ additionalProperties: false },
);

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
export function registerAskDecisionTool(pi: ExtensionAPI, options: AskDecisionToolOptions = {}): AskDecisionToolHandle {
	const taskPath = options.taskPath ?? process.env.PI_WORKER_TASK;
	const resolvedTaskPath = taskPath !== undefined && taskPath !== "" ? path.resolve(taskPath) : undefined;
	const projectDir =
		options.projectDir ??
		(resolvedTaskPath !== undefined ? controlRootFromTaskPath(resolvedTaskPath) : process.cwd());
	const tracePath =
		options.tracePath ??
		(resolvedTaskPath !== undefined ? path.join(path.dirname(resolvedTaskPath), "trace.log") : undefined);
	// The worker's owning key/task come from its own card path; the PM has no
	// task path, so it must pass its `key` (and a task only when it names one).
	const ownerKey = resolvedTaskPath !== undefined ? ownerKeyFromTaskPath(resolvedTaskPath) : options.key;
	const workerTaskKey =
		resolvedTaskPath !== undefined
			? (workerTaskKeyFromTaskPath(resolvedTaskPath) ?? null)
			: (options.taskKey ?? null);
	const initiatorRole = resolvedTaskPath
		? initiatorRoleFromWorkerTask(resolvedTaskPath)
		: (options.initiatorRole ?? "unknown");

	function boundKey(requested: string | undefined): string | undefined {
		if (ownerKey !== undefined)
			return requested === undefined || requested.trim() === ownerKey ? ownerKey : undefined;
		if (initiatorRole !== "pm") return undefined;
		return claimedPmKey(projectDir, requested);
	}

	const counter = createDecisionBlockCounter();
	/** The decisions this window asked (receipt lookup + the join meta). */
	const asked = new Map<string, { meta: DecisionToolMeta; dp: string }>();

	// One turn = one retry window: the same dp gets a fresh budget per turn.
	pi.on("turn_start", () => counter.reset());

	pi.registerTool<typeof ASK_DECISION_PARAMETERS, AskDecisionPayload>({
		name: ASK_DECISION_TOOL,
		label: ASK_DECISION_TOOL,
		description:
			"Ask the external decision service for a human-style ruling on a gated decision point. " +
			"Returns ONE line of JSON: {available, decision_id, mode, acted, answers, confidence_source, latency_ms}" +
			", plus {selection, feedback} on the prepared material path. " +
			"available=false means UNAVAILABLE: the gated action stays blocked — do NOT guess, do NOT work around it, " +
			'report "blocked on decision <dp>" and stop. The failure line also carries escalated_reason, and for ' +
			"input-incomplete, missing_fields.",
		promptSnippet:
			"ask_decision(dp, trigger, material?, question?, note?) — ask the decision service before a gated action; " +
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
			...Object.values(DECISION_MATERIAL_PROMPTS),
			"Prepare material and a separately timestamped basis_catalog. Each item cites existing material_refs and names its applicable choices. No preparation means this request is blocked; never invent evidence. An L0 note cannot substitute for pm_note.",
			"task_before is an optional local Agent report of this task BEFORE the decision, never model material. Use source=agent-report, an ISO timestamp with timezone, and null for unrecorded progress; do not substitute current state for past state or invent observations.",
			"Generated roleScope governs the entry. Only the current worker can ask dp-w-check-task; a worker is refused on PM entries and must report the block " +
				"instead of asking.",
			"After the selection: act only inside your existing authority, then call decision_receipt with the " +
				"action you really performed (executed) and, when this round is handled, settled. Never receipt what " +
				"did not happen; dp-sign-key uses the sign CLI (the sign-off writer is the CLI).",
			"dp-pm-steer handling: a narrow that changes the confirmed delivery goal still goes to the user; direct-exec " +
				"first coordinates the live worker's write surface; escalate asks the user a CONCRETE risk/authority " +
				"question. The model's choice alone never rewrites, terminates or splits a task.",
			"dp-sign-key branches: finalize is decided AND signed by the same `mw decide sign` call - the tool writes the sign-off file itself, so never ask the PM for a second approval or a second model call; continue and user-confirm write no sign-off and end with the concrete gaps to advance or the concrete items to confirm.",
		],
		parameters: ASK_DECISION_PARAMETERS,
		// Sequential: an ask changes gate state, so it must not race the tools
		// it authorizes (design Q1 §1.1).
		executionMode: "sequential",
		execute: async (_toolCallId, params, signal) => {
			if (Object.hasOwn(params, "parentDecisionRef") || Object.hasOwn(params, "parent_decision_ref")) {
				const refused = refusalOutcome("input-incomplete", params.dp, ["parent_decision_ref"]);
				return { content: [{ type: "text", text: refused.text }], details: refused.payload };
			}
			const invalidDp = decisionIdRefusal(params.dp);
			if (invalidDp) {
				const refused = refusalOutcome(invalidDp, params.dp);
				return { content: [{ type: "text", text: refused.text }], details: refused.payload };
			}
			const requestedKey = boundKey(params.key);
			if (requestedKey === undefined) {
				// A window never decides under another key: the association must stay
				// exact instead of being rewritten by a model parameter (AC-010).
				const refused = refusalOutcome("input-incomplete", params.dp, ["meta.key"]);
				appendDecisionTrace(
					tracePath,
					`[DECISION_UNAVAILABLE] ${new Date().toISOString()} dp=${params.dp} trigger=${params.trigger} ` +
						"reason=input-incomplete field=meta.key count=1 max=" +
						`${ASK_DECISION_MAX_BLOCKED_PER_TURN} role=${initiatorRole}`,
				);
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
				preparation: params.preparation,
				context: params.context,
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
				appendDecisionTrace(
					tracePath,
					`[DECISION] ${iso} dp=${params.dp} trigger=${params.trigger} ` +
						`decision_id=${outcome.payload.decision_id} mode=${outcome.payload.mode ?? "-"} ` +
						`acted=${String(outcome.payload.acted)} source=${outcome.payload.confidence_source} ` +
						`latency_ms=${outcome.payload.latency_ms} role=${initiatorRole}` +
						(outcome.payload.selection !== undefined ? ` selection=${outcome.payload.selection.id}` : "") +
						(outcome.payload.feedback !== undefined
							? ` feedback=${outcome.payload.feedback.stage}:${outcome.payload.feedback.status}`
							: ""),
				);
				return { content: [{ type: "text", text: outcome.text }], details: outcome.payload };
			}

			const reason = outcome.payload.unavailable;
			const escalated =
				outcome.payload.escalated_reason !== undefined
					? ` escalated_reason=${outcome.payload.escalated_reason}`
					: "";
			const blocks = counter.recordBlock(params.dp);
			appendDecisionTrace(
				tracePath,
				`[DECISION_UNAVAILABLE] ${iso} dp=${params.dp} trigger=${params.trigger} reason=${reason}` +
					`${escalated} count=${blocks} max=${ASK_DECISION_MAX_BLOCKED_PER_TURN} role=${initiatorRole}`,
			);
			if (blocks < ASK_DECISION_MAX_BLOCKED_PER_TURN) {
				return { content: [{ type: "text", text: outcome.text }], details: outcome.payload };
			}
			appendDecisionTrace(
				tracePath,
				`[DECISION_RETRY_STOP] ${iso} dp=${params.dp} trigger=${params.trigger} reason=${reason} ` +
					`count=${blocks} max=${ASK_DECISION_MAX_BLOCKED_PER_TURN} role=${initiatorRole}`,
			);
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
	pi.registerTool<typeof DECISION_RECEIPT_PARAMETERS, DecisionReceiptDetails>({
		name: DECISION_RECEIPT_TOOL,
		label: DECISION_RECEIPT_TOOL,
		description:
			"Record what really happened with a decision this window asked: executed (the action happened) " +
			"and settled (this round of handling finished). Returns ONE line of JSON " +
			"{stage, status, decision_id}; status=failed means the feedback ledger rejected the write — the " +
			"action itself is not undone. An unknown decision id or action is NOT recorded.",
		promptSnippet:
			"decision_receipt(decision_id, stage, action?, result?, outcome?, reason?) — record the real action/closure.",
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
			const refusal = (
				reason: string,
				dp: string | null,
				missing?: string[],
			): { content: Array<{ type: "text"; text: string }>; details: DecisionReceiptDetails } => {
				const refused = refusalOutcome(reason, dp ?? "unknown", missing);
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
			if (known === undefined) return refusal(ASK_DECISION_REASON_UNKNOWN_DECISION, null);
			if (boundKey(known.meta.key) !== known.meta.key)
				return refusal(ASK_DECISION_REASON_INPUT_INCOMPLETE, known.dp, ["meta.key"]);
			if (
				params.task_after !== undefined &&
				(known.meta.task_key === null || !isTaskStateSnapshot(params.task_after))
			)
				return refusal(ASK_DECISION_REASON_INPUT_INCOMPLETE, known.dp);
			const eventId = params.event_id ?? randomUUID();
			let envelope: DecisionLifecycleEnvelope;
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
				if (params.result !== undefined) envelope.result = params.result;
				if (params.reason !== undefined) envelope.reason = params.reason;
			} else {
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
				if (params.reason !== undefined) envelope.reason = params.reason;
			}
			if (params.task_after !== undefined) envelope.task_after = copyTaskState(params.task_after);
			const feedback = await writeDecisionLifecycle(projectDir, envelope, options.lifecycleRunner ?? runLifecycleMw);
			appendDecisionTrace(
				tracePath,
				`[DECISION_RECEIPT] ${new Date().toISOString()} dp=${known.dp} stage=${feedback.stage} ` +
					`status=${feedback.status} decision_id=${params.decision_id} role=${initiatorRole}`,
			);
			const details: DecisionReceiptDetails = {
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
		if (missing.length === 0) return;
		pi.setActiveTools([...active, ...missing]);
	});

	return { projectDir, tracePath, counter };
}
