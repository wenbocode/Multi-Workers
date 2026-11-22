/**
 * T14 worker terminal -> PM recovery L2 slice.
 *
 * This suite uses the real AgentSession/extension runner and the production
 * worker terminal writer, PM terminal poll/readback channel and agent_settled
 * dispatcher. The faux provider decides to publish ONE successor card only
 * after the PM conversation actually contains the terminal output. No terminal
 * product, DP answer, sign-off or queue verdict under test is hand-written.
 * Queue status propagation uses WorkerStore.upsert at the launcher boundary and
 * reads the worker's real run.json status.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, expect, it, vi } from "vitest";
import { emitSessionShutdownEvent } from "../../src/core/extensions/runner.ts";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { type AgentTeamLoopComposition, activateWithRuntimeHost } from "../../src/extensions/agent-team-loop/index.ts";
import { ASK_DECISION_TOOL } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { SUBMIT_DECISION_HANDOFF_TOOL } from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import { startWorkerPollLoop } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	buildMatterBudgetFromCard,
	preflightReservation,
	readRuntimeStopFacts,
} from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import {
	cardWriteFaceEntries,
	ENVELOPE_PRODUCER_KEY,
	envelopeProducerIdentity,
	extractCardSections,
	renderWriteFaceLine,
	WATCH_ENTRY_TYPE,
	WRITE_FACE_CARD_SECTION,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { acquireLock } from "../../src/extensions/agent-team-loop/shared/file-lock.ts";
import { allocationFile } from "../../src/extensions/agent-team-loop/shared/fixed-child-budget.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { type WorkerStatus, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, type Harness } from "./harness.ts";

interface Fixture {
	root: string;
	doc: string;
	keyDir: string;
	keyName: string;
	claim: string;
	taskKey: string;
	taskDir: string;
	taskMdPath: string;
	cardPath: string;
	cardSha256: string;
	successorKey: string;
	successorDir: string;
	successorTaskMdPath: string;
	successorCardPath: string;
	writeFaceLine: string;
	terminalMarker: string;
}

interface ToolState {
	successorWrites: number;
	successorResults: Array<Record<string, unknown>>;
	busyHolds: number;
}

const ACTIVATION_FLAG = "__agentTeamLoopActivated";
const ORIGINAL_CWD = process.cwd();
const ORIGINAL_EXIT_CODE = process.exitCode;
const roots: string[] = [];
const harnesses: Harness[] = [];
const timers: NodeJS.Timeout[] = [];
const CONTROLLED_REL = "src/l2.txt";
const TERMINAL_MARKER = "upstream result is absent";
const BUDGET_MINUTES = 30;
const SOURCE_SEAMS = [
	"src/extensions/agent-team-loop/index.ts",
	"src/extensions/agent-team-loop/pm/decision-tool.ts",
	"src/extensions/agent-team-loop/pm/host-submit.ts",
	"src/extensions/agent-team-loop/pm/pm-orchestrator.ts",
	"src/extensions/agent-team-loop/pm/runtime-host-adapter.ts",
	"src/extensions/agent-team-loop/pm/ui-bridge.ts",
	"src/extensions/agent-team-loop/shared/ack-store.ts",
	"src/extensions/agent-team-loop/shared/implementation-gate.ts",
	"src/extensions/agent-team-loop/shared/index-store.ts",
	"src/extensions/agent-team-loop/shared/worker-store.ts",
	"src/extensions/agent-team-loop/worker/worker-mode.ts",
	"test/suite/harness.ts",
] as const;

function sourceHashManifest(): Record<string, string> {
	const out: Record<string, string> = {};
	for (const relative of SOURCE_SEAMS) {
		out[relative] = createHash("sha256")
			.update(fs.readFileSync(path.join(ORIGINAL_CWD, relative)))
			.digest("hex");
	}
	return out;
}

function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

function resetActivationFlag(): void {
	delete (globalThis as Record<string, unknown>)[ACTIVATION_FLAG];
}

function budgetBlock(cardRef: string, remaining: number): string {
	return [
		"## 事项预算事实",
		`- \`budget_ref\`: \`${cardRef}#事项预算事实\` + 卡 SHA`,
		cardRef === "tasks/T-worker.md" || cardRef === "tasks/T-exhausted.md"
			? "- `matter_ref`: `l2-worker-key/T-worker`；`parent_matter_ref`: `l2-worker-key`"
			: `- \`matter_ref\`: \`l2-worker-key/${cardRef}\``,
		`- \`deadline\`: \`run.json.started_at + ${BUDGET_MINUTES}m\``,
		"- `max_steps`: 8",
		"- `no_progress_limit`: 5",
		`- \`remaining_cost\`: ${remaining}，\`cost_consumed\` 与 \`steps_consumed\` 同单位（1 cost unit ≡ 1 tool call；卡明确约定）`,
		"- `steps_consumed`: 0",
		"- `cost_consumed`: 0",
		"- `no_progress_count`: 0",
		"- `source_refs`: 卡 SHA、`run.json`、`_index.parallel`、`task.md` 头",
		"",
	].join("\n");
}

function cardText(claim: string, title: string, cardRef: string, remaining: number): string {
	return [
		`# ${title}`,
		``,
		`type: coding`,
		`owning_pm_claim: ${claim}`,
		`title: ${title}`,
		``,
		budgetBlock(cardRef, remaining),
		`## ${WRITE_FACE_CARD_SECTION}`,
		``,
		`- \`${CONTROLLED_REL}\``,
		``,
		`## 写入禁止面`,
		``,
		`- 除上述唯一具体文件外的所有路径`,
		``,
	].join("\n");
}

function taskText(cardRel: string, cardSha: string, writeFaceLine: string, body: string): string {
	return [
		`type: coding`,
		`images: no`,
		`card_path: ${cardRel}`,
		`card_sha256: ${cardSha}`,
		`${ENVELOPE_PRODUCER_KEY}: ${envelopeProducerIdentity()}`,
		writeFaceLine,
		``,
		`# Isolated worker recovery slice`,
		``,
		body,
		``,
	].join("\n");
}

function fixture(): Fixture {
	const root = fs.realpathSync.native(fs.mkdtempSync(path.join(os.tmpdir(), "dp-continuity-worker-l2-")));
	roots.push(root);
	const doc = path.join(root, ".agenticdoc");
	const keyName = "l2-worker-key";
	const keyDir = path.join(doc, keyName);
	const claim = currentClaimId();
	const taskKey = "terminal-worker";
	const successorKey = "legal-successor";
	const taskDir = path.join(keyDir, "workers", taskKey);
	const successorDir = path.join(keyDir, "workers", successorKey);
	const cardPath = path.join(keyDir, "tasks", "T-worker.md");
	const successorCardPath = path.join(keyDir, "tasks", "T-successor.md");
	const cardBody = cardText(claim, "terminal worker", "tasks/T-worker.md", 8);
	const successorCardBody = cardText(claim, "legal successor", "tasks/T-successor.md", 8);
	const entries = cardWriteFaceEntries(extractCardSections(cardBody)) ?? [];
	const writeFaceLine = renderWriteFaceLine(entries);
	const cardSha256 = sha256(cardBody);
	for (const dir of [
		path.join(keyDir, "tasks"),
		path.join(keyDir, "evidence", "research"),
		taskDir,
		path.join(root, ".mw"),
		path.join(root, "src"),
	]) {
		fs.mkdirSync(dir, { recursive: true });
	}
	fs.writeFileSync(cardPath, cardBody);
	fs.writeFileSync(successorCardPath, successorCardBody);
	fs.writeFileSync(
		path.join(doc, "_index.parallel"),
		`# Index Parallel\n| ${keyName} | active | EXECUTE | ${claim} | | isolated worker L2 fixture | now |\n`,
	);
	fs.writeFileSync(path.join(doc, "target.yml"), "active: single\n");
	fs.writeFileSync(path.join(root, ".mw", "mw.pid"), String(process.pid));
	fs.writeFileSync(
		path.join(root, ".mw", "decide.json"),
		`${JSON.stringify({ enabled: false, signoff: "auto", points: {} }, null, 2)}\n`,
	);
	const disabledPoints = Object.fromEntries(
		[
			"dp-w-type",
			"dp-pm-steer",
			"dp-w-check-task",
			"dp-QG",
			"dp-gate-approve",
			"dp-sign-key",
			"dp-auto",
			"dp-route",
		].map((dp) => [dp, { tier: "P2", enabled: false, mode: "auto", note: "" }]),
	);
	fs.writeFileSync(
		path.join(root, ".mw", "decide-points.json"),
		`${JSON.stringify({ version: 1, points: disabledPoints }, null, 2)}\n`,
	);
	fs.writeFileSync(path.join(root, ".mw", "dispatch.yml"), "models:\n  coding: faux/faux\n");
	fs.writeFileSync(path.join(keyDir, "pm-state.md"), `- Phase: init\n- ClaimId: ${claim}\n`);
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Isolated L2 spec\n\nAC-001: one real terminal result is consumed and one legal successor starts.\n\n${"x".repeat(600)}\n`,
	);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Isolated L2 design\n\n${"x".repeat(600)}\n`);
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "spec-note.md"), "spec research note\n");
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "design-note.md"), "design research note\n");
	fs.writeFileSync(path.join(root, CONTROLLED_REL), "initial\n");
	const taskMdPath = path.join(taskDir, "task.md");
	const deadline = new Date(Date.now() + BUDGET_MINUTES * 60_000).toISOString();
	const file = allocationFile(taskDir);
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(
		file,
		JSON.stringify({ task: taskKey, card: "tasks/T-worker.md", pin: cardSha256, steps: 8, deadline }),
		{ flag: "wx" },
	);
	fs.writeFileSync(
		taskMdPath,
		`fixed_child_steps: 8\nfixed_child_deadline: ${deadline}\n` +
			taskText(
				"tasks/T-worker.md",
				cardSha256,
				writeFaceLine,
				"Bounded worker-local terminate; PM must recover one successor.",
			),
	);
	return {
		root,
		doc,
		keyDir,
		keyName,
		claim,
		taskKey,
		taskDir,
		taskMdPath,
		cardPath,
		cardSha256,
		successorKey,
		successorDir,
		successorTaskMdPath: path.join(successorDir, "task.md"),
		successorCardPath,
		writeFaceLine,
		terminalMarker: TERMINAL_MARKER,
	};
}

async function queueRow(f: Fixture, taskKey: string, taskPath: string, status: WorkerStatus): Promise<void> {
	await new WorkerStore(f.doc).upsert({
		taskKey,
		status,
		cli: "pi",
		provider: "timi",
		taskPath,
		dispatchedAt: new Date().toISOString(),
		updatedAt: new Date().toISOString(),
		model: "",
	});
}

function registerTestTools(pi: ExtensionAPI, f: Fixture, state: ToolState): void {
	pi.registerTool({
		name: "queue_successor",
		label: "queue_successor",
		description: "Publish one successor task card at the explicit dispatcher boundary",
		parameters: Type.Object({ task_key: Type.String(), trigger: Type.String() }),
		execute: async (toolCallId, params) => {
			const parentBinding = `parent_worker_run: ${String(readRun(f).run_id)}\n`;
			const card = parentBinding + cardText(f.claim, "legal successor", "tasks/T-successor.md", 8);
			fs.writeFileSync(f.successorCardPath, card);
			fs.mkdirSync(f.successorDir, { recursive: true });
			const text =
				parentBinding +
				taskText(
					"tasks/T-successor.md",
					sha256(card),
					f.writeFaceLine,
					`Successor for ${f.taskKey}; trigger=${params.trigger}. One bounded recovery action.`,
				);
			fs.writeFileSync(f.successorTaskMdPath, text);
			const result = {
				tool_call_id: toolCallId,
				task_key: params.task_key,
				trigger: params.trigger,
				task_path: f.successorTaskMdPath,
				sha256: sha256(text),
			};
			state.successorWrites += 1;
			state.successorResults.push(result);
			return { content: [{ type: "text" as const, text: `published ${params.task_key}` }], details: result };
		},
	});
	pi.registerTool({
		name: "hold_busy",
		label: "hold_busy",
		description: "Keep the PM turn streaming while the real terminal result arrives",
		parameters: Type.Object({ ms: Type.Number() }),
		execute: async (toolCallId, params) => {
			state.busyHolds += 1;
			await new Promise((resolve) => setTimeout(resolve, Math.min(Math.max(params.ms, 1), 500)));
			return {
				content: [{ type: "text" as const, text: `held ${params.ms}ms` }],
				details: { tool_call_id: toolCallId, held_ms: params.ms },
			};
		},
	});
}

function offerId(h: Harness): string | undefined {
	const blob = JSON.stringify(h.session.messages);
	const match = /offer:([0-9a-f]{40,})/.exec(blob);
	return match?.[1] === undefined ? undefined : `offer:${match[1]}`;
}

async function produceWorkerTerminal(
	f: Fixture,
	stop?: "parent-cancel" | "worker-deadline",
): Promise<{ run: Record<string, unknown>; output: string }> {
	process.chdir(f.root);
	resetActivationFlag();
	process.env.PI_WORKER_TASK = f.taskMdPath;
	if (stop === "worker-deadline") {
		vi.stubEnv("PI_WORKER_TIMEOUT_MS", "250");
		vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
	}
	const worker = await createHarness({
		initialActiveToolNames: [ASK_DECISION_TOOL, SUBMIT_DECISION_HANDOFF_TOOL],
		extensionFactories: [
			async (pi) => {
				await activateWithRuntimeHost(pi);
			},
		],
	});
	harnesses.push(worker);
	await worker.session.bindExtensions({});
	const askArgs = {
		dp: "dp-w-check-task",
		trigger: f.taskKey,
		key: f.keyName,
		task_key: f.taskKey,
		note: "Isolated worker recovery L2: DP offline, finite budget, truthful terminate, no QG or sign claim.",
		material: {
			task_goal: "Bounded worker-local terminate; PM must recover one successor.",
			reachability_facts: `Read evidence.txt: ${TERMINAL_MARKER}`,
			completed: "Read the bounded evidence source",
			remaining: "Successor recovery belongs to the PM",
			blockers: TERMINAL_MARKER,
			constraints: "Same parent matter budget, original deadline and existing claim only",
		},
		preparation: {
			prepared_at: new Date().toISOString(),
			basis_catalog: [
				{
					id: "basis",
					text: "The bounded evidence read proves this worker cannot finish",
					material_refs: ["reachability_facts"],
					applies_to: ["terminate"],
				},
			],
		},
	};
	worker.setResponses(
		stop === "parent-cancel"
			? [fauxAssistantMessage("Parent cancelled", { stopReason: "aborted" })]
			: [
					fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, askArgs)], { stopReason: "toolUse" }),
					() => {
						const offer = offerId(worker);
						if (offer === undefined) return fauxAssistantMessage("No submittable offer; terminal not produced");
						return fauxAssistantMessage(
							[
								fauxToolCall(SUBMIT_DECISION_HANDOFF_TOOL, {
									offer_id: offer,
									choice: "terminate",
									basis_id: "basis",
								}),
							],
							{ stopReason: "toolUse" },
						);
					},
					fauxAssistantMessage("Worker terminal: upstream result is absent; PM recovery required."),
				],
	);
	if (stop === "worker-deadline")
		await waitFor("real watchdog terminal", () => (readRun(f).status === "failed" ? true : undefined));
	else await worker.session.prompt("Produce a truthful worker terminal");
	const run = JSON.parse(fs.readFileSync(path.join(f.taskDir, "run.json"), "utf8")) as Record<string, unknown>;
	const output = fs.readFileSync(path.join(f.taskDir, "output.md"), "utf8");
	return { run, output };
}

function readRun(f: Fixture): Record<string, unknown> {
	return JSON.parse(fs.readFileSync(path.join(f.taskDir, "run.json"), "utf8")) as Record<string, unknown>;
}

async function propagateTerminalQueue(f: Fixture): Promise<void> {
	const run = readRun(f);
	const status = run.status;
	if (status !== "failed" && status !== "done" && status !== "needs-clarification" && status !== "lost")
		throw new Error(`worker run is not terminal: ${String(status)}`);
	const store = new WorkerStore(f.doc);
	const entry = store.findByKey(f.taskKey);
	if (entry === undefined) throw new Error("terminal worker queue row is missing");
	await store.upsert({ ...entry, status: status as WorkerStatus, updatedAt: new Date().toISOString() });
}

async function waitFor<T>(label: string, read: () => T | undefined, timeoutMs = 4000): Promise<T> {
	const until = Date.now() + timeoutMs;
	let value = read();
	while (value === undefined && Date.now() < until) {
		await new Promise((resolve) => setTimeout(resolve, 20));
		value = read();
	}
	if (value === undefined) throw new Error(`timed out waiting for ${label}`);
	return value;
}

interface PmComposition {
	pm: Harness;
	pmPi: ExtensionAPI;
	composition: AgentTeamLoopComposition;
}

async function composePm(f: Fixture, state: ToolState): Promise<PmComposition> {
	// The enclosing worker process exports PI_WORKER_TASK for this actual card.
	// Remove it before composing the PM window: the production composition uses
	// that env to choose worker mode, and a leaked value is not a PM result seam.
	delete process.env.PI_WORKER_TASK;
	resetActivationFlag();
	let pmPi: ExtensionAPI | undefined;
	let composition: AgentTeamLoopComposition | undefined;
	const pm = await createHarness({
		initialActiveToolNames: ["queue_successor", "hold_busy"],
		extensionFactories: [
			async (pi) => {
				pmPi = pi;
				composition = await activateWithRuntimeHost(pi);
				registerTestTools(pi, f, state);
			},
		],
	});
	harnesses.push(pm);
	pm.sessionManager.appendCustomEntry(WATCH_ENTRY_TYPE, { key: f.keyName, claimed: false });
	await pm.session.bindExtensions({});
	if (pmPi === undefined || composition === undefined) throw new Error("PM production composition missing");
	return { pm, pmPi, composition };
}

function startPmPollLoop(f: Fixture, pmPi: ExtensionAPI): NodeJS.Timeout {
	const timer = startWorkerPollLoop(
		pmPi,
		new WorkerStore(f.doc),
		new AckStore(f.doc),
		new IndexStore(f.doc),
		f.doc,
		{ key: f.keyName },
		{ ctx: undefined },
		20,
	);
	timers.push(timer);
	return timer;
}

function exhaustedCardText(claim: string, cardRef: string): string {
	return cardText(claim, "exhausted parent budget", cardRef, 0)
		.replace("`steps_consumed`: 0", "`steps_consumed`: 8")
		.replace("`cost_consumed`: 0", "`cost_consumed`: 8");
}

function terminalMessageCount(h: Harness): number {
	return h.session.messages.filter(
		(message) => message.role === "custom" && JSON.stringify(message.content).includes(TERMINAL_MARKER),
	).length;
}

function toolResultText(h: Harness, name: string): string {
	const message = [...h.session.messages]
		.reverse()
		.find((item) => item.role === "toolResult" && item.toolName === name);
	if (message === undefined || message.role !== "toolResult") return "";
	if (typeof message.content === "string") return message.content;
	if (!Array.isArray(message.content)) return "";
	return message.content
		.filter(
			(part): part is { type: "text"; text: string } =>
				part !== null &&
				typeof part === "object" &&
				"type" in part &&
				part.type === "text" &&
				"text" in part &&
				typeof part.text === "string",
		)
		.map((part) => part.text)
		.join("\n");
}

afterEach(async () => {
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	for (const timer of timers.splice(0)) clearInterval(timer);
	delete process.env.PI_WORKER_TASK;
	process.chdir(ORIGINAL_CWD);
	process.exitCode = ORIGINAL_EXIT_CODE;
	resetActivationFlag();
	for (const h of harnesses.splice(0)) {
		await emitSessionShutdownEvent(h.session.extensionRunner, { type: "session_shutdown", reason: "quit" });
		h.cleanup();
	}
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

it("idle PM consumes a real worker terminal once, queues one successor and suppresses the duplicate", async () => {
	const f = fixture();
	console.log(`[VERIFY] worker-l2 imported seams: ${JSON.stringify(sourceHashManifest())}`);
	process.chdir(f.root);
	await queueRow(f, f.taskKey, f.taskMdPath, "running");
	const state: ToolState = { successorWrites: 0, successorResults: [], busyHolds: 0 };
	const { pm, pmPi, composition } = await composePm(f, state);
	const sendSpy = vi.spyOn(pm.session, "sendCustomMessage");

	pm.setResponses([
		(context) => {
			const blob = JSON.stringify([context.messages, pm.session.messages]);
			if (!blob.includes(TERMINAL_MARKER))
				return fauxAssistantMessage("No terminal result was consumed; successor not published");
			return fauxAssistantMessage(
				[fauxToolCall("queue_successor", { task_key: f.successorKey, trigger: "idle-terminal" })],
				{ stopReason: "toolUse" },
			);
		},
		fauxAssistantMessage("One successor published after the terminal readback."),
	]);

	startPmPollLoop(f, pmPi);

	const terminal = await produceWorkerTerminal(f);
	expect(terminal.run.status).toBe("failed");
	expect(terminal.run.exit).toBe(1);
	expect(terminal.output).toContain(TERMINAL_MARKER);
	await propagateTerminalQueue(f);

	const delivered = await waitFor("PM terminal custom message", () => {
		const seen = sendSpy.mock.calls.filter((call) => JSON.stringify(call[0]).includes(TERMINAL_MARKER));
		return seen.length > 0 ? seen : undefined;
	});
	console.log(
		`[VERIFY] worker-l2 idle diagnostic: deliveries=${delivered.length} ` +
			`trigger_turn=${delivered.filter((call) => JSON.stringify(call[1]).includes('"triggerTurn":true')).length} ` +
			`custom_type=${delivered.filter((call) => JSON.stringify(call[0]).includes("agent-team-loop:worker-summary")).length} ` +
			`tools=${state.successorWrites} queue_rows=${new WorkerStore(f.doc).readAll().length}`,
	);
	const successorRow = await waitFor("successor queue row", () => new WorkerStore(f.doc).findByKey(f.successorKey));
	expect(state.successorWrites).toBe(1);
	expect(toolResultText(pm, "queue_successor")).toContain(f.successorKey);
	expect(terminalMessageCount(pm)).toBeGreaterThanOrEqual(1);
	expect(successorRow.status).toBe("pending");
	expect(composition.host.countsSnapshot().registered).toBeGreaterThanOrEqual(1);

	// Repeat the same terminal queue fact. The production notified set must not
	// deliver a second result or publish a second successor.
	const store = new WorkerStore(f.doc);
	const terminalRow = store.findByKey(f.taskKey);
	if (terminalRow === undefined) throw new Error("terminal row disappeared");
	await store.upsert({ ...terminalRow, status: terminalRow.status, updatedAt: new Date().toISOString() });
	await new Promise((resolve) => setTimeout(resolve, 120));
	const duplicateRows = store.readAll().filter((row) => row.taskKey === f.successorKey);
	const terminalDeliveries = sendSpy.mock.calls.filter((call) => JSON.stringify(call[0]).includes(TERMINAL_MARKER));
	expect(terminalDeliveries).toHaveLength(1);
	expect(duplicateRows).toHaveLength(1);
	expect(state.successorWrites).toBe(1);

	// Start the queued successor through the real worker activation seam in this
	// in-process harness. No OS subprocess dispatch is claimed here.
	resetActivationFlag();
	process.env.PI_WORKER_TASK = f.successorTaskMdPath;
	const successor = await createHarness({
		extensionFactories: [
			async (pi) => {
				await activateWithRuntimeHost(pi);
			},
		],
	});
	harnesses.push(successor);
	await successor.session.bindExtensions({});
	const started = JSON.parse(fs.readFileSync(path.join(f.successorDir, "run.json"), "utf8")) as Record<
		string,
		unknown
	>;
	expect(started.status).toBe("running");
	expect(started.task_key).toBe(f.successorKey);

	console.log(
		`[VERIFY] worker-l2 idle: terminal=${String(terminal.run.status)}/${String(terminal.run.exit)} ` +
			`readback=${terminalDeliveries.length} successor_writes=${state.successorWrites} ` +
			`successor_rows=${duplicateRows.length} registered=${composition.host.countsSnapshot().registered} ` +
			`successor_run=${String(started.status)} os_subprocess_dispatch=0`,
	);
});

it("busy PM steers a real terminal readback into the active turn and queues one successor", async () => {
	const f = fixture();
	process.chdir(f.root);
	await queueRow(f, f.taskKey, f.taskMdPath, "running");
	const state: ToolState = { successorWrites: 0, successorResults: [], busyHolds: 0 };
	const { pm, pmPi, composition } = await composePm(f, state);
	const sendSpy = vi.spyOn(pm.session, "sendCustomMessage");
	pm.setResponses([
		fauxAssistantMessage([fauxToolCall("hold_busy", { ms: 150 })], { stopReason: "toolUse" }),
		(context) => {
			const blob = JSON.stringify([context.messages, pm.session.messages]);
			if (!blob.includes(TERMINAL_MARKER))
				return fauxAssistantMessage("No steered terminal result; successor not published");
			return fauxAssistantMessage(
				[fauxToolCall("queue_successor", { task_key: f.successorKey, trigger: "busy-terminal" })],
				{ stopReason: "toolUse" },
			);
		},
		fauxAssistantMessage("Busy turn consumed the terminal and published one successor."),
	]);
	startPmPollLoop(f, pmPi);

	const terminal = await produceWorkerTerminal(f);
	expect(terminal.run.status).toBe("failed");
	expect(terminal.output).toContain(TERMINAL_MARKER);
	// The queue transition happens while hold_busy keeps this PM turn streaming.
	const propagation = new Promise<void>((resolve, reject) => {
		const handle = setTimeout(() => {
			void propagateTerminalQueue(f).then(resolve, reject);
		}, 20);
		timers.push(handle);
	});
	await pm.session.prompt("Hold while the worker terminal result arrives");
	await propagation;

	const delivered = await waitFor("busy PM terminal custom message", () => {
		const seen = sendSpy.mock.calls.filter((call) => JSON.stringify(call[0]).includes(TERMINAL_MARKER));
		return seen.length > 0 ? seen : undefined;
	});
	const successorRow = await waitFor("busy successor queue row", () =>
		new WorkerStore(f.doc).findByKey(f.successorKey),
	);
	expect(state.busyHolds).toBe(1);
	expect(delivered).toHaveLength(1);
	expect(JSON.stringify(delivered[0]?.[1])).toContain('"triggerTurn":true');
	expect(state.successorWrites).toBe(1);
	expect(toolResultText(pm, "queue_successor")).toContain(f.successorKey);
	expect(successorRow.status).toBe("pending");
	expect(composition.host.countsSnapshot().registered).toBeGreaterThanOrEqual(1);

	const store = new WorkerStore(f.doc);
	const terminalRow = store.findByKey(f.taskKey);
	if (terminalRow === undefined) throw new Error("busy terminal row disappeared");
	await store.upsert({ ...terminalRow, status: terminalRow.status, updatedAt: new Date().toISOString() });
	await new Promise((resolve) => setTimeout(resolve, 120));
	const terminalDeliveries = sendSpy.mock.calls.filter((call) => JSON.stringify(call[0]).includes(TERMINAL_MARKER));
	expect(terminalDeliveries).toHaveLength(1);
	expect(store.readAll().filter((row) => row.taskKey === f.successorKey)).toHaveLength(1);
	expect(state.successorWrites).toBe(1);
	console.log(
		`[VERIFY] worker-l2 busy: hold=${state.busyHolds} readback=${terminalDeliveries.length} ` +
			`successor_writes=${state.successorWrites} registered=${composition.host.countsSnapshot().registered} ` +
			`os_subprocess_dispatch=0`,
	);
});

it("repeated scans of an unfunded orphan wake the PM once and leave the queue empty", async () => {
	const f = fixture();
	fs.unlinkSync(allocationFile(f.taskDir));
	process.chdir(f.root);
	const { pm } = await composePm(f, { successorWrites: 0, successorResults: [], busyHolds: 0 });
	const alerts = vi.spyOn(pm.session, "sendCustomMessage");
	pm.setResponses([fauxAssistantMessage("Observed the dispatch refusal.")]);
	const ledger = path.join(f.doc, "_autopilot", "auto-decisions.jsonl");
	for (let scan = 1; scan <= 2; scan++) {
		await pm.session.extensionRunner.emit({ type: "agent_settled" });
		await vi.waitFor(() => {
			const refusals = fs
				.readFileSync(ledger, "utf8")
				.split("\n")
				.filter((line) => line.includes("fixed-child-recovery"));
			expect(refusals.length).toBeGreaterThanOrEqual(scan);
		});
	}
	expect(alerts.mock.calls.filter((call) => JSON.stringify(call[0]).includes("fixed-child-recovery"))).toHaveLength(1);
	expect(new WorkerStore(f.doc).findByKey(f.taskKey)).toBeUndefined();
});

it("a changed wrapper/trigger does not refresh an exhausted parent budget", () => {
	const f = fixture();
	const cardRef = "tasks/T-exhausted.md";
	const cardBody = exhaustedCardText(f.claim, cardRef);
	const cardSha256 = sha256(cardBody);
	fs.writeFileSync(path.join(f.keyDir, "tasks", "T-exhausted.md"), cardBody);
	const wrappers = ["original-trigger", "changed-trigger"];
	const runStartedAt = new Date().toISOString();
	const budgets = wrappers.map((trigger, index) => {
		const wrapperDir = path.join(f.root, "wrappers", `w${index}`);
		fs.mkdirSync(wrapperDir, { recursive: true });
		const wrapperPath = path.join(wrapperDir, "task.md");
		fs.writeFileSync(wrapperPath, `trigger: ${trigger}\nwrapper: ${trigger}\n`);
		const read = buildMatterBudgetFromCard(cardBody, {
			cardRef,
			cardSha256,
			runStartedAt,
			runRef: path.relative(f.root, wrapperPath).replaceAll("\\", "/"),
			indexRef: "_index.parallel",
		});
		if (!read.ok) throw new Error(`budget read failed for ${trigger}: ${read.reason}`);
		return { trigger, budget: read.value.budget };
	});
	const [first, second] = budgets;
	if (first === undefined || second === undefined) throw new Error("missing wrapper budgets");
	expect(first.trigger).not.toBe(second.trigger);
	expect(second.budget.deadline).toBe(first.budget.deadline);
	expect(second.budget.max_steps).toBe(first.budget.max_steps);
	expect(second.budget.remaining_cost).toBe(first.budget.remaining_cost);
	expect(second.budget.steps_consumed).toBe(first.budget.steps_consumed);
	expect(second.budget.cost_consumed).toBe(first.budget.cost_consumed);
	expect(second.budget.no_progress_count).toBe(first.budget.no_progress_count);
	const nowMs = Date.parse(runStartedAt) + 1000;
	for (const wrapper of budgets) {
		const preflight = preflightReservation(wrapper.budget, nowMs);
		if (!preflight.ok) throw new Error(`preflight failed for ${wrapper.trigger}: ${preflight.reason}`);
		expect(preflight.value.granted).toBe(false);
		expect(preflight.value.reason).toBe("budget-exhausted");
	}
	console.log(
		`[VERIFY] worker-l2 budget: wrappers=${wrappers.length} deadline=${first.budget.deadline} ` +
			`remaining=${first.budget.remaining_cost} steps=${first.budget.steps_consumed}/${first.budget.max_steps} ` +
			`preflight=budget-exhausted`,
	);
});

it.each(["parent-cancel", "worker-deadline"] as const)(
	"a real %s forbids direct and automatic linked dispatch",
	async (stop) => {
		const f = fixture();
		process.chdir(f.root);
		const state: ToolState = { successorWrites: 0, successorResults: [], busyHolds: 0 };
		const { pm } = await composePm(f, state);
		const terminal = await produceWorkerTerminal(f, stop);
		expect(terminal.run).toMatchObject({
			status: "failed",
			exit: 1,
			...(stop === "parent-cancel" ? { aborted: true } : { stop_kind: stop }),
		});
		await queueRow(f, f.taskKey, f.taskMdPath, "failed");
		const stopFacts = readRuntimeStopFacts({
			agenticdocRoot: f.doc,
			key: f.keyName,
			taskKey: f.taskKey,
			runId: String(terminal.run.run_id),
		});
		expect(stopFacts.gaps).toEqual([]);
		expect(stopFacts.stop_signals.some((signal) => signal.kind === stop)).toBe(true);

		const parentBinding = `parent_worker_run: ${String(terminal.run.run_id)}\n`;
		const explicitCard = path.join(f.keyDir, "tasks", "T-public-successor.md");
		fs.writeFileSync(
			explicitCard,
			[
				parentBinding.trimEnd(),
				"type: review",
				"",
				"# Review successor",
				"",
				"## 上下文",
				"Read `.agenticdoc/goal.md` and `src/l2.txt:1`.",
				"## 要求",
				"Review the outcome of the bound parent.",
				"## 交付格式",
				"Write report.md in the assigned task directory.",
				"## 审计目标",
				"Verify the actual terminal state.",
				"## 未覆盖面声明",
				"Only the isolated parent is covered.",
				"",
			].join("\n"),
		);
		const explicitTask = "explicit-successor";
		pm.session.setActiveToolsByName(["dispatch_worker"]);
		pm.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("dispatch_worker", {
						task_key: explicitTask,
						key: f.keyName,
						type: "review",
						card_path: explicitCard,
						description: "Review the outcome of the bound parent.",
						images: "no",
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("The dispatch result was recorded."),
		]);
		await pm.session.prompt("Check direct dispatch after parent cancellation");
		expect(toolResultText(pm, "dispatch_worker")).toContain(`${stop}: ${String(terminal.run.run_id)}`);
		expect(fs.existsSync(path.join(f.keyDir, "workers", explicitTask))).toBe(false);
		expect(new WorkerStore(f.doc).findByKey(explicitTask)).toBeUndefined();
		const stopCard = path.join(f.keyDir, "tasks", "T-user-stop.md");
		fs.writeFileSync(stopCard, fs.readFileSync(explicitCard, "utf8").slice(parentBinding.length));
		const stoppedTask = "stopped-before-queue";
		const workerStore = new WorkerStore(f.doc);
		const unlock = await acquireLock(workerStore.lockFilePath);
		let dispatch: Promise<void> | undefined;
		let aborted: Promise<void> | undefined;
		try {
			const previousStarts = pm.eventsOfType("tool_execution_start").length;
			pm.setResponses([
				fauxAssistantMessage(
					[
						fauxToolCall("dispatch_worker", {
							task_key: stoppedTask,
							key: f.keyName,
							type: "review",
							card_path: stopCard,
							description: "Review an independent bounded result.",
							images: "no",
						}),
					],
					{ stopReason: "toolUse" },
				),
			]);
			dispatch = pm.session.prompt("Cancel this direct dispatch while it waits for the queue lock");
			await vi.waitFor(() => expect(pm.eventsOfType("tool_execution_start")).toHaveLength(previousStarts + 1));
			aborted = pm.session.abort();
		} finally {
			unlock();
			await aborted;
			await dispatch;
		}
		expect(workerStore.findByKey(stoppedTask)).toBeUndefined();
		expect(fs.existsSync(path.join(f.keyDir, "workers", stoppedTask))).toBe(false);

		const boundCard = parentBinding + fs.readFileSync(f.successorCardPath, "utf8");
		fs.writeFileSync(f.successorCardPath, boundCard);
		fs.mkdirSync(f.successorDir, { recursive: true });
		fs.writeFileSync(
			f.successorTaskMdPath,
			parentBinding +
				taskText(
					"tasks/T-successor.md",
					sha256(boundCard),
					f.writeFaceLine,
					"This successor must not be queued while parent-cancel is active.",
				),
		);
		const independentKey = "independent-work";
		const independentPath = path.join(f.keyDir, "workers", independentKey, "task.md");
		const independentCardPath = path.join(f.keyDir, "tasks", "T-independent.md");
		const independentCard = cardText(f.claim, "Independent work", "tasks/T-independent.md", 8);
		fs.writeFileSync(independentCardPath, independentCard);
		fs.mkdirSync(path.dirname(independentPath), { recursive: true });
		fs.writeFileSync(
			independentPath,
			taskText(
				"tasks/T-independent.md",
				sha256(independentCard),
				f.writeFaceLine,
				"This action is independent of the stopped run.",
			),
		);
		await pm.session.extensionRunner.emit({ type: "agent_settled" });
		const store = new WorkerStore(f.doc);
		const independent = await waitFor("independent same-key queue row", () => store.findByKey(independentKey));
		expect(independent.status).toBe("pending");
		const stopScopeRow = store.findByKey(f.successorKey);
		console.log(
			`[VERIFY] worker-l2 stop gap: stop_signals=${JSON.stringify(stopFacts.stop_signals)} ` +
				`successor_row=${stopScopeRow === undefined ? "none" : stopScopeRow.status} independent_row=${independent.status}`,
		);
		expect(stopScopeRow, "PM production dispatcher queued a successor despite the bound run's stop").toBeUndefined();
	},
);
