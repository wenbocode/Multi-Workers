/**
 * Tests for the /autopilot monitor panel (autopilot-monitor T-01, design
 * D-001..D-007, VC-001..VC-008 + VC-011).
 *
 * - readMonitorState/renderMonitorLines derive the four-section snapshot
 *   from fixture FILES alone: serve (mw.pid liveness + serve.meta), the
 *   conductor (pid file + signal-0 + config.json intent), cross-key running
 *   workers (_workers.parallel), and pending gates (frontmatter line scan).
 * - startMonitor renders the first frame synchronously (0 ticks, VC-001),
 *   then re-reads every interval; fake timers drive the ticks.
 * - stopMonitor clears the widget and stops the ticks (VC-005).
 * - The /autopilot monitor command path (console.ts wiring) is exercised
 *   through fake pi/command contexts (same pattern as
 *   autopilot-console.test.ts), including the print-mode hasUI guard
 *   (VC-006) and the deps injection seams.
 * - VC-010 (T-02) locks the dual-widget contract on ONE shared fake UI:
 *   the production watch render path (ui-bridge setWatchWidget) and the
 *   monitor command path write two distinct widget ids that coexist —
 *   neither setWidget call overwrites the other's frame.
 * - VC-011 locks the per-window memory semantics: two module instances
 *   (vi.resetModules + a second import) hold independent monitor state.
 *
 * A dead pid is a large unused number (signal-0 → ESRCH); a live pid is
 * this test process. No provider APIs, keys, or network: pure file fixtures.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import {
	autoStartMonitor,
	registerAutopilotCommands,
	resetMonitorSuppression,
} from "../../src/extensions/agent-team-loop/autopilot/console.ts";
import {
	deriveAdvanceStalls,
	isMonitorActive,
	MONITOR_WIDGET_ID,
	type MonitorAutopilot,
	type MonitorSnapshot,
	PANEL_STALE_MISSED_CYCLES,
	readMonitorState,
	readTimelineTail,
	renderMonitorLines,
	startMonitor,
	stopMonitor,
} from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import {
	DEFAULT_CONFIG,
	deriveStatusModel,
	readConfig,
	renderStatusText,
	type TimelineEvent,
	validateConfigData,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { setWatchWidget } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "ap-monitor-"));
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

/** A running serve: mw.pid (live pid) + serve.meta with the start time. */
function writeServe(root: string, pid: number, startedAtMs: number): void {
	const mwDir = path.join(root, ".mw");
	fs.mkdirSync(mwDir, { recursive: true });
	fs.writeFileSync(path.join(mwDir, "mw.pid"), String(pid), "utf8");
	fs.writeFileSync(path.join(mwDir, "serve.meta"), JSON.stringify({ pid, started_at_ms: startedAtMs }), "utf8");
}

/** A conductor pid file (caller picks live or dead pids). */
function writeConductor(root: string, pid: number): void {
	const mwDir = path.join(root, ".mw");
	fs.mkdirSync(mwDir, { recursive: true });
	fs.writeFileSync(path.join(mwDir, "conductor.pid"), String(pid), "utf8");
}

/** A valid _autopilot/config.json (partial fields fall back to defaults). */
function writeConfig(root: string, cfg: { enabled: boolean; paused?: boolean }): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, "config.json"),
		JSON.stringify({ enabled: cfg.enabled, paused: cfg.paused ?? false }),
		"utf8",
	);
}

/** `_workers.parallel` rows in the 9-column WorkerStore format
 * (`... | model | origin`). `ownerKey` selects the
 * `.agenticdoc/<owner>/workers/` path; `origin` defaults to empty (a legacy
 * row, which the canonical reader normalises to `manual`). */
function writeWorkers(
	root: string,
	rows: Array<{ key: string; status: string; dispatchedAt: string; ownerKey?: string; origin?: string }>,
): void {
	const agenticdoc = path.join(root, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	const lines = rows.map((r) => {
		const owner = r.ownerKey ?? "_scratch";
		return (
			`${r.key} | ${r.status} | pi | timi | ${path.join(agenticdoc, owner, "workers", r.key, "task.md")} | ` +
			`${r.dispatchedAt} | ${r.dispatchedAt} |  | ${r.origin ?? ""}`
		);
	});
	fs.writeFileSync(path.join(agenticdoc, "_workers.parallel"), `${lines.join("\n")}\n`, "utf8");
}

/** A gate file in the gates.py frontmatter shape (line-scan compatible). */
function writeGate(
	root: string,
	g: { id: string; kind: string; stage: number | null; status: string; key?: string },
): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot", "gates");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, `${g.id}.md`),
		[
			"---",
			`id: ${g.id}`,
			`kind: ${g.kind}`,
			`stage: ${g.stage === null ? "" : g.stage}`,
			`key: ${g.key ?? ""}`,
			"created_at: 2026-09-11T10:00:00+00:00",
			"created_by: conductor",
			"question: 'Proceed?'",
			"context_refs:",
			"  - .agenticdoc/_autopilot/_roadmap.md",
			`status: ${g.status}`,
			"answered_at:",
			"answered_by:",
			"note:",
			"---",
			"",
			`# Gate ${g.id}`,
			"",
		].join("\n"),
		"utf8",
	);
}

/** The autopilot section of a snapshot, for the panel tests that only care
 * about serve/conductor/workers/gates (the dedicated autopilot assertions
 * build their own via readMonitorState on real files). */
function stubAutopilot(overrides: Partial<MonitorAutopilot> = {}): MonitorAutopilot {
	return {
		enabled: true,
		everEnabled: true,
		tickSeq: null,
		tickAgeMs: null,
		tickStale: false,
		slotsUsed: 0,
		slotsMax: 2,
		stallTicks: 5,
		keys: [],
		stalls: [],
		...overrides,
	};
}

/** sha1 over every file's path + content under the given roots (VC-008). */
function hashTree(roots: string[]): string {
	const h = createHash("sha1");
	const walk = (dir: string): void => {
		let entries: fs.Dirent[];
		try {
			entries = fs.readdirSync(dir, { withFileTypes: true });
		} catch {
			return;
		}
		for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
			const p = path.join(dir, e.name);
			if (e.isDirectory()) walk(p);
			else if (e.isFile()) {
				h.update(p);
				h.update(fs.readFileSync(p));
			}
		}
	};
	for (const r of roots) walk(r);
	return h.digest("hex");
}

// ── Fake pi / command context ────────────────────────────────────────────────

function fakeConsolePi(): {
	pi: ExtensionAPI;
	commands: Map<string, { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }>;
} {
	const commands = new Map<string, { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }>();
	const pi = {
		registerCommand: (
			name: string,
			opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, opts);
		},
		appendEntry: () => {},
	} as unknown as ExtensionAPI;
	return { pi, commands };
}

