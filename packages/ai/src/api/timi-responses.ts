import type { AssistantMessageEvent, Model, ProviderStreams, SimpleStreamOptions, StreamOptions } from "../types.ts";
import { appendAssistantMessageDiagnostic } from "../utils/diagnostics.ts";
import { AssistantMessageEventStream } from "../utils/event-stream.ts";
import { PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC } from "../utils/retry.ts";
import { openAIResponsesApi } from "./openai-responses.lazy.ts";

function normalizePayload(value: unknown): void {
	if (Array.isArray(value)) {
		for (const item of value) normalizePayload(item);
		return;
	}
	if (!value || typeof value !== "object") return;
	const obj = value as Record<string, unknown>;

	// Remove store at every depth — Timi rejects payloads that contain it
	if ("store" in obj) delete obj.store;

	if (Array.isArray(obj.tools)) {
		(obj.tools as unknown[]).forEach((tool, index) => {
			if (!tool || typeof tool !== "object") return;
			const t = tool as Record<string, unknown>;
			if (typeof t.description === "string" && t.description.trim() === "") {
				const name = typeof t.name === "string" && t.name.trim() ? t.name.trim() : null;
				t.description = name ? `Tool ${name}` : `Tool ${index}`;
			}
		});
	}

	for (const child of Object.values(obj)) normalizePayload(child);
}

function wrapOptions<T extends StreamOptions>(options: T | undefined): T {
	const originalOnPayload = options?.onPayload;
	const maxRetries = options?.maxRetries ?? 8;

	const timiOnPayload = async (payload: unknown, model: Model<"openai-responses">) => {
		let result = payload;
		if (originalOnPayload) {
			const next = await (originalOnPayload as (p: unknown, m: unknown) => Promise<unknown>)(payload, model);
			if (next !== undefined) result = next;
		}

		const cloned = JSON.parse(JSON.stringify(result)) as Record<string, unknown>;
		normalizePayload(cloned);
		return cloned;
	};

	return {
		...options,
		maxRetries,
		onPayload: timiOnPayload,
	} as T;
}

function wrapStream(innerStream: AssistantMessageEventStream): AssistantMessageEventStream {
	const outer = new AssistantMessageEventStream();
	(async () => {
		let started = false;
		for await (const event of innerStream) {
			if (event.type === "start") {
				started = true;
			} else if (event.type === "error" && !started) {
				const errorMsg = event.error;
				appendAssistantMessageDiagnostic(errorMsg, {
					type: PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC,
					timestamp: Date.now(),
					details: { outerRetryEligible: false },
				});
				outer.push({ type: "error", reason: event.reason, error: errorMsg } satisfies AssistantMessageEvent);
				return;
			}
			outer.push(event);
		}
	})();
	return outer;
}

export function timiResponsesApi(delegate = openAIResponsesApi()): ProviderStreams {
	return {
		stream(model, context, options) {
			return wrapStream(delegate.stream(model, context, wrapOptions(options as StreamOptions)));
		},
		streamSimple(model, context, options) {
			return wrapStream(delegate.streamSimple(model, context, wrapOptions(options as SimpleStreamOptions)));
		},
	};
}
