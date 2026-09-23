/**
 * Cross-key aggregate-line tests for the bottom watch panel
 * (mw-worker-visibility-gate T-3; AC/VC-006..009 + the own-row regression).
 *
 * renderWatchLines' new optional sixth parameter names the task keys THIS
 * window dispatched that landed under a DIFFERENT key (mw-task-scope-isolation
 * watch.dispatchedTaskKeys). Those rows must render as exactly ONE aggregate
 * tail line (design D-105/D-106) — never as rows of the watched key — and the
 * panel must stay line-for-line identical to the pre-aggregate output when the
 * parameter is omitted or empty (AC-007/VC-007).
 *
 * Fixtures reuse the construction style of agent-team-loop.test.ts:2145
 * (WorkerStore + IndexStore + AckStore over one temp .agenticdoc root, rows
 * queued via WorkerStore.upsert under {owner}/workers/<task>/). Every fixture
 * lives under os.tmpdir() — the repo is never polluted.
 *
 * [VERIFY] lines go to stdout via process.stdout.write (P-006: the suite
 * swallows console.log from green tests).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import { renderWatchLines } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { type WorkerStatus, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "atl-watch-agg-"));
}

/** Queue a worker row (task.md + queue entry) under {owner}/workers/{taskKey}/ —
 * the same construction agent-team-loop.test.ts:2145 uses (queueTask helper). */
