/**
 * Dual-workspace target configuration (mw-dual-workspace D-002/D-010/D-014).
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
/** Error categories — parity-asserted by kind, not by message text. */
export type TargetConfigErrorKind = "invalid-yaml" | "invalid-config" | "missing-field" | "uproject-not-found" | "ambiguous-uproject";
export declare class TargetConfigError extends Error {
    readonly kind: TargetConfigErrorKind;
    constructor(kind: TargetConfigErrorKind, message: string);
}
export type WorkspaceMode = "single" | "dual";
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
    /** Game root. Absolute; === controlRoot in single mode. */
    gameRoot: string;
    /** Engine root (UE), or null when not configured. */
    engineRoot: string | null;
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
 * Resolve the workspace configuration for a control root.
 *
 * Precedence: MW_TARGET_GAME/MW_TARGET_ENGINE env > target.yml > single
 * fallback (gameRoot === controlRoot). Throws TargetConfigError on
 * contradictory or unusable configuration (fail-closed, never a silent
 * single fallback).
 */
export declare function resolveWorkspaceConfig(controlRoot: string): WorkspaceConfig;
/**
 * Resolve {uproject} (D-014): explicit field wins (must exist on disk);
 * otherwise exactly one *.uproject under the game root. 0 or many is an
 * error carrying the count — never a guess.
 */
export declare function discoverUproject(gameRoot: string, explicit?: string | null): string;
/**
 * Render one toolchain command template (AC-004, fail-closed). Replaces
 * {game}/{engine}/{uproject}; a token whose root is unconfigured throws
 * with the field name and the original command — no game-root fallback.
 */
export declare function renderToolchainCommand(command: string, config: WorkspaceConfig): string;
//# sourceMappingURL=target-config.d.ts.map