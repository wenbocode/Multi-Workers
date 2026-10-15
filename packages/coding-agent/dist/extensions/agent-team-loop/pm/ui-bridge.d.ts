import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../../core/extensions/types.ts";
import type { ModelRegistry } from "../../../core/model-registry.ts";
import type { AckStore } from "../shared/ack-store.ts";
import { type IndexStore } from "../shared/index-store.ts";
import type { DoctorJson, MwCliResult } from "../shared/mw-runner.ts";
import { type PmStateClaimSyncResult } from "../shared/pm-state-claim.ts";
import type { WorkerEntry, WorkerStatus, WorkerStore } from "../shared/worker-store.ts";
import { type WriteTargetShape } from "../shared/write-surface.ts";
export { classifyWriteTargetShape, type WriteTargetShape } from "../shared/write-surface.ts";
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
export declare function resolveOwnerKeyWithSync(pi: ExtensionAPI, indexStore: IndexStore, watch: PmWatchState, explicit: string | undefined, agenticdocRoot: string): string;
export declare function displaySummary(pi: ExtensionAPI, summary: string): void;
/** Deliver a message into the conversation AND trigger a PM turn — the
 * shared "wake the PM" channel (finish calls and mid-run escalations).
 * `pi.sendMessage` without `triggerTurn` only injects the message into LLM
 * context: it displays in the transcript, but an idle PM never wakes up.
 * With `triggerTurn: true` an idle PM starts an LLM turn immediately; a
 * streaming PM gets the text steered into the current turn. Informational
 * notices (init, mw start, gate skips) stay passive via displaySummary —
 * they must not spend agent turns. */
export declare function deliverPmAlert(pi: ExtensionAPI, text: string): void;
/** Deliver a terminal worker result (the "finish call" of dispatch →
 * monitor → finish call → pm run). See deliverPmAlert for the channel. */
export declare function deliverWorkerResult(pi: ExtensionAPI, summary: string): void;
export interface PmWatchState {
    /** AgenticTask key this window explicitly executes; undefined = not watching. */
    key: string | undefined;
    /** Task keys THIS window dispatched in this process (mw-task-scope-isolation).
     * Optional so callers that only track the watch key keep building the state
     * as a plain literal. Needed because the owner key is not always the watched
     * key: an explicit `key:` dispatch is honoured without warning
     * (resolveOwnerKeyWithSync) and the global-active fallback lands elsewhere
     * too, yet both are this window's work for list_tasks / ack. Process-local by
     * design — never persisted, never shared between windows. */
    dispatchedTaskKeys?: Set<string>;
}
export interface PmUiHolder {
    /** Latest ExtensionContext, captured on session_start so background timers
     * can render UI. Undefined before session start or in headless runs. */
    ctx: ExtensionContext | undefined;
}
/** Session entry type persisting this window's watched key across restarts. */
export declare const WATCH_ENTRY_TYPE = "agent-team-loop:watch";
/** This window's claim identity: host:pid. Written into _index.parallel so
 * another window can tell whether a key's claim is still held by a live
 * process (pid check) before taking it over. */
export declare function windowClaimId(): string;
export type ClaimState = "free" | "held-live" | "held-stale" | "held-conductor";
/** Who holds a key's `_index.parallel` claim — deliberately a HOLDER verdict,
 * not a takeover verdict (the two differ for exactly one holder):
 *  - "held-live": another live window (or a foreign host whose liveness we
 *    cannot verify) holds it. A takeover needs `--force`.
 *  - "held-conductor": THIS host's autopilot conductor holds it through its
 *    synthetic claim `autopilot@<host>:<pid>` (T-16). The conductor yields to
 *    a human takeover on its next tick, so `takeOverKey` succeeds WITHOUT
 *    `--force` (T-16b requirement 1).
 *  - "held-stale": the holder is gone; "free": nobody (or this window).
 *
 * The synthetic branch is decided by index-store's shared parser
 * (`parseSyntheticClaim` + `syntheticClaimLive`), never by a prefix test
 * repeated here: the TS takeover guard and the Python conductor can then only
 * drift through that one predicate (T-16b requirement 4). */
export declare function claimState(claimId: string, self: string): ClaimState;
/** Machine-readable refusal code for a cross-key write (AC-024). */
export declare const CROSS_KEY_READ_ONLY = "cross-key-read-only";
/** Writer surfaces the cross-key guard actually fences, in refusal-text order.
 * Single declaration source (AC-003/VC-011): the refusal body below is built
 * from this array, and the coverage test asserts every entry maps to a real
 * guard call site — the text can never again claim a surface the code does not
 * guard (the pre-AC-003 gap: it named `/worker` while only dispatch_worker and
 * advance_phase called the guard). */
export declare const CROSS_KEY_READ_ONLY_SURFACES: readonly ["dispatch_worker", "/worker", "advance_phase"];
/** Row-ack addendum of the refusal text: `ack_worker_result` filters rows by
 * ownership instead of calling the guard, so it is named in the text but is
 * deliberately NOT part of {@link CROSS_KEY_READ_ONLY_SURFACES} (which is the
 * call-site set VC-011 compares against). */
