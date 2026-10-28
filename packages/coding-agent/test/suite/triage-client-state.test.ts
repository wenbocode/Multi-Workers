/**
 * triage-client-state.test.ts — structured decision input for the DP triage
 * client (mw-decision-substitution T-04; design §2.6 + D-004/D-019/D-021;
 * input table and byte budgets: evidence/research/design-input-redaction Q1).
 *
 * What is pinned here:
 *
 * 1. **`(dpId, state)` input** — the decision point id rides `--dp` and the
 *    request envelope; the structured envelope carries the state only (question
 *    authority is the Python registry, design §2.1);
 * 2. **`input-incomplete` refuses with ZERO spawn** — missing / wrongly typed /
 *    out-of-enum / over-cap required fields, a P0 authority tier, a dp mismatch
 *    and unknown top-level keys (the L2 leak guard) never reach the runner and
 *    set `escalate_to_human`;
 * 3. **≤2000B canonical budget** — oversized optional L1 is dropped/shrunk
 *    first, then required L1 is halved, and an irreducibly oversized state is
 *    refused as `input-oversize` with zero spawn;
 * 4. **digest passthrough** — `state_digest` is read from the Python response
 *    verbatim; the TS side never hashes (design D-004);
 * 5. **legacy string state** — the free-form string path keeps its frozen
 *    bytes (16KB bound + DP-1 question map, `spec.md:162`).
 * 6. **cross-layer dp id lock** — every `REQUIRED_FIELDS_BY_DP` key and DP1_ID
 *    is asserted against the live `decision_points.DP_REGISTRY` (a short or
 *    stale id would never match a real dpId and `?? []` would silently drop the
 *    dp-specific requirement, so this fails rather than skips without Python).
 *    The four business-material dps (dp1/dp2/dp3/dp25) deliberately have NO
 *    legacy row: their required fields are the generated registry contract
 *    (`DECIDE_REGISTRY.requiredStateFields`), which the material path consumes.
 *    A row for them would force business material to carry the legacy audit
 *    keys (the retired pre-T01 compatibility branch, spec §1.7).
 *
 * The decision child is stubbed at the `DecideRunner` seam: no real provider
 * call, no network, no `mw decide run`.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	canonicalStateBytes,
	canonicalStateJson,
	DEFAULT_TRIAGE_TIMEOUT_MS,
	type DecideRunner,
	type DecideRunRequest,
	DP1_ID,
	MAX_STRUCTURED_STATE_BYTES,
	prepareStructuredState,
	type RawDecideRun,
	REQUIRED_FIELDS_BY_DP,
	TRIAGE_REASON_INPUT_INCOMPLETE,
	TRIAGE_REASON_INPUT_OVERSIZE,
	type TriageState,
	triageDispatch,
	truncateStructuredState,
	validateStructuredState,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import { PYTHON_EXE } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";

const tempDirs: string[] = [];

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

function projectWithDecideJson(body: Record<string, unknown> = { enabled: true }): string {
	const root = mkdtemp("atl-triage-state-");
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), `${JSON.stringify(body, null, 2)}\n`, "utf8");
	return root;
}

interface Stub {
	run: DecideRunner;
	calls: DecideRunRequest[];
}

function stubRunner(response: RawDecideRun | (() => RawDecideRun)): Stub {
	const calls: DecideRunRequest[] = [];
	const run: DecideRunner = (request) => {
		calls.push(request);
		return typeof response === "function" ? response() : response;
	};
	return { run, calls };
}

function okStdout(extra: Record<string, unknown> = {}): string {
	return JSON.stringify({
		available: true,
		transport: "llm-transitional",
		confidence_source: "model-self-report",
		attempts: 1,
		latency_ms: 12,
		answers: {
			triage_type: { value: "coding", confidence: 0.8 },
			triage_risk: { value: "mid", confidence: 0.6 },
		},
		...extra,
	});
}

function okRun(extra: Record<string, unknown> = {}): RawDecideRun {
	return { status: 0, timedOut: false, stderr: "", stdout: okStdout(extra) };
}

function envelopeOf(call: DecideRunRequest | undefined): Record<string, unknown> {
	expect(call).toBeDefined();
	return JSON.parse(call?.input ?? "{}") as Record<string, unknown>;
}

/** A dp1 state that passes every universal-field / optional-cap check.
 *
 * dp1's business contract (task_goal/task_requirements/task_deliverables) is a
 * material contract; this structured state exercises the legacy 21-dp path. */
