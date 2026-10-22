/**
 * worker/output-sections.ts — T-05 recovery contract (AC-001/AC-003/AC-014,
 * design §4.1).
 *
 * This is the WRITE-SIDE contract for a worker's product text (`output.md` /
 * `report.md` / `report-<slug>.md`, in the AC-015 candidate order): which
 * sections the report must carry so the PM can recover it, and the H2-heading
 * predicate that judges that text. It is deliberately distinct from
 * `shared/output-sections.ts`, which is the READ side (splitting an
 * append-only `output.md` into blocks and picking the last non-placeholder one)
 * — same file name, opposite direction, no shared symbols.
 *
 * The five-section shape (design §3.2):
 *   base 4 for every role: 结论 / 证据 / 残留与未验证 / 上下文来源
 *   + 改动清单           for `coding`
 *   + 未覆盖面声明       for `review`
 *
 * Judgement (design §4.1, H2 档): the haystack is ONLY the H2 heading text —
 * every line matching ` {0,3}##(?!#)[ \t]+` outside fenced code blocks and
 * outside blockquotes — normalized by stripping trailing `#`, trimming,
 * collapsing internal whitespace and ASCII-lowering. A section is present when
 * one of its 45 aliases is a substring of some heading. Body text never
 * participates (that is what closed the FW-001 self-witness hole, where the
 * framework's own `## Recovery Gaps` paragraph naming `上下文来源` made the
 * missing section read as satisfied). The vocabulary stays fail-open (a heading
 * may use any alias) while the verdict is fail-closed (a required section with
 * no heading hit is missing). No punctuation stripping; `###` is not an H2.
 *
 * AC-014 (corrected attribution): this file used to justify its whole-text
 * predicate with `99.4% / 87.2%`. Those numbers belong to a DIFFERENT contract
 * — the dispatch-envelope/card compliance stats of `mw-dispatch-card-gate`
 * (341/343 = 99.4%, `evidence/research/spec-dispatch-input-format-20261012.md:142`;
 * 301/345 = 87.2%, `spec-card-format-corpus-20261012.md:281`) — and must not be
 * cited as this contract's evidence (`.agenticdoc/_framework-reflect.md`
 * FW-001 修法 5, corrected 2026-10-14). The honest reason the vocabulary is
 * broad is historical: the old contract did not require headings, and
 * historical products are never an acceptance object (R1). This contract's own
 * measured background is 145/433 = 33.5% whole-text vs 35/433 = 8.1%
 * heading-only (spec-rq1-contract-corpus-20261014.md), recorded as background
 * only.
 *
 * Migration: this module only answers a question; the caller decides when to
 * ask it (`worker/output-writer.ts`, `worker/worker-mode.ts`). Historical task
 * books without a header `type:` are never re-judged (P-07/P-09).
 *
 * The T-04a verdict-table half at the bottom is the same shape of contract for
 * the L3 layer: `parseVerdictTable` reads the agent-authored `## 断言裁决`
 * table and `claimCoverage` judges it against the card's claim set. Both are
 * pure (plus `statSync`/line counts for evidence refs) and never throw.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { CLAIM_BUDGET, type Claim, claimsGaps, UNVERIFIED_REASONS } from "../shared/dispatch-card.ts";

/** Sections every role's product must carry (design §3.2). */
export const RECOVERY_SECTIONS = ["结论", "证据", "残留与未验证", "上下文来源"] as const;

/** Extra section a role must add on top of `RECOVERY_SECTIONS`. Roles absent
 * from this table carry the base four only. */
export const RECOVERY_TYPE_SECTIONS: Readonly<Record<string, readonly string[]>> = {
	coding: ["改动清单"],
	review: ["未覆盖面声明"],
};

/** The card-declared report roles whose `task.md` carries the S2 contract
 * checklist (`recoveryContractSection`). Mirror of
 * `packages/multi-workers/autopilot/dispatch.py::RECOVERY_CONTRACT_TYPES`
 * (`test_mwoc_s2_sections.py::test_recovery_tables_match_the_ts_source` locks
 * the two tables above against this file; the TS scope constant is the TS
 * mirror of the Python one). */
