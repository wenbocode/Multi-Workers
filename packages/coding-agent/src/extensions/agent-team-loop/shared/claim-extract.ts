/**
 * shared/claim-extract.ts — E1 structured claim extraction (T-03, key
 * `claim-driven-review-orchestration`; spec AC-E1, design §2.1).
 *
 * A real review card is prose: it has no `<!-- mw-claims: v1 -->` block, so the
 * split path (L0 → L1) needs a machine-checkable coverage list BEFORE a single
 * unit is spawned. E1 is the cheapest rung of stage 0: take rows that already
 * ARE a list (QG findings, spec AC rows, diff hunks, anti-pattern grep hits)
 * and turn them into {@link Claim} rows mechanically — zero LLM, zero reads.
 *
 * Contract (cards T-03 + T-06):
 *   - consumption order is fixed — `findings` → `acRows` → `diffHunks` →
 *     `antiPatternHits` — so ids `C-01`, `C-02`, … are deterministic (2 digits,
 *     3 from the 100th claim on);
 *   - `type` comes from the 判据 prefix only (`cmd:`/`grep:`/`fs:`/`struct:`);
 *     no prefix (and `manual:`) stays `manual`. The kind is never inferred from
 *     the statement (RQ-3 §2.4: the classifier agrees with the corpus 63.5%);
 *   - `falsifier` is a caller cell when the row carries one (trimmed). E1 only
 *     DERIVES a refutation condition for machine-shaped sources and only when
 *     the derived text is executable: an anti-pattern hit refutes itself when
 *     the pattern is not at `path:line`, a hunk when it does not show the
 *     stated change. Prose rows (`findings`/`acRows`) and every `manual` claim
 *     get NO derived falsifier: there E1 says `extract:falsifier-missing:<id>`
 *     and KEEPS the claim (losing it would lose coverage). The validator is
 *     never relaxed for E1: `claimsGaps` keeps reporting `claim:<id>:falsifier`
 *     and this module renames exactly that gap to the one wording above, so a
 *     missing falsifier has one name and cannot throw;
 *   - the 判据 prefix is normalized to the validator's canonical spelling:
 *     `fs:`/`struct:` both become `shape:` (a `struct` claim may only carry
 *     `shape:`), `cmd:`/`grep:`/`manual:` keep their lowercase canonical form.
 *     Unknown prefixes are left alone;
 *   - source-side reconciliation (AC-E1): a row that cannot become a claim is
 *     `extract:lost-source-row:<index>` (0-based, within its own source list),
 *     a 定位 naming a file outside the change face the input declares is
 *     `extract:foreign-locator:<id>`;
 *   - the produced claims are handed to `claimsGaps` and its findings are
 *     passed through verbatim, except the one falsifier rename above — the
 *     validator keeps one implementation (T-06).
 *
 * Pure by construction (P-048: bad input becomes a gap, never a throw): no
 * project file is read, nothing is written, no model is called. `claimsGaps`
 * only `statSync`es 定位 cells, and the default project root is a path nothing
 * creates, so the default result does not depend on the caller's cwd or tree.
 */

import { tmpdir } from "node:os";
import { join } from "node:path";
import { type Claim, type ClaimBlock, type ClaimType, claimsGaps } from "./dispatch-card.ts";

// ── inputs (card T-03; every field optional, `absent` = no rows) ────────────

/** One prose list row: the shape of a QG finding and of a spec AC line. */
export interface ClaimSourceRow {
	/** 陈述 — what the row asserts. Empty means the row cannot become a claim. */
	text: string;
	/** 定位, copied verbatim (a `path:line`, a symbol, `-`, …). */
	locator: string;
	/** 判据; its prefix picks the claim type. Empty stays empty (a real gap). */
	judgement: string;
	/**
	 * 反证条件 supplied by the caller (T-06). T-03's "`falsifier` stays `''`"
	 * conflicted with the validator, which treats an empty one as a structural
	 * gap; the fix is to carry the caller's text here, not to soften the
	 * validator. Prose rows get no derivation: a human verdict cannot be
	 * machine-refuted, so a missing cell is reported, never invented.
	 */
	falsifier?: string;
}

/** A QG finding row (`findings` source). */
export type ClaimSourceFinding = ClaimSourceRow;

/** A spec AC row (`acRows` source). */
export type ClaimSourceAcRow = ClaimSourceRow;

