/** T15-D — registered PM feedback/offer owner binding, fully offline.
 *
 * The suite harness/faux provider drives the real registered ask_decision
 * execute. Injected children are counted but never invoked by the disabled
 * config reader. No DP answer, approval, receipt, sign-off or real provider.
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	ASK_DECISION_TOOL,
	type DecideConfigReader,
	type DecideRunner,
	type LifecycleRunner,
	type RawDecideResult,
	registerAskDecisionTool,
	type SignRunner,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	type OfferRevalidation,
	type PrepareOfferInput,
	type PrepareOfferResult,
	SUBMIT_DECISION_HANDOFF_TOOL,
	type SubmitDecisionHostHandle,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import type { DecisionFeedback, HostFacts } from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

const KEY = "mw-pm-owner-binding";
const SELF = currentClaimId();
const FOREIGN = "other-host:999";
const FORGED_OWNER = "forged-host-owner";
const WORKER_OWNER = "worker-run-owner";
const TASK = "owner-binding-worker";
const NOW = "2026-11-17T12:00:00Z";

const selfActive = `| ${KEY} | active | EXECUTE | ${SELF} | — | fixture | now |`;
const selfActive2 = `| ${KEY}-2 | active | EXECUTE | ${SELF} | — | fixture | now |`;
const foreignActive = `| ${KEY} | active | EXECUTE | ${FOREIGN} | — | fixture | now |`;

const tempDirs: string[] = [];
const harnesses: Harness[] = [];
const savedEnv = new Map<string, string | undefined>();

function mkTemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-pm-owner-"));
	tempDirs.push(dir);
	return dir;
}

function dpAutoMaterial(): Record<string, unknown> {
	return {
		question: "Which handling option should the PM take?",
		background: {
			task_goal: "bind feedback to the real PM claim",
			current_state: "the decision point is disabled",
			tried: "no DP answer or approval is constructed",
			unknowns: "none for this identity check",
			constraints: "existing claim, role and write face only",
		},
		handling_options: [
			{
				id: "c1",
				label: "continue",
				description: "stay in scope",
				consequence: "keeps scope",
				risk: "low",
				conditions: "within budget",
			},
			{
				id: "c2",
				label: "collect",
				description: "collect evidence",
				consequence: "adds a step",
				risk: "low",
				conditions: "within budget",
			},
		],
	};
}

function dpAutoPreparation(): Record<string, unknown> {
	return {
		prepared_at: NOW,
		basis_catalog: [
			{ id: "basis", text: "Review the referenced fact", material_refs: ["question"], applies_to: ["c1", "c2"] },
		],
	};
}

function workerMaterial(): Record<string, unknown> {
	return {
		task_goal: "preserve worker binding semantics",
		reachability_facts: "The worker card and run.json are present.",
		completed: "Read the card.",
		remaining: "Check the local identity.",
		blockers: "none",
		constraints: "worker-local identity only",
	};
}

function workerPreparation(): Record<string, unknown> {
	return {
		prepared_at: NOW,
		basis_catalog: [
			{
				id: "worker-card",
				text: "The worker run state supplies its owner",
				material_refs: ["reachability_facts"],
				applies_to: ["continue"],
			},
		],
	};
}

interface Counts {
	decide: number;
	lifecycle: number;
	sign: number;
}

interface OfferCapture {
	initial: PrepareOfferInput["identity"];
	revalidated: OfferRevalidation["identity"];
}

function captureHandle(captures: OfferCapture[]): SubmitDecisionHostHandle {
	return {
		prepareOffer(input: PrepareOfferInput): PrepareOfferResult {
			const rev = input.revalidate();
			captures.push({
				initial: structuredClone(input.identity),
				revalidated: structuredClone(rev.identity),
			});
			return {
				prepared: false,
				metadata: {
					submittable: false,
					submit_tool: SUBMIT_DECISION_HANDOFF_TOOL,
					gaps: ["test-only-no-offer"],
				},
			};
		},
		readCommittedSelection: () => undefined,
		hostExpectedFor: () => undefined,
	};
}

function forgedHostFacts(): HostFacts {
	return {
		binding: {
			role: "pm",
			owner: FORGED_OWNER,
			claim_id: FORGED_OWNER,
			binding_version: "decision-handoff/v1",
			observed_at: NOW,
		},
	};
}

interface Scenario {
	index: string | null;
	params?: Record<string, unknown>;
	hostFacts?: HostFacts;
	handle?: SubmitDecisionHostHandle;
	taskPath?: string;
}

interface AskResult {
	text: string;
	payload: Record<string, unknown>;
	feedback: DecisionFeedback;
	counts: Counts;
}

async function registeredAsk(scenario: Scenario): Promise<AskResult> {
	const root = mkTemp();
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	if (scenario.index !== null) {
		fs.writeFileSync(path.join(root, ".agenticdoc", "_index.parallel"), `${scenario.index}\n`, "utf8");
	}
	if (scenario.taskPath !== undefined) {
		const taskDir = path.dirname(scenario.taskPath);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(scenario.taskPath, "type: coding\n\n## 上下文\n\nfixture\n", "utf8");
		fs.writeFileSync(
			path.join(taskDir, "run.json"),
			JSON.stringify({
				schema: 1,
				task_key: TASK,
				run_id: `${TASK}@${NOW}`,
				owner_key: WORKER_OWNER,
				kind: "coding",
				status: "running",
				started_at: NOW,
				artifacts: [],
			}),
			"utf8",
		);
	}
	const counts: Counts = { decide: 0, lifecycle: 0, sign: 0 };
	const empty: RawDecideResult = { status: 0, stdout: "", stderr: "", timedOut: false };
	const runner: DecideRunner = async () => {
		counts.decide += 1;
		return empty;
	};
	const lifecycleRunner: LifecycleRunner = async () => {
		counts.lifecycle += 1;
		return empty;
	};
	const signRunner: SignRunner = async () => {
		counts.sign += 1;
		return empty;
	};
	const configReader: DecideConfigReader = () => ({
		transport: "on",
		dpDisabled: true,
		signoffDisabled: false,
		mode: "unknown",
		configRefs: [".mw/decide-points.json"],
	});
	const harness = await createHarness({
		extensionFactories: [
			(pi: ExtensionAPI) => {
				registerAskDecisionTool(pi, {
					projectDir: root,
					taskPath: scenario.taskPath,
					initiatorRole: scenario.taskPath === undefined ? "pm" : undefined,
					runner,
					lifecycleRunner,
					signRunner,
					configReader,
					hostFacts: scenario.hostFacts,
					submitHandle: scenario.handle,
				});
			},
		],
	});
	harnesses.push(harness);
	const params: Record<string, unknown> = {
		dp: "dp-auto",
		trigger: `${KEY}#ckpt1`,
		material: dpAutoMaterial(),
		preparation: dpAutoPreparation(),
		...scenario.params,
	};
	harness.setResponses([
		fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, params)], { stopReason: "toolUse" }),
		fauxAssistantMessage("done"),
	]);
	await harness.session.prompt("Check owner binding.");
	const toolResult = harness.session.messages.filter((message) => message.role === "toolResult").at(-1);
	const text = getMessageText(toolResult);
	const lines = text.split("\n");
	const payload = JSON.parse(lines[0] ?? "") as Record<string, unknown>;
	let feedback: DecisionFeedback | undefined;
	for (const line of lines.slice(1)) {
		try {
			const parsed = JSON.parse(line) as { decision_feedback?: DecisionFeedback };
			if (parsed.decision_feedback !== undefined) feedback = parsed.decision_feedback;
		} catch {
			// Directive / offer line, not feedback JSON.
		}
	}
	if (feedback === undefined) throw new Error("registered ask result has no decision_feedback");
	return { text, payload, feedback, counts };
}

function diagnosisReason(payload: Record<string, unknown>): string | undefined {
	const diagnosis = payload.claim_diagnosis;
	if (diagnosis === null || typeof diagnosis !== "object" || Array.isArray(diagnosis)) return undefined;
	return (diagnosis as { reason?: string }).reason;
}

beforeEach(() => {
	savedEnv.set("PI_WORKER_TASK", process.env.PI_WORKER_TASK);
	delete process.env.PI_WORKER_TASK;
});

afterEach(() => {
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

describe("T15-D registered PM owner binding", () => {
	it("binds a live PM claim into disabled feedback and the prepared offer identity", async () => {
		const offers: OfferCapture[] = [];
		const result = await registeredAsk({
			index: selfActive,
			hostFacts: forgedHostFacts(),
			handle: captureHandle(offers),
		});
		expect(result.payload).toMatchObject({ available: false, unavailable: "disabled", action: "blocked-ask-human" });
		expect(Object.hasOwn(result.payload, "decision_id")).toBe(false);
		expect(Object.hasOwn(result.payload, "answers")).toBe(false);
		expect(result.text).toContain("disabled ≠ approval");
		expect(result.feedback.owner).toBe(SELF);
		expect(result.feedback.binding?.owner).toBe(SELF);
		expect(result.feedback.binding?.claim_id).toBe(SELF);
		expect(result.feedback.binding?.owner).not.toBe(FORGED_OWNER);
		expect(result.feedback.gaps ?? []).not.toContain("owner");
		expect(result.feedback.gaps ?? []).not.toContain("host.binding.owner");
		expect(offers).toHaveLength(1);
		expect(offers[0]?.initial).toMatchObject({ source: "pm", owner: SELF, claimId: SELF, key: KEY });
		expect(offers[0]?.revalidated).toMatchObject({ source: "pm", owner: SELF, claimId: SELF, key: KEY });
		expect(result.counts).toEqual({ decide: 0, lifecycle: 0, sign: 0 });
	});

	for (const entry of [
		{ name: "missing", index: null, params: {}, reason: "index-empty-or-unparseable" },
		{ name: "foreign", index: foreignActive, params: { key: KEY }, reason: "foreign-owner" },
		{ name: "ambiguous", index: `${selfActive}\n${selfActive2}`, params: {}, reason: "ambiguous-claim" },
	] as const) {
		it(`refuses a legal owner for ${entry.name} claim and ignores forged hostFacts`, async () => {
			const offers: OfferCapture[] = [];
			const result = await registeredAsk({
				index: entry.index,
				params: entry.params,
				hostFacts: forgedHostFacts(),
				handle: captureHandle(offers),
			});
			expect(result.payload.available).toBe(false);
			expect(diagnosisReason(result.payload)).toBe(entry.reason);
			expect(result.feedback.owner).toBeUndefined();
			expect(result.feedback.binding?.owner).toBeUndefined();
			expect(result.feedback.owner).not.toBe(FORGED_OWNER);
			expect(result.feedback.gaps).toContain("owner");
			expect(offers).toHaveLength(0);
			expect(result.counts).toEqual({ decide: 0, lifecycle: 0, sign: 0 });
		});
	}

	it("keeps worker run owner_key semantics and never promotes them to a PM claim", async () => {
		const offers: OfferCapture[] = [];
		const root = mkTemp();
		const taskPath = path.join(root, ".agenticdoc", KEY, "workers", TASK, "task.md");
		const result = await registeredAsk({
			index: selfActive,
			taskPath,
			handle: captureHandle(offers),
			params: {
				dp: "dp-w-check-task",
				trigger: `${TASK}#ckpt1`,
				task_key: TASK,
				material: workerMaterial(),
				preparation: workerPreparation(),
			},
		});
		expect(result.payload).toMatchObject({ available: false, unavailable: "disabled" });
		expect(result.feedback.owner).toBe(WORKER_OWNER);
		expect(result.feedback.binding?.owner).toBe(WORKER_OWNER);
		expect(result.feedback.owner).not.toBe(SELF);
		expect(result.feedback.binding?.claim_id).toBeUndefined();
		expect(result.feedback.binding?.run_id).toBe(`${TASK}@${NOW}`);
		expect(offers).toHaveLength(1);
		expect(offers[0]?.initial).toMatchObject({ source: "worker-local", owner: WORKER_OWNER, key: KEY });
		expect(offers[0]?.initial.claimId).toBeUndefined();
		expect(offers[0]?.revalidated).toMatchObject({ source: "worker-local", owner: WORKER_OWNER, key: KEY });
		expect(offers[0]?.revalidated.claimId).toBeUndefined();
		expect(result.counts).toEqual({ decide: 0, lifecycle: 0, sign: 0 });
	});
});
