/**
 * rag-evidence.test.ts — RAG evidence lines, breaker and fallback limits
 * (mw-rag-integration T-05, VCs 010/011/012/013/021).
 *
 * The suite config is `silent: "passed-only"`, so every `[VERIFY]` line is
 * written with `process.stdout.write` (T-02/T-12/T-13 lesson): a green test's
 * `console.log` never reaches the required command's output.
 *
 * Evidence lines land in `<workerTaskDir>/trace.log` through the single
 * `output-writer.ts::appendTrace` path, which prefixes `[FLOW] <iso-ts> `;
 * the assertions strip that prefix and match the evidence payload.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { Breaker, Budget } from "../../src/extensions/agent-team-loop/rag/budget.ts";
import { ENV_RAG_SERVERS_FILE } from "../../src/extensions/agent-team-loop/rag/config.ts";
import {
	RAG_FALLBACK,
	RAG_REQUIRED_MISSING,
	ragBudgetExceededLine,
	ragCallLine,
	ragFallbackLine,
	ragRequiredMissingLine,
	ragRewriteDegradedLine,
	ragUnavailableLine,
	redactSecrets,
} from "../../src/extensions/agent-team-loop/rag/evidence.ts";
import { type RagRuntime, registerRagTools } from "../../src/extensions/agent-team-loop/rag/tools.ts";
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
const savedEnv = new Map<string, string | undefined>();

afterEach(async () => {
	await Promise.all(fixtures.splice(0).map((fixture) => fixture.stop()));
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
});

function setEnv(name: string, value: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	process.env[name] = value;
}

function makeTempDir(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

interface ServerSpec {
	name: string;
	transport: "mcp" | "skill" | "both";
	url?: string;
	tokenEnv?: string;
	cliEntry?: string;
	skillDir?: string;
	timeoutMs?: number;
	graph?: boolean;
	chat?: boolean;
	rewrite?: boolean;
}

function serversYaml(entries: ServerSpec[]): string {
	const lines = ["servers:"];
	for (const entry of entries) {
		lines.push(`  ${entry.name}:`);
		lines.push(`    transport: ${entry.transport}`);
		if (entry.url !== undefined) {
			lines.push("    mcp:");
			lines.push(`      url: ${entry.url}`);
			if (entry.tokenEnv !== undefined) lines.push(`      token_env: ${entry.tokenEnv}`);
			if (entry.timeoutMs !== undefined) lines.push(`      timeout_ms: ${entry.timeoutMs}`);
		}
		if (entry.cliEntry !== undefined) {
			lines.push("    skill:");
			lines.push(`      dir: ${JSON.stringify(entry.skillDir ?? ".")}`);
			lines.push(`      cli_entry: ${JSON.stringify(entry.cliEntry)}`);
			if (entry.timeoutMs !== undefined) lines.push(`      timeout_ms: ${entry.timeoutMs}`);
		}
		lines.push("    capabilities:");
		lines.push(`      graph: ${entry.graph ?? false}`);
		lines.push(`      chat: ${entry.chat ?? false}`);
		lines.push(`      rewrite: ${entry.rewrite ?? false}`);
	}
	return `${lines.join("\n")}\n`;
}

function makeProject(enabled: string[], servers: string): { project: string; taskDir: string } {
	const project = makeTempDir("rag-evidence-");
	fs.mkdirSync(path.join(project, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
	fs.writeFileSync(
		path.join(project, ".agenticdoc", "target.yml"),
		`rag:\n  enabled: [${enabled.join(", ")}]\n`,
		"utf8",
	);
	fs.writeFileSync(path.join(project, ".mw", "rag-servers.yml"), servers, "utf8");
	// Hermetic machine layer: hard override to a non-existent file.
	if (!savedEnv.has(ENV_RAG_SERVERS_FILE)) savedEnv.set(ENV_RAG_SERVERS_FILE, process.env[ENV_RAG_SERVERS_FILE]);
	process.env[ENV_RAG_SERVERS_FILE] = path.join(project, ".machine-servers-does-not-exist.yml");
	const taskDir = path.join(project, ".agenticdoc", "key", "workers", "task");
	fs.mkdirSync(taskDir, { recursive: true });
	return { project, taskDir };
}

function makeCliScript(tool: string, payload: unknown): { dir: string; cliEntry: string } {
	const dir = makeTempDir("rag-evidence-cli-");
	const script = [
		"import json",
		"import sys",
		"",
		"",
		"def main():",
		`    payload = ${JSON.stringify(payload)}`,
		"    sys.stdout.write(json.dumps(payload))",
		"    sys.stdout.write('\\n')",
		"    return 0",
		"",
		"",
		"if __name__ == '__main__':",
		"    sys.exit(main())",
		"",
	].join("\n");
	const cliEntry = path.join(dir, `${tool}_cli.py`);
	fs.writeFileSync(cliEntry, script, "utf8");
	return { dir, cliEntry };
}

async function makeFixture(options?: Parameters<typeof startRagFixture>[0]): Promise<RagFixture> {
	const fixture = await startRagFixture(options);
	fixtures.push(fixture);
	return fixture;
}

interface Registered {
	capture: CapturingApi;
	runtime: RagRuntime;
	taskDir: string;
	breaker: Breaker;
}

async function registerFor(project: string, taskDir: string): Promise<Registered> {
	const { capture, pi } = api();
	const breaker = new Breaker();
	// A wired budget keeps the cheap retrieval path open; nothing here asserts
	// chat counting (that is rag-budget.test.ts).
	const budget = new Budget(taskDir, 2, 900_000);
	const runtime = registerRagTools(pi, project, { workerTaskDir: taskDir, breaker, budget });
	expect(runtime).not.toBeNull();
	if (runtime === null) throw new Error("rag runtime was not created");
	await runtime.ready;
	return { capture, runtime, taskDir, breaker };
}

function traceLines(taskDir: string): string[] {
	try {
		return fs
			.readFileSync(path.join(taskDir, "trace.log"), "utf8")
			.split(/\r?\n/)
			.filter((line) => line.length > 0);
	} catch {
		return [];
	}
}

/** Strip the `appendTrace` envelope so the payload can be matched as a line. */
function payloads(lines: string[]): string[] {
	return lines.map((line) => line.replace(/^\[FLOW\] \S+ /, ""));
}

