import * as path from "node:path";
import {
	type Api,
	type AssistantMessage,
	type Context,
	createAssistantMessageEventStream,
	type Model,
	type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../../core/extensions/types.ts";
import { readLocalCodexModels } from "./codex-models.ts";
import {
	checkProxy,
	formatProxyStatus,
	LOCAL_CODEX_PROVIDER,
	manageProxy,
	proxyProject,
	proxySnapshot,
	readProxyConfig,
	refreshProxy,
	relayUrl,
	setProxySnapshot,
} from "./codex-proxy.ts";

export const PROXY_HEARTBEAT_TIMEOUT_MS = 10_000;

/** Shared by request serialization and the conservative request-budget estimator. */
export function createLocalCodexPayload(
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
	project?: string,
) {
	return {
		model: model.id,
		context,
		reasoning: options?.reasoning,
		...(project
			? {
					caller: process.env.PI_WORKER_TASK
						? `worker:${path.basename(path.dirname(process.env.PI_WORKER_TASK))}`.slice(0, 100)
						: `pm:${process.pid}`,
				}
			: {}),
	};
}

export function streamLocalCodex(model: Model<Api>, context: Context, options?: SimpleStreamOptions, project?: string) {
	const stream = createAssistantMessageEventStream();
	const output: AssistantMessage = {
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
		stopReason: "pending",
		timestamp: Date.now(),
	};
	void (async () => {
		let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
		const startedAt = Date.now();
		const deadline = startedAt + (options?.timeoutMs ?? 240_000);
		const controller = new AbortController();
		let heartbeatTimer: ReturnType<typeof setTimeout> | undefined;
		const progress = (phase: string): void => {
			if (project)
				setProxySnapshot(project, {
					...proxySnapshot(project),
					status: proxySnapshot(project)?.status ?? "checking",
					request: { startedAt, deadline, heartbeatAt: Date.now(), phase },
				});
		};
		try {
			const url = relayUrl(model.baseUrl);
			const token = options?.env?.MW_CODEX_LOCAL_TOKEN ?? process.env.MW_CODEX_LOCAL_TOKEN;
			if (!token || token.length < 24) throw new Error("MW_CODEX_LOCAL_TOKEN must have at least 24 characters");
			const payload = createLocalCodexPayload(model, context, options, project);
			const replacement = await options?.onPayload?.(payload, model);
			const signal = AbortSignal.any([
				...(options?.signal ? [options.signal] : []),
				AbortSignal.timeout(options?.timeoutMs ?? 240_000),
				controller.signal,
			]);
			progress("preflight");
			const status = await checkProxy({ url, token }, { fetch: options?.fetch, signal });
			if (project) setProxySnapshot(project, { ...status, request: proxySnapshot(project)?.request });
			if (status.status !== "ready") throw new Error(`Local Codex proxy is ${status.status}`);
			const heartbeat = (): void => {
				clearTimeout(heartbeatTimer);
				heartbeatTimer = setTimeout(
					() => controller.abort(new Error("Local Codex proxy heartbeat lost (10s)")),
					PROXY_HEARTBEAT_TIMEOUT_MS,
				);
				progress("waiting for Codex");
			};
			heartbeat();
			const response = await (options?.fetch ?? fetch)(`${url}/complete`, {
				method: "POST",
				headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
				body: JSON.stringify(replacement === undefined ? payload : replacement),
				signal,
				redirect: "error",
			});
			await options?.onResponse?.(
				{ status: response.status, headers: Object.fromEntries(response.headers.entries()) },
				model,
			);
			if (!response.ok) throw new Error(`Local Codex relay HTTP ${response.status}`);
			if (!response.body) throw new Error("Local Codex relay returned no body");
			reader = response.body.getReader();
			stream.push({ type: "start", partial: output });
			const decoder = new TextDecoder();
			let pending = "";
			while (true) {
				const activeReader = reader;
				const chunk = await new Promise<Awaited<ReturnType<typeof activeReader.read>>>((resolve, reject) => {
					const abort = (): void => reject(signal.reason);
					if (signal.aborted) {
						abort();
						return;
					}
					signal.addEventListener("abort", abort, { once: true });
					void activeReader
						.read()
						.then(resolve, reject)
						.finally(() => signal.removeEventListener("abort", abort));
				});
				if (chunk.done) throw new Error("Local Codex relay ended before a result");
				pending += decoder.decode(chunk.value, { stream: true });
				if (pending.length > 8 * 1024 * 1024) throw new Error("Local Codex response is too large");
				let end = pending.indexOf("\n");
				while (end >= 0) {
					const event = JSON.parse(pending.slice(0, end)) as Record<string, unknown>;
					pending = pending.slice(end + 1);
					if (event.type === "heartbeat") heartbeat();
					if (event.type === "error") throw new Error(String(event.error));
					if (event.type === "result") {
						if (typeof event.text !== "string" || !Array.isArray(event.toolCalls)) {
							throw new Error("Invalid local Codex result");
						}
						if (event.text) {
							output.content.push({ type: "text", text: event.text });
							stream.push({ type: "text_start", contentIndex: 0, partial: output });
							stream.push({ type: "text_delta", contentIndex: 0, delta: event.text, partial: output });
							stream.push({ type: "text_end", contentIndex: 0, content: event.text, partial: output });
						}
						for (const value of event.toolCalls) {
							const call = value as Record<string, unknown>;
							if (
								!call ||
								typeof call.id !== "string" ||
								typeof call.name !== "string" ||
								!context.tools?.some((tool) => tool.name === call.name) ||
								!call.arguments ||
								typeof call.arguments !== "object" ||
								Array.isArray(call.arguments)
							) {
								throw new Error("Invalid local Codex tool call");
							}
							const toolCall = {
								type: "toolCall" as const,
								id: call.id,
								name: call.name,
								arguments: call.arguments as Record<string, unknown>,
							};
							const contentIndex = output.content.length;
							output.content.push(toolCall);
							stream.push({ type: "toolcall_start", contentIndex, partial: output });
							stream.push({ type: "toolcall_end", contentIndex, toolCall, partial: output });
						}
						if (!output.content.length) throw new Error("Empty local Codex result");
						const usage = event.usage as Record<string, unknown> | undefined;
						const input = Number(usage?.input_tokens ?? 0);
						const cached = Number(usage?.cached_input_tokens ?? 0);
						const generated = Number(usage?.output_tokens ?? 0);
						if ([input, cached, generated].some((n) => !Number.isFinite(n) || n < 0) || cached > input) {
							throw new Error("Invalid local Codex usage");
						}
						output.usage.input = input - cached;
						output.usage.cacheRead = cached;
						output.usage.output = generated;
						output.usage.totalTokens = input + generated;
						output.stopReason = event.toolCalls.length ? "toolUse" : "stop";
						stream.push({ type: "done", reason: output.stopReason, message: output });
						return;
					}
					end = pending.indexOf("\n");
				}
			}
		} catch (error) {
			output.stopReason = options?.signal?.aborted ? "aborted" : "error";
			output.errorMessage = error instanceof Error ? error.message : String(error);
			stream.push({ type: "error", reason: output.stopReason, error: output });
		} finally {
			clearTimeout(heartbeatTimer);
			if (project) {
				const previous = proxySnapshot(project);
				setProxySnapshot(project, {
					...previous,
					status: previous?.status ?? "unknown",
					request: undefined,
					...(output.stopReason === "error"
						? { last_error: { at: Date.now() / 1000, error: output.errorMessage ?? "Proxy failed" } }
						: {}),
				});
			}
			await reader?.cancel().catch(() => {});
			stream.end();
		}
	})();
	return stream;
}

export function registerLocalCodex(pi: ExtensionAPI): void {
	const project = proxyProject();
	configureLocalCodex(pi, project);
	let timer: ReturnType<typeof setInterval> | undefined;
	let busy = false;
	const update = async (ctx: ExtensionContext): Promise<void> => {
		if (busy) return;
		busy = true;
		try {
			const status = await refreshProxy(project);
			if (status.status !== "not configured") ctx.ui.setStatus("codex-proxy", formatProxyStatus(status)[0]);
		} catch {
			// A replaced UI context must not turn the background poll into an unhandled rejection.
		} finally {
			busy = false;
		}
	};
	const route = async (ctx: ExtensionContext, selected = ctx.model): Promise<void> => {
		if (selected?.provider !== "openai-codex") return;
		if (!configureLocalCodex(pi, project)) return;
		await ctx.modelRegistry.refresh({ allowNetwork: false });
		const model = ctx.modelRegistry.find(LOCAL_CODEX_PROVIDER, selected.id);
		if (!model || !(await pi.setModel(model))) throw new Error(`Could not select local Codex model ${selected.id}`);
	};
	pi.on("session_start", async (_event, ctx) => {
		await route(ctx);
		await update(ctx);
		timer = setInterval(() => {
			void update(ctx);
		}, 4000);
		timer.unref();
	});
	pi.on("model_select", async (event, ctx) => {
		await route(ctx, event.model);
		if (["openai-codex", LOCAL_CODEX_PROVIDER].includes(event.model.provider)) await update(ctx);
	});
	pi.on("before_agent_start", async (_event, ctx) => {
		await route(ctx);
	});
	pi.on("turn_end", async (_event, ctx) => {
		if (ctx.model?.provider === LOCAL_CODEX_PROVIDER) await update(ctx);
	});
	pi.on("session_shutdown", () => {
		clearInterval(timer);
	});
}

export function configureLocalCodex(pi: ExtensionAPI, project: string): boolean {
	const config = readProxyConfig(project);
	if (!config) return false;
	const baseUrl = config.url;
	pi.registerProvider(LOCAL_CODEX_PROVIDER, {
		name: "Codex (local CLI)",
		baseUrl,
		api: "openai-codex-responses",
		apiKey: config.token,
		models: readLocalCodexModels(baseUrl).models,
		refreshModels: async () => readLocalCodexModels(readProxyConfig(project)?.url ?? baseUrl).models,
		streamSimple: (model, context, options) => {
			const current = readProxyConfig(project);
			return streamLocalCodex(
				{ ...model, baseUrl: current?.url ?? baseUrl },
				context,
				{
					...options,
					env: { ...options?.env, MW_CODEX_LOCAL_TOKEN: current?.token ?? config.token },
				},
				project,
			);
		},
	});
	return true;
}

export async function runProxyCommand(
	pi: ExtensionAPI,
	ctx: ExtensionCommandContext,
	project: string,
	args: string,
): Promise<void> {
	const [action = "status", flag, extra] = args.trim().split(/\s+/).filter(Boolean);
	if (
		!["start", "stop", "status", "check", "models"].includes(action) ||
		extra ||
		(flag && !(action === "check" && flag === "--deep"))
	) {
		ctx.ui.notify("Usage: /mw proxy start|stop|status|models|check [--deep]", "warning");
		return;
	}
	try {
		if (action === "models") {
			const config = readProxyConfig(project);
			if (!config) throw new Error("Local Codex proxy is not configured; run /mw proxy start first");
			configureLocalCodex(pi, project);
			await ctx.modelRegistry.refresh({ allowNetwork: false });
			const catalog = readLocalCodexModels(config.url);
			const text = [
				`Local Codex models refreshed (${catalog.models.length}). Source: ${catalog.source}`,
				...catalog.models.map((model) => `${LOCAL_CODEX_PROVIDER}/${model.id}`),
				...(catalog.warning ? [catalog.warning] : []),
				"Catalog only; availability is checked by Codex when making a request.",
			].join("\n");
			ctx.ui.notify(text, catalog.warning ? "warning" : "info");
			if (!ctx.hasUI) pi.sendMessage({ customType: "mw-proxy", content: text, display: true });
			return;
		}
		const isCodex = ctx.model && ["openai-codex", LOCAL_CODEX_PROVIDER].includes(ctx.model.provider);
		const status = await manageProxy(project, action, isCodex ? ctx.model?.id : undefined, flag === "--deep");
		if (action === "start") {
			configureLocalCodex(pi, project);
			await ctx.modelRegistry.refresh({ allowNetwork: false });
			if (isCodex && ctx.model) {
				const local = ctx.modelRegistry.find(LOCAL_CODEX_PROVIDER, ctx.model.id);
				if (!local || !(await pi.setModel(local))) throw new Error("Proxy started but model selection failed");
			}
		}
		const text =
			formatProxyStatus(status).join("\n") +
			(action === "start"
				? "\nLocal routing enabled. Select a Codex model; workers read this project's proxy configuration."
				: "");
		ctx.ui.notify(text, "info");
		if (!ctx.hasUI) pi.sendMessage({ customType: "mw-proxy", content: text, display: true });
	} catch (error) {
		const message = error instanceof Error ? error.message : "Proxy command failed";
		ctx.ui.notify(message, "error");
		if (!ctx.hasUI) pi.sendMessage({ customType: "mw-proxy", content: message, display: true });
	}
}

export default registerLocalCodex;
