import * as fs from "node:fs";
import * as path from "node:path";
import { TERMINAL_WORKER_STATUSES } from "../autopilot/status-model.js";
import { RAG_MARKER_V1, renderRagBlock } from "../rag/block.js";
import { loadRagConfig } from "../rag/config.js";
import { acquireLock } from "../shared/file-lock.js";
import { controlRootFromTaskPath } from "../shared/paths.js";
import { renderToolchainCommand, resolveWorkspaceConfig } from "../shared/target-config.js";
import { readTaskHeaderScalar, readTaskType } from "../shared/task-frontmatter.js";
import { workerOwnerKey } from "../shared/worker-store.js";
import { parseWriteFace, writeFacesOverlap } from "../shared/write-face.js";
/** Sentinel opening the legacy (dual/single) profile block — makes
 * re-dispatch idempotent (the block is appended at most once per task.md).
 * Dual/single keep this marker and its rendered text byte-identical
 * (mw-target-partition AC-016d: the golden d baseline was recorded against
 * the v1 marker; the v2 marker is partition-only). */
const PROFILE_MARK = "<!-- mw-profile: v1 -->";
/** v2 marker (mw-target-partition D-005): a partition block carries an
 * explicit mode line right under the marker — the anchor both the
 * launcher's tear check (AC-020) and the switch-replacement boundary
 * (AC-019) read. */
const PROFILE_MARK_V2 = "<!-- mw-profile: v2 -->";
/** Does the resolved config carry anything worth injecting? Dual mode
 * alone qualifies: the control-root path is the key fact for a worker whose
 * cwd is the game root (D-005). Sections missing → their block is skipped
 * without blocking the dispatch (AC-007). */
function hasProfileContent(config) {
    return (config.mode === "dual" ||
        Object.keys(config.toolchain).length > 0 ||
        config.ignore.deny_globs.length > 0 ||
        config.contract.forbidden_paths.length > 0 ||
        config.contract.conventions !== null ||
        config.contract.docs.length > 0);
}
/** Render the workspace-profile essentials (AC-007: 要点, not the full file).
 * Line prefixes are deliberately not `key:`-shaped so the worker's
 * whole-file frontmatter scan (parseTaskMd) never misreads them.
 * `ignoreEnforced=false` (the task carries its own deny_globs) skips the
 * firewall section — rendering the yml defaults there would claim an
 * enforcement that is not active for this task. */
function renderProfileBlock(config, ignoreEnforced) {
    const lines = [
        PROFILE_MARK,
        "[mw] Workspace profile (target.yml essentials, injected at dispatch;",
        `full file: ${path.join(config.controlRoot, ".agenticdoc", "target.yml")})`,
    ];
    if (config.mode === "dual") {
        lines.push(`Control workspace: ${config.controlRoot}`);
        lines.push(`Game root: ${config.gameRoot}`);
        if (config.engineRoot !== null)
            lines.push(`Engine root: ${config.engineRoot}`);
    }
    const toolNames = Object.keys(config.toolchain);
    if (toolNames.length > 0) {
        lines.push("Toolchain commands (placeholders resolved):");
        for (const name of toolNames) {
            // Fail-closed render (AC-004): a referenced-but-unconfigured root
            // throws and the dispatch is refused — never a half-resolved command.
            lines.push(`- ${name}: ${renderToolchainCommand(config.toolchain[name], config)}`);
        }
    }
    if (ignoreEnforced && config.ignore.deny_globs.length > 0) {
        lines.push("Context firewall (deny globs, enforced by the read-scope layer):");
        for (const glob of config.ignore.deny_globs)
            lines.push(`- ${glob}`);
    }
    const contract = config.contract;
    if (contract.forbidden_paths.length > 0 || contract.conventions !== null || contract.docs.length > 0) {
        lines.push("Contract:");
        if (contract.forbidden_paths.length > 0) {
            lines.push(`- forbidden paths: ${contract.forbidden_paths.join(", ")}`);
        }
        if (contract.conventions !== null) {
            lines.push("- conventions:");
            for (const line of contract.conventions.split("\n"))
                lines.push(`  ${line}`);
        }
        if (contract.docs.length > 0) {
            lines.push("- docs (references, not inlined):");
            for (const doc of contract.docs)
                lines.push(`  - ${path.resolve(config.controlRoot, doc)}`);
        }
    }
    return lines.join("\n");
}
/** Locate the (single) profile block in a task.md: the index of the
 * earliest marker of either version — the replacement boundary (AC-019:
 * marker line to end of file, so a corrupt double block also clears
 * wholesale). */
