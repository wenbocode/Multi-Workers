/**
 * worker-model-error-perception.test.ts — T-05 (mw-model-error-perception,
 * AC-001/003/004/005/006/007; spec §3, design §3.1/§3.4/§5).
 *
 * The process-level revision (design D3, 2026-10-15) makes the worker process
 * the retry unit: the FIRST error settle ends this process with exit 3, and the
 * launcher owns same-model retries plus the fallback chain. These tests pin the
 * worker-side half of that contract:
 *
 * - pipeline level (createHarness + faux provider, the
 *   `agent-team-loop-checkpoint-wiring.test.ts` precedent): an all-error run
 *   exits 3 with `[MODEL_ERR]`, `run.json.model_exhausted:true`, a
 *   `model unavailable:` Exit Reason and its intermediate products; an error
 *   followed by a success (in-run auto-retry) settles done (AC-005); the
 *   launcher-seeded `PI_WORKER_TRIED_MODELS` chain is rendered while
 *   `PI_WORKER_MODEL_ERR_MAX` (launcher budget) is not consumed.
 * - timing level (fakePi + fake timers, the `worker-idle-heartbeat.test.ts`
 *   precedent): a no-in-flight hang whose last boundary was an error is
 *   reclassified as model exhaustion (exit 3 + `last_model_error=yes`), while a
 *   genuinely hung tool keeps the exit-1 path and a successful boundary keeps
 *   feeding the activity clock.
 * - PM perception (AC-006): K consecutive model-error terminals under one key
 *   record one notice alarm; any other terminal clears the streak.
 *
 * Offline by contract (AGENTS.md): faux provider only, no network, no keys.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	bumpModelErrorStreak,
	describeDispatchAlarm,
	formatDispatchAlarm,
	isModelErrorTerminal,
	isNoticeDispatchAlarm,
	MODEL_ERROR_STREAK_K,
	MODEL_UNAVAILABLE_PREFIX,
	recordModelErrorTerminal,
	runModelExhausted,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	formatModelUnavailableReason,
	MODEL_ERR_TEXT_MAX,
	parseTriedModels,
	resolveToolIdleMs,
	truncateModelErrText,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness, type Harness } from "./harness.ts";

// Each activation registers a process-exit hook; this file activates several
// workers in one process, tripping Node's listener-leak heuristic.
process.setMaxListeners(50);

const IDLE_MS = 60_000;
/** 2h wall budget: the wall must not win before the 30m tool-idle bound. */
const WALL_MS = 2 * 60 * 60_000;
const TOOL_IDLE_MS = resolveToolIdleMs(IDLE_MS);
const FAUX_MODEL_LABEL = "faux/faux-1";

const tmpRoots: string[] = [];
const harnesses: Harness[] = [];
const savedEnv = new Map<string, string | undefined>();

function setEnv(name: string, value: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	process.env[name] = value;
}

function clearEnv(name: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	delete process.env[name];
}

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpRoots.push(dir);
	return dir;
}

afterEach(() => {
	while (harnesses.length > 0) {
		harnesses.pop()?.cleanup();
	}
	for (const dir of tmpRoots.splice(0)) {
		fs.rmSync(dir, { recursive: true, force: true });
	}
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
	vi.restoreAllMocks();
	vi.useRealTimers();
});

// ── shared readers/writers ────────────────────────────────────────────────────

/** Body of the LAST `## <title>` block of a markdown product. */
function sectionBody(markdown: string, title: string): string | undefined {
	const re = new RegExp(`(?:^|\\n)##\\s+${title}\\s*\\n+([\\s\\S]*?)(?=\\n##\\s|$)`);
	return re.exec(markdown)?.[1]?.trim();
}

function readRunJson(taskDir: string): Record<string, unknown> {
	return JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8")) as Record<string, unknown>;
}

function readOutput(taskDir: string): string {
	return fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
}

function readTrace(taskDir: string): string {
	return fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
}

