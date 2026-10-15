import * as fs from "node:fs";
import * as path from "node:path";
import { autoStartMonitor, registerAutopilotCommands } from "../autopilot/console.js";
import { stopMonitor } from "../autopilot/monitor.js";
import { readConfig, readGateReminders } from "../autopilot/status-model.js";
import { registerRagTools } from "../rag/tools.js";
import { AckStore } from "../shared/ack-store.js";
import { ENVELOPE_SECTION_LABELS, ENVELOPE_SECTIONS, inspectEnvelope, isKnownDispatchType, typeExtrasMissing, } from "../shared/dispatch-card.js";
import { registerMainWindowModel } from "../shared/dispatch-models.js";
import { formatHeartbeatAge, readTaskProgress } from "../shared/heartbeat.js";
import { conductorClaimState, IndexStore, keyHasOwnerTraces, keyStateDocPaths, ownerEvidenceCurrent, } from "../shared/index-store.js";
import { getMwStatus, initMw, serveStaleness, startMw, waitForMwStart } from "../shared/mw-runner.js";
import { agenticdocRoot as resolveAgenticdocRoot, SCRATCH_WORKERS_KEY } from "../shared/paths.js";
import { dispatchDocGaps, readPhaseDocs } from "../shared/phase-docs.js";
import { syncPmStateClaimId } from "../shared/pm-state-claim.js";
import { registerPmStateGuard } from "../shared/pm-state-guard.js";
import { evaluateRunIdentity } from "../shared/run-store.js";
import { readTaskType } from "../shared/task-frontmatter.js";
import { WorkerStore, workerOwnerKey } from "../shared/worker-store.js";
import { isGoalEstablished, readGoal } from "./goal-reader.js";
import { StateManager } from "./state-manager.js";
import { dispatchTask } from "./task-dispatcher.js";
import { applyWatchWidget, claimState, claimSyncWarningText, deliverPmAlert, deliverWorkerResult, displaySummary, makeScopedDocGateNotifier, ownerKeyOf, readOutputBody, readSpawnFailure, registerAdvancePhaseTool, registerMwCommands, registerMwTools, registerPmKeyCommands, registerPmSaveCommand, registerSwitchKeyTool, registerWatchCommand, registerWorkerCommands, registerWorkerTools, renderWatchLines, setWatchWidget, takeOverKey, WATCH_ENTRY_TYPE, windowClaimId, } from "./ui-bridge.js";
/**
 * Terminal-readback watermark semantics (AC-011 / AC-012 / AC-013):
 *
 * - `notified` (process-local Set, one per window session) is the DELIVERY
 *   watermark: the open-time baseline ∪ rows consumed silently while no key is
 *   watched (C3) ∪ rows actually delivered after the owner gate (C1). A row in
 *   it is never delivered again by this window. A row whose owner key differs
 *   from the watched key is deliberately NOT recorded, so taking over that key
 *   later still delivers it exactly once.
 * - `readbackDelivered` (process-local Set) is the subset of `notified` that was
 *   actually delivered. It feeds ONLY the AC-012/AC-013 unread counter — it
 *   never suppresses a delivery (the `notified` check does that).
 * - `AckStore` (`_workers.acked`, project-level, persisted) is the PM's HANDLING
 *   watermark, NOT a delivery ledger: `done` rows need no ack, an unacked row is
 *   not therefore undelivered, `ack()` rewrites `ackedAt` on re-ack, and it is
 *   read only for the widget/unread split. No branch ever replays a readback
 *   because of ack state.
 */
const POLL_INTERVAL_MS = 4000; // < 5s per AC-001
function isTerminal(status) {
    return status === "done" || status === "failed" || status === "needs-clarification" || status === "lost";
}
/** AC-012/AC-013 unread count: terminal queue rows whose readback this window
 * never delivered and which the PM never acked. Pure; the caller supplies the
 * already-read `acked` set so one tick reads `_workers.acked` at most once. */
function countUnreadTerminal(entries, acked, readbackDelivered) {
    let n = 0;
    for (const e of entries) {
        if (!isTerminal(e.status))
            continue;
        if (acked.has(e.taskKey) || readbackDelivered.has(e.taskKey))
            continue;
        n += 1;
    }
    return n;
}
/** The phase-doc write/edit target, when the tool path resolves to
 * {agenticdocRoot}/{key}/spec.md | design.md | plan.md — the PM phase docs that
 * mean "this window is now executing this key". Any other path (or file) is
 * not a claim signal. */
function docWriteTarget(toolName, args, projectDir, agenticdocRoot) {
    if (toolName !== "write" && toolName !== "edit")
        return undefined;
    const filePath = args?.path;
    if (typeof filePath !== "string" || filePath === "")
        return undefined;
    const rel = path.relative(path.resolve(agenticdocRoot), path.resolve(projectDir, filePath));
    if (rel.startsWith("..") || path.isAbsolute(rel))
        return undefined; // outside .agenticdoc
    const parts = rel.split(path.sep);
    const doc = parts.length === 2 ? parts[1] : undefined;
    if (doc !== "spec.md" && doc !== "design.md" && doc !== "plan.md")
        return undefined;
    const key = parts[0] ?? "";
    if (!key || key.startsWith("_") || key.startsWith("."))
        return undefined;
    return { key, doc };
}
/** The key a phase-doc write/edit belongs to (see docWriteTarget). */
export function keyFromDocWrite(toolName, args, projectDir, agenticdocRoot) {
    return docWriteTarget(toolName, args, projectDir, agenticdocRoot)?.key;
}
/** Which phase doc was written/edited (see docWriteTarget). */
export function docFromWrite(toolName, args, projectDir, agenticdocRoot) {
    return docWriteTarget(toolName, args, projectDir, agenticdocRoot)?.doc;
}
/** The evidence-note write target, when the tool path resolves to
 * {agenticdocRoot}/{key}/evidence/research/spec-*.md | design-*.md. Not a
 * claim signal (only phase docs are) — but the moment evidence lands is the
 * moment an already-written phase doc's claims can be re-reviewed against
 * it. */
export function evidencePhaseFromWrite(toolName, args, projectDir, agenticdocRoot) {
    if (toolName !== "write" && toolName !== "edit")
        return undefined;
    const filePath = args?.path;
    if (typeof filePath !== "string" || filePath === "")
        return undefined;
    const rel = path.relative(path.resolve(agenticdocRoot), path.resolve(projectDir, filePath));
    if (rel.startsWith("..") || path.isAbsolute(rel))
        return undefined; // outside .agenticdoc
    const parts = rel.split(path.sep);
    if (parts.length !== 4 || parts[1] !== "evidence" || parts[2] !== "research")
        return undefined;
    const note = parts[3] ?? "";
    if (!note.endsWith(".md"))
        return undefined;
    const phase = note.startsWith("spec-")
        ? "spec"
        : note.startsWith("design-")
            ? "design"
            : undefined;
    if (!phase)
        return undefined;
    const key = parts[0] ?? "";
    if (!key || key.startsWith("_") || key.startsWith("."))
        return undefined;
    return { key, phase };
}
/** UI notice when a phase doc and its research evidence coexist — the
 * "re-review when evidence is generated" protocol, as a *notice*, not an
 * injected instruction (mw-evidence-nudge-notify): the old sendUserMessage
 * form made the model treat the automatic nudge as the user ordering an
 * immediate review pass, so the window agent started rewriting the doc with
 * no consent and no chance to veto, hijacking the turn. The framework's role
 * is to flag the moment; the user decides when (and whether) to run the
 * review. Fires once per (key, phase) per session, only when both the phase
 * doc (>= 500 bytes) and >= 1 evidence note exist: the review needs both
 * sides of the comparison. */
export function evidenceReviewNotice(ctx, key, phase, agenticdocRoot, notified) {
    const dedup = `${key}:${phase}`;
    if (notified.has(dedup))
        return;
    const docs = readPhaseDocs(agenticdocRoot, key);
    const docOk = phase === "spec" ? docs.spec : docs.design;
    const evidence = phase === "spec" ? docs.specEvidence : docs.designEvidence;
    if (!docOk || evidence < 1)
        return;
    notified.add(dedup);
    const doc = phase === "spec" ? "spec.md" : "design.md";
    ctx.ui.notify(`[mw] ${key}: ${phase} 阶段证据已就位（${evidence} 份 research note）——建议对照 evidence/research/ 复查 ${doc}（断言-证据对照 / 数字口径 / 内部一致性 / 可证伪性）。何时执行复查由你决定。`, "info");
}
/** Nudge the user toward the /goal brainstorm when the project goal is not
 * yet established. Headless sessions (print/-p) skip the nudge entirely:
 * sendUserMessage starts a generation immediately, and the queued -p prompt
 * would collide with it ("Agent is already processing") before ever reaching
 * the model — `pi -p` in any project without an established goal.md would
 * hard-fail at startup. */
export function nudgeGoalUnestablished(pi, agenticdocRoot, hasUI) {
    const goal = readGoal(agenticdocRoot);
    if (hasUI && !isGoalEstablished(goal)) {
        pi.sendUserMessage("[agent-team-loop] 项目总目标（.agenticdoc/goal.md）尚未确立。\n" +
            "建议先运行 /goal，与我对话共创项目总目标——它是后续每个 spec 对齐的锚点。\n" +
            "（也可直接编辑 .agenticdoc/goal.md 填好三段内容并把 status 改为 active。）");
    }
}
/** Auto-takeover on phase-doc write: writing/editing {key}/spec.md, design.md,
 * or plan.md is this window saying "I am now executing key X" — claim it and
 * watch it, exactly like /pm-key switch. A live foreign claim blocks the claim
 * (watch-only) but never the watch itself. Writing design.md / plan.md also
 * runs the next-phase evidence gate (mirrors advance_phase.py): the previous
 * phase's research notes must exist, or the user is warned immediately. */
