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
import { type IndexEntry, IndexStore, keyNameRefusal, normalizeKey } from "./index-store.ts";
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

/** Read-only pre-transport availability facts from the SAME two config files
 *  `resolveDecidePolicy` already owns. Only EXPLICIT declarations become known
 *  facts; an absent/ambiguous/unreadable value stays `unknown` so Python keeps
 *  the authorization verdict (D-036). This is not a new config source and never
 *  writes a live switch. `unconfigured` means the transport file is missing
 *  (`decision.py:DecisionConfig.from_project`); a corrupt file is `unknown`.
 *  `signoffDisabled` is a business exemption, never a service fault. */
/** Current effective per-dp mode fact from the SAME points row. Python's
 *  `_parse_row` starts at the registry default (`default_mode`, "auto" for
 *  every active entry), accepts only `auto|suggest` as a declared value and
 *  force-disables the row on an illegal declaration (L3). A missing table is
 *  that default; a corrupt/unreadable table or a non-object row stays `unknown`
 *  under the existing reader-error contract (Python keeps the verdict). This
 *  is a cache-invalidation fact, never a permission or budget grant. */
export type DecideModeFact = "auto" | "suggest" | "invalid" | "unknown";

export interface DecideConfigFacts {
	transport: "on" | "off" | "unconfigured" | "unknown";
	dpDisabled: boolean;
	signoffDisabled: boolean;
	/** Current effective per-dp mode from the real row reader. */
	mode: DecideModeFact;
	/** Relative config paths actually consulted (L0 evidence refs). */
	configRefs: string[];
}

export const DECIDE_CONFIG_REFS = {
	points: ".mw/decide-points.json",
	decide: ".mw/decide.json",
} as const;

/** Real per-dp row validity from the SAME points row reader. Mirrors Python
 *  `_parse_row` force_off (`decision_points.py`): an illegally declared
 *  enabled (non-bool), mode (not auto|suggest) or note/tier (non-string)
 *  closes the row. Policy numbers are deliberately NOT here: an illegal
 *  value only falls back through `resolveDecidePolicy` and never closes the
 *  dp. A missing table / non-object row is owned by the caller's reader-error
 *  contract, never turned into a trusted auto or a known off fact here. */
function rowForcesOff(row: Record<string, unknown>): boolean {
	if (Object.hasOwn(row, "enabled") && typeof row.enabled !== "boolean") return true;
	if (Object.hasOwn(row, "mode") && row.mode !== "auto" && row.mode !== "suggest") return true;
	if (Object.hasOwn(row, "note") && typeof row.note !== "string") return true;
	if (Object.hasOwn(row, "tier") && typeof row.tier !== "string") return true;
	return false;
}

/** This P0 entry defaults off. Only an explicit, valid enabled row can route
 * a pending gate to automated handling. The handler owns the policy verdict. */
export function gateApprovalRow(projectDir: string): "on" | "off" | "unreadable" {
	const file = path.join(projectDir, DECIDE_CONFIG_REFS.points);
	let config: unknown;
	try {
		config = JSON.parse(fs.readFileSync(file, "utf8"));
	} catch (err) {
		return (err as NodeJS.ErrnoException).code === "ENOENT" ? "off" : "unreadable";
	}
	if (!isRecord(config) || !isRecord(config.points)) return "unreadable";
	const row = config.points["dp-gate-approve"];
	if (row === undefined) return "off";
	if (!isRecord(row) || rowForcesOff(row)) return "unreadable";
	return row.enabled === true ? "on" : "off";
}

