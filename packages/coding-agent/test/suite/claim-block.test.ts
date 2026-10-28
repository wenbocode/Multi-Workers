/**
 * claim-block.test.ts — L1 claims contract (T-01, key `claim-driven-review`).
 *
 * Locks the three pure functions and the four parity-locked constants of
 * `shared/dispatch-card.ts` (design §2.1/§2.3/§3.1/§7 D-001/D-005/D-007):
 *
 *   1. `parseClaimsBlock` — block markers, free column order, header aliases,
 *      full-width folding, fenced-block skip, `C-01.3` struct child rule,
 *      unparsable rows report instead of throw (P-048).
 *   2. `claimsGaps` — the frozen `claim:<id>:<element>` / `claims:<rule>:<d>`
 *      item shapes T-02 concatenates into its refusal text, plus the
 *      `enforce` grey switch (D-006): structural gaps always, soft findings
 *      only when enforcing.
 *   3. `claimBudgetCaps` — `min(30, perClaim × n)` (= 6 calls per claim) and
 *      `min(393216, 65536 × n)` (design §4, D-014).
 *
 * Fixtures are inline literals plus a temporary project dir (only `statSync`
 * is exercised); no corpus counts and no real project files are frozen.
 */

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
	CLAIM_BUDGET,
	CLAIM_GATE_DEFAULT,
	CLAIM_TYPES,
	type Claim,
	claimBudgetCaps,
	claimsGaps,
	parseClaimsBlock,
	UNVERIFIED_REASONS,
} from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";

const OPEN = "<!-- mw-claims: v1 -->";
const CLOSE = "<!-- /mw-claims -->";
const HEADER = "| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |";
const SEPARATOR = "| --- | --- | --- | --- | --- | --- | --- |";

/** One canonical claims block around `rows` (`close: false` drops the marker). */
function blockText(rows: string[], options: { close?: boolean } = {}): string {
	const lines = [OPEN, HEADER, SEPARATOR, ...rows];
	if (options.close !== false) lines.push(CLOSE);
	return lines.join("\n");
}

/** One canonical seven-column row. */
function row(
	id: string,
	type: string,
	statement: string,
	falsifier: string,
	locator: string,
	judgement: string,
	budget: string,
): string {
	return `| ${id} | ${type} | ${statement} | ${falsifier} | ${locator} | ${judgement} | ${budget} |`;
}

/** A complete `Claim` object for the pure budget caps. */
function claimOf(id: string, type: string): Claim {
	return {
		id,
		type,
		parent: "",
		statement: `断言 ${id} 成立`,
		falsifier: `出现 ${id} 的反例`,
		locator: "-",
		judgement: "manual: 由 PM 裁决",
		budget: 1,
		row: 1,
	};
}

let projectDir: string;

beforeEach(() => {
	projectDir = mkdtempSync(join(tmpdir(), "mw-claim-block-"));
	writeFileSync(join(projectDir, "decision-tool.ts"), "export const decision = 1;\n", "utf8");
	mkdirSync(join(projectDir, "evidence", "claims"), { recursive: true });
	writeFileSync(join(projectDir, "evidence", "claims", "qg.md"), "| C-01 | ok |\n", "utf8");
});

afterEach(() => {
	rmSync(projectDir, { recursive: true, force: true });
});

describe("parity-locked constants (T-06 reads these verbatim)", () => {
	it("keeps the four constant values and their order", () => {
		expect([...CLAIM_TYPES]).toEqual(["cmd", "grep", "struct", "manual"]);
		expect([...UNVERIFIED_REASONS]).toEqual([
			"budget",
			"no-access",
			"not-found",
			"ambiguous",
			"environment",
			"out-of-scope",
			"awaiting-input",
		]);
		expect(CLAIM_GATE_DEFAULT).toBe("advisory");
		expect(CLAIM_BUDGET).toEqual({
			perClaim: 6,
			callCap: 30,
			hardCap: 35,
			claimByteCap: 65536,
			byteCapMax: 393216,
		});
	});
});

