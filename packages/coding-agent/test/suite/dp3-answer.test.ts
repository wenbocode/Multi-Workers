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
import type {
	DecideRunner,
	DecideRunRequest,
	RawDecideRun,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import { assertStateMatchesRegistry } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { resolveDecidePolicy } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { RUN_SCHEMA, type RunState, writeRunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import {
	buildDp3Candidates,
	DP3_ANSWER_PREFIX,
	DP3_CITATION_RE,
	DP3_QUESTIONS_VERSION,
	type Dp3DecisionInput,
	decideDp3WorkerClarify,
	dp3Thresholds,
	formatDp3TraceLine,
	matchDp3Reuse,
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

		const stubA = stubRunner(dp3Answer());
		const stubB = stubRunner(dp3Answer());
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

describe("invariant 2: the original `## Questions` first line survives a failed dp3 attempt", () => {
	it("an unavailable decision falls back to the byte-identical human path", async () => {
		const control = makeFixture();
		const controlWorker = await startWorker(control); // no decide.json -> closed
		settle(controlWorker, NC_REPLY);
		const controlOutput = readText(path.join(control.taskDir, "output.md"));

		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(unavailableRun("timeout"));
		const worker = await startWorker(fx, stub);
		settle(worker, NC_REPLY);

		expect(stub.calls).toHaveLength(1);
		expect(stub.calls[0]?.dp).toBe("dp3-worker-clarify");
		// the envelope is the state only; the question text never rides
		// state.decision_point
		const envelope = JSON.parse(stub.calls[0]?.input ?? "{}") as Record<string, unknown>;
		expect(Object.keys(envelope)).toEqual(["state"]);

		const output = readText(path.join(fx.taskDir, "output.md"));
		expect(questionsFirstLine(output)?.startsWith(NO_PRODUCT)).toBe(true);
		// every degradation is byte-identical to the closed-state product
		expect(normalize(output)).toBe(normalize(controlOutput));

		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("dp=dp3-worker-clarify");
		expect(rows[0]).toContain("sub=3a");
		expect(rows[0]).toContain("acted=false");
		expect(rows[0]).toContain("escalated_reason=unavailable");
		expect(rows[0]).toContain("nc_raw=1 nc_human=1");
	});
});

// ── 3. at most one auto-answer per process ──────────────────────────────────

describe("invariant 3: the auto-answer budget is one round per process", () => {
	it("injects one `[mw dp3-answer]` followUp and never asks again on a second NC", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }));
		const worker = await startWorker(fx, stub);

		settle(worker, NC_REPLY);

		// one call, one steer, run still open, no terminal product yet
		expect(stub.calls).toHaveLength(1);
		expect(worker.sent).toHaveLength(1);
		expect(worker.sent[0]?.text.startsWith(DP3_ANSWER_PREFIX)).toBe(true);
		expect(worker.sent[0]?.text).toContain("dp3-worker-clarify:dp3-worker#nc1");
		expect(worker.sent[0]?.options).toEqual({ deliverAs: "followUp" });
		expect(readRun(fx).status).toBe("running");
		expect(fs.existsSync(path.join(fx.taskDir, "output.md"))).toBe(false);

		const firstRows = decideRows(traceOf(fx));
		expect(firstRows).toHaveLength(1);
		expect(firstRows[0]).toContain("sub=3a acted=true mode=auto escalated_reason=-");
		expect(firstRows[0]).toContain("nc_raw=1 nc_human=0");

		// the answered turn settles NC again: no second service call, human path
		settle(worker, NC_REPLY);
		expect(stub.calls).toHaveLength(1);
		expect(worker.sent).toHaveLength(1);
		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(2);
		expect(rows[1]).toContain("sub=- acted=false");
		expect(rows[1]).toContain("nc_raw=2 nc_human=1");
		expect(readRun(fx).status).toBe("needs-clarification");
	});
});

// ── 4. 3b default + four-face NC terminal ───────────────────────────────────

