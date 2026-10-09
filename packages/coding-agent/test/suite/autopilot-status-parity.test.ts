/**
 * Autopilot key-status vocabulary cross-language parity — enum lock (T-23,
 * mw-autopilot-slot-capacity AC-010 / VC-011). Closes the QG Q-VC-011 /
 * Q-AC-010 debt left by T-08.
 *
 * T-08 added `pending-review` to BOTH sides — Python
 * (`autopilot/roadmap.py::KEY_STATUSES`, the fail-closed parser source of
 * truth) and TS (`autopilot/status-model.ts::KEY_STATUSES`, the console's
 * view-side enumeration consumed by `parseKeyStatusLine`) — but added no
 * machine lock between them. `EVENT_TYPES`, the config corpus and
 * `GATE_FRONTMATTER_FIELDS` all have cross-language locks; the enum did not.
 *
 * The judge is IDENTITY (same values in the same order), not set equality:
 * the enum is a fail-closed contract (P-021) — an out-of-order pair would
 * silently shift the meaning of every positional consumer. The Python half
 * is a real subprocess dump, never a hand-copied constant (precedent:
 * `autopilot-event-parity.test.ts`). Fail-closed like design P-016/D-013: a
 * missing interpreter, a failing subprocess, or an absent constant on either
 * side is a hard failure — deliberately no `skipIf`, which would make the
 * guard hollow.
 */

import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { KEY_STATUSES, parseRoadmapText } from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";

/** `packages/multi-workers` — the Python ground truth. */
const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

/**
 * Dump the two Python facts the lock needs: the enum in order (no `sorted`)
 * and the dependency-satisfaction set (sorted — it is a frozenset, so only
 * membership matters).
 */
const PY_DUMP_ENUMS = [
	"import json, sys",
	"sys.path.insert(0, sys.argv[1])",
	"from autopilot import conductor, roadmap",
	"print(json.dumps({",
	'    "key_statuses": list(roadmap.KEY_STATUSES),',
	'    "dep_satisfied": sorted(conductor._DEP_SATISFIED),',
	"}, ensure_ascii=False))",
].join("\n");

interface PythonEnums {
	/** `roadmap.KEY_STATUSES` in declaration order. */
	keyStatuses: string[];
	/** `conductor._DEP_SATISFIED`, sorted. */
	depSatisfied: string[];
}

function isStringArray(value: unknown): value is string[] {
	return Array.isArray(value) && value.every((entry) => typeof entry === "string");
}

/** Python half of the measurement. Fails closed with stdout+stderr. */
function pythonEnums(): PythonEnums {
	const result = spawnSync(resolveRagPython(), ["-X", "utf8", "-c", PY_DUMP_ENUMS, MULTI_WORKERS_DIR], {
		encoding: "utf8",
		timeout: 30_000,
		env: process.env,
	});
	const stdout = result.stdout ?? "";
	const stderr = result.stderr ?? "";
	if (result.error !== undefined || result.status !== 0) {
		throw new Error(`python KEY_STATUSES dump failed (status=${String(result.status)}): ${stdout}\n${stderr}`);
	}
	const parsed: unknown = JSON.parse(stdout.trim());
	if (typeof parsed !== "object" || parsed === null) {
		throw new Error(`python KEY_STATUSES dump is not an object: ${stdout}`);
	}
	const record = parsed as Record<string, unknown>;
	const keyStatuses = record.key_statuses;
	const depSatisfied = record.dep_satisfied;
	if (!isStringArray(keyStatuses)) {
		throw new Error(`python KEY_STATUSES dump has no string key_statuses: ${stdout}`);
	}
	if (!isStringArray(depSatisfied)) {
		throw new Error(`python KEY_STATUSES dump has no string dep_satisfied: ${stdout}`);
	}
	return { keyStatuses, depSatisfied };
}

/** A minimal well-formed roadmap exercising exactly one key-status line. */
function roadmapText(keyStatusLine: string): string {
	return [
		"# Roadmap",
		"> generated_at: 2026-01-01T00:00:00+00:00",
		"",
		"## Stage 1: fixture",
		"> goal: exercise the key-status validation path",
		"> status: running",
		`> key-status: ${keyStatusLine}`,
		"### Keys",
		"| key | role | depends_on |",
		"|-----|------|-----------|",
		"| k1 | fixture | - |",
		"",
	].join("\n");
}

/** Key-status validation warnings only (`parseKeyStatusLine`), not the
 * unrelated stage-status ones. */