function dp1State(overrides: TriageState = {}): TriageState {
	return {
		schema_version: 2,
		decision_point: DP1_ID,
		key: "mw-decision-substitution",
		phase: "EXECUTE",
		task_type: "coding",
		requested_type: "coding",
		risk: "mid",
		risk_source: "pm-label",
		authority_tier: "P2",
		questions_version: "dp1@1",
		task_summary: "结构化输入落地：triage-client 出口改为结构化 state",
		scope: {
			// ≤32B per item, ≤12 items (D6 Q1.1 caps)
			write_scope: ["packages/coding-agent/src/pm"],
			file_extensions: ["ts"],
		},
		...overrides,
	};
}

/** A dp3 state (required_if matrix: task_summary + ambiguity + the dynamic
 * candidate list, no scope). */
function dp3State(overrides: TriageState = {}): TriageState {
	return {
		schema_version: 2,
		decision_point: "dp3-worker-clarify",
		key: "mw-decision-substitution",
		phase: "EXECUTE",
		task_type: "coding",
		risk: "mid",
		risk_source: "machine",
		authority_tier: "P2",
		questions_version: "dp3@1",
		task_summary: "worker 需要澄清写面边界",
		ambiguity: { kind: "scope", question: "是否允许改 pm-orchestrator.ts？" },
		local_candidates: [{ id: "c1", label: "packages/coding-agent/src/pm/pm-orchestrator.ts" }],
		...overrides,
	};
}

// ── 1. dpId passthrough / envelope shape ────────────────────────────────────

describe("structured input: dpId and envelope (requirement 1/4)", () => {
	it("passes the dpId through to --dp and to the state envelope", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		const state = dp3State();
		const result = triageDispatch({ projectDir: root, dpId: "dp3-worker-clarify", state, run: stub.run });

		expect(result.available).toBe(true);
		expect(stub.calls).toHaveLength(1);
		expect(stub.calls[0]?.dp).toBe("dp3-worker-clarify");
		const envelope = envelopeOf(stub.calls[0]);
		expect((envelope.state as Record<string, unknown>).decision_point).toBe("dp3-worker-clarify");
	});

	it("defaults the dp to the registry dp1 id and keeps the 20s hard timeout", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });

		expect(stub.calls[0]?.dp).toBe(DP1_ID);
		expect(stub.calls[0]?.timeoutMs).toBe(DEFAULT_TRIAGE_TIMEOUT_MS);
	});

	it("structured envelope carries state only: question authority is Python", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });

		const envelope = envelopeOf(stub.calls[0]);
		expect(Object.keys(envelope)).toEqual(["state"]);
		expect("questions" in envelope).toBe(false);
	});

	it("serialises the state as canonical JSON (sorted keys, compact separators)", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		const state = dp1State({ history: { recent_done: 4, recent_failed: 1 } });
		triageDispatch({ projectDir: root, state, run: stub.run });

		const envelope = envelopeOf(stub.calls[0]);
		expect(JSON.stringify(envelope.state)).toBe(canonicalStateJson(state));
		expect(canonicalStateJson({ b: 1, a: { d: 2, c: [{ y: 1, x: 2 }] } })).toBe(
			'{"a":{"c":[{"x":2,"y":1}],"d":2},"b":1}',
		);
		expect(canonicalStateBytes({ 中: "文" })).toBe(Buffer.byteLength('{"中":"文"}', "utf8"));
		// no redaction / rewriting at the egress point (D-019: L2 has no entry)
		expect((envelope.state as Record<string, unknown>).task_summary).toBe(state.task_summary);
	});
});

// ── 2. input-incomplete: validate before spawn ──────────────────────────────