describe("invariant 4: 3b is the default and the NC terminal stays four-face consistent", () => {
	it("an intent question goes to the human with zero spawn and a consistent terminal", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(dp3Answer());
		const worker = await startWorker(fx, stub);

		settle(worker, "应该用哪个方案？请确认，我倾向 A。");

		expect(stub.calls).toHaveLength(0); // 3b never spawns
		expect(worker.sent).toHaveLength(0);

		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("sub=3b acted=false mode=auto escalated_reason=-");
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

describe("invariant 5: [GOAL_CHECK] stays one-per-phase under an auto-answer", () => {
	it("a phased run keeps one real-mtime goal check per phase and adds none on the follow-up turn", async () => {
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
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }));
		const worker = await startWorker(fx, stub);

		// initial settle -> phase one prompt
		settle(worker, "phase one reply");
		expect(worker.sent).toHaveLength(1);
		// phase one completes -> phase two prompt
		settle(worker, "phase two reply");
		expect(worker.sent).toHaveLength(2);
		// phase two completes -> NC judgement -> dp3 auto-answer
		settle(worker, NC_REPLY);
		expect(worker.sent).toHaveLength(3);
		expect(worker.sent[2]?.text.startsWith(DP3_ANSWER_PREFIX)).toBe(true);

		// the follow-up turn settles NC again (budget spent) -> terminal
		settle(worker, NC_REPLY);
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
		expect(decideRows(trace)).toHaveLength(2);
	});
});

// ── extra: 3c local reuse (zero spawn) ─────────────────────────────────────