// ── ① 正常 3 行 ─────────────────────────────────────────────────────────────

describe("parseClaimsBlock: canonical three rows", () => {
	it("parses id, type, three text cells, locator, judgement and budget", () => {
		const text = blockText([
			row(
				"C-01",
				"grep",
				"`decision-tool.ts` 不再读取 `.mw/decide-points.json`",
				"出现 `readFileSync` 命中该路径",
				"decision-tool.ts",
				"grep: readFileSync => count=0",
				"2",
			),
			row("C-02", "struct", "覆盖表 6 行齐全", "缺任一行", "decision-tool.ts", "shape: 覆盖表 6 行", "1"),
			row(
				"C-03",
				"cmd",
				"定向用例仍绿",
				"给出 rc≠0",
				"evidence/claims/qg.md#C-03",
				"cmd: node ../../node_modules/vitest/dist/cli.js --run test/x.test.ts => rc=0",
				"1",
			),
		]);
		const block = parseClaimsBlock(text);
		expect(block.present).toBe(true);
		expect(block.errors).toEqual([]);
		expect(block.claims.map((claim) => claim.id)).toEqual(["C-01", "C-02", "C-03"]);
		expect(block.claims[0]).toMatchObject({
			id: "C-01",
			type: "grep",
			parent: "",
			statement: "`decision-tool.ts` 不再读取 `.mw/decide-points.json`",
			falsifier: "出现 `readFileSync` 命中该路径",
			locator: "decision-tool.ts",
			judgement: "grep: readFileSync => count=0",
			budget: 2,
		});
		expect(block.claims[2]?.budget).toBe(1);
	});

	it("reports absence without a marker and tolerates a missing close marker", () => {
		expect(parseClaimsBlock("## 要求\n\n没有 claims 块。\n")).toEqual({ present: false, claims: [], errors: [] });
		const unterminated = blockText([row("C-01", "manual", "人工判断", "给出反例", "-", "manual: 由 PM 裁决", "2")], {
			close: false,
		});
		const withHeading = `${unterminated}\n## 交付格式\n\n${row("C-99", "manual", "块外的行", "反例", "-", "manual: x", "2")}\n`;
		const block = parseClaimsBlock(withHeading);
		expect(block.present).toBe(true);
		expect(block.claims.map((claim) => claim.id)).toEqual(["C-01"]);
	});
});

// ── ② 列序打乱 + 别名 + 全角 ────────────────────────────────────────────────

describe("parseClaimsBlock: column order, aliases and full-width cells", () => {
	it("accepts a shuffled header with `断言`, an extra column and `：｜` folding", () => {
		const text = [
			OPEN,
			"| 判据 | 预算 | 断言 | 定位 | 反证条件 | 类型 | 陈述 | 备注 |",
			"| --- | --- | --- | --- | --- | --- | --- | --- |",
			"｜ cmd：node x => rc=0 ｜ 1 ｜ C-01 ｜ evidence/claims/qg.md#C-01 ｜ 出现 rc≠0 ｜ cmd ｜ 定向用例仍绿 ｜ 忽略列 ｜",
			CLOSE,
		].join("\n");
		const block = parseClaimsBlock(text);
		expect(block.errors).toEqual([]);
		expect(block.claims).toHaveLength(1);
		expect(block.claims[0]).toMatchObject({
			id: "C-01",
			type: "cmd",
			statement: "定向用例仍绿",
			falsifier: "出现 rc≠0",
			locator: "evidence/claims/qg.md#C-01",
			judgement: "cmd:node x => rc=0",
			budget: 1,
		});
	});

	it("does not count a table inside a fenced code block and ignores a fenced marker", () => {
		const text = [
			OPEN,
			"```markdown",
			HEADER,
			SEPARATOR,
			row("C-99", "manual", "围栏内的示例", "反例", "-", "manual: x", "2"),
			"```",
			HEADER,
			SEPARATOR,
			row("C-01", "manual", "围栏外的真行", "给出反例", "-", "manual: 由 PM 裁决", "2"),
			CLOSE,
		].join("\n");
		const block = parseClaimsBlock(text);
		expect(block.present).toBe(true);
		expect(block.claims.map((claim) => claim.id)).toEqual(["C-01"]);
		expect(parseClaimsBlock(["```", OPEN, "```"].join("\n")).present).toBe(false);
	});
});

