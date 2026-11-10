import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import {
	type AssistantMessage,
	type Context,
	fauxAssistantMessage,
	fauxToolCall,
	type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import { streamSimple as streamFaux } from "@earendil-works/pi-ai/compat";
import { Type } from "typebox";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentSessionRuntime } from "../../src/core/agent-session-runtime.ts";
import { SUMMARIZATION_SYSTEM_PROMPT } from "../../src/core/compaction/utils.ts";
import { computeContextBudget, estimateContext } from "../../src/extensions/agent-team-loop/shared/context-budget.ts";
import { registerContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-extension.ts";
import { resolveContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-policy.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { runPrintMode } from "../../src/modes/print-mode.ts";
import { runRpcMode } from "../../src/modes/rpc/rpc-mode.ts";
import { createHarness, type Harness } from "../suite/harness.ts";

const io = vi.hoisted(() => ({
	lines: [] as string[],
	onLine: undefined as ((line: string) => void) | undefined,
}));
vi.mock("../../src/core/output-guard.ts", () => ({
	flushRawStdout: async () => {},
	takeOverStdout: () => {},
	waitForRawStdoutBackpressure: async () => {},
	writeRawStdout: (text: string) => io.lines.push(text),
}));
vi.mock("../../src/modes/rpc/jsonl.ts", () => ({
	attachJsonlLineReader: (_stream: NodeJS.ReadableStream, onLine: (line: string) => void) => {
		io.onLine = onLine;
		return () => {
			io.onLine = undefined;
		};
	},
	serializeJsonLine: (value: unknown) => `${JSON.stringify(value)}\n`,
}));

let root: string;
let exitListeners: Set<NodeJS.ExitListener>;
let stdinEndListeners: Set<unknown>;
const harnesses: Harness[] = [];
const runtimes: AgentSessionRuntime[] = [];
const signalListeners = new Map<NodeJS.Signals, Set<unknown>>();
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-native-lifecycle-"));
	exitListeners = new Set(process.listeners("exit"));
	stdinEndListeners = new Set(process.stdin.listeners("end"));
	for (const signal of ["SIGTERM", "SIGHUP"] as const) signalListeners.set(signal, new Set(process.listeners(signal)));
	vi.stubEnv("PI_WORKER_TASK", "");
	vi.stubEnv("MW_RAG_SERVERS_FILE", path.join(root, "no-rag.yml"));
	vi.stubEnv("MW_CONCURRENCY_DIR", path.join(root, "slots"));
	io.lines = [];
	io.onLine = undefined;
});
afterEach(async () => {
	for (const h of harnesses) if (h.session.isStreaming) await h.session.abort();
	while (runtimes.length) await runtimes.pop()?.dispose();
	while (harnesses.length) harnesses.pop()?.cleanup();
	for (const listener of process.listeners("exit"))
		if (!exitListeners.has(listener)) process.removeListener("exit", listener);
	for (const listener of process.stdin.listeners("end"))
		if (!stdinEndListeners.has(listener)) process.stdin.removeListener("end", listener as () => void);
	for (const [signal, previous] of signalListeners) {
		for (const listener of process.listeners(signal))
			if (!previous.has(listener)) process.removeListener(signal, listener as NodeJS.SignalsListener);
	}
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	fs.rmSync(root, { recursive: true, force: true });
});

function deferred() {
	let resolve = () => {};
	const promise = new Promise<void>((done) => {
		resolve = done;
	});
	return { promise, resolve };
}

function records(): Array<Record<string, unknown>> {
	return io.lines
		.flatMap((line) => line.split("\n"))
		.filter((line) => line.trim())
		.map((line) => JSON.parse(line) as Record<string, unknown>);
}

