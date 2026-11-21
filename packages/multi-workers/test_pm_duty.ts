import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { Duty } from "./pm_duty.ts";

test("retries one event, survives restart, suppresses a handled stop, and sends the next round", () => {
	const dir = mkdtempSync(join(tmpdir(), "mw-duty-"));
	const pin = { key: "demo", project: dir, binding: "binding", claim: "host:1", session: "session" };
	try {
		let duty = new Duty(pin, dir);
		let calls = 0;
		const deliver = () => ({ accepted: ++calls !== 1, detail: "test transport" });
		duty.tick("idle", 0, pin, deliver);
		duty.tick("idle", 45_000, pin, deliver);
		const first = duty.stopId;
		assert.ok(first);
		duty.tick("idle", 46_000, pin, deliver);
		assert.equal(calls, 1);
		duty = new Duty(pin, dir);
		duty.tick("idle", 47_000, pin, deliver);
		duty.tick("idle", 92_000, pin, deliver);
		assert.equal(calls, 2);
		assert.equal(duty.stopId, first);
		writeFileSync(join(dir, first + ".handled.json"), "{}");
		duty.tick("idle", 1_000_000, pin, deliver);
		assert.equal(calls, 2);
		duty.tick("working", 1_005_000, pin, deliver);
		duty.tick("waiting-for-worker", 1_010_000, pin, deliver);
		duty.tick("idle", 1_015_000, pin, deliver);
		duty.tick("idle", 1_060_000, pin, deliver);
		assert.notEqual(duty.stopId, first);
		assert.equal(calls, 3);
		const second = duty.stopId;
		duty.tick("idle", 1_070_000, pin, deliver, 1_065_000);
		duty.tick("idle", 1_115_000, pin, deliver);
		assert.notEqual(duty.stopId, second);
		assert.equal(calls, 4);
		const log = readFileSync(join(dir, "events.jsonl"), "utf8").trim().split("\n").map(line => JSON.parse(line));
		assert.deepEqual(log.map(entry => entry.id), [first, first, second, duty.stopId]);
	} finally {
		rmSync(dir, { recursive: true, force: true });
	}
});
