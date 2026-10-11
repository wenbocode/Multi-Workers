/**
 * mwds-t04-deliverable.test.ts — T-04 / AC-006 (VC-025…VC-029):
 * the settle-time three-channel deliverable predicate
 * (`shared/deliverable-evidence.ts`), its fold into `exitCode` in
 * `worker-mode.ts::finishSuccess`, the `2 → needs-clarification` status
 * mapping, the `dispatch-alarm(kind="no-product")` row on the TRUE
 * `.agenticdoc` root, and the discriminating proof that the pre-existing
 * `hasProductEvidence` run-occurrence guard was NOT narrowed.
 *
 * No provider APIs, keys or network. The worker path uses a fake
 * ExtensionAPI (same pattern as `mwds-t03-bash-write-scope.test.ts`); the
 * predicate-level cases are pure functions over temp dirs; the corpus replay
 * reads the real 30 worker dirs of `mw-gate-verdict-hardening`.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	type DispatchAlarm,
	describeDispatchAlarm,
	dispatchNewTasks,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	DELIVERABLE_PLACEHOLDERS,
	hasDeliverableEvidence,
} from "../../src/extensions/agent-team-loop/shared/deliverable-evidence.ts";
import { RUN_SCHEMA, type RunState, writeRunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

// ── corpus (VC-025) ──────────────────────────────────────────────────────────

const CORPUS = fileURLToPath(new URL("../../../../.agenticdoc/mw-gate-verdict-hardening/workers/", import.meta.url));
/** The two dirs the corpus must reject: an empty delivery (no signal at all)
 * and a hard kill (no output.md). */
const CORPUS_NC = new Set(["mwg-qg-review-20261010", "mwg-t08b-g2-surfaces"]);

const PLACEHOLDER_OUTPUT = [
	"## TL;DR",
	"",
	"(worker exited without writing output)",
	"",
	"## Summary",
	"",
	"(worker exited without writing output)",
	"",
	"## Exit Reason",
	"",
	"Process exited before output.md was written (crash or unexpected exit).",
	"",
].join("\n");

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

// ── VC-025: corpus replay (hard criterion) ───────────────────────────────────

describe("AC-006 corpus replay (VC-025)", () => {
	it("VC-025: 30 real worker dirs -> delivered=28 / none=2 / false positives=0", () => {
		expect(fs.existsSync(CORPUS), `corpus missing: ${CORPUS}`).toBe(true);
		const dirs = fs
			.readdirSync(CORPUS, { withFileTypes: true })
			.filter((d) => d.isDirectory())
			.map((d) => d.name)
			.sort();
		expect(dirs).toHaveLength(30);

		const delivered: string[] = [];
		const none: string[] = [];
		const channels = new Map<string, number>();
		for (const name of dirs) {
			const verdict = hasDeliverableEvidence(path.join(CORPUS, name), "");
			channels.set(verdict.channel, (channels.get(verdict.channel) ?? 0) + 1);
			(verdict.delivered ? delivered : none).push(name);
		}
		console.log(
			`[VC-025] corpus_dirs=${dirs.length} delivered=${delivered.length} none=${none.length} false_positives=${
				none.filter((n) => !CORPUS_NC.has(n)).length
			}`,
		);
		console.log(`[VC-025] none=[${none.join(",")}] channels=${JSON.stringify(Object.fromEntries(channels))}`);

		expect(delivered).toHaveLength(28);
		expect(none.slice().sort()).toEqual([...CORPUS_NC].sort());
		expect(none.filter((n) => !CORPUS_NC.has(n))).toHaveLength(0);
	});

	it("VC-025b: mgh-rq2-gate-alert (placeholder first block, real later blocks) is delivered", () => {
		const dir = path.join(CORPUS, "mgh-rq2-gate-alert");
		const output = fs.readFileSync(path.join(dir, "output.md"), "utf8");
		expect(output.startsWith("## TL;DR\n\n(worker exited without writing output)")).toBe(true);
		const verdict = hasDeliverableEvidence(dir, "");
		expect(verdict.delivered).toBe(true);
		expect(verdict.channel).toBe("output");
	});
});

