/**
 * mw-decision-context T03 (AC-001/003/004/010/014): the PM dp1 producer sends
 * the task's ORIGINAL goal/requirements/deliverables inside the local envelope
 * `{material, meta}`, and the machine no longer calls dp2 on its own.
 *
 * Locked behaviour under test:
 *  1. dp1 material = the card's 上下文 / 要求 / 交付格式 bodies verbatim (no
 *     summary, no excerpt cap, no byte truncation); the only model keys are the
 *     registry's `modelStateFields` for dp1.
 *  2. The local envelope carries `record_version:2`, a per-decision UUID
 *     `logical_id`, the owning `key`, the REAL reserved `task_key` (null when
 *     the PM decision has no task), `initiator_role:"pm"`, `retry_of:null`.
 *     Identity/audit fields never enter the model material.
 *  3. dp1 asks exactly ONE question (triage_type) with the three user-defined
 *     labels; no risk / reason question rides along.
 *  4. A role outside coding/research/review (vision / rag-research / codex)
 *     performs ZERO decision calls and never rewrites its type.
 *  5. Missing material or an over-budget material is refused with ZERO spawn —
 *     never silently truncated.
 *  6. dp1's real consumer (the dispatch) can produce its lifecycle feedback
 *     facts for the future `mw decide lifecycle` writer; nothing is appended
 *     by the extension itself and `consumed` is never treated as completed.
 *  7. The checkpoint watchdog still wakes the PM for a mid/high risk
 *     checkpoint, but the PM loop no longer asks dp2 nor writes a narrow steer.
 *
 * Fixtures are files + injected faux runners + the suite harness (faux
 * provider). No real provider, key, token, service or subprocess is used.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	DP2_CHECKPOINT_ID,
	DP2_STEER_FILE,
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
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
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

function dp1Plan(overrides: Partial<Dp1DispatchPlan> = {}): Dp1DispatchPlan {
	return {
		key: "mw-decision-context",
		taskType: "coding",
		taskKey: "dc-t03-pm-producers",
		sections: fixtureSections(),
		...overrides,
	};
}

/** A project whose `.mw/decide.json` enables the decision service. */
function decideProject(): string {
	const dir = mkProject();
	fs.mkdirSync(path.join(dir, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(dir, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
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
			decision_id: `${DP1_ID}:mw-decision-context`,
			answers: { triage_type: { value: answer ?? "coding", confidence: 0.9 } },
		};
		const raw: RawDecideRun = { status: 0, stdout: JSON.stringify(payload), stderr: "", timedOut: false };
		return raw;
	};
	return { run, calls };
}

function envelopeOf(request: DecideRunRequest): { material: Record<string, unknown>; meta: Record<string, unknown> } {
	return JSON.parse(request.input) as { material: Record<string, unknown>; meta: Record<string, unknown> };
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
	it("builds material from the card's three bodies verbatim, never a summary", () => {
		const built = buildDp1DecisionMaterial(dp1Plan());
		expect(built.ok).toBe(true);
		if (!built.ok) return;
		expect(Object.keys(built.material).sort()).toEqual([...(DECIDE_REGISTRY[DP1_ID]?.modelStateFields ?? [])].sort());
		expect(built.material.task_goal).toBe(GOAL);
		expect(built.material.task_requirements).toBe(REQUIREMENTS);
		expect(built.material.task_deliverables).toBe(DELIVERABLES);
		// No excerpt cap: the requirements body is reproduced byte for byte.
		expect(Buffer.byteLength(built.material.task_requirements, "utf8")).toBe(Buffer.byteLength(REQUIREMENTS, "utf8"));
		expect(built.material.task_requirements.length).toBeGreaterThan(1200);
		console.log(
			`[VERIFY] VC-001: producers=1/1 material_bytes=${built.bytes} fields=${Object.keys(built.material).length}`,
		);
	});

	it("sends {material, meta} on the existing stdin wrapper with identity only in meta", () => {
		const runner = capturingRunner();
		const triage = triageWith(runner.run);
		expect(triage).not.toBeNull();
		expect(runner.calls).toHaveLength(1);
		const request = runner.calls[0];
		if (!request) throw new Error("no decision request captured");
		expect(request.dp).toBe(DP1_ID);
		const envelope = envelopeOf(request);
		expect(Object.keys(envelope).sort()).toEqual(["material", "meta"]);
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

	it("asks exactly one triage_type question with the three user-defined labels (VC-003)", () => {
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
		expect(question.choices).toEqual(["coding", "research", "review"]);
		expect(Object.keys(question.labels ?? {}).sort()).toEqual(["coding", "research", "review"]);
		expect(Object.values(question.labels ?? {})).toHaveLength(3);
		expect(dp1.model_state_fields).toEqual(["task_goal", "task_requirements", "task_deliverables"]);
		const runner = capturingRunner();
		triageWith(runner.run);
		const wire = runner.calls[0]?.input ?? "";
		expect(wire).not.toContain("triage_risk");
		expect(wire).not.toContain('"reason"');
		console.log(`[VERIFY] VC-003: questions=1 choices=${question.choices?.join("/")} labels=3`);
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
	it("keeps vision/rag-research/codex outside dp1: no decision call, type unchanged", () => {
		for (const taskType of ["vision", "rag-research", "codex"]) {
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
		console.log("[VERIFY] VC-001: unsupported_role_calls=0 types=vision/rag-research/codex");
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
			projectDir: mkProject(),
			dpId: DP1_ID,
			material: sentMaterial as TriageState,
			meta: newDecisionMeta({ key: "mw-decision-context", taskKey: "t" }),
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
		const meta = newDecisionMeta({ key: "mw-decision-context", taskKey: "t" });
		const result = triageDispatchEnvelope({
			projectDir: mkProject(),
			dpId: DP1_ID,
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
		expect(decisionId).toBe(`${DP1_ID}:mw-decision-context`);

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
		const escalated = triageWith(() => ({
			status: 0,
			stdout: JSON.stringify({
				available: false,
				reason: "input-oversize",
				decision_id: `${DP1_ID}:mw-decision-context`,
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
				decision_id: `${DP1_ID}:${OWNER}`,
				answers: { triage_type: { value: "coding", confidence: 0.9 } },
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
		expect(Object.keys(envelope).sort()).toEqual(["material", "meta"]);
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
