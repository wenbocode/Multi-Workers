/**
 * dispatch-card-envelope.test.ts — T-01 envelope contract
 * (key `mw-dispatch-card-gate`, AC-001).
 *
 * Byte goldens for the dispatch-card envelope: a compliant card, every missing
 * section, an empty section, a missing `type:`, a missing file, and CRLF/LF
 * equivalence, plus the wide-档 heading-variation / semantic-fallback cases
 * (design.md §6.3) and the per-type extras of `typeExtrasMissing` (§1.2).
 *
 * Fixtures are literal byte strings written verbatim to a temp dir; the
 * compliant card additionally carries a sha256 byte lock so an accidental
 * fixture edit cannot silently move the golden. No provider APIs or network.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	CODING_EXTRA_SECTIONS,
	ENVELOPE_SECTIONS,
	inspectEnvelope,
	readEnvelope,
	SEED_GOAL_ITEM,
	SEED_PATH_ITEM,
	seedItemsMissing,
	typeExtrasMissing,
} from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";

const tempDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

/** Write `bytes` verbatim and return the card path. */
function writeCard(bytes: string, name = "card.md"): string {
	const dir = mkdtemp("mwd-t01-");
	const cardPath = path.join(dir, name);
	fs.writeFileSync(cardPath, bytes, "utf8");
	return cardPath;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Byte golden: a fully compliant coding card (seeds + three sections +
 * extras), LF. The context carries the T-12/F-05 seed minimum (a `goal.md`
 * anchor and a `path:line` reference). */
const GOLDEN_COMPLIANT = `---
type: coding
---

# Task T-XX: 信封契约

## 上下文

派发链无人读卡，故需单一判据（design.md §4）；种子锚点：.agenticdoc/goal.md；判据位置 pm/ui-bridge.ts:1969。

## 要求

AC-001 卡片非空判据成立。

## 交付格式

产物 shared/dispatch-card.ts；回收 report.md。

## 写入允许面

仅 shared/dispatch-card.ts 与 test/suite/dispatch-card-envelope.test.ts。

## 写入禁止面

pm/**、worker/**、packages/multi-workers/**。

## 验收命令

node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-envelope.test.ts

## 改动历史

见 trace.log 写入事件与 report.md 改动清单。`;

const GOLDEN_COMPLIANT_SHA256 = "3a0179b4eeeb5a788b48115b03fe0c21c72252975d58d0a357a797cf7a58c913";

/** Build a card from the given sections; `undefined` omits a section, `""`
 * keeps its heading with an empty body. Extras are appended as `## <title>`. */
function card(spec: {
	type?: string;
	context?: string;
	requirements?: string;
	deliverables?: string;
	extras?: ReadonlyArray<readonly [string, string]>;
}): string {
	const lines: string[] = ["---", spec.type === undefined ? "phase: build" : `type: ${spec.type}`, "---", ""];
	lines.push("# Task T-XX", "");
	const put = (title: string, body?: string): void => {
		if (body === undefined) return;
		lines.push(`## ${title}`, "", body, "");
	};
	put("上下文", spec.context);
	put("要求", spec.requirements);
	put("交付格式", spec.deliverables);
	for (const [title, body] of spec.extras ?? []) put(title, body);
	return lines.join("\n");
}

const NEUTRAL_CONTEXT = "本任务建立单一判据（种子锚点 .agenticdoc/goal.md，判据 pm/ui-bridge.ts:1969）。";
const NEUTRAL_REQUIREMENTS = "AC-001 判据成立。";
const NEUTRAL_DELIVERABLES = "产物 shared/dispatch-card.ts。";

// ── Byte goldens ────────────────────────────────────────────────────────────

describe("readEnvelope: byte goldens (AC-001)", () => {
	it("compliant coding card: sha256 byte lock, ok=true, no missing", () => {
		const digest = createHash("sha256").update(GOLDEN_COMPLIANT, "utf8").digest("hex");
		expect(digest).toBe(GOLDEN_COMPLIANT_SHA256);
		expect(Buffer.byteLength(GOLDEN_COMPLIANT, "utf8")).toBe(669);

		const cardPath = writeCard(GOLDEN_COMPLIANT);
		expect(fs.readFileSync(cardPath)).toEqual(Buffer.from(GOLDEN_COMPLIANT, "utf8"));

		const envelope = readEnvelope(cardPath);
		expect(envelope.ok).toBe(true);
		expect(envelope.missing).toEqual([]);
		expect(envelope.type).toBe("coding");
		expect(envelope.detected.context).toBe("heading:上下文");
		expect(envelope.detected.requirements).toBe("heading:要求");
		expect(envelope.detected.deliverables).toBe("heading:交付格式");
	});

	it("missing 上下文 -> missing=[context] with the rest detected", () => {
		const text = card({
			type: "coding",
			requirements: NEUTRAL_REQUIREMENTS,
			deliverables: NEUTRAL_DELIVERABLES,
		});
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(false);
		expect(envelope.missing).toEqual(["context"]);
		expect(envelope.detected.requirements).not.toBe("");
		expect(envelope.detected.deliverables).not.toBe("");
	});

	it("missing 要求 -> missing=[requirements]", () => {
		const text = card({ type: "coding", context: NEUTRAL_CONTEXT, deliverables: NEUTRAL_DELIVERABLES });
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(false);
		expect(envelope.missing).toEqual(["requirements"]);
		expect(envelope.detected.context).not.toBe("");
		expect(envelope.detected.deliverables).not.toBe("");
	});

	it("missing 交付格式 -> missing=[deliverables]", () => {
		const text = card({ type: "coding", context: NEUTRAL_CONTEXT, requirements: NEUTRAL_REQUIREMENTS });
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(false);
		expect(envelope.missing).toEqual(["deliverables"]);
	});

	it("empty section body (heading without content) does not count", () => {
		const text = card({
			type: "coding",
			context: "",
			requirements: NEUTRAL_REQUIREMENTS,
			deliverables: NEUTRAL_DELIVERABLES,
		});
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(false);
		expect(envelope.missing).toEqual(["context"]);
		expect(envelope.detected.context).toBe("");
	});

	it("missing type: -> missing=[type] but sections still detected", () => {
		const text = card({
			type: undefined,
			context: NEUTRAL_CONTEXT,
			requirements: NEUTRAL_REQUIREMENTS,
			deliverables: NEUTRAL_DELIVERABLES,
		});
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(false);
		expect(envelope.missing).toEqual(["type"]);
		expect(envelope.type).toBe("");
		expect(envelope.detected.context).not.toBe("");
	});

	it("missing file -> ok=false, missing=[file], nothing detected", () => {
		const missingPath = path.join(mkdtemp("mwd-t01-absent-"), "does-not-exist.md");
		const envelope = readEnvelope(missingPath);
		expect(envelope.ok).toBe(false);
		expect(envelope.missing).toEqual(["file"]);
		expect(envelope.type).toBe("");
		expect(envelope.detected).toEqual({ context: "", requirements: "", deliverables: "" });
	});

	it("CRLF and LF are equivalent (same envelope, different bytes)", () => {
		const lf = GOLDEN_COMPLIANT;
		const crlf = lf.replace(/\n/g, "\r\n");
		expect(crlf).not.toBe(lf);
		expect(Buffer.byteLength(crlf, "utf8")).toBeGreaterThan(Buffer.byteLength(lf, "utf8"));

		const lfPath = writeCard(lf, "lf.md");
		const crlfPath = writeCard(crlf, "crlf.md");
		expect(fs.readFileSync(crlfPath, "utf8")).toContain("\r\n");
		expect(readEnvelope(crlfPath)).toEqual(readEnvelope(lfPath));
	});

	it("empty card -> type and all three sections missing", () => {
		const envelope = readEnvelope(writeCard(""));
		expect(envelope.ok).toBe(false);
		expect(envelope.missing).toEqual(["type", "context", "requirements", "deliverables"]);
	});

	it("a leading BOM is stripped without changing the verdict", () => {
		const plain = readEnvelope(writeCard(GOLDEN_COMPLIANT, "plain.md"));
		const bom = readEnvelope(writeCard(`\uFEFF${GOLDEN_COMPLIANT}`, "bom.md"));
		expect(bom).toEqual(plain);
		expect(bom.ok).toBe(true);
	});
});

// ── Wide-档 criterion (design.md §6.3, DQ-2) ────────────────────────────────

describe("readEnvelope: wide-档 criterion", () => {
	it("heading variants are honoured (目标 / 验收标准 / 预期产出)", () => {
		const text = card({
			type: "research",
			context: "现状与动机描述。",
			requirements: "必须做到以下步骤。",
			deliverables: "证据文件落在 evidence/。",
		})
			.replace("## 上下文", "## 目标")
			.replace("## 要求", "## 验收标准")
			.replace("## 交付格式", "## 预期产出");
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(true);
		expect(envelope.detected.context).toBe("heading:目标");
		expect(envelope.detected.requirements).toBe("heading:验收标准");
		expect(envelope.detected.deliverables).toBe("heading:预期产出");
	});

	it("numbering prefixes are stripped before the family match", () => {
		const text = card({
			type: "coding",
			context: NEUTRAL_CONTEXT,
			requirements: NEUTRAL_REQUIREMENTS,
			deliverables: NEUTRAL_DELIVERABLES,
		})
			.replace("## 上下文", "## 1. 上下文")
			.replace("## 要求", "## (2) 要求")
			.replace("## 交付格式", "## A. 交付格式");
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(true);
		expect(envelope.detected.deliverables).toBe("heading:交付格式");
	});

	it("H3 headings count like H2", () => {
		const text = card({
			type: "coding",
			context: NEUTRAL_CONTEXT,
			requirements: NEUTRAL_REQUIREMENTS,
			deliverables: NEUTRAL_DELIVERABLES,
		})
			.replace("## 上下文", "### 上下文")
			.replace("## 要求", "### 要求")
			.replace("## 交付格式", "### 交付格式");
		expect(readEnvelope(writeCard(text)).ok).toBe(true);
	});

	it("paragraph semantics alone detect a headingless card", () => {
		const text = `---
type: research
---

# Task T-XX

因为历史卡常无标题，所以这里只给段落语义。

判据 AC-007 必须成立。

产物落在 report.md 与 progress.md。
`;
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(true);
		expect(envelope.detected.context).toBe("semantics");
		expect(envelope.detected.requirements).toBe("semantics");
		expect(envelope.detected.deliverables).toBe("semantics");
	});

	it("bullet key-value labels alone detect a headingless card", () => {
		const text = `---
type: research
---

# Task T-XX

- 背景: 无标题的键值卡
- 验收: 判据成立
- 交付: report.md
`;
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.ok).toBe(true);
		expect(envelope.detected.context).toBe("semantics");
		expect(envelope.detected.requirements).toBe("semantics");
		expect(envelope.detected.deliverables).toBe("semantics");
	});

	it("a body-level type: line cannot flip the header type (F-10)", () => {
		const text = card({
			type: "coding",
			context: "正文里写着 type: review 一行。",
			requirements: NEUTRAL_REQUIREMENTS,
			deliverables: NEUTRAL_DELIVERABLES,
		});
		const envelope = readEnvelope(writeCard(text));
		expect(envelope.type).toBe("coding");
	});

	it("recognises the live PM inline type conventions (｜type: and | type:)", () => {
		const bullet = `# T-01 X

- Key: my-key｜Wave: 1｜依赖: 无｜type: coding

## 上下文

动机。

## 要求

AC-001。

## 交付格式

report.md。
`;
		const bulletEnvelope = readEnvelope(writeCard(bullet));
		expect(bulletEnvelope.type).toBe("coding");
		expect(bulletEnvelope.ok).toBe(true);

		const blockquote = `# Task: X

> key: my-key | type: review | deps: -

## 上下文

动机。

## 要求

AC-001。

## 交付格式

report.md。
`;
		expect(readEnvelope(writeCard(blockquote)).type).toBe("review");
	});

	it("inspectEnvelope is the pure judgement seam used by readEnvelope", () => {
		expect(inspectEnvelope(GOLDEN_COMPLIANT)).toEqual(readEnvelope(writeCard(GOLDEN_COMPLIANT)));
	});

	it("ENVELOPE_SECTIONS stays the frozen three-key tuple", () => {
		expect(ENVELOPE_SECTIONS).toEqual(["context", "requirements", "deliverables"]);
	});
});

