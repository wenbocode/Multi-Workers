import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import type { PreparedBasis } from "../shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.ts";
import type {
	JsonValue,
	LocalExecutionRecordV1,
	LocalSelectionRecordV1,
	LocalSource,
} from "../shared/decision-handoff.ts";
import { acquireLock } from "../shared/file-lock.ts";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.ts";
import { canonicalStateJson } from "./triage-client.ts";

const TARGET_DPS = ["dp-pm-steer", "dp-auto"] as const;
const INTENT_STATUSES = ["prepared", "requesting", "answered", "failed", "executed"] as const;
const TASK_STATUSES = [
	"not-queued",
	"pending",
	"running",
	"done",
	"failed",
	"needs-clarification",
	"lost",
	"unknown",
] as const;

type TargetDp = (typeof TARGET_DPS)[number];
type IntentStatus = (typeof INTENT_STATUSES)[number];
export type FollowupTaskStatus = (typeof TASK_STATUSES)[number];

export interface BoundPmIdentity {
	role: "pm";
	key: string;
	window_id: string;
}

export interface DecisionFollowupIntent {
	schema_version: 1;
	parent_ref: string;
	parent_logical_id: string;
	parent_decision_id: string;
	parent_matter_version: string;
	target_dp: TargetDp;
	material_version: string;
	basis_version: string;
	owner_key: string;
	task_key: string | null;
	prepared_by: BoundPmIdentity;
	restricted_action: string;
	restricted_executor: string;
	status: IntentStatus;
	request_ref: string | null;
	answer: string | null;
	failure_reason: string | null;
	/** F2: the frozen NATIVE transport/effect facts of the real failed reply,
	 *  retained so a later ordinary ingress can re-read them instead of inferring
	 *  from the reason string. Absent/unknown keeps an unchanged failure refused. */
	effect_facts?: DecisionEffectFacts;
	/** F2/P1-01 (host-minted witness): digest THIS host minted when it wrote this
	 *  failed row from a reply it observed itself. Binding value only, NEVER
	 *  authority: a row whose digest does not equal this process's own observation
	 *  of THIS intent is unauthenticated coordination state (unknown, no resend).
	 *  A rewritten counter set, a rewritten/foreign digest or a row copied onto a
	 *  path this host never wrote all fail this check. Deliberately
	 *  process-lifetime: authenticating a positive across a host restart needs a
	 *  signed effect token or a zero-transport lifecycle query, neither of which
	 *  exists in this surface, so a restart fails closed instead of trusting a row. */
	effect_witness?: string;
	action_evidence?: string;
}

/** Obtained from the current gate, prepared material, and bound PM window. */
export type ExpectedDecisionFollowup = Pick<DecisionFollowupIntent, (typeof BINDING_FIELDS)[number]>;

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
] as const;

/** This scope comes from the host, never the prepared intent or a tool argument. */
type LifecycleScope =
	| { projectDir: string; parentEvidence?: { pmNote: string; modelBasis: string; stageNoteEvent?: string } }
	| { isolatedTestRoot: string; projectId: string };

export type DecisionFollowupRequestResult =
	| { available: true; request_ref: string; answer: string }
	| { available: false; reason: string; effect_facts?: unknown };

/** The frozen wire/effect facts of one real request result. `0` attempts and 0
 *  transport attempts with no business decision and no replay is the ONLY
 *  positive no-effect fact set; anything else (or an absent set) is unknown. */
export interface DecisionEffectFacts {
	attempts: number;
	transport_attempts: number;
	business_decisions: number;
	replayed: boolean;
}

export type FollowupFailureEffect = "known-no-effect" | "unknown";

function normalizeEffectFacts(value: unknown): DecisionEffectFacts | undefined {
	if (!isRecord(value)) return undefined;
	const { attempts, transport_attempts, business_decisions, replayed } = value;
	if (
		!Number.isInteger(attempts) ||
		!Number.isInteger(transport_attempts) ||
		!Number.isInteger(business_decisions) ||
		typeof replayed !== "boolean"
	)
		return undefined;
	return {
		attempts: attempts as number,
		transport_attempts: transport_attempts as number,
		business_decisions: business_decisions as number,
		replayed,
	};
}

/** Positive only for a fully retained, zero-attempt/zero-business fact set.
 *  Missing, malformed or effect-bearing facts stay the conservative unknown
 *  that the ordinary ingress keeps refusing. */
export function failureEffectVerdict(value: unknown): FollowupFailureEffect {
	const facts = normalizeEffectFacts(value);
	if (facts === undefined || facts.replayed) return "unknown";
	return facts.attempts === 0 && facts.transport_attempts === 0 && facts.business_decisions === 0
		? "known-no-effect"
		: "unknown";
}

/** Host-owned observations of failed replies this process itself produced. The
 *  key is the intent path this host wrote; the value is the digest it minted.
 *  Only a value minted here can authenticate a retained fact set. There is no
 *  read/write tool for it, it never grants anything, and it can only ever move
 *  a verdict TOWARD the conservative unknown. */
const observedEffectWitnesses = new Map<string, string>();

function effectWitnessKey(intentPath: string): string {
	return path.resolve(intentPath);
}

/** Digest over the substantive failed-row content: the eleven binding fields,
 *  the bound preparer, the frozen reason and the frozen fact set. Observation
 *  fields (timestamps, tool calls) are excluded, so a rewrite of the counters or
 *  of the digest itself no longer reproduces this value. */
function effectWitnessDigest(
	intent: DecisionFollowupIntent,
	reason: string,
	facts: DecisionEffectFacts | undefined,
): string {
	return createHash("sha256")
		.update(
			JSON.stringify({
				schema: 1,
				parent_ref: intent.parent_ref,
				parent_logical_id: intent.parent_logical_id,
				parent_decision_id: intent.parent_decision_id,
				parent_matter_version: intent.parent_matter_version,
				material_version: intent.material_version,
				basis_version: intent.basis_version,
				target_dp: intent.target_dp,
				owner_key: intent.owner_key,
				task_key: intent.task_key,
				restricted_action: intent.restricted_action,
				restricted_executor: intent.restricted_executor,
				prepared_by: {
					role: intent.prepared_by.role,
					key: intent.prepared_by.key,
					window_id: intent.prepared_by.window_id,
				},
				status: "failed",
				failure_reason: reason,
				effect_facts:
					facts === undefined
						? null
						: {
								attempts: facts.attempts,
								transport_attempts: facts.transport_attempts,
								business_decisions: facts.business_decisions,
								replayed: facts.replayed,
							},
			}),
		)
		.digest("hex");
}

/** True only while this process's own write of THIS intent path still describes
 *  these exact bytes: the row carries the digest we minted AND the digest the
 *  row's current counters/reason re-compute to is that same value. */
function effectWitnessCurrent(intentPath: string, intent: DecisionFollowupIntent, reason: string): boolean {
	const observed = observedEffectWitnesses.get(effectWitnessKey(intentPath));
	if (observed === undefined || intent.effect_witness !== observed) return false;
	return effectWitnessDigest(intent, reason, normalizeEffectFacts(intent.effect_facts)) === observed;
}

