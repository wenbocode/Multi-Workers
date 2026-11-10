/**
 * Per-dp policy resolution (spec §14 AC-016, design D-048..D-051).
 *
 * One authority chain, mirrored byte-for-byte with
 * `packages/multi-workers/decision_points.py::resolve_policy`:
 *
 *   per-dp row in `.mw/decide-points.json`
 *     > declared keys of `.mw/decide.json`
 *       > built-in defaults (0.7 / 8 / 20)
 *
 * Lives in `shared/` (not `pm/`) because BOTH consumers need it: the worker
 * (`worker/worker-mode.ts`, dp3 thresholds) and the PM
 * (`pm/pm-orchestrator.ts`, dp2 gate). A `pm/` home would make the worker
 * extension import the PM layer, which the module layout forbids.
 *
 * Fail-soft by contract (AC-016): an illegal value is dropped with a
 * `problems` entry and the resolver falls through to the next layer. Nothing
 * here throws, and a missing/unreadable file is simply an empty layer.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { DECIDE_REGISTRY, DECIDE_REGISTRY_RETIRED, type DecideRegistryField } from "./decide-registry.generated.ts";

import { currentClaimId } from "./implementation-gate.ts";
import { IndexStore, keyNameRefusal, normalizeKey } from "./index-store.ts";
import { agenticdocRoot } from "./paths.ts";

/** The three knobs of AC-016. Order is frozen (parity with Python). */
export const DECIDE_POLICY_KEYS = ["min_confidence", "max_questions", "timeout_s"] as const;

export type DecidePolicyKey = (typeof DECIDE_POLICY_KEYS)[number];

/** Built-in (last-resort) layer — the values that were hard-coded in TS. */
export const DECIDE_POLICY_BUILTIN: Readonly<Record<DecidePolicyKey, number>> = {
	min_confidence: 0.7,
	max_questions: 8,
	timeout_s: 20,
};

/** Per-dp row domain (`POLICY_ROW_BOUNDS` in `decision_points.py`). */
export const DECIDE_POLICY_ROW_BOUNDS: Readonly<Record<DecidePolicyKey, readonly [number, number]>> = {
	min_confidence: [0, 1],
	max_questions: [1, 8],
	timeout_s: [1, 300],
};

/** Which layer decided an effective value (audit / `dp check` parity). */
export type DecidePolicyOrigin = "row" | "decide.json" | "builtin";

