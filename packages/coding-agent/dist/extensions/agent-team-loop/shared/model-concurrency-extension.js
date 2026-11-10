import { createAssistantMessageEventStream, } from "@earendil-works/pi-ai";
import { readConcurrencySnapshot, renderConcurrencyLines } from "./concurrency-view.js";
import { acquireModelSlot, concurrencyDirectory, concurrencyRoute, setConcurrencyLimit } from "./model-concurrency.js";
import { installProviderPolicies } from "./provider-policies.js";
export function limitProviderStream(model, start, signal, directory, onWait, onReady) {
    const output = createAssistantMessageEventStream();
    void (async () => {
        let release;
        try {
            release = await acquireModelSlot(`${model.provider}/${model.id}`, { signal, directory, onWait });
            onReady?.();
            signal?.throwIfAborted();
            const stream = start();
            let terminal;
            for await (const event of stream) {
                // Release before exposing terminal to the next request/tool turn.
                if (event.type === "done" || event.type === "error") {
                    terminal = event.type === "done" ? event.message : event.error;
                    await release?.();
                    release = undefined;
                }
                output.push(event);
            }
            if (!terminal)
                throw new Error("Provider stream ended without a terminal event");
            output.end(terminal);
        }
        catch (error) {
            let failure = error;
            if (release) {
                try {
                    await release();
                }
                catch (cleanupError) {
                    failure = cleanupError;
                }
            }
            const message = {
                role: "assistant",
                content: [],
                api: model.api,
                provider: model.provider,
                model: model.id,
                usage: {
                    input: 0,
                    output: 0,
                    cacheRead: 0,
                    cacheWrite: 0,
                    totalTokens: 0,
                    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
                },
                stopReason: signal?.aborted ? "aborted" : "error",
                errorMessage: failure instanceof Error ? failure.message : String(failure),
                timestamp: Date.now(),
            };
            output.push({ type: "error", reason: signal?.aborted ? "aborted" : "error", error: message });
            output.end(message);
        }
        finally {
            onReady?.();
        }
    })();
    return output;
}
/** Register native wrappers so model refresh continues to delegate through the limiter. */
export function installConcurrencyProviders(ctx) {
    installProviderPolicies(ctx, {
        limit: (model, start, signal, current) => {
            const status = (text) => {
                try {
                    current.ui.setStatus("mw-concurrency", text);
                }
                catch {
                    /* A stale/headless UI cannot affect slot ownership. */
                }
            };
            return limitProviderStream(model, start, signal, concurrencyDirectory(), () => status(`Waiting for LLM slot: ${concurrencyRoute(`${model.provider}/${model.id}`)}`), () => status());
        },
    });
}
export function registerModelConcurrency(pi) {
    pi.on("session_start", (_event, ctx) => installConcurrencyProviders(ctx));
    pi.on("before_agent_start", (_event, ctx) => installConcurrencyProviders(ctx));
    pi.on("context", (_event, ctx) => installConcurrencyProviders(ctx));
    pi.on("model_select", (_event, ctx) => installConcurrencyProviders(ctx));
    pi.on("session_before_compact", (_event, ctx) => installConcurrencyProviders(ctx));
}
export async function runConcurrencyCommand(pi, ctx, args) {
    try {
        const [action = "show", route, count, extra] = args.trim().split(/\s+/).filter(Boolean);
        if (action === "set" && route && count && !extra && /^[1-9]\d*$/.test(count)) {
            await setConcurrencyLimit(route, Number(count));
        }
        else if (action === "clear" && route && !count) {
            await setConcurrencyLimit(route, undefined);
        }
        else if (!(action === "show" && !route)) {
            throw new Error("Usage: /mw concurrency set <provider/model|provider/*> <N> | show | clear <provider/model|provider/*>");
        }
        installConcurrencyProviders(ctx);
        const text = renderConcurrencyLines(readConcurrencySnapshot(), Date.now()).join("\n");
        ctx.ui.notify(text, "info");
        if (!ctx.hasUI)
            pi.sendMessage({ customType: "mw-concurrency", content: text, display: true });
    }
    catch (error) {
        const text = error instanceof Error ? error.message : String(error);
        ctx.ui.notify(text, "error");
        if (!ctx.hasUI)
            pi.sendMessage({ customType: "mw-concurrency", content: text, display: true });
    }
}
//# sourceMappingURL=model-concurrency-extension.js.map