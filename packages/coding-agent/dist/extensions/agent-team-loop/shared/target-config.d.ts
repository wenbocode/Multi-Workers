/**
 * Dual-workspace / partition target configuration (mw-dual-workspace
 * D-002/D-010/D-014; mw-target-partition v2 single-file format, spec §1.5
 * / design D-001..D-004).
 *
 * Single source of truth for resolving `.agenticdoc/target.yml` + the
 * MW_TARGET_GAME / MW_TARGET_ENGINE env overrides into a WorkspaceConfig.
 * The Python side (mw_common.load_target_config) mirrors this module's
 * semantics 1:1 (T-17 parity pattern; cross-checked by shared fixtures).
 *
 * Resolution precedence (design D-011): env > target.yml > single. In
 * single mode gameRoot === controlRoot and engineRoot is null, so every
 * caller that only uses {game}-relative semantics keeps today's behavior
 * (AC-001 zero-regression default).
 *
 * v2 single-file format (mw-target-partition): a top-level `active:` key
 * (single | dual | partition) activates one mode block; files without it
 * keep the v1 flat semantics byte-identical (AC-013). The §1.5 rule table
 * lives in decideActiveMode(); partition mode resolves parent/partition
 * roots plus named roots (gameRoot is null there) with
 * MW_PARTITION_PARENT / MW_PARTITION_ROOT env overrides.
 *
 * Placeholder rendering ({game}/{engine}/{uproject}) is fail-closed
 * (AC-004): a command that references a field the config cannot supply
 * throws instead of silently falling back to the game root, and
 * {uproject} resolves only from an explicit `uproject:` field or exactly
 * one *.uproject under the game root (0 or many is an error carrying the
 * count).
 *
 * This module is pure decision logic: fs reads only (target.yml, uproject
 * discovery); no writes, no pi dependency.
 */
/** Env override for the game root (highest precedence, D-011). */
export declare const ENV_TARGET_GAME = "MW_TARGET_GAME";
/** Env override for the engine root. */
export declare const ENV_TARGET_ENGINE = "MW_TARGET_ENGINE";
/** Env override for the partition parent root (spec §1.5 EP family; only
 * honored when partition is the active mode — cross-family env is a
 * rule-table row 3 error). */
export declare const ENV_PARTITION_PARENT = "MW_PARTITION_PARENT";
/** Env override for the partition root (= worker cwd). */
export declare const ENV_PARTITION_ROOT = "MW_PARTITION_ROOT";
/** Error categories — parity-asserted by kind, not by message text. */
export type TargetConfigErrorKind = "invalid-yaml" | "invalid-config" | "missing-field" | "uproject-not-found" | "ambiguous-uproject";
export declare class TargetConfigError extends Error {
    readonly kind: TargetConfigErrorKind;
    constructor(kind: TargetConfigErrorKind, message: string);
}
export type WorkspaceMode = "single" | "dual" | "partition";
/** Where the resolved game/engine roots came from (observability, D-011). */
export type WorkspaceConfigSource = "env" | "target-yml" | "default";
/** toolchain section: command templates with {game}/{engine}/{uproject}. */
export type TargetToolchain = Record<string, string>;
/** ignore section. Field names mirror the YAML file for Py parity. */
export interface TargetIgnore {
    deny_globs: string[];
}
/** contract section. Field names mirror the YAML file for Py parity. */
export interface TargetContract {
    forbidden_paths: string[];
    conventions: string | null;
    docs: string[];
}
export interface WorkspaceConfig {
    mode: WorkspaceMode;
    /** Control workspace root (agenticdoc owner). Absolute. */
    controlRoot: string;
    /** Game root. Absolute; === controlRoot in single mode, null in
     * partition mode (partition has no game root — D-002). */
    gameRoot: string | null;
    /** Engine root (UE), or null when not configured. */
    engineRoot: string | null;
    /** Parent project root (partition mode only; read-only context), or
     * null. */
    parentRoot: string | null;
    /** Partition root = worker cwd (partition mode only), or null. */
    partitionRoot: string | null;
    /** Named extra roots (partition mode only), or null. Name → normalized
     * absolute path (relative entries anchor to the control root). */
    roots: Record<string, string> | null;
    vcs: string | null;
    /** Explicit `uproject:` field value (not discovered). Lazy discovery
     * happens in discoverUproject()/renderToolchainCommand(). */
    uproject: string | null;
    toolchain: TargetToolchain;
    ignore: TargetIgnore;
    contract: TargetContract;
    source: WorkspaceConfigSource;
}
/** Resolve the target.yml path for a control root (exported for tests). */
export declare function targetYmlPath(controlRoot: string): string;
/**
 * Read the raw `.agenticdoc/target.yml` mapping for a control root. Exported
 * for rag/config.ts (T-01, mw-rag-integration) so the RAG layer reuses this
 * single target.yml reader instead of adding a second parser (P-003); no
 * semantic change to the resolver.
 */
