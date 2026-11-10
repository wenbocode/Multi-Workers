export const NATIVE_SUMMARY_POLICY = {
    minimumOutputTokens: 16384,
    maxAttempts: 2,
    thinking: "off",
    outputGrowth: 2,
};
/** Retry only summary generation, before native core can persist or replace context. */
export async function runNativeSummaryPolicy(model, context, options, produce) {
    const attempts = [];
    const initialMaxTokens = Math.min(model.maxTokens, Math.max(options?.maxTokens ?? 0, NATIVE_SUMMARY_POLICY.minimumOutputTokens));
    let accumulated;
    for (let index = 0; index < NATIVE_SUMMARY_POLICY.maxAttempts; index++) {
        options?.signal?.throwIfAborted();
        const requestOptions = {
            ...options,
            maxTokens: Math.min(model.maxTokens, initialMaxTokens * NATIVE_SUMMARY_POLICY.outputGrowth ** index),
        };
        delete requestOptions.reasoning;
        delete requestOptions.thinkingBudgets;
        // Raw stream callers can carry provider-specific options outside SimpleStreamOptions.
        Reflect.deleteProperty(requestOptions, "reasoningEffort");
        const request = index === 0
            ? context
            : {
                ...context,
                systemPrompt: `${context.systemPrompt ?? ""}\n\nThe previous summary did not finish with usable text. Generate a shorter, complete summary. Preserve the task goal, constraints, completed work, unresolved work, and information needed to continue. Omit exploration details and do not narrate reasoning.`,
            };
        const produced = await produce(request, requestOptions);
        const providerRequestStarted = produced.providerRequestStarted;
        const response = options?.signal?.aborted
            ? { ...produced.response, stopReason: "aborted", errorMessage: "Native summary cancelled" }
            : produced.response;
        const text = response.content
            .filter((block) => block.type === "text")
            .map((block) => block.text)
            .join("");
        const invalid = (response.stopReason === "stop" &&
            (!text.trim() || response.content.some((block) => block.type === "toolCall"))) ||
            response.stopReason === "pending" ||
            response.stopReason === "deferred" ||
            response.stopReason === "toolUse";
        const values = [response.usage.input, response.usage.output, response.usage.cacheRead, response.usage.cacheWrite];
        const known = values.every((value) => Number.isFinite(value) && value >= 0) && values.some((value) => value > 0);
        attempts.push({
            attempt: index + 1,
            maxTokens: requestOptions.maxTokens,
            reasoning: "off",
            status: response.stopReason,
            usage: known ? { input: values[0], output: values[1], cacheRead: values[2], cacheWrite: values[3] } : null,
            reasoningTokens: typeof response.usage.reasoning === "number" &&
                Number.isFinite(response.usage.reasoning) &&
                response.usage.reasoning >= 0
                ? response.usage.reasoning
                : null,
            textChars: text.length,
            invalid,
            providerRequestStarted,
        });
        const previous = accumulated;
        const usage = response.usage;
        accumulated = previous
            ? {
                input: previous.input + usage.input,
                output: previous.output + usage.output,
                cacheRead: previous.cacheRead + usage.cacheRead,
                cacheWrite: previous.cacheWrite + usage.cacheWrite,
                ...(previous.cacheWrite1h !== undefined || usage.cacheWrite1h !== undefined
                    ? { cacheWrite1h: (previous.cacheWrite1h ?? 0) + (usage.cacheWrite1h ?? 0) }
                    : {}),
                ...(previous.reasoning !== undefined || usage.reasoning !== undefined
                    ? { reasoning: (previous.reasoning ?? 0) + (usage.reasoning ?? 0) }
                    : {}),
                totalTokens: previous.totalTokens + usage.totalTokens,
                cost: {
                    input: previous.cost.input + usage.cost.input,
                    output: previous.cost.output + usage.cost.output,
                    cacheRead: previous.cost.cacheRead + usage.cost.cacheRead,
                    cacheWrite: previous.cost.cacheWrite + usage.cost.cacheWrite,
                    total: previous.cost.total + usage.cost.total,
                },
            }
            : usage;
        if (index + 1 < NATIVE_SUMMARY_POLICY.maxAttempts &&
            (response.stopReason === "length" || invalid) &&
            !response.diagnostics?.some((diagnostic) => diagnostic.type === "mw_context_policy"))
            continue;
        return {
            response: {
                ...response,
                usage: accumulated,
                ...(invalid ? { stopReason: "error", errorMessage: "Native summary produced no usable text" } : {}),
            },
            report: { summaryStatus: response.stopReason, invalid, attempts },
        };
    }
    throw new Error("Native summary attempt limit exhausted without a result");
}
//# sourceMappingURL=native-summary-policy.js.map