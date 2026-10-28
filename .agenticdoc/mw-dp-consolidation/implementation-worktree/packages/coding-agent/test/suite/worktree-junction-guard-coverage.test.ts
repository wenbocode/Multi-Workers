/**
 * worktree-junction-guard-coverage.test.ts — W-06 (mw-worktree-junction-guard,
 * G1 AC-001/002/003/004).
 *
 * W-05's suite pinned the pure decision pipeline (`decideWorktreeRemove`). The
 * P-002 failure mode this card closes is exactly the one that pure assertions
 * cannot see: the decision function stays green while the registration in
 * `extensions/agent-team-loop/index.ts` breaks (the guard silently stops
 * existing in a real window). So this file carries two layers:
 *
 *   1. pure matcher assertions on `decideWorktreeRemove` over %TEMP% fixtures,
 *      and
 *   2. REAL `tool_call` dispatch through the production pipeline:
 *      faux provider → Agent loop → ExtensionRunner.emitToolCall → the handler
 *      registered by the REAL `activate(pi)` (never a direct
 *      `registerWorktreeJunctionGuard` call, which would stay green with the
 *      registration deleted) → `{block, reason}` → the tool body never runs.
 *      Only the bash backend is stubbed (`BashOperations` recorder), so the
 *      strongest evidence available is `executedBashCommands === []`: zero
 *      side effects, not merely an error result, and
 *
 *   3. AC-014 REAL `user_bash` dispatch (TUI `!`/`!!` + RPC `bash`): the same
 *      real registration, driven through `session.extensionRunner.emitUserBash`
 *      and the documented short-circuit (a returned `result` is used INSTEAD
 *      of executing — interactive-mode.ts `handleBashCommand`, rpc-mode.ts
 *      `bash`). The execution backend is a recorder once more, so an
 *      intercepted refusal shows `executed === []` while the clean reverse
 *      control shows `executed === [command]`.
 *
 * Fixtures live entirely under `%TEMP%` and every junction target is INSIDE the
 * fixture (never the real tree): `<root>/real/node_modules` (plain dir + a
 * file) is the link target, `<root>/wt/node_modules` is a `cmd /c mklink /J`
 * junction pointing at it (the 2026-10-09 accident shape), `<root>/clean` is a
 * plain directory without reparse points, and `<root>/task.md` is pointed to by
 * `PI_WORKER_TASK` so refusals land in the fixture's `trace.log`.
 *
 * Junctions are unlinked with `cmd /c rmdir` (no `/S`, no trailing separator)
 * before the fixture root is removed; every test also calls `harness.cleanup()`.
 */

import { Buffer } from "node:buffer";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ToolResultMessage } from "@earendil-works/pi-ai";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { BashOperations } from "../../src/core/tools/bash.ts";
import { createBashTool } from "../../src/core/tools/bash.ts";
import { createEditTool } from "../../src/core/tools/edit.ts";
import { createFindTool } from "../../src/core/tools/find.ts";
import { createGrepTool } from "../../src/core/tools/grep.ts";
import { createReadTool } from "../../src/core/tools/read.ts";
import { createWriteTool } from "../../src/core/tools/write.ts";
import { activate } from "../../src/extensions/agent-team-loop/index.ts";
import { decideWorktreeRemove } from "../../src/extensions/agent-team-loop/shared/worktree-junction-guard.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

/** Same key `index.ts` uses for its double-load flag; the harness boots a
 * fresh runtime per test, so it must be re-armed before each `activate`. */
const ACTIVATION_FLAG = "__agentTeamLoopActivated";
const ENV_WORKER_TASK = "PI_WORKER_TASK";

