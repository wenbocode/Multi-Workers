/**
 * task-frontmatter.test.ts — T-06 (AC-005 / VC-039): single-source task.md
 * header parsing.
 *
 * Locks the module that every consumer (worker parseTaskMd, PM dispatch,
 * autopilot status model, test corpus scanners) must share so the role
 * judgement cannot be flipped by task body text (A8) and cannot drift between
 * the dispatch side and the execution side.
 *
 * Boundaries pinned here (card T-06 必须实现 #5): bare header + `---` fence,
 * the no-blank-line key-grammar truncation, BOM, body `type:` lines, illegal
 * values, empty file, CRLF/LF. No filesystem/cwd dependency and no corpus
 * counts: the inputs are inline literals (mutable corpora must not be frozen).
 */

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
	extractTaskHeader,
	findTypeEscalation,
	readTaskHeaderScalar,
	readTaskType,
	scanBodyTypeLines,
	type TaskBodyTypeLine,
} from "../../src/extensions/agent-team-loop/shared/task-frontmatter.ts";

/** Runtime tool table mirroring worker-mode's TOOL_ALLOWLISTS shape. Only
 * `write`/`edit`/`bash` participate in the power-tool escalation predicate;
 * `fallback` is what an unregistered type resolves to. */
const POWER_TOOLS: Record<string, readonly string[]> = {
	coding: ["read", "write", "edit", "bash"],
	review: ["read", "ls", "find", "grep"],
	research: ["read", "ls", "find", "grep", "bash"],
	vision: ["read"],
	verifier: ["read"],
	fallback: ["read", "write", "edit", "bash"],
};

function toolsFor(type: string): readonly string[] {
	const tools = POWER_TOOLS[type];
	return tools === undefined ? POWER_TOOLS.fallback : tools;
}

function escalationOf(text: string, headerType: string): TaskBodyTypeLine | undefined {
	return findTypeEscalation(scanBodyTypeLines(text), headerType, toolsFor);
}

