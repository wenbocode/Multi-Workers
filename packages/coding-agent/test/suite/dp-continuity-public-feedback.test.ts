/**
 * T04A — r2 public feedback + matter-scoped retry suppression (design §4.1/4.5).
 *
 * L1 / public-entry integration ONLY. Fully offline: a CapturingApi drives the
 * REAL registered `ask_decision`/`decision_receipt` execute, one faux-provider
 * harness case proves an independent legal tool still runs after two DP
 * failures, and injected runner/config spies count every child. No real DP,
 * provider, python child, sign-off, QG or 32VC claim.
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	ASK_DECISION_GUESS_DIRECTIVE,
	ASK_DECISION_TOOL,
	type AskDecisionInput,
	type AskDecisionOutcome,
	type AskDecisionPayload,
	DECISION_RECEIPT_TOOL,
	type DecideConfigReader,
	type DecideRunner,
	type LifecycleRunner,
	type RawDecideResult,
	readRealDecideConfigFacts,
	registerAskDecisionTool,
	runAskDecision,
	type SignRunner,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { canPmSelectType } from "../../src/extensions/agent-team-loop/pm/type-fallback.ts";
import {
	type DecideConfigFacts,
	type DecisionPreparation,
	readDecideConfigFacts,
} from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import {
	classifyDecisionFeedback,
	type DecisionFeedback,
	type HostFacts,
	parseDecisionFeedback,
} from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { createHarness, type Harness } from "./harness.ts";

const KEY = "mw-dp-r2-t04a";
const TEST_DP = "dp-auto";
const CHILD_ID = `${TEST_DP}:t04a-child`;

interface ToolResult {
	content: Array<{ type: "text"; text: string }>;
	details: unknown;
	terminate?: boolean;
}

interface CapturedTool {
	name: string;
	description?: string;
	promptGuidelines?: string[];
	execute: (toolCallId: string, params: Record<string, unknown>, signal?: AbortSignal) => Promise<ToolResult>;
}

type Handler = (event: unknown, ctx: unknown) => unknown;

class CapturingApi {
	readonly tools = new Map<string, CapturedTool>();
	readonly handlers = new Map<string, Handler[]>();
	active: string[] = [];

	registerTool(tool: unknown): void {
		const captured = tool as CapturedTool;
		this.tools.set(captured.name, captured);
	}

	on(event: string, handler: Handler): void {
		this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
	}

	getActiveTools(): string[] {
		return [...this.active];
	}

	setActiveTools(names: string[]): void {
		this.active = [...names];
	}

	fire(event: string): void {
		for (const handler of this.handlers.get(event) ?? []) handler({ type: event }, {});
	}
}

function toolOf(capture: CapturingApi, name: string): CapturedTool {
	const tool = capture.tools.get(name);
	if (tool === undefined) throw new Error(`tool '${name}' was not registered`);
	return tool;
}

const tempDirs: string[] = [];
const harnesses: Harness[] = [];
const savedEnv = new Map<string, string | undefined>();

function mkTemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-t04a-"));
	tempDirs.push(dir);
	return dir;
}

/** A PM project with a REAL self-active claim row and an enabled transport. */
function pmProject(): { root: string; indexFile: string } {
	const root = mkTemp();
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	const indexFile = path.join(root, ".agenticdoc", "_index.parallel");
	fs.writeFileSync(indexFile, `| ${KEY} | active | EXECUTE | ${currentClaimId()} | — | fixture | now |\n`, "utf8");
	return { root, indexFile };
}

