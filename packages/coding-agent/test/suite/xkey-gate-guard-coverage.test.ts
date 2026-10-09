/**
 * XKEY autopilot write-guard coverage (mw-autopilot-slot-capacity T-10,
 * design D-013, AC-020/AC-030, VC-025/VC-026).
 *
 * The audited party must not be able to forge the conductor's audit/control
 * files through its only channel. Until this card only `_autopilot/gates/**`
 * was fenced, so `timeline.jsonl` / `config.json` / `auto-decisions.jsonl`
 * could be appended to or flipped by hand. The guard now covers
 * `_autopilot/**` with a path boundary, while leaving the pre-existing
 * agent-writable `_autopilot/xkey/**` subtree (proposal/evidence, ledger,
 * tickets; xkey-repair-mechanism D-004/D-005) exactly as it was.
 *
 * Two layers, for the P-002 reason (pure decision functions stay green while
 * registration breaks):
 *   1. pure matcher assertions on `isXkeyGatePath` / `checkXkeyGateBashCommand`
 *      (boundary, lookalikes, xkey carve-out), and
 *   2. REAL `tool_call` dispatch through the production pipeline: faux
 *      provider → Agent loop → ExtensionRunner.emitToolCall → the handler
 *      `registerXkeyGateGuard` registered on the real createExtensionAPI
 *      surface → `{block, reason}` → the tool never executes. Only the bash
 *      backend is stubbed (BashOperations recorder) to stay CI-safe.
 *
 * Fixtures: a temp project root per test, injected via MW_XKEY_GATE_ROOT (the
 * guard's test hook) and PI_WORKER_TASK (so the refusal trace is observable
 * in the fixture, not the live repo). The gate root is read at registration
 * time, so the env is set before the harness boots.
 */

import { Buffer } from "node:buffer";
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
import {
	checkXkeyGateBashCommand,
	isXkeyGatePath,
	registerXkeyGateGuard,
	xkeyGuardedDir,
	xkeySubtreeDir,
} from "../../src/extensions/agent-team-loop/shared/xkey-gate-guard.ts";
import { createHarness, type Harness } from "./harness.ts";

const ENV_GATE_ROOT = "MW_XKEY_GATE_ROOT";
const ENV_WORKER_TASK = "PI_WORKER_TASK";

interface GuardFixture {
	/** Temp project root the guard anchors paths against. */
	root: string;
	/** <root>/.agenticdoc/_autopilot */
	autopilot: string;
	/** <root>/.agenticdoc/workers/w1/task.md */
	taskPath: string;
	/** dirname(taskPath)/trace.log — where refusals are recorded. */
	tracePath: string;
	/** Absolute path under the guarded _autopilot dir. */
	guarded(...segments: string[]): string;
	/** Absolute path under the carved-out xkey subtree. */
	xkey(...segments: string[]): string;
	/** Absolute path under a lookalike sibling of _autopilot. */
	lookalike(...segments: string[]): string;
	readTrace(): string;
}

function createFixture(): GuardFixture {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-xkey-guard-"));
	const autopilot = path.join(root, ".agenticdoc", "_autopilot");
	const taskPath = path.join(root, ".agenticdoc", "workers", "w1", "task.md");
	const fixture: GuardFixture = {
		root,
		autopilot,
		taskPath,
		tracePath: path.join(path.dirname(taskPath), "trace.log"),
		guarded(...segments: string[]): string {
			return path.join(autopilot, ...segments);
		},
		xkey(...segments: string[]): string {
			return path.join(autopilot, "xkey", ...segments);
		},
		lookalike(...segments: string[]): string {
			return path.join(root, ".agenticdoc", "_autopilotX", ...segments);
		},
		readTrace(): string {
			try {
				return fs.readFileSync(this.tracePath, "utf8");
			} catch {
				return "";
			}
		},
	};
	// Seed every file the blocking scenarios target, plus the xkey proposal
	// path and the lookalike dir.
	fs.mkdirSync(path.join(autopilot, "gates"), { recursive: true });
	fs.mkdirSync(path.dirname(fixture.xkey("evidence", "r1", "proposal.md")), { recursive: true });
	fs.mkdirSync(path.dirname(fixture.lookalike("timeline.jsonl")), { recursive: true });
	fs.writeFileSync(fixture.guarded("timeline.jsonl"), '{"seq":1,"ev":"tick"}\n', "utf8");
	fs.writeFileSync(fixture.guarded("config.json"), '{"enabled":true,"paused":false}\n', "utf8");
	fs.writeFileSync(fixture.guarded("auto-decisions.jsonl"), '{"decision_id":"d1"}\n', "utf8");
	fs.writeFileSync(fixture.guarded("gates", "gate-0001.md"), "---\nid: gate-0001\nstatus: pending\n---\n", "utf8");
	fs.writeFileSync(fixture.xkey("evidence", "r1", "proposal.md"), "proposal r1\n", "utf8");
	fixtures.push(fixture);
	return fixture;
}