interface GuardFixture {
	/** Temp project root the guard anchors paths against. */
	root: string;
	/** <root>/real/node_modules — plain directory, junction target. */
	real: string;
	/** <root>/real/node_modules/<file> — proves the target tree is not empty. */
	realFile: string;
	/** <root>/wt — the worktree-shaped directory. */
	wt: string;
	/** <root>/wt/node_modules — the junction (reparse point). */
	link: string;
	/** <root>/clean — plain directory, reverse control. */
	clean: string;
	/** <root>/task.md — PI_WORKER_TASK target. */
	taskPath: string;
	/** <root>/trace.log — where the guard records refusals. */
	tracePath: string;
	readTrace(): string;
}

function createFixture(): GuardFixture {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "wjg-w06-"));
	const real = path.join(root, "real", "node_modules");
	const realFile = path.join(real, "fixture-dep.txt");
	const wt = path.join(root, "wt");
	const link = path.join(wt, "node_modules");
	const clean = path.join(root, "clean");
	const taskPath = path.join(root, "task.md");

	fs.mkdirSync(real, { recursive: true });
	fs.writeFileSync(realFile, "fixture dependency\n", "utf8");
	fs.mkdirSync(wt, { recursive: true });
	fs.mkdirSync(clean, { recursive: true });
	fs.writeFileSync(taskPath, "type: coding\n\nfixture worker task for the worktree junction guard\n", "utf8");

	const linked = spawnSync("cmd", ["/c", "mklink", "/J", link, real], { encoding: "utf8", windowsHide: true });
	if (linked.status !== 0) {
		throw new Error(`mklink /J ${link} ${real} failed (${linked.status}): ${linked.stderr}`);
	}

	const fixture: GuardFixture = {
		root,
		real,
		realFile,
		wt,
		link,
		clean,
		taskPath,
		tracePath: path.join(root, "trace.log"),
		readTrace(): string {
			try {
				return fs.readFileSync(this.tracePath, "utf8");
			} catch {
				return "";
			}
		},
	};
	fixtures.push(fixture);
	return fixture;
}

/** Unlink a junction WITHOUT `/S` and WITHOUT a trailing separator, so the
 * recursive delete that follows can never walk through the link. */
function unlinkJunction(link: string): void {
	spawnSync("cmd", ["/c", "rmdir", link], { encoding: "utf8", windowsHide: true });
}

const harnesses: Harness[] = [];
const fixtures: GuardFixture[] = [];
let savedWorkerTask: string | undefined;
let savedCwd = process.cwd();
/** Env var used by the AC-014 interpolation case (never set by the repo). */
const ENV_USER_BASH_TARGET = "WJG_W14_USER_BASH_WT";
let savedUserBashTarget: string | undefined;

async function createGuardHarness(
	fixture: GuardFixture,
	workerMode: boolean,
): Promise<{ harness: Harness; executedBashCommands: string[] }> {
	// PM-mode activation reads `process.cwd()` for its coordination root; move
	// it into the fixture so no real-repo `.agenticdoc` is touched.
	process.chdir(fixture.root);
	if (workerMode) {
		process.env[ENV_WORKER_TASK] = fixture.taskPath;
	} else {
		delete process.env[ENV_WORKER_TASK];
	}
	delete (globalThis as Record<string, unknown>)[ACTIVATION_FLAG];

	const executedBashCommands: string[] = [];
	const bashOperations: BashOperations = {
		exec: async (command, _cwd, options) => {
			executedBashCommands.push(command);
			options.onData(Buffer.from(`ran: ${command}`));
			return { exitCode: 0 };
		},
	};
	const harness = await createHarness({
		tools: [
			createReadTool(fixture.root),
			createWriteTool(fixture.root),
			createEditTool(fixture.root),
			createBashTool(fixture.root, { operations: bashOperations }),
			createFindTool(fixture.root),
			createGrepTool(fixture.root),
		],
		// REAL registration surface: only activate() proves the guard is wired.
		extensionFactories: [(pi) => activate(pi)],
	});
	harnesses.push(harness);
	return { harness, executedBashCommands };
}

function toolResults(harness: Harness, toolName: string): ToolResultMessage[] {
	return harness.session.messages.filter(
		(message): message is ToolResultMessage => message.role === "toolResult" && message.toolName === toolName,
	);
}

