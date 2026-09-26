/**
 * console.ts — the /autopilot command set (goal-autopilot T-15, AC-015/016/
 * 018/025, design §4.1 / D-005 / D-109).
 *
 * The console is STATELESS: every command derives its view from the file
 * family alone (D-005 — console closed and reopened is just a normal
 * reopen). The one piece of persistent context, the timeline watermark, is
 * a pi session entry (`agent-team-loop:autopilot-seen`, same mechanism as
 * WATCH_ENTRY_TYPE) — the session file belongs to pi, not the console.
 *
 * Commands:
 *   /autopilot status [--json]        stage progress / gate queue / timeline
 *                                     watermark / per-key round budgets; the
 *                                     human view and --json come from the
 *                                     same derivation (view parity, VC-017)
 *   /autopilot gates                  pending gate list
 *   /autopilot gate <id> approve|reject [--note <text>]
 *                                     answer a gate under .mw/gates.lock
 *                                     (AC-016)
 *   /autopilot timeline [--since <iso>] [--all]
 *                                     replay events since the last-seen
 *                                     watermark (default), beats filtered;
 *                                     --all replays everything incl. beats
 *   /autopilot enable | disable       write config atomically; enable starts
 *                                     mw serve when it is not running
 *                                     (AC-025)
 *   /autopilot pause | resume         write config paused — the conductor
 *                                     stays alive but stops dispatching
 *   /autopilot monitor [on|off]        toggle the bottom monitor panel
 *                                     (serve/conductor/workers/gates,
 *                                     read-only, 4s refresh — AC-001..008;
 *                                     print mode degrades to a notice)
 *   /autopilot roadmap                stage summary view
 */
import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
import { type LockOptions } from "../shared/file-lock.ts";
import { type readMonitorState } from "./monitor.ts";
import { type AutopilotConfig } from "./status-model.ts";
/** Session entry type persisting this window's timeline watermark (D-109
 * seq/watermark protocol — same mechanism as WATCH_ENTRY_TYPE). */
export declare const AUTOPILOT_SEEN_ENTRY_TYPE = "agent-team-loop:autopilot-seen";
export type EnsureMwOutcome = "started" | "already-running" | "restarted" | "spawn-failed";
export interface AutopilotConsoleDeps {
    /** Test seam for the enable flow's "ensure a CURRENT mw serve is running"
     * step (AC-025 + stale-serve fix). Default: getMwStatus + startMw, plus a
     * stale-serve restart — a serve predating the current code never spawns
     * the conductor, so enable must not promise one. */
    ensureMwRunning?: (projectDir: string) => EnsureMwOutcome | Promise<EnsureMwOutcome>;
    /** Test seam for the monitor panel's state derivation (autopilot-monitor
     * L1 fixtures). Default: readMonitorState from monitor.ts. */
    readMonitorState?: typeof readMonitorState;
    /** Test seam for the monitor poll interval (default 4000ms). */
    monitorIntervalMs?: number;
    /** Auto-show the monitor for autopilot-enabled projects on session start
     * (default true). Set false to opt out (tests / embeddings). */
    autoMonitor?: boolean;
    /** Lock retry budget for the config read-modify-write handlers. Default:
     * retries=6, baseDelayMs=20 (identical to the Python writer, worst case
     * ~1.26s). Tests inject a tiny budget. */
    lockOpts?: LockOptions;
}
export declare function registerAutopilotCommands(pi: ExtensionAPI, projectDir: string, deps?: AutopilotConsoleDeps): void;
/** Lock retry budget frozen by plan §2.2 — identical to the Python writer
 * (`mw_common.acquire_lock(retries=6, base_delay=0.02)`). */
export declare const DEFAULT_CONFIG_LOCK_OPTS: LockOptions;
/** Read-modify-write config.json under `.mw/autopilot-config.lock` (D-006).
 * The whole read → mutate → atomic write runs inside the lock: two windows (or
 * a window and the `mw autopilot verify` CLI) can otherwise interleave and roll
 * each other back. A lock that cannot be taken fails closed — the caller
 * reports the error and NOTHING is written. The lock deliberately lives here,
 * not inside `saveConfig` (the primitive is not re-entrant, D-006). */
export declare function saveConfigLocked(projectDir: string, mutate: (config: AutopilotConfig) => AutopilotConfig, lockOpts?: LockOptions): Promise<{
    ok: true;
} | {
    ok: false;
    error: string;
}>;
/** Forget the session-level suppression. The test suite uses it so one case's
 * `/autopilot monitor off` cannot leak into the next (a production session is
 * one process lifetime; a future session_shutdown hook can call this too). */
export declare function resetMonitorSuppression(): void;
/** Show the monitor automatically for autopilot-enabled projects.
 *
 * Called from the PM session_start hook, the first place a UI context exists
 * (registerAutopilotCommands runs at extension load, with no ctx). Feedback for
 * a stalled key has to be visible without remembering a command to run — the
 * E2Feature incident ran 2h35m unnoticed because nothing surfaced it.
 *
 * Returns true when the panel is showing. Idempotent: an already-active panel
 * is left alone (and reports true). Guards, in order: no visual UI, the
 * autoMonitor opt-out, an explicit session-level `/autopilot monitor off`,
 * and a config that is absent/invalid or `enabled: false`. */
export declare function autoStartMonitor(ctx: ExtensionContext, projectDir: string, deps?: AutopilotConsoleDeps): boolean;
//# sourceMappingURL=console.d.ts.map