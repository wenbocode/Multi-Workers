import * as fs from "node:fs";
import * as path from "node:path";
import { autoStartMonitor, registerAutopilotCommands } from "../autopilot/console.js";
import { registerRagTools } from "../rag/tools.js";
import { AckStore } from "../shared/ack-store.js";
import { registerMainWindowModel } from "../shared/dispatch-models.js";
import { formatHeartbeatAge, readTaskProgress } from "../shared/heartbeat.js";
import { IndexStore } from "../shared/index-store.js";
import { getMwStatus, initMw, serveStaleness, startMw, waitForMwStart } from "../shared/mw-runner.js";
import { agenticdocRoot as resolveAgenticdocRoot, SCRATCH_WORKERS_KEY } from "../shared/paths.js";
import { dispatchDocGaps, readPhaseDocs } from "../shared/phase-docs.js";
import { registerPmStateGuard } from "../shared/pm-state-guard.js";
import { WorkerStore } from "../shared/worker-store.js";
import { isGoalEstablished, readGoal } from "./goal-reader.js";
import { dispatchTask } from "./task-dispatcher.js";
import { applyWatchWidget, claimState, deliverPmAlert, deliverWorkerResult, displaySummary, makeScopedDocGateNotifier, ownerKeyOf, readOutputBody, readSpawnFailure, registerAdvancePhaseTool, registerMwCommands, registerMwTools, registerPmKeyCommands, registerPmSaveCommand, registerSwitchKeyTool, registerWatchCommand, registerWorkerCommands, registerWorkerTools, renderWatchLines, setWatchWidget, takeOverKey, WATCH_ENTRY_TYPE, windowClaimId, } from "./ui-bridge.js";
const POLL_INTERVAL_MS = 4000; // < 5s per AC-001
function isTerminal(status) {
    return status === "done" || status === "failed" || status === "needs-clarification";
}
/** The phase-doc write/edit target, when the tool path resolves to
 * {agenticdocRoot}/{key}/spec.md | design.md | plan.md — the PM phase docs that
 * mean "this window is now executing this key". Any other path (or file) is
 * not a claim signal. */
function docWriteTarget(toolName, args, projectDir, agenticdocRoot) {
    if (toolName !== "write" && toolName !== "edit")
        return undefined;
    const filePath = args?.path;
    if (typeof filePath !== "string" || filePath === "")
        return undefined;
    const rel = path.relative(path.resolve(agenticdocRoot), path.resolve(projectDir, filePath));
    if (rel.startsWith("..") || path.isAbsolute(rel))
        return undefined; // outside .agenticdoc
    const parts = rel.split(path.sep);
    const doc = parts.length === 2 ? parts[1] : undefined;
    if (doc !== "spec.md" && doc !== "design.md" && doc !== "plan.md")
        return undefined;
    const key = parts[0] ?? "";
    if (!key || key.startsWith("_") || key.startsWith("."))
        return undefined;
    return { key, doc };
}
/** The key a phase-doc write/edit belongs to (see docWriteTarget). */
export function keyFromDocWrite(toolName, args, projectDir, agenticdocRoot) {
    return docWriteTarget(toolName, args, projectDir, agenticdocRoot)?.key;
}
/** Which phase doc was written/edited (see docWriteTarget). */
export function docFromWrite(toolName, args, projectDir, agenticdocRoot) {
    return docWriteTarget(toolName, args, projectDir, agenticdocRoot)?.doc;
}
/** The evidence-note write target, when the tool path resolves to
 * {agenticdocRoot}/{key}/evidence/research/spec-*.md | design-*.md. Not a
 * claim signal (only phase docs are) — but the moment evidence lands is the
 * moment an already-written phase doc's claims can be re-reviewed against
 * it. */
