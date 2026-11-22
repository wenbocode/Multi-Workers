/**
 * T06-J production host integration: ONE real index.ts composition per window,
 * trusted PM dispatch / worker activation sources, frozen store, C/D pair and
 * pi event accounting. Faux provider only; no paid API, provider call or live
 * root check. This suite never injects a success-only adapter into production.
 */

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import { type AgentTeamLoopComposition, activateWithRuntimeHost } from "../../src/extensions/agent-team-loop/index.ts";
import { ASK_DECISION_TOOL } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	SUBMIT_DECISION_HANDOFF_TOOL,
	type SubmitOfferMetadata,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import {
	dispatchNewTasks,
	type RuntimeHostDispatchFacts,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import type {
	ProductionRuntimeHost,
	RuntimeHostDispatchObservation,
} from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness } from "./harness.ts";

type Harness = Awaited<ReturnType<typeof createHarness>>;

interface Fixture {
	root: string;
	doc: string;
	taskMdPath: string;
	cardSha: string;
	cardText: string;
}

interface ToolState {
	writes: number;
	reads: number;
}

const ACTIVATION_FLAG = "__agentTeamLoopActivated";
const keyName = "key-a";
const taskKey = "local-task";
const claim = currentClaimId();
const originalCwd = process.cwd();
const roots: string[] = [];
const harnesses: Harness[] = [];

function resetActivationFlag(): void {
	delete (globalThis as Record<string, unknown>)[ACTIVATION_FLAG];
}

function sha256(text: string): string {
	return crypto.createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");
}

function budgetBlock(maxSteps: number, remaining: number): string {
	return [
		"## 事项预算事实",
		"- `budget_ref`: `tasks/T-01.md#事项预算事实` + 其 SHA",
		"- `matter_ref`: `key-a/T-01`；`parent_matter_ref`: `key-a`",
		"- `deadline`: `run.json.started_at + 30m`（由 harness 派生）",
		`- \`max_steps\`: ${maxSteps}`,
		"- `no_progress_limit`: 5",
		`- \`remaining_cost\`: ${remaining}，\`cost_consumed\` 与 \`steps_consumed\` 同单位（1 cost unit ≡ 1 tool call；卡明确约定）`,
		"- `steps_consumed` / `no_progress_count`：本运行初始 0",
		"- `source_refs`: 卡 SHA、`run.json`、`_index.parallel`、`task.md` 头",
		"",
	].join("\n");
}

function fixture(options: { maxSteps?: number; remaining?: number; worker?: boolean } = {}): Fixture {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "t06j-integration-"));
	roots.push(root);
	const doc = path.join(root, ".agenticdoc");
	const keyDir = path.join(doc, keyName);
	const workerDir = path.join(keyDir, "workers", taskKey);
	fs.mkdirSync(path.join(keyDir, "tasks"), { recursive: true });
	fs.mkdirSync(path.join(keyDir, "evidence", "research"), { recursive: true });
	fs.mkdirSync(workerDir, { recursive: true });
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.mkdirSync(path.join(root, "src"), { recursive: true });
	fs.writeFileSync(
		path.join(doc, "_index.parallel"),
		`# Index Parallel\n| ${keyName} | active | EXECUTE | ${claim} | | fixture | now |\n`,
	);
	fs.writeFileSync(path.join(doc, "target.yml"), "active: single\n");
	fs.writeFileSync(path.join(root, ".mw", "mw.pid"), String(process.pid));
	fs.writeFileSync(path.join(keyDir, "pm-state.md"), `- Phase: init\n- ClaimId: ${claim}\n`);
	fs.writeFileSync(path.join(keyDir, "spec.md"), `# Spec\n\nAC-001: integration acceptance\n\n${"x".repeat(600)}\n`);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n\n${"x".repeat(600)}\n`);
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "spec-note.md"), "spec research note\n");
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "design-note.md"), "design research note\n");
	const cardText = `# Real titled fixture\n\nowning_pm_claim: ${claim}\ntitle: fixture\n\n${budgetBlock(options.maxSteps ?? 20, options.remaining ?? 20)}`;
	fs.writeFileSync(path.join(keyDir, "tasks", "T-01.md"), cardText);
	const cardSha = sha256(cardText);
	const taskMdPath = path.join(workerDir, "task.md");
	fs.writeFileSync(
		taskMdPath,
		`type: coding\ncard_path: tasks/T-01.md\ncard_sha256: ${cardSha}\nwrite_face: src/a.txt,src/b.txt\n\n${options.worker ? "worker activation positive control\n" : "fixture body\n"}`,
	);
	fs.writeFileSync(path.join(root, "src", "a.txt"), "a0\n");
	fs.writeFileSync(path.join(root, "src", "b.txt"), "b0\n");
	return { root, doc, taskMdPath, cardSha, cardText };
}

const registeredMaterial = {
	question: "PM integration: choose the next bounded action",
	background: {
		task_goal: "Compose and verify the production runtime host",
		current_state: "PM dispatch source and frozen store are registered",
		tried: "none",
		unknowns: "none",
		constraints: "existing active claim and finite card budget only",
	},
	handling_options: [
		{
			id: "continue",
			label: "Continue",
			description: "Proceed with one controlled write",
			consequence: "one action",
			risk: "low",
			conditions: "trusted host source",
		},
		{
			id: "defer",
			label: "Defer",
			description: "Stop after the prepared selection",
			consequence: "no action",
			risk: "low",
			conditions: "trusted host source",
		},
	],
};

function registeredPreparation(): Record<string, unknown> {
	return {
		prepared_at: new Date().toISOString(),
		basis_catalog: [
			{
				id: "basis",
				text: "PM dispatch source and finite budget are registered",
				material_refs: ["background.current_state"],
				applies_to: ["continue"],
			},
		],
	};
}

function toolDetails(h: Harness, name: string): Record<string, unknown> {
	const message = [...h.session.messages]
		.reverse()
		.find((item) => item.role === "toolResult" && item.toolName === name);
	if (message === undefined || message.role !== "toolResult") throw new Error(`missing ${name} tool result`);
	const direct = message.details;
	if (direct !== null && typeof direct === "object" && !Array.isArray(direct) && Object.keys(direct).length > 0)
		return direct as Record<string, unknown>;
	const content = message.content;
	if (typeof content === "string") return { text: content };
	if (Array.isArray(content)) {
		for (const part of content) {
			if (
				part !== null &&
				typeof part === "object" &&
				"type" in part &&
				part.type === "text" &&
				"text" in part &&
				typeof part.text === "string"
			) {
				try {
					const parsed: unknown = JSON.parse(part.text);
					if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed))
						return parsed as Record<string, unknown>;
				} catch {
					return { text: part.text };
				}
			}
		}
	}
	return {};
}

function offerFrom(h: Harness): SubmitOfferMetadata & { offer_id: string } {
	const offer = toolDetails(h, ASK_DECISION_TOOL).submit_offer as SubmitOfferMetadata | undefined;
	expect(offer?.submittable, JSON.stringify(toolDetails(h, ASK_DECISION_TOOL))).toBe(true);
	if (offer === undefined || typeof offer.offer_id !== "string") throw new Error("missing submittable offer");
	return offer as SubmitOfferMetadata & { offer_id: string };
}

async function promptTool(h: Harness, name: string, args: Record<string, unknown>, text: string): Promise<void> {
	h.setResponses([
		fauxAssistantMessage([fauxToolCall(name, args)], { stopReason: "toolUse" }),
		fauxAssistantMessage(text),
	]);
	await h.session.prompt(text);
}

function registerTestTools(pi: ExtensionAPI, state: ToolState): void {
	pi.registerTool({
		name: "write",
		label: "write",
		description: "fixture write",
		parameters: Type.Object({ path: Type.String(), content: Type.String() }),
		execute: async (_id, params, _signal, _update, _ctx) => {
			void _id;
			void _signal;
			void _update;
			void _ctx;
			if (params.path.includes("b.txt")) throw new Error("forced tool error");
			state.writes += 1;
			fs.writeFileSync(path.join(process.cwd(), "src", "a.txt"), `${params.content}\n`);
			fs.writeFileSync(path.join(process.cwd(), "src", "b.txt"), `${params.content}-b\n`);
			return {
				content: [{ type: "text" as const, text: "wrote" }],
				details: {
					completion: "complete",
					executor: "forged-executor",
					targets: ["forged/target"],
					action_refs: ["forged-action-ref"],
					task_key: "forged-task",
					owner: "forged-owner",
					run_id: "forged-run",
					started_at: "2000-01-01T00:00:00.000Z",
				},
			};
		},
	});
	pi.registerTool({
		name: "read",
		label: "read",
		description: "fixture read",
		parameters: Type.Object({ path: Type.String() }),
		execute: async (_id, params, _signal, _update, _ctx) => {
			void _id;
			void _signal;
			void _update;
			void _ctx;
			state.reads += 1;
			return {
				content: [{ type: "text" as const, text: fs.readFileSync(path.join(process.cwd(), params.path), "utf8") }],
				details: {},
			};
		},
	});
}

async function composePm(f: Fixture): Promise<{
	h: Harness;
	composition: AgentTeamLoopComposition;
	state: ToolState;
	facts: RuntimeHostDispatchObservation;
}> {
	process.chdir(f.root);
	resetActivationFlag();
	delete process.env.PI_WORKER_TASK;
	const state: ToolState = { writes: 0, reads: 0 };
	let composition: AgentTeamLoopComposition | undefined;
	const h = await createHarness({
		extensionFactories: [
			async (pi) => {
				composition = await activateWithRuntimeHost(pi);
				registerTestTools(pi, state);
			},
		],
	});
	harnesses.push(h);
	if (composition === undefined) throw new Error("index.ts did not compose the runtime host");
	await h.session.bindExtensions({});
	const store = new WorkerStore(f.doc);
	let docGaps: string[] = [];
	let facts: RuntimeHostDispatchFacts | undefined;
	await dispatchNewTasks(store, f.doc, {
		scope: "cli",
		maxPerScan: 1,
		onDocGate: (_key, gaps) => {
			docGaps = gaps;
			return true;
		},
		onDispatchObserved: (observed) => {
			facts = observed;
			composition?.host.registerPmDispatch(observed);
		},
	});
	if (facts === undefined) throw new Error(`PM dispatch was not observed; doc gaps=${docGaps.join(",")}`);
	return { h, composition, state, facts };
}

async function prepareAndSubmit(
	h: Harness,
	trigger = "local-task",
): Promise<{ offer_id: string; submit: Record<string, unknown> }> {
	await promptTool(
		h,
		ASK_DECISION_TOOL,
		{
			dp: "dp-auto",
			trigger,
			key: keyName,
			task_key: taskKey,
			note: "PM integration fixture",
			material: registeredMaterial,
			preparation: registeredPreparation(),
		},
		"prepare",
	);
	const ask = toolDetails(h, ASK_DECISION_TOOL);
	expect(ask.available).toBe(false);
	const offer = offerFrom(h);
	await promptTool(
		h,
		SUBMIT_DECISION_HANDOFF_TOOL,
		{ offer_id: offer.offer_id, choice: "continue", basis_id: "basis" },
		"submit",
	);
	return { offer_id: offer.offer_id, submit: toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL) };
}

function restartContext(
	h: Harness,
	entries: readonly unknown[],
	_append: (customType: string, data: unknown) => void,
): ExtensionContext {
	for (const raw of entries) {
		const entry = raw as { type?: string; customType?: string; data?: unknown };
		if (entry.type === "custom" && typeof entry.customType === "string")
			h.sessionManager.appendCustomEntry(entry.customType, entry.data);
	}
	return {
		sessionManager: {
			getEntries: () => h.sessionManager.getEntries(),
			getSessionFile: () => h.sessionManager.getSessionFile(),
			getSessionId: () => h.sessionManager.getSessionId(),
		},
	} as unknown as ExtensionContext;
}

beforeEach(() => {
	resetActivationFlag();
	delete process.env.PI_WORKER_TASK;
});

