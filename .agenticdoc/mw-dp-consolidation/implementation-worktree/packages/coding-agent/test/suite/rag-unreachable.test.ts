/**
 * rag-unreachable.test.ts — mw-rag-integration T-16 (AC-007 / VC-104):
 *   VC-104  an enabled server that is down at activate time still registers
 *           the tool surface, every description carries the
 *           `[unreachable at session start]` marker, and the first real call
 *           appends a `rag-unavailable` evidence line (delta-only assertion).
 *
 * The fixture allocates an ephemeral port and then releases it, so "server
 * down" is a real connection refusal on 127.0.0.1 (no DNS, no timing race).
 *
 * The suite config uses `silent: "passed-only"` — every `[VERIFY]` line goes
 * through process.stdout.write.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { RAG_BASE_TOOL_NAMES, registerRagTools } from "../../src/extensions/agent-team-loop/rag/tools.ts";
import { startRagFixture } from "./rag-fixture.ts";

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

interface CapturedTool {
	name: string;
	description: string;
	parameters: unknown;
	execute: (
		toolCallId: string,
		params: Record<string, unknown>,
		signal?: AbortSignal,
		onUpdate?: (partial: { content: Array<{ type: "text"; text: string }>; details: unknown }) => void,
	) => Promise<{ content: Array<{ type: "text"; text: string }>; details: unknown }>;
}

class CapturingApi {
	readonly tools = new Map<string, CapturedTool>();

	registerTool(tool: unknown): void {
		const captured = tool as CapturedTool;
		this.tools.set(captured.name, captured);
	}

	setActiveTools(): void {}

	getActiveTools(): string[] {
		return [];
	}

	getAllTools(): Array<{ name: string }> {
		return [...this.tools.keys()].map((name) => ({ name }));
	}

	on(): void {}
}

function toolOf(capture: CapturingApi, name: string): CapturedTool {
	const tool = capture.tools.get(name);
	if (tool === undefined) throw new Error(`tool '${name}' was not registered`);
	return tool;
}

const tempDirs: string[] = [];
let savedServersFile: string | undefined;
let serversFileSaved = false;

/** A server entry pointing at `url`, MCP-only so a connect failure cannot fall
 * back to a CLI transport (which would mask the unreachable state). */
function serversYaml(name: string, url: string): string {
	return [
		"servers:",
		`  ${name}:`,
		"    transport: mcp",
		"    mcp:",
		`      url: ${url}`,
		"      token_env: RAG_UNREACHABLE_TEST_TOKEN",
		"    capabilities:",
		"      graph: true",
		"      chat: false",
		"      rewrite: false",
		"",
	].join("\n");
}

function makeProject(name: string, url: string): { project: string; taskDir: string } {
	const project = fs.mkdtempSync(path.join(os.tmpdir(), "rag-unreachable-"));
	tempDirs.push(project);
	fs.mkdirSync(path.join(project, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(
		path.join(project, ".agenticdoc", "target.yml"),
		`rag:\n  enabled: [${name}]\n  default_server: ${name}\n`,
		"utf8",
	);
	fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(project, ".mw", "rag-servers.yml"), serversYaml(name, url), "utf8");
	if (!serversFileSaved) {
		savedServersFile = process.env.MW_RAG_SERVERS_FILE;
		serversFileSaved = true;
	}
	process.env.MW_RAG_SERVERS_FILE = path.join(project, "machine-does-not-exist.yml");

	const taskDir = path.join(project, ".agenticdoc", "key-a", "workers", "w-unreachable");
	fs.mkdirSync(taskDir, { recursive: true });
	return { project, taskDir };
}

function readTrace(taskDir: string): string {
	try {
		return fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
	} catch {
		return "";
	}
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	if (serversFileSaved) {
		if (savedServersFile === undefined) delete process.env.MW_RAG_SERVERS_FILE;
		else process.env.MW_RAG_SERVERS_FILE = savedServersFile;
		serversFileSaved = false;
	}
});

describe("VC-104 unreachable server at session start", () => {
	it("keeps the tool surface, marks the description and appends rag-unavailable", async () => {
		// Bind then release an ephemeral port: the URL is guaranteed to refuse.
		const probe = await startRagFixture();
		const deadUrl = probe.url;
		await probe.stop();

		const { project, taskDir } = makeProject("A", deadUrl);
		const capture = new CapturingApi();
		const runtime = registerRagTools(capture as unknown as ExtensionAPI, project, { workerTaskDir: taskDir });
		expect(runtime).not.toBeNull();
		if (runtime === null) return;
		await runtime.ready;

		// Registration still happened and the activate probe recorded failure.
		expect([...capture.tools.keys()].sort()).toEqual([...RAG_BASE_TOOL_NAMES].sort());
		expect(runtime.reachable.get("A")).toBe(false);

		let marked = 0;
		for (const name of RAG_BASE_TOOL_NAMES) {
			if (toolOf(capture, name).description.includes("[unreachable at session start]")) marked += 1;
		}
		expect(marked).toBe(RAG_BASE_TOOL_NAMES.length);

		// Delta-only: snapshot the trace before the call, assert the new bytes.
		const before = readTrace(taskDir);
		const result = await toolOf(capture, "rag_search").execute("call-1", { query: "anything" });
		const details = result.details as { kind?: string };
		expect(details.kind).toBe("connect");
		const delta = readTrace(taskDir).slice(before.length);
		expect(delta).toContain("rag-unavailable");

		const marker = toolOf(capture, "rag_search").description.includes("[unreachable at session start]");
		verify(
			`[VERIFY] VC-104: unreachable_marker=${marker} rag_unavailable_line=${delta.includes(
				"rag-unavailable",
			)} server=A`,
		);
	});
});
