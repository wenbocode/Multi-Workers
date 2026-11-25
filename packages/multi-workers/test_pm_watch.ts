import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { StopWatch } from "./pm_watch.ts";

test("a worker masks idle, stable stops fire once, a new turn rearms, another binding is never reported idle", () => {
	const root = mkdtempSync(join(tmpdir(), "pm-watch-"));
	try {
		const doc = join(root, ".agenticdoc");
		mkdirSync(doc);
		const claim = "host:123";
		const binding = randomUUID();
		const watch = new StopWatch(root, "alpha", claim, binding, root);
		const index = join(doc, "_index.parallel");
		writeFileSync(index, `| alpha | active | EXECUTE | ${claim} | | | |\n`);
		const dir = join(watch.channel.dir, "alpha");
		mkdirSync(dir, { recursive: true });
		const publish = (activity: string, id = binding, age = 0) => writeFileSync(join(dir, createHash("sha256").update(claim).digest("hex") + ".json"),
			JSON.stringify({ claim, binding: id, at: Date.now() - age, activity }));
		publish("idle");
		const queue = join(doc, "_workers.parallel");
		writeFileSync(queue, `w | running | pi | timi | ${join(doc, "alpha/workers/w/task.md")} | t | t\n`);
		assert.equal(watch.sample().state, "waiting-for-worker");
		assert.equal(watch.observe(0), undefined);
		assert.equal(watch.observe(70000), undefined);
		const workerDir = join(doc, "alpha/workers/w");
		mkdirSync(workerDir, { recursive: true });
		const stopped = spawnSync(process.execPath, ["-e", ""]);
		assert.equal(stopped.status, 0);
		const runFile = join(workerDir, "run.json");
		const start = new Date(Date.now() - 300_000).toISOString();
		const row = `w | running | pi | timi | ${join(workerDir, "task.md")} | ${start} | t\n`;
		writeFileSync(queue, row);
		const run = { task_key: "w", owner_key: "alpha", started_at: start, last_heartbeat_at: start, pid: process.pid, status: "running" };
		writeFileSync(runFile, JSON.stringify(run));
		assert.equal(watch.sample().state, "waiting-for-worker");
		run.pid = stopped.pid;
		writeFileSync(runFile, JSON.stringify({ ...run, last_heartbeat_at: new Date().toISOString() }));
		assert.equal(watch.sample().state, "waiting-for-worker");
		writeFileSync(runFile, JSON.stringify(run));
		writeFileSync(queue, row + `next | pending | pi | timi | ${join(doc, "alpha/workers/next/task.md")} | t | t\n`);
		assert.equal(watch.sample().state, "waiting-for-worker");
		writeFileSync(queue, row);
		assert.equal(watch.observe(70001), undefined);
		assert.equal(watch.observe(115001)?.state, "worker-lost");
		assert.equal(watch.observe(116001), undefined);
		writeFileSync(queue, `w | running | pi | timi | ${join(doc, "other/workers/w/task.md")} | t | t\n`);
		assert.equal(watch.observe(71000), undefined);
		assert.equal(watch.observe(116000)?.state, "idle");
		assert.equal(watch.observe(300000), undefined);
		publish("working");
		assert.equal(watch.observe(301000), undefined);
		publish("idle");
		assert.equal(watch.observe(302000), undefined);
		assert.equal(watch.observe(347000)?.state, "idle");
		writeFileSync(queue, "bad row");
		assert.equal(watch.sample().state, "unobservable");
		publish("idle", binding, 60000);
		assert.equal(watch.sample().state, "offline");
		publish("idle", randomUUID());
		assert.equal(watch.observe(348000)?.state, "binding-changed");
	} finally {
		rmSync(root, { recursive: true, force: true });
	}
});

function makeFixture(key = "alpha") {
	const root = mkdtempSync(join(tmpdir(), "pm-watch-file-"));
	const doc = join(root, ".agenticdoc");
	mkdirSync(doc);
	const claim = "host:123";
	const binding = randomUUID();
	const index = join(doc, "_index.parallel");
	const queue = join(doc, "_workers.parallel");
	writeFileSync(index, `| ${key} | active | EXECUTE | ${claim} | | | |\n`);
	const create = (requirePm: boolean, watched = key) => new StopWatch(root, watched, claim, binding, root, { requirePm });
	const publish = (activity: string, age = 0) => {
		const dir = join(create(false).channel.dir, key);
		mkdirSync(dir, { recursive: true });
		writeFileSync(join(dir, createHash("sha256").update(claim).digest("hex") + ".json"),
			JSON.stringify({ claim, binding, at: Date.now() - age, activity }));
	};
	return { root, doc, key, claim, index, queue, create, publish };
}

