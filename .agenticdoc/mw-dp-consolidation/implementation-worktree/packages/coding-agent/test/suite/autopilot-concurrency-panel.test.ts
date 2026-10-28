/**
 * Dynamic-concurrency panel — TS half (key `mw-dynamic-concurrency`, card
 * M-05-tests-ts, VC-107 + VC-108). Tests only: no production file is touched.
 *
 * VC-107 (AC-005 / AC-012): the panel must expose four quantities from ONE
 * snapshot — the config upper bound (`slotsCap`), this snapshot's dependency
 * frontier (`frontierSize`), this tick's effective concurrency
 * (`slotsEffective === min(slotsCap, frontierSize)`) and the occupied-slot
 * count (`slotsUsed`, a count of KEYS in flight, not of rows). The in-flight
 * convention is conductor-sourced (D-019 / D-106): a row holds a slot iff it is
 * NON-TERMINAL (so `pending` counts), `origin === "conductor"` and its
 * `taskPath` anchors under the key (`shared/worker-store.ts:65-70`
 * `workerBelongsToKey`). `manual` rows therefore own no slot; terminal rows own
 * none either. The renderer prints `autopilot: cap C | eff E (frontier F)`.
 *
 * VC-108 (P-021): the TS `DEFAULT_CONFIG` / `INT_RANGES` entries for the two
 * concurrency keys equal the Python frozen values field-by-field, and the
 * frozen corpus's named cases keep their verdicts (in particular
 * `range-max-parallel-low` = `max_parallel_keys: 1` is now ACCEPTED). The
 * corpus is read-only; its whole-file sha256 is deliberately NOT asserted here
 * (a re-freeze would make that brittle) — the existing P4 suite owns that.
 *
 * `frontierSize` is an over-approximation of the conductor's own `|F|` (TS does
 * not read the claim, `monitor.ts:948-953`), so the equation is asserted on the
 * panel's own `|F|`, never against a conductor count.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, describe, expect, it } from "vitest";
import { readMonitorState, renderMonitorLines } from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import {
	DEFAULT_CONFIG,
	INT_RANGES,
	validateConfigData,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";

// ── Frozen inputs (read-only) ────────────────────────────────────────────────

const CORPUS_FILE = fileURLToPath(
	new URL("../../../multi-workers/test/fixtures/autopilot-config-corpus.json", import.meta.url),
);
/** `packages/multi-workers` — Python ground truth (precedent:
 * `autopilot-config-parity.test.ts`). */
const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

interface CorpusCase {
	id: string;
	categories: string[];
	payload_text: string;
	expected: { verdict: "accept" | "reject"; error_fields: string[] };
}
interface Corpus {
	schema: string;
	cases: CorpusCase[];
}

const CORPUS = JSON.parse(fs.readFileSync(CORPUS_FILE, "utf8")) as Corpus;

/** Fail-closed lookup: a missing named case is a hard error, not a silent skip. */
function requireCase(id: string): CorpusCase {
	const testCase = CORPUS.cases.find((candidate) => candidate.id === id);
	if (testCase === undefined) throw new Error(`corpus is missing the named case '${id}'`);
	return testCase;
}

/** TS verdict for one corpus payload through the real validator. */
function tsVerdict(testCase: CorpusCase): "accept" | "reject" {
	const errors = validateConfigData(JSON.parse(testCase.payload_text));
	return errors.length === 0 ? "accept" : "reject";
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

const tmpDirs: string[] = [];
afterAll(() => {
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkroot(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mdc-m05-ts-"));
	tmpDirs.push(dir);
	return dir;
}

/** The single panel snapshot instant every fixture is read at. */
const NOW_MS = Date.parse("2026-10-14T10:00:00+00:00");

function writeConfig(root: string, cfg: Record<string, unknown>): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(path.join(dir, "config.json"), `${JSON.stringify(cfg, null, 2)}\n`, "utf8");
}

/** `_roadmap.md` in the shape `readRoadmap`/`parseRoadmapText` parse. */
function writeRoadmap(root: string, keys: Array<{ key: string; status: string; dependsOn: string[] }>): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, "_roadmap.md"),
		[
			"# Roadmap",
			"",
			"## Stage 1: work",
			"> goal: ship the frontier",
			"> status: running",
			`> key-status: ${keys.map((k) => `${k.key}=${k.status}`).join(", ")}`,
			"### Keys",
			"| key | role | depends_on |",
			"|-----|------|-----------|",
			...keys.map((k) => `| ${k.key} | worker | ${k.dependsOn.length === 0 ? "-" : k.dependsOn.join(",")} |`),
			"",
		].join("\n"),
		"utf8",
	);
}

