/**
 * mwgal-t17c-ledger-unresolvable.test.ts — T-17c / key
 * `mw-autopilot-gate-alarm-liveness` (card T-17c-ledger-unresolvable):
 * "declared but not on disk" is not a write.
 *
 * The T-16 terminal named four unrecorded writes; all four were false
 * positives. Two of them were a NEW subclass (C-36 fifth class):
 *   - `update_index.py` — a ghost file name harvested from code text the report
 *     quoted; the file does not exist anywhere;
 *   - `os.replace` — a Python identifier (7 occurrences in `conductor.py`),
 *     shape-identical to a dotless dotted-basename declaration, never a path.
 * `INFRA_BASENAMES` (T-17b) already covers the other two (`.mw/serve.meta`,
 * `.agenticdoc/_index.parallel`), which just needed the rebuilt bundle.
 *
 * The rule under test: a declared-but-unrecorded path with no file/directory on
 * disk is EXCLUDED from `extra` and surfaced warn-only
 * (`ChangeLedger.unresolvable` → `## Ledger Unresolvable` + a
 * `[FLOW] ledger-unresolvable` trace line), exactly like T-17b's infra class.
 * The discriminator is the FILESYSTEM FACT (existence), never the token's shape
 * and never mtime (T-17b proved both worker and framework writes share the run
 * window).
 *
 * Required regression corpus (card requirement 5):
 *   1. `update_index.py` (off disk) ⇒ zero findings + warn visible;
 *   2. `os.replace` (off disk, dotted identifier) ⇒ same;
 *   3. a REAL existing out-of-scope file ⇒ still red (P-03 counterweight);
 *   4. an existing infra path (`serve.meta` / `_index.parallel`) ⇒ infra channel;
 *   5. the T-17b whitelist and the T-17 writeless corpus do not regress.
 *
 * Two extra tests prove the discriminator is existence itself: creating
 * `os.replace` / `update_index.py` on disk turns them back into `extra`, and an
 * existing declared file with an old mtime is still judged (mtime is not read).
 *
 * The live T-16 corpus at the end replays the exact four false positives.
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
	WRITELESS_LEDGER_ROLES,
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

/** A throwaway project root; returns the root plus the key/task layout. */
function mkproject(): { root: string; trueRoot: string; keyDir: string; taskDir: string; evidenceDir: string } {
	const root = mkdtemp("mwgal-t17c-");
	const trueRoot = path.join(root, ".agenticdoc");
	const keyDir = path.join(trueRoot, "t17ckey");
	const taskDir = path.join(keyDir, "workers", "t17c-worker");
	const evidenceDir = path.join(keyDir, "evidence");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.mkdirSync(evidenceDir, { recursive: true });
	return { root, trueRoot, keyDir, taskDir, evidenceDir };
}

const TASK_KEY = "t17ckey/workers/t17c-worker";

/** Create a real file under `root` (the existence half of the corpus). */
function createFile(root: string, rel: string, mtime?: Date): string {
	const abs = path.join(root, rel);
	fs.mkdirSync(path.dirname(abs), { recursive: true });
	fs.writeFileSync(abs, "// fixture\n", "utf8");
	if (mtime !== undefined) fs.utimesSync(abs, mtime, mtime);
	return abs;
}

function trace(recorded: readonly string[]): string {
	return recorded.map((file) => formatWriteFileEvent(file)).join("\n");
}

/** Recovery-contract shaped report with a change list (the T-21 fixture form). */
function report(body: readonly string[]): string {
	return ["## 结论", "", "done", "", "## 改动清单", "", ...body, "", "## 残留与未验证", "", "none"].join("\n");
}

// ── requirement 5.1/5.2: the two new false-positive shapes ───────────────────

