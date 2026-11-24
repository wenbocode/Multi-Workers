/**
 * Tests for the checkpoint wiring and role split (mw-worker-progress-persist
 * T-3, AC-001/002/003/004/007, design D-104/D-105/D-106/D-107).
 *
 * Covers:
 * - VC-001/VC-002 (integration): a read-only (`type: review`) worker past the
 *   checkpoint anchor writes exactly one `[machine]` line into its own
 *   `progress.md`, via the production `writeCheckpoint` closure + fake timers.
 * - VC-002 (unit): `appendProgressLine` is append-only (pre-seeded sentinel
 *   stays first, byte for byte).
 * - VC-003: a `type: coding` worker past the anchor writes no `[machine]` line.
 * - VC-004 (render layer): the writeless steer never carries the old "append to
 *   …progress.md" instruction and offers the narrow tool / reply alternative;
 *   the coding steer is byte-identical to the frozen pre-change baseline; both
 *   branches keep `deliverAs: "followUp"`.
 * - VC-007: `activeToolsForType` = `toolsForType` + `worker_file` for roles
 *   with no write tool only, per type including `rag-research`; the allowlist
 *   table matches the frozen 10-key snapshot; the final active set is asserted
 *   AFTER `before_agent_start` (the production recompute point).
 * - VC-005/VC-006 trace evidence through the REAL pi pipeline (createHarness +
 *   faux provider): `[TOOL] worker_file` for a legal call and `[TOOL_ERR]
 *   worker_file` for a rejection thrown by T-2's `execute`.
 *
 * The suite config is `silent: "passed-only"` and swallows console.log from
 * green tests, so `[VERIFY]` lines go straight to stdout via process.stdout.write.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { appendWriteFileEvent } from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import { hasDeliverableEvidence } from "../../src/extensions/agent-team-loop/shared/deliverable-evidence.ts";
import { MW_RUN_DETACHED_TOOL } from "../../src/extensions/agent-team-loop/shared/run-detached.ts";
import {
	PROGRESS_STALE_MS,
	RUN_PROGRESS_FILE,
	readRunProgress,
	recordRunProgress,
} from "../../src/extensions/agent-team-loop/shared/run-progress.ts";
import { readRunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { appendProgressLine } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import { WORKER_FILE_TOOL } from "../../src/extensions/agent-team-loop/worker/worker-file-tool.ts";
import {
	activeToolsForType,
	checkpointSteerText,
	resolveBudgetMs,
	toolsForType,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { WORKER_PROGRESS_TOOL } from "../../src/extensions/agent-team-loop/worker/worker-progress-tool.ts";
import { createHarness, type Harness } from "../suite/harness.ts";

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

const MACHINE_LINE_RE =
	/^CKPT \d+m \[machine\] ts=\S+ reads=\d+ writes=\d+ phases=(\d+\/\d+|-) repeat_top=\d+ risk=(low|mid|high)$/;

/** Frozen pre-change coding steer render (VC-004). The path is the only
 * interpolation the baseline leaves open; everything else is literal. */
const PROGRESS_SAMPLE = "D:/proj/.agenticdoc/key-a/workers/t/progress.md";
const CODING_STEER_BASELINE =
	"[mw checkpoint] 运行 1m（总预算 2m）。请立即自评收敛性，把一行追加到 " +
	PROGRESS_SAMPLE +
	"：CKPT 1m converging=yes|no eta≈<X>m <一句话理由>。若不收敛：立即收窄范围，优先保证已完成部分可交付，不要展开新工作。";

/** The frozen 2026-09-23 `TOOL_ALLOWLISTS` table (VC-007/VC-008 mirror of the
 * Python snapshot) — order-exact. */
