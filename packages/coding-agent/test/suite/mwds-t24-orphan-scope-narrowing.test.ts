/**
 * mwds-t24-orphan-scope-narrowing.test.ts — T-24 / C-30 (key
 * mw-dispatch-card-gate): the first automatic post-cutover repair run queued
 * THREE historical task dirs (`agent-team-loop/workers/ga-spec-review-1`,
 * `mw-dispatch-reliability/workers/mw-dr-glm53`, `mw-dr-keyed-probe`) and the
 * queue reaped them `done` within 4s, because those months-old dirs already had
 * `output.md`. Both keys were `idle` in `_index.parallel` with August Claim-Ids
 * (`20260808-174558-3176`, `20260828-160111-8496`).
 *
 * Two defects:
 *   1. the "undispatched work" criterion was too wide — "dir has `task.md` and
 *      the queue has no row" is naturally true for every historical dir;
 *   2. the owner evidence had no currency — a T-22 trace/row from August counted
 *      forever, turning a key idle for weeks into a repair target.
 *
 * T-24 narrows both. Contract under test:
 *   1. WORK (req. 1): a candidate is undispatched work only when
 *      (a) `task.md` exists, (b) `output.md` does NOT, and (c) — for a key that
 *      publishes state documents — the task-key is named by `pm-state.md` /
 *      `plan.md`;
 *   2. OWNER EVIDENCE (req. 2): current only when the index row status is not
 *      `idle`/`done`, or `pm-state.md`/`plan.md` moved within the freshness
 *      window, or the claim is conductor-`live`;
 *   3. an `idle`/`done` key with stale state docs is NEVER repaired: one
 *      neutral notice (key, judged work, why not repaired), 0 repairs, and both
 *      `_workers.parallel` and `_index.parallel` untouched;
 *   4. the T-19 claim-free positive path still repairs (an `active` row / fresh
 *      state trace), a live claim still writes nothing, and the notice is once
 *      per key per session.
 *
 * Fixtures ①② are the REAL C-30 corpus (index rows copied verbatim); state-doc
 * mtimes are pushed a year back so the currency verdict is clock-independent.
 * Temp dirs only, no provider APIs.
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
	type IndexEntry,
	IndexStore,
	ownerEvidenceCurrent,
} from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const tempDirs: string[] = [];

/** `<tmp>/.agenticdoc` — the taskPath anchor `workerOwnerKey` needs. */
function mkWs(): { root: string; agenticdocRoot: string } {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-t24-"));
	tempDirs.push(root);
	const agenticdocRoot = path.join(root, ".agenticdoc");
	fs.mkdirSync(agenticdocRoot, { recursive: true });
	return { root, agenticdocRoot };
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Verbatim C-30 index rows (`.agenticdoc/_index.parallel`, observed
 * 2026-10-13 after the cutover's first automatic repair run). */
const REAL_INDEX_ROWS: Record<string, string> = {
	"agent-team-loop":
		"| agent-team-loop | idle | EXECUTE | 20260808-174558-3176 | — | Agent Team Loop: multi-CLI worker orchestration (pi/codex/claude) via AgenticTask PM + timi-proxy routing | 2026-09-07T12:05:36.859Z |",
	"mw-dispatch-reliability":
		"| mw-dispatch-reliability | idle | EXECUTE | 20260828-160111-8496 | — | Fix multi-worker dispatch availability (per-task credential failure isolation, stale entry cleanup) and build debug/test system (mw doctor, L0/L1/L2 tests) | 2026-09-07T12:05:36.859Z |",
};

function writeIndexRows(agenticdocRoot: string, rows: string[]): void {
	const lines = [
		"# Index Parallel",
		"",
		"| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
		"| --- | --- | --- | --- | --- | --- | --- |",
		...rows,
	];
	fs.writeFileSync(path.join(agenticdocRoot, "_index.parallel"), `${lines.join("\n")}\n`, "utf8");
}

/** `_index.parallel` bytes, or `null` when the file does not exist. */
function indexText(agenticdocRoot: string): string | null {
	const file = path.join(agenticdocRoot, "_index.parallel");
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
}

/** `_workers.parallel` bytes, or `null` when the file does not exist — the
 * "0 rows written" primitive the C-30 regression pins on. */
function workerText(agenticdocRoot: string): string | null {
	const file = path.join(agenticdocRoot, "_workers.parallel");
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
}

interface TaskDirOpts {
	output?: boolean;
	trace?: boolean;
	taskContent?: string;
}

function writeTaskDir(
	agenticdocRoot: string,
	key: string,
	taskKey: string,
	opts: TaskDirOpts = {},
): { dir: string; md: string } {
	const dir = path.join(agenticdocRoot, key, "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	const md = path.join(dir, "task.md");
	fs.writeFileSync(md, opts.taskContent ?? "type: coding\n\nwork\n", "utf8");
	if (opts.output) fs.writeFileSync(path.join(dir, "output.md"), "# output\n", "utf8");
	if (opts.trace) fs.writeFileSync(path.join(dir, "trace.log"), "[START] pid=1\n", "utf8");
	return { dir, md };
}

/** `pm-state.md` (always) and `plan.md` (when given), with the machine
 * interface lines a real owner writes. `old` pushes BOTH mtimes a year back so
 * the T-24 currency verdict does not depend on the wall clock. */
function writeStateDocs(
	agenticdocRoot: string,
	key: string,
	opts: { pmState: string; plan?: string; old?: boolean },
): void {
	const keyDir = path.join(agenticdocRoot, key);
	fs.mkdirSync(keyDir, { recursive: true });
	const pm = path.join(keyDir, "pm-state.md");
	fs.writeFileSync(pm, opts.pmState, "utf8");
	const docs = [pm];
	if (opts.plan !== undefined) {
		const plan = path.join(keyDir, "plan.md");
		fs.writeFileSync(plan, opts.plan, "utf8");
		docs.push(plan);
	}
	if (opts.old) {
		const old = new Date(Date.now() - 365 * 24 * 60 * 60 * 1000);
		for (const doc of docs) fs.utimesSync(doc, old, old);
	}
}

const PM_STATE_OLD = (key: string, claimId: string): string =>
	`# PM State: ${key}\n\n- Key: ${key}\n- Claim-Id: ${claimId}\n- Phase: EXECUTE\n`;

/** `[VERIFY]` evidence line on real stdout (vite silent:"passed-only" swallows
 * `console.log` from passing tests). */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

function row(status: string, claimId = "20260808-174558-3176"): IndexEntry {
	return {
		key: "k",
		status: status as IndexEntry["status"],
		phase: "EXECUTE",
		claimId,
		deps: "",
		desc: "",
		updated: "",
	};
}

function pmOpts(alarms: DispatchAlarm[], orphanedWarned: Set<string>, unregisteredWarned = new Set<string>()) {
	return {
		scope: "pm" as const,
		watchedKey: "watched",
		orphanedWarned,
		unregisteredWarned,
		onAlarm: (a: DispatchAlarm) => alarms.push(a),
	};
}

// ── ①② C-30 real corpus: idle + August claim + terminal dirs => notice only ──

describe("C-30 real corpus: idle key with historical dirs is never repaired", () => {
	it("① agent-team-loop: idle + 20260808 claim + ga-spec-review-1 with output.md => notice only, 0 writes", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndexRows(agenticdocRoot, [REAL_INDEX_ROWS["agent-team-loop"]]);
		writeStateDocs(agenticdocRoot, "agent-team-loop", {
			pmState: PM_STATE_OLD("agent-team-loop", "20260808-174558-3176"),
			plan: "# Plan: agent-team-loop\n\n- historical plan body\n",
			old: true,
		});
		const { dir, md } = writeTaskDir(agenticdocRoot, "agent-team-loop", "ga-spec-review-1", {
			output: true,
			taskContent: "type: coding\n\nReview the spec at .agenticdoc/goal-autopilot/spec.md\n",
		});
		const taskBefore = fs.readFileSync(md, "utf8");
		const indexBefore = indexText(agenticdocRoot);
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, pmOpts(alarms, new Set<string>()));

		// Req. 3: 0 repairs, 0 queue rows.
		expect(store.findByKey("ga-spec-review-1")).toBeUndefined();
		expect(workerText(agenticdocRoot)).toBeNull();
		// Req. 3: `_index.parallel` is byte-identical (the repair path must never
		// write it; the blocked path must never write anything).
		expect(indexText(agenticdocRoot)).toBe(indexBefore);
		// Req. 3: exactly one neutral notice naming key + judged work + reason.
		const skipped = alarms.filter((a) => a.kind === "orphan-repair-skipped");
		expect(skipped).toHaveLength(1);
		expect(skipped[0].count).toBe(1);
		expect(skipped[0].detail).toContain("agent-team-loop");
		expect(skipped[0].detail).toContain("ga-spec-review-1");
		expect(skipped[0].detail).toContain("idle");
		// Never the "repaired" kind, never a refusal kind.
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([]);
		expect(alarms.filter((a) => a.kind === "out-of-scope")).toEqual([]);
		// No task-dir mutation: the envelope fallback would have rewritten
		// task.md and appended trace.log (exactly the pre-T-24 C-30 damage).
		expect(fs.readFileSync(md, "utf8")).toBe(taskBefore);
		expect(fs.existsSync(path.join(dir, "trace.log"))).toBe(false);
		verify(
			"[VERIFY] T-24-1: key=agent-team-loop status=idle claim=20260808-174558-3176 work=[ga-spec-review-1] repaired=0 queue_written=0 index_bytes_unchanged=1 notice=orphan-repair-skipped",
		);
	});

	it("② mw-dispatch-reliability: idle + 20260828 claim + mw-dr-glm53/mw-dr-keyed-probe with output.md => notice only, 0 writes", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndexRows(agenticdocRoot, [REAL_INDEX_ROWS["mw-dispatch-reliability"]]);
		writeStateDocs(agenticdocRoot, "mw-dispatch-reliability", {
			pmState: PM_STATE_OLD("mw-dispatch-reliability", "20260828-160111-8496"),
			plan: "# Plan: mw-dispatch-reliability\n\n- historical plan body\n",
			old: true,
		});
		const a = writeTaskDir(agenticdocRoot, "mw-dispatch-reliability", "mw-dr-glm53", { output: true });
		const b = writeTaskDir(agenticdocRoot, "mw-dispatch-reliability", "mw-dr-keyed-probe", { output: true });
		const before = [fs.readFileSync(a.md, "utf8"), fs.readFileSync(b.md, "utf8")];
		const indexBefore = indexText(agenticdocRoot);
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, pmOpts(alarms, new Set<string>()));

		expect(store.findByKey("mw-dr-glm53")).toBeUndefined();
		expect(store.findByKey("mw-dr-keyed-probe")).toBeUndefined();
		expect(workerText(agenticdocRoot)).toBeNull();
		expect(indexText(agenticdocRoot)).toBe(indexBefore);
		const skipped = alarms.filter((k) => k.kind === "orphan-repair-skipped");
		expect(skipped).toHaveLength(1);
		expect(skipped[0].count).toBe(1);
		for (const taskKey of ["mw-dr-glm53", "mw-dr-keyed-probe"]) {
			expect(skipped[0].detail).toContain(taskKey);
		}
		expect(skipped[0].detail).toContain("idle");
		expect(alarms.filter((k) => k.kind === "orphaned-keys")).toEqual([]);
		expect(fs.readFileSync(a.md, "utf8")).toBe(before[0]);
		expect(fs.readFileSync(b.md, "utf8")).toBe(before[1]);
		expect(fs.existsSync(path.join(a.dir, "trace.log"))).toBe(false);
		expect(fs.existsSync(path.join(b.dir, "trace.log"))).toBe(false);
		verify(
			"[VERIFY] T-24-2: key=mw-dispatch-reliability status=idle claim=20260828-160111-8496 work=[mw-dr-glm53,mw-dr-keyed-probe] repaired=0 queue_written=0 index_bytes_unchanged=1 notice=orphan-repair-skipped",
		);
	});

	it("⑤ the skipped notice is once per key per session", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndexRows(agenticdocRoot, [REAL_INDEX_ROWS["agent-team-loop"]]);
		writeStateDocs(agenticdocRoot, "agent-team-loop", {
			pmState: PM_STATE_OLD("agent-team-loop", "20260808-174558-3176"),
			plan: "# Plan\n",
			old: true,
		});
		writeTaskDir(agenticdocRoot, "agent-team-loop", "ga-spec-review-1", { output: true });
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const opts = pmOpts(alarms, new Set<string>());

		// Two ticks of the same session (same dedup sets).
		await dispatchNewTasks(store, agenticdocRoot, opts);
		await dispatchNewTasks(store, agenticdocRoot, opts);

		expect(alarms.filter((a) => a.kind === "orphan-repair-skipped")).toHaveLength(1);
		verify("[VERIFY] T-24-5: skipped_notice_per_key_per_session=1");
	});
});

