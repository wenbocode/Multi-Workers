/**
 * decide-controls.test.ts — suite-level entry wiring for the new `/mw decide`
 * controls (mw-decide-window-controls T-01, AC-001/003/005, VC-005).
 *
 * Uses test/suite/harness.ts + the faux provider: the real registered `/mw`
 * command is dispatched through `AgentSession.prompt`, no real model turn is
 * consumed, and provider credentials are masked. No confirmed write is sent
 * through this entry on purpose — a confirmed `set`/`dp on` would call the real
 * `mw.py` and write a config/authority file. Confirm=false proves the human
 * gate at the real entry; probe is deliberately NOT prompted here because the
 * real CLI may issue a paid request (its fixed argv and all fake-green exits
 * are covered offline in test/extensions/decide-controls.test.ts).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionUIContext } from "../../src/core/extensions/types.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, type Harness } from "./harness.ts";

function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

interface Notify {
	message: string;
	type: string;
}

interface ConfirmCall {
	title: string;
	message: string;
}

const tmpDirs: string[] = [];
const harnesses: Harness[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const harness of harnesses.splice(0)) harness.cleanup();
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

const CREDENTIAL_KEYS = ["TIMI_API_KEY", "TAI_PAT_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"] as const;

/** Mask every credential-bearing input the real CLI spawn could reach. */
async function withIsolatedHome<T>(fn: () => Promise<T> | T): Promise<T> {
	const home = mkdtemp("mw-dc-home-");
	const saved = new Map<string, string | undefined>();
	for (const key of ["HOME", "USERPROFILE", "PI_CODING_AGENT_DIR", "MW_PY", ...CREDENTIAL_KEYS]) {
		saved.set(key, process.env[key]);
	}
	process.env.HOME = home;
	process.env.USERPROFILE = home;
	process.env.PI_CODING_AGENT_DIR = path.join(home, "agent");
	delete process.env.MW_PY;
	for (const key of CREDENTIAL_KEYS) delete process.env[key];
	try {
		return await fn();
	} finally {
		for (const [key, value] of saved) {
			if (value === undefined) delete process.env[key];
			else process.env[key] = value;
		}
	}
}

async function createCommandHarness(
	root: string,
	mode: "tui" | "rpc" | "print" | "json" = "tui",
): Promise<{
	harness: Harness;
	notifications: Notify[];
	confirmations: ConfirmCall[];
}> {
	const notifications: Notify[] = [];
	const confirmations: ConfirmCall[] = [];
	const harness = await createHarness({
		extensionFactories: [
			(pi: ExtensionAPI) => {
				registerMwCommands(pi, root, new WorkerStore(root), {} as AckStore, { key: undefined }, root);
			},
		],
	});
	const ui = {
		notify: (message: string, type?: string) => {
			notifications.push({ message, type: type ?? "info" });
		},
		confirm: async (title: string, message: string) => {
			confirmations.push({ title, message });
			return false;
		},
		select: async () => undefined,
		input: async () => undefined,
	} as unknown as ExtensionUIContext;
	await harness.session.bindExtensions({ uiContext: ui, mode });
	harnesses.push(harness);
	return { harness, notifications, confirmations };
}

