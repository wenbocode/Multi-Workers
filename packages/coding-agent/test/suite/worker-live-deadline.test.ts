import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	registerWorkerDeadlineApproval,
	takeDeadlineReview,
} from "../../src/extensions/agent-team-loop/pm/worker-deadline-tool.ts";
import { sha256EolNormalizedBytes } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import { recordRunProgress } from "../../src/extensions/agent-team-loop/shared/run-progress.ts";
import {
	RUN_SCHEMA,
	type RunState,
	readRunState,
	writeRunState,
} from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import {
	approveWorkerDeadline,
	type DeadlineApproval,
	readWorkerDeadline,
	startWorkerDeadline,
	workerDeadlineFiles,
} from "../../src/extensions/agent-team-loop/shared/worker-deadline.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { WORKER_PROGRESS_TOOL } from "../../src/extensions/agent-team-loop/worker/worker-progress-tool.ts";
import * as shell from "../../src/utils/shell.ts";
import { createHarness } from "./harness.ts";

const MIN = 60_000;
const start = Date.parse("2026-11-22T07:00:00.000Z");
const claim = "test-pm:42";
const workspaces: string[] = [];
const evidenceRef = ".agenticdoc/demo/workers/task/report.md";

afterEach(() => {
	vi.useRealTimers();
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	for (const workspace of workspaces.splice(0)) fs.rmSync(workspace, { force: true, recursive: true });
});

function fixture(overrides: Record<string, number> = {}, ceiling = Infinity, fixedSteps?: number) {
	const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "mw-live-deadline-"));
	workspaces.push(workspace);
	const root = path.join(workspace, ".agenticdoc");
	const home = path.join(workspace, "private");
	const dir = path.join(root, "demo", "workers", "task");
	const card = "type: coding\n\nVerify AC-001 and AC-002.\n";
	const pin = sha256EolNormalizedBytes(Buffer.from(card));
	const taskFile = path.join(dir, "task.md");
	fs.mkdirSync(dir, { recursive: true });
	fs.mkdirSync(path.join(root, "demo", "tasks"), { recursive: true });
	fs.writeFileSync(path.join(root, "_index.parallel"), `| demo | active | EXECUTE | ${claim} | | | now |\n`);
	fs.writeFileSync(path.join(root, "demo", "tasks", "task.md"), card);
	fs.writeFileSync(
		taskFile,
		`type: coding\ntimeout: 10\ncard_path: tasks/task.md\ncard_sha256: ${pin}\n\nComplete the task.\n`,
	);
	const run: RunState = {
		schema: RUN_SCHEMA,
		task_key: "task",
		owner_key: "demo",
		status: "running",
		kind: "coding",
		run_id: `task@${new Date(start).toISOString()}`,
		started_at: new Date(start).toISOString(),
		artifacts: [],
	};
	const files = workerDeadlineFiles(root, "demo", "task", run.run_id, home);
	fs.mkdirSync(path.dirname(files.policy), { recursive: true });
	const policy = {
		card_sha256: pin,
		expires_at: start + 60 * MIN,
		review_after_ms: 8 * MIN,
		max_run_ms: 16 * MIN,
		max_extension_ms: 3 * MIN,
		max_total_extension_ms: 6 * MIN,
		max_approvals: 2,
		max_steps: 10,
		max_cost: 10,
		no_progress_limit: 6,
		...overrides,
	};
	fs.writeFileSync(files.policy, JSON.stringify(policy));
	run.live_deadline = startWorkerDeadline(root, dir, run, start, start + 10 * MIN, ceiling, fixedSteps, home);
	expect(run.live_deadline).toBeDefined();
	expect(writeRunState(dir, run).ok).toBe(true);
	const milestone = {
		completed: [{ acceptance: "AC-001", evidence: evidenceRef }],
		current: "Reviewing the second result",
		remaining: "Verify AC-002",
		blocker: "",
		next: "Run the remaining check",
	};
	function report(at = start + 8 * MIN, content = "AC-001 PASS") {
		fs.writeFileSync(path.join(dir, "report.md"), content);
		recordRunProgress(dir, run.run_id, { milestone: { ...milestone, at: new Date(at).toISOString() } });
	}
	function view(now = start + 9 * MIN) {
		return readWorkerDeadline(root, dir, readRunState(dir)!, now, home);
	}
	const request: DeadlineApproval = {
		requestId: "first",
		version: 0,
		deadline: start + 13 * MIN,
		reviewAt: start + 12 * MIN,
		reason: "AC-001 passed and only the second check remains",
		next: "Run the second check",
	};
	function approve(
		input: DeadlineApproval = request,
		now = () => start + 9 * MIN,
		caller = claim,
		signal?: AbortSignal,
	) {
		return approveWorkerDeadline(root, dir, caller, run.run_id, input, { home, now, signal });
	}
	return { dir, root, home, run, files, policy, report, request, approve, view, milestone, taskFile };
}

