/**
 * rag-adapter.test.ts — overcode-v1 adapter contract (mw-rag-integration T-02).
 *
 * Pure-function coverage for the citation grammar (VC-026), normalization plus
 * local existence checks (VC-006), the unconfigured-vs-missing distinction
 * (VC-007) and the rewrite defaults (VC-008).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	capabilityError,
	formatCitation,
	loadPathRoots,
	normalizeResults,
	parseCitation,
	resolveLocalPath,
} from "../../src/extensions/agent-team-loop/rag/adapter.ts";
import { RagConfigError, rewriteDefaults } from "../../src/extensions/agent-team-loop/rag/config.ts";

const tempDirs: string[] = [];

function makeTmpDir(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rag-adapter-"));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/**
 * The suite config sets `silent: "passed-only"`, which swallows console.log
 * from green tests. Write the machine-readable VERIFY evidence straight to
 * stdout so the required command surfaces it.
 */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

describe("citation grammar (VC-026)", () => {
	const cases = [
		"engine::Runtime/Renderer/X.cpp",
		"Runtime/Renderer/X.cpp",
		"Source Files/My Header.h",
		"Engine\\Source\\X.cpp",
		"源码/角色.cpp",
	];

	it("round-trips all five contract shapes", () => {
		let roundTrips = 0;
		for (const filePath of cases) {
			const citation = formatCitation({ server: "overcode", source: "engine-code", filePath, line: 123 });
			expect(parseCitation(citation)).toEqual({ server: "overcode", source: "engine-code", filePath, line: 123 });
			roundTrips++;
		}
		expect(roundTrips).toBe(5);
		verify(`[VERIFY] VC-026: grammar_cases=${cases.length} roundtrip=${roundTrips}/${cases.length}`);
	});

	it("never splits a file_path containing ':' into server/source", () => {
		expect(parseCitation("srv:src:engine::Runtime/X.cpp:7")).toEqual({
			server: "srv",
			source: "src",
			filePath: "engine::Runtime/X.cpp",
			line: 7,
		});
		expect(parseCitation("srv:src:a:b::c.cpp:41")).toEqual({
			server: "srv",
			source: "src",
			filePath: "a:b::c.cpp",
			line: 41,
		});
	});

	it("rejects malformed citations", () => {
		expect(parseCitation("only-two:parts")).toBeNull();
		expect(parseCitation("srv:src:file.cpp:abc")).toBeNull();
		expect(parseCitation("srv::file.cpp:1")).toBeNull();
		expect(parseCitation(":src:file.cpp:1")).toBeNull();
		expect(parseCitation("srv:src:file.cpp:")).toBeNull();
	});

	it("rejects a ':' inside server/source when formatting", () => {
		expect(() => formatCitation({ server: "a:b", source: "src", filePath: "f.cpp", line: 1 })).toThrow(
			RagConfigError,
		);
		expect(() => formatCitation({ server: "srv", source: "a:b", filePath: "f.cpp", line: 1 })).toThrow(
			RagConfigError,
		);
	});
});

describe("normalization and local resolution (VC-006)", () => {
	it("maps a result item onto the normalized absolute local path", () => {
		const root = makeTmpDir();
		const relative = "Runtime/Renderer/X.cpp";
		fs.mkdirSync(path.join(root, "Runtime", "Renderer"), { recursive: true });
		fs.writeFileSync(path.join(root, "Runtime", "Renderer", "X.cpp"), "// renderer\n");

		const raw = {
			results: [
				{
					file_path: "engine::Runtime/Renderer/X.cpp",
					symbol_name: "X::Render",
					qualified_name: "X::Render",
					symbol_type: "method",
					line_start: 123,
					line_end: 140,
					content: "void X::Render() {}",
					score: 0.87,
				},
			],
		};
		const envelope = normalizeResults("overcode", "rag_search", "engine-code", raw, { engine: root });

		expect(envelope.snapshot).toBe(true);
		expect(envelope.items).toHaveLength(1);
		const item = envelope.items[0];
		expect(item.local_path).toBe(path.resolve(root, relative));
		expect(item.exists).toBe(true);
		expect(item.line_hint).toBe(123);
		expect(item.snapshot_warning).toBe(true);
		expect(item.symbol_name).toBe("X::Render");
		expect(item.citation).toBe("overcode:engine-code:engine::Runtime/Renderer/X.cpp:123");
		expect(parseCitation(item.citation ?? "")).toEqual({
			server: "overcode",
			source: "engine-code",
			filePath: "engine::Runtime/Renderer/X.cpp",
			line: 123,
		});
		verify("[VERIFY] VC-006: citation_roundtrip=true line_hint=123 exists=true");
	});

	it("keeps local_path separate from citation and preserves meta", () => {
		const raw = {
			total_callers: 2,
			affected_files: ["engine::A.cpp", "engine::B.cpp"],
			static_analysis: true,
			rewrite_degraded: false,
			callers_by_hop: { "1": [] },
		};
		const envelope = normalizeResults("overcode", "rag_impact", "src", raw, null);
		expect(envelope.items).toHaveLength(2);
		expect(envelope.meta.total_callers).toBe(2);
		expect(envelope.meta.static_analysis).toBe(true);
		expect(envelope.meta.rewrite_degraded).toBe(false);
		expect(envelope.items[0].citation).toBeNull();
		expect(envelope.items[0].local_path).toBeNull();
		expect(envelope.items[0].file_path).toBe("engine::A.cpp");
	});

	it("throws on invalid response shapes instead of emitting an empty envelope", () => {
		expect(() => normalizeResults("srv", "rag_search", "src", { unexpected: true }, null)).toThrow(RagConfigError);
		expect(() => normalizeResults("srv", "rag_search", "src", null, null)).toThrow(RagConfigError);
		expect(() => normalizeResults("srv", "rag_search", "src", [1, 2], null)).toThrow(RagConfigError);
		expect(() => normalizeResults("srv", "rag_search", "src", { results: [{}] }, null)).toThrow(RagConfigError);
	});

	it("accepts an empty result array without throwing", () => {
		const envelope = normalizeResults("srv", "rag_search", "src", { results: [] }, null);
		expect(envelope.items).toEqual([]);
	});
});

