/**
 * r2 decision-handoff contract, schema v1 (`design.md` §4.1..§4.5, T01).
 *
 * PURE MODULE BOUNDARY — read this before using any API below:
 *   - This file is types + classification + shape/consistency validation ONLY.
 *   - It imports NOTHING, reads no file, opens no socket, mints no authority,
 *     produces no business effect and never refreshes a budget.
 *   - `source`, `owner`, `local_ref`, `decision_id` are DATA, not capabilities.
 *   - A successful `ContractValidation` is explicitly `host_source_verified: false`.
 *     It proves the JSON shape is internally consistent; it NEVER proves that
 *     the host binding, claim, files, digests or action/result refs are real.
 *   - Real host/file verification is the job of T02 (the unique TS host writer)
 *     and T03 (the Python strict reader): current live claim/owner, lock/path,
 *     card and file digests, actual tool_call/dispatch receipts and verifier
 *     output. Those checks are deliberately NOT implemented here.
 *   - `DecisionRef` is a discriminated union; a `local_ref` is never a DP id and
 *     a string prefix never grants a source. A real parent DP is referenced by
 *     a separate `kind: "dp"` field, never by a local record's own id.
 *
 * Every exported record type is JSON-serializable (optional fields are simply
 * absent in JSON when unknown; nothing is guessed or filled in).
 */

// ── Schema identity ────────────────────────────────────────────────────────

export const DECISION_HANDOFF_SCHEMA_VERSION = 1;
export const DECISION_HANDOFF_SCHEMA_ID = "decision-handoff/v1";

export type SchemaVersion = typeof DECISION_HANDOFF_SCHEMA_VERSION;

/** Closed 13-category feedback vocabulary (`design.md` §4.1). */
export const FEEDBACK_CATEGORIES = [
	"answer",
	"advisory",
	"service-unavailable",
	"input-gap",
	"uncertain-answer",
	"binding-invalid",
	"integrity-error",
	"authority-required",
	"effect-unknown",
	"cancelled",
	"budget-exhausted",
	"exemption",
	"unclassified",
] as const;
export type FeedbackCategory = (typeof FEEDBACK_CATEGORIES)[number];

export const EFFECT_STATES = ["none", "known", "unknown"] as const;
export type EffectState = (typeof EFFECT_STATES)[number];

/** Scope of a stop/budget fact. `user-global` can ONLY come from a host stop
 *  signal; a service timeout is `service-request` and never stops the PM. */
export const STOP_SCOPES = [
	"none",
	"service-request",
	"worker-run",
	"matter",
	"pm-or-key",
	"user-global",
	"unknown",
] as const;
export type StopScope = (typeof STOP_SCOPES)[number];

export const PM_DISPOSITION_KINDS = [
	"self-decide",
	"collect-evidence",
	"reconcile",
	"replan",
	"await-worker",
	"await-external",
	"stopped",
	"resource-limited",
] as const;
export type PmDispositionKind = (typeof PM_DISPOSITION_KINDS)[number];

export const PM_DISPOSITION_STATUSES = ["planned", "running", "observed", "superseded", "waiting", "stopped"] as const;
export type PmDispositionStatus = (typeof PM_DISPOSITION_STATUSES)[number];

export const TOOL_NAMES = ["read", "find", "grep", "ls", "bash", "write", "edit", "dispatch"] as const;
export type ToolName = (typeof TOOL_NAMES)[number];
export const READ_ONLY_TOOLS: readonly ToolName[] = ["read", "find", "grep", "ls"];

export const LOCAL_SOURCES = ["pm", "worker-local"] as const;
export type LocalSource = (typeof LOCAL_SOURCES)[number];

/** A local record must NEVER carry any of these DP facts. This is a schema
 *  list, not an authorization list: readers must reject these keys verbatim. */
export const FORBIDDEN_LOCAL_DP_FIELDS: readonly string[] = [
	"decision_id",
	"answers",
	"available",
	"business_decisions",
	"business_decision",
	"decision_lifecycle",
	"receipt",
	"request_ref",
	"model_called",
	"decision_ref",
];

/** Transport reason vocabulary frozen by the existing Python service. Unknown
 *  reasons are NOT in this map and are classified `unclassified` with the raw
 *  text preserved — never folded into `authority-required`. */
export const TRANSPORT_REASON_CATEGORIES: Readonly<Record<string, FeedbackCategory>> = {
	disabled: "service-unavailable",
	"entry-unavailable": "service-unavailable",
	unconfigured: "service-unavailable",
	"unsupported-question-type": "service-unavailable",
	retired: "service-unavailable",
	"unknown-dp": "service-unavailable",
	timeout: "service-unavailable",
	"rate-limited": "service-unavailable",
	"upstream-error": "service-unavailable",
	"bad-response": "service-unavailable",
	"input-incomplete": "input-gap",
	"input-oversize": "input-gap",
	"role-forbidden": "binding-invalid",
	"budget-exhausted": "budget-exhausted",
};

/** Reasons whose stop scope is the single service request, never the PM/key. */
const SERVICE_REQUEST_REASONS: ReadonlySet<string> = new Set([
	"timeout",
	"rate-limited",
	"upstream-error",
	"bad-response",
]);

/** Own-key-only reason lookup. Inherited Object.prototype members
 *  (`toString`, `__proto__`, `constructor`, ...) are NOT transport reasons:
 *  indexing the map for them returns a function/object at runtime. Unknown
 *  reasons stay `unclassified` with the raw text preserved verbatim, and the
 *  returned value is always a real FeedbackCategory string. */
function transportCategoryFor(reason: unknown): FeedbackCategory | undefined {
	if (typeof reason !== "string" || !Object.hasOwn(TRANSPORT_REASON_CATEGORIES, reason)) return undefined;
	const mapped: unknown = TRANSPORT_REASON_CATEGORIES[reason];
	return typeof mapped === "string" && (FEEDBACK_CATEGORIES as readonly string[]).includes(mapped)
		? (mapped as FeedbackCategory)
		: undefined;
}

// ── JSON primitives ────────────────────────────────────────────────────────

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

/** Recursive, cycle-safe JSON-value guard. Untrusted input is always `unknown`. */
export function isJsonValue(value: unknown, seen: Set<object> = new Set()): value is JsonValue {
	if (value === null || typeof value === "string" || typeof value === "boolean") return true;
	if (typeof value === "number") return Number.isFinite(value);
	if (Array.isArray(value)) {
		if (seen.has(value)) return false;
		seen.add(value);
		return value.every((item) => isJsonValue(item, seen));
	}
	if (typeof value === "object") {
		if (seen.has(value as object)) return false;
		seen.add(value as object);
		return Object.values(value as Record<string, unknown>).every((item) => isJsonValue(item, seen));
	}
	return false;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonblank(value: unknown): value is string {
	return typeof value === "string" && value.trim() !== "";
}

function isoTimestamp(value: unknown): value is string {
	return (
		nonblank(value) && /^\d{4}-\d\d-\d\dT.+(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value))
	);
}

function finiteAtLeast(value: unknown, min: number): value is number {
	return typeof value === "number" && Number.isFinite(value) && value >= min;
}

function safeIntAtLeast(value: unknown, min: number): value is number {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= min;
}

function nonblankStringArray(value: unknown): value is string[] {
	return Array.isArray(value) && value.every(nonblank);
}

// ── Validation result (pure shape only) ────────────────────────────────────

export interface ContractIssue {
	field: string;
	rule: string;
}

/** Every success is `host_source_verified: false`. Every failure is a
 *  fillable shape/consistency gap (`authority_required: false`): a missing
 *  budget or material is never fabricated into a human-authority question. */
export type ContractValidation<T> =
	| {
			ok: true;
			layer: string;
			value: T;
			verification: "shape-only";
			host_source_verified: false;
	  }
	| {
			ok: false;
			layer: string;
			issues: ContractIssue[];
			gaps: string[];
			authority_required: false;
	  };

function issue(field: string, rule: string): ContractIssue {
	return { field, rule };
}

function accepted<T>(layer: string, value: T): ContractValidation<T> {
	return { ok: true, layer, value, verification: "shape-only", host_source_verified: false };
}

function rejected<T>(layer: string, issues: ContractIssue[], gaps: string[] = []): ContractValidation<T> {
	return { ok: false, layer, issues, gaps, authority_required: false };
}

function requiredString(
	obj: Record<string, unknown>,
	key: string,
	issues: ContractIssue[],
	gaps: string[],
	prefix = "",
): string | undefined {
	const value = obj[key];
	if (!nonblank(value)) {
		issues.push(issue(prefix + key, "missing or blank"));
		gaps.push(prefix + key);
		return undefined;
	}
	return value;
}

function optionalString(
	obj: Record<string, unknown>,
	key: string,
	issues: ContractIssue[],
	prefix = "",
): string | undefined {
	const value = obj[key];
	if (value === undefined) return undefined;
	if (!nonblank(value)) {
		issues.push(issue(prefix + key, "must be a nonblank string when present"));
		return undefined;
	}
	return value;
}

function optionalStringArray(
	obj: Record<string, unknown>,
	key: string,
	issues: ContractIssue[],
	prefix = "",
): string[] | undefined {
	const value = obj[key];
	if (value === undefined) return undefined;
	if (!nonblankStringArray(value)) {
		issues.push(issue(prefix + key, "must be an array of nonblank strings"));
		return undefined;
	}
	return value;
}

/** Reject both unknown keys and DP impersonation keys. The forbidden rule is
 *  reported explicitly so a reader never mistakes a local row for a DP row. */
function checkDeclaredKeys(
	obj: Record<string, unknown>,
	allowed: readonly string[],
	issues: ContractIssue[],
	prefix = "",
): void {
	for (const key of Object.keys(obj)) {
		if (FORBIDDEN_LOCAL_DP_FIELDS.includes(key)) {
			issues.push(issue(prefix + key, "forbidden DP impersonation field in a local record"));
		} else if (!allowed.includes(key)) {
			issues.push(issue(prefix + key, "not a declared schema v1 field"));
		}
	}
}

// ── Host facts (trusted snapshot, NOT model self-report) ───────────────────

export type HostRole = "pm" | "coding" | "research" | "review" | "unknown";

/** `owner` is resolved by the calling host. Absent = owner-unbound; a model
 *  parameter can never set it. `binding_version` is a host snapshot marker used
 *  to reject stale bindings; it is not an authorization token. */
export interface HostBinding {
	role: HostRole;
	owner?: string;
	claim_id?: string;
	key?: string;
	task_key?: string;
	run_id?: string;
	binding_version: string;
	observed_at: string;
}

/** A real, host-observed external authority gap (policy check), not p0 text. */
export interface AuthorityFact {
	policy_ref: string;
	condition: string;
}

/** A real, host-observed business exemption (e.g. signoff=disable config). */
export interface ExemptionFact {
	config_ref: string;
	kind: "signoff-disabled" | "dp-disabled" | "transport-unconfigured";
}

export type StopSignalKind = "user-stop" | "parent-cancel" | "worker-deadline" | "key-budget" | "service-timeout";

export interface StopSignal {
	signal_ref: string;
	kind: StopSignalKind;
}

/** Service-budget and task-budget exhaustion are separate facts. */
export interface BudgetExhaustionFact {
	budget_ref: string;
	scope: "service" | "task";
}

