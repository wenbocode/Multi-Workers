import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { type Context, InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ExtensionAPI, ProviderConfig } from "../../src/core/extensions/types.ts";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { configureDeepSeek } from "../../src/extensions/agent-team-loop/shared/deepseek-provider.ts";
import { validateModelValue } from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";

let root: string;
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-deepseek-"));
	vi.stubEnv("HOME", path.join(root, "home"));
	vi.stubEnv("USERPROFILE", path.join(root, "home"));
	vi.stubEnv("PI_WORKER_TASK", "");
	vi.stubEnv("DEEPSEEK_API_KEY", "fake-deepseek-key");
});
afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	fs.rmSync(root, { recursive: true, force: true });
});

function writeConfig(
	value: unknown = { version: 1, baseUrl: "https://api.deepseek.com", models: ["deepseek-flash", "deepseek-v4-pro"] },
): void {
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw/deepseek.json"), JSON.stringify(value));
}

it("does not register without config and refuses corrupt, unknown, duplicate or credential-bearing config", () => {
	const registerProvider = vi.fn();
	const pi = { registerProvider } as unknown as ExtensionAPI;
	expect(configureDeepSeek(pi, root)).toBe(false);
	for (const value of [
		null,
		{},
		{ version: 1, baseUrl: "https://api.deepseek.com", models: ["unknown"] },
		{ version: 1, baseUrl: "https://api.deepseek.com", models: ["deepseek-flash", "deepseek-flash"] },
		{ version: 1, baseUrl: "https://user:secret@api.deepseek.com", models: ["deepseek-flash"] },
		{ version: 1, baseUrl: "https://api.deepseek.com", models: ["deepseek-flash"], apiKey: "secret" },
	]) {
		writeConfig(value);
		expect(() => configureDeepSeek(pi, root)).toThrow();
	}
	fs.writeFileSync(path.join(root, ".mw/deepseek.json"), "broken");
	expect(() => configureDeepSeek(pi, root)).toThrow("Invalid JSON");
	expect(registerProvider).not.toHaveBeenCalled();
});

it.each([false, true])(
	"registers native PM/dual-worker models, preserves auth and reasoning on tool followup (worker=%s)",
	async (worker) => {
		writeConfig();
		vi.spyOn(process, "cwd").mockReturnValue(worker ? path.join(root, "game") : root);
		vi.stubEnv("PI_WORKER_TASK", worker ? path.join(root, ".agenticdoc/key/workers/task/task.md") : "");
		const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
		const pi = {
			registerProvider: (id: string, config: ProviderConfig) => runtime.registerProvider(id, config),
		} as unknown as ExtensionAPI;
		expect(configureDeepSeek(pi)).toBe(true);
		const registry = new ModelRegistry(runtime);
		await registry.refresh({ allowNetwork: false });
		expect(validateModelValue(registry, "pi", "deepseek", "deepseek/deepseek-flash").ok).toBe(true);
		const selected = runtime.getModel("deepseek", "deepseek-flash");
		if (!selected) throw new Error("DeepSeek Flash missing");
		expect(selected.input).toContain("image");
		expect(runtime.getModel("deepseek", "deepseek-v4-pro")?.input).toEqual(["text"]);
		const bodies: Record<string, unknown>[] = [];
		const fetcher = vi.fn<typeof fetch>(async (_url, init) => {
			expect(new Headers(init?.headers).get("authorization")).toBe("Bearer fake-deepseek-key");
			bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
			const first = bodies.length === 1;
			const chunks = [
				{
					choices: [
						{ index: 0, delta: { role: "assistant", reasoning_content: "reasoning" }, finish_reason: null },
					],
				},
				{
					choices: [
						{
							index: 0,
							delta: first
								? {
										tool_calls: [
											{
												index: 0,
												id: "call-1",
												type: "function",
												function: { name: "lookup", arguments: "{}" },
											},
										],
									}
								: { content: "ok" },
							finish_reason: first ? "tool_calls" : "stop",
						},
					],
				},
				{
					choices: [],
					usage: {
						prompt_tokens: 100,
						completion_tokens: 10,
						total_tokens: 110,
						prompt_cache_hit_tokens: 60,
						prompt_cache_miss_tokens: 40,
						prompt_tokens_details: { cached_tokens: 60 },
					},
				},
			];
			return new Response(
				`${chunks.map((chunk) => `data: ${JSON.stringify(chunk)}\n\n`).join("")}data: [DONE]\n\n`,
				{ headers: { "Content-Type": "text/event-stream" } },
			);
		});
		const context: Context = {
			messages: [{ role: "user", content: "lookup", timestamp: 1 }],
			tools: [{ name: "lookup", description: "lookup", parameters: { type: "object", properties: {} } }],
		};
		const first = await runtime.completeSimple(selected, context, { reasoning: "low", fetch: fetcher });
		expect(first.stopReason).toBe("toolUse");
		expect(first.usage.cacheRead).toBe(60);
		context.messages.push(first, {
			role: "toolResult",
			toolCallId: "call-1",
			toolName: "lookup",
			content: [{ type: "text", text: "result" }],
			isError: false,
			timestamp: 2,
		});
		const second = await runtime.completeSimple(selected, context, { reasoning: "low", fetch: fetcher });
		expect(second.stopReason).toBe("stop");
		expect(bodies[0]).toMatchObject({
			model: "deepseek-flash",
			thinking: { type: "enabled" },
			reasoning_effort: "low",
		});
		expect(bodies[1].messages).toEqual(
			expect.arrayContaining([expect.objectContaining({ role: "assistant", reasoning_content: "reasoning" })]),
		);
	},
);

