import { createHash } from "node:crypto";
import {
	type BudgetReservationResult,
	type MatterBudgetV1,
	parseBudgetReservationResult,
	validateMatterBudget,
} from "../shared/decision-handoff.ts";

/** Host-only identity. A matter/turn/card is NOT an authorization unit. The host
 * resolves every descendant to the SAME canonical unit and parent budget ref. */
export interface RuntimeBudgetBinding {
	authorization_unit: string;
	parent_budget_ref: string;
	matter_ref: string;
}

export interface RuntimeBudgetAction extends RuntimeBudgetBinding {
	/** Real run + toolCallId; never a model-provided action label. */
	call_id: string;
	max_cost: number;
	cost_unit: string;
	child_reservation_id?: string;
}

export interface RuntimeBudgetObservation extends RuntimeBudgetBinding {
	call_id: string;
	result_ref: string;
	outcome: "success" | "error" | "unknown";
	actual_cost: number;
	cost_unit: string;
}

export interface RuntimeBudgetChild extends RuntimeBudgetBinding {
	reservation_id: string;
	steps: number;
	cost: number;
	cost_unit: string;
	/** Fixed child deadline, no later than its parent. Canonical UTC ISO. */
	deadline: string;
}

export interface RuntimeBudgetSettlement extends RuntimeBudgetBinding {
	reservation_id: string;
}

/** Captured by a host closure reading authorized evidence, not tool text or
 * details. The controller hashes a copy immediately; no mutable bytes escape. */
export interface RuntimeBudgetEvidence {
	ref: string;
	bytes: Uint8Array;
}
export interface RuntimeBudgetEvidenceDigest {
	ref: string;
	sha256: string;
}

/** Existing host trace import boundary, not a new persistent journal. The host
 * must verify completeness/order/provenance through through_ref, including ALL
 * outstanding reservations, before returning it from readAuthorization. */
export type RuntimeBudgetReplayEvent = { at: number } & (
	| { kind: "reserve"; request: RuntimeBudgetAction; evidence: RuntimeBudgetEvidenceDigest[] }
	| { kind: "observe"; request: RuntimeBudgetObservation; evidence: RuntimeBudgetEvidenceDigest[] }
	| { kind: "reserve-child"; request: RuntimeBudgetChild }
	| { kind: "settle"; request: RuntimeBudgetSettlement }
);

export interface RuntimeBudgetHistory {
	kind: "verified-empty" | "verified-replay";
	origin_ref: string;
	through_ref: string;
	events: RuntimeBudgetReplayEvent[];
}

export interface RuntimeBudgetAuthorization {
	authorization_unit: string;
	parent_budget_ref: string;
	/** Verified pinned-card GENESIS, with explicitly zero initial counters.
	 * Nonzero current state is reconstructed by verified history, never reset. */
	initial: MatterBudgetV1;
	/** Smallest authorized accounting unit; counts must be safe integers.
	 * E.g. the card's explicit tool-call-equivalent, NOT inferred currency. */
	cost_unit: string;
	started_at: string;
	history?: RuntimeBudgetHistory;
}

export interface RuntimeBudgetOptions {
	/** Same trusted clock closure as the adapter/store. Required; no timeout
	 * derived allowance or fallback clock. Epoch milliseconds. */
	clock: () => number;
	/** Private host closure: verifies live authority, pinned card, canonical
	 * unit mapping and COMPLETE existing trace. Never register this as a tool. */
	readAuthorization: (binding: RuntimeBudgetBinding) => RuntimeBudgetAuthorization | undefined;
	captureEvidence: (binding: RuntimeBudgetBinding) => readonly RuntimeBudgetEvidence[] | undefined;
}

export type RuntimeBudgetCode =
	| "invalid-input"
	| "invalid-clock"
	| "authorization-missing"
	| "authorization-drift"
	| "history-missing"
	| "history-invalid"
	| "not-open"
	| "conflict"
	| "not-reserved"
	| "in-flight"
	| "budget-exhausted"
	| "insufficient-remaining"
	| "cost-overrun";
export type RuntimeBudgetResult<T> = { ok: true; value: T } | { ok: false; code: RuntimeBudgetCode; gap: string };

