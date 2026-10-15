/**
 * `write_face` glob normalizer + intersection operator — TS side
 * (mw-write-face-guard W-02, card T-W-I02).
 *
 * Frozen contract:
 * `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md`
 * §3.1 (canonical syntax + parse-time fail-closed rules), §3.2 (deny does NOT
 * participate in the overlap decision; conservative-fallback list), §3.3
 * (three states), §4.2 (segment-level character-pattern intersection), §4.3
 * (epsilon-NFA product over glob segment sequences), §4.4 (face-level operator).
 *
 * The repository already has five "one path vs one pattern" predicates
 * (`worker/read-scope.ts:isSameOrUnder`/`isWithinScope`/`matchedDenyGlob`,
 * `shared/write-surface.ts:matchesWriteScopeEntry` — moved there from
 * `worker/worker-mode.ts` by mw-worker-output-contract T-10 —, Python
 * `xkey.py:fnmatch`);
 * none of them is a glob x glob operator, so this module is new. `minimatch`
 * is only the single-path semantic baseline — it is NEVER called here; the
 * intersection is the hand-written epsilon-NFA product below.
 *
 * Semantics honoured (design.md D-001/D-006):
 *
 * - single `/`-separated syntax; `\` is always a separator, never an escape;
 * - a bare `!` is refused (`write-face-invalid-entry`); `..` is refused
 *   (`write-face-escape`); a top-level `,` inside an entry is refused;
 * - a refusal carries the conductor's `Refused.detail` (`write_face.py:654/668/
 *   674/685`): `present-but-empty write_face head` for an empty head, and
 *   `entry '<raw>'` / `deny entry '<raw>'` for a rejected entry (the raw text,
 *   NOT Python's `repr` quote-selection — see the bounded-difference note in
 *   the W-14 evidence: a raw containing a single quote keeps the single-quote
 *   wrapper here, while Python `repr` switches to double quotes);
 * - `a/**` INCLUDES the bare `a`; leading `./`, empty segments and a trailing
 *   `/` are normalized away; repeated `**` segments collapse;
 * - a literal entry is an EXACT node (a directory must be written `a/**`);
 * - `dot:true` — a leading `.` segment is an ordinary segment;
 * - case sensitivity is an explicit parameter, never inferred from the
 *   platform;
 * - `**` inside a segment (`a**b`) behaves as `*` (does not cross `/`);
 * - the overlap decision never subtracts `deny`;
 * - the Python mirror is `packages/multi-workers/autopilot/write_face.py`; both
 *   sides read the same frozen corpus `test/fixtures/write-face-corpus.json`.
 */
export declare const WRITE_FACE_EMPTY = "write-face-empty";
export declare const WRITE_FACE_INVALID_ENTRY = "write-face-invalid-entry";
export declare const WRITE_FACE_ESCAPE = "write-face-escape";
export declare const WRITE_FACE_OUTSIDE_BASE = "write-face-outside-base";
/** The conductor's `Refused.detail` for a present-but-empty head
 * (`write_face.py:654/674`). The only refusal with no offending entry, so it is
 * the one detail constant instead of a `${label} '${raw}'` rendering. */
export declare const WRITE_FACE_EMPTY_DETAIL = "present-but-empty write_face head";
/** Every parse-time refusal code this module can emit. */
export type WriteFaceRejectCode = typeof WRITE_FACE_EMPTY | typeof WRITE_FACE_INVALID_ENTRY | typeof WRITE_FACE_ESCAPE | typeof WRITE_FACE_OUTSIDE_BASE;
interface LitToken {
    readonly kind: "lit";
    readonly ch: string;
}
interface StarToken {
    readonly kind: "star";
}
interface QMarkToken {
    readonly kind: "qmark";
}
interface ClassToken {
    readonly kind: "class";
    readonly members: readonly string[];
    readonly negated: boolean;
}
type Token = LitToken | StarToken | QMarkToken | ClassToken;
/** One glob segment: the multi-segment wildcard, or a single-segment character
 * pattern (already brace/@()-expanded; a segment carries ONE token run). */
