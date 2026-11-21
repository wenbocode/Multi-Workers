import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
	type Api,
	type Context,
	fauxAssistantMessage,
	fauxProvider,
	type Model,
	type Provider,
	type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import { streamSimple as streamFaux } from "@earendil-works/pi-ai/compat";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	consumeContextPolicyFailure,
	registerContextPolicy,
	runContextCommand,
} from "../../src/extensions/agent-team-loop/shared/context-extension.ts";
import { readConcurrencyState } from "../../src/extensions/agent-team-loop/shared/model-concurrency.ts";
import { registerModelConcurrency } from "../../src/extensions/agent-team-loop/shared/model-concurrency-extension.ts";
import { createHarness, type Harness } from "../suite/harness.ts";

let root: string;
const harnesses: Harness[] = [];
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-window-compact-"));
	vi.stubEnv("PI_WORKER_TASK", "");
	vi.stubEnv("MW_CONCURRENCY_DIR", path.join(root, "slots"));
});
afterEach(() => {
	while (harnesses.length) harnesses.pop()?.cleanup();
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	fs.rmSync(root, { recursive: true, force: true });
});

async function fixture(contextWindow = 100000) {
	let api: ExtensionAPI | undefined;
	const h = await createHarness({
		models: [
			{ id: "task-model", contextWindow: 200000, maxTokens: 32768 },
			{ id: "same-provider-summary", contextWindow: 100000, maxTokens: 4096 },
		],
		settings: {
			retry: { enabled: false },
			compaction: { enabled: true, keepRecentTokens: 1, reserveTokens: 16384 },
		},
		extensionFactories: [
			(pi) => {
				api = pi;
				registerModelConcurrency(pi);
				registerContextPolicy(pi, { controlRoot: root, homeDir: path.join(root, "home") });
			},
		],
	});
	harnesses.push(h);
	const target = fauxProvider({
		provider: "compact-fixture",
		api: "compact-fixture-api",
		models: [{ id: "summary/model", contextWindow, maxTokens: 4096 }],
	});
	const calls: Array<{ model: Model<Api>; context: Context; options?: SimpleStreamOptions }> = [];
	const stream: Provider["streamSimple"] = (model, context, options) => {
		calls.push({ model, context, options });
		return target.provider.streamSimple(model, context, options);
	};
	h.session.modelRuntime.registerNativeProvider({
		id: h.getModel().provider,
		name: "Source faux",
		getModels: () => h.models,
		auth: {
			apiKey: {
				name: "Source",
				resolve: async () => ({
					auth: { apiKey: "source-secret", headers: { "x-source-secret": "source-private" } },
				}),
			},
		},
		stream: streamFaux,
		streamSimple: streamFaux,
	});
	h.session.modelRuntime.registerNativeProvider({
		...target.provider,
		auth: {
			apiKey: {
				name: "Target",
				resolve: async () => ({
					auth: {
						apiKey: "target-secret",
						headers: { "x-target": "target-value" },
						baseUrl: "http://target.invalid/v1",
					},
				}),
			},
		},
		stream,
		streamSimple: stream,
	});
	h.session.agent.streamFunction = h.session.modelRuntime.streamSimple.bind(h.session.modelRuntime);
	await h.session.bindExtensions({});
	const command = async (args: string) => {
		if (!api) throw new Error("extension API not installed");
		const ctx = h.session.extensionRunner.createCommandContext();
		const notify = vi.spyOn(ctx.ui, "notify");
		await runContextCommand(api, ctx, root, args, { homeDir: path.join(root, "home") });
		return notify.mock.calls.at(-1)?.[0] ?? "";
	};
	const history = (size = 9000) => {
		h.sessionManager.appendMessage({ role: "user", content: "Task goal and restrictions", timestamp: 1 });
		h.sessionManager.appendMessage(fauxAssistantMessage("x".repeat(size), { timestamp: 2 }));
		h.sessionManager.appendMessage({ role: "user", content: "Continue the remaining task", timestamp: 3 });
		h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
	};
	target.setResponses(
		Array.from({ length: 10 }, () => fauxAssistantMessage("Complete task summary with remaining work.")),
	);
	return { h, target, calls, command, history };
}

