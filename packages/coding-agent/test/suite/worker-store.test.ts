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
		const raw = fs.readFileSync(path.join(root, "_workers.parallel"), "utf8").trim();
		expect(raw.split(" | ")).toHaveLength(9);
		expect(raw.split(" | ")[8]).toBe("manual");
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