afterEach(() => {
	delete process.env.PI_WORKER_TASK;
	process.chdir(originalCwd);
	resetActivationFlag();
	for (const h of harnesses.splice(0)) h.cleanup();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

describe("T06-J production runtime host integration", () => {
	it("PM service failure stays matter-scoped; ask/submit/default adapter/events/store execution and disposition are real", async () => {
		const f = fixture();
		const { h, composition, state, facts } = await composePm(f);
		const host = composition.host;
		expect(composition.submitHandle.runtimeHost).toBe(host);
		await promptTool(
			h,
			ASK_DECISION_TOOL,
			{
				dp: "dp-auto",
				trigger: "local-task",
				key: keyName,
				task_key: taskKey,
				note: "PM integration fixture",
				material: registeredMaterial,
				preparation: registeredPreparation(),
			},
			"prepare",
		);
		expect(toolDetails(h, ASK_DECISION_TOOL).available).toBe(false);
		await promptTool(h, "read", { path: "src/a.txt" }, "unrelated tool");
		expect(state.reads).toBe(1);
		const offer = offerFrom(h);
		await promptTool(
			h,
			SUBMIT_DECISION_HANDOFF_TOOL,
			{ offer_id: offer.offer_id, choice: "continue", basis_id: "basis" },
			"submit",
		);
		expect(
			toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL).status,
			JSON.stringify(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL)),
		).toBe("planned");
		expect(host.countsSnapshot().selectionCommits, JSON.stringify(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL))).toBe(
			1,
		);
		await promptTool(
			h,
			SUBMIT_DECISION_HANDOFF_TOOL,
			{ offer_id: offer.offer_id, choice: "continue", basis_id: "basis" },
			"repeat",
		);
		expect(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL).business_completed).toBe(false);
		await promptTool(h, "write", { path: "src/a.txt", content: "changed" }, "controlled write");
		expect(state.writes, JSON.stringify(toolDetails(h, "write"))).toBe(1);
		const counts = host.countsSnapshot();
		expect(counts.registered).toBe(1);
		expect(counts.selectionCommits, JSON.stringify(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL))).toBe(1);
		expect(counts.reserves).toBe(1);
		expect(counts.observes).toBe(1);
		expect(counts.recordedWithDisposition).toBe(1);
		expect(counts.recordedWithoutDisposition).toBe(0);
		const childDeadline = new Date(new Date(facts.dispatchedAt).getTime() + 29 * 60_000).toISOString();
		const insufficient = host.reserveChild({
			taskKey,
			reservationId: "too-large",
			steps: 100,
			cost: 100,
			deadline: childDeadline,
		});
		expect(insufficient.ok).toBe(false);
		const small = host.reserveChild({
			taskKey,
			reservationId: "child-1",
			steps: 1,
			cost: 1,
			deadline: childDeadline,
		});
		expect(small.ok).toBe(true);
		expect(host.settleChild(taskKey, "child-1", "terminal:not-observed").ok).toBe(false);
		const childCounts = host.countsSnapshot();
		expect(childCounts.childBlockedInsufficient).toBe(1);
		expect(childCounts.childReserves).toBe(1);
		expect(childCounts.childSettles).toBe(0);
		process.stdout.write(
			`${JSON.stringify({ marker: "T06-K3-ORIGINAL-CHILD", factsDispatchedAt: facts.dispatchedAt, childDeadline, insufficient, small, childCounts })}\n`,
		);
		host.onAgentEnd("shutdown");
		host.onAgentEnd("shutdown");
		const shutdown = host.countsSnapshot();
		expect(shutdown.busyIdleTransitions).toBe(1);
		expect(shutdown.duplicateShutdown).toBe(1);
		expect(shutdown.shutdownOutcome).toBe("ok");
		expect(shutdown.idleDisposition).toBe(true);

		// Split-turn restart: replay the SAME session custom observations into a
		// second host with the exact same registered dispatch facts. No hidden
		// global authority cache, no reconstructed grant and no business replay.
		const captured = h.sessionManager.getEntries();
		resetActivationFlag();
		let second: AgentTeamLoopComposition | undefined;
		const h2 = await createHarness({
			extensionFactories: [
				async (pi) => {
					second = await activateWithRuntimeHost(pi);
					registerTestTools(pi, state);
				},
			],
		});
		harnesses.push(h2);
		if (second === undefined) throw new Error("restart composition missing");
		await h2.session.bindExtensions({});
		const ctx = restartContext(h2, captured, (customType, data) => {
			h2.sessionManager.appendCustomEntry(customType, data);
		});
		second.host.attachSession(ctx, (customType, data) => h2.sessionManager.appendCustomEntry(customType, data));
		expect(second.host.registerPmDispatch(facts).ok).toBe(true);
		const replayed = second.host.countsSnapshot();
		expect(replayed.replayedActionRefs).toBeGreaterThan(0);
		const later = new Date(new Date(facts.dispatchedAt).getTime() + 1000).toISOString();
		expect(second.host.registerPmDispatch({ ...facts, dispatchedAt: later }).ok).toBe(false);
		expect(second.host.countsSnapshot().newCardTurnRefreshes).toBe(1);
		second.host.onAgentEnd("shutdown");
		second.host.onAgentEnd("shutdown");
		expect(second.host.countsSnapshot().duplicateShutdown).toBe(1);
	});

	it("reserveChild rejects a child deadline beyond the registered parent budget", async () => {
		const f = fixture();
		const { composition, facts } = await composePm(f);
		const host = composition.host;
		const before = host.countsSnapshot();
		const overParentDeadline = new Date(new Date(facts.dispatchedAt).getTime() + 31 * 60_000).toISOString();
		const rejected = host.reserveChild({
			taskKey,
			reservationId: "over-parent",
			steps: 1,
			cost: 1,
			deadline: overParentDeadline,
		});
		expect(rejected).toEqual({
			ok: false,
			gaps: ["invalid-input"],
			reason: "finite positive child allocation/unit and bounded canonical deadline required",
		});
		const after = host.countsSnapshot();
		expect(after.childBlockedInsufficient).toBe(before.childBlockedInsufficient);
		expect(after.childReserves).toBe(before.childReserves);
		expect(after.childSettles).toBe(before.childSettles);
		process.stdout.write(
			`${JSON.stringify({ marker: "T06-K3-OVER-PARENT", factsDispatchedAt: facts.dispatchedAt, overParentDeadline, rejected, beforeChildCounters: { childBlockedInsufficient: before.childBlockedInsufficient, childReserves: before.childReserves, childSettles: before.childSettles }, afterChildCounters: { childBlockedInsufficient: after.childBlockedInsufficient, childReserves: after.childReserves, childSettles: after.childSettles } })}\n`,
		);
	});

	it("worker activation positive control uses its immutable run start and exact card pin", async () => {
		const f = fixture({ worker: true });
		process.chdir(f.root);
		process.env.PI_WORKER_TASK = f.taskMdPath;
		resetActivationFlag();
		let composition: AgentTeamLoopComposition | undefined;
		const h = await createHarness({
			extensionFactories: [
				async (pi) => {
					composition = await activateWithRuntimeHost(pi);
				},
			],
		});
		harnesses.push(h);
		if (composition === undefined) throw new Error("worker composition missing");
		await h.session.bindExtensions({});
		expect(composition.host.countsSnapshot().registered).toBe(1);
		// R10 live-lifecycle positive control: keep ask AND submit inside ONE
		// active worker turn, so no agent_end can end the run between them. The
		// ended guard and all worker actions stay intact; a faux response factory
		// extracts the REAL dynamic offer_id from the ask result at provider time.
		h.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall(ASK_DECISION_TOOL, {
						dp: "dp-w-check-task",
						trigger: "worker-local-task",
						key: keyName,
						task_key: taskKey,
						material: {
							task_goal: "Compose and verify the production runtime host",
							reachability_facts: "registered worker activation and finite card budget",
							completed: "none",
							remaining: "one controlled selection",
							blockers: "none",
							constraints: "existing active claim and finite card budget only",
						},
						preparation: {
							prepared_at: new Date().toISOString(),
							basis_catalog: [
								{
									id: "basis",
									text: "worker activation source is registered",
									material_refs: ["reachability_facts"],
									applies_to: ["continue"],
								},
							],
						},
					}),
				],
				{ stopReason: "toolUse" },
			),
			(context) => {
				const blob = JSON.stringify([context.messages, h.session.messages]);
				const match = /offer:([0-9a-f]{40,})/.exec(blob);
				const offerId = match === null ? "" : `offer:${match[1]}`;
				return fauxAssistantMessage(
					[
						fauxToolCall(SUBMIT_DECISION_HANDOFF_TOOL, {
							offer_id: offerId,
							choice: "continue",
							basis_id: "basis",
						}),
					],
					{ stopReason: "toolUse" },
				);
			},
			fauxAssistantMessage("worker done"),
		]);
		await h.session.prompt("prepare and submit within one active worker turn");
		expect(
			composition.host.countsSnapshot().selectionCommits,
			JSON.stringify(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL)),
		).toBe(1);
	});

	it("isError/unknown stops the next business tool and forged details grant nothing", async () => {
		const f = fixture();
		const { h, composition, state } = await composePm(f);
		await prepareAndSubmit(h);
		await promptTool(h, "write", { path: "src/b.txt", content: "error" }, "error write");
		await promptTool(h, "write", { path: "src/a.txt", content: "after-error" }, "blocked write");
		expect(state.writes).toBe(0);
		const counts = composition.host.countsSnapshot();
		expect(counts.unknowns).toBeGreaterThan(0);
		expect(counts.blocks).toBeGreaterThan(0);
		expect(counts.recordedWithDisposition).toBe(0);
	});

	it("one prepared action cannot spend the remaining card budget on repeated writes", async () => {
		const f = fixture({ maxSteps: 3, remaining: 3 });
		const { h, state, composition } = await composePm(f);
		await prepareAndSubmit(h, "budget-task");
		for (let step = 1; step <= 4; step += 1)
			await promptTool(h, "write", { path: "src/a.txt", content: `step-${step}` }, `step-${step}`);
		// One offer authorizes one action. K4 and K8 exercise three distinct
		// authorized actions and refusal of the fourth under the same budget.
		expect(state.writes).toBe(1);
		expect(composition.host.countsSnapshot().blocks).toBeGreaterThan(0);
	});

	it("keeps a PM action admissible while a sibling holds part of its budget", async () => {
		const f = fixture({ maxSteps: 3, remaining: 3 });
		const { h, state, composition, facts } = await composePm(f);
		const host = composition.host;
		const deadline = new Date(Date.parse(facts.dispatchedAt) + 60_000).toISOString();
		expect(host.reserveChild({ taskKey, reservationId: "sibling", steps: 1, cost: 1, deadline })).toMatchObject({
			ok: true,
			value: { status: "reserved" },
		});
		const { submit } = await prepareAndSubmit(h, "sibling-hold");
		expect(submit).toMatchObject({ status: "planned" });
		await promptTool(h, "write", { path: "src/a.txt", content: "one effect" }, "funded PM action");
		expect(state.writes).toBe(1);
		expect(host.countsSnapshot()).toMatchObject({ appends: 1, childReserves: 1 });
		expect(host.reserveChild({ taskKey, reservationId: "too-large", steps: 2, cost: 2, deadline })).toMatchObject({
			ok: false,
			gaps: ["insufficient-remaining"],
		});
	});

	it("R1 default-store positive: one real PM action persists one execution + one disposition; duplicate replay writes nothing new; a forged ref is not a trusted ref", async () => {
		const f = fixture();
		const { h, composition, state } = await composePm(f);
		const host = composition.host;
		await prepareAndSubmit(h, "r1-positive");
		const offer = offerFrom(h);
		// Idempotent replay of the SAME offer/choice (R10): a planned duplicate,
		// never a second selection/execution write.
		await promptTool(
			h,
			SUBMIT_DECISION_HANDOFF_TOOL,
			{ offer_id: offer.offer_id, choice: "continue", basis_id: "basis" },
			"r1-repeat",
		);
		expect(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL).business_completed).toBe(false);
		expect(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL).code).toBe("duplicate");
		// ONE genuine controlled action through the DEFAULT frozen store.
		await promptTool(h, "write", { path: "src/a.txt", content: "r1" }, "r1 controlled write");
		expect(state.writes).toBe(1);
		const counts = host.countsSnapshot();
		expect(counts.selectionCommits).toBe(1); // duplicate was NOT a new commit
		expect(counts.reserves).toBe(1);
		expect(counts.observes).toBe(1);
		expect(counts.recordedWithDisposition).toBe(1); // R1: execution + disposition persisted
		expect(counts.recordedWithoutDisposition).toBe(0);
		const walk = (dir: string, suffix: string): string[] => {
			const out: string[] = [];
			if (!fs.existsSync(dir)) return out;
			for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
				const full = path.join(dir, entry.name);
				if (entry.isDirectory()) out.push(...walk(full, suffix));
				else if (entry.name.endsWith(suffix)) out.push(full);
			}
			return out;
		};
		const records = path.join(f.doc, keyName, "evidence", "decision-handoffs");
		const allJson = walk(records, ".json");
		// Real default-store files (not an inMemory/custom stub).
		expect(walk(records, ".execution.json").length).toBe(1);
		expect(walk(records, ".disposition.json").length).toBe(1);
		expect(walk(path.join(f.doc, "_autopilot", "dp-blocked"), ".json")).toHaveLength(1);
		const selections = allJson.filter((x) => !x.endsWith(".execution.json") && !x.endsWith(".disposition.json"));
		expect(selections.length).toBe(1); // duplicate replay added no second selection write
		// Wrong-ref negative: a forged disposition ref is NOT a synthetic trusted ref.
		expect(composition.submitHandle.hostExpectedFor("disposition:forged-ref")).toBeUndefined();
		expect(composition.submitHandle.hostExpectedFor(String(offer.local_ref))).toBeDefined();
	});
});

// ── T06-J3 append-only: real composition translated finishing path ───────
// LAYER: genuine activateWithRuntimeHost() composition (index.ts), one real
// registered PM dispatch, real ask/submit, real default frozen store and a real
// "write" action A. Physical .json bytes captured before/after. No private
// map/method access, no manual seeding, no permissive trusted-hook override.
function j3DocJson(doc: string): { path: string; sha: string }[] {
	const out: { path: string; sha: string }[] = [];
	const walk = (dir: string): void => {
		// Failed DP requests have a separate diagnostic audit. The byte-invariant
		// snapshots below cover all other project JSON, including DP records.
		if (dir === path.join(doc, "_autopilot", "dp-blocked")) return;
		if (!fs.existsSync(dir)) return;
		for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, e.name);
			if (e.isDirectory()) walk(full);
			else if (e.name.endsWith(".json"))
				out.push({
					path: path.relative(doc, full),
					sha: crypto.createHash("sha256").update(fs.readFileSync(full)).digest("hex"),
				});
		}
	};
	walk(doc);
	return out.sort((a, b) => a.path.localeCompare(b.path));
}

function j3Counts(doc: string) {
	const all = j3DocJson(doc);
	return {
		all,
		executions: all.filter((x) => x.path.endsWith(".execution.json")),
		dispositions: all.filter((x) => x.path.endsWith(".disposition.json")),
		selections: all.filter((x) => !x.path.endsWith(".execution.json") && !x.path.endsWith(".disposition.json")),
	};
}

describe("T06-J3 real composition translated finishing path (append-only)", () => {
	it("POSITIVE legitimate action A persists exactly one execution + one disposition via the translated ref", async () => {
		const f = fixture();
		const before = j3Counts(f.doc);
		expect(before.executions).toHaveLength(0);
		expect(before.dispositions).toHaveLength(0);
		const { h, composition, state } = await composePm(f);
		const host = composition.host;
		await prepareAndSubmit(h, "j3-control");
		const offer = offerFrom(h);
		expect(host.countsSnapshot().selectionCommits).toBe(1);
		await promptTool(h, "write", { path: "src/a.txt", content: "j3" }, "action A");
		expect(state.writes).toBe(1);
		const counts = host.countsSnapshot();
		expect(counts.recordedWithDisposition).toBe(1);
		expect(counts.recordedWithoutDisposition).toBe(0);
		const after = j3Counts(f.doc);
		expect(after.executions).toHaveLength(1);
		expect(after.dispositions).toHaveLength(1);
		expect(after.selections).toHaveLength(1);
		// authentic offer still resolvable; a disposition ref is NOT an offer ref
		expect(composition.submitHandle.hostExpectedFor(String(offer.local_ref))).toBeDefined();
	});

	it("NEGATIVE forged disposition ref / forged offer / replay write nothing foreign; legitimate association retained", async () => {
		const f = fixture();
		const { h, composition } = await composePm(f);
		const host = composition.host;
		await prepareAndSubmit(h, "j3-neg");
		const offer = offerFrom(h);
		await promptTool(h, "write", { path: "src/a.txt", content: "j3-neg" }, "action A");
		const legit = j3Counts(f.doc);
		expect(legit.executions).toHaveLength(1);
		expect(legit.dispositions).toHaveLength(1);
		expect(legit.selections).toHaveLength(1);
		// (N1) forged disposition ref resolves to no genuine offer (H boundary).
		expect(composition.submitHandle.hostExpectedFor("disposition:forged-ref")).toBeUndefined();
		// (N2) a forged offer_id submit is refused and writes nothing.
		await promptTool(
			h,
			SUBMIT_DECISION_HANDOFF_TOOL,
			{ offer_id: "offer:forged", choice: "continue", basis_id: "basis" },
			"forged submit",
		);
		expect(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL).status).not.toBe("planned");
		// (N3) idempotent replay of the genuine offer writes nothing new.
		await promptTool(
			h,
			SUBMIT_DECISION_HANDOFF_TOOL,
			{ offer_id: offer.offer_id, choice: "continue", basis_id: "basis" },
			"replay",
		);
		expect(toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL).business_completed).toBe(false);
		const after = j3Counts(f.doc);
		expect(after).toEqual(legit); // exact physical bytes unchanged, no foreign write
		expect(after.executions).toHaveLength(1);
		expect(after.dispositions).toHaveLength(1);
		expect(after.selections).toHaveLength(1);
		// legitimate association / control retained
		expect(composition.submitHandle.hostExpectedFor(String(offer.local_ref))).toBeDefined();
		expect(host.countsSnapshot().selectionCommits).toBe(1);
		expect(host.countsSnapshot().recordedWithDisposition).toBe(1);
	});
});

// ── T06-J4 append-only: public genuine-offer translated route + semantic records ──
// Only the public ProductionRuntimeHost.bindExpectedFor reader is bounded. It
// delegates to the real submit handle; no private map/method, custom store,
// authority stub, fabricated offer or verifier success stub is introduced.
type J4JsonRecord = Record<string, unknown>;
type J4Offer = SubmitOfferMetadata & { offer_id: string; local_ref: string };
type J4Projection = NonNullable<ReturnType<AgentTeamLoopComposition["submitHandle"]["hostExpectedFor"]>>;
type J4Reader = Parameters<ProductionRuntimeHost["bindExpectedFor"]>[0];
type J4Snapshot = ReturnType<typeof j3DocJson>;

interface J4Prepared {
	trigger: string;
	note: string;
	question: string;
	state: string;
	offer: J4Offer;
	material: Record<string, unknown>;
	preparation: Record<string, unknown>;
	materialDigest: string;
	basisDigest: string;
	projection: J4Projection;
}

interface J4ReaderEvent {
	requestedRef: string;
	delegatedRef: string;
	aExecutionExists: boolean;
	projection: J4Projection | null;
}

interface J4TargetManifestEntry {
	path: string;
	state: "file";
	sha256: string;
}

interface J4BindingSummary {
	bindingVersion: string;
	budgetRef: string;
	matterRef: string;
	materialDigest: string;
	basisDigest: string;
	selectionBinding: J4JsonRecord;
}

interface J4PhysicalPaths {
	selection: string;
	execution: string;
	disposition: string;
	selectionRel: string;
	executionRel: string;
	dispositionRel: string;
}

