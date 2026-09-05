import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { appendGoalCheck, appendTrace, writeOutput } from "./output-writer.ts";
import type { TaskPhase } from "./phase-runner.ts";
import { goalMtime, writePhaseFile } from "./phase-runner.ts";

// ── Tool allowlists by task type ─────────────────────────────────────────────

const TOOL_ALLOWLISTS: Record<string, string[]> = {
	coding: ["read", "write", "edit", "bash", "find", "grep", "ls"],
	review: ["read", "find", "grep", "ls"],
	research: ["read", "find", "grep", "ls", "bash"],
	fallback: ["read", "write", "edit", "bash", "find", "grep", "ls"],
};

function toolsForType(taskType: string): string[] {
	return TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback ?? [];
}

// ── Task file parsing ────────────────────────────────────────────────────────

interface TaskMeta {
	type: string;
	phases?: TaskPhase[];
	taskKey: string;
	agenticdocRoot: string;
}

function parseTaskMd(taskPath: string): TaskMeta {
	const content = fs.readFileSync(taskPath, "utf8");
	const lines = content.split("\n");

	let taskType = "default";
	const phases: TaskPhase[] = [];
	let currentPhase: TaskPhase | null = null;
	let inPhasePrompt = false;

	for (const line of lines) {
		const trimmed = line.trim();
		if (trimmed.startsWith("type:")) {
			taskType = trimmed.slice("type:".length).trim();
		}
		if (trimmed.startsWith("- name:")) {
			currentPhase = { name: trimmed.slice("- name:".length).trim(), prompt: "" };
			phases.push(currentPhase);
			inPhasePrompt = false;
		} else if (trimmed === "prompt: |" && currentPhase) {
			inPhasePrompt = true;
		} else if (inPhasePrompt && currentPhase) {
			if (trimmed.startsWith("- ") || trimmed.startsWith("name:")) {
				inPhasePrompt = false;
			} else {
				currentPhase.prompt += `${line}\n`;
			}
		}
	}

	// taskKey is the parent directory name of the task file
	const agenticdocRoot = path.dirname(path.dirname(taskPath));
	const taskKey = path.basename(path.dirname(taskPath));

	return { type: taskType, phases: phases.length > 0 ? phases : undefined, taskKey, agenticdocRoot };
}

// ── Main entry ───────────────────────────────────────────────────────────────