/** One diff hunk of the change face (the A-class source, spec §2.0). */
export interface ClaimSourceDiffHunk {
	/** Path the hunk touches (repo-relative in practice). */
	path: string;
	/** 1-based first changed line. */
	start: number;
	/** 1-based last changed line (`end >= start`). */
	end: number;
	/** What this hunk is supposed to prove — the caller supplies it, E1 never guesses. */
	statement: string;
	/** 判据; absent keeps the claim `manual` with an empty 判据 (a real gap). */
	judgement?: string;
	/**
	 * 反证条件 supplied by the caller (T-06). When absent, a non-`manual` hunk
	 * derives {@link HUNK_FALSIFIER}: a hunk that does not show the stated
	 * change refutes it, which is executable (re-read the diff).
	 */
	falsifier?: string;
}

/** One anti-pattern grep hit. */
export interface ClaimSourceAntiPattern {
	path: string;
	/** 1-based line of the hit. */
	line: number;
	/** The matched anti-pattern; it becomes the claim statement's subject. */
	pattern: string;
	/** 判据; absent keeps the claim `manual` with an empty 判据 (a real gap). */
	judgement?: string;
	/**
	 * 反证条件 supplied by the caller (T-06). When absent, a non-`manual` hit
	 * derives `在 path:line 处找不到 pattern`: re-grepping that one line is the
	 * refutation, so the condition is executable instead of a restatement.
	 */
	falsifier?: string;
}
export interface ClaimExtractInput {
	findings?: readonly ClaimSourceFinding[];
	acRows?: readonly ClaimSourceAcRow[];
	diffHunks?: readonly ClaimSourceDiffHunk[];
	antiPatternHits?: readonly ClaimSourceAntiPattern[];
}

/** Options of {@link extractClaims}. */
export interface ClaimExtractOptions {
	/**
	 * Root the 定位 paths resolve against. Only `claimsGaps`' soft checks
	 * consult it, so it matters only with `enforce: true`; the default cannot
	 * resolve any file (extraction must not depend on the caller's cwd).
	 */
	projectDir?: string;
	/** D-006 grey switch handed to `claimsGaps`; default `false` (advisory). */
	enforce?: boolean;
}

/** Result of {@link extractClaims}. */
export interface ClaimExtractResult {
	claims: Claim[];
	/**
	 * In emission order: `extract:lost-source-row:<index>` in source-row order
	 * (lost rows as they are scanned), then `extract:foreign-locator:<id>` in
	 * claim order, then the `claimsGaps` findings. A `claim:<id>:falsifier`
	 * finding is renamed to `extract:falsifier-missing:<id>` (one wording per
	 * problem); every other validator finding passes through verbatim.
	 */
	gaps: string[];
	/** Rows the input carried; `sourceRows === claims.length + lost rows`. */
	sourceRows: number;
}

// ── constants ───────────────────────────────────────────────────────────────

/**
 * Default project root: a temp path nothing creates. `claimsGaps` only
 * `statSync`es it, so every 定位 resolves to `unresolved` and the default
 * output stays independent of the caller's cwd; a caller that wants the soft
 * locator checks passes its own `projectDir` together with `enforce: true`.
 */
const UNRESOLVED_PROJECT_DIR = join(tmpdir(), "mw-claim-extract-unresolved");

/**
 * 判据 prefix → self-reported type. `shape:` is accepted as the validator's own
 * alias for `struct` (`CLAIM_TYPE_PREFIX`, `dispatch-card.ts`), so a caller that
 * wants the `type-prefix` advisory to stay quiet can use it.
 */
const JUDGEMENT_PREFIX_RE = /^\s*(cmd|grep|fs|struct|shape)\s*:/;
/** Prefix word → {@link ClaimType}; anything absent reads `manual`. */
const JUDGEMENT_PREFIX_TYPES: Readonly<Record<string, ClaimType>> = {
	cmd: "cmd",
	grep: "grep",
	fs: "struct",
	struct: "struct",
	shape: "struct",
};

/**
 * Prefix word → the validator's canonical 判据 prefix (`CLAIM_TYPE_PREFIX` in
 * `dispatch-card.ts`). `fs:`/`struct:` are aliases of `shape:`; the three
 * lowercase forms are the only spelling of the other prefixes. A word absent
 * from this table is not rewritten (T-06).
 */