function dpAutoMaterial(): Record<string, unknown> {
	return {
		question: "Which option should the PM take?",
		background: {
			task_goal: "public feedback continuity",
			current_state: "DP service failed twice",
			tried: "no retry of the same matter",
			unknowns: "whether new evidence exists",
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
		prepared_at: "2026-11-12T10:00:00Z",
		basis_catalog: [
			{ id: "basis", text: "Review the referenced evidence", material_refs: ["question"], applies_to: ["c1", "c2"] },
		],
	};
}

/** Direct public API call with a registry-valid material/preparation pair. */
function directAsk(spy: Spies, overrides: Partial<AskDecisionInput> = {}): Promise<AskDecisionOutcome> {
	return runAskDecision({
		projectDir: mkTemp(),
		dp: TEST_DP,
		trigger: "t04a#direct",
		initiatorRole: "pm",
		key: KEY,
		material: dpAutoMaterial(),
		preparation: dpAutoPreparation() as unknown as NonNullable<AskDecisionInput["preparation"]>,
		runner: spy.decide,
		lifecycleRunner: spy.lifecycle,
		...overrides,
	});
}

/** A valid material-path answer whose decision_id joins the envelope meta. */
function successSpy(mode: string): Spies {
	return spies((_call, input) => {
		const envelope = JSON.parse(input) as { meta: { logical_id: string } };
		return raw(
			0,
			okStdout({
				mode,
				decision_id: `${TEST_DP}:${envelope.meta.logical_id}`,
				answers: { handling: { value: "c1" }, basis_id: { value: "basis" } },
			}),
		);
	});
}

function askParams(trigger = "t04a#ckpt1"): Record<string, unknown> {
	return { dp: TEST_DP, trigger, key: KEY, material: dpAutoMaterial(), preparation: dpAutoPreparation() };
}

function okStdout(overrides: Record<string, unknown> = {}): string {
	return JSON.stringify({
		available: true,
		file_evidence: [],
		decision_id: CHILD_ID,
		mode: "auto",
		acted: false,
		latency_ms: 7,
		confidence_source: "api",
		answers: { answer_kind: { value: "fact" } },
		reason: null,
		escalated_reason: null,
		...overrides,
	});
}

function unavailableStdout(reason: string, escalated?: string): string {
	return JSON.stringify({
		available: false,
		decision_id: CHILD_ID,
		mode: "auto",
		acted: false,
		latency_ms: 3,
		confidence_source: "unknown",
		answers: null,
		reason,
		escalated_reason: escalated ?? null,
	});
}

function raw(status: number | null, stdout: string, overrides: Partial<RawDecideResult> = {}): RawDecideResult {
	return { status, stdout, stderr: "", timedOut: false, ...overrides };
}

interface Spies {
	decideCalls: Array<{ dp: string; input: string }>;
	lifecycleCalls: string[];
	signCalls: string[];
	decide: DecideRunner;
	lifecycle: LifecycleRunner;
	sign: SignRunner;
}

function spies(reply: (call: number, input: string) => RawDecideResult): Spies {
	const decideCalls: Array<{ dp: string; input: string }> = [];
	const lifecycleCalls: string[] = [];
	const signCalls: string[] = [];
	return {
		decideCalls,
		lifecycleCalls,
		signCalls,
		decide: async (request) => {
			decideCalls.push({ dp: request.dp, input: request.input });
			return reply(decideCalls.length, request.input);
		},
		lifecycle: async (request) => {
			lifecycleCalls.push(request.input);
			return raw(0, JSON.stringify({ recorded: true, status: "written" }));
		},
		sign: async (request) => {
			signCalls.push(request.input);
			return raw(0, JSON.stringify({ recorded: true, status: "written" }));
		},
	};
}

function capture(): { api: CapturingApi; pi: ExtensionAPI } {
	const api = new CapturingApi();
	return { api, pi: api as unknown as ExtensionAPI };
}

/** The registered tool keeps the frozen legacy payload on line 1 and puts
 * the frozen T01 feedback on line 2; surface both through one test view. */
function feedbackFromText(text: string): DecisionFeedback | undefined {
	for (const line of text.split("\n").slice(1)) {
		try {
			const parsed = JSON.parse(line) as { decision_feedback?: DecisionFeedback };
			if (parsed.decision_feedback !== undefined) return parsed.decision_feedback;
		} catch {
			// Directive / diagnosis line, not JSON.
		}
	}
	return undefined;
}

function payloadOf(text: string): AskDecisionPayload {
	const payload = JSON.parse(text.split("\n")[0] ?? "") as AskDecisionPayload;
	const feedback = feedbackFromText(text);
	if (feedback !== undefined) payload.decision_feedback = feedback;
	return payload;
}

/** Direct `runAskDecision` calls carry the feedback on the outcome. */
function payloadOfOutcome(outcome: { text: string; decision_feedback?: DecisionFeedback }): AskDecisionPayload {
	const payload = payloadOf(outcome.text);
	if (outcome.decision_feedback !== undefined) payload.decision_feedback = outcome.decision_feedback;
	return payload;
}

function feedbackOf(payload: AskDecisionPayload): DecisionFeedback {
	const feedback = payload.decision_feedback;
	if (feedback === undefined) throw new Error("public result lacks decision_feedback");
	return feedback;
}

/** No `key` option: identity comes from the REAL live claim read (so an
 *  empty index really is an unbound window, not a shortcut). */
function reg(
	root: string,
	options: {
		spy: Spies;
		configReader?: DecideConfigReader;
		hostFacts?: HostFacts;
	},
): CapturingApi {
	const { api, pi } = capture();
	registerAskDecisionTool(pi, {
		projectDir: root,
		initiatorRole: "pm",
		runner: options.spy.decide,
		lifecycleRunner: options.spy.lifecycle,
		signRunner: options.spy.sign,
		configReader: options.configReader,
		hostFacts: options.hostFacts,
	});
	return api;
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

// ── 1. frozen feedback on every public result, verbatim raw reason ───────────

describe("T04A public runAskDecision feedback", () => {
	it("preserves an unknown child reason BEFORE frozen normalisation", async () => {
		const spy = spies(() => raw(0, unavailableStdout("vendor-weird-7")));
		const outcome = await directAsk(spy, { trigger: "t04a#raw" });
		const payload = payloadOfOutcome(outcome);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.unavailable).toBe("upstream-error");
		const feedback = feedbackOf(payload);
		expect(feedback.raw_reason).toBe("vendor-weird-7");
		expect(feedback.origin).toBe("mw-decide-run");
		expect(feedback.stage).toBe("service-reply");
		expect(feedback.category).toBe("unclassified");
		expect(feedback.stop_scope).toBe("unknown");
		expect(feedback.effect_state).toBe("unknown");
		expect(feedback.binding?.binding_version).toBe("decision-handoff/v1");
		expect(parseDecisionFeedback(feedback).ok).toBe(true);
		expect(outcome.text).toContain(ASK_DECISION_GUESS_DIRECTIVE);
	});

	it("keeps timeout / malformed reply / low-confidence raw reasons with real origin and stage", async () => {
		const cases: Array<{ reply: RawDecideResult; reason: string; category: string }> = [
			{ reply: raw(null, "", { timedOut: true }), reason: "timeout", category: "service-unavailable" },
			{ reply: raw(0, "Fatal: not json at all"), reason: "Fatal: not json at all", category: "service-unavailable" },
			{
				reply: raw(0, unavailableStdout("low-confidence", "low-confidence")),
				reason: "low-confidence",
				category: "unclassified",
			},
		];
		for (const entry of cases) {
			const spy = spies(() => entry.reply);
			const outcome = await directAsk(spy, { trigger: "t04a#reasons" });
			const feedback = feedbackOf(payloadOfOutcome(outcome));
			expect(feedback.raw_reason, entry.reason).toBe(entry.reason);
			expect(feedback.category, entry.reason).toBe(entry.category);
			expect(feedback.origin).toBe("mw-decide-run");
			expect(feedback.stage).not.toBe("");
			expect(feedback.matter_ref).toMatch(/^[0-9a-f]{32}$/);
		}
		// T01 pure primitive: a low-confidence SUCCESSFUL reply is uncertain,
		// never treated as a trusted answer.
		const uncertain = classifyDecisionFeedback({
			envelope: { feedback_ref: "f", matter_ref: "m", origin: "test", stage: "reply" },
			host: {
				binding: { role: "pm", binding_version: "decision-handoff/v1", observed_at: new Date().toISOString() },
			},
			raw: { available: true, decision_id: "x", answers: { q: { value: "v" } }, low_confidence: true },
		});
		expect(uncertain.category).toBe("uncertain-answer");
	});

	it("refuses to consume or receipt a correlated low-confidence answer", async () => {
		let decisionId = "";
		const spy = spies((_call, input) => {
			decisionId = `${TEST_DP}:${JSON.parse(input).meta.logical_id}`;
			return raw(
				0,
				okStdout({
					decision_id: decisionId,
					low_confidence: true,
					answers: { handling: { value: "c1" }, basis_id: { value: "basis" } },
				}),
			);
		});
		const api = reg(pmProject().root, { spy });
		const result = await toolOf(api, ASK_DECISION_TOOL).execute("ask", askParams());
		const payload = payloadOf(result.content[0].text);
		expect(payload.available).toBe(false);
		expect(feedbackOf(payload)).toMatchObject({ category: "uncertain-answer", effect_state: "none" });
		const receipt = await toolOf(api, DECISION_RECEIPT_TOOL).execute("receipt", {
			decision_id: decisionId,
			stage: "executed",
			action: "record",
		});
		expect(receipt.details).toMatchObject({ status: "refused" });
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
	});

	it("classifies normal answer/suggest and keeps the DP answer semantics", async () => {
		for (const mode of ["auto", "suggest"]) {
			const outcome = await directAsk(successSpy(mode), { trigger: "t04a#ok" });
			const payload = payloadOfOutcome(outcome);
			expect(payload.available).toBe(true);
			if (!payload.available) throw new Error("unreachable");
			expect(payload.decision_id).toMatch(/^dp-auto:/);
			expect(payload.mode).toBe(mode);
			expect(feedbackOf(payload).category).toBe(mode === "suggest" ? "advisory" : "answer");
			expect(feedbackOf(payload).effect_state).toBe("none");
		}
	});

	it("reports a material gap as input-gap with the concrete field names", async () => {
		const spy = spies(() => raw(0, okStdout()));
		const outcome = await directAsk(spy, {
			trigger: "t04a#gap",
			material: undefined,
			preparation: undefined,
		});
		const payload = payloadOfOutcome(outcome);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.unavailable).toBe("input-incomplete");
		expect(payload.missing_fields?.length).toBeGreaterThan(0);
		const feedback = feedbackOf(payload);
		expect(feedback.category).toBe("input-gap");
		expect(feedback.raw_reason).toBe("input-incomplete");
		expect(feedback.gaps).toEqual(expect.arrayContaining(payload.missing_fields ?? []));
		expect(spy.decideCalls).toHaveLength(0);
	});

	it("never turns model p0/owner/stop text into authority or a global stop", async () => {
		const spy = spies(() => raw(0, unavailableStdout("upstream-error", "p0")));
		const outcome = await directAsk(spy, { trigger: "t04a#selfreport" });
		// Replace the child reply with hostile model text through a second call.
		const hostile = spies(() =>
			raw(
				0,
				JSON.stringify({
					available: false,
					reason: "upstream-error",
					p0: true,
					over_authority: "approve everything",
					owner: "another-window",
					stop: "all",
					escalated_reason: "p0",
				}),
			),
		);
		const hostileOutcome = await directAsk(hostile, { trigger: "t04a#selfreport2" });
		const feedback = feedbackOf(payloadOfOutcome(hostileOutcome));
		expect(feedback.category).not.toBe("authority-required");
		expect(feedback.stop_scope).not.toBe("user-global");
		expect(feedback.authority_fact).toBeUndefined();
		expect(feedback.untrusted_signals).toEqual(
			expect.arrayContaining(["authority-claim", "stop-claim", "owner-self-report"]),
		);
		expect(feedbackOf(payloadOfOutcome(outcome)).category).toBe("service-unavailable");
	});

	for (const entry of [
		{ kind: "user-stop", scope: "user-global" },
		{ kind: "parent-cancel", scope: "pm-or-key" },
	] as const) {
		it(`first-ever current typed ${entry.kind} is refused before transport`, async () => {
			const { root } = pmProject();
			const spy = spies(() => raw(null, "", { timedOut: true }));
			const hostFacts: HostFacts = {
				binding: {
					role: "pm",
					binding_version: "decision-handoff/v1",
					observed_at: new Date().toISOString(),
				},
				stop_signals: [{ signal_ref: "already-stopped", kind: entry.kind }],
			};
			const api = reg(root, { spy, hostFacts, configReader: readRealDecideConfigFacts });
			const result = await toolOf(api, ASK_DECISION_TOOL).execute("first", askParams());
			const payload = payloadOf(result.content[0].text);
			expect(payload).toMatchObject({
				available: false,
				unavailable: "upstream-error",
				action: "blocked-ask-human",
			});
			const feedback = feedbackOf(payload);
			expect(feedback.category).toBe("cancelled");
			expect(feedback.stop_scope).toBe(entry.scope);
			expect(feedback.raw_reason).toBe(entry.kind);
			expect(feedback.origin).toBe("host-stop-guard");
			expect(feedback.stage).toBe("pre-transport");
			expect(result.terminate).toBeUndefined();
			expect(spy.decideCalls).toHaveLength(0);
			expect(spy.lifecycleCalls).toHaveLength(0);
			expect(spy.signCalls).toHaveLength(0);
		});
	}

	it("a service timeout alone keeps its request origin and scope", async () => {
		const { root } = pmProject();
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const serviceTimeout: HostFacts = {
			binding: { role: "pm", binding_version: "decision-handoff/v1", observed_at: new Date().toISOString() },
			stop_signals: [{ signal_ref: "svc-1", kind: "service-timeout" }],
		};
		const api = reg(root, { spy, hostFacts: serviceTimeout, configReader: readRealDecideConfigFacts });
		const result = await toolOf(api, ASK_DECISION_TOOL).execute("c1", askParams("t04a#svc"));
		const feedback = feedbackOf(payloadOf(result.content[0].text));
		expect(feedback.origin).toBe("mw-decide-run");
		expect(feedback.stage).toBe("child-timeout");
		expect(feedback.raw_reason).toBe("timeout");
		expect(feedback.category).toBe("service-unavailable");
		expect(feedback.stop_scope).toBe("service-request");
		expect(feedback.stop_scope).not.toBe("user-global");
		expect(spy.decideCalls).toHaveLength(1);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
	});
});

