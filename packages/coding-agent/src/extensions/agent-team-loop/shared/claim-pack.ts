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
export const CLAIM_PACK_BUDGET_SUM_DEFAULT = 8;

/** Slot target of one packed unit (`manual` = 2 slots) — the old `5 条/单元`. */
export const CLAIM_PACK_SLOTS_PER_UNIT = 5;

/** `Σ预算` / slot weight of a `manual` claim (`dispatch-card.ts:claimsGaps`). */
const CLAIM_PACK_MANUAL_WEIGHT = 2;

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

/** `C-01.3` -> `C-01` for a claim row that lost its declared parent. */
const CLAIM_PACK_CHILD_ID_RE = /^(C-\d{2,3})\.(\d+)$/i;

/** `定位` / `判据` cell separators: `;`/`,` and their full-width forms. */
const CLAIM_PACK_LOCATOR_SPLIT_RE = /[;,\s\uFF1B\uFF0C\u3001]+/u;

/** One normalized locator token: `path[:line[-line]][#fragment]`. */
const CLAIM_PACK_LOCATOR_TOKEN_RE = /^[A-Za-z0-9_][A-Za-z0-9_./-]*(?::\d+(?:-\d+)?)?(?:#[A-Za-z0-9_.:-]+)?$/;

/** One cluster of claims that must never be split across units. */
interface PackCluster {
	ids: string[];
	budgetSum: number;
	slots: number;
	hasMachineClaim: boolean;
	/** Atomicity reason; `undefined` for a free single-claim cluster. */
	atomic: "struct-atomic" | "locator" | undefined;
	/** This cluster opened a unit because the previous unit had no budget left. */
	openedByBudget: boolean;
}

/** Lower-cased self-reported type; unknown / empty types weigh 1 and are not machine. */
function packClaimType(claim: Claim): string {
	return (claim.type ?? "").trim().toLowerCase();
}

/** `Σ预算` weight: `manual` counts twice (AC-001, design §4.6 (b)). */
function packClaimWeight(claim: Claim): number {
	return packClaimType(claim) === "manual" ? CLAIM_PACK_MANUAL_WEIGHT : 1;
}

/** Slot cost: `manual` occupies two slots, every other claim one. */
function packClaimSlots(claim: Claim): number {
	return packClaimType(claim) === "manual" ? CLAIM_PACK_MANUAL_WEIGHT : 1;
}

/** `cmd` / `grep` / `struct` are the machine-checkable kinds (design §4.6 (c)). */
function packIsMachineClaim(claim: Claim): boolean {
	const type = packClaimType(claim);
	return type === "cmd" || type === "grep" || type === "struct";
}

/** Declared parent, or the `C-01` prefix of a `C-01.3` child id. */
function packParentId(claim: Claim): string {
	const declared = (claim.parent ?? "").trim();
	if (declared !== "") return declared;
	const match = CLAIM_PACK_CHILD_ID_RE.exec(claim.id ?? "");
	return match === null ? "" : (match[1] ?? "");
}

/**
 * One `path[:line][#fragment]` token -> merge key, `undefined` for a bare
 * symbol (`read`), a prose word or a non-locator artefact.
 */
function packLocatorKey(raw: string): string | undefined {
	const text = raw
		.replace(/`/g, "")
		.replace(/^[([{<"'`]+/, "")
		.replace(/[)\]}>"'`,.;:]+$/, "")
		.trim();
	if (text === "" || !CLAIM_PACK_LOCATOR_TOKEN_RE.test(text)) return undefined;
	const pathPart = text.replace(/:\d+(?:-\d+)?$/, "").replace(/#.*$/, "");
	const looksLikePath = pathPart.includes("/") || /\.[A-Za-z][A-Za-z0-9]{0,7}$/.test(pathPart);
	return looksLikePath ? text.toLowerCase() : undefined;
}

