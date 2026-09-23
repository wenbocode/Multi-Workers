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
import * as path from "node:path";
import { Type } from "typebox";
import { activeToolsForType } from "../worker/worker-mode.js";
import { capabilityError, loadPathRoots, mergeToolResponses, normalizeResults, ragToolCalls, } from "./adapter.js";
import { RAG_HEARTBEAT_INTERVAL_MS, withHeartbeat } from "./budget.js";
import { callCli } from "./cli-bridge.js";
import { loadRagConfig, RagConfigError, resolveDefaults, rewriteDefaults, } from "./config.js";
import { appendEvidence, ragBudgetExceededLine, ragCallLine, ragFallbackLine, ragRewriteDegradedLine, ragUnavailableLine, redactSecrets, } from "./evidence.js";
import { RAG_PROMPT_GUIDELINES } from "./guidelines.js";
import { McpSession, RagToolError } from "./mcp-client.js";
/** Per-server probe budget at activation (design D-002, VC-009). */
export const RAG_PROBE_TIMEOUT_MS = 5_000;
/** task.md header names for the per-task RAG budgets (D-006, T-04). */
export const RAG_CHAT_BUDGET_HEADER = "rag_chat_budget:";
export const RAG_TIME_BUDGET_HEADER = "rag_time_budget_s:";
/** The six always-visible RAG tools (AC-004). `rag_chat` is added below. */
export const RAG_BASE_TOOL_NAMES = [
    "rag_search",
    "rag_symbol",
    "rag_graph",
    "rag_impact",
    "rag_sources",
    "rag_feedback",
];
/** The single `rag-research`-only tool (AC-011 / VC-015). */
export const RAG_CHAT_TOOL_NAME = "rag_chat";
/**
 * Minimum per-call transport budget for `rag_chat` (mw-rag-integration T-09).
 * The reference service observed 41s-9min on chat, so the 180s default
 * `mcp.timeout_ms` (T-05) would cut healthy long answers off. Retrieval tools
 * keep the configured value; `rag/config.ts`'s schema is a locked cross-
 * language contract (T-12), so this is a constant, not a new field.
 */
export const RAG_CHAT_TIMEOUT_MS = 600_000;
/**
 * Per-call transport timeout for one logical RAG tool: `rag_chat` takes
 * `max(config.mcp.timeoutMs, RAG_CHAT_TIMEOUT_MS)` so an explicit larger
 * configuration always wins; every retrieval tool keeps the configured value.
 * Exported for the T-09 timeout-contract test.
 */
export function ragCallTimeoutMs(logicalTool, config) {
    return logicalTool === RAG_CHAT_TOOL_NAME ? Math.max(config.timeoutMs, RAG_CHAT_TIMEOUT_MS) : config.timeoutMs;
}
function failResult(error) {
    return { content: [{ type: "text", text: JSON.stringify(error) }], details: error };
}
function okResult(envelope) {
    return { content: [{ type: "text", text: JSON.stringify(envelope) }], details: envelope };
}
/** Closed `server` enum over the project's enabled set. */
function serverEnum(enabled) {
    const literals = enabled.map((name) => Type.Literal(name));
    if (literals.length === 1) {
        const only = literals[0];
        if (only !== undefined)
            return only;
    }
    return Type.Union(literals);
}
/**
 * Load the project config and register the RAG surface. Returns null (and
 * registers/probes nothing) when no server is enabled — the structural
 * zero-impact path. Throws `RagConfigError` for an unusable config; callers
 * fail closed.
 */
