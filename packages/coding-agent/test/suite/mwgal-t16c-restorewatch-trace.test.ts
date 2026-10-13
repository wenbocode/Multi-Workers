/**
 * mwgal-t16c-restorewatch-trace.test.ts — T-16c / key
 * `mw-autopilot-gate-alarm-liveness` (card T-16c-restorewatch-trace).
 *
 * Gap (T-16b self-reported R-2): `pm-orchestrator.ts::restoreWatch` re-claims a
 * key held by THIS host's autopilot conductor (`held-conductor`, T-16b) when a
 * window restarts. The direction is right — human priority, the conductor
 * yields (T-16/T-16b) — but the takeover was SILENT: an operator could not
 * explain afterwards why that key stopped being dispatched by the conductor.
 *
 * Requirements (card):
 *   1. the handover must leave a VISIBLE record on an existing surface (no new
 *      timeline event name; the timeline has a single writer — the conductor);
 *   2. precedence unchanged: the human wins and the conductor never reclaims;
 *   3. a key truly held by another LIVE window (`held-live`) keeps the old
 *      restoreWatch behavior (no silent seizure, no trace beyond "watching
 *      only");
 *   4. idempotent: restarting again never duplicates the trace;
 *   5. regression coverage for 1-4, and T-16b's 8 cases stay green.
 *
 * Chosen surfaces (see report): the `_index.parallel` Claim cell (already
 * flipped, plus its pm-state.md mirror), the EXISTING `agent-team-loop:watch`
 * session entry shape carrying `tookOverFromConductor`, and one passive
 * transcript notice over the existing `displaySummary` channel. No new event
 * name, no new entry type, no timeline write.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import { restoreWatch } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import { type PmWatchState, windowClaimId } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import {
	IndexStore,
	SYNTHETIC_CLAIM_PREFIX,
	syntheticClaimLive,
} from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const ORCHESTRATOR_PATH = path.join(TEST_DIR, "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts");
const WATCH_ENTRY_TYPE = "agent-team-loop:watch";

const tempDirs: string[] = [];
const livePids: number[] = [];

afterEach(async () => {
	for (const pid of livePids.splice(0)) {
		try {
			process.kill(pid);
		} catch {
			// already gone
		}
	}
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwgal-t16c-"));
	tempDirs.push(dir);
	return dir;
}

/** Spawn a live pid — the stand-in for the live conductor behind a synthetic
 * claim. `stop()` waits for the exit so the pid is unambiguously dead. */
function spawnChild(): Promise<{ pid: number; stop: () => Promise<void> }> {
	const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 60000)"]);
	if (child.pid === undefined) throw new Error("spawn failed");
	const pid = child.pid;
	livePids.push(pid);
	return new Promise((resolve) => {
		child.on("spawn", () =>
			resolve({
				pid,
				stop: () =>
					new Promise<void>((done) => {
						if (child.exitCode !== null) return done();
						child.on("exit", () => done());
						child.kill();
					}),
			}),
		);
	});
}

function syntheticClaim(pid: number, host = os.hostname()): string {
	return `${SYNTHETIC_CLAIM_PREFIX}${host}:${pid}`;
}

async function seedKey(root: string, key: string, claimId: string): Promise<void> {
	await new IndexStore(root).upsert({
		key,
		status: "active",
		phase: "EXECUTE",
		claimId,
		deps: "",
		desc: "",
		updated: new Date().toISOString(),
	});
}

/** pm-state.md with both machine-interface lines, so the D-108 claim mirror
 * sync can be asserted as an existing state surface. */
function seedPmState(root: string, key: string): string {
	const file = path.join(root, key, "pm-state.md");
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(
		file,
		`# PM State: ${key}\n\n- Key: ${key}\n- Claim-Id: cid-old\n- Phase: EXECUTE\n\n## Notes\n`,
		"utf8",
	);
	return file;
}

interface FakePi {
	pi: ExtensionAPI;
	entries: Array<{ customType: string; data: unknown }>;
	/** content of every displaySummary/sendMessage payload. */
	sent: string[];
	/** true when a sendMessage call carried options (turn-triggering channel). */
	triggered: boolean[];
}

function fakePi(): FakePi {
	const entries: Array<{ customType: string; data: unknown }> = [];
	const sent: string[] = [];
	const triggered: boolean[] = [];
	const pi = {
		appendEntry: (customType: string, data: unknown) => {
			entries.push({ customType, data });
		},
		sendMessage: (message: unknown, options?: unknown) => {
			sent.push(typeof message === "string" ? message : ((message as { content?: string }).content ?? ""));
			triggered.push(options !== undefined);
		},
	} as unknown as ExtensionAPI;
	return { pi, entries, sent, triggered };
}

