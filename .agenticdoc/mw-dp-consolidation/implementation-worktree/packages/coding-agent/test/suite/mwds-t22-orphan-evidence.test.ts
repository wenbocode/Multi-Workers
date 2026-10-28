/**
 * mwds-t22-orphan-evidence.test.ts — T-22 / AC-011 (key mw-dispatch-card-gate):
 * the ORPHANED admission was "registered in `_index.parallel`" (T-19), which
 * misses two real lost-record shapes:
 *
 *   (b) the row was lost — index/timeline rotation, or a concurrent whole-file
 *       rewrite — while the key kept running (owner traces survive);
 *   (c) registration never finished — `dispatch_worker(key=…)` creates the task
 *       dir and registers in two non-atomic steps, and a crash between them
 *       leaves a fully-populated dir with no row.
 *
 * T-22 widens the ADMISSION EVIDENCE — `_index.parallel` row OR the key's own
 * owner traces — but still never auto-registers: a scanned row would have to
 * invent Phase/ClaimId/Deps, and an ownerless cross-key write violates AC-019.
 * So:
 *   1. ORPHANED = undispatched work ∧ no live claim ∧ no live run ∧ owner
 *      evidence; owner evidence = index row ∨ key owner traces
 *      (`{key}/pm-state.md`'s `- Claim-Id:` / `- Phase:` line, or a
 *      `{key}/workers/<task>/trace.log`);
 *   2. admitted keys take the T-19 claim-free repair (never writes
 *      `_index.parallel`; the conductor's only skip condition stays false);
 *   3. a key with work but NO owner trace is only an actionable notice
 *      (`out-of-scope`, once per key per session), and zero files are written;
 *   4. no path ever adds an `_index.parallel` row because of this card.
 *
 * Fixtures are temp dirs, no provider APIs. The conductor skip condition is
 * asserted against the real Python source, exactly as T-19 does.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	type DispatchAlarm,
	dispatchNewTasks,
	formatDispatchAlarm,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	conductorClaimState,
	IndexStore,
	keyHasOwnerTraces,
} from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { type WorkerEntry, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const tempDirs: string[] = [];

/** `<tmp>/.agenticdoc` — the taskPath anchor `workerOwnerKey` needs. */
function mkWs(): { root: string; agenticdocRoot: string } {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-t22-"));
	tempDirs.push(root);
	const agenticdocRoot = path.join(root, ".agenticdoc");
	fs.mkdirSync(agenticdocRoot, { recursive: true });
	return { root, agenticdocRoot };
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

interface IndexRow {
	key: string;
	status?: string;
	phase?: string;
	claimId?: string;
	desc?: string;
}

function writeIndex(agenticdocRoot: string, rows: IndexRow[]): void {
	const lines = [
		"# Index Parallel",
		"",
		"| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
		"| --- | --- | --- | --- | --- | --- | --- |",
	];
	for (const r of rows) {
		lines.push(
			`| ${r.key} | ${r.status ?? "idle"} | ${r.phase ?? "DONE"} | ${r.claimId ?? "—"} | — | ${
				r.desc ?? ""
			} | 2026-10-12T00:00:00Z |`,
		);
	}
	fs.writeFileSync(path.join(agenticdocRoot, "_index.parallel"), `${lines.join("\n")}\n`, "utf8");
}

/** `_index.parallel` bytes, or `null` when the file does not exist at all —
 * the "not even a header" state the no-row admission must leave untouched. */
function indexText(agenticdocRoot: string): string | null {
	const file = path.join(agenticdocRoot, "_index.parallel");
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
}

function writeTask(agenticdocRoot: string, key: string, taskKey: string, content = "type: coding\n\nbody\n"): string {
	const dir = path.join(agenticdocRoot, key, "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	const md = path.join(dir, "task.md");
	fs.writeFileSync(md, content, "utf8");
	return md;
}

function writeWorkerTrace(agenticdocRoot: string, key: string, taskKey: string): void {
	const dir = path.join(agenticdocRoot, key, "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(path.join(dir, "trace.log"), "[START] pid=1\n", "utf8");
}

/** The framework's own `pm-state.md` shape (state-manager.ts): a `- Key:` line
 * plus the two machine-interface lines. */
function writePmState(agenticdocRoot: string, key: string, snapshot: string): void {
	const dir = path.join(agenticdocRoot, key);
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(path.join(dir, "pm-state.md"), snapshot, "utf8");
}

const PM_STATE_NO_CLAIM =
	"# PM State: orphan\n\n## Section 1: Snapshot\n- Key: orphan\n- Claim-Id: —\n- Phase: TASKS\n- Updated: 2026-10-12T00:00:00Z\n";

function runningRow(agenticdocRoot: string, key: string, taskKey: string): WorkerEntry {
	return {
		taskKey,
		status: "running",
		cli: "pi",
		provider: "timi",
		taskPath: path.join(agenticdocRoot, key, "workers", taskKey, "task.md"),
		dispatchedAt: "2026-10-12T00:00:00.000Z",
		updatedAt: "2026-10-12T00:00:00.000Z",
		model: "",
		origin: "manual",
	};
}

const DEAD_CLAIM = "other-host:4242";

function liveClaim(): string {
	return `${os.hostname()}:${process.pid}`;
}

/** `[VERIFY]` evidence line on real stdout (vite silent:"passed-only" swallows
 * `console.log` from passing tests). */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

/** The conductor skip condition, verbatim from
 * `packages/multi-workers/autopilot/conductor.py`. */
function conductorSkipSource(): string {
	return fs.readFileSync(new URL("../../../multi-workers/autopilot/conductor.py", import.meta.url), "utf8");
}

// ── Owner-trace predicate (T-22 req. 1) ─────────────────────────────────────

describe("key owner traces (T-22 req. 1)", () => {
	it("pm-state.md Claim-Id or Phase line is owner evidence; a bare dir is not", () => {
		const { agenticdocRoot } = mkWs();
		// Claim-Id line.
		writePmState(agenticdocRoot, "with-claim", PM_STATE_NO_CLAIM);
		expect(keyHasOwnerTraces(agenticdocRoot, "with-claim")).toBe(true);
		// Phase-only line (no Claim-Id) still counts.
		writePmState(
			agenticdocRoot,
			"phase-only",
			"# PM State: phase-only\n\n## Section 1: Snapshot\n- Key: phase-only\n- Phase: EXECUTE\n",
		);
		expect(keyHasOwnerTraces(agenticdocRoot, "phase-only")).toBe(true);
		// pm-state.md WITHOUT either machine line is not owner evidence.
		writePmState(agenticdocRoot, "notes-only", "# PM State: notes-only\n\njust notes\n");
		writeTask(agenticdocRoot, "notes-only", "n-1");
		expect(keyHasOwnerTraces(agenticdocRoot, "notes-only")).toBe(false);
		// Bare dir + task.md only: not owner evidence.
		writeTask(agenticdocRoot, "bare", "b-1");
		expect(keyHasOwnerTraces(agenticdocRoot, "bare")).toBe(false);
		// A worker trace.log IS owner evidence.
		writeWorkerTrace(agenticdocRoot, "worker-ran", "w-1");
		expect(keyHasOwnerTraces(agenticdocRoot, "worker-ran")).toBe(true);
		// Missing key: false, never a throw.
		expect(keyHasOwnerTraces(agenticdocRoot, "absent")).toBe(false);
		verify("[VERIFY] T-22: owner_trace pmstate_claim=1 pmstate_phase=1 notes_only=0 bare_dir=0 trace_log=1");
	});

	it("the predicate is read-only against _index.parallel", () => {
		const { agenticdocRoot } = mkWs();
		writePmState(agenticdocRoot, "with-claim", PM_STATE_NO_CLAIM);
		expect(indexText(agenticdocRoot)).toBeNull();
		expect(keyHasOwnerTraces(agenticdocRoot, "with-claim")).toBe(true);
		expect(indexText(agenticdocRoot)).toBeNull();
		verify("[VERIFY] T-22: predicate_writes_index=0");
	});
});

// ── ① owner traces, no index row => ORPHANED + claim-free repair ────────────

describe("ORPHANED admission widening (T-22 req. 1+2)", () => {
	it("pm-state.md Claim-Id + work, NO index row => ORPHANED, repaired, index untouched", async () => {
		const { agenticdocRoot } = mkWs();
		writePmState(agenticdocRoot, "orphan", PM_STATE_NO_CLAIM);
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		expect(indexText(agenticdocRoot)).toBeNull(); // no row, not even a file
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const warned = new Set<string>();

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: warned,
			unregisteredWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		// Admitted and repaired through the T-19 claim-free path.
		expect(store.findByKey("o-1")?.status).toBe("pending");
		expect(warned.has("orphan")).toBe(true);
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([
			{ kind: "orphaned-keys", count: 1, detail: "orphan" },
		]);
		// Req. 4: no row was ever created; the index file still does not exist.
		expect(indexText(agenticdocRoot)).toBeNull();
		expect(new IndexStore(agenticdocRoot).readAll()).toEqual([]);
		// Claim cell untouched (there is none) => the conductor is eligible.
		const claimId = new IndexStore(agenticdocRoot).findByKey("orphan")?.claimId ?? "";
		expect(claimId).toBe("");
		expect(conductorClaimState(claimId)).not.toBe("live");
		// The verdict is only meaningful against the real skip condition: a key
		// with no row derives CLAIM_FREE (`ks = key_states.get(key)`; None =>
		// CLAIM_FREE), so the conductor drives it.
		expect(conductorSkipSource()).toContain("if claim == state.CLAIM_LIVE:");
		verify("[VERIFY] T-22-1: state=ORPHANED_NO_ROW repaired=o-1 index_rows=0 claim='' conductor_eligible=1");
	});

	it("a worker trace.log is enough evidence: repaired, index untouched", async () => {
		const { agenticdocRoot } = mkWs();
		writeWorkerTrace(agenticdocRoot, "orphan", "o-1");
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			unregisteredWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.findByKey("o-1")?.status).toBe("pending");
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([
			{ kind: "orphaned-keys", count: 1, detail: "orphan" },
		]);
		expect(indexText(agenticdocRoot)).toBeNull();
		verify("[VERIFY] T-22-1: trace_log_evidence repaired=o-1 index_rows=0");
	});

	it("owner traces + a live run => NOT orphaned (no repair, no write)", async () => {
		const { agenticdocRoot } = mkWs();
		writePmState(agenticdocRoot, "orphan", PM_STATE_NO_CLAIM);
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		await store.upsert(runningRow(agenticdocRoot, "orphan", "o-running"));
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			unregisteredWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.findByKey("o-1")).toBeUndefined();
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([]);
		expect(indexText(agenticdocRoot)).toBeNull();
		verify("[VERIFY] T-22-1: owner_trace_live_run orphaned=0 repaired=0");
	});

	// ── ③ T-19 regression: index row + no live claim ─────────────────────────
	it("index row + no live claim (T-19 path) => repaired, index bytes unchanged", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "orphan", claimId: DEAD_CLAIM }]);
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const before = indexText(agenticdocRoot);

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			unregisteredWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.findByKey("o-1")?.status).toBe("pending");
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([
			{ kind: "orphaned-keys", count: 1, detail: "orphan" },
		]);
		expect(indexText(agenticdocRoot)).toBe(before);
		const claimId = new IndexStore(agenticdocRoot).findByKey("orphan")?.claimId ?? "";
		expect(claimId).toBe(DEAD_CLAIM);
		expect(conductorClaimState(claimId)).not.toBe("live");
		verify(`[VERIFY] T-22-3: state=ORPHANED_ROW repaired=o-1 claim=${claimId} index_unchanged=1`);
	});

	// ── ④ live claim => writer=0 (AC-019 unchanged) ──────────────────────────
	it("a live claim => zero writes to the key (AC-019 unchanged)", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "owned", claimId: liveClaim() }]);
		writeTask(agenticdocRoot, "owned", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const before = indexText(agenticdocRoot);

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			unregisteredWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.findByKey("o-1")).toBeUndefined();
		expect(alarms).toEqual([]);
		expect(indexText(agenticdocRoot)).toBe(before);
		expect(conductorClaimState(liveClaim())).toBe("live");
		verify("[VERIFY] T-22-4: live_claim writer=0 index_unchanged=1");
	});
});

