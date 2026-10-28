/**
 * rag-role-defaults.test.ts — role/phase defaults actually wired at runtime
 * (mw-rag-integration-fix T-15, review finding F-1).
 *
 * The pre-fix bug: `rewriteDefaults` existed and was unit-tested, but
 * `callRag` never consulted it, so a
 * research role that left `multi_rounds` open still emitted `rag_search`.
 *
 *   VC-101  role=design + server rewrite capability, no explicit switch ->
 *           the *fixture-observed* wire name is `rag_search_multi_rounds`;
 *           role=coding -> `rag_search`; an explicit `multi_rounds: false`
 *           still wins.
 *   VC-102  role declaration `server: B` routes the call to B's url while an
 *           explicit `server: A` overrides the role default.
 *   VC-110  no role/phase (the PM-session path) injects nothing: still
 *           `rag_search`, still `default_server`, zero new files.
 *   VC-008  emitted here from the fixture observation (the old pure-function
 *           line in `rag-adapter.test.ts` was removed; the assertions stay).
 *
 * `[VERIFY]` lines go straight to stdout: the suite config is
 * `silent: "passed-only"` and swallows `console.log` from green tests (P-006).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { type RagRuntime, registerRagTools } from "../../src/extensions/agent-team-loop/rag/tools.ts";
import { type RagFixture, startRagFixture } from "./rag-fixture.ts";

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

// ── capturing ExtensionAPI (same shape as rag-tools.test.ts) ────────────────

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
	registerTool(tool: unknown): void {
		const captured = tool as CapturedTool;
		this.tools.set(captured.name, captured);
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

function makeTempDir(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

/** A hermetic control root: target.yml + project rag-servers.yml, machine layer disabled. */
function makeProject(targetBody: string, serversBody: string): string {
	const project = makeTempDir("rag-role-defaults-");
	fs.mkdirSync(path.join(project, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(project, ".agenticdoc", "target.yml"), targetBody, "utf8");
	fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(project, ".mw", "rag-servers.yml"), serversBody, "utf8");
	if (!serversFileSaved) {
		savedServersFile = process.env.MW_RAG_SERVERS_FILE;
		serversFileSaved = true;
	}
	process.env.MW_RAG_SERVERS_FILE = path.join(project, ".machine-servers-does-not-exist.yml");
	return project;
}

function serversYaml(entries: Array<{ name: string; url: string; rewrite?: boolean }>): string {
	const lines = ["servers:"];
	for (const entry of entries) {
		lines.push(`  ${entry.name}:`);
		lines.push("    transport: mcp");
		lines.push("    mcp:");
		lines.push(`      url: ${entry.url}`);
		lines.push("      token_env: RAG_ROLE_DEFAULTS_TEST_TOKEN");
		lines.push("    capabilities:");
		lines.push("      graph: false");
		lines.push("      chat: false");
		lines.push(`      rewrite: ${entry.rewrite ?? false}`);
	}
	return `${lines.join("\n")}\n`;
}

async function makeFixture(): Promise<RagFixture> {
	const fixture = await startRagFixture({
		tools: {
			rag_search: () => ({ results: [] }),
			rag_search_multi_rounds: () => ({ results: [] }),
		},
	});
	fixtures.push(fixture);
	return fixture;
}

/** Every `tools/call` name the fixture actually observed (the wire contract). */
function observedWires(fixture: RagFixture): string[] {
	return fixture.calls.filter((call) => call.method === "tools/call").map((call) => call.name ?? "");
}

/** Snapshot the project tree so "no new files" is an actual byte comparison. */
function snapshotTree(root: string): Record<string, string> {
	const out: Record<string, string> = {};
	const walk = (dir: string, prefix: string): void => {
		for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
			const rel = prefix === "" ? entry.name : `${prefix}/${entry.name}`;
			const abs = path.join(dir, entry.name);
			if (entry.isDirectory()) walk(abs, rel);
			else out[rel] = fs.readFileSync(abs, "utf8");
		}
	};
	walk(root, "");
	return out;
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

async function searchOnce(
	capture: CapturingApi,
	fixture: RagFixture,
	params: Record<string, unknown>,
): Promise<{ wire: string[]; details: unknown }> {
	const baseline = observedWires(fixture).length;
	const result = await toolOf(capture, "rag_search").execute("call-1", params);
	return { wire: observedWires(fixture).slice(baseline), details: result.details };
}

// ── VC-101 / VC-008: the rewrite default reaches the wire ───────────────────

