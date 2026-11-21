import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import { registerAskDecisionTool, runAskDecision } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	extractCardSections,
	planDispatchFrontmatter,
	registerWorkerTools,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import type { DecisionPreparation } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, type Harness } from "./harness.ts";

const dirs: string[] = [];
const harnesses: Harness[] = [];
afterEach(() => {
	for (const harness of harnesses.splice(0)) harness.cleanup();
	for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	vi.unstubAllEnvs();
});

function fixture(type = "coding") {
	const project = fs.mkdtempSync(path.join(os.tmpdir(), "pm-type-fallback-"));
	dirs.push(project);
	const root = path.join(project, ".agenticdoc");
	const keyDir = path.join(root, "fallback");
	fs.mkdirSync(path.join(project, ".mw"));
	fs.writeFileSync(path.join(project, ".mw/decide.json"), JSON.stringify({ enabled: true }));
	fs.mkdirSync(path.join(keyDir, "tasks"), { recursive: true });
	fs.mkdirSync(path.join(keyDir, "evidence/research"), { recursive: true });
	// Explicit legal single workspace for this isolated fixture only; the new
	// target-config gate is real and is neither mocked nor weakened.
	fs.writeFileSync(path.join(root, "target.yml"), "active: single\n", "utf8");
	fs.writeFileSync(path.join(root, "goal.md"), "# Goal\nSupport PM dispatch.\n");
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		`| fallback | active | SPEC | ${os.hostname()}:${process.pid} | — | fixture | now |\n`,
	);
	fs.writeFileSync(path.join(keyDir, "spec.md"), `# Spec\n${"Task specification. ".repeat(50)}\nAC-001\n`);
	fs.writeFileSync(path.join(keyDir, "evidence/research/spec-fixture.md"), "# Local fixture evidence\n");
	const card = [
		`type: ${type}`,
		"## 上下文",
		".agenticdoc/goal.md:1; packages/fixture.ts:1",
		"## 要求",
		"Implement the scoped change; read the original task.",
		"## 交付格式",
		"Deliver the scoped result and verification report.",
		"## 写入允许面",
		"packages/fixture.ts",
		"## 写入禁止面",
		"All other source files",
		"## 验收命令",
		"node --version",
		"## 改动历史",
		"Initial dispatch",
		"## 唯一证据文件",
		".agenticdoc/fallback/evidence/research/result.md",
		"## 审计目标",
		"packages/fixture.ts:1",
		"## 未覆盖面声明",
		"All files outside the task scope",
	].join("\n\n");
	const cardPath = path.join(keyDir, "tasks/T01.md");
	fs.writeFileSync(cardPath, card);
	const sections = extractCardSections(card);
	const material = {
		task_goal: sections.context,
		task_requirements: sections.requirements,
		task_deliverables: sections.deliverables,
		images_required: false,
	};
	const preparation: DecisionPreparation = {
		prepared_at: "2026-11-11T12:00:00Z",
		basis_catalog: [
			{
				id: "card-basis",
				text: "The original card defines this task's deliverable.",
				material_refs: ["task_deliverables"],
				applies_to: [type],
			},
		],
	};
	return { project, root, cardPath, sections, material, preparation };
}

