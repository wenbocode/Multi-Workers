/**
 * mwgal-t17-ledger-role-aware.test.ts — T-17 / key
 * `mw-autopilot-gate-alarm-liveness` (card T-17-ledger-role-aware).
 *
 * Four measured ledger defects, each a required regression corpus here:
 *
 *   C-36a 过判 — a writeless role's report is a survey full of paths it READ.
 *     The broad `改动`/`变更` heading aliases turned a prose section into a
 *     declaration body (`结论 6｜可度量：改动前后的预期变化…`), so the reader's
 *     references (`l3-verdict.txt`, `auto-decisions.jsonl`, a nonexistent
 *     `gates.pending`) were charged as writes (T-08 live false red).
 *   C-36b 漏判 — a writeless role's deliverable lives outside taskDir
 *     (`<key>/evidence/…`). Zero `[WRITE_FILE]` events made it invisible
 *     (`writes=none`, 8 live cases). The disk channel reconciles it.
 *   C-36c 路径污染 — unexpanded shell variables (`$dir`, `${HOME}`, `%VAR%`)
 *     must be `malformed` (warn-only), never declared/recorded.
 *   C-36d 系统写入误归因 — a token inside a longer identifier
 *     (`gate-writer.ts`) must not produce a bogus `r.ts` declaration.
 *
 * The P-03 counterweight is explicit: a real coding-role out-of-scope write
 * stays red, and a writeless `改动清单` claim stays red too — the role split is
 * not a blanket exemption.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	collectMalformedCandidates,
	diffLedger,
	formatWriteFileEvent,
	isWritelessLedgerRole,
	WRITELESS_LEDGER_ROLES,
} from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import { readTerminalGaps, writeOutput } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import { isWritelessRole, REGISTERED_WORKER_TYPES } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

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
	const root = mkdtemp("mwgal-t17-");
	const trueRoot = path.join(root, ".agenticdoc");
	const keyDir = path.join(trueRoot, "t17key");
	const taskDir = path.join(keyDir, "workers", "t17-worker");
	// The deliverable channel root is `<key>/evidence` (not the research subdir):
	// that is exactly what `output-writer.ts::deliverableDir` passes.
	const evidenceDir = path.join(keyDir, "evidence");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.mkdirSync(path.join(evidenceDir, "research"), { recursive: true });
	return { root, trueRoot, keyDir, taskDir, evidenceDir };
}

const TASK_KEY = "t17key/workers/t17-worker";

/** Create a declared fixture path under a temp project root (T-17c: the P-03
 * counterweight needs a real file — existence is the discriminator). */
function createDeclared(root: string, rel: string): string {
	const abs = path.join(root, rel);
	fs.mkdirSync(path.dirname(abs), { recursive: true });
	fs.writeFileSync(abs, "// out of scope\n", "utf8");
	return abs;
}

// ── C-36a: the false-positive corpus (read references are not writes) ────────

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

