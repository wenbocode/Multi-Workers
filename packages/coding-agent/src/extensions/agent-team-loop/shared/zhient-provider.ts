import type { ExtensionAPI, ProviderModelConfig } from "../../../core/extensions/types.ts";

export function registerZhient(pi: Pick<ExtensionAPI, "registerProvider">): void {
	// Base USD per million tokens from the gateway's rate card, before account group multipliers.
	const models: ProviderModelConfig[] = [
		{ id: "gpt-6.1-sol", inputRate: 2, outputRate: 10, cachedRate: 0.1 },
		{ id: "gpt-6-sol", inputRate: 2, outputRate: 10, cachedRate: 0.2 },
		{ id: "gpt-6.1-terra", inputRate: 1, outputRate: 5, cachedRate: 0.05 },
		{ id: "gpt-6-astra", inputRate: 10, outputRate: 50, cachedRate: 1 },
		{ id: "gpt-5.6-sol", inputRate: 4, outputRate: 20, cachedRate: 0.4 },
		{ id: "gpt-5.6-terra", inputRate: 2, outputRate: 12, cachedRate: 0.2 },
		{ id: "codex-auto-review", inputRate: 4, outputRate: 20, cachedRate: 0.4 },
	].map<ProviderModelConfig>(({ id, inputRate, outputRate, cachedRate }) => {
		const responses = id === "gpt-6.1-sol" || id === "gpt-6-sol";
		const reviewAlias = id === "codex-auto-review";
		return {
			id,
			name: id,
			api: responses ? "openai-responses" : "openai-completions",
			input: reviewAlias ? ["text"] : ["text", "image"],
			reasoning: !reviewAlias,
			...(id === "gpt-6.1-sol" && { thinkingLevelMap: { off: null, minimal: null, xhigh: "xhigh", max: "max" } }),
			// Conservative client caps where the gateway publishes no exact limits.
			contextWindow: reviewAlias ? 32_768 : responses ? 1_050_000 : 1_000_000,
			maxTokens: reviewAlias ? 4096 : responses ? 128_000 : 16_384,
			cost: {
				input: inputRate,
				output: outputRate,
				cacheRead: cachedRate,
				cacheWrite: inputRate * 1.25,
				...(id === "gpt-6.1-sol" && {
					tiers: [{ inputTokensAbove: 272_000, input: 4, output: 15, cacheRead: 0.2, cacheWrite: 5 }],
				}),
			},
		};
	});
	pi.registerProvider("zhient", {
		name: "Zhient",
		baseUrl: "https://zhient.com/v1",
		apiKey: "$ZHIENT_API_KEY",
		api: "openai-completions",
		models,
	});
}
