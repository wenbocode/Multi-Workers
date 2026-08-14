import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "./file-lock.ts";

export type WorkerStatus = "pending" | "running" | "done" | "failed" | "needs-clarification";

export interface WorkerEntry {
	taskKey: string;
	status: WorkerStatus;
	cli: string;
	provider: string;
	taskPath: string;
	dispatchedAt: string;
	updatedAt: string;
}

const WORKER_COLS = 7;

function parseWorkerLine(line: string): WorkerEntry | undefined {
	const parts = line.split("|");
	if (parts.length !== WORKER_COLS) return undefined;
	const [taskKey, status, cli, provider, taskPath, dispatchedAt, updatedAt] = parts.map((s) => s.trim());
	if (!taskKey || taskKey.startsWith("#")) return undefined;
	return {
		taskKey: taskKey ?? "",
		status: (status ?? "pending") as WorkerStatus,
		cli: cli ?? "",
		provider: provider ?? "",
		taskPath: taskPath ?? "",
		dispatchedAt: dispatchedAt ?? "",
		updatedAt: updatedAt ?? "",
	};
}

function serializeWorkerLine(entry: WorkerEntry): string {
	return [
		entry.taskKey,
		entry.status,
		entry.cli,
		entry.provider,
		entry.taskPath,
		entry.dispatchedAt,
		entry.updatedAt,
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