export function readDecideConfigFacts(dpId: string, projectDir: string): DecideConfigFacts {
	const pointsPath = path.join(projectDir, DECIDE_CONFIG_REFS.points);
	const decidePath = path.join(projectDir, DECIDE_CONFIG_REFS.decide);
	const points = readJsonRecord(pointsPath);
	const rawPoints = points?.points;
	const row =
		!decisionIdRefusal(dpId) && isRecord(rawPoints) && Object.hasOwn(rawPoints, dpId) ? rawPoints[dpId] : undefined;
	// A non-object row is NOT a known off fact here: Python's layered row
	// validation owns it, so the child keeps its say. The effective off fact
	// also covers the SAME row's force_off declarations (illegal enabled/mode/
	// note/tier), so a non-bool enabled invalidates the matter cache and closes
	// the dp instead of replaying a cached success.
	const dpDisabled = isRecord(row) && (row.enabled === false || rowForcesOff(row));
	let mode: DecideModeFact = "auto";
	if (points === undefined && fs.existsSync(pointsPath)) mode = "unknown";
	else if (isRecord(rawPoints) && Object.hasOwn(rawPoints, dpId) && !isRecord(row)) mode = "unknown";
	else if (isRecord(row) && Object.hasOwn(row, "mode")) {
		const declared = row.mode;
		mode = declared === "auto" || declared === "suggest" ? declared : "invalid";
	}
	const decide = readJsonRecord(decidePath);
	let transport: DecideConfigFacts["transport"] = "unknown";
	if (decide === undefined) transport = fs.existsSync(decidePath) ? "unknown" : "unconfigured";
	else if (decide.enabled === false) transport = "off";
	else if (decide.enabled === true) transport = "on";
	return {
		transport,
		dpDisabled,
		signoffDisabled: decide?.signoff === "disable",
		mode,
		configRefs: [DECIDE_CONFIG_REFS.points, DECIDE_CONFIG_REFS.decide],
	};
}

export interface PreparedBasis {
	id: string;
	text: string;
	material_refs: string[];
	applies_to: string[];
	finding_ids?: string[];
	remaining_ids?: string[];
}

export interface DecisionPreparation {
	prepared_at: string;
	basis_catalog: PreparedBasis[];
	model_context?: Record<string, unknown>;
}

export interface MaterialIssue {
	field: string;
	rule: string;
	/** Only `missing` means the field was absent; supplied invalid values keep
	 * their actual constraint failure. Counts never include submitted text. */
	code?: "missing" | "type" | "blank" | "max-bytes" | "max-items" | "enum" | "unknown-field";
	allowed_choices?: readonly string[];
	received_choice?: string;
	actual?: number;
	limit?: number;
}