/** Trusted host snapshot supplied by the caller, never by the model. */
export interface HostFacts {
	binding: HostBinding;
	authority_gap?: AuthorityFact;
	exemption?: ExemptionFact;
	stop_signals?: StopSignal[];
	budget_facts?: BudgetExhaustionFact[];
	effect_unknown?: { action_ref: string };
}

export function stopScopeForSignal(kind: StopSignalKind): StopScope {
	switch (kind) {
		case "user-stop":
			return "user-global";
		case "parent-cancel":
		case "key-budget":
			return "pm-or-key";
		case "worker-deadline":
			return "worker-run";
		case "service-timeout":
			return "service-request";
	}
}

export function stopScopeForBudgetFact(scope: BudgetExhaustionFact["scope"]): StopScope {
	return scope === "service" ? "service-request" : "matter";
}

/** Rank a host stop by its REAL scope, never by array order. Service-request
 *  failures, exemption and authority diagnostics are not global stops. */
const STOP_SCOPE_RANK: Readonly<Record<StopScope, number>> = {
	none: 0,
	unknown: 0,
	"service-request": 1,
	"worker-run": 2,
	matter: 3,
	"pm-or-key": 4,
	"user-global": 5,
};

/** Fixed within-scope tie-break (never an array index), so permutations of
 *  stop_signals / budget_facts cannot change which fact wins. */
const STOP_SIGNAL_PRIORITY: Readonly<Record<StopSignalKind, number>> = {
	"user-stop": 9,
	"parent-cancel": 8,
	"key-budget": 7,
	"worker-deadline": 6,
	"service-timeout": 3,
};
const TASK_BUDGET_FACT_PRIORITY = 5;
const SERVICE_BUDGET_FACT_PRIORITY = 4;

const STOP_SIGNAL_KINDS: readonly StopSignalKind[] = [
	"user-stop",
	"parent-cancel",
	"worker-deadline",
	"key-budget",
	"service-timeout",
];

interface HostStopFact {
	scope: StopScope;
	category: FeedbackCategory;
	priority: number;
	signal_ref?: string;
	budget_fact?: BudgetExhaustionFact;
}

/** Trusted host stop/budget facts as scope-ranked candidates. Diagnostics
 *  (authority gap, exemption, effect-unknown) are deliberately NOT facts here:
 *  they must never mask a real host stop. Untrusted runtime shapes are guarded
 *  with `unknown` + type guards, never assumed from the static type. */
function hostStopFacts(host: HostFacts): HostStopFact[] {
	const snapshot: Record<string, unknown> = isRecord(host) ? host : {};
	const facts: HostStopFact[] = [];
	const signals: unknown = snapshot.stop_signals;
	if (Array.isArray(signals)) {
		for (const entry of signals) {
			if (!isRecord(entry)) continue;
			const kind = STOP_SIGNAL_KINDS.find((candidate) => candidate === entry.kind);
			if (kind === undefined) continue;
			const category: FeedbackCategory =
				kind === "user-stop" || kind === "parent-cancel"
					? "cancelled"
					: kind === "service-timeout"
						? "service-unavailable"
						: "budget-exhausted";
			const signalRef =
				typeof entry.signal_ref === "string" && entry.signal_ref !== "" ? entry.signal_ref : undefined;
			facts.push({
				scope: stopScopeForSignal(kind),
				category,
				priority: STOP_SIGNAL_PRIORITY[kind],
				...(signalRef === undefined ? {} : { signal_ref: signalRef }),
			});
		}
	}
	const budgetFacts: unknown = snapshot.budget_facts;
	if (Array.isArray(budgetFacts)) {
		for (const entry of budgetFacts) {
			if (!isRecord(entry) || (entry.scope !== "service" && entry.scope !== "task")) continue;
			const scope: BudgetExhaustionFact["scope"] = entry.scope;
			const budgetRef = typeof entry.budget_ref === "string" ? entry.budget_ref : "";
			facts.push({
				scope: stopScopeForBudgetFact(scope),
				category: "budget-exhausted",
				priority: scope === "task" ? TASK_BUDGET_FACT_PRIORITY : SERVICE_BUDGET_FACT_PRIORITY,
				budget_fact: { budget_ref: budgetRef, scope },
			});
		}
	}
	return facts;
}

function strongerHostStop(a: HostStopFact, b: HostStopFact): boolean {
	const rankA = STOP_SCOPE_RANK[a.scope];
	const rankB = STOP_SCOPE_RANK[b.scope];
	return rankA === rankB ? a.priority > b.priority : rankA > rankB;
}

/** Dominant trusted host stop by real scope, not array order. */
function dominantHostStop(host: HostFacts): HostStopFact | undefined {
	let best: HostStopFact | undefined;
	for (const fact of hostStopFacts(host)) {
		if (best === undefined || strongerHostStop(fact, best)) best = fact;
	}
	return best;
}

/** Which trusted stops forbid NEW work in this host's scope. A service-only
 *  failure never stops independent PM/key work; a worker-run deadline stops
 *  only the corresponding worker, never an unrelated PM. */
function stopBlocksNewWork(fact: HostStopFact, role: HostRole | undefined): boolean {
	switch (fact.scope) {
		case "user-global":
		case "pm-or-key":
		case "matter":
			return true;
		case "worker-run":
			return role !== "pm";
		default:
			return false;
	}
}

/** Scope-aware stop for the new-work entry points. Necessary read-only
 *  reconciliation while stopped is the later host writer's dedicated wrap-up
 *  path (T02/T03), not a grant from this pure API: shape parsers and feedback
 *  classification stay available for that path. */
function newWorkStop(host: HostFacts): HostStopFact | undefined {
	const snapshot: Record<string, unknown> = isRecord(host) ? host : {};
	const binding: unknown = snapshot.binding;
	const role: HostRole | undefined =
		isRecord(binding) &&
		(binding.role === "pm" ||
			binding.role === "coding" ||
			binding.role === "research" ||
			binding.role === "review" ||
			binding.role === "unknown")
			? binding.role
			: undefined;
	let best: HostStopFact | undefined;
	for (const fact of hostStopFacts(host)) {
		if (!stopBlocksNewWork(fact, role)) continue;
		if (best === undefined || strongerHostStop(fact, best)) best = fact;
	}
	return best;
}

const HOST_BINDING_FIELDS = [
	"role",
	"owner",
	"claim_id",
	"key",
	"task_key",
	"run_id",
	"binding_version",
	"observed_at",
] as const;

/** Binding IDENTITY coordinates checked for drift. `observed_at` is the
 *  snapshot timestamp, deliberately NOT an identity coordinate. Strict
 *  inequality also catches absent <-> present drift. */
const HOST_IDENTITY_FIELDS = ["owner", "role", "claim_id", "key", "task_key", "run_id", "binding_version"] as const;

/** Shape-only validation of a host binding snapshot. It does NOT check that
 *  the claim/owner is live: that is T02/T03's real host verification. */
export function parseHostBinding(value: unknown): ContractValidation<HostBinding> {
	const layer = "host-binding-schema";
	if (!isRecord(value)) return rejected(layer, [issue("host_binding", "must be an object")], ["host_binding"]);
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	checkDeclaredKeys(value, HOST_BINDING_FIELDS, issues, "host_binding.");
	const rawRole = value.role;
	const role: HostRole | undefined =
		rawRole === "pm" ||
		rawRole === "coding" ||
		rawRole === "research" ||
		rawRole === "review" ||
		rawRole === "unknown"
			? rawRole
			: undefined;
	if (role === undefined) {
		issues.push(issue("host_binding.role", "unknown role"));
		gaps.push("host_binding.role");
	}
	const owner = optionalString(value, "owner", issues, "host_binding.");
	const claimId = optionalString(value, "claim_id", issues, "host_binding.");
	const key = optionalString(value, "key", issues, "host_binding.");
	const taskKey = optionalString(value, "task_key", issues, "host_binding.");
	const runId = optionalString(value, "run_id", issues, "host_binding.");
	const version = requiredString(value, "binding_version", issues, gaps, "host_binding.");
	const observedAt = value.observed_at;
	if (!isoTimestamp(observedAt)) {
		issues.push(issue("host_binding.observed_at", "must be an ISO timestamp with timezone"));
		gaps.push("host_binding.observed_at");
	}
	if (issues.length || role === undefined || version === undefined || !isoTimestamp(observedAt)) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		role,
		...(owner === undefined ? {} : { owner }),
		...(claimId === undefined ? {} : { claim_id: claimId }),
		...(key === undefined ? {} : { key }),
		...(taskKey === undefined ? {} : { task_key: taskKey }),
		...(runId === undefined ? {} : { run_id: runId }),
		binding_version: version,
		observed_at: observedAt,
	});
}

// ── DecisionRef: discriminated DP | local ──────────────────────────────────

export interface DpDecisionRef {
	kind: "dp";
	decision_id: string;
}

export interface LocalDecisionRef {
	kind: "local";
	local_ref: string;
}

export type DecisionRef = DpDecisionRef | LocalDecisionRef;

export function isDecisionRef(value: unknown): value is DecisionRef {
	if (!isRecord(value)) return false;
	if (value.kind === "dp") return nonblank(value.decision_id) && Object.keys(value).length === 2;
	if (value.kind === "local") return nonblank(value.local_ref) && Object.keys(value).length === 2;
	return false;
}

export function parseDecisionRef(value: unknown): ContractValidation<DecisionRef> {
	const layer = "decision-ref-schema";
	if (!isDecisionRef(value)) {
		return rejected(
			layer,
			[issue("decision_ref", "must be {kind:'dp',decision_id} or {kind:'local',local_ref}")],
			["decision_ref"],
		);
	}
	return accepted(
		layer,
		value.kind === "dp"
			? { kind: "dp", decision_id: value.decision_id }
			: {
					kind: "local",
					local_ref: value.local_ref,
				},
	);
}

// ── Feedback (`design.md` §4.1) ────────────────────────────────────────────

export interface FeedbackEnvelope {
	/** Host-minted reference for this feedback record (never model-generated). */
	feedback_ref: string;
	matter_ref?: string;
	origin?: string;
	stage?: string;
	evidence_refs?: string[];
}

export interface FeedbackInput {
	envelope: FeedbackEnvelope;
	/** Trusted host snapshot; the untrusted observation is `raw`. */
	host: HostFacts;
	/** Verbatim, untrusted observation (transport reply / CLI / UI / worker). */
	raw: unknown;
}

export interface DecisionFeedback {
	schema_version: SchemaVersion;
	feedback_ref: string;
	matter_ref?: string;
	origin?: string;
	stage?: string;
	evidence_refs?: string[];
	category: FeedbackCategory;
	/** Verbatim reason text. Never truncated, even for oversize transport. */
	raw_reason?: string;
	/** Full untrusted payload when it is a JSON value; verbatim, not truncated. */
	raw_payload?: JsonValue;
	escalated_reason?: string;
	disable_scope?: string;
	confidence?: number;
	/** From `host.binding` only, never from a model `owner` field. */
	owner?: string;
	/** The available trusted binding snapshot; absent when host cannot supply. */
	binding?: HostBinding;
	/** Names of missing/unknowable fields, never guessed values. */
	gaps?: string[];
	effect_state: EffectState;
	stop_scope: StopScope;
	stop_signal_ref?: string;
	authority_fact?: AuthorityFact;
	exemption_fact?: ExemptionFact;
	budget_fact?: BudgetExhaustionFact;
	transport_oversize?: boolean;
	/** Model text claims (p0 / authority / stop) preserved by name, never
	 *  promoted to host facts, external authority or a global stop. */
	untrusted_signals?: string[];
}

