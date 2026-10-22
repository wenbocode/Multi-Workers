import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { type DecideRunner } from "../pm/triage-client.ts";
import { type RagRuntime } from "../rag/tools.ts";
import { type Claim } from "../shared/dispatch-card.ts";
import { type WriteFace, type WriteFaceRejectCode } from "../shared/write-face.ts";
import { type VerdictTable } from "./output-sections.ts";
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
export declare const DECIDE_PREPARE_TYPE = "decide_prepare";
/** Card item carrying the send authority (`yes` = the worker may send). */
export declare const DECISION_ALLOW_SEND_ITEM = "allow-send";
/** The one directory a decision book may be written to. */
export declare const DECISION_BOOK_SUBDIR = "evidence/books";
/** The fixed decision-worker prompt (card requirement 2). */
export declare const DECISION_TYPE_PROMPT: string;
/** Does the task authorize the worker itself to send the book?
 *
 * Only an explicit `allow-send: yes` line does (`- allow-send: yes` or
 * `allow-send: yes`); every other shape — absent, `no`, garbage — is the
 * closed state (W8 requirement 4: the default is `no`). */
export declare function decisionAllowsSend(taskContent: string): boolean;
/** Block reason for one decision-worker bash command, or `null` when allowed.
 *
 * Splits on the shell control operators (`&&`, `||`, `;`, `|`, newline) so a
 * chained write (`rg x && rm -rf y`) cannot hide behind an allowed prefix, and
 * refuses redirections/known mutators outright (P1: for this role a false
 * block costs one retry, a miss writes outside the books dir).
 *
 * `mw decide book new` is allowed on top of the card's read-only list because
 * the prompt's FIRST step is that scaffold; its `--out` must stay inside
 * `evidence/books/**` and the no-`--out` shape only prints to stdout. */
export declare function decisionBashBlockReason(command: string, allowSend: boolean): string | null;
/** Is this `worker_file` target inside the decision book directory?
 *
 * Accepts both spellings the tool documents: `evidence/books/<f>` (taskDir
 * relative) and `.agenticdoc/<key>/evidence/books/<f>`. Everything else — the
 * broader `<key>/evidence/**` face, `progress.md`, a source file — is refused
 * (W8 requirement 3: the write face narrows to the books dir). */
export declare function decisionWorkerFilePathAllowed(file: string): boolean;
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
    /** T-04b/D-002: the `<!-- mw-claims: v1 -->` block T-02 injects into task.md
     * (the settle-time claim contract; the mutable card file is never re-read).
     * `undefined` when the block is absent — the zero-branch legacy path (AC-007:
     * a claims-free book keeps `finishSuccess` byte-identical). Present-but-empty
     * stays `[]` on purpose: the block exists, so the run DOES carry a claim
     * contract whose claims all failed to parse (the count is then 0, never a
     * silent "no claims"). */
    claims?: Claim[];
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
/** Share of `unverified` rows above which the run did not settle its claim
 * contract (AC-008 ②). `>` — the boundary itself passes. */
export declare const CLAIM_UNVERIFIED_MAX_DEFAULT = 0.4;
/** ... except for the review role, which legitimately hits the no-bash wall
 * (RQ-3 §4 B-2: all 46 corpus review units only carry read/find/grep/ls). */
export declare const CLAIM_UNVERIFIED_MAX_REVIEW = 0.6;
/** One `run.json` `claims` subobject (design §3.4). `total` is the card's claim
 * count; the three verdict counters are the rows that settled against it; and
 * `tokens: null` is the contract's "not attributable" value (AC-005b: the
 * worker process cannot split LLM usage per claim — the Python side joins the
 * session ledger, and a made-up number would corrupt `tokens_per_closed_claim`).
 * T-05's `readRunClaims` reads exactly these six keys (absent key = no claims). */
export interface ClaimCounts {
    total: number;
    closed: number;
    partial: number;
    unverified: number;
    /** `[FLOW] tool_call` read-class count (D-008: only allowed calls). */
    fetches: number;
    tokens: number | null;
}
/** Per-run claim counters: the card's claim set against the product's `## 断言裁决`
 * table (first row per id wins, same as `claimCoverage`). A claims-free run has
 * no counters to write at all — the caller guards on `meta.claims === undefined`
 * rather than fabricating zeroes (T-05: an absent key means "not measured"). */
