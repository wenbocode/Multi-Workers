/**
 * review-split-gate.test.ts — the `plan`-tier dispatch short-circuit (card T-11,
 * key `claim-driven-review-orchestration`, spec AC-S2, design §2.2).
 *
 * Locks the wiring contract of `pm/review-split-gate.ts`:
 *
 *  - `mode=plan` + a `type: review` card ⇒ a receipt + a
 *    `evidence/split/review-<taskKey>-manifest.json` that `JSON.parse`s and
 *    carries a `selfSha256`;
 *  - ZERO dispatch side effects: no `workers/<taskKey>/`, no `task.md`, no
 *    `.mw/workers.parallel` (GC-3 — the reason the gate sits before
 *    `writeDispatchTaskMd`);
 *  - `mode=off` and a non-review card ⇒ `null` and no byte written;
 *  - a card without a claim source still writes an `ids=[]` manifest and an
 *    `units=0` receipt (never a throw);
 *  - two identical calls write identical bytes (idempotent).
 *
 * Every scenario runs in its own temp project dir; the switch is set through
 * `MW_REVIEW_SPLIT` so the ambient `.mw/review-split.json` of the checkout can
 * never decide the outcome.
 */

import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { planReviewSplitGate } from "../../src/extensions/agent-team-loop/pm/review-split-gate.ts";
import { planReviewSplit } from "../../src/extensions/agent-team-loop/pm/review-split-plan.ts";
import { REVIEW_SPLIT_ENV } from "../../src/extensions/agent-team-loop/shared/review-split.ts";
import { type SplitManifest, verifySplitManifest } from "../../src/extensions/agent-team-loop/shared/split-manifest.ts";

/** Owner key of every scenario (the key dir the manifest must land under). */
const OWNER_KEY = "review-split-key";
/** Parent task key of every scenario. */
const TASK_KEY = "review-task";
/** Card reference handed to the gate (relative — resolved against projectDir). */
const CARD_REF = "tasks/review-card.md";

let projectDir: string;
let agenticdocRoot: string;
let savedEnv: string | undefined;

/** A `type: review` card that already carries a machine-claims block. */
function claimsCard(count = 11): string {
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
		"type: review",
		"",
		"# 复查卡 review-claims",
		"",
		"## 上下文",
		"",
		"目标见 `.agenticdoc/goal.md`；入口 `src/file1.ts:1`。",
		"",
		"## 要求",
		"",
		"- 逐条取证（本行不含定位，claims 块优先）。",
		"",
		"<!-- mw-claims: v1 -->",
		...rows,
		"<!-- /mw-claims -->",
		"",
		"## 交付格式",
		"",
		"- report.md 四段。",
		"",
	].join("\n");
}

/** A `type: review` card with no claim source (no claims block, no locator). */
function noSourceCard(): string {
	return [
		"type: review",
		"",
		"# 复查卡 review-prose",
		"",
		"## 上下文",
		"",
		"目标见 `.agenticdoc/goal.md`；入口 `src/entry.ts:1`。",
		"",
		"## 要求",
		"",
		"- 读一遍代码。",
		"- 再读一遍。",
		"",
		"## 交付格式",
		"",
		"- report.md 四段。",
		"",
	].join("\n");
}

/** A `type: coding` card: the gate must stay silent and let the dispatch run. */
function codingCard(): string {
	return ["type: coding", "", "# 编码卡", "", "## 上下文", "", "见 `src/entry.ts:1`。", ""].join("\n");
}

/**
 * A `type: review` prose card in the measured QG shape: 定位 in 上下文, asks in
 * `要求（这是本轮的核心）` (`evidence/m1-exit-probe-20261022.md`).
 */
function proseAcCard(asks: readonly string[]): string {
	return [
		"type: review",
		"",
		"# 复查卡 QG-review-2",
		"",
		"## 上下文",
		"",
		`被审对象：\`.agenticdoc/${OWNER_KEY}/spec.md\`（AC-001 到 AC-013）。`,
		"",
		"## 要求（这是本轮的核心）",
		"",
		...asks,
		"",
		"## 交付格式",
		"",
		"- report.md 四段。",
		"",
	].join("\n");
}