function fakeCmdCtx(hasUI: boolean): {
	ctx: ExtensionCommandContext;
	notifications: string[];
	widgets: Array<{ key: string; content: string[] | undefined; options?: { placement?: string } }>;
} {
	const notifications: string[] = [];
	const widgets: Array<{ key: string; content: string[] | undefined; options?: { placement?: string } }> = [];
	const ctx = {
		hasUI,
		ui: {
			notify: (message: string) => {
				notifications.push(message);
			},
			setWidget: (key: string, content: string[] | undefined, options?: { placement?: string }) => {
				widgets.push({ key, content, options });
			},
		},
		sessionManager: { getEntries: () => [] },
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications, widgets };
}

// ── Monitor panel (VC-001..VC-008, VC-011) ───────────────────────────────────

describe("autopilot monitor panel (T-01, VC-001..008 + VC-011)", () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		stopMonitor();
		vi.useRealTimers();
	});

	it("VC-001: serve running — the first frame renders synchronously (0 ticks) with pid + fresh/stale", () => {
		const root = mkdtemp();
		const now = Date.now();
		writeServe(root, process.pid, now);
		try {
			const frames: Array<string[] | undefined> = [];
			expect(startMonitor(root, (lines) => frames.push(lines), { nowMs: () => now })).toBe(true);
			// First frame BEFORE any tick — 0 timers advanced.
			expect(frames).toHaveLength(1);
			const lines = frames[0] ?? [];
			const serveLine = lines.find((l) => l.startsWith("serve:")) ?? "";
			expect(serveLine).toContain(String(process.pid));
			expect(/fresh|stale/.test(serveLine)).toBe(true);
			// Fixed section structure: all four sections always present (§9).
			// G4: the header now carries the frame's self-attesting stamp, so
			// assert the stable prefix instead of exact equality.
			expect(lines[0]).toContain("[autopilot monitor]");
			expect(lines.some((l) => l.startsWith("conductor:"))).toBe(true);
			expect(lines.some((l) => l.startsWith("workers:"))).toBe(true);
			expect(lines.some((l) => l.startsWith("gates:"))).toBe(true);
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-002: a dead conductor pid renders dead from the first frame (and stays dead; a live pid renders alive)", () => {
		const root = mkdtemp();
		const now = Date.now();
		const deadPid = 4_194_304;
		// Fixture guard: the "dead" pid must be unused on this machine.
		expect(() => process.kill(deadPid, 0)).toThrow();
		writeConductor(root, deadPid);
		writeConfig(root, { enabled: true, paused: false });
		try {
			const frames: Array<string[] | undefined> = [];
			startMonitor(root, (lines) => frames.push(lines), { nowMs: () => now });
			const conductor = (): string => frames.at(-1)?.find((l) => l.startsWith("conductor:")) ?? "";
			expect(conductor()).toContain("dead");
			expect(conductor()).toContain(String(deadPid));
			// Still dead at tick 1 and tick 2 (<= 2 ticks, AC-002).
			vi.advanceTimersByTime(4000);
			expect(conductor()).toContain("dead");
			vi.advanceTimersByTime(4000);
			expect(conductor()).toContain("dead");
			// A live pid (this test process) flips the line to alive on the next tick.
			writeConductor(root, process.pid);
			vi.advanceTimersByTime(4000);
			expect(conductor()).toContain("alive");
			expect(conductor()).toContain(String(process.pid));
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-003: two running rows dispatched 90s ago render as 2 worker lines with ceil minutes; non-running rows never appear", () => {
		const root = mkdtemp();
		const now = Date.now();
		const dispatched = new Date(now - 90_000).toISOString();
		writeWorkers(root, [
			{ key: "ap-x-t01", status: "running", dispatchedAt: dispatched },
			{ key: "ap-y-t02", status: "running", dispatchedAt: dispatched },
			{ key: "ap-z-done", status: "done", dispatchedAt: dispatched },
		]);
		try {
			const frames: Array<string[] | undefined> = [];
			startMonitor(root, (lines) => frames.push(lines), { nowMs: () => now });
			const lines = frames[0] ?? [];
			expect(lines.find((l) => l.startsWith("workers:"))).toBe("workers: 2 running (all keys)");
			const rows = lines.filter((l) => l.startsWith("  ·"));
			expect(rows).toHaveLength(2);
			expect(rows.join("\n")).toContain("ap-x-t01");
			expect(rows.join("\n")).toContain("ap-y-t02");
			// ceil(90s / 60s) = 2m per row.
			expect(rows.every((r) => r.includes("  2m"))).toBe(true);
			expect(lines.join("\n")).not.toContain("ap-z-done");
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-004: a pending gate shows id+kind; approving it zeroes the line on the next tick", () => {
		const root = mkdtemp();
		const now = Date.now();
		writeGate(root, { id: "gate-0002", kind: "stage-confirm", stage: 2, status: "pending" });
		try {
			const frames: Array<string[] | undefined> = [];
			startMonitor(root, (lines) => frames.push(lines), { nowMs: () => now });
			const gatesLine = frames[0]?.find((l) => l.startsWith("gates:")) ?? "";
			expect(gatesLine).toContain("1 pending");
			expect(gatesLine).toContain("gate-0002");
			expect(gatesLine).toContain("stage-confirm");
			// The gate leaves pending → the next tick shows zero.
			writeGate(root, { id: "gate-0002", kind: "stage-confirm", stage: 2, status: "approved" });
			vi.advanceTimersByTime(4000);
			expect(frames.at(-1)?.find((l) => l.startsWith("gates:"))).toBe("gates: 0 pending");
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-005: off clears the widget (setWidget undefined) and later ticks render nothing", async () => {
		const root = mkdtemp();
		writeServe(root, process.pid, Date.now());
		try {
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root, { monitorIntervalMs: 100 });
			const { ctx, widgets } = fakeCmdCtx(true);
			await commands.get("autopilot")?.handler("monitor on", ctx);
			expect(widgets[0]?.key).toBe(MONITOR_WIDGET_ID);
			expect(widgets[0]?.content?.[0]).toContain("[autopilot monitor]");
			expect(widgets[0]?.options?.placement).toBe("belowEditor");
			// First frame + two ticks = three setWidget calls with content.
			vi.advanceTimersByTime(100);
			vi.advanceTimersByTime(100);
			expect(widgets).toHaveLength(3);
			expect(widgets.every((w) => w.content !== undefined)).toBe(true);
			// off → the widget is cleared via setWidget(id, undefined).
			await commands.get("autopilot")?.handler("monitor off", ctx);
			expect(widgets.at(-1)?.key).toBe(MONITOR_WIDGET_ID);
			expect(widgets.at(-1)?.content).toBeUndefined();
			expect(isMonitorActive()).toBe(false);
			// The interval is gone: further time produces no setWidget calls.
			const countAtOff = widgets.length;
			vi.advanceTimersByTime(1000);
			expect(widgets).toHaveLength(countAtOff);
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-006: print mode (hasUI=false) degrades to a 'no visual UI' notice, starts nothing, throws nothing", async () => {
		const root = mkdtemp();
		try {
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications, widgets } = fakeCmdCtx(false);
			let thrown = 0;
			try {
				await commands.get("autopilot")?.handler("monitor on", ctx);
			} catch {
				thrown += 1;
			}
			expect(thrown).toBe(0);
			expect(notifications[0] ?? "").toContain("no visual UI");
			expect(widgets).toHaveLength(0);
			expect(isMonitorActive()).toBe(false);
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-007: no mw.pid — the serve line carries 'not running' + /mw restart; the other sections still render", () => {
		const root = mkdtemp();
		// No .mw/mw.pid at all; the rest of the chain is present.
		writeConductor(root, process.pid);
		writeConfig(root, { enabled: true, paused: false });
		try {
			const lines = renderMonitorLines(readMonitorState(root, Date.now()));
			const serveLine = lines.find((l) => l.startsWith("serve:")) ?? "";
			expect(serveLine).toContain("not running");
			expect(serveLine).toContain("/mw restart");
			// other_lines_present=true — a full panel despite the dead serve.
			expect(lines.some((l) => l.startsWith("conductor:"))).toBe(true);
			expect(lines.some((l) => l.startsWith("workers:"))).toBe(true);
			expect(lines.some((l) => l.startsWith("gates:"))).toBe(true);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-008: three ticks leave every .mw/ and _autopilot/ file byte-identical (pure read-only)", () => {
		const root = mkdtemp();
		const now = Date.now();
		writeServe(root, process.pid, now);
		writeConductor(root, process.pid);
		writeConfig(root, { enabled: true, paused: false });
		writeWorkers(root, [{ key: "ap-x-t01", status: "running", dispatchedAt: new Date(now - 60_000).toISOString() }]);
		writeGate(root, { id: "gate-0001", kind: "stalled", stage: 2, status: "pending" });
		try {
			const roots = [path.join(root, ".mw"), path.join(root, ".agenticdoc", "_autopilot")];
			const before = hashTree(roots);
			const frames: Array<string[] | undefined> = [];
			startMonitor(root, (lines) => frames.push(lines), { nowMs: () => now });
			vi.advanceTimersByTime(4000);
			vi.advanceTimersByTime(4000);
			vi.advanceTimersByTime(4000);
			// First frame + 3 ticks actually ran against the fixture.
			expect(frames).toHaveLength(4);
			expect(hashTree(roots)).toBe(before);
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-011: two module instances (windows) hold independent monitor state — no cross-window leak", async () => {
		const rootA = mkdtemp();
		const rootB = mkdtemp();
		writeServe(rootA, process.pid, Date.now());
		writeServe(rootB, process.pid, Date.now());
		const framesA: Array<string[] | undefined> = [];
		const framesB: Array<string[] | undefined> = [];
		try {
			// Window A (this module instance) starts its monitor.
			expect(startMonitor(rootA, (lines) => framesA.push(lines))).toBe(true);
			expect(isMonitorActive()).toBe(true);
			const aFramesAfterStart = framesA.length;

			// Window B: a fresh module instance (resetModules + re-import) —
			// the singleton state is per module instance, i.e. per window
			// process (AC-009 in-process semantics).
			vi.resetModules();
			const monitorB = await import("../../src/extensions/agent-team-loop/autopilot/monitor.ts");
			expect(monitorB.isMonitorActive()).toBe(false);
			expect(monitorB.startMonitor(rootB, (lines) => framesB.push(lines))).toBe(true);
			expect(monitorB.isMonitorActive()).toBe(true);
			// B's start did not re-render or stop A's panel.
			expect(framesA.length).toBe(aFramesAfterStart);

			// B stops — only B's apply receives the clear; A keeps running.
			expect(monitorB.stopMonitor()).toBe(true);
			expect(framesB.at(-1)).toBeUndefined();
			expect(monitorB.isMonitorActive()).toBe(false);
			expect(isMonitorActive()).toBe(true);

			// A stops — A's panel clears.
			expect(stopMonitor()).toBe(true);
			expect(framesA.at(-1)).toBeUndefined();
			expect(isMonitorActive()).toBe(false);
		} finally {
			stopMonitor();
			fs.rmSync(rootA, { recursive: true, force: true });
			fs.rmSync(rootB, { recursive: true, force: true });
		}
	});
});

// ── G2 AC-008 (VC-011): pending age + BLOCKED_ON_HUMAN marker ────────────────

describe("G2 AC-008/VC-011: pending-gate age + BLOCKED_ON_HUMAN marker", () => {
	const NOW_MS = Date.parse("2026-09-11T10:30:00+00:00");

	it("VC-011: status rows show pending age and the panel marks the human-blocked state", () => {
		const root = mkdtemp();
		writeConfig(root, { enabled: true });
		writeGate(root, { id: "gate-0007", kind: "stalled", stage: null, status: "pending", key: "k1" });
		try {
			// (a) pending gate + 0 non-terminal rows ⇒ the truth table is true.
			const blocked = readMonitorState(root, NOW_MS);
			expect(blocked.blockedOnHuman).toBe(true);
			const marker = renderMonitorLines(blocked).find((l) => l.startsWith("BLOCKED_ON_HUMAN"));
			expect(marker).toBeDefined();
			expect(marker ?? "").toContain("1 pending gate(s)");

			// (b) the status view shows the pending age; `age=?` for an
			// unparsable created_at — never NaN.
			const status = deriveStatusModel(root, NOW_MS);
			expect(status.ok).toBe(true);
			if (!status.ok) return;
			const text = renderStatusText(status.model);
			expect(text).toContain("gate-0007 stalled pending age=30m");
			expect(text).not.toContain("NaN");
			process.stdout.write("[VERIFY] VC-011: age_shown=true blocked_marker=true\n");

			// (c) non-hollow fixtures: a `pending` row is non-terminal (design
			// D-008/F6) and a `running` row too — both clear the marker.
			writeWorkers(root, [
				{ key: "ap-k1-t01", status: "pending", dispatchedAt: "2026-09-11T10:00:00+00:00", ownerKey: "k1" },
			]);
			const pendingRow = readMonitorState(root, NOW_MS);
			expect(pendingRow.blockedOnHuman).toBe(false);
			expect(renderMonitorLines(pendingRow).some((l) => l.startsWith("BLOCKED_ON_HUMAN"))).toBe(false);

			writeWorkers(root, [
				{ key: "ap-k1-t02", status: "running", dispatchedAt: "2026-09-11T10:00:00+00:00", ownerKey: "k1" },
			]);
			const runningRow = readMonitorState(root, NOW_MS);
			expect(runningRow.blockedOnHuman).toBe(false);
			expect(renderMonitorLines(runningRow).some((l) => l.startsWith("BLOCKED_ON_HUMAN"))).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-011: a stale conductor suppresses only the marker, not the truth table (TS-only third axis)", () => {
		const root = mkdtemp();
		writeConfig(root, { enabled: true });
		writeGate(root, { id: "gate-0008", kind: "stalled", stage: null, status: "pending", key: "k1" });
		writeTimeline(root, [{ ts: "2026-09-11T10:00:00+00:00", ev: "beat" }]);
		try {
			const snap = readMonitorState(root, NOW_MS);
			expect(snap.autopilot.tickStale).toBe(true);
			expect(snap.blockedOnHuman).toBe(true); // file-only truth table unchanged
			expect(renderMonitorLines(snap).some((l) => l.startsWith("BLOCKED_ON_HUMAN"))).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── G4 AC-015..017 (VC-020..VC-022): freshness + degraded frames ─────────────

/** A readState that fails on demand: drives the degraded path without touching
 * any file (the fail injection adds no write path). */
function flakyReadState(): { readState: typeof readMonitorState; fail: (on: boolean) => void } {
	let failing = false;
	return {
		readState: (projectDir: string, nowMs: number) => {
			if (failing) throw new Error("boom");
			return readMonitorState(projectDir, nowMs);
		},
		fail: (on: boolean): void => {
			failing = on;
		},
	};
}

describe("G4 AC-015/AC-016/AC-017 (VC-020..VC-022): frame self-attestation", () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		stopMonitor();
		vi.useRealTimers();
	});

	it("VC-020: the absolute stamp + tick advance every tick; >3 stale periods raise STALE PANEL", () => {
		const root = mkdtemp();
		const t0 = Date.parse("2026-10-10T12:00:00+00:00");
		let now = t0;
		const { readState, fail } = flakyReadState();
		writeServe(root, process.pid, t0);
		writeConfig(root, { enabled: true });
		try {
			const frames: Array<string[] | undefined> = [];
			startMonitor(root, (lines) => frames.push(lines), { nowMs: () => now, readState });
			const header = (index: number): string => frames[index]?.[0] ?? "";
			// Frame 0 stamps the absolute wall-clock collection time + tick count.
			expect(header(0)).toContain(`collected ${new Date(t0).toISOString()}`);
			expect(header(0)).toMatch(/tick \d+/);
			expect(header(0)).not.toContain("STALE PANEL");
			const tickAt0 = Number(/tick (\d+)/.exec(header(0))?.[1]);
			// Tick 1 advances BOTH the stamp and the monotonic count.
			now += 4000;
			vi.advanceTimersByTime(4000);
			expect(header(1)).toContain(`collected ${new Date(now).toISOString()}`);
			expect(Number(/tick (\d+)/.exec(header(1))?.[1])).toBeGreaterThan(tickAt0);
			// The read starts failing: the stamp freezes (payload = last good), the
			// tick count stops, and no frame is dropped.
			fail(true);
			const goodStamp = new Date(now).toISOString();
			for (let i = 0; i < PANEL_STALE_MISSED_CYCLES; i++) {
				now += 4000;
				vi.advanceTimersByTime(4000);
			}
			expect(frames).toHaveLength(2 + PANEL_STALE_MISSED_CYCLES);
			const atBound = header(frames.length - 1);
			expect(atBound).toContain(`collected ${goodStamp}`);
			expect(atBound).not.toContain("STALE PANEL"); // exactly N periods is not "more than N"
			expect(frames.at(-1)?.join("\n")).toContain("DEGRADED");
			// The next failed period crosses the AC-015 bound.
			now += 4000;
			vi.advanceTimersByTime(4000);
			const late = header(frames.length - 1);
			expect(late).toContain("STALE PANEL");
			expect(late).toContain("no refresh since");
			process.stdout.write("[VERIFY] VC-020: stamp_advances=true stale_warned=true\n");
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-021: a data-plane change is followed within <=2 refresh cycles", () => {
		const root = mkdtemp();
		const t0 = Date.parse("2026-10-10T12:00:00+00:00");
		let now = t0;
		const { readState } = flakyReadState();
		writeWorkers(root, [{ key: "ap-k1-old", status: "done", dispatchedAt: new Date(t0).toISOString() }]);
		try {
			const frames: Array<string[] | undefined> = [];
			startMonitor(root, (lines) => frames.push(lines), { nowMs: () => now, readState });
			const workersLine = (index: number): string => frames[index]?.find((l) => l.startsWith("workers:")) ?? "";
			expect(workersLine(0)).toBe("workers: 0 running");
			// The data plane flips 0 -> 3 running rows...
			writeWorkers(
				root,
				[1, 2, 3].map((n) => ({
					key: `ap-k1-t0${n}`,
					status: "running",
					dispatchedAt: new Date(t0).toISOString(),
					ownerKey: "k1",
					origin: "conductor",
				})),
			);
			// ...and the panel must have followed by the 2nd refresh cycle.
			now += 4000;
			vi.advanceTimersByTime(4000);
			now += 4000;
			vi.advanceTimersByTime(4000);
			expect(workersLine(2)).toBe("workers: 3 running (all keys)");
			process.stdout.write("[VERIFY] VC-021: followed_within_cycles=2\n");
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-022: a failing read emits a DEGRADED frame, including when the FIRST tick fails", () => {
		const root = mkdtemp();
		const t0 = Date.parse("2026-10-10T12:00:00+00:00");
		let now = t0;
		const { readState, fail } = flakyReadState();
		writeConfig(root, { enabled: true });
		writeWorkers(root, [
			{
				key: "ap-k1-t01",
				status: "running",
				dispatchedAt: new Date(t0).toISOString(),
				ownerKey: "k1",
				origin: "conductor",
			},
		]);
		try {
			const roots = [path.join(root, ".mw"), path.join(root, ".agenticdoc")];
			const before = hashTree(roots);
			// (a) with a previous good frame the degraded frame reuses its payload.
			const frames: Array<string[] | undefined> = [];
			startMonitor(root, (lines) => frames.push(lines), { nowMs: () => now, readState });
			expect(frames).toHaveLength(1);
			expect(frames[0]?.join("\n")).toContain("workers: 1 running");
			fail(true);
			now += 4000;
			vi.advanceTimersByTime(4000);
			expect(frames).toHaveLength(2); // never silently dropped
			const degraded = frames.at(-1) ?? [];
			expect(degraded.join("\n")).toContain("workers: 1 running"); // last-good payload kept
			expect(degraded.join("\n")).toContain("DEGRADED");
			expect(degraded.join("\n")).toContain("boom");
			expect(degraded.join("\n")).toContain(`read failed at ${new Date(now).toISOString()}`);
			expect(degraded[0]).toContain(`collected ${new Date(t0).toISOString()}`);
			stopMonitor();

			// (b) BOUNDARY (D-018): the very FIRST collection fails ⇒ no previous
			// frame exists; the emitted frame carries the collection stamp + the
			// error summary and fabricates no data.
			now = t0;
			const firstFail: Array<string[] | undefined> = [];
			startMonitor(root, (lines) => firstFail.push(lines), { nowMs: () => now, readState });
			expect(firstFail).toHaveLength(1);
			const only = firstFail[0] ?? [];
			expect(only[0]).toContain(`collected ${new Date(t0).toISOString()}`);
			expect(only.join("\n")).toContain("DEGRADED");
			expect(only.join("\n")).toContain("boom");
			expect(only.join("\n")).not.toContain("workers: 1 running"); // no fabricated payload
			// The boundary stamp does not advance on further failures: the panel goes
			// STALE PANEL instead of pretending to be freshly stamped.
			for (let i = 0; i <= PANEL_STALE_MISSED_CYCLES; i++) {
				now += 4000;
				vi.advanceTimersByTime(4000);
			}
			const lateBoundary = firstFail.at(-1) ?? [];
			expect(lateBoundary[0]).toContain("STALE PANEL");
			expect(lateBoundary[0]).toContain(`no refresh since ${new Date(t0).toISOString()}`);
			expect(lateBoundary.join("\n")).toContain("DEGRADED");
			expect(lateBoundary.join("\n")).not.toContain("workers: 1 running");
			// No write path was added: the read-only contract holds on the failure
			// path too.
			expect(hashTree(roots)).toBe(before);
			process.stdout.write("[VERIFY] VC-022: degraded_frame=true silent_frames=0\n");
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── /autopilot monitor command wiring (console.ts) ───────────────────────────

describe("/autopilot monitor command wiring", () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		stopMonitor();
		vi.useRealTimers();
	});

	it("render: boundary states - paused conductor, never-enabled, empty workers/gates, stale serve", () => {
		const paused = renderMonitorLines({
			serve: { running: false, pid: null, stale: false, staleDetail: "", upMs: null },
			conductor: { pid: 123, alive: true, enabled: true, paused: true, everEnabled: true },
			autopilot: stubAutopilot(),
			workers: [],
			gates: [],
			blockedOnHuman: false,
		}).join("\n");
		expect(paused).toContain("serve: not running -> /mw restart");
		expect(paused).toContain("conductor: PID 123 alive | autopilot enabled, paused");
		expect(paused).toContain("workers: 0 running");
		expect(paused).toContain("gates: 0 pending");

		const never = renderMonitorLines({
			serve: { running: true, pid: 7, stale: true, staleDetail: "serve started X, mw code changed Y", upMs: 1 },
			conductor: { pid: null, alive: false, enabled: false, paused: false, everEnabled: false },
			autopilot: stubAutopilot({ enabled: false, everEnabled: false }),
			workers: [],
			gates: [],
			blockedOnHuman: false,
		}).join("\n");
		expect(never).toContain("serve: PID 7 STALE CODE (serve started X, mw code changed Y) -> /mw restart");
		expect(never).toContain("conductor: not enabled (/autopilot enable)");
		expect(never).toContain("autopilot: not enabled (/autopilot enable)");

		// Long staleness detail is capped, never the /mw restart hint.
		const longDetail = renderMonitorLines({
			serve: {
				running: true,
				pid: 7,
				stale: true,
				staleDetail: "d".repeat(300),
				upMs: null,
			},
			conductor: { pid: null, alive: false, enabled: false, paused: false, everEnabled: false },
			autopilot: stubAutopilot({ enabled: false, everEnabled: false }),
			workers: [],
			gates: [],
			blockedOnHuman: false,
		});
		expect(longDetail[1]?.length).toBeLessThanOrEqual(110);
		expect(longDetail[1]).toContain("-> /mw restart");
	});

	it("wiring: no-arg toggles, USAGE covers monitor, and the readMonitorState seam feeds the panel", async () => {
		const root = mkdtemp();
		try {
			const snapshot: MonitorSnapshot = {
				serve: { running: true, pid: 27572, stale: false, staleDetail: "", upMs: 7_380_000 },
				conductor: { pid: 99000, alive: true, enabled: true, paused: false, everEnabled: true },
				autopilot: stubAutopilot(),
				workers: [
					{
						taskKey: "ap-x-t01",
						status: "running",
						cli: "pi",
						provider: "timi",
						taskPath: "H:/p/.agenticdoc/_scratch/workers/ap-x-t01/task.md",
						dispatchedAt: "2026-09-22T10:00:00+00:00",
						updatedAt: "2026-09-22T10:00:00+00:00",
						model: "",
						origin: "manual",
						elapsedMs: 180_000,
					},
				],
				gates: [{ id: "gate-0002", kind: "stage-confirm", stage: 2, key: "" }],
				blockedOnHuman: false,
			};
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root, {
				readMonitorState: () => snapshot,
				monitorIntervalMs: 100,
			});
			const { ctx, notifications, widgets } = fakeCmdCtx(true);

			// Unknown subcommands surface the USAGE, which now covers monitor.
			await commands.get("autopilot")?.handler("bogus", ctx);
			expect(notifications[0]).toContain("monitor [on|off]");
			// An invalid monitor argument gets its own usage line.
			await commands.get("autopilot")?.handler("monitor bogus", ctx);
			expect(notifications[1]).toContain("Usage: /autopilot monitor");

			// No argument while inactive → on; the seam snapshot renders.
			await commands.get("autopilot")?.handler("monitor", ctx);
			expect(isMonitorActive()).toBe(true);
			const first = widgets[0];
			expect(first?.key).toBe("agent-team-loop-monitor");
			expect(first?.options?.placement).toBe("belowEditor");
			const panel = first?.content?.join("\n") ?? "";
			expect(panel).toContain("serve: PID 27572 fresh, up 2h 3m");
			expect(panel).toContain("conductor: PID 99000 alive | autopilot enabled, not paused");
			expect(panel).toContain("workers: 1 running (all keys)");
			expect(panel).toContain("  · ap-x-t01  3m");
			expect(panel).toContain("gates: 1 pending - gate-0002 (stage-confirm)");
			expect(panel).toContain("-> /autopilot gate gate-0002 approve|reject");

			// No argument while active → off (toggle, D-006).
			await commands.get("autopilot")?.handler("monitor", ctx);
			expect(isMonitorActive()).toBe(false);
			expect(widgets.at(-1)?.content).toBeUndefined();

			// Explicit off while already stopped → notice, widget untouched.
			const count = widgets.length;
			await commands.get("autopilot")?.handler("monitor off", ctx);
			expect(widgets).toHaveLength(count);
			expect(notifications.at(-1)).toContain("was not running");
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── VC-010: dual widget coexistence (watch + monitor on one UI) ──────────────

describe("VC-010: watch + monitor widgets coexist on one window (distinct ids, no overwrite)", () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		stopMonitor();
		vi.useRealTimers();
	});

	it("VC-010: the watch widget and the monitor panel render under two distinct ids on the same UI — distinct_widget_ids=2", async () => {
		const root = mkdtemp();
		// One window = one shared UI: every setWidget lands in a keyed store.
		const store = new Map<string, string[] | undefined>();
		const calls: Array<{
			key: string;
			content: string[] | undefined;
			options?: { placement?: string; order?: number };
		}> = [];
		const ctx = {
			hasUI: true,
			ui: {
				notify: () => {},
				setWidget: (
					key: string,
					content: string[] | undefined,
					options?: { placement?: string; order?: number },
				) => {
					store.set(key, content);
					calls.push({ key, content, options });
				},
			},
			sessionManager: { getEntries: () => [] },
		} as unknown as ExtensionCommandContext;

		const snapshot: MonitorSnapshot = {
			serve: { running: true, pid: 27572, stale: false, staleDetail: "", upMs: 240_000 },
			conductor: { pid: 99000, alive: true, enabled: true, paused: false, everEnabled: true },
			autopilot: stubAutopilot(),
			workers: [],
			gates: [],
			blockedOnHuman: false,
		};
		const { pi, commands } = fakeConsolePi();
		registerAutopilotCommands(pi, root, {
			readMonitorState: () => snapshot,
			monitorIntervalMs: 100,
		});
		try {
			// The watch widget renders first (production path: ui-bridge
			// setWatchWidget — WATCH_WIDGET_KEY, belowEditor).
			setWatchWidget(ctx, ["[mw] ap-x | phase=2 | 1 running", "  > ap-x-t01 — ph 2/4 hb 12s"]);
			expect(store.get("agent-team-loop-watch")?.[0]).toContain("[mw] ap-x");

			// The monitor panel goes on over the SAME window UI.
			await commands.get("autopilot")?.handler("monitor on", ctx);
			expect(store.get("agent-team-loop-monitor")?.[0]).toContain("[autopilot monitor]");

			// Two distinct ids, both live — neither overwrote the other.
			expect(new Set(calls.map((c) => c.key))).toEqual(
				new Set(["agent-team-loop-watch", "agent-team-loop-monitor"]),
			);
			expect(store.get("agent-team-loop-watch")?.[0]).toContain("[mw] ap-x");
			expect(store.get("agent-team-loop-monitor")?.join("\n")).toContain("serve: PID 27572 fresh");
			// Both widgets stack below the editor (design D-003).
			expect(calls.every((c) => c.options?.placement === "belowEditor")).toBe(true);
			// mw-widget-order-stability: the monitor paints ABOVE the watch panel via an
			// explicit order, so the two 4s pollers can no longer flip positions.
			expect(calls.find((c) => c.key === "agent-team-loop-monitor")?.options?.order).toBe(0);
			expect(calls.find((c) => c.key === "agent-team-loop-watch")?.options?.order).toBe(10);

			// Interleaved refresh — one monitor tick, then a watch refresh:
			// each re-render touches only its own id; both frames stay live.
			vi.advanceTimersByTime(100);
			expect(store.get("agent-team-loop-watch")?.[0]).toContain("[mw] ap-x");
			setWatchWidget(ctx, ["[mw] ap-x | phase=3 | 1 running"]);
			expect(store.get("agent-team-loop-monitor")?.[0]).toContain("[autopilot monitor]");
			expect(store.get("agent-team-loop-watch")?.[0]).toContain("phase=3");

			// monitor off clears ONLY the monitor id — the watch widget stays.
			await commands.get("autopilot")?.handler("monitor off", ctx);
			expect(store.get("agent-team-loop-monitor")).toBeUndefined();
			expect(store.get("agent-team-loop-watch")?.[0]).toContain("phase=3");

			// VC-010 verdict: exactly two distinct widget ids were ever driven,
			// coexisting without overwriting each other.
			expect(new Set(calls.map((c) => c.key)).size).toBe(2);
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── Autopilot progress section (mw-autopilot-stall-feedback AC-006/AC-007) ────

/** config.json with an arbitrary field set (the canonical key order is up to
 * saveConfig; only the parse path matters here). */
function writeConfigJson(root: string, cfg: Record<string, unknown>): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(path.join(dir, "config.json"), `${JSON.stringify(cfg, null, 2)}\n`, "utf8");
}

/** _roadmap.md with key-status + depends_on (the shape readRoadmap parses). */
function writeRoadmap(root: string, keys: Array<{ key: string; status: string; dependsOn: string[] }>): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, "_roadmap.md"),
		[
			"# Roadmap",
			"> generated_at: 2026-09-22T00:00:00+00:00",
			"> goal_mtime: 1",
			"",
			"## Stage 1: work",
			"> goal: ship",
			"> status: running",
			`> key-status: ${keys.map((k) => `${k.key}=${k.status}`).join(", ")}`,
			"### Keys",
			"| key | role | depends_on |",
			"|-----|------|-----------|",
			...keys.map((k) => `| ${k.key} | worker | ${k.dependsOn.length === 0 ? "-" : k.dependsOn.join(",")} |`),
			"",
		].join("\n"),
		"utf8",
	);
}

/** _index.parallel rows (7-column IndexStore format). */
function writeIndex(root: string, rows: Array<{ key: string; phase: string }>): void {
	const agenticdoc = path.join(root, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	const lines = rows.map((r) => `| ${r.key} | active | ${r.phase} | free | - | d | 2026-09-22T00:00:00 |`);
	fs.writeFileSync(path.join(agenticdoc, "_index.parallel"), `${lines.join("\n")}\n`, "utf8");
}

/** Timeline JSONL from raw event partials (seq assigned by position). */
function writeTimeline(
	root: string,
	events: Array<Partial<{ ts: string; ev: string; key: string; detail: string }>>,
): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	const lines = events.map((e, i) =>
		JSON.stringify({
			ts: e.ts ?? "2026-09-22T00:00:00+00:00",
			seq: i + 1,
			ev: e.ev ?? "beat",
			key: e.key ?? "-",
			stage: null,
			detail: e.detail ?? "",
		}),
	);
	fs.writeFileSync(path.join(dir, "timeline.jsonl"), `${lines.join("\n")}\n`, "utf8");
}

describe("autopilot monitor auto-show (AC-008)", () => {
	beforeEach(() => {
		// the panel's suppression flag is module memory: clear it so a sibling
		// test's `/autopilot monitor off` does not leak into this case
		resetMonitorSuppression();
	});

	it("shows the panel for enabled projects, stays idempotent, and honors an explicit off", async () => {
		const root = mkdtemp();
		try {
			writeConfigJson(root, { enabled: true });
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root, { monitorIntervalMs: 100 });
			const { ctx, widgets } = fakeCmdCtx(true);
			expect(isMonitorActive()).toBe(false);
			expect(autoStartMonitor(ctx, root)).toBe(true);
			expect(isMonitorActive()).toBe(true);
			expect(widgets.at(-1)?.key).toBe(MONITOR_WIDGET_ID);
			expect(widgets.at(-1)?.content?.[0]).toContain("[autopilot monitor]");
			// idempotent: an active panel is left alone (no extra start)
			const frames = widgets.length;
			expect(autoStartMonitor(ctx, root)).toBe(true);
			expect(widgets.length).toBe(frames);
			// explicit off suppresses the auto-show for this session...
			await commands.get("autopilot")?.handler("monitor off", ctx);
			expect(autoStartMonitor(ctx, root)).toBe(false);
			// ...until an explicit on clears the suppression again
			await commands.get("autopilot")?.handler("monitor on", ctx);
			expect(autoStartMonitor(ctx, root)).toBe(true);
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("does not auto-show without a UI, when opted out, or when autopilot is disabled", () => {
		const root = mkdtemp();
		try {
			const { ctx } = fakeCmdCtx(true);
			// disabled config
			writeConfigJson(root, { enabled: false });
			expect(autoStartMonitor(ctx, root)).toBe(false);
			expect(isMonitorActive()).toBe(false);
			// enabled, but the embedding opted out
			writeConfigJson(root, { enabled: true });
			expect(autoStartMonitor(ctx, root, { autoMonitor: false })).toBe(false);
			expect(isMonitorActive()).toBe(false);
			// enabled, but no visual UI (print mode)
			const { ctx: printCtx } = fakeCmdCtx(false);
			expect(autoStartMonitor(printCtx, root)).toBe(false);
			expect(isMonitorActive()).toBe(false);
			// no config at all → never enabled
			const empty = mkdtemp();
			try {
				expect(autoStartMonitor(ctx, empty)).toBe(false);
			} finally {
				fs.rmSync(empty, { recursive: true, force: true });
			}
		} finally {
			stopMonitor();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

describe("autopilot progress section (AC-006/AC-007)", () => {
	it("derives tick freshness, slots, per-key phase/status and advance stalls from files", () => {
		const root = mkdtemp();
		try {
			const now = Date.parse("2026-09-22T10:00:12+00:00");
			writeConfigJson(root, {
				enabled: true,
				paused: false,
				poll_interval_sec: 4,
				max_parallel_keys: 2,
				advance_stall_ticks: 3,
			});
			writeRoadmap(root, [
				{ key: "feature-params-service", status: "stalled", dependsOn: [] },
				{ key: "feature-gui-backend", status: "running", dependsOn: ["feature-params-service"] },
			]);
			writeIndex(root, [
				{ key: "feature-params-service", phase: "VERIFY" },
				{ key: "feature-gui-backend", phase: "EXECUTE" },
			]);
			writeWorkers(root, [
				{
					key: "ap-feature-params-service-repair-a1",
					status: "running",
					dispatchedAt: "2026-09-22T10:00:00+00:00",
					// T-16/AC-021: a conductor row owns its slot via origin + path,
					// not via the `ap-` task-key prefix.
					ownerKey: "feature-params-service",
					origin: "conductor",
				},
			]);
			writeGate(root, {
				id: "gate-0002",
				kind: "stalled",
				stage: null,
				status: "pending",
				key: "feature-params-service",
			});
			const failureTs = "2026-09-22T10:00:00+00:00";
			writeTimeline(root, [
				{ ts: "2026-09-22T09:59:55+00:00", ev: "beat" },
				{ ts: "2026-09-22T10:00:08+00:00", ev: "beat" },
				{
					ts: "2026-09-22T09:59:56+00:00",
					ev: "advance",
					key: "feature-params-service",
					detail: "execute->verify exit=1 class=interface-drift",
				},
				{
					ts: "2026-09-22T09:59:56+00:00",
					ev: "config",
					key: "feature-params-service",
					detail: "advance execute->verify failed: ERROR: unknown phase 'execute（…）'. Valid: spec, design",
				},
				{
					ts: failureTs,
					ev: "advance",
					key: "feature-params-service",
					detail: "execute->verify exit=1 class=interface-drift",
				},
				{
					ts: failureTs,
					ev: "config",
					key: "feature-params-service",
					detail: "advance execute->verify failed: ERROR: unknown phase 'execute（…）'. Valid: spec, design",
				},
				{
					ts: failureTs,
					ev: "advance",
					key: "feature-params-service",
					detail: "execute->verify exit=1 class=interface-drift",
				},
				{
					ts: failureTs,
					ev: "config",
					key: "feature-params-service",
					detail: "advance execute->verify failed: ERROR: unknown phase 'execute（…）'. Valid: spec, design",
				},
				{
					ts: "2026-09-22T10:00:10+00:00",
					ev: "stalled",
					key: "feature-params-service",
					detail: "advance execute->verify 连续 3 次失败",
				},
				{
					ts: "2026-09-22T10:00:10+00:00",
					ev: "gate-created",
					key: "feature-params-service",
					detail: "gate-0002 kind=stalled",
				},
			]);

			const before = hashTree([root]);
			const snap = readMonitorState(root, now);
			expect(hashTree([root])).toBe(before); // AC-007: strictly read-only

			expect(snap.autopilot.enabled).toBe(true);
			expect(snap.autopilot.stallTicks).toBe(3);
			expect(snap.autopilot.tickSeq).toBe(2); // last beat
			expect(snap.autopilot.tickAgeMs).toBe(4000);
			expect(snap.autopilot.tickStale).toBe(false);
			expect(snap.autopilot.slotsUsed).toBe(1);
			expect(snap.autopilot.slotsMax).toBe(2);
			const k1 = snap.autopilot.keys.find((k) => k.key === "feature-params-service");
			expect(k1?.phase).toBe("VERIFY");
			expect(k1?.status).toBe("stalled");
			expect(k1?.inFlight).toBe(1);
			const k2 = snap.autopilot.keys.find((k) => k.key === "feature-gui-backend");
			expect(k2?.blockedBy).toEqual(["feature-params-service"]);
			const stall = snap.autopilot.stalls.find((s) => s.key === "feature-params-service");
			expect(stall?.count).toBe(3);
			expect(stall?.primaryClass).toBe("interface-drift");
			expect(stall?.edge).toBe("execute->verify");
			expect(stall?.lastError).toContain("unknown phase");
			expect(snap.gates.map((g) => g.key)).toEqual(["feature-params-service"]); // key column parsed

			// render: summary + the stalled key row with the recovery command
			const panel = renderMonitorLines(snap).join("\n");
			expect(panel).toContain("autopilot: tick seq 2 (4s ago)");
			expect(panel).toContain("slots 1/2");
			expect(panel).toContain("stall-ticks 3");
			expect(panel).toContain("feature-params-service VERIFY/stalled");
			expect(panel).toContain("advance 3x interface-drift");
			expect(panel).toContain("-> /autopilot gate gate-0002 approve|reject");
			expect(panel).toContain("deps blocked by feature-params-service");
			for (const line of renderMonitorLines(snap)) expect(line.length).toBeLessThanOrEqual(110);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("T-16/AC-021: slot ownership uses origin+path, not the ap- prefix", () => {
		const root = mkdtemp();
		try {
			const now = Date.parse("2026-09-22T10:00:12+00:00");
			writeConfigJson(root, {
				enabled: true,
				paused: false,
				poll_interval_sec: 4,
				max_parallel_keys: 2,
			});
			writeRoadmap(root, [
				{ key: "feature-params-service", status: "running", dependsOn: [] },
				{ key: "feature-gui-backend", status: "running", dependsOn: [] },
			]);
			writeIndex(root, [
				{ key: "feature-params-service", phase: "EXECUTE" },
				{ key: "feature-gui-backend", phase: "EXECUTE" },
			]);
			const row = {
				key: "ap-feature-params-service-repair-a1",
				status: "running",
				dispatchedAt: "2026-09-22T10:00:00+00:00",
				ownerKey: "feature-params-service",
			};
			// A PM-hand-started `ap-` row with no `origin` column reads `manual`
			// (VC-028): the old prefix rule counted it as a conductor slot.
			writeWorkers(root, [row]);
			const manual = readMonitorState(root, now);
			expect(manual.autopilot.slotsUsed).toBe(0);
			expect(manual.autopilot.keys.find((k) => k.key === "feature-params-service")?.inFlight).toBe(0);
			expect(renderMonitorLines(manual).join("\n")).toContain("slots 0/2");

			// Control: stamping origin makes the same row own the slot.
			writeWorkers(root, [{ ...row, origin: "conductor" }]);
			const withOrigin = readMonitorState(root, now);
			expect(withOrigin.autopilot.slotsUsed).toBe(1);
			expect(withOrigin.autopilot.keys.find((k) => k.key === "feature-params-service")?.inFlight).toBe(1);
			expect(renderMonitorLines(withOrigin).join("\n")).toContain("slots 1/2");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("flags a stale tick when the conductor stopped beating", () => {
		const root = mkdtemp();
		try {
			const now = Date.parse("2026-09-22T10:10:00+00:00");
			writeConfigJson(root, { enabled: true });
			writeRoadmap(root, [{ key: "k1", status: "running", dependsOn: [] }]);
			writeIndex(root, [{ key: "k1", phase: "EXECUTE" }]);
			writeTimeline(root, [{ ts: "2026-09-22T10:00:00+00:00", ev: "beat" }]);
			const snap = readMonitorState(root, now);
			expect(snap.autopilot.tickAgeMs).toBe(600_000);
			expect(snap.autopilot.tickStale).toBe(true);
			expect(renderMonitorLines(snap).join("\n")).toContain("STALE (conductor not ticking)");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("degrades to placeholders for an empty project (no config/roadmap/index/timeline)", () => {
		const root = mkdtemp();
		try {
			const snap = readMonitorState(root, Date.now());
			expect(snap.autopilot.everEnabled).toBe(false);
			expect(snap.autopilot.tickSeq).toBeNull();
			expect(snap.autopilot.keys).toEqual([]);
			expect(renderMonitorLines(snap).join("\n")).toContain("autopilot: not enabled");
			// enabled config but no roadmap/index/timeline yet: placeholders, no throw
			writeConfigJson(root, { enabled: true });
			const partial = readMonitorState(root, Date.now());
			expect(partial.autopilot.enabled).toBe(true);
			expect(partial.autopilot.tickSeq).toBeNull();
			expect(renderMonitorLines(partial).join("\n")).toContain("tick: none yet");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("stall derivation: success clears the run, other events do not, other edges are ignored", () => {
		const now = Date.parse("2026-09-22T10:00:00+00:00");
		const ev = (seq: number, evName: string, detail: string, key = "k1"): TimelineEvent => ({
			ts: "2026-09-22T10:00:00+00:00",
			seq,
			ev: evName,
			key,
			stage: null,
			detail,
		});
		const run = deriveAdvanceStalls(
			[
				ev(1, "advance", "execute->verify exit=1 class=other"),
				ev(2, "stalled", "advance execute->verify 连续 2 次失败"),
				ev(3, "advance", "execute->verify exit=1 class=interface-drift"),
				ev(4, "config", "advance execute->verify failed: ERROR: unknown phase 'x'"),
			],
			now,
		);
		expect(run).toHaveLength(1);
		expect(run[0]?.count).toBe(2); // the `stalled` event does not break the run
		expect(run[0]?.primaryClass).toBe("interface-drift");
		expect(run[0]?.lastError).toContain("unknown phase");
		const cleared = deriveAdvanceStalls(
			[ev(1, "advance", "execute->verify exit=1 class=other"), ev(2, "advance", "execute->verify exit=0")],
			now,
		);
		expect(cleared).toEqual([]);
		const otherEdge = deriveAdvanceStalls(
			[
				ev(1, "advance", "tasks->execute exit=1 class=other"),
				ev(2, "advance", "execute->verify exit=1 class=other"),
			],
			now,
		);
		expect(otherEdge[0]?.edge).toBe("execute->verify");
		expect(otherEdge[0]?.count).toBe(1);
		// a success on a *different* edge must not end this run: the conductor
		// skips a neighbouring boundary's advance, so it keeps counting
		const crossEdge = deriveAdvanceStalls(
			[
				ev(1, "advance", "execute->verify exit=1 class=other"),
				ev(2, "advance", "tasks->execute exit=0"),
				ev(3, "advance", "execute->verify exit=1 class=other"),
			],
			now,
		);
		expect(crossEdge).toHaveLength(1);
		expect(crossEdge[0]?.edge).toBe("execute->verify");
		expect(crossEdge[0]?.count).toBe(2);
		// failures older than this edge's own success never revive
		const notRevived = deriveAdvanceStalls(
			[
				ev(1, "advance", "execute->verify exit=1 class=other"),
				ev(2, "advance", "execute->verify exit=0"),
				ev(3, "advance", "execute->verify exit=1 class=other"),
			],
			now,
		);
		expect(notRevived).toEqual([]);
	});

	it("timeline tail read is bounded and tolerates torn lines", () => {
		const root = mkdtemp();
		try {
			writeTimeline(root, [
				{ ev: "beat" },
				{ ev: "beat" },
				{ ev: "advance", key: "k1", detail: "execute->verify exit=1 class=other" },
			]);
			const file = path.join(root, ".agenticdoc", "_autopilot", "timeline.jsonl");
			fs.appendFileSync(file, "{torn\n", "utf8");
			const tail = readTimelineTail(file, { limit: 2 });
			expect(tail).toHaveLength(2);
			expect(tail[1]?.ev).toBe("advance");
			expect(readTimelineTail(path.join(root, "missing.jsonl"))).toEqual([]);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("config mirror: advance_stall_ticks validates, defaults, and round-trips", () => {
		const root = mkdtemp();
		try {
			// written by the Python side (which now always emits the field)
			writeConfigJson(root, { enabled: true, advance_stall_ticks: 7 });
			const cfg = readConfig(root);
			expect(cfg.ok).toBe(true);
			expect(cfg.ok && cfg.config.advance_stall_ticks).toBe(7);
			expect(DEFAULT_CONFIG.advance_stall_ticks).toBe(5);
			expect(validateConfigData({ advance_stall_ticks: 0 }).join(";")).toContain("must be >= 1");
			expect(validateConfigData({ advance_stall_ticks: 51 }).join(";")).toContain("must be <= 50");
			expect(validateConfigData({ advance_stall_ticks: "5" }).join(";")).toContain("expected integer");
			// absent field → default (old config files keep working)
			writeConfigJson(root, { enabled: true });
			const legacy = readConfig(root);
			expect(legacy.ok && legacy.config.advance_stall_ticks).toBe(5);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
