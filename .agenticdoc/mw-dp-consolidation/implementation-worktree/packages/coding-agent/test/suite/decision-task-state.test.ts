import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	buildDecisionToolMeta,
	type DecideRunner as AsyncDecideRunner,
	type LifecycleRunner,
	registerAskDecisionTool,
	runAskDecision,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	type DecideRunner,
	type DecideRunRequest,
	newDecisionMeta,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import * as bridge from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, type Harness } from "./harness.ts";

const dirs: string[] = [];
const harnesses: Harness[] = [];
afterEach(() => {
	for (const harness of harnesses.splice(0)) harness.cleanup();
	vi.restoreAllMocks();
	for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});
function project(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "decision-task-state-"));
	dirs.push(dir);
	fs.mkdirSync(path.join(dir, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(dir, ".mw"), { recursive: true });
	return dir;
}
const before = {
	status: "running" as const,
	source: "agent-report" as const,
	observed_at: "2026-10-24T08:00:00Z",
	completed: ["synthetic progress"],
	remaining: null,
	blockers: [],
};

it("keeps the before observation in local metadata and freezes its lists", () => {
	const input = { key: "owner", taskKey: "task", taskBefore: { ...before, completed: [...before.completed] } };
	const meta = newDecisionMeta(input);
	expect(meta).toHaveProperty("task_before", before);
	input.taskBefore.completed.push("later");
	expect(meta.task_before?.completed).toEqual(["synthetic progress"]);
});

it("captures only the exact owning task row, without writing the queue", async () => {
	expect(bridge).toHaveProperty("captureDecisionTaskState");
	const dir = project();
	const store = new WorkerStore(path.join(dir, ".agenticdoc"));
	await store.upsert({
		taskKey: "task",
		status: "running",
		cli: "pi",
		provider: "timi",
		taskPath: path.join(dir, ".agenticdoc/owner/workers/task/task.md"),
		dispatchedAt: "",
		updatedAt: "",
		model: "",
	});
	const bytes = fs.readFileSync(store.queuePath);
	expect(bridge.captureDecisionTaskState(store, "owner", "task")).toMatchObject({
		status: "running",
		source: "worker-registry",
		completed: null,
		remaining: null,
		blockers: null,
	});
	expect(bridge.captureDecisionTaskState(store, "other", "task").status).toBe("unknown");
	expect(fs.readFileSync(store.queuePath)).toEqual(bytes);
});

it("does not convert a damaged or failed queue read into not-queued", () => {
	expect(bridge).toHaveProperty("captureDecisionTaskState");
	const dir = project();
	const store = new WorkerStore(path.join(dir, ".agenticdoc"));
	expect(bridge.captureDecisionTaskState(store, "owner", "task").status).toBe("unknown");
	expect(fs.existsSync(store.queuePath)).toBe(false);
	fs.writeFileSync(store.queuePath, "broken row\n");
	expect(bridge.captureDecisionTaskState(store, "owner", "task").status).toBe("unknown");
	vi.spyOn(store, "readQueue").mockImplementation(() => {
		throw new Error("synthetic unreadable queue");
	});
	expect(bridge.captureDecisionTaskState(store, "owner", "task").status).toBe("unknown");
});

it("does not trust a same-owner row from a different root or an unsupported queue version", async () => {
	const dir = project();
	const store = new WorkerStore(path.join(dir, ".agenticdoc"));
	await store.upsert({
		taskKey: "task",
		status: "running",
		cli: "pi",
		provider: "timi",
		taskPath: path.join(dir, "else/.agenticdoc/owner/workers/task/task.md"),
		dispatchedAt: "",
		updatedAt: "",
		model: "",
	});
	expect(bridge.captureDecisionTaskState(store, "owner", "task").status).toBe("unknown");
	const queue = store.readQueue();
	queue.rows[0].taskPath = path.join(dir, ".agenticdoc/owner/workers/task/task.md");
	queue.version = 99;
	vi.spyOn(store, "readQueue").mockReturnValue(queue);
	expect(bridge.captureDecisionTaskState(store, "owner", "task").status).toBe("unknown");
});

it("refuses linked queue observations without reading the link target", () => {
	expect(bridge).toHaveProperty("captureDecisionTaskState");
	const dir = project();
	const linked = path.join(dir, "linked");
	fs.mkdirSync(linked);
	fs.writeFileSync(path.join(linked, "_workers.parallel"), "private target\n");
	const alias = path.join(dir, "alias");
	fs.symlinkSync(linked, alias, "junction");
	const store = new WorkerStore(alias);
	const read = vi.spyOn(store, "readQueue");
	expect(bridge.captureDecisionTaskState(store, "owner", "task").status).toBe("unknown");
	expect(read).not.toHaveBeenCalled();
});

