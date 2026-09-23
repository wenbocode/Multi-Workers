import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
import { AckStore } from "../shared/ack-store.ts";
import { IndexStore } from "../shared/index-store.ts";
import { WorkerStore } from "../shared/worker-store.ts";
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
export interface DispatchScanOptions {
    /** Keys already warned about in this session — a key is reported at most once. */
    warnedKeys?: Set<string>;
    /** Fires once per undocumented key whose worker tasks were skipped.
     * MUST return whether the event was actually broadcast: false when it was
     * intentionally suppressed (e.g. scoped to another window's key) so the
     * once-per-session dedup does not burn the key's only slot. */
    onDocGate?: (key: string, gaps: string[]) => boolean;
}
export declare function dispatchNewTasks(workerStore: WorkerStore, agenticdocRoot: string, opts?: DispatchScanOptions): Promise<void>;
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