export async function autoTakeOverFromDoc(pi, indexStore, watch, refreshWatch, key, doc, agenticdocRoot, ctx) {
    // Next-phase evidence gate: writing design.md means the spec phase should be
    // complete (its research notes exist); writing plan.md means design should be.
    // Fires regardless of takeover idempotency — the missing evidence is the
    // message, and it stays true until the notes are written.
    const docs = readPhaseDocs(agenticdocRoot, key);
    if (doc === "spec.md" && docs.specEvidence < 1) {
        ctx.ui.notify(`[mw] ${key}: no evidence/research/spec-*.md found — write the research notes (or a zero-research declaration) alongside the spec; the advance-to-design gate checks them.`, "warning");
    }
    if (doc === "design.md" && docs.specEvidence < 1) {
        ctx.ui.notify(`[mw] ${key}: no evidence/research/spec-*.md found — the advance-to-design gate requires >= 1 research note (a zero-research declaration counts). Write it before advancing.`, "warning");
    }
    if (doc === "plan.md") {
        if (!docs.design) {
            ctx.ui.notify(`[mw] ${key}: design.md missing or under 500 bytes — required before plan (run the system-design workflow).`, "warning");
        }
        else if (docs.designEvidence < 1) {
            ctx.ui.notify(`[mw] ${key}: no evidence/research/design-*.md found — the advance-to-plan gate requires >= 1 research note (a zero-research declaration counts). Write it before advancing.`, "warning");
        }
    }
    const row = indexStore.findByKey(key);
    const wasWatching = watch.key === key;
    const wasClaimed = row?.claimId === windowClaimId();
    if (wasWatching && wasClaimed)
        return; // already ours — nothing to do
    const result = await takeOverKey(indexStore, key, false, agenticdocRoot);
    watch.key = key;
    pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed: result.ok });
    refreshWatch(ctx);
    if (result.ok) {
        ctx.ui.notify(`[mw] claimed key '${key}' (doc write detected) — watching it${result.created ? " (new key registered)" : ""}.`, "info");
        if (result.audit.length > 0)
            ctx.ui.notify(result.audit.join("\n"), "warning");
    }
    else {
        ctx.ui.notify(`[mw] key '${key}' is claimed by another live window (${result.blockedBy}) — watching only.`, "warning");
    }
}
/** Restore this window's watched key from the session file (survives restart
 * and resume) and re-render the bottom widget. A watch that came with a key
 * takeover re-claims the key with this process's identity — quietly, unless
 * another live window took it over in the meantime. */
export async function restoreWatch(pi, watch, indexStore, workerStore, ackStore, agenticdocRoot, ctx) {
    let data;
    try {
        const entries = ctx.sessionManager.getEntries();
        for (let i = entries.length - 1; i >= 0; i--) {
            const e = entries[i];
            if (e.type === "custom" && e.customType === WATCH_ENTRY_TYPE) {
                data = e.data;
                break;
            }
        }
    }
    catch {
        return; // session entries unavailable — nothing to restore
    }
    if (!data?.key)
        return;
    const key = data.key;
    watch.key = key;
    // T-16c: the restart restore path may take a key back from THIS host's
    // conductor (a `held-conductor` synthetic claim is yieldable — T-16b). That
    // handover is correct (human priority) but must not be silent: the goal is
    // that "who took the key from the conductor, and when" stays explainable.
    // Recorded on existing surfaces only — no new event name, no new entry type:
    //   * the `_index.parallel` Claim cell (and the pm-state.md mirror) flips to
    //     this window — the state surface;
    //   * `tookOverFromConductor` rides the EXISTING `agent-team-loop:watch`
    //     session entry shape, giving the durable machine-readable act record;
    //   * a transcript notice via the existing `displaySummary` channel states
    //     the holder change out loud (passive — it never spends an agent turn).
    // The timeline is deliberately NOT written here: it has a single writer (the
    // conductor, `timeline.py` D-109) and a second seq counter would corrupt it.
    // Set only in the `held-conductor` branch, so a second restart (row now this
    // window's, or stale) leaves exactly the same record count — idempotent by
    // construction.
    let tookOverFromConductor;
    if (data.claimed) {
        const row = indexStore.findByKey(key);
        if (row) {
            const self = windowClaimId();
            const previousClaim = row.claimId.trim();
            const holder = claimState(previousClaim, self);
            if (holder === "held-live") {
                // Another window took over while this one was closed — keep the
                // watch (display-only) and say so; do not touch the shared row.
                // Unchanged by T-16c (requirement 3): a truly live foreign claim
                // is still never taken silently.
                ctx.ui.notify(`[mw] key '${key}' is claimed by another window (${row.claimId}) — watching only.`, "warning");
            }
            else {
                // Our previous process is gone; re-bind ownership through the
                // atomic claim — a window that raced us to this key wins and we
                // degrade to watch-only (review M2). Quiet re-claim: no demote of
                // other active rows, no status flip; only claimId/updated move.
                const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", {
                    demoteOthers: false,
                    activate: false,
                });
                if (!outcome.ok) {
                    ctx.ui.notify(`[mw] key '${key}' is claimed by another window (${outcome.blockedBy}) — watching only.`, "warning");
                }
                else {
                    // This path flips the index row's Claim column too, so the
                    // pm-state.md mirror must be synced as well (D-108). A failed
                    // mirror never reverts the claim — the index row is
                    // authoritative — but the divergence must be visible.
                    const sync = syncPmStateClaimId(agenticdocRoot, key, self);
                    const syncWarning = claimSyncWarningText(key, sync);
                    if (syncWarning !== "")
                        ctx.ui.notify(syncWarning, "warning");
                    if (holder === "held-conductor") {
                        tookOverFromConductor = previousClaim;
                        displaySummary(pi, `[mw] 窗口重启恢复：key '${key}' 原由本机 autopilot conductor 接管（合成 claim ${previousClaim}），` +
                            `已改由本窗口接管（${self}）。人工优先，conductor 下次 tick 让位且不再抢回；` +
                            "记录面：_index.parallel 的 Claim 单元 + 本 session 的 agent-team-loop:watch entry（tookOverFromConductor）。");
                    }
                }
            }
        }
    }
    setWatchWidget(ctx, renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key, watch.dispatchedTaskKeys));
    // Re-stamp the entry so it lands in the (possibly new) session file.
    // T-16c: `tookOverFromConductor` (the pre-takeover synthetic claim id) is
    // added ONLY on the handover restore, so the act record is exactly one entry
    // regardless of how often the window restarts afterwards.
    pi.appendEntry(WATCH_ENTRY_TYPE, {
        key,
        claimed: data.claimed ?? false,
        ...(tookOverFromConductor === undefined ? {} : { tookOverFromConductor }),
    });
    // Saved working context (pm-save): point the user at it — a notice, never
    // an injected instruction (same principle as evidenceReviewNotice: the
    // framework flags, the user decides whether the agent reads it).
    const pmStatePath = path.join(agenticdocRoot, key, "pm-state.md");
    if (fs.existsSync(pmStatePath)) {
        const updated = fs.statSync(pmStatePath).mtime.toISOString();
        ctx.ui.notify(`[mw] key '${key}' 有已保存的 pm-state.md（更新于 ${updated}）。如需接续上次的工作上下文，让 agent 读取 ${key}/pm-state.md 的 Notes 区。`, "info");
    }
}
function pickWorkerRoute(taskContent) {
    // Global default is pi/timi: review/research are routing HINTS for the
    // agent, not claude redirects (design D-005) — a claude worker requires an
    // explicit `cli` param on dispatch_worker / /worker, where missing
    // credentials fail per-task instead of silently degrading the route.
    // The reading comes from the single-source header parser (AC-005/F-6): the
    // old `/^type:\s*codex/im` full-text regex let one body line flip the
    // dispatch CLI, outside the shared `type:` matrix.
    if (readTaskType(taskContent).type === "codex")
        return { cli: "codex", provider: "" };
    return { cli: "pi", provider: "timi" };
}
// Optional `model:` line in task.md → passed through to the launcher as --model/-m.
function readModel(taskContent) {
    const m = taskContent.match(/^model:\s*(.+)$/im);
    return m ? m[1].trim() : "";
}
// Conductor-origin marker line (D-104): `origin: conductor`. Conductor task.md
// files are rendered by autopilot/dispatch.py render_task_md; the value is the
// literal token "conductor" (line-exact, CRLF-tolerant).
const ORIGIN_LINE_RE = /^origin:[ \t]*(\S+)[ \t\r]*$/m;
/** Dispatch origin of a task.md, when it carries an `origin:` line. */
function readTaskOrigin(taskContent) {
    return ORIGIN_LINE_RE.exec(taskContent)?.[1];
}
/** Is this a conductor-owned task (D-104)? Such tasks are queued by the
 * conductor alone — the TS scan must never upsert them, closing both the
 * scan/upsert race and the re-insert-as-pending path that a launcher restart
 * (or an archived row) would otherwise open. Manual/legacy tasks carry no
 * marker and behave exactly as before (AC-012 zero regression). Unreadable
 * task.md returns false so the dispatch loop hits the same read error it
 * always did. */
function isConductorTask(taskMdPath) {
    try {
        return readTaskOrigin(fs.readFileSync(taskMdPath, "utf8")) === "conductor";
    }
    catch {
        return false;
    }
}
/** Alarm kinds that are NOT refusals — the scan made a scope/ownership
 * observation. Their text must stay neutral (`[mw] dispatch 提示：…`); only
 * real refusal kinds may say `[mw] dispatch 已拒绝：…` (AC-011/T-19). */
export const NOTICE_DISPATCH_ALARM_KINDS = new Set([
    "out-of-scope",
    "orphaned-keys",
    "orphan-repair-skipped",
]);
/** Is this alarm a notice (neutral wording) rather than a refusal? */
export function isNoticeDispatchAlarm(kind) {
    return NOTICE_DISPATCH_ALARM_KINDS.has(kind);
}
/** Autopilot ledger path (shared with the Python conductor). */
const AUTO_DECISIONS_FILE = "auto-decisions.jsonl";
/** One-line human text for a refused dispatch scan (AC-020/AC-021). Notice
 * kinds carry neutral wording; the verdict prefix is added by
 * {@link formatDispatchAlarm} (AC-011/T-19). */
export function describeDispatchAlarm(alarm) {
    switch (alarm.kind) {
        case "queue-rows-unparsable":
            return `${alarm.count} unreadable row(s) in _workers.parallel — dispatch refused (fix the row; nothing was queued)${alarm.detail ? `: ${alarm.detail}` : ""}`;
        case "queue-unreadable":
            return `the queue looks empty while the work has already run (key ${alarm.detail ?? "?"}) — dispatch refused instead of re-running ${alarm.count} task(s)`;
        case "dispatch-quota":
            return `scan quota reached after ${alarm.count} task(s) — the rest of this scan was refused`;
        case "out-of-scope":
            return `${alarm.count} key(s) with undispatched work but no owner record, outside this window's write scope (${alarm.detail ?? "?"}) — scanned read-only, nothing written. Action required: register the key first (switch_key <key> or dispatch_worker(key=<key>)), then dispatch; its work sits in {key}/workers/<task-key>/task.md`;
        case "orphaned-keys":
            return `${alarm.count} orphaned key(s) with undispatched work, no live claim and no live run (${alarm.detail ?? "?"}) — claim-free repair dispatch applied (the conductor stays eligible); no _index.parallel claim was written`;
        case "orphan-repair-skipped":
            return `${alarm.count} key(s) with work but stale owner evidence — claim-free repair skipped, nothing written (${alarm.detail ?? "?"})`;
        case "run-ledger-conflict":
            return `${alarm.count} task(s) already have a terminal run.json while the queue has no row for them — not re-queued${alarm.detail ? `: ${alarm.detail}` : ""}`;
        case "no-product":
            return `${alarm.count} read-only run(s) settled without a product — needs-clarification, awaiting human judgement${alarm.detail ? `: ${alarm.detail}` : ""}`;
        case "write-scope-risk":
            return `${alarm.count} write-scope residual-risk row(s) (blocked=false, risk=deny-basename)${alarm.detail ? ` on ${alarm.detail}` : ""} — the guard allowed them by contract; review the audited target`;
        case "write-face-refusal":
            return `write_face gate refused ${alarm.count} task(s)${alarm.detail ? `: ${alarm.detail}` : ""} — not queued`;
    }
}
/** The full PM alert line for one alarm (AC-011/T-19): only real refusal kinds
 * carry the `已拒绝` verdict — a notice (`out-of-scope` / `orphaned-keys`) says
 * `提示` and never reads as a refusal. */
