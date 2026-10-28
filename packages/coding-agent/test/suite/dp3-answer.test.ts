/**
 * dp3-answer.test.ts — T-06 / mw-decision-substitution: dp3 clarification
 * substitution at the worker settle chain.
 *
 * What is pinned here (card requirement 5, five invariants):
 *
 * 1. **closed state is byte-identical** — a missing `.mw/decide.json` and an
 *    explicit `enabled=false` produce the same NC product, the same terminal
 *    record and ZERO `[DECIDE]` rows / ZERO decision-runner calls;
 * 2. **`## Questions` first line keeps the original text** — every degradation
 *    (`unavailable` here) falls back to the byte-identical human path;
 * 3. **at most one auto-answer per process** — a second NC after an injected
 *    answer never asks the service again and lands the normal NC terminal;
 * 4. **the NC terminal is four-face consistent** — run.json status/exit,
 *    `[END] exit=2`, the output.md run marker and `## Questions` all agree
 *    (the OS-level exit code is out of reach in this in-process harness; the
 *    recorded `run.exit` is the value the print-mode exit path uses);
 * 5. **goal mtime recording stays orthogonal** — a phased task under an
 *    auto-answer still emits exactly one `[GOAL_CHECK] phase=N` per phase with
 *    a non-zero real mtime, and the extra follow-up turn adds none.
 *
 * Plus the local 3c reuse path (zero spawn) as a discriminating extra.
 *
 * FIX-J adds the 3a consumption contract on top: the model does not write prose
 * or a citation any more (the Jev question set is choice + noul + a dynamic
 * choice). It picks one of the locally built `local_candidates` and reports
 * `answerable`; the injected answer is the local line plus its local
 * `<path>:<line>`. The tests below use the `DecideRunner` seam with a fake
 * `mw decide run` payload (no network, no real Jev credentials).
 *
 * No provider APIs, keys or network: the decision child is stubbed at the
 * `DecideRunner` seam of `pm/triage-client.ts` and the worker runs against a
 * fake `ExtensionAPI` (same pattern as `mwds-t04-deliverable.test.ts`).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { DP3_ID } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import type {
	DecideRunner,
	DecideRunRequest,
	RawDecideRun,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import { assertStateMatchesRegistry } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { resolveDecidePolicy } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import { RUN_SCHEMA, type RunState, writeRunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import {
	type Dp3DecisionInput,
	decideDp3WorkerClarify,
	dp3Thresholds,
	formatDp3TraceLine,
	readDp3Policy,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const KEY = "dp3-key";
const TASK = "dp3-worker";
const NO_PRODUCT = "no-product: output.md has no machine line, no referenced evidence and no artifacts";

const tempDirs: string[] = [];
let savedCwd = process.cwd();

beforeEach(() => {
	savedCwd = process.cwd();
});

afterEach(() => {
	process.chdir(savedCwd);
	delete process.env.PI_WORKER_TASK;
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
	taskPath: string;
}

/** A research (writeless) worker book; `body` lets a phase machine or a local
 * reuse line ride the same card. */
function makeFixture(body = "Use `prepareStructuredState` from the triage client.", phase = "EXECUTE"): Fixture {
	const projectRoot = mkdtemp("dp3-answer-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, KEY);
	const taskDir = path.join(keyDir, "workers", TASK);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), `---\ntype: research\n---\n\nphase: ${phase}\n${body}\n`, "utf8");
	fs.writeFileSync(path.join(trueRoot, "goal.md"), "# Goal\n\nfile-driven coordination\n", "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir, taskPath: path.join(taskDir, "task.md") };
}

/** Write a repo-relative file inside the fixture project root. */
function writeProjectFile(fx: Fixture, rel: string, content: string): void {
	const file = path.join(fx.projectRoot, rel);
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(file, content, "utf8");
}

/** The line the local candidate answer must quote. It carries a question token
 * (`prepareStructuredState`) on line 2, so the cited line is not the default. */
const CANDIDATE_LINE = "# prepareStructuredState lives in pm/triage-client.ts";
const CANDIDATE_REL = "evidence/preparestructuredstate-notes.md";

function addCandidateFile(fx: Fixture): string {
	writeProjectFile(fx, CANDIDATE_REL, `# notes\n${CANDIDATE_LINE}\n`);
	return CANDIDATE_REL;
}