export declare function rawTargetYml(controlRoot: string): Record<string, unknown>;
/** decideActiveMode result: the workspace mode for v2 shapes, or "legacy"
 * (rows 8/11/12) telling the caller to run the pre-partition v1/env
 * resolution unchanged; block names the v2 mode block to parse (rows 6/7)
 * or null. */
export type ActiveModeDecision = "single" | "dual" | "partition" | "legacy";
export interface DecideActiveModeInput {
    fileShape: "none" | "v1" | "v2";
    active: string | null;
    envPartitionParent: string | null;
    envPartitionRoot: string | null;
    envTargetGame: string | null;
    envTargetEngine: string | null;
}
export interface ActiveModeResult {
    mode: ActiveModeDecision;
    block: "dual" | "partition" | null;
}
/** Spec §1.5 rule-table decision, rows 2-12 (row order is priority).
 *
 * Rows 1 and 4 are not expressible from these inputs and are enforced by
 * the caller: row 1 (mixed format) in detectShape(), row 4 (active names a
 * mode whose block is missing) when the caller parses the block this
 * function points at. Throws TargetConfigError(invalid-config) for rows
 * 2/3/10 with the table's message elements (illegal active value + enum /
 * conflicting env names / missing env name). Mirrors _decide_active_mode
 * in mw_common.py (shared table: test/fixtures/active-mode-table.json). */
export declare function decideActiveMode(input: DecideActiveModeInput): ActiveModeResult;
/**
 * Resolve the workspace configuration for a control root (single choke
 * point, mw-target-partition design D-001).
 *
 * Shape first (spec §1.5): no target.yml -> none; top-level `active:` key
 * -> v2 (v1 flat fields alongside raise the mixed-format error, row 1);
 * else v1. decideActiveMode() then applies rows 2-12 and dispatches:
 * legacy (v1/env semantics, byte-identical to the pre-partition resolver
 * — rows 8/11/12), v2 single (blocks parked, row 5), v2 dual (block fields
 * + MW_TARGET_GAME/MW_TARGET_ENGINE overlay, row 6), or partition
 * (block/env fields + MW_PARTITION_PARENT/MW_PARTITION_ROOT overlay,
 * rows 7/9). Throws TargetConfigError on contradictory or unusable
 * configuration (fail-closed, never a silent single fallback).
 */
export declare function resolveWorkspaceConfig(controlRoot: string): WorkspaceConfig;
/**
 * Resolve {uproject} (D-014): explicit field wins (must exist on disk);
 * otherwise exactly one *.uproject under the game root. 0 or many is an
 * error carrying the count — never a guess.
 */
export declare function discoverUproject(gameRoot: string, explicit?: string | null): string;
/**
 * Render one toolchain command template (AC-004, fail-closed) with the
 * token set dispatched by mode (design D-002): partition replaces
 * {parent}/{partition}/{<root name>} and any other placeholder-shaped
 * token (including {game}/{engine}/{uproject}) raises missing-field with
 * the token and the original command; dual/single keep the current
 * {game}/{engine}/{uproject} replacement — a token whose root is
 * unconfigured throws with the field name and the original command, no
 * game-root fallback.
 */
export declare function renderToolchainCommand(command: string, config: WorkspaceConfig): string;
//# sourceMappingURL=target-config.d.ts.map