async function nativeHarness(worker = false, phases = false) {
	const taskDir = path.join(root, ".agenticdoc", "native-key", "workers", "native-task");
	fs.mkdirSync(taskDir, { recursive: true });
	const taskFile = path.join(taskDir, "task.md");
	fs.writeFileSync(
		taskFile,
		`type: coding\n\nComplete the assigned task using retained results.\n${phases ? "\n- name: implement\n  prompt: |\n    Complete the implementation phase using retained tool results.\n" : ""}`,
	);
	if (worker) vi.stubEnv("PI_WORKER_TASK", taskFile);
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(
		path.join(root, ".mw", "context.json"),
		JSON.stringify({ version: 1, defaults: { maxTokens: 65000, compaction: { enabled: true, triggerRatio: 0.6 } } }),
	);
	const effects = new Map<string, number>();
	// A worker-allowlisted faux tool has a durable side effect so any replay is observable.
	const tool: AgentTool = {
		name: "read",
		label: "read",
		description: "Read a fixture and record one irreversible fixture operation",
		parameters: Type.Object({ path: Type.String() }),
		execute: async (_toolCallId, args) => {
			const target = (args as { path: string }).path;
			const count = (effects.get(target) ?? 0) + 1;
			effects.set(target, count);
			fs.appendFileSync(path.join(root, "side-effects.log"), `${target}\n`);
			expect(count).toBe(1);
			await delay(target.endsWith("one") ? 12 : 1);
			return { content: [{ type: "text", text: `finished ${target}\n${"x".repeat(30000)}` }], details: undefined };
		},
	};
	let settledCompleted = false;
	const h = await createHarness({
		models: [{ id: "native-lifecycle", contextWindow: 100000, maxTokens: 32000 }],
		tools: [tool],
		settings: {
			retry: { enabled: false },
			compaction: { enabled: false, keepRecentTokens: 1, reserveTokens: 16384 },
		},
		extensionFactories: [
			async (pi) => {
				registerContextPolicy(pi, {
					controlRoot: root,
					homeDir: path.join(root, "home"),
					taskFile: worker ? taskFile : undefined,
				});
				if (worker) await workerModeActivate(pi);
				pi.on("agent_settled", async () => {
					await delay(15);
					settledCompleted = true;
				});
			},
		],
	});
	harnesses.push(h);
	const selected = h.getModel();
	h.session.modelRuntime.registerNativeProvider({
		id: selected.provider,
		name: "Lifecycle faux provider",
		getModels: () => h.models,
		auth: { apiKey: { name: "Fixture", resolve: async () => ({ auth: { apiKey: "faux-key" } }) } },
		stream: streamFaux,
		streamSimple: streamFaux,
	});
	h.session.agent.streamFunction = h.session.modelRuntime.streamSimple.bind(h.session.modelRuntime);
	h.sessionManager.appendMessage({ role: "user", content: "Existing task and write restrictions", timestamp: 1 });
	h.sessionManager.appendMessage(fauxAssistantMessage("old verified work ".repeat(600)));
	h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
	const runtime = new AgentSessionRuntime(
		h.session,
		{
			cwd: h.tempDir,
			agentDir: h.tempDir,
			modelRuntime: h.session.modelRuntime,
			settingsManager: h.settingsManager,
			resourceLoader: h.session.resourceLoader,
			diagnostics: [],
		},
		async () => {
			throw new Error("No runtime replacement in lifecycle fixture");
		},
	);
	runtimes.push(runtime);
	return { h, runtime, taskDir, effects, settledCompleted: () => settledCompleted };
}

function cycleScript(
	fixture: Awaited<ReturnType<typeof nativeHarness>>,
	summaries: { count: number },
	onSummary?: () => void,
	bootstrap = false,
) {
	let business = 0;
	const requests: Context[] = [];
	const respond = (context: Context, options?: SimpleStreamOptions): AssistantMessage => {
		if (context.systemPrompt === SUMMARIZATION_SYSTEM_PROMPT) {
			summaries.count++;
			expect(options?.maxTokens).toBeGreaterThan(4096);
			onSummary?.();
			return fauxAssistantMessage(
				`Native text summary ${summaries.count}: preserve task restrictions and completed tool results.`,
			);
		}
		const budget = computeContextBudget(
			fixture.h.getModel(),
			resolveContextPolicy({ controlRoot: root, homeDir: path.join(root, "home") }),
		);
		expect(estimateContext(context).estimatedTokens).toBeLessThanOrEqual(budget.inputBudget);
		const toolIds = context.messages.flatMap((message) =>
			message.role === "assistant"
				? message.content.filter((part) => part.type === "toolCall").map((part) => part.id)
				: [],
		);
		for (const message of context.messages)
			if (message.role === "toolResult") expect(toolIds).toContain(message.toolCallId);
		requests.push({
			...context,
			messages: structuredClone(context.messages),
			tools: context.tools?.map(({ name, description, parameters }) => ({ name, description, parameters })),
		});
		business++;
		if (business > 2) return fauxAssistantMessage("All assigned work is complete.");
		const names = business === 1 ? ["one", "two"] : ["three", "four"];
		return fauxAssistantMessage(
			names.map((name) => fauxToolCall("read", { path: path.join(fixture.taskDir, name) }, { id: `tool-${name}` })),
		);
	};
	fixture.h.setResponses([
		...(bootstrap ? [fauxAssistantMessage("Worker bootstrap accepted.")] : []),
		...Array.from({ length: 20 }, () => respond),
	]);
	return { requests, business: () => business };
}

