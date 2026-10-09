import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "./file-lock.ts";

export type WorkerStatus = "pending" | "running" | "done" | "failed" | "needs-clarification";

/** Queue-row provenance (D-019/AC-021): `conductor` rows were dispatched by
 * the autopilot conductor, `manual` rows by a PM/TS dispatch. Row membership
 * is decided by this cell plus `taskPath` — never by the `ap-` task-key
 * prefix, which is a false signal on its own (6 measured rows). */
export type WorkerOrigin = "conductor" | "manual";

export interface WorkerEntry {
	taskKey: string;
	status: WorkerStatus;
	cli: string;
	provider: string;
	taskPath: string;
	dispatchedAt: string;
	updatedAt: string;
	/** Optional model id passed to the worker CLI (--model/-m). Empty = launcher default. */
	model: string;
	/** Originating writer; absent on legacy rows (pre-column) and normalised to
	 * `manual` by {@link workerOrigin}. */
	origin?: WorkerOrigin;
}

/** Column count range: 7 legacy (no model) | 8 (no origin) | 9 current. The
 * order is locked to the Python writer (mw_common.parse_workers_file /
 * serialize_entry): task_key | status | cli | provider | task_path |
 * dispatched_at | updated_at | model | origin. */
const WORKER_COLS_MIN = 7;
const WORKER_COLS_MAX = 9;

/** `.agenticdoc/<key>/workers/<task>/task.md` — the queue-row path contract
 * (conductor dispatch.py `task_dir`). Mirrors mw_common._WORKER_PATH_KEY_RE. */
const WORKER_PATH_KEY_RE = /(?:^|[\\/])\.agenticdoc[\\/]([^\\/]+)[\\/]workers[\\/]/;

/** Normalise an `origin` cell: only the literal `conductor` is a conductor
 * dispatch; a missing/empty/unknown cell fails closed to `manual` so the
 * `ap-` prefix can never resurrect the old false signal (VC-028). */
export function normalizeWorkerOrigin(raw: string | undefined): WorkerOrigin {
	return (raw ?? "").trim().toLowerCase() === "conductor" ? "conductor" : "manual";
}

/** Provenance of a row, with legacy rows (no column) read as `manual`. */
export function workerOrigin(entry: WorkerEntry): WorkerOrigin {
	return entry.origin ?? "manual";
}

/** Owner project key of a row: the key its `taskPath` is filed under ("" when
 * the path is not under a `.agenticdoc/<key>/workers/` directory). Independent
 * of `origin` — a manual row still groups under its key; it just never holds a
 * conductor slot (VC-028 `fallback=path`).
 *
 * Anchored exactly like `mw_common.worker_path_key`, so the Python reader and
 * the TS writer agree on the owner key of every row. */
export function workerOwnerKey(entry: WorkerEntry): string {
	return WORKER_PATH_KEY_RE.exec(entry.taskPath)?.[1] ?? "";
}

/** Unified owner predicate (D-019): does this row hold `key`'s autopilot slot?
 * `origin` decides first — manual/legacy rows own no slot — and a conductor
 * row owns the key its `taskPath` anchors under. */
export function workerBelongsToKey(entry: WorkerEntry, key: string): boolean {
	return workerOrigin(entry) === "conductor" && workerOwnerKey(entry) === key;
}

function parseWorkerLine(line: string): WorkerEntry | undefined {
	const parts = line.split("|");
	// Tolerate legacy 7-column rows (no model), 8-column rows (no origin) and
	// the current 9-column layout (origin last).
	if (parts.length < WORKER_COLS_MIN || parts.length > WORKER_COLS_MAX) return undefined;
	const [taskKey, status, cli, provider, taskPath, dispatchedAt, updatedAt, model, origin] = parts.map((s) =>
		s.trim(),
	);
	if (!taskKey || taskKey.startsWith("#")) return undefined;
	return {
		taskKey: taskKey ?? "",
		status: (status ?? "pending") as WorkerStatus,
		cli: cli ?? "",
		provider: provider ?? "",
		taskPath: taskPath ?? "",
		dispatchedAt: dispatchedAt ?? "",
		updatedAt: updatedAt ?? "",
		model: model ?? "",
		origin: origin === undefined || origin === "" ? undefined : normalizeWorkerOrigin(origin),
	};
}

function serializeWorkerLine(entry: WorkerEntry): string {
	// The origin column is always emitted (legacy rows normalise to `manual`):
	// this store is the PM/manual writer, so its rows must never be read back
	// as an unattributed legacy row.
	return [
		entry.taskKey,
		entry.status,
		entry.cli,
		entry.provider,
		entry.taskPath,
		entry.dispatchedAt,
		entry.updatedAt,
		entry.model ?? "",
		workerOrigin(entry),
	].join(" | ");
}

export class WorkerStore {
	private readonly filePath: string;
	private readonly lockPath: string;

	constructor(agenticdocRoot: string) {
		this.filePath = path.join(agenticdocRoot, "_workers.parallel");
		this.lockPath = path.join(agenticdocRoot, "..", ".mw", "workers.lock");
	}

	readAll(): WorkerEntry[] {
		if (!fs.existsSync(this.filePath)) return [];
		const lines = fs.readFileSync(this.filePath, "utf8").split("\n");
		return lines.map(parseWorkerLine).filter((e): e is WorkerEntry => e !== undefined);
	}

	async upsert(entry: WorkerEntry): Promise<void> {
		const release = await acquireLock(this.lockPath);
		try {
			const existing = this.readAll();
			const idx = existing.findIndex((e) => e.taskKey === entry.taskKey);
			if (idx >= 0) {
				existing[idx] = entry;
			} else {
				existing.push(entry);
			}
			const content = `${existing.map(serializeWorkerLine).join("\n")}\n`;
			const tmpPath = `${this.filePath}.tmp`;
			fs.writeFileSync(tmpPath, content, "utf8");
			fs.renameSync(tmpPath, this.filePath);
		} finally {
			release();
		}
	}

	findByKey(taskKey: string): WorkerEntry | undefined {
		return this.readAll().find((e) => e.taskKey === taskKey);
	}
}
