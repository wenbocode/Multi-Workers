/**
 * mwgal-t16b-takeover-yield.test.ts — T-16b / key
 * `mw-autopilot-gate-alarm-liveness` (card T-16b-takeover-yield).
 *
 * Gap: T-16 self-reported it as R-1. `ui-bridge.ts::claimState` judged EVERY
 * external-host claim `held-live`, so the synthetic claim T-16 introduced
 * (`autopilot@<host>:<pid>`) made a plain human `switch_key` fail without
 * `--force`. The conductor side was already correct — it yields to a human
 * claim and never fights back (T-16 `maintain_synthetic_claims` +
 * `_trace_human_hold`, existing `skip` event; Python VC-3) — the broken half
 * was the TAKEOVER guard's holder verdict.
 *
 * Requirements (card):
 *   1. a THIS-host conductor synthetic claim is yieldable: a non-forced human
 *      takeover must succeed;
 *   2. a claim held by another LIVE window still needs `--force` (no widening
 *      of the cross-window guard);
 *   3. the yield leaves T-16's existing trace shape (no new event name);
 *   4. the synthetic verdict reuses index-store.ts's parser — the `autopilot@`
 *      shape is never re-implemented in ui-bridge.ts;
 *   5. regression coverage for 1-4.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import {
	CROSS_KEY_READ_ONLY,
	claimState,
	foreignLiveClaimRefusal,
	type PmWatchState,
	registerPmKeyCommands,
	registerSwitchKeyTool,
	resolveOwnerKeyWithSync,
	takeOverKey,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	IndexStore,
	isSyntheticClaimId,
	parseSyntheticClaim,
	SYNTHETIC_CLAIM_PREFIX,
	syntheticClaimLive,
} from "../../src/extensions/agent-team-loop/shared/index-store.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const UI_BRIDGE_PATH = path.join(TEST_DIR, "../../src/extensions/agent-team-loop/pm/ui-bridge.ts");

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
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwgal-t16b-"));
	tempDirs.push(dir);
	return dir;
}

/** Spawn a short-lived child and wait until its pid is observable — the
 * stand-in for a live window / live conductor pid in claim-state tests. */
function spawnLivePid(): Promise<number> {
	const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 15000)"]);
	if (child.pid === undefined) throw new Error("spawn failed");
	const pid = child.pid;
	livePids.push(pid);
	return new Promise((resolve) => {
		child.on("spawn", () => resolve(pid));
		setTimeout(() => resolve(pid), 500);
	});
}

async function seedKey(
	root: string,
	key: string,
	claimId: string,
	status: "active" | "idle" = "active",
): Promise<void> {
	await new IndexStore(root).upsert({
		key,
		status,
		phase: "EXECUTE",
		claimId,
		deps: "",
		desc: "",
		updated: new Date().toISOString(),
	});
}

function syntheticClaim(pid: number, host = os.hostname()): string {
	return `${SYNTHETIC_CLAIM_PREFIX}${host}:${pid}`;
}

interface FakePi {
	pi: ExtensionAPI;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
	tools: Map<
		string,
		{ execute: (id: string, params: unknown) => Promise<{ content: Array<{ type: string; text: string }> }> }
	>;
	entries: Array<{ customType: string; data: unknown }>;
	sent: string[];
}

function fakePi(): FakePi {
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const tools = new Map<
		string,
		{ execute: (id: string, params: unknown) => Promise<{ content: Array<{ type: string; text: string }> }> }
	>();
	const entries: Array<{ customType: string; data: unknown }> = [];
	const sent: string[] = [];
	const pi = {
		registerCommand: (
			name: string,
			opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, opts.handler);
		},
		registerTool: (tool: {
			name: string;
			execute: (id: string, params: unknown) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}) => {
			tools.set(tool.name, tool);
		},
		appendEntry: (customType: string, data: unknown) => {
			entries.push({ customType, data });
		},
		sendMessage: (m: unknown) => {
			sent.push(typeof m === "string" ? m : ((m as { content?: string }).content ?? ""));
		},
	} as unknown as ExtensionAPI;
	return { pi, commands, tools, entries, sent };
}

function fakeCmdCtx(): { ctx: ExtensionCommandContext; notifications: string[] } {
	const notifications: string[] = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string) => notifications.push(message),
			setWidget: () => {},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

// ── requirement 1/4: the holder verdict ─────────────────────────────────────

