/**
 * run-detached surface tests (mw-console-storm-hardening W-03b, design D-005,
 * AC-008 / VC-008). shared/run-detached.ts is the single source of the
 * handoff contract and the spawn; this file proves:
 *   - both activation paths register `mw_run_detached` (pmActivate +
 *     workerModeActivate against fake ExtensionAPIs),
 *   - the worker-side shell-only gate: shell roles get the tool, read-only
 *     roles don't (activeToolsForType),
 *   - the TypeBox schema rejects an empty `cmd` and unknown keys,
 *   - option flags reach `runDetachedMw`'s spawn argv verbatim,
 *   - the `/mw run-detached` command branch exists and goes through
 *     `runDetachedMw` (injectable runner seam, the rag precedent).
 *
 * Self-contained (faux provider, no real CLI/network): `node:child_process`
 * is mocked, so no python is spawned and nothing touches the network.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Check } from "typebox/value";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ToolDefinition } from "../../src/core/extensions/types.ts";
import { pmActivate } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	MW_COMMAND_DESCRIPTION,
	parseRunDetachedArgs,
	registerMwCommands,
	runMwRunDetachedCommand,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { PYTHON_EXE } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import {
	MW_RUN_DETACHED_TOOL,
	type RunDetachedResult,
	registerRunDetachedTool,
	runDetachedMw,
} from "../../src/extensions/agent-team-loop/shared/run-detached.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { activeToolsForType, workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const childMocks = vi.hoisted(() => ({
	spawn: vi.fn(),
	spawnSync: vi.fn(),
}));

vi.mock("node:child_process", () => ({
	spawn: childMocks.spawn,
	spawnSync: childMocks.spawnSync,
}));

// The worker runtime registers a process-exit hook per activation; this file
// activates a worker once, but a leaked listener set is still noise.
process.setMaxListeners(50);

/** A valid `mw run-detached` handoff as printed by the foreground CLI. */
const HANDOFF_STDOUT = [
	"[mw run-detached] pid=4242",
	"marker=/run/marker.json",
	"heartbeat=/run/heartbeat.json",
	"log=/run/run.log",
	"",
].join("\n");

const temporaryDirs: string[] = [];
const savedEnv = new Map<string, string | undefined>();

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	temporaryDirs.push(dir);
	return dir;
}

function setEnv(name: string, value: string | undefined): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	if (value === undefined) delete process.env[name];
	else process.env[name] = value;
}

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
	childMocks.spawn.mockReset();
	childMocks.spawnSync.mockReset();
});

/** Fake pi collecting tool registrations, command handlers and event handlers. */
function fakePi(): {
	pi: ExtensionAPI;
	tools: Map<string, ToolDefinition>;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
	handlers: Map<string, Array<(event?: unknown, ctx?: unknown) => unknown>>;
} {
	const tools = new Map<string, ToolDefinition>();
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const handlers = new Map<string, Array<(event?: unknown, ctx?: unknown) => unknown>>();
	const pi = {
		registerTool: (tool: ToolDefinition) => {
			tools.set(tool.name, tool);
		},
		registerCommand: (
			name: string,
			opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, opts.handler);
		},
		on: (name: string, handler: (event?: unknown, ctx?: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(handler);
			handlers.set(name, list);
		},
		appendEntry: () => {},
		sendUserMessage: () => {},
		sendMessage: () => {},
		setActiveTools: () => {},
	} as unknown as ExtensionAPI;
	return { pi, tools, commands, handlers };
}

function fakeCmdCtx(): { ctx: ExtensionCommandContext; notifications: Array<{ message: string; level: string }> } {
	const notifications: Array<{ message: string; level: string }> = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string, level: string) => {
				notifications.push({ message, level });
			},
			setWidget: () => {},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

// ── worker-side shell-only gate (activeToolsForType) ────────────────────────

describe("mw_run_detached shell-only gate (D-005)", () => {
	it("shell roles (coding/research) carry the tool; read-only roles (review) do not", () => {
		expect(activeToolsForType("coding")).toContain(MW_RUN_DETACHED_TOOL);
		expect(activeToolsForType("research")).toContain(MW_RUN_DETACHED_TOOL);
		expect(activeToolsForType("review")).not.toContain(MW_RUN_DETACHED_TOOL);
		expect(activeToolsForType("verifier")).not.toContain(MW_RUN_DETACHED_TOOL);
	});
});

