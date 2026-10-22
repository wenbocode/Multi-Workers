/**
 * triage-client.ts — decision-point client for the pre-dispatch triage
 * (mw-jev-provider-integration T-03; mw-decision-substitution T-04; design
 * D-004/D-005/D-006/D-007 + D-019/D-021).
 *
 * Contract:
 * - Input is `(dpId, state)`: `dpId` selects the decision point and `state` is
 *   a **structured object** whose field table is frozen by D6 Q1.1 (L0
 *   enums/counters, L1 capped summaries). L2 content (credentials / user
 *   quotes / absolute paths / code) has **no place in the signature** — it is
 *   excluded by construction, not washed afterwards (D-019). The legacy
 *   free-form string state stays byte-compatible (`spec.md:162` compat clause)
 *   for callers that still send `buildTriageState` output; it is bounded to
 *   16KB exactly as before.
 * - Canonical serialisation = recursive key sort + compact separators, measured
 *   in UTF-8 bytes (D6 Q1.1/Q2.2). > {@link MAX_STRUCTURED_STATE_BYTES}
 *   triggers the two-stage truncation: drop optional L1 → halve required L1 →
 *   refuse `input-oversize`. A missing / wrongly typed / over-cap required
 *   field refuses with `input-incomplete`. Both refusals are **zero spawn** and
 *   set `escalate_to_human` (D-021: record it, never alert).
 * - The question set is authoritative in the Python decision registry
 *   (design §2.1 "问题集（TS 不再持有字面量）"), so the structured request
 *   carries no `questions` map. The legacy string path keeps forwarding the
 *   frozen DP-1 choice set so its bytes stay identical.
 * - `state_digest` is computed by Python (`sha256(canonical)[:16]`) and only
 *   passed through here — this module never hashes (D-004).
 * - The single egress point is **one** `JSON.stringify` of the request envelope
 *   in {@link triageDispatch}. It is pure serialisation: no redaction, no
 *   truncation, no hashing happens there.
 *
 * Unchanged hard rules (T-03):
 * - **Default off** (D-007): `.mw/decide.json` missing / invalid / `enabled !=
 *   true` / `points.dp1.enabled == false` means a complete bypass — this module
 *   then performs ZERO spawn and ZERO write.
 * - **Fail-soft** (D-004): every failure (missing mw.py, timeout, non-JSON
 *   stdout, non-zero exit, thrown exception) normalises to
 *   `available=false`, never throws, never affects the dispatch.
 * - **State on stdin only** (D-003): `state` rides the request JSON on stdin;
 *   the command line carries only `--project` / `--dp` / `--json`.
 * - **Spawn reuse** (D-001 / W1): the child is the existing `PYTHON_EXE` +
 *   `findMwPy()` resolution from `shared/mw-runner.ts` (MW_PY override,
 *   global-install sidecar, `-X utf8`), never a bare `spawn` with a guessed
 *   interpreter/path.
 * - **Single writer** (D-005): the structured evidence file
 *   `.agenticdoc/_autopilot/triage-decisions.jsonl` is written by the Python
 *   decision client only; this module never touches it.
 * - **Confidence provenance** (D-002/D-004): `confidence_source` is carried
 *   through verbatim; callers must label `model-self-report` as an unverified
 *   self-report that is NOT usable for gating.
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.js";
/** Hard client-side wall-clock budget for one `mw decide run` child (D-006). */
export const DEFAULT_TRIAGE_TIMEOUT_MS = 20_000;
/** Client-side canonical budget for a structured state (spec §5.4 / D6 Q1). */
export const MAX_STRUCTURED_STATE_BYTES = 2_000;
/** Largest free-form `state` string forwarded on the legacy path (design
 * D-004 `max_state_bytes`; kept below the Python default so a long task body
 * does not trip the server budget check). Structured states use
 * {@link MAX_STRUCTURED_STATE_BYTES} instead. */
export const MAX_TRIAGE_STATE_BYTES = 16_000;
/** Decision point id for the pre-dispatch triage (D-006). The Python registry
 * owns the id set and the question set; this module only holds ids — and they
 * are the **registry ids verbatim** (`decision_points.DP_REGISTRY`), never short
 * forms: a short id silently misses every dp-specific row below. The drift lock
 * in `test/suite/triage-client-state.test.ts` pins this against the registry. */
export const DP1_ID = "dp1-dispatch-type";
/** TS-local refusal reasons (they never come back from the Python response;
 * `decision.py`'s frozen 8-value reason set is untouched by them). */
