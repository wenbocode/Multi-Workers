import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { hostname, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { type TestContext, test } from "node:test";
import type { ExtensionAPI } from "../coding-agent/src/core/extensions/types.ts";
import { PmChannel, registerPmChannel } from "../coding-agent/src/extensions/agent-team-loop/pm/codex-channel.ts";
import { lockDutyTarget } from "./pm_duty_lease.ts";
import { loadShift, publishDutyFact, type Shift, WindowDuty } from "./window_duty.ts";
import registerDuty from "./window_duty_extension.ts";

interface Sample {
	at: string;
	key: string;
	action: string;
	minutes: number;
	id: string;
	evidence: string;
	fact: string;
	sourceSha256: string;
}
const fixture: {
	shift: string;
	start: string;
	end: string;
	events: Sample[];
	cards: Record<string, Pick<Shift["targets"][number], "minutes" | "rules">>;
} = JSON.parse(readFileSync(new URL("./fixtures/window-duty-night-20261116.json", import.meta.url), "utf8"));
const exceptions = ["05506be4-ee13-4cf9-becc-7e17782551f1", "ba83f28c-65da-4a81-80af-e8ef8d491ebd"];
const missed = [
	"64ca751b-6728-40f3-983d-af8c030982c8",
	"68935690-e648-421e-9ab5-26f834c76376",
	"7e8e0be8-5a45-46a5-84a3-4b40b9ead068",
];

// Timer, provider and UI boundaries only. Both window extensions, spool files, authority,
// worker queue, authorization ledger, receipt correlation and the per-target lease are real.
function desktop(cwd: string) {
	const session = randomUUID();
	const notices: string[] = [];
	const ctx = {
		cwd,
		mode: "tui",
		isIdle: () => true,
		hasPendingMessages: () => false,
		sessionManager: { getSessionId: () => session },
		ui: {
			confirm: async (_title: string, _message: string) => false,
			notify: (msg: string, kind: string) => {
				notices.push(msg);
				if (kind === "warning") throw Error(msg);
			},
		},
	};
	type Callback = (...args: unknown[]) => unknown;
	const events = new Map<string, Callback>();
	const commands = new Map<string, Callback>();
	const tools = new Map<string, Callback>();
	const messages: { customType: string; details: { id: string; key: string }; content: string }[] = [];
	const api = {
		on: (event: string, handler: Callback) => {
			const prior = events.get(event);
			events.set(event, (...args) => {
				prior?.(...args);
				return handler(...args);
			});
		},
		registerCommand: (cmd: string, def: { handler: Callback }) => commands.set(cmd, def.handler),
		registerTool: (def: { name: string; execute: Callback }) => tools.set(def.name, def.execute),
		sendMessage: (message: (typeof messages)[number], options: { triggerTurn: boolean }) => {
			assert.equal(options.triggerTurn, true);
			messages.push(message);
			events.get("context")?.({ messages: [{ ...message, role: "custom" }] }, ctx);
			events.get("message_end")?.(
				{
					message: {
						role: "assistant",
						model: "offline",
						stopReason: "stop",
						content: [{ type: "text", text: "Offline receiver acknowledged the direction." }],
						usage: { input: 0, output: 0 },
					},
				},
				ctx,
			);
		},
	} as unknown as ExtensionAPI;
	return {
		api,
		ctx,
		messages,
		session,
		notices,
		events,
		command: (name: string, arg: string) => commands.get(name)!(arg, ctx),
		tool: (name: string, params: object) => tools.get(name)!("call", params, undefined, undefined, ctx),
	};
}

function setup(t: TestContext) {
	const root = mkdtempSync(join(tmpdir(), "mw duty replay-"));
	t.after(() => rmSync(root, { recursive: true, force: true }));
	const windows = new Map<string, ReturnType<typeof desktop>>();
	const targets = Object.entries(fixture.cards).map(([key, card]) => {
		const project = join(root, key);
		const doc = join(project, ".agenticdoc");
		mkdirSync(join(doc, key), { recursive: true });
		const claim = `${hostname()}:${process.pid}`;
		writeFileSync(join(doc, "_index.parallel"), `| ${key} | active | EXECUTE | ${claim} | | | |\n`);
		writeFileSync(
			join(doc, "_workers.parallel"),
			`prior | running | pi | model | ${join(doc, key, "workers/prior/task.md")} | t | t\n`,
		);
		const original = desktop(project);
		registerPmChannel(original.api, root);
		registerDuty(original.api, root);
		original.events.get("session_start")!({}, original.ctx);
		const channel = new PmChannel(project, root);
		const binding = channel.status(key).binding!;
		assert.ok(binding, "Original PM heartbeat missing");
		windows.set(key, original);
		return { ...card, project, key, claim, session: original.session, binding };
	});
	const { shift, start, end } = fixture;
	const file = join(root, "shift.json");
	writeFileSync(file, JSON.stringify({ shift, start, end, targets }));
	const config = loadShift(file);
	const local = (e: Sample) => join(root, e.key, ".agenticdoc", e.key);
	function materialize(e: Sample) {
		const path = join(local(e), e.evidence);
		mkdirSync(dirname(path), { recursive: true });
		if (process.env.MW_DUTY_REPLAY_EVIDENCE) {
			copyFileSync(join(process.env.MW_DUTY_REPLAY_EVIDENCE, `${e.id}.md`), path);
			assert.equal(createHash("sha256").update(readFileSync(path)).digest("hex"), e.sourceSha256);
		} else writeFileSync(path, e.fact);
	}
	return { root, windows, file, config, materialize, local };
}

test("7 historical decisions, 3 recovered terminal reports, cold handoff and correlated original PM receipts", async (t) => {
	t.mock.timers.enable({ apis: ["Date"], now: Date.parse(fixture.start) });
	const intervals = new Map<object, () => void>();
	t.mock.method(globalThis, "setInterval", (fn: () => void) => {
		const handle = { unref() {} };
		intervals.set(handle, fn);
		return handle;
	});
	t.mock.method(globalThis, "clearInterval", (handle: object) => intervals.delete(handle));
	function tick(ms: number) {
		t.mock.timers.setTime(Date.now() + ms);
		for (const fn of intervals.values()) fn();
	}
	const { root, windows, file, config, materialize, local } = setup(t);
	const wakeIds: string[] = [];
	const rows = [];
	let supervisor = desktop(root);
	t.after(() => supervisor.command("duty-off", ""));
	registerDuty(supervisor.api, root);
	for (const original of windows.values()) await original.command("duty-report-on", file);
	let running = false;
	for (const e of fixture.events) {
		t.mock.timers.setTime(Date.parse(`2026-11-17T${e.at}:00+08:00`));
		const original = windows.get(e.key)!;
		// Refresh original-window heartbeats after the virtual clock jump.
		tick(2500);
		writeFileSync(join(root, e.key, ".agenticdoc", "_workers.parallel"), "");
		materialize(e);
		await original.tool("mw_duty_report", {
			id: e.id,
			state: "ready",
			gate: "clear",
			action: e.action,
			minutes: e.minutes,
			reason: e.fact,
			path: e.evidence,
		});
		if (!running || missed.includes(e.id)) {
			if (running) await supervisor.command("duty-off", "");
			supervisor = desktop(root);
			registerDuty(supervisor.api, root);
			await supervisor.command("duty-on", file);
			running = true;
		}
		tick(1000);
		tick(45_000);
		const relevant = supervisor.messages.filter((m) => m.details.id === e.id);
		assert.equal(relevant.length, Number(exceptions.includes(e.id)), e.at);
		if (relevant.length) {
			wakeIds.push(e.id);
			await supervisor.tool("mw_duty_decide", {
				id: e.id,
				key: e.key,
				approve: true,
				reason: "Replay of the bounded historical choice.",
			});
		}
		const target = config.targets.find((x) => x.key === e.key)!;
		const channel = new PmChannel(target.project, root);
		const request = channel.messagePath(e.key, target.binding, e.id, "request");
		assert.ok(existsSync(request), `${e.key} ${e.at}`);
		// Transfer once after enqueue and once after started. Reuse actual durable receipts.
		if (e.at === "00:28") {
			await supervisor.command("duty-off", "");
			await supervisor.command("duty-on", file);
		}
		tick(5000);
		assert.equal(channel.receipt(e.key, target.binding, e.id).state, "started", e.at);
		if (e.at === "01:03") {
			await supervisor.command("duty-off", "");
			await supervisor.command("duty-on", file);
		}
		assert.equal(original.messages.filter((m) => m.details.id === e.id).length, 1);
		assert.match(original.messages.find((m) => m.details.id === e.id)!.content, /MW 值守窗口/);
		const progress = `evidence/offline-${e.id}.txt`;
		writeFileSync(join(local(e), progress), `Simulated original PM produced a new artifact for ${e.id}`);
		await original.tool("mw_duty_report", {
			id: e.id,
			state: "result",
			gate: "clear",
			action: e.action,
			minutes: e.minutes,
			reason: "offline proof",
			path: progress,
		});
		tick(5000);
		const state = new WindowDuty(config, target, root);
		assert.equal(state.entries.find((x) => x.id === e.id)?.stage, "complete", e.at);
		rows.push({
			at: e.at,
			key: e.key,
			route: relevant.length ? "duty" : "original",
			receipt: "started",
			evidence: progress,
		});
	}
	assert.deepEqual(wakeIds, exceptions);
	const audit = readFileSync(join(root, "duty-audit", `${fixture.shift}.jsonl`), "utf8")
		.trim()
		.split("\n")
		.map((line) => JSON.parse(line));
	assert.deepEqual(
		audit.filter((row) => row.event).map((row) => row.event.id),
		exceptions,
	);
	for (const target of config.targets) {
		const ledger = new WindowDuty(config, target, root);
		assert.equal(
			ledger.balance,
			target.minutes - fixture.events.filter((e) => e.key === target.key).reduce((a, e) => a + e.minutes, 0),
		);
		assert.equal(
			ledger.entries.filter((e) => e.message && e.action !== "report-stop").length,
			fixture.events.filter((e) => e.key === target.key).length,
		);
	}
	await supervisor.command("duty-off", "");
	console.log(
		JSON.stringify({
			primaryStops: 7,
			dutyWakeIds: wakeIds,
			recovered: rows.filter((r) => ["01:59", "02:03", "03:38"].includes(r.at)),
			rows,
			providerCalls: 0,
			source: process.env.MW_DUTY_REPLAY_EVIDENCE ? "pinned historical snapshots" : "portable stop summaries",
		}),
	);
});

test("target lease excludes another owner and releases on departure", async () => {
	const lease = await lockDutyTarget(tmpdir(), `offline-test-${process.pid}`);
	try {
		await assert.rejects(() => lockDutyTarget(tmpdir(), `offline-test-${process.pid}`), /EADDRINUSE/);
	} finally {
		await new Promise<void>((resolve) => lease.close(() => resolve()));
	}
	const next = await lockDutyTarget(tmpdir(), `offline-test-${process.pid}`);
	next.close();
});

test("first duty-on prepares a live owner's project and resumes on heartbeat; cancellation and owner changes stop the wait", async (t) => {
	t.mock.timers.enable({ apis: ["setInterval"] });
	const root = mkdtempSync(join(tmpdir(), "mw duty setup-"));
	const project = join(root, "bearing");
	const doc = join(project, ".agenticdoc");
	const settings = join(project, ".pi", "settings.json");
	const key = "work-memory";
	const claim = `${hostname()}:${process.ppid}`;
	const index = (owner: string) =>
		writeFileSync(join(doc, "_index.parallel"), `| ${key} | active | EXECUTE | ${owner} | | | |\n`);
	mkdirSync(join(doc, key), { recursive: true });
	index(claim);
	writeFileSync(join(doc, "_workers.parallel"), "");
	const window = desktop(root);
	registerDuty(window.api, root);
	t.after(async () => {
		await window.command("duty-off", "");
		rmSync(root, { recursive: true, force: true });
	});
	const args = `"${project}" ${key}`;
	await window.command("duty-on", args);
	assert.ok(!existsSync(settings), "declined setup must not write");
	mkdirSync(dirname(settings), { recursive: true });
	writeFileSync(settings, JSON.stringify({ theme: "test", extensions: ["./other.ts"] }));
	const confirm = t.mock.method(window.ctx.ui, "confirm", async () => true);
	await window.command("duty-on", args);
	const config = JSON.parse(readFileSync(settings, "utf8"));
	assert.equal(config.theme, "test");
	assert.deepEqual(config.extensions.slice(0, 1), ["./other.ts"]);
	assert.equal(config.extensions.length, 3);
	assert.ok(config.extensions.slice(1).every((entry: string) => existsSync(entry)));
	assert.match(window.notices.at(-1)!, /\/reload/);
	await window.command("duty-off", "");
	index("other:42");
	t.mock.timers.tick(2500);
	assert.equal(window.notices.at(-1), "Duty released");
	await assert.rejects(async () => window.command("duty-on", args), /No connected/);
	index(claim);
	await window.command("duty-on", args);
	index("other:42");
	t.mock.timers.tick(2500);
	assert.match(window.notices.at(-1)!, /认领或进程已变化/);
	index(claim);
	await window.command("duty-on", args);
	assert.equal(confirm.mock.callCount(), 1);
	const channel = new PmChannel(project, root);
	const directory = join(channel.dir, key);
	mkdirSync(directory, { recursive: true });
	const endpoint = join(directory, createHash("sha256").update(claim).digest("hex") + ".json");
	writeFileSync(
		endpoint,
		JSON.stringify({ claim, binding: randomUUID(), session: randomUUID(), at: Date.now(), activity: "idle" }),
	);
	t.mock.timers.tick(2500);
	await new Promise<void>((resolve) => setImmediate(resolve));
	assert.match(window.notices.at(-1)!, /Observing/);
	assert.equal(window.messages.length, 0);
});

test("project and key isolate observation, registration and leases to the selected original PM", async (t) => {
	t.mock.timers.enable({ apis: ["Date", "setInterval"], now: Date.parse(fixture.start) });
	const { root, windows, config, file } = setup(t);
	const [target, other] = config.targets;
	const original = windows.get(target.key)!;
	const supervisor = desktop(root);
	registerDuty(supervisor.api, root);
	t.after(() => supervisor.command("duty-off", ""));
	const relativeTarget = `"./${target.key}" ${target.key}`;
	await assert.rejects(
		async () => supervisor.command("duty-on", `"${other.project}" ${target.key}`),
		/Missing or ambiguous/,
	);
	await assert.rejects(async () => original.command("duty-on", `. ${target.key}`), /current PM/);
	writeFileSync(join(target.project, ".agenticdoc", "_workers.parallel"), "");
	await supervisor.command("duty-on", relativeTarget);
	// Refresh the real endpoint on either side of a virtual idle interval.
	t.mock.timers.tick(2500);
	t.mock.timers.setTime(Date.now() + 45_000);
	t.mock.timers.tick(5000);
	assert.ok(supervisor.notices.some((msg) => msg.includes("Observing")));
	assert.ok(supervisor.notices.some((msg) => msg.includes("idle")));
	assert.equal(original.messages.length, 0);
	assert.equal(supervisor.messages.length, 0);
	await supervisor.command("duty-off", "");
	const withSpaces = join(root, "my shift.json");
	copyFileSync(file, withSpaces);
	await original.command("duty-report-on", withSpaces);
	await original.command("duty-report-on", `. ${target.key}`);
	const otherLease = await lockDutyTarget(new PmChannel(other.project, root).dir, other.key);
	try {
		await supervisor.command("duty-on", relativeTarget);
		assert.equal(supervisor.notices.at(-1), `Duty active for ${target.key}`);
		await supervisor.command("duty-off", "");
		writeFileSync(withSpaces, JSON.stringify(config, null, 2));
		await assert.rejects(async () => supervisor.command("duty-on", relativeTarget), /Registered shift card changed/);
	} finally {
		otherLease.close();
	}
	copyFileSync(file, withSpaces);
	original.events.get("session_shutdown")!({}, original.ctx);
	original.events.get("session_start")!({}, original.ctx);
	await assert.rejects(async () => supervisor.command("duty-on", relativeTarget), /binding mismatch/);
});

test("cold scan holds expired, revoked, out-of-scope, over-budget and gated work", async (t) => {
	t.mock.timers.enable({ apis: ["Date", "setInterval"], now: Date.parse("2026-11-17T02:00:00+08:00") });
	const { root, config, windows, materialize } = setup(t);
	const e = fixture.events[0],
		target = config.targets.find((x) => x.key === e.key)!;
	materialize(e);
	writeFileSync(join(target.project, ".agenticdoc", "_workers.parallel"), "");
	const original = windows.get(e.key)!;
	await original.command("duty-report-on", join(root, "shift.json"));
	for (const [scenario, change] of Object.entries({
		gate: { gate: "blocked" as const },
		scope: { action: "edit-host" },
		"unit-limit": { minutes: 61 },
		budget: {},
		revoked: {},
		expired: {},
	})) {
		const id = randomUUID(),
			notices: string[] = [];
		const activeTarget = { ...target };
		if (scenario === "revoked") activeTarget.rules = target.rules.filter((r) => r.name !== e.action);
		if (scenario === "budget") activeTarget.minutes = e.minutes - 1;
		const altered = { ...config, shift: `scenario-${scenario}` };
		publishDutyFact(altered, activeTarget, {
			id,
			action: e.action,
			minutes: e.minutes,
			reason: e.fact,
			path: e.evidence,
			gate: "clear",
			state: "ready",
			...change,
		});
		const station = new WindowDuty(altered, activeTarget, root);
		const now = scenario === "expired" ? Date.parse(config.end) : Date.now();
		for (const after of [0, 46_000, 60_000]) station.poll(now + after, (n) => notices.push(n.kind));
		assert.deepEqual(notices, ["user"], scenario);
		assert.equal(station.balance, activeTarget.minutes);
		assert.ok(!existsSync(station.watch.channel.messagePath(e.key, target.binding, id, "request")));
	}
	const station = new WindowDuty(config, target, root);
	publishDutyFact(config, target, {
		id: e.id,
		action: e.action,
		minutes: e.minutes,
		reason: e.fact,
		path: e.evidence,
		gate: "clear",
		state: "ready",
	});
	writeFileSync(
		join(target.project, ".agenticdoc", "_index.parallel"),
		`| ${e.key} | active | EXECUTE | other:12 | | | |\n`,
	);
	const alerts: string[] = [];
	for (const after of [0, 46_000]) station.poll(Date.now() + after, (n) => alerts.push(n.kind));
	assert.deepEqual(alerts, ["duty"]);
	assert.equal(original.messages.length, 0);
});

test("no progress escalates once; inherited queued direction resumes without a new reservation", (t) => {
	t.mock.timers.enable({ apis: ["Date", "setInterval"], now: Date.parse("2026-11-17T01:00:00+08:00") });
	const { root, config, materialize } = setup(t);
	const e = fixture.events[0],
		target = config.targets.find((x) => x.key === e.key)!;
	writeFileSync(join(target.project, ".agenticdoc", "_workers.parallel"), "");
	materialize(e);
	const station = new WindowDuty(config, target, root);
	const channel = station.watch.channel;
	channel.send(e.key, target.binding, e.id, "Existing direction from outgoing Codex shift");
	publishDutyFact(config, target, {
		id: e.id,
		action: e.action,
		minutes: e.minutes,
		reason: e.fact,
		path: e.evidence,
		gate: "clear",
		state: "ready",
	});
	const events: string[] = [];
	for (const ms of [0, 46_000, 50_000]) station.poll(Date.now() + ms, (n) => events.push(n.kind));
	assert.equal(station.entries[0].receipt, "queued");
	t.mock.timers.tick(2500);
	station.poll(Date.now() + 60_000, (n) => events.push(n.kind));
	assert.equal(station.entries[0].receipt, "started");
	assert.equal(station.entries[0].stage, "tracking");
	for (const after of [45, 46]) station.poll(Date.now() + after * 60_000, (n) => events.push(n.kind));
	assert.equal(station.entries[0].stage, "diagnosis");
	assert.equal(station.balance, target.minutes);
	assert.deepEqual(events, ["duty"]);
});

test("withdrawn current stop is rejected at the original window before triggering a turn", (t) => {
	t.mock.timers.enable({ apis: ["Date", "setInterval"], now: Date.parse("2026-11-17T01:00:00+08:00") });
	const { root, config, materialize, windows } = setup(t);
	const e = fixture.events[0],
		target = config.targets.find((x) => x.key === e.key)!;
	writeFileSync(join(target.project, ".agenticdoc", "_workers.parallel"), "");
	materialize(e);
	const station = new WindowDuty(config, target, root);
	const fact = {
		id: e.id,
		action: e.action,
		minutes: e.minutes,
		reason: e.fact,
		path: e.evidence,
		gate: "clear" as const,
	};
	publishDutyFact(config, target, { ...fact, state: "ready" });
	station.poll(Date.now(), () => assert.fail());
	station.poll(Date.now() + 46_000, () => assert.fail());
	assert.equal(station.entries[0].receipt, "queued");
	publishDutyFact(config, target, { ...fact, id: randomUUID(), state: "stopped" });
	t.mock.timers.tick(2500);
	assert.equal(station.watch.channel.receipt(e.key, target.binding, e.id).state, "rejected");
	assert.equal(windows.get(e.key)!.messages.length, 0);
});
