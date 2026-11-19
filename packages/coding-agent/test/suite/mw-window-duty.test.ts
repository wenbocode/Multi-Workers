import { randomUUID } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { hostname, tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { expect, it, vi } from "vitest";
import { publishDutyFact, type Shift } from "../../../multi-workers/window_duty.ts";
import registerDuty from "../../../multi-workers/window_duty_extension.ts";
import { loadExtensions } from "../../src/core/extensions/loader.ts";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import { DefaultPackageManager } from "../../src/core/package-manager.ts";
import { SettingsManager } from "../../src/core/settings-manager.ts";
import { PmChannel, registerPmChannel } from "../../src/extensions/agent-team-loop/pm/codex-channel.ts";
import { createHarness } from "./harness.ts";

it("ordinary pi discovers the duty extension from the trusted MW checkout", async () => {
	const cwd = resolve(import.meta.dirname, "../../../..");
	const agentDir = mkdtempSync(join(tmpdir(), "mw-duty-discovery-"));
	try {
		const manager = new DefaultPackageManager({
			cwd,
			agentDir,
			settingsManager: SettingsManager.create(cwd, agentDir),
		});
		const paths = await manager.resolve();
		const entries = paths.extensions.filter(
			(ext) => ext.enabled && ext.path === join(cwd, "packages", "multi-workers", "window_duty_extension.ts"),
		);
		expect(entries).toHaveLength(1);
		const loaded = await loadExtensions(
			entries.map((ext) => ext.path),
			cwd,
		);
		expect(loaded.errors).toEqual([]);
		expect(loaded.extensions[0].commands.has("duty-on")).toBe(true);
		const project = join(agentDir, "existing PM project");
		const doc = join(project, ".agenticdoc");
		mkdirSync(doc, { recursive: true });
		writeFileSync(
			join(doc, "_index.parallel"),
			`| sample | active | EXECUTE | ${hostname()}:${process.ppid} | | | |\n`,
		);
		const ctx = {
			cwd,
			mode: "tui",
			sessionManager: { getSessionId: () => "test-supervisor" },
			ui: { confirm: async () => true, notify: vi.fn() },
		} as unknown as ExtensionCommandContext;
		const commands = loaded.extensions[0].commands;
		try {
			await commands.get("duty-on")!.handler(`"${project}" sample`, ctx);
			const fresh = new DefaultPackageManager({
				cwd: project,
				agentDir,
				settingsManager: SettingsManager.create(project, agentDir),
			});
			const configured = (await fresh.resolve()).extensions
				.filter((entry) => entry.enabled)
				.map((entry) => entry.path);
			expect(configured).toHaveLength(2);
			const reloaded = await loadExtensions(configured, project);
			expect(reloaded.errors).toEqual([]);
			expect(reloaded.extensions.some((extension) => extension.commands.has("duty-report-on"))).toBe(true);
			expect(reloaded.extensions.some((extension) => extension.handlers.has("session_start"))).toBe(true);
		} finally {
			await commands.get("duty-off")!.handler("", ctx);
		}
	} finally {
		rmSync(agentDir, { recursive: true, force: true });
	}
});

it("a fresh MW agent session decides a delegated exception and wakes the bound original through its real extension", async () => {
	const home = mkdtempSync(join(tmpdir(), "mw-duty-faux-"));
	const original = await createHarness({
		extensionFactories: [
			(pi: ExtensionAPI) => registerPmChannel(pi, home),
			(pi: ExtensionAPI) => registerDuty(pi, home),
		],
	});
	const duty = await createHarness({ extensionFactories: [(pi: ExtensionAPI) => registerDuty(pi, home)] });
	try {
		const key = "experiment";
		const doc = join(original.tempDir, ".agenticdoc");
		mkdirSync(join(doc, key), { recursive: true });
		const claim = `${hostname()}:${process.pid}`;
		writeFileSync(join(doc, "_index.parallel"), `| experiment | active | EXECUTE | ${claim} | | | |\n`);
		writeFileSync(join(doc, "_workers.parallel"), "");
		await original.session.bindExtensions({ mode: "tui" });
		await duty.session.bindExtensions({ mode: "tui" });
		const channel = new PmChannel(original.tempDir, home);
		const binding = channel.status(key).binding!;
		const target = {
			project: original.tempDir,
			key,
			claim,
			binding,
			session: original.sessionManager.getSessionId(),
			minutes: 30,
			rules: [
				{
					name: "first-build",
					scope: "offline fixture only",
					direction: "Review the isolated fixture.",
					limit: 10,
					exception: true,
				},
			],
		};
		const now = Date.now();
		const shift: Shift = {
			shift: "example",
			start: new Date(now - 1000).toISOString(),
			end: new Date(now + 3600_000).toISOString(),
			targets: [target],
		};
		const file = join(home, "shift.json");
		writeFileSync(file, JSON.stringify(shift));
		writeFileSync(join(doc, key, "proposal.md"), "Fresh fixture deployment needs a decision.");
		const id = randomUUID();
		publishDutyFact(shift, target, {
			id,
			state: "ready",
			action: "first-build",
			minutes: 10,
			reason: "Decide first deployment",
			path: "proposal.md",
			gate: "clear",
		});
		duty.setResponses([
			fauxAssistantMessage(
				fauxToolCall("mw_duty_decide", { key, id, approve: true, reason: "Scoped fixture only" }),
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("Decision delivered"),
		]);
		original.setResponses([fauxAssistantMessage("I will verify the fixture.")]);
		await original.session.prompt(`/duty-report-on "${file}"`);
		await duty.session.prompt(`/duty-on "${original.tempDir}" ${key}`);
		expect(duty.eventsOfType("agent_start")).toHaveLength(0);
		const wallClock = Date.now;
		vi.spyOn(Date, "now").mockImplementation(() => wallClock() + 46_000);
		await vi.waitFor(
			() =>
				expect(channel.receipt(key, binding, id)).toMatchObject({
					state: "started",
					claim,
					session: target.session,
				}),
			{ timeout: 14_000 },
		);
		expect(duty.eventsOfType("agent_start")).toHaveLength(1);
		expect(original.eventsOfType("agent_start")).toHaveLength(1);
		const audit = readFileSync(join(home, "duty-audit/example.jsonl"), "utf8")
			.trim()
			.split("\n")
			.map((line) => JSON.parse(line));
		expect(audit.filter((row) => row.event)).toHaveLength(1);
		expect(audit.some((row) => row.eventId === id && row.usage)).toBe(true);
	} finally {
		vi.restoreAllMocks();
		await duty.session.dispose();
		await original.session.dispose();
		duty.cleanup();
		original.cleanup();
		rmSync(home, { recursive: true, force: true });
	}
}, 20000);