export const TRIAGE_REASON_INPUT_INCOMPLETE = "input-incomplete";
export const TRIAGE_REASON_INPUT_OVERSIZE = "input-oversize";
export const CONFIDENCE_SOURCE_API = "api";
export const CONFIDENCE_SOURCE_MODEL_SELF_REPORT = "model-self-report";
/** Legacy DP-1 question set (D-006 wire shape).
 *
 * `spec.md:162` keeps the `isinstance(state, str)` branch byte-compatible, and
 * `mw.py:718` still requires a non-empty `questions` map in that request, so the
 * legacy path must keep forwarding exactly these choices. The **structured**
 * path does not use it: the question set is authoritative in the Python
 * decision registry (design §2.1). Delete this constant together with the
 * legacy branch once Python fills `questions` from the registry. */
export const DP1_QUESTIONS = {
    triage_type: { type: "choice", choices: ["coding", "research", "review"] },
    triage_risk: { type: "choice", choices: ["low", "mid", "high"] },
};
/** `questions_version` for dp1 = `q-<sha256(canonical questions)[:8]>`, exactly
 * `decision_points._questions_version()` for the registry's dp1 question set
 * (`q-09d3aad3` today). Derived from {@link DP1_QUESTIONS} instead of hardcoded
 * so the two cannot drift; the canonical form is Python's
 * `json.dumps(list(questions), ensure_ascii=False, sort_keys=True,
 * separators=(",", ":"))` — the same mirror `pm-orchestrator.ts` uses for dp2.
 *
 * A structured dp1 state must carry this value or `decide_for` refuses it as
 * `input-incomplete` (registry `REQUIRED_STATE_FIELDS`). */
export const DP1_QUESTIONS_VERSION = `q-${createHash("sha256")
    .update(JSON.stringify(Object.entries(DP1_QUESTIONS).map(([id, spec]) => ({ choices: spec.choices, id, type: spec.type }))), "utf8")
    .digest("hex")
    .slice(0, 8)}`;
const DISABLED_POLICY = {
    enabled: false,
    dp1Enabled: true,
    alertOnDisagreement: true,
    notifyOnUnavailable: false,
    timeoutMs: DEFAULT_TRIAGE_TIMEOUT_MS,
};
/** Read `<projectDir>/.mw/decide.json` fail-soft (design D-007): a missing,
 * unreadable, non-object or `enabled != true` file is the "fully off" policy.
 * Read-only — this module never writes config. */
export function readDecidePolicy(projectDir) {
    let raw;
    try {
        raw = JSON.parse(fs.readFileSync(path.join(projectDir, ".mw", "decide.json"), "utf8"));
    }
    catch {
        return { ...DISABLED_POLICY };
    }
    if (raw === null || typeof raw !== "object" || Array.isArray(raw))
        return { ...DISABLED_POLICY };
    const obj = raw;
    if (obj.enabled !== true)
        return { ...DISABLED_POLICY };
    const points = asRecord(obj.points);
    const dp1 = asRecord(points?.dp1);
    const timeoutS = typeof obj.timeout_s === "number" && Number.isFinite(obj.timeout_s) && obj.timeout_s > 0
        ? obj.timeout_s
        : undefined;
    return {
        enabled: true,
        dp1Enabled: dp1?.enabled !== false,
        alertOnDisagreement: dp1?.alert_on_disagreement !== false,
        notifyOnUnavailable: obj.triage_notify_on_unavailable === true,
        timeoutMs: timeoutS === undefined ? DEFAULT_TRIAGE_TIMEOUT_MS : Math.round(timeoutS * 1000),
    };
}
function asRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value)
        ? value
        : undefined;
}
/** The real child: reuse mw-runner's interpreter/path resolution and the
 * no-window contract (`windowsHide`) plus `-X utf8` for the Chinese
 * diagnostics (design D-001; `agentic-scripts.ts:65-71` precedent). */
export const runDecideMw = (request) => {
    const mwPy = findMwPy();
    if (!mwPy)
        return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
    const args = ["-X", "utf8", mwPy, "decide", "run", `--project=${request.projectDir}`, "--dp", request.dp, "--json"];
    try {
        const result = spawnSync(PYTHON_EXE, args, {
            input: request.input,
            encoding: "utf8",
            timeout: request.timeoutMs,
            windowsHide: true,
        });
        const code = result.error?.code;
        return {
            status: result.status,
            stdout: result.stdout ?? "",
            stderr: result.stderr ?? "",
            error: result.error ? result.error.message : undefined,
            timedOut: code === "ETIMEDOUT",
        };
    }
    catch (err) {
        return {
            status: null,
            stdout: "",
            stderr: "",
            error: err instanceof Error ? err.message : String(err),
            timedOut: false,
        };
    }
};
function unavailable(reason, latencyMs = 0, digest) {
    const result = {
        available: false,
        reason,
        confidences: {},
        confidence_source: "unknown",
        latency_ms: latencyMs,
    };
    if (digest !== undefined)
        result.state_digest = digest;
    return result;
}
/** Zero-spawn refusal: the state was never put on the wire, so the caller has
 * to bring a human in (design D-021; no alert, only a ledger/notice line). */
