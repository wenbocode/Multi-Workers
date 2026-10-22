import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
/**
 * Agent tool-layer write guards for the authority-channel files (autopilot
 * state, the decision sign-off, the dp authorization table). Two
 * guards live here because they are one mechanism (mw-decision-substitution
 * D-015: same shape, same visible refusal):
 *
 *   1. `registerXkeyGateGuard` — autopilot state, `.agenticdoc/_autopilot/**`
 *      (xkey-repair-mechanism D-008 "observable refusal", AC-004).
 *   2. `registerDecisionSignoffGuard` — the decision sign-off file
 *      `evidence/review/sign-final.md` and the authorization table
 *      `.mw/decide-points.json` (mw-decision-substitution D-015, AC-009 /
 *      AC-010). See the section comment above `DECISION_SIGNOFF_FRAGMENT`.
 *
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
// ---------------------------------------------------------------------------
// Decision sign-off write guard (mw-decision-substitution D-015, AC-009 /
// AC-010) — same mechanism as the xkey guard above, different target.
//
// Why: the sign-off file `evidence/review/sign-final.md` is the authority
// channel of the decision-substitution feature (spec §7.2 / §15) and
// `.mw/decide-points.json` is the only authority source (DS-9, "唯配置论").
// Since the 2026-10-21 ruling (spec §15 AC-026) the sign-off is *written by the
// tool*, not by a person in a terminal: `mw decide sign` asks
// `dp25-signoff-conclusion` (signed_via: auto-decide) or the caller's LLM
// inference (auto-llm) and writes the file, `--auto|--disable` persist the
// `signoff` mode. What this guard still stops is FORGING that record: a raw
// write/edit/redirect/`Set-Content` of the file, or a direct table write,
// bypasses the verdict, the sha and the authority-change row.
//
// `pm/pm-orchestrator.ts` only COUNTS `[WRITE_SCOPE]` trace residuals; it does
// not intercept any write, so without this guard an agent could forge its own
// sign-off (skipping the verdict, the sha and the archive row). The guard
// therefore reuses the mechanism above: paths are fragment-matched (relative,
// absolute, and backslash spellings) and bash commands are scanned text-level,
// fail-closed. `mw decide sign` itself is NOT blocked — it is the sanctioned
// writer (the `decide dp <write verb>` regex below deliberately omits it).
//
// Deliberately NOT blocked: `evidence/review/decision-review-*.md` (the
// machine-generated advice channel — it never grants authority) and every read
// (`read`/`find`/`grep`/read-only bash), so a worker can still inspect a
// sign-off or the table.
//
// `worker_file` (QG MAJOR-4): a writeless role (research / review) has no
// `write`/`edit`, so `worker_file` is its only write channel, and that channel's
// evidence face accepts any basename under `<key>/evidence/**`
// (shared/write-surface.ts). Without the `worker_file` branch below a dispatched
// worker could write the sign-off itself, bypassing the verdict/sha the same way
// a raw write does (advance_phase.py) — the same self-signed authority the
// write/edit branch exists to prevent. The branch shares the fixed-name predicate
// `isDecisionSignoffEvidenceTarget` and leaves every other evidence product
// (`evidence/review/<other>.md`, `evidence/research/**`) writable.
//
// Residual risk (same threat model as the xkey guard): this is an
// application-layer guard, not a sandbox. A same-uid out-of-process writer can
// still touch the files; what the guard guarantees is that an agent cannot do
// it through its only tool channel without a recorded refusal.
/** The fixed sign-off file name (D-014: `content_match` cannot take a glob). */
export const DECISION_SIGNOFF_BASENAME = "sign-final.md";
/** The fixed sign-off fragment the done gate checks (project/key relative).
 *
 * The done gate only reads this `review/` landing spot, but the guard covers
 * BOTH landing spots (`<key>/evidence/sign-final.md` and
 * `<key>/evidence/review/sign-final.md`). write/edit/bash judge paths through
 * `isDecisionSignoffPath`, `worker_file` through
 * `isDecisionSignoffEvidenceTarget`, and both delegate to the SAME landing rule
 * (first `evidence` segment + tail `[]` or `["review"]`), so the four channels
 * refuse the same path and stay consistent. Keep them on that shared rule: a
 * `evidence/sign-final.md` suffix patch would re-refuse the legal
 * `evidence/research/evidence/sign-final.md` product (QG MAJOR-4 residual). */