export declare const CROSS_KEY_READ_ONLY_ACK_NOTE = "acking its rows";
/** Cross-key write guard (AC-024): a key whose `_index.parallel` row is held
 * live by ANOTHER window is READ-ONLY for this window. Reading it stays global
 * and unrestricted (`list_tasks` scope "all"/"key", `mw_status`, `mw doctor`,
 * the watch panel); the WRITER surfaces refuse with the stable
 * {@link CROSS_KEY_READ_ONLY} code instead of silently touching another
 * window's namespace. Writable: this window's own claim, an unclaimed key
 * (new-key bootstrap: write spec.md -> advance -> dispatch), and `_scratch`.
 * Returns null when the write is allowed. */
export declare function foreignLiveClaimRefusal(indexStore: IndexStore, key: string): string | null;
export interface TakeoverResult {
    ok: boolean;
    /** Present when ok=false: the live claim that blocked the takeover. */
    blockedBy?: string;
    claimId: string;
    /** True when the key row was auto-created (key was unknown to _index.parallel). */
    created: boolean;
    /** Phase-chain audit warnings for the claimed key (empty = clean):
     * two-source divergence + gate-evidence gaps for phases the pm-state
     * claims to have passed. Non-blocking — claiming a broken key to fix it
     * is legitimate; the warnings make the breakage visible immediately. */
    audit: string[];
    /** Present when ok=false: the key NAME was refused by the shared
     * shape/reserved gate (AC-006, stable `keyNameRefusal` code) rather than a
     * live foreign claim. */
    refusal?: string;
    /** Result of mirroring the claim into {key}/pm-state.md's '- Claim-Id:'
     * line (mw-worker-visibility-gate D-107/D-108); undefined when the claim
     * itself failed. A failed mirror never flips `ok` — the index row is
     * authoritative, pm-state.md is only its mirror. */
    claimSync?: PmStateClaimSyncResult;
}
/** Claim a key for this window — shared by /pm-key switch, /pm-key new and
 * the spec-write auto-takeover. Routes through IndexStore.claim so the
 * liveness check, demote, and write are one atomic step under the index
 * lock: racing windows cannot both believe they claimed. Also runs the
 * phase-chain audit on success (audit_phase.py's TS-side mirror). */
export declare function takeOverKey(indexStore: IndexStore, key: string, force: boolean, agenticdocRoot: string): Promise<TakeoverResult>;
/** One-line warning for a claim whose pm-state.md mirror sync failed
 * (D-108): the claim itself succeeded — the index row is authoritative — so
 * this only makes the divergence visible to the user/agent. "" when the
 * sync succeeded or never ran (nothing to warn about). */
export declare function claimSyncWarningText(key: string, sync?: PmStateClaimSyncResult): string;
/** Owner key of a queue row: the first taskPath segment below the agenticdoc
 * root ({key}/workers/<task>/task.md → key). Legacy root-level rows resolve to
 * their own task key and simply never match a watched key. */
export declare function ownerKeyOf(entry: WorkerEntry, agenticdocRoot: string): string;
/** Does THIS window own the queue row (mw-task-scope-isolation)? True when the
 * row sits under the watched key, or when this process dispatched the task
 * (explicit cross-key dispatch, or the global-active fallback — see
 * resolveOwnerKeyWithSync). Fail-closed: with no watch key and no dispatch
 * record the row belongs to another window. Shared by list_tasks and both ack
 * entry points, so what the tools act on matches what the bottom watch widget
 * shows (it scopes by ownerKeyOf alone). */
export declare function ownedByThisWindow(entry: WorkerEntry, watch: PmWatchState, agenticdocRoot: string): boolean;
/** Body of a `## <section>` block in output.md (first match), trimmed;
 * undefined when the file or section is missing. Generic reader behind
 * readOutputSummary and the terminal-detail fallback chains (D-004): `##
 * TL;DR`, `## Exit Reason`, `## Questions`. The section literal is regex-escaped
 * so a future caller-side string with metacharacters can never inject. */
export declare function readOutputSection(taskDir: string, section: string): string | undefined;
/** `## Summary` body — the legacy detail source, now the done-row fallback
 * when no `## TL;DR` exists (old output.md files, AC-009). */
export declare function readOutputSummary(taskDir: string): string | undefined;
/** Cap for terminal readback bodies (AC-014). */
export declare const OUTPUT_READBACK_MAX = 20000;
/** Full output.md body for terminal readback (AC-014): worker results are
 * delivered into the watching window's conversation so the PM processes
 * them without manual file reads. Over-cap reports are truncated with a
 * pointer to the file. */
export declare function readOutputBody(taskDir: string): string | undefined;
/** Last `[launcher] spawn failed …` line from worker.log, if any. Spawn-failure
 * logs are tiny (the CLI never ran — the launcher writes exactly this line and
 * nothing else); a large log means the worker actually ran, so ignore it. */
export declare function readSpawnFailure(taskDir: string): string | undefined;
/** Last non-empty worker.log line, or undefined. The needs-clarification
 * fallback for tasks that never wrote an output.md (claude/codex workers,
 * old bundles) — their last logged line names what they were asking about. */
