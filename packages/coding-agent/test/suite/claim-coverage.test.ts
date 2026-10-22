/**
 * claim-coverage.test.ts — L3 settle layer, read-only face (T-04a, key
 * `claim-driven-review`).
 *
 * Locks the two new exports of `worker/output-sections.ts` and their one
 * integration point in `worker/output-writer.ts`:
 *
 *   1. `parseVerdictTable` — the agent-authored `## 断言裁决` table: heading
 *      aliases, free column order, ignored extra columns, full-width folding,
 *      fenced-block exclusion, unparsable rows reported instead of thrown
 *      (RQ-3 §5.1/§5.6, the P-048 tolerance lesson).
 *   2. `claimCoverage` — the 11 criteria groups / 12 gap tokens of the card
 *      (`claims:missing-table`, `missing-row`, `claims:extra-row`, `verdict`,
 *      `finding`, `verdict-finding`, `evidence`, `reason`, `self-evidence`,
 *      `struct-held`, `budget`, `tautology`), each with a positive and a
 *      negative case, plus the RQ-3 §5.3 evidence grammar.
 *   3. `readTerminalGaps({ claims })` — the field-identical no-claims path, the
 *      `ok` fold and the optional `claimGaps` field; `writeOutput`'s
 *      `## Questions` first-line readback format (`未裁决断言：…`).
 *
 * Only local fixtures: a temp project dir for evidence stat/line counts and a
 * temp task dir for the terminal write. No provider APIs, no real repo files.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Claim } from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";
import { claimCoverage, parseVerdictTable } from "../../src/extensions/agent-team-loop/worker/output-sections.ts";
import {
	readTerminalGaps,
	type TerminalGaps,
	writeOutput,
} from "../../src/extensions/agent-team-loop/worker/output-writer.ts";

// ── fixtures ─────────────────────────────────────────────────────────────────

const tempDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

function numberedLines(count: number): string {
	const lines: string[] = [];
	for (let i = 1; i <= count; i++) lines.push(`line ${i}`);
	return `${lines.join("\n")}\n`;
}

let projectDir: string;

beforeEach(() => {
	projectDir = mkdtemp("mw-claim-coverage-");
	fs.mkdirSync(path.join(projectDir, "src"), { recursive: true });
	fs.writeFileSync(path.join(projectDir, "src", "a.ts"), numberedLines(20), "utf8");
	fs.writeFileSync(path.join(projectDir, "src", "long.ts"), numberedLines(260), "utf8");
	// Self-witness fixture: exists on disk, so a `report.md:12` ref is a
	// grammar-valid citation that ONLY the self-evidence criterion can reject.
	fs.writeFileSync(path.join(projectDir, "report.md"), numberedLines(20), "utf8");
	fs.writeFileSync(path.join(projectDir, "progress.md"), numberedLines(20), "utf8");
});

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** One card claim, full six-element shape unless overridden. */
function claimOf(id: string, overrides: Partial<Claim> = {}): Claim {
	return {
		id,
		type: "grep",
		parent: "",
		statement: `断言 ${id} 的行为`,
		falsifier: `运行 app 观察 ${id} 出现相反结果`,
		locator: "-",
		judgement: `grep: ${id}`,
		budget: 2,
		row: 1,
		...overrides,
	};
}

const HEADER = "| claim | 类型 | 裁决 | 判定 | 证据 | 取数 | 原因 |";
const SEPARATOR = "| --- | --- | --- | --- | --- | --- | --- |";

interface RowSpec {
	id: string;
	type?: string;
	verdict: string;
	finding: string;
	evidence?: string;
	fetches?: string;
	reason?: string;
}

/** One canonical seven-column verdict row. */
function rowText(spec: RowSpec): string {
	return `| ${spec.id} | ${spec.type ?? "grep"} | ${spec.verdict} | ${spec.finding} | ${
		spec.evidence ?? "-"
	} | ${spec.fetches ?? "0"} | ${spec.reason ?? "-"} |`;
}