export function evidencePhaseFromWrite(toolName, args, projectDir, agenticdocRoot) {
    if (toolName !== "write" && toolName !== "edit")
        return undefined;
    const filePath = args?.path;
    if (typeof filePath !== "string" || filePath === "")
        return undefined;
    const rel = path.relative(path.resolve(agenticdocRoot), path.resolve(projectDir, filePath));
    if (rel.startsWith("..") || path.isAbsolute(rel))
        return undefined; // outside .agenticdoc
    const parts = rel.split(path.sep);
    if (parts.length !== 4 || parts[1] !== "evidence" || parts[2] !== "research")
        return undefined;
    const note = parts[3] ?? "";
    if (!note.endsWith(".md"))
        return undefined;
    const phase = note.startsWith("spec-")
        ? "spec"
        : note.startsWith("design-")
            ? "design"
            : undefined;
    if (!phase)
        return undefined;
    const key = parts[0] ?? "";
    if (!key || key.startsWith("_") || key.startsWith("."))
        return undefined;
    return { key, phase };
}
/** UI notice when a phase doc and its research evidence coexist — the
 * "re-review when evidence is generated" protocol, as a *notice*, not an
 * injected instruction (mw-evidence-nudge-notify): the old sendUserMessage
 * form made the model treat the automatic nudge as the user ordering an
 * immediate review pass, so the window agent started rewriting the doc with
 * no consent and no chance to veto, hijacking the turn. The framework's role
 * is to flag the moment; the user decides when (and whether) to run the
 * review. Fires once per (key, phase) per session, only when both the phase
 * doc (>= 500 bytes) and >= 1 evidence note exist: the review needs both
 * sides of the comparison. */
export function evidenceReviewNotice(ctx, key, phase, agenticdocRoot, notified) {
    const dedup = `${key}:${phase}`;
    if (notified.has(dedup))
        return;
    const docs = readPhaseDocs(agenticdocRoot, key);
    const docOk = phase === "spec" ? docs.spec : docs.design;
    const evidence = phase === "spec" ? docs.specEvidence : docs.designEvidence;
    if (!docOk || evidence < 1)
        return;
    notified.add(dedup);
    const doc = phase === "spec" ? "spec.md" : "design.md";
    ctx.ui.notify(`[mw] ${key}: ${phase} 阶段证据已就位（${evidence} 份 research note）——建议对照 evidence/research/ 复查 ${doc}（断言-证据对照 / 数字口径 / 内部一致性 / 可证伪性）。何时执行复查由你决定。`, "info");
}
/** Nudge the user toward the /goal brainstorm when the project goal is not
 * yet established. Headless sessions (print/-p) skip the nudge entirely:
 * sendUserMessage starts a generation immediately, and the queued -p prompt
 * would collide with it ("Agent is already processing") before ever reaching
 * the model — `pi -p` in any project without an established goal.md would
 * hard-fail at startup. */
export function nudgeGoalUnestablished(pi, agenticdocRoot, hasUI) {
    const goal = readGoal(agenticdocRoot);
    if (hasUI && !isGoalEstablished(goal)) {
        pi.sendUserMessage("[agent-team-loop] 项目总目标（.agenticdoc/goal.md）尚未确立。\n" +
            "建议先运行 /goal，与我对话共创项目总目标——它是后续每个 spec 对齐的锚点。\n" +
            "（也可直接编辑 .agenticdoc/goal.md 填好三段内容并把 status 改为 active。）");
    }
}
/** Auto-takeover on phase-doc write: writing/editing {key}/spec.md, design.md,
 * or plan.md is this window saying "I am now executing key X" — claim it and
 * watch it, exactly like /pm-key switch. A live foreign claim blocks the claim
 * (watch-only) but never the watch itself. Writing design.md / plan.md also
 * runs the next-phase evidence gate (mirrors advance_phase.py): the previous
 * phase's research notes must exist, or the user is warned immediately. */
export async function autoTakeOverFromDoc(pi, indexStore, watch, refreshWatch, key, doc, agenticdocRoot, ctx) {
    // Next-phase evidence gate: writing design.md means the spec phase should be
    // complete (its research notes exist); writing plan.md means design should be.
    // Fires regardless of takeover idempotency — the missing evidence is the
    // message, and it stays true until the notes are written.
    const docs = readPhaseDocs(agenticdocRoot, key);
    if (doc === "spec.md" && docs.specEvidence < 1) {
        ctx.ui.notify(`[mw] ${key}: no evidence/research/spec-*.md found — write the research notes (or a zero-research declaration) alongside the spec; the advance-to-design gate checks them.`, "warning");
    }
    if (doc === "design.md" && docs.specEvidence < 1) {
        ctx.ui.notify(`[mw] ${key}: no evidence/research/spec-*.md found — the advance-to-design gate requires >= 1 research note (a zero-research declaration counts). Write it before advancing.`, "warning");
    }
    if (doc === "plan.md") {
        if (!docs.design) {
            ctx.ui.notify(`[mw] ${key}: design.md missing or under 500 bytes — required before plan (run the system-design workflow).`, "warning");
        }
        else if (docs.designEvidence < 1) {
            ctx.ui.notify(`[mw] ${key}: no evidence/research/design-*.md found — the advance-to-plan gate requires >= 1 research note (a zero-research declaration counts). Write it before advancing.`, "warning");
        }
    }
    const row = indexStore.findByKey(key);
    const wasWatching = watch.key === key;
    const wasClaimed = row?.claimId === windowClaimId();
    if (wasWatching && wasClaimed)
        return; // already ours — nothing to do
    const result = await takeOverKey(indexStore, key, false, agenticdocRoot);
    watch.key = key;
    pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed: result.ok });
    refreshWatch(ctx);
    if (result.ok) {
        ctx.ui.notify(`[mw] claimed key '${key}' (doc write detected) — watching it${result.created ? " (new key registered)" : ""}.`, "info");
        if (result.audit.length > 0)
            ctx.ui.notify(result.audit.join("\n"), "warning");
    }
    else {
        ctx.ui.notify(`[mw] key '${key}' is claimed by another live window (${result.blockedBy}) — watching only.`, "warning");
    }
}
/** Restore this window's watched key from the session file (survives restart
 * and resume) and re-render the bottom widget. A watch that came with a key
 * takeover re-claims the key with this process's identity — quietly, unless
 * another live window took it over in the meantime. */