export function registerRagTools(pi, controlRoot, hooks = {}) {
    const config = loadRagConfig(controlRoot);
    if (config.enabled.length === 0)
        return null;
    const runtime = {
        config,
        controlRoot,
        workerTaskDir: hooks.workerTaskDir ?? null,
        reachable: new Map(),
        sessions: new Map(),
        breaker: hooks.breaker ?? null,
        budget: hooks.budget ?? null,
        ready: Promise.resolve(),
        chatRegistered: false,
        role: hooks.role ?? "",
        phase: hooks.phase ?? "",
    };
    runtime.ready = probeAndRegister(pi, runtime);
    return runtime;
}
async function probeAndRegister(pi, runtime) {
    await Promise.all(runtime.config.enabled.map(async (server) => {
        const entry = runtime.config.servers[server];
        if (entry === undefined || entry.mcp === null) {
            runtime.reachable.set(server, true);
            return;
        }
        try {
            const session = new McpSession(entry.mcp.url, entry.mcp.tokenEnv);
            await session.initialize(RAG_PROBE_TIMEOUT_MS);
            runtime.sessions.set(server, session);
            runtime.reachable.set(server, true);
        }
        catch {
            runtime.reachable.set(server, false);
        }
    }));
    registerBaseTools(pi, runtime);
}
/** Tool description suffix while any enabled server failed the activate probe. */
function withReachability(runtime, description) {
    const anyUnreachable = runtime.config.enabled.some((server) => runtime.reachable.get(server) === false);
    return anyUnreachable ? `${description} [unreachable at session start]` : description;
}
function registerBaseTools(pi, runtime) {
    const enumSchema = serverEnum(runtime.config.enabled);
    pi.registerTool({
        name: "rag_search",
        label: "RAG search",
        description: withReachability(runtime, "Semantic/keyword search across the configured RAG sources. Returns normalized items with citation and local_path verification state."),
        promptGuidelines: RAG_PROMPT_GUIDELINES,
        parameters: Type.Object({
            query: Type.String({ description: "Natural-language or keyword query." }),
            server: Type.Optional(enumSchema),
            source: Type.Optional(Type.String({ description: "Restrict the search to one source (e.g. docs, code)." })),
            collection: Type.Optional(Type.String({ description: "Restrict the search to one collection." })),
            top_k: Type.Optional(Type.Number({ description: "Maximum number of hits to return." })),
            multi_rounds: Type.Optional(Type.Boolean({ description: "Allow the server to run multiple recall rounds." })),
            auto_rewrite: Type.Optional(Type.Boolean({ description: "Allow query rewriting before recall." })),
        }),
        execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_search", params, signal, wrapOnUpdate(onUpdate)),
    });
    pi.registerTool({
        name: "rag_symbol",
        label: "RAG symbol",
        description: withReachability(runtime, "Locate a symbol by name and return its definition plus caller/callee summary with citations."),
        promptGuidelines: RAG_PROMPT_GUIDELINES,
        parameters: Type.Object({
            symbol_name: Type.String({ description: "Symbol name to resolve (function, class, type)." }),
            server: Type.Optional(enumSchema),
            source: Type.Optional(Type.String({ description: "Restrict the lookup to one source." })),
        }),
        execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_symbol", params, signal, wrapOnUpdate(onUpdate)),
    });
    pi.registerTool({
        name: "rag_graph",
        label: "RAG graph",
        description: withReachability(runtime, "Walk the static knowledge graph: callers, callees, inheritance or a subgraph around a symbol."),
        promptGuidelines: RAG_PROMPT_GUIDELINES,
        parameters: Type.Object({
            operation: Type.Union([
                Type.Literal("callers"),
                Type.Literal("callees"),
                Type.Literal("inheritance"),
                Type.Literal("subgraph"),
            ]),
            symbol_name: Type.String({ description: "Symbol the graph walk is anchored on." }),
            server: Type.Optional(enumSchema),
            source: Type.Optional(Type.String({ description: "Restrict the walk to one source." })),
            depth: Type.Optional(Type.Number({ minimum: 1, maximum: 10, description: "Traversal depth (1..10)." })),
            limit: Type.Optional(Type.Number({ description: "Maximum number of edges to return." })),
        }),
        execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_graph", params, signal, wrapOnUpdate(onUpdate)),
    });
    pi.registerTool({
        name: "rag_impact",
        label: "RAG impact",
        description: withReachability(runtime, "Estimate the change impact of a symbol: total callers, affected files and callers grouped by hop."),
        promptGuidelines: RAG_PROMPT_GUIDELINES,
        parameters: Type.Object({
            symbol: Type.String({ description: "Symbol whose change impact is measured." }),
            server: Type.Optional(enumSchema),
            source: Type.Optional(Type.String({ description: "Restrict the analysis to one source." })),
            depth: Type.Optional(Type.Number({ minimum: 1, maximum: 10, description: "Traversal depth (1..10)." })),
        }),
        execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_impact", params, signal, wrapOnUpdate(onUpdate)),
    });
    pi.registerTool({
        name: "rag_sources",
        label: "RAG sources",
        description: withReachability(runtime, "List the RAG sources and their collections for one server."),
        promptGuidelines: RAG_PROMPT_GUIDELINES,
        parameters: Type.Object({
            server: Type.Optional(enumSchema),
        }),
        execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_sources", params, signal, wrapOnUpdate(onUpdate)),
    });
    pi.registerTool({
        name: "rag_feedback",
        label: "RAG feedback",
        description: withReachability(runtime, "Report a mismatch between an expected and an actual RAG result back to the server (write operation, never auto-retried)."),
        promptGuidelines: RAG_PROMPT_GUIDELINES,
        parameters: Type.Object({
            title: Type.String({ description: "Short feedback title." }),
            tool: Type.String({ description: "Tool the feedback is about." }),
            expected: Type.String({ description: "What the caller expected." }),
            actual: Type.String({ description: "What the tool actually returned." }),
            scenario: Type.Optional(Type.String({ description: "Optional scenario/context." })),
            detail: Type.Optional(Type.String({ description: "Optional free-form detail." })),
            server: Type.Optional(enumSchema),
        }),
        execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_feedback", params, signal, wrapOnUpdate(onUpdate)),
    });
}
/** Register the research-only tool exactly once (idempotent). */
function ensureRagChatTool(pi, runtime) {
    if (runtime.chatRegistered)
        return;
    runtime.chatRegistered = true;
    const enumSchema = serverEnum(runtime.config.enabled);
    pi.registerTool({
        name: RAG_CHAT_TOOL_NAME,
        label: "RAG chat",
        description: withReachability(runtime, "Ask the RAG server to synthesize an answer from its sources (lead only; expensive, never auto-retried)."),
        promptGuidelines: RAG_PROMPT_GUIDELINES,
        parameters: Type.Object({
            query: Type.String({ description: "Question for the RAG server to answer from its sources." }),
            server: Type.Optional(enumSchema),
            source: Type.Optional(Type.String({ description: "Restrict the answer to one source." })),
            top_k: Type.Optional(Type.Number({ description: "Maximum number of supporting hits." })),
            max_recall_rounds: Type.Optional(Type.Number({ description: "Maximum recall rounds." })),
        }),
        execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, RAG_CHAT_TOOL_NAME, params, signal, wrapOnUpdate(onUpdate)),
    });
}
/** Tool names the given task type may activate out of the RAG surface. */
export function ragToolNamesForType(rt, type) {
    const names = [...RAG_BASE_TOOL_NAMES];
    if (rt.config.enabled.length > 0 && type === "rag-research")
        names.push(RAG_CHAT_TOOL_NAME);
    return names;
}
/**
 * Idempotently set the active tool set for one agent run: the full base set
 * for the type plus its RAG subset. `before_agent_start` fires on every run
 * (including phase/follow-up turns), so this recomputes the complete expected
 * set each time and never accumulates duplicates. A null runtime (RAG
 * disabled) reproduces the pre-RAG behavior byte for byte.
 */