function refused(reason, missing, dropped) {
    const result = {
        available: false,
        reason,
        confidences: {},
        confidence_source: "unknown",
        latency_ms: 0,
        escalate_to_human: true,
    };
    if (missing.length > 0)
        result.missing_fields = missing;
    if (dropped.length > 0)
        result.dropped_fields = dropped;
    return result;
}
// ── Structured state: field table, validation, canonical bytes, truncation ──
/** Top-level schema keys (D6 Q1.1). An unknown top-level key is rejected
 * outright: the TS side is the producer, and this is also what keeps L2 blobs
 * (`description`, code, transcripts) out — they have no legal key to ride. */
const STATE_TOP_LEVEL_KEYS = new Set([
    "schema_version",
    "decision_point",
    "key",
    "task_key",
    "phase",
    "task_type",
    "requested_type",
    "risk",
    "risk_source",
    "authority_tier",
    "questions_version",
    "task_summary",
    "scope",
    "progress",
    "failure",
    "ambiguity",
    // `local_candidates` feeds a dynamic-choice question's enum (dp3): it is
    // input data, not part of the question set, so it is a legal top-level key.
    "local_candidates",
    // `context` is the optional AC-017 block (task excerpt / change summary /
    // candidate snippets / artifact status / error excerpt). It carries the
    // engineering-context slots the decide model needs, so it is a legal
    // top-level key even though it is never required.
    "context",
    "closure",
    "history",
]);
/** Required for every dp (D6 Q5.1 "必需" = present, right type, in enum, in cap:
 * missing / wrong type / out of enum / over cap are all equivalent refusals). */
const UNIVERSAL_REQUIRED_FIELDS = [
    "schema_version",
    "decision_point",
    "key",
    "phase",
    "task_type",
    "risk",
    "risk_source",
    "authority_tier",
    "questions_version",
];
/** `required_if` matrix (D6 Q5.1): each dp only carries its own block.
 *
 * Keys are **canonical ids from `packages/multi-workers/decision_points.py`
 * `DP_REGISTRY`** — the registry owns the id set, so a short form (`dp1`,
 * `dp3-clarify`) would never match a real dpId and `?? []` would silently drop
 * the whole dp-specific requirement. Exported only so the cross-layer drift
 * lock can assert every key against the live registry. */
export const REQUIRED_FIELDS_BY_DP = {
    [DP1_ID]: ["requested_type", "task_summary", "scope.write_scope", "scope.file_extensions"],
    "dp2-checkpoint-split": [
        "progress.elapsed_minutes",
        "progress.budget_minutes",
        "progress.phases_done",
        "progress.phases_total",
        "progress.artifact_present",
    ],
    "dp3-worker-clarify": ["task_summary", "ambiguity.kind", "ambiguity.question", "local_candidates"],
    "dp4-failure-handling": ["failure.kind"],
    "dp5-test-triage": ["failure.kind", "failure.test_name", "failure.baseline_known"],
    "dp6-qg-verdict": ["closure"],
    "dp13-commit-release": ["closure"],
};
const TASK_TYPE_CHOICES = ["coding", "research", "review"];
const RISK_CHOICES = ["low", "mid", "high"];
const RISK_SOURCE_CHOICES = ["machine", "pm-label"];
const AUTHORITY_TIER_CHOICES = ["P0", "P1", "P2"];
const FAILURE_KIND_CHOICES = ["model-error", "wall-timeout", "exit-nonzero", "needs-clarification", "lost"];
const AMBIGUITY_KIND_CHOICES = ["scope", "missing-dep", "rule-conflict"];
function utf8Bytes(text) {
    return Buffer.byteLength(text, "utf8");
}
function stringField(maxBytes) {
    return (value) => {
        if (typeof value !== "string" || value.trim() === "")
            return "must be a non-empty string";
        if (maxBytes > 0 && utf8Bytes(value) > maxBytes)
            return `must be <= ${maxBytes} UTF-8 bytes`;
        return undefined;
    };
}
function enumField(choices) {
    return (value) => typeof value === "string" && choices.includes(value) ? undefined : `must be one of ${choices.join("|")}`;
}
function intField(value) {
    return typeof value === "number" && Number.isInteger(value) ? undefined : "must be an integer";
}
function intOrNullField(value) {
    return value === null ? undefined : intField(value);
}
function boolField(value) {
    return typeof value === "boolean" ? undefined : "must be a boolean";
}
function objectField(value) {
    return asRecord(value) === undefined ? "must be an object" : undefined;
}
function stringListField(maxItems, maxItemBytes, maxTotalBytes) {
    return (value) => {
        if (!Array.isArray(value) || value.length === 0)
            return "must be a non-empty string array";
        if (value.length > maxItems)
            return `must have <= ${maxItems} items`;
        let total = 0;
        for (const item of value) {
            if (typeof item !== "string" || item.trim() === "")
                return "items must be non-empty strings";
            const size = utf8Bytes(item);
            if (size > maxItemBytes)
                return `items must be <= ${maxItemBytes} UTF-8 bytes`;
            total += size;
        }
        if (total > maxTotalBytes)
            return `items must total <= ${maxTotalBytes} UTF-8 bytes`;
        return undefined;
    };
}
const TEST_NAME_PATTERN = /^[A-Za-z_$][\w$]*$/;
/** Dynamic-choice candidate ids (`decision_points._DYNAMIC_CHOICE_ID_RE`). */
const LOCAL_CANDIDATE_ID_PATTERN = /^c[1-9]$/;
const LOCAL_CANDIDATES_MAX = 5;
const LOCAL_CANDIDATE_LABEL_MAX = 80;
/** `local_candidates`: the enum source of a `dynamic_choices` question. Mirrors
 * Python's `decision_points.dynamic_choices_value_error` — `[{id: "cN", label}]`,
 * 1..5 items, ids contiguous from `c1`, non-empty single-line label <= 80 chars;
 * an illegal list must be refused (input-incomplete), never half-sent. */
