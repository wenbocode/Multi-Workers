/** Regression coverage for decision material, real window binding, one-call signing
 * and explicit lifecycle receipts. Fixtures use isolated homes and the faux provider. */
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { activate } from "../../src/extensions/agent-team-loop/index.ts";
import {
	ASK_DECISION_MATERIAL_DP_IDS,
	ASK_DECISION_PM_ONLY_DP_IDS,
	ASK_DECISION_REASON_ROLE_FORBIDDEN,
	ASK_DECISION_REASON_UNKNOWN_ACTION,
	ASK_DECISION_REASON_UNKNOWN_DECISION,
	ASK_DECISION_TOOL,
	type AskDecisionPayload,
	buildDecideArgv,
	buildDecisionEnvelope,
	buildDecisionToolMeta,
	buildLifecycleArgv,
	DECISION_RECEIPT_TOOL,
	type DecideRunner,
	type DecideRunRequest,
	type DecisionToolMeta,
	DP3_HANDLING_LABEL_MAX,
	initiatorRoleFromWorkerTask,
	type LifecycleRequest,
	type LifecycleRunner,
	type RawDecideResult,
	registerAskDecisionTool,
	resolveHandlingSelection,
	runAskDecision,
	type SignRequest,
	type SignRunner,
	validateDecisionMaterial,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import type {
	DecideRunner as WorkerDecideRunner,
	DecideRunRequest as WorkerDecideRunRequest,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import {
	type Dp3DecisionInput,
	decideDp3WorkerClarify,
	readDp3Policy,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

const tempDirs: string[] = [];
const harnesses: Harness[] = [];
const savedEnv = new Map<string, string | undefined>();

function mkTemp(prefix = "mwdctx-t04-"): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

function saveEnv(name: string): void {
	savedEnv.set(name, process.env[name]);
}

function restoreEnv(): void {
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
}

beforeEach(() => {
	for (const name of ["HOME", "USERPROFILE", "PI_CODING_AGENT_DIR", "PI_WORKER_TASK", "MW_PY", "MW_STUB_SEEN"]) {
		saveEnv(name);
	}
	// Synthetic, isolated agent home: nothing here can read or write real
	// credentials or the developer's own agent config.
	const home = mkTemp("mwdctx-home-");
	process.env.HOME = home;
	process.env.USERPROFILE = home;
	process.env.PI_CODING_AGENT_DIR = path.join(home, ".pi", "agent");
	delete process.env.PI_WORKER_TASK;
	delete process.env.MW_PY;
});

afterEach(() => {
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	for (const dir of tempDirs.splice(0)) {
		try {
			fs.rmSync(dir, { recursive: true, force: true });
		} catch {
			// Best effort.
		}
	}
	restoreEnv();
});

// ── fixtures ────────────────────────────────────────────────────────────────

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const KEY = "mw-decision-context";
const TASK = "dc-t04-agent-materials";

/** A worker window: `.agenticdoc/<key>/workers/<task>/task.md`. */
function workerProject(): { root: string; taskPath: string; keyDir: string } {
	const root = mkTemp();
	const keyDir = path.join(root, ".agenticdoc", KEY);
	const taskDir = path.join(keyDir, "workers", TASK);
	fs.mkdirSync(taskDir, { recursive: true });
	const taskPath = path.join(taskDir, "task.md");
	fs.writeFileSync(taskPath, "type: coding\ntimeout: 60\n\n## 上下文\n\nfixture\n", "utf8");
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	return { root, taskPath, keyDir };
}

function pmProject(): { root: string; keyDir: string } {
	const root = mkTemp();
	const keyDir = path.join(root, ".agenticdoc", KEY);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	return { root, keyDir };
}

/** Multi-byte, long question text (~1.2 KB): a truncation cap would show. */
const QUESTION = [
	"决策点：dp3 的材料必须原样到达模型，不得被截断。",
	Array.from({ length: 20 }, (_, i) => `行${i + 1}：问号😀与中文混排，不做摘要。`).join(""),
].join("\n");

function autoMaterial(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		question: QUESTION,
		background: {
			task_goal: "让两个提问角色共用同一材料入口。",
			current_state: "T01/T02 已交付；当前 state 只有 question/background/handling_options。",
			tried: "旧 fact/intent/reuse 多问已被替代，必须由提问 Agent 给材料。",
			unknowns: "Verifying user intent.",
			constraints: "不得自动检索旧答案；c1 为继续、c2 为交 PM、c3 为问用户。",
		},
		handling_options: [
			{
				id: "c1",
				label: "按现有假设继续",
				description: "在当前写面内继续，不扩大授权。",
				consequence: "retains the scope",
				risk: "documented",
				conditions: "within the present budget",
			},
			{
				id: "c2",
				label: "交 PM 判定边界",
				description: "把材料交给 PM，由 PM 判定是否需要用户确认。",
				consequence: "retains the scope",
				risk: "documented",
				conditions: "within the present budget",
			},
			{
				id: "c3",
				label: "向用户提问",
				description: "当前事实不足以判断，向用户提出具体问题。",
				consequence: "retains the scope",
				risk: "documented",
				conditions: "within the present budget",
			},
		],
		...overrides,
	};
}

function steerMaterial(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		task_goal: "T04 交付双角色材料工具。",
		task_requirements: "RED->GREEN；保留外部 diff；不越写面。",
		task_deliverables: "report.md + 证据 + 测试。",
		pm_decision_background: "当前进度需要判断继续/拆小/直执/上抛人；budget 剩 12 分钟。",
		...overrides,
	};
}

function signMaterial(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		delivery_goal: "四 DP 材料契约落地并通过验收命令。",
		actual_completion: "dp2/dp3/dp25 材料与权限已实现，测试 GREEN。",
		verification_evidence: { verified: ["vitest RED/GREEN 原日志"], unverified: [] },
		unfinished_impact: [],
		...overrides,
	};
}

function preparation(dp: string) {
	const choices: Record<string, string[]> = {
		"dp-auto": ["c1", "c2", "c3"],
		"dp-sign-key": ["finalize", "continue", "user-confirm"],
		"dp-pm-steer": ["narrow", "split", "direct-exec", "escalate"],
	};
	const refs: Record<string, string> = {
		"dp-auto": "question",
		"dp-sign-key": "delivery_goal",
		"dp-pm-steer": "task_goal",
	};
	return {
		prepared_at: "2026-10-25T10:00:00Z",
		basis_catalog: [
			{ id: "reason", text: "Review the referenced evidence", material_refs: [refs[dp]], applies_to: choices[dp] },
		],
	};
}
interface CapturedRunner {
	run: DecideRunner;
	calls: DecideRunRequest[];
}
function decideRunner(answer = '{"handling":{"value":"c2","confidence":0.9}}'): CapturedRunner {
	const calls: DecideRunRequest[] = [];
	const run: DecideRunner = async (request) => {
		calls.push(request);
		const raw: RawDecideResult = {
			status: 0,
			stdout: JSON.stringify({
				available: true,
				mode: "auto",
				acted: false,
				confidence_source: "api",
				latency_ms: 12,
				decision_id: `${request.dp}:${envelopeOf(request).meta.logical_id}`,
				answers: { ...(JSON.parse(answer) as Record<string, unknown>), basis_id: { value: "reason" } },
			}),
			stderr: "",
			timedOut: false,
		};
		return raw;
	};
	return { run, calls };
}