export function formatDispatchAlarm(alarm) {
    const verdict = isNoticeDispatchAlarm(alarm.kind) ? "提示" : "已拒绝";
    return `[mw] dispatch ${verdict}：${describeDispatchAlarm(alarm)}`;
}
/** Append one machine-readable alarm row to the autopilot ledger
 * (`.agenticdoc/_autopilot/auto-decisions.jsonl`, AC-020/AC-021). The shape
 * mirrors the Python single writer (`conductor._append_auto_decision_row`):
 * one JSON object per line, 1-based `seq`. Decision consumers filter on
 * `phase == "decide"`, so `phase: "dispatch-alarm"` is invisible to them while
 * staying visible to humans, `mw doctor` and later consumers. Best-effort by
 * design: losing the alarm must never break dispatch. */
export function recordDispatchAlarm(agenticdocRoot, alarm) {
    try {
        const ledger = path.join(agenticdocRoot, "_autopilot", AUTO_DECISIONS_FILE);
        let seq = 1;
        try {
            seq =
                fs
                    .readFileSync(ledger, "utf8")
                    .split("\n")
                    .filter((l) => l.trim() !== "").length + 1;
        }
        catch {
            seq = 1;
        }
        const row = { seq, phase: "dispatch-alarm", kind: alarm.kind, count: alarm.count, detail: alarm.detail ?? "" };
        fs.mkdirSync(path.dirname(ledger), { recursive: true });
        fs.appendFileSync(ledger, `${JSON.stringify(row)}\n`, "utf8");
    }
    catch (err) {
        console.error(`[mw] dispatch alarm not recorded: ${err instanceof Error ? err.message : String(err)}`);
    }
}
/** Count the write-guard residual-risk audit rows in one worker trace
 * (AC-007/T-03): `[WRITE_SCOPE]` lines carrying BOTH `blocked=false` and
 * `risk=deny-basename`. The filter is deliberately the two-field pair and never
 * `rule=allow-unknown` alone (design-write-guard-landing §5.5): the unknown tier
 * is the contract, the deny-list basename is the residual risk. Best-effort — a
 * missing/unreadable trace is zero, never an error. */
export function countWriteScopeResidualRisks(taskDir) {
    let raw;
    try {
        raw = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
    }
    catch {
        return 0;
    }
    let count = 0;
    for (const line of raw.split("\n")) {
        if (!line.startsWith("[WRITE_SCOPE] "))
            continue;
        if (!line.includes("blocked=false"))
            continue;
        if (!line.includes("risk=deny-basename"))
            continue;
        count += 1;
    }
    return count;
}
/** PM-side exit for the write-guard residual risk (AC-007/DD-08): the worker
 * was allowed through by contract, so the ledger row is the remaining defence.
 * Reuses the single dispatch-alarm channel and its unchanged row shape; returns
 * the number of residual-risk rows found (0 ⇒ nothing written). */
export function recordWriteScopeResidualRisks(agenticdocRoot, taskKey, taskDir) {
    const count = countWriteScopeResidualRisks(taskDir);
    if (count === 0)
        return 0;
    recordDispatchAlarm(agenticdocRoot, { kind: "write-scope-risk", count, detail: taskKey });
    return count;
}
/** The one-line ledger detail for a PM-side write-face refusal (AC-003/D-008).
 * `DispatchRefusal.reason` is byte-identical to the conductor's
 * `DispatchResult.reason`, so it already carries the stable refusal `code`, the
 * `overlap-with:<task_key>` pair and the conflict `sample` when the gate could
 * prove one. The refused task key prefixes it because the alarm row has no key
 * column of its own. */
export function writeFaceRefusalDetail(taskKey, refusal) {
    return `${taskKey}: ${refusal.reason}`;
}
/** Consume one non-ok `DispatchOutcome` on the PM dispatch path (AC-003/D-008,
 * card T-W-I13): the refusal is a zero-side-effect return value, so the caller
 * must NOT count the task as queued. It is turned into a durable ledger row
 * through the single {@link recordDispatchAlarm} channel (best-effort by
 * design: a lossy audit must never break dispatch) plus a short human-visible
 * PM alert. The two are deliberately separate — the alert is not the audit. */
function reportWriteFaceRefusal(agenticdocRoot, taskKey, refusal, onRefusal) {
    const alarm = {
        kind: "write-face-refusal",
        count: 1,
        detail: writeFaceRefusalDetail(taskKey, refusal),
    };
    recordDispatchAlarm(agenticdocRoot, alarm);
    onRefusal?.(formatDispatchAlarm(alarm));
}
/** Single-scan dispatch quota (AC-021). A scan that wants to queue more rows
 * than this is looking at something it does not understand (IN-3 queued 252 in
 * one scan and the launcher spawned 66 workers at once). */
export const DEFAULT_DISPATCH_MAX_PER_SCAN = 3;
/** `dispatch_max_per_scan` from the project's autopilot config (D-026/AC-021).
 *
 * An explicit `DispatchScanOptions.maxPerScan` wins (tests and refreshers);
 * otherwise the project config decides. Read-only and fail-soft: a missing,
 * unreadable or out-of-range config falls back to
 * {@link DEFAULT_DISPATCH_MAX_PER_SCAN} — a broken file must never be able to
 * disable the quota (the IN-3 direction of the failure is *more* dispatching,
 * never less). */
export function readDispatchMaxPerScan(agenticdocRoot) {
    try {
        const result = readConfig(path.dirname(agenticdocRoot));
        if (!result.ok)
            return DEFAULT_DISPATCH_MAX_PER_SCAN;
        const value = result.config.dispatch_max_per_scan;
        return Number.isInteger(value) && value >= 1 ? value : DEFAULT_DISPATCH_MAX_PER_SCAN;
    }
    catch {
        return DEFAULT_DISPATCH_MAX_PER_SCAN;
    }
}
/** Product evidence for {@link dispatchNewTasks}'s empty-queue guard (AC-020):
 * files the worker itself writes into its own directory. A task dir holding
 * only `task.md` has never run — that is a fresh project, not a lost queue. */
function hasProductEvidence(taskDir) {
    for (const name of ["output.md", "report.md", "run.json", "trace.log"]) {
        if (fs.existsSync(path.join(taskDir, name)))
            return true;
    }
    return false;
}
/** T-24 req. 1b: the terminal product of a task run. A task dir that already
 * holds `output.md` is HISTORY, never "undispatched work" — C-30's repair queued
 * `ga-spec-review-1` / `mw-dr-glm53` / `mw-dr-keyed-probe` precisely because
 * their months-old dirs had this file (the queue then reaped them `done` in 4s).
 * Deliberately narrower than {@link hasProductEvidence}: only the worker's final
 * product counts here, not `trace.log`/`run.json` (a fresh run may have a trace
 * without an output yet). */
function hasTerminalProduct(taskDir) {
    return fs.existsSync(path.join(taskDir, "output.md"));
}
/** Does the key's own current state (`pm-state.md` / `plan.md`) name this
 * task-key (T-24 req. 1c)? Boundary-anchored so `task-1` never matches
 * `task-12`. Read-only and best-effort: a missing/unreadable doc is no match. */