function localCandidatesField(value) {
    if (!Array.isArray(value) || value.length === 0)
        return "must be a non-empty array";
    if (value.length > LOCAL_CANDIDATES_MAX)
        return `must have <= ${LOCAL_CANDIDATES_MAX} items`;
    for (let index = 0; index < value.length; index += 1) {
        const candidate = asRecord(value[index]);
        if (!candidate)
            return `items[${index}] must be an object`;
        const id = candidate.id;
        if (typeof id !== "string" || !LOCAL_CANDIDATE_ID_PATTERN.test(id)) {
            return `items[${index}].id must be cN (c1..c9)`;
        }
        if (id !== `c${index + 1}`)
            return `items[${index}].id must be contiguous from c1`;
        const label = candidate.label;
        if (typeof label !== "string" || label.trim() === "") {
            return `items[${index}].label must be a non-empty string`;
        }
        if (label.includes("\n") || label.includes("\r")) {
            return `items[${index}].label must not contain a newline`;
        }
        if (label.length > LOCAL_CANDIDATE_LABEL_MAX) {
            return `items[${index}].label must be <= ${LOCAL_CANDIDATE_LABEL_MAX} chars`;
        }
    }
    return undefined;
}
/** Per-field type/enum/cap checks (D6 Q1.1 budgets). Dotted names are read with
 * {@link readPath}; block presence itself is checked where the dp requires it. */
