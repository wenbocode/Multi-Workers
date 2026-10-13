/**
 * mwds-t19-orphan-ownership.test.ts — T-19 / AC-011 (key mw-dispatch-card-gate):
 * the ownership gap that left a conductor-driven project with nobody able to
 * re-dispatch its work.
 *
 * Contract under test:
 *   1. the dispatch scan is global and READ-ONLY, the WRITE right is scoped
 *      (watched key, `_scratch`, ORPHANED keys);
 *   2. ORPHANED = registered in `_index.parallel` ∧ undispatched work ∧ no live
 *      claim ∧ no live run; it raises an actionable, neutral-worded
 *      `orphaned-keys` notice (once per key per session);
 *   3. the repair dispatch is CLAIM-FREE: `_index.parallel` is byte-identical
 *      afterwards, so the conductor's only skip condition
 *      (`conductor.py`: `if claim == state.CLAIM_LIVE: … continue`) stays false;
 *   4. an old-form card is made dispatchable by the service-layer envelope
 *      skeleton, with an `[ENVELOPE_FALLBACK]` audit fact in trace.log.
 *
 * The conductor skip condition is asserted against the real Python source
 * (not only a TS mirror); fixtures are temp dirs, no provider APIs.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	type DispatchAlarm,
	dispatchNewTasks,
	ENVELOPE_FALLBACK_AUDIT,
	ENVELOPE_FALLBACK_MARKER,
	formatDispatchAlarm,
	repairDispatchOrphanedKey,
	synthesizeEnvelopeFallback,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	inspectEnvelope,
	readEnvelope,
	typeExtrasMissing,
} from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";
import { conductorClaimState, IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { type WorkerEntry, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const tempDirs: string[] = [];

/** `<tmp>/.agenticdoc` — the taskPath anchor `workerOwnerKey` needs
 * (`.agenticdoc/<key>/workers/<task>/task.md`). */
function mkWs(): { root: string; agenticdocRoot: string } {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-t19-"));
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

function indexText(agenticdocRoot: string): string {
	return fs.readFileSync(path.join(agenticdocRoot, "_index.parallel"), "utf8");
}

function writeTask(agenticdocRoot: string, key: string, taskKey: string, content = "type: coding\n\nbody\n"): string {
	const dir = path.join(agenticdocRoot, key, "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	const md = path.join(dir, "task.md");
	fs.writeFileSync(md, content, "utf8");
	return md;
}

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

/** `[VERIFY]` evidence line, written to real stdout (the vite config is
 * `silent: "passed-only"`, so `console.log` from a passing test is swallowed). */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

/** The conductor skip condition, verbatim from
 * `packages/multi-workers/autopilot/conductor.py`. */
function conductorSkipSource(): string {
	return fs.readFileSync(new URL("../../../multi-workers/autopilot/conductor.py", import.meta.url), "utf8");
}

// ── ORPHANED four states (AC-011) ───────────────────────────────────────────

describe("ORPHANED judgement (AC-011/T-19)", () => {
	it("registered + work + no live claim + no live run => ORPHANED: repaired and alerted", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "orphan", claimId: DEAD_CLAIM }]);
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const warned = new Set<string>();

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: warned,
			onAlarm: (a) => alarms.push(a),
		});

		// Repaired (claim-free) and alerted.
		expect(store.findByKey("o-1")?.status).toBe("pending");
		expect(warned.has("orphan")).toBe(true);
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([
			{ kind: "orphaned-keys", count: 1, detail: "orphan" },
		]);
		// The repair never wrote the claim.
		expect(new IndexStore(agenticdocRoot).findByKey("orphan")?.claimId).toBe(DEAD_CLAIM);
		verify("[VERIFY] AC-011: state=ORPHANED repaired=o-1 alarm=orphaned-keys claim_untouched=1");
	});

	it("a live run => NOT orphaned (no repair, no alert)", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "orphan", claimId: "—" }]);
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		await store.upsert(runningRow(agenticdocRoot, "orphan", "o-running"));
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.findByKey("o-1")).toBeUndefined();
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([]);
		verify("[VERIFY] AC-011: state=LIVE_RUN orphaned=0 repaired=0");
	});

	it("a live claim => NOT orphaned and never written", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "orphan", claimId: liveClaim() }]);
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const before = indexText(agenticdocRoot);

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.findByKey("o-1")).toBeUndefined();
		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([]);
		expect(indexText(agenticdocRoot)).toBe(before);
		verify("[VERIFY] AC-011: state=LIVE_CLAIM orphaned=0 writes=0");
	});

	it("no undispatched work => NOT orphaned (no alert)", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "quiet", claimId: "—" }]);
		fs.mkdirSync(path.join(agenticdocRoot, "quiet", "workers"), { recursive: true });
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toEqual([]);
		verify("[VERIFY] AC-011: state=NO_WORK orphaned=0");
	});

	it("alerts at most once per key per session", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "orphan", claimId: DEAD_CLAIM }]);
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];
		const warned = new Set<string>();
		const opts = {
			scope: "pm" as const,
			watchedKey: "watched",
			orphanedWarned: warned,
			onAlarm: (a: DispatchAlarm) => alarms.push(a),
		};

		await dispatchNewTasks(store, agenticdocRoot, opts);
		await dispatchNewTasks(store, agenticdocRoot, opts);

		expect(alarms.filter((a) => a.kind === "orphaned-keys")).toHaveLength(1);
		verify("[VERIFY] AC-011: orphaned_alerts_per_session=1");
	});

	it("an unregistered key with work is a read-only out-of-scope notice, never repaired", async () => {
		const { agenticdocRoot } = mkWs();
		writeTask(agenticdocRoot, "never-owned", "n-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(store.findByKey("n-1")).toBeUndefined();
		expect(alarms).toEqual([{ kind: "out-of-scope", count: 1, detail: "never-owned" }]);
		verify("[VERIFY] AC-011: unregistered=out-of-scope repaired=0");
	});

	it("with no watched key the out-of-scope notice is suppressed (never permanently lit)", async () => {
		const { agenticdocRoot } = mkWs();
		writeTask(agenticdocRoot, "never-owned", "n-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const alarms: DispatchAlarm[] = [];

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			orphanedWarned: new Set<string>(),
			onAlarm: (a) => alarms.push(a),
		});

		expect(alarms).toEqual([]);
		verify("[VERIFY] AC-011: no_watch out_of_scope_alarms=0");
	});
});