const CANONICAL_JUDGEMENT_PREFIX: Readonly<Record<string, string>> = {
	cmd: "cmd:",
	grep: "grep:",
	fs: "shape:",
	struct: "shape:",
	shape: "shape:",
	manual: "manual:",
};

/** `  FS： rest` → prefix word, separator, remainder (`rest` kept verbatim). */
const JUDGEMENT_HEAD_RE = /^\s*(cmd|grep|fs|struct|shape|manual)\s*([:：])([\s\S]*)$/i;

/** Derived 反证条件 of a hunk: re-read the diff and find the stated change missing. */
const HUNK_FALSIFIER = "该 hunk 未体现陈述的改动（符号未改 / 改在其它定位）";

/**
 * `claim:<id>:falsifier` — the single validator finding E1 rewords (T-06). The
 * validator keeps its rule; only the caller-facing wording changes, one-to-one
 * with the claim it names, so no claim loses coverage and nothing throws.
 */
const CLAIM_FALSIFIER_GAP_RE = /^claim:(C-\d{2,3}(?:\.\d+)?):falsifier$/;

/** E1 预算 defaults: a hunk usually has to be read with its surrounding context. */
const CLAIM_BUDGET_DEFAULT = 1;
const CLAIM_BUDGET_DIFF_HUNK = 2;

/** `path[:line[-line]]`; the path part is group 1. */
const LOCATOR_RANGE_RE = /^(.*?):\d+(?:-\d+)?$/;
/** A locator names a file when it has an extension (a separator also does). */
const PATH_EXT_RE = /\.[A-Za-z][A-Za-z0-9]{0,7}$/;

// ── tolerance helpers (P-048: report, never throw) ──────────────────────────

/** Rows of one optional source; a non-array is "no rows" instead of a throw. */
function rowsOf(value: unknown): readonly unknown[] {
	return Array.isArray(value) ? value : [];
}

/** `row[key]` when the row is an object and the field a string, else `""`. */
function textField(row: unknown, key: string): string {
	if (typeof row !== "object" || row === null) return "";
	const value = (row as Record<string, unknown>)[key];
	return typeof value === "string" ? value : "";
}

/** `row[key]` when it is an integer, `undefined` otherwise. */
function intField(row: unknown, key: string): number | undefined {
	if (typeof row !== "object" || row === null) return undefined;
	const value = (row as Record<string, unknown>)[key];
	return typeof value === "number" && Number.isInteger(value) ? value : undefined;
}

/** Full-width `：` → `:`, ideographic space → space, then trim + lower-case. */
function foldJudgement(judgement: string): string {
	return judgement
		.replace(/：/g, ":")
		.replace(/\u3000/g, " ")
		.trim()
		.toLowerCase();
}

/** Claim type from the 判据 prefix; `manual:`/no prefix/everything else → `manual`. */
function claimTypeOf(judgement: string): ClaimType {
	const match = JUDGEMENT_PREFIX_RE.exec(foldJudgement(judgement));
	if (match === null) return "manual";
	const prefix = match[1] ?? "";
	return JUDGEMENT_PREFIX_TYPES[prefix] ?? "manual";
}

/**
 * Rewrite a 判据 prefix to the validator's canonical spelling, keeping the rest
 * of the cell verbatim (T-06). `fs:`/`struct:` → `shape:` so a `struct` claim
 * does not trip `claim:<id>:type-prefix`; `cmd:`/`grep:`/`manual:` only lose
 * padding and colon width. A prefix outside the table is not rewritten.
 */
function normalizeJudgementPrefix(judgement: string): string {
	const match = JUDGEMENT_HEAD_RE.exec(judgement);
	if (match === null) return judgement;
	const canonical = CANONICAL_JUDGEMENT_PREFIX[(match[1] ?? "").toLowerCase()];
	if (canonical === undefined) return judgement;
	return `${canonical}${match[3] ?? ""}`;
}

/** `C-01` … `C-99`, then three digits from the 100th claim on. */
function claimId(number: number): string {
	return `C-${String(number).padStart(number > 99 ? 3 : 2, "0")}`;
}