interface CapturedLifecycle {
	run: LifecycleRunner;
	calls: LifecycleRequest[];
}

function lifecycleRunner(status: "written" | "failed" = "written"): CapturedLifecycle {
	const calls: LifecycleRequest[] = [];
	const run: LifecycleRunner = async (request) => {
		calls.push(request);
		const raw: RawDecideResult = {
			// The real writer's `--json` receipt: `recorded` is the only success
			// signal a consumer may trust.
			status: status === "written" ? 0 : 1,
			stdout:
				status === "written"
					? JSON.stringify({ stage: "consumed", status: "written", recorded: true, duplicate: false })
					: JSON.stringify({ stage: "consumed", status: "failed", recorded: false, error_class: "io" }),
			stderr: "",
			timedOut: false,
		};
		return raw;
	};
	return { run, calls };
}

interface CapturedSign {
	run: SignRunner;
	calls: SignRequest[];
}

/** The real `decide sign --stdin --json` receipt: ONE judgment, then either a
 * written sign-off file or a concrete handoff (no second approval). */
function signRunner(conclusion: "finalize" | "continue" | "user-confirm" = "finalize"): CapturedSign {
	const calls: SignRequest[] = [];
	const run: SignRunner = async (request) => {
		calls.push(request);
		const finalize = conclusion === "finalize";
		const meta = (JSON.parse(request.input) as { meta: { logical_id: string } }).meta;
		const raw: RawDecideResult = {
			status: 0,
			stdout: JSON.stringify({
				dp: "dp-sign-key",
				key: request.key,
				logical_id: meta.logical_id,
				decision_id: `dp-sign-key:${meta.logical_id}`,
				conclusion,
				basis_id: "reason",
				signoff_status: finalize ? "written" : "not-required",
				signoff_path: finalize ? "/fixture/sign-final.md" : null,
				record_status: "written",
				model_called: true,
				second_approval: 0,
				problems: [],
				feedback_status: "recorded",
				feedback_stages: [{ stage: "consumed", status: "written", event_id: "consumed-fixture" }],
				...(finalize
					? {}
					: { handoff: { owner: "pm", kind: conclusion, signoff_writes: 0, instruction: "advance" } }),
			}),
			stderr: "",
			timedOut: false,
		};
		return raw;
	};
	return { run, calls };
}

function envelopeOf(request: DecideRunRequest): { material: Record<string, unknown>; meta: DecisionToolMeta } {
	return JSON.parse(request.input) as { material: Record<string, unknown>; meta: DecisionToolMeta };
}

function firstLine(text: string): string {
	return text.split("\n")[0] ?? "";
}

function payloadOf(text: string): AskDecisionPayload {
	return JSON.parse(firstLine(text)) as AskDecisionPayload;
}

// ── 1. dp-auto material contract (AC-005) ───────────────────────────────────────

describe("dp-auto material contract (AC-005)", () => {
	it("keeps the question 原文, the four background facts and every description verbatim", () => {
		const built = validateDecisionMaterial("dp-auto", autoMaterial());
		expect(built.ok).toBe(true);
		if (!built.ok) throw new Error("unreachable");
		expect(built.material.question).toBe(QUESTION);
		// A byte cap or a 80-char label squeeze must never shorten the payload.
		expect(Buffer.byteLength(built.material.question as string, "utf8")).toBeGreaterThan(900);
		const options = built.material.handling_options as Array<Record<string, string>>;
		expect(options).toHaveLength(3);
		expect(options.map((option) => option.id)).toEqual(["c1", "c2", "c3"]);
		for (const option of options) {
			expect(option.description.length).toBeGreaterThan(4);
		}
		expect(options[1]?.description).toBe("把材料交给 PM，由 PM 判定是否需要用户确认。");
	});

	it("refuses candidate counts outside the transport limits, duplicate ids, long labels and blank descriptions", () => {
		const cases: Array<{ material: Record<string, unknown>; field: string }> = [
			{
				material: autoMaterial({
					handling_options: [{ id: "c1", label: "唯一项", description: "只有一个候选。" }],
				}),
				field: "handling_options",
			},
			{
				material: autoMaterial({
					handling_options: Array.from({ length: 33 }, (_, i) => ({
						id: `c${i + 1}`,
						label: `候选${i + 1}`,
						description: `说明${i + 1}`,
					})),
				}),
				field: "handling_options",
			},
			{
				material: autoMaterial({
					handling_options: [
						{
							id: "c1",
							label: "A",
							description: "说明 A。",
							consequence: "retains the scope",
							risk: "documented",
							conditions: "within the present budget",
						},
						{
							id: "c1",
							label: "B",
							description: "说明 B。",
							consequence: "retains the scope",
							risk: "documented",
							conditions: "within the present budget",
						},
					],
				}),
				field: "handling_options[1].id",
			},
			{
				material: autoMaterial({
					handling_options: [
						{
							id: "c1",
							label: "A".repeat(DP3_HANDLING_LABEL_MAX + 1),
							description: "说明 A。",
							consequence: "retains the scope",
							risk: "documented",
							conditions: "within the present budget",
						},
						{
							id: "c2",
							label: "B",
							description: "说明 B。",
							consequence: "retains the scope",
							risk: "documented",
							conditions: "within the present budget",
						},
					],
				}),
				field: "handling_options[0].label",
			},
			{
				material: autoMaterial({
					handling_options: [
						{
							id: "c1",
							label: "A",
							description: "   ",
							consequence: "retains the scope",
							risk: "documented",
							conditions: "within the present budget",
						},
						{
							id: "c2",
							label: "B",
							description: "说明 B。",
							consequence: "retains the scope",
							risk: "documented",
							conditions: "within the present budget",
						},
					],
				}),
				field: "handling_options[0].description",
			},
			{
				material: autoMaterial({
					handling_options: [
						{
							id: "c1",
							label: "重复",
							description: "说明 A。",
							consequence: "retains the scope",
							risk: "documented",
							conditions: "within the present budget",
						},
						{
							id: "c2",
							label: "重复",
							description: "说明 B。",
							consequence: "retains the scope",
							risk: "documented",
							conditions: "within the present budget",
						},
					],
				}),
				field: "handling_options[1].label",
			},
		];
		for (const { material, field } of cases) {
			const built = validateDecisionMaterial("dp-auto", material);
			expect(built.ok, field).toBe(false);
			if (built.ok) continue;
			expect(built.issues.map((issue) => issue.field)).toContain(field);
		}
	});

	it("refuses missing background facts and unknown keys by name", () => {
		const missing = autoMaterial({ background: { task_goal: "g", current_state: "s", tried: "r" } });
		const built = validateDecisionMaterial("dp-auto", missing);
		expect(built.ok).toBe(false);
		if (built.ok) throw new Error("unreachable");
		expect(built.issues.map((issue) => issue.field)).toContain("background.constraints");

		const extra = validateDecisionMaterial("dp-auto", { ...autoMaterial(), local_candidates: [] });
		expect(extra.ok).toBe(false);
		if (extra.ok) throw new Error("unreachable");
		expect(extra.issues.map((issue) => issue.field)).toContain("local_candidates");
		// The field list is the generated registry's, not a second local table.
		expect(DECIDE_REGISTRY["dp-auto"]?.modelStateFields).toEqual([
			"question",
			"background.task_goal",
			"background.current_state",
			"background.tried",
			"background.unknowns",
			"background.constraints",
			"handling_options",
		]);
	});
});

