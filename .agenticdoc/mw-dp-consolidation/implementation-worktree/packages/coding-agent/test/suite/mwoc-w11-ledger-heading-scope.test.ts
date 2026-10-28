/**
 * mwoc-w11-ledger-heading-scope.test.ts — T-11 (key `mw-worker-output-contract`,
 * FW-005): the change-ledger "declaration section" heading recognizer must not
 * read a report's document title / header as a change list.
 *
 * Real event (this key's own T-02 worker, `workers/woc-t02-ledger`): the H1
 * `# T-02 · 变更账本抽取器加固（W3 · AC-008 / AC-017）— output` hit the broad
 * alias `变更` under the old `#{1,6}` + `includes` recognizer, so
 * `extractLedgerBody` took the header that follows it (the `card:` line and the
 * `目标锚点：.agenticdoc/goal.md` line) as the change-list body. The settle then
 * reported `exit=2 / needs-clarification` with
 * `unrecorded write(s): .../T-02-ledger-extractor-hardening.md, .agenticdoc/
 * goal.md` — two files no worker ever wrote (`goal.md` mtime predates the run).
 *
 * Two rules fix that class without loosening the red judgement:
 *   1. an H1 is the document title, never a declaration section (level >= 2);
 *   2. after stripping a section-number/list prefix and folding case, an alias
 *      must ANCHOR: it starts the heading or one of its `：`/`｜`-separated
 *      clauses. `### 7. 类型检查与改动面` (alias embedded mid-clause) no longer
 *      matches, while `## 改动清单（本卡写面）` still does and the T-21 QG corpus
 *      heading `### 结论 6｜可度量：改动前后的期望变化…` keeps its locked
 *      verdict (`mwgal-t21-qg-fixes.test.ts`).
 *
 * The real-event fixture is the actual `workers/woc-t02-ledger` product when
 * present; the inline `REAL_SHAPE_HEADER` rebuilds the same shape line by line
 * (source line cited) so the regression also runs on a clean checkout.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { diffLedger } from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const REAL_WORKER_DIR = path.join(REPO_ROOT, ".agenticdoc", "mw-worker-output-contract", "workers", "woc-t02-ledger");

/** The two never-written files the incident charged: the dispatch card named by
 * the header's `card:` line and the project goal anchor. */
const CARD_PATH = ".agenticdoc/mw-worker-output-contract/tasks/T-02-ledger-extractor-hardening.md";
const GOAL_PATH = ".agenticdoc/goal.md";

/** `workers/woc-t02-ledger/output.md` header (lines 1-5) plus the negative
 * section that lives in the same report (`:112`), rebuilt line by line with the
 * source line cited. After the header the next heading is the real `## 结论`. */
const REAL_SHAPE_HEADER: string = [
	// output.md:1 — H1, contains the alias 变更
	"# T-02 · 变更账本抽取器加固（W3 · AC-008 / AC-017）— output",
	// output.md:2 — blank
	"",
	// output.md:3 — the `card:` line naming the dispatch card
	"- Key: `mw-worker-output-contract`；worker: `woc-t02-ledger`；card: `.agenticdoc/mw-worker-output-contract/tasks/T-02-ledger-extractor-hardening.md`（`card_sha256 37336624…`）",
	// output.md:4 — the goal anchor
	"- 目标锚点：`.agenticdoc/goal.md`（「文件驱动的去中心化协调」「工具白名单按任务类型」）",
	// output.md:5 — blank
	"",
	// output.md:7 — the next real section
	"## 结论",
	"",
	"T-02 done.",
	"",
	// output.md:112 — the negative heading of the same incident report
	"### 7. 类型检查与改动面",
	"",
	"```text",
	"$ npx tsgo --noEmit",
	"tsgo=0",
	"```",
].join("\n");

const LEDGER_FILE = "packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts";
const WORKER_MODE_FILE = "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts";

/** A coding report whose only declaration section is the given heading line. */
function reportWithHeading(headingLine: string, files: readonly string[]): string {
	return [
		"## 结论",
		"",
		"done",
		"",
		headingLine,
		"",
		...files.map((file) => `- \`${file}\` — 改动`),
		"",
		"## 残留与未验证",
		"",
		"none",
	].join("\n");
}

