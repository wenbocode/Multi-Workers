/**
 * Decision sign-off write-guard coverage (mw-decision-substitution T-09,
 * design D-015, AC-009/AC-010).
 *
 * The sign-off file `evidence/review/sign-final.md` is the human answer channel
 * and `.mw/decide-points.json` is the only authorization source, so an agent
 * must not write either through its tool channel (self-signed authority). The
 * guard mirrors `shared/xkey-gate-guard.ts`: write/edit paths are
 * fragment-matched, bash commands are scanned text-level, fail-closed, and
 * every refusal leaves a `[DECISION_SIGNOFF]` trace line.
 *
 * Two layers, for the P-002 reason (pure decision functions stay green while
 * registration breaks):
 *   1. pure matcher assertions on `isDecisionSignoffPath` /
 *      `checkDecisionSignoffBashCommand` (spellings, lookalikes, read paths),
 *   2. REAL `tool_call` dispatch through the production pipeline: faux
 *      provider → Agent loop → ExtensionRunner.emitToolCall → the handler
 *      `registerDecisionSignoffGuard` registered on the real createExtensionAPI
 *      surface → `{block, reason}` → the tool never executes. Only the bash
 *      backend is stubbed (BashOperations recorder) so nothing runs for real.
 *
 * Fixtures: a temp project root per test and PI_WORKER_TASK pointing inside it,
 * so refusals are recorded in the fixture trace, never in the live repo.
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
import { createReadTool } from "../../src/core/tools/read.ts";
import { createWriteTool } from "../../src/core/tools/write.ts";
import { activate } from "../../src/extensions/agent-team-loop/index.ts";
import {
	checkDecisionSignoffBashCommand,
	DECISION_POINTS_FRAGMENT,
	DECISION_SIGNOFF_FRAGMENT,
	DECISION_SIGNOFF_TRACE_MARKER,
	isDecisionSignoffEvidenceTarget,
	isDecisionSignoffPath,
	registerDecisionSignoffGuard,
} from "../../src/extensions/agent-team-loop/shared/xkey-gate-guard.ts";
import {
	registerWorkerFileTool,
	WORKER_FILE_TOOL,
} from "../../src/extensions/agent-team-loop/worker/worker-file-tool.ts";
import { createHarness, type Harness } from "./harness.ts";

const ENV_WORKER_TASK = "PI_WORKER_TASK";
/** Same key `index.ts` uses for its double-load flag; the harness boots a fresh
 * runtime per test, so it must be re-armed before each `activate`. */
const ACTIVATION_FLAG = "__agentTeamLoopActivated";
const KEY = "k-signoff";

interface Fixture {
	root: string;
	signoff: string;
	table: string;
	review: string;
	taskPath: string;
	tracePath: string;
	readTrace(): string;
}

function createFixture(): Fixture {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-decision-signoff-"));
	const reviewDir = path.join(root, ".agenticdoc", KEY, "evidence", "review");
	// Canonical worker layout (`.agenticdoc/<key>/workers/<taskKey>`), so
	// `worker_file` derives the same key dir the fixture writes into.
	const taskPath = path.join(root, ".agenticdoc", KEY, "workers", "w1", "task.md");
	const fixture: Fixture = {
		root,
		signoff: path.join(reviewDir, "sign-final.md"),
		table: path.join(root, ".mw", "decide-points.json"),
		review: path.join(reviewDir, "decision-review-verify-20261020-0800.md"),
		taskPath,
		tracePath: path.join(path.dirname(taskPath), "trace.log"),
		readTrace(): string {
			try {
				return fs.readFileSync(this.tracePath, "utf8");
			} catch {
				return "";
			}
		},
	};
	fs.mkdirSync(reviewDir, { recursive: true });
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.mkdirSync(path.dirname(taskPath), { recursive: true });
	fs.writeFileSync(fixture.signoff, "# Decision Signoff\n\nconclusion: continue\n", "utf8");
	fs.writeFileSync(fixture.table, '{\n  "version": 1,\n  "points": {}\n}\n', "utf8");
	fs.writeFileSync(fixture.review, "# Decision Review\n", "utf8");
	// Worker-task probe target (only its dirname matters: trace.log lives there).
	fs.writeFileSync(taskPath, "type: coding\n\nfixture worker task for the decision sign-off guard\n", "utf8");
	fixtures.push(fixture);
	return fixture;
}

