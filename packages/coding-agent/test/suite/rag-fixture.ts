/**
 * rag-fixture.ts — scripted MCP server for mw-rag-integration transport tests (T-03).
 *
 * Speaks the overcode-rag streamable-HTTP subset: `POST /mcp/`, JSON-RPC 2.0,
 * `initialize` returns the session id in the `Mcp-Session-Id` **response header**
 * and every later request must carry it (missing -> HTTP 400). No SSE.
 *
 * The fixture is intentionally dependency-free (`node:http` only) and records
 * every delivered request so tests can assert "zero requests were sent" for the
 * capability/budget/broker paths (VC-005/010/012).
 */

import { randomUUID } from "node:crypto";
import { once } from "node:events";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export type RagToolHandler = (args: Record<string, unknown>, call: number) => unknown | Promise<unknown>;

export interface RagFixtureOptions {
	/** Scripted per-tool results; `call` is the 1-based invocation count for that tool. */
	tools?: Record<string, RagToolHandler>;
	/** Response delay in ms for every request (simulates a slow call). */
	delayMs?: number;
	/** Receive the request but never respond (simulates "delivered, response lost"). Applies after `initialize`. */
	dropAfterDelivery?: boolean;
	/** Expected `X-MCP-Token`; a mismatch answers HTTP 401. When undefined the header is not checked. */
	token?: string;
	/** Inject `rewrite_degraded: true` into `rag_search` results (VC-021). */
	rewriteDegraded?: boolean;
}

export interface RagFixtureCall {
	method: string;
	name: string | null;
	args: Record<string, unknown>;
	/** `Mcp-Session-Id` carried by the request, or null (the initialize leg). */
	sessionId: string | null;
}

export interface RagFixture {
	url: string;
	port: number;
	calls: RagFixtureCall[];
	/** Force the next `n` requests to fail: `reset` destroys the socket, `500` answers HTTP 500. */
	failNext(n: number, mode?: "reset" | "500"): void;
	stop(): Promise<void>;
}

type FailMode = "reset" | "500";

const PROTOCOL_VERSION = "2025-03-26";