interface ParsedCall {
	server: string;
	tool: string;
	via: string;
	ms: number;
	results: number;
	mcpTool: string | null;
}

function parseCall(payload: string): ParsedCall | null {
	const match = /^rag_call server=(\S+) tool=(\S+) via=(mcp|cli) ms=(\d+) results=(\d+)(?: mcp_tool=(\S+))?$/.exec(
		payload,
	);
	if (match === null) return null;
	return {
		server: match[1],
		tool: match[2],
		via: match[3],
		ms: Number.parseInt(match[4], 10),
		results: Number.parseInt(match[5], 10),
		mcpTool: match[6] ?? null,
	};
}

async function run(
	capture: CapturingApi,
	name: string,
	params: Record<string, unknown>,
): Promise<{ details: unknown; content: string }> {
	const result = await toolOf(capture, name).execute("call-1", params);
	return { details: result.details, content: result.content.map((part) => part.text).join("\n") };
}

// ── evidence line formats (five types, machine-checkable) ───────────────────

describe("evidence line formats", () => {
	it("emits every evidence line type with stable field names", () => {
		const call = ragCallLine({
			server: "A",
			tool: "rag_search",
			via: "mcp",
			ms: 12,
			results: 3,
			mcpTool: "rag_search",
		});
		expect(call).toBe("rag_call server=A tool=rag_search via=mcp ms=12 results=3 mcp_tool=rag_search");
		expect(ragCallLine({ server: "A", tool: "rag_graph", via: "mcp", ms: 1, results: 0 })).toBe(
			"rag_call server=A tool=rag_graph via=mcp ms=1 results=0",
		);
		expect(ragFallbackLine({ server: "A", tool: "rag_search", reason: "connect" })).toBe(
			`${RAG_FALLBACK} server=A tool=rag_search via=cli reason=connect`,
		);
		expect(ragUnavailableLine({ server: "A", tool: "rag_chat", kind: "timeout", ms: 600001 })).toBe(
			"rag-unavailable server=A tool=rag_chat kind=timeout ms=600001",
		);
		expect(ragBudgetExceededLine({ server: "A", tool: "rag_chat", reason: "count", used: 2, budget: 2 })).toBe(
			"rag-budget-exceeded server=A tool=rag_chat reason=count used=2 budget=2",
		);
		expect(ragRewriteDegradedLine({ server: "A", tool: "rag_search" })).toBe(
			"rag-rewrite-degraded server=A tool=rag_search",
		);
		expect(ragRequiredMissingLine({ role: "review", phase: "review", server: "A" })).toBe(
			`${RAG_REQUIRED_MISSING} role=review phase=review server=A`,
		);
		verify("[VERIFY] evidence_line_types=5+fallback formats=stable");
	});
});