// ── ② + ⑤ no owner trace => actionable notice, once, writer=0 ───────────────

describe("no owner trace => actionable notice only (T-22 req. 3+5)", () => {
	it("work but no owner record => one neutral notice, zero writes, index unchanged", async () => {
		const { agenticdocRoot } = mkWs();
		const md = writeTask(agenticdocRoot, "never-owned", "n-1", "type: coding\n\nwork\n");
		const taskBefore = fs.readFileSync(md, "utf8");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const warned = new Set<string>();
		const opts = {
			scope: "pm" as const,
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			unregisteredWarned: warned,
			onAlarm: (a: DispatchAlarm) => alarms.push(a),
		};

		// Two ticks of the same scan (⑤ frequency): one notice per key/session.
		await dispatchNewTasks(store, agenticdocRoot, opts);
		await dispatchNewTasks(store, agenticdocRoot, opts);

		expect(warned.has("never-owned")).toBe(true);
		expect(alarms).toEqual([{ kind: "out-of-scope", count: 1, detail: "never-owned" }]);
		// No owner was invented: no queue row, no task.md mutation.
		expect(store.findByKey("n-1")).toBeUndefined();
		expect(store.readAll()).toEqual([]);
		expect(fs.readFileSync(md, "utf8")).toBe(taskBefore);
		// Req. 4: no index row/file appeared.
		expect(indexText(agenticdocRoot)).toBeNull();
		expect(new IndexStore(agenticdocRoot).readAll()).toEqual([]);
		verify("[VERIFY] T-22-2/5: unregistered_notice n=1 writes=0 index_rows=0");
	});

	it("the notice text is actionable and neutral (no 已拒绝)", () => {
		const text = formatDispatchAlarm({ kind: "out-of-scope", count: 1, detail: "never-owned" });
		expect(text).not.toContain("已拒绝");
		expect(text).toContain("提示");
		expect(text).toContain("never-owned");
		expect(text).toContain("switch_key");
		expect(text).toContain("dispatch_worker(key=<key>)");
		expect(text).toContain("{key}/workers/<task-key>/task.md");
		verify("[VERIFY] T-22-3: notice_actionable=1 refusal_wording=0");
	});

	it("with no watched key the notice stays suppressed and unburnt", async () => {
		const { agenticdocRoot } = mkWs();
		writeTask(agenticdocRoot, "never-owned", "n-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const warned = new Set<string>();

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			orphanedWarned: new Set<string>(),
			unregisteredWarned: warned,
			onAlarm: (a) => alarms.push(a),
		});

		expect(alarms).toEqual([]);
		// Suppressed, so the key did not burn its once-per-session slot.
		expect(warned.has("never-owned")).toBe(false);
		verify("[VERIFY] T-22-3: no_watch_notice_suppressed=1 slot_burnt=0");
	});
});
