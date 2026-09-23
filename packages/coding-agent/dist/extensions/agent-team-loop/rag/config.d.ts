/**
 * RAG configuration layer (mw-rag-integration T-01; design D-003/D-009/D-013,
 * VC-002/VC-024): two-layer (machine + project) per-field merge, validation,
 * default/required resolution and the static-config fingerprint.
 *
 * Pure decision logic: fs reads only (rag-servers.yml, target.yml, path_roots
 * digest) — no writes, no network. The Python side
 * (mw_common.load_rag_config, T-06) mirrors this module 1:1 so both sides read
 * the same bytes.
 *
 * YAML shape: every YAML input key is snake_case (`token_env` / `timeout_ms` /
 * `path_roots_file` / `cli_entry`, and `target.yml`'s `default_server` /
 * `chat_budget` / `time_budget_s`) so both languages read one file;
 * RagServerEntry / RagRoleSpec expose camelCase, while `origin` keeps the
 * snake_case evaluated field paths (`mcp.url`, `path_roots_file`, …) that the
 * Python side (mw_common.RAG_FIELD_CAMEL) records.
 *
 * Resolution precedence (D-003/D-013, task T-01):
 *   machine file: MW_RAG_SERVERS_FILE > MW_RAG_SERVERS_HOME/.agents >
 *   $HOME/.agents > %USERPROFILE%/.agents; a missing file/dir is an empty
 *   layer and is never created (D-014).
 *   servers: machine layer, then project layer field-by-field (project value
 *   wins; arrays replace wholesale; `null` deletes the field).
 */
/** Env override for the machine service table file (whole-file hook). */
export declare const ENV_RAG_SERVERS_FILE = "MW_RAG_SERVERS_FILE";
/** Env override for the machine service table directory. */
export declare const ENV_RAG_SERVERS_HOME = "MW_RAG_SERVERS_HOME";
/** Machine service table basename under `<home>/.agents/`. */
export declare const RAG_SERVERS_BASENAME = "rag-servers.yml";
/** Default per-call transport timeout (design D-006). */
export declare const DEFAULT_RAG_TIMEOUT_MS = 180000;
/** Default rag_chat call budget (design D-006). */
export declare const DEFAULT_RAG_CHAT_BUDGET = 2;
/** Default task-level cumulative RAG time budget in seconds (D-006). */
export declare const DEFAULT_RAG_TIME_BUDGET_S = 900;
/**
 * snake_case (YAML) -> camelCase (runtime) field mapping. mw_common
 * `RAG_FIELD_CAMEL` is the authoritative copy; the two tables must stay
 * identical (T-01/T-06 parity). Fingerprint payloads and `origin` keys stay
 * snake_case, so this only describes the user-facing `RagConfig` shape.
 */
export declare const RAG_FIELD_CAMEL: Record<string, string>;
export type RagTransport = "mcp" | "skill" | "both";
/** Error categories — parity-asserted by kind, not by message text. */
export type RagConfigErrorKind = "bad-yaml" | "invalid-shape" | "unknown-key" | "unknown-server" | "mcp-missing-url" | "skill-missing-cli" | "enabled-empty-entry";
export declare class RagConfigError extends Error {
    readonly kind: RagConfigErrorKind;
    constructor(kind: RagConfigErrorKind, message: string);
}
export interface RagMcpEntry {
    url: string;
    tokenEnv: string | null;
    timeoutMs: number;
}
export interface RagSkillEntry {
    /** `skill.dir`: control-workspace-relative (or absolute); `null` = the control root (D-301). */
    dir: string | null;
    cliEntry: string;
    timeoutMs: number;
}
export interface RagCapabilities {
    graph: boolean;
    chat: boolean;
    rewrite: boolean;
}
export type RagFieldOrigin = "machine" | "project";
export interface RagServerEntry {
    transport: RagTransport;
    mcp: RagMcpEntry | null;
    skill: RagSkillEntry | null;
    adapter: "overcode-v1";
    pathRootsFile: string | null;
    /** sha256 of the resolved `path_roots_file` bytes (project-root anchored). */
    pathRootsDigest: string | null;
    sources: string[];
    capabilities: RagCapabilities;
    /** Per evaluated field path (`mcp.url`, `sources`, `skill`, …) origin. */
    origin: Record<string, RagFieldOrigin>;
}
export interface RagRoleSpec {
    server?: string;
    source?: string;
    require?: boolean;
    rewrite?: boolean;
    chatBudget?: number;
    timeBudgetS?: number;
}
export interface RagPhaseSpec {
    server?: string;
    source?: string;
    require?: boolean;
    rewrite?: boolean;
}
/** Global budget defaults from `target.yml`'s `rag.budgets` section. */
export interface RagBudgets {
    chat: number;
    timeS: number;
}
export interface RagConfig {
    enabled: string[];
    defaultServer: string | null;
    servers: Record<string, RagServerEntry>;
    roles: Record<string, RagRoleSpec>;
    phases: Record<string, RagPhaseSpec>;
    budgets: RagBudgets;
    fingerprint: string;
}
/**
 * Resolve the machine service table path (D-013): MW_RAG_SERVERS_FILE (whole
 * file) > MW_RAG_SERVERS_HOME (dir) > $HOME > %USERPROFILE%; the target is
 * `<home>/.agents/rag-servers.yml`. Returns "" when no home can be resolved
 * (the caller treats that as an empty layer). The directory is never created.
 */
