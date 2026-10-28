/**
 * rag-transport.test.ts — MCP session transport + cli bridge (mw-rag-integration T-03).
 *
 * VC-009: handshake establishes a real session and an unreachable port fails fast
 * as `connect` (< 2000ms), never waiting on a long timeout.
 *
 * Also pins the D-005 error taxonomy the T-05 fallback/breaker depends on:
 * `connect` (provably not delivered), `timeout` (including "delivered but the
 * response was lost"), `protocol`, `tool`.
 */

import { once } from "node:events";
import * as fs from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { callCli, resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";
import { McpSession, RagToolError } from "../../src/extensions/agent-team-loop/rag/mcp-client.ts";
import { type RagFixture, type RagFixtureOptions, startRagFixture } from "./rag-fixture.ts";

/**
 * The suite config sets `silent: "passed-only"`, which swallows console.log from
 * green tests. Write the machine-readable VERIFY evidence straight to stdout so
 * the required command surfaces it.
 */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

const fixtures: RagFixture[] = [];
const tempDirs: string[] = [];
const savedEnv = new Map<string, string | undefined>();

async function makeFixture(options?: RagFixtureOptions): Promise<RagFixture> {
	const fixture = await startRagFixture(options);
	fixtures.push(fixture);
	return fixture;
}

function setEnv(name: string, value: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	process.env[name] = value;
}

function makeTempDir(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rag-transport-"));
	tempDirs.push(dir);
	return dir;
}

async function unusedPort(): Promise<number> {
	const probe = createServer();
	probe.listen(0, "127.0.0.1");
	await once(probe, "listening");
	const port = (probe.address() as AddressInfo).port;
	await new Promise<void>((resolve) => probe.close(() => resolve()));
	return port;
}

async function expectTransportError(promise: Promise<unknown>): Promise<RagToolError> {
	try {
		await promise;
	} catch (error) {
		if (error instanceof RagToolError) return error;
		throw error;
	}
	throw new Error("expected a RagToolError, but the call resolved");
}

function makeSession(fixture: RagFixture, tokenEnv: string | null = null): McpSession {
	return new McpSession(fixture.url, tokenEnv);
}

afterEach(async () => {
	await Promise.all(fixtures.splice(0).map((fixture) => fixture.stop()));
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
});

describe("mcp session handshake (VC-009)", () => {
	it("initializes, carries the session id and returns scripted tool results", async () => {
		const fixture = await makeFixture({
			tools: {
				rag_search: (args) => ({
					documents: [{ file_path: "engine::src/App.cpp", line_start: 42 }],
					meta: { count: 1, query: args.query },
				}),
			},
		});
		const session = makeSession(fixture);

		await session.initialize(2_000);
		const result = await session.callTool(
			"rag_search",
			{ query: "renderer" },
			{ timeoutMs: 2_000, signal: new AbortController().signal },
		);

		expect(result).toEqual({
			documents: [{ file_path: "engine::src/App.cpp", line_start: 42 }],
			meta: { count: 1, query: "renderer" },
		});
		expect(fixture.calls).toHaveLength(2);
		expect(fixture.calls[0].method).toBe("initialize");
		expect(fixture.calls[0].sessionId).toBeNull();
		expect(fixture.calls[1].method).toBe("tools/call");
		expect(fixture.calls[1].name).toBe("rag_search");
		expect(fixture.calls[1].args).toEqual({ query: "renderer" });
		expect(typeof fixture.calls[1].sessionId).toBe("string");
		expect(fixture.calls[1].sessionId).not.toBe("");

		verify(`[VERIFY] VC-009: session_handshake=true session_id_present=true requests=${fixture.calls.length}`);
	});

	it("fails fast as connect against an unlistened port", async () => {
		const port = await unusedPort();
		const session = new McpSession(`http://127.0.0.1:${port}/mcp/`, null);

		const started = Date.now();
		const error = await expectTransportError(session.initialize(180_000));
		const elapsed = Date.now() - started;

		expect(error.kind).toBe("connect");
		expect(elapsed).toBeLessThan(2_000);
		verify(`[VERIFY] VC-009: error_kind=connect elapsed_lt_2000ms=true elapsed_ms=${elapsed}`);
	});

	it("classifies a mid-request socket reset as connect, not timeout", async () => {
		const fixture = await makeFixture({ tools: { rag_search: () => ({ ok: true }) } });
		const session = makeSession(fixture);
		await session.initialize(2_000);

		fixture.failNext(1, "reset");
		const error = await expectTransportError(
			session.callTool("rag_search", {}, { timeoutMs: 2_000, signal: new AbortController().signal }),
		);

		expect(error.kind).toBe("connect");
		verify("[VERIFY] VC-009: reset_kind=connect reset_not_timeout=true");
	});
});

describe("mcp error taxonomy", () => {
	it("classifies an abort on a slow response as timeout", async () => {
		const fixture = await makeFixture({
			delayMs: 400,
			tools: { rag_search: () => ({ documents: [] }) },
		});
		const session = makeSession(fixture);
		await session.initialize(5_000);

		const error = await expectTransportError(
			session.callTool("rag_search", {}, { timeoutMs: 120, signal: new AbortController().signal }),
		);

		expect(error.kind).toBe("timeout");
		verify(`[VERIFY] VC-009: slow_kind=${error.kind} throttled=true`);
	});

	it("classifies delivered-but-lost responses as timeout, never connect", async () => {
		const fixture = await makeFixture({
			dropAfterDelivery: true,
			tools: { rag_search: () => ({ documents: [] }) },
		});
		const session = makeSession(fixture);
		await session.initialize(2_000);

		const error = await expectTransportError(
			session.callTool("rag_search", {}, { timeoutMs: 150, signal: new AbortController().signal }),
		);

		expect(error.kind).toBe("timeout");
		expect(error.kind).not.toBe("connect");
		// The fixture received the tools/call: control flow proves the request was
		// delivered, which is exactly why fallback must not run for this kind.
		expect(fixture.calls).toHaveLength(2);
		expect(fixture.calls[1].method).toBe("tools/call");
		verify(`[VERIFY] VC-009: delivered_lost_kind=timeout delivered=true calls=${fixture.calls.length}`);
	});

	it("classifies HTTP 500 and a missing session header as protocol", async () => {
		const fixture = await makeFixture({ tools: { rag_search: () => ({ documents: [] }) } });
		const session = makeSession(fixture);
		await session.initialize(2_000);

		fixture.failNext(1, "500");
		const httpError = await expectTransportError(
			session.callTool("rag_search", {}, { timeoutMs: 2_000, signal: new AbortController().signal }),
		);
		expect(httpError.kind).toBe("protocol");

		const noSession = makeSession(fixture);
		const sessionError = await expectTransportError(
			noSession.callTool("rag_search", {}, { timeoutMs: 2_000, signal: new AbortController().signal }),
		);
		expect(sessionError.kind).toBe("protocol");

		verify(`[VERIFY] VC-009: http500_kind=${httpError.kind} missing_session_kind=${sessionError.kind}`);
	});

	it("classifies a JSON-RPC error object as tool", async () => {
		const fixture = await makeFixture({
			tools: {
				rag_search: () => {
					throw new Error("index not ready");
				},
			},
		});
		const session = makeSession(fixture);
		await session.initialize(2_000);

		const error = await expectTransportError(
			session.callTool("rag_search", {}, { timeoutMs: 2_000, signal: new AbortController().signal }),
		);

		expect(error.kind).toBe("tool");
		expect(error.message).toContain("index not ready");
		verify(`[VERIFY] VC-009: tool_error_kind=${error.kind}`);
	});

	it("reads the token from env only and redacts it from error messages", async () => {
		const fixture = await makeFixture({
			token: "SECRET123",
			tools: { rag_search: () => ({ documents: [] }) },
		});

		setEnv("OVERCODE_MCP_TOKEN", "SECRET123");
		const good = new McpSession(fixture.url, "OVERCODE_MCP_TOKEN");
		await good.initialize(2_000);
		await good.callTool("rag_search", {}, { timeoutMs: 2_000, signal: new AbortController().signal });

		setEnv("OVERCODE_MCP_TOKEN", "WRONGTOKEN999");
		const bad = new McpSession(fixture.url, "OVERCODE_MCP_TOKEN");
		const error = await expectTransportError(bad.initialize(2_000));

		expect(error.kind).toBe("protocol");
		expect(error.message).not.toContain("WRONGTOKEN999");
		expect(error.message).not.toContain("SECRET123");
		verify(`[VERIFY] VC-009: token_ok=true mismatch_kind=${error.kind} secret_hits=0`);
	});
});

describe("cli bridge (skill transport)", () => {
	const SCRIPT = `import json
import sys


def main():
    args = {}
    argv = sys.argv[2:]
    index = 0
    while index < len(argv):
        if argv[index] == "--arg" and index + 1 < len(argv):
            key, _, value = argv[index + 1].partition("=")
            args[key] = value
            index += 2
            continue
        index += 1
    exit_code = int(args.pop("exit_code", "0"))
    if exit_code != 0:
        sys.stderr.write("cli failure " + str(exit_code) + "\\n")
        return exit_code
    print(json.dumps({"tool": sys.argv[1], "args": args, "argv_count": len(sys.argv)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
`;

	async function makeCliEntry(): Promise<{ dir: string; cliEntry: string; timeoutMs: number }> {
		const dir = makeTempDir();
		const scriptPath = path.join(dir, "rag_cli.py");
		fs.writeFileSync(scriptPath, SCRIPT, "utf8");
		return { dir, cliEntry: scriptPath, timeoutMs: 20_000 };
	}

	it("spawns without a shell and keeps spaced arguments intact", async () => {
		const entry = await makeCliEntry();
		const result = await callCli(
			entry,
			"rag_search",
			{ query: "a b & c" },
			{ signal: new AbortController().signal, env: process.env },
		);

		expect(result).toEqual({
			tool: "rag_search",
			args: { query: "a b & c" },
			argv_count: 4,
		});
		verify("[VERIFY] VC-009: cli_argv_intact=true shell_used=false");
	});

	it("maps exit codes 0/2/3 to success/connect/tool", async () => {
		const entry = await makeCliEntry();
		const options = { signal: new AbortController().signal, env: process.env };

		const connect = await expectTransportError(callCli(entry, "rag_search", { exit_code: 2 }, options));
		expect(connect.kind).toBe("connect");

		const tool = await expectTransportError(callCli(entry, "rag_search", { exit_code: 3 }, options));
		expect(tool.kind).toBe("tool");

		verify(`[VERIFY] VC-009: cli_exit2=${connect.kind} cli_exit3=${tool.kind}`);
	});

	it("resolves the python interpreter with an env override, never process.execPath", () => {
		expect(resolveRagPython({ MW_RAG_PYTHON: " /custom/python " })).toBe("/custom/python");
		const fallback = resolveRagPython({});
		expect(fallback).toBe(process.platform === "win32" ? "python" : "python3");
		expect(fallback).not.toBe(process.execPath);
	});
});