const invalidStatusWarnings = (warnings: string[]): string[] =>
	warnings.filter((w) => w.includes("has invalid status"));

describe("autopilot key-status vocabulary parity (AC-010 / VC-011)", () => {
	it("(a) KEY_STATUSES is identical across Python and TS, order included", () => {
		const py = pythonEnums();
		const ts: string[] = [...KEY_STATUSES];
		const pySet = new Set(py.keyStatuses);
		const tsSet = new Set(ts);

		// A drained enum on either side would otherwise make every difference
		// set empty — non-emptiness is structural, not a hardcoded count.
		expect(py.keyStatuses.length, "python KEY_STATUSES is empty").toBeGreaterThan(0);
		expect(ts.length, "ts KEY_STATUSES is empty").toBeGreaterThan(0);

		// Diagnostics first: on drift, name the offending values on both sides.
		const pyOnly = py.keyStatuses.filter((name) => !tsSet.has(name));
		const tsOnly = ts.filter((name) => !pySet.has(name));
		expect(pyOnly, "python-only key statuses (TS mirror missing them)").toEqual([]);
		expect(tsOnly, "ts-only key statuses (Python vocabulary missing them)").toEqual([]);
		// The real judge: item-for-item identity in declaration order.
		expect(py.keyStatuses, "KEY_STATUSES must be identical (values AND order)").toEqual(ts);

		const equal = pyOnly.length === 0 && tsOnly.length === 0;
		const ordered = py.keyStatuses.length === ts.length && py.keyStatuses.every((v, i) => v === ts[i]);
		const depSet = new Set(py.depSatisfied);
		const subset = py.depSatisfied.every((status) => pySet.has(status));
		const pendingReviewNotDep = !depSet.has("pending-review");
		const closedLegacyDep = depSet.has("closed-legacy");
		// Every printed value is measured from the subprocess dump / the TS
		// import — no hardcoded literals (P-023). The dep facts are asserted
		// in (b); this single line is the card's consolidated [VERIFY] record.
		process.stdout.write(
			`[VERIFY] VC-011: equal=${equal} count=${ts.length} ordered=${ordered} ` +
				`dep_satisfied=${py.depSatisfied.length} pending_review_not_dep=${pendingReviewNotDep} ` +
				`closed_legacy_dep=${closedLegacyDep} subset=${subset}\n`,
		);
	});

	it("(b) Python `_DEP_SATISFIED` is a subset of KEY_STATUSES and keeps the T-08/T-07 red lines", () => {
		const py = pythonEnums();
		const keySet = new Set(py.keyStatuses);
		const depSet = new Set(py.depSatisfied);

		const notSubset = py.depSatisfied.filter((status) => !keySet.has(status));
		expect(notSubset, `_DEP_SATISFIED ⊄ KEY_STATUSES: unknown dep statuses ${notSubset.join(",")}`).toEqual([]);
		// T-08 / D-005: a deferred review is NOT a verdict — it must never unlock dependents.
		expect(depSet.has("pending-review"), "pending-review must not unlock dependencies").toBe(false);
		// T-07: a legacy-closed key is terminal and DOES unlock its dependents, like done.
		expect(depSet.has("closed-legacy"), "closed-legacy must unlock dependencies (like done)").toBe(true);
	});

	it("(c) the TS mirror is consumed by the key-status validation path (not a dead constant)", () => {
		// Accept side: every mirrored value passes the `parseKeyStatusLine`
		// closed-set check and lands in `keyStatus` verbatim.
		for (const status of KEY_STATUSES) {
			const parse = parseRoadmapText(roadmapText(`k1=${status}`));
			expect(invalidStatusWarnings(parse.warnings), `TS accepted '${status}'`).toEqual([]);
			expect(parse.stages[0]?.keyStatus.k1).toBe(status);
		}
		// Reject side: a value outside the mirror is flagged; the lenient view
		// keeps the raw value but records the warning, so a silently accepted
		// unknown value is impossible.
		for (const bogus of ["pending", "pending-review2", "bogus"]) {
			const parse = parseRoadmapText(roadmapText(`k1=${bogus}`));
			const warnings = invalidStatusWarnings(parse.warnings);
			expect(warnings, `TS rejected '${bogus}'`).toHaveLength(1);
			expect(warnings[0]).toContain(`key 'k1' has invalid status '${bogus}'`);
			expect(parse.stages[0]?.keyStatus.k1).toBe(bogus);
		}
	});
});
