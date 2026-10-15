/**
 * mwds-t21-write-intent-soundness.test.ts — T-21 (key mw-dispatch-card-gate,
 * wave 14): the AC-004 change-ledger extraction must not turn a report's prose
 * into declarations. Two real cards (T-18 / T-19) were flipped to
 * `needs-clarification` by `recovery-incomplete: unrecorded write(s)` whose list
 * was entirely artifacts:
 *
 *   1. negation blindness — `未写入 packages/multi-workers/**` counted as a
 *      write intent (every card carries a 写入禁止面 section);
 *   2. no per-worker attribution — a concurrent worker's files charged here;
 *   3. token residue — `coding/ncard_path:`, `^/s@|`, `host/pid`,
 *      `notice/refusal`, `（仅金样本/期望重基线）` (card/diff text split on
 *      backticks and `|`, then `\n`/`\s` normalized into fake `/n`/`/s` paths).
 *
 * The judgement chain under test (all in `shared/change-ledger.ts`):
 *   `diffLedger` -> `stripNonDeclarativeSpans` (comments/contract sections/
 *   fences) -> `extractLedgerBody` -> declaration positions -> shape whitelist
 *   -> item-scoped negation -> `declared \ recorded`.
 *
 * Fixtures below are VERBATIM excerpts of the two real reports
 * (`.agenticdoc/mw-dispatch-card-gate/workers/mwd-t18-ts-producer-identity/
 * report.md` and `.../mwd-t19-orphan-ownership/report.md`); the corpus test at
 * the end runs those files read-only and prints the before/after per item.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
	collectMalformedCandidates,
	diffLedger,
	stripNonDeclarativeSpans,
} from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const WORKERS_DIR = path.join(REPO_ROOT, ".agenticdoc", "mw-dispatch-card-gate", "workers");

// ── verbatim fixtures (T-18) ─────────────────────────────────────────────────

/** T-18 report.md `## 改动清单` body, verbatim (the fenced diff keeps its
 * literal `\n` escape sequences — the residue the legacy extractor turned into
 * `/ncard_path:` etc.). */
const T18_LEDGER_BODY: readonly string[] = [
	"写面内、仅 2 个文件（无 `src/**` 其它文件、无 `packages/multi-workers/**`、无 `.agenticdoc/**` 其它内容）：",
	"",
	"1. `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`",
	'   - 顶层新增 `import { VERSION } from "../../../config.ts";`（`VERSION` = 既有版本源',
	"     `packages/coding-agent/package.json`，运行期读取，见 §3）。",
	"   - 新增 `DISPATCH_PRODUCER_ID` / `ENVELOPE_PRODUCER_KEY` / `envelopeProducerIdentity()`",
	"2. `packages/coding-agent/test/suite/dispatch-card-injection.test.ts`（仅金样本/期望重基线）",
	'   - 新增 `import { VERSION } from "../../src/config.ts";` 及 `DISPATCH_PRODUCER_ID` /',
	"     `ENVELOPE_PRODUCER_KEY` 导入。",
	"     ```diff",
	// biome-ignore lint/suspicious/noTemplateCurlyInString: verbatim T-18 report fixture — `${...}` is literal diff text, not interpolation
	"- const frontmatter = `type: coding\\ncard_path: tasks/${CARD_NAME}\\ncard_sha256: ${sha}\\n`;",
	// biome-ignore lint/suspicious/noTemplateCurlyInString: verbatim T-18 report fixture — `${...}` is literal diff text, not interpolation
	"+ expect(producerLine).toMatch(new RegExp(`^${ENVELOPE_PRODUCER_KEY}: [^\\s@|]+@[^\\s|]+$`));",
	"     ```",
	"",
	"`packages/coding-agent/test/suite/dispatch-card-envelope.test.ts` **未改**：它只测卡文件本身的",
	"`readEnvelope` 判定，与 task.md 头行无关，新增身份行不影响它（A 组 51 passed 已证实）。",
];

// ── verbatim fixtures (T-19) ─────────────────────────────────────────────────