// ── 2. dp3 dual role + native single choice (AC-005 / AC-006) ───────────────

describe("PM dynamic choice entry (AC-005/AC-006)", () => {
	it("sends the task-associated PM's material envelope and returns the exact candidate to the same asker", async () => {
		const { root, taskPath } = workerProject();
		const decide = decideRunner();
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp-auto",
			preparation: preparation("dp-auto"),
			trigger: `${TASK}#nc1`,
			material: autoMaterial(),
			initiatorRole: "pm",
			key: KEY,
			taskKey: TASK,
			runner: decide.run,
			lifecycleRunner: lifecycleRunner().run,
		});

		expect(outcome.spawned).toBe(true);
		expect(decide.calls).toHaveLength(1);
		const envelope = envelopeOf(decide.calls[0] as DecideRunRequest);
		// The model sees ONLY business material (identity/association in meta).
		expect(Object.keys(envelope.material).sort()).toEqual(["background", "handling_options", "question"]);
		expect(envelope.material).toEqual(autoMaterial());
		expect(envelope.meta.record_version).toBe(2);
		expect(envelope.meta.logical_id).toMatch(UUID_V4);
		expect(envelope.meta.key).toBe(KEY);
		expect(envelope.meta.task_key).toBe(TASK);
		expect(envelope.meta.initiator_role).toBe("pm");
		expect(envelope.meta.retry_of).toBeNull();

		const payload = payloadOf(outcome.text);
		expect(payload.available).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		// Precisely the original asker's candidate: id + label + description.
		expect(payload.selection).toEqual({
			question: "handling",
			id: "c2",
			label: "交 PM 判定边界",
			description: "把材料交给 PM，由 PM 判定是否需要用户确认。",
		});
		expect(payload.answers).toEqual({ handling: { value: "c2", confidence: 0.9 }, basis_id: { value: "reason" } });
		// Receipt cost: the child's decision_id, never a locally concatenated one.
		expect(payload.decision_id).toBe(`dp-auto:${envelope.meta.logical_id}`);
		expect(taskPath).toContain(TASK);
	});

	it("supports the PM asking the user with the same entry (task_key stays null)", async () => {
		const { root } = pmProject();
		const decide = decideRunner();
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp-auto",
			preparation: preparation("dp-auto"),
			trigger: `${KEY}#ckpt2`,
			material: autoMaterial(),
			initiatorRole: "pm",
			key: KEY,
			runner: decide.run,
			lifecycleRunner: lifecycleRunner().run,
		});
		expect(outcome.spawned).toBe(true);
		const envelope = envelopeOf(decide.calls[0] as DecideRunRequest);
		expect(envelope.meta.initiator_role).toBe("pm");
		// No task given -> null, never "the latest task".
		expect(envelope.meta.task_key).toBeNull();
	});

	it("mints one fresh logical_id per real call", async () => {
		const { root } = workerProject();
		const decide = decideRunner();
		const ids: string[] = [];
		for (let i = 0; i < 2; i++) {
			await runAskDecision({
				projectDir: root,
				dp: "dp-auto",
				preparation: preparation("dp-auto"),
				trigger: `${TASK}#nc${i + 1}`,
				material: autoMaterial(),
				initiatorRole: "pm",
				key: KEY,
				taskKey: TASK,
				runner: decide.run,
				lifecycleRunner: lifecycleRunner().run,
			});
			ids.push(envelopeOf(decide.calls[i] as DecideRunRequest).meta.logical_id);
		}
		expect(ids).toHaveLength(2);
		expect(ids[0]).not.toBe(ids[1]);
		for (const id of ids) expect(id).toMatch(UUID_V4);
	});

	it("never resolves a selection the agent did not send (unknown candidate id)", () => {
		expect(resolveHandlingSelection({ handling: { value: "c9" } }, autoMaterial().handling_options)).toBeUndefined();
		expect(resolveHandlingSelection({}, autoMaterial().handling_options)).toBeUndefined();
	});
});

// ── 3. role permissions (AC-006 / AC-010) ───────────────────────────────────

