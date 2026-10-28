/**
 * mwgal-t17b-ledger-infra-writes.test.ts — T-17b / key
 * `mw-autopilot-gate-alarm-liveness` (card T-17b-ledger-infra-writes, C-36 4th
 * class: framework infrastructure writes must not be attributed to a worker).
 *
 * The T-12 live incident: worker `mwgal-t12-stage-close-auto` (coding) settled
 * with `未记录写入：_workers.parallel`, although its own `trace.log` contains
 * ZERO `_workers.parallel` hits and the queue file's mtime (19:23:30 local) is
 * AFTER the worker's run window (19:07–19:20 local). It is the launcher's queue.
 * An mtime window therefore cannot attribute a write — only OWNERSHIP can
 * (`change-ledger.ts::INFRA_BASENAMES`). T-21 R-1 narrowed that ownership table
 * to FILE level: the `_autopilot`/`.mw` path-segment exempt no longer exists, so
 * a declared conductor/launcher control-plane file is judged like any other
 * repo path (see the R-1 block below).
 *
 * Required regression corpus (card requirement 5):
 *   1. `_workers.parallel` in the candidate set ⇒ zero findings (T-12 shape);
 *   2. `run.json` / `trace.log` / `serve.meta` in the candidate set ⇒ zero
 *      findings AND visible on the warn-only infra channel (`## Ledger Infra` +
 *      the `[FLOW] ledger-infra` trace line);
 *   3. a NON-infrastructure out-of-scope path stays RED (P-03 counterweight:
 *      `packages/coding-agent/src/out-of-scope.ts` still lands in `extra`);
 *   4. T-17's writeless corpus (`l3-verdict.txt` / `auto-decisions.jsonl` / the
 *      ghost name) still yields zero findings (C-36a not regressed), and the
 *      no-role verdict is unchanged (requirement 4).
 *
 * T-21 R-1 added requirement 6: the conductor's `_autopilot/**` control plane
 * (gates, roadmap, timeline, decision ledger, xkey state) and the launcher's
 * `.mw/**` locks are NOT exempt — declared + existing + unrecorded ⇒ RED.
 *
 * The live corpora at the end replay the two real false reds
 * (`mwgal-t12-stage-close-auto` → `_workers.parallel`;
 * `mwd-t24-orphan-scope-narrowing` → `pm-state.md`).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	diffLedger,
	formatWriteFileEvent,
	INFRA_BASENAMES,
	isInfrastructurePath,
} from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import { readTerminalGaps, writeOutput } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");

const tempDirs: string[] = [];

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

function trace(recorded: readonly string[]): string {
	return recorded.map((file) => formatWriteFileEvent(file)).join("\n");
}

/** Recovery-contract shaped report with a change list (the T-21 fixture form). */
function report(body: readonly string[]): string {
	return ["## 结论", "", "done", "", "## 改动清单", "", ...body, "", "## 残留与未验证", "", "none"].join("\n");
}

function mkproject(): { root: string; trueRoot: string; keyDir: string; taskDir: string; evidenceDir: string } {
	const root = mkdtemp("mwgal-t17b-");
	const trueRoot = path.join(root, ".agenticdoc");
	const keyDir = path.join(trueRoot, "t17bkey");
	const taskDir = path.join(keyDir, "workers", "t17b-worker");
	const evidenceDir = path.join(keyDir, "evidence");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.mkdirSync(evidenceDir, { recursive: true });
	return { root, trueRoot, keyDir, taskDir, evidenceDir };
}

const TASK_KEY = "t17bkey/workers/t17b-worker";

// ── requirement 1: the ownership whitelist ───────────────────────────────────