export declare function claimCounts(claims: Claim[], table: VerdictTable, fetches: number): ClaimCounts;
/** The `[CLAIMS]` trace row (design D-004): a line of its own, NEVER folded into
 * `[END]` — both sides of `[END]` are anchored regexes (`shared/heartbeat.ts`,
 * `packages/multi-workers/mw_common.py`). Field order is frozen here and by
 * `usage.py::_CLAIMS_LINE_RE` (T-05). */
export declare function formatClaimsTraceLine(counts: ClaimCounts, now?: Date): string;
/** Append the `[CLAIMS]` row once, lifecycle style (no `[FLOW]` prefix — the line
 * starts with its own anchor). Best-effort like every other trace anchor: a
 * diagnostic append must never change the terminal verdict. */
export declare function appendClaimsTraceLine(taskKey: string, agenticdocRoot: string, counts: ClaimCounts): void;
/** The claim ids named by a gap list (`claim:<id>:<criterion>`), de-duplicated in
 * emission order. Tokens without an id (`claims:missing-table`,
 * `claims:unverified-ratio:…`) are skipped: their own name is the diagnostic. */
export declare function claimGapIds(gaps: string[]): string[];
/**
 * The three AC-008 settlement criteria that need inputs only the worker layer
 * holds (the role, the run clock, the trace read count) — `claimCoverage`'s
 * per-claim criteria stay in `worker/output-sections.ts` (frozen, T-04a):
 *
 *   ② `claims:unverified-ratio:<u>/<n>><limit>%`  too many un-settled claims
 *      (40%, or 60% for the review role) ⇒ the run must not read as PASS.
 *   ③ `claims:fetches:<sum>><cap>`               Σ取数 above `min(Σ预算, 30)`.
 *      `claims:fetches:<sum>>trace:<n>`           Σ取数 above the trace's own
 *                                                read-class `tool_call` count
 *                                                (B-6: an upper bound — you
 *                                                cannot honestly report more
 *                                                fetches than you performed).
 *   ⑥ `claim:<id>:carried-from`                 a closed/partial row whose every
 *      cited file predates this run's task.md and carries no `carried-from:`:
 *      the previous round's verdict was copied without saying so.
 *
 * Never throws. `claims.length === 0` (no contract) returns `[]`, and an unknown
 * `taskMtimeMs` skips ⑥ rather than guessing a clock.
 */
export declare function claimSettlementGaps(opts: {
    claims: Claim[];
    table: VerdictTable;
    /** Task type whose role sets the ② threshold (`roleForTaskType`). */
    role: string;
    /** `[FLOW] tool_call` read-class count of this run (D-008). */
    traceReads: number;
    /** mtime of this run's task.md — the clock a "fresh" citation must beat. */
    taskMtimeMs?: number;
    /** Root the evidence paths resolve against (launcher cwd in production). */
    projectDir?: string;
}): string[];
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
    /** True when the most recent assistant boundary was an error (design D4): a
     * silent worker whose last message failed is a model-availability suspect,
     * not a generic hang. */
    lastModelError: boolean;
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
export interface WorkerModeOptions {
    /** Test seam for the dp3 decision service (production uses the triage
     * client's `runDecideMw`, which reuses `findMwPy()` + `PYTHON_EXE`). */
    dp3Runner?: DecideRunner;
}
export declare function workerModeActivate(pi: ExtensionAPI, options?: WorkerModeOptions): Promise<void>;
/** `PI_WORKER_TRIED_MODELS` csv -> ordered, deduped model labels
 * (`provider/model`). The launcher seeds it with the main model and every
 * fallback it moved through, so the list is the audit chain the Exit Reason
 * reports. */
export declare function parseTriedModels(env: string | undefined): string[];
/** Model-error text budget (design §4): every error string on trace.log and in
 * `## Exit Reason` is collapsed to one line and capped at 200 chars, so a
 * multi-line provider dump can never break the line-parsable trace or the PM
 * readback. */
export declare const MODEL_ERR_TEXT_MAX = 200;
/** Collapse whitespace to one line and cap at {@link MODEL_ERR_TEXT_MAX}
 * (ellipsis included in the cap). */
