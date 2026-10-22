import * as fs from "node:fs";
import * as path from "node:path";
import { killTrackedDetachedChildren } from "../../../utils/shell.js";
import { DP2_NARROW_MARKER, DP2_STEER_FILE, DP2_STEER_REQUEST_HEADER, recordDispatchAlarm, } from "../pm/pm-orchestrator.js";
import { canonicalStateBytes, readDecidePolicy, runDecideMw, } from "../pm/triage-client.js";
import { assertStateMatchesRegistry, WRITE_SURFACE_MARKER, WRITE_SURFACE_MARKER_END } from "../pm/ui-bridge.js";
import { Breaker, Budget } from "../rag/budget.js";
import { requiredFor } from "../rag/config.js";
import { appendEvidence } from "../rag/evidence.js";
import { researchDocEvidence, scanCitations, validateResearchDoc } from "../rag/research-doc.js";
import { applyRagTools, RAG_CHAT_BUDGET_HEADER, RAG_TIME_BUDGET_HEADER, registerRagTools, } from "../rag/tools.js";
import { appendUnresolvedWriteEvent, appendWriteFileEvent, parseWriteFileEvents, repoRelativePath, } from "../shared/change-ledger.js";
import { resolveDecidePolicy } from "../shared/decide-policy.js";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.js";
import { findNonEmptyReport, hasDeliverableEvidence } from "../shared/deliverable-evidence.js";
import { claimBudgetCaps, DISPATCH_TYPE_VOCABULARY, parseClaimsBlock } from "../shared/dispatch-card.js";
import { roleForTaskType } from "../shared/dispatch-models.js";
import { formatHeartbeatAge, HEARTBEAT_INTERVAL_MS } from "../shared/heartbeat.js";
import { controlRootFromTaskPath } from "../shared/paths.js";
import { MW_RUN_DETACHED_TOOL, registerRunDetachedTool } from "../shared/run-detached.js";
import { collectArtifacts, isTerminalRunStatus, newRunId, parseSupersedes, RUN_SCHEMA, runMarker, writeRunState, } from "../shared/run-store.js";
import { findTypeEscalation, readTaskType, scanBodyTypeLines } from "../shared/task-frontmatter.js";
import { parseWriteFace, parseWriteFaceEntries, writeFacesOverlap, } from "../shared/write-face.js";
import { evidenceDirOf, matchesWriteScopeEntry, parseWriteScopeHeader, resolveOwnWriteTarget, resolveWriteSurfacePaths, } from "../shared/write-surface.js";
import { claimCoverage, isMechanicalSection, parseVerdictTable } from "./output-sections.js";
import { agentProductText, appendCheckpoint, appendEnd, appendError, appendGoalCheck, appendHeartbeat, appendMechanicalContextSources, appendModel, appendPhase, appendProgressLine, appendStart, appendTimeout, appendTool, appendToolError, appendTrace, currentRecoveryMissing, formatMachineCheckpoint, hasReportProduct, readTerminalGaps, writeOutput, } from "./output-writer.js";
import { goalMtime, writePhaseFile } from "./phase-runner.js";
import { applyParentRootUnion, checkReadScopeCall, isSameOrUnder, normalizeForCompare, parentRootFromTaskContent, readScopeConfigFromMeta, } from "./read-scope.js";
import { registerWorkerFileTool, WORKER_FILE_TOOL } from "./worker-file-tool.js";
// ── Tool allowlists by task type ─────────────────────────────────────────────
const TOOL_ALLOWLISTS = {
    coding: ["read", "write", "edit", "bash", "find", "grep", "ls"],
    review: ["read", "find", "grep", "ls"],
    research: ["read", "find", "grep", "ls", "bash"],
    // Autopilot typed dispatches (D-107/VC-023): per-type tool sets must stay
    // EXACTLY equal to the Python-side REGISTRY in
    // packages/multi-workers/autopilot/dispatch.py (entry order included) —
    // the T-17 L0 parity test locks that equality. "fallback" is the internal
    // default bucket, not a dispatchable type.
    "roadmap-writer": ["read", "write", "edit", "find", "grep", "ls"],
    "phase-writer": ["read", "write", "edit", "bash", "find", "grep", "ls"],
    verifier: ["read", "find", "grep", "ls"],
    reviewer: ["read", "find", "grep", "ls"],
    repair: ["read", "write", "edit", "bash", "find", "grep", "ls"],
    // RAG research bucket (mw-rag-integration D-011): renders rag_chat, the only
    // type allowed to call it. PM/`/worker`-dispatched only — the conductor
    // refuses it on the Python side (conductor_dispatchable=False).
    "rag-research": [
        "read",
        "find",
        "grep",
        "ls",
        "rag_search",
        "rag_symbol",
        "rag_graph",
        "rag_impact",
        "rag_sources",
        "rag_feedback",
        "rag_chat",
    ],
    // Vision bucket (mw-vision-role D-001): full coding set, same order as the
    // Python-side REGISTRY entry in autopilot/dispatch.py.
    vision: ["read", "write", "edit", "bash", "find", "grep", "ls"],
    // Decision-book writer (mw-decision-substitution W8, renamed W10): read-only
    // tools plus a narrowed `bash` (see `decisionBashBlockReason` below). Same
    // order as the Python-side REGISTRY entry in autopilot/dispatch.py. W10:
    // the type value is `decide_prepare` (was `decision`; no alias kept).
    decide_prepare: ["read", "find", "grep", "ls", "bash"],
    fallback: ["read", "write", "edit", "bash", "find", "grep", "ls"],
};
/** Is this a dispatchable type with an explicit allowlist entry? "fallback"
 * is the internal default bucket (D-107: a `type: fallback` task with
 * origin: conductor must fail closed, not resolve to the full set). */
function isRegisteredType(taskType) {
    return taskType !== "fallback" && taskType in TOOL_ALLOWLISTS;
}
/**
 * P-08 single source for the worker runtime's recognized vocabulary. This is
 * the SAME constant the tool-layer envelope judge consults
 * (`shared/dispatch-card.ts::DISPATCH_TYPE_VOCABULARY`), re-exported here so
 * the runtime table (`TOOL_ALLOWLISTS`, plus the internal `default`/`fallback`
 * buckets) and the gate can be locked together by
 * `test/suite/dispatch-recovery-terminal.test.ts` instead of drifting. It is
 * deliberately NOT `isRegisteredType`: that conductor fail-closed predicate
 * must keep matching the Python REGISTRY entry-for-entry (T-17 L0).
 */
export const WORKER_TYPE_VOCABULARY = DISPATCH_TYPE_VOCABULARY;
/** The worker runtime's registered type keys (the tool-table entries, minus the
 * internal `fallback` bucket). Exported only so
 * `test/suite/dispatch-recovery-terminal.test.ts` can lock the subset relation
 * against {@link WORKER_TYPE_VOCABULARY} (P-08 single source). */
export const REGISTERED_WORKER_TYPES = Object.keys(TOOL_ALLOWLISTS).filter((type) => type !== "fallback");
export function toolsForType(taskType) {
    return TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback ?? [];
}
/** `toolsForType` plus the narrow write channel for roles with no write/edit
 * tool (D-104/D-106). The allowlist table and `toolsForType` stay byte for
 * byte unchanged (Python parity lock, direct test imports); the writeless
 * extra lives only here. Write roles get the base array untouched, read-only
 * roles get a copy with `worker_file` appended. */
export function activeToolsForType(taskType) {
    const base = toolsForType(taskType);
    const tools = base.includes("write") ? base : [...base, WORKER_FILE_TOOL];
    // mw_run_detached is a spawn surface: only shell roles (base carries
    // `bash`) get it. Read-only roles stay without it so the AC-005b bash
    // write-surface guard cannot be bypassed (design D-005). Never goes into
    // TOOL_ALLOWLISTS (T-17 parity lock).
    return tools.includes("bash") ? [...tools, MW_RUN_DETACHED_TOOL] : tools;
}
/** Is this a role whose tool set carries `bash` (contract C3)? */
export function isShellRole(taskType) {
    return activeToolsForType(taskType).includes("bash");
}
/** Is this a role with no write/edit tool (contract C3)? Such a role writes
 * only through the narrow `worker_file` channel, so bash is the one structural
 * hole left for the AC-005b write-surface guard. */
export function isWritelessRole(taskType) {
    const tools = activeToolsForType(taskType);
    return !tools.includes("write") && !tools.includes("edit");
}
/** Does this role carry a `write`/`edit` tool (D-115 rule 6)? The runtime
 * write-surface guard must cover these roles on the `write`/`edit` channel even
 * when they have no `bash` (`roadmap-writer` was unguarded before D-115). */
export function hasWriteTools(taskType) {
    const tools = activeToolsForType(taskType);
    return tools.includes("write") || tools.includes("edit");
}
// ── decision worker type (mw-decision-substitution W8, renamed W10) ──────────
//
// W10: the dispatch type value is `decide_prepare` (was `decision`); no alias
// is kept, so `type: decision` is now an unknown type.
//
// A `decide_prepare` worker writes ONE decision book: scaffold it, fill every field
// from real evidence, pass `mw decide book check`, and hand the book back. It
// never edits code and never sends the book: the send (`decide run|ask --book`)
// is the PM's call unless the card explicitly says `allow-send: yes`.
//
// Three runtime pieces live here:
//   1. the fixed prompt (`DECISION_TYPE_PROMPT`) — injected into the system
//      prompt of every turn of a decision worker, so the contract cannot be
//      lost by compaction or by a terse card;
//   2. a read-only bash policy (`decisionBashBlockReason`) that blocks every
//      command except `mw decide book check`, `git diff|status|log`, `rg`,
//      `cat`, `ls`, `head`, `tail`, `wc` — and blocks `decide run|ask` unless
//      the card authorized the send;
//   3. a `worker_file` target policy (`decisionWorkerFilePathAllowed`) that
//      keeps the only write channel inside `<key>/evidence/books/**`.
export const DECIDE_PREPARE_TYPE = "decide_prepare";
/** Card item carrying the send authority (`yes` = the worker may send). */
export const DECISION_ALLOW_SEND_ITEM = "allow-send";
/** The one directory a decision book may be written to. */
export const DECISION_BOOK_SUBDIR = "evidence/books";
/** The fixed decision-worker prompt (card requirement 2). */
export const DECISION_TYPE_PROMPT = [
    "[mw decide_prepare worker] 你写决策本，不改代码。",
    "1. 先跑 `mw decide book new <dp> --out <key>/evidence/books/<dp>-<slug>.json`；<dp> 与 book 路径见 task.md 的「决策本参数」段。",
    "2. 按每个字段的 description 从证据里填值；`notes.evidence` 每条给 `path:line` 或命令原文。",
    "3. 最后跑 `mw decide book check <book>`；失败就继续填，直到通过。",
    "不要改阈值、不要填预期答案、不要改任何代码（packages/ 只读）。",
    "bash 只允许 `mw decide book check`、`git diff --stat`、`rg`、`cat` 这类只读命令。",
    "`allow-send: no` 时不要调用 `decide run` / `decide ask`（含 `--book`）；发送由 PM 做。",
].join("\n");
/** Does the task authorize the worker itself to send the book?
 *
 * Only an explicit `allow-send: yes` line does (`- allow-send: yes` or
 * `allow-send: yes`); every other shape — absent, `no`, garbage — is the
 * closed state (W8 requirement 4: the default is `no`). */
export function decisionAllowsSend(taskContent) {
    for (const raw of taskContent.split(/\r?\n/)) {
        const m = /^\s*(?:[-*+]\s*)?(?:\*\*)?allow-send(?:\*\*)?\s*[:：]\s*(\S+)/i.exec(raw);
        if (m)
            return m[1].trim().toLowerCase() === "yes";
    }
    return false;
}
/** Commands a decision worker may run (read-only subset, card requirement 2).
 * Order matters only for the audit message. */
const DECISION_ALLOWED_COMMANDS = [
    [/^mw\s+decide\s+book\s+check\b/, "mw decide book check"],
    [/^python\S*\s+.*\bmw\.py\s+decide\s+book\s+check\b/, "mw decide book check"],
    [/^git\s+diff\b/, "git diff"],
    [/^git\s+status\b/, "git status"],
    [/^git\s+log\b/, "git log"],
    [/^rg\b/, "rg"],
    [/^cat\b/, "cat"],
    [/^ls\b/, "ls"],
    [/^head\b/, "head"],
    [/^tail\b/, "tail"],
    [/^wc\b/, "wc"],
];
/** Shell metacharacters a read-only decision command may never carry. */
const DECISION_BASH_REDIRECT_RE = /[<>]|\btee\b|\brm\b|\bmv\b|\bcp\b|\bsed\s+-i\b|\bgit\s+(?:add|commit|checkout|reset)\b|\bpython\S*\s+-c\b/;
/** The `decide run|ask` invocations (with or without `--book`). */
const DECISION_SEND_RE = /\bdecide\s+(?:run|ask)\b/;
/** The scaffold call (`book new`), which may WRITE exactly one file: its
 * `--out` target (W8: the prompt's first step, still bounded to the books dir).
 * Without `--out` it only prints to stdout — that shape writes nothing. */
const DECISION_BOOK_NEW_RE = /^(?:mw\s+decide\s+book\s+new|python\S*\s+.*\bmw\.py\s+decide\s+book\s+new)\b/;
/** Block reason for one decision-worker bash command, or `null` when allowed.
 *
 * Splits on the shell control operators (`&&`, `||`, `;`, `|`, newline) so a
 * chained write (`rg x && rm -rf y`) cannot hide behind an allowed prefix, and
 * refuses redirections/known mutators outright (P1: for this role a false
 * block costs one retry, a miss writes outside the books dir).
 *
 * `mw decide book new` is allowed on top of the card's read-only list because
 * the prompt's FIRST step is that scaffold; its `--out` must stay inside
 * `evidence/books/**` and the no-`--out` shape only prints to stdout. */
export function decisionBashBlockReason(command, allowSend) {
    const send = DECISION_SEND_RE.exec(command);
    if (send && !allowSend) {
        return (`decision: \`decide ${send[0].split(/\s+/)[1]}\` is the PM's call — this card says ` +
            `\`allow-send: no\` (or nothing), so only \`mw decide book check\` is allowed`);
    }
    const allowed = DECISION_ALLOWED_COMMANDS.map(([, label]) => label).join(", ");
    for (const raw of command.split(/&&|\|\||[;|\n]/)) {
        const segment = raw.trim();
        if (segment === "")
            continue;
        if (DECISION_BASH_REDIRECT_RE.test(segment)) {
            return `decision: bash is read-only for this role (no redirect/mutation); allowed: ${allowed}`;
        }
        if (DECISION_BOOK_NEW_RE.test(segment)) {
            const out = /--out(?:=|\s+)(\S+)/.exec(segment);
            const target = out?.[1]?.replace(/^["']|["']$/g, "") ?? "";
            if (target !== "" && !decisionWorkerFilePathAllowed(target)) {
                return (`decision: \`book new --out\` must target ${DECISION_BOOK_SUBDIR}/** ` +
                    `(got ${JSON.stringify(target)})`);
            }
            continue;
        }
        if (send && segment.includes(send[0]) && allowSend)
            continue;
        if (!DECISION_ALLOWED_COMMANDS.some(([pattern]) => pattern.test(segment))) {
            return (`decision: bash is read-only for this role; \`${segment.split(/\s+/)[0]}\` is not allowed ` +
                `(allowed: ${allowed})`);
        }
    }
    return null;
}
/** Is this `worker_file` target inside the decision book directory?
 *
 * Accepts both spellings the tool documents: `evidence/books/<f>` (taskDir
 * relative) and `.agenticdoc/<key>/evidence/books/<f>`. Everything else — the
 * broader `<key>/evidence/**` face, `progress.md`, a source file — is refused
 * (W8 requirement 3: the write face narrows to the books dir). */
export function decisionWorkerFilePathAllowed(file) {
    const normalized = file.trim().replace(/\\/g, "/").replace(/^\.\//, "");
    if (normalized === "" || normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized)) {
        return false;
    }
    if (normalized.split("/").includes(".."))
        return false;
    return normalized.includes(`${DECISION_BOOK_SUBDIR}/`);
}
/** Checkpoint self-assessment steer text, split by role (D-104/VC-004).
 * - `hasWriteTools === true`: the pre-change wording byte for byte — the
 *   agent appends its own CKPT line to progress.md with its write tool.
 * - `hasWriteTools === false`: never tells the agent to append to a file it
 *   cannot write. The machine evidence is already on disk (framework-written),
 *   and the self-assessment goes through the narrow tool or the reply.
 * `deliverAs` stays `followUp` for both branches (decided by the caller). */
export function checkpointSteerText(opts) {
    if (opts.hasWriteTools) {
        return `[mw checkpoint] 运行 ${formatHeartbeatAge(opts.elapsedMs)}（总预算 ${formatHeartbeatAge(opts.budgetMs)}）。请立即自评收敛性，把一行追加到 ${opts.progressPath}：CKPT ${Math.round(opts.elapsedMs / 60_000)}m converging=yes|no eta≈<X>m <一句话理由>。若不收敛：立即收窄范围，优先保证已完成部分可交付，不要展开新工作。`;
    }
    return `[mw checkpoint] 运行 ${formatHeartbeatAge(opts.elapsedMs)}（总预算 ${formatHeartbeatAge(opts.budgetMs)}）。检查点机器证据（reads/writes/phases/risk）已由框架写入 ${opts.progressPath}。请立即自评收敛性：用 ${opts.narrowTool} 工具把一行自评写入该文件，或在本回复中直接给出一行 CKPT ${Math.round(opts.elapsedMs / 60_000)}m converging=yes|no eta≈<X>m <一句话理由>。若不收敛：立即收窄范围，优先保证已完成部分可交付，不要展开新工作。`;
}
// ── Watchdog budgets (GC-4 as amended 2026-09-09: activity-based hang
// detection + per-task wall budget) ─────────────────────────────────────────
/** Default wall budget. The old 30m value killed healthy tasks (OverCode
 * cpr-004/005: actively working 28s/9s before the kill); 60m covers every
 * observed successful run (7–14m) with margin for generation-heavy tasks. */
export const DEFAULT_BUDGET_MS = 60 * 60_000;
/** Default hang threshold: no activity (token deltas, tools, turns) for this
 * long while the task is unfinished means a dead API call. Conservative —
 * above the 7m legit single-generation observed on glm-5.3 (cpr-003); tighten
 * after confirming streaming deltas arrive on the timi route. */
export const DEFAULT_IDLE_MS = 10 * 60_000;
const CHECKPOINT_ANCHOR_MS = 30 * 60_000;
const CHECKPOINT_REFRESH_MS = 10 * 60_000;
const STEER_MIN_MS = 5 * 60_000;
/** Wall budget: task.md `timeout:` (minutes) > PI_WORKER_TIMEOUT_MS > default. */
export function resolveBudgetMs(timeoutMin, env) {
    if (timeoutMin !== undefined)
        return timeoutMin * 60_000;
    const envMs = Number(env);
    if (Number.isFinite(envMs) && envMs > 0)
        return envMs;
    return DEFAULT_BUDGET_MS;
}
/** Hang threshold from PI_WORKER_IDLE_MS (falling back to the default). */
export function resolveIdleMs(env) {
    const envMs = Number(env);
    if (Number.isFinite(envMs) && envMs > 0)
        return envMs;
    return DEFAULT_IDLE_MS;
}
/** Max silence allowed while a tool is in flight, before the in-flight branch
 * of the idle watchdog kills. Root cause (measured 2026-09-26, T-04/AC-005):
 * 22/24 idle kills died while a bash call was in flight with zero
 * `tool_execution_update` — bash updates are output-driven (core/tools/bash.ts),
 * so a long command that prints nothing looked like a hung worker. A tool that
 * is still running legitimately owns the activity clock, but only up to a
 * bound: a genuinely hung tool must still die (VC-006). 30m mirrors the
 * design's floor (D-016) and sits inside the 60m default wall budget, which
 * remains the outer guard. Deliberately a code constant: T-04 forbids a new
 * config key, so this is NOT wired through `_autopilot/config.json`.
 *
 * Deliberately does not change `DEFAULT_IDLE_MS` or the PI_WORKER_IDLE_MS
 * semantics: the threshold was never the root cause. */
export const DEFAULT_TOOL_IDLE_MS = 30 * 60_000;
/** Effective in-flight tool-idle bound: the configured raw idle threshold
 * (lower bound, so a tightened PI_WORKER_IDLE_MS also tightens this) vs the
 * 30m floor. */
export function resolveToolIdleMs(idleMs) {
    return Math.max(idleMs, DEFAULT_TOOL_IDLE_MS);
}
/** First convergence-checkpoint time: the 30m anchor, scaled down
 * proportionally for small budgets so smoke runs exercise the whole path. */
export function checkpointAnchorMs(budgetMs) {
    return Math.min(CHECKPOINT_ANCHOR_MS, Math.max(1_000, Math.round(budgetMs / 2)));
}
/** Deadline-steer time: budget minus min(5m, budget/4). */
export function steerAtMs(budgetMs) {
    return Math.max(1_000, budgetMs - Math.min(STEER_MIN_MS, Math.round(budgetMs / 4)));
}
/** Read-ish tools for checkpoint convergence signals. */
const READ_TOOLS = new Set(["read", "grep", "find", "ls", "glob"]);
/** Write-ish tools for checkpoint convergence signals. */
const WRITE_TOOLS = new Set(["write", "edit"]);
/** T-04/AC-009: freshness floor for a landing — one minute, so a small smoke
 * budget (anchor 60s) still has an exercisable window. */
export const LAND_FRESH_FLOOR_MS = 60_000;
/** T-04/AC-009: how recent the newest landing must be to count as "fresh"
 * (a writeless run that is still producing). `anchor/3` floored at 1m: the
 * default anchor (30m) yields 10m, exactly the checkpoint refresh cadence. */
export function landFreshMs(anchorMs) {
    return Math.max(LAND_FRESH_FLOOR_MS, Math.round(anchorMs / 3));
}
/** Machine divergence heuristic (AC-004, advisory only — the PM with the
 * fullest context judges and decides):
 * - high: past the anchor with ZERO writes — pure exploration, the cpr-007
 *   pattern (22 minutes of reads, generation never got time to land).
 * - mid: phase framework present but nothing completed past the anchor, or
 *   the same target read ≥4 times (spinning).
 * - low: writes advancing — implementation underway.
 *
 * T-04/AC-009: when the caller supplies landing signals (`landed !== undefined`,
 * writeless roles), the counts `writes`/`uniq_targets` stop being the criterion
 * (they are structurally 0 for those roles) and the ledger + disk facts decide:
 * - W2a: a non-empty product on disk ⇒ low (strongest convergence evidence;
 *   outranks a missed ledger event).
 * - W1: nothing landed at all past the anchor ⇒ high (unchanged intent).
 * - W2b: a fresh landing plus the role's own `converging=yes` note ⇒ low.
 * - W3/W4: landed-but-stale (or nothing before the anchor) — only read spin or
 *   stalled phases are mid, everything else is low. */
export function computeRisk(s) {
    if (s.landed !== undefined) {
        const stalled = s.phasesTotal > 0 && s.phasesDone === 0 && s.elapsedMs >= s.anchorMs;
        if (s.artifactPresent === true)
            return "low";
        if (s.landed === 0 && s.elapsedMs >= s.anchorMs)
            return "high";
        const fresh = s.lastLandingAgeMs !== undefined && s.lastLandingAgeMs <= landFreshMs(s.anchorMs);
        if (s.landed > 0 && fresh && s.progressDone === true)
            return "low";
        return stalled || s.repeatTop >= 4 ? "mid" : "low";
    }
    if (s.writes === 0 && s.elapsedMs >= s.anchorMs)
        return "high";
    if ((s.phasesTotal > 0 && s.phasesDone === 0 && s.elapsedMs >= s.anchorMs) || s.repeatTop >= 4)
        return "mid";
    return "low";
}
/** T-04/AC-009: the role's own completion record in progress.md — the heading
 * report shape or the `CKPT <n>m converging=yes` self-assessment line the
 * checkpoint steer asks for (`[machine]` lines are framework-written and do
 * not count). */
const PROGRESS_DONE_RE = /(^|\n)(?:##\s*完成记录|CKPT\s+\d+m\s+(?!\[machine\])(?=[^\n]*converging=yes))/;
/** Bounded read-only scan of the key's `evidence/` tree (depth ≤5, ≤500
 * entries, symlinks skipped) for a file fresher than the run start — the
 * writeless deliverable channel lives outside taskDir. Returns the newest
 * qualifying mtime, or undefined. */
function newestEvidenceMtimeMs(keyDir, startedAtMs, nowMs) {
    const maxDepth = 5;
    const maxEntries = 500;
    let visited = 0;
    let newest;
    const walk = (dir, depth) => {
        if (depth > maxDepth || visited >= maxEntries)
            return;
        let entries;
        try {
            entries = fs.readdirSync(dir, { withFileTypes: true });
        }
        catch {
            return;
        }
        for (const entry of entries) {
            if (visited >= maxEntries)
                return;
            visited++;
            const abs = path.join(dir, entry.name);
            if (entry.isSymbolicLink())
                continue;
            if (entry.isDirectory()) {
                walk(abs, depth + 1);
                continue;
            }
            if (!entry.isFile())
                continue;
            try {
                const stat = fs.statSync(abs);
                if (stat.size === 0 || stat.mtimeMs < startedAtMs)
                    continue;
                // T-12: a mtime past `nowMs` only means "just landed" (clock
                // granularity / write-read race). Clamp it to `nowMs` (age 0)
                // instead of dropping a real landing.
                const mtimeMs = stat.mtimeMs > nowMs ? nowMs : stat.mtimeMs;
                if (newest === undefined || mtimeMs > newest)
                    newest = mtimeMs;
            }
            catch {
                // Best-effort: an unreadable entry is not a landing.
            }
        }
    };
    walk(path.join(keyDir, "evidence"), 0);
    return newest;
}
/** T-04/AC-009: landing signals for a writeless run, from the SAME ledger the
 * settle judgement reads. `parseWriteFileEvents` (not the `[TOOL] worker_file`
 * lines, not a second extractor) supplies the target set, so the two views
 * cannot diverge; disk truth (non-empty artifact, surviving targets, fresh
 * evidence) is the fallback when the ledger missed an event. Read-only. */
export function collectLandingSignals(opts) {
    const targets = parseWriteFileEvents(opts.traceText);
    let newestMtimeMs;
    const touch = (mtimeMs) => {
        if (newestMtimeMs === undefined || mtimeMs > newestMtimeMs)
            newestMtimeMs = mtimeMs;
    };
    let nonProgressLanded = false;
    for (const target of targets) {
        const abs = path.isAbsolute(target) ? target : path.resolve(process.cwd(), target);
        try {
            const stat = fs.statSync(abs);
            if (!stat.isFile() || stat.size === 0)
                continue;
            // T-12: clamp a future mtime to `nowMs` (age 0) rather than
            // skipping it — it is a landing, not a stale artifact.
            touch(stat.mtimeMs > opts.nowMs ? opts.nowMs : stat.mtimeMs);
            if (path.basename(abs) !== "progress.md")
                nonProgressLanded = true;
        }
        catch {
            // Not on disk — recorded but not a surviving landing.
        }
    }
    const keyDir = path.dirname(path.dirname(opts.taskDir));
    const evidenceMtimeMs = newestEvidenceMtimeMs(keyDir, opts.startedAtMs, opts.nowMs);
    if (evidenceMtimeMs !== undefined)
        touch(evidenceMtimeMs);
    return {
        landed: targets.length,
        lastLandingAgeMs: newestMtimeMs === undefined ? undefined : Math.max(0, opts.nowMs - newestMtimeMs),
        artifactPresent: findNonEmptyReport(opts.taskDir) !== undefined || nonProgressLanded || evidenceMtimeMs !== undefined,
        progressDone: PROGRESS_DONE_RE.test(opts.progressText),
    };
}
export function writeSurfaceMarkerState(content) {
    const lines = content.split(/\r?\n/).map((line) => line.trimEnd());
    const starts = lines.filter((line) => line === WRITE_SURFACE_MARKER).length;
    const ends = lines.filter((line) => line === WRITE_SURFACE_MARKER_END).length;
    if (starts === 0 && ends === 0)
        return "absent";
    if (starts !== 1 || ends !== 1)
        return "malformed";
    return lines.indexOf(WRITE_SURFACE_MARKER) < lines.indexOf(WRITE_SURFACE_MARKER_END) ? "ok" : "malformed";
}
export function parseTaskMd(taskPath) {
    const content = fs.readFileSync(taskPath, "utf8");
    const lines = content.split("\n");
    const taskType = readTaskType(content).type ?? "default";
    let phase;
    let timeoutMin;
    let origin;
    let images;
    const phases = [];
    let currentPhase = null;
    let inPhasePrompt = false;
    let readScope;
    let inReadScopeList = false;
    let denyGlobs;
    let inDenyGlobsList = false;
    let readFileCap;
    let readByteCap;
    let ragChatBudget;
    let ragTimeBudgetS;
    let allowForeignWrite;
    for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("phase:")) {
            const v = trimmed.slice("phase:".length).trim();
            if (v)
                phase = v;
        }
        if (trimmed.startsWith("timeout:")) {
            const v = Number(trimmed.slice("timeout:".length).trim());
            if (Number.isFinite(v) && v > 0)
                timeoutMin = v;
        }
        if (trimmed.startsWith("origin:")) {
            origin = trimmed.slice("origin:".length).trim();
        }
        if (trimmed.startsWith("images:"))
            images = trimmed.slice("images:".length).trim() === "yes";
        // read_scope renders as a YAML block list (dispatch.py render_task_md):
        // `  - entry` lines after a bare `read_scope:`. Any other line ends the
        // list. `read_scope:` present-but-empty keeps the field defined — the
        // interceptor then fails closed (everything out of scope).
        if (trimmed === "read_scope:") {
            readScope = [];
            inReadScopeList = true;
        }
        else if (inReadScopeList && !inPhasePrompt) {
            if (trimmed.startsWith("- ")) {
                const item = trimmed.slice(2).trim();
                if (item)
                    readScope?.push(item);
            }
            else {
                inReadScopeList = false;
            }
        }
        // deny_globs renders like read_scope (dispatch.py render_task_md), but
        // entries are globs — dispatch quotes them (a leading `*` is a YAML
        // alias marker), so strip one pair of surrounding quotes when present.
        if (trimmed === "deny_globs:") {
            denyGlobs = [];
            inDenyGlobsList = true;
        }
        else if (inDenyGlobsList && !inPhasePrompt) {
            if (trimmed.startsWith("- ")) {
                let item = trimmed.slice(2).trim();
                if ((item.startsWith('"') && item.endsWith('"')) || (item.startsWith("'") && item.endsWith("'"))) {
                    item = item.slice(1, -1);
                }
                if (item)
                    denyGlobs?.push(item);
            }
            else {
                inDenyGlobsList = false;
            }
        }
        // write_scope is parsed by the shared single implementation
        // (`shared/write-surface.ts::parseWriteScopeHeader`, T-10) AFTER the loop, so
        // the shell guard, `parseTaskMeta` and `worker_file` cannot drift apart. The
        // gate-v2 `write_scope` field is a DIFFERENT semantic (`blast_radius`) and
        // never feeds this parse.
        if (trimmed.startsWith("l2_read_file_cap:")) {
            const v = Number(trimmed.slice("l2_read_file_cap:".length).trim());
            if (Number.isFinite(v) && v > 0)
                readFileCap = v;
        }
        if (trimmed.startsWith("l2_read_byte_cap:")) {
            const v = Number(trimmed.slice("l2_read_byte_cap:".length).trim());
            if (Number.isFinite(v) && v > 0)
                readByteCap = v;
        }
        if (trimmed.startsWith(RAG_CHAT_BUDGET_HEADER)) {
            const v = Number(trimmed.slice(RAG_CHAT_BUDGET_HEADER.length).trim());
            if (Number.isFinite(v) && v > 0)
                ragChatBudget = v;
        }
        if (trimmed.startsWith(RAG_TIME_BUDGET_HEADER)) {
            const v = Number(trimmed.slice(RAG_TIME_BUDGET_HEADER.length).trim());
            if (Number.isFinite(v) && v > 0)
                ragTimeBudgetS = v;
        }
        // AC-007/T-07 escape hatch: only the literal `true` (case-insensitive)
        // opens the hatch; every other value (including absent) is fail-closed.
        if (trimmed.startsWith("allow_foreign_write:")) {
            allowForeignWrite = trimmed.slice("allow_foreign_write:".length).trim().toLowerCase() === "true";
        }
        if (trimmed.startsWith("- name:")) {
            currentPhase = { name: trimmed.slice("- name:".length).trim(), prompt: "" };
            phases.push(currentPhase);
            inPhasePrompt = false;
        }
        else if (trimmed === "prompt: |" && currentPhase) {
            inPhasePrompt = true;
        }
        else if (inPhasePrompt && currentPhase) {
            if (trimmed.startsWith("- ") || trimmed.startsWith("name:")) {
                inPhasePrompt = false;
            }
            else {
                currentPhase.prompt += `${line}\n`;
            }
        }
    }
    // taskKey is the parent directory name of the task file; `agenticdocRoot`
    // is its parent — the owner's workers/ dir, the outputDir base (contract
    // unchanged). The TRUE .agenticdoc root (goal.md's parent) is four levels
    // up from task.md (D-116 semantic split).
    const agenticdocRoot = path.dirname(path.dirname(taskPath));
    const taskKey = path.basename(path.dirname(taskPath));
    const trueAgenticdocRoot = path.dirname(path.dirname(agenticdocRoot));
    // D-115 carrier convergence: parse the authoritative `write_face:` head with
    // the shared operator (D-009/AC-007) so the runtime allow face cannot drift
    // from the dispatch-time overlap operator. Entries are normalized
    // project-root-relative, so the runtime re-parse against the worker cwd is
    // base-independent. `write_scope` is the shared single implementation (T-10).
    const writeScope = parseWriteScopeHeader(content);
    const writeFaceParsed = parseWriteFace(content, {
        base: path.dirname(trueAgenticdocRoot),
        caseInsensitive: process.platform === "win32",
    });
    // T-04b: the claims block is an HTML comment, so the card seed's heading
    // slices never carried it — T-02 injects the block verbatim into task.md
    // (`pm/ui-bridge.ts::extractClaimsBlockText`). Parsing it here keeps the one
    // settle-time source of truth in the task book (D-002) and reuses the L1
    // parser (no second grammar).
    const claimsBlock = parseClaimsBlock(content);
    return {
        type: taskType,
        phase,
        phases: phases.length > 0 ? phases : undefined,
        taskKey,
        agenticdocRoot,
        origin,
        images,
        trueAgenticdocRoot,
        timeoutMin,
        readScope,
        denyGlobs,
        writeScope,
        writeFaceEntries: writeFaceParsed.kind === "declared" ? [...writeFaceParsed.face.entries] : undefined,
        writeFaceRejected: writeFaceParsed.kind === "rejected" ? writeFaceParsed.code : undefined,
        readFileCap,
        readByteCap,
        ragChatBudget,
        ragTimeBudgetS,
        allowForeignWrite,
        writeSurfaceMarker: writeSurfaceMarkerState(content),
        claims: claimsBlock.present ? claimsBlock.claims : undefined,
    };
}
// ── claims settlement (T-04b / design §3.3, AC-008) ───────────────────────
/** Share of `unverified` rows above which the run did not settle its claim
 * contract (AC-008 ②). `>` — the boundary itself passes. */
export const CLAIM_UNVERIFIED_MAX_DEFAULT = 0.4;
/** ... except for the review role, which legitimately hits the no-bash wall
 * (RQ-3 §4 B-2: all 46 corpus review units only carry read/find/grep/ls). */
export const CLAIM_UNVERIFIED_MAX_REVIEW = 0.6;
/** The `carried-from: <path:line>` audit marker of a re-used verdict (RQ-3 §4
 * B-7: "code really did not change" is legal, but only when written down). */
const CARRIED_FROM_RE = /carried-from\s*:\s*\S+/i;
/** `裁决` cell folded to its token form (ticks/whitespace/case), mirroring the
 * L3 parser's own comparison so the counters cannot disagree with the verdict. */
function claimVerdictToken(cell) {
    return cell.replace(/`/g, "").replace(/\s+/g, "").toLowerCase();
}
/** Per-run claim counters: the card's claim set against the product's `## 断言裁决`
 * table (first row per id wins, same as `claimCoverage`). A claims-free run has
 * no counters to write at all — the caller guards on `meta.claims === undefined`
 * rather than fabricating zeroes (T-05: an absent key means "not measured"). */
export function claimCounts(claims, table, fetches) {
    const counts = {
        total: claims.length,
        closed: 0,
        partial: 0,
        unverified: 0,
        fetches,
        tokens: null,
    };
    const declared = new Set(claims.map((claim) => claim.id));
    const seen = new Set();
    for (const row of table.rows) {
        if (!declared.has(row.id) || seen.has(row.id))
            continue;
        seen.add(row.id);
        const verdict = claimVerdictToken(row.verdict);
        if (verdict === "closed")
            counts.closed += 1;
        else if (verdict === "partial")
            counts.partial += 1;
        else if (verdict === "unverified")
            counts.unverified += 1;
    }
    return counts;
}
/** The `[CLAIMS]` trace row (design D-004): a line of its own, NEVER folded into
 * `[END]` — both sides of `[END]` are anchored regexes (`shared/heartbeat.ts`,
 * `packages/multi-workers/mw_common.py`). Field order is frozen here and by
 * `usage.py::_CLAIMS_LINE_RE` (T-05). */
export function formatClaimsTraceLine(counts, now = new Date()) {
    return (`[CLAIMS] ${now.toISOString()} claims=${counts.total} closed=${counts.closed} ` +
        `partial=${counts.partial} unverified=${counts.unverified} fetches=${counts.fetches}`);
}
/** Append the `[CLAIMS]` row once, lifecycle style (no `[FLOW]` prefix — the line
 * starts with its own anchor). Best-effort like every other trace anchor: a
 * diagnostic append must never change the terminal verdict. */
export function appendClaimsTraceLine(taskKey, agenticdocRoot, counts) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(path.join(dir, "trace.log"), `${formatClaimsTraceLine(counts)}\n`, "utf8");
    }
    catch {
        // Diagnostic append — trace.log and run.json carry the rest
    }
}
/** The claim ids named by a gap list (`claim:<id>:<criterion>`), de-duplicated in
 * emission order. Tokens without an id (`claims:missing-table`,
 * `claims:unverified-ratio:…`) are skipped: their own name is the diagnostic. */
export function claimGapIds(gaps) {
    const ids = [];
    for (const gap of gaps) {
        const match = /^claim:(C-\d{2,3}(?:\.\d+)?):/.exec(gap);
        const id = match?.[1];
        if (id !== undefined && !ids.includes(id))
            ids.push(id);
    }
    return ids;
}
/** Repo-relative `path:line` evidence refs of one verdict row's `证据` cell. This
 * is a deliberately narrow reader (the full grammar lives in `output-sections.ts`,
 * which is frozen for T-04b): only the `path[:line[-line]]` half is needed to ask
 * "was this citation produced by an EARLIER round?" — command refs and
 * unparsable refs are ignored, they are owned by the `:evidence` criterion. */
function claimEvidencePaths(cell) {
    const paths = [];
    for (const raw of cell.replace(/`/g, "").split(";")) {
        const ref = raw
            .trim()
            .replace(/「[^」]*」\s*$/, "")
            .trim();
        if (ref === "" || ref === "-" || ref.includes("=>"))
            continue;
        const match = /^(.+?):(\d+)(?:-(\d+))?$/.exec(ref);
        if (match === null)
            continue;
        const file = (match[1] ?? "").trim();
        if (file === "" || file.startsWith("/") || /^[A-Za-z]:[\\/]/.test(file) || file.startsWith("./"))
            continue;
        if (file.split(/[\\/]/).includes(".."))
            continue;
        paths.push(file);
    }
    return paths;
}
/**
 * The three AC-008 settlement criteria that need inputs only the worker layer
 * holds (the role, the run clock, the trace read count) — `claimCoverage`'s
 * per-claim criteria stay in `worker/output-sections.ts` (frozen, T-04a):
 *
 *   ② `claims:unverified-ratio:<u>/<n>><limit>%`  too many un-settled claims
 *      (40%, or 60% for the review role) ⇒ the run must not read as PASS.
 *   ③ `claims:fetches:<sum>><cap>`               Σ取数 above `min(Σ预算, 30)`.
 *      `claims:fetches:<sum>>trace:<n>`           Σ取数 above the trace's own
 *                                                read-class `tool_call` count
 *                                                (B-6: an upper bound — you
 *                                                cannot honestly report more
 *                                                fetches than you performed).
 *   ⑥ `claim:<id>:carried-from`                 a closed/partial row whose every
 *      cited file predates this run's task.md and carries no `carried-from:`:
 *      the previous round's verdict was copied without saying so.
 *
 * Never throws. `claims.length === 0` (no contract) returns `[]`, and an unknown
 * `taskMtimeMs` skips ⑥ rather than guessing a clock.
 */
export function claimSettlementGaps(opts) {
    const gaps = [];
    if (opts.claims.length === 0)
        return gaps;
    const declared = new Set(opts.claims.map((claim) => claim.id));
    const rows = [];
    const seen = new Set();
    for (const row of opts.table.rows) {
        if (!declared.has(row.id) || seen.has(row.id))
            continue;
        seen.add(row.id);
        rows.push(row);
    }
    // ② unverified share (integer permille so the boundary is exact: `>` not `>=`).
    const limitPermille = Math.round(opts.role === "review" ? CLAIM_UNVERIFIED_MAX_REVIEW * 1000 : CLAIM_UNVERIFIED_MAX_DEFAULT * 1000);
    const unverified = rows.filter((row) => claimVerdictToken(row.verdict) === "unverified").length;
    if (opts.claims.length > 0 && unverified * 1000 > opts.claims.length * limitPermille) {
        gaps.push(`claims:unverified-ratio:${unverified}/${opts.claims.length}>${limitPermille / 10}%`);
    }
    // ③ Σ取数 against the derived cap and the trace's own read count.
    let fetchSum = 0;
    for (const row of rows) {
        const fetches = Number(row.fetches.replace(/`/g, "").trim());
        if (Number.isInteger(fetches) && fetches >= 0)
            fetchSum += fetches;
    }
    const { fileCap } = claimBudgetCaps(opts.claims);
    if (fetchSum > fileCap)
        gaps.push(`claims:fetches:${fetchSum}>${fileCap}`);
    if (fetchSum > opts.traceReads)
        gaps.push(`claims:fetches:${fetchSum}>trace:${opts.traceReads}`);
    // ⑥ carried-from: a re-used previous-round verdict must say so.
    const projectDir = opts.projectDir ?? process.cwd();
    if (opts.taskMtimeMs !== undefined) {
        for (const row of rows) {
            const verdict = claimVerdictToken(row.verdict);
            if (verdict !== "closed" && verdict !== "partial")
                continue;
            if (CARRIED_FROM_RE.test(`${row.evidence} ${row.reason}`))
                continue;
            const files = claimEvidencePaths(row.evidence).map((file) => path.resolve(projectDir, file));
            if (files.length === 0)
                continue;
            let staleOnly = true;
            for (const file of files) {
                try {
                    if (!(fs.statSync(file).mtimeMs < opts.taskMtimeMs)) {
                        staleOnly = false;
                        break;
                    }
                }
                catch {
                    // Missing file: the `:evidence` criterion owns it, not this one.
                    staleOnly = false;
                    break;
                }
            }
            if (staleOnly)
                gaps.push(`claim:${row.id}:carried-from`);
        }
    }
    return gaps;
}
// ── Trace helpers ────────────────────────────────────────────────────────────
/** Short, single-line argument summary for trace [TOOL] lines: the file path a
 * read/write/edit targets, the first command line for bash, or the search
 * pattern. Keeps one tool call = one trace line. */
