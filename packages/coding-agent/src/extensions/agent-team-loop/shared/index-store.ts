import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { acquireLock } from "./file-lock.ts";
import { SCRATCH_WORKERS_KEY } from "./paths.ts";

export type IndexStatus = "active" | "idle" | "done";

// ── Key identity (AC-006 / RQ-5) ────────────────────────────────────────────

/** Reserved `.agenticdoc/` root entries that name framework files/dirs, not
 * AgenticTask key namespaces: the 12 names from RQ-5 plus `_impl_gate.log`
 * (`shared/implementation-gate.ts` writes it) and `_incidents`. This is an
 * EXPLICIT list, deliberately not a `_`/`.` prefix rule (the pre-AC-006
 * exemption): a prefix rule would also exempt `_tmp`, `.mw` and
 * `_index.parallel` from the cross-key guard and let a dispatch with
 * `key: _index.parallel` create `.agenticdoc/_index.parallel/workers/`. */
export const RESERVED_INDEX_NAMES: readonly string[] = [
	"_scratch",
	".mw",
	"_index.parallel",
	"_index.md",
	"_workers.parallel",
	"_workers.stale.parallel",
	"_workers.acked",
	"_autopilot",
	"_project_log.md",
	"_arch_snapshot.md",
	"_pitfalls.md",
	".agenticdoc",
	"_impl_gate.log",
	"_incidents",
];

/** Lower-cased membership set of {@link RESERVED_INDEX_NAMES} (stored names
 * are lower-case; compare through {@link normalizeKey}). */
export const RESERVED_INDEX_NAME_SET: ReadonlySet<string> = new Set(RESERVED_INDEX_NAMES);

/** Comparison form of a key: trimmed and lower-cased. Windows filesystems are
 * case-insensitive, so `MW-KEY` and `mw-key` name the SAME directory — the key
 * namespace must be case-insensitive too (A6). Reads normalize; writes keep
 * the first-seen casing so existing `_index.parallel` bytes are never
 * rewritten by a read (no migration). */
export function normalizeKey(key: string): string {
	return key.trim().toLowerCase();
}

/** True for `_scratch` and its case variants — the only reserved name that is
 * still usable as an owner key (never as a claimable/advanceable key). */
export function isScratchKey(key: string): boolean {
	return normalizeKey(key) === normalizeKey(SCRATCH_WORKERS_KEY);
}

/** Shape of a usable key name: alnum first char, then alnum / `.` / `_` / `-`. */
const KEY_SHAPE_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const KEY_MAX_LENGTH = 64;

/** Stable machine code + human message of a refused key name. */
export interface KeyNameRefusal {
	code: string;
	message: string;
}

/** Shape + reserved-name gate shared by the cross-key guard, `IndexStore.claim`
 * and `advance_phase` (AC-006/DD-07a/DD-07b): `null` = usable key name. Every
 * other return refuses the name unconditionally, independent of claim state,
 * so no caller can bootstrap a namespace next to a framework file. */