const AUTHORITY_FACT_FIELDS = ["policy_ref", "condition"] as const;
const EXEMPTION_FACT_FIELDS = ["config_ref", "kind"] as const;
const BUDGET_FACT_FIELDS = ["budget_ref", "scope"] as const;

function stringField(obj: Record<string, unknown>, key: string): string | undefined {
	const value = obj[key];
	return nonblank(value) ? value : undefined;
}

function booleanField(obj: Record<string, unknown>, key: string): boolean | undefined {
	const value = obj[key];
	return typeof value === "boolean" ? value : undefined;
}

function numberField(obj: Record<string, unknown>, key: string): number | undefined {
	const value = obj[key];
	return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function extractRawReason(raw: Record<string, unknown> | undefined, original: unknown): string | undefined {
	if (raw) {
		for (const key of ["raw_reason", "unavailable", "error", "message", "escalated_reason"]) {
			const value = stringField(raw, key);
			if (value !== undefined) return value;
		}
	}
	return typeof original === "string" && original !== "" ? original : undefined;
}

function extractUntrustedSignals(raw: Record<string, unknown> | undefined): string[] {
	if (!raw) return [];
	const signals: string[] = [];
	if (
		booleanField(raw, "authority_required") === true ||
		booleanField(raw, "p0") === true ||
		stringField(raw, "over_authority") !== undefined ||
		stringField(raw, "escalated_reason")?.toLowerCase().includes("authority") === true
	) {
		signals.push("authority-claim");
	}
	if (stringField(raw, "stop") !== undefined || booleanField(raw, "aborted") === true) signals.push("stop-claim");
	if (stringField(raw, "owner") !== undefined) signals.push("owner-self-report");
	if (stringField(raw, "role") !== undefined) signals.push("role-self-report");
	return signals;
}

/** Classify ANY feedback. Reception requires only a real input/error plus the
 *  owner/matter clues the host actually has; it never requires a legal claim or
 *  a complete business envelope (design §4.3 layer 1).
 *
 *  Host facts dominate model text: `authority-required`, `exemption`,
 *  `cancelled`, `budget-exhausted` and `user-global` can only come from
 *  `HostFacts`. A service timeout stays `service-request`; p0 text stays an
 *  untrusted signal. Unknown reasons keep their raw text and are `unclassified`,
 *  never folded into `authority-required`. */
export function classifyDecisionFeedback(input: FeedbackInput): DecisionFeedback {
	const raw = isRecord(input.raw) ? input.raw : undefined;
	const host = input.host;
	const binding = host.binding;
	const reason = extractRawReason(raw, input.raw);
	/** Frozen transport reason (`unavailable`) is the classification key even
	 *  when `raw_reason` holds a long untruncated original text. */
	const transportReason = raw ? stringField(raw, "unavailable") : undefined;
	const mappedReason = transportReason ?? reason;
	const rawPayload = isJsonValue(input.raw) ? input.raw : undefined;
	const escalated = raw ? stringField(raw, "escalated_reason") : undefined;
	const disableScope = raw ? stringField(raw, "disable_scope") : undefined;
	const confidence = raw ? numberField(raw, "confidence") : undefined;
	const missingFields = raw && nonblankStringArray(raw.missing_fields) ? raw.missing_fields : [];
	const transportOversize =
		(raw && (booleanField(raw, "transport_oversize") === true || booleanField(raw, "input_oversize") === true)) ===
			true || mappedReason === "input-oversize";
	const untrustedSignals = extractUntrustedSignals(raw);
	const effectUnknown =
		host.effect_unknown !== undefined ||
		(raw && (stringField(raw, "effect_state") === "unknown" || stringField(raw, "side_effect") === "unknown")) ===
			true;

	const roleClaim = raw ? stringField(raw, "role") : undefined;
	const ownerClaim = raw ? stringField(raw, "owner") : undefined;
	const versionClaim = raw ? stringField(raw, "binding_version") : undefined;
	const bindingDrift =
		(roleClaim !== undefined && roleClaim !== binding.role) ||
		(ownerClaim !== undefined && ownerClaim !== binding.owner) ||
		(versionClaim !== undefined && versionClaim !== binding.binding_version);

	// Host stop/budget facts are ranked by their REAL scope, never by array
	// order. A user-global / pm-or-key / matter / current-worker-run stop is a
	// real stop and cannot be masked by a service timeout, exemption or
	// authority diagnostic. A service-only failure never becomes a global PM
	// stop. Exemption/authority stay diagnostics, outranked by real stops.
	const dominantStop = dominantHostStop(host);
	const realStop =
		dominantStop !== undefined && STOP_SCOPE_RANK[dominantStop.scope] >= STOP_SCOPE_RANK["worker-run"]
			? dominantStop
			: undefined;
	const serviceStop =
		dominantStop !== undefined && realStop === undefined && dominantStop.scope !== "none" ? dominantStop : undefined;

	let category: FeedbackCategory;
	let stopScope: StopScope = "none";
	let stopSignalRef: string | undefined;
	let authorityFact: AuthorityFact | undefined;
	let exemptionFact: ExemptionFact | undefined;
	let budgetFactOut: BudgetExhaustionFact | undefined;

	if (realStop) {
		category = realStop.category;
		stopScope = realStop.scope;
		stopSignalRef = realStop.signal_ref;
		budgetFactOut = realStop.budget_fact;
	} else if (host.authority_gap) {
		category = "authority-required";
		stopScope = "matter";
		authorityFact = host.authority_gap;
	} else if (host.exemption) {
		category = "exemption";
		stopScope = "none";
		exemptionFact = host.exemption;
	} else if (serviceStop) {
		category = serviceStop.category;
		stopScope = serviceStop.scope;
		stopSignalRef = serviceStop.signal_ref;
		budgetFactOut = serviceStop.budget_fact;
	} else if (host.effect_unknown || effectUnknown) {
		category = "effect-unknown";
		stopScope = "none";
	} else if (bindingDrift) {
		category = "binding-invalid";
		stopScope = "none";
	} else if (!raw && typeof input.raw !== "string") {
		category = "integrity-error";
		stopScope = "unknown";
	} else if (raw && Object.hasOwn(raw, "available") && typeof raw.available !== "boolean") {
		category = "integrity-error";
		stopScope = "unknown";
	} else if (raw?.available === true) {
		const contradictory = reason !== undefined || !isRecord(raw.answers) || !nonblank(raw.decision_id);
		if (contradictory) {
			category = "integrity-error";
			stopScope = "unknown";
		} else if (booleanField(raw, "low_confidence") === true) {
			category = "uncertain-answer";
			stopScope = "none";
		} else {
			category = stringField(raw, "mode") === "suggest" ? "advisory" : "answer";
			stopScope = "none";
		}
	} else if (raw?.available === false) {
		const mapped = transportCategoryFor(mappedReason);
		if (effectUnknown) {
			category = "effect-unknown";
			stopScope = "none";
		} else if (mapped === undefined) {
			category = "unclassified";
			stopScope = "unknown";
		} else {
			category = mapped;
			if (mapped === "budget-exhausted") stopScope = "service-request";
			else if (
				mapped === "service-unavailable" &&
				mappedReason !== undefined &&
				SERVICE_REQUEST_REASONS.has(mappedReason)
			)
				stopScope = "service-request";
			else stopScope = "none";
		}
	} else if (raw && (nonblank(raw.decision_id) || isRecord(raw.answers))) {
		category = "integrity-error";
		stopScope = "unknown";
	} else {
		const mapped = transportCategoryFor(mappedReason);
		if (mapped === undefined) {
			category = "unclassified";
			stopScope = "unknown";
		} else {
			category = mapped;
			if (mapped === "budget-exhausted") stopScope = "service-request";
			else if (
				mapped === "service-unavailable" &&
				mappedReason !== undefined &&
				SERVICE_REQUEST_REASONS.has(mappedReason)
			)
				stopScope = "service-request";
			else stopScope = "none";
		}
	}

	// A trusted/real unknown effect dominates an untrusted raw
	// `effect_state: "known"`. The contradictory payload is preserved verbatim
	// in `raw_payload`; a model "known" claim is only an untrusted signal and
	// never waives reconciliation. Output can never be category=effect-unknown
	// with effect_state=known.
	const rawEffectKnownClaim = stringField(raw ?? {}, "effect_state") === "known";
	const unknownEffectRequired =
		effectUnknown ||
		category === "effect-unknown" ||
		category === "cancelled" ||
		category === "unclassified" ||
		category === "integrity-error";
	if (rawEffectKnownClaim) untrustedSignals.push("effect-known-claim");
	const effectState: EffectState = unknownEffectRequired ? "unknown" : rawEffectKnownClaim ? "known" : "none";

	const gaps: string[] = [...missingFields];
	if (input.envelope.matter_ref === undefined) gaps.push("matter_ref");
	if (input.envelope.origin === undefined) gaps.push("origin");
	if (input.envelope.stage === undefined) gaps.push("stage");
	if (binding.owner === undefined) gaps.push("owner");
	if (binding.role === "unknown") gaps.push("binding.role");
	if (reason === undefined) gaps.push("raw_reason");
	if (transportOversize) gaps.push("transport.oversize");

	return {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		feedback_ref: input.envelope.feedback_ref,
		...(input.envelope.matter_ref === undefined ? {} : { matter_ref: input.envelope.matter_ref }),
		...(input.envelope.origin === undefined ? {} : { origin: input.envelope.origin }),
		...(input.envelope.stage === undefined ? {} : { stage: input.envelope.stage }),
		...(input.envelope.evidence_refs === undefined ? {} : { evidence_refs: input.envelope.evidence_refs }),
		category,
		...(reason === undefined ? {} : { raw_reason: reason }),
		...(rawPayload === undefined ? {} : { raw_payload: rawPayload }),
		...(escalated === undefined ? {} : { escalated_reason: escalated }),
		...(disableScope === undefined ? {} : { disable_scope: disableScope }),
		...(confidence === undefined ? {} : { confidence }),
		...(binding.owner === undefined ? {} : { owner: binding.owner }),
		binding,
		...(gaps.length ? { gaps } : {}),
		effect_state: effectState,
		stop_scope: stopScope,
		...(stopSignalRef === undefined ? {} : { stop_signal_ref: stopSignalRef }),
		...(authorityFact === undefined ? {} : { authority_fact: authorityFact }),
		...(exemptionFact === undefined ? {} : { exemption_fact: exemptionFact }),
		...(budgetFactOut === undefined ? {} : { budget_fact: budgetFactOut }),
		...(transportOversize ? { transport_oversize: true } : {}),
		...(untrustedSignals.length ? { untrusted_signals: untrustedSignals } : {}),
	};
}

const FEEDBACK_FIELDS = [
	"schema_version",
	"feedback_ref",
	"matter_ref",
	"origin",
	"stage",
	"evidence_refs",
	"category",
	"raw_reason",
	"raw_payload",
	"escalated_reason",
	"disable_scope",
	"confidence",
	"owner",
	"binding",
	"gaps",
	"effect_state",
	"stop_scope",
	"stop_signal_ref",
	"authority_fact",
	"exemption_fact",
	"budget_fact",
	"transport_oversize",
	"untrusted_signals",
] as const;

/** Pure shape check of an untrusted `DecisionFeedback` JSON value. Success
 *  means "well-formed v1 shape", NOT "verified host source". */
export function parseDecisionFeedback(value: unknown): ContractValidation<DecisionFeedback> {
	const layer = "feedback-schema";
	if (!isRecord(value)) return rejected(layer, [issue("feedback", "must be an object")], ["feedback"]);
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	checkDeclaredKeys(value, FEEDBACK_FIELDS, issues, "feedback.");
	if (value.schema_version !== DECISION_HANDOFF_SCHEMA_VERSION) {
		issues.push(issue("feedback.schema_version", "must be 1"));
	}
	const feedbackRef = requiredString(value, "feedback_ref", issues, gaps, "feedback.");
	const matterRef = optionalString(value, "matter_ref", issues, "feedback.");
	const origin = optionalString(value, "origin", issues, "feedback.");
	const stage = optionalString(value, "stage", issues, "feedback.");
	const evidenceRefs = optionalStringArray(value, "evidence_refs", issues, "feedback.");
	const rawReason = optionalString(value, "raw_reason", issues, "feedback.");
	const escalated = optionalString(value, "escalated_reason", issues, "feedback.");
	const disableScope = optionalString(value, "disable_scope", issues, "feedback.");
	const stopSignalRef = optionalString(value, "stop_signal_ref", issues, "feedback.");
	const gapsOut = optionalStringArray(value, "gaps", issues, "feedback.");
	const untrusted = optionalStringArray(value, "untrusted_signals", issues, "feedback.");
	const owner = optionalString(value, "owner", issues, "feedback.");
	if (value.raw_payload !== undefined && !isJsonValue(value.raw_payload)) {
		issues.push(issue("feedback.raw_payload", "must be a JSON value"));
	}
	if (value.confidence !== undefined && !finiteAtLeast(value.confidence, 0)) {
		issues.push(issue("feedback.confidence", "must be a finite number"));
	}
	if (value.transport_oversize !== undefined && typeof value.transport_oversize !== "boolean") {
		issues.push(issue("feedback.transport_oversize", "must be a boolean"));
	}
	if (!(FEEDBACK_CATEGORIES as readonly string[]).includes(value.category as string)) {
		issues.push(issue("feedback.category", "unknown category"));
	}
	if (!(EFFECT_STATES as readonly string[]).includes(value.effect_state as string)) {
		issues.push(issue("feedback.effect_state", "unknown effect_state"));
	}
	if (!(STOP_SCOPES as readonly string[]).includes(value.stop_scope as string)) {
		issues.push(issue("feedback.stop_scope", "unknown stop_scope"));
	}
	if (value.binding !== undefined) {
		const parsed = parseHostBinding(value.binding);
		if (!parsed.ok) issues.push(...parsed.issues.map((item) => issue(`feedback.${item.field}`, item.rule)));
	}
	for (const [key, fields] of [
		["authority_fact", AUTHORITY_FACT_FIELDS],
		["exemption_fact", EXEMPTION_FACT_FIELDS],
		["budget_fact", BUDGET_FACT_FIELDS],
	] as const) {
		const fact = value[key];
		if (fact === undefined) continue;
		if (!isRecord(fact) || Object.keys(fact).some((field) => !(fields as readonly string[]).includes(field))) {
			issues.push(issue(`feedback.${key}`, "unknown host fact field"));
			continue;
		}
		if (!fields.every((field) => nonblank(fact[field]))) {
			issues.push(issue(`feedback.${key}`, "incomplete host fact"));
		}
		if (
			key === "exemption_fact" &&
			fact.kind !== "signoff-disabled" &&
			fact.kind !== "dp-disabled" &&
			fact.kind !== "transport-unconfigured"
		) {
			issues.push(issue("feedback.exemption_fact.kind", "unknown exemption kind"));
		}
		if (key === "budget_fact" && fact.scope !== "service" && fact.scope !== "task") {
			issues.push(issue("feedback.budget_fact.scope", "unknown budget scope"));
		}
	}
	if (issues.length || feedbackRef === undefined) return rejected(layer, issues, gaps);
	return accepted(layer, {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		feedback_ref: feedbackRef,
		...(matterRef === undefined ? {} : { matter_ref: matterRef }),
		...(origin === undefined ? {} : { origin }),
		...(stage === undefined ? {} : { stage }),
		...(evidenceRefs === undefined ? {} : { evidence_refs: evidenceRefs }),
		category: value.category as FeedbackCategory,
		...(rawReason === undefined ? {} : { raw_reason: rawReason }),
		...(value.raw_payload === undefined ? {} : { raw_payload: value.raw_payload as JsonValue }),
		...(escalated === undefined ? {} : { escalated_reason: escalated }),
		...(disableScope === undefined ? {} : { disable_scope: disableScope }),
		...(value.confidence === undefined ? {} : { confidence: value.confidence as number }),
		...(owner === undefined ? {} : { owner }),
		...(value.binding === undefined ? {} : { binding: value.binding as HostBinding }),
		...(gapsOut === undefined ? {} : { gaps: gapsOut }),
		effect_state: value.effect_state as EffectState,
		stop_scope: value.stop_scope as StopScope,
		...(stopSignalRef === undefined ? {} : { stop_signal_ref: stopSignalRef }),
		...(value.authority_fact === undefined ? {} : { authority_fact: value.authority_fact as AuthorityFact }),
		...(value.exemption_fact === undefined ? {} : { exemption_fact: value.exemption_fact as ExemptionFact }),
		...(value.budget_fact === undefined ? {} : { budget_fact: value.budget_fact as BudgetExhaustionFact }),
		...(value.transport_oversize === undefined ? {} : { transport_oversize: value.transport_oversize as boolean }),
		...(untrusted === undefined ? {} : { untrusted_signals: untrusted }),
	});
}

// ── PM disposition (`design.md` §4.2, §4.3 layer 2) ───────────────────────

export interface DispositionAction {
	tool: ToolName;
	scope_ref: string;
	read_only: boolean;
}

/** Host-declared legal tool scope for one disposition (whitelist + write face). */
export interface ToolScope {
	tools: readonly ToolName[];
	scope_ref: string;
	read_only: boolean;
}

export interface PmDisposition {
	schema_version: SchemaVersion;
	disposition_ref: string;
	feedback_ref: string;
	matter_ref: string;
	kind: PmDispositionKind;
	/** From the trusted host snapshot, never model self-report. */
	owner: string;
	binding: HostBinding;
	goal_ref: string;
	gap_refs: string[];
	basis_refs?: string[];
	planned_action: DispositionAction;
	expected_result: string;
	result_consumer: string;
	budget_ref: string;
	status: PmDispositionStatus;
}

export interface CollectEvidenceInput {
	disposition_ref: string;
	feedback_ref: string;
	matter_ref: string;
	goal_ref: string;
	host: HostFacts;
	tool_scope: unknown;
	planned_action: unknown;
	gap_refs: unknown;
	basis_refs?: unknown;
	expected_result: string;
	result_consumer: string;
	/** Parent matter budget. A complete business basis_catalog is NOT required. */
	budget: unknown;
}

const DISPOSITION_ACTION_FIELDS = ["tool", "scope_ref", "read_only"] as const;
const TOOL_SCOPE_FIELDS = ["tools", "scope_ref", "read_only"] as const;

function parseDispositionAction(
	value: unknown,
	issues: ContractIssue[],
	prefix: string,
): DispositionAction | undefined {
	const local: ContractIssue[] = [];
	if (!isRecord(value)) {
		issues.push(issue(prefix, "must be an object"));
		return undefined;
	}
	checkDeclaredKeys(value, DISPOSITION_ACTION_FIELDS, local, `${prefix}.`);
	if (!(TOOL_NAMES as readonly string[]).includes(value.tool as string)) {
		local.push(issue(`${prefix}.tool`, "unknown tool"));
	}
	if (!nonblank(value.scope_ref)) local.push(issue(`${prefix}.scope_ref`, "missing or blank"));
	if (typeof value.read_only !== "boolean") local.push(issue(`${prefix}.read_only`, "must be a boolean"));
	issues.push(...local);
	if (local.length) return undefined;
	return { tool: value.tool as ToolName, scope_ref: value.scope_ref as string, read_only: value.read_only as boolean };
}

function parseToolScope(value: unknown, issues: ContractIssue[], prefix: string): ToolScope | undefined {
	const local: ContractIssue[] = [];
	if (!isRecord(value)) {
		issues.push(issue(prefix, "must be an object"));
		return undefined;
	}
	checkDeclaredKeys(value, TOOL_SCOPE_FIELDS, local, `${prefix}.`);
	if (
		!Array.isArray(value.tools) ||
		!value.tools.length ||
		!(value.tools as unknown[]).every((tool) => (TOOL_NAMES as readonly string[]).includes(tool as string))
	) {
		local.push(issue(`${prefix}.tools`, "must be a non-empty array of known tools"));
	}
	if (!nonblank(value.scope_ref)) local.push(issue(`${prefix}.scope_ref`, "missing or blank"));
	if (typeof value.read_only !== "boolean") local.push(issue(`${prefix}.read_only`, "must be a boolean"));
	issues.push(...local);
	if (local.length) return undefined;
	return {
		tools: value.tools as ToolName[],
		scope_ref: value.scope_ref as string,
		read_only: value.read_only as boolean,
	};
}

/** Layer 2: collect-evidence / coordination. Requires a legal host owner,
 *  a known goal, a legal tool scope and a parent budget. It deliberately does
 *  NOT require complete business material/preparation/basis — a missing final
 *  conclusion envelope never forbids ordinary evidence collection (§4.3). */
export function validateCollectEvidenceDisposition(input: CollectEvidenceInput): ContractValidation<PmDisposition> {
	const layer = "collect-evidence";
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	const dispositionRef = requiredString({ disposition_ref: input.disposition_ref }, "disposition_ref", issues, gaps);
	const feedbackRef = requiredString({ feedback_ref: input.feedback_ref }, "feedback_ref", issues, gaps);
	const matterRef = requiredString({ matter_ref: input.matter_ref }, "matter_ref", issues, gaps);
	const goalRef = requiredString({ goal_ref: input.goal_ref }, "goal_ref", issues, gaps);
	const expected = requiredString({ expected_result: input.expected_result }, "expected_result", issues, gaps);
	const consumer = requiredString({ result_consumer: input.result_consumer }, "result_consumer", issues, gaps);

	const bindingResult = parseHostBinding(input.host.binding);
	if (!bindingResult.ok) issues.push(...bindingResult.issues);
	const binding = bindingResult.ok ? bindingResult.value : undefined;
	if (binding && binding.role !== "pm")
		issues.push(issue("host.binding.role", "PM disposition requires host role pm"));
	if (binding && binding.owner === undefined) {
		issues.push(issue("host.binding.owner", "legal host owner required"));
		gaps.push("host.binding.owner");
	}
	const collectStop = newWorkStop(input.host);
	if (collectStop) {
		issues.push(
			issue("host.stop_signals", `host ${collectStop.scope} stop forbids a new collect-evidence disposition`),
		);
	}
	if (!nonblankStringArray(input.gap_refs) || (input.gap_refs as string[]).length === 0) {
		issues.push(issue("gap_refs", "at least one known gap reference required"));
		gaps.push("gap_refs");
	}
	const basisRefs = input.basis_refs === undefined ? undefined : input.basis_refs;
	if (basisRefs !== undefined && !nonblankStringArray(basisRefs)) {
		issues.push(issue("basis_refs", "must be an array of nonblank strings"));
	}
	const toolScope = parseToolScope(input.tool_scope, issues, "tool_scope");
	const action = parseDispositionAction(input.planned_action, issues, "planned_action");
	if (toolScope && action) {
		if (!toolScope.tools.includes(action.tool)) {
			issues.push(issue("planned_action.tool", "tool is outside the host-declared tool scope"));
		}
		if (toolScope.scope_ref !== action.scope_ref) {
			issues.push(issue("planned_action.scope_ref", "must equal the host-declared tool scope ref"));
		}
		if (toolScope.read_only && !READ_ONLY_TOOLS.includes(action.tool)) {
			issues.push(issue("planned_action.tool", "read-only tool scope forbids this tool"));
		}
		if (action.read_only && !READ_ONLY_TOOLS.includes(action.tool)) {
			issues.push(issue("planned_action.read_only", "inconsistent with the selected tool"));
		}
	}
	const budgetResult = validateMatterBudget(input.budget);
	if (!budgetResult.ok) {
		issues.push(...budgetResult.issues.map((item) => issue(`budget.${item.field}`, item.rule)));
		gaps.push(...budgetResult.gaps.map((gap) => `budget.${gap}`));
	}
	const budget = budgetResult.ok ? budgetResult.value : undefined;
	if (budget && budget.matter_ref !== matterRef) {
		issues.push(issue("budget.matter_ref", "parent budget must belong to the same matter"));
	}

	if (
		issues.length ||
		dispositionRef === undefined ||
		feedbackRef === undefined ||
		matterRef === undefined ||
		goalRef === undefined ||
		expected === undefined ||
		consumer === undefined ||
		binding === undefined ||
		toolScope === undefined ||
		action === undefined ||
		budget === undefined
	) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		disposition_ref: dispositionRef,
		feedback_ref: feedbackRef,
		matter_ref: matterRef,
		kind: "collect-evidence",
		owner: binding.owner as string,
		binding,
		goal_ref: goalRef,
		gap_refs: input.gap_refs as string[],
		...(basisRefs === undefined ? {} : { basis_refs: basisRefs as string[] }),
		planned_action: action,
		expected_result: expected,
		result_consumer: consumer,
		budget_ref: budget.budget_ref,
		status: "planned",
	});
}

