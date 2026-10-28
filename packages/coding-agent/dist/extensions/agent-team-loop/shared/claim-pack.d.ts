/**
 * claim-pack.ts — claim-cluster packing of one card's claims (T-04, AC-002).
 *
 * The split unit is NOT "5 claims": RQ-2 §4.6 measured that a `struct` parent
 * plus its children occupies N+1 slots, so 16/29 (55.2%) of the corpus units are
 * torn apart by any fixed-width slice, `manual` density is a function of n, and
 * 17.2% of the `struct` claims can only be enumerated at runtime. The unit is a
 * BIN PACK of atomic claim clusters:
 *
 * - (a) cluster atomicity: a `C-01.3` child stays with its `C-01` parent, and
 *   claims that name a shared `定位` token stay together (one verdict cannot be
 *   read without the other's evidence);
 * - (b) `Σ预算` per unit (a `manual` claim counts 2) stays within
 *   {@link CLAIM_PACK_BUDGET_SUM_DEFAULT};
 * - (c) every unit carries at least one machine-checkable claim
 *   (`cmd`/`grep`/`struct`); a manual-only unit is merged into a machine
 *   neighbour, and reported as `split:unit-infeasible:<k>:manual-only` when the
 *   merge would break (b);
 * - (d) `K = ceil(Σslots / 5)` (`manual` = 2 slots) is a LOWER bound of the unit
 *   count. Packing targets {@link CLAIM_PACK_SLOTS_PER_UNIT} slots per unit, so
 *   the bound holds unless an atomic cluster is wider than the target. The
 *   shortfall an over-width atomic cluster explains is not reported; anything
 *   else is `split:unit-infeasible:<k>:below-min`.
 *
 * An atomic cluster that is over budget on its own is still emitted as one unit
 * (a claim is never dropped) and flagged
 * `split:unit-infeasible:<k>:cluster-over-budget`.
 *
 * Contract: pure — no filesystem, no clock, no randomness. Input order in, the
 * same order out; the same `claims` always yield the same `units`/`packing`.
 * Never throws (P-048).
 */
import type { Claim } from "./dispatch-card.ts";
/** `Σ预算` cap of one packed unit (`manual` counted twice, design §4.6 (b)). */
export declare const CLAIM_PACK_BUDGET_SUM_DEFAULT = 8;
/** Slot target of one packed unit (`manual` = 2 slots) — the old `5 条/单元`. */
export declare const CLAIM_PACK_SLOTS_PER_UNIT = 5;
/** Why one cluster sits where it sits in the pack. */
export type PackWhy = "struct-atomic" | "budget" | "locator" | "order";
/** Options of {@link packClaims}; every field is optional and defensive. */
export interface PackOptions {
    /** `Σ预算` ceiling of one unit; default {@link CLAIM_PACK_BUDGET_SUM_DEFAULT}. */
    maxBudgetSum?: number;
    /** Extra unit-count floor on top of `K = ceil(Σslots / 5)`. */
    minUnits?: number;
}
/** One packed dispatch unit. `k` is 1-based (the `split:*` detail index). */
export interface PackUnit {
    k: number;
    ids: string[];
    budgetSum: number;
    slots: number;
    hasMachineClaim: boolean;
}
/** One cluster -> unit mapping row; `cluster` holds the claim ids it covers. */
export interface PackingRow {
    cluster: string[];
    unit: number;
    why: PackWhy;
}
/** Result of {@link packClaims}. `packing` covers every claim exactly once. */
export interface PackResult {
    units: PackUnit[];
    packing: PackingRow[];
    gaps: string[];
}
/**
 * Pack one card's claims into dispatch units (design §4.6, AC-002). Pure and
 * total: the same input always yields the same result, and an empty or
 * malformed claim list yields empty `units`/`packing` instead of a throw.
 */
export declare function packClaims(claims: Claim[], opts?: PackOptions): PackResult;
//# sourceMappingURL=claim-pack.d.ts.map