const ALLOWLIST_SNAPSHOT: Record<string, string[]> = {
	coding: ["read", "write", "edit", "bash", "find", "grep", "ls"],
	review: ["read", "find", "grep", "ls"],
	research: ["read", "find", "grep", "ls", "bash"],
	"roadmap-writer": ["read", "write", "edit", "find", "grep", "ls"],
	"phase-writer": ["read", "write", "edit", "bash", "find", "grep", "ls"],
	verifier: ["read", "find", "grep", "ls"],
	reviewer: ["read", "find", "grep", "ls"],
	repair: ["read", "write", "edit", "bash", "find", "grep", "ls"],
	"rag-research": [
		"read",
		"find",
		"grep",
		"ls",
		"rag_search",
		"rag_symbol",
		"rag_graph",
		"rag_impact",
		"rag_sources",
		"rag_feedback",
		"rag_chat",
	],
	fallback: ["read", "write", "edit", "bash", "find", "grep", "ls"],
};

// worker-mode registers a process-exit hook per activation; this file
// activates many workers in one process, tripping Node's listener-leak
// heuristic. All hooks are intentional and harmless.
process.setMaxListeners(50);

const tmpRoots: string[] = [];
const harnesses: Harness[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "atl-ckpt-wiring-"));
	tmpRoots.push(dir);
	return dir;
}

afterEach(() => {
	vi.useRealTimers();
	while (harnesses.length > 0) {
		harnesses.pop()?.cleanup();
	}
	for (const dir of tmpRoots.splice(0)) {
		fs.rmSync(dir, { recursive: true, force: true });
	}
	delete process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_IDLE_MS;
});

// ── fake-timer worker driver (same shape as agent-team-loop.test.ts) ─────────

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	sent: Array<{ text: string; options?: { deliverAs?: string } }>;
	activeTools: () => string[] | undefined;
	registered: string[];
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => void>>();
	const sent: Array<{ text: string; options?: { deliverAs?: string } }> = [];
	const activeSets: string[][] = [];
	const registered: string[] = [];
	const pi = {
		on: (name: string, cb: (e: unknown) => void) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: (text: string, options?: { deliverAs?: string }) => {
			sent.push({ text, options });
		},
		setActiveTools: (names: string[]) => {
			activeSets.push([...names]);
		},
		registerTool: (tool: { name?: string }) => {
			if (tool.name) registered.push(tool.name);
		},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		sent,
		activeTools: () => activeSets.at(-1),
		registered,
	};
}

/** Activate the worker loop against root/{owner}/workers/{task}; idle threshold
 * is shortened to 60s via env so the interval logic is reachable in-test. */
