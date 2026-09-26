/**
 * status-model.ts — the /autopilot console's stateless view model
 * (goal-autopilot T-15, design D-005/D-109/D-110, AC-015/AC-018).
 *
 * Everything here is DERIVED FROM FILES on every call — the console keeps no
 * process state (D-005: 断点重开 = 正常重开). One derivation feeds both the
 * human-readable view and `--json` (view parity, VC-017).
 *
 * File-family schemas are owned by the Python side; this module mirrors the
 * read-side rules it needs:
 *   - _roadmap.md                      → autopilot/roadmap.py (D-105 section
 *     schema; lenient view-side parse — malformed pieces become warnings,
 *     while the conductor is the one that hard-fails and skips its tick)
 *   - gates/gate-{seq:04d}.md          → autopilot/gates.py (12-field
 *     frontmatter YAML subset, status enum, seq-ordered directory scan)
 *   - timeline.jsonl + .1/.2 rotations → autopilot/timeline.py (query_events
 *     watermark / ev_filter / pruned semantics, D-109)
 *   - _autopilot/config.json           → autopilot/config.py (13 fields,
 *     D-110; present-but-invalid fails closed, missing file = defaults)
 *   - rounds derivation                → autopilot/state.py used_rounds
 *     (distinct attempt per loop label; a missing attempt label degrades to
 *     directory-identity counting — VC-020 locks both implementations to
 *     the same result over the same task dirs)
 *   - key phase                        → _index.parallel via shared/index-store.ts
 *
 * Loop families per key (design §4.1 round table): `l2:{key}:{edge}` → l2,
 * `l3:{key}` → l3, `exec:{key}:{stem}` and `repair:{key}` → retry. A
 * family's `used` is its most-consumed loop — budgets are enforced per loop
 * (AC-008/AC-011), so the maximum is the binding constraint; a key that
 * spent one round on each of several edges is NOT exhausted. `max` is
 * config round_budget for all three families (single source, AC-011).
 */
export declare function autopilotDir(projectDir: string): string;
export declare function roadmapPath(projectDir: string): string;
export declare function gatesDir(projectDir: string): string;
export declare function timelinePath(projectDir: string): string;
export declare function configPath(projectDir: string): string;
/** `.mw/gates.lock` — the O_CREAT|O_EXCL gate answer lock (D-105). */
export declare function gatesLockPath(projectDir: string): string;
/** `.mw/autopilot-config.lock` — the O_CREAT|O_EXCL lock guarding the
 * config.json read-modify-write (mw-autopilot-verify-cli D-006). Same path
 * family and protocol as the other `.mw/` locks; the Python writer takes the
 * byte-identical path (plan §2.2), so the two sides are mutually exclusive. */
export declare function configLockPath(projectDir: string): string;
export interface AutopilotConfig {
    enabled: boolean;
    paused: boolean;
    poll_interval_sec: number;
    max_parallel_keys: number;
    round_budget: number;
    worker_timeout_min: number;
    l2_read_file_cap: number;
    l2_read_byte_cap: number;
    /** Consecutive same-edge advance failures before the key is marked
     * stalled (mw-autopilot-stall-feedback AC-003). Optional in the file —
     * absent falls back to the default. */
    advance_stall_ticks: number;
    /** Cross-key red repair channel (xkey-repair-mechanism AC-008). Off by
     * default so every existing flow is untouched until a project opts in. */
    xkey_repair: boolean;
    /** Per-project verification argv — no shell, so a list is the contract
     * (D-007). */
    xkey_verify_cmd: string[];
    /** Conductor verification-subprocess timeout in seconds (>= 1). */
    xkey_verify_timeout_s: number;
    /** Workspace-root selector for xkey verification (conductor-resolved).
     * "" = auto (workspace_root). The schema only requires a string; the
     * root-name validity is resolved at parse time (plan §2.2). */
    xkey_verify_cwd: string;
}
export declare const DEFAULT_CONFIG: AutopilotConfig;
export declare const BOOL_FIELDS: readonly ["enabled", "paused", "xkey_repair"];
/** field → list of non-empty strings — identical to config.py _LIST_FIELDS. */
export declare const LIST_FIELDS: readonly ["xkey_verify_cmd"];
/** Plain string fields — identical to config.py _STRING_FIELDS. */
export declare const STR_FIELDS: readonly ["xkey_verify_cwd"];
/** field → [min, max|null] — identical to config.py _INT_RANGES. */
export declare const INT_RANGES: Record<string, [number, number | null]>;
/** Validate a raw config object exactly like config.py validate_config:
 * unknown fields and out-of-range values fail closed, naming every offender.
 * Bool fields are checked before the int rules (JSON booleans would
 * otherwise pass number checks). Absent fields are fine — they fall back to
 * their defaults at read time. */