export const RECOVERY_CONTRACT_TYPES: readonly string[] = ["coding", "research", "review"];

/** Fixed heading of the injected checklist section (mirror of the Python
 * `dispatch.RECOVERY_CONTRACT_HEADING`). */
export const RECOVERY_CONTRACT_HEADING = "## 交付段契约（本角色）";

/**
 * Broad-档 alias table. An entry is satisfied when a normalized H2 heading
 * contains any alias. Chinese aliases match literally; ASCII aliases match
 * case-insensitively (the heading is lower-cased once in `checkRecovery`).
 * Extend only by adding aliases — never by narrowing an existing one.
 */
const RECOVERY_SECTION_ALIASES: Readonly<Record<string, readonly string[]>> = {
	结论: ["结论", "tldr", "tl;dr", "summary", "摘要", "verdict", "总结"],
	证据: ["证据", "evidence", "原始命令", "命令与输出", "复现", "verification", "验证步骤", "测试结果"],
	残留与未验证: ["残留", "未验证", "未确认", "遗留", "remaining", "residual", "unverified", "limitation", "限制"],
	上下文来源: ["上下文来源", "来源清单", "sources", "references", "参考", "读取", "阅读清单", "context sources"],
	改动清单: ["改动清单", "变更清单", "changed files", "files changed", "改动", "变更", "修改文件"],
	未覆盖面声明: ["未覆盖面", "未覆盖", "coverage", "未审", "未考察", "缺口"],
};

/**
 * Sections the framework is allowed to fill mechanically (R2 hard constraint):
 * `上下文来源` is derivable from facts the framework already holds (the task's
 * `card_path` / `card_sha256`, its own read-tool events, the product path), so
 * an I2 backfill may append it. Every other section — `结论`, `证据`,
 * `残留与未验证`, `改动清单`, `未覆盖面声明`, and `## Questions` — is a
 * substantive judgement and is NEVER auto-generated; a whitelist (not a
 * blacklist) so a future section cannot be auto-filled by accident.
 */
export const MECHANICAL_SECTIONS: readonly string[] = ["上下文来源"];

/** True when `name` is on the mechanical-backfill whitelist (R2). */
export function isMechanicalSection(name: string): boolean {
	return MECHANICAL_SECTIONS.includes(name);
}

/** Which sections `type` must carry: the base four plus its role extra. */
export function recoverySectionsFor(type: string | undefined): string[] {
	const required: string[] = [...RECOVERY_SECTIONS];
	if (type !== undefined) required.push(...(RECOVERY_TYPE_SECTIONS[type] ?? []));
	return required;
}

/**
 * The `## 交付段契约（本角色）` block for `task_type`, or `""` outside
 * `RECOVERY_CONTRACT_TYPES`. Every required section is rendered as a copyable
 * `- \`## <段名>\`` line so the worker can paste the canonical heading the
 * settle judge looks for — never an invented alias. Byte-shape mirror of
 * `dispatch.py::recovery_contract_section` so the two producers inject the same
 * section (idempotent on re-application).
 */
export function recoveryContractSection(type: string | undefined): string {
	if (type === undefined || !RECOVERY_CONTRACT_TYPES.includes(type)) return "";
	const sections = recoverySectionsFor(type);
	if (sections.length === 0) return "";
	return [
		RECOVERY_CONTRACT_HEADING,
		"",
		`本角色（type: ${type}）的恢复契约段：report.md / output.md 必须按下列标题成节（可直接复制；缺任一段即 settle 判缺失）：`,
		"",
		...sections.map((name) => `- \`## ${name}\``),
	].join("\n");
}