describe("role permissions (AC-006/AC-010)", () => {
	it("refuses dp2 for every worker role with zero spawn", async () => {
		const { root } = workerProject();
		for (const role of ["coding", "research", "review"] as const) {
			const decide = decideRunner();
			const lifecycle = lifecycleRunner();
			const outcome = await runAskDecision({
				projectDir: root,
				dp: "dp-pm-steer",
				preparation: preparation("dp-pm-steer"),
				trigger: `${TASK}#ckpt1`,
				material: steerMaterial(),
				initiatorRole: role,
				key: KEY,
				taskKey: TASK,
				runner: decide.run,
				lifecycleRunner: lifecycle.run,
			});
			expect(outcome.spawned, role).toBe(false);
			const payload = payloadOf(outcome.text);
			expect(payload.available).toBe(false);
			if (payload.available) throw new Error("unreachable");
			expect(payload.unavailable).toBe(ASK_DECISION_REASON_ROLE_FORBIDDEN);
			expect(decide.calls).toHaveLength(0);
			expect(lifecycle.calls).toHaveLength(0);
		}
		expect(ASK_DECISION_PM_ONLY_DP_IDS).toContain("dp-pm-steer");
	});

	it("refuses dp25 material for a worker and never writes a sign-off", async () => {
		const { root } = workerProject();
		const decide = decideRunner();
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp-sign-key",
			preparation: preparation("dp-sign-key"),
			trigger: `${TASK}#sign`,
			material: signMaterial(),
			initiatorRole: "coding",
			key: KEY,
			taskKey: TASK,
			runner: decide.run,
			lifecycleRunner: lifecycleRunner().run,
		});
		expect(outcome.spawned).toBe(false);
		expect(decide.calls).toHaveLength(0);
		const payload = payloadOf(outcome.text);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.unavailable).toBe(ASK_DECISION_REASON_ROLE_FORBIDDEN);
		expect(ASK_DECISION_PM_ONLY_DP_IDS).toContain("dp-sign-key");
		// No file is written anywhere by the material tool.
		expect(fs.existsSync(path.join(root, "evidence"))).toBe(false);
	});

	it("sends the PM's dp2 material verbatim, with and without worker_execution", async () => {
		const { root } = pmProject();
		const decide = decideRunner('{"checkpoint_action":{"value":"narrow","confidence":0.7}}');
		const lifecycle = lifecycleRunner();
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp-pm-steer",
			preparation: preparation("dp-pm-steer"),
			trigger: `${KEY}#ckpt1`,
			material: steerMaterial(),
			initiatorRole: "pm",
			key: KEY,
			runner: decide.run,
			lifecycleRunner: lifecycle.run,
		});
		expect(outcome.spawned).toBe(true);
		const envelope = envelopeOf(decide.calls[0] as DecideRunRequest);
		expect(envelope.material).toEqual(steerMaterial());
		// Not dispatched is legal: no invented worker_execution field.
		expect("worker_execution" in envelope.material).toBe(false);
		const payload = payloadOf(outcome.text);
		expect(payload.available).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		// The local label table is NOT duplicated on the TS side.
		expect(payload.selection).toEqual({ question: "checkpoint_action", id: "narrow" });

		const withWorker = decideRunner('{"checkpoint_action":{"value":"split","confidence":0.7}}');
		await runAskDecision({
			projectDir: root,
			dp: "dp-pm-steer",
			preparation: preparation("dp-pm-steer"),
			trigger: `${KEY}#ckpt2`,
			material: steerMaterial({ worker_execution: "done: 12 files; remaining: review; blocked: none; budget 12m" }),
			initiatorRole: "pm",
			key: KEY,
			runner: withWorker.run,
			lifecycleRunner: lifecycle.run,
		});
		expect(envelopeOf(withWorker.calls[0] as DecideRunRequest).material.worker_execution).toContain("remaining");
	});

	it("refuses a PM dp2 with a blank decision background, zero spawn", async () => {
		const { root } = pmProject();
		const decide = decideRunner();
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp-pm-steer",
			preparation: preparation("dp-pm-steer"),
			trigger: `${KEY}#ckpt1`,
			material: steerMaterial({ pm_decision_background: "   " }),
			initiatorRole: "pm",
			key: KEY,
			runner: decide.run,
			lifecycleRunner: lifecycleRunner().run,
		});
		expect(outcome.spawned).toBe(false);
		expect(decide.calls).toHaveLength(0);
		const payload = payloadOf(outcome.text);
		expect(payload.available).toBe(false);
		if (payload.available) throw new Error("unreachable");
		expect(payload.unavailable).toBe("input-incomplete");
		expect(payload.missing_fields).toContain("pm_decision_background");
	});

	it("sends the PM's dp25 four sections, `[]` being a real 'none', and signs in one judgment", async () => {
		const { root } = pmProject();
		const sign = signRunner("finalize");
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp-sign-key",
			preparation: preparation("dp-sign-key"),
			trigger: `${KEY}#sign`,
			material: signMaterial(),
			initiatorRole: "pm",
			key: KEY,
			signRunner: sign.run,
		});
		expect(outcome.spawned).toBe(true);
		// ONE judgment: the sign CLI is the only child, never `run` + a second sign.
		expect(sign.calls).toHaveLength(1);
		const call = sign.calls[0] as SignRequest;
		expect(call.key).toBe(KEY);
		const envelope = JSON.parse(call.input) as { material: Record<string, unknown>; meta: DecisionToolMeta };
		expect(Object.keys(envelope.material).sort()).toEqual([
			"actual_completion",
			"delivery_goal",
			"unfinished_impact",
			"verification_evidence",
		]);
		expect(envelope.material.verification_evidence).toEqual({
			verified: ["vitest RED/GREEN 原日志"],
			unverified: [],
		});
		expect(envelope.material.unfinished_impact).toEqual([]);
		expect(envelope.meta.initiator_role).toBe("pm");
		const payload = payloadOf(outcome.text);
		expect(payload.available).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		expect(payload.selection).toEqual({ question: "q-conclusion", id: "finalize" });
		expect(payload.signoff).toMatchObject({ status: "written", second_approval: 0 });
		expect(payload.mode).toBeUndefined();
	});

	it("continue/user-confirm write no sign-off and hand the next step back", async () => {
		for (const conclusion of ["continue", "user-confirm"] as const) {
			const { root } = pmProject();
			const sign = signRunner(conclusion);
			const outcome = await runAskDecision({
				projectDir: root,
				dp: "dp-sign-key",
				preparation: preparation("dp-sign-key"),
				trigger: `${KEY}#sign-${conclusion}`,
				material: signMaterial(),
				initiatorRole: "pm",
				key: KEY,
				signRunner: sign.run,
			});
			expect(sign.calls, conclusion).toHaveLength(1);
			const payload = payloadOf(outcome.text);
			expect(payload.available, conclusion).toBe(true);
			if (!payload.available) continue;
			expect(payload.selection?.id, conclusion).toBe(conclusion);
			expect(payload.signoff, conclusion).toMatchObject({
				status: "not-required",
				handoff: { owner: "pm", kind: conclusion, signoff_writes: 0 },
			});
		}
	});

	it("refuses a dp25 with an empty goal / a missing evidence pair", async () => {
		const cases = [
			{ material: signMaterial({ delivery_goal: "" }), field: "delivery_goal" },
			{
				material: signMaterial({ verification_evidence: { verified: [] } }),
				field: "verification_evidence.unverified",
			},
			{ material: signMaterial({ unfinished_impact: "none" }), field: "unfinished_impact" },
		];
		for (const { material, field } of cases) {
			const built = validateDecisionMaterial("dp-sign-key", material);
			expect(built.ok, field).toBe(false);
			if (built.ok) continue;
			expect(built.issues.map((issue) => issue.field)).toContain(field);
		}
	});
});

// ── 4. lifecycle feedback (AC-014) ──────────────────────────────────────────