export declare function readWorkerLogTail(taskDir: string): string | undefined;
/** Widget detail line for a terminal worker row (D-004): the glyph/status
 * says what happened, this says why it stuck or what it concluded.
 *  - failed: spawn-failure reason (launcher prefix stripped, timestamp-free)
 *    ?? `## Exit Reason` first line
 *  - needs-clarification: `## Questions` first line ?? worker.log tail ??
 *    explicit no-output hint (claude/codex tasks write no output.md at all)
 *  - lost (D-022/T-20): the run's process is gone with no verified outcome —
 *    same evidence ladder as a failure (Exit Reason, then the log tail), so the
 *    PM reads the scene instead of a synthesized conclusion
 *  - done: `## TL;DR` first line ?? `## Summary` first line (old output.md
 *    files). AC-010: the LAST non-placeholder TL;DR/Summary block, not the
 *    first — append-only multi-run files lead with crash placeholders.
 * Returns "" when nothing informative exists (caller renders the key only).
 * Line-width truncation stays with the caller (WATCH_LINE_MAX). */
export declare function readTerminalDetail(taskDir: string, status: WorkerStatus): string;
/** Shared ack validation + write path behind /mw ack and the ack_worker_result
 * tool (D-002). `"all"` expands to every terminal row not yet acked;
 * individual keys must reference an existing terminal row — running/pending
 * rows are rejected and nothing is written for them (AC-004).
 *
 * `scope` (mw-task-scope-isolation) narrows the write path to this window: the
 * ack sidecar is a PROJECT-level file, so without it any window could ack (and
 * silently clear) another window's unhandled rows. When given, `"all"` only
 * covers rows this window owns and an explicit foreign key is rejected with the
 * owning key. Omitted = unscoped (callers that are not a PM window). */
export declare function ackTasks(workerStore: WorkerStore, ackStore: AckStore, targets: string[] | "all", scope?: {
    watch: PmWatchState;
    agenticdocRoot: string;
}): Promise<{
    acked: string[];
    rejected: Array<{
        key: string;
        reason: string;
    }>;
}>;
/** Live bottom-widget lines for the watched key, in three sections (D-003):
 *  1. live — running then pending, all shown, never folded
 *  2. unhandled — failed/needs-clarification rows the PM has not acked
 *     (/mw ack), all shown, never folded; header carries the count
 *  3. history — done rows ∪ acked terminal rows, newest-first, capped at
 *     WATCH_HISTORY_MAX with a `+N more` fold line
 * Terminal-row details come from readTerminalDetail (D-004).
 * `extraTaskKeys` (mw-worker-visibility-gate D-105) optionally names tasks
 * THIS window dispatched that landed under a different key: they render as
 * ONE aggregate tail line (`  ~ N elsewhere: …`, D-106) instead of rows, so
 * cross-key work stays visible without drowning the panel. Omitted or empty
 * keeps the output identical to the pre-aggregate panel (AC-007). */
export declare function renderWatchLines(indexStore: IndexStore, workerStore: WorkerStore, ackStore: AckStore, agenticdocRoot: string, key: string, extraTaskKeys?: ReadonlySet<string>): string[];
/** Render (or clear) the bottom watch widget on a UI-capable context. */
export declare function setWatchWidget(ctx: ExtensionContext, lines: string[] | undefined): void;
/** Render (or clear) the widget via the session_start-captured context.
 * No-op before session start or in headless runs. */
export declare function applyWatchWidget(ui: PmUiHolder, lines: string[] | undefined): void;
/** Doc-gate notifier scoped to this window's watched key (AC-011): the scan
 * evaluates gates for every undocumented key (blocking stays global), but a
 * gate event is only BROADCAST here when it is this window's own key — other
 * keys' gates belong to their owning windows. A window watching nothing
 * stays silent. */
export declare function makeScopedDocGateNotifier(pi: ExtensionAPI, watch: PmWatchState): (key: string, gaps: string[]) => boolean;
export declare function registerPmKeyCommands(pi: ExtensionAPI, indexStore: IndexStore, watch: PmWatchState, refreshWatch: (ctx: ExtensionContext) => void, agenticdocRoot: string): void;
/** Insert a session-snapshot section at the top of {key}/pm-state.md's Notes
 * area. Machine-interface lines (- Phase: / - Claim-Id:) are owned by the
 * framework scripts and stay byte-identical: the snapshot is inserted under
 * "## Notes" only, never rewriting the rest of the file (pm-state-guard
 * principle, framework-side write with the same lock protocol as
 * StateManager). Returns the path written. */
export declare function writeSessionSnapshot(agenticdocRoot: string, key: string, lines: string[]): Promise<string>;
/** /pm-save — persist this window's working context into the watched key's
 * pm-state.md so a restarted pi window (e.g. after a framework rebuild) can
 * pick the work back up. The handler writes the mechanical snapshot (watch
 * key, index row, worker counts, free note) itself; the conversational
 * context (what we are doing, decisions, next steps) can only be summarized
 * by the agent, so the handler asks it to — the user invoked the command, so
 * this is a user-requested action, not a framework-injected nudge. */
export declare function registerPmSaveCommand(pi: ExtensionAPI, indexStore: IndexStore, workerStore: WorkerStore, watch: PmWatchState, agenticdocRoot: string): void;
/** /mw-watch — toggle this window's bottom progress widget for one key.
 * Display-only observation: no claim is taken. Use /pm-key switch to take
 * over a key while developing it.
 *
 * Usage: /mw-watch <key>   watch a key (widget appears below the editor)
 *        /mw-watch off     stop watching (widget cleared)
 *        /mw-watch         show current watch state
 */
