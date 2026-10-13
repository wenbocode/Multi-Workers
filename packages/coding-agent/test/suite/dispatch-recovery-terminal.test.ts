/**
 * dispatch-recovery-terminal.test.ts — T-07 / key `mw-dispatch-card-gate`.
 *
 * Closes the four W1/W2 residuals (card T-07):
 *   1. AC-003 terminal flip: an incomplete `output.md`/report product flips the
 *      run status from `done` to `needs-clarification` and names the missing
 *      section on the `## Questions` readback line; a complete report stays
 *      `done`; a migration book without a header `type:` is never judged.
 *   2. AC-007 escape hatch: `allow_foreign_write: true` is really READ — it
 *      lets a declared foreign bash write through and audits it with
 *      `[ESCAPE_HATCH] allow_foreign_write=<task> target=<path>`; absent/false
 *      stays fail-closed.
 *   3. P-08 vocabulary: the in-use runtime aliases (`verifier`, `repair`,
 *      `phase-writer`, ...) and the legacy `codex` value are no longer
 *      `unknown-type`; a genuinely unknown value still is; the tool layer's
 *      accepted set and the worker runtime's registered set are locked to the
 *      single-source vocabulary.
 *   4. AC-004 change ledger: a report-declared file the trace never recorded
 *      flips the run and lands in `## Ledger Gaps`; a trace with no
 *      `[WRITE_FILE]` event but a non-empty declaration is `unjudgeable`
 *      (T-12/F-04), and a successful bash write is recorded like write/edit.
 *
 * No provider APIs: the settle/guard cases drive `workerModeActivate` through a
 * fake ExtensionAPI (the `output-recovery-contract.test.ts` pattern).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { readTerminalDetail } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	DISPATCH_TYPE_VOCABULARY,
	isKnownDispatchType,
	typeExtrasMissing,
} from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";
import { DISPATCHABLE_TYPES } from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";
import type { RunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { readTerminalGaps } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import {
	REGISTERED_WORKER_TYPES,
	WORKER_TYPE_VOCABULARY,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

// ── fixtures ─────────────────────────────────────────────────────────────────

const tempDirs: string[] = [];
function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

let savedCwd = process.cwd();
beforeEach(() => {
	savedCwd = process.cwd();
});
afterEach(() => {
	process.chdir(savedCwd);
	delete process.env.PI_WORKER_TASK;
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Complete research report: the four base sections + a delivery signal. */
const COMPLETE_RESEARCH = [
	"## 结论",
	"查清了。",
	"",
	"## 证据",
	"[VERIFY] VC-t07: probe -> ok",
	"",
	"## 残留与未验证",
	"无。",
	"",
	"## 上下文来源",
	"spec.md:1",
	"",
].join("\n");

/** Same report minus 上下文来源: the discriminating missing section. */
const MISSING_CONTEXT_SOURCES = COMPLETE_RESEARCH.replace(/## 上下文来源[\s\S]*$/, "");

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
}