const FIELD_VALIDATORS = {
    // Schema version 2 == the registry builder's
    // `{"schema_version": 2, "decision_point": <id>}` shape
    // (`decision_points._state_builder`). Bumping one side alone is a refusal.
    schema_version: (value) => (value === 2 ? undefined : "must be the integer 2"),
    // The dp id set is authoritative in the Python registry: only shape and the
    // envelope equality are checked here, never a duplicated id enum. The 20B cap
    // is the longest registry id (`dp2-checkpoint-split` / `dp4-failure-handling`)
    // — a longer id must surface as a refusal, not as a silently unmatched row.
    decision_point: stringField(20),
    key: stringField(48),
    task_key: stringField(48),
    phase: stringField(16),
    task_type: enumField(TASK_TYPE_CHOICES),
    requested_type: enumField(TASK_TYPE_CHOICES),
    risk: enumField(RISK_CHOICES),
    risk_source: enumField(RISK_SOURCE_CHOICES),
    authority_tier: enumField(AUTHORITY_TIER_CHOICES),
    questions_version: stringField(24),
    task_summary: stringField(600),
    scope: objectField,
    "scope.write_scope": stringListField(12, 32, 384),
    "scope.file_extensions": stringListField(6, 8, 36),
    "scope.images_required": boolField,
    progress: objectField,
    "progress.elapsed_minutes": intField,
    "progress.budget_minutes": intField,
    "progress.phases_done": intField,
    "progress.phases_total": intField,
    "progress.artifact_present": boolField,
    "progress.writes": intOrNullField,
    "progress.uniq_targets": intOrNullField,
    "progress.repeat_top": intOrNullField,
    "progress.last_land_age_min": intOrNullField,
    failure: objectField,
    "failure.kind": enumField(FAILURE_KIND_CHOICES),
    "failure.exit": intField,
    "failure.attempts": intField,
    "failure.summary": stringField(300),
    "failure.test_name": (value) => typeof value === "string" && TEST_NAME_PATTERN.test(value) && utf8Bytes(value) <= 64
        ? undefined
        : "must be an identifier (<= 64 bytes)",
    "failure.baseline_known": boolField,
    ambiguity: objectField,
    "ambiguity.kind": enumField(AMBIGUITY_KIND_CHOICES),
    "ambiguity.question": stringField(300),
    local_candidates: localCandidatesField,
    closure: objectField,
    "closure.blockers_count": intField,
    "closure.evidence_present": boolField,
    "closure.blockers": stringListField(3, 200, 600),
    "closure.blockers_kind": stringListField(3, 40, 120),
    history: objectField,
    "history.recent_done": intField,
    "history.recent_failed": intField,
    "history.recent_lost": intField,
    "history.recent_needs_clarification": intField,
    "history.recent_superseded": intField,
};
function readPath(state, dotted) {
    let current = state;
    for (const part of dotted.split(".")) {
        const record = asRecord(current);
        if (!record)
            return undefined;
        current = record[part];
    }
    return current;
}
/** Cross-field consistency (D6 Q5.2) — every violation is a refusal. */
function crossFieldProblems(state) {
    const problems = [];
    // P0 = permanently human (DS-1); a P0 decision point is short-circuited by
    // construction, so it never reaches the service.
    if (state.authority_tier === "P0")
        problems.push("authority_tier:P0");
    const failure = asRecord(state.failure);
    if (failure) {
        const hasExit = failure.exit !== undefined;
        if (failure.kind === "exit-nonzero" && !hasExit)
            problems.push("failure.exit");
        if (failure.kind !== "exit-nonzero" && hasExit)
            problems.push("failure.exit");
    }
    const progress = asRecord(state.progress);
    if (progress && typeof progress.elapsed_minutes === "number" && typeof progress.budget_minutes === "number") {
        // machine risk: over budget can never be `low` (computeRisk, worker-mode.ts)
        if (progress.elapsed_minutes > progress.budget_minutes && state.risk === "low")
            problems.push("risk");
    }
    return problems;
}
/** Required-field refusal list for one dp: field names only (L0). An empty
 * array means the state is sendable. */
export function validateStructuredState(dpId, state) {
    if (state === null || typeof state !== "object" || Array.isArray(state))
        return ["state"];
    const problems = [];
    for (const key of Object.keys(state)) {
        if (!STATE_TOP_LEVEL_KEYS.has(key))
            problems.push(`unknown:${key}`);
    }
    // The envelope dp and the state decision point must agree (one decision,
    // one digest).
    if (typeof state.decision_point === "string" && state.decision_point !== dpId) {
        problems.push("decision_point");
    }
    const required = [...UNIVERSAL_REQUIRED_FIELDS, ...(REQUIRED_FIELDS_BY_DP[dpId] ?? [])];
    for (const field of required) {
        const value = readPath(state, field);
        if (value === undefined) {
            problems.push(field);
            continue;
        }
        if (FIELD_VALIDATORS[field]?.(value) !== undefined)
            problems.push(field);
    }
    // Optional fields are validated when present: a present-but-wrong value is
    // never silently dropped, it is a refusal (D6 Q5.1 禁静默).
    for (const [field, validate] of Object.entries(FIELD_VALIDATORS)) {
        if (required.includes(field))
            continue;
        const value = readPath(state, field);
        if (value === undefined)
            continue;
        if (validate(value) !== undefined)
            problems.push(field);
    }
    problems.push(...crossFieldProblems(state));
    return [...new Set(problems)];
}
/** Canonical form (D6 Q2.2): recursive key sort + compact separators, raw
 * non-ASCII. Only the `state` sub-object is canonicalised; the outer envelope
 * is plain `JSON.stringify` because Python re-serialises after `json.loads`. */
function canonicalize(value) {
    if (Array.isArray(value))
        return value.map(canonicalize);
    const record = asRecord(value);
    if (!record)
        return value;
    const out = {};
    for (const key of Object.keys(record).sort())
        out[key] = canonicalize(record[key]);
    return out;
}
export function canonicalStateJson(state) {
    return JSON.stringify(canonicalize(state));
}
/** UTF-8 byte length of the canonical state — the number the ≤2000B budget
 * (and Python's own `_encode_state` check) is measured in. Length only: this
 * module never hashes (D-004). */
