import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Type } from "typebox";
import { VERSION } from "../../../config.js";
import { validateRagEnabled } from "../rag/tools.js";
import { runAgenticScript } from "../shared/agentic-scripts.js";
import { cardDigest } from "../shared/card-digest.js";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.js";
import { CLAIM_GATE_DEFAULT, CLAIM_TYPES, claimBudgetCaps, claimsGaps, ENVELOPE_HEADING_FAMILIES, ENVELOPE_SECTION_LABELS, parseClaimsBlock, readEnvelope, seedItemsMissing, typeExtrasMissing, } from "../shared/dispatch-card.js";
import { DISPATCHABLE_TYPES, detectImageNeed, modelImageCapability, readRoleModel, roleForTaskType, validateModelValue, } from "../shared/dispatch-models.js";
import { acquireLock } from "../shared/file-lock.js";
import { formatHeartbeatAge, HEARTBEAT_STALE_MS, readTaskProgress } from "../shared/heartbeat.js";
import { isScratchKey, keyNameRefusal, normalizeKey, parseSyntheticClaim, RESERVED_INDEX_NAMES, readIndexMdActive, syntheticClaimLive, } from "../shared/index-store.js";
import { buildMw, decideMw, doctorMw, getMwStatus, initMw, modelMw, partitionMw, RAG_SUBCOMMANDS, ragMw, restartMw, serveStaleness, startMw, statsMw, stopMw, targetMw, updateEnvMw, } from "../shared/mw-runner.js";
import { readLastProductSectionBody } from "../shared/output-sections.js";
import { SCRATCH_WORKERS_KEY, workerTaskDir } from "../shared/paths.js";
import { DOC_GATE_HINT, dispatchDocGaps, formatDocsBadge, readPhaseDocs } from "../shared/phase-docs.js";
import { syncPmStateClaimId } from "../shared/pm-state-claim.js";
import { PHASE_ORDER, phaseAuditWarnings } from "../shared/pm-state-guard.js";
import { runDetachedMw } from "../shared/run-detached.js";
import { classifyWriteTargetShape, judgeWriteTarget as judgeSharedWriteTarget, WORKER_FILE_NAME_RE, } from "../shared/write-surface.js";
import { RECOVERY_CONTRACT_HEADING, recoveryContractSection } from "../worker/output-sections.js";
import { isSameOrUnder } from "../worker/read-scope.js";
// W1 (mw-worker-output-contract): shape classification and the basename
// whitelist moved to the write-surface single source; these re-exports keep the
// existing `pm/ui-bridge.ts` importers byte-compatible.
export { classifyWriteTargetShape } from "../shared/write-surface.js";
import { isShellRole, isWritelessRole } from "../worker/worker-mode.js";
import { formatDispatchAlarm, recordDispatchAlarm } from "./pm-orchestrator.js";
import { StateManager } from "./state-manager.js";
import { dispatchTask } from "./task-dispatcher.js";
import { buildTriageState, canonicalStateBytes, DP1_ID, DP1_QUESTIONS_VERSION, formatTriageLedgerDetail, formatTriageReceipt, MAX_STRUCTURED_STATE_BYTES, prepareStructuredState, readDecidePolicy, TRIAGE_REASON_INPUT_OVERSIZE, triageDispatch, } from "./triage-client.js";
/** Owner key for a worker task — this window's own claim first, the shared
 * active pointer second. Explicit key wins (deliberate choice — no warning).
 * Otherwise, when this window watches a key whose _index.parallel row it
 * holds (claimId === this window's host:pid), dispatches land under that key
 * even when another window's later takeover made a different row the
 * globally-latest active one: single-active demote flips the shared pointer
 * between windows, but ownership does not move. A stale or foreign watch
 * (no claim held) falls back to the global active row — but never one held
 * live by another window (injecting work into another window's key is the
 * cross-window dispatch bug this guards); that case degrades to _scratch
 * with a warning. Then the degraded _index.md `active:` pointer, then
 * _scratch. */
export function resolveOwnerKeyWithSync(pi, indexStore, watch, explicit, agenticdocRoot) {
    const explicitKey = (explicit ?? "").trim();
    if (explicitKey)
        return explicitKey;
    const self = windowClaimId();
    if (watch.key) {
        // _scratch is watchable but never indexed; a window watching it means
        // its ad-hoc dispatches belong there.
        if (isScratchKey(watch.key))
            return SCRATCH_WORKERS_KEY;
        if (indexStore.findByKey(watch.key)?.claimId === self)
            return watch.key;
    }
    const active = indexStore.activeEntry();
    if (active && claimHeldByAnotherWriter(claimState(active.claimId, self))) {
        warnForeignActiveOnce(pi, active.key);
        return SCRATCH_WORKERS_KEY;
    }
    // `_index.md active:` is a degraded pointer that carries NO claim column, so
    // it cannot be trusted by itself (A7): resolve it back to the
    // `_index.parallel` row and apply the SAME name + liveness gate as the
    // active-row branch. A foreign live value and a reserved/illegal name both
    // degrade to _scratch with a warning instead of silently becoming an owner
    // key in another window's namespace.
    const fallbackKey = active?.key ?? readIndexMdActive(agenticdocRoot);
    if (fallbackKey) {
        if (keyNameRefusal(fallbackKey)) {
            warnForeignActiveOnce(pi, fallbackKey);
            return SCRATCH_WORKERS_KEY;
        }
        const row = indexStore.findByKey(fallbackKey);
        if (row && claimHeldByAnotherWriter(claimState(row.claimId, self))) {
            warnForeignActiveOnce(pi, fallbackKey);
            return SCRATCH_WORKERS_KEY;
        }
        if (watch.key && normalizeKey(watch.key) !== normalizeKey(fallbackKey)) {
            warnOwnerMismatchOnce(pi, watch.key, fallbackKey);
        }
        return fallbackKey;
    }
    if (watch.key)
        warnOwnerMismatchOnce(pi, watch.key, SCRATCH_WORKERS_KEY);
    return SCRATCH_WORKERS_KEY;
}
/** Warned (watch -> owner) pairs this session. displaySummary persists the
 * warning to the transcript (LLM-visible), so once per pair is enough. */
const warnedOwnerMismatches = new Set();
function warnOwnerMismatchOnce(pi, watchKey, ownerKey) {
    const pair = `${watchKey}->${ownerKey}`;
    if (warnedOwnerMismatches.has(pair))
        return;
    warnedOwnerMismatches.add(pair);
    displaySummary(pi, `[mw] owner-key mismatch: this window watches '${watchKey}' but holds no claim on it, and the active key is '${ownerKey}' — ` +
        `dispatching under '${ownerKey}'. Run /pm-key switch ${ownerKey} to align the window.`);
}
/** Warned foreign active keys this session (same once-per-pair rationale as
 * warnedOwnerMismatches). */
const warnedForeignActives = new Set();
function warnForeignActiveOnce(pi, activeKey) {
    if (warnedForeignActives.has(activeKey))
        return;
    warnedForeignActives.add(activeKey);
    displaySummary(pi, `[mw] active key '${activeKey}' is claimed by another live window — not dispatching under it; ` +
        `using '${SCRATCH_WORKERS_KEY}' instead. Pass an explicit key, or switch_key in this window first.`);
}
export function displaySummary(pi, summary) {
    pi.sendMessage({
        customType: "agent-team-loop:worker-summary",
        content: summary,
        display: true,
        details: summary,
    });
}
/** Deliver a message into the conversation AND trigger a PM turn — the
 * shared "wake the PM" channel (finish calls and mid-run escalations).
 * `pi.sendMessage` without `triggerTurn` only injects the message into LLM
 * context: it displays in the transcript, but an idle PM never wakes up.
 * With `triggerTurn: true` an idle PM starts an LLM turn immediately; a
 * streaming PM gets the text steered into the current turn. Informational
 * notices (init, mw start, gate skips) stay passive via displaySummary —
 * they must not spend agent turns. */
export function deliverPmAlert(pi, text) {
    pi.sendMessage({
        customType: "agent-team-loop:worker-summary",
        content: text,
        display: true,
        details: text,
    }, { triggerTurn: true });
}
/** Deliver a terminal worker result (the "finish call" of dispatch →
 * monitor → finish call → pm run). See deliverPmAlert for the channel. */
export function deliverWorkerResult(pi, summary) {
    deliverPmAlert(pi, summary);
}
/** The decision a dp1 dispatch CONSUMES from one usable triage result.
 *
 * D-041 makes adoption a consuming-side fact: Python's `acted=false` only says
 * it did not execute an action itself (an `answer` intent never executes), not
 * that the answer was rejected. The dispatch side therefore adopts the triage
 * type itself — but ONLY when the child actually authorized it (`mode=auto`),
 * delivered a `triage_type` and a `decision_id`, AND that type is the one this
 * dispatch actually uses. Task.md has exactly three states:
 *
 * | mode | `triage_type` vs dispatched | acted | `decision:` head line |
 * | --- | --- | --- | --- |
 * | `auto` | equal (agree) | `true` | written |
 * | `auto` | different (disagree) | `false` | not written |
 * | `suggest` (any) | either | `false` | not written |
 *
 * AC-014: the dispatch never rewrites its `type:` from the advice, so a
 * disagreeing answer was NOT adopted (T-04c adoption = "the dispatcher took
 * this type"). Counting it as adopted would push a disagreement into the
 * agreement-rate numerator, so it stays un-correlated exactly like `suggest`:
 * the answer and its `decision_id` remain observable in the {@link TriageResult}
 * (the ledger/report channel), only the head line is withheld. A missing or
 * empty dispatched type also fails closed (never "unknown means adopted").
 * An unavailable result and an answer without an id are undefined too, so the
 * task.md bytes stay byte-identical to the pre-T-08 shape. This never reads
 * `.mw/decide-points.json` (D-036). */
function dispatchDecisionOf(result, dispatchedType) {
    if (!result.available || result.mode !== "auto" || result.triage_type === undefined)
        return undefined;
    // AC-014 disagreement gate: an advice naming another type was not adopted.
    if (result.triage_type !== dispatchedType)
        return undefined;
    const decisionId = (result.decision_id ?? "").trim();
    if (decisionId === "")
        return undefined;
    return { decisionId, acted: true };
}
const DP1_TYPE_CHOICES = ["coding", "research", "review"];
/** Repo-relative path shape a write-face entry must have to become dp1 input.
 * Prose in the `## 写入允许面` section ("仅本任务目录下的 task.md…") is not a
 * scope declaration and is skipped, as is anything absolute (L2: a state never
 * carries an absolute path). A card whose whole face is prose therefore yields
 * no scope and the dispatch falls back to the legacy state (traced). */
const WRITE_FACE_PATH_RE = /^[A-Za-z0-9_.@+-]+(?:\/[A-Za-z0-9_.@*+-]+)+$/;
/** Repo-relative directories for `scope.write_scope` (D6 Q1.1: ≤12 items,
 * ≤32 UTF-8 bytes each, ≤384 total). Each path-shaped write-face entry
 * contributes its own directory, coarsened upward (parent by parent) until it
 * fits the 32-byte cap — coarsening can only WIDEN the reported scope, never
 * narrow it, so the decision input never understates the blast radius. */