describe("extractTaskHeader — header region boundary", () => {
	it("an unfenced header ends at the first blank line", () => {
		expect(extractTaskHeader("type: coding\n\nwork\n")).toEqual({
			startLine: 0,
			endLine: 0,
			fenced: false,
			truncated: false,
			byteOrderMark: false,
		});
	});

	it("keeps all leading key lines of an unfenced header", () => {
		expect(extractTaskHeader("type: review\nphase: SPEC\nmodel: x\n\nwork\n").endLine).toBe(2);
	});

	it("does not treat a bare --- below line 1 as a fence (read-scope fixture shape)", () => {
		const region = extractTaskHeader("type: verifier\nread_scope:\n---\n\nwork\n");
		expect(region).toEqual({
			startLine: 0,
			endLine: 2,
			fenced: false,
			truncated: false,
			byteOrderMark: false,
		});
		expect(readTaskHeaderScalar("type: verifier\nread_scope:\n---\n\nwork\n", "type")).toBe("verifier");
	});

	it("only the first line can open a fence", () => {
		const region = extractTaskHeader("\n---\ntype: coding\n\nwork\n");
		expect(region).toMatchObject({ startLine: 0, endLine: -1, fenced: false });
	});

	it("a fenced header runs to the first closing --- ", () => {
		expect(extractTaskHeader("---\ntype: research\norigin: conductor\n---\n\nwork\n")).toEqual({
			startLine: 1,
			endLine: 2,
			fenced: true,
			truncated: false,
			byteOrderMark: false,
		});
	});

	it("an empty fenced header yields an empty region", () => {
		expect(extractTaskHeader("---\n---\n\nwork\n")).toMatchObject({ startLine: 1, endLine: 0, fenced: true });
	});

	it("an unclosed fence falls back to the blank-line rule, never to an empty header", () => {
		expect(extractTaskHeader("---\ntype: coding\n\nwork\n")).toMatchObject({
			startLine: 0,
			endLine: 1,
			fenced: false,
			truncated: false,
		});
	});

	it("with no blank line the header is the leading key-grammar run (truncated)", () => {
		expect(extractTaskHeader("type: coding\nwork without blank line\n")).toEqual({
			startLine: 0,
			endLine: 0,
			fenced: false,
			truncated: true,
			byteOrderMark: false,
		});
	});

	it("with no blank line the key run absorbs indented block-list items", () => {
		expect(extractTaskHeader("type: verifier\nread_scope:\n  - a\n  - b\n")).toMatchObject({
			startLine: 0,
			endLine: 3,
			truncated: true,
		});
	});

	it("with no blank line and a prose first line the header is empty and truncated", () => {
		expect(extractTaskHeader("# title\nwork")).toMatchObject({
			startLine: 0,
			endLine: -1,
			fenced: false,
			truncated: true,
		});
	});

	it("a leading blank line yields an empty header", () => {
		expect(extractTaskHeader("\ntype: coding\n\nwork\n")).toMatchObject({
			startLine: 0,
			endLine: -1,
			fenced: false,
			truncated: false,
		});
	});

	it("an empty file yields an empty header", () => {
		expect(extractTaskHeader("")).toEqual({
			startLine: 0,
			endLine: -1,
			fenced: false,
			truncated: false,
			byteOrderMark: false,
		});
	});

	it("a lone newline still yields an empty header", () => {
		expect(extractTaskHeader("\n")).toMatchObject({ startLine: 0, endLine: -1 });
	});

	it("strips a BOM and reports it", () => {
		expect(extractTaskHeader("\uFEFFtype: vision\n\nwork\n")).toEqual({
			startLine: 0,
			endLine: 0,
			fenced: false,
			truncated: false,
			byteOrderMark: true,
		});
	});

	it("normalizes CRLF line endings and still finds the blank separator", () => {
		expect(extractTaskHeader("type: repair\r\n\r\nwork\r\n")).toMatchObject({
			startLine: 0,
			endLine: 0,
			byteOrderMark: false,
		});
	});

	it("treats a CR-only line as the blank separator", () => {
		expect(extractTaskHeader("type: coding\r\rwork\r")).toMatchObject({ startLine: 0, endLine: 0 });
	});

	it("accepts a fenced CRLF header", () => {
		expect(extractTaskHeader("---\r\ntype: coding\r\n---\r\n\r\nwork\r\n")).toMatchObject({
			startLine: 1,
			endLine: 1,
			fenced: true,
			byteOrderMark: false,
		});
	});
});

describe("readTaskHeaderScalar — first key wins", () => {
	it("returns the first occurrence of a duplicated key", () => {
		expect(readTaskHeaderScalar("type: coding\nphase: SPEC\ntype: review\n\nwork\n", "type")).toBe("coding");
	});

	it("returns undefined for an absent key", () => {
		expect(readTaskHeaderScalar("type: coding\n\nwork\n", "phase")).toBeUndefined();
	});

	it("returns an empty string for a present-but-empty key", () => {
		expect(readTaskHeaderScalar("type:\n\nwork\n", "type")).toBe("");
	});

	it("does not match a key by prefix (type-x is not type)", () => {
		expect(readTaskHeaderScalar("type-x: coding\n\nwork\n", "type")).toBeUndefined();
	});

	it("does not match a near-miss colon form (type :)", () => {
		expect(readTaskHeaderScalar("type : coding\n\nwork\n", "type")).toBeUndefined();
	});

	it("trims the value but never strips quotes", () => {
		expect(readTaskHeaderScalar("type:   coding   \n\nwork\n", "type")).toBe("coding");
		expect(readTaskHeaderScalar('type: "coding"\n\nwork\n', "type")).toBe('"coding"');
	});

	it("parses a BOM-prefixed document", () => {
		expect(readTaskHeaderScalar("\uFEFFtype: vision\n\nwork\n", "type")).toBe("vision");
	});

	it("does not read keys below the header boundary", () => {
		expect(readTaskHeaderScalar("type: coding\n\nphase: SPEC\n\nwork\n", "phase")).toBeUndefined();
	});
});