// ── ③ positive: current owner evidence + narrowed work still repairs ────────

describe("positive repairs still work (T-19/T-22 path unchanged)", () => {
	it("③ active row + fresh state + referenced work => claim-free repair, `_index.parallel` unchanged", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndexRows(agenticdocRoot, [
			"| fresh-key | active | EXECUTE | other-host:4242 | — | live owner | 2026-10-12T00:00:00Z |",
		]);
		writeStateDocs(agenticdocRoot, "fresh-key", {
			pmState:
				"# PM State: fresh-key\n\n- Key: fresh-key\n- Claim-Id: other-host:4242\n- Phase: EXECUTE\n\n## Tasks\n- p-1: in flight\n",
		});
		writeTaskDir(agenticdocRoot, "fresh-key", "p-1", { taskContent: "type: coding\n\nwork\n" });
		const indexBefore = indexText(agenticdocRoot);
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const warned = new Set<string>();

		await dispatchNewTasks(store, agenticdocRoot, pmOpts(alarms, warned));

		expect(store.findByKey("p-1")?.status).toBe("pending");
		expect(indexText(agenticdocRoot)).toBe(indexBefore);
		expect(new IndexStore(agenticdocRoot).findByKey("fresh-key")?.claimId).toBe("other-host:4242");
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([
			{ kind: "orphaned-keys", count: 1, detail: "fresh-key" },
		]);
		expect(alarms.filter((a) => a.kind === "orphan-repair-skipped")).toEqual([]);
		verify("[VERIFY] T-24-3: case=positive_active_row repaired=p-1 index_bytes_unchanged=1 claim=other-host:4242");
	});

	it("④ a live claim => writer=0 (AC-019 unchanged)", async () => {
		const { agenticdocRoot } = mkWs();
		const live = `${os.hostname()}:${process.pid}`;
		writeIndexRows(agenticdocRoot, [
			`| owned | active | EXECUTE | ${live} | — | live owner | 2026-10-12T00:00:00Z |`,
		]);
		writeStateDocs(agenticdocRoot, "owned", {
			pmState: PM_STATE_OLD("owned", live),
			plan: "# Plan\n- o-1\n",
			old: true,
		});
		writeTaskDir(agenticdocRoot, "owned", "o-1");
		const indexBefore = indexText(agenticdocRoot);
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, pmOpts(alarms, new Set<string>()));

		expect(store.findByKey("o-1")).toBeUndefined();
		expect(workerText(agenticdocRoot)).toBeNull();
		expect(indexText(agenticdocRoot)).toBe(indexBefore);
		expect(alarms).toEqual([]);
		verify("[VERIFY] T-24-4: live_claim writer=0 index_bytes_unchanged=1 alarms=0");
	});

	it("req 1b: a never-owned key whose only dir is terminal raises no notice", async () => {
		const { agenticdocRoot } = mkWs();
		writeTaskDir(agenticdocRoot, "never-owned", "n-1", { output: true });
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const unregisteredWarned = new Set<string>();

		await dispatchNewTasks(store, agenticdocRoot, pmOpts(alarms, new Set<string>(), unregisteredWarned));

		expect(alarms).toEqual([]);
		expect(unregisteredWarned.has("never-owned")).toBe(false);
		expect(workerText(agenticdocRoot)).toBeNull();
		verify("[VERIFY] T-24-1b: never_owned_terminal_only out_of_scope=0 writes=0");
	});
});

