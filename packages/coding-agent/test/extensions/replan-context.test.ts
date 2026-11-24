import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Check } from "typebox/value";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ToolDefinition } from "../../src/core/extensions/types.ts";
import { PARALLEL_PROTOCOL, startWorkerPollLoop } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import { registerReplanTool } from "../../src/extensions/agent-team-loop/pm/replan.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const temporaryDirs: string[] = [];

afterEach(() => {
	vi.clearAllTimers();
	vi.useRealTimers();
	for (const dir of temporaryDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

describe("replan context and triggers", () => {
	it("exposes bounded inventory paging and rejects bulk requests", () => {
		const tools: ToolDefinition[] = [];
		registerReplanTool(
			{ registerTool: (tool: ToolDefinition) => tools.push(tool) } as unknown as ExtensionAPI,
			".",
			() => "self",
		);
		const tool = tools[0];
		if (!tool) throw new Error("replan tool missing");
		expect(tool.description).toContain("Apply split, narrow and direct-exec directly as the PM");
		expect(tool.description).toContain("Escalate requires a matching dp-pm-steer decision_id");
		const base = { operation: "inspect", key: "demo" };
		expect(Check(tool.parameters, base)).toBe(true);
		expect(Check(tool.parameters, { ...base, section: "cards", offset: 20, limit: 50 })).toBe(true);
		for (const invalid of [{ limit: 0 }, { limit: 51 }, { offset: -1 }, { offset: 0.5 }, { section: "all" }]) {
			expect(Check(tool.parameters, { ...base, ...invalid })).toBe(false);
		}
	});

	it.each(["done", "failed", "needs-clarification", "lost"] as const)(
		"scopes %s readback instructions and delivers each terminal only once",
		async (status) => {
			const project = fs.mkdtempSync(path.join(os.tmpdir(), "replan-context-"));
			temporaryDirs.push(project);
			const root = path.join(project, ".agenticdoc");
			const taskDir = path.join(root, "demo", "workers", "task-1");
			fs.mkdirSync(taskDir, { recursive: true });
			fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n");
			fs.writeFileSync(path.join(taskDir, "output.md"), "## Summary\nTask result\n");
			const store = new WorkerStore(root);
			const entry = {
				taskKey: "task-1",
				status: "running" as const,
				cli: "pi",
				provider: "faux",
				model: "",
				taskPath: path.join(taskDir, "task.md"),
				dispatchedAt: new Date().toISOString(),
				updatedAt: new Date().toISOString(),
			};
			await store.upsert(entry);
			const sendMessage = vi.fn();
			const pi = { sendMessage, appendEntry: vi.fn() } as unknown as ExtensionAPI;
			vi.useFakeTimers();
			startWorkerPollLoop(
				pi,
				store,
				new AckStore(root),
				new IndexStore(root),
				root,
				{ key: "demo" },
				{ ctx: undefined },
				100,
			);
			await store.upsert({ ...entry, status });
			await vi.advanceTimersByTimeAsync(400);
			expect(sendMessage).toHaveBeenCalledTimes(1);
			const message = sendMessage.mock.calls[0]?.[0] as { content: string };
			expect(message.content).toContain("Task result");
			if (status === "done") {
				expect(message.content).toContain("按现有计划推进");
				expect(message.content).not.toContain("replan_tasks");
				expect(message.content).not.toContain("preview");
			} else {
				expect(message.content).toContain("key=demo, task=task-1");
				expect(message.content).toContain("重派被 replan-required 拒绝");
				expect(message.content).toContain("证据未变化时复用");
				expect(message.content).toContain("收窄、拆卡和接手可以由 PM 直接发布");
				expect(message.content).toContain("上抛须用匹配的 dp-pm-steer 裁决");
			}
		},
	);

	it("does not prescribe inventory inspection on ordinary resume", () => {
		expect(PARALLEL_PROTOCOL).toContain("正常接续 key、worker 成功或继续派发现有任务");
		expect(PARALLEL_PROTOCOL).toContain("不例行调用 replan_tasks");
		expect(PARALLEL_PROTOCOL).not.toContain("接续 key 时用 replan_tasks inspect");
	});
});
