/**
 * output-recovery-contract.test.ts — T-04 / AC-003 (design §3.2):
 * the `output.md` recovery contract (`worker/output-sections.ts`) and the
 * write-out enforcement in `worker/output-writer.ts`.
 *
 * The contract: every worker report carries `结论 / 证据 / 残留与未验证 /
 * 上下文来源` (plus `改动清单` for coding and `未覆盖面声明` for review). A
 * complete report settles `done`; a missing section settles
 * `needs-clarification` and the read-back names the missing section instead of
 * the old generic "only placeholder sections". Historical task books without a
 * header `type:` are never judged (migration compatibility).
 *
 * No provider APIs, keys or network: the settle cases use the fake
 * ExtensionAPI pattern already used by `test/suite/mwds-t04-deliverable.test.ts`
 * (worker-mode is driven by events, not by a real model).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { readOutputSection, readTerminalDetail } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { RunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import {
	checkRecovery,
	RECOVERY_SECTIONS,
	recoverySectionsFor,
} from "../../src/extensions/agent-team-loop/worker/output-sections.ts";
import { writeOutput } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

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

/** A complete research report: all four base sections, with the evidence
 * section carrying the machine-readable line the delivery oracle needs. */
const COMPLETE_RESEARCH = [
	"## 结论",
	"已经查清，结论如下。",
	"",
	"## 证据",
	"[VERIFY] VC-AC003: `rg -n foo src` -> 3 hits",
	"",
	"## 残留与未验证",
	"无未验证项。",
	"",
	"## 上下文来源",
	"spec.md:12, design.md:34",
	"",
].join("\n");

/** All of it except 上下文来源 (the discriminating missing section). */
const MISSING_CONTEXT_SOURCES = COMPLETE_RESEARCH.replace(/## 上下文来源[\s\S]*$/, "");

/** An incomplete report that also carries no delivery signal — the real
 * incident shape (content, but not a recoverable product): the run settles
 * needs-clarification and the read-back must name the missing sections. */
const INCOMPLETE_REPORT = ["## 结论", "需要澄清。", "", "## 上下文来源", "spec.md:12", ""].join("\n");

const COMPLETE_CODING = `${COMPLETE_RESEARCH}\n## 改动清单\n- src/a.ts\n`;
const COMPLETE_REVIEW = `${COMPLETE_RESEARCH}\n## 未覆盖面声明\n未覆盖 src/b.ts。\n`;

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	taskDir: string;
}

