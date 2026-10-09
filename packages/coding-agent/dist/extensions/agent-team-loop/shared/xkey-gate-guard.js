import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
/**
 * XKEY gate-dir write guard (xkey-repair-mechanism D-008 "observable
 * refusal", AC-004).
 *
 * Why: a gate is the human-answer channel. `gates.py` treats the file as the
 * source of truth and a manual edit as a legal answer, so a permission model
 * that only narrows the /autopilot gate command (D-008 a) cannot stop an
 * agent from writing the gate file directly and silently "answering" it.
 * D-008 therefore pairs the entry narrowing with a tool-layer block plus a
 * truth-disclosure (the refusal, not a cryptographic proof, is what makes
 * agent answering observable).
 *
 * Widening (mw-autopilot-slot-capacity D-013 / AC-020 / AC-030): the audit
 * and the kill switch are file-driven too — `_autopilot/timeline.jsonl`,
 * `_autopilot/config.json` and `_autopilot/auto-decisions.jsonl` were outside
 * every tool-layer guard, so the audited party could append forged events or
 * flip its own switch. The guard now covers the whole `_autopilot` directory,
 * not only `gates/`.
 *
 * Rule: agent tool calls must not create, modify, move, or delete anything
 * under `<project>/.agenticdoc/_autopilot/` (the directory itself included),
 * EXCEPT the pre-existing `_autopilot/xkey/**` subtree. write/edit tool paths
 * are resolved like the tools do (relative against cwd, leading ~ expanded);
 * bash commands are scanned text-level (fail-closed, mirroring
 * protected-config.ts: a command that references the guarded directory and
 * carries any write construct is denied, even when the reference is a read
 * side — rerun the read part alone). Reads stay allowed, and this is not a
 * sandbox: an out-of-process writer with the same uid can still touch the
 * file. What the guard guarantees is that an agent cannot do it through its
 * only channel without a recorded refusal.
 *
 * Deliberately NOT blocked (xkey-repair-mechanism D-004/D-005): the
 * `_autopilot/xkey/` subtree — `evidence/**` (the proposal worker must write
 * proposals and verification artifacts), `ledger.json`, and `tickets/**` all
 * pass exactly as before. Ownership of that tree is enforced by the
 * conductor, not here, so the proposal path can never be killed by a
 * guard-side mistake. The boundary is a path boundary, so `_autopilotX` /
 * `_autopilot-backup` lookalikes are not hit.
 *
 * Residual risk (AC-020): this is an application-layer guard, not a sandbox —
 * a same-uid out-of-band process (another shell, the Python conductor, an
 * editor) can still write these files. The guard only makes a forgery through
 * the agent tool channel leave a refusal record.
 *
 * Registered in EVERY mode (index.ts, next to registerProtectedConfigGuard /
 * registerImplementationGate) so a worker window is covered too.
 */
const IS_WIN32 = process.platform === "win32";
/** Project-root override (test hook), else process.cwd(). */
const ENV_GATE_ROOT = "MW_XKEY_GATE_ROOT";
const AGENTICDOC_DIR = ".agenticdoc";
const AUTOPILOT_DIR = "_autopilot";
/** The pre-existing agent-writable subtree left open by the widening
 * (xkey-repair-mechanism D-004/D-005): `_autopilot/xkey/**`. */
const XKEY_DIR = "xkey";
/** Project-relative fragment shared by every spelling of the guarded
 * directory (relative, absolute, and backslash Windows forms after
 * normalization). */
const AUTOPILOT_DIR_FRAGMENT = `${AGENTICDOC_DIR}/${AUTOPILOT_DIR}`;
const GUARD_EXPLANATION = "Autopilot state (.agenticdoc/_autopilot/**) is the conductor's audit and control channel: gates/** are " +
    "answered only by a human (via the /autopilot gate console or by editing the file from outside the agent), " +
    "and timeline.jsonl / config.json / auto-decisions.jsonl are written only by the conductor. An agent tool " +
    "call must not write them. To propose a change, write " +
    ".agenticdoc/_autopilot/xkey/evidence/<request_id>/proposal.md instead - the conductor validates proposals " +
    "and applies them; ledger.json and tickets/ stay with the conductor. Reads remain allowed.";
function fold(p) {
    return IS_WIN32 ? p.toLowerCase() : p;
}
function toForwardSlashes(p) {
    return p.replaceAll("\\", "/");
}
function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
/** Fragment boundary: the match must not continue into a word character or
 * dash (`.../_autopilot` yes, `.../_autopilot-backup` / `.../_autopilotX`
 * no). */
function boundary() {
    return "(?![\\w-])";
}
/** The guarded-directory fragment: boundary-checked AND not the xkey subtree
 * (`_autopilot/xkey` stays writable, `_autopilot/xkeyX` does not). */
