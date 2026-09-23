/**
 * rag-toolmap.test.ts — logical tool name -> server tool name mapping
 * (mw-rag-integration T-13, VC-028 / AC-006).
 *
 * T-04 sent the logical names straight to `McpSession.callTool`. The reference
 * service (`adapter: overcode-v1`) uses different wire names:
 *   rag_graph -> graph_query
 *   rag_sources -> list_sources + list_collections (merged into one envelope)
 *   rag_search (rewrite switch on) -> rag_search_multi_rounds
 * The remaining logical names are identical.
 *
 * Every mapping assertion reads the **actually emitted** name from
 * `fixture.calls[].name` — the VC-028 judgement criterion. The suite config is
 * `silent: "passed-only"`, so the evidence line is written with
 * `process.stdout.write`.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { mergeToolResponses, parseCitation, ragToolCalls } from "../../src/extensions/agent-team-loop/rag/adapter.ts";
import { ENV_RAG_SERVERS_FILE, RagConfigError } from "../../src/extensions/agent-team-loop/rag/config.ts";
import { type RagRuntime, registerRagTools } from "../../src/extensions/agent-team-loop/rag/tools.ts";
import { type RagFixture, type RagFixtureCall, startRagFixture } from "./rag-fixture.ts";

/* The suite swallows console.log from green tests; write the evidence line
 * straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

const BASE_LOGICAL_TOOLS = ["rag_search", "rag_symbol", "rag_graph", "rag_impact", "rag_sources", "rag_feedback"];

// ── capturing ExtensionAPI (same shape as T-04's rag-tools.test.ts) ─────────

interface CapturedTool {
	name: string;
	parameters: unknown;
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

interface EnvelopeLike {
	server: string;
	tool: string;
	source: string | null;
	items: Array<{
		symbol_name: string;
		symbol_type: string | null;
		file_path: string;
		snippet: string | null;
		citation: string | null;
		snapshot_warning: boolean;
	}>;
	mcp_tool?: string;
}

interface ErrorLike {
	kind: string;
	server: string;
	tool: string;
	message: string;
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

function makeProject(url: string): string {
	const project = makeTempDir("rag-toolmap-");
	fs.mkdirSync(path.join(project, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(project, ".agenticdoc", "target.yml"), "rag:\n  enabled: [A]\n", "utf8");
	fs.writeFileSync(
		path.join(project, ".mw", "rag-servers.yml"),
		[
			"servers:",
			"  A:",
			"    transport: mcp",
			"    mcp:",
			`      url: ${url}`,
			"      token_env: RAG_TOOLMAP_TEST_TOKEN",
			"    capabilities:",
			"      graph: true",
			"      chat: true",
			"      rewrite: true",
			"",
		].join("\n"),
		"utf8",
	);
	if (!serversFileSaved) {
		savedServersFile = process.env[ENV_RAG_SERVERS_FILE];
		serversFileSaved = true;
	}
	// Hermetic machine layer: hard override to a non-existent file.
	process.env[ENV_RAG_SERVERS_FILE] = path.join(project, ".machine-servers-does-not-exist.yml");
	return project;
}

async function makeFixture(
	tools: Record<string, (args: Record<string, unknown>, call: number) => unknown>,
): Promise<RagFixture> {
	const fixture = await startRagFixture({ tools });
	fixtures.push(fixture);
	return fixture;
}

interface Ran {
	fresh: RagFixtureCall[];
	details: unknown;
}

/** Register the surface against a project and return the captured tools. */
async function registerFor(fixture: RagFixture): Promise<{ capture: CapturingApi; runtime: RagRuntime }> {
	const project = makeProject(fixture.url);
	const { capture, pi } = api();
	const runtime = registerRagTools(pi, project);
	expect(runtime).not.toBeNull();
	if (runtime === null) throw new Error("rag runtime was not created");
	await runtime.ready;
	return { capture, runtime };
}

/** Execute one logical tool and slice the requests it emitted. */
async function run(
	capture: CapturingApi,
	fixture: RagFixture,
	name: string,
	params: Record<string, unknown>,
): Promise<Ran> {
	const before = fixture.calls.length;
	const result = await toolOf(capture, name).execute("call-1", params);
	return { fresh: fixture.calls.slice(before), details: result.details };
}