function findProfileBlock(content) {
    const v1 = content.indexOf(PROFILE_MARK);
    const v2 = content.indexOf(PROFILE_MARK_V2);
    if (v1 === -1 && v2 === -1)
        return null;
    if (v2 === -1)
        return v1;
    if (v1 === -1)
        return v2;
    return Math.min(v1, v2);
}
/** Drop the `<!-- mw-rag: v1 -->` block (marker line to EOF) from a task.md,
 * collapsing the tail whitespace to a single newline. The RAG block is always
 * the last block, so this re-anchors the profile boundary cleanly. */
function stripRagBlock(content) {
    const index = content.indexOf(RAG_MARKER_V1);
    if (index === -1)
        return content;
    return content.slice(0, index).replace(/\s+$/, "\n");
}
/** Positive-integer task.md header (`<header>      12`). */
function headerInt(content, header) {
    const match = new RegExp(`^${header}[ \\t]*(\\d+)[ \\t]*$`, "m").exec(content);
    if (match === null)
        return undefined;
    const value = Number(match[1]);
    return Number.isFinite(value) && value > 0 ? value : undefined;
}
/** Task metadata `renderRagBlock` needs, read from the task.md frontmatter.
 * `type:`/`phase:` go through the single-source header parser (AC-005): the
 * old `/^type:/m` and `/^phase:/m` regexes read the whole file, so a body line
 * could inject a header key into the RAG render. */
function parseRagTaskMeta(content) {
    return {
        type: readTaskType(content).type,
        phase: readTaskHeaderScalar(content, "phase"),
        chatBudget: headerInt(content, "rag_chat_budget:"),
        timeBudgetS: headerInt(content, "rag_time_budget_s:"),
    };
}
/** AC-019/FIX-2 freshness predicate: an existing block is fresh exactly
 * when it is byte-identical to what the current config renders — the
 * render is a pure function of the config, so a same-config re-dispatch is
 * byte-stable (AC-007 idempotency) while ANY config change under the same
 * mode (parent/partition/roots paths, toolchain, firewall, contract)
 * produces a different block and the stale one is replaced wholesale
 * (marker line to EOF). The firewall arm is rendered both ways because
 * that section depends on whether the task file already carries a
 * deny_globs line: a first dispatch inserts the line AND renders the
 * section, so both renders must count as fresh for the re-dispatch to
 * stay byte-identical. A config with nothing to inject (parked single)
 * renders no block at all — any existing block is stale and gets dropped. */
function blockIsFresh(existingText, config) {
    if (config.mode === "partition") {
        return (existingText === `${renderPartitionProfileBlock(config, true)}\n` ||
            existingText === `${renderPartitionProfileBlock(config, false)}\n`);
    }
    if (!hasProfileContent(config))
        return false;
    return (existingText === `${renderProfileBlock(config, true)}\n` ||
        existingText === `${renderProfileBlock(config, false)}\n`);
}
/** Render the partition workspace profile (mw-target-partition D-005,
 * AC-007): v2 marker + explicit mode line, then the same essentials shape
 * as the dual block — parent/partition/named roots replace the game/engine
 * lines (partition has neither). The toolchain/firewall/contract sections
 * are intentionally duplicated from renderProfileBlock rather than shared:
 * the dual render is frozen byte-exact by the AC-016d golden. The full-file
 * line always names target.yml (the single config file). */