function latch() {
	let release = () => {};
	const done = new Promise<void>((resolve) => {
		release = resolve;
	});
	return { done, release };
}

describe("Worker live deadline decisions", () => {
	it("uses the existing timeout path when there is no provisioned allowance", () => {
		const f = fixture();
		fs.unlinkSync(f.files.policy);
		const legacy = { ...f.run, live_deadline: undefined };
		expect(
			startWorkerDeadline(f.root, f.dir, legacy, start, start + 10 * MIN, Infinity, undefined, f.home),
		).toBeUndefined();
		expect(readWorkerDeadline(f.root, f.dir, legacy, start, f.home)).toBeUndefined();
	});

	it("delivers a review once for a low-risk run with separate activity and no reported ETA", () => {
		const f = fixture();
		f.report();
		recordRunProgress(f.dir, f.run.run_id, {
			activity: { at: new Date(start + 8 * MIN).toISOString(), source: "tool", tools: [] },
		});
		expect(takeDeadlineReview(f.root, f.dir, claim, start + 8 * MIN - 1, f.home)).toBeUndefined();
		expect(takeDeadlineReview(f.root, f.dir, claim, start + 8 * MIN, f.home)).toMatchObject({
			runId: f.run.run_id,
			eta: "unknown",
			deadline: start + 10 * MIN,
			availableExtensionMs: 3 * MIN,
			availableApprovals: 2,
			progress: { milestone: { remaining: "Verify AC-002" }, activity: { source: "tool" } },
		});
		expect(takeDeadlineReview(f.root, f.dir, claim, start + 8 * MIN + 1, f.home)).toBeUndefined();
	});

	it("persists one approval through concurrent requests, repeat delivery, and a new reader", async () => {
		const f = fixture();
		f.report();
		const race = await Promise.allSettled([f.approve(), f.approve({ ...f.request, requestId: "parallel" })]);
		expect(race.map((result) => result.status)).toEqual(["fulfilled", "rejected"]);
		expect(await f.approve()).toMatchObject({ requestId: "first", deadline: start + 13 * MIN, version: 0 });
		expect(f.view(start + 10 * MIN)).toMatchObject({ deadline: start + 13 * MIN, version: 1 });
		expect(f.view(start + 13 * MIN - 1)?.stop).toBeUndefined();
		expect(f.view(start + 13 * MIN)?.stop).toBe("worker-deadline");
		f.report(start + 10 * MIN); // timestamp, ETA and heartbeat do not prove additional progress
		const next = {
			...f.request,
			requestId: "next",
			version: 1,
			deadline: start + 16 * MIN,
			reviewAt: start + 15 * MIN,
		};
		await expect(f.approve(next, () => start + 11 * MIN)).rejects.toThrow("fresh business progress");
		f.report(start + 11 * MIN, "AC-001 PASS\nSecond check prepared");
		await expect(f.approve(next, () => start + 11 * MIN)).resolves.toMatchObject({ deadline: start + 16 * MIN });
		expect(f.view(start + 11 * MIN)).toMatchObject({ availableApprovals: 0, deadline: start + 16 * MIN });
		expect(readRunState(f.dir)?.live_deadline?.usage).toEqual({ steps: 0, cost: 0, noProgress: 0 });
	});

	it("rejects missing, stale, other-run and unverifiable milestone evidence", async () => {
		const f = fixture();
		recordRunProgress(f.dir, f.run.run_id, {
			activity: { at: new Date(start + 8 * MIN).toISOString(), source: "tool", tools: [] },
		});
		await expect(f.approve()).rejects.toThrow("fresh business progress");
		f.report(start - MIN);
		await expect(f.approve()).rejects.toThrow("fresh business progress");
		fs.writeFileSync(
			path.join(f.dir, "run-progress.json"),
			JSON.stringify({ run_id: "other", milestone: f.milestone }),
		);
		await expect(f.approve()).rejects.toThrow("fresh business progress");
		f.report();
		fs.unlinkSync(path.join(f.dir, "report.md"));
		await expect(f.approve()).rejects.toThrow("fresh business progress");
		await expect(f.approve(f.request, undefined, "wrong:1")).rejects.toThrow("unbound PM");
		expect(fs.existsSync(f.files.journal)).toBe(false);
	});

	it.each(["fixed", "upper", "single", "total", "count"] as const)(
		"enforces the %s authorization limit",
		async (limit) => {
			const f = fixture(
				limit === "upper"
					? { expires_at: start + 12 * MIN }
					: limit === "total"
						? { max_total_extension_ms: 2 * MIN }
						: limit === "count"
							? { max_approvals: 1 }
							: {},
				limit === "fixed" ? start + 12 * MIN : Infinity,
			);
			f.report();
			const boundary =
				limit === "fixed" || limit === "upper" || limit === "total" ? start + 12 * MIN : start + 13 * MIN;
			const request = { ...f.request, deadline: boundary, reviewAt: start + 11 * MIN };
			await expect(f.approve({ ...request, deadline: boundary + 1 })).rejects.toThrow(
				"extension allowance exceeded",
			);
			await expect(f.approve(request)).resolves.toMatchObject({ deadline: boundary });
			if (limit === "count") {
				f.report(start + 11 * MIN, "New evidence");
				await expect(
					f.approve(
						{ ...f.request, requestId: "second", version: 1, deadline: start + 14 * MIN },
						() => start + 11 * MIN,
					),
				).rejects.toThrow("extension allowance exceeded");
			}
		},
	);

	it("gives the hard deadline precedence even if the approval began before it", async () => {
		const f = fixture();
		f.report();
		let samples = 0;
		await expect(
			f.approve(f.request, () => (++samples <= 2 ? start + 10 * MIN - 1 : start + 10 * MIN)),
		).rejects.toThrow("worker-deadline");
		expect(fs.existsSync(f.files.journal)).toBe(false);
		expect(f.view(start + 10 * MIN)).toMatchObject({ deadline: start + 10 * MIN, stop: "worker-deadline" });
		writeRunState(f.dir, { ...f.run, status: "failed", stop_kind: "worker-deadline" });
		await expect(f.approve()).rejects.toThrow("run no longer eligible");
	});

	it.each(["user-stop", "parent-cancel", "authority-revoked", "budget-exhausted"] as const)(
		"rechecks %s at the approval commit boundary",
		async (stop) => {
			const f = fixture();
			f.report();
			const controller = new AbortController();
			if (stop === "parent-cancel") {
				const dir = path.join(f.root, "demo", "workers", "parent");
				fs.mkdirSync(dir, { recursive: true });
				f.run.parent_worker_run = "parent@earlier";
				writeRunState(dir, {
					...f.run,
					run_id: "parent@earlier",
					task_key: "parent",
					parent_worker_run: undefined,
					status: "done",
				});
				writeRunState(f.dir, f.run);
			}
			let samples = 0;
			const now = () => {
				if (++samples === 3) {
					if (stop === "user-stop") controller.abort();
					if (stop === "authority-revoked") fs.unlinkSync(f.files.policy);
					if (stop === "budget-exhausted" && f.run.live_deadline) {
						f.run.live_deadline.usage.cost = f.policy.max_cost;
						writeRunState(f.dir, f.run);
					}
					if (stop === "parent-cancel") {
						const dir = path.join(f.root, "demo", "workers", "parent");
						writeRunState(dir, { ...readRunState(dir)!, status: "failed", aborted: true });
					}
				}
				return start + 9 * MIN;
			};
			await expect(f.approve(f.request, now, claim, controller.signal)).rejects.toThrow(stop);
			expect(fs.existsSync(f.files.journal)).toBe(false);
		},
	);

	it.each(["steps", "cost", "noProgress"] as const)(
		"retains the approval while the %s limit blocks further work",
		async (dimension) => {
			const f = fixture();
			f.report();
			await f.approve();
			const usage = f.run.live_deadline!.usage;
			usage[dimension] = dimension === "noProgress" ? f.policy.no_progress_limit : f.policy.max_steps;
			writeRunState(f.dir, f.run);
			expect(f.view(start + 11 * MIN)).toMatchObject({
				version: 1,
				deadline: start + 13 * MIN,
				stop: "budget-exhausted",
				budget: { [dimension]: 0 },
			});
			await expect(f.approve({ ...f.request, requestId: "further" })).rejects.toThrow("budget-exhausted");
		},
	);

	it("fails closed on corrupt or unpublishable journal records and inactive claims", async () => {
		const f = fixture();
		f.report();
		await f.approve();
		fs.writeFileSync(f.files.journal, "{");
		expect(f.view()).toMatchObject({ deadline: start + 10 * MIN, stop: "authority-revoked" });
		fs.unlinkSync(f.files.journal);
		let samples = 0;
		await expect(
			f.approve(f.request, () => {
				if (++samples === 4) fs.mkdirSync(f.files.journal);
				return start + 9 * MIN;
			}),
		).rejects.toThrow();
		fs.rmdirSync(f.files.journal);
		expect(f.view()).toMatchObject({ version: 0, deadline: start + 10 * MIN });
		fs.writeFileSync(path.join(f.root, "_index.parallel"), "| demo | active | EXECUTE | another:42 | | | now |\n");
		await expect(f.approve()).rejects.toThrow("authority-revoked");
	});
});

