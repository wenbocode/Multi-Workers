import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import { type TestContext, test } from "node:test";
import type { ExtensionAPI } from "../coding-agent/src/core/extensions/types.ts";
import {
	type DutyEnvelope,
	MW_FOLLOWUP_SOURCE,
	type PmChannelSource,
	type PmStageGrantV1,
	registerPmChannel,
	PmChannel as Spool,
} from "../coding-agent/src/extensions/agent-team-loop/pm/codex-channel.ts";
import { DutyFollowup, type FollowupNotice, type FollowupStatus, type FollowupTarget } from "./duty_followup.ts";

type Callback = (...args: unknown[]) => unknown;
const IDLE_MS = 45_000;

interface Fixture {
	root: string;
	project: string;
	home: string;
	doc: string;
	channel: Spool;
	target: FollowupTarget;
	heartbeatFile: string;
	heartbeat: (change?: Record<string, unknown>) => void;
	heartbeatFor: (claim: string, change?: Record<string, unknown>) => void;
	index: (claim?: string, phase?: string) => void;
	receipt: (id: string, state: string, change?: Record<string, unknown>) => void;
	receiptPath: (id: string, binding?: string) => string;
	request: (id: string, binding?: string) => string;
	requestDir: (binding?: string) => string;
}

function fixture(t: TestContext, key = "target-key"): Fixture {
	const root = mkdtempSync(join(tmpdir(), "mw-duty-followup-"));
	t.after(() => rmSync(root, { recursive: true, force: true }));
	const project = join(root, "project");
	const home = join(root, "home");
	const claim = `${hostname()}:${process.pid}`;
	const session = randomUUID();
	const binding = randomUUID();
	const doc = join(project, ".agenticdoc");
	mkdirSync(join(doc, key), { recursive: true });
	mkdirSync(home, { recursive: true });
	const channel = new Spool(project, home);
	const target: FollowupTarget = { project, key, claim, binding, session };
	const index = (owner = claim, phase = "EXECUTE") =>
		writeFileSync(join(doc, "_index.parallel"), `| ${key} | active | ${phase} | ${owner} | | | |\n`);
	index();
	writeFileSync(join(doc, "_workers.parallel"), "");
	writeFileSync(join(doc, key, "pm-state.md"), "- Phase: EXECUTE\n- Next Action: test\n");
	mkdirSync(join(channel.dir, key, binding), { recursive: true });
	const heartbeatFor = (owner: string, change: Record<string, unknown> = {}) =>
		writeFileSync(
			channel.windowPath(key, owner),
			JSON.stringify({
				claim: owner,
				binding,
				session,
				at: Date.now(),
				activity: "idle",
				...change,
			}),
		);
	const heartbeatFile = channel.windowPath(key, claim);
	heartbeatFor(claim);
	return {
		root,
		project,
		home,
		doc,
		channel,
		target,
		heartbeatFile,
		heartbeat: (change = {}) => heartbeatFor(claim, change),
		heartbeatFor,
		index,
		receipt: (id, state, change = {}) =>
			writeFileSync(
				channel.messagePath(key, binding, id, "receipt"),
				JSON.stringify({ id, key, binding, claim, session, state, observedAt: Date.now(), ...change }),
			),
		receiptPath: (id, idBinding = binding) => channel.messagePath(key, idBinding, id, "receipt"),
		request: (id, idBinding = binding) => channel.messagePath(key, idBinding, id, "request"),
		requestDir: (idBinding = binding) => join(channel.dir, key, idBinding),
	};
}

function firstStop(controller: DutyFollowup, now: number, emit?: (notice: FollowupNotice) => void): FollowupNotice {
	const notices: FollowupNotice[] = [];
	const collect = (notice: FollowupNotice) => {
		notices.push(notice);
		emit?.(notice);
	};
	controller.poll(now, collect);
	controller.poll(now + IDLE_MS, collect);
	const stop = notices.find((notice) => notice.kind === "stop");
	assert.ok(stop, "stable idle did not emit a stop notice");
	return stop;
}

function requestCount(f: Fixture, binding = f.target.binding): number {
	if (!existsSync(f.requestDir(binding))) return 0;
	return readdirSync(f.requestDir(binding)).filter((name) => name.endsWith(".request.json")).length;
}

function readRequest(f: Fixture, id: string, binding = f.target.binding): Record<string, unknown> {
	return JSON.parse(readFileSync(f.request(id, binding), "utf8")) as Record<string, unknown>;
}

interface Receiver {
	ctx: Record<string, unknown>;
	events: Map<string, Callback>;
	messages: string[];
	tick: () => void;
	close: () => void;
}