function toolTarget(args) {
    const a = args;
    const raw = typeof a?.path === "string"
        ? a.path
        : typeof a?.command === "string"
            ? a.command
            : typeof a?.pattern === "string"
                ? a.pattern
                : typeof a?.query === "string"
                    ? a.query
                    : typeof a?.file === "string"
                        ? a.file
                        : "";
    if (!raw)
        return "";
    return raw.split("\n")[0] ?? "";
}
/** First line of a failed tool result, for trace [TOOL_ERR] lines. */
function toolErrorText(result) {
    const r = result;
    const text = r?.content?.find((c) => typeof c.text === "string")?.text;
    const first = typeof text === "string" ? (text.split("\n")[0] ?? "") : "";
    return first || "tool error";
}
/** Best-effort synchronous status line into worker.log. The launcher redirects
 * the worker's stdout (fd 1) to worker.log; fs.writeSync lands there even when
 * we process.exit() immediately after (async writes would be dropped). */
function writeWorkerLogLine(line) {
    try {
        fs.writeSync(1, `${line}\n`);
    }
    catch {
        // fd closed / not writable — trace.log and output.md carry the state
    }
}
// ── Process observation + fail-closed gate (D-115/D-107) ──────────────────
/** D-115 process-observation anchor: one pure `[START] pid=<pid>` line per
 * spawn, appended (never reset) to trace.log before the first agent turn —
 * the launcher truncates worker.log per spawn, but trace.log only ever
 * grows, so spawn counts survive. Python autopilot/state.py start_pids
 * counts spawns by exactly this line format (`^\[START\] pid=(\d+)\s*$`);
 * the timestamped [START] runtime anchor from appendStart is a different,
 * coexisting line. */
function appendStartPidLine(taskKey, agenticdocRoot) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(path.join(dir, "trace.log"), `[START] pid=${process.pid}\n`, "utf8");
    }
    catch {
        // Diagnostic append — must never break worker startup
    }
}
/** Append one `[HEADER]` audit line to trace.log (AC-005 §1.4). Best-effort,
 * like the other trace anchors: a diagnostic append must never break startup. */
function appendHeaderTraceLine(taskKey, agenticdocRoot, line) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(path.join(dir, "trace.log"), `${line}\n`, "utf8");
    }
    catch {
        // Diagnostic append — must never break worker startup
    }
}
/** AC-005 observability (DRQ-3 §1.4): record how the single-source role was
 * resolved and what the header boundary ignored. `body-type-ignored` lists the
 * below-header `type:` lines the parser refused to read (A8); `BOM detected`
 * makes the Python-side divergence visible; an unregistered type on an UNMARKED
 * task is the GC-8 fallback the PM ruling keeps (origin-marked tasks are
 * refused by `dispatchRefusal` before this is read). Observational only — it
 * never changes the run's fate (T-13 zero interception). */
function appendHeaderAudit(taskKey, agenticdocRoot, content, taskType) {
    const reading = readTaskType(content);
    if (reading.bomStripped)
        appendHeaderTraceLine(taskKey, agenticdocRoot, "[HEADER] BOM detected");
    const bodyLines = scanBodyTypeLines(content);
    if (bodyLines.length > 0) {
        const shown = bodyLines.slice(0, 4);
        const lines = shown.map((l) => l.line).join(",");
        const values = shown.map((l) => l.value).join(",");
        // The escalation predicate is reported, not enforced here (T-07 scope:
        // the PM ruling only refuses missing/invalid types on origin-marked tasks).
        const escaped = findTypeEscalation(bodyLines, taskType, activeToolsForType) !== undefined;
        appendHeaderTraceLine(taskKey, agenticdocRoot, `[HEADER] body-type-ignored count=${bodyLines.length} lines=${lines} values=${values} ` +
            `escaped=${escaped} role=${roleForTaskType(taskType)}`);
    }
    if (!isRegisteredType(taskType)) {
        appendHeaderTraceLine(taskKey, agenticdocRoot, `[HEADER] unregistered-type-fallback type=${taskType} source=${reading.source} ` +
            `role=${roleForTaskType(taskType)}`);
    }
}
/** Worker-side re-check of the conductor's dispatch-time refusals (D-107
 * double insurance, VC-023): what the Python registry rejects must also fail
 * closed here, so a stale bundle or a non-conductor queue path can never land
 * an unregistered conductor type in the fallback full tool set, nor run a
 * scopeless conductor verifier. Conductor dispatches only — the manual path
 * keeps the GC-8 fallback and the T-13 no-read_scope contract (no origin
 * marker → zero interception) untouched. Returns the exit reason, or
 * undefined when the task may run. */
function dispatchRefusal(meta) {
    if (meta.origin !== "conductor")
        return undefined;
    if (!isRegisteredType(meta.type)) {
        const registered = Object.keys(TOOL_ALLOWLISTS)
            .filter((t) => t !== "fallback")
            .sort()
            .join(", ");
        return (`Fail-closed (D-107/VC-023): this task carries origin: conductor but type '${meta.type}' has no ` +
            `tool-allowlist entry — running it would fall back to the full tool set, which conductor dispatches ` +
            `never get. Registered types: ${registered}.`);
    }
    if (meta.type === "verifier" && (meta.readScope?.length ?? 0) === 0) {
        return ("Fail-closed (D-106): verifier dispatches require a non-empty read_scope in task.md — " +
            "without one the L2 containment boundary is undefined.");
    }
    return undefined;
}
// ── Read-scope rejection records (D-106/AC-009) ──────────────────────────────
// Blocked read-ish calls are recorded twice: immediately in trace.log (the PM
// watch reads trace.log live) and at exit in output.md. Both land in the
// worker task dir, the same directory the output-writer functions use.
/** Append one `[READ_SCOPE]` line to trace.log at block time. */
function appendReadScopeTraceLine(taskKey, agenticdocRoot, r) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(path.join(dir, "trace.log"), `[READ_SCOPE] ${r.ts} blocked path=${r.path} rule=${r.rule} tool=${r.tool}\n`, "utf8");
    }
    catch {
        // Diagnostic append — a failure must never break the block itself
    }
}
/** Append the `## Read Scope Rejections` section to output.md. Called right
 * after every writeOutput (which overwrites output.md), so the section rides
 * along the unified write-out points on every exit path. No-op when nothing
 * was blocked. */
function appendReadScopeRejectionsSection(taskKey, agenticdocRoot, rejections) {
    if (rejections.length === 0)
        return;
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        const lines = ["## Read Scope Rejections", "", "| tool | rule | path | ts |", "| ---- | ---- | ---- | ---- |"];
        for (const r of rejections) {
            lines.push(`| ${r.tool} | ${r.rule} | ${r.path.replaceAll("|", "\\|")} | ${r.ts} |`);
        }
        fs.appendFileSync(path.join(dir, "output.md"), `\n${lines.join("\n")}\n`, "utf8");
    }
    catch {
        // Best-effort at exit — nothing else we can do
    }
}
/** Live shell-expansion characters. Deliberately NOT the `write_scope:`
 * glob-magic set in `shared/write-surface.ts` (`GLOB_MAGIC_RE`): that set
 * matches scope entries, this one decides `verbatim` on command words. */
const LIVE_EXPANSION_CHARS = new Set(["$", "`", "*", "?", "[", "{"]);
/** Split a shell command into quote-aware tokens; control operators become
 * their own tokens, so `echo "a > b"` never yields a redirect. */
export function tokenizeShellCommand(command) {
    const tokens = [];
    let word = "";
    let hasWord = false;
    let inert = true;
    const append = (ch, live) => {
        word += ch;
        if (live && (LIVE_EXPANSION_CHARS.has(ch) || (ch === "~" && word.length === 1)))
            inert = false;
    };
    const flush = () => {
        if (hasWord) {
            tokens.push({ text: word, operator: false, verbatim: inert });
            word = "";
            hasWord = false;
            inert = true;
        }
    };
    let i = 0;
    while (i < command.length) {
        const ch = command[i];
        if (ch === "'" || ch === '"') {
            hasWord = true;
            i++;
            while (i < command.length && command[i] !== ch) {
                if (ch === '"' && command[i] === "\\" && i + 1 < command.length) {
                    // POSIX: only `$`, a backtick, `"` and `\` are escaped in double quotes (P-1).
                    i = appendDoubleQuoteEscape(command, i, append);
                }
                else {
                    // Single quotes inert everything; double quotes only inert an
                    // escaped character (`$`/backtick/glob stay live inside `"`).
                    append(command[i], ch === '"');
                }
                i++;
            }
            i++; // closing quote (or end of input)
            continue;
        }
        if (ch === "\\" && i + 1 < command.length) {
            hasWord = true;
            append(command[i + 1], false);
            i += 2;
            continue;
        }
        // PowerShell here-strings (`@'...'@` / `@"..."@`, AC-013): the body is
        // data, never shell source. Without this the body's apostrophes mis-pair
        // the quote state below and a literal `>` inside becomes a live redirect
        // (measured false block: pattern=redirect target=<script fragment>).
        // Deliberately lenient about the closing `'@` line-start rule: finding the
        // first `${quote}@` can only make more of the command inert (a miss), and
        // never turns data into a target (P1).
        if (ch === "@" && !hasWord && (command[i + 1] === "'" || command[i + 1] === '"')) {
            const close = `${command[i + 1]}@`;
            const closeAt = command.indexOf(close, i + 2);
            const end = closeAt === -1 ? command.length : closeAt + close.length;
            hasWord = true;
            word += command.slice(i, end);
            i = end;
            continue;
        }
        if (ch === " " || ch === "\t") {
            flush();
            i++;
            continue;
        }
        if (ch === "\n") {
            flush();
            tokens.push(markLineBreak({ text: ";", operator: true, verbatim: true }));
            i++;
            continue;
        }
        if (ch === ">" || ch === "<" || ch === "|" || ch === ";" || ch === "&" || ch === "(" || ch === ")") {
            flush();
            let op = ch;
            while (i + 1 < command.length && (command[i + 1] === ch || (command[i + 1] === "-" && op === "<<"))) {
                op += command[i + 1]; // `ch` repeats, but `<<-` absorbs its `-`
                i++;
            }
            tokens.push({ text: op, operator: true, verbatim: true });
            i++;
            continue;
        }
        hasWord = true;
        append(ch, true);
        i++;
    }
    flush();
    return tokens;
}
/** Wrapper commands whose following word is still a command position.
 * Byte-frozen: expanded (never replaced) by `COMMAND_WRAPPERS` below. */
const SHELL_WRAPPER_COMMANDS = new Set(["sudo", "env", "command", "nohup", "time", "nice", "stdbuf", "xargs"]);
/** Command-position wrappers: skip their known flags, the next word is the command. */
const COMMAND_WRAPPERS = new Set([...SHELL_WRAPPER_COMMANDS, "doas", "timeout", "setsid"]);
/** Wrappers whose payload is shell source (re-tokenized and scanned again). */
const SHELL_SCRIPT_WRAPPERS = new Set(["bash", "sh", "zsh", "dash", "ksh"]);
const CMD_SCRIPT_WRAPPERS = new Set(["cmd"]);
const PS_SCRIPT_WRAPPERS = new Set(["powershell", "pwsh"]);
/** Unwrap recursion budget; a deeper payload is left undecided (fails open). */
const MAX_UNWRAP_DEPTH = 3;
/** Wrapper flags that consume one value. Unlisted flags are arity 0, which can
 * only lose coverage — never introduce a false block. */
const WRAPPER_VALUE_FLAGS = {
    sudo: new Set([
        "-u",
        "--user",
        "-g",
        "--group",
        "-p",
        "--prompt",
        "-C",
        "--close-from",
        "-h",
        "--host",
        "-r",
        "--role",
        "-t",
        "--type",
        "-T",
        "--command-timeout",
        "-U",
        "--other-user",
        "-R",
        "--chroot",
        "-D",
        "--chdir",
    ]),
    doas: new Set(["-u", "-C"]),
    env: new Set(["-u", "--unset", "-C", "--chdir", "-S", "--split-string"]),
    nice: new Set(["-n", "--adjustment"]),
    stdbuf: new Set(["-i", "--input", "-o", "--output", "-e", "--error"]),
    timeout: new Set(["-k", "--kill-after", "-s", "--signal"]),
    xargs: new Set([
        "-n",
        "--max-args",
        "-I",
        "--replace",
        "-i",
        "-d",
        "--delimiter",
        "-E",
        "--eof",
        "-P",
        "--max-procs",
        "-s",
        "--max-chars",
        "-L",
        "--max-lines",
        "-a",
        "--arg-file",
    ]),
    time: new Set(["-o", "--output", "-f", "--format"]),
};
/** Operand-position flags that consume one value (arity-aware `positionals`). */
const OPERAND_VALUE_FLAGS = {
    truncate: new Set(["-s", "--size", "-r", "--reference"]),
    install: new Set(["-m", "--mode", "-o", "--owner", "-g", "--group", "-t", "--target-directory", "-S", "--suffix"]),
    cp: new Set(["-t", "--target-directory", "-S", "--suffix"]),
    mv: new Set(["-t", "--target-directory", "-S", "--suffix"]),
    ln: new Set(["-t", "--target-directory", "-S", "--suffix"]),
    rsync: new Set([
        "-e",
        "--rsh",
        "--exclude",
        "--include",
        "--files-from",
        "--chown",
        "--chmod",
        "--bwlimit",
        "--port",
        "--rsync-path",
        "--filter",
        "--exclude-from",
        "--include-from",
        "--log-file",
        "-T",
        "--temp-dir",
        "-M",
        "--remote-option",
        "--out-format",
        "--suffix",
    ]),
    sed: new Set(["-e", "--expression"]),
    perl: new Set(["-e", "-E"]),
};
function flagBase(value) {
    if (value.includes("="))
        return value.slice(0, value.indexOf("="));
    if (value.startsWith("--"))
        return value;
    return `-${value[1] ?? ""}`;
}
function flagHasAttachedValue(value) {
    return value.includes("=") || (value.startsWith("-") && !value.startsWith("--") && value.length > 2);
}
/** Word tokens from `start` up to (not including) the next operator. */
function shellOperands(tokens, start) {
    const values = [];
    for (let i = start; i < tokens.length; i++) {
        if (tokens[i].operator)
            break;
        values.push(tokens[i]);
    }
    return values;
}
/** Positional tokens after arity-aware flag skipping; a bare `--` stops flag
 * interpretation so `rm -- -weird.txt` keeps its operand. */