describe("readTaskType — provenance", () => {
	it("takes the header value and reports source=header", () => {
		expect(readTaskType("type: coding\n\nwork\n")).toEqual({
			type: "coding",
			source: "header",
			bomStripped: false,
		});
	});

	it("keeps the first of duplicated header keys", () => {
		expect(readTaskType("type: coding\nphase: SPEC\ntype: review\n\nwork\n")).toEqual({
			type: "coding",
			source: "header",
			bomStripped: false,
		});
	});

	it("never lets a body type: line flip the header (A8 injection)", () => {
		const text = "type: review\n\n# task\n\ntype: coding\n\nwork\n";
		expect(readTaskType(text)).toEqual({ type: "review", source: "header", bomStripped: false });
		expect(escalationOf(text, "review")).toEqual({ line: 5, value: "coding" });
	});

	it("reports source=body (and no type) when only the body carries one", () => {
		expect(readTaskType("# title\n\ntype: coding\n")).toEqual({
			type: undefined,
			source: "body",
			bomStripped: false,
		});
	});

	it("reports source=missing when no type: line exists", () => {
		expect(readTaskType("# title\n\nwork\n")).toEqual({
			type: undefined,
			source: "missing",
			bomStripped: false,
		});
	});

	it("reports source=invalid for a present-but-empty header value", () => {
		expect(readTaskType("type:\n\nwork\n")).toEqual({
			type: undefined,
			source: "invalid",
			bomStripped: false,
		});
	});

	it("keeps source=invalid even when the body carries a value (header is authoritative)", () => {
		expect(readTaskType("type:\n\ntype: coding\n")).toEqual({
			type: undefined,
			source: "invalid",
			bomStripped: false,
		});
	});

	it("treats a near-miss `type :` as missing, not as an illegal value", () => {
		expect(readTaskType("type : coding\n\nwork\n").source).toBe("missing");
	});

	it("parses a fenced header", () => {
		expect(readTaskType("---\ntype: research\norigin: conductor\n---\n\ntype: coding\n")).toEqual({
			type: "research",
			source: "header",
			bomStripped: false,
		});
	});

	it("parses CRLF input", () => {
		expect(readTaskType("type: repair\r\n\r\nwork\r\n")).toEqual({
			type: "repair",
			source: "header",
			bomStripped: false,
		});
	});

	it("strips BOM and flags it", () => {
		expect(readTaskType("\uFEFFtype: vision\n\nwork\n")).toEqual({
			type: "vision",
			source: "header",
			bomStripped: true,
		});
	});

	it("parses a BOM plus fenced header", () => {
		expect(readTaskType("\uFEFF---\ntype: coding\n---\n\nwork\n")).toEqual({
			type: "coding",
			source: "header",
			bomStripped: true,
		});
	});

	it("reports source=missing for an empty file", () => {
		expect(readTaskType("")).toEqual({ type: undefined, source: "missing", bomStripped: false });
	});

	it("keeps illegal-but-syntactic values verbatim for the consumer to reject", () => {
		expect(readTaskType("type: mystery-type\n\nwork\n").type).toBe("mystery-type");
	});

	it("always returns one of the four sources and never throws", () => {
		const hostile = [
			"",
			"\n",
			"\uFEFF",
			"---",
			"---\n---",
			"---\n---\n---\n",
			"\r\n",
			"type:",
			"type::",
			"  type:  ",
			"\uFEFF---\n---\n\n",
			"type: a\ntype: b\ntype: c\n",
			"type: coding\n\x00\n\nwork\n",
		];
		for (const text of hostile) {
			const reading = readTaskType(text);
			expect(["header", "body", "missing", "invalid"]).toContain(reading.source);
			expect(reading.bomStripped).toBe(text.startsWith("\uFEFF"));
		}
	});
});