export function applyRagTools(pi, rt, type) {
    if (rt === null) {
        pi.setActiveTools(activeToolsForType(type));
        return;
    }
    if (type === "rag-research")
        ensureRagChatTool(pi, rt);
    pi.setActiveTools([...new Set([...activeToolsForType(type), ...ragToolNamesForType(rt, type)])]);
}
/**
 * RAG dispatch pre-check (VC-003): load the merged config and reject an
 * unusable one (e.g. `enabled` naming an undefined server) before any task.md
 * is created. The returned message carries the server name and the visible
 * server list.
 */
export function validateRagEnabled(projectDir) {
    try {
        loadRagConfig(projectDir);
        return { ok: true };
    }
    catch (error) {
        if (error instanceof RagConfigError) {
            return { ok: false, message: `RAG config rejected dispatch (${error.kind}): ${error.message}` };
        }
        throw error;
    }
}
function wrapOnUpdate(onUpdate) {
    if (onUpdate === undefined)
        return undefined;
    return (message) => onUpdate({ content: [{ type: "text", text: message }], details: undefined });
}
/** The shared capability -> budget -> transport -> normalize chain. */
async function callRag(runtime, tool, params, signal, onUpdate) {
    const tokenEnvNames = ragTokenEnvNames(runtime.config);
    // T-15 / D-102 / D-109: role/phase defaults resolve through the single
    // `resolveDefaults` (declared values: role > phase > default_server). An
    // empty axis (PM session, unregistered role/phase) falls back to
    // `default_server` / null / false (D-103), so the request keeps the
    // pre-T-15 shape.
    const defaults = resolveDefaults(runtime.config, runtime.role, runtime.phase);
    const requested = typeof params.server === "string" && params.server.length > 0 ? params.server : undefined;
    const server = requested ?? defaults.server;
    if (server === null) {
        return failResult({
            kind: "tool",
            server: "",
            tool,
            message: `no RAG server selected for ${tool} and no default_server configured`,
        });
    }
    const entry = runtime.config.servers[server];
    if (entry === undefined) {
        return failResult({ kind: "tool", server, tool, message: `unknown rag server '${server}'` });
    }
    // Evidence is appended once per logical call, redacted with the configured
    // token env names; a null workerTaskDir (PM session) writes nothing.
    const taskDir = runtime.workerTaskDir;
    const evidence = (line) => {
        if (taskDir !== null)
            appendEvidence(taskDir, redactSecrets(line, tokenEnvNames));
    };
    if (runtime.breaker?.isOpen(server)) {
        evidence(ragUnavailableLine({ server, tool, kind: "circuit", ms: 0 }));
        return failResult({ kind: "circuit", server, tool, message: `circuit open for rag server '${server}'` });
    }
    const capability = capabilityError(server, tool, entry.capabilities);
    if (capability !== null)
        return failResult(capability);
    const isChat = tool === RAG_CHAT_TOOL_NAME;
    const budget = runtime.budget;
    if (budget !== null) {
        // Cumulative RAG time and the wall guard are refused before the network;
        // the reservation (chat count) is synchronous so concurrent calls cannot
        // both take the last slot.
        const cumulative = budget.checkCumulative();
        if (!cumulative.ok) {
            const state = budget.state();
            evidence(ragBudgetExceededLine({
                server,
                tool,
                reason: "cumulative",
                used: state.timeUsedMs,
                budget: state.timeBudgetMs,
            }));
            return failResult({ kind: "budget", server, tool, message: cumulative.message });
        }
        if (isChat) {
            const wall = budget.checkWall(Date.now());
            if (!wall.ok) {
                evidence(ragBudgetExceededLine({
                    server,
                    tool,
                    reason: "wall",
                    used: Math.max(0, Date.now() - budget.startedAt),
                    budget: budget.taskWallMs ?? 0,
                }));
                return failResult({ kind: "budget", server, tool, message: wall.message });
            }
            const reserved = budget.reserveChat();
            if (!reserved.ok) {
                const state = budget.state();
                evidence(ragBudgetExceededLine({
                    server,
                    tool,
                    reason: "count",
                    used: state.chatUsed,
                    budget: state.chatBudget,
                }));
                return failResult({ kind: "budget", server, tool, message: reserved.message });
            }
        }
    }
    const args = {};
    for (const [key, value] of Object.entries(params)) {
        if (key !== "server" && value !== undefined)
            args[key] = value;
    }
    // D-102: explicit `source` > role > phase. The resolved value is injected
    // only when the agent did not pass one, so an unconfigured session keeps
    // the request unchanged.
    const explicitSource = typeof params.source === "string" && params.source.length > 0 ? params.source : undefined;
    const source = explicitSource ?? defaults.source;
    if (explicitSource === undefined && source !== null)
        args.source = source;
    // AC-101/D-102: a role/phase rewrite default only decides the wire tool for
    // `rag_search`, and only when the agent left both switches open (an explicit
    // `multi_rounds`/`auto_rewrite` always wins). `rewriteDefaults`'s `explicit`
    // slot carries the config-level role/phase `rewrite:` override so the wire
    // selection matches `renderRagBlock`'s `[mw] Rewrite:` line.
    if (tool === "rag_search" && args.multi_rounds === undefined && args.auto_rewrite === undefined) {
        const explicitRewrite = runtime.config.roles[runtime.role]?.rewrite ?? runtime.config.phases[runtime.phase]?.rewrite;
        if (rewriteDefaults(runtime.role, runtime.phase, entry.capabilities.rewrite, explicitRewrite)) {
            args.multi_rounds = true;
        }
    }
    const startedAt = Date.now();
    try {
        // One logical call = one budget/breaker/heartbeat (T-05): `rag_sources`
        // fans out to two HTTP calls but counts as a single tool invocation, and
        // the 30s heartbeat covers the whole fan-out.
        const calls = ragToolCalls(tool, args);
        const outcomes = await withHeartbeat(RAG_HEARTBEAT_INTERVAL_MS, onUpdate, async () => {
            const legs = [];
            for (const call of calls) {
                legs.push(await transport(runtime, server, entry, tool, call.name, call.args, signal, onUpdate));
            }
            return legs;
        });
        const roots = loadPathRoots(resolvePathRootsFile(runtime.controlRoot, entry));
        const envelope = normalizeResults(server, tool, source, mergeToolResponses(tool, outcomes.map((leg) => leg.response)), roots);
        envelope.mcp_tool = calls.map((call) => call.name).join("+");
        const elapsed = Date.now() - startedAt;
        runtime.budget?.accumulate(elapsed);
        if (isChat)
            runtime.budget?.settleChat(true, null);
        runtime.breaker?.noteSuccess(server);
        if (outcomes.some((leg) => leg.fallback)) {
            evidence(ragFallbackLine({ server, tool, reason: "connect" }));
        }
        if (envelope.meta.rewrite_degraded === true)
            evidence(ragRewriteDegradedLine({ server, tool }));
        evidence(ragCallLine({
            server,
            tool,
            via: outcomes.some((leg) => leg.via === "cli") ? "cli" : "mcp",
            ms: elapsed,
            results: evidenceResults(envelope),
            mcpTool: envelope.mcp_tool ?? null,
        }));
        return okResult(envelope);
    }
    catch (error) {
        const elapsed = Date.now() - startedAt;
        const tagged = retag(error, server, tool);
        runtime.budget?.accumulate(elapsed);
        runtime.breaker?.noteFailure(server, tagged.kind);
        if (isChat)
            runtime.budget?.settleChat(false, tagged.kind);
        evidence(ragUnavailableLine({ server, tool, kind: tagged.kind, ms: elapsed }));
        return failResult(redactToolError(tagged, tokenEnvNames));
    }
}
/** Every configured `token_env` name, deduplicated, for evidence/error redaction. */
function ragTokenEnvNames(config) {
    const names = new Set();
    for (const entry of Object.values(config.servers)) {
        const name = entry.mcp?.tokenEnv;
        if (name !== undefined && name !== null && name.length > 0)
            names.add(name);
    }
    return [...names];
}
/**
 * `results` semantics (T-05): list tools = `items.length`; `rag_impact` =
 * `meta.affected_files.length`; `rag_feedback` = 0 (no list payload).
 */