function stateDocReferencesTask(agenticdocRoot, key, taskKey) {
    const boundary = "[^A-Za-z0-9._-]";
    const escaped = taskKey.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(^|${boundary})${escaped}($|${boundary})`);
    for (const doc of keyStateDocPaths(agenticdocRoot, key)) {
        let text;
        try {
            text = fs.readFileSync(doc, "utf8");
        }
        catch {
            continue;
        }
        if (re.test(text))
            return true;
    }
    return false;
}
/** T-24 scope narrowing for one out-of-scope key (C-30). Two gates:
 *
 *   1. work (req. 1): drop every candidate whose dir already has `output.md`;
 *      when the key publishes state documents AND its owner evidence is stale,
 *      also drop candidates its own `pm-state.md` / `plan.md` does not name (1c);
 *   2. owner evidence (req. 2): an `idle` / `done` index row with no fresh state
 *      document and no live claim is stale — the key is history, never a repair
 *      target (req. 3).
 *
 * The reference filter (1c) is applied only on the stale-evidence path: for a
 * CURRENT owner the frozen T-19/T-22 contract deliberately repairs a trace-only
 * key whose task is not yet written into its plan (a real in-flight task). See
 * the T-24 report for this deviation from the card's unconditional 1c. */
function judgeOrphanScope(agenticdocRoot, key, candidates, row) {
    const live = candidates.filter(({ taskMdPath }) => !hasTerminalProduct(path.dirname(taskMdPath)));
    const evidence = ownerEvidenceCurrent(agenticdocRoot, key, row);
    if (evidence.current)
        return { repairable: live };
    return {
        repairable: live.filter(({ taskKey }) => stateDocReferencesTask(agenticdocRoot, key, taskKey)),
        blockReason: evidence.reason ?? "owner 证据已过期",
    };
}
// ── Claim-free orphan repair (AC-011/T-19) ─────────────────────────────────
/** Marker/skeleton of the service-layer envelope fallback, byte-mirrored from
 * `packages/multi-workers/launcher.py` (T-14, `envelope_fallback_inject`): the
 * same marker keeps the injection idempotent, and the same `[ENVELOPE_FALLBACK]`
 * audit token makes the fallback greppable on both sides. */
export const ENVELOPE_FALLBACK_MARKER = "<!-- mw-envelope-fallback -->";
export const ENVELOPE_FALLBACK_AUDIT = "[ENVELOPE_FALLBACK]";
const ENVELOPE_FALLBACK_SECTION_BODY = `${ENVELOPE_FALLBACK_AUDIT} 服务层兜底注入：原 producer 未提供本段。` +
    "这是让该行可 spawn 的最小骨架，不是任务内容，也不改变任何写面判据；" +
    "请以任务卡与 PM 指令为准，并在升级 producer 后重新派发。";
const ENVELOPE_FALLBACK_EXTRA_LINES = {
    写入允许面: `${ENVELOPE_FALLBACK_AUDIT} 写入允许面: 服务层兜底骨架（原 producer 未声明；写面判据不变）`,
    写入禁止面: `${ENVELOPE_FALLBACK_AUDIT} 写入禁止面: 服务层兜底骨架（原 producer 未声明；写面判据不变）`,
    验收命令: `${ENVELOPE_FALLBACK_AUDIT} 验收命令: 服务层兜底骨架（原 producer 未声明）`,
    改动历史: `${ENVELOPE_FALLBACK_AUDIT} 改动历史: 服务层兜底骨架（原 producer 未声明）；trace.log 写入事件`,
    唯一证据文件: `${ENVELOPE_FALLBACK_AUDIT} 唯一证据文件: 服务层兜底骨架（原 producer 未声明）`,
    审计目标: `${ENVELOPE_FALLBACK_AUDIT} 审计目标: 服务层兜底骨架（原 producer 未声明）`,
    未覆盖面声明: `${ENVELOPE_FALLBACK_AUDIT} 未覆盖面声明: 服务层兜底骨架（原 producer 未声明）`,
};
/** Canonical-envelope skeleton for a refused card, or `null` when the card
 * cannot be made compliant without inventing facts (missing/unknown `type:`).
 *
 * AC-011e / T-14 semantics, re-implemented on the TS side so a claim-free
 * repair does not depend on the project's `envelope_fallback` config (the very
 * config an old-form project does not have): only the MISSING pieces are
 * appended — the card's own frontmatter and body are untouched — and the
 * result is re-judged before it is returned. A skeleton that still fails yields
 * `null` and the caller stays fail-closed. Existing `[ENVELOPE_FALLBACK]`
 * marker ⇒ idempotent passthrough. */
export function synthesizeEnvelopeFallback(text) {
    if (text.includes(ENVELOPE_FALLBACK_MARKER))
        return text;
    const envelope = inspectEnvelope(text);
    if (envelope.type === "" || !isKnownDispatchType(envelope.type))
        return null;
    const additions = [ENVELOPE_FALLBACK_MARKER];
    for (const section of ENVELOPE_SECTIONS) {
        if (!envelope.missing.includes(section))
            continue;
        additions.push("", `## ${ENVELOPE_SECTION_LABELS[section]}`, "", ENVELOPE_FALLBACK_SECTION_BODY);
    }
    for (const item of typeExtrasMissing(envelope.type, text)) {
        const line = ENVELOPE_FALLBACK_EXTRA_LINES[item];
        if (line === undefined)
            return null;
        additions.push("", line);
    }
    if (additions.length === 1)
        return null; // nothing to inject
    const injected = `${text.replace(/\n+$/, "")}\n${additions.join("\n")}\n`;
    const after = inspectEnvelope(injected);
    const extrasAfter = after.type === "" ? [] : typeExtrasMissing(after.type, injected);
    if (!after.ok || extrasAfter.length > 0)
        return null;
    return injected;
}
/** Default run-identity gate for the repair path: the product decides, exactly
 * as the automatic scan's wiring does (`evaluateRunIdentity`, AC-022). */
function defaultOrphanRunVerdict(agenticdocRoot, ownerKey) {
    return (task) => evaluateRunIdentity({
        taskDir: task.taskDir,
        readTaskContent: task.readTaskContent,
        resolveTaskDir: (supersededKey) => {
            const dir = path.join(agenticdocRoot, ownerKey, "workers", supersededKey);
            return fs.existsSync(dir) ? dir : undefined;
        },
    });
}
/** Make one old-form task.md dispatchable through the service-layer skeleton,
 * appending an `[ENVELOPE_FALLBACK]` audit fact to its trace.log. `"ok"` = the
 * card already carries a complete envelope; `"synthesized"` = rewritten;
 * `"unsynthesizable"` = missing/unknown `type:`, fail-closed. */
function ensureServiceEnvelope(taskMdPath, key, taskKey) {
    let text;
    try {
        text = fs.readFileSync(taskMdPath, "utf8");
    }
    catch {
        return "unsynthesizable";
    }
    const envelope = inspectEnvelope(text);
    if (envelope.ok && typeExtrasMissing(envelope.type, text).length === 0)
        return "ok";
    const injected = synthesizeEnvelopeFallback(text);
    if (injected === null)
        return "unsynthesizable";
    try {
        fs.writeFileSync(taskMdPath, injected, "utf8");
        const audit = `${ENVELOPE_FALLBACK_AUDIT} ${new Date().toISOString()} ${key}/${taskKey} ` +
            "kind=repair synthesized=canonical-envelope-skeleton " +
            "(claim-free orphan repair; envelope judgement only — write-face judgement unchanged)";
        fs.appendFileSync(path.join(path.dirname(taskMdPath), "trace.log"), `${audit}\n`, "utf8");
    }
    catch {
        return "unsynthesizable";
    }
    return "synthesized";
}
/** Dispatch already-collected repair candidates and NEVER touch
 * `_index.parallel` — the whole point of the repair path is that the key keeps
 * its claim cell (dead/free), so `conductor.py`'s
 * `if claim == state.CLAIM_LIVE: … continue` stays false and the conductor can
 * resume driving the key at any time (AC-011). */
async function dispatchOrphanCandidates(workerStore, agenticdocRoot, key, candidates, maxPerScan, runVerdict, onRefusal) {
    const result = {
        key,
        queued: [],
        refused: [],
        synthesized: [],
        unsynthesizable: [],
    };
    for (const { taskKey, taskMdPath } of candidates) {
        if (result.queued.length >= maxPerScan)
            break;
        const taskDir = path.dirname(taskMdPath);
        const verdict = runVerdict({
            taskKey,
            taskDir,
            readTaskContent: () => fs.readFileSync(taskMdPath, "utf8"),
        });
        if (!verdict.ok) {
            result.refused.push({ taskKey, reason: verdict.reason, detail: verdict.detail });
            continue;
        }
        const envelope = ensureServiceEnvelope(taskMdPath, key, taskKey);
        if (envelope === "unsynthesizable") {
            result.unsynthesizable.push(taskKey);
            continue;
        }
        if (envelope === "synthesized")
            result.synthesized.push(taskKey);
        const taskContent = fs.readFileSync(taskMdPath, "utf8");
        const { cli, provider } = pickWorkerRoute(taskContent);
        const model = readModel(taskContent);
        try {
            const outcome = await dispatchTask({ taskKey, status: "pending", cli, provider, model, taskPath: taskMdPath }, workerStore);
            if (outcome.ok) {
                result.queued.push(taskKey);
            }
            else {
                // AC-003/D-008: a refused task is never counted as queued, and the
                // refusal leaves its own durable ledger row (best-effort).
                reportWriteFaceRefusal(agenticdocRoot, taskKey, outcome, onRefusal);
            }
        }
        catch (err) {
            // Same fail-closed per-task isolation as the normal scan (AC-007): one
            // unusable target.yml never blocks the rest of the repair.
            console.error(`[mw] orphan repair refused for ${taskKey}: ${err instanceof Error ? err.message : String(err)}`);
        }
    }
    return result;
}
/** Claim-free repair dispatch for one ORPHANED key (AC-011/T-19).
 *
 * Scans `{key}/workers/<task-key>/task.md`, skips already-queued and conductor-owned
 * tasks, applies the run-identity gate, synthesizes the service-layer envelope
 * for old-form cards (with an `[ENVELOPE_FALLBACK]` audit), and queues the
 * candidate through {@link dispatchTask}. It never reads-modify-writes
 * `_index.parallel`, so the conductor's eligibility predicate is untouched: the
 * repair does not "take over" the key, it only unblocks its undispatched work. */
export async function repairDispatchOrphanedKey(workerStore, agenticdocRoot, key, opts = {}) {
    const empty = { key, queued: [], refused: [], synthesized: [], unsynthesizable: [] };
    const queue = workerStore.readQueue();
    const dispatched = new Set(queue.rows.map((e) => e.taskKey));
    const maxPerScan = opts.maxPerScan ?? readDispatchMaxPerScan(agenticdocRoot);
    const runVerdict = opts.runVerdict ?? defaultOrphanRunVerdict(agenticdocRoot, key);
    let taskDirs;
    try {
        taskDirs = fs.readdirSync(path.join(agenticdocRoot, key, "workers"), { withFileTypes: true });
    }
    catch {
        return empty;
    }
    const candidates = [];
    for (const taskDir of taskDirs) {
        if (!taskDir.isDirectory() || taskDir.name.startsWith("."))
            continue;
        const taskKey = taskDir.name;
        if (dispatched.has(taskKey))
            continue;
        const taskMdPath = path.join(agenticdocRoot, key, "workers", taskKey, "task.md");
        if (!fs.existsSync(taskMdPath))
            continue;
        if (isConductorTask(taskMdPath))
            continue;
        candidates.push({ taskKey, taskMdPath });
    }
    if (candidates.length === 0)
        return empty;
    return dispatchOrphanCandidates(workerStore, agenticdocRoot, key, candidates, maxPerScan, runVerdict, opts.onRefusal);
}
/** Does `key` have a live run? `run.json` pending/running (the worker's own
 * product, AC-022) or a queue row pending/running (the ledger's cache) both
 * count — an ORPHANED key must have neither (AC-011/T-19). */
