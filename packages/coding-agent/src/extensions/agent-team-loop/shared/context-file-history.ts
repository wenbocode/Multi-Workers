import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { formatFileOperations } from "../../../core/compaction/utils.ts";
import type { BranchSummaryEntry, CompactionEntry, SessionEntry } from "../../../core/session-manager.ts";
import { DEFAULT_FILE_HISTORY_MAX_BYTES } from "./context-policy.ts";

/** Only project an exact native-generated suffix; durable summary/details stay untouched. */
export function projectNativeFileHistory(
	entry: CompactionEntry | BranchSummaryEntry,
	maxBytes = DEFAULT_FILE_HISTORY_MAX_BYTES,
	recentPaths: readonly string[] = [],
): string {
	if (entry.fromHook || !entry.details || typeof entry.details !== "object") return entry.summary;
	const { readFiles, modifiedFiles } = entry.details as Record<string, unknown>;
	if (
		!Array.isArray(readFiles) ||
		!Array.isArray(modifiedFiles) ||
		!readFiles.every((file): file is string => typeof file === "string") ||
		!modifiedFiles.every((file): file is string => typeof file === "string")
	)
		return entry.summary;
	const suffix = formatFileOperations(readFiles, modifiedFiles);
	if (!suffix || !entry.summary.endsWith(suffix)) return entry.summary;
	let bytes = Buffer.byteLength(suffix, "utf8");
	const inventories = {
		"read-files": new Set([...readFiles, ...modifiedFiles]),
		"modified-files": new Set(modifiedFiles),
	};
	// Older split-turn summaries can contain earlier copies before the final native suffix.
	const prose = entry.summary
		.slice(0, -suffix.length)
		.replace(
			/\n\n<(read-files|modified-files)>\n([\s\S]*?)\n<\/\1>/g,
			(block: string, tag: string, paths: string) => {
				const inventory = inventories[tag as keyof typeof inventories];
				if (!paths.split("\n").every((path) => inventory.has(path))) return block;
				bytes += Buffer.byteLength(block, "utf8");
				return "";
			},
		);
	if (bytes <= maxBytes) return entry.summary;
	const modified = new Set(modifiedFiles);
	// Unknown legacy ordering comes first; known accesses move their paths to the recent end.
	const ordered = new Set([...readFiles, ...modifiedFiles]);
	for (const path of recentPaths) {
		if (!ordered.delete(path)) continue;
		ordered.add(path);
	}
	const keptRead: string[] = [];
	const keptModified: string[] = [];
	for (const path of [...ordered].reverse()) {
		const kept = modified.has(path) ? keptModified : keptRead;
		kept.push(path);
		if (Buffer.byteLength(formatFileOperations(keptRead, keptModified), "utf8") > maxBytes) kept.pop();
	}
	return `${prose}${formatFileOperations(keptRead, keptModified)}\n\n[File history: ${readFiles.length} read-only, ${modifiedFiles.length} modified; showing ${keptRead.length + keptModified.length} recent paths. Full lists remain in local session entry ${entry.id} details.]`;
}

/** Apply the same projection to admission estimates and actual context events, including resumed sessions. */
export function projectFileHistoryMessages(
	messages: AgentMessage[],
	entries: readonly SessionEntry[],
	maxBytes = DEFAULT_FILE_HISTORY_MAX_BYTES,
): AgentMessage[] {
	const summaries = new Map<string, string>();
	const recentPaths = new Set<string>();
	const wanted = new Set(
		messages
			.filter((message) => message.role === "compactionSummary" || message.role === "branchSummary")
			.map((message) => `${message.role}\0${message.timestamp}`),
	);
	for (const entry of entries) {
		if (entry.type === "message" && entry.message.role === "assistant") {
			for (const block of entry.message.content ?? []) {
				if (block.type !== "toolCall" || !["read", "write", "edit"].includes(block.name)) continue;
				const path = block.arguments?.path;
				if (typeof path !== "string") continue;
				recentPaths.delete(path);
				recentPaths.add(path);
			}
		}
		if (entry.type !== "compaction" && entry.type !== "branch_summary") continue;
		const role = entry.type === "compaction" ? "compactionSummary" : "branchSummary";
		if (!wanted.has(`${role}\0${Date.parse(entry.timestamp)}`)) continue;
		const summary = projectNativeFileHistory(entry, maxBytes, [...recentPaths]);
		if (summary !== entry.summary) {
			summaries.set(`${role}\0${Date.parse(entry.timestamp)}\0${entry.summary}`, summary);
		}
	}
	return messages.map((message) => {
		if (message.role !== "compactionSummary" && message.role !== "branchSummary") return message;
		const summary = summaries.get(`${message.role}\0${message.timestamp}\0${message.summary}`);
		return summary === undefined ? message : { ...message, summary };
	});
}
