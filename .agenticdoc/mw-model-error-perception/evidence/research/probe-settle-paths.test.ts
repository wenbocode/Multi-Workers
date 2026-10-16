/**
 * TRQ2 empirical probe (mw-model-error-perception / trq2-settle-paths).
 *
 * Drives two layers with a faux provider that ONLY returns HTTP 500 errors:
 *
 * Probe C (logic level): the REAL worker-mode extension (`workerModeActivate`)
 * on a FakeWorkerPi — proves the agent_settled handler is blind to
 * stopReason==="error": first settle dispatches phase 1, error settles advance
 * the phase machine, phase exhaustion reaches finishSuccess with exit 0.
 *
 * Probe A/B (session level): a real AgentSession (suite harness) whose
 * extension mimics the worker-mode phase machine, driven the way
 * runPrintMode drives it (await prompt -> read last message -> dispose) and
 * the way an idle-waiting driver would. Reveals whether a queued phase run
 * keeps print mode alive and what the OS exit code reads.
 *
 * Repo-write policy: everything is written under os.tmpdir().
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { fauxAssistantMessage } from "@earendil-works/pi-ai/compat";
import type { ExtensionAPI } from "../../../../packages/coding-agent/src/core/extensions/types.ts";
import { workerModeActivate } from "../../../../packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts";
import {
	createHarness,
	getUserTexts,
	type Harness,
} from "../../../../packages/coding-agent/test/suite/harness.ts";

const ERR = { stopReason: "error" as const, errorMessage: "HTTP 500 Internal Server Error" };
const errMsg = (): ReturnType<typeof fauxAssistantMessage> => fauxAssistantMessage("", ERR);

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	sent: Array<{ text: string; options?: { deliverAs?: string } }>;
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => unknown>>();
	const sent: FakeWorker["sent"] = [];
	const pi = {
		on: (name: string, cb: (e: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: (text: string, options?: { deliverAs?: string }) => {
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

function makeTask(root: string, taskKey: string, body: string): { taskDir: string; taskMd: string } {
	const taskDir = path.join(root, "key-a", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	const taskMd = path.join(taskDir, "task.md");
	fs.writeFileSync(taskMd, body, "utf8");
	return { taskDir, taskMd };
}

function read(file: string): string {
	try {
		return fs.readFileSync(file, "utf8");
	} catch {
		return `(missing: ${file})`;
	}
}

const savedEnv = new Map<string, string | undefined>();
function setEnv(name: string, value: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	process.env[name] = value;
}

const harnesses: Harness[] = [];
const tempDirs: string[] = [];
function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
});

/** Probe C: worker-mode agent_settled on error turns (real worker-mode). */
describe("probe C: worker-mode agent_settled on error turns (real worker-mode)", () => {
	it("C-1 error settles dispatch phases, advance the machine, and end in exit=0 done", async () => {
		const root = mkdtemp("trq2-phased-");
		const { taskDir, taskMd } = makeTask(
			root,
			"probe-phased",
			"type: coding\ntimeout: 5\n\n- name: build\n  prompt: |\n    do build\n\n- name: verify\n  prompt: |\n    do verify\n",
		);
		setEnv("PI_WORKER_TASK", taskMd);
		const worker = fakeWorkerPi();
		await workerModeActivate(worker.pi);

		const errorEnd = { messages: [{ role: "assistant", content: [], ...ERR }] };

		// Settle 1: initial prompt settled on an ERROR turn.
		worker.emit("agent_end", errorEnd);
		worker.emit("agent_settled");
		expect(worker.sent.length).toBe(1);
		expect(worker.sent[0]?.text).toContain("do build");

		// Settle 2: phase 1 settled on an ERROR turn -> treated as phase complete.
		worker.emit("agent_end", errorEnd);
		worker.emit("agent_settled");
		expect(worker.sent.length).toBe(2);
		expect(worker.sent[1]?.text).toContain("do verify");

		// Settle 3: phase 2 settled on an ERROR turn -> machine exhausted -> finishSuccess.
		worker.emit("agent_end", errorEnd);
		worker.emit("agent_settled");

		const trace = read(path.join(taskDir, "trace.log"));
		const output = read(path.join(taskDir, "output.md"));
		const run = JSON.parse(read(path.join(taskDir, "run.json"))) as { status: string; exit: number };
		const phase1 = read(path.join(taskDir, "progress", "phase-1.md"));

		console.log("[probe C-1] trace:\n" + trace);
		console.log("[probe C-1] output.md:\n" + output);
		console.log("[probe C-1] run.json:", JSON.stringify(run));
		console.log("[probe C-1] phase-1.md:\n" + phase1);

		expect(trace).toMatch(/\[PHASE\] \S+ start 1\/2 build/);
		expect(trace).toMatch(/\[PHASE\] \S+ done 1\/2/);
		expect(trace).toMatch(/\[PHASE\] \S+ start 2\/2 verify/);
		expect(trace).toMatch(/\[PHASE\] \S+ done 2\/2/);
		expect(trace).toMatch(/\[GOAL_CHECK\] phase=1/);
		expect(trace).toMatch(/\[END\] \S+ exit=0 \S+ tools=0 phases=2\/2/);
		expect(phase1).toContain("Phase 1 complete");
		expect(run.status).toBe("done");
		expect(run.exit).toBe(0);
		expect(output).toContain("Agent settled after 0 tool call(s)");
		// The blindness: no artifact of the run mentions the 500 at all.
		expect(output.toLowerCase()).not.toContain("500");
		expect(trace.toLowerCase()).not.toContain("500");
		expect(trace).not.toContain("[TIMEOUT]");
	});

	it("C-2 writeless research role: first error settle -> no-product needs-clarification, no self-check turn", async () => {
		const root = mkdtemp("trq2-research-");
		const { taskDir, taskMd } = makeTask(root, "probe-research", "type: research\n\nresearch something\n");
		setEnv("PI_WORKER_TASK", taskMd);
		const worker = fakeWorkerPi();
		await workerModeActivate(worker.pi);

		worker.emit("agent_end", { messages: [{ role: "assistant", content: [], ...ERR }] });
		worker.emit("agent_settled");

		const trace = read(path.join(taskDir, "trace.log"));
		const output = read(path.join(taskDir, "output.md"));
		const run = JSON.parse(read(path.join(taskDir, "run.json"))) as { status: string; exit: number };
		console.log("[probe C-2] trace:\n" + trace);
		console.log("[probe C-2] output.md:\n" + output);
		console.log("[probe C-2] run.json:", JSON.stringify(run));

		expect(worker.sent.length).toBe(0); // no self-check turn: reply carries no deliverable
		expect(trace).toMatch(/recovery-gap missing=\S+ selfcheck=pending/);
		expect(trace).toMatch(/\[END\] \S+ exit=2/);
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);
		expect(output).toContain("no-product: no report file and no output text");
		expect(output).toContain("## Recovery Gaps");
	});

	it("C-3 write coding role without phases: error settle -> exit=0 done", async () => {
		const root = mkdtemp("trq2-coding-");
		const { taskDir, taskMd } = makeTask(root, "probe-coding", "type: coding\n\nbuild the thing\n");
		setEnv("PI_WORKER_TASK", taskMd);
		const worker = fakeWorkerPi();
		await workerModeActivate(worker.pi);

		worker.emit("agent_end", { messages: [{ role: "assistant", content: [], ...ERR }] });
		worker.emit("agent_settled");

		const trace = read(path.join(taskDir, "trace.log"));
		const output = read(path.join(taskDir, "output.md"));
		const run = JSON.parse(read(path.join(taskDir, "run.json"))) as { status: string; exit: number };
		console.log("[probe C-3] trace:\n" + trace);
		console.log("[probe C-3] output.md:\n" + output);
		console.log("[probe C-3] run.json:", JSON.stringify(run));

		expect(trace).toMatch(/\[END\] \S+ exit=0 \S+ tools=0 phases=-/);
		expect(run.status).toBe("done");
		expect(run.exit).toBe(0);
		expect(output).toContain("## Exit Reason");
		expect(output).toContain("Agent settled after 0 tool call(s)");
		expect(output).toContain("writes=none");
	});
});

