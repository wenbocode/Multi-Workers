/**
 * rag-research-doc.test.ts — `rag-research` type wiring + research-document
 * validation + the `rag_chat` per-call timeout floor (mw-rag-integration T-09).
 *
 *   VC-015  the `rag-research` allowlist is the 11-tool RAG set, order-exact;
 *           `roleForTaskType` maps it to the research role; `rag_chat` is
 *           visible only for that type.
 *   (T-09)  `rag_chat` gets `max(mcp.timeout_ms, 600s)`, retrieval tools keep
 *           the configured value, an explicit larger config wins.
 *   VC-018  a `<server>-<slug>.md` doc with the six fixed sections and
 *           D-004-parseable citations (at least one `::`) validates; a missing
 *           section / an unparseable citation / no doc fails.
 *
 * The suite config uses `silent: "passed-only"`, which swallows console.log
 * from green tests — every `[VERIFY]` line goes through process.stdout.write.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	researchDocEvidence,
	summarizeResearchDoc,
	validateResearchDoc,
} from "../../src/extensions/agent-team-loop/rag/research-doc.ts";
import {
	applyRagTools,
	RAG_CHAT_TIMEOUT_MS,
	RAG_CHAT_TOOL_NAME,
	type RagRuntime,
	ragCallTimeoutMs,
	ragToolNamesForType,
} from "../../src/extensions/agent-team-loop/rag/tools.ts";
import { DISPATCHABLE_TYPES, roleForTaskType } from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";
import { toolsForType } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

// ── capturing ExtensionAPI (register/setActiveTools only) ───────────────────

interface CapturedTool {
	name: string;
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
		// registration-time handlers are irrelevant here
	}
}

function api(): { capture: CapturingApi; pi: ExtensionAPI } {
	const capture = new CapturingApi();
	return { capture, pi: capture as unknown as ExtensionAPI };
}

/** Minimal runtime surface used by `applyRagTools` / `ragToolNamesForType`. */
function chatRuntime(): RagRuntime {
	return {
		config: { enabled: ["A"] },
		reachable: new Map<string, boolean>(),
		chatRegistered: false,
	} as unknown as RagRuntime;
}

// ── VC-015: allowlist + role + rag_chat gating ──────────────────────────────

const RAG_RESEARCH_TOOLS = [
	"read",
	"find",
	"grep",
	"ls",
	"rag_search",
	"rag_symbol",
	"rag_graph",
	"rag_impact",
	"rag_sources",
	"rag_feedback",
	"rag_chat",
];

describe("rag-research type wiring (VC-015)", () => {
	it("registers the 11-tool allowlist order-exact and maps to the research role", () => {
		const tools = toolsForType("rag-research");
		expect(tools).toEqual(RAG_RESEARCH_TOOLS);
		expect(tools.length).toBe(11);
		expect(roleForTaskType("rag-research")).toBe("research");
		expect([...DISPATCHABLE_TYPES]).toContain("rag-research");

		verify(`[VERIFY] VC-015: parity_unchanged=pass tools=${tools.length} conductor_dispatchable=false`);
	});

	it("exposes rag_chat only for rag-research", () => {
		const { capture, pi } = api();
		const runtime = chatRuntime();

		applyRagTools(pi, runtime, "rag-research");
		expect(capture.active).toContain(RAG_CHAT_TOOL_NAME);
		expect(capture.tools.has(RAG_CHAT_TOOL_NAME)).toBe(true);

		for (const type of ["coding", "review", "research", "verifier", "roadmap-writer"]) {
			expect(ragToolNamesForType(runtime, type), type).not.toContain(RAG_CHAT_TOOL_NAME);
			applyRagTools(pi, runtime, type);
			expect(capture.active, type).not.toContain(RAG_CHAT_TOOL_NAME);
		}

		verify(`[VERIFY] VC-015: rag_chat_visible_only_for=rag-research gated_types=5`);
	});
});

// ── rag_chat per-call timeout floor (T-09) ──────────────────────────────────

describe("rag_chat per-call timeout (T-09)", () => {
	it("floors rag_chat at 600s, keeps retrieval at the configured value", () => {
		expect(RAG_CHAT_TIMEOUT_MS).toBe(600_000);
		expect(ragCallTimeoutMs("rag_chat", { timeoutMs: 180_000 })).toBe(600_000);
		expect(ragCallTimeoutMs("rag_search", { timeoutMs: 180_000 })).toBe(180_000);
		expect(ragCallTimeoutMs("rag_symbol", { timeoutMs: 300_000 })).toBe(300_000);
		// `max` semantics: an explicit larger configuration always wins.
		expect(ragCallTimeoutMs("rag_chat", { timeoutMs: 900_000 })).toBe(900_000);
		expect(ragCallTimeoutMs("rag_graph", { timeoutMs: 60_000 })).toBe(60_000);

		verify(
			`[VERIFY] rag_chat_timeout: chat=${ragCallTimeoutMs("rag_chat", { timeoutMs: 180_000 })} ` +
				`retrieval=${ragCallTimeoutMs("rag_search", { timeoutMs: 180_000 })} ` +
				`configured_override=${ragCallTimeoutMs("rag_chat", { timeoutMs: 900_000 })}`,
		);
	});
});