export declare function registerWatchCommand(pi: ExtensionAPI, watch: PmWatchState, refreshWatch: (ctx: ExtensionContext) => void, indexStore: IndexStore): void;
export declare function registerMwTools(pi: ExtensionAPI, projectDir: string): void;
/** Resolve the task type for one dispatch: an explicit value must be one of
 * DISPATCHABLE_TYPES, an omitted one keeps the legacy cli-derived mapping
 * (pi -> coding, claude -> review, codex -> codex) so pre-existing dispatches
 * stay byte-identical. */
export declare function resolveDispatchType(cli: string, requested: string): {
    ok: true;
    type: string;
} | {
    ok: false;
    message: string;
};
/** Build the task.md frontmatter (type / phase / images / model / model-reason)
 * for one dispatch and the echo line that tells the PM which layer supplies the model
 * (design D-001~D-007). Shared by the dispatch_worker tool and /worker so the
 * two entries can never drift.
 *
 * Refusals (no task file must be written): an unknown model id for a pi route
 * (validateModelValue), and an override of a configured dispatch.yml role
 * default without a reason. */
export declare function planDispatchFrontmatter(input: {
    cwd: string;
    cli: string;
    provider: string;
    taskType: string;
    /** Owner key's current phase (T-14): non-empty appends `phase: <P>` right
     * after `type:`; ""/undefined keeps the pre-T-14 bytes unchanged. */
    phase?: string;
    /** Declared image capability (T-05): `"yes"`/`"no"` appends `images: <v>`
     * right after `phase:` and before `model:`; `undefined` (undeclared) keeps
     * the pre-T-05 bytes unchanged. */
    images?: "yes" | "no";
    /** Task body, scanned for an image-file reference when `images` is
     * undeclared (T-06 auto-detection). Optional (T-17): callers that only
     * exercise the phase/model path omit it, matching `phase?: string`. */
    description?: string;
    model: string;
    modelReason: string;
    registry: ModelRegistry | undefined;
}): {
    ok: true;
    frontmatter: string;
    echo: string;
} | {
    ok: false;
    message: string;
};
/** Paired markers of the dispatch-injected write-surface contract (contract
 * C2, producer T-02 → consumer T-03). The runtime consumer only greps for
 * these markers; the three lines between them are for the worker and PM. */
export declare const WRITE_SURFACE_MARKER = "<!-- mw-write-surface: v1 -->";
export declare const WRITE_SURFACE_MARKER_END = "<!-- /mw-write-surface: v1 -->";
/** Machine-readable refusal code for an unsatisfiable write requirement. */
export declare const WORKER_WRITE_SURFACE = "worker-write-surface";
/** Write verbs a task book can use to order a file write (AC-005a). Exported so
 * the rule is enumerable by the unit matrix and by the corpus replay.
 * `写到文件` before `写到` so the longest form wins. */
export declare const WRITE_INTENT_VERBS: readonly string[];
/** Allow-guards (AC-005a), stable names for the test matrix. A hit matching
 * any guard is a legitimate mention, never an unsatisfiable write order. */
export declare const WRITE_INTENT_GUARDS: readonly string[];
/** Upper bound (chars) between a write verb and its path. The matcher is
 * deliberately stricter: only whitespace and at most one quote may separate
 * the two, which is what keeps prose like "追加而非重写 achieved.md" out while
 * still satisfying the ≤32 bound. */
export declare const WRITE_INTENT_PATH_WINDOW = 32;
export interface WriteIntentHit {
    verb: string;
    path: string;
    clause: string;
}
/** Verdict of the target axis (AC-003/AC-004). `rule` exists only when
 * allowed=false: `deny` = the deny prefix table fired, `scope` = a path-shaped
 * target outside the write surface. */
export interface WriteTargetJudge {
    allowed: boolean;
    shape: WriteTargetShape;
    rule?: "deny" | "scope";
    detail?: string;
}
/** Write-surface context for judgeWriteTarget (AC-003/AC-004). `keyDir` and
 * `trueRoot` activate the deny prefix table (same table as worker-mode.ts);
 * omitted, only containment + shape evaluation run. */
export interface PmWriteSurfaceCtx {
    taskDir: string;
    projectRoot: string;
    keyDir?: string;
    trueRoot?: string;
}
/** Write-intent hits that survive the five allow-guards (AC-005a). Pure over
 * text so the corpus replay and the unit cases share one implementation.
 *
 * HTML comments are stripped structurally (AC-010 / C-29) before any verb or
 * token matching: the framework's own injected markers
 * (`<!-- mw-write-surface: v1 -->` / `<!-- /mw-write-surface: v1 -->`) contain
 * the English verb `write`, whose anchored token scan would otherwise read
 * `-surface:` as a colon-shaped target and refuse the producer's honest
 * artifact. Stripping the whole comment span (inline and multi-line) removes
 * every comment-borne mention — never a marker-name special case. */
export declare function collectWriteIntentHits(text: string): WriteIntentHit[];
/** Verdict of the target axis delegated to the shared write-surface predicate
 * (`shared/write-surface.ts::judgeWriteTarget`, design §3; AC-016). This
 * adapter only adds the two PM-only channels the predicate does not own: the
 * framework basenames (`task.md`/`trace.log`/`output.md`/`run.json`/
 * `worker.log`, which the framework itself writes) and the `WriteTargetJudge`
 * shape/rule vocabulary. Evaluation order matches the historical one:
 *   1. deny prefixes + own task dir + own-key `<key>/evidence/**` + worker_file
 *      basenames + path-shape refusal — all from the shared predicate
 *   2. framework basenames — PM prose channel only
 *   3. non-candidate prose => pass untouched
 * The `!hasDirComponent` precondition (not `shape === "bare"`) is load-bearing:
 * `output.md`/`report.md` are `ext`-shaped and must still use the channel. */