/** Locator keys of one claim: its `定位` plus the `path:line` named in `判据`. */
function packLocatorKeys(claim: Claim): string[] {
	const keys = new Set<string>();
	for (const cell of [claim.locator ?? "", claim.judgement ?? ""]) {
		if (cell === "") continue;
		for (const piece of cell.split(CLAIM_PACK_LOCATOR_SPLIT_RE)) {
			const key = packLocatorKey(piece);
			if (key !== undefined) keys.add(key);
		}
	}
	return [...keys];
}

/** Union-find `find` with path compression and a min-index root. */
function packFind(parents: number[], index: number): number {
	let root = index;
	while ((parents[root] ?? root) !== root) root = parents[root] ?? root;
	let node = index;
	while ((parents[node] ?? root) !== root) {
		const next = parents[node] ?? root;
		parents[node] = root;
		node = next;
	}
	return root;
}

/** Union by smaller index, so the cluster keeps the earliest member's position. */
function packUnion(parents: number[], left: number, right: number): void {
	const leftRoot = packFind(parents, left);
	const rightRoot = packFind(parents, right);
	if (leftRoot === rightRoot) return;
	parents[Math.max(leftRoot, rightRoot)] = Math.min(leftRoot, rightRoot);
}

/** Dedupe by id (first row wins) and fold the claim list into atomic clusters. */
function packBuildClusters(claims: Claim[], gaps: string[]): PackCluster[] {
	const unique: Claim[] = [];
	const indexById = new Map<string, number>();
	for (const claim of claims) {
		const key = (claim.id ?? "").trim().toUpperCase();
		if (key === "" || indexById.has(key)) continue;
		indexById.set(key, unique.length);
		unique.push(claim);
	}
	const parents = unique.map((_, index) => index);
	const parentLinked = unique.map(() => false);
	const locatorLinked = unique.map(() => false);
	for (let i = 0; i < unique.length; i++) {
		const parentId = packParentId(unique[i] as Claim);
		if (parentId === "") continue;
		const parentIndex = indexById.get(parentId.toUpperCase());
		parentLinked[i] = true;
		if (parentIndex === undefined) {
			// A child row without its parent row: the slice that produced this
			// input already tore the struct pair apart (RQ-2 §2.4 S-06).
			gaps.push(`split:orphan-child:${(unique[i] as Claim).id}`);
			continue;
		}
		parentLinked[parentIndex] = true;
		packUnion(parents, i, parentIndex);
	}
	const firstByLocator = new Map<string, number>();
	for (let i = 0; i < unique.length; i++) {
		for (const key of packLocatorKeys(unique[i] as Claim)) {
			const first = firstByLocator.get(key);
			if (first === undefined) {
				firstByLocator.set(key, i);
				continue;
			}
			if (first === i) continue;
			locatorLinked[i] = true;
			locatorLinked[first] = true;
			packUnion(parents, i, first);
		}
	}
	const clusters: PackCluster[] = [];
	const clusterByRoot = new Map<number, PackCluster>();
	for (let i = 0; i < unique.length; i++) {
		const claim = unique[i] as Claim;
		const root = packFind(parents, i);
		let cluster = clusterByRoot.get(root);
		if (cluster === undefined) {
			cluster = {
				ids: [],
				budgetSum: 0,
				slots: 0,
				hasMachineClaim: false,
				atomic: undefined,
				openedByBudget: false,
			};
			clusterByRoot.set(root, cluster);
			clusters.push(cluster);
		}
		cluster.ids.push(claim.id);
		cluster.budgetSum += packClaimWeight(claim);
		cluster.slots += packClaimSlots(claim);
		cluster.hasMachineClaim = cluster.hasMachineClaim || packIsMachineClaim(claim);
		if (parentLinked[i]) cluster.atomic = "struct-atomic";
		else if (locatorLinked[i] && cluster.atomic === undefined) cluster.atomic = "locator";
	}
	return clusters;
}