function j4IsRecord(value: unknown): value is J4JsonRecord {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

function j4AsRecord(value: unknown, label: string): J4JsonRecord {
	if (!j4IsRecord(value)) throw new Error(`${label} is not a JSON object`);
	return value;
}

function j4ReadJson(file: string, label: string): J4JsonRecord {
	const raw = fs.readFileSync(file, "utf8");
	const parsed: unknown = JSON.parse(raw);
	return j4AsRecord(parsed, label);
}

function j4StringField(record: J4JsonRecord, key: string, label: string): string {
	const value = record[key];
	if (typeof value !== "string" || value === "") throw new Error(`${label}.${key} is not a nonblank string`);
	return value;
}

function j4NumberField(record: J4JsonRecord, key: string, label: string): number {
	const value = record[key];
	if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label}.${key} is not a finite number`);
	return value;
}

function j4FalseField(record: J4JsonRecord, key: string, label: string): void {
	if (record[key] !== false) throw new Error(`${label}.${key} is not false`);
}

function j4ArrayField(record: J4JsonRecord, key: string, label: string): unknown[] {
	const value = record[key];
	if (!Array.isArray(value)) throw new Error(`${label}.${key} is not an array`);
	return value;
}

function j4ProjectionFrom(value: unknown, label: string): J4Projection {
	const record = j4AsRecord(value, label);
	j4StringField(record, "matter_identity", label);
	j4StringField(record, "matter_ref", label);
	j4StringField(record, "matter_version", label);
	j4StringField(record, "material_digest", label);
	j4StringField(record, "basis_digest", label);
	return record as unknown as J4Projection;
}

function j4StableJson(value: unknown): string {
	if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
	if (Array.isArray(value)) return `[${value.map(j4StableJson).join(",")}]`;
	const record = value as J4JsonRecord;
	return `{${Object.keys(record)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${j4StableJson(record[key])}`)
		.join(",")}}`;
}

function j4Digest(value: unknown): string {
	return crypto.createHash("sha256").update(j4StableJson(value), "utf8").digest("hex");
}

function j4CardBacktick(cardText: string, field: string): string {
	const line = cardText.split(/\r?\n/).find((entry) => entry.includes(`\`${field}\`:`));
	const match = /`([A-Za-z_]+)`\s*:\s*`([^`]+)`/.exec(line ?? "");
	if (match?.[2] === undefined) throw new Error(`missing card field ${field}`);
	return match[2];
}

function j4WriteFace(f: Fixture): string[] {
	const line = fs
		.readFileSync(f.taskMdPath, "utf8")
		.split(/\r?\n/)
		.find((entry) => entry.startsWith("write_face:"));
	const value = line?.slice("write_face:".length).trim() ?? "";
	const targets = value
		.split(",")
		.map((entry) => entry.trim())
		.filter((entry) => entry !== "")
		.sort();
	if (
		targets.length === 0 ||
		targets.some(
			(entry) => path.posix.normalize(entry) !== entry || path.posix.isAbsolute(entry) || entry.includes(".."),
		)
	)
		throw new Error("physical task.md write_face is not a canonical complete target set");
	return targets;
}

function j4TargetManifest(root: string, targets: readonly string[]): J4TargetManifestEntry[] {
	return [...targets].sort().map((target) => ({
		path: target,
		state: "file" as const,
		sha256: crypto
			.createHash("sha256")
			.update(fs.readFileSync(path.join(root, ...target.split("/"))))
			.digest("hex"),
	}));
}

function j4ManifestDigest(manifest: readonly J4TargetManifestEntry[]): string {
	return `sha256:${crypto.createHash("sha256").update(JSON.stringify(manifest), "utf8").digest("hex")}`;
}

function j4EncodedRef(ref: string): string {
	return Buffer.from(ref, "utf8").toString("base64url");
}

function j4PmPath(doc: string, ref: string, suffix: string): string {
	return path.join(doc, keyName, "evidence", "decision-handoffs", `${j4EncodedRef(ref)}${suffix}`);
}

function j4PhysicalPaths(f: Fixture, localRef: string, callId: string): J4PhysicalPaths {
	const selection = j4PmPath(f.doc, localRef, ".json");
	const execution = j4PmPath(f.doc, localRef, ".execution.json");
	const disposition = j4PmPath(f.doc, `disposition:${callId}`, ".disposition.json");
	return {
		selection,
		execution,
		disposition,
		selectionRel: path.relative(f.doc, selection),
		executionRel: path.relative(f.doc, execution),
		dispositionRel: path.relative(f.doc, disposition),
	};
}

const J4_EVIDENCE_NAMES = ["j4-positive-evidence.json", "j4-route-evidence.json"] as const;

function j4OwnedEvidenceDir(f: Fixture): string {
	const tmpRel = path.relative(os.tmpdir(), f.root);
	if (
		tmpRel === "" ||
		tmpRel.startsWith("..") ||
		path.isAbsolute(tmpRel) ||
		!path.basename(f.root).startsWith("t06j-integration-")
	)
		throw new Error("J4 evidence root is not this test's OS-temp fixture");
	if (!roots.includes(f.root)) throw new Error("J4 evidence root is not registered for afterEach cleanup");
	const dir = path.join(f.root, "j4-owned-evidence");
	if (!path.relative(f.doc, dir).startsWith(".."))
		throw new Error("J4 evidence dir would pollute the doc JSON snapshot");
	fs.mkdirSync(dir, { recursive: true });
	return dir;
}

function j4EvidenceFile(f: Fixture, name: string): string {
	if (!J4_EVIDENCE_NAMES.some((allowed) => allowed === name))
		throw new Error(`J4 evidence name is not owned: ${name}`);
	return path.join(j4OwnedEvidenceDir(f), name);
}

function j4OwnedEvidence(f: Fixture, file: string): J4JsonRecord {
	const rootRel = path.relative(f.root, file);
	const docRel = path.relative(f.doc, file);
	if (rootRel.startsWith("..") || path.isAbsolute(rootRel) || !docRel.startsWith(".."))
		throw new Error("J4 evidence escaped its owned fixture surface");
	return {
		fixtureRoot: f.root,
		evidenceDir: path.dirname(file),
		evidenceFile: file,
		outsideDocJson: docRel.startsWith(".."),
		cleanupRegistry: "afterEach:roots",
		cleanupRegistered: roots.includes(f.root),
	};
}

function j4WriteEvidence(f: Fixture, name: string, value: unknown): void {
	const file = j4EvidenceFile(f, name);
	fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
	// Same full payload, single structured stdout line, so this run's caller can
	// archive its OWN artifact from stdout without any repo/history exporter.
	process.stdout.write(`${JSON.stringify({ marker: "T06-J4-EVIDENCE", name, payload: value })}\n`);
}

function j4OfferFrom(h: Harness): J4Offer {
	const offer = offerFrom(h);
	const localRef = offer.local_ref;
	if (typeof localRef !== "string" || localRef === "") throw new Error("real ask offer has no local_ref");
	return { ...offer, offer_id: offer.offer_id, local_ref: localRef };
}

async function j4Prepare(
	h: Harness,
	composition: AgentTeamLoopComposition,
	trigger: string,
	note: string,
	question: string,
	state: string,
): Promise<J4Prepared> {
	const material: Record<string, unknown> = {
		question,
		background: { ...registeredMaterial.background, current_state: state },
		handling_options: registeredMaterial.handling_options,
	};
	const preparation = registeredPreparation();
	const basisCatalog = preparation.basis_catalog;
	if (!Array.isArray(basisCatalog)) throw new Error("preparation basis_catalog missing");
	const materialDigest = j4Digest({ material, context: null });
	const basisDigest = j4Digest({ basis_catalog: basisCatalog });
	await promptTool(
		h,
		ASK_DECISION_TOOL,
		{
			dp: "dp-auto",
			trigger,
			key: keyName,
			task_key: taskKey,
			note,
			material,
			preparation,
		},
		`prepare ${trigger}`,
	);
	expect(toolDetails(h, ASK_DECISION_TOOL).available).toBe(false);
	const offer = j4OfferFrom(h);
	const projection = j4ProjectionFrom(
		composition.submitHandle.hostExpectedFor(offer.local_ref),
		`${trigger} projection`,
	);
	const identity = j4AsRecord(projection.identity, `${trigger} projection.identity`);
	expect(j4StringField(identity, "source", trigger)).toBe("pm");
	expect(j4StringField(identity, "key", trigger)).toBe(keyName);
	expect(j4StringField(identity, "role", trigger)).toBe("pm");
	expect(j4StringField(identity, "claimId", trigger)).toBe(claim);
	expect(j4StringField(identity, "taskKey", trigger)).toBe(taskKey);
	expect(Object.hasOwn(identity, "runId")).toBe(false);
	expect(projection.material_digest).toBe(materialDigest);
	expect(projection.basis_digest).toBe(basisDigest);
	return { trigger, note, question, state, offer, material, preparation, materialDigest, basisDigest, projection };
}

async function j4Commit(h: Harness, prepared: J4Prepared): Promise<J4JsonRecord> {
	await promptTool(
		h,
		SUBMIT_DECISION_HANDOFF_TOOL,
		{
			offer_id: prepared.offer.offer_id,
			choice: "continue",
			basis_id: "basis",
		},
		`commit ${prepared.trigger}`,
	);
	const submit = toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL);
	expect(submit.status, JSON.stringify(submit)).toBe("planned");
	expect(submit.code, JSON.stringify(submit)).toBe("written");
	expect(submit.local_ref, JSON.stringify(submit)).toBe(prepared.offer.local_ref);
	expect(submit.business_completed, JSON.stringify(submit)).toBe(false);
	return submit;
}

function j4LastWriteCallId(h: Harness): string {
	const events = h.eventsOfType("tool_execution_end").filter((event) => event.toolName === "write");
	const last = events.at(-1);
	if (last === undefined) throw new Error("real write execution_end event missing");
	return last.toolCallId;
}

function j4AssertBinding(value: unknown, label: string, cardSha: string): void {
	const binding = j4AsRecord(value, label);
	expect(j4StringField(binding, "role", label)).toBe("pm");
	expect(j4StringField(binding, "owner", label)).toBe(claim);
	expect(j4StringField(binding, "claim_id", label)).toBe(claim);
	expect(j4StringField(binding, "key", label)).toBe(keyName);
	expect(j4StringField(binding, "binding_version", label)).toBe(`runtime-t06-r1:${claim}:${cardSha}`);
	expect(j4StringField(binding, "observed_at", label)).not.toBe("");
	// The frozen PM binding intentionally omits task/run; never invent them.
	expect(Object.hasOwn(binding, "task_key")).toBe(false);
	expect(Object.hasOwn(binding, "run_id")).toBe(false);
}

function j4AssertSelection(f: Fixture, prepared: J4Prepared): J4BindingSummary {
	const file = j4PmPath(f.doc, prepared.offer.local_ref, ".json");
	const record = j4ReadJson(file, "selection");
	expect(j4NumberField(record, "schema_version", "selection")).toBe(1);
	expect(j4StringField(record, "kind", "selection")).toBe("local-selection");
	expect(j4StringField(record, "origin", "selection")).toBe("local-decision");
	expect(j4StringField(record, "source", "selection")).toBe("pm");
	expect(j4StringField(record, "local_ref", "selection")).toBe(prepared.offer.local_ref);
	const budgetRef = j4CardBacktick(f.cardText, "budget_ref");
	const cardMatterRef = j4CardBacktick(f.cardText, "matter_ref");
	expect(budgetRef).toBe("tasks/T-01.md#事项预算事实");
	expect(cardMatterRef).toBe("key-a/T-01");
	expect(j4StringField(record, "budget_ref", "selection")).toBe(budgetRef);
	expect(j4StringField(record, "matter_ref", "selection")).toBe(prepared.projection.matter_ref);
	expect(j4StringField(record, "matter_version", "selection")).toBe(prepared.projection.matter_version);
	expect(j4StringField(record, "material_digest", "selection")).toBe(prepared.materialDigest);
	expect(j4StringField(record, "basis_digest", "selection")).toBe(prepared.basisDigest);
	expect(j4StringField(record, "selected_action", "selection")).toBe("continue");
	expect(j4StringField(record, "selected_basis_id", "selection")).toBe("basis");
	expect(j4StringField(record, "action_state", "selection")).toBe("planned");
	j4FalseField(record, "business_completed", "selection");
	expect(j4StringField(record, "created_at", "selection")).not.toBe("");
	const selectionBinding = j4AsRecord(record.host_binding, "selection.host_binding");
	j4AssertBinding(selectionBinding, "selection.host_binding", f.cardSha);
	return {
		bindingVersion: j4StringField(selectionBinding, "binding_version", "selection.host_binding"),
		budgetRef,
		matterRef: j4StringField(record, "matter_ref", "selection"),
		materialDigest: prepared.materialDigest,
		basisDigest: prepared.basisDigest,
		selectionBinding,
	};
}

function j4AssertExecution(
	f: Fixture,
	prepared: J4Prepared,
	summary: J4BindingSummary,
	facts: RuntimeHostDispatchObservation,
	callId: string,
	beforeDigest: string,
	afterDigest: string,
): J4JsonRecord {
	const file = j4PmPath(f.doc, prepared.offer.local_ref, ".execution.json");
	const record = j4ReadJson(file, "execution");
	const resultRef = `tool_result:${callId}`;
	const executionRunId = `${facts.taskKey}@${facts.dispatchedAt}`;
	expect(j4NumberField(record, "schema_version", "execution")).toBe(1);
	expect(j4StringField(record, "kind", "execution")).toBe("local-execution");
	expect(j4StringField(record, "origin", "execution")).toBe("local-decision");
	expect(j4StringField(record, "source", "execution")).toBe("pm");
	expect(j4StringField(record, "local_ref", "execution")).toBe(prepared.offer.local_ref);
	j4AssertBinding(record.host_binding, "execution.host_binding", f.cardSha);
	expect(j4StringField(record, "action_ref", "execution")).toBe(callId);
	expect(j4StringField(record, "result_ref", "execution")).toBe(resultRef);
	expect(j4StringField(record, "executor", "execution")).toBe(JSON.stringify([executionRunId, callId]));
	expect(j4StringField(record, "target_digest", "execution")).toBe(afterDigest);
	expect(j4StringField(record, "observed_effect", "execution")).toBe(
		`byte-manifest:${beforeDigest}->${afterDigest};business-correctness=unverified`,
	);
	expect(j4StringField(record, "effect_state", "execution")).toBe("known");
	expect(j4StringField(record, "verified_by", "execution")).toBe("target-digest-v1@runtime-execution-1");
	expect(j4StringField(record, "budget_ref", "execution")).toBe(summary.budgetRef);
	expect(j4StringField(record, "created_at", "execution")).not.toBe("");
	return record;
}

function j4AssertDisposition(f: Fixture, summary: J4BindingSummary, callId: string): J4JsonRecord {
	const dispositionRef = `disposition:${callId}`;
	const resultRef = `tool_result:${callId}`;
	const file = j4PmPath(f.doc, dispositionRef, ".disposition.json");
	const record = j4ReadJson(file, "disposition");
	expect(j4NumberField(record, "schema_version", "disposition")).toBe(1);
	expect(j4StringField(record, "disposition_ref", "disposition")).toBe(dispositionRef);
	expect(j4StringField(record, "feedback_ref", "disposition")).toBe(`feedback:${callId}`);
	expect(j4StringField(record, "matter_ref", "disposition")).toBe(summary.matterRef);
	expect(j4StringField(record, "kind", "disposition")).toBe("collect-evidence");
	expect(j4StringField(record, "owner", "disposition")).toBe(claim);
	expect(record.binding).toEqual(summary.selectionBinding);
	j4AssertBinding(record.binding, "disposition.binding", f.cardSha);
	expect(j4StringField(record, "goal_ref", "disposition")).toBe("goal:observed-byte-manifest");
	expect(j4ArrayField(record, "gap_refs", "disposition")).toEqual([]);
	expect(j4ArrayField(record, "basis_refs", "disposition")).toEqual([callId, resultRef]);
	const plannedAction = j4AsRecord(record.planned_action, "disposition.planned_action");
	expect(j4StringField(plannedAction, "tool", "disposition.planned_action")).toBe("write");
	expect(j4StringField(plannedAction, "scope_ref", "disposition.planned_action")).toBe("host-complete-write-face");
	expect(plannedAction.read_only).toBe(false);
	expect(j4StringField(record, "expected_result", "disposition")).toBe("target byte manifest");
	expect(j4StringField(record, "result_consumer", "disposition")).toBe("owning-pm:review");
	expect(j4StringField(record, "budget_ref", "disposition")).toBe(summary.budgetRef);
	expect(j4StringField(record, "status", "disposition")).toBe("observed");
	return record;
}

describe("T06-J4 public genuine-offer translated route (append-only, <=3 tests)", () => {
	it("T06-J4-1 unchanged reader persists semantically correlated records; forged and post-effect replay are exact", async () => {
		const f = fixture();
		const positiveEvidenceFile = j4EvidenceFile(f, "j4-positive-evidence.json");
		const owned = j4OwnedEvidence(f, positiveEvidenceFile);
		expect(owned.outsideDocJson, JSON.stringify(owned)).toBe(true);
		expect(owned.cleanupRegistered, JSON.stringify(owned)).toBe(true);
		expect(path.relative(f.doc, positiveEvidenceFile).startsWith(".."), JSON.stringify(owned)).toBe(true);
		const beforeState = j3DocJson(f.doc);
		expect(beforeState).toEqual([]);
		const { h, composition, state, facts } = await composePm(f);
		const host = composition.host;
		const prepared = await j4Prepare(
			h,
			composition,
			"j4-positive",
			"T06-J4 positive unchanged public reader",
			"T06-J4 positive: choose one unchanged-reader bounded action",
			"Positive control has one genuine registered PM dispatch and finite card budget",
		);
		const aExecutionPath = j4PmPath(f.doc, prepared.offer.local_ref, ".execution.json");
		const readerTrace: J4ReaderEvent[] = [];
		const unchangedReader: J4Reader = (requestedRef) => {
			const projection = composition.submitHandle.hostExpectedFor(requestedRef);
			readerTrace.push({
				requestedRef,
				delegatedRef: requestedRef,
				aExecutionExists: fs.existsSync(aExecutionPath),
				projection: projection === undefined ? null : j4ProjectionFrom(projection, "unchanged projection"),
			});
			return projection as unknown as ReturnType<J4Reader>;
		};
		host.bindExpectedFor(unchangedReader);
		await j4Commit(h, prepared);
		const targets = j4WriteFace(f);
		const beforeManifest = j4TargetManifest(f.root, targets);
		const beforeDigest = j4ManifestDigest(beforeManifest);
		await promptTool(h, "write", { path: "src/a.txt", content: "j4-positive" }, "genuine action A");
		const afterManifest = j4TargetManifest(f.root, targets);
		const afterDigest = j4ManifestDigest(afterManifest);
		expect(fs.readFileSync(path.join(f.root, "src", "a.txt"), "utf8")).toBe("j4-positive\n");
		expect(fs.readFileSync(path.join(f.root, "src", "b.txt"), "utf8")).toBe("j4-positive-b\n");
		const callId = j4LastWriteCallId(h);
		const paths = j4PhysicalPaths(f, prepared.offer.local_ref, callId);
		const legitState = j3DocJson(f.doc);
		const counts = host.countsSnapshot();
		j4WriteEvidence(f, "j4-positive-evidence.json", {
			observed_at: new Date().toISOString(),
			owned,
			beforeState,
			legitState,
			paths,
			callId,
			executionRunId: `${facts.taskKey}@${facts.dispatchedAt}`,
			targets,
			beforeManifest,
			afterManifest,
			beforeDigest,
			afterDigest,
			readerTrace,
			counts,
			stateWrites: state.writes,
			offer: prepared.offer,
			projection: prepared.projection,
			materialDigest: prepared.materialDigest,
			basisDigest: prepared.basisDigest,
			cardSha: f.cardSha,
			budgetRef: j4CardBacktick(f.cardText, "budget_ref"),
		});
		expect(fs.existsSync(positiveEvidenceFile), JSON.stringify(owned)).toBe(true);
		expect(
			j3DocJson(f.doc).some((entry) => entry.path.includes("j4-owned-evidence")),
			"owned evidence must not appear in the doc JSON snapshot",
		).toBe(false);
		const firstEvidenceSha256 = sha256(fs.readFileSync(positiveEvidenceFile, "utf8"));

		const expectedPaths = [paths.selectionRel, paths.executionRel, paths.dispositionRel].sort((a, b) =>
			a.localeCompare(b),
		);
		expect(
			legitState.map((entry) => entry.path),
			JSON.stringify(legitState),
		).toEqual(expectedPaths);
		expect(readerTrace.length).toBeGreaterThan(0);
		expect(
			readerTrace.every((entry) => entry.requestedRef === entry.delegatedRef),
			JSON.stringify(readerTrace),
		).toBe(true);
		expect(
			readerTrace.some((entry) => entry.requestedRef === prepared.offer.local_ref),
			JSON.stringify(readerTrace),
		).toBe(true);
		const summary = j4AssertSelection(f, prepared);
		const execution = j4AssertExecution(f, prepared, summary, facts, callId, beforeDigest, afterDigest);
		const disposition = j4AssertDisposition(f, summary, callId);
		expect(counts.appends).toBe(1);
		expect(counts.dispositions).toBe(1);
		expect(counts.selectionCommits).toBe(1);
		expect(counts.recordedWithDisposition).toBe(1);
		expect(counts.recordedWithoutDisposition).toBe(0);
		expect(state.writes).toBe(1);

		await promptTool(
			h,
			SUBMIT_DECISION_HANDOFF_TOOL,
			{ offer_id: "offer:j4-forged", choice: "continue", basis_id: "basis" },
			"forged submit",
		);
		const forged = toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL);
		expect(forged.status, JSON.stringify(forged)).toBe("refused");
		expect(forged.reason, JSON.stringify(forged)).toBe("unknown-or-unbound-offer");
		expect(forged.selection_written, JSON.stringify(forged)).toBe(false);
		expect(forged.business_completed, JSON.stringify(forged)).toBe(false);
		expect(forged.gaps, JSON.stringify(forged)).toEqual(["offer_id"]);
		// Segment 1: immediately after the forged submit, independently prove
		// no doc JSON write and no target byte change (not the final combined state).
		const forgedState = j3DocJson(f.doc);
		const forgedManifest = j4TargetManifest(f.root, targets);
		const forgedDigest = j4ManifestDigest(forgedManifest);
		expect(forgedState, JSON.stringify({ legitState, forgedState })).toEqual(legitState);
		expect(forgedManifest, JSON.stringify({ afterManifest, forgedManifest })).toEqual(afterManifest);
		expect(forgedDigest, JSON.stringify({ afterDigest, forgedDigest })).toBe(afterDigest);

		await promptTool(
			h,
			SUBMIT_DECISION_HANDOFF_TOOL,
			{ offer_id: prepared.offer.offer_id, choice: "continue", basis_id: "basis" },
			"post-effect replay",
		);
		const replay = toolDetails(h, SUBMIT_DECISION_HANDOFF_TOOL);
		expect(replay.status, JSON.stringify(replay)).toBe("planned");
		expect(replay.code, JSON.stringify(replay)).toBe("duplicate");
		expect(replay.business_completed, JSON.stringify(replay)).toBe(false);
		expect(replay.local_ref, JSON.stringify(replay)).toBe(prepared.offer.local_ref);
		// Segment 2: immediately after the replay, repeat BOTH independent proofs.
		const replayState = j3DocJson(f.doc);
		const replayManifest = j4TargetManifest(f.root, targets);
		const replayDigest = j4ManifestDigest(replayManifest);
		expect(replayState, JSON.stringify({ legitState, replayState })).toEqual(legitState);
		expect(replayManifest, JSON.stringify({ afterManifest, replayManifest })).toEqual(afterManifest);
		expect(replayDigest, JSON.stringify({ afterDigest, replayDigest })).toBe(afterDigest);
		const finalState = j3DocJson(f.doc);
		expect(finalState, JSON.stringify({ legitState, finalState })).toEqual(legitState);
		expect(host.countsSnapshot().selectionCommits).toBe(1);
		expect(host.countsSnapshot().recordedWithDisposition).toBe(1);
		j4WriteEvidence(f, "j4-positive-evidence.json", {
			observed_at: new Date().toISOString(),
			owned,
			firstEvidenceSha256,
			beforeState,
			legitState,
			finalState,
			forgedSnapshot: { state: forgedState, manifest: forgedManifest, digest: forgedDigest },
			replaySnapshot: { state: replayState, manifest: replayManifest, digest: replayDigest },
			paths,
			callId,
			executionRunId: `${facts.taskKey}@${facts.dispatchedAt}`,
			targets,
			beforeManifest,
			afterManifest,
			beforeDigest,
			afterDigest,
			readerTrace,
			counts,
			stateWrites: state.writes,
			offer: prepared.offer,
			projection: prepared.projection,
			selection: j4ReadJson(paths.selection, "selection evidence"),
			execution,
			disposition,
			materialDigest: prepared.materialDigest,
			basisDigest: prepared.basisDigest,
			cardSha: f.cardSha,
			budgetRef: summary.budgetRef,
			forged,
			replay,
		});
	});

	it("T06-J4-2 public reader routes translated A ref to genuine B after A execution; real guard outcome is retained", async () => {
		const f = fixture();
		const routeEvidenceFile = j4EvidenceFile(f, "j4-route-evidence.json");
		const owned = j4OwnedEvidence(f, routeEvidenceFile);
		expect(owned.outsideDocJson, JSON.stringify(owned)).toBe(true);
		expect(owned.cleanupRegistered, JSON.stringify(owned)).toBe(true);
		expect(path.relative(f.doc, routeEvidenceFile).startsWith(".."), JSON.stringify(owned)).toBe(true);
		const beforeState = j3DocJson(f.doc);
		expect(beforeState).toEqual([]);
		const { h, composition, state, facts } = await composePm(f);
		const host = composition.host;
		const a = await j4Prepare(
			h,
			composition,
			"j4-a",
			"T06-J4 genuine offer A on the registered task",
			"T06-J4 A: choose the bounded controlled write",
			"A matter: registered PM dispatch with the original finite card budget",
		);
		const b = await j4Prepare(
			h,
			composition,
			"j4-b",
			"T06-J4 genuine offer B on the same registered task",
			"T06-J4 B: choose a substantively different bounded action",
			"B matter: same registered PM dispatch and card with a different substantive current state",
		);
		expect(a.offer.local_ref).not.toBe(b.offer.local_ref);
		expect(a.offer.offer_id).not.toBe(b.offer.offer_id);
		expect(a.projection.matter_ref).not.toBe(b.projection.matter_ref);
		expect(a.projection.matter_identity).not.toBe(b.projection.matter_identity);
		expect(a.projection.material_digest).not.toBe(b.projection.material_digest);
		expect(a.projection.identity?.source).toBe(b.projection.identity?.source);
		expect(a.projection.identity?.key).toBe(b.projection.identity?.key);
		expect(a.projection.identity?.role).toBe(b.projection.identity?.role);
		expect(a.projection.identity?.claimId).toBe(b.projection.identity?.claimId);
		expect(a.projection.identity?.taskKey).toBe(b.projection.identity?.taskKey);
		expect(a.projection.identity?.runId).toBeUndefined();
		expect(b.projection.identity?.runId).toBeUndefined();
		expect(composition.submitHandle.hostExpectedFor(a.offer.local_ref)).toBeDefined();
		expect(composition.submitHandle.hostExpectedFor(b.offer.local_ref)).toBeDefined();

		const aExecutionPath = j4PmPath(f.doc, a.offer.local_ref, ".execution.json");
		const routeTrace: J4ReaderEvent[] = [];
		let barrierSnapshot: J4Snapshot | undefined;
		const boundedReader: J4Reader = (requestedRef) => {
			const aExecutionExists = fs.existsSync(aExecutionPath);
			const route = requestedRef === a.offer.local_ref && aExecutionExists;
			const delegatedRef = route ? b.offer.local_ref : requestedRef;
			const projection = composition.submitHandle.hostExpectedFor(delegatedRef);
			routeTrace.push({
				requestedRef,
				delegatedRef,
				aExecutionExists,
				projection: projection === undefined ? null : j4ProjectionFrom(projection, "delegated projection"),
			});
			if (route && barrierSnapshot === undefined) barrierSnapshot = j3DocJson(f.doc);
			return projection as unknown as ReturnType<J4Reader>;
		};
		host.bindExpectedFor(boundedReader);
		await j4Commit(h, a);
		const targets = j4WriteFace(f);
		const beforeManifest = j4TargetManifest(f.root, targets);
		const beforeDigest = j4ManifestDigest(beforeManifest);
		await promptTool(
			h,
			"write",
			{ path: "src/a.txt", content: "j4-routed" },
			"genuine action A with bounded public reader",
		);
		const afterManifest = j4TargetManifest(f.root, targets);
		const afterDigest = j4ManifestDigest(afterManifest);
		const callId = j4LastWriteCallId(h);
		const paths = j4PhysicalPaths(f, a.offer.local_ref, callId);
		const afterState = j3DocJson(f.doc);
		const counts = host.countsSnapshot();
		j4WriteEvidence(f, "j4-route-evidence.json", {
			observed_at: new Date().toISOString(),
			owned,
			beforeState,
			barrierSnapshot,
			afterState,
			paths,
			callId,
			executionRunId: `${facts.taskKey}@${facts.dispatchedAt}`,
			targets,
			beforeManifest,
			afterManifest,
			beforeDigest,
			afterDigest,
			routeTrace,
			counts,
			stateWrites: state.writes,
			a: { offer: a.offer, projection: a.projection, materialDigest: a.materialDigest, basisDigest: a.basisDigest },
			b: { offer: b.offer, projection: b.projection, materialDigest: b.materialDigest, basisDigest: b.basisDigest },
			cardSha: f.cardSha,
			budgetRef: j4CardBacktick(f.cardText, "budget_ref"),
			publicExactStoreCodeObservable: false,
		});
		expect(fs.existsSync(routeEvidenceFile), JSON.stringify(owned)).toBe(true);
		expect(
			j3DocJson(f.doc).some((entry) => entry.path.includes("j4-owned-evidence")),
			"owned evidence must not appear in the doc JSON snapshot",
		).toBe(false);

		const summary = j4AssertSelection(f, a);
		const execution = j4AssertExecution(f, a, summary, facts, callId, beforeDigest, afterDigest);
		const barrier = barrierSnapshot;
		const publicOutcome = { counts, routeTrace, afterState, barrier, paths };
		expect(
			routeTrace.some(
				(entry) =>
					entry.requestedRef === a.offer.local_ref &&
					entry.delegatedRef === a.offer.local_ref &&
					!entry.aExecutionExists,
			),
			JSON.stringify(publicOutcome),
		).toBe(true);
		expect(
			routeTrace.some(
				(entry) =>
					entry.requestedRef === a.offer.local_ref &&
					entry.delegatedRef === b.offer.local_ref &&
					entry.aExecutionExists &&
					entry.projection?.matter_ref === b.projection.matter_ref,
			),
			JSON.stringify(publicOutcome),
		).toBe(true);
		expect(
			routeTrace.some((entry) => entry.requestedRef.startsWith("disposition:")),
			JSON.stringify(publicOutcome),
		).toBe(false);
		expect(
			routeTrace.every(
				(entry) =>
					entry.delegatedRef === entry.requestedRef ||
					(entry.requestedRef === a.offer.local_ref &&
						entry.delegatedRef === b.offer.local_ref &&
						entry.aExecutionExists),
			),
			JSON.stringify(publicOutcome),
		).toBe(true);
		expect(b, JSON.stringify(publicOutcome)).toBeDefined();
		if (barrier === undefined) throw new Error("public reader route barrier was never observed");
		const barrierA = barrier.filter(
			(entry) => entry.path === paths.selectionRel || entry.path === paths.executionRel,
		);
		const afterA = afterState.filter(
			(entry) => entry.path === paths.selectionRel || entry.path === paths.executionRel,
		);
		expect(barrierA, JSON.stringify(publicOutcome)).toHaveLength(2);
		expect(
			afterA.map((entry) => `${entry.path}:${entry.sha}`),
			JSON.stringify(publicOutcome),
		).toEqual(barrierA.map((entry) => `${entry.path}:${entry.sha}`));
		expect(afterState, JSON.stringify(publicOutcome)).toHaveLength(2);
		expect(
			afterState.some((entry) => entry.path === paths.dispositionRel),
			JSON.stringify(publicOutcome),
		).toBe(false);
		expect(
			afterState.filter((entry) => entry.path.endsWith(".disposition.json")),
			JSON.stringify(publicOutcome),
		).toEqual([]);
		expect(
			afterState.filter((entry) => entry.path.endsWith(".execution.json")),
			JSON.stringify(publicOutcome),
		).toHaveLength(1);
		const bEncoded = j4EncodedRef(b.offer.local_ref);
		expect(
			afterState.some((entry) => entry.path.includes(bEncoded)),
			JSON.stringify(publicOutcome),
		).toBe(false);
		expect(
			barrier.some((entry) => entry.path.includes(bEncoded)),
			JSON.stringify(publicOutcome),
		).toBe(false);
		for (const entry of afterState) {
			const record = j4ReadJson(path.join(f.doc, entry.path), "retained physical record");
			expect(record.local_ref, JSON.stringify(publicOutcome)).toBe(a.offer.local_ref);
			expect(record.matter_ref, JSON.stringify(publicOutcome)).not.toBe(b.projection.matter_ref);
		}
		expect(state.writes, JSON.stringify(publicOutcome)).toBe(1);
		expect(counts.selectionCommits, JSON.stringify(publicOutcome)).toBe(1);
		expect(counts.appends, JSON.stringify(publicOutcome)).toBe(1);
		expect(counts.dispositions, JSON.stringify(publicOutcome)).toBe(0);
		expect(counts.recordedWithDisposition, JSON.stringify(publicOutcome)).toBe(0);
		expect(counts.recordedWithoutDisposition, JSON.stringify(publicOutcome)).toBe(1);
		expect(execution.local_ref).toBe(a.offer.local_ref);
	});
});

// 鈹€鈹€ T06-K4 append-only: explicit authorized successors on one pinned card 鈹€鈹€
// No production seam, store seed, private map injection or new budget unit.
// A separate fixture card pins ONE bounded ordered set of three business
// writes BEFORE dispatch; each successor uses a genuinely distinct public
// ask/submit matter and the unchanged production composition.
interface K4Fixture extends Fixture {
	grant: readonly string[];
}

interface K4Artifact {
	path: string;
	bytes: number;
	sha256: string;
	body: unknown;
	raw: string;
}

interface K4ReaderEvent {
	requestedRef: string;
	found: boolean;
	matter_ref: unknown;
	material_digest: unknown;
}

type K4Reader = Parameters<ProductionRuntimeHost["bindExpectedFor"]>[0];
type K4Counts = ReturnType<ProductionRuntimeHost["countsSnapshot"]>;

interface K4Snapshot {
	docJson: ReturnType<typeof j3DocJson>;
	artifacts: K4Artifact[];
	counts: K4Counts;
	ledger: unknown[];
	writeCallIds: string[];
	stateWrites: number;
	readerTrace: K4ReaderEvent[];
}

interface K4Step {
	index: number;
	askInput: Record<string, unknown>;
	askDetails: Record<string, unknown>;
	offer: Record<string, unknown>;
	projection: unknown;
	submitInput: Record<string, unknown>;
	submitDetails: Record<string, unknown>;
	writeInput: Record<string, unknown>;
	writeDetails: Record<string, unknown>;
	snapshots: { before: K4Snapshot; afterAsk: K4Snapshot; afterSubmit: K4Snapshot; afterWrite: K4Snapshot };
	targets: string[];
	beforeManifest: J4TargetManifestEntry[];
	afterManifest: J4TargetManifestEntry[];
	beforeDigest: string;
	afterDigest: string;
	physical: J4PhysicalPaths | undefined;
}

function k4AuthorizedFixture(): K4Fixture {
	const f = fixture({ maxSteps: 3, remaining: 3 });
	const grant = [
		"write#one:src/a.txt,src/b.txt ordered effect one",
		"write#two:src/a.txt,src/b.txt ordered effect two",
		"write#three:src/a.txt,src/b.txt ordered effect three",
	] as const;
	const cardText = [
		"# Real titled fixture",
		"",
		`owning_pm_claim: ${claim}`,
		"title: fixture",
		"",
		budgetBlock(3, 3),
		"- `authorization_scope`: bounded ordered set of three business writes/effects before real dispatch",
		`- \`authorized_action_one\`: \`${grant[0]}\``,
		`- \`authorized_action_two\`: \`${grant[1]}\``,
		`- \`authorized_action_three\`: \`${grant[2]}\``,
		"- `authorized_action_order`: one then two then three on one pinned card, one budget unit and one dispatch start; no per-action card, clock or unit reset",
		"",
	].join("\n");
	const cardSha = sha256(cardText);
	fs.writeFileSync(path.join(f.doc, keyName, "tasks", "T-01.md"), cardText);
	fs.writeFileSync(
		f.taskMdPath,
		`type: coding\ncard_path: tasks/T-01.md\ncard_sha256: ${cardSha}\nwrite_face: src/a.txt,src/b.txt\n\nT06-K4 bounded ordered authorized effects\n`,
	);
	return { ...f, cardText, cardSha, grant };
}