function receiver(t: TestContext, f: Fixture): Receiver {
	const ctx: Record<string, unknown> = {
		cwd: f.project,
		mode: "tui",
		isIdle: () => true,
		hasPendingMessages: () => false,
		sessionManager: { getSessionId: () => f.target.session },
		ui: { notify: (_message: string, _kind: string) => {} },
	};
	const events = new Map<string, Callback>();
	const messages: string[] = [];
	const intervals = new Map<object, Callback>();
	const api = {
		on: (event: string, handler: Callback) => {
			const prior = events.get(event);
			events.set(event, (...args: unknown[]) => {
				prior?.(...args);
				return handler(...args);
			});
		},
		sendMessage: (message: { content: string }) => {
			messages.push(message.content);
		},
	} as unknown as ExtensionAPI;
	const originalSetInterval = globalThis.setInterval;
	const originalClearInterval = globalThis.clearInterval;
	globalThis.setInterval = ((fn: Callback) => {
		const handle = { unref() {} };
		intervals.set(handle, fn);
		return handle;
	}) as unknown as typeof setInterval;
	globalThis.clearInterval = ((handle: object) => intervals.delete(handle)) as unknown as typeof clearInterval;
	t.after(() => {
		globalThis.setInterval = originalSetInterval;
		globalThis.clearInterval = originalClearInterval;
	});
	const priorWorkerTask = process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_TASK;
	try {
		registerPmChannel(api, f.home);
	} finally {
		if (priorWorkerTask === undefined) delete process.env.PI_WORKER_TASK;
		else process.env.PI_WORKER_TASK = priorWorkerTask;
	}
	events.get("session_start")!({}, ctx);
	return {
		ctx,
		events,
		messages,
		tick: () => {
			for (const fn of [...intervals.values()]) fn();
		},
		close: () => events.get("session_shutdown")!({}, ctx),
	};
}

test("changed original PM session refuses a send before any request is created", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const stop = firstStop(controller, now);
	f.heartbeat({ session: randomUUID() });
	assert.throws(() => controller.send(stop.id, "Confirm the pinned state", now + IDLE_MS), /session/i);
	assert.equal(existsSync(f.request(stop.id)), false);
	assert.equal(readFileSync(f.heartbeatFile, "utf8").includes(f.target.session), false);
});

test("transport receipts and working activity never count as engineering progress", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const notice = firstStop(controller, now);
	const result = controller.send(notice.id, "Verify the target evidence", now + IDLE_MS);
	assert.equal(result.id, notice.id);
	for (const state of ["queued", "received", "started"]) {
		f.receipt(notice.id, state);
		const status = controller.status(now + IDLE_MS + 1000) as FollowupStatus;
		assert.equal(status.businessProgress, "unverified");
		assert.equal(
			status.receipts.some((entry) => entry.id === notice.id && entry.state === state),
			true,
		);
	}
	f.heartbeat({ activity: "working" });
	const working = controller.status(now + IDLE_MS + 2000) as FollowupStatus;
	assert.equal(working.businessProgress, "unverified");
	assert.equal(working.observedState, "working");
});

test("stable idle emits one stop and an unchanged stop is deduplicated", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const notices: FollowupNotice[] = [];
	const now = Date.now();
	controller.poll(now, (notice) => notices.push(notice));
	controller.poll(now + 44_999, (notice) => notices.push(notice));
	assert.equal(notices.length, 0);
	controller.poll(now + IDLE_MS, (notice) => notices.push(notice));
	controller.poll(now + 90_000, (notice) => notices.push(notice));
	assert.equal(notices.length, 1);
	assert.equal(notices[0]?.kind, "stop");
	const status = controller.status(now + 90_000);
	assert.equal(status.activeStopId, notices[0]?.id ?? null);
	assert.equal(status.stop?.state, "idle");
	assert.equal(status.businessProgress, "unverified");
	assert.equal(status.outbox.length, 0);
});

test("a busy emitter retains the persisted pending notice and later emits it once", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	controller.poll(now, () => assert.fail("idle below threshold must not emit"));
	controller.poll(now + IDLE_MS, () => {
		throw Error("supervisor busy");
	});
	const pending = controller.status(now + IDLE_MS + 1);
	assert.equal(pending.pendingNotices.length, 1);
	assert.equal(pending.pendingNotices[0]?.kind, "stop");
	assert.equal(pending.stop?.noticeEmitted, false);
	assert.ok(pending.activeStopId);
	assert.throws(
		() => controller.send(pending.activeStopId!, "Inspect current state", now + IDLE_MS + 1),
		/notice has not been emitted/,
	);
	assert.equal(pending.sendAllowed, false);
	assert.equal(requestCount(f), 0);
	const emitted: FollowupNotice[] = [];
	controller.poll(now + IDLE_MS + 5_000, (notice) => emitted.push(notice));
	controller.poll(now + IDLE_MS + 10_000, (notice) => emitted.push(notice));
	assert.equal(emitted.length, 1);
	assert.equal(controller.status(now + IDLE_MS + 10_000).pendingNotices.length, 0);
	assert.equal(controller.status(now + IDLE_MS + 10_000).stop?.noticeEmitted, true);
	assert.equal(controller.status(now + IDLE_MS + 10_000).sendAllowed, true);
	assert.equal(controller.send(emitted[0].id, "Inspect current state", now + IDLE_MS + 10_000).ok, true);
	assert.equal(requestCount(f), 1);
});

