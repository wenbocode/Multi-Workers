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
import * as fs from "node:fs";
import * as path from "node:path";
import { Type } from "typebox";
import { appendWriteFileEvent, repoRelativePath } from "../shared/change-ledger.js";
import { deriveWriteSurfacePaths, isAllowedWorkerFileName, judgeWriteTarget, parseWriteScopeHeader, WORKER_FILE_PATH_RE, } from "../shared/write-surface.js";
// Single source of truth re-exports (DR1 §3.2: 3 importers + 2 test imports keep
// their existing paths with zero churn).
export { isAllowedWorkerFileName as isAllowedWorkerFile, WORKER_FILE_NAME_RE, WORKER_FILE_PATH_RE, } from "../shared/write-surface.js";
/** Tool name registered with pi (D-101). */
export const WORKER_FILE_TOOL = "worker_file";
/** Maximum accepted content size, in UTF-8 bytes (D-101; not code units). */
export const WORKER_FILE_MAX_BYTES = 64 * 1024;
/** Derive the runtime write-surface context from `taskDir`, loading the
 * `write_scope:` header from `<taskDir>/task.md` once (best-effort; an
 * unreadable/absent task.md means "no declaration" = the default face). */
export function resolveWorkerFileSurface(taskDir) {
    const derived = deriveWriteSurfacePaths(taskDir);
    let writeScope;
    try {
        writeScope = parseWriteScopeHeader(fs.readFileSync(path.join(derived.taskDir, "task.md"), "utf8"));
    }
    catch {
        writeScope = undefined;
    }
    return { ...derived, writeScope };
}
/**
 * Write `content` into the worker's own surface. Rejects fail-closed before
 * touching the filesystem: shared predicate, then the basename channel check,
 * then the UTF-8 byte cap, then `mkdirSync` + write.
 */
export function writeWorkerFile(taskDir, file, content, mode, surface) {
    const ctx = surface ?? resolveWorkerFileSurface(taskDir);
    const verdict = judgeWriteTarget(file, { ...ctx, taskDir });
    if (!verdict.allowed) {
        const detail = verdict.detail ?? verdict.rule ?? "outside-write-surface";
        return { ok: false, reason: `${detail}: ${JSON.stringify(file)}` };
    }
    const inEvidence = verdict.domain === "evidence";
    // The evidence face is extension-agnostic; the basename face must still be a
    // whitelisted worker_file name (this also rejects framework names such as
    // output.md that the PM prose channel allows).
    if (!inEvidence && !isAllowedWorkerFileName(file)) {
        return { ok: false, reason: `file name not allowed: ${JSON.stringify(file)}` };
    }
    const bytes = Buffer.byteLength(content, "utf8");
    if (bytes > WORKER_FILE_MAX_BYTES) {
        return {
            ok: false,
            reason: `content too large: ${bytes} bytes > ${WORKER_FILE_MAX_BYTES} bytes (UTF-8)`,
        };
    }
    const target = verdict.target;
    fs.mkdirSync(path.dirname(target), { recursive: true });
    if (mode === "append") {
        fs.appendFileSync(target, content, "utf8");
    }
    else {
        fs.writeFileSync(target, content, "utf8");
    }
    // T-05/AC-004 change history: one machine event per successful write, path
    // only (never content). After the fs call, so a rejected/failed write leaves
    // no event. Best-effort: a trace append failure never fails the write.
    appendWriteFileEvent(path.join(taskDir, "trace.log"), repoRelativePath(target));
    return { ok: true, path: target, bytes };
}
/** Register the narrow write tool for a writeless worker role (D-109). */
export function registerWorkerFileTool(pi, taskDir) {
    const surface = resolveWorkerFileSurface(taskDir);
    pi.registerTool({
        name: WORKER_FILE_TOOL,
        label: "worker_file",
        description: "Your ONLY write channel when this role has no write/edit tool. Writes a short text file into " +
            "this worker's own task directory (progress.md | report.md | report-<slug>.md) or into the key's " +
            "evidence tree (<key>/evidence/** or .agenticdoc/<key>/evidence/**, no extension restriction). " +
            'Use mode="append" for progress notes and mode="write" to replace a report file. Content is ' +
            "capped at 64 KiB of UTF-8 bytes; any other path is rejected and a rejected call writes nothing.",
        promptGuidelines: [
            "worker_file is your only write channel; do not try write/edit/bash>file for artifacts. " +
                "The file must be progress.md, report.md or report-<slug>.md (basename only), or an evidence " +
                "path such as evidence/research/notes.md / .agenticdoc/<key>/evidence/research/notes.md.",
            'worker_file mode defaults to "append"; use mode="write" only to replace a report file entirely.',
            "A declared write_scope: narrows this channel; paths outside it are rejected fail-closed.",
        ],
        parameters: Type.Object({
            file: Type.String({
                pattern: WORKER_FILE_PATH_RE.source,
                description: "progress.md | report.md | report-<slug>.md | evidence/** | .agenticdoc/<key>/evidence/**",
            }),
            content: Type.String({ minLength: 1, description: "Text to write (max 64 KiB UTF-8)" }),
            mode: Type.Optional(Type.Union([Type.Literal("append"), Type.Literal("write")])),
        }, { additionalProperties: false }),
        execute: async (_toolCallId, params) => {
            // Schema `default` is not applied by Value.Convert — land it here.
            const mode = params.mode ?? "append";
            const r = writeWorkerFile(taskDir, params.file, params.content, mode, surface);
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