function positionals(operandTokens, commandName) {
    const values = [];
    const valueFlags = OPERAND_VALUE_FLAGS[commandName];
    let flagsDone = false;
    for (let i = 0; i < operandTokens.length; i++) {
        const token = operandTokens[i];
        const value = token.text;
        if (!flagsDone) {
            if (value === "--") {
                flagsDone = true;
                continue;
            }
            if (value.startsWith("-") && value !== "-") {
                if (valueFlags?.has(flagBase(value)) === true && !flagHasAttachedValue(value))
                    i++;
                continue;
            }
        }
        values.push(token);
    }
    return values;
}
/** The `-t`/`--target-directory` value, with or without an embedded `=`. */
function targetDirectory(operandTokens, flags) {
    for (let i = 0; i < operandTokens.length; i++) {
        const value = operandTokens[i].text;
        if (flags.includes(value))
            return operandTokens[i + 1] ?? null;
        for (const flag of flags) {
            if (flag.startsWith("--") && value.startsWith(`${flag}=`)) {
                const text = value.slice(flag.length + 1);
                return text === "" ? null : { text, operator: false, verbatim: operandTokens[i].verbatim };
            }
        }
    }
    return null;
}
/** Targets that are not repository writes (null devices / std streams). */
const NULL_WRITE_TARGETS = new Set([
    "/dev/null",
    "/dev/stdout",
    "/dev/stderr",
    "/dev/fd/1",
    "/dev/fd/2",
    "nul",
    "/nul",
    "$null", // PowerShell null stream: not a repository write, no audit noise
]);
/** PowerShell write cmdlets and the flags that carry an explicit path. */
const POWERSHELL_WRITE_COMMANDS = new Set([
    "set-content",
    "add-content",
    "clear-content",
    "out-file",
    "new-item",
    "remove-item",
]);
const POWERSHELL_PATH_FLAGS = new Set(["-path", "-literalpath", "-filepath", "-destination"]);
/** AC-017(b)/T-02: `.NET` static FILE/DIRECTORY write methods, mapped to the
 * 0-based argument index that carries the target. This is the write-verb/target
 * position signal (`[System.IO.File]::WriteAllText(path, contents)` — the
 * target is argument 0, never "a path-looking substring"); the read methods
 * (`ReadAllText`, `ReadAllLines`, `Exists`) are deliberately absent. The label
 * is the single `net-file-api` pattern, preserved for the guard's audit line. */
const NET_FILE_API_TARGETS = new Map([
    ["writealltext", 0],
    ["writealllines", 0],
    ["writeallbytes", 0],
    ["appendalltext", 0],
    ["appendalllines", 0],
    ["create", 0],
    ["delete", 0],
    ["move", 0],
    ["replace", 0],
    ["copy", 1],
]);
/** `[System.IO.File]::WriteAllText` (case-folded by `commandBasename`). */
const NET_FILE_API_RE = /^\[system\.io\.(?:file|directory)\]::([a-z0-9_]+)$/;
/** Argument groups of a `name(args)` call: the tokens between the opening `(`
 * and its matching `)` split on top-level commas. The tokenizer makes `(`/`)`
 * operators and keeps `,` inside a word token, so the split is done here. An
 * empty result means the call shape was not found (fail-open: an unparsed call
 * is not a recognized write). */
function callArgumentGroups(tokens, start) {
    const open = tokens[start];
    if (open === undefined || !open.operator || open.text !== "(")
        return [];
    const groups = [[]];
    let depth = 0;
    for (let i = start + 1; i < tokens.length; i++) {
        const token = tokens[i];
        if (token.operator) {
            if (token.text === "(")
                depth += 1;
            else if (token.text === ")") {
                if (depth === 0)
                    return groups;
                depth -= 1;
            }
            groups[groups.length - 1].push(token);
            continue;
        }
        // A comma is an argument separator, and the tokenizer glues it to the
        // neighbouring word (`$path,` / `,arg` / `a,b`), so split on every comma.
        const parts = token.text.split(",");
        for (let p = 0; p < parts.length; p++) {
            if (p > 0)
                groups.push([]);
            if (parts[p] !== "") {
                groups[groups.length - 1].push({ text: parts[p], operator: false, verbatim: token.verbatim });
            }
        }
    }
    return groups;
}
/** Single-command literal value environment (design §5.2): `$x = "lit"`,
 * `$x = 'lit'` and `NAME=lit` bind the name to a literal string. A value with a
 * live expansion is NOT bound, so a target that still depends on one stays
 * non-verbatim and lands in `[WRITE_UNRESOLVED]` instead of being guessed. */
function literalBindings(tokens) {
    const env = new Map();
    const bind = (nameToken, value) => {
        if (value === undefined || value.operator || !value.verbatim || value.text === "")
            return;
        const name = nameToken.startsWith("$") ? nameToken.slice(1) : nameToken;
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name))
            return;
        env.set(name, value.text);
    };
    for (let i = 0; i + 2 < tokens.length; i++) {
        if (tokens[i].operator || tokens[i + 1].operator || tokens[i + 1].text !== "=")
            continue;
        bind(tokens[i].text, tokens[i + 2]);
    }
    for (const token of tokens) {
        if (token.operator || !token.verbatim)
            continue;
        const match = /^([A-Za-z_][A-Za-z0-9_]*)=(.+)$/.exec(token.text);
        if (match === null)
            continue;
        env.set(match[1], match[2]);
    }
    return env;
}
/** Resolve one write-verb operand to a literal target through {@link
 * literalBindings}. A verbatim token is already literal; a `$name` with a
 * binding becomes literal; anything else stays non-verbatim (fail-closed to
 * `[WRITE_UNRESOLVED]`). */
function resolveLiteralTarget(token, env) {
    if (token.verbatim)
        return { target: token.text, verbatim: true };
    const name = token.text.startsWith("$") ? token.text.slice(1) : undefined;
    if (name !== undefined && env.has(name))
        return { target: env.get(name), verbatim: true };
    return { target: token.text, verbatim: false };
}
/** Inline python/node write call sites; the LAST capture group is the path.
 * The bare `write_(text|bytes)` form is intentionally absent: it captures the
 * written CONTENT, not the path (historical false-positive `write_text('x')`). */