export declare function truncateModelErrText(text: string): string;
/** Model-error view of one boundary event's message (design D4). `undefined`
 * when the message is not an assistant message: the activity clock must still
 * be fed, and the most recent assistant fact is left unchanged. For an
 * assistant message, `error` says whether that boundary was an error — which
 * suppresses `touch` and arms the model-error state machine. */
export interface AssistantBoundaryView {
    error: boolean;
    errorMessage?: string;
}
export declare function assistantBoundaryInfo(message: unknown): AssistantBoundaryView | undefined;
/** One entry of the tried-model audit chain (AC-004). */
export interface ModelErrChainEntry {
    model: string;
    runs: number;
}
/** AC-004 exit reason: `model unavailable: tried=<m>(<n>),... last=<err>`. The
 * PM reads the tried chain and the final error text with zero text parsing. */
export declare function formatModelUnavailableReason(entries: readonly ModelErrChainEntry[], lastError: string): string;
/** Marker line written into `steer-dp2.md` after a delivered injection. */
export declare const DP2_CONSUMED_MARKER = "[dp2-consumed";
/** True when the request file already carries a consumption marker (any run). */
export declare function hasDp2ConsumedMarker(content: string): boolean;
/** The injected text of one steer request: the machine request header is a
 * transport artifact, not a directive, so it is dropped; the directive keeps the
 * `[mw dp2-narrow]` attribution prefix (added only when it is not there yet).
 * `undefined` when nothing is left to inject (empty / header-only file) — an
 * empty steer is not a steer. */
export declare function formatDp2NarrowSteer(content: string): string | undefined;
/** Atomically append the consumption marker to the request file. The file stays
 * the single source of truth for "this steer was already injected", so the
 * append is a tmp+rename replacement, never a partial write. */
export declare function appendDp2ConsumedMarker(steerPath: string, content: string, runId: string): boolean;
/** Registry id of the worker-clarification decision point (`decision_points.py`
 * `DP_REGISTRY`; AC-011: the TS side only holds ids, never a second registry). */
export declare const DP3_ID = "dp3-worker-clarify";
/** `questions_version` of `DP3_ID` (`decision_points._questions_version`). */
export declare const DP3_QUESTIONS_VERSION = "q-fcbd3847";
/** Fixed attribution prefix of an injected dp3 answer (DS-7 guardrail). */
export declare const DP3_ANSWER_PREFIX = "[mw dp3-answer]";
/** Deterministic-reuse threshold of the local matcher (design Q2.2). Built-in
 * baseline only: the effective value is derived from the resolved
 * `min_confidence` by {@link dp3Thresholds} (0.75 = 0.7 + 0.05). */
export declare const DP3_MIN_MATCH_SCORE = 0.75;
/** Below this score a local match is not even a reuse candidate. */
export declare const DP3_BORDERLINE_MATCH_SCORE = 0.6;
/** Built-in baseline of the confidence gate (AC-016 layer 3). The effective
 * value is `resolveDecidePolicy(DP3_ID, projectDir).minConfidence`. */
export declare const DP3_MIN_CONFIDENCE = 0.7;
/** `answerable` (an `noul` probability) below this is a refusal, not an answer:
 * the model reports it cannot settle the question from the sent candidates.
 * Built-in baseline only; derived by {@link dp3Thresholds} (0.7 - 0.2 = 0.5). */
export declare const DP3_ANSWERABLE_MIN = 0.5;
/** The three dp3 thresholds as a function of the effective `min_confidence`.
 *
 * D-050: the decision STRUCTURE does not change — only the numbers are read
 * from policy instead of the hard-coded constants. The two satellite gates keep
 * their historic margin to the confidence gate, so the built-in layer (0.7)
 * reproduces the pre-AC-016 values exactly: 0.75 / 0.7 / 0.5. */
