import * as fs from "node:fs";
import * as path from "node:path";

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

export const RUN_FILE_NAME = "run.json";
export const RUN_SCHEMA = 1;

export type RunStatus = "pending" | "running" | "done" | "failed" | "needs-clarification" | "lost";

/** Statuses that end a run's life: it must never be started again under the
 * same task_key (AC-022). Mirrors `mw_common.RUN_TERMINAL_STATUSES` — keep the
 * two sets identical, they are the cross-language contract. */
export const RUN_TERMINAL_STATUSES: ReadonlySet<string> = new Set(["done", "failed", "needs-clarification", "lost"]);

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
export function runPath(taskDir: string): string {
	return path.join(taskDir, RUN_FILE_NAME);
}

/** Why a candidate may not be dispatched (AC-022). */
export type RunIdentityRefusal = "run-terminal" | "run-active" | "supersede-unknown" | "supersede-not-terminal";

export type RunIdentityVerdict = { ok: true } | { ok: false; reason: RunIdentityRefusal; detail?: string };

/** Read a run record, or `undefined` for "no information": missing file, bad
 * JSON, non-object root, or no usable status. Must never throw — the dispatcher
 * calls this inside its scan loop (a throw would break the whole scan). */
export function readRunState(taskDir: string): RunState | undefined {
	let raw: string;
	try {
		raw = fs.readFileSync(runPath(taskDir), "utf8");
	} catch {
		return undefined;
	}
	let parsed: unknown;
	try {
		parsed = JSON.parse(raw);
	} catch {
		return undefined;
	}
	if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return undefined;
	const record = parsed as Record<string, unknown>;
	const status = record.status;
	const taskKey = record.task_key;
	if (typeof status !== "string" || status === "" || typeof taskKey !== "string" || taskKey === "") return undefined;
	return parsed as RunState;
}

/** `terminal` (never restart), `active` (a run is/was live — do not duplicate),
 * or `unknown` (no record, or a status this version does not know: treated as
 * "no information" so a future status can never wedge dispatch). */
export function runStateKind(state: RunState | undefined): "terminal" | "active" | "unknown" {
	if (state === undefined) return "unknown";
	if (RUN_TERMINAL_STATUSES.has(state.status)) return "terminal";
	if (state.status === "running" || state.status === "pending") return "active";
	return "unknown";
}

export function isTerminalRunStatus(status: string | undefined): boolean {
	return status !== undefined && RUN_TERMINAL_STATUSES.has(status);
}

/** `<task_key>@<iso>` — the marker's identity half. */
export function newRunId(taskKey: string, now: Date = new Date()): string {
	return `${taskKey}@${now.toISOString()}`;
}

/** Single line a human (and a grep) can use to tie `output.md` back to one run.
 * Written by {@link writeOutputViaMarker}; see the note there about its
 * placement — it never displaces an agent-written machine-readable first line. */
export function runMarker(state: RunState): string {
	return `<!-- mw-run: ${state.run_id} status=${state.status} -->`;
}

/** Deliverables present in the task dir at terminal-write time. Best-effort:
 * a readdir failure simply yields an empty list. */
export function collectArtifacts(taskDir: string): string[] {
	const names: string[] = [];
	for (const fixed of ["output.md", "report.md", "progress.md"]) {
		try {
			if (fs.statSync(path.join(taskDir, fixed)).isFile()) names.push(fixed);
		} catch {
			// absent — not an artifact
		}
	}
	try {
		for (const entry of fs.readdirSync(taskDir, { withFileTypes: true })) {
			if (!entry.isFile()) continue;
			if (/^phase-.*\.md$/.test(entry.name) || /^stage-\d+.*\.md$/.test(entry.name)) names.push(entry.name);
		}
	} catch {
		// unreadable dir — the fixed names above are all we know
	}
	return names.sort();
}

/** Best-effort note in the task's own `trace.log` (same shape as
 * `output-writer.appendTrace`), used when a `run.json` write fails so the
 * failure is visible without breaking the run. */
function appendRunNote(taskDir: string, message: string): void {
	try {
		fs.appendFileSync(path.join(taskDir, "trace.log"), `[FLOW] ${new Date().toISOString()} ${message}\n`, "utf8");
	} catch {
		// Best-effort: nothing else we can do without a writable task dir.
	}
}

/** Write the whole record (the worker owns it; single writer per task dir).
 * Atomic via tmp + rename, never throws: returns `{ok:false}` and leaves a
 * `trace.log` note instead (R15 — `output.md` must still be written). */
export function writeRunState(taskDir: string, state: RunState): { ok: boolean; error?: string } {
	try {
		fs.mkdirSync(taskDir, { recursive: true });
		const target = runPath(taskDir);
		const tmp = `${target}.tmp`;
		fs.writeFileSync(tmp, `${JSON.stringify(state, null, 2)}\n`, "utf8");
		fs.renameSync(tmp, target);
		return { ok: true };
	} catch (err) {
		const message = err instanceof Error ? err.message : String(err);
		appendRunNote(taskDir, `[RUN] run.json write failed (${state.status}): ${message}`);
		return { ok: false, error: message };
	}
}

/** `supersedes: <task_key>` from a task.md header block, or `undefined`.
 * Header convention is shared with `origin:` / `type:` (one line, column 0). */
export function parseSupersedes(taskContent: string): string | undefined {
	const match = /^supersedes:[ \t]*(\S+)[ \t\r]*$/m.exec(taskContent);
	const key = match?.[1]?.trim();
	return key ? key : undefined;
}

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
export function evaluateRunIdentity(input: {
	taskDir: string;
	readTaskContent: () => string;
	resolveTaskDir: (taskKey: string) => string | undefined;
	/** Test seam; defaults to {@link readRunState}. */
	readState?: (taskDir: string) => RunState | undefined;
}): RunIdentityVerdict {
	const read = input.readState ?? readRunState;
	const own = read(input.taskDir);
	const kind = runStateKind(own);
	if (kind === "terminal") {
		return {
			ok: false,
			reason: "run-terminal",
			detail: `status=${own?.status} run_id=${own?.run_id ?? "?"}`,
		};
	}
	if (kind === "active") {
		return {
			ok: false,
			reason: "run-active",
			detail: `status=${own?.status} run_id=${own?.run_id ?? "?"}`,
		};
	}
	// No usable own record: the only remaining gate is the supersede target.
	const target = parseSupersedes(input.readTaskContent());
	if (target === undefined) return { ok: true };
	const targetDir = input.resolveTaskDir(target);
	if (targetDir === undefined) return { ok: false, reason: "supersede-unknown", detail: target };
	const targetKind = runStateKind(read(targetDir));
	if (targetKind !== "terminal") {
		return { ok: false, reason: "supersede-not-terminal", detail: `${target}:${targetKind}` };
	}
	return { ok: true };
}
