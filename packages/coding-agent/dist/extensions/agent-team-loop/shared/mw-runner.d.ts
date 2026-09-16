export interface MwStatus {
    running: boolean;
    pid: number | null;
}
/**
 * Resolve mw.py, in order:
 *   1. MW_PY env override
 *   2. `.mw-py-path` sidecar written by `mw setup`/`mw build --install` — the
 *      reliable path when the bundle is loaded from the GLOBAL install dir in an
 *      unrelated project (where the repo-relative lookup below cannot resolve).
 *   3. relative from the extension source (development / project-local install)
 */
export declare function findMwPy(): string | null;
/**
 * Rebuild the extension bundle and reinstall it globally via `mw.py build --install`.
 * Bash-free and cwd-independent (mw.py derives all paths from its own location),
 * so this works from any pi window. The new bundle loads on the next pi start.
 */
export declare function buildMw(): {
    ok: true;
    output: string;
} | {
    ok: false;
    error: string;
};
export declare function getMwStatus(projectDir: string): MwStatus;
/**
 * Run mw init via `mw.py init --project=<dir>` (synchronous — creates directory structure).
 * Returns { ok: true } on success, or { ok: false, error } on failure.
 */
export declare function initMw(projectDir: string): {
    ok: true;
} | {
    ok: false;
    error: string;
};
/**
 * Start mw in the background via `mw.py start --project=<dir>`.
 * Returns true if the spawn was attempted, false if mw.py could not be found.
 */
export declare function startMw(projectDir: string): boolean;
/**
 * Wait for mw to be running by polling getMwStatus.
 * Call this after startMw() to confirm the service is actually up before the
 * agent's first turn.
 *
 * Stability window (mw-dispatch-reliability D-006): the PID file must stay
 * alive for `stableMs` after first sight before this reports started. mw serve
 * can die right after startup (e.g. route precheck failure) — the old
 * "PID file appeared" check reported a false "started" in that window.
 *
 * Returns true if mw is confirmed running within `timeoutMs`, false otherwise.
 */
export declare function waitForMwStart(projectDir: string, timeoutMs?: number, stableMs?: number): Promise<boolean>;
/**
 * Testable core of waitForMwStart: poll an injected status function until it
 * has been continuously `running` for `stableMs` (or the timeout elapses).
 * On timeout the instantaneous state decides — a service alive but observed
 * for less than the stable window still counts as started.
 */
export declare function waitForStart(statusFn: () => {
    running: boolean;
}, timeoutMs: number, stableMs: number, pollMs?: number): Promise<boolean>;
/**
 * Stop mw via `mw.py stop --project=<dir>` (synchronous, waits up to 10s via mw's own logic).
 * Returns true if the command was executed.
 */
export declare function stopMw(projectDir: string): boolean;
/** `.mw/serve.meta` written by mw serve at startup (pid + started_at_ms). */
export interface MwServeMeta {
    pid: number;
    startedAtMs: number;
}
export declare function readServeMeta(projectDir: string): MwServeMeta | null;
/**
 * Newest mtime among mw runtime sources (.py + providers.json) — the serve
 * staleness baseline. Serves load these at startup, so any file newer than
 * the serve's start means the running serve predates current code. Skips
 * tests, dev scratch (`_*`), `__pycache__`, and `dist` (bundle output).
 */
export declare function mwCodeNewestMtimeMs(mwPyOverride?: string): number | null;
export interface ServeStaleness {
    stale: boolean;
    /** Human-readable timestamps for the stale notification. */
    detail: string;
}
/**
 * mtime-based staleness (agreed design: simple; false positives from e.g.
 * git checkouts only cost a restart prompt, and a restart is safe — all state
 * lives in files). Falls back to the PID file's mtime for serves started
 * before serve.meta existed. Returns undefined when it cannot be determined
 * (no meta AND no PID file, or no mw source dir resolved).
 */
export declare function serveStaleness(projectDir: string, codeMtimeMs?: number): ServeStaleness | undefined;
export type RestartMwResult = "restarted" | "stop-failed" | "start-failed";
/**
 * Testable restart core: graceful stop (stop-request + poll) then start +
 * confirm-up. Injected collaborators keep this unit-testable without real
 * processes.
 */
export declare function restartSequence(isRunning: () => boolean, requestStop: () => void, start: () => boolean, waitUp: () => Promise<boolean>, timeoutMs: number, pollMs?: number): Promise<RestartMwResult>;
/**
 * Restart mw serve: same stop protocol as `mw.py stop` (stop-request file +
 * poll), then a fresh detached start. In-flight workers are NOT killed — the
 * new launcher's orphan reconcile adopts them. Returns "restarted" only when
 * the new serve is confirmed up (stability window applies).
 */
export declare function restartMw(projectDir: string, timeoutMs?: number): Promise<RestartMwResult>;
/** Minimal typed view of `mw.py doctor --json` output used by /mw doctor. */
export interface DoctorJson {
    service?: {
        running?: boolean;
        pid?: number | null;
        pid_file?: string;
    };
    proxy?: Array<{
        route?: string;
        port?: number;
        listening?: boolean;
    }>;
    orphan_proxy?: {
        detected?: boolean;
        ports?: Array<{
            port?: number;
            owner_pids?: number[];
        }>;
    };
    launcher_log?: {
        exists?: boolean;
        tail?: string[];
        error_count?: number;
        fatal?: boolean;
    };
    queue?: {
        non_terminal?: Array<{
            task_key?: string;
            status?: string;
            cli?: string;
            task_md_exists?: boolean;
        }>;
        stale_count?: number;
        archived_total?: number;
    };
    worker_liveness?: Array<{
        task_key?: string;
        last_heartbeat?: string | null;
        age_s?: number | null;
        verdict?: "alive" | "stale" | "no-heartbeat";
    }>;
    credentials?: {
        routes?: Array<{
            route?: string;
            available?: boolean;
            source?: {
                kind?: string;
                name?: string;
                path?: string;
            };
            missing?: string | null;
        }>;
        all_missing?: boolean;
    };
    bundle?: {
        available?: boolean;
        stale?: boolean | null;
        global_bundle_mtime?: string;
        source_newest_mtime?: string;
        note?: string;
    };
    fix?: {
        applied?: unknown;
    };
    summary?: {
        healthy?: boolean;
        issues?: unknown;
        suggestions?: unknown;
    };
}
export type DoctorMwResult = {
    ok: true;
    report: DoctorJson;
} | {
    ok: false;
    error: string;
};
/**
 * Run `mw.py doctor --project=<dir> --json` (single source of diagnostics —
 * the TS side never re-implements checks). `fix` adds --fix first.
 */
export declare function doctorMw(projectDir: string, fix?: boolean): DoctorMwResult;
export type TargetMwResult = {
    ok: true;
    output: string;
} | {
    ok: false;
    error: string;
};
/**
 * Run `mw.py target <args...> --project=<dir>` (dual-workspace config:
 * show / set / clear). The Python side stays the single source of parsing,
 * validation, and rendering — the TS side only forwards and displays.
 * `--project` is appended here so callers never forget the control root.
 */
export declare function targetMw(projectDir: string, args: string[]): TargetMwResult;
//# sourceMappingURL=mw-runner.d.ts.map