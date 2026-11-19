import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import {
	applyMainModelConfig,
	modelImageCapability,
	recordWindowModel,
	validateModelValue,
	windowModelPath,
} from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";

let root: string;
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-openai-dispatch-"));
	vi.stubEnv("PI_CODING_AGENT_DIR", path.join(root, "agent"));
	vi.stubGlobal(
		"fetch",
		vi.fn(() => {
			throw new Error("Unexpected network request");
		}),
	);
});
afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	vi.unstubAllGlobals();
	fs.rmSync(root, { recursive: true, force: true });
});

it("accepts OpenAI models from the same registry as /model and still rejects unknown ids", async () => {
	const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
	runtime.registerProvider("openai", {
		baseUrl: "https://configured-gateway.example/v1",
		api: "openai-responses",
		models: [
			{
				id: "gpt-6.1-sol",
				name: "Registered OpenAI model",
				reasoning: true,
				input: ["text", "image"],
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				contextWindow: 100000,
				maxTokens: 10000,
			},
		],
	});
	const registry = new ModelRegistry(runtime);
	await registry.refresh({ allowNetwork: false });
	const model = registry.find("openai", "gpt-6.1-sol");
	if (!model) throw new Error("Registered OpenAI model missing");
	expect(validateModelValue(registry, "pi", "timi", "openai/gpt-6.1-sol")).toEqual({ ok: true, message: "" });
	expect(validateModelValue(registry, "pi", "timi", "openai/not-a-model")).toMatchObject({ ok: false });
	expect(modelImageCapability(registry, "pi", "timi", "openai/gpt-6.1-sol")).toBe("yes");
	fs.mkdirSync(path.join(root, ".agenticdoc"));
	recordWindowModel(root, model);
	expect(fs.readFileSync(windowModelPath(root), "utf8")).toBe("openai/gpt-6.1-sol\n");
	fs.writeFileSync(path.join(root, ".mw/dispatch.yml"), "models:\n  main: openai/gpt-6.1-sol\n");
	const setModel = vi.fn(async () => true);
	const notify = vi.fn();
	await applyMainModelConfig(
		{ setModel } as unknown as ExtensionAPI,
		{
			cwd: root,
			modelRegistry: registry,
			ui: { notify },
		} as unknown as ExtensionContext,
	);
	expect(setModel).toHaveBeenCalledWith(model);
	expect(notify).toHaveBeenCalledWith("model set to openai/gpt-6.1-sol (dispatch.yml main)", "info");
});