const PM_DISPOSITION_FIELDS = [
	"schema_version",
	"disposition_ref",
	"feedback_ref",
	"matter_ref",
	"kind",
	"owner",
	"binding",
	"goal_ref",
	"gap_refs",
	"basis_refs",
	"planned_action",
	"expected_result",
	"result_consumer",
	"budget_ref",
	"status",
] as const;

export function parsePmDisposition(value: unknown): ContractValidation<PmDisposition> {
	const layer = "pm-disposition-schema";
	if (!isRecord(value)) return rejected(layer, [issue("disposition", "must be an object")], ["disposition"]);
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	checkDeclaredKeys(value, PM_DISPOSITION_FIELDS, issues, "disposition.");
	if (value.schema_version !== DECISION_HANDOFF_SCHEMA_VERSION)
		issues.push(issue("disposition.schema_version", "must be 1"));
	const dispositionRef = requiredString(value, "disposition_ref", issues, gaps, "disposition.");
	const feedbackRef = requiredString(value, "feedback_ref", issues, gaps, "disposition.");
	const matterRef = requiredString(value, "matter_ref", issues, gaps, "disposition.");
	const owner = requiredString(value, "owner", issues, gaps, "disposition.");
	const goalRef = requiredString(value, "goal_ref", issues, gaps, "disposition.");
	const expected = requiredString(value, "expected_result", issues, gaps, "disposition.");
	const consumer = requiredString(value, "result_consumer", issues, gaps, "disposition.");
	const budgetRef = requiredString(value, "budget_ref", issues, gaps, "disposition.");
	const gapRefs = optionalStringArray(value, "gap_refs", issues, "disposition.");
	const basisRefs = optionalStringArray(value, "basis_refs", issues, "disposition.");
	if (!nonblankStringArray(value.gap_refs)) issues.push(issue("disposition.gap_refs", "required string array"));
	if (!(PM_DISPOSITION_KINDS as readonly string[]).includes(value.kind as string))
		issues.push(issue("disposition.kind", "unknown kind"));
	if (!(PM_DISPOSITION_STATUSES as readonly string[]).includes(value.status as string))
		issues.push(issue("disposition.status", "unknown status"));
	if (value.binding !== undefined) {
		const parsed = parseHostBinding(value.binding);
		if (!parsed.ok) issues.push(...parsed.issues.map((item) => issue(`disposition.${item.field}`, item.rule)));
	} else {
		issues.push(issue("disposition.binding", "required"));
	}
	const action = parseDispositionAction(value.planned_action, issues, "disposition.planned_action");
	if (
		issues.length ||
		dispositionRef === undefined ||
		feedbackRef === undefined ||
		matterRef === undefined ||
		owner === undefined ||
		goalRef === undefined ||
		expected === undefined ||
		consumer === undefined ||
		budgetRef === undefined ||
		action === undefined
	) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		disposition_ref: dispositionRef,
		feedback_ref: feedbackRef,
		matter_ref: matterRef,
		kind: value.kind as PmDispositionKind,
		owner,
		binding: value.binding as HostBinding,
		goal_ref: goalRef,
		gap_refs: gapRefs ?? (value.gap_refs as string[]),
		...(basisRefs === undefined ? {} : { basis_refs: basisRefs }),
		planned_action: action,
		expected_result: expected,
		result_consumer: consumer,
		budget_ref: budgetRef,
		status: value.status as PmDispositionStatus,
	});
}