function writeScopeDirs(entries) {
    const out = [];
    for (const raw of entries) {
        const entry = raw.trim().replace(/\\/g, "/").replace(/^\.\//, "");
        if (!WRITE_FACE_PATH_RE.test(entry))
            continue;
        const segments = entry.split("/").filter((part) => part !== "");
        // A trailing file segment is not a directory: write scope is directories.
        const dirs = /\.[A-Za-z0-9]{1,8}$/.test(segments.at(-1) ?? "") ? segments.slice(0, -1) : segments;
        let dir = dirs.join("/");
        while (Buffer.byteLength(dir, "utf8") > 32 && dirs.length > 1) {
            dirs.pop();
            dir = dirs.join("/");
        }
        if (dir === "" || Buffer.byteLength(dir, "utf8") > 32)
            continue;
        if (!out.includes(dir))
            out.push(dir);
    }
    return out.slice(0, 12);
}
/** Extension set for `scope.file_extensions` (D6 Q1.1: ≤6 items, ≤8 bytes
 * each, ≤36 total) — the extensions of the write-face entries that name files.
 * An empty set is a missing required field, never a fabricated default. */
function writeScopeExts(entries) {
    const seen = new Set();
    for (const raw of entries) {
        const entry = raw.trim().replace(/\\/g, "/");
        if (!WRITE_FACE_PATH_RE.test(entry))
            continue;
        const match = /\.[A-Za-z0-9]{1,8}$/.exec(entry);
        if (match === null)
            continue;
        const ext = match[0].slice(1).toLowerCase();
        if (ext === "" || Buffer.byteLength(ext, "utf8") > 8)
            continue;
        seen.add(ext);
    }
    const kept = [];
    let total = 0;
    for (const ext of [...seen].sort()) {
        const size = Buffer.byteLength(ext, "utf8");
        if (kept.length >= 6 || total + size > 36)
            continue;
        kept.push(ext);
        total += size;
    }
    return kept;
}
/** Code-point-safe byte truncation (never splits a surrogate pair). */
function truncateUtf8Value(text, maxBytes) {
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
/** L1 `task_summary` (≤600B): the description's first non-empty line, collapsed
 * to one line, with absolute paths replaced by `<path>` (L2 has no place in a
 * dp state). No summary means a missing required field, i.e. legacy fallback. */
function dispatchTaskSummary(description) {
    const firstLine = (description ?? "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .find((line) => line !== "") ?? "";
    const scrubbed = firstLine
        .replace(/[A-Za-z]:[\\/][^\s,，、;；)）]*/g, "<path>")
        .replace(/(^|\s)\/(?:[\w.@+-]+\/)+[\w.@+-]*/g, "$1<path>")
        .replace(/\s+/g, " ")
        .trim();
    return truncateUtf8Value(scrubbed, 600);
}
/** Dispatch-time risk label for dp1.
 *
 * dp1 runs BEFORE the first checkpoint, so there is no `computeRisk` machine
 * signal to read. The label is therefore the PM's own blast-radius
 * classification of the plan it is about to dispatch — a foreign-write
 * authorization is `high`, a writeless (read-only) role is `low`, every other
 * write role is `mid` — and `risk_source` says `pm-label` so no consumer can
 * mistake it for machine evidence. It is derived from declared dispatch
 * properties, never a placeholder default (spec §5.4 / D6 Q5.1 禁静默默认值). */
function dispatchRisk(taskType, allowForeignWrite) {
    if (allowForeignWrite)
        return "high";
    return isWritelessRole(taskType) ? "low" : "mid";
}
const STATE_CONTEXT_KEY = "context";
/** dp1 `context.task_excerpt` cap (W6 / D-052). */
const DP1_TASK_EXCERPT_MAX = 1200;
/** Bytes the enclosing `"context":` key adds, reserved out of the state budget. */
const STATE_CONTEXT_OVERHEAD = 16;
function readDottedPath(state, dotted) {
    let current = state;
    for (const part of dotted.split(".")) {
        if (current === null || typeof current !== "object" || Array.isArray(current))
            return undefined;
        current = current[part];
    }
    return current;
}
function isBlankStateValue(value) {
    return value === undefined || value === null || (typeof value === "string" && value.trim() === "");
}
/** Assert one built state matches its registry row (W6: the registry is the
 * field-list authority, so a producer may never send a second hand-written
 * list). Missing required paths AND uncontrolled keys throw; `context` is the
 * only extra top-level key and its slots must be in the dp's `contextSlots`.
 *
 * The extras check is deliberately top-level: the registry lists required paths
 * only, while a dp may also carry OPTIONAL L1 children (dp2's
 * `progress.writes`/`trend`), which must not read as drift. */
export function assertStateMatchesRegistry(dpId, state) {
    const entry = DECIDE_REGISTRY[dpId];
    if (entry === undefined)
        throw new Error(`decide registry: unknown dp '${dpId}'`);
    const required = entry.requiredStateFields.map((field) => field.name);
    const missing = required.filter((path) => isBlankStateValue(readDottedPath(state, path)));
    const allowedTopLevel = new Set(required.map((path) => path.split(".")[0] ?? path));
    allowedTopLevel.add(STATE_CONTEXT_KEY);
    const extra = Object.keys(state).filter((key) => !allowedTopLevel.has(key));
    const context = state[STATE_CONTEXT_KEY];
    if (context !== undefined) {
        if (context === null || typeof context !== "object" || Array.isArray(context)) {
            extra.push(`${STATE_CONTEXT_KEY}:<not-an-object>`);
        }
        else {
            for (const slot of Object.keys(context)) {
                if (!entry.contextSlots.includes(slot))
                    extra.push(`${STATE_CONTEXT_KEY}.${slot}`);
            }
        }
    }
    if (missing.length === 0 && extra.length === 0)
        return;
    const problems = [];
    if (missing.length > 0)
        problems.push(`missing=${missing.join(",")}`);
    if (extra.length > 0)
        problems.push(`extra=${extra.join(",")}`);
    throw new Error(`dp ${dpId} state does not match the registry: ${problems.join("; ")}`);
}
/** One `## <heading>` section of a dispatch card body ("" when absent). */
function dispatchCardSection(text, heading) {
    const lines = text.split("\n");
    const start = lines.findIndex((line) => line.trim() === `## ${heading}`);
    if (start < 0)
        return "";
    const body = [];
    for (let index = start + 1; index < lines.length; index += 1) {
        const line = lines[index] ?? "";
        if (/^##\s/.test(line))
            break;
        body.push(line);
    }
    return body.join("\n").trim();
}
/** dp1 `context.task_excerpt`: the card's `## 上下文` + `## 要求` sections, or the
 * whole body when the card has neither heading. Byte-capped so it can never
 * push the state over the 2000 B budget. */
function dispatchTaskExcerpt(text, maxBytes) {
    if (!text)
        return "";
    const sections = [dispatchCardSection(text, "上下文"), dispatchCardSection(text, "要求")].filter((section) => section !== "");
    const source = (sections.length > 0 ? sections.join("\n\n") : text).trim();
    if (source === "")
        return "";
    return truncateUtf8Value(source, maxBytes);
}
/** Build the dp1 structured state from the dispatch plan (T-04d).
 *
 * Field set = `decision_points.REQUIRED_STATE_FIELDS["dp1-dispatch-type"]`
 * (universal 9 + `requested_type`/`task_summary`/`scope.write_scope`/
 * `scope.file_extensions`), plus `task_key`-free `key` and the registry
 * `questions_version`. Everything is validated + bounded by
 * {@link prepareStructuredState} (≤2000B, two-stage truncation); a refusal is
 * reported, never patched over — the caller then falls back to the legacy
 * string state. */
export function buildDp1DispatchState(plan) {
    const taskType = plan.taskType ?? "";
    const writeFace = plan.writeFace ?? [];
    const state = {
        // Same schema version the registry builder and the TS validator are pinned
        // to (`decision_points._state_builder`).
        schema_version: 2,
        decision_point: DP1_ID,
        key: (plan.key ?? "").trim(),
        phase: (plan.phase ?? "").trim(),
        task_type: taskType,
        // The dispatch never rewrites the requested type, so both fields carry the
        // plan's `type:` unless a caller says otherwise.
        requested_type: plan.requestedType ?? taskType,
        risk: dispatchRisk(taskType, plan.allowForeignWrite === true),
        risk_source: "pm-label",
        // dp1 is a P2 (reversible, local) decision point in the registry; the tier
        // is the action's authority class, not a config mirror (D-036).
        authority_tier: "P2",
        task_summary: dispatchTaskSummary(plan.description),
        questions_version: DP1_QUESTIONS_VERSION,
        scope: { write_scope: writeScopeDirs(writeFace), file_extensions: writeScopeExts(writeFace) },
    };
    if (!DP1_TYPE_CHOICES.includes(taskType)) {
        // A role outside the dp1 taxonomy (vision / rag-research / codex) cannot be
        // expressed in the required enum: report it as missing instead of guessing.
        return { ok: false, reason: "missing" };
    }
    const prepared = prepareStructuredState(DP1_ID, state);
    if (!prepared.ok) {
        return {
            ok: false,
            reason: prepared.reason === TRIAGE_REASON_INPUT_OVERSIZE ? "oversize" : "missing",
        };
    }
    // W6 (D-052): attach the engineered context AFTER the structured validator,
    // which only knows the decision fields; the excerpt is then sized against the
    // remaining 2000 B headroom so the whole state still fits the budget.
    const contextSlots = DECIDE_REGISTRY[DP1_ID]?.contextSlots ?? [];
    const dropped = [...prepared.dropped];
    let finalState = prepared.state;
    let bytes = prepared.bytes;
    if (contextSlots.includes("task_excerpt")) {
        const headroom = MAX_STRUCTURED_STATE_BYTES - prepared.bytes - STATE_CONTEXT_OVERHEAD;
        const excerpt = dispatchTaskExcerpt(plan.description, Math.min(DP1_TASK_EXCERPT_MAX, headroom));
        if (excerpt === "")
            dropped.push("context.task_excerpt");
        else {
            finalState = { ...prepared.state, context: { task_excerpt: excerpt } };
            bytes = canonicalStateBytes(finalState);
        }
    }
    assertStateMatchesRegistry(DP1_ID, finalState);
    return { ok: true, state: finalState, bytes, dropped };
}
/** Compute the bypass advice for one dispatch. Reads `.mw/decide.json`
 * (read-only) and asks the triage client for a suggestion; returns `null` on
 * the default-off path so nothing downstream changes. Never throws.
 *
 * T-04d: when `dp1` is supplied and the plan yields the complete registry
 * required set, the request carries a STRUCTURED state — the only shape the
 * CLI routes through `decision_points.decide_for`, which is what makes
 * `decision_id` / `mode` / `acted` reachable in production. An incomplete or
 * oversized set falls back to the frozen pre-T-04 legacy string state and the
 * fallback is recorded in {@link DispatchTriage.stateTrace} (never silent). */
export function computeDispatchTriage(input) {
    const policy = readDecidePolicy(input.projectDir);
    if (!policy.enabled || !policy.dp1Enabled)
        return null;
    let state = input.state;
    let statePath = "legacy";
    let fallbackReason = "missing";
    let structuredBytes = 0;
    if (input.dp1 !== undefined) {
        const built = buildDp1DispatchState(input.dp1);
        if (built.ok) {
            state = built.state;
            statePath = "structured";
            structuredBytes = built.bytes;
        }
        else {
            fallbackReason = built.reason;
        }
    }
    const stateTrace = statePath === "structured"
        ? `[DECISION] dp1 state=structured bytes=${structuredBytes}`
        : `[DECISION] dp1 state=legacy reason=${fallbackReason}`;
    const result = triageDispatch({ projectDir: input.projectDir, state, policy, run: input.run });
    return {
        result,
        alertOnDisagreement: policy.alertOnDisagreement,
        notifyOnUnavailable: policy.notifyOnUnavailable,
        dispatchedType: input.dispatchedType,
        disagreement: result.available && result.triage_type !== undefined && result.triage_type !== input.dispatchedType,
        receipt: formatTriageReceipt(result),
        decision: dispatchDecisionOf(result, input.dispatchedType),
        statePath,
        stateTrace,
    };
}
/** Durable + wake channel for one triage outcome (design D-005 item 3).
 * Best-effort: the ledger writer never throws; `deliverPmAlert` (one PM turn)
 * fires ONLY on a disagreement the config did not mute. Unavailable advice is
 * completely silent unless `triage_notify_on_unavailable=true`. */
export function emitDispatchTriage(pi, agenticdocRoot, triage) {
    if (!triage)
        return;
    if (triage.result.available) {
        const detail = formatTriageLedgerDetail(triage.result, triage.dispatchedType);
        recordDispatchAlarm(agenticdocRoot, { kind: "triage-suggestion", count: 1, detail });
        if (triage.disagreement && triage.alertOnDisagreement) {
            deliverPmAlert(pi, formatDispatchAlarm({ kind: "triage-suggestion", count: 1, detail }));
        }
        return;
    }
    if (triage.notifyOnUnavailable) {
        recordDispatchAlarm(agenticdocRoot, {
            kind: "triage-unavailable",
            count: 1,
            detail: `dp=dp1 reason=${triage.result.reason ?? "unknown"}`,
        });
    }
}
/** Append the triage receipt line to a dispatch receipt. Byte-identical when
 * there is no advice to show (default-off equivalence, T-03 requirement 5). */
export function appendTriageReceipt(text, triage) {
    const line = triage?.receipt ?? "";
    return line === "" ? text : `${text}\n${line}`;
}
/** The acted decision a triage result carries, or undefined.
 *
 * Design D-036 makes the child (`mw decide run --dp <id> --json`) the single
 * authority for `decision_id` / `mode` / `acted`; the triage result type only
 * declares the legacy fields today, so this reads the additive keys
 * structurally and stays undefined until the client forwards them. It never
 * infers `acted` from the mode or from `.mw/decide-points.json` (that mirror is
 * exactly what D-036 forbids), and a non-`acted` answer is dropped here. */
export function actedDecisionOf(triage) {
    const carried = triage?.result;
    if (typeof carried !== "object" || carried === null)
        return undefined;
    const record = carried;
    const decisionId = typeof record.decision_id === "string" ? record.decision_id.trim() : "";
    if (record.acted !== true || decisionId === "")
        return undefined;
    return { decisionId, acted: true };
}
/** Session entry type persisting this window's watched key across restarts. */
export const WATCH_ENTRY_TYPE = "agent-team-loop:watch";
// ── Window claim identity (_index.parallel claimId) ─────────────────────────
/** This window's claim identity: host:pid. Written into _index.parallel so
 * another window can tell whether a key's claim is still held by a live
 * process (pid check) before taking it over. */
export function windowClaimId() {
    return `${os.hostname()}:${process.pid}`;
}
/** Parse a `host:pid` claim; anything else (e.g. legacy timestamp claims) is
 * unparseable and treated as stale. */
function parseClaim(claimId) {
    const m = claimId.match(/^([^:]+):(\d+)$/);
    if (!m)
        return undefined;
    const pid = Number(m[2]);
    if (!Number.isInteger(pid) || pid <= 0)
        return undefined;
    return { host: m[1] ?? "", pid };
}
function isPidAlive(pid) {
    try {
        process.kill(pid, 0);
        return true;
    }
    catch (err) {
        // EPERM: process exists but is not ours — still alive. ESRCH: gone.
        return err.code === "EPERM";
    }
}
/** Who holds a key's `_index.parallel` claim — deliberately a HOLDER verdict,
 * not a takeover verdict (the two differ for exactly one holder):
 *  - "held-live": another live window (or a foreign host whose liveness we
 *    cannot verify) holds it. A takeover needs `--force`.
 *  - "held-conductor": THIS host's autopilot conductor holds it through its
 *    synthetic claim `autopilot@<host>:<pid>` (T-16). The conductor yields to
 *    a human takeover on its next tick, so `takeOverKey` succeeds WITHOUT
 *    `--force` (T-16b requirement 1).
 *  - "held-stale": the holder is gone; "free": nobody (or this window).
 *
 * The synthetic branch is decided by index-store's shared parser
 * (`parseSyntheticClaim` + `syntheticClaimLive`), never by a prefix test
 * repeated here: the TS takeover guard and the Python conductor can then only
 * drift through that one predicate (T-16b requirement 4). */
export function claimState(claimId, self) {
    const trimmed = claimId.trim();
    if (!trimmed || trimmed === self)
        return "free";
    // Local conductor-owned claim (T-16). A synthetic claim from ANOTHER host is
    // a different machine's conductor: it must not be stolen without --force, so
    // it falls through to the ordinary foreign-host rule below (parseClaim reads
    // "autopilot@host" as a host name and returns "held-live").
    const synthetic = parseSyntheticClaim(trimmed);
    if (synthetic !== undefined && synthetic.host === os.hostname()) {
        return syntheticClaimLive(trimmed) ? "held-conductor" : "held-stale";
    }
    const c = parseClaim(trimmed);
    if (!c)
        return "free"; // legacy/unparseable claim — stale
    if (c.host !== os.hostname())
        return "held-live"; // cannot verify liveness
    return isPidAlive(c.pid) ? "held-live" : "held-stale";
}
/** Is the key held by someone OTHER than this window — a live human window
 * ("held-live") or this host's conductor ("held-conductor")? Both keep the
 * namespace foreign for the cross-key read/write guard (AC-024) and for
 * owner-key resolution: the conductor is YIELDABLE, but only through the
 * explicit `takeOverKey` path — never by a silent write into its key. */
function claimHeldByAnotherWriter(state) {
    return state === "held-live" || state === "held-conductor";
}
/** Machine-readable refusal code for a cross-key write (AC-024). */
export const CROSS_KEY_READ_ONLY = "cross-key-read-only";
/** Writer surfaces the cross-key guard actually fences, in refusal-text order.
 * Single declaration source (AC-003/VC-011): the refusal body below is built
 * from this array, and the coverage test asserts every entry maps to a real
 * guard call site — the text can never again claim a surface the code does not
 * guard (the pre-AC-003 gap: it named `/worker` while only dispatch_worker and
 * advance_phase called the guard). */
export const CROSS_KEY_READ_ONLY_SURFACES = ["dispatch_worker", "/worker", "advance_phase"];
/** Row-ack addendum of the refusal text: `ack_worker_result` filters rows by
 * ownership instead of calling the guard, so it is named in the text but is
 * deliberately NOT part of {@link CROSS_KEY_READ_ONLY_SURFACES} (which is the
 * call-site set VC-011 compares against). */
export const CROSS_KEY_READ_ONLY_ACK_NOTE = "acking its rows";
/** Cross-key write guard (AC-024): a key whose `_index.parallel` row is held
 * live by ANOTHER window is READ-ONLY for this window. Reading it stays global
 * and unrestricted (`list_tasks` scope "all"/"key", `mw_status`, `mw doctor`,
 * the watch panel); the WRITER surfaces refuse with the stable
 * {@link CROSS_KEY_READ_ONLY} code instead of silently touching another
 * window's namespace. Writable: this window's own claim, an unclaimed key
 * (new-key bootstrap: write spec.md -> advance -> dispatch), and `_scratch`.
 * Returns null when the write is allowed. */
export function foreignLiveClaimRefusal(indexStore, key) {
    const trimmed = key.trim();
    if (!trimmed || isScratchKey(trimmed))
        return null;
    // Explicit name gate (A5): reserved framework names and illegal shapes are
    // refused unconditionally. The pre-AC-006 `_`/`.` prefix exemption returned
    // null BEFORE findByKey, so a live `_tmp` key passed and reserved files could
    // be used as key namespaces — there is no such bypass left.
    const nameRefusal = keyNameRefusal(trimmed);
    if (nameRefusal)
        return reservedKeyRefusal(trimmed, nameRefusal);
    const claim = indexStore.findByKey(trimmed)?.claimId.trim() ?? "";
    if (!claim)
        return null;
    const state = claimState(claim, windowClaimId());
    if (!claimHeldByAnotherWriter(state))
        return null;
    // The holder is named exactly: a human window needs --force to be displaced
    // from, while the conductor yields to a plain (non-forced) takeover. The
    // refusal code is the same for both, so callers/tests keep one contract.
    const holder = state === "held-conductor"
        ? `by this host's autopilot conductor (synthetic claim ${claim})`
        : `live by another window (claim ${claim})`;
    const escapeHint = state === "held-conductor"
        ? `switch_key { key: "${trimmed}" } (no force needed — the conductor yields to a human claim)`
        : `switch_key { key: "${trimmed}" } (ask the user before stealing a live claim)`;
    return (`[${CROSS_KEY_READ_ONLY}] key '${trimmed}' is held ${holder} — ` +
        "this window's view of it is read-only.\n" +
        `Allowed: list_tasks { scope: "all" } or { scope: "key", key: "${trimmed}" }, mw_status, mw doctor, the watch panel.\n` +
        `Refused: ${CROSS_KEY_READ_ONLY_SURFACES.join(", ")}, ${CROSS_KEY_READ_ONLY_ACK_NOTE}.\n` +
        `To act on it, take it over first: ${escapeHint}`);
}
/** Refusal text for a key NAME that fails the shape/reserved gate (AC-006):
 * there is no owner to negotiate with — the name itself is unusable, so the
 * cross-key escape hatch (switch_key) does not apply. */
function reservedKeyRefusal(key, refusal) {
    return (`[${CROSS_KEY_READ_ONLY}] key '${key}' is refused (${refusal.code}): ${refusal.message}.\n` +
        `Allowed: names matching ^[A-Za-z0-9][A-Za-z0-9._-]*$ that are not reserved framework names (${RESERVED_INDEX_NAMES.join(", ")}).\n` +
        `Refused: ${CROSS_KEY_READ_ONLY_SURFACES.join(", ")}, ${CROSS_KEY_READ_ONLY_ACK_NOTE}.`);
}
/** Claim a key for this window — shared by /pm-key switch, /pm-key new and
 * the spec-write auto-takeover. Routes through IndexStore.claim so the
 * liveness check, demote, and write are one atomic step under the index
 * lock: racing windows cannot both believe they claimed. Also runs the
 * phase-chain audit on success (audit_phase.py's TS-side mirror). */
export async function takeOverKey(indexStore, key, force, agenticdocRoot) {
    const self = windowClaimId();
    const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", { force });
    const audit = outcome.ok ? phaseAuditWarnings(agenticdocRoot, key, outcome.entry.phase) : [];
    // Case-variant audit (design-role-key-identity §5.1 / DD-07d): the claim hit a
    // stored row spelled differently only by case, so the window now owns
    // `<stored>` while the user typed `<key>`. Surface it on the existing audit
    // channel (every takeOverKey caller already notifies `result.audit`) instead
    // of letting the substitution stay invisible.
    if (outcome.caseVariantOf) {
        audit.push(`[KEY] case-variant '${key}' -> stored '${outcome.caseVariantOf}'`);
    }
    // Mirror the claim into {key}/pm-state.md's '- Claim-Id:' line (D-108):
    // every path that flips the index row's Claim column must also sync the
    // mirror, or the two sources diverge. Failure is non-fatal by design.
    const claimSync = outcome.ok ? syncPmStateClaimId(agenticdocRoot, key, self) : undefined;
    return {
        ok: outcome.ok,
        blockedBy: outcome.blockedBy,
        refusal: outcome.refusal,
        claimId: self,
        created: outcome.created,
        audit,
        claimSync,
    };
}
/** One-line warning for a claim whose pm-state.md mirror sync failed
 * (D-108): the claim itself succeeded — the index row is authoritative — so
 * this only makes the divergence visible to the user/agent. "" when the
 * sync succeeded or never ran (nothing to warn about). */
export function claimSyncWarningText(key, sync) {
    if (sync?.ok !== false)
        return "";
    return `WARNING: claim succeeded but ${key}/pm-state.md was not synced (${sync.reason}). The index row is authoritative.`;
}
const WATCH_WIDGET_KEY = "agent-team-loop-watch";
/** History rows kept in the widget (D-003): done rows and acked terminal
 * rows are processed history — newest five shown, the rest folded into
 * `+N more`. Live (running/pending) and unhandled (failed/nc awaiting ack)
 * rows are never folded. */
const WATCH_HISTORY_MAX = 5;
const WATCH_LINE_MAX = 110;
const STATUS_GLYPH = {
    pending: ".",
    running: ">",
    done: "+",
    failed: "x",
    "needs-clarification": "?",
    // Product says the run started but its process is gone and the outcome is
    // unknown (D-022/T-20) — loud on purpose: a `lost` row needs a human look.
    lost: "!",
};
function trunc(s, max) {
    return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}
/** Owner key of a queue row: the first taskPath segment below the agenticdoc
 * root ({key}/workers/<task>/task.md → key). Legacy root-level rows resolve to
 * their own task key and simply never match a watched key. */
export function ownerKeyOf(entry, agenticdocRoot) {
    const rel = path.relative(agenticdocRoot, path.normalize(entry.taskPath));
    return rel.split(path.sep)[0] ?? "";
}
/** Does THIS window own the queue row (mw-task-scope-isolation)? True when the
 * row sits under the watched key, or when this process dispatched the task
 * (explicit cross-key dispatch, or the global-active fallback — see
 * resolveOwnerKeyWithSync). Fail-closed: with no watch key and no dispatch
 * record the row belongs to another window. Shared by list_tasks and both ack
 * entry points, so what the tools act on matches what the bottom watch widget
 * shows (it scopes by ownerKeyOf alone). */
export function ownedByThisWindow(entry, watch, agenticdocRoot) {
    return ownerKeyOf(entry, agenticdocRoot) === watch.key || watch.dispatchedTaskKeys?.has(entry.taskKey) === true;
}
/** Body of a `## <section>` block in output.md (first match), trimmed;
 * undefined when the file or section is missing. Generic reader behind
 * readOutputSummary and the terminal-detail fallback chains (D-004): `##
 * TL;DR`, `## Exit Reason`, `## Questions`. The section literal is regex-escaped
 * so a future caller-side string with metacharacters can never inject. */
export function readOutputSection(taskDir, section) {
    let content;
    try {
        content = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
    }
    catch {
        return undefined;
    }
    const m = content.match(new RegExp(`## ${section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\n+([\\s\\S]*?)(?=\\n## |$)`));
    return m ? m[1].trim() : undefined;
}
/** `## Summary` body — the legacy detail source, now the done-row fallback
 * when no `## TL;DR` exists (old output.md files, AC-009). */
export function readOutputSummary(taskDir) {
    return readOutputSection(taskDir, "Summary");
}
/** Cap for terminal readback bodies (AC-014). */
export const OUTPUT_READBACK_MAX = 20_000;
/** Full output.md body for terminal readback (AC-014): worker results are
 * delivered into the watching window's conversation so the PM processes
 * them without manual file reads. Over-cap reports are truncated with a
 * pointer to the file. */
export function readOutputBody(taskDir) {
    const outputPath = path.join(taskDir, "output.md");
    let content;
    try {
        content = fs.readFileSync(outputPath, "utf8").trim();
    }
    catch {
        return undefined;
    }
    if (!content)
        return undefined;
    if (content.length <= OUTPUT_READBACK_MAX)
        return content;
    return `${content.slice(0, OUTPUT_READBACK_MAX)}\n\n…(truncated — full report: ${outputPath})`;
}
/** Last `[launcher] spawn failed …` line from worker.log, if any. Spawn-failure
 * logs are tiny (the CLI never ran — the launcher writes exactly this line and
 * nothing else); a large log means the worker actually ran, so ignore it. */
export function readSpawnFailure(taskDir) {
    const logPath = path.join(taskDir, "worker.log");
    try {
        const stat = fs.statSync(logPath);
        if (stat.size > 64 * 1024)
            return undefined;
        const lines = fs.readFileSync(logPath, "utf8").split("\n");
        for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i].trim();
            if (line.startsWith("[launcher] spawn failed"))
                return line;
        }
        return undefined;
    }
    catch {
        return undefined;
    }
}
/** worker.log read guard for the needs-clarification fallback: larger logs
 * mean the worker actually ran (D-004) — skip the read entirely. */
const WORKER_LOG_TAIL_MAX = 256 * 1024;
/** Last non-empty worker.log line, or undefined. The needs-clarification
 * fallback for tasks that never wrote an output.md (claude/codex workers,
 * old bundles) — their last logged line names what they were asking about. */
export function readWorkerLogTail(taskDir) {
    try {
        const stat = fs.statSync(path.join(taskDir, "worker.log"));
        if (stat.size > WORKER_LOG_TAIL_MAX)
            return undefined;
        const lines = fs.readFileSync(path.join(taskDir, "worker.log"), "utf8").split("\n");
        for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i].trim();
            if (line !== "")
                return line;
        }
        return undefined;
    }
    catch {
        return undefined;
    }
}
/** First non-empty line of a section body, trimmed, leading markdown
 * markers stripped so terminal details never start with `#`/`**`/`- `/`> `
 * (AC-007). Mirrors HEADLINE_MARKER_RE in worker/output-writer. */
const DETAIL_MARKER_RE = /^(?:#{1,6}\s+|\*\*|[-*]\s+|>\s+)/;
function firstLine(body) {
    let line = body?.split("\n")[0]?.trim() ?? "";
    while (DETAIL_MARKER_RE.test(line)) {
        line = line.replace(DETAIL_MARKER_RE, "").trim();
    }
    return line === "" ? undefined : line;
}
/** Widget detail line for a terminal worker row (D-004): the glyph/status
 * says what happened, this says why it stuck or what it concluded.
 *  - failed: spawn-failure reason (launcher prefix stripped, timestamp-free)
 *    ?? `## Exit Reason` first line
 *  - needs-clarification: `## Questions` first line ?? worker.log tail ??
 *    explicit no-output hint (claude/codex tasks write no output.md at all)
 *  - lost (D-022/T-20): the run's process is gone with no verified outcome —
 *    same evidence ladder as a failure (Exit Reason, then the log tail), so the
 *    PM reads the scene instead of a synthesized conclusion
 *  - done: `## TL;DR` first line ?? `## Summary` first line (old output.md
 *    files). AC-010: the LAST non-placeholder TL;DR/Summary block, not the
 *    first — append-only multi-run files lead with crash placeholders.
 * Returns "" when nothing informative exists (caller renders the key only).
 * Line-width truncation stays with the caller (WATCH_LINE_MAX). */
export function readTerminalDetail(taskDir, status) {
    if (status === "failed") {
        const spawn = readSpawnFailure(taskDir);
        if (spawn !== undefined) {
            const reason = spawn.match(/^\[launcher\] spawn failed \([^)]*\):\s*(.*)$/);
            return (reason?.[1] ?? spawn).trim();
        }
        return firstLine(readLastProductSectionBody(taskDir, ["Exit Reason"])) ?? "";
    }
    if (status === "needs-clarification") {
        return (firstLine(readLastProductSectionBody(taskDir, ["Questions"])) ?? readWorkerLogTail(taskDir) ?? "no output.md");
    }
    if (status === "lost") {
        return (firstLine(readLastProductSectionBody(taskDir, ["Exit Reason"])) ??
            readWorkerLogTail(taskDir) ??
            "run lost: process gone, outcome unverified — inspect the task dir");
    }
    if (status === "done") {
        // AC-010: last non-placeholder block, same placeholder oracle as
        // hasDeliverableEvidence (contract C5) — a first-match here would show the
        // leading crash stub of an append-only multi-run output.md.
        return firstLine(readLastProductSectionBody(taskDir, ["TL;DR", "Summary"])) ?? "";
    }
    return "";
}
/** Terminal worker statuses (queue semantics; mirrors pm-orchestrator's
 * isTerminal — shared by the ack validation path). `lost` is terminal for the
 * ledger (the run is over) while still being unhandled until acked: it must be
 * absorbed, never re-run (D-022). */
function isTerminalStatus(status) {
    return status === "done" || status === "failed" || status === "needs-clarification" || status === "lost";
}
/** Statuses that stay in the widget's unhandled section until the PM acks them
 * (D-002/D-022): everything terminal except a clean `done`. */
function isUnhandledStatus(status) {
    return status === "failed" || status === "needs-clarification" || status === "lost";
}
/** Shared ack validation + write path behind /mw ack and the ack_worker_result
 * tool (D-002). `"all"` expands to every terminal row not yet acked;
 * individual keys must reference an existing terminal row — running/pending
 * rows are rejected and nothing is written for them (AC-004).
 *
 * `scope` (mw-task-scope-isolation) narrows the write path to this window: the
 * ack sidecar is a PROJECT-level file, so without it any window could ack (and
 * silently clear) another window's unhandled rows. When given, `"all"` only
 * covers rows this window owns and an explicit foreign key is rejected with the
 * owning key. Omitted = unscoped (callers that are not a PM window). */
export async function ackTasks(workerStore, ackStore, targets, scope) {
    const entries = workerStore.readAll();
    const owns = (e) => scope === undefined || ownedByThisWindow(e, scope.watch, scope.agenticdocRoot);
    if (targets === "all") {
        const alreadyAcked = new Set(ackStore.readAll().keys());
        const keys = entries
            .filter((e) => owns(e) && isTerminalStatus(e.status) && !alreadyAcked.has(e.taskKey))
            .map((e) => e.taskKey);
        if (keys.length === 0)
            return { acked: [], rejected: [] };
        return { acked: (await ackStore.ack(keys)).acked, rejected: [] };
    }
    const byKey = new Map(entries.map((e) => [e.taskKey, e]));
    const acked = [];
    const rejected = [];
    for (const key of targets) {
        const entry = byKey.get(key);
        if (entry === undefined) {
            rejected.push({ key, reason: "no such task in the worker queue" });
        }
        else if (!isTerminalStatus(entry.status)) {
            rejected.push({
                key,
                reason: `not terminal (status: ${entry.status}) — only done/failed/needs-clarification/lost rows can be acked`,
            });
        }
        else if (!owns(entry)) {
            const owner = scope === undefined ? "?" : ownerKeyOf(entry, scope.agenticdocRoot);
            const mine = scope?.watch.key ?? "(none)";
            rejected.push({
                key,
                reason: `owned by key '${owner}' — this window owns '${mine}'; ` +
                    `run /pm-key switch ${owner} to align, or ack it from the window that dispatched it`,
            });
        }
        else {
            acked.push(key);
        }
    }
    const written = acked.length > 0 ? await ackStore.ack(acked) : { acked: [], rejected: [] };
    return { acked: written.acked, rejected };
}
/** Live bottom-widget lines for the watched key, in three sections (D-003):
 *  1. live — running then pending, all shown, never folded
 *  2. unhandled — failed/needs-clarification rows the PM has not acked
 *     (/mw ack), all shown, never folded; header carries the count
 *  3. history — done rows ∪ acked terminal rows, newest-first, capped at
 *     WATCH_HISTORY_MAX with a `+N more` fold line
 * Terminal-row details come from readTerminalDetail (D-004).
 * `extraTaskKeys` (mw-worker-visibility-gate D-105) optionally names tasks
 * THIS window dispatched that landed under a different key: they render as
 * ONE aggregate tail line (`  ~ N elsewhere: …`, D-106) instead of rows, so
 * cross-key work stays visible without drowning the panel. Omitted or empty
 * keeps the output identical to the pre-aggregate panel (AC-007). */