// ── VC-011: one rag_call line per logical tool, results semantics ───────────

describe("VC-011 rag_call evidence", () => {
	it("writes one line per tool with the wire name and correct results count", async () => {
		const fixture = await makeFixture({
			tools: {
				rag_search: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 9 }], total_count: 1 }),
				rag_symbol: () => ({ file_path: "engine::src/A.cpp", line_start: 4, name: "Foo" }),
				graph_query: () => ({
					symbol: "Foo",
					operation: "callers",
					results: [{ file_path: "engine::src/A.cpp", line_start: 3 }],
				}),
				rag_impact: () => ({
					symbol: "Foo",
					total_callers: 3,
					affected_files: ["engine::src/a.cpp", "engine::src/b.cpp", "engine::src/c.cpp"],
				}),
				list_sources: () => ({ sources: [{ name: "engine-code", collections: [{ name: "engine" }] }] }),
				list_collections: () => ({ collections: [{ name: "engine", chunk_count: 12 }] }),
				rag_feedback: () => ({ status: "ok", results: [] }),
			},
		});
		const { project, taskDir } = makeProject(
			["A"],
			serversYaml([{ name: "A", transport: "mcp", url: fixture.url, graph: true, chat: true, rewrite: true }]),
		);
		const { capture } = await registerFor(project, taskDir);

		const before = traceLines(taskDir).length;
		await run(capture, "rag_search", { server: "A", query: "renderer" });
		await run(capture, "rag_symbol", { server: "A", symbol_name: "Foo" });
		await run(capture, "rag_graph", { server: "A", operation: "callers", symbol_name: "Foo" });
		await run(capture, "rag_impact", { server: "A", symbol: "Foo" });
		await run(capture, "rag_sources", { server: "A" });
		await run(capture, "rag_feedback", {
			server: "A",
			title: "t",
			tool: "rag_search",
			expected: "a",
			actual: "b",
		});

		const delta = payloads(traceLines(taskDir).slice(before));
		const calls = delta.map(parseCall).filter((call): call is ParsedCall => call !== null);
		const byTool = new Map(calls.map((call) => [call.tool, call]));

		const expectedTools = ["rag_search", "rag_symbol", "rag_graph", "rag_impact", "rag_sources", "rag_feedback"];
		for (const tool of expectedTools) {
			const call = byTool.get(tool);
			expect(call, `missing rag_call for ${tool}`).toBeDefined();
			if (call === undefined) continue;
			expect(call.server).toBe("A");
			expect(call.via).toBe("mcp");
			expect(Number.isInteger(call.ms)).toBe(true);
			expect(call.mcpTool).not.toBeNull();
		}
		// The T-13 mapping is auditable from the line: logical name + wire name.
		expect(byTool.get("rag_graph")?.mcpTool).toBe("graph_query");
		expect(byTool.get("rag_sources")?.mcpTool).toBe("list_sources+list_collections");
		// results semantics.
		expect(byTool.get("rag_impact")?.results).toBe(3);
		expect(byTool.get("rag_sources")?.results).toBe(2);
		expect(byTool.get("rag_feedback")?.results).toBe(0);
		expect(byTool.get("rag_search")?.results).toBe(1);

		verify(`[VERIFY] VC-011: rag_call_types=${byTool.size} impact_results_semantics=affected-files`);
	});
});