// ── Layered business material (`design.md` §4.3 layer 3) ───────────────────

export interface MaterialEnvelope {
	material_ref: string;
	fields: Record<string, JsonValue>;
	digest: string;
	evidence_refs: string[];
}

export interface BasisCatalogEntry {
	id: string;
	text: string;
	material_refs: string[];
	applies_to: string[];
}

export interface PreparationEnvelope {
	prepared_at: string;
	digest: string;
	basis_catalog: BasisCatalogEntry[];
}

export interface CandidateEnvelope {
	version: string;
	ids: string[];
}

const MATERIAL_FIELDS = ["material_ref", "fields", "digest", "evidence_refs"] as const;
const BASIS_ITEM_FIELDS = ["id", "text", "material_refs", "applies_to"] as const;
const PREPARATION_FIELDS = ["prepared_at", "digest", "basis_catalog"] as const;
const CANDIDATE_FIELDS = ["version", "ids"] as const;

function parseMaterialEnvelope(value: unknown, issues: ContractIssue[], gaps: string[]): MaterialEnvelope | undefined {
	if (!isRecord(value)) {
		issues.push(issue("material", "complete applicable business material required"));
		gaps.push("material");
		return undefined;
	}
	checkDeclaredKeys(value, MATERIAL_FIELDS, issues, "material.");
	const materialRef = requiredString(value, "material_ref", issues, gaps, "material.");
	const digest = requiredString(value, "digest", issues, gaps, "material.");
	if (!isRecord(value.fields) || !Object.keys(value.fields).length || !isJsonValue(value.fields)) {
		issues.push(issue("material.fields", "non-empty JSON object of applicable fields required"));
		gaps.push("material.fields");
	}
	if (!nonblankStringArray(value.evidence_refs) || !(value.evidence_refs as string[]).length) {
		issues.push(issue("material.evidence_refs", "at least one trusted evidence reference required"));
		gaps.push("material.evidence_refs");
	}
	if (issues.length || materialRef === undefined || digest === undefined) return undefined;
	return {
		material_ref: materialRef,
		fields: value.fields as Record<string, JsonValue>,
		digest,
		evidence_refs: value.evidence_refs as string[],
	};
}

function parsePreparationEnvelope(
	value: unknown,
	issues: ContractIssue[],
	gaps: string[],
): PreparationEnvelope | undefined {
	if (!isRecord(value)) {
		issues.push(issue("preparation", "independently prepared basis required"));
		gaps.push("preparation");
		return undefined;
	}
	checkDeclaredKeys(value, PREPARATION_FIELDS, issues, "preparation.");
	const digest = requiredString(value, "digest", issues, gaps, "preparation.");
	const preparedAt = value.prepared_at;
	if (!isoTimestamp(preparedAt)) {
		issues.push(issue("preparation.prepared_at", "must be an ISO timestamp with timezone"));
		gaps.push("preparation.prepared_at");
	}
	if (!Array.isArray(value.basis_catalog) || !value.basis_catalog.length) {
		issues.push(issue("preparation.basis_catalog", "non-empty basis_catalog required"));
		gaps.push("preparation.basis_catalog");
		return undefined;
	}
	const ids = new Set<string>();
	const catalog: BasisCatalogEntry[] = [];
	for (const [index, item] of value.basis_catalog.entries()) {
		const prefix = `preparation.basis_catalog[${index}]`;
		if (!isRecord(item)) {
			issues.push(issue(prefix, "must be a basis object"));
			continue;
		}
		checkDeclaredKeys(item, BASIS_ITEM_FIELDS, issues, `${prefix}.`);
		const id = requiredString(item, "id", issues, gaps, `${prefix}.`);
		const text = requiredString(item, "text", issues, gaps, `${prefix}.`);
		if (!nonblankStringArray(item.material_refs) || !(item.material_refs as string[]).length) {
			issues.push(issue(`${prefix}.material_refs`, "non-empty material_refs required"));
			gaps.push(`${prefix}.material_refs`);
		}
		if (!nonblankStringArray(item.applies_to) || !(item.applies_to as string[]).length) {
			issues.push(issue(`${prefix}.applies_to`, "non-empty applies_to required"));
			gaps.push(`${prefix}.applies_to`);
		}
		if (id !== undefined) {
			if (ids.has(id)) issues.push(issue(`${prefix}.id`, "duplicate basis id"));
			ids.add(id);
		}
		if (
			id !== undefined &&
			text !== undefined &&
			nonblankStringArray(item.material_refs) &&
			nonblankStringArray(item.applies_to)
		) {
			catalog.push({ id, text, material_refs: item.material_refs, applies_to: item.applies_to });
		}
	}
	if (issues.length || digest === undefined || !isoTimestamp(preparedAt) || !catalog.length) return undefined;
	return { prepared_at: preparedAt, digest, basis_catalog: catalog };
}