const INLINE_WRITE_PATTERNS = [
    /\bopen\s*\(\s*(?:f)?(['"])([^'"]+)\1\s*,\s*(?:mode\s*=\s*)?['"][wax+]/i,
    /\bos\.(?:remove|unlink|rmdir|mkdir|makedirs|rename)\s*\(\s*(['"])([^'"]+)\1/i,
    /\bshutil\.rmtree\s*\(\s*(['"])([^'"]+)\1/i,
    /\bshutil\.(?:copy|copyfile|move)\s*\(\s*(['"])([^'"]+)\1\s*,\s*(['"])([^'"]+)\3/i,
    /\bPath\s*\(\s*(['"])([^'"]+)\1\s*\)\s*\.\s*(?:write_text|write_bytes|touch|mkdir|unlink|rename|replace)/i,
    /\b(?:fs\.)?(?:writeFileSync|writeFile|appendFileSync|appendFile|unlinkSync|unlink|rmSync|rm|rmdirSync|rmdir|mkdirSync|mkdir|createWriteStream)\s*\(\s*(['"])([^'"]+)\1/i,
    /\b(?:fs\.)?renameSync\s*\(\s*(['"])([^'"]+)\1\s*,\s*(['"])([^'"]+)\3/i,
];
/** Perl/Ruby inline write call sites (literal path is the last capture). */
const PERL_INLINE_PATTERNS = [
    /\bopen\s*\(\s*(?:[A-Za-z_]\w*\s*,\s*)?(['"])[^'"]*\1\s*,\s*(['"])([^'"]+)\2/,
    /\bopen\s*\(\s*(?:[A-Za-z_]\w*\s*,\s*)?(['"])[>+]{1,2}([^'"]+)\1/,
];
const RUBY_INLINE_PATTERNS = [
    /\bFile\s*\.\s*(?:write|binwrite|open)\s*\(\s*(['"])([^'"]+)\1/,
    /\bIO\s*\.\s*(?:write|binwrite)\s*\(\s*(['"])([^'"]+)\1/,
];
/** Inline process-spawn call sites; the captured literal is a shell payload. */
const INLINE_EXEC_PATTERNS = [
    /\bos\s*\.\s*(?:system|popen)\s*\(\s*(['"])([^'"]+)\1/,
    /\bsubprocess\s*\.\s*(?:run|call|check_call|check_output|Popen)\s*\(\s*(['"])([^'"]+)\1/,
    /\b(?:execSync|exec|execFileSync|spawnSync|spawn)\s*\(\s*(['"])([^'"]+)\1/,
];
function matchInline(patterns, script) {
    const values = [];
    for (const pattern of patterns) {
        const match = pattern.exec(script);
        if (match === null)
            continue;
        const value = match[match.length - 1];
        if (typeof value === "string" && value.length > 0)
            values.push(value);
    }
    return values;
}
/** Which flag of `commandName` introduces an inline script payload. */
function scriptPayloadFlag(commandName, value) {
    if (SHELL_SCRIPT_WRAPPERS.has(commandName)) {
        return value.startsWith("-") && !value.startsWith("--") && value.includes("c");
    }
    if (CMD_SCRIPT_WRAPPERS.has(commandName)) {
        return value === "/c" || value === "/C" || value === "/k" || value === "/K";
    }
    if (PS_SCRIPT_WRAPPERS.has(commandName)) {
        const lower = value.toLowerCase();
        return lower === "-command" || lower === "-c" || lower === "-commandwithargs";
    }
    if (commandName === "perl")
        return /^-[A-Za-z]*[eE][A-Za-z]*$/.test(value);
    if (commandName === "ruby")
        return value === "-e" || value === "-E";
    if (commandName === "python" || commandName === "python3" || commandName === "py")
        return value === "-c";
    if (commandName === "node")
        return value === "-e" || value === "--eval" || value === "-p" || value === "--print";
    return false;
}
function scriptPayloadToken(operands, commandName) {
    for (let i = 0; i < operands.length; i++) {
        if (scriptPayloadFlag(commandName, operands[i].text))
            return operands[i + 1] ?? null;
    }
    return null;
}
/** Skip command-position wrappers and their flags; returns the inner command
 * index plus any `xargs` replacement placeholders. */
function skipWrapperPrefix(tokens, start) {
    let i = start;
    const placeholders = [];
    while (i < tokens.length && !tokens[i].operator) {
        const name = commandBasename(tokens[i].text);
        if (!COMMAND_WRAPPERS.has(name))
            break;
        i++;
        while (i < tokens.length && !tokens[i].operator) {
            const value = tokens[i].text;
            if (value === "--") {
                i++;
                continue;
            }
            if (!value.startsWith("-")) {
                if (name === "timeout") {
                    // `timeout` takes exactly one leading positional (DURATION) before
                    // the wrapped command; consume it and stop skipping.
                    i++;
                    break;
                }
                if (name === "env" && /^[A-Za-z_][A-Za-z0-9_]*=/.test(value)) {
                    i++;
                    continue;
                }
                break;
            }
            if (name === "xargs") {
                const base = flagBase(value);
                if (base === "--replace" || base === "-I" || base === "-i") {
                    if (flagHasAttachedValue(value)) {
                        const attached = value.includes("=") ? value.slice(value.indexOf("=") + 1) : value.slice(2);
                        if (attached !== "")
                            placeholders.push(attached);
                        i++;
                        continue;
                    }
                    if (base === "-i") {
                        placeholders.push("{}");
                        i++;
                        continue;
                    }
                    const next = tokens[i + 1];
                    if (next !== undefined && !next.operator) {
                        placeholders.push(next.text);
                        i += 2;
                        continue;
                    }
                    i++;
                    continue;
                }
            }
            const arity = WRAPPER_VALUE_FLAGS[name]?.has(flagBase(value)) === true ? 1 : 0;
            i += arity === 1 && !flagHasAttachedValue(value) ? 2 : 1;
        }
    }
    return { index: i, placeholders };
}
/** Flag-shaped redirect operand (`> --glob`) is probe/placeholder text, not a
 * statically known file path — the AC-013 false-block family
 * (`Write-Output a <term> --glob x` measured `target=--glob`). P1 applies: a
 * miss on a genuinely `-` named file is preferable to a false block. Only
 * redirect operands are filtered; `rm -- -weird.txt` style positionals keep
 * their exact-target contract. */
function isFlagLikeRedirectTarget(text) {
    return text.length > 1 && text.startsWith("-");
}
/** Recursive extractor over already-tokenized words. `opaqueTokens` are runtime
 * placeholders (`{}`, `xargs -I R`): a target containing one is not statically
 * determinable and is marked non-verbatim (fail-open). */
function extractFromTokens(tokens, depth, out, opaqueTokens) {
    const add = (source, pattern, verbatimOverride) => {
        const value = (typeof source === "string" ? source : source.text).trim();
        if (value === "" || NULL_WRITE_TARGETS.has(value.toLowerCase()))
            return;
        let verbatim = verbatimOverride ?? (typeof source === "string" ? true : source.verbatim);
        if (verbatim) {
            for (const opaque of opaqueTokens) {
                if (opaque !== "" && value.includes(opaque)) {
                    verbatim = false;
                    break;
                }
            }
        }
        out.push({ target: value, pattern, verbatim });
    };
    // Comparison contexts (`[[ a > b ]]`, `(( a > b ))`, `$(( a > b ))`): the
    // `>`/`<` there compare, they do not redirect (F-2). Track the depth so a real
    // redirect after the closing bracket still registers.
    let comparisonDepth = 0;
    for (let i = 0, list = dropHeredocBodies(tokens); i < list.length; i++) {
        const token = list[i];
        if (token.operator) {
            if (token.text === "((") {
                comparisonDepth += 1;
                continue;
            }
            if (token.text === "))") {
                if (comparisonDepth > 0)
                    comparisonDepth -= 1;
                continue;
            }
            if (token.text === ">" || token.text === ">>") {
                if (comparisonDepth > 0)
                    continue;
                const next = list[i + 1];
                if (next === undefined)
                    continue;
                if (!next.operator) {
                    if (!isFlagLikeRedirectTarget(next.text))
                        add(next, "redirect");
                    continue;
                }
                const after = list[i + 2];
                if (after !== undefined && !after.operator && !isFlagLikeRedirectTarget(after.text)) {
                    if (next.text === "|")
                        add(after, "redirect-clobber");
                    else if (next.text === "&" && !/^\d+$/.test(after.text) && after.text !== "-") {
                        add(after, "redirect-fd-target");
                    }
                }
            }
            continue;
        }
        if (token.text === "[[") {
            comparisonDepth += 1;
            continue;
        }
        if (token.text === "]]") {
            if (comparisonDepth > 0)
                comparisonDepth -= 1;
            continue;
        }
        const previous = list[i - 1];
        if (previous !== undefined && !previous.operator)
            continue;
        extractCommand(list, i, depth, out, add, opaqueTokens);
    }
}
/** Extract the write targets of one command found at `start` (which may be a
 * command-position wrapper chain). */
function extractCommand(tokens, start, depth, out, add, opaqueTokens) {
    const skip = skipWrapperPrefix(tokens, start);
    const commandIndex = skip.index;
    if (commandIndex >= tokens.length)
        return;
    const commandToken = tokens[commandIndex];
    if (commandToken.operator)
        return;
    const commandName = commandBasename(commandToken.text);
    const operandTokens = shellOperands(tokens, commandIndex + 1);
    const childOpaque = new Set(opaqueTokens);
    for (const placeholder of skip.placeholders)
        if (placeholder !== "")
            childOpaque.add(placeholder);
    const recurseShell = (payload) => {
        if (depth >= MAX_UNWRAP_DEPTH)
            return;
        extractFromTokens(tokenizeShellCommand(payload), depth + 1, out, childOpaque);
    };
    const inlineTargets = (patterns, script) => {
        for (const value of matchInline(patterns, script.text)) {
            add(value, "inline-script", script.verbatim && !/[$`]/.test(value));
        }
    };
    switch (commandName) {
        case "bash":
        case "sh":
        case "zsh":
        case "dash":
        case "ksh":
        case "cmd":
        case "powershell":
        case "pwsh": {
            const payload = scriptPayloadToken(operandTokens, commandName);
            if (payload !== null)
                recurseShell(payload.text);
            break;
        }
        case "perl": {
            let suffix;
            let suffixVerbatim = true;
            const files = [];
            for (let k = 0; k < operandTokens.length; k++) {
                const token = operandTokens[k];
                const value = token.text;
                if (value === "--") {
                    for (let m = k + 1; m < operandTokens.length; m++)
                        files.push(operandTokens[m]);
                    break;
                }
                if (value === "-i" || value === "--in-place") {
                    suffix = "";
                    continue;
                }
                if (value.startsWith("-i") && value.length > 2 && !value.startsWith("--")) {
                    suffix = value.slice(2);
                    suffixVerbatim = token.verbatim;
                    continue;
                }
                if (value.startsWith("--in-place=")) {
                    suffix = value.slice("--in-place=".length);
                    suffixVerbatim = token.verbatim;
                    continue;
                }
                if (scriptPayloadFlag("perl", value)) {
                    const payload = operandTokens[k + 1];
                    if (payload !== undefined)
                        inlineTargets(PERL_INLINE_PATTERNS, payload);
                    k++;
                    continue;
                }
                if (value.startsWith("-"))
                    continue;
                files.push(token);
            }
            if (suffix !== undefined) {
                for (const file of files) {
                    add(file, "perl -i");
                    if (suffix !== "")
                        add(`${file.text}${suffix}`, "perl -i", file.verbatim && suffixVerbatim);
                }
            }
            break;
        }
        case "ruby": {
            const payload = scriptPayloadToken(operandTokens, "ruby");
            if (payload !== null)
                inlineTargets(RUBY_INLINE_PATTERNS, payload);
            break;
        }
        case "python":
        case "python3":
        case "py":
        case "node": {
            const payload = scriptPayloadToken(operandTokens, commandName);
            if (payload !== null) {
                inlineTargets(INLINE_WRITE_PATTERNS, payload);
                for (const captured of matchInline(INLINE_EXEC_PATTERNS, payload.text))
                    recurseShell(captured);
            }
            break;
        }
        case "tee": {
            for (const token of operandTokens)
                if (!token.text.startsWith("-"))
                    add(token, "tee");
            break;
        }
        case "cp":
        case "mv": {
            const dir = targetDirectory(operandTokens, ["-t", "--target-directory"]);
            if (dir !== null) {
                add(dir, commandName);
                break;
            }
            const values = positionals(operandTokens, commandName);
            const destination = values[values.length - 1];
            if (destination !== undefined)
                add(destination, commandName);
            break;
        }
        case "rm":
        case "mkdir":
        case "touch":
        case "truncate": {
            for (const token of positionals(operandTokens, commandName))
                add(token, commandName);
            break;
        }
        case "install": {
            const dir = targetDirectory(operandTokens, ["-t", "--target-directory"]);
            const values = positionals(operandTokens, "install");
            if (dir !== null) {
                add(dir, "install -t");
                for (const token of values)
                    add(token, "install");
            }
            else if (values.length >= 2) {
                add(values[values.length - 1], "install");
            }
            break;
        }
        case "ln": {
            const dir = targetDirectory(operandTokens, ["-t", "--target-directory"]);
            if (dir !== null) {
                add(dir, "ln -t");
                break;
            }
            const values = positionals(operandTokens, "ln");
            if (values.length >= 2)
                add(values[values.length - 1], "ln");
            break;
        }
        case "rsync": {
            const values = positionals(operandTokens, "rsync");
            if (values.length >= 2)
                add(values[values.length - 1], "rsync");
            break;
        }
        case "dd": {
            for (const token of operandTokens) {
                const match = /^of=(.*)$/.exec(token.text);
                if (match !== null && match[1] !== "")
                    add(match[1], "dd of=", token.verbatim);
            }
            break;
        }
        case "tar": {
            let create = false;
            let extract = false;
            // Keep the whole token (not only its text) so the target's live-expansion
            // flag survives: `tar -czf $OUT.tar` is not statically determinable and
            // must land in the allow-unknown tier, not be denied as a literal (F-1).
            let archive;
            let directory;
            for (let k = 0; k < operandTokens.length; k++) {
                const token = operandTokens[k];
                const value = token.text;
                if (value === "-C" || value === "--directory") {
                    directory = operandTokens[k + 1];
                    k++;
                    continue;
                }
                if (value.startsWith("--directory=")) {
                    directory = { text: value.slice("--directory=".length), operator: false, verbatim: token.verbatim };
                    continue;
                }
                if (value === "-f" || value === "--file") {
                    archive = operandTokens[k + 1];
                    k++;
                    continue;
                }
                if (value.startsWith("--file=")) {
                    archive = { text: value.slice("--file=".length), operator: false, verbatim: token.verbatim };
                    continue;
                }
                if (value.startsWith("-") && !value.startsWith("--")) {
                    const letters = value.slice(1);
                    if (letters.includes("c"))
                        create = true;
                    if (letters.includes("x"))
                        extract = true;
                    if (letters.includes("f")) {
                        archive = operandTokens[k + 1];
                        k++;
                    }
                }
            }
            if (extract && directory !== undefined)
                add(directory, "tar -C");
            else if (extract)
                add(".", "tar -x");
            else if (create && archive !== undefined)
                add(archive, "tar -c");
            break;
        }
        case "sed": {
            const inPlace = operandTokens.some((token) => token.text === "-i" ||
                token.text === "--in-place" ||
                token.text.startsWith("--in-place=") ||
                (token.text.startsWith("-i") && token.text.length > 2 && !token.text.startsWith("--")));
            if (!inPlace)
                break;
            let suffix = "";
            let suffixVerbatim = true;
            for (const token of operandTokens) {
                if (token.text.startsWith("--in-place=")) {
                    suffix = token.text.slice("--in-place=".length);
                    suffixVerbatim = token.verbatim;
                }
                else if (token.text.startsWith("-i") && token.text.length > 2 && !token.text.startsWith("--")) {
                    suffix = token.text.slice(2);
                    suffixVerbatim = token.verbatim;
                }
            }
            const values = positionals(operandTokens, "sed");
            for (const token of values.slice(1)) {
                add(token, "sed -i");
                if (suffix !== "")
                    add(`${token.text}${suffix}`, "sed -i", token.verbatim && suffixVerbatim);
            }
            break;
        }
        case "find": {
            const roots = [];
            for (const token of operandTokens) {
                if (token.text.startsWith("-") || token.text === "!")
                    break;
                roots.push(token);
            }
            if (roots.length === 0)
                roots.push({ text: ".", operator: false, verbatim: true });
            let remove = false;
            for (let k = 0; k < operandTokens.length; k++) {
                const value = operandTokens[k].text;
                if (value === "-delete")
                    remove = true;
                if (value === "-exec" || value === "-execdir") {
                    const sub = [];
                    let m = k + 1;
                    while (m < operandTokens.length && operandTokens[m].text !== ";" && operandTokens[m].text !== "+") {
                        sub.push(operandTokens[m]);
                        m++;
                    }
                    if (depth < MAX_UNWRAP_DEPTH)
                        extractFromTokens(sub, depth + 1, out, childOpaque);
                    k = m;
                }
            }
            if (remove)
                for (const root of roots)
                    add(root, "find -delete");
            break;
        }
        case "git": {
            const sub = operandTokens[0]?.text.toLowerCase();
            if (sub !== "checkout" && sub !== "apply" && sub !== "clean" && sub !== "restore")
                break;
            const paths = positionals(operandTokens.slice(1), "git");
            if (paths.length === 0)
                add(".", `git ${sub}`);
            else
                for (const token of paths)
                    add(token, `git ${sub}`);
            break;
        }
        case "curl": {
            for (let k = 0; k < operandTokens.length; k++) {
                const value = operandTokens[k].text;
                if (value === "-o" || value === "--output") {
                    const next = operandTokens[k + 1];
                    if (next !== undefined)
                        add(next, "curl -o");
                }
                else if (value.startsWith("--output=")) {
                    add(value.slice("--output=".length), "curl -o", operandTokens[k].verbatim);
                }
            }
            break;
        }
        case "wget": {
            for (let k = 0; k < operandTokens.length; k++) {
                const value = operandTokens[k].text;
                if (value === "-O" || value === "--output-document") {
                    const next = operandTokens[k + 1];
                    if (next !== undefined)
                        add(next, "wget -O");
                }
                else if (value.startsWith("--output-document=")) {
                    add(value.slice("--output-document=".length), "wget -O", operandTokens[k].verbatim);
                }
            }
            break;
        }
        default: {
            // AC-017(b): `.NET` static write methods. The member name is the write
            // verb, its argument position the target position — the same positive
            // signal as every other pattern, so a path-looking substring elsewhere in
            // the command can never become a target.
            const netMember = NET_FILE_API_RE.exec(commandName)?.[1];
            if (netMember !== undefined && NET_FILE_API_TARGETS.has(netMember)) {
                const groups = callArgumentGroups(tokens, commandIndex + 1);
                const operand = groups[NET_FILE_API_TARGETS.get(netMember)]?.find((token) => !token.operator);
                if (operand !== undefined) {
                    const resolved = resolveLiteralTarget(operand, literalBindings(tokens));
                    add(resolved.target, "net-file-api", resolved.verbatim);
                }
                break;
            }
            if (!POWERSHELL_WRITE_COMMANDS.has(commandName))
                break;
            for (let k = 0; k < operandTokens.length; k++) {
                const value = operandTokens[k].text;
                if (value.startsWith("-")) {
                    if (POWERSHELL_PATH_FLAGS.has(value.toLowerCase()) && operandTokens[k + 1] !== undefined) {
                        add(operandTokens[k + 1], `${commandName} -Path`);
                    }
                    continue;
                }
                const previous = operandTokens[k - 1];
                if (previous?.text.startsWith("-"))
                    continue;
                add(operandTokens[k], commandName);
            }
            break;
        }
    }
}
/** Heredoc openers of one physical line, quote- and arithmetic-aware: `<<<`
 * (a here-string with no body) and `<<` inside `(( ))` (a shift) are not
 * heredocs, and a quoted delimiter (`<<'EOF'`) is unquoted. */
function heredocOpeners(line) {
    const openers = [];
    let quote = null;
    let depth = 0;
    let i = 0;
    while (i < line.length) {
        const ch = line[i];
        if (quote !== null) {
            if (ch === "\\" && quote === '"' && i + 1 < line.length) {
                i += 2;
                continue;
            }
            if (ch === quote)
                quote = null;
            i += 1;
            continue;
        }
        if (ch === "'" || ch === '"') {
            quote = ch;
            i += 1;
            continue;
        }
        if (ch === "(" && line[i + 1] === "(") {
            depth += 1;
            i += 2;
            continue;
        }
        if (ch === ")" && line[i + 1] === ")" && depth > 0) {
            depth -= 1;
            i += 2;
            continue;
        }
        if (ch === "<" && line[i + 1] === "<" && depth === 0) {
            let run = i + 2;
            while (line[run] === "<")
                run += 1;
            if (run > i + 2) {
                i = run; // `<<<` here-string: single word, no body
                continue;
            }
            let j = i + 2;
            if (line[j] === "-")
                j += 1;
            while (line[j] === " " || line[j] === "\t")
                j += 1;
            let delimiter = "";
            const q = line[j];
            if (q === "'" || q === '"') {
                const close = line.indexOf(q, j + 1);
                if (close === -1)
                    break;
                delimiter = line.slice(j + 1, close);
                j = close + 1;
            }
            else {
                let k = j;
                while (k < line.length && !/[\s;|&<>()]/.test(line[k]))
                    k += 1;
                delimiter = line.slice(j, k);
                j = k;
            }
            if (delimiter === "") {
                i += 1;
                continue;
            }
            openers.push({ delimiter, start: i, end: j });
            i = j;
            continue;
        }
        i += 1;
    }
    return openers;
}
/** A heredoc terminator line: the delimiter alone, tolerating a trailing `\r`
 * (mixed EOL) and leading tabs (`<<-`). */
function isHeredocTerminator(line, delimiter) {
    return line.replace(/\r+$/, "").replace(/^\t+/, "") === delimiter;
}
/** Strip POSIX heredoc bodies (text level): each `<<DELIM`/`<<-DELIM` opener is
 * removed from its line (a redirect after it survives) and every line up to
 * and including the delimiter line is dropped. */
function stripHeredocTextBodies(command) {
    const lines = command.split("\n");
    const kept = [];
    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        const openers = heredocOpeners(line);
        if (openers.length === 0) {
            kept.push(line);
            i += 1;
            continue;
        }
        let rebuilt = "";
        let cursor = 0;
        for (const opener of openers) {
            rebuilt += line.slice(cursor, opener.start);
            cursor = opener.end;
        }
        kept.push(rebuilt + line.slice(cursor));
        i += 1;
        for (const opener of openers) {
            while (i < lines.length && !isHeredocTerminator(lines[i], opener.delimiter))
                i += 1;
            i += 1; // drop the delimiter line too
        }
    }
    return kept.join("\n");
}
/** Strip PowerShell here-string regions (`@'…'@` / `@"…"@`, AC-013): the
 * opening `@'`/`@"` and everything through the closing `'@`/`"@` is data, not
 * shell source. An unterminated opener consumes to end of input — a miss,
 * never a false operator. */
function stripHereStrings(command) {
    let out = "";
    let i = 0;
    while (i < command.length) {
        const ch = command[i];
        if (ch === "@" && (command[i + 1] === "'" || command[i + 1] === '"')) {
            const close = `${command[i + 1]}@`;
            // PowerShell requires the closing marker at the start of a line; a
            // mid-line `'@` inside the body is data and must NOT close the region
            // early (that leak was re-measured on the rq3 8 KB command).
            const closeRe = new RegExp(`\\n[ \\t]*${close}`);
            closeRe.lastIndex = i + 2;
            const match = closeRe.exec(command);
            out += " ";
            i = match === null ? command.length : match.index + match[0].length;
            continue;
        }
        out += ch;
        i += 1;
    }
    return out;
}
/** AC-017(a) / design §5.1: **strip data regions before the lexer**. A
 * PowerShell here-string body and a POSIX heredoc body are DATA: a literal `>`
 * or `->` inside them must never become a redirect operator, and a quoted
 * fragment inside them must never become a write target. The stripping is a
 * separate, independently testable stage (called first by
 * `extractBashWriteCandidates`), not a regex patch on the extractor's targets. */
export function stripDataRegions(command) {
    return stripHeredocTextBodies(stripHereStrings(command));
}
/** Extract the KNOWN write targets of a bash command. An empty result means
 * "not a recognized write" — the caller must allow it (P1, DD-03). */
export function extractBashWriteCandidates(command) {
    const out = [];
    extractFromTokens(tokenizeShellCommand(stripDataRegions(command)), 0, out, new Set(["{}"]));
    return out;
}
export function classifyLedgerTargets(command) {
    const recorded = [];
    const unresolved = [];
    for (const candidate of extractBashWriteCandidates(command)) {
        const target = candidate.target.trim();
        if (target === "" || target === "." || target === ".." || target === "/")
            continue;
        if (candidate.verbatim)
            recorded.push(target);
        else
            unresolved.push({ pattern: candidate.pattern, target });
    }
    return { recorded, unresolved };
}
function samePath(a, b) {
    return isSameOrUnder(a, b) && isSameOrUnder(b, a);
}
/** Absolute deny reason for a resolved target, or null. The deny list is
 * checked first and can never be widened by a `write_scope:` header. The
 * `packages/**` entry is writeless-only (D-007 / spec risk 10): for a
 * writable role it is the normal work surface, while the isolation entries
 * (framework files, other keys, `.git/**`) stay absolute for every role.
 *
 * T-10: this is deliberately the SHELL-channel role-classified table, not
 * `shared/write-surface.ts::pmWriteDenyReason`. The two share the same six rule
 * names and priority, but only this one is role-parameterized (`packages/**`
 * must stay writable for `coding`/`repair`), so it cannot be the PM table under
 * another name. The ALLOW face below is shared with the predicate instead. */
function bashWriteDenyReason(config, target) {
    const workersDir = path.join(config.keyDir, "workers");
    if (samePath(target, path.join(config.keyDir, "pm-state.md")))
        return "pm-state.md";
    if (isSameOrUnder(workersDir, target)) {
        const firstSegment = path.relative(workersDir, target).split(/[\\/]/)[0] ?? "";
        if (firstSegment.startsWith("_workers"))
            return "workers/_workers*";
    }
    if (samePath(target, path.join(config.trueRoot, "_index.parallel")))
        return "_index.parallel";
    if (isSameOrUnder(config.trueRoot, target) && !isSameOrUnder(config.keyDir, target)) {
        return "other key dir / .agenticdoc root";
    }
    if (config.roleClass !== "writable" && isSameOrUnder(path.join(config.projectRoot, "packages"), target)) {
        return "packages/**";
    }
    if (isSameOrUnder(path.join(config.projectRoot, ".git"), target))
        return ".git/**";
    return null;
}
/** Is `absoluteTarget` inside the authoritative `write_face:` allow face
 * (D-115)? The judgement goes through the SAME shared operator the dispatch
 * gate uses (D-009/AC-007): the concrete target is parsed as a one-entry face
 * and intersected with the declared face, so `*`/`**`/`{a,b}`/case-mode/`..`
 * can never diverge between the two sides. A target the operator cannot place
 * (parse refusal, `..` escape, outside base, equal to the base) is NOT allowed
 * — fail-closed, never a silent widening. Only a PROVABLE conflict
 * (`WriteFaceConflict`, carries a `sample`) admits the target: the conservative
 * `{unsupported}` result means "could not decide" and must block here (the
 * dispatch gate reads it as overlap, i.e. refuse, D-006/D-111). */
function matchesWriteFaceTarget(face, absoluteTarget) {
    const targetFace = parseWriteFaceEntries([absoluteTarget], {
        // Use the declared face's OWN base so the operator's base-equality check
        // can never fail open (`incomparable-base` is treated as overlap).
        base: face.base,
        caseInsensitive: face.caseInsensitive,
    });
    if (targetFace.kind !== "declared")
        return false;
    const result = writeFacesOverlap(targetFace.face, face);
    return result !== null && "sample" in result;
}
/** Compare one carrier entry for the dual-carrier audit flag only (never for
 * the allow decision): lexical separator/dot normalization, order-insensitive. */
function normalizeCarrierEntry(entry) {
    return entry
        .trim()
        .replaceAll("\\", "/")
        .split("/")
        .filter((segment) => segment !== "" && segment !== ".")
        .join("/");
}
function carriersUnequal(writeFaceEntries, writeScopeEntries) {
    const a = writeFaceEntries
        .map(normalizeCarrierEntry)
        .filter((entry) => entry !== "")
        .sort();
    const b = writeScopeEntries
        .map(normalizeCarrierEntry)
        .filter((entry) => entry !== "")
        .sort();
    if (a.length !== b.length)
        return true;
    return a.some((entry, index) => entry !== b[index]);
}
/** D-115 rule 3 audit: both allow carriers are present. The runtime face is
 * their INTERSECTION (the legacy carrier can only narrow, never widen), and the
 * fact is never silent. Written once per task before the first agent turn;
 * best-effort like every other trace append. */
function appendWriteFaceCarrierTraceLine(taskKey, agenticdocRoot, info) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        const rejected = info.rejected === undefined ? "" : ` write_face_rejected=${info.rejected}`;
        const writeFace = JSON.stringify(info.writeFace);
        const writeScope = JSON.stringify(info.writeScope);
        const unequal = String(info.unequal);
        fs.appendFileSync(path.join(dir, "trace.log"), `[WRITE_FACE] ${new Date().toISOString()} carrier=dual unequal=${unequal} ` +
            `write_face=${writeFace} write_scope=${writeScope}${rejected} ` +
            `detail=write_face and write_scope both present, unequal=${unequal}; ` +
            `write_face=${writeFace} write_scope=${writeScope}; declared face = intersection ` +
            "(legacy write_scope can only narrow)\n", "utf8");
    }
    catch {
        // Diagnostic append — a failure must never break the guard.
    }
}
/** The write-surface verdict for one extracted target: a non-verbatim target is
 * not statically determinable (`allow-unknown`, fail-open); otherwise the deny
 * list comes first (absolute priority), then the role-classified default face,
 * then the declared allow carriers (D-115).
 *
 * - writeless (research): default face = own taskDir + `<key>/evidence/**`, and
 *   a declared `write_scope:` intersects it (historical behavior, byte for
 *   byte). The authoritative `write_face:` carrier is never consulted here.
 * - writable (coding/repair/phase-writer/vision/fallback/roadmap-writer):
 *   default face = the working tree, because `packages/**` is the role's work
 *   surface (D-007). The declared face is the authoritative `write_face:` when
 *   present, the legacy `write_scope:` when it is absent, and their
 *   INTERSECTION when both are present (fail-closed: the legacy carrier can
 *   only narrow). The own taskDir/evidence stay writable either way.
 *
 * T-10: the ALLOW face (own taskDir + own-key `<key>/evidence/**`) is resolved
 * by `shared/write-surface.ts::resolveOwnWriteTarget` — the same single source
 * the dispatch predicate and `worker_file` use — so this guard owns no second
 * path-domain/`write_scope` implementation. The SHELL basis is `project-root`:
 * a bash target is a cwd-resolved literal, so a keyDir-relative `evidence/x.md`
 * is refused (DR1 ruling, locked by tests — a designed difference, not a bug).
 * The deny table stays the role-classified shell table (only it makes
 * `packages/**` writeless-only).
 *
 * `toolLabel` only phrases the block reason (`bash` keeps the historical
 * "bash write" wording for the research audit line). */
export function checkBashWriteScopeTarget(config, rawTarget, verbatim, toolLabel = "bash") {
    if (!verbatim) {
        const basename = rawTarget.split(/[\\/]/).pop() ?? "";
        const risk = basename === "pm-state.md" || basename.startsWith("_workers") ? "deny-basename" : undefined;
        return {
            allowed: true,
            rule: "allow-unknown",
            detail: "target-not-statically-determinable",
            target: rawTarget,
            risk,
        };
    }
    const writable = config.roleClass === "writable";
    const target = normalizeForCompare(config.projectRoot, rawTarget);
    // T-10: the ALLOW face (own taskDir + own-key `<key>/evidence/**`) is the
    // shared single source, resolved with the SHELL basis (`project-root` only):
    // a bash target is a cwd-resolved literal, so a keyDir-relative
    // `evidence/x.md` stays cwd-relative and is refused (DR1 — designed; see
    // `shared/write-surface.ts::EvidenceBasis`). The deny table below stays the
    // role-classified shell table (writeless-only `packages/**`).
    const surfacePaths = resolveWriteSurfacePaths({
        taskDir: config.taskDir,
        keyDir: config.keyDir,
        trueRoot: config.trueRoot,
        projectRoot: config.projectRoot,
    });
    const evidenceDir = evidenceDirOf(surfacePaths);
    const allowedLabel = writable ? config.projectRoot : `${config.taskDir} or ${evidenceDir}`;
    const verb = toolLabel === "bash" ? "bash write" : toolLabel;
    const denied = bashWriteDenyReason(config, target);
    if (denied !== null) {
        return {
            allowed: false,
            rule: "deny",
            detail: `denied:${denied}`,
            target: rawTarget,
            reason: `write-scope: blocked ${verb} to ${rawTarget}: ${denied} is on the denied write list ` +
                `[rule=deny]; allowed: ${allowedLabel}`,
        };
    }
    const inOwnSandbox = resolveOwnWriteTarget(target, surfacePaths, { evidenceBasis: "project-root", basenameChannel: false }) !== null;
    // Role-classified default face (D-007). The writable face is the repo root;
    // its realpath is taken so a junctioned cwd cannot make the containment check
    // depend on the unnormalized spelling.
    const insideDefaultFace = writable
        ? isSameOrUnder(normalizeForCompare(config.projectRoot, config.projectRoot), target)
        : inOwnSandbox;
    if (!insideDefaultFace) {
        return {
            allowed: false,
            rule: "scope",
            detail: "outside-allowed-surface",
            target: rawTarget,
            reason: `write-scope: blocked ${verb} to ${rawTarget}: outside the worker write surface ` +
                `[rule=scope]; allowed: ${allowedLabel}`,
        };
    }
    // Declared allow carriers narrow the default face (D-115). The
    // authoritative `write_face:` face is the primary carrier; the legacy
    // `write_scope:` entries apply as a fallback (writable role without a
    // `write_face:` head) and/or as an additional narrowing constraint when both
    // carriers are present (intersection, fail-closed: the legacy carrier can
    // only narrow, never widen). For writable roles the own sandbox stays
    // writable (the worker's own output/evidence artifacts), which keeps a
    // declaration from false-blocking its bookkeeping. Writeless roles never get
    // `writeFace`, so this reduces byte for byte to the historical
    // `write_scope:` narrowing.
    if (!(writable && inOwnSandbox)) {
        const declaredFacePresent = config.writeFace !== undefined || config.writeFaceRejected === true;
        const declaredScopePresent = config.writeScope !== undefined;
        if (declaredFacePresent || declaredScopePresent) {
            const inWriteFace = config.writeFace !== undefined && matchesWriteFaceTarget(config.writeFace, target);
            const inWriteScope = config.writeScope === undefined ||
                config.writeScope.some((entry) => matchesWriteScopeEntry(config.projectRoot, entry, target));
            if (declaredFacePresent && !inWriteFace) {
                return {
                    allowed: false,
                    rule: "write-scope",
                    detail: config.writeFaceRejected === true ? "write-face-rejected" : "outside-declared-write-face",
                    target: rawTarget,
                    reason: `write-scope: blocked ${verb} to ${rawTarget}: outside the task's declared write_face ` +
                        `[rule=write-scope]; allowed: ${allowedLabel}`,
                };
            }
            if (declaredScopePresent && !inWriteScope) {
                return {
                    allowed: false,
                    rule: "write-scope",
                    detail: "outside-declared-write-scope",
                    target: rawTarget,
                    reason: `write-scope: blocked ${verb} to ${rawTarget}: outside the task's declared write_scope ` +
                        `[rule=write-scope]; allowed: ${allowedLabel}`,
                };
            }
        }
    }
    return { allowed: true, target: rawTarget };
}
/** Append one `[WRITE_SCOPE] ... write-scope ...` audit line to trace.log.
 * Contract (AC-005b/AC-007): the line carries the `write-scope` token, the
 * `blocked=<bool>` field, the optional `risk=<token>` residual marker and the
 * blocked command summary. Pure-read/unclassified commands never reach here (no
 * audit noise — the P1 miss surface is covered by the existing full command
 * trace). */
function appendBashWriteScopeTraceLine(taskKey, agenticdocRoot, r) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        const summary = r.command.replace(/\s+/g, " ").trim().slice(0, 200);
        const risk = r.risk === undefined ? "" : `risk=${r.risk} `;
        fs.appendFileSync(path.join(dir, "trace.log"), `[WRITE_SCOPE] ${r.ts} write-scope blocked=${String(r.blocked)} ${risk}rule=${r.rule} detail=${r.detail} ` +
            `pattern=${r.pattern} target=${r.target} cmd=${summary}\n`, "utf8");
    }
    catch {
        // Diagnostic append — a failure must never break the block itself
    }
}
/** Append one machine `[WRITE_SCOPE_SUMMARY]` counter line for a guarded run
 * (AC-007/T-03). Its `allow-unknown=` count and the number of
 * `blocked=false rule=allow-unknown` audit rows are the two independent sources
 * of the equality criterion `allow_unknown_audited == allow_unknown_count`.
 * Best-effort like the audit line: a diagnostic append failure must never break
 * the settle path. */
function appendWriteScopeSummary(taskKey, agenticdocRoot, counts) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(path.join(dir, "trace.log"), `[WRITE_SCOPE_SUMMARY] allow=${counts.allowDetermined} deny=${counts.deny} allow-unknown=${counts.allowUnknown}\n`, "utf8");
    }
    catch {
        // Diagnostic append — a failure must never break the settle path
    }
}
/** Append one machine `[ESCAPE_HATCH] allow_foreign_write=<task_key>
 * target=<path>` audit line (AC-007/T-07). Written for every foreign write the
 * declared escape hatch lets through the bash write-surface guard, so the
 * exception is never silent. Best-effort like every other trace append: a
 * diagnostic failure must never break the write it audits. */
function appendEscapeHatchTraceLine(taskKey, agenticdocRoot, target) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(path.join(dir, "trace.log"), `[ESCAPE_HATCH] allow_foreign_write=${taskKey} target=${target}\n`, "utf8");
    }
    catch {
        // Diagnostic append — a failure must never break the write itself
    }
}
/** Append one machine `[IDLE_KILL]` line to trace.log. Returns false when the
 * line could not be written — the caller must then NOT kill ("no evidence ->
 * no kill"); the wall watchdog stays the outer bound, so a hung worker is
 * still reaped even if the evidence write keeps failing. */
export function appendIdleKillEvidence(taskKey, agenticdocRoot, evidence) {
    try {
        const dir = path.resolve(agenticdocRoot, taskKey);
        fs.mkdirSync(dir, { recursive: true });
        const num = (value) => (value === null ? "-" : String(value));
        const line = `[IDLE_KILL] ${new Date().toISOString()} tool_in_flight=${evidence.toolInFlight} ` +
            `tool_run_s=${num(evidence.toolRunS)} tool_idle_s=${num(evidence.toolIdleS)} ` +
            `silence_s=${evidence.silenceS} threshold_s=${evidence.thresholdS} ` +
            `threshold_kind=${evidence.thresholdKind} last_activity=${evidence.lastActivity} ` +
            `last_model_error=${evidence.lastModelError ? "yes" : "no"}`;
        fs.appendFileSync(path.join(dir, "trace.log"), `${line}\n`, "utf8");
        return true;
    }
    catch {
        return false;
    }
}
// ── VC-014 worker-face emission (T-14) ───────────────────────────────────────
// `required = role.require OR phase.require` is a warning-only contract
// (AC-010): a required role/phase that produced no verifiable citation gets one
// `rag-required-missing` trace line plus a machine-readable output.md marker,
// and the task still settles done. The line itself comes from T-09's
// `researchDocEvidence` (the single mechanism T-10's audit shares) — never a
// second line builder here.
/** task.md `phase:` value, or the literal `unknown` — never a guess. */
export function evidencePhase(phase) {
    return phase !== undefined && phase.length > 0 ? phase : "unknown";
}
const RAG_UNUSED_MARKER = "RAG 未生效：required but unused";
/** Append `line` once: a re-run/duplicate settle must not double the trace. */
function appendEvidenceOnce(taskDir, line) {
    try {
        const tracePath = path.join(path.resolve(taskDir), "trace.log");
        let existing = "";
        try {
            existing = fs.readFileSync(tracePath, "utf8");
        }
        catch {
            // No trace yet — nothing to dedupe against.
        }
        if (existing.includes(line))
            return;
    }
    catch {
        // Fall through to the append; the writer handles a bad dir best-effort.
    }
    appendEvidence(taskDir, line);
}
/** Append the `## RAG` marker to output.md once. output.md is rewritten on
 * every exit path, so a re-settle naturally re-adds the marker exactly once. */
function markOutputRagUnused(taskDir) {
    try {
        const outputPath = path.join(path.resolve(taskDir), "output.md");
        if (!fs.existsSync(outputPath))
            return;
        if (fs.readFileSync(outputPath, "utf8").includes(RAG_UNUSED_MARKER))
            return;
        fs.appendFileSync(outputPath, `\n## RAG\n\n${RAG_UNUSED_MARKER}\n`, "utf8");
    }
    catch {
        // Best-effort at exit — the trace line is the machine gate.
    }
}
/** Server for the evidence line: role spec > phase spec > default_server
 * (mirror of mw_common._rag_resolve_defaults). */
function ragServerFor(config, role, phase) {
    return config.roles[role]?.server ?? config.phases[phase]?.server ?? config.defaultServer ?? "";
}
/**
 * VC-014 (AC-010) worker face: for a *required* role/phase, emit the shared
 * `rag-required-missing` evidence line and mark output.md when no verifiable
 * citation was produced. Returns the emitted line, or null on a no-op (not
 * required, or a citation exists). Zero writes when not required.
 *
 * "Verifiable citation" mirrors T-10's audit: a parseable D-004 citation in
 * the worker's own deliverable, or — for the research role, whose citations
 * live in `<key>/rag/*.md` — a citation in that key's research doc. The
 * research-doc report's `ok` is the used-flag and the line is routed through
 * `researchDocEvidence`, so there is exactly one line builder.
 */
export function emitRagRequiredMissing(check) {
    const role = roleForTaskType(check.taskType);
    if (!requiredFor(check.config, role, check.phase))
        return null;
    const report = validateResearchDoc(check.keyDir);
    const used = scanCitations(check.outputText).length > 0 || (role === "research" && report.citations.length > 0);
    const line = researchDocEvidence({ ...report, ok: used }, role, check.phase, ragServerFor(check.config, role, check.phase));
    if (line === null)
        return null;
    appendEvidenceOnce(check.taskDir, line);
    markOutputRagUnused(check.taskDir);
    return line;
}
export async function workerModeActivate(pi, options) {
    const taskPathEnv = process.env.PI_WORKER_TASK;
    if (!taskPathEnv) {
        return;
    }
    const taskPath = path.resolve(taskPathEnv);
    if (!fs.existsSync(taskPath)) {
        killTrackedDetachedChildren();
        process.exit(1);
    }
    const meta = parseTaskMd(taskPath);
    const startedAt = Date.now();
    const phaseTotal = meta.phases?.length ?? 0;
    // Model-error state machine (design §3.1 / D1/D3/D4/D6, process-level revision
    // 2026-10-15): the process itself is the retry unit. One error agent run ends
    // this process (exit 3); same-model retries and the fallback chain live in the
    // launcher, so there is no per-process error-run counter here. agent_end only
    // records `lastErrorInfo` (it fires once per internal auto-retry attempt, so
    // acting there would miscount). `triedModels` is the launcher-seeded audit
    // chain; the current model joins it at session start.
    // `provider/id` label of the live model (raw id when the provider is absent):
    // the identity every model-error protocol line reports (design §4).
    let currentModelLabel = "";
    let lastErrorInfo;
    // Design D4 patch (hang classification): a no-in-flight-tool hang is a
    // model-availability suspect when this process already saw an error boundary,
    // or when its agent loop started and never produced a successful assistant
    // (a pure first-call hang). A worker that never entered its agent loop is a
    // generic hang, not a model diagnosis.
    let agentRunStarted = false;
    let sawSuccessfulAssistant = false;
    const triedModels = parseTriedModels(process.env.PI_WORKER_TRIED_MODELS);
    // D-115: record this spawn before anything else — the process itself is
    // the observation unit (spawn count + pid liveness), even when the task
    // is refused right below.
    appendStartPidLine(meta.taskKey, meta.agenticdocRoot);
    // Product-carried run identity (D-022/D-023, AC-022): this process writes its
    // OWN run.json — `running` now, a terminal state on every exit path below.
    // That is what makes a finished task un-restartable even when its ledger row
    // is lost (IN-3 rebuilt 252 rows in one second and a re-run overwrote a
    // finished task's output.md at 11:45:40), and what forces more work on a
    // finished task to use a NEW task_key declaring `supersedes:`.
    // task.md is read once here and reused for the read-scope parent root below.
    const taskDir = path.dirname(taskPath);
    const taskContent = fs.readFileSync(taskPath, "utf8");
    // AC-005 observability: record the ignored body `type:` lines / BOM / GC-8
    // fallback before the fail-closed gate so a refused spawn is audited too.
    appendHeaderAudit(meta.taskKey, meta.agenticdocRoot, taskContent, meta.type);
    const runState = {
        schema: RUN_SCHEMA,
        task_key: meta.taskKey,
        run_id: newRunId(meta.taskKey),
        // `.agenticdoc/<key>/workers/<task>` (or `_scratch`): the owner key is the
        // directory that owns this task, never inferred from the task-key prefix.
        owner_key: path.basename(path.dirname(path.dirname(taskDir))),
        kind: meta.type,
        status: "running",
        started_at: new Date().toISOString(),
        supersedes: parseSupersedes(taskContent),
        artifacts: [],
        pid: process.pid,
        last_heartbeat_at: new Date().toISOString(),
    };
    writeRunState(taskDir, runState);
    // D-107 fail-closed gate: refuse the task before any agent turn, with the
    // reason in output.md (counts into the loop budget escalation on the
    // conductor side, AC-023).
    const refusal = dispatchRefusal(meta);
    if (refusal !== undefined) {
        appendError(meta.taskKey, meta.agenticdocRoot, refusal);
        markOutcome(1);
        writeOutput({
            taskKey: meta.taskKey,
            agenticdocRoot: meta.agenticdocRoot,
            exitCode: 1,
            summary: "Task refused at startup (fail-closed).",
            exitReason: refusal,
            runMarker: runMarker(runState),
        });
        // A refusal is a real terminal outcome: record it as such, so the row and
        // the product tell the same story and the task is never auto-restarted.
        finishRun("failed", 1);
        writeWorkerLogLine(`[worker] refused task=${meta.taskKey} type=${meta.type}: ${refusal}`);
        killTrackedDetachedChildren();
        process.exit(1);
    }
    // Read-scope enforcement (D-106/AC-009): active only when task.md carries
    // read_scope — otherwise zero interception (AC-012 red line). Rejections
    // accumulate in memory and are written to output.md on every exit path via
    // writeOutputGuarded (the output-writer remains the unified write-out point).
    // Partition extended-workspace union (mw-partition-parent-extended AC-002):
    // the profile block's Parent root joins the allowed scope — parent is a
    // directly developed extension of the workspace, not read-only context.
    // No-op for empty (fail-closed) / deny-only scopes and non-partition tasks.
    const readScopeConfig = applyParentRootUnion(readScopeConfigFromMeta(meta), parentRootFromTaskContent(taskContent));
    const readScopeState = { allowedCalls: 0, bytesRead: 0 };
    const readScopeRejections = [];
    function writeOutputGuarded(opts) {
        // The product write is this run's terminal moment, and the marker it carries
        // must state the outcome the same write records — so reflect it in memory
        // first (finishRun persists it right after, R15).
        markOutcome(opts.exitCode);
        writeOutput({ ...opts, runMarker: runMarker(runState) });
        appendReadScopeRejectionsSection(meta.taskKey, meta.agenticdocRoot, readScopeRejections);
    }
    /** The one place that maps an exit code to a terminal status (shared by the
     * output.md marker and the persisted record). AC-006 adds the framework's
     * no-product verdict: exit 2 = needs-clarification (not a crash), so the OS
     * exit code, `[END] exit=`, run.json.status and the output.md marker all
     * agree with `launcher._exit_to_status`. */
    function markOutcome(exitCode) {
        runState.status = exitCode === 0 ? "done" : exitCode === 2 ? "needs-clarification" : "failed";
        return runState.status;
    }
    /** Terminal write for THIS run (AC-022/D-022). Every exit path lands here
     * through `recordEnd`, a startup refusal, or the process-exit safety net.
     * Best-effort by contract (R15): when the write fails it is noted in
     * trace.log and the run still writes output.md. `artifacts` is re-collected
     * here (the deliverables exist by now), never for a `lost` run — the Python
     * launcher owns that single addition (D-023). */
    function finishRun(status, exit) {
        runState.status = status;
        runState.ended_at = new Date().toISOString();
        if (exit !== undefined)
            runState.exit = exit;
        runState.artifacts = collectArtifacts(taskDir);
        writeRunState(taskDir, runState);
    }
    // Task lifecycle start: trace.log gets a machine-parseable [START] anchor
    // (runtime origin for elapsed computation), worker.log a human status line.
    appendStart(meta.taskKey, meta.agenticdocRoot, meta.type, phaseTotal);
    // AC-010/T-12: consume the C2 contract markers read back by `parseTaskMd`.
    // The producer is PM-side; a malformed pair here means renderer drift (a
    // dangling marker the cleanup regex could not remove, or a duplicated
    // section) and the agent may be reading a stale half-contract. Absence is
    // the normal state for manual/legacy task books and is never flagged.
    if (meta.writeSurfaceMarker === "malformed") {
        appendTrace(meta.taskKey, meta.agenticdocRoot, "[WRITE_SURFACE] contract-section markers malformed (expected exactly one ordered marker pair)");
    }
    // D-116: record which model runs this task. ExtensionAPI has no model
    // getter — the resolved id is only readable from an event context, so
    // capture it at session start (fires before the first turn). A duplicate
    // line on a later session event is harmless: readers take the last one.
    pi.on("session_start", (_event, ctx) => {
        const modelId = ctx.model?.id;
        if (modelId) {
            appendModel(meta.taskKey, meta.agenticdocRoot, modelId);
            // Model-error perception: remember which model this run is on and make
            // sure it joins the launcher-seeded tried chain (D-116 `[MODEL]` source).
            currentModelLabel = ctx.model?.provider ? `${ctx.model.provider}/${modelId}` : modelId;
            if (!triedModels.includes(currentModelLabel))
                triedModels.push(currentModelLabel);
        }
        // T-09/AC-011 (VC-011): runtime image-capability backstop. The dispatch
        // declared `images: yes` but the resolved model cannot read images —
        // refuse before the task body runs, through the same failure channel as
        // dispatchRefusal. `outputWritten` is set first so the process 'exit'
        // safety net does not append its crash output over this refusal.
        if (meta.images === true && ctx.model && Array.isArray(ctx.model.input) && !ctx.model.input.includes("image")) {
            const line = `[IMAGE-CAP] model=${ctx.model.id} provider=${ctx.model.provider} task=${meta.taskKey} declared=images:yes`;
            writeWorkerLogLine(line);
            appendError(meta.taskKey, meta.agenticdocRoot, line);
            markOutcome(1);
            writeOutput({
                taskKey: meta.taskKey,
                agenticdocRoot: meta.agenticdocRoot,
                exitCode: 1,
                summary: "Task refused (image capability).",
                exitReason: line,
                runMarker: runMarker(runState),
            });
            outputWritten = true;
            finishRun("failed", 1);
            killTrackedDetachedChildren();
            process.exit(1);
            return;
        }
        // Fail-open (GC-8): without a resolved model the capability is
        // unverifiable — record a trace note, never block the task.
        if (meta.images === true && ctx.model === undefined) {
            appendTrace(meta.taskKey, meta.agenticdocRoot, "[IMAGE-CAP] fail-open: ctx.model undefined, image capability unverifiable for declared=images:yes");
        }
    });
    writeWorkerLogLine(`[worker] start task=${meta.taskKey} type=${meta.type} phases=${phaseTotal > 0 ? phaseTotal : "-"}`);
    // Safety net: guarantee an output.md exists on any exit path. The normal
    // writers (success / timeout / catch) set outputWritten=true; if the process
    // dies before any of them run (hard crash, unexpected process.exit), the
    // exit hook writes a minimal failure output so the PM never sees silence.
    let outputWritten = false;
    process.on("exit", () => {
        // Hard-crash backstop: an exit path that bypassed the explicit kills
        // below (uncaught exception, unexpected process.exit) must not leak the
        // bash tool's in-flight child trees as orphans (2026-09-19 incident:
        // idle-killed worker left a spinning probe at 151 GB WS).
        // Isolated so a future throwing change in the kill path can never
        // skip the fallback output write below (currently throw-free: both
        // killProcessTree branches swallow their own errors).
        try {
            killTrackedDetachedChildren();
        }
        catch {
            // Best-effort during exit — nothing else we can do.
        }
        if (outputWritten)
            return;
        try {
            writeOutputGuarded({
                taskKey: meta.taskKey,
                agenticdocRoot: meta.agenticdocRoot,
                exitCode: 1,
                summary: "(worker exited without writing output)",
                exitReason: "Process exited before output.md was written (crash or unexpected exit).",
            });
        }
        catch {
            // Best-effort during exit — nothing else we can do.
        }
        // Crash backstop: nothing wrote output, so this run ended without a
        // result — record that in the product too (a normal terminal path returns
        // above via `outputWritten`). Guarded so a terminal state is never
        // downgraded.
        if (!isTerminalRunStatus(runState.status))
            finishRun("failed", 1);
    });
    // RAG surface (D-002): registered only when the project enables servers;
    // disabled projects get no registration and no probe (structural zero impact).
    // The probe runs here so tool descriptions can carry the unreachable marker
    // before the first agent turn.
    let ragRuntime = null;
    const controlRoot = controlRootFromTaskPath(taskPath);
    const workerTaskDir = path.dirname(taskPath);
    try {
        ragRuntime = registerRagTools(pi, controlRoot, {
            breaker: new Breaker(),
            workerTaskDir,
            role: roleForTaskType(meta.type),
            phase: meta.phase ?? "",
        });
    }
    catch (err) {
        writeWorkerLogLine(`[worker] rag disabled: ${err instanceof Error ? err.message : String(err)}`);
    }
    // run-detached surface (D-005): registered in BOTH activate paths (the
    // registerRagTools precedent) so PM and worker windows can dispatch
    // background commands. The allowlist gate above decides visibility.
    try {
        registerRunDetachedTool(pi, controlRoot);
    }
    catch (err) {
        writeWorkerLogLine(`[worker] run-detached disabled: ${err instanceof Error ? err.message : String(err)}`);
    }
    // Narrow write channel (D-101/D-104/D-106): roles whose allowlist has no
    // write/edit tool get `worker_file` registered — a structural gate mirroring
    // `registerRagTools`'s disabled→skip. OUTSIDE the RAG try/catch on purpose:
    // a broken RAG config must not swallow a read-only role's only channel.
    const hasWriteTool = toolsForType(meta.type).includes("write");
    if (!hasWriteTool) {
        registerWorkerFileTool(pi, workerTaskDir);
    }
    if (ragRuntime !== null) {
        await ragRuntime.ready;
        ragRuntime.workerTaskDir = workerTaskDir;
        // T-05: real budget instance. task.md headers win over the project's
        // `rag.budgets` defaults; the wall guard shares the watchdog wall budget.
        ragRuntime.budget = new Budget(workerTaskDir, meta.ragChatBudget ?? ragRuntime.config.budgets.chat, (meta.ragTimeBudgetS ?? ragRuntime.config.budgets.timeS) * 1000, { taskWallMs: resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS) });
    }
    // Set tool allowlist once before the first agent run (AC-010)
    // setActiveTools is an action method — must be deferred to after runner.initialize().
    // `applyRagTools` recomputes the complete expected set on every run, so the
    // handler stays idempotent across phase/follow-up turns (D-002); a null
    // runtime reproduces the pre-RAG `setActiveTools(toolsForType(type))` byte
    // for byte.
    // dp2 narrow steer (T-07b): this is the primary consumption point of
    // `steer-dp2.md` — the file the PM writes INSTEAD of waking itself. Same
    // handler because both are per-run, idempotent and must run before the turn.
    let dp2SteerInjected = false;
    /** Consume `<taskDir>/steer-dp2.md` once. Returns true when a steer was
     * injected in THIS call (the settle path then keeps the run open so the
     * queued follow-up turn actually executes). Never throws: a broken steer must
     * not change the terminal verdict — it is reported on trace.log instead. */
    function consumeDp2NarrowSteer(via) {
        const steerPath = path.join(taskDir, DP2_STEER_FILE);
        let content;
        try {
            content = fs.readFileSync(steerPath, "utf8");
        }
        catch (err) {
            // Absent file is the normal state (no dp2 narrow request): zero trace.
            if (err.code !== "ENOENT") {
                appendTrace(meta.taskKey, meta.agenticdocRoot, "[DECISION] dp2 consume-failed reason=read");
            }
            return false;
        }
        if (dp2SteerInjected || hasDp2ConsumedMarker(content))
            return false;
        const text = formatDp2NarrowSteer(content);
        if (text === undefined) {
            // Header-only / empty request: nothing to inject, and no marker either
            // (marking it consumed would assert a steer that never existed).
            appendTrace(meta.taskKey, meta.agenticdocRoot, "[DECISION] dp2 consume-failed reason=empty");
            return false;
        }
        try {
            pi.sendUserMessage(text, { deliverAs: "followUp" });
        }
        catch {
            appendTrace(meta.taskKey, meta.agenticdocRoot, "[DECISION] dp2 consume-failed reason=inject");
            return false;
        }
        dp2SteerInjected = true;
        // Marker AFTER a delivered injection: a crash in between replays the steer
        // (at-least-once) instead of silently swallowing it (fail-open).
        let marked = false;
        try {
            marked = appendDp2ConsumedMarker(steerPath, content, runState.run_id);
        }
        catch {
            marked = false;
        }
        if (!marked) {
            appendTrace(meta.taskKey, meta.agenticdocRoot, "[DECISION] dp2 consume-failed reason=mark");
        }
        const decisionId = /decision_id=(\S+)/.exec(content)?.[1] ?? "-";
        appendTrace(meta.taskKey, meta.agenticdocRoot, `[DECISION] dp2 consumed=1 decision_id=${decisionId} via=${via} marker=${marked ? "ok" : "failed"}`);
        return true;
    }
    pi.on("before_agent_start", () => {
        applyRagTools(pi, ragRuntime, meta.type);
        consumeDp2NarrowSteer("before_agent_start");
    });
    // W8: the decision role's fixed contract + its two runtime guards. The prompt
    // is appended to the system prompt of EVERY turn (not a one-shot message), so
    // a compacted context cannot lose "do not send, do not edit code"; the guards
    // enforce the two shapes the prompt alone cannot prevent (a mutating bash
    // command, a write outside the books dir). Inert for every other type.
    if (meta.type === DECIDE_PREPARE_TYPE) {
        const allowSend = decisionAllowsSend(taskContent);
        pi.on("before_agent_start", (event) => {
            if (event.systemPrompt.includes(DECISION_TYPE_PROMPT))
                return undefined;
            return { systemPrompt: `${event.systemPrompt}\n\n${DECISION_TYPE_PROMPT}` };
        });
        pi.on("tool_call", (event) => {
            if (event.toolName === "bash") {
                const command = event.input?.command;
                if (typeof command !== "string" || command.trim() === "")
                    return undefined;
                const reason = decisionBashBlockReason(command, allowSend);
                if (reason === null)
                    return undefined;
                appendTrace(meta.taskKey, meta.agenticdocRoot, `[DECISION] bash blocked allow_send=${allowSend ? "yes" : "no"}`);
                return { block: true, reason };
            }
            if (event.toolName === WORKER_FILE_TOOL) {
                const file = event.input?.path;
                if (typeof file !== "string" || decisionWorkerFilePathAllowed(file))
                    return undefined;
                appendTrace(meta.taskKey, meta.agenticdocRoot, "[DECISION] worker_file blocked outside evidence/books");
                return {
                    block: true,
                    reason: `decision: this role writes only ${DECISION_BOOK_SUBDIR}/** ` +
                        `(got ${JSON.stringify(file)}); the book is the whole product.`,
                };
            }
            return undefined;
        });
    }
    // Read-scope interceptor (D-106): read/ls/find/grep share one containment
    // gate. ls/find/grep default to the cwd (= project root) when their path
    // is omitted — that implicit target goes through the same containment as
    // an explicit path, so dropping the argument cannot bypass the scope.
    // grep's glob filter is not separately validated (the search root is).
    if (readScopeConfig) {
        const projectRoot = process.cwd(); // launcher spawns workers with cwd = project root (D-106 base)
        pi.on("tool_call", (event) => {
            if (event.toolName !== "read" &&
                event.toolName !== "ls" &&
                event.toolName !== "find" &&
                event.toolName !== "grep") {
                return undefined;
            }
            const inputPath = event.input?.path;
            const rawPath = typeof inputPath === "string" && inputPath !== "" ? inputPath : ".";
            const verdict = checkReadScopeCall(projectRoot, readScopeConfig, readScopeState, event.toolName, rawPath);
            if (verdict.allowed) {
                readScopeState.allowedCalls++;
                readScopeState.bytesRead += verdict.chargedBytes;
                return undefined;
            }
            const rejection = {
                tool: event.toolName,
                path: rawPath,
                rule: verdict.rule ?? "scope",
                ts: new Date().toISOString(),
            };
            readScopeRejections.push(rejection);
            appendReadScopeTraceLine(meta.taskKey, meta.agenticdocRoot, rejection);
            return { block: true, reason: verdict.reason };
        });
    }
    // Runtime write-surface guard (AC-004 / AC-005b / contract C3 → D-007 IP-1b,
    // carrier convergence D-115): every role with a `write`/`edit` tool OR a
    // `bash` tool gets it, and the shell-like ones are covered on both channels in
    // this single `tool_call` handler. Bash commands are classified by the
    // write-face lexer; a `write`/`edit` call contributes its literal `path`. A
    // target is accepted only when it stays inside the role-classified surface:
    // the deny list first (absolute priority), then the default face, then the
    // declared allow carriers (D-115: authoritative `write_face:`, legacy
    // `write_scope:` only as fallback/narrowing). `writeless` roles (today:
    // `research`) keep the historical face byte for byte (own taskDir +
    // `<key>/evidence/**`, `packages/**` denied); `writable` roles get the
    // working tree as their default face, because `packages/**` is their work
    // surface, not a red line (spec risk 10). Pure-read and unclassifiable bash
    // commands pass silently (P1: a miss is preferable to a false block). The
    // handler never touches the `tool_execution_start/end` accounting branch.
    const roleClass = isWritelessRole(meta.type) ? "writeless" : "writable";
    // D-115 carrier resolution: the authoritative `write_face:` face is re-parsed
    // against the worker cwd (the same shared operator as the dispatch gate), and
    // only writable roles consult it — writeless roles keep `write_scope:` byte
    // for byte and never see `write_face`.
    const writeFaceEntries = roleClass === "writable" ? meta.writeFaceEntries : undefined;
    let declaredWriteFace;
    if (writeFaceEntries !== undefined && writeFaceEntries.length > 0) {
        const parsed = parseWriteFaceEntries(writeFaceEntries, {
            base: process.cwd(),
            caseInsensitive: process.platform === "win32",
        });
        if (parsed.kind === "declared")
            declaredWriteFace = parsed.face;
    }
    const declaredWriteFaceRejected = roleClass === "writable" &&
        declaredWriteFace === undefined &&
        (meta.writeFaceRejected !== undefined || meta.writeFaceEntries !== undefined);
    const bashWriteScopeConfig = hasWriteTools(meta.type) || isShellRole(meta.type)
        ? {
            projectRoot: process.cwd(), // launcher spawns workers with cwd = project root
            taskDir,
            keyDir: path.dirname(meta.agenticdocRoot),
            trueRoot: meta.trueAgenticdocRoot,
            writeScope: meta.writeScope,
            roleClass,
            writeFace: declaredWriteFace,
            writeFaceRejected: declaredWriteFaceRejected || undefined,
        }
        : undefined;
    // D-115 rule 3: two carriers present ⇒ the runtime allow face is their
    // intersection and the fact is audited on trace.log (never silent).
    if ((declaredWriteFace !== undefined || declaredWriteFaceRejected) && meta.writeScope !== undefined) {
        const faceEntries = declaredWriteFace?.entries ?? [];
        appendWriteFaceCarrierTraceLine(meta.taskKey, meta.agenticdocRoot, {
            writeFace: faceEntries,
            writeScope: meta.writeScope,
            unequal: carriersUnequal(faceEntries, meta.writeScope),
            rejected: declaredWriteFace === undefined ? meta.writeFaceRejected : undefined,
        });
    }
    // AC-007/T-03 outcome counters: mutated by the guard below, consumed by
    // `recordEnd` for the `[WRITE_SCOPE_SUMMARY]` line. Declared outside the
    // `if` so the settle path can read them.
    const writeScopeCounts = { allowDetermined: 0, deny: 0, allowUnknown: 0 };
    if (bashWriteScopeConfig) {
        const config = bashWriteScopeConfig;
        pi.on("tool_call", (event) => {
            if (event.toolName === "bash") {
                // The bash sub-judgement stays installed only for roles that actually
                // carry `bash` (D-115 rule 6): a writable bash-less role
                // (`roadmap-writer`) gets the `write`/`edit` branch alone.
                if (!isShellRole(meta.type))
                    return undefined;
                const command = event.input?.command;
                if (typeof command !== "string" || command.trim() === "")
                    return undefined;
                for (const candidate of extractBashWriteCandidates(command)) {
                    const verdict = checkBashWriteScopeTarget(config, candidate.target, candidate.verbatim);
                    if (verdict.rule === "allow-unknown") {
                        // Contract cost (F1–F3): not blockable — audit first, then continue.
                        writeScopeCounts.allowUnknown += 1;
                        appendBashWriteScopeTraceLine(meta.taskKey, meta.agenticdocRoot, {
                            ts: new Date().toISOString(),
                            blocked: false,
                            rule: "allow-unknown",
                            detail: verdict.detail ?? "target-not-statically-determinable",
                            risk: verdict.risk,
                            target: candidate.target,
                            pattern: candidate.pattern,
                            command,
                        });
                        continue;
                    }
                    if (verdict.allowed) {
                        writeScopeCounts.allowDetermined += 1;
                        continue;
                    }
                    // AC-007/T-07 escape hatch: a declared, human-accepted foreign write is
                    // allowed and audited; missing/false stays fail-closed. The hard deny
                    // list (other keys, .git/**, pm-state.md, _workers*) is an isolation red
                    // line (AC-008) and is deliberately NOT widened — the hatch covers an
                    // external target, not the framework's own files. (`packages/**` is
                    // writeless-only, so it is not part of that list for writable roles.)
                    if (meta.allowForeignWrite === true && verdict.rule !== "deny") {
                        writeScopeCounts.allowDetermined += 1;
                        appendEscapeHatchTraceLine(meta.taskKey, meta.agenticdocRoot, candidate.target);
                        continue;
                    }
                    writeScopeCounts.deny += 1;
                    appendBashWriteScopeTraceLine(meta.taskKey, meta.agenticdocRoot, {
                        ts: new Date().toISOString(),
                        blocked: true,
                        rule: verdict.rule ?? "scope",
                        detail: verdict.detail ?? "blocked",
                        target: candidate.target,
                        pattern: candidate.pattern,
                        command,
                    });
                    return { block: true, reason: verdict.reason };
                }
                return undefined;
            }
            // D-007 IP-1b: the same verdict for the literal `write`/`edit` target
            // (`event.input.path`). These tools are only in a writable role's
            // allowlist, so the writeless default face never sees them; a writable
            // role's declared face narrows outside its own sandbox.
            if (event.toolName !== "write" && event.toolName !== "edit")
                return undefined;
            const toolLabel = event.toolName === "write" ? "write" : "edit";
            const rawPath = event.input?.path;
            if (typeof rawPath !== "string" || rawPath.trim() === "")
                return undefined;
            const verdict = checkBashWriteScopeTarget(config, rawPath, true, toolLabel);
            if (verdict.allowed) {
                writeScopeCounts.allowDetermined += 1;
                return undefined;
            }
            if (meta.allowForeignWrite === true && verdict.rule !== "deny") {
                writeScopeCounts.allowDetermined += 1;
                appendEscapeHatchTraceLine(meta.taskKey, meta.agenticdocRoot, rawPath);
                return undefined;
            }
            writeScopeCounts.deny += 1;
            appendBashWriteScopeTraceLine(meta.taskKey, meta.agenticdocRoot, {
                ts: new Date().toISOString(),
                blocked: true,
                rule: verdict.rule ?? "scope",
                detail: verdict.detail ?? "blocked",
                target: rawPath,
                pattern: toolLabel,
                command: `${toolLabel} ${rawPath}`,
            });
            return { block: true, reason: verdict.reason };
        });
    }
    const inFlightTools = new Map();
    let lastActivityAt = startedAt;
    let lastDeltaAt;
    let lastToolAt;
    /** Last source that refreshed `lastActivityAt` (VC-004 evidence field). */
    let lastActivitySource = "session_start";
    const touch = (source) => {
        lastActivityAt = Date.now();
        lastActivitySource = source;
    };
    /** Design D4 (option A): an error assistant boundary is NOT activity — a
     * failed/stalled model must not keep the idle clock fresh, so a silent hang
     * is reaped by the idle wall (~10m) instead of the ~40m N=2 chain. The fact
     * is still recorded (`lastErrorInfo`) so `[IDLE_KILL]` can name the model as
     * the suspect (AC-002). A non-assistant message leaves the previous
     * assistant fact alone and always feeds the clock. */
    const noteBoundary = (source, view) => {
        if (view !== undefined) {
            lastErrorInfo = view.error ? { error: true, errorMessage: view.errorMessage } : undefined;
            // Any successful assistant boundary disqualifies the D4-patch "first call
            // never returned" reading (the model did answer at least once).
            if (!view.error)
                sawSuccessfulAssistant = true;
        }
        if (view === undefined || !view.error)
            touch(source);
    };
    pi.on("message_update", () => {
        touch("delta");
        lastDeltaAt = Date.now();
    });
    pi.on("message_start", () => touch("message_start"));
    pi.on("message_end", (event) => noteBoundary("message_end", assistantBoundaryInfo(event.message)));
    pi.on("turn_start", () => touch("turn_start"));
    pi.on("turn_end", (event) => noteBoundary("turn_end", assistantBoundaryInfo(event.message)));
    pi.on("agent_start", () => {
        agentRunStarted = true;
        touch("agent_start");
    });
    pi.on("tool_execution_update", (event) => {
        const tool = inFlightTools.get(event.toolCallId);
        if (tool)
            tool.lastActivityAt = Date.now();
        touch("tool_update");
    });
    pi.on("tool_execution_end", (event) => {
        inFlightTools.delete(event.toolCallId);
        touch("tool_end");
    });
    // Track tool calls for trace.log (AC-012) + structured [TOOL]/[TOOL_ERR]
    // progress lines: what the worker is operating on, and where it failed.
    // Read/write counters and target sets feed the convergence checkpoint.
    let toolCallCount = 0;
    let toolErrorCount = 0;
    const toolsUsed = new Set();
    let readCount = 0;
    let writeCount = 0;
    const writeTargets = new Set();
    const readCounts = new Map();
    // T-05/AC-004: write/edit target keyed by toolCallId. `tool_execution_end`
    // carries no args, so the path captured at start is what a successful end
    // records; every end path (error included) clears the entry.
    const pendingWriteTargets = new Map();
    // T-12/F-04: the KNOWN write targets of a shell command, captured at start
    // (the end event carries no args) so a successful bash write is recorded as
    // a change-history event too. Without this a coding worker that writes only
    // through bash left the trace with zero events and the ⊆ judgement went
    // blind (or false-red an honest declaration).
    const pendingBashWrites = new Map();
    pi.on("tool_execution_start", (event) => {
        toolCallCount++;
        toolsUsed.add(event.toolName);
        const toolStartedAt = Date.now();
        inFlightTools.set(event.toolCallId, {
            name: event.toolName,
            startedAt: toolStartedAt,
            lastActivityAt: toolStartedAt,
        });
        touch("tool_start");
        lastToolAt = Date.now();
        const target = toolTarget(event.args);
        if (READ_TOOLS.has(event.toolName)) {
            readCount++;
            if (target)
                readCounts.set(target, (readCounts.get(target) ?? 0) + 1);
        }
        else if (WRITE_TOOLS.has(event.toolName)) {
            writeCount++;
            if (target)
                writeTargets.add(target);
            pendingWriteTargets.set(event.toolCallId, target);
        }
        else if (event.toolName === "bash") {
            const command = event.args?.command;
            if (typeof command === "string" && command.trim() !== "") {
                pendingBashWrites.set(event.toolCallId, classifyLedgerTargets(command));
            }
        }
        appendTrace(meta.taskKey, meta.agenticdocRoot, `tool_call ${event.toolName}`);
        appendTool(meta.taskKey, meta.agenticdocRoot, event.toolName, target);
    });
    pi.on("tool_execution_end", (event) => {
        const writeTarget = pendingWriteTargets.get(event.toolCallId);
        pendingWriteTargets.delete(event.toolCallId);
        const bashWrites = pendingBashWrites.get(event.toolCallId);
        pendingBashWrites.delete(event.toolCallId);
        if (!event.isError) {
            // T-05/AC-004 change history: one `[WRITE_FILE] path=<repo-relative>`
            // event per SUCCESSFUL write/edit, path only (never content). A failed
            // call falls through to the [TOOL_ERR] branch and records nothing.
            const tracePath = path.join(path.resolve(meta.agenticdocRoot, meta.taskKey), "trace.log");
            if (writeTarget !== undefined && writeTarget !== "") {
                appendWriteFileEvent(tracePath, repoRelativePath(writeTarget));
            }
            // T-12/F-04: a successful shell command records its resolved write
            // targets as change-history events, so the bash channel is no longer
            // invisible to the ledger. AC-017/T-02: only a STATICALLY RESOLVED
            // target is a `[WRITE_FILE]`; an unresolved write verb is stated as
            // `[WRITE_UNRESOLVED]` (a trace fact, never a recorded path). An
            // unclassifiable command records nothing — the caller then sees an
            // unjudgeable trace rather than a false green.
            for (const bashTarget of bashWrites?.recorded ?? []) {
                appendWriteFileEvent(tracePath, repoRelativePath(bashTarget));
            }
            for (const unresolvedWrite of bashWrites?.unresolved ?? []) {
                appendUnresolvedWriteEvent(tracePath, unresolvedWrite.pattern, unresolvedWrite.target);
            }
            return;
        }
        toolErrorCount++;
        appendToolError(meta.taskKey, meta.agenticdocRoot, event.toolName, toolErrorText(event.result));
    });
    // Capture last assistant text for output summary (AC-019). Model-error
    // perception (design D1): the same scan records whether the run's final
    // assistant message was an error. agent_end fires once per internal
    // auto-retry attempt, so this is evidence only — counting/resend/exit live on
    // agent_settled.
    let lastAssistantText = "";
    pi.on("agent_end", (event) => {
        let view;
        for (let i = event.messages.length - 1; i >= 0; i--) {
            const msg = event.messages[i];
            if (msg.role === "assistant") {
                const text = msg.content
                    .filter((c) => c.type === "text" && "text" in c)
                    .map((c) => c.text)
                    .join("\n");
                if (text)
                    lastAssistantText = text;
                view = assistantBoundaryInfo(msg);
                break;
            }
        }
        noteBoundary("agent_end", view);
    });
    // Shared terminal bookkeeping: trace [END] with exact runtime + a status
    // line into worker.log (synchronous — survives an immediate process.exit).
    function recordEnd(exitCode) {
        // Single exit-code → status mapping (markOutcome), reused here so the trace
        // line, the persisted record and the marker can never disagree (AC-006).
        const status = markOutcome(exitCode);
        appendEnd(meta.taskKey, meta.agenticdocRoot, {
            exitCode,
            elapsedMs: Date.now() - startedAt,
            toolCalls: toolCallCount,
            phaseDone: meta.phases ? completedPhaseIdx : undefined,
            phaseTotal,
        });
        // AC-007/T-03 (D-115 rule 7): one machine summary per guarded run, after
        // the last audit row and before the terminal status is persisted. Every
        // role with a `write`/`edit` tool or `bash` is guarded now, so every such
        // role writes exactly one line.
        if (bashWriteScopeConfig) {
            appendWriteScopeSummary(meta.taskKey, meta.agenticdocRoot, writeScopeCounts);
        }
        finishRun(status, exitCode);
        writeWorkerLogLine(`[worker] ${status} exit=${exitCode} elapsed=${formatHeartbeatAge(Date.now() - startedAt)} tools=${toolCallCount}${toolErrorCount > 0 ? ` tool_errors=${toolErrorCount}` : ""}${phaseTotal > 0 ? ` phases=${completedPhaseIdx}/${phaseTotal}` : ""}`);
    }
    // Watchdog suite (AC-001/002/003/004, GC-4 as amended 2026-09-09).
    // - idle watchdog: NOTHING moved (no deltas/tools/turns) for idleMs while
    //   the task is unfinished → true hang (dead API call). Detail line records
    //   the discriminating evidence (last delta vs last tool).
    // - wall budget: total runtime exceeded → the task simply needs more time;
    //   the PM reads the Exit Reason and decides retry-with-larger-budget vs
    //   split vs takeover. Wall kills with recent activity are NOT hangs.
    // - convergence checkpoint: past min(30m, budget/2) while unfinished, write
    //   machine evidence + steer the agent to self-assess; refresh every 10m.
    // - deadline steer: near budget end, steer the agent to wrap up and produce
    //   its final reply (→ output.md) instead of dying mid-finalization.
    const budgetMs = resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS);
    const idleMs = resolveIdleMs(process.env.PI_WORKER_IDLE_MS);
    // T-04: the in-flight branch judges the tool-idle clock against this bound
    // (>= the raw idle threshold) so a silent long command is not a hang, while a
    // tool that never reports progress still dies.
    const toolIdleMs = resolveToolIdleMs(idleMs);
    const riskAnchorMs = checkpointAnchorMs(budgetMs);
    let taskDone = false;
    let selfCheckSent = false;
    let lastCheckpoint;
    let checkpointTimer;
    let steerTimer;
    let idleTimer;
    let wallTimer;
    function clearWatchdogTimers() {
        if (idleTimer)
            clearInterval(idleTimer);
        if (wallTimer)
            clearTimeout(wallTimer);
        if (checkpointTimer)
            clearTimeout(checkpointTimer);
        if (steerTimer)
            clearTimeout(steerTimer);
    }
    /** Freshest in-flight tool (max lastActivityAt), or undefined when none. */
    function freshestInFlightTool() {
        let best;
        for (const tool of inFlightTools.values()) {
            if (best === undefined || tool.lastActivityAt > best.lastActivityAt)
                best = tool;
        }
        return best;
    }
    function timeoutExit(kind, detail, modelExhausted = false) {
        taskDone = true;
        clearWatchdogTimers();
        clearInterval(heartbeat);
        appendTimeout(meta.taskKey, meta.agenticdocRoot, kind, detail);
        // Design D4 patch: an idle hang with no in-flight tool and either a prior
        // error boundary or no successful assistant at all is a model-availability
        // verdict, not a generic workflow hang. The existing [IDLE_KILL]/[TIMEOUT]
        // evidence is already on disk; the terminal write reuses the model-exhausted
        // path (exit 3 + run.json model_exhausted:true) so the launcher's same-model
        // retry / fallback chain takes over. A real hung tool and a wall kill keep
        // the exit-1 path below.
        if (modelExhausted) {
            modelExhaustedExit(lastErrorInfo?.errorMessage ?? "model produced no response before the idle timeout");
            return;
        }
        const ckpt = lastCheckpoint
            ? ` (checkpoint: risk=${lastCheckpoint.risk} reads=${lastCheckpoint.reads} writes=${lastCheckpoint.writes} phases=${lastCheckpoint.phases})`
            : "";
        writeOutputGuarded({
            taskKey: meta.taskKey,
            agenticdocRoot: meta.agenticdocRoot,
            exitCode: 1,
            summary: `Worker timed out (${kind}).`,
            exitReason: `${kind} timeout: ${detail}${ckpt}`,
        });
        recordEnd(1);
        outputWritten = true;
        // Kill the bash tool's in-flight child trees before exiting: the
        // watchdog fires while a tool call can still be hung (spinning probe,
        // dead API call mid-command) and Windows descendants survive the
        // parent. Fire-and-forget (detached taskkill / kill(-pgid)); every
        // write above is already synchronous.
        killTrackedDetachedChildren();
        process.exit(1);
    }
    /** T-04/AC-009: best-effort text read for the landing signals (a missing
     * trace/progress file is simply "no signal"). */
    function readTextBestEffort(file) {
        try {
            return fs.readFileSync(file, "utf8");
        }
        catch {
            return "";
        }
    }
    /** T-04/AC-009: the writeless `[CHECKPOINT]` line with the optional landing
     * suffix. Mirrors `appendCheckpoint`'s base fields (worker/output-writer.ts is
     * outside this task's write face) and appends `land=/last_land=/artifact=/
     * done=`; `CHECKPOINT_LINE_RE` (shared/heartbeat.ts) accepts both forms. Write
     * roles keep the byte-identical `appendCheckpoint` path. */
    function appendLandingCheckpoint(opts) {
        const lastLand = opts.landing.lastLandingAgeMs === undefined ? "-" : `${Math.round(opts.landing.lastLandingAgeMs / 1000)}s`;
        const line = `[CHECKPOINT] ${new Date().toISOString()} elapsed=${Math.round(opts.elapsedMs / 1000)}s ` +
            `reads=${opts.reads} writes=${opts.writes} phases=${opts.phases} uniq_targets=${opts.uniqTargets} ` +
            `repeat_top=${opts.repeatTop} risk=${opts.risk} land=${opts.landing.landed} last_land=${lastLand} ` +
            `artifact=${opts.landing.artifactPresent ? "yes" : "no"} done=${opts.landing.progressDone ? "yes" : "no"}`;
        try {
            const dir = path.resolve(meta.agenticdocRoot, meta.taskKey);
            fs.mkdirSync(dir, { recursive: true });
            fs.appendFileSync(path.join(dir, "trace.log"), `${line}\n`, "utf8");
        }
        catch {
            // Diagnostic append — best effort, same contract as appendCheckpoint.
        }
    }
    /** Machine convergence evidence for the checkpoint line (AC-004). Risk is
     * advisory only — the PM (fullest context) judges and decides. */
    function writeCheckpoint() {
        const elapsedMs = Date.now() - startedAt;
        let repeatTop = 0;
        for (const n of readCounts.values())
            repeatTop = Math.max(repeatTop, n);
        const phasesStr = phaseTotal > 0 ? `${completedPhaseIdx}/${phaseTotal}` : "-";
        const taskDir = path.dirname(taskPath);
        // T-04/AC-009: landing signals are writeless-only, so a write role's
        // checkpoint does no extra I/O and its result stays byte-identical.
        const landing = hasWriteTool
            ? undefined
            : collectLandingSignals({
                taskDir,
                traceText: readTextBestEffort(path.join(taskDir, "trace.log")),
                progressText: readTextBestEffort(path.join(taskDir, "progress.md")),
                startedAtMs: startedAt,
                nowMs: startedAt + elapsedMs,
            });
        const risk = computeRisk({
            elapsedMs,
            anchorMs: riskAnchorMs,
            writes: writeCount,
            phasesTotal: phaseTotal,
            phasesDone: completedPhaseIdx,
            repeatTop,
            ...(landing ?? {}),
        });
        if (landing === undefined) {
            appendCheckpoint(meta.taskKey, meta.agenticdocRoot, {
                elapsedMs,
                reads: readCount,
                writes: writeCount,
                phases: phasesStr,
                uniqTargets: writeTargets.size,
                repeatTop,
                risk,
            });
        }
        else {
            appendLandingCheckpoint({
                elapsedMs,
                reads: readCount,
                writes: writeCount,
                phases: phasesStr,
                uniqTargets: writeTargets.size,
                repeatTop,
                risk,
                landing,
            });
        }
        lastCheckpoint = { risk, reads: readCount, writes: writeCount, phases: phasesStr };
        // Machine line: written by code (D-104/D-105) for roles with no write tool;
        // the self-assessment line goes through worker_file or the reply, per role.
        // Write roles keep the pre-change behavior byte for byte (no [machine] line).
        if (!hasWriteTool) {
            appendProgressLine(meta.taskKey, meta.agenticdocRoot, formatMachineCheckpoint({
                elapsedMs,
                reads: readCount,
                writes: writeCount,
                phases: phasesStr,
                repeatTop,
                risk,
            }));
        }
        // Self-assessment steer. sendUserMessage with deliverAs: while the agent is
        // mid-run (tool call or generation) a bare call throws "Agent is already
        // processing" — followUp queues the steer as its own turn after the current
        // one, so in-flight work is never disrupted (smoke-validated 2026-09-09).
        // Both role branches keep followUp; only the wording differs (VC-004).
        pi.sendUserMessage(checkpointSteerText({
            elapsedMs,
            budgetMs,
            progressPath: path.join(taskDir, "progress.md"),
            hasWriteTools: hasWriteTool,
            narrowTool: WORKER_FILE_TOOL,
        }), { deliverAs: "followUp" });
    }
    function scheduleCheckpoint(delayMs) {
        checkpointTimer = setTimeout(() => {
            if (taskDone)
                return;
            writeCheckpoint();
            scheduleCheckpoint(CHECKPOINT_REFRESH_MS);
        }, delayMs);
        checkpointTimer.unref();
    }
    scheduleCheckpoint(riskAnchorMs);
    steerTimer = setTimeout(() => {
        if (taskDone)
            return;
        // deliverAs "steer": urgent — inject into the CURRENT turn so the model
        // sees the wrap-up directive at its next opportunity, mid-turn.
        pi.sendUserMessage(`[mw deadline] 预算还剩约 ${formatHeartbeatAge(budgetMs - steerAtMs(budgetMs))}。立即停止开始新工作：完成当前最小步骤后收尾，最终回复中列出已完成/未完成/后续建议（会被存为 output.md 摘要）。最终回复第一行必须是单行结论（状态 + 关键产出/卡点）。`, { deliverAs: "steer" });
    }, steerAtMs(budgetMs));
    steerTimer.unref();
    idleTimer = setInterval(() => {
        if (taskDone)
            return;
        const now = Date.now();
        const idleForMs = now - lastActivityAt;
        // B (T-04): while a tool is in flight, judge the TOOL-idle clock, not raw
        // activity. A silent long bash is not a hung worker; the tool's own
        // heartbeat (core/tools/bash.ts) keeps this clock fresh. The bound keeps a
        // genuinely hung tool killable (C/VC-006).
        const inFlight = freshestInFlightTool();
        if (inFlight !== undefined) {
            const toolIdleForMs = now - inFlight.lastActivityAt;
            if (toolIdleForMs < toolIdleMs)
                return;
            const toolRunS = Math.round((now - inFlight.startedAt) / 1000);
            const written = appendIdleKillEvidence(meta.taskKey, meta.agenticdocRoot, {
                toolInFlight: inFlight.name,
                toolRunS,
                toolIdleS: Math.round(toolIdleForMs / 1000),
                silenceS: Math.round(idleForMs / 1000),
                thresholdS: Math.round(toolIdleMs / 1000),
                thresholdKind: "tool_idle",
                lastActivity: lastActivitySource,
                lastModelError: lastErrorInfo !== undefined,
            });
            if (!written)
                return; // no evidence -> no kill
            timeoutExit("idle", `in-flight tool ${inFlight.name} silent for ${Math.round(toolIdleForMs / 1000)}s (tool running ${toolRunS}s, threshold ${Math.round(toolIdleMs / 1000)}s, last activity ${lastActivitySource})`);
            return;
        }
        if (idleForMs < idleMs)
            return;
        // C (T-04): the no-in-flight branch keeps the existing judgement, with a
        // second confirmation that the token-delta clock is stale too — a recent
        // delta is the one signal that separates a slow generation from a dead
        // connection, so a genuinely hung worker is still killed (VC-006).
        const deltaIdleMs = lastDeltaAt === undefined ? Number.POSITIVE_INFINITY : now - lastDeltaAt;
        if (deltaIdleMs < idleMs)
            return;
        const written = appendIdleKillEvidence(meta.taskKey, meta.agenticdocRoot, {
            toolInFlight: "none",
            toolRunS: null,
            toolIdleS: null,
            silenceS: Math.round(idleForMs / 1000),
            thresholdS: Math.round(idleMs / 1000),
            thresholdKind: "idle",
            lastActivity: lastActivitySource,
            lastModelError: lastErrorInfo !== undefined,
        });
        if (!written)
            return; // no evidence -> no kill
        const d = lastDeltaAt === undefined ? "-" : `${Math.round((now - lastDeltaAt) / 1000)}`;
        const t = lastToolAt === undefined ? "-" : `${Math.round((now - lastToolAt) / 1000)}`;
        // Design D4 patch: with no in-flight tool the worker is stuck waiting on an
        // LLM call. If this process already saw an error boundary, or its agent loop
        // started and never produced a successful assistant, the hang is a
        // model-availability verdict (exit 3 -> launcher retry/fallback) rather than
        // a generic worker hang. A real hung tool keeps the exit-1 path above.
        const modelExhausted = lastErrorInfo !== undefined || (!sawSuccessfulAssistant && agentRunStarted);
        timeoutExit("idle", `no activity for ${Math.round(idleForMs / 1000)}s (last delta ${d}s ago, last tool ${t}s ago)`, modelExhausted);
    }, 30_000);
    idleTimer.unref();
    wallTimer = setTimeout(() => {
        if (taskDone)
            return;
        const sinceAct = Math.round((Date.now() - lastActivityAt) / 1000);
        timeoutExit("wall", `budget ${Math.round(budgetMs / 1000)}s exceeded (last activity ${sinceAct}s ago)`);
    }, budgetMs);
    wallTimer.unref();
    // Phase state machine: track how many phases have been dispatched and completed.
    // - initialSettled: true once the first agent_settled fires (after pi -p <task_content>)
    // - nextPhaseIdx: index of the next phase prompt to send (or phases.length when all sent)
    // - completedPhaseIdx: index of the phase whose output should be written on current settle
    // - phaseMachineComplete: the last phase's output/goal-check was already written.
    //   `taskDone` alone cannot carry this any more: a dp3 auto-answer keeps the
    //   process alive past the final settle, so a later settle must NOT re-emit
    //   `[GOAL_CHECK]`/`[PHASE] done` for a phase that already landed (invariant 5).
    let initialSettled = false;
    let nextPhaseIdx = 0;
    let completedPhaseIdx = 0;
    let phaseMachineComplete = false;
    const phases = meta.phases;
    // Heartbeat: a [HEARTBEAT] line every HEARTBEAT_INTERVAL_MS, written by pure
    // code (this timer, not the LLM) so liveness evidence continues while the
    // agent is mid-generation with no tool calls (design D-003). Phase progress
    // is read at tick time; unref'd so it never holds the event loop, cleared on
    // every exit path below.
    const heartbeat = setInterval(() => {
        appendHeartbeat(meta.taskKey, meta.agenticdocRoot, phases && phases.length > 0 ? `${completedPhaseIdx}/${phases.length}` : "-");
        // Same tick refreshes the product-carried liveness stamp: a reader that
        // has only run.json can still tell a live run from a dead one (D-022).
        runState.last_heartbeat_at = new Date().toISOString();
        writeRunState(taskDir, runState);
    }, HEARTBEAT_INTERVAL_MS);
    heartbeat.unref();
    function buildSummary() {
        const base = lastAssistantText || "Task completed.";
        const tools = toolsUsed.size > 0 ? ` Tools used: ${[...toolsUsed].sort().join(", ")} (${toolCallCount} calls).` : "";
        return `${base}${tools}`;
    }
    /** T-04b: mtime of this run's task.md — the clock the AC-008 ⑥
     * `carried-from` check compares evidence citations against ("written before
     * this task book existed" = a previous round's artifact). `undefined` when
     * the file is unreadable: the check then skips rather than inventing a clock. */
    function taskMtimeMs() {
        try {
            return fs.statSync(taskPath).mtimeMs;
        }
        catch {
            return undefined;
        }
    }
    /** T-04b: the claim gaps this settle would report. Same criteria list
     * `readTerminalGaps` folds (`claimCoverage`) PLUS the three AC-008 checks that
     * need worker-only inputs; used by the pre-settle self-check, which must name
     * the un-settled claims BEFORE the terminal write exists. `[]` for a
     * claims-free book (zero branches). */
    function claimGapsHere(summary) {
        if (meta.claims === undefined)
            return [];
        const table = parseVerdictTable(agentProductText(taskDir, summary));
        return [
            ...claimCoverage(meta.claims, table, { projectDir: process.cwd() }),
            ...claimSettlementGaps({
                claims: meta.claims,
                table,
                role: roleForTaskType(meta.type),
                traceReads: readCount,
                taskMtimeMs: taskMtimeMs(),
                projectDir: process.cwd(),
            }),
        ];
    }
    /** AC-007/DD-09: the effort half of `## Exit Reason` — which product file this
     * run actually wrote, taken from the live write-tool targets (not from disk, so
     * it reflects what the agent did even when the file was later removed). The
     * value domain is fixed: the two canonical products, or `none`. */
    function writesLabel() {
        const bases = new Set([...writeTargets].map((t) => path.basename(t.replace(/[\\/]+$/, ""))));
        if ([...bases].some((b) => b === "report.md" || /^report-.+\.md$/.test(b)))
            return "report.md";
        if (bases.has("progress.md"))
            return "progress.md";
        return "none";
    }
    /** T-05: the header `type:` the recovery contract judges (undefined on a
     * legacy/manual book, P-07/P-09 — the same resolution `readTerminalGaps`
     * performs when no type is passed). */
    const judgedTypeReading = readTaskType(taskContent);
    const judgedType = judgedTypeReading.source === "header" ? judgedTypeReading.type : undefined;
    /** Is the AC-003 recovery contract applied to this run at all? A writeless
     * role's reply IS its deliverable, so it is always judged; a write role is
     * judged once it produced a report product (`report.md` or
     * `report-<slug>.md`, AC-015) — otherwise the AC-006/C5 exemption stands (a
     * coding run's deliverable is the repository, and its terse settle summary is
     * not a report). */
    function judgeRecoveryHere() {
        return judgedType !== undefined && (isWritelessRole(meta.type) || hasReportProduct(taskDir));
    }
    // dp3 state: the process-level budget (`Dp3Attempted`) bounds the auto-answer
    // to ONE follow-up round per run, so a second NC can never loop (design Q4.3);
    // the two counters are the `nc_raw` / `nc_human` metric pair (Q3.3).
    let dp3RawClarifications = 0;
    let dp3HumanClarifications = 0;
    let dp3AutoAnswered = false;
    /** Insert-point hook for dp3 (`finishSuccess`, after `exitCode`, before
     * `writeOutputGuarded`). Returns true when an auto-answer was injected — the
     * caller then returns WITHOUT writing any terminal product. Every other path
     * (3b, suggest, all four degradations, budget spent) returns false and the
     * original human path proceeds byte-identically. Never throws. */
    function attemptDp3Clarification(harnessDetail) {
        try {
            const projectDir = process.cwd();
            const policy = readDp3Policy(projectDir);
            // D-007 complete bypass: a disabled dp3 performs ZERO spawn and ZERO write
            // (not even a trace row), which is what keeps the closed state identical.
            if (!policy.enabled)
                return false;
            dp3RawClarifications += 1;
            const triggerId = `${meta.taskKey}#nc${dp3RawClarifications}`;
            const decisionId = `${DP3_ID}:${triggerId}`;
            if (dp3AutoAnswered) {
                // Budget spent: never ask the service twice — the human path resumes.
                dp3HumanClarifications += 1;
                appendTrace(meta.taskKey, meta.agenticdocRoot, formatDp3TraceLine({
                    triggerId,
                    acted: false,
                    mode: policy.mode,
                    escalatedReason: "-",
                    decisionId,
                    ncRaw: dp3RawClarifications,
                    ncHuman: dp3HumanClarifications,
                }));
                return false;
            }
            const risk = lastCheckpoint?.risk ?? "mid";
            const decision = decideDp3WorkerClarify({
                projectDir,
                taskKey: meta.taskKey,
                ncIndex: dp3RawClarifications,
                key: path.basename(path.dirname(meta.agenticdocRoot)),
                phase: meta.phase ?? "EXECUTE",
                taskType: dp3TaskType(meta.type),
                risk,
                riskSource: lastCheckpoint === undefined ? "pm-label" : "machine",
                question: lastAssistantText,
                harnessDetail,
                taskDir,
                taskPath,
                taskContent,
                trueRoot: meta.trueAgenticdocRoot,
                keyDir: path.dirname(meta.agenticdocRoot),
                policy,
                runner: options?.dp3Runner,
            });
            if (decision.kind === "answer" && decision.detail !== undefined) {
                // FIX-J §5: which local candidate was consumed and from where. The frozen
                // `[DECIDE]` row keeps its key order, so the detail rides its own line.
                appendTrace(meta.taskKey, meta.agenticdocRoot, `[DECISION] dp3 detail=${decision.detail}`);
            }
            if (decision.kind === "answer" && decision.mode === "auto") {
                // D-041: adoption happens HERE, at the point that injects the steer.
                // The child's own `acted` only says Python did not execute the action
                // itself; the auto-answered clarification IS the consumed decision.
                // `decision.mode` is Python's verdict on the spawned path (D-036).
                const actedDecision = { ...decision, acted: true };
                dp3AutoAnswered = true;
                appendTrace(meta.taskKey, meta.agenticdocRoot, formatDp3TraceLine({
                    triggerId,
                    sub: actedDecision.sub,
                    acted: actedDecision.acted === true,
                    mode: actedDecision.mode,
                    escalatedReason: "-",
                    decisionId: actedDecision.decisionId,
                    ncRaw: dp3RawClarifications,
                    ncHuman: dp3HumanClarifications,
                }));
                // Association marker (same shape dp2 uses): the one line a settle/
                // report can correlate without parsing the frozen `[DECIDE]` row.
                appendTrace(meta.taskKey, meta.agenticdocRoot, `[DECISION] dp3 acted=1 decision_id=${actedDecision.decisionId}`);
                // The steer carrier (design Q3): a settle-time follow-up turn, the same
                // mechanism the recovery self-check uses. The original question is never
                // rewritten and `## Questions` is not written at all yet.
                pi.sendUserMessage(formatDp3AnswerSteer(actedDecision, lastAssistantText), { deliverAs: "followUp" });
                return true;
            }
            // Every other outcome is the human path: 3b by default, `suggest` mode,
            // low confidence, unavailable service, incomplete input, budget spent.
            dp3HumanClarifications += 1;
            appendTrace(meta.taskKey, meta.agenticdocRoot, formatDp3TraceLine({
                triggerId,
                sub: decision.sub,
                acted: false,
                mode: decision.kind === "answer" ? decision.mode : policy.mode,
                escalatedReason: decision.kind === "escalate" ? decision.reason : "-",
                decisionId,
                ncRaw: dp3RawClarifications,
                ncHuman: dp3HumanClarifications,
            }));
            return false;
        }
        catch {
            // Structural fail-soft: a bug in the dp3 hook must never change the
            // terminal verdict. The caller falls through to the original NC path.
            return false;
        }
    }
    /** Success path. Does NOT process.exit: this handler runs inside pi's
     * agent_settled emit — returning lets pi's print mode resolve, print the
     * final assistant message to stdout (captured as worker.log), flush, and
     * exit with its own code. Exiting here was why worker.log stayed empty:
     * process.exit truncates the pending stdout flush. */
    function finishSuccess() {
        // AC-010②: a second settle in the same process is a no-op — without this the
        // append-only writer (output-writer.ts D-117) adds a second harness block,
        // a second `[END]` and (for an NC run) a second no-product alarm.
        // The terminal lock itself is taken LOWER DOWN, after the dp3 clarification
        // hook: an auto-answered NC must return with the run still open (T-06).
        if (taskDone)
            return;
        // dp2 narrow steer (T-07b): a request that arrived while this turn was
        // running is consumed HERE, before the terminal write-out. It is injected as
        // a followUp and the run stays OPEN (no terminal product, timers armed), so
        // the queued turn actually executes — the same carrier dp3 uses. The
        // consumed marker bounds this to one extra turn per request.
        if (consumeDp2NarrowSteer("settle"))
            return;
        // AC-006 (contract C5): a writeless role that settles without a product is
        // needs-clarification, not done. Judged here — before the single write-out —
        // so the output.md marker, `## Questions`, run.json.status and `[END] exit=`
        // all carry the same verdict. Write roles are exempt: a coding run's
        // deliverable is the repository, not a file in its own task dir.
        const evidence = isWritelessRole(meta.type)
            ? hasDeliverableEvidence(taskDir, lastAssistantText)
            : { delivered: true, channel: "none", detail: "write role" };
        // AC-003/AC-004 terminal flip (T-07): the recovery contract and the change
        // ledger are judged HERE, before the single write-out, and folded into the
        // exit code — so the output.md marker, `## Questions`, run.json.status and
        // `[END] exit=` all carry the same verdict. Migration: a task book without
        // a header `type:` is never judged (P-07/P-09), and a trace with no
        // `[WRITE_FILE]` event yields no ledger gap.
        // Recovery scope: a writeless role's reply IS its deliverable, so it is
        // always judged; a write role is judged once it produced a report product
        // (`report.md` or `report-<slug>.md`, AC-015) — otherwise the AC-006/C5
        // exemption stands (a coding run's deliverable is the repository, and its
        // terse settle summary is not a report). The change ledger below is judged
        // for every role.
        const judgeRecovery = judgeRecoveryHere();
        // T-05/I2 (AC-005): append the mechanical `## 上下文来源` to the file the
        // judgement is about to read — BEFORE `readTerminalGaps`, so the judged text
        // and the landed product cannot diverge (invariant I1). Only the mechanical
        // whitelist is ever filled (R2); every failure class stays fail-closed.
        if (judgeRecovery) {
            const backfill = appendMechanicalContextSources({
                taskKey: meta.taskKey,
                agenticdocRoot: meta.agenticdocRoot,
                summary: buildSummary(),
                type: judgedType,
            });
            if (backfill.appended) {
                appendTrace(meta.taskKey, meta.agenticdocRoot, `recovery-backfill section=上下文来源 target=${path.basename(backfill.target ?? "")} ok=${backfill.ok}`);
            }
        }
        const gaps = readTerminalGaps({
            taskKey: meta.taskKey,
            agenticdocRoot: meta.agenticdocRoot,
            summary: buildSummary(),
            judgeRecovery,
            // T-04b/D-003: the card's claim set (from task.md) rides the SAME single
            // decision point as the recovery contract and the change ledger. Absent
            // (`undefined`) ⇒ `readTerminalGaps` returns a field-identical verdict to
            // the pre-claim one, so a claims-free book keeps this path byte-identical.
            claims: meta.claims,
        });
        // ── AC-008 settlement criteria (T-04b) ─────────────────────────────────
        // ② unverified share, ③ Σ取数 upper bounds and ⑥ carried-from need inputs
        // only this layer holds (role, run clock, trace read count), so they are
        // computed here and folded into the SAME `gaps` object. No second decision
        // point and no reordering: the ONE terminal fold below (`delivered &&
        // gaps.ok`) stays the only place an exit code is decided, and
        // `worker/output-*.ts` stay frozen (T-04a owns the per-claim criteria).
        const claimsTable = meta.claims === undefined ? undefined : parseVerdictTable(agentProductText(taskDir, buildSummary()));
        if (meta.claims !== undefined && claimsTable !== undefined && judgeRecovery) {
            const settlementGaps = claimSettlementGaps({
                claims: meta.claims,
                table: claimsTable,
                role: roleForTaskType(meta.type),
                traceReads: readCount,
                taskMtimeMs: taskMtimeMs(),
                projectDir: process.cwd(),
            });
            if (settlementGaps.length > 0) {
                gaps.claimGaps = [...(gaps.claimGaps ?? []), ...settlementGaps];
                gaps.ok = false;
            }
        }
        const exitCode = evidence.delivered && gaps.ok ? 0 : 2;
        // AC-007/DD-09: carry the settle-time artifacts into the product so a
        // `## Deliverables` section can list them (the writer drops output.md and
        // progress.md, and omits the section when nothing is left).
        const effort = `writes=${writesLabel()}`;
        const gapReason = gaps.missingSections.length > 0 ? `missing section(s): ${gaps.missingSections.join(", ")}` : "";
        const ledgerReason = gaps.unrecordedFiles.length > 0 ? `unrecorded write(s): ${gaps.unrecordedFiles.join(", ")}` : "";
        // T-12/F-04: zero write events with a declaration is unjudgeable, not a
        // pass — name it so the settle reason and the exit code agree.
        const unjudgeableReason = gaps.unjudgeableFiles.length > 0
            ? `unjudgeable write(s) (trace has no [WRITE_FILE] event): ${gaps.unjudgeableFiles.join(", ")}`
            : "";
        // T-04b: the claim half of the settle reason. `claimGaps` exists only when
        // the run carries a claim contract, so a claims-free book keeps this list —
        // and therefore `## Questions` / `## Exit Reason` — byte-identical.
        const claimIds = claimGapIds(gaps.claimGaps ?? []);
        const claimReason = claimIds.length > 0
            ? `unsettled claim(s): ${claimIds.join(", ")}`
            : (gaps.claimGaps?.length ?? 0) > 0
                ? `unsettled claims: ${(gaps.claimGaps ?? []).join(", ")}`
                : "";
        const gapsReason = [gapReason, ledgerReason, unjudgeableReason, claimReason]
            .filter((part) => part !== "")
            .join("; ");
        // The exact `## Questions` body this run would land. It is computed ONCE so
        // the dp3 hook and the original human path read the same string: every
        // degradation falls through with this value byte-identical (design Q4.1).
        const questionsText = evidence.delivered
            ? gaps.ok
                ? undefined
                : `recovery-incomplete: ${gapsReason}`
            : `no-product: ${evidence.detail}`;
        // ── dp3 clarification substitution (mw-decision-substitution T-06) ──────
        // The ONLY insertion point (design Q1.2): every dp3 input is in scope here
        // (`evidence`, `gaps`, `lastAssistantText`), the NC product is NOT written
        // yet, the terminal run record is not committed, and this process can still
        // continue the same run. An auto-answer returns WITHOUT closing the run:
        // `taskDone` stays false and the watchdog/heartbeat timers stay armed, so the
        // next settle re-judges the same predicates and only the human path (or a
        // delivered product) commits a terminal state.
        if (exitCode === 2 && attemptDp3Clarification([evidence.detail, gapsReason].filter((p) => p !== "").join("; "))) {
            return;
        }
        // Terminal from here on: take the lock, stop the liveness timers and land
        // the single write-out exactly as before (byte-identical when dp3 is off).
        taskDone = true;
        clearWatchdogTimers();
        clearInterval(heartbeat);
        writeOutputGuarded({
            taskKey: meta.taskKey,
            agenticdocRoot: meta.agenticdocRoot,
            exitCode,
            summary: buildSummary(),
            changedFiles: collectArtifacts(taskDir),
            verificationSteps: "See task output for details.",
            exitReason: evidence.delivered
                ? gaps.ok
                    ? `Agent settled after ${toolCallCount} tool call(s). ${effort}`
                    : `Agent settled after ${toolCallCount} tool call(s) without a recoverable product (${gapsReason}). ${effort}`
                : `Agent settled after ${toolCallCount} tool call(s) without a deliverable: ${evidence.detail} ${effort}`,
            questions: questionsText,
            terminalGaps: gaps,
        });
        if (!evidence.delivered) {
            // The ledger root is the TRUE `.agenticdoc` root (meta.trueAgenticdocRoot),
            // never `<key>/workers` (meta.agenticdocRoot) — the latter would scatter the
            // row into a directory no consumer reads.
            recordDispatchAlarm(meta.trueAgenticdocRoot, {
                kind: "no-product",
                count: 1,
                detail: `${meta.taskKey}:${evidence.channel}`,
            });
        }
        // VC-014 (AC-010): warning-only required-but-unused marker. ragRuntime is
        // null on an RAG-less project, so this is a structural zero-write no-op.
        if (ragRuntime !== null) {
            emitRagRequiredMissing({
                config: ragRuntime.config,
                taskType: meta.type,
                phase: evidencePhase(meta.phase),
                outputText: lastAssistantText,
                keyDir: path.dirname(meta.agenticdocRoot),
                taskDir: path.dirname(taskPath),
            });
        }
        // T-04b/AC-008: the independent `[CLAIMS]` evidence row (design D-004 — a
        // line of its own, never folded into `[END]`) and the `run.json` `claims`
        // subobject T-05 reads back. Written ONCE per run, immediately before the
        // terminal bookkeeping (`recordEnd` -> `[END]` + `finishRun`), so the trace
        // line and the persisted record carry the same counters. A claims-free book
        // writes NEITHER (no line, no key: T-05 treats an absent key as "not
        // measured" and renders n/a instead of a fabricated zero).
        if (meta.claims !== undefined && claimsTable !== undefined) {
            const counts = claimCounts(meta.claims, claimsTable, readCount);
            runState.claims = counts;
            appendClaimsTraceLine(meta.taskKey, meta.agenticdocRoot, counts);
        }
        recordEnd(exitCode);
        outputWritten = true;
    }
    /** T-05/I1 (AC-004): the pre-settle self-check. On the final settle attempt
     * the worker gets ONE structured gap (the missing section names, or nothing
     * when `ok`) and is asked to fill it in its own product; the run then settles
     * again on its actual text. Only substantive gaps trigger the turn — a
     * mechanical-only gap is handled by the I2 backfill inside `finishSuccess`, so
     * burning an agent turn for it would be pure cost. One turn per process.
     * T-13/D-015 (option C): the round is gated on DELIVERED, not on a product
     * file on disk — a writeless run whose reply IS its deliverable gets one
     * chance to fix a substantive gap; an undelivered (no-product) settle keeps
     * the immediate no-product verdict (AC-006/C5 alarm is never delayed). */
    function settleOrSelfCheck() {
        if (judgedType !== undefined && (isWritelessRole(meta.type) || hasReportProduct(taskDir))) {
            const summary = buildSummary();
            const missing = currentRecoveryMissing({
                taskKey: meta.taskKey,
                agenticdocRoot: meta.agenticdocRoot,
                summary,
                type: judgedType,
            });
            // T-04b: claim gaps are a SEPARATE list with a separate render, but they
            // share this trigger and the one-shot `selfCheckSent` state (design §3.3:
            // no second boolean — the I1 invariant is "one self-check turn per
            // process", not "one per criterion family").
            const claimGaps = claimGapsHere(summary);
            const claimIds = claimGapIds(claimGaps);
            // Parseable machine record of the gap the worker is about to receive
            // (AC-004): `[FLOW] <ts> recovery-gap missing=<a|b> selfcheck=<...>`.
            // The claim half is appended only when the run has an unsettled claim, so
            // a claims-free book keeps the line byte-identical.
            appendTrace(meta.taskKey, meta.agenticdocRoot, `recovery-gap missing=${missing.length > 0 ? missing.join("|") : "-"} selfcheck=${selfCheckSent ? "sent" : "pending"}${claimGaps.length > 0 ? ` claims=${claimIds.length > 0 ? claimIds.join("|") : "-"}` : ""}`);
            const substantive = missing.filter((name) => !isMechanicalSection(name));
            // T-13/D-015 (option C): the follow-up turn exists so the agent can fix
            // the product the judgement will read. The gate is the SAME predicate
            // finishSuccess uses for the deliverable verdict — for a writeless role
            // that is `hasDeliverableEvidence(taskDir, lastAssistantText).delivered`
            // (its reply IS its deliverable), for a write role the outer
            // judgeRecoveryHere()/hasReportProduct guard already proves a product
            // exists, so it is delivered by construction. A run that settled with
            // no deliverable takes the AC-006/C5 no-product verdict instead —
            // granting an extra turn would turn the no-product signal into an open
            // loop. The parseable trace row above is still written for every judged
            // settle.
            const isDelivered = isWritelessRole(meta.type)
                ? hasDeliverableEvidence(taskDir, lastAssistantText).delivered
                : true;
            if (!selfCheckSent && (substantive.length > 0 || claimGaps.length > 0) && isDelivered) {
                selfCheckSent = true;
                const recoveryText = substantive.length > 0
                    ? `你的产物缺少恢复契约段：${substantive.join("、")}。请在 report.md / output.md 中用 \`## <段名>\` 标题补上这些段落`
                    : "";
                // AC-008 ②/⑥ and the per-claim criteria: name the FIRST un-settled claim
                // id so the agent has one concrete row to fix first, then the machine
                // tokens behind it.
                const claimText = claimGaps.length > 0
                    ? `产物中的 \`## 断言裁决\` 未结算 ${claimIds.length > 0 ? claimIds.join("、") : "-"}（首个缺失 claim id：${claimIds[0] ?? "-"}），缺项：${claimGaps.join("; ")}`
                    : "";
                // Reuse the checkpoint steer carrier (followUp): the agent is settled,
                // so this queues one more turn instead of resuming mid-generation.
                // A claims-free run keeps the pre-T-04b sentence byte for byte.
                const steerText = claimText === ""
                    ? `${recoveryText}，然后重新收尾；本进程只自检一次，之后按实际产物判定。`
                    : `${[recoveryText, claimText].filter((part) => part !== "").join("；另：")}。然后重新收尾；本进程只自检一次，之后按实际产物判定。`;
                pi.sendUserMessage(`[mw recovery self-check] ${steerText}`, { deliverAs: "followUp" });
                return;
            }
        }
        finishSuccess();
    }
    /** AC-004 chain: every model the launcher moved through plus the current one.
     * Each worker process contributes exactly one error run (the process is the
     * retry unit now), so `runs` is the literal 1; same-model retries and the
     * fallback chain are counted by the launcher from trace.log
     * (`[MODEL_RETRY]`/`[MODEL_FALLBACK]`). */
    function modelErrChain() {
        const models = [...triedModels];
        if (currentModelLabel !== "" && !models.includes(currentModelLabel))
            models.push(currentModelLabel);
        return models.map((model) => ({ model, runs: 1 }));
    }
    /** Bounded model-exhausted exit (design D1/D3 修订版 D6, mirrors `timeoutExit`):
     * all evidence is written synchronously, then the process exits 3 so the
     * launcher can run the same-model retry / next-fallback step. Reached from the
     * first error settle (process-level retry unit, revised 2026-10-15: no worker
     * budget, no in-process followUp resend — it never ran in print mode) and from
     * the D4-patch hang classification. Never reaches `finishSuccess` (AC-003). */
    function modelExhaustedExit(lastError) {
        taskDone = true;
        clearWatchdogTimers();
        clearInterval(heartbeat);
        // Protocol extension (plan §3 / design §4): the terminal run record carries
        // the machine-readable flag the PM polls for (D7).
        runState.model_exhausted = true;
        const phasesLabel = phaseTotal > 0 ? `${completedPhaseIdx}/${phaseTotal}` : "-";
        const summary = `${truncateModelErrText(lastAssistantText || "Model exhausted before producing output.")} phases=${phasesLabel}`;
        writeOutputGuarded({
            taskKey: meta.taskKey,
            agenticdocRoot: meta.agenticdocRoot,
            exitCode: 3,
            summary,
            changedFiles: collectArtifacts(taskDir),
            exitReason: formatModelUnavailableReason(modelErrChain(), lastError),
        });
        recordEnd(3);
        outputWritten = true;
        killTrackedDetachedChildren();
        process.exit(3);
    }
    pi.on("agent_settled", () => {
        try {
            // AC-010②: this handler is the settle entry point; once finishSuccess has
            // run (taskDone), later settles must not re-write phase files, re-emit
            // goal checks or append another output.md block. Phased tasks keep
            // taskDone === false until the final finishSuccess, so the phase machine
            // below is unaffected.
            if (taskDone)
                return;
            // Model-error branch (design §3.1 / D1/D3/D4, revised 2026-10-15): an error
            // settle must never advance the phase machine or reach the success path
            // (AC-003), so it sits ahead of EVERY initialSettled / phase /
            // settleOrSelfCheck branch. It records the [MODEL_ERR] evidence and exits 3
            // immediately; the launcher owns same-model retries and the fallback chain.
            if (lastErrorInfo !== undefined) {
                // Capture the error text before the fact is consumed so exit 3 (AC-004)
                // and the `[MODEL_ERR]` line report the SAME final errorMessage.
                const lastErrorText = lastErrorInfo.errorMessage ?? "error";
                // Task-mandated carrier: appendTrace (`[MODEL_ERR] <iso> model=<p/m>
                // run=1 err=<≤200>`), one line per error agent run — never from
                // agent_end, which fires once per internal auto-retry attempt. Every
                // process is exactly one error run now, so `run` is the literal 1.
                appendTrace(meta.taskKey, meta.agenticdocRoot, `[MODEL_ERR] ${new Date().toISOString()} model=${currentModelLabel === "" ? "unknown" : currentModelLabel} run=1 err=${truncateModelErrText(lastErrorText)}`);
                // Consume the fact (the next agent_end refreshes it) so one error
                // boundary can never be counted twice.
                lastErrorInfo = undefined;
                modelExhaustedExit(lastErrorText);
                return;
            }
            if (!initialSettled) {
                initialSettled = true;
                // Initial task prompt (from pi -p) has settled
                if (phases && phases.length > 0) {
                    // Send first phase prompt
                    appendPhase(meta.taskKey, meta.agenticdocRoot, "start", 1, phases.length, phases[0].name);
                    pi.sendUserMessage(phases[0].prompt);
                    nextPhaseIdx = 1;
                    return;
                }
                // No phases — self-check, then write output and let pi exit naturally
                settleOrSelfCheck();
                return;
            }
            // A phase just completed: write its output file and goal-check trace. The
            // guard keeps a post-dp3-answer settle from re-processing a finished phase.
            if (phases && !phaseMachineComplete) {
                const phaseIndex = completedPhaseIdx;
                writePhaseFile(meta.taskKey, meta.agenticdocRoot, phaseIndex, lastAssistantText || `Phase ${phaseIndex + 1} complete`);
                // D-116: goal.md lives in the TRUE .agenticdoc root (task.md four
                // levels up) — meta.agenticdocRoot is the workers dir and would stat
                // {owner}/workers/goal.md, a guaranteed miss ([GOAL_CHECK] recorded 0).
                appendGoalCheck(meta.taskKey, meta.agenticdocRoot, phaseIndex + 1, goalMtime(meta.trueAgenticdocRoot));
                completedPhaseIdx++;
                appendPhase(meta.taskKey, meta.agenticdocRoot, "done", phaseIndex + 1, phases.length);
                if (nextPhaseIdx < phases.length) {
                    // More phases — send next prompt
                    const next = phases[nextPhaseIdx];
                    appendPhase(meta.taskKey, meta.agenticdocRoot, "start", nextPhaseIdx + 1, phases.length, next.name);
                    pi.sendUserMessage(next.prompt);
                    nextPhaseIdx++;
                    return;
                }
                phaseMachineComplete = true;
            }
            // All phases done (or no phases after initial settle)
            settleOrSelfCheck();
        }
        catch (err) {
            taskDone = true;
            clearWatchdogTimers();
            clearInterval(heartbeat);
            appendError(meta.taskKey, meta.agenticdocRoot, String(err));
            writeOutputGuarded({
                taskKey: meta.taskKey,
                agenticdocRoot: meta.agenticdocRoot,
                exitCode: 1,
                summary: "Task failed during output writing.",
                exitReason: String(err),
            });
            recordEnd(1);
            outputWritten = true;
            killTrackedDetachedChildren();
            process.exit(1);
        }
    });
}
/** Double-quote backslash handling for `tokenizeShellCommand` (P-1): POSIX says
 * a backslash inside double quotes escapes only `$`, a backtick, `"` and `\`;
 * every other backslash is a literal character. Folding all of them away erased
 * Windows path separators, so `& "C:\Program Files\Git\bin\bash.exe" -c "..."`
 * tokenized to a name no wrapper set could match. Appends the escaped/literal
 * character and returns the last consumed index (the caller advances one).
 * Declared after its call site on purpose: AC-011 pins the line numbers that
 * spec.md/design.md reference.
 *
 * T-18/A also folds a trailing `.exe` off the command basename at the two
 * command-position call sites (`skipWrapperPrefix`, `extractCommand`):
 * `bash.exe`/`cmd.exe`/`powershell.exe` are the same wrappers as their bare
 * names, and the unwrap sets are exact-name matches. */
function appendDoubleQuoteEscape(command, i, append) {
    const next = command[i + 1];
    if (next === "$" || next === "`" || next === '"' || next === "\\") {
        append(next, false);
        return i + 1;
    }
    append("\\", false);
    return i;
}
/** T-18/A + T-20/H-2: the command-position basename with a trailing Windows
 * `.exe` folded away. `bash.exe`/`cmd.exe`/`powershell.exe` are the same
 * wrappers as their bare names, and the unwrap sets are exact-name matches.
 * Splits on both separators itself instead of `path.basename`: the latter uses
 * the host's semantics, so `C:\...\bash.exe` did not fold on POSIX (Linux CI).
 * Declared after its call sites for the same AC-011 line-number reason. */
function commandBasename(text) {
    const base = (text
        .replace(/[\\/]+$/, "")
        .split(/[\\/]/)
        .pop() ?? "").toLowerCase();
    return base.replace(/\.exe$/, "");
}
/** T-20/H-4: the tokenizer emits `;` both for a literal `;` and for a physical
 * newline, but a heredoc body starts at the physical newline. Tag the newline
 * tokens so `dropHeredocBodies` can split on real line boundaries: with
 * `cat <<EOF; printf y > real.md` the `;` is not a body start, the following
 * `\n` is. The tag lives in a `WeakSet` so `ShellToken` itself is unchanged. */
const LINE_BREAK_TOKENS = new WeakSet();
function markLineBreak(token) {
    LINE_BREAK_TOKENS.add(token);
    return token;
}
/** T-19/C-17: a heredoc body is DATA, not shell source. `cat <<EOF > out.md`
 * writes only out.md, and a body line `x > y` writes nothing — judging its `>`
 * as a redirect was a false block. The tokenizer has no line state of its own
 * (a newline is just a `;` operator), so the body token ranges are identified
 * and removed here before the redirect scan. Handles `<<` / `<<-` (one operator
 * token) and quoted delimiters (the tokenizer already unquotes the word), skips
 * `<<` inside `(( ))` arithmetic (a shift, not a heredoc) and ignores `<<<`
 * here-strings (single-word, no body). Declared after its call site on purpose:
 * AC-011 pins the line numbers that spec.md/design.md reference. */
function dropHeredocBodies(tokens) {
    const lines = [[]];
    for (const token of tokens) {
        if (LINE_BREAK_TOKENS.has(token))
            lines.push([]);
        else
            lines[lines.length - 1].push(token);
    }
    const dropped = new Set();
    // T-20/H-3: on a CRLF-opened heredoc the tokenizer keeps a trailing `\r` in
    // the word, so a `<<EOF\r` opener and an `EOF` closer (mixed EOL) must compare
    // equal or the search runs to the end and swallows the real redirects.
    const trimDelimiter = (value) => value.replace(/\r+$/, "");
    for (let line = 0; line < lines.length; line++) {
        const delimiters = [];
        let depth = 0;
        for (let i = 0; i + 1 < lines[line].length; i++) {
            const token = lines[line][i];
            if (token.operator && token.text === "((")
                depth += 1;
            else if (token.operator && token.text === "))")
                depth = Math.max(0, depth - 1);
            else if (depth === 0 && token.operator && (token.text === "<<" || token.text === "<<-")) {
                if (!lines[line][i + 1].operator)
                    delimiters.push(trimDelimiter(lines[line][i + 1].text));
            }
        }
        if (delimiters.length === 0)
            continue;
        let cursor = line;
        for (const delimiter of delimiters) {
            let end = cursor + 1;
            while (end < lines.length && !(lines[end].length === 1 && trimDelimiter(lines[end][0].text) === delimiter))
                end++;
            for (let d = cursor + 1; d <= end && d < lines.length; d++)
                dropped.add(d);
            cursor = end;
        }
        line = cursor;
    }
    if (dropped.size === 0)
        return tokens;
    const kept = [];
    for (let line = 0; line < lines.length; line++) {
        if (line > 0)
            kept.push({ text: ";", operator: true, verbatim: true });
        if (!dropped.has(line))
            kept.push(...lines[line]);
    }
    return kept;
}
/** `PI_WORKER_TRIED_MODELS` csv -> ordered, deduped model labels
 * (`provider/model`). The launcher seeds it with the main model and every
 * fallback it moved through, so the list is the audit chain the Exit Reason
 * reports. */
export function parseTriedModels(env) {
    const out = [];
    const seen = new Set();
    for (const part of (env ?? "").split(",")) {
        const model = part.trim();
        if (model === "" || seen.has(model))
            continue;
        seen.add(model);
        out.push(model);
    }
    return out;
}
/** Model-error text budget (design §4): every error string on trace.log and in
 * `## Exit Reason` is collapsed to one line and capped at 200 chars, so a
 * multi-line provider dump can never break the line-parsable trace or the PM
 * readback. */
export const MODEL_ERR_TEXT_MAX = 200;
/** Collapse whitespace to one line and cap at {@link MODEL_ERR_TEXT_MAX}
 * (ellipsis included in the cap). */
export function truncateModelErrText(text) {
    const oneLine = text.replace(/\s+/g, " ").trim();
    return oneLine.length <= MODEL_ERR_TEXT_MAX ? oneLine : `${oneLine.slice(0, MODEL_ERR_TEXT_MAX - 1)}…`;
}
export function assistantBoundaryInfo(message) {
    if (typeof message !== "object" || message === null)
        return undefined;
    const record = message;
    if (record.role !== "assistant")
        return undefined;
    return {
        error: record.stopReason === "error",
        errorMessage: typeof record.errorMessage === "string" ? record.errorMessage : undefined,
    };
}
/** AC-004 exit reason: `model unavailable: tried=<m>(<n>),... last=<err>`. The
 * PM reads the tried chain and the final error text with zero text parsing. */
export function formatModelUnavailableReason(entries, lastError) {
    const tried = entries.length > 0 ? entries.map((entry) => `${entry.model}(${entry.runs})`).join(",") : "-";
    return `model unavailable: tried=${tried} last=${truncateModelErrText(lastError)}`;
}
// ── dp2 narrow steer consumption (mw-decision-substitution T-07b) ───────────
//
// `pm/pm-orchestrator.ts` replaces the divergence wake with a
// `<taskDir>/steer-dp2.md` request when dp2 answers `narrow`. This module is the
// ONLY reader of that file: an unconsumed request is the fail-open DS-4 forbids
// — the decision suppressed the PM wake (a displaySummary, no triggerTurn) and
// nothing reached the worker, so the task stalls and no human ever learns.
//
// Contract:
// - two consumption points: `before_agent_start` (the normal case) and the
//   settle path inside `finishSuccess` (a request that arrived mid-turn);
// - idempotency lives in the file itself: the injected steer is followed by a
//   `[dp2-consumed <runId> <ISO ts>]` line, so a restart re-reads the same file
//   and never replays it (the process-local flag only covers a failed mark);
// - injection is `pi.sendUserMessage(text, { deliverAs: "followUp" })` behind
//   the fixed `[mw dp2-narrow]` prefix (DS-7: machine-attributable);
// - every failure is a trace row (`[DECISION] dp2 consume-failed reason=…`),
//   never a throw — a broken steer must not change the terminal verdict.
/** Marker line written into `steer-dp2.md` after a delivered injection. */
export const DP2_CONSUMED_MARKER = "[dp2-consumed";
/** True when the request file already carries a consumption marker (any run). */
export function hasDp2ConsumedMarker(content) {
    return content.split(/\r?\n/).some((line) => line.trim().startsWith(DP2_CONSUMED_MARKER));
}
/** The injected text of one steer request: the machine request header is a
 * transport artifact, not a directive, so it is dropped; the directive keeps the
 * `[mw dp2-narrow]` attribution prefix (added only when it is not there yet).
 * `undefined` when nothing is left to inject (empty / header-only file) — an
 * empty steer is not a steer. */
export function formatDp2NarrowSteer(content) {
    const body = content
        .split(/\r?\n/)
        .filter((line) => line.trim() !== "" &&
        !line.trim().startsWith(DP2_CONSUMED_MARKER) &&
        !line.startsWith(DP2_STEER_REQUEST_HEADER))
        .join("\n")
        .trim();
    if (body === "")
        return undefined;
    return body.startsWith(DP2_NARROW_MARKER) ? body : `${DP2_NARROW_MARKER} ${body}`;
}
/** Atomically append the consumption marker to the request file. The file stays
 * the single source of truth for "this steer was already injected", so the
 * append is a tmp+rename replacement, never a partial write. */
export function appendDp2ConsumedMarker(steerPath, content, runId) {
    const marker = `${DP2_CONSUMED_MARKER} ${runId} ${new Date().toISOString()}]`;
    const separator = content === "" || content.endsWith("\n") ? "" : "\n";
    const tmp = `${steerPath}.consumed.tmp`;
    try {
        fs.writeFileSync(tmp, `${content}${separator}${marker}\n`, "utf8");
        fs.renameSync(tmp, steerPath);
        return true;
    }
    catch {
        try {
            fs.rmSync(tmp, { force: true });
        }
        catch {
            // Best-effort cleanup only — the false return already traces the failure.
        }
        return false;
    }
}
// ── dp3 clarification substitution (mw-decision-substitution T-06) ───────────
//
// Insertion point: `finishSuccess()` — after `exitCode` is computed and before
// `writeOutputGuarded`. Everything below is module-level and deliberately sits
// AFTER the anchor-pinned shell-lexer helpers (T-17/B-1 pins their absolute
// lines; new module code must never be inserted above them).
//
// Contract (design Q2/Q3/Q4):
// - triage: 3c local reuse (score >= 0.75 AND a shared exact referent) answers
//   from the quoted line with zero spawn; 3a fact lookup (no intent word + a
//   resolvable referent + locator shape) asks the decision service once, and
//   the answer must carry a `path:line` citation; everything else is 3b (the
//   default) and goes straight back to the human;
// - FIX-J: the 3a question set is Jev-native (choice + noul + a dynamic choice),
//   so the model neither writes prose nor a citation: `buildDp3Candidates`
//   derives the candidates locally (deterministic, no network), the model picks
//   one and reports `answerable`, and the injected answer is the local line plus
//   its local `<path>:<line>`;
// - fail-soft: every failure normalises to `unavailable` / `low-confidence` /
//   `input-incomplete` (plus the `input-oversize` refusal, D-028) with ZERO spawn
//   beyond the one attempt, and the caller falls through to the byte-identical NC
//   path;
// - disabled (`readDp3Policy().enabled === false`) is a complete bypass: zero
//   spawn AND zero write (D-007), so the closed state stays byte-identical;
// - injection: `pi.sendUserMessage(text, { deliverAs: "followUp" })` behind the
//   fixed `[mw dp3-answer]` prefix + decision_id (machine-attributable);
// - metrics: one {@link formatDp3TraceLine} row per clarification event, with
//   `nc_raw` (clarifications seen) and `nc_human` (those that reached a human).
//   Every row satisfies `nc_raw = nc_human + acted`.
/** Registry id of the worker-clarification decision point (`decision_points.py`
 * `DP_REGISTRY`; AC-011: the TS side only holds ids, never a second registry). */
export const DP3_ID = "dp3-worker-clarify";
/** `questions_version` of `DP3_ID` (`decision_points._questions_version`). */
export const DP3_QUESTIONS_VERSION = "q-fcbd3847";
/** Fixed attribution prefix of an injected dp3 answer (DS-7 guardrail). */
export const DP3_ANSWER_PREFIX = "[mw dp3-answer]";
/** Deterministic-reuse threshold of the local matcher (design Q2.2). Built-in
 * baseline only: the effective value is derived from the resolved
 * `min_confidence` by {@link dp3Thresholds} (0.75 = 0.7 + 0.05). */
export const DP3_MIN_MATCH_SCORE = 0.75;
/** Below this score a local match is not even a reuse candidate. */
export const DP3_BORDERLINE_MATCH_SCORE = 0.6;
/** Built-in baseline of the confidence gate (AC-016 layer 3). The effective
 * value is `resolveDecidePolicy(DP3_ID, projectDir).minConfidence`. */
export const DP3_MIN_CONFIDENCE = 0.7;
/** `answerable` (an `noul` probability) below this is a refusal, not an answer:
 * the model reports it cannot settle the question from the sent candidates.
 * Built-in baseline only; derived by {@link dp3Thresholds} (0.7 - 0.2 = 0.5). */
export const DP3_ANSWERABLE_MIN = 0.5;
/** The three dp3 thresholds as a function of the effective `min_confidence`.
 *
 * D-050: the decision STRUCTURE does not change — only the numbers are read
 * from policy instead of the hard-coded constants. The two satellite gates keep
 * their historic margin to the confidence gate, so the built-in layer (0.7)
 * reproduces the pre-AC-016 values exactly: 0.75 / 0.7 / 0.5. */
export function dp3Thresholds(minConfidence) {
    const clamp01 = (value) => Math.min(1, Math.max(0, value));
    // Round to 4 decimals: the margin arithmetic above is exact in decimal but
    // not in IEEE-754 (0.9 + 0.05 = 0.9500000000000001), and the value ends up in
    // a trace line that must stay readable.
    const round4 = (value) => Math.round(clamp01(value) * 1e4) / 1e4;
    return {
        minMatchScore: round4(minConfidence + (DP3_MIN_MATCH_SCORE - DP3_MIN_CONFIDENCE)),
        minConfidence,
        answerableMin: round4(minConfidence - (DP3_MIN_CONFIDENCE - DP3_ANSWERABLE_MIN)),
    };
}
/** Hard cap on the local candidate list (`local_candidates`, 1..5). */
export const DP3_CANDIDATE_LIMIT = 5;
/** Client-side canonical state budget (spec §5.4). */
export const DP3_MAX_STATE_BYTES = 2_000;
/** Question excerpt carried in the injected steer (L2 stays local). */
export const DP3_STEER_QUESTION_MAX = 300;
function asPlainRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value)
        ? value
        : undefined;
}
function readJsonRecord(file) {
    try {
        return asPlainRecord(JSON.parse(fs.readFileSync(file, "utf8")));
    }
    catch {
        return undefined;
    }
}
/** Mirror of the `force_off` half of `decision_points.py::_parse_row`
 * (decision_points.py:884-968): a non-object row (L2, handled by the caller) or
 * a row whose `mode`/`note`/`tier` is not a string of the accepted shape, or
 * whose `enabled` is not a boolean (L3/L5), is `enabled=false` for that dp only.
 * L4/L7 (tier VALUE outside P0|P1|P2, tier ≠ registry) are advisory and never
 * disable. Divergence is fixed HERE, in favour of Python `decide_for`. */
function dp3RowForceOff(row) {
    if ("mode" in row && row.mode !== "auto" && row.mode !== "suggest")
        return true;
    if ("note" in row && typeof row.note !== "string")
        return true;
    if ("tier" in row && typeof row.tier !== "string")
        return true;
    return "enabled" in row && typeof row.enabled !== "boolean";
}
/** Read the dp3 policy fail-soft (AC-001). The transport gate is authoritative:
 * without `.mw/decide.json` (`enabled === true`) dp3 does nothing at all, which
 * is what keeps the closed state byte-identical to the pre-dp3 worker.
 *
 * NON-AUTHORITATIVE (D-036): `enabled`/`note` pre-read from
 * `.mw/decide-points.json` exists ONLY to avoid paying for a `mw decide run`
 * child that Python would reject. The authorization verdict belongs to
 * `decision_points.decide_for`; if this mirror disagrees, PYTHON WINS. */
export function readDp3Policy(projectDir) {
    const transportEnabled = readDecidePolicy(projectDir).enabled;
    let enabled = true; // registry default for a P2 point
    let mode = "auto";
    const points = asPlainRecord(readJsonRecord(path.join(projectDir, ".mw", "decide-points.json"))?.points);
    // A present-but-non-object row (L2) is `enabled=false`; only a MISSING row
    // falls back to the registry default.
    const rawRow = points !== undefined && Object.hasOwn(points, DP3_ID) ? points[DP3_ID] : undefined;
    const row = asPlainRecord(rawRow);
    if (rawRow !== undefined && row === undefined)
        enabled = false;
    if (row !== undefined) {
        // AC-001: a bad row is `enabled=false` (never a crash, never a guess).
        if (row.enabled === false || dp3RowForceOff(row))
            enabled = false;
        if (row.mode === "suggest")
            mode = "suggest";
    }
    // AC-016: the three thresholds/limits come from one resolver, so the worker
    // mirror and Python agree on every layer (parity fixture in the tests).
    const resolved = resolveDecidePolicy(DP3_ID, projectDir);
    return {
        enabled: transportEnabled && enabled,
        mode,
        minConfidence: resolved.minConfidence,
        maxQuestions: resolved.maxQuestions,
        timeoutS: resolved.timeoutS,
    };
}
/** Byte-safe truncation (never splits a surrogate pair). */
function dp3TruncateUtf8(text, maxBytes) {
    if (Buffer.byteLength(text, "utf8") <= maxBytes)
        return text;
    let out = "";
    let used = 0;
    for (const char of text) {
        const size = Buffer.byteLength(char, "utf8");
        if (used + size > maxBytes)
            break;
        out += char;
        used += size;
    }
    return out;
}
function dp3RelPath(projectDir, target) {
    const rel = path.relative(projectDir, target);
    return rel !== "" && !rel.startsWith("..") ? rel.replace(/\\/g, "/") : target.replace(/\\/g, "/");
}
function dp3ReadBounded(file, maxBytes) {
    try {
        const text = fs.readFileSync(file, "utf8");
        return dp3TruncateUtf8(text, maxBytes);
    }
    catch {
        return undefined;
    }
}
/** `## [N.] Decisions` section of pm-state.md (the key's settled rulings). */
function dp3DecisionsSection(text) {
    const lines = text.split(/\r?\n/);
    let start = -1;
    for (let i = 0; i < lines.length; i++) {
        if (/^##\s+(?:\d+\.\s*)?Decisions\b/.test(lines[i])) {
            start = i;
            break;
        }
    }
    if (start < 0)
        return undefined;
    let end = lines.length;
    for (let i = start + 1; i < lines.length; i++) {
        if (/^##\s+/.test(lines[i])) {
            end = i;
            break;
        }
    }
    return lines.slice(start, end).join("\n");
}
/** Bounded local reuse corpus, in priority order (design Q2.2): own dispatch
 * card → sibling cards → goal.md → pm-state `## Decisions`. The session-history
 * level is deliberately absent (L2: user quotes never leave the machine, and
 * this card has no session reader). */
export function readDp3ReuseSources(input) {
    const maxBytes = input.maxBytes ?? 8_192;
    const sources = [
        { label: dp3RelPath(input.projectDir, input.taskPath), text: dp3TruncateUtf8(input.taskContent, maxBytes) },
    ];
    const workersDir = path.dirname(input.taskDir);
    const ownName = path.basename(input.taskDir);
    const limit = input.siblingLimit ?? 5;
    try {
        const siblings = fs
            .readdirSync(workersDir, { withFileTypes: true })
            .filter((entry) => entry.isDirectory() && entry.name !== ownName)
            .map((entry) => entry.name)
            .sort()
            .slice(0, limit);
        for (const name of siblings) {
            const file = path.join(workersDir, name, "task.md");
            const text = dp3ReadBounded(file, maxBytes);
            if (text !== undefined)
                sources.push({ label: dp3RelPath(input.projectDir, file), text });
        }
    }
    catch {
        // A missing/unreadable workers dir simply yields no sibling source.
    }
    const goal = dp3ReadBounded(path.join(input.trueRoot, "goal.md"), maxBytes);
    if (goal !== undefined)
        sources.push({ label: dp3RelPath(input.projectDir, path.join(input.trueRoot, "goal.md")), text: goal });
    const pmStateFile = path.join(input.keyDir, "pm-state.md");
    const pmState = dp3ReadBounded(pmStateFile, maxBytes);
    if (pmState !== undefined) {
        const decisions = dp3DecisionsSection(pmState);
        if (decisions !== undefined) {
            sources.push({ label: `${dp3RelPath(input.projectDir, pmStateFile)}:decisions`, text: decisions });
        }
    }
    return sources;
}
/** Content tokens for the Jaccard score: latin words verbatim + CJK bigrams
 * (a whitespace split cannot tokenise Chinese prose). */
export function dp3ContentTokens(text) {
    const tokens = new Set();
    for (const word of text.toLowerCase().match(/[a-z0-9_][a-z0-9_.\-/]*/g) ?? [])
        tokens.add(word);
    for (const run of text.match(/[\u4e00-\u9fff]+/g) ?? []) {
        for (let i = 0; i + 1 < run.length; i++)
            tokens.add(run.slice(i, i + 2));
    }
    return tokens;
}
/** Exact referents (paths / identifiers / commands / quoted errors) from a
 * question — the second 3c condition besides the Jaccard score. */
export function dp3QuestionReferents(text) {
    const out = new Set();
    for (const match of text.matchAll(/`([^`\n]{2,80})`/g)) {
        const value = match[1].trim();
        if (value !== "")
            out.add(value);
    }
    for (const match of text.matchAll(/(?:^|[\s("'`])((?:[\w.@-]+[\\/]){1,}[\w.@-]+)/g))
        out.add(match[1]);
    for (const match of text.matchAll(/"([^"\n]{3,60})"|\u201c([^\n\u201d]{3,60})\u201d/g)) {
        const value = (match[1] ?? match[2] ?? "").trim();
        if (value !== "")
            out.add(value);
    }
    for (const match of text.matchAll(/\b(?:npm|npx|node|python3?|pytest|vitest|git|make)\s+[\w:./-]+/g))
        out.add(match[0]);
    return [...out].slice(0, 8);
}
function dp3Jaccard(a, b) {
    if (a.size === 0 || b.size === 0)
        return 0;
    let shared = 0;
    for (const token of a)
        if (b.has(token))
            shared += 1;
    return shared / (a.size + b.size - shared);
}
/** Deterministic 3c matcher: the best line of each source in priority order,
 * requiring a shared exact referent AND a content-word Jaccard >= 0.6. The
 * first source that clears the effective match threshold (default
 * {@link DP3_MIN_MATCH_SCORE}, derived from `min_confidence` by
 * {@link dp3Thresholds}) wins (priority order); otherwise the best borderline
 * hit is returned for the caller to escalate. */
export function matchDp3Reuse(question, sources, minMatchScore = DP3_MIN_MATCH_SCORE) {
    const referents = dp3QuestionReferents(question);
    if (referents.length === 0)
        return undefined;
    const qTokens = dp3ContentTokens(dp3TruncateUtf8(question, 2_000));
    let best;
    for (const source of sources) {
        const lines = source.text.split(/\r?\n/);
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (line.length < 4)
                continue;
            const sharedReferent = referents.find((ref) => line.includes(ref));
            if (sharedReferent === undefined)
                continue;
            const score = dp3Jaccard(qTokens, dp3ContentTokens(dp3TruncateUtf8(line, 2_000)));
            if (score < DP3_BORDERLINE_MATCH_SCORE)
                continue;
            if (best === undefined || score > best.score) {
                best = { source: `${source.label}:${i + 1}`, quote: dp3TruncateUtf8(line, 300), score };
            }
            if (score >= minMatchScore)
                return best;
        }
    }
    return best;
}
/** Intent / preference / approval wording — the hard 3b signal (design Q2.1). */
const DP3_INTENT_RE = /应该|建议|更好|倾向于|偏好|优先|取舍|是否可以|要不要|请确认|需要你|由你|你决定|approve|prefer|should\b|trade-?off/i;
/** Locator / definition / error-shape questions that a fact answer can settle. */
const DP3_LOCATOR_RE = /在哪|哪里|哪个文件|什么文件|什么命令|怎么(?:运行|跑|执行|用|做)|如何(?:运行|跑|执行)|字段名|签名|定义|位置|报错|为什么|为何|where\b|which file|what file|how (?:do|to|can) i (?:run|use)|field name|signature|defined/i;
/** A fact answer must cite `path:line` (design Q2.2 3a). */
export const DP3_CITATION_RE = /[\w./-]+\.(?:ts|tsx|js|mjs|cjs|py|json|md|yml|yaml|toml|sh)\s*:\d+/i;
function normalizeDp3Question(text) {
    return text.replace(/\s+/g, " ").trim();
}
/** Map an arbitrary worker role onto the dp3 `task_type` enum. A role outside
 * the enum keeps its nature (write tools → coding, else research) instead of
 * refusing the decision outright. */
export function dp3TaskType(type) {
    if (type === "coding" || type === "research" || type === "review")
        return type;
    return hasWriteTools(type) ? "coding" : "research";
}
/** Stopwords of the candidate tokenizer (frozen by FIX-J §2). */
const DP3_CANDIDATE_STOPWORDS = new Set([
    "the",
    "and",
    "for",
    "which",
    "where",
    "should",
    "what",
    "how",
    "this",
    "that",
    "file",
    "write",
    "please",
]);
/** Repo-relative roots searched for candidate files (FIX-J §2). */
const DP3_CANDIDATE_ROOTS = ["evidence", "docs", "tasks"];
/** Per-root walk budget: at most this many files are listed (names only). */
const DP3_CANDIDATE_FILES_PER_ROOT = 300;
/** Per-root walk budget: at most this directory depth is descended into. */
const DP3_CANDIDATE_MAX_DEPTH = 3;
/** `label` budget of a single candidate (FIX-J §2). */
const DP3_CANDIDATE_LABEL_MAX = 80;
/** Question tokens of the candidate matcher (FIX-J §2): ASCII words of >= 3
 * chars and CJK runs of >= 2 chars, lowercased, stopwords dropped, first-seen
 * order (so the line scan below is deterministic). */
export function dp3CandidateTokens(question) {
    const tokens = [];
    const seen = new Set();
    const push = (raw) => {
        const token = raw.toLowerCase();
        if (token === "" || DP3_CANDIDATE_STOPWORDS.has(token) || seen.has(token))
            return;
        seen.add(token);
        tokens.push(token);
    };
    for (const word of question.match(/[A-Za-z0-9]{3,}/g) ?? [])
        push(word);
    for (const run of question.match(/[\u4e00-\u9fff]{2,}/g) ?? [])
        push(run);
    return tokens;
}
/** Middle truncation so a label never exceeds {@link DP3_CANDIDATE_LABEL_MAX}. */
function dp3CandidateLabel(rel) {
    if (rel.length <= DP3_CANDIDATE_LABEL_MAX)
        return rel;
    const keep = DP3_CANDIDATE_LABEL_MAX - 3;
    const head = Math.ceil(keep / 2);
    return `${rel.slice(0, head)}...${rel.slice(rel.length - (keep - head))}`;
}
/** `YYYYMMDD` of the LOCAL day (the convention candidate's stamp). */
function dp3LocalDateStamp(now = new Date()) {
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${now.getFullYear()}${month}${day}`;
}
/** Bounded, name-only walk: depth <= 3, <= 300 files per root, deterministic
 * (sorted) order. The candidate search never reads file CONTENT. */
function dp3CollectCandidateFiles(projectDir, rootRel, out) {
    const walk = (dirRel, depth) => {
        if (out.length >= DP3_CANDIDATE_FILES_PER_ROOT)
            return;
        let entries;
        try {
            entries = fs.readdirSync(path.join(projectDir, dirRel), { withFileTypes: true });
        }
        catch {
            return; // a missing/unreadable root contributes nothing (fail-soft)
        }
        entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
        for (const entry of entries) {
            if (out.length >= DP3_CANDIDATE_FILES_PER_ROOT)
                return;
            const rel = `${dirRel}/${entry.name}`;
            if (entry.isDirectory()) {
                if (depth < DP3_CANDIDATE_MAX_DEPTH)
                    walk(rel, depth + 1);
            }
            else if (entry.isFile()) {
                out.push(rel);
            }
        }
    };
    walk(rootRel, 1);
}
/** Deterministic local candidate list for one dp3 question (FIX-J §2): `c1` is
 * always the convention evidence file of the task type, `c2..c5` are the best
 * name matches under the four roots, ordered by (hit count desc, path asc). */
export function buildDp3Candidates(input, question) {
    const folder = input.taskType === "research" ? "evidence/research" : "evidence/runs";
    const fixedRel = `${folder}/${input.taskKey}-${dp3LocalDateStamp()}.md`;
    const candidates = [
        { id: "c1", label: dp3CandidateLabel(fixedRel), path: path.join(input.projectDir, fixedRel) },
    ];
    const tokens = dp3CandidateTokens(question);
    if (tokens.length === 0)
        return candidates;
    const seen = new Set([fixedRel.toLowerCase()]);
    const files = [];
    for (const root of [...DP3_CANDIDATE_ROOTS, `.agenticdoc/${input.key}`]) {
        const rootFiles = [];
        dp3CollectCandidateFiles(input.projectDir, root, rootFiles);
        files.push(...rootFiles);
    }
    const scored = files
        .filter((rel) => !seen.has(rel.toLowerCase()))
        .map((rel) => {
        const lower = rel.toLowerCase();
        let hits = 0;
        for (const token of tokens)
            if (lower.includes(token))
                hits += 1;
        return { rel, hits };
    })
        .filter((entry) => entry.hits > 0)
        .sort((a, b) => b.hits - a.hits || (a.rel < b.rel ? -1 : a.rel > b.rel ? 1 : 0));
    for (const entry of scored) {
        if (candidates.length >= DP3_CANDIDATE_LIMIT)
            break;
        if (seen.has(entry.rel.toLowerCase()))
            continue;
        seen.add(entry.rel.toLowerCase());
        candidates.push({
            id: `c${candidates.length + 1}`,
            label: dp3CandidateLabel(entry.rel),
            path: path.join(input.projectDir, entry.rel),
        });
    }
    return candidates;
}
/** The locally quoted line of a chosen candidate (FIX-J §4): the first line
 * that hits any question token (case-insensitive), else the first non-empty
 * line. `undefined` when the file is unreadable or carries no non-empty line. */
function dp3CandidateLine(file, tokens) {
    let content;
    try {
        content = fs.readFileSync(file, "utf8");
    }
    catch {
        return undefined;
    }
    const lines = content.split(/\r?\n/);
    let first;
    for (let i = 0; i < lines.length; i++) {
        const text = lines[i].trim();
        if (text === "")
            continue;
        if (first === undefined)
            first = { text, line: i + 1 };
        const lower = text.toLowerCase();
        if (tokens.some((token) => lower.includes(token)))
            return { text, line: i + 1 };
    }
    return first;
}
/** Resolve the model's `candidate` choice into a LOCALLY quoted answer (FIX-J
 * §4). Nothing the child wrote in free text reaches `answer`: the text is the
 * local line, the citation is the local `<path>:<line>`. */
function resolveDp3CandidateAnswer(input, question, candidates, rawCandidate) {
    const chosenId = parseAnswerEntry(rawCandidate)?.value;
    const chosen = chosenId === undefined ? undefined : candidates.find((entry) => entry.id === chosenId);
    if (chosen === undefined)
        return { ok: false, detail: `unknown candidate id ${chosenId ?? "-"}` };
    const rel = dp3RelPath(input.projectDir, chosen.path);
    const hit = dp3CandidateLine(chosen.path, dp3CandidateTokens(question));
    if (hit === undefined)
        return { ok: false, detail: `candidate file unreadable ${rel}` };
    const answer = `${hit.text.slice(0, 200)} (${rel}:${hit.line})`;
    return {
        ok: true,
        answer,
        source: DP3_CITATION_RE.exec(answer)?.[0],
        detail: `candidate=${chosen.id} path=${rel} line=${hit.line} sent=${candidates.map((entry) => entry.id).join(",")}`,
    };
}
/** `answerable` is an `noul` probability (0..1) carried as a NUMBER in
 * `value`, unlike the string-valued entries {@link parseAnswerEntry} handles. */
function parseDp3Probability(value) {
    const entry = asPlainRecord(value);
    if (!entry)
        return undefined;
    const raw = entry.value;
    const numeric = typeof raw === "number" ? raw : typeof raw === "string" && raw.trim() !== "" ? Number(raw) : NaN;
    return Number.isFinite(numeric) ? Math.min(1, Math.max(0, numeric)) : undefined;
}
function buildDp3State(input, question, candidates = buildDp3Candidates(input, question)) {
    const excerpt = dp3TruncateUtf8(question, 600);
    // FIX-J: the candidate list IS input data, not part of the question set —
    // `questions_version` deliberately does not track it (FIX-I frozen contract).
    const state = {
        schema_version: 2,
        decision_point: DP3_ID,
        key: input.key,
        phase: input.phase,
        task_type: input.taskType,
        risk: input.risk,
        risk_source: input.riskSource,
        authority_tier: "P2",
        questions_version: DECIDE_REGISTRY[DP3_ID]?.questionsVersion ?? DP3_QUESTIONS_VERSION,
        task_summary: excerpt,
        // The ambiguity.kind enum is scope|missing-dep|rule-conflict (the contract
        // has no `fact` member, so dp3a rides `scope`; the registry question
        // `answer_kind` carries the real three-way verdict).
        ambiguity: { kind: "scope", question: dp3TruncateUtf8(question, 300) },
        local_candidates: candidates.map(({ id, label }) => ({ id, label })),
    };
    // W6 (D-052..D-054): the engineered context the model needs to answer without
    // guessing — a one-line change summary plus the verbatim hit line of every
    // candidate (first 200 chars + `<path>:<line>`, so a citation is checkable).
    const contextSlots = DECIDE_REGISTRY[DP3_ID]?.contextSlots ?? [];
    const context = {};
    if (contextSlots.includes("change_summary")) {
        context.change_summary = dp3TruncateUtf8(`clarification (scope): ${question}`, 600);
    }
    if (contextSlots.includes("candidate_snippets")) {
        const tokens = dp3CandidateTokens(question);
        const snippets = [];
        for (const candidate of candidates) {
            const hit = dp3CandidateLine(candidate.path, tokens);
            if (hit === undefined)
                continue;
            const rel = dp3RelPath(input.projectDir, candidate.path);
            snippets.push({ text: Array.from(hit.text).slice(0, 200).join(""), source: `${rel}:${hit.line}` });
        }
        if (snippets.length > 0)
            context.candidate_snippets = snippets;
    }
    if (Object.keys(context).length > 0)
        state.context = context;
    // W6: the registry, not this builder, owns the field list; drift fails loud.
    assertStateMatchesRegistry(DP3_ID, state);
    return state;
}
function parseDecideStdout(stdout) {
    const trimmed = stdout.trim();
    if (trimmed === "")
        return undefined;
    const candidates = [trimmed, trimmed.split("\n").at(-1) ?? ""];
    for (const candidate of candidates) {
        if (candidate === "")
            continue;
        try {
            const parsed = asPlainRecord(JSON.parse(candidate));
            if (parsed)
                return parsed;
        }
        catch {
            // try the next candidate
        }
    }
    return undefined;
}
function parseAnswerEntry(value) {
    const entry = asPlainRecord(value);
    if (!entry)
        return undefined;
    const rawValue = entry.value;
    const text = typeof rawValue === "string" && rawValue.trim() !== "" ? rawValue.trim() : undefined;
    const rawConfidence = entry.confidence;
    const confidence = typeof rawConfidence === "number" && Number.isFinite(rawConfidence)
        ? Math.min(1, Math.max(0, rawConfidence))
        : null;
    if (text === undefined && confidence === null)
        return undefined;
    return { value: text, confidence };
}
/** Decide one clarification (never throws; the caller owns the trace + steer). */
export function decideDp3WorkerClarify(input) {
    const localDecisionId = `${DP3_ID}:${input.taskKey}#nc${input.ncIndex}`;
    // The id every escalation reports: the locally derived one until the child
    // answers, then the child's own `decision_id` (D-041: verbatim passthrough).
    let decisionId = localDecisionId;
    const escalate = (reason, sub, detail) => ({
        kind: "escalate",
        sub,
        reason,
        detail,
        decisionId,
    });
    try {
        const question = normalizeDp3Question(dp3TruncateUtf8(input.question, 2_000));
        if (question === "")
            return escalate("input-incomplete", undefined, "lastAssistantText is empty");
        if (input.taskKey === "" || input.key === "" || input.phase === "") {
            return escalate("input-incomplete", undefined, "task context unavailable");
        }
        const sources = readDp3ReuseSources({
            projectDir: input.projectDir,
            taskDir: input.taskDir,
            taskPath: input.taskPath,
            taskContent: input.taskContent,
            trueRoot: input.trueRoot,
            keyDir: input.keyDir,
        });
        // 3c first: the cheapest, most deterministic path (zero spawn).
        // AC-016: the three dp3 thresholds follow the effective `min_confidence`
        // (built-in 0.7 reproduces 0.75 / 0.7 / 0.5 exactly).
        const thresholds = dp3Thresholds(input.policy.minConfidence);
        const match = matchDp3Reuse(question, sources, thresholds.minMatchScore);
        if (match !== undefined) {
            if (match.score < thresholds.minMatchScore) {
                return escalate("low-confidence", "3c", `reuse score ${match.score.toFixed(2)} < ${thresholds.minMatchScore}`);
            }
            return {
                kind: "answer",
                sub: "3c",
                answer: match.quote,
                source: match.source,
                decisionId,
                confidence: match.score,
                confidenceSource: "local-match",
                mode: input.policy.mode,
            };
        }
        // 3a gate: no intent wording, a resolvable in-repo referent and a locator
        // question. Anything else is 3b (the default) and goes back to the human.
        const intent = DP3_INTENT_RE.test(question);
        const referents = dp3QuestionReferents(question);
        const corpus = sources.map((source) => source.text).join("\n");
        const resolvable = referents.filter((ref) => {
            if (ref.includes("/") || ref.includes("\\")) {
                return (fs.existsSync(path.join(input.projectDir, ref)) || fs.existsSync(path.resolve(input.projectDir, ref)));
            }
            return corpus.includes(ref);
        });
        if (intent || resolvable.length === 0 || !DP3_LOCATOR_RE.test(question)) {
            const why = intent
                ? "intent wording"
                : resolvable.length === 0
                    ? "no resolvable referent"
                    : "not a locator question";
            return escalate("intent", "3b", why);
        }
        // One decision-service call (stdin JSON only; <=2000B canonical state).
        // The candidate list is built ONCE: the ids sent in `local_candidates` are
        // exactly the ids the answer is validated against below.
        const candidates = buildDp3Candidates(input, question);
        const state = buildDp3State(input, question, candidates);
        if (canonicalStateBytes(state) > DP3_MAX_STATE_BYTES) {
            // D-028: an over-budget state is refused, never sent; the reason is the
            // distinct `input-oversize` so it cannot be mistaken for a missing field.
            return escalate("input-oversize", "3a", `canonical state > ${DP3_MAX_STATE_BYTES}B`);
        }
        let raw;
        try {
            raw = (input.runner ?? runDecideMw)({
                projectDir: input.projectDir,
                dp: DP3_ID,
                timeoutMs: input.timeoutMs ?? Math.round(input.policy.timeoutS * 1000),
                input: JSON.stringify({ state }),
            });
        }
        catch {
            return escalate("unavailable", "3a", "decision runner threw");
        }
        if (raw.timedOut)
            return escalate("unavailable", "3a", "decision call timed out");
        if (raw.error !== undefined)
            return escalate("unavailable", "3a", raw.error);
        if (raw.status !== 0)
            return escalate("unavailable", "3a", `decision exit ${raw.status ?? "null"}`);
        const payload = parseDecideStdout(raw.stdout);
        if (payload === undefined)
            return escalate("unavailable", "3a", "non-JSON decision stdout");
        if (payload.available !== true) {
            const reason = typeof payload.reason === "string" && payload.reason !== "" ? payload.reason : "upstream-error";
            return escalate("unavailable", "3a", reason);
        }
        // The child is the authority for the id (D-036/D-041): adopt its
        // `decision_id` when it reported one, else keep the locally derived id.
        const carriedDecisionId = payload.decision_id;
        if (typeof carriedDecisionId === "string" && carriedDecisionId.trim() !== "") {
            decisionId = carriedDecisionId.trim();
        }
        const answers = asPlainRecord(payload.answers);
        const kind = parseAnswerEntry(answers?.answer_kind);
        // FIX-I removed `clarifying_answer` from the dp3 question set (the model may
        // not write prose). It is only honoured on the legacy 3c `reuse` path, where
        // the old behaviour is kept byte-identical for an old-shaped payload.
        const legacyAnswer = parseAnswerEntry(answers?.clarifying_answer);
        if (kind?.value === undefined) {
            return escalate("unavailable", "3a", "decision answer shape is unusable");
        }
        const confidenceSource = typeof payload.confidence_source === "string" && payload.confidence_source !== ""
            ? payload.confidence_source
            : "unknown";
        // FIX-J: `answerable` carries the noul probability; its `confidence` is the
        // second choice of the confidence chain (the kind verdict is the first).
        const answerableEntry = parseAnswerEntry(answers?.answerable);
        const confidence = kind.confidence ?? answerableEntry?.confidence ?? null;
        // D-036/D-041: on the spawned path the child's own `mode` is the ONLY
        // authority on whether the service considers the decision settled. A child
        // that reports none (or an unknown value) has not said it answered, so the
        // consumer must not invent `auto` from the local mirror and inject a steer;
        // it escalates instead. The zero-spawn 3c path above is the only place the
        // local `policy.mode` is authoritative (there is no child to ask).
        const childMode = payload.mode;
        if (childMode !== "auto" && childMode !== "suggest") {
            return escalate("unavailable", "3a", "decision mode missing");
        }
        // Spec §7.2: confidence only gates when the source is `api`.
        if (confidenceSource === "api" && confidence !== null && confidence < input.policy.minConfidence) {
            return escalate("low-confidence", "3a", `confidence ${confidence.toFixed(2)} < ${input.policy.minConfidence}`);
        }
        if (kind.value === "intent")
            return escalate("intent", "3b", "model classified the question as intent");
        if (kind.value === "reuse" && legacyAnswer?.value !== undefined) {
            // Legacy 3c payloads keep the old behaviour verbatim: the quoted text is
            // whatever the answer carried, the citation is its `path:line`.
            return {
                kind: "answer",
                sub: "3c",
                answer: legacyAnswer.value,
                source: DP3_CITATION_RE.exec(legacyAnswer.value)?.[0],
                decisionId,
                confidence,
                confidenceSource,
                mode: childMode,
            };
        }
        if (kind.value !== "fact" && kind.value !== "reuse") {
            return escalate("unavailable", "3a", `unknown answer_kind ${kind.value}`);
        }
        // FIX-J: the model neither writes the answer nor its citation. It reports
        // how answerable the question is and picks one of the candidates it was
        // sent; the text and the `path:line` come from that LOCAL file.
        const answerable = parseDp3Probability(answers?.answerable);
        if (answerable === undefined) {
            return escalate("unavailable", "3a", "decision answer shape is unusable");
        }
        if (answerable < thresholds.answerableMin) {
            return escalate("unavailable", "3a", `model reports unanswerable (${answerable})`);
        }
        const picked = resolveDp3CandidateAnswer(input, question, candidates, answers?.candidate);
        if (!picked.ok) {
            // `reuse` still classifies as 3c; everything else is the 3a refusal.
            return escalate("unavailable", kind.value === "reuse" ? "3c" : "3a", picked.detail);
        }
        return {
            kind: "answer",
            sub: kind.value === "reuse" ? "3c" : "3a",
            answer: picked.answer,
            source: picked.source,
            decisionId,
            confidence,
            confidenceSource,
            mode: childMode,
            detail: picked.detail,
        };
    }
    catch {
        // Structural fail-soft: a bug here must never break a terminal verdict.
        return { kind: "escalate", reason: "unavailable", detail: "dp3 internal error", decisionId };
    }
}
/** The injected steer (DS-7: machine-attributable, never impersonates a human).
 * The original question is quoted, never rewritten. */
export function formatDp3AnswerSteer(decision, question) {
    const excerpt = dp3TruncateUtf8(normalizeDp3Question(question), DP3_STEER_QUESTION_MAX);
    const kind = decision.sub === "3a" ? "3a 事实检索" : "3c 已表态引用";
    const source = decision.source === undefined || decision.source === "" ? "-" : decision.source;
    return [
        `${DP3_ANSWER_PREFIX} 你的澄清问题已由自动决策解答（decision_id=${decision.decisionId}，${kind}，非人工输入）。`,
        `问题：${excerpt}`,
        `答案：${decision.answer}`,
        `出处：${source}`,
        "请基于该答案继续完成任务并正常收尾；若与该出处冲突，以出处内容为准。",
    ].join("\n");
}
/** One unified dp3 metric row. Key order is FROZEN — the offline statistics
 * parse `sub`/`acted`/`escalated_reason` and reconcile `nc_raw` against
 * `nc_human + acted` (Q3.3). `sub=-` means no classifier ran (budget spent). */
export function formatDp3TraceLine(input) {
    const iso = (input.now ?? new Date()).toISOString();
    const reason = input.escalatedReason === "intent" ? "-" : input.escalatedReason;
    return (`[DECIDE] ${iso} dp=${DP3_ID} trigger=${input.triggerId} sub=${input.sub ?? "-"} acted=${input.acted}` +
        ` mode=${input.mode} escalated_reason=${reason} decision_id=${input.decisionId}` +
        ` nc_raw=${input.ncRaw} nc_human=${input.ncHuman}`);
}
//# sourceMappingURL=worker-mode.js.map