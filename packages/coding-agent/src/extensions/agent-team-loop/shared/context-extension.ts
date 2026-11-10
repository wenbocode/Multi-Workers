import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../../core/extensions/types.ts";
import type { ModelRegistry } from "../../../core/model-registry.ts";
import { createLocalCodexPayload } from "./codex-local.ts";
import { LOCAL_CODEX_PROVIDER } from "./codex-proxy.ts";
import { type ContextBudget, ContextBudgetError, computeContextBudget } from "./context-budget.ts";
import {
	ContextController,
	contextPolicyFailureMessage,
	type MwContextPolicyDetails,
	MwContextPolicyError,
} from "./context-controller.ts";
import {
	CONTEXT_POLICY_FIELDS,
	type ContextPolicyField,
	type ContextPolicyLocation,
	type ResolvedContextPolicy,
	resolveContextPolicy,
	updateContextPolicy,
} from "./context-policy.ts";
import { installProviderPolicies } from "./provider-policies.ts";

export interface ContextExtensionOptions {
	controlRoot?: string;
	homeDir?: string;
	taskFile?: string;
}

const policyFailures = new WeakMap<ModelRegistry, MwContextPolicyDetails>();
const nativeSummarySignalsByRegistry = new WeakMap<ModelRegistry, AbortSignal>();

/** Native core cancellation may never become an assistant message; preserve its signal identity. */
export function consumeNativeContextAbort(registry: ModelRegistry): boolean {
	const signal = nativeSummarySignalsByRegistry.get(registry);
	nativeSummarySignalsByRegistry.delete(registry);
	return signal?.aborted ?? false;
}

/** Native compaction may flatten provider diagnostics; retain the typed failure for worker settlement. */
export function consumeContextPolicyFailure(registry: ModelRegistry): MwContextPolicyDetails | undefined {
	const failure = policyFailures.get(registry);
	policyFailures.delete(registry);
	return failure;
}

