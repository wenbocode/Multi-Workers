/**
 * mwgal-t21-qg-fixes.test.ts — T-21 / key `mw-autopilot-gate-alarm-liveness`
 * (card T-21-qg-fixes-ts): the three TS-side adversarial-QG defects.
 *
 *   R-1 (high, constructible) — `change-ledger.ts` exempted whole trees
 *     (`INFRA_DIR_SEGMENTS = ["_autopilot", ".mw"]`), so a coding worker whose
 *     `## 改动清单` answered its own gate (`.agenticdoc/_autopilot/gates/
 *     gate-0007.md`) with NO trace write was classified infrastructure and
 *     rendered green. The exemption is now FILE-level (`INFRA_BASENAMES` + the
 *     basename regexes): an existing control-plane file the trace never recorded
 *     is a real out-of-scope write (RED).
 *   R-2 (medium) — `monitor.ts` rendered `gates: 0 pending` for
 *     `queueState="partial"` with zero readable pending gates, indistinguishable
 *     from "there really are no gates". The partial branch now also fires with
 *     nothing readable and carries an explicit failure COUNT + samples.
 *   R-3 (medium) — `status-model.ts::listGates` swallowed every `readdir`
 *     failure (`catch { return { gates: [], errors: [] } }`), so
 *     `/autopilot status` printed a silent `0 pending` for an unreadable queue.
 *     Non-ENOENT failures are errors now; an absent/empty directory stays a
 *     legitimate empty queue.
 *
 * Locked contracts this file must NOT disturb: the `reason` / DRIFT / age
 * triple and the `+N` trace in the pending-gate fit ladder, the exact
 * `GateView` shape (`autopilot-console.test.ts`), and the AC-011 config key set.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	type MonitorSnapshot,
	readMonitorState,
	renderMonitorLines,
} from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import {
	DEFAULT_CONFIG,
	deriveStatusModel,
	gatesDir,
	listGates,
	renderStatusText,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import {
	diffLedger,
	formatWriteFileEvent,
	isInfrastructurePath,
} from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import { readTerminalGaps, writeOutput } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const NOW_MS = Date.parse("2026-10-13T12:00:00+00:00");
const LINE_MAX = 110;

const tempDirs: string[] = [];

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

/** A throwaway project root with the key/task layout the ledger expects. */
function mkproject(): { root: string; trueRoot: string; keyDir: string; taskDir: string; evidenceDir: string } {
	const root = mkdtemp("mwgal-t21-");
	const trueRoot = path.join(root, ".agenticdoc");
	const keyDir = path.join(trueRoot, "t21key");
	const taskDir = path.join(keyDir, "workers", "t21-worker");
	const evidenceDir = path.join(keyDir, "evidence");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.mkdirSync(evidenceDir, { recursive: true });
	return { root, trueRoot, keyDir, taskDir, evidenceDir };
}

const TASK_KEY = "t21key/workers/t21-worker";

function trace(recorded: readonly string[]): string {
	return recorded.map((file) => formatWriteFileEvent(file)).join("\n");
}

/** Recovery-contract shaped report with a change list. */
function report(body: readonly string[]): string {
	return ["## 结论", "", "done", "", "## 改动清单", "", ...body, "", "## 残留与未验证", "", "none"].join("\n");
}

function createFile(root: string, rel: string, body = "// fixture\n"): string {
	const abs = path.join(root, rel);
	fs.mkdirSync(path.dirname(abs), { recursive: true });
	fs.writeFileSync(abs, body, "utf8");
	return abs;
}

/** A minimal valid pending gate file (the monitor's lenient frontmatter scan). */
function writeGate(root: string, id: string): void {
	const dir = gatesDir(root);
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, `${id}.md`),
		[
			"---",
			`id: ${id}`,
			"kind: stalled",
			"stage: 1",
			"key: k1",
			"created_at: 2026-10-13T11:00:00+00:00",
			"created_by: conductor",
			"question: 'Proceed?'",
			"context_refs:",
			"  - .agenticdoc/_autopilot/_roadmap.md",
			"status: pending",
			"---",
			"",
			`# Gate ${id}`,
			"",
		].join("\n"),
		"utf8",
	);
}

// ── R-1: the exemption is file-level; the conductor control plane is judgeable ─

