/**
 * claim-pack.test.ts — claim-cluster packing (T-04, AC-002, key
 * `claim-driven-review-orchestration`).
 *
 * Locks the pure `packClaims` contract of `shared/claim-pack.ts` (design §4.6):
 * cluster atomicity (struct parent + children, shared `定位` token), the
 * `Σ预算 ≤ 8` ceiling, the "at least one machine-checkable claim" rule, the
 * `K = ceil(Σslots / 5)` unit floor, the `split:orphan-child:<id>` /
 * `split:unit-infeasible:<k>:<rule>` gap shapes, and determinism.
 *
 * Fixtures are inline literals: no corpus counts, no project files, no clock.
 */

import { describe, expect, it } from "vitest";
import {
	CLAIM_PACK_BUDGET_SUM_DEFAULT,
	CLAIM_PACK_SLOTS_PER_UNIT,
	type PackResult,
	packClaims,
} from "../../src/extensions/agent-team-loop/shared/claim-pack.ts";
import type { Claim } from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";

/** One claim row; `locator` is unique per id unless the test overrides it. */
function fixture(id: string, type: string, extra: Partial<Claim> = {}): Claim {
	return {
		id,
		type,
		parent: "",
		statement: `${id} statement`,
		falsifier: `${id} falsifier`,
		locator: `src/${id.toLowerCase().replace(/\./g, "-")}.ts:1`,
		judgement: `${type === "struct" ? "shape" : type}: ${id} judged`,
		budget: 1,
		row: 1,
		...extra,
	};
}

/** `n` grep claims `C-01..C-0n`, each with its own locator. */
function greps(n: number): Claim[] {
	return Array.from({ length: n }, (_, index) => fixture(`C-${String(index + 1).padStart(2, "0")}`, "grep"));
}

/** A struct parent plus six child rows, `manualChildren` of them `manual`. */
function structCluster(manualChildren: number): Claim[] {
	const children = Array.from({ length: 6 }, (_, index) => {
		const id = `C-01.${index + 1}`;
		return fixture(id, index < manualChildren ? "manual" : "struct", { parent: "C-01" });
	});
	return [fixture("C-01", "struct"), ...children];
}

/** The unit index that carries `id`; fails the test when the claim was dropped. */
function unitOf(result: PackResult, id: string): number {
	const unit = result.units.find((candidate) => candidate.ids.includes(id));
	if (unit === undefined) throw new Error(`claim ${id} is not packed`);
	return unit.k;
}

/** Every claim id of `packing`, in packing order. */
function packedIds(result: PackResult): string[] {
	return result.packing.flatMap((row) => row.cluster);
}

