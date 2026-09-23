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
import * as fs from "node:fs";
import * as path from "node:path";
import { RagConfigError } from "./config.js";
const DEFAULT_ROLE = "engine";
const GRAPH_TOOLS = new Set(["rag_graph", "rag_impact"]);
const CHAT_TOOLS = new Set(["rag_chat"]);
/** Meta keys copied verbatim into the envelope (plus every `total_*` key). */
const META_KEYS = new Set([
    "affected_files",
    "answer",
    "callers_by_hop",
    "count",
    "depth",
    "file",
    "lead_only",
    "multiple_matches",
    "note",
    "operation",
    "resolved_symbol",
    "rewrite_degraded",
    "static_analysis",
    "status",
    "symbol",
]);
/** Result array keys, in priority order, used to locate the item list. */
const ITEM_ARRAY_KEYS = ["documents", "results", "symbols", "items"];
function fail(message) {
    throw new RagConfigError("invalid-shape", message);
}
function optionalString(value) {
    return typeof value === "string" && value.length > 0 ? value : null;
}
function optionalNumber(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
}
export function formatCitation(c) {
    if (c.server.length === 0 || c.server.includes(":")) {
        fail(`citation server must be non-empty and contain no ':' (got ${JSON.stringify(c.server)})`);
    }
    if (c.source.length === 0 || c.source.includes(":")) {
        fail(`citation source must be non-empty and contain no ':' (got ${JSON.stringify(c.source)})`);
    }
    if (!Number.isInteger(c.line) || c.line < 0) {
        fail(`citation line must be a non-negative integer (got ${String(c.line)})`);
    }
    return `${c.server}:${c.source}:${c.filePath}:${c.line}`;
}
export function parseCitation(text) {
    if (typeof text !== "string")
        return null;
    // Left: server = up to the first ':' (non-empty).
    const firstColon = text.indexOf(":");
    if (firstColon <= 0)
        return null;
    const server = text.slice(0, firstColon);
    // Left: source = up to the second ':' (non-empty).
    const afterServer = text.slice(firstColon + 1);
    const secondColon = afterServer.indexOf(":");
    if (secondColon <= 0)
        return null;
    const source = afterServer.slice(0, secondColon);
    // Right: line = the last ':' segment, digits only.
    const tail = afterServer.slice(secondColon + 1);
    const lastColon = tail.lastIndexOf(":");
    if (lastColon < 0)
        return null;
    const filePath = tail.slice(0, lastColon);
    const lineText = tail.slice(lastColon + 1);
    if (filePath.length === 0 || !/^\d+$/.test(lineText))
        return null;
    const line = Number.parseInt(lineText, 10);
    if (!Number.isSafeInteger(line))
        return null;
    return { server, source, filePath, line };
}
/** Returns null when the mapping is not configured (missing file or null path). */
export function loadPathRoots(pathRootsFile) {
    if (pathRootsFile === null || pathRootsFile.length === 0)
        return null;
    let text;
    try {
        text = fs.readFileSync(pathRootsFile, "utf8");
    }
    catch (error) {
        const code = error.code;
        if (code === "ENOENT" || code === "ENOTDIR")
            return null;
        fail(`cannot read path_roots file ${pathRootsFile}: ${String(error)}`);
    }
    // utf-8-sig semantics: strip a leading BOM written by Windows editors.
    const withoutBom = text.startsWith("\uFEFF") ? text.slice(1) : text;
    let parsed;
    try {
        parsed = JSON.parse(withoutBom);
    }
    catch (error) {
        fail(`path_roots file is not valid JSON: ${pathRootsFile}: ${String(error)}`);
    }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        fail(`path_roots file must contain a JSON object: ${pathRootsFile}`);
    }
    const roots = {};
    for (const [key, value] of Object.entries(parsed)) {
        if (key.startsWith("_"))
            continue;
        if (typeof value !== "string" || value.trim().length === 0) {
            fail(`path_roots entry '${key}' must be a non-empty path string`);
        }
        roots[key] = value;
    }
    return roots;
}
/**
 * Maps a RAG `file_path` (`role::rel` or bare `rel`, bare defaults to
 * `engine`) onto a normalized absolute local path.
 */