describe("window compact model", () => {
	it("keeps the prior selection on auth failure, during a run and in worker mode", async () => {
		const { h, command } = await fixture();
		await command("compact-model compact-fixture/summary/model");
		const registry = h.session.extensionRunner.getModelRegistry();
		vi.spyOn(registry, "getApiKeyAndHeaders").mockResolvedValueOnce({ ok: false, error: "PRIVATE-AUTH-DETAIL" });
		expect(await command("compact-model faux/same-provider-summary")).toBe(
			"Compact model authentication unavailable",
		);
		const idle = vi.spyOn(h.session, "isIdle", "get").mockReturnValue(false);
		expect(await command("compact-model clear")).toContain("Wait for the current operation");
		idle.mockRestore();
		vi.stubEnv("PI_WORKER_TASK", "worker-task");
		expect(await command("compact-model clear")).toBe("Workers may only show the compact model");
		expect(await command("compact-model")).toContain("compact-fixture/summary/model source=window");
	});

	it("fails without committing or falling back when the selected model leaves the catalog", async () => {
		const { h, calls, command, history } = await fixture();
		await command("compact-model compact-fixture/summary/model");
		history();
		vi.spyOn(h.session.extensionRunner.getModelRegistry(), "find").mockReturnValue(undefined);
		await expect(h.session.compact()).rejects.toThrow("SUMMARY_MODEL_UNAVAILABLE");
		expect(calls).toEqual([]);
		expect(h.faux.state.callCount).toBe(0);
		expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toEqual([]);
	});

	it("sets, shows and clears only this window; rejects invalid input without replacing the selection", async () => {
		const first = await fixture();
		expect(await first.command("compact-model compact-fixture/summary/model")).toContain("source=window");
		for (const args of [
			"compact-model unknown/model",
			"compact-model summary/model",
			"compact-model --project",
			"compact-model clear extra",
		])
			expect(await first.command(args)).toMatch(/Unknown compact model|Usage:/);
		expect(await first.command("compact-model")).toContain("compact-fixture/summary/model source=window");
		const report = JSON.parse(await first.command("show --json"));
		expect(report.compactModel).toEqual({ provider: "compact-fixture", id: "summary/model", source: "window" });
		const second = await fixture();
		expect(await second.command("compact-model")).toContain("faux/task-model source=task");
		expect(await first.command("compact-model clear")).toContain("faux/task-model source=task");
		expect(fs.existsSync(path.join(root, ".mw", "context.json"))).toBe(false);
		expect(fs.existsSync(path.join(root, "home"))).toBe(false);
		expect(first.target.state.callCount + second.target.state.callCount).toBe(0);
	});

	it.each(["manual", "automatic", "overflow"] as const)(
		"routes %s compaction to target auth, endpoint and output limit, then resumes the task model",
		async (mode) => {
			const { h, calls, command, history } = await fixture();
			await command("compact-model compact-fixture/summary/model");
			if (mode === "automatic") {
				fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
				fs.writeFileSync(
					path.join(root, ".mw/context.json"),
					JSON.stringify({ version: 1, defaults: { maxTokens: 80000 } }),
				);
			}
			history(mode === "automatic" ? 130000 : 9000);
			h.setResponses([
				...(mode === "overflow"
					? [fauxAssistantMessage("", { stopReason: "error", errorMessage: "maximum context length exceeded" })]
					: []),
				fauxAssistantMessage("Business finished"),
			]);
			if (mode === "manual") await h.session.compact();
			await h.session.prompt("Continue task");
			expect(calls).toHaveLength(1);
			expect(calls[0].model).toMatchObject({
				provider: "compact-fixture",
				id: "summary/model",
				baseUrl: "http://target.invalid/v1",
			});
			expect(calls[0].options).toMatchObject({
				apiKey: "target-secret",
				headers: { "x-target": "target-value" },
				maxTokens: 4096,
				cacheRetention: "none",
			});
			expect(calls[0].options?.sessionId).toBeTruthy();
			expect(JSON.stringify(calls[0].options)).not.toMatch(/source-secret|source-private|x-source-secret/);
			expect(calls[0].options?.reasoning).toBeUndefined();
			expect(h.session.model?.id).toBe("task-model");
			expect(h.faux.state.callCount).toBe(mode === "overflow" ? 2 : 1);
			expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(1);
			expect(readConcurrencyState().requests).toEqual([]);
		},
	);

	it("supports another model on the same provider and clear restores native task-model compaction", async () => {
		const { h, command, history, calls } = await fixture();
		await command("compact-model faux/same-provider-summary");
		history();
		const models: string[] = [];
		h.setResponses(
			Array.from({ length: 4 }, () => (_ctx, _options, _state, model) => {
				models.push(model.id);
				return fauxAssistantMessage("Complete summary");
			}),
		);
		await h.session.compact();
		await command("compact-model clear");
		history();
		await h.session.compact();
		expect(models).toEqual(["same-provider-summary", "task-model"]);
		expect(calls).toEqual([]);
	});

	it.each(["bad-request", "budget", "cancel"] as const)("preserves context after target %s", async (mode) => {
		const { h, target, command, history, calls } = await fixture(mode === "budget" ? 23000 : 100000);
		await command("compact-model compact-fixture/summary/model");
		history(mode === "budget" ? 30000 : 9000);
		const before = h.session.messages;
		if (mode === "bad-request")
			target.setResponses([
				fauxAssistantMessage("", {
					stopReason: "error",
					errorMessage: "HTTP 400 Unsupported parameter: reasoning_effort PRIVATE-SECRET",
				}),
			]);
		else if (mode === "cancel")
			target.setResponses([
				() => {
					h.session.abortCompaction();
					return fauxAssistantMessage("Late summary must not be committed");
				},
			]);
		await expect(h.session.compact()).rejects.toThrow(
			mode === "budget"
				? "NATIVE_SUMMARY_BUDGET"
				: mode === "cancel"
					? /cancel|abort/i
					: "summary=parameter; http=400",
		);
		expect(h.session.messages).toEqual(before);
		expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toEqual([]);
		expect(calls).toHaveLength(mode === "budget" ? 0 : 1);
		if (mode === "bad-request") {
			const details = consumeContextPolicyFailure(h.session.extensionRunner.getModelRegistry());
			expect(details).toMatchObject({
				provider: "compact-fixture",
				model: "summary/model",
				summaryFailure: { category: "parameter", httpStatus: 400 },
			});
			expect(JSON.stringify(details)).not.toContain("PRIVATE-SECRET");
		}
		expect(readConcurrencyState().requests).toEqual([]);
	});
});