test("stable-ID sends are idempotent; changed bodies and arbitrary IDs are refused", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const stop = firstStop(controller, now);
	const note = "Verify the original PM evidence";
	const first = controller.send(stop.id, note, now + IDLE_MS);
	assert.equal(first.ok, true);
	assert.equal(first.id, stop.id);
	assert.equal(first.idempotent, false);
	assert.equal(first.source, MW_FOLLOWUP_SOURCE);
	const request = readRequest(f, stop.id);
	assert.equal(request.source, MW_FOLLOWUP_SOURCE);
	assert.equal(request.duty, undefined);
	assert.equal(request.stage, undefined);
	const second = controller.send(stop.id, note, now + IDLE_MS + 1);
	assert.equal(second.idempotent, true);
	assert.equal(second.id, stop.id);
	assert.equal(second.body, request.text);
	assert.equal(requestCount(f), 1);
	assert.throws(() => controller.send(stop.id, "Changed body", now + IDLE_MS + 2), /ID\/body conflict/i);
	assert.throws(() => controller.send(randomUUID(), note, now + IDLE_MS + 3), /Unknown follow-up stop ID/i);
	const status = controller.status(now + IDLE_MS + 4);
	assert.equal(status.outbox.length, 1);
	assert.equal(status.businessProgress, "unverified");
	assert.equal(requestCount(f), 1);
});

const refusalScenarios: ReadonlyArray<{
	name: string;
	reason: RegExp;
	apply: (f: Fixture) => void;
}> = [
	{
		name: "owner change",
		reason: /owner/i,
		apply: (f) => {
			f.index("other:42");
			f.heartbeatFor("other:42");
		},
	},
	{
		name: "binding change",
		reason: /binding/i,
		apply: (f) => f.heartbeat({ binding: randomUUID() }),
	},
	{
		name: "session change",
		reason: /session/i,
		apply: (f) => f.heartbeat({ session: randomUUID() }),
	},
	{
		name: "offline receiver",
		reason: /offline/i,
		apply: (f) => f.heartbeat({ at: Date.now() - 60_000 }),
	},
	{
		name: "DONE phase",
		reason: /finished|inactive|phase|status/i,
		apply: (f) => f.index(f.target.claim, "DONE"),
	},
];

for (const scenario of refusalScenarios) {
	test(`${scenario.name} refuses the original stable stop without creating a request`, (t) => {
		const f = fixture(t);
		const controller = new DutyFollowup(f.target, f.home);
		const now = Date.now();
		const stop = firstStop(controller, now);
		scenario.apply(f);
		assert.throws(() => controller.send(stop.id, "Verify identity", now + IDLE_MS), scenario.reason);
		assert.equal(existsSync(f.request(stop.id)), false);
		const status = controller.status(now + IDLE_MS);
		assert.equal(status.sendAllowed, false);
		assert.equal(status.businessProgress, "unverified");
	});
}

test("DONE emits one bounded suspended diagnosis and keeps sends refused", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const notices: FollowupNotice[] = [];
	const stop = firstStop(controller, now, (notice) => notices.push(notice));
	notices.length = 0;
	f.index(f.target.claim, "DONE");
	controller.poll(now + IDLE_MS + 1_000, (notice) => notices.push(notice));
	controller.poll(now + IDLE_MS + 2_000, (notice) => notices.push(notice));
	assert.equal(notices.filter((notice) => notice.kind === "suspended").length, 1);
	assert.match(notices[0]?.summary ?? "", /suspended/i);
	const status = controller.status(now + IDLE_MS + 2_000);
	assert.equal(status.sendAllowed, false);
	assert.match(status.diagnosis ?? "", /finished|inactive|phase|status/i);
	assert.equal(status.businessProgress, "unverified");
	assert.throws(
		() => controller.send(stop.id, "Verify completion", now + IDLE_MS + 2_000),
		/finished|inactive|phase|status/i,
	);
});