describe("claimState: the conductor's synthetic claim is a yieldable holder (T-16b req 1 + 4)", () => {
	it("classifies a THIS-host synthetic claim as held-conductor, everything else by the old rules", async () => {
		const self = windowClaimId();
		const pid = await spawnLivePid();
		const local = syntheticClaim(pid);

		// The shared index-store parser is the single source for the shape.
		expect(parseSyntheticClaim(local)).toEqual({ host: os.hostname(), pid });
		expect(isSyntheticClaimId(local)).toBe(true);
		expect(syntheticClaimLive(local)).toBe(true);
		expect(claimState(local, self)).toBe("held-conductor");

		// A synthetic claim from ANOTHER host is that machine's conductor: not
		// yieldable, the ordinary foreign-host rule applies (--force needed).
		expect(claimState(syntheticClaim(pid, "other-host"), self)).toBe("held-live");
		// A malformed prefix is never silently adopted as a synthetic claim.
		expect(claimState(`${SYNTHETIC_CLAIM_PREFIX}${os.hostname()}:not-a-pid`, self)).toBe("free");
		expect(claimState(`${SYNTHETIC_CLAIM_PREFIX}${os.hostname()}:0`, self)).toBe("free");
		// A live HUMAN window on this host keeps needing --force.
		expect(claimState(`${os.hostname()}:${pid}`, self)).toBe("held-live");

		process.kill(pid);
		await new Promise((r) => setTimeout(r, 200));
		// Dead conductor pid: the claim is stale (non-blocking), same as any
		// dead same-host holder.
		expect(claimState(local, self)).toBe("held-stale");
		console.log("[VERIFY] T-16b req1: local_synthetic=held-conductor foreign_synthetic=held-live human=held-live");
	}, 20000);

	it("held-conductor is exactly the parser's positive verdict (single truth)", async () => {
		const self = windowClaimId();
		const pid = await spawnLivePid();
		const probes = [
			syntheticClaim(pid),
			syntheticClaim(pid, "other-host"),
			`${SYNTHETIC_CLAIM_PREFIX}${os.hostname()}:not-a-pid`,
			`${SYNTHETIC_CLAIM_PREFIX}${os.hostname()}:0`,
			`${os.hostname()}:${pid}`,
			"other-host:4242",
			windowClaimId(),
			"",
			"20260808-142655-3496",
			`${SYNTHETIC_CLAIM_PREFIX}${os.hostname()}`,
		];
		for (const probe of probes) {
			const parsed = parseSyntheticClaim(probe);
			const parserSaysYieldable = parsed !== undefined && parsed.host === os.hostname() && syntheticClaimLive(probe);
			expect(claimState(probe, self) === "held-conductor").toBe(parserSaysYieldable);
		}
		console.log(`[VERIFY] T-16b req4: probes=${probes.length} parser_equivalence=1`);
	}, 20000);
});

// ── requirement 1/2: the takeover itself ────────────────────────────────────

describe("takeOverKey: non-forced takeover of a conductor claim (T-16b req 1 + 2)", () => {
	it("succeeds without force on a synthetic claim and still refuses a live human window", async () => {
		const root = mkdtemp();
		const store = new IndexStore(root);
		const conductorPid = await spawnLivePid();
		const humanPid = await spawnLivePid();
		const synthetic = syntheticClaim(conductorPid);

		await seedKey(root, "key-conductor", synthetic);
		const nonForced = await takeOverKey(store, "key-conductor", false, root);
		expect(nonForced.ok).toBe(true);
		expect(nonForced.blockedBy).toBeUndefined();
		const row = store.findByKey("key-conductor");
		expect(row?.claimId).toBe(windowClaimId());
		expect(row?.status).toBe("active");
		// The conductor's own yield precondition (T-16 VC-3): the on-disk claim
		// is no longer synthetic, and from the conductor's identity it reads as a
		// live human holder — so `_human_claim_blocks_synthetic` yields instead
		// of reclaiming (see the trace-shape test below).
		expect(isSyntheticClaimId(row?.claimId ?? "")).toBe(false);
		expect(claimState(row?.claimId ?? "", synthetic)).toBe("held-live");

		// Counterweight (req 2): a LIVE human window is untouched by a non-forced
		// takeover and only leaves with --force.
		const humanClaim = `${os.hostname()}:${humanPid}`;
		await seedKey(root, "key-human", humanClaim);
		const blocked = await takeOverKey(store, "key-human", false, root);
		expect(blocked.ok).toBe(false);
		expect(blocked.blockedBy).toBe(humanClaim);
		expect(store.findByKey("key-human")?.claimId).toBe(humanClaim);
		const forced = await takeOverKey(store, "key-human", true, root);
		expect(forced.ok).toBe(true);
		expect(store.findByKey("key-human")?.claimId).toBe(windowClaimId());
		console.log("[VERIFY] T-16b req1/2: synthetic_nonforced=ok human_nonforced=blocked human_forced=ok");
	}, 30000);

	it("human-facing surfaces (/pm-key switch and switch_key) both yield without --force", async () => {
		const root = mkdtemp();
		const store = new IndexStore(root);
		const conductorPid = await spawnLivePid();
		const synthetic = syntheticClaim(conductorPid);
		await seedKey(root, "key-a", synthetic);
		await seedKey(root, "key-b", synthetic);

		// /pm-key switch key-a (no --force)
		const cmd = fakePi();
		const watch: PmWatchState = { key: undefined };
		registerPmKeyCommands(cmd.pi, store, watch, () => {}, root);
		const handler = cmd.commands.get("pm-key");
		if (!handler) throw new Error("pm-key not registered");
		const notice = fakeCmdCtx();
		await handler("switch key-a", notice.ctx);
		expect(store.findByKey("key-a")?.claimId).toBe(windowClaimId());
		expect(watch.key).toBe("key-a");
		expect(notice.notifications.some((n) => n.includes("Took over key: key-a"))).toBe(true);
		expect(cmd.entries.filter((e) => e.customType === "agent-team-loop:watch")).toHaveLength(1);
		// No new event vocabulary is introduced on the takeover path: the only
		// session entry written is the existing watch entry (req 3).
		expect(cmd.entries.every((e) => e.customType === "agent-team-loop:watch")).toBe(true);

		// switch_key tool on key-b (no force)
		const toolPi = fakePi();
		registerSwitchKeyTool(toolPi.pi, store, { key: undefined }, () => {}, root);
		const tool = toolPi.tools.get("switch_key");
		if (!tool) throw new Error("switch_key not registered");
		const result = await tool.execute("call-1", { key: "key-b" });
		expect(result.content[0]?.text ?? "").toContain("Took over key 'key-b'");
		expect(store.findByKey("key-b")?.claimId).toBe(windowClaimId());
		console.log("[VERIFY] T-16b req1: pm_key_switch=ok switch_key_tool=ok entries_only_watch=1");
	}, 20000);
});