/** A verdict-table section (heading + header + separator + rows). */
function tableText(rows: string[], heading = "## 断言裁决"): string {
	return [heading, "", HEADER, SEPARATOR, ...rows, ""].join("\n");
}

/** Judged gaps for `claims` against a generated table. */
function gapsFor(claims: Claim[], rows: string[], heading = "## 断言裁决"): string[] {
	return claimCoverage(claims, parseVerdictTable(tableText(rows, heading)), { projectDir });
}

const CLEAN_CLAIM = claimOf("C-01");
const CLEAN_ROW = rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3", fetches: "1" });

// ── 1. parseVerdictTable ─────────────────────────────────────────────────────

describe("parseVerdictTable (RQ-3 §5.1/§5.6)", () => {
	it("parses the seven columns under the H2 and keeps cell text for diagnostics", () => {
		const table = parseVerdictTable(tableText([CLEAN_ROW]));
		console.log(`[VC-T04a-parse] present=${table.present} rows=${table.rows.length} errors=${table.errors.length}`);
		expect(table.present).toBe(true);
		expect(table.errors).toEqual([]);
		expect(table.rows).toHaveLength(1);
		expect(table.rows[0]).toMatchObject({
			id: "C-01",
			type: "grep",
			verdict: "closed",
			finding: "成立",
			evidence: "src/a.ts:3",
			fetches: "1",
			reason: "-",
		});
	});

	it("accepts a suffixed heading alias (`## 断言裁决（claims）`)", () => {
		expect(parseVerdictTable(tableText([CLEAN_ROW], "## 断言裁决（claims）")).present).toBe(true);
	});

	it("tolerates free column order and ignores extra columns", () => {
		const text = [
			"## 断言裁决",
			"| 裁决 | claim | 证据 | 类型 | 备注 | 取数 | 判定 | 原因 |",
			"| --- | --- | --- | --- | --- | --- | --- | --- |",
			"| closed | C-01 | src/a.ts:3 | grep | ignore me | 1 | 成立 | - |",
			"",
		].join("\n");
		const table = parseVerdictTable(text);
		expect(table.errors).toEqual([]);
		expect(table.rows[0]).toMatchObject({ id: "C-01", verdict: "closed", evidence: "src/a.ts:3", fetches: "1" });
	});

	it("folds full-width pipes, colons and digits", () => {
		const text = [
			"## 断言裁决",
			"｜ claim ｜ 类型 ｜ 裁决 ｜ 判定 ｜ 证据 ｜ 取数 ｜ 原因 ｜",
			"｜ --- ｜ --- ｜ --- ｜ --- ｜ --- ｜ --- ｜ --- ｜",
			"｜ C-01 ｜ grep ｜ closed ｜ 成立 ｜ src/a.ts：3 ｜ １ ｜ - ｜",
			"",
		].join("\n");
		const table = parseVerdictTable(text);
		expect(table.present).toBe(true);
		expect(table.errors).toEqual([]);
		expect(table.rows[0]).toMatchObject({ id: "C-01", evidence: "src/a.ts:3", fetches: "1" });
	});

	it("ignores a table inside a fenced code block", () => {
		const text = ["## 断言裁决", "```md", HEADER, SEPARATOR, CLEAN_ROW, "```", ""].join("\n");
		const table = parseVerdictTable(text);
		expect(table.present).toBe(true);
		expect(table.rows).toEqual([]);
		expect(claimCoverage([CLEAN_CLAIM], table, { projectDir })).toEqual(["claim:C-01:missing-row"]);
	});

	it("reports an unparsable row instead of throwing (P-048)", () => {
		const table = parseVerdictTable(tableText([rowText({ id: "not-a-claim", verdict: "closed", finding: "成立" })]));
		expect(table.rows).toEqual([]);
		expect(table.errors).toEqual(["claim:5:unparsable"]);
	});
});

// ── 2. claimCoverage: 11 criteria groups / 12 gap tokens ─────────────────────