test("restart reconciles the exact ID and receipt; a later session switch closes send authority", (t) => {
	const f = fixture(t);
	const first = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const stop = firstStop(first, now);
	const note = "Reconcile the persisted outbox";
	first.send(stop.id, note, now + IDLE_MS);
	f.receipt(stop.id, "started");
	const restarted = new DutyFollowup(f.target, f.home);
	const status = restarted.status(now + IDLE_MS + 1_000);
	assert.equal(status.activeStopId, stop.id);
	assert.equal(status.outbox.length, 1);
	assert.equal(
		status.receipts.some((entry) => entry.id === stop.id && entry.state === "started"),
		true,
	);
	assert.equal(status.businessProgress, "unverified");
	const notices: FollowupNotice[] = [];
	restarted.poll(now + IDLE_MS + 5_000, (notice) => notices.push(notice));
	restarted.poll(now + IDLE_MS + 10_000, (notice) => notices.push(notice));
	assert.equal(notices.filter((notice) => notice.kind === "stop").length, 0);
	const retry = restarted.send(stop.id, note, now + IDLE_MS + 11_000);
	assert.equal(retry.idempotent, true);
	assert.equal(retry.id, stop.id);
	assert.equal(requestCount(f), 1);
	f.heartbeat({ session: randomUUID() });
	assert.throws(() => restarted.send(stop.id, note, now + IDLE_MS + 12_000), /session/i);
	assert.equal(restarted.status(now + IDLE_MS + 12_000).sendAllowed, false);
	assert.equal(requestCount(f), 1);
});

test("one no-progress notice follows an unchanged idle without an automatic resend", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const stop = firstStop(controller, now);
	controller.send(stop.id, "Check actual evidence", now + IDLE_MS);
	f.receipt(stop.id, "started");
	const later: FollowupNotice[] = [];
	controller.poll(now + 90_000, (notice) => later.push(notice));
	controller.poll(now + 135_000, (notice) => later.push(notice));
	assert.equal(later.filter((notice) => notice.kind === "no-progress").length, 1);
	assert.equal(later.filter((notice) => notice.kind === "stop").length, 0);
	assert.match(later[0]?.summary ?? "", /No verified progress/i);
	const status = controller.status(now + 135_000);
	assert.equal(status.stop?.noProgressEmitted, true);
	assert.equal(status.outbox.length, 1);
	assert.equal(status.businessProgress, "unverified");
	assert.equal(requestCount(f), 1);
});

test("evidence candidates are observation only; heartbeat, receipts and controller files do not rearm", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const stop = firstStop(controller, now);
	controller.send(stop.id, "Inspect target evidence", now + IDLE_MS);
	const before = controller.status(now + IDLE_MS).evidenceFingerprint;
	f.heartbeat({ at: Date.now() });
	f.receipt(stop.id, "started");
	const controllerDir = join(f.doc, f.target.key, "duty-followup");
	mkdirSync(controllerDir, { recursive: true });
	writeFileSync(join(controllerDir, "ledger.json"), "controller self-write");
	writeFileSync(join(f.doc, f.target.key, "noise.request.json"), "controller self-write");
	writeFileSync(join(f.doc, f.target.key, "noise.receipt.json"), "controller self-write");
	writeFileSync(join(f.doc, f.target.key, "heartbeat.json"), "controller self-write");
	writeFileSync(join(f.doc, f.target.key, "run.json"), "controller self-write");
	assert.equal(controller.status(now + IDLE_MS + 1_000).evidenceFingerprint, before);
	writeFileSync(join(f.doc, f.target.key, "pm-state.md"), "- Phase: EXECUTE\n- Next Action: changed\n");
	writeFileSync(
		join(f.doc, "_workers.parallel"),
		`terminal | done | pi | model | ${join(f.doc, f.target.key, "workers/terminal/task.md")} | t | t | | manual\n`,
	);
	const notices: FollowupNotice[] = [];
	controller.poll(now + 90_000, (notice) => notices.push(notice));
	const rearmed = notices.find((notice) => notice.kind === "stop" && notice.id !== stop.id);
	assert.ok(rearmed, "actual PM/worker evidence changes should rearm a new observed stop");
	assert.match(rearmed.summary, /Business progress unverified/i);
	const status = controller.status(now + 90_000);
	assert.equal(status.businessProgress, "unverified");
	assert.equal(status.outbox.length, 1);
	assert.equal(requestCount(f), 1);
});

