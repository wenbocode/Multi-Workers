import { createHash, randomUUID } from "node:crypto";
import {
	existsSync,
	mkdirSync,
	mkdtempSync,
	readdirSync,
	readFileSync,
	realpathSync,
	rmSync,
	writeFileSync,
} from "node:fs";
import { hostname, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterAll, beforeAll, expect, it, vi } from "vitest";
import { lockDutyTarget } from "../../../multi-workers/pm_duty_lease.ts";
import registerDuty from "../../../multi-workers/window_duty_extension.ts";
import { receiverSettings } from "../../../multi-workers/window_duty_setup.ts";
import type {
	ExtensionAPI,
	ExtensionCommandContext,
	RegisteredCommand,
	ToolDefinition,
} from "../../src/core/extensions/types.ts";
import { PmChannel, registerPmChannel } from "../../src/extensions/agent-team-loop/pm/codex-channel.ts";
import { createHarness, type Harness } from "./harness.ts";

const KEY = "target-key";
const FOLLOWUP_TYPE = "mw:duty-followup";

type Handler = (...args: unknown[]) => unknown;
interface Captured {
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
	tools: Map<string, ToolDefinition>;
	events: Map<string, Handler>;
}

/** The worker-task marker is a process-level switch: a supervisor extension must register in tests. */
let savedWorkerTask: string | undefined;
beforeAll(() => {
	savedWorkerTask = process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_TASK;
});
afterAll(() => {
	if (savedWorkerTask !== undefined) process.env.PI_WORKER_TASK = savedWorkerTask;
});

function registerCaptured(pi: ExtensionAPI, home: string, captured: Captured) {
	const proxy = new Proxy(pi, {
		get(target, prop, receiver) {
			if (prop === "registerCommand")
				return (name: string, def: Omit<RegisteredCommand, "name" | "sourceInfo">) => {
					captured.commands.set(name, def.handler);
					return target.registerCommand(name, def);
				};
			if (prop === "registerTool")
				return (def: ToolDefinition) => {
					captured.tools.set(def.name, def);
					return target.registerTool(def);
				};
			if (prop === "on")
				return (event: string, handler: Handler) => {
					captured.events.set(event, handler);
					return (target.on as unknown as (name: string, fn: Handler) => void)(event, handler);
				};
			const value = Reflect.get(target, prop, receiver);
			return typeof value === "function" ? (value as (...args: unknown[]) => unknown).bind(target) : value;
		},
	});
	registerDuty(proxy, home);
}

/** Deterministic 5s/2.5s interval driving; no wall-clock wait and no provider callbacks in the timer. */
function controlledIntervals() {
	const callbacks = new Map<object, () => void>();
	const realSet = globalThis.setInterval;
	const realClear = globalThis.clearInterval;
	let created = 0;
	let cleared = 0;
	const setSpy = vi.spyOn(globalThis, "setInterval");
	setSpy.mockImplementation(((callback: () => void) => {
		const handle = realSet(() => {}, 2_147_000_000);
		handle.unref();
		created++;
		callbacks.set(handle, callback);
		return handle;
	}) as unknown as typeof globalThis.setInterval);
	const clearSpy = vi.spyOn(globalThis, "clearInterval");
	clearSpy.mockImplementation(((handle: object) => {
		cleared++;
		callbacks.delete(handle);
		realClear(handle as NodeJS.Timeout);
	}) as unknown as typeof globalThis.clearInterval);
	return {
		tick() {
			for (const callback of [...callbacks.values()]) callback();
		},
		get count() {
			return callbacks.size;
		},
		get created() {
			return created;
		},
		get cleared() {
			return cleared;
		},
		restore() {
			setSpy.mockRestore();
			clearSpy.mockRestore();
			for (const handle of callbacks.keys()) realClear(handle as NodeJS.Timeout);
			callbacks.clear();
		},
	};
}

function makeCtx(
	h: Harness,
	flags: { idle: boolean; pending: boolean },
	notices: Array<{ msg: string; kind?: string }>,
	session: string | { value: string } = h.sessionManager.getSessionId(),
) {
	const sessionRef = typeof session === "string" ? { value: session } : session;
	return {
		cwd: h.tempDir,
		mode: "tui",
		hasUI: true,
		sessionManager: { getSessionId: () => sessionRef.value },
		isIdle: () => flags.idle,
		hasPendingMessages: () => flags.pending,
		ui: {
			notify: (msg: string, kind?: string) => notices.push({ msg, kind }),
			confirm: async () => true,
			select: async () => undefined,
			input: async () => undefined,
		},
	} as unknown as ExtensionCommandContext;
}

