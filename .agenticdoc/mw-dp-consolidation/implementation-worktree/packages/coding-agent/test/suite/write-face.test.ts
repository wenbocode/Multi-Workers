/**
 * `write_face` glob intersection operator — TS side (mw-write-face-guard W-02).
 *
 * The frozen corpus `packages/multi-workers/test/fixtures/write-face-corpus.json`
 * (read-only) is the single contract both language sides must satisfy: 23
 * `parse` rows and 59 `overlap` rows. `overlap` rows only pin the conclusion
 * kind (`overlap` / `none` / `reject` / `serial_only` / `unsupported`) plus
 * "the witness is glob-free", so the two sides do not have to agree on the
 * witness text. D-111: at intersection time a provable conflict wins over an
 * unsupported-syntax entry; `unsupported` means "cannot decide".
 *
 * Pure-function unit test: no provider, no credentials, no fs writes inside
 * the repository.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { minimatch } from "minimatch";
import { afterAll, describe, expect, it } from "vitest";
import {
	parseWriteFace,
	parseWriteFaceEntries,
	WRITE_FACE_EMPTY,
	WRITE_FACE_EMPTY_DETAIL,
	WRITE_FACE_ESCAPE,
	WRITE_FACE_INVALID_ENTRY,
	WRITE_FACE_OUTSIDE_BASE,
	type WriteFace,
	type WriteFaceOverlapResult,
	type WriteFaceParseResult,
	writeFacesOverlap,
} from "../../src/extensions/agent-team-loop/shared/write-face.ts";

const CORPUS_FILE = fileURLToPath(
	new URL("../../../multi-workers/test/fixtures/write-face-corpus.json", import.meta.url),
);
const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
/** Absolute repository root at test time (`$REPO` in the corpus protocol). */
const REPO_ROOT = fileURLToPath(new URL("../../../../", import.meta.url)).replace(/\/+$/, "");
/** Absolute path guaranteed NOT under `$REPO` (`$OUTSIDE` in the protocol). */
const OUTSIDE = fs.mkdtempSync(path.join(os.tmpdir(), "mw-write-face-outside-"));

afterAll(() => {
	fs.rmSync(OUTSIDE, { recursive: true, force: true });
});

interface ParseCase {
	name: string;
	head: string[];
	expect: { kind: string; entries?: string[]; code?: string };
	note?: string;
}
interface OverlapCase {
	name: string;
	a: string[] | null;
	a_deny?: string[];
	b: string[] | null;
	case_insensitive: boolean;
	expect: { kind: string; sample_globfree?: boolean; side?: string; code?: string };
}
interface Corpus {
	schema: string;
	counts: { parse: number; overlap: number };
	protocol: { magic_chars: string[] };
	notes: string[];
	parse: ParseCase[];
	overlap: OverlapCase[];
}

const CORPUS = JSON.parse(fs.readFileSync(CORPUS_FILE, "utf8")) as Corpus;
const MAGIC_RE = /[*?[\]{}]/;
const OPTIONS = { base: REPO_ROOT, caseInsensitive: false };

function subst(value: string): string {
	return value.split("$REPO").join(REPO_ROOT).split("$OUTSIDE").join(OUTSIDE);
}

function declared(result: WriteFaceParseResult): WriteFace {
	if (result.kind !== "declared") throw new Error(`expected a declared face, got ${JSON.stringify(result)}`);
	return result.face;
}

type Kind = "overlap" | "none" | "unsupported";

function overlapKind(
	a: readonly string[],
	b: readonly string[],
	caseInsensitive = false,
	aDeny: readonly string[] = [],
): Kind {
	const opts = { base: REPO_ROOT, caseInsensitive };
	const fa = declared(parseWriteFaceEntries(a, opts, aDeny));
	const fb = declared(parseWriteFaceEntries(b, opts));
	return classify(writeFacesOverlap(fa, fb));
}

function classify(result: WriteFaceOverlapResult): Kind {
	if (result === null) return "none";
	if ("unsupported" in result) return "unsupported";
	return "overlap";
}