describe("T-17b requirement 1 — framework infrastructure ownership (T-21 R-1: file level)", () => {
	/** The card's minimum list, at the paths the framework really writes: the
	 * worker's own run record / trace / product, the shared queue + index, and
	 * the two identity mirrors. All are basename-matched. */
	const INFRA_SAMPLES = [
		"_workers.parallel",
		".agenticdoc/_workers.parallel",
		"_index.parallel",
		".agenticdoc/_index.parallel",
		"run.json",
		".agenticdoc/k/workers/t/run.json",
		"trace.log",
		"output.md",
		"report.md",
		"report-adversarial.md",
		"progress.md",
		"worker.log",
		"task.md",
		"serve.meta",
		".mw/serve.meta",
		"pm-state.md",
		"REPORT-ADVERSARIAL.MD",
	];

	/** T-21 R-1: the conductor's audit/control channel and the launcher's locks.
	 * Written only by `mw serve` / the conductor, so a worker declaring one is
	 * the out-of-scope signal the ledger exists to surface — never infra. */
	const CONDUCTOR_CONTROL_SAMPLES = [
		".agenticdoc/_autopilot/timeline.jsonl",
		".agenticdoc/_autopilot/timeline.jsonl.1",
		".agenticdoc/_autopilot/auto-decisions.jsonl",
		".agenticdoc/_autopilot/_roadmap.md",
		".agenticdoc/_autopilot/config.json",
		".agenticdoc/_autopilot/xkey/ledger.json",
		".agenticdoc/_autopilot/gates/gate-0007.md",
		".mw/gates.lock",
		".mw/index.lock",
	];

	const WORKER_SAMPLES = [
		"packages/coding-agent/src/out-of-scope.ts",
		"packages/foo/config.json",
		"packages/multi-workers/launcher.py",
		"scripts/deploy",
		"host/pid",
		"src/a.ts",
	];

	it("worker-run framework files are infrastructure and every repo path is not", () => {
		const missed = INFRA_SAMPLES.filter((p) => !isInfrastructurePath(p));
		const overbroad = WORKER_SAMPLES.filter((p) => isInfrastructurePath(p));
		console.log(
			`[VERIFY] T17b-whitelist infra=${INFRA_SAMPLES.length - missed.length}/${INFRA_SAMPLES.length} overbroad=${overbroad.length} entries=${INFRA_BASENAMES.size}`,
		);
		for (const p of missed) console.log(`  [VERIFY] T17b-whitelist MISSED ${p}`);
		for (const p of overbroad) console.log(`  [VERIFY] T17b-whitelist OVERBROAD ${p}`);
		expect(missed).toEqual([]);
		expect(overbroad).toEqual([]);
		// The basename table itself carries the queue/index/run/trace/product names.
		for (const name of [
			"_workers.parallel",
			"_index.parallel",
			"run.json",
			"trace.log",
			"output.md",
			"report.md",
			"serve.meta",
			"pm-state.md",
		]) {
			expect(INFRA_BASENAMES.has(name)).toBe(true);
		}
	});

	it("T-21 R-1: no conductor control-plane path is infrastructure", () => {
		const exempt = CONDUCTOR_CONTROL_SAMPLES.filter((p) => isInfrastructurePath(p));
		console.log(
			`[VERIFY] T17b-R1-control-plane infra=${exempt.length}/${CONDUCTOR_CONTROL_SAMPLES.length} exempt=[${exempt.join(",")}]`,
		);
		expect(exempt).toEqual([]);
	});

	it("T-21 R-1: a declared + existing gate file is an unrecorded write (RED)", () => {
		// The QG counterexample: a coding worker's `## 改动清单` names its own
		// gate answer while the trace has no write event for it. Before R-1 the
		// `_autopilot` segment swallowed it as infra.
		const project = mkproject();
		const gateRel = ".agenticdoc/_autopilot/gates/gate-0007.md";
		const gateAbs = path.join(project.root, gateRel);
		fs.mkdirSync(path.dirname(gateAbs), { recursive: true });
		fs.writeFileSync(gateAbs, "---\nid: gate-0007\nstatus: approved\n---\n", "utf8");
		const ledger = diffLedger(report([`- ${gateRel} — 直接应答了该 gate`]), trace(["src/other.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17b-R1-gate declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unj=${ledger.unjudgeable}`,
		);
		expect(ledger.declared).toEqual([gateRel]);
		expect(ledger.extra).toEqual([gateRel]);
		expect(ledger.infra).toEqual([]);
		expect(ledger.unresolvable).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("T-21 R-1: declared + existing roadmap / decision ledger / .mw lock are RED too", () => {
		const project = mkproject();
		const declared = [
			".agenticdoc/_autopilot/_roadmap.md",
			".agenticdoc/_autopilot/auto-decisions.jsonl",
			".agenticdoc/_autopilot/timeline.jsonl",
			".agenticdoc/_autopilot/xkey/ledger.json",
			".mw/gates.lock",
		];
		for (const rel of declared) {
			const abs = path.join(project.root, rel);
			fs.mkdirSync(path.dirname(abs), { recursive: true });
			fs.writeFileSync(abs, "fixture\n", "utf8");
		}
		const ledger = diffLedger(report(declared.map((f) => `- ${f} — 控制面`)), trace(["src/other.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(`[VERIFY] T17b-R1-control-red extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}]`);
		expect(ledger.extra).toEqual(declared);
		expect(ledger.infra).toEqual([]);
	});

	it("a bare timeline/ledger name is NOT basename-whitelisted (path-scoped only)", () => {
		// C-36a's T-08 corpus declares a bare `auto-decisions.jsonl` as a READ
		// reference. Matching it by basename would silently change the no-role
		// T-17 verdict; T-21 R-1 removes the `_autopilot` segment rule entirely,
		// so the conductor spelling is not exempt either (requirement 4).
		expect(isInfrastructurePath("auto-decisions.jsonl")).toBe(false);
		expect(isInfrastructurePath("timeline.jsonl")).toBe(false);
		expect(isInfrastructurePath(".agenticdoc/_autopilot/timeline.jsonl")).toBe(false);
		expect(isInfrastructurePath(".agenticdoc/_autopilot/_roadmap.md")).toBe(false);
		console.log("[VERIFY] T17b-whitelist timeline_ledger_not_whitelisted=true");
	});
});

// ── requirement 5.1: the T-12 shape (queue file) ─────────────────────────────

describe("T-17b requirement 5.1 — `_workers.parallel` yields zero findings", () => {
	it("coding: the queue file lands on the infra channel, never in extra", () => {
		const ledger = diffLedger(report(["- `_workers.parallel` — 队列行由 launcher 追加"]), trace(["src/other.ts"]), {
			role: "coding",
		});
		console.log(
			`[VERIFY] T17b-T12 declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unj=${ledger.unjudgeable}`,
		);
		expect(ledger.declared).toEqual(["_workers.parallel"]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual(["_workers.parallel"]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("a whole-table row that merely mentions `_workers.parallel` is not a finding either", () => {
		// The exact T-12 row shape: the first path-shaped token in the row is the
		// referenced queue file, not a declared source file.
		const text = report([
			"| `_stage_close_facts`（`:6292`） | 新增：从 roadmap / `_workers.parallel` / key 目录现算全部 facts |",
		]);
		const ledger = diffLedger(text, trace(["scripts/other.py"]), { role: "coding" });
		console.log(`[VERIFY] T17b-T12-table declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`);
		expect(ledger.declared).toEqual(["_workers.parallel"]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual(["_workers.parallel"]);
	});
});

// ── requirement 5.2: run.json / trace.log / serve.meta ⇒ warn channel ────────

describe("T-17b requirement 5.2 — run/trace/serve metadata → visible warn channel", () => {
	const INFRA = ["run.json", "trace.log", "serve.meta"];

	it("diffLedger: zero findings, all three on the infra channel", () => {
		const ledger = diffLedger(report(INFRA.map((f) => `- ${f} — 框架自有`)), trace(["src/other.ts"]), {
			role: "coding",
		});
		console.log(
			`[VERIFY] T17b-infra declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}]`,
		);
		expect(ledger.declared).toEqual(INFRA);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual(INFRA);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("readTerminalGaps + writeOutput: ok stays true and the section/trace line are visible", () => {
		const project = mkproject();
		fs.writeFileSync(path.join(project.taskDir, "task.md"), "type: coding\n", "utf8");
		fs.writeFileSync(path.join(project.taskDir, "report.md"), report(INFRA.map((f) => `- ${f} — 框架自有`)), "utf8");
		fs.writeFileSync(path.join(project.taskDir, "trace.log"), trace(["src/other.ts"]), "utf8");
		const gaps = readTerminalGaps({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			summary: "done",
			judgeRecovery: false,
		});
		console.log(
			`[VERIFY] T17b-infra-terminal ok=${gaps.ok} unrecorded=[${gaps.unrecordedFiles.join(",")}] infra=[${gaps.infraFiles.join(",")}]`,
		);
		expect(gaps.ok).toBe(true);
		expect(gaps.unrecordedFiles).toEqual([]);
		expect(gaps.infraFiles).toEqual(INFRA);

		writeOutput({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			exitCode: 0,
			summary: "done",
			terminalGaps: gaps,
		});
		const output = fs.readFileSync(path.join(project.taskDir, "output.md"), "utf8");
		const traceText = fs.readFileSync(path.join(project.taskDir, "trace.log"), "utf8");
		expect(output).toContain("## Ledger Infra");
		expect(output).toContain("框架基础设施写入（warn，不计入判定）");
		expect(output).not.toContain("## Ledger Gaps");
		expect(traceText).toContain("ledger-infra count=3");
		// Warn-only: the infra note must not ride the `## Questions` readback line
		// (the PM reads that line as a failure signal).
		expect(output).not.toContain("未记录写入：run.json");
		console.log(
			`[VERIFY] T17b-infra-visible ledger_infra_section=${output.includes("## Ledger Infra")} ledger_gaps=${output.includes("## Ledger Gaps")} trace_line=${/ledger-infra count=3/.test(traceText)}`,
		);
	});

	it("an infra-only declaration on a zero-event trace is green, not unjudgeable", () => {
		const ledger = diffLedger(report(["- trace.log — 框架自有"]), "", { role: "coding" });
		console.log(`[VERIFY] T17b-infra-zero-event extra=[${ledger.extra.join(",")}] unj=${ledger.unjudgeable}`);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual(["trace.log"]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("a mixed zero-event declaration names only the non-infra file as unjudgeable", () => {
		const missing = "packages/coding-agent/src/out-of-scope.ts";
		const project = mkproject();
		// T-17c: the judgeable declaration must exist on disk, otherwise it is
		// warn-only and there is no real write left to reconcile.
		const missingAbs = path.join(project.root, missing);
		fs.mkdirSync(path.dirname(missingAbs), { recursive: true });
		fs.writeFileSync(missingAbs, "// out of scope\n", "utf8");
		const ledger = diffLedger(report([`- ${missing} — 越界新增`, "- _workers.parallel — 框架队列"]), "", {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17b-infra-zero-event-mixed extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unj=${ledger.unjudgeable}`,
		);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual(["_workers.parallel"]);
		expect(ledger.unjudgeable).toBe(true);

		fs.writeFileSync(path.join(project.taskDir, "task.md"), "type: coding\n", "utf8");
		fs.writeFileSync(
			path.join(project.taskDir, "report.md"),
			report([`- ${missing} — 越界新增`, "- _workers.parallel — 框架队列"]),
			"utf8",
		);
		fs.writeFileSync(path.join(project.taskDir, "trace.log"), "", "utf8");
		const gaps = readTerminalGaps({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			summary: "done",
			judgeRecovery: false,
			projectRoot: project.root,
		});
		// The infra path stays off the unjudgeable gap list; only the real write is named.
		expect(gaps.unjudgeableFiles).toEqual([missing]);
		expect(gaps.infraFiles).toEqual(["_workers.parallel"]);
		expect(gaps.ok).toBe(false);
	});
});

// ── requirement 5.3: P-03 counterweight ─────────────────────────────────────

describe("T-17b requirement 5.3 — non-infrastructure out-of-scope writes stay red", () => {
	const MISSING = "packages/coding-agent/src/out-of-scope.ts";

	it("coding: a declared non-infra out-of-scope file is still in extra (mixed with infra)", () => {
		// T-17c: the P-03 counterweight keeps a REAL write red — the fixture file
		// exists on disk, which is exactly the existence discriminator.
		const project = mkproject();
		const missingAbs = path.join(project.root, MISSING);
		fs.mkdirSync(path.dirname(missingAbs), { recursive: true });
		fs.writeFileSync(missingAbs, "// out of scope\n", "utf8");
		const ledger = diffLedger(
			report([`- ${MISSING} — 越界新增`, "- _workers.parallel — 框架队列"]),
			trace(["src/other.ts"]),
			{
				role: "coding",
				projectRoot: project.root,
			},
		);
		console.log(
			`[VERIFY] T17b-P03 declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}]`,
		);
		expect(ledger.declared).toEqual([MISSING, "_workers.parallel"]);
		expect(ledger.extra).toEqual([MISSING]);
		expect(ledger.infra).toEqual(["_workers.parallel"]);
	});

	it("readTerminalGaps: the out-of-scope file makes the verdict not-ok", () => {
		const project = mkproject();
		const missingAbs = path.join(project.root, MISSING);
		fs.mkdirSync(path.dirname(missingAbs), { recursive: true });
		fs.writeFileSync(missingAbs, "// out of scope\n", "utf8");
		fs.writeFileSync(path.join(project.taskDir, "task.md"), "type: coding\n", "utf8");
		fs.writeFileSync(path.join(project.taskDir, "report.md"), report([`- ${MISSING} — 越界新增`]), "utf8");
		fs.writeFileSync(path.join(project.taskDir, "trace.log"), trace(["src/other.ts"]), "utf8");
		const gaps = readTerminalGaps({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			summary: "done",
			judgeRecovery: false,
			projectRoot: project.root,
		});
		console.log(`[VERIFY] T17b-P03-terminal unrecorded=[${gaps.unrecordedFiles.join(",")}] ok=${gaps.ok}`);
		expect(gaps.unrecordedFiles).toEqual([MISSING]);
		expect(gaps.ok).toBe(false);
	});
});

// ── requirement 4/5.4: T-17 is not regressed ─────────────────────────────────

/** The T-08 live shape: a survey report with a prose heading that merely
 * mentions 改动, followed by a change-flavoured list of paths it READ. */
const SURVEY_REPORT = [
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

describe("T-17b requirement 4/5.4 — C-36a writeless corpus and the no-role verdict", () => {
	it("research: the survey corpus still yields zero findings", () => {
		const project = mkproject();
		const ledger = diffLedger(SURVEY_REPORT, trace(["src/a.ts"]), {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: Date.now() - 60_000,
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17b-C36a declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}]`,
		);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("no role: the historical all-roles declaration is unchanged; its off-disk ghosts are warn-only", () => {
		const ledger = diffLedger(SURVEY_REPORT, trace(["src/a.ts"]));
		console.log(
			`[VERIFY] T17b-no-role declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}] infra=[${ledger.infra.join(",")}]`,
		);
		// The declaration extraction is historical (byte-for-byte). T-17c moves
		// the off-disk tokens out of `extra` into the visible warn channel: a path
		// that is not on disk cannot be a write.
		expect(ledger.declared).toEqual(["auto-decisions.jsonl", "gates.pending", "ghost/namespace.md"]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unresolvable).toEqual(["auto-decisions.jsonl", "gates.pending", "ghost/namespace.md"]);
		expect(ledger.infra).toEqual([]);
	});
});

// ── live corpora (skipped when the run dirs are absent) ──────────────────────

describe("T-17b live corpus — the two real false reds reconcile green", () => {
	const cases = [
		{
			dir: path.join(
				REPO_ROOT,
				".agenticdoc",
				"mw-autopilot-gate-alarm-liveness",
				"workers",
				"mwgal-t12-stage-close-auto",
			),
			role: "coding",
			expected: "_workers.parallel",
		},
		{
			dir: path.join(REPO_ROOT, ".agenticdoc", "mw-dispatch-card-gate", "workers", "mwd-t24-orphan-scope-narrowing"),
			role: "coding",
			expected: "pm-state.md",
		},
	];

	it("each real report moves its infra item from extra to infra", () => {
		let checked = 0;
		for (const c of cases) {
			const reportPath = path.join(c.dir, "report.md");
			const tracePath = path.join(c.dir, "trace.log");
			if (!fs.existsSync(reportPath) || !fs.existsSync(tracePath)) continue;
			const ledger = diffLedger(fs.readFileSync(reportPath, "utf8"), fs.readFileSync(tracePath, "utf8"), {
				role: c.role,
			});
			console.log(
				`[VERIFY] T17b-corpus ${path.basename(c.dir)} extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}]`,
			);
			expect(ledger.extra).not.toContain(c.expected);
			expect(ledger.infra).toContain(c.expected);
			checked += 1;
		}
		if (checked === 0) console.log("[VERIFY] T17b-corpus unavailable — skipped");
	});
});