function evidenceResults(envelope) {
    if (envelope.tool === "rag_feedback")
        return 0;
    const affected = envelope.meta.affected_files;
    if (envelope.tool === "rag_impact" && Array.isArray(affected))
        return affected.length;
    return envelope.items.length;
}
/** Re-run redaction over the tool-facing error so no token env value can leak. */
function redactToolError(error, tokenEnvNames) {
    const message = redactSecrets(error.message, tokenEnvNames);
    return { ...error, message, detail: redactDetail(error.detail, tokenEnvNames) };
}
function redactDetail(detail, tokenEnvNames) {
    if (detail === undefined)
        return undefined;
    try {
        return JSON.parse(redactSecrets(JSON.stringify(detail), tokenEnvNames));
    }
    catch {
        return redactSecrets(String(detail), tokenEnvNames);
    }
}
/** path_roots_file is project-root relative (design D-007/T-12 anchor). */
function resolvePathRootsFile(controlRoot, entry) {
    if (entry.pathRootsFile === null || entry.pathRootsFile.length === 0)
        return null;
    return path.resolve(controlRoot, entry.pathRootsFile);
}
async function transport(runtime, server, entry, logicalTool, mcpTool, args, signal, onUpdate) {
    const canMcp = (entry.transport === "mcp" || entry.transport === "both") && entry.mcp !== null;
    const canCli = (entry.transport === "skill" || entry.transport === "both") && entry.skill !== null;
    const readOnly = logicalTool !== "rag_feedback" && logicalTool !== RAG_CHAT_TOOL_NAME;
    if (canMcp) {
        try {
            return {
                response: await mcpCall(runtime, server, entry, mcpTool, args, signal, onUpdate, logicalTool),
                via: "mcp",
                fallback: false,
            };
        }
        catch (error) {
            const kind = error instanceof RagToolError ? error.kind : "protocol";
            // Fallback only for a provably-undelivered connect on a read-only tool (D-005).
            if (!(canCli && kind === "connect" && readOnly))
                throw error;
            return {
                response: await cliCall(runtime, entry, logicalTool, args, signal, onUpdate),
                via: "cli",
                fallback: true,
            };
        }
    }
    if (canCli) {
        return {
            response: await cliCall(runtime, entry, logicalTool, args, signal, onUpdate),
            via: "cli",
            fallback: false,
        };
    }
    throw new RagToolError({
        kind: "tool",
        server,
        tool: logicalTool,
        message: `rag server '${server}' has no usable transport`,
    });
}
async function mcpCall(runtime, server, entry, tool, args, signal, onUpdate, logicalTool) {
    const mcp = entry.mcp;
    if (mcp === null)
        throw new RagToolError({ kind: "tool", server, tool, message: "mcp is not configured" });
    let session = runtime.sessions.get(server);
    if (session === undefined) {
        session = new McpSession(mcp.url, mcp.tokenEnv);
        await session.initialize(mcp.timeoutMs);
        runtime.sessions.set(server, session);
    }
    return await session.callTool(tool, args, {
        // rag_chat gets the 600s floor (T-09); every other logical tool keeps
        // the configured mcp.timeout_ms. `tool` here is the wire name, so the
        // decision keys off the logical name the agent invoked.
        timeoutMs: ragCallTimeoutMs(logicalTool, mcp),
        signal: signal ?? new AbortController().signal,
        onUpdate,
    });
}
/**
 * Resolve the skill transport working directory (D-302): an explicit
 * `skill.dir` resolves against the control workspace root (absolute values are
 * returned unchanged by `path.resolve`), while a missing/`null` `dir` means
 * the control workspace root itself. Pure, so it is unit-testable without
 * spawning the CLI.
 */
export function resolveCliDir(controlRoot, dir) {
    return dir === null ? controlRoot : path.resolve(controlRoot, dir);
}
async function cliCall(runtime, entry, tool, args, signal, onUpdate) {
    const skill = entry.skill;
    if (skill === null)
        throw new Error(`rag server has no skill block for tool ${tool}`);
    const dir = resolveCliDir(runtime.controlRoot, skill.dir);
    return await callCli({ dir, cliEntry: skill.cliEntry, timeoutMs: skill.timeoutMs }, tool, args, {
        signal: signal ?? new AbortController().signal,
        env: process.env,
        onUpdate,
    });
}
/**
 * Re-tag a transport error with the configured server name: T-03 only knows
 * the base URL / cli entry and fills `server` with that, but evidence lines
 * and breaker keys must use the name from the project config.
 */
function retag(error, server, tool) {
    if (error instanceof RagToolError) {
        return { kind: error.kind, server, tool, message: error.message, detail: error.detail };
    }
    return {
        kind: "tool",
        server,
        tool,
        message: error instanceof Error ? error.message : String(error),
    };
}
//# sourceMappingURL=tools.js.map