function parseCandidateEnvelope(
	value: unknown,
	issues: ContractIssue[],
	gaps: string[],
): CandidateEnvelope | undefined {
	if (!isRecord(value)) {
		issues.push(issue("candidates", "current candidate set required"));
		gaps.push("candidates");
		return undefined;
	}
	checkDeclaredKeys(value, CANDIDATE_FIELDS, issues, "candidates.");
	const version = requiredString(value, "version", issues, gaps, "candidates.");
	if (
		!nonblankStringArray(value.ids) ||
		!(value.ids as string[]).length ||
		new Set(value.ids).size !== value.ids.length
	) {
		issues.push(issue("candidates.ids", "non-empty array of distinct current candidate ids required"));
		gaps.push("candidates.ids");
	}
	if (issues.length || version === undefined) return undefined;
	return { version, ids: value.ids as string[] };
}

// ── Local selection / execution records (`design.md` §4.4) ─────────────────

/** A selection is a PLAN, not an execution: `action_state` is `planned`,
 *  `business_completed` is false, and it carries NO action/result facts. */
export interface LocalSelectionRecordV1 {
	schema_version: SchemaVersion;
	kind: "local-selection";
	origin: "local-decision";
	source: LocalSource;
	local_ref: string;
	/** A real parent DP is referenced only by this separate discriminated ref. */
	parent_decision_ref?: DpDecisionRef;
	feedback_ref?: string;
	matter_ref: string;
	host_binding: HostBinding;
	matter_version: string;
	material_digest: string;
	basis_digest: string;
	selected_action: string;
	selected_basis_id: string;
	budget_ref: string;
	action_state: "planned";
	business_completed: false;
	result_consumer?: string;
	created_at: string;
}

/** Formed ONLY by the later host writer after an actual tool/dispatch/object
 *  effect and a target verifier. Never from a PM self-report. */
export interface LocalExecutionRecordV1 {
	schema_version: SchemaVersion;
	kind: "local-execution";
	origin: "local-decision";
	source: LocalSource;
	local_ref: string;
	host_binding: HostBinding;
	action_ref: string;
	result_ref: string;
	executor: string;
	target_digest: string;
	observed_effect: string;
	effect_state: "known" | "unknown";
	verified_by: string;
	budget_ref: string;
	created_at: string;
}

export const LOCAL_SELECTION_FIELDS = [
	"schema_version",
	"kind",
	"origin",
	"source",
	"local_ref",
	"parent_decision_ref",
	"feedback_ref",
	"matter_ref",
	"host_binding",
	"matter_version",
	"material_digest",
	"basis_digest",
	"selected_action",
	"selected_basis_id",
	"budget_ref",
	"action_state",
	"business_completed",
	"result_consumer",
	"created_at",
] as const;

export const LOCAL_EXECUTION_FIELDS = [
	"schema_version",
	"kind",
	"origin",
	"source",
	"local_ref",
	"host_binding",
	"action_ref",
	"result_ref",
	"executor",
	"target_digest",
	"observed_effect",
	"effect_state",
	"verified_by",
	"budget_ref",
	"created_at",
] as const;

export interface LocalBusinessSelectionInput {
	local_ref: string;
	source: unknown;
	host: HostFacts;
	feedback_ref?: string;
	parent_decision_ref?: unknown;
	matter_ref: string;
	matter_version: string;
	/** Untrusted shapes go through type guards; `unknown`, never `any`. */
	material: unknown;
	preparation: unknown;
	candidates: unknown;
	selected_action: string;
	selected_basis_id: string;
	budget: unknown;
	result_consumer?: string;
	created_at: string;
}

/** Layer 3: a complete local business selection requires the applicable
 *  complete material, an independently prepared basis catalog, the CURRENT
 *  candidate set, a basis that applies to the chosen action and a valid host
 *  binding. A transport oversize flag is NOT proof of material completeness. */
export function validateLocalBusinessSelection(
	input: LocalBusinessSelectionInput,
): ContractValidation<LocalSelectionRecordV1> {
	const layer = "local-business-selection";
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	const localRef = requiredString({ local_ref: input.local_ref }, "local_ref", issues, gaps);
	const matterRef = requiredString({ matter_ref: input.matter_ref }, "matter_ref", issues, gaps);
	const matterVersion = requiredString({ matter_version: input.matter_version }, "matter_version", issues, gaps);
	const selectedAction = requiredString({ selected_action: input.selected_action }, "selected_action", issues, gaps);
	const selectedBasisId = requiredString(
		{ selected_basis_id: input.selected_basis_id },
		"selected_basis_id",
		issues,
		gaps,
	);
	const feedbackRef = input.feedback_ref;
	if (feedbackRef !== undefined && !nonblank(feedbackRef))
		issues.push(issue("feedback_ref", "must be nonblank when present"));
	const resultConsumer = input.result_consumer;
	if (resultConsumer !== undefined && !nonblank(resultConsumer))
		issues.push(issue("result_consumer", "must be nonblank when present"));
	if (!isoTimestamp(input.created_at)) {
		issues.push(issue("created_at", "must be an ISO timestamp with timezone"));
		gaps.push("created_at");
	}
	if (input.source !== "pm" && input.source !== "worker-local") {
		issues.push(issue("source", "must be pm or worker-local"));
		gaps.push("source");
	}

	const bindingResult = parseHostBinding(input.host.binding);
	if (!bindingResult.ok) issues.push(...bindingResult.issues);
	const binding = bindingResult.ok ? bindingResult.value : undefined;
	if (binding) {
		if (binding.owner === undefined) {
			issues.push(issue("host.binding.owner", "legal host owner required"));
			gaps.push("host.binding.owner");
		}
		if (input.source === "pm" && binding.role !== "pm")
			issues.push(issue("host.binding.role", "pm source requires host role pm"));
		if (
			input.source === "worker-local" &&
			binding.role !== "coding" &&
			binding.role !== "research" &&
			binding.role !== "review"
		) {
			issues.push(issue("host.binding.role", "worker-local source requires a worker role"));
		}
		if (input.source === "pm" && (binding.claim_id === undefined || binding.key === undefined)) {
			issues.push(issue("host.binding", "pm selection requires claim_id and key"));
			gaps.push("host.binding.claim_id", "host.binding.key");
		}
		if (input.source === "worker-local" && (binding.task_key === undefined || binding.run_id === undefined)) {
			issues.push(issue("host.binding", "worker-local selection requires task_key and run_id"));
			gaps.push("host.binding.task_key", "host.binding.run_id");
		}
	}
	if (input.host.authority_gap) {
		issues.push(issue("host.authority_gap", "real external authority gap forbids a local business selection"));
	}
	const selectionStop = newWorkStop(input.host);
	if (selectionStop) {
		issues.push(
			issue("host.stop_signals", `host ${selectionStop.scope} stop forbids a new local business selection`),
		);
	}

	let parentRef: DpDecisionRef | undefined;
	if (input.parent_decision_ref !== undefined) {
		const parsed = parseDecisionRef(input.parent_decision_ref);
		if (!parsed.ok || parsed.value.kind !== "dp") {
			issues.push(issue("parent_decision_ref", "must be a separate {kind:'dp',decision_id} ref, never a local ref"));
		} else {
			parentRef = parsed.value;
		}
	}

	const material = parseMaterialEnvelope(input.material, issues, gaps);
	const preparation = parsePreparationEnvelope(input.preparation, issues, gaps);
	const candidates = parseCandidateEnvelope(input.candidates, issues, gaps);
	if (material && preparation && candidates) {
		if (!candidates.ids.includes(selectedAction ?? "")) {
			issues.push(issue("selected_action", "must name a current candidate id"));
		}
		for (const [index, item] of preparation.basis_catalog.entries()) {
			for (const ref of item.material_refs) {
				if (!Object.hasOwn(material.fields, ref)) {
					issues.push(issue(`preparation.basis_catalog[${index}].material_refs`, `unknown material field ${ref}`));
				}
			}
			for (const target of item.applies_to) {
				if (!candidates.ids.includes(target)) {
					issues.push(issue(`preparation.basis_catalog[${index}].applies_to`, `unknown candidate ${target}`));
				}
			}
		}
		const basis = preparation.basis_catalog.find((item) => item.id === selectedBasisId);
		if (!basis) {
			issues.push(issue("selected_basis_id", "no basis catalog entry with this id"));
		} else if (selectedAction !== undefined && !basis.applies_to.includes(selectedAction)) {
			issues.push(issue("selected_basis_id", "basis does not apply to the selected action"));
		}
	}

	const budgetResult = validateMatterBudget(input.budget);
	if (!budgetResult.ok) {
		issues.push(...budgetResult.issues.map((item) => issue(`budget.${item.field}`, item.rule)));
		gaps.push(...budgetResult.gaps.map((gap) => `budget.${gap}`));
	}
	const budget = budgetResult.ok ? budgetResult.value : undefined;
	if (budget && budget.matter_ref !== matterRef)
		issues.push(issue("budget.matter_ref", "budget must belong to the same matter"));

	if (
		issues.length ||
		localRef === undefined ||
		matterRef === undefined ||
		matterVersion === undefined ||
		selectedAction === undefined ||
		selectedBasisId === undefined ||
		binding === undefined ||
		material === undefined ||
		preparation === undefined ||
		candidates === undefined ||
		budget === undefined ||
		(input.source !== "pm" && input.source !== "worker-local")
	) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		kind: "local-selection",
		origin: "local-decision",
		source: input.source,
		local_ref: localRef,
		...(parentRef === undefined ? {} : { parent_decision_ref: parentRef }),
		...(feedbackRef === undefined ? {} : { feedback_ref: feedbackRef }),
		matter_ref: matterRef,
		host_binding: binding,
		matter_version: matterVersion,
		material_digest: material.digest,
		basis_digest: preparation.digest,
		selected_action: selectedAction,
		selected_basis_id: selectedBasisId,
		budget_ref: budget.budget_ref,
		action_state: "planned",
		business_completed: false,
		...(resultConsumer === undefined ? {} : { result_consumer: resultConsumer }),
		created_at: input.created_at,
	});
}

/** Strict shape check of an untrusted local selection JSON row. Rejects a
 *  selection that smuggles execution facts or any DP field. */
