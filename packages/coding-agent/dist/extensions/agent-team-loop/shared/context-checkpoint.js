import { createHash } from "node:crypto";
export const CONTEXT_CHECKPOINT_TYPE = "mw-context-checkpoint";
export const CONTEXT_SUMMARY_FIELDS = [
    "goal",
    "constraints",
    "decisions",
    "changes",
    "verification",
    "remaining",
];
/** Sort object keys recursively so tool arguments have a stable semantic fingerprint. */
function canonical(value) {
    if (value === undefined)
        return "null";
    if (value === null || typeof value !== "object")
        return JSON.stringify(value);
    if (Array.isArray(value))
        return `[${value.map(canonical).join(",")}]`;
    const object = value;
    return `{${Object.keys(object)
        .filter((key) => object[key] !== undefined)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${canonical(object[key])}`)
        .join(",")}}`;
}
/** Only fields that can reach a provider: never usage, prices, timestamps or diagnostics. */
export function contextMessageSemantics(message) {
    if (message.role === "user")
        return { role: message.role, content: message.content };
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
export function contextPrefixHash(messages, count) {
    return createHash("sha256")
        .update(canonical(messages.slice(0, count).map(contextMessageSemantics)))
        .digest("hex");
}
export function parseContextSummary(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return undefined;
    const object = value;
    if (Object.keys(object).length !== CONTEXT_SUMMARY_FIELDS.length)
        return undefined;
    const summary = {};
    for (const field of CONTEXT_SUMMARY_FIELDS) {
        const text = object[field];
        if (typeof text !== "string" || !text.trim())
            return undefined;
        summary[field] = text.trim();
    }
    return summary;
}
/** A group containing tool calls is complete only once every result has arrived. */
export function completeContextGroups(messages, start = 0) {
    const groups = [];
    for (let index = start; index < messages.length;) {
        const first = messages[index];
        if (first.role === "toolResult")
            throw new Error("MW_CONTEXT_ORPHAN_TOOL_RESULT");
        // Failed or cancelled provider attempts never execute their proposed tools.
        // pi retries may remove them from active memory while retaining session history.
        const calls = first.role === "assistant" && first.stopReason !== "error" && first.stopReason !== "aborted"
            ? first.content.filter((part) => part.type === "toolCall")
            : [];
        const pending = new Map(calls.map((call) => [call.id, call.name]));
        if (pending.size !== calls.length)
            throw new Error("MW_CONTEXT_DUPLICATE_TOOL_CALL");
        const begin = index++;
        while (pending.size) {
            const result = messages[index];
            if (!result ||
                result.role !== "toolResult" ||
                pending.get(result.toolCallId) !== result.toolName ||
                !pending.delete(result.toolCallId)) {
                throw new Error("MW_CONTEXT_INCOMPLETE_TOOL_BATCH");
            }
            index++;
        }
        groups.push({ start: begin, end: index });
    }
    return groups;
}
export function taskAnchorEnd(messages) {
    const index = messages.findIndex((message) => message.role === "user");
    return index < 0 ? 0 : index + 1;
}
export function latestContextCheckpoint(entries, messages) {
    let boundaries;
    try {
        boundaries = new Set(completeContextGroups(messages).map((group) => group.end));
    }
    catch {
        return undefined;
    }
    for (let index = entries.length - 1; index >= 0; index--) {
        const entry = entries[index];
        if (entry.customType !== CONTEXT_CHECKPOINT_TYPE || !entry.data || typeof entry.data !== "object")
            continue;
        const data = entry.data;
        if (data.schemaVersion !== 1 ||
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
            contextPrefixHash(messages, data.coveredMessages) !== data.prefixSha256)
            continue;
        return data;
    }
    return undefined;
}
export function projectContext(context, checkpoint) {
    if (!checkpoint)
        return { ...context, messages: [...context.messages] };
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
//# sourceMappingURL=context-checkpoint.js.map