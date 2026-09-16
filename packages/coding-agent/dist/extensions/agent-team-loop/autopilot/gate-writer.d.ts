/**
 * gate-writer.ts — the `/autopilot gate <id> approve|reject` answer writer
 * (goal-autopilot T-15, design D-105, AC-016).
 *
 * Answering a gate = rewriting four frontmatter fields of the gate file —
 * `status` / `answered_at` / `answered_by` (the answering window's claimId,
 * for audit) / `note` — under `.mw/gates.lock` (O_CREAT|O_EXCL, the shared
 * file-lock protocol). EVERY other line is preserved byte-for-byte,
 * including a trailing CR when the source line had one, so hand-edited gate
 * files keep their exact shape across an answer.
 *
 * Creation is conductor-only (gates.py); this module never creates gates and
 * never reorders or synthesizes fields — conductor-created gates always
 * carry all 12 frontmatter fields (gates.py FRONTMATTER_FIELDS), so the
 * rewrite targets existing lines only. Manual file edits remain equally
 * legal answers (the file is the source of truth); this writer is just the
 * audited path. All paths are explicit parameters — nothing is derived
 * here, so tests drive the writer without a project layout.
 */
import { type LockOptions } from "../shared/file-lock.ts";
export interface AnswerGateOptions {
    /** Path of the gate .md file to answer. */
    gateFile: string;
    /** The `.mw/gates.lock` path (O_CREAT|O_EXCL). */
    lockFile: string;
    decision: "approve" | "reject";
    /** Free-form single-line answer note. Omitted → the note field is
     * cleared (rewritten to its empty form). */
    note?: string;
    /** Audit identity written to `answered_by` — the answering window's
     * claimId (host:pid). */
    answeredBy: string;
    /** Timestamp override for `answered_at`. Defaults to now at second
     * precision in the `...Z` form gates.py _check_iso explicitly accepts. */
    answeredAt?: string;
    /** Lock retry options (tests inject small values). */
    lockOpts?: LockOptions;
}
export type AnswerGateResult = {
    ok: true;
    gateFile: string;
    status: "approved" | "rejected";
} | {
    ok: false;
    error: string;
};
/** Render one YAML-subset scalar exactly like gates.py _render_scalar: plain
 * when unambiguous, single-quoted (with '' escaping) otherwise. */
export declare function renderScalar(value: string): string;
/** Answer one gate: take `.mw/gates.lock`, read the gate file, rewrite
 * status/answered_at/answered_by/note, and atomically replace the file
 * (tmp + rename). The read-modify-write happens under the lock so a
 * concurrent lock-respecting writer (the conductor creating gates, another
 * window answering) can never interleave with ours. */
export declare function answerGate(opts: AnswerGateOptions): Promise<AnswerGateResult>;
//# sourceMappingURL=gate-writer.d.ts.map