export async function restoreWatch(pi, watch, indexStore, workerStore, ackStore, agenticdocRoot, ctx) {
    let data;
    try {
        const entries = ctx.sessionManager.getEntries();
        for (let i = entries.length - 1; i >= 0; i--) {
            const e = entries[i];
            if (e.type === "custom" && e.customType === WATCH_ENTRY_TYPE) {
                data = e.data;
                break;
            }
        }
    }
    catch {
        return; // session entries unavailable — nothing to restore
    }
    if (!data?.key)
        return;
    const key = data.key;
    watch.key = key;
    if (data.claimed) {
        const row = indexStore.findByKey(key);
        if (row) {
            const self = windowClaimId();
            if (claimState(row.claimId, self) === "held-live") {
                // Another window took over while this one was closed — keep the
                // watch (display-only) and say so; do not touch the shared row.
                ctx.ui.notify(`[mw] key '${key}' is claimed by another window (${row.claimId}) — watching only.`, "warning");
            }
            else {
                // Our previous process is gone; re-bind ownership through the
                // atomic claim — a window that raced us to this key wins and we
                // degrade to watch-only (review M2). Quiet re-claim: no demote of
                // other active rows, no status flip; only claimId/updated move.
                const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", {
                    demoteOthers: false,
                    activate: false,
                });
                if (!outcome.ok) {
                    ctx.ui.notify(`[mw] key '${key}' is claimed by another window (${outcome.blockedBy}) — watching only.`, "warning");
                }
            }
        }
    }
    setWatchWidget(ctx, renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key));
    // Re-stamp the entry so it lands in the (possibly new) session file.
    pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed: data.claimed ?? false });
    // Saved working context (pm-save): point the user at it — a notice, never
    // an injected instruction (same principle as evidenceReviewNotice: the
    // framework flags, the user decides whether the agent reads it).
    const pmStatePath = path.join(agenticdocRoot, key, "pm-state.md");
    if (fs.existsSync(pmStatePath)) {
        const updated = fs.statSync(pmStatePath).mtime.toISOString();
        ctx.ui.notify(`[mw] key '${key}' 有已保存的 pm-state.md（更新于 ${updated}）。如需接续上次的工作上下文，让 agent 读取 ${key}/pm-state.md 的 Notes 区。`, "info");
    }
}
function pickWorkerRoute(taskContent) {
    // Global default is pi/timi: review/research are routing HINTS for the
    // agent, not claude redirects (design D-005) — a claude worker requires an
    // explicit `cli` param on dispatch_worker / /worker, where missing
    // credentials fail per-task instead of silently degrading the route.
    if (/^type:\s*codex/im.test(taskContent))
        return { cli: "codex", provider: "" };
    return { cli: "pi", provider: "timi" };
}
// Optional `model:` line in task.md → passed through to the launcher as --model/-m.
function readModel(taskContent) {
    const m = taskContent.match(/^model:\s*(.+)$/im);
    return m ? m[1].trim() : "";
}
// Conductor-origin marker line (D-104): `origin: conductor`. Conductor task.md
// files are rendered by autopilot/dispatch.py render_task_md; the value is the
// literal token "conductor" (line-exact, CRLF-tolerant).
const ORIGIN_LINE_RE = /^origin:[ \t]*(\S+)[ \t\r]*$/m;
/** Dispatch origin of a task.md, when it carries an `origin:` line. */
function readTaskOrigin(taskContent) {
    return ORIGIN_LINE_RE.exec(taskContent)?.[1];
}
/** Is this a conductor-owned task (D-104)? Such tasks are queued by the
 * conductor alone — the TS scan must never upsert them, closing both the
 * scan/upsert race and the re-insert-as-pending path that a launcher restart
 * (or an archived row) would otherwise open. Manual/legacy tasks carry no
 * marker and behave exactly as before (AC-012 zero regression). Unreadable
 * task.md returns false so the dispatch loop hits the same read error it
 * always did. */