describe("write_face corpus — parse (23 rows)", () => {
	it("sanity: corpus is the frozen shape", () => {
		expect(CORPUS.schema).toBe("mw-write-face-corpus/v1");
		expect(fs.existsSync(MULTI_WORKERS_DIR)).toBe(true);
		expect(OUTSIDE.toLowerCase().startsWith(REPO_ROOT.toLowerCase())).toBe(false);
	});

	for (const row of CORPUS.parse) {
		it(row.name, () => {
			const text = row.head.map(subst).join("\n");
			const result = parseWriteFace(text, OPTIONS);
			if (row.expect.kind === "unknown") {
				expect(result).toEqual({ kind: "undeclared" });
				return;
			}
			if (row.expect.kind === "reject") {
				expect(result.kind).toBe("rejected");
				if (result.kind === "rejected") expect(result.code).toBe(row.expect.code);
				return;
			}
			expect(result.kind).toBe("declared");
			if (result.kind === "declared") expect(result.face.entries).toEqual(row.expect.entries);
		});
	}
});

describe("write_face corpus — overlap (59 rows)", () => {
	it("sanity: counts and kind distribution are frozen", () => {
		expect(CORPUS.counts.parse).toBe(23);
		expect(CORPUS.counts.overlap).toBe(59);
		expect(CORPUS.parse.length).toBe(23);
		expect(CORPUS.overlap.length).toBe(59);
		const kinds: Record<string, number> = { overlap: 0, none: 0, reject: 0, serial_only: 0, unsupported: 0 };
		for (const row of CORPUS.overlap) kinds[row.expect.kind] = (kinds[row.expect.kind] ?? 0) + 1;
		expect(kinds).toEqual({ overlap: 34, none: 13, reject: 8, serial_only: 1, unsupported: 3 });
	});

	for (const row of CORPUS.overlap) {
		it(row.name, () => {
			if (row.a === null || row.b === null) {
				expect(row.expect.kind).toBe("serial_only");
				// An undeclared side is never handed to the operator (D-003);
				// a document without the head parses as undeclared instead.
				expect(parseWriteFace("# T-01\n\n- type: coding", OPTIONS)).toEqual({ kind: "undeclared" });
				return;
			}
			const opts = { base: REPO_ROOT, caseInsensitive: row.case_insensitive };
			const ra = parseWriteFaceEntries(row.a.map(subst), opts, (row.a_deny ?? []).map(subst));
			const rb = parseWriteFaceEntries(row.b.map(subst), opts);
			if (row.expect.kind === "reject") {
				const side = row.expect.side === "a" ? ra : rb;
				expect(side.kind).toBe("rejected");
				if (side.kind === "rejected") expect(side.code).toBe(row.expect.code);
				return;
			}
			expect(ra.kind).toBe("declared");
			expect(rb.kind).toBe("declared");
			if (ra.kind !== "declared" || rb.kind !== "declared") return;
			const result = writeFacesOverlap(ra.face, rb.face);
			if (row.expect.kind === "none") {
				expect(result).toBeNull();
				return;
			}
			if (row.expect.kind === "unsupported") {
				// §3.2 fallback / D-111: no conflict is provable and at least one
				// side carries unsupported syntax; callers treat this as overlap.
				expect(result !== null && "unsupported" in result).toBe(true);
				return;
			}
			expect(row.expect.kind).toBe("overlap");
			expect(row.expect.sample_globfree).toBe(true);
			expect(result).not.toBeNull();
			expect(result !== null && !("unsupported" in result)).toBe(true);
			if (result !== null && !("unsupported" in result)) {
				expect(result.sample.length).toBeGreaterThan(0);
				expect(MAGIC_RE.test(result.sample)).toBe(false);
			}
		});
	}
});