function guardedFragmentPattern(fragment) {
    return `${escapeRegExp(fragment)}${boundary()}(?!/${XKEY_DIR}${boundary()})`;
}
/** Is the guarded (non-xkey) directory fragment present in scan text? */
function guardedFragmentPresent(scan, fragment) {
    return new RegExp(guardedFragmentPattern(fragment)).test(scan);
}
/** Tilde expansion only (mirrors core normalizePath's tilde branch): `~` and
 * `~/x` fold onto the home dir; everything else is returned unchanged —
 * relative paths stay relative so callers resolve them against THEIR base. */
function expandTildePath(p) {
    if (p === "~")
        return os.homedir();
    if (p.startsWith("~/") || p.startsWith("~\\")) {
        return path.join(os.homedir(), p.slice(2));
    }
    return p;
}
/** Resolve the project root the gate directory is anchored against: the
 * MW_XKEY_GATE_ROOT override (tilde-expanded, resolved) wins, else the
 * process cwd (PM and worker windows both run with the project as cwd).
 * env injectable for tests. */
export function resolveXkeyGateRoot(env = process.env) {
    const raw = env[ENV_GATE_ROOT];
    if (typeof raw === "string" && raw !== "") {
        return path.resolve(expandTildePath(raw));
    }
    return process.cwd();
}
/** The project's guarded directory: `<root>/.agenticdoc/_autopilot`. */
export function xkeyGuardedDir(root) {
    return path.join(root, AGENTICDOC_DIR, AUTOPILOT_DIR);
}
/** The pre-existing agent-writable xkey subtree:
 * `<root>/.agenticdoc/_autopilot/xkey` (xkey-repair-mechanism D-004/D-005). */
export function xkeySubtreeDir(root) {
    return path.join(xkeyGuardedDir(root), XKEY_DIR);
}
/** Is `child` the same as `parent` or nested under it (folded, separator
 * aware — `/gates` matches `/gates/x.md` but not `/gates-backup`)? */
function isUnder(parent, child) {
    const p = fold(path.normalize(parent));
    const c = fold(path.normalize(child));
    if (c === p)
        return true;
    const prefix = p.endsWith(path.sep) ? p : p + path.sep;
    return c.startsWith(prefix);
}
/** Does a write/edit tool path target the guarded `_autopilot` directory
 * (outside the xkey subtree)? Pure: resolves the path like the tools do
 * (cwd-relative, ~ expanded, folded) and also matches an absolute spelling
 * of any project's `_autopilot` directory, so a write aimed at a different
 * project is still refused. */
export function isXkeyGatePath(root, rawPath, cwd = process.cwd()) {
    if (typeof rawPath !== "string" || rawPath === "")
        return false;
    const target = path.resolve(cwd, expandTildePath(rawPath));
    if (isUnder(xkeyGuardedDir(root), target) && !isUnder(xkeySubtreeDir(root), target))
        return true;
    return guardedFragmentPresent(toForwardSlashes(fold(target)), AUTOPILOT_DIR_FRAGMENT);
}
/** Shell/PowerShell write verbs (word-bounded so prose does not fire; the
 * dashed PowerShell cmdlets are matched as plain substrings). Mirrors
 * protected-config.ts. */
