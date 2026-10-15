import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { type RagRuntime } from "../rag/tools.ts";
import { type WriteFace, type WriteFaceRejectCode } from "../shared/write-face.ts";
import type { TaskPhase } from "./phase-runner.ts";
/**
 * P-08 single source for the worker runtime's recognized vocabulary. This is
 * the SAME constant the tool-layer envelope judge consults
 * (`shared/dispatch-card.ts::DISPATCH_TYPE_VOCABULARY`), re-exported here so
 * the runtime table (`TOOL_ALLOWLISTS`, plus the internal `default`/`fallback`
 * buckets) and the gate can be locked together by
 * `test/suite/dispatch-recovery-terminal.test.ts` instead of drifting. It is
 * deliberately NOT `isRegisteredType`: that conductor fail-closed predicate
 * must keep matching the Python REGISTRY entry-for-entry (T-17 L0).
 */
export declare const WORKER_TYPE_VOCABULARY: readonly string[];
/** The worker runtime's registered type keys (the tool-table entries, minus the
 * internal `fallback` bucket). Exported only so
 * `test/suite/dispatch-recovery-terminal.test.ts` can lock the subset relation
 * against {@link WORKER_TYPE_VOCABULARY} (P-08 single source). */
export declare const REGISTERED_WORKER_TYPES: readonly string[];
export declare function toolsForType(taskType: string): string[];
/** `toolsForType` plus the narrow write channel for roles with no write/edit
 * tool (D-104/D-106). The allowlist table and `toolsForType` stay byte for
 * byte unchanged (Python parity lock, direct test imports); the writeless
 * extra lives only here. Write roles get the base array untouched, read-only
 * roles get a copy with `worker_file` appended. */
export declare function activeToolsForType(taskType: string): string[];
/** Is this a role whose tool set carries `bash` (contract C3)? */
export declare function isShellRole(taskType: string): boolean;
/** Is this a role with no write/edit tool (contract C3)? Such a role writes
 * only through the narrow `worker_file` channel, so bash is the one structural
 * hole left for the AC-005b write-surface guard. */
export declare function isWritelessRole(taskType: string): boolean;
/** Does this role carry a `write`/`edit` tool (D-115 rule 6)? The runtime
 * write-surface guard must cover these roles on the `write`/`edit` channel even
 * when they have no `bash` (`roadmap-writer` was unguarded before D-115). */
export declare function hasWriteTools(taskType: string): boolean;
/** Checkpoint self-assessment steer text, split by role (D-104/VC-004).
 * - `hasWriteTools === true`: the pre-change wording byte for byte — the
 *   agent appends its own CKPT line to progress.md with its write tool.
 * - `hasWriteTools === false`: never tells the agent to append to a file it
 *   cannot write. The machine evidence is already on disk (framework-written),
 *   and the self-assessment goes through the narrow tool or the reply.
 * `deliverAs` stays `followUp` for both branches (decided by the caller). */
export declare function checkpointSteerText(opts: {
    elapsedMs: number;
    budgetMs: number;
    progressPath: string;
    hasWriteTools: boolean;
    narrowTool: string;
}): string;
/** Default wall budget. The old 30m value killed healthy tasks (OverCode
 * cpr-004/005: actively working 28s/9s before the kill); 60m covers every
 * observed successful run (7–14m) with margin for generation-heavy tasks. */
export declare const DEFAULT_BUDGET_MS: number;
/** Default hang threshold: no activity (token deltas, tools, turns) for this
 * long while the task is unfinished means a dead API call. Conservative —
 * above the 7m legit single-generation observed on glm-5.3 (cpr-003); tighten
 * after confirming streaming deltas arrive on the timi route. */