/** Comparison form of a path: `\` → `/`, a leading `./` dropped. */
function normalizePath(text: string): string {
	return text.trim().replace(/\\/g, "/").replace(/^\.\//, "");
}

/**
 * Path part of a 定位 cell (`src/a.ts:12-20` → `src/a.ts`). A bare symbol, `-`
 * and an empty cell name no file, so there is nothing to reconcile.
 */
function locatorPath(locator: string): string | undefined {
	const raw = locator.replace(/`/g, "").replace(/#.*$/, "").trim();
	const ranged = LOCATOR_RANGE_RE.exec(raw);
	const candidate = (ranged === null ? raw : (ranged[1] ?? "")).trim();
	if (candidate === "" || candidate === "-") return undefined;
	if (!candidate.includes("/") && !PATH_EXT_RE.test(candidate)) return undefined;
	return normalizePath(candidate);
}

/**
 * The claim's path belongs to the change face the input declared. A segment
 * suffix match keeps an absolute 定位 and a repo-relative hunk path comparable
 * without guessing a project root.
 */
function isKnownPath(pathText: string, known: readonly string[]): boolean {
	return known.some(
		(candidate) => candidate === pathText || candidate.endsWith(`/${pathText}`) || pathText.endsWith(`/${candidate}`),
	);
}

// ── candidates ──────────────────────────────────────────────────────────────

/** One extracted row before its `C-xx` id is assigned. */
interface ExtractCandidate {
	type: ClaimType;
	statement: string;
	falsifier: string;
	locator: string;
	judgement: string;
	budget: number;
	/** 1-based index of the row inside its own source list (diagnostics only). */
	row: number;
	/** Path part of `locator`, `undefined` when the cell names no file. */
	path: string | undefined;
}

/** One prose row → candidate, `undefined` when the row states nothing. */
function proseCandidate(row: unknown, index: number): ExtractCandidate | undefined {
	const statement = textField(row, "text").trim();
	if (statement === "") return undefined;
	const judgement = normalizeJudgementPrefix(textField(row, "judgement"));
	const locator = textField(row, "locator").trim();
	return {
		type: claimTypeOf(judgement),
		statement,
		// Prose rows never get a derived falsifier: a human verdict is not
		// machine-refutable, so a missing cell is reported instead (T-06).
		falsifier: textField(row, "falsifier").trim(),
		locator,
		judgement,
		budget: CLAIM_BUDGET_DEFAULT,
		row: index + 1,
		path: locatorPath(locator),
	};
}

/**
 * A machine-shaped row's falsifier: the caller's cell when present, otherwise
 * the derived one for a non-`manual` claim. `manual` means no 判据 prefix was
 * written, so the row is prose in effect and derivation is forbidden.
 */
function machineFalsifier(cells: string, type: ClaimType, derived: string): string {
	const supplied = cells.trim();
	if (supplied !== "") return supplied;
	return type === "manual" ? "" : derived;
}

// ── extraction (AC-E1) ──────────────────────────────────────────────────────

/**
 * E1: rows already shaped like a list → {@link Claim} rows (AC-E1).
 *
 * Consumption order is fixed, ids are positional, and nothing depends on the
 * clock, a random source or the filesystem, so two calls with the same input
 * return deeply equal results (`JSON.stringify` stable). Malformed rows are
 * reported as `extract:lost-source-row:<index>` and skipped instead of throwing.
 */
export function extractClaims(input: ClaimExtractInput = {}, opts: ClaimExtractOptions = {}): ClaimExtractResult {
	const findings = rowsOf(input.findings);
	const acRows = rowsOf(input.acRows);
	const diffHunks = rowsOf(input.diffHunks);
	const antiPatternHits = rowsOf(input.antiPatternHits);
	const candidates: ExtractCandidate[] = [];
	const gaps: string[] = [];
	/** Paths the input itself declares as the change face (hunks + hits). */
	const knownPaths: string[] = [];

	// 1. QG findings: 陈述/定位 are copied verbatim, 判据 keeps its text but gets
	//    the canonical prefix; prose rows derive no falsifier (T-06).
	for (const [index, row] of findings.entries()) {
		const candidate = proseCandidate(row, index);
		if (candidate === undefined) gaps.push(`extract:lost-source-row:${index}`);
		else candidates.push(candidate);
	}

	// 2. Spec AC rows: same shape, own id block, same verbatim policy.
	for (const [index, row] of acRows.entries()) {
		const candidate = proseCandidate(row, index);
		if (candidate === undefined) gaps.push(`extract:lost-source-row:${index}`);
		else candidates.push(candidate);
	}

	// 3. Diff hunks: A-class change-face rows, 定位 `path:start-end`, 预算 2.
	for (const [index, hunk] of diffHunks.entries()) {
		const pathText = textField(hunk, "path").trim();
		if (pathText !== "" && !knownPaths.includes(normalizePath(pathText))) {
			knownPaths.push(normalizePath(pathText));
		}
		const statement = textField(hunk, "statement").trim();
		const start = intField(hunk, "start");
		const end = intField(hunk, "end");
		const validRange = start !== undefined && start >= 1 && end !== undefined && end >= start;
		if (statement === "" || pathText === "" || !validRange) {
			gaps.push(`extract:lost-source-row:${index}`);
			continue;
		}
		const judgement = normalizeJudgementPrefix(textField(hunk, "judgement"));
		const locator = `${pathText}:${start}-${end}`;
		const type = claimTypeOf(judgement);
		candidates.push({
			type,
			statement,
			falsifier: machineFalsifier(textField(hunk, "falsifier"), type, HUNK_FALSIFIER),
			locator,
			judgement,
			budget: CLAIM_BUDGET_DIFF_HUNK,
			row: index + 1,
			path: normalizePath(pathText),
		});
	}

	// 4. Anti-pattern hits: 定位 `path:line`, 预算 1.
	for (const [index, hit] of antiPatternHits.entries()) {
		const pathText = textField(hit, "path").trim();
		if (pathText !== "" && !knownPaths.includes(normalizePath(pathText))) {
			knownPaths.push(normalizePath(pathText));
		}
		const pattern = textField(hit, "pattern").trim();
		const line = intField(hit, "line");
		if (pattern === "" || pathText === "" || line === undefined || line < 1) {
			gaps.push(`extract:lost-source-row:${index}`);
			continue;
		}
		const judgement = normalizeJudgementPrefix(textField(hit, "judgement"));
		const locator = `${pathText}:${line}`;
		const type = claimTypeOf(judgement);
		candidates.push({
			type,
			statement: `反模式命中：${pattern}`,
			// Re-grepping that one line is the executable refutation (T-06).
			falsifier: machineFalsifier(textField(hit, "falsifier"), type, `在 ${locator} 处找不到 ${pattern}`),
			locator,
			judgement,
			budget: CLAIM_BUDGET_DEFAULT,
			row: index + 1,
			path: normalizePath(pathText),
		});
	}

	// 5. Ids are positional: source order in, `C-01`, `C-02`, … out.
	const claims: Claim[] = candidates.map((candidate, offset) => ({
		id: claimId(offset + 1),
		type: candidate.type,
		parent: "",
		statement: candidate.statement,
		falsifier: candidate.falsifier,
		locator: candidate.locator,
		judgement: candidate.judgement,
		budget: candidate.budget,
		row: candidate.row,
	}));

	// 6. Foreign locators: a 定位 may only point into the declared change face.
	//    With no hunk/hit path declared there is nothing to be foreign to.
	if (knownPaths.length > 0) {
		for (const [offset, candidate] of candidates.entries()) {
			if (candidate.path === undefined) continue;
			if (isKnownPath(candidate.path, knownPaths)) continue;
			gaps.push(`extract:foreign-locator:${claimId(offset + 1)}`);
		}
	}

	// 7. The validator keeps one implementation: pass its findings through, but
	//    rename the one gap E1 is responsible for so a missing falsifier has a
	//    single wording (`claim:<id>:falsifier` → `extract:falsifier-missing:<id>`).
	//    The replacement is 1:1 and never drops a claim: the claim itself is kept.
	const block: ClaimBlock = { present: claims.length > 0, claims, errors: [] };
	for (const gap of claimsGaps(block, {
		projectDir: opts.projectDir ?? UNRESOLVED_PROJECT_DIR,
		enforce: opts.enforce === true,
	})) {
		const falsifierGap = CLAIM_FALSIFIER_GAP_RE.exec(gap);
		gaps.push(falsifierGap === null ? gap : `extract:falsifier-missing:${falsifierGap[1] ?? ""}`);
	}

	return {
		claims,
		gaps,
		sourceRows: findings.length + acRows.length + diffHunks.length + antiPatternHits.length,
	};
}