export function canonicalStateBytes(state) {
    return Buffer.byteLength(canonicalStateJson(state), "utf8");
}
/** Code-point-safe UTF-8 truncation (never splits a surrogate pair and never
 * produces invalid JSON — we truncate values, never the serialised string). */
function truncateUtf8(text, maxBytes) {
    if (utf8Bytes(text) <= maxBytes)
        return text;
    let out = "";
    let used = 0;
    for (const char of text) {
        const size = utf8Bytes(char);
        if (used + size > maxBytes)
            break;
        out += char;
        used += size;
    }
    return out;
}
function shrinkList(state, parent, key, limit) {
    const container = asRecord(state[parent]);
    if (!container)
        return false;
    const list = container[key];
    if (!Array.isArray(list) || list.length <= limit)
        return false;
    container[key] = list.slice(0, limit);
    return true;
}
function removeOptionalProgressKeys(state) {
    const progress = asRecord(state.progress);
    if (!progress)
        return false;
    let changed = false;
    for (const key of ["writes", "uniq_targets", "repeat_top", "last_land_age_min"]) {
        if (key in progress) {
            delete progress[key];
            changed = true;
        }
    }
    return changed;
}
function removeField(state, parent, key) {
    const container = parent === undefined ? state : asRecord(state[parent]);
    if (!container || !(key in container))
        return false;
    delete container[key];
    return true;
}
function truncateField(state, parent, key, maxBytes) {
    const container = parent === undefined ? state : asRecord(state[parent]);
    if (!container)
        return false;
    const value = container[key];
    if (typeof value !== "string")
        return false;
    const next = truncateUtf8(value, maxBytes);
    if (next === value)
        return false;
    container[key] = next;
    return true;
}
/** Two-stage truncation (D6 Q1.4), deterministic and never dropping a required
 * field: stage 1 drops/shrinks optional L1 blocks, stage 2 halves the required
 * L1 summaries, and if the state is still over budget the caller must refuse.
 * The input object is never mutated. */
export function truncateStructuredState(state, maxBytes = MAX_STRUCTURED_STATE_BYTES) {
    const work = JSON.parse(JSON.stringify(state));
    const dropped = [];
    let size = canonicalStateBytes(work);
    const steps = [
        // Stage 1 — optional L1, lowest decision value first.
        { label: "history", apply: () => removeField(work, undefined, "history") },
        { label: "closure.blockers", apply: () => shrinkList(work, "closure", "blockers", 2) },
        { label: "closure.blockers_kind", apply: () => shrinkList(work, "closure", "blockers_kind", 2) },
        { label: "closure.blockers", apply: () => shrinkList(work, "closure", "blockers", 1) },
        { label: "closure.blockers_kind", apply: () => shrinkList(work, "closure", "blockers_kind", 1) },
        { label: "closure.blockers", apply: () => removeField(work, "closure", "blockers") },
        { label: "scope.write_scope", apply: () => shrinkList(work, "scope", "write_scope", 6) },
        { label: "scope.write_scope", apply: () => shrinkList(work, "scope", "write_scope", 3) },
        {
            label: "progress.writes/uniq_targets/repeat_top/last_land_age_min",
            apply: () => removeOptionalProgressKeys(work),
        },
        { label: "failure.summary", apply: () => removeField(work, "failure", "summary") },
        // Stage 2 — required L1: shrink to half of the D6 cap, never drop.
        { label: "task_summary", apply: () => truncateField(work, undefined, "task_summary", 300) },
        { label: "ambiguity.question", apply: () => truncateField(work, "ambiguity", "question", 150) },
    ];
    for (const step of steps) {
        if (size <= maxBytes)
            break;
        if (!step.apply())
            continue;
        dropped.push(step.label);
        size = canonicalStateBytes(work);
    }
    return { state: work, dropped, bytes: size, oversize: size > maxBytes };
}
/** Validate → canonicalise → bound, in that order. A refusal means ZERO spawn. */
export function prepareStructuredState(dpId, state, maxBytes = MAX_STRUCTURED_STATE_BYTES) {
    const missing = validateStructuredState(dpId, state);
    if (missing.length > 0) {
        return { ok: false, reason: TRIAGE_REASON_INPUT_INCOMPLETE, missing, dropped: [] };
    }
    let truncation;
    try {
        truncation = truncateStructuredState(state, maxBytes);
    }
    catch {
        // Non-JSON-native value (cycle, BigInt, ...) — never guess at a wire form.
        return { ok: false, reason: TRIAGE_REASON_INPUT_INCOMPLETE, missing: ["state:serializable"], dropped: [] };
    }
    if (truncation.oversize) {
        return { ok: false, reason: TRIAGE_REASON_INPUT_OVERSIZE, missing: [], dropped: truncation.dropped };
    }
    // Hand over the canonical form so the bytes measured here are exactly the
    // bytes Python re-serialises (D6 Q2.2); the egress point stays a plain
    // `JSON.stringify` of an already-clean object.
    return {
        ok: true,
        state: canonicalize(truncation.state),
        bytes: truncation.bytes,
        dropped: truncation.dropped,
    };
}
// ── Legacy string state (byte-compatible, spec §5.4 compat clause) ──────────
/** Build the DP-1 `state` string from the dispatch-time inputs (D-006 legacy
 * path; the structured path uses a caller-built object instead). */
