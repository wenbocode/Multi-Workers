/**
 * triage-client.ts — decision-point client for the pre-dispatch triage
 * (mw-jev-provider-integration T-03; mw-decision-substitution T-04; design
 * D-004/D-005/D-006/D-007 + D-019/D-021).
 *
 * Contract:
 * - Input is `(dpId, material, meta)` for the four-DP business contract
 *   (mw-decision-context T03): `material` carries ONLY the registry's
 *   `modelStateFields` for that dp (the single allowlist projection), `meta`
 *   carries the local envelope (`record_version`, `logical_id`, `key`,
 *   `task_key`, `initiator_role`, `retry_of`) and NEVER reaches the model.
 *   The stdin payload is exactly `{material, meta}`.
 * - The older **structured state** entry (`{state}`, D6 Q1.1) is still accepted
 *   by {@link triageDispatch} for callers that do not build the envelope yet;
 *   it validates L0 enums/counters/L1 summaries and caps the state at 2000B.
 *   The free-form dp1 string state and its `triage_risk` question map are gone
 *   (spec §1.7: a replaced contract is not kept as a compatibility branch).
 *   L2 content (credentials / user quotes / absolute paths / code) has **no
 *   place in either signature** — it is excluded by construction, not washed
 *   afterwards (D-019).
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
import { type TaskStateSnapshot } from "./decision-task-state.ts";
/** Hard client-side wall-clock budget for one `mw decide run` child (D-006). */
export declare const DEFAULT_TRIAGE_TIMEOUT_MS = 20000;
/** Client-side canonical budget for a structured state (spec §5.4 / D6 Q1). */
export declare const MAX_STRUCTURED_STATE_BYTES = 2000;
/** Decision point id for the pre-dispatch triage (D-006). The Python registry
 * owns the id set and the question set; this module only holds ids — and they
 * are the **registry ids verbatim** (`decision_points.DP_REGISTRY`), never short
 * forms: a short id silently misses every dp-specific row below. The drift lock
 * in `test/suite/triage-client-state.test.ts` pins this against the registry. */
export declare const DP1_ID = "dp1-dispatch-type";
/** TS-local refusal reasons (they never come back from the Python response;
 * `decision.py`'s frozen 8-value reason set is untouched by them). */
export declare const TRIAGE_REASON_INPUT_INCOMPLETE = "input-incomplete";
export declare const TRIAGE_REASON_INPUT_OVERSIZE = "input-oversize";
export declare const CONFIDENCE_SOURCE_API = "api";
export declare const CONFIDENCE_SOURCE_MODEL_SELF_REPORT = "model-self-report";
/** Record version of the local decision envelope (mw-decision-context §4.1).
 * Lives in the immutable creation fact, never in a wire-capture absence probe. */
export declare const DECISION_RECORD_VERSION = 2;
/** Initiating role vocabulary: the PM, the three dp1 worker types, or an
 * unverifiable caller. dp1 always says `pm` (the dispatch is the PM's), and the
 * vocabulary is T02's single lowercase one: Python's
 * `decision_lifecycle.INITIATOR_ROLES` refuses a second spelling table here (it
 * only case-normalises as a defensive fallback), so a `PM` producer would send
 * a role the writer never meant to accept. */
export type DecisionInitiatorRole = "pm" | "coding" | "research" | "review" | "unknown";
/** Local envelope metadata. Never part of the model material. */
export interface DecisionEnvelopeMeta {
    record_version: typeof DECISION_RECORD_VERSION;
    /** One new UUID per real decision; every attempt/feedback row joins on it. */
    logical_id: string;
    /** AgenticTask key the decision was made under. */
    key: string;
    /** The REAL reserved task id, or null when the PM decision has no task
     * (never "the latest task" by inference). */
    task_key: string | null;
    initiator_role: DecisionInitiatorRole;
    /** Set only when this decision retries another (new id,指前次). */
    retry_of: string | null;
    task_before?: TaskStateSnapshot;
}
/** The stdin payload for `mw decide run <dp> --stdin` (four-DP contract). */
export interface DecisionMaterialEnvelope {
    material: TriageState;
    meta: DecisionEnvelopeMeta;
}
/** A dp1 task-material triple,原文 from the dispatch card. */
export interface Dp1TaskMaterial extends TriageState {
    task_goal: string;
    task_requirements: string;
    task_deliverables: string;
}
/** Build the local envelope metadata for one NEW decision.
 *
 * `logical_id` is minted here (one UUID per decision, independent of the task
 * id) so a caller cannot reuse a previous decision's id by accident. `retry_of`
 * is explicit: a retry mints a new id and points at the previous one; a first
 * attempt keeps `null`. A missing task stays `null` instead of being guessed. */