function exitedPid(): number {
	const child = spawnSync(process.execPath, ["-e", ""]);
	assert.equal(child.status, 0);
	assert.ok(typeof child.pid === "number" && child.pid > 0);
	return child.pid;
}

function writeRunningWorker(doc: string, key: string, queue: string, taskKey: string, pid: number): { workerDir: string; start: string } {
	const workerDir = join(doc, `${key}/workers/${taskKey}`);
	mkdirSync(workerDir, { recursive: true });
	const start = new Date(Date.now() - 300_000).toISOString();
	writeFileSync(queue, `${taskKey} | running | pi | timi | ${join(workerDir, "task.md")} | ${start} | t\n`);
	writeFileSync(join(workerDir, "run.json"),
		JSON.stringify({ task_key: taskKey, owner_key: key, started_at: start, last_heartbeat_at: start, pid, status: "running" }));
	return { workerDir, start };
}

test("requirePm=false reports worker-lost without a PM heartbeat, fires once and re-arms on a new stop", () => {
	const f = makeFixture();
	try {
		const watch = f.create(false);
		const { workerDir, start } = writeRunningWorker(f.doc, f.key, f.queue, "w", exitedPid());
		const lost = watch.sample();
		assert.equal(lost.state, "worker-lost");
		assert.equal(lost.detail, "w, PM offline");
		assert.equal(watch.observe(0), undefined);
		const event = watch.observe(45_000);
		assert.equal(event?.state, "worker-lost");
		assert.equal(event?.detail, "w, PM offline");
		assert.equal(watch.observe(46_000), undefined);
		writeFileSync(f.queue, `w | pending | pi | timi | ${join(workerDir, "task.md")} | ${start} | t\n`);
		assert.equal(watch.sample().state, "waiting-for-worker");
		assert.equal(watch.observe(47_000), undefined);
		writeFileSync(f.queue, `w | running | pi | timi | ${join(workerDir, "task.md")} | ${start} | t\n`);
		assert.equal(watch.sample().state, "worker-lost");
		assert.equal(watch.observe(48_000), undefined);
		assert.equal(watch.observe(93_000)?.state, "worker-lost");
	} finally {
		rmSync(f.root, { recursive: true, force: true });
	}
});

test("requirePm=false keeps an empty queue visible as idle with a PM offline note, then follows the heartbeat", () => {
	const f = makeFixture();
	try {
		writeFileSync(f.queue, "");
		const watch = f.create(false);
		const idle = watch.sample();
		assert.equal(idle.state, "idle");
		assert.match(idle.detail ?? "", /PM offline/);
		f.publish("working");
		assert.equal(watch.sample().state, "working");
		f.publish("thinking");
		assert.deepEqual(watch.sample(), { state: "unobservable", detail: "Unknown PM activity" });
		f.publish("idle");
		assert.deepEqual(watch.sample(), { state: "idle" });
	} finally {
		rmSync(f.root, { recursive: true, force: true });
	}
});

test("requirePm=false treats unreadable queues and unknown keys as unobservable and a DONE key as finished", () => {
	const f = makeFixture();
	try {
		writeFileSync(f.queue, "bad row");
		assert.equal(f.create(false).sample().state, "unobservable");
		writeFileSync(f.queue, "# mw-queue:v3\n");
		assert.equal(f.create(false).sample().state, "unobservable");
		writeFileSync(f.queue, `w | zombie | pi | timi | ${join(f.doc, `${f.key}/workers/w/task.md`)} | t | t\n`);
		assert.equal(f.create(false).sample().state, "unobservable");
		writeFileSync(f.queue, "bad row");
		assert.equal(f.create(false, "ghost").sample().state, "unobservable");
		writeFileSync(f.index, `| ${f.key} | DONE | DONE | ${f.claim} | | | |\n`);
		assert.equal(f.create(false).sample().state, "finished");
	} finally {
		rmSync(f.root, { recursive: true, force: true });
	}
});

test("the default requirePm path still reports offline for the same dead worker without a PM heartbeat", () => {
	const f = makeFixture();
	try {
		writeRunningWorker(f.doc, f.key, f.queue, "w", exitedPid());
		assert.deepEqual(f.create(true).sample(), { state: "offline" });
	} finally {
		rmSync(f.root, { recursive: true, force: true });
	}
});