test("an uncertain transport keeps the same stable ID and stays uncertain until a real receipt", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const stop = firstStop(controller, now);
	const note = "Transport uncertainty retry";
	const originalSend = Spool.prototype.send;
	Spool.prototype.send = (() => {
		throw Error("simulated transport interruption");
	}) as unknown as typeof Spool.prototype.send;
	t.after(() => {
		Spool.prototype.send = originalSend;
	});
	const uncertain = controller.send(stop.id, note, now + IDLE_MS);
	Spool.prototype.send = originalSend;
	assert.equal(uncertain.ok, false);
	assert.equal(uncertain.id, stop.id);
	assert.equal(uncertain.uncertain, true);
	assert.equal(uncertain.transport, "uncertain");
	const beforeRetry = controller.status(now + IDLE_MS + 1);
	assert.equal(beforeRetry.outbox.length, 1);
	assert.equal(beforeRetry.outbox[0]?.uncertain, true);
	assert.equal(beforeRetry.receipts[0]?.state, "unknown");
	assert.equal(requestCount(f), 0);
	const retry = controller.send(stop.id, note, now + IDLE_MS + 2);
	assert.equal(retry.idempotent, true);
	assert.equal(retry.id, stop.id);
	assert.equal(retry.uncertain, true);
	assert.equal(retry.ok, false);
	assert.equal(existsSync(f.request(stop.id)), true);
	assert.equal(requestCount(f), 1);
	f.receipt(stop.id, "started");
	const reconciled = controller.status(now + IDLE_MS + 3);
	assert.equal(reconciled.outbox.length, 1);
	assert.equal(reconciled.outbox[0]?.uncertain, false);
	assert.equal(reconciled.receipts[0]?.state, "started");
	assert.equal(reconciled.businessProgress, "unverified");
});

test("MW/pi source is closed, persisted and included in ID conflict comparison", (t) => {
	const f = fixture(t);
	const id = randomUUID();
	const legacy = randomUUID();
	f.channel.send(f.target.key, f.target.binding, id, "Stable body", undefined, undefined, MW_FOLLOWUP_SOURCE);
	const request = readRequest(f, id);
	assert.equal(request.source, MW_FOLLOWUP_SOURCE);
	assert.equal(request.duty, undefined);
	assert.equal(request.stage, undefined);
	assert.throws(() => f.channel.send(f.target.key, f.target.binding, id, "Stable body"), /conflict/i);
	assert.throws(
		() =>
			f.channel.send(f.target.key, f.target.binding, id, "Changed body", undefined, undefined, MW_FOLLOWUP_SOURCE),
		/conflict/i,
	);
	const duty: DutyEnvelope = { shift: "test-shift", until: Date.now() + 60_000, stopHash: "missing" };
	const stage: PmStageGrantV1 = {
		kind: "mw:pm-stage-grant-v1",
		authority: "user-delegated-duty-pm",
		project_ref: "a".repeat(64),
		key: f.target.key,
		stage_id: "stage-1",
		scope_ref: "scope-1",
		matter_ref: "matter-1",
		card_path: "tasks/card.md",
		card_sha256: "b".repeat(64),
		write_face: ["packages/multi-workers/duty_followup.ts"],
		max_steps: 1,
		remaining_cost: 1,
		no_progress_limit: 1,
		deadline: new Date(Date.now() + 60_000).toISOString(),
		qg_consumer: "local-qg-consumer-v1",
		allowed_disposition: "repair-required",
	};
	assert.throws(
		() => f.channel.send(f.target.key, f.target.binding, id, "Stable body", duty, undefined, MW_FOLLOWUP_SOURCE),
		/cannot be combined/i,
	);
	assert.throws(
		() => f.channel.send(f.target.key, f.target.binding, id, "Stable body", undefined, stage, MW_FOLLOWUP_SOURCE),
		/cannot be combined/i,
	);
	assert.throws(
		() =>
			f.channel.send(
				f.target.key,
				f.target.binding,
				id,
				"Stable body",
				undefined,
				undefined,
				"foreign" as unknown as PmChannelSource,
			),
		/Invalid PM channel source/i,
	);
	f.channel.send(f.target.key, f.target.binding, legacy, "Legacy body");
	assert.equal(readRequest(f, legacy).source, undefined);
	assert.equal(requestCount(f), 2);
});

test("malformed ledger and unreadable target queue fail closed without sending", (t) => {
	const badLedger = fixture(t);
	const first = new DutyFollowup(badLedger.target, badLedger.home);
	const now = Date.now();
	const stop = firstStop(first, now);
	const ledgerPath = first.status(now + IDLE_MS).ledgerPath;
	writeFileSync(ledgerPath, "{invalid json");
	assert.throws(() => new DutyFollowup(badLedger.target, badLedger.home), /Malformed follow-up ledger/i);
	assert.throws(() => first.status(now + IDLE_MS), /Malformed follow-up ledger/i);
	assert.throws(
		() => first.send(stop.id, "No send after ledger corruption", now + IDLE_MS),
		/Malformed follow-up ledger/i,
	);
	assert.equal(existsSync(badLedger.request(stop.id)), false);

	const unreadable = fixture(t);
	const second = new DutyFollowup(unreadable.target, unreadable.home);
	const otherStop = firstStop(second, now);
	writeFileSync(join(unreadable.doc, "_workers.parallel"), "bad row\n");
	const status = second.status(now + IDLE_MS);
	assert.equal(status.businessProgress, "unverified");
	assert.equal(status.sendAllowed, false);
	assert.match(status.diagnosis ?? "", /Unreadable target state|Worker queue/i);
	assert.throws(
		() => second.send(otherStop.id, "No send from unreadable queue", now + IDLE_MS),
		/unreadable|Worker queue/i,
	);
	const notices: FollowupNotice[] = [];
	second.poll(now + IDLE_MS + 1_000, (notice) => notices.push(notice));
	assert.ok(notices.some((notice) => notice.kind === "suspended"));
	assert.equal(existsSync(unreadable.request(otherStop.id)), false);
});