function traceLinesContaining(trace: string, needle: string): string[] {
	return trace.split(/\r?\n/).filter((line) => line.includes(needle));
}

function idleKillLine(taskDir: string): string | undefined {
	return readTrace(taskDir)
		.split(/\r?\n/)
		.find((line) => line.startsWith("[IDLE_KILL]"));
}

/** All-error faux script tall enough to exhaust the in-run auto-retry budget
 * (`maxRetries: 3` → initial call + 3 retries), so the LAST error text is the
 * scripted one rather than faux's "No more faux responses queued". */
function allErrorSteps(count = 4, errorMessage = "HTTP 500"): ReturnType<typeof fauxAssistantMessage>[] {
	return Array.from({ length: count }, () =>
		fauxAssistantMessage("partial step done", { stopReason: "error", errorMessage }),
	);
}

// ── pipeline-level driver (createHarness + faux worker-mode) ─────────────────

/** Boot a real AgentSession whose only extension is worker-mode, anchored at
 * root/key-a/workers/<taskKey>. The watchdog env is pushed out of reach; the
 * retry budget is 1ms so the auto-retry chain stays fast on real timers. */
async function startPipelineWorker(
	root: string,
	taskKey: string,
	body = "type: coding\n\nwork\n",
): Promise<{ harness: Harness; taskDir: string }> {
	const taskDir = path.join(root, "key-a", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), body, "utf8");
	setEnv("PI_WORKER_TASK", path.join(taskDir, "task.md"));
	setEnv("PI_WORKER_IDLE_MS", String(10 * 60_000));
	setEnv("PI_WORKER_TIMEOUT_MS", String(60 * 60_000));
	const harness = await createHarness({
		settings: { retry: { enabled: true, maxRetries: 3, baseDelayMs: 1 } },
		extensionFactories: [
			async (pi) => {
				await workerModeActivate(pi);
			},
		],
	});
	harnesses.push(harness);
	// session_start is what captures the live model label (worker-mode has no
	// model getter); without it the `[MODEL]`/tried-chain half stays empty.
	await harness.session.bindExtensions({});
	return { harness, taskDir };
}

