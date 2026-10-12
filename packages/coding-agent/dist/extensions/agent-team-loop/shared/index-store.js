import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "./file-lock.js";
import { SCRATCH_WORKERS_KEY } from "./paths.js";
// ── Key identity (AC-006 / RQ-5) ────────────────────────────────────────────
/** Reserved `.agenticdoc/` root entries that name framework files/dirs, not
 * AgenticTask key namespaces: the 12 names from RQ-5 plus `_impl_gate.log`
 * (`shared/implementation-gate.ts` writes it) and `_incidents`. This is an
 * EXPLICIT list, deliberately not a `_`/`.` prefix rule (the pre-AC-006
 * exemption): a prefix rule would also exempt `_tmp`, `.mw` and
 * `_index.parallel` from the cross-key guard and let a dispatch with
 * `key: _index.parallel` create `.agenticdoc/_index.parallel/workers/`. */
export const RESERVED_INDEX_NAMES = [
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
export const RESERVED_INDEX_NAME_SET = new Set(RESERVED_INDEX_NAMES);
/** Comparison form of a key: trimmed and lower-cased. Windows filesystems are
 * case-insensitive, so `MW-KEY` and `mw-key` name the SAME directory — the key
 * namespace must be case-insensitive too (A6). Reads normalize; writes keep
 * the first-seen casing so existing `_index.parallel` bytes are never
 * rewritten by a read (no migration). */
export function normalizeKey(key) {
    return key.trim().toLowerCase();
}
/** True for `_scratch` and its case variants — the only reserved name that is
 * still usable as an owner key (never as a claimable/advanceable key). */
export function isScratchKey(key) {
    return normalizeKey(key) === normalizeKey(SCRATCH_WORKERS_KEY);
}
/** Shape of a usable key name: alnum first char, then alnum / `.` / `_` / `-`. */
const KEY_SHAPE_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const KEY_MAX_LENGTH = 64;
/** Shape + reserved-name gate shared by the cross-key guard, `IndexStore.claim`
 * and `advance_phase` (AC-006/DD-07a/DD-07b): `null` = usable key name. Every
 * other return refuses the name unconditionally, independent of claim state,
 * so no caller can bootstrap a namespace next to a framework file. */
export function keyNameRefusal(key) {
    const trimmed = key.trim();
    if (!trimmed)
        return { code: "empty-key", message: "the key is empty" };
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
const INDEX_COLS = 7;
function parseIndexLine(line) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#"))
        return undefined;
    let parts;
    // AgenticTask format: "| key | status | ... | updated |" — 9 split-by-| parts (empty outer)
    // Bare format: "key | status | ... | updated" — 7 parts
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
        parts = trimmed
            .slice(1, -1)
            .split("|")
            .map((s) => s.trim());
    }
    else {
        parts = trimmed.split("|").map((s) => s.trim());
    }
    if (parts.length !== INDEX_COLS)
        return undefined;
    const [key, status, phase, claimId, deps, desc, updated] = parts;
    if (!key || key.startsWith("#") || key.startsWith("-") || key === "Key" || key.startsWith("---"))
        return undefined;
    return {
        key,
        status: (status ?? "idle"),
        phase: phase ?? "",
        claimId: claimId ?? "",
        deps: deps ?? "",
        desc: desc ?? "",
        updated: updated ?? "",
    };
}
function serializeIndexLine(entry) {
    // Write in AgenticTask format so the external indexer can read rows back
    return `| ${[entry.key, entry.status, entry.phase, entry.claimId, entry.deps, entry.desc, entry.updated].join(" | ")} |`;
}
export class IndexStore {
    filePath;
    lockPath;
    constructor(agenticdocRoot) {
        this.filePath = path.join(agenticdocRoot, "_index.parallel");
        this.lockPath = path.join(agenticdocRoot, "..", ".mw", "index.lock");
    }
    readAll() {
        if (!fs.existsSync(this.filePath))
            return [];
        const lines = fs.readFileSync(this.filePath, "utf8").split("\n");
        return lines.map(parseIndexLine).filter((e) => e !== undefined);
    }
    async upsert(entry) {
        const release = await acquireLock(this.lockPath);
        try {
            const existing = this.readAll();
            const idx = existing.findIndex((e) => normalizeKey(e.key) === normalizeKey(entry.key));
            if (idx >= 0) {
                // Keep the first-seen casing of the stored row: reads are
                // case-insensitive, writes must not rewrite existing rows (A6).
                existing[idx] = { ...entry, key: existing[idx].key };
            }
            else {
                existing.push(entry);
            }
            this.writeRows(existing);
        }
        finally {
            release();
        }
    }
    /** Atomically claim `key` for `self`: liveness check, optional demote of
     * other active rows, upsert, and a post-write disk verification — all
     * under ONE lock acquisition, so racing windows cannot both walk away
     * believing they hold the claim. `heldLive` decides whether a foreign
     * claim blocks us (ui-bridge claimState; injected to keep this store free
     * of host/os dependencies). */
    async claim(key, self, heldLive, opts = {}) {
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
            const claimed = existing
                ? {
                    ...existing,
                    claimId: self,
                    updated: now,
                    ...(activate ? { status: "active" } : {}),
                }
                : { key, status: "active", phase: "SPEC", claimId: self, deps: "", desc: "", updated: now };
            if (idx >= 0)
                rows[idx] = claimed;
            else
                rows.push(claimed);
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
            const caseVariantOf = existing && existing.key !== requested && existing.key.toLowerCase() === requested.toLowerCase()
                ? existing.key
                : undefined;
            return { ok: true, entry: after, created: !existing, ...(caseVariantOf ? { caseVariantOf } : {}) };
        }
        finally {
            release();
        }
    }
    /** Serialize rows back to _index.parallel, preserving AgenticTask header
     * lines. Callers must hold the index lock. */
    writeRows(rows) {
        // Preserve AgenticTask header lines: "# Index Parallel", "| Key | ... |", "| --- | ... |"
        let header = "";
        if (fs.existsSync(this.filePath)) {
            const raw = fs.readFileSync(this.filePath, "utf8");
            const headerLines = [];
            for (const l of raw.split("\n")) {
                const t = l.trim();
                if (t.startsWith("#") || t.startsWith("| Key") || t.startsWith("| ---") || t.startsWith("|---")) {
                    headerLines.push(l);
                }
                else {
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
    findByKey(key) {
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
    activeEntry() {
        let best;
        let bestTs = Number.NEGATIVE_INFINITY;
        for (const e of this.readAll()) {
            if (e.status !== "active")
                continue;
            const parsed = Date.parse(e.updated);
            const ts = Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
            if (!best || ts >= bestTs) {
                best = e;
                bestTs = ts;
            }
        }
        return best;
    }
    activeKey() {
        return this.activeEntry()?.key;
    }
}
/** Read the degraded-mode `active:` pointer from `_index.md`. Fallback for
 * owner-key resolution when `_index.parallel` has no active row. Returns
 * undefined when the file or the line is missing. */
export function readIndexMdActive(agenticdocRoot) {
    const mdPath = path.join(agenticdocRoot, "_index.md");
    if (!fs.existsSync(mdPath))
        return undefined;
    for (const line of fs.readFileSync(mdPath, "utf8").split("\n")) {
        const m = /^active:\s*(\S+)/u.exec(line.trim());
        if (m)
            return m[1];
    }
    return undefined;
}
//# sourceMappingURL=index-store.js.map