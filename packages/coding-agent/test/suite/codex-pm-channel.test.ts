import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage } from "@earendil-works/pi-ai";
import { expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { PmChannel, registerPmChannel } from "../../src/extensions/agent-team-loop/pm/codex-channel.ts";
import { createHarness } from "./harness.ts";

const sharing = vi.hoisted(() => ({ endpoint: "", failures: 0, attempts: 0 }));
vi.mock("node:fs", async (importOriginal) => {
	const real = await importOriginal<typeof fs>();
	return {
		...real,
		renameSync: (...args: Parameters<typeof fs.renameSync>) => {
			if (sharing.endpoint && String(args[1]) === sharing.endpoint) {
				sharing.attempts++;
				if (sharing.failures-- > 0) throw Object.assign(new Error("file is in use"), { code: "EPERM" });
			}
			return real.renameSync(...args);
		},
	};
});

it("routes a desktop instruction to its owning PM, records its actual response, and rejects replay or foreign keys", async () => {
	const home = fs.mkdtempSync(path.join(os.tmpdir(), "mw-channel-"));
	const h = await createHarness({ extensionFactories: [(pi: ExtensionAPI) => registerPmChannel(pi, home)] });
	try {
		const doc = path.join(h.tempDir, ".agenticdoc");
		fs.mkdirSync(doc);
		const index = path.join(doc, "_index.parallel");
		const claim = `${os.hostname()}:${process.pid}`;
		fs.writeFileSync(
			index,
			`| target | active | EXECUTE | ${claim} | | | |\n| foreign | active | VERIFY | other:22 | | | |\n`,
		);
		await h.session.bindExtensions({ mode: "tui" });
		const channel = new PmChannel(h.tempDir, home);
		const binding = channel.status("target").binding;
		if (!binding) throw new Error("Owner did not register");
		const id = randomUUID();
		expect(() => channel.send("foreign", binding, id, "wrong")).toThrow(/unavailable/);
		h.setResponses([fauxAssistantMessage("Starting the budget diagnosis")]);
		const target = path.join(channel.dir, "target");
		sharing.endpoint = path.join(target, fs.readdirSync(target).find((name) => name.endsWith(".json"))!);
		const original = fs.readFileSync(sharing.endpoint, "utf8");
		sharing.failures = 4;
		expect(channel.send("target", binding, id, "Trace the first denied reservation").state).toBe("queued");
		expect(channel.send("target", binding, id, "Trace the first denied reservation").state).toBe("queued");
		await vi.waitFor(
			() =>
				expect(channel.receipt("target", binding, id)).toMatchObject({
					state: "started",
					id,
					binding,
					claim,
					observation: "Starting the budget diagnosis",
				}),
			{ timeout: 7000 },
		);
		expect(channel.send("target", binding, id, "Trace the first denied reservation").state).toBe("started");
		expect(() => channel.send("target", binding, id, "different")).toThrow(/conflict/);
		expect(h.eventsOfType("agent_start")).toHaveLength(1);
		expect(sharing.attempts).toBeGreaterThanOrEqual(4);
		expect(JSON.parse(original).binding).toBe(binding);
		await vi.waitFor(() => expect(fs.readFileSync(sharing.endpoint, "utf8")).not.toBe(original), { timeout: 4000 });
		expect(channel.status("target").binding).toBe(binding);
		const next = randomUUID();
		channel.send("target", binding, next, "Do not deliver after reassignment");
		fs.writeFileSync(index, "| target | active | EXECUTE | other:22 | | | |\n");
		expect(channel.status("target").connected).toBe(false);
		await new Promise((resolve) => setTimeout(resolve, 2800));
		expect(h.eventsOfType("agent_start")).toHaveLength(1);
		expect(channel.receipt("target", binding, next).state).toBe("queued");
	} finally {
		sharing.endpoint = "";
		await h.session.dispose();
		h.cleanup();
		fs.rmSync(home, { recursive: true, force: true });
	}
}, 12000);