function reportWithSection(title: string, files: readonly string[]): string {
	return reportWithHeading(`## ${title}`, files);
}

const CODING = { role: "coding", projectRoot: REPO_ROOT } as const;

describe("T-11 real event — the H1 header is never a declaration body", () => {
	it("the rebuilt T-02 header declares neither the card nor goal.md (extra empty)", () => {
		const ledger = diffLedger(REAL_SHAPE_HEADER, "", CODING);
		console.log(
			`[VERIFY] T11 header declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] unjudgeable=${ledger.unjudgeable}`,
		);
		expect(ledger.declared).not.toContain(CARD_PATH);
		expect(ledger.declared).not.toContain(GOAL_PATH);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
	});

	it("the real woc-t02-ledger product reconciles green (when the run dir is present)", () => {
		const outputPath = path.join(REAL_WORKER_DIR, "output.md");
		const tracePath = path.join(REAL_WORKER_DIR, "trace.log");
		if (!fs.existsSync(outputPath) || !fs.existsSync(tracePath)) {
			console.log("[VERIFY] T11 real corpus unavailable — inline header asserted above");
			return;
		}
		const ledger = diffLedger(fs.readFileSync(outputPath, "utf8"), fs.readFileSync(tracePath, "utf8"), CODING);
		console.log(
			`[VERIFY] T11 real-corpus declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] unjudgeable=${ledger.unjudgeable}`,
		);
		expect(ledger.declared).not.toContain(CARD_PATH);
		expect(ledger.declared).not.toContain(GOAL_PATH);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});
});

describe("T-11 heading recognition — legal variants and negatives", () => {
	const LEGAL_TITLES: readonly string[] = [
		"改动清单",
		"改动清单（本卡写面）",
		"变更清单",
		"Changed Files",
		"Files Changed",
	];

	// The three negatives of the card: the incident H1 title (separate test),
	// an alias embedded mid-clause at H3, and a heading with no alias at all.
	const NEGATIVE_HEADINGS: readonly string[] = ["### 7. 类型检查与改动面", "## 上下文来源"];

	it("all five legal variant headings still declare", () => {
		const rows: string[] = [];
		for (const title of LEGAL_TITLES) {
			const ledger = diffLedger(reportWithSection(title, [LEDGER_FILE]), `[WRITE_FILE] path=${LEDGER_FILE}`, CODING);
			rows.push(`${title}:${ledger.declared.length}`);
			expect(ledger.declared, title).toEqual([LEDGER_FILE]);
			expect(ledger.extra, title).toEqual([]);
		}
		console.log(`[VERIFY] T11 legal_hits=${rows.join(",")}`);
	});

	it("the three negative headings declare nothing", () => {
		const rows: string[] = [];
		for (const heading of NEGATIVE_HEADINGS) {
			const ledger = diffLedger(
				reportWithHeading(heading, [LEDGER_FILE]),
				`[WRITE_FILE] path=${LEDGER_FILE}`,
				CODING,
			);
			rows.push(`${heading}:${ledger.declared.length}`);
			expect(ledger.declared, heading).toEqual([]);
			expect(ledger.extra, heading).toEqual([]);
		}
		console.log(`[VERIFY] T11 negative_hits=${rows.join(",")}`);
	});

	it("an H1 that was the incident title would not match even without prefix stripping", () => {
		// `# 变更账本…` is the incident shape; the level-1 rule refuses it outright.
		const text = ["# 变更账本抽取器加固", "", `- \`${LEDGER_FILE}\` — 改动`, "", "## 结论", "", "done"].join("\n");
		const ledger = diffLedger(text, `[WRITE_FILE] path=${LEDGER_FILE}`, CODING);
		expect(ledger.declared).toEqual([]);
	});
});

describe("T-11 real red is not weakened", () => {
	it("`## 改动清单` naming a trace-unrecorded real file stays red", () => {
		const ledger = diffLedger(
			reportWithSection("改动清单", [WORKER_MODE_FILE]),
			`[WRITE_FILE] path=${LEDGER_FILE}`,
			CODING,
		);
		console.log(`[VERIFY] T11 real-red declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`);
		expect(ledger.declared).toEqual([WORKER_MODE_FILE]);
		expect(ledger.extra).toEqual([WORKER_MODE_FILE]);
		expect(ledger.unjudgeable).toBe(false);
	});
});
