import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { type Context, InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { expect, it, vi } from "vitest";
import type { ExtensionAPI, ProviderConfig } from "../../src/core/extensions/types.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { configureLocalCodex } from "../../src/extensions/agent-team-loop/shared/codex-local.ts";
import { checkProxy, LOCAL_CODEX_PROVIDER } from "../../src/extensions/agent-team-loop/shared/codex-proxy.ts";
import { PYTHON_EXE } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";

it("ModelRuntime -> actual Python relay -> fake CLI -> tool result -> final response", async () => {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "codex-proxy-http-"));
	const token = "hermetic-http-test-token-at-least-24-characters";
	const pythonDir = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
	const fakeCli = path.join(root, "fake_cli.py");
	fs.writeFileSync(
		fakeCli,
		`import json, pathlib, sys
args = sys.argv
context = json.loads(sys.stdin.read().split("CONTEXT JSON:\\n", 1)[1])
has_result = any(message["role"] == "toolResult" for message in context["messages"])
result = {"text": "ready" if has_result else "", "tool_calls": [] if has_result else [{"name": "lookup", "arguments": '{"ticket":42}'}]}
pathlib.Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result), encoding="utf-8")
print(json.dumps({"type":"turn.completed", "usage":{"input_tokens":10,"output_tokens":2}}))
`,
	);
	const serverFile = path.join(root, "server.py");
	fs.writeFileSync(
		serverFile,
		`import sys
sys.path.insert(0, sys.argv[1])
from codex_local import CodexBackend, RelayServer
server = RelayServer(("127.0.0.1", 0), sys.argv[3], CodexBackend([sys.executable, sys.argv[2]], timeout=5))
print(server.server_port, flush=True)
try:
    server.serve_forever(poll_interval=0.1)
finally:
    server.server_close()
`,
	);
	const child = spawn(PYTHON_EXE, ["-u", serverFile, pythonDir, fakeCli, token], {
		windowsHide: true,
		stdio: ["ignore", "pipe", "pipe"],
	});
	let serverUrl: string | undefined;
	const exited = new Promise<void>((resolve) => child.once("close", () => resolve()));
	try {
		const port = await new Promise<number>((resolve, reject) => {
			const timer = setTimeout(() => reject(new Error("Fake relay startup timed out")), 5000);
			child.once("error", reject);
			child.stdout.once("data", (data: Buffer) => {
				clearTimeout(timer);
				resolve(Number(data.toString().trim()));
			});
			child.once("close", () => {
				clearTimeout(timer);
				reject(new Error("Fake relay exited before startup"));
			});
		});
		serverUrl = `http://127.0.0.1:${port}`;
		fs.mkdirSync(path.join(root, ".mw"));
		fs.writeFileSync(path.join(root, ".mw/codex-local.json"), JSON.stringify({ version: 1, url: serverUrl, token }));
		const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
		configureLocalCodex(
			{
				registerProvider: (id: string, config: ProviderConfig) => runtime.registerProvider(id, config),
			} as unknown as ExtensionAPI,
			root,
		);
		const model = runtime.getModel(LOCAL_CODEX_PROVIDER, "gpt-5.6-sol");
		if (!model) throw new Error("Missing local model");
		const context: Context = {
			messages: [{ role: "user", content: "look up ticket 42", timestamp: 1 }],
			tools: [{ name: "lookup", description: "lookup ticket", parameters: Type.Object({ ticket: Type.Number() }) }],
		};
		const first = await runtime.completeSimple(model, context);
		expect(first.stopReason).toBe("toolUse");
		const call = first.content[0];
		if (call.type !== "toolCall") throw new Error("Expected tool call");
		expect(call.arguments).toEqual({ ticket: 42 });
		context.messages.push(first, {
			role: "toolResult",
			toolCallId: call.id,
			toolName: call.name,
			content: [{ type: "text", text: "ready" }],
			isError: false,
			timestamp: 2,
		});
		const final = await runtime.completeSimple(model, context);
		expect(final.content).toEqual([{ type: "text", text: "ready" }]);
		await vi.waitFor(async () =>
			expect((await checkProxy({ url: serverUrl as string, token })).active).toHaveLength(0),
		);
		expect((await checkProxy({ url: serverUrl, token })).last_success?.model).toBe(model.id);
	} finally {
		if (serverUrl)
			await fetch(`${serverUrl}/stop`, { method: "POST", headers: { Authorization: `Bearer ${token}` } }).catch(
				() => {},
			);
		const timer = setTimeout(() => child.kill(), 2000);
		await exited;
		clearTimeout(timer);
		fs.rmSync(root, { recursive: true, force: true });
	}
}, 15_000);