async function startWorker(
	root: string,
	taskKey: string,
	body: string,
	owner = "key-a",
): Promise<{ worker: FakeWorker; taskDir: string }> {
	const taskDir = path.join(root, owner, "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), body, "utf8");
	process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
	process.env.PI_WORKER_IDLE_MS = "60000";
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return { worker, taskDir };
}

/** Advance to just past the anchor with a stream of activity events, so the
 * 60s idle watchdog never fires first (anchor for a 2m budget is 60s). */
function trickleToAnchor(worker: FakeWorker, steps = 5, stepMs = 15_000): void {
	for (let i = 0; i < steps; i++) {
		vi.advanceTimersByTime(stepMs);
		worker.emit("message_update");
	}
}

function progressOf(taskDir: string): string | undefined {
	const file = path.join(taskDir, "progress.md");
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : undefined;
}

function machineLines(content: string | undefined): string[] {
	if (content === undefined) return [];
	return content.split("\n").filter((line) => line.includes("[machine]"));
}

// ── VC-001 / VC-002 / VC-003: checkpoint machine line by role ────────────────

describe("checkpoint machine line by role (VC-001/002/003)", () => {
	it("VC-001/VC-002: type=review writes exactly one [machine] line at the anchor", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			vi.stubEnv("PI_WORKER_TIMEOUT_MS", "120000");
			const review = await startWorker(root, "t-review", "type: review\n\nreview\n");
			trickleToAnchor(review.worker);
			const content = progressOf(review.taskDir);
			const lines = (content ?? "").split("\n").filter((l) => l !== "");
			expect(content).toBeDefined();
			expect(machineLines(content)).toHaveLength(1);
			expect(machineLines(content)[0]).toMatch(MACHINE_LINE_RE);
			verify(`[VERIFY] VC-001: progress_exists=true machine_lines=${machineLines(content).length}`);
			verify(`[VERIFY] VC-002: machine_lines=1 sentinel_first=${lines[0] === machineLines(content)[0]}`);
			// VC-004 integration: the writeless branch delivers as followUp with the
			// alternative action, never the old write instruction.
			const steer = review.worker.sent.find((m) => m.text.includes("[mw checkpoint]"));
			expect(steer?.options?.deliverAs).toBe("followUp");
			expect(steer?.text ?? "").not.toMatch(/追加到.*progress\.md/);
			expect(steer?.text ?? "").toContain(WORKER_FILE_TOOL);
			expect(exitSpy).not.toHaveBeenCalled();
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});

	it("VC-003: type=coding writes no [machine] line at the same anchor", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			const coding = await startWorker(root, "t-coding", "type: coding\ntimeout: 2\n\nwork\n");
			trickleToAnchor(coding.worker);
			const codingContent = progressOf(coding.taskDir);
			expect(machineLines(codingContent)).toHaveLength(0);
			verify(`[VERIFY] VC-003: machine_lines=0`);
			// VC-004 integration: the coding branch is byte-identical to the frozen
			// baseline and keeps followUp (writeCheckpoint wiring).
			const steer = coding.worker.sent.find((m) => m.text.includes("[mw checkpoint]"));
			expect(steer?.options?.deliverAs).toBe("followUp");
			expect(steer?.text).toBe(
				checkpointSteerText({
					elapsedMs: 60_000,
					budgetMs: 120_000,
					progressPath: path.join(coding.taskDir, "progress.md"),
					hasWriteTools: true,
					narrowTool: WORKER_FILE_TOOL,
				}),
			);
			expect(exitSpy).not.toHaveBeenCalled();
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});

	it("VC-002: appendProgressLine is append-only — a pre-existing sentinel stays first byte for byte", () => {
		const root = mkdtemp();
		const taskKey = path.join("key-a", "workers", "t-sentinel");
		const file = path.join(root, taskKey, "progress.md");
		fs.mkdirSync(path.dirname(file), { recursive: true });
		const sentinel = "CKPT 20m converging=yes eta≈10m 只差最后一段证据";
		fs.writeFileSync(file, `${sentinel}\n`, "utf8");

		const appended = [
			"CKPT 30m [machine] ts=2026-09-23T00:00:00.000Z reads=4 writes=0 phases=- repeat_top=1 risk=mid",
			"CKPT 40m [machine] ts=2026-09-23T00:10:00.000Z reads=7 writes=0 phases=- repeat_top=0 risk=low",
			"CKPT 50m [machine] ts=2026-09-23T00:20:00.000Z reads=9 writes=0 phases=- repeat_top=2 risk=low",
		];
		for (const line of appended) appendProgressLine(taskKey, root, line);

		const lines = fs
			.readFileSync(file, "utf8")
			.split("\n")
			.filter((l) => l !== "");
		expect(lines[0]).toBe(sentinel);
		expect(lines).toEqual([sentinel, ...appended]);
		verify(
			`[VERIFY] VC-002: machine_lines=${machineLines(fs.readFileSync(file, "utf8")).length} sentinel_first=true`,
		);
	});
});

// ── VC-004: steer text role split (render layer) ────────────────────────────

describe("checkpoint steer role split (VC-004)", () => {
	it("VC-004: coding steer is byte-identical to the pre-change baseline", () => {
		const rendered = checkpointSteerText({
			elapsedMs: 60_000,
			budgetMs: 120_000,
			progressPath: PROGRESS_SAMPLE,
			hasWriteTools: true,
			narrowTool: "worker_file",
		});
		expect(rendered).toBe(CODING_STEER_BASELINE);
	});

	it("VC-004: writeless steer carries no 'append to …progress.md' instruction and offers the alternatives", () => {
		const rendered = checkpointSteerText({
			elapsedMs: 60_000,
			budgetMs: 120_000,
			progressPath: PROGRESS_SAMPLE,
			hasWriteTools: false,
			narrowTool: "worker_file",
		});
		expect(rendered).not.toMatch(/追加到.*progress\.md/);
		expect(rendered).toContain("worker_file");
		expect(rendered).toContain("converging=yes|no");
		// The machine evidence location is declared (framework-written).
		expect(rendered).toContain(PROGRESS_SAMPLE);
		verify(`[VERIFY] VC-004: writeless_write_instr=false coding_identical=true`);
	});
});

