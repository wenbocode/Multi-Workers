import { anthropicMessagesApi } from "../api/anthropic-messages.lazy.js";
import { timiResponsesApi } from "../api/timi-responses.js";
import { envApiKeyAuth } from "../auth/helpers.js";
import { createProvider } from "../models.js";
import { TIMI_MODELS } from "./timi.models.js";
export function timiProvider() {
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
//# sourceMappingURL=timi.js.map