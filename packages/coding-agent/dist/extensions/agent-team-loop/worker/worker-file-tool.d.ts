/**
 * worker/worker-file-tool.ts — the narrow write channel for worker roles whose
 * allowlist has no `write`/`edit` (mw-worker-progress-persist T-2, design
 * D-101/D-102/D-109, §4.1).
 *
 * The tool takes a *basename* only: no path parsing exists, so `task.md`,
 * `trace.log`, `worker.log`, `output.md` and every path variant (`../x.md`,
 * `a/b.md`, `C:\abs\x.md`, `\\unc\share\x.md`) are rejected by one regex before
 * any `fs.*` call. Rejection is fail-closed: no directory is created, no file
 * is created or truncated (P-003).
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
/** Tool name registered with pi (D-101). */
export declare const WORKER_FILE_TOOL = "worker_file";
/** Maximum accepted content size, in UTF-8 bytes (D-101; not code units). */
export declare const WORKER_FILE_MAX_BYTES: number;
/**
 * Single source of truth for the writable basename set (D-102): `progress.md`,
 * `report.md` and `report[-.]<slug>.md` with a 1..41 char slug. No `g` flag
 * (no `lastIndex` state); `$` without `m` rejects a trailing newline. The
 * schema `pattern` reuses `.source` so the two layers cannot drift.
 */
export declare const WORKER_FILE_NAME_RE: RegExp;
/** Append (progress note) or whole-file write (report). */
export type WorkerFileMode = "append" | "write";
/** Basename whitelist check (authoritative guard used by `execute` too). */
export declare function isAllowedWorkerFile(name: string): boolean;
/**
 * Write `content` into `taskDir/<file>`. Rejects fail-closed before touching
 * the filesystem: name check, then UTF-8 byte cap, then `mkdirSync` + write.
 */
export declare function writeWorkerFile(taskDir: string, file: string, content: string, mode: WorkerFileMode): {
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