// ── VC-007: active set computation ──────────────────────────────────────────

/** Active-set derivation mirroring `activeToolsForType`: worker_file is
 * appended to writeless roles, and mw_run_detached is appended to roles whose
 * base carries `bash` (spawn surface; deliberately outside the frozen
 * TOOL_ALLOWLISTS table — see worker-mode.ts and commit 4980da301). */
function expectedActiveTools(base: string[]): string[] {
	let tools = [...base, WORKER_PROGRESS_TOOL];
	if (!base.includes("write")) tools.push(WORKER_FILE_TOOL);
	if (base.includes("bash")) tools = [...tools, MW_RUN_DETACHED_TOOL];
	return tools;
}

describe("activeToolsForType (VC-007)", () => {
	it("VC-007: table matches the frozen 10-key snapshot; worker_file is appended to writeless roles only", () => {
		for (const [taskType, expected] of Object.entries(ALLOWLIST_SNAPSHOT)) {
			expect(toolsForType(taskType), taskType).toEqual(expected);
			expect(activeToolsForType(taskType), taskType).toEqual(expectedActiveTools(expected));
		}
		// Unknown types resolve through the fallback bucket (which has write).
		expect(toolsForType("mystery-type")).toEqual(ALLOWLIST_SNAPSHOT.fallback);
		expect(activeToolsForType("mystery-type")).toEqual(expectedActiveTools(ALLOWLIST_SNAPSHOT.fallback));
		verify(
			`[VERIFY] VC-007: table_unchanged=true extra_only_writeless=true types=${Object.keys(ALLOWLIST_SNAPSHOT).length}`,
		);
	});

	it("VC-007: every registered type gets the expected final set AFTER before_agent_start", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const cases: Array<{ type: string; expected: string[] }> = Object.entries(ALLOWLIST_SNAPSHOT)
				.filter(([taskType]) => taskType !== "fallback")
				.map(([taskType, base]) => ({ type: taskType, expected: expectedActiveTools(base) }));
			for (const c of cases) {
				const taskKey = `t-${c.type}`;
				const { worker } = await startWorker(root, taskKey, `type: ${c.type}\n\nwork\n`);
				// Registration is structurally gated on the writeless role.
				const expectsNarrow = c.expected.includes(WORKER_FILE_TOOL);
				expect(worker.registered.includes(WORKER_FILE_TOOL), c.type).toBe(expectsNarrow);
				worker.emit("before_agent_start");
				expect(worker.activeTools(), c.type).toEqual(c.expected);
			}
			expect(exitSpy).not.toHaveBeenCalled();
		} finally {
			exitSpy.mockRestore();
		}
	});
});

// ── VC-005 / VC-006: trace evidence through the real pi pipeline ────────────

interface ToolResultLike {
	isError?: boolean;
	content: Array<{ type: string; text?: string }>;
}

/** Boot a real AgentSession whose only extension is worker-mode, anchored at a
 * temp task dir (type: review → worker_file registered + active). */
async function createWorkerHarness(
	root: string,
	taskKey: string,
	role = "review",
): Promise<{ harness: Harness; taskDir: string }> {
	const taskDir = path.join(root, "key-a", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), `type: ${role}\n\nreview\n`, "utf8");
	process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
	const harness = await createHarness({
		extensionFactories: [
			async (pi) => {
				await workerModeActivate(pi);
			},
		],
	});
	harnesses.push(harness);
	return { harness, taskDir };
}

function workerFileResults(harness: Harness): ToolResultLike[] {
	return harness.session.messages.filter(
		(message) => message.role === "toolResult" && message.toolName === WORKER_FILE_TOOL,
	) as unknown as ToolResultLike[];
}

