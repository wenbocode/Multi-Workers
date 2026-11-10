/**
 * mw-decision-context T03 (AC-001/003/004/010/014): the PM dp1 producer sends
 * the task's ORIGINAL goal/requirements/deliverables inside the local envelope
 * `{material, meta, preparation}`, and the machine never asks a PM steer on its own.
 *
 * Locked behaviour under test:
 *  1. dp1 material = the card's 上下文 / 要求 / 交付格式 bodies verbatim (no
 *     summary, no excerpt cap, no byte truncation); the only model keys are the
 *     registry's `modelStateFields` for dp1.
 *  2. The local envelope carries `record_version:2`, a per-decision UUID
 *     `logical_id`, the owning `key`, the REAL reserved `task_key` (null when
 *     the PM decision has no task), `initiator_role:"pm"`, `retry_of:null`.
 *     Identity/audit fields never enter the model material.
 *  3. dp-w-type has one business question (triage_type) with four labels.
 *  4. A role outside coding/research/review/vision (rag-research / codex)
 *     performs ZERO decision calls and never rewrites its type.
 *  5. Missing material or an over-budget material is refused with ZERO spawn —
 *     never silently truncated.
 *  6. dp1's real consumer (the dispatch) can produce its lifecycle feedback
 *     facts for the future `mw decide lifecycle` writer; nothing is appended
 *     by the extension itself and `consumed` is never treated as completed.
 *  7. The checkpoint watchdog still wakes the PM for a mid/high risk
 *     checkpoint, but the PM loop no longer asks dp2 nor writes a narrow steer.
 *
 * Gate fixtures drive the local Python lifecycle writer and its HTTP fixture
 * through the ordinary PM tool. The suite harness uses the faux provider.
 */

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import { answerPreparedGate } from "../../src/extensions/agent-team-loop/autopilot/gate-writer.ts";
import { runAskDecision } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	DP2_CHECKPOINT_ID,
	DP2_STEER_FILE,
	pmActivate,
	registerPmGateFollowup,
	startWorkerPollLoop,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	canonicalStateBytes,
	type DecideRunner,
	type DecideRunRequest,
	DP1_ID,
	MAX_STRUCTURED_STATE_BYTES,
	newDecisionMeta,
	type RawDecideRun,
	TRIAGE_REASON_INPUT_OVERSIZE,
	type TriageState,
	triageDispatchEnvelope,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import {
	buildDp1DecisionMaterial,
	buildDp1LifecycleFact,
	type CardSections,
	computeDispatchTriage,
	type DispatchTriage,
	type Dp1DispatchPlan,
	extractCardSections,
	type PmUiHolder,
	type PmWatchState,
	registerWorkerTools,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import type { DecisionPreparation } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { PYTHON_EXE } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import type { ExtensionFactory, InlineExtension } from "../../src/index.ts";
import { createHarness, type Harness } from "./harness.ts";

const tempDirs: string[] = [];
const harnesses: Harness[] = [];

function mkProject(prefix = "mwdctx-t03-"): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	vi.unstubAllEnvs();
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	vi.useRealTimers();
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

// ── fixtures ────────────────────────────────────────────────────────────────

const GOAL = [
	"实现批准 PM dp1 原文 producer。",
	"目标锚点 .agenticdoc/goal.md:1；设计锚 .agenticdoc/mw-decision-context/design.md:34。",
	"第二行必须原样到达模型，不做摘要。",
].join("\n");

/** ~1.25 KB: longer than the retired `DP1_TASK_EXCERPT_MAX` (1200 bytes), so
 * an excerpt cap would be observable, still inside the transport budget. */
const REQUIREMENTS = [
	"## 要求",
	"",
	...Array.from(
		{ length: 15 },
		(_, i) => `- Requirement ${i + 1}: keep the original text verbatim, no summary and no truncation.`,
	),
].join("\n");

const DELIVERABLES = [
	"report.md 必须包含：",
	"- 最终材料原文与实际 stdin 例子",
	"- RED/GREEN 原日志（UTC / exit / hash）",
	"- consumer 回执接线坐标与 T05 CLI 约束",
].join("\n");

function fixtureSections(): CardSections {
	return {
		context: GOAL,
		requirements: REQUIREMENTS,
		deliverables: DELIVERABLES,
		extras: [
			{ title: "写入允许面", body: "- packages/coding-agent/src/x.ts" },
			{ title: "写入禁止面", body: "- 其它 TS" },
			{ title: "验收命令", body: "node vitest" },
			{ title: "改动历史", body: "初派" },
		],
	};
}

const dispatchPreparation: DecisionPreparation = {
	prepared_at: "2026-10-26T00:00:00Z",
	basis_catalog: [
		{
			id: "b-primary",
			text: "The original deliverables require editing the implementation.",
			material_refs: ["task_deliverables"],
			applies_to: ["coding"],
		},
	],
};

function dp1Plan(overrides: Partial<Dp1DispatchPlan> = {}): Dp1DispatchPlan & { preparation: DecisionPreparation } {
	return {
		key: "mw-decision-context",
		taskType: "coding",
		taskKey: "dc-t03-pm-producers",
		sections: fixtureSections(),
		preparation: dispatchPreparation,
		...overrides,
	};
}

/** A project whose `.mw/decide.json` enables the decision service. */
function decideProject(): string {
	const dir = mkProject();
	fs.mkdirSync(path.join(dir, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(dir, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	fs.mkdirSync(path.join(dir, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(
		path.join(dir, ".agenticdoc", "_index.parallel"),
		`| mw-decision-context | active | EXECUTE | ${windowClaimId()} | | fixture | 2026-10-26 |\n`,
	);
	return dir;
}

interface CapturedRunner {
	run: DecideRunner;
	calls: DecideRunRequest[];
}

function capturingRunner(answer?: string): CapturedRunner {
	const calls: DecideRunRequest[] = [];
	const run: DecideRunner = (request) => {
		calls.push(request);
		const payload = {
			available: true,
			mode: "auto",
			acted: false,
			confidence_source: "api",
			decision_id: `${DP1_ID}:${envelopeOf(request).meta.logical_id}`,
			answers: { triage_type: { value: answer ?? "coding", confidence: 0.9 }, basis_id: { value: "b-primary" } },
		};
		const raw: RawDecideRun = { status: 0, stdout: JSON.stringify(payload), stderr: "", timedOut: false };
		return raw;
	};
	return { run, calls };
}

function envelopeOf(request: DecideRunRequest): {
	material: Record<string, unknown>;
	meta: Record<string, unknown>;
	preparation: DecisionPreparation;
} {
	return JSON.parse(request.input);
}

function triageWith(
	runner: DecideRunner,
	plan: Dp1DispatchPlan = dp1Plan(),
	projectDir = decideProject(),
): DispatchTriage | null {
	return computeDispatchTriage({
		projectDir,
		dispatchedType: plan.taskType ?? "coding",
		run: runner,
		dp1: plan,
	});
}

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** Fields that must never reach the model material (identity + audit). */
const IDENTITY_KEYS = [
	"schema_version",
	"decision_point",
	"questions_version",
	"key",
	"task_key",
	"phase",
	"task_type",
	"requested_type",
	"risk",
	"risk_source",
	"authority_tier",
	"task_summary",
	"scope",
	"context",
	"progress",
	"triage_risk",
];

// ── 1. AC-001 / AC-003: original text material on the wire ──────────────────

describe("dp1 producer sends the original task material (AC-001)", () => {
	it("accepts the prepared dispatch fixture at the claimed T11 host boundary", () => {
		const projectDir = decideProject();
		const runner = capturingRunner();
		const result = triageDispatchEnvelope({
			projectDir,
			dpId: DP1_ID,
			material: {
				task_goal: GOAL,
				task_requirements: REQUIREMENTS,
				task_deliverables: DELIVERABLES,
				images_required: false,
			},
			meta: newDecisionMeta({ key: OWNER, taskKey: TASK, initiatorRole: "pm" }),
			preparation: dispatchPreparation,
			run: runner.run,
		});
		expect(runner.calls).toHaveLength(1);
		expect(result).toMatchObject({ available: true, basis: dispatchPreparation.basis_catalog[0] });
	});
	it("builds material from the card's three bodies verbatim, never a summary", () => {
		const built = buildDp1DecisionMaterial(dp1Plan());
		expect(built.ok).toBe(true);
		if (!built.ok) return;
		expect(Object.keys(built.material).sort()).toEqual([...(DECIDE_REGISTRY[DP1_ID]?.modelStateFields ?? [])].sort());
		expect(built.material.task_goal).toBe(GOAL);
		expect(built.material.task_requirements).toBe(REQUIREMENTS);
		expect(built.material.task_deliverables).toBe(DELIVERABLES);
		expect(built.material.images_required).toBe(false);
		// No excerpt cap: the requirements body is reproduced byte for byte.
		expect(Buffer.byteLength(built.material.task_requirements, "utf8")).toBe(Buffer.byteLength(REQUIREMENTS, "utf8"));
		expect(built.material.task_requirements.length).toBeGreaterThan(1200);
		console.log(
			`[VERIFY] VC-001: producers=1/1 material_bytes=${built.bytes} fields=${Object.keys(built.material).length}`,
		);
	});

	it("keeps the prepared basis and identity outside the model material", () => {
		const runner = capturingRunner();
		const triage = triageWith(runner.run);
		expect(triage).not.toBeNull();
		expect(runner.calls).toHaveLength(1);
		const request = runner.calls[0];
		if (!request) throw new Error("no decision request captured");
		expect(request.dp).toBe(DP1_ID);
		const envelope = envelopeOf(request);
		expect(Object.keys(envelope).sort()).toEqual(["material", "meta", "preparation"]);
		expect(envelope.preparation).toEqual(dispatchPreparation);
		expect(Object.keys(envelope.material).sort()).toEqual(
			[...(DECIDE_REGISTRY[DP1_ID]?.modelStateFields ?? [])].sort(),
		);
		for (const key of IDENTITY_KEYS) {
			expect(envelope.material, `material must not carry ${key}`).not.toHaveProperty(key);
		}
		// Identity lives in the local envelope only.
		expect(envelope.meta).toMatchObject({
			record_version: 2,
			key: "mw-decision-context",
			task_key: "dc-t03-pm-producers",
			initiator_role: "pm",
			retry_of: null,
		});
		expect(String(envelope.meta.logical_id)).toMatch(UUID_V4);
		// The question set is registry-authoritative: no `questions` map on the wire.
		expect(envelope).not.toHaveProperty("questions");
		expect(triage?.statePath).toBe("material");
		expect(triage?.stateTrace).toMatch(/^\[DECISION\] dp1 state=material bytes=\d+$/);
		console.log(
			`[VERIFY] VC-003: dp1 stdin=${request.input.slice(0, 120)}... meta_role=${String(envelope.meta.initiator_role)}`,
		);
	});

	it("asks one triage_type business question with the four registered labels (VC-003)", () => {
		const registryPath = fileURLToPath(new URL("../../../multi-workers/decide_registry.json", import.meta.url));
		const registry = JSON.parse(fs.readFileSync(registryPath, "utf8")) as {
			points: Array<{
				id: string;
				questions: Array<{ id: string; choices?: string[]; labels?: Record<string, string> }>;
				model_state_fields?: string[];
			}>;
		};
		const dp1 = registry.points.find((point) => point.id === DP1_ID);
		if (!dp1) throw new Error("dp1 not in registry");
		expect(dp1.questions).toHaveLength(1);
		const question = dp1.questions[0];
		if (!question) throw new Error("dp1 question missing");
		expect(question.id).toBe("triage_type");
		expect(question.choices).toEqual(["coding", "research", "review", "vision"]);
		expect(Object.keys(question.labels ?? {}).sort()).toEqual(["coding", "research", "review", "vision"]);
		expect(Object.values(question.labels ?? {})).toHaveLength(4);
		expect(dp1.model_state_fields).toEqual([
			"task_goal",
			"task_requirements",
			"task_deliverables",
			"images_required",
		]);
		const runner = capturingRunner();
		triageWith(runner.run);
		const wire = runner.calls[0]?.input ?? "";
		expect(wire).not.toContain("triage_risk");
		expect(wire).not.toContain('"reason"');
		console.log(`[VERIFY] VC-003: questions=1 choices=${question.choices?.join("/")} labels=4`);
	});
});

// ── 2. AC-010: ids and association ──────────────────────────────────────────

describe("decision identity (AC-010)", () => {
	it("mints one independent logical_id per decision and keeps retry_of null", () => {
		const first = newDecisionMeta({ key: "mw-decision-context", taskKey: "dc-t03-pm-producers" });
		const second = newDecisionMeta({ key: "mw-decision-context", taskKey: "dc-t03-pm-producers" });
		expect(first.logical_id).toMatch(UUID_V4);
		expect(second.logical_id).toMatch(UUID_V4);
		expect(first.logical_id).not.toBe(second.logical_id);
		expect(first.retry_of).toBeNull();
		expect(first.record_version).toBe(2);
	});

	it("associates the reserved task_key and keeps a task-less PM decision null (no guessing)", () => {
		const projectDir = decideProject();
		// A decoy task exists on disk: the producer must NOT adopt "the latest".
		fs.mkdirSync(path.join(projectDir, ".agenticdoc", "mw-decision-context", "workers", "some-other-task"), {
			recursive: true,
		});
		const runner = capturingRunner();
		triageWith(runner.run, dp1Plan({ taskKey: "dc-t03-pm-producers" }), projectDir);
		const meta = envelopeOf(runner.calls[0] as DecideRunRequest).meta;
		expect(meta.task_key).toBe("dc-t03-pm-producers");
		expect(meta.key).toBe("mw-decision-context");

		const noTask = capturingRunner();
		triageWith(noTask.run, dp1Plan({ taskKey: undefined }), projectDir);
		const noTaskMeta = envelopeOf(noTask.calls[0] as DecideRunRequest).meta;
		expect(noTaskMeta.task_key).toBeNull();
		expect(noTaskMeta.retry_of).toBeNull();
		console.log(`[VERIFY] VC-010: inferred_task_links=0 task_key=${String(meta.task_key)} null_ok=1`);
	});
});

// ── 3. dp1 boundaries: unsupported roles, missing/oversize material ─────────

describe("dp1 boundaries (zero spawn)", () => {
	it("keeps rag-research/codex outside dp-w-type: no decision call, type unchanged", () => {
		for (const taskType of ["rag-research", "codex"]) {
			const runner = capturingRunner();
			const plan = dp1Plan({ taskType, sections: fixtureSections() });
			expect(buildDp1DecisionMaterial(plan)).toEqual({ ok: false, reason: "unsupported-type" });
			const triage = triageWith(runner.run, plan);
			expect(runner.calls, taskType).toHaveLength(0);
			expect(triage?.statePath, taskType).toBe("skipped");
			expect(triage?.stateTrace, taskType).toBe("[DECISION] dp1 state=skipped reason=unsupported-type");
			expect(triage?.result.available, taskType).toBe(false);
			expect(triage?.decision, taskType).toBeUndefined();
			// The dispatched type is carried through untouched — dp1 never rewrites it.
			expect(triage?.dispatchedType, taskType).toBe(taskType);
		}
		console.log("[VERIFY] VC-001: unsupported_role_calls=0 types=rag-research/codex");
	});

	it("refuses blank material with zero spawn (no fabricated goal/requirements)", () => {
		const runner = capturingRunner();
		const plan = dp1Plan({
			sections: { context: GOAL, requirements: "   ", deliverables: DELIVERABLES, extras: [] },
		});
		const triage = triageWith(runner.run, plan);
		expect(runner.calls).toHaveLength(0);
		expect(triage?.statePath).toBe("skipped");
		expect(triage?.stateTrace).toBe("[DECISION] dp1 state=skipped reason=missing-material");
		expect(triage?.decision).toBeUndefined();
	});

	it("keeps necessary material verbatim (no legacy-2000B truncation) and refuses only an explicitly configured budget", () => {
		const huge = `${"长".repeat(1200)}-tail-must-survive`;
		const plan = dp1Plan({
			sections: { context: huge, requirements: huge, deliverables: huge, extras: [] },
		});
		// The builder keeps the material verbatim (no silent shrinking) ...
		const built = buildDp1DecisionMaterial(plan);
		expect(built.ok).toBe(true);
		if (built.ok) {
			expect(built.material.task_goal).toBe(huge);
			expect(built.material.task_goal.endsWith("-tail-must-survive")).toBe(true);
		}
		// ... and with no configured client ceiling the whole material goes on the
		// wire: the real budget is the transport's (design §2), not the legacy
		// 2000B state constant.
		const runner = capturingRunner();
		const triage = triageWith(runner.run, plan);
		expect(runner.calls).toHaveLength(1);
		const sentMaterial = envelopeOf(runner.calls[0] as DecideRunRequest).material;
		expect(sentMaterial.task_goal).toBe(huge);
		expect(triage?.statePath).toBe("material");
		expect(canonicalStateBytes(sentMaterial)).toBeGreaterThan(MAX_STRUCTURED_STATE_BYTES);
		// An EXPLICIT budget refuses the same material as a whole (zero spawn).
		const spy = capturingRunner();
		const refusedByBudget = triageDispatchEnvelope({
			projectDir: decideProject(),
			dpId: DP1_ID,
			material: sentMaterial as TriageState,
			preparation: dispatchPreparation,
			meta: newDecisionMeta({ key: "mw-decision-context", taskKey: "t", initiatorRole: "pm" }),
			policy: {
				enabled: true,
				dp1Enabled: true,
				alertOnDisagreement: false,
				notifyOnUnavailable: false,
				timeoutMs: 1,
			},
			maxBytes: MAX_STRUCTURED_STATE_BYTES,
			run: spy.run,
		});
		expect(spy.calls).toHaveLength(0);
		expect(refusedByBudget.available).toBe(false);
		expect(refusedByBudget.reason).toBe(TRIAGE_REASON_INPUT_OVERSIZE);
		console.log(
			`[VERIFY] VC-020: truncation=0 legacy_cap_gates_material=0 explicit_budget_refused=1 bytes=${canonicalStateBytes(sentMaterial)}`,
		);
	});

	it("propagates the transport refusal reason for an over-budget envelope", () => {
		const meta = newDecisionMeta({ key: "mw-decision-context", taskKey: "t", initiatorRole: "pm" });
		const result = triageDispatchEnvelope({
			projectDir: decideProject(),
			dpId: DP1_ID,
			preparation: dispatchPreparation,
			material: {
				task_goal: "g".repeat(900),
				task_requirements: "r".repeat(900),
				task_deliverables: "d".repeat(900),
			},
			meta,
			maxBytes: MAX_STRUCTURED_STATE_BYTES,
			policy: {
				enabled: true,
				dp1Enabled: true,
				alertOnDisagreement: false,
				notifyOnUnavailable: false,
				timeoutMs: 1,
			},
			run: capturingRunner().run,
		});
		expect(result.available).toBe(false);
		expect(result.reason).toBe(TRIAGE_REASON_INPUT_OVERSIZE);
		expect(result.escalate_to_human).toBe(true);
	});
});

// ── 4. AC-014: the real consumer's feedback facts (no naked append) ─────────

describe("dp1 consumer feedback facts (AC-014)", () => {
	it("derives the T05 enclosures from the same decision, without writing", () => {
		const runner = capturingRunner("coding");
		const triage = triageWith(runner.run);
		if (!triage) throw new Error("expected a dispatch triage");
		const logicalId = triage.meta?.logical_id ?? "";
		const decisionId = triage.result.decision_id ?? "";
		expect(logicalId).toMatch(UUID_V4);
		expect(decisionId).toBe(`${DP1_ID}:${logicalId}`);

		const consumed = buildDp1LifecycleFact(triage, "consumed", { answer: "coding" });
		const executed = buildDp1LifecycleFact(triage, "executed", {
			action: "type-read",
			result: "dispatched:dc-t03-pm-producers",
		});
		const settled = buildDp1LifecycleFact(triage, "settled", { outcome: "ok" });
		for (const [stage, fact] of [
			["consumed", consumed],
			["executed", executed],
			["settled", settled],
		] as const) {
			expect(fact, stage).toBeDefined();
			// Same-decision association: one decision_id, one logical_id.
			expect(fact?.decision_id, stage).toBe(decisionId);
			expect(fact?.meta.logical_id, stage).toBe(logicalId);
			expect(fact?.dp, stage).toBe(DP1_ID);
			expect(fact?.stage, stage).toBe(stage);
			expect(fact?.event_id, stage).toBe(`dp1:${logicalId}:${stage}`);
			expect(fact?.event_id, stage).toMatch(/^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$/);
		}
		// T02's closed stage fields: only the stage's own slot is carried.
		expect(consumed).toMatchObject({ answer: "coding" });
		expect(consumed).not.toHaveProperty("action");
		expect(consumed).not.toHaveProperty("outcome");
		expect(executed).toMatchObject({ action: "type-read", result: "dispatched:dc-t03-pm-producers" });
		expect(executed).not.toHaveProperty("answer");
		expect(executed).not.toHaveProperty("outcome");
		expect(settled).toMatchObject({ outcome: "ok" });
		expect(settled).not.toHaveProperty("action");
		// Stage mixing is refused locally (the Python writer refuses it too).
		expect(buildDp1LifecycleFact(triage, "consumed", { action: "type-read" })).toBeUndefined();
		expect(buildDp1LifecycleFact(triage, "executed", { outcome: "ok" })).toBeUndefined();
		expect(buildDp1LifecycleFact(triage, "settled", { action: "type-read" })).toBeUndefined();
		// Nothing is appended by the builder itself (the Python writer is T05).
		const lifecycleLedger = path.join(
			path.dirname(triage.meta ? (runner.calls[0]?.projectDir ?? "") : ""),
			"_autopilot",
			"decision-lifecycle.jsonl",
		);
		expect(fs.existsSync(lifecycleLedger)).toBe(false);
		console.log(`[VERIFY] VC-014: false_completions=0 logical_id=${logicalId} stages=3 bare_appends=0`);
	});

	it("has no consumed fact when the decision was never answered", () => {
		const run: DecideRunner = () => ({
			status: 0,
			stdout: JSON.stringify({ available: false, reason: "entry-unavailable" }),
			stderr: "",
			timedOut: false,
		});
		const triage = triageWith(run);
		expect(triage).not.toBeNull();
		// No answer arrived, so `consumed` must not be claimed.
		expect(buildDp1LifecycleFact(triage, "consumed", { answer: "coding" })).toBeUndefined();
		// No decision record exists either (the child reported no decision_id), so
		// there is nothing to join a settled fact to: no invented association.
		expect(buildDp1LifecycleFact(triage, "settled", { outcome: "rework" })).toBeUndefined();

		// An escalated row DOES carry the child's decision_id (record-start exists), so
		// the round can settle as rework — but still never claims `consumed`.
		const escalated = triageWith((req) => ({
			status: 0,
			stdout: JSON.stringify({
				available: false,
				reason: "input-oversize",
				decision_id: `${DP1_ID}:${envelopeOf(req).meta.logical_id}`,
				mode: "auto",
				acted: false,
			}),
			stderr: "",
			timedOut: false,
		}));
		expect(buildDp1LifecycleFact(escalated, "consumed", { answer: "coding" })).toBeUndefined();
		expect(buildDp1LifecycleFact(escalated, "settled", { outcome: "rework" })).toMatchObject({
			stage: "settled",
			outcome: "rework",
		});
	});
});

// ── 5. AC-001 end-to-end: the real dispatch_worker tool path (harness+faux) ──

const OWNER = "mw-decision-context";
const TASK = "dc-t03-pm-producers";

function writePhaseDocs(root: string, key: string): void {
	const keyDir = path.join(root, key);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.writeFileSync(path.join(keyDir, "spec.md"), `# Spec\n${"x".repeat(600)}\n\n| AC-001 | ok |\n`, "utf8");
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}`, "utf8");
	const research = path.join(keyDir, "evidence", "research");
	fs.mkdirSync(research, { recursive: true });
	fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "# research\n", "utf8");
	fs.writeFileSync(path.join(research, "design-topic-2026-01-01.md"), "# research\n", "utf8");
}

/** A complete coding dispatch card (envelope + coding extras + seed minimum). */
const CARD_BODY = [
	"type: coding",
	"",
	"## 上下文",
	"",
	GOAL,
	"",
	"## 要求",
	"",
	REQUIREMENTS,
	"",
	"## 交付格式",
	"",
	DELIVERABLES,
	"",
	"## 写入允许面",
	"",
	"- packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts",
	"",
	"## 写入禁止面",
	"",
	"- 其它 TS",
	"",
	"## 验收命令",
	"",
	"- node vitest --run test/suite/decision-context-pm-producers.test.ts",
	"",
	"## 改动历史",
	"",
	"- 初派",
	"",
].join("\n");

function writeCard(projectDir: string): string {
	const dir = path.join(projectDir, ".agenticdoc", OWNER, "tasks");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(path.join(projectDir, ".agenticdoc", "goal.md"), "# goal\n", "utf8");
	const cardPath = path.join(dir, "T03-pm-producers.md");
	fs.writeFileSync(cardPath, CARD_BODY, "utf8");
	return cardPath;
}

async function dispatchThroughTool(projectDir: string): Promise<{ calls: DecideRunRequest[]; text: string }> {
	const calls: DecideRunRequest[] = [];
	const triageRun: DecideRunner = (request) => {
		calls.push(request);
		return {
			status: 0,
			stdout: JSON.stringify({
				available: true,
				mode: "auto",
				acted: false,
				confidence_source: "api",
				decision_id: `${DP1_ID}:${envelopeOf(request).meta.logical_id}`,
				answers: { triage_type: { value: "coding", confidence: 0.9 }, basis_id: { value: "b-primary" } },
			}),
			stderr: "",
			timedOut: false,
		};
	};
	const agenticdocRoot = path.join(projectDir, ".agenticdoc");
	const cardPath = writeCard(projectDir);
	writePhaseDocs(agenticdocRoot, OWNER);
	const extensionFactories: Array<ExtensionFactory | InlineExtension> = [
		(pi) => {
			registerWorkerTools(
				pi,
				new WorkerStore(agenticdocRoot),
				new AckStore(agenticdocRoot),
				new IndexStore(agenticdocRoot),
				agenticdocRoot,
				{ key: OWNER } satisfies PmWatchState,
				projectDir,
				triageRun,
			);
		},
	];
	const harness = await createHarness({ extensionFactories });
	harnesses.push(harness);
	harness.setResponses([
		fauxAssistantMessage(
			fauxToolCall("dispatch_worker", {
				decision_preparation: dispatchPreparation,
				task_key: TASK,
				card_path: cardPath,
				description: "实现 dp1 原文 producer。",
				type: "coding",
				key: OWNER,
			}),
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage("done"),
	]);
	await harness.session.prompt("dispatch the T03 card");
	const results = harness.session.messages.filter((message) => message.role === "toolResult");
	const text = JSON.stringify(results.at(-1)?.content ?? "");
	return { calls, text };
}

describe("real dispatch_worker producer (harness + faux, AC-001)", () => {
	it("sends the card's original text through the production dispatch path", async () => {
		const projectDir = decideProject();
		const { calls, text } = await dispatchThroughTool(projectDir);
		expect(calls).toHaveLength(1);
		const request = calls[0];
		if (!request) throw new Error("dispatch produced no decision request");
		expect(request.dp).toBe(DP1_ID);
		const envelope = envelopeOf(request);
		expect(Object.keys(envelope).sort()).toEqual(["material", "meta", "preparation"]);
		expect(envelope.preparation).toEqual(dispatchPreparation);
		const sections = extractCardSections(CARD_BODY);
		expect(envelope.material.task_goal).toBe(sections.context);
		expect(envelope.material.task_requirements).toBe(sections.requirements);
		expect(envelope.material.task_deliverables).toBe(sections.deliverables);
		expect(envelope.meta).toMatchObject({
			record_version: 2,
			key: OWNER,
			task_key: TASK,
			initiator_role: "pm",
			retry_of: null,
		});
		expect(text).toContain("Dispatched worker");
		const taskMd = fs.readFileSync(path.join(projectDir, ".agenticdoc", OWNER, "workers", TASK, "task.md"), "utf8");
		expect(taskMd).toContain("type: coding");
		expect(
			fs.readFileSync(path.join(projectDir, ".agenticdoc", OWNER, "workers", TASK, "trace.log"), "utf8"),
		).toContain("[DECISION] dp1 state=material bytes=");
		console.log(`[EVIDENCE] dp1 stdin=${request.input}`);
		console.log(
			`[VERIFY] VC-001: producers=1/1 path=dispatch_worker material_bytes=${canonicalStateBytes(envelope.material)} task_key=${String(envelope.meta.task_key)}`,
		);
	});
});

// ── 6. AC-004: dp2 is PM-initiated only; the watchdog alert stays ──────────

function checkpointLine(elapsedS: number, reads: number, writes: number, risk = "mid"): string {
	return (
		`[CHECKPOINT] 2026-10-20T10:00:00Z elapsed=${elapsedS}s reads=${reads} writes=${writes}` +
		` phases=1/3 uniq_targets=2 repeat_top=5 risk=${risk}`
	);
}

interface Sent {
	content: string;
	triggerTurn: boolean | undefined;
}

function fakePi(): { pi: unknown; sent: Sent[] } {
	const sent: Sent[] = [];
	const pi = {
		sendMessage: (message: { content: string }, opts?: { triggerTurn?: boolean }) => {
			sent.push({ content: message.content, triggerTurn: opts?.triggerTurn });
		},
		appendEntry: () => undefined,
	};
	return { pi, sent };
}

async function runPollTicks(projectDir: string, ticks = 4): Promise<Sent[]> {
	const agenticdocRoot = path.join(projectDir, ".agenticdoc");
	const taskDir = path.join(agenticdocRoot, OWNER, "workers", TASK);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\nphase: EXECUTE\ntimeout: 40\n\nwork\n", "utf8");
	fs.writeFileSync(path.join(taskDir, "trace.log"), `${checkpointLine(1800, 12, 3)}\n`, "utf8");
	await new WorkerStore(agenticdocRoot).upsert({
		taskKey: TASK,
		status: "running",
		cli: "pi",
		provider: "timi",
		taskPath: path.join(taskDir, "task.md"),
		dispatchedAt: "",
		updatedAt: "",
		model: "",
	});
	await new IndexStore(agenticdocRoot).upsert({
		key: OWNER,
		status: "active",
		phase: "EXECUTE",
		claimId: "1",
		deps: "",
		desc: "",
		updated: new Date().toISOString(),
	});
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(projectDir, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	fs.writeFileSync(
		path.join(projectDir, ".mw", "decide-points.json"),
		`${JSON.stringify({ version: 1, points: { [DP2_CHECKPOINT_ID]: { tier: "P2", enabled: true, mode: "auto" } } })}\n`,
		"utf8",
	);
	const watch: PmWatchState = { key: OWNER };
	const ui: PmUiHolder = { ctx: undefined };
	const { pi, sent } = fakePi();
	vi.useFakeTimers();
	try {
		const handle = startWorkerPollLoop(
			pi as Parameters<typeof startWorkerPollLoop>[0],
			new WorkerStore(agenticdocRoot),
			new AckStore(agenticdocRoot),
			new IndexStore(agenticdocRoot),
			agenticdocRoot,
			watch,
			ui,
			100,
		);
		vi.advanceTimersByTime(100 * ticks + 10);
		clearInterval(handle);
	} finally {
		vi.useRealTimers();
	}
	return sent;
}

describe("dp2 is PM-initiated only (AC-004)", () => {
	it("registers the PM gate successor on the ordinary tool surface and refuses an unclaimed window", async () => {
		const dir = mkProject();
		const harness = await createHarness({
			extensionFactories: [(pi) => pmActivate(pi, dir)],
		});
		harnesses.push(harness);
		harness.setResponses([
			fauxAssistantMessage(
				fauxToolCall("pm_gate_followup", {
					gate_id: "gate-0001",
					restricted_action: "split",
					material: {},
					preparation: {
						prepared_at: "2026-10-26T00:00:00Z",
						basis_catalog: [{ id: "b", text: "Evidence", material_refs: ["task_goal"], applies_to: ["split"] }],
					},
				}),
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("done"),
		]);
		await harness.session.prompt("Resume this gate");
		const result = harness.session.messages.find((message) => message.role === "toolResult");
		expect(JSON.stringify(result)).toContain("pm-claim-missing");
	});
	it("never asks dp2 from the PM loop but still wakes the PM on a mid-risk checkpoint", async () => {
		const projectDir = mkProject("mwdctx-t03-watchdog-");
		const sent = await runPollTicks(projectDir);
		// The module exposes no runner seam for dp2 any more: the loop literally
		// cannot ask. The static check below pins that; the alert must still fire.
		expect(sent).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBe(true);
		expect(sent[0]?.content.startsWith(`[mw] 发散风险：worker '${TASK}' 检查点 risk=mid`)).toBe(true);
		expect(sent[0]?.content).not.toContain("dp2");
		expect(sent[0]?.content).not.toContain("[dp2-narrow-fallback]");
		expect(fs.existsSync(path.join(projectDir, ".agenticdoc", OWNER, "workers", TASK, DP2_STEER_FILE))).toBe(false);
		console.log(`[VERIFY] VC-004: auto_checkpoint_calls=0 alerts=1 triggerTurn=${String(sent[0]?.triggerTurn)}`);
	});

	it("keeps the dp2 registry question/labels intact for the future PM tool (AC-004)", () => {
		const registryPath = fileURLToPath(new URL("../../../multi-workers/decide_registry.json", import.meta.url));
		const registry = JSON.parse(fs.readFileSync(registryPath, "utf8")) as {
			points: Array<{
				id: string;
				questions: Array<{
					id: string;
					instructions?: string;
					choices?: string[];
					labels?: Record<string, string>;
				}>;
			}>;
		};
		const dp2 = registry.points.find((point) => point.id === DP2_CHECKPOINT_ID);
		if (!dp2) throw new Error("dp2 not in registry");
		expect(dp2.questions).toHaveLength(1);
		const question = dp2.questions[0];
		expect(question?.id).toBe("checkpoint_action");
		expect(question?.choices).toEqual(["narrow", "split", "direct-exec", "escalate"]);
		expect(question?.labels?.narrow).toContain("收窄");
		expect(question?.labels?.split).toContain("拆");
		expect(question?.labels?.["direct-exec"]).toContain("直接做完");
		expect(question?.labels?.escalate).toContain("风险高");
		console.log(`[VERIFY] VC-004: dp2_choices=${question?.choices?.join("/")} labels=4`);
	});

	it("has no automatic dp2 call or automatic narrow execution left in the loop", () => {
		const source = fs.readFileSync(
			fileURLToPath(new URL("../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts", import.meta.url)),
			"utf8",
		);
		const start = source.indexOf("export function startWorkerPollLoop");
		expect(start).toBeGreaterThan(-1);
		const nextExport = source.indexOf("\nexport ", start + 1);
		const loopBody = source.slice(start, nextExport === -1 ? undefined : nextExport);
		expect(loopBody).not.toContain("decideDp2Checkpoint");
		expect(loopBody).not.toContain("writeDp2SteerRequest");
		expect(loopBody).not.toContain("appendDp2ActedTrace");
		expect(loopBody).not.toContain("probeDp2TaskLiveness");
		expect(loopBody).not.toContain("dp2Fallback");
		// The generic checkpoint alarm stays (it is the mechanism the user kept).
		expect(loopBody).toContain("deliverPmAlert");
		expect(loopBody).toContain("发散风险");
	});
});

const gateFixture = `
import hashlib, json, pathlib, sys
import pytest
from autopilot import gates
import decision_lifecycle as life
import decision_wire as wire
import test_dp_consolidation_materials as f
root, owner, phase, target, choice, window = sys.argv[1:]
root = pathlib.Path(root)
parent = phase == "gate"
dp = "dp-gate-approve" if parent else target
payload = {} if parent else json.load(sys.stdin)
if parent:
    key = life.DecisionMeta.create(owner, initiator_role="pm")
    gate = gates.create(root/".agenticdoc"/"_autopilot"/"gates", "stage-confirm", "Review this step",
                        stage=1, key=None if target == "dp-auto" else owner, pm_note="Prepared PM plan", matter_ref="task-main", substantive_version="v1")
    gate_choice = "steer" if target == "dp-pm-steer" else "need_fix"
    material = f._material(dp)
    prep = f._preparation(dp, material)
else:
    data = payload["meta"]
    key = life.DecisionMeta(**data)
    material, prep = payload["material"], payload["preparation"]
ref = dp + ":" + key.logical_id
store = life.LifecycleStore.production(root, redact=wire.SubstringRedactor([f.API_KEY]))
actor = ("system", "pm:" + window)
if phase == "split-effect":
    tasks = root/".agenticdoc"/owner/"tasks"
    for name, surface in (("ui", "ui.ts"), ("reader", "reader.py")):
        card = tasks / (name + ".md")
        with card.open("x",encoding="utf-8") as stream:
            stream.write("Implement and verify the " + name + " unit within " + surface)
    event = life.record_executed(store,key,decision_id=ref,dp=dp,actor=actor,action="split",
        result="Prepared two independent task cards: ui.md and reader.md",event_id="split-two-cards")
    assert event.recorded
    print(event.event_id)
    sys.exit(0)
assert life.record_start(store,key,decision_id=ref,actor=actor).recorded
if parent:
    stage_note = "nt:stage-gate:" + hashlib.sha256(json.dumps(
        [owner, gate.stem, 1, "task-main", "v1", ref], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert life.record_note(store,key,decision_id=ref,pm_note="Prepared PM plan",prepared_at=prep["prepared_at"],
                            event_id=stage_note if target=="dp-auto" else None,actor=actor).recorded
with pytest.MonkeyPatch.context() as patch:
    selected = gate_choice if parent else choice
    if selected == "first-prepared":
        selected = f._legal_choice(dp, material)
    answers = {f.BUSINESS_QIDS[dp]: f._choice_answer(selected), "basis_id": f._choice_answer(prep["basis_catalog"][0]["id"])}
    fake = f.FakeHttp(lambda *args:f._body(dp,answers))
    patch.setattr(f.backends,"_http_post",fake)
    result = f._make_client(root,patch).request_prepared(dp,material,prep,actor_role="pm")
    assert len(fake.calls)==1 and result["business_decisions"]==1, result.get("issues")
    assert life.record_request(store,key,decision_id=ref,result=result,material=material,preparation=prep,
        parent_ref=None if parent else payload["parent_decision_ref"],actor=actor).recorded
if parent:
    subject=f._material(target)
    print(json.dumps({"gate":str(gate),"gate_ref":ref,"parent_basis":result["basis_text"],"allowed_action": choice if choice != "first-prepared" else f._legal_choice(target,subject),
        "material":subject,"preparation":f._preparation(target,subject)}))
else:
    print(json.dumps({"available":True,"mode":"auto","acted":False,"decision_id":ref,"dp":dp,"logical_id":key.logical_id,
        "answers":{f.BUSINESS_QIDS[dp]:{"value":result["choice"]},"basis_id":{"value":result["basis_id"]}}}))
`;

describe("claimed PM gate follow-up (AC-045/049)", () => {
	it.each([
		["dp-pm-steer", "narrow", "Complete the original deliverable by isolating the outstanding assertion."],
		["dp-pm-steer", "split", "The UI fixture and Python reader have independent files and verification."],
		["dp-pm-steer", "direct-exec", "The running PM holds the failure reproduction in this window."],
		["dp-pm-steer", "escalate", "Only the owner can authorize the new scope. May this task edit the schema?"],
		["dp-auto", "first-prepared", "Use the already prepared repair candidate within its declared scope."],
		["dp-pm-steer", "not-prepared", "Its cited material is missing."],
		["dp-pm-steer", "in-progress", "The reserved successor already has a live writer."],
		["dp-pm-steer", "failed", "The prepared request reaches an unavailable backend."],
	])("submits the bound %s request and keeps %s separate from execution", async (target, choice, basis) => {
		const root = mkProject();
		const card = writeCard(root);
		const doc = path.join(root, ".agenticdoc");
		const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
		vi.stubEnv("MW_PY", path.join(mw, "mw.py"));
		const window = windowClaimId();
		expect((await new IndexStore(doc).claim(OWNER, window, () => false)).ok).toBe(true);
		const call = (stage: string, input = "") =>
			execFileSync(PYTHON_EXE, ["-B", "-X", "utf8", "-c", gateFixture, root, OWNER, stage, target, choice, window], {
				cwd: mw,
				input,
				encoding: "utf8",
				windowsHide: true,
			});
		const initial: {
			gate: string;
			gate_ref: string;
			parent_basis: string;
			allowed_action: string;
			material: Record<string, unknown>;
			preparation: DecisionPreparation;
		} = JSON.parse(call("gate"));
		fs.writeFileSync(
			path.join(doc, "_autopilot", "config.json"),
			JSON.stringify({ enabled: true, auto_gate_mode: "live" }),
		);
		expect(
			(
				await answerPreparedGate({
					gateFile: initial.gate,
					lockFile: path.join(root, ".mw", "gates.lock"),
					decision: target === "dp-auto" ? "need_fix" : "steer",
					matterRef: "task-main",
					substantiveVersion: "v1",
					note: "Prepared PM plan",
					modelBasis: initial.parent_basis,
					decisionRef: initial.gate_ref,
					answeredBy: window,
				})
			).ok,
		).toBe(true);
		const unchanged = fs.readFileSync(initial.gate, "utf8");
		initial.preparation.basis_catalog[0].text = basis;
		const envelopeInputs: string[] = [];
		const h = await createHarness({
			extensionFactories: [
				(pi) =>
					registerPmGateFollowup(pi, root, new WorkerStore(doc), { key: OWNER }, (input) =>
						runAskDecision({
							...input,
							runner: async (req) => {
								envelopeInputs.push(req.input);
								if (choice === "failed")
									return {
										status: 2,
										stdout: JSON.stringify({ available: false, reason: "provider-unavailable" }),
										stderr: "",
										timedOut: false,
									};
								return { status: 0, stdout: call("successor", req.input), stderr: "", timedOut: false };
							},
							lifecycleRunner: async () => ({
								status: 2,
								stdout: "",
								stderr: "fixture does not write an automatic consumed receipt",
								timedOut: false,
							}),
						}),
					),
			],
		});
		harnesses.push(h);
		const invoke = async (params: Record<string, unknown>) => {
			h.setResponses([
				fauxAssistantMessage(fauxToolCall("pm_gate_followup", params), { stopReason: "toolUse" }),
				fauxAssistantMessage("done"),
			]);
			await h.session.prompt("Inspect this prepared work item");
			const last = h.session.messages.filter((m) => m.role === "toolResult").at(-1);
			return last?.role === "toolResult" ? last : undefined;
		};
		const hasSourceWorker = choice === "direct-exec";
		if (hasSourceWorker || choice === "in-progress") {
			const dir = path.join(doc, OWNER, "workers", TASK);
			fs.mkdirSync(dir, { recursive: true });
			const taskPath = path.join(dir, "task.md");
			fs.writeFileSync(taskPath, CARD_BODY);
			fs.writeFileSync(path.join(dir, "trace.log"), checkpointLine(1800, 12, 3));
			await new WorkerStore(doc).upsert({
				taskKey: TASK,
				status: "running",
				cli: "pi",
				provider: "fixture",
				taskPath,
				dispatchedAt: "",
				updatedAt: "",
				model: "",
			});
		}
		const args = {
			gate_id: path.basename(initial.gate, ".md"),
			source_card: path.basename(card, ".md"),
			restricted_action: initial.allowed_action,
			...(hasSourceWorker ? { source_worker: TASK, task_key: "reserved-successor" } : {}),
			...(choice === "in-progress" ? { task_key: TASK } : {}),
			material: initial.material,
			preparation: initial.preparation,
		};
		if (choice === "not-prepared" || choice === "in-progress" || choice === "failed") {
			if (choice === "not-prepared") initial.preparation.basis_catalog[0].material_refs = ["nonexistent"];
			const result = await invoke(args);
			expect(result?.details).toMatchObject({
				state: choice === "not-prepared" ? "blocked" : choice === "in-progress" ? "in-progress" : "failed",
				parent_released: false,
			});
			expect(envelopeInputs).toHaveLength(choice === "failed" ? 1 : 0);
			expect(fs.readFileSync(initial.gate, "utf8")).toBe(unchanged);
			return;
		}
		if (choice === "narrow") {
			for (const label of ["Prepared PM plan", initial.parent_basis]) {
				expect(unchanged).toContain(label);
				fs.writeFileSync(initial.gate, unchanged.replaceAll(label, "Uncorrelated gate text"));
				const refused = await invoke(args);
				expect(refused?.role === "toolResult" && refused.details).toMatchObject({
					state: "blocked",
					request_started: false,
				});
				expect(envelopeInputs).toHaveLength(0);
			}
			fs.writeFileSync(initial.gate, unchanged);
		}
		if (target === "dp-auto") {
			const alias = "gate-9876";
			fs.writeFileSync(
				path.join(path.dirname(initial.gate), `${alias}.md`),
				unchanged.replaceAll(args.gate_id, alias),
			);
			expect((await invoke({ ...args, gate_id: alias }))?.details).toMatchObject({
				state: "blocked",
				request_started: false,
			});
			expect(envelopeInputs).toHaveLength(0);
		}
		const result = await invoke(args);
		expect(result?.role === "toolResult" && result.details, JSON.stringify(result?.content)).toMatchObject({
			state: "answered",
			target,
			request_started: true,
			parent_released: false,
			selected_basis: basis,
			pm_note: "Prepared PM plan",
		});
		expect(envelopeInputs).toHaveLength(1);
		const request = JSON.parse(envelopeInputs[0]);
		expect(request.parent_decision_ref).toBe(initial.gate_ref);
		expect(request.material).not.toHaveProperty("parent_decision_ref");
		if (target === "dp-pm-steer") {
			const source = extractCardSections(fs.readFileSync(card, "utf8"));
			expect(request.material).toMatchObject({
				task_goal: source.context,
				task_requirements: source.requirements,
				task_deliverables: source.deliverables,
			});
			if (hasSourceWorker) {
				expect(JSON.parse(request.material.worker_execution)).toMatchObject({
					task_key: TASK,
					status: "running",
					checkpoint: { reads: 12, writes: 3 },
					writeFace: expect.stringContaining("ui-bridge.ts"),
				});
				expect(request.meta).toMatchObject({
					task_key: "reserved-successor",
					task_before: { status: "not-queued", source: "worker-registry" },
				});
			} else expect(request.material).not.toHaveProperty("worker_execution");
		}
		expect(fs.readFileSync(initial.gate, "utf8")).toBe(unchanged);
		expect(new WorkerStore(doc).readAll()).toHaveLength(hasSourceWorker ? 1 : 0);
		const replay = await invoke(args);
		expect(replay?.role === "toolResult" && replay.details).toMatchObject({
			state: "answered",
			duplicate: true,
			selected_basis: basis,
			request_started: false,
		});
		expect(envelopeInputs).toHaveLength(1);
		if (choice === "split") {
			const requestRef = `${target}:${request.meta.logical_id}`;
			const actualAction = async (eventId: string) => {
				h.setResponses([
					fauxAssistantMessage(
						fauxToolCall("pm_gate_followup", { ...args, action_event: eventId, request_ref: requestRef }),
						{ stopReason: "toolUse" },
					),
					fauxAssistantMessage("done"),
				]);
				await h.session.prompt("Inspect the recorded split action");
				const outcome = h.session.messages.filter((m) => m.role === "toolResult").at(-1);
				return outcome?.role === "toolResult" && outcome.details;
			};
			expect(await actualAction("split-two-cards")).toMatchObject({ state: "unknown", request_started: false });
			expect(call("split-effect", envelopeInputs[0]).trim()).toBe("split-two-cards");
			expect(await actualAction("split-two-cards")).toMatchObject({
				state: "executed",
				request_started: false,
				parent_released: false,
			});
			expect(fs.readFileSync(path.join(doc, OWNER, "tasks", "ui.md"), "utf8")).toContain("ui.ts");
			expect(fs.readFileSync(path.join(doc, OWNER, "tasks", "reader.md"), "utf8")).toContain("reader.py");
			expect(envelopeInputs).toHaveLength(1);
			expect(fs.readFileSync(initial.gate, "utf8")).toBe(unchanged);
		}
	});
});