// ── ④ 子行 C-01.3 ───────────────────────────────────────────────────────────

describe("parseClaimsBlock: child rows", () => {
	it("accepts C-01.3 under a struct parent and inherits its type", () => {
		const text = blockText([
			row("C-01", "struct", "覆盖表 6 行齐全", "缺任一行", "decision-tool.ts", "shape: 覆盖表 6 行", "1"),
			row("C-01.3", "", "第 3 行齐全", "第 3 行缺失", "decision-tool.ts:3", "shape: 第 3 行", "1"),
		]);
		const block = parseClaimsBlock(text);
		expect(block.errors).toEqual([]);
		expect(block.claims.map((claim) => claim.id)).toEqual(["C-01", "C-01.3"]);
		expect(block.claims[1]).toMatchObject({ parent: "C-01", type: "struct" });
	});

	it("drops C-02.1 whose parent is not a struct and reports the row", () => {
		const text = blockText([
			row("C-02", "grep", "旧键不再被读取", "出现旧键命中", "decision-tool.ts", "grep: old_key => count=0", "1"),
			row("C-02.1", "", "子项", "子项反例", "decision-tool.ts", "grep: x => count=0", "1"),
		]);
		const block = parseClaimsBlock(text);
		expect(block.claims.map((claim) => claim.id)).toEqual(["C-02"]);
		expect(block.errors).toEqual([expect.stringMatching(/^claim:\d+:unparsable$/)]);
	});
});

// ── ⑤ 七种结构性缺失 ────────────────────────────────────────────────────────

describe("claimsGaps: the seven structural findings", () => {
	const rows = [
		row("C-01", "", "陈述一", "反证一", "decision-tool.ts", "grep: x => count=0", "1"),
		row("C-02", "shape", "陈述二", "反证二", "decision-tool.ts", "shape: 覆盖表", "1"),
		row("C-03", "grep", "", "反证三", "decision-tool.ts", "grep: x => count=0", "1"),
		row("C-04", "grep", "陈述四", "", "decision-tool.ts", "grep: x => count=0", "1"),
		row("C-05", "manual", "陈述五", "反证五", "", "manual: 由 PM 裁决", "2"),
		row("C-06", "manual", "陈述六", "反证六", "-", "", "2"),
		row("C-07", "manual", "陈述七", "反证七", "-", "manual: 由 PM 裁决", "-"),
	];
	const block = parseClaimsBlock(blockText(rows));
	const expected = [
		"claim:C-01:type",
		"claim:C-02:type",
		"claim:C-03:statement",
		"claim:C-04:falsifier",
		"claim:C-05:locator",
		"claim:C-06:judgement",
		"claim:C-07:budget",
	];

	it("names each missing element as claim:<id>:<element>", () => {
		expect(block.errors).toEqual([]);
		expect(claimsGaps(block, { projectDir, enforce: false })).toEqual(expected);
	});

	it("keeps structural gaps in enforce mode too (only soft findings upgrade)", () => {
		expect(claimsGaps(block, { projectDir, enforce: true })).toEqual(expected);
	});
});

// ── ⑥ enforce=false 时五类软 gap 降级 ───────────────────────────────────────

