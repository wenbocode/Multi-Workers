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
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { type readMonitorState } from "./monitor.ts";
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
}
export declare function registerAutopilotCommands(pi: ExtensionAPI, projectDir: string, deps?: AutopilotConsoleDeps): void;
//# sourceMappingURL=console.d.ts.map