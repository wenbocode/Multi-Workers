import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../../core/extensions/types.ts";
import type { ModelRegistry } from "../../../core/model-registry.ts";
import type { AckStore } from "../shared/ack-store.ts";
import { type IndexStore } from "../shared/index-store.ts";
import type { DoctorJson, MwCliResult } from "../shared/mw-runner.ts";
import type { WorkerEntry, WorkerStatus, WorkerStore } from "../shared/worker-store.ts";
/** Owner key for a worker task — this window's own claim first, the shared
 * active pointer second. Explicit key wins (deliberate choice — no warning).
 * Otherwise, when this window watches a key whose _index.parallel row it
 * holds (claimId === this window's host:pid), dispatches land under that key
 * even when another window's later takeover made a different row the
 * globally-latest active one: single-active demote flips the shared pointer
 * between windows, but ownership does not move. A stale or foreign watch
 * (no claim held) falls back to the global active row — but never one held
 * live by another window (injecting work into another window's key is the
 * cross-window dispatch bug this guards); that case degrades to _scratch
 * with a warning. Then the degraded _index.md `active:` pointer, then
 * _scratch. */
export declare function resolveOwnerKeyWithSync(pi: ExtensionAPI, indexStore: IndexStore, watch: PmWatchState, explicit: string | undefined, agenticdocRoot: string): string;
export declare function displaySummary(pi: ExtensionAPI, summary: string): void;
/** Deliver a message into the conversation AND trigger a PM turn — the
 * shared "wake the PM" channel (finish calls and mid-run escalations).
 * `pi.sendMessage` without `triggerTurn` only injects the message into LLM
 * context: it displays in the transcript, but an idle PM never wakes up.
 * With `triggerTurn: true` an idle PM starts an LLM turn immediately; a
 * streaming PM gets the text steered into the current turn. Informational
 * notices (init, mw start, gate skips) stay passive via displaySummary —
 * they must not spend agent turns. */
export declare function deliverPmAlert(pi: ExtensionAPI, text: string): void;
/** Deliver a terminal worker result (the "finish call" of dispatch →
 * monitor → finish call → pm run). See deliverPmAlert for the channel. */
export declare function deliverWorkerResult(pi: ExtensionAPI, summary: string): void;
export interface PmWatchState {
    /** AgenticTask key this window explicitly executes; undefined = not watching. */
    key: string | undefined;
}
export interface PmUiHolder {
    /** Latest ExtensionContext, captured on session_start so background timers
     * can render UI. Undefined before session start or in headless runs. */
    ctx: ExtensionContext | undefined;
}
/** Session entry type persisting this window's watched key across restarts. */
export declare const WATCH_ENTRY_TYPE = "agent-team-loop:watch";
/** This window's claim identity: host:pid. Written into _index.parallel so
 * another window can tell whether a key's claim is still held by a live
 * process (pid check) before taking it over. */
export declare function windowClaimId(): string;
export type ClaimState = "free" | "held-live" | "held-stale";
/** Whether a key's claim blocks a takeover. "held-live" = another live window
 * (or a foreign host we cannot verify) holds it and --force is required. */
export declare function claimState(claimId: string, self: string): ClaimState;
export interface TakeoverResult {
    ok: boolean;
    /** Present when ok=false: the live claim that blocked the takeover. */
    blockedBy?: string;
    claimId: string;
    /** True when the key row was auto-created (key was unknown to _index.parallel). */
    created: boolean;
    /** Phase-chain audit warnings for the claimed key (empty = clean):
     * two-source divergence + gate-evidence gaps for phases the pm-state
     * claims to have passed. Non-blocking — claiming a broken key to fix it
     * is legitimate; the warnings make the breakage visible immediately. */
    audit: string[];
}
/** Claim a key for this window — shared by /pm-key switch, /pm-key new and
 * the spec-write auto-takeover. Routes through IndexStore.claim so the
 * liveness check, demote, and write are one atomic step under the index
 * lock: racing windows cannot both believe they claimed. Also runs the
 * phase-chain audit on success (audit_phase.py's TS-side mirror). */
