/**
 * worker-store.test.ts — T-12 (AC-021, VC-027/VC-028): the queue-row
 * `origin` column and the unified owner predicate on the TS side.
 *
 * The Python reader (mw_common.parse_workers_file / worker_owner_key) and this
 * writer share one column order — `task_key | status | cli | provider |
 * task_path | dispatched_at | updated_at | model | origin` — and one predicate
 * shape: origin decides the slot, the path anchors the owner key, and the
 * `ap-` task-key prefix is never a signal on its own.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	normalizeWorkerOrigin,
	type WorkerEntry,
	WorkerStore,
	workerBelongsToKey,
	workerOrigin,
	workerOwnerKey,
} from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const tempDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "worker-store-t12-"));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function entry(over: Partial<WorkerEntry> & { taskKey: string; taskPath: string }): WorkerEntry {
	return {
		status: "running",
		cli: "pi",
		provider: "timi",
		dispatchedAt: "2026-09-26T00:00:00+00:00",
		updatedAt: "2026-09-26T00:00:00+00:00",
		model: "",
		...over,
	};
}

/** `<root>/.agenticdoc/<key>/workers/<task>/task.md` (the conductor contract). */
function keyedPath(key: string, taskKey: string): string {
	return path.join("H:", "proj", ".agenticdoc", key, "workers", taskKey, "task.md");
}

/** The 6 measured PM-hand-started `ap-` rows with no conductor origin (RQ-9
 * F1/F2: E2 L407/L413/L414/L470/L480 + FM's single `ap-` row). */
const FALSE_SIGNAL_ROWS: Array<[string, string]> = [
	["feature-sampling-human-channel", "ap-feature-sampling-human-channel-repair-a2-achieved-terminal"],
	["feature-cigate-install-kit", "ap-feature-cigate-install-kit-repair-a3-achieved-terminal"],
	["feature-gui-time-mvp-board", "ap-feature-gui-time-mvp-board-unratified-disclosure"],
	["feature-l3-verdict-source-fallback", "ap-feature-l3-verdict-source-fallback-l3-a5-recon"],
	["feature-false-meets-remediation", "ap-feature-false-meets-remediation-l3-a5-recon"],
	["gui-run-control-hitl", "ap-gui-run-control-hitl-001-contract-input-and-red-baseline"],
];

describe("worker-store origin column (T-12)", () => {
	it("normalises only the literal `conductor` cell to conductor", () => {
		expect(normalizeWorkerOrigin("conductor")).toBe("conductor");
		expect(normalizeWorkerOrigin(" conductor ")).toBe("conductor");
		expect(normalizeWorkerOrigin("CONDUCTOR")).toBe("conductor");
		expect(normalizeWorkerOrigin("manual")).toBe("manual");
		expect(normalizeWorkerOrigin("pm-manual")).toBe("manual");
		expect(normalizeWorkerOrigin("")).toBe("manual");
		expect(normalizeWorkerOrigin(undefined)).toBe("manual");
	});

	it("parses the 9-column writer line with origin last (order locked to Python)", () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		const line =
			"manual-task | running | pi | timi | " +
			"H:/proj/.agenticdoc/k/workers/manual-task/task.md | " +
			"2026-09-26T00:00:00.000Z | 2026-09-26T00:00:00.000Z | gpt-5 | manual";
		fs.writeFileSync(path.join(root, "_workers.parallel"), `${line}\n`, "utf8");
		const [row] = new WorkerStore(root).readAll();
		expect(row?.model).toBe("gpt-5");
		expect(row?.origin).toBe("manual");
		expect(workerOrigin(row as WorkerEntry)).toBe("manual");
		expect(workerOwnerKey(row as WorkerEntry)).toBe("k");
	});

	it("tolerates legacy 7/8-column rows (origin absent -> manual)", () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		fs.writeFileSync(
			path.join(root, "_workers.parallel"),
			"legacy7 | pending | pi | timi | /p/a.md | t1 | t1\n" +
				"legacy8 | pending | pi | timi | /p/b.md | t2 | t2 | my-model\n" +
				"broken | pending | pi\n",
			"utf8",
		);
		const rows = new WorkerStore(root).readAll();
		expect(rows.map((r) => r.taskKey)).toEqual(["legacy7", "legacy8"]);
		expect(rows[1]?.model).toBe("my-model");
		expect(rows.map(workerOrigin)).toEqual(["manual", "manual"]);
	});

	it("upserts with the origin column last (the store is the manual writer)", async () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		const store = new WorkerStore(root);
		await store.upsert(entry({ taskKey: "manual-task", taskPath: keyedPath("k", "manual-task") }));
		const raw = fs.readFileSync(path.join(root, "_workers.parallel"), "utf8").trim().split("\n");
		// A brand-new queue is stamped with the layout version (T-15/AC-023), so
		// the row is the file's last line.
		expect(raw[0]).toBe("# mw-queue:v2");
		const cells = raw[raw.length - 1].split(" | ");
		expect(cells).toHaveLength(9);
		expect(cells[8]).toBe("manual");
		expect(store.findByKey("manual-task")?.origin).toBe("manual");
	});
});