function resultText(result: ToolResultLike): string {
	return result.content
		.filter((part): part is { type: "text"; text: string } => part.type === "text")
		.map((part) => part.text)
		.join("\n");
}

describe("run-scoped Worker progress", () => {
	it.each(["coding", "review"])("%s reports a milestone with evidence", async (role) => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		const { harness, taskDir } = await createWorkerHarness(root, "progress-case", role);
		const evidence = ".agenticdoc/key-a/workers/progress-case/report.md";
		fs.writeFileSync(path.join(taskDir, "report.md"), "AC-001 PASS");
		const milestone = {
			completed: [{ acceptance: "AC-001", evidence }],
			current: "Checking output",
			remaining: "AC-002",
			blocker: "",
			next: "Run verification",
		};
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall(WORKER_PROGRESS_TOOL, milestone)], { stopReason: "toolUse" }),
			fauxAssistantMessage(
				[
					fauxToolCall(WORKER_PROGRESS_TOOL, {
						...milestone,
						completed: [{ acceptance: "AC-002", evidence: "../outside.md" }],
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("Done"),
		]);
		await harness.session.prompt("Record progress");
		const runId = readRunState(taskDir)?.run_id ?? "";
		const snapshot = readRunProgress(taskDir, runId);
		expect(snapshot).toMatchObject({ status: "current", run_id: runId, milestone });
		expect(readRunProgress(taskDir, runId, Date.now() + PROGRESS_STALE_MS)).toMatchObject({ status: "stale" });
		expect(readRunProgress(taskDir, "different-run")).toEqual({ status: "other-run" });
		expect(
			harness.session.messages.flatMap((message) =>
				message.role === "toolResult" && message.toolName === WORKER_PROGRESS_TOOL ? [message.isError] : [],
			),
		).toEqual([false, true]);
	});

	it("reports in-flight activity separately and preserves it at the wall deadline", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			vi.stubEnv("PI_WORKER_TIMEOUT_MS", "60000");
			const { taskDir, worker } = await startWorker(root, "t-live", "type: review\n\nreview\n");
			const runId = readRunState(taskDir)?.run_id ?? "";
			worker.emit("tool_execution_start", { toolCallId: "held", toolName: "read", args: { path: "report.md" } });
			await vi.advanceTimersByTimeAsync(10_000);
			worker.emit("tool_execution_update", { toolCallId: "held" });
			expect(readRunProgress(taskDir, runId)).toMatchObject({
				status: "missing",
				activity: { source: "tool_update", tools: [{ name: "read" }] },
			});
			const milestone = {
				at: new Date().toISOString(),
				completed: [],
				current: "Reading report",
				remaining: "Validate AC-001",
				blocker: "",
				next: "Compare the report with the expected output",
			};
			expect(recordRunProgress(taskDir, runId, { milestone })).toBe(true);
			await vi.advanceTimersByTimeAsync(50_000);
			expect(readRunState(taskDir)).toMatchObject({ status: "failed", stop_kind: "worker-deadline", run_id: runId });
			expect(readRunProgress(taskDir, runId)).toMatchObject({ milestone, activity: { tools: [{ name: "read" }] } });
			expect(recordRunProgress(taskDir, runId, { milestone })).toBe(false);
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});
});

describe("explicit worker wall budgets", () => {
	it.each([
		["research", 10, 30],
		["research", 45, 45],
		["review", 10, 30],
		["coding", 10, 10],
	])("%s timeout %d minutes resolves to %d minutes", (role, card, expected) => {
		expect(resolveBudgetMs(card, "90000", role)).toBe(expected * 60_000);
	});
});