export declare function dp3Thresholds(minConfidence: number): {
    minMatchScore: number;
    minConfidence: number;
    answerableMin: number;
};
/** Hard cap on the local candidate list (`local_candidates`, 1..5). */
export declare const DP3_CANDIDATE_LIMIT = 5;
/** Client-side canonical state budget (spec §5.4). */
export declare const DP3_MAX_STATE_BYTES = 2000;
/** Question excerpt carried in the injected steer (L2 stays local). */
export declare const DP3_STEER_QUESTION_MAX = 300;
/** Three-way split (spec §4.1): 3a fact, 3b intent, 3c already-answered. */
export type Dp3Sub = "3a" | "3b" | "3c";
/** Failure vocabulary (AC-005, the four-value set from design Q4) plus
 * `input-oversize` (D-028: a REFUSAL, not a degradation — the canonical state is
 * complete, it just cannot be sent, so it must not read as `input-incomplete`).
 *
 * This is a worker-local SUBSET of the single shared `escalated_reason`
 * vocabulary (design D-030 / `decision_points.ESCALATED_REASONS`), which already
 * contains `input-oversize`. Nothing else in TS shares this union
 * (`triage-client.ts` and `decision-tool.ts` type the field as `string`), so the
 * member narrows nothing and widens no outward contract: the legacy
 * `mw decide run` `reason` field keeps its frozen 8-value transport set, where
 * `mw.py` maps `input-oversize` onto `budget-exhausted`. */
export type Dp3EscalatedReason = "disabled" | "unavailable" | "low-confidence" | "input-incomplete" | "input-oversize";
/** Effective dp3 authorization (`decide-points.json`) + transport gate
 * (`.mw/decide.json`). A missing authorization file/row is the registry default
 * (P2 → enabled, auto); a missing/invalid transport file is a complete bypass. */
export interface Dp3Policy {
    enabled: boolean;
    /** Advisory mode for the ZERO-SPAWN paths (3b/3c never reach Python) and for
     * the metric row. A dp3a answer carries Python's own `mode` in the payload and
     * the settle hook prefers THAT (D-036). */
    mode: "auto" | "suggest";
    /** Effective `min_confidence` (AC-016): per-dp row > decide.json > 0.7. */
    minConfidence: number;
    /** Effective `max_questions` (AC-016). The dp3 question set comes from the
     * registry, so this is carried for audit/parity, not for shaping a prompt. */
    maxQuestions: number;
    /** Effective `timeout_s` (AC-016): default child budget when the caller has
     * no explicit `timeoutMs` override. */
    timeoutS: number;
}
/** Read the dp3 policy fail-soft (AC-001). The transport gate is authoritative:
 * without `.mw/decide.json` (`enabled === true`) dp3 does nothing at all, which
 * is what keeps the closed state byte-identical to the pre-dp3 worker.
 *
 * NON-AUTHORITATIVE (D-036): `enabled`/`note` pre-read from
 * `.mw/decide-points.json` exists ONLY to avoid paying for a `mw decide run`
 * child that Python would reject. The authorization verdict belongs to
 * `decision_points.decide_for`; if this mirror disagrees, PYTHON WINS. */
export declare function readDp3Policy(projectDir: string): Dp3Policy;
/** One candidate source of an already-stated answer, already bounded. */
export interface Dp3ReuseSource {
    label: string;
    text: string;
}
/** Bounded local reuse corpus, in priority order (design Q2.2): own dispatch
 * card → sibling cards → goal.md → pm-state `## Decisions`. The session-history
 * level is deliberately absent (L2: user quotes never leave the machine, and
 * this card has no session reader). */
export declare function readDp3ReuseSources(input: {
    projectDir: string;
    taskDir: string;
    taskPath: string;
    taskContent: string;
    trueRoot: string;
    keyDir: string;
    siblingLimit?: number;
    maxBytes?: number;
}): Dp3ReuseSource[];
/** Content tokens for the Jaccard score: latin words verbatim + CJK bigrams
 * (a whitespace split cannot tokenise Chinese prose). */
export declare function dp3ContentTokens(text: string): Set<string>;
/** Exact referents (paths / identifiers / commands / quoted errors) from a
 * question — the second 3c condition besides the Jaccard score. */
export declare function dp3QuestionReferents(text: string): string[];
/** One local reuse hit. `source` is `<path>:<line>`; `quote` is the raw line. */
export interface Dp3ReuseMatch {
    source: string;
    quote: string;
    score: number;
}
/** Deterministic 3c matcher: the best line of each source in priority order,
 * requiring a shared exact referent AND a content-word Jaccard >= 0.6. The
 * first source that clears the effective match threshold (default
 * {@link DP3_MIN_MATCH_SCORE}, derived from `min_confidence` by
 * {@link dp3Thresholds}) wins (priority order); otherwise the best borderline
 * hit is returned for the caller to escalate. */
