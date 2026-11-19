import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, expect, it, vi } from "vitest";
import type {
	ExtensionAPI,
	ExtensionCommandContext,
	ToolCallEvent,
	ToolResultEvent,
} from "../../src/core/extensions/types.ts";
import { requestReplan } from "../../src/extensions/agent-team-loop/pm/replan.ts";
import { registerTrim } from "../../src/extensions/agent-team-loop/pm/trim.ts";
import { windowClaimId } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";

vi.mock("../../src/extensions/agent-team-loop/pm/replan.ts", () => ({ requestReplan: vi.fn() }));
vi.mock("node:child_process", { spy: true });

const tmp = fileURLToPath(new URL("../../../../.tmp/", import.meta.url));
const dirs: string[] = [];
afterEach(() => {
	vi.resetAllMocks();
	vi.unstubAllEnvs();
	for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function fixture() {
	mkdirSync(tmp, { recursive: true });
	const project = mkdtempSync(path.join(tmp, "trim-slash-"));
	dirs.push(project);
	const root = path.join(project, ".agenticdoc");
	const agent = path.join(project, "agent");
	const script = path.join(project, "pm_state.py");
	vi.stubEnv("PI_CODING_AGENT_DIR", agent);
	mkdirSync(path.join(agent, "extensions"), { recursive: true });
	writeFileSync(path.join(agent, "extensions", ".mw-pm-state-path"), script);
	mkdirSync(path.join(root, "sample"), { recursive: true });
	writeFileSync(path.join(root, "sample", "pm-state.md"), "PM state source");
	const row = { key: "sample", status: "active", phase: "EXECUTE", claimId: windowClaimId() };

	const registerTool = vi.fn<ExtensionAPI["registerTool"]>();
	const on = vi.fn<(kind: string, handler: (...args: never[]) => unknown) => void>();
	const pi = {
		registerTool,
		on,
		getActiveTools: () => [],
		setActiveTools: vi.fn(),
		sendUserMessage: vi.fn(),
	};
	const requestCompaction = vi.fn();
	const notify = vi.fn();
	const ctx = { isIdle: () => true, requestCompaction, ui: { notify } } as unknown as ExtensionCommandContext;
	const start = registerTrim(
		pi as unknown as ExtensionAPI,
		project,
		root,
		{ readAll: () => [row] } as unknown as IndexStore,
		() => "sample",
		windowClaimId,
	);
	const command = {
		handler: (input: string, context: ExtensionCommandContext) => start(input.slice(4).trim(), context),
	};
	const tool = registerTool.mock.calls.find(([config]) => config.name === "trim_progress")?.[0];
	if (!tool) throw new Error("trim tool missing");
	const submit = (operation: string, extra?: Record<string, string>) =>
		tool.execute("trim", { operation, ...extra }, undefined, undefined, ctx);
	const event = (kind: string, payload: unknown) =>
		on.mock.calls.find(([name]) => name === kind)?.[1](payload as never, ctx as never);
	const check = (isError: boolean) => {
		const call = {
			type: "tool_call",
			toolName: "bash",
			toolCallId: "proof_7",
			input: { command: "check" },
		} satisfies ToolCallEvent;
		event("tool_call", call);
		event("tool_result", {
			...call,
			type: "tool_result",
			isError,
			content: [],
			details: undefined,
		} satisfies ToolResultEvent);
	};
	vi.mocked(requestReplan).mockImplementation((_project, req) =>
		req.operation === "trim_steer"
			? { ok: true, state: "queued" }
			: req.task
				? { ok: true, snapshot: "snapshot", issue: "issue", facts: { task: "work-run", status: "running" } }
				: { ok: true, workers: [{ task: "work-run", status: "running" }] },
	);
	vi.mocked(spawnSync).mockReturnValue({
		pid: 1,
		status: 0,
		stdout: '{"applied": true}',
		stderr: "",
		signal: null,
		output: [],
	} as ReturnType<typeof spawnSync>);
	return { command, ctx, pi, row, check, event, submit, requestCompaction, notify };
}

it("routes /mw trim task and requires an actual successful check to steer", async () => {
	const f = fixture();
	const edit = { remaining: "Finish the real path", stop: "Extra benchmarks" };
	await expect(f.submit("steer", edit)).rejects.toThrow("没有");
	await f.command.handler("trim card-name", f.ctx);
	expect(f.pi.sendUserMessage).toHaveBeenCalledWith(expect.stringContaining("work-run"));
	await expect(f.submit("prepare_task", { task: "another-task" })).rejects.toThrow("范围");
	await expect(f.submit("steer", edit)).rejects.toThrow("最小验证");
	f.check(true);
	await expect(f.submit("steer", edit)).rejects.toThrow("最小验证");
	f.check(false);
	await expect(f.submit("steer", edit)).resolves.toMatchObject({ details: { state: "queued" } });
	expect(requestReplan).toHaveBeenLastCalledWith(
		expect.any(String),
		expect.objectContaining({ operation: "trim_steer", task: "work-run", verification: "proof_7", ...edit }),
	);
	await expect(f.submit("steer", edit)).rejects.toThrow("最小验证");
});

it("scopes replan to the verified target and compacts the key at a native boundary", async () => {
	const f = fixture();
	await f.command.handler("trim", f.ctx);
	await f.submit("prepare_task", { task: "work-run" });
	const replan = {
		type: "tool_call",
		toolName: "replan_tasks",
		toolCallId: "replan",
		input: { operation: "preview", key: "sample", issue: "issue", snapshot: "snapshot" },
	} satisfies ToolCallEvent;
	expect(f.event("tool_call", replan)).toMatchObject({ block: true });
	f.check(false);
	expect(f.event("tool_call", replan)).toBeUndefined();
	expect(f.event("tool_call", { ...replan, input: { ...replan.input, issue: "foreign" } })).toMatchObject({
		block: true,
	});
	await f.submit("prepare_context");
	await expect(f.submit("compact_context", { summary: "reviewed" })).rejects.toThrow("最小验证");
	f.check(false);
	await expect(f.submit("compact_context", { summary: "reviewed" })).resolves.toMatchObject({
		details: { state: "compacted", transcript: "queued" },
	});
	expect(spawnSync).toHaveBeenCalledWith(
		expect.any(String),
		expect.arrayContaining(["--key", "sample", "--apply", "--window-claim-id", f.row.claimId]),
		expect.objectContaining({ input: "reviewed" }),
	);
	expect(f.requestCompaction).toHaveBeenCalledOnce();
});

it("refuses trim after the window loses its claim", async () => {
	const f = fixture();
	await f.command.handler("trim work-run", f.ctx);
	f.check(false);
	f.row.claimId = "foreign:123";
	await expect(f.submit("steer", { remaining: "Finish", stop: "Explore" })).rejects.toThrow("认领");
});