function worktreeGuardTraceLines(trace: string): string[] {
	return trace
		.split(/\r?\n/)
		.filter((line) => line.trim() !== "")
		.filter((line) => line.includes("[WORKTREE_GUARD]"));
}

function bashResult(harness: Harness, index: number): { isError: boolean | undefined; text: string } {
	const results = toolResults(harness, "bash");
	const result = results[index];
	return { isError: result?.isError, text: result ? getMessageText(result) : "" };
}

/** Shared teardown: dispose the harnesses, unlink each junction with
 * `cmd /c rmdir` (no `/S`, no trailing separator), then remove the fixture
 * root, and restore the worker-task env probe. */
function cleanupHarnessesAndFixtures(): void {
	while (harnesses.length > 0) {
		harnesses.pop()?.cleanup();
	}
	// Restore the cwd before deleting a fixture the process may sit inside.
	process.chdir(savedCwd);
	while (fixtures.length > 0) {
		const fixture = fixtures.pop();
		if (!fixture) continue;
		unlinkJunction(fixture.link);
		spawnSync("cmd", ["/c", "rmdir", "/S", "/Q", fixture.root], { encoding: "utf8", windowsHide: true });
		if (fs.existsSync(fixture.root)) fs.rmSync(fixture.root, { recursive: true, force: true });
	}
	if (savedWorkerTask === undefined) {
		delete process.env[ENV_WORKER_TASK];
	} else {
		process.env[ENV_WORKER_TASK] = savedWorkerTask;
	}
}

interface UserBashOutcome {
	/** True when the guard returned a full replacement (`eventResult.result`). */
	intercepted: boolean;
	/** Output the user would see (guard text when intercepted, else the run). */
	output: string;
	/** Commands that reached the execution backend. Empty proves zero side effects. */
	executed: string[];
}

/**
 * Mirror of the production `!`/`!!` call path, minus the TUI widget:
 * `handleBashCommand` (interactive-mode.ts) and the RPC `bash` command both
 * call `ExtensionRunner.emitUserBash`, then short-circuit ONLY on a returned
 * `eventResult.result` (used INSTEAD of executing), otherwise run the command
 * through `session.executeBash`. So dispatch here is the real runner + the
 * real registered handler, and the execution backend is stubbed with a
 * recorder: `executed === []` is the zero-side-effect evidence, and
 * `executed === [command]` is the reverse-control proof that a clean command
 * still runs.
 */
async function runUserBash(harness: Harness, command: string, excludeFromContext = false): Promise<UserBashOutcome> {
	const executed: string[] = [];
	const eventResult = await harness.session.extensionRunner.emitUserBash({
		type: "user_bash",
		command,
		excludeFromContext,
		cwd: harness.sessionManager.getCwd(),
	});
	if (eventResult?.result) {
		harness.session.recordBashResult(command, eventResult.result, { excludeFromContext });
		return { intercepted: true, output: eventResult.result.output, executed };
	}
	const result = await harness.session.executeBash(command, undefined, {
		excludeFromContext,
		operations: {
			exec: async (cmd, _cwd, options) => {
				executed.push(cmd);
				options.onData(Buffer.from(`ran: ${cmd}`));
				return { exitCode: 0 };
			},
		},
	});
	return { intercepted: false, output: result.output, executed };
}

