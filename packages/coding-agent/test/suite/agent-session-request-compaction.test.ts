import { setTimeout as delay } from "node:timers/promises";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import {
	type AssistantMessage,
	createAssistantMessageEventStream,
	fauxAssistantMessage,
	fauxToolCall,
	type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import { registerFauxProvider } from "@earendil-works/pi-ai/compat";
import { Type } from "typebox";
import { afterEach, describe, expect, it } from "vitest";
import { findCutPoint, prepareCompaction } from "../../src/core/compaction/index.ts";
import { SessionManager } from "../../src/core/session-manager.ts";
import { createHarness, type Harness, type HarnessOptions } from "./harness.ts";

const harnesses: Harness[] = [];
afterEach(() => {
	while (harnesses.length) harnesses.pop()?.cleanup();
});

async function nativeHarness(
	options: HarnessOptions,
	reply: (options?: SimpleStreamOptions) => AssistantMessage | Promise<AssistantMessage> = () =>
		fauxAssistantMessage("Native summary preserves the task and prior completed work."),
) {
	const signals = new WeakSet<AbortSignal>();
	const nativeOptions: Array<SimpleStreamOptions | undefined> = [];
	const h = await createHarness({
		...options,
		settings: {
			retry: { enabled: false },
			compaction: { enabled: false, keepRecentTokens: 1, reserveTokens: 5000 },
			...options.settings,
		},
		extensionFactories: [
			(pi) => {
				pi.on("session_before_compact", (event) => {
					signals.add(event.signal);
				});
			},
			...(options.extensionFactories ?? []),
		],
	});
	harnesses.push(h);
	const businessStream = h.session.agent.streamFunction;
	h.session.agent.streamFunction = (model, context, requestOptions) => {
		if (!requestOptions?.signal || !signals.has(requestOptions.signal))
			return businessStream(model, context, requestOptions);
		nativeOptions.push(requestOptions);
		const stream = createAssistantMessageEventStream();
		void Promise.resolve(reply(requestOptions)).then((response) => {
			const message = { ...response, api: model.api, provider: model.provider, model: model.id };
			if (message.stopReason === "pending") throw new Error("Native fixture must be terminal");
			if (message.stopReason === "error" || message.stopReason === "aborted") {
				stream.push({ type: "error", reason: message.stopReason, error: message });
			} else {
				stream.push({ type: "done", reason: message.stopReason, message });
			}
			stream.end(message);
		});
		return stream;
	};
	h.sessionManager.appendMessage({ role: "user", content: "Original task", timestamp: 1 });
	h.sessionManager.appendMessage(fauxAssistantMessage("completed history ".repeat(2000)));
	h.sessionManager.appendMessage({ role: "user", content: "Follow-up history", timestamp: 2 });
	h.sessionManager.appendMessage(fauxAssistantMessage("more completed history ".repeat(1000)));
	h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
	return { h, nativeOptions };
}

describe("deferred explicit native compaction", () => {
	it.each(["second", "unknown"])(
		"retains a complete oversized trailing batch for %s tool result ownership",
		(lastId) => {
			const session = SessionManager.inMemory();
			session.appendMessage({ role: "user", content: "Prior goal", timestamp: 1 });
			session.appendMessage(fauxAssistantMessage("Prior completed history"));
			session.appendMessage({ role: "user", content: "Current task", timestamp: 2 });
			const batchId = session.appendMessage(
				fauxAssistantMessage([
					fauxToolCall("read", { path: "first" }, { id: "first" }),
					fauxToolCall("read", { path: "second" }, { id: "second" }),
				]),
			);
			for (const id of ["first", lastId])
				session.appendMessage({
					role: "toolResult",
					toolCallId: id,
					toolName: "read",
					content: [{ type: "text", text: "x".repeat(30000) }],
					isError: false,
					timestamp: 3,
				});
			const entries = session.getBranch();
			const cut = findCutPoint(entries, 0, entries.length, 1);
			if (lastId === "unknown") {
				// Unknown ownership retains all history; never isolate an unmatched result.
				expect(cut.firstKeptEntryIndex).toBe(0);
				return;
			}
			expect(entries[cut.firstKeptEntryIndex].id).toBe(batchId);
			const preparation = prepareCompaction(entries, { enabled: false, reserveTokens: 16384, keepRecentTokens: 1 });
			expect(preparation?.firstKeptEntryId).toBe(batchId);
			expect(preparation?.messagesToSummarize.length).toBeGreaterThan(0);
			session.appendCompaction("Historical summary", batchId, 20000);
			const kept = session.buildSessionContext().messages;
			expect(kept.filter((message) => message.role === "toolResult").map((message) => message.toolCallId)).toEqual([
				"first",
				"second",
			]);
			expect(
				kept
					.filter((message) => message.role === "assistant")
					.flatMap((message) => message.content.filter((part) => part.type === "toolCall").map((part) => part.id)),
			).toEqual(["first", "second"]);
		},
	);
	it("coalesces initial requests and awaits callbacks using pi parameters even when native auto is disabled", async () => {
		const completed: number[] = [];
		const { h, nativeOptions } = await nativeHarness({
			models: [{ id: "native-options", contextWindow: 200000, maxTokens: 20000 }],
			extensionFactories: [
				(pi) => {
					pi.on("before_agent_start", (_event, ctx) => {
						ctx.requestCompaction({
							onComplete: async () => {
								await delay(5);
								completed.push(1);
							},
						});
						ctx.requestCompaction({
							onComplete: () => {
								completed.push(2);
							},
						});
					});
				},
			],
		});
		h.setResponses([
			(context) => {
				expect(completed).toEqual([1, 2]);
				expect(
					context.messages.filter(
						(message) => message.role === "user" && JSON.stringify(message.content).includes("continue"),
					),
				).toHaveLength(1);
				return fauxAssistantMessage("complete");
			},
		]);
		await h.session.prompt("continue");
		expect(h.settingsManager.getCompactionSettings().enabled).toBe(false);
		expect(h.eventsOfType("compaction_start")).toEqual([{ type: "compaction_start", reason: "manual" }]);
		expect(nativeOptions.length).toBeGreaterThan(0);
		expect(nativeOptions.some((options) => options?.maxTokens === 4000)).toBe(true);
		expect(nativeOptions.every((options) => options?.maxTokens === 4000 || options?.maxTokens === 2500)).toBe(true);
		expect(h.faux.state.callCount).toBe(1);
		expect(h.eventsOfType("agent_start")).toHaveLength(1);
		expect(h.eventsOfType("agent_settled")).toHaveLength(1);
		expect(
			h.session.messages.filter(
				(message) => message.role === "user" && JSON.stringify(message.content).includes("continue"),
			),
		).toHaveLength(1);
	});

	it("uses rebuilt context through two tool batches in one run without replaying effects", async () => {
		const effects: number[] = [];
		const parameters = Type.Object({ sequence: Type.Number() });
		const tool: AgentTool<typeof parameters> = {
			name: "effect",
			label: "Effect",
			description: "Record one effect",
			parameters,
			execute: async (_id, args) => {
				effects.push(args.sequence);
				return { content: [{ type: "text", text: `effect=${args.sequence}` }], details: {} };
			},
		};
		let completeCount = 0;
		let downstreamSettled = false;
		const { h } = await nativeHarness({
			tools: [tool],
			initialActiveToolNames: ["effect"],
			extensionFactories: [
				(pi) => {
					pi.on("turn_end", (event, ctx) => {
						if (event.toolResults.length)
							ctx.requestCompaction({
								onComplete: () => {
									completeCount++;
								},
							});
					});
					pi.on("agent_settled", async () => {
						await delay(15);
						downstreamSettled = true;
					});
				},
			],
		});
		h.setResponses([
			fauxAssistantMessage(
				[{ type: "text", text: "first batch plan ".repeat(100) }, fauxToolCall("effect", { sequence: 1 })],
				{ stopReason: "toolUse" },
			),
			(context) => {
				expect(completeCount).toBe(1);
				expect(context.messages.some((message) => JSON.stringify(message.content).includes("Native summary"))).toBe(
					true,
				);
				return fauxAssistantMessage(
					[{ type: "text", text: "second batch plan ".repeat(100) }, fauxToolCall("effect", { sequence: 2 })],
					{ stopReason: "toolUse" },
				);
			},
			() => {
				expect(completeCount).toBe(2);
				return fauxAssistantMessage("all effects complete");
			},
		]);
		await h.session.prompt("perform two effects");
		expect(h.session.state.errorMessage).toBeUndefined();
		expect(downstreamSettled).toBe(true);
		expect(effects).toEqual([1, 2]);
		expect(h.eventsOfType("compaction_start")).toHaveLength(2);
		expect(h.eventsOfType("agent_start")).toHaveLength(1);
		expect(h.eventsOfType("agent_end")).toHaveLength(1);
		expect(h.eventsOfType("agent_settled")).toHaveLength(1);
		expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(2);
	});

	it("does not suppress a native failure when onError returns and never calls business", async () => {
		let failures = 0;
		const { h } = await nativeHarness(
			{
				extensionFactories: [
					(pi) => {
						pi.on("before_agent_start", (_event, ctx) =>
							ctx.requestCompaction({
								onError: async () => {
									failures++;
								},
							}),
						);
					},
				],
			},
			() => fauxAssistantMessage("", { stopReason: "error", errorMessage: "fixture native failure" }),
		);
		await expect(h.session.prompt("continue")).rejects.toThrow("fixture native failure");
		expect(failures).toBe(1);
		expect(h.faux.state.callCount).toBe(0);
		expect(h.eventsOfType("agent_settled")).toHaveLength(1);
	});

	it("awaits a post-compaction validation rejection and permits safe error mapping", async () => {
		const mapped = new Error("safe mapped refusal");
		let observed: Error | undefined;
		const { h } = await nativeHarness({
			extensionFactories: [
				(pi) => {
					pi.on("before_agent_start", (_event, ctx) =>
						ctx.requestCompaction({
							onComplete: async () => {
								await delay(5);
								throw new Error("post-check failed");
							},
							onError: (error) => {
								observed = error;
								throw mapped;
							},
						}),
					);
				},
			],
		});
		await expect(h.session.prompt("continue")).rejects.toBe(mapped);
		expect(observed?.message).toBe("post-check failed");
		expect(h.faux.state.callCount).toBe(0);
		expect(h.sessionManager.getEntries().some((entry) => entry.type === "compaction")).toBe(true);
	});

	it.each(["abort", "abortCompaction"] as const)(
		"cancels initial requested compaction through session.%s without business",
		async (method) => {
			let nativeSignal: AbortSignal | undefined;
			let complete = false;
			let h: Harness;
			const created = await nativeHarness(
				{
					extensionFactories: [
						(pi) => {
							pi.on("before_agent_start", (_event, ctx) =>
								ctx.requestCompaction({
									onComplete: () => {
										complete = true;
									},
								}),
							);
						},
					],
				},
				(options) =>
					new Promise((resolve) => {
						nativeSignal = options?.signal;
						if (nativeSignal?.aborted) {
							resolve(fauxAssistantMessage("", { stopReason: "aborted" }));
							return;
						}
						nativeSignal?.addEventListener(
							"abort",
							() => resolve(fauxAssistantMessage("", { stopReason: "aborted" })),
							{ once: true },
						);
						queueMicrotask(() => {
							void h.session[method]();
						});
					}),
			);
			h = created.h;
			await expect(h.session.prompt("continue")).rejects.toSatisfy(
				(error: unknown) => error === nativeSignal?.reason,
			);
			expect(complete).toBe(false);
			expect(h.faux.state.callCount).toBe(0);
			expect(h.eventsOfType("agent_settled")).toHaveLength(1);
			expect(h.sessionManager.getEntries().some((entry) => entry.type === "compaction")).toBe(false);
		},
	);

	it("cancels the lifecycle while asynchronous post-compaction validation is pending", async () => {
		let h: Harness;
		let lifecycleSignal: AbortSignal | undefined;
		let errorSignal: AbortSignal | undefined;
		const created = await nativeHarness({
			extensionFactories: [
				(pi) => {
					pi.on("before_agent_start", (_event, ctx) =>
						ctx.requestCompaction({
							onComplete: async (_result, signal) => {
								lifecycleSignal = signal;
								queueMicrotask(() => {
									void h.session.abort();
								});
								await delay(5);
							},
							onError: (_error, signal) => {
								errorSignal = signal;
								throw new Error("must not replace cancellation");
							},
						}),
					);
				},
			],
		});
		h = created.h;
		await expect(h.session.prompt("continue")).rejects.toSatisfy(
			(error: unknown) => error === lifecycleSignal?.reason,
		);
		expect(errorSignal).toBe(lifecycleSignal);
		expect(errorSignal?.aborted).toBe(true);
		expect(h.faux.state.callCount).toBe(0);
		expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(1);
	});

	it("rejects all coalesced requests when the first completion callback refuses continuation", async () => {
		const completed: number[] = [];
		const failed: number[] = [];
		const { h } = await nativeHarness({
			extensionFactories: [
				(pi) => {
					pi.on("before_agent_start", (_event, ctx) => {
						ctx.requestCompaction({
							onComplete: () => {
								completed.push(1);
								throw new Error("post-check refusal");
							},
							onError: () => {
								failed.push(1);
							},
						});
						ctx.requestCompaction({
							onComplete: () => {
								completed.push(2);
							},
							onError: () => {
								failed.push(2);
							},
						});
					});
				},
			],
		});
		await expect(h.session.prompt("continue")).rejects.toThrow("post-check refusal");
		expect(completed).toEqual([1]);
		expect(failed).toEqual([1, 2]);
		expect(h.faux.state.callCount).toBe(0);
	});

	it.each(["abort", "reload"] as const)(
		"does not carry a queued request across %s before its boundary",
		async (operation) => {
			const { h } = await nativeHarness({});
			let completed = false;
			h.session.requestCompaction({
				onComplete: () => {
					completed = true;
				},
			});
			await h.session[operation]();
			// reload intentionally resets API registrations; restore only the offline provider.
			const fresh =
				operation === "reload"
					? registerFauxProvider({
							api: h.faux.api,
							provider: h.getModel().provider,
							models: [{ id: h.getModel().id }],
						})
					: undefined;
			try {
				(fresh ?? h.faux).setResponses([fauxAssistantMessage("complete without old queued request")]);
				await h.session.prompt("new task");
				expect(h.session.state.errorMessage).toBeUndefined();
				expect(completed).toBe(false);
				expect(h.eventsOfType("compaction_start")).toHaveLength(0);
				expect((fresh ?? h.faux).state.callCount).toBe(1);
			} finally {
				fresh?.unregister();
			}
		},
	);

	it("rejects a concurrent manual compact without replacing the active native controller", async () => {
		let markStarted: (() => void) | undefined;
		let finishSummary: ((message: AssistantMessage) => void) | undefined;
		const started = new Promise<void>((resolve) => {
			markStarted = resolve;
		});
		const summary = new Promise<AssistantMessage>((resolve) => {
			finishSummary = resolve;
		});
		const { h } = await nativeHarness({}, () => {
			markStarted?.();
			return summary;
		});
		const original = h.session.compact();
		await started;
		await expect(h.session.compact()).rejects.toThrow("Compaction is already in progress");
		finishSummary?.(fauxAssistantMessage("Native summary"));
		await original;
		expect(h.eventsOfType("compaction_start")).toHaveLength(1);
		expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(1);
	});

	it.each(["user", "custom"] as const)(
		"joins nested %s phase continuations and their final asynchronous settlement",
		async (kind) => {
			let phases = 0;
			let delayedSettlements = 0;
			const { h } = await nativeHarness({
				extensionFactories: [
					(pi) => {
						pi.on("agent_settled", () => {
							phases++;
							if (phases >= 3) return;
							if (kind === "user") pi.sendUserMessage(`phase ${phases}`);
							else
								pi.sendMessage(
									{ customType: "phase", content: `phase ${phases}`, display: false },
									{ triggerTurn: true },
								);
						});
						pi.on("agent_settled", async () => {
							await delay(10);
							delayedSettlements++;
						});
					},
				],
			});
			h.setResponses([
				fauxAssistantMessage("bootstrap"),
				fauxAssistantMessage("phase one"),
				fauxAssistantMessage("phase two"),
			]);
			await h.session.prompt("start phase task");
			expect(phases).toBe(3);
			expect(delayedSettlements).toBe(3);
			expect(h.faux.state.callCount).toBe(3);
			const lastMessage = h.session.messages.at(-1);
			expect(lastMessage?.role).toBe("assistant");
			if (lastMessage?.role !== "assistant") throw new Error("Missing final assistant");
			expect(lastMessage.content).toEqual([{ type: "text", text: "phase two" }]);
			expect(h.eventsOfType("agent_settled")).toHaveLength(3);
		},
	);

	it("joins pending siblings before propagating an earlier child preflight failure", async () => {
		let h: Harness;
		let dispatched = false;
		let releaseChild: (() => void) | undefined;
		let childStarted: (() => void) | undefined;
		let childCompleted = false;
		const childGate = new Promise<void>((resolve) => {
			releaseChild = resolve;
		});
		const started = new Promise<void>((resolve) => {
			childStarted = resolve;
		});
		const created = await nativeHarness({
			extensionFactories: [
				(pi) => {
					pi.on("agent_settled", () => {
						if (dispatched) return;
						dispatched = true;
						const runtime = h.session.modelRuntime;
						const configured = runtime.hasConfiguredAuth.bind(runtime);
						const checkAuth = runtime.checkAuth.bind(runtime);
						runtime.hasConfiguredAuth = () => false;
						runtime.checkAuth = async () => undefined;
						pi.sendUserMessage("first child denied during auth preflight");
						runtime.hasConfiguredAuth = configured;
						runtime.checkAuth = checkAuth;
						pi.sendMessage(
							{ customType: "pending-sibling", content: "Continue the sibling", display: false },
							{ triggerTurn: true },
						);
					});
				},
			],
		});
		h = created.h;
		h.setResponses([
			fauxAssistantMessage("parent complete"),
			async () => {
				childStarted?.();
				await childGate;
				childCompleted = true;
				return fauxAssistantMessage("sibling complete");
			},
		]);
		let parentDone = false;
		let parentFailure: unknown;
		const parent = h.session.prompt("parent task").then(
			() => {
				parentDone = true;
			},
			(error: unknown) => {
				parentDone = true;
				parentFailure = error;
			},
		);
		try {
			await started;
			await delay(15);
			expect(childCompleted).toBe(false);
			expect(h.session.isStreaming).toBe(true);
			expect(parentDone).toBe(false);
		} finally {
			releaseChild?.();
			await parent;
		}
		expect(childCompleted).toBe(true);
		expect(parentFailure).toBeInstanceOf(Error);
		expect((parentFailure as Error).message).toContain("No API key found");
		expect(h.session.isStreaming).toBe(false);
		expect(h.faux.state.callCount).toBe(2);
	});
});
