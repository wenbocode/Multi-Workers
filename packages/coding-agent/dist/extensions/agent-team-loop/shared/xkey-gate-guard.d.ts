import type { ExtensionAPI } from "../../../core/extensions/types.ts";
/** Resolve the project root the gate directory is anchored against: the
 * MW_XKEY_GATE_ROOT override (tilde-expanded, resolved) wins, else the
 * process cwd (PM and worker windows both run with the project as cwd).
 * env injectable for tests. */
export declare function resolveXkeyGateRoot(env?: NodeJS.ProcessEnv): string;
/** The project's guarded directory: `<root>/.agenticdoc/_autopilot`. */
export declare function xkeyGuardedDir(root: string): string;
/** The pre-existing agent-writable xkey subtree:
 * `<root>/.agenticdoc/_autopilot/xkey` (xkey-repair-mechanism D-004/D-005). */
export declare function xkeySubtreeDir(root: string): string;
/** Does a write/edit tool path target the guarded `_autopilot` directory
 * (outside the xkey subtree)? Pure: resolves the path like the tools do
 * (cwd-relative, ~ expanded, folded) and also matches an absolute spelling
 * of any project's `_autopilot` directory, so a write aimed at a different
 * project is still refused. */
export declare function isXkeyGatePath(root: string, rawPath: string, cwd?: string): boolean;
export interface XkeyGateBashVerdict {
    /** True when the command must be blocked (guarded-dir reference + write
     * construct, or a redirect whose target is inside the guarded dir). */
    prohibited: boolean;
    /** Block reason (always present when prohibited=true). */
    reason?: string;
}
/** Decision for one bash tool command: fail-closed — a guarded `_autopilot`
 * reference (outside the xkey subtree) plus any write construct is denied,
 * redirect targets are checked separately (a redirect to an unprotected path
 * with a guarded-side read stays allowed). Text-level heuristic mirroring
 * protected-config.ts, not a sandbox. */
export declare function checkXkeyGateBashCommand(root: string, command: string): XkeyGateBashVerdict;
/** Worker-mode visibility: append one [XKEY_GATE] line to the task's
 * trace.log (dirname of PI_WORKER_TASK — the same file the PM watch reads
 * live) so a refused worker shows up immediately. Best-effort: a failure
 * here must never break the block itself. taskPathEnv injectable for tests. */
export declare function recordXkeyGateBlockTrace(toolName: string, detail: string, taskPathEnv?: string | undefined): void;
/** Register the tool_call autopilot block: write/edit paths and bash commands
 * are checked against `.agenticdoc/_autopilot/**` (minus the xkey subtree);
 * everything else (including all reads and the xkey evidence/ledger/tickets
 * tree) passes through untouched. Runs in every mode (PM, worker,
 * interactive). */
export declare function registerXkeyGateGuard(pi: ExtensionAPI): void;
/** The fixed sign-off file name (D-014: `content_match` cannot take a glob). */
export declare const DECISION_SIGNOFF_BASENAME = "sign-final.md";
/** The fixed sign-off fragment the done gate checks (project/key relative).
 *
 * The done gate only reads this `review/` landing spot, but the guard covers
 * BOTH landing spots (`<key>/evidence/sign-final.md` and
 * `<key>/evidence/review/sign-final.md`). write/edit/bash judge paths through
 * `isDecisionSignoffPath`, `worker_file` through
 * `isDecisionSignoffEvidenceTarget`, and both delegate to the SAME landing rule
 * (first `evidence` segment + tail `[]` or `["review"]`), so the four channels
 * refuse the same path and stay consistent. Keep them on that shared rule: a
 * `evidence/sign-final.md` suffix patch would re-refuse the legal
 * `evidence/research/evidence/sign-final.md` product (QG MAJOR-4 residual). */
export declare const DECISION_SIGNOFF_FRAGMENT = "evidence/review/sign-final.md";
/** The authorization table (project-relative). */
export declare const DECISION_POINTS_FRAGMENT = ".mw/decide-points.json";
/** Trace marker written into a worker's trace.log (mirrors `[XKEY_GATE]`). */
export declare const DECISION_SIGNOFF_TRACE_MARKER = "[DECISION_SIGNOFF]";
/** Does a write/edit tool path target the sign-off file or the table?
 * Pure: fragment match after normalizing backslashes (and case on win32), so
 * relative, `./`-prefixed and absolute spellings are all covered.
 *
 * Channel parity (see `DECISION_SIGNOFF_FRAGMENT`): the table and the `review/`
 * landing spot keep their fragment match, and every remaining `sign-final.md`
 * basename is delegated to the SAME landing rule `worker_file` uses — so
 * `<key>/evidence/sign-final.md` is refused here as well, while the deep
 * product `evidence/research/evidence/sign-final.md` still passes. */
export declare function isDecisionSignoffPath(rawPath: string): boolean;
/** Does a `worker_file` target name the decision sign-off file (the file
 * `mw decide sign` writes)?
 *
 * `worker_file` is the only write channel of a writeless role and its paths are
 * key-dir relative (`evidence/…`) or project-root relative
 * (`.agenticdoc/<key>/evidence/…`), with no basename restriction inside the
 * evidence face — so the fixed D-014 name has to be judged on the path, not on
 * the tool. Covers both landing spots the sign-off can be written to
 * (`<key>/evidence/sign-final.md` and `<key>/evidence/review/sign-final.md`)
 * and nothing else under `evidence/**`, so normal research/review products stay
 * writable. Case folding above (win32) also catches `SIGN-FINAL.MD`, which a
 * Win32 filesystem would land on the same file. */
export declare function isDecisionSignoffEvidenceTarget(rawPath: string): boolean;
export interface DecisionSignoffBashVerdict {
    /** True when the command must be blocked. */
    prohibited: boolean;
    /** Block reason (always present when prohibited=true). */
    reason?: string;
}
/** Decision for one bash tool command (fail-closed, text-level heuristic).
 *
 * Two independent triggers: (a) a reference to a guarded path plus any write
 * construct / redirect into it, and (b) the table-writing CLI itself
 * (`mw decide dp on|off|set|apply`) even without a literal path.
 * Read-only references (`cat sign-final.md`, `mw decide dp list|show|check`), the
 * sanctioned writer (`mw decide sign`, which names no guarded file and is absent
 * from the write-verb regex) and the registry->table one-way merge
 * (`mw decide dp refresh`, append-only) pass. */
export declare function checkDecisionSignoffBashCommand(command: string): DecisionSignoffBashVerdict;
/** Worker-mode visibility: append one `[DECISION_SIGNOFF]` line to the task's
 * trace.log (dirname of PI_WORKER_TASK — the file the PM watch reads live), so
 * a refused worker shows up immediately. Best-effort: a failure here must never
 * break the block itself; the env is injectable for tests. */
export declare function recordDecisionSignoffBlockTrace(toolName: string, detail: string, taskPathEnv?: string | undefined): void;
/** Register the tool_call sign-off block: write/edit paths and bash commands
 * aiming at `evidence/review/sign-final.md` or `.mw/decide-points.json` are
 * refused, as is a `worker_file` call whose target is the fixed sign-off name
 * under the key's evidence tree (writeless-role channel); every other call
 * (including reads, `decision-review-*.md` and the rest of `evidence/**`) passes
 * through untouched. Runs in every mode (PM, worker, interactive); registered
 * in `index.ts` right after `registerXkeyGateGuard`. */
export declare function registerDecisionSignoffGuard(pi: ExtensionAPI): void;
//# sourceMappingURL=xkey-gate-guard.d.ts.map