interface FakeCtx {
	ctx: ExtensionContext;
	notifications: string[];
}

function fakeCtx(entries: Array<{ customType: string; data: unknown }>): FakeCtx {
	const notifications: string[] = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string) => notifications.push(message),
			setWidget: () => {},
		},
		sessionManager: {
			getEntries: () => entries.map((e) => ({ type: "custom", customType: e.customType, data: e.data })),
		},
	} as unknown as ExtensionContext;
	return { ctx, notifications };
}

function restoreEntries(key: string): Array<{ customType: string; data: unknown }> {
	return [{ customType: WATCH_ENTRY_TYPE, data: { key, claimed: true } }];
}

function watchEntryOf(fake: FakePi): { key?: string; claimed?: boolean; tookOverFromConductor?: string } | undefined {
	const entry = fake.entries.filter((e) => e.customType === WATCH_ENTRY_TYPE).at(-1);
	return entry?.data as { key?: string; claimed?: boolean; tookOverFromConductor?: string } | undefined;
}

function traceCount(entries: Array<{ customType: string; data: unknown }>): number {
	return entries.filter(
		(e) => e.customType === WATCH_ENTRY_TYPE && (e.data as { tookOverFromConductor?: string }).tookOverFromConductor,
	).length;
}

function conductorTakeoverMessages(sent: string[]): string[] {
	return sent.filter((m) => m.includes("conductor") && m.includes("窗口重启恢复"));
}

// ── requirement 1: the handover leaves a visible record ─────────────────────

describe("restoreWatch: taking a conductor-held key back is traced (T-16c req 1)", () => {
	it("claims the held-conductor key and records the handover on existing surfaces", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const ws = new WorkerStore(root);
		const conductor = await spawnChild();
		const synthetic = syntheticClaim(conductor.pid);
		await seedKey(root, "key-a", synthetic);
		const pmState = seedPmState(root, "key-a");

		const fake = fakePi();
		const shell = fakeCtx(restoreEntries("key-a"));
		const watch: PmWatchState = { key: undefined };
		await restoreWatch(fake.pi, watch, is, ws, new AckStore(root), root, shell.ctx);

		// Human priority: the claim is now this window's (T-16b precedence kept).
		expect(watch.key).toBe("key-a");
		expect(is.findByKey("key-a")?.claimId).toBe(windowClaimId());
		expect(syntheticClaimLive(synthetic)).toBe(true); // the conductor was live throughout
		// Existing state surface: the D-108 pm-state.md claim mirror follows the row.
		expect(fs.readFileSync(pmState, "utf8")).toContain(`- Claim-Id: ${windowClaimId()}`);
		expect(fs.readFileSync(pmState, "utf8")).not.toContain("cid-old");

		// Act record: the EXISTING watch entry shape, one extra field only.
		expect(fake.entries).toHaveLength(1);
		const entry = watchEntryOf(fake);
		expect(entry?.tookOverFromConductor).toBe(synthetic);
		// No new event/entry vocabulary: the whole restore writes only watch entries.
		expect(fake.entries.every((e) => e.customType === WATCH_ENTRY_TYPE)).toBe(true);

		// Visible record: the passive transcript notice names key / previous holder / new holder.
		const notices = conductorTakeoverMessages(fake.sent);
		expect(notices).toHaveLength(1);
		expect(notices[0]).toContain("key-a");
		expect(notices[0]).toContain(synthetic);
		expect(notices[0]).toContain(windowClaimId());
		// Passive channel: displaySummary never triggers an agent turn.
		expect(fake.triggered.every((t) => t === false)).toBe(true);

		console.log(
			`[VERIFY] T-16c req1: claimed=1 trace_entries=${traceCount(fake.entries)} notices=${notices.length} ` +
				`mirror=${fs.readFileSync(pmState, "utf8").includes(windowClaimId())} new_entry_types=0`,
		);
	}, 20000);
});

// ── requirement 3: held-live behavior is untouched ──────────────────────────