export interface RuntimeBudgetSnapshot {
	budget: MatterBudgetV1;
	cost_unit: string;
	available_steps: number;
	available_cost: number;
	held_steps: number;
	held_cost: number;
	in_flight: number;
	blocked: RuntimeBudgetCode | null;
}
export interface RuntimeBudgetActionResult {
	status: "reserved" | "observed" | "duplicate";
	/** ONLY a fresh reservation permits an actual tool action. */
	execute: boolean;
	progress: boolean;
	overrun: boolean;
}
export interface RuntimeBudgetChildResult {
	status: "reserved" | "settled" | "duplicate";
	released_steps: number;
	released_cost: number;
}

export interface RuntimeBudgetController {
	/** Call outside store readTrustedContext; it may initialize/replay/bind. */
	open(binding: RuntimeBudgetBinding): RuntimeBudgetResult<RuntimeBudgetSnapshot>;
	/** Both reads are pure: no binding, reservation, consumption or clock write. */
	snapshot(binding: RuntimeBudgetBinding): RuntimeBudgetResult<RuntimeBudgetSnapshot>;
	preflight(request: RuntimeBudgetAction): RuntimeBudgetResult<BudgetReservationResult>;
	reserve(request: RuntimeBudgetAction): RuntimeBudgetResult<RuntimeBudgetActionResult>;
	observe(request: RuntimeBudgetObservation): RuntimeBudgetResult<RuntimeBudgetActionResult>;
	/** Lost/unknown result: charge its full reserved cost, never refund/replay. */
	settleUnknown(
		binding: RuntimeBudgetBinding,
		callId: string,
		resultRef: string,
	): RuntimeBudgetResult<RuntimeBudgetActionResult>;
	reserveChild(request: RuntimeBudgetChild): RuntimeBudgetResult<RuntimeBudgetChildResult>;
	/** Release unused child allowance ONLY when it has no outstanding calls. */
	settle(request: RuntimeBudgetSettlement): RuntimeBudgetResult<RuntimeBudgetChildResult>;
}

interface ActionState {
	request: RuntimeBudgetAction;
	before: RuntimeBudgetEvidenceDigest[];
	observation?: RuntimeBudgetObservation;
	progress: boolean;
	overrun: boolean;
}
interface ChildState {
	request: RuntimeBudgetChild;
	steps: number;
	cost: number;
	settled: boolean;
}
interface UnitState {
	initial: MatterBudgetV1;
	costUnit: string;
	startedAt: string;
	lastAt: number;
	matters: Set<string>;
	actions: Map<string, ActionState>;
	children: Map<string, ChildState>;
	seenEvidence: Set<string>;
	steps: number;
	cost: number;
	noProgress: number;
	overrun: boolean;
}

function fail(code: RuntimeBudgetCode, gap: string): { ok: false; code: RuntimeBudgetCode; gap: string } {
	return { ok: false, code, gap };
}
function good<T>(value: T): { ok: true; value: T } {
	return { ok: true, value };
}
function nonblank(value: unknown): value is string {
	return typeof value === "string" && value.trim().length > 0;
}
function count(value: unknown, min = 0): value is number {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= min;
}
function iso(value: unknown): value is string {
	if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)) return false;
	const ms = Date.parse(value);
	if (!Number.isSafeInteger(ms)) return false;
	const canonical = new Date(ms).toISOString();
	return canonical === value || canonical.replace(".000Z", "Z") === value;
}
function validBinding(binding: RuntimeBudgetBinding): boolean {
	return (
		!!binding &&
		nonblank(binding.authorization_unit) &&
		nonblank(binding.parent_budget_ref) &&
		nonblank(binding.matter_ref)
	);
}
function unitKey(binding: RuntimeBudgetBinding): string {
	return JSON.stringify([binding.authorization_unit, binding.parent_budget_ref]);
}
function sameBinding(a: RuntimeBudgetBinding, b: RuntimeBudgetBinding): boolean {
	return unitKey(a) === unitKey(b) && a.matter_ref === b.matter_ref;
}
function sameAction(a: RuntimeBudgetAction, b: RuntimeBudgetAction): boolean {
	return (
		sameBinding(a, b) &&
		a.call_id === b.call_id &&
		a.max_cost === b.max_cost &&
		a.cost_unit === b.cost_unit &&
		a.child_reservation_id === b.child_reservation_id
	);
}
function validDigests(value: RuntimeBudgetEvidenceDigest[]): boolean {
	return (
		Array.isArray(value) &&
		value.every(
			(entry) =>
				entry && nonblank(entry.ref) && typeof entry.sha256 === "string" && /^[a-f0-9]{64}$/.test(entry.sha256),
		) &&
		new Set(value.map((entry) => entry.ref)).size === value.length
	);
}
function evidenceKey(evidence: RuntimeBudgetEvidenceDigest[]): string {
	return JSON.stringify(evidence.map((entry) => [entry.ref, entry.sha256]).sort((a, b) => a[0].localeCompare(b[0])));
}

