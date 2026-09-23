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

import * as fs from "node:fs";
import * as path from "node:path";
import type { RagErrorKind } from "./adapter.ts";

export interface BudgetState {
	chatUsed: number;
	chatBudget: number;
	timeUsedMs: number;
	timeBudgetMs: number;
}

export type BudgetCheck = { ok: true } | { ok: false; kind: "budget"; message: string };

export interface BudgetOptions {
	/** Task wall budget in ms (`task.md timeout:` / `PI_WORKER_TIMEOUT_MS`); null disables the guard. */
	taskWallMs?: number | null;
	/** Clock injection for tests. */
	now?: () => number;
}

/** Fraction of the task wall budget after which `rag_chat` is refused. */
export const WALL_GUARD_RATIO = 0.7;

export const RAG_BUDGET_FILENAME = "rag-budget.json";

/** Heartbeat cadence for every potentially long RAG call (D-006: 30s). */
export const RAG_HEARTBEAT_INTERVAL_MS = 30_000;

/** Breaker kinds: transport failures only (D-005). */
const BREAKER_KINDS: ReadonlySet<RagErrorKind> = new Set(["connect", "timeout", "protocol"]);

/** Consecutive counted failures that open the breaker. */
export const BREAKER_THRESHOLD = 3;

function toNonNegativeInt(value: number): number {
	return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}

function readBudgetState(file: string): BudgetState | null {
	let text: string;
	try {
		text = fs.readFileSync(file, "utf8");
	} catch {
		return null;
	}
	let parsed: unknown;
	try {
		parsed = JSON.parse(text);
	} catch {
		return null;
	}
	if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
	const record = parsed as Record<string, unknown>;
	const number = (key: string): number => {
		const value = record[key];
		return typeof value === "number" && Number.isFinite(value) ? value : 0;
	};
	return {
		chatUsed: toNonNegativeInt(number("chatUsed")),
		chatBudget: toNonNegativeInt(number("chatBudget")),
		timeUsedMs: toNonNegativeInt(number("timeUsedMs")),
		timeBudgetMs: toNonNegativeInt(number("timeBudgetMs")),
	};
}

export class Budget {
	/** Session start; the wall guard measures `now - startedAt`. */
	readonly startedAt: number;
	readonly chatBudget: number;
	readonly timeBudgetMs: number;
	/** Task wall budget for the 70% guard; null = guard disabled. */
	readonly taskWallMs: number | null;

	private readonly workerTaskDir: string | null;
	private readonly now: () => number;
	private chatUsed = 0;
	private timeUsedMs = 0;

	constructor(workerTaskDir: string | null, chatBudget: number, timeBudgetMs: number, opts: BudgetOptions = {}) {
		this.workerTaskDir = workerTaskDir !== null && workerTaskDir.length > 0 ? workerTaskDir : null;
		this.chatBudget = toNonNegativeInt(chatBudget);
		this.timeBudgetMs = toNonNegativeInt(timeBudgetMs);
		this.taskWallMs = opts.taskWallMs ?? null;
		this.now = opts.now ?? Date.now;
		this.startedAt = this.now();
		this.load();
	}

	/** Seed counters from a previous run in the same task dir (read-only). */
	private load(): void {
		const state = this.readExisting();
		if (state === null) return;
		this.chatUsed = state.chatUsed;
		this.timeUsedMs = state.timeUsedMs;
	}

	/**
	 * Synchronous reservation: enforce the cumulative budget, then spend one
	 * chat slot **before** any `await`. The count is persisted at once so a
	 * crash mid-call still leaves the reservation behind.
	 */
	reserveChat(): BudgetCheck {
		const cumulative = this.checkCumulative();
		if (!cumulative.ok) return cumulative;
		if (this.chatUsed >= this.chatBudget) {
			return {
				ok: false,
				kind: "budget",
				message: `rag chat budget exhausted (used=${this.chatUsed}, budget=${this.chatBudget})`,
			};
		}
		this.chatUsed += 1;
		this.persist();
		return { ok: true };
	}

	/**
	 * Settle a chat reservation. `ok=true` keeps the spent slot (the call was
	 * made). On failure only a provably-undelivered `connect` (or an explicit
	 * `null` release, used when the guard refuses before the request) refunds;
	 * `timeout` may have been delivered and therefore never refunds.
	 */
	settleChat(ok: boolean, kind: RagErrorKind | null): void {
		if (ok) return;
		if (kind !== "connect" && kind !== null) return;
		if (this.chatUsed > 0) this.chatUsed -= 1;
		this.persist();
	}

	/** Charge the elapsed wall time of one logical call (success or failure). */
	accumulate(ms: number): void {
		if (!Number.isFinite(ms) || ms <= 0) return;
		this.timeUsedMs += Math.round(ms);
		this.persist();
	}