describe("packClaims", () => {
	it("① packs 5 grep claims into one unit (Σ预算 5 ≤ 8)", () => {
		const claims = greps(5);
		const result = packClaims(claims);

		expect(result.units).toHaveLength(1);
		const unit = result.units[0]!;
		expect(unit.k).toBe(1);
		expect(unit.ids).toEqual(["C-01", "C-02", "C-03", "C-04", "C-05"]);
		expect(unit.budgetSum).toBe(5);
		expect(unit.slots).toBe(5);
		expect(unit.hasMachineClaim).toBe(true);
		expect(result.gaps).toEqual([]);
		expect(result.packing.map((row) => row.why)).toEqual(["order", "order", "order", "order", "order"]);
	});

	it("② splits 10 grep claims into 2 units, each Σ预算 ≤ 8", () => {
		const result = packClaims(greps(10));

		expect(result.units.map((unit) => unit.k)).toEqual([1, 2]);
		expect(result.units.map((unit) => unit.ids.length)).toEqual([5, 5]);
		for (const unit of result.units) {
			expect(unit.budgetSum).toBeLessThanOrEqual(CLAIM_PACK_BUDGET_SUM_DEFAULT);
			expect(unit.hasMachineClaim).toBe(true);
		}
		expect(result.gaps).toEqual([]);
	});

	it("③ keeps a struct parent with its 6 children and reports only cluster-over-budget", () => {
		// 5 machine rows + 2 manual children = 9 预算 on one atomic cluster.
		const claims = structCluster(2);
		const result = packClaims(claims);

		expect(result.units).toHaveLength(1);
		const unit = result.units[0]!;
		expect(unit.ids).toEqual(["C-01", "C-01.1", "C-01.2", "C-01.3", "C-01.4", "C-01.5", "C-01.6"]);
		expect(unit.budgetSum).toBe(9);
		expect(unit.hasMachineClaim).toBe(true);
		expect(result.gaps).toEqual(["split:unit-infeasible:1:cluster-over-budget"]);
		expect(result.packing).toHaveLength(1);
		expect(result.packing[0]!.why).toBe("struct-atomic");
		expect(result.packing[0]!.cluster).toEqual(unit.ids);
	});

	it("④ merges a manual-only unit into the adjacent machine unit", () => {
		const claims = [
			fixture("C-01", "manual"),
			fixture("C-02", "manual"),
			fixture("C-03", "manual"),
			fixture("C-04", "grep"),
			fixture("C-05", "grep"),
		];
		const result = packClaims(claims);

		// The two leading manual claims form no unit of their own any more.
		expect(result.gaps).toEqual([]);
		expect(unitOf(result, "C-01")).toBe(unitOf(result, "C-04"));
		expect(unitOf(result, "C-02")).toBe(unitOf(result, "C-03"));
		for (const unit of result.units) expect(unit.hasMachineClaim).toBe(true);
		// Σslots = 3 manual × 2 + 2 = 8 ⇒ K = 2, so the floor is still met.
		expect(result.units.length).toBeGreaterThanOrEqual(Math.ceil(8 / CLAIM_PACK_SLOTS_PER_UNIT));
		expect(packedIds(result)).toHaveLength(claims.length);
	});

	it("⑤ reports manual-only units when every claim is manual", () => {
		const claims = ["C-01", "C-02", "C-03", "C-04"].map((id) => fixture(id, "manual"));
		const result = packClaims(claims);

		expect(result.units.length).toBeGreaterThanOrEqual(2);
		for (const unit of result.units) expect(unit.hasMachineClaim).toBe(false);
		expect(result.gaps).toContain("split:unit-infeasible:1:manual-only");
		expect(packedIds(result)).toHaveLength(4);
	});

	it("⑥ uses K = ceil(Σslots / 5) as the floor and tops units up to it", () => {
		// 6 grep claims: Σbudget 6 fits one unit, but K = 2 keeps the density bound.
		const six = packClaims(greps(6));
		expect(Math.ceil(6 / CLAIM_PACK_SLOTS_PER_UNIT)).toBe(2);
		expect(six.units).toHaveLength(2);
		expect(six.units.map((unit) => unit.ids.length)).toEqual([5, 1]);
		expect(six.gaps).toEqual([]);

		// An explicit floor above K splits further, still without dropping claims.
		const three = packClaims(greps(6), { minUnits: 3 });
		expect(three.units).toHaveLength(3);
		expect(three.units.flatMap((unit) => unit.ids)).toEqual(six.units.flatMap((unit) => unit.ids));
		for (const unit of three.units) expect(unit.hasMachineClaim).toBe(true);
		expect(three.gaps).toEqual([]);

		// 3 manual + 1 grep collapses into one machine unit whose only split
		// boundary is manual-only ⇒ the K = 2 floor is genuinely unreachable.
		const infeasible = packClaims([
			fixture("C-01", "manual"),
			fixture("C-02", "manual"),
			fixture("C-03", "manual"),
			fixture("C-04", "grep"),
		]);
		expect(infeasible.units).toHaveLength(1);
		expect(infeasible.units[0]!.slots).toBe(7);
		expect(infeasible.gaps).toContain("split:unit-infeasible:2:below-min");
	});

	it("⑦ is deterministic and never mutates its input", () => {
		const claims = [...structCluster(1), ...greps(4), fixture("C-09", "manual")];
		const before = JSON.stringify(claims);
		const first = packClaims(claims);
		const second = packClaims(claims);
		const copy = packClaims(claims.map((claim) => ({ ...claim })));

		expect(second).toEqual(first);
		expect(copy).toEqual(first);
		expect(JSON.stringify(claims)).toBe(before);
	});

	it("⑧ lists every claim exactly once in packing, mapped to its unit", () => {
		const claims = [
			...structCluster(1),
			fixture("C-05", "grep", { locator: "src/shared.ts:10" }),
			fixture("C-06", "grep", { locator: "src/shared.ts:10" }),
			fixture("C-07", "manual"),
			fixture("C-08", "cmd", { locator: "evidence/claims/x.md#C-08" }),
		];
		const result = packClaims(claims);
		const ids = packedIds(result);

		expect(ids).toHaveLength(claims.length);
		expect(new Set(ids).size).toBe(claims.length);
		expect([...ids].sort()).toEqual(claims.map((claim) => claim.id).sort());
		expect(result.units.flatMap((unit) => unit.ids)).toEqual(ids);
		for (const row of result.packing) {
			for (const id of row.cluster) expect(unitOf(result, id)).toBe(row.unit);
		}
	});

	it("⑨ reports an orphan struct child instead of dropping it", () => {
		const claims = [
			fixture("C-01", "struct"),
			fixture("C-02.1", "struct", { parent: "C-02" }),
			fixture("C-03", "grep"),
		];
		const result = packClaims(claims);

		expect(result.gaps).toContain("split:orphan-child:C-02.1");
		expect(packedIds(result)).toEqual(["C-01", "C-02.1", "C-03"]);
	});

	it("⑩ keeps claims that share a 定位 token in the same unit", () => {
		const claims = [
			fixture("C-01", "grep", { locator: "src/shared.ts:10" }),
			fixture("C-02", "grep"),
			fixture("C-03", "grep"),
			fixture("C-04", "grep"),
			fixture("C-05", "grep"),
			fixture("C-06", "grep", { locator: "src/shared.ts:10" }),
		];
		const result = packClaims(claims);
		const row = result.packing.find((candidate) => candidate.cluster.includes("C-01"));

		expect(unitOf(result, "C-01")).toBe(unitOf(result, "C-06"));
		expect(row?.cluster).toEqual(["C-01", "C-06"]);
		expect(row?.why).toBe("locator");
		expect(result.units.flatMap((unit) => unit.ids)).toHaveLength(claims.length);
	});

	it("tolerates an empty claim list", () => {
		expect(packClaims([])).toEqual({ units: [], packing: [], gaps: [] });
	});
});