export function keyNameRefusal(key: string): KeyNameRefusal | null {
	const trimmed = key.trim();
	if (!trimmed) return { code: "empty-key", message: "the key is empty" };
	if (RESERVED_INDEX_NAME_SET.has(normalizeKey(trimmed))) {
		return {
			code: "reserved-key-name",
			message: `'${trimmed}' is a reserved framework name, not an AgenticTask key namespace`,
		};
	}
	if (trimmed === "." || trimmed === "..") {
		return { code: "key-path-escape", message: `'${trimmed}' escapes the .agenticdoc root` };
	}
	if (/[/\\]/.test(trimmed) || /^[A-Za-z]:/.test(trimmed)) {
		return { code: "key-path-escape", message: `'${trimmed}' contains a path separator or drive prefix` };
	}
	if (trimmed.length > KEY_MAX_LENGTH) {
		return { code: "key-illegal-shape", message: `the key is ${trimmed.length} chars (max ${KEY_MAX_LENGTH})` };
	}
	if (trimmed.endsWith(".")) {
		return { code: "key-illegal-shape", message: `'${trimmed}' ends with '.'` };
	}
	if (/[\u0000-\u001f\u007f:<>"|?*]/.test(trimmed)) {
		return {
			code: "key-illegal-shape",
			message: `'${trimmed}' contains a control, ADS or shell metacharacter`,
		};
	}
	if (!KEY_SHAPE_RE.test(trimmed)) {
		return {
			code: "key-illegal-shape",
			message: `'${trimmed}' does not match ^[A-Za-z0-9][A-Za-z0-9._-]*$`,
		};
	}
	return null;
}

// ── Conductor-side claim liveness (T-19 / AC-011) ───────────────────────────

/** Conductor-side verdict for one claim id (mirror of
 * `packages/multi-workers/autopilot/state.py::claim_state`). `"free"` —
 * empty/placeholder/self; `"live"` — this host, pid alive (the conductor's
 * ONLY skip condition); `"dead"` — foreign host or dead pid; `"stale"` —
 * unparseable (legacy). */
export type ConductorClaimState = "free" | "live" | "dead" | "stale";

const CONDUCTOR_CLAIM_RE = /^([^:]+):(\d+)$/;

function conductorPidAlive(pid: number): boolean {
	try {
		process.kill(pid, 0);
		return true;
	} catch (err) {
		// EPERM: the process exists but is not ours — still alive. ESRCH: gone.
		return (err as NodeJS.ErrnoException).code === "EPERM";
	}
}

/** Liveness verdict the Python conductor uses to decide whether a key's claim
 * blocks dispatch (`conductor.py`: `if claim == state.CLAIM_LIVE: ... continue`).
 *
 * This is deliberately NOT `ui-bridge.ts::claimState`: that one is the
 * takeover guard and conservatively reports a FOREIGN host as `held-live`
 * ("cannot verify liveness"), while the conductor treats a foreign host as
 * `dead` ("conductor-side rule: foreign host is not live"). ORPHANED judgement
 * and the repair path must speak the CONDUCTOR's language, or a key the
 * conductor is happy to drive would be mis-labelled orphaned. */
export function conductorClaimState(claimId: string, selfId = ""): ConductorClaimState {
	const trimmed = (claimId ?? "").trim();
	if (!trimmed || trimmed === "—" || trimmed === "-" || (selfId !== "" && trimmed === selfId)) return "free";
	const match = CONDUCTOR_CLAIM_RE.exec(trimmed);
	if (!match) return "stale";
	const pid = Number(match[2]);
	if (!Number.isInteger(pid) || pid <= 0) return "stale";
	if (match[1] !== os.hostname()) return "dead";
	return conductorPidAlive(pid) ? "live" : "dead";
}

// ── Owner evidence for the widened ORPHANED admission (T-22 / AC-011) ──────

/** Maximum depth the owner-trace scan descends into a key's `workers/` tree.
 * Worker task dirs are `workers/<task-key>/`, so depth 1 is the normal shape;
 * the cap keeps a pathological tree from turning a read-only scan into a walk
 * of the whole disk. */
const OWNER_TRACE_MAX_DEPTH = 3;

/** Does a `trace.log` exist anywhere under `workersDir`? A worker only ever
 * writes `trace.log` from inside its own task dir, so its existence is a durable
 * "this key has had an owner" fact even when `_index.parallel` lost the key's row
 * (index rotation, concurrent whole-file rewrite, or the non-atomic
 * `dispatch_worker(key=…)` create-then-register pair). Read-only and best-effort:
 * an unreadable directory reads as "no trace". */
function hasWorkerTraceLog(workersDir: string, depth: number): boolean {
	let entries: fs.Dirent[];
	try {
		entries = fs.readdirSync(workersDir, { withFileTypes: true });
	} catch {
		return false;
	}
	for (const entry of entries) {
		if (entry.isFile() && entry.name === "trace.log") return true;
	}
	if (depth >= OWNER_TRACE_MAX_DEPTH) return false;
	for (const entry of entries) {
		if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
		if (hasWorkerTraceLog(path.join(workersDir, entry.name), depth + 1)) return true;
	}
	return false;
}

/** Owner evidence LOCAL to a key namespace (T-22 / AC-011): the `_index.parallel`
 * row is gone, but the key itself still carries owner-authored facts. Final,
 * testable predicate (the report quotes this verbatim):
 *
 *   `{agenticdocRoot}/{key}/pm-state.md` has a `- Claim-Id:` or `- Phase:`
 *   line, OR `{agenticdocRoot}/{key}/workers/<task-key>/trace.log` exists (any
 *   depth under `workers/`).
 *
 * The pm-state lines are the framework machine interface (`state-manager.ts` /
 * `advance_phase.py` write them) and `trace.log` is only ever written by a
 * worker that actually ran — both survive a lost index row.
 *
 * A bare directory holding only `task.md` files is NOT owner evidence: there is
 * no fact to reconstruct the row from, so it stays a notice-only case (T-22
 * req. 3). This predicate NEVER reads or writes `_index.parallel`; it only feeds
 * the admission decision — the scan still refuses to write any index row
 * (req. 4), so guessing a row's Phase/ClaimId/Deps is impossible by
 * construction. */
export function keyHasOwnerTraces(agenticdocRoot: string, key: string): boolean {
	const keyDir = path.join(agenticdocRoot, key);
	try {
		const pmState = fs.readFileSync(path.join(keyDir, "pm-state.md"), "utf8");
		if (/^- (?:Claim-Id|Phase):/m.test(pmState)) return true;
	} catch {
		// missing/unreadable pm-state.md — fall through to the trace scan
	}
	return hasWorkerTraceLog(path.join(keyDir, "workers"), 0);
}

// ── Owner-evidence currency (T-24 / C-30) ──────────────────────────────────

/** Freshness window for a key's own state documents (T-24/C-30): how recently
 * `pm-state.md` / `plan.md` must have moved for a claim-free repair to treat
 * the owner as still present. C-30 measured an `idle` key whose only evidence
 * was a legacy August Claim-Id and whose worker dirs were months old, yet the
 * T-22 widened admission still called it ORPHANED. */
export const OWNER_EVIDENCE_FRESH_MS = 14 * 24 * 60 * 60 * 1000;

/** The two key-level state documents a live owner writes (the framework's
 * machine interface for `pm-state.md`, the human plan for `plan.md`). */
export function keyStateDocPaths(agenticdocRoot: string, key: string): string[] {
	const keyDir = path.join(agenticdocRoot, key);
	return [path.join(keyDir, "pm-state.md"), path.join(keyDir, "plan.md")];
}

/** Verdict of {@link ownerEvidenceCurrent}. */
export interface OwnerEvidenceVerdict {
	/** True when the key's owner looks current enough to repair for (T-24 req. 2). */
	current: boolean;
	/** True when the key publishes at least one of `pm-state.md` / `plan.md`.
	 * Such a key has current-state authority: the state documents decide both
	 * which tasks are live work and whether the owner is still present. A key
	 * with neither document has nothing to narrow against, so the durable
	 * owner traces stay the only evidence (T-19/T-22 behaviour). */
	hasStateDocs: boolean;
	/** Machine-ish reason when `current` is false, used verbatim in the notice
	 * (`index 状态 idle`, `无 index 行且 pm-state 未近期更新`). */
	reason?: string;
}

/** Is a key's owner evidence still CURRENT (T-24 req. 2)? The repair path used
 * to accept any T-19 index row or T-22 owner trace, so an `idle` key carrying a
 * months-old legacy Claim-Id stayed repairable forever. Evidence is current when
 * ANY holds:
 *
 *   - the key publishes no `pm-state.md` / `plan.md` (nothing to be stale against;
 *     the durable row/trace is the only fact there is, T-19/T-22 semantics);
 *   - a state document moved within {@link OWNER_EVIDENCE_FRESH_MS};
 *   - the index row's status is not `idle` / `done` (an `active` row is a live
 *     owner; `done` is terminal and must not be repaired);
 *   - the row's claim is conductor-`live` (this host, pid alive).
 *
 * Read-only; the caller decides what to do with the verdict. */
export function ownerEvidenceCurrent(
	agenticdocRoot: string,
	key: string,
	row: IndexEntry | undefined,
	now = Date.now(),
	freshMs = OWNER_EVIDENCE_FRESH_MS,
): OwnerEvidenceVerdict {
	let hasStateDocs = false;
	for (const doc of keyStateDocPaths(agenticdocRoot, key)) {
		let stat: fs.Stats;
		try {
			stat = fs.statSync(doc);
		} catch {
			continue; // missing/unreadable — not a state document this key publishes
		}
		hasStateDocs = true;
		if (now - stat.mtimeMs <= freshMs) return { current: true, hasStateDocs };
	}
	if (!hasStateDocs) return { current: true, hasStateDocs: false };
	if (row !== undefined && row.status !== "idle" && row.status !== "done") {
		return { current: true, hasStateDocs };
	}
	if (row !== undefined && conductorClaimState(row.claimId) === "live") {
		return { current: true, hasStateDocs };
	}
	return {
		current: false,
		hasStateDocs,
		reason: row === undefined ? "无 index 行且 pm-state 未近期更新" : `index 状态 ${row.status}`,
	};
}

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
			const idx = existing.findIndex((e) => normalizeKey(e.key) === normalizeKey(entry.key));
			if (idx >= 0) {
				// Keep the first-seen casing of the stored row: reads are
				// case-insensitive, writes must not rewrite existing rows (A6).
				existing[idx] = { ...entry, key: existing[idx].key };
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
			// Key name gate (AC-006): reserved/illegal names never reach the rows,
			// so `claim('_tmp')` / `claim('_index.parallel')` cannot create an active
			// row in a framework namespace. `_scratch` is refused here too: usable as
			// an owner key, never claimable.
			const nameRefusal = keyNameRefusal(key);
			if (nameRefusal) {
				return {
					ok: false,
					entry: { key, status: "idle", phase: "", claimId: "", deps: "", desc: "", updated: "" },
					created: false,
					refusal: nameRefusal.code,
				};
			}
			const rows = this.readAll();
			const idx = rows.findIndex((e) => normalizeKey(e.key) === normalizeKey(key));
			const existing = rows[idx];
			if (existing && existing.claimId !== self && heldLive(existing.claimId) && !force) {
				return { ok: false, blockedBy: existing.claimId, entry: existing, created: false };
			}
			const now = new Date().toISOString();
			if (demoteOthers) {
				for (let i = 0; i < rows.length; i++) {
					if (rows[i].status === "active" && normalizeKey(rows[i].key) !== normalizeKey(key)) {
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
			// Observability (design-role-key-identity §5.1 / DD-07d): the claim hit a
			// stored row whose bytes differ from the request only by case. The claim
			// still resolves to that row (no migration, no duplicate), but the caller
			// must be able to SEE the substitution instead of silently owning a row
			// under a different spelling. `takeOverKey` turns this into an audit line.
			const requested = key.trim();
			const caseVariantOf =
				existing && existing.key !== requested && existing.key.toLowerCase() === requested.toLowerCase()
					? existing.key
					: undefined;
			return { ok: true, entry: after, created: !existing, ...(caseVariantOf ? { caseVariantOf } : {}) };
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
		// Case-insensitive (A6): the first stored row with the same normalized key
		// wins; a caller passing a case variant gets the row the guard sees too.
		return this.readAll().find((e) => normalizeKey(e.key) === normalizeKey(key));
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
	/** Present when ok=false and the refusal was the key NAME itself (AC-006):
	 * stable {@link keyNameRefusal} code (`reserved-key-name`,
	 * `key-illegal-shape`, `key-path-escape`, `empty-key`). */
	refusal?: string;
	/** Present when ok=true and the request hit an existing row that differs
	 * from it only by case (A6): the stored, first-written spelling. The claim
	 * resolves to that row -- this field exists so the substitution is auditable
	 * rather than silent. */
	caseVariantOf?: string;
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
