/**
 * decision-tool.test.ts — `ask_decision` payload/failure contract
 * (mw-decision-substitution T-05, spec AC-004/AC-005/AC-013/AC-015; QG MAJOR-1
 * / MAJOR-2 fix FIX-A).
 *
 * R1 migration: the retired dp1/dp2/dp3/dp25/dp12/dp4 fixtures and the 25-id
 * parity assertions are migrated to the EIGHT active registry entries with
 * legal material + separately prepared basis. No scenario is dropped: success
 * (verbatim four-key passthrough), suggest, missing authority keys, structured
 * state, material budget, sign CLI refusal, unavailable/escalated reasons,
 * timeout (real child kill), unparsable stdout, retired/unknown ids (zero
 * spawn), anti-retry breaker, registration wiring, registry parity and argv /
 * child cleanup are all still covered. The frozen payload shape, the D-036
 * single authority and the strict lifecycle join stay unchanged.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	ASK_DECISION_DP_IDS,
	ASK_DECISION_ENFORCED_STATE_DP_IDS,
	ASK_DECISION_GUESS_DIRECTIVE,
	ASK_DECISION_MATERIAL_DP_IDS,
	ASK_DECISION_MAX_BLOCKED_PER_TURN,
	ASK_DECISION_MAX_STATE_BYTES,
	ASK_DECISION_TOOL,
	type AskDecisionInput,
	type AskDecisionPayload,
	buildDecideArgv,
	buildDecisionState,
	DECISION_RECEIPT_TOOL,
	type DecideRunner,
	type DecideRunRequest,
	type LifecycleRunner,
	missingDecisionStateFields,
	parseDecisionJson,
	type RawDecideResult,
	registerAskDecisionTool,
	runAskDecision,
	runDecideMw,
	type SignRequest,
	type SignRunner,
	spawnWithTimeout,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import type { DecisionPreparation } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";

// ── temp isolated projects ──────────────────────────────────────────────────

function registryFields(dp: string): string[] {
	return [...(DECIDE_REGISTRY[dp]?.requiredStateFields ?? [])].map((field) => field.name);
}

const tempDirs: string[] = [];

function makeTempDir(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

/** Write `.mw/decide-points.json` — a config table the tool only uses for real
 *  pre-transport facts, never as a second authorization authority (D-036). */
function writePoints(projectDir: string, points: Record<string, unknown>): void {
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(
		path.join(projectDir, ".mw", "decide-points.json"),
		`${JSON.stringify({ version: 1, updated_by: "test", points })}\n`,
		"utf8",
	);
}

/** A PM project with one real self-active claim (all eight entries are PM/worker
 *  role-gated, so registered calls need a live claim). */
function makePmProject(prefix: string): string {
	const projectDir = makeTempDir(prefix);
	fs.mkdirSync(path.join(projectDir, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(projectDir, ".mw", "decide.json"), JSON.stringify({ enabled: true }), "utf8");
	fs.writeFileSync(
		path.join(projectDir, ".agenticdoc", "_index.parallel"),
		`| fallback | active | EXECUTE | ${currentClaimId()} | — | fixture | now |\n`,
		"utf8",
	);
	return projectDir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) {
		try {
			fs.rmSync(dir, { recursive: true, force: true });
		} catch {
			// Best effort.
		}
	}
});

// ── legal eight-DP material / preparation ───────────────────────────────────

/** One active, dynamic-candidate PM entry: its child answer joins the envelope
 *  meta by `<dp>:<logical_id>` and names a real prepared basis. */
const TEST_DP = "dp-auto";