describe("lifecycle feedback (AC-014)", () => {
	it("writes consumed for the received selection and nothing else", async () => {
		const { root } = workerProject();
		const decide = decideRunner();
		const lifecycle = lifecycleRunner();
		await runAskDecision({
			projectDir: root,
			dp: "dp-auto",
			preparation: preparation("dp-auto"),
			trigger: `${TASK}#nc1`,
			material: autoMaterial(),
			initiatorRole: "pm",
			key: KEY,
			taskKey: TASK,
			runner: decide.run,
			lifecycleRunner: lifecycle.run,
		});
		expect(lifecycle.calls).toHaveLength(1);
		const envelope = JSON.parse((lifecycle.calls[0] as LifecycleRequest).input) as Record<string, unknown>;
		expect(envelope.stage).toBe("consumed");
		expect(envelope.dp).toBe("dp-auto");
		expect(envelope.decision_id).toBe(`dp-auto:${envelopeOf(decide.calls[0] as DecideRunRequest).meta.logical_id}`);
		expect(typeof envelope.event_id).toBe("string");
		expect(envelope.answer).toBe("c2");
		expect(envelope.action).toBeUndefined();
		expect(envelope.outcome).toBeUndefined();
		const meta = envelope.meta as Record<string, unknown>;
		expect(meta.record_version).toBe(2);
		expect(meta.initiator_role).toBe("pm");
		const runMeta = envelopeOf(decide.calls[0] as DecideRunRequest).meta;
		// Same decision, same logical_id, same key (the join key T06 uses).
		expect(meta.logical_id).toBe(runMeta.logical_id);
		expect(meta.key).toBe(runMeta.key);
		expect(meta.task_key).toBe(TASK);
	});

	it("records nothing when the ask was refused or unavailable", async () => {
		const { root } = workerProject();
		const lifecycle = lifecycleRunner();
		// role refusal
		await runAskDecision({
			projectDir: root,
			dp: "dp-pm-steer",
			preparation: preparation("dp-pm-steer"),
			trigger: `${TASK}#ckpt1`,
			material: steerMaterial(),
			initiatorRole: "coding",
			key: KEY,
			runner: decideRunner().run,
			lifecycleRunner: lifecycle.run,
		});
		// service unavailable
		const down: DecideRunner = async () => ({
			status: 0,
			stdout: JSON.stringify({ available: false, reason: "disabled", answers: null }),
			stderr: "",
			timedOut: false,
		});
		await runAskDecision({
			projectDir: root,
			dp: "dp-auto",
			preparation: preparation("dp-auto"),
			trigger: `${TASK}#nc2`,
			material: autoMaterial(),
			initiatorRole: "pm",
			key: KEY,
			runner: down,
			lifecycleRunner: lifecycle.run,
		});
		expect(lifecycle.calls).toHaveLength(0);
	});

	it("reports a failed consumed write honestly instead of claiming success", async () => {
		const { root } = workerProject();
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp-auto",
			preparation: preparation("dp-auto"),
			trigger: `${TASK}#nc1`,
			material: autoMaterial(),
			initiatorRole: "pm",
			key: KEY,
			runner: decideRunner().run,
			lifecycleRunner: lifecycleRunner("failed").run,
		});
		const payload = payloadOf(outcome.text);
		expect(payload.available).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		expect(payload.feedback).toMatchObject({ stage: "consumed", status: "failed" });
	});

	it("records executed/settled only through the explicit receipt op", async () => {
		const { root } = workerProject();
		const decide = decideRunner();
		const lifecycle = lifecycleRunner();
		const { capture, pi } = capturingApi();
		registerAskDecisionTool(pi, {
			projectDir: root,
			initiatorRole: "pm",
			key: KEY,
			taskKey: TASK,
			runner: decide.run,
			lifecycleRunner: lifecycle.run,
		});
		const ask = capture.tools.get(ASK_DECISION_TOOL);
		const receipt = capture.tools.get(DECISION_RECEIPT_TOOL);
		expect(ask, "ask_decision registered").toBeDefined();
		expect(receipt, "decision_receipt registered").toBeDefined();

		const asked = await ask?.execute("call-1", {
			dp: "dp-auto",
			preparation: preparation("dp-auto"),
			trigger: `${TASK}#nc1`,
			material: autoMaterial(),
		});
		const askedPayload = JSON.parse(firstLine(asked?.content[0]?.text ?? "")) as AskDecisionPayload;
		expect(askedPayload.available).toBe(true);
		// Nothing was recorded as executed/settled by the model returning.
		expect(lifecycle.calls.map((call) => (JSON.parse(call.input) as { stage: string }).stage)).toEqual(["consumed"]);

		const done = await receipt?.execute("call-2", {
			decision_id: `dp-auto:${envelopeOf(decide.calls[0] as DecideRunRequest).meta.logical_id}`,
			stage: "executed",
			action: "clarify",
			result: "asked the PM with the chosen handling option",
		});
		expect(done?.content[0]?.text).toContain("executed");
		const settled = await receipt?.execute("call-3", {
			decision_id: `dp-auto:${envelopeOf(decide.calls[0] as DecideRunRequest).meta.logical_id}`,
			stage: "settled",
			outcome: "ok",
		});
		expect(settled?.content[0]?.text).toContain("settled");
		const stages = lifecycle.calls.map((call) => JSON.parse(call.input) as Record<string, unknown>);
		expect(stages.map((row) => row.stage)).toEqual(["consumed", "executed", "settled"]);
		expect(stages[1]?.action).toBe("clarify");
		expect(stages[2]?.outcome).toBe("ok");
		// Same decision id + logical_id across all three facts.
		const logical = (stages[0]?.meta as Record<string, unknown>).logical_id;
		for (const row of stages) expect((row.meta as Record<string, unknown>).logical_id).toBe(logical);
	});

	it("refuses an unknown action or an unknown decision id without recording", async () => {
		const { root } = workerProject();
		const lifecycle = lifecycleRunner();
		const decide = decideRunner();
		const { capture, pi } = capturingApi();
		registerAskDecisionTool(pi, {
			projectDir: root,
			initiatorRole: "pm",
			key: KEY,
			runner: decide.run,
			lifecycleRunner: lifecycle.run,
		});
		const ask = capture.tools.get(ASK_DECISION_TOOL);
		const receipt = capture.tools.get(DECISION_RECEIPT_TOOL);
		await ask?.execute("call-1", {
			dp: "dp-auto",
			trigger: `${TASK}#nc1`,
			material: autoMaterial(),
			preparation: preparation("dp-auto"),
		});
		expect(lifecycle.calls).toHaveLength(1);

		const badAction = await receipt?.execute("call-2", {
			decision_id: `dp-auto:${envelopeOf(decide.calls[0] as DecideRunRequest).meta.logical_id}`,
			stage: "executed",
			action: "kill-worker",
			result: "unknown action",
		});
		expect(badAction?.content[0]?.text).toContain(ASK_DECISION_REASON_UNKNOWN_ACTION);
		const unknown = await receipt?.execute("call-3", {
			decision_id: "dp-auto:not-mine",
			stage: "settled",
			outcome: "ok",
		});
		expect(unknown?.content[0]?.text).toContain(ASK_DECISION_REASON_UNKNOWN_DECISION);
		// Neither refusal wrote a fact.
		expect(lifecycle.calls).toHaveLength(1);
	});
});

// ── 5. the worker producer (worker-mode) ────────────────────────────────────