function keyHasLiveRun(rows, key) {
    for (const row of rows) {
        if (row.status !== "pending" && row.status !== "running")
            continue;
        if (workerOwnerKey(row) === key)
            return true;
    }
    return false;
}
export async function dispatchNewTasks(workerStore, agenticdocRoot, opts = {}) {
    // Worker tasks live under {key}/workers/<task-key>/task.md (owner = AgenticTask
    // key) or _scratch/workers/<task-key>/task.md (keyless ad-hoc). Root-level
    // task dirs are no longer dispatched - they polluted the key namespace.
    if (!fs.existsSync(agenticdocRoot))
        return;
    // Read the queue once, through `readQueue()`: its rows drive the
    // already-queued set, and any unreadable row aborts the whole scan
    // (AC-020/AC-023). This is the guard IN-3 lacked — the old code built the set
    // from `readAll()`, so a row the parser silently dropped looked like a task
    // that had never run and the entire project was re-queued (252 rows within
    // one second, 2026-10-10T02:50:05Z, peak 66 concurrent workers).
    const queue = workerStore.readQueue();
    if (queue.unparsable.length > 0) {
        opts.onAlarm?.({
            kind: "queue-rows-unparsable",
            count: queue.unparsable.length,
            detail: queue.unparsable[0]?.reason,
        });
        return;
    }
    const dispatched = new Set(queue.rows.map((e) => e.taskKey));
    const scope = opts.scope ?? "cli";
    const maxPerScan = opts.maxPerScan ?? readDispatchMaxPerScan(agenticdocRoot);
    const queueIsEmpty = queue.rows.length === 0;
    let queued = 0;
    // Visibility for the "skipped, not refused" classes (T-19/T-20): keys
    // outside this window's scope, ORPHANED keys, and candidates whose product
    // already ended the run. They are aggregated per scan and go through the same
    // alarm channel (once per kind per session at the wiring), so a healthy
    // project sees at most one row per session instead of one per candidate.
    const outOfScope = [];
    // Only keys NOT already alerted this session (T-19: one `orphaned-keys`
    // alarm per key per session — a key that stays orphaned must not re-wake the
    // PM on every settled turn).
    const orphanedFresh = [];
    // T-24 (C-30): out-of-scope keys whose work was judged but whose owner
    // evidence is stale (`idle`/`done` row, no fresh state doc, no live claim).
    // They are NOT repaired; one neutral notice per key per session. `work` is
    // the RAW candidate list (what was judged), not the narrowed list, so the
    // PM can see which historical dirs triggered the judgement.
    const orphanBlocked = [];
    const runRefused = [];
    const flushScanAlarms = () => {
        if (outOfScope.length > 0) {
            opts.onAlarm?.({
                kind: "out-of-scope",
                count: outOfScope.length,
                detail: `${outOfScope.slice(0, 3).join(",")}${outOfScope.length > 3 ? ",…" : ""}`,
            });
        }
        if (orphanedFresh.length > 0) {
            opts.onAlarm?.({
                kind: "orphaned-keys",
                count: orphanedFresh.length,
                detail: `${orphanedFresh.slice(0, 3).join(",")}${orphanedFresh.length > 3 ? ",…" : ""}`,
            });
        }
        if (orphanBlocked.length > 0) {
            const shown = orphanBlocked
                .slice(0, 3)
                .map((b) => `${b.key}(工作=[${b.work.join(",")}]; 原因=${b.reason})`)
                .join(", ");
            opts.onAlarm?.({
                kind: "orphan-repair-skipped",
                count: orphanBlocked.length,
                detail: `${shown}${orphanBlocked.length > 3 ? ",…" : ""}`,
            });
        }
        if (runRefused.length > 0) {
            // Aggregate, bounded: the PM needs to see WHICH tasks and WHY (the
            // distinct reasons are what tells a stale ledger from a live run),
            // without one ledger row per candidate.
            const reasons = [...new Set(runRefused.map((r) => r.reason))].sort().join(",");
            const shown = runRefused
                .slice(0, 3)
                .map((r) => `${r.taskKey}:${r.reason}${r.detail ? `(${r.detail})` : ""}`)
                .join(",");
            opts.onAlarm?.({
                kind: "run-ledger-conflict",
                count: runRefused.length,
                detail: `${runRefused.length} refused (${reasons}): ${shown}${runRefused.length > 3 ? ",…" : ""}`,
            });
        }
    };
    let owners;
    try {
        owners = fs.readdirSync(agenticdocRoot, { withFileTypes: true });
    }
    catch {
        return;
    }
    const indexStore = new IndexStore(agenticdocRoot);
    for (const owner of owners) {
        if (!owner.isDirectory() || owner.name.startsWith("."))
            continue;
        // T-19: every owner directory is READ (the ownership scan is global and
        // read-only); the WRITE right is decided per key below. `scope: "cli"`
        // callers keep the historical whole-project behaviour.
        const inScope = scope === "cli" || owner.name === SCRATCH_WORKERS_KEY || owner.name === opts.watchedKey;
        const workersDir = path.join(agenticdocRoot, owner.name, "workers");
        let taskDirs;
        try {
            taskDirs = fs.readdirSync(workersDir, { withFileTypes: true });
        }
        catch {
            continue; // owner has no workers/ dir (plain key or meta entry)
        }
        // Collect undispatched tasks FIRST (AC-010): a key with nothing new to
        // queue must not even evaluate the docs gate — fully-queued undoc keys
        // are historical, not actionable, and gate noise for them drowns real
        // blockage in multi-key projects.
        const undispatched = [];
        for (const taskDir of taskDirs) {
            if (!taskDir.isDirectory() || taskDir.name.startsWith("."))
                continue;
            const taskKey = taskDir.name;
            if (dispatched.has(taskKey))
                continue;
            const taskMdPath = path.join(workersDir, taskKey, "task.md");
            if (!fs.existsSync(taskMdPath))
                continue;
            // D-104: conductor-owned tasks (origin: conductor) never enter the TS
            // dispatch path — not queued, not upserted, and not counted as
            // undispatched work for the docs gate below. The conductor is their
            // only queue writer; its reconciliation is the sole repair path.
            if (isConductorTask(taskMdPath))
                continue;
            // AC-022 (T-20): the product carries the run's own terminal state. A task
            // whose run.json already ended is never re-queued (the queue row is a
            // cache, the product is the truth) and a live run is never duplicated;
            // more work on a finished task means a NEW task_key declaring
            // `supersedes:`. Candidates without any run record keep the pre-T-20
            // behaviour (zero backfill, P-018). The task.md read is lazy, so a
            // candidate that already has a run record is decided without any read.
            if (opts.runVerdict) {
                const verdict = opts.runVerdict({
                    taskKey,
                    taskDir: path.join(workersDir, taskKey),
                    readTaskContent: () => fs.readFileSync(taskMdPath, "utf8"),
                });
                if (!verdict.ok) {
                    runRefused.push({ taskKey, reason: verdict.reason, detail: verdict.detail });
                    continue;
                }
            }
            undispatched.push({ taskKey, taskMdPath });
        }
        if (!inScope) {
            // Ownership classification only (T-19/T-22) — never write an
            // out-of-scope key from the automatic scan. A live claim (conductor
            // language: `state.CLAIM_LIVE`) means somebody else owns it; a live run
            // means it is already executing. Otherwise the key is a repair candidate
            // ONLY when it carries owner evidence: an `_index.parallel` row (T-19) OR
            // the key's own owner traces (`pm-state.md` machine lines / a worker
            // `trace.log`, T-22) — the row may have been lost to index rotation or the
            // non-atomic `dispatch_worker(key=…)` create-then-register pair. A bare
            // directory holding only `task.md` files is NOT ORPHANED: there is no
            // owner fact to reconstruct a row from, so it stays an actionable,
            // once-per-key notice and the scan writes nothing.
            const row = indexStore.findByKey(owner.name);
            if (row !== undefined && conductorClaimState(row.claimId) === "live")
                continue; // owned elsewhere — never write
            if (row === undefined && !keyHasOwnerTraces(agenticdocRoot, owner.name)) {
                if (undispatched.some((t) => !hasTerminalProduct(path.dirname(t.taskMdPath))) &&
                    opts.watchedKey !== undefined &&
                    !(opts.unregisteredWarned?.has(owner.name) ?? false)) {
                    opts.unregisteredWarned?.add(owner.name);
                    outOfScope.push(owner.name);
                }
                continue;
            }
            if (keyHasLiveRun(queue.rows, owner.name))
                continue; // running — not orphaned
            if (undispatched.length === 0)
                continue; // nothing to repair
            // T-24 (C-30): narrow the work (drop dirs with a terminal `output.md`;
            // for a stale owner, require the key's own state to name the task) and
            // require the owner evidence to still be current. A key whose only
            // evidence is an `idle`/`done` row with stale state docs is history:
            // never repaired, one neutral notice (req. 2/3). The reference filter
            // is part of the block path only — see the T-24 report.
            const scopeVerdict = judgeOrphanScope(agenticdocRoot, owner.name, undispatched, row);
            if (scopeVerdict.blockReason !== undefined) {
                if (!(opts.orphanedWarned?.has(owner.name) ?? false)) {
                    opts.orphanedWarned?.add(owner.name);
                    orphanBlocked.push({
                        key: owner.name,
                        work: undispatched.map((t) => t.taskKey),
                        reason: scopeVerdict.blockReason,
                    });
                }
                continue;
            }
            if (scopeVerdict.repairable.length === 0)
                continue; // only history left
            if (queued >= maxPerScan) {
                flushScanAlarms();
                opts.onAlarm?.({ kind: "dispatch-quota", count: queued });
                return;
            }
            const repair = await dispatchOrphanCandidates(workerStore, agenticdocRoot, owner.name, scopeVerdict.repairable, maxPerScan - queued, opts.runVerdict ?? defaultOrphanRunVerdict(agenticdocRoot, owner.name), opts.onRefusal);
            queued += repair.queued.length;
            if (!(opts.orphanedWarned?.has(owner.name) ?? false)) {
                opts.orphanedWarned?.add(owner.name);
                orphanedFresh.push(owner.name);
            }
            continue;
        }
        if (undispatched.length === 0)
            continue;
        // AC-020: an empty queue plus product evidence in the very tasks we are
        // about to queue is the IN-3 shape — the queue lost its rows while the
        // work had already run. Refuse the whole scan instead of re-running
        // history; a real fresh project has no such evidence and dispatches.
        if (queueIsEmpty && undispatched.some((t) => hasProductEvidence(path.dirname(t.taskMdPath)))) {
            flushScanAlarms();
            opts.onAlarm?.({ kind: "queue-unreadable", count: undispatched.length, detail: owner.name });
            return;
        }
        // Docs gate, phase-tiered (mw-worker-visibility-gate D-110): the tier comes
        // from the SCAN KEY's own phase (its pm-state '- Phase:' line), never from
        // this window's watch — the background scan and the dispatch_worker tool
        // entry must not diverge. _scratch is the ad-hoc escape hatch. Report
        // each blocked key at most once.
        if (owner.name !== SCRATCH_WORKERS_KEY) {
            const ownerPhase = new StateManager(agenticdocRoot, owner.name).read().phase ?? "";
            const gaps = dispatchDocGaps(agenticdocRoot, owner.name, ownerPhase);
            if (gaps.length > 0) {
                if (!opts.warnedKeys?.has(owner.name)) {
                    // Mark as warned only when the notifier actually broadcast —
                    // a suppressed broadcast (scoped to another window's key) must
                    // not burn this key's once-per-session slot (review m1).
                    if (opts.onDocGate?.(owner.name, gaps) !== false) {
                        opts.warnedKeys?.add(owner.name);
                    }
                }
                continue;
            }
        }
        for (const { taskKey, taskMdPath } of undispatched) {
            // AC-021: one scan may queue at most `maxPerScan` rows. Exceeding the
            // quota means the scan is looking at something it does not understand,
            // not that hundreds of tasks need running.
            if (queued >= maxPerScan) {
                flushScanAlarms();
                opts.onAlarm?.({ kind: "dispatch-quota", count: queued });
                return;
            }
            const taskContent = fs.readFileSync(taskMdPath, "utf8");
            const { cli, provider } = pickWorkerRoute(taskContent);
            const model = readModel(taskContent);
            try {
                const outcome = await dispatchTask({
                    taskKey,
                    status: "pending",
                    cli,
                    provider,
                    model,
                    taskPath: taskMdPath,
                }, workerStore);
                if (outcome.ok) {
                    queued += 1;
                }
                else {
                    // AC-003/D-008: a write-face refusal is a return value, not a
                    // throw — counting it as queued would both falsify the quota and
                    // leave the refusal without any durable trace.
                    reportWriteFaceRefusal(agenticdocRoot, taskKey, outcome, opts.onRefusal);
                }
            }
            catch (err) {
                // Fail-closed (mw-dual-workspace AC-007): an unusable target.yml
                // must never silently degrade to an un-injected task.md — the task
                // stays undispatched and is retried on the next scan once the
                // config is fixed. Per-task isolation: one bad task never blocks
                // the rest of the scan.
                console.error(`[mw] dispatch refused for ${taskKey}: ${err instanceof Error ? err.message : String(err)}`);
            }
        }
    }
    flushScanAlarms();
}
/** Continuation directive appended to terminal worker results: the finish
 * call wakes an idle PM (triggerTurn) — this line tells it what "continue the
 * PM loop" means per terminal status, so results are processed and the next
 * task is dispatched without the user re-prompting. Timeout failures get an
 * explicit retry policy (AC-004/D-005): the Exit Reason in the readback body
 * distinguishes idle (true hang) from wall (healthy but out of budget). */
