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
export const MCP_PROTOCOL_VERSION = "2025-03-26";

/** Conservative default when the caller does not pass an initialize budget. */
export const DEFAULT_MCP_INIT_TIMEOUT_MS = 15_000;

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
export class RagToolError extends Error {
	kind: RagErrorKind;
	server: string;
	tool: string;
	detail?: unknown;

	constructor(init: RagToolErrorInit) {
		super(init.message);
		this.name = "RagToolError";
		this.kind = init.kind;
		this.server = init.server;
		this.tool = init.tool;
		this.detail = init.detail;
	}
}

export interface McpCallOptions {
	timeoutMs: number;
	signal: AbortSignal;
	onUpdate?: (message: string) => void;
}

interface JsonRpcRequest {
	jsonrpc: "2.0";
	id: number;
	method: string;
	params: Record<string, unknown>;
}

interface RawResponse {
	status: number;
	text: string;
	sessionId: string | null;
}

const CONNECT_ERROR_CODES = new Set([
	"ECONNREFUSED",
	"ECONNRESET",
	"ENOTFOUND",
	"EAI_AGAIN",
	"EHOSTUNREACH",
	"ENETUNREACH",
	"EPIPE",
	"ECONNABORTED",
	"UND_ERR_SOCKET",
	"UND_ERR_CONNECT_TIMEOUT",
]);

const CONNECT_ERROR_MESSAGES = ["socket hang up", "other side closed", "econnrefused", "econnreset", "getaddrinfo"];

export class McpSession {
	private readonly baseUrl: string;
	private readonly tokenEnv: string | null;
	private sessionId: string | null = null;
	private nextRequestId = 0;

	constructor(baseUrl: string, tokenEnv: string | null) {
		this.baseUrl = baseUrl;
		this.tokenEnv = tokenEnv;
	}

	/** Handshake: capture `Mcp-Session-Id` from the response header. */
	async initialize(timeoutMs: number = DEFAULT_MCP_INIT_TIMEOUT_MS): Promise<void> {
		const response = await this.send(
			this.buildRequest("initialize", {
				protocolVersion: MCP_PROTOCOL_VERSION,
				capabilities: {},
				clientInfo: { name: "mw-rag", version: "1.0.0" },
			}),
			timeoutMs,
			undefined,
			"initialize",
		);
		this.parseEnvelope(response, "initialize");

		if (response.sessionId === null || response.sessionId.length === 0) {
			throw this.buildError("protocol", "initialize", "initialize response is missing the Mcp-Session-Id header", {
				status: response.status,
			});
		}
		this.sessionId = response.sessionId;
	}

	/** `tools/call`; returns the tool payload (MCP `content[0].text` JSON is unwrapped). */
	async callTool(name: string, args: unknown, opts: McpCallOptions): Promise<unknown> {
		const response = await this.send(
			this.buildRequest("tools/call", { name, arguments: args ?? {} }),
			opts.timeoutMs,
			opts.signal,
			name,
		);
		const result = this.parseEnvelope(response, name);
		return this.unwrapToolResult(result, name);
	}

	private buildRequest(method: string, params: Record<string, unknown>): JsonRpcRequest {
		this.nextRequestId += 1;
		return { jsonrpc: "2.0", id: this.nextRequestId, method, params };
	}

