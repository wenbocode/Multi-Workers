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
import { registerAutopilotCommands } from "../../src/extensions/agent-team-loop/autopilot/console.ts";
import {
	isMonitorActive,
	MONITOR_WIDGET_ID,
	type MonitorSnapshot,
	readMonitorState,
	renderMonitorLines,
	startMonitor,
	stopMonitor,
} from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
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

/** _workers.parallel rows in the 8-column WorkerStore format. */
function writeWorkers(root: string, rows: Array<{ key: string; status: string; dispatchedAt: string }>): void {
	const agenticdoc = path.join(root, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	const lines = rows.map(
		(r) =>
			`${r.key} | ${r.status} | pi | timi | ${path.join(agenticdoc, "_scratch", "workers", r.key, "task.md")} | ` +
			`${r.dispatchedAt} | ${r.dispatchedAt} | `,
	);
	fs.writeFileSync(path.join(agenticdoc, "_workers.parallel"), `${lines.join("\n")}\n`, "utf8");
}

/** A gate file in the gates.py frontmatter shape (line-scan compatible). */
function writeGate(root: string, g: { id: string; kind: string; stage: number | null; status: string }): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot", "gates");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, `${g.id}.md`),
		[
			"---",
			`id: ${g.id}`,
			`kind: ${g.kind}`,
			`stage: ${g.stage === null ? "" : g.stage}`,
			"key:",
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
			expect(lines[0]).toBe("[autopilot monitor]");
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
			expect(widgets[0]?.content?.[0]).toBe("[autopilot monitor]");
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
			workers: [],
			gates: [],
		}).join("\n");
		expect(paused).toContain("serve: not running -> /mw restart");
		expect(paused).toContain("conductor: PID 123 alive | autopilot enabled, paused");
		expect(paused).toContain("workers: 0 running");
		expect(paused).toContain("gates: 0 pending");

		const never = renderMonitorLines({
			serve: { running: true, pid: 7, stale: true, staleDetail: "serve started X, mw code changed Y", upMs: 1 },
			conductor: { pid: null, alive: false, enabled: false, paused: false, everEnabled: false },
			workers: [],
			gates: [],
		}).join("\n");
		expect(never).toContain("serve: PID 7 STALE CODE (serve started X, mw code changed Y) -> /mw restart");
		expect(never).toContain("conductor: not enabled (/autopilot enable)");

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
			workers: [],
			gates: [],
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
				workers: [{ taskKey: "ap-x-t01", elapsedMs: 180_000 }],
				gates: [{ id: "gate-0002", kind: "stage-confirm", stage: 2 }],
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
		const calls: Array<{ key: string; content: string[] | undefined; options?: { placement?: string } }> = [];
		const ctx = {
			hasUI: true,
			ui: {
				notify: () => {},
				setWidget: (key: string, content: string[] | undefined, options?: { placement?: string }) => {
					store.set(key, content);
					calls.push({ key, content, options });
				},
			},
			sessionManager: { getEntries: () => [] },
		} as unknown as ExtensionCommandContext;

		const snapshot: MonitorSnapshot = {
			serve: { running: true, pid: 27572, stale: false, staleDetail: "", upMs: 240_000 },
			conductor: { pid: 99000, alive: true, enabled: true, paused: false, everEnabled: true },
			workers: [],
			gates: [],
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
			expect(store.get("agent-team-loop-monitor")?.[0]).toBe("[autopilot monitor]");

			// Two distinct ids, both live — neither overwrote the other.
			expect(new Set(calls.map((c) => c.key))).toEqual(
				new Set(["agent-team-loop-watch", "agent-team-loop-monitor"]),
			);
			expect(store.get("agent-team-loop-watch")?.[0]).toContain("[mw] ap-x");
			expect(store.get("agent-team-loop-monitor")?.join("\n")).toContain("serve: PID 27572 fresh");
			// Both widgets stack below the editor (design D-003).
			expect(calls.every((c) => c.options?.placement === "belowEditor")).toBe(true);

			// Interleaved refresh — one monitor tick, then a watch refresh:
			// each re-render touches only its own id; both frames stay live.
			vi.advanceTimersByTime(100);
			expect(store.get("agent-team-loop-watch")?.[0]).toContain("[mw] ap-x");
			setWatchWidget(ctx, ["[mw] ap-x | phase=3 | 1 running"]);
			expect(store.get("agent-team-loop-monitor")?.[0]).toBe("[autopilot monitor]");
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
