import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "./file-lock.ts";

/**
 * Sidecar store for worker-task acknowledgements (mw-widget-terminal-lifecycle
 * T-01, AC-004/VC-004 — storage half only).
 *
 * Backs `.agenticdoc/_workers.acked`: one `taskKey | ackedAtIso` row per
 * acked task. Writes take the shared workers lock (`.mw/workers.lock`, the
 * same lock WorkerStore uses) and swap the file atomically via tmp + rename,
 * so concurrent PM windows never observe a torn file. The /mw ack channel and
 * its terminal-state validation live in T-07; this class is pure storage.
 */
export class AckStore {
	private readonly filePath: string;
	private readonly lockPath: string;

	constructor(agenticdocRoot: string) {
		this.filePath = path.join(agenticdocRoot, "_workers.acked");
		this.lockPath = path.join(agenticdocRoot, "..", ".mw", "workers.lock");
	}

	/** taskKey -> ackedAt (UTC ISO). Missing file yields an empty map; `#`
	 * comment lines and malformed rows are skipped. */
	readAll(): Map<string, string> {
		const result = new Map<string, string>();
		if (!fs.existsSync(this.filePath)) return result;
		const lines = fs.readFileSync(this.filePath, "utf8").split("\n");
		for (const line of lines) {
			const entry = parseAckLine(line);
			if (entry === undefined) continue;
			result.set(entry.taskKey, entry.ackedAt);
		}
		return result;
	}

	/** Ack taskKeys: hold the workers lock, read-merge-write via tmp + rename.
	 * Idempotent — re-acking a key overwrites its timestamp. Returns the keys
	 * actually written plus the keys rejected by taskKey validation (empty or
	 * containing `|`); rejected keys never touch the file. */
	async ack(taskKeys: string[]): Promise<{ acked: string[]; rejected: string[] }> {
		const ackedAt = new Date().toISOString();
		const acked: string[] = [];
		const rejected: string[] = [];
		for (const taskKey of taskKeys) {
			if (!isValidTaskKey(taskKey)) {
				rejected.push(taskKey);
			} else if (!acked.includes(taskKey)) {
				acked.push(taskKey);
			}
		}
		if (acked.length === 0) return { acked, rejected };

		const release = await acquireLock(this.lockPath);
		try {
			const merged = this.readAll();
			for (const taskKey of acked) {
				merged.set(taskKey, ackedAt);
			}
			const content = `${[...merged].map(([key, ts]) => `${key} | ${ts}`).join("\n")}\n`;
			const tmpPath = `${this.filePath}.tmp`;
			fs.writeFileSync(tmpPath, content, "utf8");
			fs.renameSync(tmpPath, this.filePath);
		} finally {
			release();
		}
		return { acked, rejected };
	}
}

interface AckEntry {
	taskKey: string;
	ackedAt: string;
}

/** `taskKey | ackedAtIso` — exactly two columns, both non-empty after trim.
 * `#`-prefixed rows and anything else (wrong column count, empty key or
 * timestamp) are comments/garbage and skipped on read. */
function parseAckLine(line: string): AckEntry | undefined {
	const parts = line.split("|");
	if (parts.length !== 2) return undefined;
	const taskKey = (parts[0] ?? "").trim();
	const ackedAt = (parts[1] ?? "").trim();
	if (!taskKey || taskKey.startsWith("#") || !ackedAt) return undefined;
	return { taskKey, ackedAt };
}

/** A taskKey is writable only if it is non-empty (including whitespace-only)
 * and contains no `|`, which would corrupt the two-column row format. */
function isValidTaskKey(taskKey: string): boolean {
	return taskKey.length > 0 && !taskKey.includes("|") && taskKey.trim().length > 0;
}