describe("claimsGaps: enforce is a grey switch for soft findings only", () => {
	it("suppresses type-prefix, cmd-locator, locator-unresolved, locator-range and tautology", () => {
		writeFileSync(join(projectDir, "big.ts"), "x".repeat(40_000), "utf8");
		const text = blockText([
			row("C-01", "grep", "模块 A 不再读取旧键", "出现旧键命中", "decision-tool.ts", "cmd: node x => rc=0", "1"),
			row("C-02", "cmd", "定向用例仍绿", "给出 rc≠0", "decision-tool.ts", "cmd: node x => rc=0", "1"),
			row("C-03", "grep", "模块 B 不再读取旧键", "出现旧键命中", "missing-file.ts", "grep: x => count=0", "1"),
			row("C-04", "struct", "覆盖表 6 行齐全", "缺任一行", "big.ts", "shape: 覆盖表 6 行", "1"),
			row("C-05", "manual", "断言 X 已修复", "断言 X 未修复", "-", "manual: 成立", "2"),
		]);
		const block = parseClaimsBlock(text);
		expect(block.errors).toEqual([]);
		expect(claimsGaps(block, { projectDir, enforce: false })).toEqual([]);
		expect(claimsGaps(block, { projectDir, enforce: true })).toEqual([
			"claim:C-01:type-prefix",
			"claim:C-02:cmd-locator",
			"claim:C-03:locator-unresolved",
			"claim:C-04:locator-range",
			"claim:C-05:tautology",
		]);
	});

	it("suppresses the claims:budget-sum and claims:manual-overflow aggregates", () => {
		const many = Array.from({ length: 41 }, (_, index) =>
			row(
				`C-${String(index + 1).padStart(2, "0")}`,
				"grep",
				`模块 ${index + 1} 不再读取旧键`,
				`出现第 ${index + 1} 处旧键命中`,
				"-",
				"grep: old_key => count=0",
				"1",
			),
		);
		const overflow = parseClaimsBlock(
			blockText([
				row("C-01", "manual", "断言一", "反例一", "-", "manual: 裁决", "2"),
				row("C-02", "manual", "断言二", "反例二", "-", "manual: 裁决", "2"),
				row("C-03", "manual", "断言三", "反例三", "-", "manual: 裁决", "2"),
				row("C-04", "manual", "断言四", "反例四", "-", "manual: 裁决", "2"),
			]),
		);
		const big = parseClaimsBlock(blockText(many));
		expect(claimsGaps(big, { projectDir, enforce: false })).toEqual([]);
		expect(claimsGaps(big, { projectDir, enforce: true })).toEqual(["claims:budget-sum:41>40"]);
		expect(claimsGaps(overflow, { projectDir, enforce: false })).toEqual([]);
		expect(claimsGaps(overflow, { projectDir, enforce: true })).toEqual(["claims:manual-overflow:4/4"]);
	});
});

// ── ⑦ cmd: TBD(...) 放行 ────────────────────────────────────────────────────

describe("claimsGaps: the pending `cmd: TBD(...)` channel", () => {
	it("accepts TBD with the cmd prefix and the D-005 evidence locator", () => {
		const block = parseClaimsBlock(
			blockText([
				row(
					"C-01",
					"cmd",
					"定向用例尚未写出",
					"给出 rc≠0",
					"evidence/claims/qg.md#C-01",
					"cmd: TBD(test/suite/claim-block.test.ts)",
					"1",
				),
			]),
		);
		expect(claimsGaps(block, { projectDir, enforce: true })).toEqual([]);
	});

	it("still flags a judgement that drops the type prefix", () => {
		const block = parseClaimsBlock(
			blockText([
				row("C-01", "cmd", "定向用例尚未写出", "给出 rc≠0", "evidence/claims/qg.md#C-01", "TBD(x.test.ts)", "1"),
			]),
		);
		expect(claimsGaps(block, { projectDir, enforce: true })).toEqual(["claim:C-01:type-prefix"]);
	});
});

// ── ⑧ 预算求和与两个上限 ────────────────────────────────────────────────────