// ── Per-type extras (design.md §1.2) ────────────────────────────────────────
describe("typeExtrasMissing", () => {
	it("coding with all four extras declared -> []", () => {
		expect(typeExtrasMissing("coding", GOLDEN_COMPLIANT)).toEqual([]);
		expect(CODING_EXTRA_SECTIONS).toEqual(["写入允许面", "写入禁止面", "验收命令", "改动历史"]);
	});

	it("coding missing 验收命令 -> [验收命令]", () => {
		const text = card({
			type: "coding",
			context: NEUTRAL_CONTEXT,
			requirements: NEUTRAL_REQUIREMENTS,
			deliverables: NEUTRAL_DELIVERABLES,
			extras: [
				["写入允许面", "仅 shared/dispatch-card.ts。"],
				["写入禁止面", "pm/**、worker/**。"],
				["改动历史", "见 trace.log。"],
			],
		});
		expect(typeExtrasMissing("coding", text)).toEqual(["验收命令"]);
	});

	it("coding recognises the injected write-surface bullets plus the remaining two", () => {
		const text = `---
type: coding
---

# Task T-XX

## 上下文

因为要注入写面契约。

## 要求

- AC-001 判据成立。

## 交付格式

产物 report.md。

<!-- mw-write-surface: v1 -->
- 允许写：本任务目录下的 worker_file
- 不得写：本任务目录之外的任何路径
- 越界后果：运行期写面守卫 block
<!-- /mw-write-surface: v1 -->

## 验收命令

node ../../node_modules/vitest/dist/cli.js --run test/x.test.ts

## 改动历史

见 trace.log 写入事件。
`;
		expect(typeExtrasMissing("coding", text)).toEqual([]);
		expect(readEnvelope(writeCard(text)).ok).toBe(true);
	});

	it("coding accepts a write_scope: field as the allow surface", () => {
		const text = `---
type: coding
write_scope: .agenticdoc/k/workers/t, .agenticdoc/k/evidence
---

# Task T-XX

## 上下文

动机。

## 要求

AC-001。

## 交付格式

report.md。

## 写入禁止面

不得写 pm/**。

## 验收命令

node x.test.ts

## 改动历史

trace.log。
`;
		expect(typeExtrasMissing("coding", text)).toEqual([]);
	});

	it("research requires 唯一证据文件", () => {
		const without = card({
			type: "research",
			context: NEUTRAL_CONTEXT,
			requirements: NEUTRAL_REQUIREMENTS,
			deliverables: NEUTRAL_DELIVERABLES,
		});
		expect(typeExtrasMissing("research", without)).toEqual(["唯一证据文件"]);
		const withExtra = `${without}\n\n## 唯一证据文件\n\nevidence/only.md（仅此一写）。\n`;
		expect(typeExtrasMissing("research", withExtra)).toEqual([]);
	});

	it("review requires 审计目标 and 未覆盖面声明", () => {
		const partial = `---
type: review
---

# Task T-XX

## 上下文

动机。

## 要求

AC-001。

## 交付格式

report.md。

## 审计目标

要回答：投递链是否读卡。
`;
		expect(typeExtrasMissing("review", partial)).toEqual(["未覆盖面声明"]);
		const complete = `${partial}\n## 未覆盖面声明\n\npackages/multi-workers/** 未读。\n`;
		expect(typeExtrasMissing("review", complete)).toEqual([]);
	});

	it("unknown type names itself", () => {
		// T-07/P-08: `verifier` / `phase-writer` are in-use runtime roles and are
		// now part of the single-source vocabulary, so they must NOT be named
		// unknown (the old expectation false-rejected them for real dispatches).
		expect(typeExtrasMissing("code-gen/impl", "")).toEqual(["unknown-type:code-gen/impl"]);
		expect(typeExtrasMissing("bogus", GOLDEN_COMPLIANT)).toEqual(["unknown-type:bogus"]);
	});

	it("in-use runtime roles and the legacy codex value are no longer false unknowns (T-07/P-08)", () => {
		for (const role of ["verifier", "phase-writer", "repair", "roadmap-writer", "reviewer", "codex"]) {
			expect(typeExtrasMissing(role, ""), role).toEqual([]);
		}
	});

	it("known roles without extra rules do not get a false unknown", () => {
		expect(typeExtrasMissing("vision", "")).toEqual([]);
		expect(typeExtrasMissing("rag-research", "")).toEqual([]);
	});
});