describe("hard acceptance points (§4.3, card requirement 2)", () => {
	it("bare ** overlaps a multi-segment path (`**` self-loop)", () => {
		// §4.3 hard acceptance point: `globsOverlap(["**"], ["x", "y"])` at the
		// segment level. As entries, `**` vs the two-segment path `x/y` exercises
		// the self-loop; the two-entry form must overlap as well.
		const opts = OPTIONS;
		const fa = declared(parseWriteFaceEntries(["**"], opts));
		const fb = declared(parseWriteFaceEntries(["x/y"], opts));
		const result = writeFacesOverlap(fa, fb);
		expect(result).not.toBeNull();
		if (result !== null && !("unsupported" in result)) expect(result.sample).toBe("x/y");
		expect(overlapKind(["**"], ["x", "y"])).toBe("overlap");
	});

	it("mid ** expands to zero segments (`a/**/b` vs `a/b`)", () => {
		expect(overlapKind(["a/**/b"], ["a/b"])).toBe("overlap");
	});

	it("`a/**` includes the bare `a`", () => {
		expect(overlapKind(["a/**"], ["a"])).toBe("overlap");
		expect(overlapKind(["a/b/**"], ["a/b"])).toBe("overlap");
	});

	it("`a/**/*` still requires one segment", () => {
		expect(overlapKind(["a/**/*"], ["a"])).toBe("none");
	});

	it("witnesses are concrete, glob-free paths", () => {
		const fa = declared(parseWriteFaceEntries(["packages/x/**"], OPTIONS));
		const fb = declared(parseWriteFaceEntries(["packages/x/y.ts"], OPTIONS));
		const result = writeFacesOverlap(fa, fb);
		expect(result).not.toBeNull();
		if (result !== null && !("unsupported" in result)) {
			expect(result.sample).toBe("packages/x/y.ts");
			expect(result.rule).toBe("packages/x/**");
			expect(result.other).toBe("packages/x/y.ts");
		}
	});

	it("`**` inside a segment behaves as `*` (does not cross `/`)", () => {
		expect(overlapKind(["a**b"], ["axb"])).toBe("overlap");
		expect(overlapKind(["a/**b"], ["a/x/b"])).toBe("none");
	});
});

describe("conservative fallbacks (§3.2, card requirement 4)", () => {
	it("extglob `+()` / `*()` / `?()` and negated `!()` -> unsupported", () => {
		const opts = { base: REPO_ROOT, caseInsensitive: false };
		const clean = declared(parseWriteFaceEntries(["a/b.ts"], opts));
		for (const entry of ["a/+(b)/**", "a/*(b)/**", "a/?(b)/**", "a/!(b)/**", "a/@(b|c)/**"]) {
			const parsed = parseWriteFaceEntries([entry], opts);
			expect(parsed.kind).toBe("declared");
			if (parsed.kind !== "declared") continue;
			const flagged = parsed.face.allow.some((glob) => glob.unsupported);
			const result = writeFacesOverlap(parsed.face, clean);
			if (entry === "a/@(b|c)/**") {
				// `@(a|b)` IS part of the §3.1 grammar and is expanded, not flagged.
				expect(flagged).toBe(false);
				expect("unsupported" in (result ?? {})).toBe(false);
			} else {
				expect(flagged).toBe(true);
				expect(result).toEqual({ unsupported: "unsupported-syntax" });
			}
		}
	});

	it("illegal class -> unsupported", () => {
		const opts = { base: REPO_ROOT, caseInsensitive: false };
		for (const entry of ["a/[bc/**", "a/[]/**"]) {
			const parsed = declared(parseWriteFaceEntries([entry], opts));
			expect(parsed.allow.some((glob) => glob.unsupported)).toBe(true);
		}
	});

	it("brace nesting beyond the depth limit -> unsupported", () => {
		let nested = "z";
		for (let i = 0; i < 10; i++) nested = `{a,${nested}}`;
		const parsed = declared(parseWriteFaceEntries([`a/${nested}/**`], OPTIONS));
		expect(parsed.allow.some((glob) => glob.unsupported)).toBe(true);
	});

	it("segment token-run limit -> unsupported", () => {
		const parsed = declared(parseWriteFaceEntries([`a/${"*".repeat(300)}`], OPTIONS));
		expect(parsed.allow.some((glob) => glob.unsupported)).toBe(true);
	});

	it("glob product state limit -> unsupported (BFS-level fallback)", () => {
		const many = `${"x/".repeat(300)}`;
		const result = overlapKind([many], [many]);
		expect(result).toBe("unsupported");
	});

	it("incomparable base / case mode -> unsupported", () => {
		const inRepo = declared(parseWriteFaceEntries(["a/**"], { base: REPO_ROOT, caseInsensitive: false }));
		const outside = declared(parseWriteFaceEntries(["a/**"], { base: OUTSIDE, caseInsensitive: false }));
		expect(writeFacesOverlap(inRepo, outside)).toEqual({ unsupported: "incomparable-base" });
		// A case-mode mismatch is only reachable once the (per-side folded)
		// bases are equal; an all-lowercase base keeps the two branches distinct.
		const cs = declared(parseWriteFaceEntries(["a/**"], { base: "/repo", caseInsensitive: false }));
		const ci = declared(parseWriteFaceEntries(["a/**"], { base: "/repo", caseInsensitive: true }));
		expect(writeFacesOverlap(cs, ci)).toEqual({ unsupported: "incomparable-case-mode" });
	});

	it("a bare `!` is a parse refusal, not a silent overlap", () => {
		expect(parseWriteFaceEntries(["!packages/x/**"], OPTIONS)).toEqual({
			kind: "rejected",
			code: WRITE_FACE_INVALID_ENTRY,
			detail: "entry '!packages/x/**'",
		});
	});
});

