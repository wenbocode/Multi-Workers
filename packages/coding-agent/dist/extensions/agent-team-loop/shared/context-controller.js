import { ContextBudgetError, ContextCalibration, computeContextBudget, estimateContext, } from "./context-budget.js";
import { completeContextGroups, taskAnchorEnd } from "./context-checkpoint.js";
import { ContextPolicyError } from "./context-policy.js";
import { projectSummaryFailure } from "./context-summary-diagnostics.js";
export const CONTEXT_COMPACTION_USAGE_TYPE = "mw-context-compaction-usage";
export class MwContextPolicyError extends Error {
    details;
    constructor(code, details = {}) {
        const reason = details.summaryFailure;
        super(`MW_CONTEXT_POLICY:${code}${reason ? ` (summary=${reason.category}; http=${reason.httpStatus ?? "unknown"})` : ""}`);
        this.name = "MwContextPolicyError";
        this.details = {
            source: null,
            configured: null,
            effective: null,
            estimate: null,
            ...details,
            code,
            noProviderRequest: true,
        };
    }
}
export function isContextPolicyFailure(message) {
    return (message.diagnostics?.some((diagnostic) => diagnostic.type === "mw_context_policy" && diagnostic.details?.noProviderRequest === true) ?? false);
}
export function contextPolicyFailureMessage(model, error) {
    return {
        role: "assistant",
        api: model.api,
        provider: model.provider,
        model: model.id,
        content: [],
        stopReason: "error",
        errorMessage: error.message,
        timestamp: Date.now(),
        usage: {
            input: 0,
            output: 0,
            cacheRead: 0,
            cacheWrite: 0,
            totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
        diagnostics: [
            { type: "mw_context_policy", timestamp: Date.now(), details: error.details },
            { type: "provider_retry_boundary", timestamp: Date.now(), details: { outerRetryEligible: false } },
        ],
    };
}
/** MW owns admission and triggering; pi owns generation, persistence and context rebuilding. */
export class ContextController {
    options;
    calibration = new ContextCalibration();
    constructor(options) {
        this.options = options;
    }
    resetCalibration() {
        this.calibration.reset();
    }
    estimate(model, context, options) {
        try {
            const estimateOptions = this.options.estimateOptions?.(model, context, options) ?? {};
            const base = estimateContext(context, estimateOptions);
            return estimateContext(context, {
                ...estimateOptions,
                calibrationFactor: this.calibration.getFactor(model.provider, model.id, base.wrapperKey),
            });
        }
        catch (error) {
            if (error instanceof MwContextPolicyError)
                throw error;
            if (error instanceof ContextBudgetError)
                throw new MwContextPolicyError(error.code, { ...error.details });
            throw new MwContextPolicyError("PREPARATION_FAILED");
        }
    }
    observeUsage(model, context, options, usage) {
        const estimate = this.estimate(model, context, options);
        this.calibration.observe(model.provider, model.id, estimate.wrapperKey, estimate.baseTokens, usage);
    }
    async settings(model, options) {
        let policy;
        try {
            policy = await this.options.readPolicy();
            return { policy, budget: computeContextBudget(model, policy, options?.maxTokens) };
        }
        catch (error) {
            if (error instanceof MwContextPolicyError)
                throw error;
            throw new MwContextPolicyError("INVALID_POLICY", {
                source: policy?.sources ??
                    (error instanceof ContextPolicyError
                        ? { path: error.path, field: error.field, code: error.code }
                        : null),
                configured: policy?.maxTokens ?? null,
                effective: policy ? Math.min(model.contextWindow, policy.maxTokens) : null,
                ...(error instanceof ContextBudgetError ? error.details : {}),
            });
        }
    }
    failure(code, policy, budget, estimate, extra = {}) {
        return new MwContextPolicyError(code, {
            source: policy.sources,
            configured: budget.configuredMaxTokens,
            effective: budget.effectiveWindow,
            estimate,
            inputBudget: budget.inputBudget,
            triggerTokens: budget.triggerTokens,
            ...extra,
        });
    }
    /** Called only at complete-turn boundaries, before core native compaction is requested. */
    async planNativeCompaction(model, context, options) {
        options?.signal?.throwIfAborted();
        const { policy, budget } = await this.settings(model, options);
        const before = this.estimate(model, context, options).estimatedTokens;
        try {
            completeContextGroups(context.messages);
        }
        catch {
            throw this.failure("INCOMPLETE_TOOL_BATCH", policy, budget, before);
        }
        const fixed = this.estimate(model, { ...context, messages: context.messages.slice(0, taskAnchorEnd(context.messages)) }, options).estimatedTokens;
        if (fixed > budget.inputBudget)
            throw this.failure("FIXED_CONTEXT_BUDGET", policy, budget, fixed);
        if (!policy.compaction.enabled) {
            if (before > budget.inputBudget)
                throw this.failure("AUTOCOMPACTION_DISABLED", policy, budget, before);
            return undefined;
        }
        options?.signal?.throwIfAborted();
        return before >= budget.triggerTokens
            ? { beforeTokens: before, beforeBaseTokens: this.estimate(model, context, options).baseTokens, policy, budget }
            : undefined;
    }
    /** Provider requests never generate or project summaries. They only enforce the actual budget. */
    async prepare(model, context, options, mode = {}) {
        options?.signal?.throwIfAborted();
        const { policy, budget } = await this.settings(model, options);
        const estimate = this.estimate(model, context, options).estimatedTokens;
        if (mode.automaticNativeSummary && !policy.compaction.enabled)
            throw this.failure("AUTOCOMPACTION_DISABLED", policy, budget, estimate);
        if (!mode.nativeSummary) {
            try {
                completeContextGroups(context.messages);
            }
            catch {
                throw this.failure("INCOMPLETE_TOOL_BATCH", policy, budget, estimate);
            }
        }
        if (estimate > budget.inputBudget) {
            throw this.failure(mode.nativeSummary ? "NATIVE_SUMMARY_BUDGET" : mode.budgetOnly ? "CURRENT_POLICY_BUDGET" : "INPUT_BUDGET", policy, budget, estimate);
        }
        options?.signal?.throwIfAborted();
        return context;
    }
    /** Core has already committed and rebuilt native context; reject continuation if it made no progress. */
    async assertNativeProgress(model, context, plan, options) {
        options?.signal?.throwIfAborted();
        const { policy, budget } = await this.settings(model, options);
        const estimate = this.estimate(model, context, options);
        const after = estimate.estimatedTokens;
        if (estimate.baseTokens >= plan.beforeBaseTokens)
            throw this.failure("SUMMARY_NO_PROGRESS", policy, budget, after, { before: plan.beforeTokens });
        if (after > budget.inputBudget)
            throw this.failure("CURRENT_POLICY_BUDGET", policy, budget, after, { before: plan.beforeTokens });
        options?.signal?.throwIfAborted();
    }
    nativeFailure(model, failure, code = "SUMMARY_FAILED") {
        return new MwContextPolicyError(code, {
            provider: model.provider,
            model: model.id,
            summaryFailure: projectSummaryFailure(failure),
        });
    }
}
//# sourceMappingURL=context-controller.js.map