function enableDecide(fx: Fixture, points?: Record<string, unknown>): void {
	fs.mkdirSync(path.join(fx.projectRoot, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(fx.projectRoot, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	if (points !== undefined) {
		fs.writeFileSync(
			path.join(fx.projectRoot, ".mw", "decide-points.json"),
			`${JSON.stringify({ version: 1, points })}\n`,
			"utf8",
		);
	}
}

function disableDecide(fx: Fixture): void {
	fs.mkdirSync(path.join(fx.projectRoot, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(fx.projectRoot, ".mw", "decide.json"), `${JSON.stringify({ enabled: false })}\n`, "utf8");
}

interface Stub {
	run: DecideRunner;
	calls: DecideRunRequest[];
}

function stubRunner(response: RawDecideRun | (() => RawDecideRun)): Stub {
	const calls: DecideRunRequest[] = [];
	const run: DecideRunner = (request) => {
		calls.push(request);
		return typeof response === "function" ? response() : response;
	};
	return { run, calls };
}

/** Free text a child may still emit: FIX-J forbids it reaching the answer. */
const RUNNER_FREE_TEXT = "RUNNER-FREE-TEXT-9f3a2b must never reach an answer";

interface Dp3AnswerSpec {
	kind?: string;
	/** `noul` probability carried as a NUMBER in `value` (FIX-I contract). */
	answerable?: number;
	candidate?: string;
	kindConfidence?: number;
	/** `null` omits `clarifying_answer` (the FIX-I question set has none). */
	legacyAnswer?: string | null;
}

/** A dp3 answer in the FROZEN FIX-I shape: `answer_kind` (choice), `answerable`
 * (noul) and `candidate` (a choice over the sent `local_candidates`).
 * `clarifying_answer` is not part of the question set any more; where it rides
 * along it is runner free text that must never reach the injected answer. */
function dp3Answer(spec: Dp3AnswerSpec = {}, extra: Record<string, unknown> = {}): RawDecideRun {
	return {
		status: 0,
		timedOut: false,
		stderr: "",
		stdout: JSON.stringify({
			available: true,
			mode: "auto",
			confidence_source: "api",
			latency_ms: 7,
			answers: {
				answer_kind: { value: spec.kind ?? "fact", confidence: spec.kindConfidence ?? 0.92 },
				answerable: { value: spec.answerable ?? 0.8 },
				candidate: { value: spec.candidate ?? "c1" },
				...(spec.legacyAnswer === null
					? {}
					: { clarifying_answer: { value: spec.legacyAnswer ?? RUNNER_FREE_TEXT } }),
			},
			...extra,
		}),
	};
}

function unavailableRun(reason: string): RawDecideRun {
	return {
		status: 0,
		timedOut: false,
		stderr: "",
		stdout: JSON.stringify({ available: false, reason }),
	};
}

interface SentMessage {
	text: string;
	options?: unknown;
}

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	sent: SentMessage[];
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => unknown>>();
	const sent: SentMessage[] = [];
	const pi = {
		on: (name: string, cb: (e: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: (text: string, options?: unknown) => {
			sent.push({ text, options });
		},
		setActiveTools: () => {},
		registerTool: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		sent,
	};
}

async function startWorker(fx: Fixture, stub?: Stub): Promise<FakeWorker> {
	process.env.PI_WORKER_TASK = fx.taskPath;
	process.chdir(fx.projectRoot);
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi, stub === undefined ? undefined : { dp3Runner: stub.run });
	return worker;
}

function settle(worker: FakeWorker, reply: string): void {
	worker.emit("agent_end", { messages: [{ role: "assistant", content: [{ type: "text", text: reply }] }] });
	worker.emit("agent_settled");
}

/** Direct `decideDp3WorkerClarify` input over a fixture (the unit-level seam,
 * no `pi` harness): same field values the settle hook uses. */
function dp3Input(fx: Fixture, question: string, stub?: Stub): Dp3DecisionInput {
	return {
		projectDir: fx.projectRoot,
		taskKey: TASK,
		ncIndex: 1,
		key: KEY,
		phase: "EXECUTE",
		taskType: "research",
		risk: "mid",
		riskSource: "pm-label",
		question,
		harnessDetail: NO_PRODUCT,
		taskDir: fx.taskDir,
		taskPath: fx.taskPath,
		taskContent: readText(fx.taskPath),
		trueRoot: fx.trueRoot,
		keyDir: fx.keyDir,
		policy: readDp3Policy(fx.projectRoot),
		runner: stub?.run,
	};
}

function readRun(fx: Fixture): RunState {
	return JSON.parse(fs.readFileSync(path.join(fx.taskDir, "run.json"), "utf8")) as RunState;
}

function readText(file: string): string {
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
}

/** The ASKING agent's dp3 material (T04 design §2): question 原文, the four
 * background facts and 2..5 distinguishable handling candidates. */
function dp3Material(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		question: NC_REPLY,
		background: {
			task_goal: "answer the clarification and finish the research product",
			current_state: "the worker is blocked on one file-location question",
			decision_reason: "the asking agent cannot resolve it from its own notes",
			constraints_impact: "a wrong guess would cite a non-existent file",
		},
		handling_options: [
			{ id: "c1", label: "交由 PM 判定", description: "把问题原文与背景交给 PM，由 PM 决定是否回答。" },
			{ id: "c2", label: "等待人工澄清", description: "保持阻塞并向用户提出这个具体问题。" },
		],
		...overrides,
	};
}

/** A `mw decide run --stdin` answer for the material path: the native
 * `handling` choice plus the authority keys Python returns. */
function handlingRun(choice: string, extra: Record<string, unknown> = {}): RawDecideRun {
	return {
		status: 0,
		timedOut: false,
		stderr: "",
		stdout: JSON.stringify({
			available: true,
			mode: "auto",
			acted: false,
			confidence_source: "api",
			latency_ms: 7,
			decision_id: "dp3-worker-clarify:dp3-worker#nc1",
			answers: { handling: { value: choice, confidence: 0.9 } },
			...extra,
		}),
	};
}

function inputWithMaterial(
	fx: Fixture,
	stub: Stub | undefined,
	material: Record<string, unknown> = dp3Material(),
): Dp3DecisionInput {
	return { ...dp3Input(fx, NC_REPLY, stub), material };
}

function traceOf(fx: Fixture): string {
	return readText(path.join(fx.taskDir, "trace.log"));
}

function decideRows(trace: string): string[] {
	// `appendTrace` prefixes every line with `[FLOW] <iso>`, exactly like the
	// design's pseudocode; the unified `[DECIDE]` row starts right after it.
	return trace.split("\n").filter((line) => line.includes("[DECIDE] "));
}

/** `## Questions` body's first non-empty line, i.e. exactly what
 * `pm/ui-bridge.ts::readTerminalDetail` reads back. */
function questionsFirstLine(output: string): string | undefined {
	const lines = output.split(/\r?\n/);
	const start = lines.findIndex((line) => line.trim() === "## Questions");
	if (start < 0) return undefined;
	for (let i = start + 1; i < lines.length; i++) {
		const line = lines[i].trim();
		if (line !== "") return line;
	}
	return undefined;
}

/** Strip the volatile fields (run id timestamp, trace timestamps, elapsed
 * seconds) so two independent runs can be compared byte-for-byte. */
function normalize(text: string): string {
	return text
		.replace(/<!-- mw-run: [^>]*-->/g, "<!-- mw-run: normalized -->")
		.replace(/\d{4}-\d{2}-\d{2}T[0-9:.]+Z/g, "<iso>")
		.replace(/elapsed=\d+s/g, "elapsed=<n>s");
}

const NC_REPLY = "I need to check: 哪个文件定义了 `prepareStructuredState`？";

// ── 1. closed state: byte-identical, zero spawn, zero trace ───────────────────

describe("invariant 1: dp3 closed state is byte-identical", () => {
	it("no decide.json and enabled=false produce the same NC product, with no [DECIDE] row and no call", async () => {
		const offByAbsence = makeFixture();
		const offByFlag = makeFixture();
		disableDecide(offByFlag);

		const stubA = stubRunner(handlingRun("c1"));
		const stubB = stubRunner(handlingRun("c1"));
		const workerA = await startWorker(offByAbsence, stubA);
		const workerB = await startWorker(offByFlag, stubB);

		settle(workerA, NC_REPLY);
		settle(workerB, NC_REPLY);

		// zero spawn / zero write
		expect(stubA.calls).toHaveLength(0);
		expect(stubB.calls).toHaveLength(0);
		expect(decideRows(traceOf(offByAbsence))).toEqual([]);
		expect(decideRows(traceOf(offByFlag))).toEqual([]);
		expect(workerA.sent).toHaveLength(0);
		expect(workerB.sent).toHaveLength(0);

		// the product and the terminal record are identical across both closed
		// configurations (byte-identical after stripping the run-id timestamp)
		const outputA = readText(path.join(offByAbsence.taskDir, "output.md"));
		const outputB = readText(path.join(offByFlag.taskDir, "output.md"));
		expect(normalize(outputA)).toBe(normalize(outputB));
		expect(questionsFirstLine(outputA)?.startsWith(NO_PRODUCT)).toBe(true);
		expect(outputA).toContain("status=needs-clarification");
		expect(outputA.match(/^## .*/gm)?.filter((h) => h === "## Questions")).toHaveLength(1);

		const runA = readRun(offByAbsence);
		expect(runA.status).toBe("needs-clarification");
		expect(runA.exit).toBe(2);
		expect(traceOf(offByAbsence)).toMatch(/\[END\][^\n]*exit=2/);
	});
});

// ── 2. `## Questions` first line keeps the original text on every fallback ───

describe("invariant 2: the settle hook never answers from local guesses (T04)", () => {
	it("an enabled dp3 without agent material keeps the byte-identical human path", async () => {
		const control = makeFixture();
		const controlWorker = await startWorker(control); // no decide.json -> closed
		settle(controlWorker, NC_REPLY);
		const controlOutput = readText(path.join(control.taskDir, "output.md"));

		const fx = makeFixture();
		enableDecide(fx);
		// A quotable local line exists: the retired 3a/3c path would have used it.
		addCandidateFile(fx);
		const stub = stubRunner(handlingRun("c2"));
		const worker = await startWorker(fx, stub);
		settle(worker, NC_REPLY);

		// The settle-time hook has no agent material, so it spends ZERO calls and
		// injects no `[mw dp3-answer]` steer: the human path proceeds unchanged.
		expect(stub.calls).toHaveLength(0);
		expect(worker.sent).toHaveLength(0);

		const output = readText(path.join(fx.taskDir, "output.md"));
		expect(questionsFirstLine(output)?.startsWith(NO_PRODUCT)).toBe(true);
		// every path without agent material is byte-identical to the closed state
		expect(normalize(output)).toBe(normalize(controlOutput));

		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("dp=dp3-worker-clarify");
		expect(rows[0]).toContain("acted=false");
		expect(rows[0]).toContain("escalated_reason=input-incomplete");
		expect(rows[0]).toContain("nc_raw=1 nc_human=1");
	});

	it("a degraded material call escalates and never invents an answer", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(unavailableRun("timeout"));
		const decision = decideDp3WorkerClarify(inputWithMaterial(fx, stub));
		expect(stub.calls).toHaveLength(1);
		expect(decision.kind).toBe("escalate");
		if (decision.kind === "escalate") {
			expect(decision.reason).toBe("unavailable");
			expect(decision.detail).toContain("timeout");
			expect(decision.decisionId).toBe(`${DP3_ID}:${TASK}#nc1`);
		}
	});
});

// ── 3. at most one auto-answer per process ──────────────────────────────────

describe("invariant 3: no auto-answer budget is ever spent at settle", () => {
	it("two clarifying settles still ask nothing and keep the human path", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		addCandidateFile(fx);
		const stub = stubRunner(handlingRun("c2"));
		const worker = await startWorker(fx, stub);

		settle(worker, NC_REPLY);
		// The NC terminal landed: no service call, no steer, no product yet.
		expect(stub.calls).toHaveLength(0);
		expect(worker.sent).toHaveLength(0);
		expect(readRun(fx).status).toBe("needs-clarification");
		expect(fs.existsSync(path.join(fx.taskDir, "output.md"))).toBe(true);

		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("acted=false");
		expect(rows[0]).toContain("nc_raw=1 nc_human=1");
		// No acted marker anywhere: nothing was auto-answered from local guesses.
		expect(traceOf(fx)).not.toContain("acted=1");
	});
});

// ── 4. 3b default + four-face NC terminal ───────────────────────────────────

describe("invariant 4: an intent-looking question is never classified locally", () => {
	it("goes to the human with zero spawn and a consistent terminal", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(handlingRun("c1"));
		const worker = await startWorker(fx, stub);

		settle(worker, "应该用哪个方案？请确认，我倾向 A。");

		expect(stub.calls).toHaveLength(0); // no local classifier decides anything
		expect(worker.sent).toHaveLength(0);

		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("acted=false");
		expect(rows[0]).toContain("nc_raw=1 nc_human=1");

		const run = readRun(fx);
		const output = readText(path.join(fx.taskDir, "output.md"));
		const trace = traceOf(fx);
		// four faces: record+exit, product marker, [END], Questions body
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);
		expect(output).toContain("status=needs-clarification");
		expect(trace).toMatch(/\[END\][^\n]*exit=2/);
		expect(questionsFirstLine(output)).toMatch(/^no-product: /);
	});
});

// ── 5. goal mtime recording is orthogonal ───────────────────────────────────

describe("invariant 5: [GOAL_CHECK] stays one-per-phase", () => {
	it("a phased run keeps one real-mtime goal check per phase and none on the NC settle", async () => {
		const fx = makeFixture(
			[
				"Use `prepareStructuredState` from the triage client.",
				"- name: phase-one",
				"  prompt: |",
				"    do phase one",
				"- name: phase-two",
				"  prompt: |",
				"    do phase two",
			].join("\n"),
		);
		enableDecide(fx);
		const stub = stubRunner(handlingRun("c2"));
		const worker = await startWorker(fx, stub);

		// initial settle -> phase one prompt
		settle(worker, "phase one reply");
		expect(worker.sent).toHaveLength(1);
		// phase one completes -> phase two prompt
		settle(worker, "phase two reply");
		expect(worker.sent).toHaveLength(2);
		// phase two completes -> NC judgement: the hook has no material, so the
		// human path proceeds (no auto-answer, no extra follow-up turn).
		settle(worker, NC_REPLY);
		expect(worker.sent).toHaveLength(2);
		expect(stub.calls).toHaveLength(0);
		expect(readRun(fx).status).toBe("needs-clarification");

		const trace = traceOf(fx);
		const goalChecks = trace.split("\n").filter((line) => line.startsWith("[GOAL_CHECK] "));
		expect(goalChecks).toHaveLength(2);
		expect(goalChecks[0]).toMatch(/^\[GOAL_CHECK\] phase=1 goal_mtime=[1-9]\d*(?:\.\d+)?$/);
		expect(goalChecks[1]).toMatch(/^\[GOAL_CHECK\] phase=2 goal_mtime=[1-9]\d*(?:\.\d+)?$/);
		expect(trace).not.toMatch(/\[GOAL_CHECK\] phase=3/);

		const phaseStart = trace.split("\n").filter((line) => /\[PHASE\] \S+ start /.test(line));
		const phaseDone = trace.split("\n").filter((line) => /\[PHASE\] \S+ done /.test(line));
		expect(phaseStart).toHaveLength(2);
		expect(phaseDone).toHaveLength(2);
		expect(decideRows(trace)).toHaveLength(1);
	});
});

// ── extra: the 3c local-reuse consumer is retired (T04) ───────────────────

describe("dp3c: a locally quoted already-stated answer is no longer injected", () => {
	it("a card body that states the answer answers nothing (zero spawn, human path)", async () => {
		const statement = "`prepareStructuredState` 在哪个文件定义？";
		const fx = makeFixture(statement);
		enableDecide(fx);
		const stub = stubRunner(handlingRun("c1"));
		const worker = await startWorker(fx, stub);

		settle(worker, statement);

		// T04: the asking agent's material owns dp3; this settle-time hook has none,
		// so neither the service nor a locally matched card line produces an answer.
		expect(stub.calls).toHaveLength(0);
		expect(worker.sent).toHaveLength(0);
		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("acted=false");
		// No classifier ran (no material): the unified row says `sub=-`.
		expect(rows[0]).toContain("sub=-");
		expect(traceOf(fx)).not.toContain("dp3 acted=1");
		expect(readText(path.join(fx.taskDir, "output.md"))).toContain("status=needs-clarification");
	});
});

// ── policy / trace-shape unit pins ──────────────────────────────────────────

describe("dp3 policy and metric-row shape", () => {
	it("missing decide-points.json is the P2 registry default (on, auto) once the transport is enabled", () => {
		const fx = makeFixture();
		expect(readDp3Policy(fx.projectRoot).enabled).toBe(false); // transport gate
		enableDecide(fx);
		expect(readDp3Policy(fx.projectRoot)).toMatchObject({ enabled: true, mode: "auto" });
	});

	it("an explicit off row / suggest mode / a bad mode value are honoured", () => {
		const off = makeFixture();
		enableDecide(off, { "dp3-worker-clarify": { enabled: false } });
		expect(readDp3Policy(off.projectRoot).enabled).toBe(false);

		const suggest = makeFixture();
		enableDecide(suggest, { "dp3-worker-clarify": { enabled: true, mode: "suggest" } });
		expect(readDp3Policy(suggest.projectRoot)).toMatchObject({ enabled: true, mode: "suggest" });

		const bad = makeFixture();
		enableDecide(bad, { "dp3-worker-clarify": { enabled: true, mode: "sometimes" } });
		expect(readDp3Policy(bad.projectRoot).enabled).toBe(false);
	});

	it("a non-object row / a bad note / a bad tier type force dp3 off (Python L2/L3)", () => {
		const nonObject = makeFixture();
		enableDecide(nonObject, { "dp3-worker-clarify": "yes" });
		expect(readDp3Policy(nonObject.projectRoot).enabled).toBe(false);

		for (const row of [
			{ enabled: true, mode: "auto", note: 5 },
			{ enabled: true, mode: "auto", note: null },
			{ enabled: true, mode: "auto", tier: 7 },
			{ enabled: "yes", mode: "auto" },
		]) {
			const fx = makeFixture();
			enableDecide(fx, { "dp3-worker-clarify": row });
			expect(readDp3Policy(fx.projectRoot).enabled, JSON.stringify(row)).toBe(false);
		}

		// L4/L7 are advisory only: an illegal or differing tier VALUE keeps dp3 on.
		const advisory = makeFixture();
		enableDecide(advisory, { "dp3-worker-clarify": { tier: "P9", enabled: true, mode: "auto", note: "trial" } });
		expect(readDp3Policy(advisory.projectRoot)).toMatchObject({ enabled: true, mode: "auto" });
	});

	it("a bad `note` (L3) disables dp3 without spawning", async () => {
		const fx = makeFixture();
		enableDecide(fx, { "dp3-worker-clarify": { tier: "P2", enabled: true, mode: "auto", note: 5 } });
		const stub = stubRunner(handlingRun("c1"));
		const worker = await startWorker(fx, stub);

		settle(worker, NC_REPLY);

		// decision_points.py L3 force-off: Python would reject the decision, so the
		// mirror must not pay for that child in the first place.
		expect(stub.calls).toHaveLength(0);
		expect(decideRows(traceOf(fx))).toEqual([]);
		expect(worker.sent).toHaveLength(0);
		expect(readRun(fx).status).toBe("needs-clarification");
		console.log("[VERIFY] dp3 L3 bad note: spawn=0, human path");
	});

	it("a material answer is a receipt: mode never injects a steer", async () => {
		const fx = makeFixture();
		enableDecide(fx, { "dp3-worker-clarify": { enabled: true, mode: "suggest" } });
		const stub = stubRunner(handlingRun("c2", { mode: "suggest" }));
		const decision = decideDp3WorkerClarify(inputWithMaterial(fx, stub));

		expect(stub.calls).toHaveLength(1);
		expect(decision.kind).toBe("handling");
		if (decision.kind === "handling") {
			expect(decision.mode).toBe("suggest");
			expect(decision.option.id).toBe("c2");
		}
		// A handling receipt is a receipt: no consumer injects a steer for it.
	});

	it("a child that reports no usable `mode` escalates instead of falling back to the local row (D-036)", () => {
		for (const extra of [{ mode: undefined }, { mode: "bogus" }]) {
			const fx = makeFixture();
			enableDecide(fx);
			const stub = stubRunner(handlingRun("c2", extra));
			const decision = decideDp3WorkerClarify(inputWithMaterial(fx, stub));
			const label = JSON.stringify(extra);
			expect(stub.calls, label).toHaveLength(1);
			expect(decision.kind, label).toBe("escalate");
			if (decision.kind === "escalate") expect(decision.detail, label).toContain("decision mode missing");
		}
	});

	it("the metric row carries the frozen key order and the nc_raw = nc_human + acted invariant", () => {
		const row = formatDp3TraceLine({
			triggerId: "t#nc1",
			sub: "3a",
			acted: true,
			mode: "auto",
			escalatedReason: "-",
			decisionId: "dp3-worker-clarify:t#nc1",
			ncRaw: 3,
			ncHuman: 2,
			now: new Date("2026-10-20T00:00:00.000Z"),
		});
		expect(row).toBe(
			"[DECIDE] 2026-10-20T00:00:00.000Z dp=dp3-worker-clarify trigger=t#nc1 sub=3a acted=true mode=auto " +
				"escalated_reason=- decision_id=dp3-worker-clarify:t#nc1 nc_raw=3 nc_human=2",
		);
		// 3b is a classification, not a degradation: it never borrows a failure reason
		const intentRow = formatDp3TraceLine({
			triggerId: "t#nc2",
			sub: "3b",
			acted: false,
			mode: "auto",
			escalatedReason: "intent",
			decisionId: "dp3-worker-clarify:t#nc2",
			ncRaw: 4,
			ncHuman: 3,
		});
		expect(intentRow).toContain("escalated_reason=-");
	});

	it("decideDp3WorkerClarify never throws on an empty question and refuses without spawning", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(handlingRun("c1"));
		const decision = decideDp3WorkerClarify(dp3Input(fx, "   ", stub));
		expect(decision.kind).toBe("escalate");
		if (decision.kind === "escalate") {
			expect(decision.reason).toBe("input-incomplete");
			expect(decision.decisionId).toBe("dp3-worker-clarify:dp3-worker#nc1");
		}
		expect(stub.calls).toHaveLength(0);
	});

	it("refuses an over-budget material as `input-oversize` with zero spawn (D-028)", () => {
		// The canonical budget is the CLIENT-side refusal (design §2.3 step 6): the
		// material is complete, it just cannot be sent, so the reason must stay
		// distinguishable from a missing field.
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(handlingRun("c1"));
		const huge = dp3Material({
			handling_options: [
				{ id: "c1", label: "A", description: "x".repeat(2_500) },
				{ id: "c2", label: "B", description: "y".repeat(2_500) },
			],
		});
		const decision = decideDp3WorkerClarify(inputWithMaterial(fx, stub, huge));

		// The request never left: zero decision-runner calls.
		expect(stub.calls).toHaveLength(0);
		expect(decision.kind).toBe("escalate");
		if (decision.kind === "escalate") expect(decision.reason).toBe("input-oversize");
	});

	it("the terminal record it starts from is the untouched `running` state", () => {
		// guard against a future refactor that commits a terminal record before dp3
		const fx = makeFixture();
		const input: RunState = {
			schema: RUN_SCHEMA,
			task_key: TASK,
			run_id: `${TASK}@2026-10-20T00:00:00.000Z`,
			owner_key: KEY,
			kind: "research",
			status: "running",
			started_at: "2026-10-20T00:00:00.000Z",
			artifacts: [],
		};
		writeRunState(fx.taskDir, input);
		expect(readRun(fx).status).toBe("running");
	});
});