/** `Σ预算` of a provisional unit. */
function packGroupBudget(group: PackCluster[]): number {
	return group.reduce((sum, cluster) => sum + cluster.budgetSum, 0);
}

/** A unit is admissible under (c) only when it carries a machine claim. */
function packGroupHasMachine(group: PackCluster[]): boolean {
	return group.some((cluster) => cluster.hasMachineClaim);
}

/**
 * First cluster boundary that splits `group` into two budget-fitting units that
 * BOTH keep a machine claim; `undefined` when no boundary qualifies.
 */
function packSplitPosition(group: PackCluster[], maxBudgetSum: number): number | undefined {
	const totalBudget = packGroupBudget(group);
	const totalMachines = group.filter((cluster) => cluster.hasMachineClaim).length;
	let leftBudget = 0;
	let leftMachines = 0;
	for (let position = 1; position < group.length; position++) {
		const cluster = group[position - 1] as PackCluster;
		leftBudget += cluster.budgetSum;
		if (cluster.hasMachineClaim) leftMachines += 1;
		const rightBudget = totalBudget - leftBudget;
		const rightMachines = totalMachines - leftMachines;
		if (leftBudget > maxBudgetSum || rightBudget > maxBudgetSum) continue;
		if (leftMachines === 0 || rightMachines === 0) continue;
		return position;
	}
	return undefined;
}

/** Why a cluster sits at its final unit (priority: atomicity, budget, order). */
function packWhy(cluster: PackCluster): PackWhy {
	if (cluster.atomic === "struct-atomic") return "struct-atomic";
	if (cluster.openedByBudget) return "budget";
	if (cluster.atomic === "locator") return "locator";
	return "order";
}

/** Positive integer option or its fallback (defensive: `0`, `NaN`, `1.5`). */
function packOptionInt(value: number | undefined, fallback: number): number {
	return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : fallback;
}

/**
 * Pack one card's claims into dispatch units (design §4.6, AC-002). Pure and
 * total: the same input always yields the same result, and an empty or
 * malformed claim list yields empty `units`/`packing` instead of a throw.
 */