describe("deny never participates (§3.2)", () => {
	it("adding a deny that covers the whole intersection does not change the verdict", () => {
		const opts = { base: REPO_ROOT, caseInsensitive: false };
		const withoutDeny = classify(
			writeFacesOverlap(
				declared(parseWriteFaceEntries(["a/**"], opts)),
				declared(parseWriteFaceEntries(["a/b"], opts)),
			),
		);
		const covered = classify(
			writeFacesOverlap(
				declared(parseWriteFaceEntries(["a/**"], opts, ["a/**"])),
				declared(parseWriteFaceEntries(["a/b"], opts)),
			),
		);
		const partiallyCovered = classify(
			writeFacesOverlap(
				declared(parseWriteFaceEntries(["a/**"], opts, ["a/b"])),
				declared(parseWriteFaceEntries(["a/b"], opts)),
			),
		);
		expect(withoutDeny).toBe("overlap");
		expect(covered).toBe("overlap");
		expect(partiallyCovered).toBe("overlap");
	});

	it("deny entries are parsed and carried but never consumed", () => {
		const face = declared(parseWriteFaceEntries(["a/**"], OPTIONS, ["a/b", "a/c"]));
		expect(face.deny).toEqual(["a/b", "a/c"]);
	});
});

describe("§3.3 three states and normalization", () => {
	it("missing head and dash-only value are both undeclared", () => {
		expect(parseWriteFace("# T-01\n\n- type: coding", OPTIONS)).toEqual({ kind: "undeclared" });
		expect(parseWriteFace("write_face: -", OPTIONS)).toEqual({ kind: "undeclared" });
		expect(parseWriteFace("write_face:   -  ", OPTIONS)).toEqual({ kind: "undeclared" });
	});

	it("present-but-empty head is refused, not treated as an empty set", () => {
		expect(parseWriteFace("write_face:", OPTIONS)).toEqual({
			kind: "rejected",
			code: WRITE_FACE_EMPTY,
			detail: WRITE_FACE_EMPTY_DETAIL,
		});
		expect(parseWriteFace("write_face: a/**,,", OPTIONS).kind).toBe("declared");
		expect(parseWriteFaceEntries([""], OPTIONS)).toEqual({
			kind: "rejected",
			code: WRITE_FACE_EMPTY,
			detail: WRITE_FACE_EMPTY_DETAIL,
		});
	});

	it("indented block list is accepted and equivalent to the one-line form", () => {
		const block = parseWriteFace("write_face:\n  - a/**\n  - b/c.ts", OPTIONS);
		const inline = parseWriteFace("write_face: a/**, b/c.ts", OPTIONS);
		expect(block.kind).toBe("declared");
		expect(inline.kind).toBe("declared");
		if (block.kind === "declared" && inline.kind === "declared")
			expect(block.face.entries).toEqual(inline.face.entries);
	});

	it("normalizes `./`, `//`, trailing `/`, repeated `**` and `\\`", () => {
		const opts = { base: REPO_ROOT, caseInsensitive: false };
		const cases: Array<[string, string]> = [
			["./packages/x/**", "packages/x/**"],
			["packages//x/**", "packages/x/**"],
			["packages/x/", "packages/x"],
			["a/**/**", "a/**"],
			["src\\x\\**", "src/x/**"],
		];
		for (const [input, expected] of cases) {
			const face = declared(parseWriteFaceEntries([input], opts));
			expect(face.entries).toEqual([expected]);
		}
	});

	it("escapes and outside-base absolutes are refused with stable codes", () => {
		const opts = { base: REPO_ROOT, caseInsensitive: false };
		expect(parseWriteFaceEntries(["a/../b/**"], opts)).toEqual({
			kind: "rejected",
			code: WRITE_FACE_ESCAPE,
			detail: "entry 'a/../b/**'",
		});
		expect(parseWriteFaceEntries([`${OUTSIDE}/packages/x/**`], opts)).toEqual({
			kind: "rejected",
			code: WRITE_FACE_OUTSIDE_BASE,
			detail: `entry '${OUTSIDE}/packages/x/**'`,
		});
		expect(parseWriteFaceEntries(['"a,b"'], opts)).toEqual({
			kind: "rejected",
			code: WRITE_FACE_INVALID_ENTRY,
			detail: "entry '\"a,b\"'",
		});
		const inside = declared(parseWriteFaceEntries([`${REPO_ROOT}/packages/x/**`], opts));
		expect(inside.entries).toEqual(["packages/x/**"]);
	});

	describe("rejected detail is the conductor's `Refused.detail` (T-W-I14)", () => {
		it("every rejected entry keeps its raw text under `entry '<raw>'`", () => {
			const cases: Array<[string, string, string]> = [
				["!x/**", WRITE_FACE_INVALID_ENTRY, "entry '!x/**'"],
				["a/../b/**", WRITE_FACE_ESCAPE, "entry 'a/../b/**'"],
				[`${OUTSIDE}/x/**`, WRITE_FACE_OUTSIDE_BASE, `entry '${OUTSIDE}/x/**'`],
				['"a,b"', WRITE_FACE_INVALID_ENTRY, "entry '\"a,b\"'"],
			];
			for (const [entry, code, detail] of cases) {
				expect(parseWriteFaceEntries([entry], OPTIONS), entry).toEqual({ kind: "rejected", code, detail });
			}
		});

		it("an off-face entry inside a block list reports that entry's raw text", () => {
			// The block-list carrier is the D-113 form; the rejected entry must be
			// the one the author wrote, not the normalized head value.
			expect(parseWriteFace("write_face:\n  - packages/x/**\n  - !packages/y/**\n", OPTIONS)).toEqual({
				kind: "rejected",
				code: WRITE_FACE_INVALID_ENTRY,
				detail: "entry '!packages/y/**'",
			});
		});

		it("a refused deny entry uses the conductor's `deny entry` label", () => {
			// `write_face.py:685` (`f"deny entry {raw!r}"`); the overlap operator
			// never consumes `deny`, but the refusal detail is still surfaced.
			expect(parseWriteFaceEntries(["a/**"], OPTIONS, ["!x/**"])).toEqual({
				kind: "rejected",
				code: WRITE_FACE_INVALID_ENTRY,
				detail: "deny entry '!x/**'",
			});
		});

		it("the raw text is preserved verbatim (no repr quote-selection)", () => {
			// Known bounded difference, pinned here so a future `repr` emulation is
			// a deliberate change: Python `repr('x\'y/**')` is `"x'y/**"` (double
			// quotes), while the operator keeps the plain single-quote wrapper. The
			// two sides agree on everything except the wrapper quote style.
			const result = parseWriteFaceEntries(["x'y/**"], OPTIONS);
			expect(result).toEqual({
				kind: "rejected",
				code: WRITE_FACE_INVALID_ENTRY,
				detail: "entry 'x'y/**'",
			});
		});
	});

	it("brace alternation expands inside one entry", () => {
		const face = declared(parseWriteFaceEntries(["a/{b,c}/**"], OPTIONS));
		expect(face.allow.map((glob) => glob.text)).toEqual(["a/b/**", "a/c/**"]);
		expect(overlapKind(["a/{b,c}/**"], ["a/c/x.md"])).toBe("overlap");
	});

	it("case sensitivity is an explicit parameter", () => {
		expect(overlapKind(["packages/x/**"], ["packages/X/**"], true)).toBe("overlap");
		expect(overlapKind(["packages/x/**"], ["packages/X/**"], false)).toBe("none");
		expect(overlapKind(["a/**"], ["A/B"], true)).toBe("overlap");
		expect(overlapKind(["a/**"], ["A/B"], false)).toBe("none");
	});

	it("dot segments are ordinary (dot:true semantics)", () => {
		expect(overlapKind(["**"], [".agenticdoc/k/x.md"])).toBe("overlap");
		expect(overlapKind(["a/**/*.ts"], ["a/.x/b.ts"])).toBe("overlap");
	});
});

