import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
import { AckStore } from "../shared/ack-store.ts";
import { type CheckpointInfo } from "../shared/heartbeat.ts";
import { IndexStore } from "../shared/index-store.ts";
import { type RunIdentityRefusal, readRunState } from "../shared/run-store.ts";
import { type WorkerEntry, type WorkerStatus, WorkerStore } from "../shared/worker-store.ts";
import { type DispatchRefusal } from "./task-dispatcher.ts";
import { type DecideRunner } from "./triage-client.ts";
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
export type DispatchAlarmKind = "queue-rows-unparsable" | "queue-unreadable" | "dispatch-quota" | "out-of-scope" | "orphaned-keys" | "run-ledger-conflict" | "no-product" | "write-scope-risk" | "orphan-repair-skipped" | "write-face-refusal" | "model-error" | "triage-suggestion" | "triage-unavailable";
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
/** Exit-Reason prefix every model-exhausted worker writes (design §4; the
 * worker-side T-01 half of this key). */
export declare const MODEL_UNAVAILABLE_PREFIX = "model unavailable:";
/** Consecutive model-error terminals before the PM records one `model-error`
 * alarm (AC-006; K=2 per design §3.4/D7). */
export declare const MODEL_ERROR_STREAK_K = 2;
/** `run.json.model_exhausted === true` (design §4: the worker sets it on the
 * model-exhausted terminal, exit 3). Read raw rather than through the shared
 * `RunState` type because that field is added by the worker protocol (T-01) and
 * `shared/run-store.ts` is not this file's write face; a missing, unreadable or
 * malformed record is simply `false` (never throws — the poll loop calls this
 * on every terminal row). */
export declare function runModelExhausted(taskDir: string): boolean;
/** Does this terminal run carry model-unavailable evidence (AC-006/design
 * §3.4)? Two independent sources, OR'd: the worker's own
 * `run.json.model_exhausted` flag and the `## Exit Reason` body starting with
 * `model unavailable:`. Reading failures degrade to `false`, never throw. */
export declare function isModelErrorTerminal(taskDir: string): boolean;
/** Bump (model-error) or clear (every other terminal) one key's consecutive
 * model-error streak. The pure half of AC-006, exported so tests can drive the
 * sequence without standing up the poll loop. */
export declare function bumpModelErrorStreak(streaks: Map<string, number>, key: string, modelError: boolean): number;
/** PM-side model-error perception for one terminal worker row (AC-006, design
 * §3.4/D7). Called once per terminal transition on the poll loop's ownership
 * branch: bumps the owning key's streak, clears it on any non-model-error
 * terminal, and records ONE `model-error` alarm row through the single
 * dispatch-alarm channel once the streak reaches {@link MODEL_ERROR_STREAK_K}.
 * `detail` is the task key of the terminal that triggered the alarm. PERCEPTION
 * ONLY: the return value is never used to block or alter a re-dispatch. */
export declare function recordModelErrorTerminal(agenticdocRoot: string, streakKey: string, taskKey: string, taskDir: string, streaks: Map<string, number>): number;
/** `settle.outcome` vocabulary of the archive (`decide_archive._OUTCOMES`). */
export type DecisionSettleOutcome = "pending" | "ok" | "rework" | "rollback" | "inconclusive";
/** One `kind=settle` row to append — the exact argument set of
 * `decide_archive.append_settle` (dp is derived from the decision id).
 *
 * `evidenceRef` carries the run id `<task_key>@<iso>` (`run.json.run_id`): it is
 * the per-run half of the `(decision_id, outcome, run_id)` idempotency key and
 * the only place the frozen row contract can carry it (there is no `run_id`
 * field). */
export interface DecisionSettleRow {
    decisionId: string;
    dp: string;
    key: string;
    taskKey: string | null;
    outcome: DecisionSettleOutcome;
    settledBy: "pm-auto" | "human";
    evidenceRef: string | null;
    note: string | null;
}
/** Why a terminal row produced no settle row. `no-decision-header` is the
 * explicit non-association bucket demanded by spec §6.2 — PM-local decisions,
 * long-latency (dp10), composite attribution, worker-internal `tool_call`s and
 * cross-key spillover all land there and are NEVER guessed at. */