describe("T-21 R-1 — infrastructure exemption is file-level only", () => {
	it("the QG counterexample (a declared existing gate file) is RED", () => {
		const project = mkproject();
		const gateRel = ".agenticdoc/_autopilot/gates/gate-0007.md";
		createFile(project.root, gateRel, "---\nid: gate-0007\nstatus: approved\n---\n");
		const ledger = diffLedger(report([`- ${gateRel} — 直接应答了该 gate`]), trace(["src/other.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T21-R1-gate declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}] unj=${ledger.unjudgeable}`,
		);
		expect(ledger.declared).toEqual([gateRel]);
		expect(ledger.extra).toEqual([gateRel]);
		expect(ledger.infra).toEqual([]);
		expect(ledger.unresolvable).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("the same gate file rides `## Ledger Gaps` end-to-end (never `## Ledger Infra`)", () => {
		const project = mkproject();
		const gateRel = ".agenticdoc/_autopilot/gates/gate-0007.md";
		createFile(project.root, gateRel, "---\nid: gate-0007\nstatus: approved\n---\n");
		fs.writeFileSync(path.join(project.taskDir, "task.md"), "type: coding\n", "utf8");
		fs.writeFileSync(path.join(project.taskDir, "report.md"), report([`- ${gateRel} — 应答`]), "utf8");
		fs.writeFileSync(path.join(project.taskDir, "trace.log"), trace(["src/other.ts"]), "utf8");
		const gaps = readTerminalGaps({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			summary: "done",
			judgeRecovery: false,
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T21-R1-terminal ok=${gaps.ok} unrecorded=[${gaps.unrecordedFiles.join(",")}] infra=[${gaps.infraFiles.join(",")}]`,
		);
		expect(gaps.ok).toBe(false);
		expect(gaps.unrecordedFiles).toEqual([gateRel]);
		expect(gaps.infraFiles).toEqual([]);

		writeOutput({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			exitCode: 2,
			summary: "done",
			questions: "recovery-incomplete",
			terminalGaps: gaps,
		});
		const output = fs.readFileSync(path.join(project.taskDir, "output.md"), "utf8");
		expect(output).toContain("## Ledger Gaps");
		expect(output).not.toContain("## Ledger Infra");
		expect(output).toContain(gateRel);
	});

	it("the whole conductor control plane and the launcher locks are judgeable", () => {
		const samples = [
			".agenticdoc/_autopilot/gates/gate-0007.md",
			".agenticdoc/_autopilot/_roadmap.md",
			".agenticdoc/_autopilot/auto-decisions.jsonl",
			".agenticdoc/_autopilot/timeline.jsonl",
			".agenticdoc/_autopilot/timeline.jsonl.1",
			".agenticdoc/_autopilot/config.json",
			".agenticdoc/_autopilot/xkey/ledger.json",
			".agenticdoc/_autopilot/xkey/tickets/xkey-1.md",
			".mw/gates.lock",
			".mw/index.lock",
			".mw/mw.pid",
		];
		const exempt = samples.filter((p) => isInfrastructurePath(p));
		console.log(`[VERIFY] T21-R1-control exempt=${exempt.length}/${samples.length} samples=[${exempt.join(",")}]`);
		expect(exempt).toEqual([]);
	});

	it("non-regression: serve.meta / _index.parallel (T-16 terminal items) stay infra", () => {
		// The two framework-written files from the T-16 terminal's four false
		// positives. Narrowing must not turn them red again.
		const project = mkproject();
		createFile(project.root, ".mw/serve.meta");
		createFile(project.root, ".agenticdoc/_index.parallel");
		const ledger = diffLedger(
			report(["- .mw/serve.meta — 框架写", "- .agenticdoc/_index.parallel — 框架队列"]),
			trace(["src/other.ts"]),
			{ role: "coding", projectRoot: project.root },
		);
		console.log(
			`[VERIFY] T21-R1-infra-nonregression extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual([".mw/serve.meta", ".agenticdoc/_index.parallel"]);
		expect(ledger.unresolvable).toEqual([]);
	});

	it("infra ownership still wins over the existence probe (absent infra path is infra)", () => {
		const project = mkproject();
		const ledger = diffLedger(report(["- _workers.parallel — 框架队列", "- serve.meta — 框架写"]), "", {
			role: "coding",
			projectRoot: project.root,
		});
		expect(ledger.infra).toEqual(["_workers.parallel", "serve.meta"]);
		expect(ledger.unresolvable).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("the T-17/T-17c no-role survey corpus is byte-identical (bare ledger name untouched)", () => {
		const project = mkproject();
		const survey = [
			"# DRQ survey",
			"",
			"## 结论",
			"本轮普查读取 `l3-verdict.txt`、`auto-decisions.jsonl`，并核对 `gates.pending`（磁盘不存在）。",
			"",
			"### 结论 6｜可度量：改动前后的期望变化与运行期验收数字",
			"- 自动批准占比 = `auto-decisions.jsonl` 中 phase==decide 的行数。",
			"- 等待时长 = `gates.pending[].waited_s`。",
			"- 复查见 `ghost/namespace.md`（本卡不存在）。",
			"",
			"## 证据",
			"survey only.",
			"",
			"## 残留与未验证",
			"none.",
			"",
			"## 上下文来源",
			"spec.md:1",
		].join("\n");
		const ledger = diffLedger(survey, trace(["src/a.ts"]), { role: "coding", projectRoot: project.root });
		console.log(
			`[VERIFY] T21-R1-corpus declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.declared).toEqual(["auto-decisions.jsonl", "gates.pending", "ghost/namespace.md"]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual([]);
		expect(ledger.unresolvable).toEqual(["auto-decisions.jsonl", "gates.pending", "ghost/namespace.md"]);
	});

	it("live corpus: the T-16 terminal ledger still reconciles (extra empty, infra keeps serve.meta/index)", () => {
		const dir = path.join(
			REPO_ROOT,
			".agenticdoc",
			"mw-autopilot-gate-alarm-liveness",
			"workers",
			"mwgal-t16-synthetic-claim",
		);
		const reportPath = path.join(dir, "report.md");
		const tracePath = path.join(dir, "trace.log");
		if (!fs.existsSync(reportPath) || !fs.existsSync(tracePath)) {
			console.log("[VERIFY] T21-R1-live-corpus unavailable — skipped");
			return;
		}
		const ledger = diffLedger(fs.readFileSync(reportPath, "utf8"), fs.readFileSync(tracePath, "utf8"), {
			role: "coding",
			projectRoot: REPO_ROOT,
		});
		console.log(
			`[VERIFY] T21-R1-live-corpus extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toContain(".mw/serve.meta");
		expect(ledger.infra).toContain(".agenticdoc/_index.parallel");
		expect(ledger.unresolvable).toContain("update_index.py");
		expect(ledger.unresolvable).toContain("os.replace");
	});
});

// ── R-2: partial + zero readable gates is "cannot read", not "0 pending" ──────

describe("T-21 R-2 — partial queue with zero readable gates is never `0 pending`", () => {
	/** Hand-built snapshot: the pure-renderer minimal repro of the QG finding
	 * (one gate listed on disk, its read failed, nothing else pending). */
	function partialZeroSnapshot(queueError: string, queueFailures?: string[]): MonitorSnapshot {
		return {
			serve: { running: false, pid: null, stale: false, staleDetail: "", upMs: null },
			conductor: { pid: null, alive: false, enabled: false, paused: false, everEnabled: false },
			autopilot: {
				enabled: true,
				everEnabled: true,
				tickSeq: null,
				tickAgeMs: null,
				tickStale: false,
				slotsUsed: 0,
				slotsMax: 2,
				stallTicks: 5,
				keys: [],
				stalls: [],
			},
			workers: [],
			gates: [],
			queueState: "partial",
			queueError,
			queueFailures,
			blockedOnHuman: false,
		};
	}

	it("renders the unreadable marker with a count and the sample, never `0 pending`", () => {
		const snap = partialZeroSnapshot("gate-0002.md: EACCES");
		const panel = renderMonitorLines(snap).join("\n");
		console.log(
			`[VERIFY] T21-R2-partial-zero\n${panel
				.split("\n")
				.filter((l) => l.startsWith("gates:"))
				.join("\n")}`,
		);
		expect(panel).toContain("gate-queue-unreadable");
		expect(panel).toContain("1 unreadable: gate-0002.md: EACCES");
		expect(panel).not.toContain("gates: 0 pending");
	});

	it("readMonitorState: two failed gate reads ⇒ partial, 0 readable, count=2, line <= 110", () => {
		const root = mkdtemp("mwgal-t21-r2-");
		writeGate(root, "gate-0001");
		writeGate(root, "gate-0002");
		// Injection seam: a per-file read failure cannot be constructed portably
		// (Windows has no chmod read denial), so the seam plays the EACCES role.
		const snap = readMonitorState(root, NOW_MS, {
			readGateText: () => {
				throw "EBUSY";
			},
		});
		const gateLines = renderMonitorLines(snap).filter((l) => l.startsWith("gates:"));
		console.log(
			`[VERIFY] T21-R2-collect state=${snap.queueState} gates=${snap.gates.length} failures=${(snap.queueFailures ?? []).length} line=${gateLines[0]}`,
		);
		expect(snap.queueState).toBe("partial");
		expect(snap.gates).toEqual([]);
		expect(snap.queueFailures).toEqual(["gate-0001.md: EBUSY", "gate-0002.md: EBUSY"]);
		expect(snap.queueError).toBe("2 files unreadable: gate-0001.md: EBUSY; gate-0002.md: EBUSY");
		const line = gateLines[0] ?? "";
		expect(line).toContain("gate-queue-unreadable");
		expect(line).toContain("2 unreadable: gate-0001.md: EBUSY; gate-0002.md: EBUSY");
		expect(line).not.toContain("0 pending");
		expect(line.length).toBeLessThanOrEqual(LINE_MAX);
	});

	it("the count survives width pressure: a long sample still states HOW MANY are unreadable", () => {
		const long = `${"x".repeat(400)}`;
		const snap = partialZeroSnapshot(`${long}: EACCES`, [`${long}: EACCES`]);
		const line = renderMonitorLines(snap).find((l) => l.startsWith("gates:")) ?? "";
		console.log(`[VERIFY] T21-R2-truncated len=${line.length} line=${line.slice(0, 60)}…`);
		expect(line.length).toBeLessThanOrEqual(LINE_MAX);
		expect(line).toContain("gate-queue-unreadable");
		expect(line).toContain("1 unreadable");
	});

	it("with one readable gate the existing partial note is unchanged", () => {
		const root = mkdtemp("mwgal-t21-r2-mixed-");
		writeGate(root, "gate-0001");
		writeGate(root, "gate-0002");
		const snap = readMonitorState(root, NOW_MS, {
			readGateText: (file) => {
				if (file.endsWith("gate-0002.md")) throw "EACCES";
				return fs.readFileSync(file, "utf8");
			},
		});
		const panel = renderMonitorLines(snap).join("\n");
		console.log(`[VERIFY] T21-R2-mixed state=${snap.queueState} gates=${snap.gates.length}`);
		expect(snap.queueState).toBe("partial");
		expect(snap.gates.map((g) => g.id)).toEqual(["gate-0001"]);
		expect(panel).toContain("gate-queue-unreadable");
		expect(panel).toContain("1 unreadable: gate-0002.md: EACCES");
		// The reason/DRIFT/age triple is untouched by this fix.
		expect(panel).toContain("reason=");
		expect(panel).toContain("age=");
	});

	it("an empty gates directory / an absent directory are legitimate `0 pending`", () => {
		const emptyDir = mkdtemp("mwgal-t21-r2-empty-");
		fs.mkdirSync(gatesDir(emptyDir), { recursive: true });
		const emptySnap = readMonitorState(emptyDir, NOW_MS);
		expect(emptySnap.queueState).toBe("ok");
		expect(emptySnap.queueFailures).toEqual([]);
		expect(renderMonitorLines(emptySnap).join("\n")).toContain("gates: 0 pending");
		expect(renderMonitorLines(emptySnap).join("\n")).not.toContain("gate-queue-unreadable");

		const absentDir = mkdtemp("mwgal-t21-r2-absent-");
		const absentSnap = readMonitorState(absentDir, NOW_MS);
		expect(absentSnap.queueState).toBe("ok");
		expect(renderMonitorLines(absentSnap).join("\n")).toContain("gates: 0 pending");
		console.log("[VERIFY] T21-R2-legit-zero empty_and_absent=ok");
	});

	it("the unreadable directory case still renders the marker (regression)", () => {
		const root = mkdtemp("mwgal-t21-r2-unreadable-");
		fs.mkdirSync(path.dirname(gatesDir(root)), { recursive: true });
		fs.writeFileSync(gatesDir(root), "not a directory", "utf8");
		const snap = readMonitorState(root, NOW_MS);
		const panel = renderMonitorLines(snap).join("\n");
		console.log(`[VERIFY] T21-R2-unreadable state=${snap.queueState}`);
		expect(snap.queueState).toBe("unreadable");
		expect(snap.queueFailures ?? []).toHaveLength(1);
		expect(panel).toContain("gate-queue-unreadable");
		expect(panel).not.toContain("gates: 0 pending");
		for (const line of renderMonitorLines(snap)) expect(line.length).toBeLessThanOrEqual(LINE_MAX);
	});
});

// ── R-3: readdir errors are surfaced, empty/absent dirs stay legitimately empty ─

describe("T-21 R-3 — listGates does not swallow a non-ENOENT readdir failure", () => {
	it("the gates path being a plain file is an error, not an empty queue", () => {
		const root = mkdtemp("mwgal-t21-r3-file-");
		fs.mkdirSync(path.dirname(gatesDir(root)), { recursive: true });
		fs.writeFileSync(gatesDir(root), "not a directory", "utf8");
		const scan = listGates(root);
		console.log(
			`[VERIFY] T21-R3-listGates gates=${scan.gates.length} errors=${scan.errors.length} first=${scan.errors[0]}`,
		);
		expect(scan.gates).toEqual([]);
		expect(scan.errors.length).toBe(1);
		expect(scan.errors[0]).toContain(gatesDir(root));
	});

	it("/autopilot status surfaces the warning (human text) and keeps the JSON shard locked", () => {
		const root = mkdtemp("mwgal-t21-r3-status-");
		fs.mkdirSync(path.dirname(gatesDir(root)), { recursive: true });
		fs.writeFileSync(gatesDir(root), "not a directory", "utf8");
		const result = deriveStatusModel(root, NOW_MS);
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		const warnings = result.model.warnings.filter((w) => w.includes(gatesDir(root)));
		console.log(
			`[VERIFY] T21-R3-status warnings=${result.model.warnings.length} gate_warning=${warnings.length} status_gates=${result.model.status.gates.length}`,
		);
		expect(warnings.length).toBe(1);
		const text = renderStatusText(result.model);
		expect(text).toContain(`warning: ${warnings[0]}`);
		expect(text).toContain("gates: 0 total, 0 pending");
	});

	it("an empty directory and an absent directory are legitimate zero errors (0 pending)", () => {
		const emptyDir = mkdtemp("mwgal-t21-r3-empty-");
		fs.mkdirSync(gatesDir(emptyDir), { recursive: true });
		expect(listGates(emptyDir)).toEqual({ gates: [], errors: [] });
		const absentDir = mkdtemp("mwgal-t21-r3-absent-");
		expect(listGates(absentDir)).toEqual({ gates: [], errors: [] });
		const emptyStatus = deriveStatusModel(emptyDir, NOW_MS);
		expect(emptyStatus.ok).toBe(true);
		if (emptyStatus.ok) {
			expect(renderStatusText(emptyStatus.model)).toContain("gates: 0 total, 0 pending");
			expect(emptyStatus.model.warnings.filter((w) => w.includes(gatesDir(emptyDir)))).toEqual([]);
		}
		console.log("[VERIFY] T21-R3-legit-zero empty_and_absent=clean");
	});

	it("a corrupt gate file still surfaces as a parse error (regression)", () => {
		const root = mkdtemp("mwgal-t21-r3-corrupt-");
		fs.mkdirSync(gatesDir(root), { recursive: true });
		fs.writeFileSync(path.join(gatesDir(root), "gate-0001.md"), "not a gate\n", "utf8");
		const scan = listGates(root);
		console.log(`[VERIFY] T21-R3-corrupt errors=${scan.errors.length}`);
		expect(scan.gates).toEqual([]);
		expect(scan.errors.length).toBe(1);
	});
});

// ── contracts this card must not move ────────────────────────────────────────

describe("T-21 contract locks", () => {
	it("GateView is unchanged: exactly {id, kind, status, ageMs} on the status JSON", () => {
		const root = mkdtemp("mwgal-t21-lock-");
		writeGate(root, "gate-0001");
		const result = deriveStatusModel(root, NOW_MS);
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		console.log(`[VERIFY] T21-lock-gateview keys=[${Object.keys(result.model.status.gates[0] ?? {}).join(",")}]`);
		expect(Object.keys(result.model.status.gates[0] ?? {}).sort()).toEqual(["ageMs", "id", "kind", "status"]);
	});

	it("one config key was added by MDC M-03: the default set moves to 21", () => {
		console.log(`[VERIFY] T21-lock-config keys=${Object.keys(DEFAULT_CONFIG).length}`);
		expect(Object.keys(DEFAULT_CONFIG)).toHaveLength(21);
	});
});
