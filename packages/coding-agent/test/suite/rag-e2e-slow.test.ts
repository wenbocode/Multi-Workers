/**
 * rag-e2e-slow.test.ts — VC-017 L2 (AC-013): a real 180s `rag_chat` must not
 * be killed by the worker idle watchdog.
 *
 * This is the slow half of VC-017 that T-05 explicitly deferred to T-11
 * (`l2_worker_alive_scope=T-11`). It activates the real `workerModeActivate`
 * against a fixture MCP server whose `rag_chat` handler blocks for 180s, with
 * `PI_WORKER_IDLE_MS=60000` (idle threshold below the call duration) and a
 * wall budget of 240s. The worker's heartbeat (30s `withHeartbeat` →
 * `tool_execution_update` → `touch()`) must keep the idle watchdog quiet while
 * the call is in flight.
 *
 * Default-skipped: one run costs ~3 minutes. Open it explicitly:
 *
 *   MW_RAG_SLOW=1 npx vitest --run test/suite/rag-e2e-slow.test.ts
 *
 * The `MW_RAG_SLOW_MS` env override exists for debugging only; the recorded
 * evidence run uses the default 180000 ms.
 *
 * Assertions (the VC-017 L2 contract):
 *   1. the call returns after >= 180000 ms and the worker is still alive
 *      (the idle watchdog never fired `process.exit`);
 *   2. `trace.log` carries a `rag_call ... ms=<>=180000>` line;
 *   3. the idle watchdog was armed: a `[CHECKPOINT]` line from the same
 *      watchdog suite is present, and the resolved idle threshold is 60000 ms;
 *   4. the heartbeat delivered >= 4 progress updates (onUpdate) during the call.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { RAG_HEARTBEAT_INTERVAL_MS } from "../../src/extensions/agent-team-loop/rag/budget.ts";
import { ENV_RAG_SERVERS_FILE } from "../../src/extensions/agent-team-loop/rag/config.ts";
import {
	parseTaskMd,
	resolveIdleMs,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { type RagFixture, startRagFixture } from "./rag-fixture.ts";

const SLOW_ENABLED = process.env.MW_RAG_SLOW === "1";
const SLOW_MS = Number(process.env.MW_RAG_SLOW_MS ?? 180_000);
const IDLE_MS = 60_000;
const WALL_MS = 240_000;

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

interface CapturedTool {
	name: string;
	execute: (
		toolCallId: string,
		params: Record<string, unknown>,
		signal?: AbortSignal,
		onUpdate?: (partial: { content: Array<{ type: "text"; text: string }>; details: unknown }) => void,
	) => Promise<unknown>;
}

class FakeWorkerPi {
	readonly handlers = new Map<string, Array<(event: unknown, ctx?: unknown) => unknown>>();
	readonly tools = new Map<string, CapturedTool>();
	active: string[] = [];
	readonly sent: Array<{ text: string; options?: { deliverAs?: string } }> = [];

	on(name: string, cb: (event: unknown, ctx?: unknown) => unknown): void {
		const list = this.handlers.get(name) ?? [];
		list.push(cb);
		this.handlers.set(name, list);
	}

	sendUserMessage(text: string, options?: { deliverAs?: string }): void {
		this.sent.push({ text, options });
	}

	setActiveTools(names: string[]): void {
		this.active = [...names];
	}

	registerTool(tool: unknown): void {
		const captured = tool as CapturedTool;
		this.tools.set(captured.name, captured);
	}

	getActiveTools(): string[] {
		return [...this.active];
	}

	getAllTools(): Array<{ name: string }> {
		return [...this.tools.keys()].map((name) => ({ name }));
	}

	emit(name: string, payload?: unknown): void {
		for (const cb of this.handlers.get(name) ?? []) cb(payload);
	}
}

const savedEnv = new Map<string, string | undefined>();
const fixtures: RagFixture[] = [];
const tempDirs: string[] = [];

function setEnv(name: string, value: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	process.env[name] = value;
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

describe.skipIf(!SLOW_ENABLED)("VC-017 L2: 180s rag_chat under a 60s idle watchdog", () => {
	it(
		"worker survives the slow call; rag_call ms >= 180000; watchdog armed",
		async () => {
			// A real fixture whose rag_chat blocks for the full slow window.
			const fixture = await startRagFixture({
				tools: {
					rag_chat: async () => {
						await sleep(SLOW_MS);
						return { answer: "slow but alive", documents: [] };
					},
				},
			});
			fixtures.push(fixture);

			const root = fs.mkdtempSync(path.join(os.tmpdir(), "rag-e2e-slow-"));
			tempDirs.push(root);
			const key = "slow-key";
			const taskDir = path.join(root, ".agenticdoc", key, "workers", "t-slow");
			fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
			fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
			fs.mkdirSync(taskDir, { recursive: true });
			fs.writeFileSync(
				path.join(root, ".agenticdoc", "target.yml"),
				[
					"rag:",
					"  enabled: [A]",
					"  default_server: A",
					"  budgets:",
					"    chat_budget: 2",
					"    time_budget_s: 900",
					"",
				].join("\n"),
				"utf8",
			);
			fs.writeFileSync(
				path.join(root, ".mw", "rag-servers.yml"),
				[
					"servers:",
					"  A:",
					"    transport: mcp",
					"    mcp:",
					`      url: ${fixture.url}`,
					"    capabilities:",
					"      graph: false",
					"      chat: true",
					"      rewrite: false",
					"",
				].join("\n"),
				"utf8",
			);
			const taskPath = path.join(taskDir, "task.md");
			fs.writeFileSync(taskPath, "type: rag-research\nphase: execute\n\nSlow research call.\n", "utf8");

			// Hermetic machine layer (hard override to a non-existent file).
			setEnv(ENV_RAG_SERVERS_FILE, path.join(root, "no-machine-layer.yml"));
			setEnv("PI_WORKER_TASK", taskPath);
			setEnv("PI_WORKER_IDLE_MS", String(IDLE_MS));
			setEnv("PI_WORKER_TIMEOUT_MS", String(WALL_MS));

			const worker = new FakeWorkerPi();
			const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
			let pings = 0;
			let callMs = -1;
			try {
				await workerModeActivate(worker as unknown as ExtensionAPI);
				// before_agent_start is what registers rag_chat (rag-research).
				worker.emit("before_agent_start");
				const chat = worker.tools.get("rag_chat");
				expect(chat, "rag_chat must be registered for rag-research").toBeDefined();
				if (chat === undefined) return;

				const startedAt = Date.now();
				const result = await chat.execute(
					"slow-call-1",
					{ query: "why is the renderer slow?" },
					undefined,
					// The host forwards onUpdate as tool_execution_update; worker-mode
					// listens to that event and calls touch().
					() => {
						pings += 1;
						worker.emit("tool_execution_update");
					},
				);
				callMs = Date.now() - startedAt;

				expect(result).toBeDefined();
				expect(callMs).toBeGreaterThanOrEqual(SLOW_MS);
				expect(SLOW_MS).toBeGreaterThanOrEqual(180_000);
				// Worker alive: the idle watchdog never fired its process.exit(1).
				expect(exitSpy).not.toHaveBeenCalled();
				// Heartbeat kept the idle watchdog fed.
				expect(pings).toBeGreaterThanOrEqual(4);
				expect(RAG_HEARTBEAT_INTERVAL_MS).toBe(30_000);
				// Watchdog armed: the same suite's convergence checkpoint fired.
				const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
				const callLine = trace
					.split(/\r?\n/)
					.find((line) => line.includes("rag_call ") && line.includes("tool=rag_chat"));
				expect(callLine, "trace.log must carry a rag_call line").toBeDefined();
				const ms = Number(/ ms=(\d+) /.exec(`${callLine} `)?.[1] ?? "-1");
				expect(ms).toBeGreaterThanOrEqual(180_000);
				expect(trace).toContain("[CHECKPOINT]");
				expect(resolveIdleMs(process.env.PI_WORKER_IDLE_MS)).toBe(IDLE_MS);
				// The task.md the worker actually parsed is the rag-research one.
				expect(parseTaskMd(taskPath).type).toBe("rag-research");

				process.stdout.write(
					`[VERIFY] VC-017: worker_alive=true rag_call_ms=${ms} pings=${pings} watchdog_enabled=true idle_ms=${IDLE_MS} heartbeat_ms=${RAG_HEARTBEAT_INTERVAL_MS}\n`,
				);
			} finally {
				exitSpy.mockRestore();
			}
		},
		SLOW_MS + 60_000,
	);
});