// ── reverse cases (b)(c)(d): channel order and placeholder-only ──────────────

describe("AC-006 channel order (reverse cases b/c/d)", () => {
	it("(b) a 0-byte report.md is not delivery: the verdict falls through to the output channel", () => {
		const keyDir = mkdtemp("mwds-t04-b-");
		const taskDir = path.join(keyDir, "workers", "t");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "report.md"), "", "utf8");
		fs.writeFileSync(path.join(taskDir, "output.md"), "[VERIFY] VC-1: x=1\n", "utf8");
		const verdict = hasDeliverableEvidence(taskDir, "");
		expect(verdict.delivered).toBe(true);
		expect(verdict.channel).toBe("output");

		// Control: a 0-byte report with nothing else is not delivery.
		const bare = path.join(mkdtemp("mwds-t04-b2-"), "workers", "t");
		fs.mkdirSync(bare, { recursive: true });
		fs.writeFileSync(path.join(bare, "report.md"), "", "utf8");
		expect(hasDeliverableEvidence(bare, "").delivered).toBe(false);
	});

	it("(c) a placeholder-only output.md is none", () => {
		const keyDir = mkdtemp("mwds-t04-c-");
		const taskDir = path.join(keyDir, "workers", "t");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "output.md"), PLACEHOLDER_OUTPUT, "utf8");
		const verdict = hasDeliverableEvidence(taskDir, "");
		expect(verdict.delivered).toBe(false);
		expect(verdict.channel).toBe("none");
		expect(DELIVERABLE_PLACEHOLDERS.size).toBe(16); // 15 documented entries, idle/wall + (none) collapsed
	});

	it("(d) a machine-line-only output.md (no report) is the output channel", () => {
		const keyDir = mkdtemp("mwds-t04-d-");
		const taskDir = path.join(keyDir, "workers", "t");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "output.md"), "VERDICT=pass TASKS=3\n", "utf8");
		const verdict = hasDeliverableEvidence(taskDir, "");
		expect(verdict.delivered).toBe(true);
		expect(verdict.channel).toBe("output");
	});
});

// ── T2/T3 signal semantics at the predicate boundary ─────────────────────────