export function resolveLocalPath(filePath, roots) {
    if (roots === null) {
        return { localPath: null, exists: false, lineHint: null, reason: "path_roots not configured" };
    }
    let role = DEFAULT_ROLE;
    let relative = filePath;
    const separator = filePath.indexOf("::");
    if (separator >= 0) {
        role = filePath.slice(0, separator).trim();
        relative = filePath.slice(separator + 2);
    }
    if (!Object.hasOwn(roots, role)) {
        const available = Object.keys(roots).sort().join(", ");
        return {
            localPath: null,
            exists: false,
            lineHint: null,
            reason: `unknown role '${role}' (available roles: ${available})`,
        };
    }
    const normalizedRelative = relative.trim().replace(/\\/g, "/").replace(/^\/+/, "");
    const root = path.resolve(roots[role]);
    const resolved = path.resolve(root, normalizedRelative);
    if (!isInside(root, resolved)) {
        return {
            localPath: null,
            exists: false,
            lineHint: null,
            reason: `path traversal escapes role '${role}' root: ${filePath}`,
        };
    }
    let exists = false;
    try {
        exists = fs.statSync(resolved).isFile();
    }
    catch {
        exists = false;
    }
    return { localPath: resolved, exists, lineHint: null, reason: exists ? null : "file missing" };
}
function isInside(root, candidate) {
    const relative = path.relative(root, candidate);
    if (relative === "")
        return true;
    if (path.isAbsolute(relative))
        return false;
    return relative.split(/[\\/]/)[0] !== "..";
}
export const RAG_TOOL_MAP = {
    rag_search: { mcp: ["rag_search"], multi: "rag_search_multi_rounds" },
    rag_symbol: { mcp: ["rag_symbol"] },
    rag_graph: { mcp: ["graph_query"] },
    rag_impact: { mcp: ["rag_impact"] },
    rag_sources: { mcp: ["list_sources", "list_collections"], merge: "sources" },
    rag_feedback: { mcp: ["rag_feedback"] },
    rag_chat: { mcp: ["rag_chat"] },
};
/** Switches that select the multi-round server tool instead of `rag_search`. */
const REWRITE_SWITCHES = new Set(["multi_rounds", "auto_rewrite"]);
const RAG_TOOL_TABLE = RAG_TOOL_MAP;
function toolTarget(logical) {
    if (!Object.hasOwn(RAG_TOOL_MAP, logical)) {
        fail(`unknown logical rag tool '${logical}' (no RAG_TOOL_MAP entry)`);
    }
    const target = RAG_TOOL_TABLE[logical];
    if (target === undefined || target.mcp.length === 0) {
        fail(`RAG_TOOL_MAP entry for '${logical}' has no server tool`);
    }
    return target;
}
/**
 * Resolve one logical tool call into the concrete server calls. `rag_sources`
 * fans out to two reads; an unknown logical name is a configuration error
 * raised before any request is attempted.
 */
export function ragToolCalls(logical, args) {
    const target = toolTarget(logical);
    if (target.multi !== undefined && (args.multi_rounds === true || args.auto_rewrite === true)) {
        return [{ name: target.multi, args: withoutRewriteSwitches(args) }];
    }
    return target.mcp.map((name) => ({ name, args: { ...args } }));
}
function withoutRewriteSwitches(args) {
    const next = {};
    for (const [key, value] of Object.entries(args)) {
        if (REWRITE_SWITCHES.has(key))
            continue;
        next[key] = value;
    }
    return next;
}
/**
 * Fold the raw responses of one logical call back into a single payload for
 * `normalizeResults`. A single-leg logical tool returns its payload unchanged;
 * `rag_sources` merges `list_sources` + `list_collections` keeping per-entry
 * source/collection attribution (`symbol_type` + the raw entry in `snippet`).
 * Any leg missing is a hard error: no partial merge.
 */
