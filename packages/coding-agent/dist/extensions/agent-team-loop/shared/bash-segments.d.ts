/**
 * Quote-aware bash segment lexer (mw-worktree-junction-guard W-01, D-3).
 *
 * Extracted verbatim from implementation-gate.ts so the target-side write
 * gate and the worktree/junction guard share ONE lexer instead of keeping
 * two drifting copies (the IN-3 class of incident: a second copy that
 * diverges from the original). The accident command
 * `git worktree remove --force "$env:TEMP\qg-head"` has a non-literal
 * target: the resolution layer must first be able to lift that token out
 * unchanged (quotes stripped, interpolation NOT expanded), which is exactly
 * what this lexer does.
 *
 * Split a command into `;`/`&&`/`||`/`|`/`&`/paren-separated segments with
 * quote-aware, escape-aware words and redirect targets captured separately
 * from payload words. Heredoc bodies are skipped as payload text.
 */
export interface BashSegment {
    /** argv words: quotes stripped, backslash escapes resolved. */
    words: string[];
    /** File targets of `>` / `>>` / `n>` / `&>` redirections in this segment. */
    redirectTargets: string[];
}
/** Split a command into `;`/`&&`/`||`/`|`/`&`/paren-separated segments with
 * quote-aware, escape-aware words and redirect targets captured separately
 * from payload words. Quote content is always literal (a quoted `>` is
 * text, not a redirect — the false-positive lesson from P-002's bash
 * heuristic). Heredoc bodies are skipped entirely: they are payload text,
 * and scanning them would let a doc that quotes shell commands fire the
 * gate. */
export declare function parseBashSegments(command: string): BashSegment[];
//# sourceMappingURL=bash-segments.d.ts.map