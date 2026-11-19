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
