/**
 * rag/budget.ts — RAG call/heartbeat budget, wall-clock guard, breaker (T-05).
 *
 * Three independent guards, all consulted once per **logical** call (T-13: a
 * fan-out such as `rag_sources` -> `list_sources`+`list_collections` is still a
 * single invocation):
 *
 *   1. chat count budget (`rag_chat_budget`, default 2). `reserveChat` is
 *      synchronous on purpose: it increments **before** the network `await`, so
 *      two concurrent calls can never both spend the last slot.
 *   2. task-level cumulative RAG time (`rag_time_budget_s`, default 900s).
 *      `accumulate` after every call; over budget rejects every later call.
 *   3. remaining wall-clock guard: past 70% of the task wall budget only cheap
 *      retrieval is allowed — `rag_chat` is refused.
 *
 * `rag-budget.json` lives in the worker task dir and is created on the **first
 * RAG call only** (D-014): the constructor/read is read-only, `persist` is the
 * single write point and it rewrites the whole document (read-modify-write).
 *
 * The breaker counts only `connect`/`timeout`/`protocol` (D-005): those prove
 * the transport failed. `capability`, `budget` and `tool` are application-level
 * answers and must not trip it.
 */
import type { RagErrorKind } from "./adapter.ts";
export interface BudgetState {
    chatUsed: number;
    chatBudget: number;
    timeUsedMs: number;
    timeBudgetMs: number;
}
export type BudgetCheck = {
    ok: true;
} | {
    ok: false;
    kind: "budget";
    message: string;
};
export interface BudgetOptions {
    /** Task wall budget in ms (`task.md timeout:` / `PI_WORKER_TIMEOUT_MS`); null disables the guard. */
    taskWallMs?: number | null;
    /** Clock injection for tests. */
    now?: () => number;
}
/** Fraction of the task wall budget after which `rag_chat` is refused. */
export declare const WALL_GUARD_RATIO = 0.7;
export declare const RAG_BUDGET_FILENAME = "rag-budget.json";
/** Heartbeat cadence for every potentially long RAG call (D-006: 30s). */
export declare const RAG_HEARTBEAT_INTERVAL_MS = 30000;
/** Consecutive counted failures that open the breaker. */
export declare const BREAKER_THRESHOLD = 3;
export declare class Budget {
    /** Session start; the wall guard measures `now - startedAt`. */
    readonly startedAt: number;
    readonly chatBudget: number;
    readonly timeBudgetMs: number;
    /** Task wall budget for the 70% guard; null = guard disabled. */
    readonly taskWallMs: number | null;
    private readonly workerTaskDir;
    private readonly now;
    private chatUsed;
    private timeUsedMs;
    constructor(workerTaskDir: string | null, chatBudget: number, timeBudgetMs: number, opts?: BudgetOptions);
    /** Seed counters from a previous run in the same task dir (read-only). */
    private load;
    /**
     * Synchronous reservation: enforce the cumulative budget, then spend one
     * chat slot **before** any `await`. The count is persisted at once so a
     * crash mid-call still leaves the reservation behind.
     */
    reserveChat(): BudgetCheck;
    /**
     * Settle a chat reservation. `ok=true` keeps the spent slot (the call was
     * made). On failure only a provably-undelivered `connect` (or an explicit
     * `null` release, used when the guard refuses before the request) refunds;
     * `timeout` may have been delivered and therefore never refunds.
     */
    settleChat(ok: boolean, kind: RagErrorKind | null): void;
    /** Charge the elapsed wall time of one logical call (success or failure). */
    accumulate(ms: number): void;
    /** Task-level cumulative RAG time budget (VC-025). */
    checkCumulative(): BudgetCheck;
    /** Cheap retrieval is still allowed while the cumulative budget holds. */
    canCallCheap(): boolean;
    /** Wall-clock guard: past 70% of the task wall budget only cheap calls pass. */
    checkWall(nowMs: number): BudgetCheck;
    state(): BudgetState;
    /**
     * Rewrite `<workerTaskDir>/rag-budget.json` as a whole (read-modify-write).
     * No-op when there is no task dir (PM/non-worker session) — the file is
     * created on the first RAG call, never at activation (D-014).
     */
    persist(): void;
    private filePath;
    private readExisting;
}
/**
 * Per-server breaker over the three transport kinds. An open breaker is the
 * caller's signal to reject **before** the transport, so an open circuit costs
 * zero requests.
 */
export declare class Breaker {
    private readonly failures;
    noteFailure(server: string, kind: RagErrorKind): void;
    isOpen(server: string): boolean;
    noteSuccess(server: string): void;
}
/**
 * Run `fn` while pinging `onUpdate` every `intervalMs` (default 30s) with an
 * elapsed-time message. The host turns `onUpdate` into `tool_execution_update`,
 * which refreshes the worker's activity watchdog (`worker-mode.ts` touch()), so
 * a long `rag_chat`/retrieval cannot be mistaken for a hung process. The timer
 * is always cleared, on resolve and on reject; `onUpdate` errors are swallowed
 * (evidence must never break a call).
 */
export declare function withHeartbeat<T>(intervalMs: number, onUpdate: ((message: string) => void) | undefined, fn: () => Promise<T>): Promise<T>;
//# sourceMappingURL=budget.d.ts.map