/** T-19 report.md `## 9. 改动清单` rows, verbatim. */
const T19_LEDGER_BODY: readonly string[] = [
	"| 文件 | 改动 |",
	"|---|---|",
	"| `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts` | 新增 `ConductorClaimState` + `conductorClaimState()`（`autopilot/state.py::claim_state` 的 TS 镜像，含 host/pid 判定）。 |",
	"| `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | ② notice/refusal 分流；⑤ `synthesizeEnvelopeFallback()` + `ENVELOPE_FALLBACK_MARKER/AUDIT`（T-14 语义镜像）；⑦ dispatchNewTasks 改为全项目只读扫描 + 写权分流（watched/`_scratch`/ORPHANED），ORPHANED 走 claim-free 修复并告警。 |",
	"| `packages/coding-agent/test/suite/mwds-t19-orphan-ownership.test.ts` | 新建。 |",
	"| `packages/multi-workers/launcher.py` | **未改**（合成后的 `items=[]` 直接过 launcher gate，无需 fallback 配置）。 |",
	"| `packages/multi-workers/autopilot/dispatch.py` | **未改**（producer 语义保持 T-13）。 |",
	"| `pm/ui-bridge.ts` | **未改**（T-18 写面）。 |",
	"",
	"未触碰：`.agenticdoc/**`（除本 worker 目录）、其它 key 目录、任何 task 卡、`test/extensions/**`。未做 cutover。dist/ 未重建。",
];

function report(section: string, body: readonly string[]): string {
	return ["## 结论", "", "done", "", `## ${section}`, "", ...body, "", "## 残留与未验证", "", "none"].join("\n");
}

function trace(recorded: readonly string[]): string {
	return recorded.map((file) => `[WRITE_FILE] path=${file}`).join("\n");
}

const T18_DECLARED = [
	"packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts",
	"packages/coding-agent/test/suite/dispatch-card-injection.test.ts",
];
const T19_DECLARED = [
	"packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts",
	"packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts",
	"packages/coding-agent/test/suite/mwds-t19-orphan-ownership.test.ts",
];

// ── requirement 5: the five positive/negative cases ──────────────────────────

describe("T-21 requirement 5 — five judgement cases", () => {
	it("① a real out-of-scope declaration is still red (judgement not relaxed)", () => {
		const text = report("改动清单", [
			"- packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts — 越界新增",
		]);
		const ledger = diffLedger(text, trace(["src/unrelated.ts"]), { projectRoot: REPO_ROOT });
		expect(ledger.declared).toEqual(["packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts"]);
		expect(ledger.extra).toEqual(["packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts"]);
		console.log(`[VERIFY] T21-① out_of_scope_extra=${ledger.extra.length}`);
	});

	it("① prose declarations still count: 写入 / 我修改了 / wrote", () => {
		for (const line of ["写入 packages/x/y.ts", "我修改了 packages/x/y.ts", "wrote packages/x/y.ts"]) {
			const ledger = diffLedger(report("改动清单", [line]), trace(["packages/other/z.ts"]));
			expect(ledger.declared).toEqual(["packages/x/y.ts"]);
		}
		console.log("[VERIFY] T21-① prose write verbs declared=3/3");
	});

	it("② negation context is not a declaration (and does not exempt a later item)", () => {
		const text = report("改动清单", [
			"- 未写入 `src/**`、`packages/multi-workers/**`、`.agenticdoc/**`",
			"- 不得改 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`",
			"- 禁止面：`test/extensions/**` 无",
			"- not written `packages/coding-agent/src/a.ts`, `src/b.ts`",
			"- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` **未改**（禁止派发）",
			"- 真实声明：写入 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`",
		]);
		const ledger = diffLedger(
			text,
			trace(["packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts"]),
		);
		// Only the last item declares; the `禁止` in item 3 must not exempt it.
		expect(ledger.declared).toEqual(["packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts"]);
		expect(ledger.extra).toEqual([]);
		console.log("[VERIFY] T21-② negated_items_excluded=5 real_item_kept=1");
	});

	it("③ a concurrent worker's files are not charged to this worker", () => {
		// T-18's own evidence: its report + its own trace. T-19's files
		// (index-store.ts / pm-orchestrator.ts) are not in T-18's declaration.
		const ledger = diffLedger(report("改动清单", T18_LEDGER_BODY), trace(T18_DECLARED));
		expect(ledger.extra).toEqual([]);
		expect(ledger.declared).not.toContain(
			"packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts",
		);
		// Per-worker isolation, the other direction: the same report judged
		// against the CONCURRENT worker's trace must not become green — no
		// repo-wide evidence is accepted.
		const crossWorker = diffLedger(report("改动清单", T18_LEDGER_BODY), trace(T19_DECLARED), {
			projectRoot: REPO_ROOT,
		});
		expect(crossWorker.extra).toEqual(T18_DECLARED);
		console.log(`[VERIFY] T21-③ own_trace_extra=0 cross_trace_extra=${crossWorker.extra.length}`);
	});

	it("④ card/fence patterns declare nothing", () => {
		const fenced = report("改动清单", [
			"- `packages/coding-agent/src/a.ts`",
			"```ts",
			// biome-ignore lint/suspicious/noTemplateCurlyInString: fenced diff fixture — `${...}` is documentation text
			"const x = `type: coding\\ncard_path: tasks/${CARD_NAME}`;",
			"const re = /[^\\s@|]+@[^\\s|]+$/;",
			"```",
		]);
		expect(diffLedger(fenced, trace(["packages/coding-agent/src/a.ts"])).declared).toEqual([
			"packages/coding-agent/src/a.ts",
		]);

		const contract = [
			"## 结论",
			"",
			"done",
			"",
			"## 改动清单",
			"",
			"<!-- mw-write-surface: v1 -->",
			"- 允许写：本任务目录下的 worker_file；write_scope: .agenticdoc/other/evidence",
			"- 不得写：`packages/**`、`.git/**`",
			"<!-- /mw-write-surface: v1 -->",
			"- `packages/coding-agent/src/a.ts`",
		].join("\n");
		expect(diffLedger(contract, trace(["packages/coding-agent/src/a.ts"])).declared).toEqual([
			"packages/coding-agent/src/a.ts",
		]);
		console.log("[VERIFY] T21-④ fenced_declarations=0 contract_declarations=0");
	});

	it("⑤ token residue is not red and is counted in malformed_candidates", () => {
		const text = report("改动清单", [
			"| `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts` | 含 host/pid 判定与 notice/refusal 分流。 |",
			"- `packages/coding-agent/test/suite/dispatch-card-injection.test.ts`（仅金样本/期望重基线）",
			"写面：`.agenticdoc/**` 无（`test/extensions/**`）",
		]);
		const ledger = diffLedger(
			text,
			trace([
				"packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts",
				"packages/coding-agent/test/suite/dispatch-card-injection.test.ts",
			]),
		);
		const malformed = collectMalformedCandidates(text);
		expect(ledger.extra).toEqual([]);
		expect(malformed).toContain("host/pid");
		expect(malformed).toContain("notice/refusal");
		expect(malformed).toContain("（仅金样本/期望重基线）");
		expect(malformed).toContain(".agenticdoc/**");
		expect(malformed).toContain("test/extensions/**");
		console.log(`[VERIFY] T21-⑤ malformed=[${malformed.join(",")}] extra=0`);
	});
});

