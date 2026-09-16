/**
 * Shared path constants for the agent-team-loop framework.
 * Single source of truth for directory/file names that are otherwise
 * hardcoded independently in PM and Worker code.
 */
/** AgenticTask document root directory name (relative to project root). */
export declare const AGENTICDOC_DIR = ".agenticdoc";
/** Goal file name inside the agenticdoc root. */
export declare const GOAL_FILE = "goal.md";
/** Reserved owner directory for keyless ad-hoc worker tasks. */
export declare const SCRATCH_WORKERS_KEY = "_scratch";
/** Workers directory name inside an AgenticTask key directory. */
export declare const WORKERS_DIR = "workers";
/** Resolve the agenticdoc root for a project directory. */
export declare function agenticdocRoot(projectDir: string): string;
/** Resolve the goal file path inside an agenticdoc root. */
export declare function goalPath(agenticdocRoot: string): string;
/** Resolve the workers dir for an owner key (AgenticTask key or _scratch). */
export declare function workersDirFor(agenticdocRoot: string, ownerKey: string): string;
/** Resolve a worker task directory under an owner key. */
export declare function workerTaskDir(agenticdocRoot: string, ownerKey: string, taskKey: string): string;
/** Control workspace root for a worker task path (mw-dual-workspace D-001).
 *
 * <control>/.agenticdoc/{owner}/workers/{taskKey}/task.md → <control>. In
 * dual mode the worker cwd is the game root, but every coordination write
 * (trace.log / output.md / phase docs) anchors here via the PI_WORKER_TASK
 * derivation — zero env, zero target-tree files. */
export declare function controlRootFromTaskPath(taskPath: string): string;
//# sourceMappingURL=paths.d.ts.map