export const DECISION_SIGNOFF_FRAGMENT = `evidence/review/${DECISION_SIGNOFF_BASENAME}`;
/** The authorization table (project-relative). */
export const DECISION_POINTS_FRAGMENT = ".mw/decide-points.json";
/** Trace marker written into a worker's trace.log (mirrors `[XKEY_GATE]`). */
export const DECISION_SIGNOFF_TRACE_MARKER = "[DECISION_SIGNOFF]";
const DECISION_GUARD_EXPLANATION = "The decision sign-off is the authority channel: evidence/review/sign-final.md is written by `mw decide sign` " +
    "(the auto-* faces from an agent session, the cli/tui faces from a human) and .mw/decide-points.json is the " +
    "only authorization source: `mw decide dp on|off|set|apply` writes its rows, and `mw decide dp refresh` may only " +
    "append missing registry rows with their registry defaults. Directly writing the file - Set-Content, a " +
    "redirect, an editor - forges that record without the verdict, so an agent tool call must not do it; call " +
    "`mw decide sign` instead (it computes counted_rows/rows_sha256 from the archive and appends the " +
    "authority-change row). Reads stay allowed.";
/** The table-writing CLI verbs (AC-010: `list/show/check/report` stay reads).
 *
 * `decide sign` is deliberately ABSENT (spec §15 AC-026): it is the sanctioned
 * writer of the sign-off file (and, with `--auto|--disable`, of the `signoff`
 * key in `.mw/decide.json`), so a bare invocation names no guarded file and is
 * never refused. A redirect into the file, a `Set-Content` or a `dp apply`
 * beside it is still caught by the refs/constructs rules below.
 *
 * `refresh` is ABSENT on purpose too (mw-signoff-per-key): it is the one-way
 * registry -> table merge, it only APPENDS the rows a registry point is missing
 * (`mw._dp_refresh` never rewrites an existing row's `enabled`/`mode`, and a
 * P0/P1 row is added disabled), so it cannot widen authority — it is how a new
 * registry point such as `dp25-signoff-conclusion` becomes a visible row in the
 * table instead of living on its registry default alone. `on|off|set|apply`
 * stay refused: those flip authority and need a human. */
const TABLE_WRITE_CLI_RE = /\bmw(?:\.py)?\b[^\n;&|]*\bdecide\s+dp\s+(?:on|off|set|apply)\b/i;
/** Does a write/edit tool path target the sign-off file or the table?
 * Pure: fragment match after normalizing backslashes (and case on win32), so
 * relative, `./`-prefixed and absolute spellings are all covered.
 *
 * Channel parity (see `DECISION_SIGNOFF_FRAGMENT`): the table and the `review/`
 * landing spot keep their fragment match, and every remaining `sign-final.md`
 * basename is delegated to the SAME landing rule `worker_file` uses — so
 * `<key>/evidence/sign-final.md` is refused here as well, while the deep
 * product `evidence/research/evidence/sign-final.md` still passes. */