/** Effective per-dp policy plus the provenance `mw decide dp check` prints. */
export interface ResolvedDecidePolicy {
	minConfidence: number;
	maxQuestions: number;
	timeoutS: number;
	origins: Record<DecidePolicyKey, DecidePolicyOrigin>;
	/** One line per dropped value, e.g. `L8: min_confidence 1.5 is outside [0, 1]`. */
	problems: string[];
	/** Where the two files were read from (diagnostics only). */
	pointsPath: string;
	decidePath: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readJsonRecord(file: string): Record<string, unknown> | undefined {
	try {
		const parsed: unknown = JSON.parse(fs.readFileSync(file, "utf8"));
		return isRecord(parsed) ? parsed : undefined;
	} catch {
		return undefined;
	}
}

/** `JSON number -> number`; booleans are NOT numbers (Python `_policy_number`). */
function policyNumber(value: unknown): number | undefined {
	return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** Validate one knob; `{ value }` or `{ problem }` — never throws. */
export function coerceDecidePolicyValue(
	key: DecidePolicyKey,
	value: unknown,
	perDp: boolean,
): { value: number; problem?: undefined } | { problem: string; value?: undefined } {
	const number = policyNumber(value);
	if (number === undefined) return { problem: `must be a number, got ${JSON.stringify(value)}` };
	if (key === "min_confidence") {
		const [low, high] = perDp ? DECIDE_POLICY_ROW_BOUNDS.min_confidence : [0, 1];
		if (!(low <= number && number <= high)) return { problem: `${number} is outside [${low}, ${high}]` };
		return { value: number };
	}
	if (!Number.isInteger(number)) return { problem: `must be an integer, got ${JSON.stringify(value)}` };
	if (perDp) {
		const [low, high] = DECIDE_POLICY_ROW_BOUNDS[key];
		if (!(low <= number && number <= high)) return { problem: `${number} is outside [${low}, ${high}]` };
	} else if (number < 1) {
		return { problem: `must be >= 1, got ${number}` };
	}
	return { value: number };
}

/** One layer's value for one key.
 *
 * `exists`-based declaration check mirrors Python: a present row key always
 * speaks (an illegal value becomes an L8 problem), while `.mw/decide.json`
 * treats `null` as "not declared" (`if raw.get(key) is None: continue`). */
function layerValue(
	layer: Record<string, unknown> | undefined,
	key: DecidePolicyKey,
	perDp: boolean,
	problems: string[],
	nullIsUndeclared: boolean,
): number | undefined {
	if (layer === undefined || !Object.hasOwn(layer, key)) return undefined;
	const raw = layer[key];
	if (nullIsUndeclared && (raw === null || raw === undefined)) return undefined;
	const parsed = coerceDecidePolicyValue(key, raw, perDp);
	if (parsed.problem !== undefined) {
		problems.push(`L8: ${key} ${parsed.problem}; effective value falls back to the next layer`);
		return undefined;
	}
	return parsed.value;
}

/**
 * Resolve the effective per-dp policy for `dpId` under `projectDir`.
 *
 * The row layer is the raw `.mw/decide-points.json` `points[dpId]` object: a
 * missing row or a non-object row contributes nothing (Python keeps such a row
 * `enabled=false` / unparsed, and its policy fields are unset either way). The
 * global layer is the *declared* keys of `.mw/decide.json` — a dataclass default
 * is not a declaration, so an unset file never masks the built-in layer.
 */
export function resolveDecidePolicy(dpId: string, projectDir: string): ResolvedDecidePolicy {
	const pointsPath = path.join(projectDir, ".mw", "decide-points.json");
	const decidePath = path.join(projectDir, ".mw", "decide.json");
	const points = readJsonRecord(pointsPath);
	const rawPoints = points?.points;
	const rawRow =
		!decisionIdRefusal(dpId) && isRecord(rawPoints) && Object.hasOwn(rawPoints, dpId) ? rawPoints[dpId] : undefined;
	const row = isRecord(rawRow) ? rawRow : undefined;
	const globals = readJsonRecord(decidePath);

	const problems: string[] = [];
	const origins = {} as Record<DecidePolicyKey, DecidePolicyOrigin>;
	const effective = {} as Record<DecidePolicyKey, number>;
	for (const key of DECIDE_POLICY_KEYS) {
		const rowValue = layerValue(row, key, true, problems, false);
		if (rowValue !== undefined) {
			effective[key] = rowValue;
			origins[key] = "row";
			continue;
		}
		const globalValue = layerValue(globals, key, false, problems, true);
		if (globalValue !== undefined) {
			effective[key] = globalValue;
			origins[key] = "decide.json";
			continue;
		}
		effective[key] = DECIDE_POLICY_BUILTIN[key];
		origins[key] = "builtin";
	}
	return {
		minConfidence: effective.min_confidence,
		maxQuestions: effective.max_questions,
		timeoutS: effective.timeout_s,
		origins,
		problems,
		pointsPath,
		decidePath,
	};
}

export interface PreparedBasis {
	id: string;
	text: string;
	material_refs: string[];
	applies_to: string[];
}

export interface DecisionPreparation {
	prepared_at: string;
	basis_catalog: PreparedBasis[];
}

export interface MaterialIssue {
	field: string;
	rule: string;
}

export type MaterialValidation =
	| { ok: true; material: Record<string, unknown> }
	| { ok: false; issues: MaterialIssue[] };

export function decisionIdRefusal(dp: string): string | undefined {
	if (Object.hasOwn(DECIDE_REGISTRY, dp)) return undefined;
	return DECIDE_REGISTRY_RETIRED.some((item) => item.id === dp) ? "retired" : "unknown-dp";
}

export function decisionActorAllowed(dp: string, role: unknown): boolean {
	if (decisionIdRefusal(dp)) return false;
	return DECIDE_REGISTRY[dp].roleScope === "pm"
		? role === "pm"
		: role === "coding" || role === "research" || role === "review";
}

function nonblank(value: unknown): value is string {
	return typeof value === "string" && value.trim() !== "";
}

function fieldValue(material: Record<string, unknown>, path: string): unknown {
	let value: unknown = material;
	for (const name of path.split(".")) {
		if (!isRecord(value) || !Object.hasOwn(value, name)) return undefined;
		value = value[name];
	}
	return value;
}

function validField(field: DecideRegistryField, value: unknown): boolean {
	switch (field.type) {
		case "string":
			return (
				nonblank(value) &&
				(field.maxBytes === undefined || Buffer.byteLength(value) <= field.maxBytes) &&
				(field.enum === undefined || field.enum.includes(value))
			);
		case "array":
			return (
				Array.isArray(value) &&
				(field.maxItems === undefined || value.length <= field.maxItems) &&
				value.every((item) =>
					field.itemType === "object"
						? isRecord(item)
						: nonblank(item) &&
							(field.itemMaxBytes === undefined || Buffer.byteLength(item) <= field.itemMaxBytes),
				)
			);
		case "boolean":
			return typeof value === "boolean";
		case "object":
			return isRecord(value);
		case "integer":
			return typeof value === "number" && Number.isSafeInteger(value);
		case "number":
			return typeof value === "number" && Number.isFinite(value);
	}
}

export function validateDecisionMaterial(dp: string, material: unknown): MaterialValidation {
	if (decisionIdRefusal(dp))
		return { ok: false, issues: [{ field: "dp", rule: "requires an active decision point" }] };
	if (!isRecord(material)) return { ok: false, issues: [{ field: "material", rule: "must be an object" }] };
	const entry = DECIDE_REGISTRY[dp];
	const paths = entry.modelStateFields ?? [];
	const issues: MaterialIssue[] = [];
	function checkKeys(parent: Record<string, unknown>, prefix: string): void {
		for (const [key, value] of Object.entries(parent)) {
			const path = prefix + key;
			if (!key.includes(".") && paths.includes(path)) continue;
			if (!key.includes(".") && paths.some((allowed) => allowed.startsWith(`${path}.`)) && isRecord(value)) {
				checkKeys(value, `${path}.`);
			} else {
				issues.push({ field: path, rule: "not a declared material field or container" });
			}
		}
	}
	checkKeys(material, "");
	for (const field of [...entry.requiredStateFields, ...entry.optionalStateFields]) {
		const value = fieldValue(material, field.name);
		if (value === undefined && entry.optionalStateFields.includes(field)) continue;
		if (!validField(field, value)) issues.push({ field: field.name, rule: "missing or invalid field" });
	}
	if (entry.kind === "dynamic-candidates" && Array.isArray(material.handling_options)) {
		const candidates = material.handling_options;
		if (candidates.length < 2)
			issues.push({ field: "handling_options", rule: "at least two distinguishable candidates" });
		const keys = ["id", "label", "description", "consequence", "risk", "conditions"];
		const ids = new Set<string>();
		const labels = new Set<string>();
		for (const [i, item] of candidates.entries()) {
			const field = `handling_options[${i}]`;
			if (!isRecord(item)) {
				issues.push({ field, rule: "must be a candidate object" });
				continue;
			}
			for (const name of Object.keys(item)) {
				if (!keys.includes(name)) issues.push({ field: `${field}.${name}`, rule: "unknown candidate field" });
			}
			for (const key of keys)
				if (!nonblank(item[key])) issues.push({ field: `${field}.${key}`, rule: "must be nonblank" });
			if (nonblank(item.id)) {
				if (ids.has(item.id)) issues.push({ field: `${field}.id`, rule: "duplicate candidate id" });
				ids.add(item.id);
			}
			if (nonblank(item.label)) {
				if (labels.has(item.label) || /[\r\n]/.test(item.label) || [...item.label].length > 80)
					issues.push({
						field: `${field}.label`,
						rule: "requires a distinct single-line label of at most 80 characters",
					});
				labels.add(item.label);
			}
		}
	}
	return issues.length ? { ok: false, issues } : { ok: true, material };
}

function decisionChoices(dp: string, material: Record<string, unknown>): readonly string[] {
	const entry = DECIDE_REGISTRY[dp];
	if (entry.kind !== "dynamic-candidates") return entry.fixedChoiceIds;
	return Array.isArray(material.handling_options)
		? material.handling_options.flatMap((item) => (isRecord(item) && nonblank(item.id) ? [item.id] : []))
		: [];
}

export function preparationProblems(
	dp: string,
	material: Record<string, unknown>,
	preparation: unknown,
	context: unknown,
): string[] {
	const entry = DECIDE_REGISTRY[dp];
	const problems: string[] = [];
	if (context !== undefined) {
		if (!isRecord(context)) problems.push("context");
		else
			for (const [name, value] of Object.entries(context)) {
				if (
					!entry.contextSlots.includes(name) ||
					(value !== null && (typeof value !== "string" || [...value].length > 1500))
				)
					problems.push(`context.${name}`);
			}
	}
	if (!isRecord(preparation)) return [...problems, "preparation"];
	if (Object.keys(preparation).some((key) => !entry.preparation.keys.includes(key))) problems.push("preparation");
	const time = preparation.prepared_at;
	if (!nonblank(time) || !/^\d{4}-\d\d-\d\dT.+(?:Z|[+-]\d\d:\d\d)$/.test(time) || !Number.isFinite(Date.parse(time)))
		problems.push("preparation.prepared_at");
	const catalog = preparation.basis_catalog;
	if (!Array.isArray(catalog) || !catalog.length) return [...problems, "preparation.basis_catalog"];
	const ids = new Set<string>();
	const choices = decisionChoices(dp, material);
	for (const [i, item] of catalog.entries()) {
		const path = `preparation.basis_catalog[${i}]`;
		if (!isRecord(item)) {
			problems.push(path);
			continue;
		}
		if (Object.keys(item).some((key) => !entry.preparation.basisItemKeys.includes(key))) problems.push(path);
		if (!nonblank(item.id) || ids.has(item.id)) problems.push(`${path}.id`);
		else ids.add(item.id);
		if (!nonblank(item.text)) problems.push(`${path}.text`);
		if (
			!Array.isArray(item.material_refs) ||
			!item.material_refs.length ||
			!item.material_refs.every(
				(ref) =>
					nonblank(ref) &&
					fieldValue(material, ref) !== undefined &&
					(Object.hasOwn(material, ref) || entry.modelStateFields?.includes(ref)),
			)
		)
			problems.push(`${path}.material_refs`);
		if (
			!Array.isArray(item.applies_to) ||
			!item.applies_to.length ||
			!item.applies_to.every((target) => nonblank(target) && choices.includes(target))
		)
			problems.push(`${path}.applies_to`);
	}
	return problems;
}

export function selectedDecisionBasis(
	dp: string,
	material: Record<string, unknown>,
	prep: DecisionPreparation,
	choice: unknown,
	basisId: unknown,
): PreparedBasis | undefined {
	if (!nonblank(choice) || !decisionChoices(dp, material).includes(choice)) return undefined;
	if (
		dp === "dp-w-check-task" &&
		choice === "investigate" &&
		DECIDE_REGISTRY[dp].optionalStateFields.some((field) => !nonblank(fieldValue(material, field.name)))
	)
		return undefined;
	if (
		dp === "dp-QG" &&
		((choice === "pass" && material.basis_issue !== undefined) ||
			(choice === "reopen" && !nonblank(material.basis_issue)))
	)
		return undefined;
	return prep.basis_catalog.find((item) => item.id === basisId && item.applies_to.includes(choice));
}

/** Resolve only an unambiguous live claim of this PM process, on every call. */
export function claimedPmKey(projectDir: string, requested?: string): string | undefined {
	try {
		const self = currentClaimId();
		const rows = new IndexStore(agenticdocRoot(projectDir)).readAll();
		const eligible = rows.filter(
			(row) =>
				row.status === "active" &&
				row.claimId === self &&
				(requested === undefined || normalizeKey(requested) === normalizeKey(row.key)),
		);
		if (eligible.length !== 1) return undefined;
		const key = eligible[0].key;
		if (keyNameRefusal(key) || rows.filter((row) => normalizeKey(row.key) === normalizeKey(key)).length !== 1)
			return undefined;
		return key;
	} catch {
		return undefined;
	}
}