const PM_CONTINUE_HINT = "[mw] worker 终态回读。请继续 PM 循环：吸收上述结果（done→推进下一任务/phase；failed→读 worker.log 与 trace.log 排查后决定重试或修复；needs-clarification→整理问题向用户澄清；超时失败（Exit Reason 含 idle/wall timeout）→ wall 型用双倍 timeout 预算重派一次，再失败转 PM 直执，idle 型直接排查环境），然后派发下一个任务或汇报阶段完成。吸收终态结果后调用 ack_worker_result(task_key)（或 /mw ack all）确认处理完成，widget 待处理区才会清空。";
/** Runtime stats for terminal worker summaries (AC-013):
 * ` (6m-style coarse duration, ph i/n)`. Preference order: exact [START]→[END]
 * interval from trace.log (present on every new-bundle terminal task), ≥2
 * [HEARTBEAT] lines (older format), then the queue row's dispatchedAt→updatedAt
 * (coarse but always present). Empty when nothing is derivable. */
function heartbeatStatsSuffix(taskDir, entry) {
    const prog = readTaskProgress(taskDir);
    if (prog?.startTs && prog.endTs) {
        const durMs = Math.max(0, Date.parse(prog.endTs) - Date.parse(prog.startTs));
        const ph = prog.endPhases && prog.endPhases !== "-" ? `, ph ${prog.endPhases}` : "";
        return ` (${formatHeartbeatAge(durMs)}${ph})`;
    }
    const hb = prog?.heartbeat;
    if (hb && hb.count >= 2) {
        const durMs = Math.max(0, Date.parse(hb.lastTs) - Date.parse(hb.firstTs));
        const ph = hb.phase === "-" ? "" : `, ph ${hb.phase}/${hb.phaseTotal}`;
        return ` (${formatHeartbeatAge(durMs)}${ph})`;
    }
    const durMs = Date.parse(entry.updatedAt) - Date.parse(entry.dispatchedAt);
    if (!Number.isNaN(durMs) && durMs > 0)
        return ` (${formatHeartbeatAge(durMs)})`;
    return "";
}
/** Session entry type recording a delivered gate reminder. Read back on
 * restart/resume so the same ledger row is never pushed twice (design D-010).
 * Same mechanism as WATCH_ENTRY_TYPE / AUTOPILOT_SEEN_ENTRY_TYPE. */
export const GATE_REMINDER_ENTRY_TYPE = "agent-team-loop:gate-reminder-seen";
/** Session entry type recording a DROPPED gate reminder (mw-autopilot-gate-
 * alarm-liveness AC-010): "no watch", "other key" and "read error" drops must
 * leave a visible record, never vanish silently. Deliberately a SEPARATE type
 * and WITHOUT `seq`: the delivery resume path reads `e.data?.seq` from
 * {@link GATE_REMINDER_ENTRY_TYPE} entries to advance `reminderWatermark`, so a
 * drop record carrying a `seq` would suppress the real delivery that follows
 * it (DRQ-2 C5 counter-example). */
export const GATE_REMINDER_DROPPED_ENTRY_TYPE = "agent-team-loop:gate-reminder-dropped";
/** Record one dropped reminder into the session (visible via the transcript /
 * session file). Deduplicated per `${gateId}:${n}:${reason}` for this process:
 * the poll loop runs every 4 s, so an undeduped drop would append an entry per
 * tick forever. `reason` is one of the three literal drop causes. */
