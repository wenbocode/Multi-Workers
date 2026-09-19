import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Type } from "typebox";
import { runAgenticScript } from "../shared/agentic-scripts.js";
import { acquireLock } from "../shared/file-lock.js";
import { formatHeartbeatAge, HEARTBEAT_STALE_MS, readTaskProgress } from "../shared/heartbeat.js";
import { readIndexMdActive } from "../shared/index-store.js";
import { buildMw, doctorMw, getMwStatus, initMw, modelMw, partitionMw, restartMw, serveStaleness, startMw, stopMw, targetMw, } from "../shared/mw-runner.js";
import { SCRATCH_WORKERS_KEY, workerTaskDir } from "../shared/paths.js";
import { DOC_GATE_HINT, dispatchDocGaps, formatDocsBadge, readPhaseDocs } from "../shared/phase-docs.js";
import { PHASE_ORDER, phaseAuditWarnings } from "../shared/pm-state-guard.js";
import { headline } from "../worker/output-writer.js";
import { dispatchTask } from "./task-dispatcher.js";
/** Owner key for a worker task — this window's own claim first, the shared
 * active pointer second. Explicit key wins (deliberate choice — no warning).
 * Otherwise, when this window watches a key whose _index.parallel row it
 * holds (claimId === this window's host:pid), dispatches land under that key
 * even when another window's later takeover made a different row the
 * globally-latest active one: single-active demote flips the shared pointer
 * between windows, but ownership does not move. A stale or foreign watch
 * (no claim held) falls back to the global active row — but never one held
 * live by another window (injecting work into another window's key is the
 * cross-window dispatch bug this guards); that case degrades to _scratch
 * with a warning. Then the degraded _index.md `active:` pointer, then
 * _scratch. */
export function resolveOwnerKeyWithSync(pi, indexStore, watch, explicit, agenticdocRoot) {
    const explicitKey = (explicit ?? "").trim();
    if (explicitKey)
        return explicitKey;
    const self = windowClaimId();
    if (watch.key) {
        // _scratch is watchable but never indexed; a window watching it means
        // its ad-hoc dispatches belong there.
        if (watch.key === SCRATCH_WORKERS_KEY)
            return watch.key;
        if (indexStore.findByKey(watch.key)?.claimId === self)
            return watch.key;
    }
    const active = indexStore.activeEntry();
    if (active && claimState(active.claimId, self) === "held-live") {
        warnForeignActiveOnce(pi, active.key);
        return SCRATCH_WORKERS_KEY;
    }
    const owner = active?.key ?? readIndexMdActive(agenticdocRoot) ?? SCRATCH_WORKERS_KEY;
    if (watch.key && watch.key !== owner)
        warnOwnerMismatchOnce(pi, watch.key, owner);
    return owner;
}
/** Warned (watch -> owner) pairs this session. displaySummary persists the
 * warning to the transcript (LLM-visible), so once per pair is enough. */
const warnedOwnerMismatches = new Set();
function warnOwnerMismatchOnce(pi, watchKey, ownerKey) {
    const pair = `${watchKey}->${ownerKey}`;
    if (warnedOwnerMismatches.has(pair))
        return;
    warnedOwnerMismatches.add(pair);
    displaySummary(pi, `[mw] owner-key mismatch: this window watches '${watchKey}' but holds no claim on it, and the active key is '${ownerKey}' — ` +
        `dispatching under '${ownerKey}'. Run /pm-key switch ${ownerKey} to align the window.`);
}
/** Warned foreign active keys this session (same once-per-pair rationale as
 * warnedOwnerMismatches). */
const warnedForeignActives = new Set();
function warnForeignActiveOnce(pi, activeKey) {
    if (warnedForeignActives.has(activeKey))
        return;
    warnedForeignActives.add(activeKey);
    displaySummary(pi, `[mw] active key '${activeKey}' is claimed by another live window — not dispatching under it; ` +
        `using '${SCRATCH_WORKERS_KEY}' instead. Pass an explicit key, or switch_key in this window first.`);
}
export function displaySummary(pi, summary) {
    pi.sendMessage({
        customType: "agent-team-loop:worker-summary",
        content: summary,
        display: true,
        details: summary,
    });
}
/** Deliver a message into the conversation AND trigger a PM turn — the
 * shared "wake the PM" channel (finish calls and mid-run escalations).
 * `pi.sendMessage` without `triggerTurn` only injects the message into LLM
 * context: it displays in the transcript, but an idle PM never wakes up.
 * With `triggerTurn: true` an idle PM starts an LLM turn immediately; a
 * streaming PM gets the text steered into the current turn. Informational
 * notices (init, mw start, gate skips) stay passive via displaySummary —
 * they must not spend agent turns. */
export function deliverPmAlert(pi, text) {
    pi.sendMessage({
        customType: "agent-team-loop:worker-summary",
        content: text,
        display: true,
        details: text,
    }, { triggerTurn: true });
}
/** Deliver a terminal worker result (the "finish call" of dispatch →
 * monitor → finish call → pm run). See deliverPmAlert for the channel. */
export function deliverWorkerResult(pi, summary) {
    deliverPmAlert(pi, summary);
}
/** Session entry type persisting this window's watched key across restarts. */
export const WATCH_ENTRY_TYPE = "agent-team-loop:watch";
// ── Window claim identity (_index.parallel claimId) ─────────────────────────
/** This window's claim identity: host:pid. Written into _index.parallel so
 * another window can tell whether a key's claim is still held by a live
 * process (pid check) before taking it over. */
export function windowClaimId() {
    return `${os.hostname()}:${process.pid}`;
}
/** Parse a `host:pid` claim; anything else (e.g. legacy timestamp claims) is
 * unparseable and treated as stale. */
function parseClaim(claimId) {
    const m = claimId.match(/^([^:]+):(\d+)$/);
    if (!m)
        return undefined;
    const pid = Number(m[2]);
    if (!Number.isInteger(pid) || pid <= 0)
        return undefined;
    return { host: m[1] ?? "", pid };
}
function isPidAlive(pid) {
    try {
        process.kill(pid, 0);
        return true;
    }
    catch (err) {
        // EPERM: process exists but is not ours — still alive. ESRCH: gone.
        return err.code === "EPERM";
    }
}
/** Whether a key's claim blocks a takeover. "held-live" = another live window
 * (or a foreign host we cannot verify) holds it and --force is required. */
export function claimState(claimId, self) {
    const trimmed = claimId.trim();
    if (!trimmed || trimmed === self)
        return "free";
    const c = parseClaim(trimmed);
    if (!c)
        return "free"; // legacy/unparseable claim — stale
    if (c.host !== os.hostname())
        return "held-live"; // cannot verify liveness
    return isPidAlive(c.pid) ? "held-live" : "held-stale";
}
/** Claim a key for this window — shared by /pm-key switch, /pm-key new and
 * the spec-write auto-takeover. Routes through IndexStore.claim so the
 * liveness check, demote, and write are one atomic step under the index
 * lock: racing windows cannot both believe they claimed. Also runs the
 * phase-chain audit on success (audit_phase.py's TS-side mirror). */
export async function takeOverKey(indexStore, key, force, agenticdocRoot) {
    const self = windowClaimId();
    const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", { force });
    const audit = outcome.ok ? phaseAuditWarnings(agenticdocRoot, key, outcome.entry.phase) : [];
    return { ok: outcome.ok, blockedBy: outcome.blockedBy, claimId: self, created: outcome.created, audit };
}
const WATCH_WIDGET_KEY = "agent-team-loop-watch";
/** History rows kept in the widget (D-003): done rows and acked terminal
 * rows are processed history — newest five shown, the rest folded into
 * `+N more`. Live (running/pending) and unhandled (failed/nc awaiting ack)
 * rows are never folded. */
const WATCH_HISTORY_MAX = 5;
const WATCH_LINE_MAX = 110;
const STATUS_GLYPH = {
    pending: ".",
    running: ">",
    done: "+",
    failed: "x",
    "needs-clarification": "?",
};
function trunc(s, max) {
    return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}
