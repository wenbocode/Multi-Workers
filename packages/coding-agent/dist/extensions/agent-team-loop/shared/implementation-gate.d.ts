import type { ExtensionAPI } from "../../../core/extensions/types.ts";
/** Resolve the repo root the gate anchors code paths against: the
 * MW_IMPL_GATE_ROOT override (tilde-expanded, resolved) wins, else the
 * process cwd. env injectable for tests. */
export declare function resolveGateRoot(env?: NodeJS.ProcessEnv): string;
/** This window's claim id, in update_index.py's host:pid format. */
export declare function currentClaimId(): string;
/** Does a write/edit tool path target a code file (D-4)? Pure: resolves the
 * path like the tools do (cwd-relative, ~ expanded) and checks the
 * packages/ tree, the code extensions, and the node_modules/dist/.tmp
 * exclusions. */
export declare function isCodePath(rawPath: string, root?: string, cwd?: string): boolean;
/** Active-claim matcher (D-3a): does .agenticdoc/_index.parallel hold a row
 * with status active whose claim id equals the given host:pid
 * (case-insensitive)? Missing or unparsable file = no claim (fail-closed).
 * readIndexFile injectable for pure tests. */
export declare function hasActiveKeyClaim(root: string, claimId: string, readIndexFile?: (absPath: string) => string | undefined): boolean;
/** Fresh mini-spec finder (D-3c): the most recently modified
 * .agenticdoc/<key>/mini-spec.md whose mtime is within the freshness window
 * (future mtimes count as fresh — clock skew is not the agent's fault);
 * undefined when none exists. now injectable for pure tests. */
export declare function findFreshMiniSpec(root: string, now?: number, maxAgeMs?: number): string | undefined;
/** bash write-target check (D-1 layer 2): the write-structure target
 * arguments (redirect targets + tee/cp/mv/rm/sed -i operand sides) that
 * resolve to code paths, as the raw tokens appear in the command. Empty =
 * nothing gated. `cd` is tracked so relative targets resolve like the shell
 * would. Payload words are never scanned — only target sides. */
export declare function checkBashWriteTarget(command: string, root?: string, cwd?: string): string[];
export interface GateDecision {
    /** True when the tool call must be blocked. */
    blocked: boolean;
    /** Block reason (always present when blocked=true): why + the two
     * compliant paths. */
    reason?: string;
    /** Machine-readable decision basis: not-gated-tool | no-path |
     * no-command | not-a-code-path | no-code-path-target | claim |
     * worker-env | mini-spec:<path> | no-claim-no-mini. */
    basis: string;
    /** The gated code path (write/edit input path, or the first bash write
     * target hit), for the audit line. */
    target?: string;
}
/** The tool input shape the gate reads (write/edit `path`, bash `command`).
 * Structural so the typed tool events pass through without casts. */
export interface GateToolInput {
    path?: unknown;
    command?: unknown;
}
/** The gate decision for one tool call (D-3): not gated / not a code path →
 * pass; a code path passes on the three-condition OR (active claim for this
 * host:pid, worker env, fresh mini-spec); otherwise blocked with guidance.
 * env and cwd injectable for tests; root comes from env
 * (MW_IMPL_GATE_ROOT) or the process cwd. */
export declare function gateDecision(toolName: string, input: GateToolInput, env: NodeJS.ProcessEnv, cwd?: string): GateDecision;
/** Append one audit line to <root>/.agenticdoc/_impl_gate.log (D-6):
 * `[GATE] <ISO> <tag> tool=<t> target=<p> basis=<b>`. Append-only (never
 * read-modify-write — pitfall P-003), best-effort: a failure here must
 * never change the decision. */
export declare function recordImplGateAudit(tag: "blocked" | "mini-pass", toolName: string, target: string, basis: string, root?: string): void;
/** Register the tool_call gate (D-1/D-2): write/edit/bash calls are decided
 * by gateDecision; a block returns {block, reason} so the tool never runs;
 * every block and every mini fast-path pass appends one audit line. Runs in
 * every mode (PM, worker, interactive). */
export declare function registerImplementationGate(pi: ExtensionAPI): void;
//# sourceMappingURL=implementation-gate.d.ts.map