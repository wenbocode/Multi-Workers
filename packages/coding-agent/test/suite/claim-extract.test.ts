/**
 * claim-extract.test.ts — E1 structured claim extraction (T-03, key
 * `claim-driven-review-orchestration`; spec AC-E1, design §2.1).
 *
 * Locks `shared/claim-extract.ts`, the zero-LLM rung of stage 0: rows that are
 * already a list (QG findings, spec AC rows, diff hunks, anti-pattern hits)
 * become `Claim` rows with a deterministic `C-xx` id, a prefix-derived type, a
 * `path:a-b` / `path:line` 定位 and a 预算.
 *
 * Fixtures are inline literals: no project file, no temp dir, no model.
 *
 * Note on `falsifier` (cards T-03 → T-06): T-03 pinned E1's `falsifier` to `""`
 * while `claimsGaps`' structural rule requires a non-empty one, and the card
 * forbade rewriting the validator. T-06 resolved the conflict without softening
 * the validator: a source row may carry its own `falsifier`, mechanical sources
 * (`antiPatternHits`, `diffHunks`) derive an executable one, prose sources
 * (`findings`/`acRows`) and every `manual` claim do not, and the validator's
 * `claim:<id>:falsifier` finding is renamed to `extract:falsifier-missing:<id>`
 * (same problem, one wording, claim kept).
 */

import { describe, expect, it } from "vitest";
import { type ClaimExtractInput, extractClaims } from "../../src/extensions/agent-team-loop/shared/claim-extract.ts";

