/**
 * rag/block.ts — single source of the task.md `<!-- mw-rag: v1 -->` block
 * (mw-rag-integration D-009 / T-04).
 *
 * The render is a pure function of the merged `RagConfig` and the task
 * metadata; the Python side (`mw_common.render_rag_block`, T-06) emits the
 * byte-identical text. The byte contract is locked by
 * `packages/multi-workers/test/fixtures/rag-block.golden.md` (347 B, **no
 * trailing newline**); the injection side appends it with
 * `content.rstrip() + "\n\n" + block + "\n"`.
 *
 * `renderRagBlock` returns null when `enabled` is empty — the structural
 * zero-impact guarantee (D-014/AC-001): no RAG byte is written at all.
 */
import { type RagConfig } from "./config.ts";
/** Marker opening the block; the idempotent replacement boundary. */
export declare const RAG_MARKER_V1 = "<!-- mw-rag: v1 -->";
/** Citation grammar rendered into task.md (design D-004). */
export declare const RAG_CITATION_SYNTAX = "<server>:<source>:<file_path>:<line>";
/**
 * Task metadata the block depends on. Field names are the TS runtime
 * (camelCase) shape; the Python side reads its own `chat_budget` /
 * `time_budget_s` keys. Both drive the same rendered lines.
 */
export interface RagTaskMeta {
    type?: string;
    role?: string;
    phase?: string;
    chatBudget?: number;
    timeBudgetS?: number;
}
/**
 * Render the `mw-rag: v1` block for one task, or null when the project has no
 * enabled servers. Mirrors `mw_common.render_rag_block` line for line.
 */
export declare function renderRagBlock(config: RagConfig, meta: RagTaskMeta): string | null;
//# sourceMappingURL=block.d.ts.map