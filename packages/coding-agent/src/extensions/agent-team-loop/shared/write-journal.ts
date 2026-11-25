/**
 * PM-window write journal (mw-key-write-journal, AC-001).
 *
 * A worker window already records every successful write in its own
 * `trace.log` (`[WRITE_FILE]` / `[WRITE_UNRESOLVED]`). This module covers the
 * OTHER half: writes made directly by the PM window. It observes the real
 * `tool_result` event, so the agent never has to call a recorder tool and a
 * failed write is never recorded.
 *
 * Events land in `.agenticdoc/<key>/write-journal.jsonl`, one JSON line each.
 * `change_set.py` folds this file together with worker traces and the closure
 * write list at done time. All of `.agenticdoc/` is process state and is
 * deliberately excluded from the produced-code record.
 *
 * Claim checks use the shared index reader and lock so a key transfer cannot
 * interleave with a journal append.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI, ToolResultEvent } from "../../../core/extensions/types.ts";
import { repoRelativePath } from "./change-ledger.ts";
import { acquireLock } from "./file-lock.ts";
import { currentClaimId } from "./implementation-gate.ts";
import { type IndexEntry, IndexStore, keyNameRefusal, normalizeKey } from "./index-store.ts";
import { AGENTICDOC_DIR, agenticdocRoot } from "./paths.ts";

const JOURNAL_NAME = "write-journal.jsonl";
const MAX_TARGET = 240;

export interface PmWriteEvent {
	ts: string;
	key: string;
	source: "pm-tool-result";
	tool: string;
	path: string;
}

export interface PmUnresolvedEvent {
	ts: string;
	key: string;
	source: "unresolved";
	tool: string;
	pattern: string;
	target: string;
}

export type PmJournalEvent = PmWriteEvent | PmUnresolvedEvent;

/** A redirect whose target is a literal path, or a dynamic target that must be
 * reported as "a write happened, path unknown" instead of guessed. */
const REDIRECT_RE = /(?:^|[\s;|&])(?:2>|1>|&>|>>|>)\s*(?:"([^"]+)"|'([^']+)'|([^\s>;|&]+))/g;
/** Write verbs whose operand we do not parse; one warn-only marker per command. */
const WRITE_VERB_RE = /\b(?:tee|cp|mv|install)\b|\bsed\s+-i\b/;

export interface BashTargets {
	resolved: string[];
	unresolved: string[];
}

/** Conservative static extraction. An empty result means "no recognized
 * write", not "no write happened" — a script-driven write stays unobservable
 * from the tool layer and is surfaced through coverage, never faked. */
export function bashWriteTargets(command: string): BashTargets {
	const resolved: string[] = [];
	const unresolved: string[] = [];
	for (const match of command.matchAll(REDIRECT_RE)) {
		const token = (match[1] ?? match[2] ?? match[3] ?? "").trim();
		if (token === "" || /^&\d+$/.test(token) || token.startsWith("/dev/")) continue;
		// A bare token carrying a quote is a quoted string fragment, not a
		// redirect target (real quoted targets arrive via groups 1/2).
		if (/["']/.test(token)) continue;
		if (/[*$`{}]/.test(token) || !/[./\\]/.test(token)) {
			unresolved.push(token.slice(0, MAX_TARGET));
			continue;
		}
		resolved.push(token);
	}
	if (resolved.length === 0 && unresolved.length === 0 && WRITE_VERB_RE.test(command)) {
		unresolved.push("(write verb target unparsed)");
	}
	return { resolved, unresolved };
}

/** Repo-relative path of a tool target. Absolute targets outside the
 * workspace stay absolute: an honest record is better than a dropped write. */
export function journalPath(raw: string, projectDir: string): string {
	return repoRelativePath(path.resolve(projectDir, raw), projectDir);
}

export function isProcessState(rel: string): boolean {
	return rel.replaceAll("\\", "/").split("/")[0]?.toLowerCase() === AGENTICDOC_DIR;
}

function resolveJournalKey(rows: readonly IndexEntry[], watchedKey: string | undefined): string | undefined {
	const claimId = currentClaimId();
	const watched = watchedKey ? normalizeKey(watchedKey) : undefined;
	const owned = rows.filter(
		(row) =>
			row.status === "active" &&
			row.phase.toLowerCase() !== "done" &&
			row.claimId === claimId &&
			(watched === undefined || normalizeKey(row.key) === watched),
	);
	if (owned.length !== 1) return undefined;
	const key = owned[0].key;
	if (keyNameRefusal(key) || rows.filter((row) => normalizeKey(row.key) === normalizeKey(key)).length !== 1) {
		return undefined;
	}
	return key;
}

/** Best-effort append. A journal failure must never break a tool call or a
 * write that already succeeded. */
export function appendJournalEvents(keyDir: string, events: readonly PmJournalEvent[]): void {
	if (events.length === 0) return;
	const file = path.join(keyDir, JOURNAL_NAME);
	try {
		fs.mkdirSync(path.dirname(file), { recursive: true });
		fs.appendFileSync(file, `${events.map((event) => JSON.stringify(event)).join("\n")}\n`, "utf8");
	} catch {
		// Diagnostic channel only.
	}
}

/** Turn one successful tool_result into journal events. Pure: no filesystem
 * access, so the registration can be tested without a live agent loop. */
export function journalEventsForResult(event: ToolResultEvent, key: string, projectDir: string): PmJournalEvent[] {
	if (event.isError) return [];
	const input = event.input as Record<string, unknown>;
	const ts = new Date().toISOString();
	const events: PmJournalEvent[] = [];
	const addPath = (raw: unknown, tool: string): void => {
		if (typeof raw !== "string" || raw.trim() === "") return;
		const rel = journalPath(raw, projectDir);
		if (rel === "" || isProcessState(rel)) return;
		events.push({ ts, key, source: "pm-tool-result", tool, path: rel });
	};
	if (event.toolName === "write" || event.toolName === "edit") {
		addPath(input.path, event.toolName);
	} else if (event.toolName === "bash" && typeof input.command === "string") {
		const targets = bashWriteTargets(input.command);
		for (const target of targets.resolved) addPath(target, "bash");
		for (const target of targets.unresolved) {
			events.push({
				ts,
				key,
				source: "unresolved",
				tool: "bash",
				pattern: "bash-target",
				target: target.slice(0, MAX_TARGET),
			});
		}
	}
	return events;
}

/** Registered only in the PM branch of activate(), so a worker window is never
 * double-recorded (its own trace.log remains the single source). */
export function registerPmWriteJournal(
	pi: ExtensionAPI,
	projectDir: string,
	getWatchedKey: () => string | undefined,
): void {
	if (process.env.PI_WORKER_TASK !== undefined) return;
	const docRoot = agenticdocRoot(projectDir);
	const index = new IndexStore(docRoot);
	const lockPath = path.join(projectDir, ".mw", "index.lock");
	pi.on("tool_result", async (event: ToolResultEvent) => {
		if (event.isError || !["write", "edit", "bash"].includes(event.toolName)) return;
		const watchedKey = getWatchedKey();
		try {
			const release = await acquireLock(lockPath, { retries: 2 });
			try {
				if (getWatchedKey() !== watchedKey) return;
				const key = resolveJournalKey(index.readAuthorityRows(), watchedKey);
				if (key === undefined) return;
				appendJournalEvents(path.join(docRoot, key), journalEventsForResult(event, key, projectDir));
			} finally {
				release();
			}
		} catch {
			// The journal is best-effort. Unavailable authority never changes the tool result.
		}
	});
}