export function buildTriageState(input) {
    const lines = [`requested_type: ${input.taskType}`, `cli: ${input.cli}`];
    if (input.phase)
        lines.push(`owner_phase: ${input.phase}`);
    lines.push("", "task:", input.description);
    return lines.join("\n");
}
/** Bound the legacy `state` payload so a long task body cannot trip the Python
 * `max_state_bytes` budget (fail-soft: the advice is skipped, not the
 * dispatch). Byte-accurate because the Python side measures UTF-8 bytes. */
export function boundTriageState(state, maxBytes = MAX_TRIAGE_STATE_BYTES) {
    if (Buffer.byteLength(state, "utf8") <= maxBytes)
        return state;
    let text = state;
    while (Buffer.byteLength(text, "utf8") > maxBytes - 16 && text.length > 0) {
        text = text.slice(0, Math.floor(text.length * 0.9));
    }
    return `${text}\n[state truncated]`;
}
function parseJsonPayload(stdout) {
    const trimmed = stdout.trim();
    const attempts = [trimmed];
    const lastLine = trimmed.split("\n").at(-1);
    if (lastLine !== undefined && lastLine !== trimmed)
        attempts.push(lastLine.trim());
    for (const text of attempts) {
        if (!text)
            continue;
        try {
            const parsed = JSON.parse(text);
            if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
                return parsed;
            }
        }
        catch {
            // try the next candidate
        }
    }
    return undefined;
}
function answerOf(answers, id) {
    const entry = asRecord(answers?.[id]);
    if (!entry)
        return undefined;
    const rawValue = entry.value;
    const value = typeof rawValue === "string" && rawValue.trim() !== "" ? rawValue.trim() : undefined;
    const rawConfidence = entry.confidence;
    const confidence = typeof rawConfidence === "number" && Number.isFinite(rawConfidence)
        ? Math.min(1, Math.max(0, rawConfidence))
        : null;
    if (value === undefined && confidence === null)
        return undefined;
    return { value, confidence };
}
function digestOf(payload) {
    const raw = payload.state_digest;
    return typeof raw === "string" && raw.trim() !== "" ? raw.trim() : undefined;
}
/** Copy the four authority keys the child added in T-02b onto a result.
 *
 * Purely structural: a missing / `null` / wrongly typed value stays absent (no
 * `mode=auto`, no `acted=false` fabrication), and `escalated_reason` is NOT
 * written into `reason` — the legacy reason keeps its frozen vocabulary and the
 * two coexist (D-036/D-041). `mode` is the only value shape-restricted field:
 * anything outside `auto|suggest` is not forwarded. */
function applyAuthorityKeys(target, payload) {
    const decisionId = payload.decision_id;
    if (typeof decisionId === "string")
        target.decision_id = decisionId;
    const mode = payload.mode;
    if (mode === "auto" || mode === "suggest")
        target.mode = mode;
    const acted = payload.acted;
    if (typeof acted === "boolean")
        target.acted = acted;
    const escalatedReason = payload.escalated_reason;
    if (typeof escalatedReason === "string")
        target.escalated_reason = escalatedReason;
}
// ── The one client entry point ───────────────────────────────────────────────
/** Run one decision point. Never throws; a non-enabled policy is a `disabled`
 * no-op that performs no spawn. */