// ── 2. real config reader: known off states use ZERO DP network ─────────────

describe("T04A pre-transport config facts", () => {
	it("reads the real readers (per-dp row, transport, signoff) without writing config", () => {
		const root = mkTemp();
		fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
		fs.writeFileSync(
			path.join(root, ".mw", "decide-points.json"),
			JSON.stringify({ version: 1, points: { [TEST_DP]: { enabled: false } } }),
			"utf8",
		);
		fs.writeFileSync(
			path.join(root, ".mw", "decide.json"),
			JSON.stringify({ enabled: false, signoff: "disable" }),
			"utf8",
		);
		const facts = readRealDecideConfigFacts(TEST_DP, root);
		expect(facts.transport).toBe("off");
		expect(facts.dpDisabled).toBe(true);
		expect(facts.signoffDisabled).toBe(true);
		expect(readDecideConfigFacts("dp-QG", root).dpDisabled).toBe(false);
		const before = fs.readFileSync(path.join(root, ".mw", "decide.json"), "utf8");
		expect(JSON.parse(before)).toEqual({ enabled: false, signoff: "disable" });
	});

	it("known single-DP off / transport off / unconfigured produce zero runner calls", async () => {
		const cases: Array<{ facts: DecideConfigFacts; reason: string }> = [
			{
				facts: {
					transport: "on",
					dpDisabled: true,
					signoffDisabled: false,
					mode: "unknown",
					configRefs: [".mw/decide-points.json"],
				},
				reason: "disabled",
			},
			{
				facts: {
					transport: "off",
					dpDisabled: false,
					signoffDisabled: false,
					mode: "unknown",
					configRefs: [".mw/decide.json"],
				},
				reason: "disabled",
			},
			{
				facts: {
					transport: "unconfigured",
					dpDisabled: false,
					signoffDisabled: false,
					mode: "unknown",
					configRefs: [".mw/decide.json"],
				},
				reason: "unconfigured",
			},
		];
		for (const entry of cases) {
			const root = pmProject().root;
			const spy = spies(() => raw(0, okStdout()));
			const api = reg(root, { spy, configReader: () => entry.facts });
			const result = await toolOf(api, ASK_DECISION_TOOL).execute("cfg", askParams());
			const payload = payloadOf(result.content[0].text);
			expect(payload.available, entry.reason).toBe(false);
			if (payload.available) throw new Error("unreachable");
			expect(payload.unavailable).toBe(entry.reason);
			const feedback = feedbackOf(payload);
			expect(feedback.raw_reason).toBe(entry.reason);
			expect(feedback.origin).toBe("decide-config-reader");
			expect(feedback.stage).toBe("pre-transport");
			expect(feedback.category).toBe("service-unavailable");
			expect(feedback.evidence_refs).toEqual(entry.facts.configRefs);
			expect(spy.decideCalls).toHaveLength(0);
			expect(spy.lifecycleCalls).toHaveLength(0);
			expect(spy.signCalls).toHaveLength(0);
			expect(result.terminate).toBeUndefined();
		}
	});

	it("signoff=disable is a business exemption, never a service fault", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(0, okStdout()));
		const api = reg(root, {
			spy,
			configReader: () => ({
				transport: "on",
				dpDisabled: false,
				signoffDisabled: true,
				mode: "unknown",
				configRefs: [".mw/decide.json"],
			}),
		});
		const result = await toolOf(api, ASK_DECISION_TOOL).execute("cfg", {
			dp: "dp-sign-key",
			trigger: "t04a#sign",
			key: KEY,
		});
		const payload = payloadOf(result.content[0].text);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.unavailable).toBe("signoff-disabled");
		const feedback = feedbackOf(payload);
		expect(feedback.category).toBe("exemption");
		expect(feedback.exemption_fact?.kind).toBe("signoff-disabled");
		expect(feedback.stop_scope).toBe("none");
		expect(feedback.effect_state).toBe("none");
		expect(feedback.raw_reason).toBe("signoff-disabled");
		expect(result.content[0].text).toContain("不是服务故障");
		expect(spy.decideCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
	});
});

// ── 3. identity, cross-turn dedup, no global terminate ─────────────────────

