import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ProviderConfig } from "../../src/core/extensions/types.ts";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { configureLocalCodex, runProxyCommand } from "../../src/extensions/agent-team-loop/shared/codex-local.ts";
import { readLocalCodexModels } from "../../src/extensions/agent-team-loop/shared/codex-models.ts";
import { validateModelValue } from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";

let root: string;
const baseUrl = "http://127.0.0.1:7010";
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-codex-catalog-"));
	vi.stubEnv("CODEX_HOME", root);
	vi.stubEnv("MW_CODEX_LOCAL_URL", "");
	vi.stubEnv("MW_CODEX_LOCAL_TOKEN", "");
	vi.stubGlobal(
		"fetch",
		vi.fn(() => {
			throw new Error("Unexpected network request");
		}),
	);
});
afterEach(() => {
	vi.unstubAllEnvs();
	vi.unstubAllGlobals();
	fs.rmSync(root, { recursive: true, force: true });
});

function cache(slug = "gpt-6.1-sol"): void {
	fs.writeFileSync(
		path.join(root, "models_cache.json"),
		JSON.stringify({
			models: [
				{
					slug,
					display_name: "GPT-6.1-Sol",
					visibility: "list",
					context_window: 500000,
					supported_reasoning_levels: [{ effort: "high" }],
					instructions: "must not leak",
				},
				{ slug: "hidden-model", visibility: "hide", display_name: "Hidden", context_window: 10000 },
				{ slug: "gpt-5.6-sol", visibility: "hide" },
				{ slug: "bad model", visibility: "list", display_name: "Bad", context_window: 10000 },
			],
		}),
	);
}

it("reads CODEX_HOME visible metadata, ignores invalid/hidden entries, and diagnoses fallback", () => {
	cache();
	const catalog = readLocalCodexModels(baseUrl);
	expect(catalog.source).toContain(path.join(root, "models_cache.json"));
	expect(catalog.warning).toContain("1 invalid");
	const selected = catalog.models.find((m) => m.id === "gpt-6.1-sol");
	expect(selected).toMatchObject({
		provider: "openai-codex-local",
		contextWindow: 500000,
		input: ["text"],
		reasoning: true,
	});
	expect(JSON.stringify(selected)).not.toContain("must not leak");
	expect(catalog.models.some((m) => ["hidden-model", "gpt-5.6-sol", "bad model"].includes(m.id))).toBe(false);
	fs.writeFileSync(path.join(root, "models_cache.json"), "invalid");
	expect(readLocalCodexModels(baseUrl)).toMatchObject({
		source: "built-in fallback",
		warning: expect.stringContaining("Cannot load"),
	});
	fs.unlinkSync(path.join(root, "models_cache.json"));
	expect(readLocalCodexModels(baseUrl).models.length).toBeGreaterThan(0);
});

it("refresh command registers cache-only models, validates worker dispatch, and sends the raw id locally", async () => {
	cache();
	fs.mkdirSync(path.join(root, ".mw"));
	fs.writeFileSync(
		path.join(root, ".mw/codex-local.json"),
		JSON.stringify({ version: 1, url: baseUrl, token: "fake-token-with-at-least-24-characters" }),
	);
	const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
	const pi = {
		registerProvider: (id: string, config: ProviderConfig) => runtime.registerProvider(id, config),
	} as unknown as ExtensionAPI;
	const notify = vi.fn();
	const ctx = {
		hasUI: true,
		modelRegistry: new ModelRegistry(runtime),
		ui: { notify },
	} as unknown as ExtensionCommandContext;
	expect(configureLocalCodex(pi, root)).toBe(true);
	await runProxyCommand(pi, ctx, root, "models");
	expect(fetch).not.toHaveBeenCalled();
	expect(notify).toHaveBeenCalledWith(expect.stringContaining("gpt-6.1-sol"), "warning");
	expect(validateModelValue(ctx.modelRegistry, "pi", "openai-codex", "codex/gpt-6.1-sol").ok).toBe(true);
	expect(validateModelValue(ctx.modelRegistry, "pi", "openai-codex", "codex/unknown-model").ok).toBe(false);
	const selected = runtime.getModel("openai-codex-local", "gpt-6.1-sol");
	if (!selected) throw new Error("cache model missing");
	const fetcher = vi.fn<typeof fetch>(async (url) =>
		String(url).endsWith("/status")
			? Response.json({ status: "ready", backend: "codex-cli", protocol: 2, active: [] })
			: new Response('{"type":"result","text":"ok","toolCalls":[]}\n'),
	);
	const result = await runtime.completeSimple(selected, { messages: [] }, { fetch: fetcher });
	expect(result.content).toEqual([{ type: "text", text: "ok" }]);
	expect(fetcher).toHaveBeenCalledWith(
		`${baseUrl}/complete`,
		expect.objectContaining({ body: expect.stringContaining('"model":"gpt-6.1-sol"') }),
	);
	cache("gpt-6-astra");
	await runProxyCommand(pi, ctx, root, "models");
	expect(runtime.getModel("openai-codex-local", "gpt-6-astra")).toBeDefined();
	expect(fetch).not.toHaveBeenCalled();
});
