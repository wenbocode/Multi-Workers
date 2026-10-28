/**
 * Autopilot event vocabulary cross-language parity — D3 guard (T-02,
 * design D-003/design-consumption-record F4, AC-010/AC-021/AC-022, VC-012).
 *
 * The Python side (`autopilot/timeline.py::EVENT_TYPES`) is the source of
 * truth for the timeline vocabulary; the TS side
 * (`autopilot/status-model.ts::EVENT_TYPES`) mirrors it as the console's
 * default include-set (`nonBeatFilter()`, `console.ts cmdTimeline`). A name
 * present on one side only is silently swallowed by the default view — the
 * exact drift D3 records for `target-config-rejected`.
 *
 * The judge is SET EQUALITY, not count equality: both difference sets must be
 * empty. The Python half is a real subprocess dump, never a hand-copied
 * constant (precedent: `autopilot-config-parity.test.ts`). Fail-closed like
 * design P-016/D-013: a missing interpreter, a failing subprocess, or an
 * absent constant on either side is a hard failure — deliberately no
 * `skipIf`, which would make the guard hollow.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
	EVENT_TYPES,
	nonBeatFilter,
	queryTimeline,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";

/** `packages/multi-workers` — the Python ground truth. */
const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

/** Event names pre-admitted by T-02; producers land in T-07/T-08. */
const NEW_EVENT_TYPES = [
	"gate-auto-decision",
	"gate-auto-revoke",
	"review-decided",
	"review-escalated",
	"evidence-reconciliation",
	"stage-reopen-refused",
];

const PY_DUMP_EVENT_TYPES = [
	"import json, sys",
	"sys.path.insert(0, sys.argv[1])",
	"from autopilot import timeline",
	"print(json.dumps(sorted(timeline.EVENT_TYPES), ensure_ascii=False))",
].join("\n");

/** Python half of the measurement. Fails closed with stdout+stderr. */
function pythonEventTypes(): string[] {
	const result = spawnSync(resolveRagPython(), ["-X", "utf8", "-c", PY_DUMP_EVENT_TYPES, MULTI_WORKERS_DIR], {
		encoding: "utf8",
		timeout: 30_000,
		env: process.env,
	});
	const stdout = result.stdout ?? "";
	const stderr = result.stderr ?? "";
	if (result.error !== undefined || result.status !== 0) {
		throw new Error(`python EVENT_TYPES dump failed (status=${String(result.status)}): ${stdout}\n${stderr}`);
	}
	const parsed: unknown = JSON.parse(stdout.trim());
	if (!Array.isArray(parsed) || parsed.some((entry) => typeof entry !== "string")) {
		throw new Error(`python EVENT_TYPES dump is not a string array: ${stdout}`);
	}
	return parsed;
}

describe("autopilot event vocabulary parity (AC-010 / AC-021 / AC-022, VC-012)", () => {
	it("EVENT_TYPES is set-equal across Python and TS (both difference sets empty)", () => {
		const py = pythonEventTypes();
		const ts = [...EVENT_TYPES];
		const pySet = new Set(py);
		const tsSet = new Set(ts);

		const pyOnly = py.filter((name) => !tsSet.has(name)).sort();
		const tsOnly = ts.filter((name) => !pySet.has(name)).sort();
		expect(pyOnly, "python-only event types (TS mirror missing them)").toEqual([]);
		expect(tsOnly, "ts-only event types (Python vocabulary missing them)").toEqual([]);
		// Belt and braces: the sorted arrays compare equal as sets too.
		expect([...ts].sort()).toEqual([...py].sort());
		// Cardinality is recorded, never the judge (design VC-012: "set equality,
		// not count") — a future task adding a name on BOTH sides must not have
		// to edit a magic number here.
		process.stdout.write(`[VERIFY] VC-012: equal=true count=${ts.length}\n`);
	});

	it("pre-admits every T-02 event name on both sides and in the default view", () => {
		const py = new Set(pythonEventTypes());
		for (const name of [...NEW_EVENT_TYPES, "target-config-rejected"]) {
			expect(EVENT_TYPES.has(name), `ts EVENT_TYPES missing ${name}`).toBe(true);
			expect(py.has(name), `python EVENT_TYPES missing ${name}`).toBe(true);
			expect(nonBeatFilter().has(name), `${name} hidden by nonBeatFilter()`).toBe(true);
		}
	});

	it("admits the optional `data` payload while the rest of the whitelist stays closed", () => {
		const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ap-evparity-"));
		try {
			const file = path.join(dir, "timeline.jsonl");
			fs.writeFileSync(
				file,
				`${JSON.stringify({
					ts: "2026-01-01T00:00:00+00:00",
					seq: 1,
					ev: "gate-auto-decision",
					key: "key-a",
					stage: 1,
					detail: "auto approve",
					data: { decision_id: "d-1", decision: "approve" },
					extra: "dropped",
				})}\n`,
				"utf8",
			);
			const event = queryTimeline(file, 0).events[0];
			expect(event).toBeDefined();
			expect(event.data).toEqual({ decision_id: "d-1", decision: "approve" });
			// The whitelist is not opened up: an unknown sibling key stays out.
			expect(Object.keys(event)).not.toContain("extra");
		} finally {
			fs.rmSync(dir, { recursive: true, force: true });
		}
	});
});