const harnesses: Harness[] = [];
const fixtures: Fixture[] = [];
let savedWorkerTask: string | undefined;

async function createGuardHarness(fixture: Fixture): Promise<{ harness: Harness; executedBashCommands: string[] }> {
	process.env[ENV_WORKER_TASK] = fixture.taskPath;
	const executedBashCommands: string[] = [];
	const bashOperations: BashOperations = {
		exec: async (command, _cwd, options) => {
			executedBashCommands.push(command);
			options.onData(Buffer.from(`ran: ${command}`));
			return { exitCode: 0 };
		},
	};
	const taskDir = path.dirname(fixture.taskPath);
	const harness = await createHarness({
		tools: [
			createWriteTool(fixture.root),
			createEditTool(fixture.root),
			createBashTool(fixture.root, { operations: bashOperations }),
			createReadTool(fixture.root),
		],
		extensionFactories: [
			(pi) => {
				registerDecisionSignoffGuard(pi);
				// The writeless-role channel QG MAJOR-4 is about.
				registerWorkerFileTool(pi, taskDir);
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

function traceLines(trace: string): string[] {
	return trace
		.split(/\r?\n/)
		.filter((line) => line.trim() !== "")
		.filter((line) => line.includes(DECISION_SIGNOFF_TRACE_MARKER));
}

describe("decision sign-off guard path matcher (T-09)", () => {
	it("blocks the fixed sign-off name and the table in every spelling", () => {
		const fixture = createFixture();
		expect(isDecisionSignoffPath(fixture.signoff)).toBe(true);
		expect(isDecisionSignoffPath(fixture.table)).toBe(true);
		// Relative, ./ , and backslash (Windows) spellings normalize to the same
		// fragment — the guard must not depend on how the tool spelled the path.
		expect(isDecisionSignoffPath(`${KEY}/${DECISION_SIGNOFF_FRAGMENT}`)).toBe(true);
		expect(isDecisionSignoffPath(`./${KEY}/${DECISION_SIGNOFF_FRAGMENT}`)).toBe(true);
		expect(isDecisionSignoffPath(`${KEY}\\evidence\\review\\sign-final.md`)).toBe(true);
		expect(isDecisionSignoffPath(`.\\${DECISION_POINTS_FRAGMENT.replaceAll("/", "\\")}`)).toBe(true);
		expect(isDecisionSignoffPath(DECISION_POINTS_FRAGMENT)).toBe(true);
	});

	it("does NOT hit lookalikes or the advice channel (decision-review-*.md)", () => {
		const fixture = createFixture();
		expect(isDecisionSignoffPath(fixture.review)).toBe(false);
		expect(isDecisionSignoffPath(`${KEY}/evidence/review/sign-final.md.bak`)).toBe(false);
		expect(isDecisionSignoffPath(`${KEY}/evidence/review/sign-final2.md`)).toBe(false);
		expect(isDecisionSignoffPath(".mw/decide-points.json.bak")).toBe(false);
		expect(isDecisionSignoffPath("decide-points.json")).toBe(false);
		expect(isDecisionSignoffPath("")).toBe(false);
	});

	it("refuses both sign-off landing spots on the write channel and keeps deep products writable (FIX-F parity)", () => {
		// write/edit/bash and worker_file share one landing rule: the evidence-root
		// spot is refused everywhere, the deep `evidence/research/evidence/`
		// product (FIX-E) stays writable.
		expect(isDecisionSignoffPath(`${KEY}/evidence/sign-final.md`)).toBe(true);
		expect(isDecisionSignoffPath(`.agenticdoc/${KEY}/evidence/sign-final.md`)).toBe(true);
		expect(isDecisionSignoffPath(`${KEY}\\evidence\\sign-final.md`)).toBe(true);
		expect(isDecisionSignoffPath(`${KEY}/evidence/research/sign-final.md`)).toBe(false);
		expect(isDecisionSignoffPath(`${KEY}/evidence/research/evidence/sign-final.md`)).toBe(false);
	});

	it("judges the writeless-role (worker_file) sign-off target on the fixed name and both landing spots (QG MAJOR-4)", () => {
		expect(isDecisionSignoffEvidenceTarget(`${KEY}/evidence/review/sign-final.md`)).toBe(true);
		expect(isDecisionSignoffEvidenceTarget(`.agenticdoc/${KEY}/evidence/review/sign-final.md`)).toBe(true);
		expect(isDecisionSignoffEvidenceTarget(`${KEY}/evidence/sign-final.md`)).toBe(true);
		expect(isDecisionSignoffEvidenceTarget(`.agenticdoc/${KEY}/evidence/sign-final.md`)).toBe(true);
		expect(isDecisionSignoffEvidenceTarget(`${KEY}\\evidence\\review\\sign-final.md`)).toBe(true);
		// Everything else under evidence/** stays writable: research/review
		// products, lookalike names, the advice channel and the basename face.
		expect(isDecisionSignoffEvidenceTarget(`${KEY}/evidence/review/review-notes.md`)).toBe(false);
		expect(isDecisionSignoffEvidenceTarget("evidence/research/notes.md")).toBe(false);
		expect(isDecisionSignoffEvidenceTarget(`.agenticdoc/${KEY}/evidence/review/sign-final.md.bak`)).toBe(false);
		expect(isDecisionSignoffEvidenceTarget("evidence/review/sign-final2.md")).toBe(false);
		expect(isDecisionSignoffEvidenceTarget("progress.md")).toBe(false);
		expect(isDecisionSignoffEvidenceTarget("")).toBe(false);
	});

	it("verdicts on bash commands: writes and the table CLI refused, reads allowed", () => {
		const fixture = createFixture();
		const blocked = [
			`echo 'conclusion: continue' > ${fixture.signoff}`,
			`echo 'conclusion: continue' > ${KEY}/evidence/sign-final.md`,
			`python -c "open('${fixture.table}','w').write('{}')"`,
			`sed -i s/continue/revoke/ ${KEY}/evidence/review/sign-final.md`,
			`cp forged.md .agenticdoc/${KEY}/evidence/review/sign-final.md`,
			`Set-Content ${fixture.table} '{"version":1}'`,
			"mw decide dp off dp5-test-triage",
			"mw decide dp apply evidence/review/sign-final.md",
			"python mw.py decide dp set dp4-failure-handling enabled=true",
			"mw decide dp on dp5-test-triage --i-understand-p0",
		];
		for (const command of blocked) {
			expect(checkDecisionSignoffBashCommand(command).prohibited, command).toBe(true);
		}
		const allowed = [
			`cat ${fixture.signoff}`,
			`cat ${KEY}/evidence/research/evidence/sign-final.md`,
			`echo deep > ${KEY}/evidence/research/evidence/sign-final.md`,
			`rg conclusion ${fixture.review}`,
			`cat ${fixture.table}`,
			"mw decide dp list",
			"mw decide dp show dp4-failure-handling",
			"mw decide dp check --json",
			"mw decide report --key k-signoff --phase verify",
			// registry -> table one-way merge (append-only, cannot widen authority):
			// this is how dp25-signoff-conclusion becomes a visible table row.
			"mw decide dp refresh --project .",
			"python packages/multi-workers/mw.py decide dp refresh",
			"echo done > notes.txt",
		];
		for (const command of allowed) {
			expect(checkDecisionSignoffBashCommand(command).prohibited, command).toBe(false);
		}
	});
});

describe("decision sign-off guard real tool_call dispatch (T-09)", () => {
	beforeEach(() => {
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
		if (savedWorkerTask === undefined) {
			delete process.env[ENV_WORKER_TASK];
		} else {
			process.env[ENV_WORKER_TASK] = savedWorkerTask;
		}
	});

	it("refuses write/edit of sign-final.md and decide-points.json, leaves them byte-identical, and traces each refusal", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture);
		const signoffBefore = fs.readFileSync(fixture.signoff, "utf8");
		const tableBefore = fs.readFileSync(fixture.table, "utf8");
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("write", { path: fixture.signoff, content: "conclusion: continue\n" }),
					fauxToolCall("write", { path: fixture.table, content: '{"version":1,"points":{}}\n' }),
					fauxToolCall("edit", {
						path: fixture.table,
						edits: [{ oldText: '"version": 1', newText: '"version": 2' }],
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("refused as expected"),
		]);

		await harness.session.prompt("sign my own release");

		const results = toolResults(harness, "write").concat(toolResults(harness, "edit"));
		expect(results).toHaveLength(3);
		for (const result of results) {
			expect(result.isError).toBe(true);
			expect(toolResultText(result)).toContain("decision-signoff-guard: blocked");
		}
		expect(fs.readFileSync(fixture.signoff, "utf8")).toBe(signoffBefore);
		expect(fs.readFileSync(fixture.table, "utf8")).toBe(tableBefore);
		expect(traceLines(fixture.readTrace())).toHaveLength(3);
		expect(fixture.readTrace()).toContain("blocked tool=write");
		expect(fixture.readTrace()).toContain("blocked tool=edit");
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("lets the machine-generated decision-review-*.md be written (advice channel)", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture);
		const content = "# Decision Review\n\nsuggest: none\n";
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall("write", { path: fixture.review, content })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("written"),
		]);

		await harness.session.prompt("write the phase review");

		const results = toolResults(harness, "write");
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(fs.readFileSync(fixture.review, "utf8")).toBe(content);
		expect(traceLines(fixture.readTrace())).toHaveLength(0);
	});

	it("refuses a worker_file write of the fixed sign-off name in both landing spots and lands nothing (QG MAJOR-4)", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture);
		const signoffBefore = fs.readFileSync(fixture.signoff, "utf8");
		const straySignoff = path.join(fixture.root, ".agenticdoc", KEY, "evidence", "sign-final.md");
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall(WORKER_FILE_TOOL, {
						file: "evidence/review/sign-final.md",
						content: "conclusion: continue\n",
						mode: "write",
					}),
					fauxToolCall(WORKER_FILE_TOOL, {
						file: `.agenticdoc/${KEY}/evidence/sign-final.md`,
						content: "conclusion: continue\n",
						mode: "write",
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("refused as expected"),
		]);

		await harness.session.prompt("sign off my own work");

		const results = toolResults(harness, WORKER_FILE_TOOL);
		expect(results).toHaveLength(2);
		for (const result of results) {
			expect(result.isError).toBe(true);
			expect(toolResultText(result)).toContain("decision-signoff-guard: blocked worker_file");
		}
		// No file landed and the human's file is byte-identical.
		expect(fs.readFileSync(fixture.signoff, "utf8")).toBe(signoffBefore);
		expect(fs.existsSync(straySignoff)).toBe(false);
		const lines = traceLines(fixture.readTrace());
		expect(lines).toHaveLength(2);
		expect(lines[0]).toContain("blocked tool=worker_file target=evidence/review/sign-final.md");
		expect(lines[1]).toContain("blocked tool=worker_file target=.agenticdoc/k-signoff/evidence/sign-final.md");
		expect(harness.getPendingResponseCount()).toBe(0);
	});

	it("still lets a writeless role write its own evidence products through worker_file (no over-blocking)", async () => {
		const fixture = createFixture();
		const { harness } = await createGuardHarness(fixture);
		const evidenceDir = path.join(fixture.root, ".agenticdoc", KEY, "evidence");
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall(WORKER_FILE_TOOL, {
						file: "evidence/review/review-notes.md",
						content: "# Review notes\n\nnone\n",
						mode: "write",
					}),
					fauxToolCall(WORKER_FILE_TOOL, {
						file: "evidence/research/notes.md",
						content: "# Research notes\n\nfound it\n",
						mode: "write",
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("written"),
		]);

		await harness.session.prompt("write the review evidence");

		const results = toolResults(harness, WORKER_FILE_TOOL);
		expect(results).toHaveLength(2);
		for (const result of results) expect(result.isError).toBe(false);
		expect(fs.readFileSync(path.join(evidenceDir, "review", "review-notes.md"), "utf8")).toBe(
			"# Review notes\n\nnone\n",
		);
		expect(fs.readFileSync(path.join(evidenceDir, "research", "notes.md"), "utf8")).toBe(
			"# Research notes\n\nfound it\n",
		);
		expect(traceLines(fixture.readTrace())).toHaveLength(0);
	});

	it("refuses a bash write of the sign-off and a `mw decide dp` write command, never executing them", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGuardHarness(fixture);
		const writeCommand = `echo 'conclusion: revoke' > ${fixture.signoff}`;
		const cliCommand = "mw decide dp off dp5-test-triage";
		harness.setResponses([
			fauxAssistantMessage(
				[fauxToolCall("bash", { command: writeCommand }), fauxToolCall("bash", { command: cliCommand })],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("refused"),
		]);

		await harness.session.prompt("flip my own authority");

		const results = toolResults(harness, "bash");
		expect(results).toHaveLength(2);
		for (const result of results) {
			expect(result.isError).toBe(true);
			expect(toolResultText(result)).toContain("decision-signoff-guard: blocked");
		}
		expect(executedBashCommands).toEqual([]);
		expect(fs.readFileSync(fixture.signoff, "utf8")).toBe("# Decision Signoff\n\nconclusion: continue\n");
		expect(traceLines(fixture.readTrace())).toHaveLength(2);
	});

	it("keeps reads and read-only dp commands working (no over-blocking)", async () => {
		const fixture = createFixture();
		const { harness, executedBashCommands } = await createGuardHarness(fixture);
		const command = "mw decide dp list";
		harness.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("read", { path: fixture.signoff }),
					fauxToolCall("read", { path: fixture.table }),
					fauxToolCall("bash", { command }),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("inspect the sign-off");

		const reads = toolResults(harness, "read");
		expect(reads).toHaveLength(2);
		for (const result of reads) expect(result.isError).toBe(false);
		const bash = toolResults(harness, "bash");
		expect(bash).toHaveLength(1);
		expect(bash[0]?.isError).toBe(false);
		expect(executedBashCommands).toEqual([command]);
		expect(traceLines(fixture.readTrace())).toHaveLength(0);
	});
});