function makeFixture(type: string | undefined, taskKey = "t04-worker"): Fixture {
	const projectRoot = mkdtemp("mwd-t04-recovery-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const taskDir = path.join(trueRoot, "mwd-t04", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	const head = type === undefined ? "" : `type: ${type}\n\n`;
	fs.writeFileSync(path.join(taskDir, "task.md"), `${head}Do the task.\n`, "utf8");
	return { projectRoot, trueRoot, taskDir };
}

// ── checkRecovery (pure predicate) ───────────────────────────────────────────

describe("checkRecovery (AC-003)", () => {
	it("RECOVERY_SECTIONS is the documented base four", () => {
		expect([...RECOVERY_SECTIONS]).toEqual(["结论", "证据", "残留与未验证", "上下文来源"]);
	});

	it("complete research report => ok, no missing section", () => {
		const verdict = checkRecovery(COMPLETE_RESEARCH, "research");
		console.log(`[VC-AC003] research_complete ok=${verdict.ok} missing=${JSON.stringify(verdict.missing)}`);
		expect(verdict.ok).toBe(true);
		expect(verdict.missing).toEqual([]);
	});

	it("missing 上下文来源 => ok=false and the missing list names exactly that section", () => {
		const verdict = checkRecovery(MISSING_CONTEXT_SOURCES, "research");
		expect(verdict.ok).toBe(false);
		expect(verdict.missing).toEqual(["上下文来源"]);
	});

	it("coding adds 改动清单; review adds 未覆盖面声明 (and not vice versa)", () => {
		expect(recoverySectionsFor("coding")).toEqual([...RECOVERY_SECTIONS, "改动清单"]);
		expect(recoverySectionsFor("review")).toEqual([...RECOVERY_SECTIONS, "未覆盖面声明"]);

		expect(checkRecovery(COMPLETE_CODING, "coding").ok).toBe(true);
		expect(checkRecovery(COMPLETE_CODING, "review").missing).toEqual(["未覆盖面声明"]);
		expect(checkRecovery(COMPLETE_REVIEW, "review").ok).toBe(true);
		expect(checkRecovery(COMPLETE_REVIEW, "coding").missing).toEqual(["改动清单"]);
	});

	it("undefined/unknown type carries the base four only", () => {
		expect(recoverySectionsFor(undefined)).toEqual([...RECOVERY_SECTIONS]);
		expect(recoverySectionsFor("vision")).toEqual([...RECOVERY_SECTIONS]);
		expect(checkRecovery(COMPLETE_RESEARCH, undefined).ok).toBe(true);
	});

	it("empty text is missing every required section", () => {
		expect(checkRecovery("", "research").missing).toEqual([...RECOVERY_SECTIONS]);
	});

	it("CRLF and LF are equivalent (EOL-normalized judgement)", () => {
		const crlf = COMPLETE_RESEARCH.replace(/\n/g, "\r\n");
		expect(checkRecovery(crlf, "research").ok).toBe(true);
	});
});

// ── write-out enforcement ────────────────────────────────────────────────────

describe("writeOutput recovery enforcement", () => {
	it("needs-clarification path: the read-back names the missing sections", () => {
		const fx = makeFixture("research");
		writeOutput({
			taskKey: "mwd-t04/workers/t04-worker",
			agenticdocRoot: fx.trueRoot,
			exitCode: 2,
			summary: "settled without a complete report",
			questions: "no-product: output.md carries only placeholder sections",
		});
		const detail = readTerminalDetail(fx.taskDir, "needs-clarification");
		console.log(`[VC-AC003] nc_detail="${detail}"`);
		expect(detail).toContain("no-product:");
		expect(detail).toContain("缺失段：");
		for (const name of ["证据", "残留与未验证", "上下文来源"]) {
			expect(detail).toContain(name);
		}
		// Not the old generic-only line.
		expect(detail).not.toBe("no-product: output.md carries only placeholder sections");
	});

	it("done path with a complete report: no gap section, clean exit reason", () => {
		const fx = makeFixture("research");
		const outputPath = path.join(fx.taskDir, "output.md");
		fs.writeFileSync(outputPath, COMPLETE_RESEARCH, "utf8");
		writeOutput({
			taskKey: "mwd-t04/workers/t04-worker",
			agenticdocRoot: fx.trueRoot,
			exitCode: 0,
			summary: "research complete",
			exitReason: "Agent settled.",
		});
		const out = fs.readFileSync(outputPath, "utf8");
		expect(out).not.toContain("## Recovery Gaps");
		expect(out).toContain("## Exit Reason\n\nAgent settled.");
	});

	// Residual limitation (documented in the report): a report that satisfies the
	// delivery oracle but misses a recovery section keeps its `done` run status;
	// the writer still records the named gaps on the product so the PM can chase
	// them. Flipping the status for this case needs the verdict folded before
	// worker-mode picks the exit code (worker-mode is T-05-owned).
	it("done path with gaps: the named gaps are recorded, not a placeholder-only claim", () => {
		const fx = makeFixture("research");
		const outputPath = path.join(fx.taskDir, "output.md");
		fs.writeFileSync(outputPath, MISSING_CONTEXT_SOURCES, "utf8");
		writeOutput({
			taskKey: "mwd-t04/workers/t04-worker",
			agenticdocRoot: fx.trueRoot,
			exitCode: 0,
			summary: "research done",
			exitReason: "Agent settled.",
		});
		const out = fs.readFileSync(outputPath, "utf8");
		expect(out).toContain("## Recovery Gaps");
		expect(out).toContain("缺失段：上下文来源");
	});

	it("migration: no task.md (legacy unit caller) => contract not applied", () => {
		const root = mkdtemp("mwd-t04-legacy-");
		const key = "legacy";
		fs.mkdirSync(path.join(root, key), { recursive: true });
		writeOutput({ taskKey: key, agenticdocRoot: root, exitCode: 0, summary: "Done" });
		const out = fs.readFileSync(path.join(root, key, "output.md"), "utf8");
		expect(out).not.toContain("缺失段");
		expect(out).not.toContain("## Recovery Gaps");
	});

	it("migration: task.md without a header type: is never judged", () => {
		const fx = makeFixture(undefined);
		writeOutput({
			taskKey: "mwd-t04/workers/t04-worker",
			agenticdocRoot: fx.trueRoot,
			exitCode: 0,
			summary: "Done",
		});
		const out = fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
		expect(out).not.toContain("缺失段");
	});
});

// ── settle fold (worker-mode) ────────────────────────────────────────────────

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
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

describe("recovery contract at settle (AC-003)", () => {
	it("complete report => done", async () => {
		const fx = makeFixture("research");
		const worker = await startWorker(fx);
		settle(worker, COMPLETE_RESEARCH);

		const run = readRun(fx);
		console.log(`[VC-AC003] complete settle: exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("done");
		expect(run.exit).toBe(0);
		expect(readTerminalDetail(fx.taskDir, "done")).not.toBe("");
	});

	it("missing section => needs-clarification and the read-back names it", async () => {
		const fx = makeFixture("research");
		const worker = await startWorker(fx);
		settle(worker, INCOMPLETE_REPORT);

		const run = readRun(fx);
		console.log(`[VC-AC003] incomplete settle: exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);

		const detail = readTerminalDetail(fx.taskDir, "needs-clarification");
		console.log(`[VC-AC003] nc_detail="${detail}"`);
		expect(detail).toContain("证据");
		expect(detail).toContain("残留与未验证");
		expect(readOutputSection(fx.taskDir, "Questions")).toContain("缺失段：");
	});
});