describe("input-incomplete refuses with ZERO spawn (requirement 2)", () => {
	const cases: Array<{ name: string; dpId?: string; state: TriageState; expectMissing: string }> = [
		{
			name: "missing required field (risk)",
			state: (() => {
				const state = dp1State();
				delete state.risk;
				return state;
			})(),
			expectMissing: "risk",
		},
		{
			name: "wrong type / out of enum (risk=medium)",
			state: dp1State({ risk: "medium" }),
			expectMissing: "risk",
		},
		{
			name: "blank optional L1 summary (task_summary)",
			state: dp1State({ task_summary: "" }),
			expectMissing: "task_summary",
		},
		{
			name: "P0 authority tier is never sent (DS-1)",
			state: dp1State({ authority_tier: "P0" }),
			expectMissing: "authority_tier:P0",
		},
		{
			name: "dp mismatch between envelope and state",
			dpId: "dp3-worker-clarify",
			state: dp1State(),
			expectMissing: "decision_point",
		},
		{
			name: "unknown top-level key (L2 leak guard, no legal key)",
			state: dp1State({ description: "用户原话与凭据都塞在这里" }),
			expectMissing: "unknown:description",
		},
		{
			name: "float where the schema is int-only (digest drift)",
			dpId: "dp4-failure-handling",
			state: {
				schema_version: 2,
				decision_point: "dp4-failure-handling",
				key: "mw-decision-substitution",
				phase: "EXECUTE",
				task_type: "coding",
				risk: "mid",
				risk_source: "machine",
				authority_tier: "P2",
				questions_version: "dp4@1",
				failure: { kind: "exit-nonzero", exit: 1.5 },
			},
			expectMissing: "failure.exit",
		},
		{
			name: "over-cap required L1 (task_summary > 600B)",
			state: dp1State({ task_summary: "决".repeat(300) }),
			expectMissing: "task_summary",
		},
	];

	for (const testCase of cases) {
		it(`${testCase.name}: no spawn, escalate_to_human, field name only`, () => {
			const root = projectWithDecideJson();
			const stub = stubRunner(okRun());
			const result = triageDispatch({
				projectDir: root,
				dpId: testCase.dpId ?? DP1_ID,
				state: testCase.state,
				run: stub.run,
			});

			expect(stub.calls).toHaveLength(0);
			expect(result.available).toBe(false);
			expect(result.reason).toBe(TRIAGE_REASON_INPUT_INCOMPLETE);
			expect(result.escalate_to_human).toBe(true);
			expect(result.missing_fields).toContain(testCase.expectMissing);
			expect(result.state_digest).toBeUndefined();
		});
	}

	it("still performs zero spawn when the policy is off (default-off wins)", () => {
		const root = mkdtemp("atl-triage-off-");
		const stub = stubRunner(okRun());
		const result = triageDispatch({ projectDir: root, state: dp1State({ risk: "" }), run: stub.run });
		expect(stub.calls).toHaveLength(0);
		expect(result.reason).toBe("disabled");
		expect(result.escalate_to_human).toBeUndefined();
	});

	it("keeps the normalize-to-available=false contract for a throwing runner", () => {
		const root = projectWithDecideJson();
		const throwing: DecideRunner = () => {
			throw new Error("kaboom");
		};
		const result = triageDispatch({ projectDir: root, state: dp1State(), run: throwing });
		expect(result.available).toBe(false);
		expect(result.reason).toBe("upstream-error");
	});
});

// ── 3. canonical ≤2000B: two-stage truncation, then refusal ─────────────────

