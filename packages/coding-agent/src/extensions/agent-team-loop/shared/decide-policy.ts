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
	const rawRow = isRecord(rawPoints) && Object.hasOwn(rawPoints, dpId) ? rawPoints[dpId] : undefined;
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