/** Owner key of a queue row: the first taskPath segment below the agenticdoc
 * root ({key}/workers/<task>/task.md → key). Legacy root-level rows resolve to
 * their own task key and simply never match a watched key. */
export function ownerKeyOf(entry, agenticdocRoot) {
    const rel = path.relative(agenticdocRoot, path.normalize(entry.taskPath));
    return rel.split(path.sep)[0] ?? "";
}
/** Body of a `## <section>` block in output.md (first match), trimmed;
 * undefined when the file or section is missing. Generic reader behind
 * readOutputSummary and the terminal-detail fallback chains (D-004): `##
 * TL;DR`, `## Exit Reason`, `## Questions`. The section literal is regex-escaped
 * so a future caller-side string with metacharacters can never inject. */
export function readOutputSection(taskDir, section) {
    let content;
    try {
        content = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
    }
    catch {
        return undefined;
    }
    const m = content.match(new RegExp(`## ${section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\n+([\\s\\S]*?)(?=\\n## |$)`));
    return m ? m[1].trim() : undefined;
}
/** `## Summary` body — the legacy detail source, now the done-row fallback
 * when no `## TL;DR` exists (old output.md files, AC-009). */
export function readOutputSummary(taskDir) {
    return readOutputSection(taskDir, "Summary");
}
/** Cap for terminal readback bodies (AC-014). */
export const OUTPUT_READBACK_MAX = 20_000;
/** Full output.md body for terminal readback (AC-014): worker results are
 * delivered into the watching window's conversation so the PM processes
 * them without manual file reads. Over-cap reports are truncated with a
 * pointer to the file. */
export function readOutputBody(taskDir) {
    const outputPath = path.join(taskDir, "output.md");
    let content;
    try {
        content = fs.readFileSync(outputPath, "utf8").trim();
    }
    catch {
        return undefined;
    }
    if (!content)
        return undefined;
    if (content.length <= OUTPUT_READBACK_MAX)
        return content;
    return `${content.slice(0, OUTPUT_READBACK_MAX)}\n\n…(truncated — full report: ${outputPath})`;
}
/** Last `[launcher] spawn failed …` line from worker.log, if any. Spawn-failure
 * logs are tiny (the CLI never ran — the launcher writes exactly this line and
 * nothing else); a large log means the worker actually ran, so ignore it. */
export function readSpawnFailure(taskDir) {
    const logPath = path.join(taskDir, "worker.log");
    try {
        const stat = fs.statSync(logPath);
        if (stat.size > 64 * 1024)
            return undefined;
        const lines = fs.readFileSync(logPath, "utf8").split("\n");
        for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i].trim();
            if (line.startsWith("[launcher] spawn failed"))
                return line;
        }
        return undefined;
    }
    catch {
        return undefined;
    }
}
/** worker.log read guard for the needs-clarification fallback: larger logs
 * mean the worker actually ran (D-004) — skip the read entirely. */
const WORKER_LOG_TAIL_MAX = 256 * 1024;
/** Last non-empty worker.log line, or undefined. The needs-clarification
 * fallback for tasks that never wrote an output.md (claude/codex workers,
 * old bundles) — their last logged line names what they were asking about. */
export function readWorkerLogTail(taskDir) {
    try {
        const stat = fs.statSync(path.join(taskDir, "worker.log"));
        if (stat.size > WORKER_LOG_TAIL_MAX)
            return undefined;
        const lines = fs.readFileSync(path.join(taskDir, "worker.log"), "utf8").split("\n");
        for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i].trim();
            if (line !== "")
                return line;
        }
        return undefined;
    }
    catch {
        return undefined;
    }
}
/** First non-empty line of a section body, trimmed, leading markdown
 * markers stripped so terminal details never start with `#`/`**`/`- `/`> `
 * (AC-007). Mirrors HEADLINE_MARKER_RE in worker/output-writer. */
const DETAIL_MARKER_RE = /^(?:#{1,6}\s+|\*\*|[-*]\s+|>\s+)/;
function firstLine(body) {
    let line = body?.split("\n")[0]?.trim() ?? "";
    while (DETAIL_MARKER_RE.test(line)) {
        line = line.replace(DETAIL_MARKER_RE, "").trim();
    }
    return line === "" ? undefined : line;
}
/** Widget detail line for a terminal worker row (D-004): the glyph/status
 * says what happened, this says why it stuck or what it concluded.
 *  - failed: spawn-failure reason (launcher prefix stripped, timestamp-free)
 *    ?? `## Exit Reason` first line
 *  - needs-clarification: `## Questions` first line ?? worker.log tail ??
 *    explicit no-output hint (claude/codex tasks write no output.md at all)
 *  - done: `## TL;DR` first line ?? headline-normalized `## Summary` first
 *    line (old output.md files)
 * Returns "" when nothing informative exists (caller renders the key only).
 * Line-width truncation stays with the caller (WATCH_LINE_MAX). */
export function readTerminalDetail(taskDir, status) {
    if (status === "failed") {
        const spawn = readSpawnFailure(taskDir);
        if (spawn !== undefined) {
            const reason = spawn.match(/^\[launcher\] spawn failed \([^)]*\):\s*(.*)$/);
            return (reason?.[1] ?? spawn).trim();
        }
        return firstLine(readOutputSection(taskDir, "Exit Reason")) ?? "";
    }
    if (status === "needs-clarification") {
        return firstLine(readOutputSection(taskDir, "Questions")) ?? readWorkerLogTail(taskDir) ?? "no output.md";
    }
    if (status === "done") {
        const tldr = firstLine(readOutputSection(taskDir, "TL;DR"));
        if (tldr !== undefined)
            return tldr;
        const summary = readOutputSummary(taskDir);
        return summary === undefined ? "" : headline(summary);
    }
    return "";
}
/** Terminal worker statuses (queue semantics; mirrors pm-orchestrator's
 * isTerminal — shared by the ack validation path). */
function isTerminalStatus(status) {
    return status === "done" || status === "failed" || status === "needs-clarification";
}
/** Shared ack validation + write path behind /mw ack and the ack_worker_result
 * tool (D-002). `"all"` expands to every terminal row not yet acked;
 * individual keys must reference an existing terminal row — running/pending
 * rows are rejected and nothing is written for them (AC-004). */
export async function ackTasks(workerStore, ackStore, targets) {
    const entries = workerStore.readAll();
    if (targets === "all") {
        const alreadyAcked = new Set(ackStore.readAll().keys());
        const keys = entries
            .filter((e) => isTerminalStatus(e.status) && !alreadyAcked.has(e.taskKey))
            .map((e) => e.taskKey);
        if (keys.length === 0)
            return { acked: [], rejected: [] };
        return { acked: (await ackStore.ack(keys)).acked, rejected: [] };
    }
    const byKey = new Map(entries.map((e) => [e.taskKey, e]));
    const acked = [];
    const rejected = [];
    for (const key of targets) {
        const entry = byKey.get(key);
        if (entry === undefined) {
            rejected.push({ key, reason: "no such task in the worker queue" });
        }
        else if (!isTerminalStatus(entry.status)) {
            rejected.push({
                key,
                reason: `not terminal (status: ${entry.status}) — only done/failed/needs-clarification rows can be acked`,
            });
        }
        else {
            acked.push(key);
        }
    }
    const written = acked.length > 0 ? await ackStore.ack(acked) : { acked: [], rejected: [] };
    return { acked: written.acked, rejected };
}
/** Live bottom-widget lines for the watched key, in three sections (D-003):
 *  1. live — running then pending, all shown, never folded
 *  2. unhandled — failed/needs-clarification rows the PM has not acked
 *     (/mw ack), all shown, never folded; header carries the count
 *  3. history — done rows ∪ acked terminal rows, newest-first, capped at
 *     WATCH_HISTORY_MAX with a `+N more` fold line
 * Terminal-row details come from readTerminalDetail (D-004). */