async function waitFor(predicate: () => boolean, timeoutMs = 5000) {
	const start = Date.now();
	while (!predicate()) {
		if (Date.now() - start > timeoutMs) throw Error("Timed out waiting for the real agent turn");
		await new Promise<void>((resolve) => setTimeout(resolve, 25));
	}
}

function followupMessages(h: Harness) {
	return h.session.messages.filter(
		(message) =>
			message.role === "custom" &&
			(message as { customType?: string }).customType === FOLLOWUP_TYPE &&
			typeof (message as { details?: { id?: string } }).details?.id === "string",
	) as Array<{
		role: "custom";
		customType: string;
		content: string;
		details: { id: string; kind: string; summary: string };
	}>;
}

function requestFiles(channel: PmChannel, binding: string) {
	const directory = join(channel.dir, KEY, binding);
	if (!existsSync(directory)) return [] as string[];
	return readdirSync(directory).filter((name) => name.endsWith(".request.json"));
}

interface Fixture {
	home: string;
	original: Harness;
	duty: Harness;
	channel: PmChannel;
	binding: string;
	flags: { idle: boolean; pending: boolean };
	notices: Array<{ msg: string; kind?: string }>;
	clock: { offset: number };
	control: ReturnType<typeof controlledIntervals>;
	captured: Captured;
	command(name: string, args: string, ctx?: ExtensionCommandContext): Promise<void>;
	tool(name: string, params: object, ctx?: ExtensionCommandContext): Promise<{ details: unknown }>;
	status(ctx?: ExtensionCommandContext): Promise<Record<string, unknown>>;
	ctx: ExtensionCommandContext;
	cleanup(): Promise<void>;
}

type DutyLease = Awaited<ReturnType<typeof lockDutyTarget>>;

async function releaseLease(lease: DutyLease) {
	await new Promise<void>((resolve) => lease.close(() => resolve()));
}

async function assertLeasesReleased(directory: string, key: string) {
	for (let attempt = 0; attempt < 2; attempt++) {
		const monitor = await lockDutyTarget(directory, key);
		const send = await lockDutyTarget(directory, key, "send");
		expect(monitor.listening).toBe(true);
		expect(send.listening).toBe(true);
		await releaseLease(monitor);
		await releaseLease(send);
	}
}

function samePinsLedger(f: Fixture) {
	const project = realpathSync.native(f.original.tempDir);
	const claim = `${hostname()}:${process.pid}`;
	const pinned = createHash("sha256")
		.update(
			JSON.stringify([
				process.platform === "win32" ? project.toLowerCase() : project,
				KEY.trim().toLowerCase(),
				claim.trim(),
				f.binding.trim(),
				f.original.sessionManager.getSessionId().trim(),
			]),
		)
		.digest("hex");
	const now = Date.now();
	const stopId = randomUUID();
	const ledger = {
		schema: "mw-duty-followup-v1",
		version: 1,
		pinned,
		activeStopId: stopId,
		stableSince: null,
		lastState: "working",
		lastDetail: "",
		stops: [
			{
				id: stopId,
				state: "idle",
				detail: "",
				fingerprint: "a".repeat(64),
				evidenceFingerprint: "b".repeat(64),
				evidence: [],
				stableSince: now - 46_000,
				createdAt: now - 46_000,
				noticeCreated: true,
				noticeEmitted: true,
				noProgressCreated: false,
				noProgressEmitted: false,
			},
		],
		outbox: [
			{
				id: stopId,
				stopId,
				pinned,
				body: "Unresolved bounded status request",
				createdAt: now - 46_000,
				updatedAt: now - 46_000,
				attempts: 1,
				transport: "uncertain",
				receiptState: "queued",
				uncertain: true,
			},
		],
		notices: [],
		diagnoses: [],
	};
	return {
		pinned,
		bytes: JSON.stringify(ledger),
		reboundBytes: JSON.stringify({ ...ledger, pinned: "f".repeat(64) }),
	};
}

