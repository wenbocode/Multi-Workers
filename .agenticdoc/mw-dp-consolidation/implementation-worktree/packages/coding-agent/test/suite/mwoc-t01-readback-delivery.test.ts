/**
 * mw-worker-output-contract T-03 (W5): terminal-readback delivery scope.
 *
 * AC-011: a terminal row whose owner key is not the watched key is NOT recorded
 * as delivered; taking over the owner key replays it exactly once (C1), while
 * "no watched key" stays silent AND consumed (C3).
 * AC-012: an open-time terminal row is never replayed (option B), but the
 * watched-key widget carries an `N unread` tail until it is acked.
 * AC-013: with no watched key the window renders ONE `N unread` line (or clears
 * when N=0) and never broadcasts a message.
 *
 * Pure file fixtures + a fake pi + fake timers; no provider APIs, keys, or
 * network. Precedent for a harness-free suite test: mwgal-t10-state-surface.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import { startWorkerPollLoop } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import type { PmUiHolder, PmWatchState } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { type WorkerStatus, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "mwoc-t01-"));
}

/** Fake pi recording injected-message content and the sendMessage options. */
function fakePi(): { pi: ExtensionAPI; messages: string[]; options: Array<{ triggerTurn?: boolean } | undefined> } {
	const messages: string[] = [];
	const options: Array<{ triggerTurn?: boolean } | undefined> = [];
	const pi = {
		sendMessage: (m: { content: string }, opts?: { triggerTurn?: boolean }) => {
			messages.push(m.content);
			options.push(opts);
		},
		appendEntry: () => undefined,
	} as unknown as ExtensionAPI;
	return { pi, messages, options };
}

/** Fake ExtensionContext whose setWidget calls are captured in order. */
function fakeUiCtx(): { ctx: ExtensionContext; widgets: Array<string[] | undefined> } {
	const widgets: Array<string[] | undefined> = [];
	const ctx = {
		hasUI: true,
		ui: {
			setWidget: (_key: string, content: string[] | undefined) => {
				widgets.push(content);
			},
		},
	} as unknown as ExtensionContext;
	return { ctx, widgets };
}

/** Queue a task row (with output.md) under {owner}/workers/{taskKey}/. */
async function queueTask(root: string, owner: string, taskKey: string, status: WorkerStatus): Promise<void> {
	const taskDir = path.join(root, owner, "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
	fs.writeFileSync(path.join(taskDir, "output.md"), "## Summary\n\ndid the thing\n", "utf8");
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

async function setStatus(store: WorkerStore, taskKey: string, status: WorkerStatus): Promise<void> {
	const entry = store.findByKey(taskKey);
	if (!entry) throw new Error(`${taskKey} missing from queue`);
	await store.upsert({ ...entry, status });
}

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

const count = (messages: string[], taskKey: string): number =>
	messages.filter((m) => m.includes(`[${taskKey}]`)).length;

describe("mwoc AC-011/AC-012/AC-013 terminal readback delivery scope", () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it("AC-011: takeover replays an un-notified cross-key terminal row exactly once", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "keyA");
		await activateKey(root, "keyB");
		await activateKey(root, "keyC");
		// a1 running + a2 done under the watched key (a2 is the open-time
		// baseline); b1 running under another key; c1 done under a never-watched
		// key (also baseline).
		await queueTask(root, "keyA", "a1", "running");
		await queueTask(root, "keyA", "a2", "done");
		await queueTask(root, "keyB", "b1", "running");
		await queueTask(root, "keyC", "c1", "done");
		const watch: PmWatchState = { key: "keyA" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);

			// P1: nothing terminal has transitioned yet.
			vi.advanceTimersByTime(300);
			expect(messages).toHaveLength(0);

			// P2: b1 goes terminal while another key is watched — owner gate keeps
			// this window silent AND must not consume the transition (C1).
			await setStatus(store, "b1", "done");
			vi.advanceTimersByTime(400);
			expect(count(messages, "b1")).toBe(0);

			// P3 (C1): taking over keyB replays b1 exactly once.
			watch.key = "keyB";
			vi.advanceTimersByTime(800);
			expect(count(messages, "b1")).toBe(1);
			const step3 = messages.length;
			expect(step3).toBe(1);

			// P4: a control row that goes terminal UNDER the watched key is pushed
			// once more (relative to the takeover delivery).
			await queueTask(root, "keyB", "b2", "running");
			vi.advanceTimersByTime(200);
			await setStatus(store, "b2", "done");
			vi.advanceTimersByTime(400);
			expect(count(messages, "b2")).toBe(1);
			expect(messages.length).toBe(step3 + 1);

			// P5: an open-time terminal row under the watched key is history.
			expect(count(messages, "a2")).toBe(0);

			// P6: c1 was terminal at open under an unwatched key — never replayed,
			// and b1 stays at one delivery across all later ticks.
			watch.key = "keyC";
			vi.advanceTimersByTime(600);
			expect(count(messages, "c1")).toBe(0);
			expect(count(messages, "b1")).toBe(1);
			console.log("[VERIFY] mwoc-AC-011: P1..P6 pass; b1 replayed exactly once after takeover");
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-012: an open-time terminal row is not replayed but counted unread", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "keyA");
		await queueTask(root, "keyA", "r1", "done");
		const watch: PmWatchState = { key: "keyA" };
		const { ctx, widgets } = fakeUiCtx();
		const ui: PmUiHolder = { ctx };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			vi.advanceTimersByTime(400);
			// Option B: the open-time terminal row is not replayed ...
			expect(count(messages, "r1")).toBe(0);
			// ... but the unread tail surfaces it. Mechanical criterion: the widget
			// contains a `1 unread` line.
			const beforeAck = widgets.at(-1);
			expect(beforeAck).toBeDefined();
			expect(beforeAck?.some((l) => l.includes("1 unread"))).toBe(true);

			// Acking moves it out of the unread set: the tail disappears.
			await new AckStore(root).ack(["r1"]);
			vi.advanceTimersByTime(400);
			const afterAck = widgets.at(-1);
			expect(afterAck).toBeDefined();
			expect(afterAck?.some((l) => l.includes("unread"))).toBe(false);
			expect(count(messages, "r1")).toBe(0);
			console.log(`[VERIFY] mwoc-AC-012: unread tail=${beforeAck?.find((l) => l.includes("unread"))}`);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-013: a window with no watched key surfaces N without broadcasting", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "keyA");
		await activateKey(root, "keyB");
		// Both terminal before the window opens and neither acked: N = 2.
		await queueTask(root, "keyA", "x1", "done");
		await queueTask(root, "keyB", "x2", "failed");
		const watch: PmWatchState = { key: undefined };
		const { ctx, widgets } = fakeUiCtx();
		const ui: PmUiHolder = { ctx };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			vi.advanceTimersByTime(400);
			// No cross-key broadcast, even though two keys have terminal rows.
			expect(messages).toHaveLength(0);
			const waiting = widgets.at(-1);
			expect(waiting).toBeDefined();
			expect(waiting).toHaveLength(1);
			expect(waiting?.[0]).toContain("2 unread");

			// N drops to zero once every terminal row is acked -> widget cleared.
			await new AckStore(root).ack(["x1", "x2"]);
			vi.advanceTimersByTime(400);
			expect(widgets.at(-1)).toBeUndefined();
			expect(messages).toHaveLength(0);
			console.log(`[VERIFY] mwoc-AC-013: no-watch widget=${waiting?.[0]}; cleared at N=0`);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