export function renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key, extraTaskKeys) {
    const counts = {
        pending: 0,
        running: 0,
        done: 0,
        failed: 0,
        "needs-clarification": 0,
        lost: 0,
    };
    const acked = new Set(ackStore.readAll().keys());
    // One queue read shared by the own-key rows and the cross-key aggregate —
    // the aggregate must not add a second full readAll() (§9).
    const all = workerStore.readAll();
    const owned = all.filter((e) => ownerKeyOf(e, agenticdocRoot) === key);
    const aggregate = elsewhereAggregateLine(all, extraTaskKeys, key, agenticdocRoot);
    for (const e of owned)
        counts[e.status]++;
    // Unhandled = terminal-but-not-done rows not yet acked — the PM's explicit
    // to-do list; ack moves a row out of this section into history.
    const unhandled = owned.filter((e) => isUnhandledStatus(e.status) && !acked.has(e.taskKey));
    const idx = indexStore.findByKey(key);
    const phase = idx
        ? `phase=${idx.phase}`
        : key === SCRATCH_WORKERS_KEY
            ? "manual tasks"
            : "key not in _index.parallel";
    const badge = key === SCRATCH_WORKERS_KEY ? undefined : formatDocsBadge(readPhaseDocs(agenticdocRoot, key));
    const parts = [];
    if (counts.running > 0)
        parts.push(`${counts.running} running`);
    if (counts.pending > 0)
        parts.push(`${counts.pending} pending`);
    if (counts.done > 0)
        parts.push(`${counts.done} done`);
    if (counts.failed > 0)
        parts.push(`${counts.failed} failed`);
    if (counts["needs-clarification"] > 0)
        parts.push(`${counts["needs-clarification"]} needs-clarification`);
    if (counts.lost > 0)
        parts.push(`${counts.lost} lost`);
    if (unhandled.length > 0)
        parts.push(`${unhandled.length} unhandled`);
    const header = `[mw] ${key} | ${phase}${badge ? ` | docs ${badge}` : ""} | ${parts.length > 0 ? parts.join(" / ") : "no workers"}`;
    if (owned.length === 0) {
        return aggregate === undefined ? [header, "  (no worker tasks)"] : [header, "  (no worker tasks)", aggregate];
    }
    // One rendered row per entry; detail per status (live heartbeat vs D-04
    // terminal sources). Width truncation is uniform (WATCH_LINE_MAX).
    // D-116: every row carries the worker's model in a [id] badge — running
    // and terminal rows read the pi-resolved id from trace.log [START]
    // (launcher defaults included); pending rows fall back to the dispatch-time
    // override from the queue row (no trace.log yet).
    const rowLine = (e) => {
        let detail = "";
        let model = "";
        if (e.status === "running") {
            // Heartbeat-derived live progress (design D-008): phase counter + age
            // of the last [HEARTBEAT] line, refreshed on every poll tick. Old
            // bundles without heartbeats get a visible (no-hb) placeholder.
            // [START] adds elapsed runtime ("up 6m") and the last [TOOL] line
            // names what the worker is currently doing.
            const prog = readTaskProgress(path.dirname(e.taskPath));
            model = prog?.model ?? "";
            const hb = prog?.heartbeat;
            if (hb) {
                const ph = hb.phase === "-" ? "ph -" : `ph ${hb.phase}/${hb.phaseTotal}`;
                const up = prog?.elapsedMs !== undefined ? ` up ${formatHeartbeatAge(prog.elapsedMs)}` : "";
                const stale = hb.ageMs > HEARTBEAT_STALE_MS ? " STALE" : "";
                detail = `${ph}${up} hb ${formatHeartbeatAge(hb.ageMs)}${stale}`;
            }
            else {
                detail = "(no-hb)";
            }
            // Convergence checkpoint badge (AC-005): past the checkpoint time the
            // running line carries the machine risk verdict — the PM's divergence
            // radar at a glance. Non-low risks get a warning glyph.
            const ck = prog?.checkpoint;
            if (ck) {
                detail += ` ck${Math.round(ck.elapsedS / 60)}m${ck.risk !== "low" ? ` ${ck.risk}⚠` : ""}`;
            }
            if (prog?.lastAction)
                detail += ` · ${prog.lastAction}`;
        }
        else if (e.status === "pending") {
            // Dispatch-time --model override; the effective id lands in trace.log
            // [START] once the worker spawns.
            model = e.model;
        }
        else {
            // Terminal detail per status (D-004): spawn reason / Exit Reason /
            // Questions / TL;DR with their fallback chains.
            model = readTaskProgress(path.dirname(e.taskPath))?.model ?? "";
            detail = readTerminalDetail(path.dirname(e.taskPath), e.status);
        }
        const badge = model ? ` [${model}]` : "";
        return trunc(`  ${STATUS_GLYPH[e.status]} ${e.taskKey}${badge}${detail ? ` — ${detail}` : ""}`, WATCH_LINE_MAX);
    };
    const newestFirst = (a, b) => (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
    const live = [
        ...owned.filter((e) => e.status === "running").sort(newestFirst),
        ...owned.filter((e) => e.status === "pending").sort(newestFirst),
    ];
    const history = owned.filter((e) => e.status === "done" || acked.has(e.taskKey)).sort(newestFirst);
    const lines = [header];
    for (const e of live)
        lines.push(rowLine(e));
    for (const e of [...unhandled].sort(newestFirst))
        lines.push(rowLine(e));
    for (const e of history.slice(0, WATCH_HISTORY_MAX))
        lines.push(rowLine(e));
    if (history.length > WATCH_HISTORY_MAX)
        lines.push(`  ... +${history.length - WATCH_HISTORY_MAX} more`);
    // The cross-key aggregate is a never-folded tail line (D-106): it rides
    // after the history fold, never inside it.
    if (aggregate !== undefined)
        lines.push(aggregate);
    return lines;
}
/** Status order inside one owner group of the aggregate line (D-106): the
 * fixed sequence running/pending/done/failed/needs-clarification, only
 * non-zero entries rendered. */
const AGGREGATE_STATUS_ORDER = [
    "running",
    "pending",
    "done",
    "failed",
    "needs-clarification",
    "lost",
];
/** The single cross-key aggregate line for the watch panel (D-105/D-106):
 * `  ~ <N> elsewhere: <owner>(<c1> running, <c2> failed, …; risk=high:<K>)`.
 *
 * `extraTaskKeys` are the task keys THIS window dispatched; rows among them
 * owned by a DIFFERENT key than the watched one are summarized here instead
 * of rendered as rows (cross-key rows must not be misread as the watched
 * key's own output). Returns undefined when `extraTaskKeys` is omitted or
 * holds no cross-key row — the caller then keeps the pre-aggregate output
 * line for line (AC-007/VC-007).
 *
 * Shape (D-106): one line; owner groups joined with ", " sorted by (row
 * count desc, owner name asc); per group only non-zero statuses in the fixed
 * order; `; risk=high:<K>` appended when K >= 1 of the group's running rows
 * carries a high convergence checkpoint (same readTaskProgress source as the
 * own-key rows). Over-long lines are truncated to WATCH_LINE_MAX like every
 * other panel line. Reuses the caller's single workerStore.readAll() result
 * — no second queue read (§9). */
function elsewhereAggregateLine(all, extraTaskKeys, watchKey, agenticdocRoot) {
    if (extraTaskKeys === undefined)
        return undefined;
    const elsewhere = all.filter((e) => extraTaskKeys.has(e.taskKey) === true && ownerKeyOf(e, agenticdocRoot) !== watchKey);
    if (elsewhere.length === 0)
        return undefined;
    const groups = new Map();
    for (const e of elsewhere) {
        const owner = ownerKeyOf(e, agenticdocRoot);
        const group = groups.get(owner);
        if (group === undefined)
            groups.set(owner, [e]);
        else
            group.push(e);
    }
    const owners = [...groups.keys()].sort((a, b) => {
        const byRows = (groups.get(b)?.length ?? 0) - (groups.get(a)?.length ?? 0);
        return byRows !== 0 ? byRows : a < b ? -1 : a > b ? 1 : 0;
    });
    const parts = [];
    for (const owner of owners) {
        const group = groups.get(owner) ?? [];
        const counts = {
            pending: 0,
            running: 0,
            done: 0,
            failed: 0,
            "needs-clarification": 0,
            lost: 0,
        };
        for (const e of group)
            counts[e.status]++;
        const countText = AGGREGATE_STATUS_ORDER.filter((s) => counts[s] > 0)
            .map((s) => `${counts[s]} ${s}`)
            .join(", ");
        let highRisk = 0;
        for (const e of group) {
            if (e.status === "running" && readTaskProgress(path.dirname(e.taskPath))?.checkpoint?.risk === "high") {
                highRisk++;
            }
        }
        parts.push(`${owner}(${countText}${highRisk > 0 ? `; risk=high:${highRisk}` : ""})`);
    }
    return trunc(`  ~ ${elsewhere.length} elsewhere: ${parts.join(", ")}`, WATCH_LINE_MAX);
}
/** Render (or clear) the bottom watch widget on a UI-capable context. */
export function setWatchWidget(ctx, lines) {
    if (!ctx.hasUI)
        return;
    // order 10 keeps the watch panel BELOW the autopilot monitor (order 0) in the
    // same belowEditor placement, independent of which poller refreshed last.
    ctx.ui.setWidget(WATCH_WIDGET_KEY, lines, { placement: "belowEditor", order: 10 });
}
/** Render (or clear) the widget via the session_start-captured context.
 * No-op before session start or in headless runs. */
export function applyWatchWidget(ui, lines) {
    if (!ui.ctx)
        return;
    setWatchWidget(ui.ctx, lines);
}
/** Set this window's watched key, persist it in the session file (survives
 * restart/resume), and refresh the bottom widget immediately. `claimed` marks
 * watches that came with a key takeover. */
function setWindowWatch(pi, watch, refresh, ctx, key, claimed) {
    watch.key = key;
    pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed });
    refresh(ctx);
}
/** Doc-gate notifier scoped to this window's watched key (AC-011): the scan
 * evaluates gates for every undocumented key (blocking stays global), but a
 * gate event is only BROADCAST here when it is this window's own key — other
 * keys' gates belong to their owning windows. A window watching nothing
 * stays silent. */
export function makeScopedDocGateNotifier(pi, watch) {
    return (key, gaps) => {
        if (!watch.key || key !== watch.key)
            return false;
        displaySummary(pi, `[mw] skipped dispatch for '${key}' — missing phase docs: ${gaps.join("; ")}. ` +
            "Generate spec/design + evidence/research notes (agentic-task workflows), or move ad-hoc work under _scratch.");
        return true;
    };
}
export function registerPmKeyCommands(pi, indexStore, watch, refreshWatch, agenticdocRoot) {
    pi.registerCommand("pm-key", {
        description: "Manage PM keys: new / switch (take over + watch) / list",
        handler: async (args, ctx) => {
            const [sub, ...rest] = args.trim().split(/\s+/);
            const flags = rest.filter((t) => t.startsWith("--"));
            const positional = rest.filter((t) => !t.startsWith("--"));
            const keyName = positional[0] ?? "";
            const force = flags.includes("--force");
            if (sub === "list") {
                const entries = indexStore.readAll();
                if (entries.length === 0) {
                    ctx.ui.notify("No keys found.", "info");
                    return;
                }
                const table = entries.map((e) => `${e.key} | ${e.status} | ${e.phase} | ${e.claimId}`).join("\n");
                ctx.ui.notify(table, "info");
                return;
            }
            if (sub === "new") {
                if (!keyName) {
                    ctx.ui.notify("Usage: /pm-key new <key-name>", "warning");
                    return;
                }
                if (indexStore.findByKey(keyName)) {
                    ctx.ui.notify(`Key '${keyName}' already exists — use /pm-key switch ${keyName} to take it over.`, "warning");
                    return;
                }
                // Name gate (AC-006): a reserved/illegal name must never be registered,
                // so it is refused here (before the claim) with a readable code.
                const newNameRefusal = keyNameRefusal(keyName);
                if (newNameRefusal) {
                    ctx.ui.notify(`Key '${keyName}' is refused (${newNameRefusal.code}): ${newNameRefusal.message}.`, "warning");
                    return;
                }
                // Route through the atomic claim: auto-create + demote other active
                // rows (single-active discipline) in one locked step.
                const result = await takeOverKey(indexStore, keyName, false, agenticdocRoot);
                // Executing a key in this window also watches it (bottom progress widget).
                setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
                ctx.ui.notify(`Created and claimed key: ${keyName} (${result.claimId})`, "info");
                if (result.audit.length > 0)
                    ctx.ui.notify(result.audit.join("\n"), "warning");
                // pm-state.md mirror sync failure is visible but non-fatal (D-108):
                // the claim itself succeeded; the index row stays authoritative.
                const createdSyncWarning = claimSyncWarningText(keyName, result.claimSync);
                if (createdSyncWarning !== "")
                    ctx.ui.notify(createdSyncWarning, "warning");
                return;
            }
            if (sub === "switch") {
                if (!keyName) {
                    ctx.ui.notify("Usage: /pm-key switch <key-name> [--force]", "warning");
                    return;
                }
                const target = indexStore.findByKey(keyName);
                if (!target) {
                    ctx.ui.notify(`Key not found: ${keyName}`, "error");
                    return;
                }
                const result = await takeOverKey(indexStore, keyName, force, agenticdocRoot);
                if (!result.ok) {
                    if (result.refusal) {
                        ctx.ui.notify(`Key '${keyName}' is refused (${result.refusal}): reserved framework names and illegal key shapes cannot be claimed.`, "warning");
                        return;
                    }
                    ctx.ui.notify(`Key '${keyName}' is claimed by another live window (${result.blockedBy}). Use /pm-key switch ${keyName} --force to take it over.`, "warning");
                    return;
                }
                // Switching keys in this window also switches what it watches.
                setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
                ctx.ui.notify(`Took over key: ${keyName} (claim ${result.claimId})`, "info");
                if (result.audit.length > 0)
                    ctx.ui.notify(result.audit.join("\n"), "warning");
                const switchSyncWarning = claimSyncWarningText(keyName, result.claimSync);
                if (switchSyncWarning !== "")
                    ctx.ui.notify(switchSyncWarning, "warning");
                return;
            }
            ctx.ui.notify("Usage: /pm-key new|switch|list [key-name] [--force]", "warning");
        },
    });
}
/** Insert a session-snapshot section at the top of {key}/pm-state.md's Notes
 * area. Machine-interface lines (- Phase: / - Claim-Id:) are owned by the
 * framework scripts and stay byte-identical: the snapshot is inserted under
 * "## Notes" only, never rewriting the rest of the file (pm-state-guard
 * principle, framework-side write with the same lock protocol as
 * StateManager). Returns the path written. */
export async function writeSessionSnapshot(agenticdocRoot, key, lines) {
    const statePath = path.join(agenticdocRoot, key, "pm-state.md");
    const content = fs.existsSync(statePath) ? fs.readFileSync(statePath, "utf8") : `# PM State: ${key}\n\n## Notes\n`;
    const section = [
        `### Session Snapshot — ${new Date().toISOString()} (${windowClaimId()})`,
        ...lines.map((l) => (l ? `- ${l}` : "")),
        "",
    ].join("\n");
    const NOTES_HEADING = /^## Notes[ \t]*$/m;
    const next = NOTES_HEADING.test(content)
        ? content.replace(NOTES_HEADING, `## Notes\n\n${section}`)
        : `${content.trimEnd()}\n\n## Notes\n\n${section}`;
    fs.mkdirSync(path.dirname(statePath), { recursive: true });
    const release = await acquireLock(`${statePath}.lock`);
    try {
        const tmpPath = `${statePath}.tmp`;
        fs.writeFileSync(tmpPath, next, "utf8");
        fs.renameSync(tmpPath, statePath);
    }
    finally {
        release();
    }
    return statePath;
}
/** /pm-save — persist this window's working context into the watched key's
 * pm-state.md so a restarted pi window (e.g. after a framework rebuild) can
 * pick the work back up. The handler writes the mechanical snapshot (watch
 * key, index row, worker counts, free note) itself; the conversational
 * context (what we are doing, decisions, next steps) can only be summarized
 * by the agent, so the handler asks it to — the user invoked the command, so
 * this is a user-requested action, not a framework-injected nudge. */
export function registerPmSaveCommand(pi, indexStore, workerStore, watch, agenticdocRoot) {
    pi.registerCommand("pm-save", {
        description: "Save this window's working context to {watched key}/pm-state.md for restart pickup",
        handler: async (args, ctx) => {
            const note = args.trim();
            if (!watch.key) {
                ctx.ui.notify("Not watching any key — /pm-key switch <key> (take over) or /mw-watch <key> (display only) first.", "warning");
                return;
            }
            const key = watch.key;
            const row = indexStore.findByKey(key);
            const owned = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot) === key);
            const ORDER = ["pending", "running", "done", "failed", "needs-clarification", "lost"];
            const counts = new Map();
            for (const e of owned)
                counts.set(e.status, (counts.get(e.status) ?? 0) + 1);
            const workerSummary = owned.length === 0
                ? "no workers"
                : ORDER.filter((s) => counts.get(s))
                    .map((s) => `${counts.get(s)} ${s}`)
                    .join(" / ");
            const lines = [
                `Watch: ${key} (window ${windowClaimId()})`,
                row
                    ? `Index: status=${row.status} phase=${row.phase}${row.desc ? ` — ${row.desc}` : ""}`
                    : "Index: (not in _index.parallel)",
                `Workers: ${workerSummary}`,
            ];
            if (note)
                lines.push(`Note: ${note}`);
            lines.push("(agent: fill in below — 当前工作脉络 / 关键决策 / 进行中 / 下一步)");
            const statePath = await writeSessionSnapshot(agenticdocRoot, key, lines);
            ctx.ui.notify(`Saved session snapshot to ${path.relative(agenticdocRoot, statePath)} — asking the agent to fill in the working context.`, "info");
            pi.sendUserMessage(`[agent-team-loop] /pm-save：已在 ${key}/pm-state.md 的 Notes 区写入会话快照。请立即把当前对话的上下文状态补全到该快照小节：当前工作脉络、关键决策、进行中的事项、下一步动作。只编辑 ${key}/pm-state.md 的 Notes 区，不要动 - Phase: / - Claim-Id: 机器接口行。写完简短确认。`);
        },
    });
}
/** /mw-watch — toggle this window's bottom progress widget for one key.
 * Display-only observation: no claim is taken. Use /pm-key switch to take
 * over a key while developing it.
 *
 * Usage: /mw-watch <key>   watch a key (widget appears below the editor)
 *        /mw-watch off     stop watching (widget cleared)
 *        /mw-watch         show current watch state
 */
export function registerWatchCommand(pi, watch, refreshWatch, indexStore) {
    const USAGE = "Usage: /mw-watch <key> | off   (display only — /pm-key switch takes over a key)";
    pi.registerCommand("mw-watch", {
        description: "Show one key's live worker progress in a bottom widget (/mw-watch <key> | off)",
        handler: async (args, ctx) => {
            const arg = args.trim();
            if (!arg) {
                ctx.ui.notify(watch.key ? `Watching: ${watch.key}. ${USAGE}` : `Not watching anything. ${USAGE}`, "info");
                return;
            }
            if (arg === "off" || arg === "none") {
                watch.key = undefined;
                pi.appendEntry(WATCH_ENTRY_TYPE, { key: undefined, claimed: false });
                refreshWatch(ctx);
                ctx.ui.notify("Watch disabled — bottom widget cleared.", "info");
                return;
            }
            if (arg !== SCRATCH_WORKERS_KEY && !indexStore.findByKey(arg)) {
                ctx.ui.notify(`Key '${arg}' not found in _index.parallel (or use ${SCRATCH_WORKERS_KEY}). ${USAGE}`, "warning");
                return;
            }
            setWindowWatch(pi, watch, refreshWatch, ctx, arg, false);
            ctx.ui.notify(`Watching '${arg}' — worker progress shown below the editor.`, "info");
        },
    });
}
export function registerMwTools(pi, projectDir) {
    pi.registerTool({
        name: "mw_status",
        label: "mw_status",
        description: "Check whether the multi-worker background service (mw serve) is running. Returns PID if running, or 'not running' if stopped.",
        parameters: Type.Object({}),
        execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
            const s = getMwStatus(projectDir);
            return {
                content: [
                    {
                        type: "text",
                        text: s.running
                            ? `mw is running (PID ${s.pid}). Workers are being dispatched and monitored.`
                            : "mw is not running. Workers will not be dispatched. Use /mw start or ask the user to start it.",
                    },
                ],
                details: undefined,
            };
        },
    });
}
/** Resolve the task type for one dispatch: an explicit value must be one of
 * DISPATCHABLE_TYPES, an omitted one keeps the legacy cli-derived mapping
 * (pi -> coding, claude -> review, codex -> codex) so pre-existing dispatches
 * stay byte-identical. */
export function resolveDispatchType(cli, requested) {
    const trimmed = requested.trim();
    if (!trimmed) {
        const legacy = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
        return { ok: true, type: legacy };
    }
    if (!DISPATCHABLE_TYPES.includes(trimmed)) {
        return {
            ok: false,
            message: `Invalid type '${trimmed}'. Must be one of: ${DISPATCHABLE_TYPES.join(", ")}.`,
        };
    }
    return { ok: true, type: trimmed };
}
/** Collapse a model-override reason to the single line a task.md frontmatter
 * entry can hold (design D-003). */
function oneLineReason(raw) {
    return raw.replace(/\s*\r?\n\s*/g, " ").trim();
}
/** Current phase of the owner key from its pm-state.md `- Phase:` line, or
 * "" when the owner is `_scratch` / the key has no readable phase. The phase
 * axis (`required = role.require OR phase.require`, T-14) must never be
 * guessed, so an unknown phase writes no `phase:` header at all. pm-state.md is
 * owned by advance_phase.py — read-only here. */
function dispatchPhase(agenticdocRoot, ownerKey) {
    if (ownerKey === SCRATCH_WORKERS_KEY)
        return "";
    return new StateManager(agenticdocRoot, ownerKey).read().phase ?? "";
}
/** Build the task.md frontmatter (type / phase / images / model / model-reason)
 * for one dispatch and the echo line that tells the PM which layer supplies the model
 * (design D-001~D-007). Shared by the dispatch_worker tool and /worker so the
 * two entries can never drift.
 *
 * Refusals (no task file must be written): an unknown model id for a pi route
 * (validateModelValue), and an override of a configured dispatch.yml role
 * default without a reason. */
export function planDispatchFrontmatter(input) {
    const role = roleForTaskType(input.taskType);
    const configured = readRoleModel(input.cwd, role) ?? "";
    const requested = input.model.trim();
    const reason = oneLineReason(input.modelReason);
    // Image requirement (T-06, three-state, verbatim precedence): an explicit
    // `images: "no"` short-circuits to "no image" WITHOUT calling the filesystem
    // detector (the exemption is unconditional and must stay cheap); an explicit
    // `images: "yes"` forces the requirement; otherwise the description is
    // scanned for a reference to an existing image file.
    const imagesRequested = input.images === "no"
        ? false
        : input.images === "yes"
            ? true
            : detectImageNeed(input.cwd, input.description ?? "");
    // Write side (D-013): a detected need writes `images: yes` too, so the
    // worker's runtime fallback covers auto-detected tasks.
    const imagesField = input.images === "no" ? "no" : imagesRequested ? "yes" : undefined;
    const headLines = [`type: ${input.taskType}`];
    if (input.phase !== undefined && input.phase.length > 0)
        headLines.push(`phase: ${input.phase}`);
    if (imagesField !== undefined)
        headLines.push(`images: ${imagesField}`);
    const typeLines = `${headLines.join("\n")}\n`;
    // The value that will actually run: an explicit request wins, else the
    // configured role default (which the launcher would pick next). Either way
    // it must name a model the pi route can resolve.
    let effective = requested || configured;
    if (effective) {
        const validation = validateModelValue(input.registry, input.cli, input.provider, effective);
        if (!validation.ok)
            return { ok: false, message: validation.message };
    }
    // Auto-route (T-07, AC-016/AC-017): an un-pinned task that needs images while
    // its role default is a definite "no" moves to the `vision` role's model when
    // that model is a definite "yes". ONLY the model value moves — `type:` (and
    // with it the worker tool allowlist) is deliberately left untouched (D-004).
    // An explicit `model:` is never rewritten (it walks the capability gate
    // below), and a missing / non-"yes" `vision` value leaves `effective` on the
    // role default so the gate still owns the refusal. Runs BEFORE the gate:
    // otherwise the gate would refuse before routing could take effect.
    let autoRouteSource = "";
    if (!requested && imagesRequested) {
        const roleCapability = modelImageCapability(input.registry, input.cli, input.provider, effective);
        if (roleCapability === "no") {
            const visionValue = readRoleModel(input.cwd, "vision") ?? "";
            if (visionValue && modelImageCapability(input.registry, input.cli, input.provider, visionValue) === "yes") {
                effective = visionValue;
                autoRouteSource = role;
            }
        }
    }
    // Capability gate (T-06, AC-006/AC-008): only a definite "no" refuses, and
    // only when the task really needs images. "unknown" fails open by design —
    // never turn an undecidable registry lookup into a refused dispatch.
    if (imagesRequested) {
        const capability = modelImageCapability(input.registry, input.cli, input.provider, effective);
        if (capability === "no") {
            return {
                ok: false,
                message: `Task declares images (or references an image file) but model '${effective}' cannot take image input. ` +
                    "Use 'mw model set vision <provider/model>' to configure a vision role, or declare 'images: no' if the task does not need the image.",
            };
        }
    }
    // DP-1 advisory triage (T-03/D-006): computed inside this shared plan point —
    // before any dispatch fs write — and attached to the result. It NEVER mutates
    // the frontmatter/echo below: the default-off path returns null and changes
    // nothing, and the suggestion never rewrites type/role/model/cli.
    // T-04d: the request carries a structured state whenever the plan yields the
    // registry's full dp1 required set (the only shape whose CLI response carries
    // `decision_id`/`mode`/`acted`); otherwise the frozen legacy string state is
    // used and the fallback is traced.
    const triage = computeDispatchTriage({
        projectDir: input.cwd,
        state: buildTriageState({
            description: input.description ?? "",
            taskType: input.taskType,
            cli: input.cli,
            phase: input.phase,
        }),
        dispatchedType: input.taskType,
        run: input.triageRun,
        dp1: {
            key: input.dp1?.key,
            phase: input.phase,
            taskType: input.taskType,
            requestedType: input.taskType,
            description: input.description,
            writeFace: input.dp1?.writeFace,
            allowForeignWrite: input.dp1?.allowForeignWrite,
        },
    });
    // Auto-route result: the vision model is pinned (the role default cannot take
    // image input) and the machine-readable source rides both the task
    // frontmatter (`model-reason`) and the echo (`model-source`). `type:` stays
    // untouched. Checked before the no-override branch below, which would
    // otherwise emit a frontmatter without the routed `model:` line.
    if (autoRouteSource) {
        const routeReason = reason
            ? `${reason}; auto-route: ${autoRouteSource} -> vision`
            : `auto-route: ${autoRouteSource} -> vision`;
        const routeLines = [...headLines, `model: ${effective}`, `model-reason: ${routeReason}`];
        return {
            ok: true,
            frontmatter: `${routeLines.join("\n")}\n`,
            echo: `model: dispatch.yml vision=${effective} (model-source: auto-route, ${autoRouteSource} -> vision)`,
            triage,
        };
    }
    if (!requested) {
        return {
            ok: true,
            frontmatter: typeLines,
            echo: configured
                ? `model: dispatch.yml ${role}=${configured}`
                : `model: route default (no dispatch.yml ${role} default)`,
            triage,
        };
    }
    // Requested value equals the configured default: leave the line out so the
    // config stays the single source of truth (a later config change applies).
    if (configured && requested === configured) {
        return {
            ok: true,
            frontmatter: typeLines,
            echo: `model: dispatch.yml ${role}=${configured} (requested value matches the configured default; not pinned)`,
            triage,
        };
    }
    if (configured && !reason) {
        return {
            ok: false,
            message: `Model override for role '${role}' needs model_reason: dispatch.yml ${role}=${configured}, requested=${requested}. ` +
                "Omit the model to use the configured default, or re-dispatch with model_reason explaining the deviation.",
        };
    }
    const lines = [...headLines];
    if (requested)
        lines.push(`model: ${requested}`);
    if (reason)
        lines.push(`model-reason: ${reason}`);
    return {
        ok: true,
        frontmatter: `${lines.join("\n")}\n`,
        echo: configured
            ? `model override: role default ${role}=${configured} -> ${requested} (reason: ${reason})`
            : `model: ${requested} (no dispatch.yml ${role} default)`,
        triage,
    };
}
// ── AC-005a: dispatch-time write-surface satisfiability (T-02) ──────────────
/** Paired markers of the dispatch-injected write-surface contract (contract
 * C2, producer T-02 → consumer T-03). The runtime consumer only greps for
 * these markers; the three lines between them are for the worker and PM. */
