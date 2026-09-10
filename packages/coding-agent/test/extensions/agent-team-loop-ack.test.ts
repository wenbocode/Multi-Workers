/**
 * Tests for the AckStore sidecar (mw-widget-terminal-lifecycle T-01,
 * AC-004/VC-004 — storage half: write/persist/idempotence of
 * `.agenticdoc/_workers.acked`). Channel and terminal-state validation are
 * T-07's scope.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "atl-ack-"));
}

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

function isIsoUtc(value: string): boolean {
	return !Number.isNaN(Date.parse(value)) && new Date(value).toISOString() === value;
}

describe("AckStore", () => {
	const roots: string[] = [];

	afterEach(() => {
		for (const root of roots.splice(0)) {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("write/read roundtrip: ack 2 keys, readAll returns both with valid UTC ISO timestamps", async () => {
		const root = mkdtemp();
		roots.push(root);
		const store = new AckStore(root);

		const res = await store.ack(["mw-widget-terminal-lifecycle/t-01", "mw-widget-terminal-lifecycle/t-02"]);
		expect(res.acked.sort()).toEqual(["mw-widget-terminal-lifecycle/t-01", "mw-widget-terminal-lifecycle/t-02"]);
		expect(res.rejected).toEqual([]);

		const all = store.readAll();
		expect(all.size).toBe(2);
		for (const ts of all.values()) {
			expect(isIsoUtc(ts)).toBe(true);
		}

		// Raw file keeps the pipe row format.
		const raw = fs.readFileSync(path.join(root, "_workers.acked"), "utf8").split("\n").filter(Boolean);
		expect(raw).toHaveLength(2);
		for (const line of raw) {
			expect(line).toMatch(/^[^|]+ \| \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
		}
	});

	it("idempotent: re-acking the same key keeps the count and overwrites the timestamp", async () => {
		const root = mkdtemp();
		roots.push(root);
		const store = new AckStore(root);

		await store.ack(["mw-widget-terminal-lifecycle/t-01"]);
		const first = store.readAll().get("mw-widget-terminal-lifecycle/t-01");
		expect(first).toBeDefined();

		await sleep(5); // ensure a new millisecond timestamp
		await store.ack(["mw-widget-terminal-lifecycle/t-01"]);
		const all = store.readAll();
		expect(all.size).toBe(1);
		const second = all.get("mw-widget-terminal-lifecycle/t-01");
		expect(second).toBeDefined();
		expect(second).not.toBe(first);
		expect(new Date(second ?? "").getTime()).toBeGreaterThan(new Date(first ?? "").getTime());
	});

	it("persists across instances: a fresh AckStore on the same root reads the same keys (VC-004)", async () => {
		const root = mkdtemp();
		roots.push(root);
		const keys = ["mw-widget-terminal-lifecycle/t-01-ack-store"];
		const res = await new AckStore(root).ack(keys);
		expect(res.rejected).toEqual([]);

		const reloaded = new AckStore(root).readAll();
		expect([...reloaded.keys()]).toEqual(keys);
		expect(isIsoUtc(reloaded.get(keys[0] ?? "") ?? "")).toBe(true);

		console.log(`[VERIFY] VC-004: acked=${keys.join(",")}, persisted=yes`);
	});

	it("tolerates bad rows and skips # comment lines on read", () => {
		const root = mkdtemp();
		roots.push(root);
		fs.writeFileSync(
			path.join(root, "_workers.acked"),
			[
				"# manual note",
				"good-key | 2026-01-02T03:04:05.006Z",
				"missing-pipe",
				"too | many | columns",
				"   | 2026-01-02T03:04:05.006Z",
				"empty-ts |",
				"",
			].join("\n"),
			"utf8",
		);

		const all = new AckStore(root).readAll();
		expect(all.size).toBe(1);
		expect(all.get("good-key")).toBe("2026-01-02T03:04:05.006Z");
	});

	it("rejects empty and |-containing keys without writing them", async () => {
		const root = mkdtemp();
		roots.push(root);
		const store = new AckStore(root);

		const res = await store.ack(["", "bad|key"]);
		expect(res.acked).toEqual([]);
		expect(res.rejected).toEqual(["", "bad|key"]);
		expect(fs.existsSync(path.join(root, "_workers.acked"))).toBe(false);

		// Mixed batch: only the valid key lands in the file.
		const mixed = await store.ack(["valid-key", "", "other|key"]);
		expect(mixed.acked).toEqual(["valid-key"]);
		expect(mixed.rejected).toEqual(["", "other|key"]);
		const all = store.readAll();
		expect(all.size).toBe(1);
		expect(all.has("valid-key")).toBe(true);
	});
});
