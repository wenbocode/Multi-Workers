import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import type { TaskPhase } from "./phase-runner.ts";
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
    phases?: TaskPhase[];
    taskKey: string;
    agenticdocRoot: string;
    /** Dispatch origin marker (D-104): "conductor" on autopilot dispatches,
     * undefined on manual/legacy tasks (which keep the fallback path, GC-8). */
    origin?: string;
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
}
export declare function parseTaskMd(taskPath: string): TaskMeta;
export declare function workerModeActivate(pi: ExtensionAPI): Promise<void>;
export {};
//# sourceMappingURL=worker-mode.d.ts.map