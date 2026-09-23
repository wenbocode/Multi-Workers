/**
 * rag/evidence.ts — append-only RAG evidence lines (mw-rag-integration T-05).
 *
 * `trace.log` is the audit surface for every logical RAG call. The canonical
 * success line is `rag_call` and it carries both names: `tool` is the logical
 * tool the agent invoked and `mcp_tool` is the actual server tool name(s)
 * emitted by the T-13 adapter (`+`-joined when one logical call fans out, e.g.
 * `rag_sources` -> `list_sources+list_collections`).
 *
 * Two hard rules:
 *   - **Append only.** The writer reuses `output-writer.ts::appendTrace` (P-001);
 *     nothing here ever overwrites `trace.log`.
 *   - **Redact before writing.** Every line goes through `redactSecrets` with the
 *     configured `token_env` names, so a token that ends up echoed in a server
 *     response can never reach the trace.
 */
import * as path from "node:path";
import { appendTrace } from "../worker/output-writer.js";
export const RAG_FALLBACK = "rag_fallback";
export const RAG_UNAVAILABLE = "rag-unavailable";
export const RAG_REWRITE_DEGRADED = "rag-rewrite-degraded";
export const RAG_REQUIRED_MISSING = "rag-required-missing";
export const RAG_BUDGET_EXCEEDED = "rag-budget-exceeded";
/** `ms`/`results` are parsed by machine gates; keep them non-negative integers. */
function count(value) {
    return Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
}
/**
 * `rag_call server=<S> tool=<T> via=(mcp|cli) ms=<N> results=<N> [mcp_tool=<M>]`.
 * `mcp_tool` is appended whenever the caller knows the wire name — T-13's
 * mapping cannot be audited otherwise.
 */
export function ragCallLine(e) {
    const line = `rag_call server=${e.server} tool=${e.tool} via=${e.via} ms=${count(e.ms)} results=${count(e.results)}`;
    return e.mcpTool !== undefined && e.mcpTool !== null && e.mcpTool.length > 0
        ? `${line} mcp_tool=${e.mcpTool}`
        : line;
}
/** `rag_fallback server=<S> tool=<T> via=cli reason=<K>` (D-005 read-only connect). */
export function ragFallbackLine(e) {
    return `${RAG_FALLBACK} server=${e.server} tool=${e.tool} via=cli reason=${e.reason}`;
}
/** `rag-unavailable server=<S> tool=<T> kind=<K> ms=<N>` — no usable transport. */
export function ragUnavailableLine(e) {
    return `${RAG_UNAVAILABLE} server=${e.server} tool=${e.tool} kind=${e.kind} ms=${count(e.ms)}`;
}
/**
 * `rag-budget-exceeded server=<S> tool=<T> reason=<count|cumulative|wall>
 * used=<N> budget=<N>` — emitted even though no request was attempted, so a
 * dropped call is still visible in the trace.
 */
export function ragBudgetExceededLine(e) {
    return `${RAG_BUDGET_EXCEEDED} server=${e.server} tool=${e.tool} reason=${e.reason} used=${count(e.used)} budget=${count(e.budget)}`;
}
/** `rag-rewrite-degraded server=<S> tool=<T>` (VC-021; meta.rewrite_degraded=true). */
export function ragRewriteDegradedLine(e) {
    return `${RAG_REWRITE_DEGRADED} server=${e.server} tool=${e.tool}`;
}
/**
 * `rag-required-missing role=<R> phase=<P> server=<S>` — T-10/VC-014 emit this
 * when a `require=true` role/phase finished without a verifiable citation.
 */
export function ragRequiredMissingLine(e) {
    return `${RAG_REQUIRED_MISSING} role=${e.role} phase=${e.phase} server=${e.server}`;
}
/**
 * Append one evidence line to `<taskDir>/trace.log` through the single
 * trace writer (`appendTrace`), which prefixes `[FLOW] <ts> `. `taskDir` is
 * the worker task directory (`<agenticdocRoot>/<taskKey>`), so it round-trips
 * to `appendTrace(basename, dirname, line)` without a second write path.
 */
export function appendEvidence(taskDir, line) {
    const resolved = path.resolve(taskDir);
    appendTrace(path.basename(resolved), path.dirname(resolved), line);
}
/**
 * Replace the **current value** of every named token env var with
 * `<redacted>`. Values are read at call time (the env is the source of truth),
 * and empty values are ignored so `""` can never mangle a line.
 */
export function redactSecrets(text, tokenEnvNames) {
    let redacted = text;
    for (const envName of tokenEnvNames) {
        const value = process.env[envName];
        if (value === undefined || value.length === 0)
            continue;
        if (!redacted.includes(value))
            continue;
        redacted = redacted.split(value).join("<redacted>");
    }
    return redacted;
}
//# sourceMappingURL=evidence.js.map