// ── VC-010: breaker counts only transport kinds ─────────────────────────────

describe("VC-010 breaker", () => {
	it("opens after 3 transport failures and ignores capability rejections", async () => {
		const fixture = await makeFixture({
			tools: {
				rag_search: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 1 }] }),
				graph_query: () => ({ symbol: "Foo", results: [] }),
			},
		});
		const { project, taskDir } = makeProject(
			["A", "B"],
			serversYaml([
				{ name: "A", transport: "mcp", url: fixture.url, graph: true, chat: true },
				{ name: "B", transport: "mcp", url: fixture.url, graph: false, chat: false },
			]),
		);
		const { capture, breaker } = await registerFor(project, taskDir);

		// Three counted failures on A.
		const baseline = fixture.calls.length;
		fixture.failNext(3, "reset");
		for (let attempt = 0; attempt < 3; attempt += 1) {
			const result = await run(capture, "rag_search", { server: "A", query: "x" });
			expect((result.details as { kind?: string }).kind).toBe("connect");
		}
		expect(fixture.calls.length - baseline).toBe(3);
		expect(breaker.isOpen("A")).toBe(true);

		// Fourth call short-circuits: zero requests.
		const beforeCircuit = fixture.calls.length;
		const circuit = await run(capture, "rag_search", { server: "A", query: "x" });
		expect((circuit.details as { kind?: string }).kind).toBe("circuit");
		expect((circuit.details as { message?: string }).message).toContain("circuit open");
		expect(fixture.calls.length - beforeCircuit).toBe(0);

		// capability is not a transport failure: two rejections on B, then the
		// mcp call still succeeds and B's breaker is untouched.
		const beforeCapability = fixture.calls.length;
		for (let attempt = 0; attempt < 2; attempt += 1) {
			const denied = await run(capture, "rag_graph", { server: "B", operation: "callers", symbol_name: "Foo" });
			expect((denied.details as { kind?: string }).kind).toBe("capability");
		}
		expect(fixture.calls.length - beforeCapability).toBe(0);
		expect(breaker.isOpen("B")).toBe(false);

		const ok = await run(capture, "rag_search", { server: "B", query: "x" });
		expect((ok.details as { kind?: string }).kind).toBeUndefined();
		expect((ok.details as { server?: string }).server).toBe("B");
		expect(fixture.calls.length - beforeCapability).toBe(1);

		verify("[VERIFY] VC-010: short_circuited=true api_calls=0 capability_not_counted=true");
	});
});

// ── VC-012: fallback limits ─────────────────────────────────────────────────

