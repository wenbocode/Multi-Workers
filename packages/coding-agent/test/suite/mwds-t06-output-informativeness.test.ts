/**
 * mwds-t06-output-informativeness.test.ts — T-06 / AC-007 (VC-031…VC-033):
 * the product (`output.md`) must carry information a reader can act on.
 *
 *  - VC-031: no deliverables => the `## Changed Files`/`## Deliverables`
 *    section is omitted whole (never an empty section, never `(none)`).
 *  - VC-032: deliverables present => `## Deliverables` lists them and never
 *    the machine-generated `output.md`/`progress.md`.
 *  - VC-033: `## Exit Reason` carries the effort (`<n> tool call(s)` + the
 *    `writes=<report.md|progress.md|none>` field) instead of one constant
 *    string for an 8-call run and a 127-call run alike.
 *
 * The settle cases drive the real `workerModeActivate` path with a fake
 * ExtensionAPI (same pattern as `mwds-t04-deliverable.test.ts`); no provider
 * APIs, keys or network. The write-side format is additionally pinned at the
 * `writeOutput` boundary and against the source text (falsifying the old
 * unreachable `?? "(none)"` branch).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { readOutputSection } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { writeOutput } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

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

// ── worker settle fixture ────────────────────────────────────────────────────

interface Fixture {
	projectRoot: string;
	keyDir: string;
	taskDir: string;
}

function makeFixture(type: string): Fixture {
	const projectRoot = mkdtemp("mwds-t06-w-");
	const keyDir = path.join(projectRoot, ".agenticdoc", "mwds-t06");
	const taskDir = path.join(keyDir, "workers", "t06-worker");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), `---\ntype: ${type}\n---\n\nDo the task.\n`, "utf8");
	return { projectRoot, keyDir, taskDir };
}

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

function writeTool(worker: FakeWorker, id: string, target: string): void {
	worker.emit("tool_execution_start", { toolName: "write", toolCallId: id, args: { path: target } });
}

function readOutput(fx: Fixture): string {
	return fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
}

// ── VC-031: no deliverables ⇒ section omitted whole ─────────────────────────

describe("AC-007 no-deliverable settle (VC-031)", () => {
	it("VC-031 (a): a write-role settle with no artifacts has neither section and no (none)", async () => {
		const fx = makeFixture("coding");
		const worker = await startWorker(fx);
		settle(worker, "implemented");

		const out = readOutput(fx);
		expect(out).not.toContain("## Changed Files");
		expect(out).not.toContain("## Deliverables");
		expect(out).not.toContain("(none)");
		// The rest of the exit-0 contract is intact.
		for (const section of ["## TL;DR", "## Summary", "## Verification Steps", "## Exit Reason"]) {
			expect(out).toContain(section);
		}
		// The old writer's only `## Changed Files` producer passed `[]`, so the
		// section was always the literal `(none)`; that path is gone for good.
		expect(readOutputSection(fx.taskDir, "Changed Files")).toBeUndefined();
		console.log("[VC-031] no_artifacts_section_absent=true none_literal=0");
	});
});

// ── VC-032: deliverables present ⇒ ## Deliverables, filtered ────────────────

describe("AC-007 deliverable section (VC-032)", () => {
	it("VC-032 (b): artifacts => ## Deliverables excluding output.md and progress.md", async () => {
		const fx = makeFixture("coding");
		// A pre-existing agent-written output.md (D-117 merge) plus the two
		// machine products must never be listed as deliverables.
		fs.writeFileSync(path.join(fx.taskDir, "output.md"), "VERDICT=pass\n", "utf8");
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), "# report\n\nfindings\n", "utf8");
		fs.writeFileSync(path.join(fx.taskDir, "progress.md"), "CKPT 1m ...\n", "utf8");
		fs.writeFileSync(path.join(fx.taskDir, "phase-1-impl.md"), "# phase 1\n", "utf8");

		const worker = await startWorker(fx);
		settle(worker, "implemented");

		const body = readOutputSection(fx.taskDir, "Deliverables");
		expect(body).toBeDefined();
		expect(body?.split("\n")).toEqual(["phase-1-impl.md", "report.md"]);
		expect(body).not.toContain("output.md");
		expect(body).not.toContain("progress.md");
		expect(readOutput(fx)).not.toContain("## Changed Files");
		console.log("[VC-032] with_artifacts_heading=Deliverables excludes_output_md=true excludes_progress_md=true");
	});

	it("VC-032 (b'): an artifacts-only list made of the two machine products omits the section", async () => {
		const fx = makeFixture("coding");
		fs.writeFileSync(path.join(fx.taskDir, "output.md"), "stub\n", "utf8");
		fs.writeFileSync(path.join(fx.taskDir, "progress.md"), "CKPT 1m ...\n", "utf8");
		const worker = await startWorker(fx);
		settle(worker, "implemented");
		const out = readOutput(fx);
		expect(out).not.toContain("## Changed Files");
		expect(out).not.toContain("## Deliverables");
	});
});

// ── VC-033: Exit Reason carries effort ──────────────────────────────────────

describe("AC-007 exit-reason effort (VC-033)", () => {
	it("VC-033 (c): tool count and writes=<product> distinguish an 8-call from a 127-call run", async () => {
		const fx = makeFixture("coding");
		const worker = await startWorker(fx);
		// 8 calls: the last one is the report write.
		for (let i = 0; i < 7; i++)
			worker.emit("tool_execution_start", { toolName: "read", toolCallId: `r${i}`, args: {} });
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), "# report\n", "utf8");
		writeTool(worker, "w0", path.join(fx.taskDir, "report.md"));
		settle(worker, "implemented");

		const reason = readOutputSection(fx.taskDir, "Exit Reason");
		expect(reason).toMatch(/^Agent settled after 8 tool call\(s\)\./);
		expect(reason).toContain("writes=report.md");
		expect(reason).not.toContain("writes=none");
		expect(reason?.split("\n")).toHaveLength(1);
		console.log(`[VC-033] exit_reason=${JSON.stringify(reason)}`);
	});

	it("VC-033 (c'): a run with no write action reports writes=none but still names the tool count", async () => {
		const fx = makeFixture("coding");
		const worker = await startWorker(fx);
		settle(worker, "implemented");
		const reason = readOutputSection(fx.taskDir, "Exit Reason");
		expect(reason).toMatch(/^Agent settled after 0 tool call\(s\)\./);
		expect(reason).toContain("writes=none");
		console.log(`[VC-033] exit_reason_no_write=${JSON.stringify(reason)}`);
	});

	it("VC-033 (c''): a progress.md-only run reports writes=progress.md", async () => {
		const fx = makeFixture("research");
		const worker = await startWorker(fx);
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), "# report\n", "utf8");
		writeTool(worker, "w1", path.join(fx.taskDir, "progress.md"));
		settle(worker, "done");
		// A delivered read-only run is exit 0, so ## Exit Reason is written.
		expect(readOutputSection(fx.taskDir, "Exit Reason")).toContain("writes=progress.md");
	});
});

// ── (d) falsify the old unreachable path ────────────────────────────────────

describe("AC-007 old (none) branch (falsification)", () => {
	it("(d1) source: the section is conditional and the dead `?? (none)` expression is gone", () => {
		const src = fs.readFileSync(
			fileURLToPath(new URL("../../src/extensions/agent-team-loop/worker/output-writer.ts", import.meta.url)),
			"utf8",
		);
		expect(src).toContain("## Deliverables");
		// Scan CODE only: a comment is allowed to name the retired section.
		const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
		expect(code).not.toContain("## Changed Files");
		expect(code).not.toContain('opts.changedFiles?.join("\\n") ?? "(none)"');
		// The filter is the single place both machine products are excluded.
		expect(code).toContain('f !== "output.md" && f !== "progress.md"');
	});

	it("(d2) real run: the settle-produced output.md never regains the (none) literal", async () => {
		const fx = makeFixture("coding");
		const worker = await startWorker(fx);
		settle(worker, "implemented");
		const out = readOutput(fx);
		expect(out).not.toContain("## Changed Files");
		expect((out.match(/\(none\)/g) ?? []).length).toBe(0);
	});

	it("(d3) writeOutput boundary: an empty deliverable list omits the section at the unit level too", () => {
		const root = mkdtemp("mwds-t06-unit-");
		const key = "t-unit";
		fs.mkdirSync(path.join(root, key), { recursive: true });
		writeOutput({
			taskKey: key,
			agenticdocRoot: root,
			exitCode: 0,
			summary: "Done",
			verificationSteps: "see trace",
			exitReason: `Agent settled after 3 tool call(s). writes=none`,
		});
		const out = fs.readFileSync(path.join(root, key, "output.md"), "utf8");
		expect(out).not.toContain("## Changed Files");
		expect(out).not.toContain("## Deliverables");
		expect(out).not.toContain("(none)");
	});
});
