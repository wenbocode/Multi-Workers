import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "./file-lock.js";
const WORKER_COLS = 8;
function parseWorkerLine(line) {
    const parts = line.split("|");
    // Tolerate legacy 7-column rows (no model) as well as the current 8-column layout.
    if (parts.length !== WORKER_COLS && parts.length !== WORKER_COLS - 1)
        return undefined;
    const [taskKey, status, cli, provider, taskPath, dispatchedAt, updatedAt, model] = parts.map((s) => s.trim());
    if (!taskKey || taskKey.startsWith("#"))
        return undefined;
    return {
        taskKey: taskKey ?? "",
        status: (status ?? "pending"),
        cli: cli ?? "",
        provider: provider ?? "",
        taskPath: taskPath ?? "",
        dispatchedAt: dispatchedAt ?? "",
        updatedAt: updatedAt ?? "",
        model: model ?? "",
    };
}
function serializeWorkerLine(entry) {
    return [
        entry.taskKey,
        entry.status,
        entry.cli,
        entry.provider,
        entry.taskPath,
        entry.dispatchedAt,
        entry.updatedAt,
        entry.model ?? "",
    ].join(" | ");
}
export class WorkerStore {
    filePath;
    lockPath;
    constructor(agenticdocRoot) {
        this.filePath = path.join(agenticdocRoot, "_workers.parallel");
        this.lockPath = path.join(agenticdocRoot, "..", ".mw", "workers.lock");
    }
    readAll() {
        if (!fs.existsSync(this.filePath))
            return [];
        const lines = fs.readFileSync(this.filePath, "utf8").split("\n");
        return lines.map(parseWorkerLine).filter((e) => e !== undefined);
    }
    async upsert(entry) {
        const release = await acquireLock(this.lockPath);
        try {
            const existing = this.readAll();
            const idx = existing.findIndex((e) => e.taskKey === entry.taskKey);
            if (idx >= 0) {
                existing[idx] = entry;
            }
            else {
                existing.push(entry);
            }
            const content = `${existing.map(serializeWorkerLine).join("\n")}\n`;
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