function makeFixture(type: string | undefined, extraFrontmatter: string[] = []): Fixture {
	const projectRoot = mkdtemp("mwd-t07-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, "mwd-t07");
	const taskDir = path.join(keyDir, "workers", "t07-worker");
	for (const dir of [taskDir, path.join(keyDir, "evidence")]) fs.mkdirSync(dir, { recursive: true });
	const head = type === undefined ? "" : `type: ${type}\n`;
	fs.writeFileSync(
		path.join(taskDir, "task.md"),
		`${head}${extraFrontmatter.join("\n")}${head || extraFrontmatter.length > 0 ? "\n" : ""}work\n`,
		"utf8",
	);
	return { projectRoot, trueRoot, keyDir, taskDir };
}

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	toolCall: (toolName: string, input: Record<string, unknown>) => { block?: boolean; reason?: string } | undefined;
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => unknown>>();
	const pi = {
		on: (name: string, cb: (e: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: () => {},
		setActiveTools: () => {},
		registerTool: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		toolCall: (toolName, input) => {
			for (const cb of handlers.get("tool_call") ?? []) {
				const result = cb({ type: "tool_call", toolCallId: "tc", toolName, input }) as
					| { block?: boolean; reason?: string }
					| undefined;
				if (result?.block) return result;
			}
			return undefined;
		},
	};
}

async function startWorker(fx: Fixture): Promise<FakeWorker> {
	process.env.PI_WORKER_TASK = path.join(fx.taskDir, "task.md");
	process.chdir(fx.projectRoot);
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return worker;
}

function settle(worker: FakeWorker, reply: string): void {
	worker.emit("agent_end", { messages: [{ role: "assistant", content: [{ type: "text", text: reply }] }] });
	worker.emit("agent_settled");
}

function readRun(fx: Fixture): RunState {
	return JSON.parse(fs.readFileSync(path.join(fx.taskDir, "run.json"), "utf8")) as RunState;
}

// ── 1. AC-003 terminal flip ──────────────────────────────────────────────────

describe("AC-003 terminal flip (T-07 requirement 1)", () => {
	it("a delivered but incomplete report flips done -> needs-clarification and names the missing section", async () => {
		const fx = makeFixture("research");
		const worker = await startWorker(fx);
		settle(worker, MISSING_CONTEXT_SOURCES);

		const run = readRun(fx);
		console.log(`[VC-T07-1] incomplete exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);

		const detail = readTerminalDetail(fx.taskDir, "needs-clarification");
		console.log(`[VC-T07-1] readback="${detail}"`);
		expect(detail).toContain("上下文来源");
		expect(detail).toContain("缺失段：");
	});

	it("a complete report settles done", async () => {
		const fx = makeFixture("research");
		const worker = await startWorker(fx);
		settle(worker, COMPLETE_RESEARCH);

		const run = readRun(fx);
		console.log(`[VC-T07-1] complete exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("done");
		expect(run.exit).toBe(0);
	});

	it("migration: a book without a header type: is never judged (no flip)", async () => {
		const fx = makeFixture(undefined);
		const worker = await startWorker(fx);
		settle(worker, MISSING_CONTEXT_SOURCES);

		const run = readRun(fx);
		console.log(`[VC-T07-1] no_type exit=${run.exit} status=${run.status}`);
		// Delivered (inline [VERIFY]) and NOT judged => done, proving the flip is
		// gated on the declared type rather than on the missing section.
		expect(run.status).toBe("done");
		expect(run.exit).toBe(0);
		expect(readTerminalDetail(fx.taskDir, "done")).not.toContain("缺失段");
	});
});

// ── 2. AC-007 escape hatch is really read ────────────────────────────────────

describe("AC-007 escape hatch read point (T-07 requirement 2)", () => {
	const FOREIGN = "echo x > ../foreign-out.md";

	it("declared true: the foreign write is allowed and audited", async () => {
		const fx = makeFixture("research", ["allow_foreign_write: true"]);
		const worker = await startWorker(fx);
		const result = worker.toolCall("bash", { command: FOREIGN });
		console.log(`[VC-T07-2] declared block=${String(result?.block)}`);
		expect(result?.block).toBeUndefined();
		const trace = fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
		expect(trace).toContain("[ESCAPE_HATCH] allow_foreign_write=t07-worker target=../foreign-out.md");
	});

	it("missing declaration: fail-closed (blocked, no audit line)", async () => {
		const fx = makeFixture("research");
		const worker = await startWorker(fx);
		const result = worker.toolCall("bash", { command: FOREIGN });
		console.log(`[VC-T07-2] undeclared block=${String(result?.block)} rule=${result?.reason ?? ""}`);
		expect(result?.block).toBe(true);
		const trace = fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
		expect(trace).not.toContain("[ESCAPE_HATCH]");
	});

	it("declared false: fail-closed", async () => {
		const fx = makeFixture("research", ["allow_foreign_write: false"]);
		const worker = await startWorker(fx);
		const result = worker.toolCall("bash", { command: FOREIGN });
		expect(result?.block).toBe(true);
	});

	it("the isolation deny list is never widened by the hatch (other key stays blocked)", async () => {
		const fx = makeFixture("research", ["allow_foreign_write: true"]);
		const worker = await startWorker(fx);
		const result = worker.toolCall("bash", { command: "echo x > .agenticdoc/other-key/out.md" });
		expect(result?.block).toBe(true);
		expect(result?.reason).toContain("rule=deny");
		const trace = fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
		expect(trace).not.toContain("[ESCAPE_HATCH]");
	});
});

// ── 3. P-08 type vocabulary single source ────────────────────────────────────

describe("P-08 type vocabulary (T-07 requirement 3)", () => {
	it("the legacy codex value and the in-use runtime aliases are recognised", () => {
		for (const value of [
			"codex",
			"verifier",
			"repair",
			"phase-writer",
			"roadmap-writer",
			"reviewer",
			"vision",
			"rag-research",
		]) {
			expect(isKnownDispatchType(value), value).toBe(true);
			expect(typeExtrasMissing(value, ""), value).toEqual([]);
		}
		console.log(`[VC-T07-3] vocabulary=${DISPATCH_TYPE_VOCABULARY.length} codex_known=true`);
	});

	it("a genuinely unknown value is still named (the branch stays discriminating)", () => {
		expect(isKnownDispatchType("deploy")).toBe(false);
		expect(typeExtrasMissing("deploy", "")).toEqual(["unknown-type:deploy"]);
	});

	it("the tool-layer accepted set and the worker runtime set are subsets of the one vocabulary", () => {
		const known = new Set<string>(DISPATCH_TYPE_VOCABULARY);
		for (const type of DISPATCHABLE_TYPES) expect(known.has(type), `tool-layer ${type}`).toBe(true);
		for (const type of REGISTERED_WORKER_TYPES) expect(known.has(type), `runtime ${type}`).toBe(true);
		expect(WORKER_TYPE_VOCABULARY).toEqual(DISPATCH_TYPE_VOCABULARY);
		console.log(
			`[VC-T07-3] tool_layer=${DISPATCHABLE_TYPES.length} runtime=${REGISTERED_WORKER_TYPES.length} vocabulary=${DISPATCH_TYPE_VOCABULARY.length}`,
		);
	});
});

// ── 4. AC-004 change ledger folded into the terminal verdict ─────────────────

describe("AC-004 ledger gaps (T-07 requirement 6)", () => {
	const COMPLETE_WITH_LEDGER = `${COMPLETE_RESEARCH}\n## 改动清单\n- src/a.ts\n- src/z.ts\n`;
	const BASH_LEDGER_REPORT = `${COMPLETE_RESEARCH}\n## 改动清单\n- src/a.ts\n`;

	it("a declared-but-unrecorded file flips the run and lands in ## Ledger Gaps", async () => {
		const fx = makeFixture("research");
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), COMPLETE_WITH_LEDGER, "utf8");
		// One recorded write (src/a.ts); src/z.ts is only declared.
		fs.writeFileSync(path.join(fx.taskDir, "trace.log"), "[WRITE_FILE] path=src/a.ts\n", "utf8");
		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		console.log(`[VC-T07-4] ledger exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);
		const output = fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
		expect(output).toContain("## Ledger Gaps");
		expect(output).toContain("src/z.ts");
		const detail = readTerminalDetail(fx.taskDir, "needs-clarification");
		expect(detail).toContain("未记录写入：src/z.ts");
	});

	it("T-12/F-04: a trace with no [WRITE_FILE] event and a declaration is unjudgeable, not green", async () => {
		const fx = makeFixture("research");
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), COMPLETE_WITH_LEDGER, "utf8");
		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		console.log(`[VC-T12-F04] unjudgeable exit=${run.exit} status=${run.status}`);
		// The declaration cannot be confirmed or refuted without events: the run
		// is not a clean pass, and the reason is named on the readback line.
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);
		const output = fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
		expect(output).toContain("## Ledger Unjudgeable");
		expect(output).toContain("未记录写入（不可判）：src/a.ts、src/z.ts");
		const detail = readTerminalDetail(fx.taskDir, "needs-clarification");
		expect(detail).toContain("未记录写入（不可判）");
	});

	it("migration: no [WRITE_FILE] event and no declaration is not judged", async () => {
		const fx = makeFixture("research");
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), COMPLETE_RESEARCH, "utf8");
		const worker = await startWorker(fx);
		settle(worker, "done");
		expect(readRun(fx).status).toBe("done");
		const output = fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
		expect(output).not.toContain("## Ledger Gaps");
		expect(output).not.toContain("## Ledger Unjudgeable");
	});

	it("T-12/F-04: a successful bash write records a [WRITE_FILE] event", async () => {
		const fx = makeFixture("coding");
		const worker = await startWorker(fx);
		worker.emit("tool_execution_start", {
			toolName: "bash",
			toolCallId: "b1",
			args: { command: "echo x > src/a.ts" },
		});
		worker.emit("tool_execution_end", {
			toolCallId: "b1",
			toolName: "bash",
			isError: false,
			result: { content: [] },
		});
		const trace = fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
		expect(trace).toContain("[WRITE_FILE] path=src/a.ts");
	});

	it("T-12/F-04: a bash-only coding run reconciles green against its declaration", async () => {
		const fx = makeFixture("coding");
		const worker = await startWorker(fx);
		worker.emit("tool_execution_start", {
			toolName: "bash",
			toolCallId: "b1",
			args: { command: "echo x > src/a.ts" },
		});
		worker.emit("tool_execution_end", {
			toolCallId: "b1",
			toolName: "bash",
			isError: false,
			result: { content: [] },
		});
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), BASH_LEDGER_REPORT, "utf8");
		settle(worker, "done");

		const run = readRun(fx);
		console.log(`[VC-T12-F04] bash-only exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("done");
		expect(run.exit).toBe(0);
	});

	it("readTerminalGaps is the single verdict both the status and the product use", () => {
		const fx = makeFixture("research");
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), COMPLETE_WITH_LEDGER, "utf8");
		fs.writeFileSync(path.join(fx.taskDir, "trace.log"), "[WRITE_FILE] path=src/a.ts\n", "utf8");
		const gaps = readTerminalGaps({
			taskKey: "mwd-t07/workers/t07-worker",
			agenticdocRoot: fx.trueRoot,
			summary: "",
		});
		expect(gaps.judged).toBe(true);
		expect(gaps.missingSections).toEqual([]);
		expect(gaps.unrecordedFiles).toEqual(["src/z.ts"]);
		expect(gaps.ok).toBe(false);
	});
});