describe("≤2000B canonical budget (requirement 3)", () => {
	/** Valid per every cap, yet > 2000B once the optional blocks are combined:
	 * the documented "only pathological combinations overflow" case (D6 Q1.3). */
	function oversizedButValidState(): TriageState {
		return dp1State({
			task_summary: "决".repeat(200), // 600B (cap)
			scope: {
				write_scope: Array.from({ length: 12 }, () => "packages/coding-agent/src/pm"), // 12 x 28B
				file_extensions: ["ts", "py"],
			},
			history: {
				recent_done: 4,
				recent_failed: 1,
				recent_lost: 0,
				recent_needs_clarification: 0,
				recent_superseded: 2,
			},
			closure: {
				blockers_count: 3,
				evidence_present: true,
				blockers: Array.from({ length: 3 }, () => "阻".repeat(66)),
			},
			failure: { summary: "错".repeat(100) },
			ambiguity: { kind: "scope", question: "问".repeat(100) },
		});
	}

	it("drops optional L1 first and still sends a required-field-complete state", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		const state = oversizedButValidState();
		expect(canonicalStateBytes(state)).toBeGreaterThan(MAX_STRUCTURED_STATE_BYTES);
		expect(validateStructuredState(DP1_ID, state)).toEqual([]);

		const result = triageDispatch({ projectDir: root, state, run: stub.run });

		expect(stub.calls).toHaveLength(1);
		expect(result.available).toBe(true);
		const envelope = envelopeOf(stub.calls[0]);
		const sent = envelope.state as TriageState;
		expect(canonicalStateBytes(sent)).toBeLessThanOrEqual(MAX_STRUCTURED_STATE_BYTES);
		// required L1 is shrunk, never dropped
		expect(typeof sent.task_summary).toBe("string");
		expect((sent.task_summary as string).length).toBeGreaterThan(0);
		expect(sent.risk).toBe("mid");
		expect(Array.isArray((sent.scope as TriageState).write_scope)).toBe(true);
		expect(result.dropped_fields?.length).toBeGreaterThan(0);
		// never a blind string cut: the payload is whole, parseable JSON
		expect(() => JSON.parse(stub.calls[0]?.input ?? "")).not.toThrow();
	});

	it("truncation is deterministic and leaves the caller object untouched", () => {
		const state = oversizedButValidState();
		const before = canonicalStateJson(state);
		const first = truncateStructuredState(state);
		const second = truncateStructuredState(state);
		expect(first.oversize).toBe(false);
		expect(first.dropped).toEqual(second.dropped);
		expect(canonicalStateJson(first.state)).toBe(canonicalStateJson(second.state));
		expect(canonicalStateJson(state)).toBe(before);
	});

	it("refuses input-oversize with zero spawn when nothing is droppable left", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		// Unknown nested key = schema drift: it survives every drop step, so the
		// state stays over budget and must not be sent.
		const state = dp1State({ closure: { notes: "n".repeat(2_500) } });
		expect(validateStructuredState(DP1_ID, state)).toEqual([]);

		const result = triageDispatch({ projectDir: root, state, run: stub.run });

		expect(stub.calls).toHaveLength(0);
		expect(result.available).toBe(false);
		expect(result.reason).toBe(TRIAGE_REASON_INPUT_OVERSIZE);
		expect(result.escalate_to_human).toBe(true);
	});

	it("prepareStructuredState short-circuits on a missing field before truncating", () => {
		const prepared = prepareStructuredState(DP1_ID, dp1State({ task_summary: "决".repeat(200), risk: "" }));
		expect(prepared.ok).toBe(false);
		if (!prepared.ok) {
			expect(prepared.reason).toBe(TRIAGE_REASON_INPUT_INCOMPLETE);
			expect(prepared.missing).toContain("risk");
		}
	});
});

// ── 4. digest passthrough (TS never hashes) ─────────────────────────────────

describe("state_digest is a Python passthrough (requirement 4 / D-004)", () => {
	it("returns the digest from the response verbatim", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun({ state_digest: "d428504f067a5092" }));
		const result = triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });

		expect(result.available).toBe(true);
		expect(result.state_digest).toBe("d428504f067a5092");
	});

	it("passes an arbitrary digest through unchanged (no local hashing)", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun({ state_digest: "deadbeefdeadbeef" }));
		const result = triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });
		expect(result.state_digest).toBe("deadbeefdeadbeef");
	});

	it("keeps the digest on an unavailable response and omits it when absent", () => {
		const root = projectWithDecideJson();
		const unavailableStub = stubRunner({
			status: 0,
			timedOut: false,
			stderr: "",
			stdout: JSON.stringify({ available: false, reason: "rate-limited", state_digest: "0123456789abcdef" }),
		});
		const missing = triageDispatch({ projectDir: root, state: dp1State(), run: unavailableStub.run });
		expect(missing.available).toBe(false);
		expect(missing.reason).toBe("rate-limited");
		expect(missing.state_digest).toBe("0123456789abcdef");

		const plainStub = stubRunner(okRun());
		const plain = triageDispatch({ projectDir: root, state: dp1State(), run: plainStub.run });
		expect(plain.state_digest).toBeUndefined();
	});
});

// ── 5. the removed free-form string state is refused, never forwarded ──────

describe("free-form string state (the removed legacy path, spec §1.7)", () => {
	it("refuses a 100KB string with zero spawn instead of truncating it", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		// A JS caller can still pass prose; it is never a structured state and the
		// replaced path must not forward or truncate it.
		const result = triageDispatch({
			projectDir: root,
			state: "x".repeat(100_000) as unknown as TriageState,
			run: stub.run,
		});

		expect(result.available).toBe(false);
		expect(result.reason).toBe("input-incomplete");
		expect(result.missing_fields).toEqual(["state"]);
		expect(result.escalate_to_human).toBe(true);
		expect(stub.calls).toHaveLength(0);
	});

	it("refuses a short string state too: a state is an object, never prose", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		const result = triageDispatch({
			projectDir: root,
			state: "requested_type: coding" as unknown as TriageState,
			run: stub.run,
		});
		expect(result.available).toBe(false);
		expect(result.missing_fields).toEqual(["state"]);
		expect(stub.calls).toHaveLength(0);
	});
});