export async function startRagFixture(options: RagFixtureOptions = {}): Promise<RagFixture> {
	const calls: RagFixtureCall[] = [];
	const toolCallCounts = new Map<string, number>();
	const openResponses = new Set<ServerResponse>();
	let sessionId: string | null = null;
	let failuresRemaining = 0;
	let failureMode: FailMode = "reset";
	let stopped = false;

	const server: Server = createServer((request, response) => {
		void handle(request, response);
	});
	server.on("clientError", (_error, socket) => socket.destroy());

	async function handle(request: IncomingMessage, response: ServerResponse): Promise<void> {
		const rawBody = await readBody(request);
		const sessionHeader = headerValue(request, "mcp-session-id");

		let rpc: Record<string, unknown> | null = null;
		try {
			const parsed: unknown = JSON.parse(rawBody);
			if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
				rpc = parsed as Record<string, unknown>;
			}
		} catch {
			// handled below as HTTP 400
		}

		if (rpc !== null) {
			const params = isRecord(rpc.params) ? rpc.params : {};
			calls.push({
				method: typeof rpc.method === "string" ? rpc.method : "",
				name: typeof params.name === "string" ? params.name : null,
				args: isRecord(params.arguments) ? params.arguments : {},
				sessionId: sessionHeader,
			});
		}

		if (failuresRemaining > 0) {
			failuresRemaining -= 1;
			if (failureMode === "reset") {
				request.socket.destroy();
				return;
			}
			sendJson(response, 500, jsonRpcError(rpc, -32603, "fixture forced 500"));
			return;
		}

		if (options.token !== undefined && headerValue(request, "x-mcp-token") !== options.token) {
			sendJson(response, 401, jsonRpcError(rpc, -32001, "unauthorized"));
			return;
		}

		if (rpc === null) {
			sendJson(response, 400, { error: { code: -32700, message: "invalid JSON body" } });
			return;
		}

		const method = rpc.method;
		if (method === "initialize") {
			sessionId = randomUUID();
			sendJson(
				response,
				200,
				{
					jsonrpc: "2.0",
					id: rpc.id ?? null,
					result: {
						protocolVersion: PROTOCOL_VERSION,
						capabilities: { tools: {} },
						serverInfo: { name: "rag-fixture", version: "1.0.0" },
					},
				},
				{ "Mcp-Session-Id": sessionId },
			);
			return;
		}

		if (typeof method === "string" && method.startsWith("notifications/")) {
			response.writeHead(202).end();
			return;
		}

		if (sessionId === null || sessionHeader !== sessionId) {
			sendJson(response, 400, jsonRpcError(rpc, -32000, "Missing session ID"));
			return;
		}

		if (method === "tools/call") {
			const name =
				typeof rpc.params === "object" && rpc.params !== null ? (rpc.params as Record<string, unknown>).name : null;
			const toolName = typeof name === "string" ? name : "";
			const params = rpc.params as Record<string, unknown>;
			const args = isRecord(params.arguments) ? params.arguments : {};

			if (options.dropAfterDelivery) {
				trackOpenResponse(request, response);
				return;
			}

			const call = (toolCallCounts.get(toolName) ?? 0) + 1;
			toolCallCounts.set(toolName, call);

			if (options.delayMs !== undefined && options.delayMs > 0) {
				await sleep(options.delayMs);
				if (stopped || response.writableEnded) return;
			}

			let result: unknown;
			try {
				const handler = options.tools?.[toolName];
				result = handler ? await handler(args, call) : {};
			} catch (error) {
				sendJson(response, 200, jsonRpcError(rpc, -32000, String(error)));
				return;
			}

			if (
				options.rewriteDegraded &&
				toolName === "rag_search" &&
				isRecord(result) &&
				!("rewrite_degraded" in result)
			) {
				result = { ...result, rewrite_degraded: true };
			}

			sendJson(response, 200, { jsonrpc: "2.0", id: rpc.id ?? null, result });
			return;
		}

		sendJson(response, 200, jsonRpcError(rpc, -32601, `method not found: ${String(method)}`));
	}

	function trackOpenResponse(request: IncomingMessage, response: ServerResponse): void {
		openResponses.add(response);
		const forget = (): void => {
			openResponses.delete(response);
		};
		request.on("close", forget);
		response.on("close", forget);
	}

	async function readBody(request: IncomingMessage): Promise<string> {
		const chunks: Buffer[] = [];
		for await (const chunk of request) {
			chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
		}
		return Buffer.concat(chunks).toString("utf8");
	}

	function sendJson(
		response: ServerResponse,
		status: number,
		payload: unknown,
		extraHeaders: Record<string, string> = {},
	): void {
		if (response.writableEnded) return;
		response.writeHead(status, { "Content-Type": "application/json", ...extraHeaders });
		response.end(JSON.stringify(payload));
	}

	function jsonRpcError(rpc: Record<string, unknown> | null, code: number, message: string): unknown {
		return { jsonrpc: "2.0", id: rpc?.id ?? null, error: { code, message } };
	}

	server.listen(0, "127.0.0.1");
	await once(server, "listening");
	const address = server.address() as AddressInfo;

	const fixture: RagFixture = {
		url: `http://127.0.0.1:${address.port}/mcp/`,
		port: address.port,
		calls,
		failNext(n: number, mode: FailMode = "reset"): void {
			failuresRemaining = Math.max(0, Math.floor(n));
			failureMode = mode;
		},
		async stop(): Promise<void> {
			if (stopped) return;
			stopped = true;
			for (const response of openResponses) response.destroy();
			openResponses.clear();
			await new Promise<void>((resolve) => {
				server.close(() => resolve());
				server.closeAllConnections();
				server.closeIdleConnections();
			});
		},
	};
	return fixture;
}

/** Case-insensitive header lookup that tolerates a missing header value. */
export function headerValue(request: IncomingMessage, name: string): string | null {
	const value = request.headers[name];
	if (typeof value === "string") return value;
	if (Array.isArray(value) && value.length > 0) return value[0];
	return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}