export function packClaims(claims: Claim[], opts: PackOptions = {}): PackResult {
	const maxBudgetSum = packOptionInt(opts?.maxBudgetSum, CLAIM_PACK_BUDGET_SUM_DEFAULT);
	const minUnits = packOptionInt(opts?.minUnits, 0);
	const gaps: string[] = [];
	const clusters = packBuildClusters(Array.isArray(claims) ? claims : [], gaps);
	if (clusters.length === 0) return { units: [], packing: [], gaps };

	// (b) + slot target: greedy in input order, never reordering (determinism).
	const groups: PackCluster[][] = [];
	let current: PackCluster[] = [];
	let currentBudget = 0;
	let currentSlots = 0;
	for (const cluster of clusters) {
		if (current.length === 0) {
			current = [cluster];
			currentBudget = cluster.budgetSum;
			currentSlots = cluster.slots;
			continue;
		}
		const fitsBudget = currentBudget + cluster.budgetSum <= maxBudgetSum;
		const fitsSlots = currentSlots + cluster.slots <= CLAIM_PACK_SLOTS_PER_UNIT;
		if (!fitsBudget || !fitsSlots) {
			cluster.openedByBudget = !fitsBudget;
			groups.push(current);
			current = [cluster];
			currentBudget = cluster.budgetSum;
			currentSlots = cluster.slots;
			continue;
		}
		current.push(cluster);
		currentBudget += cluster.budgetSum;
		currentSlots += cluster.slots;
	}
	groups.push(current);

	// (c) merge a manual-only unit into a machine neighbour whose budget allows.
	// A manual-only neighbour is never a merge target: the merge would not buy the
	// unit its missing machine claim, so the finding is reported instead.
	let index = 0;
	while (index < groups.length) {
		const group = groups[index] as PackCluster[];
		if (packGroupHasMachine(group)) {
			index += 1;
			continue;
		}
		const previous = index > 0 ? (groups[index - 1] as PackCluster[]) : undefined;
		const next = index + 1 < groups.length ? (groups[index + 1] as PackCluster[]) : undefined;
		if (
			previous !== undefined &&
			packGroupHasMachine(previous) &&
			packGroupBudget(previous) + packGroupBudget(group) <= maxBudgetSum
		) {
			previous.push(...group);
			groups.splice(index, 1);
			continue;
		}
		if (
			next !== undefined &&
			packGroupHasMachine(next) &&
			packGroupBudget(next) + packGroupBudget(group) <= maxBudgetSum
		) {
			next.unshift(...group);
			groups.splice(index, 1);
			continue;
		}
		index += 1;
	}

	// (d) unit-count floor: split at cluster boundaries until `K` is reached.
	const totalSlots = clusters.reduce((sum, cluster) => sum + cluster.slots, 0);
	const unitFloor = Math.ceil(totalSlots / CLAIM_PACK_SLOTS_PER_UNIT);
	const requiredUnits = Math.max(minUnits, unitFloor);
	while (groups.length < requiredUnits) {
		const candidates = groups
			.map((group, position) => ({ group, position }))
			.filter((entry) => entry.group.length >= 2)
			.sort((left, right) => right.group.length - left.group.length || left.position - right.position);
		let split:
			| {
					position: number;
					at: number;
			  }
			| undefined;
		for (const candidate of candidates) {
			const at = packSplitPosition(candidate.group, maxBudgetSum);
			if (at === undefined) continue;
			split = { position: candidate.position, at };
			break;
		}
		if (split === undefined) break;
		const group = groups[split.position] as PackCluster[];
		groups.splice(split.position, 1, group.slice(0, split.at), group.slice(split.at));
	}

	const units: PackUnit[] = groups.map((group, position) => {
		const unit: PackUnit = {
			k: position + 1,
			ids: [],
			budgetSum: 0,
			slots: 0,
			hasMachineClaim: false,
		};
		for (const cluster of group) {
			unit.ids.push(...cluster.ids);
			unit.budgetSum += cluster.budgetSum;
			unit.slots += cluster.slots;
			unit.hasMachineClaim = unit.hasMachineClaim || cluster.hasMachineClaim;
		}
		return unit;
	});

	const packing: PackingRow[] = [];
	for (const unit of units) {
		const group = groups[unit.k - 1] as PackCluster[];
		for (const cluster of group) {
			packing.push({ cluster: [...cluster.ids], unit: unit.k, why: packWhy(cluster) });
		}
	}

	// Unit gaps, in unit order and in detector order: over-budget first (the
	// cluster was kept whole), then manual-only, then a real count shortfall.
	for (const unit of units) {
		if (unit.budgetSum > maxBudgetSum) gaps.push(`split:unit-infeasible:${unit.k}:cluster-over-budget`);
	}
	for (const unit of units) {
		if (!unit.hasMachineClaim) gaps.push(`split:unit-infeasible:${unit.k}:manual-only`);
	}
	// A shortfall an over-width atomic cluster explains is not a defect of the
	// pack (the cluster cannot be split, `cluster-over-budget` prices it when it
	// is over budget); only the remaining missing units are reported.
	const shortfall = Math.max(0, requiredUnits - units.length);
	const atomicExcess = units.filter((unit) => {
		const group = groups[unit.k - 1] as PackCluster[];
		return group.length === 1 && unit.slots > CLAIM_PACK_SLOTS_PER_UNIT;
	}).length;
	const unexplained = Math.max(0, shortfall - atomicExcess);
	for (let k = units.length + 1; k <= units.length + unexplained; k++) {
		gaps.push(`split:unit-infeasible:${k}:below-min`);
	}

	return { units, packing, gaps };
}