export function mergeToolResponses(logical, responses) {
    const target = toolTarget(logical);
    if (target.merge === "sources") {
        if (responses.length !== target.mcp.length) {
            fail(`rag_sources expects ${target.mcp.length} responses, got ${responses.length}`);
        }
        return mergeSourcesResponses(responses[0], responses[1]);
    }
    if (responses.length !== 1) {
        fail(`${logical} expects a single response, got ${responses.length}`);
    }
    return responses[0];
}
function mergeSourcesResponses(sourcesRaw, collectionsRaw) {
    const sources = listedEntries(sourcesRaw, "sources", "list_sources");
    const collections = listedEntries(collectionsRaw, "collections", "list_collections");
    const results = [];
    for (const entry of sources)
        results.push(listingItem(entry, "source", "list_sources"));
    for (const entry of collections)
        results.push(listingItem(entry, "collection", "list_collections"));
    return { results, sources, collections };
}
function listedEntries(raw, key, tool) {
    const record = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? raw : null;
    const value = record === null ? undefined : record[key];
    if (!Array.isArray(value))
        fail(`${tool} response is missing the '${key}' array`);
    const entries = [];
    for (const entry of value) {
        if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
            fail(`${tool} ${key} entry is not an object`);
        }
        entries.push(entry);
    }
    return entries;
}
function listingItem(entry, kind, tool) {
    const name = optionalString(entry.name);
    if (name === null)
        fail(`${tool} entry is missing a 'name'`);
    return {
        ...entry,
        file_path: optionalString(entry.file_path) ?? name,
        symbol_name: optionalString(entry.symbol_name) ?? name,
        symbol_type: kind,
        snippet: JSON.stringify(entry),
    };
}
export function capabilityError(server, tool, caps) {
    if (GRAPH_TOOLS.has(tool) && !caps.graph) {
        return { kind: "capability", server, tool, message: `no knowledge graph for server ${server}` };
    }
    if (CHAT_TOOLS.has(tool) && !caps.chat) {
        return { kind: "capability", server, tool, message: `no chat capability for server ${server}` };
    }
    return null;
}
export function normalizeResults(server, tool, source, raw, roots) {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
        fail(`${tool} response must be a JSON object`);
    }
    const record = raw;
    const meta = {};
    for (const key of Object.keys(record)) {
        if (key.startsWith("total_") || META_KEYS.has(key))
            meta[key] = record[key];
    }
    if (roots === null)
        meta.hint = "path_roots not configured; set path_roots_file to resolve local_path";
    const rawItems = locateItems(record, tool);
    const items = rawItems.map((entry, index) => normalizeItem(server, tool, source, entry, roots, index));
    return { server, tool, source, snapshot: true, items, meta };
}
function locateItems(record, tool) {
    // rag_symbol unique hit: a flat symbol object rather than a wrapper.
    if (typeof record.file_path === "string" && record.file_path.length > 0) {
        return [record];
    }
    for (const key of ITEM_ARRAY_KEYS) {
        const value = record[key];
        if (Array.isArray(value))
            return value;
    }
    if (Array.isArray(record.affected_files))
        return record.affected_files;
    if (Array.isArray(record.candidates))
        return record.candidates;
    fail(`${tool} response has no recognized result array (documents/results/symbols/items/affected_files)`);
}
function normalizeItem(server, tool, source, entry, roots, index) {
    // rag_impact affected_files entries are bare path strings.
    if (typeof entry === "string") {
        const filePath = entry.trim();
        if (filePath.length === 0)
            fail(`${tool} result[${index}] is an empty file path`);
        return buildItem(server, source, filePath, null, null, null, roots);
    }
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
        fail(`${tool} result[${index}] is not an object`);
    }
    const item = entry;
    const filePath = optionalString(item.file_path) ?? optionalString(item.file) ?? optionalString(item.path);
    if (filePath === null) {
        fail(`${tool} result[${index}] is missing file_path`);
    }
    return buildItem(server, source, filePath, optionalNumber(item.line_start), optionalString(item.symbol_name) ?? optionalString(item.name), optionalString(item.qualified_name), roots, {
        symbolType: optionalString(item.symbol_type) ?? optionalString(item.kind),
        snippet: optionalString(item.content) ?? optionalString(item.snippet),
        score: optionalNumber(item.score),
        lineEnd: optionalNumber(item.line_end),
    });
}
function buildItem(server, source, filePath, lineStart, symbolName, qualifiedName, roots, extras) {
    const resolved = resolveLocalPath(filePath, roots);
    const citation = source === null || lineStart === null ? null : formatCitation({ server, source, filePath, line: lineStart });
    return {
        symbol_name: symbolName ?? "",
        qualified_name: qualifiedName,
        symbol_type: extras?.symbolType ?? null,
        file_path: filePath,
        line_start: lineStart,
        line_end: extras?.lineEnd ?? null,
        snippet: extras?.snippet ?? null,
        score: extras?.score ?? null,
        citation,
        local_path: resolved.localPath,
        exists: resolved.exists,
        line_hint: lineStart,
        snapshot_warning: true,
    };
}
//# sourceMappingURL=adapter.js.map