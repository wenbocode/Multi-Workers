/**
 * T02 — the UNIQUE TS host writer for frozen local decision records (schema v1).
 *
 * BOUNDARY — read this before using the API:
 *  - This store REUSES the frozen pure contract in `decision-handoff.ts`. It does
 *    NOT fork a second schema, field list, category or record shape. Records are
 *    produced by the frozen validators (`validateLocalBusinessSelection`,
 *    `parseLocalExecutionRecord`, `parsePmDisposition`) and checked by the frozen
 *    parsers/comparators. `schema_version` is always `DECISION_HANDOFF_SCHEMA_VERSION`.
 *  - A pure `parse*` success is `shape-only`; it is NEVER a host-source proof. The
 *    read methods are ALWAYS `verification: "shape-only"`, `host_source_verified:
 *    false`. Only a controlled write that passed the trusted-host checks reports
 *    `host_source_verified: true`.
 *  - The ONLY trusted entry point for host-owned facts is the injected
 *    `LocalSelectionHostAdapter`. T04..T15 wire it to production sources; tests
 *    inject L1 host fixtures. A model-supplied `HostFacts`, a `source: "pm"`
 *    string, a boolean `verified: true`, or "the file exists" is NEVER accepted
 *    as provenance. Missing adapter / trusted context / verifier ⇒ FAIL CLOSED.
 *  - The store reads the authoritative live binding ITSELF from `_index.parallel`
 *    (via `IndexStore.readAll`, the unique active EXACT-SELF row, never
 *    `_index.md`/`activeEntry`/latest/global). Old records are read-only recovery
 *    clues, never replayed or overwritten.
 *  - `selection != execution`: a selection is a PLAN (`action_state: planned`,
 *    `business_completed: false`, no action/result facts). An execution record is
 *    appended to a PHYSICALLY SEPARATE file only after a real verifier proof.
 *  - This is a primitive. It does not alter live asks/followup/gate/sign/Done,
 *    does not perform business effects, does not create a scheduler ledger, does
 *    not add budget grants and does not claim any product L2/VC pass.
 *
 * Physical layout is shared with T03 (Python strict reader) per
 * `evidence/acceptance/T01/contract-freeze-20261112.md`; T02 writes, T03 reads.
 */

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import {
	type AuthorityFact,
	type BudgetExhaustionFact,
	type BudgetReservationResult,
	type ContractValidation,
	compareLocalSelectionToHost,
	DECISION_HANDOFF_SCHEMA_ID,
	DECISION_HANDOFF_SCHEMA_VERSION,
	type ExemptionFact,
	type HostBinding,
	type HostFacts,
	type HostRole,
	type LocalBusinessSelectionInput,
	type LocalExecutionRecordV1,
	type LocalSelectionRecordV1,
	type LocalSource,
	type MatterBudgetV1,
	type PmDisposition,
	parseBudgetReservationResult,
	parseLocalExecutionRecord,
	parseLocalSelectionRecord,
	parsePmDisposition,
	type StopScope,
	type StopSignal,
	stopScopeForBudgetFact,
	stopScopeForSignal,
	validateLocalBusinessSelection,
	validateMatterBudget,
} from "./decision-handoff.ts";
import { acquireLock, type LockOptions } from "./file-lock.ts";
import { type IndexEntry, IndexStore, keyNameRefusal, normalizeKey } from "./index-store.ts";

// ── Frozen physical naming (freeze §Common physical naming) ────────────────

export const SELECTION_FILE_SUFFIX = ".json";
export const EXECUTION_FILE_SUFFIX = ".execution.json";
export const DISPOSITION_FILE_SUFFIX = ".disposition.json";

/** PM base `<root>/<key>/evidence/decision-handoffs/`; worker base
 *  `<root>/<key>/workers/<task_key>/local-decisions/` (bound to task AND run by
 *  the trusted binding, not by a path segment). No caller-supplied target path. */
export const PM_HANDOFF_DIR = ["evidence", "decision-handoffs"] as const;
export const WORKER_DECISION_DIR = "local-decisions";
export const WORKERS_DIR = "workers";

/** Max logical ref size we encode. A longer ref returns a concrete failure; we
 *  NEVER truncate (a truncated ref is collision-prone). Keeps the base64url
 *  filename + suffix + tmp name below the Windows per-component limit. */
export const MAX_LOCAL_REF_BYTES = 120;

/** A trusted host snapshot must be CURRENT, not an old replay: a controlled
 *  commit checks that `observed_at` is neither in the future nor older than
 *  this FINITE window relative to the store/host clock. This is a bounded
 *  freshness refusal, never an implicit grant or an unlimited clock. */
const MAX_TRUSTED_CONTEXT_AGE_MS = 10 * 60 * 1000;

/** Shared intent lock name. It follows the existing O_EXCL `.mw/<name>.lock`
 *  convention (`index.lock`, `workers.lock`, `gates.lock`). The shared intent
 *  lock is acquired BEFORE the per-record local lock; both are released in
 *  reverse order. No network call is made while holding either. */
export const SHARED_INTENT_LOCK_BASENAME = "decision-handoff-intent.lock";

export function sharedIntentLockPath(agenticdocRoot: string): string {
	return path.join(agenticdocRoot, "..", ".mw", SHARED_INTENT_LOCK_BASENAME);
}

/** Canonical RFC4648 base64url (NO padding) of the FULL UTF-8 ref bytes. The
 *  round-trip check rejects lone surrogates / non-canonical encodings. Returns
 *  undefined for blank / NUL / too-long / non-canonical refs (a concrete refusal,
 *  never a truncated name). Colons, slashes, dots are encoded away so Windows
 *  never sees a colon or a path separator in the filename. */
export function encodeLocalRef(ref: unknown): string | undefined {
	if (typeof ref !== "string" || ref.length === 0 || /\u0000/.test(ref)) return undefined;
	const bytes = Buffer.from(ref, "utf8");
	if (bytes.length > MAX_LOCAL_REF_BYTES) return undefined;
	const encoded = bytes.toString("base64url");
	if (encoded.length === 0 || encoded.length > 160) return undefined;
	if (Buffer.from(encoded, "base64url").toString("utf8") !== ref) return undefined;
	return encoded;
}

/** Absolute path of a record file (for evidence / test fixtures). This does NOT
 *  perform the redirect/escape checks; use the store methods for real I/O. */
export function storedRecordPath(
	agenticdocRoot: string,
	key: string,
	source: LocalSource,
	taskKey: string | undefined,
	ref: string,
	suffix: string,
): string {
	const encoded = encodeLocalRef(ref);
	if (encoded === undefined) throw new Error("invalid local ref");
	const base =
		source === "pm"
			? path.join(agenticdocRoot, key, ...PM_HANDOFF_DIR)
			: path.join(agenticdocRoot, key, WORKERS_DIR, taskKey ?? "", WORKER_DECISION_DIR);
	return path.join(base, `${encoded}${suffix}`);
}

// ── Failure codes (closed, documented) ─────────────────────────────────────

/** Machine outcomes. `written`/`duplicate` are the only successes. Everything
 *  else is a fail-closed refusal (no record written, no controlled effect). */
export const LOCAL_STORE_CODES = [
	"written",
	"duplicate",
	"conflict",
	"recovery-clue",
	"existing-corrupt",
	"existing-invalid",
	"effect-unknown",
	"trusted-context-missing",
	"trusted-context-refused",
	"binding-no-unique-active",
	"binding-ambiguous",
	"binding-foreign",
	"binding-stale-owner",
	"binding-stale-run",
	"parent-drift",
	"material-drift",
	"basis-drift",
	"matter-drift",
	"target-drift",
	"budget-invalid",
	"budget-preflight-missing",
	"budget-preflight-denied",
	"budget-exhausted",
	"stop-scope-blocked",
	"verifier-missing",
	"verifier-unproven",
	"selection-invalid",
	"execution-invalid",
	"disposition-invalid",
	"target-path-invalid",
	"redirect-detected",
	"out-of-bounds",
	"lock-busy",
	"write-failed",
	"absent",
	"ok",
] as const;
export type LocalStoreCode = (typeof LOCAL_STORE_CODES)[number];

/** Verification level of an API result. Reads are ALWAYS `shape-only`; the
 *  controlled write path always runs the fail-closed host-verification protocol
 *  and reports `host-context-checked` (pass ⇒ written/duplicate, fail ⇒ refusal). */
export type StoreVerification = "shape-only" | "host-context-checked";

// ── Trusted host adapter (the ONLY host-source entry point) ─────────────────

export interface ExpectedHostFacts {
	matter_ref: string;
	matter_version: string;
	material_digest: string;
	basis_digest: string;
	budget_ref: string;
	/** Expected parent DP decision id (absent when there is no parent DP). */
	parent_decision_id?: string;
	/** Expected target digest for execution correlation, when known. */
	target_digest?: string;
}

/** Store-controlled write intent. It is NEVER supplied by a model-facing
 *  request: each controlled write method constructs the context request itself.
 *  The narrow terminal exception is available only for execution/disposition
 *  archival of an already executed, uniquely joined action. */
export type LocalWriteKind = "selection" | "execution" | "disposition";

export interface TrustedContextRequest {
	key: string;
	source: LocalSource;
	/** The record ref being committed (local_ref or disposition_ref). */
	ref: string;
	task_key?: string;
	run_id?: string;
	/** Internal only; absent means a normal business selection preflight. */
	write_kind?: LocalWriteKind;
}

/** Concrete facts the host observed from real card/run/material/basis/target
 *  files. NOT booleans, NOT model text. The store cross-checks them against the
 *  authoritative index and the produced record. */