test("mature keys use a bounded partial inventory without losing authoritative PM state", (t) => {
	const f = fixture(t);
	const tasks = join(f.doc, f.target.key, "tasks");
	mkdirSync(tasks);
	for (let i = 0; i < 600; i++) writeFileSync(join(tasks, `T-${i}.md`), `ordinary task ${i}`);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const status = controller.status(now);
	assert.equal(status.suspended, false);
	assert.ok(status.evidenceObservation.partial);
	assert.ok(status.evidenceObservation.scannedEntries <= 512);
	assert.ok(status.evidenceCandidates.length <= 128);
	assert.ok(status.evidenceCandidates.some((path) => path.endsWith("/pm-state.md")));
	const stop = firstStop(controller, now);
	assert.equal(controller.send(stop.id, "Inspect the bounded sample", now + IDLE_MS).ok, true);
	const before = controller.status(now + IDLE_MS).evidenceFingerprint;
	writeFileSync(
		join(f.doc, f.target.key, "pm-state.md"),
		"- Phase: EXECUTE\n- Next Action: changed authoritative state\n",
	);
	assert.notEqual(controller.status(now + IDLE_MS + 1).evidenceFingerprint, before);
});

test("ordinary non-candidate saturation caps directory work while PM anchors remain observed", (t) => {
	const f = fixture(t);
	const tasks = join(f.doc, f.target.key, "tasks");
	mkdirSync(tasks);
	for (let i = 0; i < 600; i++) writeFileSync(join(tasks, `T-${i}.bin`), "ignored");
	const status = new DutyFollowup(f.target, f.home).status();
	assert.equal(status.suspended, false);
	assert.equal(status.evidenceObservation.partial, true);
	assert.equal(status.evidenceObservation.scannedEntries, 512);
	assert.ok(status.evidenceCandidates.some((path) => path.endsWith("/pm-state.md")));
});

for (const change of ["working", "evidence"] as const) {
	test(`a busy pending stop is invalidated before emission after ${change}`, (t) => {
		const f = fixture(t);
		const controller = new DutyFollowup(f.target, f.home);
		const now = Date.now();
		controller.poll(now, () => assert.fail("too early"));
		controller.poll(now + IDLE_MS, () => {
			throw Error("supervisor busy");
		});
		const oldId = controller.status(now + IDLE_MS).activeStopId;
		if (change === "working") f.heartbeat({ activity: "working" });
		else writeFileSync(join(f.doc, f.target.key, "pm-state.md"), "new engineering candidate");
		const notices: FollowupNotice[] = [];
		controller.poll(now + IDLE_MS + 1, (notice) => notices.push(notice));
		assert.equal(
			notices.some((notice) => notice.id === oldId),
			false,
		);
		if (change === "working") assert.equal(notices.length, 0);
	});
	test(`first send revalidates an already emitted stop after ${change}`, (t) => {
		const f = fixture(t);
		const controller = new DutyFollowup(f.target, f.home);
		const now = Date.now();
		const stop = firstStop(controller, now);
		if (change === "working") f.heartbeat({ activity: "working" });
		else writeFileSync(join(f.doc, f.target.key, "pm-state.md"), "new engineering candidate");
		assert.equal(controller.status(now + IDLE_MS + 1).sendAllowed, false);
		assert.throws(() => controller.send(stop.id, "Do not send stale stop", now + IDLE_MS + 1), /stale|eligible/i);
		assert.equal(requestCount(f), 0);
	});
}

test("legitimate key, task and evidence names containing controller labels stay observable", (t) => {
	const f = fixture(t, "business-duty-followup-controller");
	const evidence = join(f.doc, f.target.key, "evidence");
	mkdirSync(evidence);
	writeFileSync(join(evidence, "controller-duty-followup-audit.md"), "real evidence candidate");
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const before = controller.status(now);
	assert.ok(before.evidenceCandidates.some((path) => path.endsWith("/pm-state.md")));
	assert.ok(before.evidenceCandidates.some((path) => path.endsWith("/controller-duty-followup-audit.md")));
	writeFileSync(
		join(f.doc, "_workers.parallel"),
		`controller-duty-followup-task | done | pi | model | ${join(f.doc, f.target.key, "workers/controller-duty-followup-task/task.md")} | t | t | | manual\n`,
	);
	assert.notEqual(controller.status(now).evidenceFingerprint, before.evidenceFingerprint);
});