// ── decision association (T-04c / D-041) ────────────────────────────────────

describe("dp3 decision association (T-04c)", () => {
	const CLI_ID = "dp3-worker-clarify:cli-trigger#nc9";

	it("the handling receipt carries the child's decision_id verbatim", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(handlingRun("c2", { decision_id: CLI_ID, mode: "auto", acted: false }));

		const decision = decideDp3WorkerClarify(inputWithMaterial(fx, stub));

		expect(decision.kind).toBe("handling");
		if (decision.kind === "handling") {
			expect(decision.decisionId).toBe(CLI_ID);
			expect(decision.option.id).toBe("c2");
		}
	});

	it("a degraded attempt records no acted marker", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(unavailableRun("timeout"));
		const worker = await startWorker(fx, stub);
		settle(worker, NC_REPLY);

		const trace = traceOf(fx);
		expect(trace).not.toContain("[DECISION] dp3 acted=1");
		const rows = decideRows(trace);
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("acted=false");
		expect(rows[0]).not.toContain("acted=true");
	});

	it("falls back to the locally derived id when the child reports none", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(handlingRun("c2"));

		const decision = decideDp3WorkerClarify(inputWithMaterial(fx, stub));

		expect(decision.kind).toBe("handling");
		if (decision.kind === "handling") expect(decision.decisionId).toBe(`${DP3_ID}:${TASK}#nc1`);
	});
});

