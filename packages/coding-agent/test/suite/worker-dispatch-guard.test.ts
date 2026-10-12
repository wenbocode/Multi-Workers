/**
 * worker-dispatch-guard.test.ts — T-17/T-19 (AC-019/AC-020/AC-021/AC-022):
 * the dispatch scan's fail-closed guards, its single-scan quota and the scope
 * split that keeps a PM turn away from other keys' history.
 *
 * These are the guards the IN-3 incident (2026-10-10T02:50:05Z, 252 rows
 * re-queued in one second, peak 66 workers) showed to be missing: the scan
 * trusted an unreadable queue, had no terminal-state notion and no quota.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	DEFAULT_DISPATCH_MAX_PER_SCAN,
	type DispatchAlarm,
	describeDispatchAlarm,
	dispatchNewTasks,
	pmActivate,
	readDispatchMaxPerScan,
	recordDispatchAlarm,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import { RUN_SCHEMA, type RunState, writeRunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { type WorkerEntry, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const tempDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-dispatch-guard-"));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Key docs that satisfy the dispatch docs gate (same shape as the existing
 * agent-team-loop suite). */
function writePhaseDocs(root: string, key: string): void {
	const keyDir = path.join(root, key);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Spec\n${"x".repeat(600)}\n\n| AC-001 | in x, y returns z |\n`,
		"utf8",
	);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}`, "utf8");
	const research = path.join(keyDir, "evidence", "research");
	fs.mkdirSync(research, { recursive: true });
	fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "# research\n", "utf8");
	fs.writeFileSync(path.join(research, "design-topic-2026-01-01.md"), "# research\n", "utf8");
}

function writeTask(root: string, key: string, taskKey: string, evidence?: string): string {
	const dir = path.join(root, key, "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	const md = path.join(dir, "task.md");
	fs.writeFileSync(md, "type: research\n\nwork\n", "utf8");
	if (evidence) fs.writeFileSync(path.join(dir, evidence), "already ran\n", "utf8");
	return md;
}

function queuePath(root: string): string {
	return path.join(root, "_workers.parallel");
}

function entry(root: string, key: string, taskKey: string): WorkerEntry {
	return {
		taskKey,
		status: "running",
		cli: "pi",
		provider: "timi",
		taskPath: path.join(root, key, "workers", taskKey, "task.md"),
		dispatchedAt: "2026-10-10T00:00:00.000Z",
		updatedAt: "2026-10-10T00:00:00.000Z",
		model: "",
		origin: "manual",
	};
}

describe("dispatch scope split (T-19, AC-019)", () => {
	it("scope pm queues only the watched key + _scratch and never rewrites another key's history", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		writePhaseDocs(root, "watched");
		writePhaseDocs(root, "other");
		writeTask(root, "watched", "w-1");
		writeTask(root, "other", "o-1");
		writeTask(root, "_scratch", "s-1");
		// A pre-existing row of the other key: the isolated scan must leave it
		// byte-identical (this is the exact damage IN-3 did to 20+ keys).
		await store.upsert(entry(root, "other", "o-history"));

		await dispatchNewTasks(store, root, { scope: "pm", watchedKey: "watched" });

		const keys = store
			.readAll()
			.map((r) => r.taskKey)
			.sort();
		expect(keys).toEqual(["o-history", "s-1", "w-1"]);
		expect(store.findByKey("o-1")).toBeUndefined();
		expect(fs.readFileSync(queuePath(root), "utf8")).toContain("o-history");
	});

	it("scope cli (the mw command surface) still dispatches across keys", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		writePhaseDocs(root, "watched");
		writePhaseDocs(root, "other");
		writeTask(root, "watched", "w-1");
		writeTask(root, "other", "o-1");

		// No scope option = the historical global behaviour (explicit callers).
		await dispatchNewTasks(store, root);

		expect(store.findByKey("o-1")?.status).toBe("pending");
		expect(store.findByKey("w-1")?.status).toBe("pending");
	});

	it("scope pm without a watched key still picks up _scratch (never the whole project)", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		writePhaseDocs(root, "other");
		writeTask(root, "other", "o-1");
		writeTask(root, "_scratch", "s-1");

		await dispatchNewTasks(store, root, { scope: "pm" });

		expect(store.findByKey("s-1")?.status).toBe("pending");
		expect(store.findByKey("o-1")).toBeUndefined();
	});

	it("reports the keys it did not scan instead of skipping them silently (T-19/T-20)", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "watched");
		writePhaseDocs(root, "other");
		writeTask(root, "other", "o-1");
		const store = new WorkerStore(root);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, root, {
			scope: "pm",
			watchedKey: "watched",
			onAlarm: (a) => alarms.push(a),
		});

		// Visibility, not prohibition: nothing of the other key was touched, but
		// the PM can see that it existed (and why it was left alone).
		expect(alarms).toEqual([{ kind: "out-of-scope", count: 1, detail: "other" }]);
		expect(store.readAll()).toEqual([]);
	});
});