export function parseLocalSelectionRecord(value: unknown): ContractValidation<LocalSelectionRecordV1> {
	const layer = "local-selection-schema";
	if (!isRecord(value)) return rejected(layer, [issue("local_selection", "must be an object")], ["local_selection"]);
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	checkDeclaredKeys(value, LOCAL_SELECTION_FIELDS, issues, "local_selection.");
	if (value.schema_version !== DECISION_HANDOFF_SCHEMA_VERSION)
		issues.push(issue("local_selection.schema_version", "must be 1"));
	if (value.kind !== "local-selection") issues.push(issue("local_selection.kind", "must be local-selection"));
	if (value.origin !== "local-decision") issues.push(issue("local_selection.origin", "must be local-decision"));
	if (value.source !== "pm" && value.source !== "worker-local")
		issues.push(issue("local_selection.source", "unknown source"));
	const localRef = requiredString(value, "local_ref", issues, gaps, "local_selection.");
	const matterRef = requiredString(value, "matter_ref", issues, gaps, "local_selection.");
	const version = requiredString(value, "matter_version", issues, gaps, "local_selection.");
	const materialDigest = requiredString(value, "material_digest", issues, gaps, "local_selection.");
	const basisDigest = requiredString(value, "basis_digest", issues, gaps, "local_selection.");
	const selectedAction = requiredString(value, "selected_action", issues, gaps, "local_selection.");
	const selectedBasisId = requiredString(value, "selected_basis_id", issues, gaps, "local_selection.");
	const budgetRef = requiredString(value, "budget_ref", issues, gaps, "local_selection.");
	const feedbackRef = optionalString(value, "feedback_ref", issues, "local_selection.");
	const resultConsumer = optionalString(value, "result_consumer", issues, "local_selection.");
	if (!isoTimestamp(value.created_at))
		issues.push(issue("local_selection.created_at", "must be an ISO timestamp with timezone"));
	if (value.action_state !== "planned")
		issues.push(issue("local_selection.action_state", "selection must remain planned"));
	if (value.business_completed !== false)
		issues.push(issue("local_selection.business_completed", "selection must be false"));
	if (value.host_binding !== undefined) {
		const parsed = parseHostBinding(value.host_binding);
		if (!parsed.ok) issues.push(...parsed.issues.map((item) => issue(`local_selection.${item.field}`, item.rule)));
	} else {
		issues.push(issue("local_selection.host_binding", "required"));
	}
	if (value.parent_decision_ref !== undefined) {
		const parsed = parseDecisionRef(value.parent_decision_ref);
		if (!parsed.ok || parsed.value.kind !== "dp") {
			issues.push(issue("local_selection.parent_decision_ref", "must be a separate dp ref"));
		}
	}
	if (
		issues.length ||
		localRef === undefined ||
		matterRef === undefined ||
		version === undefined ||
		materialDigest === undefined ||
		basisDigest === undefined ||
		selectedAction === undefined ||
		selectedBasisId === undefined ||
		budgetRef === undefined
	) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		kind: "local-selection",
		origin: "local-decision",
		source: value.source as LocalSource,
		local_ref: localRef,
		...(value.parent_decision_ref === undefined
			? {}
			: { parent_decision_ref: value.parent_decision_ref as DpDecisionRef }),
		...(feedbackRef === undefined ? {} : { feedback_ref: feedbackRef }),
		matter_ref: matterRef,
		host_binding: value.host_binding as HostBinding,
		matter_version: version,
		material_digest: materialDigest,
		basis_digest: basisDigest,
		selected_action: selectedAction,
		selected_basis_id: selectedBasisId,
		budget_ref: budgetRef,
		action_state: "planned",
		business_completed: false,
		...(resultConsumer === undefined ? {} : { result_consumer: resultConsumer }),
		created_at: value.created_at as string,
	});
}

/** Strict shape check of a local execution row. A record without real
 *  action/result refs (i.e. a selection) is rejected. */
export function parseLocalExecutionRecord(value: unknown): ContractValidation<LocalExecutionRecordV1> {
	const layer = "local-execution-schema";
	if (!isRecord(value)) return rejected(layer, [issue("local_execution", "must be an object")], ["local_execution"]);
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	checkDeclaredKeys(value, LOCAL_EXECUTION_FIELDS, issues, "local_execution.");
	if (value.schema_version !== DECISION_HANDOFF_SCHEMA_VERSION)
		issues.push(issue("local_execution.schema_version", "must be 1"));
	if (value.kind !== "local-execution") issues.push(issue("local_execution.kind", "must be local-execution"));
	if (value.origin !== "local-decision") issues.push(issue("local_execution.origin", "must be local-decision"));
	if (value.source !== "pm" && value.source !== "worker-local")
		issues.push(issue("local_execution.source", "unknown source"));
	const localRef = requiredString(value, "local_ref", issues, gaps, "local_execution.");
	const actionRef = requiredString(value, "action_ref", issues, gaps, "local_execution.");
	const resultRef = requiredString(value, "result_ref", issues, gaps, "local_execution.");
	const executor = requiredString(value, "executor", issues, gaps, "local_execution.");
	const targetDigest = requiredString(value, "target_digest", issues, gaps, "local_execution.");
	const observedEffect = requiredString(value, "observed_effect", issues, gaps, "local_execution.");
	const verifiedBy = requiredString(value, "verified_by", issues, gaps, "local_execution.");
	const budgetRef = requiredString(value, "budget_ref", issues, gaps, "local_execution.");
	if (value.effect_state !== "known" && value.effect_state !== "unknown") {
		issues.push(issue("local_execution.effect_state", "must be known or unknown"));
	}
	if (!isoTimestamp(value.created_at))
		issues.push(issue("local_execution.created_at", "must be an ISO timestamp with timezone"));
	if (value.host_binding !== undefined) {
		const parsed = parseHostBinding(value.host_binding);
		if (!parsed.ok) issues.push(...parsed.issues.map((item) => issue(`local_execution.${item.field}`, item.rule)));
	} else {
		issues.push(issue("local_execution.host_binding", "required"));
	}
	if (
		issues.length ||
		localRef === undefined ||
		actionRef === undefined ||
		resultRef === undefined ||
		executor === undefined ||
		targetDigest === undefined ||
		observedEffect === undefined ||
		verifiedBy === undefined ||
		budgetRef === undefined
	) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		kind: "local-execution",
		origin: "local-decision",
		source: value.source as LocalSource,
		local_ref: localRef,
		host_binding: value.host_binding as HostBinding,
		action_ref: actionRef,
		result_ref: resultRef,
		executor,
		target_digest: targetDigest,
		observed_effect: observedEffect,
		effect_state: value.effect_state as "known" | "unknown",
		verified_by: verifiedBy,
		budget_ref: budgetRef,
		created_at: value.created_at as string,
	});
}

/** Compare a parsed local selection against the CURRENT host snapshot. This is
 *  shape/consistency only (stale binding, owner/role drift, stop/authority
 *  facts); it NEVER proves the snapshot is a real live host. T02/T03 must do
 *  the actual host/file verification. */
export function compareLocalSelectionToHost(
	record: LocalSelectionRecordV1,
	current: HostFacts,
): ContractValidation<LocalSelectionRecordV1> {
	const layer = "host-consistency";
	const issues: ContractIssue[] = [];
	const binding = current.binding;
	for (const field of HOST_IDENTITY_FIELDS) {
		if (record.host_binding[field] !== binding[field]) {
			issues.push(
				issue(
					`host_binding.${field}`,
					field === "binding_version" ? "stale binding version" : "binding identity drift",
				),
			);
		}
	}
	if (record.source === "pm" && binding.role !== "pm") issues.push(issue("source", "pm source requires host role pm"));
	if (record.source === "worker-local" && binding.role === "pm")
		issues.push(issue("source", "worker-local source cannot use pm role"));
	const stop = newWorkStop(current);
	if (stop) issues.push(issue("host.stop_signals", `host ${stop.scope} stop forbids this selection`));
	if (current.authority_gap) issues.push(issue("host.authority_gap", "real authority gap forbids this selection"));
	if (issues.length) return rejected(layer, issues);
	return accepted(layer, record);
}

// ── Matter budget (`design.md` §4.5) ───────────────────────────────────────

/** Explicit FINITE budget. Every number comes from the real task card / run
 *  state (`source_refs`); there is no default, no Infinity and no implicit
 *  unlimited value. `parent_matter_ref` ties child work to the same matter. */
export interface MatterBudgetV1 {
	schema_version: SchemaVersion;
	budget_ref: string;
	matter_ref: string;
	parent_matter_ref?: string;
	deadline: string;
	max_steps: number;
	no_progress_limit: number;
	remaining_cost: number;
	steps_consumed: number;
	cost_consumed: number;
	no_progress_count: number;
	source_refs: string[];
}

export const MATTER_BUDGET_FIELDS = [
	"schema_version",
	"budget_ref",
	"matter_ref",
	"parent_matter_ref",
	"deadline",
	"max_steps",
	"no_progress_limit",
	"remaining_cost",
	"steps_consumed",
	"cost_consumed",
	"no_progress_count",
	"source_refs",
] as const;

/** Shape/consistency check. A missing budget returns fillable gaps and
 *  `authority_required: false` — never a fabricated human-authority question. */
export function validateMatterBudget(value: unknown): ContractValidation<MatterBudgetV1> {
	const layer = "matter-budget";
	if (!isRecord(value)) return rejected(layer, [issue("budget", "must be an object")], ["budget"]);
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	checkDeclaredKeys(value, MATTER_BUDGET_FIELDS, issues, "budget.");
	if (value.schema_version !== DECISION_HANDOFF_SCHEMA_VERSION)
		issues.push(issue("budget.schema_version", "must be 1"));
	const budgetRef = requiredString(value, "budget_ref", issues, gaps, "budget.");
	const matterRef = requiredString(value, "matter_ref", issues, gaps, "budget.");
	const parentMatterRef = optionalString(value, "parent_matter_ref", issues, "budget.");
	if (!isoTimestamp(value.deadline)) {
		issues.push(issue("budget.deadline", "must be a finite ISO deadline with timezone"));
		gaps.push("deadline");
	}
	if (!safeIntAtLeast(value.max_steps, 1)) {
		issues.push(issue("budget.max_steps", "must be a finite positive integer"));
		gaps.push("max_steps");
	}
	if (!safeIntAtLeast(value.no_progress_limit, 0)) {
		issues.push(issue("budget.no_progress_limit", "must be a finite non-negative integer"));
		gaps.push("no_progress_limit");
	}
	if (!finiteAtLeast(value.remaining_cost, 0)) {
		issues.push(issue("budget.remaining_cost", "must be a finite non-negative number"));
		gaps.push("remaining_cost");
	}
	if (!safeIntAtLeast(value.steps_consumed, 0)) {
		issues.push(issue("budget.steps_consumed", "must be a finite non-negative integer"));
		gaps.push("steps_consumed");
	}
	if (!finiteAtLeast(value.cost_consumed, 0)) {
		issues.push(issue("budget.cost_consumed", "must be a finite non-negative number"));
		gaps.push("cost_consumed");
	}
	if (!safeIntAtLeast(value.no_progress_count, 0)) {
		issues.push(issue("budget.no_progress_count", "must be a finite non-negative integer"));
		gaps.push("no_progress_count");
	}
	if (!nonblankStringArray(value.source_refs) || !(value.source_refs as string[]).length) {
		issues.push(issue("budget.source_refs", "real card/run provenance required; no invented default"));
		gaps.push("source_refs");
	}
	if (
		safeIntAtLeast(value.steps_consumed, 0) &&
		safeIntAtLeast(value.max_steps, 1) &&
		(value.steps_consumed as number) > (value.max_steps as number)
	) {
		issues.push(issue("budget.steps_consumed", "cannot exceed max_steps"));
	}
	if (
		issues.length ||
		budgetRef === undefined ||
		matterRef === undefined ||
		!isoTimestamp(value.deadline) ||
		!safeIntAtLeast(value.max_steps, 1) ||
		!safeIntAtLeast(value.no_progress_limit, 0) ||
		!finiteAtLeast(value.remaining_cost, 0) ||
		!safeIntAtLeast(value.steps_consumed, 0) ||
		!finiteAtLeast(value.cost_consumed, 0) ||
		!safeIntAtLeast(value.no_progress_count, 0) ||
		!nonblankStringArray(value.source_refs) ||
		!(value.source_refs as string[]).length
	) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		budget_ref: budgetRef,
		matter_ref: matterRef,
		...(parentMatterRef === undefined ? {} : { parent_matter_ref: parentMatterRef }),
		deadline: value.deadline as string,
		max_steps: value.max_steps as number,
		no_progress_limit: value.no_progress_limit as number,
		remaining_cost: value.remaining_cost as number,
		steps_consumed: value.steps_consumed as number,
		cost_consumed: value.cost_consumed as number,
		no_progress_count: value.no_progress_count as number,
		source_refs: value.source_refs as string[],
	});
}