	/** Task-level cumulative RAG time budget (VC-025). */
	checkCumulative(): BudgetCheck {
		if (this.timeUsedMs > this.timeBudgetMs) {
			return {
				ok: false,
				kind: "budget",
				message: `rag cumulative time budget exhausted (used=${this.timeUsedMs}ms, budget=${this.timeBudgetMs}ms)`,
			};
		}
		return { ok: true };
	}

	/** Cheap retrieval is still allowed while the cumulative budget holds. */
	canCallCheap(): boolean {
		return this.checkCumulative().ok;
	}

	/** Wall-clock guard: past 70% of the task wall budget only cheap calls pass. */
	checkWall(nowMs: number): BudgetCheck {
		const wall = this.taskWallMs;
		if (wall === null || !Number.isFinite(wall) || wall <= 0) return { ok: true };
		const elapsed = Math.max(0, nowMs - this.startedAt);
		if (elapsed > wall * WALL_GUARD_RATIO) {
			return {
				ok: false,
				kind: "budget",
				message: `rag wall clock guard: elapsed=${elapsed}ms exceeds ${Math.round(
					WALL_GUARD_RATIO * 100,
				)}% of task wall budget ${wall}ms`,
			};
		}
		return { ok: true };
	}

	state(): BudgetState {
		return {
			chatUsed: this.chatUsed,
			chatBudget: this.chatBudget,
			timeUsedMs: this.timeUsedMs,
			timeBudgetMs: this.timeBudgetMs,
		};
	}

	/**
	 * Rewrite `<workerTaskDir>/rag-budget.json` as a whole (read-modify-write).
	 * No-op when there is no task dir (PM/non-worker session) — the file is
	 * created on the first RAG call, never at activation (D-014).
	 */
	persist(): void {
		const dir = this.workerTaskDir;
		if (dir === null) return;
		const existing = this.readExisting();
		if (existing !== null) {
			this.chatUsed = Math.max(this.chatUsed, existing.chatUsed);
			this.timeUsedMs = Math.max(this.timeUsedMs, existing.timeUsedMs);
		}
		const merged: BudgetState = {
			chatUsed: this.chatUsed,
			chatBudget: this.chatBudget,
			timeUsedMs: this.timeUsedMs,
			timeBudgetMs: this.timeBudgetMs,
		};
		fs.mkdirSync(dir, { recursive: true });
		fs.writeFileSync(this.filePath(), `${JSON.stringify(merged, null, 2)}\n`, "utf8");
	}

	private filePath(): string {
		return path.join(this.workerTaskDir ?? "", RAG_BUDGET_FILENAME);
	}

	private readExisting(): BudgetState | null {
		if (this.workerTaskDir === null) return null;
		return readBudgetState(this.filePath());
	}
}

/**
 * Per-server breaker over the three transport kinds. An open breaker is the
 * caller's signal to reject **before** the transport, so an open circuit costs
 * zero requests.
 */
export class Breaker {
	private readonly failures = new Map<string, number>();

	noteFailure(server: string, kind: RagErrorKind): void {
		if (!BREAKER_KINDS.has(kind)) return;
		this.failures.set(server, (this.failures.get(server) ?? 0) + 1);
	}

	isOpen(server: string): boolean {
		return (this.failures.get(server) ?? 0) >= BREAKER_THRESHOLD;
	}

	noteSuccess(server: string): void {
		this.failures.delete(server);
	}
}

/**
 * Run `fn` while pinging `onUpdate` every `intervalMs` (default 30s) with an
 * elapsed-time message. The host turns `onUpdate` into `tool_execution_update`,
 * which refreshes the worker's activity watchdog (`worker-mode.ts` touch()), so
 * a long `rag_chat`/retrieval cannot be mistaken for a hung process. The timer
 * is always cleared, on resolve and on reject; `onUpdate` errors are swallowed
 * (evidence must never break a call).
 */
export function withHeartbeat<T>(
	intervalMs: number,
	onUpdate: ((message: string) => void) | undefined,
	fn: () => Promise<T>,
): Promise<T> {
	const period = Number.isFinite(intervalMs) && intervalMs > 0 ? intervalMs : RAG_HEARTBEAT_INTERVAL_MS;
	const startedAt = Date.now();
	const timer = setInterval(() => {
		if (onUpdate === undefined) return;
		const elapsedMs = Date.now() - startedAt;
		try {
			onUpdate(`rag call in progress (elapsed ${Math.round(elapsedMs / 1000)}s)`);
		} catch {
			// Heartbeats are best-effort liveness only.
		}
	}, period);
	return Promise.resolve()
		.then(fn)
		.finally(() => clearInterval(timer));
}