function renderPartitionProfileBlock(config, ignoreEnforced) {
    const lines = [
        PROFILE_MARK_V2,
        `[mw] mode: ${config.mode}`,
        "[mw] Workspace profile (target.yml essentials, injected at dispatch;",
        `full file: ${path.join(config.controlRoot, ".agenticdoc", "target.yml")})`,
        `Control workspace: ${config.controlRoot}`,
        `Parent root (extended workspace, writable): ${config.parentRoot}`,
        `Partition root (worker cwd): ${config.partitionRoot}`,
    ];
    const roots = config.roots ?? {};
    if (Object.keys(roots).length > 0) {
        lines.push("Named roots:");
        for (const [name, root] of Object.entries(roots))
            lines.push(`- ${name}: ${root}`);
    }
    const toolNames = Object.keys(config.toolchain);
    if (toolNames.length > 0) {
        lines.push("Toolchain commands (placeholders resolved):");
        for (const name of toolNames) {
            // Fail-closed render (AC-004): an undefined placeholder throws and
            // the dispatch is refused — never a half-resolved command.
            lines.push(`- ${name}: ${renderToolchainCommand(config.toolchain[name], config)}`);
        }
    }
    if (ignoreEnforced && config.ignore.deny_globs.length > 0) {
        lines.push("Context firewall (deny globs, enforced by the read-scope layer):");
        for (const glob of config.ignore.deny_globs)
            lines.push(`- ${glob}`);
    }
    const contract = config.contract;
    if (contract.forbidden_paths.length > 0 || contract.conventions !== null || contract.docs.length > 0) {
        lines.push("Contract:");
        if (contract.forbidden_paths.length > 0) {
            lines.push(`- forbidden paths: ${contract.forbidden_paths.join(", ")}`);
        }
        if (contract.conventions !== null) {
            lines.push("- conventions:");
            for (const line of contract.conventions.split("\n"))
                lines.push(`  ${line}`);
        }
        if (contract.docs.length > 0) {
            lines.push("- docs (references, not inlined):");
            for (const doc of contract.docs)
                lines.push(`  - ${path.resolve(config.controlRoot, doc)}`);
        }
    }
    return lines.join("\n");
}
/** Insert the deny_globs block into a task.md. When the file opens with a
 * `---` frontmatter pair, the block goes before the closing marker (same
 * shape as dispatch.py's renderer); otherwise it is prepended — the worker
 * parser scans the whole file, not just the frontmatter. An existing
 * `deny_globs:` line (task-level override) is never touched. */
function insertDenyGlobs(content, denyGlobs) {
    const block = ["deny_globs:", ...denyGlobs.map((g) => `  - '${g}'`)].join("\n");
    const lines = content.split("\n");
    if (lines[0]?.trim() === "---") {
        const close = lines.findIndex((line, i) => i > 0 && line.trim() === "---");
        if (close !== -1) {
            lines.splice(close, 0, block);
            return lines.join("\n");
        }
    }
    return `${block}\n${content}`;
}
/** Inject the workspace profile into a task.md at dispatch time (AC-007:
 * the worker reads task.md only — it never needs to know target.yml exists).
 * Throws TargetConfigError on an unusable target.yml (fail-closed: the
 * caller must refuse the dispatch, never queue an un-injected task.md).
 * An unreadable task.md skips injection (warned) — the queue row still
 * lands and the launcher's own task-file validation fails visibly.
 *
 * Marker semantics (mw-target-partition D-005): dual/single render the v1
 * marker exactly as before; partition renders the v2 marker + mode line.
 * Re-dispatch is idempotent while the existing block is byte-identical to
 * what the current config renders (FIX-2: staleness is content-based, not
 * mode-only — any same-mode config change replaces the block too); when
 * the block no longer matches, it is replaced wholesale from its marker
 * line to EOF (AC-019) — including a v1-marked legacy block under partition
 * activation, and a drop to nothing under a non-injecting mode (parked
 * single restores the pre-injection bytes). */