export function triageDispatch(input) {
    const started = Date.now();
    try {
        const policy = input.policy ?? readDecidePolicy(input.projectDir);
        if (!policy.enabled || !policy.dp1Enabled)
            return unavailable("disabled");
        const dpId = input.dpId ?? input.dp ?? DP1_ID;
        let envelope;
        let droppedFields = [];
        if (typeof input.state === "string") {
            // Legacy path — frozen bytes (spec §5.4 compat clause): bounded text
            // plus the frozen question map, exactly as before T-04.
            envelope = { state: boundTriageState(input.state), questions: DP1_QUESTIONS };
        }
        else {
            // Structured path — validate/refuse before any spawn, then bound.
            const prepared = prepareStructuredState(dpId, input.state);
            if (!prepared.ok)
                return refused(prepared.reason, prepared.missing, prepared.dropped);
            droppedFields = prepared.dropped;
            // Question-set authority is the Python registry (design §2.1), so the
            // envelope carries the state only.
            envelope = { state: prepared.state };
        }
        const run = input.run ?? runDecideMw;
        const request = {
            projectDir: input.projectDir,
            dp: dpId,
            timeoutMs: input.timeoutMs ?? policy.timeoutMs,
            // Single egress point: pure serialisation, no redaction, no hashing.
            input: JSON.stringify(envelope),
        };
        let raw;
        try {
            raw = run(request);
        }
        catch {
            return unavailable("upstream-error", Date.now() - started);
        }
        if (raw.timedOut)
            return unavailable("timeout", Date.now() - started);
        if (raw.error !== undefined)
            return unavailable("upstream-error", Date.now() - started);
        if (raw.status !== 0)
            return unavailable("upstream-error", Date.now() - started);
        const payload = parseJsonPayload(raw.stdout);
        if (!payload)
            return unavailable("bad-response", Date.now() - started);
        const latency = typeof payload.latency_ms === "number" ? payload.latency_ms : Date.now() - started;
        const digest = digestOf(payload);
        if (payload.available !== true) {
            const reason = typeof payload.reason === "string" && payload.reason !== "" ? payload.reason : "upstream-error";
            const result = unavailable(reason, latency, digest);
            // An escalated row still carries its own `decision_id` / `mode` /
            // `escalated_reason` (D-041 row 2): the caller may correlate it, it just
            // may not claim it acted.
            applyAuthorityKeys(result, payload);
            return result;
        }
        const answers = asRecord(payload.answers);
        const type = answerOf(answers, "triage_type");
        const risk = answerOf(answers, "triage_risk");
        if (!type?.value && !risk?.value)
            return unavailable("bad-response", latency, digest);
        const result = {
            available: true,
            triage_type: type?.value,
            triage_risk: risk?.value,
            confidences: { triage_type: type?.confidence ?? null, triage_risk: risk?.confidence ?? null },
            confidence_source: typeof payload.confidence_source === "string" && payload.confidence_source !== ""
                ? payload.confidence_source
                : "unknown",
            latency_ms: latency,
        };
        if (digest !== undefined)
            result.state_digest = digest;
        if (droppedFields.length > 0)
            result.dropped_fields = droppedFields;
        // T-04c: the authority keys ride through unchanged so the dispatch side can
        // correlate the task it just wrote (D-036/D-041).
        applyAuthorityKeys(result, payload);
        return result;
    }
    catch {
        // Structural fail-soft: a bug in this client must never break a dispatch.
        return unavailable("upstream-error", Date.now() - started);
    }
}
function formatConfidence(value) {
    return typeof value === "number" ? value.toFixed(2) : "n/a";
}
/** Provenance-qualified confidence wording. Only `api` may read as a real
 * confidence; `model-self-report` must carry the "not for gating" marker
 * (design D-002/D-004 hard rule). */
export function confidenceSourceLabel(confidenceSource) {
    if (confidenceSource === CONFIDENCE_SOURCE_MODEL_SELF_REPORT)
        return "模型自报置信度（不用于门控）";
    if (confidenceSource === CONFIDENCE_SOURCE_API)
        return "置信度来源=api（可作为判据）";
    return `置信度来源=${confidenceSource}（未标注，不作为判据）`;
}
/** One-line receipt echo for a produced advice (design D-005 item 2). Empty
 * for an unavailable result — the degraded path is silent by default. */
export function formatTriageReceipt(result) {
    if (!result.available)
        return "";
    const source = result.confidence_source;
    return (`[triage] 旁路建议，未据此改派发：triage_type=${result.triage_type ?? "?"}` +
        `（conf=${formatConfidence(result.confidences.triage_type)}）, ` +
        `triage_risk=${result.triage_risk ?? "?"}（conf=${formatConfidence(result.confidences.triage_risk)}）` +
        `；${confidenceSourceLabel(source)}，confidence_source=${source}`);
}
/** One-line `detail` for the `triage-suggestion` ledger row (five-tuple row
 * shape unchanged — seq/phase/kind/count/detail). */
export function formatTriageLedgerDetail(result, dispatchedType, dpId = DP1_ID) {
    const disagreement = result.triage_type !== undefined && result.triage_type !== dispatchedType;
    return [
        `dp=${dpId}`,
        `triage_type=${result.triage_type ?? "?"}`,
        `triage_risk=${result.triage_risk ?? "?"}`,
        `dispatched_type=${dispatchedType}`,
        `disagreement=${disagreement ? "yes" : "no"}`,
        `confidence_source=${result.confidence_source}`,
    ].join(" ");
}
//# sourceMappingURL=triage-client.js.map