describe("C-36a — writeless role classifies survey paths as read references", () => {
	it("research: a survey report has zero findings (the T-08 false positive is gone)", () => {
		const project = mkproject();
		const before = diffLedger(SURVEY_REPORT, trace(["src/a.ts"]));
		const after = diffLedger(SURVEY_REPORT, trace(["src/a.ts"]), {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: Date.now() - 60_000,
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17-C36a before_extra=[${before.extra.join(",")}] before_unresolvable=[${before.unresolvable.join(",")}] after_declared=[${after.declared.join(",")}] after_extra=[${after.extra.join(",")}]`,
		);
		// Old behaviour (no role): the prose section is a declaration body. T-17c:
		// the ghost paths are not on disk, so they are warn-only, never red.
		expect(before.declared).toEqual(["auto-decisions.jsonl", "gates.pending", "ghost/namespace.md"]);
		expect(before.extra).toEqual([]);
		expect(before.unresolvable).toEqual(["auto-decisions.jsonl", "gates.pending", "ghost/namespace.md"]);
		// Role-aware: nothing is declared, so nothing is red.
		expect(after.declared).toEqual([]);
		expect(after.extra).toEqual([]);
		expect(after.unjudgeable).toBe(false);
		for (const item of ["l3-verdict.txt", "auto-decisions.jsonl", "gates.pending", "ghost/namespace.md"]) {
			expect(after.declared).not.toContain(item);
		}
	});

	it("role source: the ledger's writeless set is locked to the runtime allowlist", () => {
		const runtimeWriteless = REGISTERED_WORKER_TYPES.filter((type) => isWritelessRole(type)).sort();
		expect([...WRITELESS_LEDGER_ROLES].sort()).toEqual(runtimeWriteless);
		expect(isWritelessLedgerRole("research")).toBe(true);
		expect(isWritelessLedgerRole("review")).toBe(true);
		expect(isWritelessLedgerRole("coding")).toBe(false);
		expect(isWritelessLedgerRole(undefined)).toBe(false);
		console.log(`[VERIFY] T17-role research/review writeless=true runtime_set=[${runtimeWriteless.join(",")}]`);
	});
});

// ── P-03: real declared-but-unrecorded writes stay red ───────────────────────

describe("P-03 — the role split does not loosen a real write declaration", () => {
	const MISSING = "packages/coding-agent/src/out-of-scope.ts";

	it("coding role: a declared-but-unrecorded out-of-scope write is still red", () => {
		// T-17c: the P-03 counterweight is about a REAL write, so the fixture file
		// must exist on disk — existence is exactly the discriminator under test.
		const project = mkproject();
		createDeclared(project.root, MISSING);
		const ledger = diffLedger(report([`- ${MISSING} — 新增`]), trace(["packages/other/z.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(`[VERIFY] T17-P03-coding declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`);
		expect(ledger.declared).toEqual([MISSING]);
		expect(ledger.extra).toEqual([MISSING]);
		expect(ledger.unresolvable).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("writeless role: an explicit 改动清单 claim is still red", () => {
		const project = mkproject();
		createDeclared(project.root, MISSING);
		const ledger = diffLedger(report([`- ${MISSING} — 新增`]), trace(["packages/other/z.ts"]), {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: Date.now() - 60_000,
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17-P03-research declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`,
		);
		expect(ledger.declared).toEqual([MISSING]);
		expect(ledger.extra).toEqual([MISSING]);
	});

	it("writeless role: a zero-event trace with a 改动清单 declaration stays unjudgeable (T-12/F-04)", () => {
		const project = mkproject();
		// T-17c: an existing declared path is a real write to reconcile, so the
		// empty trace is unjudgeable (a nonexistent one would be warn-only).
		createDeclared(project.root, MISSING);
		const ledger = diffLedger(report([`- ${MISSING} — 新增`]), "", {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: Date.now() - 60_000,
			projectRoot: project.root,
		});
		expect(ledger.recorded).toEqual([]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unjudgeable).toBe(true);
	});
});

// ── C-36c: path hygiene (variables and unparseable tokens) ───────────────────

describe("C-36c — unexpanded variables and unparseable paths are malformed only", () => {
	const HYGIENE_REPORT = report([
		"- path=$dir — 未展开变量",
		"- path=$env:TEMPfoo.py — 未展开变量",
		// biome-ignore lint/suspicious/noTemplateCurlyInString: variable-residue fixture — `${...}` is literal report text, not a template
		"- ${HOME}/x.ts — 未展开变量",
		"- %TEMP%\\note.md — 未展开变量",
		"- src/ok.ts — 真实声明",
	]);

	it("variable tokens are malformed, visible, and never declared or recorded", () => {
		const project = mkproject();
		const malformed = collectMalformedCandidates(HYGIENE_REPORT);
		const ledger = diffLedger(HYGIENE_REPORT, trace(["src/ok.ts"]), {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: Date.now() - 60_000,
			projectRoot: project.root,
		});
		console.log(`[VERIFY] T17-C36c malformed=[${malformed.join(",")}] declared=[${ledger.declared.join(",")}]`);
		// biome-ignore lint/suspicious/noTemplateCurlyInString: asserting on literal `${...}` report residue
		for (const token of ["path=$dir", "path=$env:TEMPfoo.py", "${HOME}/x.ts"]) {
			expect(malformed).toContain(token);
		}
		// The real declaration survives; the variable residue never does.
		expect(ledger.declared).toEqual(["src/ok.ts"]);
		expect(ledger.extra).toEqual([]);
		// biome-ignore lint/suspicious/noTemplateCurlyInString: asserting on literal `${...}` report residue
		for (const token of ["$dir", "$env", "${HOME}"]) {
			expect(ledger.declared.some((file) => file.includes(token))).toBe(false);
			expect(ledger.recorded.some((file) => file.includes(token))).toBe(false);
		}
	});

	it("malformed samples are surfaced as a warn-only product section, never a gap", () => {
		const project = mkproject();
		fs.writeFileSync(path.join(project.taskDir, "task.md"), "type: research\n", "utf8");
		fs.writeFileSync(path.join(project.taskDir, "report.md"), HYGIENE_REPORT, "utf8");
		fs.writeFileSync(path.join(project.taskDir, "trace.log"), trace(["src/ok.ts"]), "utf8");
		const gaps = readTerminalGaps({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			summary: "done",
			judgeRecovery: false,
		});
		expect(gaps.ok).toBe(true);
		expect(gaps.unrecordedFiles).toEqual([]);
		expect(gaps.malformedFiles.length).toBeGreaterThan(0);

		writeOutput({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			exitCode: 0,
			summary: "done",
			terminalGaps: gaps,
		});
		const output = fs.readFileSync(path.join(project.taskDir, "output.md"), "utf8");
		console.log(
			`[VERIFY] T17-C36c-warn malformed=${gaps.malformedFiles.length} section=${output.includes("## Ledger Malformed")}`,
		);
		expect(output).toContain("## Ledger Malformed");
		expect(output).toContain("格式异常（warn，不影响判定）");
		expect(output).not.toContain("## Ledger Gaps");
	});
});

// ── C-36d: no phantom declaration from inside a longer identifier ────────────

describe("C-36d — a write verb inside an identifier does not declare `r.ts`", () => {
	it("gate-writer.ts in prose yields no phantom declaration", () => {
		const text = report(["- 改 `gate-writer.ts` 的写入逻辑，见 `pm-orchestrator.ts`"]);
		const ledger = diffLedger(text, trace(["packages/other/z.ts"]));
		console.log(`[VERIFY] T17-C36d declared=[${ledger.declared.join(",")}]`);
		expect(ledger.declared).not.toContain("r.ts");
		expect(ledger.extra).not.toContain("r.ts");
	});
});

// ── C-36b: the deliverable channel outside taskDir is reconciled ─────────────

describe("C-36b — a writeless deliverable outside taskDir is declared + recorded", () => {
	function deliverableReport(rel: string): string {
		return [
			"## 结论",
			`唯一证据文件：\`${rel}\`（本文件）。`,
			"",
			"## 证据",
			"see the deliverable.",
			"",
			"## 残留与未验证",
			"none.",
			"",
			"## 上下文来源",
			"spec.md:1",
		].join("\n");
	}

	it("a fresh file under <key>/evidence is declared and recorded (no more writes=none blindness)", () => {
		const project = mkproject();
		const startedMs = Date.now() - 60_000;
		const abs = path.join(project.evidenceDir, "research", "spec-t17-20261013.md");
		fs.writeFileSync(abs, "# deliverable\n", "utf8");
		const reportText = deliverableReport("evidence/research/spec-t17-20261013.md");
		const ledger = diffLedger(reportText, "", {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: startedMs,
			projectRoot: project.root,
		});
		const rel = ".agenticdoc/t17key/evidence/research/spec-t17-20261013.md";
		console.log(
			`[VERIFY] T17-C36b declared=[${ledger.declared.join(",")}] recorded=[${ledger.recorded.join(",")}] extra=[${ledger.extra.join(",")}] unj=${ledger.unjudgeable}`,
		);
		expect(ledger.declared).toEqual([rel]);
		expect(ledger.recorded).toEqual([rel]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("an absolute-path reference resolves to the same deliverable", () => {
		const project = mkproject();
		const startedMs = Date.now() - 60_000;
		const abs = path.join(project.evidenceDir, "research", "spec-abs-20261013.md");
		fs.writeFileSync(abs, "# deliverable\n", "utf8");
		const ledger = diffLedger(deliverableReport(abs.replace(/\\/g, "/")), "", {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: startedMs,
			projectRoot: project.root,
		});
		expect(ledger.declared).toEqual([".agenticdoc/t17key/evidence/research/spec-abs-20261013.md"]);
		expect(ledger.extra).toEqual([]);
	});

	it("a stale referenced file is a read reference, not this run's deliverable", () => {
		const project = mkproject();
		const startedMs = Date.now();
		const abs = path.join(project.evidenceDir, "research", "spec-old-20261013.md");
		fs.writeFileSync(abs, "# old\n", "utf8");
		const old = new Date(startedMs - 3_600_000);
		fs.utimesSync(abs, old, old);
		const ledger = diffLedger(deliverableReport("evidence/research/spec-old-20261013.md"), "", {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: startedMs,
			projectRoot: project.root,
		});
		console.log(`[VERIFY] T17-C36b-stale declared=[${ledger.declared.join(",")}]`);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
	});

	it("a referenced-but-missing deliverable is not declared (no false red)", () => {
		const project = mkproject();
		const ledger = diffLedger(deliverableReport("evidence/research/ghost-20261013.md"), "", {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: Date.now() - 60_000,
			projectRoot: project.root,
		});
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
	});

	it("readTerminalGaps folds the outside-taskDir deliverable into a clean verdict", () => {
		const project = mkproject();
		const startedMs = Date.now() - 60_000;
		fs.writeFileSync(
			path.join(project.evidenceDir, "research", "spec-integration-20261013.md"),
			"# deliverable\n",
			"utf8",
		);
		fs.writeFileSync(path.join(project.taskDir, "task.md"), "type: research\n", "utf8");
		fs.writeFileSync(
			path.join(project.taskDir, "report.md"),
			deliverableReport("evidence/research/spec-integration-20261013.md"),
			"utf8",
		);
		// The trace has no evidence event at all (the live C-36b shape).
		fs.writeFileSync(path.join(project.taskDir, "trace.log"), "", "utf8");
		fs.writeFileSync(
			path.join(project.taskDir, "run.json"),
			JSON.stringify({ schema: 1, task_key: "t17-worker", started_at: new Date(startedMs).toISOString() }),
			"utf8",
		);
		const gaps = readTerminalGaps({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			summary: "",
			judgeRecovery: false,
		});
		console.log(
			`[VERIFY] T17-C36b-terminal judged=${gaps.judged} unrecorded=[${gaps.unrecordedFiles.join(",")}] unjudgeable=[${gaps.unjudgeableFiles.join(",")}] ok=${gaps.ok}`,
		);
		expect(gaps.judged).toBe(true);
		expect(gaps.unrecordedFiles).toEqual([]);
		expect(gaps.unjudgeableFiles).toEqual([]);
		expect(gaps.ok).toBe(true);
	});

	it("the same report with no role keeps the historical all-roles verdict", () => {
		const project = mkproject();
		fs.writeFileSync(
			path.join(project.evidenceDir, "research", "spec-legacy-20261013.md"),
			"# deliverable\n",
			"utf8",
		);
		const text = deliverableReport("evidence/research/spec-legacy-20261013.md");
		// No role: the section has no 改动清单, so nothing is declared (unchanged).
		const ledger = diffLedger(text, trace(["src/a.ts"]));
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
	});
});

// ── live corpus guard (skipped when the run dirs are absent) ─────────────────

describe("live corpus — the four research workers reconcile green", () => {
	const dir = path.join(REPO_ROOT, ".agenticdoc", "mw-autopilot-gate-alarm-liveness", "workers");
	const evidenceDir = path.join(REPO_ROOT, ".agenticdoc", "mw-autopilot-gate-alarm-liveness", "evidence");
	const workers = [
		"mwgal-t01-rq1-reminder-chain",
		"mwgal-t04-rq4-schema-view",
		"mwgal-t05-drq1-field-registration",
		"mwgal-t08-drq4-auto-approve",
	];

	it("each fresh evidence deliverable is declared and recorded with zero extra", () => {
		let checked = 0;
		for (const worker of workers) {
			const taskDir = path.join(dir, worker);
			const reportPath = path.join(taskDir, "report.md");
			const tracePath = path.join(taskDir, "trace.log");
			if (!fs.existsSync(reportPath) || !fs.existsSync(tracePath)) continue;
			const startedAt = JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8")) as {
				started_at?: string;
			};
			const ledger = diffLedger(fs.readFileSync(reportPath, "utf8"), fs.readFileSync(tracePath, "utf8"), {
				role: "research",
				deliverableDir: evidenceDir,
				runStartedAtMs: startedAt.started_at ? Date.parse(startedAt.started_at) : undefined,
				projectRoot: REPO_ROOT,
			});
			console.log(
				`[VERIFY] T17-corpus ${worker} declared=${ledger.declared.length} extra=[${ledger.extra.join(",")}] unj=${ledger.unjudgeable}`,
			);
			expect(ledger.extra).toEqual([]);
			expect(ledger.unjudgeable).toBe(false);
			expect(ledger.declared.length).toBeGreaterThanOrEqual(1);
			checked += 1;
		}
		if (checked === 0) console.log("[VERIFY] T17-corpus unavailable — skipped");
	});
});