describe("bare minimatch is not the contract (evidence: §3.1 vs minimatch)", () => {
	/** Vectors where a bare `minimatch(path, pattern)` call would reach the
	 * OPPOSITE conclusion from the §3.1 contract for one side of the pair.
	 * `caseInsensitive` reproduces the corpus's V04-ci/V40 setting for the one
	 * case-folding vector. */
	const divergences: Array<{ witness: string; pattern: string; caseInsensitive: boolean; note: string }> = [
		// a/** must include the bare directory; bare minimatch does not.
		{ witness: "a", pattern: "a/**", caseInsensitive: false, note: "trailing /** includes the bare dir" },
		{
			witness: "packages/x",
			pattern: "packages/x/**",
			caseInsensitive: false,
			note: "trailing /** includes the bare dir",
		},
		{ witness: "a/b", pattern: "a/b/**", caseInsensitive: false, note: "trailing /** includes the bare dir" },
		// dot:true; bare minimatch defaults to dot:false.
		{ witness: "a/.x/b.ts", pattern: "a/**/*.ts", caseInsensitive: false, note: "dot:true" },
		{ witness: ".agenticdoc/k/x.md", pattern: "**", caseInsensitive: false, note: "dot:true" },
		// win32 case folding; bare minimatch is case-sensitive by default.
		{ witness: "A/B", pattern: "a/b", caseInsensitive: true, note: "explicit case folding" },
		// lexical normalization; bare minimatch does not fold `./` or `\`.
		{ witness: "./a/b.ts", pattern: "a/b.ts", caseInsensitive: false, note: "leading ./ normalization" },
	];

	it("bare minimatch disagrees, our operator agrees with §3.1", () => {
		for (const { witness, pattern, caseInsensitive } of divergences) {
			expect(minimatch(witness, pattern), `${witness} vs ${pattern}`).toBe(false);
			expect(overlapKind([pattern], [witness], caseInsensitive)).toBe("overlap");
		}
	});

	it("a single minimatch call cannot decide glob x glob at all", () => {
		// `**/*.ts` and `packages/**/*.py` are disjoint (§3.1 -> none), but
		// minimatch has no pattern-vs-pattern form; the operator proves it.
		expect(overlapKind(["**/*.ts"], ["packages/**/*.py"])).toBe("none");
		// A witness from the operator is accepted by minimatch where the
		// contract and minimatch agree on plain paths.
		expect(minimatch("packages/x/y.ts", "packages/**")).toBe(true);
		expect(overlapKind(["packages/**"], ["packages/x/y.ts"])).toBe("overlap");
	});
});