describe("T-17c requirement 5.1/5.2 — off-disk ghost name and code identifier", () => {
	it("`update_index.py` (not on disk) is zero findings and warn-only", () => {
		const project = mkproject();
		const ledger = diffLedger(report(["- update_index.py — 引用的脚本名"]), trace(["src/other.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17c-ghost declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}] unj=${ledger.unjudgeable}`,
		);
		expect(ledger.declared).toEqual(["update_index.py"]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual([]);
		expect(ledger.unresolvable).toEqual(["update_index.py"]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("`os.replace` (dotted identifier, not on disk) is zero findings and warn-only", () => {
		const project = mkproject();
		const ledger = diffLedger(report(["- os.replace — Python 标识符"]), trace(["src/other.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17c-identifier declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.declared).toEqual(["os.replace"]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unresolvable).toEqual(["os.replace"]);
	});

	it("an off-disk-only declaration on a zero-event trace is green, not unjudgeable", () => {
		// There is no real write to reconcile, so the empty trace is not a
		// T-12/F-04 unjudgeable run either.
		const project = mkproject();
		const ledger = diffLedger(report(["- update_index.py — 引用的脚本名", "- os.replace — 标识符"]), "", {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17c-zero-event extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}] unj=${ledger.unjudgeable}`,
		);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unresolvable).toEqual(["update_index.py", "os.replace"]);
		expect(ledger.unjudgeable).toBe(false);
	});
});

// ── requirement 6: the visible warn channel ──────────────────────────────────

describe("T-17c — the exclusion is visible, never silent", () => {
	it("readTerminalGaps + writeOutput surface `## Ledger Unresolvable` and a trace line", () => {
		const project = mkproject();
		fs.writeFileSync(path.join(project.taskDir, "task.md"), "type: coding\n", "utf8");
		fs.writeFileSync(
			path.join(project.taskDir, "report.md"),
			report(["- update_index.py — 引用的脚本名", "- os.replace — Python 标识符"]),
			"utf8",
		);
		fs.writeFileSync(path.join(project.taskDir, "trace.log"), trace(["src/other.ts"]), "utf8");

		const gaps = readTerminalGaps({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			summary: "done",
			judgeRecovery: false,
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17c-terminal ok=${gaps.ok} unrecorded=[${gaps.unrecordedFiles.join(",")}] unresolvable=[${gaps.unresolvableFiles.join(",")}]`,
		);
		expect(gaps.ok).toBe(true);
		expect(gaps.unrecordedFiles).toEqual([]);
		expect(gaps.unresolvableFiles).toEqual(["update_index.py", "os.replace"]);

		writeOutput({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			exitCode: 0,
			summary: "done",
			terminalGaps: gaps,
		});
		const output = fs.readFileSync(path.join(project.taskDir, "output.md"), "utf8");
		const traceText = fs.readFileSync(path.join(project.taskDir, "trace.log"), "utf8");
		// The exact generated section + trace line (report requirement 6 evidence).
		console.log(
			`[VERIFY] T17c-output-section\n${output
				.split("\n")
				.filter((l) => l.includes("Ledger"))
				.join("\n")}`,
		);
		console.log(
			`[VERIFY] T17c-trace-line ${traceText.split(/\r?\n/).find((l) => l.includes("ledger-unresolvable"))}`,
		);
		expect(output).toContain("## Ledger Unresolvable");
		expect(output).toContain("不可解析声明（磁盘不存在，warn，不计入判定）：update_index.py、os.replace");
		expect(output).not.toContain("## Ledger Gaps");
		expect(traceText).toContain("ledger-unresolvable count=2 samples=update_index.py,os.replace");
		// Warn-only: the exclusion must not ride the `## Questions` readback line
		// (the PM reads that line as a failure signal).
		expect(output).not.toContain("未记录写入：update_index.py");
	});
});

// ── requirement 3: existence, not shape and not mtime ────────────────────────

describe("T-17c requirement 3 — the filesystem fact is the discriminator", () => {
	it("the same `os.replace` token EXISTS on disk ⇒ it is a real unrecorded write (red)", () => {
		// Shape is not the discriminator: only the file on disk is.
		const project = mkproject();
		createFile(project.root, "os.replace");
		const ledger = diffLedger(report(["- os.replace — 同形态但真实存在"]), trace(["src/other.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17c-exists declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.extra).toEqual(["os.replace"]);
		expect(ledger.unresolvable).toEqual([]);
	});

	it("the same `update_index.py` token EXISTS on disk ⇒ real unrecorded write (red)", () => {
		const project = mkproject();
		createFile(project.root, "packages/scripts/update_index.py");
		const ledger = diffLedger(
			report(["- packages/scripts/update_index.py — 同形态但真实存在"]),
			trace(["src/other.ts"]),
			{
				role: "coding",
				projectRoot: project.root,
			},
		);
		expect(ledger.extra).toEqual(["packages/scripts/update_index.py"]);
		expect(ledger.unresolvable).toEqual([]);
	});

	it("mtime is never read: an existing declared file with an old mtime is still red", () => {
		const project = mkproject();
		createFile(project.root, "src/stale.ts", new Date(Date.now() - 30 * 24 * 3_600_000));
		const ledger = diffLedger(report(["- src/stale.ts — 上月文件，仅声明"]), trace(["src/other.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17c-mtime extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.extra).toEqual(["src/stale.ts"]);
		expect(ledger.unresolvable).toEqual([]);
	});
});

// ── requirement 5.3: P-03 counterweight (real overreach stays red) ───────────

describe("T-17c requirement 5.3 — a real out-of-scope write stays red", () => {
	const OUT_OF_SCOPE = "packages/coding-agent/src/out-of-scope.ts";

	it("diffLedger: the existing out-of-scope file lands in extra", () => {
		const project = mkproject();
		createFile(project.root, OUT_OF_SCOPE);
		const ledger = diffLedger(report([`- ${OUT_OF_SCOPE} — 越界新增`]), trace(["src/other.ts"]), {
			role: "coding",
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17c-P03 declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.declared).toEqual([OUT_OF_SCOPE]);
		expect(ledger.extra).toEqual([OUT_OF_SCOPE]);
		expect(ledger.unresolvable).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("readTerminalGaps + writeOutput: the real write is not-ok and lands in `## Ledger Gaps`", () => {
		const project = mkproject();
		createFile(project.root, OUT_OF_SCOPE);
		fs.writeFileSync(path.join(project.taskDir, "task.md"), "type: coding\n", "utf8");
		fs.writeFileSync(path.join(project.taskDir, "report.md"), report([`- ${OUT_OF_SCOPE} — 越界新增`]), "utf8");
		fs.writeFileSync(path.join(project.taskDir, "trace.log"), trace(["src/other.ts"]), "utf8");
		const gaps = readTerminalGaps({
			taskKey: TASK_KEY,
			agenticdocRoot: project.trueRoot,
			summary: "done",
			judgeRecovery: false,
			projectRoot: project.root,
		});
		console.log(`[VERIFY] T17c-P03-terminal unrecorded=[${gaps.unrecordedFiles.join(",")}] ok=${gaps.ok}`);
		expect(gaps.unrecordedFiles).toEqual([OUT_OF_SCOPE]);
		expect(gaps.unresolvableFiles).toEqual([]);
		expect(gaps.ok).toBe(false);

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
		expect(output).not.toContain("## Ledger Unresolvable");
	});

	it("a real write mixed with an off-disk ghost: only the real one is red", () => {
		const project = mkproject();
		createFile(project.root, OUT_OF_SCOPE);
		const ledger = diffLedger(
			report([`- ${OUT_OF_SCOPE} — 越界新增`, "- os.replace — 标识符"]),
			trace(["src/other.ts"]),
			{
				role: "coding",
				projectRoot: project.root,
			},
		);
		console.log(
			`[VERIFY] T17c-P03-mixed extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.extra).toEqual([OUT_OF_SCOPE]);
		expect(ledger.unresolvable).toEqual(["os.replace"]);
	});
});

// ── requirement 5.4: existing infra stays on the infra channel ───────────────

describe("T-17c requirement 5.4 — existing infra keeps the infra channel (not unresolvable)", () => {
	it("`serve.meta` / `_index.parallel` existing on disk are infra, never unresolvable", () => {
		const project = mkproject();
		createFile(project.root, ".mw/serve.meta");
		createFile(project.root, ".agenticdoc/_index.parallel");
		const ledger = diffLedger(
			report(["- .mw/serve.meta — 框架写", "- .agenticdoc/_index.parallel — 框架写"]),
			trace(["src/other.ts"]),
			{ role: "coding", projectRoot: project.root },
		);
		console.log(
			`[VERIFY] T17c-infra extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toEqual([".mw/serve.meta", ".agenticdoc/_index.parallel"]);
		expect(ledger.unresolvable).toEqual([]);
	});

	it("infra ownership wins over the existence probe (an absent infra path is still infra)", () => {
		// The T-17b fixtures and zero-event infra cases rely on this order.
		const project = mkproject();
		const ledger = diffLedger(report(["- _workers.parallel — 框架队列", "- serve.meta — 框架写"]), "", {
			role: "coding",
			projectRoot: project.root,
		});
		expect(ledger.infra).toEqual(["_workers.parallel", "serve.meta"]);
		expect(ledger.unresolvable).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});
});

// ── requirement 5.5: T-17b whitelist and T-17 writeless corpus do not regress ─

/** The T-08 live shape reused by the T-17 corpus (survey read references). */
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

describe("T-17c requirement 5.5 — T-17b / T-17 corpora do not regress", () => {
	it("the T-17b infra whitelist still classifies its paths as infrastructure", () => {
		for (const p of [
			"_workers.parallel",
			".agenticdoc/_workers.parallel",
			"_index.parallel",
			".agenticdoc/_index.parallel",
			"serve.meta",
			".mw/serve.meta",
			"pm-state.md",
		]) {
			expect(isInfrastructurePath(p), p).toBe(true);
		}
		expect(INFRA_BASENAMES.has("_workers.parallel")).toBe(true);
		console.log(`[VERIFY] T17c-infra-whitelist entries=${INFRA_BASENAMES.size}`);
	});

	it("the T-17 writeless survey corpus still yields zero findings", () => {
		const project = mkproject();
		const ledger = diffLedger(SURVEY_REPORT, trace(["src/a.ts"]), {
			role: "research",
			deliverableDir: project.evidenceDir,
			runStartedAtMs: Date.now() - 60_000,
			projectRoot: project.root,
		});
		console.log(
			`[VERIFY] T17c-T17-corpus declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}] infra=[${ledger.infra.join(",")}]`,
		);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unresolvable).toEqual([]);
		expect(ledger.infra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
		expect(WRITELESS_LEDGER_ROLES.has("research")).toBe(true);
	});
});

// ── live corpus: the exact T-16 terminal false positives ─────────────────────

describe("T-17c live corpus — the T-16 four false positives reconcile green", () => {
	const dir = path.join(
		REPO_ROOT,
		".agenticdoc",
		"mw-autopilot-gate-alarm-liveness",
		"workers",
		"mwgal-t16-synthetic-claim",
	);

	it("extra is empty; os.replace/update_index.py warn; serve.meta/_index.parallel infra", () => {
		const reportPath = path.join(dir, "report.md");
		const tracePath = path.join(dir, "trace.log");
		if (!fs.existsSync(reportPath) || !fs.existsSync(tracePath)) {
			console.log("[VERIFY] T17c-corpus unavailable — skipped");
			return;
		}
		const ledger = diffLedger(fs.readFileSync(reportPath, "utf8"), fs.readFileSync(tracePath, "utf8"), {
			role: "coding",
			projectRoot: REPO_ROOT,
		});
		console.log(
			`[VERIFY] T17c-corpus declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] infra=[${ledger.infra.join(",")}] unresolvable=[${ledger.unresolvable.join(",")}]`,
		);
		expect(ledger.extra).toEqual([]);
		expect(ledger.infra).toContain(".mw/serve.meta");
		expect(ledger.infra).toContain(".agenticdoc/_index.parallel");
		expect(ledger.unresolvable).toContain("update_index.py");
		expect(ledger.unresolvable).toContain("os.replace");
		expect(ledger.unjudgeable).toBe(false);
	});
});
