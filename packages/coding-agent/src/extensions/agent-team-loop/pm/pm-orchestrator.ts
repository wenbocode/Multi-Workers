import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { IndexStore } from "../shared/index-store.ts";
import { getMwStatus, initMw, startMw } from "../shared/mw-runner.ts";
import { WorkerStore } from "../shared/worker-store.ts";
import { readOrElicitGoal } from "./goal-reader.ts";
import { dispatchTask } from "./task-dispatcher.ts";
import { displaySummary, registerMwCommands, registerMwTools, registerPmKeyCommands } from "./ui-bridge.ts";

const POLL_INTERVAL_MS = 4000; // < 5s per AC-001

function readOutputSummary(agenticdocRoot: string, taskKey: string): string | undefined {
	const outputPath = path.join(agenticdocRoot, taskKey, "output.md");
	if (!fs.existsSync(outputPath)) return undefined;
	const content = fs.readFileSync(outputPath, "utf8");
	const m = content.match(/## Summary\s*\n+([\s\S]*?)(?=\n## |$)/);
	return m ? m[1].trim() : undefined;
}

function pickWorkerRoute(taskContent: string): { cli: string; provider: string } {
	if (/^type:\s*(review|research)/im.test(taskContent)) return { cli: "claude", provider: "" };
	return { cli: "pi", provider: "timi" };
}

async function dispatchNewTasks(workerStore: WorkerStore, agenticdocRoot: string): Promise<void> {
	if (!fs.existsSync(agenticdocRoot)) return;
	const dispatched = new Set(workerStore.readAll().map((e) => e.taskKey));

	let dirents: fs.Dirent[];
	try {
		dirents = fs.readdirSync(agenticdocRoot, { withFileTypes: true });
	} catch {
		return;
	}

	for (const dirent of dirents) {
		if (!dirent.isDirectory()) continue;
		const taskKey = dirent.name;
		// Skip meta dirs
		if (taskKey.startsWith("_") || taskKey.startsWith(".")) continue;
		const taskMdPath = path.join(agenticdocRoot, taskKey, "task.md");
		if (!fs.existsSync(taskMdPath)) continue;
		if (dispatched.has(taskKey)) continue;

		const taskContent = fs.readFileSync(taskMdPath, "utf8");
		const { cli, provider } = pickWorkerRoute(taskContent);
		await dispatchTask(
			{
				taskKey,
				status: "pending",
				cli,
				provider,
				taskPath: taskMdPath,
			},
			workerStore,
		);
	}
}

export function startWorkerPollLoop(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	agenticdocRoot: string,
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
					const summary = readOutputSummary(agenticdocRoot, entry.taskKey);
					if (summary) {
						displaySummary(pi, `[${entry.taskKey}] ${entry.status}: ${summary}`);
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
	const agenticdocRoot = path.join(projectDir, ".agenticdoc");
	const workerStore = new WorkerStore(agenticdocRoot);
	const indexStore = new IndexStore(agenticdocRoot);

	// Register commands and tools during loading (safe — not action methods)
	registerPmKeyCommands(pi, indexStore);
	registerMwCommands(pi, projectDir);
	registerMwTools(pi, projectDir);

	// Start worker status poll loop (setInterval is safe; displaySummary inside fires later)
	startWorkerPollLoop(pi, workerStore, agenticdocRoot);

	// After each agent turn, scan for new task.md files and dispatch them (AC-030)
	pi.on("agent_settled", () => {
		dispatchNewTasks(workerStore, agenticdocRoot).catch(() => {
			// Dispatch errors are non-fatal — PM loop continues
		});
	});

	// Defer action method calls to after runner.initialize() (session_start fires post-init)
	pi.on("session_start", async () => {
		// Auto-init project if extension bundle not installed yet
		const bundleInstalled = fs.existsSync(path.join(projectDir, ".pi", "extensions", "agent-team-loop.js"));
		if (!bundleInstalled) {
			const result = initMw(projectDir);
			if (result.ok) {
				displaySummary(pi, "[mw] Project initialized — .agenticdoc/ .mw/ .pi/extensions/ created.");
			} else {
				displaySummary(pi, `[mw] Init failed: ${result.error}`);
				return;
			}
		}

		// Auto-start mw background service if not already running
		const mwStatus = getMwStatus(projectDir);
		if (!mwStatus.running) {
			const started = startMw(projectDir);
			displaySummary(
				pi,
				started
					? "[mw] Starting background service…"
					: "[mw] Could not find mw.py — run `mw start --project=.` manually.",
			);
		}

		// Ensure goal.md exists (AC-021)
		await readOrElicitGoal(agenticdocRoot, pi);
	});
}
