import { InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { expect, it } from "vitest";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { registerZhient } from "../../src/extensions/agent-team-loop/shared/zhient-provider.ts";

it("registers the authenticated Zhient catalog and sends each model to its advertised endpoint", async () => {
	const credentials = new InMemoryCredentialStore();
	await credentials.modify("zhient", async () => ({ type: "api_key", key: "zhient-test" }));
	const runtime = await ModelRuntime.create({ credentials, modelsPath: null });
	const registry = new ModelRegistry(runtime);
	registerZhient({ registerProvider: registry.registerProvider.bind(registry) });
	await runtime.refresh({ allowNetwork: false });
	const paths = new Map([
		["gpt-6.1-sol", "responses"],
		["gpt-6-sol", "responses"],
		["gpt-6.1-terra", "chat/completions"],
		["gpt-6-astra", "chat/completions"],
		["gpt-5.6-sol", "chat/completions"],
		["gpt-5.6-terra", "chat/completions"],
		["codex-auto-review", "chat/completions"],
	]);
	const models = await runtime.getAvailable("zhient");
	expect(models.map((model) => model.id).sort()).toEqual([...paths.keys()].sort());
	for (const model of models) {
		expect(model.input).toEqual(model.id === "codex-auto-review" ? ["text"] : ["text", "image"]);
		let request: Request | undefined;
		const result = await runtime.completeSimple(
			model,
			{
				messages: [{ role: "user", content: "ping", timestamp: 1 }],
			},
			{
				fetch: async (input, init) => {
					request = new Request(input, init);
					return Response.json({ error: { message: "test endpoint" } }, { status: 400 });
				},
				maxRetries: 0,
			},
		);
		expect(result.errorMessage).toContain("test endpoint");
		expect(request?.url).toBe(`https://zhient.com/v1/${paths.get(model.id)}`);
		expect(request?.headers.get("authorization")).toBe("Bearer zhient-test");
		expect(await request?.json()).toMatchObject({ model: model.id, stream: true });
	}
});