export function renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key) {
    const counts = {
        pending: 0,
        running: 0,
        done: 0,
        failed: 0,
        "needs-clarification": 0,
    };
    const acked = new Set(ackStore.readAll().keys());
    const owned = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot) === key);
    for (const e of owned)
        counts[e.status]++;
    // Unhandled = failed/needs-clarification not yet acked — the PM's explicit
    // to-do list; ack moves a row out of this section into history.
    const unhandled = owned.filter((e) => (e.status === "failed" || e.status === "needs-clarification") && !acked.has(e.taskKey));
    const idx = indexStore.findByKey(key);
    const phase = idx
        ? `phase=${idx.phase}`
        : key === SCRATCH_WORKERS_KEY
            ? "manual tasks"
            : "key not in _index.parallel";
    const badge = key === SCRATCH_WORKERS_KEY ? undefined : formatDocsBadge(readPhaseDocs(agenticdocRoot, key));
    const parts = [];
    if (counts.running > 0)
        parts.push(`${counts.running} running`);
    if (counts.pending > 0)
        parts.push(`${counts.pending} pending`);
    if (counts.done > 0)
        parts.push(`${counts.done} done`);
    if (counts.failed > 0)
        parts.push(`${counts.failed} failed`);
    if (counts["needs-clarification"] > 0)
        parts.push(`${counts["needs-clarification"]} needs-clarification`);
    if (unhandled.length > 0)
        parts.push(`${unhandled.length} unhandled`);
    const header = `[mw] ${key} | ${phase}${badge ? ` | docs ${badge}` : ""} | ${parts.length > 0 ? parts.join(" / ") : "no workers"}`;
    if (owned.length === 0)
        return [header, "  (no worker tasks)"];
    // One rendered row per entry; detail per status (live heartbeat vs D-04
    // terminal sources). Width truncation is uniform (WATCH_LINE_MAX).
    // D-116: every row carries the worker's model in a [id] badge — running
    // and terminal rows read the pi-resolved id from trace.log [START]
    // (launcher defaults included); pending rows fall back to the dispatch-time
    // override from the queue row (no trace.log yet).
    const rowLine = (e) => {
        let detail = "";
        let model = "";
        if (e.status === "running") {
            // Heartbeat-derived live progress (design D-008): phase counter + age
            // of the last [HEARTBEAT] line, refreshed on every poll tick. Old
            // bundles without heartbeats get a visible (no-hb) placeholder.
            // [START] adds elapsed runtime ("up 6m") and the last [TOOL] line
            // names what the worker is currently doing.
            const prog = readTaskProgress(path.dirname(e.taskPath));
            model = prog?.model ?? "";
            const hb = prog?.heartbeat;
            if (hb) {
                const ph = hb.phase === "-" ? "ph -" : `ph ${hb.phase}/${hb.phaseTotal}`;
                const up = prog?.elapsedMs !== undefined ? ` up ${formatHeartbeatAge(prog.elapsedMs)}` : "";
                const stale = hb.ageMs > HEARTBEAT_STALE_MS ? " STALE" : "";
                detail = `${ph}${up} hb ${formatHeartbeatAge(hb.ageMs)}${stale}`;
            }
            else {
                detail = "(no-hb)";
            }
            // Convergence checkpoint badge (AC-005): past the checkpoint time the
            // running line carries the machine risk verdict — the PM's divergence
            // radar at a glance. Non-low risks get a warning glyph.
            const ck = prog?.checkpoint;
            if (ck) {
                detail += ` ck${Math.round(ck.elapsedS / 60)}m${ck.risk !== "low" ? ` ${ck.risk}⚠` : ""}`;
            }
            if (prog?.lastAction)
                detail += ` · ${prog.lastAction}`;
        }
        else if (e.status === "pending") {
            // Dispatch-time --model override; the effective id lands in trace.log
            // [START] once the worker spawns.
            model = e.model;
        }
        else {
            // Terminal detail per status (D-004): spawn reason / Exit Reason /
            // Questions / TL;DR with their fallback chains.
            model = readTaskProgress(path.dirname(e.taskPath))?.model ?? "";
            detail = readTerminalDetail(path.dirname(e.taskPath), e.status);
        }
        const badge = model ? ` [${model}]` : "";
        return trunc(`  ${STATUS_GLYPH[e.status]} ${e.taskKey}${badge}${detail ? ` — ${detail}` : ""}`, WATCH_LINE_MAX);
    };
    const newestFirst = (a, b) => (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
    const live = [
        ...owned.filter((e) => e.status === "running").sort(newestFirst),
        ...owned.filter((e) => e.status === "pending").sort(newestFirst),
    ];
    const history = owned.filter((e) => e.status === "done" || acked.has(e.taskKey)).sort(newestFirst);
    const lines = [header];
    for (const e of live)
        lines.push(rowLine(e));
    for (const e of [...unhandled].sort(newestFirst))
        lines.push(rowLine(e));
    for (const e of history.slice(0, WATCH_HISTORY_MAX))
        lines.push(rowLine(e));
    if (history.length > WATCH_HISTORY_MAX)
        lines.push(`  ... +${history.length - WATCH_HISTORY_MAX} more`);
    return lines;
}
/** Render (or clear) the bottom watch widget on a UI-capable context. */
export function setWatchWidget(ctx, lines) {
    if (!ctx.hasUI)
        return;
    ctx.ui.setWidget(WATCH_WIDGET_KEY, lines, { placement: "belowEditor" });
}
/** Render (or clear) the widget via the session_start-captured context.
 * No-op before session start or in headless runs. */
export function applyWatchWidget(ui, lines) {
    if (!ui.ctx)
        return;
    setWatchWidget(ui.ctx, lines);
}
/** Set this window's watched key, persist it in the session file (survives
 * restart/resume), and refresh the bottom widget immediately. `claimed` marks
 * watches that came with a key takeover. */
function setWindowWatch(pi, watch, refresh, ctx, key, claimed) {
    watch.key = key;
    pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed });
    refresh(ctx);
}
/** Doc-gate notifier scoped to this window's watched key (AC-011): the scan
 * evaluates gates for every undocumented key (blocking stays global), but a
 * gate event is only BROADCAST here when it is this window's own key — other
 * keys' gates belong to their owning windows. A window watching nothing
 * stays silent. */
export function makeScopedDocGateNotifier(pi, watch) {
    return (key, gaps) => {
        if (!watch.key || key !== watch.key)
            return false;
        displaySummary(pi, `[mw] skipped dispatch for '${key}' — missing phase docs: ${gaps.join("; ")}. ` +
            "Generate spec/design + evidence/research notes (agentic-task workflows), or move ad-hoc work under _scratch.");
        return true;
    };
}
export function registerPmKeyCommands(pi, indexStore, watch, refreshWatch, agenticdocRoot) {
    pi.registerCommand("pm-key", {
        description: "Manage PM keys: new / switch (take over + watch) / list",
        handler: async (args, ctx) => {
            const [sub, ...rest] = args.trim().split(/\s+/);
            const flags = rest.filter((t) => t.startsWith("--"));
            const positional = rest.filter((t) => !t.startsWith("--"));
            const keyName = positional[0] ?? "";
            const force = flags.includes("--force");
            if (sub === "list") {
                const entries = indexStore.readAll();
                if (entries.length === 0) {
                    ctx.ui.notify("No keys found.", "info");
                    return;
                }
                const table = entries.map((e) => `${e.key} | ${e.status} | ${e.phase} | ${e.claimId}`).join("\n");
                ctx.ui.notify(table, "info");
                return;
            }
            if (sub === "new") {
                if (!keyName) {
                    ctx.ui.notify("Usage: /pm-key new <key-name>", "warning");
                    return;
                }
                if (indexStore.findByKey(keyName)) {
                    ctx.ui.notify(`Key '${keyName}' already exists — use /pm-key switch ${keyName} to take it over.`, "warning");
                    return;
                }
                // Route through the atomic claim: auto-create + demote other active
                // rows (single-active discipline) in one locked step.
                const result = await takeOverKey(indexStore, keyName, false, agenticdocRoot);
                // Executing a key in this window also watches it (bottom progress widget).
                setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
                ctx.ui.notify(`Created and claimed key: ${keyName} (${result.claimId})`, "info");
                if (result.audit.length > 0)
                    ctx.ui.notify(result.audit.join("\n"), "warning");
                return;
            }
            if (sub === "switch") {
                if (!keyName) {
                    ctx.ui.notify("Usage: /pm-key switch <key-name> [--force]", "warning");
                    return;
                }
                const target = indexStore.findByKey(keyName);
                if (!target) {
                    ctx.ui.notify(`Key not found: ${keyName}`, "error");
                    return;
                }
                const result = await takeOverKey(indexStore, keyName, force, agenticdocRoot);
                if (!result.ok) {
                    ctx.ui.notify(`Key '${keyName}' is claimed by another live window (${result.blockedBy}). Use /pm-key switch ${keyName} --force to take it over.`, "warning");
                    return;
                }
                // Switching keys in this window also switches what it watches.
                setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
                ctx.ui.notify(`Took over key: ${keyName} (claim ${result.claimId})`, "info");
                if (result.audit.length > 0)
                    ctx.ui.notify(result.audit.join("\n"), "warning");
                return;
            }
            ctx.ui.notify("Usage: /pm-key new|switch|list [key-name] [--force]", "warning");
        },
    });
}
/** Insert a session-snapshot section at the top of {key}/pm-state.md's Notes
 * area. Machine-interface lines (- Phase: / - Claim-Id:) are owned by the
 * framework scripts and stay byte-identical: the snapshot is inserted under
 * "## Notes" only, never rewriting the rest of the file (pm-state-guard
 * principle, framework-side write with the same lock protocol as
 * StateManager). Returns the path written. */
