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
			this.writeRows(existing);
		} finally {
			release();
		}
	}

	/** Atomically claim `key` for `self`: liveness check, optional demote of
	 * other active rows, upsert, and a post-write disk verification — all
	 * under ONE lock acquisition, so racing windows cannot both walk away
	 * believing they hold the claim. `heldLive` decides whether a foreign
	 * claim blocks us (ui-bridge claimState; injected to keep this store free
	 * of host/os dependencies). */
	async claim(
		key: string,
		self: string,
		heldLive: (claimId: string) => boolean,
		opts: ClaimOptions = {},
	): Promise<ClaimOutcome> {
		const { force = false, demoteOthers = true, activate = true } = opts;
		const release = await acquireLock(this.lockPath);
		try {
			const rows = this.readAll();
			const idx = rows.findIndex((e) => e.key === key);
			const existing = rows[idx];
			if (existing && existing.claimId !== self && heldLive(existing.claimId) && !force) {
				return { ok: false, blockedBy: existing.claimId, entry: existing, created: false };
			}
			const now = new Date().toISOString();
			if (demoteOthers) {
				for (let i = 0; i < rows.length; i++) {
					if (rows[i].status === "active" && rows[i].key !== key) {
						rows[i] = { ...rows[i], status: "idle", updated: now };
					}
				}
			}
			const claimed: IndexEntry = existing
				? {
						...existing,
						claimId: self,
						updated: now,
						...(activate ? { status: "active" as const } : {}),
					}
				: { key, status: "active", phase: "SPEC", claimId: self, deps: "", desc: "", updated: now };
			if (idx >= 0) rows[idx] = claimed;
			else rows.push(claimed);
			this.writeRows(rows);
			// Post-write verification against the disk: every TS writer holds the
			// lock, so this only trips against lock-skipping writers — and then we
			// must not pretend we own the row.
			const after = this.findByKey(key);
			if (!after || after.claimId !== self) {
				return { ok: false, blockedBy: after?.claimId, entry: after ?? claimed, created: false };
			}
			return { ok: true, entry: after, created: !existing };
		} finally {
			release();
		}
	}

	/** Serialize rows back to _index.parallel, preserving AgenticTask header
	 * lines. Callers must hold the index lock. */
	private writeRows(rows: IndexEntry[]): void {
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
		const content = `${header}${rows.map(serializeIndexLine).join("\n")}\n`;
		const tmpPath = `${this.filePath}.tmp`;
		fs.writeFileSync(tmpPath, content, "utf8");
		fs.renameSync(tmpPath, this.filePath);
	}

	findByKey(key: string): IndexEntry | undefined {
		return this.readAll().find((e) => e.key === key);
	}

	/** The currently active row, if any (single-active discipline).
	 * Legacy divergence can leave several active rows; the most recently
	 * updated one wins (ties: the later row in file order). TS rows carry
	 * ISO-UTC `updated` while update_index.py writes local "YYYY-MM-DD HH:MM",
	 * so compare via Date.parse rather than lexicographic order. Exposes the
	 * full row so callers can also read its claimId (owner resolution must
	 * distinguish "our" active row from another live window's). */
	activeEntry(): IndexEntry | undefined {
		let best: IndexEntry | undefined;
		let bestTs = Number.NEGATIVE_INFINITY;
		for (const e of this.readAll()) {
			if (e.status !== "active") continue;
			const parsed = Date.parse(e.updated);
			const ts = Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
			if (!best || ts >= bestTs) {
				best = e;
				bestTs = ts;
			}
		}
		return best;
	}

	activeKey(): string | undefined {
		return this.activeEntry()?.key;
	}
}

export interface ClaimOutcome {
	ok: boolean;
	/** Present when ok=false: the claim that blocked or beat us. */
	blockedBy?: string;
	/** The target row as it stands after the attempt. */
	entry: IndexEntry;
	/** True when the target row was auto-created (key unknown to the index). */
	created: boolean;
}

export interface ClaimOptions {
	/** Stomp a held-live foreign claim on the target key. */
	force?: boolean;
	/** Demote other active rows (single-active discipline). Explicit takeovers
	 * want this; quiet re-claims of our own row do not. Default true. */
	demoteOthers?: boolean;
	/** Flip the target row to "active". Quiet re-claims keep the row's status. */
	activate?: boolean;
}

/** Read the degraded-mode `active:` pointer from `_index.md`. Fallback for
 * owner-key resolution when `_index.parallel` has no active row. Returns
 * undefined when the file or the line is missing. */
export function readIndexMdActive(agenticdocRoot: string): string | undefined {
	const mdPath = path.join(agenticdocRoot, "_index.md");
	if (!fs.existsSync(mdPath)) return undefined;
	for (const line of fs.readFileSync(mdPath, "utf8").split("\n")) {
		const m = /^active:\s*(\S+)/u.exec(line.trim());
		if (m) return m[1];
	}
	return undefined;
}