async function setup(): Promise<Fixture> {
	const home = mkdtempSync(join(tmpdir(), "mw-duty-c2-"));
	const control = controlledIntervals();
	const captured: Captured = { commands: new Map(), tools: new Map(), events: new Map() };
	const original = await createHarness({
		extensionFactories: [(pi: ExtensionAPI) => registerPmChannel(pi, home)],
	});
	const duty = await createHarness({
		extensionFactories: [(pi: ExtensionAPI) => registerCaptured(pi, home, captured)],
	});
	const doc = join(original.tempDir, ".agenticdoc");
	mkdirSync(join(doc, KEY), { recursive: true });
	writeFileSync(join(doc, "_index.parallel"), `| ${KEY} | active | EXECUTE | ${hostname()}:${process.pid} | | | |\n`);
	writeFileSync(join(doc, "_workers.parallel"), "");
	writeFileSync(join(doc, KEY, "pm-state.md"), "- Phase: EXECUTE\n- Next Action: test\n");
	// Receiver wiring is already in place: these tests exercise activation, not first install.
	receiverSettings(original.tempDir).install();
	await original.session.bindExtensions({ mode: "tui" });
	await duty.session.bindExtensions({ mode: "tui" });
	const channel = new PmChannel(original.tempDir, home);
	const binding = channel.status(KEY).binding!;
	if (!binding) throw Error("Original PM heartbeat missing");
	const flags = { idle: true, pending: false };
	const notices: Array<{ msg: string; kind?: string }> = [];
	const ctx = makeCtx(duty, flags, notices);
	const clock = { offset: 0 };
	const wall = Date.now.bind(Date);
	vi.spyOn(Date, "now").mockImplementation(() => wall() + clock.offset);
	const command = async (name: string, args: string, override?: ExtensionCommandContext) => {
		const handler = captured.commands.get(name);
		if (!handler) throw Error(`Missing command ${name}`);
		await handler(args, override ?? ctx);
	};
	const tool = async (name: string, params: object, override?: ExtensionCommandContext) => {
		const definition = captured.tools.get(name);
		if (!definition) throw Error(`Missing tool ${name}`);
		return (await definition.execute("test", params, undefined, undefined, override ?? ctx)) as {
			details: unknown;
		};
	};
	return {
		home,
		original,
		duty,
		channel,
		binding,
		flags,
		notices,
		clock,
		control,
		captured,
		command,
		tool,
		status: async (override?: ExtensionCommandContext) =>
			(await tool("mw_duty_status", {}, override)).details as Record<string, unknown>,
		ctx,
		async cleanup() {
			control.restore();
			vi.restoreAllMocks();
			await duty.session.dispose();
			await original.session.dispose();
			duty.cleanup();
			original.cleanup();
			rmSync(home, { recursive: true, force: true });
		},
	};
}

it("passive observation stays silent: zero agent turns, zero follow-up sends, truthful mode", async () => {
	const f = await setup();
	try {
		await f.command("duty-on", `"${f.original.tempDir}" ${KEY}`);
		const status = await f.status();
		expect(status.mode).toBe("observation");
		expect(status.businessProgress).toBe("unverified");
		expect((status.pinnedTargets as Array<{ key: string }>)[0].key).toBe(KEY);
		const timers = f.control.count;
		f.clock.offset = 46_000;
		f.control.tick();
		f.control.tick();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(0);
		expect(f.duty.faux.state.callCount).toBe(0);
		expect(followupMessages(f.duty)).toHaveLength(0);
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
		await expect(f.tool("mw_duty_followup", { id: randomUUID(), note: "Should be refused" })).rejects.toThrow(
			/not active|requires/i,
		);
		expect(f.control.count).toBe(timers);
	} finally {
		await f.cleanup();
	}
});

it("explicit follow-up reports the pinned target and wakes the real agent once for >=45s idle", async () => {
	const f = await setup();
	try {
		f.duty.setResponses([fauxAssistantMessage("Supervisor inspected the notice")]);
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		const status = await f.status();
		expect(status.mode).toBe("followup");
		expect((status.pinnedTargets as Array<{ key: string; session: string }>)[0]).toMatchObject({
			key: KEY,
			claim: `${hostname()}:${process.pid}`,
		});
		expect(status.businessProgress).toBe("unverified");
		f.control.tick();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(0);
		f.clock.offset = 46_000;
		f.control.tick();
		await waitFor(() => f.duty.eventsOfType("agent_start").length === 1);
		expect(f.duty.faux.state.callCount).toBe(1);
		const messages = followupMessages(f.duty);
		expect(messages).toHaveLength(1);
		expect(messages[0].details.kind).toBe("stop");
		expect(messages[0].content).toContain("businessProgress=unverified");
		expect(messages[0].content).toContain("Inspect the real engineering evidence");
		f.control.tick();
		f.control.tick();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(1);
		expect(followupMessages(f.duty)).toHaveLength(1);
	} finally {
		await f.cleanup();
	}
}, 20000);

it("a busy or pending supervisor retains the notice and wakes once after it becomes idle", async () => {
	const f = await setup();
	try {
		f.duty.setResponses([fauxAssistantMessage("Supervisor inspected the deferred notice")]);
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		f.flags.idle = false;
		f.clock.offset = 46_000;
		f.control.tick();
		f.control.tick();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(0);
		expect(followupMessages(f.duty)).toHaveLength(0);
		f.flags.idle = true;
		f.flags.pending = true;
		f.control.tick();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(0);
		f.flags.pending = false;
		f.control.tick();
		await waitFor(() => f.duty.eventsOfType("agent_start").length === 1);
		expect(followupMessages(f.duty)).toHaveLength(1);
		f.control.tick();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(1);
	} finally {
		await f.cleanup();
	}
}, 20000);