export declare function validateConfigData(data: unknown): string[];
export type ConfigResult = {
    ok: true;
    config: AutopilotConfig;
} | {
    ok: false;
    error: string;
};
/** Read _autopilot/config.json. A missing file is NOT an error — it means
 * "autopilot never enabled" and yields the defaults with zero footprint
 * (D-110). A present-but-invalid file fails closed with every offending
 * field named (config.py load_config semantics). Fields absent from a
 * partial file fall back to their defaults (view-side robustness; saves
 * normalize the file to the full canonical set). */
export declare function readConfig(projectDir: string): ConfigResult;
/** Validate, then atomically write config.json (tmp + rename, UTF-8, LF,
 * indent-2 + trailing newline — the exact shape config.py save_config
 * writes and parses back). The write always normalizes to the full
 * canonical field set in DEFAULT_CONFIG order. */
export declare function saveConfig(projectDir: string, config: AutopilotConfig): {
    ok: true;
} | {
    ok: false;
    error: string;
};
export declare const STAGE_STATUSES: readonly ["pending", "approved", "running", "closed", "closed-human", "halted"];
export declare const KEY_STATUSES: readonly ["running", "done", "stalled", "closed-legacy"];
export interface RoadmapKey {
    key: string;
    role: string;
    dependsOn: string[];
}
export interface RoadmapStage {
    number: number;
    title: string;
    goal: string;
    status: string;
    /** key → running|done|stalled|closed-legacy (D-105 KEY_STATUSES).
     * Values are kept verbatim; ones outside the enum surface as parse
     * warnings instead of being dropped. */
    keyStatus: Record<string, string>;
    keys: RoadmapKey[];
}
export interface RoadmapParse {
    stages: RoadmapStage[];
    warnings: string[];
}
/** Parse roadmap markdown into stages + warnings. Never throws — this is the
 * view side of roadmap.py's strict parser: structural problems the conductor
 * treats as skip-the-tick errors degrade here to warnings plus whatever
 * stages did parse, so the console always has something honest to show. */
export declare function parseRoadmapText(text: string): RoadmapParse;
export type RoadmapResult = {
    ok: true;
    stages: RoadmapStage[];
    warnings: string[];
} | {
    ok: false;
    error: string;
};
export declare function readRoadmap(projectDir: string): RoadmapResult;
export declare const GATE_KINDS: readonly ["stage-confirm", "stage-close", "stalled", "budget-exhausted", "goal-change", "xkey-authorize"];
export declare const GATE_STATUSES: readonly ["pending", "approved", "rejected"];
/** Canonical frontmatter field order (gates.py FRONTMATTER_FIELDS). */
export declare const GATE_FRONTMATTER_FIELDS: readonly ["id", "kind", "stage", "key", "created_at", "created_by", "question", "context_refs", "status", "answered_at", "answered_by", "note"];
export interface GateRecord {
    id: string;
    kind: string;
    status: string;
    stage: number | null;
    key: string | null;
    question: string;
    createdAt: string;
    path: string;
}
/** Parse one gate file into a GateRecord. Throws GateFormatError on any
 * frontmatter/schema violation — corrupt gate files surface as errors, never
 * as silently wrong queue entries (gates.py parse semantics). */
export declare function parseGateFile(text: string, file: string): GateRecord;
/** All gates in the directory, ordered by seq — the directory scan IS the
 * queue (D-105). A missing directory is an empty queue. Corrupt gate files
 * are reported in `errors` (the console surfaces them as warnings) and
 * excluded from the list, mirroring gates.py enumerate()'s explicit errors. */
export declare function listGates(projectDir: string): {
    gates: GateRecord[];
    errors: string[];
};
/** Event type vocabulary (D-109). Used for the console's default beat-free
 * include-set — NOT for rejection: unknown ev values parse fine. */