describe("worker dp3 producer (worker-mode, AC-005/AC-006)", () => {
	function dp3Input(projectRoot: string, runner: WorkerDecideRunner): Dp3DecisionInput {
		return {
			projectDir: projectRoot,
			taskKey: TASK,
			ncIndex: 1,
			key: KEY,
			phase: "EXECUTE",
			taskType: "coding",
			risk: "mid",
			riskSource: "pm-label",
			question: QUESTION,
			harnessDetail: "no product",
			taskDir: path.join(projectRoot, ".agenticdoc", KEY, "workers", TASK),
			taskPath: path.join(projectRoot, ".agenticdoc", KEY, "workers", TASK, "task.md"),
			taskContent: "type: coding\n",
			trueRoot: path.join(projectRoot, ".agenticdoc"),
			keyDir: path.join(projectRoot, ".agenticdoc", KEY),
			policy: readDp3Policy(projectRoot),
			runner,
			material: autoMaterial(),
		};
	}

	/** worker-mode's dp3 producer uses the SYNCHRONOUS triage-client runner seam. */
	function syncRunner(): { run: WorkerDecideRunner; calls: WorkerDecideRunRequest[] } {
		const calls: WorkerDecideRunRequest[] = [];
		const run: WorkerDecideRunner = (request) => {
			calls.push(request);
			return {
				status: 0,
				stdout: JSON.stringify({
					available: true,
					mode: "auto",
					acted: false,
					confidence_source: "api",
					decision_id: "dp-auto:worker",
					answers: { handling: { value: "c2", confidence: 0.8 } },
				}),
				stderr: "",
				timedOut: false,
			};
		};
		return { run, calls };
	}

	it("the retired numeric worker hook never manufactures an active request", () => {
		const { root } = workerProject();
		const decide = syncRunner();
		const decision = decideDp3WorkerClarify(dp3Input(root, decide.run));
		expect(decision.kind).toBe("escalate");
		expect(decide.calls).toHaveLength(0);
	});

	it("refuses to answer without agent-prepared material (no local guesses, zero spawn)", () => {
		const { root } = workerProject();
		const decide = syncRunner();
		const input = dp3Input(root, decide.run);
		delete input.material;
		const decision = decideDp3WorkerClarify(input);
		expect(decision.kind).toBe("escalate");
		if (decision.kind !== "escalate") throw new Error("unreachable");
		expect(decision.reason).toBe("input-incomplete");
		expect(decide.calls).toHaveLength(0);
	});
});

// ── 6. the real entry (roles, prompts, registry) ────────────────────────────