it("the formal tool sends one stable-ID request, retries idempotently and keeps progress unverified", async () => {
	const f = await setup();
	try {
		f.duty.setResponses([
			() => {
				const notice = followupMessages(f.duty).at(-1);
				if (!notice) throw Error("No emitted notice in the real session context");
				return fauxAssistantMessage(
					fauxToolCall("mw_duty_followup", { id: notice.details.id, note: "Verify the pinned state" }),
					{ stopReason: "toolUse" },
				);
			},
			fauxAssistantMessage("Follow-up tool result received"),
		]);
		f.original.setResponses([fauxAssistantMessage("Original PM acknowledging the bounded request")]);
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		f.clock.offset = 46_000;
		f.control.tick();
		await waitFor(() => followupMessages(f.duty).length === 1);
		const id = followupMessages(f.duty)[0].details.id;
		await waitFor(() => requestFiles(f.channel, f.binding).length === 1, 6000);
		const requestPath = f.channel.messagePath(KEY, f.binding, id, "request");
		expect(existsSync(requestPath)).toBe(true);
		const request = JSON.parse(readFileSync(requestPath, "utf8"));
		expect(request.id).toBe(id);
		expect(request.source).toBe("mw-followup");
		expect(request.text).toContain("MW/pi bounded follow-up");
		expect(request.text).toContain("Verify the pinned state");
		// The real original-PM receiver consumes the request and writes a correlated receipt.
		f.control.tick();
		await waitFor(() => existsSync(f.channel.messagePath(KEY, f.binding, id, "receipt")), 6000);
		await waitFor(() => f.original.eventsOfType("agent_start").length >= 1, 6000);
		await waitFor(() => String(f.channel.receipt(KEY, f.binding, id).state) !== "queued", 6000);
		const correlated = await f.status();
		expect(
			(correlated.receipts as Array<{ id: string; businessProgress: string }>).some(
				(entry) => entry.id === id && entry.businessProgress === "unverified",
			),
		).toBe(true);
		expect(correlated.businessProgress).toBe("unverified");
		const retry = await f.tool("mw_duty_followup", { id, note: "Verify the pinned state" });
		expect((retry.details as { businessProgress: string }).businessProgress).toBe("unverified");
		expect(requestFiles(f.channel, f.binding)).toHaveLength(1);
		await expect(f.tool("mw_duty_followup", { id, note: "Changed note" })).rejects.toThrow();
		expect(requestFiles(f.channel, f.binding)).toHaveLength(1);
		await expect(f.tool("mw_duty_followup", { id: randomUUID(), note: "x".repeat(3000) })).rejects.toThrow();
		const status = await f.status();
		expect(status.businessProgress).toBe("unverified");
		expect(status.mode).toBe("followup");
	} finally {
		await f.cleanup();
	}
}, 25000);