describe("VC-012 fallback limits", () => {
	it("skill transport is the primary path: rag_call via=cli, no rag_fallback", async () => {
		const fixture = await makeFixture({});
		const cli = makeCliScript("rag_search", { documents: [{ file_path: "engine::src/A.cpp", line_start: 5 }] });
		const { project, taskDir } = makeProject(
			["S"],
			serversYaml([
				{ name: "S", transport: "skill", cliEntry: cli.cliEntry, skillDir: cli.dir, graph: false, chat: false },
			]),
		);
		const { capture } = await registerFor(project, taskDir);
		const before = fixture.calls.length;

		const result = await run(capture, "rag_search", { server: "S", query: "renderer" });
		expect((result.details as { tool?: string }).tool).toBe("rag_search");
		const delta = payloads(traceLines(taskDir));
		const calls = delta.map(parseCall).filter((call): call is ParsedCall => call !== null);
		expect(calls).toHaveLength(1);
		expect(calls[0].tool).toBe("rag_search");
		expect(calls[0].via).toBe("cli");
		expect(delta.some((line) => line.startsWith(RAG_FALLBACK))).toBe(false);
		expect(fixture.calls.length - before).toBe(0);

		verify("[VERIFY] VC-012: skill_primary=true fallback_on_connect=true write_tool_no_fallback=true");
	});

	it("both + mcp connect reset falls back to cli and records rag_fallback", async () => {
		const fixture = await makeFixture({
			tools: { rag_search: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 5 }] }) },
		});
		const cli = makeCliScript("rag_search", { documents: [{ file_path: "engine::src/A.cpp", line_start: 6 }] });
		const { project, taskDir } = makeProject(
			["B"],
			serversYaml([
				{
					name: "B",
					transport: "both",
					url: fixture.url,
					cliEntry: cli.cliEntry,
					skillDir: cli.dir,
					graph: true,
					chat: true,
				},
			]),
		);
		const { capture } = await registerFor(project, taskDir);
		const before = fixture.calls.length;

		fixture.failNext(1, "reset");
		const result = await run(capture, "rag_search", { server: "B", query: "renderer" });
		expect((result.details as { tool?: string }).tool).toBe("rag_search");
		// Exactly one mcp attempt (the reset); the cli leg never touches the fixture.
		expect(fixture.calls.length - before).toBe(1);

		const delta = payloads(traceLines(taskDir));
		expect(delta).toContain(`${RAG_FALLBACK} server=B tool=rag_search via=cli reason=connect`);
		const calls = delta.map(parseCall).filter((call): call is ParsedCall => call !== null);
		expect(calls).toHaveLength(1);
		expect(calls[0].via).toBe("cli");
	});

	it("write tool rag_feedback never falls back on connect", async () => {
		const fixture = await makeFixture({
			tools: { rag_feedback: () => ({ status: "ok" }) },
		});
		const cli = makeCliScript("rag_feedback", { status: "cli-should-not-run" });
		const { project, taskDir } = makeProject(
			["B"],
			serversYaml([
				{
					name: "B",
					transport: "both",
					url: fixture.url,
					cliEntry: cli.cliEntry,
					skillDir: cli.dir,
					graph: true,
					chat: true,
				},
			]),
		);
		const { capture } = await registerFor(project, taskDir);
		const before = fixture.calls.length;

		fixture.failNext(1, "reset");
		const result = await run(capture, "rag_feedback", {
			server: "B",
			title: "t",
			tool: "rag_search",
			expected: "a",
			actual: "b",
		});
		expect((result.details as { kind?: string }).kind).toBe("connect");
		expect(fixture.calls.length - before).toBe(1);
		const delta = payloads(traceLines(taskDir));
		expect(delta.some((line) => line.startsWith(RAG_FALLBACK))).toBe(false);
		expect(delta.some((line) => line.startsWith("rag-unavailable server=B tool=rag_feedback kind=connect"))).toBe(
			true,
		);

		verify("[VERIFY] VC-012: skill_primary=true fallback_on_connect=true write_tool_no_fallback=true");
	});

	it("timeout (delivered but lost) never falls back", async () => {
		const fixture = await makeFixture({ dropAfterDelivery: true, tools: { rag_search: () => ({ documents: [] }) } });
		const cli = makeCliScript("rag_search", { documents: [{ file_path: "engine::src/A.cpp", line_start: 7 }] });
		const { project, taskDir } = makeProject(
			["B"],
			serversYaml([
				{
					name: "B",
					transport: "both",
					url: fixture.url,
					cliEntry: cli.cliEntry,
					skillDir: cli.dir,
					timeoutMs: 250,
					graph: true,
					chat: true,
				},
			]),
		);
		const { capture } = await registerFor(project, taskDir);

		const result = await run(capture, "rag_search", { server: "B", query: "renderer" });
		expect((result.details as { kind?: string }).kind).toBe("timeout");
		const delta = payloads(traceLines(taskDir));
		expect(delta.some((line) => line.startsWith(RAG_FALLBACK))).toBe(false);
		expect(delta.some((line) => line.startsWith("rag-unavailable server=B tool=rag_search kind=timeout"))).toBe(true);
	});
});

// ── VC-013: token redaction ─────────────────────────────────────────────────