describe("T04A matter suppression and fail-closed identity", () => {
	it("an unbound window yields real unbound feedback with zero business effect", async () => {
		const { root, indexFile } = pmProject();
		fs.writeFileSync(indexFile, "", "utf8");
		const before = fs.readFileSync(indexFile);
		const spy = spies(() => raw(0, okStdout()));
		const api = reg(root, { spy });
		const result = await toolOf(api, ASK_DECISION_TOOL).execute("bad", askParams());
		const payload = payloadOf(result.content[0].text);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.claim_diagnosis?.reason).toBe("index-empty-or-unparseable");
		const feedback = feedbackOf(payload);
		expect(feedback.origin).toBe("claim-binding");
		expect(feedback.stage).toBe("identity-check");
		expect(feedback.binding?.owner).toBeUndefined();
		expect(feedback.binding?.key).toBeUndefined();
		expect(feedback.gaps).toContain("owner");
		expect(feedback.stop_scope).toBe("none");
		expect(feedback.effect_state).toBe("none");
		expect(spy.decideCalls).toHaveLength(0);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
		expect(fs.readFileSync(indexFile).equals(before)).toBe(true);
		// A local_ref can never be receipted as a real DP decision.
		const receipt = await toolOf(api, DECISION_RECEIPT_TOOL).execute("r1", {
			decision_id: "local:not-a-dp",
			stage: "executed",
			action: "record",
		});
		expect((receipt.details as { status: string }).status).toBe("refused");
		expect(spy.lifecycleCalls).toHaveLength(0);
	});

	it("same matter across turn_start (and a changed trigger) never resends", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const api = reg(root, { spy });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = await ask.execute("c1", askParams("t04a#a"));
		const firstFeedback = feedbackOf(payloadOf(first.content[0].text));
		expect(spy.decideCalls).toHaveLength(1);
		api.fire("turn_start");
		const second = await ask.execute("c2", askParams("t04a#b"));
		const secondPayload = payloadOf(second.content[0].text);
		expect(secondPayload.matter_suppressed).toBe(true);
		expect(feedbackOf(secondPayload).feedback_ref).toBe(firstFeedback.feedback_ref);
		expect(feedbackOf(secondPayload).matter_ref).toBe(firstFeedback.matter_ref);
		expect(spy.decideCalls).toHaveLength(1);
		expect(second.terminate).toBeUndefined();
		// New real material is a NEW matter and may be re-prepared once.
		const third = await ask.execute("c3", { ...askParams("t04a#c"), note: "new observed evidence" });
		expect(payloadOf(third.content[0].text).matter_suppressed).toBeUndefined();
		expect(spy.decideCalls).toHaveLength(2);
	});

	it("two service failures never terminate the PM; another legal tool really runs", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const readCalls: string[] = [];
		const harness = await createHarness({
			extensionFactories: [
				(pi) => {
					pi.registerTool({
						name: "read",
						label: "Read fixture",
						description: "Read the named fixture",
						parameters: Type.Object({ path: Type.String() }),
						execute: async (_id: string, args: { path: string }) => {
							readCalls.push(args.path);
							return { content: [{ type: "text" as const, text: "fixture evidence" }], details: {} };
						},
					});
					registerAskDecisionTool(pi, {
						projectDir: root,
						initiatorRole: "pm",
						runner: spy.decide,
						lifecycleRunner: spy.lifecycle,
						signRunner: spy.sign,
					});
				},
			],
		});
		harnesses.push(harness);
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, askParams("t04a#f1"))], { stopReason: "toolUse" }),
			fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, askParams("t04a#f2"))], { stopReason: "toolUse" }),
			fauxAssistantMessage([fauxToolCall("read", { path: "evidence.txt" })], { stopReason: "toolUse" }),
			fauxAssistantMessage("done"),
		]);
		await harness.session.prompt("Continue.");
		const toolResults = harness.session.messages.filter((message) => message.role === "toolResult");
		const texts = toolResults.map((message) => JSON.stringify(message));
		expect(texts.some((text) => text.includes("TERMINAL"))).toBe(false);
		expect(spy.decideCalls).toHaveLength(1); // second ask was matter-suppressed
		expect(readCalls).toEqual(["evidence.txt"]);
		expect(toolResults.length).toBeGreaterThanOrEqual(3);
		// Description/prompt no longer instruct an unconditional human wait.
		const { api, pi } = capture();
		registerAskDecisionTool(pi, { projectDir: root, initiatorRole: "pm" });
		const description = toolOf(api, ASK_DECISION_TOOL).description ?? "";
		expect(description).toContain("decision_feedback");
		expect(description).toContain("NOT a global PM stop");
		const guidelines = toolOf(api, ASK_DECISION_TOOL).promptGuidelines ?? [];
		expect(guidelines.join(" ")).toContain("Two service failures never terminate the whole PM");
	});

	it("a real DP answer keeps consumed feedback and a strict receipt join; local_ref still refused", async () => {
		const root = pmProject().root;
		const spy = spies((_call, input) => {
			const envelope = JSON.parse(input) as { meta?: { logical_id?: string } };
			return raw(
				0,
				okStdout({
					decision_id: `dp-auto:${envelope.meta?.logical_id ?? "x"}`,
					answers: { handling: { value: "c1" }, basis_id: { value: "basis" } },
				}),
			);
		});
		const api = reg(root, { spy });
		const asked = await toolOf(api, ASK_DECISION_TOOL).execute("ask", {
			dp: "dp-auto",
			trigger: "t04a#join",
			key: KEY,
			material: dpAutoMaterial(),
			preparation: dpAutoPreparation(),
		});
		const payload = payloadOf(asked.content[0].text);
		expect(payload.available).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		expect(payload.feedback?.stage).toBe("consumed");
		expect(payload.feedback?.status).toBe("written");
		expect(payload.decision_feedback?.category).toBe("answer");
		expect(spy.lifecycleCalls).toHaveLength(1);

		const receipt = await toolOf(api, DECISION_RECEIPT_TOOL).execute("rec", {
			decision_id: payload.decision_id,
			stage: "executed",
			action: "record",
		});
		expect((receipt.details as { status: string }).status).toBe("written");
		expect(spy.lifecycleCalls).toHaveLength(2);
		const executed = JSON.parse(spy.lifecycleCalls[1]) as { stage: string; action: string; decision_id: string };
		expect(executed.stage).toBe("executed");
		expect(executed.action).toBe("record");
		expect(executed.decision_id).toBe(payload.decision_id);

		const forged = await toolOf(api, DECISION_RECEIPT_TOOL).execute("rec2", {
			decision_id: "local:some-local-ref",
			stage: "settled",
			outcome: "ok",
		});
		expect((forged.details as { status: string }).status).toBe("refused");
		expect(spy.lifecycleCalls).toHaveLength(2);
	});
});

// ── 4. R1 boundary regressions (from the PM's seven-case offline probe) ─────

function dpWTypeMaterial(): Record<string, unknown> {
	return {
		task_goal: "Repair the public feedback boundary",
		task_requirements: "Use the original card and the prepared basis",
		task_deliverables: "Code, tests and a verification report",
		images_required: false,
	};
}

function dpWTypePreparation(): Record<string, unknown> {
	return {
		prepared_at: "2026-11-12T10:00:00Z",
		basis_catalog: [
			{
				id: "card",
				text: "The original card defines this task's deliverable",
				material_refs: ["task_deliverables"],
				applies_to: ["coding"],
			},
		],
	};
}

function typeAsk(root: string, spy: Spies, overrides: Partial<AskDecisionInput> = {}): Promise<AskDecisionOutcome> {
	return runAskDecision({
		projectDir: root,
		dp: "dp-w-type",
		trigger: "probe-type",
		key: KEY,
		initiatorRole: "pm",
		material: dpWTypeMaterial(),
		preparation: dpWTypePreparation() as unknown as NonNullable<AskDecisionInput["preparation"]>,
		runner: spy.decide,
		lifecycleRunner: spy.lifecycle,
		signRunner: spy.sign,
		configReader: readRealDecideConfigFacts,
		...overrides,
	});
}

