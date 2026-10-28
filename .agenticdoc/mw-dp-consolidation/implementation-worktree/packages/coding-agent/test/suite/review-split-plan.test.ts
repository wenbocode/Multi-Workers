/**
 * review-split-plan.test.ts — the `plan`-tier composer (card T-10, key
 * `claim-driven-review-orchestration`, spec AC-S2).
 *
 * Locks the pure contract of `pm/review-split-plan.ts`: the two claim-source
 * orders (claims block first, deterministic prose downgrade second, never an
 * invented claim), the packing wiring (`<taskKey>-u<k>` / `workers/<...>`),
 * the frozen `[review-split] …` receipt wording, the L0 arithmetic
 * (`asks - mapped === unmapped.length`), the derived-cap inflation (no
 * division by zero), the honest manifest self-check (`l1=ok`) and idempotency.
 *
 * Fixtures are inline card texts: no project files, no clock, no model.
 */

import { describe, expect, it } from "vitest";
import {
	canonicalizeLocator,
	planReviewSplit,
	type ReviewSplitPlan,
	type ReviewSplitPlanInput,
	serializeUnitCardText,
} from "../../src/extensions/agent-team-loop/pm/review-split-plan.ts";
import { type Claim, parseClaimsBlock } from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";
import { verifySplitManifest } from "../../src/extensions/agent-team-loop/shared/split-manifest.ts";

/** The frozen receipt wording (module doc of `review-split-plan.ts`). */
const RECEIPT_RE =
	/^\[review-split\] mode=(plan|on) units=\d+ claims=\d+ cap=\d+ capSum=\d+ inflation=\d+\.\d{2} l0=\d+\/\d+ fals=\d+ l1=(ok|gaps:\d+)$/;

/** A review card that already carries machine claims (the claims-block path). */
function claimsBlockCard(count = 11): string {
	const rows: string[] = [
		"| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |",
		"| --- | --- | --- | --- | --- | --- | --- |",
	];
	for (let i = 1; i <= count; i++) {
		const id = `C-${String(i).padStart(2, "0")}`;
		rows.push(
			`| ${id} | grep | 第 ${i} 条断言 | 在 src/file${id}.ts:${i} 处找不到 pattern-${i} | src/file${id}.ts:${i} | grep: pattern-${i} | 1 |`,
		);
	}
	return [
		"# 复查卡 review-claims",
		"",
		"## 要求",
		"",
		"- 逐条取证（本行不含定位，claims 块优先，因此不参与 L0）。",
		"",
		"<!-- mw-claims: v1 -->",
		...rows,
		"<!-- /mw-claims -->",
		"",
		"## 检查项",
		"",
		"- 散文条目不应被使用：见 `src/prose.ts:9`。",
	].join("\n");
}

/**
 * A prose card: `locators` entries with a `path:line` under `## 检查项` and
 * `plain` entries without any locator (the L0 `unmapped` asks).
 */
function proseCard(locators: number, plain: number): string {
	const lines: string[] = ["# 复查卡 review-prose", "", "## 检查项", ""];
	for (let i = 1; i <= locators; i++) {
		lines.push(`- \`apps/api/src/handler${i}.ts:${i * 10}\` 的错误分支未覆盖，应补一条断言。`);
	}
	for (let i = 1; i <= plain; i++) {
		lines.push(`- 整体风格检查第 ${i} 项（无定位，不可机检）。`);
	}
	lines.push("", "## 审查要求", "", "```", "- `src/fenced.ts:1` 这里在代码块里，不算条目。", "```");
	lines.push("", "## 其它", "", "- `src/other.ts:3` 不在三个扫描标题下，不算条目。");
	return lines.join("\n");
}

function planOf(
	cardText: string,
	mode: "plan" | "on" = "plan",
	taskKey = "review-task",
	index?: Record<string, string>,
): ReviewSplitPlan {
	const input: ReviewSplitPlanInput = { taskKey, projectDir: "/tmp/does-not-exist", cardText, mode, acIndex: index };
	return planReviewSplit(input);
}