describe("dispatch alarm wiring (T-17)", () => {
	it("a refused agent_settled scan writes one ledger row and alerts the PM once per kind", async () => {
		const root = mkdtemp();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		fs.mkdirSync(agenticdocRoot, { recursive: true });
		const cwd = process.cwd();
		process.chdir(root);
		try {
			const handlers = new Map<string, (event?: unknown, ctx?: unknown) => unknown>();
			const sent: string[] = [];
			const pi = {
				registerCommand: () => {},
				registerTool: () => {},
				on: (name: string, handler: (event?: unknown, ctx?: unknown) => unknown) => {
					handlers.set(name, handler);
				},
				appendEntry: () => {},
				sendMessage: (m: unknown) => {
					const content = typeof m === "string" ? m : ((m as { content?: string }).content ?? "");
					sent.push(content);
				},
			} as unknown as ExtensionAPI;
			pmActivate(pi);

			// IN-3 shape: one unreadable queue row plus a genuinely pending task.
			fs.writeFileSync(
				path.join(agenticdocRoot, "_workers.parallel"),
				"a | b | c | d | e | f | g | h | i | j\n",
				"utf8",
			);
			writePhaseDocs(agenticdocRoot, "k");
			writeTask(agenticdocRoot, "k", "t-1");

			const settle = handlers.get("agent_settled");
			const shutdown = handlers.get("session_shutdown");
			if (!settle) throw new Error("no agent_settled handler");
			settle({}, undefined);
			const ledger = path.join(agenticdocRoot, "_autopilot", "auto-decisions.jsonl");
			for (let i = 0; i < 100 && !fs.existsSync(ledger); i += 1) {
				await new Promise((resolve) => setTimeout(resolve, 10));
			}
			const readRows = (): Array<{ phase: string; kind: string }> =>
				fs
					.readFileSync(ledger, "utf8")
					.split("\n")
					.filter((l) => l.trim() !== "")
					.map((l) => JSON.parse(l) as { phase: string; kind: string });

			expect(readRows()).toEqual([
				{ seq: 1, phase: "dispatch-alarm", kind: "queue-rows-unparsable", count: 1, detail: "cols" },
			]);
			expect(sent.some((text) => text.includes("dispatch"))).toBe(true);

			// Once per kind per session: a second settled turn adds neither a row
			// nor a second PM wake-up.
			settle({}, undefined);
			await new Promise((resolve) => setTimeout(resolve, 50));
			expect(readRows()).toHaveLength(1);
			shutdown?.({}, undefined);
		} finally {
			process.chdir(cwd);
		}
	});
});