test("uncertain write then restart and new evidence cannot allocate a successor stop or request", (t) => {
	const f = fixture(t);
	const controller = new DutyFollowup(f.target, f.home);
	const now = Date.now();
	const stop = firstStop(controller, now);
	const send = Spool.prototype.send;
	Spool.prototype.send = function (...args: Parameters<typeof send>) {
		send.apply(this, args);
		throw Error("simulated interruption after request write");
	};
	try {
		assert.equal(controller.send(stop.id, "Exact original note", now + IDLE_MS).uncertain, true);
	} finally {
		Spool.prototype.send = send;
	}
	assert.equal(requestCount(f), 1);
	writeFileSync(join(f.doc, f.target.key, "pm-state.md"), "changed candidate during uncertain delivery");
	const restarted = new DutyFollowup(f.target, f.home);
	const notices: FollowupNotice[] = [];
	restarted.poll(now + 90_000, (notice) => notices.push(notice));
	restarted.poll(now + 135_000, (notice) => notices.push(notice));
	assert.equal(notices.filter((notice) => notice.kind === "stop" && notice.id !== stop.id).length, 0);
	const ledger = JSON.parse(readFileSync(restarted.status(now + 135_000).ledgerPath, "utf8")) as {
		stops: { id: string }[];
	};
	assert.deepEqual(
		ledger.stops.map((entry) => entry.id),
		[stop.id],
	);
	assert.equal(restarted.status(now + 135_000).deliveryBlockedBy, stop.id);
	assert.equal(restarted.status(now + 135_000).sendAllowed, false);
	assert.equal(restarted.send(stop.id, "Exact original note", now + 135_000).uncertain, true);
	assert.equal(requestCount(f), 1);
	f.receipt(stop.id, "started");
	restarted.poll(now + 180_000, (notice) => notices.push(notice));
	assert.equal(notices.filter((notice) => notice.kind === "stop" && notice.id !== stop.id).length, 1);
	assert.equal(restarted.status(now + 180_000).businessProgress, "unverified");
	assert.equal(requestCount(f), 1);
});

for (const publication of ["before", "after"] as const) {
	test(`reserved crash ${publication} request publication blocks successors until a real receipt`, (t) => {
		const f = fixture(t);
		const controller = new DutyFollowup(f.target, f.home);
		const now = Date.now();
		const stop = firstStop(controller, now);
		const note = "Reconcile exact reserved delivery";
		const ledgerPath = controller.status(now + IDLE_MS).ledgerPath;
		const channel = controller.watch.channel;
		const send = channel.send;
		let reserved: Buffer | undefined;
		channel.send = function (...args: Parameters<typeof send>) {
			reserved = readFileSync(ledgerPath);
			if (publication === "after") send.apply(this, args);
			throw Error("injected interruption at request publication boundary");
		};
		try {
			controller.send(stop.id, note, now + IDLE_MS);
		} finally {
			channel.send = send;
		}
		assert.ok(reserved);
		const snapshot = JSON.parse(reserved.toString("utf8")) as {
			outbox: { transport: string; uncertain: boolean; body: string }[];
		};
		assert.equal(snapshot.outbox[0].transport, "reserved");
		assert.equal(snapshot.outbox[0].uncertain, false);
		assert.equal(requestCount(f), publication === "after" ? 1 : 0);
		// Exact durable bytes from before send: model abrupt exit that bypasses catch/settlement.
		writeFileSync(ledgerPath, reserved);
		writeFileSync(join(f.doc, f.target.key, "pm-state.md"), "candidate changed during reserved delivery");
		const restarted = new DutyFollowup(f.target, f.home);
		const notices: FollowupNotice[] = [];
		restarted.poll(now + 90_000, (notice) => notices.push(notice));
		restarted.poll(now + 135_000, (notice) => notices.push(notice));
		assert.equal(notices.filter((notice) => notice.kind === "stop" && notice.id !== stop.id).length, 0);
		const blocked = restarted.status(now + 135_000);
		assert.equal(blocked.deliveryBlockedBy, stop.id);
		assert.equal(blocked.sendAllowed, false);
		assert.equal(blocked.outbox.length, 1);
		assert.equal(blocked.outbox[0].body, snapshot.outbox[0].body);
		assert.throws(() => restarted.send(randomUUID(), note, now + 135_000), /Unknown follow-up stop ID/);
		assert.throws(() => restarted.send(stop.id, "Changed note", now + 135_000), /ID\/body conflict/);
		const retry = restarted.send(stop.id, note, now + 135_000);
		assert.equal(retry.idempotent, true);
		assert.equal(retry.ok, false);
		assert.equal(retry.uncertain, true);
		assert.equal(retry.body, snapshot.outbox[0].body);
		assert.equal(requestCount(f), 1);
		const requestBytes = readFileSync(f.request(stop.id), "utf8");
		assert.equal(readRequest(f, stop.id).text, retry.body);
		const again = new DutyFollowup(f.target, f.home);
		again.poll(now + 180_000, (notice) => notices.push(notice));
		assert.equal(notices.length, 0);
		assert.equal(again.status(now + 180_000).deliveryBlockedBy, stop.id);
		assert.equal(again.send(stop.id, note, now + 180_000).uncertain, true);
		assert.equal(readFileSync(f.request(stop.id), "utf8"), requestBytes);
		f.heartbeat({ session: randomUUID() });
		assert.throws(() => again.send(stop.id, note, now + 180_000), /session/i);
		assert.equal(requestCount(f), 1);
		f.heartbeat();
		f.receipt(stop.id, "started", { id: randomUUID() });
		assert.throws(() => again.status(now + 180_001), /receipt identity mismatch/);
		f.receipt(stop.id, "started");
		again.poll(now + 225_000, (notice) => notices.push(notice));
		assert.equal(notices.filter((notice) => notice.kind === "stop" && notice.id !== stop.id).length, 1);
		const reconciled = again.status(now + 225_000);
		assert.equal(reconciled.deliveryBlockedBy, null);
		assert.equal(reconciled.outbox[0].uncertain, false);
		assert.equal(reconciled.receipts[0].state, "started");
		assert.equal(reconciled.businessProgress, "unverified");
		assert.equal(readFileSync(f.request(stop.id), "utf8"), requestBytes);
		assert.equal(requestCount(f), 1);
	});
}