describe("claimBudgetCaps: derived read budget (design §4, D-014)", () => {
	it("prices one claim at perClaim 6 calls / 65,536 B", () => {
		// The fetch cap is perClaim × n, not the Σ预算 planning weight: a single
		// grep claim buys 6 read/search calls (T-07 e2e: Σ预算 gave it 1).
		expect(claimBudgetCaps([claimOf("C-01", "grep")])).toEqual({ fileCap: 6, byteCap: 65_536 });
	});

	it("scales with the claim count: 5 claims => 30 / 327,680", () => {
		const claims = [
			claimOf("C-01", "grep"),
			claimOf("C-02", "struct"),
			claimOf("C-03", "cmd"),
			claimOf("C-04", "manual"),
			claimOf("C-05", "manual"),
		];
		// 5 × 6 = 30 = callCap; 5 × 65,536 = 327,680. The two manual claims no
		// longer change the file cap (that is the Σ预算 gate's job).
		expect(claimBudgetCaps(claims)).toEqual({ fileCap: 30, byteCap: 327_680 });
		console.log(
			`[VERIFY] claimBudgetCaps one=${JSON.stringify(claimBudgetCaps([claims[0] as Claim]))} ` +
				`five=${JSON.stringify(claimBudgetCaps(claims))}`,
		);
	});

	it("clamps at callCap 30 and byteCapMax 393,216 (8 claims)", () => {
		const eight = Array.from({ length: 8 }, (_, index) => claimOf(`C-${index + 1}`, "grep"));
		// 8 × 6 = 48 -> clamp 30; 8 × 65,536 = 524,288 -> clamp 393,216.
		expect(claimBudgetCaps(eight)).toEqual({ fileCap: 30, byteCap: 393_216 });
		console.log(`[VERIFY] claimBudgetCaps eight=${JSON.stringify(claimBudgetCaps(eight))}`);
	});

	it("clamps a flood at both ceilings and returns 0/0 for no claims", () => {
		const claims = Array.from({ length: 40 }, (_, index) => claimOf(`C-${index + 1}`, "grep"));
		expect(claimBudgetCaps(claims)).toEqual({ fileCap: 30, byteCap: 393_216 });
		expect(claimBudgetCaps([])).toEqual({ fileCap: 0, byteCap: 0 });
	});

	it("budgets 2 per manual claim toward the Σ40 cap", () => {
		const mixed = (manualCount: number, total: number) => {
			const rows = Array.from({ length: total }, (_, index) => {
				if (index < manualCount) {
					return row(
						`C-${String(index + 1).padStart(2, "0")}`,
						"manual",
						`人工断言 ${index + 1}`,
						`反例 ${index + 1}`,
						"-",
						"manual: 裁决",
						"2",
					);
				}
				return row(
					`C-${String(index + 1).padStart(2, "0")}`,
					"grep",
					`模块 ${index + 1} 不再读取旧键`,
					`出现第 ${index + 1} 处旧键命中`,
					"-",
					"grep: old_key => count=0",
					"1",
				);
			});
			return parseClaimsBlock(blockText(rows));
		};
		// 40 non-manual rows sum to exactly 40; the same 40 rows with 2 manual
		// rows sum to 42 because a manual claim is charged twice (2 stays under
		// the min(4, ceil(40/3)) manual cap, so only Σ fires).
		expect(claimsGaps(mixed(0, 40), { projectDir, enforce: true })).toEqual([]);
		expect(claimsGaps(mixed(2, 40), { projectDir, enforce: true })).toEqual(["claims:budget-sum:42>40"]);
	});

	it("caps manual rows at min(4, ceil(n/3))", () => {
		const make = (manualCount: number, total: number) => {
			const rows = Array.from({ length: total }, (_, index) => {
				const type = index < manualCount ? "manual" : "grep";
				return type === "manual"
					? row(
							`C-${String(index + 1).padStart(2, "0")}`,
							type,
							`人工断言 ${index + 1}`,
							`反例 ${index + 1}`,
							"-",
							"manual: 裁决",
							"2",
						)
					: row(
							`C-${String(index + 1).padStart(2, "0")}`,
							type,
							`模块 ${index + 1} 不再读取旧键`,
							`出现第 ${index + 1} 处旧键命中`,
							"-",
							"grep: old_key => count=0",
							"1",
						);
			});
			return parseClaimsBlock(blockText(rows));
		};
		// n=3 -> ceil(3/3)=1: three manual rows overflow.
		expect(claimsGaps(make(3, 3), { projectDir, enforce: true })).toEqual(["claims:manual-overflow:3/3"]);
		// n=9 -> ceil(9/3)=3: three manual rows are still legal.
		expect(claimsGaps(make(3, 9), { projectDir, enforce: true })).toEqual([]);
	});
});