export function isDecisionSignoffPath(rawPath) {
    if (typeof rawPath !== "string" || rawPath === "")
        return false;
    const scan = toForwardSlashes(fold(rawPath)).replace(/\/+$/, "");
    for (const fragment of [DECISION_SIGNOFF_FRAGMENT, DECISION_POINTS_FRAGMENT]) {
        if (scan === fragment || scan.endsWith(`/${fragment}`))
            return true;
    }
    return isDecisionSignoffEvidenceTarget(scan);
}
/** Does a `worker_file` target name the decision sign-off file (the file
 * `mw decide sign` writes)?
 *
 * `worker_file` is the only write channel of a writeless role and its paths are
 * key-dir relative (`evidence/…`) or project-root relative
 * (`.agenticdoc/<key>/evidence/…`), with no basename restriction inside the
 * evidence face — so the fixed D-014 name has to be judged on the path, not on
 * the tool. Covers both landing spots the sign-off can be written to
 * (`<key>/evidence/sign-final.md` and `<key>/evidence/review/sign-final.md`)
 * and nothing else under `evidence/**`, so normal research/review products stay
 * writable. Case folding above (win32) also catches `SIGN-FINAL.MD`, which a
 * Win32 filesystem would land on the same file. */
export function isDecisionSignoffEvidenceTarget(rawPath) {
    if (typeof rawPath !== "string" || rawPath === "")
        return false;
    const segments = toForwardSlashes(fold(rawPath))
        .replace(/\/+$/, "")
        .split("/")
        .filter((segment) => segment !== "" && segment !== ".");
    const name = segments[segments.length - 1];
    if (name === undefined || name !== DECISION_SIGNOFF_BASENAME)
        return false;
    const dir = segments.slice(0, -1);
    // The FIRST `evidence` segment is the landing position: a key-dir relative
    // path has exactly one evidence face, so any deeper `evidence` is part of a
    // product name (`evidence/research/evidence/…`), not a second face.
    const evidenceIdx = dir.indexOf("evidence");
    if (evidenceIdx < 0)
        return false;
    const tail = dir.slice(evidenceIdx + 1);
    return tail.length === 0 || (tail.length === 1 && tail[0] === "review");
}
/** Command tokens that can spell a path (quotes, `>`/`|`/`;` and parens
 * split them), used to apply the shared landing rule text-level. */
const COMMAND_TOKEN_RE = /[^\s"'`|&;<>()]+/g;
/** Does the command name the fixed sign-off name at a landing spot that the
 * fragment above misses (the `evidence/` root landing spot)?
 *
 * Deliberately segment-based via `isDecisionSignoffPath`, never an
 * `evidence/sign-final.md` suffix test: the latter would re-refuse the legal
 * `evidence/research/evidence/sign-final.md` product. */
function signoffLandingRefPresent(scan) {
    if (!scan.includes(DECISION_SIGNOFF_BASENAME))
        return false;
    for (const match of scan.matchAll(COMMAND_TOKEN_RE)) {
        if (isDecisionSignoffPath(match[0] ?? ""))
            return true;
    }
    return false;
}
/** Decision for one bash tool command (fail-closed, text-level heuristic).
 *
 * Two independent triggers: (a) a reference to a guarded path plus any write
 * construct / redirect into it, and (b) the table-writing CLI itself
 * (`mw decide dp on|off|set|apply`) even without a literal path.
 * Read-only references (`cat sign-final.md`, `mw decide dp list|show|check`), the
 * sanctioned writer (`mw decide sign`, which names no guarded file and is absent
 * from the write-verb regex) and the registry->table one-way merge
 * (`mw decide dp refresh`, append-only) pass. */
export function checkDecisionSignoffBashCommand(command) {
    if (typeof command !== "string" || command === "")
        return { prohibited: false };
    const scan = toForwardSlashes(fold(command));
    const refs = [];
    if (scan.includes(DECISION_SIGNOFF_FRAGMENT))
        refs.push(DECISION_SIGNOFF_FRAGMENT);
    if (scan.includes(DECISION_POINTS_FRAGMENT))
        refs.push(DECISION_POINTS_FRAGMENT);
    // The root landing spot carries no single fragment; judge it with the same
    // landing rule the write/edit and worker_file channels use.
    if (refs.length === 0 && signoffLandingRefPresent(scan))
        refs.push(DECISION_SIGNOFF_BASENAME);
    const cliWrite = TABLE_WRITE_CLI_RE.test(scan);
    if (refs.length === 0 && !cliWrite)
        return { prohibited: false };
    const constructs = [];
    if (cliWrite)
        constructs.push("mw decide dp write command");
    if (refs.length > 0) {
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
            if (target !== "" && isDecisionSignoffPath(target))
                constructs.push("redirect target");
        }
    }
    if (constructs.length === 0)
        return { prohibited: false };
    const where = refs.length > 0 ? ` (${refs.join(", ")})` : "";
    return {
        prohibited: true,
        reason: `decision-signoff-guard: blocked a bash command targeting the decision sign-off channel${where} ` +
            `with a write construct (${constructs.join(", ")}). ${DECISION_GUARD_EXPLANATION}`,
    };
}
/** Worker-mode visibility: append one `[DECISION_SIGNOFF]` line to the task's
 * trace.log (dirname of PI_WORKER_TASK — the file the PM watch reads live), so
 * a refused worker shows up immediately. Best-effort: a failure here must never
 * break the block itself; the env is injectable for tests. */