// ── 6. cross-layer dp id lock (Python registry is the authority) ────────────

const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

/** Dump `decision_points.DP_REGISTRY` ids — the authoritative cross-layer list. */
const PY_DP_REGISTRY_IDS = [
	"import json, sys",
	"sys.path.insert(0, sys.argv[1])",
	"import decision_points as d",
	"print(json.dumps([p.id for p in d.DP_REGISTRY]))",
].join("\n");

/** The dp-specific rows the `required_if` matrix still carries (registry ids):
 * dp4/dp5/dp6/dp13 are explicit legacy debt. The four business-material dps
 * (dp1/dp2/dp3/dp25) are enforced by the generated registry contract instead. */
const DP_SPECIFIC_ROWS = ["dp4-failure-handling", "dp5-test-triage", "dp6-qg-verdict", "dp13-commit-release"];

/** The four dps whose contract moved to the generated material registry. */
const MATERIAL_CONTRACT_DP_IDS = [
	"dp1-dispatch-type",
	"dp2-checkpoint-split",
	"dp3-worker-clarify",
	"dp25-signoff-conclusion",
];

/** Live registry ids. Fail-closed: this lock is a cross-layer contract, so a
 * missing interpreter or a failing subprocess fails the test (never skips). */
function pythonDpRegistryIds(): string[] {
	const result = spawnSync(PYTHON_EXE, ["-c", PY_DP_REGISTRY_IDS, MULTI_WORKERS_DIR], {
		encoding: "utf8",
		timeout: 30_000,
		env: process.env,
	});
	const stdout = (result.stdout ?? "").trim();
	if (result.status !== 0 || stdout === "") {
		throw new Error(
			`python DP_REGISTRY dump failed (status=${String(result.status)}): ${stdout}\n${result.stderr ?? ""}`,
		);
	}
	const ids = JSON.parse(stdout.split("\n").at(-1) ?? "[]") as unknown;
	if (!Array.isArray(ids) || ids.some((id) => typeof id !== "string") || ids.length === 0) {
		throw new Error(`python DP_REGISTRY dump is not a non-empty string list: ${stdout}`);
	}
	return ids as string[];
}

describe("dp ids match the Python registry (cross-layer drift lock)", () => {
	it("every REQUIRED_FIELDS_BY_DP key is a live DP_REGISTRY id", () => {
		const registryIds = pythonDpRegistryIds();
		const tableKeys = Object.keys(REQUIRED_FIELDS_BY_DP);

		// A short / misspelled / retired id never matches a real dpId, and
		// `REQUIRED_FIELDS_BY_DP[dpId] ?? []` then silently drops the whole
		// dp-specific requirement (AC-005 "输入不全就放行").
		const unknownKeys = tableKeys.filter((id) => !registryIds.includes(id));
		expect(unknownKeys, "dp ids not present in decision_points.DP_REGISTRY").toEqual([]);
		expect(tableKeys.slice().sort()).toEqual(DP_SPECIFIC_ROWS.slice().sort());

		for (const id of DP_SPECIFIC_ROWS) expect(registryIds).toContain(id);
	});

	it("DP1_ID is the registry id and the default dpId", () => {
		expect(DP1_ID).toBe("dp1-dispatch-type");
		expect(pythonDpRegistryIds()).toContain(DP1_ID);

		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });
		expect(stub.calls[0]?.dp).toBe("dp1-dispatch-type");
	});

	it("state schema version is the registry's schema_version: 2", () => {
		// `decision_points._state_builder` emits
		// `{"schema_version": 2, "decision_point": <id>}`: the version is the
		// registry's schema version, so the TS validator must accept exactly it.
		expect(validateStructuredState(DP1_ID, { ...dp1State(), schema_version: 2 })).toEqual([]);
		expect(validateStructuredState(DP1_ID, { ...dp1State(), schema_version: 1 })).toContain("schema_version");
	});

	it("the dp-specific row actually fires for every registry id", () => {
		// Registry ids must HIT the matrix (not just exist in it): a state that
		// carries only the universal fields has to be refused per dp.
		for (const dpId of DP_SPECIFIC_ROWS) {
			const state: TriageState = {
				schema_version: 2,
				decision_point: dpId,
				key: "mw-decision-substitution",
				phase: "EXECUTE",
				task_type: "coding",
				risk: "mid",
				risk_source: "machine",
				authority_tier: "P2",
				questions_version: "q-00000000",
			};
			const missing = validateStructuredState(dpId, state);
			expect(missing, `${dpId} must require its own block`).toEqual(
				expect.arrayContaining(REQUIRED_FIELDS_BY_DP[dpId]?.slice(0, 1) ?? []),
			);
			expect(missing.length, `${dpId} must have a dp-specific required field`).toBeGreaterThan(0);
		}
	});

	it("retires the pre-T01 rows for the four business-material dps", () => {
		for (const dpId of MATERIAL_CONTRACT_DP_IDS) {
			// The legacy structured validator composes UNIVERSAL_REQUIRED_FIELDS
			// (key/phase/risk/...) with this table, so keeping a row would force
			// BUSINESS material to carry audit keys.
			expect(REQUIRED_FIELDS_BY_DP, dpId).not.toHaveProperty(dpId);
			expect(DECIDE_REGISTRY[dpId]?.requiredStateFields.length, dpId).toBeGreaterThan(0);
		}
		// dp1 keeps its generated business contract even without a legacy row.
		expect(DECIDE_REGISTRY[DP1_ID]?.requiredStateFields.map((field) => field.name)).toEqual([
			"task_goal",
			"task_requirements",
			"task_deliverables",
		]);
	});

	it("dp3's dynamic candidates are required by the material contract, not local_candidates", () => {
		const names = DECIDE_REGISTRY["dp3-worker-clarify"]?.requiredStateFields.map((field) => field.name) ?? [];
		expect(names).toContain("handling_options");
		expect(names).not.toContain("local_candidates");
		// The retired row is gone; the dynamic choice is fed by the registry contract.
		expect(REQUIRED_FIELDS_BY_DP).not.toHaveProperty("dp3-worker-clarify");
	});
});