/** Write `<agenticdocRoot>/<ownerKey>/spec.md` (the only AC index source). */
function writeSpec(lines: readonly string[], ownerKey = OWNER_KEY): string {
	const specPath = join(agenticdocRoot, ownerKey, "spec.md");
	mkdirSync(join(agenticdocRoot, ownerKey), { recursive: true });
	writeFileSync(specPath, [...lines, ""].join("\n"), "utf8");
	return specPath;
}

/**
 * The index the gate builds from `acSpecLines`: `AC-<n>` → `spec.md:<n>`, the
 * canonical form (`canonicalizeLocator`), never a path relative to the project.
 */
function specIndex(count = 13): Record<string, string> {
	const index: Record<string, string> = {};
	for (let i = 1; i <= count; i++) index[`AC-${String(i).padStart(3, "0")}`] = `spec.md:${i}`;
	return index;
}

/** The 13 AC lines of a spec whose `AC-<n>` sits on line `n`. */
function acSpecLines(count = 13): string[] {
	return Array.from(
		{ length: count },
		(_, i) => `- AC-${String(i + 1).padStart(3, "0")} 验收条件 ${i + 1}：证据见 evidence/m1.md:${i + 1}`,
	);
}

/**
 * A `type: review` card whose inline 定位 and whose AC reference name the SAME
 * line: the inline one as `spec.md:7`, the AC row through `AC-007` and the key's
 * `spec.md`. Only a canonical 定位 makes the two claims share a cluster.
 */
function acBridgeCard(): string {
	return [
		"type: review",
		"",
		"# 复查卡 AC bridge",
		"",
		"## 上下文",
		"",
		"被审对象：`.agenticdoc/spec.md`（AC-001 到 AC-013）。",
		"",
		"## 要求",
		"",
		"- `spec.md:7` 手工核对该行的断言。",
		"- 核对 AC-007 的落地证据。",
		"",
	].join("\n");
}

/** Write a card at `CARD_REF` under the temp project and return its path. */
function writeCard(text: string): string {
	const cardPath = join(projectDir, CARD_REF);
	mkdirSync(join(projectDir, "tasks"), { recursive: true });
	writeFileSync(cardPath, text, "utf8");
	return cardPath;
}

/** The manifest path the card requires, relative to the temp project. */
function manifestPath(taskKey = TASK_KEY): string {
	return join(agenticdocRoot, OWNER_KEY, "evidence", "split", `review-${taskKey}-manifest.json`);
}

/** Run the gate for the scenario's card. */
function gate(cardRef = CARD_REF, taskKey = TASK_KEY, ownerKey = OWNER_KEY) {
	return planReviewSplitGate({ cardPath: cardRef, taskKey, ownerKey, agenticdocRoot, projectDir });
}

/** Files the gate must never create (the dispatch's own side effects, GC-3). */
function dispatchSideEffects(): string[] {
	return [
		join(agenticdocRoot, OWNER_KEY, "workers", TASK_KEY),
		join(agenticdocRoot, OWNER_KEY, "workers", TASK_KEY, "task.md"),
		join(projectDir, ".mw", "workers.parallel"),
		join(agenticdocRoot, "_workers.parallel"),
	];
}

beforeEach(() => {
	projectDir = mkdtempSync(join(tmpdir(), "mw-review-split-gate-"));
	agenticdocRoot = join(projectDir, ".agenticdoc");
	savedEnv = process.env[REVIEW_SPLIT_ENV];
	delete process.env[REVIEW_SPLIT_ENV];
});

afterEach(() => {
	if (savedEnv === undefined) delete process.env[REVIEW_SPLIT_ENV];
	else process.env[REVIEW_SPLIT_ENV] = savedEnv;
	rmSync(projectDir, { recursive: true, force: true });
});

