import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
import { AckStore } from "../shared/ack-store.ts";
import { IndexStore } from "../shared/index-store.ts";
import { type RunIdentityRefusal } from "../shared/run-store.ts";
import { WorkerStore } from "../shared/worker-store.ts";
import { type DispatchRefusal } from "./task-dispatcher.ts";
import { type PmUiHolder, type PmWatchState } from "./ui-bridge.ts";
export type PhaseDocName = "spec.md" | "design.md" | "plan.md";
/** The key a phase-doc write/edit belongs to (see docWriteTarget). */
export declare function keyFromDocWrite(toolName: string, args: unknown, projectDir: string, agenticdocRoot: string): string | undefined;
/** Which phase doc was written/edited (see docWriteTarget). */
export declare function docFromWrite(toolName: string, args: unknown, projectDir: string, agenticdocRoot: string): PhaseDocName | undefined;
export type EvidencePhase = "spec" | "design";
/** The evidence-note write target, when the tool path resolves to
 * {agenticdocRoot}/{key}/evidence/research/spec-*.md | design-*.md. Not a
 * claim signal (only phase docs are) — but the moment evidence lands is the
 * moment an already-written phase doc's claims can be re-reviewed against
 * it. */
export declare function evidencePhaseFromWrite(toolName: string, args: unknown, projectDir: string, agenticdocRoot: string): {
    key: string;
    phase: EvidencePhase;
} | undefined;
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
export declare function evidenceReviewNotice(ctx: ExtensionContext, key: string, phase: EvidencePhase, agenticdocRoot: string, notified: Set<string>): void;
/** Nudge the user toward the /goal brainstorm when the project goal is not
 * yet established. Headless sessions (print/-p) skip the nudge entirely:
 * sendUserMessage starts a generation immediately, and the queued -p prompt
 * would collide with it ("Agent is already processing") before ever reaching
 * the model — `pi -p` in any project without an established goal.md would
 * hard-fail at startup. */
export declare function nudgeGoalUnestablished(pi: ExtensionAPI, agenticdocRoot: string, hasUI: boolean): void;
/** Auto-takeover on phase-doc write: writing/editing {key}/spec.md, design.md,
 * or plan.md is this window saying "I am now executing key X" — claim it and
 * watch it, exactly like /pm-key switch. A live foreign claim blocks the claim
 * (watch-only) but never the watch itself. Writing design.md / plan.md also
 * runs the next-phase evidence gate (mirrors advance_phase.py): the previous
 * phase's research notes must exist, or the user is warned immediately. */
export declare function autoTakeOverFromDoc(pi: ExtensionAPI, indexStore: IndexStore, watch: PmWatchState, refreshWatch: (ctx: ExtensionContext) => void, key: string, doc: PhaseDocName, agenticdocRoot: string, ctx: ExtensionContext): Promise<void>;
/** Restore this window's watched key from the session file (survives restart
 * and resume) and re-render the bottom widget. A watch that came with a key
 * takeover re-claims the key with this process's identity — quietly, unless
 * another live window took it over in the meantime. */
export declare function restoreWatch(pi: ExtensionAPI, watch: PmWatchState, indexStore: IndexStore, workerStore: WorkerStore, ackStore: AckStore, agenticdocRoot: string, ctx: ExtensionContext): Promise<void>;
/** Why a dispatch scan refused to queue anything (AC-020/AC-021). */
export type DispatchAlarmKind = "queue-rows-unparsable" | "queue-unreadable" | "dispatch-quota" | "out-of-scope" | "orphaned-keys" | "run-ledger-conflict" | "no-product" | "write-scope-risk" | "orphan-repair-skipped" | "write-face-refusal";
export interface DispatchAlarm {
    kind: DispatchAlarmKind;
    count: number;
    detail?: string;
}
/** Alarm kinds that are NOT refusals — the scan made a scope/ownership
 * observation. Their text must stay neutral (`[mw] dispatch 提示：…`); only
 * real refusal kinds may say `[mw] dispatch 已拒绝：…` (AC-011/T-19). */