describe("model-error settle (AC-001/003/004)", () => {
	it("exits 3 on the first error settle: [MODEL_ERR], run.json model_exhausted, model unavailable reason, intermediate products", async () => {
		const root = mkdtemp("mw-mep-pipeline-");
		clearEnv("PI_WORKER_TRIED_MODELS");
		const { harness, taskDir } = await startPipelineWorker(root, "t-all-error");
		// An already-produced intermediate product: the breaker must preserve it.
		fs.writeFileSync(path.join(taskDir, "phase-1.md"), "# phase 1\ndone\n", "utf8");
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		harness.setResponses(allErrorSteps());

		await harness.session.prompt("do the work");

		// AC-001/D6: the process-level retry unit ends here.
		expect(exitSpy).toHaveBeenCalledWith(3);
		// AC-003 reverse assertion: a writeless-phase-less all-error write role
		// must never take the exit-0/done path.
		expect(exitSpy).not.toHaveBeenCalledWith(0);

		// AC-002: exactly one [MODEL_ERR] line, written through appendTrace so it
		// lands as `[FLOW] <iso> [MODEL_ERR] …` (prefix must NOT be anchored).
		const errLines = traceLinesContaining(readTrace(taskDir), "[MODEL_ERR]");
		expect(errLines).toHaveLength(1);
		expect(errLines[0]).toContain(`model=${FAUX_MODEL_LABEL}`);
		expect(errLines[0]).toContain("run=1");
		expect(errLines[0]).toContain("err=HTTP 500");

		// AC-004/design §4: machine-readable terminal record.
		const run = readRunJson(taskDir);
		expect(run.model_exhausted).toBe(true);
		expect(run.status).toBe("failed");
		expect(run.exit).toBe(3);

		// AC-004: Exit Reason opens with the stable prefix and carries the chain.
		const output = readOutput(taskDir);
		const reason = sectionBody(output, "Exit Reason");
		expect(reason).toBeDefined();
		expect(reason?.startsWith(MODEL_UNAVAILABLE_PREFIX)).toBe(true);
		expect(reason).toContain(`tried=${FAUX_MODEL_LABEL}(1)`);
		expect(reason).toContain("last=HTTP 500");

		// AC-010: intermediate products survive — the last assistant text and the
		// collected deliverables are both present on the exit-3 product.
		expect(sectionBody(output, "Summary")).toContain("partial step done");
		expect(sectionBody(output, "Summary")).toContain("phases=-");
		expect(sectionBody(output, "Deliverables")).toContain("phase-1.md");
		// AC-003: no success-shaped sections leaked into the model-error product.
		expect(output).not.toContain("## Verification Steps");
		expect(reason).not.toContain("Agent settled");
	});

	it("renders the launcher-seeded TRIED chain and ignores PI_WORKER_MODEL_ERR_MAX / PI_WORKER_FALLBACK_INDEX", async () => {
		const root = mkdtemp("mw-mep-envchain-");
		// `PI_WORKER_MODEL_ERR_MAX=0` means "disable the breaker" for the launcher
		// budget — if the worker still consumed it, this run would NOT exit 3.
		setEnv("PI_WORKER_MODEL_ERR_MAX", "0");
		setEnv("PI_WORKER_FALLBACK_INDEX", "3");
		setEnv("PI_WORKER_TRIED_MODELS", "anthropic/claude-3,openai/gpt-4");
		const { harness, taskDir } = await startPipelineWorker(root, "t-envchain");
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		harness.setResponses(allErrorSteps());

		await harness.session.prompt("do the work");

		expect(exitSpy).toHaveBeenCalledWith(3);
		const reason = sectionBody(readOutput(taskDir), "Exit Reason") ?? "";
		expect(reason.startsWith(MODEL_UNAVAILABLE_PREFIX)).toBe(true);
		// The launcher chain is rendered in order and the live model joins last.
		expect(reason).toContain(`tried=anthropic/claude-3(1),openai/gpt-4(1),${FAUX_MODEL_LABEL}(1)`);
		expect(reason).toContain("last=HTTP 500");
	});
});

describe("in-run auto-retry recovery (AC-005)", () => {
	it("settles done without exit 3 when an error is followed by a success", async () => {
		const root = mkdtemp("mw-mep-jitter-");
		clearEnv("PI_WORKER_TRIED_MODELS");
		const { harness, taskDir } = await startPipelineWorker(root, "t-jitter");
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		harness.setResponses([
			fauxAssistantMessage("", { stopReason: "error", errorMessage: "overloaded_error" }),
			fauxAssistantMessage("recovered"),
		]);

		await harness.session.prompt("do the work");

		// The run-internal retry (not the cross-process launcher retry) recovered.
		expect(harness.eventsOfType("agent_end").map((event) => event.willRetry)).toEqual([true, false]);
		expect(exitSpy).not.toHaveBeenCalledWith(3);
		expect(traceLinesContaining(readTrace(taskDir), "[MODEL_ERR]")).toHaveLength(0);

		const run = readRunJson(taskDir);
		expect(run.status).toBe("done");
		expect(run.model_exhausted).toBeUndefined();
		const reason = sectionBody(readOutput(taskDir), "Exit Reason") ?? "";
		expect(reason.startsWith(MODEL_UNAVAILABLE_PREFIX)).toBe(false);
		expect(reason).toContain("Agent settled");
	});
});

// ── timing-level driver (fakePi + fake timers, worker-idle-heartbeat shape) ──

class FakeWorkerPi {
	readonly handlers = new Map<string, Array<(event: unknown) => void>>();
	readonly sent: Array<{ text: string; options?: { deliverAs?: string } }> = [];

