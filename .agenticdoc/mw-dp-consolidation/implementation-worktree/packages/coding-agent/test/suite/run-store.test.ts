/**
 * run-store.test.ts — T-20 (AC-022/D-022/D-023): the product-carried run
 * identity.
 *
 * IN-3 made the ledger the single source of "did this run?" — so a rebuilt
 * ledger silently re-ran 252 tasks and a re-run overwrote a finished task's
 * output.md. The fix is a run record written by the worker itself
 * (`workers/<task>/run.json`) that the dispatcher must read before queueing.
 * These tests cover the store in isolation; the launcher half lives in
 * packages/multi-workers (TestReconcileRunState) and the dispatch wiring in
 * worker-dispatch-guard.test.ts.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	collectArtifacts,
	evaluateRunIdentity,
	isTerminalRunStatus,
	newRunId,
	parseSupersedes,
	RUN_SCHEMA,
	type RunState,
	readRunState,
	runMarker,
	runStateKind,
	writeRunState,
} from "../../src/extensions/agent-team-loop/shared/run-store.ts";

const tempDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-run-store-"));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function state(taskDir: string, overrides: Partial<RunState> = {}): RunState {
	return {
		schema: RUN_SCHEMA,
		task_key: path.basename(taskDir),
		run_id: `${path.basename(taskDir)}@2026-10-10T02:00:00.000Z`,
		owner_key: "k",
		kind: "coding",
		status: "running",
		started_at: "2026-10-10T02:00:00.000Z",
		artifacts: [],
		...overrides,
	};
}

function writeTask(taskDir: string, content: string): void {
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), content, "utf8");
}

describe("run-store: read is 'no information', never a guess (AC-022)", () => {
	it("returns undefined for every unreadable record", () => {
		const dir = mkdtemp();
		expect(readRunState(dir)).toBeUndefined(); // missing file

		fs.writeFileSync(path.join(dir, "run.json"), "{ not json\n", "utf8");
		expect(readRunState(dir)).toBeUndefined(); // bad JSON

		fs.writeFileSync(path.join(dir, "run.json"), "[1,2,3]\n", "utf8");
		expect(readRunState(dir)).toBeUndefined(); // non-object root

		fs.writeFileSync(path.join(dir, "run.json"), `${JSON.stringify({ task_key: "t" })}\n`, "utf8");
		expect(readRunState(dir)).toBeUndefined(); // no status
	});

	it("reads a worker-written record and classifies its state", () => {
		const dir = mkdtemp();
		writeRunState(dir, state(dir, { status: "running" }));
		expect(readRunState(dir)?.status).toBe("running");
		expect(runStateKind(readRunState(dir))).toBe("active");

		writeRunState(dir, state(dir, { status: "done", ended_at: "2026-10-10T03:00:00.000Z", exit: 0 }));
		expect(runStateKind(readRunState(dir))).toBe("terminal");
		expect(isTerminalRunStatus("done")).toBe(true);
	});

	it("treats a future/unknown status as no information instead of wedging dispatch", () => {
		const dir = mkdtemp();
		writeRunState(dir, { ...state(dir), status: "quarantined" } as unknown as RunState);
		expect(runStateKind(readRunState(dir))).toBe("unknown");
		expect(isTerminalRunStatus("quarantined")).toBe(false);
	});

	it("every terminal status of the cross-language contract is terminal", () => {
		for (const status of ["done", "failed", "needs-clarification", "lost"]) {
			expect(isTerminalRunStatus(status)).toBe(true);
		}
		for (const status of ["running", "pending"]) {
			expect(isTerminalRunStatus(status)).toBe(false);
		}
	});
});

describe("run-store: write is atomic and best-effort (AC-022/R15)", () => {
	it("writes the record without leaving a temp file behind", () => {
		const dir = mkdtemp();
		const result = writeRunState(dir, state(dir));
		expect(result.ok).toBe(true);
		expect(fs.existsSync(path.join(dir, "run.json.tmp"))).toBe(false);
		expect(readRunState(dir)?.task_key).toBe(path.basename(dir));
	});

	it("never throws and notes the failure in trace.log when the product cannot be written", () => {
		const dir = mkdtemp();
		// A directory in the target slot makes the tmp+rename swap fail.
		fs.mkdirSync(path.join(dir, "run.json"), { recursive: true });

		const result = writeRunState(dir, state(dir, { status: "running" }));

		expect(result.ok).toBe(false);
		expect(result.error).toBeTruthy();
		expect(fs.readFileSync(path.join(dir, "trace.log"), "utf8")).toContain("[RUN] run.json write failed");
	});

	it("run_id is unique per run and the marker carries it", () => {
		const first = newRunId("t-1", new Date("2026-10-10T02:00:00.000Z"));
		const second = newRunId("t-1", new Date("2026-10-10T02:00:01.000Z"));
		expect(first).toBe("t-1@2026-10-10T02:00:00.000Z");
		expect(first).not.toBe(second);
		expect(runMarker(state("/x/t-1"))).toBe("<!-- mw-run: t-1@2026-10-10T02:00:00.000Z status=running -->");
	});
});

describe("run-store: supersedes header + artifact list", () => {
	it("parses only a real header line", () => {
		expect(parseSupersedes("type: coding\nsupersedes: t-14\n\nbody\n")).toBe("t-14");
		expect(parseSupersedes("type: coding\n\nbody mentions supersedes: t-14\n")).toBeUndefined();
		expect(parseSupersedes("type: coding\n\uFEFFsupersedes:\n")).toBeUndefined();
	});

	it("collects the deliverables that exist, sorted", () => {
		const dir = mkdtemp();
		fs.writeFileSync(path.join(dir, "output.md"), "x", "utf8");
		fs.writeFileSync(path.join(dir, "progress.md"), "x", "utf8");
		fs.writeFileSync(path.join(dir, "phase-1-impl.md"), "x", "utf8");
		fs.writeFileSync(path.join(dir, "task.md"), "x", "utf8");
		expect(collectArtifacts(dir)).toEqual(["output.md", "phase-1-impl.md", "progress.md"]);
	});
});

describe("run-store: evaluateRunIdentity (AC-022/D-023)", () => {
	function verdictFor(
		taskDir: string,
		taskContent: string,
		targets: Record<string, string> = {},
	): ReturnType<typeof evaluateRunIdentity> {
		return evaluateRunIdentity({
			taskDir,
			readTaskContent: () => taskContent,
			resolveTaskDir: (key) => targets[key],
		});
	}

	it("allows a task with no run record at all (zero backfill)", () => {
		const dir = mkdtemp();
		writeTask(dir, "type: coding\n\nwork\n");
		expect(verdictFor(dir, "type: coding\n\nwork\n")).toEqual({ ok: true });
	});

	it("refuses a task whose own run already ended", () => {
		const dir = mkdtemp();
		writeRunState(dir, state(dir, { status: "done", exit: 0 }));
		const verdict = verdictFor(dir, "type: coding\n\nwork\n");
		expect(verdict.ok).toBe(false);
		expect(verdict.ok === false && verdict.reason).toBe("run-terminal");
	});

	it("refuses a live run instead of duplicating its directory writer", () => {
		const dir = mkdtemp();
		writeRunState(dir, state(dir, { status: "running" }));
		const verdict = verdictFor(dir, "type: coding\n\nwork\n");
		expect(verdict.ok === false && verdict.reason).toBe("run-active");
	});

	it("does not even read task.md when the task already has a run record", () => {
		const dir = mkdtemp();
		writeRunState(dir, state(dir, { status: "failed", exit: 1 }));
		let reads = 0;
		const verdict = evaluateRunIdentity({
			taskDir: dir,
			readTaskContent: () => {
				reads += 1;
				return "type: coding\n\nwork\n";
			},
			resolveTaskDir: () => undefined,
		});
		expect(verdict.ok).toBe(false);
		expect(reads).toBe(0);
	});

	it("allows a replacement run only when the superseded run already ended", () => {
		const oldDir = mkdtemp();
		const newDir = mkdtemp();
		writeRunState(oldDir, state(oldDir, { status: "done", exit: 0 }));
		const content = "type: coding\nsupersedes: t-old\n\nwork\n";

		expect(verdictFor(newDir, content, { "t-old": oldDir })).toEqual({ ok: true });
	});

	it("refuses a supersede target that is unknown or not terminal", () => {
		const liveDir = mkdtemp();
		const newDir = mkdtemp();
		writeRunState(liveDir, state(liveDir, { status: "running" }));
		const content = "type: coding\nsupersedes: t-old\n\nwork\n";

		const unknown = verdictFor(newDir, content);
		expect(unknown.ok === false && unknown.reason).toBe("supersede-unknown");

		const active = verdictFor(newDir, content, { "t-old": liveDir });
		expect(active.ok === false && active.reason).toBe("supersede-not-terminal");
		expect(active.ok === false && active.detail).toContain("active");
	});
});