export declare const NOTICE_DISPATCH_ALARM_KINDS: ReadonlySet<DispatchAlarmKind>;
/** Is this alarm a notice (neutral wording) rather than a refusal? */
export declare function isNoticeDispatchAlarm(kind: DispatchAlarmKind): boolean;
/** One-line human text for a refused dispatch scan (AC-020/AC-021). Notice
 * kinds carry neutral wording; the verdict prefix is added by
 * {@link formatDispatchAlarm} (AC-011/T-19). */
export declare function describeDispatchAlarm(alarm: DispatchAlarm): string;
/** The full PM alert line for one alarm (AC-011/T-19): only real refusal kinds
 * carry the `已拒绝` verdict — a notice (`out-of-scope` / `orphaned-keys`) says
 * `提示` and never reads as a refusal. */
export declare function formatDispatchAlarm(alarm: DispatchAlarm): string;
/** Append one machine-readable alarm row to the autopilot ledger
 * (`.agenticdoc/_autopilot/auto-decisions.jsonl`, AC-020/AC-021). The shape
 * mirrors the Python single writer (`conductor._append_auto_decision_row`):
 * one JSON object per line, 1-based `seq`. Decision consumers filter on
 * `phase == "decide"`, so `phase: "dispatch-alarm"` is invisible to them while
 * staying visible to humans, `mw doctor` and later consumers. Best-effort by
 * design: losing the alarm must never break dispatch. */
export declare function recordDispatchAlarm(agenticdocRoot: string, alarm: DispatchAlarm): void;
/** Count the write-guard residual-risk audit rows in one worker trace
 * (AC-007/T-03): `[WRITE_SCOPE]` lines carrying BOTH `blocked=false` and
 * `risk=deny-basename`. The filter is deliberately the two-field pair and never
 * `rule=allow-unknown` alone (design-write-guard-landing §5.5): the unknown tier
 * is the contract, the deny-list basename is the residual risk. Best-effort — a
 * missing/unreadable trace is zero, never an error. */
export declare function countWriteScopeResidualRisks(taskDir: string): number;
/** PM-side exit for the write-guard residual risk (AC-007/DD-08): the worker
 * was allowed through by contract, so the ledger row is the remaining defence.
 * Reuses the single dispatch-alarm channel and its unchanged row shape; returns
 * the number of residual-risk rows found (0 ⇒ nothing written). */
export declare function recordWriteScopeResidualRisks(agenticdocRoot: string, taskKey: string, taskDir: string): number;
/** The one-line ledger detail for a PM-side write-face refusal (AC-003/D-008).
 * `DispatchRefusal.reason` is byte-identical to the conductor's
 * `DispatchResult.reason`, so it already carries the stable refusal `code`, the
 * `overlap-with:<task_key>` pair and the conflict `sample` when the gate could
 * prove one. The refused task key prefixes it because the alarm row has no key
 * column of its own. */
export declare function writeFaceRefusalDetail(taskKey: string, refusal: DispatchRefusal): string;
/** Single-scan dispatch quota (AC-021). A scan that wants to queue more rows
 * than this is looking at something it does not understand (IN-3 queued 252 in
 * one scan and the launcher spawned 66 workers at once). */
export declare const DEFAULT_DISPATCH_MAX_PER_SCAN = 3;
/** `dispatch_max_per_scan` from the project's autopilot config (D-026/AC-021).
 *
 * An explicit `DispatchScanOptions.maxPerScan` wins (tests and refreshers);
 * otherwise the project config decides. Read-only and fail-soft: a missing,
 * unreadable or out-of-range config falls back to
 * {@link DEFAULT_DISPATCH_MAX_PER_SCAN} — a broken file must never be able to
 * disable the quota (the IN-3 direction of the failure is *more* dispatching,
 * never less). */
