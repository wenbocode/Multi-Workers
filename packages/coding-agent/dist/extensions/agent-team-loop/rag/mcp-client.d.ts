/**
 * mcp-client.ts — JSON-RPC 2.0 over HTTP POST for overcode-rag (mw-rag-integration T-03).
 *
 * Transport only: no config loading, no writes, no retries. The caller owns
 * budgets/budgets/heartbeats; this module answers one question — did the request
 * reach the server and come back, and if not, **why** (D-005 error taxonomy).
 *
 * The taxonomy is the load-bearing part: `connect` is the only kind that proves
 * the request was NOT delivered (ECONNREFUSED / reset / DNS), which is what
 * licenses the cli fallback for read-only tools. `timeout` (including "delivered
 * but the response was lost") must never be folded into `connect`.
 */
import type { RagErrorKind } from "./adapter.ts";
export type { RagErrorKind };
/** Mirrors the overcode-rag handshake spike (mcp-config.json). */
export declare const MCP_PROTOCOL_VERSION = "2025-03-26";
/** Conservative default when the caller does not pass an initialize budget. */
export declare const DEFAULT_MCP_INIT_TIMEOUT_MS = 15000;
export interface RagToolErrorInit {
    kind: RagErrorKind;
    server: string;
    tool: string;
    message: string;
    detail?: unknown;
}
/**
 * `server` is whatever identifier the session was constructed with; with only
 * `(baseUrl, tokenEnv)` available it is the base URL, and callers that know the
 * configured server name may re-tag it.
 */
export declare class RagToolError extends Error {
    kind: RagErrorKind;
    server: string;
    tool: string;
    detail?: unknown;
    constructor(init: RagToolErrorInit);
}
export interface McpCallOptions {
    timeoutMs: number;
    signal: AbortSignal;
    onUpdate?: (message: string) => void;
}
export declare class McpSession {
    private readonly baseUrl;
    private readonly tokenEnv;
    private sessionId;
    private nextRequestId;
    constructor(baseUrl: string, tokenEnv: string | null);
    /** Handshake: capture `Mcp-Session-Id` from the response header. */
    initialize(timeoutMs?: number): Promise<void>;
    /** `tools/call`; returns the tool payload (MCP `content[0].text` JSON is unwrapped). */
    callTool(name: string, args: unknown, opts: McpCallOptions): Promise<unknown>;
    private buildRequest;
    private send;
    private parseEnvelope;
    private tokenValue;
    private redact;
    private redactDetail;
    private unwrapToolResult;
    private buildError;
}
//# sourceMappingURL=mcp-client.d.ts.map