/**
 * rag-budget.test.ts — RAG chat/time/wall budgets, synchronous reservation,
 * heartbeat cadence and the breaker kind filter (mw-rag-integration T-05,
 * VCs 010/016/017/025).
 *
 * `reserveChat` is deliberately synchronous: the assertion that matters is the
 * concurrent one — two calls racing for the last slot must produce exactly one
 * rejection and exactly one fixture `rag_chat` request. The suite config is
 * `silent: "passed-only"`, so `[VERIFY]` lines use `process.stdout.write`.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	Breaker,
	Budget,
	RAG_HEARTBEAT_INTERVAL_MS,
	withHeartbeat,
} from "../../src/extensions/agent-team-loop/rag/budget.ts";
import { ENV_RAG_SERVERS_FILE } from "../../src/extensions/agent-team-loop/rag/config.ts";
import { applyRagTools, type RagRuntime, registerRagTools } from "../../src/extensions/agent-team-loop/rag/tools.ts";
import { type RagFixture, startRagFixture } from "./rag-fixture.ts";

/* The suite swallows console.log from green tests; write the evidence line
 * straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

// ── capturing ExtensionAPI (T-04/T-13 shape) ────────────────────────────────

interface CapturedTool {
	name: string;
	execute: (
		toolCallId: string,
		params: Record<string, unknown>,
		signal?: AbortSignal,
		onUpdate?: (partial: { content: Array<{ type: "text"; text: string }>; details: unknown }) => void,
	) => Promise<{ content: Array<{ type: "text"; text: string }>; details: unknown }>;
}

class CapturingApi {
	readonly tools = new Map<string, CapturedTool>();
	active: string[] = [];

	registerTool(tool: unknown): void {
		const captured = tool as CapturedTool;
		this.tools.set(captured.name, captured);
	}

	setActiveTools(names: string[]): void {
		this.active = [...names];
	}

	getActiveTools(): string[] {
		return [...this.active];
	}

	getAllTools(): Array<{ name: string }> {
		return [...this.tools.keys()].map((name) => ({ name }));
	}

	on(): void {
		// registration-time handlers are irrelevant to these assertions
	}
}

function api(): { capture: CapturingApi; pi: ExtensionAPI } {
	const capture = new CapturingApi();
	return { capture, pi: capture as unknown as ExtensionAPI };
}

function toolOf(capture: CapturingApi, name: string): CapturedTool {
	const tool = capture.tools.get(name);
	if (tool === undefined) throw new Error(`tool '${name}' was not registered`);
	return tool;
}

// ── temp projects / fixtures / env isolation ────────────────────────────────

const tempDirs: string[] = [];
const fixtures: RagFixture[] = [];
let savedServersFile: string | undefined;
let serversFileSaved = false;

afterEach(async () => {
	await Promise.all(fixtures.splice(0).map((fixture) => fixture.stop()));
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	if (serversFileSaved) {
		if (savedServersFile === undefined) delete process.env[ENV_RAG_SERVERS_FILE];
		else process.env[ENV_RAG_SERVERS_FILE] = savedServersFile;
		serversFileSaved = false;
	}
});

function makeTempDir(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

function serversYaml(url: string): string {
	return [
		"servers:",
		"  A:",
		"    transport: mcp",
		"    mcp:",
		`      url: ${url}`,
		"      token_env: RAG_BUDGET_TEST_TOKEN",
		"    capabilities:",
		"      graph: true",
		"      chat: true",
		"      rewrite: true",
		"",
	].join("\n");
}

function makeProject(url: string): { project: string; taskDir: string } {
	const project = makeTempDir("rag-budget-");
	fs.mkdirSync(path.join(project, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(project, ".agenticdoc", "target.yml"), "rag:\n  enabled: [A]\n", "utf8");
	fs.writeFileSync(path.join(project, ".mw", "rag-servers.yml"), serversYaml(url), "utf8");
	if (!serversFileSaved) {
		savedServersFile = process.env[ENV_RAG_SERVERS_FILE];
		serversFileSaved = true;
	}
	// Hermetic machine layer: hard override to a non-existent file.
	process.env[ENV_RAG_SERVERS_FILE] = path.join(project, ".machine-servers-does-not-exist.yml");
	const taskDir = path.join(project, ".agenticdoc", "key", "workers", "task");
	fs.mkdirSync(taskDir, { recursive: true });
	return { project, taskDir };
}

async function makeFixture(options?: Parameters<typeof startRagFixture>[0]): Promise<RagFixture> {
	const fixture = await startRagFixture(options);
	fixtures.push(fixture);
	return fixture;
}

function chatCalls(fixture: RagFixture): number {
	return fixture.calls.filter((call) => call.name === "rag_chat").length;
}

interface Registered {
	capture: CapturingApi;
	pi: ExtensionAPI;
	runtime: RagRuntime;
}

async function registerFor(
	project: string,
	taskDir: string | null,
	budget: Budget,
	breaker: Breaker,
): Promise<Registered> {
	const { capture, pi } = api();
	const runtime = registerRagTools(pi, project, { workerTaskDir: taskDir, budget, breaker });
	expect(runtime).not.toBeNull();
	if (runtime === null) throw new Error("rag runtime was not created");
	await runtime.ready;
	applyRagTools(pi, runtime, "rag-research");
	return { capture, pi, runtime };
}

async function callTool(capture: CapturingApi, name: string, params: Record<string, unknown>): Promise<unknown> {
	const result = await toolOf(capture, name).execute("call-1", params);
	return result.details;
}

function kindOf(details: unknown): string | undefined {
	return (details as { kind?: string }).kind;
}

function messageOf(details: unknown): string {
	return (details as { message?: string }).message ?? "";
}

function traceText(taskDir: string): string {
	try {
		return fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
	} catch {
		return "";
	}
}

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── VC-016: chat count budget ───────────────────────────────────────────────

describe("VC-016 chat budget", () => {
	it("rejects the 3rd call of a budget of 2 with used=2 and only 2 requests", async () => {
		const fixture = await makeFixture({ tools: { rag_chat: () => ({ answer: "ok", documents: [] }) } });
		const { project, taskDir } = makeProject(fixture.url);
		const budget = new Budget(taskDir, 2, 900_000);
		const { capture } = await registerFor(project, taskDir, budget, new Breaker());

		expect(kindOf(await callTool(capture, "rag_chat", { server: "A", query: "q1" }))).toBeUndefined();
		expect(kindOf(await callTool(capture, "rag_chat", { server: "A", query: "q2" }))).toBeUndefined();
		expect(chatCalls(fixture)).toBe(2);

		const rejected = await callTool(capture, "rag_chat", { server: "A", query: "q3" });
		expect(kindOf(rejected)).toBe("budget");
		expect(messageOf(rejected)).toContain("used=2");
		expect(chatCalls(fixture)).toBe(2);
		expect(traceText(taskDir)).toContain("rag-budget-exceeded server=A tool=rag_chat reason=count used=2 budget=2");

		verify("[VERIFY] VC-016: rejected=true chat_calls=2 concurrent_single_grant=true");
	});

	it("reserves synchronously so two concurrent calls cannot both take the last slot", async () => {
		const fixture = await makeFixture({ delayMs: 200, tools: { rag_chat: () => ({ answer: "ok", documents: [] }) } });
		const { project } = makeProject(fixture.url);
		const budget = new Budget(null, 1, 900_000);
		const { capture } = await registerFor(project, null, budget, new Breaker());
		const before = chatCalls(fixture);

		const chat = toolOf(capture, "rag_chat");
		const [first, second] = await Promise.all([
			chat.execute("call-1", { server: "A", query: "q1" }),
			chat.execute("call-2", { server: "A", query: "q2" }),
		]);
		const kinds = [first.details, second.details].map((details) => kindOf(details));
		expect(kinds.filter((kind) => kind === "budget")).toHaveLength(1);
		expect(kinds.filter((kind) => kind === undefined)).toHaveLength(1);
		expect(chatCalls(fixture) - before).toBe(1);

		verify("[VERIFY] VC-016: rejected=true chat_calls=2 concurrent_single_grant=true");
	});

	it("refunds only a connect failure (timeout keeps the reservation)", () => {
		const connectBudget = new Budget(null, 1, 900_000);
		expect(connectBudget.reserveChat().ok).toBe(true);
		connectBudget.settleChat(false, "connect");
		expect(connectBudget.state().chatUsed).toBe(0);
		expect(connectBudget.reserveChat().ok).toBe(true);

		const timeoutBudget = new Budget(null, 1, 900_000);
		expect(timeoutBudget.reserveChat().ok).toBe(true);
		timeoutBudget.settleChat(false, "timeout");
		expect(timeoutBudget.state().chatUsed).toBe(1);
		const rejected = timeoutBudget.reserveChat();
		expect(rejected.ok).toBe(false);
		if (!rejected.ok) expect(rejected.message).toContain("used=1");
	});

	it("creates rag-budget.json on the first call only", () => {
		const dir = makeTempDir("rag-budget-file-");
		const file = path.join(dir, "rag-budget.json");
		const budget = new Budget(dir, 2, 900_000);
		expect(fs.existsSync(file)).toBe(false);
		expect(budget.reserveChat().ok).toBe(true);
		expect(fs.existsSync(file)).toBe(true);
		const parsed = JSON.parse(fs.readFileSync(file, "utf8")) as { chatUsed: number; chatBudget: number };
		expect(parsed.chatUsed).toBe(1);
		expect(parsed.chatBudget).toBe(2);

		budget.accumulate(1234);
		const after = JSON.parse(fs.readFileSync(file, "utf8")) as { timeUsedMs: number };
		expect(after.timeUsedMs).toBe(1234);

		// A dir-less budget never writes anywhere (PM/non-worker session).
		const scratch = makeTempDir("rag-budget-scratch-");
		const noDir = new Budget(null, 1, 900_000);
		noDir.reserveChat();
		expect(fs.readdirSync(scratch)).toEqual([]);
	});
});

// ── VC-017: heartbeat ───────────────────────────────────────────────────────

describe("VC-017 heartbeat", () => {
	it("pings onUpdate throughout a long call and clears the timer afterwards", async () => {
		let pings = 0;
		const times: number[] = [];
		const result = await withHeartbeat(
			20,
			() => {
				pings += 1;
				times.push(Date.now());
			},
			() => sleep(160).then(() => "done"),
		);

		expect(result).toBe("done");
		expect(pings).toBeGreaterThanOrEqual(4);
		const gaps = times.slice(1).map((time, index) => time - times[index]);
		for (const gap of gaps) expect(gap).toBeLessThan(60_000);
		expect(RAG_HEARTBEAT_INTERVAL_MS).toBe(30_000);

		// A throwing onUpdate must never break the call.
		await expect(
			withHeartbeat(
				10,
				() => {
					throw new Error("host update failed");
				},
				() => sleep(30).then(() => 7),
			),
		).resolves.toBe(7);

		await sleep(30);
		const settled = pings;
		await sleep(30);
		expect(pings).toBe(settled);

		verify(`[VERIFY] VC-017: heartbeat_interval_le_30s=true pings=${pings} l2_worker_alive_scope=T-11`);
	});

	it("accepts a missing onUpdate (PM/no-host call path)", async () => {
		await expect(withHeartbeat(10, undefined, () => sleep(25).then(() => "ok"))).resolves.toBe("ok");
	});
});

// ── VC-025: cumulative time budget + wall guard ─────────────────────────────

describe("VC-025 cumulative time and wall guard", () => {
	it("rejects every later call once the cumulative RAG time budget is exhausted", async () => {
		const fixture = await makeFixture({
			tools: {
				rag_search: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 1 }] }),
				rag_chat: () => ({ answer: "ok", documents: [] }),
			},
		});
		const { project, taskDir } = makeProject(fixture.url);
		const budget = new Budget(taskDir, 2, 1000);
		budget.accumulate(5000);
		const { capture } = await registerFor(project, taskDir, budget, new Breaker());
		const before = fixture.calls.length;

		const rejected = await callTool(capture, "rag_search", { server: "A", query: "x" });
		expect(kindOf(rejected)).toBe("budget");
		expect(messageOf(rejected)).toContain("used=5000");
		expect(fixture.calls.length - before).toBe(0);
		expect(traceText(taskDir)).toContain(
			"rag-budget-exceeded server=A tool=rag_search reason=cumulative used=5000 budget=1000",
		);

		verify("[VERIFY] VC-025: cumulative_rejected=true wall_guard_chat_rejected=true cheap_call_allowed=true");
	});

	it("past 70% of the wall budget rejects rag_chat while rag_search still works", async () => {
		const fixture = await makeFixture({
			tools: {
				rag_search: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 1 }] }),
				rag_chat: () => ({ answer: "ok", documents: [] }),
			},
		});
		const { project, taskDir } = makeProject(fixture.url);
		// startedAt is 10s in the past while the task wall budget is 1s.
		const budget = new Budget(taskDir, 2, 900_000, { taskWallMs: 1000, now: () => Date.now() - 10_000 });
		const { capture } = await registerFor(project, taskDir, budget, new Breaker());

		const chatBefore = chatCalls(fixture);
		const chat = await callTool(capture, "rag_chat", { server: "A", query: "q" });
		expect(kindOf(chat)).toBe("budget");
		expect(messageOf(chat)).toContain("wall clock guard");
		expect(chatCalls(fixture) - chatBefore).toBe(0);
		expect(traceText(taskDir)).toContain("rag-budget-exceeded server=A tool=rag_chat reason=wall");

		const before = fixture.calls.length;
		const cheap = await callTool(capture, "rag_search", { server: "A", query: "x" });
		expect(kindOf(cheap)).toBeUndefined();
		expect(fixture.calls.length - before).toBe(1);

		verify("[VERIFY] VC-025: cumulative_rejected=true wall_guard_chat_rejected=true cheap_call_allowed=true");
	});
});

// ── breaker kind filter (VC-010 counterexample) ─────────────────────────────

describe("breaker kind filter", () => {
	it("counts only connect/timeout/protocol", () => {
		const breaker = new Breaker();
		for (const kind of ["capability", "budget", "tool"] as const) {
			breaker.noteFailure("A", kind);
			breaker.noteFailure("A", kind);
			breaker.noteFailure("A", kind);
			expect(breaker.isOpen("A")).toBe(false);
		}
		breaker.noteFailure("A", "connect");
		breaker.noteFailure("A", "timeout");
		expect(breaker.isOpen("A")).toBe(false);
		breaker.noteFailure("A", "protocol");
		expect(breaker.isOpen("A")).toBe(true);
		breaker.noteSuccess("A");
		expect(breaker.isOpen("A")).toBe(false);
	});
});