/** `L0` invariant card T-12 item 4 requires on EVERY branch, no-source included. */
function expectAskCoverage(plan: ReviewSplitPlan, expected: { asks: number; mapped: number }): void {
	expect(plan.l0.asks).toBe(expected.asks);
	expect(plan.l0.mapped).toBe(expected.mapped);
	expect(plan.l0.asks - plan.l0.mapped).toBe(plan.l0.unmapped.length);
	expect(plan.l0.unmapped).toHaveLength(expected.asks - expected.mapped);
	expect(plan.receipt).toContain(` l0=${expected.mapped}/${expected.asks} `);
}

/** `AC-001`…`AC-<count>` → `spec.md:<i>` (the index `review-split-gate.ts` builds). */
function acIndex(count = 13): Record<string, string> {
	const index: Record<string, string> = {};
	for (let i = 1; i <= count; i++) index[`AC-${String(i).padStart(3, "0")}`] = `spec.md:${i}`;
	return index;
}

/**
 * A card in the measured QG shape (`evidence/m1-exit-probe-20261022.md`): the
 * 定位 live in 上下文/被审对象, the asks live under the given 要求 heading.
 */
function qgCard(heading: string, asks: readonly string[]): string {
	return [
		"# 复查卡 QG-review-2",
		"",
		"## 上下文",
		"",
		"被审对象：`.agenticdoc/key/spec.md`（AC-001 到 AC-013），证据 `evidence/m1.md:1`。",
		"",
		heading,
		"",
		...asks,
		"",
	].join("\n");
}

