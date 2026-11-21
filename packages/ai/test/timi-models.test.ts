import { describe, expect, it } from "vitest";
import { MODELS } from "../src/models.generated.ts";
import { timiProvider } from "../src/providers/timi.ts";

const ZERO_COST = {
	input: 0,
	output: 0,
	cacheRead: 0,
	cacheWrite: 0,
} as const;

const TIMI_ANTHROPIC_COMPAT = {
	supportsLongCacheRetention: false,
	supportsEagerToolInputStreaming: false,
	supportsCacheControlOnTools: false,
} as const;

const TIMI_RESPONSES_COMPAT = {
	supportsDeveloperRole: true,
	sessionAffinityFormat: "openai-nosession",
	supportsLongCacheRetention: false,
	supportsStrictMode: false,
	supportsOpenAIGrammarTools: false,
	supportsToolSearch: false,
	supportsExplicitPromptCacheMode: false,
} as const;

// Correct protocol routing per E2E evidence:
//   gpt-*      → openai-responses   (GPT-5.6-*, GPT-5.5-*)
//   everything else → anthropic-messages   (claude-*, kimi-*, glm-*, deepseek-*, hy3)
const EXPECTED_MODELS: Record<
	string,
	{
		name: string;
		api: "anthropic-messages" | "openai-responses";
		input: readonly string[];
		contextWindow: number;
		maxTokens: number;
		reasoning: boolean;
	}
> = {
	"claude-haiku-4.5": {
		name: "Claude Haiku 4.5",
		api: "anthropic-messages",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"claude-sonnet-4.6": {
		name: "Claude Sonnet 4.6",
		api: "anthropic-messages",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"claude-sonnet-5": {
		name: "Claude Sonnet 5",
		api: "anthropic-messages",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"claude-opus-4.6": {
		name: "Claude Opus 4.6",
		api: "anthropic-messages",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 32000,
		reasoning: false,
	},
	"claude-opus-4.8": {
		name: "Claude Opus 4.8",
		api: "anthropic-messages",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 32000,
		reasoning: false,
	},
	"gpt-5.6-sol": {
		name: "GPT-5.6 Sol",
		api: "openai-responses",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: true,
	},
	"gpt-5.6-terra": {
		name: "GPT-5.6 Terra",
		api: "openai-responses",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: true,
	},
	"gpt-5.6-luna": {
		name: "GPT-5.6 Luna",
		api: "openai-responses",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: true,
	},
	"kimi-k3": {
		name: "Kimi K3",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"glm-5.2": {
		name: "GLM-5.2",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"glm-5.3": {
		name: "GLM-5.3",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	hy3: {
		name: "Hunyuan 3",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"deepseek-v4-pro-r1": {
		name: "DeepSeek V4 Pro R1",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 32000,
		reasoning: true,
	},
	"gpt-5.5-r3": {
		name: "GPT-5.5 R3",
		api: "openai-responses",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 32000,
		reasoning: true,
	},
	"deepseek-v4-pro": {
		name: "DeepSeek V4 Pro",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"deepseek-v4-flash": {
		name: "DeepSeek V4 Flash",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"hy4-preview": {
		name: "Hunyuan 4 Preview",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"deepseek-v4-pro-0813": {
		name: "DeepSeek V4 Pro 0813",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"deepseek-v4-flash-0731": {
		name: "DeepSeek V4 Flash 0731",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"deepseek-v4.1-flash": {
		name: "DeepSeek V4.1 Flash",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"gpt-6-astra": {
		name: "GPT-6 Astra",
		api: "openai-responses",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: true,
	},
	"deepseek-v4-flash-vision-exp": {
		name: "DeepSeek V4 Flash Vision Exp",
		api: "anthropic-messages",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"glm-5.3-flash": {
		name: "GLM-5.3 Flash",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
	"jev-latest": {
		name: "JEV Latest",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: true,
	},
	"gpt-6.1-sol": {
		name: "GPT-6.1 Sol",
		api: "openai-responses",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: true,
	},
	"glm-5.3-flashx": {
		name: "GLM-5.3 FlashX",
		api: "anthropic-messages",
		input: ["text"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: true,
	},
	"claude-opus-5.5": {
		name: "Claude Opus 5.5",
		api: "anthropic-messages",
		input: ["text", "image"],
		contextWindow: 512000,
		maxTokens: 64000,
		reasoning: false,
	},
};

describe("Timi models", () => {
	it("uses the temporary 512k context default for every runtime model", () => {
		const models = timiProvider().getModels();
		expect(models.map((model) => model.id).sort()).toEqual(Object.keys(EXPECTED_MODELS).sort());
		for (const model of models) {
			expect(model.contextWindow, model.id).toBe(512000);
		}
	});

	it("classifies Timi model protocols and preserves the complete catalog metadata", () => {
		expect(Object.keys(MODELS.timi).sort()).toEqual(Object.keys(EXPECTED_MODELS).sort());

		for (const [id, expected] of Object.entries(EXPECTED_MODELS)) {
			const model = MODELS.timi[id as keyof typeof MODELS.timi];
			const isAnthropicMessages = expected.api === "anthropic-messages";

			expect(model).toMatchObject({
				id,
				provider: "timi",
				api: expected.api,
				name: expected.name,
				input: expected.input,
				contextWindow: expected.contextWindow,
				maxTokens: expected.maxTokens,
				reasoning: expected.reasoning,
				cost: ZERO_COST,
			});
			expect(model.compat).toEqual(isAnthropicMessages ? TIMI_ANTHROPIC_COMPAT : TIMI_RESPONSES_COMPAT);
		}
	});
});