describe("worktree junction guard decisions over %TEMP% fixtures (AC-001/002/003)", () => {
	it("blocks the accident shape and prescribes the copyable mw worktree rm", () => {
		const fixture = createFixture();
		const verdict = decideWorktreeRemove(`git worktree remove --force "${fixture.wt}"`, fixture.root, process.env);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(verdict.hits).toEqual([fixture.link]);
		expect(verdict.reason).toContain("reparse point");
		expect(verdict.reason).toContain(`mw worktree rm "${fixture.wt}"`);
	});

	it("allows the clean target (reverse control)", () => {
		const fixture = createFixture();
		const verdict = decideWorktreeRemove(`git worktree remove --force "${fixture.clean}"`, fixture.root, process.env);

		expect(verdict.block).toBe(false);
		expect(verdict.basis).toBe("resolved");
		expect(verdict.hits).toEqual([]);
	});

	it("blocks the penetrating rm form with the per-link rmdir prescription", () => {
		const fixture = createFixture();
		const verdict = decideWorktreeRemove(`rm -rf "${fixture.wt}/"`, fixture.root, process.env);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("delete-penetration");
		expect(verdict.hits).toEqual([fixture.link]);
		expect(verdict.reason).toContain(`cmd /c rmdir "${fixture.link}"`);
		expect(verdict.reason).not.toContain("mw worktree rm");
	});

	it("leaves read-only and unrelated commands uncovered", () => {
		const fixture = createFixture();
		for (const command of ["git worktree list", `ls "${fixture.wt}"`, `cat "${fixture.realFile}"`]) {
			const verdict = decideWorktreeRemove(command, fixture.root, process.env);
			expect(verdict.block, command).toBe(false);
			expect(verdict.basis, command).toBe("not-remove");
		}
	});
});

describe("worktree junction guard real tool_call dispatch via activate (AC-001/003/004)", () => {
	beforeEach(() => {
		savedWorkerTask = process.env[ENV_WORKER_TASK];
		savedCwd = process.cwd();
	});

	afterEach(() => {
		cleanupHarnessesAndFixtures();
	});

	it("AC-001/004 (worker mode): refuses the accident command, runs nothing, records the trace", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGuardHarness(fixture, true);
		const command = `git worktree remove --force "${fixture.wt}"`;
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("bash", { command })], { stopReason: "toolUse" }),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("remove the worktree");

		const results = toolResults(harness, "bash");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(true);
		const text = results[0] ? getMessageText(results[0]) : "";
		expect(text).toContain("[mw-worktree-guard] blocked");
		expect(text).toContain(`mw worktree rm "${fixture.wt}"`);
		// Strongest evidence: the bash backend never saw the command.
		expect(executedBashCommands).toEqual([]);
		// AC-004: the refusal is observable next to task.md.
		expect(worktreeGuardTraceLines(fixture.readTrace())).toHaveLength(1);
		expect(fixture.readTrace()).toContain("[WORKTREE_GUARD]");
		expect(fixture.readTrace()).toContain("blocked tool=bash");
	});

	it("AC-001 (interactive/PM mode, PI_WORKER_TASK unset): the same registration still refuses", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGuardHarness(fixture, false);
		const command = `git worktree remove --force "${fixture.wt}"`;
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("bash", { command })], { stopReason: "toolUse" }),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("remove the worktree");

		const results = toolResults(harness, "bash");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(true);
		expect(results[0] ? getMessageText(results[0]) : "").toContain("[mw-worktree-guard] blocked");
		expect(executedBashCommands).toEqual([]);
	});

	it("AC-002 extension: refuses the delete-penetration form with the rmdir prescription, runs nothing", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGuardHarness(fixture, true);
		const command = `rm -rf "${fixture.wt}/"`;
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("bash", { command })], { stopReason: "toolUse" }),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("delete the worktree contents");

		const results = toolResults(harness, "bash");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(true);
		const text = results[0] ? getMessageText(results[0]) : "";
		expect(text).toContain("穿透 reparse point");
		expect(text).toContain(`cmd /c rmdir "${fixture.link}"`);
		expect(executedBashCommands).toEqual([]);
		expect(worktreeGuardTraceLines(fixture.readTrace())).toHaveLength(1);
	});

	it("AC-003 (reverse control): a clean worktree removal passes and the tool actually executes", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGuardHarness(fixture, true);
		const command = `git worktree remove --force "${fixture.clean}"`;
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("bash", { command })], { stopReason: "toolUse" }),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("remove the clean worktree");

		const results = toolResults(harness, "bash");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(executedBashCommands).toEqual([command]);
		expect(worktreeGuardTraceLines(fixture.readTrace())).toHaveLength(0);
	});

	it("AC-003: read-only/unrelated bash is not intercepted and executes", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGuardHarness(fixture, true);
		const commands = ["git worktree list", `ls "${fixture.wt}"`, `cat "${fixture.realFile}"`];
		harness.setResponses([
			fauxAssistantMessage(
				commands.map((command) => fauxToolCall("bash", { command })),
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("inspect the worktree without deleting");

		const results = toolResults(harness, "bash");
		expect(results).toHaveLength(commands.length);
		for (const [index] of commands.entries()) {
			expect(bashResult(harness, index).isError, commands[index]).toBe(false);
		}
		expect(executedBashCommands).toEqual(commands);
		expect(worktreeGuardTraceLines(fixture.readTrace())).toHaveLength(0);
	});
});

