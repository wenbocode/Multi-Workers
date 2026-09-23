/**
 * overcode-v1 RAG adapter (mw-rag-integration D-004 / D-007).
 *
 * Pure function layer: no network, no writes. The only filesystem access is
 * read-only (loading the path_roots mapping and checking local existence).
 *
 * Citation grammar: `server ":" source ":" file_path ":" line`
 *   - parse takes the FIRST two segments for server/source (neither may be
 *     empty or contain `:`),
 *   - takes the LAST segment for `line` (must match `^\d+$`),
 *   - keeps EVERYTHING in between — including `::`, spaces, backslashes and
 *     Unicode — as `file_path`.
 */
export type RagErrorKind = "connect" | "protocol" | "tool" | "capability" | "budget" | "timeout" | "circuit";
export interface RagCitation {
    server: string;
    source: string;
    filePath: string;
    line: number;
}
export interface RagItem {
    symbol_name: string;
    qualified_name: string | null;
    symbol_type: string | null;
    file_path: string;
    line_start: number | null;
    line_end: number | null;
    snippet: string | null;
    score: number | null;
    citation: string | null;
    local_path: string | null;
    exists: boolean;
    line_hint: number | null;
    snapshot_warning: true;
}
export interface RagEnvelope {
    server: string;
    tool: string;
    source: string | null;
    snapshot: true;
    items: RagItem[];
    meta: Record<string, unknown>;
    /**
     * Actual server tool name(s) emitted for this logical call, joined with `+`
     * when one logical tool fans out (T-13, AC-006). `tool` stays the logical
     * name; this field is the wire truth for audits.
     */
    mcp_tool?: string;
}
export interface RagToolError {
    kind: RagErrorKind;
    server: string;
    tool: string;
    message: string;
    detail?: unknown;
}
export interface ResolvedLocalPath {
    localPath: string | null;
    exists: boolean;
    lineHint: number | null;
    reason: string | null;
}
export declare function formatCitation(c: RagCitation): string;
export declare function parseCitation(text: string): RagCitation | null;
/** Returns null when the mapping is not configured (missing file or null path). */
export declare function loadPathRoots(pathRootsFile: string | null): Record<string, string> | null;
/**
 * Maps a RAG `file_path` (`role::rel` or bare `rel`, bare defaults to
 * `engine`) onto a normalized absolute local path.
 */
export declare function resolveLocalPath(filePath: string, roots: Record<string, string> | null): ResolvedLocalPath;
/**
 * Logical tool name -> server tool names (T-13, AC-006).
 *
 * The reference service (`adapter: overcode-v1`) does not expose our logical
 * names one-for-one: `rag_graph` is `graph_query`, `rag_sources` is split over
 * `list_sources` + `list_collections`, and a rewrite switch routes
 * `rag_search` to `rag_search_multi_rounds`. All of it lives in this data table
 * so the call chain never special-cases a tool by name; a second service family
 * plugs in as a new adapter, not as per-server overrides.
 */
export interface RagToolTarget {
    /** Server tool names to call, in order. More than one entry is merged back. */
    mcp: readonly string[];
    /** Server tool used instead when a rewrite switch is on. */
    multi?: string;
    /** Strategy for folding several server responses into one payload. */
    merge?: "sources";
}
export declare const RAG_TOOL_MAP: {
    readonly rag_search: {
        readonly mcp: readonly ["rag_search"];
        readonly multi: "rag_search_multi_rounds";
    };
    readonly rag_symbol: {
        readonly mcp: readonly ["rag_symbol"];
    };
    readonly rag_graph: {
        readonly mcp: readonly ["graph_query"];
    };
    readonly rag_impact: {
        readonly mcp: readonly ["rag_impact"];
    };
    readonly rag_sources: {
        readonly mcp: readonly ["list_sources", "list_collections"];
        readonly merge: "sources";
    };
    readonly rag_feedback: {
        readonly mcp: readonly ["rag_feedback"];
    };
    readonly rag_chat: {
        readonly mcp: readonly ["rag_chat"];
    };
};
export type LogicalRagTool = keyof typeof RAG_TOOL_MAP;
export interface RagToolCall {
    /** Actual server tool name. */
    name: string;
    args: Record<string, unknown>;
}
/**
 * Resolve one logical tool call into the concrete server calls. `rag_sources`
 * fans out to two reads; an unknown logical name is a configuration error
 * raised before any request is attempted.
 */
export declare function ragToolCalls(logical: string, args: Record<string, unknown>): RagToolCall[];
/**
 * Fold the raw responses of one logical call back into a single payload for
 * `normalizeResults`. A single-leg logical tool returns its payload unchanged;
 * `rag_sources` merges `list_sources` + `list_collections` keeping per-entry
 * source/collection attribution (`symbol_type` + the raw entry in `snippet`).
 * Any leg missing is a hard error: no partial merge.
 */
export declare function mergeToolResponses(logical: string, responses: unknown[]): unknown;
export declare function capabilityError(server: string, tool: string, caps: {
    graph: boolean;
    chat: boolean;
}): RagToolError | null;
export declare function normalizeResults(server: string, tool: string, source: string | null, raw: unknown, roots: Record<string, string> | null): RagEnvelope;
//# sourceMappingURL=adapter.d.ts.map