function writeIndex(root: string, rows: Array<{ key: string; phase: string }>): void {
	const agenticdoc = path.join(root, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	const lines = rows.map((r) => `| ${r.key} | active | ${r.phase} | free | - | d | 2026-10-14T00:00:00 |`);
	fs.writeFileSync(path.join(agenticdoc, "_index.parallel"), `${lines.join("\n")}\n`, "utf8");
}

interface WorkerRow {
	taskKey: string;
	status: string;
	/** The `.agenticdoc/<ownerKey>/workers/<taskKey>/task.md` path owner. */
	ownerKey: string;
	origin: "conductor" | "manual";
}

/** `_workers.parallel` rows in the 9-column WorkerStore format
 * (`task_key | status | cli | provider | task_path | dispatched_at |
 * updated_at | model | origin`). */
function writeWorkers(root: string, rows: WorkerRow[]): void {
	const agenticdoc = path.join(root, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	const ts = "2026-10-14T00:00:00+00:00";
	const lines = rows.map(
		(r) =>
			`${r.taskKey} | ${r.status} | pi | timi | ` +
			`${path.join(agenticdoc, r.ownerKey, "workers", r.taskKey, "task.md")} | ${ts} | ${ts} |  | ${r.origin}`,
	);
	fs.writeFileSync(path.join(agenticdoc, "_workers.parallel"), `${lines.join("\n")}\n`, "utf8");
}

/** The shared roadmap: kA/kB are frontier-ready, kC waits on the still-running
 * kB (dep not satisfied), kD is terminal (dispatch-skipped) ⇒ |F| = 2. */
const ROADMAP_KEYS: Array<{ key: string; status: string; dependsOn: string[] }> = [
	{ key: "kA", status: "running", dependsOn: [] },
	{ key: "kB", status: "running", dependsOn: [] },
	{ key: "kC", status: "running", dependsOn: ["kB"] },
	{ key: "kD", status: "done", dependsOn: [] },
];

function writeBaseProject(root: string, maxParallelKeys: number): void {
	writeConfig(root, {
		enabled: true,
		paused: false,
		poll_interval_sec: 4,
		max_parallel_keys: maxParallelKeys,
		max_workers_per_key: 1,
	});
	writeRoadmap(root, ROADMAP_KEYS);
	writeIndex(root, [
		{ key: "kA", phase: "EXECUTE" },
		{ key: "kB", phase: "EXECUTE" },
		{ key: "kC", phase: "EXECUTE" },
		{ key: "kD", phase: "DONE" },
	]);
}

// ── VC-107: the panel's three quantities, one snapshot ───────────────────────

describe("VC-107 dynamic-concurrency panel (AC-005 / AC-012)", () => {
	it("recomputes cap / used / eff / frontier from one snapshot and renders all three", () => {
		const root = mkroot();
		try {
			writeBaseProject(root, 8);
			writeWorkers(root, [
				{ taskKey: "ap-kA-1", status: "running", ownerKey: "kA", origin: "conductor" },
				{ taskKey: "ap-kB-1", status: "pending", ownerKey: "kB", origin: "conductor" },
				{ taskKey: "ap-kC-1", status: "running", ownerKey: "kC", origin: "manual" },
				{ taskKey: "ap-kD-1", status: "done", ownerKey: "kD", origin: "conductor" },
			]);

			for (const cap of [8, 1]) {
				writeConfig(root, {
					enabled: true,
					paused: false,
					poll_interval_sec: 4,
					max_parallel_keys: cap,
					max_workers_per_key: 1,
				});
				const snap = readMonitorState(root, NOW_MS);
				const a = snap.autopilot;

				// One snapshot: cap from config, |F| from THIS roadmap, eff =
				// min(cap, |F|), used = number of in-flight KEYS.
				expect(a.enabled).toBe(true);
				expect(a.slotsCap).toBe(cap);
				expect(a.slotsMax).toBe(cap);
				expect(a.frontierSize).toBe(2);
				expect(a.slotsEffective).toBe(Math.min(a.slotsCap ?? -1, a.frontierSize ?? -1));
				expect(a.slotsEffective).toBe(Math.min(cap, 2));
				// kA (running/conductor) + kB (pending/conductor); kC is manual and
				// kD is terminal, so neither occupies a slot.
				expect(a.slotsUsed).toBe(2);

				const capLine = renderMonitorLines(snap).find((line) => line.startsWith("autopilot: cap "));
				expect(capLine).toBe(`autopilot: cap ${cap} | eff ${Math.min(cap, 2)} (frontier 2)`);
				expect(capLine).toContain(`cap ${cap}`);
				expect(capLine).toContain(`eff ${Math.min(cap, 2)}`);
				expect(capLine).toContain("(frontier 2)");

				process.stdout.write(
					`[VERIFY] VC-107 recompute cap=${cap} used=${a.slotsUsed} eff=${a.slotsEffective} ` +
						`frontier=${a.frontierSize} render="${capLine}"\n`,
				);
			}
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("counts slots per key: pending counts, manual does not, terminal does not, mixed key once", () => {
		// ① A `pending` conductor row already occupies its key's slot, even though
		// the running-only worker list (and therefore `inFlight`) is empty.
		const pendingRoot = mkroot();
		try {
			writeBaseProject(pendingRoot, 8);
			writeWorkers(pendingRoot, [{ taskKey: "ap-kB-1", status: "pending", ownerKey: "kB", origin: "conductor" }]);
			const pending = readMonitorState(pendingRoot, NOW_MS);
			expect(pending.workers.length).toBe(0);
			expect(pending.autopilot.keys.find((k) => k.key === "kB")?.inFlight).toBe(0);
			expect(pending.autopilot.slotsUsed).toBe(1);
			process.stdout.write(`[VERIFY] VC-107 edge=pending slotsUsed=${pending.autopilot.slotsUsed}\n`);
		} finally {
			fs.rmSync(pendingRoot, { recursive: true, force: true });
		}

		// ② A running `manual` row is visible as a worker but owns no slot.
		const manualRoot = mkroot();
		try {
			writeBaseProject(manualRoot, 8);
			writeWorkers(manualRoot, [{ taskKey: "ap-kA-1", status: "running", ownerKey: "kA", origin: "manual" }]);
			const manual = readMonitorState(manualRoot, NOW_MS);
			expect(manual.workers.length).toBe(1);
			expect(manual.autopilot.keys.find((k) => k.key === "kA")?.inFlight).toBe(0);
			expect(manual.autopilot.slotsUsed).toBe(0);
			process.stdout.write(`[VERIFY] VC-107 edge=manual slotsUsed=${manual.autopilot.slotsUsed}\n`);
		} finally {
			fs.rmSync(manualRoot, { recursive: true, force: true });
		}

		// ③ Terminal rows (`done` / `failed`) free their keys.
		const terminalRoot = mkroot();
		try {
			writeBaseProject(terminalRoot, 8);
			writeWorkers(terminalRoot, [
				{ taskKey: "ap-kA-1", status: "done", ownerKey: "kA", origin: "conductor" },
				{ taskKey: "ap-kB-1", status: "failed", ownerKey: "kB", origin: "conductor" },
			]);
			const terminal = readMonitorState(terminalRoot, NOW_MS).autopilot;
			expect(terminal.slotsUsed).toBe(0);
			process.stdout.write(`[VERIFY] VC-107 edge=terminal slotsUsed=${terminal.slotsUsed}\n`);
		} finally {
			fs.rmSync(terminalRoot, { recursive: true, force: true });
		}

		// ④ One key with a manual row and TWO conductor rows counts once; a second
		// key with a conductor row counts once more ⇒ 2 keys, never 4 rows.
		const mixedRoot = mkroot();
		try {
			writeBaseProject(mixedRoot, 8);
			writeWorkers(mixedRoot, [
				{ taskKey: "ap-kA-run", status: "running", ownerKey: "kA", origin: "conductor" },
				{ taskKey: "ap-kA-pend", status: "pending", ownerKey: "kA", origin: "conductor" },
				{ taskKey: "ap-kA-manual", status: "running", ownerKey: "kA", origin: "manual" },
				{ taskKey: "ap-kB-pend", status: "pending", ownerKey: "kB", origin: "conductor" },
			]);
			const mixed = readMonitorState(mixedRoot, NOW_MS).autopilot;
			expect(mixed.slotsUsed).toBe(2);
			process.stdout.write(`[VERIFY] VC-107 edge=mixed slotsUsed=${mixed.slotsUsed}\n`);
		} finally {
			fs.rmSync(mixedRoot, { recursive: true, force: true });
		}
	});
});

// ── VC-108: two-side parity, field-by-field ──────────────────────────────────

const PY_VALUES_SCRIPT = [
	"import json, sys",
	"sys.path.insert(0, sys.argv[1])",
	"from autopilot import config",
	"print('MDC_M05_JSON_BEGIN')",
	"print(json.dumps({",
	"    'max_parallel_keys_default': config.DEFAULT_CONFIG['max_parallel_keys'],",
	"    'max_workers_per_key_default': config.DEFAULT_CONFIG['max_workers_per_key'],",
	"    'max_parallel_keys_range': list(config._INT_RANGES['max_parallel_keys']),",
	"    'max_workers_per_key_range': list(config._INT_RANGES['max_workers_per_key']),",
	"}))",
	"print('MDC_M05_JSON_END')",
].join("\n");

interface PyConcurrencyValues {
	max_parallel_keys_default: number;
	max_workers_per_key_default: number;
	max_parallel_keys_range: Array<number | null>;
	max_workers_per_key_range: Array<number | null>;
}

/** Dump the two concurrency keys from the real Python module. Fail-closed: a
 * missing interpreter or a bad exit throws with stderr. */
function pythonConcurrencyValues(): PyConcurrencyValues {
	const result = spawnSync(resolveRagPython(), ["-c", PY_VALUES_SCRIPT, MULTI_WORKERS_DIR], {
		encoding: "utf8",
		timeout: 30_000,
		env: process.env,
	});
	const stdout = result.stdout ?? "";
	const stderr = result.stderr ?? "";
	const begin = stdout.indexOf("MDC_M05_JSON_BEGIN");
	const end = stdout.indexOf("MDC_M05_JSON_END");
	if (result.status !== 0 || begin < 0 || end < 0) {
		throw new Error(`python concurrency-values dump failed (status=${String(result.status)}): ${stdout}\n${stderr}`);
	}
	return JSON.parse(stdout.slice(begin + "MDC_M05_JSON_BEGIN".length, end).trim()) as PyConcurrencyValues;
}

describe("VC-108 two-side concurrency parity (P-021)", () => {
	it("TS defaults and ranges equal the Python frozen values field-by-field", () => {
		const py = pythonConcurrencyValues();

		// The Python frozen literals themselves (config.py:91-92 / :127-128),
		// asserted so a coordinated two-side drift cannot hide behind the
		// differential comparison below.
		expect(py.max_parallel_keys_default).toBe(8);
		expect(py.max_workers_per_key_default).toBe(4);
		expect(py.max_parallel_keys_range).toEqual([1, null]);
		expect(py.max_workers_per_key_range).toEqual([1, null]);

		// TS == Python, field by field.
		expect(DEFAULT_CONFIG.max_parallel_keys).toBe(py.max_parallel_keys_default);
		expect(DEFAULT_CONFIG.max_workers_per_key).toBe(py.max_workers_per_key_default);
		expect(INT_RANGES.max_parallel_keys).toEqual(py.max_parallel_keys_range);
		expect(INT_RANGES.max_workers_per_key).toEqual(py.max_workers_per_key_range);

		process.stdout.write(
			`[VERIFY] VC-108 field=max_parallel_keys ts_default=${DEFAULT_CONFIG.max_parallel_keys} ` +
				`py_default=${py.max_parallel_keys_default} ts_range=${JSON.stringify(INT_RANGES.max_parallel_keys)} ` +
				`py_range=${JSON.stringify(py.max_parallel_keys_range)}\n`,
		);
		process.stdout.write(
			`[VERIFY] VC-108 field=max_workers_per_key ts_default=${DEFAULT_CONFIG.max_workers_per_key} ` +
				`py_default=${py.max_workers_per_key_default} ts_range=${JSON.stringify(INT_RANGES.max_workers_per_key)} ` +
				`py_range=${JSON.stringify(py.max_workers_per_key_range)}\n`,
		);
	});

	it("corpus named cases keep their frozen verdicts under the TS validator", () => {
		// `max_parallel_keys: 1` is the load-bearing widening: it MUST be accepted
		// now (the floor moved 2 -> 1), and its payload is unchanged.
		const low = requireCase("range-max-parallel-low");
		expect(JSON.parse(low.payload_text)).toEqual({ max_parallel_keys: 1 });
		expect(tsVerdict(low)).toBe("accept");
		expect(low.expected.verdict).toBe("accept");

		const min = requireCase("range-max-parallel-min");
		expect(JSON.parse(min.payload_text)).toEqual({ max_parallel_keys: 2 });
		expect(tsVerdict(min)).toBe("accept");
		expect(min.expected.verdict).toBe("accept");

		// The new key's partial-file case.
		const perKey = requireCase("partial-key-max_workers_per_key");
		expect(JSON.parse(perKey.payload_text)).toEqual({ max_workers_per_key: 4 });
		expect(tsVerdict(perKey)).toBe("accept");
		expect(perKey.expected.verdict).toBe("accept");

		// Negative control: the floor itself still rejects 0, so the accepts above
		// are not a validator that accepts anything.
		const belowFloor = requireCase("range-max-parallel-below-floor");
		expect(JSON.parse(belowFloor.payload_text)).toEqual({ max_parallel_keys: 0 });
		expect(tsVerdict(belowFloor)).toBe("reject");
		expect(belowFloor.expected.verdict).toBe("reject");
		expect(validateConfigData(JSON.parse(belowFloor.payload_text)).join("; ")).toContain("max_parallel_keys");

		process.stdout.write(
			"[VERIFY] VC-108 corpus range-max-parallel-low=accept range-max-parallel-min=accept " +
				"partial-key-max_workers_per_key=accept range-max-parallel-below-floor=reject\n",
		);
	});
});
