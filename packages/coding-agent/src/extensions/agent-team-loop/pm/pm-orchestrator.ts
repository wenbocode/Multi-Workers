import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { IndexStore } from "../shared/index-store.ts";
import { getMwStatus, initMw, startMw, waitForMwStart } from "../shared/mw-runner.ts";
import { agenticdocRoot as resolveAgenticdocRoot } from "../shared/paths.ts";
import { WorkerStore } from "../shared/worker-store.ts";
import { isGoalEstablished, readGoal } from "./goal-reader.ts";
import { dispatchTask } from "./task-dispatcher.ts";
import {
	displaySummary,
	registerMwCommands,
	registerMwTools,
	registerPmKeyCommands,
	registerWorkerCommands,
	registerWorkerTools,
} from "./ui-bridge.ts";

const POLL_INTERVAL_MS = 4000; // < 5s per AC-001

function readOutputSummary(taskDir: string): string | undefined {
	const outputPath = path.join(taskDir, "output.md");
	if (!fs.existsSync(outputPath)) return undefined;
	const content = fs.readFileSync(outputPath, "utf8");
	const m = content.match(/## Summary\s*\n+([\s\S]*?)(?=\n## |$)/);
	return m ? m[1].trim() : undefined;
}

function pickWorkerRoute(taskContent: string): { cli: string; provider: string } {
	if (/^type:\s*codex/im.test(taskContent)) return { cli: "codex", provider: "" };
	if (/^type:\s*(review|research)/im.test(taskContent)) return { cli: "claude", provider: "" };
	return { cli: "pi", provider: "timi" };
}

// Optional `model:` line in task.md → passed through to the launcher as --model/-m.
function readModel(taskContent: string): string {
	const m = taskContent.match(/^model:\s*(.+)$/im);
	return m ? m[1].trim() : "";
}

export async function dispatchNewTasks(workerStore: WorkerStore, agenticdocRoot: string): Promise<void> {
	// Worker tasks live under {key}/workers/<task-key>/task.md (owner = AgenticTask
	// key) or _scratch/workers/<task-key>/task.md (keyless ad-hoc). Root-level
	// task dirs are no longer dispatched - they polluted the key namespace.
	if (!fs.existsSync(agenticdocRoot)) return;
	const dispatched = new Set(workerStore.readAll().map((e) => e.taskKey));

	let owners: fs.Dirent[];
	try {
		owners = fs.readdirSync(agenticdocRoot, { withFileTypes: true });
	} catch {
		return;
	}

	for (const owner of owners) {
		if (!owner.isDirectory() || owner.name.startsWith(".")) continue;
		const workersDir = path.join(agenticdocRoot, owner.name, "workers");
		let taskDirs: fs.Dirent[];
		try {
			taskDirs = fs.readdirSync(workersDir, { withFileTypes: true });
		} catch {
			continue; // owner has no workers/ dir (plain key or meta entry)
		}
		for (const taskDir of taskDirs) {
			if (!taskDir.isDirectory() || taskDir.name.startsWith(".")) continue;
			const taskKey = taskDir.name;
			if (dispatched.has(taskKey)) continue;
			const taskMdPath = path.join(workersDir, taskKey, "task.md");
			if (!fs.existsSync(taskMdPath)) continue;

			const taskContent = fs.readFileSync(taskMdPath, "utf8");
			const { cli, provider } = pickWorkerRoute(taskContent);
			const model = readModel(taskContent);
			await dispatchTask(
				{
					taskKey,
					status: "pending",
					cli,
					provider,
					model,
					taskPath: taskMdPath,
				},
				workerStore,
			);
		}
	}
}

export function startWorkerPollLoop(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	pollIntervalMs = POLL_INTERVAL_MS,
): NodeJS.Timeout {
	const notified = new Set<string>();

	return setInterval(() => {
		try {
			const entries = workerStore.readAll();
			for (const entry of entries) {
				if (notified.has(entry.taskKey)) continue;
				if (entry.status === "done" || entry.status === "failed" || entry.status === "needs-clarification") {
					notified.add(entry.taskKey);
					// Task dir from the queue row taskPath: works for keyed {key}/workers/<task-key>/ and legacy root paths.
					const taskDir = path.dirname(entry.taskPath);
					const summary = readOutputSummary(taskDir);
					if (summary) {
						displaySummary(pi, `[${entry.taskKey}] ${entry.status}: ${summary}`);
					} else {
						// Terminal but no output.md summary — never stay silent. The worker may
						// have crashed/timed out; point at the per-task log for diagnosis.
						const logPath = path.join(taskDir, "worker.log");
						displaySummary(
							pi,
							`[${entry.taskKey}] ${entry.status} — 无 output.md 摘要（worker 可能崩溃/超时）。日志：${logPath}`,
						);
					}
				}
			}
		} catch {
			// Transient I/O error (e.g. EACCES during concurrent rename) — skip this tick
		}
	}, pollIntervalMs);
}

export function pmActivate(pi: ExtensionAPI): void {
	const projectDir = process.cwd();
	const agenticdocRoot = resolveAgenticdocRoot(projectDir);
	const workerStore = new WorkerStore(agenticdocRoot);
	const indexStore = new IndexStore(agenticdocRoot);

	// Register commands and tools during loading (safe — not action methods)
	registerPmKeyCommands(pi, indexStore);
	registerMwCommands(pi, projectDir);
	registerMwTools(pi, projectDir);
	registerWorkerTools(pi, workerStore, indexStore, agenticdocRoot);
	registerWorkerCommands(pi, workerStore, indexStore, agenticdocRoot);

	// Start worker status poll loop (setInterval is safe; displaySummary inside fires later)
	startWorkerPollLoop(pi, workerStore);

	// After each agent turn, scan for new task.md files and dispatch them (AC-030)
	pi.on("agent_settled", () => {
		dispatchNewTasks(workerStore, agenticdocRoot).catch(() => {
			// Dispatch errors are non-fatal — PM loop continues
		});
	});

	// Defer action method calls to after runner.initialize() (session_start fires post-init)
	pi.on("session_start", async () => {
		// Auto-init project if it hasn't been initialized yet. Gate on .agenticdoc
		// (the project marker mw init creates), NOT on a project-local bundle copy:
		// the extension is now installed GLOBALLY (mw setup), so no project-local
		// bundle exists and checking for one would re-run init on every session.
		const initialized = fs.existsSync(path.join(projectDir, ".agenticdoc"));
		if (!initialized) {
			const result = initMw(projectDir);
			if (result.ok) {
				displaySummary(pi, "[mw] Project initialized — .agenticdoc/ .mw/ .pi/extensions/ created.");
			} else {
				displaySummary(pi, `[mw] Init failed: ${result.error}`);
				return;
			}
		}

		// Auto-start mw background service if not already running.
		// After spawning, poll for the PID file so the agent's first turn doesn't
		// race against Python startup and falsely report mw as not running.
		// Stability window: the PID must stay alive for 3s — mw serve can die
		// right after startup (route precheck failure) and the old check would
		// report a false "started" in that window (mw-dispatch-reliability AC-005).
		const mwStatus = getMwStatus(projectDir);
		if (!mwStatus.running) {
			const started = startMw(projectDir);
			if (started) {
				const confirmed = await waitForMwStart(projectDir, 8000);
				displaySummary(
					pi,
					confirmed
						? "[mw] Background service started."
						: "[mw] Background service 启动未确认（可能预检失败或仍在启动）——运行 /mw doctor 诊断。",
				);
			} else {
				displaySummary(pi, "[mw] Could not find mw.py — run `mw start --project=.` manually.");
			}
		}

		// The project goal is the north-star every key/spec derives from.
		// Do NOT fabricate a placeholder — if it isn't established yet, softly
		// guide the user into the goal brainstorm workflow (/goal). An
		// established goal (or a legacy goal.md with content) is left untouched.
		const goal = readGoal(agenticdocRoot);
		if (!isGoalEstablished(goal)) {
			pi.sendUserMessage(
				"[agent-team-loop] 项目总目标（.agenticdoc/goal.md）尚未确立。\n" +
					"建议先运行 /goal，与我对话共创项目总目标——它是后续每个 spec 对齐的锚点。\n" +
					"（也可直接编辑 .agenticdoc/goal.md 填好三段内容并把 status 改为 active。）",
			);
		}
	});
}