describe("VC-101 role rewrite default at runtime", () => {
	it("routes design to rag_search_multi_rounds and coding to rag_search", async () => {
		const fixture = await makeFixture();
		const project = makeProject(
			"rag:\n  enabled: [A]\n  default_server: A\n  roles:\n    design:\n      server: A\n",
			serversYaml([{ name: "A", url: fixture.url, rewrite: true }]),
		);

		const design = api();
		const designRuntime = registerRagTools(design.pi, project, { role: "design", phase: "" });
		expect(designRuntime).not.toBeNull();
		await (designRuntime as RagRuntime).ready;
		const designCall = await searchOnce(design.capture, fixture, { query: "how does X work" });
		expect(designCall.wire).toEqual(["rag_search_multi_rounds"]);

		// An explicit switch always wins over the role default (D-102).
		const explicitOff = await searchOnce(design.capture, fixture, { query: "q", multi_rounds: false });
		expect(explicitOff.wire).toEqual(["rag_search"]);

		const coding = api();
		const codingRuntime = registerRagTools(coding.pi, project, { role: "coding", phase: "" });
		expect(codingRuntime).not.toBeNull();
		await (codingRuntime as RagRuntime).ready;
		const codingCall = await searchOnce(coding.capture, fixture, { query: "how does X work" });
		expect(codingCall.wire).toEqual(["rag_search"]);

		// VC-008 (AC-102): fields come from the fixture observation, not from a
		// pure function and not from the returned envelope.
		expect(designCall.wire.length).toBe(1);
		expect(codingCall.wire.length).toBe(1);
		verify(
			`[VERIFY] VC-008: role=design rewrite_tool=${designCall.wire[0]} explicit=false ` +
				`fixture_calls=${designCall.wire.length} coding_tool=${codingCall.wire[0]}`,
		);
		verify(
			`[VERIFY] VC-101: design_wire=${designCall.wire[0]} coding_wire=${codingCall.wire[0]} explicit_off_wire=rag_search`,
		);
	});
});

// ── VC-102: role server default, explicit overrides ─────────────────────────

describe("VC-102 role server default", () => {
	it("sends the call to the role's server unless the agent overrides it", async () => {
		const fixtureA = await makeFixture();
		const fixtureB = await makeFixture();
		const project = makeProject(
			"rag:\n  enabled: [A, B]\n  default_server: A\n  roles:\n    design:\n      server: B\n",
			serversYaml([
				{ name: "A", url: fixtureA.url },
				{ name: "B", url: fixtureB.url },
			]),
		);

		const { capture, pi } = api();
		const runtime = registerRagTools(pi, project, { role: "design", phase: "" });
		expect(runtime).not.toBeNull();
		await (runtime as RagRuntime).ready;

		// No explicit server -> the role declaration picks B.
		const roleDefault = await searchOnce(capture, fixtureB, { query: "q" });
		expect(roleDefault.wire).toEqual(["rag_search"]);
		const roleHitsA = observedWires(fixtureA).length;
		const roleHitsB = observedWires(fixtureB).length;
		expect(roleHitsA).toBe(0);
		expect(roleHitsB).toBe(1);

		// Explicit server: A overrides the role default.
		const explicit = await searchOnce(capture, fixtureA, { query: "q", server: "A" });
		expect(explicit.wire).toEqual(["rag_search"]);
		const explicitHitsA = observedWires(fixtureA).length;
		const explicitHitsB = observedWires(fixtureB).length;
		expect(explicitHitsA).toBe(1);
		expect(explicitHitsB).toBe(1);

		// Evidence line fields come from the fixture observations above (AC-108),
		// not from literal labels.
		verify(
			`[VERIFY] VC-102: role_server=B role_hits_a=${roleHitsA} role_hits_b=${roleHitsB} ` +
				`explicit_server=A explicit_hits_a=${explicitHitsA} explicit_hits_b=${explicitHitsB} ` +
				`role_default_wire=${roleDefault.wire[0]} explicit_wire=${explicit.wire[0]}`,
		);
	});
});

// ── VC-110: no role/phase = zero intervention (PM session) ──────────────────

describe("VC-110 no role/phase leaves the request unchanged", () => {
	it("keeps rag_search on default_server and writes no file", async () => {
		const fixture = await makeFixture();
		const project = makeProject(
			"rag:\n  enabled: [A]\n  default_server: A\n",
			serversYaml([{ name: "A", url: fixture.url, rewrite: true }]),
		);
		const before = snapshotTree(project);

		const { capture, pi } = api();
		const runtime = registerRagTools(pi, project);
		expect(runtime).not.toBeNull();
		await (runtime as RagRuntime).ready;
		expect((runtime as RagRuntime).role).toBe("");
		expect((runtime as RagRuntime).phase).toBe("");

		// Server A declares rewrite:true, but with no role/phase the default is
		// not applied (D-103): the wire name stays `rag_search`.
		const call = await searchOnce(capture, fixture, { query: "q" });
		expect(call.wire).toEqual(["rag_search"]);
		expect(observedWires(fixture)).toEqual(["rag_search"]);
		expect(snapshotTree(project)).toEqual(before);

		verify(`[VERIFY] VC-110: role="" phase="" wire=${call.wire[0]} server=default_server files_added=0`);
	});
});