describe("fail-closed guards (T-17, AC-020/AC-021/AC-022)", () => {
	it("an unreadable queue row aborts the whole scan and is preserved", async () => {
		const root = mkdtemp();
		fs.mkdirSync(root, { recursive: true });
		const badLine = "a | b | c | d | e | f | g | h | i | j";
		fs.writeFileSync(queuePath(root), `${badLine}\n`, "utf8");
		writePhaseDocs(root, "k");
		writeTask(root, "k", "t-1");
		const store = new WorkerStore(root);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, root, { onAlarm: (a) => alarms.push(a) });

		expect(alarms.map((a) => a.kind)).toEqual(["queue-rows-unparsable"]);
		expect(store.readAll()).toEqual([]);
		expect(fs.readFileSync(queuePath(root), "utf8")).toContain(badLine);
	});

	it("an empty queue plus product evidence refuses the scan; a fresh project dispatches", async () => {
		// (a) IN-3 shape: queue emptied, the work already ran.
		const root = mkdtemp();
		fs.mkdirSync(root, { recursive: true });
		fs.writeFileSync(queuePath(root), "", "utf8");
		writePhaseDocs(root, "k");
		writeTask(root, "k", "t-1", "output.md");
		const store = new WorkerStore(root);
		const alarms: DispatchAlarm[] = [];
		await dispatchNewTasks(store, root, { onAlarm: (a) => alarms.push(a) });
		expect(alarms.map((a) => a.kind)).toEqual(["queue-unreadable"]);
		expect(store.readAll()).toEqual([]);

		// (b) Control: same empty queue, but the task has never run.
		const fresh = mkdtemp();
		writePhaseDocs(fresh, "k");
		writeTask(fresh, "k", "t-1");
		const freshStore = new WorkerStore(fresh);
		const freshAlarms: DispatchAlarm[] = [];
		await dispatchNewTasks(freshStore, fresh, { onAlarm: (a) => freshAlarms.push(a) });
		expect(freshAlarms).toEqual([]);
		expect(freshStore.findByKey("t-1")?.status).toBe("pending");
	});

	it("queues at most the per-scan quota and reports the refusal", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "k");
		for (let i = 1; i <= 5; i += 1) writeTask(root, "k", `t-${i}`);
		const store = new WorkerStore(root);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, root, { onAlarm: (a) => alarms.push(a) });

		expect(store.readAll()).toHaveLength(DEFAULT_DISPATCH_MAX_PER_SCAN);
		expect(alarms.map((a) => a.kind)).toEqual(["dispatch-quota"]);
		expect(alarms[0]?.count).toBe(DEFAULT_DISPATCH_MAX_PER_SCAN);
	});

	it("refuses a 10-candidate scan after the quota (the IN-3 scan shape, T-21)", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "k");
		for (let i = 1; i <= 10; i += 1) writeTask(root, "k", `t-${i}`);
		const store = new WorkerStore(root);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, root, { onAlarm: (a) => alarms.push(a) });

		// 10 candidates in one alphabetical scan: exactly the quota is queued and
		// the rest is refused with one alarm - never 10 rows, never silence. The
		// kept keys are ASCII-ordered (`t-10` before `t-2`), which is the same
		// fingerprint the incident's 252-row rebuild carries.
		expect(store.readAll()).toHaveLength(DEFAULT_DISPATCH_MAX_PER_SCAN);
		expect(store.readAll().map((r) => r.taskKey)).toEqual(["t-1", "t-10", "t-2"]);
		expect(alarms.map((a) => a.kind)).toEqual(["dispatch-quota"]);
		expect(alarms[0]?.count).toBe(DEFAULT_DISPATCH_MAX_PER_SCAN);
	});

	it("refuses a candidate whose own run already ended and reports the conflict (AC-022)", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "k");
		writeTask(root, "k", "t-1");
		const store = new WorkerStore(root);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, root, {
			runVerdict: () => ({ ok: false, reason: "run-terminal", detail: "status=done" }),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.readAll()).toEqual([]);
		expect(alarms).toEqual([
			{
				kind: "run-ledger-conflict",
				count: 1,
				detail: "1 refused (run-terminal): t-1:run-terminal(status=done)",
			},
		]);
	});

	it("refuses a live run so a task dir never gets two writers (AC-022)", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "k");
		writeTask(root, "k", "t-live");
		const store = new WorkerStore(root);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, root, {
			runVerdict: () => ({ ok: false, reason: "run-active" }),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.readAll()).toEqual([]);
		expect(alarms[0]?.kind).toBe("run-ledger-conflict");
	});

	it("records a machine-readable alarm row the decision loop cannot see (AC-020/AC-021)", () => {
		const root = mkdtemp();
		const alarms: DispatchAlarm[] = [
			{ kind: "queue-rows-unparsable", count: 2, detail: "10 columns" },
			{ kind: "dispatch-quota", count: DEFAULT_DISPATCH_MAX_PER_SCAN },
		];
		for (const alarm of alarms) {
			recordDispatchAlarm(root, alarm);
			expect(describeDispatchAlarm(alarm)).toContain(String(alarm.count));
		}

		const ledger = path.join(root, "_autopilot", "auto-decisions.jsonl");
		const rows = fs
			.readFileSync(ledger, "utf8")
			.split("\n")
			.filter((l) => l.trim() !== "")
			.map((l) => JSON.parse(l) as { seq: number; phase: string; kind: string; count: number });
		expect(rows.map((r) => r.seq)).toEqual([1, 2]);
		expect(rows.map((r) => r.kind)).toEqual(["queue-rows-unparsable", "dispatch-quota"]);
		// `phase` keeps the row out of the `phase == "decide"` consumers.
		expect(rows.every((r) => r.phase === "dispatch-alarm")).toBe(true);
	});

	it("reads the quota from the project's dispatch_max_per_scan (AC-021/D-026)", async () => {
		const root = mkdtemp();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		fs.mkdirSync(agenticdocRoot, { recursive: true });
		writePhaseDocs(agenticdocRoot, "k");
		for (let i = 0; i < 5; i += 1) writeTask(agenticdocRoot, "k", `t-${i}`);
		const configPath = path.join(agenticdocRoot, "_autopilot", "config.json");
		fs.mkdirSync(path.dirname(configPath), { recursive: true });
		fs.writeFileSync(configPath, `${JSON.stringify({ dispatch_max_per_scan: 1 })}\n`, "utf8");
		const store = new WorkerStore(agenticdocRoot);

		expect(readDispatchMaxPerScan(agenticdocRoot)).toBe(1);
		await dispatchNewTasks(store, agenticdocRoot);
		expect(store.readAll()).toHaveLength(1);

		// A broken config falls back to the built-in default instead of
		// disabling the quota.
		fs.writeFileSync(configPath, "{ not json\n", "utf8");
		expect(readDispatchMaxPerScan(agenticdocRoot)).toBe(DEFAULT_DISPATCH_MAX_PER_SCAN);
	});
});

