import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai/compat";
import { Type } from "typebox";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	registerSubmitDecisionHandoffTool,
	SUBMIT_DECISION_HANDOFF_TOOL,
	type SubmitDecisionHostHandle,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import {
	createRuntimeBudgetController,
	type RuntimeBudgetAuthorization,
} from "../../src/extensions/agent-team-loop/pm/runtime-budget.ts";
import {
	buildMatterBudgetFromCard,
	ProductionRuntimeHost,
	RUNTIME_BUDGET_ENTRY_TYPE,
	registerProductionRuntimeEvents,
} from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import { sha256EolNormalizedBytes } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import type { DecisionPreparation } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { LocalSelectionStore } from "../../src/extensions/agent-team-loop/shared/local-selection-store.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

const roots: string[] = [];
const harnesses: Harness[] = [];
afterEach(() => {
	vi.restoreAllMocks();
	for (const harness of harnesses.splice(0)) harness.cleanup();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

const key = "runtime-tool-isolation";
const claim = currentClaimId();
const now = Math.floor(Date.now() / 1000) * 1000;
const startedAt = new Date(now - 60_000).toISOString();
const deadline = new Date(now + 1_800_000).toISOString().replace(".000Z", "Z");

function card(task: string, deadlineText = deadline, remaining = 3): string {
	return [
		`owning_pm_claim: ${claim}`,
		"",
		"## 事项预算事实",
		`- \`budget_ref\`: \`tasks/${task}.md#事项预算事实\``,
		`- \`matter_ref\`: \`${key}/${task}\``,
		`- \`deadline\`: \`${deadlineText}\``,
		"- `max_steps`: 3",
		`- \`remaining_cost\`: ${remaining}`,
		"- `no_progress_limit`: 2",
		"- `steps_consumed`: 0",
		"- `cost_consumed`: 0",
		"- `no_progress_count`: 0",
		"- `cost_unit`: 1 cost unit = 1 tool call",
		"- `source_refs`: card SHA, `_index.parallel`, `task.md`",
		"",
	].join("\n");
}

describe("runtime date contract", () => {
	it.each([deadline, new Date(Date.parse(deadline)).toISOString()])(
		"opens parsed card %s, shares spent capacity and enforces the exact deadline",
		(deadlineText) => {
			const parsed = buildMatterBudgetFromCard(card("a", deadlineText), {
				cardRef: "tasks/a.md",
				cardSha256: "a".repeat(64),
				runStartedAt: startedAt,
				runRef: "fixture/run",
				indexRef: "_index.parallel",
			});
			expect(parsed.ok).toBe(true);
			if (!parsed.ok) throw new Error(parsed.reason);
			const binding = {
				authorization_unit: `${key}/a`,
				parent_budget_ref: "tasks/a.md#事项预算事实",
				matter_ref: "fixture-matter",
			};
			let clock = now;
			const authorization: RuntimeBudgetAuthorization = {
				...binding,
				initial: parsed.value.budget,
				cost_unit: "tool-call",
				started_at: startedAt.replace(".000Z", "Z"),
				history: { kind: "verified-empty", origin_ref: "fixture/start", through_ref: "fixture/head", events: [] },
			};
			const budget = createRuntimeBudgetController({
				clock: () => clock,
				readAuthorization: () => authorization,
				captureEvidence: () => [],
			});
			expect(budget.open(binding)).toMatchObject({ ok: true, value: { available_cost: 3 } });
			const action = { ...binding, call_id: "fixture-call", max_cost: 1, cost_unit: "tool-call" };
			expect(budget.reserve(action).ok).toBe(true);
			expect(
				budget.observe({
					...binding,
					call_id: action.call_id,
					result_ref: "fixture/result",
					outcome: "success",
					actual_cost: 1,
					cost_unit: action.cost_unit,
				}).ok,
			).toBe(true);
			expect(budget.open({ ...binding, matter_ref: "another-wrapper" })).toMatchObject({
				ok: true,
				value: { available_cost: 2, budget: { steps_consumed: 1 } },
			});
			expect(
				budget.reserveChild({
					...binding,
					reservation_id: "child",
					steps: 1,
					cost: 1,
					cost_unit: action.cost_unit,
					deadline: deadlineText,
				}).ok,
			).toBe(true);
			expect(budget.settle({ ...binding, reservation_id: "child" }).ok).toBe(true);
			const originalDeadline = authorization.initial.deadline;
			authorization.initial = {
				...authorization.initial,
				deadline: new Date(Date.parse(deadline) + 1000).toISOString(),
			};
			expect(budget.open(binding)).toMatchObject({ ok: false, code: "authorization-drift" });
			authorization.initial = { ...authorization.initial, deadline: originalDeadline };
			clock = Date.parse(deadline);
			expect(budget.reserve({ ...action, call_id: "late" })).toMatchObject({ ok: false, code: "budget-exhausted" });
		},
	);

	it.each(["2026-02-30T00:00:00Z", "2026-11-18T02:40:00+00:00", "2026-11-18T02:40:00.00Z", "invalid"])(
		"refuses malformed/noncanonical card date %s",
		(value) => {
			expect(
				buildMatterBudgetFromCard(card("a", value), {
					cardRef: "tasks/a.md",
					cardSha256: "a".repeat(64),
					runRef: "fixture/run",
					indexRef: "_index.parallel",
				}).ok,
			).toBe(false);
		},
	);
});

async function fixture(options: { invalidBudget?: boolean } = {}) {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "runtime-tool-isolation-"));
	roots.push(root);
	const doc = path.join(root, ".agenticdoc");
	fs.mkdirSync(path.join(doc, key, "tasks"), { recursive: true });
	fs.writeFileSync(path.join(doc, "_index.parallel"), `| ${key} | active | EXECUTE | ${claim} | | fixture | now |\n`);
	const clock = { at: now };
	const host = new ProductionRuntimeHost(root, () => clock.at);
	const state = { failWrite: false };
	let handle: SubmitDecisionHostHandle | undefined;
	const bodies: string[] = [];
	const h = await createHarness({
		extensionFactories: [
			(pi) => {
				registerProductionRuntimeEvents(pi, host);
				pi.on("tool_call", (event) => {
					if (event.toolName === "read" && event.input.path === "denied.txt")
						return { block: true, reason: "fixture-read-scope" };
					return undefined;
				});
				handle = registerSubmitDecisionHandoffTool(pi, {
					projectDir: root,
					hostRuntime: host,
					runtimeHost: host.adapterHooks(),
					clock: () => clock.at,
				});
				for (const name of ["read", "ls", "find", "grep", "bash", "edit", "write"]) {
					pi.registerTool({
						name,
						label: name,
						description: "isolated fixture tool",
						parameters: Type.Object({ path: Type.String(), content: Type.Optional(Type.String()) }),
						execute: async (_id, params) => {
							bodies.push(name);
							if (name === "write" && state.failWrite) throw new Error("fixture disk failure");
							if (name === "write") fs.writeFileSync(path.join(root, params.path), params.content ?? "changed");
							return {
								content: [
									{
										type: "text",
										text:
											name === "read"
												? fs.readFileSync(path.join(root, params.path), "utf8")
												: "fixture-result",
									},
								],
								details: {},
							};
						},
					});
				}
			},
		],
	});
	harnesses.push(h);
	await h.session.bindExtensions({});
	if (!handle) throw new Error("submit handle missing");
	for (const task of ["a", "b"]) {
		const text = card(task, deadline, options.invalidBudget ? 1.5 : 3);
		fs.writeFileSync(path.join(doc, key, "tasks", `${task}.md`), text);
		const envelope = path.join(root, `${task}.md`);
		fs.writeFileSync(
			envelope,
			`card_path: tasks/${task}.md\ncard_sha256: ${sha256EolNormalizedBytes(Buffer.from(text))}\nwrite_face: ${task}.txt\n`,
		);
		fs.writeFileSync(path.join(root, `${task}.txt`), `original-${task}`);
		const registered = host.registerPmDispatch({
			key,
			taskKey: task,
			claimId: claim,
			taskMdPath: envelope,
			dispatchedAt: startedAt,
		});
		expect(registered.ok, JSON.stringify(registered)).toBe(true);
	}
	const submitHandle = handle;
	return {
		root,
		doc,
		host,
		h,
		bodies,
		state,
		clock,
		prepare(task: string) {
			const identity = { source: "pm" as const, key, role: "pm" as const, claimId: claim, taskKey: task };
			const preparation: DecisionPreparation = {
				prepared_at: new Date(now).toISOString(),
				basis_catalog: [
					{
						id: "basis",
						applies_to: ["continue"],
						material_refs: ["background.current_state"],
						text: "Isolated fixture has a registered pin and finite budget",
					},
				],
			};
			const offer = submitHandle.prepareOffer({
				dp: "dp-auto",
				identity,
				matterRef: `fixture-${task}`,
				feedbackEffectUnknown: false,
				preparation,
				material: {
					question: "Choose the isolated fixture action",
					background: {
						task_goal: "test runtime isolation",
						current_state: "fixture registered",
						tried: "none",
						unknowns: "none",
						constraints: "fixture only",
					},
					handling_options: [
						{
							id: "continue",
							label: "Continue",
							description: "One bounded fixture write",
							consequence: "fixture bytes only",
							risk: "low",
							conditions: "registered source",
						},
						{
							id: "stop",
							label: "Stop",
							description: "No fixture effect",
							consequence: "none",
							risk: "low",
							conditions: "no execution",
						},
					],
				},
				revalidate: () => ({ configSignature: "fixture", hostSignature: "fixture", identity, trustedStop: false }),
			});
			expect(offer.prepared, JSON.stringify(offer)).toBe(true);
			if (!offer.metadata.offer_id) throw new Error("offer missing");
			return { offer_id: offer.metadata.offer_id, choice: "continue", basis_id: "basis" };
		},
		async tool(name: string, args: Record<string, unknown>) {
			const id = randomUUID();
			h.setResponses([
				fauxAssistantMessage([fauxToolCall(name, args, { id })], { stopReason: "toolUse" }),
				fauxAssistantMessage("done"),
			]);
			await h.session.prompt(`isolated ${name}`);
			const result = h.session.messages.find(
				(message) => message.role === "toolResult" && message.toolCallId === id,
			);
			if (!result || result.role !== "toolResult") throw new Error("tool result missing");
			return { error: result.isError, text: getMessageText(result), details: result.details };
		},
		events() {
			return h.sessionManager
				.getEntries()
				.filter(
					(entry) =>
						entry.type === "custom" &&
						entry.customType === RUNTIME_BUDGET_ENTRY_TYPE &&
						(entry.data as { kind?: string }).kind === "event",
				);
		},
	};
}

