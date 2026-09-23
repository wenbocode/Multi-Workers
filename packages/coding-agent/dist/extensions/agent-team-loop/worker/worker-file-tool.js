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
import * as fs from "node:fs";
import * as path from "node:path";
import { Type } from "typebox";
/** Tool name registered with pi (D-101). */
export const WORKER_FILE_TOOL = "worker_file";
/** Maximum accepted content size, in UTF-8 bytes (D-101; not code units). */
export const WORKER_FILE_MAX_BYTES = 64 * 1024;
/**
 * Single source of truth for the writable basename set (D-102): `progress.md`,
 * `report.md` and `report[-.]<slug>.md` with a 1..41 char slug. No `g` flag
 * (no `lastIndex` state); `$` without `m` rejects a trailing newline. The
 * schema `pattern` reuses `.source` so the two layers cannot drift.
 */
export const WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/;
/** Basename whitelist check (authoritative guard used by `execute` too). */
export function isAllowedWorkerFile(name) {
    return WORKER_FILE_NAME_RE.test(name);
}
/**
 * Write `content` into `taskDir/<file>`. Rejects fail-closed before touching
 * the filesystem: name check, then UTF-8 byte cap, then `mkdirSync` + write.
 */
export function writeWorkerFile(taskDir, file, content, mode) {
    if (!isAllowedWorkerFile(file)) {
        return { ok: false, reason: `file name not allowed: ${JSON.stringify(file)}` };
    }
    const bytes = Buffer.byteLength(content, "utf8");
    if (bytes > WORKER_FILE_MAX_BYTES) {
        return {
            ok: false,
            reason: `content too large: ${bytes} bytes > ${WORKER_FILE_MAX_BYTES} bytes (UTF-8)`,
        };
    }
    fs.mkdirSync(taskDir, { recursive: true });
    const target = path.join(taskDir, file);
    if (mode === "append") {
        fs.appendFileSync(target, content, "utf8");
    }
    else {
        fs.writeFileSync(target, content, "utf8");
    }
    return { ok: true, path: target, bytes };
}
/** Register the narrow write tool for a writeless worker role (D-109). */
export function registerWorkerFileTool(pi, taskDir) {
    pi.registerTool({
        name: WORKER_FILE_TOOL,
        label: "worker_file",
        description: "Write a short text file into this worker's own task directory. Only progress.md, report.md " +
            "and report-<slug>.md are accepted as basenames (no directories, no separators). Use " +
            'mode="append" for progress notes and mode="write" to replace a report file. Content is ' +
            "capped at 64 KiB of UTF-8 bytes; a rejected call writes nothing.",
        promptGuidelines: [
            "Use worker_file to persist progress notes and reports when the task role has no write/edit tool; " +
                "the file must be progress.md, report.md or report-<slug>.md (basename only, slug up to 41 chars).",
            'worker_file mode defaults to "append"; use mode="write" only to replace a report file entirely.',
        ],
        parameters: Type.Object({
            file: Type.String({
                pattern: WORKER_FILE_NAME_RE.source,
                description: "Basename only: progress.md | report.md | report-<slug>.md",
            }),
            content: Type.String({ minLength: 1, description: "Text to write (max 64 KiB UTF-8)" }),
            mode: Type.Optional(Type.Union([Type.Literal("append"), Type.Literal("write")])),
        }, { additionalProperties: false }),
        execute: async (_toolCallId, params) => {
            // Schema `default` is not applied by Value.Convert — land it here.
            const mode = params.mode ?? "append";
            const r = writeWorkerFile(taskDir, params.file, params.content, mode);
            if (!r.ok) {
                throw new Error(`worker_file rejected: ${r.reason}`);
            }
            return {
                content: [{ type: "text", text: `wrote ${r.bytes} bytes to ${r.path} (${mode})` }],
                details: {},
            };
        },
    });
}
//# sourceMappingURL=worker-file-tool.js.map