function isConductorTask(taskMdPath) {
    try {
        return readTaskOrigin(fs.readFileSync(taskMdPath, "utf8")) === "conductor";
    }
    catch {
        return false;
    }
}
export async function dispatchNewTasks(workerStore, agenticdocRoot, opts = {}) {
    // Worker tasks live under {key}/workers/<task-key>/task.md (owner = AgenticTask
    // key) or _scratch/workers/<task-key>/task.md (keyless ad-hoc). Root-level
    // task dirs are no longer dispatched - they polluted the key namespace.
    if (!fs.existsSync(agenticdocRoot))
        return;
    const dispatched = new Set(workerStore.readAll().map((e) => e.taskKey));
    let owners;
    try {
        owners = fs.readdirSync(agenticdocRoot, { withFileTypes: true });
    }
    catch {
        return;
    }
    for (const owner of owners) {
        if (!owner.isDirectory() || owner.name.startsWith("."))
            continue;
        const workersDir = path.join(agenticdocRoot, owner.name, "workers");
        let taskDirs;
        try {
            taskDirs = fs.readdirSync(workersDir, { withFileTypes: true });
        }
        catch {
            continue; // owner has no workers/ dir (plain key or meta entry)
        }
        // Collect undispatched tasks FIRST (AC-010): a key with nothing new to
        // queue must not even evaluate the docs gate — fully-queued undoc keys
        // are historical, not actionable, and gate noise for them drowns real
        // blockage in multi-key projects.
        const undispatched = [];
        for (const taskDir of taskDirs) {
            if (!taskDir.isDirectory() || taskDir.name.startsWith("."))
                continue;
            const taskKey = taskDir.name;
            if (dispatched.has(taskKey))
                continue;
            const taskMdPath = path.join(workersDir, taskKey, "task.md");
            if (!fs.existsSync(taskMdPath))
                continue;
            // D-104: conductor-owned tasks (origin: conductor) never enter the TS
            // dispatch path — not queued, not upserted, and not counted as
            // undispatched work for the docs gate below. The conductor is their
            // only queue writer; its reconciliation is the sole repair path.
            if (isConductorTask(taskMdPath))
                continue;
            undispatched.push({ taskKey, taskMdPath });
        }
        if (undispatched.length === 0)
            continue;
        // Docs gate: real AgenticTask keys must be fully documented (spec + design
        // + research evidence) before their worker tasks enter the queue. _scratch
        // is the ad-hoc escape hatch. Report each blocked key at most once.
        if (owner.name !== SCRATCH_WORKERS_KEY) {
            const gaps = dispatchDocGaps(agenticdocRoot, owner.name);
            if (gaps.length > 0) {
                if (!opts.warnedKeys?.has(owner.name)) {
                    // Mark as warned only when the notifier actually broadcast —
                    // a suppressed broadcast (scoped to another window's key) must
                    // not burn this key's once-per-session slot (review m1).
                    if (opts.onDocGate?.(owner.name, gaps) !== false) {
                        opts.warnedKeys?.add(owner.name);
                    }
                }
                continue;
            }
        }
        for (const { taskKey, taskMdPath } of undispatched) {
            const taskContent = fs.readFileSync(taskMdPath, "utf8");
            const { cli, provider } = pickWorkerRoute(taskContent);
            const model = readModel(taskContent);
            try {
                await dispatchTask({
                    taskKey,
                    status: "pending",
                    cli,
                    provider,
                    model,
                    taskPath: taskMdPath,
                }, workerStore);
            }
            catch (err) {
                // Fail-closed (mw-dual-workspace AC-007): an unusable target.yml
                // must never silently degrade to an un-injected task.md — the task
                // stays undispatched and is retried on the next scan once the
                // config is fixed. Per-task isolation: one bad task never blocks
                // the rest of the scan.
                console.error(`[mw] dispatch refused for ${taskKey}: ${err instanceof Error ? err.message : String(err)}`);
            }
        }
    }
}
/** Continuation directive appended to terminal worker results: the finish
 * call wakes an idle PM (triggerTurn) — this line tells it what "continue the
 * PM loop" means per terminal status, so results are processed and the next
 * task is dispatched without the user re-prompting. Timeout failures get an
 * explicit retry policy (AC-004/D-005): the Exit Reason in the readback body
 * distinguishes idle (true hang) from wall (healthy but out of budget). */