export type DecisionSettleSkipReason = "no-decision-header" | "needs-clarification" | "not-terminal" | "inconsistent-run" | "duplicate-settle" | "rollback-without-ok" | "unreadable-task-md" | "append-failed";
export interface DecisionSettleSkip {
    decisionId: string;
    reason: DecisionSettleSkipReason;
}
/** Mapping verdict for one terminal transition (6-state table of card T-08). */
export type DecisionSettleMapping = {
    ok: true;
    outcome: DecisionSettleOutcome;
    note?: string;
} | {
    ok: false;
    reason: DecisionSettleSkipReason;
};
/** The 6 terminal-state mapping (design D-013):
 *
 * | terminal | outcome |
 * | --- | --- |
 * | `done` (exit 0) | `ok` |
 * | `failed` | `rework` |
 * | `failed` + exit 3 / `model_exhausted` | `inconclusive` |
 * | `needs-clarification` | NO row (the human is the next settle subject) |
 * | `lost` | `pending` + `note=lost` |
 * | superseded (replacement landed) | `rollback` |
 *
 * `done` is `ok` without re-reading the contract sections: the worker folds the
 * contract verdict into the exit code (`evidence.delivered && gaps.ok ? 0 : 2`),
 * so a second PM-side oracle could only disagree with the run record. */
export declare function mapTerminalToSettle(input: {
    status: WorkerStatus;
    /** `run.json.exit`; undefined while unknown (`lost`, pre-terminal record). */
    runExit?: number;
    /** `isModelErrorTerminal(taskDir)`: exit 3 / `model unavailable:` evidence. */
    modelError: boolean;
}): DecisionSettleMapping;
/** `<dp>:<trigger_id>` split on the FIRST `:` (design D-023: trigger ids may
 * contain `:`, dp ids are kebab-case registry ids). Rejects empty halves and
 * any whitespace so a free-text value can never become a decision id. */
export declare function splitDecisionId(decisionId: string): {
    dp: string;
    triggerId: string;
} | undefined;
/** One settle row already in the archive (the fields the fold needs). */
export interface DecisionSettleRecord {
    decisionId: string;
    outcome: string;
    runId: string | null;
}
/** Read the settle rows of the decision archive, tolerating foreign/broken
 * lines (a half-written tail row is not this reader's error). Returns `[]` when
 * the archive does not exist yet. */
export declare function readDecisionSettles(archivePath: string): DecisionSettleRecord[];
/** Decide whether one settle row may be appended (pure): idempotency on
 * `(decision_id, outcome, run_id)` (a PM restart replay writes nothing) and the
 * `rollback` ordering rule (a rollback only exists for a decision that already
 * settled `ok` — otherwise it would fabricate a reversal that never happened).
 * Multiple settles per decision ARE legal: the fold takes the LAST one, which is
 * the only way `ok → rollback` can ever be recorded (design D-013). */
export declare function planDecisionSettle(input: {
    decisionId: string;
    ownerKey: string;
    taskKey: string | null;
    runId: string | null;
    outcome: DecisionSettleOutcome;
    note?: string;
    prior: readonly DecisionSettleRecord[];
}): {
    ok: true;
    row: DecisionSettleRow;
} | {
    ok: false;
    reason: DecisionSettleSkipReason;
};
/** Append implementation for one settle row (injected in tests). */
export type DecisionSettleAppender = (row: DecisionSettleRow) => {
    ok: true;
} | {
    ok: false;
    error: string;
};
/** Test seams for the settle path (production passes none). */
export interface DecisionSettleHooks {
    /** Archive path; defaults to `<agenticdocRoot>/_autopilot/decisions.jsonl`. */
    archivePath?: string;
    /** Append implementation; defaults to {@link archiveSettleAppender}. */
    append?: DecisionSettleAppender;
    /** Run-state reader; defaults to `readRunState`. */
    readRun?: (taskDir: string) => ReturnType<typeof readRunState>;
    /** Model-terminal probe; defaults to `isModelErrorTerminal`. */
    modelError?: (taskDir: string) => boolean;
}
export interface DecisionSettleResult {
    written: DecisionSettleRow[];
    skipped: DecisionSettleSkip[];
}
/** Settle the decision one terminal worker row executes (spec §6.2 / D-013).
 *
 * Called once per terminal transition from the poll loop (the `notified` set is
 * the per-task-per-session bound, exactly like `recordWriteScopeResidualRisks` /
 * `recordModelErrorTerminal` next to it). The decision id is reverse-looked up
 * from the task's own `decision:` head line; a task without one stays
 * un-associated (never guessed). A `supersedes:` task that settled `ok` also
 * records the `rollback` of the decision it replaced. Fail-soft: an unwritable
 * archive is reported in the result, never thrown into the poll loop. */