function activeMaterial(): Record<string, unknown> {
	return {
		question: "Which option should the PM take?",
		background: {
			task_goal: "verify the decision tool contract",
			current_state: "offline fixture child",
			tried: "no real DP call",
			unknowns: "none in this unit fixture",
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

function activePreparation(): DecisionPreparation {
	return {
		prepared_at: "2026-11-12T10:00:00Z",
		basis_catalog: [
			{
				id: "basis",
				text: "The child's handling answer is checked against the prepared basis",
				material_refs: ["question"],
				applies_to: ["c1", "c2"],
			},
		],
	};
}

function signMaterial(): Record<string, unknown> {
	return {
		delivery_goal: "goal",
		actual_completion: "completion",
		verification_evidence: { verified: [], unverified: [] },
		unfinished_impact: ["one gap"],
	};
}

function signPreparation(): DecisionPreparation {
	return {
		prepared_at: "2026-11-12T10:00:00Z",
		basis_catalog: [
			{
				id: "sign-basis",
				text: "The delivery goal is the prepared basis",
				material_refs: ["delivery_goal"],
				applies_to: ["finalize", "continue", "user-confirm"],
			},
		],
	};
}

/** A real (offline) lifecycle runner: the material path always writes
 *  `consumed` through the single writer, so no test spawns a Python child. */
const fakeLifecycle: LifecycleRunner = async () => ({
	status: 0,
	stdout: JSON.stringify({ recorded: true, status: "written" }),
	stderr: "",
	timedOut: false,
});

// ── fakes ───────────────────────────────────────────────────────────────────

interface CapturedTool {
	name: string;
	parameters: unknown;
	executionMode?: string;
	promptGuidelines?: string[];
	execute: (
		toolCallId: string,
		params: Record<string, unknown>,
		signal?: AbortSignal,
	) => Promise<{
		content: Array<{ type: "text"; text: string }>;
		details: unknown;
		terminate?: boolean;
	}>;
}

type CapturedHandler = (event: unknown, ctx: unknown) => unknown;

class CapturingApi {
	readonly tools = new Map<string, CapturedTool>();
	readonly handlers = new Map<string, CapturedHandler[]>();
	active: string[] = [];

	registerTool(tool: unknown): void {
		const captured = tool as CapturedTool;
		this.tools.set(captured.name, captured);
	}

	on(event: string, handler: CapturedHandler): void {
		const list = this.handlers.get(event) ?? [];
		list.push(handler);
		this.handlers.set(event, list);
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

function api(): { capture: CapturingApi; pi: ExtensionAPI } {
	const capture = new CapturingApi();
	return { capture, pi: capture as unknown as ExtensionAPI };
}

function toolOf(capture: CapturingApi, name: string): CapturedTool {
	const tool = capture.tools.get(name);
	if (tool === undefined) throw new Error(`tool '${name}' was not registered`);
	return tool;
}

function enumValues(schema: unknown): string[] {
	const value = schema as { anyOf?: Array<{ const?: unknown }>; enum?: unknown; const?: unknown };
	if (Array.isArray(value.anyOf)) return value.anyOf.map((entry) => String(entry.const));
	if (Array.isArray(value.enum)) return value.enum.map((entry) => String(entry));
	if (value.const !== undefined) return [String(value.const)];
	return [];
}

function dpEnumOf(tool: CapturedTool): string[] {
	const parameters = tool.parameters as { properties?: Record<string, unknown> };
	return enumValues(parameters.properties?.dp);
}

type FakeReply = RawDecideResult | ((request: DecideRunRequest) => RawDecideResult);

function fakeRunner(reply: FakeReply): { calls: DecideRunRequest[]; runner: DecideRunner } {
	const calls: DecideRunRequest[] = [];
	return {
		calls,
		runner: async (request: DecideRunRequest) => {
			calls.push(request);
			return typeof reply === "function" ? reply(request) : reply;
		},
	};
}

/** The child's id is derived by Python from the envelope meta
 * (`Trigger.resolved_id`), never from the tool's `trigger` label. */
function okStdout(overrides: Record<string, unknown> = {}, logicalId = "fixed"): string {
	return JSON.stringify({
		available: true,
		file_evidence: [],
		confidence_source: "api",
		latency_ms: 1420,
		answers: { handling: { value: "c1" }, basis_id: { value: "basis" } },
		reason: null,
		decision_id: `${TEST_DP}:${logicalId}`,
		mode: "auto",
		acted: false,
		escalated_reason: null,
		...overrides,
	});
}

function okReply(overrides: Record<string, unknown> = {}): (request: DecideRunRequest) => RawDecideResult {
	return (request) => {
		const envelope = JSON.parse(request.input) as { meta: { logical_id: string } };
		return { status: 0, stdout: okStdout(overrides, envelope.meta.logical_id), stderr: "", timedOut: false };
	};
}

function unavailableStdout(reason: string, escalated?: string): string {
	return JSON.stringify({
		available: false,
		confidence_source: "unknown",
		latency_ms: 30,
		answers: null,
		reason,
		decision_id: `${TEST_DP}:child`,
		mode: "auto",
		acted: false,
		escalated_reason: escalated ?? null,
	});
}

function raw(status: number | null, stdout: string, overrides: Partial<RawDecideResult> = {}): RawDecideResult {
	return { status, stdout, stderr: "", timedOut: false, ...overrides };
}

function firstLine(text: string): string {
	return text.split("\n")[0] ?? "";
}

function parseText(text: string): AskDecisionPayload {
	return JSON.parse(firstLine(text)) as AskDecisionPayload;
}

function expectUnavailableText(text: string, reason: string): AskDecisionPayload {
	const payload = parseText(text);
	expect(payload.available).toBe(false);
	if (payload.available) throw new Error("unreachable");
	expect(payload.unavailable).toBe(reason);
	expect(payload.action).toBe("blocked-ask-human");
	expect(text).toContain(ASK_DECISION_GUESS_DIRECTIVE);
	return payload;
}

/** One legal ask with all eight-DP material/identity facts supplied. */
function baseAsk(
	projectDir: string,
	runner: DecideRunner,
	overrides: Partial<AskDecisionInput> = {},
): ReturnType<typeof runAskDecision> {
	return runAskDecision({
		projectDir,
		dp: TEST_DP,
		trigger: "ds-t05-ask-tool#ckpt1",
		note: "test failure in decision-tool.test.ts",
		taskKey: "ds-t05-ask-tool",
		initiatorRole: "pm",
		key: "mw-decision-tool",
		material: activeMaterial(),
		preparation: activePreparation(),
		runner,
		lifecycleRunner: fakeLifecycle,
		...overrides,
	});
}

function askParams(trigger = "ds-t05-ask-tool"): Record<string, unknown> {
	return { dp: TEST_DP, trigger, key: "fallback", material: activeMaterial(), preparation: activePreparation() };
}

// ── 1. success: verbatim four-key passthrough ───────────────────────────────

describe("ask_decision success", () => {
	it("passes the child's decision_id/mode/acted through verbatim, whatever the table says", async () => {
		const cleanDir = makeTempDir("mw-ask-ok-");
		const tableDir = makeTempDir("mw-ask-ok-table-");
		writePoints(tableDir, { [TEST_DP]: { enabled: false, mode: "suggest" } });
		const corruptDir = makeTempDir("mw-ask-ok-corrupt-");
		fs.mkdirSync(path.join(corruptDir, ".mw"), { recursive: true });
		fs.writeFileSync(path.join(corruptDir, ".mw", "decide-points.json"), "{ not json", "utf8");

		for (const projectDir of [cleanDir, tableDir, corruptDir]) {
			const { calls, runner } = fakeRunner(okReply());
			const outcome = await baseAsk(projectDir, runner);
			expect(outcome.spawned).toBe(true);
			expect(calls).toHaveLength(1);
			const payload = parseText(outcome.text);
			const request = calls[0];
			expect(request.projectDir).toBe(projectDir);
			expect(request.dp).toBe(TEST_DP);
			expect(request.viaStdin).toBe(true);
			expect(request.input).not.toContain("\n");
			expect(Buffer.byteLength(request.input, "utf8")).toBeLessThanOrEqual(ASK_DECISION_MAX_STATE_BYTES);
			const envelope = JSON.parse(request.input) as {
				material: Record<string, unknown>;
				preparation: DecisionPreparation;
				meta: { logical_id: string; key: string; task_key: string | null; initiator_role: string };
			};
			expect(envelope.material).toEqual(activeMaterial());
			expect(envelope.preparation).toEqual(activePreparation());
			expect(envelope.meta).toMatchObject({
				key: "mw-decision-tool",
				task_key: "ds-t05-ask-tool",
				initiator_role: "pm",
			});
			expect(payload).toEqual({
				available: true,
				decision_id: `${TEST_DP}:${envelope.meta.logical_id}`,
				mode: "auto",
				acted: false,
				answers: { handling: { value: "c1" }, basis_id: { value: "basis" } },
				confidence_source: "api",
				latency_ms: 1420,
				selection: { question: "handling", id: "c1", label: "continue", description: "stay in scope" },
				basis: activePreparation().basis_catalog[0],
				feedback: { stage: "consumed", status: "written", recorded: true },
			});
			// `trigger` is an audit label only: it never becomes the id.
			expect(payload.available && payload.decision_id).not.toContain("ds-t05-ask-tool");
		}
	});

	it("mirrors a suggest verdict (acted=false) and projects a single question id", async () => {
		const projectDir = makeTempDir("mw-ask-suggest-");
		const { runner } = fakeRunner(okReply({ mode: "suggest", acted: false }));
		const outcome = await baseAsk(projectDir, runner, { question: "handling" });
		const payload = parseText(outcome.text);
		expect(payload.available).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		expect(payload.mode).toBe("suggest");
		expect(payload.acted).toBe(false);
		// The material path never re-projects a question subset: the child's
		// answer set is passed through verbatim (the legacy path is retired).
		expect(Object.keys(payload.answers).sort()).toEqual(["basis_id", "handling"]);
	});

	it("refuses to fabricate the authority keys when the child omits them", async () => {
		const projectDir = makeTempDir("mw-ask-nokeys-");
		const { runner } = fakeRunner(okReply({ decision_id: null, mode: null }));
		const outcome = await baseAsk(projectDir, runner);
		expect(outcome.spawned).toBe(true);
		expectUnavailableText(outcome.text, "bad-response");
	});
});

// ── 2. structured state per dp (MAJOR-2) ────────────────────────────────────

describe("ask_decision structured state", () => {
	it("builds only the L0/L1 the call site knows and never pre-gates an ungated dp", () => {
		expect(buildDecisionState({ dp: TEST_DP, note: "  stuck  ", taskKey: "ds-t05-ask-tool" })).toEqual({
			schema_version: 2,
			decision_point: TEST_DP,
			key: "ds-t05-ask-tool",
			task_key: "ds-t05-ask-tool",
			task_summary: "stuck",
		});
		// The eight business dps report the GENERATED REGISTRY's required paths.
		expect(missingDecisionStateFields(TEST_DP, buildDecisionState({ dp: TEST_DP }))).toEqual(registryFields(TEST_DP));
		// An id the registry cannot resolve has no local field gate: the
		// registry refusal owns it (zero spawn), not a second client table.
		expect(missingDecisionStateFields("dp99-nope", buildDecisionState({ dp: "dp99-nope" }))).toEqual([]);
		expect(missingDecisionStateFields(TEST_DP, buildDecisionState({ dp: TEST_DP }))).not.toContain(
			"questions_version",
		);
	});

	it("refuses three active dps with exactly the registry's missing field names and zero spawn", async () => {
		const projectDir = makeTempDir("mw-ask-state-");
		const { calls, runner } = fakeRunner(okReply());
		for (const dp of ["dp-w-type", "dp-auto", "dp-QG"]) {
			const outcome = await baseAsk(projectDir, runner, {
				dp,
				material: {},
				preparation: activePreparation(),
			});
			expect(outcome.spawned, dp).toBe(false);
			const payload = expectUnavailableText(outcome.text, "input-incomplete");
			if (payload.available) throw new Error("unreachable");
			expect(payload.missing_fields, dp).toEqual(registryFields(dp));
		}
		expect(calls).toHaveLength(0);
	});
});

// ── 3. material budget: the CLI is the only authority ───────────────────────

describe("ask_decision material budget: the CLI is the only authority", () => {
	const longQuestion = `dp 预算比对：${"问".repeat(900)}`;

	it("does not pre-refuse a >2000B material before the child runs", async () => {
		const projectDir = makeTempDir("mw-ask-budget-material-");
		const { calls, runner } = fakeRunner(raw(0, unavailableStdout("budget-exhausted", "input-oversize")));
		const outcome = await baseAsk(projectDir, runner, {
			material: { ...activeMaterial(), question: longQuestion },
		});
		expect(calls).toHaveLength(1);
		expect(outcome.spawned).toBe(true);
		const payload = expectUnavailableText(outcome.text, "budget-exhausted");
		if (payload.available) throw new Error("unreachable");
		expect(payload.escalated_reason).toBe("input-oversize");
	});

	it("maps the sign CLI's own input-oversize refusal instead of a bare upstream-error", async () => {
		const projectDir = makeTempDir("mw-ask-budget-sign-");
		const calls: SignRequest[] = [];
		const signRunner: SignRunner = async (request) => {
			calls.push(request);
			return {
				status: 2,
				stdout: JSON.stringify({
					dp: "dp-sign-key",
					logical_id: "6d0a0d3a-9f83-4f4f-a1d7-159c50d5a3f1",
					conclusion: null,
					signoff_status: "failed",
					second_approval: 0,
					problems: [
						"dp-sign-key did not produce a conclusion (input-oversize)",
						"dp-sign-key:x: state is 9618B > 8192B",
					],
				}),
				stderr: "",
				timedOut: false,
			};
		};
		const outcome = await baseAsk(projectDir, fakeRunner(okReply()).runner, {
			dp: "dp-sign-key",
			material: signMaterial(),
			preparation: signPreparation(),
			signRunner,
		});
		expect(calls).toHaveLength(1);
		expect(outcome.spawned).toBe(true);
		const payload = expectUnavailableText(outcome.text, "input-oversize");
		if (payload.available) throw new Error("unreachable");
		expect(payload.escalated_reason).toBe("input-oversize");
	});
});

// ── 4. unavailable ──────────────────────────────────────────────────────────

describe("ask_decision unavailable", () => {
	it("maps a service available=false to the frozen reason + fixed directive", async () => {
		const projectDir = makeTempDir("mw-ask-down-");
		const { runner } = fakeRunner(raw(0, unavailableStdout("entry-unavailable")));
		const outcome = await baseAsk(projectDir, runner);
		expect(outcome.spawned).toBe(true);
		expectUnavailableText(outcome.text, "entry-unavailable");
		expect(outcome.text).toContain(`blocked on decision ${TEST_DP}`);
	});

	it("forwards the child's escalated_reason beside (never instead of) the legacy reason", async () => {
		const projectDir = makeTempDir("mw-ask-escalated-");
		const { runner } = fakeRunner(raw(0, unavailableStdout("bad-response", "input-incomplete")));
		const outcome = await baseAsk(projectDir, runner);
		const payload = expectUnavailableText(outcome.text, "bad-response");
		if (payload.available) throw new Error("unreachable");
		expect(payload.escalated_reason).toBe("input-incomplete");
	});

	it("passes the seven-value escalation vocabulary through verbatim", async () => {
		const reasons = [
			"disabled",
			"unavailable",
			"input-incomplete",
			"input-oversize",
			"low-confidence",
			"over-authority",
			"p0",
		];
		for (const escalated of reasons) {
			const projectDir = makeTempDir("mw-ask-vocab-");
			const { runner } = fakeRunner(raw(0, unavailableStdout("disabled", escalated)));
			const outcome = await baseAsk(projectDir, runner);
			const payload = expectUnavailableText(outcome.text, "disabled");
			if (payload.available) throw new Error("unreachable");
			expect(payload.escalated_reason).toBe(escalated);
		}
	});

	it("does not pre-gate on the authorization table (Python stays the single authority)", async () => {
		const projectDir = makeTempDir("mw-ask-table-");
		writePoints(projectDir, { [TEST_DP]: { enabled: false } });
		const { calls, runner } = fakeRunner(raw(0, unavailableStdout("disabled", "disabled")));
		const outcome = await baseAsk(projectDir, runner);
		expect(outcome.spawned).toBe(true);
		expect(calls).toHaveLength(1);
		const payload = expectUnavailableText(outcome.text, "disabled");
		expect(payload.available).toBe(false);
		expect(outcome.text).toContain("disabled ≠ approval");
	});
});

// ── 5. timeout ──────────────────────────────────────────────────────────────

describe("ask_decision timeout", () => {
	it("maps a killed child to unavailable=timeout", async () => {
		const projectDir = makeTempDir("mw-ask-timeout-");
		const { runner } = fakeRunner(raw(null, "", { timedOut: true }));
		expectUnavailableText((await baseAsk(projectDir, runner)).text, "timeout");
	});

	it("spawnWithTimeout really kills the child at the wall clock", async () => {
		const started = Date.now();
		const rawResult = await spawnWithTimeout([process.execPath, "-e", "setInterval(() => {}, 1000)"], {
			timeoutMs: 400,
		});
		const elapsed = Date.now() - started;
		expect(rawResult.timedOut).toBe(true);
		expect(elapsed).toBeGreaterThanOrEqual(350);
		expect(elapsed).toBeLessThan(10_000);
		const ok = await spawnWithTimeout([process.execPath, "-e", "process.stdout.write('hi')"], {
			timeoutMs: 10_000,
		});
		expect(ok.timedOut).toBe(false);
		expect(ok.status).toBe(0);
		expect(ok.stdout).toBe("hi");
	});
});

// ── 6. unparsable JSON ──────────────────────────────────────────────────────

describe("ask_decision bad response", () => {
	it("maps non-JSON stdout to unavailable=bad-response without throwing", async () => {
		const projectDir = makeTempDir("mw-ask-badjson-");
		const { runner } = fakeRunner(raw(0, "Fatal: something went sideways\n<<< not json >>>"));
		expectUnavailableText((await baseAsk(projectDir, runner)).text, "bad-response");
		expect(parseDecisionJson("<<< nope >>>")).toBeUndefined();
		expect(parseDecisionJson(`[log] noise\n${okStdout()}`)?.available).toBe(true);
	});

	it("normalises a reason outside the frozen set to upstream-error", async () => {
		const projectDir = makeTempDir("mw-ask-reason-");
		const { runner } = fakeRunner(raw(0, unavailableStdout("not-a-frozen-reason")));
		expectUnavailableText((await baseAsk(projectDir, runner)).text, "upstream-error");
	});
});

// ── 7. unregistered / retired dp ────────────────────────────────────────────

describe("ask_decision unregistered dp", () => {
	it("reports retired/unknown ids with zero spawn and no throw", async () => {
		const projectDir = makeTempDir("mw-ask-unknown-");
		const { calls, runner } = fakeRunner(okReply());
		const unknown = await baseAsk(projectDir, runner, { dp: "dp99-nope" });
		expect(unknown.spawned).toBe(false);
		expectUnavailableText(unknown.text, "unknown-dp");
		const retired = await baseAsk(projectDir, runner, { dp: "dp1-dispatch-type" });
		expect(retired.spawned).toBe(false);
		expectUnavailableText(retired.text, "retired");
		expect(calls).toHaveLength(0);
	});

	it("keeps unknown ids out of the tool schema enum", () => {
		const projectDir = makeTempDir("mw-ask-schema-");
		const { capture, pi } = api();
		registerAskDecisionTool(pi, { projectDir, tracePath: path.join(projectDir, "trace.log") });
		const values = dpEnumOf(toolOf(capture, ASK_DECISION_TOOL));
		expect(values).toHaveLength(ASK_DECISION_DP_IDS.length);
		expect([...values].sort()).toEqual([...ASK_DECISION_DP_IDS].sort());
		expect(values).not.toContain("dp99-nope");
		expect(values).not.toContain("dp1-dispatch-type");
	});
});

// ── 8. anti-retry breaker + registration wiring ─────────────────────────────

describe("ask_decision anti-retry breaker", () => {
	it("r2: two blocked asks suppress only that matter, never terminate the PM", async () => {
		const projectDir = makePmProject("mw-ask-breaker-");
		const tracePath = path.join(projectDir, "trace.log");
		const { calls, runner } = fakeRunner(raw(null, "", { timedOut: true }));
		const { capture, pi } = api();
		const handle = registerAskDecisionTool(pi, {
			projectDir,
			tracePath,
			initiatorRole: "pm",
			runner,
			lifecycleRunner: fakeLifecycle,
		});
		const tool = toolOf(capture, ASK_DECISION_TOOL);
		expect(tool.executionMode).toBe("sequential");
		expect(handle.projectDir).toBe(projectDir);

		const first = await tool.execute("call-1", askParams());
		expect(first.terminate).toBeUndefined();
		expect(first.details).toMatchObject({
			next: { owner: "pm", action: "reconcile-action", action_ref: expect.stringMatching(/^dp-auto:/) },
		});
		expect(handle.counter.countFor(TEST_DP)).toBe(1);

		const second = await tool.execute("call-2", askParams("ds-t05-ask-tool#other"));
		expect(second.terminate).toBeUndefined();
		expect(second.content[0].text).not.toContain("TERMINAL");
		expect(second.content[0].text).toContain('"matter_suppressed":true');
		expect(second.details).toMatchObject({ next: (first.details as { next: object }).next });
		expect((second.details as { decision_feedback?: { raw_reason?: string } }).decision_feedback?.raw_reason).toBe(
			"timeout",
		);
		expect(calls).toHaveLength(1);

		const receipts = path.join(projectDir, ".agenticdoc", "_autopilot", "dp-blocked");
		const firstId = (first.details as { blocked_event_id: string }).blocked_event_id;
		const secondId = (second.details as { blocked_event_id: string }).blocked_event_id;
		expect(secondId).not.toBe(firstId);
		expect(fs.readdirSync(receipts).sort()).toEqual([`${firstId}.json`, `${secondId}.json`].sort());
		expect(JSON.parse(fs.readFileSync(path.join(receipts, `${firstId}.json`), "utf8"))).toMatchObject({
			dp: TEST_DP,
			stage: "child-timeout",
			reason: "timeout",
		});
		expect(JSON.parse(fs.readFileSync(path.join(receipts, `${secondId}.json`), "utf8"))).toMatchObject({
			dp: TEST_DP,
			stage: "replay",
			reason: "timeout",
		});

		const trace = fs.readFileSync(tracePath, "utf8");
		expect(trace.match(/\[DECISION_UNAVAILABLE\]/g)).toHaveLength(1);
		expect(trace.match(/\[DECISION_RETRY_STOP\]/g)).toBeNull();
		expect(trace.match(/\[DECISION_MATTER_SUPPRESSED\]/g)).toHaveLength(1);
		expect(trace).toContain("reason=timeout");
		expect(trace).toContain(`max=${ASK_DECISION_MAX_BLOCKED_PER_TURN}`);

		capture.fire("turn_start");
		expect(handle.counter.countFor(TEST_DP)).toBe(0);
		const third = await tool.execute("call-3", askParams());
		expect(third.terminate).toBeUndefined();
		expect(calls).toHaveLength(1);
		const fourth = await tool.execute("call-4", { ...askParams(), note: "new observed evidence" });
		expect(fourth.terminate).toBeUndefined();
		expect(calls).toHaveLength(2);
	});

	it("records the child's decision_id/mode/acted in the success line and clears the block count", async () => {
		const projectDir = makePmProject("mw-ask-trace-ok-");
		const tracePath = path.join(projectDir, "trace.log");
		const { runner } = fakeRunner(okReply());
		const { capture, pi } = api();
		const handle = registerAskDecisionTool(pi, {
			projectDir,
			tracePath,
			initiatorRole: "pm",
			runner,
			lifecycleRunner: fakeLifecycle,
		});
		const tool = toolOf(capture, ASK_DECISION_TOOL);
		handle.counter.recordBlock(TEST_DP);
		const result = await tool.execute("call-ok", askParams());
		expect(result.terminate).toBeUndefined();
		expect(handle.counter.countFor(TEST_DP)).toBe(0);
		const trace = fs.readFileSync(tracePath, "utf8");
		expect(trace).toContain("[DECISION]");
		expect(trace).toMatch(/decision_id=dp-auto:/);
		expect(trace).toContain("mode=auto");
		expect(trace).toContain("acted=false");
	});

	it("traces the child's escalated_reason on a blocked ask", async () => {
		const projectDir = makePmProject("mw-ask-trace-esc-");
		const tracePath = path.join(projectDir, "trace.log");
		const { runner } = fakeRunner(raw(0, unavailableStdout("bad-response", "input-incomplete")));
		const { capture, pi } = api();
		registerAskDecisionTool(pi, { projectDir, tracePath, initiatorRole: "pm", runner });
		await toolOf(capture, ASK_DECISION_TOOL).execute("call-esc", askParams());
		expect(fs.readFileSync(tracePath, "utf8")).toContain("escalated_reason=input-incomplete");
	});

	it("appends the tool to the active set for every role, exactly once", () => {
		const projectDir = makeTempDir("mw-ask-active-");
		const { capture, pi } = api();
		registerAskDecisionTool(pi, { projectDir, tracePath: path.join(projectDir, "trace.log") });
		capture.active = ["read", "bash", "worker_file"];
		capture.fire("before_agent_start");
		expect(capture.active).toEqual(["read", "bash", "worker_file", ASK_DECISION_TOOL, DECISION_RECEIPT_TOOL]);
		capture.fire("before_agent_start");
		expect(
			capture.active.filter((name) => name === ASK_DECISION_TOOL || name === DECISION_RECEIPT_TOOL),
		).toHaveLength(2);
	});
});

// ── 9. eight-DP registry parity + argv contract ─────────────────────────────

describe("ask_decision registry parity", () => {
	const registryPath = fileURLToPath(new URL("../../../multi-workers/decision_points.py", import.meta.url));
	const registrySource = fs.readFileSync(registryPath, "utf8");

	it("keeps the TS dp id enum inside the Python DP_REGISTRY", () => {
		const ids = [...registrySource.matchAll(/_point\(\s*dp_id="([^"]+)"/g)].map(([, id]) => id);
		expect(ids).toHaveLength(8);
		expect([...ASK_DECISION_DP_IDS].sort()).toEqual([...ids].sort());
	});

	it("pins the client-side required-field dp set to decision_points.REQUIRED_STATE_FIELDS", () => {
		const start = registrySource.indexOf("REQUIRED_STATE_FIELDS: Mapping");
		const end = registrySource.indexOf("OPTIONAL_STATE_PATHS", start);
		expect(start).toBeGreaterThan(-1);
		expect(end).toBeGreaterThan(start);
		const block = registrySource.slice(start, end);
		const ids = [...block.matchAll(/^\s+"([A-Za-z0-9-]+)": \($/gm)].map(([, id]) => id);
		expect(ids.length).toBeGreaterThan(0);
		const enforced = [...ASK_DECISION_ENFORCED_STATE_DP_IDS].sort();
		expect(enforced).toEqual([...ASK_DECISION_MATERIAL_DP_IDS].sort());
		expect(enforced).toEqual([...ASK_DECISION_DP_IDS].sort());
		for (const id of enforced) {
			expect(ids, id).toContain(id);
			expect(DECIDE_REGISTRY[id]?.requiredStateFields.length, id).toBeGreaterThan(0);
		}
		// The Python field table still carries legacy rows; a retired id is not a
		// callable alias and stays out of the generated active registry.
		expect(DECIDE_REGISTRY["dp1-dispatch-type"]).toBeUndefined();
		expect(enforced).not.toContain("dp1-dispatch-type");
	});

	it("builds a decide-run argv that carries the state via --request-file only", () => {
		const argv = buildDecideArgv(
			"/repo/packages/multi-workers/mw.py",
			{ projectDir: "/work", dp: TEST_DP, input: '{"state":{"schema_version":2}}', timeoutMs: 20_000 },
			"/tmp/mw-decide-x/request.json",
		);
		expect(argv).toEqual([
			"-X",
			"utf8",
			"/repo/packages/multi-workers/mw.py",
			"decide",
			"run",
			"--project=/work",
			"--dp",
			TEST_DP,
			"--request-file",
			"/tmp/mw-decide-x/request.json",
			"--json",
		]);
		expect(argv.some((arg) => arg.includes('"state"'))).toBe(false);
	});

	it("pipes the envelope on stdin and leaves no temp request file on the production path", async () => {
		const python = process.platform === "win32" ? "python" : "python3";
		const hasPython = spawnSync(python, ["-c", "import sys; sys.exit(0)"], { windowsHide: true }).status === 0;
		if (!hasPython) return; // No Python: the argv test above still locks the contract.

		const projectDir = makeTempDir("mw-ask-stub-");
		const stub = path.join(projectDir, "stub_mw.py");
		fs.writeFileSync(
			stub,
			[
				"import json, sys",
				"args = sys.argv[1:]",
				"payload = json.load(sys.stdin)",
				"assert payload['material']['question']",
				"assert payload['meta']['logical_id']",
				"proj = [a for a in args if a.startswith('--project=')][0].split('=', 1)[1]",
				"seen = 'request-file' if '--request-file' in args else 'stdin'",
				"open(proj + '/request-path.txt', 'w', encoding='utf-8').write(seen)",
				"print(json.dumps({'available': True, 'confidence_source': 'api', 'latency_ms': 1,",
				"                  'answers': {'handling': {'value': 'c1'}, 'basis_id': {'value': 'basis'}}, 'reason': None,",
				"                  'decision_id': 'dp-auto:' + payload['meta']['logical_id'], 'mode': 'auto', 'acted': False,",
				"                  'escalated_reason': None}))",
			].join("\n"),
			"utf8",
		);

		const saved = process.env.MW_PY;
		process.env.MW_PY = stub;
		try {
			const result = await runDecideMw({
				projectDir,
				dp: TEST_DP,
				input: JSON.stringify({
					material: activeMaterial(),
					preparation: activePreparation(),
					meta: { logical_id: "stub-id" },
				}),
				timeoutMs: 15_000,
				viaStdin: true,
			});
			expect(result.timedOut).toBe(false);
			expect(result.error).toBeUndefined();
			expect(result.status).toBe(0);
			expect(parseDecisionJson(result.stdout)?.available).toBe(true);
			const seenPathFile = path.join(projectDir, "request-path.txt");
			expect(fs.existsSync(seenPathFile)).toBe(true);
			expect(fs.readFileSync(seenPathFile, "utf8").trim()).toBe("stdin");
		} finally {
			if (saved === undefined) delete process.env.MW_PY;
			else process.env.MW_PY = saved;
		}
	});
});