describe("scanBodyTypeLines", () => {
	it("returns 1-based line numbers in order for LF input", () => {
		expect(scanBodyTypeLines("type: coding\n\n# work\n\ntype: review\n\ntype: coding\n")).toEqual([
			{ line: 5, value: "review" },
			{ line: 7, value: "coding" },
		]);
	});

	it("returns 1-based line numbers for CRLF input", () => {
		expect(scanBodyTypeLines("type: coding\r\n\r\nwork\r\n\r\ntype: review\r\n")).toEqual([
			{ line: 5, value: "review" },
		]);
	});

	it("skips the header region", () => {
		expect(scanBodyTypeLines("type: coding\nphase: SPEC\ntype: review\n\nwork\n")).toEqual([]);
	});

	it("skips the fenced header region and reads the body after it", () => {
		expect(scanBodyTypeLines("---\ntype: research\n---\n\ntype: coding\n")).toEqual([{ line: 5, value: "coding" }]);
	});

	it("ignores near-miss forms in the body", () => {
		expect(scanBodyTypeLines("# t\n\ntype : coding\ntype-x: y\nTYPE: z\n")).toEqual([]);
	});

	it("records an empty-value body line verbatim", () => {
		expect(scanBodyTypeLines("# t\n\ntype:\n")).toEqual([{ line: 3, value: "" }]);
	});

	it("returns an empty list when the body has no type: line", () => {
		expect(scanBodyTypeLines("type: coding\n\nwork\n")).toEqual([]);
	});

	it("scans the whole file when the header is empty", () => {
		expect(scanBodyTypeLines("\ntype: coding\n")).toEqual([{ line: 2, value: "coding" }]);
	});
});

describe("findTypeEscalation — power-tool non-subset", () => {
	it("flags a body type that adds write/edit/bash", () => {
		expect(escalationOf("type: review\n\nwork\n\ntype: coding\n", "review")).toEqual({
			line: 5,
			value: "coding",
		});
	});

	it("does not flag a body type that narrows capability", () => {
		expect(escalationOf("type: coding\n\nwork\n\ntype: review\n", "coding")).toBeUndefined();
	});

	it("does not flag a body type equal to the header", () => {
		expect(escalationOf("type: coding\n\nwork\n\ntype: coding\n", "coding")).toBeUndefined();
	});

	it("does not flag read-only tool differences", () => {
		expect(escalationOf("type: review\n\nwork\n\ntype: vision\n", "review")).toBeUndefined();
		expect(escalationOf("type: research\n\nwork\n\ntype: vision\n", "research")).toBeUndefined();
	});

	it("flags a body type that adds bash to a read-only header", () => {
		expect(escalationOf("type: review\n\nwork\n\ntype: research\n", "review")).toEqual({
			line: 5,
			value: "research",
		});
	});

	it("flags an unregistered body type (fallback carries write/edit/bash)", () => {
		expect(escalationOf("type: verifier\n\nwork\n\ntype: whatever\n", "verifier")).toEqual({
			line: 5,
			value: "whatever",
		});
	});

	it("returns the first escalating line when several exist", () => {
		expect(escalationOf("type: verifier\n\nwork\n\ntype: research\n\ntype: coding\n", "verifier")).toEqual({
			line: 5,
			value: "research",
		});
	});

	it("returns undefined for an empty body line list", () => {
		expect(findTypeEscalation([], "coding", toolsFor)).toBeUndefined();
	});

	it("compares only write/edit/bash, ignoring read-side lookups", () => {
		expect(findTypeEscalation([{ line: 1, value: "vision" }], "review", toolsFor)).toBeUndefined();
	});
});

