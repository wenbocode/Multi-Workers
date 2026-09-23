/**
 * rag/guidelines.ts — the three-line call discipline appended to every RAG
 * tool's `promptGuidelines` (mw-rag-integration D-012 / T-04).
 *
 * Single source of truth for the *tool* guidance only. The methodology body
 * (citation format, anti-patterns, research-doc sections) lives in the mw-rag
 * skill source under `packages/multi-workers/skills/` and is installed by the
 * explicit `mw rag sync` command — never duplicated here.
 */
export const RAG_PROMPT_GUIDELINES = [
    "Prefer rag_symbol / rag_graph for precise symbol and relationship lookups; use rag_search only when the symbol is unknown.",
    "Quote citations exactly as returned by the tools (server:source:file_path:line); never assemble a citation by hand.",
    "A RAG result counts as used only after it is written to rag/*.md with its citation and local verification state.",
];
//# sourceMappingURL=guidelines.js.map