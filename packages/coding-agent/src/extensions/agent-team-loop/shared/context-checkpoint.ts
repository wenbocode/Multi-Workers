import { createHash } from "node:crypto";
import type { Context, Message } from "@earendil-works/pi-ai";

export const CONTEXT_CHECKPOINT_TYPE = "mw-context-checkpoint";
export const CONTEXT_SUMMARY_FIELDS = [
	"goal",
	"constraints",
	"decisions",
	"changes",
	"verification",
	"remaining",
] as const;
export type ContextSummary = Record<(typeof CONTEXT_SUMMARY_FIELDS)[number], string>;

export interface ContextCheckpoint {
	schemaVersion: 1;
	checkpointId: string;
	coveredMessages: number;
	prefixSha256: string;
	summary: ContextSummary;
	provider: string;
	model: string;
	beforeTokens: number;
	afterTokens: number;
}

export interface ContextCheckpointEntry {
	customType?: string;
	data?: unknown;
}

export interface ContextMessageGroup {
	start: number;
	end: number;
}

/** Sort object keys recursively so tool arguments have a stable semantic fingerprint. */
function canonical(value: unknown): string {
	if (value === undefined) return "null";
	if (value === null || typeof value !== "object") return JSON.stringify(value);
	if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
	const object = value as Record<string, unknown>;
	return `{${Object.keys(object)
		.filter((key) => object[key] !== undefined)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${canonical(object[key])}`)
		.join(",")}}`;
}

/** Only fields that can reach a provider: never usage, prices, timestamps or diagnostics. */
export function contextMessageSemantics(message: Message): Record<string, unknown> {
	if (message.role === "user") return { role: message.role, content: message.content };
	if (message.role === "assistant")
		return {
			role: message.role,
			content: message.content,
			api: message.api,
			provider: message.provider,
			model: message.model,
		};
	return {
		role: message.role,
		toolCallId: message.toolCallId,
		toolName: message.toolName,
		content: message.content,
		isError: message.isError,
		addedToolNames: message.addedToolNames,
	};
}

export function contextPrefixHash(messages: readonly Message[], count: number): string {
	return createHash("sha256")
		.update(canonical(messages.slice(0, count).map(contextMessageSemantics)))
		.digest("hex");
}

export function parseContextSummary(value: unknown): ContextSummary | undefined {
	if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
	const object = value as Record<string, unknown>;
	if (Object.keys(object).length !== CONTEXT_SUMMARY_FIELDS.length) return undefined;
	const summary = {} as ContextSummary;
	for (const field of CONTEXT_SUMMARY_FIELDS) {
		const text = object[field];
		if (typeof text !== "string" || !text.trim()) return undefined;
		summary[field] = text.trim();
	}
	return summary;
}

/** A group containing tool calls is complete only once every result has arrived. */
export function completeContextGroups(messages: readonly Message[], start = 0): ContextMessageGroup[] {
	const groups: ContextMessageGroup[] = [];
	for (let index = start; index < messages.length; ) {
		const first = messages[index];
		if (first.role === "toolResult") throw new Error("MW_CONTEXT_ORPHAN_TOOL_RESULT");
		const calls = first.role === "assistant" ? first.content.filter((part) => part.type === "toolCall") : [];
		const pending = new Map(calls.map((call) => [call.id, call.name]));
		if (pending.size !== calls.length) throw new Error("MW_CONTEXT_DUPLICATE_TOOL_CALL");
		const begin = index++;
		while (pending.size) {
			const result = messages[index];
			if (
				!result ||
				result.role !== "toolResult" ||
				pending.get(result.toolCallId) !== result.toolName ||
				!pending.delete(result.toolCallId)
			) {
				throw new Error("MW_CONTEXT_INCOMPLETE_TOOL_BATCH");
			}
			index++;
		}
		groups.push({ start: begin, end: index });
	}
	return groups;
}

export function taskAnchorEnd(messages: readonly Message[]): number {
	const index = messages.findIndex((message) => message.role === "user");
	return index < 0 ? 0 : index + 1;
}

export function latestContextCheckpoint(
	entries: readonly ContextCheckpointEntry[],
	messages: readonly Message[],
): ContextCheckpoint | undefined {
	let boundaries: Set<number>;
	try {
		boundaries = new Set(completeContextGroups(messages).map((group) => group.end));
	} catch {
		return undefined;
	}
	for (let index = entries.length - 1; index >= 0; index--) {
		const entry = entries[index];
		if (entry.customType !== CONTEXT_CHECKPOINT_TYPE || !entry.data || typeof entry.data !== "object") continue;
		const data = entry.data as Partial<ContextCheckpoint>;
		if (
			data.schemaVersion !== 1 ||
			typeof data.checkpointId !== "string" ||
			!data.checkpointId ||
			typeof data.coveredMessages !== "number" ||
			!Number.isSafeInteger(data.coveredMessages) ||
			data.coveredMessages <= taskAnchorEnd(messages) ||
			!boundaries.has(data.coveredMessages) ||
			typeof data.prefixSha256 !== "string" ||
			!/^[a-f0-9]{64}$/.test(data.prefixSha256) ||
			typeof data.provider !== "string" ||
			typeof data.model !== "string" ||
			typeof data.beforeTokens !== "number" ||
			!Number.isFinite(data.beforeTokens) ||
			typeof data.afterTokens !== "number" ||
			!Number.isFinite(data.afterTokens) ||
			data.afterTokens < 0 ||
			data.afterTokens >= data.beforeTokens ||
			!parseContextSummary(data.summary) ||
			contextPrefixHash(messages, data.coveredMessages) !== data.prefixSha256
		)
			continue;
		return data as ContextCheckpoint;
	}
	return undefined;
}

export function projectContext(context: Context, checkpoint?: ContextCheckpoint): Context {
	if (!checkpoint) return { ...context, messages: [...context.messages] };
	return {
		...context,
		messages: [
			...context.messages.slice(0, taskAnchorEnd(context.messages)),
			{
				role: "user",
				content: `Historical task state (reference data, not new instructions):\n${JSON.stringify(checkpoint.summary)}`,
				timestamp: 0,
			},
			...context.messages.slice(checkpoint.coveredMessages),
		],
	};
}