/** Probe A/B: real AgentSession + settle-driven phase machine, print-mode driver. */
describe("probe A/B: print-mode lifecycle vs queued phase runs (real session, all-500)", () => {
	function phaseExtension() {
		const state = { settles: 0, terminal: false };
		return {
			state,
			factory: (pi: {
				on: (name: string, cb: () => void) => void;
				sendUserMessage: (text: string) => void;
			}) => {
				pi.on("agent_settled", () => {
					state.settles++;
					if (state.settles <= 2) pi.sendUserMessage(`phase-${state.settles} prompt`);
					else state.terminal = true;
				});
			},
		};
	}

	async function allErrorHarness(): Promise<{ harness: Harness; state: ReturnType<typeof phaseExtension>["state"] }> {
		const ext = phaseExtension();
		const harness = await createHarness({
			settings: { retry: { enabled: true, maxRetries: 1, baseDelayMs: 1 } },
			extensionFactories: [ext.factory as never],
		});
		harnesses.push(harness);
		harness.setResponses([
			errMsg(),
			errMsg(),
			errMsg(),
			errMsg(),
			errMsg(),
			errMsg(),
			errMsg(),
			errMsg(),
		]);
		return { harness, state: ext.state };
	}

	function lastMsg(harness: Harness): { role?: string; stopReason?: string; text?: string } {
		const msgs = harness.session.state.messages;
		const last = msgs[msgs.length - 1] as
			| { role: string; stopReason?: string; content?: Array<{ type: string; text?: string }> }
			| undefined;
		if (!last) return {};
		const text = (last.content ?? [])
			.filter((c) => c.type === "text")
			.map((c) => c.text ?? "")
			.join("\n");
		return { role: last.role, stopReason: last.stopReason, text };
	}

	it("probe B: idle-waiting driver — phases DO run to completion, every settle on an error turn", async () => {
		const { harness, state } = await allErrorHarness();
		await harness.session.prompt("task");
		// An idle-waiting host (what print mode does NOT do).
		for (let i = 0; i < 100 && !(state.terminal && harness.session.isIdle); i++) {
			await new Promise((r) => setTimeout(r, 20));
		}
		const users = getUserTexts(harness);
		const turnEnds = harness.eventsOfType("turn_end").length;
		const agentEnds = harness.eventsOfType("agent_end").length;
		const settles = harness.eventsOfType("agent_settled").length;
		const deltas = harness.eventsOfType("message_update").length;
		const last = lastMsg(harness);
		console.log(
			`[probe B] users=${JSON.stringify(users)} settles=${settles} turn_end=${turnEnds} agent_end=${agentEnds} message_update=${deltas} last=${JSON.stringify(last)}`,
		);
		expect(users).toEqual(["task", "phase-1 prompt", "phase-2 prompt"]);
		expect(state.terminal).toBe(true);
		expect(settles).toBe(3);
		// maxRetries=1: each prompt runs 2 agent attempts -> 2 turn_end/agent_end.
		expect(turnEnds).toBe(6);
		expect(agentEnds).toBe(6);
		// Q4 evidence: boundary events fired on EVERY error attempt (2 per prompt).
		expect(turnEnds).toBeGreaterThanOrEqual(3);
		console.log(`[probe B] deltas=${deltas} (faux error streams do emit message_update)`);
		expect(last.stopReason).toBe("error");
		// print-mode text branch verdict on this final state:
		expect(last.stopReason === "error" || last.stopReason === "aborted").toBe(true);
	});

	it("probe A: print-mode driver — prompt resolves at FIRST settle; dispose kills the queued phase run", async () => {
		const { harness, state } = await allErrorHarness();
		await harness.session.prompt("task");
		const atResolve = {
			last: lastMsg(harness),
			turnEnds: harness.eventsOfType("turn_end").length,
			agentEnds: harness.eventsOfType("agent_end").length,
			settles: harness.eventsOfType("agent_settled").length,
			pending: harness.getPendingResponseCount(),
			isIdle: harness.session.isIdle,
		};
		// print-mode text branch reads the last message NOW:
		const printExit =
			atResolve.last.role === "assistant" &&
			(atResolve.last.stopReason === "error" || atResolve.last.stopReason === "aborted")
				? 1
				: 0;
		harness.session.dispose(); // what runPrintMode's disposeRuntime does
		await new Promise((r) => setTimeout(r, 200));
		const afterDispose = {
			last: lastMsg(harness),
			turnEnds: harness.eventsOfType("turn_end").length,
			agentEnds: harness.eventsOfType("agent_end").length,
			settles: harness.eventsOfType("agent_settled").length,
			pending: harness.getPendingResponseCount(),
			terminal: state.terminal,
		};
		console.log(`[probe A] atResolve=${JSON.stringify(atResolve)} printExit=${printExit}`);
		console.log(`[probe A] afterDispose=${JSON.stringify(afterDispose)}`);
		// Structural facts (independent of exact interleaving):
		// 1. prompt() resolved while the phase machine had NOT reached its terminal settle.
		expect(state.terminal).toBe(false);
		// 2. After dispose, no further public events arrive (listeners disconnected).
		const frozenTurnEnds = harness.eventsOfType("turn_end").length;
		await new Promise((r) => setTimeout(r, 100));
		expect(harness.eventsOfType("turn_end").length).toBe(frozenTurnEnds);
		// 3. The exit code print mode would set comes from the message read at resolve time.
		expect([0, 1]).toContain(printExit);
	});
});
