import { appendAssistantMessageDiagnostic } from "../utils/diagnostics.js";
import { AssistantMessageEventStream } from "../utils/event-stream.js";
import { PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC } from "../utils/retry.js";
import { openAIResponsesApi } from "./openai-responses.lazy.js";
function normalizePayload(value) {
    if (Array.isArray(value)) {
        for (const item of value)
            normalizePayload(item);
        return;
    }
    if (!value || typeof value !== "object")
        return;
    const obj = value;
    // Remove store at every depth — Timi rejects payloads that contain it
    if ("store" in obj)
        delete obj.store;
    if (Array.isArray(obj.tools)) {
        obj.tools.forEach((tool, index) => {
            if (!tool || typeof tool !== "object")
                return;
            const t = tool;
            if (typeof t.description === "string" && t.description.trim() === "") {
                const name = typeof t.name === "string" && t.name.trim() ? t.name.trim() : null;
                t.description = name ? `Tool ${name}` : `Tool ${index}`;
            }
        });
    }
    for (const child of Object.values(obj))
        normalizePayload(child);
}
function wrapOptions(options) {
    const originalOnPayload = options?.onPayload;
    const maxRetries = options?.maxRetries ?? 8;
    const timiOnPayload = async (payload, model) => {
        let result = payload;
        if (originalOnPayload) {
            const next = await originalOnPayload(payload, model);
            if (next !== undefined)
                result = next;
        }
        const cloned = JSON.parse(JSON.stringify(result));
        normalizePayload(cloned);
        return cloned;
    };
    return {
        ...options,
        maxRetries,
        onPayload: timiOnPayload,
    };
}
function wrapStream(innerStream) {
    const outer = new AssistantMessageEventStream();
    (async () => {
        let started = false;
        for await (const event of innerStream) {
            if (event.type === "start") {
                started = true;
            }
            else if (event.type === "error" && !started) {
                const errorMsg = event.error;
                appendAssistantMessageDiagnostic(errorMsg, {
                    type: PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC,
                    timestamp: Date.now(),
                    details: { outerRetryEligible: false },
                });
                outer.push({ type: "error", reason: event.reason, error: errorMsg });
                return;
            }
            outer.push(event);
        }
    })();
    return outer;
}
export function timiResponsesApi(delegate = openAIResponsesApi()) {
    return {
        stream(model, context, options) {
            return wrapStream(delegate.stream(model, context, wrapOptions(options)));
        },
        streamSimple(model, context, options) {
            return wrapStream(delegate.streamSimple(model, context, wrapOptions(options)));
        },
    };
}
//# sourceMappingURL=timi-responses.js.map