it("same-target re-entry and observer upgrade keep one timer and the exclusive leases", async () => {
	const f = await setup();
	try {
		await f.command("duty-on", `"${f.original.tempDir}" ${KEY}`);
		const baseline = f.control.count;
		await f.command("duty-on", `"${f.original.tempDir}" ${KEY}`);
		expect((await f.status()).mode).toBe("observation");
		expect(f.control.count).toBe(baseline);
		expect(f.notices.some((n) => n.msg.includes("Duty already active"))).toBe(true);
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		expect((await f.status()).mode).toBe("followup");
		expect(f.control.count).toBe(baseline);
		// The observer's monitor lease is retained, not taken twice; both leases are exclusive.
		await expect(lockDutyTarget(f.channel.dir, KEY)).rejects.toThrow();
		await expect(lockDutyTarget(f.channel.dir, KEY, "send")).rejects.toThrow();
		await expect(f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`)).resolves.toBeUndefined();
		await f.command("duty-on", `"${f.original.tempDir}" ${KEY}`);
		expect((await f.status()).mode).toBe("followup");
		expect(f.control.count).toBe(baseline);
		await expect(f.command("duty-followup-on", `"${f.original.tempDir}" other-key`)).rejects.toThrow(
			/different target|duty-off/i,
		);
		const shiftCard = join(f.home, "shift.json");
		writeFileSync(shiftCard, "{}");
		await expect(f.command("duty-followup-on", `"${shiftCard}"`)).rejects.toThrow(/explicit follow-up target/);
		expect((await f.status()).mode).toBe("followup");
	} finally {
		await f.cleanup();
	}
});

it("a refused observer upgrade preserves its registered observation timer, truthful mode and both leases", async () => {
	const f = await setup();
	try {
		const args = `"${f.original.tempDir}" ${KEY}`;
		expect(f.captured.commands.has("duty-followup-on")).toBe(true);
		await f.command("duty-on", args);
		const before = await f.status();
		expect(before.mode).toBe("observation");
		const timersBefore = f.control.count;
		const createdBefore = f.control.created;
		const clearedBefore = f.control.cleared;
		const ledgerPath = join(f.channel.dir, KEY, "duty-followup", "ledger.json");
		mkdirSync(dirname(ledgerPath), { recursive: true });
		const valid = samePinsLedger(f);
		expect(valid.pinned).toMatch(/^[a-f0-9]{64}$/);

		writeFileSync(ledgerPath, "{invalid");
		await expect(f.command("duty-followup-on", args)).rejects.toThrow(/Malformed follow-up ledger: invalid JSON/);
		writeFileSync(ledgerPath, valid.reboundBytes);
		await expect(f.command("duty-followup-on", args)).rejects.toThrow(/Malformed or rebound follow-up ledger/);
		console.log(
			JSON.stringify({
				probe: "upgrade-rollback",
				timersBefore,
				timersAfter: f.control.count,
				createdBefore,
				createdAfter: f.control.created,
				clearedBefore,
				clearedAfter: f.control.cleared,
			}),
		);
		expect(f.control.count).toBe(timersBefore);
		expect(f.control.created).toBe(createdBefore);
		expect(f.control.cleared).toBe(clearedBefore);
		const afterFailure = await f.status();
		expect(afterFailure.mode).toBe("observation");
		expect(afterFailure.supervisorSession).toBe(before.supervisorSession);
		expect(
			(afterFailure.pinnedTargets as Array<{ key: string; claim: string; binding: string; session: string }>)[0],
		).toMatchObject({ key: KEY, claim: "", binding: "", session: "" });
		await expect(f.tool("mw_duty_followup", { id: randomUUID(), note: "Should be refused" })).rejects.toThrow(
			/not active|requires/i,
		);
		await f.command("duty-on", args);
		expect(f.notices.some((n) => n.msg.includes("Duty already active"))).toBe(true);
		expect((await f.status()).mode).toBe("observation");
		expect(f.control.count).toBe(timersBefore);

		// The attempted send lease is free; the original monitor lease is still exclusive.
		await expect(lockDutyTarget(f.channel.dir, KEY)).rejects.toThrow();
		const send = await lockDutyTarget(f.channel.dir, KEY, "send");
		await expect(lockDutyTarget(f.channel.dir, KEY)).rejects.toThrow();
		await releaseLease(send);
		const sendAgain = await lockDutyTarget(f.channel.dir, KEY, "send");
		await releaseLease(sendAgain);

		// The original observer still polls and emits a meaningful observation notice.
		const noticesBefore = f.notices.length;
		f.clock.offset = 46_000;
		f.control.tick();
		expect(f.notices.slice(noticesBefore).some((n) => n.msg.includes("Duty observation:"))).toBe(true);
		expect(f.control.count).toBe(timersBefore);
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(0);
		expect(f.duty.faux.state.callCount).toBe(0);
		expect(followupMessages(f.duty)).toHaveLength(0);
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);

		// Repair by exact-byte restoration, never deleting the unresolved outbox state.
		writeFileSync(ledgerPath, valid.bytes);
		expect(existsSync(ledgerPath)).toBe(true);
		expect(readFileSync(ledgerPath, "utf8")).toBe(valid.bytes);
		const restored = JSON.parse(readFileSync(ledgerPath, "utf8"));
		expect(restored.pinned).toBe(valid.pinned);
		expect(restored.outbox).toHaveLength(1);
		expect(restored.outbox[0].transport).toBe("uncertain");
		expect(restored.stops).toHaveLength(1);

		f.duty.setResponses([fauxAssistantMessage("Supervisor idle during activation")]);
		const createdBeforeSuccess = f.control.created;
		const clearedBeforeSuccess = f.control.cleared;
		await f.command("duty-followup-on", args);
		const upgraded = await f.status();
		expect(upgraded.mode).toBe("followup");
		expect(upgraded.businessProgress).toBe("unverified");
		expect((upgraded.pinnedTargets as Array<{ key: string }>)[0].key).toBe(KEY);
		expect(f.control.count).toBe(timersBefore);
		expect(f.control.created - createdBeforeSuccess).toBe(1);
		expect(f.control.cleared - clearedBeforeSuccess).toBe(1);
		await expect(lockDutyTarget(f.channel.dir, KEY)).rejects.toThrow();
		await expect(lockDutyTarget(f.channel.dir, KEY, "send")).rejects.toThrow();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(0);
		expect(f.duty.faux.state.callCount).toBe(0);
		expect(followupMessages(f.duty)).toHaveLength(0);
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
	} finally {
		await f.cleanup();
	}
});

it("refusals create no request: inactive, observation, offline, DONE, owner, session and note bounds", async () => {
	const scenarios = ["inactive", "observation", "offline", "done", "owner", "session", "bound-note"] as const;
	for (const scenario of scenarios) {
		const f = await setup();
		try {
			const index = join(f.original.tempDir, ".agenticdoc", "_index.parallel");
			if (scenario === "observation") await f.command("duty-on", `"${f.original.tempDir}" ${KEY}`);
			else if (scenario !== "inactive") {
				await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
				if (scenario === "done")
					writeFileSync(index, `| ${KEY} | active | DONE | ${hostname()}:${process.pid} | | | |\n`);
				if (scenario === "owner") writeFileSync(index, `| ${KEY} | active | EXECUTE | other:42 | | | |\n`);
				if (scenario === "offline" || scenario === "session") {
					const endpoint = f.channel.windowPath(KEY, `${hostname()}:${process.pid}`);
					const heartbeat = JSON.parse(readFileSync(endpoint, "utf8"));
					if (scenario === "offline") rmSync(endpoint);
					else writeFileSync(endpoint, JSON.stringify({ ...heartbeat, session: randomUUID() }));
				}
			}
			const note = scenario === "bound-note" ? "x".repeat(3000) : "Verify the pinned state";
			await expect(f.tool("mw_duty_followup", { id: randomUUID(), note })).rejects.toThrow();
			expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
			const status = await f.status();
			expect(status.businessProgress).toBe("unverified");
		} finally {
			await f.cleanup();
		}
	}
});

it("duty-off, session switch and shutdown release local authority; explicit re-entry reconciles the outbox", async () => {
	const f = await setup();
	try {
		f.duty.setResponses([fauxAssistantMessage("Supervisor inspected the notice")]);
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		f.clock.offset = 46_000;
		f.control.tick();
		await waitFor(() => followupMessages(f.duty).length === 1);
		const id = followupMessages(f.duty)[0].details.id;
		await f.tool("mw_duty_followup", { id, note: "Verify the pinned state" });
		expect(requestFiles(f.channel, f.binding)).toHaveLength(1);
		await f.command("duty-off", "");
		expect((await f.status()).mode).toBe("inactive");
		await assertLeasesReleased(f.channel.dir, KEY);
		await expect(f.tool("mw_duty_followup", { id, note: "Verify the pinned state" })).rejects.toThrow(
			/not active|requires/i,
		);
		// Explicit re-entry reconciles the persisted ID; no duplicate request is manufactured.
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		expect((await f.status()).mode).toBe("followup");
		expect(requestFiles(f.channel, f.binding)).toHaveLength(1);
		const changed = makeCtx(f.duty, f.flags, f.notices, randomUUID());
		await expect(f.tool("mw_duty_followup", { id, note: "Verify the pinned state" }, changed)).rejects.toThrow(
			/session|not active/i,
		);
		expect((await f.status(changed)).mode).toBe("inactive");
		expect(requestFiles(f.channel, f.binding)).toHaveLength(1);
	} finally {
		await f.cleanup();
	}
}, 25000);

it("one later unchanged idle emits a single no-progress notice, not another send", async () => {
	const f = await setup();
	try {
		f.duty.setResponses([
			fauxAssistantMessage("Supervisor inspected the stop"),
			fauxAssistantMessage("Supervisor recorded missing verified progress"),
		]);
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		f.clock.offset = 46_000;
		f.control.tick();
		await waitFor(() => followupMessages(f.duty).length === 1);
		const id = followupMessages(f.duty)[0].details.id;
		await f.tool("mw_duty_followup", { id, note: "Verify the pinned state" });
		expect(requestFiles(f.channel, f.binding)).toHaveLength(1);
		f.clock.offset = 92_000;
		f.control.tick();
		await waitFor(() => followupMessages(f.duty).length === 2, 6000);
		const notices = followupMessages(f.duty);
		expect(notices[1].details.kind).toBe("no-progress");
		expect(notices[1].content).toContain("No new verified engineering progress");
		expect(requestFiles(f.channel, f.binding)).toHaveLength(1);
		f.control.tick();
		expect(followupMessages(f.duty)).toHaveLength(2);
		const status = await f.status();
		expect(status.businessProgress).toBe("unverified");
		expect((status.controllerStatus as { businessProgress: string }).businessProgress).toBe("unverified");
	} finally {
		await f.cleanup();
	}
}, 25000);

it("foreign OS leases and a different target/full shift are refused without replacing the mode", async () => {
	const f = await setup();
	const monitor = await lockDutyTarget(f.channel.dir, KEY);
	try {
		await expect(f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`)).rejects.toThrow();
		expect((await f.status()).mode).toBe("inactive");
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
	} finally {
		await new Promise<void>((resolve) => monitor.close(() => resolve()));
		await f.cleanup();
	}
	const g = await setup();
	try {
		await g.command("duty-on", `"${g.original.tempDir}" ${KEY}`);
		await expect(g.command("duty-on", `"${g.original.tempDir}" other-key`)).rejects.toThrow(
			/different target|duty-off/i,
		);
		const shiftCard = join(g.home, "shift.json");
		writeFileSync(shiftCard, "{}");
		await expect(g.command("duty-on", `"${shiftCard}"`)).rejects.toThrow(/different target|duty-off/i);
		expect((await g.status()).mode).toBe("observation");
		expect(requestFiles(g.channel, g.binding)).toHaveLength(0);
	} finally {
		await g.cleanup();
	}
});