export declare function matchDp3Reuse(question: string, sources: readonly Dp3ReuseSource[], minMatchScore?: number): Dp3ReuseMatch | undefined;
/** A fact answer must cite `path:line` (design Q2.2 3a). */
export declare const DP3_CITATION_RE: RegExp;
export interface Dp3DecisionInput {
    projectDir: string;
    taskKey: string;
    /** `nc<N>` index of this clarification event inside the run (1-based). */
    ncIndex: number;
    key: string;
    phase: string;
    taskType: "coding" | "research" | "review";
    risk: "low" | "mid" | "high";
    riskSource: "machine" | "pm-label";
    question: string;
    harnessDetail: string;
    taskDir: string;
    taskPath: string;
    taskContent: string;
    trueRoot: string;
    keyDir: string;
    policy: Dp3Policy;
    /** Test seam; production uses the triage client's `runDecideMw`. */
    runner?: DecideRunner;
    timeoutMs?: number;
}
/** Classification + (for 3a) one decision-service call. Never throws. */
export type Dp3Decision = {
    kind: "answer";
    sub: "3a" | "3c";
    answer: string;
    source?: string;
    decisionId: string;
    confidence: number | null;
    confidenceSource: string;
    /** Effective mode for THIS answer: the child's `payload.mode` when Python
     * answered (D-036: mode is an authorization OUTPUT), otherwise the local
     * `policy.mode` — the 3c path never spawns, so the mirror is all there is. */
    mode: "auto" | "suggest";
    /** D-041: set by the CONSUMING side only — the settle hook that actually
     * injected the `[mw dp3-answer]` steer. The classifier never fills it: an
     * `answer` from the child is a proposal, not an executed action. */
    acted?: boolean;
    /** FIX-J: which local candidate was consumed and from where. The frozen
     * `[DECIDE]` row keeps its shape; this rides its own trace line. */
    detail?: string;
} | {
    kind: "escalate";
    sub?: Dp3Sub;
    reason: Dp3EscalatedReason | "intent";
    detail: string;
    decisionId: string;
};
/** Map an arbitrary worker role onto the dp3 `task_type` enum. A role outside
 * the enum keeps its nature (write tools → coding, else research) instead of
 * refusing the decision outright. */
export declare function dp3TaskType(type: string): "coding" | "research" | "review";
/** One locally generated dp3 candidate. `label` is the bounded repo-relative
 * path that rides `local_candidates`; `path` is the absolute file the answer is
 * quoted from (the child never supplies either). */
export interface Dp3Candidate {
    id: string;
    label: string;
    path: string;
}
/** Question tokens of the candidate matcher (FIX-J §2): ASCII words of >= 3
 * chars and CJK runs of >= 2 chars, lowercased, stopwords dropped, first-seen
 * order (so the line scan below is deterministic). */
export declare function dp3CandidateTokens(question: string): string[];
/** Deterministic local candidate list for one dp3 question (FIX-J §2): `c1` is
 * always the convention evidence file of the task type, `c2..c5` are the best
 * name matches under the four roots, ordered by (hit count desc, path asc). */
export declare function buildDp3Candidates(input: Dp3DecisionInput, question: string): Dp3Candidate[];
/** Decide one clarification (never throws; the caller owns the trace + steer). */
export declare function decideDp3WorkerClarify(input: Dp3DecisionInput): Dp3Decision;
/** The injected steer (DS-7: machine-attributable, never impersonates a human).
 * The original question is quoted, never rewritten. */
export declare function formatDp3AnswerSteer(decision: {
    sub: "3a" | "3c";
    answer: string;
    source?: string;
    decisionId: string;
}, question: string): string;
/** One unified dp3 metric row. Key order is FROZEN — the offline statistics
 * parse `sub`/`acted`/`escalated_reason` and reconcile `nc_raw` against
 * `nc_human + acted` (Q3.3). `sub=-` means no classifier ran (budget spent). */
export declare function formatDp3TraceLine(input: {
    triggerId: string;
    sub?: Dp3Sub;
    acted: boolean;
    mode: "auto" | "suggest";
    escalatedReason: Dp3EscalatedReason | "intent" | "-";
    decisionId: string;
    ncRaw: number;
    ncHuman: number;
    now?: Date;
}): string;
export {};
//# sourceMappingURL=worker-mode.d.ts.map