const harnesses: Harness[] = [];
const fixtures: GuardFixture[] = [];
let savedGateRoot: string | undefined;
let savedWorkerTask: string | undefined;

async function createGuardHarness(
	fixture: GuardFixture,
): Promise<{ harness: Harness; executedBashCommands: string[] }> {
	process.env[ENV_GATE_ROOT] = fixture.root;
	process.env[ENV_WORKER_TASK] = fixture.taskPath;
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
			createWriteTool(fixture.root),
			createEditTool(fixture.root),
			createBashTool(fixture.root, { operations: bashOperations }),
			createReadTool(fixture.root),
			createFindTool(fixture.root),
			createGrepTool(fixture.root),
		],
		extensionFactories: [
			(pi) => {
				registerXkeyGateGuard(pi);
			},
		],
	});
	harnesses.push(harness);
	return { harness, executedBashCommands };
}

function toolResults(harness: Harness, toolName: string): ToolResultMessage[] {
	return harness.session.messages.filter(
		(message): message is ToolResultMessage => message.role === "toolResult" && message.toolName === toolName,
	);
}

function toolResultText(message: ToolResultMessage): string {
	return message.content
		.filter((part): part is { type: "text"; text: string } => part.type === "text")
		.map((part) => part.text)
		.join("\n");
}

function xkeyGateTraceLines(trace: string): string[] {
	return trace
		.split(/\r?\n/)
		.filter((line) => line.trim() !== "")
		.filter((line) => line.includes("[XKEY_GATE]"));
}