	private async send(
		request: JsonRpcRequest,
		timeoutMs: number,
		externalSignal: AbortSignal | undefined,
		tool: string,
	): Promise<RawResponse> {
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), timeoutMs);
		const onExternalAbort = (): void => controller.abort();
		if (externalSignal !== undefined) {
			if (externalSignal.aborted) controller.abort();
			else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
		}

		try {
			const headers: Record<string, string> = {
				"Content-Type": "application/json",
				Accept: "application/json",
			};
			const token = this.tokenValue();
			if (token !== null) headers["X-MCP-Token"] = token;
			if (this.sessionId !== null) headers["Mcp-Session-Id"] = this.sessionId;

			const response = await fetch(this.baseUrl, {
				method: "POST",
				headers,
				body: JSON.stringify(request),
				signal: controller.signal,
			});
			const text = await response.text();
			return { status: response.status, text, sessionId: response.headers.get("mcp-session-id") };
		} catch (error) {
			if (controller.signal.aborted) {
				throw this.buildError("timeout", tool, `request timed out after ${timeoutMs}ms`, {
					method: request.method,
				});
			}
			throw this.buildError(classifyFetchFailure(error), tool, describeFetchFailure(error), {
				method: request.method,
			});
		} finally {
			clearTimeout(timer);
			if (externalSignal !== undefined) externalSignal.removeEventListener("abort", onExternalAbort);
		}
	}

	private parseEnvelope(response: RawResponse, tool: string): unknown {
		if (response.status === 401 || response.status === 403) {
			throw this.buildError("protocol", tool, `authentication rejected (HTTP ${response.status})`, {
				status: response.status,
				body: this.redact(snippet(response.text)),
			});
		}
		if (response.status < 200 || response.status >= 300) {
			throw this.buildError("protocol", tool, `unexpected HTTP status ${response.status}`, {
				status: response.status,
				body: this.redact(snippet(response.text)),
			});
		}

		let parsed: unknown;
		try {
			parsed = JSON.parse(response.text);
		} catch {
			throw this.buildError("protocol", tool, "response is not valid JSON", {
				body: this.redact(snippet(response.text)),
			});
		}
		if (!isRecord(parsed)) {
			throw this.buildError("protocol", tool, "JSON-RPC response is not an object", {
				body: this.redact(snippet(response.text)),
			});
		}

		const error = parsed.error;
		if (isRecord(error)) {
			const detail = this.redactDetail(error);
			throw this.buildError(
				"tool",
				tool,
				stringField(error, "message") ?? "server returned a JSON-RPC error",
				detail,
			);
		}
		if (!("result" in parsed)) {
			throw this.buildError("protocol", tool, "JSON-RPC response has neither result nor error", {
				body: this.redact(snippet(response.text)),
			});
		}
		return parsed.result;
	}

	private tokenValue(): string | null {
		if (this.tokenEnv === null) return null;
		const value = process.env[this.tokenEnv];
		return value !== undefined && value.length > 0 ? value : null;
	}

	private redact(text: string): string {
		const token = this.tokenValue();
		if (token === null) return text;
		return text.split(token).join("<redacted>");
	}

	private redactDetail(detail: unknown): unknown {
		if (detail === undefined) return undefined;
		const token = this.tokenValue();
		if (token === null) return detail;
		try {
			return JSON.parse(this.redact(JSON.stringify(detail)));
		} catch {
			return "<redacted>";
		}
	}

	private unwrapToolResult(result: unknown, tool: string): unknown {
		if (!isRecord(result)) return result;
		if (result.isError === true) {
			throw this.buildError("tool", tool, contentText(result) ?? "tool returned isError=true", result);
		}
		const text = contentText(result);
		if (text === null) return result;
		try {
			return JSON.parse(text);
		} catch {
			return result;
		}
	}

	private buildError(kind: RagErrorKind, tool: string, message: string, detail?: unknown): RagToolError {
		return new RagToolError({
			kind,
			server: this.baseUrl,
			tool,
			message: this.redact(message),
			detail: this.redactDetail(detail),
		});
	}
}

function contentText(result: Record<string, unknown>): string | null {
	const content = result.content;
	if (!Array.isArray(content)) return null;
	for (const entry of content) {
		if (isRecord(entry) && entry.type === "text" && typeof entry.text === "string") return entry.text;
	}
	return null;
}

function classifyFetchFailure(error: unknown): RagErrorKind {
	const codes = collectErrorCodes(error);
	for (const code of codes) {
		if (CONNECT_ERROR_CODES.has(code)) return "connect";
	}
	const messages = collectErrorMessages(error).join(" ").toLowerCase();
	for (const fragment of CONNECT_ERROR_MESSAGES) {
		if (messages.includes(fragment)) return "connect";
	}
	// Any failure before an HTTP status exists is a transport failure: no
	// application-level response was produced, so the request is not provably
	// processed.
	return "connect";
}

function describeFetchFailure(error: unknown): string {
	const messages = collectErrorMessages(error);
	if (messages.length > 0) return `request failed: ${messages.join("; ")}`;
	return "request failed before an HTTP response was received";
}

function collectErrorCodes(error: unknown): string[] {
	const codes: string[] = [];
	visitErrors(error, (record) => {
		if (typeof record.code === "string") codes.push(record.code);
	});
	return codes;
}

function collectErrorMessages(error: unknown): string[] {
	const messages: string[] = [];
	visitErrors(error, (record) => {
		if (typeof record.message === "string" && record.message.length > 0) messages.push(record.message);
	});
	return messages;
}

function visitErrors(value: unknown, visit: (record: Record<string, unknown>) => void): void {
	const seen = new Set<unknown>();
	const walk = (current: unknown, depth: number): void => {
		if (depth > 5 || !isRecord(current) || seen.has(current)) return;
		seen.add(current);
		visit(current);
		if (Array.isArray(current.errors)) for (const entry of current.errors) walk(entry, depth + 1);
		walk(current.cause, depth + 1);
	};
	walk(value, 0);
}

function stringField(record: Record<string, unknown>, key: string): string | null {
	const value = record[key];
	return typeof value === "string" ? value : null;
}

function snippet(text: string): string {
	return text.length > 300 ? text.slice(0, 300) : text;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}