export async function workerModeActivate(pi: ExtensionAPI): Promise<void> {
	const taskPathEnv = process.env.PI_WORKER_TASK;
	if (!taskPathEnv) {
		return;
	}

	const taskPath = path.resolve(taskPathEnv);
	if (!fs.existsSync(taskPath)) {
		process.exit(1);
	}

	const meta = parseTaskMd(taskPath);

	// Safety net: guarantee an output.md exists on any exit path. The normal
	// writers (success / timeout / catch) set outputWritten=true; if the process
	// dies before any of them run (hard crash, unexpected process.exit), the
	// exit hook writes a minimal failure output so the PM never sees silence.
	let outputWritten = false;
	process.on("exit", () => {
		if (outputWritten) return;
		try {
			writeOutput({
				taskKey: meta.taskKey,
				agenticdocRoot: meta.agenticdocRoot,
				exitCode: 1,
				summary: "(worker exited without writing output)",
				exitReason: "Process exited before output.md was written (crash or unexpected exit).",
			});
		} catch {
			// Best-effort during exit — nothing else we can do.
		}
	});

	// Set tool allowlist once before the first agent run (AC-010)
	// setActiveTools is an action method — must be deferred to after runner.initialize()
	pi.on("before_agent_start", () => {
		pi.setActiveTools(toolsForType(meta.type));
	});

	// Track tool calls for trace.log (AC-012)
	let toolCallCount = 0;
	const toolsUsed = new Set<string>();
	pi.on("tool_execution_start", (event) => {
		toolCallCount++;
		toolsUsed.add(event.toolName);
		appendTrace(meta.taskKey, meta.agenticdocRoot, `tool_call ${event.toolName}`);
	});

	// Capture last assistant text for output summary (AC-019)
	let lastAssistantText = "";
	pi.on("agent_end", (event) => {
		for (let i = event.messages.length - 1; i >= 0; i--) {
			const msg = event.messages[i];
			if (msg.role === "assistant") {
				const text = msg.content
					.filter((c): c is { type: "text"; text: string } => c.type === "text" && "text" in c)
					.map((c) => c.text)
					.join("\n");
				if (text) lastAssistantText = text;
				break;
			}
		}
	});

	// Watchdog: exit on timeout if agent_settled never fires (network hang, crashed session)
	const timeoutMs = Number(process.env.PI_WORKER_TIMEOUT_MS) || 30 * 60 * 1000;
	const watchdog = setTimeout(() => {
		writeOutput({
			taskKey: meta.taskKey,
			agenticdocRoot: meta.agenticdocRoot,
			exitCode: 1,
			summary: "Worker timed out waiting for agent_settled.",
			exitReason: `No response after ${timeoutMs}ms.`,
		});
		outputWritten = true;
		process.exit(1);
	}, timeoutMs);
	watchdog.unref();

	// Phase state machine: track how many phases have been dispatched and completed.
	// - initialSettled: true once the first agent_settled fires (after pi -p <task_content>)
	// - nextPhaseIdx: index of the next phase prompt to send (or phases.length when all sent)
	// - completedPhaseIdx: index of the phase whose output should be written on current settle
	let initialSettled = false;
	let nextPhaseIdx = 0;
	let completedPhaseIdx = 0;
	const phases = meta.phases;

	function buildSummary(): string {
		const base = lastAssistantText || "Task completed.";
		const tools =
			toolsUsed.size > 0 ? ` Tools used: ${[...toolsUsed].sort().join(", ")} (${toolCallCount} calls).` : "";
		return `${base}${tools}`;
	}

	function exitWithSuccess(): void {
		writeOutput({
			taskKey: meta.taskKey,
			agenticdocRoot: meta.agenticdocRoot,
			exitCode: 0,
			summary: buildSummary(),
			changedFiles: [],
			verificationSteps: "See task output for details.",
			exitReason: `Agent settled after ${toolCallCount} tool call(s).`,
		});
		outputWritten = true;
		process.exit(0);
	}

	pi.on("agent_settled", () => {
		clearTimeout(watchdog);
		try {
			if (!initialSettled) {
				initialSettled = true;
				// Initial task prompt (from pi -p) has settled
				if (phases && phases.length > 0) {
					// Send first phase prompt
					pi.sendUserMessage(phases[0].prompt);
					nextPhaseIdx = 1;
					return;
				}
				// No phases — write output and exit
				exitWithSuccess();
				return;
			}

			// A phase just completed: write its output file and goal-check trace
			if (phases) {
				const phaseIndex = completedPhaseIdx;
				writePhaseFile(
					meta.taskKey,
					meta.agenticdocRoot,
					phaseIndex,
					lastAssistantText || `Phase ${phaseIndex + 1} complete`,
				);
				appendGoalCheck(meta.taskKey, meta.agenticdocRoot, phaseIndex + 1, goalMtime(meta.agenticdocRoot));
				completedPhaseIdx++;

				if (nextPhaseIdx < phases.length) {
					// More phases — send next prompt
					pi.sendUserMessage(phases[nextPhaseIdx].prompt);
					nextPhaseIdx++;
					return;
				}
			}

			// All phases done (or no phases after initial settle)
			exitWithSuccess();
		} catch (err) {
			writeOutput({
				taskKey: meta.taskKey,
				agenticdocRoot: meta.agenticdocRoot,
				exitCode: 1,
				summary: "Task failed during output writing.",
				exitReason: String(err),
			});
			outputWritten = true;
			process.exit(1);
		}
	});
}