// ── Alarm wording by kind (AC-011) ──────────────────────────────────────────

describe("dispatch alarm wording (AC-011/T-19)", () => {
	it("only refusal kinds say 已拒绝; notices stay neutral", () => {
		for (const kind of ["out-of-scope", "orphaned-keys"] as const) {
			const text = formatDispatchAlarm({ kind, count: 2, detail: "k1,k2" });
			expect(text, kind).not.toContain("已拒绝");
			expect(text, kind).toContain("提示");
		}
		expect(formatDispatchAlarm({ kind: "dispatch-quota", count: 3 })).toContain("已拒绝");
		expect(formatDispatchAlarm({ kind: "queue-rows-unparsable", count: 1, detail: "cols" })).toContain("已拒绝");
		// The notice text is actionable: it names the keys.
		expect(formatDispatchAlarm({ kind: "orphaned-keys", count: 2, detail: "k1,k2" })).toContain("k1,k2");
		verify("[VERIFY] AC-011: refusal_prefix=已拒绝 notice_prefix=提示");
	});
});

// ── Claim-free repair + conductor eligibility (AC-011) ──────────────────────

describe("claim-free repair keeps the conductor eligible (AC-011/T-19)", () => {
	it("repair queues work without writing the claim; the conductor skip condition stays false", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "orphan", claimId: DEAD_CLAIM }]);
		writeTask(agenticdocRoot, "orphan", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const before = indexText(agenticdocRoot);

		const result = await repairDispatchOrphanedKey(store, agenticdocRoot, "orphan");

		expect(result.queued).toEqual(["o-1"]);
		expect(store.findByKey("o-1")?.status).toBe("pending");
		// The claim cell is byte-identical: the repair never touched
		// `_index.parallel`.
		expect(indexText(agenticdocRoot)).toBe(before);
		const row = new IndexStore(agenticdocRoot).findByKey("orphan");
		expect(row?.claimId).toBe(DEAD_CLAIM);
		expect(conductorClaimState(row?.claimId ?? "")).not.toBe("live");

		// The verdict is only meaningful against the real skip condition: the
		// conductor skips ONLY on CLAIM_LIVE, and state.py derives LIVE only for
		// "this host + pid alive" (a foreign host is explicitly DEAD).
		const conductor = conductorSkipSource();
		expect(conductor).toContain("if claim == state.CLAIM_LIVE:");
		const statePy = fs.readFileSync(new URL("../../../multi-workers/autopilot/state.py", import.meta.url), "utf8");
		expect(statePy).toContain("if m.group(1) != socket.gethostname():");
		expect(statePy).toContain("return CLAIM_LIVE if mw_common._is_alive(int(pid_text)) else CLAIM_DEAD");
		verify(
			`[VERIFY] AC-011: repaired=o-1 claim=${row?.claimId} conductor_claim_state=${conductorClaimState(
				row?.claimId ?? "",
			)} conductor_eligible=1`,
		);
	});

	it("a live claim is never repair-dispatched", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "owned", claimId: liveClaim() }]);
		writeTask(agenticdocRoot, "owned", "o-1", "type: coding\n\nwork\n");
		const store = new WorkerStore(agenticdocRoot);
		const before = indexText(agenticdocRoot);

		// Even the explicit primitive is scoped by the caller; the automatic scan
		// is the one that decides. Assert the SCAN refuses the write.
		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "pm",
			watchedKey: "watched",
			orphanedWarned: new Set<string>(),
		});
		expect(store.findByKey("o-1")).toBeUndefined();
		expect(indexText(agenticdocRoot)).toBe(before);
		// Sanity: this process's own pid is genuinely "live" to the conductor.
		expect(conductorClaimState(liveClaim())).toBe("live");
		verify("[VERIFY] AC-011: live_claim writer=0");
	});
});