export declare const DEFAULT_IDLE_MS: number;
/** Wall budget: task.md `timeout:` (minutes) > PI_WORKER_TIMEOUT_MS > default. */
export declare function resolveBudgetMs(timeoutMin: number | undefined, env: string | undefined): number;
/** Hang threshold from PI_WORKER_IDLE_MS (falling back to the default). */
export declare function resolveIdleMs(env: string | undefined): number;
/** Max silence allowed while a tool is in flight, before the in-flight branch
 * of the idle watchdog kills. Root cause (measured 2026-09-26, T-04/AC-005):
 * 22/24 idle kills died while a bash call was in flight with zero
 * `tool_execution_update` — bash updates are output-driven (core/tools/bash.ts),
 * so a long command that prints nothing looked like a hung worker. A tool that
 * is still running legitimately owns the activity clock, but only up to a
 * bound: a genuinely hung tool must still die (VC-006). 30m mirrors the
 * design's floor (D-016) and sits inside the 60m default wall budget, which
 * remains the outer guard. Deliberately a code constant: T-04 forbids a new
 * config key, so this is NOT wired through `_autopilot/config.json`.
 *
 * Deliberately does not change `DEFAULT_IDLE_MS` or the PI_WORKER_IDLE_MS
 * semantics: the threshold was never the root cause. */
export declare const DEFAULT_TOOL_IDLE_MS: number;
/** Effective in-flight tool-idle bound: the configured raw idle threshold
 * (lower bound, so a tightened PI_WORKER_IDLE_MS also tightens this) vs the
 * 30m floor. */
export declare function resolveToolIdleMs(idleMs: number): number;
/** First convergence-checkpoint time: the 30m anchor, scaled down
 * proportionally for small budgets so smoke runs exercise the whole path. */
export declare function checkpointAnchorMs(budgetMs: number): number;
/** Deadline-steer time: budget minus min(5m, budget/4). */
export declare function steerAtMs(budgetMs: number): number;
/** T-04/AC-009: freshness floor for a landing — one minute, so a small smoke
 * budget (anchor 60s) still has an exercisable window. */
export declare const LAND_FRESH_FLOOR_MS = 60000;
/** T-04/AC-009: how recent the newest landing must be to count as "fresh"
 * (a writeless run that is still producing). `anchor/3` floored at 1m: the
 * default anchor (30m) yields 10m, exactly the checkpoint refresh cadence. */
export declare function landFreshMs(anchorMs: number): number;
export interface ConvergenceSignals {
    elapsedMs: number;
    /** Checkpoint anchor (min(30m, budget/2)) — the point past which zero
     * output stops being "warming up" and starts being divergence. */
    anchorMs: number;
    writes: number;
    phasesTotal: number;
    phasesDone: number;
    /** Highest per-target repeat count for reads. */
    repeatTop: number;
    /** T-04/AC-009 writeless landing signals, sourced from `parseWriteFileEvents`
     * (the change ledger the settle judgement reads — never `[TOOL] worker_file`
     * counts). Undefined for write roles ⇒ the legacy rule below applies byte for
     * byte; `landed: 0` is a signal, not an absence of one. */
    landed?: number;
    /** Age of the newest landing on disk (ms). Undefined = no surviving target. */
    lastLandingAgeMs?: number;
    /** A non-empty product exists on disk (channel-independent ground truth). */
    artifactPresent?: boolean;
    /** `progress.md` carries the role's own completion record. */
    progressDone?: boolean;
}
/** Machine divergence heuristic (AC-004, advisory only — the PM with the
 * fullest context judges and decides):
 * - high: past the anchor with ZERO writes — pure exploration, the cpr-007
 *   pattern (22 minutes of reads, generation never got time to land).
 * - mid: phase framework present but nothing completed past the anchor, or
 *   the same target read ≥4 times (spinning).
 * - low: writes advancing — implementation underway.
 *
 * T-04/AC-009: when the caller supplies landing signals (`landed !== undefined`,
 * writeless roles), the counts `writes`/`uniq_targets` stop being the criterion
 * (they are structurally 0 for those roles) and the ledger + disk facts decide:
 * - W2a: a non-empty product on disk ⇒ low (strongest convergence evidence;
 *   outranks a missed ledger event).
 * - W1: nothing landed at all past the anchor ⇒ high (unchanged intent).
 * - W2b: a fresh landing plus the role's own `converging=yes` note ⇒ low.
 * - W3/W4: landed-but-stale (or nothing before the anchor) — only read spin or
 *   stalled phases are mid, everything else is low. */
