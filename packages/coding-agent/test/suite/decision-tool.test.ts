/**
 * decision-tool.test.ts — `ask_decision` payload/failure contract
 * (mw-decision-substitution T-05, spec AC-004/AC-005/AC-013/AC-015; QG MAJOR-1
 * / MAJOR-2 fix FIX-A).
 *
 * Five required paths plus the anti-retry breaker:
 *   1. success (the child's four authority keys pass through verbatim),
 *   2. unavailable (service `available:false`, `escalated_reason` passthrough),
 *   3. timeout (mapped AND the async spawn really kills the child),
 *   4. unparsable stdout (`bad-response`),
 *   5. unregistered dp (zero spawn, frozen `disabled`, no throw).
 *
 * Invariants asserted throughout: an unavailable result NEVER throws and its
 * text always carries the fixed "不要自行猜测" directive; the JSON line is the
 * first line and parses on its own; the request envelope stays single-line and
 * under the canonical budget; the tool never reads `.mw/decide-points.json`
 * (D-036 single authority) and never derives `mode`/`acted`/`decision_id`
 * (D-036/D-041); the TS dp constants match
 * `packages/multi-workers/decision_points.py` (the registry authority).
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
	ASK_DECISION_MAX_BLOCKED_PER_TURN,
	ASK_DECISION_MAX_STATE_BYTES,
	ASK_DECISION_TOOL,
	type AskDecisionPayload,
	buildDecideArgv,
	buildDecisionState,
	type DecideRunner,
	type DecideRunRequest,
	missingDecisionStateFields,
	parseDecisionJson,
	type RawDecideResult,
	registerAskDecisionTool,
	runAskDecision,
	runDecideMw,
	spawnWithTimeout,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";

// ── temp isolated projects ──────────────────────────────────────────────────

const tempDirs: string[] = [];

function makeTempDir(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

/** Write `.mw/decide-points.json` — the table the tool must NOT read (D-036). */
function writePoints(projectDir: string, points: Record<string, unknown>): void {
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(
		path.join(projectDir, ".mw", "decide-points.json"),
		`${JSON.stringify({ version: 1, updated_by: "test", points })}\n`,
		"utf8",
	);
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

function fakeRunner(raw: RawDecideResult): { calls: DecideRunRequest[]; runner: DecideRunner } {
	const calls: DecideRunRequest[] = [];
	return {
		calls,
		runner: async (request: DecideRunRequest) => {
			calls.push(request);
			return raw;
		},
	};
}

/** Dp used for the plain success/unavailable paths: it has no registry
 * required-field set, so it is sendable with only the L0/L1 this call site
 * knows (see `decision_points.REQUIRED_STATE_FIELDS`). */
const TEST_DP = "dp4-failure-handling";

/** The child's id is derived by Python from the state's `key`
 * (`Trigger.resolved_id`), never from the tool's `trigger` label. */
const CHILD_DECISION_ID = `${TEST_DP}:mw-decision-substitution`;

function okStdout(overrides: Record<string, unknown> = {}): string {
	return JSON.stringify({
		available: true,
		transport: "fake",
		model: "fake-model",
		confidence_source: "api",
		attempts: 1,
		latency_ms: 1420,
		answers: {
			answer_kind: { value: "fact", confidence: 0.83 },
			clarifying_answer: { value: "the interface lives in shared/paths.ts" },
		},
		reason: null,
		// The four authority keys `mw decide run` adds (`mw.py:_decide_run_payload`).
		decision_id: CHILD_DECISION_ID,
		mode: "auto",
		// `intent="answer"` archives the advisory row with acted=false (D-035).
		acted: false,
		escalated_reason: null,
		...overrides,
	});
}

function unavailableStdout(reason: string, escalated?: string): string {
	return JSON.stringify({
		available: false,
		transport: "fake",
		model: null,
		confidence_source: "unknown",
		attempts: 1,
		latency_ms: 30,
		answers: null,
		reason,
		decision_id: CHILD_DECISION_ID,
		mode: "auto",
		acted: false,
		escalated_reason: escalated ?? null,
	});
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

// ── 1. success: verbatim four-key passthrough ───────────────────────────────

describe("ask_decision success", () => {
	it("passes the child's decision_id/mode/acted through verbatim, whatever the table says", async () => {
		const cleanDir = makeTempDir("mw-ask-ok-");
		// A row that disagrees with the child on `enabled` AND `mode`: it must not
		// influence the payload (D-036: only Python judges authorization).
		const tableDir = makeTempDir("mw-ask-ok-table-");
		writePoints(tableDir, { [TEST_DP]: { enabled: false, mode: "suggest" } });
		// A broken table must not crash or invent a verdict either.
		const corruptDir = makeTempDir("mw-ask-ok-corrupt-");
		fs.mkdirSync(path.join(corruptDir, ".mw"), { recursive: true });
		fs.writeFileSync(path.join(corruptDir, ".mw", "decide-points.json"), "{ not json", "utf8");

		const expected = {
			available: true,
			// The child's id — not a local `<dp>:<trigger>` concat, which would
			// drift from the archive row Python actually wrote.
			decision_id: CHILD_DECISION_ID,
			mode: "auto",
			acted: false,
			answers: {
				answer_kind: { value: "fact", confidence: 0.83 },
				clarifying_answer: { value: "the interface lives in shared/paths.ts" },
			},
			confidence_source: "api",
			latency_ms: 1420,
		};

		for (const projectDir of [cleanDir, tableDir, corruptDir]) {
			const { calls, runner } = fakeRunner({ status: 0, stdout: okStdout(), stderr: "", timedOut: false });

			const outcome = await runAskDecision({
				projectDir,
				dp: TEST_DP,
				trigger: "ds-t05-ask-tool#ckpt1",
				note: "test failure in decision-tool.test.ts",
				taskKey: "ds-t05-ask-tool",
				runner,
			});

			expect(outcome.spawned).toBe(true);
			expect(calls).toHaveLength(1);
			const payload = parseText(outcome.text);
			expect(outcome.text).not.toContain("\n");
			expect(payload).toEqual(expected);

			// The request rides as one bounded JSON line (temp-file contract).
			const request = calls[0];
			expect(request.projectDir).toBe(projectDir);
			expect(request.dp).toBe(TEST_DP);
			expect(request.input).not.toContain("\n");
			expect(Buffer.byteLength(request.input, "utf8")).toBeLessThanOrEqual(ASK_DECISION_MAX_STATE_BYTES);
			const envelope = JSON.parse(request.input) as { state: Record<string, unknown> };
			expect(envelope.state).toEqual({
				schema_version: 2,
				decision_point: TEST_DP,
				key: "ds-t05-ask-tool",
				task_key: "ds-t05-ask-tool",
				task_summary: "test failure in decision-tool.test.ts",
			});
		}

		// `trigger` is an audit label only: it never becomes the id.
		expect(expected.decision_id).not.toContain("ds-t05-ask-tool");
	});

	it("mirrors a suggest verdict (acted=false) and projects a single question id", async () => {
		const projectDir = makeTempDir("mw-ask-suggest-");
		const { runner } = fakeRunner({
			status: 0,
			stdout: okStdout({ mode: "suggest", acted: false }),
			stderr: "",
			timedOut: false,
		});

		const outcome = await runAskDecision({
			projectDir,
			dp: TEST_DP,
			trigger: "ds-t05-ask-tool",
			question: "answer_kind",
			runner,
		});

		const payload = parseText(outcome.text);
		expect(payload.available).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		expect(payload.mode).toBe("suggest");
		expect(payload.acted).toBe(false);
		expect(Object.keys(payload.answers)).toEqual(["answer_kind"]);
	});

	it("refuses to fabricate the authority keys when the child omits them", async () => {
		const projectDir = makeTempDir("mw-ask-nokeys-");
		const { runner } = fakeRunner({
			status: 0,
			stdout: okStdout({ decision_id: null, mode: null }),
			stderr: "",
			timedOut: false,
		});

		const outcome = await runAskDecision({ projectDir, dp: TEST_DP, trigger: "ds-t05-ask-tool", runner });

		expect(outcome.spawned).toBe(true);
		expectUnavailableText(outcome.text, "bad-response");
	});
});

// ── 2. structured state per dp (MAJOR-2) ────────────────────────────────────

describe("ask_decision structured state", () => {
	it("builds only the L0/L1 the call site knows and never pre-gates an ungated dp", () => {
		expect(buildDecisionState({ dp: "dp3-worker-clarify", note: "  stuck  ", taskKey: "ds-t05-ask-tool" })).toEqual({
			schema_version: 2,
			decision_point: "dp3-worker-clarify",
			key: "ds-t05-ask-tool",
			task_key: "ds-t05-ask-tool",
			task_summary: "stuck",
		});
		// The gated dp reports its own block (names only) — the dp-specific table
		// is triage-client's `REQUIRED_FIELDS_BY_DP`, never a local copy.
		expect(
			missingDecisionStateFields("dp3-worker-clarify", buildDecisionState({ dp: "dp3-worker-clarify" })),
		).toEqual(expect.arrayContaining(["task_summary", "ambiguity.kind", "ambiguity.question"]));
		// Ungated dp: the registry requires nothing beyond
		// schema_version/decision_point/questions_version.
		expect(missingDecisionStateFields(TEST_DP, buildDecisionState({ dp: TEST_DP }))).toEqual([]);
		// `questions_version` is filled by Python's state builder, so it is never
		// reported as a field the caller has to supply.
		expect(
			missingDecisionStateFields("dp3-worker-clarify", buildDecisionState({ dp: "dp3-worker-clarify" })),
		).not.toContain("questions_version");
	});

	it("refuses dp1/dp2/dp3 with exactly the registry's missing field names and zero spawn", async () => {
		const projectDir = makeTempDir("mw-ask-state-");
		const { calls, runner } = fakeRunner({ status: 0, stdout: okStdout(), stderr: "", timedOut: false });
		// Expected lists are `decision_points._missing_required(build_state(...))`
		// as a set (probed against the registry; `note` supplies task_summary);
		// the order follows triage-client (universal block, then the dp block).
		const cases: Array<{ dp: string; fields: string[] }> = [
			{
				dp: "dp1-dispatch-type",
				fields: [
					"phase",
					"task_type",
					"risk",
					"risk_source",
					"authority_tier",
					"requested_type",
					"scope.write_scope",
					"scope.file_extensions",
				],
			},
			{
				dp: "dp2-checkpoint-split",
				fields: [
					"phase",
					"task_type",
					"risk",
					"risk_source",
					"authority_tier",
					"progress.elapsed_minutes",
					"progress.budget_minutes",
					"progress.phases_done",
					"progress.phases_total",
					"progress.artifact_present",
				],
			},
			{
				dp: "dp3-worker-clarify",
				fields: [
					"phase",
					"task_type",
					"risk",
					"risk_source",
					"authority_tier",
					"ambiguity.kind",
					"ambiguity.question",
					// W4 made `local_candidates` a required dp3 field (Python registry).
					"local_candidates",
				],
			},
		];

		for (const { dp, fields } of cases) {
			const outcome = await runAskDecision({
				projectDir,
				dp,
				trigger: "ds-t05-ask-tool",
				note: "stuck on a failing test",
				taskKey: "ds-t05-ask-tool",
				runner,
			});
			// A state `decide_for` step 5 must refuse is never sent (MAJOR-2).
			expect(outcome.spawned, dp).toBe(false);
			const payload = expectUnavailableText(outcome.text, "input-incomplete");
			if (payload.available) throw new Error("unreachable");
			expect(payload.missing_fields, dp).toEqual(fields);
		}
		expect(calls).toHaveLength(0);
	});
});

// ── 3. unavailable ──────────────────────────────────────────────────────────

describe("ask_decision unavailable", () => {
	it("maps a service available=false to the frozen reason + fixed directive", async () => {
		const projectDir = makeTempDir("mw-ask-down-");
		const { runner } = fakeRunner({
			status: 0,
			stdout: unavailableStdout("entry-unavailable"),
			stderr: "",
			timedOut: false,
		});

		const outcome = await runAskDecision({ projectDir, dp: TEST_DP, trigger: "ds-t05-ask-tool", runner });

		expect(outcome.spawned).toBe(true);
		expectUnavailableText(outcome.text, "entry-unavailable");
		expect(outcome.text).toContain(`blocked on decision ${TEST_DP}`);
	});

	it("forwards the child's escalated_reason beside (never instead of) the legacy reason", async () => {
		const projectDir = makeTempDir("mw-ask-escalated-");
		const { runner } = fakeRunner({
			status: 0,
			// `_DECIDE_RUN_REASON_MAP`: input-incomplete -> legacy bad-response.
			stdout: unavailableStdout("bad-response", "input-incomplete"),
			stderr: "",
			timedOut: false,
		});

		const outcome = await runAskDecision({ projectDir, dp: TEST_DP, trigger: "ds-t05-ask-tool", runner });
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
			const { runner } = fakeRunner({
				status: 0,
				stdout: unavailableStdout("disabled", escalated),
				stderr: "",
				timedOut: false,
			});
			const outcome = await runAskDecision({ projectDir, dp: TEST_DP, trigger: "ds-t05-ask-tool", runner });
			const payload = expectUnavailableText(outcome.text, "disabled");
			if (payload.available) throw new Error("unreachable");
			expect(payload.escalated_reason).toBe(escalated);
		}
	});

	it("does not pre-gate on the authorization table (Python stays the single authority)", async () => {
		const projectDir = makeTempDir("mw-ask-table-");
		writePoints(projectDir, { "dp12-destructive": { enabled: false } });
		const { calls, runner } = fakeRunner({
			status: 0,
			stdout: unavailableStdout("disabled", "disabled"),
			stderr: "",
			timedOut: false,
		});

		const outcome = await runAskDecision({
			projectDir,
			dp: "dp12-destructive",
			trigger: "ds-t05-ask-tool",
			runner,
		});

		// The local table says "off", but only the child's verdict is reported.
		expect(outcome.spawned).toBe(true);
		expect(calls).toHaveLength(1);
		const payload = expectUnavailableText(outcome.text, "disabled");
		expect(payload.available).toBe(false);
		// AC-005: "disabled" must never read as approval.
		expect(outcome.text).toContain("disabled ≠ approval");
	});
});

// ── 4. timeout ──────────────────────────────────────────────────────────────

describe("ask_decision timeout", () => {
	it("maps a killed child to unavailable=timeout", async () => {
		const projectDir = makeTempDir("mw-ask-timeout-");
		const { runner } = fakeRunner({ status: null, stdout: "", stderr: "", timedOut: true });

		const outcome = await runAskDecision({ projectDir, dp: TEST_DP, trigger: "ds-t05-ask-tool", runner });

		expectUnavailableText(outcome.text, "timeout");
	});

	it("spawnWithTimeout really kills the child at the wall clock", async () => {
		const started = Date.now();
		const raw = await spawnWithTimeout([process.execPath, "-e", "setInterval(() => {}, 1000)"], {
			timeoutMs: 400,
		});
		const elapsed = Date.now() - started;

		expect(raw.timedOut).toBe(true);
		expect(elapsed).toBeGreaterThanOrEqual(350);
		// A killed child must settle the promise promptly (2 s grace cap).
		expect(elapsed).toBeLessThan(10_000);

		// Control: a fast child still reports its exit code and stdout.
		const ok = await spawnWithTimeout([process.execPath, "-e", "process.stdout.write('hi')"], {
			timeoutMs: 10_000,
		});
		expect(ok.timedOut).toBe(false);
		expect(ok.status).toBe(0);
		expect(ok.stdout).toBe("hi");
	});
});

// ── 5. unparsable JSON ──────────────────────────────────────────────────────

describe("ask_decision bad response", () => {
	it("maps non-JSON stdout to unavailable=bad-response without throwing", async () => {
		const projectDir = makeTempDir("mw-ask-badjson-");
		const { runner } = fakeRunner({
			status: 0,
			stdout: "Fatal: something went sideways\n<<< not json >>>",
			stderr: "",
			timedOut: false,
		});

		const outcome = await runAskDecision({ projectDir, dp: TEST_DP, trigger: "ds-t05-ask-tool", runner });

		expectUnavailableText(outcome.text, "bad-response");
		expect(parseDecisionJson("<<< nope >>>")).toBeUndefined();
		// Last-line candidate: a wrapper log line before the payload still parses.
		expect(parseDecisionJson(`[log] noise\n${okStdout()}`)?.available).toBe(true);
	});

	it("normalises a reason outside the frozen set to upstream-error", async () => {
		const projectDir = makeTempDir("mw-ask-reason-");
		const { runner } = fakeRunner({
			status: 0,
			stdout: unavailableStdout("not-a-frozen-reason"),
			stderr: "",
			timedOut: false,
		});
		const outcome = await runAskDecision({ projectDir, dp: TEST_DP, trigger: "ds-t05-ask-tool", runner });
		expectUnavailableText(outcome.text, "upstream-error");
	});
});

// ── 6. unregistered dp ──────────────────────────────────────────────────────

describe("ask_decision unregistered dp", () => {
	it("reports the frozen disabled reason with zero spawn and no throw", async () => {
		const projectDir = makeTempDir("mw-ask-unknown-");
		const { calls, runner } = fakeRunner({ status: 0, stdout: okStdout(), stderr: "", timedOut: false });

		const outcome = await runAskDecision({ projectDir, dp: "dp99-nope", trigger: "ds-t05-ask-tool", runner });

		expect(outcome.spawned).toBe(false);
		expect(calls).toHaveLength(0);
		expectUnavailableText(outcome.text, "disabled");
	});

	it("keeps unknown ids out of the tool schema enum", async () => {
		const projectDir = makeTempDir("mw-ask-schema-");
		const { capture, pi } = api();
		registerAskDecisionTool(pi, { projectDir, tracePath: path.join(projectDir, "trace.log") });
		const tool = toolOf(capture, ASK_DECISION_TOOL);
		const values = dpEnumOf(tool);
		expect(values).toHaveLength(ASK_DECISION_DP_IDS.length);
		expect([...values].sort()).toEqual([...ASK_DECISION_DP_IDS].sort());
		expect(values).not.toContain("dp99-nope");
	});
});

// ── 7. anti-retry breaker + registration wiring ─────────────────────────────

describe("ask_decision anti-retry breaker", () => {
	it("terminates the tool loop on the second blocked ask for the same dp and traces it", async () => {
		const projectDir = makeTempDir("mw-ask-breaker-");
		const tracePath = path.join(projectDir, "trace.log");
		const { runner } = fakeRunner({ status: null, stdout: "", stderr: "", timedOut: true });
		const { capture, pi } = api();
		const handle = registerAskDecisionTool(pi, { projectDir, tracePath, runner });
		const tool = toolOf(capture, ASK_DECISION_TOOL);

		expect(tool.executionMode).toBe("sequential");
		expect(handle.projectDir).toBe(projectDir);

		const first = await tool.execute("call-1", { dp: TEST_DP, trigger: "ds-t05-ask-tool" });
		expect(first.terminate).toBeUndefined();
		expect(first.content[0].text).toContain(ASK_DECISION_GUESS_DIRECTIVE);
		expect(handle.counter.countFor(TEST_DP)).toBe(1);

		const second = await tool.execute("call-2", { dp: TEST_DP, trigger: "ds-t05-ask-tool" });
		expect(second.terminate).toBe(true);
		expect(second.content[0].text).toContain("TERMINAL");
		expect(second.content[0].text).toContain(ASK_DECISION_GUESS_DIRECTIVE);
		expect(handle.counter.countFor(TEST_DP)).toBe(ASK_DECISION_MAX_BLOCKED_PER_TURN);

		const trace = fs.readFileSync(tracePath, "utf8");
		expect(trace.match(/\[DECISION_UNAVAILABLE\]/g)).toHaveLength(2);
		expect(trace.match(/\[DECISION_RETRY_STOP\]/g)).toHaveLength(1);
		expect(trace).toContain("reason=timeout");

		// A new turn restores the per-dp budget (same dp is not terminal again).
		capture.fire("turn_start");
		expect(handle.counter.countFor(TEST_DP)).toBe(0);
		const third = await tool.execute("call-3", { dp: TEST_DP, trigger: "ds-t05-ask-tool" });
		expect(third.terminate).toBeUndefined();
	});

	it("records the child's decision_id/mode/acted in the success line and clears the block count", async () => {
		const projectDir = makeTempDir("mw-ask-trace-ok-");
		const tracePath = path.join(projectDir, "trace.log");
		const { runner } = fakeRunner({ status: 0, stdout: okStdout(), stderr: "", timedOut: false });
		const { capture, pi } = api();
		const handle = registerAskDecisionTool(pi, { projectDir, tracePath, runner });
		const tool = toolOf(capture, ASK_DECISION_TOOL);

		handle.counter.recordBlock(TEST_DP);
		const result = await tool.execute("call-ok", { dp: TEST_DP, trigger: "ds-t05-ask-tool" });
		expect(result.terminate).toBeUndefined();
		expect(handle.counter.countFor(TEST_DP)).toBe(0);
		const trace = fs.readFileSync(tracePath, "utf8");
		expect(trace).toContain("[DECISION]");
		expect(trace).toContain(`decision_id=${CHILD_DECISION_ID}`);
		expect(trace).toContain("mode=auto");
		expect(trace).toContain("acted=false");
	});

	it("traces the child's escalated_reason on a blocked ask", async () => {
		const projectDir = makeTempDir("mw-ask-trace-esc-");
		const tracePath = path.join(projectDir, "trace.log");
		const { runner } = fakeRunner({
			status: 0,
			stdout: unavailableStdout("bad-response", "input-incomplete"),
			stderr: "",
			timedOut: false,
		});
		const { capture, pi } = api();
		registerAskDecisionTool(pi, { projectDir, tracePath, runner });
		const tool = toolOf(capture, ASK_DECISION_TOOL);

		await tool.execute("call-esc", { dp: TEST_DP, trigger: "ds-t05-ask-tool" });
		expect(fs.readFileSync(tracePath, "utf8")).toContain("escalated_reason=input-incomplete");
	});

	it("appends the tool to the active set for every role, exactly once", () => {
		const projectDir = makeTempDir("mw-ask-active-");
		const { capture, pi } = api();
		registerAskDecisionTool(pi, { projectDir, tracePath: path.join(projectDir, "trace.log") });

		capture.active = ["read", "bash", "worker_file"];
		capture.fire("before_agent_start");
		expect(capture.active).toEqual(["read", "bash", "worker_file", ASK_DECISION_TOOL]);
		capture.fire("before_agent_start");
		expect(capture.active.filter((name) => name === ASK_DECISION_TOOL)).toHaveLength(1);
	});
});

// ── 8. registry parity + argv contract ──────────────────────────────────────

describe("ask_decision registry parity", () => {
	const registryPath = fileURLToPath(new URL("../../../multi-workers/decision_points.py", import.meta.url));
	const registrySource = fs.readFileSync(registryPath, "utf8");

	it("keeps the TS dp id enum inside the Python DP_REGISTRY", () => {
		const ids = [...registrySource.matchAll(/_point\(\s*dp_id="([^"]+)"/g)].map(([, id]) => id);
		expect(ids).toHaveLength(25);
		expect([...ASK_DECISION_DP_IDS].sort()).toEqual([...ids].sort());
	});

	it("pins the client-side required-field dp set to decision_points.REQUIRED_STATE_FIELDS", () => {
		// Only these dps are pre-refused on a missing field; the field names come
		// from triage-client, the id set from the Python mapping.
		const start = registrySource.indexOf("REQUIRED_STATE_FIELDS: Mapping");
		const end = registrySource.indexOf("OPTIONAL_STATE_PATHS", start);
		expect(start).toBeGreaterThan(-1);
		expect(end).toBeGreaterThan(start);
		const block = registrySource.slice(start, end);
		const ids = [...block.matchAll(/^\s+"([a-z0-9-]+)": \($/gm)].map(([, id]) => id);
		expect(ids.length).toBeGreaterThan(0);
		expect([...ASK_DECISION_ENFORCED_STATE_DP_IDS].sort()).toEqual([...ids].sort());
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
		// The request JSON never rides argv (D-003).
		expect(argv.some((arg) => arg.includes('"state"'))).toBe(false);
	});

	it("writes the request to a temp file and cleans it up on the production path", async () => {
		const python = process.platform === "win32" ? "python" : "python3";
		const hasPython = spawnSync(python, ["-c", "import sys; sys.exit(0)"], { windowsHide: true }).status === 0;
		if (!hasPython) return; // Environment has no Python: the argv test above still locks the contract.

		const projectDir = makeTempDir("mw-ask-stub-");
		const stub = path.join(projectDir, "stub_mw.py");
		// The stub records the --request-file path it actually received so the
		// test can prove the file was created, consumed and then removed.
		fs.writeFileSync(
			stub,
			[
				"import json, sys",
				"args = sys.argv[1:]",
				"path = args[args.index('--request-file') + 1]",
				"with open(path, encoding='utf-8') as fh:",
				"    payload = json.load(fh)",
				`assert payload['state']['decision_point'] == '${TEST_DP}', payload`,
				"proj = [a for a in args if a.startswith('--project=')][0].split('=', 1)[1]",
				"open(proj + '/request-path.txt', 'w', encoding='utf-8').write(path)",
				"print(json.dumps({'available': True, 'confidence_source': 'api', 'latency_ms': 1,",
				`                  'answers': {'answer_kind': {'value': 'fact'}}, 'reason': None,`,
				`                  'decision_id': '${CHILD_DECISION_ID}', 'mode': 'auto', 'acted': False,`,
				"                  'escalated_reason': None}))",
			].join("\n"),
			"utf8",
		);

		const saved = process.env.MW_PY;
		process.env.MW_PY = stub;
		try {
			const raw = await runDecideMw({
				projectDir,
				dp: TEST_DP,
				input: JSON.stringify({ state: { schema_version: 2, decision_point: TEST_DP } }),
				timeoutMs: 15_000,
			});
			expect(raw.timedOut).toBe(false);
			expect(raw.error).toBeUndefined();
			expect(raw.status).toBe(0);
			expect(parseDecisionJson(raw.stdout)?.available).toBe(true);

			const seenPathFile = path.join(projectDir, "request-path.txt");
			expect(fs.existsSync(seenPathFile)).toBe(true);
			const consumedPath = fs.readFileSync(seenPathFile, "utf8").trim();
			// The temp request file lived outside the project and is gone now.
			expect(consumedPath.startsWith(projectDir)).toBe(false);
			expect(fs.existsSync(consumedPath)).toBe(false);
		} finally {
			if (saved === undefined) delete process.env.MW_PY;
			else process.env.MW_PY = saved;
		}
	});
});
