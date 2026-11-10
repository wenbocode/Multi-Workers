import { getImageDimensions } from "@earendil-works/pi-tui";
export class ContextBudgetError extends Error {
    code;
    details;
    constructor(code, details) {
        super(`${code}: request budget cannot satisfy the configured policy`);
        this.name = "ContextBudgetError";
        this.code = code;
        this.details = details;
    }
}
/** This never mutates model metadata or silently reduces the caller's output budget. */
export function computeContextBudget(model, policy, explicitMaxTokens, fixedTokens = 0) {
    const requestedOutput = explicitMaxTokens ?? model.maxTokens;
    if (![model.contextWindow, policy.maxTokens, requestedOutput].every((value) => Number.isSafeInteger(value) && value > 0) ||
        !Number.isSafeInteger(fixedTokens) ||
        fixedTokens < 0)
        throw new ContextBudgetError("MW_CONTEXT_BUDGET_INVALID", {
            modelWindow: model.contextWindow,
            configuredMaxTokens: policy.maxTokens,
            requestedOutput,
            fixedTokens,
        });
    const effectiveWindow = Math.min(model.contextWindow, policy.maxTokens);
    const outputReserve = Math.max(16384, requestedOutput);
    const safetyMargin = Math.max(4096, Math.ceil(effectiveWindow * 0.02));
    const inputBudget = effectiveWindow - outputReserve - safetyMargin;
    const budget = {
        modelWindow: model.contextWindow,
        configuredMaxTokens: policy.maxTokens,
        effectiveWindow,
        outputReserve,
        safetyMargin,
        inputBudget,
        triggerTokens: Math.floor(inputBudget * policy.compaction.triggerRatio),
        targetTokens: Math.floor(inputBudget * policy.compaction.targetRatio),
    };
    if (inputBudget <= 0 || fixedTokens > inputBudget)
        throw new ContextBudgetError("MW_CONTEXT_BUDGET_IMPOSSIBLE", { ...budget, fixedTokens });
    return budget;
}
export function estimateTextTokens(text) {
    return Math.ceil(Buffer.byteLength(text, "utf8") / 3);
}
/** Model-neutral image estimate: cover both pixel and tile based accounting. */
function estimateImage(image) {
    const dimensions = getImageDimensions(image.data, image.mimeType);
    if (!dimensions || dimensions.widthPx < 1 || dimensions.heightPx < 1)
        return { tokens: 4096, fallback: true };
    const pixels = Math.ceil((dimensions.widthPx * dimensions.heightPx) / 750);
    const tiles = 85 + 170 * Math.ceil(dimensions.widthPx / 512) * Math.ceil(dimensions.heightPx / 512);
    return { tokens: Math.max(pixels, tiles), fallback: false };
}
/** Observable request inputs only; response usage, timestamps and tool details are not model input. */
export function estimateContext(context, options = {}) {
    const calibrationFactor = options.calibrationFactor ?? 1;
    const additionalTokens = options.additionalTokens ?? 0;
    if (!Number.isFinite(calibrationFactor) ||
        calibrationFactor < 1 ||
        !Number.isSafeInteger(additionalTokens) ||
        additionalTokens < 0)
        throw new ContextBudgetError("MW_CONTEXT_ESTIMATE_INVALID", { calibrationFactor, additionalTokens });
    let imageTokens = 0;
    let imageFallbackCount = 0;
    const images = [];
    const messages = context.messages.map((message) => ({
        role: message.role,
        ...(message.role === "toolResult"
            ? {
                toolCallId: message.toolCallId,
                toolName: message.toolName,
                isError: message.isError,
                addedToolNames: message.addedToolNames,
            }
            : {}),
        content: typeof message.content === "string"
            ? message.content
            : message.content.map((block) => {
                if (block.type !== "image")
                    return block;
                images.push(block);
                const estimate = estimateImage(block);
                imageTokens += estimate.tokens;
                if (estimate.fallback)
                    imageFallbackCount++;
                return { type: "image", mimeType: block.mimeType };
            }),
    }));
    let serialized;
    try {
        serialized =
            options.serializedPayload ??
                JSON.stringify({ systemPrompt: context.systemPrompt, tools: context.tools, messages });
    }
    catch {
        throw new ContextBudgetError("MW_CONTEXT_ESTIMATE_INVALID", {});
    }
    // Base64 transport bytes are not text tokens. Keep the complete wrapping around them.
    if (options.serializedPayload !== undefined) {
        for (const image of images) {
            if (image.data)
                serialized = serialized.split(image.data).join("[image]");
        }
    }
    const textBytes = Buffer.byteLength(serialized, "utf8");
    const baseTokens = Math.ceil(textBytes / 3) + imageTokens + 1024 + additionalTokens;
    const estimatedTokens = Math.ceil(baseTokens * calibrationFactor);
    if (!Number.isSafeInteger(baseTokens) || !Number.isSafeInteger(estimatedTokens))
        throw new ContextBudgetError("MW_CONTEXT_ESTIMATE_INVALID", { baseTokens, estimatedTokens });
    return {
        baseTokens,
        estimatedTokens,
        calibrationFactor,
        textBytes,
        imageTokens,
        imageFallbackCount,
        wrapperKey: options.wrapperKey ?? (options.serializedPayload === undefined ? "context-json-v1" : "wire-json-v1"),
    };
}
/** Input calibration is monotone and scoped to the exact provider/model/wrapping tuple. */
export class ContextCalibration {
    factors = new Map();
    getFactor(provider, model, wrapperKey) {
        return this.factors.get(JSON.stringify([provider, model, wrapperKey])) ?? 1;
    }
    observe(provider, model, wrapperKey, baseTokens, usage) {
        const current = this.getFactor(provider, model, wrapperKey);
        if (!Number.isSafeInteger(baseTokens) ||
            baseTokens <= 0 ||
            ![usage.input, usage.output, usage.cacheRead, usage.cacheWrite].every((value) => Number.isSafeInteger(value) && value >= 0))
            return current;
        const inputTokens = usage.input + usage.cacheRead + usage.cacheWrite;
        if (!Number.isSafeInteger(inputTokens) || inputTokens <= 0)
            return current;
        const next = Math.max(current, inputTokens / baseTokens);
        this.factors.set(JSON.stringify([provider, model, wrapperKey]), next);
        return next;
    }
    reset() {
        this.factors.clear();
    }
}
//# sourceMappingURL=context-budget.js.map