// ── extraction-level checks on the verbatim fixtures ────────────────────────

describe("T-21 extraction semantics on the T-18/T-19 fixtures", () => {
	it("T-18: only the two declared files survive; fence and prose references do not", () => {
		const ledger = diffLedger(report("改动清单", T18_LEDGER_BODY), trace(T18_DECLARED));
		expect(ledger.declared).toEqual(T18_DECLARED);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);

		const malformed = collectMalformedCandidates(report("改动清单", T18_LEDGER_BODY));
		expect(malformed).toContain("（仅金样本/期望重基线）");
		expect(malformed).toContain("src/**");
		expect(malformed).toContain("packages/multi-workers/**");
		expect(malformed).toContain(".agenticdoc/**");
		// Fence-borne residue is stripped before tokenization, not merely
		// mis-shaped: none of the old `/n`-normalized fragments exists.
		expect(malformed).not.toContain("coding/ncard_path:");
		expect(malformed).not.toContain("/n$");
		expect(ledger.declared).not.toContain("task.md");
		expect(ledger.declared).not.toContain("packages/coding-agent/package.json");
		expect(ledger.declared).not.toContain("../../../config.ts");
		console.log(`[VERIFY] T21-T18 declared=[${ledger.declared.join(",")}] malformed=[${malformed.join(",")}]`);
	});

	it("T-19: real rows declare, `**未改**` rows and the trailing paragraph do not", () => {
		const ledger = diffLedger(report("9. 改动清单", T19_LEDGER_BODY), trace(T19_DECLARED));
		expect(ledger.declared).toEqual(T19_DECLARED);
		expect(ledger.extra).toEqual([]);

		const malformed = collectMalformedCandidates(report("9. 改动清单", T19_LEDGER_BODY));
		expect(malformed).toContain("host/pid");
		expect(malformed).toContain("notice/refusal");
		expect(malformed).toContain("autopilot/state.py::claim_state");
		expect(malformed).toContain("ENVELOPE_FALLBACK_MARKER/AUDIT");
		expect(malformed).toContain(".agenticdoc/**");
		expect(malformed).toContain("test/extensions/**");
		console.log(`[VERIFY] T21-T19 declared=[${ledger.declared.join(",")}] malformed=[${malformed.join(",")}]`);
	});

	it("a table row declares its first shape-valid token regardless of column order", () => {
		const flipped = report("改动清单", [
			"| 改动 | 文件 |",
			"|---|---|",
			"| 新增 | `packages/coding-agent/src/a.ts` |",
		]);
		expect(diffLedger(flipped, trace([])).declared).toEqual(["packages/coding-agent/src/a.ts"]);
	});

	it("only the first candidate of an item declares (intent-prose references are ignored)", () => {
		const text = report("改动清单", ["- packages/x/y.ts — 参考 packages/x/reference.ts 的实现"]);
		expect(diffLedger(text, trace([])).declared).toEqual(["packages/x/y.ts"]);
	});

	it("stripNonDeclarativeSpans removes comments, contract sections and fences", () => {
		const text = "a\n<!-- mw-write-surface: v1 -->\nX\n<!-- /mw-write-surface: v1 -->\n```\nY\n```\nb\n<!-- c -->";
		const stripped = stripNonDeclarativeSpans(text);
		expect(stripped).toContain("a");
		expect(stripped).toContain("b");
		expect(stripped).not.toContain("mw-write-surface");
		expect(stripped).not.toContain("X");
		expect(stripped).not.toContain("Y");
		expect(stripped).not.toContain("<!-- c -->");
	});
});

