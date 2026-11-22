import * as fs from "node:fs";
import * as path from "node:path";
import { atomicWriteJson } from "./local-selection-store.ts";
import { readRunState } from "./run-store.ts";

export const RUN_PROGRESS_FILE = "run-progress.json";
export const PROGRESS_STALE_MS = 10 * 60_000;

export interface WorkerMilestone {
	completed: { acceptance: string; evidence: string }[];
	current: string;
	remaining: string;
	blocker: string;
	next: string;
	eta?: string;
}

export interface WorkerActivity {
	at: string;
	source: string;
	tools: { name: string; started_at: string; last_activity_at: string }[];
}

interface RunProgress {
	run_id: string;
	milestone?: WorkerMilestone & { at: string };
	activity?: WorkerActivity;
}

function readSnapshot(taskDir: string): RunProgress | undefined {
	try {
		const file = path.join(taskDir, RUN_PROGRESS_FILE);
		const stat = fs.lstatSync(file);
		if (!stat.isFile() || stat.size > 64 * 1024) return undefined;
		const data: RunProgress = JSON.parse(fs.readFileSync(file, "utf8"));
		if (typeof data?.run_id !== "string") return undefined;
		if (
			data.activity &&
			(!Array.isArray(data.activity.tools) ||
				typeof data.activity.at !== "string" ||
				data.activity.tools.some(
					(tool) =>
						!tool ||
						typeof tool.name !== "string" ||
						typeof tool.last_activity_at !== "string" ||
						typeof tool.started_at !== "string",
				))
		)
			return undefined;
		if (data.milestone && (typeof data.milestone.at !== "string" || !Array.isArray(data.milestone.completed))) {
			return undefined;
		}
		return data;
	} catch {
		return undefined;
	}
}

export function readRunProgress(taskDir: string, runId: string, now = Date.now()) {
	const snapshot = readSnapshot(taskDir);
	if (!snapshot) return { status: "missing" as const };
	if (snapshot.run_id !== runId) return { status: "other-run" as const };
	const reported = snapshot.milestone ? Date.parse(snapshot.milestone.at) : NaN;
	const status =
		!Number.isFinite(reported) || reported > now
			? "missing"
			: now - reported >= PROGRESS_STALE_MS
				? "stale"
				: "current";
	return { ...snapshot, status };
}

export function recordRunProgress(taskDir: string, runId: string, update: Omit<RunProgress, "run_id">): boolean {
	const run = readRunState(taskDir);
	if (run?.run_id !== runId || run.status !== "running" || run.aborted) return false;
	const previous = readSnapshot(taskDir);
	atomicWriteJson(path.join(taskDir, RUN_PROGRESS_FILE), {
		...(previous?.run_id === runId ? previous : undefined),
		...update,
		run_id: runId,
	});
	return true;
}

export function milestoneEvidence(taskDir: string, reference: string): string {
	const keyDir = path.dirname(path.dirname(taskDir));
	const project = path.dirname(path.dirname(keyDir));
	if (
		!reference ||
		/[:\\\x00-\x1f]/.test(reference) ||
		reference.split("/").some((part) => !part || part === ".." || part === ".")
	) {
		throw new Error("Use a project-relative evidence file path");
	}
	const file = path.join(project, reference);
	const evidence = path.join(keyDir, "evidence");
	if (![taskDir, evidence].some((root) => file.startsWith(root + path.sep))) {
		throw new Error("Evidence must be in this worker's directory or this key's evidence directory");
	}
	if (!fs.statSync(file).isFile() || fs.realpathSync(file) !== file) {
		throw new Error("Evidence must be an existing file inside the declared evidence directory");
	}
	return reference;
}