describe("VC-013 token redaction", () => {
	it("keeps the token out of trace lines, messages and detail", async () => {
		setEnv("OVERCODE_MCP_TOKEN", "SECRET123");
		const fixture = await makeFixture({
			token: "SECRET123",
			tools: {
				rag_search: () => {
					throw new Error("upstream echoed SECRET123");
				},
			},
		});
		const { project, taskDir } = makeProject(
			["A"],
			serversYaml([
				{
					name: "A",
					transport: "mcp",
					url: fixture.url,
					tokenEnv: "OVERCODE_MCP_TOKEN",
					graph: true,
					chat: true,
				},
			]),
		);
		const { capture } = await registerFor(project, taskDir);

		// The unit level: the configured env value is replaced, not the name.
		expect(redactSecrets("token SECRET123 token", ["OVERCODE_MCP_TOKEN"])).toBe("token <redacted> token");
		expect(redactSecrets("no match here", ["OVERCODE_MCP_TOKEN"])).toBe("no match here");
		expect(redactSecrets("x", ["MW_RAG_ABSENT_TOKEN"])).toBe("x");

		const failure = await run(capture, "rag_search", { server: "A", query: "renderer" });
		expect((failure.details as { kind?: string }).kind).toBe("tool");
		expect(JSON.stringify(failure.details)).not.toContain("SECRET123");
		expect(failure.content).not.toContain("SECRET123");

		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		expect(trace).not.toContain("SECRET123");
		expect(trace).toContain("rag-unavailable server=A tool=rag_search kind=tool");

		// A connect failure path too.
		fixture.failNext(1, "reset");
		const connectFailure = await run(capture, "rag_search", { server: "A", query: "renderer" });
		expect((connectFailure.details as { kind?: string }).kind).toBe("connect");
		expect(JSON.stringify(connectFailure.details)).not.toContain("SECRET123");
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).not.toContain("SECRET123");

		verify("[VERIFY] VC-013: secret_hits=0 error_redacted=true argv_clean_scope=T-07/T-08");
	});
});

// ── VC-021: rewrite_degraded evidence ───────────────────────────────────────

describe("VC-021 rewrite degraded", () => {
	it("adds rag-rewrite-degraded only when the server degrades the rewrite", async () => {
		const degradedFixture = await makeFixture({
			rewriteDegraded: true,
			tools: { rag_search: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 1 }] }) },
		});
		const degraded = makeProject(
			["A"],
			serversYaml([
				{ name: "A", transport: "mcp", url: degradedFixture.url, graph: true, chat: true, rewrite: true },
			]),
		);
		const degradedRuntime = await registerFor(degraded.project, degraded.taskDir);
		const degradedBefore = traceLines(degraded.taskDir).length;
		const degradedResult = await run(degradedRuntime.capture, "rag_search", { server: "A", query: "renderer" });
		expect((degradedResult.details as { meta?: { rewrite_degraded?: unknown } }).meta?.rewrite_degraded).toBe(true);
		const degradedDelta = payloads(traceLines(degraded.taskDir).slice(degradedBefore));
		expect(degradedDelta.some((line) => line.startsWith("rag-rewrite-degraded server=A tool=rag_search"))).toBe(true);
		// The successful call line is still written alongside the degradation note.
		expect(degradedDelta.some((line) => line.startsWith("rag_call server=A tool=rag_search via=mcp"))).toBe(true);

		const cleanFixture = await makeFixture({
			tools: { rag_search: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 2 }] }) },
		});
		const clean = makeProject(
			["A"],
			serversYaml([{ name: "A", transport: "mcp", url: cleanFixture.url, graph: true, chat: true, rewrite: true }]),
		);
		const cleanRuntime = await registerFor(clean.project, clean.taskDir);
		const cleanBefore = traceLines(clean.taskDir).length;
		const cleanResult = await run(cleanRuntime.capture, "rag_search", { server: "A", query: "renderer" });
		expect((cleanResult.details as { meta?: { rewrite_degraded?: unknown } }).meta?.rewrite_degraded).not.toBe(true);
		const cleanDelta = payloads(traceLines(clean.taskDir).slice(cleanBefore));
		expect(cleanDelta.some((line) => line.startsWith("rag-rewrite-degraded"))).toBe(false);

		verify("[VERIFY] VC-021: degraded_flag=true trace_delta=rag-rewrite-degraded clean_delta=0");
	});
});