export declare const EVENT_TYPES: Set<string>;
export declare const BEAT_EV = "beat";
/** The default timeline view's include-set: every event type except beats. */
export declare function nonBeatFilter(): Set<string>;
export interface TimelineEvent {
    ts: string;
    seq: number;
    ev: string;
    key: string;
    stage: number | null;
    detail: string;
}
export interface TimelineQuery {
    /** Parsed lines with seq > watermark, sorted ascending (rotations
     * oldest → newest, then the current file). */
    events: TimelineEvent[];
    /** Events past the watermark that rotation no longer retains (超 2 代轮
     * 转) — never a silent gap. */
    pruned: number;
    /** Unparseable (torn) lines encountered — counted, not silently dropped. */
    skipped: number;
    /** Highest-seq event in the retained chain — the watermark to persist
     * (D-109: every status/timeline view stores {seq, ts}). */
    head: {
        seq: number;
        ts: string;
    } | undefined;
}
/** Replay timeline events with seq > watermark (D-109 回放协议): rotated
 * generations oldest → newest, then the current file; union filtered by seq,
 * sorted ascending. `evFilter` is an include-set (pass nonBeatFilter() for
 * the console's default beat-free view; undefined keeps every type).
 *
 * A watermark predating the oldest retained line yields a non-zero `pruned`
 * count — the replay explicitly reports what rotation ate instead of
 * silently starting mid-history. */
export declare function queryTimeline(timelinePath: string, watermark: number, evFilter?: ReadonlySet<string>): TimelineQuery;
/** Map an --since ISO timestamp onto the seq watermark protocol: the highest
 * seq among events at-or-before that timestamp (0 = replay everything). */
export declare function watermarkFromSince(timelinePath: string, sinceIso: string): number;
/** Frontmatter scalar labels of one task.md (loop/attempt/origin/type...).
 * Lenient mirror of state.py parse_task_labels: a missing frontmatter or a
 * malformed line simply yields no label; nested blocks (read_scope lists)
 * are skipped, not parsed. */
export declare function parseTaskLabels(taskMdPath: string): Map<string, string>;
/** Per-loop used-round counts from task.md loop/attempt labels — the VC-020
 * parity surface with state.py used_rounds. A round = one distinct attempt
 * value within a loop (D-111 round table): same-attempt repair dispatches
 * and orphan re-insertions do not add rounds. A task.md whose attempt label
 * is missing degrades to file-count semantics keyed by its directory, so
 * rewrites of the same dir never double-count. In-flight dispatches count —
 * their task.md exists from the dispatch transaction on (D-102). */
export declare function usedRounds(workersDirs: string[]): Map<string, number>;
export declare const STATUS_SCHEMA = "autopilot-status/1";
export interface RoundBudget {
    used: number;
    max: number;
}
export interface KeyRounds {
    l2: RoundBudget;
    l3: RoundBudget;
    retry: RoundBudget;
}
export interface StageKeyView {
    key: string;
    phase: string;
    state: string;
    rounds: KeyRounds;
}
export interface StageView {
    current: number;
    status: string;
    keys: StageKeyView[];
}
export interface GateView {
    id: string;
    kind: string;
    status: string;
}
export interface TimelineWatermark {
    seq: number;
    ts: string;
}
export interface StatusConfigView {
    enabled: boolean;
    poll_interval_sec: number;
    round_budget: number;
    max_parallel_keys: number;
}
/** The versioned `/autopilot status --json` payload (design §4.1, D-109 N8).
 * Field set and shapes are locked by the design example. */
export interface AutopilotStatus {
    schema: typeof STATUS_SCHEMA;
    stage: StageView;
    gates: GateView[];
    timeline: TimelineWatermark;
    config: StatusConfigView;
}
/** Derivation outcome: `status` is the schema-exact JSON surface; `paused`
 * and `warnings` are human-view extras (the D-110 pause flag lives in the
 * config file, not the versioned status schema). */
export interface StatusModel {
    status: AutopilotStatus;
    paused: boolean;
    warnings: string[];
}
export type StatusModelResult = {
    ok: true;
    model: StatusModel;
} | {
    ok: false;
    error: string;
};
/** Derive the full status view from files alone (AC-015: a reopened console
 * rebuilds this in <10s with zero process state). The only hard failure is
 * an invalid config.json (D-110 fail-closed); a missing/parse-failed
 * roadmap, corrupt gate files, and an absent timeline all degrade to empty
 * views plus warnings. */
export declare function deriveStatusModel(projectDir: string): StatusModelResult;
/** Human-readable rendering of the SAME derivation that produced the --json
 * payload (view parity, VC-017): every number below is taken from the model
 * object, so the two views cannot drift. */
export declare function renderStatusText(model: StatusModel): string;
//# sourceMappingURL=status-model.d.ts.map