export type BudgetRefreshReason = "new-turn" | "new-trigger" | "route" | "child-card" | "worker-restart";

/** Input contract for a continuation attempt. The caller must pass the SAME
 *  parent budget; this module never mints or refreshes one. */
export interface BudgetRefreshAttempt {
	reason: BudgetRefreshReason;
	matter_ref: string;
	child_matter_ref: string;
	proposed_budget: MatterBudgetV1;
}

export interface BudgetContinuation {
	allowed: boolean;
	reason:
		| "unchanged"
		| "budget-increase"
		| "deadline-extended"
		| "counter-reset"
		| "parent-mismatch"
		| "budget-exhausted"
		| "invalid-now"
		| "invalid-budget"
		| "identity-mismatch";
	issues: ContractIssue[];
	/** Always false: new turn / trigger / route / child never refresh budget. */
	budget_refreshed: false;
}

/** Reject any attempt to rebind the parent budget, change its matter/parent
 *  association, increase a limit/allowance, reset counters, or submit
 *  malformed / non-finite values. Both budgets are shape-validated BEFORE any
 *  numeric comparison, so NaN/Infinity/strings cannot slip through a false
 *  comparison. `now` is caller-supplied so this stays pure (no clock reads).
 *  Exhausted parents yield no new child action; always budget_refreshed=false. */
export function evaluateBudgetContinuation(
	parent: MatterBudgetV1,
	attempt: BudgetRefreshAttempt,
	now: string,
): BudgetContinuation {
	const issues: ContractIssue[] = [];
	const base: Omit<BudgetContinuation, "allowed" | "reason" | "issues"> = { budget_refreshed: false };
	if (!isoTimestamp(now)) {
		return { ...base, allowed: false, reason: "invalid-now", issues: [issue("now", "must be an ISO timestamp")] };
	}
	if (!isRecord(parent) || !isRecord(attempt)) {
		return {
			...base,
			allowed: false,
			reason: "invalid-budget",
			issues: [issue("budget", "parent and attempt must be objects")],
		};
	}
	const parentShape = validateMatterBudget(parent);
	const proposedShape = validateMatterBudget(attempt.proposed_budget);
	if (!parentShape.ok || !proposedShape.ok) {
		if (!parentShape.ok) issues.push(...parentShape.issues.map((item) => issue(`parent.${item.field}`, item.rule)));
		if (!proposedShape.ok)
			issues.push(...proposedShape.issues.map((item) => issue(`proposed_budget.${item.field}`, item.rule)));
		return { ...base, allowed: false, reason: "invalid-budget", issues };
	}
	const checkedParent = parentShape.value;
	const proposed = proposedShape.value;
	if (attempt.matter_ref !== checkedParent.matter_ref || !nonblank(attempt.child_matter_ref)) {
		return {
			...base,
			allowed: false,
			reason: "parent-mismatch",
			issues: [issue("matter_ref", "must match parent matter")],
		};
	}
	if (
		proposed.budget_ref !== checkedParent.budget_ref ||
		proposed.matter_ref !== checkedParent.matter_ref ||
		proposed.parent_matter_ref !== checkedParent.parent_matter_ref
	) {
		issues.push(issue("proposed_budget", "budget_ref / matter_ref / parent association must match parent"));
		return { ...base, allowed: false, reason: "identity-mismatch", issues };
	}
	if (
		checkedParent.remaining_cost <= 0 ||
		checkedParent.steps_consumed >= checkedParent.max_steps ||
		checkedParent.no_progress_count >= checkedParent.no_progress_limit ||
		Date.parse(now) >= Date.parse(checkedParent.deadline)
	) {
		return {
			...base,
			allowed: false,
			reason: "budget-exhausted",
			issues: [issue("budget", "parent budget exhausted; deliver a real resource-limited result")],
		};
	}
	if (proposed.deadline !== checkedParent.deadline) {
		issues.push(issue("deadline", "deadline must not be extended"));
		return { ...base, allowed: false, reason: "deadline-extended", issues };
	}
	if (
		proposed.max_steps > checkedParent.max_steps ||
		proposed.no_progress_limit > checkedParent.no_progress_limit ||
		proposed.remaining_cost > checkedParent.remaining_cost
	) {
		issues.push(issue("budget", "remaining budget / limits must not increase"));
		return { ...base, allowed: false, reason: "budget-increase", issues };
	}
	if (
		proposed.steps_consumed < checkedParent.steps_consumed ||
		proposed.cost_consumed < checkedParent.cost_consumed ||
		proposed.no_progress_count < checkedParent.no_progress_count
	) {
		issues.push(issue("budget", "consumption / no-progress counters must not be reset"));
		return { ...base, allowed: false, reason: "counter-reset", issues };
	}
	return { ...base, allowed: true, reason: "unchanged", issues: [] };
}

// ── Reservation I/O contract (NOT implemented here, T02/T06 own it) ────────

/** Inputs/outputs only. T02/T06 perform the real atomic reservation under the
 *  shared intent lock; this pure module never reserves or spends anything. */
export interface BudgetReservationRequest {
	parent_budget_ref: string;
	matter_ref: string;
	child_matter_ref: string;
	requested_steps: number;
	requested_cost: number;
	lock_ref: string;
}

export interface BudgetReservationResult {
	granted: boolean;
	reserved_steps: number;
	reserved_cost: number;
	child_budget_ref?: string;
	remaining_after_steps: number;
	remaining_after_cost: number;
	reason: "granted" | "budget-exhausted" | "insufficient-remaining" | "parent-mismatch" | "lock-unverified";
}

const RESERVATION_REQUEST_FIELDS = [
	"parent_budget_ref",
	"matter_ref",
	"child_matter_ref",
	"requested_steps",
	"requested_cost",
	"lock_ref",
] as const;
const RESERVATION_RESULT_FIELDS = [
	"granted",
	"reserved_steps",
	"reserved_cost",
	"child_budget_ref",
	"remaining_after_steps",
	"remaining_after_cost",
	"reason",
] as const;

export function parseBudgetReservationRequest(value: unknown): ContractValidation<BudgetReservationRequest> {
	const layer = "reservation-request-schema";
	if (!isRecord(value))
		return rejected(layer, [issue("reservation_request", "must be an object")], ["reservation_request"]);
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	checkDeclaredKeys(value, RESERVATION_REQUEST_FIELDS, issues, "reservation_request.");
	const parent = requiredString(value, "parent_budget_ref", issues, gaps, "reservation_request.");
	const matter = requiredString(value, "matter_ref", issues, gaps, "reservation_request.");
	const child = requiredString(value, "child_matter_ref", issues, gaps, "reservation_request.");
	const lock = requiredString(value, "lock_ref", issues, gaps, "reservation_request.");
	if (!safeIntAtLeast(value.requested_steps, 1))
		issues.push(issue("reservation_request.requested_steps", "finite positive integer"));
	if (!finiteAtLeast(value.requested_cost, 0))
		issues.push(issue("reservation_request.requested_cost", "finite non-negative number"));
	if (
		issues.length ||
		parent === undefined ||
		matter === undefined ||
		child === undefined ||
		lock === undefined ||
		!safeIntAtLeast(value.requested_steps, 1) ||
		!finiteAtLeast(value.requested_cost, 0)
	) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		parent_budget_ref: parent,
		matter_ref: matter,
		child_matter_ref: child,
		requested_steps: value.requested_steps as number,
		requested_cost: value.requested_cost as number,
		lock_ref: lock,
	});
}

const RESERVATION_REASONS: readonly string[] = [
	"granted",
	"budget-exhausted",
	"insufficient-remaining",
	"parent-mismatch",
	"lock-unverified",
];

export function parseBudgetReservationResult(value: unknown): ContractValidation<BudgetReservationResult> {
	const layer = "reservation-result-schema";
	if (!isRecord(value))
		return rejected(layer, [issue("reservation_result", "must be an object")], ["reservation_result"]);
	const issues: ContractIssue[] = [];
	const gaps: string[] = [];
	checkDeclaredKeys(value, RESERVATION_RESULT_FIELDS, issues, "reservation_result.");
	const child = optionalString(value, "child_budget_ref", issues, "reservation_result.");
	if (typeof value.granted !== "boolean") issues.push(issue("reservation_result.granted", "must be a boolean"));
	for (const field of ["reserved_steps", "remaining_after_steps"] as const) {
		if (!safeIntAtLeast(value[field], 0))
			issues.push(issue(`reservation_result.${field}`, "finite non-negative integer"));
	}
	for (const field of ["reserved_cost", "remaining_after_cost"] as const) {
		if (!finiteAtLeast(value[field], 0))
			issues.push(issue(`reservation_result.${field}`, "finite non-negative number"));
	}
	if (!RESERVATION_REASONS.includes(value.reason as string))
		issues.push(issue("reservation_result.reason", "unknown reason"));
	if (
		issues.length ||
		typeof value.granted !== "boolean" ||
		!safeIntAtLeast(value.reserved_steps, 0) ||
		!finiteAtLeast(value.reserved_cost, 0) ||
		!safeIntAtLeast(value.remaining_after_steps, 0) ||
		!finiteAtLeast(value.remaining_after_cost, 0) ||
		!RESERVATION_REASONS.includes(value.reason as string)
	) {
		return rejected(layer, issues, gaps);
	}
	return accepted(layer, {
		granted: value.granted as boolean,
		reserved_steps: value.reserved_steps as number,
		reserved_cost: value.reserved_cost as number,
		...(child === undefined ? {} : { child_budget_ref: child }),
		remaining_after_steps: value.remaining_after_steps as number,
		remaining_after_cost: value.remaining_after_cost as number,
		reason: value.reason as BudgetReservationResult["reason"],
	});
}

// ── Frozen v1 schema summary (JSON-serializable, for TS/Python parity) ─────

export const SCHEMA_V1 = {
	id: DECISION_HANDOFF_SCHEMA_ID,
	schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
	records: ["decision-feedback", "pm-disposition", "local-selection", "local-execution", "matter-budget"],
	feedback_categories: FEEDBACK_CATEGORIES,
	effect_states: EFFECT_STATES,
	stop_scopes: STOP_SCOPES,
	pm_disposition_kinds: PM_DISPOSITION_KINDS,
	pm_disposition_statuses: PM_DISPOSITION_STATUSES,
	local_sources: LOCAL_SOURCES,
	forbidden_dp_fields: FORBIDDEN_LOCAL_DP_FIELDS,
	local_selection_fields: LOCAL_SELECTION_FIELDS,
	local_execution_fields: LOCAL_EXECUTION_FIELDS,
	matter_budget_fields: MATTER_BUDGET_FIELDS,
	decision_ref_kinds: ["dp", "local"],
	verification_scope: "shape-only",
	host_source_verified: false,
} as const;