// ── ⑨ 同义反复正反例 ────────────────────────────────────────────────────────

describe("claimsGaps: tautology judge (RQ-3 B-5)", () => {
	it("flags a restatement that only differs by a negation word", () => {
		const block = parseClaimsBlock(
			blockText([row("C-01", "manual", "断言 X 已修复", "断言 X 未修复", "-", "manual: 成立", "2")]),
		);
		expect(claimsGaps(block, { projectDir, enforce: true })).toEqual(["claim:C-01:tautology"]);
	});

	it("accepts a falsifier with a new artifact token in the judgement", () => {
		const block = parseClaimsBlock(
			blockText([
				row(
					"C-01",
					"grep",
					"`decision-tool.ts` 不再读取 `.mw/decide-points.json`",
					"出现 `readFileSync` 命中该路径",
					"decision-tool.ts",
					"grep: readFileSync => count=0",
					"1",
				),
			]),
		);
		expect(claimsGaps(block, { projectDir, enforce: true })).toEqual([]);
	});
});

// ── ⑩ 大文件无行段 → locator-range ──────────────────────────────────────────

describe("claimsGaps: locator size and range", () => {
	it("requires a line segment for a file over 32,768 B", () => {
		writeFileSync(join(projectDir, "big.ts"), "x".repeat(40_000), "utf8");
		const withoutRange = parseClaimsBlock(
			blockText([row("C-01", "struct", "覆盖表 6 行齐全", "缺任一行", "big.ts", "shape: 覆盖表 6 行", "1")]),
		);
		expect(claimsGaps(withoutRange, { projectDir, enforce: true })).toEqual(["claim:C-01:locator-range"]);
		const withRange = parseClaimsBlock(
			blockText([row("C-01", "struct", "覆盖表 6 行齐全", "缺任一行", "big.ts:1-40", "shape: 覆盖表 6 行", "1")]),
		);
		expect(claimsGaps(withRange, { projectDir, enforce: true })).toEqual([]);
	});

	it("leaves a small file without a line segment alone", () => {
		const block = parseClaimsBlock(
			blockText([
				row("C-01", "struct", "覆盖表 6 行齐全", "缺任一行", "decision-tool.ts", "shape: 覆盖表 6 行", "1"),
			]),
		);
		expect(claimsGaps(block, { projectDir, enforce: true })).toEqual([]);
	});

	it("treats a bare symbol, a missing file and an outside path as unresolved", () => {
		const block = parseClaimsBlock(
			blockText([
				row("C-01", "grep", "符号不再出现", "出现该符号", "missingDecisionStateFields", "grep: x => count=0", "1"),
				row("C-02", "grep", "符号不再出现", "出现该符号", "no-such-file.ts", "grep: x => count=0", "1"),
				row("C-03", "grep", "符号不再出现", "出现该符号", "../outside-project.ts", "grep: x => count=0", "1"),
			]),
		);
		expect(claimsGaps(block, { projectDir, enforce: true })).toEqual([
			"claim:C-01:locator-unresolved",
			"claim:C-02:locator-unresolved",
			"claim:C-03:locator-unresolved",
		]);
	});
});