describe("dp3c: a locally matched already-stated answer never calls the service", () => {
	it("matchDp3Reuse requires a shared exact referent and the 0.6 score floor", () => {
		const question = "`prepareStructuredState` 在哪个文件定义？";
		const hit = matchDp3Reuse(question, [
			{ label: "card.md", text: "背景：`prepareStructuredState` 在哪个文件定义？" },
		]);
		expect(hit?.score).toBeGreaterThanOrEqual(0.75);
		expect(hit?.source).toBe("card.md:1");

		const noReferent = matchDp3Reuse(question, [{ label: "card.md", text: "在哪个文件定义，没有指称" }]);
		expect(noReferent).toBeUndefined();
	});

	it("injects the quoted card line with source and zero runner calls", async () => {
		const statement = "`prepareStructuredState` 在哪个文件定义？";
		const fx = makeFixture(statement);
		enableDecide(fx);
		const stub = stubRunner(dp3Answer());
		const worker = await startWorker(fx, stub);

		settle(worker, statement);

		expect(stub.calls).toHaveLength(0);
		expect(worker.sent).toHaveLength(1);
		expect(worker.sent[0]?.text).toContain("3c 已表态引用");
		expect(worker.sent[0]?.text).toContain("task.md:6");
		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("sub=3c acted=true");
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
		const stub = stubRunner(dp3Answer());
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

	it("suggest mode records the answer without injecting any steer", async () => {
		const fx = makeFixture();
		enableDecide(fx, { "dp3-worker-clarify": { enabled: true, mode: "suggest" } });
		// The spawned path takes the mode from the child (D-036), so the stub has to
		// report `suggest` too; a child that stays silent escalates (see the
		// "no usable mode" case). The answer is still archived, just never acted on.
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }, { mode: "suggest" }));
		const worker = await startWorker(fx, stub);

		settle(worker, NC_REPLY);

		expect(stub.calls).toHaveLength(1);
		expect(worker.sent).toHaveLength(0);
		const rows = decideRows(traceOf(fx));
		expect(rows[0]).toContain("sub=3a acted=false mode=suggest");
		expect(readRun(fx).status).toBe("needs-clarification");
	});

	it("a child-reported `mode=suggest` wins over the local row (D-036): no steer", async () => {
		const fx = makeFixture();
		enableDecide(fx, { "dp3-worker-clarify": { tier: "P2", enabled: true, mode: "auto", note: "" } });
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }, { mode: "suggest" }));
		const worker = await startWorker(fx, stub);

		settle(worker, NC_REPLY);

		expect(stub.calls).toHaveLength(1);
		expect(worker.sent).toHaveLength(0);
		expect(decideRows(traceOf(fx))[0]).toContain("sub=3a acted=false mode=suggest");
		expect(traceOf(fx)).not.toContain("[DECISION] dp3 acted=1");
		expect(readRun(fx).status).toBe("needs-clarification");
	});

	it("a child that reports no usable `mode` escalates instead of falling back to the local row (D-036/D-041)", async () => {
		// The spawned path has exactly one authority on "did the service answer":
		// the child's own `mode`. Inventing `auto` from the local mirror would
		// inject a steer the service never authorized.
		for (const extra of [{ mode: undefined }, { mode: "bogus" }]) {
			const fx = makeFixture();
			enableDecide(fx);
			const stub = stubRunner(dp3Answer({}, extra));
			const worker = await startWorker(fx, stub);

			settle(worker, NC_REPLY);

			const label = JSON.stringify(extra);
			expect(stub.calls, label).toHaveLength(1);
			// No steer, no `[DECISION] acted=1` marker: nothing was executed.
			expect(worker.sent, label).toHaveLength(0);
			const trace = traceOf(fx);
			expect(trace, label).not.toContain(DP3_ANSWER_PREFIX);
			expect(trace, label).not.toContain("[DECISION] dp3 acted=1");
			const rows = decideRows(trace);
			expect(rows, label).toHaveLength(1);
			expect(rows[0], label).toContain("sub=3a acted=false");
			expect(rows[0], label).toContain("escalated_reason=unavailable");
			// Human path: the NC terminal lands and no `decision:` head line.
			expect(readRun(fx).status, label).toBe("needs-clarification");
			expect(readText(fx.taskPath), label).not.toContain("decision:");
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
		const stub = stubRunner(dp3Answer());
		const decision = decideDp3WorkerClarify(dp3Input(fx, "   ", stub));
		expect(decision.kind).toBe("escalate");
		if (decision.kind === "escalate") {
			expect(decision.reason).toBe("input-incomplete");
			expect(decision.decisionId).toBe("dp3-worker-clarify:dp3-worker#nc1");
		}
		expect(stub.calls).toHaveLength(0);
	});

	it("an over-budget canonical state is refused as `input-oversize` with zero spawn (D-028)", async () => {
		// The canonical budget is the CLIENT-side refusal (design §2.3 step 6): the
		// state is complete, it just cannot be sent, so the reason must stay
		// distinguishable from a missing field. `phase` is the unbounded dispatch
		// fact here, so an oversized one is enough to cross 2000B.
		const fx = makeFixture(undefined, `EXECUTE ${"x".repeat(2_100)}`);
		enableDecide(fx);
		const stub = stubRunner(dp3Answer());
		const worker = await startWorker(fx, stub);
		settle(worker, NC_REPLY);

		// The request never left: zero decision-runner calls.
		expect(stub.calls).toHaveLength(0);
		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("sub=3a acted=false");
		expect(rows[0]).toContain("escalated_reason=input-oversize");
		expect(rows[0]).toContain("nc_raw=1 nc_human=1");
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

describe("dp3 decision association (T-04c / D-041)", () => {
	const CLI_ID = "dp3-worker-clarify:cli-trigger#nc9";

	it("the auto-answer branch records acted=1 and the child's decision_id", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		addCandidateFile(fx);
		const stub = stubRunner(
			dp3Answer({ candidate: "c2" }, { decision_id: CLI_ID, mode: "auto", acted: false, escalated_reason: null }),
		);
		const worker = await startWorker(fx, stub);
		settle(worker, NC_REPLY);

		// The id is the child's, verbatim (D-036), and it rides the injected steer.
		expect(worker.sent[0]?.text).toContain(`decision_id=${CLI_ID}`);
		const trace = traceOf(fx);
		expect(trace).toContain(`[DECISION] dp3 acted=1 decision_id=${CLI_ID}`);
		const rows = decideRows(trace);
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("sub=3a acted=true");
		expect(rows[0]).toContain(`decision_id=${CLI_ID}`);
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

	it("falls back to the locally derived id when the child reports none", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }));
		const worker = await startWorker(fx, stub);
		settle(worker, NC_REPLY);

		expect(traceOf(fx)).toContain("[DECISION] dp3 acted=1 decision_id=dp3-worker-clarify:dp3-worker#nc1");
	});
});

