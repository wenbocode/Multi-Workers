/**
 * Dual-root worker execution tests (mw-dual-workspace Task 005, AC-003,
 * VC-005/VC-009).
 *
 * The launcher guarantee is simulated with process.chdir(game) — same-drive
 * dual fixture (cross-drive semantics are Task 008, env-gated). With cwd=game
 * and the task.md under the control root:
 * - VC-005: every coordination write (trace.log / output.md) lands under the
 *   CONTROL root's task dir; the game tree stays free of framework files.
 * - VC-009: read_scope spans the game root (relative entry, anchored to cwd)
 *   and the engine root (absolute entry); outside both is blocked.
 * - controlRootFromTaskPath (paths.ts D-001 helper) agrees with where the
 *   writes actually land.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { mwCodeNewestMtimeMs, serveStaleness } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { controlRootFromTaskPath } from "../../src/extensions/agent-team-loop/shared/paths.ts";
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
		registerTool: () => {},
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

function mkdtemp(prefix: string): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

describe("dual-root worker execution (mw-dual-workspace AC-003)", () => {
	it("VC-005/VC-009: writes anchor the control root; scope spans game+engine", async () => {
		const control = mkdtemp("atl-dual-ctl-");
		const game = mkdtemp("atl-dual-game-");
		const engine = mkdtemp("atl-dual-eng-");

		// Task under the CONTROL root (conductor shape).
		const taskDir = path.join(control, ".agenticdoc", "goal-autopilot", "workers", "ap-dual-vc005");
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
				"Verify the dual-root phase gate.",
				"",
			].join("\n"),
			"utf8",
		);

		// Fixtures: game tree (relative scope anchor via cwd) + engine tree.
		fs.mkdirSync(path.join(game, "Content"), { recursive: true });
		fs.writeFileSync(path.join(game, "Content", "ok.txt"), "in game scope", "utf8");
		fs.writeFileSync(path.join(game, "secret.txt"), "out of scope", "utf8");
		fs.writeFileSync(path.join(engine, "file.txt"), "in engine scope", "utf8");

		process.env.PI_WORKER_TASK = taskMd;
		const cwd = process.cwd();
		process.chdir(game); // the launcher's dual-mode cwd guarantee
		try {
			const worker = fakeWorkerPi();
			await workerModeActivate(worker.pi);

			// VC-009: relative entry anchors to cwd (= game root in dual mode).
			expect(worker.toolCall("read", { path: "Content/ok.txt" })).toBeUndefined();
			// VC-009: absolute engine entry allowed cross-root.
			expect(worker.toolCall("read", { path: path.join(engine, "file.txt") })).toBeUndefined();
			// VC-009: outside both roots is blocked.
			const blocked = worker.toolCall("read", { path: "secret.txt" });
			expect(blocked?.block).toBe(true);
			expect(blocked?.reason).toContain("rule=scope");

			// VC-005: the block write and the exit write land under the CONTROL
			// root's task dir, never the game tree.
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toMatch(/\[READ_SCOPE\] \S+ blocked path=secret\.txt rule=scope tool=read/);
			worker.emit("agent_end", { messages: [] });
			worker.emit("agent_settled");
			expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(true);

			for (const name of [".agenticdoc", "trace.log", "output.md", "_workers.parallel", ".mw"]) {
				expect(fs.existsSync(path.join(game, name))).toBe(false);
			}

			// Helper lock: controlRootFromTaskPath agrees with the real write root.
			expect(fs.realpathSync.native(controlRootFromTaskPath(taskMd))).toBe(fs.realpathSync.native(control));

			console.log("[VERIFY] VC-005: write-prefix=control-root");
			console.log("[VERIFY] VC-009: game-allow=true engine-allow=true outside-block=true");
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
			for (const dir of [control, game, engine]) {
				fs.rmSync(dir, { recursive: true, force: true });
			}
		}
	});

	it("controlRootFromTaskPath peels the 5-level worker-task shape", () => {
		const taskMd = path.join("C:", "proj", ".agenticdoc", "k", "workers", "t1", "task.md");
		if (process.platform === "win32") {
			expect(controlRootFromTaskPath(taskMd)).toBe(path.join("C:", "proj"));
		}
		const root = path.parse(process.cwd()).root;
		const scratch = path.join(root, "w", ".agenticdoc", "_scratch", "workers", "t2", "task.md");
		expect(controlRootFromTaskPath(scratch)).toBe(path.join(root, "w"));
	});
});

describe("dual-root goal check + serve staleness (mw-dual-workspace AC-008/AC-009)", () => {
	it("VC-014: [GOAL_CHECK] tracks the CONTROL goal.md with cwd=game", async () => {
		const control = mkdtemp("atl-goal-ctl-");
		const game = mkdtemp("atl-goal-game-");

		// goal.md lives at the TRUE .agenticdoc root (control) with a fixed,
		// recognizable mtime — a miss (wrong root) would record 0 (D-116).
		const agenticdoc = path.join(control, ".agenticdoc");
		fs.mkdirSync(agenticdoc, { recursive: true });
		const goalMd = path.join(agenticdoc, "goal.md");
		fs.writeFileSync(goalMd, "# Goal\n", "utf8");
		const fixedGoalMtime = 1_700_000_123_456;
		const fixedDate = new Date(fixedGoalMtime);
		fs.utimesSync(goalMd, fixedDate, fixedDate);

		const taskDir = path.join(agenticdoc, "goal-autopilot", "workers", "ap-dual-vc014");
		fs.mkdirSync(taskDir, { recursive: true });
		// Canonical phased task.md shape (phases are body content, prompts end at
		// the next `- name:` line).
		fs.writeFileSync(
			path.join(taskDir, "task.md"),
			["type: coding", "", "- name: investigate", "  prompt: |", "    Look around and report.", ""].join("\n"),
			"utf8",
		);

		process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
		const cwd = process.cwd();
		process.chdir(game); // launcher's dual-mode cwd guarantee
		try {
			const worker = fakeWorkerPi();
			await workerModeActivate(worker.pi);

			// Initial settle starts phase 1/1; phase result ends it.
			worker.emit("agent_settled");
			worker.emit("agent_end", {
				messages: [{ role: "assistant", content: [{ type: "text", text: "phase result" }] }],
			});
			worker.emit("agent_settled");

			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			const goalMtimeMs = fs.statSync(goalMd).mtimeMs; // whatever precision the FS kept
			expect(trace).toContain(`[GOAL_CHECK] phase=1 goal_mtime=${goalMtimeMs}`);
			expect(trace).not.toContain("goal_mtime=0"); // 0 would mean the wrong root was stat'ed (D-116)
			// Phase output + exit write anchor the CONTROL task dir.
			expect(fs.existsSync(path.join(taskDir, "progress", "phase-1.md"))).toBe(true);
			expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(true);
			// The game tree never sees coordination files — not even goal.md.
			expect(fs.existsSync(path.join(game, "goal.md"))).toBe(false);
			expect(fs.existsSync(path.join(game, ".agenticdoc"))).toBe(false);

			const goalCheckPass = trace.includes(`[GOAL_CHECK] phase=1 goal_mtime=${goalMtimeMs}`);
			console.log(
				`[VERIFY] VC-014: goal-check-pass=${goalCheckPass} trace-has-goalcheck=${trace.includes("[GOAL_CHECK]")}`,
			);
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
			fs.rmSync(control, { recursive: true, force: true });
			fs.rmSync(game, { recursive: true, force: true });
		}
	});

	it("VC-016: staleness baselines on CONTROL mw source mtime, never the game tree", () => {
		const control = mkdtemp("atl-stale-ctl-");
		const game = mkdtemp("atl-stale-game-");

		// Fake mw source tree in the CONTROL workspace + serve.meta stamp.
		const pkg = path.join(control, "packages", "multi-workers");
		const autoDir = path.join(pkg, "autopilot");
		fs.mkdirSync(autoDir, { recursive: true });
		fs.writeFileSync(path.join(pkg, "mw.py"), "# mw", "utf8");
		fs.writeFileSync(path.join(autoDir, "state.py"), "# state", "utf8");

		const T = Date.now() - 3_600_000;
		const at = (ms: number) => new Date(ms);
		// Control code is 10s newer than the serve start (fresh, within slack).
		fs.utimesSync(path.join(pkg, "mw.py"), at(T), at(T));
		fs.utimesSync(path.join(autoDir, "state.py"), at(T + 10_000), at(T + 10_000));
		// Game tree "build output" is FAR newer — must not count as mw code.
		const gameArtifact = path.join(game, "Build", "Cooked.py");
		fs.mkdirSync(path.dirname(gameArtifact), { recursive: true });
		fs.writeFileSync(gameArtifact, "# cooked", "utf8");
		fs.utimesSync(gameArtifact, at(T + 3_000_000), at(T + 3_000_000));

		const mwDir = path.join(control, ".mw");
		fs.mkdirSync(mwDir, { recursive: true });
		fs.writeFileSync(
			path.join(mwDir, "serve.meta"),
			JSON.stringify({ pid: 4242, started_at_ms: T + 8_000, code_dir: pkg }),
			"utf8",
		);

		// Game-side newness alone: still fresh (staleness never scans the game tree).
		const codeMs = mwCodeNewestMtimeMs(path.join(pkg, "mw.py"));
		expect(codeMs).not.toBeNull();
		expect(serveStaleness(control, codeMs ?? undefined)?.stale).toBe(false);

		// A CONTROL source edit after the serve start flips it stale.
		fs.utimesSync(path.join(autoDir, "state.py"), at(T + 60_000), at(T + 60_000));
		const stale = serveStaleness(control, mwCodeNewestMtimeMs(path.join(pkg, "mw.py")) ?? undefined);
		expect(stale?.stale).toBe(true);
		console.log(`[VERIFY] VC-016: staleness-detect=${stale?.stale === true}`);

		fs.rmSync(control, { recursive: true, force: true });
		fs.rmSync(game, { recursive: true, force: true });
	});
});