describe("xkey guard path matcher (T-10, VC-025/VC-026)", () => {
	it("blocks every _autopilot audit/control target by absolute path", () => {
		const fixture = createFixture();
		for (const rel of ["timeline.jsonl", "config.json", "auto-decisions.jsonl", path.join("gates", "gate-0001.md")]) {
			expect(isXkeyGatePath(fixture.root, fixture.guarded(rel)), rel).toBe(true);
		}
		// The guarded directory itself (and any future file in it) is refused.
		expect(isXkeyGatePath(fixture.root, fixture.autopilot)).toBe(true);
		expect(isXkeyGatePath(fixture.root, fixture.guarded("future-state.json"))).toBe(true);
	});

	it("blocks relative spellings against the given cwd", () => {
		const fixture = createFixture();
		expect(isXkeyGatePath(fixture.root, ".agenticdoc/_autopilot/timeline.jsonl", fixture.root)).toBe(true);
		expect(isXkeyGatePath(fixture.root, ".agenticdoc/_autopilot/config.json", fixture.root)).toBe(true);
		expect(xkeyGuardedDir(fixture.root)).toBe(fixture.autopilot);
	});

	it("blocks an absolute spelling aimed at any other project's _autopilot", () => {
		const fixture = createFixture();
		const other = path.join(fixture.root, "..", "other-project", ".agenticdoc", "_autopilot", "timeline.jsonl");
		expect(isXkeyGatePath(fixture.root, other)).toBe(true);
	});

	it("does NOT hit path-boundary lookalikes (_autopilotX, _autopilot-backup)", () => {
		const fixture = createFixture();
		expect(isXkeyGatePath(fixture.root, fixture.lookalike("timeline.jsonl"))).toBe(false);
		expect(
			isXkeyGatePath(fixture.root, path.join(fixture.root, ".agenticdoc", "_autopilot-backup", "config.json")),
		).toBe(false);
	});

	it("leaves the pre-existing xkey subtree writable, but not its lookalikes", () => {
		const fixture = createFixture();
		expect(xkeySubtreeDir(fixture.root)).toBe(fixture.xkey());
		expect(isXkeyGatePath(fixture.root, fixture.xkey("evidence", "r1", "proposal.md"))).toBe(false);
		expect(isXkeyGatePath(fixture.root, fixture.xkey("ledger.json"))).toBe(false);
		expect(isXkeyGatePath(fixture.root, fixture.xkey("tickets", "xkey-1.md"))).toBe(false);
		// `_autopilot/xkeyX` is not the carved-out subtree.
		expect(isXkeyGatePath(fixture.root, fixture.guarded("xkeyX", "evil.md"))).toBe(true);
	});

	it("verdicts on bash commands: writes refused, reads allowed, lookalikes untouched", () => {
		const fixture = createFixture();
		const blocked = [
			"echo forged >> .agenticdoc/_autopilot/timeline.jsonl",
			"rm .agenticdoc/_autopilot/config.json",
			"Set-Content .agenticdoc/_autopilot/config.json '{}'",
			"sed -i s/enabled/disabled/ .agenticdoc/_autopilot/config.json",
			"echo x > .agenticdoc/_autopilot/gates/gate-0001.md",
		];
		for (const command of blocked) {
			expect(checkXkeyGateBashCommand(fixture.root, command).prohibited, command).toBe(true);
		}
		const allowed = [
			"cat .agenticdoc/_autopilot/timeline.jsonl",
			"rg forged .agenticdoc/_autopilot/",
			"echo proposal > .agenticdoc/_autopilot/xkey/evidence/r1/proposal.md",
			"echo x > .agenticdoc/_autopilotX/timeline.jsonl",
		];
		for (const command of allowed) {
			expect(checkXkeyGateBashCommand(fixture.root, command).prohibited, command).toBe(false);
		}
	});
});