describe("AC-006 signal semantics (reply vs on-disk product, evidence refs)", () => {
	it("T2: an inline [VERIFY] in the reply is a signal while output.md is empty", () => {
		const keyDir = mkdtemp("mwds-t04-t2-");
		const taskDir = path.join(keyDir, "workers", "t");
		fs.mkdirSync(taskDir, { recursive: true });
		const verdict = hasDeliverableEvidence(taskDir, "复用上一份报告，实测结果见 [VERIFY] VC-1: x=1。");
		expect(verdict.delivered).toBe(true);
		expect(verdict.channel).toBe("output");
	});

	it("T2 negative: a placeholder-only on-disk output.md is authoritative over a chatty reply", () => {
		const keyDir = mkdtemp("mwds-t04-t2n-");
		const taskDir = path.join(keyDir, "workers", "t");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "output.md"), PLACEHOLDER_OUTPUT, "utf8");
		const verdict = hasDeliverableEvidence(taskDir, "Here is the report. [VERIFY] VC-9: x=9");
		expect(verdict.delivered).toBe(false);
	});

	it("T3: a referenced evidence file that exists (and is fresh) delivers; a missing one does not", () => {
		const keyDir = mkdtemp("mwds-t04-t3-");
		const taskDir = path.join(keyDir, "workers", "t");
		const evidence = path.join(keyDir, "evidence", "research");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.mkdirSync(evidence, { recursive: true });
		const runState: RunState = {
			schema: RUN_SCHEMA,
			task_key: "t",
			run_id: "t@2020-01-01T00:00:00.000Z",
			owner_key: "mwds-t04",
			kind: "research",
			status: "running",
			started_at: new Date(Date.now() - 60_000).toISOString(),
			artifacts: [],
		};
		writeRunState(taskDir, runState);
		fs.writeFileSync(path.join(evidence, "spec-y-20261010.md"), "# found\n", "utf8");
		fs.writeFileSync(
			path.join(taskDir, "output.md"),
			"## TL;DR\n\nDONE — note at evidence/research/spec-y-20261010.md\n",
			"utf8",
		);
		const ok = hasDeliverableEvidence(taskDir, "");
		expect(ok.delivered).toBe(true);
		expect(ok.channel).toBe("output");

		// Accident shape: the referenced report was never written.
		fs.writeFileSync(
			path.join(taskDir, "output.md"),
			"## TL;DR\n\nDONE — note at evidence/quality-gate-report-review-20261010.md\n",
			"utf8",
		);
		expect(hasDeliverableEvidence(taskDir, "").delivered).toBe(false);

		// Anti-forgery: a stale referenced file (older than the run) does not deliver.
		const stale = path.join(evidence, "spec-old-20260101.md");
		fs.writeFileSync(stale, "# old\n", "utf8");
		fs.utimesSync(stale, new Date("2020-01-01T00:00:00Z"), new Date("2020-01-01T00:00:00Z"));
		fs.writeFileSync(
			path.join(taskDir, "output.md"),
			"## TL;DR\n\nDONE — see evidence/research/spec-old-20260101.md\n",
			"utf8",
		);
		expect(hasDeliverableEvidence(taskDir, "").delivered).toBe(false);
	});

	it("artifacts channel: run.json.artifacts beyond output.md delivers even without a machine line", () => {
		const keyDir = mkdtemp("mwds-t04-art-");
		const taskDir = path.join(keyDir, "workers", "t");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "output.md"), "## Summary\n\nPASS — 3 phases done.\n", "utf8");
		const runState: RunState = {
			schema: RUN_SCHEMA,
			task_key: "t",
			run_id: "t@2020-01-01T00:00:01.000Z",
			owner_key: "mwds-t04",
			kind: "phase-writer",
			status: "done",
			started_at: "2020-01-01T00:00:00.000Z",
			artifacts: ["output.md", "phase-1-impl.md"],
		};
		writeRunState(taskDir, runState);
		const verdict = hasDeliverableEvidence(taskDir, "");
		expect(verdict.delivered).toBe(true);
		expect(verdict.channel).toBe("artifact");
	});
});

// ── worker settle: fold exitCode, status, alarm (VC-026/027/028) ─────────────

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
}