describe("decision sign-off guard production wiring (T-09b)", () => {
	beforeEach(() => {
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
		if (savedWorkerTask === undefined) {
			delete process.env[ENV_WORKER_TASK];
		} else {
			process.env[ENV_WORKER_TASK] = savedWorkerTask;
		}
	});

	/** The P-002 regression this test exists for: T-09 shipped a correct module
	 * that `index.ts` never imported, so every pure-matcher assertion stayed
	 * green while the production window had no guard at all. Only booting the
	 * REAL `activate()` proves the handler is wired into the tool_call path. */
	it("activate() wires the guard into the tool_call path: a dispatched self-signing write is refused and traced", async () => {
		const fixture = createFixture();
		const savedCwd = process.cwd();
		// PM branch on purpose (no PI_WORKER_TASK at activate time, so no worker
		// allowlist/write-face can claim the block); the trace path is read at
		// block time, so the worker-task probe is armed after activation.
		delete process.env[ENV_WORKER_TASK];
		process.chdir(fixture.root);
		delete (globalThis as Record<string, unknown>)[ACTIVATION_FLAG];
		try {
			const executedBashCommands: string[] = [];
			const harness = await createHarness({
				tools: [
					createWriteTool(fixture.root),
					createBashTool(fixture.root, {
						operations: {
							exec: async (command, _cwd, options) => {
								executedBashCommands.push(command);
								options.onData(Buffer.from(`ran: ${command}`));
								return { exitCode: 0 };
							},
						},
					}),
					createReadTool(fixture.root),
				],
				// REAL registration surface: production `activate()`, nothing hand-wired.
				extensionFactories: [(pi) => activate(pi)],
			});
			harnesses.push(harness);
			process.env[ENV_WORKER_TASK] = fixture.taskPath;
			const signoffBefore = fs.readFileSync(fixture.signoff, "utf8");
			const bashCommand = `echo 'conclusion: revoke' > ${fixture.signoff}`;
			harness.setResponses([
				fauxAssistantMessage(
					[
						fauxToolCall("write", { path: fixture.signoff, content: "conclusion: revoke\n" }),
						fauxToolCall("bash", { command: bashCommand }),
					],
					{ stopReason: "toolUse" },
				),
				fauxAssistantMessage("refused"),
			]);

			await harness.session.prompt("sign my own release");

			const writes = toolResults(harness, "write");
			expect(writes).toHaveLength(1);
			expect(writes[0]?.isError).toBe(true);
			expect(toolResultText(writes[0] as ToolResultMessage)).toContain("decision-signoff-guard: blocked write");
			const bash = toolResults(harness, "bash");
			expect(bash).toHaveLength(1);
			expect(bash[0]?.isError).toBe(true);
			expect(toolResultText(bash[0] as ToolResultMessage)).toContain("decision-signoff-guard: blocked");
			expect(executedBashCommands).toEqual([]);
			expect(fs.readFileSync(fixture.signoff, "utf8")).toBe(signoffBefore);

			const trace = fixture.readTrace();
			const lines = traceLines(trace);
			expect(lines).toHaveLength(2);
			expect(trace).toContain("blocked tool=write");
			expect(trace).toContain("blocked tool=bash");
			expect(lines[0]).toContain(`target=${fixture.signoff}`);
		} finally {
			process.chdir(savedCwd);
			delete (globalThis as Record<string, unknown>)[ACTIVATION_FLAG];
		}
	});
});
