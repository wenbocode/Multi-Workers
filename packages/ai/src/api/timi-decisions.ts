/**
 * timi-decisions API implementation.
 *
 * The timiai gateway's `POST /v1/decisions` endpoint (see `jev接入.md`) answers a
 * set of structured questions about the `state` supplied with them. It is not a
 * chat endpoint: there is no stream, no box, and no free-form text output — only
 * per-question `noul` / `choice` / `score` answers.
 * pi's stream contract is chat-shaped, so this module defines one explicit
 * input convention instead of inventing a lossy mapping:
 *
 * - The last user message text must be a JSON object carrying `state` and
 *   `questions`, e.g. `{"state": "I was charged twice", "questions": {...}}`.
 *   Anything else (plain prose, non-JSON, a JSON object missing either key)
 *   fails fast with an `error` event before any request is made.
 * - The request is a single `POST <baseUrl>/v1/decisions` with only
 *   `{ model, state, questions }` in the body; no chat fields (messages,
 *   tools, stream, sampling parameters) are forwarded. Authentication is the
 *   platform API key sent verbatim in `Authorization` (no `Bearer` prefix).
 * - The one-shot JSON response's `answers` object becomes the assistant text
 *   as compact JSON, `usage.input_tokens`/`usage.output_tokens` become the
 *   assistant message usage, and the upstream `model` names the assistant
 *   message model.
 *
 * 429/5xx responses are surfaced as errors without client-side retries.
 */

import { calculateCost } from "../models.ts";
import type {
	Api,
	AssistantMessage,
	AssistantMessageEvent,
	Context,
	Model,
	ProviderStreams,
	SimpleStreamOptions,
	StreamOptions,
	Usage,
} from "../types.ts";
import { AssistantMessageEventStream } from "../utils/event-stream.ts";
import { headersToRecord, providerHeadersToRecord } from "../utils/headers.ts";

const EXPECTED_INPUT_MESSAGE = `timi-decisions expects the last user message to be a JSON object {"state": ..., "questions": {...}}`;

const ERROR_BODY_PREVIEW_LIMIT = 200;

interface DecisionsRequest {
	state: unknown;
	questions: unknown;
}

function createEmptyUsage(): Usage {
	return {
		input: 0,
		output: 0,
		cacheRead: 0,
		cacheWrite: 0,
		totalTokens: 0,
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
	};
}

function lastUserText(context: Context): string | undefined {
	for (let index = context.messages.length - 1; index >= 0; index -= 1) {
		const message = context.messages[index];
		if (!message || message.role !== "user") continue;
		return typeof message.content === "string"
			? message.content
			: message.content.map((part) => (part.type === "text" ? part.text : "")).join("");
	}
	return undefined;
}

function parseDecisionsRequest(text: string | undefined): DecisionsRequest | undefined {
	if (text === undefined) return undefined;

	let parsed: unknown;
	try {
		parsed = JSON.parse(text);
	} catch {
		return undefined;
	}
	if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return undefined;

	const record = parsed as Record<string, unknown>;
	if (!("state" in record) || !("questions" in record)) return undefined;

	return { state: record.state, questions: record.questions };
}

function mapUsage(model: Model<Api>, raw: unknown): Usage {
	const record = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
	const input = typeof record.input_tokens === "number" ? record.input_tokens : 0;
	const output = typeof record.output_tokens === "number" ? record.output_tokens : 0;
	const usage: Usage = {
		input,
		output,
		cacheRead: 0,
		cacheWrite: 0,
		totalTokens: input + output,
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
	};
	calculateCost(model, usage);
	return usage;
}

function previewBody(body: string): string {
	return body.length > ERROR_BODY_PREVIEW_LIMIT ? body.slice(0, ERROR_BODY_PREVIEW_LIMIT) : body;
}

function createErrorEvent(model: Model<Api>, errorMessage: string, aborted: boolean): AssistantMessageEvent {
	const message: AssistantMessage = {
		role: "assistant",
		content: [],
		api: model.api,
		provider: model.provider,
		model: model.id,
		usage: createEmptyUsage(),
		stopReason: aborted ? "aborted" : "error",
		errorMessage,
		timestamp: Date.now(),
	};
	return { type: "error", reason: aborted ? "aborted" : "error", error: message };
}

function streamDecisions(model: Model<Api>, context: Context, options?: StreamOptions): AssistantMessageEventStream {
	const eventStream = new AssistantMessageEventStream();

	void (async () => {
		const request = parseDecisionsRequest(lastUserText(context));
		if (!request) {
			eventStream.push(createErrorEvent(model, EXPECTED_INPUT_MESSAGE, false));
			return;
		}

		const apiKey = options?.apiKey;
		if (!apiKey) {
			eventStream.push(createErrorEvent(model, `No API key provided for provider "${model.provider}"`, false));
			return;
		}

		const url = new URL(`${model.baseUrl.replace(/\/+$/u, "")}/v1/decisions`);
		const payload = { model: model.id, state: request.state, questions: request.questions };

		const response = await (options?.fetch ?? globalThis.fetch)(url, {
			method: "POST",
			headers: {
				authorization: apiKey,
				"content-type": "application/json",
				accept: "application/json",
				...providerHeadersToRecord(options?.headers),
			},
			body: JSON.stringify(payload),
			signal: options?.signal,
		});

		await options?.onResponse?.({ status: response.status, headers: headersToRecord(response.headers) }, model);

		const body = await response.text();
		if (!response.ok) {
			eventStream.push(
				createErrorEvent(
					model,
					`timi-decisions request failed: ${response.status} ${response.statusText}: ${previewBody(body)}`,
					options?.signal?.aborted ?? false,
				),
			);
			return;
		}

		let parsed: unknown;
		try {
			parsed = JSON.parse(body);
		} catch {
			eventStream.push(
				createErrorEvent(model, `timi-decisions returned a non-JSON response: ${previewBody(body)}`, false),
			);
			return;
		}

		const record = parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : undefined;
		const answers = record?.answers;
		if (!answers || typeof answers !== "object") {
			eventStream.push(
				createErrorEvent(model, `timi-decisions response has no answers object: ${previewBody(body)}`, false),
			);
			return;
		}

		const answerText = JSON.stringify(answers);
		const message: AssistantMessage = {
			role: "assistant",
			content: [{ type: "text", text: answerText }],
			api: model.api,
			provider: model.provider,
			model: typeof record?.model === "string" && record.model ? record.model : model.id,
			usage: mapUsage(model, record?.usage),
			stopReason: "stop",
			timestamp: Date.now(),
		};

		eventStream.push({
			type: "start",
			partial: { ...message, content: [], stopReason: "pending" },
		});
		eventStream.push({ type: "text_delta", contentIndex: 0, delta: answerText, partial: message });
		eventStream.push({ type: "done", reason: "stop", message });
	})().catch((error: unknown) => {
		eventStream.push(
			createErrorEvent(
				model,
				error instanceof Error ? error.message : String(error),
				options?.signal?.aborted ?? false,
			),
		);
	});

	return eventStream;
}

function streamSimpleDecisions(
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
): AssistantMessageEventStream {
	return streamDecisions(model, context, options);
}

export function timiDecisionsApi(): ProviderStreams {
	return { stream: streamDecisions, streamSimple: streamSimpleDecisions };
}