function k4String(value: unknown): string | undefined {
	return typeof value === "string" && value !== "" ? value : undefined;
}

function k4Details(h: Harness, name: string): Record<string, unknown> {
	const message = [...h.session.messages]
		.reverse()
		.find((item) => item.role === "toolResult" && item.toolName === name);
	if (message === undefined || message.role !== "toolResult") return { missingToolResult: true, toolName: name };
	const direct = message.details;
	if (direct !== null && typeof direct === "object" && !Array.isArray(direct) && Object.keys(direct).length > 0)
		return direct as Record<string, unknown>;
	const content = message.content;
	if (typeof content === "string") return { text: content };
	if (Array.isArray(content)) {
		for (const part of content) {
			if (
				part !== null &&
				typeof part === "object" &&
				"type" in part &&
				part.type === "text" &&
				"text" in part &&
				typeof part.text === "string"
			) {
				try {
					const parsed: unknown = JSON.parse(part.text);
					if (j4IsRecord(parsed)) return parsed;
				} catch {
					return { text: part.text };
				}
			}
		}
	}
	return {};
}

function k4OfferOf(details: Record<string, unknown>): Record<string, unknown> {
	const raw = details.submit_offer;
	return j4IsRecord(raw) ? raw : { missing_submit_offer: true, submit_offer: raw ?? null };
}

function k4DocArtifacts(doc: string): K4Artifact[] {
	const out: K4Artifact[] = [];
	const walk = (dir: string): void => {
		if (!fs.existsSync(dir)) return;
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) walk(full);
			else if (entry.name.endsWith(".json")) {
				const rawBytes = fs.readFileSync(full);
				const raw = rawBytes.toString("utf8");
				let body: unknown;
				try {
					body = JSON.parse(raw) as unknown;
				} catch (error) {
					body = { parseError: String(error) };
				}
				out.push({
					path: path.relative(doc, full),
					bytes: rawBytes.length,
					sha256: crypto.createHash("sha256").update(rawBytes).digest("hex"),
					body,
					raw,
				});
			}
		}
	};
	walk(doc);
	return out.sort((a, b) => a.path.localeCompare(b.path));
}

function k4Ledger(h: Harness): unknown[] {
	const entries = h.sessionManager.getEntries() as readonly unknown[];
	return entries.flatMap((raw) => {
		const entry = raw as { type?: unknown; customType?: unknown; data?: unknown };
		return entry.type === "custom" && entry.customType === "mw-runtime-budget-v1" ? [entry.data ?? null] : [];
	});
}

function k4WriteCallIds(h: Harness): string[] {
	const events = h.eventsOfType("tool_execution_end") as readonly unknown[];
	return events.flatMap((raw) => {
		const event = raw as { toolName?: unknown; toolCallId?: unknown };
		return event.toolName === "write" && typeof event.toolCallId === "string" ? [event.toolCallId] : [];
	});
}

function k4Snapshot(
	f: Fixture,
	h: Harness,
	host: ProductionRuntimeHost,
	state: ToolState,
	readerTrace: readonly K4ReaderEvent[],
): K4Snapshot {
	return {
		docJson: j3DocJson(f.doc),
		artifacts: k4DocArtifacts(f.doc),
		counts: host.countsSnapshot(),
		ledger: k4Ledger(h),
		writeCallIds: k4WriteCallIds(h),
		stateWrites: state.writes,
		readerTrace: [...readerTrace],
	};
}

