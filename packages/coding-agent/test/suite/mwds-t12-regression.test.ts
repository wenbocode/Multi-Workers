/**
 * mwds-t12-regression.test.ts — T-12 / AC-009: cross-card SEAM cases.
 *
 * The per-card suites justify each card in isolation; this file exists because
 * every one of them touches a boundary another card owns. Each case runs BOTH
 * ends on ONE fixture and asserts they reach the same conclusion:
 *
 *   1. `write_scope:` header (T-02 producer, `ui-bridge.ts`) consumed by the
 *      bash write-scope guard (T-03, `worker-mode.ts`) — including the
 *      absent (fail-open) and blank (fail-closed) header shapes.
 *   2. `hasDeliverableEvidence` channel (T-04) and the Python launcher reap
 *      (T-07) agree: the run.json status derived from the T-04 verdict is the
 *      status `_reap_status` returns, even with exit 0 (the G-f gap).
 *   3. T-06 section generation (`output-writer.ts`) and the T-05 read side
 *      (`output-sections.ts`) do not break each other on a double run.
 *   4. `mw doctor`'s `blocked_on_human` (T-08) and the monitor panel's
 *      same-source quantity (monitor.ts) agree on one fixture.
 *   5. T-09's stage-terminal reminder suppression and the doctor gates
 *      section do not interfere (the doctor never consults stage status).
 *
 * The Python half is driven through `python -X utf8` on a temp probe script so
 * the fixture stays single-sourced here. No provider APIs, keys or network.
 */

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { readMonitorState, renderMonitorLines } from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import {
	readTerminalDetail,
	renderDefaultWriteScope,
	writeDispatchTaskMd,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { hasDeliverableEvidence } from "../../src/extensions/agent-team-loop/shared/deliverable-evidence.ts";
import {
	readLastProductSection,
	readOutputSections,
} from "../../src/extensions/agent-team-loop/shared/output-sections.ts";
import { writeOutput } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import {
	type BashWriteScopeConfig,
	checkBashWriteScopeTarget,
	parseTaskMd,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const REPO_ROOT = path.resolve(fileURLToPath(new URL("../../../../", import.meta.url)));
const MW_DIR = path.join(REPO_ROOT, "packages", "multi-workers").replace(/\\/g, "/");

const tempDirs: string[] = [];
function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Run a probe script under the repo's Python (3.10+ fromisoformat handles the
 * `Z` suffix) against a fixture dir and parse its `JSON:` line. */
function runPythonJson(code: string, args: string[]): Record<string, unknown> {
	const dir = mkdtemp("mwds-t12-py-");
	const script = path.join(dir, "probe.py");
	const machineLayer = path.join(dir, "no-machine-layer.json");
	const preamble = [
		"import json, pathlib, sys, os",
		`sys.path.insert(0, ${JSON.stringify(MW_DIR)})`,
		`os.environ["MW_AUTOPILOT_FILE"] = ${JSON.stringify(machineLayer.replace(/\\/g, "/"))}`,
	].join("\n");
	fs.writeFileSync(script, `${preamble}\n${code}\n`, "utf8");
	const out = execFileSync("python", ["-X", "utf8", script, ...args], {
		cwd: REPO_ROOT,
		encoding: "utf8",
		// stdout only: the launcher deliberately writes its conflict line to stderr
		// (`.mw/launcher.log` under `mw serve`), which is not this probe's output.
		stdio: ["ignore", "pipe", "ignore"],
		env: { ...process.env, MW_AUTOPILOT_FILE: machineLayer },
	});
	const line = out
		.split(/\r?\n/)
		.filter((l) => l.startsWith("JSON:"))
		.pop();
	if (line === undefined) throw new Error(`probe emitted no JSON line:\n${out}`);
	return JSON.parse(line.slice("JSON:".length)) as Record<string, unknown>;
}

// ── seam 1: C1/C2 write_scope (T-02 producer → T-03 consumer) ────────────────

describe("seam C1/C2: write_scope header (T-02) consumed by the bash guard (T-03)", () => {
	interface SeamProject {
		projectRoot: string;
		agenticdocRoot: string;
	}

	function makeProject(): SeamProject {
		const projectRoot = mkdtemp("mwds-t12-ws-");
		return { projectRoot, agenticdocRoot: path.join(projectRoot, ".agenticdoc") };
	}

	function writeResearchTask(p: SeamProject, taskKey: string, writeScope?: string) {
		return writeDispatchTaskMd(
			{ agenticdocRoot: p.agenticdocRoot, ownerKey: "k" },
			{
				taskKey,
				type: "research",
				body: "work",
				frontmatter: "type: research\nphase: EXECUTE\n",
				writeScope,
				injectWriteSurface: true,
			},
		);
	}

	function scopeConfig(p: SeamProject, taskDir: string, writeScope: string[] | undefined): BashWriteScopeConfig {
		return {
			projectRoot: p.projectRoot,
			taskDir,
			keyDir: path.join(p.agenticdocRoot, "k"),
			trueRoot: p.agenticdocRoot,
			writeScope,
		};
	}

	it("the producer's one-line header is parsed by the consumer and both defaults are symmetric", () => {
		const p = makeProject();
		const taskKey = "t-ws";
		const written = writeResearchTask(p, taskKey, renderDefaultWriteScope("k", taskKey));
		const meta = parseTaskMd(written.path);
		expect(meta.writeScope).toEqual([`.agenticdoc/k/workers/${taskKey}`, ".agenticdoc/k/evidence"]);
		const taskDir = path.join(p.agenticdocRoot, "k", "workers", taskKey);
		const cfg = scopeConfig(p, taskDir, meta.writeScope);
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/k/evidence/x.md").allowed).toBe(true);
		expect(checkBashWriteScopeTarget(cfg, `.agenticdoc/k/workers/${taskKey}/report.md`).allowed).toBe(true);

		// A narrower producer line excludes the key evidence tree: the consumer
		// must honour it (intersection), not fall back to the default surface.
		const narrowedKey = `${taskKey}-n`;
		const narrowed = writeResearchTask(p, narrowedKey, `write_scope: .agenticdoc/k/workers/${narrowedKey}`);
		const narrowedMeta = parseTaskMd(narrowed.path);
		const narrowedCfg = scopeConfig(
			p,
			path.join(p.agenticdocRoot, "k", "workers", narrowedKey),
			narrowedMeta.writeScope,
		);
		const blocked = checkBashWriteScopeTarget(narrowedCfg, ".agenticdoc/k/evidence/x.md");
		expect(blocked.allowed).toBe(false);
		expect(blocked.rule).toBe("write-scope");
	});

	it("an absent header fails open and a blank header fails closed (both consume shapes)", () => {
		const p = makeProject();
		const absent = writeResearchTask(p, "t-absent", undefined);
		expect(fs.readFileSync(absent.path, "utf8")).not.toContain("write_scope:");
		const absentMeta = parseTaskMd(absent.path);
		expect(absentMeta.writeScope).toBeUndefined();
		expect(
			checkBashWriteScopeTarget(
				scopeConfig(p, path.join(p.agenticdocRoot, "k", "workers", "t-absent"), absentMeta.writeScope),
				".agenticdoc/k/evidence/x.md",
			).allowed,
		).toBe(true);

		const blankDir = path.join(p.agenticdocRoot, "k", "workers", "t-blank");
		fs.mkdirSync(blankDir, { recursive: true });
		const blankPath = path.join(blankDir, "task.md");
		fs.writeFileSync(blankPath, "type: research\nwrite_scope:\n\nwork\n", "utf8");
		const blankMeta = parseTaskMd(blankPath);
		expect(blankMeta.writeScope).toEqual([]);
		const verdict = checkBashWriteScopeTarget(
			scopeConfig(p, blankDir, blankMeta.writeScope),
			".agenticdoc/k/evidence/x.md",
		);
		expect(verdict.allowed).toBe(false);
		expect(verdict.rule).toBe("write-scope");
	});
});

// ── seam 2: C5/C6 deliverable verdict (T-04) ↔ python reap (T-07) ────────────

const REAP_PROBE = [
	"import launcher",
	"task_dir = pathlib.Path(sys.argv[1])",
	'print("JSON:" + json.dumps({"status": launcher._reap_status(task_dir, int(sys.argv[2]), task_dir.name)}))',
].join("\n");

describe("seam C5/C6: T-04 verdict and T-07 python reap agree on one fixture", () => {
	it("the verdict-derived run.json status is exactly what the launcher reaps (exit 0 cannot override)", () => {
		const root = mkdtemp("mwds-t12-reap-");
		for (const name of ["delivered", "undelivered"] as const) {
			const taskDir = path.join(root, "k", "workers", name);
			fs.mkdirSync(taskDir, { recursive: true });
			if (name === "delivered") fs.writeFileSync(path.join(taskDir, "report.md"), "# report\n\nfound\n", "utf8");
			const verdict = hasDeliverableEvidence(taskDir, "");
			// The T-04 fold: delivered => exit 0/done, none => exit 2/NC.
			const status = verdict.delivered ? "done" : "needs-clarification";
			fs.writeFileSync(
				path.join(taskDir, "run.json"),
				JSON.stringify({
					schema: 1,
					task_key: name,
					run_id: `${name}@2026-10-11T00:00:00.000Z`,
					owner_key: "k",
					kind: "research",
					status,
					started_at: "2026-10-11T00:00:00.000Z",
					artifacts: [],
				}),
				"utf8",
			);
			const reaped = runPythonJson(REAP_PROBE, [taskDir, "0"]).status;
			console.log(
				`[VERIFY] seam T-04/T-07 ${name}: delivered=${verdict.delivered} status=${status} reaped=${String(reaped)}`,
			);
			expect(verdict.delivered).toBe(name === "delivered");
			expect(reaped).toBe(status);
		}
	});
});

// ── seam 3: T-06 section generation ↔ T-05 read side ────────────────────────

describe("seam C7: T-06 section generation and the T-05 read side do not break each other", () => {
	it("a T-06-written output.md reads back through the T-05 readers across a double run", () => {
		const root = mkdtemp("mwds-t12-sections-");
		const taskKey = "t-sections";
		const taskDir = path.join(root, taskKey);
		const write = (summary: string, files: string[]): void => {
			writeOutput({
				taskKey,
				agenticdocRoot: root,
				exitCode: 0,
				summary,
				changedFiles: files,
				verificationSteps: "see trace",
				exitReason: "Agent settled after 8 tool call(s). writes=report.md",
			});
		};
		write("DONE — all good", ["report.md", "phase-1-impl.md", "output.md", "progress.md"]);
		const first = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
		const firstTitles = readOutputSections(first).map((b) => b.title);
		expect(firstTitles).toContain("Deliverables");
		expect(firstTitles).not.toContain("Changed Files");
		expect(readOutputSections(first).find((b) => b.title === "Deliverables")?.body).toBe(
			"report.md\nphase-1-impl.md",
		);
		expect(readLastProductSection(first, ["TL;DR", "Summary"])?.body).toBe("DONE — all good");
		expect(readTerminalDetail(taskDir, "failed")).toContain("writes=report.md");

		// D-117 double run: the append-only writer adds a second block, and the
		// read side still resolves the LAST real block while T-06's sections
		// stay machine-readable.
		write("SECOND — replay", ["report.md"]);
		const second = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
		expect(readLastProductSection(second, ["TL;DR", "Summary"])?.body).toBe("SECOND — replay");
		expect(readTerminalDetail(taskDir, "failed")).toContain("writes=report.md");
		expect(readOutputSections(second).some((b) => b.title === "Deliverables" && b.body === "report.md")).toBe(true);
	});
});

// ── python project fixtures shared by seams 4 and 5 ─────────────────────────

function gateText(id: string, stage: number | null, createdMinutesAgo: number): string {
	const created = new Date(Date.now() - createdMinutesAgo * 60_000).toISOString();
	const expires = new Date(Date.now() + 24 * 3600_000).toISOString();
	return [
		"---",
		`id: ${id}`,
		"gate_schema: 2",
		"kind: stage-confirm",
		`stage: ${stage === null ? "" : stage}`,
		"key: k1",
		`created_at: ${created}`,
		"created_by: conductor",
		"question: proceed?",
		"context_refs: []",
		"status: pending",
		"answered_at:",
		"answered_by:",
		"note:",
		"reason_code: stage:all-keys-terminal",
		`expires_at: ${expires}`,
		"default_action: escalate-to-human",
		"---",
		"",
		`# Gate ${id}`,
		"",
	].join("\n");
}

function writeGate(root: string, id: string, stage: number | null, createdMinutesAgo: number): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot", "gates");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(path.join(dir, `${id}.md`), gateText(id, stage, createdMinutesAgo), "utf8");
}