describe("claimCoverage (RQ-3 §5 / B-1/B-4/B-10)", () => {
	it("baseline: a covered, evidenced, budgeted claim has no gaps", () => {
		expect(gapsFor([CLEAN_CLAIM], [CLEAN_ROW])).toEqual([]);
	});

	it("claims:missing-table — no `## 断言裁决` H2 at all", () => {
		expect(claimCoverage([CLEAN_CLAIM], parseVerdictTable("## 结论\n\n无表。\n"), { projectDir })).toEqual([
			"claims:missing-table",
		]);
		expect(gapsFor([CLEAN_CLAIM], [CLEAN_ROW])).toEqual([]);
	});

	it("claim:<id>:missing-row / claims:extra-row:<id> — bidirectional set equality (B-10)", () => {
		expect(gapsFor([CLEAN_CLAIM, claimOf("C-02")], [CLEAN_ROW])).toEqual(["claim:C-02:missing-row"]);
		expect(gapsFor([CLEAN_CLAIM], [CLEAN_ROW, rowText({ id: "C-09", verdict: "closed", finding: "成立" })])).toEqual([
			"claims:extra-row:C-09",
		]);
		expect(gapsFor([CLEAN_CLAIM], [CLEAN_ROW])).toEqual([]);
	});

	it("claim:<id>:verdict — outside the closed|partial|unverified set", () => {
		expect(gapsFor([CLEAN_CLAIM], [rowText({ ...{ id: "C-01", verdict: "done", finding: "成立" } })])).toEqual([
			"claim:C-01:verdict",
		]);
		expect(gapsFor([CLEAN_CLAIM], [CLEAN_ROW])).toEqual([]);
	});

	it("claim:<id>:finding — outside 成立|不成立|无法判定", () => {
		expect(
			gapsFor([CLEAN_CLAIM], [rowText({ id: "C-01", verdict: "closed", finding: "PASS", evidence: "src/a.ts:3" })]),
		).toEqual(["claim:C-01:finding"]);
		expect(gapsFor([CLEAN_CLAIM], [CLEAN_ROW])).toEqual([]);
	});

	it("claim:<id>:verdict-finding — the §5.1 mapping must hold", () => {
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "closed", finding: "无法判定", evidence: "src/a.ts:3" })],
			),
		).toEqual(["claim:C-01:verdict-finding"]);
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "unverified", finding: "无法判定", reason: "ambiguous", fetches: "0" })],
			),
		).toEqual([]);
		expect(
			gapsFor(
				[claimOf("C-01", { type: "struct" })],
				[rowText({ id: "C-01", type: "struct", verdict: "partial", finding: "部分成立", evidence: "src/a.ts:3" })],
			),
		).toEqual([]);
	});

	it("claim:<id>:evidence — required for closed/partial, and the §5.3 grammar enforced", () => {
		const noEvidence = gapsFor(
			[CLEAN_CLAIM],
			[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "" })],
		);
		expect(noEvidence).toEqual(["claim:C-01:evidence"]);
		// unparsable ref, missing path, line past EOF, range wider than 200 lines.
		for (const evidence of ["随便写的", "src/missing.ts:1", "src/a.ts:999", "src/long.ts:1-260"]) {
			expect(
				gapsFor([CLEAN_CLAIM], [rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence })]),
			).toEqual(["claim:C-01:evidence"]);
		}
		// Negative: a valid path range and a valid cmdref both satisfy it.
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:1-3" })],
			),
		).toEqual([]);
		expect(
			gapsFor(
				[claimOf("C-01", { type: "cmd" })],
				[
					rowText({
						id: "C-01",
						type: "cmd",
						verdict: "closed",
						finding: "成立",
						evidence: "node ../../node_modules/vitest/dist/cli.js --run test/x.ts => rc=0",
					}),
				],
			),
		).toEqual([]);
		// A cmdref that smuggles a shell chain is not evidence.
		expect(
			gapsFor(
				[claimOf("C-01", { type: "cmd" })],
				[
					rowText({
						id: "C-01",
						type: "cmd",
						verdict: "closed",
						finding: "成立",
						evidence: "node a.js && node b.js",
					}),
				],
			),
		).toEqual(["claim:C-01:evidence"]);
	});

	it("claim:<id>:reason — unverified needs one of the seven frozen reasons", () => {
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "unverified", finding: "无法判定", reason: "没查", fetches: "0" })],
			),
		).toEqual(["claim:C-01:reason"]);
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "unverified", finding: "无法判定", reason: "ambiguous", fetches: "0" })],
			),
		).toEqual([]);
	});

	it("claim:<id>:self-evidence — report*/output/progress/task cannot be the only evidence (B-1/B-4)", () => {
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "report.md:12" })],
			),
		).toEqual(["claim:C-01:self-evidence"]);
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "progress.md:3" })],
			),
		).toEqual(["claim:C-01:self-evidence"]);
		// progress.md is allowed as SECONDARY evidence: one real ref clears it.
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[
					rowText({
						id: "C-01",
						verdict: "closed",
						finding: "成立",
						evidence: "progress.md:3;src/a.ts:3",
					}),
				],
			),
		).toEqual([]);
	});

	it("claim:<id>:struct-held — a struct row may not count toward the closed numerator (B-10)", () => {
		expect(
			gapsFor(
				[claimOf("C-01", { type: "struct" })],
				[rowText({ id: "C-01", type: "struct", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" })],
			),
		).toEqual(["claim:C-01:struct-held"]);
		expect(
			gapsFor(
				[claimOf("C-01", { type: "struct" })],
				[rowText({ id: "C-01", type: "struct", verdict: "partial", finding: "部分成立", evidence: "src/a.ts:3" })],
			),
		).toEqual([]);
	});

	it("claim:<id>:budget — `取数` must be a count and <= min(Σ预算, 30)", () => {
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3", fetches: "5" })],
			),
		).toEqual(["claim:C-01:budget"]);
		expect(
			gapsFor(
				[CLEAN_CLAIM],
				[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3", fetches: "two" })],
			),
		).toEqual(["claim:C-01:budget"]);
		// Σ预算 40 -> the calibrated call cap (30) is the ceiling.
		const rich = claimOf("C-01", { budget: 40 });
		expect(
			gapsFor(
				[rich],
				[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3", fetches: "31" })],
			),
		).toEqual(["claim:C-01:budget"]);
		expect(
			gapsFor(
				[rich],
				[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3", fetches: "30" })],
			),
		).toEqual([]);
	});

	it("claim:<id>:tautology — T-01's B-5 judge is reused, not re-implemented", () => {
		const tautology = claimOf("C-01", {
			statement: "配置已修复",
			falsifier: "配置未修复",
			judgement: "grep: 配置",
		});
		expect(gapsFor([tautology], [CLEAN_ROW])).toEqual(["claim:C-01:tautology"]);
		expect(gapsFor([CLEAN_CLAIM], [CLEAN_ROW])).toEqual([]);
	});

	it("a claim-free card is not judged (nothing to adjudicate)", () => {
		expect(claimCoverage([], parseVerdictTable(""), { projectDir })).toEqual([]);
	});
});

// ── 3. evidence grammar matrix (RQ-3 §5.3) ───────────────────────────────────

describe("evidence ref grammar (RQ-3 §5.3)", () => {
	function evidenceGaps(evidence: string): string[] {
		return gapsFor(
			[CLEAN_CLAIM],
			[rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence, fetches: "1" })],
		);
	}

	it("accepts `path:line` and `path:a-b`", () => {
		expect(evidenceGaps("src/a.ts:1")).toEqual([]);
		expect(evidenceGaps("src/a.ts:2-4")).toEqual([]);
	});

	it("accepts `cmd => rc=0` and rejects an rc-less command", () => {
		expect(evidenceGaps("npm run check => rc=0")).toEqual([]);
		expect(evidenceGaps("npm run check")).toEqual(["claim:C-01:evidence"]);
	});

	it("rejects a range wider than 200 lines and a line past EOF", () => {
		expect(evidenceGaps("src/long.ts:1-202")).toEqual(["claim:C-01:evidence"]);
		expect(evidenceGaps("src/long.ts:1-201")).toEqual([]);
		expect(evidenceGaps(`src/a.ts:${20 + 1}`)).toEqual(["claim:C-01:evidence"]);
	});

	it("rejects a nonexistent path and an escape from the project root", () => {
		expect(evidenceGaps("src/none.ts:1")).toEqual(["claim:C-01:evidence"]);
		expect(evidenceGaps("../outside.ts:1")).toEqual(["claim:C-01:evidence"]);
		expect(evidenceGaps("/etc/hosts:1")).toEqual(["claim:C-01:evidence"]);
	});

	it("marks a self-witness path as self-evidence, not as evidence-syntax failure", () => {
		expect(evidenceGaps("report.md:12")).toEqual(["claim:C-01:self-evidence"]);
		expect(evidenceGaps("src/a.ts:3「line 3」")).toEqual([]);
	});
});