describe("worktree junction guard real user_bash dispatch via activate (AC-014)", () => {
	beforeEach(() => {
		savedWorkerTask = process.env[ENV_WORKER_TASK];
		savedCwd = process.cwd();
		savedUserBashTarget = process.env[ENV_USER_BASH_TARGET];
	});

	afterEach(() => {
		cleanupHarnessesAndFixtures();
		if (savedUserBashTarget === undefined) {
			delete process.env[ENV_USER_BASH_TARGET];
		} else {
			process.env[ENV_USER_BASH_TARGET] = savedUserBashTarget;
		}
	});

	it("AC-014 (literal): refuses the accident command on the ! channel, runs nothing, records the trace", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture, true);
		const command = `git worktree remove --force "${fixture.wt}"`;

		const outcome = await runUserBash(harness, command);

		expect(outcome.intercepted).toBe(true);
		expect(outcome.output).toContain("[mw-worktree-guard] blocked");
		expect(outcome.output).toContain(`mw worktree rm "${fixture.wt}"`);
		// Strongest evidence: the execution backend never saw the command.
		expect(outcome.executed).toEqual([]);
		// AC-014 + AC-004: the refusal is observable next to task.md.
		expect(worktreeGuardTraceLines(fixture.readTrace())).toHaveLength(1);
		expect(fixture.readTrace()).toContain("blocked tool=user_bash");
	});

	it("AC-014 (interpolation): refuses the accident-shape $env: target on the ! channel, runs nothing", async () => {
		const fixture = createFixture();
		process.env[ENV_USER_BASH_TARGET] = fixture.wt;
		const { harness } = await createGuardHarness(fixture, true);
		const command = `git worktree remove --force "$env:${ENV_USER_BASH_TARGET}"`;

		const outcome = await runUserBash(harness, command);

		expect(outcome.intercepted).toBe(true);
		expect(outcome.output).toContain("[mw-worktree-guard] blocked");
		expect(outcome.output).toContain(`mw worktree rm "${fixture.wt}"`);
		expect(outcome.executed).toEqual([]);
		expect(worktreeGuardTraceLines(fixture.readTrace())).toHaveLength(1);
	});

	it("AC-014 (reverse control): a clean target on the ! channel still runs for real", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture, true);
		const command = `git worktree remove --force "${fixture.clean}"`;

		const outcome = await runUserBash(harness, command);

		expect(outcome.intercepted).toBe(false);
		expect(outcome.executed).toEqual([command]);
		expect(worktreeGuardTraceLines(fixture.readTrace())).toHaveLength(0);
	});

	it("AC-014: the prescribed replacements are not eaten by the guard itself", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture, true);
		const commands = [`mw worktree rm "${fixture.wt}"`, `cmd /c rmdir "${fixture.link}"`];

		for (const command of commands) {
			const outcome = await runUserBash(harness, command);
			expect(outcome.intercepted, command).toBe(false);
			expect(outcome.executed, command).toEqual([command]);
		}
		expect(worktreeGuardTraceLines(fixture.readTrace())).toHaveLength(0);
	});
});