describe("planReviewSplit", () => {
	it("① 11 条 claims 块卡 → units ≥ 1 且 ids 并集等于原 11 条", () => {
		const plan = planOf(claimsBlockCard(11));

		expect(plan.manifest).toBeDefined();
		const manifest = plan.manifest!;
		expect(manifest.units.length).toBeGreaterThanOrEqual(1);
		expect(manifest.ids).toHaveLength(11);
		expect(manifest.ids).toEqual(Array.from({ length: 11 }, (_, i) => `C-${String(i + 1).padStart(2, "0")}`));
		// The unit id sets are the manifest id set, each claim exactly once.
		const union = manifest.units.flatMap((unit) => unit.ids);
		expect(union).toEqual(manifest.ids);
		expect(new Set(union).size).toBe(11);
		// Unit naming: `<taskKey>-u<k>` and a per-unit write face.
		for (const unit of manifest.units) {
			expect(unit.taskKey).toBe(`review-task-u${unit.k}`);
			expect(unit.writeFace).toBe(`workers/review-task-u${unit.k}`);
			expect(unit.sha256).toMatch(/^[0-9a-f]{64}$/);
		}
	});

	it("② 回执行前缀与字段名逐字匹配冻结格式", () => {
		const plan = planOf(claimsBlockCard(11));

		expect(plan.receipt).toMatch(RECEIPT_RE);
		expect(plan.receipt).toContain("[review-split] mode=plan units=");
		expect(plan.receipt).toContain(" claims=11 ");
		expect(plan.receipt).toContain(" inflation=");
		expect(plan.receipt).toContain(" l0=");
		expect(plan.receipt).toContain(" fals=");
		expect(plan.receipt).toContain("l0=11/11 fals=0 l1=ok");
		expect(plan.receipt.indexOf(" fals=")).toBeLessThan(plan.receipt.indexOf(" l1="));
		expect(plan.receipt.endsWith(" l1=ok")).toBe(true);
		expect(plan.receipt).not.toContain("gap=no-source");
		// `mode=on` keeps the same field order.
		const onPlan = planOf(proseCard(4, 0), "on");
		expect(onPlan.receipt).toMatch(RECEIPT_RE);
		expect(onPlan.receipt.startsWith("[review-split] mode=on units=")).toBe(true);
		expect(onPlan.manifest!.mode).toBe("on");
	});

	it("③ l0 映射算术自洽（asks - mapped === unmapped.length）", () => {
		const plan = planOf(proseCard(4, 2));
		const l0 = plan.manifest!.l0;

		expect(l0.asks).toBe(6);
		expect(l0.mapped).toBe(4);
		expect(l0.unmapped).toHaveLength(2);
		expect(l0.asks - l0.mapped).toBe(l0.unmapped.length);
		expect(l0.unmapped.every((summary) => summary.length > 0 && summary.length <= 80)).toBe(true);
		// The receipt mirrors the same numbers.
		expect(plan.receipt).toContain(` l0=${l0.mapped}/${l0.asks} `);
		// Fenced blocks and other H2 sections contribute no ask.
		expect(plan.manifest!.ids).toHaveLength(4);
	});

	it("④ 散文卡 4 条带 path:line 的条目 → 4 条 manual claim + falsifier-missing 计数", () => {
		const plan = planOf(proseCard(4, 0));

		expect(plan.manifest).toBeDefined();
		expect(plan.manifest!.ids).toHaveLength(4);
		const missing = plan.gaps.filter((gap) => gap.startsWith("extract:falsifier-missing:"));
		expect(missing).toHaveLength(4);
		expect(missing).toEqual([
			"extract:falsifier-missing:C-01",
			"extract:falsifier-missing:C-02",
			"extract:falsifier-missing:C-03",
			"extract:falsifier-missing:C-04",
		]);
		// Every claim is manual-only, so packing reports it twice (never silently).
		expect(plan.gaps.filter((gap) => gap.endsWith(":manual-only"))).toHaveLength(2);
		expect(plan.receipt).toContain("l1=gaps:2");
		// No claim is invented: the asks equal the entries with a locator.
		expect(plan.manifest!.l0.asks).toBe(4);
		expect(plan.manifest!.l0.mapped).toBe(4);
	});

	it("⑤ 无一条目含 path:line → units=0 + extract:no-source，且不抛异常", () => {
		const card = ["# 复查卡", "", "## 要求", "", "- 读一遍代码。", "- 再读一遍。", ""].join("\n");

		let plan: ReviewSplitPlan | undefined;
		expect(() => {
			plan = planOf(card);
		}).not.toThrow();
		const result = plan!;
		expect(result.gaps).toEqual(["extract:no-source"]);
		expect(result.manifest).toBeUndefined();
		expect(result.manifestText).toBeUndefined();
		expect(result.receipt).toContain("units=0");
		expect(result.receipt).toContain("claims=0");
		expect(result.receipt.endsWith(" gap=no-source")).toBe(true);
		expect(result.l0.unmapped).toHaveLength(2);
		expect(result.receipt).toMatch(
			/^\[review-split\] mode=plan units=0 claims=0 cap=0 capSum=0 inflation=0\.00 l0=0\/2 fals=0 l1=ok gap=no-source$/,
		);
	});

	it("⑥ inflation = capSum / cap，cap = 0 时不除零（输出 0.00）", () => {
		// 11 grep claims: 5 + 5 + 1 per unit → cap = min(30, 6×11) = 30,
		// capSum = 30 + 30 + 6 = 66, inflation = 2.20.
		const plan = planOf(claimsBlockCard(11));
		expect(plan.receipt).toContain("cap=30 capSum=66 inflation=2.20");

		// No claims at all → cap = 0, no Infinity/NaN.
		const empty = planOf("");
		expect(empty.receipt).toContain("cap=0 capSum=0 inflation=0.00");
		expect(empty.receipt).not.toContain("Infinity");
		expect(empty.receipt).not.toContain("NaN");
	});

	it("⑦ 诚实构建时 manifest 自检 l1=ok", () => {
		const card = claimsBlockCard(11);
		const plan = planOf(card);

		expect(plan.gaps).toEqual([]);
		expect(plan.receipt.endsWith("l1=ok")).toBe(true);
		expect(verifySplitManifest(plan.manifest!)).toEqual([]);
		// The serialized artifact re-verifies against the live parent text.
		const reparsed = JSON.parse(plan.manifestText!) as typeof plan.manifest;
		expect(verifySplitManifest(reparsed!, { parentText: card })).toEqual([]);
		expect(reparsed!.selfSha256).toBe(plan.manifest!.selfSha256);
	});

	it("⑧ 幂等（同一输入两次 receipt 相同）", () => {
		const card = proseCard(4, 2);
		const first = planOf(card);
		const second = planOf(card);

		expect(second.receipt).toBe(first.receipt);
		expect(second.manifestText).toBe(first.manifestText);
		expect(second.gaps).toEqual(first.gaps);
		expect(second.manifest).toEqual(first.manifest);
	});

	it("⑨ 单元卡七列表逐字复用母卡单元格且可回读", () => {
		const claims: Claim[] = [
			{
				id: "C-01",
				type: "grep",
				parent: "",
				statement: "错误分支未覆盖",
				falsifier: "在 apps/api/src/handler.ts:10 处找不到该分支",
				locator: "apps/api/src/handler.ts:10",
				judgement: "grep: 错误分支未覆盖",
				budget: 2,
				row: 3,
			},
			{
				id: "C-02",
				type: "manual",
				parent: "",
				statement: "命名一致性",
				falsifier: "",
				locator: "apps/api/src/naming.ts:7",
				judgement: "manual: 命名一致性",
				budget: Number.NaN,
				row: 4,
			},
		];
		const text = serializeUnitCardText({ taskKey: "review-task-u1", claims });
		const reparsed = parseClaimsBlock(text);

		expect(text).toContain("| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |");
		expect(reparsed.claims.map((claim) => claim.id)).toEqual(["C-01", "C-02"]);
		expect(reparsed.claims[0]!.statement).toBe(claims[0]!.statement);
		expect(reparsed.claims[0]!.falsifier).toBe(claims[0]!.falsifier);
		expect(reparsed.claims[0]!.locator).toBe(claims[0]!.locator);
		expect(reparsed.claims[0]!.judgement).toBe(claims[0]!.judgement);
		expect(reparsed.claims[0]!.budget).toBe(2);
		// A NaN budget has no cell text to preserve and is emitted empty.
		expect(reparsed.claims[1]!.judgement).toBe("manual: 命名一致性");
		expect(Number.isNaN(reparsed.claims[1]!.budget)).toBe(true);
	});

	it("⑩ claims 块优先于散文降级（不重复提取）", () => {
		const plan = planOf(claimsBlockCard(3));

		expect(plan.manifest!.ids).toEqual(["C-01", "C-02", "C-03"]);
		expect(plan.manifest!.l0.asks).toBe(3);
		expect(plan.manifest!.l0.unmapped).toEqual([]);
		// The prose entry under `## 检查项` was not used.
		expect(plan.gaps.filter((gap) => gap.startsWith("extract:"))).toEqual([]);
	});

	it("⑪ `path:a-b` 区间定位被识别（同一定位的两条降级条目合成一个单元）", () => {
		const card = [
			"# 卡",
			"",
			"## 审查要求",
			"",
			"- `src/range.ts:10-20` 区间内不得出现 TODO。",
			"- `src/range.ts:10-20` 区间内不得吞异常。",
			"",
		].join("\n");
		const plan = planOf(card);

		// Without range support both entries would have no locator → no-source.
		expect(plan.manifest!.ids).toEqual(["C-01", "C-02"]);
		expect(plan.manifest!.units).toHaveLength(1);
		expect(plan.manifest!.packing).toEqual([{ cluster: ["C-01", "C-02"], unit: 1, why: "locator" }]);
		expect(plan.receipt).toContain("units=1 claims=2");
	});

	it("⑫ 畸形输入不抛异常并按空来源返回", () => {
		const garbage = {} as ReviewSplitPlanInput;
		let plan: ReviewSplitPlan | undefined;
		expect(() => {
			plan = planReviewSplit(garbage);
		}).not.toThrow();
		expect(plan!.manifest).toBeUndefined();
		expect(plan!.gaps).toEqual(["extract:no-source"]);
		expect(plan!.receipt).toContain("units=0 claims=0");
	});

	it("⑬ AC 区间逐条展开：一条“判 AC-001 到 AC-013” → 13 条 claim 但只覆盖 1 个 ask", () => {
		const card = qgCard("## 要求（这是本轮的核心）", ["- 逐条判定 AC-001 到 AC-013 每条 AC 是否落地。"]);
		const plan = planOf(card, "plan", "review-task", acIndex());

		const manifest = plan.manifest!;
		// Claim ids stay positional (`C-01`…); the AC ids are carried in 定位/判据.
		expect(manifest.ids).toEqual(Array.from({ length: 13 }, (_, i) => `C-${String(i + 1).padStart(2, "0")}`));
		expect(manifest.packing.flatMap((row) => row.cluster)).toEqual(manifest.ids);
		// Every expanded id got its own spec.md:<line>, so no locator cluster forms.
		expect(manifest.packing.every((row) => row.why !== "locator")).toBe(true);
		// `claims` (13) > `mapped` (1): ask coverage is not claim count.
		expectAskCoverage(plan, { asks: 1, mapped: 1 });
		expect(plan.receipt).toContain("claims=13 ");
		expect(plan.gaps.some((gap) => gap.startsWith("extract:ac-unresolved"))).toBe(false);
		// One 判据 per expanded id, hence one extract finding per claim.
		expect(plan.gaps.filter((gap) => gap.startsWith("extract:falsifier-missing:"))).toHaveLength(13);
	});

	it("⑭ AC 单引用借用 spec.md 定位：与手写同名定位的条目聚成一个 locator 簇", () => {
		const card = qgCard("## 要求", ["- `spec.md:7` 手工核对该行的断言。", "- 核对 AC-007 的落地证据。"]);
		const plan = planOf(card, "plan", "review-task", { "AC-007": "spec.md:7" });

		expect(plan.manifest!.ids).toEqual(["C-01", "C-02"]);
		// The AC row's 定位 IS `acIndex["AC-007"]` — the two claims share it.
		expect(plan.manifest!.packing).toEqual([{ cluster: ["C-01", "C-02"], unit: 1, why: "locator" }]);
		expectAskCoverage(plan, { asks: 2, mapped: 2 });
	});

	it("⑮ acIndex 查不到的 AC → 不产 claim、条目进 unmapped、留 extract:ac-unresolved", () => {
		const card = qgCard("## 要求", ["- 核对 AC-009 的落地证据。", "- `src/a.ts:3` 的错误分支未覆盖。"]);
		const plan = planOf(card, "plan", "review-task", { "AC-001": "spec.md:1" });

		expect(plan.manifest!.ids).toEqual(["C-01"]);
		expect(plan.gaps).toContain("extract:ac-unresolved:AC-009");
		expect(plan.gaps).toContain("extract:unmapped-ask:0");
		expect(plan.l0.unmapped).toEqual(["核对 AC-009 的落地证据。"]);
		expectAskCoverage(plan, { asks: 2, mapped: 1 });
		// No index at all is the same degradation, never a guessed locator.
		expect(planOf(card).gaps).toContain("extract:ac-unresolved:AC-009");
	});

	it("⑯ `## 审计目标` 段被扫描", () => {
		const card = ["# 复查卡", "", "## 审计目标", "", "- `src/audit.ts:12` 目标一：证据链闭合。", ""].join("\n");
		const plan = planOf(card);

		expect(plan.manifest).toBeDefined();
		expect(plan.manifest!.ids).toEqual(["C-01"]);
		expectAskCoverage(plan, { asks: 1, mapped: 1 });
	});

	it("⑰ 所有区间分隔符（到/至/~/～/-/–/—）都识别，升序含两端", () => {
		for (const separator of ["到", "至", "~", "～", "-", "–", "—"]) {
			const plan = planOf(
				qgCard("## 要求", [`- 判 AC-002 ${separator} AC-004。`]),
				"plan",
				"review-task",
				acIndex(),
			);
			expect(plan.manifest!.ids, separator).toEqual(["C-01", "C-02", "C-03"]);
			expect(
				plan.manifest!.packing.every((row) => row.why !== "locator"),
				separator,
			).toBe(true);
			expect(
				plan.gaps.some((gap) => gap.startsWith("extract:ac-unresolved")),
				separator,
			).toBe(false);
			expectAskCoverage(plan, { asks: 1, mapped: 1 });
		}
	});

	it("⑱ no-source 分支的 unmapped 装全部 ask 摘要", () => {
		const card = ["# 复查卡", "", "## 要求", "", "- 读一遍代码。", "- 再读一遍。", "- 核对 AC-001。", ""].join("\n");
		const plan = planOf(card);

		expect(plan.manifest).toBeUndefined();
		expectAskCoverage(plan, { asks: 3, mapped: 0 });
		expect(plan.l0.unmapped).toEqual(["读一遍代码。", "再读一遍。", "核对 AC-001。"]);
		expect(plan.gaps).toContain("extract:ac-unresolved:AC-001");
		expect(plan.gaps[plan.gaps.length - 1]).toBe("extract:no-source");
	});

	it("⑲ 区间展开上限 200：截断并留 extract:range-truncated:<total>", () => {
		const index: Record<string, string> = {};
		for (let i = 1; i <= 300; i++) index[`AC-${String(i).padStart(3, "0")}`] = `spec.md:${i}`;
		const plan = planOf(qgCard("## 要求", ["- 判 AC-001 至 AC-300 全部。"]), "plan", "review-task", index);

		const ids = plan.manifest!.ids;
		expect(ids).toHaveLength(200);
		expect(ids[0]).toBe("C-01");
		expect(ids[199]).toBe("C-200");
		expect(plan.gaps).toContain("extract:range-truncated:300");
		expect(plan.gaps.some((gap) => gap.startsWith("extract:ac-unresolved"))).toBe(false);
		expectAskCoverage(plan, { asks: 1, mapped: 1 });
	});

	it("⑳ AC 桥幂等：同一输入两次 receipt/manifest/gaps/l0 相同", () => {
		const card = qgCard("## 要求", ["- 判 AC-001 到 AC-013 每条。", "- 风格检查。"]);
		const first = planOf(card, "plan", "review-task", acIndex());
		const second = planOf(card, "plan", "review-task", acIndex());

		expect(second.receipt).toBe(first.receipt);
		expect(second.manifestText).toBe(first.manifestText);
		expect(second.gaps).toEqual(first.gaps);
		expect(second.l0).toEqual(first.l0);
	});

	it("㉑ 条目自带定位时优先于 AC 引用（先命中先生效）", () => {
		const card = qgCard("## 要求", ["- `src/inline.ts:5` 的 AC-001 判定要有证据。"]);
		const plan = planOf(card, "plan", "review-task", { "AC-001": "spec.md:1" });

		expect(plan.manifest!.ids).toEqual(["C-01"]);
		// The inline 定位 won: the claim does not sit on the AC index locator.
		expect(plan.manifest!.packing).toEqual([{ cluster: ["C-01"], unit: 1, why: "order" }]);
		expectAskCoverage(plan, { asks: 1, mapped: 1 });
	});

	it("㉒ canonicalizeLocator 把定位规成 basename:line[-end]", () => {
		expect(canonicalizeLocator("path/a.ts:3-5")).toBe("a.ts:3-5");
		expect(canonicalizeLocator(".agenticdoc/x/spec.md:42")).toBe("spec.md:42");
		expect(canonicalizeLocator("./apps/api/src/handler.ts:10")).toBe("handler.ts:10");
		expect(canonicalizeLocator("C:\\repo\\src\\a.ts:9")).toBe("a.ts:9");
		expect(canonicalizeLocator("`  spec.md:42  `")).toBe("spec.md:42");
		expect(canonicalizeLocator("src/symbol.ts")).toBe("symbol.ts");
		// A cell naming no file keeps its normal form.
		expect(canonicalizeLocator("-")).toBe("-");
		expect(canonicalizeLocator("read")).toBe("read");
		expect(canonicalizeLocator("")).toBe("");
		// Idempotent: canonicalizing a canonical 定位 changes nothing.
		expect(canonicalizeLocator(canonicalizeLocator(".agenticdoc/x/spec.md:42"))).toBe("spec.md:42");
	});

	it("㉓ 同一张卡两种 acIndex 拼法 → units/manifest.ids/receipt 逐字节相同", () => {
		const card = qgCard("## 要求", ["- `spec.md:7` 手工核对该行的断言。", "- 核对 AC-007 的落地证据。"]);
		const bare = planOf(card, "plan", "review-task", { "AC-007": "spec.md:7" });
		const deep = planOf(card, "plan", "review-task", { "AC-007": ".agenticdoc/review-task/spec.md:7" });
		const windows = planOf(card, "plan", "review-task", { "AC-007": ".\\review-task\\spec.md:7" });

		expect(deep.receipt).toBe(bare.receipt);
		expect(deep.manifestText).toBe(bare.manifestText);
		expect(deep.manifest!.ids).toEqual(bare.manifest!.ids);
		expect(deep.l0).toEqual(bare.l0);
		expect(deep.gaps).toEqual(bare.gaps);
		expect(windows.manifestText).toBe(bare.manifestText);
		// Both claims carry the SAME canonical 定位, so they form one locator cluster
		// and one unit — the old spelling-sensitive packing gave 2 units here.
		expect(bare.manifest!.units).toHaveLength(1);
		expect(bare.manifest!.packing).toEqual([{ cluster: ["C-01", "C-02"], unit: 1, why: "locator" }]);
		expect(bare.receipt).toContain("units=1 claims=2 ");
	});

	it("㉔ ask 段内空行分隔的段落也是一条 ask，列表项行为不变", () => {
		const card = [
			"# 复查卡",
			"",
			"## 要求",
			"",
			"**第一段散文要求：`src/one.ts:4` 的定位。**",
			"",
			"__第二段散文要求，没有定位也没有 AC。__",
			"",
			"- 列表项 `src/list.ts:2` 保持原行为。",
			"  这行是列表项的续行，不算新条目。",
			"",
			"```",
			"代码块里的散文不算条目。",
			"```",
			"",
		].join("\n");
		const plan = planOf(card);

		// 2 paragraphs + 1 list item; the continuation line and the fence are not asks.
		expect(plan.l0.asks).toBe(3);
		expect(plan.manifest!.ids).toEqual(["C-01", "C-02"]);
		expect(plan.l0.unmapped).toEqual(["第二段散文要求，没有定位也没有 AC。"]);
		expectAskCoverage(plan, { asks: 3, mapped: 2 });
	});

	it("㉕ `必须覆盖…` / `验收` 段标题被识别为 ask 段", () => {
		const card = [
			"# 复查卡",
			"",
			"## 必须覆盖的 10 项对抗探针",
			"",
			"1. `src/probe1.ts:10` 探针一。",
			"2. `src/probe2.ts:20` 探针二。",
			"",
			"## 验收：跑一遍负例",
			"",
			"- `src/accept.ts:30` 验收动作。",
			"",
			"## 上下文",
			"",
			"- `src/context.ts:40` 不是 ask 段，不计入。",
			"",
		].join("\n");
		const plan = planOf(card);

		expect(plan.manifest!.ids).toEqual(["C-01", "C-02", "C-03"]);
		expectAskCoverage(plan, { asks: 3, mapped: 3 });
	});

	it("㉖ 段标题的 AC 区间作为该段条目的默认范围（含 `AC-001..005` 缩写）", () => {
		const range = qgCard("## 要求（逐条给 PASS/FAIL，对应 AC-001..005）", ["- 逐条给 PASS/FAIL 并附证据。"]);
		const passed = planOf(range, "plan", "review-task", acIndex());

		// One bare ask inherits the heading's five AC ids: 5 claims, 1 covered ask.
		expect(passed.manifest!.ids).toHaveLength(5);
		expect(passed.receipt).toContain("claims=5 ");
		expectAskCoverage(passed, { asks: 1, mapped: 1 });
		expect(passed.gaps.some((gap) => gap.startsWith("extract:ac-unresolved"))).toBe(false);

		// The long form of the same range inherits identically.
		const long = planOf(
			qgCard("## 要求（对应 AC-001 到 AC-005）", ["- 逐条给判定。"]),
			"plan",
			"review-task",
			acIndex(),
		);
		expect(long.manifestText).toBeDefined();
		expect(long.manifest!.ids).toHaveLength(5);
		expect(long.receipt).toContain("claims=5 ");
		expect(long.l0).toEqual(passed.l0);

		// An entry naming its OWN AC does not also inherit the heading scope.
		const own = planOf(
			qgCard("## 要求（对应 AC-001 到 AC-005）", ["- 核对 AC-007 的落地证据。"]),
			"plan",
			"review-task",
			acIndex(),
		);
		expect(own.manifest!.ids).toEqual(["C-01"]);
		// An inherited id the index cannot resolve is still named.
		const partial = planOf(range, "plan", "review-task", { "AC-001": "spec.md:1" });
		expect(partial.gaps).toContain("extract:ac-unresolved:AC-002");
		expectAskCoverage(partial, { asks: 1, mapped: 1 });
	});

	it("㉗ 回执行 `fals=` 计数与 `l1` 的纯结构性口径", () => {
		const plan = planOf(proseCard(4, 0));
		const falsifierGaps = plan.gaps.filter((gap) => gap.startsWith("extract:falsifier-missing:"));

		expect(falsifierGaps).toHaveLength(4);
		expect(plan.receipt).toContain(" fals=4 ");
		// `l1` counts packing + manifest gaps only, never the falsifier gaps: 2
		// manual-only units, 4 missing falsifiers.
		const l1 = Number(/l1=gaps:(\d+)/.exec(plan.receipt)?.[1]);
		expect(l1).toBe(2);
		expect(l1).toBe(plan.gaps.filter((gap) => gap.startsWith("split:")).length);
		expect(l1).not.toBe(falsifierGaps.length);
		// A card whose claims all carry falsifiers pays nothing in `fals`.
		const clean = planOf(claimsBlockCard(3));
		expect(clean.receipt).toContain("fals=0 l1=ok");
	});

	it("㉘ T-18 形状：散文 `## 要求` 段诚实入 unmapped，`## 必须覆盖的…` 列表产出 claim", () => {
		const card = [
			"# 复查卡 T-18",
			"",
			"## 要求",
			"",
			"对实现做对抗式审计。**零写入**：只读代码。",
			"",
			"**核心命题：① 阻塞必须可见；② 派发不得前置人工。**",
			"",
			"## 必须覆盖的 10 项对抗探针",
			"",
			"1. `src/ledger.ts:298` 白名单宽度。",
			"2. `src/conductor.py:5742` 合成 claim。",
			"3. `src/gates.py:190` 字段枚举。",
			"4. `src/status-model.ts:167` 布尔字段。",
			"5. `src/monitor.ts:210` scanPendingGate。",
			"",
		].join("\n");
		const plan = planOf(card);

		expect(plan.manifest).toBeDefined();
		expect(plan.manifest!.ids).toHaveLength(5);
		expect(plan.manifest!.units.length).toBeGreaterThanOrEqual(1);
		expectAskCoverage(plan, { asks: 7, mapped: 5 });
		expect(plan.l0.unmapped).toEqual([
			"对实现做对抗式审计。**零写入**：只读代码。",
			"核心命题：① 阻塞必须可见；② 派发不得前置人工。",
		]);
	});
});