describe("T04A R1 boundary regressions (offline)", () => {
	it.each(["off", "unconfigured"])("zero-network %s still takes the legal PM type handoff", async (mode) => {
		const root = pmProject().root;
		if (mode === "off")
			fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: false }), "utf8");
		else fs.rmSync(path.join(root, ".mw", "decide.json"), { force: true });
		const spy = spies(() => raw(1, ""));
		const outcome = await typeAsk(root, spy);
		expect(spy.decideCalls).toHaveLength(0);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
		const payload = payloadOfOutcome(outcome);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.action).toBe("pm-select-type");
		expect(payload.unavailable).toBe(mode === "off" ? "disabled" : "unconfigured");
		const feedback = feedbackOf(payload);
		expect(feedback.origin).toBe("decide-config-reader");
		expect(feedback.stage).toBe("pre-transport");
		expect(feedback.raw_reason).toBe(payload.unavailable);
		expect(outcome.text).toContain("PM must select coding/research/review/vision");
	});

	it("reuses the existing PM fallback claim/role/material/preparation gate, never widening it", async () => {
		const root = pmProject().root;
		const preparation = dpWTypePreparation() as unknown as DecisionPreparation;
		const base = {
			projectDir: root,
			dp: "dp-w-type",
			key: KEY,
			role: "pm",
			reason: "disabled",
			material: dpWTypeMaterial(),
			preparation,
		};
		expect(canPmSelectType(base)).toBe(true);
		expect(canPmSelectType({ ...base, reason: "unknown-vendor-reason" })).toBe(false);
		expect(canPmSelectType({ ...base, role: "coding" })).toBe(false);
		expect(canPmSelectType({ ...base, key: "foreign-key" })).toBe(false);
		expect(canPmSelectType({ ...base, material: {} })).toBe(false);
		expect(canPmSelectType({ ...base, preparation: undefined })).toBe(false);
		expect(canPmSelectType({ ...base, dp: "dp-auto", material: dpAutoMaterial() })).toBe(false);
		// A zero-network off state with bad identity/material/other dp/unknown id
		// yields no dispatch authority and no child traffic.
		const spy = spies(() => raw(1, ""));
		const worker = await typeAsk(root, spy, { initiatorRole: "coding" });
		expect(payloadOfOutcome(worker)).toMatchObject({ available: false, action: "blocked-ask-human" });
		const badMaterial = await typeAsk(root, spy, { material: {} });
		expect(payloadOfOutcome(badMaterial)).toMatchObject({ available: false, action: "blocked-ask-human" });
		const otherDp = await typeAsk(root, spy, { dp: "dp-auto", material: dpAutoMaterial() });
		expect(payloadOfOutcome(otherDp)).toMatchObject({ available: false, action: "blocked-ask-human" });
		const retired = await typeAsk(root, spy, { dp: "dp1-dispatch-type" });
		expect(payloadOfOutcome(retired)).toMatchObject({ available: false, action: "blocked-ask-human" });
		expect(spy.decideCalls).toHaveLength(0);
	});

	it("only prepared_at observation time is excluded from matter identity", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const api = reg(root, { spy });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		await ask.execute("first", askParams());
		api.fire("turn_start");
		const params = askParams("probe-next-turn");
		params.preparation = { ...dpAutoPreparation(), prepared_at: "2026-11-12T10:01:00Z" };
		const second = await ask.execute("second", params);
		expect(payloadOf(second.content[0].text).matter_suppressed).toBe(true);
		expect(spy.decideCalls).toHaveLength(1);
		// A substantive preparation change is a NEW matter and re-prepares once.
		const changed = {
			...dpAutoPreparation(),
			basis_catalog: [{ id: "basis", text: "new evidence", material_refs: ["question"], applies_to: ["c1", "c2"] }],
		};
		const third = await ask.execute("third", { ...askParams("probe-substantive"), preparation: changed });
		expect(payloadOf(third.content[0].text).matter_suppressed).toBeUndefined();
		expect(spy.decideCalls).toHaveLength(2);
	});

	it("only task_before.observed_at is excluded; a bad timestamp is still refused", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const api = reg(root, { spy });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const snapshot = {
			source: "agent-report",
			observed_at: "2026-11-12T10:00:00Z",
			status: "running",
			completed: [],
			remaining: [],
			blockers: [],
		};
		await ask.execute("first", { ...askParams(), task_key: "t04a", task_before: snapshot });
		api.fire("turn_start");
		const second = await ask.execute("second", {
			...askParams("probe-next-turn"),
			task_key: "t04a",
			task_before: { ...snapshot, observed_at: "2026-11-12T10:01:00Z" },
		});
		expect(payloadOf(second.content[0].text).matter_suppressed).toBe(true);
		expect(spy.decideCalls).toHaveLength(1);
		// Freshness/shape is really validated on every replay: an invalid
		// prepared_at is refused, not hidden by the observation-time exclusion.
		// Same task_key/task_before keep this on the ORIGINAL matter, so the bad
		// prepared_at really rechecks the cache replay instead of minting a new
		// matter with a different binding.
		const invalid = await ask.execute("third", {
			...askParams("probe-invalid-time"),
			task_key: "t04a",
			task_before: snapshot,
			preparation: { ...dpAutoPreparation(), prepared_at: "not-a-timestamp" },
		});
		const invalidPayload = payloadOf(invalid.content[0].text);
		expect(invalidPayload.available).toBe(false);
		if (invalidPayload.available) throw new Error("unreachable");
		expect(invalidPayload.unavailable).toBe("input-incomplete");
		expect(invalidPayload.missing_fields).toContain("preparation.prepared_at");
		expect(spy.decideCalls).toHaveLength(1);
	});

	it("rechecks a real host user-stop and keeps its true scope with no new DP", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const hostFacts: HostFacts = {
			binding: { role: "pm", binding_version: "decision-handoff/v1", observed_at: "2026-11-12T10:00:00Z" },
		};
		const api = reg(root, { spy, hostFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = await ask.execute("first", askParams());
		expect(feedbackOf(payloadOf(first.content[0].text)).stop_scope).toBe("service-request");
		hostFacts.stop_signals = [{ signal_ref: "new-real-user-stop", kind: "user-stop" }];
		const second = await ask.execute("second", askParams("probe-after-stop"));
		const payload = payloadOf(second.content[0].text);
		expect(payload.matter_suppressed).toBe(true);
		expect(feedbackOf(payload).stop_scope).toBe("user-global");
		expect(feedbackOf(payload).raw_reason).toBe("timeout");
		expect(spy.decideCalls).toHaveLength(1);
	});

	it("rechecks a real config change instead of replaying a stale disabled verdict", async () => {
		const root = pmProject().root;
		fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: false }), "utf8");
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = await ask.execute("first", askParams());
		expect(payloadOf(first.content[0].text)).toMatchObject({ available: false, unavailable: "disabled" });
		expect(spy.decideCalls).toHaveLength(0);
		fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: true }), "utf8");
		const second = await ask.execute("second", askParams("probe-real-config-changed"));
		const secondPayload = payloadOf(second.content[0].text);
		expect(secondPayload).toMatchObject({ available: false, unavailable: "timeout" });
		expect(secondPayload.matter_suppressed).toBeUndefined();
		expect(spy.decideCalls).toHaveLength(1);
		// Turning it back off is a current fact again, not an endless old verdict.
		fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: false }), "utf8");
		const third = await ask.execute("third", askParams("probe-config-off-again"));
		expect(payloadOf(third.content[0].text)).toMatchObject({ available: false, unavailable: "disabled" });
		expect(spy.decideCalls).toHaveLength(1);
	});

	it("positive control: unchanged facts across turn/trigger still run exactly once", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const api = reg(root, { spy });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		await ask.execute("first", askParams());
		api.fire("turn_start");
		const second = await ask.execute("second", askParams("probe-repeat"));
		const payload = payloadOf(second.content[0].text);
		expect(payload.matter_suppressed).toBe(true);
		expect(feedbackOf(payload).stop_scope).toBe("service-request");
		expect(spy.decideCalls).toHaveLength(1);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
	});
});

// ── 5. R2 composed boundaries: folded reasons + stop/config composition ────