/** One controller per host authorization registry, shared across turns/cards.
 * All mutations are synchronous (no await/reentrant callback while committing).
 * No filesystem locks are acquired: the caller owns existing coordination;
 * frozen store may already own its intent lock. This is NOT a cross-process
 * budget server or a second selection/execution/DP writer. */
export function createRuntimeBudgetController(options: RuntimeBudgetOptions): RuntimeBudgetController {
	const units = new Map<string, UnitState>();
	const unitRefs = new Map<string, string>();
	const refUnits = new Map<string, string>();
	const callUnits = new Map<string, string>();
	let mutating = false;

	function now(): RuntimeBudgetResult<number> {
		try {
			const at = options.clock();
			return count(at) && at <= 8_640_000_000_000_000
				? good(at)
				: fail("invalid-clock", "finite non-negative epoch milliseconds required");
		} catch {
			return fail("invalid-clock", "trusted clock unavailable");
		}
	}
	function find(binding: RuntimeBudgetBinding, at: number): RuntimeBudgetResult<UnitState> {
		if (!validBinding(binding)) return fail("invalid-input", "canonical unit, parent budget and matter required");
		const unit = units.get(unitKey(binding));
		if (!unit || !unit.matters.has(binding.matter_ref))
			return fail("not-open", "host must open/bind this matter outside trusted-context reads");
		if (at < unit.lastAt) return fail("invalid-clock", "clock moved behind the last verified host event");
		return good(unit);
	}
	function readSnapshot(unit: UnitState, binding: RuntimeBudgetBinding, at: number): RuntimeBudgetSnapshot {
		let heldSteps = 0;
		let heldCost = 0;
		let inFlight = 0;
		for (const child of unit.children.values()) {
			if (child.settled) continue;
			heldSteps += Math.max(0, child.request.steps - child.steps);
			heldCost += Math.max(0, child.request.cost - child.cost);
		}
		for (const action of unit.actions.values()) {
			if (action.observation) continue;
			inFlight++;
			if (action.request.child_reservation_id !== undefined) continue;
			heldSteps++;
			heldCost += action.request.max_cost;
		}
		const remainingCost = Math.max(0, unit.initial.remaining_cost - unit.cost);
		const availableSteps = Math.max(0, unit.initial.max_steps - unit.steps - heldSteps);
		const availableCost = Math.max(0, remainingCost - heldCost);
		return {
			budget: {
				...unit.initial,
				matter_ref: binding.matter_ref,
				steps_consumed: unit.steps,
				cost_consumed: unit.cost,
				remaining_cost: remainingCost,
				no_progress_count: unit.noProgress,
				source_refs: [...unit.initial.source_refs],
			},
			cost_unit: unit.costUnit,
			available_steps: availableSteps,
			available_cost: availableCost,
			held_steps: heldSteps,
			held_cost: heldCost,
			in_flight: inFlight,
			blocked: unit.overrun
				? "cost-overrun"
				: at >= Date.parse(unit.initial.deadline) ||
						unit.steps >= unit.initial.max_steps ||
						remainingCost <= 0 ||
						unit.noProgress >= unit.initial.no_progress_limit
					? "budget-exhausted"
					: null,
		};
	}
	function actionPreflight(
		unit: UnitState,
		request: RuntimeBudgetAction,
		at: number,
	): RuntimeBudgetResult<BudgetReservationResult> {
		if (
			!nonblank(request.call_id) ||
			!count(request.max_cost, 1) ||
			request.cost_unit !== unit.costUnit ||
			(request.child_reservation_id !== undefined && !nonblank(request.child_reservation_id))
		)
			return fail("invalid-input", "real call id and positive safe-integer cost in the authorized unit required");
		const callUnit = callUnits.get(request.call_id);
		if (callUnit !== undefined && callUnit !== unitKey(request))
			return fail("conflict", "real call id already belongs to another authorization unit");
		const existing = unit.actions.get(request.call_id);
		if (existing && !sameAction(existing.request, request))
			return fail("conflict", "call id is already bound to a different action/matter/child");
		const snapshot = readSnapshot(unit, request, at);
		let steps = snapshot.available_steps;
		let cost = snapshot.available_cost;
		if (request.child_reservation_id !== undefined) {
			const child = unit.children.get(request.child_reservation_id);
			if (!child || child.settled || !sameBinding(child.request, request))
				return fail("conflict", "child reservation absent, settled or foreign");
			if (at >= Date.parse(child.request.deadline)) return fail("budget-exhausted", "fixed child deadline reached");
			steps = Math.max(0, child.request.steps - child.steps);
			cost = Math.max(0, child.request.cost - child.cost);
			for (const action of unit.actions.values()) {
				if (!action.observation && action.request.child_reservation_id === request.child_reservation_id) {
					steps--;
					cost -= action.request.max_cost;
				}
			}
		}
		const pendingDuplicate = existing !== undefined && existing.observation === undefined;
		const exhausted =
			snapshot.blocked !== null ||
			(existing !== undefined && !pendingDuplicate) ||
			(unit.noProgress + snapshot.in_flight >= unit.initial.no_progress_limit && !pendingDuplicate);
		const granted = !exhausted && (pendingDuplicate || (steps >= 1 && cost >= request.max_cost));
		const result: BudgetReservationResult = {
			granted,
			reserved_steps: granted ? 1 : 0,
			reserved_cost: granted ? request.max_cost : 0,
			...(request.child_reservation_id === undefined ? {} : { child_budget_ref: request.child_reservation_id }),
			remaining_after_steps: Math.max(0, steps - (granted && !pendingDuplicate ? 1 : 0)),
			remaining_after_cost: Math.max(0, cost - (granted && !pendingDuplicate ? request.max_cost : 0)),
			reason: granted ? "granted" : exhausted ? "budget-exhausted" : "insufficient-remaining",
		};
		const checked = parseBudgetReservationResult(result);
		return checked.ok ? good(checked.value) : fail("invalid-input", "reservation arithmetic is not finite/safe");
	}
	function capture(binding: RuntimeBudgetBinding): RuntimeBudgetEvidenceDigest[] {
		try {
			const evidence = options.captureEvidence({ ...binding });
			if (!evidence || !Array.isArray(evidence)) return [];
			if (!evidence.every((entry) => entry && entry.bytes instanceof Uint8Array)) return [];
			const digests = evidence.map((entry) => ({
				ref: entry.ref,
				sha256: createHash("sha256").update(Buffer.from(entry.bytes)).digest("hex"),
			}));
			return validDigests(digests) ? digests : [];
		} catch {
			return [];
		}
	}
	function reserve(
		unit: UnitState,
		request: RuntimeBudgetAction,
		at: number,
		evidence: RuntimeBudgetEvidenceDigest[],
	): RuntimeBudgetResult<RuntimeBudgetActionResult> {
		const callUnit = callUnits.get(request.call_id);
		if (callUnit !== undefined && callUnit !== unitKey(request))
			return fail("conflict", "real call id already belongs to another authorization unit");
		const previous = unit.actions.get(request.call_id);
		if (previous) {
			return sameAction(previous.request, request)
				? good({ status: "duplicate", execute: false, progress: previous.progress, overrun: previous.overrun })
				: fail("conflict", "call id is already bound to a different action/matter/child");
		}
		const checked = actionPreflight(unit, request, at);
		if (!checked.ok) return checked;
		if (!checked.value.granted)
			return fail(
				checked.value.reason === "budget-exhausted" ? "budget-exhausted" : "insufficient-remaining",
				"no actual action permitted by current parent/child allowance",
			);
		unit.actions.set(request.call_id, {
			request: { ...request },
			before: evidence.map((entry) => ({ ...entry })),
			progress: false,
			overrun: false,
		});
		if (evidence.length) unit.seenEvidence.add(evidenceKey(evidence));
		unit.lastAt = at;
		return good({ status: "reserved", execute: true, progress: false, overrun: false });
	}
	function observe(
		unit: UnitState,
		request: RuntimeBudgetObservation,
		at: number,
		evidence: RuntimeBudgetEvidenceDigest[],
	): RuntimeBudgetResult<RuntimeBudgetActionResult> {
		if (
			!nonblank(request.call_id) ||
			!nonblank(request.result_ref) ||
			!["success", "error", "unknown"].includes(request.outcome) ||
			!count(request.actual_cost) ||
			request.cost_unit !== unit.costUnit
		)
			return fail("invalid-input", "real result, explicit outcome and safe-integer actual cost/unit required");
		const action = unit.actions.get(request.call_id);
		if (!action) return fail("not-reserved", "unobserved/unreserved call cannot spend or prove progress");
		if (!sameBinding(action.request, request))
			return fail("conflict", "result belongs to a different matter/authorization");
		if (action.observation) {
			const previous = action.observation;
			return previous.result_ref === request.result_ref &&
				previous.outcome === request.outcome &&
				previous.actual_cost === request.actual_cost &&
				previous.cost_unit === request.cost_unit
				? good({ status: "duplicate", execute: false, progress: action.progress, overrun: action.overrun })
				: fail("conflict", "call already has a different immutable result");
		}
		if (!count(unit.cost + request.actual_cost)) {
			unit.overrun = true;
			return fail("cost-overrun", "actual aggregate cost overflow; unit quarantined, pending action NOT refunded");
		}
		const current = new Map(evidence.map((entry) => [entry.ref, entry.sha256]));
		const progress =
			request.outcome === "success" &&
			action.before.length > 0 &&
			action.before.length === evidence.length &&
			action.before.every((entry) => current.has(entry.ref)) &&
			action.before.some((entry) => current.get(entry.ref) !== entry.sha256) &&
			!unit.seenEvidence.has(evidenceKey(evidence));
		if (evidence.length) unit.seenEvidence.add(evidenceKey(evidence));
		const overrun = request.actual_cost > action.request.max_cost;
		unit.steps++;
		unit.cost += request.actual_cost;
		unit.noProgress = progress ? 0 : unit.noProgress + 1;
		unit.overrun ||= overrun;
		if (action.request.child_reservation_id !== undefined) {
			const child = unit.children.get(action.request.child_reservation_id);
			if (child) {
				child.steps++;
				child.cost += request.actual_cost;
			}
		}
		action.observation = { ...request };
		action.progress = progress;
		action.overrun = overrun;
		unit.lastAt = at;
		return good({ status: "observed", execute: false, progress, overrun });
	}
	function reserveChild(
		unit: UnitState,
		request: RuntimeBudgetChild,
		at: number,
	): RuntimeBudgetResult<RuntimeBudgetChildResult> {
		if (
			!nonblank(request.reservation_id) ||
			!count(request.steps, 1) ||
			!count(request.cost, 1) ||
			request.cost_unit !== unit.costUnit ||
			!iso(request.deadline) ||
			Date.parse(request.deadline) > Date.parse(unit.initial.deadline)
		)
			return fail("invalid-input", "finite positive child allocation/unit and bounded canonical deadline required");
		const previous = unit.children.get(request.reservation_id);
		if (previous) {
			const prior = previous.request;
			return sameBinding(prior, request) &&
				prior.steps === request.steps &&
				prior.cost === request.cost &&
				prior.cost_unit === request.cost_unit &&
				prior.deadline === request.deadline
				? good({ status: "duplicate", released_steps: 0, released_cost: 0 })
				: fail("conflict", "child reservation id already bound differently");
		}
		const snapshot = readSnapshot(unit, request, at);
		if (snapshot.blocked || at >= Date.parse(request.deadline))
			return fail(snapshot.blocked ?? "budget-exhausted", "parent/child exhausted; no new child budget");
		if (request.steps > snapshot.available_steps || request.cost > snapshot.available_cost)
			return fail("insufficient-remaining", "sum of child holds exceeds unreserved parent allowance");
		unit.children.set(request.reservation_id, { request: { ...request }, steps: 0, cost: 0, settled: false });
		unit.lastAt = at;
		return good({ status: "reserved", released_steps: 0, released_cost: 0 });
	}
	function settle(
		unit: UnitState,
		request: RuntimeBudgetSettlement,
		at: number,
	): RuntimeBudgetResult<RuntimeBudgetChildResult> {
		if (!nonblank(request.reservation_id)) return fail("invalid-input", "child reservation id required");
		const child = unit.children.get(request.reservation_id);
		if (!child) return fail("not-reserved", "child reservation does not exist");
		if (!sameBinding(child.request, request)) return fail("conflict", "child settlement binding drift");
		if (child.settled) return good({ status: "duplicate", released_steps: 0, released_cost: 0 });
		if (
			[...unit.actions.values()].some(
				(action) => action.request.child_reservation_id === request.reservation_id && !action.observation,
			)
		)
			return fail(
				"in-flight",
				"cannot release allowance backing an outstanding action; observe or settleUnknown first",
			);
		child.settled = true;
		unit.lastAt = at;
		return good({
			status: "settled",
			released_steps: Math.max(0, child.request.steps - child.steps),
			released_cost: Math.max(0, child.request.cost - child.cost),
		});
	}
	function mutate<T>(operation: (at: number) => RuntimeBudgetResult<T>): RuntimeBudgetResult<T> {
		if (mutating) return fail("conflict", "reentrant budget mutation refused");
		const time = now();
		if (!time.ok) return time;
		mutating = true;
		try {
			return operation(time.value);
		} finally {
			mutating = false;
		}
	}

	return {
		open(binding) {
			return mutate((at) => {
				if (!validBinding(binding)) return fail("invalid-input", "canonical unit/parent/matter required");
				let authorization: RuntimeBudgetAuthorization | undefined;
				try {
					authorization = options.readAuthorization({ ...binding });
				} catch {
					return fail("authorization-missing", "host could not verify authority/card/history");
				}
				if (!authorization) return fail("authorization-missing", "host verified authorization unavailable");
				const checked = validateMatterBudget(authorization.initial);
				if (!checked.ok)
					return fail("invalid-input", checked.issues.map((issue) => `${issue.field}: ${issue.rule}`).join("; "));
				const initial = checked.value;
				if (
					authorization.authorization_unit !== binding.authorization_unit ||
					authorization.parent_budget_ref !== binding.parent_budget_ref ||
					initial.budget_ref !== binding.parent_budget_ref ||
					initial.matter_ref !== binding.authorization_unit
				)
					return fail("authorization-drift", "host canonical authorization unit/parent/card genesis mismatch");
				if (
					!nonblank(authorization.cost_unit) ||
					!iso(authorization.started_at) ||
					!iso(initial.deadline) ||
					Date.parse(authorization.started_at) > at ||
					Date.parse(initial.deadline) <= Date.parse(authorization.started_at) ||
					!count(initial.remaining_cost) ||
					initial.steps_consumed !== 0 ||
					initial.cost_consumed !== 0 ||
					initial.no_progress_count !== 0
				)
					return fail(
						"invalid-input",
						"verified genesis, atomic cost unit, canonical finite dates and explicit zero initial counters required",
					);
				const key = unitKey(binding);
				const knownRef = unitRefs.get(binding.authorization_unit);
				const knownUnit = refUnits.get(binding.parent_budget_ref);
				if (knownUnit !== undefined && knownUnit !== binding.authorization_unit)
					return fail("authorization-drift", "parent budget cannot be cloned under a new authorization label");
				if (knownRef !== undefined && knownRef !== binding.parent_budget_ref)
					return fail(
						"authorization-drift",
						"new card cannot mint a new parent budget for an existing authorization unit",
					);
				const existing = units.get(key);
				if (existing) {
					if (at < existing.lastAt) return fail("invalid-clock", "clock moved behind verified history");
					if (
						JSON.stringify({ ...existing.initial, source_refs: [] }) !==
							JSON.stringify({ ...initial, source_refs: [] }) ||
						existing.costUnit !== authorization.cost_unit ||
						existing.startedAt !== authorization.started_at
					)
						return fail(
							"authorization-drift",
							"limits, deadline, genesis or unit changed under an existing authorization",
						);
					existing.matters.add(binding.matter_ref);
					return good(readSnapshot(existing, binding, at));
				}
				const history = authorization.history;
				if (!history)
					return fail(
						"history-missing",
						"no verified fresh-run empty history or complete host trace replay; never reset to zero",
					);
				if (
					!["verified-empty", "verified-replay"].includes(history.kind) ||
					!nonblank(history.origin_ref) ||
					!nonblank(history.through_ref) ||
					!Array.isArray(history.events) ||
					(history.kind === "verified-empty" && history.events.length !== 0)
				)
					return fail("history-invalid", "complete verified host history required");
				const unit: UnitState = {
					initial: { ...initial, source_refs: [...initial.source_refs] },
					costUnit: authorization.cost_unit,
					startedAt: authorization.started_at,
					lastAt: Date.parse(authorization.started_at),
					matters: new Set([binding.matter_ref]),
					actions: new Map(),
					children: new Map(),
					seenEvidence: new Set(),
					steps: 0,
					cost: 0,
					noProgress: 0,
					overrun: false,
				};
				for (const event of history.events) {
					if (
						!event ||
						!count(event.at) ||
						event.at < unit.lastAt ||
						event.at > at ||
						!validBinding(event.request) ||
						unitKey(event.request) !== key
					)
						return fail("history-invalid", "replay time/order/parent binding invalid");
					unit.matters.add(event.request.matter_ref);
					let result: RuntimeBudgetResult<RuntimeBudgetActionResult | RuntimeBudgetChildResult>;
					switch (event.kind) {
						case "reserve":
							if (!validDigests(event.evidence)) return fail("history-invalid", "invalid reserve byte evidence");
							result = reserve(unit, event.request, event.at, event.evidence);
							break;
						case "observe":
							if (!validDigests(event.evidence)) return fail("history-invalid", "invalid result byte evidence");
							result = observe(unit, event.request, event.at, event.evidence);
							break;
						case "reserve-child":
							result = reserveChild(unit, event.request, event.at);
							break;
						case "settle":
							result = settle(unit, event.request, event.at);
							break;
						default:
							return fail("history-invalid", "unknown host history event");
					}
					if (!result.ok) return fail("history-invalid", `${result.code}: ${result.gap}`);
					unit.lastAt = event.at;
				}
				units.set(key, unit);
				unitRefs.set(binding.authorization_unit, binding.parent_budget_ref);
				refUnits.set(binding.parent_budget_ref, binding.authorization_unit);
				for (const callId of unit.actions.keys()) callUnits.set(callId, key);
				return good(readSnapshot(unit, binding, at));
			});
		},
		snapshot(binding) {
			const time = now();
			if (!time.ok) return time;
			const found = find(binding, time.value);
			return found.ok ? good(readSnapshot(found.value, binding, time.value)) : found;
		},
		preflight(request) {
			const time = now();
			if (!time.ok) return time;
			const found = find(request, time.value);
			return found.ok ? actionPreflight(found.value, request, time.value) : found;
		},
		reserve(request) {
			return mutate((at) => {
				const found = find(request, at);
				if (!found.ok) return found;
				const result = reserve(
					found.value,
					request,
					at,
					found.value.actions.has(request.call_id) ? [] : capture(request),
				);
				if (result.ok && result.value.status === "reserved") callUnits.set(request.call_id, unitKey(request));
				return result;
			});
		},
		observe(request) {
			return mutate((at) => {
				const found = find(request, at);
				if (!found.ok) return found;
				return observe(
					found.value,
					request,
					at,
					found.value.actions.get(request.call_id)?.observation ? [] : capture(request),
				);
			});
		},
		settleUnknown(binding, callId, resultRef) {
			return mutate((at) => {
				const found = find(binding, at);
				if (!found.ok) return found;
				const action = found.value.actions.get(callId);
				if (!action) return fail("not-reserved", "unknown action must first have a real reservation");
				return observe(
					found.value,
					{
						...binding,
						call_id: callId,
						result_ref: resultRef,
						outcome: "unknown",
						actual_cost: action.request.max_cost,
						cost_unit: found.value.costUnit,
					},
					at,
					[],
				);
			});
		},
		reserveChild(request) {
			return mutate((at) => {
				const found = find(request, at);
				return found.ok ? reserveChild(found.value, request, at) : found;
			});
		},
		settle(request) {
			return mutate((at) => {
				const found = find(request, at);
				return found.ok ? settle(found.value, request, at) : found;
			});
		},
	};
}