	on(name: string, cb: (event: unknown) => void): void {
		const list = this.handlers.get(name) ?? [];
		list.push(cb);
		this.handlers.set(name, list);
	}

	sendUserMessage(text: string, options?: { deliverAs?: string }): void {
		this.sent.push({ text, options });
	}

	registerTool(_tool: { name?: string }): void {}

	setActiveTools(_names: string[]): void {}

	emit(name: string, payload?: unknown): void {
		for (const cb of this.handlers.get(name) ?? []) cb(payload);
	}
}

function makeTimingTask(root: string, taskKey: string): string {
	const taskDir = path.join(root, "key-a", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
	setEnv("PI_WORKER_TASK", path.join(taskDir, "task.md"));
	setEnv("PI_WORKER_IDLE_MS", String(IDLE_MS));
	setEnv("PI_WORKER_TIMEOUT_MS", String(WALL_MS));
	return taskDir;
}

/** One `agent_end`-shaped payload whose last assistant message is `stopReason`. */
function assistantBoundary(stopReason: "stop" | "error", text = ""): unknown {
	return {
		messages: [
			{
				role: "assistant",
				content: text === "" ? [] : [{ type: "text", text }],
				stopReason,
				...(stopReason === "error" ? { errorMessage: "HTTP 500" } : {}),
			},
		],
	};
}

describe("idle-hang reclassification (design D4)", () => {
	it("no in-flight tool + a last model error is a model verdict: exit 3, run.json model_exhausted, last_model_error=yes", async () => {
		vi.useFakeTimers();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		const root = mkdtemp("mw-mep-idle-");
		const taskDir = makeTimingTask(root, "t-hang");
		const pi = new FakeWorkerPi();
		await workerModeActivate(pi as unknown as ExtensionAPI);

		// A successful boundary disqualifies the D4-patch "first call never
		// returned" reading, so `lastErrorInfo !== undefined` is the ONLY trigger
		// left for the reclassification under test.
		pi.emit("agent_start");
		pi.emit("agent_end", assistantBoundary("stop", "warm"));
		pi.emit("agent_end", assistantBoundary("error"));

		vi.advanceTimersByTime(IDLE_MS);

		expect(exitSpy).toHaveBeenCalledWith(3);
		const kill = idleKillLine(taskDir);
		expect(kill).toBeDefined();
		expect(kill).toContain("last_model_error=yes");
		expect(kill).toContain("threshold_kind=idle");
		expect(kill).toContain("tool_in_flight=none");

		const run = readRunJson(taskDir);
		expect(run.model_exhausted).toBe(true);
		expect(run.status).toBe("failed");
		const reason = sectionBody(readOutput(taskDir), "Exit Reason") ?? "";
		expect(reason.startsWith(MODEL_UNAVAILABLE_PREFIX)).toBe(true);
	});

	it("a genuinely hung in-flight tool keeps the exit-1 path even after an error boundary", async () => {
		vi.useFakeTimers();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		const root = mkdtemp("mw-mep-hung-tool-");
		const taskDir = makeTimingTask(root, "t-hung-tool");
		const pi = new FakeWorkerPi();
		await workerModeActivate(pi as unknown as ExtensionAPI);

		pi.emit("agent_start");
		pi.emit("agent_end", assistantBoundary("error"));
		pi.emit("tool_execution_start", {
			type: "tool_execution_start",
			toolCallId: "call-hung",
			toolName: "bash",
			args: { command: "hung" },
		});

		vi.advanceTimersByTime(TOOL_IDLE_MS + 30_000);

		// A hung tool is a tool hang, not a model-availability verdict.
		expect(exitSpy).toHaveBeenCalledWith(1);
		expect(exitSpy).not.toHaveBeenCalledWith(3);
		const kill = idleKillLine(taskDir);
		expect(kill).toContain("tool_in_flight=bash");
		expect(kill).toContain("threshold_kind=tool_idle");
		// The error fact is still recorded, it just does not convert the verdict.
		expect(kill).toContain("last_model_error=yes");
		const run = readRunJson(taskDir);
		expect(run.model_exhausted).toBeUndefined();
	});

	it("a successful boundary still feeds the activity clock (worker-idle-heartbeat regression)", async () => {
		vi.useFakeTimers();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		const root = mkdtemp("mw-mep-success-clock-");
		const taskDir = makeTimingTask(root, "t-success-clock");
		const pi = new FakeWorkerPi();
		await workerModeActivate(pi as unknown as ExtensionAPI);

		pi.emit("agent_start");
		// t=30s: 30s of silence is below the 60s idle threshold.
		vi.advanceTimersByTime(30_000);
		expect(exitSpy).not.toHaveBeenCalled();
		// The success boundary resets the clock; without the touch the t=60s tick
		// (60s idle) would have killed the worker.
		pi.emit("agent_end", assistantBoundary("stop", "ok"));
		vi.advanceTimersByTime(30_000);
		expect(exitSpy).not.toHaveBeenCalled();
		expect(readTrace(taskDir)).not.toContain("[IDLE_KILL]");
	});
});

// ── PM model-error perception (AC-006, design D7) ────────────────────────────

function writeRunJson(dir: string, state: Record<string, unknown>): void {
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(path.join(dir, "run.json"), `${JSON.stringify(state, null, 2)}\n`, "utf8");
}

function writeModelExhaustedRun(dir: string): void {
	writeRunJson(dir, { status: "failed", exit: 3, model_exhausted: true });
}

function alarmRows(root: string): Array<Record<string, unknown>> {
	const ledger = path.join(root, "_autopilot", "auto-decisions.jsonl");
	if (!fs.existsSync(ledger)) return [];
	return fs
		.readFileSync(ledger, "utf8")
		.split(/\r?\n/)
		.filter((line) => line.trim() !== "")
		.map((line) => JSON.parse(line) as Record<string, unknown>);
}

describe("PM model-error perception (AC-006)", () => {
	it("records one notice alarm once K consecutive model-error terminals land, and a clean terminal clears the streak", () => {
		const root = mkdtemp("mw-mep-pm-");
		const errDir1 = path.join(root, "key-a", "workers", "t1");
		const errDir2 = path.join(root, "key-a", "workers", "t2");
		const cleanDir = path.join(root, "key-a", "workers", "t3");
		writeModelExhaustedRun(errDir1);
		writeModelExhaustedRun(errDir2);
		writeRunJson(cleanDir, { status: "done" });

		const streaks = new Map<string, number>();
		expect(recordModelErrorTerminal(root, "key-a", "t1", errDir1, streaks)).toBe(1);
		expect(alarmRows(root)).toHaveLength(0);

		expect(recordModelErrorTerminal(root, "key-a", "t2", errDir2, streaks)).toBe(MODEL_ERROR_STREAK_K);
		const rows = alarmRows(root);
		expect(rows).toHaveLength(1);
		expect(rows[0]).toMatchObject({ phase: "dispatch-alarm", kind: "model-error", count: 2, detail: "t2" });

		// Any non-model-error terminal resets the run of failures...
		expect(recordModelErrorTerminal(root, "key-a", "t3", cleanDir, streaks)).toBe(0);
		expect(streaks.size).toBe(0);
		// ...so a later model-error terminal starts the count over (no new alarm).
		expect(recordModelErrorTerminal(root, "key-a", "t1", errDir1, streaks)).toBe(1);
		expect(alarmRows(root)).toHaveLength(1);
	});

	it("reads model-error evidence from run.json.model_exhausted or the Exit Reason prefix, never throwing on bad records", () => {
		const root = mkdtemp("mw-mep-detect-");
		const viaRun = path.join(root, "key-a", "workers", "t-run");
		writeModelExhaustedRun(viaRun);
		expect(runModelExhausted(viaRun)).toBe(true);
		expect(isModelErrorTerminal(viaRun)).toBe(true);

		const viaOutput = path.join(root, "key-a", "workers", "t-output");
		fs.mkdirSync(viaOutput, { recursive: true });
		fs.writeFileSync(
			path.join(viaOutput, "output.md"),
			"## Exit Reason\n\nmodel unavailable: tried=a/b(1) last=HTTP 500\n",
			"utf8",
		);
		expect(runModelExhausted(viaOutput)).toBe(false);
		expect(isModelErrorTerminal(viaOutput)).toBe(true);

		const clean = path.join(root, "key-a", "workers", "t-clean");
		writeRunJson(clean, { status: "done" });
		expect(isModelErrorTerminal(clean)).toBe(false);

		const malformed = path.join(root, "key-a", "workers", "t-malformed");
		fs.mkdirSync(malformed, { recursive: true });
		fs.writeFileSync(path.join(malformed, "run.json"), "{ not json", "utf8");
		expect(runModelExhausted(malformed)).toBe(false);
		expect(isModelErrorTerminal(malformed)).toBe(false);

		// A missing task dir degrades to false, never an exception.
		expect(isModelErrorTerminal(path.join(root, "key-a", "workers", "absent"))).toBe(false);
	});

	it("bumpModelErrorStreak counts consecutive hits and deletes the key on a clean terminal", () => {
		const streaks = new Map<string, number>();
		expect(bumpModelErrorStreak(streaks, "key-a", true)).toBe(1);
		expect(bumpModelErrorStreak(streaks, "key-a", true)).toBe(2);
		expect(bumpModelErrorStreak(streaks, "key-b", true)).toBe(1);
		expect(bumpModelErrorStreak(streaks, "key-a", false)).toBe(0);
		expect(streaks.has("key-a")).toBe(false);
		expect(streaks.get("key-b")).toBe(1);
	});

	it("renders the model-error alarm as a notice, not a refusal", () => {
		expect(isNoticeDispatchAlarm("model-error")).toBe(true);
		const alarm = { kind: "model-error" as const, count: 2, detail: "t2" };
		const text = formatDispatchAlarm(alarm);
		expect(text).toContain("提示");
		expect(text).not.toContain("已拒绝");
		expect(describeDispatchAlarm(alarm)).toContain("model-unavailable");
		expect(describeDispatchAlarm(alarm)).toContain("t2");
	});
});

// ── pure helpers of the model-error protocol (design §4) ─────────────────────

describe("model-error protocol helpers", () => {
	it("parseTriedModels: csv -> ordered, trimmed, deduped chain", () => {
		expect(parseTriedModels("a/b, c/d ,a/b,,")).toEqual(["a/b", "c/d"]);
		expect(parseTriedModels("")).toEqual([]);
		expect(parseTriedModels(undefined)).toEqual([]);
	});

	it("truncateModelErrText collapses to one line and caps at MODEL_ERR_TEXT_MAX", () => {
		expect(truncateModelErrText("HTTP 500\n  overloaded")).toBe("HTTP 500 overloaded");
		const long = "x".repeat(MODEL_ERR_TEXT_MAX + 50);
		const truncated = truncateModelErrText(long);
		expect(truncated.length).toBe(MODEL_ERR_TEXT_MAX);
		expect(truncated.endsWith("…")).toBe(true);
	});

	it("formatModelUnavailableReason renders tried=<model>(<runs>),… last=<err>", () => {
		const reason = formatModelUnavailableReason(
			[
				{ model: "a/b", runs: 1 },
				{ model: "c/d", runs: 2 },
			],
			"HTTP 500",
		);
		expect(reason).toBe("model unavailable: tried=a/b(1),c/d(2) last=HTTP 500");
		expect(formatModelUnavailableReason([], "boom")).toBe("model unavailable: tried=- last=boom");
		expect(formatModelUnavailableReason([], "boom").startsWith(MODEL_UNAVAILABLE_PREFIX)).toBe(true);
	});
});