// ── dual-path registration (pmActivate + workerModeActivate) ─────────────────

describe("dual-path registration (D-005 AC-008)", () => {
	it("pmActivate registers mw_run_detached", () => {
		const root = mkdtemp("atl-run-detached-pm-");
		fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
		const cwd = process.cwd();
		process.chdir(root);
		try {
			const { pi, tools, handlers } = fakePi();
			pmActivate(pi);
			expect(tools.has(MW_RUN_DETACHED_TOOL)).toBe(true);
			// Teardown: the worker poll loop is a live interval — clear it so no
			// timer leaks past this test (the lifecycle precedent).
			for (const cb of handlers.get("session_shutdown") ?? []) cb({}, undefined);
		} finally {
			process.chdir(cwd);
		}
	});

	it("workerModeActivate registers mw_run_detached", async () => {
		const root = mkdtemp("atl-run-detached-worker-");
		const taskDir = path.join(root, "key-a", "workers", "t-1");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\ntimeout: 2\n\nwork\n", "utf8");
		setEnv("PI_WORKER_TASK", path.join(taskDir, "task.md"));
		const { pi, tools } = fakePi();
		await workerModeActivate(pi as unknown as ExtensionAPI);
		expect(tools.has(MW_RUN_DETACHED_TOOL)).toBe(true);
	});
});

// ── TypeBox schema (empty cmd / unknown keys rejected) ──────────────────────

describe("mw_run_detached schema (D-005)", () => {
	it("rejects an empty cmd array and unknown keys (additionalProperties: false)", () => {
		const root = mkdtemp("atl-run-detached-schema-");
		const { pi, tools } = fakePi();
		registerRunDetachedTool(pi, root);
		const tool = tools.get(MW_RUN_DETACHED_TOOL);
		if (!tool) throw new Error("mw_run_detached not registered");
		expect(Check(tool.parameters, { cmd: [] })).toBe(false);
		expect(Check(tool.parameters, { cmd: ["ls", "-la"], bogus: 1 })).toBe(false);
		expect(Check(tool.parameters, { cmd: ["ls", "-la"] })).toBe(true);
		// F2b: duration options carry a strictly-positive lower bound; sub-unit
		// decimals stay legal (VC-004a/b semantics).
		expect(Check(tool.parameters, { cmd: ["ls"], timeout_min: -1 })).toBe(false);
		expect(Check(tool.parameters, { cmd: ["ls"], timeout_min: 0 })).toBe(false);
		expect(Check(tool.parameters, { cmd: ["ls"], heartbeat_s: -0.5 })).toBe(false);
		expect(Check(tool.parameters, { cmd: ["ls"], heartbeat_s: 0 })).toBe(false);
		expect(Check(tool.parameters, { cmd: ["ls"], timeout_min: 0.05, heartbeat_s: 0.5 })).toBe(true);
	});
});

// ── option passthrough to the spawn argv ────────────────────────────────────

describe("runDetachedMw argv passthrough (D-005)", () => {
	it("forwards cwd/run_dir/timeout_min/heartbeat_s and the verbatim cmd after '--'", () => {
		const root = mkdtemp("atl-run-detached-argv-");
		const mwPy = path.join(root, "mw.py");
		fs.writeFileSync(mwPy, "# fake mw.py\n", "utf8");
		setEnv("MW_PY", mwPy);
		childMocks.spawnSync.mockImplementation(() => ({
			status: 0,
			stdout: HANDOFF_STDOUT,
			stderr: "",
			error: undefined,
		}));

		const result = runDetachedMw({
			cmd: ["python", "-m", "http.server", "8080"],
			cwd: "D:/proj",
			run_dir: "D:/proj/.mw/runs/run-1",
			timeout_min: 5,
			heartbeat_s: 2,
		});

		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.handle).toEqual({
			pid: 4242,
			marker: "/run/marker.json",
			heartbeat: "/run/heartbeat.json",
			log: "/run/run.log",
		});
		expect(childMocks.spawnSync).toHaveBeenCalledTimes(1);
		// F3: exact element-wise argv equality — the flags and the verbatim
		// segment after `--` are all pinned; the old toContain shape did not.
		const [pythonExe, args] = childMocks.spawnSync.mock.calls[0] as [string, string[]];
		expect(pythonExe).toBe(PYTHON_EXE);
		expect(args).toEqual([
			mwPy,
			"run-detached",
			"--cwd=D:/proj",
			"--run-dir=D:/proj/.mw/runs/run-1",
			"--timeout-min=5",
			"--heartbeat-s=2",
			"--",
			"python",
			"-m",
			"http.server",
			"8080",
		]);
	});

	it("fails open with a structured error when no command is given (no spawn)", () => {
		childMocks.spawnSync.mockClear();
		const result = runDetachedMw({ cmd: [] });
		expect(result.ok).toBe(false);
		if (result.ok) return;
		expect(result.error).toContain("no command");
		// F2b runtime half: non-positive durations fail structurally and never spawn.
		const negTimeout = runDetachedMw({ cmd: ["ls"], timeout_min: -1 });
		expect(negTimeout.ok).toBe(false);
		if (!negTimeout.ok) expect(negTimeout.error).toContain("timeout_min must be > 0");
		const zeroHeartbeat = runDetachedMw({ cmd: ["ls"], heartbeat_s: 0 });
		expect(zeroHeartbeat.ok).toBe(false);
		if (!zeroHeartbeat.ok) expect(zeroHeartbeat.error).toContain("heartbeat_s must be > 0");
		expect(childMocks.spawnSync).not.toHaveBeenCalled();
	});
});