describe("unified owner predicate (VC-027/VC-028)", () => {
	it("origin decides the slot; the path anchors the owner key", () => {
		const conductor = entry({
			taskKey: "ap-k-writer",
			taskPath: keyedPath("k", "ap-k-writer"),
			origin: "conductor",
		});
		const manual = entry({
			taskKey: "ap-k-writer",
			taskPath: keyedPath("k", "ap-k-writer"),
			origin: "manual",
		});
		const legacy = entry({ taskKey: "ap-k-writer", taskPath: keyedPath("k", "ap-k-writer") });

		expect(workerOwnerKey(conductor)).toBe("k");
		expect(workerBelongsToKey(conductor, "k")).toBe(true);
		expect(workerBelongsToKey(conductor, "other")).toBe(false);
		expect(workerBelongsToKey(manual, "k")).toBe(false);
		// VC-028: a missing origin falls back to path for the owner key but is
		// never misjudged as a conductor row.
		expect(workerOrigin(legacy)).toBe("manual");
		expect(workerOwnerKey(legacy)).toBe("k");
		expect(workerBelongsToKey(legacy, "k")).toBe(false);
		// Outside `.agenticdoc/<key>/workers/` there is no owner key, prefix or not.
		const scratch = entry({
			taskKey: "ap-k-writer",
			taskPath: "H:/proj/.agenticdoc/_scratch/workers/ap-k-writer/task.md",
		});
		expect(workerOwnerKey(scratch)).toBe("_scratch");
		expect(workerBelongsToKey(scratch, "k")).toBe(false);
	});

	it("the 6 false-signal ap- rows are manual and hold no slot", () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		fs.writeFileSync(
			path.join(root, "_workers.parallel"),
			`${FALSE_SIGNAL_ROWS.map(
				([key, taskKey]) =>
					`${taskKey} | running | pi | timi | ${keyedPath(key, taskKey)} | ` +
					"2026-09-26T00:00:00+00:00 | 2026-09-26T00:00:00+00:00 |",
			).join("\n")}\n`,
			"utf8",
		);
		const rows = new WorkerStore(root).readAll();
		expect(rows).toHaveLength(6);
		expect(rows.every((r) => workerOrigin(r) === "manual")).toBe(true);
		expect(rows.every((r) => !workerBelongsToKey(r, workerOwnerKey(r)))).toBe(true);
		// A prefix-based implementation would have counted each of the 6 as a
		// conductor slot for the key its task key implies (the red we guard).
		expect(rows.filter((r) => r.taskKey.startsWith("ap-"))).toHaveLength(6);
		expect(rows.some((r) => workerBelongsToKey(r, "feature-gui-time-mvp-board"))).toBe(false);

		// Control: a genuine 9-column conductor row does own its key.
		const conductor = entry({
			taskKey: "ap-feature-gui-time-mvp-board-l2-a1",
			taskPath: keyedPath("feature-gui-time-mvp-board", "ap-feature-gui-time-mvp-board-l2-a1"),
			origin: "conductor",
		});
		expect(workerBelongsToKey(conductor, "feature-gui-time-mvp-board")).toBe(true);
	});
});