export const WRITE_SURFACE_MARKER = "<!-- mw-write-surface: v1 -->";
export const WRITE_SURFACE_MARKER_END = "<!-- /mw-write-surface: v1 -->";
/** Machine-readable refusal code for an unsatisfiable write requirement. */
export const WORKER_WRITE_SURFACE = "worker-write-surface";
/** Write verbs a task book can use to order a file write (AC-005a). Exported so
 * the rule is enumerable by the unit matrix and by the corpus replay.
 * `写到文件` before `写到` so the longest form wins. */
export const WRITE_INTENT_VERBS = [
    "写到文件",
    "写到",
    "写入",
    "落盘",
    "输出到",
    "保存",
    "创建",
    "生成",
    "追加",
    "覆盖",
    "write",
    "save",
    "create",
    "append",
    "output to",
    "into",
];
/** Allow-guards (AC-005a), stable names for the test matrix. A hit matching
 * any guard is a legitimate mention, never an unsatisfiable write order. */
export const WRITE_INTENT_GUARDS = [
    "negation",
    "read-marker",
    "fenced-code",
    "quotation",
    "pm-attribution",
];
/** Upper bound (chars) between a write verb and its path. The matcher is
 * deliberately stricter: only whitespace and at most one quote may separate
 * the two, which is what keeps prose like "追加而非重写 achieved.md" out while
 * still satisfying the ≤32 bound. */
export const WRITE_INTENT_PATH_WINDOW = 32;
/** Framework-owned basenames: naming one means "the framework already provides
 * this channel" (reply text lands in output.md), not an external write order. */
const FRAMEWORK_TASK_BASENAMES = ["task.md", "trace.log", "output.md", "run.json", "worker.log"];
const WRITE_INTENT_NEGATIONS = [
    "不要",
    "不得",
    "禁止",
    "勿",
    "无需",
    "不准",
    "do not",
    "don't",
    "never",
    "must not",
];
const WRITE_INTENT_READ_MARKERS = [
    "读取",
    "作为输入",
    "参考",
    "输入",
    "引用",
    "依据",
    "来源",
    "现有",
    "已有",
    "核对",
    "扫描",
    "以…为输入",
    "read",
    "rg",
    "grep",
    "current",
    "existing",
    "input",
    "from",
];
const WRITE_INTENT_PM_ATTRIBUTIONS = ["pm 会", "由 pm", "pm 收录", "框架会", "交给 pm", "pm 将在"];
const WRITE_INTENT_QUOTE_PAIRS = [
    ['"', '"'],
    ["'", "'"],
    ["「", "」"],
];
const WRITE_INTENT_ENGLISH_VERBS = new Set(["write", "save", "create", "append", "output to", "into"]);
/** Anchored token after a write verb (A3 fix, AC-004): a wide character class
 * with NO extension enumeration — the shape judge below decides whether a
 * candidate is a path. New languages/config types cannot re-open the leak. */
const WRITE_INTENT_TOKEN_RE = /^[A-Za-z0-9_.\\/~:-]+/;
const WRITE_SURFACE_SECTION_RE = new RegExp(`${WRITE_SURFACE_MARKER.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[\\s\\S]*?${WRITE_SURFACE_MARKER_END.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\n*`, "g");
/** Find `verb` in `clause`; English verbs match on word boundaries so
 * `output-writer.ts` never reads as a `write` order. */
function findWriteIntentVerb(clause, verb) {
    const low = clause.toLowerCase();
    const needle = verb.toLowerCase();
    if (WRITE_INTENT_ENGLISH_VERBS.has(needle)) {
        const re = new RegExp(`(?<![A-Za-z0-9_])${needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![A-Za-z0-9_])`);
        const m = re.exec(low);
        return m ? m.index : -1;
    }
    return low.indexOf(needle);
}
/** Is `pathToken` inside a quotation span (guard ④)? */
function pathInsideQuotation(clause, pathToken) {
    const at = clause.indexOf(pathToken);
    if (at === -1)
        return false;
    for (const [open, close] of WRITE_INTENT_QUOTE_PAIRS) {
        let start = clause.indexOf(open);
        while (start !== -1 && start < at) {
            const end = clause.indexOf(close, start + 1);
            if (end === -1)
                break;
            if (at > start && at + pathToken.length <= end)
                return true;
            start = clause.indexOf(open, start + 1);
        }
    }
    return false;
}
/** Write-intent hits that survive the five allow-guards (AC-005a). Pure over
 * text so the corpus replay and the unit cases share one implementation.
 *
 * HTML comments are stripped structurally (AC-010 / C-29) before any verb or
 * token matching: the framework's own injected markers
 * (`<!-- mw-write-surface: v1 -->` / `<!-- /mw-write-surface: v1 -->`) contain
 * the English verb `write`, whose anchored token scan would otherwise read
 * `-surface:` as a colon-shaped target and refuse the producer's honest
 * artifact. Stripping the whole comment span (inline and multi-line) removes
 * every comment-borne mention — never a marker-name special case. */
