/**
 * Implementation entry gate wiring tests (mw-implementation-gate T3, AC-006).
 *
 * The anti-example these tests must not repeat: P-002's
 * agent-team-loop-protected-config.test.ts exercises only the pure decision
 * functions, which stay green while the registration breaks. Every scenario
 * here drives REAL tool_call dispatch through the production pipeline:
 *
 *   faux provider tool_use → Agent agent-loop → beforeToolCall hook
 *   (AgentSession._installAgentToolHooks) → ExtensionRunner.emitToolCall →
 *   the registerImplementationGate handler registered on the real
 *   createExtensionAPI surface (the same pi.on("tool_call") registration
 *   index.ts activate() performs) → {block, reason} handling in the agent
 *   loop (createErrorToolResult, the tool never executes).
 *
 * Only the bash shell backend is stubbed (BashOperations recorder) to keep
 * the suite CI-safe; every layer above it — tool schemas, argument
 * validation, event dispatch, block result handling — is the real one. The
 * write/edit tools are the real production tools writing to the fixture.
 *
 * Fixtures: a temp project root per test is injected via MW_IMPL_GATE_ROOT
 * (the gate's test hook) containing .agenticdoc/_index.parallel and/or
 * .agenticdoc/<key>/mini-spec.md. The active-claim fixture uses
 * currentClaimId() so the row's claim id matches this very host:pid, exactly
 * like an update_index.py claim would record.
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
import { createWriteTool } from "../../src/core/tools/write.ts";
import {
	currentClaimId,
	registerImplementationGate,
} from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { createHarness, type Harness } from "./harness.ts";

const ENV_GATE_ROOT = "MW_IMPL_GATE_ROOT";
const ENV_WORKER_TASK = "PI_WORKER_TASK";

interface GateFixture {
	/** Temp project root the gate anchors code paths against. */
	root: string;
	/** <root>/.agenticdoc */
	agenticdoc: string;
	/** <root>/.agenticdoc/_impl_gate.log */
	logPath: string;
	/** Absolute path under the fixture's packages/ tree. */
	codePath(...segments: string[]): string;
	/** Write an _index.parallel whose single row is active with this claim id. */
	writeIndex(claimId: string): void;
	/** Write a fresh (<24h) mini-spec.md under .agenticdoc/<key>/. */
	writeMiniSpec(key: string): string;
	readLog(): string;
	logExists(): boolean;
}

function createFixture(): GateFixture {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-impl-gate-"));
	const agenticdoc = path.join(root, ".agenticdoc");
	const fixture: GateFixture = {
		root,
		agenticdoc,
		logPath: path.join(agenticdoc, "_impl_gate.log"),
		codePath(...segments: string[]): string {
			return path.join(root, "packages", ...segments);
		},
		writeIndex(claimId: string): void {
			fs.mkdirSync(agenticdoc, { recursive: true });
			fs.writeFileSync(
				path.join(agenticdoc, "_index.parallel"),
				[
					"# Index Parallel",
					"",
					"| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
					"|-----|--------|-------|---------|------|------|---------|",
					`| mw-implementation-gate | active | EXECUTE | ${claimId} | — | gate wiring tests | 2026-09-22 00:00 |`,
					"",
				].join("\n"),
				"utf8",
			);
		},
		writeMiniSpec(key: string): string {
			const dir = path.join(agenticdoc, key);
			fs.mkdirSync(dir, { recursive: true });
			const mini = path.join(dir, "mini-spec.md");
			fs.writeFileSync(mini, "trivial fix fast path: one-line change\n", "utf8");
			return mini;
		},
		readLog(): string {
			try {
				return fs.readFileSync(this.logPath, "utf8");
			} catch {
				return "";
			}
		},
		logExists(): boolean {
			return fs.existsSync(this.logPath);
		},
	};
	fixtures.push(fixture);
	return fixture;
}

const harnesses: Harness[] = [];
const fixtures: GateFixture[] = [];
let savedGateRoot: string | undefined;
let savedWorkerTask: string | undefined;

