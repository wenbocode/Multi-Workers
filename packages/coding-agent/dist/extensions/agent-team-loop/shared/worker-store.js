import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "./file-lock.js";
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
export function normalizeWorkerOrigin(raw) {
    return (raw ?? "").trim().toLowerCase() === "conductor" ? "conductor" : "manual";
}
/** Provenance of a row, with legacy rows (no column) read as `manual`. */
export function workerOrigin(entry) {
    return entry.origin ?? "manual";
}
/** Owner project key of a row: the key its `taskPath` is filed under ("" when
 * the path is not under a `.agenticdoc/<key>/workers/` directory). Independent
 * of `origin` — a manual row still groups under its key; it just never holds a
 * conductor slot (VC-028 `fallback=path`).
 *
 * Anchored exactly like `mw_common.worker_path_key`, so the Python reader and
 * the TS writer agree on the owner key of every row. */
export function workerOwnerKey(entry) {
    return WORKER_PATH_KEY_RE.exec(entry.taskPath)?.[1] ?? "";
}
/** Unified owner predicate (D-019): does this row hold `key`'s autopilot slot?
 * `origin` decides first — manual/legacy rows own no slot — and a conductor
 * row owns the key its `taskPath` anchors under. */
export function workerBelongsToKey(entry, key) {
    return workerOrigin(entry) === "conductor" && workerOwnerKey(entry) === key;
}
/** `mw-queue:vN` version header (AC-023). Optional by design: a queue without
 * a header reads as v1, and an existing header-less file is never rewritten to
 * add one (P-018). Both readers skip `#` lines (`mw_common.parse_workers_file`
 * does the same), so the header never changes row parsing. */
const QUEUE_HEADER_RE = /^#\s*mw-queue:v(\d+)\s*$/;
const QUEUE_HEADER_V2 = "# mw-queue:v2";
/** Reads the version header of one raw line, or `undefined` for anything else. */
export function parseQueueHeader(line) {
    const match = QUEUE_HEADER_RE.exec(line.trim());
    return match ? Number(match[1]) : undefined;
}
function parseWorkerLine(line) {
    const parts = line.split("|");
    // Tolerate legacy 7-column rows (no model), 8-column rows (no origin) and
    // the current 9-column layout (origin last).
    if (parts.length < WORKER_COLS_MIN || parts.length > WORKER_COLS_MAX)
        return { ok: false, reason: "cols" };
    const [taskKey, status, cli, provider, taskPath, dispatchedAt, updatedAt, model, origin] = parts.map((s) => s.trim());
    if (!taskKey || taskKey.startsWith("#"))
        return { ok: false, reason: "task-key" };
    return {
        ok: true,
        entry: {
            taskKey: taskKey ?? "",
            status: (status ?? "pending"),
            cli: cli ?? "",
            provider: provider ?? "",
            taskPath: taskPath ?? "",
            dispatchedAt: dispatchedAt ?? "",
            updatedAt: updatedAt ?? "",
            model: model ?? "",
            origin: origin === undefined || origin === "" ? undefined : normalizeWorkerOrigin(origin),
        },
    };
}
function serializeWorkerLine(entry) {
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
    filePath;
    lockPath;
    constructor(agenticdocRoot) {
        this.filePath = path.join(agenticdocRoot, "_workers.parallel");
        this.lockPath = path.join(agenticdocRoot, "..", ".mw", "workers.lock");
    }
    /** Raw queue lines with the trailing newline dropped; `[]` when the file is
     * absent or empty. Keeping the lines verbatim is what lets {@link upsert}
     * rewrite one row without touching any other byte of the file (AC-023). */
    readRawLines() {
        if (!fs.existsSync(this.filePath))
            return [];
        const lines = fs.readFileSync(this.filePath, "utf8").split("\n");
        if (lines.length > 0 && lines[lines.length - 1] === "")
            lines.pop();
        return lines;
    }
    /** The full queue read: rows, unreadable lines (counted, never dropped) and
     * the declared layout version. Blank lines and `#` comments are neither. */
    readQueue() {
        const rows = [];
        const unparsable = [];
        let version = 1;
        for (const [index, line] of this.readRawLines().entries()) {
            if (line.trim() === "")
                continue;
            if (line.trimStart().startsWith("#")) {
                const header = parseQueueHeader(line);
                if (header !== undefined && index === 0)
                    version = header;
                continue;
            }
            const parsed = parseWorkerLine(line);
            if (parsed.ok)
                rows.push(parsed.entry);
            else
                unparsable.push({ index, line, reason: parsed.reason });
        }
        return { rows, unparsable, version };
    }
    readAll() {
        return this.readQueue().rows;
    }
    async upsert(entry) {
        const release = await acquireLock(this.lockPath);
        try {
            const raw = this.readRawLines();
            const replacement = serializeWorkerLine(entry);
            const idx = raw.findIndex((line) => {
                if (line.trim() === "" || line.trimStart().startsWith("#"))
                    return false;
                const parsed = parseWorkerLine(line);
                return parsed.ok && parsed.entry.taskKey === entry.taskKey;
            });
            let lines;
            if (idx >= 0) {
                // In-place row replacement; every other line (including unreadable
                // rows and comments) stays byte-identical.
                lines = raw.map((line, i) => (i === idx ? replacement : line));
            }
            else if (raw.length === 0) {
                // Brand-new queue: stamp the current layout version.
                lines = [QUEUE_HEADER_V2, replacement];
            }
            else {
                // Existing file: append, and never add a header retroactively (P-018).
                lines = [...raw, replacement];
            }
            const content = `${lines.join("\n")}\n`;
            const tmpPath = `${this.filePath}.tmp`;
            fs.writeFileSync(tmpPath, content, "utf8");
            fs.renameSync(tmpPath, this.filePath);
        }
        finally {
            release();
        }
    }
    findByKey(taskKey) {
        return this.readAll().find((e) => e.taskKey === taskKey);
    }
}
//# sourceMappingURL=worker-store.js.map