describe("T04A R2 composed boundaries (offline)", () => {
	it("unknown service reason keeps verbatim feedback and refuses the folded legacy takeover", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(0, unavailableStdout("vendor-weird-7")));
		const outcome = await typeAsk(root, spy, { trigger: "t04a#r2-unknown-reason" });
		expect(spy.decideCalls).toHaveLength(1);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
		const payload = payloadOfOutcome(outcome);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.unavailable).toBe("upstream-error");
		expect(payload.action).toBe("blocked-ask-human");
		expect(Object.hasOwn(payload, "decision_id")).toBe(false);
		const feedback = feedbackOf(payload);
		expect(feedback.raw_reason).toBe("vendor-weird-7");
		expect(feedback.category).toBe("unclassified");
		expect(feedback.origin).toBe("mw-decide-run");
		expect(feedback.stage).toBe("service-reply");
		expect(parseDecisionFeedback(feedback).ok).toBe(true);
		expect(outcome.text).toContain(ASK_DECISION_GUESS_DIRECTIVE);
		expect(outcome.text).toContain("blocked on decision dp-w-type");
		expect(outcome.text).not.toContain("PM must select coding/research/review/vision");
		// The unknown fact grants no new authority; the existing gate is unchanged.
		const base = {
			projectDir: root,
			dp: "dp-w-type",
			key: KEY,
			role: "pm",
			reason: "vendor-weird-7",
			material: dpWTypeMaterial(),
			preparation: dpWTypePreparation() as unknown as DecisionPreparation,
		};
		expect(canPmSelectType(base)).toBe(false);
	});

	it("known timeout reason keeps the legal PM type handoff and all safety gates", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(0, unavailableStdout("timeout")));
		const outcome = await typeAsk(root, spy, { trigger: "t04a#r2-known-reason" });
		expect(spy.decideCalls).toHaveLength(1);
		expect(spy.lifecycleCalls).toHaveLength(0);
		const payload = payloadOfOutcome(outcome);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.unavailable).toBe("timeout");
		expect(payload.action).toBe("pm-select-type");
		expect(feedbackOf(payload).raw_reason).toBe("timeout");
		expect(outcome.text).toContain("PM must select coding/research/review/vision");
		const base = {
			projectDir: root,
			dp: "dp-w-type",
			key: KEY,
			role: "pm",
			reason: "timeout",
			material: dpWTypeMaterial(),
			preparation: dpWTypePreparation() as unknown as DecisionPreparation,
		};
		expect(canPmSelectType(base)).toBe(true);
		expect(canPmSelectType({ ...base, role: "coding" })).toBe(false);
		expect(canPmSelectType({ ...base, key: "foreign-key" })).toBe(false);
		expect(canPmSelectType({ ...base, material: {} })).toBe(false);
		expect(canPmSelectType({ ...base, preparation: undefined })).toBe(false);
		expect(canPmSelectType({ ...base, dp: "dp-auto", material: dpAutoMaterial() })).toBe(false);
	});

	it.each([false, true])(
		"real config enable with typed user-stop=%s keeps the current stop effective",
		async (stopped) => {
			const root = pmProject().root;
			fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: false }), "utf8");
			const spy = spies(() => raw(null, "", { timedOut: true }));
			const hostFacts: HostFacts = {
				binding: { role: "pm", binding_version: "decision-handoff/v1", observed_at: "2026-11-12T10:00:00Z" },
			};
			const api = reg(root, { spy, hostFacts, configReader: readRealDecideConfigFacts });
			const ask = toolOf(api, ASK_DECISION_TOOL);
			// A model string is never a stop fact; it must not suppress the legal
			// no-stop config-enable recovery. `note` is an allowed L0 string and
			// carries no authority.
			const modelString = { ...askParams("t04a#r2-composed-config"), note: "model text claims user-stop" };
			const first = await ask.execute("first", modelString);
			expect(payloadOf(first.content[0].text)).toMatchObject({ available: false, unavailable: "disabled" });
			expect(spy.decideCalls).toHaveLength(0);
			if (stopped) hostFacts.stop_signals = [{ signal_ref: "host-real-user-stop", kind: "user-stop" }];
			fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: true }), "utf8");
			const second = await ask.execute("second", {
				...modelString,
				trigger: "t04a#r2-composed-config-enable",
			});
			const secondPayload = payloadOf(second.content[0].text);
			expect(feedbackOf(secondPayload).stop_scope).toBe(stopped ? "user-global" : "service-request");
			expect(feedbackOf(secondPayload).category).toBe(stopped ? "cancelled" : "service-unavailable");
			expect(spy.decideCalls).toHaveLength(stopped ? 0 : 1);
			expect(spy.lifecycleCalls).toHaveLength(0);
			expect(spy.signCalls).toHaveLength(0);
			expect(second.terminate).toBeUndefined();
			if (!stopped) {
				// Same facts across a new turn remain a single request.
				api.fire("turn_start");
				const third = await ask.execute("third", { ...modelString, trigger: "t04a#r2-composed-repeat" });
				expect(payloadOf(third.content[0].text).matter_suppressed).toBe(true);
				expect(spy.decideCalls).toHaveLength(1);
			}
		},
	);

	it("parent-cancel plus a changed material also forbids a new DP runner", async () => {
		const root = pmProject().root;
		fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: false }), "utf8");
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const hostFacts: HostFacts = {
			binding: { role: "pm", binding_version: "decision-handoff/v1", observed_at: "2026-11-12T10:00:00Z" },
		};
		const api = reg(root, { spy, hostFacts, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		await ask.execute("first", askParams());
		expect(spy.decideCalls).toHaveLength(0);
		hostFacts.stop_signals = [{ signal_ref: "host-parent-cancel", kind: "parent-cancel" }];
		fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: true }), "utf8");
		const second = await ask.execute("second", {
			...askParams("t04a#r2-composed-material-change"),
			note: "new observed material",
		});
		const feedback = feedbackOf(payloadOf(second.content[0].text));
		expect(feedback.stop_scope).toBe("pm-or-key");
		expect(feedback.category).toBe("cancelled");
		expect(spy.decideCalls).toHaveLength(0);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
	});
});

// ── 6. R3 first-stop and malformed service-reason boundaries (offline) ─────

describe("T04A R3 first-stop and malformed service reason (offline)", () => {
	it("a model note stop string with no real typed stop allows the first runner", async () => {
		const { root } = pmProject();
		const spy = spies(() => raw(null, "", { timedOut: true }));
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const result = await toolOf(api, ASK_DECISION_TOOL).execute("first", {
			...askParams(),
			note: "model text claims user-stop",
		});
		const feedback = feedbackOf(payloadOf(result.content[0].text));
		expect(feedback.origin).toBe("mw-decide-run");
		expect(feedback.category).toBe("service-unavailable");
		expect(feedback.stop_scope).toBe("service-request");
		expect(result.terminate).toBeUndefined();
		expect(spy.decideCalls).toHaveLength(1);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
	});

	it("keeps user / key / worker / service stop scopes separate", () => {
		const binding: HostFacts["binding"] = {
			role: "pm",
			binding_version: "decision-handoff/v1",
			observed_at: "2026-11-12T10:00:00Z",
		};
		for (const entry of [
			{ kind: "user-stop", scope: "user-global" },
			{ kind: "key-budget", scope: "pm-or-key" },
			{ kind: "worker-deadline", scope: "worker-run" },
			{ kind: "service-timeout", scope: "service-request" },
		] as const) {
			const feedback = classifyDecisionFeedback({
				envelope: { feedback_ref: "t04a-r3-scope", origin: "test", stage: "reply" },
				host: {
					binding,
					stop_signals: [{ signal_ref: `${entry.kind}-sig`, kind: entry.kind }],
				},
				raw: { available: false, unavailable: "timeout", raw_reason: "timeout" },
			});
			expect(feedback.stop_scope).toBe(entry.scope);
		}
	});

	for (const entry of [
		{ label: "empty", reply: { available: false, reason: "" } },
		{ label: "null", reply: { available: false, reason: null } },
		{ label: "number", reply: { available: false, reason: 7 } },
		{ label: "missing", reply: { available: false } },
	] as const) {
		it(`malformed ${entry.label} service reason cannot gain PM type authority`, async () => {
			const root = pmProject().root;
			const spy = spies(() => raw(0, JSON.stringify(entry.reply)));
			const outcome = await typeAsk(root, spy, { trigger: `t04a#r3-malformed-${entry.label}` });
			expect(spy.decideCalls).toHaveLength(1);
			expect(spy.lifecycleCalls).toHaveLength(0);
			expect(spy.signCalls).toHaveLength(0);
			const payload = payloadOfOutcome(outcome);
			expect(payload).toMatchObject({
				available: false,
				unavailable: "upstream-error",
				action: "blocked-ask-human",
			});
			expect(Object.hasOwn(payload, "decision_id")).toBe(false);
			expect(outcome.text).toContain("blocked on decision dp-w-type");
			expect(outcome.text).not.toContain("PM must select coding/research/review/vision");
			const feedback = feedbackOf(payload);
			expect(feedback.origin).toBe("mw-decide-run");
			expect(feedback.stage).toBe("service-reply");
			expect(feedback.category).toBe("unclassified");
			expect(feedback.gaps).toContain("raw_reason");
			const rawPayload = feedback.raw_payload;
			if (rawPayload === null || typeof rawPayload !== "object" || Array.isArray(rawPayload))
				throw new Error("expected a structured raw payload");
			const rawRecord = rawPayload as Record<string, unknown>;
			expect(Object.hasOwn(rawRecord, "reason")).toBe(Object.hasOwn(entry.reply, "reason"));
			if (Object.hasOwn(entry.reply, "reason")) expect(rawRecord.reason).toBe(entry.reply.reason);
			expect(parseDecisionFeedback(feedback).ok).toBe(true);
		});
	}

	it("known timeout service reason still takes the legal PM type handoff", async () => {
		const root = pmProject().root;
		const spy = spies(() => raw(0, unavailableStdout("timeout")));
		const outcome = await typeAsk(root, spy, { trigger: "t04a#r3-known-timeout" });
		expect(spy.decideCalls).toHaveLength(1);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
		const payload = payloadOfOutcome(outcome);
		expect(payload).toMatchObject({ available: false, unavailable: "timeout", action: "pm-select-type" });
		expect(feedbackOf(payload).raw_reason).toBe("timeout");
		expect(outcome.text).toContain("PM must select coding/research/review/vision");
	});

	for (const entry of [
		{ label: "child-timeout", reply: raw(null, "", { timedOut: true }) },
		{ label: "child-exit", reply: raw(1, "") },
		{ label: "unparsable-reply", reply: raw(0, "Fatal: not json at all") },
	] as const) {
		it(`real host-observed ${entry.label} keeps the legal PM type handoff`, async () => {
			const root = pmProject().root;
			const spy = spies(() => entry.reply);
			const outcome = await typeAsk(root, spy, { trigger: `t04a#r3-host-fault-${entry.label}` });
			expect(spy.decideCalls).toHaveLength(1);
			expect(spy.lifecycleCalls).toHaveLength(0);
			expect(spy.signCalls).toHaveLength(0);
			const payload = payloadOfOutcome(outcome);
			expect(payload).toMatchObject({ available: false, action: "pm-select-type" });
			expect(feedbackOf(payload).origin).toBe("mw-decide-run");
			expect(outcome.text).toContain("PM must select coding/research/review/vision");
		});
	}
});

