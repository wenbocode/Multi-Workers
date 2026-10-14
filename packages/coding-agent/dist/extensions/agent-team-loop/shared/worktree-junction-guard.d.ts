import type { ExtensionAPI } from "../../../core/extensions/types.ts";
/**
 * Worktree junction guard (mw-worktree-junction-guard G1, AC-001/002/003).
 *
 * Why: `git worktree remove --force <path>` walks THROUGH reparse points
 * (Windows junctions) inside the worktree and recursively deletes the link
 * TARGET. The 2026-10-09 accident ran
 * `cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head"`
 * and removed 3,456 tracked files from the shared tree (8 package trees +
 * packages/tui) plus other sessions' uncommitted work, because the worktree
 * contained a `node_modules` junction pointing back at the real tree. The
 * target was not even a literal path: it was an environment interpolation.
 *
 * This guard is the first mechanical guarantee, not a sandbox (same class as
 * shared/protected-config.ts and shared/implementation-gate.ts): before a
 * `git worktree remove|rm` bash call executes it resolves the operand,
 * scans the target tree, and blocks when it cannot prove the tree is free of
 * reparse points. The refusal text carries the copyable replacement command
 * `mw worktree rm "<worktree>"` (G2 six-step transaction).
 *
 * Boundaries (design D-4 + decision D-11, extended by D-19): covers
 * `git worktree remove|rm` (incl. `--force`, `-C`, and command-internal
 * location bases `cd`/`Set-Location`/`pushd`/`sl`/`chdir`, incl. cmd `cd /d`)
 * and the penetrating forms `<path>/`, `<path>/*`, `<path>\*` for `rm` (incl.
 * `-r`/`-rf`/`-f`) plus the PowerShell aliases `Remove-Item`/`ri`/`del`/
 * `erase`/`rd`/`rmdir` (D-19: pi pins its shell to PowerShell, so those
 * spellings have identical reach). A separator-free, glob-free operand stays
 * out of scope: `rm -rf <link>`, `rmdir /S`, and `robocopy /MIR` are NOT
 * covered, and `checkBashWriteTarget` / `WRITE_VERBS` are deliberately not
 * extended. A penetrating hit on a
 * registered worktree keeps the §4.3 text (`mw worktree rm "<path>"`); any
 * other target gets the second text with the per-link
 * `cmd /c rmdir "<link>"` prescription (AC-002 extension, D-11).
 *
 * Parsing is structural (shared/bash-segments.ts `parseBashSegments`), never
 * a word-list match — the `dd` false positive in protected-config's
 * WRITE_VERB_RE is the counter-example this guard must not repeat.
 *
 * Registered in EVERY mode (index.ts, next to the other guards) so a worker
 * window is covered too.
 *
 * AC-014 (D-13, audit N-06): the guard also hangs off the `user_bash` event,
 * the channel used by the TUI `!`/`!!` prefix and the RPC `bash` command. That
 * path never reaches the bash tool and never fires `tool_call`, so without
 * this hook `! git worktree remove --force <worktree-with-a-junction>` is the
 * exact accident shape with no guard in front of it. The handler reuses the
 * same `decideWorktreeRemove` verdict and text; returning `result` is the
 * documented short-circuit (the caller uses it INSTEAD of executing — see
 * `extensionRunner.emitUserBash` consumers in modes/interactive and modes/rpc).
 */
/** basis values are a fixed vocabulary (design §3.2). */
export interface WorktreeGuardVerdict {
    block: boolean;
    /** AC-002: link path + target + copyable `mw worktree rm "<path>"`. */
    reason?: string;
    /** Resolved absolute worktree path (audit). */
    target?: string;
    /** Absolute paths of the reparse points found in the target tree. */
    hits: string[];
    /** resolved | unresolved:<var> | glob | bare-name-ambiguous |
     * reparse-point | delete-penetration | target-absent |
     * scan-error:<code> | not-remove */
    basis: string;
}
/** Decide whether a bash command is a dangerous `git worktree remove`.
 * Pure apart from reading the filesystem and, for bare names, asking git for
 * the worktree registry. `env` is the variable table for interpolation. */
export declare function decideWorktreeRemove(command: string, cwd: string, env: NodeJS.ProcessEnv): WorktreeGuardVerdict;
/**
 * Register the tool_call worktree block: only bash `git worktree remove|rm`
 * commands are inspected; every other tool call passes through untouched.
 * Runs in every mode (PM, worker, interactive).
 *
 * AC-014 adds the `user_bash` face on the same registration function: the TUI
 * `!`/`!!` prefix and the RPC `bash` command go through
 * `ExtensionRunner.emitUserBash` (core/extensions/runner.ts), never through
 * the bash tool, so `tool_call` alone leaves that channel unguarded. Both
 * hooks share `decideWorktreeRemove` and the `[WORKTREE_GUARD]` trace; the
 * only difference is the shape of the refusal (tool_call: `{block, reason}`;
 * user_bash: `{result}` = full replacement, i.e. the command does not run).
 *
 * `pi.on` writes the handler into a `Map<string, handler[]>` with no event
 * allow-list (core/extensions/loader.ts `on()`), so the `user_bash`
 * registration cannot break extension loading even on an older pi build that
 * ignores the event; the try/catch fallback is therefore unnecessary.
 */
export declare function registerWorktreeJunctionGuard(pi: ExtensionAPI): void;
//# sourceMappingURL=worktree-junction-guard.d.ts.map