import * as fs from "node:fs";
import * as path from "node:path";

export interface TaskPhase {
	name: string;
	prompt: string;
}

export interface PhaseContext {
	taskKey: string;
	agenticdocRoot: string;
}

export interface PhaseResult {
	phaseIndex: number;
	summary: string;
	goalMtime: number;
}

export function goalMtime(agenticdocRoot: string): number {
	const goalPath = path.join(agenticdocRoot, "goal.md");
	try {
		return fs.statSync(goalPath).mtimeMs;
	} catch {
		return 0;
	}
}

export function writePhaseFile(taskKey: string, agenticdocRoot: string, phaseIndex: number, summary: string): void {
	const progressDir = path.join(agenticdocRoot, taskKey, "progress");
	fs.mkdirSync(progressDir, { recursive: true });
	const content = `# Phase ${phaseIndex + 1}\n\n${summary || "(phase complete)"}\n`;
	fs.writeFileSync(path.join(progressDir, `phase-${phaseIndex + 1}.md`), content, "utf8");
}
