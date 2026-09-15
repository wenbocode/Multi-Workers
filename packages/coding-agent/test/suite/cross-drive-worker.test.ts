/**
 * Cross-drive dual-root end-to-end (mw-dual-workspace Task 008, AC-002 /
 * VC-003): on REAL different volumes (env-gated, D-009), the full TS chain —
 * dispatchTask (profile + deny_globs injection + queue row) → worker
 * execution with cwd=game on another drive → coordination writes anchored at
 * the control root — must leave ZERO framework files in the game and engine
 * trees while the control workspace holds the complete set.
 *
 * Gate: MW_TEST_CROSS_DRIVE_ROOTS with ≥2 entries on different volumes
 * (e.g. "F:/;E:/"). Missing/degenerate env → the e2e test skips and the
 * always-run gate test prints the skip reason (CI simulation mode).
 *
 * Rationale for the TS side carrying this: every cross-drive-sensitive code
 * path is here — read-scope's dual-basis relative computation
 * (path.relative across drives cannot relativize), realpath normalization,
 * and the worker write anchoring. The Python dispatch-side expansion is
 * pure string math over absolute paths (same-drive coverage suffices).
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	toolCall: (toolName: string, input: Record<string, unknown>) => { block?: boolean; reason?: string } | undefined;
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => unknown>>();
	const pi = {
		on: (name: string, cb: (e: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: () => {},
		setActiveTools: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		toolCall: (toolName: string, input: Record<string, unknown>) => {
			const cbs = handlers.get("tool_call") ?? [];
			return cbs[0]?.({ type: "tool_call", toolCallId: "tc", toolName, input }) as
				| { block?: boolean; reason?: string }
				| undefined;
		},
	};
}

/** Parse MW_TEST_CROSS_DRIVE_ROOTS; null unless it names ≥2 distinct volumes. */
function parseCrossDriveRoots(): string[] | null {
	const raw = process.env.MW_TEST_CROSS_DRIVE_ROOTS;
	if (!raw) return null;
	const parts = raw
		.split(/[;]+/)
		.map((s) => s.trim())
		.filter(Boolean);
	if (parts.length < 2) return null;
	const volumes = new Set(parts.map((p) => path.parse(path.resolve(p)).root));
	return volumes.size >= 2 ? parts : null;
}

/** AC-002 framework-file patterns that must never appear in a target tree. */
const FRAMEWORK_NAMES = new Set([
	".agenticdoc",
	".mw",
	"_workers.parallel",
	"_index.parallel",
	"trace.log",
	"output.md",
]);
const PHASE_MD = /^phase-.*\.md$/;

function countFrameworkFiles(root: string): number {
	let hits = 0;
	const walk = (dir: string) => {
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			if (FRAMEWORK_NAMES.has(entry.name) || PHASE_MD.test(entry.name)) hits += 1;
			if (entry.isDirectory()) walk(path.join(dir, entry.name));
		}
	};
	walk(root);
	return hits;
}

function mkdtempOn(root: string, prefix: string): string {
	return fs.mkdtempSync(path.join(root, prefix));
}