it("session_shutdown cancels the timer and leases and never auto-reactivates", async () => {
	const f = await setup();
	try {
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		const timers = f.control.count;
		const handler = f.captured.events.get("session_shutdown");
		expect(handler).toBeDefined();
		handler!({ type: "session_shutdown", reason: "reload" }, f.ctx);
		expect(f.control.count).toBeLessThan(timers);
		await assertLeasesReleased(f.channel.dir, KEY);
		expect((await f.status()).mode).toBe("inactive");
		await expect(
			f.tool("mw_duty_followup", { id: randomUUID(), note: "No authority after shutdown" }),
		).rejects.toThrow(/not active|requires/i);
		f.clock.offset = 46_000;
		f.control.tick();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(0);
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
	} finally {
		await f.cleanup();
	}
});

it("a registered full shift keeps its authority and is not downgraded by follow-up activation", async () => {
	const f = await setup();
	try {
		const now = Date.now();
		const shift = {
			shift: "offline",
			start: new Date(now - 1000).toISOString(),
			end: new Date(now + 3_600_000).toISOString(),
			targets: [
				{
					project: f.original.tempDir,
					key: KEY,
					claim: `${hostname()}:${process.pid}`,
					binding: f.binding,
					session: f.original.sessionManager.getSessionId(),
					minutes: 30,
					rules: [{ name: "review", scope: "offline fixture", direction: "Review the fixture", limit: 10 }],
				},
			],
		};
		const file = join(f.home, "shift.json");
		writeFileSync(file, JSON.stringify(shift));
		await f.command("duty-on", `"${file}"`);
		const status = await f.status();
		expect(status.mode).toBe("shift");
		expect((status.pinnedTargets as Array<{ key: string }>)[0]).toMatchObject({ key: KEY, balance: 30 });
		await f.command("duty-on", `"${file}"`);
		expect((await f.status()).mode).toBe("shift");
		await expect(f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`)).rejects.toThrow(
			/different target|duty-off/i,
		);
		await expect(f.tool("mw_duty_followup", { id: randomUUID(), note: "No shift approval implied" })).rejects.toThrow(
			/not active|requires/i,
		);
		expect((await f.status()).mode).toBe("shift");
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
	} finally {
		await f.cleanup();
	}
});

it("the real slash-command entry activates explicit follow-up through the harness", async () => {
	const f = await setup();
	try {
		f.duty.setResponses([fauxAssistantMessage("Command acknowledged")]);
		await f.duty.session.prompt(`/duty-followup-on "${f.original.tempDir}" ${KEY}`);
		const status = await f.status();
		expect(status.mode).toBe("followup");
		expect((status.pinnedTargets as Array<{ key: string }>)[0].key).toBe(KEY);
		expect(status.businessProgress).toBe("unverified");
	} finally {
		await f.cleanup();
	}
});

it("a foreign send lease blocks activation and releases the monitor lease on failure", async () => {
	const f = await setup();
	const send = await lockDutyTarget(f.channel.dir, KEY, "send");
	try {
		await expect(f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`)).rejects.toThrow();
		expect((await f.status()).mode).toBe("inactive");
		const monitor = await lockDutyTarget(f.channel.dir, KEY);
		await new Promise<void>((resolve) => monitor.close(() => resolve()));
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
	} finally {
		await new Promise<void>((resolve) => send.close(() => resolve()));
		await f.cleanup();
	}
});