// ── FIX-J: local candidates + model choice + local citation ──────────────

describe("dp3 3a local candidates (FIX-J)", () => {
	it("fact + candidate=c2 answers with the LOCAL line and citation, never runner free text", async () => {
		const fx = makeFixture();
		enableDecide(fx);
		const rel = addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2", answerable: 0.8 }));
		const worker = await startWorker(fx, stub);

		settle(worker, NC_REPLY);

		expect(stub.calls).toHaveLength(1);
		expect(worker.sent).toHaveLength(1);
		const steered = worker.sent[0]?.text ?? "";
		expect(steered).toContain("3a 事实检索");
		const answer =
			steered
				.split("\n")
				.find((line) => line.startsWith("答案："))
				?.slice("答案：".length) ?? "";
		// the text is the local line (line 2), the citation the local path:line
		expect(answer.startsWith(CANDIDATE_LINE)).toBe(true);
		expect(answer.endsWith(`(${rel}:2)`)).toBe(true);
		expect(DP3_CITATION_RE.exec(answer)?.[0]).toBe(`${rel}:2`);
		expect(steered).toContain(`出处：${rel}:2`);
		// ... and no free text the child returned reaches the answer
		expect(answer).not.toContain(RUNNER_FREE_TEXT);
		expect(steered).not.toContain(RUNNER_FREE_TEXT);

		const rows = decideRows(traceOf(fx));
		expect(rows).toHaveLength(1);
		expect(rows[0]).toContain("sub=3a acted=true mode=auto escalated_reason=-");
		// the selection detail rides its own line; `[DECIDE]` keeps its shape
		expect(traceOf(fx)).toContain("[DECISION] dp3 detail=candidate=c2");
	});

	it("an `answerable` below 0.5 escalates as unanswerable", () => {
		const fx = makeFixture();
		enableDecide(fx);
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2", answerable: 0.3 }));

		const decision = decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		expect(decision.kind).toBe("escalate");
		if (decision.kind === "escalate") {
			expect(decision.reason).toBe("unavailable");
			expect(decision.sub).toBe("3a");
			expect(decision.detail).toContain("unanswerable");
		}
		expect(stub.calls).toHaveLength(1);
	});

	it("a candidate id that was never sent escalates as unknown", () => {
		const fx = makeFixture();
		enableDecide(fx);
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c9" }));

		const decision = decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		expect(decision.kind).toBe("escalate");
		if (decision.kind === "escalate") {
			expect(decision.reason).toBe("unavailable");
			expect(decision.sub).toBe("3a");
			expect(decision.detail).toContain("unknown candidate id");
			expect(decision.detail).toContain("c9");
		}
	});

	it("a candidate file that does not exist escalates as unreadable", () => {
		// Empty fixture: `c1` is the convention evidence path and no such file
		// exists, so the chosen candidate cannot be quoted from.
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c1" }));

		const decision = decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		expect(decision.kind).toBe("escalate");
		if (decision.kind === "escalate") {
			expect(decision.reason).toBe("unavailable");
			expect(decision.detail).toContain("candidate file unreadable");
			expect(decision.detail).toContain("evidence/research/");
		}
	});

	it("the request carries local_candidates c1..cN (1..5) and questions_version q-fcbd3847", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const rel = addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }));
		decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		// snapshot of the frozen FIX-I `questions_version`
		expect(DP3_QUESTIONS_VERSION).toBe("q-fcbd3847");
		const envelope = JSON.parse(stub.calls[0]?.input ?? "{}") as { state?: Record<string, unknown> };
		const state = envelope.state ?? {};
		expect(state.questions_version).toBe("q-fcbd3847");

		const candidates = state.local_candidates as Array<{ id: string; label: string }>;
		expect(Array.isArray(candidates)).toBe(true);
		expect(candidates.length).toBeGreaterThanOrEqual(1);
		expect(candidates.length).toBeLessThanOrEqual(5);
		// ids start at c1 and are contiguous
		expect(candidates.map((entry) => entry.id)).toEqual(candidates.map((_, index) => `c${index + 1}`));
		for (const entry of candidates) {
			expect(entry.id).toMatch(/^c[1-9]$/);
			expect(entry.label.trim()).not.toBe("");
			expect(entry.label.length).toBeLessThanOrEqual(80);
			expect(entry.label).not.toContain("\n");
		}
		expect(candidates[0]?.label).toMatch(/^evidence\/research\/dp3-worker-\d{8}\.md$/);
		expect(candidates.map((entry) => entry.label)).toContain(rel);
	});

	it("buildDp3Candidates keeps `c1` fixed and orders name hits by count then path", () => {
		const fx = makeFixture();
		// 3 question tokens in the path beat the 1-token evidence note.
		writeProjectFile(fx, "docs/preparestructuredstate-check-and-need.md", "x\n");
		addCandidateFile(fx);

		const candidates = buildDp3Candidates(dp3Input(fx, NC_REPLY), NC_REPLY);

		expect(candidates.map((entry) => entry.id)).toEqual(["c1", "c2", "c3"]);
		expect(candidates[0]?.label).toMatch(/^evidence\/research\/dp3-worker-\d{8}\.md$/);
		expect(candidates[1]?.label).toBe("docs/preparestructuredstate-check-and-need.md");
		expect(candidates[2]?.label).toBe(CANDIDATE_REL);
	});

	it("a model-classified intent still escalates to 3b", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const stub = stubRunner(dp3Answer({ kind: "intent" }));

		const decision = decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		expect(decision.kind).toBe("escalate");
		if (decision.kind === "escalate") {
			expect(decision.sub).toBe("3b");
			expect(decision.reason).toBe("intent");
		}
		expect(stub.calls).toHaveLength(1);
	});

	it("a legacy reuse payload keeps the unchanged 3c branch", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const quoted = "`prepareStructuredState` 定义在 pm/triage-client.ts:317";
		const stub = stubRunner(dp3Answer({ kind: "reuse", legacyAnswer: quoted }));

		const decision = decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		expect(decision.kind).toBe("answer");
		if (decision.kind === "answer") {
			expect(decision.sub).toBe("3c");
			expect(decision.answer).toBe(quoted);
			expect(decision.source).toBe("pm/triage-client.ts:317");
			expect(decision.confidence).toBe(0.92);
			expect(decision.confidenceSource).toBe("api");
			expect(decision.mode).toBe("auto");
		}
	});

	it("a reuse answer without the legacy prose quotes the local candidate line", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const rel = addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ kind: "reuse", candidate: "c2", legacyAnswer: null }));

		const decision = decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		expect(decision.kind).toBe("answer");
		if (decision.kind === "answer") {
			expect(decision.sub).toBe("3c");
			expect(decision.answer.startsWith(CANDIDATE_LINE)).toBe(true);
			expect(decision.source).toBe(`${rel}:2`);
		}
	});
});