export interface DecisionFollowupResult {
	state: "not-started" | "in-progress" | "answered" | "failed" | "executed" | "blocked" | "unknown";
	reason?: string;
	request_ref?: string;
	answer?: string;
	basis_id?: string;
	request_started: boolean;
	duplicate: boolean;
	parent_released: false;
	/** F2: re-read effect verdict of an unchanged persisted failure. Never a
	 *  reason-only inference; only present for a `failed` result. */
	failure_effect?: FollowupFailureEffect;
	/** Set ONLY by the discriminated local path; the DP path leaves these absent. */
	verified_source?: "dp" | "local";
	ref?: string;
	action?: string;
	evidence?: string;
	local_progress?: LocalFollowupProgress;
}

interface ResumeInput {
	intent_path: string;
	expected: ExpectedDecisionFollowup;
	bound_pm: BoundPmIdentity | null;
	observe_task: (ownerKey: string, taskKey: string | null) => FollowupTaskStatus;
	request: (intent: Readonly<DecisionFollowupIntent>) => Promise<DecisionFollowupRequestResult>;
	lifecycle?: LifecycleScope;
}

interface ExecutedInput {
	intent_path: string;
	expected: ExpectedDecisionFollowup;
	bound_pm: BoundPmIdentity | null;
	request_ref: string;
	action_evidence: string;
	lifecycle?: LifecycleScope;
}

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

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonEmpty(value: unknown): value is string {
	return typeof value === "string" && value.trim() !== "" && !value.includes("\0");
}

function isBoundPm(value: unknown): value is BoundPmIdentity {
	return (
		isRecord(value) &&
		value.role === "pm" &&
		nonEmpty(value.key) &&
		nonEmpty(value.window_id) &&
		Object.keys(value).length === 3
	);
}

function parseIntent(file: string): DecisionFollowupIntent | undefined {
	let raw: string;
	try {
		raw = fs.readFileSync(file, "utf8");
	} catch {
		return undefined;
	}
	// P1-01: duplicated members are ambiguous RAW evidence. JSON.parse keeps only
	// the LAST member of a duplicated key, so a strictly shaped parsed value can
	// hide contradictory or effect-bearing bytes. An intent whose original text
	// is ambiguous (or malformed) is never authority; it is refused before any
	// field is read.
	if (hasDuplicateJsonMembers(raw)) return undefined;
	let value: unknown;
	try {
		value = JSON.parse(raw);
	} catch {
		return undefined;
	}
	if (!isRecord(value)) return undefined;
	// A local-source coordination file is NEVER a DP intent. Only the dedicated
	// local path parses it; the DP request/receipt functions reject it here.
	if (value.source !== undefined && value.source !== "dp") return undefined;
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
	if (value.schema_version !== 1 || keys.some((key) => !nonEmpty(value[key]))) return undefined;
	if (!nonEmpty(value.parent_logical_id) || !UUID_PATTERN.test(value.parent_logical_id)) return undefined;
	if (!(TARGET_DPS as readonly unknown[]).includes(value.target_dp)) return undefined;
	if (!(INTENT_STATUSES as readonly unknown[]).includes(value.status)) return undefined;
	if (!isBoundPm(value.prepared_by)) return undefined;
	if (value.task_key !== null && !nonEmpty(value.task_key)) return undefined;
	for (const key of ["request_ref", "answer", "failure_reason"] as const) {
		if (value[key] !== null && !nonEmpty(value[key])) return undefined;
	}
	if (value.action_evidence !== undefined && !nonEmpty(value.action_evidence)) return undefined;
	if (value.effect_witness !== undefined && !nonEmpty(value.effect_witness)) return undefined;
	const answered = value.status === "answered" || value.status === "executed";
	if (answered) {
		if (!validAnswer(value.target_dp as TargetDp, value.request_ref, value.answer)) return undefined;
	} else if (value.request_ref !== null || value.answer !== null) return undefined;
	if ((value.status === "failed") !== (value.failure_reason !== null)) return undefined;
	if ((value.status === "executed") !== (value.action_evidence !== undefined)) return undefined;
	return value as unknown as DecisionFollowupIntent;
}

function validAnswer(dp: TargetDp, ref: unknown, answer: unknown): boolean {
	if (!nonEmpty(ref) || !TOKEN_PATTERN.test(ref) || !ref.startsWith(`${dp}:`)) return false;
	if (!nonEmpty(answer) || !TOKEN_PATTERN.test(answer)) return false;
	return dp === "dp-auto" || DECIDE_REGISTRY[dp].fixedChoiceIds.includes(answer);
}

function safeFailure(reason: unknown): string {
	return typeof reason === "string" && FAILURE_CODES.has(reason) ? reason : "request-failed";
}

function samePm(left: BoundPmIdentity, right: BoundPmIdentity): boolean {
	return left.role === right.role && left.key === right.key && left.window_id === right.window_id;
}