describe("extractClaims — source rows become claims (AC-E1)", () => {
	it("maps two findings rows to C-01/C-02 with prefix-derived types", () => {
		const result = extractClaims({
			findings: [
				{ text: "检查命令仍通过", locator: "evidence/qg.md:12", judgement: "cmd:npm run check" },
				{ text: "旧入口已删除", locator: "src/legacy.ts:40", judgement: "grep:legacyRuntime" },
			],
		});

		expect(result.sourceRows).toBe(2);
		expect(
			result.claims.map((claim) => [
				claim.id,
				claim.type,
				claim.statement,
				claim.locator,
				claim.budget,
				claim.falsifier,
				claim.row,
				claim.parent,
			]),
		).toEqual([
			["C-01", "cmd", "检查命令仍通过", "evidence/qg.md:12", 1, "", 1, ""],
			["C-02", "grep", "旧入口已删除", "src/legacy.ts:40", 1, "", 2, ""],
		]);
		// Prose rows never derive a falsifier, so the validator's structural
		// finding is renamed 1:1 instead of being dropped or softening the rule.
		expect(result.gaps).toEqual(["extract:falsifier-missing:C-01", "extract:falsifier-missing:C-02"]);
	});

	it("anchors a diff hunk at path:start-end with budget 2 and manual default", () => {
		const result = extractClaims({
			diffHunks: [
				{
					path: "src/claim-extract.ts",
					start: 10,
					end: 24,
					statement: "新增提取器不改变既有导出",
					judgement: "  fs: claim-extract.ts exports",
				},
				{ path: "src/claim-pack.ts", start: 1, end: 1, statement: "装箱单元不改 claim 语义" },
			],
		});

		expect(result.claims.map((claim) => [claim.id, claim.locator, claim.type, claim.budget])).toEqual([
			["C-01", "src/claim-extract.ts:10-24", "struct", 2],
			["C-02", "src/claim-pack.ts:1-1", "manual", 2],
		]);
		// No 判据 supplied ⇒ type defaults to manual and the 判据 cell stays empty
		// (E1 does not invent one); that manual hunk also derives no falsifier, so
		// both missing cells are reported for C-02 while C-01 derives one.
		expect(result.claims[1]?.judgement).toBe("");
		expect(result.gaps).toEqual(["extract:falsifier-missing:C-02", "claim:C-02:judgement"]);
	});

	it("anchors an anti-pattern hit at path:line with budget 1", () => {
		const result = extractClaims({
			antiPatternHits: [
				{ path: "src/deep/b.ts", line: 33, pattern: "console.log" },
				{ path: "src/deep/b.ts", line: 41, pattern: "any", judgement: "grep:no any" },
			],
		});

		expect(
			result.claims.map((claim) => [claim.id, claim.locator, claim.type, claim.budget, claim.statement]),
		).toEqual([
			["C-01", "src/deep/b.ts:33", "manual", 1, "反模式命中：console.log"],
			["C-02", "src/deep/b.ts:41", "grep", 1, "反模式命中：any"],
		]);
		expect(result.gaps).toEqual(["extract:falsifier-missing:C-01", "claim:C-01:judgement"]);
	});

	it("returns an empty result for empty and omitted input", () => {
		expect(extractClaims({})).toEqual({ claims: [], gaps: [], sourceRows: 0 });
		expect(extractClaims()).toEqual({ claims: [], gaps: [], sourceRows: 0 });
	});

	it("is idempotent: the same input twice is deeply equal", () => {
		const input: ClaimExtractInput = {
			findings: [{ text: "finding 一", locator: "src/a.ts:3", judgement: "cmd:npm run check" }],
			acRows: [{ text: "AC-E1", locator: "spec.md:97", judgement: "manual: 人工裁决" }],
			diffHunks: [{ path: "src/a.ts", start: 3, end: 9, statement: "改动面被覆盖" }],
			antiPatternHits: [{ path: "src/a.ts", line: 7, pattern: "TODO" }],
		};

		const first = extractClaims(input);
		const second = extractClaims(input);

		expect(JSON.stringify(second)).toBe(JSON.stringify(first));
		expect(second).toEqual(first);
		expect(first.sourceRows).toBe(4);
	});

	it("reports a hunk without a statement as a lost source row", () => {
		const result = extractClaims({
			diffHunks: [
				{ path: "src/a.ts", start: 1, end: 4, statement: "   " },
				{ path: "src/a.ts", start: 10, end: 12, statement: "保持 A 行为", judgement: "cmd:npm run check" },
			],
		});

		expect(result.sourceRows).toBe(2);
		expect(result.claims.map((claim) => claim.id)).toEqual(["C-01"]);
		expect(result.gaps).toEqual(["extract:lost-source-row:0"]);

		// The index is 0-based INSIDE its own source list, so each source restarts.
		const mixed = extractClaims({
			findings: [{ text: "  ", locator: "src/a.ts:1", judgement: "" }],
			acRows: [{ text: "AC 行", locator: "src/a.ts:1", judgement: "manual: 人工" }],
		});
		expect(mixed.gaps[0]).toBe("extract:lost-source-row:0");
		expect(mixed.claims.map((claim) => claim.id)).toEqual(["C-01"]);
	});

	it("reports a locator outside the declared change face as foreign", () => {
		const result = extractClaims({
			findings: [
				{
					text: "改动外的文件也被检查",
					locator: "src/elsewhere.ts:9",
					judgement: "grep:foo src/elsewhere.ts",
				},
				{ text: "符号定位不参与对账", locator: "claimBudgetCaps", judgement: "manual: 人工确认" },
			],
			diffHunks: [{ path: "src/a.ts", start: 3, end: 8, statement: "改动面被覆盖", judgement: "cmd:npm run check" }],
		});

		expect(result.claims.map((claim) => claim.id)).toEqual(["C-01", "C-02", "C-03"]);
		expect(result.gaps.filter((gap) => gap.startsWith("extract:foreign-locator:"))).toEqual([
			"extract:foreign-locator:C-01",
		]);

		// Segment-suffix tolerance: an absolute 定位 still matches a relative hunk path.
		const absolute = extractClaims({
			findings: [{ text: "绝对路径定位", locator: "/repo/src/a.ts:5", judgement: "manual: 人工" }],
			diffHunks: [{ path: "src/a.ts", start: 3, end: 8, statement: "改动面被覆盖", judgement: "cmd:npm run check" }],
		});
		expect(absolute.gaps.filter((gap) => gap.startsWith("extract:foreign-locator:"))).toEqual([]);

		// With no hunk/hit path declared there is no change face to be foreign to.
		const proseOnly = extractClaims({
			findings: [{ text: "散文清单", locator: "evidence/qg.md:9", judgement: "manual: 人工" }],
		});
		expect(proseOnly.gaps.filter((gap) => gap.startsWith("extract:lost-source-row:"))).toEqual([]);
		expect(proseOnly.gaps.filter((gap) => gap.startsWith("extract:foreign-locator:"))).toEqual([]);
	});

	it("folds full-width colons and padding whitespace without inventing gaps", () => {
		const result = extractClaims({
			findings: [
				{ text: "命令判据用全角冒号", locator: "src/a.ts:1-4", judgement: "  CMD ： npm run check  " },
				{ text: "grep 判据容忍制表符", locator: "src/a.ts:9", judgement: "\tgrep\t： npm run check" },
				{ text: "无前缀走 manual", locator: "-", judgement: "人工确认" },
			],
		});

		expect(result.claims.map((claim) => claim.type)).toEqual(["cmd", "grep", "manual"]);
		// A false gap here would be `extract:*`, `claim:*:type`, `:judgement` or
		// `:locator`; the only remaining finding is the prose rows' missing
		// falsifier, under its single wording.
		expect(result.gaps).toEqual([
			"extract:falsifier-missing:C-01",
			"extract:falsifier-missing:C-02",
			"extract:falsifier-missing:C-03",
		]);
		expect(result.claims.map((claim) => claim.judgement.trim())).toEqual([
			"cmd: npm run check",
			"grep: npm run check",
			"人工确认",
		]);
	});

	it("widens the id to three digits from the 100th claim on", () => {
		const findings = Array.from({ length: 100 }, (_, index) => ({
			text: `finding ${index}`,
			locator: `src/f${index}.ts:1`,
			judgement: "manual: 人工",
		}));

		const result = extractClaims({ findings });

		expect(result.claims).toHaveLength(100);
		expect(result.claims[0]?.id).toBe("C-01");
		expect(result.claims[98]?.id).toBe("C-99");
		expect(result.claims[99]?.id).toBe("C-100");
	});

	it("keeps sourceRows equal to claims plus lost rows", () => {
		const result = extractClaims({
			findings: [
				{ text: "已覆盖", locator: "src/a.ts:1", judgement: "cmd:npm run check" },
				{ text: "   ", locator: "", judgement: "" },
			],
			acRows: [{ text: "AC-E1 达成", locator: "src/a.ts:2", judgement: "manual: 人工" }],
			diffHunks: [
				{ path: "src/a.ts", start: 2, end: 6, statement: "hunk 被覆盖" },
				{ path: "src/a.ts", start: 9, end: 4, statement: "反向区间" },
			],
			antiPatternHits: [{ path: "src/a.ts", line: 0, pattern: "bad" }],
		});

		const lost = result.gaps.filter((gap) => gap.startsWith("extract:lost-source-row:"));
		expect(result.sourceRows).toBe(6);
		expect(result.claims.map((claim) => claim.id)).toEqual(["C-01", "C-02", "C-03"]);
		expect(lost).toEqual(["extract:lost-source-row:1", "extract:lost-source-row:1", "extract:lost-source-row:0"]);
		expect(result.claims.length + lost.length).toBe(result.sourceRows);
	});

	it("reports bad row shapes as lost rows instead of throwing (P-048)", () => {
		const input = {
			findings: "not-an-array",
			acRows: [{ text: 42, locator: null, judgement: 7 }],
			diffHunks: [null],
		} as unknown as ClaimExtractInput;

		expect(() => extractClaims(input)).not.toThrow();
		const result = extractClaims(input);
		expect(result.claims).toEqual([]);
		expect(result.gaps).toEqual(["extract:lost-source-row:0", "extract:lost-source-row:0"]);
		expect(result.sourceRows).toBe(2);
	});

	// ── T-06: falsifier contract (no validator softening) ────────────────────

	it("keeps a caller-supplied falsifier on a prose row verbatim", () => {
		const result = extractClaims({
			findings: [
				{
					text: "检查命令仍通过",
					locator: "evidence/qg.md:12",
					judgement: "cmd:npm run check",
					falsifier: "  在 evidence/qg.md:12 处找不到 npm run check 的通过记录  ",
				},
			],
			acRows: [
				{
					text: "AC-001 达成",
					locator: "spec.md:97",
					judgement: "manual: 人工裁决",
					falsifier: "评审者判定 AC-001 未达成",
				},
			],
		});

		expect(result.claims.map((claim) => [claim.id, claim.type, claim.falsifier])).toEqual([
			["C-01", "cmd", "在 evidence/qg.md:12 处找不到 npm run check 的通过记录"],
			["C-02", "manual", "评审者判定 AC-001 未达成"],
		]);
		// A supplied falsifier is not reported, and prose rows never get a derived one.
		expect(result.gaps.filter((gap) => gap.includes("falsifier"))).toEqual([]);
	});

	it("keeps a prose claim without a falsifier and reports exactly one gap", () => {
		const result = extractClaims({
			findings: [{ text: "旧入口已删除", locator: "src/legacy.ts:40", judgement: "grep:legacyRuntime" }],
		});

		// Coverage is kept: the claim stays, only the gap is reported.
		expect(result.claims).toHaveLength(1);
		expect(result.claims[0]?.falsifier).toBe("");
		expect(result.gaps).toEqual(["extract:falsifier-missing:C-01"]);
		// One wording per problem: the validator's own spelling is replaced, not added.
		expect(result.gaps).not.toContain("claim:C-01:falsifier");
	});

	it("derives an executable falsifier for an anti-pattern hit", () => {
		const result = extractClaims({
			antiPatternHits: [{ path: "src/deep/b.ts", line: 33, pattern: "console.log", judgement: "grep:console.log" }],
		});

		expect(result.claims[0]?.falsifier).toBe("在 src/deep/b.ts:33 处找不到 console.log");
		expect(result.gaps.filter((gap) => gap.includes("falsifier"))).toEqual([]);

		// A caller-supplied cell wins over the derivation.
		const supplied = extractClaims({
			antiPatternHits: [
				{
					path: "src/deep/b.ts",
					line: 33,
					pattern: "console.log",
					judgement: "grep:console.log",
					falsifier: "src/deep/b.ts:33 仍是 console.log",
				},
			],
		});
		expect(supplied.claims[0]?.falsifier).toBe("src/deep/b.ts:33 仍是 console.log");
	});

	it("derives a hunk falsifier that restates no 判据", () => {
		const result = extractClaims({
			diffHunks: [
				{ path: "src/a.ts", start: 7, end: 12, statement: "导出面未变", judgement: "shape: src/a.ts exports" },
			],
		});

		const falsifier = result.claims[0]?.falsifier ?? "";
		expect(falsifier).toContain("hunk");
		expect(falsifier).toBe("该 hunk 未体现陈述的改动（符号未改 / 改在其它定位）");
		expect(falsifier).not.toContain("判据不成立");
		expect(result.gaps.filter((gap) => gap.includes("falsifier"))).toEqual([]);
	});

	it("normalizes fs:/struct: to the canonical shape: prefix", () => {
		const result = extractClaims(
			{
				diffHunks: [
					{ path: "src/a.ts", start: 1, end: 4, statement: "导出面未变", judgement: "  fs: src/a.ts exports" },
					{ path: "src/b.ts", start: 2, end: 5, statement: "形状判据成立", judgement: "STRUCT：shape check" },
				],
			},
			{ enforce: true },
		);

		expect(result.claims.map((claim) => [claim.type, claim.judgement])).toEqual([
			["struct", "shape: src/a.ts exports"],
			["struct", "shape:shape check"],
		]);
		// The rewrite is what keeps this advisory quiet (enforce: true shows it).
		expect(result.gaps.filter((gap) => gap.endsWith(":type-prefix"))).toEqual([]);
	});

	it("keeps lowercase canonical cmd:/grep:/manual: prefixes and leaves others alone", () => {
		const result = extractClaims({
			findings: [
				{ text: "命令判据", locator: "src/a.ts:1", judgement: "  CMD : npm run check" },
				{ text: "grep 判据", locator: "src/a.ts:2", judgement: "Grep\t： legacyRuntime" },
				{ text: "未知前缀", locator: "src/a.ts:3", judgement: "other: 人工确认" },
			],
		});

		expect(result.claims.map((claim) => [claim.type, claim.judgement])).toEqual([
			["cmd", "cmd: npm run check"],
			["grep", "grep: legacyRuntime"],
			["manual", "other: 人工确认"],
		]);
	});

	it("never derives a falsifier for a manual claim", () => {
		const result = extractClaims({
			antiPatternHits: [{ path: "src/a.ts", line: 5, pattern: "TODO" }],
			diffHunks: [{ path: "src/a.ts", start: 1, end: 2, statement: "人工判断的改动" }],
		});

		expect(result.claims.map((claim) => [claim.id, claim.type, claim.falsifier])).toEqual([
			["C-01", "manual", ""],
			["C-02", "manual", ""],
		]);
		expect(result.gaps.filter((gap) => gap.startsWith("extract:falsifier-missing:"))).toEqual([
			"extract:falsifier-missing:C-01",
			"extract:falsifier-missing:C-02",
		]);
		// A missing falsifier never throws and never drops a claim.
		expect(result.claims).toHaveLength(2);
	});
});
