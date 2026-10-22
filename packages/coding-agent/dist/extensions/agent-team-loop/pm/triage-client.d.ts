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
/** Hard client-side wall-clock budget for one `mw decide run` child (D-006). */
export declare const DEFAULT_TRIAGE_TIMEOUT_MS = 20000;
/** Client-side canonical budget for a structured state (spec §5.4 / D6 Q1). */
export declare const MAX_STRUCTURED_STATE_BYTES = 2000;
/** Largest free-form `state` string forwarded on the legacy path (design
 * D-004 `max_state_bytes`; kept below the Python default so a long task body
 * does not trip the server budget check). Structured states use
 * {@link MAX_STRUCTURED_STATE_BYTES} instead. */
export declare const MAX_TRIAGE_STATE_BYTES = 16000;
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
/** Legacy DP-1 question set (D-006 wire shape).
 *
 * `spec.md:162` keeps the `isinstance(state, str)` branch byte-compatible, and
 * `mw.py:718` still requires a non-empty `questions` map in that request, so the
 * legacy path must keep forwarding exactly these choices. The **structured**
 * path does not use it: the question set is authoritative in the Python
 * decision registry (design §2.1). Delete this constant together with the
 * legacy branch once Python fills `questions` from the registry. */
export declare const DP1_QUESTIONS: Record<string, {
    type: "choice";
    choices: string[];
}>;
/** `questions_version` for dp1 = `q-<sha256(canonical questions)[:8]>`, exactly
 * `decision_points._questions_version()` for the registry's dp1 question set
 * (`q-09d3aad3` today). Derived from {@link DP1_QUESTIONS} instead of hardcoded
 * so the two cannot drift; the canonical form is Python's
 * `json.dumps(list(questions), ensure_ascii=False, sort_keys=True,
 * separators=(",", ":"))` — the same mirror `pm-orchestrator.ts` uses for dp2.
 *
 * A structured dp1 state must carry this value or `decide_for` refuses it as
 * `input-incomplete` (registry `REQUIRED_STATE_FIELDS`). */
export declare const DP1_QUESTIONS_VERSION: string;
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
    /** Structured state object (canonical ≤2000B) or the legacy free-form
     * string state (`spec.md:162` compat clause, ≤16KB). */
    state: string | TriageState;
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
/** `required_if` matrix (D6 Q5.1): each dp only carries its own block.
 *
 * Keys are **canonical ids from `packages/multi-workers/decision_points.py`
 * `DP_REGISTRY`** — the registry owns the id set, so a short form (`dp1`,
 * `dp3-clarify`) would never match a real dpId and `?? []` would silently drop
 * the whole dp-specific requirement. Exported only so the cross-layer drift
 * lock can assert every key against the live registry. */
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
/** Build the DP-1 `state` string from the dispatch-time inputs (D-006 legacy
 * path; the structured path uses a caller-built object instead). */
export declare function buildTriageState(input: {
    description: string;
    taskType: string;
    cli: string;
    phase?: string;
}): string;
/** Bound the legacy `state` payload so a long task body cannot trip the Python
 * `max_state_bytes` budget (fail-soft: the advice is skipped, not the
 * dispatch). Byte-accurate because the Python side measures UTF-8 bytes. */
export declare function boundTriageState(state: string, maxBytes?: number): string;
/** Run one decision point. Never throws; a non-enabled policy is a `disabled`
 * no-op that performs no spawn. */
export declare function triageDispatch(input: TriageRunInput): TriageResult;
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