export declare function judgeWriteTarget(pathToken: string, ctx: PmWriteSurfaceCtx): WriteTargetJudge;
/** Boolean wrapper of {@link judgeWriteTarget} (AC-003/AC-004): may this role
 * legitimately write `pathToken`? */
export declare function isWhitelistedWriteTarget(pathToken: string, ctx: PmWriteSurfaceCtx): boolean;
export interface WriteIntentVerdict {
    ok: boolean;
    /** Guard-surviving hits, before the whitelist (AC-005a corpus metric). */
    hits: WriteIntentHit[];
    /** Hits whose target the role cannot reach (the refusal set). */
    violations: WriteIntentHit[];
}
/** Judgement entry point: only a writeless role without a shell is judged — a
 * write role passes untouched, a shell role (`research`) is handled by the
 * AC-005b runtime guard instead. `allowForeignWrite` is the escape hatch. */
export declare function judgeWriteIntent(input: {
    type: string;
    description: string;
    taskDir: string;
    projectRoot: string;
    allowForeignWrite?: boolean;
    /** Own key dir (`.agenticdoc/<key>`); activates the deny prefix table. */
    keyDir?: string;
    /** TRUE `.agenticdoc` root; activates the deny prefix table. */
    trueRoot?: string;
}): WriteIntentVerdict;
/** Refusal text for an unsatisfiable write order (AC-005a): names the code, the
 * role, the path, and the three ways forward. */
export declare function writeIntentRefusal(input: {
    taskKey: string;
    type: string;
    path: string;
}): string;
/** Default `write_scope:` line for a shell role (contract C1): the task's own
 * dir plus the key's evidence tree. Absent for non-shell roles. */
export declare function renderDefaultWriteScope(ownerKey: string, taskKey: string): string;
/** The injected 3-line contract section (contract C2), marker-paired. */
export declare function renderWriteSurfaceContract(type: string, writeScope: string | undefined): string;
/** Idempotent contract-section application (contract C2, VC-019): any existing
 * marker region is removed, then the canonical section is inserted right after
 * the leading frontmatter block. Applying it twice is a byte-level fixed point
 * and leaves exactly one marker pair. */
export declare function applyWriteSurfaceContract(taskMdText: string, type: string, writeScope: string | undefined): string;
/** Machine-readable refusal code for a missing/incomplete dispatch card. */
export declare const DISPATCH_CARD_CODE = "dispatch-card";
/** Paired markers around the card-derived body section (idempotent injection,
 * same "strip old region → reinsert" mechanism as the write-surface contract). */
export declare const CARD_SEED_MARKER = "<!-- mw-dispatch-card: v1 -->";
export declare const CARD_SEED_MARKER_END = "<!-- /mw-dispatch-card: v1 -->";
/** The mandatory seed disclaimer demanded by design §2.2: the injected card is
 * a seed, never an upper bound on what the worker may read. */
export declare const CARD_SEED_DISCLAIMER = "\u4EE5\u4E0A\u4E3A\u79CD\u5B50\uFF0C\u4E0D\u662F\u63A2\u7D22\u4E0A\u754C\uFF1B\u53EF\u81EA\u884C\u68C0\u7D22\u8865\u5145\u4E0A\u4E0B\u6587";
/** One card section the envelope judge does not classify: the §1.2 per-type
 * extras (`写入允许面` / `写入禁止面` / `验收命令` / `改动历史`). Kept so the seed
 * can inject them into the derived task.md (T-12/F-02). */
export interface CardExtraSection {
    title: string;
    body: string;
}
/** The three envelope bodies injected into the generated task.md, plus the
 * card's unclassified sections (the §1.2 type extras) so the derived task.md
 * passes the SAME extras judge the service layer (G-3) runs. */
export interface CardSections {
    context: string;
    requirements: string;
    deliverables: string;
    /** Card sections outside the three envelope families, in document order. */
    extras: CardExtraSection[];
    /** T-05/AC-003: the card's declared `type:`, set only by {@link readDispatchCard}
     * (a directly constructed `CardSections` carries no type, so callers keep the
     * pre-T-05 bytes). It drives the `## 交付段契约（本角色）` checklist in
     * {@link renderCardSeedSections}. */
    type?: string;
}
/**
 * Extract the three envelope bodies from a card (T-02, contract C3).
 *
 * Heading-based slicing mirrors T-01's judgement: the first heading of a family
 * with a non-empty body wins, body runs to the next heading of the same or
 * higher level. A section T-01 accepted only through the wide semantic fallback
 * (headingless card) has no slice to take, so the whole post-prologue card body
 * is used as its content — the seed is delivered rather than dropped. This
 * never re-judges the envelope; `readEnvelope` already owns the verdict.
 */