export async function writeSessionSnapshot(agenticdocRoot, key, lines) {
    const statePath = path.join(agenticdocRoot, key, "pm-state.md");
    const content = fs.existsSync(statePath) ? fs.readFileSync(statePath, "utf8") : `# PM State: ${key}\n\n## Notes\n`;
    const section = [
        `### Session Snapshot — ${new Date().toISOString()} (${windowClaimId()})`,
        ...lines.map((l) => (l ? `- ${l}` : "")),
        "",
    ].join("\n");
    const NOTES_HEADING = /^## Notes[ \t]*$/m;
    const next = NOTES_HEADING.test(content)
        ? content.replace(NOTES_HEADING, `## Notes\n\n${section}`)
        : `${content.trimEnd()}\n\n## Notes\n\n${section}`;
    fs.mkdirSync(path.dirname(statePath), { recursive: true });
    const release = await acquireLock(`${statePath}.lock`);
    try {
        const tmpPath = `${statePath}.tmp`;
        fs.writeFileSync(tmpPath, next, "utf8");
        fs.renameSync(tmpPath, statePath);
    }
    finally {
        release();
    }
    return statePath;
}
/** /pm-save — persist this window's working context into the watched key's
 * pm-state.md so a restarted pi window (e.g. after a framework rebuild) can
 * pick the work back up. The handler writes the mechanical snapshot (watch
 * key, index row, worker counts, free note) itself; the conversational
 * context (what we are doing, decisions, next steps) can only be summarized
 * by the agent, so the handler asks it to — the user invoked the command, so
 * this is a user-requested action, not a framework-injected nudge. */
export function registerPmSaveCommand(pi, indexStore, workerStore, watch, agenticdocRoot) {
    pi.registerCommand("pm-save", {
        description: "Save this window's working context to {watched key}/pm-state.md for restart pickup",
        handler: async (args, ctx) => {
            const note = args.trim();
            if (!watch.key) {
                ctx.ui.notify("Not watching any key — /pm-key switch <key> (take over) or /mw-watch <key> (display only) first.", "warning");
                return;
            }
            const key = watch.key;
            const row = indexStore.findByKey(key);
            const owned = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot) === key);
            const ORDER = ["pending", "running", "done", "failed", "needs-clarification"];
            const counts = new Map();
            for (const e of owned)
                counts.set(e.status, (counts.get(e.status) ?? 0) + 1);
            const workerSummary = owned.length === 0
                ? "no workers"
                : ORDER.filter((s) => counts.get(s))
                    .map((s) => `${counts.get(s)} ${s}`)
                    .join(" / ");
            const lines = [
                `Watch: ${key} (window ${windowClaimId()})`,
                row
                    ? `Index: status=${row.status} phase=${row.phase}${row.desc ? ` — ${row.desc}` : ""}`
                    : "Index: (not in _index.parallel)",
                `Workers: ${workerSummary}`,
            ];
            if (note)
                lines.push(`Note: ${note}`);
            lines.push("(agent: fill in below — 当前工作脉络 / 关键决策 / 进行中 / 下一步)");
            const statePath = await writeSessionSnapshot(agenticdocRoot, key, lines);
            ctx.ui.notify(`Saved session snapshot to ${path.relative(agenticdocRoot, statePath)} — asking the agent to fill in the working context.`, "info");
            pi.sendUserMessage(`[agent-team-loop] /pm-save：已在 ${key}/pm-state.md 的 Notes 区写入会话快照。请立即把当前对话的上下文状态补全到该快照小节：当前工作脉络、关键决策、进行中的事项、下一步动作。只编辑 ${key}/pm-state.md 的 Notes 区，不要动 - Phase: / - Claim-Id: 机器接口行。写完简短确认。`);
        },
    });
}
/** /mw-watch — toggle this window's bottom progress widget for one key.
 * Display-only observation: no claim is taken. Use /pm-key switch to take
 * over a key while developing it.
 *
 * Usage: /mw-watch <key>   watch a key (widget appears below the editor)
 *        /mw-watch off     stop watching (widget cleared)
 *        /mw-watch         show current watch state
 */
export function registerWatchCommand(pi, watch, refreshWatch, indexStore) {
    const USAGE = "Usage: /mw-watch <key> | off   (display only — /pm-key switch takes over a key)";
    pi.registerCommand("mw-watch", {
        description: "Show one key's live worker progress in a bottom widget (/mw-watch <key> | off)",
        handler: async (args, ctx) => {
            const arg = args.trim();
            if (!arg) {
                ctx.ui.notify(watch.key ? `Watching: ${watch.key}. ${USAGE}` : `Not watching anything. ${USAGE}`, "info");
                return;
            }
            if (arg === "off" || arg === "none") {
                watch.key = undefined;
                pi.appendEntry(WATCH_ENTRY_TYPE, { key: undefined, claimed: false });
                refreshWatch(ctx);
                ctx.ui.notify("Watch disabled — bottom widget cleared.", "info");
                return;
            }
            if (arg !== SCRATCH_WORKERS_KEY && !indexStore.findByKey(arg)) {
                ctx.ui.notify(`Key '${arg}' not found in _index.parallel (or use ${SCRATCH_WORKERS_KEY}). ${USAGE}`, "warning");
                return;
            }
            setWindowWatch(pi, watch, refreshWatch, ctx, arg, false);
            ctx.ui.notify(`Watching '${arg}' — worker progress shown below the editor.`, "info");
        },
    });
}
export function registerMwTools(pi, projectDir) {
    pi.registerTool({
        name: "mw_status",
        label: "mw_status",
        description: "Check whether the multi-worker background service (mw serve) is running. Returns PID if running, or 'not running' if stopped.",
        parameters: Type.Object({}),
        execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
            const s = getMwStatus(projectDir);
            return {
                content: [
                    {
                        type: "text",
                        text: s.running
                            ? `mw is running (PID ${s.pid}). Workers are being dispatched and monitored.`
                            : "mw is not running. Workers will not be dispatched. Use /mw start or ask the user to start it.",
                    },
                ],
                details: undefined,
            };
        },
    });
}
/**
 * Register agent-callable tools for worker dispatch and task listing.
 * These complement the slash commands in registerWorkerCommands.
 */