function writeConfig(root: string): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(path.join(dir, "config.json"), `${JSON.stringify({ enabled: true }, null, 2)}\n`, "utf8");
}

function writeBeat(root: string, ageMs: number): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	const line = JSON.stringify({
		ts: new Date(Date.now() - ageMs).toISOString(),
		seq: 1,
		ev: "beat",
		key: "-",
		stage: null,
		detail: "",
	});
	fs.writeFileSync(path.join(dir, "timeline.jsonl"), `${line}\n`, "utf8");
}

function writeQueueRow(root: string, key: string, status: string): void {
	const taskDir = path.join(root, ".agenticdoc", key);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
	const row = [
		key,
		status,
		"pi",
		"timi",
		path.join(taskDir, "task.md"),
		"2026-10-11T00:00:00Z",
		"2026-10-11T00:00:00Z",
		"timi/glm-5.3",
	].join(" | ");
	fs.writeFileSync(path.join(root, ".agenticdoc", "_workers.parallel"), `# mw-queue:v2\n${row}\n`, "utf8");
}

function writeRoadmap(root: string, status: string): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	const text = [
		"# Roadmap",
		"> generated_at: 2026-09-10T00:00:00+00:00",
		"> goal_mtime: 1789000000000",
		"",
		"## Stage 1: stage-1",
		"> goal: deliver stage 1",
		`> status: ${status}`,
		"> key-status: k1=running",
		"### Keys",
		"| key | role | depends_on |",
		"|-----|------|-----------|",
		"| k1 | worker | - |",
		"",
	].join("\n");
	fs.writeFileSync(path.join(dir, "_roadmap.md"), text, "utf8");
}