function injectWorkspaceProfile(taskPath) {
    const controlRoot = controlRootFromTaskPath(taskPath);
    const config = resolveWorkspaceConfig(controlRoot);
    let original;
    try {
        original = fs.readFileSync(taskPath, "utf8");
    }
    catch (err) {
        console.error(`[mw] profile injection skipped for ${taskPath}: ${err instanceof Error ? err.message : String(err)}`);
        return;
    }
    // The RAG block is the last block (marker line to EOF), so strip it before
    // the profile replacement boundary (also marker -> EOF) is computed, then
    // re-append the freshly rendered block at the very end. This keeps both
    // blocks idempotent under re-dispatch and drops a stale RAG block when the
    // project no longer enables RAG (D-009).
    const base = stripRagBlock(original);
    const existing = findProfileBlock(base);
    const ownDenyGlobs = /^deny_globs:/m.test(base);
    let out = base;
    const profileFresh = existing !== null && blockIsFresh(base.slice(existing).replace(/\s+$/, "\n"), config);
    if (!profileFresh) {
        // Stale block: drop everything from its marker line (AC-019 wholesale
        // replacement — a mode switch, any same-mode config change, or a switch
        // to a non-injecting mode (parked single) that restores the pre-injection
        // bytes); fresh dispatch: anchor at the original content. The tail
        // collapses to a single newline so the replacement re-anchors cleanly.
        out = existing !== null ? base.slice(0, existing).replace(/\s+$/, "\n") : base;
        if (config.ignore.deny_globs.length > 0 && !ownDenyGlobs) {
            out = insertDenyGlobs(out, config.ignore.deny_globs);
        }
        if (config.mode === "partition") {
            // Partition always injects: the parent/partition roots are the key
            // facts for a worker whose cwd is the partition root (D-005).
            out = `${out.replace(/\s+$/, "\n")}\n${renderPartitionProfileBlock(config, !ownDenyGlobs)}\n`;
        }
        else if (hasProfileContent(config)) {
            out = `${out.replace(/\s+$/, "\n")}\n${renderProfileBlock(config, !ownDenyGlobs)}\n`;
        }
    }
    // Zero-impact when disabled: renderRagBlock returns null and writes not one
    // byte (D-014/AC-001).
    const ragBlock = renderRagBlock(loadRagConfig(controlRoot), parseRagTaskMeta(base));
    if (ragBlock !== null)
        out = `${out.replace(/\s+$/, "")}\n\n${ragBlock}\n`;
    if (out !== original)
        fs.writeFileSync(taskPath, out, "utf8");
}
export async function dispatchTask(entry, store) {
    const now = new Date().toISOString();
    const full = {
        ...entry,
        dispatchedAt: now,
        updatedAt: now,
    };
    // The judgement, the profile injection and the row write share ONE
    // `.mw/workers.lock` critical section (D-005/AC-014), anchored on the SAME
    // queue/lock paths this store was constructed with (so the call site cannot
    // drift from `worker-store.ts`). `WorkerStore.upsert` may NOT be called
    // while this lock is held (a nested `acquireLock` backs off for 14.6h then
    // raises, RQ-D3), so the row write goes through the store's own lock-free
    // entry point (D-114: one writer implementation, no byte-mirror).
    const base = writeFaceBase(path.dirname(store.queuePath));
    const caseInsensitive = writeFaceCaseInsensitive();
    const release = await acquireLock(store.lockFilePath);
    try {
        let content = "";
        try {
            content = fs.readFileSync(entry.taskPath, "utf8");
        }
        catch {
            // Unreadable task.md is "no information" (undeclared), never a
            // guessed face (D-003).
        }
        const refusal = writeFaceVerdict({ entry, content, store, base, caseInsensitive });
        if (refusal !== null)
            return refusal;
        injectWorkspaceProfile(entry.taskPath);
        store.upsertWithinLock(full);
    }
    finally {
        release();
    }
    return { ok: true };
}
/** Base for every write-face parse: the `.agenticdoc` parent — the same root
 * `WorkerStore` anchors its queue under. Given at the call site, never
 * inferred inside the operator (D-006/AC-007; mirrors
 * `dispatch.py::write_face_base`). */
export function writeFaceBase(agenticdocRoot) {
    return path.resolve(agenticdocRoot, "..");
}
/** Explicit case mode for the write-face operator (D-006/AC-007): mirrors
 * `dispatch.py::write_face_case_insensitive` (`os.name == "nt"`). */
export function writeFaceCaseInsensitive() {
    return process.platform === "win32";
}
/** The in-flight worker's own task.md `write_face:` head, or `null` when it is
 * missing / unreadable / undeclared — a side that did not declare cannot prove
 * an overlap (D-003; mirrors `dispatch.py::_parse_inflight_write_face`). */
function parseInflightWriteFace(taskPath, base, caseInsensitive) {
    if (taskPath.trim() === "")
        return null;
    let text;
    try {
        text = fs.readFileSync(taskPath, "utf8");
    }
    catch {
        return null;
    }
    const parsed = parseWriteFace(text, { base, caseInsensitive });
    return parsed.kind === "declared" ? parsed.face : null;
}
/** D-001..D-008 gate, called INSIDE the `workers.lock` critical section.
 * Returns `null` to proceed, or a zero-side-effect refusal. The in-flight set
 * is recomputed in place from the live queue (AC-008; no queue column is
 * added) using the single owner predicate and the single terminal-status set. */