it("uses the same global defaults in unrelated projects and a dual-root worker", () => {
	const globalDir = path.join(root, "home", ".mw");
	fs.mkdirSync(globalDir, { recursive: true });
	const globalFile = path.join(globalDir, "deepseek.json");
	fs.writeFileSync(
		globalFile,
		JSON.stringify({
			version: 1,
			baseUrl: "https://api.deepseek.com",
			models: ["deepseek-flash", "deepseek-v4-pro"],
		}),
	);
	const before = fs.readFileSync(globalFile, "utf8");
	const registerProvider = vi.fn();
	const pi = { registerProvider } as unknown as ExtensionAPI;
	for (const project of [path.join(root, "project-a"), path.join(root, "project-b")]) {
		expect(configureDeepSeek(pi, project)).toBe(true);
	}
	vi.spyOn(process, "cwd").mockReturnValue(path.join(root, "game"));
	vi.stubEnv("PI_WORKER_TASK", path.join(root, "project-c/.agenticdoc/key/workers/t/task.md"));
	expect(configureDeepSeek(pi)).toBe(true);
	expect(registerProvider).toHaveBeenCalledTimes(3);
	for (const [, config] of registerProvider.mock.calls) {
		expect(config.baseUrl).toBe("https://api.deepseek.com");
		expect(config.models).toEqual(expect.arrayContaining([expect.objectContaining({ id: "deepseek-flash" })]));
	}
	expect(fs.readFileSync(globalFile, "utf8")).toBe(before);
});

it("uses the complete project config over global defaults and refuses project errors without fallback", () => {
	const globalDir = path.join(root, "home", ".mw");
	fs.mkdirSync(globalDir, { recursive: true });
	const globalFile = path.join(globalDir, "deepseek.json");
	fs.writeFileSync(
		globalFile,
		JSON.stringify({ version: 1, baseUrl: "https://api.deepseek.com", models: ["deepseek-flash"] }),
	);
	writeConfig({ version: 1, baseUrl: "https://project-gateway.example/v1", models: ["deepseek-v4-pro"] });
	const registerProvider = vi.fn();
	const pi = { registerProvider } as unknown as ExtensionAPI;
	vi.spyOn(process, "cwd").mockReturnValue(path.join(root, "game"));
	vi.stubEnv("PI_WORKER_TASK", path.join(root, ".agenticdoc/key/workers/t/task.md"));
	expect(configureDeepSeek(pi)).toBe(true);
	expect(registerProvider.mock.calls[0][1].baseUrl).toBe("https://project-gateway.example/v1");
	expect(registerProvider.mock.calls[0][1].models.some((model: { id: string }) => model.id === "deepseek-flash")).toBe(
		false,
	);
	const projectFile = path.join(root, ".mw/deepseek.json");
	fs.writeFileSync(projectFile, "broken");
	expect(() => configureDeepSeek(pi)).toThrow(projectFile);
	expect(registerProvider).toHaveBeenCalledTimes(1);
	fs.unlinkSync(projectFile);
	fs.writeFileSync(globalFile, "broken");
	expect(() => configureDeepSeek(pi)).toThrow(globalFile);
	expect(registerProvider).toHaveBeenCalledTimes(1);
});