describe("queue integrity: unreadable rows are counted, never dropped (T-15, AC-023)", () => {
	/** The IN-3 shape: 9-column rows (`origin` last, `dispatched_at` written by
	 * the TS writer as `…Z`). Every one of these must read back as a row. */
	function nineColumnLine(i: number): string {
		return (
			`in3-task-${i} | done | pi | timi | H:/proj/.agenticdoc/k/workers/in3-task-${i}/task.md | ` +
			`2026-10-10T02:50:05.${String(200 + i).padStart(3, "0")}Z | 2026-10-10T03:20:40+00:00 | deepseek-v4.1-flash | manual`
		);
	}

	it("reads every 9-column IN-3-shaped row and reports no unreadable line", () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		const lines = [...Array(25).keys()].map(nineColumnLine);
		fs.writeFileSync(path.join(root, "_workers.parallel"), `${lines.join("\n")}\n`, "utf8");

		const queue = new WorkerStore(root).readQueue();
		expect(queue.rows).toHaveLength(25);
		expect(queue.unparsable).toEqual([]);
		expect(queue.version).toBe(1);
		expect(queue.rows[0]?.taskKey).toBe("in3-task-0");
		expect(queue.rows[24]?.origin).toBe("manual");
	});

	it("counts an unreadable line, then re-writes one row without touching it", async () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		const file = path.join(root, "_workers.parallel");
		const badLine = "ten | cols | pi | timi | /p.md | t1 | t1 | model | origin | extra";
		fs.writeFileSync(file, `${nineColumnLine(0)}\n${badLine}\n\n# a comment, not a failure\n`, "utf8");

		const store = new WorkerStore(root);
		const before = store.readQueue();
		expect(before.rows).toHaveLength(1);
		expect(before.unparsable).toEqual([{ index: 1, line: badLine, reason: "cols" }]);

		// The upsert of a *different* row must not become a silent deletion of
		// the unreadable one (the IN-3 mechanism was exactly this).
		await store.upsert(entry({ taskKey: "in3-task-9", taskPath: keyedPath("k", "in3-task-9") }));
		const raw = fs.readFileSync(file, "utf8");
		expect(raw).toContain(badLine);
		expect(raw).toContain(nineColumnLine(0));
		expect(raw.split("\n").filter((l) => l.trim() !== "")).toHaveLength(4);
		expect(store.readQueue().unparsable).toHaveLength(1);
		expect(store.readAll()).toHaveLength(2);
	});

	it("replaces a row in place and leaves the rest of the file byte-identical", async () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		const file = path.join(root, "_workers.parallel");
		const badLine = "broken | pending | pi";
		fs.writeFileSync(file, `${nineColumnLine(0)}\n${nineColumnLine(1)}\n${badLine}\n`, "utf8");

		const store = new WorkerStore(root);
		await store.upsert(entry({ taskKey: "in3-task-1", taskPath: keyedPath("k", "in3-task-1"), status: "done" }));

		const lines = fs.readFileSync(file, "utf8").trim().split("\n");
		expect(lines).toHaveLength(3);
		expect(lines[0]).toBe(nineColumnLine(0));
		expect(lines[1]?.split(" | ")[1]).toBe("done");
		expect(lines[2]).toBe(badLine);
	});

	it("reads a declared header and never adds one to an existing header-less file", async () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		const file = path.join(root, "_workers.parallel");

		// (a) new queue: stamped v2.
		const fresh = new WorkerStore(root);
		await fresh.upsert(entry({ taskKey: "in3-task-0", taskPath: keyedPath("k", "in3-task-0") }));
		expect(fs.readFileSync(file, "utf8")).toContain("# mw-queue:v2");
		expect(fresh.readQueue().version).toBe(2);

		// (b) legacy header-less file: version 1, and the file keeps its shape.
		const legacyRoot = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(legacyRoot, { recursive: true });
		fs.writeFileSync(path.join(legacyRoot, "_workers.parallel"), `${nineColumnLine(0)}\n`, "utf8");
		const legacy = new WorkerStore(legacyRoot);
		expect(legacy.readQueue().version).toBe(1);
		await legacy.upsert(entry({ taskKey: "in3-task-1", taskPath: keyedPath("k", "in3-task-1") }));
		const lines = fs.readFileSync(path.join(legacyRoot, "_workers.parallel"), "utf8").trim().split("\n");
		expect(lines[0]).toBe(nineColumnLine(0));
		expect(lines[1]).toContain("in3-task-1");
		expect(lines.some((l) => l.startsWith("#"))).toBe(false);

		// (c) an explicitly declared version is reported as-is.
		fs.writeFileSync(path.join(legacyRoot, "_workers.parallel"), `# mw-queue:v2\n${nineColumnLine(0)}\n`, "utf8");
		expect(legacy.readQueue().version).toBe(2);
	});

	it("reports the two failure reasons separately (too few cells vs empty task key)", () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		fs.writeFileSync(
			path.join(root, "_workers.parallel"),
			"too | few | cells\n | pending | pi | timi | /p.md | t1 | t1 |\n",
			"utf8",
		);
		const queue = new WorkerStore(root).readQueue();
		expect(queue.rows).toEqual([]);
		expect(queue.unparsable.map((u) => u.reason)).toEqual(["cols", "task-key"]);
	});
});