export declare function extractCardSections(cardText: string): CardSections;
/** Render the marker-paired card seed block (T-02, contract C3).
 *
 * T-05/AC-003 (S2 TS half): for a card-backed render whose role is a
 * card-declared WRITELESS report role, the role's `## 交付段契约（本角色）`
 * checklist is appended inside the seed block (each required section as a
 * copyable `## <name>`). The presence guard makes a card that already declares
 * the heading a byte-level fixed point, so re-rendering (or the Python
 * producer's identical `dispatch.py::_envelope_card_body` injection) cannot
 * double-render the section.
 *
 * Scope note (2026-10-14, T-05; widened 2026-10-15, T-13/D-015 option C): the
 * gate is now "the card declares a `type:`" — `recoveryContractSection` already
 * returns `""` for types outside `RECOVERY_CONTRACT_TYPES` (no contract role
 * stays byte-identical), so the checklist reaches every contract role the TS
 * dispatch path produces, `coding` included. The `dispatch-card-injection.test.ts`
 * coding fixture now carries the checklist in its pinned expected bytes. */
export declare function renderCardSeedSections(sections: CardSections): string;
/** Idempotent card-seed application: any existing marker region is removed,
 * then the canonical block is prepended to the body. Applying it twice is a
 * byte-level fixed point and leaves exactly one marker pair. */
export declare function applyCardSeedSections(bodyText: string, sections: CardSections): string;
/** T-18 (VC-003 producer identity): this generator's id for the task.md header.
 *
 * The service layer (`launcher.py` `producer_identity`, T-14/AC-009) reads
 * `envelope_producer: <producer-id>@<version>` to tell a *stale producer* (an
 * old framework copy whose task.md shape predates the current envelope/extras
 * contract) apart from a genuinely missing section. The id names this tool
 * path so it is distinct from the Python conductor's `autopilot-conductor`
 * (`dispatch.py` `PRODUCER_NAME`). */
export declare const DISPATCH_PRODUCER_ID = "agent-team-loop-pm";
/** Machine-readable key of the identity line (`dispatch.py` `PRODUCER_IDENTITY_KEY`). */
export declare const ENVELOPE_PRODUCER_KEY = "envelope_producer";
/** `<producer-id>@<version>` for the header line.
 *
 * The version is the pi release train's own, read at module load from
 * `packages/coding-agent/package.json` through `config.ts` `VERSION` — the same
 * existing version source `dispatch.py::producer_version()` prefers (and the
 * lockstep version `launcher.py` compares a dotted-numeric producer version
 * against); never a new constant. Shape is byte-compatible with the Python
 * renderer (`f"{PRODUCER_IDENTITY_KEY}: {producer_identity()}"`) and the service
 * parser (`^[ \t]*envelope_producer[ \t]*:[ \t]*(\S+)[ \t]*$`). */
export declare function envelopeProducerIdentity(): string;
/** Card section heading whose entries become the task.md `write_face:` head
 * (`dispatch.py` `WRITE_FACE_CARD_SECTION`, design D-001). */
export declare const WRITE_FACE_CARD_SECTION = "\u5199\u5165\u5141\u8BB8\u9762";
/** Raw entries of a card's `## 写入允许面` section — the TS mirror of
 * `dispatch.py::_card_write_face_entries` (W-03), reading the card sections
 * this file already extracted ({@link CardSections.extras}) instead of
 * re-parsing the card.
 *
 * `null` = the section is absent (undeclared; no `write_face:` line is
 * rendered). A present-but-entry-less section yields `[]` (the renderer then
 * writes the `-` undeclared marker, D-001/§3.3). Entries keep the author's
 * single-`/` syntax verbatim — the renderer must not transform what the
 * parser will normalize, or the two would stop being the same source. */
export declare function cardWriteFaceEntries(sections: CardSections): string[] | null;
/** The task.md `write_face:` head value for a non-empty entry list — the TS
 * mirror of `dispatch.py::render_write_face_line` (D-113).
 *
 * No entry contains `,` -> the historical single line `write_face: a, b`; any
 * entry contains `,` -> the design §3.1 block-list carrier
 * `write_face:\n  - a\n  - b` (one entry per item), because `,` is an
 * unconditional single-line separator that brackets/braces never shield.
 * `entries` is non-empty by contract — the caller writes `write_face: -` for a
 * declared-but-empty face. */
export declare function renderWriteFaceLine(entries: readonly string[]): string;
/**
 * Normalize a dispatch's card reference to the key-relative `tasks/<name>.md`
 * form the traceability audit (T-06 `card_audit.py`) reads. A card outside the
 * owner key's `tasks/` dir falls back to a repo-relative posix path; the last
 * resort is the bare basename so a header is always written.
 */
export declare function normalizeCardPathForHeader(cardPathInput: string, ownerKey: string, agenticdocRoot: string, projectDir: string): string;
/** Resolved dispatch-card gate result (T-02, contract C3). */
export interface DispatchCardGate {
    ok: boolean;
    /** Absolute path the reference resolved to (named in every refusal). */
    resolvedPath: string;
    /** Missing envelope items, `readEnvelope` keys and/or §1.2 extra names. */
    missing: string[];
    /** Normalized `tasks/<name>.md` header value (empty when ok=false). */
    headerPath: string;
    /** EOL-normalized sha256 (empty when ok=false). */
    sha256: string;
    /** Extracted seed bodies (empty strings when ok=false). */
    sections: CardSections;
}
/**
 * G-1 tool-layer gate (design §4): resolve the card path, judge the envelope
 * with T-01's `readEnvelope`, then the per-type §1.2 extras on the CARD TEXT
 * (the same `typeExtrasMissing` the service layer runs on the derived task.md,
 * T-12/F-02) and the seed minimum (`seedItemsMissing`, T-12/F-05), and only
 * then digest + extract the seed. Never judges content quality; a refusal is a
 * plain report the caller turns into text (zero side effects).
 */