export declare function recordDecisionSettle(agenticdocRoot: string, ownerKey: string, entry: Pick<WorkerEntry, "taskKey" | "status">, taskDir: string, hooks?: DecisionSettleHooks): DecisionSettleResult;
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
/** Decision-point id (registry authority: packages/multi-workers/decision_points.py). */
export declare const DP2_CHECKPOINT_ID = "dp2-checkpoint-split";
/** Registry question id whose value carries the dp2 answer. */
export declare const DP2_CHECKPOINT_QUESTION = "checkpoint_action";
/** Steer request file the PM writes into the worker's task dir. The worker
 * consumes it at its next checkpoint tick (design §5.3: file transport keeps
 * coordination file-driven and the PM the single writer). */
export declare const DP2_STEER_FILE = "steer-dp2.md";
/** Attribution marker of the narrowed-scope steer (the worker injects it as a
 * followUp; kept here so the request file and its consumer cannot drift). */
export declare const DP2_NARROW_MARKER = "[mw dp2-narrow]";
/** Machine header line of the request file (first line of `steer-dp2.md`).
 * Exported so the worker-side consumer strips exactly what this side wrote. */
export declare const DP2_STEER_REQUEST_HEADER = "[dp2-narrow-request]";
/** Appended to the PM alert when dp2 answered `narrow` but the worker can no
 * longer act on a steer (T-07b fallback, DS-4: never fail open). */
export declare const DP2_NARROW_FALLBACK_LINE = "[dp2-narrow-fallback] task not running; escalated instead";
/** `questions_version` for dp2 = `q-<sha256(canonical questions)[:8]>`, i.e. the
 * exact short code the Python registry derives (D-026). The suite re-derives it
 * from the registry source so a question-set edit cannot drift silently. */
export declare const DP2_QUESTIONS_VERSION: string;
/** One `[CHECKPOINT]` line reduced to the trend counters. The design's dp2
 * input asks for "最近 ≤3 条 (elapsed_s, reads, writes)" — enough to tell "still
 * climbing" from "stalled" without shipping any L2 material. */
export interface Dp2CheckpointPoint {
    elapsedMin: number;
    reads: number;
    writes: number;
}
/** Checkpoint series of one task dir: `total` is the number of `[CHECKPOINT]`
 * lines (the `#ckpt<N>` sequence number), `points` the last `limit` of them in
 * file order. Empty/zero when trace.log is unreadable. */
export declare function readCheckpointTrend(taskDir: string, limit?: number): {
    total: number;
    points: Dp2CheckpointPoint[];
};
/** Effective dp2 authorization PRE-READ from `.mw/decide-points.json`.
 *
 * NON-AUTHORITATIVE (design D-036「唯配置论」): the table has exactly one
 * authority, `decision_points.decide_for`. This read exists ONLY so the PM does
 * not pay for a `mw decide run` child that Python would reject — zero-spawn
 * short-circuit, nothing else. `mode`, `acted` and `decision_id` come from the
 * child payload, never from here, and when this pre-read and Python disagree
 * PYTHON WINS. Read-only (AC-010: machines never write the table).
 *
 * `source`: `default` = no table / no row (registry default for a P2 point),
 * `config` = a usable row, `invalid` = the row is present but its L2/L3/L5
 * parse degrades it (Python `force_off`). */
export interface Dp2Authorization {
    enabled: boolean;
    source: "default" | "config" | "invalid";
}
export declare function readDp2Authorization(projectDir: string): Dp2Authorization;
/** One `context.artifact_status` entry (W6 / D-052..D-054). */
export interface Dp2ArtifactStatus {
    path: string;
    exists: boolean;
    bytes: number;
}
/** Machine fields of the checkpoint, 8 + 4 (design Q5): elapsed/reads/writes/
 * phases/uniq_targets/repeat_top/risk from the line plus the writeless landing
 * suffix (land/last_land/artifact/done). Reads ride in the trend only — the
 * frozen state table has no `progress.reads`. */
export interface Dp2CheckpointStateInput {
    ownerKey: string;
    taskKey: string;
    phase: string;
    taskType: string;
    budgetMin: number;
    checkpoint: CheckpointInfo;
    trend: Dp2CheckpointPoint[];
    /** `context.artifact_status` rows (already fs-stated, ≤24 enforced here). */
    artifacts?: readonly Dp2ArtifactStatus[];
}
/** Build the dp2 structured state (spec §5.4 / D-019: L0/L1 only, ≤2000B).
 * Required fields come from `decision_points.REQUIRED_STATE_FIELDS["dp2-…"]`:
 * universal 9 + `progress.elapsed_minutes/budget_minutes/phases_done/
 * phases_total/artifact_present`; the remaining counters and the trend are
 * optional L1. */
export declare function buildDp2CheckpointState(input: Dp2CheckpointStateInput): Record<string, unknown>;
/** task.md header view dp2 needs: `phase:`, `type:` and `timeout:`. Undefined
 * when task.md is unreadable (the caller then keeps its original alert). */