const PM_CONTINUE_HINT = "[mw] worker 终态回读。请继续 PM 循环：吸收上述结果（done→推进下一任务/phase；failed→读 worker.log 与 trace.log 排查后决定重试或修复；needs-clarification→整理问题向用户澄清；超时失败（Exit Reason 含 idle/wall timeout）→ wall 型用双倍 timeout 预算重派一次，再失败转 PM 直执，idle 型直接排查环境），然后派发下一个任务或汇报阶段完成。吸收终态结果后调用 ack_worker_result(task_key)（或 /mw ack all）确认处理完成，widget 待处理区才会清空。";
/** Runtime stats for terminal worker summaries (AC-013):
 * ` (6m-style coarse duration, ph i/n)`. Preference order: exact [START]→[END]
 * interval from trace.log (present on every new-bundle terminal task), ≥2
 * [HEARTBEAT] lines (older format), then the queue row's dispatchedAt→updatedAt
 * (coarse but always present). Empty when nothing is derivable. */
function heartbeatStatsSuffix(taskDir, entry) {
    const prog = readTaskProgress(taskDir);
    if (prog?.startTs && prog.endTs) {
        const durMs = Math.max(0, Date.parse(prog.endTs) - Date.parse(prog.startTs));
        const ph = prog.endPhases && prog.endPhases !== "-" ? `, ph ${prog.endPhases}` : "";
        return ` (${formatHeartbeatAge(durMs)}${ph})`;
    }
    const hb = prog?.heartbeat;
    if (hb && hb.count >= 2) {
        const durMs = Math.max(0, Date.parse(hb.lastTs) - Date.parse(hb.firstTs));
        const ph = hb.phase === "-" ? "" : `, ph ${hb.phase}/${hb.phaseTotal}`;
        return ` (${formatHeartbeatAge(durMs)}${ph})`;
    }
    const durMs = Date.parse(entry.updatedAt) - Date.parse(entry.dispatchedAt);
    if (!Number.isNaN(durMs) && durMs > 0)
        return ` (${formatHeartbeatAge(durMs)})`;
    return "";
}
export function startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, ui, pollIntervalMs = POLL_INTERVAL_MS) {
    // Baseline snapshot: rows already terminal when this window opens are
    // history — never replay their summaries. Only transitions observed while
    // this session is open are notified, at most once each.
    const notified = new Set(workerStore
        .readAll()
        .filter((e) => isTerminal(e.status))
        .map((e) => e.taskKey));
    // Running workers already escalated for divergence (AC-004): one PM wake
    // per task, at the first mid/high convergence checkpoint.
    const escalated = new Set();
    let widgetShown = false;
    return setInterval(() => {
        try {
            // Live bottom widget for the watched key (per-window state, NOT the
            // shared _index.parallel active set — every window decides its own key).
            if (watch.key) {
                applyWatchWidget(ui, renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, watch.key));
                widgetShown = true;
            }
            else if (widgetShown) {
                applyWatchWidget(ui, undefined);
                widgetShown = false;
            }
            const entries = workerStore.readAll();
            // Divergence escalation (AC-004): running workers past the convergence
            // checkpoint whose machine risk is mid/high wake the PM once per task
            // with the evidence — the PM (fullest context) decides continue /
            // descope / kill + split / takeover. Low-risk checkpoints stay in the
            // widget only; no cross-window broadcast (scoped to the watched key).
            for (const entry of entries) {
                if (entry.status !== "running" || escalated.has(entry.taskKey))
                    continue;
                if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key)
                    continue;
                const ck = readTaskProgress(path.dirname(entry.taskPath))?.checkpoint;
                if (!ck || ck.risk === "low")
                    continue;
                escalated.add(entry.taskKey);
                const taskDir = path.dirname(entry.taskPath);
                deliverPmAlert(pi, `[mw] 发散风险：worker '${entry.taskKey}' 检查点 risk=${ck.risk}` +
                    `（elapsed ${Math.round(ck.elapsedS / 60)}m，reads=${ck.reads} writes=${ck.writes}，phases=${ck.phases}，` +
                    `重复读 top=${ck.repeatTop}）。机器判据仅供参考——请结合本 key 最全上下文判断：继续等待 / steer 收窄范围 / 终止并分拆重派 / PM 直执。` +
                    `证据：${path.join(taskDir, "trace.log")}（[CHECKPOINT] 行）与 ${path.join(taskDir, "progress.md")}（自评行；无写工具角色另含框架机器行）。`);
            }
            for (const entry of entries) {
                if (notified.has(entry.taskKey) || !isTerminal(entry.status))
                    continue;
                notified.add(entry.taskKey);
                // One-shot transcript summaries fire only for this window's watched
                // key; without a watched key the window stays silent (no cross-window
                // broadcast). The widget above still shows current state either way.
                if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key)
                    continue;
                // Task dir from the queue row taskPath: works for keyed {key}/workers/<task-key>/ and legacy root paths.
                const taskDir = path.dirname(entry.taskPath);
                // Terminal readback (AC-014): inject the full output.md body into
                // the conversation so worker results reach the PM without manual
                // file reads. Falls through to the spawn-failure / no-output
                // notices when there is nothing to read back. Sent via
                // deliverWorkerResult (triggerTurn) so an idle PM wakes up,
                // processes the result, and runs the next step — the finish call
                // of dispatch → monitor → finish call → pm run (AC-015).
                const header = `[${entry.taskKey}] ${entry.status}${heartbeatStatsSuffix(taskDir, entry)}`;
                const body = readOutputBody(taskDir);
                if (body) {
                    deliverWorkerResult(pi, `${header}:\n\n${body}\n\n${PM_CONTINUE_HINT}`);
                }
                else {
                    // Terminal but no output.md summary — never stay silent. Prefer the
                    // launcher's exact spawn-failure reason (e.g. missing credential) over
                    // the generic crash/timeout guess; both point at the per-task log.
                    const logPath = path.join(taskDir, "worker.log");
                    const spawnFailure = readSpawnFailure(taskDir);
                    deliverWorkerResult(pi, `${header} — ${spawnFailure
                        ? `${spawnFailure}。日志：${logPath}`
                        : `无 output.md 摘要（worker 可能崩溃/超时）。日志：${logPath}`}\n\n${PM_CONTINUE_HINT}`);
                }
            }
        }
        catch {
            // Transient I/O error (e.g. EACCES during concurrent rename) — skip this tick
        }
    }, pollIntervalMs);
}
/** Marker opening the injected parallel-protocol block, and the idempotency
 * guard: a handler that already sees it in the chained system prompt must not
 * append it a second time (two loaded bundle copies would otherwise duplicate
 * the text on every run). */