// ── VC-028: name mapping read from the wire ─────────────────────────────────

describe("logical -> server tool name mapping (VC-028)", () => {
	it("emits the reference service tool names for all six base tools", async () => {
		const fixture = await makeFixture({
			graph_query: (args) => ({
				symbol: args.symbol_name,
				operation: args.operation,
				results: [{ file_path: "engine::src/A.cpp", line_start: 3 }],
			}),
			rag_symbol: () => ({ file_path: "engine::src/A.cpp", line_start: 4, name: "Foo" }),
			rag_impact: () => ({ symbol: "Foo", total_callers: 1, affected_files: ["engine::src/A.cpp"] }),
			rag_feedback: () => ({ status: "ok" }),
			rag_search: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 9 }], total_count: 1 }),
			rag_search_multi_rounds: () => ({ documents: [{ file_path: "engine::src/A.cpp", line_start: 9 }] }),
			list_sources: () => ({ sources: [{ name: "engine-code", collections: [{ name: "engine", role: "" }] }] }),
			list_collections: () => ({ collections: [{ name: "engine", chunk_count: 12 }] }),
		});
		const { capture } = await registerFor(fixture);

		// rag_graph -> graph_query (never the logical name).
		const graph = await run(capture, fixture, "rag_graph", {
			server: "A",
			operation: "callers",
			symbol_name: "Foo",
		});
		expect(graph.fresh.map((call) => call.name)).toEqual(["graph_query"]);
		expect(graph.fresh.map((call) => call.name)).not.toContain("rag_graph");
		expect((graph.details as EnvelopeLike).mcp_tool).toBe("graph_query");

		// Identical names stay identical.
		const symbol = await run(capture, fixture, "rag_symbol", { server: "A", symbol_name: "Foo" });
		expect(symbol.fresh.map((call) => call.name)).toEqual(["rag_symbol"]);
		const impact = await run(capture, fixture, "rag_impact", { server: "A", symbol: "Foo" });
		expect(impact.fresh.map((call) => call.name)).toEqual(["rag_impact"]);
		const feedback = await run(capture, fixture, "rag_feedback", {
			server: "A",
			title: "t",
			tool: "rag_search",
			expected: "a",
			actual: "b",
		});
		expect(feedback.fresh.map((call) => call.name)).toEqual(["rag_feedback"]);

		// Rewrite switch on: multi-round server tool, no multi_rounds/auto_rewrite args.
		const rewritten = await run(capture, fixture, "rag_search", {
			server: "A",
			query: "renderer",
			source: "engine-code",
			multi_rounds: true,
		});
		expect(rewritten.fresh.map((call) => call.name)).toEqual(["rag_search_multi_rounds"]);
		expect(rewritten.fresh[0].args).not.toHaveProperty("multi_rounds");
		expect(rewritten.fresh[0].args).not.toHaveProperty("auto_rewrite");
		expect(rewritten.fresh[0].args.query).toBe("renderer");
		expect(rewritten.fresh[0].args.source).toBe("engine-code");
		expect((rewritten.details as EnvelopeLike).mcp_tool).toBe("rag_search_multi_rounds");

		// Rewrite switch off: plain rag_search keeps the business args.
		const plain = await run(capture, fixture, "rag_search", {
			server: "A",
			query: "renderer",
			collection: "engine",
			top_k: 5,
			multi_rounds: false,
		});
		expect(plain.fresh.map((call) => call.name)).toEqual(["rag_search"]);
		expect(plain.fresh[0].args.query).toBe("renderer");
		expect(plain.fresh[0].args.collection).toBe("engine");
		expect(plain.fresh[0].args.top_k).toBe(5);

		// rag_sources fans out into exactly two reads, merged into one envelope.
		const sources = await run(capture, fixture, "rag_sources", { server: "A" });
		expect(sources.fresh.map((call) => call.name).sort()).toEqual(["list_collections", "list_sources"]);
		const sourcesEnvelope = sources.details as EnvelopeLike;
		expect(sourcesEnvelope.tool).toBe("rag_sources");
		expect(sourcesEnvelope.mcp_tool).toBe("list_sources+list_collections");

		// rag_chat is mapped one-for-one too (not part of the six base tools).
		expect(ragToolCalls("rag_chat", { max_recall_rounds: 2 }).map((call) => call.name)).toEqual(["rag_chat"]);

		const resolved = BASE_LOGICAL_TOOLS.filter((name) => {
			try {
				return ragToolCalls(name, {}).length > 0;
			} catch {
				return false;
			}
		});
		expect(resolved.length).toBe(6);
		verify(
			"[VERIFY] VC-028: " +
				`mapped_names=${resolved.length}/${BASE_LOGICAL_TOOLS.length} sources_merged=true ` +
				"multi_rounds_tool=rag_search_multi_rounds",
		);
	});

	it("merges both listing payloads with source/collection attribution", async () => {
		const fixture = await makeFixture({
			list_sources: () => ({ sources: [{ name: "docs", collections: [{ name: "manual", role: "docs" }] }] }),
			list_collections: () => ({ collections: [{ name: "engine", chunk_count: 42 }] }),
		});
		const { capture } = await registerFor(fixture);

		const ran = await run(capture, fixture, "rag_sources", { server: "A" });
		const envelope = ran.details as EnvelopeLike;

		expect(envelope.items).toHaveLength(2);
		const kinds = envelope.items.map((item) => `${item.symbol_type}:${item.symbol_name}`).sort();
		expect(kinds).toEqual(["collection:engine", "source:docs"]);
		const sourceItem = envelope.items.find((item) => item.symbol_type === "source");
		const collectionItem = envelope.items.find((item) => item.symbol_type === "collection");
		expect(sourceItem?.snippet).toContain("manual");
		expect(collectionItem?.snippet).toContain("chunk_count");
		expect(envelope.mcp_tool).toBe("list_sources+list_collections");
	});

	it("fails the whole rag_sources call when one leg fails (no partial merge)", async () => {
		const fixture = await makeFixture({
			list_sources: () => ({ sources: [{ name: "docs", collections: [] }] }),
			list_collections: () => {
				throw new Error("collections index not ready");
			},
		});
		const { capture } = await registerFor(fixture);

		const ran = await run(capture, fixture, "rag_sources", { server: "A" });
		const failure = ran.details as ErrorLike;

		// Both legs were attempted; the second one failed and nothing was merged.
		expect(ran.fresh.map((call) => call.name).sort()).toEqual(["list_collections", "list_sources"]);
		expect(failure.kind).toBe("tool");
		expect(failure.tool).toBe("rag_sources");
		expect(failure.message).toContain("collections index not ready");
		expect((ran.details as { items?: unknown }).items).toBeUndefined();
	});

	it("throws RagConfigError for an unknown logical name with zero requests", async () => {
		const fixture = await makeFixture({});
		const { capture } = await registerFor(fixture);
		const baseline = fixture.calls.length;

		let caught: unknown;
		try {
			ragToolCalls("rag_nope", {});
		} catch (error) {
			caught = error;
		}
		expect(caught).toBeInstanceOf(RagConfigError);
		expect(() => mergeToolResponses("rag_nope", [])).toThrow(RagConfigError);
		// The captured surface never even reaches the transport for this name.
		expect(capture.tools.size).toBe(6);
		expect(fixture.calls.length).toBe(baseline);
	});

	it("keeps the D-004 citation round-trip through the mapped call", async () => {
		const filePath = "engine::Runtime/Renderer/X.cpp";
		const fixture = await makeFixture({
			rag_search: () => ({ documents: [{ file_path: filePath, line_start: 123 }] }),
		});
		const { capture } = await registerFor(fixture);

		const ran = await run(capture, fixture, "rag_search", {
			server: "A",
			query: "renderer",
			source: "engine-code",
		});
		expect(ran.fresh.map((call) => call.name)).toEqual(["rag_search"]);
		const envelope = ran.details as EnvelopeLike;
		expect(envelope.items).toHaveLength(1);
		expect(parseCitation(envelope.items[0].citation ?? "")).toEqual({
			server: "A",
			source: "engine-code",
			filePath,
			line: 123,
		});
	});
});