export declare function readDp2TaskHeader(taskDir: string, env?: NodeJS.ProcessEnv): {
    phase: string;
    taskType: string;
    budgetMin: number;
} | undefined;
/** Normalised dp2 outcome. `action` is the closed vocabulary the caller branches
 * on: only `narrow` can ever be `acted` (D-011); `split`, `direct` and
 * `escalate` all fall through to the human alert. */
export interface Dp2CheckpointDecision {
    decisionId: string;
    triggerId: string;
    /** Raw `checkpoint_action` value when the service produced one. */
    answer?: string;
    action: "narrow" | "split" | "direct" | "escalate" | "none";
    available: boolean;
    acted: boolean;
    /** Effective mode as reported by the child (`payload.mode`, D-036: mode is an
     * authorization OUTPUT). Absent when Python never answered; never read from
     * the local `.mw/decide-points.json` mirror. */
    mode?: "auto" | "suggest";
    reason?: string;
    confidence?: number | null;
    confidenceSource?: string;
    budgetMin: number;
    elapsedMin: number;
}
export interface Dp2CheckpointInput {
    /** Project root that owns `.mw/` (the control workspace in dual-root runs). */
    projectDir: string;
    ownerKey: string;
    taskKey: string;
    taskDir: string;
    checkpoint: CheckpointInfo;
    /** Test seam: replaces the `mw decide run` child (production: runDecideMw). */
    run?: DecideRunner;
    /** Budget env override (tests); defaults to `process.env`. */
    env?: NodeJS.ProcessEnv;
}
/** Ask dp2 for one checkpoint. NEVER throws and NEVER acts — it only decides
 * whether a `narrow` answer may replace the PM alert. `undefined` means the
 * feature is off for this project (design D-007 complete bypass: no spawn, no
 * write). */
export declare function decideDp2Checkpoint(input: Dp2CheckpointInput): Dp2CheckpointDecision | undefined;
/** Write `<taskDir>/steer-dp2.md` (design §5.3). The PM process is the single
 * writer; the worker consumes the file at its next checkpoint tick and renames
 * it away. Returns false when the request could not be written — the caller
 * must then fall back to the human alert: a narrow that never reaches the
 * worker is not an acted decision. */
export declare function writeDp2SteerRequest(input: {
    taskDir: string;
    decision: Dp2CheckpointDecision;
    risk: string;
}): boolean;
/** One `[DECISION] dp2 acted=1 decision_id=… trigger=…` correlation line in the
 * task's own trace (T-04d, design D-041 row 5).
 *
 * Written ONLY after the narrow actually executed — i.e. after
 * {@link writeDp2SteerRequest} returned true and the human alert was skipped. A
 * fallback to the alert (task not running / unwritable steer), `suggest` mode
 * and a disabled dp2 never write it: an un-executed decision may not claim
 * `acted=1`. Best-effort — a trace failure must never undo a written steer.
 */
export declare function appendDp2ActedTrace(taskDir: string, decision: Dp2CheckpointDecision): void;
/** `running` / `settled` / `unknown` — the narrow branch may only replace the
 * human alert when the worker can still act on the steer (T-07b, DS-4). */
export type Dp2TaskLiveness = "running" | "settled" | "unknown";
/** Is the worker this alert is about still able to consume a `steer-dp2.md`?
 *
 * The queue row is this loop's own view and is not evidence enough — it can lag
 * a run that already finished (the row is written by the launcher, the terminal
 * state by the worker itself, AC-022). So the worker's own product is consulted
 * first: `run.json` status, plus pid liveness for an `active` record (a worker
 * killed without a terminal write would otherwise look alive forever). Only
 * when the product gives no information does the ledger row decide.
 *
 * `unknown` (unreadable/unparsable record, no ledger evidence) is passed to the
 * caller as "not verified live" — the caller falls back to the human alert,
 * i.e. the fail-closed direction DS-4 requires. */
export declare function probeDp2TaskLiveness(taskDir: string, ledgerStatus?: string): Dp2TaskLiveness;
/** Test seams + the explicit project root for the dp2 checkpoint hook.
 * Production passes only `projectDir`; `run` lets the suite replace the
 * `mw decide run` child (the triage-client DecideRunner seam). */
export interface Dp2CheckpointHooks {
    projectDir?: string;
    run?: DecideRunner;
}
export declare function startWorkerPollLoop(pi: ExtensionAPI, workerStore: WorkerStore, ackStore: AckStore, indexStore: IndexStore, agenticdocRoot: string, watch: PmWatchState, ui: PmUiHolder, pollIntervalMs?: number, dp2Hooks?: Dp2CheckpointHooks): NodeJS.Timeout;
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