describe("PM type selection after classifier unavailability", () => {
	it.each(["coding", "research", "review"])("dispatches %s through real tools after failed asks", async (type) => {
		const f = fixture(type);
		const asyncRunner = vi.fn(async () => ({ status: 1, stdout: "", stderr: "offline", timedOut: false }));
		const syncRunner = vi.fn(() => ({ status: 1, stdout: "", stderr: "offline", timedOut: false }));
		const lifecycle = vi.fn(async () => ({ status: 0, stdout: "{}", stderr: "", timedOut: false }));
		const store = new WorkerStore(f.root);
		const h = await createHarness({
			extensionFactories: [
				(pi) => {
					registerAskDecisionTool(pi, {
						projectDir: f.project,
						initiatorRole: "pm",
						runner: asyncRunner,
						lifecycleRunner: lifecycle,
					});
					registerWorkerTools(
						pi,
						store,
						new AckStore(f.root),
						new IndexStore(f.root),
						f.root,
						{ key: "fallback" },
						f.project,
						syncRunner,
						lifecycle,
					);
				},
			],
		});
		harnesses.push(h);
		const ask = {
			dp: "dp-w-type",
			trigger: "task",
			key: "fallback",
			material: f.material,
			preparation: f.preparation,
		};
		h.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall("ask_decision", ask),
					fauxToolCall("ask_decision", ask),
					fauxToolCall("dispatch_worker", {
						task_key: "task",
						key: "fallback",
						type,
						card_path: f.cardPath,
						description: "Execute the original card.",
						decision_preparation: f.preparation,
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("done"),
		]);
		await h.session.prompt("Classify and dispatch the task.");
		const results = h.session.messages.filter((message) => message.role === "toolResult");
		expect(results).toHaveLength(3);
		for (const result of results.slice(0, 2)) {
			const text = JSON.stringify(result.content);
			expect(text).toContain("pm-select-type");
			expect(text).not.toContain("等待人工");
			expect(text).not.toContain("TERMINAL");
		}
		expect(JSON.stringify(results[2]?.content)).toContain("Dispatched worker");
		expect(JSON.stringify(results[2]?.content)).toContain("source");
		expect(store.readAll()).toHaveLength(1);
		const taskDir = path.join(f.root, "fallback/workers/task");
		const task = fs.readFileSync(path.join(taskDir, "task.md"), "utf8");
		expect(task).toContain(`type: ${type}`);
		expect(task).toContain('type-selection: {"source":"pm"');
		expect(task).toContain('"reason":"upstream-error"');
		expect(task).toContain('"id":"card-basis"');
		expect(task).not.toMatch(/^decision:/m);
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).toContain('[TYPE_SELECTION] {"source":"pm"');
		// A failed classifier writes no consumed lifecycle fact and mints no
		// decision id; only the real PM dispatch runs once.
		expect(lifecycle).not.toHaveBeenCalled();
		expect(asyncRunner).toHaveBeenCalledTimes(2);
		expect(syncRunner).toHaveBeenCalledTimes(1);
	});

	it.each(["timeout", "entry-unavailable", "input-incomplete", "budget-exhausted", "bad-response"])(
		"keeps %s as a failure while handing judgment to PM",
		async (reason) => {
			const f = fixture();
			const result = await runAskDecision({
				projectDir: f.project,
				dp: "dp-w-type",
				trigger: "task",
				key: "fallback",
				initiatorRole: "pm",
				material: f.material,
				preparation: f.preparation,
				runner: async () => ({
					status: 0,
					stdout: JSON.stringify({ available: false, reason }),
					stderr: "",
					timedOut: false,
				}),
			});
			expect(result.payload).toEqual({ available: false, unavailable: reason, action: "pm-select-type" });
			expect(result.text).not.toContain("等待人工");
		},
	);

	it("retains claim, material, basis and type gates", () => {
		const f = fixture();
		const runner = vi.fn(() => ({ status: 1, stdout: "", stderr: "offline", timedOut: false }));
		const input = {
			cwd: f.project,
			cli: "pi",
			provider: "timi",
			taskType: "coding",
			model: "",
			modelReason: "",
			registry: undefined,
			triageRun: runner,
			dp1: { key: "fallback", taskKey: "task", sections: f.sections, preparation: f.preparation },
		};
		expect(planDispatchFrontmatter(input).ok).toBe(true);
		for (const dp1 of [
			{ ...input.dp1, key: "foreign" },
			{ ...input.dp1, preparation: undefined },
			{ ...input.dp1, sections: { ...f.sections, requirements: "" } },
			{ ...input.dp1, sections: { ...f.sections, type: "review" } },
			{
				...input.dp1,
				preparation: {
					...f.preparation,
					basis_catalog: [{ ...f.preparation.basis_catalog[0]!, applies_to: ["research"] }],
				},
			},
		])
			expect(planDispatchFrontmatter({ ...input, dp1 }).ok).toBe(false);
		expect(planDispatchFrontmatter({ ...input, images: "yes" }).ok).toBe(false);
		vi.stubEnv("PI_WORKER_TASK", "worker/task.md");
		expect(planDispatchFrontmatter(input).ok).toBe(false);
	});

	it("keeps other DP failures and worker callers blocked", async () => {
		const f = fixture();
		const runner = vi.fn(async () => ({ status: 1, stdout: "", stderr: "offline", timedOut: false }));
		const base = {
			projectDir: f.project,
			dp: "dp-w-type",
			trigger: "task",
			key: "fallback",
			material: f.material,
			preparation: f.preparation,
			runner,
		};
		const worker = await runAskDecision({ ...base, initiatorRole: "coding" });
		expect(worker.payload).toMatchObject({
			available: false,
			action: "blocked-ask-human",
			unavailable: "role-forbidden",
		});
		const other = await runAskDecision({ ...base, dp: "dp-sign-key", initiatorRole: "pm" });
		expect(other.payload).toMatchObject({ available: false, action: "blocked-ask-human" });
		expect(runner).not.toHaveBeenCalled();
	});
});