/** Fence opener/closer: 0-3 spaces then at least three backticks or tildes. */
const FENCE_RE = /^( {0,3})(`{3,}|~{3,})(.*)$/;

/** An H2 heading line: 0-3 leading spaces, exactly two `#` (never `###`), then
 * horizontal whitespace, then the heading text. */
const H2_RE = /^ {0,3}##(?!#)[ \t]+(.*)$/;

/** A blockquote line: its `#` is quoted data, not a heading. */
const BLOCKQUOTE_RE = /^ {0,3}>/;

/** Tracks fenced-code-block state across lines. An opening fence records its
 * marker char and length; the matching closing fence must use the same char,
 * the same-or-longer marker and carry nothing but whitespace after it. */
function advanceFence(
	line: string,
	open: { char: string; len: number } | undefined,
): { char: string; len: number } | undefined {
	const match = FENCE_RE.exec(line);
	if (match === null) return open;
	const marker = match[2] ?? "";
	const rest = match[3] ?? "";
	const char = marker[0] ?? "";
	if (open === undefined) return { char, len: marker.length };
	if (char === open.char && marker.length >= open.len && rest.trim() === "") return undefined;
	return open;
}

/** Normalize one H2 heading: strip the trailing `#` closing sequence, trim,
 * collapse internal whitespace, ASCII-lower. */
function normalizeHeading(text: string): string {
	return text
		.replace(/#+\s*$/, "")
		.trim()
		.replace(/\s+/g, " ")
		.toLowerCase();
}

/**
 * The normalized H2 headings of `text`, in document order (design §4.1).
 * Fenced code blocks and blockquote lines contribute nothing; `###` is not an
 * H2. Exported for the AC-001 8-case matrix and for tests that lock the
 * normalization.
 */
export function h2Headings(text: string): string[] {
	const out: string[] = [];
	let fence: { char: string; len: number } | undefined;
	for (const line of text.split(/\r?\n/)) {
		fence = advanceFence(line, fence);
		if (fence !== undefined) continue;
		if (BLOCKQUOTE_RE.test(line)) continue;
		const match = H2_RE.exec(line);
		if (match === null) continue;
		out.push(normalizeHeading(match[1] ?? ""));
	}
	return out;
}

/** One alias hit on one heading. */
function headingHitsAlias(heading: string, aliases: readonly string[]): boolean {
	return aliases.some((alias) => heading.includes(alias.toLowerCase()));
}

export interface RecoveryVerdict {
	/** True when every required section is present. */
	ok: boolean;
	/** Required sections with no H2 heading hit, in contract order. Empty iff `ok`. */
	missing: string[];
	/** The full required list for the given type (diagnostic/tests). */
	required: string[];
}

/**
 * Judge an agent-authored product text against the recovery contract.
 *
 * `text` is the agent's report (what `report.md` / `output.md` already carries,
 * or the final reply) — never the harness block the writer appends afterwards.
 * `type` is the header `type:` of the dispatch; `undefined` (legacy/manual task
 * book) yields the base four, and the caller is responsible for only asking at
 * all when the dispatch is forward (see `worker/output-writer.ts`).
 *
 * Never throws: any string (including empty) yields a verdict.
 */
export function checkRecovery(text: string, type: string | undefined): RecoveryVerdict {
	const required = recoverySectionsFor(type);
	const headings = h2Headings(text);
	const missing = required.filter((name) => {
		const aliases = RECOVERY_SECTION_ALIASES[name] ?? [name];
		return !headings.some((heading) => headingHitsAlias(heading, aliases));
	});
	return { ok: missing.length === 0, missing, required };
}

// ── T-04a: the `## 断言裁决` verdict table (design §2.2/§3.3, RQ-3 §5) ────────
//
// The L3 settle layer judges what the worker CLAIMS to have settled. The
// table is agent-authored (`## 断言裁决`), seven columns, free column order,
// extra columns ignored, fenced code blocks excluded, full-width forms folded
// (RQ-3 §5.6, the P-048 tolerance lesson). Every gap string below is frozen:
// `claim:<id>:<element>` / `claims:<rule>:<detail>` — the same shape T-01's
// `claimsGaps` already froze, so the refusal text and the settle readback can
// concatenate either list without a second vocabulary.

/** H2 aliases of the verdict table. `## 断言裁决（claims）` still hits because
 * the match is `includes`, exactly like `RECOVERY_SECTION_ALIASES`. */
const VERDICT_TABLE_ALIASES: readonly string[] = ["断言裁决", "claim verdict", "claims verdict", "verdict table"];

/** The seven judged columns (RQ-3 §5.1). */
type VerdictField = "id" | "type" | "verdict" | "finding" | "evidence" | "fetches" | "reason";

/** Header aliases per column, both scripts (RQ-3 §5.6). */
const VERDICT_COLUMN_ALIASES: ReadonlyArray<readonly [VerdictField, readonly string[]]> = [
	["id", ["claim", "断言", "claim id"]],
	["type", ["类型", "type", "类别"]],
	["verdict", ["裁决", "verdict"]],
	["finding", ["判定", "finding", "判断"]],
	["evidence", ["证据", "evidence"]],
	["fetches", ["取数", "fetches", "reads"]],
	["reason", ["原因", "reason"]],
];

/** One parsed `## 断言裁决` row, all cells trimmed (never normalized away: the
 * raw cell text is what the diagnostics quote). */
export interface VerdictRow {
	/** `C-01` / `C-01.3` id, upper-cased. */
	id: string;
	/** `类型` cell, lower-cased, `""` when the column is absent. */
	type: string;
	verdict: string;
	finding: string;
	evidence: string;
	fetches: string;
	reason: string;
	/** 1-based line of the row in the parsed text (diagnostics only). */
	row: number;
}

/** Result of {@link parseVerdictTable}. Never throws (P-048). */
export interface VerdictTable {
	/** The `## 断言裁决` H2 was seen outside a fence. */
	present: boolean;
	rows: VerdictRow[];
	/** `claim:<row>:unparsable` findings, row = 1-based source line. */
	errors: string[];
}

/** `C-01` / `C-01.3` (the same id shape `parseClaimsBlock` accepts). */
const VERDICT_ID_RE = /^C-(\d{2,3})(?:\.(\d+))?$/i;

/** Header index per judged column, filled in header order. */
type VerdictColumns = Partial<Record<VerdictField, number>>;

/** Fold the full-width forms the card corpus mixes in (RQ-3 §5.6): `：` -> `:`,
 * `｜` -> `|`, full-width digits -> ASCII digits, ideographic space -> space.
 * Mirror of the private helper in `shared/dispatch-card.ts` (the claims block
 * parser); the exported constants are imported, never copied. */
function normalizeVerdictText(text: string): string {
	return text
		.replace(/[\uFF10-\uFF19]/g, (digit) => String.fromCharCode(digit.charCodeAt(0) - 0xfee0))
		.replace(/\uFF1A/g, ":")
		.replace(/\uFF5C/g, "|")
		.replace(/\u3000/g, " ")
		.trim();
}

/** Cells never carry markdown code fences: strip the backticks a writer adds. */
function stripVerdictTicks(text: string): string {
	return text.replace(/`/g, "").trim();
}

/** Split a `| a | b |` row into trimmed cells (leading/trailing pipes dropped). */
function splitVerdictRow(line: string): string[] {
	const cells = normalizeVerdictText(line).split("|");
	if (cells.length > 0 && (cells[0] ?? "").trim() === "") cells.shift();
	if (cells.length > 0 && (cells[cells.length - 1] ?? "").trim() === "") cells.pop();
	return cells.map((cell) => cell.trim());
}

/** Header of a verdict table, `undefined` when the row is not a header. */
function matchVerdictHeader(cells: string[]): VerdictColumns | undefined {
	const columns: VerdictColumns = {};
	let hasClaimColumn = false;
	for (let i = 0; i < cells.length; i++) {
		const name = stripVerdictTicks(normalizeVerdictText(cells[i] ?? ""))
			.toLowerCase()
			.replace(/\s+/g, " ")
			.replace(/:$/, "");
		for (const [field, aliases] of VERDICT_COLUMN_ALIASES) {
			if (!aliases.includes(name)) continue;
			if (columns[field] === undefined) columns[field] = i;
			if (field === "id") hasClaimColumn = true;
			break;
		}
	}
	return hasClaimColumn ? columns : undefined;
}

/** `| --- | --- |` separator row (any dash count, optional alignment colons). */
function isVerdictSeparatorRow(cells: string[]): boolean {
	if (cells.length === 0) return false;
	return cells.every((cell) => cell === "" || /^:?-{1,}:?$/.test(cell));
}

/** Cell of `field` in `cells`, `""` when the column is absent (tolerance). */
function verdictCell(cells: string[], columns: VerdictColumns, field: VerdictField): string {
	const index = columns[field];
	if (index === undefined) return "";
	return (cells[index] ?? "").trim();
}

/** One table row -> {@link VerdictRow}, `undefined` when the id is unparsable. */
function verdictRowFrom(cells: string[], columns: VerdictColumns, row: number): VerdictRow | undefined {
	const idMatch = VERDICT_ID_RE.exec(stripVerdictTicks(verdictCell(cells, columns, "id")));
	if (idMatch === null) return undefined;
	const number = idMatch[1] ?? "";
	const child = idMatch[2];
	return {
		id: `C-${number}${child === undefined ? "" : `.${child}`}`,
		type: stripVerdictTicks(verdictCell(cells, columns, "type")).toLowerCase(),
		verdict: verdictCell(cells, columns, "verdict"),
		finding: verdictCell(cells, columns, "finding"),
		evidence: verdictCell(cells, columns, "evidence"),
		fetches: verdictCell(cells, columns, "fetches"),
		reason: verdictCell(cells, columns, "reason"),
		row,
	};
}

/**
 * Parse the agent-authored `## 断言裁决` table (RQ-3 §5.1/§5.6).
 *
 * Tolerance is the contract (P-048): the heading may carry a suffix, column
 * order is free, extra columns are ignored, header words take both scripts,
 * full-width `：｜`/digits fold to ASCII, and fenced code blocks contribute
 * nothing (the same fence state machine `h2Headings` uses). A row whose
 * `claim` cell is not a claim id is reported as `claim:<row>:unparsable` and
 * skipped; this function never throws.
 */
export function parseVerdictTable(text: string): VerdictTable {
	const table: VerdictTable = { present: false, rows: [], errors: [] };
	let fence: { char: string; len: number } | undefined;
	let inSection = false;
	let columns: VerdictColumns | undefined;
	const lines = text.split(/\r?\n/);
	for (let i = 0; i < lines.length; i++) {
		const line = lines[i] ?? "";
		fence = advanceFence(line, fence);
		if (fence !== undefined) continue;
		const heading = H2_RE.exec(line);
		if (heading !== null) {
			const normalized = normalizeHeading(heading[1] ?? "");
			if (inSection) {
				inSection = false;
				columns = undefined;
				continue;
			}
			if (!table.present && VERDICT_TABLE_ALIASES.some((alias) => normalized.includes(alias))) {
				// RQ-3 §5.6: `## 断言裁决（claims）` hits, the body starts below it.
				table.present = true;
				inSection = true;
				columns = undefined;
			}
			continue;
		}
		if (!inSection) continue;
		if (BLOCKQUOTE_RE.test(line)) continue;
		if (!normalizeVerdictText(line).startsWith("|")) {
			columns = undefined;
			continue;
		}
		const cells = splitVerdictRow(line);
		if (columns === undefined) {
			columns = matchVerdictHeader(cells);
			continue;
		}
		if (isVerdictSeparatorRow(cells)) continue;
		const row = verdictRowFrom(cells, columns, i + 1);
		if (row === undefined) {
			table.errors.push(`claim:${i + 1}:unparsable`);
			continue;
		}
		table.rows.push(row);
	}
	return table;
}

/** `裁决` closed set (RQ-3 §5.2; no `done`/`PASS`/`ok`/`verified`/`N/A`). */
const VERDICT_TOKENS: readonly string[] = ["closed", "partial", "unverified"];

/** `判定` closed set (RQ-3 §5.1) plus the `partial` render token `部分成立` —
 * §5.1's own mapping (`partial` -> 部分成立) has no other representable form,
 * so excluding it here would make `partial` unusable. */
const FINDING_TOKENS: readonly string[] = ["成立", "不成立", "无法判定", "部分成立"];

/** Allowed `判定` per `裁决` (RQ-3 §5.1: `closed` settles either way). */
const VERDICT_FINDINGS: Readonly<Record<string, readonly string[]>> = {
	closed: ["成立", "不成立"],
	partial: ["部分成立"],
	unverified: ["无法判定"],
};

/** Fold a closed-set cell to its token form (ticks, whitespace, ASCII case). */
function verdictToken(cell: string): string {
	return stripVerdictTicks(cell).replace(/\s+/g, "").toLowerCase();
}

/** Evidence ref separators (`;`, RQ-3 §5.1) and the `-` empty marker. */
function splitEvidenceRefs(cell: string): string[] {
	return stripVerdictTicks(cell)
		.split(";")
		.map((ref) => ref.trim())
		.filter((ref) => ref !== "" && ref !== "-");
}

/** `cmdref` verbs (RQ-3 §5.3 verb whitelist). */
const CMD_REF_VERBS: readonly string[] = [
	"node",
	"npm",
	"npx",
	"python",
	"python3",
	"pytest",
	"vitest",
	"git",
	"mw",
	"rg",
	"grep",
	"bash",
];

/** `cmdref` result half: `rc=<digits>` plus optional `key=value` pairs. */
const CMD_RESULT_RE = /^rc=-?\d+(?:\s+[\w.-]+=\S+)*$/;

/** One parsed evidence ref: a path with a line/line range, or a command. */
interface EvidenceRef {
	kind: "path" | "cmd";
	/** Repo-relative path (`""` for a command ref). */
	path: string;
	first: number;
	last: number;
}

/** A path ref is repo-relative: no absolute path, no `./` prefix, no `..`. */
function isRepoRelativePath(text: string): boolean {
	if (text === "" || text.startsWith("/") || /^[A-Za-z]:[\\/]/.test(text) || text.startsWith("./")) return false;
	return !text.split(/[\\/]/).includes("..");
}

/**
 * Parse one evidence ref (RQ-3 §5.3): `path:line`, `path:a-b`, optionally with
 * a `「excerpt」` suffix, or `verb rest => rc=N [k=v]`. `undefined` means the
 * ref does not match the frozen grammar (a `claim:<id>:evidence` gap).
 */
function parseEvidenceRef(raw: string): EvidenceRef | undefined {
	const ref = stripVerdictTicks(raw);
	if (ref === "" || ref === "-") return undefined;
	const halves = ref.split("=>");
	if (halves.length > 2) return undefined;
	if (halves.length === 2) {
		const left = (halves[0] ?? "").trim();
		const right = (halves[1] ?? "").trim();
		// RQ-3 §5.3: no `&&` / `;` (split above) / `>` / backticks inside a cmdref.
		if (left === "" || left.includes("&&") || left.includes(">") || left.includes("<") || left.includes("`")) {
			return undefined;
		}
		const verb = /^([A-Za-z0-9]+)\s+/.exec(left)?.[1]?.toLowerCase() ?? "";
		if (!CMD_REF_VERBS.includes(verb) || !CMD_RESULT_RE.test(right)) return undefined;
		return { kind: "cmd", path: "", first: 0, last: 0 };
	}
	const withoutExcerpt = ref.replace(/「[^」]*」\s*$/, "").trim();
	const match = /^(.+?):(\d+)(?:-(\d+))?$/.exec(withoutExcerpt);
	if (match === null) return undefined;
	const pathText = (match[1] ?? "").trim();
	if (!isRepoRelativePath(pathText)) return undefined;
	const first = Number(match[2] ?? "");
	const last = match[3] === undefined ? first : Number(match[3]);
	if (!Number.isInteger(first) || !Number.isInteger(last) || first < 1 || last < first) return undefined;
	return { kind: "path", path: pathText, first, last };
}

/** Line count of a text file, trailing newline not counted as a line. */
function lineCount(text: string): number {
	const lines = text.split(/\r?\n/);
	return text.endsWith("\n") ? lines.length - 1 : lines.length;
}

/** True when a parsed path ref is not a usable citation: outside the project
 * root, not a file, a line past EOF, or a range wider than 200 lines. */
function evidenceRefInvalid(ref: EvidenceRef, projectDir: string): boolean {
	if (ref.kind === "cmd") return false;
	const absolute = path.resolve(projectDir, ref.path);
	const relative = path.relative(projectDir, absolute);
	if (relative === "" || relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
		return true;
	}
	let text: string;
	try {
		if (!fs.statSync(absolute).isFile()) return true;
		text = fs.readFileSync(absolute, "utf8");
	} catch {
		return true;
	}
	if (ref.last > lineCount(text)) return true;
	return ref.last - ref.first > 200;
}

/** Self-witness set of RQ-3 §4 (B-1/B-4): a claim citing only these files has
 * cited the report that contains it, not evidence. `progress.md` is allowed as
 * SECONDARY evidence (one real ref alongside it is enough), never as the only
 * one — which is exactly what "every ref is self-witness" means here. */
const SELF_EVIDENCE_BASENAMES: readonly RegExp[] = [
	/^report.*\.md$/i,
	/^output\.md$/i,
	/^progress\.md$/i,
	/^task\.md$/i,
];

/** True when a path ref points into the self-witness set (any depth). */
function isSelfEvidenceRef(ref: EvidenceRef): boolean {
	if (ref.kind !== "path") return false;
	const basename = ref.path.split(/[\\/]/).pop() ?? "";
	return SELF_EVIDENCE_BASENAMES.some((pattern) => pattern.test(basename));
}

/** `Σ预算` of the card's claims; a card that declares no `预算` at all falls
 * back to the calibrated call cap so a missing field cannot make every fetch a
 * gap (T-01's `claim:<id>:budget` already refuses that card at G1). */
function declaredBudget(claims: Claim[]): number {
	let sum = 0;
	let declared = 0;
	for (const claim of claims) {
		if (!Number.isFinite(claim.budget) || claim.budget < 0) continue;
		sum += claim.budget;
		declared += 1;
	}
	return declared === 0 ? CLAIM_BUDGET.callCap : sum;
}

/** `取数` cell as a non-negative integer, `undefined` when it is not one. */
function fetchCount(cell: string): number | undefined {
	const text = stripVerdictTicks(cell);
	return /^\d+$/.test(text) ? Number(text) : undefined;
}

/** Ids T-01's own tautology judge (RQ-3 B-5) flags for this claim set. Reuses
 * `claimsGaps` so the `陈述`/`反证条件` similarity + new-artifact rule has ONE
 * implementation (the card forbids rewriting it and `shared/**` is out of the
 * write face, so the exported validator is the only legal handle). */
function tautologyIds(claims: Claim[], projectDir: string): Set<string> {
	const ids = new Set<string>();
	if (claims.length === 0) return ids;
	const gaps = claimsGaps({ present: true, claims, errors: [] }, { projectDir, enforce: true });
	for (const gap of gaps) {
		const match = /^claim:(C-\d{2,3}(?:\.\d+)?):tautology$/.exec(gap);
		if (match !== null && match[1] !== undefined) ids.add(match[1]);
	}
	return ids;
}

/** Options of {@link claimCoverage}. `projectDir` is the root the evidence path
 * refs resolve against (the launcher's cwd in production, a fixture in tests). */
export interface ClaimCoverageOptions {
	projectDir?: string;
}

/**
 * Judge the `## 断言裁决` table against the card's claim set (RQ-3 §5, B-1/B-4/
 * B-10). Every returned string is one frozen criterion; the string IS the
 * diagnostic, so no second vocabulary is introduced.
 *
 * Criteria (in emission order):
 *   `claims:missing-table`            no `## 断言裁决` H2 at all
 *   `claim:<id>:missing-row`          a card claim the table never adjudicates
 *   `claims:extra-row:<id>`           a table row the card never declared
 *   `claim:<id>:verdict`              `裁决` outside closed|partial|unverified
 *   `claim:<id>:finding`              `判定` outside 成立|不成立|无法判定
 *   `claim:<id>:verdict-finding`      the two columns disagree (§5.1 mapping)
 *   `claim:<id>:evidence`             no evidence for closed/partial, or a ref
 *                                     that is unparsable / missing on disk /
 *                                     past EOF / wider than 200 lines
 *   `claim:<id>:reason`               `unverified` without a 7-word reason
 *   `claim:<id>:self-evidence`        every ref is `report*`/output/progress/task
 *   `claim:<id>:struct-held`          a `struct` row counted as `closed` (B-10)
 *   `claim:<id>:budget`               `取数` not a count, or > min(Σ预算, 30)
 *   `claim:<id>:tautology`            T-01's B-5 tautology judge fired
 *
 * Never throws. A claim-free card returns `[]` (nothing to adjudicate), and a
 * table-only run without claims is likewise not judged.
 */
export function claimCoverage(claims: Claim[], table: VerdictTable, opts: ClaimCoverageOptions = {}): string[] {
	const gaps: string[] = [];
	if (claims.length === 0) return gaps;
	if (!table.present) return ["claims:missing-table"];
	const projectDir = opts.projectDir ?? process.cwd();
	const rows = new Map<string, VerdictRow>();
	for (const row of table.rows) if (!rows.has(row.id)) rows.set(row.id, row);
	const budgetCap = Math.min(declaredBudget(claims), CLAIM_BUDGET.callCap);
	const tautological = tautologyIds(claims, projectDir);
	for (const claim of claims) {
		const row = rows.get(claim.id);
		if (row === undefined) {
			gaps.push(`claim:${claim.id}:missing-row`);
			continue;
		}
		const verdict = verdictToken(row.verdict);
		const finding = verdictToken(row.finding);
		if (!VERDICT_TOKENS.includes(verdict)) gaps.push(`claim:${claim.id}:verdict`);
		if (!FINDING_TOKENS.includes(finding)) gaps.push(`claim:${claim.id}:finding`);
		if (
			VERDICT_FINDINGS[verdict] !== undefined &&
			FINDING_TOKENS.includes(finding) &&
			!(VERDICT_FINDINGS[verdict] ?? []).includes(finding)
		) {
			gaps.push(`claim:${claim.id}:verdict-finding`);
		}
		const refs = splitEvidenceRefs(row.evidence);
		const parsed: Array<EvidenceRef | undefined> = refs.map((ref) => parseEvidenceRef(ref));
		const needsEvidence = verdict === "closed" || verdict === "partial";
		if (needsEvidence && refs.length === 0) gaps.push(`claim:${claim.id}:evidence`);
		else if (parsed.some((ref) => ref === undefined || evidenceRefInvalid(ref, projectDir))) {
			gaps.push(`claim:${claim.id}:evidence`);
		}
		if (verdict === "unverified" && !(UNVERIFIED_REASONS as readonly string[]).includes(verdictToken(row.reason))) {
			gaps.push(`claim:${claim.id}:reason`);
		}
		const parsedAll: EvidenceRef[] = parsed.filter((ref): ref is EvidenceRef => ref !== undefined);
		if (parsedAll.length > 0 && parsedAll.length === refs.length && parsedAll.every(isSelfEvidenceRef)) {
			gaps.push(`claim:${claim.id}:self-evidence`);
		}
		const declaredType = row.type === "" ? claim.type.toLowerCase() : row.type;
		if (declaredType === "struct" && verdict === "closed") gaps.push(`claim:${claim.id}:struct-held`);
		const fetches = fetchCount(row.fetches);
		if (fetches === undefined || fetches > budgetCap) gaps.push(`claim:${claim.id}:budget`);
		if (tautological.has(claim.id)) gaps.push(`claim:${claim.id}:tautology`);
	}
	const declaredIds = new Set(claims.map((claim) => claim.id));
	for (const row of table.rows) {
		if (!declaredIds.has(row.id)) gaps.push(`claims:extra-row:${row.id}`);
	}
	return gaps;
}