async function queueRow(root: string, owner: string, taskKey: string, status: WorkerStatus): Promise<void> {
	const taskDir = path.join(root, owner, "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
	await new WorkerStore(root).upsert({
		taskKey,
		status,
		cli: "pi",
		provider: "timi",
		taskPath: path.join(taskDir, "task.md"),
		dispatchedAt: "",
		updatedAt: "",
		model: "",
	});
}

/** Register the watched key in _index.parallel (activateKey helper, :1885). */
async function activateKey(root: string, key: string): Promise<void> {
	await new IndexStore(root).upsert({
		key,
		status: "active",
		phase: "EXECUTE",
		claimId: "1",
		deps: "",
		desc: "",
		updated: new Date().toISOString(),
	});
}

/** Build the standard VC-006 fixture in `root` and return its stores: watched
 * key-a with no rows, plus one running row under _scratch. */
async function buildBaseFixture(root: string): Promise<{
	store: WorkerStore;
	is: IndexStore;
	ackStore: AckStore;
}> {
	const store = new WorkerStore(root);
	const is = new IndexStore(root);
	const ackStore = new AckStore(root);
	await activateKey(root, "key-a");
	await queueRow(root, "_scratch", "agg-task", "running");
	return { store, is, ackStore };
}

describe("renderWatchLines cross-key aggregate (D-105/D-106)", () => {
	it("VC-006: one cross-key running row renders exactly one aggregate line", async () => {
		const root = mkdtemp();
		try {
			const { store, is, ackStore } = await buildBaseFixture(root);
			const lines = renderWatchLines(is, store, ackStore, root, "key-a", new Set(["agg-task"]));
			const aggLines = lines.filter((l) => l.includes("elsewhere"));
			expect(aggLines).toHaveLength(1);
			expect(aggLines[0]).toContain("_scratch");
			expect(aggLines[0]).toContain("running");
			expect(aggLines[0].length).toBeLessThanOrEqual(110);
			// The watched key's own empty-state text survives ahead of the tail.
			expect(lines).toContain("  (no worker tasks)");
			process.stdout.write(
				`[VERIFY] VC-006: agg_lines=${aggLines.length} owner_in_line=${aggLines[0].includes("_scratch")} count_in_line=${aggLines[0].includes("running")} max_len=${aggLines[0].length}\n`,
			);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-007: omitted / empty sixth param keeps the panel identical to the baseline", async () => {
		const root = mkdtemp();
		const root2 = mkdtemp();
		try {
			const { store, is, ackStore } = await buildBaseFixture(root);
			// Baseline: the pre-aggregate call form (no sixth argument).
			const baseline = renderWatchLines(is, store, ackStore, root, "key-a");
			// Undefined explicit argument = omitted (the poll loop's shape when
			// nothing was dispatched cross-key yet).
			const omitted = renderWatchLines(is, store, ackStore, root, "key-a", undefined);
			// An explicitly empty set must behave the same as no set at all.
			const empty = renderWatchLines(is, store, ackStore, root, "key-a", new Set<string>());
			expect(omitted).toEqual(baseline);
			expect(empty).toEqual(baseline);
			expect(baseline.filter((l) => l.includes("elsewhere"))).toHaveLength(0);
			expect(omitted.filter((l) => l.includes("elsewhere"))).toHaveLength(0);

			// Same construction again in a fresh root: the no-argument output is
			// line-for-line equal (the baseline itself is deterministic).
			const twin = await buildBaseFixture(root2);
			const baseline2 = renderWatchLines(twin.is, twin.store, twin.ackStore, root2, "key-a");
			expect(baseline2).toEqual(baseline);
			process.stdout.write(
				`[VERIFY] VC-007: agg_lines=0 identical_baseline=${baseline2.join("\n") === baseline.join("\n")}\n`,
			);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
			fs.rmSync(root2, { recursive: true, force: true });
		}
	});

	it("VC-008: unacked failed cross-key rows are counted in the aggregate", async () => {
		const root = mkdtemp();
		try {
			const { store, is, ackStore } = await buildBaseFixture(root);
			// A terminal row the PM has NOT acked — it must still be counted.
			await queueRow(root, "_scratch", "agg-fail", "failed");
			const lines = renderWatchLines(is, store, ackStore, root, "key-a", new Set(["agg-task", "agg-fail"]));
			const aggLines = lines.filter((l) => l.includes("elsewhere"));
			expect(aggLines).toHaveLength(1);
			const failedRows = store.readAll().filter((e) => e.status === "failed").length;
			expect(failedRows).toBe(1);
			expect(aggLines[0]).toContain(`${failedRows} failed`);
			expect(aggLines[0]).toContain("2 elsewhere");
			process.stdout.write(`[VERIFY] VC-008: agg_lines=${aggLines.length} terminal_counted=${failedRows}\n`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-009: high-risk checkpoints on cross-key running rows surface as risk=high:<K>", async () => {
		const root = mkdtemp();
		try {
			const { store, is, ackStore } = await buildBaseFixture(root);
			// Second cross-key running row whose trace.log carries the machine
			// checkpoint verdict. readTaskProgress parses [CHECKPOINT] trace lines
			// (output-writer.appendCheckpoint format) — the progress.md CKPT
			// [machine] line is a different, display-only artifact, so the
			// equivalent trace text is what feeds the machine verdict here.
			await queueRow(root, "_scratch", "agg-risk", "running");
			const riskTaskDir = path.join(root, "_scratch", "workers", "agg-risk");
			fs.writeFileSync(
				path.join(riskTaskDir, "trace.log"),
				`[START] ${new Date(Date.now() - 2_400_000).toISOString()} task=agg-risk type=coding phases=2\n` +
					`[CHECKPOINT] ${new Date().toISOString()} elapsed=1800s reads=42 writes=3 phases=1/2 uniq_targets=2 repeat_top=9 risk=high\n`,
				"utf8",
			);
			// Low-risk counterweight: also running, must NOT add to K.
			await queueRow(root, "_scratch", "agg-low", "running");
			fs.writeFileSync(
				path.join(root, "_scratch", "workers", "agg-low", "trace.log"),
				`[CHECKPOINT] ${new Date().toISOString()} elapsed=1800s reads=4 writes=2 phases=1/2 uniq_targets=2 repeat_top=1 risk=low\n`,
				"utf8",
			);
			const lines = renderWatchLines(
				is,
				store,
				ackStore,
				root,
				"key-a",
				new Set(["agg-task", "agg-risk", "agg-low"]),
			);
			const aggLine = lines.find((l) => l.includes("elsewhere"));
			expect(aggLine).toBeDefined();
			expect(aggLine).toContain("risk=high");
			expect(aggLine).toContain("risk=high:1");
			expect(aggLine).toContain("3 running");
			process.stdout.write(`[VERIFY] VC-009: risk_marker=risk=high:1\n`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("own-key terminal rows render identically while the aggregate tail is appended", async () => {
		const root = mkdtemp();
		try {
			const store = new WorkerStore(root);
			const is = new IndexStore(root);
			const ackStore = new AckStore(root);
			await activateKey(root, "key-a");
			// Both own-row classes coexist with a cross-key dispatched row in the
			// same queue read: done (history) + failed (unhandled).
			await queueRow(root, "key-a", "own-done", "done");
			await queueRow(root, "key-a", "own-fail", "failed");
			await queueRow(root, "_scratch", "agg-run", "running");

			const without = renderWatchLines(is, store, ackStore, root, "key-a");
			const withAggregate = renderWatchLines(is, store, ackStore, root, "key-a", new Set(["agg-run"]));
			// The own-key lines are untouched: identical prefix, exactly one
			// appended tail line, and the tail is the aggregate.
			expect(withAggregate.slice(0, without.length)).toEqual(without);
			expect(withAggregate.length).toBe(without.length + 1);
			expect(withAggregate.at(-1)).toContain("elsewhere");
			expect(without.some((l) => l.includes("own-done"))).toBe(true);
			expect(without.some((l) => l.includes("own-fail"))).toBe(true);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("multi-owner aggregate: groups sort by (rows desc, owner asc) and truncate at 110", async () => {
		const root = mkdtemp();
		try {
			const store = new WorkerStore(root);
			const is = new IndexStore(root);
			const ackStore = new AckStore(root);
			await activateKey(root, "key-a");
			// key-b owns 3 rows, _scratch 2 → rows-desc puts key-b first.
			await queueRow(root, "key-b", "m3", "running");
			await queueRow(root, "key-b", "m4", "failed");
			await queueRow(root, "key-b", "m5", "done");
			await queueRow(root, "_scratch", "m1", "running");
			await queueRow(root, "_scratch", "m2", "pending");
			const lines = renderWatchLines(is, store, ackStore, root, "key-a", new Set(["m1", "m2", "m3", "m4", "m5"]));
			const aggLine = lines.find((l) => l.includes("elsewhere"));
			if (aggLine === undefined) throw new Error("aggregate line missing");
			expect(aggLine).toContain("5 elsewhere");
			expect(aggLine).toContain("key-b(1 running, 1 done, 1 failed)");
			expect(aggLine).toContain("_scratch(1 running, 1 pending)");
			expect(aggLine.indexOf("key-b(")).toBeLessThan(aggLine.indexOf("_scratch("));
			process.stdout.write(`[VERIFY] multi-owner sample: ${aggLine}\n`);

			// Equal row counts → owner name ascending breaks the tie.
			await queueRow(root, "zzz-key", "m6", "running");
			await queueRow(root, "aaa-key", "m7", "running");
			const tieLines = renderWatchLines(is, store, ackStore, root, "key-a", new Set(["m6", "m7"]));
			const tieLine = tieLines.find((l) => l.includes("elsewhere"));
			if (tieLine === undefined) throw new Error("tie-break aggregate line missing");
			expect(tieLine).toContain("aaa-key(");
			expect(tieLine.indexOf("aaa-key(")).toBeLessThan(tieLine.indexOf("zzz-key("));
			process.stdout.write(`[VERIFY] tie-break sample: ${tieLine}\n`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("an over-long aggregate line truncates to WATCH_LINE_MAX (110)", async () => {
		const root = mkdtemp();
		try {
			const store = new WorkerStore(root);
			const is = new IndexStore(root);
			const ackStore = new AckStore(root);
			await activateKey(root, "key-a");
			const longOwner = "key-with-a-deliberately-long-name-for-truncation";
			await queueRow(root, longOwner, "t1", "running");
			await queueRow(root, longOwner, "t2", "pending");
			await queueRow(root, longOwner, "t3", "done");
			await queueRow(root, longOwner, "t4", "failed");
			await queueRow(root, longOwner, "t5", "needs-clarification");
			const lines = renderWatchLines(is, store, ackStore, root, "key-a", new Set(["t1", "t2", "t3", "t4", "t5"]));
			const aggLine = lines.find((l) => l.includes("elsewhere"));
			if (aggLine === undefined) throw new Error("aggregate line missing");
			// trunc() caps at 110 chars, the last being the ellipsis glyph.
			expect(aggLine.length).toBe(110);
			expect(aggLine.endsWith("…")).toBe(true);
			expect(aggLine.startsWith(`  ~ 5 elsewhere: ${longOwner}(`)).toBe(true);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
