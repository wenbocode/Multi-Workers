import { anthropicMessagesApi } from "../api/anthropic-messages.lazy.ts";
import { timiResponsesApi } from "../api/timi-responses.ts";
import { envApiKeyAuth } from "../auth/helpers.ts";
import { createProvider, type Provider } from "../models.ts";
import { TIMI_MODELS } from "./timi.models.ts";

export function timiProvider(): Provider<"anthropic-messages" | "openai-responses"> {
	const baseUrl = process.env.TIMI_BASE_URL ?? "http://api.timiai.woa.com/ai_api_manage/llmproxy";
	const models = Object.values(TIMI_MODELS).map((m) => ({ ...m, baseUrl }));
	return createProvider({
		id: "timi",
		name: "Timi AI",
		baseUrl,
		auth: { apiKey: envApiKeyAuth("Timi AI API key", ["TIMI_API_KEY"]) },
		models,
		api: {
			"anthropic-messages": anthropicMessagesApi(),
			"openai-responses": timiResponsesApi(),
		},
	});
}