function k4Brief(snapshot: K4Snapshot): Record<string, unknown> {
	return {
		docJson: snapshot.docJson,
		counts: snapshot.counts,
		ledger: snapshot.ledger,
		writeCallIds: snapshot.writeCallIds,
		stateWrites: snapshot.stateWrites,
		readerTrace: snapshot.readerTrace,
	};
}

function k4Emit(marker: string, payload: unknown): void {
	process.stdout.write(`${j4StableJson({ marker, observed_at: new Date().toISOString(), payload })}\n`);
}

function k4Material(
	f: K4Fixture,
	facts: RuntimeHostDispatchObservation,
	index: number,
	prior: readonly K4Artifact[],
): Record<string, unknown> {
	const evidence =
		prior.length === 0
			? "none; initial control doc has zero decision JSON artifacts"
			: prior.map((item) => `${item.path}:${item.sha256}`).join(";");
	return {
		question: `T06-K4 authorized successor ${index}: perform bounded ordered business write ${index} of three`,
		background: {
			task_goal: registeredMaterial.background.task_goal,
			current_state: `pinned card ${f.cardSha} explicitly authorizes ordered effects [${f.grant.join(" | ")}] before dispatch; one dispatch started_at ${facts.dispatchedAt}; current per-action persisted evidence: ${evidence}`,
			tried:
				index === 1
					? "none"
					: `authorized effects one through ${index - 1} attempted through real public ask, submit and write`,
			unknowns: "none",
			constraints:
				"one fixed card, one budget unit and one dispatch start; max_steps 3; remaining_cost 3; 1 cost unit equals 1 tool call; no new card, clock or unit per action",
		},
		handling_options: [
			{
				id: "continue",
				label: `Authorized write ${index}`,
				description: `bounded ordered write ${index} of three on the pinned write face`,
				consequence: `one controlled write effect ${index}`,
				risk: "low",
				conditions: "explicit pinned card authorization and current per-action evidence",
			},
			{
				id: "defer",
				label: `Defer authorized write ${index}`,
				description: `stop before bounded ordered write ${index} of three`,
				consequence: `no business write effect ${index}`,
				risk: "low",
				conditions: "no current authorized successor action",
			},
		],
	};
}

function k4Preparation(
	f: K4Fixture,
	material: Record<string, unknown>,
	index: number,
	prior: readonly K4Artifact[],
): Record<string, unknown> {
	const evidence =
		prior.length === 0
			? "initial empty decision artifact snapshot"
			: prior.map((item) => `${item.path}:${item.sha256}`).join(";");
	return {
		prepared_at: new Date().toISOString(),
		basis_catalog: [
			{
				id: `basis-k4-${index}`,
				text: `card ${f.cardSha} authorizes ordered effect ${index}: ${f.grant[index - 1]}; material digest ${j4Digest({ material, context: null })}; current persisted evidence ${evidence}`,
				material_refs: ["background.current_state"],
				applies_to: ["continue"],
			},
		],
	};
}

// ── T06-K5 append-only: read-only terminal store-return observer ─────────
// Wraps the REAL composed public controller/store methods and delegates with
// unchanged arguments and `this`. It injects no grant, no store, no map seed
// and no success; every real verifier and store check still runs.
interface K5TerminalCall {
	phase: string;
	layer: "runtime-execution" | "local-selection-store";
	method: "appendExecution" | "saveDisposition";
	observed_at: string;
	args: unknown;
	result: unknown;
	counts: K4Counts;
}

type K5AsyncMethod = (...args: readonly unknown[]) => Promise<unknown>;

interface K5ObservedControllers {
	execution: { appendExecution: K5AsyncMethod; saveDisposition: K5AsyncMethod };
	store: { appendExecution: K5AsyncMethod; saveDisposition: K5AsyncMethod };
}

function k5CloneJson(value: unknown): unknown {
	if (value === undefined) return null;
	try {
		return JSON.parse(JSON.stringify(value)) as unknown;
	} catch {
		return { unserializable: String(value) };
	}
}

function k5WrapMethod<T extends object>(
	owner: T,
	key: keyof T,
	layer: K5TerminalCall["layer"],
	method: K5TerminalCall["method"],
	phase: string,
	host: ProductionRuntimeHost,
	calls: K5TerminalCall[],
): void {
	const original = owner[key];
	if (typeof original !== "function") throw new Error(`K5 observer cannot wrap ${layer}.${String(key)}`);
	const fn = original as K5AsyncMethod;
	const wrapped: K5AsyncMethod = async (...args: readonly unknown[]): Promise<unknown> => {
		const result: unknown = await Reflect.apply(fn, owner, [...args]);
		const call: K5TerminalCall = {
			phase,
			layer,
			method,
			observed_at: new Date().toISOString(),
			args: k5CloneJson(args),
			result: k5CloneJson(result),
			counts: host.countsSnapshot(),
		};
		calls.push(call);
		k4Emit("T06-K5-TERMINAL-RETURN", call);
		return result;
	};
	Reflect.set(owner, key, wrapped);
}

function k5ObserveTerminal(host: ProductionRuntimeHost, phase: string): K5TerminalCall[] {
	const hidden = host as unknown as { controllers?: K5ObservedControllers };
	const controllers = hidden.controllers;
	if (controllers === undefined) throw new Error("K5 observer requires the real composed production controllers");
	const calls: K5TerminalCall[] = [];
	k5WrapMethod(controllers.execution, "appendExecution", "runtime-execution", "appendExecution", phase, host, calls);
	k5WrapMethod(controllers.execution, "saveDisposition", "runtime-execution", "saveDisposition", phase, host, calls);
	k5WrapMethod(controllers.store, "appendExecution", "local-selection-store", "appendExecution", phase, host, calls);
	k5WrapMethod(controllers.store, "saveDisposition", "local-selection-store", "saveDisposition", phase, host, calls);
	return calls;
}

// ── T06-K6 append-only: delegated real-method branch observation ──────────
// Each wrapper invokes the original method with the same owner and arguments.
// It records return, throw and not-attempted as separate facts. No state is
// seeded, no result is replaced and no controller/store is substituted.
interface K6BranchCall {
	seq: number;
	phase: string;
	layer: string;
	method: string;
	event: "enter" | "return" | "throw";
	observed_at: string;
	action_ref: string | null;
	args: unknown;
	result?: unknown;
	host_state: unknown;
	counts: K4Counts;
}

type K6Method = (...args: readonly unknown[]) => unknown;

function k6CloneJson(value: unknown): unknown {
	if (value === undefined) return { kind: "undefined" };
	try {
		return JSON.parse(JSON.stringify(value)) as unknown;
	} catch {
		return { unserializable: String(value) };
	}
}

function k6ActionRef(args: readonly unknown[]): string | null {
	for (const arg of args) {
		if (j4IsRecord(arg)) {
			const direct = arg.toolCallId ?? arg.call_id ?? arg.action_ref;
			if (typeof direct === "string" && direct !== "") return direct;
			const request = arg.request;
			if (j4IsRecord(request) && typeof request.call_id === "string" && request.call_id !== "")
				return request.call_id;
			const call = arg.call;
			if (j4IsRecord(call) && typeof call.toolCallId === "string" && call.toolCallId !== "") return call.toolCallId;
		} else if (typeof arg === "string" && arg.length >= 6 && !arg.includes(":")) {
			return arg;
		}
	}
	return null;
}

function k6HostState(host: ProductionRuntimeHost): unknown {
	const hidden = host as unknown as Record<string, unknown>;
	const pending = hidden.pendingCalls;
	return {
		pendingCalls: pending instanceof Map ? k6CloneJson([...pending.entries()]) : null,
		activeLocalRef: k6CloneJson(hidden.activeLocalRef),
		activeSource: k6CloneJson(hidden.activeSource),
		controlBlocked: k6CloneJson(hidden.controlBlocked),
		observationFailed: k6CloneJson(hidden.observationFailed),
		historyFailed: k6CloneJson(hidden.historyFailed),
	};
}

function k6WrapNamed(
	owner: object,
	key: string,
	layer: string,
	method: string,
	phase: string,
	host: ProductionRuntimeHost,
	calls: K6BranchCall[],
	nextSeq: () => number,
): void {
	const record = owner as unknown as Record<string, unknown>;
	const original = record[key];
	if (typeof original !== "function") throw new Error(`K6 observer cannot wrap ${layer}.${key}`);
	const fn = original as K6Method;
	const wrapped: K6Method = (...args: readonly unknown[]): unknown => {
		const actionRef = k6ActionRef(args);
		const base = {
			phase,
			layer,
			method,
			action_ref: actionRef,
			args: k6CloneJson(args),
		};
		const enter: K6BranchCall = {
			seq: nextSeq(),
			...base,
			event: "enter",
			observed_at: new Date().toISOString(),
			host_state: k6HostState(host),
			counts: host.countsSnapshot(),
		};
		calls.push(enter);
		k4Emit("T06-K6-BRANCH-CALL", enter);
		try {
			const value: unknown = Reflect.apply(fn, owner, [...args]);
			const recordReturn = (result: unknown): unknown => {
				calls.push({
					seq: nextSeq(),
					...base,
					event: "return",
					observed_at: new Date().toISOString(),
					result: k6CloneJson(result),
					host_state: k6HostState(host),
					counts: host.countsSnapshot(),
				});
				k4Emit("T06-K6-BRANCH-CALL", calls.at(-1));
				return result;
			};
			if (value instanceof Promise) return value.then(recordReturn);
			return recordReturn(value);
		} catch (error) {
			const call: K6BranchCall = {
				seq: nextSeq(),
				...base,
				event: "throw",
				observed_at: new Date().toISOString(),
				result: { thrown: String(error) },
				host_state: k6HostState(host),
				counts: host.countsSnapshot(),
			};
			calls.push(call);
			k4Emit("T06-K6-BRANCH-CALL", call);
			throw error;
		}
	};
	record[key] = wrapped;
}

function k6ObserveBranches(host: ProductionRuntimeHost, phase: string): K6BranchCall[] {
	const hidden = host as unknown as {
		controllers?: {
			budget: Record<string, unknown>;
			execution: Record<string, unknown>;
		};
	};
	const controllers = hidden.controllers;
	if (controllers === undefined) throw new Error("K6 observer requires the real composed production controllers");
	const calls: K6BranchCall[] = [];
	let seq = 0;
	const nextSeq = (): number => ++seq;
	for (const method of ["afterToolResult", "finish", "appendEvent", "readTargetAuthorization", "budgetSnapshotFor"])
		k6WrapNamed(host, method, "production-runtime-host", method, phase, host, calls, nextSeq);
	for (const method of ["observe", "settleUnknown", "snapshot", "preflight"])
		k6WrapNamed(controllers.budget, method, "runtime-budget", method, phase, host, calls, nextSeq);
	for (const method of ["observeToolResult", "verifyExecution", "appendExecution", "saveDisposition"])
		k6WrapNamed(controllers.execution, method, "runtime-execution", method, phase, host, calls, nextSeq);
	return calls;
}