// ── 7. authority keys: verbatim passthrough (T-04c / D-041) ────────────────

const AUTHORITY_KEYS = {
	decision_id: "dp1-dispatch-type:mw-decision-substitution",
	mode: "auto",
	acted: false,
	escalated_reason: "suggest-only",
};

describe("authority keys are passthrough (T-04c / D-041)", () => {
	it("forwards decision_id / mode / acted / escalated_reason key by key", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun(AUTHORITY_KEYS));
		const result = triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });

		expect(result.available).toBe(true);
		expect(result.decision_id).toBe(AUTHORITY_KEYS.decision_id);
		expect(result.mode).toBe("auto");
		// Verbatim: Python's `acted` is reported as-is (an `answer` intent is never
		// acted by Python) — this client must not re-derive it from `mode`.
		expect(result.acted).toBe(false);
		expect(result.escalated_reason).toBe("suggest-only");
		// `escalated_reason` coexists with the legacy reason; it never replaces it.
		expect(result.reason).toBeUndefined();
	});

	it("keeps them on an unavailable response (an escalated row still correlates)", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner({
			status: 0,
			timedOut: false,
			stderr: "",
			stdout: JSON.stringify({
				available: false,
				reason: "timeout",
				decision_id: "dp1-dispatch-type:ds-t04c-unavail",
				mode: "suggest",
				acted: false,
				escalated_reason: "unavailable",
			}),
		});
		const result = triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });

		expect(result.available).toBe(false);
		expect(result.reason).toBe("timeout");
		expect(result.decision_id).toBe("dp1-dispatch-type:ds-t04c-unavail");
		expect(result.mode).toBe("suggest");
		expect(result.acted).toBe(false);
		expect(result.escalated_reason).toBe("unavailable");
	});

	it("never fabricates a missing field", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun());
		const result = triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });

		expect(result.available).toBe(true);
		expect(result.decision_id).toBeUndefined();
		expect(result.mode).toBeUndefined();
		expect(result.acted).toBeUndefined();
		expect(result.escalated_reason).toBeUndefined();
	});

	it("drops null / wrongly typed values instead of guessing", () => {
		const root = projectWithDecideJson();
		const stub = stubRunner(okRun({ decision_id: null, mode: "sometimes", acted: "yes", escalated_reason: null }));
		const result = triageDispatch({ projectDir: root, state: dp1State(), run: stub.run });

		expect(result.decision_id).toBeUndefined();
		// `mode` is the one shape-restricted key: only auto|suggest is forwarded.
		expect(result.mode).toBeUndefined();
		expect(result.acted).toBeUndefined();
		expect(result.escalated_reason).toBeUndefined();
	});
});
