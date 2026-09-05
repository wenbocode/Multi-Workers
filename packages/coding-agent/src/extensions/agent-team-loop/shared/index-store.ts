import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "./file-lock.ts";

export type IndexStatus = "active" | "idle" | "done";

export interface IndexEntry {
	key: string;
	status: IndexStatus;
	phase: string;
	claimId: string;
	deps: string;
	desc: string;
	updated: string;
}

const INDEX_COLS = 7;

function parseIndexLine(line: string): IndexEntry | undefined {
	const trimmed = line.trim();
	if (!trimmed || trimmed.startsWith("#")) return undefined;

	let parts: string[];
	// AgenticTask format: "| key | status | ... | updated |" — 9 split-by-| parts (empty outer)
	// Bare format: "key | status | ... | updated" — 7 parts
	if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
		parts = trimmed
			.slice(1, -1)
			.split("|")
			.map((s) => s.trim());
	} else {
		parts = trimmed.split("|").map((s) => s.trim());
	}

	if (parts.length !== INDEX_COLS) return undefined;
	const [key, status, phase, claimId, deps, desc, updated] = parts;
	if (!key || key.startsWith("#") || key.startsWith("-") || key === "Key" || key.startsWith("---")) return undefined;
	return {
		key,
		status: (status ?? "idle") as IndexStatus,
		phase: phase ?? "",
		claimId: claimId ?? "",
		deps: deps ?? "",
		desc: desc ?? "",
		updated: updated ?? "",
	};
}

function serializeIndexLine(entry: IndexEntry): string {
	// Write in AgenticTask format so the external indexer can read rows back
	return `| ${[entry.key, entry.status, entry.phase, entry.claimId, entry.deps, entry.desc, entry.updated].join(" | ")} |`;
}

export class IndexStore {
	private readonly filePath: string;
	private readonly lockPath: string;

	constructor(agenticdocRoot: string) {
		this.filePath = path.join(agenticdocRoot, "_index.parallel");
		this.lockPath = path.join(agenticdocRoot, "..", ".mw", "index.lock");
	}

	readAll(): IndexEntry[] {
		if (!fs.existsSync(this.filePath)) return [];
		const lines = fs.readFileSync(this.filePath, "utf8").split("\n");
		return lines.map(parseIndexLine).filter((e): e is IndexEntry => e !== undefined);
	}

	async upsert(entry: IndexEntry): Promise<void> {
		const release = await acquireLock(this.lockPath);
		try {
			const existing = this.readAll();
			const idx = existing.findIndex((e) => e.key === entry.key);
			if (idx >= 0) {
				existing[idx] = entry;
			} else {
				existing.push(entry);
			}
			// Preserve AgenticTask header lines: "# Index Parallel", "| Key | ... |", "| --- | ... |"
			let header = "";
			if (fs.existsSync(this.filePath)) {
				const raw = fs.readFileSync(this.filePath, "utf8");
				const headerLines: string[] = [];
				for (const l of raw.split("\n")) {
					const t = l.trim();
					if (t.startsWith("#") || t.startsWith("| Key") || t.startsWith("| ---") || t.startsWith("|---")) {
						headerLines.push(l);
					} else {
						break;
					}
				}
				if (headerLines.length > 0) {
					header = `${headerLines.join("\n")}\n`;
				}
			}
			const rows = existing.map(serializeIndexLine).join("\n");
			const content = `${header}${rows}\n`;
			const tmpPath = `${this.filePath}.tmp`;
			fs.writeFileSync(tmpPath, content, "utf8");
			fs.renameSync(tmpPath, this.filePath);
		} finally {
			release();
		}
	}

	findByKey(key: string): IndexEntry | undefined {
		return this.readAll().find((e) => e.key === key);
	}

	/** The currently active AgenticTask key, if any (single-active discipline). */
	activeKey(): string | undefined {
		return this.readAll().find((e) => e.status === "active")?.key;
	}
}