export declare function takeOverKey(indexStore: IndexStore, key: string, force: boolean, agenticdocRoot: string): Promise<TakeoverResult>;
/** Owner key of a queue row: the first taskPath segment below the agenticdoc
 * root ({key}/workers/<task>/task.md → key). Legacy root-level rows resolve to
 * their own task key and simply never match a watched key. */
export declare function ownerKeyOf(entry: WorkerEntry, agenticdocRoot: string): string;
/** Body of a `## <section>` block in output.md (first match), trimmed;
 * undefined when the file or section is missing. Generic reader behind
 * readOutputSummary and the terminal-detail fallback chains (D-004): `##
 * TL;DR`, `## Exit Reason`, `## Questions`. The section literal is regex-escaped
 * so a future caller-side string with metacharacters can never inject. */
export declare function readOutputSection(taskDir: string, section: string): string | undefined;
/** `## Summary` body — the legacy detail source, now the done-row fallback
 * when no `## TL;DR` exists (old output.md files, AC-009). */
export declare function readOutputSummary(taskDir: string): string | undefined;
/** Cap for terminal readback bodies (AC-014). */
export declare const OUTPUT_READBACK_MAX = 20000;
/** Full output.md body for terminal readback (AC-014): worker results are
 * delivered into the watching window's conversation so the PM processes
 * them without manual file reads. Over-cap reports are truncated with a
 * pointer to the file. */
export declare function readOutputBody(taskDir: string): string | undefined;
/** Last `[launcher] spawn failed …` line from worker.log, if any. Spawn-failure
 * logs are tiny (the CLI never ran — the launcher writes exactly this line and
 * nothing else); a large log means the worker actually ran, so ignore it. */
export declare function readSpawnFailure(taskDir: string): string | undefined;
/** Last non-empty worker.log line, or undefined. The needs-clarification
 * fallback for tasks that never wrote an output.md (claude/codex workers,
 * old bundles) — their last logged line names what they were asking about. */
export declare function readWorkerLogTail(taskDir: string): string | undefined;
/** Widget detail line for a terminal worker row (D-004): the glyph/status
 * says what happened, this says why it stuck or what it concluded.
 *  - failed: spawn-failure reason (launcher prefix stripped, timestamp-free)
 *    ?? `## Exit Reason` first line
 *  - needs-clarification: `## Questions` first line ?? worker.log tail ??
 *    explicit no-output hint (claude/codex tasks write no output.md at all)
 *  - done: `## TL;DR` first line ?? headline-normalized `## Summary` first
 *    line (old output.md files)
 * Returns "" when nothing informative exists (caller renders the key only).
 * Line-width truncation stays with the caller (WATCH_LINE_MAX). */
export declare function readTerminalDetail(taskDir: string, status: WorkerStatus): string;
/** Shared ack validation + write path behind /mw ack and the ack_worker_result
 * tool (D-002). `"all"` expands to every terminal row not yet acked;
 * individual keys must reference an existing terminal row — running/pending
 * rows are rejected and nothing is written for them (AC-004). */
export declare function ackTasks(workerStore: WorkerStore, ackStore: AckStore, targets: string[] | "all"): Promise<{
    acked: string[];
    rejected: Array<{
        key: string;
        reason: string;
    }>;
}>;
/** Live bottom-widget lines for the watched key, in three sections (D-003):
 *  1. live — running then pending, all shown, never folded
 *  2. unhandled — failed/needs-clarification rows the PM has not acked
 *     (/mw ack), all shown, never folded; header carries the count
 *  3. history — done rows ∪ acked terminal rows, newest-first, capped at
 *     WATCH_HISTORY_MAX with a `+N more` fold line
 * Terminal-row details come from readTerminalDetail (D-004). */
export declare function renderWatchLines(indexStore: IndexStore, workerStore: WorkerStore, ackStore: AckStore, agenticdocRoot: string, key: string): string[];
/** Render (or clear) the bottom watch widget on a UI-capable context. */
export declare function setWatchWidget(ctx: ExtensionContext, lines: string[] | undefined): void;
/** Render (or clear) the widget via the session_start-captured context.
 * No-op before session start or in headless runs. */
export declare function applyWatchWidget(ui: PmUiHolder, lines: string[] | undefined): void;
/** Doc-gate notifier scoped to this window's watched key (AC-011): the scan
 * evaluates gates for every undocumented key (blocking stays global), but a
 * gate event is only BROADCAST here when it is this window's own key — other
 * keys' gates belong to their owning windows. A window watching nothing
 * stays silent. */
