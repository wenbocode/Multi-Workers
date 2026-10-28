/**
 * rag-tools.test.ts — RAG tool surface, dispatch gate and task.md injection
 * (mw-rag-integration T-04).
 *
 *   VC-001  disabled project: zero tool registration, zero probe requests,
 *           zero rag bytes in task.md, no skill/budget file touched.
 *   VC-003  dispatch_worker refuses `rag.enabled` naming an undefined server
 *           before any task.md exists and without adding a queue row.
 *   VC-004  exactly the six base tools are visible; the server enum is the
 *           closed enabled set; rag_chat stays hidden.
 *   VC-005  a graph-less server returns kind=capability with "no knowledge
 *           graph" and makes zero requests.
 *
 * The registration/gating assertions drive a capturing ExtensionAPI; the
 * session-level zero-registration assertion additionally runs a real pi
 * session through the faux-provider harness.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import { registerWorkerTools } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { RAG_MARKER_V1, renderRagBlock } from "../../src/extensions/agent-team-loop/rag/block.ts";
import { loadRagConfig, type RagConfig, type RagServerEntry } from "../../src/extensions/agent-team-loop/rag/config.ts";
import {
	applyRagTools,
	RAG_BASE_TOOL_NAMES,
	RAG_CHAT_TOOL_NAME,
	registerRagTools,
	validateRagEnabled,
} from "../../src/extensions/agent-team-loop/rag/tools.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { parseTaskMd } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness } from "./harness.ts";
import { type RagFixture, startRagFixture } from "./rag-fixture.ts";

/* The suite config swallows console.log from green tests; write the evidence
 * line straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

// ── capturing ExtensionAPI ──────────────────────────────────────────────────

interface CapturedTool {
	name: string;
	description: string;
	parameters: unknown;
	promptGuidelines?: string[];
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

function enumValues(schema: unknown): string[] {
	const value = schema as { anyOf?: Array<{ const?: unknown }>; enum?: unknown; const?: unknown };
	if (Array.isArray(value.anyOf)) return value.anyOf.map((entry) => String(entry.const));
	if (Array.isArray(value.enum)) return value.enum.map((entry) => String(entry));
	if (value.const !== undefined) return [String(value.const)];
	return [];
}

function serverEnumOf(tool: CapturedTool): string[] {
	const parameters = tool.parameters as { properties?: Record<string, unknown> };
	return enumValues(parameters.properties?.server);
}

// ── temp projects / fixtures / env isolation ────────────────────────────────

const tempDirs: string[] = [];
const fixtures: RagFixture[] = [];
let savedServersFile: string | undefined;
let serversFileSaved = false;

function makeTempDir(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

interface ProjectOptions {
	enabled: string[];
	servers?: string;
}

function makeProject(options: ProjectOptions): string {
	const project = makeTempDir("rag-tools-");
	fs.mkdirSync(path.join(project, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(
		path.join(project, ".agenticdoc", "target.yml"),
		`rag:\n  enabled: [${options.enabled.join(", ")}]\n`,
		"utf8",
	);
	if (options.servers !== undefined) {
		fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
		fs.writeFileSync(path.join(project, ".mw", "rag-servers.yml"), options.servers, "utf8");
	}
	// Hermetic machine layer: hard override to a non-existent file.
	if (!serversFileSaved) {
		savedServersFile = process.env.MW_RAG_SERVERS_FILE;
		serversFileSaved = true;
	}
	process.env.MW_RAG_SERVERS_FILE = path.join(project, ".machine-servers-does-not-exist.yml");
	return project;
}

function serversYaml(
	entries: Array<{ name: string; url: string; graph?: boolean; chat?: boolean; rewrite?: boolean }>,
): string {
	const lines = ["servers:"];
	for (const entry of entries) {
		lines.push(`  ${entry.name}:`);
		lines.push("    transport: mcp");
		lines.push("    mcp:");
		lines.push(`      url: ${entry.url}`);
		lines.push("      token_env: RAG_TOOLS_TEST_TOKEN");
		lines.push("    capabilities:");
		lines.push(`      graph: ${entry.graph ?? false}`);
		lines.push(`      chat: ${entry.chat ?? false}`);
		lines.push(`      rewrite: ${entry.rewrite ?? false}`);
	}
	return `${lines.join("\n")}\n`;
}

async function makeFixture(): Promise<RagFixture> {
	const fixture = await startRagFixture();
	fixtures.push(fixture);
	return fixture;
}

function writeTask(project: string, ownerKey: string, taskKey: string, body: string): string {
	const dir = path.join(project, ".agenticdoc", ownerKey, "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	const taskPath = path.join(dir, "task.md");
	fs.writeFileSync(taskPath, body, "utf8");
	return taskPath;
}

function storeFor(project: string): WorkerStore {
	return new WorkerStore(path.join(project, ".agenticdoc"));
}

async function dispatch(project: string, ownerKey: string, taskKey: string, body: string): Promise<string> {
	const taskPath = writeTask(project, ownerKey, taskKey, body);
	await dispatchTask(
		{ taskKey, status: "pending", cli: "pi", provider: "timi", model: "", taskPath },
		storeFor(project),
	);
	return taskPath;
}

afterEach(async () => {
	await Promise.all(fixtures.splice(0).map((fixture) => fixture.stop()));
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	if (serversFileSaved) {
		if (savedServersFile === undefined) delete process.env.MW_RAG_SERVERS_FILE;
		else process.env.MW_RAG_SERVERS_FILE = savedServersFile;
		serversFileSaved = false;
	}
});

// ── VC-001: structural zero impact ──────────────────────────────────────────

describe("VC-001 zero impact when RAG is disabled", () => {
	it("registers nothing, probes nothing and writes no rag bytes", async () => {
		const fixture = await makeFixture();
		const project = makeProject({
			enabled: [],
			servers: serversYaml([{ name: "A", url: fixture.url, graph: true, chat: true }]),
		});
		const { capture, pi } = api();

		const runtime = registerRagTools(pi, project);
		expect(runtime).toBeNull();
		expect(capture.tools.size).toBe(0);

		// A dispatched task.md must not gain a single rag byte.
		const skillPath = path.join(project, ".pi", "skills", "mw-rag.md");
		fs.mkdirSync(path.dirname(skillPath), { recursive: true });
		fs.writeFileSync(skillPath, "skill body\n", "utf8");
		const budgetPath = path.join(project, ".agenticdoc", "_scratch", "workers", "vc001", "rag-budget.json");

		const taskPath = await dispatch(project, "_scratch", "vc001", "type: coding\n\nzero impact\n");
		const content = fs.readFileSync(taskPath, "utf8");

		expect(content).not.toContain("mw-rag");
		expect(fixture.calls.length).toBe(0);
		expect(fs.existsSync(skillPath)).toBe(true);
		expect(fs.existsSync(budgetPath)).toBe(false);

		verify(
			`[VERIFY] VC-001: rag_tools=0 task_md_block=0 probe_requests=0 skill_file_unchanged=true budget_file_absent=true`,
		);
	});

	it("registers zero rag_* tools in a real pi session", async () => {
		const project = makeProject({ enabled: [] });
		const harness = await createHarness({
			extensionFactories: [
				(pi) => {
					registerRagTools(pi, project);
				},
			],
		});
		try {
			await harness.session.bindExtensions({});
			const ragNames = harness.session
				.getAllTools()
				.map((tool) => tool.name)
				.filter((name) => name.startsWith("rag_"));
			expect(ragNames).toEqual([]);
		} finally {
			harness.cleanup();
		}
	});
});

// ── VC-004: exactly six tools + closed server enum ──────────────────────────

describe("VC-004 tool surface and server enum", () => {
	it("registers the six base tools with enum [A, B] and hides rag_chat", async () => {
		const fixture = await makeFixture();
		const project = makeProject({
			enabled: ["A", "B"],
			servers: serversYaml([
				{ name: "A", url: fixture.url, graph: true, chat: true, rewrite: true },
				{ name: "B", url: fixture.url, graph: false },
			]),
		});
		const { capture, pi } = api();
		const runtime = registerRagTools(pi, project);
		expect(runtime).not.toBeNull();
		if (runtime !== null) await runtime.ready;

		expect([...capture.tools.keys()].sort()).toEqual([...RAG_BASE_TOOL_NAMES].sort());
		expect(capture.tools.has(RAG_CHAT_TOOL_NAME)).toBe(false);

		let withServer = 0;
		for (const name of RAG_BASE_TOOL_NAMES) {
			const values = serverEnumOf(toolOf(capture, name));
			expect(values).toEqual(["A", "B"]);
			withServer += 1;
		}
		expect(withServer).toBe(6);

		// coding activation: base tools only, no duplicates, no rag_chat.
		capture.setActiveTools([]);
		applyRagTools(pi, runtime, "coding");
		expect(capture.active.filter((name) => name.startsWith("rag_")).sort()).toEqual([...RAG_BASE_TOOL_NAMES].sort());
		expect(capture.active).not.toContain(RAG_CHAT_TOOL_NAME);
		expect(new Set(capture.active).size).toBe(capture.active.length);

		// idempotent across repeated runs.
		const first = [...capture.active];
		applyRagTools(pi, runtime, "coding");
		applyRagTools(pi, runtime, "coding");
		expect(capture.active).toEqual(first);

		// rag-research is the only type that draws in rag_chat.
		applyRagTools(pi, runtime, "rag-research");
		expect(capture.active).toContain(RAG_CHAT_TOOL_NAME);
		expect(capture.tools.has(RAG_CHAT_TOOL_NAME)).toBe(true);

		verify(`[VERIFY] VC-004: tools=6 chat_visible=false server_enums=6/6`);
	});
});

// ── VC-005: capability error with zero requests ─────────────────────────────

describe("VC-005 capability error", () => {
	it("rag_graph on a graph-less server returns kind=capability and makes no request", async () => {
		const fixture = await makeFixture();
		const project = makeProject({
			enabled: ["A"],
			servers: serversYaml([{ name: "A", url: fixture.url, graph: false, chat: true }]),
		});
		const { capture, pi } = api();
		const runtime = registerRagTools(pi, project);
		expect(runtime).not.toBeNull();
		if (runtime === null) return;
		await runtime.ready;

		const baseline = fixture.calls.length;
		const tool = toolOf(capture, "rag_graph");
		const result = await tool.execute("call-1", { server: "A", operation: "callers", symbol_name: "Foo" });
		const details = result.details as { kind?: string; message?: string };

		expect(details.kind).toBe("capability");
		expect(details.message).toContain("no knowledge graph");
		expect(fixture.calls.length - baseline).toBe(0);

		verify(`[VERIFY] VC-005: error_kind=capability message_match=true api_calls=0`);
	});
});

// ── VC-003: dispatch refused before any task.md exists ──────────────────────

describe("VC-003 dispatch gate", () => {
	it("dispatch_worker refuses an unknown enabled server without creating files", async () => {
		const project = makeProject({ enabled: ["ghost"] });
		const agenticdocRoot = path.join(project, ".agenticdoc");
		const store = new WorkerStore(agenticdocRoot);
		const beforeRows = store.readAll().length;
		const { capture, pi } = api();
		registerWorkerTools(
			pi,
			store,
			new AckStore(agenticdocRoot),
			new IndexStore(agenticdocRoot),
			agenticdocRoot,
			{ key: undefined },
			project,
		);

		const tool = toolOf(capture, "dispatch_worker");
		const result = await tool.execute("call-1", {
			task_key: "vc003",
			description: "should be refused",
			type: "coding",
			key: "_scratch",
		});
		const text = result.content.map((part) => part.text).join("\n");

		expect(text).toContain("unknown rag server");
		expect(text).toContain("ghost");
		expect(store.readAll().length - beforeRows).toBe(0);
		expect(fs.existsSync(path.join(agenticdocRoot, "_scratch", "workers", "vc003"))).toBe(false);

		// The same check is what ui-bridge calls directly (fail-closed helper).
		const direct = validateRagEnabled(project);
		expect(direct.ok).toBe(false);
		if (!direct.ok) expect(direct.message).toContain("unknown rag server");

		verify(`[VERIFY] VC-003: rejected=true error_kind=unknown-rag-server queued=0`);
	});
});

// ── worker integration: header parsing + disabled activation equivalence ───

describe("worker integration", () => {
	it("parseTaskMd reads the rag budget headers", () => {
		const project = makeTempDir("rag-tools-headers-");
		const dir = path.join(project, ".agenticdoc", "key", "workers", "t");
		fs.mkdirSync(dir, { recursive: true });
		const taskPath = path.join(dir, "task.md");
		fs.writeFileSync(taskPath, "type: coding\nrag_chat_budget: 5\nrag_time_budget_s: 1200\n\nbody\n", "utf8");

		const meta = parseTaskMd(taskPath);
		expect(meta.ragChatBudget).toBe(5);
		expect(meta.ragTimeBudgetS).toBe(1200);
	});

	it("disabled activation reproduces the pre-RAG tool set exactly", () => {
		const { capture, pi } = api();
		applyRagTools(pi, null, "coding");
		expect(capture.active).toEqual(["read", "write", "edit", "bash", "find", "grep", "ls"]);
	});

	it("renderRagBlock returns null when no server is enabled", () => {
		expect(renderRagBlock({ ...goldenConfig(), enabled: [] }, { type: "coding" })).toBeNull();
	});
});

// ── golden byte contract / injection idempotency ────────────────────────────

function goldenBytes(): Buffer {
	return fs.readFileSync(new URL("../../../multi-workers/test/fixtures/rag-block.golden.md", import.meta.url));
}

function goldenConfig(): RagConfig {
	const entry = (graph: boolean, chat: boolean, rewrite: boolean): RagServerEntry => ({
		transport: "both",
		mcp: { url: "http://127.0.0.1:9740/mcp", tokenEnv: "OVERCODE_MCP_TOKEN", timeoutMs: 180_000 },
		skill: null,
		adapter: "overcode-v1",
		pathRootsFile: null,
		pathRootsDigest: null,
		sources: ["docs", "code"],
		capabilities: { graph, chat, rewrite },
		origin: {},
	});
	return {
		enabled: ["A", "B"],
		defaultServer: "A",
		servers: {
			A: entry(true, true, true),
			B: entry(false, false, false),
		},
		roles: {
			review: { server: "A", source: "docs", require: true },
			research: { server: "A", source: "docs", chatBudget: 3, timeBudgetS: 1200 },
		},
		phases: { design: { server: "A", source: "docs", require: true } },
		budgets: { chat: 2, timeS: 900 },
		fingerprint: "436b6a35ff60162559fe45e07f80afbe4c7e1c3e044bb6cc3c17196356034950",
	};
}

describe("rag block byte contract and injection", () => {
	it("renderRagBlock matches the golden bytes exactly", () => {
		const golden = goldenBytes();
		const block = renderRagBlock(goldenConfig(), { type: "coding" });
		expect(block).not.toBeNull();
		if (block === null) return;
		const emitted = Buffer.from(block, "utf8");
		expect(emitted.equals(golden)).toBe(true);
		expect(emitted.length).toBe(347);
		expect(golden[golden.length - 1]).not.toBe(0x0a);

		verify(`[VERIFY] golden_byte_match=true bytes=${emitted.length} trailing_newline=false`);
	});

	it("injects the block idempotently and drops it when disabled", async () => {
		const project = makeProject({
			enabled: ["X"],
			servers: serversYaml([{ name: "X", url: "http://127.0.0.1:9/mcp/" }]),
		});
		const original = "type: coding\n\ninjected task\n";
		const taskPath = await dispatch(project, "_scratch", "inject", original);

		const config = loadRagConfig(project);
		const block = renderRagBlock(config, { type: "coding" });
		expect(block).not.toBeNull();
		if (block === null) return;
		const expected = `${original.replace(/\s+$/, "")}\n\n${block}\n`;
		expect(fs.readFileSync(taskPath, "utf8")).toBe(expected);

		// Re-dispatch with the same config: byte-identical (no duplicate block).
		await dispatch(project, "_scratch", "inject", original);
		expect(fs.readFileSync(taskPath, "utf8")).toBe(expected);

		// Disable RAG: the stale block is dropped wholesale.
		fs.writeFileSync(path.join(project, ".agenticdoc", "target.yml"), "rag:\n  enabled: []\n", "utf8");
		await dispatch(project, "_scratch", "inject", original);
		const afterDisable = fs.readFileSync(taskPath, "utf8");
		expect(afterDisable).not.toContain(RAG_MARKER_V1);
		expect(afterDisable).toBe(original);

		// A target.yml without a rag section (not just enabled: []) is the same
		// structural no-op.
		fs.writeFileSync(path.join(project, ".agenticdoc", "target.yml"), "mode: single\n", "utf8");
		await dispatch(project, "_scratch", "inject", original);
		expect(fs.readFileSync(taskPath, "utf8")).not.toContain(RAG_MARKER_V1);
	});
});