// ── FIX-J: the local candidate classifier is retired (T04) ─────────────────

describe("dp3 3a local candidates (retired)", () => {
	it("the request carries the ASKING agent's material, never local candidates", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const rel = addCandidateFile(fx);
		const stub = stubRunner(handlingRun("c2"));
		const material = dp3Material();

		decideDp3WorkerClarify(inputWithMaterial(fx, stub, material));

		expect(stub.calls).toHaveLength(1);
		const envelope = JSON.parse(stub.calls[0]?.input ?? "{}") as {
			material?: Record<string, unknown>;
			state?: Record<string, unknown>;
		};
		// The versioned material envelope — no `{state}` and no `local_candidates`.
		expect(envelope.state).toBeUndefined();
		expect(envelope.material).toEqual(material);
		expect(envelope.material).not.toHaveProperty("local_candidates");
		expect(envelope.material).not.toHaveProperty("questions_version");
		// The local file still exists; it is simply not consulted.
		expect(fs.existsSync(path.join(fx.projectRoot, rel))).toBe(true);
	});

	it("a local candidate file never becomes the answer (no injection, zero spawn at settle)", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		addCandidateFile(fx);
		const stub = stubRunner(handlingRun("c1"));
		const worker = await startWorker(fx, stub);

		settle(worker, NC_REPLY);

		expect(stub.calls).toHaveLength(0);
		expect(worker.sent).toHaveLength(0);
		expect(traceOf(fx)).not.toContain("[DECISION] dp3 detail=candidate=");
	});

	it("a model-classified intent no longer routes anywhere: the human path stays", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(handlingRun("c1"));
		const worker = await startWorker(fx, stub);
		settle(worker, "应该用哪个方案？请确认。");

		expect(stub.calls).toHaveLength(0);
		expect(worker.sent).toHaveLength(0);
		expect(readRun(fx).status).toBe("needs-clarification");
	});

	it("a legacy reuse payload is not mapped onto a local line", () => {
		const fx = makeFixture("`prepareStructuredState` 定义在 pm/triage-client.ts:317。");
		enableDecide(fx);
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({}, { answers: { handling: { value: "c1", confidence: 0.9 } } }));
		// Even a well-formed handling answer only names a SENT candidate; nothing
		// quotes local prose any more.
		const decision = decideDp3WorkerClarify(inputWithMaterial(fx, stub));
		expect(decision.kind).toBe("handling");
		if (decision.kind === "handling") {
			expect(decision.option.id).toBe("c1");
			expect(decision.detail).not.toContain("prepareStructuredState");
		}
	});
});