it("moves the wall timer and the wrap-up steer to the approved deadline without a tool call", async () => {
	vi.useFakeTimers();
	vi.setSystemTime(start);
	const f = fixture({ review_after_ms: 1000, max_run_ms: 6000, max_extension_ms: 3000, max_total_extension_ms: 3000 });
	fs.unlinkSync(path.join(f.dir, "run.json"));
	fs.writeFileSync(f.taskFile, fs.readFileSync(f.taskFile, "utf8").replace("timeout: 10", "timeout: 0.05"));
	vi.stubEnv("PI_WORKER_TASK", f.taskFile);
	const listeners = new Set(process.listeners("exit"));
	const previousExit = process.exitCode;
	const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
	const messages: string[] = [];
	const worker = {
		on() {},
		registerTool() {},
		sendUserMessage(message: string) {
			messages.push(message);
		},
	} as unknown as ExtensionAPI;
	try {
		await workerModeActivate(worker, { liveDeadlineHome: f.home });
		f.report(start);
		await vi.advanceTimersByTimeAsync(1500);
		await f.approve({ ...f.request, deadline: start + 6000, reviewAt: start + 5000 }, Date.now);
		await vi.advanceTimersByTimeAsync(1500);
		expect(exit).not.toHaveBeenCalled();
		expect(messages.filter((message) => message.startsWith("[mw deadline]"))).toHaveLength(0);
		await vi.advanceTimersByTimeAsync(2999);
		expect(exit).not.toHaveBeenCalled();
		expect(messages.filter((message) => message.startsWith("[mw deadline]"))).toHaveLength(1);
		await vi.advanceTimersByTimeAsync(1);
		expect(readRunState(f.dir)).toMatchObject({ status: "failed", stop_kind: "worker-deadline" });
		expect(exit).toHaveBeenCalledWith(1);
	} finally {
		for (const listener of process.listeners("exit")) if (!listeners.has(listener)) process.off("exit", listener);
		process.exitCode = previousExit;
	}
});