/** Local reference diagnosis; field names only, never submitted material values. */
export interface MaterialReferenceIssue extends MaterialIssue {
	allowed_fields: string[];
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

function fieldIssue(field: DecideRegistryField, value: unknown): MaterialIssue | undefined {
	if (value === undefined) return { field: field.name, code: "missing", rule: "required field is absent" };
	switch (field.type) {
		case "string":
			if (typeof value !== "string") break;
			if (!value.trim()) return { field: field.name, code: "blank", rule: "must be a nonblank string" };
			if (field.maxBytes !== undefined && Buffer.byteLength(value) > field.maxBytes)
				return {
					field: field.name,
					code: "max-bytes",
					rule: "exceeds the declared UTF-8 bytes limit",
					actual: Buffer.byteLength(value),
					limit: field.maxBytes,
				};
			if (field.enum !== undefined && !field.enum.includes(value))
				return { field: field.name, code: "enum", rule: "must be one of the declared choices" };
			return undefined;
		case "array":
			if (!Array.isArray(value)) break;
			if (field.maxItems !== undefined && value.length > field.maxItems)
				return {
					field: field.name,
					code: "max-items",
					rule: "exceeds the declared array item limit",
					actual: value.length,
					limit: field.maxItems,
				};
			for (const [index, item] of value.entries()) {
				// Match the existing Array.every semantics for non-JSON sparse input.
				if (!(index in value)) continue;
				const name = `${field.name}[${index}]`;
				if (field.itemType === "object") {
					if (!isRecord(item)) return { field: name, code: "type", rule: "must be an object" };
				} else {
					if (typeof item !== "string") return { field: name, code: "type", rule: "must be a string" };
					if (!item.trim()) return { field: name, code: "blank", rule: "must be a nonblank string" };
					if (field.itemMaxBytes !== undefined && Buffer.byteLength(item) > field.itemMaxBytes)
						return {
							field: name,
							code: "max-bytes",
							rule: "exceeds the declared UTF-8 bytes limit",
							actual: Buffer.byteLength(item),
							limit: field.itemMaxBytes,
						};
				}
			}
			return undefined;
		case "boolean":
			if (typeof value === "boolean") return undefined;
			break;
		case "object":
			if (isRecord(value)) return undefined;
			break;
		case "integer":
			if (typeof value === "number" && Number.isSafeInteger(value)) return undefined;
			break;
		case "number":
			if (typeof value === "number" && Number.isFinite(value)) return undefined;
	}
	return { field: field.name, code: "type", rule: `must be a ${field.type}` };
}

export function validateDecisionMaterial(dp: string, material: unknown): MaterialValidation {
	if (decisionIdRefusal(dp))
		return { ok: false, issues: [{ field: "dp", rule: "requires an active decision point" }] };
	if (!isRecord(material))
		return {
			ok: false,
			issues: [{ field: "material", code: material === undefined ? "missing" : "type", rule: "must be an object" }],
		};
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
				issues.push({
					field: prefix.slice(0, -1) || "material",
					code: "unknown-field",
					rule: "contains a field or container not declared by this entry",
				});
			}
		}
	}
	checkKeys(material, "");
	for (const field of [...entry.requiredStateFields, ...entry.optionalStateFields]) {
		const value = fieldValue(material, field.name);
		if (value === undefined && entry.optionalStateFields.includes(field)) continue;
		const issue = fieldIssue(field, value);
		if (issue !== undefined) issues.push(issue);
	}
	if (entry.kind === "dynamic-candidates" && Array.isArray(material.handling_options)) {
		const candidates = material.handling_options;
		if (candidates.length < 2)
			issues.push({ field: "handling_options", rule: "at least two distinguishable candidates" });
		const keys = ["id", "label", "description", "consequence", "risk", "conditions"];
		const ids = new Set<string>();
		const labels = new Set<string>();
		const paths = new Map<string, number>();
		for (const [i, item] of candidates.entries()) {
			const field = `handling_options[${i}]`;
			if (!isRecord(item)) {
				issues.push({ field, rule: "must be a candidate object" });
				continue;
			}
			for (const name of Object.keys(item)) {
				if (!keys.includes(name))
					issues.push({ field, code: "unknown-field", rule: "contains an unknown candidate field" });
			}
			for (const key of keys)
				if (!nonblank(item[key])) issues.push({ field: `${field}.${key}`, rule: "must be nonblank" });
			const content = keys.slice(2).map((key) => item[key]);
			if (content.every(nonblank)) {
				const path = JSON.stringify(
					content.map((value) =>
						value
							.trim()
							.replace(/[ \t\r\n]+/g, " ")
							.toLowerCase(),
					),
				);
				const previous = paths.get(path);
				if (previous === undefined) paths.set(path, i);
				else
					issues.push({
						field,
						rule: `duplicates the action, consequence, risk and conditions of handling_options[${previous}]`,
					});
			}
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

export function decisionChoices(dp: string, material: Record<string, unknown>): readonly string[] {
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
	materialRefIssues?: MaterialReferenceIssue[],
	choiceIssues?: MaterialIssue[],
): string[] {
	const entry = DECIDE_REGISTRY[dp];
	const problems: string[] = [];
	const referenceIssue = (field: string, rule: string): void => {
		materialRefIssues?.push({
			field,
			rule,
			allowed_fields: [...new Set([...Object.keys(material), ...(entry.modelStateFields ?? [])])].filter(
				(ref) => fieldValue(material, ref) !== undefined,
			),
		});
	};
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
	if (Object.keys(preparation).some((key) => key !== "model_context" && !entry.preparation.keys.includes(key)))
		problems.push("preparation");
	const time = preparation.prepared_at;
	if (!nonblank(time) || !/^\d{4}-\d\d-\d\dT.+(?:Z|[+-]\d\d:\d\d)$/.test(time) || !Number.isFinite(Date.parse(time)))
		problems.push("preparation.prepared_at");
	const catalog = preparation.basis_catalog;
	if (!Array.isArray(catalog) || !catalog.length) return [...problems, "preparation.basis_catalog"];
	const ids = new Set<string>();
	const choices = decisionChoices(dp, material);
	const covered = new Set<string>();
	for (const [i, item] of catalog.entries()) {
		const path = `preparation.basis_catalog[${i}]`;
		if (!isRecord(item)) {
			problems.push(path);
			continue;
		}
		if (
			Object.keys(item).some(
				(key) => key !== "finding_ids" && key !== "remaining_ids" && !entry.preparation.basisItemKeys.includes(key),
			)
		)
			problems.push(path);
		for (const field of ["finding_ids", "remaining_ids"] as const) {
			const values = item[field];
			if (
				values !== undefined &&
				(!Array.isArray(values) ||
					values.length > 32 ||
					values.some((id) => typeof id !== "string" || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(id)) ||
					new Set(values).size !== values.length)
			)
				problems.push(`${path}.${field}`);
		}
		if (!nonblank(item.id) || ids.has(item.id)) problems.push(`${path}.id`);
		else ids.add(item.id);
		if (!nonblank(item.text)) problems.push(`${path}.text`);
		if (
			!Array.isArray(item.material_refs) ||
			!item.material_refs.length ||
			!item.material_refs.every((ref, index) => {
				const valid =
					nonblank(ref) &&
					fieldValue(material, ref) !== undefined &&
					(Object.hasOwn(material, ref) || entry.modelStateFields?.includes(ref));
				if (!valid)
					referenceIssue(
						`${path}.material_refs[${index}]`,
						"must be a non-empty string referencing an existing field path in this material, without the material. prefix; " +
							"repository file path:line belongs in evidence field values, not material_refs",
					);
				return valid;
			})
		) {
			problems.push(`${path}.material_refs`);
			if (!Array.isArray(item.material_refs) || !item.material_refs.length)
				referenceIssue(
					`${path}.material_refs`,
					"must be a non-empty array of field paths in this material, without the material. prefix; " +
						"repository file path:line belongs in evidence field values, not material_refs",
				);
		}
		const targets = item.applies_to;
		const field = `${path}.applies_to`;
		if (!Array.isArray(targets) || !targets.length) {
			problems.push(field);
			choiceIssues?.push({
				field,
				code: targets === undefined ? "missing" : Array.isArray(targets) ? "blank" : "type",
				rule: "expected a nonempty array of choice IDs",
				allowed_choices: choices,
			});
		} else {
			for (const [index, target] of targets.entries()) {
				if (nonblank(target) && choices.includes(target)) {
					covered.add(target);
					continue;
				}
				const member = `${field}[${index}]`;
				problems.push(member);
				choiceIssues?.push({
					field: member,
					code: typeof target === "string" ? "enum" : "type",
					rule: "expected a choice ID for this decision point",
					allowed_choices: choices,
					...(typeof target === "string" && /^[A-Za-z][A-Za-z0-9-]{0,63}$/.test(target) && !/^sk-/i.test(target)
						? { received_choice: target }
						: {}),
				});
			}
		}
	}
	if (dp === "dp-QG") {
		const reasons = isRecord(preparation.model_context) ? preparation.model_context.reasons : undefined;
		if (isRecord(reasons) && Object.keys(reasons).length === 0) covered.add("fix");
		const missing = choices.filter((choice) => !covered.has(choice));
		if (missing.length) {
			const field = "preparation.basis_catalog";
			problems.push(field);
			choiceIssues?.push({
				field,
				code: "missing",
				rule: `missing prepared criteria for ${missing.join(", ")}`,
				allowed_choices: choices,
			});
		}
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

/** Stable machine reason for one PM claim inspection. `ok` means a unique,
 *  valid, self-owned active claim resolved; every other value is the exact
 *  failing observation from the SAME single readAll/evaluate pass that produced
 *  `key === undefined`. The two index-level reasons deliberately do NOT claim a
 *  precision the reader cannot have: readAll drops malformed lines and maps a
 *  missing file to `[]`, so missing / empty / all-lines-malformed are
 *  indistinguishable (index-empty-or-unparseable, explicitly unknown) and a
 *  thrown read can only be reported as unreadable, never as "no claim". */
export type PmClaimReason =
	| "ok"
	| "index-unreadable"
	| "index-empty-or-unparseable"
	| "invalid-key"
	| "ambiguous-claim"
	| "key-not-found"
	| "key-inactive"
	| "foreign-owner"
	| "no-active-claim";

export interface PmClaimInspection {
	/** The resolved key — byte-for-byte the value the legacy claimedPmKey returns. */
	key: string | undefined;
	/** Why `key` resolved (ok) or the exact observation behind undefined. */
	reason: PmClaimReason;
}

/** Label a failed eligible-set evaluation using ONLY the same rows snapshot.
 *  This NEVER re-reads the index and NEVER re-runs the authorization verdict —
 *  the verdict is already fixed as undefined at every call site; the observations
 *  below only name a stable reason for the local refusal diagnosis. */
function classifyIneligibleClaim(
	rows: readonly IndexEntry[],
	self: string,
	requested: string | undefined,
	eligibleCount: number,
): PmClaimReason {
	if (eligibleCount > 1) return "ambiguous-claim";
	if (rows.length === 0) return "index-empty-or-unparseable";
	const scoped =
		requested === undefined ? rows : rows.filter((row) => normalizeKey(requested) === normalizeKey(row.key));
	if (requested !== undefined && scoped.length === 0) return "key-not-found";
	if (requested === undefined) return "no-active-claim";
	if (scoped.some((row) => row.status === "active" && row.claimId !== self)) return "foreign-owner";
	if (scoped.some((row) => row.status !== "active")) return "key-inactive";
	return "no-active-claim";
}

/** Resolve the live claim AND its reason from ONE IndexStore.readAll snapshot.
 *  This is the single authority: claimedPmKey delegates to it (value-equal),
 *  and the PM decision tool reads `.reason` for the refusal diagnosis. The
 *  filter, normalizeKey, exact `===` claimId comparison, keyNameRefusal and the
 *  duplicate-key-row count are the original predicate, unchanged — only the
 *  return shape is richer. */
export function inspectPmClaim(projectDir: string, requested?: string): PmClaimInspection {
	try {
		const self = currentClaimId();
		const rows = new IndexStore(agenticdocRoot(projectDir)).readAll();
		const eligible = rows.filter(
			(row) =>
				row.status === "active" &&
				row.claimId === self &&
				(requested === undefined || normalizeKey(requested) === normalizeKey(row.key)),
		);
		if (eligible.length !== 1)
			return { key: undefined, reason: classifyIneligibleClaim(rows, self, requested, eligible.length) };
		const key = eligible[0].key;
		if (keyNameRefusal(key)) return { key: undefined, reason: "invalid-key" };
		if (rows.filter((row) => normalizeKey(row.key) === normalizeKey(key)).length !== 1)
			return { key: undefined, reason: "ambiguous-claim" };
		return { key, reason: "ok" };
	} catch {
		return { key: undefined, reason: "index-unreadable" };
	}
}

/** Resolve only an unambiguous live claim of this PM process, on every call.
 *  Value-compatible wrapper over inspectPmClaim: every input returns exactly
 *  the string/undefined the legacy predicate returned (all four existing
 *  consumers and canPmSelectType keep their `=== key` behavior). */
export function claimedPmKey(projectDir: string, requested?: string): string | undefined {
	return inspectPmClaim(projectDir, requested).key;
}