export function registerWorkerTools(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch) {
    // dispatch_worker: create a task.md and immediately dispatch it to the worker queue.
    pi.registerTool({
        name: "dispatch_worker",
        label: "dispatch_worker",
        description: "Dispatch a task to a background worker agent. Creates .agenticdoc/<task_key>/task.md and queues it for execution by the mw worker service. Returns the task key on success.",
        parameters: Type.Object({
            task_key: Type.String({
                description: "Unique kebab-case key for this task (e.g. 'fix-login-bug', 'add-auth-endpoint'). Must be unique across tasks in this project.",
            }),
            description: Type.String({
                description: "Full task description and instructions for the worker agent.",
            }),
            cli: Type.Optional(Type.String({
                description: "Worker CLI: 'pi' (default for all task types incl. review/research), 'claude' (explicit override — requires claude credentials, fails per-task when missing), 'codex' (codex tasks).",
            })),
            model: Type.Optional(Type.String({
                description: "Optional model override for this worker (e.g. 'claude-sonnet-4-5').",
            })),
            key: Type.Optional(Type.String({
                description: "AgenticTask key owning this worker task. Default: this window's claimed key (the one it watches and holds in _index.parallel), else the active key when no other live window holds it, else _scratch.",
            })),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
            const { task_key, description, cli = "pi", model, key, } = params;
            const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, key, agenticdocRoot);
            const validCli = ["pi", "claude", "codex"];
            if (!validCli.includes(cli)) {
                return {
                    content: [{ type: "text", text: `Invalid cli '${cli}'. Must be one of: ${validCli.join(", ")}.` }],
                    details: undefined,
                };
            }
            // Docs gate: real keys need spec + design + research evidence before any
            // worker runs (advance_phase.py gate semantics, enforced mechanically).
            const docGaps = dispatchDocGaps(agenticdocRoot, ownerKey);
            if (docGaps.length > 0) {
                return {
                    content: [
                        {
                            type: "text",
                            text: `Worker dispatch blocked: key '${ownerKey}' is missing phase documentation.\n` +
                                `${docGaps.map((g) => `- ${g}`).join("\n")}\n${DOC_GATE_HINT}`,
                        },
                    ],
                    details: undefined,
                };
            }
            // Worker tasks live under {ownerKey}/workers/<task_key>/ (never at the
            // agenticdoc root - that namespace belongs to AgenticTask keys).
            const taskDir = workerTaskDir(agenticdocRoot, ownerKey, task_key);
            if (fs.existsSync(taskDir)) {
                return {
                    content: [
                        {
                            type: "text",
                            text: `Task '${task_key}' already exists at ${taskDir}. Choose a different task_key or check existing tasks with list_tasks.`,
                        },
                    ],
                    details: undefined,
                };
            }
            const typeField = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
            const provider = cli === "pi" ? "timi" : "";
            fs.mkdirSync(taskDir, { recursive: true });
            const taskMdPath = path.join(taskDir, "task.md");
            const frontmatter = model ? `type: ${typeField}\nmodel: ${model}\n` : `type: ${typeField}\n`;
            fs.writeFileSync(taskMdPath, `${frontmatter}\n${description}\n`, "utf8");
            await dispatchTask({ taskKey: task_key, status: "pending", cli, provider, model: model ?? "", taskPath: taskMdPath }, workerStore);
            return {
                content: [
                    {
                        type: "text",
                        text: `Dispatched worker '${task_key}' (type: ${cli}${model ? `, model: ${model}` : ""}) under key '${ownerKey}'. Task file: ${taskMdPath}. Check mw_status to confirm the service is running.`,
                    },
                ],
                details: undefined,
            };
        },
    });
    // ack_worker_result: the agent-side ack channel (AC-005) — equivalent to
    // /mw ack. Registered here (PM activation path only); worker mode never
    // registers tools, so workers cannot ack their own results.
    pi.registerTool({
        name: "ack_worker_result",
        label: "ack_worker_result",
        description: "Acknowledge a worker's terminal result (done/failed/needs-clarification) after absorbing it: the row moves out of the watch widget's unhandled section into folded history. task_key acks one task; 'all' acks every unacked terminal task.",
        promptGuidelines: [
            "After absorbing a terminal worker result (the readback body / output.md), call ack_worker_result with its task_key — or 'all' after a batch — so the widget's unhandled section clears; unacked failed/needs-clarification rows stay listed until acked.",
        ],
        parameters: Type.Object({
            task_key: Type.String({ description: "Worker task key to ack, or 'all' for every unacked terminal task." }),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
            const { task_key } = params;
            const target = task_key.trim();
            if (!target) {
                return { content: [{ type: "text", text: "task_key is required (or 'all')." }], details: undefined };
            }
            const result = await ackTasks(workerStore, ackStore, target === "all" ? "all" : [target]);
            const parts = [];
            if (result.acked.length > 0)
                parts.push(`Acked ${result.acked.length} task(s): ${result.acked.join(", ")}.`);
            for (const r of result.rejected)
                parts.push(`NOT acked: ${r.key} — ${r.reason}.`);
            if (parts.length === 0)
                parts.push("No unacked terminal tasks.");
            return { content: [{ type: "text", text: parts.join("\n") }], details: undefined };
        },
    });
    // list_tasks: return all tracked tasks and their current status; terminal
    // rows carry an `acked` badge when acknowledged (AC-011).
    pi.registerTool({
        name: "list_tasks",
        label: "list_tasks",
        description: "List all worker tasks in this project with their current status (pending / running / done / failed / needs-clarification). Acked terminal tasks are badged 'acked'.",
        parameters: Type.Object({}),
        execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
            const entries = workerStore.readAll();
            if (entries.length === 0) {
                return { content: [{ type: "text", text: "No tasks found." }], details: undefined };
            }
            const acked = new Set(ackStore.readAll().keys());
            const lines = entries.map((e) => {
                const base = `${e.taskKey} | ${e.status} | ${e.cli}${e.model ? ` | model: ${e.model}` : ""}`;
                return acked.has(e.taskKey) ? `${base} | acked` : base;
            });
            return { content: [{ type: "text", text: lines.join("\n") }], details: undefined };
        },
    });
}
/** Register the agent-callable switch_key tool: same takeover as
 * /pm-key switch, callable mid-conversation. Tool description + prompt
 * guidelines teach the agent when to call it (explicit user request, or
 * starting real task work on a key — ask the user first in that case). */