// ── requirement 6: the real corpus, before vs after, per item ────────────────

interface CorpusRow {
	worker: string;
	reportText: string;
	traceText: string;
	before: string[];
	after: string[];
	malformed: string[];
}

/** The `未记录写入：<list>` line the pre-fix run wrote into output.md. */
function readBeforeList(outputText: string): string[] {
	const line = outputText.split(/\r?\n/).find((l) => l.startsWith("未记录写入："));
	if (line === undefined) return [];
	return line
		.slice("未记录写入：".length)
		.split("、")
		.map((s) => s.trim())
		.filter((s) => s !== "");
}

function loadCorpus(): CorpusRow[] {
	const rows: CorpusRow[] = [];
	for (const worker of ["mwd-t18-ts-producer-identity", "mwd-t19-orphan-ownership"]) {
		const dir = path.join(WORKERS_DIR, worker);
		const reportPath = path.join(dir, "report.md");
		const tracePath = path.join(dir, "trace.log");
		const outputPath = path.join(dir, "output.md");
		if (!fs.existsSync(reportPath) || !fs.existsSync(tracePath) || !fs.existsSync(outputPath)) continue;
		const reportText = fs.readFileSync(reportPath, "utf8");
		const traceText = fs.readFileSync(tracePath, "utf8");
		rows.push({
			worker,
			reportText,
			traceText,
			before: readBeforeList(fs.readFileSync(outputPath, "utf8")),
			after: diffLedger(reportText, traceText, { projectRoot: REPO_ROOT }).extra,
			malformed: collectMalformedCandidates(reportText),
		});
	}
	return rows;
}

describe("T-21 requirement 6 — real corpus (T-18 / T-19), before vs after", () => {
	const rows = loadCorpus();
	const available = rows.length === 2;

	it.skipIf(!available)("both real reports go from false-red to green with zero garbage items", () => {
		for (const row of rows) {
			// Per-item verdict: every pre-fix item is either shape-malformed or
			// simply not a declaration (negated / fenced / a reference).
			for (const item of row.before) {
				const verdict = row.malformed.includes(item) ? "malformed" : "not-a-declaration";
				console.log(`  [VERIFY] T21 ${row.worker}: before_item=${item} -> ${verdict}`);
			}
			console.log(
				`[VERIFY] T21 ${row.worker}: before=${row.before.length} after=${row.after.length} malformed=${row.malformed.length}`,
			);
			// The pre-fix run named real garbage (regression guard: the corpus
			// must actually exercise the bug). T-18=17 items, T-19=13 items.
			expect(row.before.length).toBeGreaterThanOrEqual(13);
			// Garbage items -> zero: nothing survives as a declared-but-unrecorded
			// file, so the terminal verdict is no longer `recovery-incomplete`.
			expect(row.after).toEqual([]);
			// Every survivor of the extraction is a real declared file that the
			// worker's own trace recorded (per-worker attribution).
			const ledger = diffLedger(row.reportText, row.traceText);
			expect(ledger.unjudgeable).toBe(false);
			expect(ledger.declared.length).toBeGreaterThanOrEqual(2);
			for (const declared of ledger.declared) {
				expect(ledger.recorded.some((r) => r === declared || r.endsWith(declared))).toBe(true);
			}
		}
	});

	it("both real reports still declare at least the files their trace recorded", () => {
		if (!available) return;
		const t18 = rows.find((r) => r.worker === "mwd-t18-ts-producer-identity");
		const t19 = rows.find((r) => r.worker === "mwd-t19-orphan-ownership");
		expect(diffLedger(t18?.reportText ?? "", t18?.traceText ?? "", { projectRoot: REPO_ROOT }).extra).toEqual([]);
		expect(diffLedger(t19?.reportText ?? "", t19?.traceText ?? "", { projectRoot: REPO_ROOT }).extra).toEqual([]);
	});
});