describe("IN-3 sample replay (T-21, AC-019/AC-023)", () => {
	// The incident's row shape, de-sensitised but column-faithful: 9 columns,
	// the burst second in `dispatched_at`, TS (`Z`) and Python (`+00:00`)
	// timestamps. Provenance + sha256: evidence/runs/t-21-integrity-report.md.
	const FIXTURE = fileURLToPath(
		new URL("../../../multi-workers/test/fixtures/in3-queue-9col-burst.txt", import.meta.url),
	);
	const FIXTURE_ROWS = 250;
	const FIXTURE_OWNERS = 27;
	const BURST_SECOND = "2026-10-10T02:50:05";
	const LEGACY_WORKER_COLS = 8;

	const fixtureLines = (): string[] =>
		fs
			.readFileSync(FIXTURE, "utf8")
			.split("\n")
			.filter((line) => line.trim() !== "");

	/** The codec that lost the rows: `b8bc115ff^` (`WORKER_COLS = 8`). */
	function legacyParse(line: string): string[] | undefined {
		const parts = line.split("|").map((s) => s.trim());
		if (parts.length !== LEGACY_WORKER_COLS && parts.length !== LEGACY_WORKER_COLS - 1) return undefined;
		return parts;
	}

	function withFixture(lines: string[]): { store: WorkerStore; file: string } {
		const root = path.join(mkdtemp(), ".agenticdoc");
		fs.mkdirSync(root, { recursive: true });
		const file = path.join(root, "_workers.parallel");
		fs.writeFileSync(file, `${lines.join("\n")}\n`, "utf8");
		return { store: new WorkerStore(root), file };
	}

	it("keeps the incident shape: 9 columns, one burst second, 27 owners", () => {
		const lines = fixtureLines();
		expect(lines).toHaveLength(FIXTURE_ROWS);
		const cols = lines.map((line) => line.split("|").map((s) => s.trim()));
		expect(cols.every((c) => c.length === 9)).toBe(true);
		expect(cols.every((c) => c[5].startsWith(BURST_SECOND) && c[5].endsWith("Z"))).toBe(true);
		expect(cols.every((c) => c[6].endsWith("+00:00"))).toBe(true);
		expect(cols.every((c) => c[8] === "manual")).toBe(true);
		expect(new Set(cols.map((c) => c[4].split("/")[3])).size).toBe(FIXTURE_OWNERS);
	});

	it("reads every incident row (the dispatched set can never be empty)", () => {
		const { store } = withFixture(fixtureLines());

		const queue = store.readQueue();

		expect(queue.version).toBe(1);
		expect(queue.unparsable).toEqual([]);
		expect(queue.rows).toHaveLength(FIXTURE_ROWS);
		// What `dispatchNewTasks` keys off: one readable row per task.md.
		expect(new Set(queue.rows.map((r) => r.taskKey)).size).toBe(FIXTURE_ROWS);
		expect(new Set(queue.rows.map((r) => workerOwnerKey(r))).size).toBe(FIXTURE_OWNERS);
	});

	it("the pre-fix codec drops every incident row (the mechanism, executable)", () => {
		const lines = fixtureLines();

		const readable = lines.filter((line) => legacyParse(line) !== undefined);

		expect(readable).toEqual([]);
	});

	it("also reads the legacy 8-column writer output (both codecs stay readable)", () => {
		const legacyLines = fixtureLines().map((line) => line.split("|").slice(0, 8).join(" | "));
		const { store } = withFixture(legacyLines);

		const queue = store.readQueue();

		expect(queue.rows).toHaveLength(FIXTURE_ROWS);
		expect(queue.unparsable).toEqual([]);
		expect(queue.rows.every((r) => workerOrigin(r) === "manual")).toBe(true);
	});

	it("counts a 10-column row and keeps its slot across an upsert", async () => {
		const bad = `inj-10col | pending | pi | timi | H:/proj/.agenticdoc/pk01/workers/inj/task.md | ${BURST_SECOND}.999Z | 2026-10-10T03:00:00+00:00 |  | manual | extra`;
		const { store, file } = withFixture([...fixtureLines(), bad]);

		const before = store.readQueue();
		expect(before.rows).toHaveLength(FIXTURE_ROWS);
		expect(before.unparsable.map((u) => u.reason)).toEqual(["cols"]);

		await store.upsert(entry({ taskKey: "brand-new", taskPath: keyedPath("pk01", "brand-new") }));

		const after = fs.readFileSync(file, "utf8").trimEnd().split("\n");
		expect(after).toHaveLength(FIXTURE_ROWS + 2);
		expect(after).toContain(bad);
		expect(store.readQueue().unparsable.map((u) => u.reason)).toEqual(["cols"]);
	});
});