export declare function computeRisk(s: ConvergenceSignals): "low" | "mid" | "high";
/** T-04/AC-009: what the writeless checkpoint actually observes. */
export interface LandingSignals {
    /** Distinct `[WRITE_FILE]` targets (parseWriteFileEvents dedup). */
    landed: number;
    /** Age of the newest surviving landing; undefined = no target on disk. */
    lastLandingAgeMs: number | undefined;
    /** A non-empty product exists on disk. */
    artifactPresent: boolean;
    /** `progress.md` carries the role's own completion record. */
    progressDone: boolean;
}
/** T-04/AC-009: landing signals for a writeless run, from the SAME ledger the
 * settle judgement reads. `parseWriteFileEvents` (not the `[TOOL] worker_file`
 * lines, not a second extractor) supplies the target set, so the two views
 * cannot diverge; disk truth (non-empty artifact, surviving targets, fresh
 * evidence) is the fallback when the ledger missed an event. Read-only. */
export declare function collectLandingSignals(opts: {
    taskDir: string;
    traceText: string;
    progressText: string;
    startedAtMs: number;
    nowMs: number;
}): LandingSignals;
interface TaskMeta {
    type: string;
    /** task.md `phase:` header (the phase axis of `required = role.require OR
     * phase.require`, T-14). Distinct from the `phases` framework array below. */
    phase?: string;
    phases?: TaskPhase[];
    taskKey: string;
    agenticdocRoot: string;
    /** Dispatch origin marker (D-104): "conductor" on autopilot dispatches,
     * undefined on manual/legacy tasks (which keep the fallback path, GC-8). */
    origin?: string;
    /** task.md `images:` header (T-09/AC-011): `true` only when the dispatch
     * declared `images: yes` (the task needs image reads). An undeclared header
     * stays `undefined` and changes nothing (zero branches). */
    images?: boolean;
    /** TRUE .agenticdoc root — task.md four levels up
     * (.agenticdoc/{owner}/workers/{taskKey}/task.md → .agenticdoc), where
     * goal.md lives (D-116). Distinct from `agenticdocRoot`, which is the
     * owner's workers/ dir and stays the outputDir base (contract unchanged). */
    trueAgenticdocRoot: string;
    /** Wall budget in minutes from the task.md `timeout:` header. */
    timeoutMin?: number;
    /** read_scope entries (D-106), project-root relative. Present → read
     * containment enabled; absent → zero interception (AC-012 red line). */
    readScope?: string[];
    /** deny_globs entries (mw-dual-workspace AC-006), minimatch dual-basis.
     * Present → deny firewall active even without read_scope (deny-only). */
    denyGlobs?: string[];
    /** write_scope entries (contract C1/T-03), project-root relative. Present →
     * the AC-005b bash write surface is narrowed to the intersection with the
     * default (own taskDir + `<key>/evidence/**`); absent → default surface.
     * D-115: legacy carrier — for writeless roles it stays the only declared
     * face (byte for byte); for writable roles it is a fallback when the
     * authoritative `write_face:` head is absent, and an additional narrowing
     * constraint when both carriers are present. */
    writeScope?: string[];
    /** D-115 authoritative allow carrier: normalized `write_face:` entries
     * (project-root relative, comma/block-list form both normalized). Undefined
     * when the head is absent, `-` (undeclared) or refused (`writeFaceRejected`).
     * Writable roles re-parse these against the worker cwd, so the runtime face
     * keeps the shared operator's semantics (D-009/AC-007). */
    writeFaceEntries?: string[];
    /** A `write_face:` head that is present but refused (fail-closed). Only the
     * writable role path consults this: no target outside the own sandbox is
     * allowed by the authoritative carrier. */
    writeFaceRejected?: WriteFaceRejectCode;
    /** l2_read_file_cap frontmatter (positive int), when present. */
    readFileCap?: number;
    /** l2_read_byte_cap frontmatter (positive int), when present. */
    readByteCap?: number;
    /** task.md `rag_chat_budget:` header (positive int), when present. */
    ragChatBudget?: number;
    /** task.md `rag_time_budget_s:` header (positive int seconds), when present. */
    ragTimeBudgetS?: number;
    /** AC-007/T-07 escape hatch: task.md `allow_foreign_write: true` (the
     * audit-visible declaration T-02 records, also set by the
     * `--allow-foreign-write` dispatch flag). `true` is the only value that
     * opens the hatch; missing/false/any other value stays fail-closed. */
    allowForeignWrite?: boolean;
    /** AC-010/T-12: structure of the C2 contract markers read back from this
     * task book (see {@link writeSurfaceMarkerState}). */
    writeSurfaceMarker: WriteSurfaceMarkerState;
}
/** Structure of the C2 write-surface contract markers in a task book
 * (AC-010/T-12). The producer is `pm/ui-bridge.ts::applyWriteSurfaceContract`
 * (contract section injected for writeless roles); until now nothing in the
 * execution path read the paired markers back, so the only writer-side
 * guarantee was that idempotency regex — a half-removed or duplicated pair
 * would survive into the task book unobserved. `parseTaskMd` records the
 * structure here and `workerModeActivate` consumes it: `"malformed"` appends
 * one `[WRITE_SURFACE]` audit line. `"absent"` is the normal state for
 * manual/legacy task books (the section is opt-in and conductor-rendered task
 * books never carry it), so absence is deliberately not flagged. Only markers
 * that occupy a whole line count: the section is line-joined, and an inline
 * mention in prose (a task book quoting the marker) is not a section.
 *
 * D-115 rule 5: this is a structure MARKER only — it never participates in the
 * allow decision (the authoritative allow carrier is `write_face:`; `write_scope:`
 * is the legacy carrier, all other `write_scope`-named fields are a DIFFERENT
 * semantic). */
