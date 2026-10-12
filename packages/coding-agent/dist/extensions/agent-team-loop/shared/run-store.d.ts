/**
 * `run.json` — the product-carried run identity (D-022/D-023, AC-022).
 *
 * IN-3 showed why the queue ledger alone cannot decide whether a task may run:
 * the ledger is a *cache* that can lose rows (252 rows were rebuilt in one
 * second, and a finished task's `output.md` was overwritten at 11:45:40 by a
 * re-run nobody asked for). The fix is the opposite direction: the WORKER writes
 * its own identity and terminal state next to its own products, and the
 * dispatcher reads that file before queueing anything.
 *
 * Roles per the frozen T-20 contract:
 *   - the worker is the only writer of `running` and of the terminal states;
 *   - the Python launcher may only ever ADD `lost` (process gone, outcome
 *     unknown) — never `done`/`failed` (see `mw_common.mark_run_lost`);
 *   - a task_key identifies ONE run; more work means a new task_key that
 *     declares `supersedes: <old>`.
 *
 * Every write here is best-effort by contract (R15): a `run.json` failure must
 * never block `output.md` from being written, so failures are swallowed and
 * noted in the task's own `trace.log`.
 */
export declare const RUN_FILE_NAME = "run.json";
export declare const RUN_SCHEMA = 1;
export type RunStatus = "pending" | "running" | "done" | "failed" | "needs-clarification" | "lost";
/** Statuses that end a run's life: it must never be started again under the
 * same task_key (AC-022). Mirrors `mw_common.RUN_TERMINAL_STATUSES` — keep the
 * two sets identical, they are the cross-language contract. */
export declare const RUN_TERMINAL_STATUSES: ReadonlySet<string>;
export interface RunState {
    schema: number;
    task_key: string;
    /** `<task_key>@<iso>` — unique per run, never reused (D-023). */
    run_id: string;
    owner_key: string;
    /** Task type from task.md (`coding`/`review`/`research`/...). */
    kind: string;
    status: RunStatus;
    started_at: string;
    ended_at?: string;
    /** Process exit code; absent while running, absent for `lost`. */
    exit?: number;
    /** `<task_key>` this run replaces (task.md header `supersedes:`). */
    supersedes?: string;
    /** Deliverable file names that existed at terminal write time. */
    artifacts: string[];
    pid?: number;
    last_heartbeat_at?: string;
}
/** `<taskDir>/run.json`. */
export declare function runPath(taskDir: string): string;
/** Why a candidate may not be dispatched (AC-022). */
export type RunIdentityRefusal = "run-terminal" | "run-active" | "supersede-unknown" | "supersede-not-terminal";
export type RunIdentityVerdict = {
    ok: true;
} | {
    ok: false;
    reason: RunIdentityRefusal;
    detail?: string;
};
/** Read a run record, or `undefined` for "no information": missing file, bad
 * JSON, non-object root, or no usable status. Must never throw — the dispatcher
 * calls this inside its scan loop (a throw would break the whole scan). */
export declare function readRunState(taskDir: string): RunState | undefined;
/** `terminal` (never restart), `active` (a run is/was live — do not duplicate),
 * or `unknown` (no record, or a status this version does not know: treated as
 * "no information" so a future status can never wedge dispatch). */
export declare function runStateKind(state: RunState | undefined): "terminal" | "active" | "unknown";
export declare function isTerminalRunStatus(status: string | undefined): boolean;
/** `<task_key>@<iso>` — the marker's identity half. */
export declare function newRunId(taskKey: string, now?: Date): string;
/** Single line a human (and a grep) can use to tie `output.md` back to one run.
 * Written by {@link writeOutputViaMarker}; see the note there about its
 * placement — it never displaces an agent-written machine-readable first line. */
export declare function runMarker(state: RunState): string;
/** Deliverables present in the task dir at terminal-write time. Best-effort:
 * a readdir failure simply yields an empty list. */
export declare function collectArtifacts(taskDir: string): string[];
/** Write the whole record (the worker owns it; single writer per task dir).
 * Atomic via tmp + rename, never throws: returns `{ok:false}` and leaves a
 * `trace.log` note instead (R15 — `output.md` must still be written). */
export declare function writeRunState(taskDir: string, state: RunState): {
    ok: boolean;
    error?: string;
};
/** `supersedes: <task_key>` from a task.md header block, or `undefined`.
 * Header convention is shared with `origin:` / `type:` (one line, column 0). */
export declare function parseSupersedes(taskContent: string): string | undefined;
/** AC-022 dispatch gate for one candidate task dir.
 *
 * Refusals (all fail-closed — the task is not queued):
 *   - the task's own `run.json` is terminal: a task_key is one run, so a re-run
 *     needs a NEW task_key (`<task>-r2`) declaring `supersedes:`; re-queueing
 *     the same dir would overwrite the very artifacts the user must be able to
 *     trust;
 *   - the task's own `run.json` is active: its row may have been lost while the
 *     run is (or was) live — queueing it again would create a second writer for
 *     one directory;
 *   - `supersedes: X` where X is unknown or not terminal: a live/absent run
 *     must not be silently replaced.
 *
 * Allowed: no run record at all (zero-backfill: historical tasks behave exactly
 * as before), and `supersedes: X` with X terminal.
 *
 * `readTaskContent` is lazy — a task with a terminal/active own record is
 * refused without reading task.md at all. */
export declare function evaluateRunIdentity(input: {
    taskDir: string;
    readTaskContent: () => string;
    resolveTaskDir: (taskKey: string) => string | undefined;
    /** Test seam; defaults to {@link readRunState}. */
    readState?: (taskDir: string) => RunState | undefined;
}): RunIdentityVerdict;
//# sourceMappingURL=run-store.d.ts.map