export declare function makeScopedDocGateNotifier(pi: ExtensionAPI, watch: PmWatchState): (key: string, gaps: string[]) => boolean;
export declare function registerPmKeyCommands(pi: ExtensionAPI, indexStore: IndexStore, watch: PmWatchState, refreshWatch: (ctx: ExtensionContext) => void, agenticdocRoot: string): void;
/** Insert a session-snapshot section at the top of {key}/pm-state.md's Notes
 * area. Machine-interface lines (- Phase: / - Claim-Id:) are owned by the
 * framework scripts and stay byte-identical: the snapshot is inserted under
 * "## Notes" only, never rewriting the rest of the file (pm-state-guard
 * principle, framework-side write with the same lock protocol as
 * StateManager). Returns the path written. */
export declare function writeSessionSnapshot(agenticdocRoot: string, key: string, lines: string[]): Promise<string>;
/** /pm-save — persist this window's working context into the watched key's
 * pm-state.md so a restarted pi window (e.g. after a framework rebuild) can
 * pick the work back up. The handler writes the mechanical snapshot (watch
 * key, index row, worker counts, free note) itself; the conversational
 * context (what we are doing, decisions, next steps) can only be summarized
 * by the agent, so the handler asks it to — the user invoked the command, so
 * this is a user-requested action, not a framework-injected nudge. */
export declare function registerPmSaveCommand(pi: ExtensionAPI, indexStore: IndexStore, workerStore: WorkerStore, watch: PmWatchState, agenticdocRoot: string): void;
/** /mw-watch — toggle this window's bottom progress widget for one key.
 * Display-only observation: no claim is taken. Use /pm-key switch to take
 * over a key while developing it.
 *
 * Usage: /mw-watch <key>   watch a key (widget appears below the editor)
 *        /mw-watch off     stop watching (widget cleared)
 *        /mw-watch         show current watch state
 */
export declare function registerWatchCommand(pi: ExtensionAPI, watch: PmWatchState, refreshWatch: (ctx: ExtensionContext) => void, indexStore: IndexStore): void;
export declare function registerMwTools(pi: ExtensionAPI, projectDir: string): void;
/** Resolve the task type for one dispatch: an explicit value must be one of
 * DISPATCHABLE_TYPES, an omitted one keeps the legacy cli-derived mapping
 * (pi -> coding, claude -> review, codex -> codex) so pre-existing dispatches
 * stay byte-identical. */
export declare function resolveDispatchType(cli: string, requested: string): {
    ok: true;
    type: string;
} | {
    ok: false;
    message: string;
};
/** Build the task.md frontmatter (type / model / model-reason) for one dispatch
 * and the echo line that tells the PM which layer supplies the model
 * (design D-001~D-007). Shared by the dispatch_worker tool and /worker so the
 * two entries can never drift.
 *
 * Refusals (no task file must be written): an unknown model id for a pi route
 * (validateModelValue), and an override of a configured dispatch.yml role
 * default without a reason. */
export declare function planDispatchFrontmatter(input: {
    cwd: string;
    cli: string;
    provider: string;
    taskType: string;
    model: string;
    modelReason: string;
    registry: ModelRegistry | undefined;
}): {
    ok: true;
    frontmatter: string;
    echo: string;
} | {
    ok: false;
    message: string;
};
/**
 * Register agent-callable tools for worker dispatch and task listing.
 * These complement the slash commands in registerWorkerCommands.
 */
export declare function registerWorkerTools(pi: ExtensionAPI, workerStore: WorkerStore, ackStore: AckStore, indexStore: IndexStore, agenticdocRoot: string, watch: PmWatchState, projectDir?: string): void;
/** Register the agent-callable switch_key tool: same takeover as
 * /pm-key switch, callable mid-conversation. Tool description + prompt
 * guidelines teach the agent when to call it (explicit user request, or
 * starting real task work on a key — ask the user first in that case). */