export interface TrustedHostContext {
	/** Exact current-window claim id. The store finds the UNIQUE active row with
	 *  this claimId in `_index.parallel`; 0/multiple/foreign ⇒ refused. */
	self_claim_id: string;
	/** Host snapshot marker (rejects stale bindings). */
	binding_version: string;
	role: HostRole;
	/** ISO timestamp of the host snapshot. FRESH on every read; this is the
	 *  current clock used for the staleness/finite-deadline checks in
	 *  `verifyTrusted`. It is intentionally NOT persisted into the binding. */
	observed_at: string;
	/** Immutable run-start ISO timestamp: the stable observation time of the
	 *  authoritative binding identity for this one run. Persisted VERBATIM into
	 *  `host_binding.observed_at` so selection / execution / disposition records
	 *  of one run correlate byte-for-byte (complete immutable binding). This is
	 *  NOT the current clock and never replaces it: freshness/staleness/deadline
	 *  are still re-checked on EVERY read against the fresh `observed_at` above,
	 *  and the last-await `finalRecheck` still re-reads that fresh clock. Optional
	 *  so L1 host fixtures that predate this field keep their exact prior
	 *  behaviour (fall back to `observed_at`). */
	binding_established_at?: string;
	/** Current worker task/run (required for worker-local). */
	task_key?: string;
	run_id?: string;
	expected: ExpectedHostFacts;
	/** Real FINITE matter budget from card/run state (validated by the store). */
	budget: unknown;
	/** Real budget/reservation preflight under the shared intent lock. Absent ⇒
	 *  a fillable gap, never a default grant. `reserved_*` is NOT cost_consumed. */
	budget_preflight: unknown;
	stop_signals?: StopSignal[];
	budget_facts?: BudgetExhaustionFact[];
	authority_gap?: AuthorityFact;
	exemption?: ExemptionFact;
	effect_unknown?: { action_ref: string };
	/** Narrow terminal bookkeeping proof from the trusted host. It is never a
	 *  new grant, reservation, selection, clock or replay body. */
	executed_action?: ExecutedActionTerminalProof;
}

/** Exact, already-executed action whose terminal records remain to be written
 *  after its own final authorized budget unit was consumed. Every field is a
 *  real host observation; the store still rechecks identity, source, current
 *  files, stops, deadline, paths and the final trusted context. */
export interface ExecutedActionTerminalProof {
	kind: "executed-action-terminal";
	source: LocalSource;
	key: string;
	role: HostRole;
	claim_id: string;
	task_key?: string;
	run_id: string;
	card_path: string;
	card_sha256: string;
	budget_started_at: string;
	authorization_unit: string;
	budget_ref: string;
	matter_ref: string;
	local_ref: string;
	action_ref: string;
	result_ref: string;
	disposition_ref: string;
	executor: string;
	observed_effect: string;
	before_digest: string;
	after_digest: string;
	reservation_ref: string;
	observation_ref: string;
	exhaustion_code: "budget-exhausted";
	preflight_reason: "budget-exhausted";
	available_steps: number;
	available_cost: number;
	held_steps: number;
	held_cost: number;
	in_flight: number;
	steps_consumed: number;
	max_steps: number;
	cost_consumed: number;
	remaining_cost: number;
	no_progress_count: number;
	no_progress_limit: number;
	deadline: string;
}

/** Structured PROOF of a real action/result/target effect, produced by the host
 *  verifier. A boolean or file-present is NOT an `ExecutionProof`; the store
 *  correlates every field with the request and the original selection. */
export interface ExecutionProof {
	action_ref: string;
	result_ref: string;
	/** Identity of the target verifier that produced this proof. */
	verifier_ref: string;
	target_digest: string;
	observed_effect: string;
	/** The verifier's observed effect state. "unknown" is recorded as unknown;
	 *  a model self-report can never force "known". */
	effect_state: "known" | "unknown";
	/** Correlated record id (not a boolean). */
	local_ref: string;
	executor: string;
}

export interface ExecutionVerificationRequest {
	key: string;
	source: LocalSource;
	local_ref: string;
	action_ref: string;
	result_ref: string;
	executor: string;
	observed_effect: string;
	expected_target_digest?: string;
	/** The authoritative binding this effect must be correlated with. */
	binding: HostBinding;
}

/** The trusted host adapter. Wired to production by T04..T15; injected as L1
 *  host fixtures in tests. Omitting it, or an absent/refused/throwing method,
 *  makes every controlled write fail closed. */
export interface LocalSelectionHostAdapter {
	/** Return concrete host-observed facts, or undefined when unavailable. */
	readTrustedContext(request: TrustedContextRequest): Promise<TrustedHostContext | undefined>;
	/** Independently verify a real effect and return structured proof, or
	 *  undefined when it cannot be established. Optional: absence ⇒ no execution
	 *  record is ever written. */
	verifyExecution?(request: ExecutionVerificationRequest): Promise<ExecutionProof | undefined>;
}

// ── Requests ───────────────────────────────────────────────────────────────

/** `selection` is the host-assembled layer-3 business input (minus `host` and
 *  `budget`, which the store supplies from trusted context). */
export interface CommitSelectionRequest {
	source: LocalSource;
	local_ref: string;
	task_key?: string;
	run_id?: string;
	selection: Omit<LocalBusinessSelectionInput, "host" | "budget" | "source" | "local_ref">;
}

export interface AppendExecutionRequest {
	source: LocalSource;
	local_ref: string;
	task_key?: string;
	run_id?: string;
	action_ref: string;
	result_ref: string;
	executor: string;
	observed_effect: string;
	created_at: string;
	/** Untrusted model claim; NEVER sufficient without a verifier proof. */
	claimed_effect_state?: "known" | "unknown";
}

export interface SaveDispositionRequest {
	source: LocalSource;
	disposition_ref: string;
	task_key?: string;
	run_id?: string;
	/** The host-built PmDisposition JSON value (validated by parsePmDisposition). */
	disposition: unknown;
}

/** Pure shape-only read. `ref` is local_ref (selection/execution) or
 *  disposition_ref (disposition). Reads need NO adapter and stay available under
 *  a stop, so read-only recovery clues are preserved. */
export interface ReadRequest {
	source: LocalSource;
	ref: string;
	task_key?: string;
}

// ── Results ────────────────────────────────────────────────────────────────

export type AnyLocalRecord = LocalSelectionRecordV1 | LocalExecutionRecordV1 | PmDisposition;

/** Result of a controlled write. `host_source_verified` is TRUE only for
 *  `written`/`duplicate` (adapter-relative, NOT a product L2/VC claim). */
export interface LocalWriteResult {
	code: LocalStoreCode;
	/** True only for `written` / `duplicate` (idempotent success). */
	ok: boolean;
	verification: StoreVerification;
	host_source_verified: boolean;
	/** Execution outcome: "known"/"unknown"; absent for selection/disposition. */
	effect_state?: "known" | "unknown";
	/** The committed / duplicate record, when available. */
	record?: AnyLocalRecord;
	/** Fillable gaps for refusals that a consumer can supply (never a grant). */
	gaps: string[];
	reason: string;
	/** Derived physical path (evidence only). */
	path?: string;
	/** Read-only recovery clue for an old-run/foreign existing record. */
	recovery_clue?: RecoveryClue;
}

export interface RecoveryClue {
	path: string;
	/** Shape-only parsed record; NEVER a current capability, never replayed. */
	record: AnyLocalRecord;
	reason: string;
}

/** Result of a pure shape-only read. NEVER reports source verified. */
export interface LocalReadResult<T> {
	verification: "shape-only";
	host_source_verified: false;
	status: "ok" | "absent" | "corrupt" | "invalid-shape" | "refused";
	code: LocalStoreCode;
	/** Shape-valid parsed record, present only for status "ok". */
	record?: T;
	reason: string;
	path: string;
}

// ── Config ─────────────────────────────────────────────────────────────────

export interface LocalStoreConfig {
	/** The `.agenticdoc` root. */
	agenticdoc_root: string;
	key: string;
	/** Trusted host adapter (T04..T15 production wiring; L1 fixtures in tests).
	 *  Omitted ⇒ every controlled write fails closed. */
	host_adapter?: LocalSelectionHostAdapter;
	/** Test-only fault seam for the atomic writer. Production leaves undefined;
	 *  the default uses real tmp/wx+fsync+rename. NOT a full mock: all locks,
	 *  path checks, parsers and host verification still run for real. */
	atomic_write?: (file: string, value: unknown) => void;
	/** Best-effort diagnostic log path; failures here NEVER affect the result
	 *  (diagnostic log failure does not globally stop the PM). */
	diagnostic_log?: string;
	/** O_EXCL lock retry tuning, shared by the intent and local locks. */
	lock_options?: LockOptions;
	/** Trusted current-clock reading (epoch ms) for the budget/freshness checks.
	 *  Production leaves it undefined: the default is the REAL host clock
	 *  (`Date.now`). Tests may inject a deterministic finite clock. A missing or
	 *  non-finite reading is a fail-closed refusal, never an unlimited default. */
	clock?: () => number;
}

// ── Internal pure helpers (no `any`, no inline imports) ─────────────────────

/** Order-independent canonical JSON string: object keys are sorted recursively
 *  so parsed-JSON key insertion order never produces a spurious conflict. Used
 *  by all three write methods for duplicate/conflict detection. */
