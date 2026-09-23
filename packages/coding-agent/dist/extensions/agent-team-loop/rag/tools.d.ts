/**
 * rag/tools.ts — the RAG tool surface, registration gating and the per-type
 * subset activation (mw-rag-integration D-002 / T-04).
 *
 * Gating is structural (VC-001/AC-001): when `rag.enabled` is empty nothing is
 * registered, no server is probed and no file is written — there is no
 * "register then hide" path. When enabled, each enabled server is probed once
 * (5s, only servers declaring an `mcp` block) so the tool descriptions can
 * carry the `[unreachable at session start]` marker (VC-009).
 *
 * Call chain (design §5.2): capability gate -> budget/deadline (T-05, injected
 * via RagRuntimeHooks) -> transport (mcp first, cli fallback only for a
 * provably-undelivered `connect` on a read-only tool) -> normalization.
 * `RagToolError.server` carries the transport base URL / cli entry from T-03,
 * so it is re-tagged with the configured server name before it can reach an
 * evidence line or a breaker key.
 */
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { type RagErrorKind } from "./adapter.ts";
import type { BudgetState } from "./budget.ts";
import { type RagConfig } from "./config.ts";
import { McpSession } from "./mcp-client.ts";
/** Per-server probe budget at activation (design D-002, VC-009). */
export declare const RAG_PROBE_TIMEOUT_MS = 5000;
/** task.md header names for the per-task RAG budgets (D-006, T-04). */
export declare const RAG_CHAT_BUDGET_HEADER = "rag_chat_budget:";
export declare const RAG_TIME_BUDGET_HEADER = "rag_time_budget_s:";
/** The six always-visible RAG tools (AC-004). `rag_chat` is added below. */
export declare const RAG_BASE_TOOL_NAMES: readonly ["rag_search", "rag_symbol", "rag_graph", "rag_impact", "rag_sources", "rag_feedback"];
/** The single `rag-research`-only tool (AC-011 / VC-015). */
export declare const RAG_CHAT_TOOL_NAME = "rag_chat";
/**
 * Minimum per-call transport budget for `rag_chat` (mw-rag-integration T-09).
 * The reference service observed 41s-9min on chat, so the 180s default
 * `mcp.timeout_ms` (T-05) would cut healthy long answers off. Retrieval tools
 * keep the configured value; `rag/config.ts`'s schema is a locked cross-
 * language contract (T-12), so this is a constant, not a new field.
 */
export declare const RAG_CHAT_TIMEOUT_MS = 600000;
/** The subset of a server's mcp block that decides a per-call timeout. */
export interface RagCallTimeoutConfig {
    timeoutMs: number;
}
/**
 * Per-call transport timeout for one logical RAG tool: `rag_chat` takes
 * `max(config.mcp.timeoutMs, RAG_CHAT_TIMEOUT_MS)` so an explicit larger
 * configuration always wins; every retrieval tool keeps the configured value.
 * Exported for the T-09 timeout-contract test.
 */
export declare function ragCallTimeoutMs(logicalTool: string, config: RagCallTimeoutConfig): number;
/**
 * Budget operations the tool chain consults. Structural mirror of T-05's
 * `Budget` class in `rag/budget.ts`, so T-05 can drop its instance straight
 * into `RagRuntime.budget` without a nominal dependency.
 */
export interface RagBudgetOps {
    readonly startedAt: number;
    readonly taskWallMs: number | null;
    reserveChat(): {
        ok: true;
    } | {
        ok: false;
        kind: "budget";
        message: string;
    };
    settleChat(ok: boolean, kind: RagErrorKind | null): void;
    accumulate(ms: number): void;
    checkCumulative(): {
        ok: true;
    } | {
        ok: false;
        kind: "budget";
        message: string;
    };
    checkWall(nowMs: number): {
        ok: true;
    } | {
        ok: false;
        kind: "budget";
        message: string;
    };
    canCallCheap(): boolean;
    state(): BudgetState;
}
/** Structural mirror of T-05's `Breaker` class (`connect`/`timeout`/`protocol`). */
export interface RagBreakerOps {
    noteFailure(server: string, kind: RagErrorKind): void;
    isOpen(server: string): boolean;
    noteSuccess(server: string): void;
}
/** Optional non-RAG dependencies, injected by the caller (T-05 wiring). */
export interface RagRuntimeHooks {
    budget?: RagBudgetOps;
    breaker?: RagBreakerOps;
    workerTaskDir?: string | null;
    /** Session role axis for the RAG default resolution (T-15); "" = unknown. */
    role?: string;
    /** Session phase axis for the RAG default resolution (T-15); "" = unknown. */
    phase?: string;
}
/** Per-session RAG state shared by every tool call (spec T-04 interface). */
export interface RagRuntime {
    config: RagConfig;
    controlRoot: string;
    workerTaskDir: string | null;
    /** Activate-time probe result per enabled server (missing = not probed). */
    reachable: Map<string, boolean>;
    sessions: Map<string, McpSession>;
    breaker: RagBreakerOps | null;
    budget: RagBudgetOps | null;
    /** Resolves once the probe finished and the tools are registered. */
    ready: Promise<void>;
    /** Whether the research-only `rag_chat` tool has been registered. */
    chatRegistered: boolean;
    /** Session role axis; "" (unknown/unregistered) leaves the defaults alone. */
    role: string;
    /** Session phase axis; "" (unknown/unregistered) leaves the defaults alone. */
    phase: string;
}
/**
 * Load the project config and register the RAG surface. Returns null (and
 * registers/probes nothing) when no server is enabled — the structural
 * zero-impact path. Throws `RagConfigError` for an unusable config; callers
 * fail closed.
 */
export declare function registerRagTools(pi: ExtensionAPI, controlRoot: string, hooks?: RagRuntimeHooks): RagRuntime | null;
/** Tool names the given task type may activate out of the RAG surface. */
export declare function ragToolNamesForType(rt: RagRuntime, type: string): string[];
/**
 * Idempotently set the active tool set for one agent run: the full base set
 * for the type plus its RAG subset. `before_agent_start` fires on every run
 * (including phase/follow-up turns), so this recomputes the complete expected
 * set each time and never accumulates duplicates. A null runtime (RAG
 * disabled) reproduces the pre-RAG behavior byte for byte.
 */
export declare function applyRagTools(pi: ExtensionAPI, rt: RagRuntime | null, type: string): void;
/**
 * RAG dispatch pre-check (VC-003): load the merged config and reject an
 * unusable one (e.g. `enabled` naming an undefined server) before any task.md
 * is created. The returned message carries the server name and the visible
 * server list.
 */
export declare function validateRagEnabled(projectDir: string): {
    ok: true;
} | {
    ok: false;
    message: string;
};
/**
 * Resolve the skill transport working directory (D-302): an explicit
 * `skill.dir` resolves against the control workspace root (absolute values are
 * returned unchanged by `path.resolve`), while a missing/`null` `dir` means
 * the control workspace root itself. Pure, so it is unit-testable without
 * spawning the CLI.
 */
export declare function resolveCliDir(controlRoot: string, dir: string | null): string;
//# sourceMappingURL=tools.d.ts.map