export declare function newDecisionMeta(input: {
    key: string;
    taskKey?: string | null;
    initiatorRole?: DecisionInitiatorRole;
    retryOf?: string | null;
    taskBefore?: TaskStateSnapshot;
}): DecisionEnvelopeMeta;
/** Effective `.mw/decide.json` policy relevant to the dispatch path. */
export interface DecidePolicy {
    /** Global `enabled` flag. False for a missing / invalid config. */
    enabled: boolean;
    /** `points.dp1.enabled` (default true) — a per-point kill switch. */
    dp1Enabled: boolean;
    /** `points.dp1.alert_on_disagreement` (default true) — wake the PM only
     * when the suggestion disagrees AND this is not explicitly false. */
    alertOnDisagreement: boolean;
    /** `triage_notify_on_unavailable` (default false) — record a ledger notice
     * when no advice could be produced. Never wakes the PM. */
    notifyOnUnavailable: boolean;
    /** Hard timeout for the child, `timeout_s` when configured else 20s. */
    timeoutMs: number;
}
/** One `mw decide run` invocation description (stdin payload included). */
export interface DecideRunRequest {
    projectDir: string;
    dp: string;
    timeoutMs: number;
    /** Request JSON (`state`, plus `questions` on the legacy path); piped on
     * stdin, never argv. */
    input: string;
    /** True for the four-DP envelope (`{material, meta}`): the CLI only takes the
     * versioned `--stdin` path, which is what mints the record-start fact and
     * requires the local meta. The legacy `{state}` request keeps the implicit
     * stdin read (no flag needed). */
    viaStdin?: boolean;
}
/** Raw child result — the seam tests replace (no real subprocess). */
export interface RawDecideRun {
    status: number | null;
    stdout: string;
    stderr: string;
    /** Spawn-level failure text (missing mw.py, ENOENT, ...). */
    error?: string;
    timedOut: boolean;
}
/** Injectable runner (tests stub this; production uses {@link runDecideMw}). */
export type DecideRunner = (request: DecideRunRequest) => RawDecideRun;
/** A structured DP state: JSON-native values only (D6 Q1.1: int/bool/string/
 * arrays/objects; no floats — canonical digests would drift). */
export type TriageState = Record<string, unknown>;
/** Structured DP advice (design D-003 response projection). */
export interface TriageResult {
    available: boolean;
    reason?: string;
    triage_type?: string;
    triage_risk?: string;
    confidences: Record<string, number | null>;
    confidence_source: string;
    latency_ms: number;
    /** `sha256(canonical state)[:16]` as returned by the Python client — pure
     * passthrough; this module never hashes (design D-004). */
    state_digest?: string;
    /** True when the state was never sent and a human must be brought in
     * (`input-incomplete` / `input-oversize`, design D-021). */
    escalate_to_human?: boolean;
    /** Required-field names that failed the check — names only (L0), never
     * values. */
    missing_fields?: string[];
    /** Field names dropped/shrunk by the ≤2000B truncation — names only. */
    dropped_fields?: string[];
    /** `<dp>:<trigger_id>` of the authorization row the child archived (design
     * D-036/D-041). Verbatim passthrough from `mw decide run`; absent when the
     * child did not report one (the legacy `questions` path never does). */
    decision_id?: string;
    /** Effective decision-point mode the child used. Verbatim passthrough — this
     * module never derives it from `.mw/decide-points.json`. */
    mode?: "auto" | "suggest";
    /** The child's own `acted` verdict: whether **Python** executed the action.
     * For `intent="answer"` it is false even when the answer is adopted
     * downstream (D-041) — adoption is a consuming-side fact, never inferred
     * from this flag or from `mode`. */
    acted?: boolean;
    /** `escalated_reason` from the child, kept alongside (never folded into)
     * the legacy `reason`, whose vocabulary stays frozen. */
    escalated_reason?: string;
}
export interface TriageRunInput {
    projectDir: string;
    /** Decision point id (design §2.1). Defaults to {@link DP1_ID}. */
    dpId?: string;
    /** @deprecated legacy alias of {@link dpId}; kept for existing callers. */
    dp?: string;
    /** Structured state object (canonical ≤2000B). The four-DP business contract
     * goes through {@link triageDispatchEnvelope} instead. */
    state: TriageState;
    /** Pre-read policy; read from disk when omitted. */
    policy?: DecidePolicy;
    /** Runner override (tests); the real mw.py child when omitted. */
    run?: DecideRunner;
    timeoutMs?: number;
}
/** Read `<projectDir>/.mw/decide.json` fail-soft (design D-007): a missing,
 * unreadable, non-object or `enabled != true` file is the "fully off" policy.
 * Read-only — this module never writes config. */
export declare function readDecidePolicy(projectDir: string): DecidePolicy;
/** The real child: reuse mw-runner's interpreter/path resolution and the
 * no-window contract (`windowsHide`) plus `-X utf8` for the Chinese
 * diagnostics (design D-001; `agentic-scripts.ts:65-71` precedent). */
export declare const runDecideMw: DecideRunner;
/** `required_if` matrix (D6 Q5.1): each structured dp only carries its own block.
 *
 * Keys are **canonical ids from `packages/multi-workers/decision_points.py`
 * `DP_REGISTRY`** — the registry owns the id set, so a short form (`dp1`,
 * `dp3-clarify`) would never match a real dpId and `?? []` would silently drop
 * the whole dp-specific requirement. Exported only so the cross-layer drift
 * lock can assert every key against the live registry.
 *
 * The four business-material dps (dp1/dp2/dp3/dp25) deliberately have NO row:
 * their required fields are the generated registry contract
 * (`DECIDE_REGISTRY.requiredStateFields`) consumed by the material validators.
 * A row here would be composed with {@link UNIVERSAL_REQUIRED_FIELDS} (the
 * audit keys `phase`/`risk`/...), forcing business material to carry them —
 * exactly the retired pre-T01 compatibility branch (spec §1.7). dp4/dp5/dp6/
 * dp13 remain explicit legacy debt for the structured path. */
