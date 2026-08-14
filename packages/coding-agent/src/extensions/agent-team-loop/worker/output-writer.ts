import * as fs from "node:fs";
import * as path from "node:path";

export interface WriteOutputOpts {
	taskKey: string;
	agenticdocRoot: string;
	exitCode: 0 | 1 | 2 | 130;
	summary: string;
	changedFiles?: string[];
	verificationSteps?: string;
	questions?: string;
	exitReason?: string;
}

function outputDir(taskKey: string, agenticdocRoot: string): string {
	const resolved = path.resolve(agenticdocRoot, taskKey);
	const root = path.resolve(agenticdocRoot);
	if (!resolved.startsWith(`${root}${path.sep}`) && resolved !== root) {
		throw new Error(`Invalid taskKey: path traversal detected in "${taskKey}"`);
	}
	return resolved;
}

export function writeOutput(opts: WriteOutputOpts): void {
	const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });

	const outputPath = path.join(dir, "output.md");

	const sections: string[] = [];
	sections.push(`## Summary\n\n${opts.summary || "(no summary)"}`);

	if (opts.exitCode === 0) {
		const files = opts.changedFiles?.join("\n") ?? "(none)";
		sections.push(`## Changed Files\n\n${files}`);
		sections.push(`## Verification Steps\n\n${opts.verificationSteps || "(none)"}`);
		sections.push(`## Exit Reason\n\n${opts.exitReason || "Task completed successfully."}`);
	} else if (opts.exitCode === 1) {
		sections.push(`## Exit Reason\n\n${opts.exitReason || "Task failed."}`);
	} else if (opts.exitCode === 2) {
		sections.push(`## Questions\n\n${opts.questions || "(no questions provided)"}`);
	} else if (opts.exitCode === 130) {
		sections.push(`## Exit Reason\n\nTask was cancelled (exit 130).`);
	}

	fs.writeFileSync(outputPath, `${sections.join("\n\n")}\n`, "utf8");
}

export function appendTrace(taskKey: string, agenticdocRoot: string, line: string): void {
	const dir = outputDir(taskKey, agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });
	const tracePath = path.join(dir, "trace.log");
	const ts = new Date().toISOString();
	fs.appendFileSync(tracePath, `[FLOW] ${ts} ${line}\n`, "utf8");
}

export function appendGoalCheck(taskKey: string, agenticdocRoot: string, phaseNum: number, goalMtimeMs: number): void {
	const dir = outputDir(taskKey, agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });
	const tracePath = path.join(dir, "trace.log");
	fs.appendFileSync(tracePath, `[GOAL_CHECK] phase=${phaseNum} goal_mtime=${goalMtimeMs}\n`, "utf8");
}