// ── AC-016: per-dp policy knobs (min_confidence / max_questions / timeout_s)

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

	it("a raised per-dp min_confidence escalates a 3a answer that the default gate would act on", async () => {
		const fx = makeFixture();
		// dp3Answer() carries an `api` confidence of 0.92: above 0.7, below 0.95.
		enableDecide(fx, { "dp3-worker-clarify": { enabled: true, mode: "auto", min_confidence: 0.95 } });
		addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }));
		const worker = await startWorker(fx, stub);

		settle(worker, NC_REPLY);

		expect(stub.calls).toHaveLength(1);
		expect(worker.sent).toHaveLength(0);
		const trace = traceOf(fx);
		expect(trace).not.toContain("[DECISION] dp3 acted=1");
		expect(decideRows(trace)[0]).toContain("acted=false");
		expect(readRun(fx).status).toBe("needs-clarification");
	});

	it("parity: Python and TS resolve the shared fixture to the same effective values", () => {
		const pyPath = fileURLToPath(new URL("../../../multi-workers/test_decide_policy.py", import.meta.url));
		const source = fs.readFileSync(pyPath, "utf8");
		const between = source.split("# PARITY-FIXTURE-BEGIN")[1]?.split("# PARITY-FIXTURE-END")[0] ?? "";
		const start = between.indexOf('"""');
		const end = between.lastIndexOf('"""');
		const fixture = JSON.parse(between.slice(start + 3, end)) as {
			decide: Record<string, unknown>;
			points: Record<string, unknown>;
			expected: Record<string, { min_confidence: number; max_questions: number; timeout_s: number }>;
		};
		const projectDir = mkdtemp("dp3-policy-parity-");
		fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
		fs.writeFileSync(path.join(projectDir, ".mw", "decide.json"), JSON.stringify(fixture.decide), "utf8");
		fs.writeFileSync(
			path.join(projectDir, ".mw", "decide-points.json"),
			JSON.stringify({ version: 1, points: fixture.points }),
			"utf8",
		);
		for (const [dpId, expected] of Object.entries(fixture.expected)) {
			const resolved = resolveDecidePolicy(dpId, projectDir);
			const effective = {
				min_confidence: resolved.minConfidence,
				max_questions: resolved.maxQuestions,
				timeout_s: resolved.timeoutS,
			};
			expect(effective, dpId).toEqual(expected);
		}
	});

	it("sends candidate_snippets with the verbatim hit line and its source (W6)", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const rel = addCandidateFile(fx);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }));
		decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		const envelope = JSON.parse(stub.calls[0]?.input ?? "{}") as { state?: Record<string, unknown> };
		const context = envelope.state?.context as
			| { change_summary?: string; candidate_snippets?: Array<{ text: string; source: string }> }
			| undefined;
		expect(context?.change_summary).toContain("clarification (scope)");
		const snippets = context?.candidate_snippets ?? [];
		const hit = snippets.find((entry) => entry.source.startsWith(`${rel}:`));
		expect(hit).toBeDefined();
		expect(hit?.text).toContain("prepareStructuredState lives in pm/triage-client.ts");
		expect(hit?.source).toMatch(/:2$/);
	});

	it("clips a candidate hit line to 200 characters (W6)", () => {
		const fx = makeFixture();
		enableDecide(fx);
		const longLine = `# prepareStructuredState ${"z".repeat(400)}`;
		writeProjectFile(fx, CANDIDATE_REL, `# notes\n${longLine}\n`);
		const stub = stubRunner(dp3Answer({ candidate: "c2" }));
		decideDp3WorkerClarify(dp3Input(fx, NC_REPLY, stub));

		const envelope = JSON.parse(stub.calls[0]?.input ?? "{}") as { state?: Record<string, unknown> };
		const context = envelope.state?.context as { candidate_snippets?: Array<{ text: string }> } | undefined;
		const texts = (context?.candidate_snippets ?? []).map((entry) => entry.text);
		const clipped = texts.find((text) => text.startsWith("# prepareStructuredState"));
		expect(clipped).toBeDefined();
		expect(clipped?.length).toBe(200);
		expect(clipped).not.toContain("z".repeat(201));
	});

	it("assertStateMatchesRegistry throws on a dp3 state missing a required field (W6)", () => {
		const state = {
			schema_version: 2,
			decision_point: "dp3-worker-clarify",
			key: KEY,
			phase: "EXECUTE",
			task_type: "research",
			risk: "mid",
			risk_source: "pm-label",
			authority_tier: "P2",
			questions_version: DP3_QUESTIONS_VERSION,
			local_candidates: [{ id: "c1", label: "evidence/x.md" }],
		};
		expect(() => assertStateMatchesRegistry("dp3-worker-clarify", state)).toThrow(/missing=task_summary/);
	});
});