async function dispatch(
	refused: boolean,
): Promise<{ calls: DecideRunRequest[]; feedback: Record<string, unknown>[]; store: WorkerStore; taskDir: string }> {
	const dir = project();
	const root = path.join(dir, ".agenticdoc");
	const owner = "owner";
	const task = "new-task";
	const keyDir = path.join(root, owner);
	fs.mkdirSync(path.join(keyDir, "tasks"), { recursive: true });
	fs.writeFileSync(path.join(root, "goal.md"), "# synthetic goal\n");
	fs.writeFileSync(path.join(keyDir, "spec.md"), `# Spec\n${"x".repeat(600)}\n| AC-001 | test |\n`);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}\n`);
	fs.mkdirSync(path.join(keyDir, "evidence/research"), { recursive: true });
	for (const phase of ["spec", "design"])
		fs.writeFileSync(path.join(keyDir, `evidence/research/${phase}-test-20261024.md`), "# research\n");
	const card = path.join(keyDir, "tasks/task.md");
	fs.writeFileSync(
		card,
		[
			"type: coding",
			"## 上下文",
			".agenticdoc/goal.md:1 synthetic goal",
			"## 要求",
			"synthetic requirement",
			"## 交付格式",
			"synthetic report",
			"## 写入允许面",
			"- implementation.ts",
			"## 写入禁止面",
			"- other",
			"## 验收命令",
			"- synthetic",
			"## 改动历史",
			"- new",
		].join("\n"),
	);
	fs.writeFileSync(path.join(dir, ".mw/decide.json"), JSON.stringify({ enabled: true }));
	const store = new WorkerStore(root);
	fs.writeFileSync(store.queuePath, "# mw-queue:v2\n");
	const calls: DecideRunRequest[] = [];
	const feedback: Record<string, unknown>[] = [];
	if (refused) {
		const other = path.join(root, owner, "workers/other-task/task.md");
		fs.mkdirSync(path.dirname(other), { recursive: true });
		fs.writeFileSync(other, "write_face: implementation.ts\n");
		await store.upsert({
			taskKey: "other-task",
			status: "running",
			cli: "pi",
			provider: "timi",
			taskPath: other,
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
	}
	const run: DecideRunner = (request) => {
		calls.push(request);
		return {
			status: 0,
			stdout: JSON.stringify({
				available: true,
				mode: "suggest",
				acted: false,
				decision_id: "dp1-dispatch-type:synthetic",
				answers: { triage_type: { value: "coding", confidence: 0.9 } },
				confidence_source: "api",
			}),
			stderr: "",
			timedOut: false,
		};
	};
	const lifecycle: LifecycleRunner = async (request) => {
		feedback.push(JSON.parse(request.input) as Record<string, unknown>);
		return {
			status: 0,
			stdout: JSON.stringify({
				stage: (feedback.at(-1) as Record<string, unknown>).stage,
				status: "written",
				recorded: true,
			}),
			stderr: "",
			timedOut: false,
		};
	};
	const harness = await createHarness({
		extensionFactories: [
			(pi) =>
				bridge.registerWorkerTools(
					pi,
					store,
					new AckStore(root),
					new IndexStore(root),
					root,
					{ key: owner },
					dir,
					run,
					lifecycle,
				),
		],
	});
	harnesses.push(harness);
	harness.setResponses([
		fauxAssistantMessage(
			fauxToolCall("dispatch_worker", {
				task_key: task,
				card_path: card,
				description: "synthetic task",
				type: "coding",
				key: owner,
			}),
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage("done"),
	]);
	await harness.session.prompt("dispatch synthetic task");
	return { calls, feedback, store, taskDir: path.join(root, owner, "workers", task) };
}

it("generic material producer preserves a local before report and rejects task-less reports before sending", async () => {
	const input = { key: "owner", taskKey: "task", initiatorRole: "pm" as const, taskBefore: before };
	expect(buildDecisionToolMeta(input)).toHaveProperty("task_before", before);
	const calls: DecideRunRequest[] = [];
	const runner: AsyncDecideRunner = async (request) => {
		calls.push(request);
		return {
			status: 0,
			stdout: JSON.stringify({
				available: true,
				mode: "suggest",
				acted: false,
				decision_id: "dp2-checkpoint-split:synthetic",
				answers: { checkpoint_action: { value: "narrow", confidence: 0.9 } },
				confidence_source: "api",
			}),
			stderr: "",
			timedOut: false,
		};
	};
	const lifecycleRunner: LifecycleRunner = async () => ({
		status: 0,
		stdout: JSON.stringify({ stage: "consumed", status: "written", recorded: true }),
		stderr: "",
		timedOut: false,
	});
	const request = {
		...input,
		projectDir: project(),
		dp: "dp2-checkpoint-split",
		trigger: "task",
		material: {
			task_goal: "synthetic",
			task_requirements: "synthetic",
			task_deliverables: "synthetic",
			pm_decision_background: "synthetic",
		},
		runner,
		lifecycleRunner,
	};
	await runAskDecision(request);
	expect(calls).toHaveLength(1);
	const envelope = JSON.parse((calls[0] as DecideRunRequest).input) as {
		material: Record<string, unknown>;
		meta: Record<string, unknown>;
	};
	expect(envelope.meta.task_before).toEqual(before);
	expect(envelope.material).not.toHaveProperty("task_before");
	const refused = await runAskDecision({ ...request, taskKey: null });
	expect(refused.spawned).toBe(false);
	expect(calls).toHaveLength(1);
});

it("explicit receipt carries an Agent after report on the same decision, without replaying a model or action", async () => {
	const root = project();
	const feedback: Record<string, unknown>[] = [];
	let modelCalls = 0;
	const runner: AsyncDecideRunner = async () => {
		modelCalls++;
		return {
			status: 0,
			stdout: JSON.stringify({
				available: true,
				mode: "suggest",
				acted: false,
				decision_id: "dp2-checkpoint-split:synthetic",
				answers: { checkpoint_action: { value: "narrow", confidence: 0.9 } },
				confidence_source: "api",
			}),
			stderr: "",
			timedOut: false,
		};
	};
	const lifecycleRunner: LifecycleRunner = async (request) => {
		const row = JSON.parse(request.input) as Record<string, unknown>;
		feedback.push(row);
		return {
			status: 0,
			stdout: JSON.stringify({ stage: row.stage, status: "written", recorded: true }),
			stderr: "",
			timedOut: false,
		};
	};
	const harness = await createHarness({
		extensionFactories: [
			(pi) => {
				registerAskDecisionTool(pi, {
					projectDir: root,
					key: "owner",
					initiatorRole: "pm",
					runner,
					lifecycleRunner,
				});
			},
		],
	});
	harnesses.push(harness);
	harness.setResponses([
		fauxAssistantMessage(
			fauxToolCall("ask_decision", {
				dp: "dp2-checkpoint-split",
				trigger: "task",
				task_key: "task",
				task_before: before,
				material: {
					task_goal: "synthetic",
					task_requirements: "synthetic",
					task_deliverables: "synthetic",
					pm_decision_background: "synthetic",
				},
			}),
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage(
			fauxToolCall("decision_receipt", {
				decision_id: "dp2-checkpoint-split:synthetic",
				stage: "settled",
				outcome: "ok",
				task_after: before,
			}),
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage("done"),
	]);
	await harness.session.prompt("synthetic report only");
	expect(modelCalls).toBe(1);
	expect(feedback).toHaveLength(2);
	expect(feedback[0]).not.toHaveProperty("task_after");
	expect(feedback[1]?.task_after).toEqual(before);
	expect(feedback[0]?.meta).toEqual(feedback[1]?.meta);
});

describe("real dispatch producer via suite harness/faux only", () => {
	it("captures before the decision and after actual enqueue, never claims running", async () => {
		const result = await dispatch(false);
		expect(result.calls).toHaveLength(1);
		const input = JSON.parse((result.calls[0] as DecideRunRequest).input) as {
			material: Record<string, unknown>;
			meta: Record<string, unknown>;
		};
		expect(input.meta.task_before).toMatchObject({ status: "not-queued", source: "worker-registry" });
		expect(input.material).not.toHaveProperty("task_before");
		expect(result.feedback.find((row) => row.stage === "settled")?.task_after).toMatchObject({
			status: "pending",
			source: "worker-registry",
		});
		expect(result.feedback.find((row) => row.stage === "consumed")).not.toHaveProperty("task_after");
		expect(result.store.findByKey("new-task")?.status).toBe("pending");
	});
	it("captures refusal as no new queue row, without marking the answer or task executed", async () => {
		const result = await dispatch(true);
		expect(result.calls).toHaveLength(1);
		expect(result.feedback.find((row) => row.stage === "settled")).toMatchObject({
			outcome: "rework",
			reason: "dispatch-refused",
			task_after: { status: "not-queued" },
		});
		expect(result.feedback.some((row) => row.stage === "executed")).toBe(false);
		expect(result.store.findByKey("new-task")).toBeUndefined();
		expect(fs.existsSync(result.taskDir)).toBe(false);
	});
});