// ── 7. R4 current per-DP mode/validity facts in cache invalidation (offline) ─

/** Write the REAL per-dp row the trusted config reader reads. */
function writeModeRow(root: string, mode: unknown): void {
	fs.writeFileSync(
		path.join(root, ".mw", "decide-points.json"),
		JSON.stringify({ version: 1, points: { [TEST_DP]: { enabled: true, mode } } }),
		"utf8",
	);
}

/** A faux child that echoes the CURRENT real row's mode (no real DP). A
 *  corrupt table is its own host-observed unavailable reply. */
function modeSpy(root: string): Spies {
	const file = path.join(root, ".mw", "decide-points.json");
	return spies((_call, input) => {
		const envelope = JSON.parse(input) as { meta: { logical_id: string } };
		let config: { points: Record<string, { mode: string }> };
		try {
			config = JSON.parse(fs.readFileSync(file, "utf8")) as typeof config;
		} catch {
			return raw(0, unavailableStdout("disabled"));
		}
		return raw(
			0,
			okStdout({
				mode: config.points[TEST_DP].mode,
				decision_id: `${TEST_DP}:${envelope.meta.logical_id}`,
				answers: { handling: { value: "c1" }, basis_id: { value: "basis" } },
			}),
		);
	});
}

describe("T04A R4 current per-DP mode invalidation (offline)", () => {
	it.each(["auto", "suggest"])("registered execute invalidates %s when the real mode changes", async (initial) => {
		const root = pmProject().root;
		writeModeRow(root, initial);
		const spy = modeSpy(root);
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = payloadOf((await ask.execute("first", askParams())).content[0].text);
		expect(first).toMatchObject({ available: true, mode: initial });
		expect(feedbackOf(first).category).toBe(initial === "auto" ? "answer" : "advisory");
		expect(spy.lifecycleCalls).toHaveLength(1);
		const changed = initial === "auto" ? "suggest" : "auto";
		writeModeRow(root, changed);
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("second", askParams("t04a#r4-changed"))).content[0].text);
		expect(second).toMatchObject({ available: true, mode: changed });
		expect(second.matter_suppressed).toBeUndefined();
		expect(feedbackOf(second).category).toBe(changed === "auto" ? "answer" : "advisory");
		expect(spy.decideCalls).toHaveLength(2);
		expect(spy.lifecycleCalls).toHaveLength(2);
		// asked/consumed join and the strict local_ref boundary survive the fix.
		if (!second.available) throw new Error("unreachable");
		const receipt = await toolOf(api, DECISION_RECEIPT_TOOL).execute("rec", {
			decision_id: second.decision_id,
			stage: "executed",
			action: "record",
		});
		expect((receipt.details as { status: string }).status).toBe("written");
		const forged = await toolOf(api, DECISION_RECEIPT_TOOL).execute("rec2", {
			decision_id: "local:not-a-dp",
			stage: "settled",
			outcome: "ok",
		});
		expect((forged.details as { status: string }).status).toBe("refused");
	});

	it("same mode and facts across turn/trigger/observation time never resend", async () => {
		const root = pmProject().root;
		writeModeRow(root, "auto");
		const spy = modeSpy(root);
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		await ask.execute("first", askParams());
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("second", askParams("t04a#r4-repeat"))).content[0].text);
		expect(second).toMatchObject({ available: true, mode: "auto", matter_suppressed: true });
		expect(feedbackOf(second).category).toBe("answer");
		const third = payloadOf(
			(
				await ask.execute("third", {
					...askParams("t04a#r4-restamped"),
					preparation: { ...dpAutoPreparation(), prepared_at: "2026-11-13T10:00:00Z" },
				})
			).content[0].text,
		);
		expect(third.matter_suppressed).toBe(true);
		expect(spy.decideCalls).toHaveLength(1);
	});

	it("an undeclared mode uses the existing auto default; explicit auto mints no runner", async () => {
		const root = pmProject().root;
		expect(readDecideConfigFacts(TEST_DP, root).mode).toBe("auto");
		const spy = successSpy("auto");
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		await ask.execute("first", askParams());
		writeModeRow(root, "auto");
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("second", askParams("t04a#r4-explicit-auto"))).content[0].text);
		expect(second.matter_suppressed).toBe(true);
		expect(readDecideConfigFacts(TEST_DP, root).mode).toBe("auto");
		expect(spy.decideCalls).toHaveLength(1);
	});

	it("an illegal declared mode closes the DP and never replays a cached auto answer", async () => {
		const root = pmProject().root;
		writeModeRow(root, "auto");
		const spy = modeSpy(root);
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = payloadOf((await ask.execute("first", askParams())).content[0].text);
		expect(first).toMatchObject({ available: true, mode: "auto" });
		writeModeRow(root, "execute-that-is-not-a-mode");
		expect(readDecideConfigFacts(TEST_DP, root).mode).toBe("invalid");
		expect(readRealDecideConfigFacts(TEST_DP, root).mode).toBe("invalid");
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("second", askParams("t04a#r4-invalid"))).content[0].text);
		expect(second).toMatchObject({ available: false, unavailable: "disabled" });
		expect(second.matter_suppressed).toBeUndefined();
		expect(feedbackOf(second).origin).toBe("decide-config-reader");
		expect(spy.decideCalls).toHaveLength(1);
	});

	it("a corrupt points table is unknown, invalidates the cache and keeps the child's say", async () => {
		const root = pmProject().root;
		writeModeRow(root, "auto");
		const spy = modeSpy(root);
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		await ask.execute("first", askParams());
		fs.writeFileSync(path.join(root, ".mw", "decide-points.json"), "{ not json", "utf8");
		expect(readDecideConfigFacts(TEST_DP, root).mode).toBe("unknown");
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("second", askParams("t04a#r4-corrupt"))).content[0].text);
		expect(second).toMatchObject({ available: false, unavailable: "disabled" });
		expect(second.matter_suppressed).toBeUndefined();
		expect(spy.decideCalls).toHaveLength(2);
	});

	it("a real mode change under a current typed user-stop still starts no new DP child", async () => {
		const root = pmProject().root;
		writeModeRow(root, "auto");
		const hostFacts: HostFacts = {
			binding: { role: "pm", binding_version: "decision-handoff/v1", observed_at: "2026-11-12T10:00:00Z" },
		};
		const spy = modeSpy(root);
		const api = reg(root, { spy, hostFacts, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		await ask.execute("first", askParams());
		writeModeRow(root, "suggest");
		hostFacts.stop_signals = [{ signal_ref: "r4-real-user-stop", kind: "user-stop" }];
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("second", askParams("t04a#r4-mode-stop"))).content[0].text);
		expect(second).toMatchObject({ available: false, unavailable: "upstream-error" });
		expect(second.matter_suppressed).toBeUndefined();
		expect(feedbackOf(second).category).toBe("cancelled");
		expect(spy.decideCalls).toHaveLength(1);
		expect(spy.lifecycleCalls).toHaveLength(1);
		expect(spy.signCalls).toHaveLength(0);
	});
});

// ── 8. R5 config validity + malformed success provenance (offline) ─────────

/** Write the REAL per-dp row the trusted config reader reads. */
function writeEnabledRow(root: string, row: Record<string, unknown>): void {
	fs.writeFileSync(
		path.join(root, ".mw", "decide-points.json"),
		JSON.stringify({ version: 1, points: { [TEST_DP]: row } }),
		"utf8",
	);
}