describe("restoreWatch: another live window's key stays untouched (T-16c req 3)", () => {
	it("does not seize a held-live claim and leaves no takeover trace", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const ws = new WorkerStore(root);
		const human = await spawnChild();
		const foreign = `${os.hostname()}:${human.pid}`;
		await seedKey(root, "key-b", foreign);

		const fake = fakePi();
		const shell = fakeCtx(restoreEntries("key-b"));
		const watch: PmWatchState = { key: undefined };
		await restoreWatch(fake.pi, watch, is, ws, new AckStore(root), root, shell.ctx);

		expect(watch.key).toBe("key-b"); // watch-only
		expect(is.findByKey("key-b")?.claimId).toBe(foreign); // shared row untouched
		expect(shell.notifications.some((n) => n.includes("watching only"))).toBe(true);
		expect(shell.notifications.some((n) => n.includes("conductor"))).toBe(false);
		// No unauthorised trace: no notice, no `tookOverFromConductor` field.
		expect(conductorTakeoverMessages(fake.sent)).toHaveLength(0);
		expect(watchEntryOf(fake)?.tookOverFromConductor).toBeUndefined();
		expect(traceCount(fake.entries)).toBe(0);
		console.log("[VERIFY] T-16c req3: claim_untouched=1 watching_only=1 trace=0");
	}, 20000);
});

// ── requirement 4: idempotence across repeated restarts ─────────────────────

describe("restoreWatch: the handover trace never duplicates (T-16c req 4)", () => {
	it("restarting twice leaves exactly one trace (the second restart is a quiet re-claim)", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const ws = new WorkerStore(root);
		const conductor = await spawnChild();
		const synthetic = syntheticClaim(conductor.pid);
		await seedKey(root, "key-c", synthetic);

		// Restart 1: conductor-held → claim + trace.
		const first = fakePi();
		const firstCtx = fakeCtx(restoreEntries("key-c"));
		await restoreWatch(first.pi, { key: undefined }, is, ws, new AckStore(root), root, firstCtx.ctx);
		expect(traceCount(first.entries)).toBe(1);

		// Restart 2: the session now carries restart 1's entry; the row is this
		// window's (same process identity) → quiet re-claim, no second trace.
		const second = fakePi();
		const secondCtx = fakeCtx(first.entries);
		await restoreWatch(second.pi, { key: undefined }, is, ws, new AckStore(root), root, secondCtx.ctx);

		expect(is.findByKey("key-c")?.claimId).toBe(windowClaimId());
		expect(traceCount(second.entries)).toBe(0);
		expect(watchEntryOf(second)?.tookOverFromConductor).toBeUndefined();
		expect(conductorTakeoverMessages(second.sent)).toHaveLength(0);
		// Exactly one act record across both restarts.
		expect(traceCount([...first.entries, ...second.entries])).toBe(1);
		console.log("[VERIFY] T-16c req4: trace_total=1 second_restart_trace=0");
	}, 30000);
});

// ── requirement 3 (scoping): held-stale stays quiet ─────────────────────────

describe("restoreWatch: only held-conductor is traced (T-16c req 3 scoping)", () => {
	it("a dead conductor's stale synthetic claim is re-claimed quietly, with no trace", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const ws = new WorkerStore(root);
		const conductor = await spawnChild();
		const synthetic = syntheticClaim(conductor.pid);
		await conductor.stop();
		expect(syntheticClaimLive(synthetic)).toBe(false);
		await seedKey(root, "key-d", synthetic);

		const fake = fakePi();
		const shell = fakeCtx(restoreEntries("key-d"));
		await restoreWatch(fake.pi, { key: undefined }, is, ws, new AckStore(root), root, shell.ctx);

		expect(is.findByKey("key-d")?.claimId).toBe(windowClaimId());
		expect(traceCount(fake.entries)).toBe(0);
		expect(conductorTakeoverMessages(fake.sent)).toHaveLength(0);
		expect(watchEntryOf(fake)?.tookOverFromConductor).toBeUndefined();
		console.log("[VERIFY] T-16c scoping: stale_reclaim=quiet trace=0");
	}, 20000);
});

// ── requirement 1 (shape): no new event vocabulary, no timeline writer ──────

describe("trace shape: existing surfaces only (T-16c req 1)", () => {
	it("restoreWatch writes the existing watch entry type and never the conductor-only timeline", () => {
		const source = fs.readFileSync(ORCHESTRATOR_PATH, "utf8");
		const at = source.indexOf("let tookOverFromConductor");
		expect(at).toBeGreaterThan(-1);
		const body = source.slice(at, at + 4000);
		// The act record reuses the watch entry and the displaySummary channel.
		expect(body).toContain("tookOverFromConductor");
		expect(body).toContain("displaySummary(");
		// No new timeline vocabulary and no second timeline writer (D-109).
		expect(body).not.toContain("timeline.append");
		expect(body).not.toContain("timeline.jsonl");
		expect(source).not.toContain("timeline.append");
		console.log("[VERIFY] T-16c req1: reuse_watch_entry=1 timeline_writers=0");
	});
});