export declare function registerSwitchKeyTool(pi: ExtensionAPI, indexStore: IndexStore, watch: PmWatchState, refreshWatch: (ctx: ExtensionContext) => void, agenticdocRoot: string): void;
/** Register the agent-callable advance_phase tool: the shell-free path
 * through the AgenticTask phase gates. The guard blocks hand-edits of
 * pm-state.md's '- Phase:' line and points at advance_phase.py; running that
 * via the bash tool was the only route, so a window whose shell resolution
 * or in-shell `python` differs (fresh machines: WSL-only bash, Store-stub
 * python, python3-only Linux) had NO way to advance a phase — it deadlocked
 * with "no shell, cannot execute advance_phase.py / update_index.py". This
 * tool spawns the script directly (list args, no shell); gate semantics stay
 * in the Python script, the single source of truth audit_phase.py replays. */
export declare function registerAdvancePhaseTool(pi: ExtensionAPI, projectDir: string): void;
/**
 * Spawn a worker directly from the pi window.
 * Usage: /worker <claude|codex|pi> [--type <t>] [--model <id>] [--reason <text>] [--key <name>] <desc>
 */
export declare function registerWorkerCommands(pi: ExtensionAPI, workerStore: WorkerStore, indexStore: IndexStore, agenticdocRoot: string, watch: PmWatchState, projectDir?: string): void;
/** Format a doctor JSON report as a readable Chinese summary (same data as
 * the CLI text output — the TS side never re-implements checks, AC-007). */
export declare function formatDoctorReport(report: DoctorJson, fix: boolean): string;
/** Split a command line on whitespace, honoring double-quoted segments
 * (Windows paths with spaces). Exported for tests. */
export declare function splitCommandLine(line: string): string[];
/** Parsed /mw target set flags. */
export interface TargetSetFlags {
    game: string;
    engine?: string;
    vcs?: string;
    uproject?: string;
}
/** Parse the flag tail of `/mw target set`. null when --game is missing or a
 * known flag has no value (unknown flags are ignored — mw.py validates). */
export declare function parseTargetSetFlags(parts: string[]): TargetSetFlags | null;
/** /mw target — dual-workspace config from the pi window. Thin wrapper over
 * `mw.py target` (single source of parsing/validation/rendering); the runner
 * is injectable for tests. set/clear remind that dual mode applies on the
 * NEXT worker spawn — no serve restart needed (launcher resolves per spawn). */
export declare function runMwTargetCommand(ctx: ExtensionCommandContext, projectDir: string, argsText: string, runner?: (projectDir: string, args: string[]) => MwCliResult): Promise<void>;
/** Parsed /mw partition set flags. `roots` keeps the raw NAME=DIR values in
 * command-line order (repeatable flag — order is forwarded verbatim). */
export interface PartitionSetFlags {
    parent: string;
    partition?: string;
    vcs?: string;
    roots: string[];
}
/** Parse the flag tail of `/mw partition set`. null when --parent is missing
 * or a known flag has no value (unknown flags are ignored — mw.py validates). */
export declare function parsePartitionSetFlags(parts: string[]): PartitionSetFlags | null;
/** /mw partition — partition-workspace config from the pi window (mw-target-
 * partition D-010). Thin wrapper over `mw.py partition` (single source of
 * parsing/validation/rendering — the same entry point a direct CLI run hits,
 * so identical args ⇒ identical target.yml bytes); the runner is injectable
 * for tests. set/on remind that the mode applies on the NEXT worker spawn —
 * no serve restart needed (launcher resolves per spawn). */
export declare function runMwPartitionCommand(ctx: ExtensionCommandContext, projectDir: string, argsText: string, runner?: (projectDir: string, args: string[]) => MwCliResult): Promise<void>;
/** /mw model — dispatch model defaults from the pi window. Thin wrapper over
 * `mw.py model` (single source of parsing/validation/rendering); the runner is
 * injectable for tests. set/clear remind when the change takes effect:
 * worker roles on the next spawn (launcher resolves per spawn, no serve
 * restart), `main` at the next window start (session_start application). */
export declare function runMwModelCommand(ctx: ExtensionCommandContext, projectDir: string, argsText: string, runner?: (projectDir: string, args: string[]) => MwCliResult): Promise<void>;
export declare function registerMwCommands(pi: ExtensionAPI, projectDir: string, workerStore: WorkerStore, ackStore: AckStore): void;
//# sourceMappingURL=ui-bridge.d.ts.map