describe("T06-K4 authorized successors (append-only)", () => {
	it("T06-K4-1 three explicitly authorized public actions, immutable joins, and old-offer replay", async () => {
		const f = k4AuthorizedFixture();
		const { h, composition, state, facts } = await composePm(f);
		const host = composition.host;
		const readerTrace: K4ReaderEvent[] = [];
		const k4Reader: K4Reader = (requestedRef) => {
			const projection = composition.submitHandle.hostExpectedFor(requestedRef);
			const record = projection as unknown as Record<string, unknown> | undefined;
			readerTrace.push({
				requestedRef,
				found: projection !== undefined,
				matter_ref: record?.matter_ref ?? null,
				material_digest: record?.material_digest ?? null,
			});
			return projection as unknown as ReturnType<K4Reader>;
		};
		host.bindExpectedFor(k4Reader);
		const k5Phase = process.env.T06_K5_PHASE ?? "pre-fix";
		const k5TerminalCalls = k5ObserveTerminal(host, k5Phase);
		const k6BranchCalls = k6ObserveBranches(host, k5Phase);
		const targets = j4WriteFace(f);
		const fixedStart = "2026-11-16T15:50:02.213Z";
		const originalBudget = {
			originalCase: "finite card budget blocks step four",
			max_steps: 3,
			remaining_cost: 3,
			expected_writes: 3,
			source: "original integration test lines 486-494; unchanged red",
		};
		const initial = k4Snapshot(f, h, host, state, readerTrace);
		k4Emit("T06-K4-SETUP", {
			fixedStart,
			originalBudget,
			cardSha: f.cardSha,
			cardText: f.cardText,
			grant: f.grant,
			facts,
			taskMd: fs.readFileSync(f.taskMdPath, "utf8"),
			targets,
			initial,
		});
		const steps: K4Step[] = [];
		for (let index = 1; index <= 3; index += 1) {
			const prior = index === 1 ? [] : (steps[index - 2]?.snapshots.afterWrite.artifacts ?? []);
			const material = k4Material(f, facts, index, prior);
			const preparation = k4Preparation(f, material, index, prior);
			const note = `T06-K4 authorized ordered effect ${index} on one pinned card`;
			const trigger = `k4-action-${index}`;
			const askInput = {
				dp: "dp-auto",
				trigger,
				key: keyName,
				task_key: taskKey,
				note,
				material,
				preparation,
			};
			const before = k4Snapshot(f, h, host, state, readerTrace);
			await promptTool(h, ASK_DECISION_TOOL, askInput, `prepare ${trigger}`);
			const askDetails = k4Details(h, ASK_DECISION_TOOL);
			const offer = k4OfferOf(askDetails);
			const localRef = k4String(offer.local_ref) ?? "";
			const projection = localRef === "" ? undefined : composition.submitHandle.hostExpectedFor(localRef);
			const afterAsk = k4Snapshot(f, h, host, state, readerTrace);
			const submitInput = {
				offer_id: k4String(offer.offer_id) ?? "",
				choice: "continue",
				basis_id: `basis-k4-${index}`,
			};
			await promptTool(h, SUBMIT_DECISION_HANDOFF_TOOL, submitInput, `commit ${trigger}`);
			const submitDetails = k4Details(h, SUBMIT_DECISION_HANDOFF_TOOL);
			const afterSubmit = k4Snapshot(f, h, host, state, readerTrace);
			const beforeManifest = j4TargetManifest(f.root, targets);
			const beforeDigest = j4ManifestDigest(beforeManifest);
			const writeInput = { path: "src/a.txt", content: `k4-${index}` };
			await promptTool(h, "write", writeInput, `action ${index}`);
			const writeDetails = k4Details(h, "write");
			const afterManifest = j4TargetManifest(f.root, targets);
			const afterDigest = j4ManifestDigest(afterManifest);
			const afterWrite = k4Snapshot(f, h, host, state, readerTrace);
			const callId = afterWrite.writeCallIds.at(-1);
			const physical = localRef !== "" && callId !== undefined ? j4PhysicalPaths(f, localRef, callId) : undefined;
			const step: K4Step = {
				index,
				askInput,
				askDetails,
				offer,
				projection,
				submitInput,
				submitDetails,
				writeInput,
				writeDetails,
				snapshots: { before, afterAsk, afterSubmit, afterWrite },
				targets,
				beforeManifest,
				afterManifest,
				beforeDigest,
				afterDigest,
				physical,
			};
			steps.push(step);
			k4Emit("T06-K4-STEP", {
				...step,
				snapshots: {
					before: k4Brief(before),
					afterAsk: k4Brief(afterAsk),
					afterSubmit: k4Brief(afterSubmit),
					afterWrite,
				},
			});
		}
		const firstOffer = k4String(steps[0]?.offer.offer_id) ?? "";
		const replayBefore = k4Snapshot(f, h, host, state, readerTrace);
		const replaySubmitInput = { offer_id: firstOffer, choice: "continue", basis_id: "basis-k4-1" };
		await promptTool(h, SUBMIT_DECISION_HANDOFF_TOOL, replaySubmitInput, "replay old offer");
		const replaySubmit = k4Details(h, SUBMIT_DECISION_HANDOFF_TOOL);
		const replayAfterSubmit = k4Snapshot(f, h, host, state, readerTrace);
		const replayWriteInput = { path: "src/a.txt", content: "k4-old-offer-replay" };
		await promptTool(h, "write", replayWriteInput, "old offer replay write");
		const replayWrite = k4Details(h, "write");
		const finalSnapshot = k4Snapshot(f, h, host, state, readerTrace);
		const replay = {
			replaySubmitInput,
			replaySubmit,
			replayAfterSubmit: k4Brief(replayAfterSubmit),
			replayWriteInput,
			replayWrite,
			replayBefore: k4Brief(replayBefore),
			finalSnapshot,
		};
		k4Emit("T06-K4-REPLAY", replay);
		k4Emit("T06-K4-FINAL", {
			cardSha: f.cardSha,
			cardShaAfter: sha256(fs.readFileSync(path.join(f.doc, keyName, "tasks", "T-01.md"), "utf8")),
			grant: f.grant,
			facts,
			steps: steps.map((step) => ({
				index: step.index,
				offer_id: step.offer.offer_id ?? null,
				local_ref: step.offer.local_ref ?? null,
				submit: step.submitDetails,
				write: step.writeDetails,
				physical: step.physical,
			})),
			finalSnapshot,
		});

		const thirdStep = steps[2];
		const thirdCallId = thirdStep?.snapshots.afterWrite.writeCallIds.at(-1) ?? "";
		const thirdLocalRef = k4String(thirdStep?.offer.local_ref) ?? "";
		const thirdStoreExecution = k5TerminalCalls.filter(
			(call) =>
				call.layer === "local-selection-store" &&
				call.method === "appendExecution" &&
				j4StableJson(call.args).includes(thirdLocalRef),
		);
		const thirdStoreDisposition = k5TerminalCalls.filter(
			(call) =>
				call.layer === "local-selection-store" &&
				call.method === "saveDisposition" &&
				j4StableJson(call.args).includes(thirdCallId),
		);
		const thirdOuterExecution = k5TerminalCalls.filter(
			(call) =>
				call.layer === "runtime-execution" &&
				call.method === "appendExecution" &&
				j4StableJson(call.args).includes(thirdCallId),
		);
		const thirdOuterDisposition = k5TerminalCalls.filter(
			(call) =>
				call.layer === "runtime-execution" &&
				call.method === "saveDisposition" &&
				j4StableJson(call.args).includes(thirdCallId),
		);
		k4Emit("T06-K5-THIRD-TERMINAL", {
			phase: k5Phase,
			join: {
				offer_id: thirdStep?.offer.offer_id ?? null,
				local_ref: thirdLocalRef,
				call_id: thirdCallId,
				result_ref: `tool_result:${thirdCallId}`,
				disposition_ref: `disposition:${thirdCallId}`,
				source: "pm",
				task_key: taskKey,
				execution_run_id: `${facts.taskKey}@${facts.dispatchedAt}`,
				claim_id: claim,
				card_sha256: f.cardSha,
				budget_ref: j4CardBacktick(f.cardText, "budget_ref"),
				authorization_unit: j4CardBacktick(f.cardText, "matter_ref"),
				before_digest: thirdStep?.beforeDigest ?? null,
				after_digest: thirdStep?.afterDigest ?? null,
			},
			reservation_and_effect: {
				ledger: thirdStep?.snapshots.afterWrite.ledger ?? [],
				counts: thirdStep?.snapshots.afterWrite.counts ?? null,
				state_writes: thirdStep?.snapshots.afterWrite.stateWrites ?? null,
				doc_json: thirdStep?.snapshots.afterWrite.docJson ?? [],
			},
			storeAppendExecution: thirdStoreExecution.at(-1) ?? {
				notAttempted: true,
				reason: "no third LocalSelectionStore.appendExecution call was observed",
			},
			storeSaveDisposition: thirdStoreDisposition.at(-1) ?? {
				notAttempted: true,
				reason: "no third LocalSelectionStore.saveDisposition call was observed",
			},
			outerAppendExecution: thirdOuterExecution.at(-1) ?? {
				notAttempted: true,
				reason: "no third RuntimeExecutionController.appendExecution call was observed",
			},
			outerSaveDisposition: thirdOuterDisposition.at(-1) ?? {
				notAttempted: true,
				reason: "no third RuntimeExecutionController.saveDisposition call was observed",
			},
			allCalls: k5TerminalCalls,
		});
		const thirdEnter = k6BranchCalls.findIndex(
			(call) => call.method === "afterToolResult" && call.event === "enter" && call.action_ref === thirdCallId,
		);
		const thirdReturnIndex = k6BranchCalls.findIndex(
			(call, index) =>
				index >= thirdEnter &&
				call.method === "afterToolResult" &&
				(call.event === "return" || call.event === "throw"),
		);
		const thirdBranchCalls =
			thirdEnter >= 0
				? k6BranchCalls.slice(thirdEnter, thirdReturnIndex >= 0 ? thirdReturnIndex + 1 : undefined)
				: [];
		const k6Result = (method: string): unknown =>
			thirdBranchCalls.find((call) => call.method === method && call.event === "return")?.result ?? {
				notAttempted: true,
			};
		const k6MethodOutcome = (method: string): unknown => {
			const enter = thirdBranchCalls.find((call) => call.method === method && call.event === "enter");
			if (enter === undefined) return { notAttempted: true };
			const done = thirdBranchCalls.find(
				(call) => call.method === method && (call.event === "return" || call.event === "throw"),
			);
			return done === undefined ? { attemptedNoReturn: true } : { event: done.event, result: done.result ?? null };
		};
		k4Emit("T06-K6-TERMINAL-BRANCH-PRE", {
			phase: k5Phase,
			sameActionId: thirdCallId,
			join: {
				offer_id: thirdStep?.offer.offer_id ?? null,
				local_ref: thirdLocalRef,
				action_ref: thirdCallId,
				result_ref: `tool_result:${thirdCallId}`,
				disposition_ref: `disposition:${thirdCallId}`,
				source: "pm",
				task_key: taskKey,
				execution_run_id: `${facts.taskKey}@${facts.dispatchedAt}`,
				claim_id: claim,
				card_sha256: f.cardSha,
				card_path: "tasks/T-01.md",
				budget_ref: j4CardBacktick(f.cardText, "budget_ref"),
				authorization_unit: j4CardBacktick(f.cardText, "matter_ref"),
				before_digest: thirdStep?.beforeDigest ?? null,
				after_digest: thirdStep?.afterDigest ?? null,
				before_manifest: thirdStep?.beforeManifest ?? [],
				after_manifest: thirdStep?.afterManifest ?? [],
			},
			reservation_and_effect: {
				ledger: thirdStep?.snapshots.afterWrite.ledger ?? [],
				counts: thirdStep?.snapshots.afterWrite.counts ?? null,
				state_writes: thirdStep?.snapshots.afterWrite.stateWrites ?? null,
				write_call_ids: thirdStep?.snapshots.afterWrite.writeCallIds ?? [],
				doc_json: thirdStep?.snapshots.afterWrite.docJson ?? [],
			},
			firstBlockingBranch: {
				file: "packages/coding-agent/src/extensions/agent-team-loop/pm/runtime-host-adapter.ts",
				function: "ProductionRuntimeHost.readTargetAuthorization",
				predicate: "!snapshot?.ok || snapshot.value.blocked",
				values: {
					budgetSnapshot: k6Result("snapshot"),
					readTargetAuthorization: k6Result("readTargetAuthorization"),
				},
				consequence:
					"RuntimeExecutionController.current returns false; observeToolResult sets binding-drift; afterToolResult returns before finish",
			},
			preFinishPredicate: {
				appendEvent: k6Result("appendEvent"),
				budgetObserve: k6Result("observe"),
				executionObserveToolResult: k6Result("observeToolResult"),
				afterToolResult: k6MethodOutcome("afterToolResult"),
				finish: k6MethodOutcome("finish"),
			},
			terminalReturns: {
				storeAppendExecution: thirdStoreExecution.at(-1) ?? { notAttempted: true },
				storeSaveDisposition: thirdStoreDisposition.at(-1) ?? { notAttempted: true },
				outerAppendExecution: thirdOuterExecution.at(-1) ?? { notAttempted: true },
				outerSaveDisposition: thirdOuterDisposition.at(-1) ?? { notAttempted: true },
			},
			callOrder: thirdBranchCalls,
			allBranchCalls: k6BranchCalls,
		});
		expect(steps).toHaveLength(3);
		const offerIds = steps.map((step) => k4String(step.offer.offer_id));
		const localRefs = steps.map((step) => k4String(step.offer.local_ref));
		const matterRefs = steps.map((step) => {
			const projection = step.projection as Record<string, unknown> | undefined;
			return k4String(projection?.matter_ref);
		});
		expect(
			offerIds.every((item) => item !== undefined),
			JSON.stringify(steps),
		).toBe(true);
		expect(
			localRefs.every((item) => item !== undefined),
			JSON.stringify(steps),
		).toBe(true);
		expect(new Set(offerIds).size, JSON.stringify(offerIds)).toBe(3);
		expect(new Set(localRefs).size, JSON.stringify(localRefs)).toBe(3);
		expect(new Set(matterRefs).size, JSON.stringify(matterRefs)).toBe(3);
		expect(finalSnapshot.stateWrites, JSON.stringify(finalSnapshot)).toBe(3);
		const finalCounts = finalSnapshot.counts;
		expect(finalCounts.selectionCommits, JSON.stringify(finalCounts)).toBe(3);
		expect(finalCounts.reserves, JSON.stringify(finalCounts)).toBe(3);
		expect(finalCounts.observes, JSON.stringify(finalCounts)).toBe(3);
		expect(finalCounts.appends, JSON.stringify(finalCounts)).toBe(3);
		expect(finalCounts.dispositions, JSON.stringify(finalCounts)).toBe(3);
		expect(finalCounts.recordedWithDisposition, JSON.stringify(finalCounts)).toBe(1);
		expect(finalCounts.recordedWithoutDisposition, JSON.stringify(finalCounts)).toBe(0);
		expect(
			finalSnapshot.docJson.filter((entry) => entry.path.endsWith(".execution.json")),
			JSON.stringify(finalSnapshot.docJson),
		).toHaveLength(3);
		expect(
			finalSnapshot.docJson.filter((entry) => entry.path.endsWith(".disposition.json")),
			JSON.stringify(finalSnapshot.docJson),
		).toHaveLength(3);
		expect(finalSnapshot.docJson, JSON.stringify(finalSnapshot.docJson)).toHaveLength(9);
		const budgetRef = j4CardBacktick(f.cardText, "budget_ref");
		const bindings: string[] = [];
		for (const step of steps) {
			const localRef = k4String(step.offer.local_ref);
			const offerId = k4String(step.offer.offer_id);
			const callId = step.snapshots.afterWrite.writeCallIds.at(-1);
			if (localRef === undefined || offerId === undefined || callId === undefined || step.physical === undefined)
				throw new Error(`T06-K4 step ${step.index} missing public identity or physical paths`);
			expect(step.submitDetails.status, JSON.stringify(step.submitDetails)).toBe("planned");
			expect(step.submitDetails.code, JSON.stringify(step.submitDetails)).toBe("written");
			expect(step.submitDetails.local_ref, JSON.stringify(step.submitDetails)).toBe(localRef);
			expect(step.submitDetails.business_completed, JSON.stringify(step.submitDetails)).toBe(false);
			expect(step.snapshots.afterWrite.stateWrites, JSON.stringify(step.snapshots.afterWrite)).toBe(step.index);
			expect(
				step.snapshots.afterWrite.counts.selectionCommits,
				JSON.stringify(step.snapshots.afterWrite.counts),
			).toBe(step.index);
			expect(step.snapshots.afterWrite.counts.appends, JSON.stringify(step.snapshots.afterWrite.counts)).toBe(
				step.index,
			);
			expect(step.snapshots.afterWrite.counts.dispositions, JSON.stringify(step.snapshots.afterWrite.counts)).toBe(
				step.index,
			);
			expect(
				readerTrace.some((event) => event.requestedRef === localRef && event.found),
				JSON.stringify(readerTrace),
			).toBe(true);
			const selection = j4ReadJson(step.physical.selection, `selection ${step.index}`);
			const execution = j4ReadJson(step.physical.execution, `execution ${step.index}`);
			const disposition = j4ReadJson(step.physical.disposition, `disposition ${step.index}`);
			expect(j4NumberField(selection, "schema_version", "selection")).toBe(1);
			expect(j4StringField(selection, "kind", "selection")).toBe("local-selection");
			expect(j4StringField(selection, "origin", "selection")).toBe("local-decision");
			expect(j4StringField(selection, "source", "selection")).toBe("pm");
			expect(j4StringField(selection, "local_ref", "selection")).toBe(localRef);
			expect(j4StringField(selection, "selected_action", "selection")).toBe("continue");
			expect(j4StringField(selection, "selected_basis_id", "selection")).toBe(`basis-k4-${step.index}`);
			expect(j4StringField(selection, "action_state", "selection")).toBe("planned");
			expect(j4StringField(selection, "budget_ref", "selection")).toBe(budgetRef);
			j4FalseField(selection, "business_completed", "selection");
			j4AssertBinding(selection.host_binding, `selection ${step.index}.host_binding`, f.cardSha);
			bindings.push(j4StableJson(selection.host_binding));
			expect(j4NumberField(execution, "schema_version", "execution")).toBe(1);
			expect(j4StringField(execution, "kind", "execution")).toBe("local-execution");
			expect(j4StringField(execution, "origin", "execution")).toBe("local-decision");
			expect(j4StringField(execution, "source", "execution")).toBe("pm");
			expect(j4StringField(execution, "local_ref", "execution")).toBe(localRef);
			expect(j4StringField(execution, "action_ref", "execution")).toBe(callId);
			expect(j4StringField(execution, "result_ref", "execution")).toBe(`tool_result:${callId}`);
			expect(j4StringField(execution, "executor", "execution")).toBe(
				JSON.stringify([`${facts.taskKey}@${facts.dispatchedAt}`, callId]),
			);
			expect(j4StringField(execution, "target_digest", "execution")).toBe(step.afterDigest);
			expect(j4StringField(execution, "observed_effect", "execution")).toBe(
				`byte-manifest:${step.beforeDigest}->${step.afterDigest};business-correctness=unverified`,
			);
			expect(j4StringField(execution, "effect_state", "execution")).toBe("known");
			expect(j4StringField(execution, "verified_by", "execution")).toBe("target-digest-v1@runtime-execution-1");
			expect(j4StringField(execution, "budget_ref", "execution")).toBe(budgetRef);
			expect(j4StableJson(execution.host_binding), JSON.stringify(execution.host_binding)).toBe(
				j4StableJson(selection.host_binding),
			);
			j4AssertBinding(execution.host_binding, `execution ${step.index}.host_binding`, f.cardSha);
			expect(j4NumberField(disposition, "schema_version", "disposition")).toBe(1);
			expect(j4StringField(disposition, "disposition_ref", "disposition")).toBe(`disposition:${callId}`);
			expect(j4StringField(disposition, "feedback_ref", "disposition")).toBe(`feedback:${callId}`);
			expect(j4StringField(disposition, "matter_ref", "disposition")).toBe(
				j4StringField(selection, "matter_ref", "selection"),
			);
			expect(j4StringField(disposition, "kind", "disposition")).toBe("collect-evidence");
			expect(j4StringField(disposition, "owner", "disposition")).toBe(claim);
			expect(j4StableJson(disposition.binding), JSON.stringify(disposition.binding)).toBe(
				j4StableJson(selection.host_binding),
			);
			expect(j4StringField(disposition, "goal_ref", "disposition")).toBe("goal:observed-byte-manifest");
			expect(j4ArrayField(disposition, "gap_refs", "disposition")).toEqual([]);
			expect(j4ArrayField(disposition, "basis_refs", "disposition")).toEqual([callId, `tool_result:${callId}`]);
			const plannedAction = j4AsRecord(disposition.planned_action, `disposition ${step.index}.planned_action`);
			expect(j4StringField(plannedAction, "tool", "disposition.planned_action")).toBe("write");
			expect(j4StringField(plannedAction, "scope_ref", "disposition.planned_action")).toBe(
				"host-complete-write-face",
			);
			expect(plannedAction.read_only).toBe(false);
			expect(j4StringField(disposition, "expected_result", "disposition")).toBe("target byte manifest");
			expect(j4StringField(disposition, "result_consumer", "disposition")).toBe("owning-pm:review");
			expect(j4StringField(disposition, "budget_ref", "disposition")).toBe(budgetRef);
			expect(j4StringField(disposition, "status", "disposition")).toBe("observed");
		}
		expect(new Set(bindings).size, JSON.stringify(bindings)).toBe(1);
		expect(sha256(fs.readFileSync(path.join(f.doc, keyName, "tasks", "T-01.md"), "utf8"))).toBe(f.cardSha);
		expect(replay.replaySubmit.status, JSON.stringify(replay.replaySubmit)).toBe("refused");
		expect(replay.replaySubmit.business_completed, JSON.stringify(replay.replaySubmit)).toBe(false);
		expect(replay.replaySubmit.selection_written, JSON.stringify(replay.replaySubmit)).toBe(false);
		expect(finalSnapshot.stateWrites, JSON.stringify(finalSnapshot)).toBe(3);
		expect(
			finalSnapshot.docJson,
			JSON.stringify({ before: replayBefore.docJson, after: finalSnapshot.docJson }),
		).toEqual(replayBefore.docJson);
		expect(
			finalSnapshot.artifacts.map((item) => `${item.path}:${item.sha256}`),
			JSON.stringify(finalSnapshot.artifacts),
		).toEqual(replayBefore.artifacts.map((item) => `${item.path}:${item.sha256}`));
	});

	// ── T06-K7 append-only: genuine exhausted-action terminal refusal matrix ────
	// Each cell builds ONE real production composition (composePm + harness/faux),
	// drives three explicitly authorized public actions to genuine budget
	// exhaustion with an authentic terminal proof, then injects ONE live-fact
	// mutation through an observable delegating wrapper on the REAL
	// ProductionRuntimeHost.budgetSnapshotFor BEFORE the last awaited callback
	// returns. The real store/verifier still run. No private map seed, no fake
	// grant/proof/success store, no clock/budget reset, no counter proof, no
	// stubbed verifier, no cross-run stitching.
	type K7Input = Record<string, unknown>;
	type K7Mutate = (input: K7Input) => void;
	interface K7Cell {
		id: string;
		mutate?: K7Mutate;
		finalAwaitOnly?: boolean;
		fourth?: boolean;
		replay?: boolean;
		mutated: boolean;
	}
	const k7Foreign = "T06-K7-FOREIGN";
	const k7Clone = (value: unknown): unknown => {
		try {
			return JSON.parse(JSON.stringify(value)) as unknown;
		} catch {
			return { unserializable: String(value) };
		}
	};
	const k7With = (base: unknown, key: string, value: unknown): Record<string, unknown> => ({
		...((base ?? {}) as Record<string, unknown>),
		[key]: value,
	});
	const k7Cells: K7Cell[] = [
		{ id: "healthy-control", mutated: false },
		{
			id: "deadline-crossing",
			mutated: true,
			mutate: (i) => {
				i.nowMs = Date.parse(String((i.cardBudget as Record<string, unknown>).deadline)) + 1;
			},
		},
		{
			id: "identity-claim-drift",
			mutated: true,
			mutate: (i) => {
				i.authorization = k7With(i.authorization, "owningPmClaim", k7Foreign);
			},
		},
		{
			id: "authorization-unit-drift",
			mutated: true,
			mutate: (i) => {
				i.authorization = k7With(i.authorization, "authorizationUnit", k7Foreign);
			},
		},
		{
			id: "source-drift",
			mutated: true,
			mutate: (i) => {
				i.request = k7With(i.request, "source", "worker-local");
			},
		},
		{
			id: "local-ref-wrong",
			mutated: true,
			mutate: (i) => {
				i.request = k7With(i.request, "ref", "lref:T06-K7-foreign");
			},
		},
		{
			id: "task-key-drift",
			mutated: true,
			mutate: (i) => {
				i.request = k7With(i.request, "task_key", "foreign-task");
			},
		},
		{
			id: "final-await-identity-drift",
			mutated: true,
			finalAwaitOnly: true,
			mutate: (i) => {
				i.authorization = k7With(i.authorization, "owningPmClaim", k7Foreign);
			},
		},
		{ id: "zero-budget-fourth", mutated: false, fourth: true },
		{ id: "repeated-result", mutated: false, replay: true },
	];
	// Cells the allowed three faces cannot prove dynamically WITHOUT seeding a
	// private map, faking a grant/proof/store, resetting clock/budget or replacing
	// the verifier. Reported explicitly MISSING, never inferred from static guards.
	const k7Missing: string[] = [
		"stop-signal-injection",
		"authority-revocation-injection",
		"claim/card/run identity drift (external file rewrite before last await)",
		"path redirect / junction before last await",
		"action/result/local_ref/disposition exact-correlation swap",
		"zero-budget new reservation (no per-action unit in allowed faces)",
		"unrelated terminal write",
	];

	function k7Install(
		host: ProductionRuntimeHost,
		cell: K7Cell,
	): { armed: boolean; qualifying: number; fired: number; guardResults: unknown[] } {
		const rec = host as unknown as Record<string, unknown>;
		const original = rec.budgetSnapshotFor as (input: K7Input) => unknown;
		if (typeof original !== "function") throw new Error("T06-K7 real budgetSnapshotFor missing");
		const state = { armed: false, qualifying: 0, fired: 0, guardResults: [] as unknown[] };
		rec.budgetSnapshotFor = (input: K7Input): unknown => {
			const req = (input.request ?? {}) as Record<string, unknown>;
			const kind = req.write_kind;
			const qualifying = state.armed && (kind === "execution" || kind === "disposition");
			let apply = false;
			if (qualifying && cell.mutate) {
				state.qualifying += 1;
				if (!cell.finalAwaitOnly || state.qualifying >= 2) apply = true;
			}
			if (apply) {
				state.fired += 1;
				cell.mutate?.(input);
			}
			const result = Reflect.apply(original, host, [input]) as Record<string, unknown>;
			if (qualifying)
				state.guardResults.push(
					k7Clone({
						applied: apply,
						ok: result?.ok ?? null,
						gaps: result?.gaps ?? null,
						reason: result?.reason ?? null,
					}),
				);
			return result;
		};
		return state;
	}

	async function k7Drive(
		h: Harness,
		f: K4Fixture,
		facts: RuntimeHostDispatchObservation,
		state: { armed: boolean } | undefined,
	): Promise<{ thirdLocalRef: string; firstOfferId: string }> {
		let thirdLocalRef = "";
		let firstOfferId = "";
		for (let index = 1; index <= 3; index += 1) {
			const prior = k4DocArtifacts(f.doc);
			const material = k4Material(f, facts, index, prior);
			const preparation = k4Preparation(f, material, index, prior);
			const trigger = `k7-action-${index}`;
			await promptTool(
				h,
				ASK_DECISION_TOOL,
				{
					dp: "dp-auto",
					trigger,
					key: keyName,
					task_key: taskKey,
					note: `T06-K7 authorized ordered effect ${index}`,
					material,
					preparation,
				},
				`prepare ${trigger}`,
			);
			const offer = k4OfferOf(k4Details(h, ASK_DECISION_TOOL));
			const localRef = k4String(offer.local_ref) ?? "";
			const offerId = k4String(offer.offer_id) ?? "";
			if (index === 1) firstOfferId = offerId;
			if (index === 3) thirdLocalRef = localRef;
			await promptTool(
				h,
				SUBMIT_DECISION_HANDOFF_TOOL,
				{ offer_id: offerId, choice: "continue", basis_id: `basis-k4-${index}` },
				`commit ${trigger}`,
			);
			if (state !== undefined) state.armed = index === 3;
			await promptTool(h, "write", { path: "src/a.txt", content: `k7-${index}` }, `action ${index}`);
		}
		if (state !== undefined) state.armed = false;
		return { thirdLocalRef, firstOfferId };
	}

	for (const cell of k7Cells) {
		it(`T06-K7-MATRIX ${cell.id}`, async () => {
			const f = k4AuthorizedFixture();
			const { h, composition, state, facts } = await composePm(f);
			const host = composition.host;
			const reader: K4Reader = (requestedRef) =>
				composition.submitHandle.hostExpectedFor(requestedRef) as unknown as ReturnType<K4Reader>;
			host.bindExpectedFor(reader);
			const k5Calls = k5ObserveTerminal(host, `k7-${cell.id}`);
			const mut = k7Install(host, cell);
			let replayBefore: K4Artifact[] = [];
			let fourthSubmit: Record<string, unknown> = {};
			let replaySubmit: Record<string, unknown> = {};
			const { thirdLocalRef, firstOfferId } = await k7Drive(h, f, facts, mut);
			if (cell.fourth) {
				replayBefore = k4DocArtifacts(f.doc);
				const prior = k4DocArtifacts(f.doc);
				const material = k4Material(f, facts, 3, prior);
				const preparation = k4Preparation(f, material, 3, prior);
				await promptTool(
					h,
					ASK_DECISION_TOOL,
					{
						dp: "dp-auto",
						trigger: "k7-fourth",
						key: keyName,
						task_key: taskKey,
						note: "T06-K7 zero-budget fourth",
						material,
						preparation,
					},
					"prepare fourth",
				);
				const offer = k4OfferOf(k4Details(h, ASK_DECISION_TOOL));
				await promptTool(
					h,
					SUBMIT_DECISION_HANDOFF_TOOL,
					{ offer_id: k4String(offer.offer_id) ?? "", choice: "continue", basis_id: "basis-k4-3" },
					"commit fourth",
				);
				fourthSubmit = k4Details(h, SUBMIT_DECISION_HANDOFF_TOOL);
				await promptTool(h, "write", { path: "src/a.txt", content: "k7-fourth" }, "fourth body");
			}
			if (cell.replay) {
				replayBefore = k4DocArtifacts(f.doc);
				await promptTool(
					h,
					SUBMIT_DECISION_HANDOFF_TOOL,
					{ offer_id: firstOfferId, choice: "continue", basis_id: "basis-k4-1" },
					"replay old offer",
				);
				replaySubmit = k4Details(h, SUBMIT_DECISION_HANDOFF_TOOL);
				await promptTool(
					h,
					"write",
					{ path: "src/a.txt", content: "k7-old-offer-replay" },
					"old offer replay write",
				);
			}
			const artifacts = k4DocArtifacts(f.doc);
			const docJson = artifacts.map((a) => a.path);
			const execFiles = docJson.filter((p) => p.endsWith(".execution.json")).length;
			const dispFiles = docJson.filter((p) => p.endsWith(".disposition.json")).length;
			const selFiles = docJson.filter(
				(p) => p.endsWith(".json") && !p.endsWith(".execution.json") && !p.endsWith(".disposition.json"),
			).length;
			const counts = host.countsSnapshot();
			const thirdStoreExec = k5Calls.filter(
				(c) =>
					c.layer === "local-selection-store" &&
					c.method === "appendExecution" &&
					j4StableJson(c.args).includes(thirdLocalRef),
			);
			const thirdStoreDisp = k5Calls.filter(
				(c) => c.layer === "local-selection-store" && c.method === "saveDisposition",
			);
			const row = {
				cell: cell.id,
				mutation_stage: cell.finalAwaitOnly
					? "final-await (2nd budgetSnapshotFor)"
					: cell.mutated
						? "budgetSnapshotFor execution/disposition read"
						: "none",
				mutated: cell.mutated,
				mut_fired: mut.fired,
				guard_results: mut.guardResults,
				state_writes: state.writes,
				selection_files: selFiles,
				execution_files: execFiles,
				disposition_files: dispFiles,
				counts: {
					appends: counts.appends,
					dispositions: counts.dispositions,
					selectionCommits: counts.selectionCommits,
				},
				third_store_exec_calls: thirdStoreExec.map((c) => k7Clone(c.result)),
				third_store_disp_calls: thirdStoreDisp.map((c) => k7Clone(c.result)),
				fourth_submit: cell.fourth ? fourthSubmit : null,
				replay_submit: cell.replay ? replaySubmit : null,
				replay_byte_invariance:
					cell.replay || cell.fourth
						? JSON.stringify(replayBefore.map((a) => `${a.path}:${a.sha256}`)) ===
							JSON.stringify(artifacts.map((a) => `${a.path}:${a.sha256}`))
						: null,
			};
			// Diagnostics BEFORE any failing assertion so an incomplete run is visible.
			k4Emit("T06-K7-MATRIX-ROW", row);
			// Universal safety: exactly the three authorized business effects, never a
			// fourth body and never a replayed already-performed body.
			expect(state.writes, `cell=${cell.id} ${JSON.stringify(row)}`).toBe(3);
			if (cell.mutated) {
				expect(mut.fired, `cell=${cell.id} guard never reached`).toBeGreaterThan(0);
				// Real store refusal: the exhausted third action's terminal records
				// were NOT archived (healthy control archives all three).
				expect(execFiles, `cell=${cell.id} ${JSON.stringify(row)}`).toBeLessThan(3);
				expect(dispFiles, `cell=${cell.id} ${JSON.stringify(row)}`).toBeLessThan(3);
			} else {
				// Healthy control genuinely archives three execution + three disposition.
				expect(execFiles, `cell=${cell.id} ${JSON.stringify(row)}`).toBe(3);
				expect(dispFiles, `cell=${cell.id} ${JSON.stringify(row)}`).toBe(3);
			}
			if (cell.fourth) expect(fourthSubmit.status, `cell=${cell.id} ${JSON.stringify(row)}`).not.toBe("planned");
			if (cell.replay) {
				expect(replaySubmit.status, `cell=${cell.id} ${JSON.stringify(row)}`).toBe("refused");
				expect(row.replay_byte_invariance, `cell=${cell.id} ${JSON.stringify(row)}`).toBe(true);
			}
		});
	}

	it("T06-K7-MATRIX-MISSING declares unproven cells", () => {
		k4Emit("T06-K7-MATRIX-MISSING", { missing: k7Missing });
		expect(k7Missing.length).toBeGreaterThan(0);
	});

	// ── T06-K8 append-only: concrete final-await, real-fact drift ─────────────
	// R1 fix for E249 QG 11da505d. Unlike the K7 private-parameter matrices, each
	// K8 cell delegates the REAL LocalSelectionHostAdapter.readTrustedContext and
	// .verifyExecution, preserves the real proof and the real return value, and
	// injects exactly ONE isolated temp-project authorization fact (card bytes
	// appended with the pin unchanged, or the real _index.parallel owner) at a
	// PROVABLE last-await boundary of the genuinely exhausted third action. The
	// real final trusted read / synchronous authoritative-row recheck then
	// refuses with a real, action/run/local_ref-correlated store code. No private
	// map seed, no forged proof/grant/success store, no clock/budget reset, no
	// stubbed verifier, no cross-run stitching, no production source edit.
	type K8Fact = "none" | "card-byte" | "index-owner";
	type K8InjectAt = "verifier-await" | "final-trusted-callback";
	interface K8Cell {
		id: string;
		fact: K8Fact;
		injectAt: K8InjectAt;
		mutated: boolean;
	}
	interface K8Event {
		seq: number;
		observed_at: string;
		boundary: string;
		event: string;
		write_kind?: string;
		ref?: string;
		action_ref?: string;
		proof_present?: boolean;
		result_code?: unknown;
		note?: string;
	}
	interface K8FactRecord {
		fact: K8Fact;
		path: string;
		before_len: number;
		after_len: number;
		before_sha256: string;
		after_sha256: string;
		pin_changed: boolean;
	}
	interface K8Snapshot {
		artifactKeys: string[];
		artifacts: K4Artifact[];
		targetDigest: string;
		ledgerLen: number;
		writeCallIds: string[];
		stateWrites: number;
	}
	interface K8Observe {
		events: K8Event[];
		factRecord: K8FactRecord | null;
		fired: number;
		toolEvents: unknown[];
		arming: { armed: boolean };
	}

	function k8Snapshot(f: K4Fixture, h: Harness, state: ToolState): K8Snapshot {
		const artifacts = k4DocArtifacts(f.doc);
		const targets = j4TargetManifest(f.root, j4WriteFace(f));
		return {
			artifactKeys: artifacts.map((a) => `${a.path}:${a.bytes}:${a.sha256}`),
			artifacts,
			targetDigest: j4ManifestDigest(targets),
			ledgerLen: k4Ledger(h).length,
			writeCallIds: k4WriteCallIds(h),
			stateWrites: state.writes,
		};
	}

	// ONE real temp-project authorization fact. The card SHA pin in task.md and
	// the run/index files are NEVER rewritten to "authorize" the drift; only the
	// single fact named by `fact` changes, inside this disposable fixture.
	function k8MutateFact(f: K4Fixture, fact: K8Fact): K8FactRecord | null {
		if (fact === "none") return null;
		const target =
			fact === "card-byte" ? path.join(f.doc, keyName, "tasks", "T-01.md") : path.join(f.doc, "_index.parallel");
		const before = fs.readFileSync(target);
		const beforeSha = crypto.createHash("sha256").update(before).digest("hex");
		if (fact === "card-byte") fs.appendFileSync(target, " ");
		else fs.writeFileSync(target, before.toString("utf8").replace(claim, `${claim}-k8-foreign`));
		const after = fs.readFileSync(target);
		const afterSha = crypto.createHash("sha256").update(after).digest("hex");
		return {
			fact,
			path: path.relative(f.doc, target),
			before_len: before.length,
			after_len: after.length,
			before_sha256: beforeSha,
			after_sha256: afterSha,
			pin_changed: false,
		};
	}

	// Delegating observers on the REAL composed adapter. Every original method is
	// invoked with the same owner and arguments and its real result is returned
	// unchanged. Only the one armed third-action boundary applies a single real
	// fact change; the ordered events prove which await is the last one.
	function k8Install(host: ProductionRuntimeHost, f: K4Fixture, cell: K8Cell): K8Observe {
		const hidden = host as unknown as { controllers?: Record<string, unknown> };
		const controllers = hidden.controllers;
		if (controllers === undefined) throw new Error("T06-K8 requires the real composed production controllers");
		const store = controllers.store as Record<string, unknown> & { adapter?: Record<string, unknown> };
		const adapter = store?.adapter;
		if (
			adapter === undefined ||
			typeof adapter.readTrustedContext !== "function" ||
			typeof adapter.verifyExecution !== "function"
		)
			throw new Error("T06-K8 requires the real LocalSelectionHostAdapter trusted callbacks");
		const observe: K8Observe = {
			events: [],
			factRecord: null,
			fired: 0,
			toolEvents: [],
			arming: { armed: false },
		};
		let seq = 0;
		let armedExecReads = 0;
		const record = (e: Omit<K8Event, "seq" | "observed_at">): void => {
			seq += 1;
			observe.events.push({ seq, observed_at: new Date().toISOString(), ...e });
		};
		const originalRead = adapter.readTrustedContext as (request: Record<string, unknown>) => Promise<unknown>;
		adapter.readTrustedContext = async (request: Record<string, unknown>): Promise<unknown> => {
			const req = (request ?? {}) as Record<string, unknown>;
			const writeKind = typeof req.write_kind === "string" ? req.write_kind : "";
			const ref = typeof req.ref === "string" ? req.ref : "";
			if (observe.arming.armed && writeKind === "execution") armedExecReads += 1;
			record({
				boundary: "LocalSelectionHostAdapter.readTrustedContext",
				event: "enter",
				write_kind: writeKind,
				ref,
			});
			const result = (await Reflect.apply(originalRead, adapter, [request])) as unknown;
			const injectHere =
				cell.mutated &&
				cell.injectAt === "final-trusted-callback" &&
				observe.arming.armed &&
				observe.fired === 0 &&
				writeKind === "execution" &&
				armedExecReads === 2;
			let note = "";
			if (injectHere) {
				observe.factRecord = k8MutateFact(f, cell.fact);
				observe.fired += 1;
				note =
					"ONE real temp-project authorization fact changed after the last trusted callback read, before it returns";
			}
			record({
				boundary: "LocalSelectionHostAdapter.readTrustedContext",
				event: "return",
				write_kind: writeKind,
				ref,
				result_code: result === undefined ? "trusted-context-undefined" : "trusted-context-present",
				note,
			});
			return result;
		};
		const originalVerify = adapter.verifyExecution as (request: Record<string, unknown>) => Promise<unknown>;
		adapter.verifyExecution = async (request: Record<string, unknown>): Promise<unknown> => {
			const req = (request ?? {}) as Record<string, unknown>;
			const actionRef = typeof req.action_ref === "string" ? req.action_ref : "";
			const localRef = typeof req.local_ref === "string" ? req.local_ref : "";
			const proof = (await Reflect.apply(originalVerify, adapter, [request])) as unknown;
			const injectHere =
				cell.mutated && cell.injectAt === "verifier-await" && observe.arming.armed && observe.fired === 0;
			let note = "";
			if (injectHere) {
				observe.factRecord = k8MutateFact(f, cell.fact);
				observe.fired += 1;
				note =
					"ONE real temp-project authorization fact changed after the real proof, before the verifier await returns; proof preserved unchanged";
			}
			record({
				boundary: "LocalSelectionHostAdapter.verifyExecution",
				event: "return",
				ref: localRef,
				action_ref: actionRef,
				proof_present: proof !== undefined && proof !== null,
				note,
			});
			return proof;
		};
		const afterKey = "afterToolResult";
		const hostRec = host as unknown as Record<string, unknown>;
		const originalAfter = hostRec[afterKey] as (event: unknown) => Promise<void>;
		hostRec[afterKey] = async (event: unknown): Promise<void> => {
			observe.toolEvents.push(event);
			await Reflect.apply(originalAfter, host, [event]);
		};
		return observe;
	}

	async function k8Drive(
		h: Harness,
		f: K4Fixture,
		state: ToolState,
		facts: RuntimeHostDispatchObservation,
		observe: K8Observe,
	): Promise<{ firstOfferId: string; thirdLocalRef: string; preThird: K8Snapshot; post: K8Snapshot }> {
		let firstOfferId = "";
		let thirdLocalRef = "";
		let preThird = k8Snapshot(f, h, state);
		for (let index = 1; index <= 3; index += 1) {
			const prior = k4DocArtifacts(f.doc);
			const material = k4Material(f, facts, index, prior);
			const preparation = k4Preparation(f, material, index, prior);
			const trigger = `k8-action-${index}`;
			await promptTool(
				h,
				ASK_DECISION_TOOL,
				{
					dp: "dp-auto",
					trigger,
					key: keyName,
					task_key: taskKey,
					note: `T06-K8 authorized ordered effect ${index}`,
					material,
					preparation,
				},
				`prepare ${trigger}`,
			);
			const offer = k4OfferOf(k4Details(h, ASK_DECISION_TOOL));
			const offerId = k4String(offer.offer_id) ?? "";
			const localRef = k4String(offer.local_ref) ?? "";
			if (index === 1) firstOfferId = offerId;
			if (index === 3) thirdLocalRef = localRef;
			await promptTool(
				h,
				SUBMIT_DECISION_HANDOFF_TOOL,
				{ offer_id: offerId, choice: "continue", basis_id: `basis-k4-${index}` },
				`commit ${trigger}`,
			);
			// Snapshot the healthy archive immediately before the third write:
			// 3 selections + the first two complete pairs. This is the byte-exact
			// baseline the reject case must leave untouched.
			if (index === 3) preThird = k8Snapshot(f, h, state);
			observe.arming.armed = index === 3;
			await promptTool(h, "write", { path: "src/a.txt", content: `k8-${index}` }, `action ${index}`);
			observe.arming.armed = false;
		}
		const post = k8Snapshot(f, h, state);
		return { firstOfferId, thirdLocalRef, preThird, post };
	}

	// Definition 1 of 2: real public composition, real verifier, one real fact
	// drift at a provable last await; healthy 3/3/3 control under identical code.
	const k8LastAwaitCells: K8Cell[] = [
		{ id: "healthy-control", fact: "none", injectAt: "verifier-await", mutated: false },
		{ id: "card-byte@verifier-await", fact: "card-byte", injectAt: "verifier-await", mutated: true },
		{ id: "index-owner@verifier-await", fact: "index-owner", injectAt: "verifier-await", mutated: true },
		{
			id: "index-owner@final-trusted-callback",
			fact: "index-owner",
			injectAt: "final-trusted-callback",
			mutated: true,
		},
	];

	for (const cell of k8LastAwaitCells) {
		it(`T06-K8-CONTRAST ${cell.id}`, async () => {
			const f = k4AuthorizedFixture();
			const { h, composition, state, facts } = await composePm(f);
			const host = composition.host;
			const reader: K4Reader = (requestedRef) =>
				composition.submitHandle.hostExpectedFor(requestedRef) as unknown as ReturnType<K4Reader>;
			host.bindExpectedFor(reader);
			const k5Calls = k5ObserveTerminal(host, `k8-${cell.id}`);
			const observe = k8Install(host, f, cell);
			const { thirdLocalRef, preThird, post } = await k8Drive(h, f, state, facts, observe);
			const thirdCallId = post.writeCallIds.at(-1) ?? "";
			const execFiles = post.artifacts.filter((a) => a.path.endsWith(".execution.json"));
			const dispFiles = post.artifacts.filter((a) => a.path.endsWith(".disposition.json"));
			const thirdExec = execFiles.filter((a) => a.raw.includes(thirdLocalRef));
			const thirdDisp = dispFiles.filter((a) => a.raw.includes(thirdCallId));
			const storeExecCodes = k5Calls
				.filter(
					(c) =>
						c.layer === "local-selection-store" &&
						c.method === "appendExecution" &&
						j4StableJson(c.args).includes(thirdLocalRef),
				)
				.map((c) => (c.result as Record<string, unknown>)?.code ?? null);
			const storeDispCodes = k5Calls
				.filter(
					(c) =>
						c.layer === "local-selection-store" &&
						c.method === "saveDisposition" &&
						j4StableJson(c.args).includes(thirdCallId),
				)
				.map((c) => (c.result as Record<string, unknown>)?.code ?? null);
			const proofEvents = observe.events.filter((e) => e.boundary === "LocalSelectionHostAdapter.verifyExecution");
			const readEvents = observe.events.filter((e) => e.boundary === "LocalSelectionHostAdapter.readTrustedContext");
			const unchangedFirstPairs = preThird.artifactKeys.every((k) => post.artifactKeys.includes(k));
			const newKeys = post.artifactKeys.filter((k) => !preThird.artifactKeys.includes(k));
			const row = {
				cell: cell.id,
				fact: cell.fact,
				inject_at: cell.injectAt,
				mutated: cell.mutated,
				mut_fired: observe.fired,
				fact_record: observe.factRecord,
				third_local_ref: thirdLocalRef,
				third_call_id: thirdCallId,
				state_writes: post.stateWrites,
				pre_third_artifact_keys: preThird.artifactKeys,
				post_artifact_keys: post.artifactKeys,
				new_artifact_keys: newKeys,
				unchanged_first_pairs: unchangedFirstPairs,
				pre_third_target_digest: preThird.targetDigest,
				post_target_digest: post.targetDigest,
				third_exec_files: thirdExec.map((a) => a.path),
				third_disp_files: thirdDisp.map((a) => a.path),
				exec_file_count: execFiles.length,
				disp_file_count: dispFiles.length,
				store_exec_codes: storeExecCodes,
				store_disp_codes: storeDispCodes,
				proof_present_per_verifier_call: proofEvents.map((e) => e.proof_present),
				last_await_read_tail: readEvents.slice(-6),
				ordered_events: observe.events,
			};
			// Ordered, real events FIRST: specific awaits, real proof source, the
			// real store refusal code correlated to action/run/local_ref, and raw
			// byte keys. Nothing here is a private budgetSnapshotFor projection.
			k4Emit("T06-K8-CONTRAST-ROW", row);
			expect(state.writes, JSON.stringify(row)).toBe(3);
			expect(unchangedFirstPairs, JSON.stringify(row)).toBe(true);
			// The third business effect genuinely happened in BOTH cases: real
			// exhaustion is not simulated by freezing the write or its digest.
			expect(post.targetDigest, JSON.stringify(row)).not.toBe(preThird.targetDigest);
			if (!cell.mutated) {
				expect(observe.fired, JSON.stringify(row)).toBe(0);
				expect(execFiles.length, JSON.stringify(row)).toBe(3);
				expect(dispFiles.length, JSON.stringify(row)).toBe(3);
				expect(thirdExec.length, JSON.stringify(row)).toBe(1);
				expect(thirdDisp.length, JSON.stringify(row)).toBe(1);
			} else {
				expect(observe.fired, JSON.stringify(row)).toBe(1);
				expect(observe.factRecord, JSON.stringify(row)).not.toBeNull();
				expect(observe.factRecord?.after_sha256, JSON.stringify(row)).not.toBe(observe.factRecord?.before_sha256);
				// Rejected third target: NO new execution/disposition bytes, NO new
				// archive bytes at all, old two pairs byte-identical.
				expect(thirdExec.length, JSON.stringify(row)).toBe(0);
				expect(thirdDisp.length, JSON.stringify(row)).toBe(0);
				expect(execFiles.length, JSON.stringify(row)).toBe(2);
				expect(dispFiles.length, JSON.stringify(row)).toBe(2);
				expect(newKeys, JSON.stringify(row)).toEqual([]);
				// The real verifier still produced and returned its genuine proof;
				// the real store refused at the last boundary with a real code.
				expect(
					proofEvents.some((e) => e.proof_present === true),
					JSON.stringify(row),
				).toBe(true);
				const realCodes = [...storeExecCodes, ...storeDispCodes];
				expect(
					realCodes.some(
						(c) => c === "trusted-context-refused" || c === "binding-foreign" || c === "binding-stale-owner",
					),
					JSON.stringify(row),
				).toBe(true);
			}
		});
	}

	// Definition 2 of 2: reuse the healthy 3/3/3 run and re-deliver the SAME real
	// tool-result event, re-submit the OLD OFFER, or attempt a zero-budget fourth
	// body. Each cell keeps the healthy control and asserts real byte invariance.
	interface K8BoundaryCell {
		id: string;
		mode: "repeated-tool-result" | "old-offer-replay" | "zero-budget-fourth";
	}
	const k8BoundaryCells: K8BoundaryCell[] = [
		{ id: "repeated-tool-result", mode: "repeated-tool-result" },
		{ id: "old-offer-replay", mode: "old-offer-replay" },
		{ id: "zero-budget-fourth", mode: "zero-budget-fourth" },
	];
	// Accurate NOT-COVERED declaration: these are recorded as data, never asserted
	// as a passing test. Each names the concrete production API / contract / minimal
	// seam required; "legacy suite green" is not coverage.
	const k8Uncovered: { cell: string; api_or_contract: string; minimal_seam: string }[] = [
		{
			cell: "stop-signal / authority-revocation before last await",
			api_or_contract:
				"local-selection-store.ts hostStopBlocks(hostFacts, role); runtime-host-adapter.ts readRuntimeAuthority builds stopSignals only from a worker-local run.json status (STOP_RUN_STATUSES). The PM path (source='pm') has run===undefined, so stopSignals is empty and there is no real file-backed host stop to flip at the PM last await.",
			minimal_seam:
				"A real PM stop authority fact would need a file the PM readRuntimeAuthority consults (e.g. a stop record that hostStopBlocks reads). None exists in the frozen source; constructing one requires a production source edit. No legal test-only seam in the allowed face.",
		},
		{
			cell: "claim/card/run source drift for worker-local",
			api_or_contract:
				"runtime-host-adapter.ts readRuntimeAuthority() worker-local branch (lines ~485-515) re-reads workers/<taskKey>/run.json + task.md and pins card_sha256/started_at.",
			minimal_seam:
				"Requires a worker-local composition (PI_WORKER_TASK + run.json + envelope), not the PM k4AuthorizedFixture used here; a distinct composePm worker path is not exposed by the frozen public test surface in this append region.",
		},
		{
			cell: "path redirect / junction before last await",
			api_or_contract:
				"local-selection-store.ts finalRecheck() pathSafety(root, base, file) runs after the LAST await; runtime-host-adapter.ts safeFile()/fs.realpathSync containment.",
			minimal_seam:
				"A real directory rename + OS junction of a temp subdir made inside the last trusted callback would exercise it, but junction/symlink creation is platform/permission dependent on this Windows host and would mutate a path the harness also reads; no hermetic seam proved here.",
		},
		{
			cell: "action/result/local_ref/disposition exact-correlation swap",
			api_or_contract:
				"local-selection-store.ts originalVerdict() / terminalExecutionMatches() / crossCheckExpected() bind selection to execution by local_ref/source/key/task/run.",
			minimal_seam:
				"A real archive-file rewrite of an existing selection's local_ref at the last await would be rejected by inspectExisting/classifyExisting before correlation; a genuine in-flight correlation swap needs a second real dispatch whose host-observed action_ref is substituted, which needs a production seam.",
		},
		{
			cell: "zero-budget new selection / new reservation / unrelated terminal write",
			api_or_contract:
				"ProductionRuntimeHost.reserveChild() (runtime-host-adapter.ts ~1341) and LocalSelectionStore.commitSelection/saveDisposition; finite card budget blocks step four is the historical red at test line ~492.",
			minimal_seam:
				"A genuine new reservation must call the real reserveChild/budget API with a zero-budget unit and prove no grant; the fourth-body cell below proves a fourth submit is non-planned, but a separate real reserveChild call and an unrelated-terminal write are not constructed here.",
		},
		{
			cell: "deadline crossing via the real clock at the last await",
			api_or_contract:
				"local-selection-store.ts verifyTrusted() nowMs = this.clock(); runtime-host-adapter.ts createRuntimeHostAdapter() clock = config.clock ?? (() => Date.now()); both captured at construction.",
			minimal_seam:
				"No post-composition clock setter exists on the frozen public host/store. The K7 deadline-crossing cell only mutates the private budgetSnapshotFor input.nowMs (a parameter projection), not the real clock. Monotonic crossing would need a constructor-time injected clock or real time to pass the fixture 30m deadline; no legal seam in the allowed face.",
		},
	];

	for (const cell of k8BoundaryCells) {
		it(`T06-K8-BOUNDARY ${cell.id}`, async () => {
			const f = k4AuthorizedFixture();
			const { h, composition, state, facts } = await composePm(f);
			const host = composition.host;
			const reader: K4Reader = (requestedRef) =>
				composition.submitHandle.hostExpectedFor(requestedRef) as unknown as ReturnType<K4Reader>;
			host.bindExpectedFor(reader);
			const observe = k8Install(host, f, {
				id: cell.id,
				fact: "none",
				injectAt: "verifier-await",
				mutated: false,
			});
			const { firstOfferId, thirdLocalRef, post } = await k8Drive(h, f, state, facts, observe);
			const thirdCallId = post.writeCallIds.at(-1) ?? "";
			// Healthy control: genuine 3/3/3 before any repeated delivery.
			const baseline = k4DocArtifacts(f.doc);
			const baselineKeys = baseline.map((a) => `${a.path}:${a.bytes}:${a.sha256}`);
			expect(baseline.filter((a) => a.path.endsWith(".execution.json")).length).toBe(3);
			expect(baseline.filter((a) => a.path.endsWith(".disposition.json")).length).toBe(3);
			let extra: Record<string, unknown> = {};
			if (cell.mode === "repeated-tool-result") {
				// Capture the SAME real tool-result event delivered for the third
				// write, then re-deliver that exact event through the real public
				// host.afterToolResult. It must not write or execute anything new.
				const captured = observe.toolEvents.find((e) => {
					const rec = e as Record<string, unknown> | null;
					return rec !== null && typeof rec === "object" && rec.toolCallId === thirdCallId;
				});
				expect(captured, JSON.stringify({ thirdCallId, toolEvents: observe.toolEvents.length })).toBeDefined();
				const beforeStateWrites = state.writes;
				const after = (host as unknown as Record<string, unknown>).afterToolResult as (
					event: unknown,
				) => Promise<void>;
				await after.call(host, captured);
				extra = {
					re_delivered_tool_call_id: thirdCallId,
					captured_event_present: captured !== undefined,
					state_writes_before: beforeStateWrites,
					state_writes_after: state.writes,
					third_local_ref: thirdLocalRef,
				};
			} else if (cell.mode === "old-offer-replay") {
				await promptTool(
					h,
					SUBMIT_DECISION_HANDOFF_TOOL,
					{ offer_id: firstOfferId, choice: "continue", basis_id: "basis-k4-1" },
					"old offer replay",
				);
				extra = { replay_submit: k4Details(h, SUBMIT_DECISION_HANDOFF_TOOL), third_local_ref: thirdLocalRef };
			} else {
				const prior = k4DocArtifacts(f.doc);
				const material = k4Material(f, facts, 3, prior);
				const preparation = k4Preparation(f, material, 3, prior);
				await promptTool(
					h,
					ASK_DECISION_TOOL,
					{
						dp: "dp-auto",
						trigger: "k8-fourth",
						key: keyName,
						task_key: taskKey,
						note: "T06-K8 zero-budget fourth",
						material,
						preparation,
					},
					"prepare fourth",
				);
				const offer = k4OfferOf(k4Details(h, ASK_DECISION_TOOL));
				await promptTool(
					h,
					SUBMIT_DECISION_HANDOFF_TOOL,
					{ offer_id: k4String(offer.offer_id) ?? "", choice: "continue", basis_id: "basis-k4-3" },
					"commit fourth",
				);
				extra = { fourth_submit: k4Details(h, SUBMIT_DECISION_HANDOFF_TOOL) };
			}
			const afterArtifacts = k4DocArtifacts(f.doc);
			const afterKeys = afterArtifacts.map((a) => `${a.path}:${a.bytes}:${a.sha256}`);
			const added = afterArtifacts.filter((a) => !baselineKeys.includes(`${a.path}:${a.bytes}:${a.sha256}`));
			const dropAudit =
				cell.mode === "zero-budget-fourth"
					? added.filter(
							(a) =>
								a.path.startsWith(path.join("_autopilot", "dp-blocked") + path.sep) &&
								j4IsRecord(a.body) &&
								a.body.dp === "dp-auto" &&
								a.body.category === "service-unavailable",
						)
					: [];
			if (cell.mode === "zero-budget-fourth") expect(dropAudit).toHaveLength(1);
			const currentProducts = afterArtifacts.filter((artifact) => !dropAudit.includes(artifact));
			const currentProductKeys = currentProducts.map((a) => `${a.path}:${a.bytes}:${a.sha256}`);
			const row = {
				cell: cell.id,
				mode: cell.mode,
				baseline_keys: baselineKeys,
				after_keys: afterKeys,
				byte_invariance: JSON.stringify(baselineKeys) === JSON.stringify(currentProductKeys),
				state_writes: state.writes,
				extra,
			};
			k4Emit("T06-K8-BOUNDARY-ROW", row);
			// Real repeated result / old-offer replay / zero-budget fourth must
			// preserve all existing bytes and add no fourth business effect.
			expect(row.byte_invariance, JSON.stringify(row)).toBe(true);
			expect(state.writes, JSON.stringify(row)).toBe(3);
			if (cell.mode === "old-offer-replay")
				expect((extra.replay_submit as Record<string, unknown>)?.status, JSON.stringify(row)).toBe("refused");
			if (cell.mode === "zero-budget-fourth")
				expect((extra.fourth_submit as Record<string, unknown>)?.status, JSON.stringify(row)).not.toBe("planned");
			if (cell.mode === "repeated-tool-result")
				expect(extra.state_writes_after as number, JSON.stringify(row)).toBe(extra.state_writes_before as number);
		});
	}

	it("T06-K8-UNCOVERED declares concrete not-covered cells (data only)", () => {
		k4Emit("T06-K8-UNCOVERED", { missing: k8Uncovered });
		// Explicitly NOT asserted as coverage: length is structural only. A real
		// coverage claim for these cells would require the named production seams.
		expect(Array.isArray(k8Uncovered)).toBe(true);
	});
});