export declare function readDispatchMaxPerScan(agenticdocRoot: string): number;
export interface DispatchScanOptions {
    /** Keys already warned about in this session — a key is reported at most once. */
    warnedKeys?: Set<string>;
    /** Fires once per undocumented key whose worker tasks were skipped.
     * MUST return whether the event was actually broadcast: false when it was
     * intentionally suppressed (e.g. scoped to another window's key) so the
     * once-per-session dedup does not burn the key's only slot. */
    onDocGate?: (key: string, gaps: string[]) => boolean;
    /** Scan scope (AC-019). `pm` = this window's watched key plus `_scratch`;
     * `cli` = the whole project. Defaults to `cli` so every pre-existing caller
     * (the `mw` command surface, tests, refreshers) keeps its global behaviour;
     * the PM-side automatic scan passes `pm` explicitly. */
    scope?: "pm" | "cli";
    /** The window's watched key; the only non-scratch key in `scope: "pm"`. */
    watchedKey?: string;
    /** Single-scan quota override (AC-021); defaults to
     * {@link DEFAULT_DISPATCH_MAX_PER_SCAN}. */
    maxPerScan?: number;
    /** Run-identity gate on the task's own product (AC-022, T-20). Default: no
     * information, i.e. pre-T-20 behaviour — the queue row alone decides.
     * `readTaskContent` is lazy so a candidate with its own run record is decided
     * without reading task.md. */
    runVerdict?: (task: {
        taskKey: string;
        taskDir: string;
        readTaskContent: () => string;
    }) => {
        ok: true;
    } | {
        ok: false;
        reason: RunIdentityRefusal;
        detail?: string;
    };
    /** Alarm sink (AC-020/AC-021). Production wires it to the ledger row (and
     * from there to the PM alert); the scan itself never invents a write path. */
    onAlarm?: (alarm: DispatchAlarm) => void;
    /** Human-visible PM alert for a per-task write-face refusal (AC-003/D-008).
     * Deliberately separate from {@link DispatchScanOptions.onAlarm}: the refusal
     * row is already persisted by the scan through `recordDispatchAlarm` (one per
     * refused task, never deduped), so this callback only carries the short
     * `formatDispatchAlarm` text to the PM. */
    onRefusal?: (text: string) => void;
    /** ORPHANED keys already alerted in this session (AC-011/T-19) — the
     * `orphaned-keys` alarm is once per key per session, so a key that stays
     * orphaned does not re-wake the PM on every settled turn. */
    orphanedWarned?: Set<string>;
    /** Keys already reported by the (T-22) "has work, no owner record" notice —
     * once per key per session, mirroring `orphanedWarned`. The notice reuses the
     * `out-of-scope` kind; the scan still writes nothing for these keys (no
     * `_index.parallel` row, no queue row, no task-dir mutation). */
    unregisteredWarned?: Set<string>;
}
/** Marker/skeleton of the service-layer envelope fallback, byte-mirrored from
 * `packages/multi-workers/launcher.py` (T-14, `envelope_fallback_inject`): the
 * same marker keeps the injection idempotent, and the same `[ENVELOPE_FALLBACK]`
 * audit token makes the fallback greppable on both sides. */