const WRITE_VERB_RE = /\b(rm|rmdir|rd|del|erase|mv|move|ren|rename|cp|copy|rsync|install|dd|tee|shred|truncate|touch|chmod|chown|ln)\b/i;
const POWERSHELL_WRITE_RE = /\b(remove-item|move-item|copy-item|rename-item|new-item|set-content|add-content|clear-content|out-file)\b/i;
const SED_IN_PLACE_RE = /\bsed\b[^\n;&|]*(?:\s-i(?:\.\w+)?\b|--in-place\b)/i;
const FIND_WRITE_RE = /\bfind\b[^\n;&|]*(\s-delete\b|\s-exec\b|\s-execdir\b)/i;
/** Redirects (`>`, `>>`, `2>`) with a capture of the target token. */
const REDIRECT_RE = /(?:^|[\s;&|(])\d?>{1,2}\s*("[^"]*"|'[^']*'|[^\s;&|>]+)/g;
/** Inline code execution: `python -c`, `node -e`, `node --eval`, or a
 * heredoc/stdin pipe into python/node. */
const INLINE_CODE_RE = /\b(python3?|node)\b[^\n;&|]*(\s-c\b|\s-e\b|\s--eval\b|<<)/i;
/** Write-mode markers that make inline code a gate-write risk. */
const INLINE_WRITE_MARKER_RE = /(['"][wa]['"]|writefile|write_file|unlink|rmsync|rmtree|os\.remove|os\.rename|shutil\.(move|copy|copyfile)|truncate\(|appendfile|open\([^)]*,\s*['"][wa]['"])/i;
/** Decision for one bash tool command: fail-closed — a guarded `_autopilot`
 * reference (outside the xkey subtree) plus any write construct is denied,
 * redirect targets are checked separately (a redirect to an unprotected path
 * with a guarded-side read stays allowed). Text-level heuristic mirroring
 * protected-config.ts, not a sandbox. */
export function checkXkeyGateBashCommand(root, command) {
    if (typeof command !== "string" || command === "")
        return { prohibited: false };
    const scan = toForwardSlashes(fold(command));
    const refs = [];
    if (guardedFragmentPresent(scan, AUTOPILOT_DIR_FRAGMENT))
        refs.push(AUTOPILOT_DIR_FRAGMENT);
    const dirFrag = toForwardSlashes(fold(path.normalize(xkeyGuardedDir(root))));
    if (dirFrag !== AUTOPILOT_DIR_FRAGMENT && guardedFragmentPresent(scan, dirFrag))
        refs.push(dirFrag);
    if (refs.length === 0)
        return { prohibited: false };
    const constructs = [];
    if (WRITE_VERB_RE.test(scan))
        constructs.push("write verb");
    if (POWERSHELL_WRITE_RE.test(scan))
        constructs.push("powershell write cmdlet");
    if (SED_IN_PLACE_RE.test(scan))
        constructs.push("sed -i");
    if (FIND_WRITE_RE.test(scan))
        constructs.push("find -delete/-exec");
    if (INLINE_CODE_RE.test(scan) && INLINE_WRITE_MARKER_RE.test(scan))
        constructs.push("inline code write");
    for (const m of scan.matchAll(REDIRECT_RE)) {
        const target = (m[1] ?? "").replace(/^["']|["']$/g, "");
        if (target !== "" && guardedFragmentPresent(target, AUTOPILOT_DIR_FRAGMENT))
            constructs.push("redirect target");
    }
    if (constructs.length === 0)
        return { prohibited: false };
    return {
        prohibited: true,
        reason: `xkey-gate-guard: blocked a bash command referencing the autopilot directory (${refs.join(", ")}) ` +
            `with a write construct (${constructs.join(", ")}). ${GUARD_EXPLANATION}`,
    };
}
/** Worker-mode visibility: append one [XKEY_GATE] line to the task's
 * trace.log (dirname of PI_WORKER_TASK — the same file the PM watch reads
 * live) so a refused worker shows up immediately. Best-effort: a failure
 * here must never break the block itself. taskPathEnv injectable for tests. */
export function recordXkeyGateBlockTrace(toolName, detail, taskPathEnv = process.env.PI_WORKER_TASK) {
    if (!taskPathEnv)
        return;
    try {
        const dir = path.dirname(path.resolve(taskPathEnv));
        fs.mkdirSync(dir, { recursive: true });
        const first = detail.split("\n")[0] ?? "";
        fs.appendFileSync(path.join(dir, "trace.log"), `[XKEY_GATE] ${new Date().toISOString()} blocked tool=${toolName} target=${first}\n`, "utf8");
    }
    catch {
        // best-effort diagnostic — the block itself already happened
    }
}
/** Register the tool_call autopilot block: write/edit paths and bash commands
 * are checked against `.agenticdoc/_autopilot/**` (minus the xkey subtree);
 * everything else (including all reads and the xkey evidence/ledger/tickets
 * tree) passes through untouched. Runs in every mode (PM, worker,
 * interactive). */
export function registerXkeyGateGuard(pi) {
    const root = resolveXkeyGateRoot();
    pi.on("tool_call", (event) => {
        if (event.toolName === "write" || event.toolName === "edit") {
            const rawPath = event.input.path;
            if (typeof rawPath === "string" && rawPath !== "" && isXkeyGatePath(root, rawPath)) {
                recordXkeyGateBlockTrace(event.toolName, rawPath);
                return {
                    block: true,
                    reason: `xkey-gate-guard: blocked ${event.toolName} of ${rawPath}. ${GUARD_EXPLANATION}`,
                };
            }
            return undefined;
        }
        if (event.toolName === "bash") {
            const command = event.input.command;
            if (typeof command === "string" && command !== "") {
                const verdict = checkXkeyGateBashCommand(root, command);
                if (verdict.prohibited) {
                    recordXkeyGateBlockTrace(event.toolName, command);
                    return { block: true, reason: verdict.reason };
                }
            }
            return undefined;
        }
        return undefined;
    });
}
//# sourceMappingURL=xkey-gate-guard.js.map