const DOCTOR_BLOCKED_PROBE = [
	"import mw_common",
	"project = pathlib.Path(sys.argv[1])",
	"gates = mw_common._doctor_gates(project)",
	'print("JSON:" + json.dumps({"blocked_on_human": bool(gates["blocked_on_human"]), "pending_count": gates["pending_count"]}))',
].join("\n");

const STAGE_PROBE = [
	"import mw_common",
	"from autopilot import conductor, gates as gates_mod",
	"project = pathlib.Path(sys.argv[1])",
	"pending = gates_mod.pending_gates(conductor.gates_dir(project))",
	"stage_status, stage_of_key = conductor._gate_stage_context(project)",
	"now = __import__('time').time()",
	"due = conductor.pending_gate_reminders(pending, [], {}, now, 30, 3, stage_status, stage_of_key)",
	"gates_section = mw_common._doctor_gates(project)",
	'print("JSON:" + json.dumps({"reminders": len(due), "blocked_on_human": bool(gates_section["blocked_on_human"]), "pending_count": gates_section["pending_count"]}))',
].join("\n");

// ── seam 4: AC-001 doctor blocked_on_human ↔ panel same-source quantity ─────

describe("seam AC-001: doctor blocked_on_human and the panel quantity agree", () => {
	function panelSaysBlocked(root: string): boolean {
		const snapshot = readMonitorState(root, Date.now());
		const rendered = renderMonitorLines(snapshot).some((line) => line.includes("BLOCKED_ON_HUMAN"));
		// `blockedOnHuman` is the file-only two-axis truth table; the panel adds
		// `!tickStale`. A fresh-tick fixture makes them identical.
		expect(rendered).toBe(snapshot.blockedOnHuman && !snapshot.autopilot.tickStale);
		return rendered;
	}

	it("pending gate + fresh tick + no in-flight row: panel and doctor both blocked", () => {
		const root = mkdtemp("mwds-t12-boh-");
		writeConfig(root);
		writeGate(root, "gate-0001", 1, 0);
		writeBeat(root, 0);
		const py = runPythonJson(DOCTOR_BLOCKED_PROBE, [root]);
		console.log(
			`[VERIFY] seam T-08 ${path.basename(root)}: panel=${panelSaysBlocked(root)} doctor=${String(py.blocked_on_human)}`,
		);
		expect(panelSaysBlocked(root)).toBe(true);
		expect(py.blocked_on_human).toBe(true);
		expect(py.pending_count).toBe(1);
	});

	it("a stale tick makes both false", () => {
		const root = mkdtemp("mwds-t12-boh-stale-");
		writeConfig(root);
		writeGate(root, "gate-0001", 1, 0);
		writeBeat(root, 6 * 60_000);
		const py = runPythonJson(DOCTOR_BLOCKED_PROBE, [root]);
		expect(panelSaysBlocked(root)).toBe(false);
		expect(py.blocked_on_human).toBe(false);
	});

	it("a non-terminal worker row makes both false", () => {
		const root = mkdtemp("mwds-t12-boh-row-");
		writeConfig(root);
		writeGate(root, "gate-0001", 1, 0);
		writeBeat(root, 0);
		writeQueueRow(root, "t-1", "running");
		const py = runPythonJson(DOCTOR_BLOCKED_PROBE, [root]);
		expect(panelSaysBlocked(root)).toBe(false);
		expect(py.blocked_on_human).toBe(false);
	});
});

