import { randomUUID } from "node:crypto";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
export function registerToa(pi) {
    const chat = openAICompletionsApi();
    let question;
    pi.on("message_start", ({ message }, ctx) => {
        if (message.role === "user")
            question = { sessionId: ctx.sessionManager.getSessionId(), id: randomUUID() };
    });
    const shared = {
        reasoning: true,
        // The internal rate card is unavailable to the local cost estimator.
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        compat: {
            supportsDeveloperRole: false,
            supportsStore: false,
            supportsStrictMode: false,
            supportsLongCacheRetention: false,
            maxTokensField: "max_tokens",
        },
    };
    pi.registerProvider("toa", {
        name: "TOA (TokenLink)",
        baseUrl: "https://tokenlink.woa.com/openapi/v1",
        api: "openai-completions",
        apiKey: "$TOA_API_KEY",
        models: [
            {
                ...shared,
                id: "hy4",
                name: "Hy4",
                contextWindow: 1024 * 1024,
                maxTokens: 64 * 1024,
                input: ["text", "image"],
                thinkingLevelMap: { off: "no_think", minimal: null, low: null, medium: null, high: "high" },
            },
            {
                ...shared,
                id: "hy3",
                name: "Hy3",
                contextWindow: 256 * 1024,
                maxTokens: 128 * 1024,
                input: ["text"],
                thinkingLevelMap: { off: "no_think", minimal: null, low: "low", medium: null, high: "high" },
            },
        ],
        streamSimple: (model, context, options) => {
            const sessionId = options?.sessionId;
            const send = options?.fetch ?? globalThis.fetch;
            return chat.streamSimple(model, context, {
                ...options,
                headers: {
                    ...options?.headers,
                    ...(sessionId && { "X-Session-Id": sessionId }),
                    ...(question && sessionId === question.sessionId && { "X-QA-Id": question.id }),
                },
                fetch: (input, init) => {
                    // The transport may retry a single model call. Give every HTTP attempt its own ID.
                    const headers = new Headers(init?.headers);
                    headers.set("X-Model-Request-Id", randomUUID());
                    return send(input, { ...init, headers });
                },
                onPayload: (payload, requestModel) => {
                    if (sessionId && options?.cacheRetention !== "none" && payload && typeof payload === "object") {
                        Object.assign(payload, { prompt_cache_key: sessionId });
                    }
                    return options?.onPayload?.(payload, requestModel);
                },
            });
        },
    });
}
//# sourceMappingURL=toa-provider.js.map