function bindingMatches(intent: ExpectedDecisionFollowup, expected: ExpectedDecisionFollowup): boolean {
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
if i.get("parent_only"):
    if expected_parent is None:
        sys.exit(1)
    actor = {"kind": "system", "id": i["restricted_executor"]}
    consumed = [r for r in rows if r.get("kind") == "lifecycle" and r.get("lifecycle") == "consumed"
                and r.get("decision_id") == i["parent_decision_id"] and r.get("logical_id") == i["parent_logical_id"]
                and r.get("answer") == choice and r.get("actor") == actor]
    released = any(r.get("kind") == "lifecycle" and r.get("lifecycle") in ("executed", "settled", "signoff")
                   and r.get("decision_id") == i["parent_decision_id"] for r in rows)
    if (len(consumed) != 1 or released or parent[0].get("initiator_role") != "pm"
            or any(r.get("actor") != actor for r in (parent[0], gate[0], *notes))):
        sys.exit(1)
    sys.exit(0)
if i.get("effect_recovery"):
    # A retained zero-attempt/no-business copy of a failed reply is a CLUE, never
    # authority. Corroborate it independently: the managed lifecycle must record
    # NO committed business decision for this parent/target DP. A committed
    # successor row, a damaged ledger or an unavailable reader keeps the
    # conservative unknown. (This is not a proof of zero POST; see the report.)
    committed = [r for r in rows if r.get("kind") == "request"
                 and r.get("parent_ref") == i["parent_decision_id"] and r.get("dp") == i["target_dp"]
                 and (r.get("business_decisions") or 0) > 0]
    sys.exit(1 if committed else 0)
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

function recorded(
	scope: LifecycleScope | undefined,
	intent: DecisionFollowupIntent,
	action?: string,
	parentOnly = false,
	effectRecovery = false,
): { basisId?: string } | undefined {
	const mw = findMwPy();
	if (scope === undefined || mw === null || (action !== undefined && !TOKEN_PATTERN.test(action))) return undefined;
	const args =
		"projectDir" in scope
			? ["production", scope.projectDir, null, scope.parentEvidence ?? null]
			: ["test", scope.isolatedTestRoot, scope.projectId, null];
	const read = spawnSync(PYTHON_EXE, ["-B", "-X", "utf8", "-c", CHECK_RECEIPT], {
		cwd: path.dirname(mw),
		stdio: ["pipe", "pipe", "ignore"],
		encoding: "utf8",
		windowsHide: true,
		timeout: 10_000,
		input: JSON.stringify([
			...args,
			{ ...intent, action_evidence: action ?? null, parent_only: parentOnly, effect_recovery: effectRecovery },
		]),
	});
	if (read.status !== 0) return undefined;
	if (intent.request_ref === null || parentOnly) return {};
	try {
		const basisId: unknown = JSON.parse(read.stdout);
		return nonEmpty(basisId) ? { basisId } : undefined;
	} catch {
		return undefined;
	}
}

/** Fresh managed lifecycle read for a host-produced LOCAL offer. The gate
 * snapshot alone is insufficient: the same owner's parent must have actually
 * been consumed and not completed/released. This performs no write or request. */
export function decisionFollowupParentCurrent(
	scope: LifecycleScope,
	expected: ExpectedDecisionFollowup,
	boundPm: BoundPmIdentity,
): boolean {
	if (
		boundPm.role !== "pm" ||
		boundPm.key !== expected.owner_key ||
		expected.restricted_executor !== `pm:${boundPm.window_id}`
	)
		return false;
	return (
		recorded(
			scope,
			{
				schema_version: 1,
				...expected,
				prepared_by: boundPm,
				status: "prepared",
				request_ref: null,
				answer: null,
				failure_reason: null,
			},
			undefined,
			true,
		) !== undefined
	);
}

function result(
	state: DecisionFollowupResult["state"],
	opts: Partial<Omit<DecisionFollowupResult, "state" | "parent_released">> = {},
): DecisionFollowupResult {
	return {
		state,
		request_started: false,
		duplicate: false,
		parent_released: false,
		...opts,
	};
}

function writeIntent(file: string, intent: unknown): void {
	const dir = path.dirname(file);
	const temporary = path.join(dir, `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`);
	let fd: number | undefined;
	try {
		fd = fs.openSync(temporary, "wx");
		fs.writeFileSync(fd, `${JSON.stringify(intent, null, 2)}\n`, "utf8");
		fs.fsyncSync(fd);
		fs.closeSync(fd);
		fd = undefined;
		fs.renameSync(temporary, file);
	} finally {
		if (fd !== undefined) fs.closeSync(fd);
		try {
			fs.unlinkSync(temporary);
		} catch {
			// The atomic rename consumed the temporary file.
		}
	}
}

function validateOwner(
	intent: { prepared_by: BoundPmIdentity; owner_key: string },
	boundPm: BoundPmIdentity | null,
): DecisionFollowupResult | undefined {
	if (boundPm === null) return result("blocked", { reason: "pm-window-unbound" });
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
export async function resumeDecisionFollowup(input: ResumeInput): Promise<DecisionFollowupResult> {
	const lockPath = `${input.intent_path}.lock`;
	const expected = { ...input.expected };
	let release = await acquireLock(lockPath);
	let intent: DecisionFollowupIntent | undefined;
	try {
		intent = parseIntent(input.intent_path);
		if (intent === undefined) return result("blocked", { reason: "intent-invalid" });
		const ownerProblem = validateOwner(intent, input.bound_pm);
		if (ownerProblem !== undefined) return ownerProblem;
		if (!bindingMatches(intent, expected)) return result("blocked", { reason: "version-mismatch" });
		if (intent.status === "requesting") return result("unknown", { reason: "request-outcome-unknown" });
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
			const reason = safeFailure(intent.failure_reason);
			// F2/P1-01: the retained counters are a CLUE, never authority. A persisted
			// row is unauthenticated coordination state, so a copied 0/0/0/false row
			// cannot by itself re-open recovery. Known-no-effect therefore also
			// requires an INDEPENDENT managed-lifecycle read proving this parent has no
			// committed child business decision; a contradictory successor, a damaged
			// ledger or an unavailable reader keeps the conservative unknown. `disabled`
			// keeps its own, separately justified semantics.
			let failureEffect = failureEffectVerdict(intent.effect_facts);
			// F2/P1-01: the counters alone are unauthenticated coordination state. The
			// positive verdict also requires this HOST's own observation of this exact
			// row, so a rewritten counter set, a rewritten/foreign witness, a copied row
			// on an unobserved path and a row from a previous host lifetime all stay
			// unknown — with no resend and no body. `disabled` is NOT exempt: its
			// separately justified semantics still require an authentic fact set.
			if (failureEffect === "known-no-effect" && !effectWitnessCurrent(input.intent_path, intent, reason))
				failureEffect = "unknown";
			if (
				failureEffect === "known-no-effect" &&
				reason !== "disabled" &&
				!recorded(input.lifecycle, intent, undefined, false, true)
			)
				failureEffect = "unknown";
			return result("failed", {
				reason,
				duplicate: true,
				failure_effect: failureEffect,
			});
		}
		let taskStatus: FollowupTaskStatus;
		try {
			taskStatus = input.observe_task(intent.owner_key, intent.task_key);
		} catch {
			return result("unknown", { reason: "task-observation-unavailable" });
		}
		if (taskStatus === "pending" || taskStatus === "running") {
			return result("in-progress", { reason: `task-${taskStatus}` });
		}
		if (taskStatus !== "not-queued") return result("unknown", { reason: "task-unknown" });
		if (input.lifecycle && "projectDir" in input.lifecycle && !input.lifecycle.parentEvidence)
			return result("blocked", { reason: "parent-evidence-missing" });
		if (!recorded(input.lifecycle, intent)) return result("blocked", { reason: "parent-or-successor-not-clear" });
		// A new request epoch starts here: no retained fact set or witness may
		// survive into it, and this host's previous observation of this path stops
		// authenticating. Only the failed write below re-mints an observation.
		intent = { ...intent, status: "requesting", request_ref: null, answer: null, failure_reason: null };
		if (intent.effect_facts !== undefined) delete intent.effect_facts;
		if (intent.effect_witness !== undefined) delete intent.effect_witness;
		observedEffectWitnesses.delete(effectWitnessKey(input.intent_path));
		writeIntent(input.intent_path, intent);
	} finally {
		release();
	}

	let requested: DecisionFollowupRequestResult;
	try {
		requested = await input.request(structuredClone(intent));
	} catch {
		requested = { available: false, reason: "request-threw" };
	}

	release = await acquireLock(lockPath);
	try {
		const current = parseIntent(input.intent_path);
		if (
			current === undefined ||
			!bindingMatches(current, expected) ||
			!samePm(current.prepared_by, intent.prepared_by) ||
			validateOwner(current, input.bound_pm)
		) {
			return result("unknown", { reason: "intent-changed-after-request", request_started: true });
		}
		if (current.status !== "requesting") {
			return result("unknown", { reason: "request-state-changed", request_started: true });
		}
		if (!requested?.available) {
			const reason = safeFailure(requested?.reason);
			// F2: retain the frozen NATIVE effect facts of THIS real reply next to
			// the frozen reason, so a later ordinary ingress re-reads them. A reply
			// without them drops any older set: unknown must never inherit a stale
			// positive, and the durable unknown keeps the ingress refusing.
			const retained = normalizeEffectFacts(requested?.effect_facts);
			// F2/P1-01: mint the host-owned witness for what THIS host just observed
			// and freeze it with the row, so the positive verdict later needs this
			// process's own observation instead of trusting rewritable bytes.
			const witness = effectWitnessDigest(current, reason, retained);
			const failed: DecisionFollowupIntent = {
				...current,
				status: "failed",
				failure_reason: reason,
				effect_witness: witness,
			};
			if (retained === undefined) delete failed.effect_facts;
			else failed.effect_facts = retained;
			writeIntent(input.intent_path, failed);
			observedEffectWitnesses.set(effectWitnessKey(input.intent_path), witness);
			return result("failed", {
				reason,
				request_started: true,
				failure_effect: effectWitnessCurrent(input.intent_path, failed, reason)
					? failureEffectVerdict(retained)
					: "unknown",
			});
		}
		if (!validAnswer(current.target_dp, requested.request_ref, requested.answer)) {
			writeIntent(input.intent_path, { ...current, status: "failed", failure_reason: "invalid-request-result" });
			return result("failed", { reason: "invalid-request-result", request_started: true });
		}
		const answered: DecisionFollowupIntent = {
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
	} finally {
		release();
	}
}

/** Record a real, already-performed follow-up action. This never performs the
 * action and never releases the parent gate; later consumers must independently
 * validate the action evidence and gate conditions. */
export async function markDecisionFollowupExecuted(input: ExecutedInput): Promise<DecisionFollowupResult> {
	const release = await acquireLock(`${input.intent_path}.lock`);
	try {
		const intent = parseIntent(input.intent_path);
		if (intent === undefined) return result("blocked", { reason: "intent-invalid" });
		const ownerProblem = validateOwner(intent, input.bound_pm);
		if (ownerProblem !== undefined) return ownerProblem;
		if (!bindingMatches(intent, input.expected)) return result("blocked", { reason: "version-mismatch" });
		if ((intent.status !== "answered" && intent.status !== "executed") || intent.request_ref !== input.request_ref) {
			return result("blocked", { reason: "answer-not-correlated" });
		}
		if (intent.restricted_action !== intent.answer) return result("blocked", { reason: "action-not-selected" });
		if (
			intent.status !== "executed" &&
			input.lifecycle &&
			"projectDir" in input.lifecycle &&
			!input.lifecycle.parentEvidence
		)
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
	} finally {
		release();
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// Discriminated LOCAL follow-up path (design.md §4.6).
//
// The DP request/receipt path above is unchanged in meaning: a file carrying a
// non-dp `source` is rejected by parseIntent, so it can never reach the DP
// functions. This path is selected ONLY by a host-bound `source: "local"`
// coordination record. A `local_ref` is a LOCATOR, never authority and never a
// DP decision id. It NEVER fills request_ref / answer / failure_reason / status,
// NEVER mints a DP id, NEVER calls CHECK_RECEIPT and NEVER writes to the DP
// lifecycle ledger. The only facts it trusts are the real committed local
// records (read through the single frozen store's shape-only readers), an
// INDEPENDENT host execution/result verifier verdict, and the CURRENT live
// owner/claim from the host. When any trusted boundary cannot certify a
// condition it FAILS CLOSED with a precise missing-interface reason instead of
// faking success, declaring the whole PM stopped, or creating an authorization.
// A successfully verified local successor satisfies CONTINUATION EVIDENCE only;
// `parent_released` stays false and the parent policy decides release.
// ─────────────────────────────────────────────────────────────────────────────

export const LOCAL_FOLLOWUP_PROGRESS = ["selected", "executing", "verified"] as const;
export type LocalFollowupProgress = (typeof LOCAL_FOLLOWUP_PROGRESS)[number];

/** A local coordination record carries NO DP status / request_ref / answer. */
export interface LocalFollowupIntent {
	schema_version: 1;
	source: "local";
	local_ref: string;
	local_source: LocalSource;
	// The SAME eleven binding fields as the DP intent (compared verbatim).
	parent_ref: string;
	parent_logical_id: string;
	parent_decision_id: string;
	parent_matter_version: string;
	target_dp: TargetDp;
	material_version: string;
	basis_version: string;
	owner_key: string;
	task_key: string | null;
	prepared_by: BoundPmIdentity;
	restricted_action: string;
	restricted_executor: string;
	// Local-only progress; deliberately NOT the DP `status`.
	local_progress: LocalFollowupProgress | null;
	local_action_evidence: string | null;
}

export type LocalRecordStatus = "ok" | "absent" | "corrupt" | "invalid-shape" | "refused";

/** Committed records as read by the frozen store's shape-only readers. */
export interface LocalFollowupRecords {
	selection?: LocalSelectionRecordV1;
	execution?: LocalExecutionRecordV1;
	selection_status: LocalRecordStatus;
	execution_status: LocalRecordStatus;
}

/** Independent host execution/result verifier output. NEVER a bare boolean,
 *  NEVER model text, NEVER derived from the record it is verifying. */
export interface LocalExecutionVerdict {
	verifier_ref: string;
	target_digest: string;
	observed_effect: string;
	confirmed: boolean;
}

/** CURRENT authoritative owner/claim + expected projection from the host. */
export interface LocalFollowupOwner {
	owner_key: string;
	claim_id: string;
	window_id: string;
	unique_active: boolean;
	material_digest: string;
	basis_digest: string;
	parent_decision_id: string;
}

/** Strictly separate local child state under one shared matter coordination path.
 *  The DP intent keeps its original bytes at the shared path; the local child
 *  never overwrites it and uses the SAME shared O_EXCL lock. */
export function localFollowupSidecarPath(sharedIntentPath: string): string {
	const ext = path.extname(sharedIntentPath);
	return ext === "" ? `${sharedIntentPath}.local` : `${sharedIntentPath.slice(0, -ext.length)}.local${ext}`;
}

export function sharedFollowupLockPath(sharedIntentPath: string): string {
	return `${sharedIntentPath}.lock`;
}

export type LocalFollowupCheckpoint =
	| "initial-lock"
	| "before-write"
	| "before-verifier"
	| "after-verifier"
	| "final-lock"
	| "before-save";

/** Host certificate for the CURRENT run and ACTUAL toolCallId executor. This is
 *  never derived from a stored execution record or an arbitrary JSON string. */
export interface LocalTrustedExecutorCertificate {
	current: true;
	local_ref: string;
	run_id: string;
	tool_call_id: string;
	executor: string;
}

/** Explicit provenance for a production current-offer certificate. The PM
 *  consumer recomputes both canonical digests from these host-owned values; the
 *  historical offer digest domain is never silently equated with this one. */
export interface LocalTrustedOfferProvenance {
	origin: "host-submit:FrozenOffer";
	material: Record<string, JsonValue>;
	context: Record<string, JsonValue> | null;
	preparation: Record<string, JsonValue>;
	material_fields: string[];
	basis_catalog: readonly PreparedBasis[];
	basis_material_refs: string[];
	parent_ref: string;
	parent_logical_id: string;
	parent_decision_id: string;
	parent_matter_version: string;
	identity_task_key: string;
	current_offer_id: string;
}

/** Host certificate for the CURRENT, non-superseded offer and its canonical
 *  supplied-material/catalog mapping. Digest fields here are explicitly in the
 *  same canonical domain as ExpectedDecisionFollowup.material_version /
 *  basis_version; they are NOT the historical offer's unrelated digest domain. */
export interface LocalTrustedOfferCertificate {
	current: true;
	current_by_matter: true;
	offer_id: string;
	local_ref: string;
	parent_decision_id: string;
	parent_matter_version: string;
	matter_ref: string;
	matter_version: string;
	canonical_material_digest: string;
	canonical_catalog_digest: string;
	target_dp: string;
	selected_action: string;
	selected_basis_id: string;
	basis_applies_to: string[];
	/** Present on production host certificates; the host-owned identity task_key. */
	identity_task_key?: string;
	/** Present on production host certificates; older fixture-only certificates
	 *  may omit it and remain their original explicitly labelled boundary. */
	provenance?: LocalTrustedOfferProvenance;
}

export interface VerifyLocalFollowupInput {
	intent_path: string;
	expected: ExpectedDecisionFollowup;
	bound_pm: BoundPmIdentity | null;
	source: LocalSource;
	local_ref: string;
	/** Trusted boundary 1: real committed local records (frozen store readers). */
	readRecords: (ref: string, source: LocalSource, taskKey: string | null) => LocalFollowupRecords;
	/** Trusted boundary 2: independent execution/result/target verifier. */
	verifyExecution: (
		execution: LocalExecutionRecordV1,
	) => LocalExecutionVerdict | undefined | Promise<LocalExecutionVerdict | undefined>;
	/** Trusted boundary 3: CURRENT live unique-active owner/claim + projection. */
	readCurrentOwner: () => LocalFollowupOwner | undefined;
	/** Shared same-matter lock; when absent the local child's own lock is used by
	 *  standalone fixtures. The registered consumer MUST pass the shared lock. */
	lock_path?: string;
	/** Trusted boundary 4: authoritative parent/config/watch/source-card/worker
	 *  evidence and current-offer re-read at every await/save checkpoint. */
	readCurrentSource?: (checkpoint: LocalFollowupCheckpoint) => boolean | undefined;
	/** Trusted boundary 5: current run + actual toolCallId executor certificate. */
	readTrustedExecutor?: () => LocalTrustedExecutorCertificate | undefined;
	/** Trusted boundary 6: current non-superseded offer and canonical material,
	 *  context, catalog, matter/version, target, choice and basis applicability. */
	readCurrentOffer?: () => LocalTrustedOfferCertificate | undefined;
}

function isLocalProgress(value: unknown): value is LocalFollowupProgress {
	return typeof value === "string" && (LOCAL_FOLLOWUP_PROGRESS as readonly string[]).includes(value);
}

const LOCAL_INTENT_KEYS = [
	"schema_version",
	"source",
	"local_ref",
	"local_source",
	"parent_ref",
	"parent_logical_id",
	"parent_decision_id",
	"parent_matter_version",
	"target_dp",
	"material_version",
	"basis_version",
	"owner_key",
	"task_key",
	"prepared_by",
	"restricted_action",
	"restricted_executor",
	"local_progress",
	"local_action_evidence",
] as const;

/** Detect duplicated JSON object members on the RAW bytes, before any parse.
 *  `JSON.parse` keeps only the LAST member of a duplicated key, so a strictly
 *  shaped parsed value can hide contradictory or evidence-bearing bytes. The
 *  local sidecar must be qualified on its original text; malformed text also
 *  refuses closed (the normal parser rejects it anyway). Nested objects and
 *  escaped/unicode key spellings are compared after JSON string decoding. */
export function hasDuplicateJsonMembers(raw: string): boolean {
	let pos = 0;
	const skipWhitespace = (): void => {
		while (pos < raw.length && /\s/.test(raw[pos])) pos += 1;
	};
	const readString = (): string | undefined => {
		if (raw[pos] !== '"') return undefined;
		pos += 1;
		let value = "";
		while (pos < raw.length) {
			const ch = raw[pos];
			if (ch === '"') {
				pos += 1;
				return value;
			}
			if (ch === "\\") {
				pos += 1;
				if (pos >= raw.length) return undefined;
				const esc = raw[pos];
				if (esc === "u") {
					const hex = raw.slice(pos + 1, pos + 5);
					if (!/^[0-9a-fA-F]{4}$/.test(hex)) return undefined;
					value += String.fromCharCode(Number.parseInt(hex, 16));
					pos += 5;
				} else {
					const decoded: Record<string, string> = {
						'"': '"',
						"\\": "\\",
						"/": "/",
						b: "\b",
						f: "\f",
						n: "\n",
						r: "\r",
						t: "\t",
					};
					const mapped = decoded[esc];
					if (mapped === undefined) return undefined;
					value += mapped;
					pos += 1;
				}
				continue;
			}
			if (ch === "\n" || ch === "\r") return undefined;
			value += ch;
			pos += 1;
		}
		return undefined;
	};
	const parseValue = (): boolean => {
		skipWhitespace();
		const ch = raw[pos];
		if (ch === "{") return parseObject();
		if (ch === "[") return parseArray();
		if (ch === '"') return readString() !== undefined;
		const start = pos;
		while (pos < raw.length && !/[\s,}\]]/.test(raw[pos])) pos += 1;
		return pos > start;
	};
	const parseObject = (): boolean => {
		pos += 1;
		const keys = new Set<string>();
		skipWhitespace();
		if (raw[pos] === "}") {
			pos += 1;
			return true;
		}
		for (;;) {
			skipWhitespace();
			const key = readString();
			if (key === undefined || keys.has(key)) return false;
			keys.add(key);
			skipWhitespace();
			if (raw[pos] !== ":") return false;
			pos += 1;
			if (!parseValue()) return false;
			skipWhitespace();
			const sep = raw[pos];
			if (sep === ",") {
				pos += 1;
				continue;
			}
			if (sep === "}") {
				pos += 1;
				return true;
			}
			return false;
		}
	};
	const parseArray = (): boolean => {
		pos += 1;
		skipWhitespace();
		if (raw[pos] === "]") {
			pos += 1;
			return true;
		}
		for (;;) {
			if (!parseValue()) return false;
			skipWhitespace();
			const sep = raw[pos];
			if (sep === ",") {
				pos += 1;
				continue;
			}
			if (sep === "]") {
				pos += 1;
				return true;
			}
			return false;
		}
	};
	if (!parseValue()) return true;
	skipWhitespace();
	return pos !== raw.length;
}

/** Prior-association marker carried in the recovered sidecar's EXISTING
 *  `local_action_evidence` field (no shape change). It is coordination evidence
 *  ONLY: never an execution result, never a host certificate and never an
 *  authentication. It records the old locator so a locator correction does not
 *  silently discard the child's earlier association. */
export const PRIOR_LOCAL_ASSOCIATION_PREFIX = "prior-local-association:";

export function parsePriorLocalAssociation(value: string | null): string[] | undefined {
	if (value === null) return [];
	if (!value.startsWith(PRIOR_LOCAL_ASSOCIATION_PREFIX)) return undefined;
	try {
		const parsed: unknown = JSON.parse(value.slice(PRIOR_LOCAL_ASSOCIATION_PREFIX.length));
		if (
			!Array.isArray(parsed) ||
			parsed.some((ref) => typeof ref !== "string" || ref.trim() === "" || ref.includes("\0"))
		)
			return undefined;
		return parsed as string[];
	} catch {
		return undefined;
	}
}

export function priorLocalAssociationEvidence(refs: string[]): string {
	return `${PRIOR_LOCAL_ASSOCIATION_PREFIX}${JSON.stringify(refs)}`;
}

/** Strict shape-only parser for an already-read local coordination value. The
 *  exact field set is part of the contract: extra facts are not silently
 *  normalized away by a recovery path. */
export function parseLocalIntentValue(value: unknown): LocalFollowupIntent | undefined {
	if (!isRecord(value)) return undefined;
	// A local record must NEVER carry DP facts. Reject the known DP field names
	// verbatim so a forged DP-shaped file cannot be laundered through this path.
	const dpKeys = [
		"status",
		"request_ref",
		"answer",
		"failure_reason",
		"action_evidence",
		"decision_id",
		"answers",
		"available",
		"business_decisions",
		"business_decision",
		"decision_lifecycle",
		"receipt",
		"model_called",
		"decision_ref",
	];
	if (dpKeys.some((key) => Object.hasOwn(value, key))) return undefined;
	if (
		Object.keys(value).length !== LOCAL_INTENT_KEYS.length ||
		LOCAL_INTENT_KEYS.some((key) => !Object.hasOwn(value, key))
	)
		return undefined;
	if (value.schema_version !== 1 || value.source !== "local") return undefined;
	const required = [
		"local_ref",
		"parent_ref",
		"parent_decision_id",
		"parent_matter_version",
		"material_version",
		"basis_version",
		"owner_key",
		"restricted_action",
		"restricted_executor",
	];
	if (required.some((key) => !nonEmpty(value[key]))) return undefined;
	if (!nonEmpty(value.parent_logical_id) || !UUID_PATTERN.test(value.parent_logical_id)) return undefined;
	if (!(TARGET_DPS as readonly unknown[]).includes(value.target_dp)) return undefined;
	if (value.local_source !== "pm" && value.local_source !== "worker-local") return undefined;
	if (!isBoundPm(value.prepared_by)) return undefined;
	if (value.task_key !== null && !nonEmpty(value.task_key)) return undefined;
	if (value.local_progress !== null && !isLocalProgress(value.local_progress)) return undefined;
	if (value.local_action_evidence !== null && !nonEmpty(value.local_action_evidence)) return undefined;
	return value as unknown as LocalFollowupIntent;
}

function parseLocalIntent(file: string): LocalFollowupIntent | undefined {
	let raw: string;
	try {
		raw = fs.readFileSync(file, "utf8");
	} catch {
		return undefined;
	}
	// A duplicated member is ambiguous RAW evidence: never let JSON.parse fold
	// it into a trusted null/null recovery before strict qualification.
	if (hasDuplicateJsonMembers(raw)) return undefined;
	let value: unknown;
	try {
		value = JSON.parse(raw);
	} catch {
		return undefined;
	}
	return parseLocalIntentValue(value);
}

function writeLocalIntent(file: string, intent: LocalFollowupIntent): void {
	writeIntent(file, intent);
}

function sourceCurrent(input: VerifyLocalFollowupInput, checkpoint: LocalFollowupCheckpoint): boolean {
	if (input.readCurrentSource === undefined) return false;
	try {
		return input.readCurrentSource(checkpoint) === true;
	} catch {
		return false;
	}
}

type CertificateRead =
	| { ok: true; executor: LocalTrustedExecutorCertificate; offer: LocalTrustedOfferCertificate }
	| { ok: false; reason: string };

function readTrustedCertificates(input: VerifyLocalFollowupInput, intent: LocalFollowupIntent): CertificateRead {
	let executor: LocalTrustedExecutorCertificate | undefined;
	let offer: LocalTrustedOfferCertificate | undefined;
	try {
		executor = input.readTrustedExecutor?.();
		offer = input.readCurrentOffer?.();
	} catch {
		return { ok: false, reason: "missing-interface:trusted-certificates (host certificate read threw)" };
	}
	if (executor === undefined)
		return {
			ok: false,
			reason:
				"missing-interface:readTrustedExecutor (current run and actual toolCallId executor certificate unavailable)",
		};
	if (offer === undefined)
		return {
			ok: false,
			reason:
				"missing-interface:readCurrentOffer (current offer canonical material/context/catalog/matter/version/target/choice/basis certificate unavailable)",
		};
	if (
		executor.current !== true ||
		executor.local_ref !== input.local_ref ||
		!nonEmpty(executor.run_id) ||
		!nonEmpty(executor.tool_call_id) ||
		!nonEmpty(executor.executor)
	)
		return { ok: false, reason: "trusted-executor-certificate-invalid" };
	if (
		offer.current !== true ||
		offer.current_by_matter !== true ||
		!nonEmpty(offer.offer_id) ||
		offer.local_ref !== input.local_ref ||
		!nonEmpty(offer.canonical_material_digest) ||
		!nonEmpty(offer.canonical_catalog_digest) ||
		!nonEmpty(offer.matter_ref) ||
		!nonEmpty(offer.matter_version) ||
		!nonEmpty(offer.selected_action) ||
		!nonEmpty(offer.selected_basis_id) ||
		!Array.isArray(offer.basis_applies_to) ||
		offer.basis_applies_to.length === 0 ||
		offer.basis_applies_to.some((candidate) => !nonEmpty(candidate))
	)
		return { ok: false, reason: "current-offer-certificate-invalid" };
	if (executor.executor !== intent.restricted_executor || executor.executor !== input.expected.restricted_executor)
		return { ok: false, reason: "trusted-executor-binding-mismatch" };
	const provenance = offer.provenance;
	if (provenance !== undefined) {
		const materialDigest = createHash("sha256").update(canonicalStateJson(provenance.material)).digest("hex");
		const basisDigest = createHash("sha256").update(canonicalStateJson(provenance.preparation)).digest("hex");
		const selectedBasis = provenance.basis_catalog.find((item) => item.id === offer.selected_basis_id);
		const basisRefsMatch =
			selectedBasis !== undefined &&
			canonicalStateJson([...selectedBasis.material_refs]) === canonicalStateJson(provenance.basis_material_refs) &&
			provenance.basis_material_refs.every((ref) => provenance.material_fields.includes(ref));
		if (
			provenance.origin !== "host-submit:FrozenOffer" ||
			provenance.context !== null ||
			provenance.current_offer_id !== offer.offer_id ||
			provenance.parent_ref !== input.expected.parent_ref ||
			provenance.parent_logical_id !== input.expected.parent_logical_id ||
			provenance.parent_decision_id !== offer.parent_decision_id ||
			provenance.parent_decision_id !== intent.parent_decision_id ||
			provenance.parent_decision_id !== input.expected.parent_decision_id ||
			provenance.parent_matter_version !== offer.parent_matter_version ||
			!provenance.identity_task_key.trim() ||
			offer.identity_task_key !== provenance.identity_task_key ||
			materialDigest !== offer.canonical_material_digest ||
			basisDigest !== offer.canonical_catalog_digest ||
			selectedBasis === undefined ||
			!selectedBasis.applies_to.includes(offer.selected_action) ||
			!basisRefsMatch
		)
			return { ok: false, reason: "current-offer-provenance-invalid" };
	}
	if (
		offer.parent_decision_id !== intent.parent_decision_id ||
		offer.parent_decision_id !== input.expected.parent_decision_id ||
		offer.parent_matter_version !== intent.parent_matter_version ||
		offer.parent_matter_version !== input.expected.parent_matter_version ||
		offer.canonical_material_digest !== input.expected.material_version ||
		offer.canonical_catalog_digest !== input.expected.basis_version ||
		offer.target_dp !== intent.target_dp ||
		offer.target_dp !== input.expected.target_dp ||
		offer.selected_action !== input.expected.restricted_action
	)
		return { ok: false, reason: "current-offer-binding-mismatch" };
	return { ok: true, executor, offer };
}

function persistedIntentFor(
	file: string,
	input: VerifyLocalFollowupInput,
	expected: ExpectedDecisionFollowup,
	preparedBy: BoundPmIdentity,
): LocalFollowupIntent | undefined {
	const current = parseLocalIntent(file);
	if (
		current === undefined ||
		current.local_ref !== input.local_ref ||
		current.local_source !== input.source ||
		!samePm(current.prepared_by, preparedBy) ||
		!bindingMatches(current, expected) ||
		validateOwner(current, input.bound_pm) !== undefined
	)
		return undefined;
	return current;
}

type LocalEvaluation =
	| { ok: true; selection: LocalSelectionRecordV1; execution: LocalExecutionRecordV1; owner: LocalFollowupOwner }
	| { ok: false; result: DecisionFollowupResult; progress?: LocalFollowupProgress };

/** Ordinary EVIDENCE collection, NOT a restricted gate effect: this only reads
 *  and certifies continuation facts. It never releases the parent gate, never
 *  grants authority and never writes a QG/sign/Done. */
function evaluateLocalFollowup(input: VerifyLocalFollowupInput, intent: LocalFollowupIntent): LocalEvaluation {
	const refuseEval = (
		state: DecisionFollowupResult["state"],
		reason: string,
		progress?: LocalFollowupProgress,
	): LocalEvaluation => ({
		ok: false,
		result: result(state, { reason }),
		...(progress === undefined ? {} : { progress }),
	});
	const certificates = readTrustedCertificates(input, intent);
	if (!certificates.ok) return refuseEval("blocked", certificates.reason);
	let owner: LocalFollowupOwner | undefined;
	try {
		owner = input.readCurrentOwner();
	} catch {
		owner = undefined;
	}
	if (owner === undefined)
		return refuseEval(
			"blocked",
			"missing-interface:readCurrentOwner (current live claim/owner projection unavailable)",
		);
	if (!owner.unique_active) return refuseEval("blocked", "current-owner-not-unique-active");
	if (input.bound_pm === null) return refuseEval("blocked", "pm-window-unbound");
	if (
		owner.owner_key !== intent.owner_key ||
		owner.owner_key !== input.expected.owner_key ||
		owner.owner_key !== input.bound_pm.key ||
		owner.window_id !== input.bound_pm.window_id ||
		!nonEmpty(owner.claim_id)
	)
		return refuseEval("blocked", "current-claim-changed");

	let records: LocalFollowupRecords;
	try {
		records = input.readRecords(input.local_ref, input.source, intent.task_key);
	} catch {
		return refuseEval("blocked", "missing-interface:readRecords (committed local records unavailable)");
	}
	if (records.selection_status !== "ok" || records.selection === undefined)
		return refuseEval("blocked", "selection-not-committed");
	const selection = records.selection;
	// Validate ALL applicable parent/action/material/catalog/owner binding facts
	// on the committed selection BEFORE emitting any selection-only label. A
	// stale plan must never be labelled CURRENT / `selected` (in-progress); the
	// independent current-offer + trusted-executor certificates and the live
	// unique-active owner/claim are already checked at the top of this function.

	// Compare all applicable original binding fields + matter/version/material/
	// basis + action/target/executor + current claim against the real records.
	if (selection.source !== input.source || selection.local_ref !== input.local_ref)
		return refuseEval("blocked", "selection-locator-mismatch");
	const parentDp = selection.parent_decision_ref?.decision_id;
	if (
		!nonEmpty(parentDp) ||
		parentDp !== owner.parent_decision_id ||
		parentDp !== intent.parent_decision_id ||
		parentDp !== input.expected.parent_decision_id
	)
		return refuseEval("blocked", "parent-dp-reference-mismatch");
	if (
		selection.selected_action !== intent.restricted_action ||
		selection.selected_action !== input.expected.restricted_action
	)
		return refuseEval("blocked", "restricted-action-mismatch");
	if (selection.material_digest !== owner.material_digest || selection.basis_digest !== owner.basis_digest)
		return refuseEval("blocked", "material-or-basis-drift");
	if (selection.action_state !== "planned" || selection.business_completed !== false)
		return refuseEval("blocked", "selection-is-not-a-plan");
	if (!nonEmpty(selection.selected_basis_id)) return refuseEval("blocked", "selected-basis-missing");
	const hb = selection.host_binding;
	if (
		hb.key !== owner.owner_key ||
		hb.owner !== owner.claim_id ||
		hb.claim_id !== owner.claim_id ||
		(input.source === "pm" && hb.role !== "pm") ||
		(input.source === "worker-local" && hb.role === "pm") ||
		(hb.task_key ?? null) !== intent.task_key
	)
		return refuseEval("blocked", "stale-or-changed-owner-binding");

	// Compare the committed plan against the CURRENT offer BEFORE emitting any
	// selection-only label. Matter/version, selected basis/choice/action and the
	// current offer's basis applicability must all still describe this plan.
	if (
		selection.matter_ref !== certificates.offer.matter_ref ||
		selection.matter_version !== certificates.offer.matter_version ||
		selection.selected_basis_id !== certificates.offer.selected_basis_id ||
		selection.selected_action !== certificates.offer.selected_action ||
		selection.selected_action !== input.expected.restricted_action ||
		!certificates.offer.basis_applies_to.includes(selection.selected_action) ||
		!certificates.offer.basis_applies_to.includes(certificates.offer.selected_action)
	)
		return refuseEval("blocked", "current-offer-selection-applicability-mismatch");

	// ONLY a genuinely ABSENT execution means "selection-only", and only now,
	// after every applicable parent/action/material/catalog/owner/offer check
	// above. A corrupt, invalid-shape (forged DP-impersonation) or refused
	// execution is a hard refusal, never laundered into a planned-selection.
	if (records.execution_status === "absent")
		return refuseEval("in-progress", "selection-only-no-execution", "selected");
	if (records.execution_status !== "ok" || records.execution === undefined)
		return refuseEval("blocked", "execution-record-invalid");
	const execution = records.execution;

	if (execution.source !== input.source || execution.local_ref !== input.local_ref)
		return refuseEval("blocked", "execution-locator-mismatch");
	if (
		execution.executor !== certificates.executor.executor ||
		execution.executor !== intent.restricted_executor ||
		execution.executor !== input.expected.restricted_executor
	)
		return refuseEval("blocked", "restricted-executor-mismatch");
	if (
		!nonEmpty(execution.action_ref) ||
		!nonEmpty(execution.result_ref) ||
		!nonEmpty(execution.verified_by) ||
		!nonEmpty(execution.target_digest)
	)
		return refuseEval("blocked", "action-result-or-verifier-ref-missing");
	if (execution.effect_state !== "known") return refuseEval("unknown", "execution-effect-unknown");
	const ehb = execution.host_binding;
	if (
		ehb.key !== hb.key ||
		ehb.owner !== hb.owner ||
		ehb.claim_id !== hb.claim_id ||
		(ehb.task_key ?? null) !== (hb.task_key ?? null) ||
		(ehb.run_id ?? null) !== (hb.run_id ?? null)
	)
		return refuseEval("blocked", "execution-binding-drift");
	return { ok: true, selection, execution, owner };
}

/** Correlate the INDEPENDENT verifier verdict with the committed execution and
 *  the real target effect. A verifier that cannot certify is a missing
 *  interface, not a success and not a global PM stop. */
function certifyVerdict(
	verdict: LocalExecutionVerdict | undefined,
	execution: LocalExecutionRecordV1,
): DecisionFollowupResult | undefined {
	if (verdict === undefined)
		return result("unknown", {
			reason: "missing-interface:verifyExecution (independent execution/result verifier unavailable)",
		});
	if (verdict.confirmed !== true) return result("unknown", { reason: "execution-verifier-unproven" });
	if (!nonEmpty(verdict.verifier_ref) || verdict.verifier_ref !== execution.verified_by)
		return result("unknown", { reason: "verifier-ref-mismatch" });
	if (!nonEmpty(verdict.target_digest) || verdict.target_digest !== execution.target_digest)
		return result("unknown", { reason: "target-digest-drift" });
	if (verdict.observed_effect !== execution.observed_effect)
		return result("unknown", { reason: "observed-effect-mismatch" });
	return undefined;
}

/** Verify a discriminated LOCAL successor as continuation evidence. Mirrors the
 *  DP path's two-lock ordering, atomic writes, crash/unknown handling and
 *  idempotence. It NEVER performs the business action and NEVER releases the
 *  parent gate (`parent_released` stays false throughout). */
export async function verifyLocalFollowupEvidence(input: VerifyLocalFollowupInput): Promise<DecisionFollowupResult> {
	const lockPath = input.lock_path ?? sharedFollowupLockPath(input.intent_path);
	const expected = { ...input.expected };
	const stale = (checkpoint: LocalFollowupCheckpoint, state: DecisionFollowupResult["state"] = "unknown") =>
		result(state, { reason: `source-evidence-not-current:${checkpoint}` });
	let release = await acquireLock(lockPath);
	let preparedBy: BoundPmIdentity | undefined;
	let verifiedBefore = false;
	let execution: LocalExecutionRecordV1 | undefined;
	try {
		if (!sourceCurrent(input, "initial-lock")) return stale("initial-lock", "blocked");
		const intent = parseLocalIntent(input.intent_path);
		if (intent === undefined) return result("blocked", { reason: "local-intent-invalid" });
		if (intent.local_ref !== input.local_ref || intent.local_source !== input.source)
			return result("blocked", { reason: "local-ref-or-source-mismatch" });
		const ownerProblem = validateOwner(intent, input.bound_pm);
		if (ownerProblem !== undefined) return ownerProblem;
		if (!bindingMatches(intent, expected)) return result("blocked", { reason: "version-mismatch" });
		// A persisted `executing` state is deliberately crash-unknown (the
		// filesystem record and the independent verifier are not one transaction).
		if (intent.local_progress === "executing") return result("unknown", { reason: "local-outcome-unknown" });
		const evaluation = evaluateLocalFollowup(input, intent);
		if (!evaluation.ok) {
			if (evaluation.progress !== undefined && intent.local_progress !== evaluation.progress) {
				if (!sourceCurrent(input, "before-write")) return stale("before-write", "blocked");
				const persisted = persistedIntentFor(input.intent_path, input, expected, intent.prepared_by);
				if (persisted === undefined) return result("unknown", { reason: "local-source-or-ref-changed" });
				if (persisted.local_progress !== evaluation.progress)
					writeLocalIntent(input.intent_path, { ...persisted, local_progress: evaluation.progress });
			}
			return evaluation.result;
		}
		execution = evaluation.execution;
		preparedBy = intent.prepared_by;
		if (!sourceCurrent(input, "before-write")) return stale("before-write", "blocked");
		const persisted = persistedIntentFor(input.intent_path, input, expected, preparedBy);
		if (persisted === undefined) return result("unknown", { reason: "local-source-or-ref-changed" });
		verifiedBefore = persisted.local_progress === "verified";
		if (!verifiedBefore) writeLocalIntent(input.intent_path, { ...persisted, local_progress: "executing" });
	} finally {
		release();
	}
	if (execution === undefined || preparedBy === undefined)
		return result("unknown", { reason: "verification-state-changed" });

	// Independent verifier runs without the file lock (mirrors the DP request).
	if (!sourceCurrent(input, "before-verifier")) return stale("before-verifier");
	let verdict: LocalExecutionVerdict | undefined;
	try {
		verdict = await input.verifyExecution(execution);
	} catch {
		verdict = undefined;
	}
	if (!sourceCurrent(input, "after-verifier")) return stale("after-verifier");

	release = await acquireLock(lockPath);
	try {
		if (!sourceCurrent(input, "final-lock")) return stale("final-lock");
		const current = parseLocalIntent(input.intent_path);
		if (
			current === undefined ||
			current.local_ref !== input.local_ref ||
			current.local_source !== input.source ||
			!samePm(current.prepared_by, preparedBy) ||
			!bindingMatches(current, expected) ||
			validateOwner(current, input.bound_pm) !== undefined
		)
			return result("unknown", { reason: "intent-changed-after-verification" });
		if (current.local_progress !== "executing" && current.local_progress !== "verified")
			return result("unknown", { reason: "verification-state-changed" });
		// Re-read CURRENT source, owner, certificates and committed records: any
		// drift during the verifier await is refused, never a stale success.
		const recheck = evaluateLocalFollowup(input, current);
		if (!recheck.ok) return recheck.result;
		const certified = certifyVerdict(verdict, recheck.execution);
		if (certified !== undefined) {
			if (current.local_progress !== "verified") {
				if (!sourceCurrent(input, "before-save")) return stale("before-save");
				const persisted = persistedIntentFor(input.intent_path, input, expected, preparedBy);
				if (persisted === undefined) return result("unknown", { reason: "local-source-or-ref-changed" });
				if (persisted.local_progress !== "selected")
					writeLocalIntent(input.intent_path, { ...persisted, local_progress: "selected" });
			}
			return certified;
		}
		if (!sourceCurrent(input, "before-save")) return stale("before-save");
		const persisted = persistedIntentFor(input.intent_path, input, expected, preparedBy);
		if (persisted === undefined) return result("unknown", { reason: "local-source-or-ref-changed" });
		const evidence = recheck.execution.result_ref;
		if (persisted.local_progress !== "verified")
			writeLocalIntent(input.intent_path, {
				...persisted,
				local_progress: "verified",
				local_action_evidence: evidence,
			});
		return result("executed", {
			verified_source: "local",
			ref: persisted.local_ref,
			action: persisted.restricted_action,
			evidence,
			local_progress: "verified",
			duplicate: verifiedBefore,
		});
	} finally {
		release();
	}
}