export declare function readDispatchCard(input: {
    cardPath: string;
    ownerKey: string;
    agenticdocRoot: string;
    projectDir: string;
}): DispatchCardGate;
/** Refusal text for an incomplete card (AC-007 fail-closed): names the code,
 * the missing items and the exact card path; says nothing was written. */
export declare function dispatchCardRefusal(gate: DispatchCardGate): string;
/** Single write point for one dispatch's task.md (contract C4). Both dispatch
 * entries — the `dispatch_worker` tool and the `/worker` command — go through
 * here so the pipeline (frontmatter merge, contract-section injection, mkdir,
 * writeFileSync) has exactly one implementation. The T-01 extraction is
 * byte-for-byte equivalent to the inline writes it replaced: with no
 * `writeScope` and no injection hook the file content is
 * `${frontmatter}\n${body}\n` and only the mkdir/write order is shared. T-02
 * fills in the write-surface contract section (C2) and `injected` reports
 * whether this call wrote one. */
export declare function writeDispatchTaskMd(deps: {
    agenticdocRoot: string;
    ownerKey: string;
}, input: {
    taskKey: string;
    type: string;
    body: string;
    frontmatter: string;
    /** Rendered `write_scope:` line (T-02, contract C1); undefined keeps the
     * pre-C1 frontmatter bytes. */
    writeScope?: string;
    /** AC-005a (contract C2): inject the write-surface contract section.
     * Opt-in so the pre-C2 byte shape stays available (T-01/T-03 callers). */
    injectWriteSurface?: boolean;
    /** AC-005a escape hatch: record `allow_foreign_write: true` for audit. */
    allowForeignWrite?: boolean;
    /** T-02 (contract C3): the judged dispatch card. Adds the bare
     * `card_path:` / `card_sha256:` header lines (plus the T-18
     * `envelope_producer:` identity line) and prepends the card-derived
     * `## 上下文` / `## 要求` / `## 交付格式` seed block (idempotent). Omitted
     * keeps the pre-T-02 byte shape for direct callers. */
    card?: {
        headerPath: string;
        sha256: string;
        sections: CardSections;
    };
}): {
    ok: true;
    path: string;
    injected: boolean;
};
/**
 * Register agent-callable tools for worker dispatch and task listing.
 * These complement the slash commands in registerWorkerCommands.
 */
export declare function registerWorkerTools(pi: ExtensionAPI, workerStore: WorkerStore, ackStore: AckStore, indexStore: IndexStore, agenticdocRoot: string, watch: PmWatchState, projectDir?: string): void;
/** Register the agent-callable switch_key tool: same takeover as
 * /pm-key switch, callable mid-conversation. Tool description + prompt
 * guidelines teach the agent when to call it (explicit user request, or
 * starting real task work on a key — ask the user first in that case). */
export declare function registerSwitchKeyTool(pi: ExtensionAPI, indexStore: IndexStore, watch: PmWatchState, refreshWatch: (ctx: ExtensionContext) => void, agenticdocRoot: string): void;
/** Register the agent-callable advance_phase tool: the shell-free path
 * through the AgenticTask phase gates. The guard blocks hand-edits of
 * pm-state.md's '- Phase:' line and points at advance_phase.py; running that
 * via the bash tool was the only route, so a window whose shell resolution
 * or in-shell `python` differs (fresh machines: WSL-only bash, Store-stub
 * python, python3-only Linux) had NO way to advance a phase — it deadlocked
 * with "no shell, cannot execute advance_phase.py / update_index.py". This
 * tool spawns the script directly (list args, no shell); gate semantics stay
 * in the Python script, the single source of truth audit_phase.py replays. */
export declare function registerAdvancePhaseTool(pi: ExtensionAPI, projectDir: string, indexStore: IndexStore): void;
/**
 * Spawn a worker directly from the pi window.
 * Usage: /worker <claude|codex|pi> [--type <t>] [--model <id>] [--reason <text>] [--key <name>] <desc>
 */
export declare function registerWorkerCommands(pi: ExtensionAPI, workerStore: WorkerStore, indexStore: IndexStore, agenticdocRoot: string, watch: PmWatchState, projectDir?: string): void;
/**
 * Render the RAG row exactly like `mw.py:_format_rag_doctor_line` (D-308): an
 * `error` wins, an empty `enabled` list yields the not-enabled form, otherwise
 * `enabled=<a, b>; probe=<name=reachable|unreachable, ...>; fingerprint=<first
 * 12>; skill=<status>` plus `; required_missing=N` when N > 0. Probe names are
 * sorted the same way (`sorted(probe.items())`). Pure, so the cross-language
 * text can be asserted byte-for-byte against the Python line for one JSON.
 */
export declare function formatRagDoctorLine(rag: NonNullable<DoctorJson["rag"]>): string;
/**
 * `mw.py doctor` prints its RAG row only when `mw.py:523` sees
 * `rag.exists or rag.enabled`. `_doctor_rag` always returns a dict, so a
 * presence test alone would add a `not enabled` row to a project with no RAG
 * config at all. Mirroring that gate keeps the window text equal to the
 * terminal text in both directions (D-308/AC-304).
 */