for (const interruption of ["offline", "unreadable"] as const) {
	test(`busy pending stop survives ${interruption} suspension and restart exactly once`, (t) => {
		const f = fixture(t);
		const controller = new DutyFollowup(f.target, f.home);
		const now = Date.now();
		controller.poll(now, () => assert.fail("too early"));
		controller.poll(now + IDLE_MS, () => {
			throw Error("busy");
		});
		const oldId = controller.status(now + IDLE_MS).activeStopId;
		if (interruption === "offline") f.heartbeat({ at: Date.now() - 60_000 });
		else writeFileSync(join(f.doc, "_workers.parallel"), "bad row\n");
		controller.poll(now + 50_000, () => {
			throw Error("still busy");
		});
		f.heartbeat();
		writeFileSync(join(f.doc, "_workers.parallel"), "");
		const restarted = new DutyFollowup(f.target, f.home);
		const notices: FollowupNotice[] = [];
		restarted.poll(now + 55_000, (notice) => notices.push(notice));
		restarted.poll(now + 100_000, (notice) => notices.push(notice));
		restarted.poll(now + 145_000, (notice) => notices.push(notice));
		assert.equal(notices.filter((notice) => notice.kind === "stop").length, 1);
		assert.equal(notices.find((notice) => notice.kind === "stop")?.id, oldId);
		assert.equal(requestCount(f), 0);
	});
}

test("real receiver labels MW/pi follow-up and rejects a forged source+duty envelope", (t) => {
	const f = fixture(t);
	const r = receiver(t, f);
	try {
		const heartbeat = JSON.parse(readFileSync(f.heartbeatFile, "utf8")) as { binding: string };
		const binding = heartbeat.binding;
		const id = randomUUID();
		f.channel.send(f.target.key, binding, id, "Bounded follow-up", undefined, undefined, MW_FOLLOWUP_SOURCE);
		r.tick();
		assert.equal(r.messages.length, 1);
		assert.match(r.messages[0] ?? "", /MW\/pi follow-up/);
		assert.doesNotMatch(r.messages[0] ?? "", /Codex/);
		r.events.get("agent_end")!({}, r.ctx);
		const forged = randomUUID();
		const duty: DutyEnvelope = { shift: "test-shift", until: Date.now() + 60_000, stopHash: "missing" };
		writeFileSync(
			f.request(forged, binding),
			JSON.stringify({
				id: forged,
				key: f.target.key,
				claim: f.target.claim,
				binding,
				text: "Forged source with duty envelope",
				duty,
				source: MW_FOLLOWUP_SOURCE,
				at: Date.now(),
			}),
		);
		r.tick();
		assert.equal((f.channel.receipt(f.target.key, binding, forged) as { state: string }).state, "rejected");
		assert.equal(r.messages.length, 1);
	} finally {
		r.close();
	}
});