export type WriteSurfaceMarkerState = "absent" | "ok" | "malformed";
export declare function writeSurfaceMarkerState(content: string): WriteSurfaceMarkerState;
export declare function parseTaskMd(taskPath: string): TaskMeta;
/** One extracted write target. */
export interface BashWriteCandidate {
    /** Raw path exactly as written in the command. */
    target: string;
    /** Which write pattern produced it (audit/debug). */
    pattern: string;
    /** False when the target word carries a live shell expansion (`$`, backtick,
     * unquoted leading `~`, glob, brace). The verdict layer only receives the raw
     * string (four quoting forms are byte-identical there), so the flag is
     * computed in the lexer and carried through. */
    verbatim: boolean;
}
/** Block rule identifiers, mirroring read-scope's rule tokens. `allow-unknown`
 * is the non-blocking token for a target that is not statically determinable
 * (see `checkBashWriteScopeTarget`), not a block reason. */
export type BashWriteScopeRule = "deny" | "scope" | "write-scope" | "allow-unknown";
/** Enforcement config for one shell worker's runtime write surface. */
export interface BashWriteScopeConfig {
    /** Worker cwd = project root (launcher guarantee). */
    projectRoot: string;
    /** Own task dir (`.agenticdoc/<key>/workers/<taskKey>`), absolute. */
    taskDir: string;
    /** Own key dir (`.agenticdoc/<key>`), absolute. */
    keyDir: string;
    /** TRUE `.agenticdoc` root (`.agenticdoc`), absolute. */
    trueRoot: string;
    /** `write_scope:` entries (project-root relative): undefined = header
     * absent (the default surface), [] = present-but-blank (fail-closed). */
    writeScope: string[] | undefined;
    /** Role class (D-007 / spec risk 10). `"writable"` = the role carries a
     * `write`/`edit` tool (its normal work surface is the repo, including
     * `packages/**`); `"writeless"` = it only reaches bash/`worker_file`. The
     * two need different default and deny faces: the writeless face is the own
     * taskDir + `<key>/evidence/**` with `packages/**` denied, which would
     * false-block every legitimate coding write. Absent defaults to the
     * historical writeless face, so pure-function callers (and the `research`
     * path) stay byte-identical. */
    roleClass?: WriteSurfaceRoleClass;
    /** D-115 authoritative `write_face:` face, parsed with the shared operator
     * (D-009/AC-007) against the worker cwd. Present only for writable roles
     * whose task.md declares a parseable head. `undefined` + `writeFaceRejected`
     * = the head was present but refused (fail-closed: nothing outside the own
     * sandbox is allowed by this carrier). Writeless roles never receive it, so
     * their `write_scope:` behavior stays byte for byte (D-115 rule 2). */
    writeFace?: WriteFace;
    /** A `write_face:` head that was present but refused by the shared parser
     * (D-115 fail-closed). */
    writeFaceRejected?: boolean;
}
/** Write-surface role classes (D-007). */
export type WriteSurfaceRoleClass = "writeless" | "writable";
/** Verdict for one extracted target. */
export interface BashWriteScopeVerdict {
    allowed: boolean;
    /** Rule that fired on a block. */
    rule?: BashWriteScopeRule;
    /** Short machine token for the trace line (e.g. `denied:pm-state.md`). */
    detail?: string;
    /** Human block reason (carries the allowed dirs on every rule). */
    reason?: string;
    /** The raw target the verdict was produced for. */
    target?: string;
    /** Set on an `allow-unknown` verdict whose basename still names a deny-list
     * artifact (`pm-state.md`, `_workers*`) — the residual-risk marker (AC-007). */
    risk?: "deny-basename";
}
interface ShellToken {
    text: string;
    /** True for an unquoted control-operator token (`>`, `>>`, `|`, ...). */
    operator: boolean;
    /** False once the word contains a live expansion (see the tokenizer). */
    verbatim: boolean;
}
/** Split a shell command into quote-aware tokens; control operators become
 * their own tokens, so `echo "a > b"` never yields a redirect. */