// ── requirement 2: no widening of the cross-key read/write guard ────────────

describe("cross-key guard: a conductor-held key stays read-only until taken over (T-16b req 2)", () => {
	it("refuses writes to the conductor's key, then opens after the takeover", async () => {
		const root = mkdtemp();
		const store = new IndexStore(root);
		const conductorPid = await spawnLivePid();
		await seedKey(root, "key-a", syntheticClaim(conductorPid));

		const refusal = foreignLiveClaimRefusal(store, "key-a");
		expect(refusal).not.toBeNull();
		expect(refusal).toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(refusal).toContain("autopilot conductor");
		expect(refusal).toContain("switch_key");
		// The guard names the right escape hatch: a plain takeover, no force.
		expect(refusal).toContain("no force needed");

		// Owner resolution stays conservative too: an active row held by the
		// conductor is not this window's owner key (unchanged pre-T-16b rule).
		const { pi } = fakePi();
		expect(resolveOwnerKeyWithSync(pi, store, { key: undefined }, undefined, root)).toBe("_scratch");

		await takeOverKey(store, "key-a", false, root);
		expect(foreignLiveClaimRefusal(store, "key-a")).toBeNull();
		expect(resolveOwnerKeyWithSync(pi, store, { key: undefined }, undefined, root)).toBe("key-a");
		console.log("[VERIFY] T-16b req2: conductor_guard=refused after_takeover=writeable owner_degrade=unchanged");
	}, 20000);

	it("still refuses another live window's claim with the same stable code", async () => {
		const root = mkdtemp();
		const store = new IndexStore(root);
		const humanPid = await spawnLivePid();
		await seedKey(root, "key-human", `${os.hostname()}:${humanPid}`);
		const refusal = foreignLiveClaimRefusal(store, "key-human");
		expect(refusal).toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(refusal).toContain("another window");
		expect(refusal).not.toContain("no force needed");
	}, 20000);
});

// ── requirement 4: one implementation of the synthetic shape ────────────────

describe("single source for the synthetic shape (T-16b req 4)", () => {
	it("ui-bridge.ts never repeats the autopilot@ prefix; it imports the shared parser", () => {
		const source = fs.readFileSync(UI_BRIDGE_PATH, "utf8");
		expect(source).toContain("parseSyntheticClaim");
		expect(source).toContain("syntheticClaimLive");
		// No re-derived prefix knowledge: neither the exported constant nor a
		// quoted literal / startsWith test of the shape lives here.
		expect(source).not.toContain("SYNTHETIC_CLAIM_PREFIX");
		expect(source).not.toContain('"autopilot@"');
		expect(source).not.toContain("'autopilot@'");
		expect(source).not.toMatch(/startsWith\(\s*["'`]autopilot/);
		console.log("[VERIFY] T-16b req4: ui_bridge_prefix_literals=0 shared_parser_refs=2");
	});
});

// ── requirement 3: the yield trace reuses T-16's existing shape ─────────────

describe("yield trace stays T-16's existing shape (T-16b req 3)", () => {
	it("the conductor yields on the post-takeover row and traces it with the existing `skip` event", () => {
		const conductorSource = fs.readFileSync(
			path.join(REPO_ROOT, "packages/multi-workers/autopilot/conductor.py"),
			"utf8",
		);
		const at = conductorSource.indexOf("def _trace_human_hold");
		expect(at).toBeGreaterThan(-1);
		// The yield/withheld trace reuses the pre-existing `skip` event name and
		// the T-16 wording — this card adds no TS trace event of its own (the
		// takeover path writes only the watch session entry, asserted above).
		const body = conductorSource.slice(at, at + 2000);
		expect(body).toContain('timeline.append("skip"');
		expect(body).toContain("synthetic claim yielded to human claim");
		console.log("[VERIFY] T-16b req3: reuse_event=skip new_event_names=0");
	});
});