// ── Old-form card: service-layer envelope synthesis (AC-011e) ───────────────

describe("old-form card repair via the service-layer envelope (AC-011e/T-14)", () => {
	const OLD_FORM = "# Task T-old\n\ntype: coding\n\n这个老卡没有任何规范节，只有一段正文。\n";

	it("synthesizeEnvelopeFallback mirrors the T-14 semantics (and fails closed)", () => {
		const synthesized = synthesizeEnvelopeFallback(OLD_FORM);
		expect(synthesized).not.toBeNull();
		const text = synthesized ?? "";
		expect(text.startsWith(OLD_FORM.trimEnd())).toBe(true);
		expect(text).toContain(ENVELOPE_FALLBACK_MARKER);
		expect(text).toContain(ENVELOPE_FALLBACK_AUDIT);
		expect(inspectEnvelope(text).ok).toBe(true);
		expect(typeExtrasMissing("coding", text)).toEqual([]);
		// Idempotent.
		expect(synthesizeEnvelopeFallback(text)).toBe(text);
		// Missing/unknown type: nothing to invent => fail closed.
		expect(synthesizeEnvelopeFallback("# old\n\n正文\n")).toBeNull();
		expect(synthesizeEnvelopeFallback("# old\n\ntype: bogus\n\n正文\n")).toBeNull();
		verify("[VERIFY] AC-011e: synthesis=ok idempotent=1 fail_closed=2");
	});

	it("repairs the old-form card, leaves an [ENVELOPE_FALLBACK] audit, and the launcher gate passes", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "orphan", claimId: "—" }]);
		const md = writeTask(agenticdocRoot, "orphan", "o-old", OLD_FORM);
		const taskDir = path.dirname(md);
		const store = new WorkerStore(agenticdocRoot);

		const result = await repairDispatchOrphanedKey(store, agenticdocRoot, "orphan");

		expect(result.synthesized).toEqual(["o-old"]);
		expect(result.queued).toEqual(["o-old"]);
		expect(result.unsynthesizable).toEqual([]);
		expect(store.findByKey("o-old")?.status).toBe("pending");

		const repaired = fs.readFileSync(md, "utf8");
		expect(repaired).toContain(ENVELOPE_FALLBACK_MARKER);
		expect(repaired).toContain(ENVELOPE_FALLBACK_AUDIT);
		expect(readEnvelope(md).ok).toBe(true);
		expect(typeExtrasMissing(readEnvelope(md).type, repaired)).toEqual([]);

		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		expect(trace).toContain(ENVELOPE_FALLBACK_AUDIT);
		expect(trace).toContain("kind=repair");
		verify("[VERIFY] AC-011e: old_form repaired=o-old audit=[ENVELOPE_FALLBACK] envelope_ok=1");
	});

	it("a card with no type: is reported unsynthesizable instead of silently dispatched", async () => {
		const { agenticdocRoot } = mkWs();
		writeIndex(agenticdocRoot, [{ key: "orphan", claimId: "—" }]);
		writeTask(agenticdocRoot, "orphan", "o-notype", "# old\n\n正文，无 type。\n");
		const store = new WorkerStore(agenticdocRoot);

		const result = await repairDispatchOrphanedKey(store, agenticdocRoot, "orphan");

		expect(result.queued).toEqual([]);
		expect(result.unsynthesizable).toEqual(["o-notype"]);
		expect(store.findByKey("o-notype")).toBeUndefined();
		verify("[VERIFY] AC-011e: no_type unsynthesizable=1 queued=0");
	});
});