describe("runtime submission and read-only isolation", () => {
	it("read-only recovery still obeys other extension read-scope guards", async () => {
		const f = await fixture({ invalidBudget: true });
		expect((await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, f.prepare("a"))).details).toMatchObject({ status: "refused" });
		expect((await f.tool("read", { path: "denied.txt" })).text).toContain("fixture-read-scope");
		expect(f.bodies).toEqual([]);
	});
	it("accepts a seconds-only card through real submit and observes one controlled write", async () => {
		const f = await fixture();
		const offer = f.prepare("b");
		expect((await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, offer)).details).toMatchObject({ status: "planned" });
		expect((await f.tool("write", { path: "b.txt", content: "changed-b" })).error).toBe(false);
		expect(fs.readFileSync(path.join(f.root, "b.txt"), "utf8")).toBe("changed-b");
		expect(f.host.countsSnapshot()).toMatchObject({ selectionCommits: 1, reserves: 1, observes: 1, appends: 1 });
		expect(f.events()).toHaveLength(2);
	});

	it("a real budget-open failure permits read-only diagnosis and never reserves a failed selection", async () => {
		const f = await fixture({ invalidBudget: true });
		expect((await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, f.prepare("a"))).details).toMatchObject({
			status: "refused",
			reason: "store-trusted-context-refused",
		});
		for (const tool of ["read", "ls", "find", "grep"])
			expect((await f.tool(tool, { path: "a.txt" })).error).toBe(false);
		for (const tool of ["bash", "edit", "write"]) expect((await f.tool(tool, { path: "a.txt" })).error).toBe(true);
		expect(f.bodies).toEqual(["read", "ls", "find", "grep"]);
		expect(f.events()).toHaveLength(0);
		expect(f.host.countsSnapshot()).toMatchObject({ selectionCommits: 0, reserves: 0, observes: 0 });
	});

	it.each(["refused", "threw"] as const)(
		"a first %s submit leaves no executable binding even after the fault is gone",
		async (mode) => {
			const f = await fixture();
			const fault = vi.spyOn(LocalSelectionStore.prototype, "commitSelection");
			if (mode === "threw") fault.mockRejectedValueOnce(new Error("isolated store failure"));
			else
				fault.mockResolvedValueOnce({
					ok: false,
					code: "trusted-context-refused",
					verification: "host-context-checked",
					host_source_verified: false,
					gaps: ["fixture"],
					reason: "isolated refusal",
				});
			expect((await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, f.prepare("a"))).details).toMatchObject({
				status: "refused",
			});
			fault.mockRestore();
			expect((await f.tool("write", { path: "a.txt" })).text).toContain("selection-unproven");
			expect((await f.tool("read", { path: "a.txt" })).text).toBe("original-a");
			expect(f.events()).toHaveLength(0);
		},
	);

	it.each(["refused", "threw", "duplicate"] as const)(
		"a later %s submit preserves the prior successful source and selection",
		async (mode) => {
			const f = await fixture();
			const first = f.prepare("a");
			const second = f.prepare("b");
			if (mode === "duplicate")
				expect((await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, second)).details).toMatchObject({ status: "planned" });
			expect((await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, first)).details).toMatchObject({ status: "planned" });
			const fault = vi.spyOn(LocalSelectionStore.prototype, "commitSelection");
			if (mode === "threw") fault.mockRejectedValueOnce(new Error("isolated store failure"));
			else if (mode === "refused")
				fault.mockResolvedValueOnce({
					ok: false,
					code: "trusted-context-refused",
					verification: "host-context-checked",
					host_source_verified: false,
					gaps: ["fixture"],
					reason: "isolated refusal",
				});
			await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, second);
			fault.mockRestore();
			expect((await f.tool("write", { path: "a.txt", content: "accepted-a" })).error).toBe(false);
			expect(fs.readFileSync(path.join(f.root, "a.txt"), "utf8")).toBe("accepted-a");
			expect(fs.readFileSync(path.join(f.root, "b.txt"), "utf8")).toBe("original-b");
		},
	);

	it("a host error still permits read-only diagnosis while mutation tools stay blocked", async () => {
		const f = await fixture();
		expect((await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, f.prepare("a"))).details).toMatchObject({ status: "planned" });
		// A host stop is produced by an actual tool error, never by a model flag.
		f.state.failWrite = true;
		expect((await f.tool("write", { path: "a.txt" })).error).toBe(true);
		f.state.failWrite = false;
		const events = f.events().length;
		for (const tool of ["read", "ls", "find", "grep"])
			expect((await f.tool(tool, { path: "a.txt" })).error).toBe(false);
		for (const tool of ["bash", "edit", "write"]) expect((await f.tool(tool, { path: "a.txt" })).error).toBe(true);
		expect(f.events()).toHaveLength(events);
		expect(f.host.countsSnapshot()).toMatchObject({ reserves: 1, unknowns: 1 });
	});

	it("an expired committed selection permits reads without allowing another controlled effect", async () => {
		const f = await fixture();
		expect((await f.tool(SUBMIT_DECISION_HANDOFF_TOOL, f.prepare("a"))).details).toMatchObject({ status: "planned" });
		f.clock.at = Date.parse(deadline);
		expect((await f.tool("read", { path: "a.txt" })).text).toBe("original-a");
		expect((await f.tool("write", { path: "a.txt" })).text).toContain("budget-exhausted");
		expect(f.events()).toHaveLength(0);
		expect(f.host.countsSnapshot().reserves).toBe(0);
	});
});
