import * as path from "node:path";

/**
 * Shared path constants for the agent-team-loop framework.
 * Single source of truth for directory/file names that are otherwise
 * hardcoded independently in PM and Worker code.
 */

/** AgenticTask document root directory name (relative to project root). */
export const AGENTICDOC_DIR = ".agenticdoc";

/** Goal file name inside the agenticdoc root. */
export const GOAL_FILE = "goal.md";

/** Reserved owner directory for keyless ad-hoc worker tasks. */
export const SCRATCH_WORKERS_KEY = "_scratch";

/** Workers directory name inside an AgenticTask key directory. */
export const WORKERS_DIR = "workers";

/** Resolve the agenticdoc root for a project directory. */
export function agenticdocRoot(projectDir: string): string {
	return path.join(projectDir, AGENTICDOC_DIR);
}

/** Resolve the goal file path inside an agenticdoc root. */
export function goalPath(agenticdocRoot: string): string {
	return path.join(agenticdocRoot, GOAL_FILE);
}

/** Resolve the workers dir for an owner key (AgenticTask key or _scratch). */
export function workersDirFor(agenticdocRoot: string, ownerKey: string): string {
	return path.join(agenticdocRoot, ownerKey, WORKERS_DIR);
}

/** Resolve a worker task directory under an owner key. */
export function workerTaskDir(agenticdocRoot: string, ownerKey: string, taskKey: string): string {
	return path.join(workersDirFor(agenticdocRoot, ownerKey), taskKey);
}