describe("planReviewSplitGate", () => {
	it("① mode=plan + review 卡 → 非 null、manifest 存在且可 JSON.parse、selfSha256 非空", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeCard(claimsCard(11));

		const result = gate();
		expect(result).not.toBeNull();
		const out = result!;
		expect(out.manifestPath).toBe(manifestPath());
		expect(existsSync(out.manifestPath)).toBe(true);

		const parsed = JSON.parse(readFileSync(out.manifestPath, "utf8")) as SplitManifest;
		expect(parsed.v).toBe(1);
		expect(parsed.parent).toBe(TASK_KEY);
		expect(parsed.mode).toBe("plan");
		expect(parsed.ids).toHaveLength(11);
		expect(parsed.selfSha256).toMatch(/^[0-9a-f]{64}$/);
		// The artifact re-verifies against its own sha chain (no gaps).
		expect(verifySplitManifest(parsed, { parentText: claimsCard(11) })).toEqual([]);
		expect(parsed.l0).toEqual({ asks: 11, mapped: 11, unmapped: [] });
		// The receipt is the frozen plan line plus the manifest link.
		expect(out.text).toMatch(/^\[review-split\] mode=plan units=\d+ claims=11 /);
		expect(out.text).toContain(
			`\n[review-split] manifest=${[".agenticdoc", OWNER_KEY, "evidence", "split", `review-${TASK_KEY}-manifest.json`].join("/")}`,
		);
	});

	it("② plan 跑完后 workers/<taskKey>/ 与队列文件都不存在（零副作用）", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeCard(claimsCard(3));

		const result = gate();
		expect(result).not.toBeNull();
		for (const sideEffect of dispatchSideEffects()) {
			expect(existsSync(sideEffect), sideEffect).toBe(false);
		}
		// No task.md anywhere under the owner key: the ONLY written file is the manifest.
		const written = readFileSync(manifestPath(), "utf8");
		expect(written).toContain(`"parent": "${TASK_KEY}"`);
		expect(existsSync(join(agenticdocRoot, OWNER_KEY, "workers"))).toBe(false);
		expect(existsSync(join(projectDir, ".mw"))).toBe(false);
	});

	it("③ mode=off → 返回 null，且什么都没写", () => {
		process.env[REVIEW_SPLIT_ENV] = "off";
		writeCard(claimsCard(3));

		expect(gate()).toBeNull();
		expect(existsSync(join(agenticdocRoot, OWNER_KEY))).toBe(false);
		expect(existsSync(join(projectDir, ".mw"))).toBe(false);
		for (const sideEffect of dispatchSideEffects()) {
			expect(existsSync(sideEffect), sideEffect).toBe(false);
		}
	});

	it("④ mode=plan + 非 review 类型 → 返回 null，且什么都没写", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeCard(codingCard());

		expect(gate()).toBeNull();
		expect(existsSync(join(agenticdocRoot, OWNER_KEY))).toBe(false);
		for (const sideEffect of dispatchSideEffects()) {
			expect(existsSync(sideEffect), sideEffect).toBe(false);
		}
	});

	it("⑤ 卡文无清单来源 → 仍返回文本（units=0），manifest 里 ids=[]，不抛", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeCard(noSourceCard());

		let result: ReturnType<typeof gate> | undefined;
		expect(() => {
			result = gate();
		}).not.toThrow();
		const out = result!;
		expect(out).not.toBeNull();
		expect(out.text).toContain("units=0");
		expect(out.text).toContain("claims=0");
		expect(out.text).toContain("gap=no-source");
		expect(out.text).toContain("[review-split] manifest=");

		const parsed = JSON.parse(readFileSync(out.manifestPath, "utf8")) as SplitManifest;
		expect(parsed.ids).toEqual([]);
		expect(parsed.units).toEqual([]);
		// `asks - mapped === unmapped.length` holds in the artifact too (card T-12).
		expect(parsed.l0).toEqual({ asks: 2, mapped: 0, unmapped: ["读一遍代码。", "再读一遍。"] });
		expect(parsed.l0.asks - parsed.l0.mapped).toBe(parsed.l0.unmapped.length);
		// Zero dispatch side effects still hold on the degraded branch.
		for (const sideEffect of dispatchSideEffects()) {
			expect(existsSync(sideEffect), sideEffect).toBe(false);
		}
	});

	it("⑥ 重复调用两次写出的 manifest 内容一致（幂等）", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeCard(claimsCard(11));

		const first = gate();
		const firstBytes = readFileSync(first!.manifestPath, "utf8");
		const second = gate();
		const secondBytes = readFileSync(second!.manifestPath, "utf8");

		expect(secondBytes).toBe(firstBytes);
		expect(second!.text).toBe(first!.text);
		expect(second!.manifestPath).toBe(first!.manifestPath);
		// No stray temp file survives the atomic write.
		expect(existsSync(`${first!.manifestPath}.tmp`)).toBe(false);
	});

	it("⑦ 读不到卡 → 不抛，返回 error=<code> 回执行且不写 manifest", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";

		let result: ReturnType<typeof gate> | undefined;
		expect(() => {
			result = gate("tasks/missing-card.md");
		}).not.toThrow();
		const out = result!;
		expect(out).not.toBeNull();
		expect(out.text).toBe("[review-split] mode=plan error=ENOENT");
		expect(out.manifestPath).toBe("");
		expect(existsSync(join(agenticdocRoot, OWNER_KEY, "evidence", "split"))).toBe(false);
	});

	it("⑧ 绝对卡路径与相对卡路径解析一致", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		const absolute = writeCard(claimsCard(3));

		const fromRelative = gate();
		rmSync(manifestPath(), { force: true });
		const fromAbsolute = gate(absolute);

		expect(fromAbsolute).not.toBeNull();
		expect(fromAbsolute!.text).toBe(fromRelative!.text);
		expect(readFileSync(manifestPath(), "utf8")).toContain('"parent": "review-task"');
	});

	it("⑨ spec.md 的 AC-001..AC-013 桥接散文卡 → manifest ids=13，每个 <taskKey>-u<k> 唯一", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeSpec(acSpecLines(13));
		writeCard(proseAcCard(["- 逐条判定 AC-001 到 AC-013 每条 AC 是否落地。"]));

		const result = gate();
		expect(result).not.toBeNull();
		const out = result!;
		expect(out.text).not.toContain("gap=no-source");
		expect(out.text).toContain("claims=13 ");
		expect(out.text).toContain(" l0=1/1 ");

		const parsed = JSON.parse(readFileSync(out.manifestPath, "utf8")) as SplitManifest;
		expect(parsed.ids.length).toBeGreaterThanOrEqual(5);
		expect(parsed.ids).toHaveLength(13);
		expect(new Set(parsed.units.map((unit) => unit.taskKey)).size).toBe(parsed.units.length);
		for (const unit of parsed.units) expect(unit.taskKey).toBe(`${TASK_KEY}-u${unit.k}`);
		// Ask coverage, not claim count: one ask line expanded to 13 claims.
		expect(parsed.l0).toEqual({ asks: 1, mapped: 1, unmapped: [] });
		expect(
			verifySplitManifest(parsed, { parentText: proseAcCard(["- 逐条判定 AC-001 到 AC-013 每条 AC 是否落地。"]) }),
		).toEqual([]);
		// Zero dispatch side effects still hold on the AC-bridge branch.
		for (const sideEffect of dispatchSideEffects()) {
			expect(existsSync(sideEffect), sideEffect).toBe(false);
		}
	});

	it("⑩ spec.md 缺失 → AC 引用降级为 no-source，仍写 manifest、不抛，l0 不变式成立", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeCard(proseAcCard(["- 核对 AC-009 的落地证据。", "- 读一遍代码。"]));

		let result: ReturnType<typeof gate> | undefined;
		expect(() => {
			result = gate();
		}).not.toThrow();
		const out = result!;
		expect(out).not.toBeNull();
		expect(out.text).toContain("units=0");
		expect(out.text).toContain("gap=no-source");
		expect(out.text).toContain(" l0=0/2 ");

		const parsed = JSON.parse(readFileSync(out.manifestPath, "utf8")) as SplitManifest;
		expect(parsed.ids).toEqual([]);
		expect(parsed.units).toEqual([]);
		expect(parsed.l0).toEqual({
			asks: 2,
			mapped: 0,
			unmapped: ["核对 AC-009 的落地证据。", "读一遍代码。"],
		});
		expect(parsed.l0.asks - parsed.l0.mapped).toBe(parsed.l0.unmapped.length);
	});

	it("⑪ acIndex 路径无关：不同 ownerKey 目录深度 → 同 units/ids，定位规范成 spec.md:<line>", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		const card = acBridgeCard();
		writeCard(card);

		// Scenario A: flat key, spec at `.agenticdoc/review-split-key/spec.md`.
		writeSpec(acSpecLines(13));
		const flat = gate();
		const flatManifest = JSON.parse(readFileSync(flat!.manifestPath, "utf8")) as SplitManifest;

		// Scenario B: the SAME card and spec, one directory deeper.
		writeSpec(acSpecLines(13), "deep/nested-key");
		const nested = gate(CARD_REF, TASK_KEY, "deep/nested-key");
		const nestedManifest = JSON.parse(readFileSync(nested!.manifestPath, "utf8")) as SplitManifest;

		expect(nestedManifest.ids).toEqual(flatManifest.ids);
		expect(nestedManifest.units.map((unit) => [unit.k, unit.ids, unit.budgetSum, unit.slots])).toEqual(
			flatManifest.units.map((unit) => [unit.k, unit.ids, unit.budgetSum, unit.slots]),
		);
		// The inline `spec.md:7` and the AC-007 row share ONE canonical 定位, so the
		// two claims pack into one locator cluster (`units=8` vs `units=12` was the
		// defect this pins).
		expect(flatManifest.units).toHaveLength(1);
		expect(nestedManifest.units).toHaveLength(1);
		// The gate's split equals the direct composer's split on the canonical index.
		const direct = planReviewSplit({
			taskKey: TASK_KEY,
			projectDir,
			cardText: card,
			mode: "plan",
			acIndex: specIndex(13),
		});
		expect(direct.manifest!.units).toHaveLength(flatManifest.units.length);
		expect(flat).not.toBeNull();
		expect(nested).not.toBeNull();
		expect(flat!.text).toContain("[review-split] mode=plan units=1 claims=2");
		expect(nested!.text).toContain("[review-split] mode=plan units=1 claims=2");
		expect(verifySplitManifest(flatManifest, { parentText: card })).toEqual([]);
		for (const sideEffect of dispatchSideEffects()) {
			expect(existsSync(sideEffect), sideEffect).toBe(false);
		}
	});

	it("⑫ 门禁回执行带 fals=<n>，且与组合器逐字一致（l1 只计结构性 gap）", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeSpec(acSpecLines(13));
		const asks = ["- 逐条判定 AC-001 到 AC-013 每条 AC 是否落地。"];
		const card = proseAcCard(asks);
		writeCard(card);

		const out = gate();
		expect(out).not.toBeNull();
		expect(out!.text).toContain(" claims=13 ");
		// AC-derived claims are all `manual`: 13 falsifier gaps, counted apart.
		expect(out!.text).toContain(" fals=13 ");
		expect(out!.text).toContain(" fals=13 l1=");
		expect(out!.text.indexOf(" fals=")).toBeLessThan(out!.text.indexOf(" l1="));

		// The receipt line is the composer's own, so the field set cannot drift.
		const direct = planReviewSplit({
			taskKey: TASK_KEY,
			projectDir,
			cardText: card,
			mode: "plan",
			acIndex: specIndex(13),
		});
		expect(out!.text.split("\n")[0]).toBe(direct.receipt);
		expect(direct.receipt).toContain("fals=13");
		expect(direct.gaps.filter((gap) => gap.startsWith("extract:falsifier-missing:"))).toHaveLength(13);
		// `l1` counts packing + manifest gaps only; falsifier gaps are separate.
		const l1 = Number(/l1=gaps:(\d+)/.exec(direct.receipt)?.[1]);
		expect(l1).toBe(direct.gaps.filter((gap) => gap.startsWith("split:")).length);
	});

	it("⑬ `## 必须覆盖的…` 段经门禁也被识别（散文覆盖放宽）", () => {
		process.env[REVIEW_SPLIT_ENV] = "plan";
		writeCard(
			[
				"type: review",
				"",
				"# 复查卡 T-18",
				"",
				"## 上下文",
				"",
				"被审对象：`.agenticdoc/spec.md`。",
				"",
				"## 必须覆盖的 3 项对抗探针",
				"",
				"1. `src/a.ts:1` 探针一。",
				"2. `src/b.ts:2` 探针二。",
				"3. `src/c.ts:3` 探针三。",
				"",
			].join("\n"),
		);

		const out = gate();
		expect(out).not.toBeNull();
		expect(out!.text).not.toContain("gap=no-source");
		expect(out!.text).toContain("claims=3 ");
		expect(out!.text).toContain(" l0=3/3 ");

		const parsed = JSON.parse(readFileSync(out!.manifestPath, "utf8")) as SplitManifest;
		expect(parsed.ids).toHaveLength(3);
		expect(parsed.units.length).toBeGreaterThanOrEqual(1);
	});
});