describe("T-19/C-15+C-16 newline index space (AC-005)", () => {
	// The boundary judgement runs in ONE index space: `\r\n`, `\r`, U+2028 and
	// U+2029 fold to `\n` before anything is indexed, so the same bytes yield the
	// same header on both language sides (F-A4-1 lone-CR, F-A4-2 U+2028).
	it("folds lone CR into line breaks (positive)", () => {
		const text = "---\rtype: verifier\rloop: l2\r---\r";
		expect(extractTaskHeader(text)).toEqual({
			startLine: 1,
			endLine: 2,
			fenced: true,
			truncated: false,
			byteOrderMark: false,
		});
		expect(readTaskType(text)).toEqual({ type: "verifier", source: "header", bomStripped: false });
		expect(readTaskHeaderScalar(text, "loop")).toBe("l2");
		expect(scanBodyTypeLines(text)).toEqual([]);
	});

	it("does not pull a CR-separated body key into the header (negative)", () => {
		const text = "type: coding\n\nbody\rphase: SPEC\n";
		expect(extractTaskHeader(text)).toEqual({
			startLine: 0,
			endLine: 0,
			fenced: false,
			truncated: false,
			byteOrderMark: false,
		});
		expect(readTaskType(text)).toEqual({ type: "coding", source: "header", bomStripped: false });
		expect(readTaskHeaderScalar(text, "phase")).toBeUndefined();
	});

	it("folds a mixed CRLF/CR document (positive)", () => {
		const text = "---\r\ntype: review\r\n---\r\n\r\ntype: coding\r\n";
		expect(extractTaskHeader(text)).toEqual({
			startLine: 1,
			endLine: 1,
			fenced: true,
			truncated: false,
			byteOrderMark: false,
		});
		expect(readTaskType(text)).toEqual({ type: "review", source: "header", bomStripped: false });
		expect(scanBodyTypeLines(text)).toEqual([{ line: 5, value: "coding" }]);
	});

	it("keeps a CRLF body key below the blank separator (negative)", () => {
		const text = "type: coding\r\n\r\nphase: SPEC\r\n";
		expect(extractTaskHeader(text)).toEqual({
			startLine: 0,
			endLine: 0,
			fenced: false,
			truncated: false,
			byteOrderMark: false,
		});
		expect(readTaskType(text)).toEqual({ type: "coding", source: "header", bomStripped: false });
		expect(readTaskHeaderScalar(text, "phase")).toBeUndefined();
	});

	it("folds U+2028 into line breaks (positive)", () => {
		const text = "---\u2028type: verifier\u2028---\u2028";
		expect(extractTaskHeader(text)).toEqual({
			startLine: 1,
			endLine: 1,
			fenced: true,
			truncated: false,
			byteOrderMark: false,
		});
		expect(readTaskType(text)).toEqual({ type: "verifier", source: "header", bomStripped: false });
		expect(scanBodyTypeLines(text)).toEqual([]);
	});

	it("does not let a U+2028 body truncate or extend the header (negative)", () => {
		const text = "type: coding\nloop: l1\n\nwork\u2028with\u2028separators\n";
		expect(extractTaskHeader(text)).toEqual({
			startLine: 0,
			endLine: 1,
			fenced: false,
			truncated: false,
			byteOrderMark: false,
		});
		expect(readTaskType(text)).toEqual({ type: "coding", source: "header", bomStripped: false });
		expect(readTaskHeaderScalar(text, "loop")).toBe("l1");
		expect(readTaskHeaderScalar(text, "with")).toBeUndefined();
		expect(scanBodyTypeLines(text)).toEqual([]);
	});
});

describe("module purity", () => {
	it("is dependency-free (no imports, no node: modules, no cwd)", () => {
		const source = readFileSync(
			new URL("../../src/extensions/agent-team-loop/shared/task-frontmatter.ts", import.meta.url),
			"utf8",
		);
		expect(source).not.toMatch(/^\s*import\s/m);
		expect(source).not.toMatch(/from\s+["']node:/);
		expect(source).not.toContain("process.cwd");
		expect(source).not.toContain("require(");
	});

	it("does not throw on hostile input for any exported function", () => {
		const hostile = ["", "\uFEFF", "---", "---\n", "\r\n", "type:", "\x00", "type: a\r\ntype: b"];
		for (const text of hostile) {
			expect(() => extractTaskHeader(text)).not.toThrow();
			expect(() => readTaskHeaderScalar(text, "type")).not.toThrow();
			expect(() => readTaskType(text)).not.toThrow();
			expect(() => scanBodyTypeLines(text)).not.toThrow();
			expect(() => findTypeEscalation(scanBodyTypeLines(text), "coding", toolsFor)).not.toThrow();
		}
	});
});