/** Install on PM and worker sessions, before the first provider request. */
export function registerContextPolicy(pi: ExtensionAPI, options: ContextExtensionOptions = {}): void {
	const location: ContextPolicyLocation = {
		controlRoot: options.controlRoot ?? process.cwd(),
		homeDir: options.homeDir,
		taskFile: options.taskFile ?? (process.env.PI_WORKER_TASK || undefined),
	};
	const states = new WeakMap<ModelRegistry, { ctx: ExtensionContext; controller: ContextController }>();
	const nativeSummarySignals = new WeakSet<AbortSignal>();
	const install = (ctx: ExtensionContext): ContextController => {
		let state = states.get(ctx.modelRegistry);
		if (!state) {
			const binding = { ctx };
			const controller = new ContextController({
				readPolicy: () => resolveContextPolicy(location),
				getCheckpointEntries: () =>
					binding.ctx.sessionManager.getBranch().filter((entry) => entry.type === "custom"),
				appendEntry: (customType, data) => pi.appendEntry(customType, data),
				taskId: location.taskFile,
				estimateOptions: (model, context, requestOptions) =>
					model.provider === LOCAL_CODEX_PROVIDER
						? {
								serializedPayload: JSON.stringify(
									createLocalCodexPayload(model, context, requestOptions, location.controlRoot),
								),
								additionalTokens: 16384,
								wrapperKey: "codex-local-v1",
							}
						: {},
			});
			state = Object.assign(binding, { controller });
			states.set(ctx.modelRegistry, state);
		}
		state.ctx = ctx;
		installProviderPolicies(ctx, {
			controller: state.controller,
			nativeSummarySignals,
			policyFailure: (model, error) => {
				if (!(error instanceof MwContextPolicyError)) return undefined;
				policyFailures.set(ctx.modelRegistry, error.details);
				return contextPolicyFailureMessage(model, error);
			},
			authChanged: () =>
				new MwContextPolicyError("AUTH_CHANGED", {
					source: "provider authentication changed while preparing request",
				}),
		});
		try {
			const policy = resolveContextPolicy(location);
			ctx.ui.setStatus(
				"mw-context",
				`Context ${policy.taskType}: ${policy.maxTokens} tokens; auto ${policy.compaction.enabled ? "on" : "off"}`,
			);
		} catch {
			ctx.ui.setStatus("mw-context", "Context policy invalid; requests blocked");
		}
		return state.controller;
	};
	pi.on("session_start", (_event, ctx) => {
		policyFailures.delete(ctx.modelRegistry);
		nativeSummarySignalsByRegistry.delete(ctx.modelRegistry);
		install(ctx).resetCalibration();
	});
	pi.on("before_agent_start", (_event, ctx) => {
		policyFailures.delete(ctx.modelRegistry);
		nativeSummarySignalsByRegistry.delete(ctx.modelRegistry);
		install(ctx);
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
		install(ctx).resetCalibration();
	});
	pi.on("session_tree", (_event, ctx) => {
		policyFailures.delete(ctx.modelRegistry);
		nativeSummarySignalsByRegistry.delete(ctx.modelRegistry);
		install(ctx).resetCalibration();
	});
	pi.on("session_before_compact", (event, ctx) => {
		install(ctx);
		if (event.reason === "threshold") return { cancel: true };
		if (event.reason === "overflow") {
			try {
				if (!resolveContextPolicy(location).compaction.enabled) {
					ctx.ui.setStatus(
						"mw-context",
						"Automatic summaries disabled; adjust context policy or compact manually",
					);
					return { cancel: true };
				}
			} catch {
				return { cancel: true };
			}
		}
		nativeSummarySignals.add(event.signal);
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

export const CONTEXT_COMMAND_USAGE =
	"Usage: /mw context show [--type TYPE] [--json] | set <field> <value> --global|--project [--type TYPE] | clear <field|type> --global|--project [--type TYPE]";

/** User-command only: workers may inspect their policy, but cannot change it. */
export async function runContextCommand(
	pi: ExtensionAPI,
	ctx: ExtensionCommandContext,
	controlRoot: string,
	args: string,
	options: Omit<ContextExtensionOptions, "controlRoot"> = {},
): Promise<void> {
	try {
		const tokens = args.trim().split(/\s+/).filter(Boolean);
		const action = tokens.shift() ?? "show";
		const positional: string[] = [];
		let scope: "global" | "project" | undefined;
		let type: string | undefined;
		let json = false;
		for (let index = 0; index < tokens.length; index++) {
			const token = tokens[index];
			if (token === "--global" || token === "--project") {
				if (scope) throw new Error(CONTEXT_COMMAND_USAGE);
				scope = token === "--global" ? "global" : "project";
			} else if (token === "--type") {
				const value = tokens[++index];
				if (type || !value || value.startsWith("--")) throw new Error(CONTEXT_COMMAND_USAGE);
				type = value;
			} else if (token === "--json") {
				if (json) throw new Error(CONTEXT_COMMAND_USAGE);
				json = true;
			} else if (token.startsWith("--")) throw new Error(CONTEXT_COMMAND_USAGE);
			else positional.push(token);
		}
		const location: ContextPolicyLocation = {
			controlRoot,
			homeDir: options.homeDir,
			taskType: type,
			taskFile: options.taskFile ?? (process.env.PI_WORKER_TASK || undefined),
		};
		let policy: ResolvedContextPolicy;
		if (action === "show" && positional.length === 0 && !scope) policy = resolveContextPolicy(location);
		else if ((action === "set" || action === "clear") && scope && !json) {
			if (location.taskFile)
				throw new Error("Workers may only show context policy; a user in the PM window must change it");
			const [field, raw, extra] = positional;
			if (extra || !field || (action === "set" ? raw === undefined : raw !== undefined))
				throw new Error(CONTEXT_COMMAND_USAGE);
			if (
				!(CONTEXT_POLICY_FIELDS as readonly string[]).includes(field) &&
				!(action === "clear" && field === "type" && type)
			)
				throw new Error(CONTEXT_COMMAND_USAGE);
			let value: number | boolean | undefined;
			if (action === "set") {
				if (field === "compaction.enabled") {
					if (raw !== "true" && raw !== "false") throw new Error("compaction.enabled must be true or false");
					value = raw === "true";
				} else {
					if (!raw || !/^(?:\d+\.?\d*|\.\d+)$/.test(raw))
						throw new Error("Context numeric values must be positive tokens or ratios");
					value = Number(raw);
				}
			}
			policy = await updateContextPolicy({
				...location,
				scope,
				type,
				field: field as ContextPolicyField | "type",
				value,
				operation: action,
			});
		} else throw new Error(CONTEXT_COMMAND_USAGE);
		let budget: ContextBudget | null = null;
		let budgetError: { code: string; details: Record<string, number> } | undefined;
		try {
			if (ctx.model) budget = computeContextBudget(ctx.model, policy);
		} catch (error) {
			if (!(error instanceof ContextBudgetError)) throw error;
			budgetError = { code: error.code, details: error.details };
		}
		const report = {
			...policy,
			budget,
			budgetError,
			modelWindow: ctx.model?.contextWindow ?? null,
			state: budgetError
				? "blocked-by-budget"
				: policy.compaction.enabled
					? "automatic-compaction-enabled"
					: "manual-compaction-only",
			limitation:
				"Client token estimate; local Codex CLI overhead reserved conservatively, CLI output decoding is not hard-capped",
		};
		const text = json
			? JSON.stringify(report, null, 2)
			: [
					`Context type=${policy.taskType} control=${policy.controlRoot}`,
					`configured=${policy.maxTokens} model=${ctx.model?.contextWindow ?? "unselected"} effective=${budget?.effectiveWindow ?? "unavailable"} inputBudget=${budget?.inputBudget ?? "unavailable"} auto=${policy.compaction.enabled}`,
					...(budgetError
						? [`Budget unavailable: ${budgetError.code} ${JSON.stringify(budgetError.details)}`]
						: []),
					...CONTEXT_POLICY_FIELDS.map((field) => {
						const source = policy.sources[field];
						const value =
							field === "maxTokens"
								? policy.maxTokens
								: policy.compaction[field.slice("compaction.".length) as keyof typeof policy.compaction];
						return `${field}=${value}: ${source.path} (${source.scope}.${source.level}${source.taskType ? `:${source.taskType}` : ""}${source.builtin ? ", initial default" : ""})`;
					}),
					report.limitation,
				].join("\n");
		ctx.ui.notify(text, "info");
		if (!ctx.hasUI) pi.sendMessage({ customType: "mw-context", content: text, display: true });
	} catch (error) {
		const text = error instanceof Error ? error.message : String(error);
		ctx.ui.notify(text, "error");
		if (!ctx.hasUI) pi.sendMessage({ customType: "mw-context", content: text, display: true });
	}
}