export declare function tokenizeShellCommand(command: string): ShellToken[];
/** AC-017(a) / design §5.1: **strip data regions before the lexer**. A
 * PowerShell here-string body and a POSIX heredoc body are DATA: a literal `>`
 * or `->` inside them must never become a redirect operator, and a quoted
 * fragment inside them must never become a write target. The stripping is a
 * separate, independently testable stage (called first by
 * `extractBashWriteCandidates`), not a regex patch on the extractor's targets. */
export declare function stripDataRegions(command: string): string;
/** Extract the KNOWN write targets of a bash command. An empty result means
 * "not a recognized write" — the caller must allow it (P1, DD-03). */
export declare function extractBashWriteCandidates(command: string): BashWriteCandidate[];
/** AC-017 / design §5.2-5.3: the ledger-facing split of one command's
 * extraction. `recorded` are targets from a write verb position that resolved
 * to a literal (verbatim) path; `unresolved` are write-verb targets that stayed
 * dynamic and are stated as `[WRITE_UNRESOLVED]` instead of being guessed. The
 * non-file targets (`.`, `..`, `/`) are dropped here — the guard still consumes
 * them for its scope judgement, but they are not change-history entries. */
export interface LedgerWriteClassification {
    recorded: string[];
    unresolved: Array<{
        pattern: string;
        target: string;
    }>;
}
export declare function classifyLedgerTargets(command: string): LedgerWriteClassification;
/** The write-surface verdict for one extracted target: a non-verbatim target is
 * not statically determinable (`allow-unknown`, fail-open); otherwise the deny
 * list comes first (absolute priority), then the role-classified default face,
 * then the declared allow carriers (D-115).
 *
 * - writeless (research): default face = own taskDir + `<key>/evidence/**`, and
 *   a declared `write_scope:` intersects it (historical behavior, byte for
 *   byte). The authoritative `write_face:` carrier is never consulted here.
 * - writable (coding/repair/phase-writer/vision/fallback/roadmap-writer):
 *   default face = the working tree, because `packages/**` is the role's work
 *   surface (D-007). The declared face is the authoritative `write_face:` when
 *   present, the legacy `write_scope:` when it is absent, and their
 *   INTERSECTION when both are present (fail-closed: the legacy carrier can
 *   only narrow). The own taskDir/evidence stay writable either way.
 *
 * T-10: the ALLOW face (own taskDir + own-key `<key>/evidence/**`) is resolved
 * by `shared/write-surface.ts::resolveOwnWriteTarget` — the same single source
 * the dispatch predicate and `worker_file` use — so this guard owns no second
 * path-domain/`write_scope` implementation. The SHELL basis is `project-root`:
 * a bash target is a cwd-resolved literal, so a keyDir-relative `evidence/x.md`
 * is refused (DR1 ruling, locked by tests — a designed difference, not a bug).
 * The deny table stays the role-classified shell table (only it makes
 * `packages/**` writeless-only).
 *
 * `toolLabel` only phrases the block reason (`bash` keeps the historical
 * "bash write" wording for the research audit line). */