export declare function shouldShowRagDoctorRow(rag: DoctorJson["rag"]): rag is NonNullable<DoctorJson["rag"]>;
/** Format a doctor JSON report as a readable Chinese summary (same data as
 * the CLI text output — the TS side never re-implements checks, AC-007). */
export declare function formatDoctorReport(report: DoctorJson, fix: boolean): string;
/** Split a command line on whitespace, honoring double-quoted segments
 * (Windows paths with spaces). Exported for tests. */
export declare function splitCommandLine(line: string): string[];
/** Parsed /mw target set flags. */
export interface TargetSetFlags {
    game: string;
    engine?: string;
    vcs?: string;
    uproject?: string;
}
/** Parse the flag tail of `/mw target set`. null when --game is missing or a
 * known flag has no value (unknown flags are ignored — mw.py validates). */
export declare function parseTargetSetFlags(parts: string[]): TargetSetFlags | null;
/** /mw target — dual-workspace config from the pi window. Thin wrapper over
 * `mw.py target` (single source of parsing/validation/rendering); the runner
 * is injectable for tests. set/clear remind that dual mode applies on the
 * NEXT worker spawn — no serve restart needed (launcher resolves per spawn). */
export declare function runMwTargetCommand(ctx: ExtensionCommandContext, projectDir: string, argsText: string, runner?: (projectDir: string, args: string[]) => MwCliResult): Promise<void>;
/** Parsed /mw partition set flags. `roots` keeps the raw NAME=DIR values in
 * command-line order (repeatable flag — order is forwarded verbatim). */
export interface PartitionSetFlags {
    parent: string;
    partition?: string;
    vcs?: string;
    roots: string[];
}
/** Parse the flag tail of `/mw partition set`. null when --parent is missing
 * or a known flag has no value (unknown flags are ignored — mw.py validates). */
export declare function parsePartitionSetFlags(parts: string[]): PartitionSetFlags | null;
/** /mw partition — partition-workspace config from the pi window (mw-target-
 * partition D-010). Thin wrapper over `mw.py partition` (single source of
 * parsing/validation/rendering — the same entry point a direct CLI run hits,
 * so identical args ⇒ identical target.yml bytes); the runner is injectable
 * for tests. set/on remind that the mode applies on the NEXT worker spawn —
 * no serve restart needed (launcher resolves per spawn). */
export declare function runMwPartitionCommand(ctx: ExtensionCommandContext, projectDir: string, argsText: string, runner?: (projectDir: string, args: string[]) => MwCliResult): Promise<void>;
/** /mw model — dispatch model defaults from the pi window. Thin wrapper over
 * `mw.py model` (single source of parsing/validation/rendering); the runner is
 * injectable for tests. set/clear remind when the change takes effect:
 * worker roles on the next spawn (launcher resolves per spawn, no serve
 * restart), `main` at the next window start (session_start application). */
export declare function runMwModelCommand(ctx: ExtensionCommandContext, projectDir: string, argsText: string, runner?: (projectDir: string, args: string[]) => MwCliResult): Promise<void>;
/** /mw command description (exported so the registration test can assert the
 * RAG branch stays documented — VC-311). */
export declare const MW_COMMAND_DESCRIPTION = "Control mw: build / init / start / stop / restart / status / doctor / update / target / partition / model / rag / ack";
/** Lines of `mw rag` output shown before truncation (D-307): the notify channel
 * is narrow, and `rag list` / `rag audit` outputs can be long. */
export declare const RAG_OUTPUT_MAX_LINES = 30;
/** Truncation footer (D-307): hand the user the exact command for the full
 * output instead of dropping it silently. `<sub>` / `<dir>` stay placeholders —
 * formatRagOutput only ever sees the output text. */
export declare const RAG_FULL_OUTPUT_HINT = "\u5B8C\u6574\u8F93\u51FA\uFF1Apython mw.py rag <sub> --project <dir>";
/**
 * Parse `/mw rag <raw>` into the subcommand and its verbatim argument tail.
 * Pure and CLI-free (VC-307): an empty or unknown sub returns the usage text
 * naming every RAG_SUBCOMMANDS entry, so the caller can reject before any
 * spawn. Arguments after the sub pass through untouched — Python stays the
 * single source of argument semantics.
 */
export declare function parseRagArgs(raw: string): {
    sub: string;
    rest: string[];
} | {
    usage: string;
};
/**
 * Map a `mw.py rag` exit code to the notify level and shorten long output
 * (D-307): 0=info, 1=warning (audit findings are expected), anything else
 * error. Output over RAG_OUTPUT_MAX_LINES is truncated with the full-command
 * hint appended so nothing is lost.
 */
export declare function formatRagOutput(output: string, code: number): {
    text: string;
    level: "info" | "warning" | "error";
};
/** /mw rag — thin wrapper over `mw.py rag` (single source of parsing,
 * validation and rendering); the runner is injectable for tests so the
 * unknown-sub path can be proven spawn-free (VC-307). The output content is
 * never parsed — only the exit code selects the notify level. */
export declare function runMwRagCommand(ctx: ExtensionCommandContext, projectDir: string, raw: string, runner?: (projectDir: string, args: string[]) => {
    ok: boolean;
    code: number;
    output: string;
}): Promise<void>;
export declare function registerMwCommands(pi: ExtensionAPI, projectDir: string, workerStore: WorkerStore, ackStore: AckStore, watch: PmWatchState, agenticdocRoot: string): void;
//# sourceMappingURL=ui-bridge.d.ts.map