export declare const REQUIRED_FIELDS_BY_DP: Record<string, string[]>;
/** Required-field refusal list for one dp: field names only (L0). An empty
 * array means the state is sendable. */
export declare function validateStructuredState(dpId: string, state: TriageState): string[];
export declare function canonicalStateJson(state: unknown): string;
/** UTF-8 byte length of the canonical state — the number the ≤2000B budget
 * (and Python's own `_encode_state` check) is measured in. Length only: this
 * module never hashes (D-004). */
export declare function canonicalStateBytes(state: unknown): number;
export interface TruncationOutcome {
    /** Deep copy of the input with the truncation steps applied. */
    state: Record<string, unknown>;
    /** Names of the fields that were dropped or shrunk, in step order. */
    dropped: string[];
    /** Canonical UTF-8 size of {@link state} after the steps. */
    bytes: number;
    /** True when even after every step the state is still over budget. */
    oversize: boolean;
}
/** Two-stage truncation (D6 Q1.4), deterministic and never dropping a required
 * field: stage 1 drops/shrinks optional L1 blocks, stage 2 halves the required
 * L1 summaries, and if the state is still over budget the caller must refuse.
 * The input object is never mutated. */
export declare function truncateStructuredState(state: TriageState, maxBytes?: number): TruncationOutcome;
/** Result of preparing a structured state for the wire. */
export type StructuredStatePreparation = {
    ok: true;
    state: Record<string, unknown>;
    bytes: number;
    dropped: string[];
} | {
    ok: false;
    reason: string;
    missing: string[];
    dropped: string[];
};
/** Validate → canonicalise → bound, in that order. A refusal means ZERO spawn. */
export declare function prepareStructuredState(dpId: string, state: TriageState, maxBytes?: number): StructuredStatePreparation;
/** Field names of a meta whose value/type would be refused. Names only (L0),
 * never values. */
export declare function validateDecisionMeta(meta: DecisionEnvelopeMeta): string[];
/** Result of preparing one material envelope for the wire. */
export type DecisionEnvelopePreparation = {
    ok: true;
    envelope: DecisionMaterialEnvelope;
    bytes: number;
} | {
    ok: false;
    reason: string;
    missing: string[];
};
/** Validate → canonicalise → bound the business material, in that order.
 *
 * The allowlist is the registry's `modelStateFields` for the dp: any extra key
 * (identity / audit / a second question) is a refusal, never forwarded. A
 * missing / blank required field is `input-incomplete`; material over an
 * explicitly configured budget is `input-oversize`. Both are ZERO-spawn
 * refusals: necessary material is never silently truncated (design §2).
 *
 * `maxBytes = 0` means the legacy 2000B client constant does NOT gate the
 * material: the design's rule is to check against the ACTUAL transport budget,
 * which lives in Python (`max_state_bytes` defaults to 0 = off; the token gates
 * apply there), and no new client ceiling may be invented before the four-case
 * measurement. Shape validation still happens here, so a malformed material is
 * refused before any spawn. */
export declare function prepareDecisionEnvelope(dpId: string, material: TriageState, meta: DecisionEnvelopeMeta, maxBytes?: number): DecisionEnvelopePreparation;
/** Run one decision point. Never throws; a non-enabled policy is a `disabled`
 * no-op that performs no spawn. */
export declare function triageDispatch(input: TriageRunInput): TriageResult;
/** Run one decision point with the four-DP business material on the local
 * envelope (`{material, meta}` piped to the SAME `mw decide run` stdin
 * wrapper). Never throws; a non-enabled policy performs no spawn. */
export declare function triageDispatchEnvelope(input: {
    projectDir: string;
    dpId: string;
    material: TriageState;
    meta: DecisionEnvelopeMeta;
    policy?: DecidePolicy;
    run?: DecideRunner;
    timeoutMs?: number;
    maxBytes?: number;
}): TriageResult;
/** Provenance-qualified confidence wording. Only `api` may read as a real
 * confidence; `model-self-report` must carry the "not for gating" marker
 * (design D-002/D-004 hard rule). */
export declare function confidenceSourceLabel(confidenceSource: string): string;
/** One-line receipt echo for a produced advice (design D-005 item 2). Empty
 * for an unavailable result — the degraded path is silent by default. */
export declare function formatTriageReceipt(result: TriageResult): string;
/** One-line `detail` for the `triage-suggestion` ledger row (five-tuple row
 * shape unchanged — seq/phase/kind/count/detail). */
export declare function formatTriageLedgerDetail(result: TriageResult, dispatchedType: string, dpId?: string): string;
//# sourceMappingURL=triage-client.d.ts.map