export function registerSwitchKeyTool(pi, indexStore, watch, refreshWatch, agenticdocRoot) {
    pi.registerTool({
        name: "switch_key",
        label: "switch_key",
        description: "Take over (claim + watch) an AgenticTask key in this window: marks it active in _index.parallel with this window's claim (host:pid) and shows its live worker progress in the bottom widget. " +
            "Call it when the user asks to take over or switch to a key, or when you are about to execute a key's tasks in this window. " +
            "Writing .agenticdoc/{key}/spec.md, design.md, or plan.md switches automatically — no call needed. " +
            "If another live window holds the key's claim, the call fails unless force is true; tell the user and let them decide.",
        promptGuidelines: [
            "Before doing real work on an AgenticTask key (executing its tasks), make sure this window has taken it over via switch_key; if the user has not asked for that key, ask them first whether to switch.",
        ],
        parameters: Type.Object({
            key: Type.String({ description: "The AgenticTask key to take over." }),
            force: Type.Optional(Type.Boolean({
                description: "Steal the claim even if another live window holds it. Only with the user's explicit confirmation.",
            })),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => {
            const { key, force = false } = params;
            const trimmed = key.trim();
            if (!trimmed) {
                return { content: [{ type: "text", text: "key is required." }], details: undefined };
            }
            const result = await takeOverKey(indexStore, trimmed, force, agenticdocRoot);
            if (!result.ok) {
                return {
                    content: [
                        {
                            type: "text",
                            text: `Key '${trimmed}' is claimed by another live window (${result.blockedBy}). The takeover was NOT performed. Tell the user; they can decide on a forced takeover (force=true).`,
                        },
                    ],
                    details: undefined,
                };
            }
            watch.key = trimmed;
            pi.appendEntry(WATCH_ENTRY_TYPE, { key: trimmed, claimed: true });
            refreshWatch(ctx);
            const auditNote = result.audit.length > 0
                ? `\n\nPHASE-CHAIN AUDIT WARNINGS for this key (fix before continuing; phase changes go through advance_phase.py only):\n${result.audit.join("\n")}`
                : "";
            return {
                content: [
                    {
                        type: "text",
                        text: `Took over key '${trimmed}' (claim ${result.claimId})` +
                            `${result.created ? " — new key registered in _index.parallel" : ""}. ` +
                            "This window now watches it; the bottom widget shows its live progress. Previously active keys were marked idle." +
                            auditNote,
                    },
                ],
                details: undefined,
            };
        },
    });
}
/** Register the agent-callable advance_phase tool: the shell-free path
 * through the AgenticTask phase gates. The guard blocks hand-edits of
 * pm-state.md's '- Phase:' line and points at advance_phase.py; running that
 * via the bash tool was the only route, so a window whose shell resolution
 * or in-shell `python` differs (fresh machines: WSL-only bash, Store-stub
 * python, python3-only Linux) had NO way to advance a phase — it deadlocked
 * with "no shell, cannot execute advance_phase.py / update_index.py". This
 * tool spawns the script directly (list args, no shell); gate semantics stay
 * in the Python script, the single source of truth audit_phase.py replays. */
export function registerAdvancePhaseTool(pi, projectDir) {
    const ladder = PHASE_ORDER.map((p) => p.toLowerCase());
    pi.registerTool({
        name: "advance_phase",
        label: "advance_phase",
        description: "Advance an AgenticTask key to the target phase by running the framework gate script (advance_phase.py): checks the phase-gate evidence (spec/design/plan/tasks/execute/done prerequisites), updates pm-state.md, and syncs _index.parallel. Runs the Python script directly without a shell — prefer this over `python .../advance_phase.py` via the bash tool. This is the only sanctioned way to change a key's phase; hand-editing pm-state.md's '- Phase:' line is blocked.",
        promptGuidelines: [
            "Change phases only through this tool (or the equivalent python script when the shell works); when the result reports GATE BLOCKED, fix the listed evidence gaps before retrying.",
        ],
        parameters: Type.Object({
            key: Type.String({ description: "AgenticTask key to advance (not _scratch)." }),
            target_phase: Type.String({
                description: "Target phase (any case): spec | design | plan | tasks | execute | verify | done.",
            }),
            summary: Type.Optional(Type.String({
                description: "Required when target_phase is done: one-line closing summary (what was added/changed + impact surface) recorded in _project_log.md as the cross-key summary row.",
            })),
            supersedes: Type.Optional(Type.String({
                description: "Key this one supersedes, recorded in _project_log.md when advancing to done.",
            })),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
            const { key, target_phase, summary, supersedes } = params;
            const trimmedKey = key.trim();
            const target = target_phase.trim().toLowerCase();
            if (!trimmedKey || !target) {
                return { content: [{ type: "text", text: "key and target_phase are required." }], details: undefined };
            }
            if (trimmedKey.startsWith("_") || trimmedKey.startsWith(".")) {
                return {
                    content: [
                        {
                            type: "text",
                            text: `Key '${trimmedKey}' has a reserved prefix and is not a phase-tracked AgenticTask key.`,
                        },
                    ],
                    details: undefined,
                };
            }
            if (!ladder.includes(target)) {
                return {
                    content: [
                        { type: "text", text: `Unknown phase '${target_phase.trim()}'. Valid: ${ladder.join(" | ")}.` },
                    ],
                    details: undefined,
                };
            }
            // done 汇总契约（advance_phase.py 同步校验，exit 2）：--summary 是
            // _project_log.md 汇总列唯一数据源，缺失不允许推进。工具层先拦，
            // 错误信息比脚本退出码可读。
            if (target === "done" && !(summary ?? "").trim()) {
                return {
                    content: [
                        {
                            type: "text",
                            text: "Advancing to done requires a non-empty summary — one line on what was added/changed and the impact surface (written to _project_log.md as the cross-key summary row).",
                        },
                    ],
                    details: undefined,
                };
            }
            const args = [trimmedKey, target];
            if (summary)
                args.push("--summary", summary);
            if (supersedes)
                args.push("--supersedes", supersedes);
            const result = runAgenticScript(projectDir, "advance_phase.py", args);
            return { content: [{ type: "text", text: result.output }], details: undefined };
        },
    });
}
/**
 * Spawn a worker directly from the pi window.
 * Usage: /worker <claude|codex|pi> [--model <id>] <task description>
 */
export function registerWorkerCommands(pi, workerStore, indexStore, agenticdocRoot, watch) {
    const USAGE = "Usage: /worker <claude|codex|pi> [--model <id>] [--key <name>] <task description>";
    pi.registerCommand("worker", {
        description: "Spawn a worker: /worker <claude|codex|pi> [--model <id>] <task description>",
        handler: async (args, ctx) => {
            const parts = args.trim().split(/\s+/);
            const cli = (parts[0] ?? "").toLowerCase();
            // Optional `--model <id>` and `--key <name>` flags right after the cli;
            // everything else is the description.
            let idx = 1;
            let model = "";
            let keyArg = "";
            while (parts[idx] === "--model" || parts[idx] === "--key") {
                if (parts[idx] === "--model") {
                    model = parts[idx + 1] ?? "";
                    idx += 2;
                    if (!model) {
                        ctx.ui.notify(USAGE, "warning");
                        return;
                    }
                }
                else {
                    keyArg = parts[idx + 1] ?? "";
                    idx += 2;
                    if (!keyArg) {
                        ctx.ui.notify(USAGE, "warning");
                        return;
                    }
                }
            }
            const description = parts.slice(idx).join(" ");
            const validCli = ["claude", "codex", "pi"];
            if (!validCli.includes(cli)) {
                ctx.ui.notify(USAGE, "warning");
                return;
            }
            if (!description) {
                ctx.ui.notify("Task description is required.", "warning");
                return;
            }
            // Map CLI to task.md type field (must match pickWorkerRoute mapping)
            const typeField = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
            const provider = cli === "pi" ? "timi" : "";
            // Create task directory and task.md under {ownerKey}/workers/ (persist
            // model: so it's visible + re-parseable)
            const taskKey = `manual-${Date.now()}`;
            const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, keyArg, agenticdocRoot);
            const docGaps = dispatchDocGaps(agenticdocRoot, ownerKey);
            if (docGaps.length > 0) {
                ctx.ui.notify(`Worker dispatch blocked ('${ownerKey}'): ${docGaps.join("; ")}. Generate the phase docs first or dispatch under _scratch.`, "warning");
                return;
            }
            const taskDir = workerTaskDir(agenticdocRoot, ownerKey, taskKey);
            fs.mkdirSync(taskDir, { recursive: true });
            const taskMdPath = path.join(taskDir, "task.md");
            const frontmatter = model ? `type: ${typeField}\nmodel: ${model}\n` : `type: ${typeField}\n`;
            fs.writeFileSync(taskMdPath, `${frontmatter}\n${description}\n`, "utf8");
            // Dispatch directly to _workers.parallel
            await dispatchTask({ taskKey, status: "pending", cli, provider, model, taskPath: taskMdPath }, workerStore);
            ctx.ui.notify(`Dispatched ${cli} worker (${taskKey}) under key '${ownerKey}'${model ? ` [model: ${model}]` : ""}.`, "info");
        },
    });
}
/** Format a doctor JSON report as a readable Chinese summary (same data as
 * the CLI text output — the TS side never re-implements checks, AC-007). */
export function formatDoctorReport(report, fix) {
    const lines = [];
    const svc = report.service;
    lines.push(svc?.running ? `服务: 运行中 (PID ${svc.pid ?? "?"})` : "服务: 未运行");
    const proxyParts = (report.proxy ?? []).map((p) => `${p.route ?? "?"}/${p.port ?? "?"} ${p.listening ? "监听中" : "未监听"}`);
    if (proxyParts.length > 0)
        lines.push(`代理端口: ${proxyParts.join("; ")}`);
    const orphan = report.orphan_proxy;
    if (orphan?.detected) {
        const ports = (orphan.ports ?? []).map((p) => `${p.port} (PID ${(p.owner_pids ?? []).join(",") || "?"})`);
        lines.push(`孤儿代理: ${ports.join("; ")}（mw 未运行但端口被占，可启动 mw 接管或处置占用进程）`);
    }
    const log = report.launcher_log;
    if (log?.exists) {
        lines.push(`launcher 日志: ${log.error_count ?? 0} 个错误行${log.fatal ? "（含 FATAL）" : ""}`);
    }
    else {
        lines.push("launcher 日志: 无日志文件");
    }
    const queue = report.queue;
    lines.push(`队列: ${queue?.non_terminal?.length ?? 0} 个进行中任务，${queue?.stale_count ?? 0} 个 stale，${queue?.archived_total ?? 0} 条已归档`);
    // Worker liveness (mw doctor worker_liveness section — informational).
    // Stale workers are named so the PM sees which task is suspected hung.
    const liveness = report.worker_liveness ?? [];
    if (liveness.length > 0) {
        const alive = liveness.filter((v) => v.verdict === "alive").length;
        const stale = liveness.filter((v) => v.verdict === "stale").map((v) => v.task_key ?? "?");
        const noHb = liveness.filter((v) => v.verdict === "no-heartbeat").length;
        const parts = [`存活 ${alive}`];
        if (stale.length > 0)
            parts.push(`疑似挂起: ${stale.join(", ")}`);
        if (noHb > 0)
            parts.push(`无心跳 ${noHb}`);
        lines.push(`worker 活性: ${parts.join("; ")}`);
    }
    const credParts = (report.credentials?.routes ?? []).map((r) => `${r.route ?? "?"} ${r.available ? "可用" : "缺凭证"}`);
    if (credParts.length > 0)
        lines.push(`路由凭证: ${credParts.join("; ")}（以 mw 进程 env 为准）`);
    const bundle = report.bundle;
    if (bundle?.available) {
        lines.push(bundle.stale ? "扩展 bundle: 源码较新，建议 /mw build 重建" : "扩展 bundle: 最新");
    }
    // pi shellPath row (fresh-machine shell bootstrap; non-Windows reports
    // not-applicable and stays silent here).
    const piShell = report.pi_shell;
    if (piShell?.status === "ok") {
        lines.push(`pi shell: ${piShell.shell_path ?? "?"}`);
    }
    else if (piShell?.status && piShell.status !== "not-applicable") {
        lines.push(`pi shell: ${piShell.status} — ${piShell.detail ?? ""}`);
    }
    // Dispatch model defaults row (silent when nothing is configured).
    const dispatch = report.dispatch;
    if (dispatch?.exists) {
        if (dispatch.error) {
            lines.push(`派发模型: 配置错误 — ${dispatch.error}`);
        }
        else {
            const roles = Object.entries(dispatch.models ?? {})
                .map(([role, value]) => `${role}=${value}`)
                .join("; ");
            const window = dispatch.window_model || "（未记录）";
            lines.push(`派发模型: ${roles || "未设角色"}; 窗口模型 ${window}`);
        }
    }
    if (fix) {
        const applied = report.fix?.applied;
        lines.push(Array.isArray(applied) && applied.length > 0 ? `已自动修复: ${applied.join("; ")}` : "无可自动修复项");
    }
    const summary = report.summary;
    if (summary?.healthy) {
        lines.push("整体: 健康");
    }
    else {
        const issues = Array.isArray(summary?.issues) ? summary?.issues : [];
        lines.push(issues.length > 0 ? `整体: ${issues.length} 个问题 — ${issues.join("; ")}` : "整体: 未知");
    }
    const suggestions = Array.isArray(summary?.suggestions) ? summary?.suggestions : [];
    for (const s of suggestions)
        lines.push(`建议: ${s}`);
    return lines.join("\n");
}
/** Split a command line on whitespace, honoring double-quoted segments
 * (Windows paths with spaces). Exported for tests. */
export function splitCommandLine(line) {
    const out = [];
    let cur = "";
    let inQuote = false;
    let has = false;
    for (const ch of line) {
        if (ch === '"') {
            inQuote = !inQuote;
            has = true;
        }
        else if (!inQuote && /\s/.test(ch)) {
            if (has) {
                out.push(cur);
                cur = "";
                has = false;
            }
        }
        else {
            cur += ch;
            has = true;
        }
    }
    if (has)
        out.push(cur);
    return out;
}
/** Parse the flag tail of `/mw target set`. null when --game is missing or a
 * known flag has no value (unknown flags are ignored — mw.py validates). */
export function parseTargetSetFlags(parts) {
    const flags = { game: "" };
    for (let i = 0; i < parts.length; i++) {
        const m = /^--(game|engine|vcs|uproject)$/.exec(parts[i]);
        if (!m)
            continue;
        const value = parts[i + 1];
        if (value === undefined || value.startsWith("--"))
            return null;
        flags[m[1]] = value;
        i++;
    }
    if (!flags.game)
        return null;
    return flags;
}
/** /mw target — dual-workspace config from the pi window. Thin wrapper over
 * `mw.py target` (single source of parsing/validation/rendering); the runner
 * is injectable for tests. set/clear remind that dual mode applies on the
 * NEXT worker spawn — no serve restart needed (launcher resolves per spawn). */
export async function runMwTargetCommand(ctx, projectDir, argsText, runner = targetMw) {
    const parts = splitCommandLine(argsText);
    const action = parts[0] ?? "";
    if (action === "show" || action === "clear" || action === "on" || action === "off") {
        const r = runner(projectDir, [action]);
        ctx.ui.notify(r.ok ? r.output || `mw target ${action}: ok` : `mw target ${action} failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "set") {
        const flags = parseTargetSetFlags(parts.slice(1));
        if (!flags) {
            ctx.ui.notify("Usage: /mw target set --game <dir> [--engine <dir>] [--vcs git|p4|none] [--uproject <file>] — quote paths containing spaces", "warning");
            return;
        }
        const args = ["set", `--game=${flags.game}`];
        if (flags.engine !== undefined)
            args.push(`--engine=${flags.engine}`);
        if (flags.vcs !== undefined)
            args.push(`--vcs=${flags.vcs}`);
        if (flags.uproject !== undefined)
            args.push(`--uproject=${flags.uproject}`);
        const r = runner(projectDir, args);
        ctx.ui.notify(r.ok
            ? `${r.output}\nDual mode takes effect on the next worker spawn (no serve restart needed).`
            : `mw target set failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    ctx.ui.notify("Usage: /mw target show | set --game <dir> [--engine <dir>] [--vcs git|p4|none] [--uproject <file>] | clear | on | off", "warning");
}
/** Parse the flag tail of `/mw partition set`. null when --parent is missing
 * or a known flag has no value (unknown flags are ignored — mw.py validates). */
export function parsePartitionSetFlags(parts) {
    const flags = { parent: "", roots: [] };
    for (let i = 0; i < parts.length; i++) {
        const m = /^(--parent|--partition|--vcs|--root)$/.exec(parts[i]);
        if (!m)
            continue;
        const value = parts[i + 1];
        if (value === undefined || value.startsWith("--"))
            return null;
        if (m[1] === "--root") {
            flags.roots.push(value);
        }
        else {
            flags[m[1].slice(2)] = value;
        }
        i++;
    }
    if (!flags.parent)
        return null;
    return flags;
}
/** /mw partition — partition-workspace config from the pi window (mw-target-
 * partition D-010). Thin wrapper over `mw.py partition` (single source of
 * parsing/validation/rendering — the same entry point a direct CLI run hits,
 * so identical args ⇒ identical target.yml bytes); the runner is injectable
 * for tests. set/on remind that the mode applies on the NEXT worker spawn —
 * no serve restart needed (launcher resolves per spawn). */
export async function runMwPartitionCommand(ctx, projectDir, argsText, runner = partitionMw) {
    const parts = splitCommandLine(argsText);
    const action = parts[0] ?? "";
    if (action === "show" || action === "clear" || action === "on" || action === "off") {
        const r = runner(projectDir, [action]);
        ctx.ui.notify(r.ok ? r.output || `mw partition ${action}: ok` : `mw partition ${action} failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "set") {
        const flags = parsePartitionSetFlags(parts.slice(1));
        if (!flags) {
            ctx.ui.notify("Usage: /mw partition set --parent <dir> [--partition <dir>] [--root name=<dir> ...] [--vcs git|p4|none] — quote paths containing spaces", "warning");
            return;
        }
        const args = ["set", `--parent=${flags.parent}`];
        if (flags.partition !== undefined)
            args.push(`--partition=${flags.partition}`);
        if (flags.vcs !== undefined)
            args.push(`--vcs=${flags.vcs}`);
        for (const root of flags.roots)
            args.push(`--root=${root}`);
        const r = runner(projectDir, args);
        ctx.ui.notify(r.ok
            ? `${r.output}\nPartition mode takes effect on the next worker spawn (no serve restart needed).`
            : `mw partition set failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    ctx.ui.notify("Usage: /mw partition show | set --parent <dir> [--partition <dir>] [--root name=<dir> ...] [--vcs git|p4|none] | clear | on | off", "warning");
}
/** /mw model — dispatch model defaults from the pi window. Thin wrapper over
 * `mw.py model` (single source of parsing/validation/rendering); the runner is
 * injectable for tests. set/clear remind when the change takes effect:
 * worker roles on the next spawn (launcher resolves per spawn, no serve
 * restart), `main` at the next window start (session_start application). */
export async function runMwModelCommand(ctx, projectDir, argsText, runner = modelMw) {
    const parts = splitCommandLine(argsText);
    const action = parts[0] ?? "show";
    if (action === "show") {
        const r = runner(projectDir, ["show"]);
        ctx.ui.notify(r.ok ? r.output || "mw model show: ok" : `mw model show failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "set") {
        const role = parts[1];
        const value = parts[2];
        if (!role || !value || parts.length > 3) {
            ctx.ui.notify("Usage: /mw model set <role> <prefix/model> — roles: main, coding, review, research (e.g. /mw model set review timi/glm-5.3-air)", "warning");
            return;
        }
        const r = runner(projectDir, ["set", role, value]);
        ctx.ui.notify(r.ok
            ? `${r.output}\nWorker roles apply on the next spawn (no serve restart); main applies at the next window start.`
            : `mw model set failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "clear") {
        const role = parts[1];
        if (!role || parts.length > 2) {
            ctx.ui.notify("Usage: /mw model clear <role|all>", "warning");
            return;
        }
        const r = runner(projectDir, ["clear", role]);
        ctx.ui.notify(r.ok ? r.output || "mw model clear: ok" : `mw model clear failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    ctx.ui.notify("Usage: /mw model show | set <role> <prefix/model> | clear <role|all>", "warning");
}
export function registerMwCommands(pi, projectDir, workerStore, ackStore) {
    pi.registerCommand("mw", {
        description: "Control mw: build / init / start / stop / restart / status / doctor / target / partition / model / ack",
        handler: async (_args, ctx) => {
            const trimmed = _args.trim();
            const sub = trimmed.split(/\s+/)[0] ?? "status";
            if (sub === "build") {
                ctx.ui.notify("Rebuilding extension bundle (bash-free)…", "info");
                const r = buildMw();
                if (r.ok) {
                    ctx.ui.notify(`mw build OK — reinstalled globally. Restart pi windows to load it.\n${r.output}`, "info");
                }
                else {
                    ctx.ui.notify(`mw build failed: ${r.error}`, "error");
                }
                return;
            }
            if (sub === "init") {
                const result = initMw(projectDir);
                if (result.ok) {
                    ctx.ui.notify("mw init complete — .agenticdoc/ .mw/ .pi/extensions/ created.", "info");
                }
                else {
                    ctx.ui.notify(result.error, "error");
                }
                return;
            }
            if (sub === "doctor") {
                const fix = _args.trim().split(/\s+/)[1]?.toLowerCase() === "fix";
                const r = doctorMw(projectDir, fix);
                if (r.ok) {
                    ctx.ui.notify(formatDoctorReport(r.report, fix), "info");
                }
                else {
                    ctx.ui.notify(`mw doctor 执行失败: ${r.error}`, "error");
                }
                return;
            }
            if (sub === "status") {
                const s = getMwStatus(projectDir);
                if (!s.running) {
                    ctx.ui.notify("mw not running", "info");
                    return;
                }
                const stale = serveStaleness(projectDir);
                ctx.ui.notify(stale?.stale
                    ? `mw running (PID ${s.pid}) — STALE CODE (${stale.detail}). Run /mw restart.`
                    : `mw running (PID ${s.pid})`, stale?.stale ? "warning" : "info");
                return;
            }
            if (sub === "start") {
                const s = getMwStatus(projectDir);
                if (s.running) {
                    ctx.ui.notify(`mw already running (PID ${s.pid})`, "info");
                    return;
                }
                const ok = startMw(projectDir);
                ctx.ui.notify(ok ? "mw starting in background…" : "Could not find mw.py — set MW_PY env var.", ok ? "info" : "error");
                return;
            }
            if (sub === "stop") {
                const s = getMwStatus(projectDir);
                if (!s.running) {
                    ctx.ui.notify("mw is not running", "info");
                    return;
                }
                stopMw(projectDir);
                ctx.ui.notify("mw stop signal sent", "info");
                return;
            }
            if (sub === "restart") {
                ctx.ui.notify("mw restarting (graceful stop, then start)...", "info");
                const r = await restartMw(projectDir);
                if (r === "restarted") {
                    const s = getMwStatus(projectDir);
                    ctx.ui.notify(`mw restarted (PID ${s.pid ?? "?"}) — in-flight workers are adopted by the new launcher's orphan reconcile.`, "info");
                }
                else if (r === "stop-failed") {
                    ctx.ui.notify("mw restart failed: serve did not exit in time — run /mw doctor.", "error");
                }
                else {
                    ctx.ui.notify("mw restart failed: serve did not come up — run /mw doctor.", "error");
                }
                return;
            }
            if (sub === "target") {
                // Dual-workspace config (mw.py target show/set/clear/on/off) — thin
                // wrapper, Python stays the single source of parsing and validation.
                await runMwTargetCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "partition") {
                // Partition-workspace config (mw.py partition set/show/clear/on/off) —
                // thin wrapper, Python stays the single source of parsing and validation.
                await runMwPartitionCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "model") {
                // Dispatch model defaults (mw.py model show/set/clear) — thin wrapper,
                // Python stays the single source of parsing and validation.
                await runMwModelCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "ack") {
                // Ack terminal worker results (AC-004): <task-key> acks one row,
                // all acks every unacked terminal row. Running/pending rows are
                // rejected with the reason — nothing is written for them.
                const target = _args.trim().split(/\s+/)[1] ?? "";
                if (!target) {
                    ctx.ui.notify("Usage: /mw ack <task-key> | all", "warning");
                    return;
                }
                const result = await ackTasks(workerStore, ackStore, target === "all" ? "all" : [target]);
                if (result.acked.length > 0) {
                    ctx.ui.notify(`Acked ${result.acked.length} task(s): ${result.acked.join(", ")}`, "info");
                }
                for (const r of result.rejected)
                    ctx.ui.notify(`Not acked: ${r.key} — ${r.reason}`, "warning");
                if (result.acked.length === 0 && result.rejected.length === 0) {
                    ctx.ui.notify("No unacked terminal tasks.", "info");
                }
                return;
            }
            ctx.ui.notify("Usage: /mw build|init|start|stop|status|doctor [fix] | target show|set|clear|on|off | partition show|set|clear|on|off | model show|set|clear | ack <task-key>|all", "warning");
        },
    });
}
//# sourceMappingURL=ui-bridge.js.map