type GlobSegment = {
    readonly kind: "any";
} | {
    readonly kind: "pattern";
    readonly tokens: readonly Token[];
};
/** One normalized allow entry, expanded and tokenized. */
export interface WriteFaceGlob {
    /** Canonical entry text (brace alternative already substituted). */
    readonly text: string;
    readonly segments: readonly GlobSegment[];
    /** A construct the product cannot decide (§3.2): fail closed, treat as overlap. */
    readonly unsupported: boolean;
}
/** A parsed, normalized, non-empty write face (§3.3 "non-empty"). */
export interface WriteFace {
    /** Expanded allow globs, document order, duplicates preserved. */
    readonly allow: readonly WriteFaceGlob[];
    /** Normalized source entries (pre brace expansion), document order. */
    readonly entries: readonly string[];
    /** Normalized deny entries; the overlap operator never uses them (§3.2). */
    readonly deny: readonly string[];
    readonly base: string;
    readonly caseInsensitive: boolean;
}
export interface WriteFaceParseOptions {
    readonly base: string;
    readonly caseInsensitive: boolean;
}
/** §3.3 three states: undeclared / refused / declared. */
export type WriteFaceParseResult = {
    readonly kind: "undeclared";
} | {
    readonly kind: "rejected";
    readonly code: WriteFaceRejectCode;
    /** The conductor's `Refused.detail` (`dispatch.py:1169` composes
     * `reason` as `${code}: ${detail}`). Populated on every refusal this
     * module emits; optional only so older/wider callers keep compiling. */
    readonly detail?: string;
} | {
    readonly kind: "declared";
    readonly face: WriteFace;
};
/** A lexically-provable non-empty intersection (§4.4); `sample` is glob-free. */
export interface WriteFaceConflict {
    readonly sample: string;
    readonly rule: string;
    readonly other: string;
    readonly reason: string;
}
/** Conservative fallback (§3.2): callers MUST treat this as overlap. */
export interface WriteFaceUnsupported {
    readonly unsupported: string;
}
export type WriteFaceOverlapResult = WriteFaceConflict | WriteFaceUnsupported | null;
/**
 * Parse the `write_face:` head of a task.md. Three states (§3.3):
 *
 * - no `write_face:` head, or a dash-only value (`write_face: -`) -> undeclared
 *   (D-003 serial-only; the overlap operator is never called for it);
 * - a present-but-empty head -> refused `write-face-empty`;
 * - a non-empty head -> a normalized, expanded `WriteFace`.
 *
 * An optional `write_face_deny:` head is parsed for completeness, but the
 * overlap operator never uses it (§3.2).
 */
export declare function parseWriteFace(text: string, opts: WriteFaceParseOptions): WriteFaceParseResult;
/**
 * Entry-array variant of {@link parseWriteFace}, for callers (and the shared
 * corpus) that already hold one entry per string. Each element is ONE entry —
 * a top-level `,` inside an element is a refusal rather than a separator.
 */
export declare function parseWriteFaceEntries(entries: readonly string[], opts: WriteFaceParseOptions, denyEntries?: readonly string[]): WriteFaceParseResult;
/**
 * Decide whether two parsed write faces share a lexically-provable path.
 *
 * `a` and `b` must both be declared (an undeclared side is handled by the
 * caller as serial-only, design D-003). `deny` never participates (§3.2).
 * D-111 precedence: a provable conflict among *supported* entries wins; a
 * conservative fallback (`{ unsupported }`) is returned only when no conflict
 * is provable and at least one side carries syntax the product cannot decide.
 * Callers MUST treat `unsupported` as overlap.
 */
export declare function writeFacesOverlap(a: WriteFace, b: WriteFace): WriteFaceOverlapResult;
/** Single conservative predicate: anything but `null` collides. */
export declare function isWriteFaceOverlap(result: WriteFaceOverlapResult): boolean;
export {};
//# sourceMappingURL=write-face.d.ts.map