// ── seam 5: AC-002 stage terminality ↔ doctor gates section ─────────────────

describe("seam AC-002: T-09 stage suppression and the doctor gates section do not interfere", () => {
	it("a gate on a terminal stage is not reminded, but the doctor still sees it as blocked", () => {
		const root = mkdtemp("mwds-t12-stage-closed-");
		writeRoadmap(root, "closed");
		writeGate(root, "gate-0001", 1, 31);
		writeBeat(root, 0);
		const py = runPythonJson(STAGE_PROBE, [root]);
		console.log(
			`[VERIFY] seam T-09/T-08 closed: reminders=${String(py.reminders)} blocked_on_human=${String(py.blocked_on_human)}`,
		);
		expect(py.reminders).toBe(0);
		expect(py.blocked_on_human).toBe(true);
		expect(py.pending_count).toBe(1);
	});

	it("a gate on a running stage still reminds, and the doctor verdict is unchanged", () => {
		const root = mkdtemp("mwds-t12-stage-running-");
		writeRoadmap(root, "running");
		writeGate(root, "gate-0001", 1, 31);
		writeBeat(root, 0);
		const py = runPythonJson(STAGE_PROBE, [root]);
		expect(py.reminders).toBe(1);
		expect(py.blocked_on_human).toBe(true);
	});
});