it.each(["worker-deadline", "budget-exhausted", "user-stop", "parent-cancel", "authority-revoked"] as const)(
	"enforces %s on a faux Worker after a normal PM tool approval",
	async (stop) => {
		vi.useFakeTimers({ toFake: ["Date"] });
		vi.setSystemTime(start);
		const f = fixture(stop === "budget-exhausted" ? { max_cost: 3 } : {});
		fs.unlinkSync(path.join(f.dir, "run.json"));
		fs.writeFileSync(path.join(f.dir, "report.md"), "AC-001 PASS");
		const parentDir = path.join(f.root, "demo", "workers", "parent");
		const parentRun = {
			...f.run,
			live_deadline: undefined,
			task_key: "parent",
			run_id: "parent@earlier",
			status: "done" as const,
		};
		if (stop === "parent-cancel") {
			fs.mkdirSync(parentDir, { recursive: true });
			writeRunState(parentDir, parentRun);
			fs.writeFileSync(f.taskFile, `parent_worker_run: ${parentRun.run_id}\n${fs.readFileSync(f.taskFile, "utf8")}`);
		}
		const listeners = new Set(process.listeners("exit"));
		const previousExit = process.exitCode;
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const kill = vi.spyOn(shell, "killTrackedDetachedChildren").mockImplementation(() => {});
		vi.stubEnv("PI_WORKER_TASK", f.taskFile);
		const entered = latch();
		const release = latch();
		const ran: number[] = [];
		const worker = await createHarness({
			extensionFactories: [
				async (pi) => {
					pi.registerTool({
						name: "read",
						label: "Read fixture",
						description: "Controlled Worker action",
						parameters: Type.Object({}),
						async execute() {
							ran.push(Date.now());
							if (ran.length === 1) {
								entered.release();
								await release.done;
							}
							return { content: [{ type: "text", text: "fixture result" }], details: {} };
						},
					});
					await workerModeActivate(pi, { liveDeadlineHome: f.home });
				},
			],
		});
		const pm = await createHarness({
			extensionFactories: [(pi) => registerWorkerDeadlineApproval(pi, f.root, () => claim, f.home)],
		});
		let prompting: Promise<void> | undefined;
		try {
			const runId = readRunState(f.dir)!.run_id;
			worker.setResponses([
				fauxAssistantMessage([fauxToolCall(WORKER_PROGRESS_TOOL, f.milestone)], { stopReason: "toolUse" }),
				fauxAssistantMessage([fauxToolCall("read", {})], { stopReason: "toolUse" }),
				fauxAssistantMessage([fauxToolCall("read", {})], { stopReason: "toolUse" }),
				() => {
					if (stop === "worker-deadline") vi.setSystemTime(start + 13 * MIN);
					return fauxAssistantMessage([fauxToolCall("read", {})], { stopReason: "toolUse" });
				},
				fauxAssistantMessage("Stopped"),
			]);
			prompting = worker.session.prompt("Report progress and finish the pending verification.");
			await entered.done;
			vi.setSystemTime(start + 9 * MIN);
			pm.setResponses([
				fauxAssistantMessage(
					[
						fauxToolCall("extend_worker_deadline", {
							key: "demo",
							task_key: "task",
							run_id: runId,
							request_id: f.request.requestId,
							version: 0,
							deadline_ms: f.request.deadline,
							review_at_ms: f.request.reviewAt,
							reason: f.request.reason,
							next: f.request.next,
						}),
					],
					{ stopReason: "toolUse" },
				),
				fauxAssistantMessage("Recorded the approval."),
			]);
			await pm.session.prompt("Review the Worker milestone and approve the bounded extension.");
			expect(pm.session.messages).toContainEqual(
				expect.objectContaining({
					role: "toolResult",
					toolName: "extend_worker_deadline",
					isError: false,
				}),
			);
			vi.setSystemTime(start + 10 * MIN + 1);
			if (stop === "user-stop") fs.writeFileSync(f.files.policy, JSON.stringify({ ...f.policy, cancelled: true }));
			if (stop === "parent-cancel") writeRunState(parentDir, { ...parentRun, aborted: true, status: "failed" });
			if (stop === "authority-revoked") fs.unlinkSync(f.files.policy);
			const stoppedInFlight = stop === "user-stop" || stop === "parent-cancel" || stop === "authority-revoked";
			if (stoppedInFlight) {
				await vi.waitFor(() => expect(readRunState(f.dir)?.stop_kind).toBe(stop), { timeout: 2000 });
			}
			release.release();
			await prompting;
			expect(ran).toEqual(stoppedInFlight ? [start] : [start, start + 10 * MIN + 1]);
			expect(readRunState(f.dir)).toMatchObject({ run_id: runId, status: "failed", stop_kind: stop });
			expect(exit).toHaveBeenCalledWith(1);
			expect(kill).toHaveBeenCalled();
		} finally {
			release.release();
			await prompting?.catch(() => {});
			worker.cleanup();
			pm.cleanup();
			for (const listener of process.listeners("exit")) if (!listeners.has(listener)) process.off("exit", listener);
			process.exitCode = previousExit;
		}
	},
	20_000,
);
