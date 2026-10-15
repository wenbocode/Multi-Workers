/**
 * worker/worker-file-tool.ts — the narrow write channel for worker roles whose
 * allowlist has no `write`/`edit` (mw-worker-progress-persist T-2, design
 * D-101/D-102/D-109, §4.1; mw-worker-output-contract W1 thin-adapter rewrite).
 *
 * Since W1 this file owns no write-surface judgement: `shared/write-surface.ts`
 * is the single predicate (`judgeWriteTarget`) and the single basename
 * whitelist (`WORKER_FILE_NAME_RE` / `isAllowedWorkerFileName`), re-exported
 * here so the historical importers and tests keep their paths. The adapter only
 * (a) derives the path anchors it needs from `taskDir`, and (b) loads the
 * task's `write_scope:` narrowing once at registration.
 *
 * Two accepted faces (design §3.2):
 * - task-dir basenames: `progress.md`, `report.md`, `report[-.]<slug>.md`;
 * - `<key>/evidence/**` on both bases: project-root relative
 *   (`.agenticdoc/<key>/evidence/…`) and keyDir relative (`evidence/…`), no
 *   extension restriction.
 * Every other path is rejected by the shared predicate, fail-closed. Rejection
 * still happens before any `fs.*` call: no directory is created, no file is
 * created or truncated (P-003).
 *
 * Failure shape (D-109): `execute` throws `Error`. `AgentToolResult`
 * (`packages/agent/src/types.ts:355-368`) has no `isError` field, so a returned
 * `{isError:true}` would be ignored; only a throw reaches `agent-loop.ts`'
 * catch and flips `tool_execution_end.event.isError`, which is what makes
 * `[TOOL_ERR]` appear (`worker-mode.ts:786-790`).
 *
 * `mode` defaults to `"append"` inside `execute`: TypeBox `Value.Convert` does
 * not apply schema `default`. The 64 KiB cap is enforced on UTF-8 bytes here
 * (`Buffer.byteLength`), because the schema `maxLength` counts UTF-16 code
 * units and would let multi-byte content through.
 */
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { type WriteSurfaceSeed } from "../shared/write-surface.ts";
export { isAllowedWorkerFileName as isAllowedWorkerFile, WORKER_FILE_NAME_RE, WORKER_FILE_PATH_RE, } from "../shared/write-surface.ts";
/** Tool name registered with pi (D-101). */
export declare const WORKER_FILE_TOOL = "worker_file";
/** Maximum accepted content size, in UTF-8 bytes (D-101; not code units). */
export declare const WORKER_FILE_MAX_BYTES: number;
/** Append (progress note) or whole-file write (report). */
export type WorkerFileMode = "append" | "write";
/** Resolved runtime surface for one worker task: derived path anchors plus the
 * task's declared `write_scope:` narrowing (undefined = header absent). */
export type WorkerFileSurface = WriteSurfaceSeed;
/** Derive the runtime write-surface context from `taskDir`, loading the
 * `write_scope:` header from `<taskDir>/task.md` once (best-effort; an
 * unreadable/absent task.md means "no declaration" = the default face). */
export declare function resolveWorkerFileSurface(taskDir: string): WorkerFileSurface;
/**
 * Write `content` into the worker's own surface. Rejects fail-closed before
 * touching the filesystem: shared predicate, then the basename channel check,
 * then the UTF-8 byte cap, then `mkdirSync` + write.
 */
export declare function writeWorkerFile(taskDir: string, file: string, content: string, mode: WorkerFileMode, surface?: WorkerFileSurface): {
    ok: true;
    path: string;
    bytes: number;
} | {
    ok: false;
    reason: string;
};
/** Register the narrow write tool for a writeless worker role (D-109). */
export declare function registerWorkerFileTool(pi: ExtensionAPI, taskDir: string): void;
//# sourceMappingURL=worker-file-tool.d.ts.map