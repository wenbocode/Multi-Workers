import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { describe, expect, it } from "vitest";
import { formatFileOperations } from "../../src/core/compaction/utils.ts";
import { createCompactionSummaryMessage } from "../../src/core/messages.ts";
import type { CompactionEntry } from "../../src/core/session-manager.ts";
import {
	projectFileHistoryMessages,
	projectNativeFileHistory,
} from "../../src/extensions/agent-team-loop/shared/context-file-history.ts";
import { DEFAULT_FILE_HISTORY_MAX_BYTES } from "../../src/extensions/agent-team-loop/shared/context-policy.ts";

function compaction(readFiles: string[], modifiedFiles: string[] = []): CompactionEntry {
	return {
		type: "compaction",
		id: "native-history",
		parentId: null,
		timestamp: "2026-11-17T00:00:00.000Z",
		firstKeptEntryId: "kept",
		tokensBefore: 100000,
		summary: `Goal and current changes${formatFileOperations(readFiles, modifiedFiles)}`,
		details: { readFiles, modifiedFiles },
	};
}

describe("native file history context limit", () => {
	it("keeps the exact byte boundary and replaces the next byte without losing durable history", () => {
		const overhead = Buffer.byteLength(formatFileOperations([""], []), "utf8");
		const at = compaction(["x".repeat(DEFAULT_FILE_HISTORY_MAX_BYTES - overhead)]);
		expect(projectNativeFileHistory(at)).toBe(at.summary);
		const over = compaction(["x".repeat(DEFAULT_FILE_HISTORY_MAX_BYTES - overhead + 1)]);
		const original = structuredClone(over);
		expect(projectNativeFileHistory(over)).toBe(
			"Goal and current changes\n\n[File history: 1 read-only, 0 modified; showing 0 recent paths. Full lists remain in local session entry native-history details.]",
		);
		expect(over).toEqual(original);
	});

	it("counts UTF-8 and both lists together", () => {
		const entry = compaction(["中".repeat(700)], ["文".repeat(700)]);
		expect(entry.summary.length).toBeLessThan(DEFAULT_FILE_HISTORY_MAX_BYTES);
		expect(projectNativeFileHistory(entry)).not.toContain("<read-files>");
		expect(projectNativeFileHistory(entry)).toContain("1 read-only, 1 modified");
	});

	it("keeps short lists in continuation but excludes them from the next summarization", () => {
		const entry = compaction(["src/read.ts"], ["src/changed.ts"]);
		expect(projectNativeFileHistory(entry)).toBe(entry.summary);
		expect(projectNativeFileHistory(entry, 0)).not.toMatch(/src\/|<read-files>|<modified-files>/);
		expect(projectNativeFileHistory(entry, 0)).toContain("Goal and current changes");
	});

	it("bounds duplicated historical blocks while preserving prose between them", () => {
		const entry = compaction(["a".repeat(2500)], ["src/changed.ts"]);
		entry.summary = `Original goal${formatFileOperations(["a".repeat(2500)], [])}\n\nNew work${formatFileOperations(["a".repeat(2500)], ["src/changed.ts"])}`;
		const projected = projectNativeFileHistory(entry);
		expect(projected).toContain("Original goal\n\nNew work");
		expect(projected.match(/<read-files>/g)).toHaveLength(1);
		expect(projected).toContain("1 read-only, 1 modified");
	});

	it("leaves unverified suffixes, custom summaries and unrelated XML in prose untouched", () => {
		const entry = compaction(["x".repeat(9000)]);
		expect(projectNativeFileHistory({ ...entry, fromHook: true })).toBe(entry.summary);
		expect(projectNativeFileHistory({ ...entry, details: { readFiles: [42], modifiedFiles: [] } })).toBe(
			entry.summary,
		);
		const mismatch = { ...entry, summary: `${entry.summary}\nUser prose after the list` };
		expect(projectNativeFileHistory(mismatch)).toBe(mismatch.summary);
		const example = "\n\n<read-files>\nkeep-this-example.ts\n</read-files>";
		expect(projectNativeFileHistory({ ...entry, summary: example + entry.summary })).toContain(example);
	});

	it("recognizes an older read-only list when its files have since moved to modified history", () => {
		const file = "a".repeat(2500);
		const entry = compaction([], [file]);
		entry.summary = `Original goal${formatFileOperations([file], [])}\n\nNew change${formatFileOperations([], [file])}`;
		expect(projectNativeFileHistory(entry)).not.toContain("<read-files>");
		expect(projectNativeFileHistory(entry).match(/<modified-files>/g)).toHaveLength(1);
		expect(projectNativeFileHistory(entry)).toContain("Original goal\n\nNew change");
	});

	it("evicts the least recent paths and refreshes repeated accesses across read and modified lists", () => {
		const entry = compaction(["src/a.ts", "src/b.ts", "src/c.ts"], ["src/d.ts"]);
		const maxBytes = Buffer.byteLength(formatFileOperations(["src/c.ts", "src/a.ts"], []), "utf8");
		const projected = projectNativeFileHistory(entry, maxBytes, ["src/b.ts", "src/d.ts", "src/a.ts", "src/c.ts"]);
		expect(projected).toContain("src/c.ts\nsrc/a.ts");
		expect(projected).not.toMatch(/src\/b.ts|src\/d.ts/);
		expect(projected).toContain("showing 2 recent paths");
	});

	it("reconstructs access order from local tool calls instead of alphabetically sorted details", () => {
		const entry = compaction(["src/a.ts", "src/b.ts", "src/c.ts"]);
		const call = (path: string, index: number) => ({
			type: "message" as const,
			id: `call-${index}`,
			parentId: null,
			timestamp: entry.timestamp,
			message: {
				role: "assistant" as const,
				api: "openai-completions" as const,
				provider: "fixture",
				model: "fixture",
				content: [{ type: "toolCall" as const, id: `tool-${index}`, name: "read", arguments: { path } }],
				usage: {
					input: 0,
					output: 0,
					cacheRead: 0,
					cacheWrite: 0,
					totalTokens: 0,
					cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
				},
				stopReason: "toolUse" as const,
				timestamp: 0,
			},
		});
		const entries = [call("src/a.ts", 0), call("src/b.ts", 1), call("src/c.ts", 2), call("src/a.ts", 3), entry];
		const messages = [createCompactionSummaryMessage(entry.summary, entry.tokensBefore, entry.timestamp)];
		const maxBytes = Buffer.byteLength(formatFileOperations(["src/a.ts", "src/c.ts"], []), "utf8");
		const projected = projectFileHistoryMessages(messages, entries, maxBytes);
		expect(JSON.stringify(projected)).toContain("src/a.ts\\nsrc/c.ts");
		expect(JSON.stringify(projected)).not.toContain("src/b.ts");
	});

	it("projects only native summary messages, including branch summaries, without mutating input", () => {
		const entry = compaction(["x".repeat(9000)]);
		const branch = { ...entry, type: "branch_summary" as const, fromId: "old-branch", id: "branch-history" };
		const messages: AgentMessage[] = [
			createCompactionSummaryMessage(entry.summary, entry.tokensBefore, entry.timestamp),
			{
				role: "branchSummary",
				summary: branch.summary,
				fromId: branch.fromId,
				timestamp: Date.parse(branch.timestamp),
			},
			{ role: "user", content: entry.summary, timestamp: 0 },
			createCompactionSummaryMessage(entry.summary, entry.tokensBefore, "2026-11-17T00:00:01.000Z"),
		];
		const original = structuredClone(messages);
		const projected = projectFileHistoryMessages(messages, [entry, branch]);
		expect(JSON.stringify(projected.slice(0, 2))).not.toContain("<read-files>");
		expect(projected[2]).toBe(messages[2]);
		expect(projected[3]).toBe(messages[3]);
		expect(messages).toEqual(original);
	});
});
