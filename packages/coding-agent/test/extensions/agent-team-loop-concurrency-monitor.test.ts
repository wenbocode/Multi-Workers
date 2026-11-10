import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionContext, ToolDefinition } from "../../src/core/extensions/types.ts";
import { readMonitorState, renderMonitorLines } from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import { registerWorkerTools } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import {
	readConcurrencySnapshot,
	taskQueueStatus,
} from "../../src/extensions/agent-team-loop/shared/concurrency-view.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import {
	acquireModelSlot,
	readConcurrencyState,
	setConcurrencyLimit,
} from "../../src/extensions/agent-team-loop/shared/model-concurrency.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

let root: string;
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-monitor-concurrency-"));
	vi.stubEnv("MW_CONCURRENCY_DIR", path.join(root, "limits"));
	vi.stubEnv("PI_WORKER_TASK", "");
});
afterEach(() => {
	vi.unstubAllEnvs();
	fs.rmSync(root, { recursive: true, force: true });
});

it("actual enqueue attribution reaches monitor and PM list_tasks, then disappears on admission", async () => {
	const project = path.join(root, "project-a");
	const docs = path.join(project, ".agenticdoc");
	fs.mkdirSync(docs, { recursive: true });
	const taskPath = path.join(docs, "key", "workers", "same-name", "task.md");
	const workerStore = new WorkerStore(docs);
	await workerStore.upsert({
		taskKey: "same-name",
		status: "running",
		cli: "pi",
		provider: "openai-codex",
		taskPath,
		dispatchedAt: new Date().toISOString(),
		updatedAt: new Date().toISOString(),
		model: "codex/gpt-a",
	});
	const registered = new Map<string, ToolDefinition>();
	registerWorkerTools(
		{ registerTool: (tool: ToolDefinition) => registered.set(tool.name, tool) } as unknown as ExtensionAPI,
		workerStore,
		new AckStore(docs),
		new IndexStore(docs),
		docs,
		{ key: "key" },
		project,
	);
	const list = registered.get("list_tasks");
	if (!list) throw new Error("list_tasks missing");
	await setConcurrencyLimit("codex/*", 1);
	const release = await acquireModelSlot("codex/gpt-b");
	vi.stubEnv("PI_WORKER_TASK", taskPath);
	const queued = acquireModelSlot("openai-codex-local/gpt-a");
	await vi.waitFor(() => expect(readConcurrencyState().requests.filter((r) => r.phase === "waiting")).toHaveLength(1));
	try {
		const state = readConcurrencyState();
		expect(state.requests.find((r) => r.phase === "waiting")).toMatchObject({ project, taskPath });
		const now = Date.now() + 3000;
		const snapshot = readMonitorState(project, now);
		expect(snapshot.concurrency?.rows).toEqual(
			expect.arrayContaining([
				{ route: "codex/*", limit: 1, active: 1, waiting: 1 },
				{ route: "codex/gpt-a", limit: 1, active: 0, waiting: 1 },
				{ route: "codex/gpt-b", limit: 1, active: 1, waiting: 0 },
			]),
		);
		expect(renderMonitorLines(snapshot).join("\n")).toContain("LLM queued: codex/gpt-a 3s");
		const output = await list.execute("list", { scope: "all" }, undefined, undefined, {} as ExtensionContext);
		expect(output.content).toEqual([
			expect.objectContaining({ text: expect.stringContaining("LLM queued: codex/gpt-a") }),
		]);
		const other = taskPath.replace("project-a", "project-b");
		expect(taskQueueStatus(readConcurrencySnapshot(), other, now)).toBe("");
		await setConcurrencyLimit("codex/*", 2);
		const releaseQueued = await queued;
		try {
			expect(taskQueueStatus(readConcurrencySnapshot(), taskPath, now)).toBe("");
			expect(readConcurrencySnapshot().rows.find((r) => r.route === "codex/*")).toMatchObject({
				limit: 2,
				active: 2,
				waiting: 0,
			});
		} finally {
			await releaseQueued();
		}
	} finally {
		await release();
		await (await queued)();
	}
});

it("reports missing and corrupt state without mutating it or breaking monitor", () => {
	const directory = process.env.MW_CONCURRENCY_DIR!;
	expect(readConcurrencySnapshot().rows).toEqual([]);
	expect(fs.existsSync(directory)).toBe(false);
	fs.mkdirSync(directory);
	const file = path.join(directory, "state.json");
	fs.writeFileSync(file, "broken");
	const snapshot = readMonitorState(root, Date.now());
	expect(renderMonitorLines(snapshot).join("\n")).toContain("LLM concurrency: unavailable");
	expect(taskQueueStatus(readConcurrencySnapshot(), "task.md", Date.now())).toBe("LLM queue unavailable");
	expect(fs.readFileSync(file, "utf8")).toBe("broken");
});

it("keeps exact and aggregate counts distinct and removes canceled queue entries", async () => {
	await setConcurrencyLimit("fake/*", 2);
	await setConcurrencyLimit("fake/a", 1);
	const release = await acquireModelSlot("fake/a");
	const abort = new AbortController();
	const queued = acquireModelSlot("fake/a", { signal: abort.signal });
	const rejected = expect(queued).rejects.toThrow();
	await vi.waitFor(() => expect(readConcurrencySnapshot().rows.find((r) => r.route === "fake/a")?.waiting).toBe(1));
	expect(readConcurrencySnapshot().rows).toEqual([
		{ route: "fake/*", limit: 2, active: 1, waiting: 1 },
		{ route: "fake/a", limit: 1, active: 1, waiting: 1 },
	]);
	abort.abort();
	await rejected;
	expect(readConcurrencySnapshot().rows.every((r) => r.waiting === 0)).toBe(true);
	await release();
});