interface CapturedTool {
	name: string;
	parameters: unknown;
	promptGuidelines?: string[];
	description?: string;
	execute: (
		toolCallId: string,
		params: Record<string, unknown>,
		signal?: AbortSignal,
	) => Promise<{ content: Array<{ type: "text"; text: string }>; details: unknown; terminate?: boolean }>;
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

function capturingApi(): { capture: CapturingApi; pi: ExtensionAPI } {
	const capture = new CapturingApi();
	return { capture, pi: capture as unknown as ExtensionAPI };
}

/** A stub `mw.py` that implements BOTH the `decide run --stdin` and the
 * `decide lifecycle --stdin` argument/ stdin boundary and records what it saw.
 * It is a stand-in for the T05 CLI (which is still in flight), never a real
 * provider: no network, no credentials, no model. */
function writeStubMw(dir: string): { stubPath: string; seenDir: string } {
	const seenDir = path.join(dir, "stub-seen");
	fs.mkdirSync(seenDir, { recursive: true });
	const stubPath = path.join(dir, "stub_mw.py");
	fs.writeFileSync(
		stubPath,
		[
			"import json, os, sys",
			"args = sys.argv[1:]",
			"seen = os.environ['MW_STUB_SEEN']",
			"raw = sys.stdin.read()",
			"payload = json.loads(raw) if raw.strip() else {}",
			"cmd = args[0] if args else ''",
			"if cmd == 'decide' and args[1:2] == ['lifecycle']:",
			"    open(os.path.join(seen, 'lifecycle-%d.json' % len(os.listdir(seen))), 'w', encoding='utf-8').write(raw)",
			"    print(json.dumps({'ok': True, 'stage': payload.get('stage'), 'status': 'written', 'recorded': True}))",
			"    sys.exit(0)",
			"if cmd == 'decide' and args[1:2] == ['run']:",
			"    open(os.path.join(seen, 'run.json'), 'w', encoding='utf-8').write(raw)",
			"    open(os.path.join(seen, 'argv.json'), 'w', encoding='utf-8').write(json.dumps(args))",
			"    assert '--stdin' in args, args",
			"    assert 'material' in payload and 'meta' in payload, payload",
			"    assert 'meta' not in payload['material'], payload",
			"    print(json.dumps({'available': True, 'mode': 'auto', 'acted': False,",
			"                      'confidence_source': 'api', 'latency_ms': 3,",
			"                      'decision_id': 'dp-auto:'+payload['meta']['logical_id'],",
			"                      'answers': {'handling': {'value': 'c3', 'confidence': 0.8}, 'basis_id': {'value': 'reason'}}}))",
			"    sys.exit(0)",
			"print('unknown command', args, file=sys.stderr)",
			"sys.exit(2)",
		].join("\n"),
		"utf8",
	);
	return { stubPath, seenDir };
}

function hasPython(): boolean {
	const python = process.platform === "win32" ? "python" : "python3";
	return spawnSync(python, ["-c", "import sys; sys.exit(0)"], { windowsHide: true }).status === 0;
}

describe("real entry: roles, prompts and the production stdin boundary", () => {
	it("activate() (PM branch) exposes both material tools and sends {material,meta} on stdin", async () => {
		const project = pmProject();
		const savedCwd = process.cwd();
		process.chdir(project.root);
		delete (globalThis as Record<string, unknown>).__agentTeamLoopActivated;
		try {
			const harness = await createHarness({
				extensionFactories: [(pi) => activate(pi)],
			});
			harnesses.push(harness);
			harness.setResponses([fauxAssistantMessage("ready")]);
			await harness.session.prompt("start");
			const active = harness.session.getActiveToolNames();
			expect(active).toContain(ASK_DECISION_TOOL);
			expect(active).toContain(DECISION_RECEIPT_TOOL);
		} finally {
			// Never leave the worker process in a deleted temp dir.
			process.chdir(savedCwd);
		}
	});

	it("exposes preparation and every generated material contract to the PM", () => {
		const { capture, pi } = capturingApi();
		registerAskDecisionTool(pi, { projectDir: pmProject().root, initiatorRole: "pm", key: KEY });
		const tool = capture.tools.get(ASK_DECISION_TOOL) as CapturedTool;
		const guidelines = (tool.promptGuidelines ?? []).join("\n");
		for (const [id, entry] of Object.entries(DECIDE_REGISTRY)) {
			expect(guidelines).toContain(id);
			for (const field of entry.requiredStateFields) expect(guidelines).toContain(field.name);
		}
		expect(JSON.stringify(tool.parameters)).toContain("basis_catalog");
	});

	it("index.ts wires the same entry into the worker branch with the derived role", () => {
		const source = fs.readFileSync(
			fileURLToPath(new URL("../../src/extensions/agent-team-loop/index.ts", import.meta.url)),
			"utf8",
		);
		// Two registrations: the worker branch (derived role) and the PM branch.
		const registrations = source.match(/registerAskDecisionTool\(/g) ?? [];
		expect(registrations).toHaveLength(2);
		expect(source).toContain('initiatorRole: "pm"');
		expect(source).toContain("initiatorRoleFromWorkerTask");
	});

	it("derives the real initiator role from the worker card, never a guess", () => {
		const dir = mkTemp("mwdctx-role-");
		const write = (type: string): string => {
			const file = path.join(dir, `task-${type || "blank"}.md`);
			fs.writeFileSync(file, type === "" ? "\n## 上下文\n" : `type: ${type}\n\n## 上下文\n`, "utf8");
			return file;
		};
		expect(initiatorRoleFromWorkerTask(write("coding"))).toBe("coding");
		expect(initiatorRoleFromWorkerTask(write("research"))).toBe("research");
		expect(initiatorRoleFromWorkerTask(write("review"))).toBe("review");
		expect(initiatorRoleFromWorkerTask(write("vision"))).toBe("coding");
		expect(initiatorRoleFromWorkerTask(write("unregistered"))).toBe("unknown");
		expect(initiatorRoleFromWorkerTask(write(""))).toBe("unknown");
		expect(initiatorRoleFromWorkerTask(undefined)).toBe("unknown");
		expect(initiatorRoleFromWorkerTask(path.join(dir, "missing.md"))).toBe("unknown");
	});

	if (hasPython()) {
		it("pipes the real envelope on the production --stdin boundary (stub mw.py)", async () => {
			const project = workerProject();
			const stub = writeStubMw(project.root);
			process.env.MW_PY = stub.stubPath;
			process.env.MW_STUB_SEEN = stub.seenDir;
			// Drop the injected runners: the production transport is under test.
			const lifecycle: LifecycleRequest[] = [];
			const outcome = await runAskDecision({
				projectDir: project.root,
				dp: "dp-auto",
				preparation: preparation("dp-auto"),
				trigger: `${TASK}#nc1`,
				material: autoMaterial(),
				initiatorRole: "pm",
				key: KEY,
				taskKey: TASK,
			});
			const payload = payloadOf(outcome.text);
			expect(payload.available, outcome.text).toBe(true);
			if (!payload.available) throw new Error("unreachable");
			expect(payload.selection?.id).toBe("c3");
			expect(payload.feedback?.stage).toBe("consumed");
			const argv = JSON.parse(fs.readFileSync(path.join(stub.seenDir, "argv.json"), "utf8")) as string[];
			expect(argv.slice(0, 4)).toEqual(["decide", "run", `--project=${project.root}`, "--dp"]);
			expect(argv).toContain("--stdin");
			expect(argv).toContain("--json");
			const seen = JSON.parse(fs.readFileSync(path.join(stub.seenDir, "run.json"), "utf8")) as {
				material: Record<string, unknown>;
				meta: DecisionToolMeta;
			};
			expect(seen.material.question).toBe(QUESTION);
			expect(seen.meta.initiator_role).toBe("pm");
			expect(seen.meta.task_key).toBe(TASK);
			expect(seen.meta.logical_id).toMatch(UUID_V4);
			expect(lifecycle).toHaveLength(0);
		});
	}

	it("builds the --stdin argv and the lifecycle argv without leaking the payload onto argv", () => {
		expect(
			buildDecideArgv("/repo/mw.py", {
				projectDir: "/work",
				dp: "dp-auto",
				input: '{"material":{}}',
				timeoutMs: 20_000,
				viaStdin: true,
			}),
		).toEqual([
			"-X",
			"utf8",
			"/repo/mw.py",
			"decide",
			"run",
			"--project=/work",
			"--dp",
			"dp-auto",
			"--stdin",
			"--json",
		]);
		expect(buildLifecycleArgv("/repo/mw.py", "/work")).toEqual([
			"-X",
			"utf8",
			"/repo/mw.py",
			"decide",
			"lifecycle",
			"--project=/work",
			"--stdin",
			// `--json` makes the writer report `recorded`/`status`: the consumer
			// never infers a successful write from exit code 0.
			"--json",
		]);
	});

	it("keeps the four material dp ids aligned with the generated registry", () => {
		expect(ASK_DECISION_MATERIAL_DP_IDS).toEqual(Object.keys(DECIDE_REGISTRY));
		for (const dp of ASK_DECISION_MATERIAL_DP_IDS) {
			expect(DECIDE_REGISTRY[dp]?.modelStateFields, dp).toBeDefined();
		}
	});

	it("keeps identity/association out of the material for every material dp", () => {
		const meta = buildDecisionToolMeta({ key: KEY, taskKey: TASK, initiatorRole: "pm" });
		for (const [dp, material] of [
			["dp-pm-steer", steerMaterial()],
			["dp-auto", autoMaterial()],
			["dp-sign-key", signMaterial()],
		] as const) {
			const envelope = buildDecisionEnvelope({ dp, material, meta, preparation: preparation(dp) });
			const paths = Object.keys(envelope.material);
			for (const forbidden of ["key", "task_key", "schema_version", "decision_point"]) {
				expect(paths, `${dp}:${forbidden}`).not.toContain(forbidden);
			}
		}
	});
});

it.each([
	["coding", "coding"],
	["research", "research"],
	["review", "review"],
	["vision", "coding"],
	["repair", "coding"],
	["roadmap-writer", "coding"],
	["phase-writer", "coding"],
	["verifier", "research"],
	["reviewer", "research"],
	["rag-research", "research"],
	["decide_prepare", "research"],
])("binds registered %s cards to lifecycle role %s through faux", async (cardType, lifecycleRole) => {
	const { root, taskPath } = workerProject();
	fs.writeFileSync(taskPath, `type: ${cardType}\n`, "utf8");
	const calls: DecideRunRequest[] = [];
	const lifecycle = lifecycleRunner();
	const runner: DecideRunner = async (request) => {
		calls.push(request);
		const { meta } = envelopeOf(request);
		return {
			status: 0,
			timedOut: false,
			stderr: "",
			stdout: JSON.stringify({
				available: true,
				decision_id: `${request.dp}:${meta.logical_id}`,
				mode: "suggest",
				acted: false,
				answers: { reachability: { value: "continue" }, basis_id: { value: "evidence" } },
			}),
		};
	};
	const harness = await createHarness({
		extensionFactories: [
			(pi) => {
				registerAskDecisionTool(pi, {
					projectDir: root,
					taskPath,
					initiatorRole: "pm",
					key: "other-key",
					taskKey: "other-task",
					runner,
					lifecycleRunner: lifecycle.run,
				});
			},
		],
	});
	harnesses.push(harness);
	const material = {
		task_goal: "Read the files",
		reachability_facts: "The fixture is present",
		completed: "Read card",
		remaining: "Review fixture",
		blockers: "none",
		constraints: "Read-only",
	};
	const prepared = {
		prepared_at: "2026-10-25T07:10:00Z",
		basis_catalog: [
			{
				id: "evidence",
				text: "Fixture is available",
				material_refs: ["reachability_facts"],
				applies_to: ["continue"],
			},
		],
	};
	harness.setResponses([
		fauxAssistantMessage(
			[
				fauxToolCall(ASK_DECISION_TOOL, {
					dp: "dp-pm-steer",
					trigger: "test",
					material: steerMaterial(),
					preparation: preparation("dp-pm-steer"),
				}),
			],
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage(
			[fauxToolCall(ASK_DECISION_TOOL, { dp: "dp-w-check-task", trigger: "test", material, preparation: prepared })],
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage("complete"),
	]);
	await harness.session.prompt("Review the current task.");
	expect(calls).toHaveLength(1);
	expect(calls[0]?.dp).toBe("dp-w-check-task");
	expect(envelopeOf(calls[0] as DecideRunRequest).meta).toMatchObject({
		key: KEY,
		task_key: TASK,
		initiator_role: lifecycleRole,
	});
	expect(lifecycle.calls).toHaveLength(1);
	const responses = harness.session.messages
		.filter((message) => message.role === "toolResult")
		.map(getMessageText)
		.join("\n");
	expect(responses).toContain("role-forbidden");
	expect(responses).toContain("Fixture is available");
});

it.each([
	["unknown", "dp-w-check-task", "role-forbidden"],
	["pm", "dp-w-check-task", "role-forbidden"],
	["main", "dp-w-check-task", "role-forbidden"],
	["decision", "dp-w-check-task", "role-forbidden"],
	["vision", "dp-pm-steer", "role-forbidden"],
	["repair", "dp-sign-key", "role-forbidden"],
	...[
		"dp1-dispatch-type",
		"dp2-checkpoint-split",
		"dp3-worker-clarify",
		"dp4-failure-handling",
		"dp5-test-triage",
		"dp6-qg-verdict",
		"dp7-gate-failure",
		"dp8-scope-change",
		"dp9-model-select",
		"dp10-dependency",
		"dp11-credential",
		"dp12-destructive",
		"dp13-commit-release",
		"dp14-rule-conflict",
		"dp15-autopilot-gate",
		"dp16-goal",
		"dp17-spec-lock",
		"dp18-claim",
		"dp19-foreign-write",
		"dp20-stage-close",
		"dp21-refine",
		"dp22-debug-plan",
		"dp23-snapshot",
		"dp24-pi-trust",
		"dp25-signoff-conclusion",
	].map((dp) => ["vision", dp, "retired"]),
])("refuses %s card calling %s despite spoofed PM option (%s)", async (cardType, dp, reason) => {
	const { root, taskPath } = workerProject();
	fs.writeFileSync(taskPath, `type: ${cardType}\n`, "utf8");
	const decide = decideRunner();
	const lifecycle = lifecycleRunner();
	const sign = signRunner();
	const { capture, pi } = capturingApi();
	registerAskDecisionTool(pi, {
		projectDir: root,
		taskPath,
		initiatorRole: "pm",
		key: KEY,
		runner: decide.run,
		lifecycleRunner: lifecycle.run,
		signRunner: sign.run,
	});
	// Invoke the actual registered execute boundary so retired IDs are checked
	// even though the public schema deliberately cannot offer them to faux.
	const result = await capture.tools.get(ASK_DECISION_TOOL)?.execute("negative", {
		dp,
		trigger: TASK,
		material: autoMaterial(),
		preparation: preparation("dp-auto"),
	});
	expect(payloadOf(result?.content[0]?.text ?? "")).toMatchObject({ available: false, unavailable: reason });
	expect(decide.calls).toHaveLength(0);
	expect(lifecycle.calls).toHaveLength(0);
	expect(sign.calls).toHaveLength(0);
});

it("checks the current PM window's live claim on each ask and receipt", async () => {
	const project = pmProject();
	const indexFile = path.join(project.root, ".agenticdoc", "_index.parallel");
	const cwd = process.cwd();
	const self = `${os.hostname()}:${process.pid}`;
	const stub = writeStubMw(project.root);
	process.env.MW_PY = stub.stubPath;
	process.env.MW_STUB_SEEN = stub.seenDir;
	process.chdir(project.root);
	try {
		const harness = await createHarness({
			extensionFactories: [
				(pi) => {
					registerAskDecisionTool(pi, { initiatorRole: "pm" });
				},
			],
		});
		harnesses.push(harness);
		async function call(name: string, params: Record<string, unknown>) {
			harness.setResponses([
				fauxAssistantMessage([fauxToolCall(name, params)], { stopReason: "toolUse" }),
				fauxAssistantMessage("done"),
			]);
			await harness.session.prompt("Check this request.");
			const result = harness.session.messages.filter((message) => message.role === "toolResult").at(-1);
			return getMessageText(result);
		}
		const args = { dp: "dp-auto", trigger: "current", material: autoMaterial(), preparation: preparation("dp-auto") };
		const selfRow = `| ${KEY} | active | EXECUTE | ${self} | — | fixture | now |`;
		const foreign = "| foreign | active | EXECUTE | other-host:100 | — | fixture | now |";
		for (const [index, key] of [
			["", KEY],
			[foreign, "foreign"],
			[`${selfRow}\n${foreign}`, "foreign"],
			[selfRow.replace("active", "idle"), KEY],
		]) {
			fs.writeFileSync(indexFile, index, "utf8");
			expect(payloadOf(await call(ASK_DECISION_TOOL, { ...args, key }))).toMatchObject({
				available: false,
				missing_fields: ["meta.key"],
			});
			expect(fs.readdirSync(stub.seenDir)).toEqual([]);
		}
		fs.writeFileSync(indexFile, `${selfRow}\n${foreign}`, "utf8");
		const confirmed = payloadOf(await call(ASK_DECISION_TOOL, args));
		expect(confirmed.available).toBe(true);
		if (!confirmed.available) throw new Error("expected a decision for the claimed key");
		const seen = JSON.parse(fs.readFileSync(path.join(stub.seenDir, "run.json"), "utf8"));
		expect(seen.meta).toMatchObject({ key: KEY, initiator_role: "pm", task_key: null });
		const prior = fs.readdirSync(stub.seenDir);
		fs.writeFileSync(indexFile, foreign, "utf8");
		const receipt = await call(DECISION_RECEIPT_TOOL, {
			decision_id: confirmed.decision_id,
			stage: "executed",
			action: "record",
		});
		expect(receipt).toContain("meta.key");
		expect(fs.readdirSync(stub.seenDir)).toEqual(prior);
	} finally {
		process.chdir(cwd);
	}
});