function stableStringify(value: unknown): string {
	if (value === null || typeof value !== "object") return JSON.stringify(value);
	if (Array.isArray(value)) return `[${value.map((item) => stableStringify(item)).join(",")}]`;
	const obj = value as Record<string, unknown>;
	return `{${Object.keys(obj)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${stableStringify(obj[key])}`)
		.join(",")}}`;
}

/** Semantic comparison key: the full record minus the two VOLATILE observation
 *  timestamps (`created_at` at the top level and the host snapshot `observed_at`
 *  nested in `host_binding`/`binding`). A legal freshness refresh changes ONLY
 *  `observed_at`: it is NOT decision identity, so a same-selection /
 *  same-execution / same-disposition replay stays an idempotent, byte-preserving
 *  duplicate. EVERY other field — owner/role/claim/key/task/run/binding_version,
 *  choice/material/basis/budget, action/result/executor/target/effect — remains
 *  compared, so a real semantic change is still a `conflict`. Freshness, the
 *  finite deadline, current budget and stops are enforced for real against the
 *  current clock on EVERY `verifyTrusted` read; excluding the volatile timestamp
 *  here NEVER relaxes those checks and NEVER overwrites a bad existing
 *  (corrupt/invalid/foreign are refused before this comparison). */
function semanticKey(record: unknown): string {
	if (record === null || typeof record !== "object" || Array.isArray(record)) return stableStringify(record);
	const copy: Record<string, unknown> = { ...(record as Record<string, unknown>) };
	delete copy.created_at;
	for (const field of ["host_binding", "binding"]) {
		const nested = copy[field];
		if (nested !== null && typeof nested === "object" && !Array.isArray(nested)) {
			const binding: Record<string, unknown> = { ...(nested as Record<string, unknown>) };
			delete binding.observed_at;
			copy[field] = binding;
		}
	}
	return stableStringify(copy);
}

/** Immutable SEMANTIC snapshot of the trusted host context, captured as a
 *  STRING the moment the context is read (BEFORE a later host callback can
 *  mutate a nested object in place). `observed_at` is deliberately EXCLUDED:
 *  a legal freshness refresh is NOT identity/material/basis/budget/stop/target
 *  drift. Freshness and the finite deadline are still enforced against the REAL
 *  current clock for EVERY read in `verifyTrusted`; excluding the timestamp from
 *  this projection NEVER relaxes those checks. Comparing two post-callback
 *  projections of the same mutable object would hide an in-place mutation; an
 *  eagerly captured immutable string cannot. */
function semanticContextFingerprint(trusted: TrustedHostContext): string {
	const semantic: Record<string, unknown> = { ...trusted };
	delete semantic.observed_at;
	return stableStringify(semantic);
}

const HOST_IDENTITY_FIELDS = ["owner", "role", "claim_id", "key", "task_key", "run_id", "binding_version"] as const;

/** Identity drift (including absent↔present). Any drift means the existing
 *  record belongs to a previous owner/run/binding and is a read-only clue. */
function bindingIdentityDrifts(a: HostBinding, b: HostBinding): boolean {
	return HOST_IDENTITY_FIELDS.some((field) => a[field] !== b[field]);
}

function nonblank(value: unknown): value is string {
	return typeof value === "string" && value.trim() !== "";
}

interface TerminalWriteCorrelation {
	source: LocalSource;
	ref: string;
	task_key?: string;
	run_id?: string;
	action_ref?: string;
	result_ref?: string;
	executor?: string;
	observed_effect?: string;
}

function isJsonRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isTerminalProof(value: unknown): value is ExecutedActionTerminalProof {
	if (!isJsonRecord(value)) return false;
	const t = value as unknown as ExecutedActionTerminalProof;
	const strings = [
		t.kind,
		t.key,
		t.role,
		t.claim_id,
		t.run_id,
		t.card_path,
		t.card_sha256,
		t.budget_started_at,
		t.authorization_unit,
		t.budget_ref,
		t.matter_ref,
		t.local_ref,
		t.action_ref,
		t.result_ref,
		t.disposition_ref,
		t.executor,
		t.observed_effect,
		t.before_digest,
		t.after_digest,
		t.reservation_ref,
		t.observation_ref,
		t.exhaustion_code,
		t.preflight_reason,
		t.deadline,
	] as const;
	const numbers = [
		t.available_steps,
		t.available_cost,
		t.held_steps,
		t.held_cost,
		t.in_flight,
		t.steps_consumed,
		t.max_steps,
		t.cost_consumed,
		t.remaining_cost,
		t.no_progress_count,
		t.no_progress_limit,
	] as const;
	return (
		t.kind === "executed-action-terminal" &&
		(t.source === "pm" || t.source === "worker-local") &&
		["pm", "coding", "research", "review"].includes(t.role) &&
		(t.task_key === undefined || nonblank(t.task_key)) &&
		strings.every((item) => nonblank(item)) &&
		/^[a-f0-9]{64}$/.test(t.card_sha256) &&
		/^sha256:[a-f0-9]{64}$/.test(t.before_digest) &&
		/^sha256:[a-f0-9]{64}$/.test(t.after_digest) &&
		t.before_digest !== t.after_digest &&
		t.observed_effect === `byte-manifest:${t.before_digest}->${t.after_digest};business-correctness=unverified` &&
		t.exhaustion_code === "budget-exhausted" &&
		t.preflight_reason === "budget-exhausted" &&
		numbers.every((item) => typeof item === "number" && Number.isFinite(item) && item >= 0) &&
		Number.isFinite(Date.parse(t.deadline))
	);
}

/** One narrow exception: archival of an action that has ALREADY consumed the
 *  last authorized unit. It is not a zero-budget exemption: every exhausted
 *  counter, denied preflight, identity, stop, deadline and final recheck must
 *  still agree with the same real action. */
function terminalExceptionAllowed(input: {
	proof: unknown;
	key: string;
	writeKind: LocalWriteKind;
	request: TrustedContextRequest;
	correlation?: TerminalWriteCorrelation;
	trusted: TrustedHostContext;
	budget: MatterBudgetV1;
	preflight: BudgetReservationResult;
	rowClaimId: string;
	role: HostRole;
	observedMs: number;
	nowMs: number;
	deadlineMs: number;
}): boolean {
	if ((input.writeKind !== "execution" && input.writeKind !== "disposition") || !isTerminalProof(input.proof))
		return false;
	const t = input.proof;
	const request = input.request;
	const correlation = input.correlation;
	const budget = input.budget;
	const preflight = input.preflight;
	if (
		request.key !== input.key ||
		request.source !== t.source ||
		request.source !== correlation?.source ||
		request.ref !== correlation?.ref ||
		t.key !== input.key ||
		t.role !== input.role ||
		t.claim_id !== input.rowClaimId ||
		t.budget_ref !== budget.budget_ref ||
		t.matter_ref !== budget.matter_ref ||
		t.matter_ref !== input.trusted.expected.matter_ref ||
		t.budget_ref !== input.trusted.expected.budget_ref ||
		!input.trusted.binding_version.includes(t.card_sha256) ||
		(request.task_key !== undefined && request.task_key !== t.task_key) ||
		(request.run_id !== undefined && request.run_id !== t.run_id) ||
		(correlation?.task_key !== undefined && correlation.task_key !== t.task_key) ||
		(correlation?.run_id !== undefined && correlation.run_id !== t.run_id)
	)
		return false;
	if (input.writeKind === "execution") {
		if (
			request.ref !== t.local_ref ||
			correlation?.action_ref !== t.action_ref ||
			correlation.result_ref !== t.result_ref ||
			correlation.executor !== t.executor ||
			correlation.observed_effect !== t.observed_effect
		)
			return false;
	} else if (request.ref !== t.disposition_ref || correlation?.ref !== t.disposition_ref) {
		return false;
	}
	if (
		input.trusted.stop_signals?.length ||
		input.trusted.budget_facts?.length ||
		input.trusted.authority_gap !== undefined ||
		input.trusted.exemption !== undefined ||
		input.trusted.effect_unknown !== undefined ||
		input.observedMs >= input.deadlineMs ||
		input.nowMs >= input.deadlineMs ||
		budget.deadline !== t.deadline
	)
		return false;
	return (
		preflight.granted === false &&
		preflight.reason === "budget-exhausted" &&
		preflight.reserved_steps === 0 &&
		preflight.reserved_cost === 0 &&
		preflight.remaining_after_steps === 0 &&
		preflight.remaining_after_cost === 0 &&
		t.available_steps === 0 &&
		t.available_cost === 0 &&
		t.held_steps === 0 &&
		t.held_cost === 0 &&
		t.in_flight === 0 &&
		t.steps_consumed === budget.steps_consumed &&
		t.max_steps === budget.max_steps &&
		t.cost_consumed === budget.cost_consumed &&
		t.remaining_cost === 0 &&
		t.no_progress_count === budget.no_progress_count &&
		t.no_progress_limit === budget.no_progress_limit &&
		budget.steps_consumed === budget.max_steps &&
		budget.remaining_cost === 0 &&
		budget.no_progress_count < budget.no_progress_limit &&
		budget.cost_consumed + budget.remaining_cost === t.cost_consumed
	);
}

function terminalExecutionMatches(proof: unknown, key: string, req: AppendExecutionRequest): boolean {
	if (!isTerminalProof(proof)) return false;
	const t = proof;
	return (
		t.key === key &&
		t.source === req.source &&
		t.local_ref === req.local_ref &&
		t.action_ref === req.action_ref &&
		t.result_ref === req.result_ref &&
		t.executor === req.executor &&
		t.observed_effect === req.observed_effect &&
		(req.task_key === undefined || req.task_key === t.task_key) &&
		(req.run_id === undefined || req.run_id === t.run_id)
	);
}

function terminalDispositionMatches(
	proof: unknown,
	key: string,
	req: SaveDispositionRequest,
	record: PmDisposition,
): boolean {
	if (!isTerminalProof(proof)) return false;
	const t = proof;
	const basis = record.basis_refs ?? [];
	return (
		t.key === key &&
		t.source === req.source &&
		t.disposition_ref === req.disposition_ref &&
		t.disposition_ref === record.disposition_ref &&
		t.claim_id === record.owner &&
		t.budget_ref === record.budget_ref &&
		record.feedback_ref === `feedback:${t.action_ref}` &&
		basis.length === 2 &&
		basis[0] === t.action_ref &&
		basis[1] === t.result_ref &&
		(req.task_key === undefined || req.task_key === t.task_key) &&
		(req.run_id === undefined || req.run_id === t.run_id)
	);
}

function errCode(err: unknown): string {
	return err instanceof Error && "code" in err ? String((err as NodeJS.ErrnoException).code) : "write-error";
}

/** Real atomic write: O_EXCL temp, fsync, rename; finally cleans only OUR temp
 *  file (never another writer's lock/file). Matches `decision-followup.ts`. */
export function atomicWriteJson(file: string, value: unknown): void {
	const dir = path.dirname(file);
	const tmp = path.join(dir, `.${path.basename(file)}.${process.pid}.${crypto.randomUUID()}.tmp`);
	let fd: number | undefined;
	try {
		fd = fs.openSync(tmp, "wx");
		fs.writeFileSync(fd, `${JSON.stringify(value, null, 2)}\n`, "utf8");
		fs.fsyncSync(fd);
		fs.closeSync(fd);
		fd = undefined;
		fs.renameSync(tmp, file);
	} finally {
		if (fd !== undefined) fs.closeSync(fd);
		try {
			fs.unlinkSync(tmp);
		} catch {
			// The atomic rename consumed the temporary file.
		}
	}
}

interface LocalPath {
	base: string;
	file: string;
	lockFile: string;
}

type LocalPathResult = LocalPath | { code: LocalStoreCode; reason: string };

function isLink(absolutePath: string): boolean {
	try {
		return fs.lstatSync(absolutePath).isSymbolicLink();
	} catch {
		return false;
	}
}

/** Per-layer redirect / symlink / junction / out-of-bounds check. On this Node,
 *  `lstatSync(...).isSymbolicLink()` is true for BOTH symlinks and Windows
 *  junctions; the realpath containment check is defense in depth. Reads NEVER
 *  create directories; the check only inspects existing components. */
function pathSafety(agenticdocRoot: string, base: string, file: string): LocalStoreCode | undefined {
	const root = path.resolve(agenticdocRoot);
	const resolvedBase = path.resolve(base);
	if (resolvedBase !== root && !resolvedBase.startsWith(root + path.sep)) return "out-of-bounds";
	const rel = path.relative(root, resolvedBase);
	let cursor = root;
	for (const segment of rel.split(path.sep).filter(Boolean)) {
		cursor = path.join(cursor, segment);
		if (isLink(cursor)) return "redirect-detected";
	}
	if (isLink(file)) return "redirect-detected";
	if (fs.existsSync(file) && !fs.lstatSync(file).isFile()) return "redirect-detected";
	if (fs.existsSync(resolvedBase)) {
		let realRoot: string;
		let realBase: string;
		try {
			realRoot = fs.realpathSync(root);
			realBase = fs.realpathSync(resolvedBase);
		} catch {
			return "redirect-detected";
		}
		if (realBase !== realRoot && !realBase.startsWith(realRoot + path.sep)) return "redirect-detected";
	}
	return undefined;
}

/** Derive the record path strictly from validated inputs. Rejects illegal
 *  key/task names, blank/overlong refs, redirects and out-of-bounds paths. Never
 *  accepts a caller-supplied target filename. */
function resolveLocalPath(
	agenticdocRoot: string,
	key: string,
	source: LocalSource,
	taskKey: string | undefined,
	ref: string,
	suffix: string,
): LocalPathResult {
	if (source !== "pm" && source !== "worker-local") return { code: "target-path-invalid", reason: "unknown source" };
	if (keyNameRefusal(key) !== null) return { code: "target-path-invalid", reason: "illegal key name" };
	let base: string;
	if (source === "pm") {
		base = path.join(agenticdocRoot, key, ...PM_HANDOFF_DIR);
	} else {
		if (taskKey === undefined || keyNameRefusal(taskKey) !== null)
			return { code: "target-path-invalid", reason: "worker-local requires a legal task_key" };
		base = path.join(agenticdocRoot, key, WORKERS_DIR, taskKey, WORKER_DECISION_DIR);
	}
	const encoded = encodeLocalRef(ref);
	if (encoded === undefined)
		return { code: "target-path-invalid", reason: "blank/overlong/non-canonical local ref (not truncated)" };
	const file = path.join(base, `${encoded}${suffix}`);
	const unsafe = pathSafety(agenticdocRoot, base, file);
	if (unsafe !== undefined) return { code: unsafe, reason: "redirect / out-of-bounds target path" };
	return { base, file, lockFile: `${file}.lock` };
}

/** UNIQUE active exact-self row in `_index.parallel`. 0 / multiple / foreign are
 *  explicit refusals. `_index.md` is only a projection and is never consulted. */
function resolveAuthoritativeRow(
	indexStore: IndexStore,
	key: string,
	selfClaimId: string,
): { row: IndexEntry } | { code: LocalStoreCode; reason: string } {
	const rows = indexStore.readAll();
	// Authority for the CURRENT key is unique only when there is exactly one
	// active row for it. A self row plus a foreign active row is still an
	// ambiguous claim on this key and must not be resolved by an own-claim
	// filter. Active rows of OTHER keys are unrelated and never counted.
	const activeForKey = rows.filter((row) => row.status === "active" && normalizeKey(row.key) === normalizeKey(key));
	if (activeForKey.length === 0)
		return { code: "binding-no-unique-active", reason: `no active exact-self row for ${key}` };
	if (activeForKey.length > 1)
		return { code: "binding-ambiguous", reason: `multiple active rows for ${key}; authority is ambiguous` };
	const row = activeForKey[0];
	if (row.claimId !== selfClaimId)
		return { code: "binding-foreign", reason: `active claim of ${key} belongs to a foreign window` };
	return { row };
}

function bindingFingerprint(row: IndexEntry): string {
	return `${row.key}|${row.status}|${row.claimId}|${row.phase}|${row.updated}`;
}

/** Trusted host binding built from the authoritative index row (NOT model text).
 *  `owner`/`claim_id` come from the live claim; run/task from the host snapshot. */
function buildBinding(row: IndexEntry, trusted: TrustedHostContext, source: LocalSource): HostBinding {
	const binding: HostBinding = {
		role: trusted.role,
		owner: row.claimId,
		claim_id: row.claimId,
		key: row.key,
		binding_version: trusted.binding_version,
		// Stable persisted identity: one immutable binding per run. The fresh
		// `trusted.observed_at` stays in the trusted context and is re-validated
		// against the real clock on every read; it is deliberately NOT used here.
		observed_at: trusted.binding_established_at ?? trusted.observed_at,
	};
	if (source === "worker-local") {
		binding.task_key = trusted.task_key;
		binding.run_id = trusted.run_id;
	}
	return binding;
}

/** Scope-aware stop using the FROZEN exported scope mappers (no schema fork).
 *  A worker-run deadline never stops a pm; service-request/unknown never blocks
 *  new work; user-global / pm-or-key / matter always do. Diagnostics
 *  (authority/exemption/effect-unknown) never mask a real host stop. */
function hostStopBlocks(hostFacts: HostFacts, role: HostRole): StopScope | undefined {
	const candidates: StopScope[] = [];
	for (const signal of hostFacts.stop_signals ?? []) candidates.push(stopScopeForSignal(signal.kind));
	for (const fact of hostFacts.budget_facts ?? []) candidates.push(stopScopeForBudgetFact(fact.scope));
	for (const scope of candidates) {
		switch (scope) {
			case "user-global":
			case "pm-or-key":
			case "matter":
				return scope;
			case "worker-run":
				if (role !== "pm") return scope;
				break;
			default:
				break;
		}
	}
	return undefined;
}

type Existing<T> =
	| { kind: "absent" }
	| { kind: "corrupt"; reason: string }
	| { kind: "invalid"; reason: string }
	| { kind: "value"; value: T };

/** Byte-level duplicate JSON-object-key detection. `JSON.parse` silently
 *  collapses duplicate keys, so a raw scan over the ORIGINAL bytes is the only
 *  way to refuse ambiguous on-disk records. Keys are decoded through
 *  `JSON.parse` of the string token, so escaped spellings (`"a"` vs
 *  `"\u0061"`) of the same key are also caught. The raw text already passed
 *  `JSON.parse` before this scan runs; an unexpected token ends the scan
 *  conservatively. Returns the first duplicated decoded key, or undefined. */
function findDuplicateJsonKey(raw: string): string | undefined {
	interface ObjectFrame {
		object: boolean;
		keys: Set<string>;
		expectKey: boolean;
	}
	const stack: ObjectFrame[] = [];
	let i = 0;
	const space = (ch: string): boolean => ch === " " || ch === "\t" || ch === "\n" || ch === "\r";
	const readString = (): string | undefined => {
		const start = i;
		i += 1;
		while (i < raw.length) {
			if (raw.charAt(i) === "\\") {
				i += 2;
				continue;
			}
			if (raw.charAt(i) === '"') {
				i += 1;
				try {
					return JSON.parse(raw.slice(start, i)) as string;
				} catch {
					return undefined;
				}
			}
			i += 1;
		}
		return undefined;
	};
	while (i < raw.length) {
		const ch = raw.charAt(i);
		if (space(ch)) {
			i += 1;
			continue;
		}
		if (ch === "{") {
			stack.push({ object: true, keys: new Set<string>(), expectKey: true });
			i += 1;
			continue;
		}
		if (ch === "[") {
			stack.push({ object: false, keys: new Set<string>(), expectKey: false });
			i += 1;
			continue;
		}
		if (ch === "}" || ch === "]") {
			stack.pop();
			i += 1;
			continue;
		}
		if (ch === ",") {
			const top = stack[stack.length - 1];
			if (top?.object) top.expectKey = true;
			i += 1;
			continue;
		}
		if (ch === ":") {
			i += 1;
			continue;
		}
		if (ch === '"') {
			const decoded = readString();
			if (decoded === undefined) return undefined;
			const top = stack[stack.length - 1];
			if (top?.object && top.expectKey) {
				if (top.keys.has(decoded)) return decoded;
				top.keys.add(decoded);
				top.expectKey = false;
			}
			continue;
		}
		// number / true / false / null: skip to the next structural character.
		while (i < raw.length && !space(raw.charAt(i)) && !",}]".includes(raw.charAt(i))) i += 1;
	}
	return undefined;
}

/** Read an existing record: bad JSON / duplicate JSON object keys / wrong
 *  shape / unknown keys / DP fields are reported as corrupt/invalid and NEVER
 *  overwritten. Both the pure read path and every controlled write go through
 *  this check, so a byte-level ambiguous existing can never become a verified
 *  duplicate or a fresh write. */
function inspectExisting<T>(file: string, parse: (value: unknown) => ContractValidation<T>): Existing<T> {
	if (!fs.existsSync(file)) return { kind: "absent" };
	let raw: string;
	try {
		raw = fs.readFileSync(file, "utf8");
	} catch {
		return { kind: "corrupt", reason: "existing file could not be read" };
	}
	let json: unknown;
	try {
		json = JSON.parse(raw);
	} catch {
		return { kind: "corrupt", reason: "existing file is not valid JSON" };
	}
	const duplicateKey = findDuplicateJsonKey(raw);
	if (duplicateKey !== undefined)
		return {
			kind: "corrupt",
			reason: `existing file has a duplicate JSON object key (${duplicateKey}); bytes are ambiguous`,
		};
	const parsed = parse(json);
	if (!parsed.ok) return { kind: "invalid", reason: "existing record has wrong shape / unknown keys / DP fields" };
	return { kind: "value", value: parsed.value };
}

// ── Result builders ────────────────────────────────────────────────────────

function refuse(code: LocalStoreCode, reason: string, gaps: string[] = []): LocalWriteResult {
	return { code, ok: false, verification: "host-context-checked", host_source_verified: false, gaps, reason };
}

function written(record: AnyLocalRecord, file: string, effectState?: "known" | "unknown"): LocalWriteResult {
	return {
		code: "written",
		ok: true,
		verification: "host-context-checked",
		host_source_verified: true,
		...(effectState === undefined ? {} : { effect_state: effectState }),
		record,
		path: file,
		reason: "record persisted atomically after trusted-host checks",
		gaps: [],
	};
}

function duplicate(record: AnyLocalRecord, file: string, effectState?: "known" | "unknown"): LocalWriteResult {
	return {
		code: "duplicate",
		ok: true,
		verification: "host-context-checked",
		host_source_verified: true,
		...(effectState === undefined ? {} : { effect_state: effectState }),
		record,
		path: file,
		reason: "semantically identical record already persisted (idempotent, no new write)",
		gaps: [],
	};
}

function recoveryClue(file: string, record: AnyLocalRecord, reason: string): LocalWriteResult {
	return {
		code: "recovery-clue",
		ok: false,
		verification: "host-context-checked",
		host_source_verified: false,
		path: file,
		recovery_clue: { path: file, record, reason },
		reason,
		gaps: [],
	};
}

/** A refusal that happens AFTER the execution verifier already ran must not
 *  claim the action was unexecuted: the effect may already have happened, only
 *  the mandatory record was not written. Reconcile read-only before retry. */
function afterExecution(failure: LocalWriteResult): LocalWriteResult {
	return {
		...failure,
		reason:
			`${failure.reason}; the execution verifier already ran, so the action may already have been ` +
			"performed (not a known-unexecuted result, no record written; reconcile read-only before any retry)",
	};
}

function effectUnknown(reason: string): LocalWriteResult {
	return {
		code: "effect-unknown",
		ok: false,
		verification: "host-context-checked",
		host_source_verified: false,
		effect_state: "unknown",
		reason,
		gaps: [],
	};
}

function readResult<T>(
	status: LocalReadResult<T>["status"],
	code: LocalStoreCode,
	file: string,
	reason: string,
	record?: T,
): LocalReadResult<T> {
	return {
		verification: "shape-only",
		host_source_verified: false,
		status,
		code,
		...(record === undefined ? {} : { record }),
		reason,
		path: file,
	};
}

// ── Verified context (shared by all three write methods) ────────────────────

interface VerifiedContext {
	trusted: TrustedHostContext;
	budget: MatterBudgetV1;
	hostFacts: HostFacts;
	binding: HostBinding;
	row: IndexEntry;
	role: HostRole;
	/** Immutable SEMANTIC snapshot of the trusted context at read time (a
	 *  string, so a later in-place mutation by the adapter cannot hide a drift).
	 *  Volatile `observed_at` is excluded; freshness/deadline are re-checked
	 *  against the real current clock on every `verifyTrusted` read instead. */
	fingerprint: string;
	/** The finite current-clock reading used for the budget/freshness checks. */
	clock_ms: number;
}

// ── The store ──────────────────────────────────────────────────────────────

export class LocalSelectionStore {
	private readonly root: string;
	private readonly key: string;
	private readonly adapter: LocalSelectionHostAdapter | undefined;
	private readonly write: (file: string, value: unknown) => void;
	private readonly diagnosticLog: string | undefined;
	private readonly lockOptions: LockOptions;
	private readonly indexStore: IndexStore;
	private readonly intentLockPath: string;
	private readonly clock: () => number;

	constructor(config: LocalStoreConfig) {
		this.root = config.agenticdoc_root;
		this.key = config.key;
		this.adapter = config.host_adapter;
		this.write = config.atomic_write ?? atomicWriteJson;
		this.diagnosticLog = config.diagnostic_log;
		this.lockOptions = config.lock_options ?? { retries: 12, baseDelayMs: 4 };
		this.indexStore = new IndexStore(this.root);
		this.intentLockPath = sharedIntentLockPath(this.root);
		this.clock = config.clock ?? (() => Date.now());
	}

	// ── pure shape-only reads (never source verified) ─────────────────────────

	readSelection(req: ReadRequest): LocalReadResult<LocalSelectionRecordV1> {
		return this.readShape(req, SELECTION_FILE_SUFFIX, parseLocalSelectionRecord);
	}

	readExecution(req: ReadRequest): LocalReadResult<LocalExecutionRecordV1> {
		return this.readShape(req, EXECUTION_FILE_SUFFIX, parseLocalExecutionRecord);
	}

	readDisposition(req: ReadRequest): LocalReadResult<PmDisposition> {
		return this.readShape(req, DISPOSITION_FILE_SUFFIX, parsePmDisposition);
	}

	private readShape<T>(
		req: ReadRequest,
		suffix: string,
		parse: (value: unknown) => ContractValidation<T>,
	): LocalReadResult<T> {
		const resolved = resolveLocalPath(this.root, this.key, req.source, req.task_key, req.ref, suffix);
		if ("code" in resolved) return readResult("refused", resolved.code, "", resolved.reason);
		const existing = inspectExisting(resolved.file, parse);
		switch (existing.kind) {
			case "absent":
				return readResult("absent", "absent", resolved.file, "no record at the derived path");
			case "corrupt":
				return readResult("corrupt", "existing-corrupt", resolved.file, existing.reason);
			case "invalid":
				return readResult("invalid-shape", "existing-invalid", resolved.file, existing.reason);
			case "value":
				return readResult("ok", "ok", resolved.file, "shape-only parsed record", existing.value);
		}
	}

	// ── controlled writes ─────────────────────────────────────────────────────

	/** Commit a PLANNED local selection (never an execution). */
	async commitSelection(req: CommitSelectionRequest): Promise<LocalWriteResult> {
		const resolved = resolveLocalPath(
			this.root,
			this.key,
			req.source,
			req.task_key,
			req.local_ref,
			SELECTION_FILE_SUFFIX,
		);
		if ("code" in resolved) return refuse(resolved.code, resolved.reason);
		const { base, file, lockFile } = resolved;
		const locks = await this.acquireWriteLocks(lockFile);
		if ("failure" in locks) return locks.failure;
		try {
			const unstable = pathSafety(this.root, base, file);
			if (unstable !== undefined) return refuse(unstable, "path became unstable under lock");
			const contextRequest: TrustedContextRequest = {
				key: this.key,
				source: req.source,
				ref: req.local_ref,
				task_key: req.task_key,
				run_id: req.run_id,
				write_kind: "selection",
			};
			const verified = await this.verifyTrusted(contextRequest);
			if ("code" in verified) return verified;
			const input: LocalBusinessSelectionInput = {
				...req.selection,
				source: req.source,
				local_ref: req.local_ref,
				host: verified.hostFacts,
				budget: verified.budget,
			};
			const validation = validateLocalBusinessSelection(input);
			if (!validation.ok) {
				const stop = validation.issues.some((issue) => issue.field.includes("stop_signals"));
				return refuse(
					stop ? "stop-scope-blocked" : "selection-invalid",
					`planned selection rejected: ${validation.issues.map((issue) => issue.field).join(", ")}`,
					validation.gaps,
				);
			}
			const record = validation.value;
			const drift = this.crossCheckExpected(record, verified.trusted.expected);
			if (drift !== undefined) return refuse(drift, "current host expectation drift");
			// NO existing/duplicate verdict before the final awaited recheck: the
			// last trusted context read may have introduced a corrupt existing, a
			// stop, a clock/budget expiry, a path redirect or a binding change. A
			// verified duplicate must pass the SAME final checks as a fresh write,
			// and an absent path can have gained bad bytes during that await.
			const final = await this.finalRecheck(verified, contextRequest, undefined, [resolved]);
			if ("code" in final) return final;
			const finalDrift = this.crossCheckExpected(record, final.trusted.expected);
			if (finalDrift !== undefined) return refuse(finalDrift, "current host expectation drift after final recheck");
			// All checks below are SYNCHRONOUS, after the LAST host await; the write
			// follows immediately so no stale pre-await safety conclusion is reused.
			const existing = inspectExisting(file, parseLocalSelectionRecord);
			const existingVerdict = this.classifyExisting(existing, file, final.binding, record);
			if (existingVerdict !== undefined) return existingVerdict;
			const recheck = this.recheckBinding(final.row);
			if (recheck !== undefined) return refuse(recheck, "authoritative binding changed before commit");
			try {
				this.write(file, record);
			} catch (err) {
				return refuse(
					"write-failed",
					`mandatory selection record not persisted (${errCode(err)}); no controlled effect`,
				);
			}
			this.diagnose(`commitSelection written ${req.local_ref}`);
			return written(record, file);
		} finally {
			locks.releaseAll();
		}
	}

	/** Append a REAL execution record (physically separate) only after the
	 *  original selection is consistent and a host verifier produced proof. */
	async appendExecution(req: AppendExecutionRequest): Promise<LocalWriteResult> {
		const selectionPath = resolveLocalPath(
			this.root,
			this.key,
			req.source,
			req.task_key,
			req.local_ref,
			SELECTION_FILE_SUFFIX,
		);
		const executionPath = resolveLocalPath(
			this.root,
			this.key,
			req.source,
			req.task_key,
			req.local_ref,
			EXECUTION_FILE_SUFFIX,
		);
		if ("code" in selectionPath) return refuse(selectionPath.code, selectionPath.reason);
		if ("code" in executionPath) return refuse(executionPath.code, executionPath.reason);
		const locks = await this.acquireWriteLocks(executionPath.lockFile);
		if ("failure" in locks) return locks.failure;
		try {
			const unstable = pathSafety(this.root, executionPath.base, executionPath.file);
			if (unstable !== undefined) return refuse(unstable, "path became unstable under lock");
			const contextRequest: TrustedContextRequest = {
				key: this.key,
				source: req.source,
				ref: req.local_ref,
				task_key: req.task_key,
				run_id: req.run_id,
				write_kind: "execution",
			};
			const correlation: TerminalWriteCorrelation = {
				source: req.source,
				ref: req.local_ref,
				task_key: req.task_key,
				run_id: req.run_id,
				action_ref: req.action_ref,
				result_ref: req.result_ref,
				executor: req.executor,
				observed_effect: req.observed_effect,
			};
			const verified = await this.verifyTrusted(contextRequest, correlation);
			if ("code" in verified) return verified;
			if (
				verified.trusted.executed_action !== undefined &&
				!terminalExecutionMatches(verified.trusted.executed_action, this.key, req)
			)
				return refuse(
					"selection-invalid",
					"terminal proof does not match this exact executed action/result/effect",
				);
			const originalExisting = inspectExisting(selectionPath.file, parseLocalSelectionRecord);
			if (originalExisting.kind === "absent")
				return refuse("selection-invalid", "no original selection for this local_ref");
			if (originalExisting.kind !== "value")
				return refuse(
					"existing-invalid",
					"original selection is corrupt/invalid (selection masquerading as execution rejected)",
				);
			const original = originalExisting.value;
			const originalVerdict = this.originalVerdict(original, verified, req);
			if (originalVerdict !== undefined) return originalVerdict;
			if (this.adapter === undefined || this.adapter.verifyExecution === undefined)
				return refuse("verifier-missing", "no execution verifier; no execution record written", [
					"verifyExecution",
				]);
			let proof: ExecutionProof | undefined;
			try {
				proof = await this.adapter.verifyExecution({
					key: this.key,
					source: req.source,
					local_ref: req.local_ref,
					action_ref: req.action_ref,
					result_ref: req.result_ref,
					executor: req.executor,
					observed_effect: req.observed_effect,
					...(verified.trusted.expected.target_digest === undefined
						? {}
						: { expected_target_digest: verified.trusted.expected.target_digest }),
					binding: verified.binding,
				});
			} catch {
				return refuse("verifier-unproven", "execution verifier threw; fail closed", ["verifyExecution"]);
			}
			if (proof === undefined)
				return refuse("verifier-unproven", "execution verifier returned no proof", ["verifyExecution"]);
			if (
				proof.action_ref !== req.action_ref ||
				proof.result_ref !== req.result_ref ||
				proof.local_ref !== req.local_ref ||
				proof.executor !== req.executor ||
				!nonblank(proof.verifier_ref) ||
				!nonblank(proof.target_digest)
			)
				return refuse("verifier-unproven", "verifier proof does not correlate with the requested action/result");
			// R4 (RV1 F1): the request explicitly submits observed_effect, so the
			// proof must describe that EXACT observation. Matching text is not
			// evidence: the host verifier still owns the proof, target, verifier
			// identity and known/unknown state. This synchronous check precedes the
			// immutable snapshot and the last host await; it adds no later await.
			if (proof.observed_effect !== req.observed_effect)
				return afterExecution(
					refuse(
						"verifier-unproven",
						"verifier proof observed_effect does not exactly match the requested observed_effect",
					),
				);
			// R3 (R2-TS-P1): the adapter OWNS `proof` and may return a SHARED MUTABLE
			// object. A later host callback (the finalRecheck context read) must not be
			// able to swap the already-validated identity/effect facts in place. Capture
			// an immutable, request-correlated snapshot of every field into OUR OWN
			// frozen object of primitive strings BEFORE the last host await. After that
			// await the adapter-owned mutable `proof` is NEVER read again: the record is
			// built ONLY from this snapshot, so bindings cannot be swapped and an
			// original `unknown` effect cannot be promoted by a non-verifier callback.
			const verifiedProof: Readonly<ExecutionProof> = Object.freeze({
				action_ref: proof.action_ref,
				result_ref: proof.result_ref,
				verifier_ref: proof.verifier_ref,
				target_digest: proof.target_digest,
				observed_effect: proof.observed_effect,
				effect_state: proof.effect_state,
				local_ref: proof.local_ref,
				executor: proof.executor,
			});
			if (
				verified.trusted.expected.target_digest !== undefined &&
				verifiedProof.target_digest !== verified.trusted.expected.target_digest
			)
				return refuse("target-drift", "target digest drift");
			// The verifier was AWAITED: material/basis/budget/stop/run/target,
			// the index, the paths and the clock may all have changed meanwhile.
			// Re-read the trusted context and all preconditions before writing.
			const final = await this.finalRecheck(verified, contextRequest, correlation, [selectionPath, executionPath]);
			if ("code" in final) return afterExecution(final);
			if (
				final.trusted.executed_action !== undefined &&
				!terminalExecutionMatches(final.trusted.executed_action, this.key, req)
			)
				return afterExecution(
					refuse("selection-invalid", "terminal proof drifted after the final trusted context read"),
				);
			const finalExisting = inspectExisting(selectionPath.file, parseLocalSelectionRecord);
			if (finalExisting.kind !== "value")
				return afterExecution(
					refuse("existing-invalid", "original selection changed during execution verification"),
				);
			const finalOriginalVerdict = this.originalVerdict(finalExisting.value, final, req);
			if (finalOriginalVerdict !== undefined) return afterExecution(finalOriginalVerdict);
			if (
				final.trusted.expected.target_digest !== undefined &&
				verifiedProof.target_digest !== final.trusted.expected.target_digest
			)
				return afterExecution(refuse("target-drift", "target digest drift detected after execution verification"));
			const execRecord: LocalExecutionRecordV1 = {
				schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
				kind: "local-execution",
				origin: "local-decision",
				source: req.source,
				local_ref: req.local_ref,
				host_binding: final.binding,
				action_ref: verifiedProof.action_ref,
				result_ref: verifiedProof.result_ref,
				executor: verifiedProof.executor,
				target_digest: verifiedProof.target_digest,
				observed_effect: verifiedProof.observed_effect,
				effect_state: verifiedProof.effect_state,
				verified_by: verifiedProof.verifier_ref,
				budget_ref: finalExisting.value.budget_ref,
				created_at: req.created_at,
			};
			const shape = parseLocalExecutionRecord(execRecord);
			if (!shape.ok)
				return afterExecution(
					refuse("execution-invalid", "execution record failed strict shape validation", shape.gaps),
				);
			// Synchronous, AFTER `finalRecheck` (the last host await): a corrupt
			// existing execution record may have appeared during that await, so the
			// duplicate/existing verdict is taken from the CURRENT bytes, never from
			// a pre-await classification. Effect-unknown is retained because the
			// verifier already ran (the action may have happened).
			const existing = inspectExisting(executionPath.file, parseLocalExecutionRecord);
			const existingVerdict = this.classifyExisting(existing, executionPath.file, final.binding, shape.value);
			if (existingVerdict !== undefined)
				return existingVerdict.ok ? existingVerdict : afterExecution(existingVerdict);
			const recheck = this.recheckBinding(final.row);
			if (recheck !== undefined)
				return afterExecution(refuse(recheck, "authoritative binding changed before commit"));
			try {
				this.write(executionPath.file, shape.value);
			} catch {
				return effectUnknown(
					"action may already have been performed but the mandatory execution record write failed; " +
						"reconcile the real object/queue read-only before any retry (not unexecuted, not written)",
				);
			}
			this.diagnose(`appendExecution written ${req.local_ref}`);
			return written(shape.value, executionPath.file, shape.value.effect_state);
		} finally {
			locks.releaseAll();
		}
	}

	/** Persist a necessary PmDisposition to its own physically separate file. */
	async saveDisposition(req: SaveDispositionRequest): Promise<LocalWriteResult> {
		const resolved = resolveLocalPath(
			this.root,
			this.key,
			req.source,
			req.task_key,
			req.disposition_ref,
			DISPOSITION_FILE_SUFFIX,
		);
		if ("code" in resolved) return refuse(resolved.code, resolved.reason);
		const { base, file, lockFile } = resolved;
		const locks = await this.acquireWriteLocks(lockFile);
		if ("failure" in locks) return locks.failure;
		try {
			const unstable = pathSafety(this.root, base, file);
			if (unstable !== undefined) return refuse(unstable, "path became unstable under lock");
			const contextRequest: TrustedContextRequest = {
				key: this.key,
				source: req.source,
				ref: req.disposition_ref,
				task_key: req.task_key,
				run_id: req.run_id,
				write_kind: "disposition",
			};
			const correlation: TerminalWriteCorrelation = {
				source: req.source,
				ref: req.disposition_ref,
				task_key: req.task_key,
				run_id: req.run_id,
			};
			const verified = await this.verifyTrusted(contextRequest, correlation);
			if ("code" in verified) return verified;
			const shape = parsePmDisposition(req.disposition);
			if (!shape.ok) return refuse("disposition-invalid", "disposition failed strict shape validation", shape.gaps);
			const record = shape.value;
			if (record.disposition_ref !== req.disposition_ref)
				return refuse("disposition-invalid", "disposition_ref does not match the derived path");
			if (bindingIdentityDrifts(record.binding, verified.binding) || record.owner !== verified.binding.owner)
				return refuse("binding-stale-owner", "disposition binding/owner drift");
			if (record.matter_ref !== verified.trusted.expected.matter_ref)
				return refuse("matter-drift", "disposition matter drift");
			if (record.budget_ref !== verified.trusted.expected.budget_ref)
				return refuse("budget-invalid", "disposition budget_ref drift");
			if (
				verified.trusted.executed_action !== undefined &&
				!terminalDispositionMatches(verified.trusted.executed_action, this.key, req, record)
			)
				return refuse(
					"disposition-invalid",
					"terminal proof does not match this exact action/result/owner/budget disposition",
				);
			// No existing/duplicate early return: a verified duplicate must still
			// pass the final trusted context / index / real clock / budget / stop /
			// path / record checks after the LAST awaited host callback.
			const final = await this.finalRecheck(verified, contextRequest, correlation, [resolved]);
			if ("code" in final) return final;
			if (
				final.trusted.executed_action !== undefined &&
				!terminalDispositionMatches(final.trusted.executed_action, this.key, req, record)
			)
				return refuse("disposition-invalid", "terminal proof drifted after the final trusted context read");
			if (record.matter_ref !== final.trusted.expected.matter_ref)
				return refuse("matter-drift", "disposition matter drift after final recheck");
			if (record.budget_ref !== final.trusted.expected.budget_ref)
				return refuse("budget-invalid", "disposition budget_ref drift after final recheck");
			if (bindingIdentityDrifts(record.binding, final.binding) || record.owner !== final.binding.owner)
				return refuse("binding-stale-owner", "disposition binding/owner drift after final recheck");
			// Synchronous, after the last await: re-classify the CURRENT existing
			// (bad bytes may have appeared during the await) against the fresh binding.
			const existing = inspectExisting(file, parsePmDisposition);
			const existingVerdict = this.classifyExisting(existing, file, final.binding, record);
			if (existingVerdict !== undefined) return existingVerdict;
			const recheck = this.recheckBinding(final.row);
			if (recheck !== undefined) return refuse(recheck, "authoritative binding changed before commit");
			try {
				this.write(file, record);
			} catch (err) {
				return refuse("write-failed", `mandatory disposition record not persisted (${errCode(err)})`);
			}
			this.diagnose(`saveDisposition written ${req.disposition_ref}`);
			return written(record, file);
		} finally {
			locks.releaseAll();
		}
	}

	// ── shared internals ──────────────────────────────────────────────────────

	/** Shared intent lock FIRST, then the per-record local lock; reverse release.
	 *  Both use the existing O_EXCL `acquireLock` (Windows `wx` behaviour). */
	private async acquireWriteLocks(
		localLockFile: string,
	): Promise<{ releaseAll: () => void } | { failure: LocalWriteResult }> {
		let releaseIntent: (() => void) | undefined;
		try {
			releaseIntent = await acquireLock(this.intentLockPath, this.lockOptions);
		} catch {
			return { failure: refuse("lock-busy", "shared intent lock busy") };
		}
		let releaseLocal: (() => void) | undefined;
		try {
			releaseLocal = await acquireLock(localLockFile, this.lockOptions);
		} catch {
			releaseIntent();
			return { failure: refuse("lock-busy", "local record lock busy") };
		}
		const relIntent = releaseIntent;
		const relLocal = releaseLocal;
		return {
			releaseAll: () => {
				try {
					relLocal();
				} finally {
					relIntent();
				}
			},
		};
	}

	/** Fail-closed trusted-context verification. Reads the authoritative binding
	 *  itself, validates the finite budget and the REAL reservation preflight,
	 *  and enforces scope-aware stops. Never minted, never defaulted. */
	private async verifyTrusted(
		request: TrustedContextRequest,
		correlation?: TerminalWriteCorrelation,
	): Promise<VerifiedContext | LocalWriteResult> {
		const source = request.source;
		const ref = request.ref;
		const taskKey = request.task_key;
		const runId = request.run_id;
		const writeKind = request.write_kind ?? "selection";
		if (request.key !== this.key) return refuse("binding-foreign", "trusted context key does not match this store");
		if (this.adapter === undefined)
			return refuse("trusted-context-missing", "no trusted host adapter; controlled write refused", [
				"host_adapter",
			]);
		let trusted: TrustedHostContext | undefined;
		try {
			trusted = await this.adapter.readTrustedContext({
				key: this.key,
				source,
				ref,
				task_key: taskKey,
				run_id: runId,
				write_kind: writeKind,
			});
		} catch {
			return refuse("trusted-context-refused", "trusted host adapter threw; fail closed", ["readTrustedContext"]);
		}
		if (trusted === undefined || trusted === null)
			return refuse("trusted-context-refused", "trusted host context unavailable; fail closed", [
				"readTrustedContext",
			]);
		if (!nonblank(trusted.self_claim_id))
			return refuse("trusted-context-refused", "exact self claim id missing", ["self_claim_id"]);
		const role = trusted.role;
		if (source === "pm" && role !== "pm") return refuse("binding-foreign", "pm source requires host role pm");
		if (source === "worker-local" && role !== "coding" && role !== "research" && role !== "review")
			return refuse("binding-foreign", "worker-local source requires a worker host role");
		if (source === "worker-local") {
			if (!trusted.task_key || !trusted.run_id)
				return refuse("binding-stale-run", "worker-local requires current task/run in the trusted context");
			if (taskKey !== undefined && trusted.task_key !== taskKey)
				return refuse("binding-stale-run", "task_key drift");
			if (runId !== undefined && trusted.run_id !== runId) return refuse("binding-stale-run", "run_id drift");
		}
		const rowResult = resolveAuthoritativeRow(this.indexStore, this.key, trusted.self_claim_id);
		if ("code" in rowResult) return refuse(rowResult.code, rowResult.reason);
		const row = rowResult.row;
		const budgetResult = validateMatterBudget(trusted.budget);
		if (!budgetResult.ok)
			return refuse(
				"budget-invalid",
				"matter budget missing / non-finite / no provenance",
				budgetResult.gaps.length ? budgetResult.gaps : ["budget"],
			);
		const budget = budgetResult.value;
		if (budget.matter_ref !== trusted.expected?.matter_ref)
			return refuse("budget-invalid", "budget matter_ref does not match the expected matter");
		// The snapshot timestamp is NOT the current clock. A past `observed_at`
		// with a past deadline must not authorize a commit made today, and a
		// stale snapshot must not authorize a still-future deadline either.
		const nowMs = this.clock();
		if (!Number.isFinite(nowMs))
			return refuse("trusted-context-refused", "trusted clock is not a finite epoch reading; no unlimited default", [
				"clock",
			]);
		const observedMs = Date.parse(trusted.observed_at);
		const deadlineMs = Date.parse(budget.deadline);
		if (!nonblank(trusted.observed_at) || !Number.isFinite(observedMs))
			return refuse("trusted-context-refused", "trusted snapshot observed_at is not a valid finite timestamp", [
				"observed_at",
			]);
		if (!Number.isFinite(deadlineMs))
			return refuse("budget-invalid", "matter budget deadline is not a finite timestamp", ["deadline"]);
		if (observedMs > nowMs || nowMs - observedMs > MAX_TRUSTED_CONTEXT_AGE_MS)
			return refuse(
				"trusted-context-refused",
				"trusted snapshot is stale or dated in the future relative to the current clock",
				["observed_at"],
			);
		if (trusted.budget_preflight === undefined || trusted.budget_preflight === null)
			return refuse("budget-preflight-missing", "no real budget/reservation preflight; fillable gap", [
				"budget_preflight",
			]);
		const preflight = parseBudgetReservationResult(trusted.budget_preflight);
		if (!preflight.ok)
			return refuse("budget-preflight-missing", "preflight result shape invalid", ["budget_preflight"]);
		const terminalAllowed = terminalExceptionAllowed({
			proof: trusted.executed_action,
			key: this.key,
			writeKind,
			request,
			correlation,
			trusted,
			budget,
			preflight: preflight.value,
			rowClaimId: row.claimId,
			role,
			observedMs,
			nowMs,
			deadlineMs,
		});
		if (
			budget.remaining_cost <= 0 ||
			budget.steps_consumed >= budget.max_steps ||
			budget.no_progress_count >= budget.no_progress_limit ||
			observedMs >= deadlineMs ||
			nowMs >= deadlineMs
		) {
			if (!terminalAllowed)
				return refuse(
					"budget-exhausted",
					"finite budget exhausted / deadline passed at the current clock; no new controlled write",
				);
		}
		if ((!preflight.value.granted || preflight.value.reason !== "granted") && !terminalAllowed)
			return refuse("budget-preflight-denied", "preflight not granted; no default grant");
		const binding = buildBinding(row, trusted, source);
		const hostFacts: HostFacts = {
			binding,
			...(trusted.stop_signals === undefined ? {} : { stop_signals: trusted.stop_signals }),
			...(trusted.budget_facts === undefined ? {} : { budget_facts: trusted.budget_facts }),
			...(trusted.authority_gap === undefined ? {} : { authority_gap: trusted.authority_gap }),
			...(trusted.exemption === undefined ? {} : { exemption: trusted.exemption }),
			...(trusted.effect_unknown === undefined ? {} : { effect_unknown: trusted.effect_unknown }),
		};
		const stop = hostStopBlocks(hostFacts, role);
		if (stop !== undefined) return refuse("stop-scope-blocked", `host ${stop} stop forbids new writes/actions`);
		return {
			trusted,
			budget,
			hostFacts,
			binding,
			row,
			role,
			fingerprint: semanticContextFingerprint(trusted),
			clock_ms: nowMs,
		};
	}

	/** Cross-check the produced/original record against the host's CURRENT
	 *  expected matter/material/basis/parent/budget (drift ⇒ fail closed). */
	private crossCheckExpected(record: LocalSelectionRecordV1, expected: ExpectedHostFacts): LocalStoreCode | undefined {
		if (record.matter_ref !== expected.matter_ref) return "matter-drift";
		if (record.matter_version !== expected.matter_version) return "matter-drift";
		if (record.budget_ref !== expected.budget_ref) return "budget-invalid";
		if (record.material_digest !== expected.material_digest) return "material-drift";
		if (record.basis_digest !== expected.basis_digest) return "basis-drift";
		if ((expected.parent_decision_id ?? undefined) !== record.parent_decision_ref?.decision_id) return "parent-drift";
		return undefined;
	}

	/** Duplicate = canonical semantic equal. Conflict = any decision-field
	 *  difference. Corrupt/invalid/foreign-or-old-run existing ⇒ reject and never
	 *  overwrite. Returns undefined when the file is absent (safe to write). */
	private classifyExisting<T extends AnyLocalRecord>(
		existing: Existing<T>,
		file: string,
		binding: HostBinding,
		record: T,
	): LocalWriteResult | undefined {
		if (existing.kind === "absent") return undefined;
		if (existing.kind === "corrupt") return refuse("existing-corrupt", `${existing.reason}; not overwritten`);
		if (existing.kind === "invalid") return refuse("existing-invalid", `${existing.reason}; not overwritten`);
		const old = existing.value;
		const value: AnyLocalRecord = old;
		const oldBinding = "host_binding" in value ? value.host_binding : "binding" in value ? value.binding : undefined;
		if (oldBinding !== undefined && bindingIdentityDrifts(oldBinding, binding))
			return recoveryClue(
				file,
				old,
				"existing record belongs to a previous owner/run/binding; read-only recovery clue, never overwritten or replayed",
			);
		if (semanticKey(old) === semanticKey(record)) return duplicate(record, file);
		return refuse("conflict", "conflicting choice/basis/material for the same ref; not overwritten");
	}

	/** Exact association of the original selection with BOTH the request and
	 *  the current trusted identity. Shape validity alone is not association: a
	 *  valid record for another ref/source/key/task/run at this filename must
	 *  not authorize an execution for the requested identity. Absent↔present
	 *  task/run differences are drift too. */
	private originalVerdict(
		original: LocalSelectionRecordV1,
		verified: VerifiedContext,
		req: AppendExecutionRequest,
	): LocalWriteResult | undefined {
		if (
			original.local_ref !== req.local_ref ||
			original.source !== req.source ||
			normalizeKey(original.host_binding.key ?? "") !== normalizeKey(this.key) ||
			(req.task_key ?? undefined) !== (original.host_binding.task_key ?? undefined) ||
			(req.run_id ?? undefined) !== (original.host_binding.run_id ?? undefined)
		)
			return refuse(
				"selection-invalid",
				"original selection identity (ref/source/key/task/run) does not match the requested execution",
			);
		if (bindingIdentityDrifts(original.host_binding, verified.binding))
			return refuse("binding-stale-owner", "original selection belongs to an old owner/run");
		const consistency = compareLocalSelectionToHost(original, verified.hostFacts);
		if (!consistency.ok) {
			const stop = consistency.issues.some((issue) => issue.field.includes("stop_signals"));
			return refuse(
				stop ? "stop-scope-blocked" : "selection-invalid",
				`selection inconsistent with current host: ${consistency.issues.map((issue) => issue.field).join(", ")}`,
				consistency.issues.map((issue) => issue.field),
			);
		}
		const drift = this.crossCheckExpected(original, verified.trusted.expected);
		if (drift !== undefined) return refuse(drift, "current host expectation drift");
		return undefined;
	}

	/** Final pre-commit recheck: re-read the trusted host context and the
	 *  authoritative index AFTER any awaited verifier, re-check the derived
	 *  paths, the finite clock/deadline and the immutable semantic snapshot, and
	 *  refuse on ANY drift or missing context. The path-ancestor/file-kind/link
	 *  check is repeated AFTER the LAST awaited host callback, so a real directory
	 *  rename + junction made inside that callback is refused with no outside
	 *  write. `verifyTrusted` here is the LAST host await: callers must only run
	 *  synchronous checks and then write, never await the host again with a stale
	 *  safety conclusion. Returns the fresh verified context on success. */
	private async finalRecheck(
		initial: VerifiedContext,
		req: TrustedContextRequest,
		correlation: TerminalWriteCorrelation | undefined,
		paths: readonly LocalPath[],
	): Promise<VerifiedContext | LocalWriteResult> {
		for (const target of paths) {
			const unstable = pathSafety(this.root, target.base, target.file);
			if (unstable !== undefined) return refuse(unstable, "path became unstable before commit");
		}
		const again = await this.verifyTrusted(req, correlation);
		if ("code" in again) return again;
		if (again.clock_ms < initial.clock_ms)
			return refuse("trusted-context-refused", "trusted clock went backwards before commit");
		if (
			again.fingerprint !== initial.fingerprint ||
			bindingFingerprint(again.row) !== bindingFingerprint(initial.row)
		)
			return refuse(
				"trusted-context-refused",
				"trusted host context (material/basis/budget/stop/run/target) or authoritative binding drifted before commit",
			);
		// AFTER the last trusted host callback: synchronously re-verify path
		// ancestors, file kind and junction/link containment. A rename + real
		// junction performed by that callback is caught here, before any write.
		for (const target of paths) {
			const unstable = pathSafety(this.root, target.base, target.file);
			if (unstable !== undefined)
				return refuse(unstable, "path became unstable after the final trusted context read");
		}
		return again;
	}

	/** "Re-read then commit": re-resolve the authoritative row just before the
	 *  write and refuse if the binding drifted while we held the intent lock. */
	private recheckBinding(row: IndexEntry): LocalStoreCode | undefined {
		const again = resolveAuthoritativeRow(this.indexStore, this.key, row.claimId);
		if ("code" in again) return again.code;
		if (bindingFingerprint(again.row) !== bindingFingerprint(row)) return "binding-stale-owner";
		return undefined;
	}

	/** Best-effort diagnostic log: a failure here NEVER changes the result. */
	private diagnose(message: string): void {
		if (this.diagnosticLog === undefined) return;
		try {
			fs.appendFileSync(this.diagnosticLog, `${new Date().toISOString()} ${message}\n`, "utf8");
		} catch {
			// Diagnostic write failure is isolated; it never stops the PM.
		}
	}
}

// Re-exported identity for consumers that assert the frozen schema id.
export const LOCAL_STORE_SCHEMA_ID = DECISION_HANDOFF_SCHEMA_ID;