export function recordDroppedGateReminder(pi, seen, reminder, reason, error) {
    const dedup = `${reminder.gateId}:${reminder.reminderN}:${reason}`;
    if (seen.has(dedup))
        return;
    seen.add(dedup);
    pi.appendEntry(GATE_REMINDER_DROPPED_ENTRY_TYPE, {
        gateId: reminder.gateId,
        n: reminder.reminderN,
        gateKey: reminder.gateKey,
        reason,
        ...(error === undefined ? {} : { error }),
    });
}
export function startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, ui, pollIntervalMs = POLL_INTERVAL_MS) {
    // Baseline snapshot: rows already terminal when this window opens are
    // history — never replay their summaries. Only transitions observed while
    // this session is open are notified, at most once each.
    const notified = new Set(workerStore
        .readAll()
        .filter((e) => isTerminal(e.status))
        .map((e) => e.taskKey));
    // AC-011/AC-012: subset of `notified` actually delivered this session. Feeds the
    // unread counter only (see the module note above) — never a suppression.
    const readbackDelivered = new Set();
    // Running workers already escalated for divergence (AC-004): one PM wake
    // per task, at the first mid/high convergence checkpoint.
    const escalated = new Set();
    let widgetShown = false;
    // Pending-gate reminder delivery (AC-005/AC-018; design D-005/D-006/D-010).
    // The conductor (Python) is the sole decider and writer; this loop is the
    // only channel that wakes an idle PM (deliverPmAlert → triggerTurn). The same
    // ledger row must never wake the PM twice:
    //   - `reminderWatermark` = highest delivered ledger `seq`, persisted per
    //     session as a pi entry: a restart/resume continues where it left off and
    //     an append-only ledger row can never be re-delivered;
    //   - `unsequencedSeen` is the process-local fallback for a row missing `seq`
    //     (the conductor always sets it, so this is belt-and-braces only).
    // The watermark starts at the ledger's high-water mark at window open, so a
    // fresh window does not replay reminders that predate it (mirrors the
    // `notified` worker baseline). `reminderHistoryRead` gates the one-shot
    // resume path: when this session already recorded deliveries, the watermark
    // drops back to the last recorded seq so rows appended while the window was
    // down still reach the PM.
    const unsequencedSeen = new Set();
    // AC-010: dropped reminders leave a visible record; dedup is process-local.
    const droppedRemindersSeen = new Set();
    let reminderWatermark = 0;
    {
        const rows = readGateReminders(agenticdocRoot);
        for (const r of rows)
            if (r.seq > reminderWatermark)
                reminderWatermark = r.seq;
    }
    let reminderHistoryRead = false;
    return setInterval(() => {
        try {
            const entries = workerStore.readAll();
            // AC-012/AC-013 unread counter input. `acked` is read only when the queue
            // actually holds terminal rows, so a queue with none adds no I/O. The
            // counter itself runs on the rows already read here (no second queue read).
            const acked = entries.some((e) => isTerminal(e.status)) ? new Set(ackStore.readAll().keys()) : undefined;
            // Live bottom widget for the watched key (per-window state, NOT the
            // shared _index.parallel active set — every window decides its own key).
            if (watch.key) {
                const lines = renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, watch.key, watch.dispatchedTaskKeys);
                // AC-012 (option B): an open-time terminal row is not replayed, but the
                // unread tail keeps it visible until acked.
                const unread = acked
                    ? countUnreadTerminal(entries.filter((e) => ownerKeyOf(e, agenticdocRoot) === watch.key), acked, readbackDelivered)
                    : 0;
                if (unread > 0)
                    lines.push(`  ${unread} unread — terminal result(s) not delivered this session`);
                applyWatchWidget(ui, lines);
                widgetShown = true;
            }
            else {
                // AC-013: with no watched key the window renders at most ONE line — the
                // unread count over the whole queue — and never broadcasts a message.
                const unread = acked ? countUnreadTerminal(entries, acked, readbackDelivered) : 0;
                if (unread > 0) {
                    applyWatchWidget(ui, [`[mw] no watched key | ${unread} unread terminal result(s)`]);
                    widgetShown = true;
                }
                else if (widgetShown) {
                    applyWatchWidget(ui, undefined);
                    widgetShown = false;
                }
            }
            // Divergence escalation (AC-004): running workers past the convergence
            // checkpoint whose machine risk is mid/high wake the PM once per task
            // with the evidence — the PM (fullest context) decides continue /
            // descope / kill + split / takeover. Low-risk checkpoints stay in the
            // widget only; no cross-window broadcast (scoped to the watched key ∪
            // this window's dispatched tasks — mw-crosskey-risk-escalation D-101).
            for (const entry of entries) {
                if (entry.status !== "running" || escalated.has(entry.taskKey))
                    continue;
                // Ownership is "watched key OR dispatched by this window": a task this
                // window sent across keys (explicit `key:` dispatch, gate fallback to
                // _scratch) is still this PM's work, while other windows' workers stay
                // silent. `!watch.key` stays first: a window watching nothing must not
                // start delivering off historical dispatch records.
                const ownerKey = ownerKeyOf(entry, agenticdocRoot);
                const owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false;
                if (!watch.key || (ownerKey !== watch.key && !owned))
                    continue;
                const ck = readTaskProgress(path.dirname(entry.taskPath))?.checkpoint;
                if (!ck || ck.risk === "low")
                    continue;
                escalated.add(entry.taskKey);
                const taskDir = path.dirname(entry.taskPath);
                // Cross-key alerts carry the owner key right after the worker name
                // (D-102) so the PM can tell an off-watch task from a watched-key one;
                // the watched-key label keeps the byte-exact `'name' ` form (AC-004).
                const workerLabel = ownerKey === watch.key ? `'${entry.taskKey}' ` : `'${entry.taskKey}'（owner key=${ownerKey}）`;
                deliverPmAlert(pi, `[mw] 发散风险：worker ${workerLabel}检查点 risk=${ck.risk}` +
                    `（elapsed ${Math.round(ck.elapsedS / 60)}m，reads=${ck.reads} writes=${ck.writes}，phases=${ck.phases}，` +
                    `重复读 top=${ck.repeatTop}）。机器判据仅供参考——请结合本 key 最全上下文判断：继续等待 / steer 收窄范围 / 终止并分拆重派 / PM 直执。` +
                    `证据：${path.join(taskDir, "trace.log")}（[CHECKPOINT] 行）与 ${path.join(taskDir, "progress.md")}（自评行；无写工具角色另含框架机器行）。`);
            }
            for (const entry of entries) {
                if (notified.has(entry.taskKey) || !isTerminal(entry.status))
                    continue;
                // C3 — no watched key: stay silent (no cross-window broadcast), but
                // consume the terminal transition for this session so adopting a key
                // later cannot resurrect it (locked by "stays silent without a watched
                // key and for tasks under other keys"). NOT counted as delivered: the
                // AC-013 unread counter must still surface it.
                if (!watch.key) {
                    notified.add(entry.taskKey);
                    continue;
                }
                // C1 — another key's terminal row: not this window's business AND not
                // consumed, so the owner window (or this window after a key takeover)
                // still gets its one readback. No I/O on this path (R5).
                if (ownerKeyOf(entry, agenticdocRoot) !== watch.key)
                    continue;
                // Owned + watched: account the delivery exactly once. This stays before
                // `recordWriteScopeResidualRisks` below — `notified` is also the
                // per-task-per-session bound for that alarm (`recordDispatchAlarm` has no
                // dedup of its own).
                notified.add(entry.taskKey);
                readbackDelivered.add(entry.taskKey);
                // Task dir from the queue row taskPath: works for keyed {key}/workers/<task-key>/ and legacy root paths.
                const taskDir = path.dirname(entry.taskPath);
                // AC-007/DD-08 residual risk: a contract-allowed write whose basename
                // still names a deny-list artifact is only observable here (the guard
                // wrote `blocked=false risk=deny-basename` and moved on). Reuses the
                // single dispatch-alarm ledger channel; `notified` above bounds it to
                // once per task per session.
                recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
                // Terminal readback (AC-014): inject the full output.md body into
                // the conversation so worker results reach the PM without manual
                // file reads. Falls through to the spawn-failure / no-output
                // notices when there is nothing to read back. Sent via
                // deliverWorkerResult (triggerTurn) so an idle PM wakes up,
                // processes the result, and runs the next step — the finish call
                // of dispatch → monitor → finish call → pm run (AC-015).
                const header = `[${entry.taskKey}] ${entry.status}${heartbeatStatsSuffix(taskDir, entry)}`;
                const body = readOutputBody(taskDir);
                if (body) {
                    deliverWorkerResult(pi, `${header}:\n\n${body}\n\n${PM_CONTINUE_HINT}`);
                }
                else {
                    // Terminal but no output.md summary — never stay silent. Prefer the
                    // launcher's exact spawn-failure reason (e.g. missing credential) over
                    // the generic crash/timeout guess; both point at the per-task log.
                    const logPath = path.join(taskDir, "worker.log");
                    const spawnFailure = readSpawnFailure(taskDir);
                    deliverWorkerResult(pi, `${header} — ${spawnFailure
                        ? `${spawnFailure}。日志：${logPath}`
                        : `无 output.md 摘要（worker 可能崩溃/超时）。日志：${logPath}`}\n\n${PM_CONTINUE_HINT}`);
                }
            }
            // Pending-gate reminders (appended last: the worker terminal-readback
            // order above must not change). Read-only — the ledger belongs to the
            // conductor; this branch never writes it.
            const reminders = readGateReminders(agenticdocRoot);
            if (!reminderHistoryRead) {
                reminderHistoryRead = true;
                let delivered = 0;
                try {
                    for (const e of ui.ctx?.sessionManager.getEntries() ?? []) {
                        if (e.type !== "custom" || e.customType !== GATE_REMINDER_ENTRY_TYPE)
                            continue;
                        const data = e.data;
                        if (typeof data?.seq === "number" && data.seq > delivered)
                            delivered = data.seq;
                    }
                }
                catch {
                    // Session entries unavailable — treat this as a fresh window.
                }
                // Resume from the recorded point (may be below the open-time baseline,
                // so rows appended while this window was down are still delivered);
                // a fresh session keeps the no-replay baseline.
                if (delivered > 0)
                    reminderWatermark = delivered;
            }
            for (const reminder of reminders) {
                // Multi-window scope (D-010): a keyed gate is only this window's
                // business when it watches that key; keyless/stage-level gates fall
                // through to the per-session watermark. A window watching nothing
                // stays silent, like the worker summaries above — but AC-010 forbids
                // a SILENT drop, so each discard is recorded first.
                if (!watch.key) {
                    recordDroppedGateReminder(pi, droppedRemindersSeen, reminder, "no-watch");
                    continue;
                }
                if (reminder.gateKey !== "" && reminder.gateKey !== watch.key) {
                    recordDroppedGateReminder(pi, droppedRemindersSeen, reminder, "other-key");
                    continue;
                }
                const dedup = `${reminder.gateId}:${reminder.reminderN}`;
                if (reminder.seq > 0) {
                    // Session watermark: the row was delivered already (this tick or a
                    // previous session) whenever its seq is not ahead of the mark.
                    if (reminder.seq <= reminderWatermark)
                        continue;
                    reminderWatermark = reminder.seq;
                }
                else {
                    if (unsequencedSeen.has(dedup))
                        continue;
                    unsequencedSeen.add(dedup);
                }
                // Persist the delivery so /new, /resume and restarts do not replay it.
                pi.appendEntry(GATE_REMINDER_ENTRY_TYPE, {
                    seq: reminder.seq,
                    gateId: reminder.gateId,
                    n: reminder.reminderN,
                });
                const scope = reminder.gateKey === "" ? "stage" : `key=${reminder.gateKey}`;
                deliverPmAlert(pi, `[mw] 门提醒（${reminder.reminderN}）：gate ${reminder.gateId}（kind=${reminder.gateKind}，${scope}）已 pending 超阈，等待人工应答。` +
                    `（判定由 conductor 完成；用 /autopilot gates 查看，/autopilot gate ${reminder.gateId} approve|reject 应答。）` +
                    (reminder.detail ? ` ${reminder.detail}` : ""));
            }
        }
        catch (err) {
            // Transient I/O error (e.g. EACCES during concurrent rename) — skip this
            // tick, but AC-010 forbids a silent drop: leave one visible read-error
            // record (deduplicated, no `seq`, so it cannot advance the watermark).
            recordDroppedGateReminder(pi, droppedRemindersSeen, { gateId: "-", reminderN: 0, gateKey: "" }, "read-error", err instanceof Error ? err.message : String(err));
        }
    }, pollIntervalMs);
}
/** Marker opening the injected parallel-protocol block, and the idempotency
 * guard: a handler that already sees it in the chained system prompt must not
 * append it a second time (two loaded bundle copies would otherwise duplicate
 * the text on every run). */
export const PARALLEL_PROTOCOL_MARKER = "[mw] 并行优先协议";
/** Static parallel-first rules appended to the PM window's system prompt once
 * per agent run (mw-parallel-protocol). Static on purpose: a constant suffix
 * keeps the system-prompt prefix cacheable, and `before_agent_start` costs no
 * session tokens (an injected message would accumulate one per run). The two
 * conflict surfaces are deliberately different: research/review workers are
 * read-only (worker-mode.ts TOOL_ALLOWLISTS), so research batches in the
 * spec/design phases parallelize freely and only need a unique note file per
 * research question; coding workers share files and must be split by
 * file/module boundary. PM-only by construction: pmActivate() runs only when
 * PI_WORKER_TASK is unset (index.ts). */