describe("worker_file trace evidence (VC-005/VC-006)", () => {
	it.each([
		["research", "检查完成。"],
		["review", "VERDICT=PASS"],
		["review", "详见 evidence/research/standalone-report.md"],
	])("%s settles from its complete evidence report with reply %s", async (role, reply) => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		const { harness, taskDir } = await createWorkerHarness(root, "t-evidence-delivery", role);
		const report = [
			"## 结论\n检查完成。",
			"## 证据\n本次检查记录。",
			"## 残留与未验证\n无。",
			"## 上下文来源\n任务卡。",
			"## 未覆盖面声明\n无。",
		].join("\n\n");
		const file = "evidence/research/standalone-report.md";
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall(WORKER_FILE_TOOL, { file, content: report, mode: "write" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage(reply),
		]);

		await harness.session.prompt("Write the findings to the evidence directory");

		const results = workerFileResults(harness);
		expect(
			results.map((result) => result.isError),
			results.map(resultText).join("\n"),
		).toEqual([false]);
		expect(readRunState(taskDir)).toMatchObject({ status: "done", exit: 0 });
		expect(fs.readFileSync(path.join(taskDir, "output.md"), "utf8")).toContain(`## Deliverables\n\n${file}`);
		expect(fs.readFileSync(path.join(root, "key-a", file), "utf8")).toBe(report);
	});

	it("keeps a complete local output ahead of an incomplete traced report", async () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		const { harness, taskDir } = await createWorkerHarness(root, "t-local-first", "research");
		const reply = [
			"## 结论\n检查完成。",
			"## 证据\n[VERIFY] 本次检查记录。",
			"## 残留与未验证\n无。",
			"## 上下文来源\n任务卡。",
		].join("\n\n");
		harness.setResponses([
			fauxAssistantMessage(
				[fauxToolCall(WORKER_FILE_TOOL, { file: "evidence/research/partial.md", content: "## 结论\n草稿。" })],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage(reply),
		]);

		await harness.session.prompt("Record the findings");

		expect(workerFileResults(harness).map((result) => result.isError)).toEqual([false]);
		expect(readRunState(taskDir)).toMatchObject({ status: "done", exit: 0 });
		expect(fs.readFileSync(path.join(taskDir, "output.md"), "utf8")).not.toContain("## Deliverables");
	});

	it("ignores trace evidence from a prior attempt and stale or escaping current targets", async () => {
		const root = path.join(mkdtemp(), ".agenticdoc");
		const { taskDir } = await startWorker(root, "t-trace-evidence-boundary", "type: review\n\nreview\n");
		const tracePath = path.join(taskDir, "trace.log");
		const currentTrace = fs.readFileSync(tracePath, "utf8");
		const evidence = path.join(root, "key-a", "evidence");
		const siblingEvidence = path.join(root, "other-key", "evidence");
		fs.mkdirSync(evidence, { recursive: true });
		fs.mkdirSync(siblingEvidence, { recursive: true });
		const fresh = path.join(evidence, "fresh.md");
		const stale = path.join(evidence, "stale.md");
		const outside = path.join(siblingEvidence, "outside.md");
		for (const file of [fresh, stale, outside]) fs.writeFileSync(file, "result");
		fs.utimesSync(stale, new Date(0), new Date(0));
		fs.writeFileSync(tracePath, `[START] pid=1\n[WRITE_FILE] path=${fresh}\n${currentTrace}`);
		const targets = [stale, evidence, outside];
		const junction = path.join(evidence, "outside");
		try {
			fs.symlinkSync(siblingEvidence, junction, process.platform === "win32" ? "junction" : "dir");
			targets.push(path.join(junction, "outside.md"));
		} catch (error) {
			if (process.platform !== "win32" || (error as NodeJS.ErrnoException).code !== "EPERM") throw error;
		}
		for (const target of targets) {
			appendWriteFileEvent(tracePath, target);
		}
		expect(hasDeliverableEvidence(taskDir)).toMatchObject({ delivered: false, channel: "none" });
		appendWriteFileEvent(tracePath, fresh);
		expect(hasDeliverableEvidence(taskDir)).toMatchObject({
			delivered: true,
			channel: "trace",
			detail: "evidence/fresh.md",
		});
		// Mixed canonical/alias spellings (e.g. Windows 8.3 short taskDir vs
		// realpathSync.native trace target) must resolve to the same evidence file.
		const canonicalFresh = fs.realpathSync.native(fresh);
		appendWriteFileEvent(tracePath, canonicalFresh);
		expect(hasDeliverableEvidence(taskDir)).toMatchObject({
			delivered: true,
			channel: "trace",
			detail: "evidence/fresh.md",
		});
	});

	it("VC-005: a legal call appends to progress.md and lands [TOOL] worker_file in trace.log", async () => {
		const root = mkdtemp();
		const { harness, taskDir } = await createWorkerHarness(root, "t-trace-ok");
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall(WORKER_FILE_TOOL, { file: "progress.md", content: "note 1\n" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("record progress");

		const results = workerFileResults(harness);
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(false);
		expect(fs.readFileSync(path.join(taskDir, "progress.md"), "utf8")).toBe("note 1\n");
		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		const toolLine = trace.split("\n").find((line) => line.includes("[TOOL]") && line.includes(WORKER_FILE_TOOL));
		expect(toolLine).toBeDefined();
		expect(toolLine).toContain("progress.md");
		verify(`[VERIFY] VC-005: append_ok=true report_ok=true tool_line=${toolLine !== undefined}`);
	});

	it("VC-006: a rejection thrown by execute lands [TOOL_ERR] worker_file and writes no file", async () => {
		const root = mkdtemp();
		const { harness, taskDir } = await createWorkerHarness(root, "t-trace-err");
		// Oversize content passes the schema (no maxLength) and fails T-2's
		// execute guard — the throw (not a returned error object) is what makes
		// tool_execution_end.isError true.
		const oversize = "a".repeat(64 * 1024 + 1);
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall(WORKER_FILE_TOOL, { file: "report-big.md", content: oversize })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
		]);

		await harness.session.prompt("write a report");

		const results = workerFileResults(harness);
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(true);
		expect(resultText(results[0] as ToolResultLike)).toContain("worker_file rejected");
		expect(fs.existsSync(path.join(taskDir, "report-big.md"))).toBe(false);
		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		const errLine = trace.split("\n").find((line) => line.includes("[TOOL_ERR]") && line.includes(WORKER_FILE_TOOL));
		expect(errLine).toBeDefined();
		expect(errLine).toContain("worker_file rejected");
		verify("[VERIFY] VC-006: rejections=1 new_files=0 tool_err_line=true");
	});

	it("VC-006: a schema-rejected file name also lands [TOOL_ERR] worker_file and writes nothing", async () => {
		const root = mkdtemp();
		const { harness, taskDir } = await createWorkerHarness(root, "t-trace-schema-err");
		// `task.md` fails the TypeBox `pattern` before `execute` runs. pi turns the
		// validation error into the tool result (agent-loop `prepareToolCall` catch →
		// `emitToolExecutionEnd` with `isError: true`), so the rejection is traceable
		// even though `worker_file`'s own guard is never reached. G1 of the
		// independent verification (2026-09-23) asked for exactly this case: the
		// oversize path above only exercises `execute`'s throw.
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall(WORKER_FILE_TOOL, { file: "task.md", content: "x" })], {
				stopReason: "toolUse",
			}),
			fauxAssistantMessage("done"),
		]);
		const before = fs.readdirSync(taskDir).sort();

		await harness.session.prompt("clobber the task file");

		const results = workerFileResults(harness);
		expect(results).toHaveLength(1);
		expect(results[0]?.isError).toBe(true);
		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		const errLine = trace.split("\n").find((line) => line.includes("[TOOL_ERR]") && line.includes(WORKER_FILE_TOOL));
		expect(errLine).toBeDefined();
		// The rejection writes nothing: task.md is byte-identical and no
		// progress/report file appeared. (output.md is written by worker-mode on
		// agent_end, so the raw directory set is not compared.)
		expect(fs.readFileSync(path.join(taskDir, "task.md"), "utf8")).toBe("type: review\n\nreview\n");
		const after = fs.readdirSync(taskDir).sort();
		expect(after.filter((name) => name !== "output.md" && name !== RUN_PROGRESS_FILE)).toEqual(before);
		verify("[VERIFY] VC-006: schema_rejection_ok=true tool_err_line=true");
	});
});