// ── /mw run-detached command branch ─────────────────────────────────────────

describe("/mw run-detached command branch (D-005)", () => {
	it("parseRunDetachedArgs parses flags and keeps the argv after '--' verbatim", () => {
		const parsed = parseRunDetachedArgs(
			'--cwd "D:/my proj" --run-dir D:/proj/.mw/runs/run-1 --timeout-min 5 --heartbeat-s=2 -- python -m http.server 8080',
		);
		expect(parsed.ok).toBe(true);
		if (!parsed.ok) return;
		expect(parsed.flags.cwd).toBe("D:/my proj");
		expect(parsed.flags.run_dir).toBe("D:/proj/.mw/runs/run-1");
		expect(parsed.flags.timeout_min).toBe(5);
		expect(parsed.flags.heartbeat_s).toBe(2);
		expect(parsed.flags.cmd).toEqual(["python", "-m", "http.server", "8080"]);
	});

	it("rejects a missing '--', an empty command, unknown options and bad numbers", () => {
		expect(parseRunDetachedArgs("ls -la").ok).toBe(false);
		expect(parseRunDetachedArgs("-- ").ok).toBe(false);
		expect(parseRunDetachedArgs("--bogus x -- ls").ok).toBe(false);
		expect(parseRunDetachedArgs("--timeout-min abc -- ls").ok).toBe(false);
		expect(parseRunDetachedArgs("--cwd -- ls").ok).toBe(false);
	});

	it("runMwRunDetachedCommand calls runDetachedMw (runner seam) and renders the 4-field summary", async () => {
		const { ctx, notifications } = fakeCmdCtx();
		const seen: Array<{ opts: Parameters<typeof runDetachedMw>[0] }> = [];
		const runner = (opts: Parameters<typeof runDetachedMw>[0]): RunDetachedResult => {
			seen.push({ opts });
			return {
				ok: true,
				handle: { pid: 7, marker: "/m.json", heartbeat: "/h.json", log: "/l.log" },
			};
		};
		await runMwRunDetachedCommand(ctx, "D:/proj", "--timeout-min 9 -- node build.mjs", runner);
		expect(seen).toHaveLength(1);
		expect(seen[0]?.opts.cmd).toEqual(["node", "build.mjs"]);
		expect(seen[0]?.opts.timeout_min).toBe(9);
		// cwd defaults to the project dir, mirroring the tool's controlRoot.
		expect(seen[0]?.opts.cwd).toBe("D:/proj");
		expect(notifications).toEqual([
			{ message: "dispatched pid=7 marker=/m.json heartbeat=/h.json log=/l.log", level: "info" },
		]);
	});

	it("runMwRunDetachedCommand notifies a structured error without throwing", async () => {
		const { ctx, notifications } = fakeCmdCtx();
		const runner = (): RunDetachedResult => ({ ok: false, error: "boom: no mw.py" });
		await runMwRunDetachedCommand(ctx, "D:/proj", "-- echo hi", runner);
		expect(notifications).toEqual([{ message: "boom: no mw.py", level: "error" }]);
	});

	it("the registered /mw handler wires run-detached through runDetachedMw end to end", async () => {
		const root = mkdtemp("atl-run-detached-cmd-");
		const mwPy = path.join(root, "mw.py");
		fs.writeFileSync(mwPy, "# fake mw.py\n", "utf8");
		setEnv("MW_PY", mwPy);
		childMocks.spawnSync.mockImplementation(() => ({
			status: 0,
			stdout: HANDOFF_STDOUT,
			stderr: "",
			error: undefined,
		}));

		const { pi, commands } = fakePi();
		registerMwCommands(pi, root, new WorkerStore(root), new AckStore(root), { key: undefined }, root);
		const handler = commands.get("mw");
		if (!handler) throw new Error("/mw not registered");
		const { ctx, notifications } = fakeCmdCtx();
		await handler("run-detached --timeout-min 3 -- python serve.py", ctx);

		expect(childMocks.spawnSync).toHaveBeenCalledTimes(1);
		const [_python, args] = childMocks.spawnSync.mock.calls[0] as [string, string[]];
		expect(args).toContain("--timeout-min=3");
		expect(args.slice(args.indexOf("--") + 1)).toEqual(["python", "serve.py"]);
		expect(notifications).toEqual([
			{
				message: "dispatched pid=4242 marker=/run/marker.json heartbeat=/run/heartbeat.json log=/run/run.log",
				level: "info",
			},
		]);
	});

	it("USAGE documents the run-detached subcommand", async () => {
		expect(MW_COMMAND_DESCRIPTION).toContain("run-detached");
		const { pi, commands } = fakePi();
		const root = mkdtemp("atl-run-detached-usage-");
		registerMwCommands(pi, root, new WorkerStore(root), new AckStore(root), { key: undefined }, root);
		const handler = commands.get("mw");
		if (!handler) throw new Error("/mw not registered");
		const { ctx, notifications } = fakeCmdCtx();
		await handler("bogus-sub", ctx);
		expect(notifications.some((n) => n.message.includes("run-detached"))).toBe(true);
	});

	it("VC-008: dual-path registration + shell gate + argv passthrough hold together", () => {
		const pmRoot = mkdtemp("atl-run-detached-vc-");
		fs.mkdirSync(path.join(pmRoot, ".agenticdoc"), { recursive: true });
		const cwd = process.cwd();
		process.chdir(pmRoot);
		let pmRegistered = false;
		try {
			const { pi, tools, handlers } = fakePi();
			pmActivate(pi);
			pmRegistered = tools.has(MW_RUN_DETACHED_TOOL);
			for (const cb of handlers.get("session_shutdown") ?? []) cb({}, undefined);
		} finally {
			process.chdir(cwd);
		}
		const shellOk = activeToolsForType("coding").includes(MW_RUN_DETACHED_TOOL);
		const readOnlyOk = !activeToolsForType("review").includes(MW_RUN_DETACHED_TOOL);

		// F3: a real spawn + full argv comparison replaces the old
		// `some(() => false)` form, whose printed value was always true.
		const vcRoot = mkdtemp("atl-run-detached-vc-argv-");
		const vcMwPy = path.join(vcRoot, "mw.py");
		fs.writeFileSync(vcMwPy, "# fake mw.py\n", "utf8");
		setEnv("MW_PY", vcMwPy);
		childMocks.spawnSync.mockImplementation(() => ({
			status: 0,
			stdout: HANDOFF_STDOUT,
			stderr: "",
			error: undefined,
		}));
		const run = runDetachedMw({
			cmd: ["node", "--", "build.mjs"],
			cwd: "D:/p",
			run_dir: "D:/p/.mw/runs/run-vc",
			timeout_min: 1,
			heartbeat_s: 0.5,
		});
		const seenArgv = (childMocks.spawnSync.mock.calls[0] as [string, string[]] | undefined)?.[1];
		const expectedArgv = [
			vcMwPy,
			"run-detached",
			"--cwd=D:/p",
			"--run-dir=D:/p/.mw/runs/run-vc",
			"--timeout-min=1",
			"--heartbeat-s=0.5",
			"--",
			"node",
			"--",
			"build.mjs",
		];
		const argvPassthrough = run.ok && JSON.stringify(seenArgv) === JSON.stringify(expectedArgv);
		expect(argvPassthrough).toBe(true);

		process.stdout.write(
			`[VERIFY] VC-008: pm_registered=${String(pmRegistered)} shell_ok=${String(shellOk)} readonly_no_tool=${String(readOnlyOk)} argv_passthrough=${String(argvPassthrough)}\n`,
		);
	});
});
