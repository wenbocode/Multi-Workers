import { randomUUID } from "node:crypto";
import { isRetryableAssistantError } from "@earendil-works/pi-ai";
import { convertToLlm } from "../../../core/messages.js";
import { buildSessionContext } from "../../../core/session-manager.js";
import { createLocalCodexPayload } from "./codex-local.js";
import { LOCAL_CODEX_PROVIDER } from "./codex-proxy.js";
import { ContextBudgetError, computeContextBudget } from "./context-budget.js";
import { ContextController, contextPolicyFailureMessage, MwContextPolicyError, } from "./context-controller.js";
import { CONTEXT_POLICY_FIELDS, DELEGATED_CONTEXT_FIELDS, resolveContextPolicy, updateContextPolicy, } from "./context-policy.js";
import { NATIVE_SUMMARY_POLICY } from "./native-summary-policy.js";
import { installProviderPolicies } from "./provider-policies.js";
const policyFailures = new WeakMap();
const nativeSummarySignalsByRegistry = new WeakMap();
/** Native core cancellation may never become an assistant message; preserve its signal identity. */
export function consumeNativeContextAbort(registry) {
    const signal = nativeSummarySignalsByRegistry.get(registry);
    nativeSummarySignalsByRegistry.delete(registry);
    return signal?.aborted ?? false;
}
/** Native compaction may flatten provider diagnostics; retain the typed failure for worker settlement. */
export function consumeContextPolicyFailure(registry) {
    const failure = policyFailures.get(registry);
    policyFailures.delete(registry);
    return failure;
}
/** Install on PM and worker sessions, before the first provider request. */
export function registerContextPolicy(pi, options = {}) {
    const location = {
        controlRoot: options.controlRoot ?? process.cwd(),
        homeDir: options.homeDir,
        taskFile: options.taskFile ?? (process.env.PI_WORKER_TASK || undefined),
    };
    const states = new WeakMap();
    const nativeSummarySignals = new WeakSet();
    const automaticNativeSummarySignals = new WeakSet();
    const nativeAttempts = new WeakMap();
    const contextFor = (ctx, pending) => {
        const active = new Set(pi.getActiveTools());
        const messages = convertToLlm(buildSessionContext(ctx.sessionManager.getBranch()).messages);
        return {
            systemPrompt: ctx.getSystemPrompt(),
            messages: pending ? [...messages, pending] : messages,
            tools: pi
                .getAllTools()
                .filter((tool) => active.has(tool.name))
                .map(({ name, description, parameters }) => ({ name, description, parameters })),
        };
    };
    const rememberFailure = (ctx, error) => {
        policyFailures.set(ctx.modelRegistry, error.details);
        pi.appendEntry("mw-context-policy-failure", error.details);
        ctx.ui.setStatus("mw-context", error.message);
    };
    const install = (ctx) => {
        let state = states.get(ctx.modelRegistry);
        if (!state) {
            const controller = new ContextController({
                readPolicy: () => resolveContextPolicy(location),
                estimateOptions: (model, context, requestOptions) => model.provider === LOCAL_CODEX_PROVIDER
                    ? {
                        serializedPayload: JSON.stringify(createLocalCodexPayload(model, context, requestOptions, location.controlRoot)),
                        additionalTokens: 16384,
                        wrapperKey: "codex-local-v1",
                    }
                    : {},
            });
            state = { ctx, controller, pending: false };
            states.set(ctx.modelRegistry, state);
        }
        state.ctx = ctx;
        const binding = state;
        installProviderPolicies(ctx, {
            controller: state.controller,
            nativeSummarySignals,
            automaticNativeSummarySignals,
            policyFailure: (model, error) => {
                if (!(error instanceof MwContextPolicyError))
                    return undefined;
                policyFailures.set(ctx.modelRegistry, error.details);
                return contextPolicyFailureMessage(model, error);
            },
            nativeSummaryComplete: (model, report, signal) => {
                policyFailures.delete(ctx.modelRegistry);
                pi.appendEntry("mw-native-summary-result", {
                    provider: model.provider,
                    model: model.id,
                    ...(signal ? nativeAttempts.get(signal) : {}),
                    ...report,
                });
            },
            nativeSummaryPolicyFailure: (_model, response, report, signal) => {
                if (signal?.aborted)
                    return;
                const details = response.diagnostics?.find((entry) => entry.type === "mw_context_policy")?.details;
                if (!details || typeof details.code !== "string")
                    return;
                policyFailures.set(ctx.modelRegistry, new MwContextPolicyError(details.code, {
                    ...details,
                    summaryAttempts: report.attempts,
                }).details);
            },
            nativeSummaryFailure: (model, response, signal, originalFailure, report) => {
                if (signal?.aborted || (response.stopReason === "stop" && !report?.invalid))
                    return undefined;
                const code = report?.invalid
                    ? "SUMMARY_INVALID"
                    : response.stopReason === "length"
                        ? "SUMMARY_TRUNCATED"
                        : response.stopReason === "aborted"
                            ? "SUMMARY_ABORTED"
                            : "SUMMARY_FAILED";
                const safe = binding.controller.nativeFailure(model, originalFailure ?? response, code);
                const values = [
                    response.usage.input,
                    response.usage.output,
                    response.usage.cacheRead,
                    response.usage.cacheWrite,
                ];
                const known = values.every((value) => Number.isFinite(value) && value >= 0) && values.some((value) => value > 0);
                const failure = new MwContextPolicyError(code, {
                    ...safe.details,
                    ...(signal ? nativeAttempts.get(signal) : {}),
                    ...(report ? { summaryAttempts: report.attempts } : {}),
                    summaryStatus: report?.summaryStatus ?? response.stopReason,
                    nativeSummaryUsage: known
                        ? { input: values[0], output: values[1], cacheRead: values[2], cacheWrite: values[3] }
                        : null,
                });
                policyFailures.set(ctx.modelRegistry, failure.details);
                const message = contextPolicyFailureMessage(model, failure);
                // Native compaction owns its configured retry budget; never expose raw provider text.
                if (isRetryableAssistantError(response)) {
                    message.errorMessage = `Provider returned error: ${message.errorMessage}`;
                    const boundary = message.diagnostics?.find((entry) => entry.type === "provider_retry_boundary");
                    if (boundary)
                        boundary.details = { outerRetryEligible: true };
                }
                return message;
            },
            authChanged: () => new MwContextPolicyError("AUTH_CHANGED", {
                source: "provider authentication changed while preparing request",
            }),
        });
        try {
            const policy = resolveContextPolicy(location);
            ctx.ui.setStatus("mw-context", `Context ${policy.taskType}: ${policy.maxTokens} tokens; native auto ${policy.compaction.enabled ? "on" : "off"}`);
        }
        catch {
            ctx.ui.setStatus("mw-context", "Context policy invalid; requests blocked");
        }
        return binding;
    };
    const plan = async (ctx, pending) => {
        const state = install(ctx);
        if (state.pending || !ctx.model)
            return;
        const model = ctx.model;
        let planned;
        try {
            planned = await state.controller.planNativeCompaction(model, contextFor(ctx, pending));
        }
        catch (error) {
            if (error instanceof MwContextPolicyError)
                policyFailures.set(ctx.modelRegistry, error.details);
            return;
        }
        if (!planned)
            return;
        state.pending = true;
        const selectedPlan = planned;
        ctx.requestCompaction({
            onComplete: async (_result, signal) => {
                try {
                    nativeSummarySignalsByRegistry.set(ctx.modelRegistry, signal);
                    const current = state.ctx;
                    await state.controller.assertNativeProgress(current.model ?? model, contextFor(current, pending), selectedPlan, { signal });
                }
                catch (error) {
                    signal.throwIfAborted();
                    const failure = error instanceof MwContextPolicyError ? error : state.controller.nativeFailure(model, error);
                    rememberFailure(state.ctx, failure);
                    throw failure;
                }
                finally {
                    state.pending = false;
                }
            },
            onError: async (error, signal) => {
                state.pending = false;
                nativeSummarySignalsByRegistry.set(ctx.modelRegistry, signal);
                if (signal.aborted)
                    throw error;
                const details = policyFailures.get(ctx.modelRegistry);
                const failure = details
                    ? new MwContextPolicyError(details.code, details)
                    : state.controller.nativeFailure(model, error);
                rememberFailure(state.ctx, failure);
                throw failure;
            },
        });
    };
    pi.on("session_start", (_event, ctx) => {
        policyFailures.delete(ctx.modelRegistry);
        nativeSummarySignalsByRegistry.delete(ctx.modelRegistry);
        install(ctx).controller.resetCalibration();
    });
    pi.on("before_agent_start", async (event, ctx) => {
        policyFailures.delete(ctx.modelRegistry);
        nativeSummarySignalsByRegistry.delete(ctx.modelRegistry);
        await plan(ctx, {
            role: "user",
            content: event.images?.length ? [{ type: "text", text: event.prompt }, ...event.images] : event.prompt,
            timestamp: Date.now(),
        });
    });
    pi.on("turn_end", async (event, ctx) => {
        if (event.message.role !== "assistant")
            return;
        if (event.message.stopReason === "error" || event.message.stopReason === "aborted")
            return;
        if (event.toolResults.length || ctx.hasPendingMessages())
            await plan(ctx);
    });
    pi.on("context", (_event, ctx) => {
        install(ctx);
    });
    pi.on("model_select", (_event, ctx) => {
        install(ctx);
    });
    pi.on("session_compact", (_event, ctx) => {
        policyFailures.delete(ctx.modelRegistry);
        nativeSummarySignalsByRegistry.delete(ctx.modelRegistry);
        install(ctx).controller.resetCalibration();
    });
    pi.on("session_tree", (_event, ctx) => {
        policyFailures.delete(ctx.modelRegistry);
        nativeSummarySignalsByRegistry.delete(ctx.modelRegistry);
        install(ctx).controller.resetCalibration();
    });
    pi.on("session_before_compact", (event, ctx) => {
        install(ctx);
        // MW owns the automatic threshold; generation and overflow recovery remain native.
        if (event.reason === "threshold")
            return { cancel: true };
        if (event.reason !== "manual") {
            try {
                if (!resolveContextPolicy(location).compaction.enabled)
                    return { cancel: true };
            }
            catch {
                return { cancel: true };
            }
        }
        nativeSummarySignals.add(event.signal);
        if (states.get(ctx.modelRegistry)?.pending)
            automaticNativeSummarySignals.add(event.signal);
        nativeAttempts.set(event.signal, { attemptId: randomUUID(), attemptStartedAt: new Date().toISOString() });
        nativeSummarySignalsByRegistry.set(ctx.modelRegistry, event.signal);
        return undefined;
    });
    pi.on("session_before_tree", (event, ctx) => {
        install(ctx);
        if (event.preparation.userWantsSummary) {
            nativeSummarySignals.add(event.signal);
            nativeSummarySignalsByRegistry.set(ctx.modelRegistry, event.signal);
        }
    });
}
export const CONTEXT_COMMAND_USAGE = "Usage: /mw context show [--type TYPE] [--json] | set <field> <value> --global|--project [--type TYPE] | clear <field|type> --global|--project [--type TYPE]";
/** User-command only: workers may inspect their policy, but cannot change it. */
export async function runContextCommand(pi, ctx, controlRoot, args, options = {}) {
    try {
        const tokens = args.trim().split(/\s+/).filter(Boolean);
        const action = tokens.shift() ?? "show";
        const positional = [];
        let scope;
        let type;
        let json = false;
        for (let index = 0; index < tokens.length; index++) {
            const token = tokens[index];
            if (token === "--global" || token === "--project") {
                if (scope)
                    throw new Error(CONTEXT_COMMAND_USAGE);
                scope = token === "--global" ? "global" : "project";
            }
            else if (token === "--type") {
                const value = tokens[++index];
                if (type || !value || value.startsWith("--"))
                    throw new Error(CONTEXT_COMMAND_USAGE);
                type = value;
            }
            else if (token === "--json") {
                if (json)
                    throw new Error(CONTEXT_COMMAND_USAGE);
                json = true;
            }
            else if (token.startsWith("--"))
                throw new Error(CONTEXT_COMMAND_USAGE);
            else
                positional.push(token);
        }
        const location = {
            controlRoot,
            homeDir: options.homeDir,
            taskType: type,
            taskFile: options.taskFile ?? (process.env.PI_WORKER_TASK || undefined),
        };
        let policy;
        if (action === "show" && positional.length === 0 && !scope)
            policy = resolveContextPolicy(location);
        else if ((action === "set" || action === "clear") && scope && !json) {
            if (location.taskFile)
                throw new Error("Workers may only show context policy; a user in the PM window must change it");
            const [field, raw, extra] = positional;
            if (extra || !field || (action === "set" ? raw === undefined : raw !== undefined))
                throw new Error(CONTEXT_COMMAND_USAGE);
            if (!CONTEXT_POLICY_FIELDS.includes(field) &&
                !(action === "clear" && field === "type" && type))
                throw new Error(CONTEXT_COMMAND_USAGE);
            let value;
            if (action === "set") {
                if (field === "compaction.enabled") {
                    if (raw !== "true" && raw !== "false")
                        throw new Error("compaction.enabled must be true or false");
                    value = raw === "true";
                }
                else {
                    if (!raw || !/^(?:\d+\.?\d*|\.\d+)$/.test(raw))
                        throw new Error("Context numeric values must be positive tokens or ratios");
                    value = Number(raw);
                }
            }
            policy = await updateContextPolicy({
                ...location,
                scope,
                type,
                field: field,
                value,
                operation: action,
            });
        }
        else
            throw new Error(CONTEXT_COMMAND_USAGE);
        let budget = null;
        let budgetError;
        try {
            if (ctx.model)
                budget = computeContextBudget(ctx.model, policy);
        }
        catch (error) {
            if (!(error instanceof ContextBudgetError))
                throw error;
            budgetError = { code: error.code, details: error.details };
        }
        const report = {
            ...policy,
            compaction: { enabled: policy.compaction.enabled, triggerRatio: policy.compaction.triggerRatio },
            generationOwner: "pi-native-compaction",
            summaryGeneration: NATIVE_SUMMARY_POLICY,
            delegatedLegacy: {
                active: false,
                message: "pi owns compaction generation parameters; legacy MW values below are not applied",
                values: Object.fromEntries(DELEGATED_CONTEXT_FIELDS.map((field) => [
                    field,
                    policy.compaction[field.slice("compaction.".length)],
                ])),
            },
            budget,
            budgetError,
            modelWindow: ctx.model?.contextWindow ?? null,
            state: budgetError
                ? "blocked-by-budget"
                : policy.compaction.enabled
                    ? "automatic-compaction-enabled"
                    : "manual-compaction-only",
            limitation: "Client token estimate; local Codex CLI overhead reserved conservatively, CLI output decoding is not hard-capped",
        };
        const text = json
            ? JSON.stringify(report, null, 2)
            : [
                `Context type=${policy.taskType} control=${policy.controlRoot}`,
                `configured=${policy.maxTokens} model=${ctx.model?.contextWindow ?? "unselected"} effective=${budget?.effectiveWindow ?? "unavailable"} inputBudget=${budget?.inputBudget ?? "unavailable"} auto=${policy.compaction.enabled}`,
                ...(budgetError
                    ? [`Budget unavailable: ${budgetError.code} ${JSON.stringify(budgetError.details)}`]
                    : []),
                `Summary thinking=${NATIVE_SUMMARY_POLICY.thinking} minimumOutput=${NATIVE_SUMMARY_POLICY.minimumOutputTokens} maxAttempts=${NATIVE_SUMMARY_POLICY.maxAttempts}; output remains capped by model and current request budget`,
                ...CONTEXT_POLICY_FIELDS.map((field) => {
                    const source = policy.sources[field];
                    const value = field === "maxTokens"
                        ? policy.maxTokens
                        : policy.compaction[field.slice("compaction.".length)];
                    return `${field}=${value}${DELEGATED_CONTEXT_FIELDS.includes(field) ? " [inactive; pi owns generation]" : ""}: ${source.path} (${source.scope}.${source.level}${source.taskType ? `:${source.taskType}` : ""}${source.builtin ? ", initial default" : ""})`;
                }),
                report.limitation,
            ].join("\n");
        ctx.ui.notify(text, "info");
        if (!ctx.hasUI)
            pi.sendMessage({ customType: "mw-context", content: text, display: true });
    }
    catch (error) {
        const text = error instanceof Error ? error.message : String(error);
        ctx.ui.notify(text, "error");
        if (!ctx.hasUI)
            pi.sendMessage({ customType: "mw-context", content: text, display: true });
    }
}
//# sourceMappingURL=context-extension.js.map