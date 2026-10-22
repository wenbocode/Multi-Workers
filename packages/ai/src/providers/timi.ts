import { anthropicMessagesApi } from "../api/anthropic-messages.lazy.ts";
import { timiDecisionsApi } from "../api/timi-decisions.ts";
import { timiResponsesApi } from "../api/timi-responses.ts";
import { envApiKeyAuth } from "../auth/helpers.ts";
import { createProvider, type Provider } from "../models.ts";
import type { Model } from "../types.ts";
import { TIMI_MODELS } from "./timi.models.ts";

export type TimiApi = "anthropic-messages" | "openai-responses" | "timi-decisions";

export function timiProvider(): Provider<TimiApi> {
	const baseUrl = process.env.TIMI_BASE_URL ?? "http://api.timiai.woa.com/ai_api_manage/llmproxy";
	const models = Object.values(TIMI_MODELS).map(
		(model): Model<TimiApi> => ({
			...model,
			baseUrl,
			// jev-latest is a timi decisions model ({state, questions} -> {answers}) served by
			// POST /v1/decisions, not a chat model, so it must not go through /v1/messages. The
			// generated catalog (scripts/generate-models.ts) still declares api
			// "anthropic-messages" plus chat-only reasoning/context fields; the catalog api will
			// be corrected by a later catalog refresh.
			api: model.id === "jev-latest" ? "timi-decisions" : model.api,
		}),
	);
	return createProvider<TimiApi>({
		id: "timi",
		name: "Timi AI",
		baseUrl,
		auth: { apiKey: envApiKeyAuth("Timi AI API key", ["TIMI_API_KEY"]) },
		models,
		api: {
			"anthropic-messages": anthropicMessagesApi(),
			"openai-responses": timiResponsesApi(),
			"timi-decisions": timiDecisionsApi(),
		},
	});
}