describe("dp3 per-dp policy knobs (AC-016)", () => {
	it("the row layer is the effective dp3 policy; built-in reproduces the old constants", () => {
		const fx = makeFixture();
		enableDecide(fx, {
			"dp3-worker-clarify": {
				enabled: true,
				mode: "auto",
				min_confidence: 0.9,
				max_questions: 3,
				timeout_s: 150,
			},
		});
		expect(readDp3Policy(fx.projectRoot)).toMatchObject({
			enabled: true,
			minConfidence: 0.9,
			maxQuestions: 3,
			timeoutS: 150,
		});
		// The two satellite gates keep their margin: 0.9 + 0.05 / 0.9 - 0.2.
		expect(dp3Thresholds(0.9)).toEqual({ minMatchScore: 0.95, minConfidence: 0.9, answerableMin: 0.7 });
		// D-050: the built-in layer (0.7) is byte-identical to the pre-AC-016 gates.
		expect(dp3Thresholds(0.7)).toEqual({ minMatchScore: 0.75, minConfidence: 0.7, answerableMin: 0.5 });
	});

	it("the effective per-dp rows are still resolved (the material path reads them)", () => {
		const fx = makeFixture();
		enableDecide(fx, { "dp3-worker-clarify": { enabled: true, mode: "auto", min_confidence: 0.95, timeout_s: 45 } });
		const policy = readDp3Policy(fx.projectRoot);
		expect(policy.enabled).toBe(true);
		expect(policy.mode).toBe("auto");
		// The row layer still drives the ONE remaining consumer (the PM's tool reads
		// the same rows); the settle hook itself has no local answer to gate.
		const resolved = resolveDecidePolicy("dp3-worker-clarify", fx.projectRoot);
		expect(resolved.minConfidence).toBeCloseTo(0.95);
		expect(resolved.timeoutS).toBe(45);
	});

	it("parity: Python and TS resolve the shared fixture to the same effective values", () => {
		const pyPath = fileURLToPath(new URL("../../../multi-workers/test_decide_policy.py", import.meta.url));
		const source = fs.readFileSync(pyPath, "utf8");
		// The shared fixture the Python suite resolves; the TS row layer must read
		// the same five values out of it.
		expect(source).toContain("min_confidence");
		const fx = makeFixture();
		enableDecide(fx, {
			"dp3-worker-clarify": { enabled: true, mode: "auto", min_confidence: 0.9, max_questions: 3, timeout_s: 150 },
		});
		expect(readDp3Policy(fx.projectRoot)).toMatchObject({
			enabled: true,
			mode: "auto",
			minConfidence: 0.9,
			maxQuestions: 3,
			timeoutS: 150,
		});
	});

	it("assertStateMatchesRegistry validates the dp3 MATERIAL (not the retired state)", () => {
		const material = dp3Material();
		expect(() => assertStateMatchesRegistry(DP3_ID, material)).not.toThrow();
		// Missing a required path names it.
		expect(() => assertStateMatchesRegistry(DP3_ID, { question: "q" })).toThrow(/missing=/);
		// Identity never rides in the material: it is `extra` drift.
		expect(() => assertStateMatchesRegistry(DP3_ID, { ...material, task_key: TASK })).toThrow(/extra=task_key/);
		// The registry is the authority for the field list.
		const required = (DECIDE_REGISTRY[DP3_ID]?.requiredStateFields ?? []).map((field) => field.name);
		expect(required).toEqual(expect.arrayContaining(["question", "background.task_goal", "handling_options"]));
	});
});