describe("path_roots contract (VC-007)", () => {
	it("distinguishes unconfigured mapping from a missing file", () => {
		const roots = loadPathRoots(null);
		expect(roots).toBeNull();

		const unconfigured = resolveLocalPath("engine::Runtime/Renderer/X.cpp", roots);
		expect(unconfigured.localPath).toBeNull();
		expect(unconfigured.exists).toBe(false);
		expect(unconfigured.reason).toContain("path_roots");

		const envelope = normalizeResults(
			"overcode",
			"rag_search",
			"src",
			{ results: [{ file_path: "engine::Runtime/Renderer/X.cpp", line_start: 5 }] },
			null,
		);
		expect(envelope.items[0].local_path).toBeNull();
		expect(envelope.items[0].exists).toBe(false);
		expect(String(envelope.meta.hint)).toContain("path_roots");

		const root = makeTmpDir();
		const missing = resolveLocalPath("engine::Runtime/Gone.cpp", { engine: root });
		expect(missing.exists).toBe(false);
		expect(missing.localPath).toBe(path.resolve(root, "Runtime/Gone.cpp"));
		expect(missing.reason).toContain("file missing");
		expect(missing.reason).not.toBe(unconfigured.reason);

		verify("[VERIFY] VC-007: unconfigured_hint=true missing_file_distinct=true");
	});

	it("loads a BOM-prefixed mapping and ignores '_'-prefixed keys", () => {
		const root = makeTmpDir();
		const mappingFile = path.join(makeTmpDir(), "path-roots.json");
		fs.writeFileSync(mappingFile, `\uFEFF${JSON.stringify({ _README: "ignored", engine: root })}`, "utf8");

		const roots = loadPathRoots(mappingFile);
		expect(roots).toEqual({ engine: root });
		expect(loadPathRoots(path.join(makeTmpDir(), "absent.json"))).toBeNull();
	});

	it("throws on malformed mapping content", () => {
		const mappingFile = path.join(makeTmpDir(), "bad.json");
		fs.writeFileSync(mappingFile, "{not json", "utf8");
		expect(() => loadPathRoots(mappingFile)).toThrow(RagConfigError);
	});

	it("rejects traversal outside the role root", () => {
		const root = makeTmpDir();
		const traversal = resolveLocalPath("engine::../outside.cpp", { engine: root });
		expect(traversal.localPath).toBeNull();
		expect(traversal.exists).toBe(false);
		expect(traversal.reason).toContain("traversal");
	});

	it("rejects unknown roles and lists the available roles", () => {
		const root = makeTmpDir();
		const unknown = resolveLocalPath("engine::", { project: root });
		expect(unknown.localPath).toBeNull();
		expect(unknown.exists).toBe(false);
		expect(unknown.reason).toContain("engine");
		expect(unknown.reason).toContain("project");
	});

	it("defaults bare paths to the engine role and normalizes separators", () => {
		const root = makeTmpDir();
		const expected = path.resolve(root, "Runtime/Renderer/X.cpp");
		expect(resolveLocalPath("Runtime/Renderer/X.cpp", { engine: root }).localPath).toBe(expected);
		expect(resolveLocalPath("Engine\\Source\\X.cpp", { engine: root }).localPath).toBe(
			path.resolve(root, "Engine/Source/X.cpp"),
		);
		expect(resolveLocalPath("/Runtime/Renderer/X.cpp", { engine: root }).localPath).toBe(expected);
	});
});

describe("rewrite defaults (VC-008)", () => {
	it("enables rewrite for research-like roles/phases when the capability is on", () => {
		expect(rewriteDefaults("research", "execute", true)).toBe(true);
		expect(rewriteDefaults("spec", "execute", true)).toBe(true);
		expect(rewriteDefaults("rag-research", "execute", true)).toBe(true);
		expect(rewriteDefaults("coding", "design", true)).toBe(true);

		expect(rewriteDefaults("coding", "execute", true)).toBe(false);
		expect(rewriteDefaults("review", "execute", true)).toBe(false);
		expect(rewriteDefaults("research", "execute", false)).toBe(false);

		expect(rewriteDefaults("coding", "execute", true, true)).toBe(true);
		expect(rewriteDefaults("research", "execute", true, false)).toBe(false);
	});
});

describe("capability errors", () => {
	it("returns a structured capability error for graph tools", () => {
		const error = capabilityError("overcode", "rag_graph", { graph: false, chat: true });
		expect(error).not.toBeNull();
		expect(error?.kind).toBe("capability");
		expect(error?.message).toContain("no knowledge graph");
		expect(capabilityError("overcode", "rag_impact", { graph: false, chat: true })?.kind).toBe("capability");
		expect(capabilityError("overcode", "rag_chat", { graph: true, chat: false })?.kind).toBe("capability");
		expect(capabilityError("overcode", "rag_search", { graph: false, chat: false })).toBeNull();
	});
});