describe("native compaction production lifecycle", () => {
	it("real print mode waits for two native cycles and final async settlement without replay or new runs", async () => {
		const fixture = await nativeHarness();
		const summaries = { count: 0 };
		const script = cycleScript(fixture, summaries);
		const result = await runPrintMode(fixture.runtime, { mode: "text", initialMessage: "Finish the existing task" });
		expect(result, JSON.stringify(fixture.h.eventsOfType("compaction_end"))).toBe(0);
		expect(fixture.settledCompleted()).toBe(true);
		expect(script.business()).toBe(3);
		expect(
			script.requests[2].messages
				.filter((message) => message.role === "toolResult")
				.map((message) => message.toolCallId),
		).toEqual(["tool-three", "tool-four"]);
		expect([...fixture.effects.values()]).toEqual([1, 1, 1, 1]);
		expect(fs.readFileSync(path.join(root, "side-effects.log"), "utf8").trim().split("\n")).toHaveLength(4);
		const compacted = fixture.h.sessionManager.getEntries().filter((entry) => entry.type === "compaction");
		expect(compacted).toHaveLength(2);
		expect(summaries.count).toBeGreaterThanOrEqual(2);
		expect(compacted.every((entry) => entry.usage && entry.usage.output > 0)).toBe(true);
		expect(fixture.h.eventsOfType("agent_start")).toHaveLength(1);
		expect(fixture.h.eventsOfType("agent_end")).toHaveLength(1);
		expect(fixture.h.eventsOfType("agent_settled")).toHaveLength(1);
		expect(
			fixture.h.sessionManager
				.getEntries()
				.filter((entry) => entry.type === "message" && entry.message.role === "user"),
		).toHaveLength(2);
		expect(
			fixture.h.sessionManager
				.getEntries()
				.filter(
					(entry) =>
						entry.type === "custom" &&
						["mw-context-checkpoint", "mw-context-compaction-usage"].includes(entry.customType),
				),
		).toHaveLength(0);
		expect(fixture.h.sessionManager.getEntries().filter((entry) => entry.type === "custom_message")).toHaveLength(0);
		expect(io.lines.join("")).toContain("All assigned work is complete.");
		expect(fixture.h.settingsManager.getCompactionSettings()).toMatchObject({
			enabled: false,
			keepRecentTokens: 1,
			reserveTokens: 16384,
		});
	});

	it("real worker stays running through compaction and writes only one final task outcome", async () => {
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const fixture = await nativeHarness(true);
		const summaries = { count: 0 };
		cycleScript(fixture, summaries, () => {
			expect(exit).not.toHaveBeenCalled();
			expect(JSON.parse(fs.readFileSync(path.join(fixture.taskDir, "run.json"), "utf8"))).toMatchObject({
				status: "running",
			});
			expect(fs.existsSync(path.join(fixture.taskDir, "output.md"))).toBe(false);
			expect(fs.readFileSync(path.join(fixture.taskDir, "trace.log"), "utf8")).not.toMatch(
				/\[END\]|\[PHASE\]|\[MODEL_ERR\]/,
			);
		});
		await fixture.h.session.prompt("Complete the assigned worker task");
		expect([...fixture.effects.values()]).toEqual([1, 1, 1, 1]);
		expect(fixture.h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(2);
		expect(JSON.parse(fs.readFileSync(path.join(fixture.taskDir, "run.json"), "utf8"))).toMatchObject({
			status: "done",
			exit: 0,
		});
		const trace = fs.readFileSync(path.join(fixture.taskDir, "trace.log"), "utf8");
		expect(trace.match(/\[END\]/g)).toHaveLength(1);
		expect(trace).not.toMatch(/\[MODEL_ERR\]|\[MODEL_RETRY\]|\[MODEL_FALLBACK\]|self-check/);
		expect(fixture.h.eventsOfType("agent_start")).toHaveLength(1);
		expect(fixture.h.eventsOfType("agent_settled")).toHaveLength(1);
	});

	it("real print worker with a configured phase completes compaction before phase progress and process disposal", async () => {
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const fixture = await nativeHarness(true, true);
		const summaries = { count: 0 };
		const script = cycleScript(
			fixture,
			summaries,
			() => {
				expect(exit).not.toHaveBeenCalled();
				expect(JSON.parse(fs.readFileSync(path.join(fixture.taskDir, "run.json"), "utf8"))).toMatchObject({
					status: "running",
				});
				expect(fs.existsSync(path.join(fixture.taskDir, "progress", "phase-1.md"))).toBe(false);
				expect(fs.existsSync(path.join(fixture.taskDir, "output.md"))).toBe(false);
			},
			true,
		);
		const result = await runPrintMode(fixture.runtime, {
			mode: "text",
			initialMessage: "Initialize this worker task",
		});
		expect(result).toBe(0);
		expect(script.business()).toBe(3);
		expect([...fixture.effects.values()]).toEqual([1, 1, 1, 1]);
		expect(fixture.h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(2);
		expect(fs.existsSync(path.join(fixture.taskDir, "progress", "phase-1.md"))).toBe(true);
		expect(JSON.parse(fs.readFileSync(path.join(fixture.taskDir, "run.json"), "utf8"))).toMatchObject({
			status: "done",
			exit: 0,
		});
		// The worker's existing bootstrap/phase transition owns two runs; compression adds none.
		expect(fixture.h.eventsOfType("agent_start")).toHaveLength(2);
		expect(fixture.h.eventsOfType("agent_settled")).toHaveLength(2);
	});

	it.each(["error", "cancel"] as const)(
		"native %s stops the worker without business resume or replay",
		async (mode) => {
			const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
			const fixture = await nativeHarness(true);
			const summaryStarted = deferred();
			let business = 0;
			let summaries = 0;
			fixture.h.setResponses(
				Array.from({ length: 8 }, () => async (context, options) => {
					if (context.systemPrompt === SUMMARIZATION_SYSTEM_PROMPT) {
						summaries++;
						summaryStarted.resolve();
						if (mode === "cancel")
							await new Promise<void>((resolve) =>
								options?.signal?.addEventListener("abort", () => resolve(), { once: true }),
							);
						return fauxAssistantMessage("", {
							stopReason: mode === "error" ? "error" : "aborted",
							errorMessage: "HTTP 429 insufficient_quota PRIVATE-NATIVE-SECRET",
						});
					}
					business++;
					return fauxAssistantMessage(
						["one", "two"].map((name) =>
							fauxToolCall("read", { path: path.join(fixture.taskDir, name) }, { id: `tool-${name}` }),
						),
					);
				}),
			);
			const pending = fixture.h.session.prompt("Complete the worker task");
			const observed = pending.catch(() => {});
			await summaryStarted.promise;
			if (mode === "cancel") await fixture.h.session.abort();
			await observed;
			expect(business).toBe(1);
			expect(summaries).toBe(1);
			expect([...fixture.effects.values()]).toEqual([1, 1]);
			expect(fixture.h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(0);
			expect(exit).toHaveBeenCalledOnce();
			const rawRun = fs.readFileSync(path.join(fixture.taskDir, "run.json"), "utf8");
			expect(JSON.parse(rawRun)).toMatchObject(
				mode === "error"
					? { status: "needs-clarification", exit: 2, context_policy_code: "SUMMARY_FAILED" }
					: { status: "failed", exit: 1, aborted: true },
			);
			if (mode === "cancel") expect(JSON.parse(rawRun).context_policy_code).toBeUndefined();
			expect(rawRun).not.toContain("PRIVATE-NATIVE-SECRET");
			expect(JSON.stringify(fixture.h.sessionManager.getEntries())).not.toContain("PRIVATE-NATIVE-SECRET");
			expect(fs.readFileSync(path.join(fixture.taskDir, "trace.log"), "utf8")).not.toMatch(
				/\[MODEL_RETRY\]|\[MODEL_FALLBACK\]|\[PHASE\]/,
			);
		},
	);

	it("real RPC emits no settled event while native compaction is pending and finishes the same run", async () => {
		const fixture = await nativeHarness();
		const summaryStarted = deferred();
		const releaseSummary = deferred();
		let business = 0;
		fixture.h.setResponses(
			Array.from({ length: 8 }, () => async (context) => {
				if (context.systemPrompt === SUMMARIZATION_SYSTEM_PROMPT) {
					summaryStarted.resolve();
					await releaseSummary.promise;
					return fauxAssistantMessage("Native task state retained.");
				}
				business++;
				return business === 1
					? fauxAssistantMessage(
							["one", "two"].map((name) =>
								fauxToolCall("read", { path: path.join(fixture.taskDir, name) }, { id: `tool-${name}` }),
							),
						)
					: fauxAssistantMessage("RPC task complete.");
			}),
		);
		void runRpcMode(fixture.runtime);
		await vi.waitFor(() => expect(io.onLine).toBeDefined());
		io.onLine?.(JSON.stringify({ id: "native-prompt", type: "prompt", message: "Finish the task" }));
		await summaryStarted.promise;
		expect(records().filter((record) => record.type === "agent_settled")).toHaveLength(0);
		expect(fixture.h.session.isCompacting).toBe(true);
		expect(business).toBe(1);
		releaseSummary.resolve();
		await vi.waitFor(() => expect(records().filter((record) => record.type === "agent_settled")).toHaveLength(1));
		expect(business).toBe(2);
		expect([...fixture.effects.values()]).toEqual([1, 1]);
		expect(records().filter((record) => record.type === "agent_start")).toHaveLength(1);
		expect(records().filter((record) => record.type === "response" && record.id === "native-prompt")).toEqual([
			expect.objectContaining({ success: true }),
		]);
	});
});