export const PARALLEL_PROTOCOL_MARKER = "[mw] 并行优先协议";
/** Static parallel-first rules appended to the PM window's system prompt once
 * per agent run (mw-parallel-protocol). Static on purpose: a constant suffix
 * keeps the system-prompt prefix cacheable, and `before_agent_start` costs no
 * session tokens (an injected message would accumulate one per run). The two
 * conflict surfaces are deliberately different: research/review workers are
 * read-only (worker-mode.ts TOOL_ALLOWLISTS), so research batches in the
 * spec/design phases parallelize freely and only need a unique note file per
 * research question; coding workers share files and must be split by
 * file/module boundary. PM-only by construction: pmActivate() runs only when
 * PI_WORKER_TASK is unset (index.ts). */
export const PARALLEL_PROTOCOL = [
    `${PARALLEL_PROTOCOL_MARKER}（PM 常驻规则）：`,
    "1. 拆解任何 phase（spec/design/plan/tasks）之前，先做并行性分析：可并行单元 / 共享资源与文件冲突面 / 必须串行的理由。",
    "2. spec/design 的调研与证据收集默认全并行：把调研拆成互不重叠的研究问题 RQ-1..N，一次性派发 N 个 type: research worker",
    "   （只读角色，彼此无文件冲突），每个 RQ 只写唯一的 evidence/research/<phase>-<rq-slug>-<date>.md；禁止两个 worker 写同一文件。",
    "3. 编码按文件/模块边界并行：同一文件同一时刻只允许一个 worker。",
    "4. 相位文档（spec.md / design.md）由 PM 自己串行写，不派 worker。",
    "5. 派发前先看 widget 上的 running worker 数：能并行就不要串行等待；worker 终态回读后立刻补派下一批。",
].join("\n");
export function pmActivate(pi) {
    const projectDir = process.cwd();
    const agenticdocRoot = resolveAgenticdocRoot(projectDir);
    const workerStore = new WorkerStore(agenticdocRoot);
    const ackStore = new AckStore(agenticdocRoot);
    const indexStore = new IndexStore(agenticdocRoot);
    // Per-window watch state: the key THIS window explicitly executes (set via
    // /mw-watch or /pm-key switch|new). Worker summaries and the bottom progress
    // widget are scoped to it — replacing the old global active-keys matching
    // that made every window notify about every active key.
    const watch = { key: undefined };
    const ui = { ctx: undefined };
    const refreshWatch = (ctx) => {
        if (!watch.key) {
            setWatchWidget(ctx, undefined);
            return;
        }
        setWatchWidget(ctx, renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, watch.key));
    };
    // Register commands and tools during loading (safe — not action methods)
    registerPmKeyCommands(pi, indexStore, watch, refreshWatch, agenticdocRoot);
    registerPmSaveCommand(pi, indexStore, workerStore, watch, agenticdocRoot);
    registerMwCommands(pi, projectDir, workerStore, ackStore);
    registerMwTools(pi, projectDir);
    registerAdvancePhaseTool(pi, projectDir);
    registerWorkerTools(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, projectDir);
    registerSwitchKeyTool(pi, indexStore, watch, refreshWatch, agenticdocRoot);
    registerWorkerCommands(pi, workerStore, indexStore, agenticdocRoot, watch, projectDir);
    // RAG tool surface (D-002): registration is structural — an empty enabled
    // set registers nothing and probes nothing. A broken config must not take
    // the whole PM window down (dispatch is gated separately in ui-bridge).
    try {
        registerRagTools(pi, projectDir);
    }
    catch (err) {
        console.error(`[mw] rag tools disabled: ${err instanceof Error ? err.message : String(err)}`);
    }
    registerWatchCommand(pi, watch, refreshWatch, indexStore);
    // Autopilot console (T-15): /autopilot status|gates|gate|timeline|enable|
    // disable|pause|resume|roadmap — stateless, file-derived (D-005).
    registerAutopilotCommands(pi, projectDir);
    // Dispatch model chain, main-window side (mw-dispatch-models): record this
    // window's model for worker inheritance and apply a configured `main` role.
    registerMainWindowModel(pi);
    // Hard gate: pm-state.md's '- Phase:' / '- Claim-Id:' interface lines are
    // script-owned (advance_phase.py / update_index.py). Hand-editing them is
    // how phase gates get bypassed (mw-worker-timeout-convergence: pm-state
    // hand-set to EXECUTE while _index.parallel stayed at SPEC), so the edit is
    // blocked at the tool layer and the agent is pointed at the script.
    registerPmStateGuard(pi, projectDir, agenticdocRoot);
    // Parallel-first protocol (mw-parallel-protocol): append the constant block
    // to this run's system prompt. Appending (never replacing) preserves what
    // other extensions chained in before us.
    pi.on("before_agent_start", (event) => {
        const base = typeof event.systemPrompt === "string" ? event.systemPrompt : "";
        if (base.includes(PARALLEL_PROTOCOL_MARKER))
            return undefined;
        return { systemPrompt: base === "" ? PARALLEL_PROTOCOL : `${base}\n\n${PARALLEL_PROTOCOL}` };
    });
    // Start worker status poll loop (setInterval is safe; displaySummary inside fires later)
    const pollHandle = startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, ui);
    // Session teardown stops the loop (review m3): a fresh runtime re-runs
    // pmActivate and starts a new one, so this only removes the zombie that
    // would keep ticking against a disposed context after /reload or session
    // replacement.
    pi.on("session_shutdown", () => clearInterval(pollHandle));
    // After each agent turn, scan for new task.md files and dispatch them (AC-030).
    // Undocumented keys are skipped and reported once per session (docs gate).
    // Gate broadcast is scoped to this window's watched key (AC-011) — the scan
    // itself stays global, and blocking semantics are unchanged.
    const docGateWarned = new Set();
    pi.on("agent_settled", () => {
        dispatchNewTasks(workerStore, agenticdocRoot, {
            warnedKeys: docGateWarned,
            onDocGate: makeScopedDocGateNotifier(pi, watch),
        }).catch(() => {
            // Dispatch errors are non-fatal — PM loop continues
        });
    });
    // Spec-write auto-takeover: tool_execution_end carries no args, so correlate
    // them with the args captured on tool_execution_start via toolCallId. Only
    // write/edit calls are tracked; the map entry is consumed on end.
    const pendingToolArgs = new Map();
    pi.on("tool_execution_start", (event) => {
        if (event.toolName === "write" || event.toolName === "edit") {
            pendingToolArgs.set(event.toolCallId, { toolName: event.toolName, args: event.args });
        }
    });
    // Evidence-review notices fire once per (key, phase) per session.
    const evidenceReviewNotified = new Set();
    pi.on("tool_execution_end", (event, ctx) => {
        const pending = pendingToolArgs.get(event.toolCallId);
        pendingToolArgs.delete(event.toolCallId);
        if (!pending || event.isError)
            return;
        const target = docWriteTarget(pending.toolName, pending.args, projectDir, agenticdocRoot);
        if (target) {
            autoTakeOverFromDoc(pi, indexStore, watch, refreshWatch, target.key, target.doc, agenticdocRoot, ctx).catch(() => {
                // Takeover failures (e.g. lock contention) must never disturb the turn
            });
            // Phase-doc write with its evidence already present → notice that the
            // doc's claims can be re-reviewed against the notes (plan has no
            // evidence phase). A notice, never an injected instruction.
            if (target.doc !== "plan.md") {
                evidenceReviewNotice(ctx, target.key, target.doc === "spec.md" ? "spec" : "design", agenticdocRoot, evidenceReviewNotified);
            }
            return;
        }
        // Research-note write: not a claim signal, but it may complete the
        // evidence set for an already-written phase doc → review notice.
        const ev = evidencePhaseFromWrite(pending.toolName, pending.args, projectDir, agenticdocRoot);
        if (ev) {
            evidenceReviewNotice(ctx, ev.key, ev.phase, agenticdocRoot, evidenceReviewNotified);
        }
    });
    // Defer action method calls to after runner.initialize() (session_start fires post-init)
    pi.on("session_start", async (_event, ctx) => {
        // Capture the UI context so the poll loop can render the bottom widget.
        ui.ctx = ctx;
        // Autopilot progress panel: auto-show for enabled projects so a stalled
        // key is visible without anyone running a command (mw-autopilot-stall-feedback
        // AC-008). An explicit /autopilot monitor off suppresses it for this session.
        autoStartMonitor(ctx, projectDir);
        // Resume the watched key this session had before restart/resume.
        await restoreWatch(pi, watch, indexStore, workerStore, ackStore, agenticdocRoot, ctx);
        // Auto-init project if it hasn't been initialized yet. Gate on .agenticdoc
        // (the project marker mw init creates), NOT on a project-local bundle copy:
        // the extension is now installed GLOBALLY (mw setup), so no project-local
        // bundle exists and checking for one would re-run init on every session.
        const initialized = fs.existsSync(path.join(projectDir, ".agenticdoc"));
        if (!initialized) {
            const result = initMw(projectDir);
            if (result.ok) {
                displaySummary(pi, "[mw] Project initialized — .agenticdoc/ .mw/ .pi/extensions/ created.");
            }
            else {
                displaySummary(pi, `[mw] Init failed: ${result.error}`);
                return;
            }
        }
        // Auto-start mw background service if not already running.
        // After spawning, poll for the PID file so the agent's first turn doesn't
        // race against Python startup and falsely report mw as not running.
        // Stability window: the PID must stay alive for 3s — mw serve can die
        // right after startup (route precheck failure) and the old check would
        // report a false "started" in that window (mw-dispatch-reliability AC-005).
        const mwStatus = getMwStatus(projectDir);
        if (!mwStatus.running) {
            const started = startMw(projectDir);
            if (started) {
                const confirmed = await waitForMwStart(projectDir, 8000);
                displaySummary(pi, confirmed
                    ? "[mw] Background service started."
                    : "[mw] Background service 启动未确认（可能预检失败或仍在启动）——运行 /mw doctor 诊断。");
            }
            else {
                displaySummary(pi, "[mw] Could not find mw.py — run `mw start --project=.` manually.");
            }
        }
        else {
            // Stale-serve detection: a serve started before the current mw code
            // silently misses features (e.g. conductor supervision) — surface it
            // instead of letting /autopilot enable promise a conductor that never
            // spawns.
            const stale = serveStaleness(projectDir);
            if (stale?.stale) {
                displaySummary(pi, `[mw] serve (PID ${mwStatus.pid}) is running stale code — ${stale.detail}. Run /mw restart.`);
            }
        }
        // The project goal is the north-star every key/spec derives from.
        // Do NOT fabricate a placeholder — if it isn't established yet, softly
        // guide the user into the goal brainstorm workflow (/goal). An
        // established goal (or a legacy goal.md with content) is left untouched.
        // Headless sessions skip the goal nudge (see nudgeGoalUnestablished).
        nudgeGoalUnestablished(pi, agenticdocRoot, ctx.hasUI);
    });
}
//# sourceMappingURL=pm-orchestrator.js.map