// ── VC-018: research document validation ────────────────────────────────────

const COMPLIANT_DOC = `# RAG 调研：symbol lookup

## 查询

原始问题：X 在哪里定义。子问题：谁调用它。

## 结论

- 结论 A：X 定义于 Runtime/Renderer/X.cpp。

## 引用

- \`overcode:code:engine::Runtime/Renderer/X.cpp:120\` exists=true local_path=E:/proj/Runtime/Renderer/X.cpp
- \`overcode:docs:guide/rag.md:8\` exists=true local_path=E:/proj/guide/rag.md

## 未解决

- 无（全部可核对）。

## 快照

- 索引快照：2026-09-22T10:00:00Z；snapshot_warning=true。

## 影响面

- Runtime/Renderer 与调用方。
`;

const tempDirs: string[] = [];

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function makeKeyDir(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rag-research-doc-"));
	tempDirs.push(dir);
	return dir;
}

function writeDoc(keyDir: string, name: string, body: string): string {
	const ragDir = path.join(keyDir, "rag");
	fs.mkdirSync(ragDir, { recursive: true });
	const docPath = path.join(ragDir, name);
	fs.writeFileSync(docPath, body, "utf8");
	return docPath;
}

describe("research document validation (VC-018)", () => {
	it("accepts a compliant <server>-<slug>.md with six sections and parseable citations", () => {
		const keyDir = makeKeyDir();
		const docPath = writeDoc(keyDir, "overcode-symbol-lookup.md", COMPLIANT_DOC);
		const report = validateResearchDoc(keyDir);

		expect(report.ok).toBe(true);
		expect(report.docPath).toBe(docPath);
		expect(report.headings).toEqual(["## 查询", "## 结论", "## 引用", "## 未解决", "## 快照", "## 影响面"]);
		expect(report.missingSections).toEqual([]);
		expect(report.citations).toEqual([
			"overcode:code:engine::Runtime/Renderer/X.cpp:120",
			"overcode:docs:guide/rag.md:8",
		]);
		expect(report.unparseable).toEqual([]);
		expect(report.hasDoubleColon).toBe(true);
		expect(researchDocEvidence(report, "rag-research", "execute", "overcode")).toBeNull();

		verify(`[VERIFY] VC-018: ${summarizeResearchDoc(report)}`);
	});

	it("rejects a doc missing one fixed section and names it", () => {
		const keyDir = makeKeyDir();
		writeDoc(
			keyDir,
			"overcode-symbol-lookup.md",
			COMPLIANT_DOC.replace(/\n## 快照[\s\S]*?\n## 影响面/, "\n## 影响面"),
		);
		const report = validateResearchDoc(keyDir);

		expect(report.ok).toBe(false);
		expect(report.missingSections).toEqual(["快照"]);
		expect(report.findings.join("\n")).toContain("## 快照");
		expect(report.headings).toHaveLength(5);

		verify(`[VERIFY] VC-018: missing_section_detected=true sections=${report.headings.length}`);
	});

	it("rejects an unparseable citation", () => {
		const keyDir = makeKeyDir();
		writeDoc(keyDir, "overcode-symbol-lookup.md", COMPLIANT_DOC.replace(/:\d+` exists/, ":not-a-line` exists"));
		const report = validateResearchDoc(keyDir);

		expect(report.ok).toBe(false);
		expect(report.unparseable.length).toBeGreaterThan(0);
		expect(report.findings.join("\n")).toContain("not parseable");

		verify(`[VERIFY] VC-018: unparseable_citation_detected=true count=${report.unparseable.length}`);
	});

	it("rejects a doc with no '::' role-prefixed citation", () => {
		const keyDir = makeKeyDir();
		writeDoc(
			keyDir,
			"overcode-symbol-lookup.md",
			COMPLIANT_DOC.replace("engine::Runtime/Renderer/X.cpp", "Runtime/Renderer/X.cpp"),
		);
		const report = validateResearchDoc(keyDir);

		expect(report.ok).toBe(false);
		expect(report.hasDoubleColon).toBe(false);
		expect(report.findings.join("\n")).toContain("'::'");
	});

	it("rejects a missing document and yields the shared rag-required-missing line", () => {
		const keyDir = makeKeyDir();
		const report = validateResearchDoc(keyDir);

		expect(report.ok).toBe(false);
		expect(report.docPath).toBeNull();
		expect(report.missingSections).toEqual(["查询", "结论", "引用", "未解决", "快照", "影响面"]);
		expect(researchDocEvidence(report, "rag-research", "execute", "overcode")).toBe(
			"rag-required-missing role=rag-research phase=execute server=overcode",
		);

		verify(`[VERIFY] VC-018: missing_doc_detected=true sections=0`);
	});

	it("rejects a doc that does not follow the <server>-<slug>.md name shape", () => {
		const keyDir = makeKeyDir();
		writeDoc(keyDir, "research.md", COMPLIANT_DOC);
		const report = validateResearchDoc(keyDir);

		expect(report.ok).toBe(false);
		expect(report.findings.join("\n")).toContain("<server>-<slug>.md");
	});
});
