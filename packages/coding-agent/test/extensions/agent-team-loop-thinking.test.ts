/**
 * `/mw thinking` window surface (mw-worker-thinking-command T-02 / AC-005 / VC-005).
 *
 * Proves the REAL registered `mw` handler forwards a strict argv to the Python
 * CLI at the control root, with `node:child_process` mocked so no python is
 * ever spawned and no config/API/worker is touched. Also covers the injectable
 * runner seam on runMwThinkingCommand directly. Python stays the single source
 * of YAML semantics — these tests only assert the window's validation/forwarding.
 *
 * Self-contained and offline (faux pi / command ctx, no network, no model).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import { runMwThinkingCommand } from "../../src/extensions/agent-team-loop/pm/thinking-command.ts";
import { MW_COMMAND_DESCRIPTION, registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { type MwCliResult, PYTHON_EXE } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";

type ThinkingRunner = (projectDir: string, args: string[]) => MwCliResult;

const childMocks = vi.hoisted(() => ({
	spawn: vi.fn(),
	spawnSync: vi.fn(),
}));

vi.mock("node:child_process", () => ({
	spawn: childMocks.spawn,
	spawnSync: childMocks.spawnSync,
}));

const temporaryDirs: string[] = [];
const savedEnv = new Map<string, string | undefined>();

/** A control root whose path contains a space — proves the argv is passed as a
 * single array element, never shell-split (the `--project=...` tail too). */
function setupProject(): { root: string; mwPy: string } {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "atl-thinking root-"));
	temporaryDirs.push(root);
	const mwPy = path.join(root, "mw.py");
	fs.writeFileSync(mwPy, "# fake mw.py\n", "utf8");
	setEnv("MW_PY", mwPy);
	return { root, mwPy };
}

function setEnv(name: string, value: string | undefined): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	if (value === undefined) delete process.env[name];
	else process.env[name] = value;
}

function setSpawn(result: { status?: number | null; stdout?: string; stderr?: string; error?: Error }): void {
	childMocks.spawnSync.mockImplementation(() => ({
		status: result.status === undefined ? 0 : result.status,
		stdout: result.stdout ?? "",
		stderr: result.stderr ?? "",
		error: result.error,
	}));
}

function fakePi(): {
	pi: ExtensionAPI;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
	descriptions: Map<string, string>;
} {
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const descriptions = new Map<string, string>();
	const pi = {
		registerCommand: (
			name: string,
			opts: { description?: string; handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, opts.handler);
			if (opts.description) descriptions.set(name, opts.description);
		},
	} as unknown as ExtensionAPI;
	return { pi, commands, descriptions };
}

function fakeCmdCtx(): { ctx: ExtensionCommandContext; notifications: Array<{ message: string; level: string }> } {
	const notifications: Array<{ message: string; level: string }> = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string, level: string) => {
				notifications.push({ message, level });
			},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

/** Register the real /mw command and return its handler. */
function register(root: string): {
	handler: (args: string, ctx: ExtensionCommandContext) => Promise<void>;
	descriptions: Map<string, string>;
} {
	const { pi, commands, descriptions } = fakePi();
	registerMwCommands(pi, root, {} as never, {} as never, {} as never, path.join(root, ".agenticdoc"));
	const handler = commands.get("mw");
	if (!handler) throw new Error("/mw not registered");
	return { handler, descriptions };
}

beforeEach(() => {
	childMocks.spawn.mockReset();
	childMocks.spawnSync.mockReset();
	childMocks.spawn.mockImplementation(() => ({ unref: () => {} }));
	setSpawn({});
});

afterEach(() => {
	while (temporaryDirs.length > 0) {
		const dir = temporaryDirs.pop();
		if (dir) fs.rmSync(dir, { recursive: true, force: true });
	}
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
});

// ── Real registered handler: argv forwarding (AC-005 / VC-005) ──────────────

interface LegalCase {
	label: string;
	sub: string;
	argv: string[];
	mutate: boolean;
}