export declare function checkBashWriteScopeTarget(config: BashWriteScopeConfig, rawTarget: string, verbatim: boolean, toolLabel?: "bash" | "write" | "edit"): BashWriteScopeVerdict;
/** Structured evidence emitted before any idle kill (VC-004/AC-005). Every
 * field is part of the contract: which tool was in flight (or `none`), how long
 * it had been running, the threshold that produced the verdict, and the last
 * source that refreshed the activity clock. */
export interface IdleKillEvidence {
    /** In-flight tool name, or "none" when the worker was tool-idle. */
    toolInFlight: string;
    /** Seconds the in-flight tool has been running; null when none. */
    toolRunS: number | null;
    /** Seconds since the in-flight tool's last activity; null when none. */
    toolIdleS: number | null;
    /** Seconds since ANY worker activity (the raw idle clock). */
    silenceS: number;
    /** The threshold used for this verdict, in seconds. */
    thresholdS: number;
    /** Which clock produced the verdict. */
    thresholdKind: "idle" | "tool_idle";
    /** Last source that refreshed the activity clock. */
    lastActivity: string;
}
/** Append one machine `[IDLE_KILL]` line to trace.log. Returns false when the
 * line could not be written — the caller must then NOT kill ("no evidence ->
 * no kill"); the wall watchdog stays the outer bound, so a hung worker is
 * still reaped even if the evidence write keeps failing. */
export declare function appendIdleKillEvidence(taskKey: string, agenticdocRoot: string, evidence: IdleKillEvidence): boolean;
/** task.md `phase:` value, or the literal `unknown` — never a guess. */
export declare function evidencePhase(phase: string | undefined): string;
export interface RagRequiredCheck {
    config: RagRuntime["config"];
    taskType: string;
    /** task.md `phase:` value (already normalized via `evidencePhase`). */
    phase: string;
    /** The worker's own deliverable text (final assistant reply). */
    outputText: string;
    /** Owner key dir (`.agenticdoc/<key>`) — the research-doc location. */
    keyDir: string;
    /** Worker task dir (trace.log / output.md live here). */
    taskDir: string;
}
/**
 * VC-014 (AC-010) worker face: for a *required* role/phase, emit the shared
 * `rag-required-missing` evidence line and mark output.md when no verifiable
 * citation was produced. Returns the emitted line, or null on a no-op (not
 * required, or a citation exists). Zero writes when not required.
 *
 * "Verifiable citation" mirrors T-10's audit: a parseable D-004 citation in
 * the worker's own deliverable, or — for the research role, whose citations
 * live in `<key>/rag/*.md` — a citation in that key's research doc. The
 * research-doc report's `ok` is the used-flag and the line is routed through
 * `researchDocEvidence`, so there is exactly one line builder.
 */
export declare function emitRagRequiredMissing(check: RagRequiredCheck): string | null;
export declare function workerModeActivate(pi: ExtensionAPI): Promise<void>;
export {};
//# sourceMappingURL=worker-mode.d.ts.map