describe("xkey guard real tool_call dispatch (T-10, VC-025/VC-026)", () => {
	beforeEach(() => {
		savedGateRoot = process.env[ENV_GATE_ROOT];
		savedWorkerTask = process.env[ENV_WORKER_TASK];
	});

	afterEach(() => {
		while (harnesses.length > 0) {
			harnesses.pop()?.cleanup();
		}
		while (fixtures.length > 0) {
			const fixture = fixtures.pop();
			if (fixture) fs.rmSync(fixture.root, { recursive: true, force: true });
		}
		if (savedGateRoot === undefined) {
			delete process.env[ENV_GATE_ROOT];
		} else {
			process.env[ENV_GATE_ROOT] = savedGateRoot;
		}
		if (savedWorkerTask === undefined) {
			delete process.env[ENV_WORKER_TASK];
		} else {
			process.env[ENV_WORKER_TASK] = savedWorkerTask;
		}
	});

	it("VC-025: write/edit of timeline.jsonl, config.json, auto-decisions.jsonl and gates/** are all refused, never land, and leave a trace", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture);
		const gateFile = fixture.guarded("gates", "gate-0001.md");
		const gateBefore = fs.readFileSync(gateFile, "utf8");
		const configBefore = fs.readFileSync(fixture.guarded("config.json"), "utf8");
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("write", { path: fixture.guarded("timeline.jsonl"), content: '{"seq":2,"ev":"forged"}\n' }),
					fauxToolCall("write", { path: fixture.guarded("config.json"), content: '{"enabled":false}\n' }),
					fauxToolCall("write", {
						path: fixture.guarded("auto-decisions.jsonl"),
						content: '{"decision_id":"fake"}\n',
					}),
					fauxToolCall("write", { path: gateFile, content: "---\nid: gate-0001\nstatus: approved\n---\n" }),
					fauxToolCall("edit", {
						path: fixture.guarded("config.json"),
						edits: [{ oldText: '"enabled":true', newText: '"enabled":false' }],
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("acknowledged"),
		]);

		await harness.session.prompt("forge the audit trail");

		const results = toolResults(harness, "write").concat(toolResults(harness, "edit"));
		expect(results).toHaveLength(5);
		for (const result of results) {
			expect(result.isError).toBe(true);
			expect(toolResultText(result)).toContain("xkey-gate-guard: blocked");
		}
		// Nothing changed on disk.
		expect(fs.readFileSync(fixture.guarded("timeline.jsonl"), "utf8")).toBe('{"seq":1,"ev":"tick"}\n');
		expect(fs.readFileSync(fixture.guarded("config.json"), "utf8")).toBe(configBefore);
		expect(fs.readFileSync(fixture.guarded("auto-decisions.jsonl"), "utf8")).toBe('{"decision_id":"d1"}\n');
		expect(fs.readFileSync(gateFile, "utf8")).toBe(gateBefore);
		// VC-025 trace=true: one [XKEY_GATE] record per refusal.
		const trace = fixture.readTrace();
		expect(xkeyGateTraceLines(trace)).toHaveLength(5);
		expect(trace).toContain("blocked tool=write");
		expect(trace).toContain("blocked tool=edit");
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("does not hit the _autopilotX lookalike: the write lands and no trace is recorded", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture);
		const lookalike = fixture.lookalike("timeline.jsonl");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: lookalike, content: "not the real thing\n" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("write a lookalike");

		const results = toolResults(harness, "write");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(fs.readFileSync(lookalike, "utf8")).toBe("not the real thing\n");
		expect(xkeyGateTraceLines(fixture.readTrace())).toHaveLength(0);
	});

	it("keeps the xkey proposal path writable (existing xkey-repair-mechanism behaviour, no regression)", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture);
		const proposal = fixture.xkey("evidence", "r2", "proposal.md");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: proposal, content: "proposal r2\n" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("propose a fix");

		const results = toolResults(harness, "write");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(fs.readFileSync(proposal, "utf8")).toBe("proposal r2\n");
		expect(xkeyGateTraceLines(fixture.readTrace())).toHaveLength(0);
	});

	it("read paths still pass: read/find/grep on _autopilot are never intercepted", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture);
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("read", { path: fixture.guarded("timeline.jsonl") }),
					fauxToolCall("find", { pattern: "*.jsonl", path: fixture.autopilot }),
					fauxToolCall("grep", { pattern: "forged", path: fixture.autopilot }),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("inspect the audit trail");

		const read = toolResults(harness, "read");
		expect(read).toHaveLength(1);
		expect(read[0]?.isError).toBe(false);
		expect(read[0] ? toolResultText(read[0]) : "").toContain('"ev":"tick"');
		// find/grep may need fd/rg; the assertion is that the GUARD did not
		// intercept them (no refusal text, no trace), not that they matched.
		for (const toolName of ["find", "grep"]) {
			const results = toolResults(harness, toolName);
			expect(results, toolName).toHaveLength(1);
			expect(results[0]?.isError === true && toolResultText(results[0]).includes("xkey-gate-guard"), toolName).toBe(
				false,
			);
		}
		expect(xkeyGateTraceLines(fixture.readTrace())).toHaveLength(0);
	});

	it("read-only bash referencing _autopilot is not blocked", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGuardHarness(fixture);
		const command = `cat ${fixture.guarded("timeline.jsonl")}`;
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("bash", { command })], { stopReason: "toolUse" }),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("read the timeline via shell");

		const results = toolResults(harness, "bash");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(executedBashCommands).toEqual([command]);
		expect(xkeyGateTraceLines(fixture.readTrace())).toHaveLength(0);
	});
});