const LEGAL: LegalCase[] = [
	{ label: "bare thinking = show", sub: "", argv: ["show"], mutate: false },
	{ label: "explicit show", sub: "show", argv: ["show"], mutate: false },
	{ label: "set coding high", sub: "set coding high", argv: ["set", "coding", "high"], mutate: true },
	{ label: "set default off", sub: "set default off", argv: ["set", "default", "off"], mutate: true },
	{
		label: "set decide_prepare xhigh",
		sub: "set decide_prepare xhigh",
		argv: ["set", "decide_prepare", "xhigh"],
		mutate: true,
	},
	{ label: "set vision max", sub: "set vision max", argv: ["set", "vision", "max"], mutate: true },
	{ label: "set research minimal", sub: "set research minimal", argv: ["set", "research", "minimal"], mutate: true },
	{ label: "set review low", sub: "set review low", argv: ["set", "review", "low"], mutate: true },
	{ label: "clear review", sub: "clear review", argv: ["clear", "review"], mutate: true },
	{ label: "clear default", sub: "clear default", argv: ["clear", "default"], mutate: true },
	{ label: "clear all", sub: "clear all", argv: ["clear", "all"], mutate: true },
	{
		label: "extra internal whitespace",
		sub: "  set   coding   medium  ",
		argv: ["set", "coding", "medium"],
		mutate: true,
	},
];

describe("real /mw thinking handler — argv forwarding", () => {
	for (const tc of LEGAL) {
		it(`legal: ${tc.label}`, async () => {
			const { root, mwPy } = setupProject();
			setSpawn({ status: 0, stdout: "thinking: ok" });
			const { handler } = register(root);
			const { ctx, notifications } = fakeCmdCtx();
			const cmd = tc.sub === "" ? "thinking" : `thinking ${tc.sub}`;
			await handler(cmd, ctx);

			expect(childMocks.spawnSync).toHaveBeenCalledTimes(1);
			const call = childMocks.spawnSync.mock.calls[0] as [string, string[], Record<string, unknown>];
			expect(call[0]).toBe(PYTHON_EXE);
			// command=thinking, projectDir is the control root, every argv item exact.
			expect(call[1]).toEqual([mwPy, "thinking", ...tc.argv, `--project=${root}`]);
			expect(call[1][1]).toBe("thinking");
			// argv is an array (not a shell string) and no shell option is used.
			expect(Array.isArray(call[1])).toBe(true);
			expect(call[2]).not.toHaveProperty("shell");

			// Success surfaces Python stdout; the next-spawn hint is mutate-only.
			expect(notifications).toHaveLength(1);
			expect(notifications[0].level).toBe("info");
			expect(notifications[0].message).toContain("thinking: ok");
			if (tc.mutate) {
				expect(notifications[0].message).toMatch(/next worker spawn/i);
			} else {
				// show is read-only: no config write, no mutate reminder.
				expect(notifications[0].message).not.toMatch(/next worker spawn/i);
			}
		});
	}
});

// ── Real registered handler: illegal args start zero subprocesses ───────────

const ILLEGAL: string[] = [
	"bogus", // unknown action
	"show extra", // show takes no trailing token
	"show coding",
	"set", // missing target + level
	"set coding", // missing level
	"set coding high extra", // extra token
	"set main high", // main is not a thinking role
	"set c high", // role alias
	"set bogus high", // unknown role
	"set coding turbo", // unknown level
	"set coding HIGH", // uppercase -> illegal token
	"set all high", // `all` only valid for clear
	"set coding 5", // digit -> illegal token
	"clear", // missing target
	"clear all extra", // extra token
	"clear main", // main
	"clear bogus", // unknown target
	'set coding "high"', // quotes
	"set coding 'high", // unpaired quote
	"set coding high;", // shell metacharacter
	"set coding high && whoami", // command injection
	"set DEFAULT high", // uppercase
];

describe("real /mw thinking handler — illegal input has zero subprocess side effects", () => {
	for (const sub of ILLEGAL) {
		it(`rejects '${sub}'`, async () => {
			const { root } = setupProject();
			setSpawn({ status: 0, stdout: "should never run" });
			const { handler } = register(root);
			const { ctx, notifications } = fakeCmdCtx();
			await handler(`thinking ${sub}`, ctx);

			expect(childMocks.spawnSync).not.toHaveBeenCalled();
			expect(notifications).toHaveLength(1);
			expect(notifications[0].level).toBe("warning");
			expect(notifications[0].message).toContain("thinking");
		});
	}
});

// ── Real registered handler: error paths + help ─────────────────────────────