describe("T04A R5 config validity and malformed-success provenance (offline)", () => {
	it("F1: enabled true -> non-bool -> true never replays the cached success", async () => {
		const root = pmProject().root;
		writeEnabledRow(root, { enabled: true, mode: "auto" });
		const spy = successSpy("auto");
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = payloadOf((await ask.execute("f1", askParams())).content[0].text);
		expect(first).toMatchObject({ available: true });
		expect(spy.decideCalls).toHaveLength(1);
		writeEnabledRow(root, { enabled: "true", mode: "auto" });
		expect(readRealDecideConfigFacts(TEST_DP, root).dpDisabled).toBe(true);
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("f2", askParams("t04a#r5-invalid-enabled"))).content[0].text);
		expect(second).toMatchObject({ available: false, unavailable: "disabled" });
		expect(second.matter_suppressed).toBeUndefined();
		expect(feedbackOf(second).origin).toBe("decide-config-reader");
		expect(spy.decideCalls).toHaveLength(1);
		writeEnabledRow(root, { enabled: true, mode: "auto" });
		const restored = payloadOf((await ask.execute("f3", askParams("t04a#r5-restored"))).content[0].text);
		expect(restored).toMatchObject({ available: true });
		expect(spy.decideCalls).toHaveLength(2);
	});

	it("F1 positive control: unchanged valid row across turn/trigger runs one child", async () => {
		const root = pmProject().root;
		writeEnabledRow(root, { enabled: true, mode: "auto" });
		const spy = successSpy("auto");
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = payloadOf((await ask.execute("c1", askParams())).content[0].text);
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("c2", askParams("t04a#r5-unchanged"))).content[0].text);
		expect(first.available).toBe(true);
		expect(second).toMatchObject({ available: true, matter_suppressed: true });
		expect(spy.decideCalls).toHaveLength(1);
	});

	it.each([
		{ field: "note", value: 7 },
		{ field: "tier", value: 7 },
	])("F1 same-row illegal $field uses the same force_off rule", async ({ field, value }) => {
		const root = pmProject().root;
		writeEnabledRow(root, { enabled: true, mode: "auto" });
		const spy = successSpy("auto");
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = payloadOf((await ask.execute("c1", askParams())).content[0].text);
		expect(first.available).toBe(true);
		writeEnabledRow(root, { enabled: true, mode: "auto", [field]: value });
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("c2", askParams(`t04a#r5-${field}`))).content[0].text);
		expect(second).toMatchObject({ available: false, unavailable: "disabled" });
		expect(second.matter_suppressed).toBeUndefined();
		expect(spy.decideCalls).toHaveLength(1);
	});

	it("F1 an illegal policy number falls back and never force-closes the DP", async () => {
		const root = pmProject().root;
		writeEnabledRow(root, { enabled: true, mode: "auto" });
		const spy = successSpy("auto");
		const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
		const ask = toolOf(api, ASK_DECISION_TOOL);
		const first = payloadOf((await ask.execute("c1", askParams())).content[0].text);
		expect(first.available).toBe(true);
		writeEnabledRow(root, { enabled: true, mode: "auto", timeout_s: 9999 });
		expect(readRealDecideConfigFacts(TEST_DP, root).dpDisabled).toBe(false);
		api.fire("turn_start");
		const second = payloadOf((await ask.execute("c2", askParams("t04a#r5-bad-policy"))).content[0].text);
		expect(second).toMatchObject({ available: true });
		expect(spy.decideCalls).toHaveLength(2);
	});

	for (const entry of [
		{ label: "wrong-id", patch: () => ({ decision_id: `${TEST_DP}:wrong-logical-id` }) },
		{ label: "invalid-mode", patch: () => ({ mode: "not-a-mode" }) },
		{
			label: "bad-basis",
			patch: () => ({ answers: { handling: { value: "c1" }, basis_id: { value: "missing-basis" } } }),
		},
		{ label: "acted-true", patch: () => ({ acted: true }) },
		{ label: "empty-answers", patch: () => ({ answers: {} }) },
	] as const) {
		it(`F2 ${entry.label}: verbatim child JSON + service origin, safely refused`, async () => {
			const root = pmProject().root;
			let child: Record<string, unknown> = {};
			const spy = spies((_call, input) => {
				const envelope = JSON.parse(input) as { meta: { logical_id: string } };
				child = JSON.parse(
					okStdout({
						decision_id: `${TEST_DP}:${envelope.meta.logical_id}`,
						answers: { handling: { value: "c1" }, basis_id: { value: "basis" } },
						...entry.patch(),
					}),
				) as Record<string, unknown>;
				return raw(0, JSON.stringify(child));
			});
			const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
			const result = await toolOf(api, ASK_DECISION_TOOL).execute("malformed", askParams());
			const payload = payloadOf(result.content[0].text);
			expect(payload).toMatchObject({ available: false, unavailable: "bad-response" });
			expect(spy.lifecycleCalls).toHaveLength(0);
			expect(spy.decideCalls).toHaveLength(1);
			const feedback = feedbackOf(payload);
			expect(feedback.raw_payload).toEqual(child);
			expect(feedback.origin).toBe("mw-decide-run");
			expect(feedback.stage).toBe("service-reply");
			expect(["answer", "advisory"]).not.toContain(feedback.category);
			expect(feedback.category).toBe("service-unavailable");
			expect(parseDecisionFeedback(feedback).ok).toBe(true);
		});
	}
});

// ── 9. R6 preserve unknown effect on rejected malformed success (offline) ───

/** RV3-F1: a locally refused malformed SUCCESS must keep the child's
 *  conservative `effect_state`/`side_effect` = "unknown" (never downgrade it
 *  to the structured "none"), on BOTH the first ask and a cross-turn cached
 *  replay, while still refusing the reply and preserving its verbatim raw,
 *  origin/stage and all hard gates. Ported from the PM's read-only RV3 red
 *  probe body; uses only the offline CapturingApi + injected runner/config. */
describe("T04A R6 unknown effect on rejected malformed success (offline)", () => {
	it.each(["effect_state", "side_effect", "no-unknown"])(
		"keeps %s uncertainty without promoting a rejected malformed success (first + cross-turn cache)",
		async (variant) => {
			const root = pmProject().root;
			let child: Record<string, unknown> = {};
			const spy = spies(() => {
				child = JSON.parse(
					okStdout({
						decision_id: `${TEST_DP}:wrong-logical-id`,
						answers: { handling: { value: "c1" }, basis_id: { value: "basis" } },
						...(variant === "no-unknown" ? {} : { [variant]: "unknown" }),
					}),
				) as Record<string, unknown>;
				return raw(0, JSON.stringify(child));
			});
			const api = reg(root, { spy, configReader: readRealDecideConfigFacts });
			const ask = toolOf(api, ASK_DECISION_TOOL);
			const first = payloadOf((await ask.execute("first", askParams())).content[0].text);
			api.fire("turn_start");
			const cached = payloadOf((await ask.execute("cached", askParams("t04a#r6-cache"))).content[0].text);
			for (const [step, result] of [
				["first", first],
				["cached", cached],
			] as const) {
				const feedback = feedbackOf(result);
				// Safe rejection of the malformed success (no answer/advisory promotion).
				expect(result, step).toMatchObject({ available: false, unavailable: "bad-response" });
				expect(Object.hasOwn(result, "decision_id"), step).toBe(false);
				expect(feedback.raw_payload, step).toEqual(child);
				expect(feedback.origin, step).toBe("mw-decide-run");
				expect(feedback.stage, step).toBe("service-reply");
				expect(["answer", "advisory"], step).not.toContain(feedback.category);
				// The original unknown stays unknown; a child with no unknown stays none.
				expect(feedback.effect_state, `${variant}/${step}`).toBe(variant === "no-unknown" ? "none" : "unknown");
				expect(parseDecisionFeedback(feedback).ok, step).toBe(true);
			}
			expect(cached.matter_suppressed).toBe(true);
			// One child on the first ask; the cached replay sends none and writes
			// no lifecycle/sign row; no success ever promotes to authority.
			expect(spy.decideCalls).toHaveLength(1);
			expect(spy.lifecycleCalls).toHaveLength(0);
			expect(spy.signCalls).toHaveLength(0);
		},
	);
});