export declare const ENVELOPE_FALLBACK_MARKER = "<!-- mw-envelope-fallback -->";
export declare const ENVELOPE_FALLBACK_AUDIT = "[ENVELOPE_FALLBACK]";
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
export declare function synthesizeEnvelopeFallback(text: string): string | null;
/** Outcome of one key's claim-free repair dispatch. */
export interface OrphanRepairResult {
    key: string;
    /** Task keys actually queued (claim-free: only `_workers.parallel` moved). */
    queued: string[];
    /** Tasks the run-identity gate refused (terminal / active product). */
    refused: Array<{
        taskKey: string;
        reason: RunIdentityRefusal;
        detail?: string;
    }>;
    /** Old-form cards rewritten with the service-layer skeleton. */
    synthesized: string[];
    /** Old-form cards that could not be synthesized without inventing facts. */
    unsynthesizable: string[];
}
export interface OrphanRepairOptions {
    /** Single-call quota; defaults to the project's `dispatch_max_per_scan`. */
    maxPerScan?: number;
    /** Run-identity gate (AC-022); defaults to {@link evaluateRunIdentity} with
     * zero-backfill semantics (a candidate without a run record passes). */
    runVerdict?: DispatchScanOptions["runVerdict"];
    /** Human-visible PM alert for a per-task write-face refusal; see
     * {@link DispatchScanOptions.onRefusal}. */
    onRefusal?: DispatchScanOptions["onRefusal"];
}
/** Claim-free repair dispatch for one ORPHANED key (AC-011/T-19).
 *
 * Scans `{key}/workers/<task-key>/task.md`, skips already-queued and conductor-owned
 * tasks, applies the run-identity gate, synthesizes the service-layer envelope
 * for old-form cards (with an `[ENVELOPE_FALLBACK]` audit), and queues the
 * candidate through {@link dispatchTask}. It never reads-modify-writes
 * `_index.parallel`, so the conductor's eligibility predicate is untouched: the
 * repair does not "take over" the key, it only unblocks its undispatched work. */
export declare function repairDispatchOrphanedKey(workerStore: WorkerStore, agenticdocRoot: string, key: string, opts?: OrphanRepairOptions): Promise<OrphanRepairResult>;
export declare function dispatchNewTasks(workerStore: WorkerStore, agenticdocRoot: string, opts?: DispatchScanOptions): Promise<void>;
/** Session entry type recording a delivered gate reminder. Read back on
 * restart/resume so the same ledger row is never pushed twice (design D-010).
 * Same mechanism as WATCH_ENTRY_TYPE / AUTOPILOT_SEEN_ENTRY_TYPE. */
export declare const GATE_REMINDER_ENTRY_TYPE = "agent-team-loop:gate-reminder-seen";
/** Session entry type recording a DROPPED gate reminder (mw-autopilot-gate-
 * alarm-liveness AC-010): "no watch", "other key" and "read error" drops must
 * leave a visible record, never vanish silently. Deliberately a SEPARATE type
 * and WITHOUT `seq`: the delivery resume path reads `e.data?.seq` from
 * {@link GATE_REMINDER_ENTRY_TYPE} entries to advance `reminderWatermark`, so a
 * drop record carrying a `seq` would suppress the real delivery that follows
 * it (DRQ-2 C5 counter-example). */
export declare const GATE_REMINDER_DROPPED_ENTRY_TYPE = "agent-team-loop:gate-reminder-dropped";
/** Record one dropped reminder into the session (visible via the transcript /
 * session file). Deduplicated per `${gateId}:${n}:${reason}` for this process:
 * the poll loop runs every 4 s, so an undeduped drop would append an entry per
 * tick forever. `reason` is one of the three literal drop causes. */
export declare function recordDroppedGateReminder(pi: ExtensionAPI, seen: Set<string>, reminder: {
    gateId: string;
    reminderN: number;
    gateKey: string;
}, reason: "no-watch" | "other-key" | "read-error", error?: string): void;
export declare function startWorkerPollLoop(pi: ExtensionAPI, workerStore: WorkerStore, ackStore: AckStore, indexStore: IndexStore, agenticdocRoot: string, watch: PmWatchState, ui: PmUiHolder, pollIntervalMs?: number): NodeJS.Timeout;
/** Marker opening the injected parallel-protocol block, and the idempotency
 * guard: a handler that already sees it in the chained system prompt must not
 * append it a second time (two loaded bundle copies would otherwise duplicate
 * the text on every run). */
export declare const PARALLEL_PROTOCOL_MARKER = "[mw] \u5E76\u884C\u4F18\u5148\u534F\u8BAE";
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
export declare const PARALLEL_PROTOCOL: string;
export declare function pmActivate(pi: ExtensionAPI): void;
//# sourceMappingURL=pm-orchestrator.d.ts.map