describe("real /mw thinking handler — error paths and help", () => {
	it("nonzero Python exit / stderr notifies error", async () => {
		const { root } = setupProject();
		setSpawn({ status: 2, stdout: "", stderr: "error: bad thinking config" });
		const { handler } = register(root);
		const { ctx, notifications } = fakeCmdCtx();
		await handler("thinking set coding high", ctx);
		expect(childMocks.spawnSync).toHaveBeenCalledTimes(1);
		expect(notifications).toHaveLength(1);
		expect(notifications[0].level).toBe("error");
		expect(notifications[0].message).toContain("bad thinking config");
	});

	it("spawn failure (result.error) notifies error", async () => {
		const { root } = setupProject();
		setSpawn({ error: new Error("spawn ENOENT") });
		const { handler } = register(root);
		const { ctx, notifications } = fakeCmdCtx();
		await handler("thinking show", ctx);
		expect(notifications).toHaveLength(1);
		expect(notifications[0].level).toBe("error");
		expect(notifications[0].message).toMatch(/Failed to spawn|ENOENT/);
	});

	it("a throwing subprocess notifies error without rejecting the handler", async () => {
		const { root } = setupProject();
		childMocks.spawnSync.mockImplementation(() => {
			throw new Error("sync boom");
		});
		const { handler } = register(root);
		const { ctx, notifications } = fakeCmdCtx();
		await expect(handler("thinking clear all", ctx)).resolves.toBeUndefined();
		expect(notifications).toHaveLength(1);
		expect(notifications[0].level).toBe("error");
		expect(notifications[0].message).toContain("sync boom");
	});

	it("help (description + usage) mentions thinking", async () => {
		expect(MW_COMMAND_DESCRIPTION).toContain("thinking");
		const { root } = setupProject();
		const { handler, descriptions } = register(root);
		expect(descriptions.get("mw")).toContain("thinking");
		const { ctx, notifications } = fakeCmdCtx();
		await handler("bogus-sub", ctx);
		expect(notifications.some((n) => n.message.includes("thinking"))).toBe(true);
	});
});

// ── Injectable runner seam (helper-level) ───────────────────────────────────

describe("runMwThinkingCommand runner seam", () => {
	const projectDir = "D:/control root";

	it("forwards exact args and projectDir to the injected runner", async () => {
		const runner = vi.fn<ThinkingRunner>(() => ({ ok: true, output: "ok" }));
		const { ctx, notifications } = fakeCmdCtx();
		await runMwThinkingCommand(ctx, projectDir, "set coding high", runner);
		expect(runner).toHaveBeenCalledWith(projectDir, ["set", "coding", "high"]);
		expect(notifications[0].level).toBe("info");
		expect(notifications[0].message).toMatch(/next worker spawn/i);
	});

	it("bare and explicit show map to the read-only show argv", async () => {
		const runner = vi.fn<ThinkingRunner>(() => ({ ok: true, output: "shown" }));
		const { ctx } = fakeCmdCtx();
		await runMwThinkingCommand(ctx, projectDir, "", runner);
		await runMwThinkingCommand(ctx, projectDir, "show", runner);
		expect(runner.mock.calls).toEqual([
			[projectDir, ["show"]],
			[projectDir, ["show"]],
		]);
	});

	it("illegal input never calls the injected runner", async () => {
		const runner = vi.fn<ThinkingRunner>(() => ({ ok: true, output: "" }));
		const { ctx, notifications } = fakeCmdCtx();
		await runMwThinkingCommand(ctx, projectDir, "set main high", runner);
		await runMwThinkingCommand(ctx, projectDir, "clear all extra", runner);
		await runMwThinkingCommand(ctx, projectDir, "set coding 'high", runner);
		expect(runner).not.toHaveBeenCalled();
		expect(notifications).toHaveLength(3);
		expect(notifications.every((n) => n.level === "warning")).toBe(true);
	});

	it("injected runner returning non-ok notifies error", async () => {
		const runner = vi.fn<ThinkingRunner>(() => ({ ok: false, error: "disk full" }));
		const { ctx, notifications } = fakeCmdCtx();
		await runMwThinkingCommand(ctx, projectDir, "clear default", runner);
		expect(notifications).toEqual([{ message: "mw thinking clear failed: disk full", level: "error" }]);
	});

	it("injected runner throwing notifies error without rejecting", async () => {
		const runner = vi.fn<ThinkingRunner>(() => {
			throw new Error("runner boom");
		});
		const { ctx, notifications } = fakeCmdCtx();
		await expect(runMwThinkingCommand(ctx, projectDir, "set review low", runner)).resolves.toBeUndefined();
		expect(notifications).toHaveLength(1);
		expect(notifications[0].level).toBe("error");
		expect(notifications[0].message).toContain("runner boom");
	});
});