function makeFixture(type: string): Fixture {
	const projectRoot = mkdtemp("mwds-t04-w-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, "mwds-t04");
	const taskDir = path.join(keyDir, "workers", "t04-worker");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), `---\ntype: ${type}\n---\n\nDo the task.\n`, "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir };
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

function readRun(fx: Fixture): RunState {
	return JSON.parse(fs.readFileSync(path.join(fx.taskDir, "run.json"), "utf8")) as RunState;
}

function ledgerPath(fx: Fixture): string {
	return path.join(fx.trueRoot, "_autopilot", "auto-decisions.jsonl");
}

describe("AC-006 settle fold (VC-026/VC-027/VC-028)", () => {
	it("(e) undelivered read-only settle: exit=2, needs-clarification, one no-product alarm on the true root", async () => {
		const fx = makeFixture("research");
		const worker = await startWorker(fx);
		settle(worker, "This is a large review task. Let me organize my work:");

		const run = readRun(fx);
		console.log(`[VC-026/027] exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);

		const output = fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
		expect(output).toContain("status=needs-clarification");
		expect(output).toContain("## Questions\n\nno-product:");
		expect(output).not.toContain("(no questions provided)");

		const trace = fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
		expect(trace).toMatch(/\[END\][^\n]*exit=2/);

		const lines = fs.readFileSync(ledgerPath(fx), "utf8").trim().split("\n");
		expect(lines).toHaveLength(1);
		const row = JSON.parse(lines[0]) as { phase: string; kind: string; count: number; detail: string };
		console.log(`[VC-028] alarm=${JSON.stringify(row)}`);
		expect(row.phase).toBe("dispatch-alarm");
		expect(row.kind).toBe("no-product");
		expect(row.count).toBe(1);
		expect(row.detail).toContain("t04-worker");
		// The wrong root (<key>/workers) must stay untouched.
		expect(fs.existsSync(path.join(fx.keyDir, "workers", "_autopilot", "auto-decisions.jsonl"))).toBe(false);
	});

	it("(f) delivered read-only settle: exit=0, done, zero no-product rows", async () => {
		const fx = makeFixture("research");
		fs.writeFileSync(path.join(fx.taskDir, "report.md"), "# report\n\nfound it\n".repeat(10), "utf8");
		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		console.log(`[VC-026] delivered exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("done");
		expect(run.exit).toBe(0);
		expect(fs.existsSync(ledgerPath(fx))).toBe(false);

		const trace = fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
		expect(trace).toMatch(/\[END\][^\n]*exit=0/);
	});

	it("T6: write roles are exempt; the same empty output is NC only for a writeless role", async () => {
		const coding = makeFixture("coding");
		const codingWorker = await startWorker(coding);
		settle(codingWorker, "implemented");
		expect(readRun(coding).status).toBe("done");
		expect(readRun(coding).exit).toBe(0);

		const review = makeFixture("review");
		const reviewWorker = await startWorker(review);
		settle(reviewWorker, "implemented");
		expect(readRun(review).status).toBe("needs-clarification");
		expect(readRun(review).exit).toBe(2);
	});

	it("VC-028: describeDispatchAlarm covers the new kind", () => {
		const text = describeDispatchAlarm({ kind: "no-product", count: 1, detail: "t-1:research" });
		expect(text).toContain("read-only run(s) settled without a product");
		expect(text).toContain("t-1:research");
	});
});

// ── VC-029: hasProductEvidence coexistence (discriminating) ──────────────────

function writePhaseDocs(root: string, key: string): void {
	const keyDir = path.join(root, key);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Spec\n${"x".repeat(600)}\n\n| AC-001 | in x, y returns z |\n`,
		"utf8",
	);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}`, "utf8");
	const research = path.join(keyDir, "evidence", "research");
	fs.mkdirSync(research, { recursive: true });
	fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "# research\n", "utf8");
	fs.writeFileSync(path.join(research, "design-topic-2026-01-01.md"), "# research\n", "utf8");
}

function writeCandidate(root: string, key: string, taskKey: string): string {
	const dir = path.join(root, key, "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	const taskMd = path.join(dir, "task.md");
	fs.writeFileSync(taskMd, "type: research\n\nwork\n", "utf8");
	return dir;
}

describe("AC-006 coexistence with the IN-3 dispatch guard (VC-029)", () => {
	it("(g) trace.log-only dir still refuses the scan; removing it dispatches (discriminator)", async () => {
		const root = mkdtemp("mwds-t04-g-");
		writePhaseDocs(root, "k");
		fs.writeFileSync(path.join(root, "_workers.parallel"), "", "utf8");
		const taskDir = writeCandidate(root, "k", "t-1");
		fs.writeFileSync(path.join(taskDir, "trace.log"), "[START] x\n[END] x exit=1\n", "utf8");

		const store = new WorkerStore(root);
		const alarms: DispatchAlarm[] = [];
		await dispatchNewTasks(store, root, { onAlarm: (a) => alarms.push(a) });
		expect(alarms.map((a) => a.kind)).toEqual(["queue-unreadable"]);
		expect(store.readAll()).toEqual([]);
		// The new AC-006 predicate rejects the same dir: the two questions differ.
		expect(hasDeliverableEvidence(taskDir, "").delivered).toBe(false);

		// Control: without trace.log the same candidate is a fresh task and dispatches.
		fs.rmSync(path.join(taskDir, "trace.log"));
		const freshStore = new WorkerStore(root);
		const freshAlarms: DispatchAlarm[] = [];
		await dispatchNewTasks(freshStore, root, { onAlarm: (a) => freshAlarms.push(a) });
		expect(freshAlarms).toEqual([]);
		expect(freshStore.findByKey("t-1")?.status).toBe("pending");
	});
});