export declare function machineRagServersPath(env?: NodeJS.ProcessEnv): string;
/**
 * Merge one server entry from the machine and project layers (D-003), mirroring
 * mw_common._rag_merge_server field by field: scalars merge per key, nested
 * blocks merge key by key (a project `null` sub-key deletes it), `sources`
 * replaces wholesale, a project `null` deletes a field/block and a machine
 * `null` deletes nothing. `origin` carries the snake_case evaluated field path
 * of every contributed key (`mcp.url`, `path_roots_file`, …). `transport`
 * defaults to `mcp` (Python parity) instead of being inferred from the present
 * blocks. Fail-closed on unknown keys and missing url/cli_entry.
 */
export declare function mergeServerEntry(machine: unknown, project: unknown, name: string): RagServerEntry;
/**
 * Load and merge the RAG configuration for a control root. No files → an
 * `enabled`-empty config (zero impact, D-014). Throws RagConfigError on
 * unknown keys/servers and on unusable mcp/skill blocks.
 */
export declare function loadRagConfig(controlRoot: string): RagConfig;
/**
 * The single `rewrite` decision: an explicit role/phase `rewrite:` always
 * wins, otherwise the server capability gates a research role/phase. Used by
 * `resolveDefaults` (both `renderRagBlock` and `callRag`) and by the
 * `rag_search` wire-tool selection; there is no second implementation.
 */
export declare function rewriteDefaults(role: string, phase: string, capabilityRewrite: boolean, explicit?: boolean): boolean;
/**
 * The single role/phase default resolver (D-102/D-104/D-109), shared by
 * `renderRagBlock` and `callRag`. Declared values only, authoritative
 * precedence `role > phase > defaultServer`: the role/phase specs are read
 * directly, never through a pre-resolved fallback, so a phase-declared server
 * is not shadowed by `default_server`. An empty/unregistered axis contributes
 * nothing (D-103): `server = defaultServer`, `source = null` and `rewrite`
 * reduces to `rewriteDefaults("", "", …)` = false. `rewrite` is the one
 * `rewriteDefaults` decision: explicit role/phase `rewrite:` wins, otherwise
 * the selected server's `capabilities.rewrite` combined with a research
 * role/phase (AC-006).
 */
export declare function resolveDefaults(config: RagConfig, role: string, phase: string): {
    server: string | null;
    source: string | null;
    rewrite: boolean;
};
/** Required judgment is a union with no exceptions (design §2). */
export declare function requiredFor(config: RagConfig, role: string, phase: string): boolean;
/**
 * Static-config fingerprint (D-009, VC-022), byte-identical to
 * mw_common.rag_fingerprint: canonical JSON (sorted keys, no whitespace) over
 * only the enabled servers' static fields + the project-root-anchored
 * `path_roots` content digest, the roles/phases specs and the budgets.
 * Probe/health state, session ids and every field of a non-enabled server are
 * excluded, so an unrelated change or a server restart never looks like a
 * config tear. Roles/phases are hashed verbatim (never resolved against
 * defaults) and the payload keys are snake_case, exactly like the Python side.
 */
export declare function ragFingerprint(config: RagConfig, enabledOnly?: string[]): string;
//# sourceMappingURL=config.d.ts.map