describe("cross-drive dual-root e2e (mw-dual-workspace AC-002)", () => {
	const roots = parseCrossDriveRoots();

	it("gate status (always runs; documents the skip reason on CI-like runs)", () => {
		if (roots === null) {
			console.log(
				"[SKIP] VC-003: MW_TEST_CROSS_DRIVE_ROOTS absent or degenerate — cross-drive semantics not covered on this run (D-009)",
			);
		} else {
			console.log(`[GATE] VC-003: cross-drive roots = ${roots.join(" ; ")}`);
		}
	});

	const gated = roots === null ? it.skip : it;
	gated("VC-003: dispatch → cross-drive worker run → zero target-tree pollution", async () => {
		const [gameRoot, controlRoot] = roots as string[];
		const control = mkdtempOn(controlRoot, "mw-xdr-ctl-");
		const game = mkdtempOn(gameRoot, "mw-xdr-game-");
		const engine = mkdtempOn(controlRoot, "mw-xdr-eng-");
		try {
			// target.yml: dual, game on the OTHER drive, engine beside control.
			const agenticdoc = path.join(control, ".agenticdoc");
			fs.mkdirSync(agenticdoc, { recursive: true });
			fs.writeFileSync(
				path.join(agenticdoc, "target.yml"),
				[
					"mode: dual",
					`game: '${game.replace(/\\/g, "/")}'`,
					`engine: '${engine.replace(/\\/g, "/")}'`,
					"ignore:",
					"  deny_globs:",
					'    - "**/*.uasset"',
					"",
				].join("\n"),
				"utf8",
			);

			// Game/engine fixtures. DDC asset sits INSIDE the allowed scope so the
			// deny-glob (not scope) is what must block it — deny priority, and the
			// dual-basis relative path cannot relativize across drives here.
			fs.mkdirSync(path.join(game, "Content", "DDC"), { recursive: true });
			fs.writeFileSync(path.join(game, "Content", "ok.txt"), "in scope", "utf8");
			fs.writeFileSync(path.join(game, "Content", "DDC", "x.uasset"), "binary-ish", "utf8");
			fs.writeFileSync(path.join(game, "secret.txt"), "out of scope", "utf8");
			fs.writeFileSync(path.join(engine, "file.txt"), "engine scope", "utf8");

			// 1. TS dispatch: task.md (raw, pre-injection) + queue row.
			const taskDir = path.join(agenticdoc, "_scratch", "workers", "ap-xdr-vc003");
			fs.mkdirSync(taskDir, { recursive: true });
			const taskMd = path.join(taskDir, "task.md");
			fs.writeFileSync(
				taskMd,
				[
					"---",
					"type: verifier",
					"read_scope:",
					"  - Content",
					`  - ${engine}`,
					"---",
					"",
					"Cross-drive verification task.",
					"",
				].join("\n"),
				"utf8",
			);
			const store = new WorkerStore(agenticdoc);
			await dispatchTask(
				{ taskKey: "ap-xdr-vc003", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: taskMd },
				store,
			);
			// dispatchTask injected the deny firewall (from target.yml) and queued.
			expect(fs.readFileSync(taskMd, "utf8")).toContain("deny_globs:\n  - '**/*.uasset'");
			expect(store.readAll().map((e) => e.taskKey)).toEqual(["ap-xdr-vc003"]);

			// 2. Worker execution with cwd=game (launcher's dual guarantee).
			delete process.env.MW_TARGET_GAME;
			delete process.env.MW_TARGET_ENGINE;
			process.env.PI_WORKER_TASK = taskMd;
			const cwd = process.cwd();
			process.chdir(game);
			try {
				const worker = fakeWorkerPi();
				await workerModeActivate(worker.pi);

				// Scope: game-relative entry anchors cwd (cross-drive control paths
				// are matched via realpath, not relative math); engine absolute.
				expect(worker.toolCall("read", { path: "Content/ok.txt" })).toBeUndefined();
				expect(worker.toolCall("read", { path: path.join(engine, "file.txt") })).toBeUndefined();
				expect(worker.toolCall("read", { path: "secret.txt" })?.block).toBe(true);
				// Deny priority inside an allowed scope, cross-drive cwd.
				const denied = worker.toolCall("read", { path: "Content/DDC/x.uasset" });
				expect(denied?.block).toBe(true);
				expect(denied?.reason).toContain("**/*.uasset");

				// Exit write.
				worker.emit("agent_end", { messages: [] });
				worker.emit("agent_settled");
			} finally {
				process.chdir(cwd);
				delete process.env.PI_WORKER_TASK;
			}

			// 3. AC-002: zero framework files in the target trees.
			const gameHits = countFrameworkFiles(game);
			const engineHits = countFrameworkFiles(engine);

			// 4. Control workspace holds the complete coordination set.
			const controlComplete =
				fs.existsSync(path.join(taskDir, "task.md")) &&
				fs.existsSync(path.join(taskDir, "trace.log")) &&
				fs.existsSync(path.join(taskDir, "output.md")) &&
				fs.existsSync(path.join(agenticdoc, "_workers.parallel"));
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toMatch(/rule=deny-glob/);

			expect(gameHits).toBe(0);
			expect(engineHits).toBe(0);
			expect(controlComplete).toBe(true);
			console.log(
				`[VERIFY] VC-003: target-tree-hits=0 control-files=complete (game-hits=${gameHits} engine-hits=${engineHits})`,
			);
		} finally {
			// Real-volume temp dirs must never leak (F:/ is a Perforce client root).
			fs.rmSync(control, { recursive: true, force: true });
			fs.rmSync(game, { recursive: true, force: true });
			fs.rmSync(engine, { recursive: true, force: true });
		}
	});
});