describe("run identity wiring (T-20, AC-022)", () => {
	interface PmHarness {
		handlers: Map<string, (event?: unknown, ctx?: unknown) => unknown>;
		sent: string[];
	}

	/** Activate the real PM wiring against `<root>/.agenticdoc` — `pmActivate`
	 * resolves the project from cwd (the dispatch-alarm test pattern). */
	function activate(): PmHarness {
		const handlers = new Map<string, (event?: unknown, ctx?: unknown) => unknown>();
		const sent: string[] = [];
		const pi = {
			registerCommand: () => {},
			registerTool: () => {},
			on: (name: string, handler: (event?: unknown, ctx?: unknown) => unknown) => {
				handlers.set(name, handler);
			},
			appendEntry: () => {},
			sendMessage: (m: unknown) => {
				const content = typeof m === "string" ? m : ((m as { content?: string }).content ?? "");
				sent.push(content);
			},
		} as unknown as ExtensionAPI;
		pmActivate(pi);
		return { handlers, sent };
	}

	/** One PM turn: settle, then wait for the queue to reach its final size. */
	async function settleAndWait(harness: PmHarness, settleMs = 120): Promise<void> {
		const settle = harness.handlers.get("agent_settled");
		if (!settle) throw new Error("no agent_settled handler");
		settle({}, undefined);
		await new Promise((resolve) => setTimeout(resolve, settleMs));
	}

	function scratchTask(agenticdocRoot: string, taskKey: string, body = "type: research\n\nwork\n"): string {
		const dir = path.join(agenticdocRoot, "_scratch", "workers", taskKey);
		fs.mkdirSync(dir, { recursive: true });
		fs.writeFileSync(path.join(dir, "task.md"), body, "utf8");
		return dir;
	}

	function runRecord(taskDir: string, taskKey: string, status: RunState["status"], exit?: number): void {
		const record: RunState = {
			schema: RUN_SCHEMA,
			task_key: taskKey,
			run_id: `${taskKey}@2026-10-10T02:00:00.000Z`,
			owner_key: "_scratch",
			kind: "research",
			status,
			started_at: "2026-10-10T02:00:00.000Z",
			ended_at: status === "running" ? undefined : "2026-10-10T02:10:00.000Z",
			exit,
			artifacts: [],
		};
		writeRunState(taskDir, record);
	}

	function ledgerKinds(agenticdocRoot: string): Array<{ kind: string; count: number; detail: string }> {
		const ledger = path.join(agenticdocRoot, "_autopilot", "auto-decisions.jsonl");
		if (!fs.existsSync(ledger)) return [];
		return fs
			.readFileSync(ledger, "utf8")
			.split("\n")
			.filter((l) => l.trim() !== "")
			.map((l) => JSON.parse(l) as { kind: string; count: number; detail: string })
			.filter((row) => row.kind === "run-ledger-conflict");
	}

	it("never re-queues a task whose own run already ended AND says why", async () => {
		const root = mkdtemp();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const taskDir = scratchTask(agenticdocRoot, "t-done");
		fs.writeFileSync(path.join(taskDir, "output.md"), "already finished\n", "utf8");
		runRecord(taskDir, "t-done", "done", 0);
		const cwd = process.cwd();
		process.chdir(root);
		try {
			const harness = activate();
			try {
				await settleAndWait(harness);
				const store = new WorkerStore(agenticdocRoot);
				expect(store.findByKey("t-done")).toBeUndefined();
				const rows = ledgerKinds(agenticdocRoot);
				expect(rows).toHaveLength(1);
				expect(rows[0]?.count).toBe(1);
				expect(rows[0]?.detail).toContain("t-done:run-terminal");
			} finally {
				harness.handlers.get("session_shutdown")?.({}, undefined);
			}
		} finally {
			process.chdir(cwd);
		}
	});

	it("refuses a live run that lost its queue row (no second writer)", async () => {
		const root = mkdtemp();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const taskDir = scratchTask(agenticdocRoot, "t-live");
		runRecord(taskDir, "t-live", "running");
		const cwd = process.cwd();
		process.chdir(root);
		try {
			const harness = activate();
			try {
				await settleAndWait(harness);
				expect(new WorkerStore(agenticdocRoot).findByKey("t-live")).toBeUndefined();
				expect(ledgerKinds(agenticdocRoot)[0]?.detail).toContain("t-live:run-active");
			} finally {
				harness.handlers.get("session_shutdown")?.({}, undefined);
			}
		} finally {
			process.chdir(cwd);
		}
	});

	it("dispatches a replacement run that declares supersedes, leaving the old dir untouched", async () => {
		const root = mkdtemp();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const oldDir = scratchTask(agenticdocRoot, "t-old");
		fs.writeFileSync(path.join(oldDir, "output.md"), "the finished first run\n", "utf8");
		runRecord(oldDir, "t-old", "done", 0);
		const before = {
			output: fs.readFileSync(path.join(oldDir, "output.md"), "utf8"),
			run: fs.readFileSync(path.join(oldDir, "run.json"), "utf8"),
			mtime: fs.statSync(path.join(oldDir, "output.md")).mtimeMs,
		};
		// The replacement is a NEW task_key that points back at the finished run.
		scratchTask(agenticdocRoot, "t-old-r2", "type: research\nsupersedes: t-old\n\nmore work\n");
		const cwd = process.cwd();
		process.chdir(root);
		try {
			const harness = activate();
			try {
				await settleAndWait(harness);
				const store = new WorkerStore(agenticdocRoot);
				expect(store.findByKey("t-old-r2")?.status).toBe("pending");
				expect(store.findByKey("t-old")).toBeUndefined();
				// The old directory is read-only for this dispatch: same bytes, same mtime.
				expect(fs.readFileSync(path.join(oldDir, "output.md"), "utf8")).toBe(before.output);
				expect(fs.readFileSync(path.join(oldDir, "run.json"), "utf8")).toBe(before.run);
				expect(fs.statSync(path.join(oldDir, "output.md")).mtimeMs).toBe(before.mtime);
			} finally {
				harness.handlers.get("session_shutdown")?.({}, undefined);
			}
		} finally {
			process.chdir(cwd);
		}
	});

	it("refuses to supersede a run that is not finished", async () => {
		const root = mkdtemp();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const liveDir = scratchTask(agenticdocRoot, "t-live");
		runRecord(liveDir, "t-live", "running");
		scratchTask(agenticdocRoot, "t-live-r2", "type: research\nsupersedes: t-live\n\nretry\n");
		const cwd = process.cwd();
		process.chdir(root);
		try {
			const harness = activate();
			try {
				await settleAndWait(harness);
				expect(new WorkerStore(agenticdocRoot).findByKey("t-live-r2")).toBeUndefined();
				expect(ledgerKinds(agenticdocRoot)[0]?.detail).toContain("supersede-not-terminal");
			} finally {
				harness.handlers.get("session_shutdown")?.({}, undefined);
			}
		} finally {
			process.chdir(cwd);
		}
	});
});