/** Boot a session whose ONLY extension registers the gate the same way
 * index.ts activate() does, with the real write/edit/bash tools bound to the
 * fixture root. Returns the bash operations recorder (the one stubbed layer). */
async function createGateHarness(fixture: GateFixture): Promise<{ harness: Harness; executedBashCommands: string[] }> {
	process.env[ENV_GATE_ROOT] = fixture.root;
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
		],
		extensionFactories: [
			(pi) => {
				registerImplementationGate(pi);
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

function blockedLines(log: string): string[] {
	return log
		.split(/\r?\n/)
		.filter((line) => line.trim() !== "")
		.filter((line) => line.includes(" blocked "));
}

describe("agent-team-loop implementation gate (mw-implementation-gate AC-001/002/004, real tool-call dispatch)", () => {
	beforeEach(() => {
		savedGateRoot = process.env[ENV_GATE_ROOT];
		savedWorkerTask = process.env[ENV_WORKER_TASK];
		// A dispatched worker env pre-authorizes code writes (D-3b); the block
		// scenarios must not inherit this test runner's own PI_WORKER_TASK.
		delete process.env[ENV_WORKER_TASK];
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

	it("AC-001: write to a code path with no claim and no mini-spec is blocked with guidance, never touches disk, and audits", async () => {
		const fixture = createFixture();
		const { harness } = await createGateHarness(fixture);
		const target = fixture.codePath("x", "mw.py");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: target, content: "wild implementation" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("acknowledged"),
		]);

		await harness.session.prompt("implement it");

		const results = toolResults(harness, "write");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(true);
		const text = results[0] ? toolResultText(results[0]) : "";
		expect(text).toContain("implementation-gate");
		// Guidance names both compliant paths (AC-001: the word "mini" + the
		// .agenticdoc spec location).
		expect(text).toContain("mini");
		expect(text).toContain(".agenticdoc");
		expect(text).toContain("spec.md");
		// The tool never executed: no file on disk.
		expect(fs.existsSync(target)).toBe(false);
		// Audit: one blocked line naming the tool, target, and basis.
		const log = fixture.readLog();
		expect(blockedLines(log)).toHaveLength(1);
		expect(log).toContain("tool=write");
		expect(log).toContain("basis=no-claim-no-mini");
		expect(log).toContain(target);
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("AC-001: edit of a code path with no claim is blocked and leaves the file unchanged", async () => {
		const fixture = createFixture();
		const target = fixture.codePath("x", "existing.py");
		fs.mkdirSync(path.dirname(target), { recursive: true });
		fs.writeFileSync(target, "original = 1\n", "utf8");
		const { harness } = await createGateHarness(fixture);
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("edit", {
						path: target,
						edits: [{ oldText: "original = 1", newText: "original = 2" }],
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("acknowledged"),
		]);

		await harness.session.prompt("edit it");

		const results = toolResults(harness, "edit");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(true);
		expect(results[0] ? toolResultText(results[0]) : "").toContain("implementation-gate");
		expect(fs.readFileSync(target, "utf8")).toBe("original = 1\n");
		const log = fixture.readLog();
		expect(blockedLines(log)).toHaveLength(1);
		expect(log).toContain("tool=edit");
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("AC-002: an active claim row matching this window's host:pid unlocks the write, un-audited", async () => {
		const fixture = createFixture();
		fixture.writeIndex(currentClaimId());
		const { harness } = await createGateHarness(fixture);
		const target = fixture.codePath("x", "claimed.py");
		const afterRelease = fixture.codePath("x", "released.py");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: target, content: "keyed work" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
			fauxAssistantMessage([fauxToolCall("write", { path: afterRelease, content: "must be blocked" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("acknowledged"),
		]);

		// Turn 1: the claim row names this window's host:pid → the write passes.
		await harness.session.prompt("keyed implementation");
		let results = toolResults(harness, "write");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(fs.readFileSync(target, "utf8")).toBe("keyed work");
		// Claim passes are not audited (the claim row is already the record).
		expect(fixture.logExists()).toBe(false);

		// Turn 2: release the claim (row gone) → the same window is blocked
		// again. This also proves turn 1 passed through the gate, not around it.
		fs.rmSync(path.join(fixture.agenticdoc, "_index.parallel"));
		await harness.session.prompt("implement more");
		results = toolResults(harness, "write");
		expect(results).toHaveLength(2);
		expect(results[1]?.isError).toBe(true);
		expect(fs.existsSync(afterRelease)).toBe(false);
		expect(blockedLines(fixture.readLog())).toHaveLength(1);
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("AC-002 (negative): another window's active claim does not unlock this window", async () => {
		const fixture = createFixture();
		fixture.writeIndex("OTHERHOST:999999");
		const { harness } = await createGateHarness(fixture);
		const target = fixture.codePath("x", "notmine.py");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: target, content: "should not land" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("acknowledged"),
		]);

		await harness.session.prompt("try to implement");

		const results = toolResults(harness, "write");
		expect(results[0]?.isError).toBe(true);
		expect(fs.existsSync(target)).toBe(false);
		expect(blockedLines(fixture.readLog())).toHaveLength(1);
	});

	it("mini fast path: a fresh mini-spec.md passes the write and audits a mini-pass line", async () => {
		const fixture = createFixture();
		fixture.writeMiniSpec("mw-trivial-fix");
		const { harness } = await createGateHarness(fixture);
		const target = fixture.codePath("x", "trivial.py");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: target, content: "one-line fix" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("trivial fix");

		const results = toolResults(harness, "write");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(fs.readFileSync(target, "utf8")).toBe("one-line fix");
		const log = fixture.readLog();
		expect(log).toContain(" mini-pass ");
		expect(log).toContain("tool=write");
		expect(log).toContain("basis=mini-spec:.agenticdoc/mw-trivial-fix/mini-spec.md");
		expect(blockedLines(log)).toHaveLength(0);
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("mini fast path decays: a stale (>24h) mini-spec.md no longer passes", async () => {
		const fixture = createFixture();
		const mini = fixture.writeMiniSpec("mw-stale-fix");
		const stale = new Date(Date.now() - 25 * 60 * 60 * 1000);
		fs.utimesSync(mini, stale, stale);
		const { harness } = await createGateHarness(fixture);
		const target = fixture.codePath("x", "stale.py");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: target, content: "must be blocked" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("acknowledged"),
		]);

		await harness.session.prompt("try again");

		const results = toolResults(harness, "write");
		expect(results[0]?.isError).toBe(true);
		expect(fs.existsSync(target)).toBe(false);
		expect(blockedLines(fixture.readLog())).toHaveLength(1);
	});

	it("worker env (PI_WORKER_TASK) pre-authorizes dispatched workers, un-audited", async () => {
		const fixture = createFixture();
		process.env[ENV_WORKER_TASK] = path.join(fixture.agenticdoc, "workers", "w1", "task.md");
		const { harness } = await createGateHarness(fixture);
		const target = fixture.codePath("x", "worker.py");
		const afterEnvGone = fixture.codePath("x", "noworker.py");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: target, content: "worker output" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
			fauxAssistantMessage([fauxToolCall("write", { path: afterEnvGone, content: "must be blocked" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("acknowledged"),
		]);

		// Turn 1: the dispatched-worker env pre-authorizes the write.
		await harness.session.prompt("worker implementation");
		let results = toolResults(harness, "write");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(fs.readFileSync(target, "utf8")).toBe("worker output");
		expect(fixture.logExists()).toBe(false);

		// Turn 2: env gone → blocked, proving turn 1 was gate-mediated.
		delete process.env[ENV_WORKER_TASK];
		await harness.session.prompt("interactive now");
		results = toolResults(harness, "write");
		expect(results).toHaveLength(2);
		expect(results[1]?.isError).toBe(true);
		expect(fs.existsSync(afterEnvGone)).toBe(false);
		expect(blockedLines(fixture.readLog())).toHaveLength(1);
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("AC-004: writes to non-code paths (packages/**.md, docs/**, .agenticdoc/**, tmp/**) are not gated", async () => {
		const fixture = createFixture();
		const { harness } = await createGateHarness(fixture);
		const readmeInPackages = fixture.codePath("x", "README.md");
		const docsFile = path.join(fixture.root, "docs", "design.md");
		const agenticdocFile = path.join(fixture.agenticdoc, "mw-key", "notes.md");
		const tmpFile = path.join(fixture.root, "tmp", "scratch.py");
		// Same turn, same root: one genuine code path as the control — it must
		// be the ONLY blocked call, proving the whitelist files passed through
		// the gate and not around it.
		const codeFile = fixture.codePath("x", "real.py");
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("write", { path: readmeInPackages, content: "# readme" }),
					fauxToolCall("write", { path: docsFile, content: "design notes" }),
					fauxToolCall("write", { path: agenticdocFile, content: "key notes" }),
					fauxToolCall("write", { path: tmpFile, content: "scratch" }),
					fauxToolCall("write", { path: codeFile, content: "code" }),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("write documentation");

		const results = toolResults(harness, "write");
		expect(results).toHaveLength(5);
		const errors = results.filter((result) => result.isError);
		expect(errors).toHaveLength(1);
		expect(errors[0] ? toolResultText(errors[0]) : "").toContain("implementation-gate");
		for (const file of [readmeInPackages, docsFile, agenticdocFile, tmpFile]) {
			expect(fs.existsSync(file), file).toBe(true);
		}
		expect(fs.existsSync(codeFile)).toBe(false);
		expect(blockedLines(fixture.readLog())).toHaveLength(1);
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("bash: a redirect target on a code path is blocked without executing; a payload mention of a code path passes", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGateHarness(fixture);
		// path.join uses the platform's native separators — on win32 this is
		// the backslash spelling a real PowerShell-backed bash tool emits.
		const nativeTarget = fixture.codePath("x", "mw.py");
		const quotedTarget = fixture.codePath("x", "mw2.py");
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("bash", { command: `echo pwned > ${nativeTarget}` }),
					fauxToolCall("bash", { command: `echo pwned2 > "${quotedTarget}"` }),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("acknowledged"),
			fauxAssistantMessage([fauxToolCall("bash", { command: 'echo "packages/x/mw.py"' })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
		]);

		// Turn 1: both redirect writes target code paths with no claim.
		await harness.session.prompt("write via shell");
		let results = toolResults(harness, "bash");
		expect(results).toHaveLength(2);
		for (const result of results) {
			expect(result.isError).toBe(true);
			expect(toolResultText(result)).toContain("implementation-gate");
		}
		// The bash tool never reached its operations layer.
		expect(executedBashCommands).toEqual([]);
		expect(fs.existsSync(nativeTarget)).toBe(false);
		expect(fs.existsSync(quotedTarget)).toBe(false);
		const log = fixture.readLog();
		expect(blockedLines(log)).toHaveLength(2);
		expect(log).toContain("tool=bash");
		expect(log).toContain(nativeTarget);
		expect(log).toContain(quotedTarget);

		// Turn 2: the same code path merely mentioned in payload text passes —
		// the 2026-09-21 W2 false-positive lesson (payload reference + write
		// word must not fire the gate).
		await harness.session.prompt("mention a path");
		results = toolResults(harness, "bash");
		expect(results).toHaveLength(3);
		expect(results[2]?.isError).toBe(false);
		expect(executedBashCommands).toEqual(['echo "packages/x/mw.py"']);
		// No new audit lines for the passing call.
		expect(blockedLines(fixture.readLog())).toHaveLength(2);
		expect(harness.getPendingResponseCount()).toBe(0);
	});
});