it("explicit follow-up parsing ignores a registered shift pointer for the same target", async () => {
	const f = await setup();
	try {
		const registered = join(f.home, "registered-shift.json");
		writeFileSync(registered, "{}");
		const pointer = join(f.channel.dir, KEY, "duty-registration.json");
		mkdirSync(dirname(pointer), { recursive: true });
		writeFileSync(
			pointer,
			JSON.stringify({
				file: registered,
				sha256: createHash("sha256").update("{}").digest("hex"),
			}),
		);
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`);
		expect((await f.status()).mode).toBe("followup");
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
	} finally {
		await f.cleanup();
	}
});

it("observation works without an online original PM and pins no identity", async () => {
	const f = await setup();
	try {
		const claim = `${hostname()}:${process.ppid}`;
		writeFileSync(
			join(f.original.tempDir, ".agenticdoc", "_index.parallel"),
			`| ${KEY} | active | EXECUTE | ${claim} | | | |\n`,
		);
		rmSync(f.channel.windowPath(KEY, `${hostname()}:${process.pid}`));
		await f.command("duty-on", `"${f.original.tempDir}" ${KEY}`);
		const status = await f.status();
		expect(status.mode).toBe("observation");
		expect(status.pinnedTargets).toHaveLength(1);
		expect(
			(status.pinnedTargets as Array<{ key: string; claim: string; binding: string; session: string }>)[0],
		).toMatchObject({
			key: KEY,
			claim: "",
			binding: "",
			session: "",
		});
		expect((status.observedStates as Array<{ state: string }>)[0].state).toBe("idle");
		expect(status.businessProgress).toBe("unverified");
		await f.command("duty-off", "");
		expect((await f.status()).mode).toBe("inactive");
	} finally {
		await f.cleanup();
	}
});

it("a single-key observation refuses follow-up while offline and creates no request", async () => {
	const f = await setup();
	try {
		const args = { ...f.ctx, cwd: f.original.tempDir } as ExtensionCommandContext;
		rmSync(f.channel.windowPath(KEY, `${hostname()}:${process.pid}`));
		await f.command("duty-on", KEY, args);
		const status = await f.status(args);
		expect(status.mode).toBe("observation");
		expect((status.pinnedTargets as Array<{ claim: string; binding: string; session: string }>)[0]).toMatchObject({
			claim: "",
			binding: "",
			session: "",
		});
		await expect(f.command("duty-followup-on", KEY, args)).rejects.toThrow(/原 PM 不在线/);
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
		expect((await f.status(args)).mode).toBe("observation");
	} finally {
		await f.cleanup();
	}
});

it("the original PM coming online upgrades a single-key observation to follow-up", async () => {
	const f = await setup();
	try {
		const args = { ...f.ctx, cwd: f.original.tempDir } as ExtensionCommandContext;
		const endpoint = f.channel.windowPath(KEY, `${hostname()}:${process.pid}`);
		const heartbeat = JSON.parse(readFileSync(endpoint, "utf8"));
		rmSync(endpoint);
		await f.command("duty-on", KEY, args);
		expect((await f.status(args)).mode).toBe("observation");
		writeFileSync(endpoint, JSON.stringify({ ...heartbeat, at: Date.now(), activity: "idle" }));
		await f.command("duty-followup-on", KEY, args);
		const status = await f.status(args);
		expect(status.mode).toBe("followup");
		expect(
			(status.pinnedTargets as Array<{ key: string; claim: string; binding: string; session: string }>)[0],
		).toMatchObject({
			key: KEY,
			claim: `${hostname()}:${process.pid}`,
			binding: f.binding,
			session: f.original.sessionManager.getSessionId(),
		});
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
	} finally {
		await f.cleanup();
	}
});

it("a changed supervisor session stops timer sends and does not reactivate", async () => {
	const f = await setup();
	try {
		const sessionRef = { value: f.duty.sessionManager.getSessionId() };
		const mutable = makeCtx(f.duty, f.flags, f.notices, sessionRef);
		await f.command("duty-followup-on", `"${f.original.tempDir}" ${KEY}`, mutable);
		sessionRef.value = randomUUID();
		f.clock.offset = 46_000;
		f.control.tick();
		expect(f.duty.eventsOfType("agent_start")).toHaveLength(0);
		expect(followupMessages(f.duty)).toHaveLength(0);
		expect((await f.status(mutable)).mode).toBe("inactive");
		await expect(
			f.tool("mw_duty_followup", { id: randomUUID(), note: "No send after session change" }, mutable),
		).rejects.toThrow(/not active|requires/i);
		expect(requestFiles(f.channel, f.binding)).toHaveLength(0);
	} finally {
		await f.cleanup();
	}
});