describe("/mw decide controls at the real registered entry (harness + faux)", () => {
	it("a cancelled `on` reaches no Python write and consumes no model turn", async () => {
		const root = mkdtemp("mw-dc-on-");
		const { harness, notifications, confirmations } = await createCommandHarness(root);

		await withIsolatedHome(() => harness.session.prompt("/mw decide on"));

		expect(confirmations).toHaveLength(1);
		expect(confirmations[0]?.title).toContain("/mw decide on");
		const text = notifications.at(-1)?.message ?? "";
		expect(text).toContain("未获得明确确认");
		expect(text).not.toContain("enabled=true) CLI 原文");
		expect(notifications.at(-1)?.type).toBe("warning");
		// No config/authority file was created in the project root.
		expect(fs.existsSync(path.join(root, ".mw", "decide.json"))).toBe(false);
		expect(fs.existsSync(path.join(root, ".mw", "decide-points.json"))).toBe(false);
		expect(harness.session.messages).toEqual([]);
		expect(harness.eventsOfType("turn_start")).toHaveLength(0);
		verify("entry-on: confirm=1 write_files=0 provider_turns=0");
	});

	it("a cancelled `dp on <id>` pre-checks the registry but writes no authority", async () => {
		const root = mkdtemp("mw-dc-dp-");
		const { harness, notifications, confirmations } = await createCommandHarness(root);

		await withIsolatedHome(() => harness.session.prompt("/mw decide dp on dp-QG"));

		expect(confirmations).toHaveLength(1);
		expect(confirmations[0]?.message).toContain("dp-QG");
		const text = notifications.at(-1)?.message ?? "";
		expect(text).toContain("未获得明确确认");
		expect(text).not.toContain("CLI 原文");
		expect(notifications.at(-1)?.type).toBe("warning");
		expect(fs.existsSync(path.join(root, ".mw", "decide-points.json"))).toBe(false);
		expect(harness.session.messages).toEqual([]);
		verify("entry-dp-on: registry_precheck=1 confirm=1 write_files=0 provider_turns=0");
	});

	it("legacy read-only forward, usage line and headless text still work", async () => {
		const root = mkdtemp("mw-dc-legacy-");
		const { harness, notifications } = await createCommandHarness(root);

		await withIsolatedHome(() => harness.session.prompt("/mw decide dp list"));
		const listText = notifications.at(-1)?.message ?? "";
		expect(listText).toContain("decision point(s)");
		expect(listText).not.toContain("unknown sub");

		await harness.session.prompt("/mw bogus");
		const usage = notifications.at(-1)?.message ?? "";
		expect(usage).toContain("decide on|off|probe");
		expect(usage).toContain("decide dp on|off <id>");
		expect(usage).toContain("decide dp list|show <id>|export");
		expect(usage).toContain("decide monitor");

		// Headless `/mw decide` still puts the returned text into the transcript.
		const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
		const summaries: string[] = [];
		const pi = {
			registerCommand: (
				name: string,
				def: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
			) => {
				commands.set(name, def.handler);
			},
			sendMessage: (message: { content: string }) => {
				summaries.push(message.content);
			},
		} as unknown as ExtensionAPI;
		registerMwCommands(pi, root, new WorkerStore(root), {} as AckStore, { key: undefined }, root);
		const handler = commands.get("mw");
		if (!handler) throw new Error("/mw command not registered");
		const headless = {
			hasUI: false,
			ui: {
				notify: () => undefined,
				confirm: async () => false,
				select: async () => undefined,
				input: async () => undefined,
			},
		} as unknown as ExtensionCommandContext;
		await handler("decide bogus", headless);
		expect(summaries.at(-1)).toContain("unknown sub 'bogus'");
		expect(harness.session.messages).toEqual([]);
		expect(harness.eventsOfType("turn_start")).toHaveLength(0);
		verify("entry-legacy: dp_list=ok usage_new_faces=1 headless_summary=1 provider_turns=0");
	});

	it("a non-TUI (rpc) entry is refused before any confirm or runner, with zero writes", async () => {
		const root = mkdtemp("mw-dc-rpc-");
		// RPC still has hasUI=true (a bound uiContext) and executes slash commands,
		// but mode=rpc is not the human TUI window: the new-control gate must reject
		// before the confirm dialog and before the real CLI spawn.
		const { harness, notifications, confirmations } = await createCommandHarness(root, "rpc");

		await withIsolatedHome(() => harness.session.prompt("/mw decide on"));

		expect(confirmations).toHaveLength(0);
		const text = notifications.at(-1)?.message ?? "";
		expect(text).toContain("mode=tui");
		expect(text).toContain("拒绝");
		expect(text).not.toContain("enabled=true) CLI 原文");
		expect(notifications.at(-1)?.type).toBe("warning");
		expect(fs.existsSync(path.join(root, ".mw", "decide.json"))).toBe(false);
		expect(harness.session.messages).toEqual([]);
		expect(harness.eventsOfType("turn_start")).toHaveLength(0);
		verify("entry-rpc: mode_gate=1 confirm=0 write_files=0 provider_turns=0");
	});
});