export function recordDecisionSignoffBlockTrace(toolName, detail, taskPathEnv = process.env.PI_WORKER_TASK) {
    if (!taskPathEnv)
        return;
    try {
        const dir = path.dirname(path.resolve(taskPathEnv));
        fs.mkdirSync(dir, { recursive: true });
        const first = detail.split("\n")[0] ?? "";
        fs.appendFileSync(path.join(dir, "trace.log"), `${DECISION_SIGNOFF_TRACE_MARKER} ${new Date().toISOString()} blocked tool=${toolName} target=${first}\n`, "utf8");
    }
    catch {
        // best-effort diagnostic — the block itself already happened
    }
}
/** Register the tool_call sign-off block: write/edit paths and bash commands
 * aiming at `evidence/review/sign-final.md` or `.mw/decide-points.json` are
 * refused, as is a `worker_file` call whose target is the fixed sign-off name
 * under the key's evidence tree (writeless-role channel); every other call
 * (including reads, `decision-review-*.md` and the rest of `evidence/**`) passes
 * through untouched. Runs in every mode (PM, worker, interactive); registered
 * in `index.ts` right after `registerXkeyGateGuard`. */
export function registerDecisionSignoffGuard(pi) {
    pi.on("tool_call", (event) => {
        if (event.toolName === "write" || event.toolName === "edit") {
            const rawPath = event.input.path;
            if (typeof rawPath === "string" && isDecisionSignoffPath(rawPath)) {
                recordDecisionSignoffBlockTrace(event.toolName, rawPath);
                return {
                    block: true,
                    reason: `decision-signoff-guard: blocked ${event.toolName} of ${rawPath}. ${DECISION_GUARD_EXPLANATION}`,
                };
            }
            return undefined;
        }
        if (event.toolName === "bash") {
            const command = event.input.command;
            if (typeof command === "string") {
                const verdict = checkDecisionSignoffBashCommand(command);
                if (verdict.prohibited) {
                    recordDecisionSignoffBlockTrace(event.toolName, command);
                    return { block: true, reason: verdict.reason };
                }
            }
            return undefined;
        }
        if (event.toolName === "worker_file") {
            const rawFile = event.input.file;
            if (typeof rawFile === "string" && isDecisionSignoffEvidenceTarget(rawFile)) {
                recordDecisionSignoffBlockTrace(event.toolName, rawFile);
                return {
                    block: true,
                    reason: `decision-signoff-guard: blocked ${event.toolName} of ${rawFile}. ${DECISION_GUARD_EXPLANATION}`,
                };
            }
            return undefined;
        }
        return undefined;
    });
}
//# sourceMappingURL=xkey-gate-guard.js.map