function writeFaceVerdict(input) {
    const taskKey = input.entry.taskKey;
    const parsed = parseWriteFace(input.content, { base: input.base, caseInsensitive: input.caseInsensitive });
    // A card-backed dispatch carries `card_path:`; a hand-written internal /
    // orphan task does not. Only a card-backed undeclared face is held
    // serial-only — a card-less dispatch has no author surface to fix, so
    // refusing it would manufacture a permanent stall (dispatch.py
    // `_write_face_verdict` card-less exemption).
    const cardBacked = (readTaskHeaderScalar(input.content, "card_path") ?? "") !== "";
    const ownerKey = workerOwnerKey({ taskPath: input.entry.taskPath });
    // `workerOwnerKey` is "" when the task path is not under
    // `.agenticdoc/<key>/workers/` (the contract an unanchored path violates).
    // An unknown owner cannot establish a same-owner set, and grouping every
    // unknown under "" would invent overlap that is not provable — the same
    // direction as D-003 (no information is not evidence of a conflict).
    const inFlight = ownerKey === ""
        ? []
        : input.store
            .readQueue()
            .rows.filter((row) => row.taskKey !== taskKey &&
            workerOwnerKey(row) === ownerKey &&
            !TERMINAL_WORKER_STATUSES.has(row.status));
    if (parsed.kind === "rejected") {
        // `reason` mirrors the conductor's `DispatchResult.reason`
        // (`dispatch.py:1169`: `f"{code}: {detail}"`), so the PM audit line
        // derived from it (`writeFaceRefusalDetail` ->
        // `.agenticdoc/_autopilot/auto-decisions.jsonl`) carries the same
        // refusal detail as the conductor's `timeline.jsonl` event. `detail`
        // keeps the conductor's timeline shape (`_write_face_audit`:
        // `"<task_key>: <code> <detail>"`). Both degrade to the bare `code`
        // when the operator supplies no detail — never `"code: undefined"`.
        const tail = parsed.detail === undefined ? "" : ` ${parsed.detail}`;
        return {
            ok: false,
            code: parsed.code,
            reason: parsed.detail === undefined ? parsed.code : `${parsed.code}: ${parsed.detail}`,
            detail: `${taskKey}: ${parsed.code}${tail}`,
        };
    }
    if (parsed.kind === "undeclared") {
        // D-003: an undeclared card-backed face is serial-only. With no same-owner
        // worker in flight there is nothing to serialize against, so the dispatch
        // proceeds (byte-identical to the pre-gate flow).
        if (inFlight.length === 0 || !cardBacked)
            return null;
        return {
            ok: false,
            code: "write-face-undeclared",
            serialOnly: true,
            inFlight: inFlight.length,
            reason: `write-face-undeclared: serial-only (${inFlight.length} same-owner worker(s) in flight)`,
            detail: `${taskKey}: write_face undeclared; ${inFlight.length} same-owner worker(s) in flight`,
        };
    }
    for (const row of inFlight) {
        const otherFace = parseInflightWriteFace(row.taskPath, input.base, input.caseInsensitive);
        if (otherFace === null)
            continue; // D-003: cannot prove an overlap
        const result = writeFacesOverlap(parsed.face, otherFace);
        if (result === null)
            continue;
        if ("unsupported" in result) {
            // D-006 conservative fallback: an undecidable pair IS an overlap.
            return {
                ok: false,
                code: "write-face-overlap",
                overlapWith: row.taskKey,
                reason: `write-face-overlap: overlap-with:${row.taskKey} unsupported=${result.unsupported}`,
                detail: `${taskKey}: undecidable overlap with ${row.taskKey} (${result.unsupported}) treated as overlap`,
            };
        }
        return {
            ok: false,
            code: "write-face-overlap",
            overlapWith: row.taskKey,
            sample: result.sample,
            reason: `write-face-overlap: overlap-with:${row.taskKey} sample=${result.sample}`,
            detail: `${taskKey}: overlap with ${row.taskKey} at ${result.sample} (${result.rule} vs ${result.other})`,
        };
    }
    return null;
}
//# sourceMappingURL=task-dispatcher.js.map