// ── Seed minimum (T-12/F-05, AC-002 ①②) ────────────────────────────────────

describe("seedItemsMissing", () => {
	it("a card with a goal.md anchor and a path:line reference declares both seeds", () => {
		expect(seedItemsMissing(GOLDEN_COMPLIANT)).toEqual([]);
		expect(seedItemsMissing("锚点 .agenticdoc/goal.md；判据 pm/ui-bridge.ts:1969。")).toEqual([]);
	});

	it("a missing goal.md anchor is named", () => {
		expect(seedItemsMissing("见 pm/ui-bridge.ts:1969。")).toEqual([SEED_GOAL_ITEM]);
	});

	it("a missing path:line reference is named", () => {
		// `goal.md` alone is not enough; the card must hand the worker a
		// resolvable starting point.
		expect(seedItemsMissing("锚点 .agenticdoc/goal.md。")).toEqual([SEED_PATH_ITEM]);
	});

	it("both gaps are named, in stable order", () => {
		expect(seedItemsMissing("没有任何种子。")).toEqual([SEED_GOAL_ITEM, SEED_PATH_ITEM]);
	});

	it("a bare time (12:30) is not a path:line reference", () => {
		// The extension must be letter-initial, so clock times never satisfy it.
		expect(seedItemsMissing("goal.md 在 12:30 更新。")).toEqual([SEED_PATH_ITEM]);
	});
});
