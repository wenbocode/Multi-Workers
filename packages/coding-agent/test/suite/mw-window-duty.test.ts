import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { hostname, tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterAll, beforeAll, expect, it, vi } from "vitest";
import { publishDutyFact, type Shift } from "../../../multi-workers/window_duty.ts";
import registerDuty from "../../../multi-workers/window_duty_extension.ts";
import { loadExtensions } from "../../src/core/extensions/loader.ts";
import type { ExtensionAPI, ExtensionCommandContext, ToolDefinition } from "../../src/core/extensions/types.ts";
import { DefaultPackageManager } from "../../src/core/package-manager.ts";
import { SettingsManager } from "../../src/core/settings-manager.ts";
import { PmChannel, registerPmChannel } from "../../src/extensions/agent-team-loop/pm/codex-channel.ts";
import { createHarness, type Harness } from "./harness.ts";

/** The worker-task marker is a process-level switch: a supervisor extension must register in tests. */
let savedWorkerTask: string | undefined;
beforeAll(() => {
	savedWorkerTask = process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_TASK;
});
afterAll(() => {
	if (savedWorkerTask !== undefined) process.env.PI_WORKER_TASK = savedWorkerTask;
});

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
		const notify = vi.fn();
		const ctx = {
			cwd,
			mode: "tui",
			sessionManager: { getSessionId: () => "test-supervisor" },
			ui: { confirm: async () => true, notify },
		} as unknown as ExtensionCommandContext;
		const commands = loaded.extensions[0].commands;
		try {
			// First wiring is an explicit consent step of the follow-up entry, not of read-only observation.
			await commands.get("duty-followup-on")!.handler(`"${project}" sample`, ctx);
			expect(notify.mock.calls.some(([message]) => String(message).includes("/reload"))).toBe(true);
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

it("a single /duty-on <key> observes this window's project without a PM, setup write or message", async () => {
	const home = mkdtempSync(join(tmpdir(), "mw-duty-single-"));
	const tools = new Map<string, ToolDefinition>();
	const extension = (pi: ExtensionAPI) => {
		const proxy = new Proxy(pi, {
			get(target, prop, receiver) {
				if (prop === "registerTool")
					return (definition: ToolDefinition) => {
						tools.set(definition.name, definition);
						return target.registerTool(definition);
					};
				const value = Reflect.get(target, prop, receiver);
				return typeof value === "function" ? (value as (...args: unknown[]) => unknown).bind(target) : value;
			},
		});
		registerDuty(proxy, home);
	};
	const duty: Harness = await createHarness({ extensionFactories: [extension] });
	try {
		const key = "single-window";
		const doc = join(duty.tempDir, ".agenticdoc");
		const settings = join(duty.tempDir, ".pi", "settings.json");
		mkdirSync(join(doc, key), { recursive: true });
		writeFileSync(join(doc, "_index.parallel"), `| ${key} | active | EXECUTE | other-host:4242 | | | |\n`);
		writeFileSync(join(doc, "_workers.parallel"), "");
		const index = readFileSync(join(doc, "_index.parallel"), "utf8");
		await duty.session.bindExtensions({ mode: "tui" });
		await duty.session.prompt(`/duty-on ${key}`);
		const definition = tools.get("mw_duty_status");
		expect(definition).toBeDefined();
		const ctx = {
			cwd: duty.tempDir,
			mode: "tui",
			isIdle: () => true,
			hasPendingMessages: () => false,
			sessionManager: duty.sessionManager,
			ui: { notify: () => {}, confirm: async () => false },
		} as unknown as ExtensionCommandContext;
		const result = (await definition!.execute("call", {}, undefined, undefined, ctx)) as {
			details: {
				mode: string;
				pinnedTargets: Array<{ project: string; key: string; claim: string; binding: string; session: string }>;
				businessProgress: string;
			};
		};
		expect(result.details.mode).toBe("observation");
		expect(result.details.businessProgress).toBe("unverified");
		expect(result.details.pinnedTargets).toHaveLength(1);
		expect(result.details.pinnedTargets[0]).toMatchObject({
			project: resolve(duty.tempDir),
			key,
			claim: "",
			binding: "",
			session: "",
		});
		expect(readFileSync(join(doc, "_index.parallel"), "utf8")).toBe(index);
		expect(existsSync(settings)).toBe(false);
		expect(duty.eventsOfType("agent_start")).toHaveLength(0);
		expect(duty.faux.state.callCount).toBe(0);
		expect(duty.session.messages.filter((message) => message.role === "custom")).toHaveLength(0);
		const channel = new PmChannel(duty.tempDir, home);
		const requests = existsSync(channel.dir)
			? readdirSync(channel.dir, { recursive: true }).filter((name) => String(name).endsWith(".request.json"))
			: [];
		expect(requests).toHaveLength(0);
	} finally {
		await duty.session.dispose();
		duty.cleanup();
		rmSync(home, { recursive: true, force: true });
	}
}, 20000);