// ── 4. readTerminalGaps: field-identical no-claims path + ok fold ────────────

const WRITE_TASK_KEY = "cdr/workers/t04a-worker";

interface TerminalFixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
}

/** `coding` task with a complete report and a consistent change ledger. */
function makeTerminalFixture(): TerminalFixture {
	const projectRoot = mkdtemp("mw-claim-terminal-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, "cdr");
	const taskDir = path.join(keyDir, "workers", "t04a-worker");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.mkdirSync(path.join(projectRoot, "src"), { recursive: true });
	fs.writeFileSync(path.join(projectRoot, "src", "a.ts"), numberedLines(20), "utf8");
	fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
	fs.writeFileSync(
		path.join(taskDir, "report.md"),
		[
			"## 结论",
			"完成。",
			"",
			"## 证据",
			"看 `src/a.ts:3`。",
			"",
			"## 残留与未验证",
			"无。",
			"",
			"## 改动清单",
			"- src/a.ts",
			"",
			"## 上下文来源",
			"`task.md`",
			"",
		].join("\n"),
		"utf8",
	);
	fs.writeFileSync(path.join(taskDir, "trace.log"), "[WRITE_FILE] path=src/a.ts\n", "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir };
}

function terminalGapsOf(fixture: TerminalFixture, claims?: Claim[]): TerminalGaps {
	return readTerminalGaps({
		taskKey: WRITE_TASK_KEY,
		agenticdocRoot: fixture.trueRoot,
		summary: "",
		projectRoot: fixture.projectRoot,
		...(claims === undefined ? {} : { claims }),
	});
}

const VERDICT_TABLE = tableText([
	rowText({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3", fetches: "1" }),
]);

/** The pre-T-04a verdict object: every field the old code returned. */
const LEGACY_GAPS: TerminalGaps = {
	judged: true,
	missingSections: [],
	unrecordedFiles: [],
	unjudgeableFiles: [],
	malformedFiles: [],
	infraFiles: [],
	unresolvableFiles: [],
	ok: true,
};

describe("readTerminalGaps claim wiring (T-04a)", () => {
	it("no `claims` opt: field-identical to the pre-claim verdict, `claimGaps` absent", () => {
		const fixture = makeTerminalFixture();
		const gaps = terminalGapsOf(fixture);
		console.log(`[VC-T04a-noclaims] keys=${Object.keys(gaps).join(",")} ok=${String(gaps.ok)}`);
		expect(gaps).toEqual(LEGACY_GAPS);
		expect("claimGaps" in gaps).toBe(false);
		expect(Object.keys(gaps)).toHaveLength(Object.keys(LEGACY_GAPS).length);
	});

	it("empty claim set: `claimGaps` is present and empty, the verdict stays green", () => {
		const fixture = makeTerminalFixture();
		const gaps = terminalGapsOf(fixture, []);
		expect(gaps.claimGaps).toEqual([]);
		expect(gaps.ok).toBe(true);
	});

	it("claims without a table flip `ok` through `claimGaps`", () => {
		const fixture = makeTerminalFixture();
		const gaps = terminalGapsOf(fixture, [CLEAN_CLAIM]);
		expect(gaps.claimGaps).toEqual(["claims:missing-table"]);
		expect(gaps.missingSections).toEqual([]);
		expect(gaps.ok).toBe(false);
	});

	it("a fully covered table keeps the verdict green", () => {
		const fixture = makeTerminalFixture();
		fs.appendFileSync(path.join(fixture.taskDir, "report.md"), `\n${VERDICT_TABLE}`, "utf8");
		const gaps = terminalGapsOf(fixture, [CLEAN_CLAIM]);
		expect(gaps.claimGaps).toEqual([]);
		expect(gaps.ok).toBe(true);
	});

	it("`judgeRecovery: false` does not judge claims either (no product to judge)", () => {
		const fixture = makeTerminalFixture();
		const gaps = readTerminalGaps({
			taskKey: WRITE_TASK_KEY,
			agenticdocRoot: fixture.trueRoot,
			summary: "",
			projectRoot: fixture.projectRoot,
			judgeRecovery: false,
			claims: [CLEAN_CLAIM],
		});
		expect("claimGaps" in gaps).toBe(false);
		expect(gaps.ok).toBe(true);
	});
});

// ── 5. writeOutput: `## Questions` first-line readback ──────────────────────

function gapsOf(overrides: Partial<TerminalGaps> = {}): TerminalGaps {
	return { ...LEGACY_GAPS, ...overrides };
}

function questionsFirstLine(outputText: string): string {
	const marker = "## Questions\n\n";
	const start = outputText.indexOf(marker);
	expect(start).toBeGreaterThanOrEqual(0);
	return (outputText.slice(start + marker.length).split("\n")[0] ?? "").trimEnd();
}

describe("writeOutput `## Questions` readback line (T-04a)", () => {
	it("names at most three un-settled claim ids with an ellipsis", () => {
		const fixture = makeTerminalFixture();
		writeOutput({
			taskKey: WRITE_TASK_KEY,
			agenticdocRoot: fixture.trueRoot,
			exitCode: 2,
			summary: "需要澄清",
			questions: "请确认 X",
			terminalGaps: gapsOf({
				claimGaps: [
					"claim:C-01:missing-row",
					"claim:C-01:evidence",
					"claim:C-02:reason",
					"claim:C-03:budget",
					"claim:C-04:tautology",
				],
				ok: false,
			}),
		});
		const text = fs.readFileSync(path.join(fixture.taskDir, "output.md"), "utf8");
		console.log(`[VC-T04a-questions] ${questionsFirstLine(text)}`);
		expect(questionsFirstLine(text)).toBe("请确认 X | 未裁决断言：C-01、C-02、C-03…");
	});

	it("omits the note when there are no claim gaps (byte-identical readback)", () => {
		const fixture = makeTerminalFixture();
		writeOutput({
			taskKey: WRITE_TASK_KEY,
			agenticdocRoot: fixture.trueRoot,
			exitCode: 2,
			summary: "需要澄清",
			questions: "请确认 X",
			terminalGaps: gapsOf({ claimGaps: [] }),
		});
		const text = fs.readFileSync(path.join(fixture.taskDir, "output.md"), "utf8");
		expect(questionsFirstLine(text)).toBe("请确认 X");
	});

	it("names an id-less gap by its own token (`claims:missing-table`)", () => {
		const fixture = makeTerminalFixture();
		writeOutput({
			taskKey: WRITE_TASK_KEY,
			agenticdocRoot: fixture.trueRoot,
			exitCode: 2,
			summary: "需要澄清",
			questions: "请确认 X",
			terminalGaps: gapsOf({ claimGaps: ["claims:missing-table"], ok: false }),
		});
		const text = fs.readFileSync(path.join(fixture.taskDir, "output.md"), "utf8");
		expect(questionsFirstLine(text)).toBe("请确认 X | 未裁决断言：claims:missing-table");
	});
});