// ── T-17/F-6: the dispatch route follows the header only ─────────────────────
// QG-A found a seventh `type:` reader: `pm-orchestrator.ts` matched
// `/^type:\s*codex/im` against the WHOLE task.md, so one body line could flip
// the dispatch CLI away from pi (no TS guard survives on a codex worker). The
// route now reads the shared single source (`readTaskType`).

describe("T-17 F-6 dispatch route is header-only", () => {
	function writeRawTask(root: string, key: string, taskKey: string, content: string): void {
		const dir = path.join(root, key, "workers", taskKey);
		fs.mkdirSync(dir, { recursive: true });
		fs.writeFileSync(path.join(dir, "task.md"), content, "utf8");
	}

	it("a body-only `type: codex` line does not flip the dispatch CLI", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "k");
		writeRawTask(root, "k", "t-body", "type: research\n\ndig into it\n\ntype: codex\n");
		const store = new WorkerStore(root);

		await dispatchNewTasks(store, root);

		const row = store.findByKey("t-body");
		expect(row?.cli).toBe("pi");
		expect(row?.provider).toBe("timi");
	});

	it("a header `type: codex` still routes to the codex CLI", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "k");
		writeRawTask(root, "k", "t-header", "type: codex\n\nbody\n");
		const store = new WorkerStore(root);

		await dispatchNewTasks(store, root);

		const row = store.findByKey("t-header");
		expect(row?.cli).toBe("codex");
		expect(row?.provider).toBe("");
	});

	it("a header `type: review` wins over a body `type: codex`", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "k");
		writeRawTask(root, "k", "t-review", "type: review\n\nbody\n\ntype: codex\n");
		const store = new WorkerStore(root);

		await dispatchNewTasks(store, root);

		const row = store.findByKey("t-review");
		expect(row?.cli).toBe("pi");
		expect(row?.provider).toBe("timi");
	});
});