// ── owner-evidence currency predicate (req. 2) ──────────────────────────────

describe("owner evidence currency (T-24 req. 2)", () => {
	it("idle/done rows with stale state docs are not current; active/fresh/no-docs are", () => {
		const { agenticdocRoot } = mkWs();
		// No state docs at all: the durable row/trace is the only evidence
		// (T-19/T-22 semantics) — remains current.
		expect(ownerEvidenceCurrent(agenticdocRoot, "bare", row("idle"))).toMatchObject({
			current: true,
			hasStateDocs: false,
		});
		// Stale state docs + idle row: C-30's shape — not current.
		writeStateDocs(agenticdocRoot, "stale-idle", {
			pmState: PM_STATE_OLD("stale-idle", "20260808-174558-3176"),
			plan: "# Plan\n",
			old: true,
		});
		const idleVerdict = ownerEvidenceCurrent(agenticdocRoot, "stale-idle", row("idle"));
		expect(idleVerdict.current).toBe(false);
		expect(idleVerdict.hasStateDocs).toBe(true);
		expect(idleVerdict.reason).toContain("idle");
		// Terminal `done` is never repairable either.
		expect(ownerEvidenceCurrent(agenticdocRoot, "stale-idle", row("done")).current).toBe(false);
		// An `active` row is a live owner even with stale docs.
		expect(ownerEvidenceCurrent(agenticdocRoot, "stale-idle", row("active")).current).toBe(true);
		// A fresh state document is current even with an idle row.
		writeStateDocs(agenticdocRoot, "fresh", {
			pmState: PM_STATE_OLD("fresh", "20260808-174558-3176"),
		});
		expect(ownerEvidenceCurrent(agenticdocRoot, "fresh", row("idle")).current).toBe(true);
		// Stale docs + no row: reason names the missing row, not a status.
		expect(ownerEvidenceCurrent(agenticdocRoot, "stale-idle", undefined).reason).toContain("无 index 行");
		verify(
			"[VERIFY] T-24-2: no_docs=current stale_idle=not_current done=not_current active=current fresh_state=current",
		);
	});

	it("the currency predicate is read-only against both index files", () => {
		const { agenticdocRoot } = mkWs();
		writeStateDocs(agenticdocRoot, "stale-idle", { pmState: PM_STATE_OLD("stale-idle", "—"), old: true });
		expect(indexText(agenticdocRoot)).toBeNull();
		expect(workerText(agenticdocRoot)).toBeNull();
		ownerEvidenceCurrent(agenticdocRoot, "stale-idle", row("idle"));
		expect(indexText(agenticdocRoot)).toBeNull();
		expect(workerText(agenticdocRoot)).toBeNull();
		verify("[VERIFY] T-24-2: predicate_writes_index=0 predicate_writes_queue=0");
	});
});

// ── notice wording (req. 3) ─────────────────────────────────────────────────

describe("skipped-repair notice wording (T-24 req. 3)", () => {
	it("is a neutral notice (no 已拒绝) naming key, judged work and reason", () => {
		const text = formatDispatchAlarm({
			kind: "orphan-repair-skipped",
			count: 1,
			detail: "agent-team-loop(工作=[ga-spec-review-1]; 原因=index 状态 idle)",
		});
		expect(text).toContain("提示");
		expect(text).not.toContain("已拒绝");
		expect(text).toContain("agent-team-loop");
		expect(text).toContain("ga-spec-review-1");
		expect(text).toContain("index 状态 idle");
		verify("[VERIFY] T-24-3: notice=提示 refusal_wording=0 names_key_work_reason=1");
	});
});
