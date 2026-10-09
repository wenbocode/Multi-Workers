import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { type RagRuntime } from "../rag/tools.ts";
import type { TaskPhase } from "./phase-runner.ts";
export declare function toolsForType(taskType: string): string[];
/** `toolsForType` plus the narrow write channel for roles with no write/edit
 * tool (D-104/D-106). The allowlist table and `toolsForType` stay byte for
 * byte unchanged (Python parity lock, direct test imports); the writeless
 * extra lives only here. Write roles get the base array untouched, read-only
 * roles get a copy with `worker_file` appended. */
export declare function activeToolsForType(taskType: string): string[];
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
}
/** Machine divergence heuristic (AC-004, advisory only — the PM with the
 * fullest context judges and decides):
 * - high: past the anchor with ZERO writes — pure exploration, the cpr-007
 *   pattern (22 minutes of reads, generation never got time to land).
 * - mid: phase framework present but nothing completed past the anchor, or
 *   the same target read ≥4 times (spinning).
 * - low: writes advancing — implementation underway. */
export declare function computeRisk(s: ConvergenceSignals): "low" | "mid" | "high";
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
    /** l2_read_file_cap frontmatter (positive int), when present. */
    readFileCap?: number;
    /** l2_read_byte_cap frontmatter (positive int), when present. */
    readByteCap?: number;
    /** task.md `rag_chat_budget:` header (positive int), when present. */
    ragChatBudget?: number;
    /** task.md `rag_time_budget_s:` header (positive int seconds), when present. */
    ragTimeBudgetS?: number;
}
export declare function parseTaskMd(taskPath: string): TaskMeta;
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