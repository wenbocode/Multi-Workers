/** T06-C algorithm + isolated real tool-event probe. Host authority/history
 * fixtures below are NOT production-observed events or a completed T06 chain. */
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it } from "vitest";
import {
	createRuntimeBudgetController,
	type RuntimeBudgetAction,
	type RuntimeBudgetAuthorization,
	type RuntimeBudgetBinding,
	type RuntimeBudgetChild,
	type RuntimeBudgetCode,
	type RuntimeBudgetEvidence,
	type RuntimeBudgetObservation,
	type RuntimeBudgetReplayEvent,
	type RuntimeBudgetResult,
} from "../../src/extensions/agent-team-loop/pm/runtime-budget.ts";
import {
	type MatterBudgetV1,
	parseBudgetReservationResult,
	validateMatterBudget,
} from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { createHarness, type Harness } from "./harness.ts";

const NOW = Date.parse("2026-11-15T15:00:00.000Z");
const DEADLINE = "2026-11-15T15:30:00.000Z";
const UNIT = "tool-call-equivalent";
const binding: RuntimeBudgetBinding = {
	authorization_unit: "key/T06-root",
	parent_budget_ref: "card/root-budget#sha256-pinned",
	matter_ref: "business-hash-a",
};
const roots: string[] = [];
const harnesses: Harness[] = [];
afterEach(() => {
	for (const harness of harnesses.splice(0)) harness.cleanup();
	for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

function value<T>(result: RuntimeBudgetResult<T>): T {
	expect(result.ok, JSON.stringify(result)).toBe(true);
	if (!result.ok) throw new Error(`${result.code}: ${result.gap}`);
	return result.value;
}
function refused(result: RuntimeBudgetResult<unknown>, code: RuntimeBudgetCode): void {
	expect(result).toMatchObject({ ok: false, code });
	if (!result.ok) expect(result.gap.length).toBeGreaterThan(0);
}
function action(callId: string, overrides: Partial<RuntimeBudgetAction> = {}): RuntimeBudgetAction {
	return { ...binding, call_id: callId, max_cost: 1, cost_unit: UNIT, ...overrides };
}
function observation(callId: string, overrides: Partial<RuntimeBudgetObservation> = {}): RuntimeBudgetObservation {
	return {
		...binding,
		call_id: callId,
		result_ref: `run/result/${callId}`,
		outcome: "success",
		actual_cost: 1,
		cost_unit: UNIT,
		...overrides,
	};
}
function child(id: string, overrides: Partial<RuntimeBudgetChild> = {}): RuntimeBudgetChild {
	return { ...binding, reservation_id: id, steps: 1, cost: 1, cost_unit: UNIT, deadline: DEADLINE, ...overrides };
}
function fixture(overrides: Partial<MatterBudgetV1> = {}) {
	const root = mkdtempSync(join(tmpdir(), "runtime-budget-"));
	roots.push(root);
	const target = join(root, "evidence.txt");
	writeFileSync(target, "initial bytes");
	const initial: MatterBudgetV1 = {
		schema_version: 1,
		budget_ref: binding.parent_budget_ref,
		matter_ref: binding.authorization_unit,
		parent_matter_ref: "key",
		deadline: DEADLINE,
		max_steps: 3,
		no_progress_limit: 3,
		remaining_cost: 6,
		steps_consumed: 0,
		cost_consumed: 0,
		no_progress_count: 0,
		source_refs: ["fixture/pinned-card-bytes", "fixture/verified-run", "fixture/live-claim"],
		...overrides,
	};
	const host: {
		at: number;
		authority: RuntimeBudgetAuthorization | undefined;
		capture: () => readonly RuntimeBudgetEvidence[] | undefined;
	} = {
		at: NOW,
		authority: {
			authorization_unit: binding.authorization_unit,
			parent_budget_ref: binding.parent_budget_ref,
			initial,
			cost_unit: UNIT,
			started_at: new Date(NOW - 60_000).toISOString(),
			history: {
				kind: "verified-empty",
				origin_ref: "fixture/run-start-confirmed-no-prior-calls",
				through_ref: "fixture/host-trace-head",
				events: [],
			},
		},
		capture: () => [{ ref: "authorized/evidence.txt", bytes: readFileSync(target) }],
	};
	const options = {
		clock: () => host.at,
		readAuthorization: () => host.authority,
		captureEvidence: () => host.capture(),
	};
	const controller = createRuntimeBudgetController(options);
	return { root, target, initial, host, controller, options };
}

// The pure cases use real local evidence files and explicit host fixtures. The
// final describe uses suite harness + faux provider and real tool_call/results.
describe("runtime budget: finite parent accounting", () => {
	it("permits three real byte-changing steps and permits zero fourth actions", () => {
		const f = fixture();
		value(f.controller.open(binding));
		let executed = 0;
		for (let step = 1; step <= 4; step++) {
			const reserved = f.controller.reserve(action(`call-${step}`));
			if (!reserved.ok) {
				expect(step).toBe(4);
				refused(reserved, "budget-exhausted");
				continue;
			}
			expect(reserved.value.execute).toBe(true);
			executed++;
			writeFileSync(f.target, `actual changed bytes ${step}`);
			expect(value(f.controller.observe(observation(`call-${step}`))).progress).toBe(true);
		}
		expect(executed).toBe(3);
		const snapshot = value(f.controller.snapshot(binding));
		expect(snapshot.budget).toMatchObject({
			steps_consumed: 3,
			cost_consumed: 3,
			remaining_cost: 3,
			no_progress_count: 0,
		});
		expect(snapshot.blocked).toBe("budget-exhausted");
		expect(validateMatterBudget(snapshot.budget).ok).toBe(true);
	});

	it("does not credit concurrent or previously seen byte states twice", () => {
		const f = fixture({ max_steps: 5 });
		value(f.controller.open(binding));
		value(f.controller.reserve(action("first")));
		value(f.controller.reserve(action("overlap")));
		writeFileSync(f.target, "one real change");
		expect(value(f.controller.observe(observation("first"))).progress).toBe(true);
		expect(value(f.controller.observe(observation("overlap"))).progress).toBe(false);
		value(f.controller.reserve(action("revert")));
		writeFileSync(f.target, "initial bytes");
		expect(value(f.controller.observe(observation("revert"))).progress).toBe(false);
		expect(value(f.controller.snapshot(binding)).budget.no_progress_count).toBe(2);
	});

	it("deduplicates reservation and immutable result; conflicts never refund", () => {
		const f = fixture();
		value(f.controller.open(binding));
		expect(value(f.controller.reserve(action("a"))).execute).toBe(true);
		const pending = value(f.controller.snapshot(binding));
		expect(value(f.controller.reserve(action("a")))).toMatchObject({ status: "duplicate", execute: false });
		expect(value(f.controller.snapshot(binding))).toEqual(pending);
		refused(f.controller.reserve(action("a", { max_cost: 2 })), "conflict");
		writeFileSync(f.target, "changed");
		expect(value(f.controller.observe(observation("a"))).progress).toBe(true);
		const observed = value(f.controller.snapshot(binding));
		expect(value(f.controller.observe(observation("a"))).status).toBe("duplicate");
		refused(f.controller.observe(observation("a", { result_ref: "other" })), "conflict");
		expect(value(f.controller.reserve(action("a"))).execute).toBe(false);
		expect(value(f.controller.snapshot(binding))).toEqual(observed);
		refused(f.controller.observe(observation("nonexistent")), "not-reserved");
	});

	it("deduplicates real call ids across units without stopping independent authorized work", () => {
		const f = fixture({ max_steps: 1 });
		value(f.controller.open(binding));
		value(f.controller.reserve(action("global-call")));
		value(f.controller.observe(observation("global-call")));
		refused(f.controller.reserve(action("exhausted")), "budget-exhausted");
		if (!f.host.authority) throw new Error("fixture authority missing");
		const independent = { ...binding, authorization_unit: "unit-b", parent_budget_ref: "budget-b" };
		f.host.authority = {
			...f.host.authority,
			...independent,
			initial: { ...f.initial, budget_ref: "budget-b", matter_ref: "unit-b" },
		};
		value(f.controller.open(independent));
		refused(f.controller.reserve(action("global-call", independent)), "conflict");
		refused(f.controller.preflight(action("global-call", independent)), "conflict");
		expect(value(f.controller.reserve(action("independent-call", independent))).execute).toBe(true);
		value(f.controller.observe(observation("independent-call", independent)));
		expect(value(f.controller.snapshot(independent)).budget.steps_consumed).toBe(1);
	});

	it("snapshot and preflight are pure, repeatable, detached and frozen-compatible", () => {
		const f = fixture();
		value(f.controller.open(binding));
		const before = value(f.controller.snapshot(binding));
		for (let repeat = 0; repeat < 5; repeat++) {
			const preflight = value(f.controller.preflight(action("future")));
			expect(preflight).toMatchObject({
				granted: true,
				reserved_steps: 1,
				reserved_cost: 1,
				remaining_after_steps: 2,
			});
			expect(parseBudgetReservationResult(preflight).ok).toBe(true);
			expect(value(f.controller.snapshot(binding))).toEqual(before);
		}
		const detached = value(f.controller.snapshot(binding));
		detached.budget.source_refs.push("foreign");
		detached.budget.steps_consumed = 999;
		expect(value(f.controller.snapshot(binding))).toEqual(before);
		value(f.controller.reserve(action("future")));
		const held = value(f.controller.snapshot(binding));
		expect(held.budget.steps_consumed).toBe(0);
		expect(held.in_flight).toBe(1);
		expect(held.available_steps).toBe(2);
		expect(value(f.controller.preflight(action("future"))).granted).toBe(true);
		expect(value(f.controller.snapshot(binding))).toEqual(held);
	});

	it("error/unknown consume cost and no-progress even if bytes changed; success resets only no-progress", () => {
		const f = fixture({ max_steps: 5, no_progress_limit: 3 });
		value(f.controller.open(binding));
		for (const outcome of ["error", "unknown"] as const) {
			value(f.controller.reserve(action(outcome)));
			writeFileSync(f.target, `changed despite ${outcome}`);
			expect(value(f.controller.observe(observation(outcome, { outcome }))).progress).toBe(false);
		}
		expect(value(f.controller.snapshot(binding)).budget).toMatchObject({
			steps_consumed: 2,
			cost_consumed: 2,
			no_progress_count: 2,
		});
		value(f.controller.reserve(action("real-progress")));
		writeFileSync(f.target, "actual verified successful change");
		expect(value(f.controller.observe(observation("real-progress"))).progress).toBe(true);
		expect(value(f.controller.snapshot(binding)).budget).toMatchObject({
			steps_consumed: 3,
			cost_consumed: 3,
			no_progress_count: 0,
		});
	});

	it("unchanged bytes exhaust no-progress and outstanding calls reserve its worst-case capacity", () => {
		const f = fixture({ max_steps: 10, no_progress_limit: 2 });
		value(f.controller.open(binding));
		value(f.controller.reserve(action("a")));
		value(f.controller.reserve(action("b")));
		refused(f.controller.reserve(action("too-many-pending")), "budget-exhausted");
		expect(value(f.controller.observe(observation("a"))).progress).toBe(false);
		expect(value(f.controller.observe(observation("b"))).progress).toBe(false);
		expect(value(f.controller.snapshot(binding)).budget.no_progress_count).toBe(2);
		refused(f.controller.reserve(action("third")), "budget-exhausted");
	});

	it.each(["missing", "throwing", "changed-ref", "duplicate-ref"])(
		"does not invent progress from %s evidence",
		(mode) => {
			const f = fixture();
			value(f.controller.open(binding));
			value(f.controller.reserve(action("a")));
			writeFileSync(f.target, "different");
			f.host.capture = () => {
				if (mode === "throwing") throw new Error("unreadable evidence");
				if (mode === "missing") return undefined;
				if (mode === "changed-ref") return [{ ref: "different-target", bytes: readFileSync(f.target) }];
				return [
					{ ref: "duplicate", bytes: Buffer.from("a") },
					{ ref: "duplicate", bytes: Buffer.from("b") },
				];
			};
			expect(value(f.controller.observe(observation("a"))).progress).toBe(false);
			expect(value(f.controller.snapshot(binding)).budget.no_progress_count).toBe(1);
		},
	);

	it("keeps counters/deadline across turns/triggers/routes/new cards and refuses a new parent ref", () => {
		const f = fixture();
		value(f.controller.open(binding));
		value(f.controller.reserve(action("a")));
		value(f.controller.observe(observation("a", { outcome: "error" })));
		for (const wrapper of ["new-turn", "new-trigger", "route", "new-child-card"]) {
			const next = { ...binding, matter_ref: `host-bound-${wrapper}` };
			const snapshot = value(f.controller.open(next));
			expect(snapshot.budget).toMatchObject({
				steps_consumed: 1,
				cost_consumed: 1,
				remaining_cost: 5,
				no_progress_count: 1,
				deadline: DEADLINE,
			});
			expect(snapshot.budget.matter_ref).toBe(next.matter_ref);
			refused(f.controller.observe(observation("a", { matter_ref: next.matter_ref })), "conflict");
		}
		const newParent = { ...binding, parent_budget_ref: "new-card-budget" };
		if (!f.host.authority) throw new Error("fixture authority missing");
		f.host.authority.parent_budget_ref = newParent.parent_budget_ref;
		f.host.authority.initial.budget_ref = newParent.parent_budget_ref;
		refused(f.controller.open(newParent), "authorization-drift");
		expect(value(f.controller.snapshot(binding)).budget.steps_consumed).toBe(1);
	});

	it("cannot clone one parent balance under a new authorization label", () => {
		const f = fixture();
		value(f.controller.open(binding));
		if (!f.host.authority) throw new Error("fixture authority missing");
		const alias = { ...binding, authorization_unit: "new-label" };
		f.host.authority.authorization_unit = alias.authorization_unit;
		f.host.authority.initial.matter_ref = alias.authorization_unit;
		refused(f.controller.open(alias), "authorization-drift");
	});

	it.each(["max_steps", "no_progress_limit", "remaining_cost", "deadline"] as const)(
		"rejects changed immutable %s without resetting state",
		(field) => {
			const f = fixture();
			value(f.controller.open(binding));
			if (field === "deadline") f.initial.deadline = "2026-11-15T16:00:00.000Z";
			else f.initial[field]++;
			refused(f.controller.open(binding), "authorization-drift");
			expect(value(f.controller.snapshot(binding)).budget.deadline).toBe(DEADLINE);
		},
	);

	it("accounts after expiry but no new action can start at the exact trusted deadline", () => {
		const f = fixture();
		value(f.controller.open(binding));
		value(f.controller.reserve(action("in-flight", { max_cost: 2 })));
		f.host.at = Date.parse(DEADLINE);
		refused(f.controller.reserve(action("late")), "budget-exhausted");
		expect(value(f.controller.preflight(action("late"))).granted).toBe(false);
		expect(value(f.controller.settleUnknown(binding, "in-flight", "host/missing-result"))).toMatchObject({
			status: "observed",
			progress: false,
		});
		expect(value(f.controller.snapshot(binding)).budget).toMatchObject({
			steps_consumed: 1,
			cost_consumed: 2,
			remaining_cost: 4,
		});
		expect(value(f.controller.settleUnknown(binding, "in-flight", "host/missing-result")).status).toBe("duplicate");
		refused(f.controller.reserve(action("in-flight", { max_cost: 3 })), "conflict");
	});

	it("quarantines aggregate cost overflow without releasing the outstanding hold", () => {
		const f = fixture({ remaining_cost: Number.MAX_SAFE_INTEGER });
		value(f.controller.open(binding));
		const largeCost = Number.MAX_SAFE_INTEGER - 1;
		value(f.controller.reserve(action("large", { max_cost: largeCost })));
		value(f.controller.observe(observation("large", { actual_cost: largeCost })));
		value(f.controller.reserve(action("overflow")));
		refused(f.controller.observe(observation("overflow", { actual_cost: 2 })), "cost-overrun");
		const snapshot = value(f.controller.snapshot(binding));
		expect(snapshot.blocked).toBe("cost-overrun");
		expect(snapshot.in_flight).toBe(1);
		expect(snapshot.available_cost).toBe(0);
		expect(value(f.controller.preflight(action("never"))).granted).toBe(false);
	});

	it("charges actual overruns and quarantines the unit rather than refunding or authorizing more", () => {
		const f = fixture();
		value(f.controller.open(binding));
		value(f.controller.reserve(action("a")));
		expect(value(f.controller.observe(observation("a", { actual_cost: 4 })))).toMatchObject({ overrun: true });
		const snapshot = value(f.controller.snapshot(binding));
		expect(snapshot.budget).toMatchObject({ steps_consumed: 1, cost_consumed: 4, remaining_cost: 2 });
		expect(snapshot.blocked).toBe("cost-overrun");
		refused(f.controller.reserveChild(child("later")), "cost-overrun");
		expect(value(f.controller.preflight(action("later"))).granted).toBe(false);
	});
});

describe("runtime budget: parallel child reservations", () => {
	it("atomically shares parent capacity across competing parallel children, never copies it", async () => {
		const f = fixture({ max_steps: 3, remaining_cost: 3 });
		value(f.controller.open(binding));
		const requests = [child("child-a", { steps: 2, cost: 2 }), child("child-b", { steps: 2, cost: 2 })];
		const results = await Promise.all(requests.map(async (request) => f.controller.reserveChild(request)));
		expect(results.filter((result) => result.ok)).toHaveLength(1);
		refused(results[1], "insufficient-remaining");
		expect(value(f.controller.snapshot(binding))).toMatchObject({
			held_steps: 2,
			held_cost: 2,
			available_steps: 1,
			available_cost: 1,
		});
		expect(value(f.controller.reserveChild(requests[0])).status).toBe("duplicate");
		value(f.controller.reserveChild(child("child-c")));
		refused(f.controller.reserve(action("root-cannot-steal")), "insufficient-remaining");
		refused(f.controller.reserveChild(child("child-d")), "insufficient-remaining");
	});

	it("child actions consume parent once; failed action cost is not refunded on release", () => {
		const f = fixture({ max_steps: 4, remaining_cost: 4 });
		value(f.controller.open(binding));
		value(f.controller.reserveChild(child("c", { steps: 3, cost: 3 })));
		const request = action("child-action", { child_reservation_id: "c" });
		value(f.controller.reserve(request));
		refused(f.controller.settle({ ...binding, reservation_id: "c" }), "in-flight");
		expect(value(f.controller.snapshot(binding)).held_cost).toBe(3);
		value(f.controller.observe(observation("child-action", { outcome: "error" })));
		expect(value(f.controller.settle({ ...binding, reservation_id: "c" }))).toEqual({
			status: "settled",
			released_steps: 2,
			released_cost: 2,
		});
		const snapshot = value(f.controller.snapshot(binding));
		expect(snapshot).toMatchObject({ held_steps: 0, held_cost: 0, available_steps: 3, available_cost: 3 });
		expect(snapshot.budget).toMatchObject({ steps_consumed: 1, cost_consumed: 1, no_progress_count: 1 });
		expect(value(f.controller.reserve(request))).toMatchObject({ status: "duplicate", execute: false });
		expect(value(f.controller.settle({ ...binding, reservation_id: "c" }))).toMatchObject({
			status: "duplicate",
			released_cost: 0,
		});
		refused(f.controller.reserve(action("new", { child_reservation_id: "c" })), "conflict");
	});

	it("enforces child-local steps/cost/deadline and cannot release someone else's child", () => {
		const f = fixture({ max_steps: 10, remaining_cost: 10 });
		value(f.controller.open(binding));
		value(f.controller.reserveChild(child("c", { steps: 1, cost: 2, deadline: "2026-11-15T15:01:00.000Z" })));
		refused(
			f.controller.reserve(action("too-expensive", { child_reservation_id: "c", max_cost: 3 })),
			"insufficient-remaining",
		);
		value(f.controller.reserve(action("one", { child_reservation_id: "c", max_cost: 2 })));
		refused(f.controller.reserve(action("two", { child_reservation_id: "c" })), "insufficient-remaining");
		value(f.controller.observe(observation("one")));
		refused(f.controller.reserve(action("three", { child_reservation_id: "c" })), "insufficient-remaining");
		const other = { ...binding, matter_ref: "another-matter" };
		value(f.controller.open(other));
		refused(f.controller.settle({ ...other, reservation_id: "c" }), "conflict");
		f.host.at += 60_000;
		refused(f.controller.reserve(action("late", { child_reservation_id: "c" })), "budget-exhausted");
		expect(value(f.controller.settle({ ...binding, reservation_id: "c" }))).toMatchObject({
			released_steps: 0,
			released_cost: 1,
		});
	});

	it("unknown child result spends its entire hold, leaving zero new exhausted child actions", () => {
		const f = fixture({ max_steps: 1, remaining_cost: 2 });
		value(f.controller.open(binding));
		value(f.controller.reserveChild(child("c", { cost: 2 })));
		value(f.controller.reserve(action("lost", { child_reservation_id: "c", max_cost: 2 })));
		value(f.controller.settleUnknown(binding, "lost", "host/unknown"));
		expect(value(f.controller.settle({ ...binding, reservation_id: "c" }))).toMatchObject({
			released_steps: 0,
			released_cost: 0,
		});
		refused(f.controller.reserveChild(child("successor")), "budget-exhausted");
		expect(value(f.controller.snapshot(binding)).budget).toMatchObject({
			steps_consumed: 1,
			cost_consumed: 2,
			remaining_cost: 0,
		});
	});
});

describe("runtime budget: strict inputs and verified restart boundary", () => {
	it.each([
		["max_steps", 0],
		["max_steps", -1],
		["max_steps", 1.5],
		["max_steps", Number.MAX_SAFE_INTEGER + 1],
		["no_progress_limit", -1],
		["remaining_cost", -1],
		["remaining_cost", NaN],
		["remaining_cost", Infinity],
		["remaining_cost", 1.5],
		["steps_consumed", -1],
		["steps_consumed", 1],
		["cost_consumed", 1],
		["no_progress_count", 1],
		["deadline", "2026-02-30T15:30:00.000Z"],
		["deadline", "+999999-01-01T00:00:00.000Z"],
		["deadline", "invalid"],
		["deadline", "1970-01-01T00:00:00.000Z"],
		["source_refs", []],
	])("refuses malformed/non-genesis card %s=%s", (field, invalid) => {
		const f = fixture();
		Object.assign(f.initial, { [field]: invalid });
		refused(f.controller.open(binding), "invalid-input");
		refused(f.controller.snapshot(binding), "not-open");
	});

	it.each([0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])(
		"refuses unsafe/zero reservation cost %s without spending",
		(maxCost) => {
			const f = fixture();
			value(f.controller.open(binding));
			const before = value(f.controller.snapshot(binding));
			refused(f.controller.reserve(action("bad", { max_cost: maxCost })), "invalid-input");
			expect(value(f.controller.snapshot(binding))).toEqual(before);
		},
	);

	it.each([-1, 1.5, NaN, Infinity])("refuses invalid observed cost %s and keeps its reservation", (actualCost) => {
		const f = fixture();
		value(f.controller.open(binding));
		value(f.controller.reserve(action("a")));
		const before = value(f.controller.snapshot(binding));
		refused(f.controller.observe(observation("a", { actual_cost: actualCost })), "invalid-input");
		expect(value(f.controller.snapshot(binding))).toEqual(before);
	});

	it.each(["", "dollars-not-authorized"])("rejects missing/foreign action and observation unit %s", (costUnit) => {
		const f = fixture();
		value(f.controller.open(binding));
		refused(f.controller.reserve(action("bad", { cost_unit: costUnit })), "invalid-input");
		value(f.controller.reserve(action("a")));
		refused(f.controller.observe(observation("a", { cost_unit: costUnit })), "invalid-input");
	});

	it("does not derive a missing cost unit or history from max_steps/timeout", () => {
		const f = fixture();
		if (!f.host.authority) throw new Error("fixture authority missing");
		f.host.authority.cost_unit = "";
		refused(f.controller.open(binding), "invalid-input");
		f.host.authority.cost_unit = UNIT;
		delete f.host.authority.history;
		refused(f.controller.open(binding), "history-missing");
	});

	it("explicit zero cost/no-progress allowance is exhausted, while zero actual cost still spends a step", () => {
		for (const limits of [{ remaining_cost: 0 }, { no_progress_limit: 0 }]) {
			const f = fixture(limits);
			expect(value(f.controller.open(binding)).blocked).toBe("budget-exhausted");
			refused(f.controller.reserve(action("never")), "budget-exhausted");
		}
		const f = fixture();
		value(f.controller.open(binding));
		value(f.controller.reserve(action("free-actual")));
		value(f.controller.observe(observation("free-actual", { actual_cost: 0 })));
		expect(value(f.controller.snapshot(binding)).budget).toMatchObject({
			steps_consumed: 1,
			cost_consumed: 0,
			remaining_cost: 6,
		});
	});

	it.each([NaN, Infinity, -1, 8_640_000_000_000_001])("uses the same trusted clock and rejects %s", (at) => {
		const f = fixture();
		f.host.at = at;
		refused(f.controller.open(binding), "invalid-clock");
		refused(f.controller.snapshot(binding), "invalid-clock");
	});

	it("refuses rollback behind an actual event but snapshot itself never advances the clock watermark", () => {
		const f = fixture();
		value(f.controller.open(binding));
		f.host.at += 1000;
		value(f.controller.snapshot(binding));
		f.host.at -= 500;
		value(f.controller.reserve(action("a")));
		f.host.at--;
		refused(f.controller.snapshot(binding), "invalid-clock");
	});

	it.each([
		{ steps: 0 },
		{ steps: -1 },
		{ steps: NaN },
		{ cost: 0 },
		{ cost: -1 },
		{ cost: Infinity },
		{ cost_unit: "" },
		{ deadline: "2026-11-16T00:00:00.000Z" },
		{ deadline: "overflow" },
	])("refuses invalid child allocation %j", (invalid) => {
		const f = fixture();
		value(f.controller.open(binding));
		refused(f.controller.reserveChild(child("bad", invalid)), "invalid-input");
		expect(value(f.controller.snapshot(binding)).held_steps).toBe(0);
	});

	it("restart with no verifiable history refuses instead of defaulting consumed to zero", () => {
		const f = fixture();
		value(f.controller.open(binding));
		value(f.controller.reserve(action("used")));
		value(f.controller.observe(observation("used")));
		if (!f.host.authority) throw new Error("fixture authority missing");
		delete f.host.authority.history;
		const restarted = createRuntimeBudgetController(f.options);
		refused(restarted.open(binding), "history-missing");
		refused(restarted.reserve(action("must-not-execute")), "not-open");
		expect(value(f.controller.snapshot(binding)).budget.steps_consumed).toBe(1);
	});

	it("replays host-verified history, including dedup ids and an in-flight child, without new allowance", () => {
		const f = fixture();
		const evidence = [
			{ ref: "authorized/evidence.txt", sha256: createHash("sha256").update("initial bytes").digest("hex") },
		];
		const events: RuntimeBudgetReplayEvent[] = [
			{ kind: "reserve", at: NOW - 3000, request: action("used"), evidence },
			{ kind: "observe", at: NOW - 2500, request: observation("used", { outcome: "error" }), evidence },
			{ kind: "observe", at: NOW - 2000, request: observation("used", { outcome: "error" }), evidence },
			{ kind: "reserve-child", at: NOW - 1500, request: child("pending-child", { steps: 2, cost: 2 }) },
			{
				kind: "reserve",
				at: NOW - 1000,
				request: action("pending", { child_reservation_id: "pending-child" }),
				evidence,
			},
		];
		if (!f.host.authority) throw new Error("fixture authority missing");
		f.host.authority.history = {
			kind: "verified-replay",
			origin_ref: "fixture/verified-start",
			through_ref: "fixture/complete-trace-head",
			events,
		};
		const restarted = createRuntimeBudgetController(f.options);
		const snapshot = value(restarted.open(binding));
		expect(snapshot.budget).toMatchObject({ steps_consumed: 1, cost_consumed: 1, no_progress_count: 1 });
		expect(snapshot).toMatchObject({ held_steps: 2, in_flight: 1, available_steps: 0 });
		expect(value(restarted.reserve(action("used"))).execute).toBe(false);
		refused(restarted.settle({ ...binding, reservation_id: "pending-child" }), "in-flight");
		value(restarted.settleUnknown(binding, "pending", "host/recovered-unknown"));
		value(restarted.settle({ ...binding, reservation_id: "pending-child" }));
		expect(value(restarted.snapshot(binding)).budget).toMatchObject({
			steps_consumed: 2,
			cost_consumed: 2,
			no_progress_count: 2,
		});
	});

	it("replays byte-progress dedup and globally rejects imported call-id collisions atomically", () => {
		const f = fixture({ max_steps: 5 });
		const before = [{ ref: "evidence", sha256: createHash("sha256").update("before").digest("hex") }];
		const after = [{ ref: "evidence", sha256: createHash("sha256").update("after").digest("hex") }];
		const events: RuntimeBudgetReplayEvent[] = [
			{ kind: "reserve", at: NOW - 4, request: action("a"), evidence: before },
			{ kind: "reserve", at: NOW - 3, request: action("b"), evidence: before },
			{ kind: "observe", at: NOW - 2, request: observation("a"), evidence: after },
			{ kind: "observe", at: NOW - 1, request: observation("b"), evidence: after },
		];
		if (!f.host.authority) throw new Error("fixture authority missing");
		f.host.authority.history = { kind: "verified-replay", origin_ref: "verified-start", through_ref: "head", events };
		const restored = value(f.controller.open(binding));
		expect(restored.budget).toMatchObject({ steps_consumed: 2, cost_consumed: 2, no_progress_count: 1 });
		const another = { ...binding, authorization_unit: "other-unit", parent_budget_ref: "other-budget" };
		f.host.authority = {
			...f.host.authority,
			...another,
			initial: { ...f.initial, budget_ref: another.parent_budget_ref, matter_ref: another.authorization_unit },
			history: {
				kind: "verified-replay",
				origin_ref: "other-start",
				through_ref: "other-head",
				events: [{ kind: "reserve", at: NOW - 1, request: action("a", another), evidence: [] }],
			},
		};
		refused(f.controller.open(another), "history-invalid");
		refused(f.controller.snapshot(another), "not-open");
		expect(value(f.controller.snapshot(binding))).toEqual(restored);
	});

	it.each(["missing-reserve", "future", "out-of-order", "foreign", "bad-digest"])(
		"refuses invalid replay %s without partially installing it",
		(mode) => {
			const f = fixture();
			const reserveEvent: RuntimeBudgetReplayEvent = {
				kind: "reserve",
				at: NOW - 1000,
				request: action("a"),
				evidence: [],
			};
			const observeEvent: RuntimeBudgetReplayEvent = {
				kind: "observe",
				at: NOW - 500,
				request: observation("a"),
				evidence: [],
			};
			let events: RuntimeBudgetReplayEvent[] = [reserveEvent, observeEvent];
			if (mode === "missing-reserve") events = [observeEvent];
			if (mode === "future") observeEvent.at = NOW + 1;
			if (mode === "out-of-order") observeEvent.at = NOW - 2000;
			if (mode === "foreign") observeEvent.request.parent_budget_ref = "other-parent";
			if (mode === "bad-digest") reserveEvent.evidence = [{ ref: "x", sha256: "model-says-changed" }];
			if (!f.host.authority) throw new Error("fixture authority missing");
			f.host.authority.history = { kind: "verified-replay", origin_ref: "start", through_ref: "head", events };
			refused(f.controller.open(binding), "history-invalid");
			refused(f.controller.snapshot(binding), "not-open");
		},
	);

	it("reentrant host callbacks cannot interleave mutations", () => {
		const f = fixture();
		value(f.controller.open(binding));
		f.host.capture = () => {
			refused(f.controller.reserveChild(child("reentrant")), "conflict");
			return [{ ref: "authorized/evidence.txt", bytes: readFileSync(f.target) }];
		};
		value(f.controller.reserve(action("a")));
		expect(value(f.controller.snapshot(binding))).toMatchObject({ held_steps: 1, in_flight: 1 });
	});
});

describe("runtime budget: harness/faux real tool boundaries (not production wiring)", () => {
	it("three real tools across turns/new matter wrappers succeed, fourth tool body never runs", async () => {
		const f = fixture();
		let currentBinding = { ...binding };
		value(f.controller.open(currentBinding));
		const executed: string[] = [];
		const observed: string[] = [];
		const blocked: string[] = [];
		const writeEvidence: AgentTool = {
			name: "write_evidence",
			label: "Write evidence",
			description: "Write isolated local fixture evidence",
			parameters: Type.Object({ text: Type.String() }),
			execute: async (callId, params) => {
				const input = params as { text: string };
				executed.push(callId);
				writeFileSync(f.target, input.text);
				return { content: [{ type: "text", text: "fixture write completed" }], details: {} };
			},
		};
		const harness = await createHarness({
			tools: [writeEvidence],
			extensionFactories: [
				(pi) => {
					pi.on("tool_call", async (event) => {
						const request = action(event.toolCallId, currentBinding);
						const reserved = f.controller.reserve(request);
						if (!reserved.ok || !reserved.value.execute) {
							blocked.push(event.toolCallId);
							return { block: true, reason: "fixture parent budget exhausted or duplicate" };
						}
						return undefined;
					});
					pi.on("tool_result", async (event) => {
						if (blocked.includes(event.toolCallId)) return;
						const result = value(
							f.controller.observe(
								observation(event.toolCallId, {
									...currentBinding,
									outcome: event.isError ? "error" : "success",
								}),
							),
						);
						expect(result.progress).toBe(true);
						observed.push(event.toolCallId);
					});
				},
			],
		});
		harnesses.push(harness);
		for (let turn = 1; turn <= 4; turn++) {
			currentBinding = { ...binding, matter_ref: `host-new-turn-route-card-${turn}` };
			value(f.controller.open(currentBinding));
			harness.setResponses([
				fauxAssistantMessage(
					[fauxToolCall("write_evidence", { text: `real bytes ${turn}` }, { id: `host-call-${turn}` })],
					{ stopReason: "toolUse" },
				),
				fauxAssistantMessage("round complete"),
			]);
			await harness.session.prompt(`fixture turn ${turn}`);
		}
		expect(executed).toEqual(["host-call-1", "host-call-2", "host-call-3"]);
		expect(observed).toEqual(executed);
		expect(blocked).toEqual(["host-call-4"]);
		expect(readFileSync(f.target, "utf8")).toBe("real bytes 3");
		expect(value(f.controller.snapshot(currentBinding)).budget).toMatchObject({
			steps_consumed: 3,
			cost_consumed: 3,
			no_progress_count: 0,
		});
	});
});