export const PARALLEL_PROTOCOL = [
    `${PARALLEL_PROTOCOL_MARKER}（PM 常驻规则）：`,
    "1. 拆解任何 phase（spec/design/plan/tasks）之前，先做并行性分析：可并行单元 / 共享资源与文件冲突面 / 必须串行的理由。",
    "2. spec/design 的调研与证据收集默认全并行：把调研拆成互不重叠的研究问题 RQ-1..N，一次性派发 N 个 type: research worker",
    "   （只读角色，彼此无文件冲突），每个 RQ 只写唯一的 evidence/research/<phase>-<rq-slug>-<date>.md；禁止两个 worker 写同一文件。",
    "3. 编码按文件/模块边界并行：同一文件同一时刻只允许一个 worker。",
    "4. 相位文档（spec.md / design.md）由 PM 自己串行写，不派 worker。",
    "5. 派发前先看 widget 上的 running worker 数：能并行就不要串行等待；worker 终态回读后立刻补派下一批。",
    "6. 引用图片/截图/mockup 的任务用 type: vision 派发（视觉角色，worker 读取图片文件并受 image 能力门禁约束）。",
].join("\n");
export function pmActivate(pi) {
    const projectDir = process.cwd();
    const agenticdocRoot = resolveAgenticdocRoot(projectDir);
    const workerStore = new WorkerStore(agenticdocRoot);
    const ackStore = new AckStore(agenticdocRoot);
    const indexStore = new IndexStore(agenticdocRoot);
    // Per-window watch state: the key THIS window explicitly executes (set via
    // /mw-watch or /pm-key switch|new). Worker summaries and the bottom progress
    // widget are scoped to it — replacing the old global active-keys matching
    // that made every window notify about every active key.
    const watch = { key: undefined };
    const ui = { ctx: undefined };
    const refreshWatch = (ctx) => {
        if (!watch.key) {
            setWatchWidget(ctx, undefined);
            return;
        }
        setWatchWidget(ctx, renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, watch.key, watch.dispatchedTaskKeys));
    };
    // Register commands and tools during loading (safe — not action methods)
    registerPmKeyCommands(pi, indexStore, watch, refreshWatch, agenticdocRoot);
    registerPmSaveCommand(pi, indexStore, workerStore, watch, agenticdocRoot);
    registerMwCommands(pi, projectDir, workerStore, ackStore, watch, agenticdocRoot);
    registerMwTools(pi, projectDir);
    registerAdvancePhaseTool(pi, projectDir, indexStore);
    registerWorkerTools(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, projectDir);
    registerSwitchKeyTool(pi, indexStore, watch, refreshWatch, agenticdocRoot);
    registerWorkerCommands(pi, workerStore, indexStore, agenticdocRoot, watch, projectDir);
    // RAG tool surface (D-002): registration is structural — an empty enabled
    // set registers nothing and probes nothing. A broken config must not take
    // the whole PM window down (dispatch is gated separately in ui-bridge).
    try {
        registerRagTools(pi, projectDir);
    }
    catch (err) {
        console.error(`[mw] rag tools disabled: ${err instanceof Error ? err.message : String(err)}`);
    }
    registerWatchCommand(pi, watch, refreshWatch, indexStore);
    // Autopilot console (T-15): /autopilot status|gates|gate|timeline|enable|
    // disable|pause|resume|roadmap — stateless, file-derived (D-005).
    registerAutopilotCommands(pi, projectDir);
    // Dispatch model chain, main-window side (mw-dispatch-models): record this
    // window's model for worker inheritance and apply a configured `main` role.
    registerMainWindowModel(pi);
    // Hard gate: pm-state.md's '- Phase:' / '- Claim-Id:' interface lines are
    // script-owned (advance_phase.py / update_index.py). Hand-editing them is
    // how phase gates get bypassed (mw-worker-timeout-convergence: pm-state
    // hand-set to EXECUTE while _index.parallel stayed at SPEC), so the edit is
    // blocked at the tool layer and the agent is pointed at the script.
    registerPmStateGuard(pi, projectDir, agenticdocRoot);
    // Parallel-first protocol (mw-parallel-protocol): append the constant block
    // to this run's system prompt. Appending (never replacing) preserves what
    // other extensions chained in before us.
    pi.on("before_agent_start", (event) => {
        const base = typeof event.systemPrompt === "string" ? event.systemPrompt : "";
        if (base.includes(PARALLEL_PROTOCOL_MARKER))
            return undefined;
        return { systemPrompt: base === "" ? PARALLEL_PROTOCOL : `${base}\n\n${PARALLEL_PROTOCOL}` };
    });
    // Start worker status poll loop (setInterval is safe; displaySummary inside fires later)
    const pollHandle = startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, ui);
    // Session teardown stops the loop (review m3): a fresh runtime re-runs
    // pmActivate and starts a new one, so this only removes the zombie that
    // would keep ticking against a disposed context after /reload or session
    // replacement. It also stops the autopilot monitor panel (AC-018/VC-023):
    // the next session_start re-arms it via autoStartMonitor, so the panel is
    // never left pointing at a disposed ctx (and no interval leaks). stopMonitor
    // is a no-op when no panel is active — it never clears non-active state.
    pi.on("session_shutdown", () => {
        clearInterval(pollHandle);
        stopMonitor();
    });
    // After each agent turn, scan for new task.md files and dispatch them (AC-030).
    // Undocumented keys are skipped and reported once per session (docs gate).
    // Gate broadcast is scoped to this window's watched key (AC-011). The SCAN
    // is global and read-only (T-19): the write right covers this window's key,
    // `_scratch`, and ORPHANED keys (claim-free repair).
    const docGateWarned = new Set();
    // Dispatch alarms are once per kind per session for the REFUSAL kinds: a
    // queue that stays broken must not append a ledger row or wake the PM on
    // every settled turn. `orphaned-keys` is deduped per KEY inside the scan
    // (`orphanedWarned`), so a newly orphaned key is still reported immediately
    // while a key that stays orphaned is not re-reported every turn.
    const dispatchAlarmsSeen = new Set();
    const orphanedWarned = new Set();
    // T-22: `out-of-scope` notice dedup is per KEY (not per kind): a key left
    // unregistered with undispatched work must be reported once per session, not
    // on every settled turn, while a DIFFERENT key can still surface later.
    const unregisteredWarned = new Set();
    pi.on("agent_settled", () => {
        dispatchNewTasks(workerStore, agenticdocRoot, {
            warnedKeys: docGateWarned,
            onDocGate: makeScopedDocGateNotifier(pi, watch),
            scope: "pm",
            watchedKey: watch.key,
            orphanedWarned,
            // Per-task write-face refusals are recorded by the scan itself (one
            // ledger row each, never deduped); this only delivers the human alert.
            onRefusal: (text) => deliverPmAlert(pi, text),
            unregisteredWarned,
            // AC-022 (T-20): the product decides. A candidate whose own run.json
            // already ended (or is still live) is refused before any queue write;
            // `supersedes:` in task.md is the only way to replace a finished run, and
            // the replaced directory is never touched. Every read is best-effort
            // ("no information" ⇒ pre-T-20 behaviour, zero backfill).
            runVerdict: (task) => evaluateRunIdentity({
                taskDir: task.taskDir,
                readTaskContent: task.readTaskContent,
                resolveTaskDir: (key) => {
                    const dir = path.join(path.dirname(task.taskDir), key);
                    return fs.existsSync(dir) ? dir : undefined;
                },
            }),
            onAlarm: (alarm) => {
                // The per-kind gate is for refusals only; a notice (`orphaned-keys`)
                // is already deduped per key by the scan and must still reach the PM
                // when a DIFFERENT key becomes orphaned later in the session.
                if (!isNoticeDispatchAlarm(alarm.kind)) {
                    if (dispatchAlarmsSeen.has(alarm.kind))
                        return;
                    dispatchAlarmsSeen.add(alarm.kind);
                }
                recordDispatchAlarm(agenticdocRoot, alarm);
                deliverPmAlert(pi, formatDispatchAlarm(alarm));
            },
        }).catch(() => {
            // Dispatch errors are non-fatal — PM loop continues
        });
    });
    // Spec-write auto-takeover: tool_execution_end carries no args, so correlate
    // them with the args captured on tool_execution_start via toolCallId. Only
    // write/edit calls are tracked; the map entry is consumed on end.
    const pendingToolArgs = new Map();
    pi.on("tool_execution_start", (event) => {
        if (event.toolName === "write" || event.toolName === "edit") {
            pendingToolArgs.set(event.toolCallId, { toolName: event.toolName, args: event.args });
        }
    });
    // Evidence-review notices fire once per (key, phase) per session.
    const evidenceReviewNotified = new Set();
    pi.on("tool_execution_end", (event, ctx) => {
        const pending = pendingToolArgs.get(event.toolCallId);
        pendingToolArgs.delete(event.toolCallId);
        if (!pending || event.isError)
            return;
        const target = docWriteTarget(pending.toolName, pending.args, projectDir, agenticdocRoot);
        if (target) {
            autoTakeOverFromDoc(pi, indexStore, watch, refreshWatch, target.key, target.doc, agenticdocRoot, ctx).catch(() => {
                // Takeover failures (e.g. lock contention) must never disturb the turn
            });
            // Phase-doc write with its evidence already present → notice that the
            // doc's claims can be re-reviewed against the notes (plan has no
            // evidence phase). A notice, never an injected instruction.
            if (target.doc !== "plan.md") {
                evidenceReviewNotice(ctx, target.key, target.doc === "spec.md" ? "spec" : "design", agenticdocRoot, evidenceReviewNotified);
            }
            return;
        }
        // Research-note write: not a claim signal, but it may complete the
        // evidence set for an already-written phase doc → review notice.
        const ev = evidencePhaseFromWrite(pending.toolName, pending.args, projectDir, agenticdocRoot);
        if (ev) {
            evidenceReviewNotice(ctx, ev.key, ev.phase, agenticdocRoot, evidenceReviewNotified);
        }
    });
    // Defer action method calls to after runner.initialize() (session_start fires post-init)
    pi.on("session_start", async (_event, ctx) => {
        // Capture the UI context so the poll loop can render the bottom widget.
        ui.ctx = ctx;
        // Autopilot progress panel: auto-show for enabled projects so a stalled
        // key is visible without anyone running a command (mw-autopilot-stall-feedback
        // AC-008). An explicit /autopilot monitor off suppresses it for this session.
        autoStartMonitor(ctx, projectDir);
        // Resume the watched key this session had before restart/resume.
        await restoreWatch(pi, watch, indexStore, workerStore, ackStore, agenticdocRoot, ctx);
        // Auto-init project if it hasn't been initialized yet. Gate on .agenticdoc
        // (the project marker mw init creates), NOT on a project-local bundle copy:
        // the extension is now installed GLOBALLY (mw setup), so no project-local
        // bundle exists and checking for one would re-run init on every session.
        const initialized = fs.existsSync(path.join(projectDir, ".agenticdoc"));
        if (!initialized) {
            const result = initMw(projectDir);
            if (result.ok) {
                displaySummary(pi, "[mw] Project initialized — .agenticdoc/ .mw/ .pi/extensions/ created.");
            }
            else {
                displaySummary(pi, `[mw] Init failed: ${result.error}`);
                return;
            }
        }
        // Auto-start mw background service if not already running.
        // After spawning, poll for the PID file so the agent's first turn doesn't
        // race against Python startup and falsely report mw as not running.
        // Stability window: the PID must stay alive for 3s — mw serve can die
        // right after startup (route precheck failure) and the old check would
        // report a false "started" in that window (mw-dispatch-reliability AC-005).
        const mwStatus = getMwStatus(projectDir);
        if (!mwStatus.running) {
            const started = startMw(projectDir);
            if (started) {
                const confirmed = await waitForMwStart(projectDir, 8000);
                displaySummary(pi, confirmed
                    ? "[mw] Background service started."
                    : "[mw] Background service 启动未确认（可能预检失败或仍在启动）——运行 /mw doctor 诊断。");
            }
            else {
                displaySummary(pi, "[mw] Could not find mw.py — run `mw start --project=.` manually.");
            }
        }
        else {
            // Stale-serve detection: a serve started before the current mw code
            // silently misses features (e.g. conductor supervision) — surface it
            // instead of letting /autopilot enable promise a conductor that never
            // spawns.
            const stale = serveStaleness(projectDir);
            if (stale?.stale) {
                displaySummary(pi, `[mw] serve (PID ${mwStatus.pid}) is running stale code — ${stale.detail}. Run /mw restart.`);
            }
        }
        // The project goal is the north-star every key/spec derives from.
        // Do NOT fabricate a placeholder — if it isn't established yet, softly
        // guide the user into the goal brainstorm workflow (/goal). An
        // established goal (or a legacy goal.md with content) is left untouched.
        // Headless sessions skip the goal nudge (see nudgeGoalUnestablished).
        nudgeGoalUnestablished(pi, agenticdocRoot, ctx.hasUI);
    });
}
//# sourceMappingURL=pm-orchestrator.js.map