export function collectWriteIntentHits(text) {
    const body = text.replace(/<!--[\s\S]*?-->/g, "").replace(/```[\s\S]*?```/g, "");
    const hits = [];
    for (const line of body.split(/\r?\n/)) {
        for (const clause of line.split(/[。；！？;]/)) {
            const low = clause.toLowerCase();
            for (const verb of WRITE_INTENT_VERBS) {
                const pos = findWriteIntentVerb(clause, verb);
                if (pos < 0)
                    continue;
                const after = clause.slice(pos + verb.length);
                const gap = /^\s*[`"']?\s*/.exec(after);
                const gapLen = gap ? gap[0].length : 0;
                if (gapLen > WRITE_INTENT_PATH_WINDOW)
                    continue;
                // Anchored token discovery (A3 fix, AC-004): no extension enumeration and
                // no `pm.index !== 0` discard branch. A non-matching token means only
                // that this verb has no candidate in this clause — never that the whole
                // clause is abandoned, and never a forward scan into later prose.
                const pm = WRITE_INTENT_TOKEN_RE.exec(after.slice(gapLen));
                if (pm === null)
                    continue;
                const pathToken = pm[0].replace(/[.]+$/, "");
                if (pathToken === "")
                    continue;
                const before = low.slice(Math.max(0, pos - 20), pos);
                if (WRITE_INTENT_NEGATIONS.some((n) => before.includes(n)))
                    continue;
                if (WRITE_INTENT_READ_MARKERS.some((r) => low.includes(r)))
                    continue;
                if (WRITE_INTENT_PM_ATTRIBUTIONS.some((a) => low.includes(a)))
                    continue;
                if (pathInsideQuotation(clause, pathToken))
                    continue;
                hits.push({ verb, path: pathToken, clause: clause.trim() });
                break;
            }
        }
    }
    return hits;
}
/** Verdict of the target axis delegated to the shared write-surface predicate
 * (`shared/write-surface.ts::judgeWriteTarget`, design §3; AC-016). This
 * adapter only adds the two PM-only channels the predicate does not own: the
 * framework basenames (`task.md`/`trace.log`/`output.md`/`run.json`/
 * `worker.log`, which the framework itself writes) and the `WriteTargetJudge`
 * shape/rule vocabulary. Evaluation order matches the historical one:
 *   1. deny prefixes + own task dir + own-key `<key>/evidence/**` + worker_file
 *      basenames + path-shape refusal — all from the shared predicate
 *   2. framework basenames — PM prose channel only
 *   3. non-candidate prose => pass untouched
 * The `!hasDirComponent` precondition (not `shape === "bare"`) is load-bearing:
 * `output.md`/`report.md` are `ext`-shaped and must still use the channel. */
export function judgeWriteTarget(pathToken, ctx) {
    const shape = classifyWriteTargetShape(pathToken, ctx);
    const verdict = judgeSharedWriteTarget(pathToken, ctx);
    if (verdict.allowed)
        return { allowed: true, shape };
    if (verdict.rule === "deny")
        return { allowed: false, shape, rule: "deny", detail: verdict.detail };
    const hasDirComponent = /[\\/]/.test(pathToken);
    if (!hasDirComponent && (WORKER_FILE_NAME_RE.test(pathToken) || FRAMEWORK_TASK_BASENAMES.includes(pathToken))) {
        return { allowed: true, shape };
    }
    return { allowed: false, shape, rule: "scope", detail: verdict.detail ?? "outside-write-surface" };
}
/** Boolean wrapper of {@link judgeWriteTarget} (AC-003/AC-004): may this role
 * legitimately write `pathToken`? */
export function isWhitelistedWriteTarget(pathToken, ctx) {
    return judgeWriteTarget(pathToken, ctx).allowed;
}
/** Judgement entry point: only a writeless role without a shell is judged — a
 * write role passes untouched, a shell role (`research`) is handled by the
 * AC-005b runtime guard instead. `allowForeignWrite` is the escape hatch. */
export function judgeWriteIntent(input) {
    if (!isWritelessRole(input.type) || isShellRole(input.type))
        return { ok: true, hits: [], violations: [] };
    const hits = collectWriteIntentHits(input.description);
    const ctx = {
        taskDir: input.taskDir,
        projectRoot: input.projectRoot,
        keyDir: input.keyDir,
        trueRoot: input.trueRoot,
    };
    const violations = input.allowForeignWrite ? [] : hits.filter((hit) => !isWhitelistedWriteTarget(hit.path, ctx));
    return { ok: violations.length === 0, hits, violations };
}
/** Refusal text for an unsatisfiable write order (AC-005a): names the code, the
 * role, the path, and the three ways forward. */
export function writeIntentRefusal(input) {
    return (`[${WORKER_WRITE_SURFACE}] task '${input.taskKey}' has type '${input.type}', which has no write/edit/bash tool, ` +
        `but its task book requires writing to '${input.path}' — unsatisfiable for this role.\n` +
        "Fix (pick one):\n" +
        '1. Put the deliverable in the task\'s own dir: worker_file file="report.md" (progress.md / report-<slug>.md also work); the PM collects it afterwards.\n' +
        "2. Re-dispatch with allow_foreign_write: true — recorded in task.md frontmatter (allow_foreign_write: true) for audit; use it only when a human accepted the external path.\n" +
        "3. Use a role with write tools: type: coding | repair | vision.");
}
/** Default `write_scope:` line for a shell role (contract C1): the task's own
 * dir plus the key's evidence tree. Absent for non-shell roles. */
export function renderDefaultWriteScope(ownerKey, taskKey) {
    return `write_scope: .agenticdoc/${ownerKey}/workers/${taskKey}, .agenticdoc/${ownerKey}/evidence`;
}
/** The injected 3-line contract section (contract C2), marker-paired. */
export function renderWriteSurfaceContract(type, writeScope) {
    const scope = (writeScope ?? "").trim().replace(/^write_scope:\s*/, "");
    const allowed = scope
        ? `本任务目录下的 worker_file（progress.md | report.md | report-<slug>.md）；write_scope: ${scope}`
        : "本任务目录下的 worker_file（progress.md | report.md | report-<slug>.md）";
    const denied = "本任务目录之外的任何路径（pm-state.md、workers/_workers*、_index.parallel、其他 key、packages/**、.git/**）";
    const consequence = isShellRole(type)
        ? "运行期 bash 写面守卫 block + [TOOL_ERR] + trace 审计行"
        : "运行期写面守卫拒绝；回复文本仍会被框架写入 output.md";
    return [
        WRITE_SURFACE_MARKER,
        `- 允许写：${allowed}`,
        `- 不得写：${denied}`,
        `- 越界后果：${consequence}`,
        WRITE_SURFACE_MARKER_END,
    ].join("\n");
}
/** Idempotent contract-section application (contract C2, VC-019): any existing
 * marker region is removed, then the canonical section is inserted right after
 * the leading frontmatter block. Applying it twice is a byte-level fixed point
 * and leaves exactly one marker pair. */
export function applyWriteSurfaceContract(taskMdText, type, writeScope) {
    const section = renderWriteSurfaceContract(type, writeScope);
    const cleaned = taskMdText.replace(WRITE_SURFACE_SECTION_RE, "");
    const blank = cleaned.search(/\n\s*\n/);
    if (blank === -1)
        return `${section}\n\n${cleaned}`;
    const head = cleaned.slice(0, blank).replace(/\n+$/, "");
    const rest = cleaned.slice(blank).replace(/^\n+/, "");
    return `${head}\n\n${section}\n\n${rest}`;
}
/** Merge the claims-derived `read_scope:` head block (T-02, design §4). Same
 * carrier as the Python renderer (`dispatch.py::render_task_md`): a YAML block
 * list of scope entries, then the two scalar caps, in that fixed order. `
 * `readScope` absent/empty writes NOTHING at all: `read_scope:` is what turns
 * the worker's read interceptor on (`worker/read-scope.ts`), so a card without
 * a claims block must keep both its bytes and its interception behaviour
 * (AC-007). A cap is rendered only when it is a positive number, so a partially
 * derived pair still yields the exact field order. */
function mergeReadScope(frontmatter, readScope, fileCap, byteCap) {
    const items = (readScope ?? []).map((item) => item.trim()).filter((item) => item !== "");
    if (items.length === 0)
        return frontmatter;
    const lines = ["read_scope:", ...items.map((item) => `  - ${item}`)];
    if (fileCap !== undefined && Number.isFinite(fileCap) && fileCap > 0) {
        lines.push(`l2_read_file_cap: ${Math.trunc(fileCap)}`);
    }
    if (byteCap !== undefined && Number.isFinite(byteCap) && byteCap > 0) {
        lines.push(`l2_read_byte_cap: ${Math.trunc(byteCap)}`);
    }
    return `${frontmatter.replace(/\r?\n$/, "")}\n${lines.join("\n")}\n`;
}
/** Merge the audit-visible escape-hatch line (AC-005a) into frontmatter. */
function mergeAllowForeignWrite(frontmatter, allowed) {
    if (!allowed || /^allow_foreign_write:/m.test(frontmatter))
        return frontmatter;
    return `${frontmatter.replace(/\r?\n$/, "")}\nallow_foreign_write: true\n`;
}
/** Append a rendered `write_scope:` line to planned frontmatter (contract
 * C1/C4). Same shape as the existing `read_scope:`/`deny_globs:` headers — one
 * line, never an empty value: undefined/blank scope leaves the frontmatter
 * bytes untouched. */
function mergeWriteScope(frontmatter, writeScope) {
    const line = (writeScope ?? "").trim();
    if (!line)
        return frontmatter;
    return `${frontmatter.replace(/\r?\n$/, "")}\n${line}\n`;
}
/** `<dp>:<trigger_id>` — dp ids are kebab-case registry ids, trigger ids are
 * task keys / `task_key#ckpt<N>` / ISO stamps (design D-023: the trigger may
 * contain `:`, the split is on the FIRST one). Anchored so a free-text value
 * can never be written into the machine-readable header. */
const DECISION_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]*:\S+$/;
/** Merge the `decision:` correlation line into the frontmatter at the END of
 * the merge chain (last head line before the body). `acted`-gated by contract:
 * `suggest` advice, a missing decision and a malformed `decision_id` all leave
 * the frontmatter bytes untouched (a broken correlation key is never written;
 * settle then treats the task as un-associated instead of guessing). */
export function mergeDecisionHeader(frontmatter, decision) {
    if (!decision?.acted)
        return frontmatter;
    const decisionId = decision.decisionId.trim();
    if (!DECISION_ID_RE.test(decisionId))
        return frontmatter;
    if (/^decision:/m.test(frontmatter))
        return frontmatter;
    return `${frontmatter.replace(/\r?\n$/, "")}\ndecision: ${decisionId}\n`;
}
// ── Dispatch-card envelope injection (T-02, contract C3) ────────────────────
/** Machine-readable refusal code for a missing/incomplete dispatch card. */
export const DISPATCH_CARD_CODE = "dispatch-card";
/** Machine-readable refusal code for a card whose claims block cannot be used
 * (T-02, design §3.2). Deliberately NOT `dispatch-card`: `card_audit` and the
 * PM read the code to tell an incomplete envelope apart from a declared-but-
 * unusable claims table. */
export const DISPATCH_CLAIMS_CODE = "dispatch-claims";
/**
 * Runtime claims-gate mode (T-02 requirement 4, D-006): `MW_CLAIM_GATE`
 * overrides {@link CLAIM_GATE_DEFAULT}. The name and the two values are the
 * same on both sides of the TS/Python pair (`dispatch.py::claim_gate`), so a
 * grey release flips one env var. An unknown/blank value falls back to the
 * default instead of blocking a dispatch: the gate is opt-in, and a typo must
 * neither silently enforce nor stall the loop (same fail-open rule as the
 * Python side).
 */
export function claimGateMode() {
    const raw = (process.env.MW_CLAIM_GATE ?? CLAIM_GATE_DEFAULT).trim().toLowerCase();
    return raw === "enforce" ? "enforce" : CLAIM_GATE_DEFAULT;
}
/** The `read_scope:` entries of one claims-backed dispatch (T-02, design §4):
 * the owner key's own tree, the project goal anchor (the pair the key's
 * conductor dispatches already carry), and — the part a claim-driven review
 * cannot do without — the files the claims point at. A locator names the file
 * the claim is about (optionally with a `:line` / `:a-b` span suffix), so the
 * scope is exactly "the claims plus their anchors": the worker reads what it
 * must falsify and nothing else, which is the whole point of pricing a review
 * by claims instead of by repo size. Absolute paths and `..` escapes are
 * dropped, so a card cannot widen its own scope out of the project root.
 * Rendered only when the card declares claims, because `read_scope:` switches
 * the worker's read interceptor on. */
export function claimReadScope(ownerKey, claims) {
    const scope = [`.agenticdoc/${ownerKey}`, ".agenticdoc/goal.md"];
    const seen = new Set(scope.map((entry) => entry.toLowerCase()));
    for (const claim of claims) {
        const entry = claim.locator
            .trim()
            .replace(/:\d+(?:-\d+)?$/, "")
            // D-005 writes a `cmd` locator as `evidence/claims/<file>#<claim-id>`; the
            // fragment names the row inside the file, not a path of its own.
            .replace(/#.*$/, "")
            .replaceAll("\\", "/")
            .replace(/^\.\//, "");
        if (entry === "" || path.isAbsolute(entry) || entry.split("/").includes(".."))
            continue;
        if (seen.has(entry.toLowerCase()))
            continue;
        seen.add(entry.toLowerCase());
        scope.push(entry);
    }
    return scope;
}
/** Markers of the card's claims block (design §2.1); the injected copy keeps
 * them verbatim so the settle path can re-parse `task.md` without the card
 * (D-002). */
const CLAIMS_OPEN_RE = /^<!--\s*mw-claims\s*:\s*v1\s*-->$/i;
const CLAIMS_CLOSE_RE = /^<!--\s*\/\s*mw-claims\s*-->$/i;
const CLAIMS_STOP_H2_RE = /^##(?!#)\s+/;
const CLAIMS_FENCE_RE = /^(`{3,}|~{3,})(.*)$/;
const CLAIMS_BLOCK_CLOSE = "<!-- /mw-claims -->";
/**
 * LF-normalized lines of `text` plus the `[start, end)` line range of the card's
 * `<!-- mw-claims: v1 -->` block; `start = -1` when the card has none. The
 * range follows the shared parser's fence/H2 semantics: an unterminated block
 * ends at the next H2 or EOF (`end` is exclusive either way).
 */
function claimsBlockRange(text) {
    const lines = text.replace(/\r\n?/g, "\n").split("\n");
    let fence;
    let start = -1;
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i] ?? "";
        const fenceMatch = CLAIMS_FENCE_RE.exec(line);
        if (fenceMatch !== null) {
            const marker = fenceMatch[1] ?? "";
            const rest = fenceMatch[2] ?? "";
            const char = marker[0] ?? "";
            if (fence === undefined)
                fence = { char, len: marker.length };
            else if (char === fence.char && marker.length >= fence.len && rest.trim() === "")
                fence = undefined;
            continue;
        }
        if (fence !== undefined)
            continue;
        if (start < 0) {
            if (CLAIMS_OPEN_RE.test(line))
                start = i;
            continue;
        }
        if (CLAIMS_CLOSE_RE.test(line))
            return { lines, start, end: i + 1 };
        if (CLAIMS_STOP_H2_RE.test(line))
            return { lines, start, end: i };
    }
    return { lines, start, end: start < 0 ? -1 : lines.length };
}
/**
 * Verbatim text of the card's `<!-- mw-claims: v1 -->` block (T-02 requirement
 * 2), `""` when the card has none.
 *
 * The card seed only injects heading slices, so an HTML comment block would
 * never reach `task.md` reliably (RQ-2 §2.3) — and the settle layer must read
 * the claims from `task.md`, never from the (mutable) card file (D-002). The
 * slice is taken between the markers with the same fence/H2 semantics as the
 * shared parser; an unterminated block gets the close marker appended, so the
 * injected copy cannot swallow the seed disclaimer or the task body after it.
 */
export function extractClaimsBlockText(text) {
    const { lines, start, end } = claimsBlockRange(text);
    if (start < 0)
        return "";
    const block = lines.slice(start, end);
    if (block.length === 0 || !CLAIMS_CLOSE_RE.test(block[block.length - 1] ?? ""))
        block.push(CLAIMS_BLOCK_CLOSE);
    return block.join("\n");
}
/** Card text with the claims block removed (T-02): the block is delivered once,
 * by {@link renderCardSeedSections}, so it must not also ride inside a §1.2
 * extra body (a card that puts it under an H2 would otherwise emit the rows
 * twice and the settle parser would see duplicated claims). */
function stripClaimsBlockText(text) {
    const { lines, start, end } = claimsBlockRange(text);
    if (start < 0)
        return text;
    return [...lines.slice(0, start), ...lines.slice(end)].join("\n");
}
/** Paired markers around the card-derived body section (idempotent injection,
 * same "strip old region → reinsert" mechanism as the write-surface contract). */
export const CARD_SEED_MARKER = "<!-- mw-dispatch-card: v1 -->";
export const CARD_SEED_MARKER_END = "<!-- /mw-dispatch-card: v1 -->";
/** The mandatory seed disclaimer demanded by design §2.2: the injected card is
 * a seed, never an upper bound on what the worker may read. */
export const CARD_SEED_DISCLAIMER = "以上为种子，不是探索上界；可自行检索补充上下文";
const CARD_HEADING_RE = /^(#{2,6})\s+(.*)$/;
/** Strip a leading `1.` / `1.2.` / `(2)` / `A.` / `一、` numbering prefix
 * (same rule as `shared/dispatch-card.ts::stripNumbering`). */
function stripCardHeadingNumbering(text) {
    let out = text.trim();
    out = out.replace(/^[（(]\s*[0-9A-Za-z一二三四五六七八九十]+\s*[)）]\s*/, "");
    out = out.replace(/^[0-9]+(?:\.[0-9]+)*\s*[.、)）]\s*/, "");
    out = out.replace(/^[A-Za-z]\s*[.、)）]\s*/, "");
    out = out.replace(/^[一二三四五六七八九十]+\s*[、.)）]\s*/, "");
    return out.trim();
}
/** First heading family a card heading belongs to (same vocabulary/order as
 * T-01's `classifyHeading`, so extraction can never disagree with the gate). */
function classifyCardHeading(heading) {
    const lower = heading.toLowerCase();
    for (const [section, tokens] of ENVELOPE_HEADING_FAMILIES) {
        for (const token of tokens) {
            if (lower.startsWith(token.toLowerCase()))
                return section;
        }
    }
    return undefined;
}
/**
 * Extract the three envelope bodies from a card (T-02, contract C3).
 *
 * Heading-based slicing mirrors T-01's judgement: the first heading of a family
 * with a non-empty body wins, body runs to the next heading of the same or
 * higher level. A section T-01 accepted only through the wide semantic fallback
 * (headingless card) has no slice to take, so the whole post-prologue card body
 * is used as its content — the seed is delivered rather than dropped. This
 * never re-judges the envelope; `readEnvelope` already owns the verdict.
 */
export function extractCardSections(cardText) {
    const raw = cardText.replace(/\r\n?|[\u2028\u2029]/g, "\n").split("\n");
    const lines = raw.map((line) => line.trim());
    const headings = [];
    for (let i = 0; i < lines.length; i++) {
        const match = CARD_HEADING_RE.exec(lines[i] ?? "");
        if (match)
            headings.push({ level: match[1]?.length ?? 2, text: stripCardHeadingNumbering(match[2] ?? ""), line: i });
    }
    const out = { context: "", requirements: "", deliverables: "", extras: [] };
    /** Body of heading `index` (to the next same-or-higher heading). */
    const bodyOf = (index) => {
        const heading = headings[index];
        if (heading === undefined)
            return "";
        let end = lines.length;
        for (let j = index + 1; j < headings.length; j++) {
            const next = headings[j];
            if (next !== undefined && next.level <= heading.level) {
                end = next.line;
                break;
            }
        }
        return raw
            .slice(heading.line + 1, end)
            .join("\n")
            .trim();
    };
    const used = new Set();
    for (let i = 0; i < headings.length; i++) {
        const heading = headings[i];
        if (heading === undefined)
            continue;
        const section = classifyCardHeading(heading.text);
        if (section === undefined || out[section] !== "")
            continue;
        const body = bodyOf(i);
        if (body !== "") {
            out[section] = body;
            used.add(i);
        }
    }
    // T-12/F-02: every remaining card heading with a body is a §1.2 extra. It is
    // injected into the derived task.md verbatim so the service-layer extras judge
    // sees the same declaration and a compliant card is not false-rejected.
    for (let i = 0; i < headings.length; i++) {
        const heading = headings[i];
        if (heading === undefined || used.has(i))
            continue;
        const body = bodyOf(i);
        if (body !== "")
            out.extras.push({ title: heading.text, body });
    }
    const firstHeading = headings[0];
    const fallback = raw
        .slice(firstHeading === undefined ? 0 : firstHeading.line + 1)
        .join("\n")
        .trim();
    for (const section of ["context", "requirements", "deliverables"]) {
        if (out[section] === "")
            out[section] = fallback;
    }
    return out;
}
/** Render the marker-paired card seed block (T-02, contract C3).
 *
 * T-05/AC-003 (S2 TS half): for a card-backed render whose role is a
 * card-declared WRITELESS report role, the role's `## 交付段契约（本角色）`
 * checklist is appended inside the seed block (each required section as a
 * copyable `## <name>`). The presence guard makes a card that already declares
 * the heading a byte-level fixed point, so re-rendering (or the Python
 * producer's identical `dispatch.py::_envelope_card_body` injection) cannot
 * double-render the section.
 *
 * Scope note (2026-10-14, T-05; widened 2026-10-15, T-13/D-015 option C): the
 * gate is now "the card declares a `type:`" — `recoveryContractSection` already
 * returns `""` for types outside `RECOVERY_CONTRACT_TYPES` (no contract role
 * stays byte-identical), so the checklist reaches every contract role the TS
 * dispatch path produces, `coding` included. The `dispatch-card-injection.test.ts`
 * coding fixture now carries the checklist in its pinned expected bytes. */
export function renderCardSeedSections(sections) {
    const parts = [
        CARD_SEED_MARKER,
        "## 上下文",
        "",
        sections.context.trim(),
        "",
        "## 要求",
        "",
        sections.requirements.trim(),
        "",
        "## 交付格式",
        "",
        sections.deliverables.trim(),
        "",
    ];
    for (const extra of sections.extras) {
        parts.push(`## ${extra.title}`, "", extra.body.trim(), "");
    }
    const contract = sections.type !== undefined ? recoveryContractSection(sections.type) : "";
    if (contract !== "" && !parts.includes(RECOVERY_CONTRACT_HEADING)) {
        parts.push(contract, "");
    }
    // T-02/design §4 + D-002: the claims block rides inside the seed marker
    // region, so the settle path reads it from task.md instead of the (mutable)
    // card file. The seed only slices headings, so without this the block would
    // never reach the derived task.md.
    const claims = (sections.claims ?? "").trim();
    if (claims !== "")
        parts.push(claims, "");
    parts.push(CARD_SEED_DISCLAIMER, CARD_SEED_MARKER_END);
    return parts.join("\n");
}
/** Card-seed region matcher for idempotent re-application (marker → marker). */
const CARD_SEED_SECTION_RE = new RegExp(`${CARD_SEED_MARKER.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[\\s\\S]*?${CARD_SEED_MARKER_END.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\n*`, "g");
/** Idempotent card-seed application: any existing marker region is removed,
 * then the canonical block is prepended to the body. Applying it twice is a
 * byte-level fixed point and leaves exactly one marker pair. */
export function applyCardSeedSections(bodyText, sections) {
    const cleaned = bodyText.replace(CARD_SEED_SECTION_RE, "").replace(/^\n+/, "");
    return `${renderCardSeedSections(sections)}\n\n${cleaned}`;
}
/** T-18 (VC-003 producer identity): this generator's id for the task.md header.
 *
 * The service layer (`launcher.py` `producer_identity`, T-14/AC-009) reads
 * `envelope_producer: <producer-id>@<version>` to tell a *stale producer* (an
 * old framework copy whose task.md shape predates the current envelope/extras
 * contract) apart from a genuinely missing section. The id names this tool
 * path so it is distinct from the Python conductor's `autopilot-conductor`
 * (`dispatch.py` `PRODUCER_NAME`). */
export const DISPATCH_PRODUCER_ID = "agent-team-loop-pm";
/** Machine-readable key of the identity line (`dispatch.py` `PRODUCER_IDENTITY_KEY`). */
export const ENVELOPE_PRODUCER_KEY = "envelope_producer";
/** `<producer-id>@<version>` for the header line.
 *
 * The version is the pi release train's own, read at module load from
 * `packages/coding-agent/package.json` through `config.ts` `VERSION` — the same
 * existing version source `dispatch.py::producer_version()` prefers (and the
 * lockstep version `launcher.py` compares a dotted-numeric producer version
 * against); never a new constant. Shape is byte-compatible with the Python
 * renderer (`f"{PRODUCER_IDENTITY_KEY}: {producer_identity()}"`) and the service
 * parser (`^[ \t]*envelope_producer[ \t]*:[ \t]*(\S+)[ \t]*$`). */
export function envelopeProducerIdentity() {
    return `${DISPATCH_PRODUCER_ID}@${VERSION}`;
}
/** Card section heading whose entries become the task.md `write_face:` head
 * (`dispatch.py` `WRITE_FACE_CARD_SECTION`, design D-001). */
export const WRITE_FACE_CARD_SECTION = "写入允许面";
/** First backtick span of an entry line (`dispatch.py` `_BACKTICK_SPAN_RE`). */
const WRITE_FACE_BACKTICK_SPAN_RE = /`([^`]+)`/;
/** Raw entries of a card's `## 写入允许面` section — the TS mirror of
 * `dispatch.py::_card_write_face_entries` (W-03), reading the card sections
 * this file already extracted ({@link CardSections.extras}) instead of
 * re-parsing the card.
 *
 * `null` = the section is absent (undeclared; no `write_face:` line is
 * rendered). A present-but-entry-less section yields `[]` (the renderer then
 * writes the `-` undeclared marker, D-001/§3.3). Entries keep the author's
 * single-`/` syntax verbatim — the renderer must not transform what the
 * parser will normalize, or the two would stop being the same source. */
export function cardWriteFaceEntries(sections) {
    for (const extra of sections.extras) {
        const title = (extra.title ?? "").trim();
        if (!title.startsWith(WRITE_FACE_CARD_SECTION))
            continue;
        const entries = [];
        for (const raw of (extra.body ?? "").split(/\r\n|\r|\n/)) {
            let item = raw.trim();
            if (item === "")
                continue;
            if ("-*+".includes(item[0] ?? ""))
                item = item.slice(1).trim();
            const span = WRITE_FACE_BACKTICK_SPAN_RE.exec(item);
            if (span !== null) {
                item = (span[1] ?? "").trim();
            }
            else {
                item = (item.split(/[\s（(]/, 1)[0] ?? "").trim();
            }
            if (item !== "" && item !== "-")
                entries.push(item);
        }
        return entries;
    }
    return null;
}
/** The task.md `write_face:` head value for a non-empty entry list — the TS
 * mirror of `dispatch.py::render_write_face_line` (D-113).
 *
 * No entry contains `,` -> the historical single line `write_face: a, b`; any
 * entry contains `,` -> the design §3.1 block-list carrier
 * `write_face:\n  - a\n  - b` (one entry per item), because `,` is an
 * unconditional single-line separator that brackets/braces never shield.
 * `entries` is non-empty by contract — the caller writes `write_face: -` for a
 * declared-but-empty face. */
export function renderWriteFaceLine(entries) {
    const values = entries.map((entry) => entry.trim());
    if (values.some((entry) => entry.includes(","))) {
        return `write_face:\n${values.map((entry) => `  - ${entry}`).join("\n")}`;
    }
    return `write_face: ${values.join(", ")}`;
}
/** Merge the bare `card_path:` / `card_sha256:` / `envelope_producer:` header
 * lines into the same header region as `type:` (no `---` fence — the live PM
 * convention). The identity line is appended last so the existing
 * `card_path:` / `card_sha256:` line positions other suites pin stay fixed.
 *
 * W-08 (D-001): when the card declares a `## 写入允许面` section, its entries
 * are rendered as the task.md `write_face:` head line, byte-identical to
 * `dispatch.py::render_write_face_line` (a declared-but-empty section renders
 * the `-` undeclared marker; the block-list carrier is used when an entry
 * contains `,`). A card without the section keeps the pre-W-08 bytes. */
function mergeCardHeader(frontmatter, cardPath, cardSha256, sections) {
    const header = frontmatter.replace(/\r?\n$/, "");
    const writeFaceEntries = cardWriteFaceEntries(sections);
    const writeFaceLine = writeFaceEntries === null
        ? ""
        : `${writeFaceEntries.length > 0 ? renderWriteFaceLine(writeFaceEntries) : "write_face: -"}\n`;
    return (`${header}\ncard_path: ${cardPath}\ncard_sha256: ${cardSha256}\n` +
        `${ENVELOPE_PRODUCER_KEY}: ${envelopeProducerIdentity()}\n${writeFaceLine}`);
}
/** D-008 zero side effects for the tool/command dispatch channel: the caller
 * created this task dir in the SAME invocation (an existing dir is refused
 * earlier / the key is `manual-<timestamp>`), and the gate runs before any
 * profile injection, so removing it restores the pre-dispatch state. */
function cleanupRefusedTaskDir(taskPath) {
    try {
        fs.rmSync(path.dirname(taskPath), { recursive: true, force: true });
    }
    catch {
        // Best effort: the refusal report is what matters.
    }
}
/** Render a write-face refusal / D-003 deferral for the user-facing channel
 * (D-008: the PM audit channel is the dispatch return value). */
function writeFaceRefusalText(taskKey, refusal) {
    if (refusal.code === "write-face-undeclared") {
        return (`Worker dispatch of '${taskKey}' held serial-only: the card declares no 写入允许面` +
            ` (write_face undeclared, D-003) and ${refusal.inFlight ?? 0} same-key worker(s) are in flight. ` +
            "Nothing was queued. Re-dispatch once the in-flight worker reaches a terminal status, or declare the card's 写入允许面.");
    }
    return (`Worker dispatch of '${taskKey}' refused: ${refusal.reason}. ` +
        "Nothing was written (no task dir, no queue row). Narrow the card's 写入允许面 so it does not overlap an in-flight same-key worker, then re-dispatch.");
}
/**
 * Normalize a dispatch's card reference to the key-relative `tasks/<name>.md`
 * form the traceability audit (T-06 `card_audit.py`) reads. A card outside the
 * owner key's `tasks/` dir falls back to a repo-relative posix path; the last
 * resort is the bare basename so a header is always written.
 */
export function normalizeCardPathForHeader(cardPathInput, ownerKey, agenticdocRoot, projectDir) {
    const resolved = path.isAbsolute(cardPathInput)
        ? path.resolve(cardPathInput)
        : path.resolve(projectDir, cardPathInput);
    const keyTasksDir = path.join(agenticdocRoot, ownerKey, "tasks");
    if (isSameOrUnder(keyTasksDir, resolved))
        return `tasks/${path.basename(resolved)}`;
    const rel = path.relative(projectDir, resolved);
    if (rel !== "" && !rel.startsWith("..") && !path.isAbsolute(rel))
        return rel.split(path.sep).join("/");
    return path.basename(resolved);
}
const EMPTY_CARD_SECTIONS = { context: "", requirements: "", deliverables: "", extras: [] };
/**
 * G-1 tool-layer gate (design §4): resolve the card path, judge the envelope
 * with T-01's `readEnvelope`, then the per-type §1.2 extras on the CARD TEXT
 * (the same `typeExtrasMissing` the service layer runs on the derived task.md,
 * T-12/F-02) and the seed minimum (`seedItemsMissing`, T-12/F-05), and only
 * then digest + extract the seed. Never judges content quality; a refusal is a
 * plain report the caller turns into text (zero side effects).
 *
 * The claims judge (T-02, design §5 G1) runs LAST, on the same card text, so a
 * card that already fails the envelope keeps its historical refusal byte for
 * byte and its `dispatch-card` code:
 *
 *  - `MW_CLAIM_GATE=enforce` (D-006) merges EVERY finding — the unusable rows
 *    that `claimsGaps` always reports plus the soft ones it only reports under
 *    enforce — into `missing`, and the verdict carries `dispatch-claims`;
 *  - `advisory` (the calibrated default) refuses NOTHING: every finding,
 *    structural or soft, rides along as a `warnings` entry on the receipt and
 *    the dispatch proceeds. A gray-release gate that could still reject a card
 *    would be a new way to lose a dispatch on a table typo, which is the exact
 *    failure mode P-048 measured (an over-strict schema produced consecutive
 *    false refusals); `enforce` is the only mode that judges.
 *
 * A card without a claims block yields `claims=[]`, `caps=null`, `warnings=[]`
 * and not a single changed byte downstream (AC-007).
 */
export function readDispatchCard(input) {
    const raw = input.cardPath.trim();
    const resolvedPath = path.isAbsolute(raw) ? path.resolve(raw) : path.resolve(input.projectDir, raw);
    const empty = {
        ok: false,
        code: DISPATCH_CARD_CODE,
        resolvedPath,
        missing: [],
        headerPath: "",
        sha256: "",
        sections: EMPTY_CARD_SECTIONS,
        claims: [],
        caps: null,
        warnings: [],
    };
    if (raw === "")
        return { ...empty, missing: ["card_path"] };
    const envelope = readEnvelope(resolvedPath);
    if (!envelope.ok)
        return { ...empty, missing: envelope.missing };
    let text;
    try {
        text = fs.readFileSync(resolvedPath, "utf8");
    }
    catch {
        return { ...empty, missing: ["file"] };
    }
    // T-12/F-02: judge the per-type extras on the CARD TEXT here so G-1 and G-3
    // are the same criterion (the derived task.md carries these sections too).
    // T-12/F-05: the seed minimum is a G-1 requirement. Any gap refuses and names
    // the item; nothing is written.
    const missing = [...(envelope.type === "" ? [] : typeExtrasMissing(envelope.type, text)), ...seedItemsMissing(text)];
    if (missing.length > 0)
        return { ...empty, missing };
    const claimBlock = parseClaimsBlock(text);
    const enforce = claimGateMode() === "enforce";
    // One call per mode: `enforce:false` is the structural set, `enforce:true` is
    // structural + soft. Advisory takes the union as warnings and refuses nothing
    // (D-006 gray release); enforce turns the union into the refusal list.
    const audit = claimsGaps(claimBlock, { projectDir: input.projectDir, enforce: true });
    const claimsMissing = enforce ? [...claimBlock.errors, ...audit] : [];
    const warnings = enforce ? [] : [...claimBlock.errors, ...audit];
    const caps = claimBlock.claims.length > 0 ? claimBudgetCaps(claimBlock.claims) : null;
    if (claimsMissing.length > 0) {
        return {
            ...empty,
            code: DISPATCH_CLAIMS_CODE,
            missing: claimsMissing,
            claims: claimBlock.claims,
            caps,
        };
    }
    const sections = {
        // T-05/AC-003: carry the card's `type:` into the seed so the S2 checklist
        // can be rendered (a `CardSections` built directly from card text has no
        // type and stays byte-identical).
        ...extractCardSections(claimBlock.present ? stripClaimsBlockText(text) : text),
        type: envelope.type,
    };
    // T-02: the claims block rides into task.md verbatim (D-002) — set only when
    // the card actually declares one, so a pre-claims card keeps its bytes.
    const claimsText = claimBlock.present ? extractClaimsBlockText(text) : "";
    if (claimsText !== "")
        sections.claims = claimsText;
    return {
        ok: true,
        code: DISPATCH_CARD_CODE,
        resolvedPath,
        missing: [],
        headerPath: normalizeCardPathForHeader(raw, input.ownerKey, input.agenticdocRoot, input.projectDir),
        sha256: cardDigest(resolvedPath),
        sections,
        claims: claimBlock.claims,
        caps,
        warnings,
    };
}
/** Refusal text for an incomplete card (AC-007 fail-closed): names the code,
 * the missing items and the exact card path; says nothing was written. A
 * claims verdict (T-02/design §3.2) keeps the same structure under its own
 * code, `missing=[claim:C2:locator, claims:budget-sum:48>40]` as parsed. */
export function dispatchCardRefusal(gate) {
    if (gate.code === DISPATCH_CLAIMS_CODE) {
        return (`[${DISPATCH_CLAIMS_CODE}] dispatch refused: card '${gate.resolvedPath}' declares a claims block that cannot be used ` +
            `(missing=[${gate.missing.join(", ")}]).\n` +
            `Required per claim row: 类型 ∈ ${CLAIM_TYPES.join(" | ")}, 陈述, 反证条件, 定位, 判据 (its prefix must match the type: cmd: / grep: / shape: / manual:), 预算 (a non-negative integer); Σ预算 ≤ 40 with 类型 manual counted twice.\n` +
            "Fix the <!-- mw-claims: v1 --> block at that path (or remove it entirely), then re-dispatch; nothing was written.");
    }
    const labels = gate.missing
        .filter((item) => item in ENVELOPE_SECTION_LABELS)
        .map((item) => ENVELOPE_SECTION_LABELS[item]);
    return (`[${DISPATCH_CARD_CODE}] dispatch refused: card '${gate.resolvedPath}' is not a complete dispatch envelope ` +
        `(missing=[${gate.missing.join(", ")}]).\n` +
        (labels.length > 0 ? `Missing sections: ${labels.join(" / ")}.\n` : "") +
        "Required: type + 上下文/要求/交付格式; per type: coding(写入允许面/写入禁止面/验收命令/改动历史), research(唯一证据文件), review(审计目标/未覆盖面声明); seeds: a goal.md reference and at least one path:line reference.\n" +
        "Fix the card at that path (or pass a different card_path), then re-dispatch; nothing was written.");
}
/** The advisory claims receipt line (design §5 G1): appended ONLY when the card
 * declares claims, so a pre-claims card's receipt stays byte-identical
 * (`triage-dispatch.test.ts` pins the full string). */
export function claimsReceiptLine(gate) {
    if (gate.claims.length === 0)
        return "";
    const caps = gate.caps === null ? "caps=none" : `caps=${gate.caps.fileCap}/${gate.caps.byteCap}`;
    const warnings = gate.warnings.length > 0 ? gate.warnings.join(", ") : "none";
    return `\n[claims] ${claimGateMode()} claims=${gate.claims.length} ${caps} warnings=[${warnings}]`;
}
/** Single write point for one dispatch's task.md (contract C4). Both dispatch
 * entries — the `dispatch_worker` tool and the `/worker` command — go through
 * here so the pipeline (frontmatter merge, contract-section injection, mkdir,
 * writeFileSync) has exactly one implementation. The T-01 extraction is
 * byte-for-byte equivalent to the inline writes it replaced: with no
 * `writeScope` and no injection hook the file content is
 * `${frontmatter}\n${body}\n` and only the mkdir/write order is shared. T-02
 * fills in the write-surface contract section (C2) and `injected` reports
 * whether this call wrote one. */
export function writeDispatchTaskMd(deps, input) {
    let frontmatter = mergeAllowForeignWrite(mergeWriteScope(mergeReadScope(input.frontmatter, input.readScope, input.readFileCap, input.readByteCap), input.writeScope), input.allowForeignWrite);
    if (input.card) {
        frontmatter = mergeCardHeader(frontmatter, input.card.headerPath, input.card.sha256, input.card.sections);
    }
    // T-08: merge chain end — the decision id is the last head line, so the
    // existing `card_path:` / `write_face:` positions other suites pin stay fixed.
    frontmatter = mergeDecisionHeader(frontmatter, input.decision);
    const taskDir = workerTaskDir(deps.agenticdocRoot, deps.ownerKey, input.taskKey);
    fs.mkdirSync(taskDir, { recursive: true });
    const taskMdPath = path.join(taskDir, "task.md");
    const body = input.card ? applyCardSeedSections(input.body, input.card.sections) : input.body;
    const plain = `${frontmatter}\n${body}\n`;
    const content = input.injectWriteSurface ? applyWriteSurfaceContract(plain, input.type, input.writeScope) : plain;
    fs.writeFileSync(taskMdPath, content, "utf8");
    // T-04d: the dp1 state path is recorded in the SAME trace the worker appends
    // to, so a legacy fallback is auditable instead of silent. Best-effort by
    // design: a trace failure must never fail a dispatch whose task.md already
    // landed.
    if (input.decisionTrace !== undefined) {
        try {
            fs.appendFileSync(path.join(taskDir, "trace.log"), `${input.decisionTrace}\n`, "utf8");
        }
        catch {
            // Diagnostic only — the task.md write is the dispatch's contract.
        }
    }
    return { ok: true, path: taskMdPath, injected: input.injectWriteSurface === true };
}
/**
 * Register agent-callable tools for worker dispatch and task listing.
 * These complement the slash commands in registerWorkerCommands.
 */
export function registerWorkerTools(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, projectDir = path.dirname(agenticdocRoot), 
/** T-03 test seam for the DP-1 child; production omits it. */
triageRun) {
    // dispatch_worker: create a task.md and immediately dispatch it to the worker queue.
    pi.registerTool({
        name: "dispatch_worker",
        label: "dispatch_worker",
        description: "Dispatch a task to a background worker agent. Creates .agenticdoc/<owner key>/workers/<task_key>/task.md and queues it for execution by the mw worker service. Returns the task key on success. " +
            'Cross-key writes are refused: a key another window holds live is READ-ONLY here — read it with list_tasks { scope: "all" } and take it over with switch_key before writing into it.',
        parameters: Type.Object({
            task_key: Type.String({
                description: "Unique kebab-case key for this task (e.g. 'fix-login-bug', 'add-auth-endpoint'). Must be unique across tasks in this project.",
            }),
            card_path: Type.String({
                description: "REQUIRED. Path to the dispatch card (task book) this worker is generated from — relative to the repo root or absolute, e.g. '.agenticdoc/<key>/tasks/T-02-slug.md'. The card must carry the dispatch envelope (type + 上下文 / 要求 / 交付格式), the per-type extras (coding: 写入允许面/写入禁止面/验收命令/改动历史; research: 唯一证据文件; review: 审计目标/未覆盖面声明), and the seed minimum (a goal.md reference plus at least one path:line reference); an incomplete or missing card refuses the dispatch with zero side effects. The card's envelope, extras and context are injected as the seed (not an upper bound on what the worker may read) and recorded via card_path/card_sha256 in task.md for traceability.",
            }),
            description: Type.String({
                description: "Full task description and instructions for the worker agent.",
            }),
            cli: Type.Optional(Type.String({
                description: "Worker CLI: 'pi' (default for all task types incl. review/research), 'claude' (explicit override — requires claude credentials, fails per-task when missing), 'codex' (codex tasks).",
            })),
            model: Type.Optional(Type.String({
                description: "Optional model override for this worker (e.g. 'timi/gpt-5.6-sol'). Deviating from the configured .mw/dispatch.yml role default requires model_reason; a value equal to that default is not pinned (the config stays the source of truth).",
            })),
            model_reason: Type.Optional(Type.String({
                description: "Why this task deviates from the .mw/dispatch.yml role default. Required when model is set and the role has a configured default with a different value; recorded in task.md as model-reason.",
            })),
            type: Type.Optional(Type.String({
                description: "Task type: 'coding' | 'review' | 'research' | 'rag-research' | 'vision' | 'decide_prepare'. Selects the dispatch.yml role (and the worker tool allowlist). Use 'vision' for tasks that must read image files (screenshots/mockups). Default: derived from cli (pi -> coding, claude -> review, codex -> codex).",
            })),
            images: Type.Optional(Type.Union([Type.Literal("yes"), Type.Literal("no")], {
                description: "Declare the image requirement: 'yes' means this task must look at images (refused when the effective model cannot take image input), 'no' exempts it. Omit to auto-detect an existing image file referenced in the description.",
            })),
            allow_foreign_write: Type.Optional(Type.Boolean({
                description: "AC-005a escape hatch: dispatch a writeless role even when its task book names an external write target. Recorded in task.md as `allow_foreign_write: true` for audit; use only when a human accepted the external path.",
            })),
            key: Type.Optional(Type.String({
                description: "AgenticTask key owning this worker task. Default: this window's claimed key (the one it watches and holds in _index.parallel), else the active key when no other live window holds it, else _scratch.",
            })),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
            const { task_key, card_path, description, cli = "pi", model, model_reason, type, images, key, allow_foreign_write, } = params;
            // RAG dispatcher gate (VC-003): an unusable rag config (e.g. `enabled`
            // naming an undefined server) must refuse BEFORE any task.md is created
            // and before the queue row lands.
            const ragCheck = validateRagEnabled(projectDir);
            if (!ragCheck.ok) {
                return { content: [{ type: "text", text: ragCheck.message }], details: undefined };
            }
            const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, key, agenticdocRoot);
            // Cross-key write guard (AC-024/AC-006): unconditional (DD-07e) — the
            // guard is the single write gate for every dispatch, explicit key or not.
            // resolveOwnerKeyWithSync already degrades a foreign-live or reserved
            // value to _scratch, so the implicit path gains no new refusal.
            const refusal = foreignLiveClaimRefusal(indexStore, ownerKey);
            if (refusal)
                return { content: [{ type: "text", text: refusal }], details: undefined };
            const validCli = ["pi", "claude", "codex"];
            if (!validCli.includes(cli)) {
                return {
                    content: [{ type: "text", text: `Invalid cli '${cli}'. Must be one of: ${validCli.join(", ")}.` }],
                    details: undefined,
                };
            }
            // Task type is declarable (mw-dispatch-role-escape): without it a pi
            // worker could never reach the review/research dispatch.yml role or tool
            // allowlist, which is what forced hand-written model overrides.
            const typeResolution = resolveDispatchType(cli, type ?? "");
            if (!typeResolution.ok) {
                return { content: [{ type: "text", text: typeResolution.message }], details: undefined };
            }
            const provider = cli === "pi" ? "timi" : "";
            // Docs gate, phase-tiered (mw-worker-visibility-gate): the owner key's
            // CURRENT phase picks the tier — SPEC (or placeholder/unknown) needs the
            // spec-side chain; from DESIGN onward the full six-item chain. One
            // phase read, reused by the task.md frontmatter below.
            const ownerPhase = dispatchPhase(agenticdocRoot, ownerKey);
            const docGaps = dispatchDocGaps(agenticdocRoot, ownerKey, ownerPhase);
            if (docGaps.length > 0) {
                return {
                    content: [
                        {
                            type: "text",
                            text: `Worker dispatch blocked: key '${ownerKey}' is missing phase documentation.\n` +
                                `${docGaps.map((g) => `- ${g}`).join("\n")}\n${DOC_GATE_HINT}`,
                        },
                    ],
                    details: undefined,
                };
            }
            // Worker tasks live under {ownerKey}/workers/<task_key>/ (never at the
            // agenticdoc root - that namespace belongs to AgenticTask keys).
            const taskDir = workerTaskDir(agenticdocRoot, ownerKey, task_key);
            if (fs.existsSync(taskDir)) {
                return {
                    content: [
                        {
                            type: "text",
                            text: `Task '${task_key}' already exists at ${taskDir}. Choose a different task_key or check existing tasks with list_tasks.`,
                        },
                    ],
                    details: undefined,
                };
            }
            const typeField = typeResolution.type;
            // AC-005a (T-02): a role with neither write/edit nor bash cannot reach a
            // path outside its own task dir, so a task book ordering one is
            // unsatisfiable. Refused here — after the cross-key guard, before the
            // frontmatter plan and decisively before mkdir/task.md/queue — so the
            // refusal has zero side effects. `research` (writeless but shell-capable)
            // is NOT refused; it only gets the contract section + write_scope header.
            const writelessRole = isWritelessRole(typeField);
            const allowForeignWrite = allow_foreign_write === true;
            if (writelessRole) {
                const verdict = judgeWriteIntent({
                    type: typeField,
                    description,
                    taskDir,
                    projectRoot: projectDir,
                    keyDir: path.join(agenticdocRoot, ownerKey),
                    trueRoot: agenticdocRoot,
                    allowForeignWrite,
                });
                if (!verdict.ok) {
                    return {
                        content: [
                            {
                                type: "text",
                                text: writeIntentRefusal({
                                    taskKey: task_key,
                                    type: typeField,
                                    path: verdict.violations[0]?.path ?? "",
                                }),
                            },
                        ],
                        details: undefined,
                    };
                }
            }
            // G-1 tool-layer envelope gate (T-02, design §4): the card must exist and
            // carry the §1 envelope + §1.2 type extras BEFORE any task.md is written
            // or a queue row lands. Placed after the earlier guards so their own
            // refusals stay byte-identical; still decisively before mkdir/queue.
            const cardGate = readDispatchCard({
                cardPath: card_path ?? "",
                ownerKey,
                agenticdocRoot,
                projectDir,
            });
            if (!cardGate.ok) {
                return { content: [{ type: "text", text: dispatchCardRefusal(cardGate) }], details: undefined };
            }
            // Model plan: validate the effective value and enforce the override
            // reason BEFORE any filesystem write (a refusal must leave no task dir).
            const modelPlan = planDispatchFrontmatter({
                cwd: projectDir,
                cli,
                provider,
                taskType: typeField,
                phase: ownerPhase,
                description,
                images,
                model: model ?? "",
                modelReason: model_reason ?? "",
                registry: _context?.modelRegistry,
                triageRun,
                // T-04d: owning key + the card's declared write face are the dispatch
                // facts the dp1 structured state needs (the rest comes from the plan).
                dp1: { key: ownerKey, writeFace: cardWriteFaceEntries(cardGate.sections), allowForeignWrite },
            });
            if (!modelPlan.ok) {
                return { content: [{ type: "text", text: modelPlan.message }], details: undefined };
            }
            // DP-1 ledger + (on disagreement) the one PM wake for this dispatch.
            emitDispatchTriage(pi, agenticdocRoot, modelPlan.triage);
            const written = writeDispatchTaskMd({ agenticdocRoot, ownerKey }, {
                taskKey: task_key,
                type: typeField,
                body: description,
                frontmatter: modelPlan.frontmatter,
                writeScope: writelessRole && isShellRole(typeField) ? renderDefaultWriteScope(ownerKey, task_key) : undefined,
                // T-02/design §4: claims-backed read budget. `caps=null` (no claims
                // block) leaves both the bytes and the interception behaviour alone.
                readScope: cardGate.caps === null ? undefined : claimReadScope(ownerKey, cardGate.claims),
                readFileCap: cardGate.caps?.fileCap,
                readByteCap: cardGate.caps?.byteCap,
                injectWriteSurface: writelessRole,
                allowForeignWrite,
                card: { headerPath: cardGate.headerPath, sha256: cardGate.sha256, sections: cardGate.sections },
                // T-08/T-04c: the decision this dispatch ADOPTED (D-041). `suggest` and
                // unavailable advice carry no decision, so the bytes stay pre-T-08.
                decision: modelPlan.triage?.decision,
                // T-04d: record which dp1 state shape the child actually received.
                decisionTrace: modelPlan.triage?.stateTrace,
            });
            const taskMdPath = written.path;
            const outcome = await dispatchTask({ taskKey: task_key, status: "pending", cli, provider, model: model ?? "", taskPath: taskMdPath }, workerStore);
            if (!outcome.ok) {
                cleanupRefusedTaskDir(taskMdPath);
                return { content: [{ type: "text", text: writeFaceRefusalText(task_key, outcome) }], details: undefined };
            }
            // Record the dispatch on this window's state (mw-task-scope-isolation) so
            // list_tasks / ack keep owning tasks that did NOT land under the watched
            // key (explicit cross-key dispatch, or the global-active fallback).
            if (watch.dispatchedTaskKeys === undefined)
                watch.dispatchedTaskKeys = new Set();
            watch.dispatchedTaskKeys.add(task_key);
            return {
                content: [
                    {
                        type: "text",
                        text: appendTriageReceipt(`Dispatched worker '${task_key}' (type: ${typeField}, role: ${roleForTaskType(typeField)}, ${modelPlan.echo}) under key '${ownerKey}'. Task file: ${taskMdPath}. Check mw_status to confirm the service is running.`, modelPlan.triage) + claimsReceiptLine(cardGate),
                    },
                ],
                details: undefined,
            };
        },
    });
    // ack_worker_result: the agent-side ack channel (AC-005) — equivalent to
    // /mw ack. Registered here (PM activation path only); worker mode never
    // registers tools, so workers cannot ack their own results.
    pi.registerTool({
        name: "ack_worker_result",
        label: "ack_worker_result",
        description: "Acknowledge a worker's terminal result (done/failed/needs-clarification) after absorbing it: the row moves out of the watch widget's unhandled section into folded history. task_key acks one task; 'all' acks every unacked terminal task THIS WINDOW owns (its watched key plus tasks it dispatched) — another window's rows are refused, never silently cleared.",
        promptGuidelines: [
            "After absorbing a terminal worker result (the readback body / output.md), call ack_worker_result with its task_key — or 'all' after a batch — so the widget's unhandled section clears; unacked failed/needs-clarification rows stay listed until acked.",
        ],
        parameters: Type.Object({
            task_key: Type.String({ description: "Worker task key to ack, or 'all' for every unacked terminal task." }),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
            const { task_key } = params;
            const target = task_key.trim();
            if (!target) {
                return { content: [{ type: "text", text: "task_key is required (or 'all')." }], details: undefined };
            }
            const result = await ackTasks(workerStore, ackStore, target === "all" ? "all" : [target], {
                watch,
                agenticdocRoot,
            });
            const parts = [];
            if (result.acked.length > 0)
                parts.push(`Acked ${result.acked.length} task(s): ${result.acked.join(", ")}.`);
            for (const r of result.rejected)
                parts.push(`NOT acked: ${r.key} — ${r.reason}.`);
            if (parts.length === 0)
                parts.push("No unacked terminal tasks.");
            return { content: [{ type: "text", text: parts.join("\n") }], details: undefined };
        },
    });
    // list_tasks: worker queue view, scoped to this window by default
    // (mw-task-scope-isolation); terminal rows carry an `acked` badge when
    // acknowledged (AC-011) and every row carries its owning key.
    pi.registerTool({
        name: "list_tasks",
        label: "list_tasks",
        description: "List worker tasks with their current status (pending / running / done / failed / needs-clarification); every row carries its owning key. " +
            'scope "mine" (default) lists only this window\'s tasks — its watched key plus tasks it dispatched; scope "key" lists one key (pass key); scope "all" lists the whole project. ' +
            "Acked terminal tasks are badged 'acked'. " +
            'READING is never restricted by the cross-key write guard: scope "all"/"key" cover other windows\' keys, so use them to inspect status before deciding anything. ' +
            "Acks are refused for another window's rows.",
        parameters: Type.Object({
            scope: Type.Optional(Type.String({ description: '"mine" (default, this window) | "key" (with key) | "all" (whole project).' })),
            key: Type.Optional(Type.String({ description: 'Owner key to list when scope is "key".' })),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
            const { scope = "mine", key = "" } = (params ?? {});
            const reply = (text) => ({
                content: [{ type: "text", text }],
                details: undefined,
            });
            const acked = new Set(ackStore.readAll().keys());
            const format = (e) => {
                const base = `${ownerKeyOf(e, agenticdocRoot)} :: ${e.taskKey} | ${e.status} | ${e.cli}` +
                    `${e.model ? ` | model: ${e.model}` : ""}`;
                return acked.has(e.taskKey) ? `${base} | acked` : base;
            };
            const rows = (entries, emptyText) => entries.length === 0 ? emptyText : entries.map(format).join("\n");
            if (scope === "all") {
                return reply(rows(workerStore.readAll(), "No tasks found."));
            }
            if (scope === "key") {
                const wanted = key.trim();
                if (!wanted) {
                    return reply('scope "key" requires key — pass the owner key, e.g. { scope: "key", key: "mw-foo" }.');
                }
                const entries = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot) === wanted);
                return reply(rows(entries, `No tasks found for key '${wanted}'.`));
            }
            if (scope !== "mine") {
                return reply(`Unknown scope '${scope}'. Use "mine" (this window), "key" (with key), or "all" (whole project).`);
            }
            const mine = workerStore.readAll().filter((e) => ownedByThisWindow(e, watch, agenticdocRoot));
            if (mine.length > 0) {
                return reply(rows(mine, "No tasks found."));
            }
            return reply(`No tasks found for this window (watched key: ${watch.key ?? "(none)"}).\n` +
                'scope "mine" covers the watched key plus tasks this window dispatched; other windows\' tasks are never listed.\n' +
                "- switch_key a key to take it over and watch its workers, or\n" +
                '- list_tasks with scope: "all" to see every key in this project.');
        },
    });
}
/** Register the agent-callable switch_key tool: same takeover as
 * /pm-key switch, callable mid-conversation. Tool description + prompt
 * guidelines teach the agent when to call it (explicit user request, or
 * starting real task work on a key — ask the user first in that case). */
export function registerSwitchKeyTool(pi, indexStore, watch, refreshWatch, agenticdocRoot) {
    pi.registerTool({
        name: "switch_key",
        label: "switch_key",
        description: "Take over (claim + watch) an AgenticTask key in this window: marks it active in _index.parallel with this window's claim (host:pid) and shows its live worker progress in the bottom widget. " +
            "Call it when the user asks to take over or switch to a key, or when you are about to execute a key's tasks in this window. " +
            "Writing .agenticdoc/{key}/spec.md, design.md, or plan.md switches automatically — no call needed. " +
            "If another live window holds the key's claim, the call fails unless force is true; tell the user and let them decide.",
        promptGuidelines: [
            "Before doing real work on an AgenticTask key (executing its tasks), make sure this window has taken it over via switch_key; if the user has not asked for that key, ask them first whether to switch.",
        ],
        parameters: Type.Object({
            key: Type.String({ description: "The AgenticTask key to take over." }),
            force: Type.Optional(Type.Boolean({
                description: "Steal the claim even if another live window holds it. Only with the user's explicit confirmation.",
            })),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => {
            const { key, force = false } = params;
            const trimmed = key.trim();
            if (!trimmed) {
                return { content: [{ type: "text", text: "key is required." }], details: undefined };
            }
            const result = await takeOverKey(indexStore, trimmed, force, agenticdocRoot);
            if (!result.ok) {
                if (result.refusal) {
                    return {
                        content: [
                            {
                                type: "text",
                                text: `Key '${trimmed}' is refused (${result.refusal}): reserved framework names and illegal key shapes cannot be claimed.`,
                            },
                        ],
                        details: undefined,
                    };
                }
                return {
                    content: [
                        {
                            type: "text",
                            text: `Key '${trimmed}' is claimed by another live window (${result.blockedBy}). The takeover was NOT performed. Tell the user; they can decide on a forced takeover (force=true).`,
                        },
                    ],
                    details: undefined,
                };
            }
            watch.key = trimmed;
            pi.appendEntry(WATCH_ENTRY_TYPE, { key: trimmed, claimed: true });
            refreshWatch(ctx);
            const auditNote = result.audit.length > 0
                ? `\n\nPHASE-CHAIN AUDIT WARNINGS for this key (fix before continuing; phase changes go through advance_phase.py only):\n${result.audit.join("\n")}`
                : "";
            // pm-state.md mirror sync failure is visible but non-fatal (D-108).
            const syncNote = claimSyncWarningText(trimmed, result.claimSync);
            return {
                content: [
                    {
                        type: "text",
                        text: `Took over key '${trimmed}' (claim ${result.claimId})` +
                            `${result.created ? " — new key registered in _index.parallel" : ""}. ` +
                            "This window now watches it; the bottom widget shows its live progress. Previously active keys were marked idle." +
                            auditNote +
                            (syncNote === "" ? "" : `\n\n${syncNote}`),
                    },
                ],
                details: undefined,
            };
        },
    });
}
/** Register the agent-callable advance_phase tool: the shell-free path
 * through the AgenticTask phase gates. The guard blocks hand-edits of
 * pm-state.md's '- Phase:' line and points at advance_phase.py; running that
 * via the bash tool was the only route, so a window whose shell resolution
 * or in-shell `python` differs (fresh machines: WSL-only bash, Store-stub
 * python, python3-only Linux) had NO way to advance a phase — it deadlocked
 * with "no shell, cannot execute advance_phase.py / update_index.py". This
 * tool spawns the script directly (list args, no shell); gate semantics stay
 * in the Python script, the single source of truth audit_phase.py replays. */
export function registerAdvancePhaseTool(pi, projectDir, indexStore) {
    const ladder = PHASE_ORDER.map((p) => p.toLowerCase());
    pi.registerTool({
        name: "advance_phase",
        label: "advance_phase",
        description: "Advance an AgenticTask key to the target phase by running the framework gate script (advance_phase.py): checks the phase-gate evidence (spec/design/plan/tasks/execute/done prerequisites), updates pm-state.md, and syncs _index.parallel. Runs the Python script directly without a shell — prefer this over `python .../advance_phase.py` via the bash tool. This is the only sanctioned way to change a key's phase; hand-editing pm-state.md's '- Phase:' line is blocked. " +
            "Cross-key writes are refused: another window's live key is READ-ONLY here (read its phase with list_tasks, take it over with switch_key first).",
        promptGuidelines: [
            "Change phases only through this tool (or the equivalent python script when the shell works); when the result reports GATE BLOCKED, fix the listed evidence gaps before retrying.",
        ],
        parameters: Type.Object({
            key: Type.String({ description: "AgenticTask key to advance (not _scratch)." }),
            target_phase: Type.String({
                description: "Target phase (any case): spec | design | plan | tasks | execute | verify | done.",
            }),
            summary: Type.Optional(Type.String({
                description: "Required when target_phase is done: one-line closing summary (what was added/changed + impact surface) recorded in _project_log.md as the cross-key summary row.",
            })),
            supersedes: Type.Optional(Type.String({
                description: "Key this one supersedes, recorded in _project_log.md when advancing to done.",
            })),
        }),
        execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
            const { key, target_phase, summary, supersedes } = params;
            const trimmedKey = key.trim();
            const target = target_phase.trim().toLowerCase();
            if (!trimmedKey || !target) {
                return { content: [{ type: "text", text: "key and target_phase are required." }], details: undefined };
            }
            // Same name gate as the guard and IndexStore.claim (AC-006, direction
            // consistent): reserved names (incl. _scratch) and illegal shapes are not
            // phase-tracked keys. `_scratch` keeps its historical wording.
            const nameRefusal = keyNameRefusal(trimmedKey);
            if (nameRefusal) {
                const reason = nameRefusal.code === "reserved-key-name" ? "has a reserved prefix" : `is refused (${nameRefusal.code})`;
                return {
                    content: [
                        {
                            type: "text",
                            text: `Key '${trimmedKey}' ${reason} and is not a phase-tracked AgenticTask key.`,
                        },
                    ],
                    details: undefined,
                };
            }
            if (!ladder.includes(target)) {
                return {
                    content: [
                        { type: "text", text: `Unknown phase '${target_phase.trim()}'. Valid: ${ladder.join(" | ")}.` },
                    ],
                    details: undefined,
                };
            }
            // done 汇总契约（advance_phase.py 同步校验，exit 2）：--summary 是
            // _project_log.md 汇总列唯一数据源，缺失不允许推进。工具层先拦，
            // 错误信息比脚本退出码可读。
            if (target === "done" && !(summary ?? "").trim()) {
                return {
                    content: [
                        {
                            type: "text",
                            text: "Advancing to done requires a non-empty summary — one line on what was added/changed and the impact surface (written to _project_log.md as the cross-key summary row).",
                        },
                    ],
                    details: undefined,
                };
            }
            const args = [trimmedKey, target];
            if (summary)
                args.push("--summary", summary);
            if (supersedes)
                args.push("--supersedes", supersedes);
            // Cross-key write guard (AC-024): advancing another live window's key
            // rewrites ITS pm-state.md + _index.parallel row, so it is refused before
            // the gate script runs. An unclaimed key still advances (new-key
            // bootstrap), and this window's own claim is untouched by the guard.
            const crossKeyRefusal = foreignLiveClaimRefusal(indexStore, trimmedKey);
            if (crossKeyRefusal)
                return { content: [{ type: "text", text: crossKeyRefusal }], details: undefined };
            const result = runAgenticScript(projectDir, "advance_phase.py", args);
            return { content: [{ type: "text", text: result.output }], details: undefined };
        },
    });
}
/**
 * Spawn a worker directly from the pi window.
 * Usage: /worker <claude|codex|pi> [--type <t>] [--model <id>] [--reason <text>] [--key <name>] <desc>
 */
export function registerWorkerCommands(pi, workerStore, indexStore, agenticdocRoot, watch, projectDir = path.dirname(agenticdocRoot), 
/** T-03 test seam for the DP-1 child; production omits it. */
triageRun) {
    const USAGE = "Usage: /worker <claude|codex|pi> --card <card-path> [--type coding|review|research|rag-research|vision] [--model <id>] [--reason <text>] [--key <name>] [--allow-foreign-write] <task description>";
    pi.registerCommand("worker", {
        description: "Spawn a worker: /worker <claude|codex|pi> --card <card-path> [--type <t>] [--model <id>] [--reason <text>] <task description>",
        handler: async (args, ctx) => {
            const parts = args.trim().split(/\s+/);
            const cli = (parts[0] ?? "").toLowerCase();
            // Optional flags right after the cli; everything else is the description.
            let idx = 1;
            let model = "";
            let modelReason = "";
            let typeArg = "";
            let keyArg = "";
            let cardArg = "";
            let imagesArg;
            let allowForeignWriteArg = false;
            while (["--card", "--model", "--type", "--reason", "--key", "--images", "--allow-foreign-write"].includes(parts[idx] ?? "")) {
                const flag = parts[idx];
                if (flag === "--allow-foreign-write") {
                    allowForeignWriteArg = true;
                    idx += 1;
                    continue;
                }
                const value = parts[idx + 1] ?? "";
                idx += 2;
                if (!value) {
                    ctx.ui.notify(USAGE, "warning");
                    return;
                }
                if (flag === "--card")
                    cardArg = value;
                else if (flag === "--model")
                    model = value;
                else if (flag === "--type")
                    typeArg = value;
                else if (flag === "--reason")
                    modelReason = value;
                else if (flag === "--images") {
                    if (value !== "yes" && value !== "no") {
                        ctx.ui.notify("--images must be 'yes' or 'no'.", "warning");
                        return;
                    }
                    imagesArg = value;
                }
                else
                    keyArg = value;
            }
            const description = parts.slice(idx).join(" ");
            const validCli = ["claude", "codex", "pi"];
            if (!validCli.includes(cli)) {
                ctx.ui.notify(USAGE, "warning");
                return;
            }
            if (!description) {
                ctx.ui.notify("Task description is required.", "warning");
                return;
            }
            // Task type: declarable, else the legacy cli-derived mapping.
            const typeResolution = resolveDispatchType(cli, typeArg);
            if (!typeResolution.ok) {
                ctx.ui.notify(typeResolution.message, "warning");
                return;
            }
            const typeField = typeResolution.type;
            const provider = cli === "pi" ? "timi" : "";
            // RAG dispatcher gate (VC-003): refuse before creating any task.md.
            const ragCheck = validateRagEnabled(projectDir);
            if (!ragCheck.ok) {
                ctx.ui.notify(ragCheck.message, "warning");
                return;
            }
            // Create task directory and task.md under {ownerKey}/workers/ (persist
            // type/model/model-reason so they are visible + re-parseable)
            const taskKey = `manual-${Date.now()}`;
            const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, keyArg, agenticdocRoot);
            // Cross-key write guard (AC-003): the SAME decision function the
            // dispatch_worker tool uses. A key another window holds live must be refused
            // before the docs gate, the frontmatter plan and — decisively — before any
            // mkdir/task.md/queue write, so a refusal is zero-side-effect. The implicit
            // path never reaches here with a foreign key (resolveOwnerKeyWithSync degrades
            // to _scratch); an explicit `--key` is what makes this reachable, exactly like
            // the tool's explicit-key branch.
            const crossKeyRefusal = foreignLiveClaimRefusal(indexStore, ownerKey);
            if (crossKeyRefusal) {
                ctx.ui.notify(crossKeyRefusal, "warning");
                return;
            }
            // AC-005a (T-02): the SAME write-intent judgement the dispatch_worker
            // tool runs — a writeless role without bash cannot satisfy an external
            // write order, so it is refused before mkdir/task.md/queue. A shell role
            // (`research`) is never refused here. Escape hatch: --allow-foreign-write.
            const writelessRole = isWritelessRole(typeField);
            const taskDir = workerTaskDir(agenticdocRoot, ownerKey, taskKey);
            if (writelessRole) {
                const verdict = judgeWriteIntent({
                    type: typeField,
                    description,
                    taskDir,
                    projectRoot: projectDir,
                    keyDir: path.join(agenticdocRoot, ownerKey),
                    trueRoot: agenticdocRoot,
                    allowForeignWrite: allowForeignWriteArg,
                });
                if (!verdict.ok) {
                    ctx.ui.notify(writeIntentRefusal({ taskKey, type: typeField, path: verdict.violations[0]?.path ?? "" }), "warning");
                    return;
                }
            }
            // Docs gate, phase-tiered (mw-worker-visibility-gate): same tier rule as
            // dispatch_worker — one phase read, reused by the frontmatter below.
            const ownerPhase = dispatchPhase(agenticdocRoot, ownerKey);
            const docGaps = dispatchDocGaps(agenticdocRoot, ownerKey, ownerPhase);
            if (docGaps.length > 0) {
                ctx.ui.notify(`Worker dispatch blocked ('${ownerKey}'): ${docGaps.join("; ")}. Generate the phase docs first or dispatch under _scratch.`, "warning");
                return;
            }
            // G-1 tool-layer envelope gate (T-02): same decision function as the
            // dispatch_worker tool — an incomplete/missing card refuses before
            // mkdir/task.md/queue with zero side effects.
            const cardGate = readDispatchCard({
                cardPath: cardArg,
                ownerKey,
                agenticdocRoot,
                projectDir,
            });
            if (!cardGate.ok) {
                ctx.ui.notify(dispatchCardRefusal(cardGate), "warning");
                return;
            }
            // Model plan before any write: a refusal must leave no task dir.
            const modelPlan = planDispatchFrontmatter({
                cwd: projectDir,
                cli,
                provider,
                taskType: typeField,
                phase: ownerPhase,
                description,
                images: imagesArg,
                model,
                modelReason,
                registry: ctx.modelRegistry,
                triageRun,
                // T-04d: owning key + the card's declared write face are the dispatch
                // facts the dp1 structured state needs (the rest comes from the plan).
                dp1: {
                    key: ownerKey,
                    writeFace: cardWriteFaceEntries(cardGate.sections),
                    allowForeignWrite: allowForeignWriteArg,
                },
            });
            if (!modelPlan.ok) {
                ctx.ui.notify(modelPlan.message, "warning");
                return;
            }
            // DP-1 ledger + (on disagreement) the one PM wake for this dispatch.
            emitDispatchTriage(pi, agenticdocRoot, modelPlan.triage);
            const written = writeDispatchTaskMd({ agenticdocRoot, ownerKey }, {
                taskKey,
                type: typeField,
                body: description,
                frontmatter: modelPlan.frontmatter,
                writeScope: writelessRole && isShellRole(typeField) ? renderDefaultWriteScope(ownerKey, taskKey) : undefined,
                // T-02/design §4: same claims-backed read budget as dispatch_worker.
                readScope: cardGate.caps === null ? undefined : claimReadScope(ownerKey, cardGate.claims),
                readFileCap: cardGate.caps?.fileCap,
                readByteCap: cardGate.caps?.byteCap,
                injectWriteSurface: writelessRole,
                allowForeignWrite: allowForeignWriteArg,
                card: { headerPath: cardGate.headerPath, sha256: cardGate.sha256, sections: cardGate.sections },
                // T-08/T-04c: the decision this dispatch ADOPTED (D-041). `suggest` and
                // unavailable advice carry no decision, so the bytes stay pre-T-08.
                decision: modelPlan.triage?.decision,
                // T-04d: record which dp1 state shape the child actually received.
                decisionTrace: modelPlan.triage?.stateTrace,
            });
            const taskMdPath = written.path;
            // Dispatch directly to _workers.parallel
            const outcome = await dispatchTask({ taskKey, status: "pending", cli, provider, model, taskPath: taskMdPath }, workerStore);
            if (!outcome.ok) {
                cleanupRefusedTaskDir(taskMdPath);
                ctx.ui.notify(writeFaceRefusalText(taskKey, outcome), "warning");
                return;
            }
            ctx.ui.notify(appendTriageReceipt(`Dispatched ${cli} worker (${taskKey}) under key '${ownerKey}' [type: ${typeField}, role: ${roleForTaskType(typeField)}, ${modelPlan.echo}].`, modelPlan.triage) + claimsReceiptLine(cardGate), "info");
        },
    });
}
/**
 * Render the RAG row exactly like `mw.py:_format_rag_doctor_line` (D-308): an
 * `error` wins, an empty `enabled` list yields the not-enabled form, otherwise
 * `enabled=<a, b>; probe=<name=reachable|unreachable, ...>; fingerprint=<first
 * 12>; skill=<status>` plus `; required_missing=N` when N > 0. Probe names are
 * sorted the same way (`sorted(probe.items())`). Pure, so the cross-language
 * text can be asserted byte-for-byte against the Python line for one JSON.
 */
export function formatRagDoctorLine(rag) {
    if (rag.error)
        return `rag: ERROR - ${rag.error}`;
    const enabled = rag.enabled ?? [];
    const skillStatus = rag.skill?.status ?? "unknown";
    if (enabled.length === 0)
        return `rag: not enabled (skill ${skillStatus})`;
    const probe = rag.probe ?? {};
    const state = Object.keys(probe)
        .sort()
        .map((name) => `${name}=${probe[name]?.reachable ? "reachable" : "unreachable"}`)
        .join(", ");
    const fingerprint = (rag.fingerprint ?? "").slice(0, 12);
    const rawRequired = rag.required_missing ?? 0;
    const requiredMissing = Number.isFinite(rawRequired) ? Math.trunc(rawRequired) : 0;
    const required = requiredMissing ? `; required_missing=${requiredMissing}` : "";
    return `rag: enabled=${enabled.join(", ")}; probe=${state}; fingerprint=${fingerprint}; skill=${skillStatus}${required}`;
}
/**
 * `mw.py doctor` prints its RAG row only when `mw.py:523` sees
 * `rag.exists or rag.enabled`. `_doctor_rag` always returns a dict, so a
 * presence test alone would add a `not enabled` row to a project with no RAG
 * config at all. Mirroring that gate keeps the window text equal to the
 * terminal text in both directions (D-308/AC-304).
 */
export function shouldShowRagDoctorRow(rag) {
    return rag !== undefined && (rag.exists === true || (rag.enabled?.length ?? 0) > 0);
}
/** Format a doctor JSON report as a readable Chinese summary (same data as
 * the CLI text output — the TS side never re-implements checks, AC-007). */
export function formatDoctorReport(report, fix) {
    const lines = [];
    const svc = report.service;
    lines.push(svc?.running ? `服务: 运行中 (PID ${svc.pid ?? "?"})` : "服务: 未运行");
    const proxyParts = (report.proxy ?? []).map((p) => `${p.route ?? "?"}/${p.port ?? "?"} ${p.listening ? "监听中" : "未监听"}`);
    if (proxyParts.length > 0)
        lines.push(`代理端口: ${proxyParts.join("; ")}`);
    const orphan = report.orphan_proxy;
    if (orphan?.detected) {
        const ports = (orphan.ports ?? []).map((p) => `${p.port} (PID ${(p.owner_pids ?? []).join(",") || "?"})`);
        lines.push(`孤儿代理: ${ports.join("; ")}（mw 未运行但端口被占，可启动 mw 接管或处置占用进程）`);
    }
    const log = report.launcher_log;
    if (log?.exists) {
        lines.push(`launcher 日志: ${log.error_count ?? 0} 个错误行${log.fatal ? "（含 FATAL）" : ""}`);
    }
    else {
        lines.push("launcher 日志: 无日志文件");
    }
    const queue = report.queue;
    lines.push(`队列: ${queue?.non_terminal?.length ?? 0} 个进行中任务，${queue?.stale_count ?? 0} 个 stale，${queue?.archived_total ?? 0} 条已归档`);
    // Worker liveness (mw doctor worker_liveness section — informational).
    // Stale workers are named so the PM sees which task is suspected hung.
    const liveness = report.worker_liveness ?? [];
    if (liveness.length > 0) {
        const alive = liveness.filter((v) => v.verdict === "alive").length;
        const stale = liveness.filter((v) => v.verdict === "stale").map((v) => v.task_key ?? "?");
        const noHb = liveness.filter((v) => v.verdict === "no-heartbeat").length;
        const parts = [`存活 ${alive}`];
        if (stale.length > 0)
            parts.push(`疑似挂起: ${stale.join(", ")}`);
        if (noHb > 0)
            parts.push(`无心跳 ${noHb}`);
        lines.push(`worker 活性: ${parts.join("; ")}`);
    }
    const credParts = (report.credentials?.routes ?? []).map((r) => `${r.route ?? "?"} ${r.available ? "可用" : "缺凭证"}`);
    if (credParts.length > 0)
        lines.push(`路由凭证: ${credParts.join("; ")}（以 mw 进程 env 为准）`);
    const bundle = report.bundle;
    if (bundle?.available) {
        lines.push(bundle.stale ? "扩展 bundle: 源码较新，建议 /mw build 重建" : "扩展 bundle: 最新");
    }
    // pi shellPath row (fresh-machine shell bootstrap; non-Windows reports
    // not-applicable and stays silent here).
    const piShell = report.pi_shell;
    if (piShell?.status === "ok") {
        lines.push(`pi shell: ${piShell.shell_path ?? "?"}`);
    }
    else if (piShell?.status && piShell.status !== "not-applicable") {
        lines.push(`pi shell: ${piShell.status} — ${piShell.detail ?? ""}`);
    }
    // Dispatch model defaults row (silent when nothing is configured).
    const dispatch = report.dispatch;
    if (dispatch?.exists) {
        if (dispatch.error) {
            lines.push(`派发模型: 配置错误 — ${dispatch.error}`);
        }
        else {
            const capabilities = dispatch.images ?? {};
            const roles = Object.entries(dispatch.models ?? {})
                .map(([role, value]) => `${role}=${value} images=${capabilities[role] || "unknown"}`)
                .join("; ");
            const window = dispatch.window_model || "（未记录）";
            lines.push(`派发模型: ${roles || "未设角色"}; 窗口模型 ${window}`);
        }
    }
    // RAG row (D-308), verbatim like the `mw.py doctor` text line. An older
    // mw.py without the `rag` key renders nothing here (and never throws).
    if (shouldShowRagDoctorRow(report.rag))
        lines.push(formatRagDoctorLine(report.rag));
    if (fix) {
        const applied = report.fix?.applied;
        lines.push(Array.isArray(applied) && applied.length > 0 ? `已自动修复: ${applied.join("; ")}` : "无可自动修复项");
    }
    const summary = report.summary;
    if (summary?.healthy) {
        lines.push("整体: 健康");
    }
    else {
        const issues = Array.isArray(summary?.issues) ? summary?.issues : [];
        lines.push(issues.length > 0 ? `整体: ${issues.length} 个问题 — ${issues.join("; ")}` : "整体: 未知");
    }
    const suggestions = Array.isArray(summary?.suggestions) ? summary?.suggestions : [];
    for (const s of suggestions)
        lines.push(`建议: ${s}`);
    return lines.join("\n");
}
/** Split a command line on whitespace, honoring double-quoted segments
 * (Windows paths with spaces). Exported for tests. */
export function splitCommandLine(line) {
    const out = [];
    let cur = "";
    let inQuote = false;
    let has = false;
    for (const ch of line) {
        if (ch === '"') {
            inQuote = !inQuote;
            has = true;
        }
        else if (!inQuote && /\s/.test(ch)) {
            if (has) {
                out.push(cur);
                cur = "";
                has = false;
            }
        }
        else {
            cur += ch;
            has = true;
        }
    }
    if (has)
        out.push(cur);
    return out;
}
/** Parse the flag tail of `/mw target set`. null when --game is missing or a
 * known flag has no value (unknown flags are ignored — mw.py validates). */
export function parseTargetSetFlags(parts) {
    const flags = { game: "" };
    for (let i = 0; i < parts.length; i++) {
        const m = /^--(game|engine|vcs|uproject)$/.exec(parts[i]);
        if (!m)
            continue;
        const value = parts[i + 1];
        if (value === undefined || value.startsWith("--"))
            return null;
        flags[m[1]] = value;
        i++;
    }
    if (!flags.game)
        return null;
    return flags;
}
/** /mw target — dual-workspace config from the pi window. Thin wrapper over
 * `mw.py target` (single source of parsing/validation/rendering); the runner
 * is injectable for tests. set/clear remind that dual mode applies on the
 * NEXT worker spawn — no serve restart needed (launcher resolves per spawn). */
export async function runMwTargetCommand(ctx, projectDir, argsText, runner = targetMw) {
    const parts = splitCommandLine(argsText);
    const action = parts[0] ?? "";
    if (action === "show" || action === "clear" || action === "on" || action === "off") {
        const r = runner(projectDir, [action]);
        ctx.ui.notify(r.ok ? r.output || `mw target ${action}: ok` : `mw target ${action} failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "set") {
        const flags = parseTargetSetFlags(parts.slice(1));
        if (!flags) {
            ctx.ui.notify("Usage: /mw target set --game <dir> [--engine <dir>] [--vcs git|p4|none] [--uproject <file>] — quote paths containing spaces", "warning");
            return;
        }
        const args = ["set", `--game=${flags.game}`];
        if (flags.engine !== undefined)
            args.push(`--engine=${flags.engine}`);
        if (flags.vcs !== undefined)
            args.push(`--vcs=${flags.vcs}`);
        if (flags.uproject !== undefined)
            args.push(`--uproject=${flags.uproject}`);
        const r = runner(projectDir, args);
        ctx.ui.notify(r.ok
            ? `${r.output}\nDual mode takes effect on the next worker spawn (no serve restart needed).`
            : `mw target set failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    ctx.ui.notify("Usage: /mw target show | set --game <dir> [--engine <dir>] [--vcs git|p4|none] [--uproject <file>] | clear | on | off", "warning");
}
/** Parse the flag tail of `/mw partition set`. null when --parent is missing
 * or a known flag has no value (unknown flags are ignored — mw.py validates). */
export function parsePartitionSetFlags(parts) {
    const flags = { parent: "", roots: [] };
    for (let i = 0; i < parts.length; i++) {
        const m = /^(--parent|--partition|--vcs|--root)$/.exec(parts[i]);
        if (!m)
            continue;
        const value = parts[i + 1];
        if (value === undefined || value.startsWith("--"))
            return null;
        if (m[1] === "--root") {
            flags.roots.push(value);
        }
        else {
            flags[m[1].slice(2)] = value;
        }
        i++;
    }
    if (!flags.parent)
        return null;
    return flags;
}
/** /mw partition — partition-workspace config from the pi window (mw-target-
 * partition D-010). Thin wrapper over `mw.py partition` (single source of
 * parsing/validation/rendering — the same entry point a direct CLI run hits,
 * so identical args ⇒ identical target.yml bytes); the runner is injectable
 * for tests. set/on remind that the mode applies on the NEXT worker spawn —
 * no serve restart needed (launcher resolves per spawn). */
export async function runMwPartitionCommand(ctx, projectDir, argsText, runner = partitionMw) {
    const parts = splitCommandLine(argsText);
    const action = parts[0] ?? "";
    if (action === "show" || action === "clear" || action === "on" || action === "off") {
        const r = runner(projectDir, [action]);
        ctx.ui.notify(r.ok ? r.output || `mw partition ${action}: ok` : `mw partition ${action} failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "set") {
        const flags = parsePartitionSetFlags(parts.slice(1));
        if (!flags) {
            ctx.ui.notify("Usage: /mw partition set --parent <dir> [--partition <dir>] [--root name=<dir> ...] [--vcs git|p4|none] — quote paths containing spaces", "warning");
            return;
        }
        const args = ["set", `--parent=${flags.parent}`];
        if (flags.partition !== undefined)
            args.push(`--partition=${flags.partition}`);
        if (flags.vcs !== undefined)
            args.push(`--vcs=${flags.vcs}`);
        for (const root of flags.roots)
            args.push(`--root=${root}`);
        const r = runner(projectDir, args);
        ctx.ui.notify(r.ok
            ? `${r.output}\nPartition mode takes effect on the next worker spawn (no serve restart needed).`
            : `mw partition set failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    ctx.ui.notify("Usage: /mw partition show | set --parent <dir> [--partition <dir>] [--root name=<dir> ...] [--vcs git|p4|none] | clear | on | off", "warning");
}
/** /mw model — dispatch model defaults from the pi window. Thin wrapper over
 * `mw.py model` (single source of parsing/validation/rendering); the runner is
 * injectable for tests. set/clear remind when the change takes effect:
 * worker roles on the next spawn (launcher resolves per spawn, no serve
 * restart), `main` at the next window start (session_start application).
 * `set-fallback`/`clear-fallback` edit the ordered per-task-type fallback
 * chain (mw-model-fallback-cli); the window face takes effect on the next
 * worker spawn too, since the launcher reads the chain per spawn. */
export async function runMwModelCommand(ctx, projectDir, argsText, runner = modelMw) {
    const parts = splitCommandLine(argsText);
    const action = parts[0] ?? "show";
    if (action === "show") {
        const r = runner(projectDir, ["show"]);
        ctx.ui.notify(r.ok ? r.output || "mw model show: ok" : `mw model show failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "set") {
        const role = parts[1];
        const value = parts[2];
        if (!role || !value || parts.length > 3) {
            ctx.ui.notify("Usage: /mw model set <role> <prefix/model> — roles: main, coding, review, research, vision, decide_prepare (e.g. /mw model set review timi/gpt-5.6-sol)", "warning");
            return;
        }
        // Earliest catch for a bad id (design D-010): a prefixed value names its
        // own route, so the registry can check it before Python writes the file
        // (a bare id keeps the task's route — not checkable here). Python stays
        // the single source for role/schema validation.
        const validation = validateModelValue(ctx.modelRegistry, "pi", "", value);
        if (!validation.ok) {
            ctx.ui.notify(validation.message, "error");
            return;
        }
        const r = runner(projectDir, ["set", role, value]);
        ctx.ui.notify(r.ok
            ? `${r.output}\nWorker roles apply on the next spawn (no serve restart); main applies at the next window start.`
            : `mw model set failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "clear") {
        const role = parts[1];
        if (!role || parts.length > 2) {
            ctx.ui.notify("Usage: /mw model clear <role|all>", "warning");
            return;
        }
        const r = runner(projectDir, ["clear", role]);
        ctx.ui.notify(r.ok ? r.output || "mw model clear: ok" : `mw model clear failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    if (action === "set-fallback" || action === "clear-fallback") {
        const taskType = parts[1];
        const expectsChain = action === "set-fallback";
        const chain = parts[2];
        if (!taskType || (expectsChain && (!chain || parts.length > 3)) || (!expectsChain && parts.length > 2)) {
            ctx.ui.notify(expectsChain
                ? "Usage: /mw model set-fallback <task-type> <prefix/model[,prefix/model...]> - 1..4 models, tried in order (e.g. /mw model set-fallback review timi/deepseek-v4.1-flash,zai/glm-5.3)"
                : "Usage: /mw model clear-fallback <task-type>", "warning");
            return;
        }
        // Thin wrapper: Python owns role/schema validation (same as set/clear).
        const args = expectsChain ? [action, taskType, chain] : [action, taskType];
        const r = runner(projectDir, args);
        ctx.ui.notify(r.ok ? r.output || `mw model ${action}: ok` : `mw model ${action} failed: ${r.error}`, r.ok ? "info" : "error");
        return;
    }
    ctx.ui.notify("Usage: /mw model show | set <role> <prefix/model> | clear <role|all> | set-fallback <task-type> <chain> | clear-fallback <task-type>", "warning");
}
/** /mw command description (exported so the registration test can assert the
 * RAG branch stays documented — VC-311). */
export const MW_COMMAND_DESCRIPTION = "Control mw: build / init / start / stop / restart / status / doctor / update / target / partition / model / decide / rag / stats / run-detached / ack";
/** Lines of `mw rag` output shown before truncation (D-307): the notify channel
 * is narrow, and `rag list` / `rag audit` outputs can be long. */
export const RAG_OUTPUT_MAX_LINES = 30;
/** Truncation footer (D-307): hand the user the exact command for the full
 * output instead of dropping it silently. `<sub>` / `<dir>` stay placeholders —
 * formatRagOutput only ever sees the output text. */
export const RAG_FULL_OUTPUT_HINT = "完整输出：python mw.py rag <sub> --project <dir>";
/**
 * Parse `/mw rag <raw>` into the subcommand and its verbatim argument tail.
 * Pure and CLI-free (VC-307): an empty or unknown sub returns the usage text
 * naming every RAG_SUBCOMMANDS entry, so the caller can reject before any
 * spawn. Arguments after the sub pass through untouched — Python stays the
 * single source of argument semantics.
 */
export function parseRagArgs(raw) {
    const usage = `Usage: /mw rag <sub> [args...] — sub: ${RAG_SUBCOMMANDS.join(" | ")}. Arguments are forwarded to mw.py rag verbatim.`;
    const parts = splitCommandLine(raw);
    const sub = parts[0] ?? "";
    if (!RAG_SUBCOMMANDS.includes(sub))
        return { usage };
    return { sub, rest: parts.slice(1) };
}
/**
 * Map a `mw.py rag` exit code to the notify level and shorten long output
 * (D-307): 0=info, 1=warning (audit findings are expected), anything else
 * error. Output over RAG_OUTPUT_MAX_LINES is truncated with the full-command
 * hint appended so nothing is lost.
 */
export function formatRagOutput(output, code) {
    const level = code === 0 ? "info" : code === 1 ? "warning" : "error";
    const text = output.replace(/\r\n/g, "\n").trim();
    if (text === "")
        return { text: code === 0 ? "mw rag: ok" : `mw rag exited with code ${code}`, level };
    const lines = text.split("\n");
    if (lines.length <= RAG_OUTPUT_MAX_LINES)
        return { text, level };
    return { text: `${lines.slice(0, RAG_OUTPUT_MAX_LINES).join("\n")}\n… ${RAG_FULL_OUTPUT_HINT}`, level };
}
/** /mw rag — thin wrapper over `mw.py rag` (single source of parsing,
 * validation and rendering); the runner is injectable for tests so the
 * unknown-sub path can be proven spawn-free (VC-307). The output content is
 * never parsed — only the exit code selects the notify level. */
export async function runMwRagCommand(ctx, projectDir, raw, runner = ragMw) {
    const parsed = parseRagArgs(raw);
    if ("usage" in parsed) {
        ctx.ui.notify(parsed.usage, "warning");
        return;
    }
    const result = runner(projectDir, [parsed.sub, ...parsed.rest]);
    const formatted = formatRagOutput(result.output, result.code);
    ctx.ui.notify(formatted.text, formatted.level);
}
/**
 * Parse `/mw run-detached [--cwd <dir>] [--run-dir <dir>]
 * [--timeout-min <n>] [--heartbeat-s <n>] -- <cmd...>`. Pure and CLI-free
 * (the rag VC-307 precedent): a missing `--`, an empty command, an unknown
 * flag, or a flag without a value returns a structured usage error so the
 * caller rejects before any spawn. The argv after `--` passes through
 * verbatim — shared/run-detached.ts (and Python) stays the single source of
 * flag semantics.
 */
export function parseRunDetachedArgs(raw) {
    const parts = splitCommandLine(raw);
    const flags = { cmd: [] };
    let i = 0;
    let afterSep = false;
    while (i < parts.length) {
        const part = parts[i] ?? "";
        if (afterSep) {
            flags.cmd.push(part);
            i++;
            continue;
        }
        if (part === "--") {
            afterSep = true;
            i++;
            continue;
        }
        const eq = part.indexOf("=");
        const flag = eq === -1 ? part : part.slice(0, eq);
        const inline = eq === -1 ? undefined : part.slice(eq + 1);
        if (flag === "--cwd" || flag === "--run-dir" || flag === "--timeout-min" || flag === "--heartbeat-s") {
            const value = inline ?? parts[i + 1];
            if (value === undefined || value === "") {
                return { ok: false, error: `Usage: /mw run-detached: ${flag} needs a value` };
            }
            if (flag === "--cwd")
                flags.cwd = value;
            else if (flag === "--run-dir")
                flags.run_dir = value;
            else if (flag === "--timeout-min") {
                const n = Number(value);
                if (Number.isNaN(n)) {
                    return { ok: false, error: `Usage: /mw run-detached: --timeout-min needs a number, got '${value}'` };
                }
                flags.timeout_min = n;
            }
            else {
                const n = Number(value);
                if (Number.isNaN(n)) {
                    return { ok: false, error: `Usage: /mw run-detached: --heartbeat-s needs a number, got '${value}'` };
                }
                flags.heartbeat_s = n;
            }
            i += eq === -1 ? 2 : 1;
            continue;
        }
        return {
            ok: false,
            error: `Usage: /mw run-detached: unknown option '${part}' — use --cwd/--run-dir/--timeout-min/--heartbeat-s and put the command after '--'`,
        };
    }
    if (!afterSep || flags.cmd.length === 0) {
        return { ok: false, error: "Usage: /mw run-detached: no command after '--'" };
    }
    return { ok: true, flags };
}
/** /mw run-detached — background command dispatch (D-005/AC-008). Thin wrapper
 * over shared/run-detached.ts; the runner is injectable for tests (the rag
 * precedent). The 4-field handoff summary matches the mw_run_detached tool
 * 文案 byte for byte; failures notify a structured error and never throw. */
export async function runMwRunDetachedCommand(ctx, projectDir, raw, runner = runDetachedMw) {
    const parsed = parseRunDetachedArgs(raw);
    if (!parsed.ok) {
        ctx.ui.notify(parsed.error, "warning");
        return;
    }
    const result = runner({ ...parsed.flags, cwd: parsed.flags.cwd ?? projectDir });
    if (!result.ok) {
        ctx.ui.notify(result.error, "error");
        return;
    }
    const { pid, marker, heartbeat, log } = result.handle;
    ctx.ui.notify(`dispatched pid=${pid} marker=${marker} heartbeat=${heartbeat} log=${log}`, "info");
}
/** /mw stats — thin wrapper over `mw.py stats` (mw-usage-monitor T-04/AC-006).
 * The window owns no aggregation: the raw argument tail passes through
 * untouched (`--since / --key / --type / --model / --source / --json` are
 * parsed by Python), the report is rendered by Python, and the runner is
 * injectable for tests (the rag precedent). A failure notifies at `error` with
 * the Python text verbatim — runMwCliRaw merges stderr into it, so the reason
 * (`invalid --since`, bad `--source`) is never swallowed. A thrown runner
 * (spawn-level bug) is reported the same way instead of escaping the command. */
export async function runMwStatsCommand(ctx, projectDir, raw, runner = statsMw) {
    const args = splitCommandLine(raw);
    let result;
    try {
        result = runner(projectDir, args);
    }
    catch (err) {
        ctx.ui.notify(`mw stats failed: ${err instanceof Error ? err.message : String(err)}`, "error");
        return;
    }
    ctx.ui.notify(result.ok ? result.output || "mw stats: ok" : `mw stats failed: ${result.error}`, result.ok ? "info" : "error");
}
/** Conclusions `mw decide sign` accepts (mirror of the Python
 * `decide_signoff.CONCLUSIONS`; only used to reject a typo before any spawn). */
export const DECIDE_CONCLUSIONS = ["continue", "narrow", "revoke"];
/** Usage line of the window face (the `--key` flag only exists on `sign`). */
export const DECIDE_USAGE = "Usage: /mw decide show | sign <continue|narrow|revoke> [--reason <text>] [--allow-empty] [--key <key>]";
/**
 * Parse `/mw decide [show | sign <conclusion> [flags]]`.
 *
 * `""` / `show` is the read-only preview; `sign <continue|narrow|revoke>`
 * accepts `--reason <text>`, `--allow-empty` and `--key <key>`. Everything else
 * (unknown sub, missing/invalid conclusion, a flag without a value, a stray
 * positional) returns a usage error so the caller rejects without a spawn —
 * Python stays the single source of the verdict and of the machine lines.
 */
export function parseDecideArgs(argsText) {
    const parts = splitCommandLine(argsText);
    const sub = parts[0] ?? "";
    if (sub === "" || sub === "show") {
        if (parts.length > 1) {
            return { action: "usage", error: `${DECIDE_USAGE} — \`show\` takes no arguments` };
        }
        return { action: "show" };
    }
    if (sub !== "sign") {
        return { action: "usage", error: `${DECIDE_USAGE} — unknown sub '${sub}'` };
    }
    const conclusion = parts[1];
    if (conclusion === undefined) {
        return { action: "usage", error: `${DECIDE_USAGE} — \`sign\` needs a conclusion` };
    }
    if (!DECIDE_CONCLUSIONS.includes(conclusion)) {
        return { action: "usage", error: `${DECIDE_USAGE} — invalid conclusion '${conclusion}'` };
    }
    let reason;
    let allowEmpty = false;
    let key;
    for (let i = 2; i < parts.length; i++) {
        const part = parts[i] ?? "";
        if (part === "--allow-empty") {
            allowEmpty = true;
            continue;
        }
        if (part === "--reason" || part === "--key") {
            const value = parts[i + 1];
            if (value === undefined || value === "" || value.startsWith("--")) {
                return { action: "usage", error: `${DECIDE_USAGE} — ${part} needs a value` };
            }
            if (part === "--reason")
                reason = value;
            else
                key = value;
            i++;
            continue;
        }
        return { action: "usage", error: `${DECIDE_USAGE} — unexpected argument '${part}'` };
    }
    return { action: "sign", conclusion, reason, allowEmpty, key };
}
/** Lines of raw preview output shown when the JSON cannot be parsed. */
export const DECIDE_ERROR_TAIL_LINES = 6;
function tailLines(text, max = DECIDE_ERROR_TAIL_LINES) {
    const lines = text.replace(/\r\n/g, "\n").trim().split("\n");
    return lines.slice(-max).join("\n");
}
/** Tolerant JSON read: the whole output first, then the outermost `{...}` — a
 * banner line before the JSON must not turn into an error notification. */
function parseDecidePreview(output) {
    const text = output.trim();
    const candidates = [text];
    const first = text.indexOf("{");
    const last = text.lastIndexOf("}");
    if (first !== -1 && last > first)
        candidates.push(text.slice(first, last + 1));
    for (const candidate of candidates) {
        try {
            const parsed = JSON.parse(candidate);
            if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
                return parsed;
            }
        }
        catch {
            // try the next candidate
        }
    }
    return null;
}
/** Render the preview facts the way `/mw decide show` prints them: the four
 * counts, the engine histogram, one verdict line per conclusion, the first 12
 * characters of `rows_sha256` and the open-P0 list. */
export function formatDecidePreview(payload) {
    const facts = payload.facts ?? {};
    const engines = Object.entries(facts.engines ?? {});
    const lines = [
        `counted_rows=${facts.counted_rows ?? 0} available=${facts.n_available ?? 0} acted=${facts.n_acted ?? 0} escalated=${facts.n_escalated ?? 0}`,
        `engines: ${engines.length > 0 ? engines.map(([name, count]) => `${name}=${count}`).join(", ") : "-"}`,
    ];
    for (const conclusion of DECIDE_CONCLUSIONS) {
        const verdict = payload.verdicts?.[conclusion];
        if (verdict === undefined) {
            lines.push(`verdict ${conclusion}: (mw decide sign --json reported none)`);
            continue;
        }
        lines.push(`verdict ${conclusion}: ${verdict.ok === false ? "REFUSED" : "ok"}`);
        for (const problem of verdict.problems ?? [])
            lines.push(`  - ${problem}`);
    }
    lines.push(`rows_sha256: ${(facts.sha256 ?? "").slice(0, 12) || "-"}`);
    lines.push(`p0-open: ${(facts.p0_open ?? []).join(", ") || "-"}`);
    return lines.join("\n");
}
/** The read-only preview argv (`--conclusion` omitted = nothing is written).
 * `--allow-empty` rides along so the reported verdicts match the sign intent. */
function decidePreviewArgs(key, allowEmpty) {
    const args = ["sign", "--key", key, "--json"];
    if (allowEmpty)
        args.push("--allow-empty");
    return args;
}
/**
 * `/mw decide show|sign` — the TUI face of the human sign-off (FIX-Q, user
 * ruling: option B).
 *
 * `show` runs the Python preview (`mw decide sign --key <k> --json`, which
 * writes nothing) and prints the facts. `sign` runs the same preview first,
 * refuses before any dialog when that conclusion's machine verdict does not
 * pass, and then asks `ctx.ui.confirm`; only a human confirmation forwards the
 * write with `--human-confirmed` (Python then records `signed_via: tui`). Guard
 * rails, in order:
 *   1. `ctx.hasUI !== true` refuses outright — headless / `-p` / rpc have no
 *      dialog, so there is no human click to collect and nothing to bypass;
 *   2. the key is `--key` > the watched key > a usage error (never guessed);
 *   3. Python stays authoritative: its verdict (exit 2, zero writes) still
 *      runs on the write call, so a preview/flag mismatch cannot fake success.
 * The runner is injectable so every branch is provable without a spawn.
 */
export async function runMwDecideCommand(ctx, projectDir, argsText, deps = {}) {
    if (ctx.hasUI !== true) {
        ctx.ui.notify("/mw decide 需要交互 TUI（headless / -p / rpc 一律拒）：签收必须有确认框里的一次人工点击。命令行请直接在终端跑 mw decide sign（agent 会话内会被拒）。", "warning");
        return;
    }
    const parsed = parseDecideArgs(argsText);
    if (parsed.action === "usage") {
        ctx.ui.notify(parsed.error, "warning");
        return;
    }
    const key = (parsed.action === "sign" ? parsed.key : undefined) ?? deps.watchKey?.();
    if (!key) {
        ctx.ui.notify(`${DECIDE_USAGE} — 无法确定 key，请给 --key <key>（或先 /worker watch <key>）`, "warning");
        return;
    }
    const allowEmpty = parsed.action === "sign" ? parsed.allowEmpty : false;
    const runner = deps.runner ?? decideMw;
    let preview;
    try {
        preview = runner(projectDir, decidePreviewArgs(key, allowEmpty));
    }
    catch (err) {
        ctx.ui.notify(`mw decide 预览失败: ${err instanceof Error ? err.message : String(err)}`, "error");
        return;
    }
    if (!preview.ok) {
        ctx.ui.notify(`mw decide 预览失败: ${preview.error}`, "error");
        return;
    }
    const payload = parseDecidePreview(preview.output);
    if (payload === null) {
        ctx.ui.notify(`mw decide 预览输出不是 JSON，原文尾部:\n${tailLines(preview.output)}`, "error");
        return;
    }
    if (parsed.action === "show") {
        ctx.ui.notify(`${formatDecidePreview(payload)}\n(preview only — nothing written; /mw decide sign <continue|narrow|revoke> 才写)`, "info");
        return;
    }
    const chosen = payload.verdicts?.[parsed.conclusion];
    const problems = chosen !== undefined ? (chosen.problems ?? []) : (payload.problems ?? []);
    const verdictOk = chosen !== undefined ? chosen.ok !== false : payload.ok !== false;
    if (!verdictOk || problems.length > 0) {
        ctx.ui.notify(`mw decide sign ${parsed.conclusion} 未通过机器行判据，未弹确认框、零写入:\n${problems.map((p) => `- ${p}`).join("\n")}`, "error");
        return;
    }
    const facts = payload.facts ?? {};
    const sha = (facts.sha256 ?? "").slice(0, 12) || "-";
    const confirmed = await ctx.ui.confirm(`确认签收 ${key}`, `conclusion=${parsed.conclusion} · counted_rows=${facts.counted_rows ?? 0} · rows_sha256=${sha}\n` +
        "确认后写入 evidence/review/sign-final.md（signed_via: tui）并追加一条 authority-change 档案行");
    if (!confirmed) {
        ctx.ui.notify("cancelled, nothing written", "info");
        return;
    }
    const writeArgs = ["sign", "--key", key, "--conclusion", parsed.conclusion, "--human-confirmed"];
    if (parsed.reason)
        writeArgs.push("--reason", parsed.reason);
    if (parsed.allowEmpty)
        writeArgs.push("--allow-empty");
    let written;
    try {
        written = runner(projectDir, writeArgs);
    }
    catch (err) {
        ctx.ui.notify(`mw decide sign ${parsed.conclusion} 写入失败: ${err instanceof Error ? err.message : String(err)}`, "error");
        return;
    }
    if (!written.ok) {
        ctx.ui.notify(`mw decide sign ${parsed.conclusion} 写入失败: ${written.error}`, "error");
        return;
    }
    const wrote = /^wrote (.+)$/m.exec(written.output)?.[1]?.trim();
    ctx.ui.notify(`已签收 ${key}（${parsed.conclusion}）→ ${wrote ?? `${key}/evidence/review/sign-final.md`}\n` +
        "authority-change 档案行已追加；key 目录存在 decision-scope.md 时，advance_phase.py 的 decision_signoff 检查现在可以推进。", "info");
}
export function registerMwCommands(pi, projectDir, workerStore, ackStore, watch, agenticdocRoot) {
    pi.registerCommand("mw", {
        description: MW_COMMAND_DESCRIPTION,
        handler: async (_args, ctx) => {
            const trimmed = _args.trim();
            const sub = trimmed.split(/\s+/)[0] ?? "status";
            if (sub === "build") {
                ctx.ui.notify("Rebuilding extension bundle (bash-free)…", "info");
                const r = buildMw();
                if (r.ok) {
                    ctx.ui.notify(`mw build OK — reinstalled globally. Restart pi windows to load it.\n${r.output}`, "info");
                }
                else {
                    ctx.ui.notify(`mw build failed: ${r.error}`, "error");
                }
                return;
            }
            if (sub === "init") {
                const result = initMw(projectDir);
                if (result.ok) {
                    ctx.ui.notify("mw init complete — .agenticdoc/ .mw/ .pi/extensions/ created.", "info");
                }
                else {
                    ctx.ui.notify(result.error, "error");
                }
                return;
            }
            if (sub === "doctor") {
                const fix = _args.trim().split(/\s+/)[1]?.toLowerCase() === "fix";
                const r = doctorMw(projectDir, fix);
                if (r.ok) {
                    ctx.ui.notify(formatDoctorReport(r.report, fix), "info");
                }
                else {
                    ctx.ui.notify(`mw doctor 执行失败: ${r.error}`, "error");
                }
                return;
            }
            if (sub === "update") {
                // Incremental self-check over the update anchors (UPDATE.md §1):
                // bundle / pi dist / serve / framework propagation. Python stays
                // the single source of the checks; --apply runs the safe fixes.
                const apply = _args.trim().split(/\s+/)[1]?.toLowerCase() === "--apply";
                ctx.ui.notify(apply
                    ? "mw update-env --apply running (bundle/dist rebuild + reinstall can take a minute)…"
                    : "mw update-env checking anchors…", "info");
                const r = updateEnvMw(projectDir, apply);
                ctx.ui.notify(r.ok ? r.output : `mw update-env 执行失败: ${r.error}`, r.ok ? "info" : "error");
                return;
            }
            if (sub === "status") {
                const s = getMwStatus(projectDir);
                if (!s.running) {
                    ctx.ui.notify("mw not running", "info");
                    return;
                }
                const stale = serveStaleness(projectDir);
                ctx.ui.notify(stale?.stale
                    ? `mw running (PID ${s.pid}) — STALE CODE (${stale.detail}). Run /mw restart.`
                    : `mw running (PID ${s.pid})`, stale?.stale ? "warning" : "info");
                return;
            }
            if (sub === "start") {
                const s = getMwStatus(projectDir);
                if (s.running) {
                    ctx.ui.notify(`mw already running (PID ${s.pid})`, "info");
                    return;
                }
                const ok = startMw(projectDir);
                ctx.ui.notify(ok ? "mw starting in background…" : "Could not find mw.py — set MW_PY env var.", ok ? "info" : "error");
                return;
            }
            if (sub === "stop") {
                const s = getMwStatus(projectDir);
                if (!s.running) {
                    ctx.ui.notify("mw is not running", "info");
                    return;
                }
                stopMw(projectDir);
                ctx.ui.notify("mw stop signal sent", "info");
                return;
            }
            if (sub === "restart") {
                ctx.ui.notify("mw restarting (graceful stop, then start)...", "info");
                const r = await restartMw(projectDir);
                if (r === "restarted") {
                    const s = getMwStatus(projectDir);
                    ctx.ui.notify(`mw restarted (PID ${s.pid ?? "?"}) — in-flight workers are adopted by the new launcher's orphan reconcile.`, "info");
                }
                else if (r === "stop-failed") {
                    ctx.ui.notify("mw restart failed: serve did not exit in time — run /mw doctor.", "error");
                }
                else {
                    ctx.ui.notify("mw restart failed: serve did not come up — run /mw doctor.", "error");
                }
                return;
            }
            if (sub === "target") {
                // Dual-workspace config (mw.py target show/set/clear/on/off) — thin
                // wrapper, Python stays the single source of parsing and validation.
                await runMwTargetCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "partition") {
                // Partition-workspace config (mw.py partition set/show/clear/on/off) —
                // thin wrapper, Python stays the single source of parsing and validation.
                await runMwPartitionCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "model") {
                // Dispatch model defaults + fallback chains (mw.py model show/set/clear/
                // set-fallback/clear-fallback) — thin wrapper, Python stays the single
                // source of parsing and validation.
                await runMwModelCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "decide") {
                // Decision archive + sign-off (FIX-Q): `show` is a read-only preview,
                // `sign` previews, asks ctx.ui.confirm and only then writes with the
                // --human-confirmed exemption (recorded as `signed_via: tui`). Python
                // stays the single source of the verdict and of the machine lines.
                await runMwDecideCommand(ctx, projectDir, trimmed.slice(sub.length).trim(), { watchKey: () => watch.key });
                return;
            }
            if (sub === "rag") {
                // RAG subcommands (list / probe / audit / sync / init) — thin wrapper,
                // Python stays the single source of parsing and validation; the exit
                // code keeps its 0/1/2 meaning (audit 1 = findings, not failure).
                await runMwRagCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "stats") {
                // Usage monitor (mw-usage-monitor AC-006): token + wall-clock
                // attribution over a time window — thin wrapper, Python owns the
                // ledger scan, the filters and the text report.
                await runMwStatsCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "run-detached") {
                // Background command dispatch (D-005/AC-008) — thin wrapper over
                // shared/run-detached.ts; parsing stays here (usage-first), the
                // handoff contract and spawn stay in the shared single source.
                await runMwRunDetachedCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
                return;
            }
            if (sub === "ack") {
                // Ack terminal worker results (AC-004): <task-key> acks one row,
                // all acks every unacked terminal row THIS WINDOW owns
                // (mw-task-scope-isolation — the sidecar is project-level, so an
                // unscoped "all" would clear another window's unhandled rows).
                // Running/pending rows are rejected with the reason — nothing is
                // written for them; foreign rows are rejected with the owning key.
                const target = _args.trim().split(/\s+/)[1] ?? "";
                if (!target) {
                    ctx.ui.notify("Usage: /mw ack <task-key> | all", "warning");
                    return;
                }
                const result = await ackTasks(workerStore, ackStore, target === "all" ? "all" : [target], {
                    watch,
                    agenticdocRoot,
                });
                if (result.acked.length > 0) {
                    ctx.ui.notify(`Acked ${result.acked.length} task(s): ${result.acked.join(", ")}`, "info");
                }
                for (const r of result.rejected)
                    ctx.ui.notify(`Not acked: ${r.key} — ${r.reason}`, "warning");
                if (result.acked.length === 0 && result.rejected.length === 0) {
                    ctx.ui.notify("No unacked terminal tasks.", "info");
                }
                return;
            }
            ctx.ui.notify("Usage: /mw build|init|start|stop|status|doctor [fix] | update [--apply] | target show|set|clear|on|off | partition show|set|clear|on|off | model show|set|clear|set-fallback|clear-fallback | decide show|sign <continue|narrow|revoke> [--reason <text>] [--allow-empty] [--key <k>] | rag <sub> | stats [--since <window>] [--key <k>] [--type <t>] [--model <m>] [--source worker|pm] [--json] | run-detached [--cwd <dir>] [--run-dir <dir>] [--timeout-min <n>] [--heartbeat-s <n>] -- <cmd...> | ack <task-key>|all", "warning");
        },
    });
}
//# sourceMappingURL=ui-bridge.js.map