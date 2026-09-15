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

import * as fs from "node:fs";
import * as path from "node:path";
import { parse } from "yaml";

/** Env override for the game root (highest precedence, D-011). */
export const ENV_TARGET_GAME = "MW_TARGET_GAME";
/** Env override for the engine root. */
export const ENV_TARGET_ENGINE = "MW_TARGET_ENGINE";

/** Error categories — parity-asserted by kind, not by message text. */
export type TargetConfigErrorKind =
	| "invalid-yaml"
	| "invalid-config"
	| "missing-field"
	| "uproject-not-found"
	| "ambiguous-uproject";

export class TargetConfigError extends Error {
	readonly kind: TargetConfigErrorKind;

	constructor(kind: TargetConfigErrorKind, message: string) {
		super(message);
		this.name = "TargetConfigError";
		this.kind = kind;
	}
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

const TARGET_YML = "target.yml";

function fail(kind: TargetConfigErrorKind, message: string): never {
	throw new TargetConfigError(kind, message);
}

function requireString(value: unknown, field: string): string {
	if (typeof value !== "string" || value.trim() === "") {
		fail("invalid-config", `target.yml: field '${field}' must be a non-empty string`);
	}
	return value;
}

function optionalString(value: unknown, field: string): string | null {
	return value === undefined || value === null ? null : requireString(value, field);
}

function stringArray(value: unknown, field: string): string[] {
	if (value === undefined || value === null) return [];
	if (!Array.isArray(value) || value.some((e) => typeof e !== "string" || e.trim() === "")) {
		fail("invalid-config", `target.yml: field '${field}' must be a list of non-empty strings`);
	}
	return value;
}

/**
 * Normalize a configured root: resolve against controlRoot (relative
 * entries allowed for local convenience), then realpath when the path
 * exists so junctions/case fold like the read-scope normalizer.
 */
function normalizeRoot(raw: string, controlRoot: string): string {
	const resolved = path.resolve(controlRoot, raw);
	try {
		return fs.realpathSync.native(resolved);
	} catch {
		return resolved;
	}
}

/** Resolve the target.yml path for a control root (exported for tests). */
export function targetYmlPath(controlRoot: string): string {
	return path.join(controlRoot, ".agenticdoc", TARGET_YML);
}

interface RawTargetYml {
	mode?: unknown;
	game?: unknown;
	engine?: unknown;
	vcs?: unknown;
	uproject?: unknown;
	toolchain?: unknown;
	ignore?: unknown;
	contract?: unknown;
}

function parseToolchain(value: unknown): TargetToolchain {
	if (value === undefined || value === null) return {};
	if (typeof value !== "object" || Array.isArray(value)) {
		fail("invalid-config", "target.yml: 'toolchain' must be a mapping of name to command");
	}
	const out: TargetToolchain = {};
	for (const [name, cmd] of Object.entries(value as Record<string, unknown>)) {
		if (typeof cmd !== "string" || cmd.trim() === "") {
			fail("invalid-config", `target.yml: toolchain.${name} must be a non-empty string`);
		}
		out[name] = cmd;
	}
	return out;
}

function parseIgnore(value: unknown): TargetIgnore {
	if (value === undefined || value === null) return { deny_globs: [] };
	if (typeof value !== "object" || Array.isArray(value)) {
		fail("invalid-config", "target.yml: 'ignore' must be a mapping");
	}
	const raw = value as Record<string, unknown>;
	return { deny_globs: stringArray(raw.deny_globs, "ignore.deny_globs") };
}

function parseContract(value: unknown): TargetContract {
	if (value === undefined || value === null) {
		return { forbidden_paths: [], conventions: null, docs: [] };
	}
	if (typeof value !== "object" || Array.isArray(value)) {
		fail("invalid-config", "target.yml: 'contract' must be a mapping");
	}
	const raw = value as Record<string, unknown>;
	const conventions =
		raw.conventions === undefined || raw.conventions === null
			? null
			: typeof raw.conventions === "string"
				? raw.conventions
				: fail("invalid-config", "target.yml: contract.conventions must be a string");
	return {
		forbidden_paths: stringArray(raw.forbidden_paths, "contract.forbidden_paths"),
		conventions,
		docs: stringArray(raw.docs, "contract.docs"),
	};
}

function readTargetYml(controlRoot: string): RawTargetYml {
	const file = targetYmlPath(controlRoot);
	let text: string;
	try {
		text = fs.readFileSync(file, "utf-8");
	} catch {
		return {};
	}
	let parsed: unknown;
	try {
		parsed = parse(text);
	} catch (err) {
		fail(
			"invalid-yaml",
			`target.yml is not valid YAML (${targetYmlPath(controlRoot)}): ${err instanceof Error ? err.message : String(err)}`,
		);
	}
	if (parsed === undefined || parsed === null) return {};
	if (typeof parsed !== "object" || Array.isArray(parsed)) {
		fail("invalid-config", "target.yml: top level must be a mapping");
	}
	return parsed as RawTargetYml;
}

/**
 * Resolve the workspace configuration for a control root.
 *
 * Precedence: MW_TARGET_GAME/MW_TARGET_ENGINE env > target.yml > single
 * fallback (gameRoot === controlRoot). Throws TargetConfigError on
 * contradictory or unusable configuration (fail-closed, never a silent
 * single fallback).
 */
export function resolveWorkspaceConfig(controlRoot: string): WorkspaceConfig {
	const raw = readTargetYml(controlRoot);

	const envGame = process.env[ENV_TARGET_GAME]?.trim() || null;
	const envEngine = process.env[ENV_TARGET_ENGINE]?.trim() || null;

	const fileMode = raw.mode === undefined ? null : requireString(raw.mode, "mode");
	if (fileMode !== null && fileMode !== "dual" && fileMode !== "single") {
		fail("invalid-config", `target.yml: 'mode' must be 'dual' or 'single', got '${fileMode}'`);
	}
	const fileGame = optionalString(raw.game, "game");
	const fileEngine = optionalString(raw.engine, "engine");

	const gameRaw = envGame ?? fileGame;
	const engineRaw = envEngine ?? fileEngine;

	// File-internal contradictions fail closed before precedence applies.
	if (fileMode === "single" && fileGame !== null) {
		fail("invalid-config", "target.yml: mode 'single' with a 'game' field is contradictory");
	}
	if (fileMode === "dual" && fileGame === null && envGame === null) {
		fail("invalid-config", "target.yml: mode 'dual' requires a game root (field 'game' or env MW_TARGET_GAME)");
	}

	// Mode establishment: a game root (env or file) forces dual; env game
	// deliberately overrides an explicit file 'single'.
	let mode: WorkspaceMode;
	if (gameRaw !== null) {
		mode = "dual";
	} else {
		mode = "single";
	}

	if (engineRaw !== null && mode === "single") {
		fail("invalid-config", "target.yml: 'engine' requires dual mode (configure 'game' first)");
	}

	const gameRoot =
		mode === "dual" ? normalizeRoot(gameRaw as string, controlRoot) : normalizeRoot(controlRoot, controlRoot);

	return {
		mode,
		controlRoot: normalizeRoot(controlRoot, controlRoot),
		gameRoot,
		engineRoot: engineRaw === null ? null : normalizeRoot(engineRaw, controlRoot),
		vcs: optionalString(raw.vcs, "vcs"),
		uproject: optionalString(raw.uproject, "uproject"),
		toolchain: parseToolchain(raw.toolchain),
		ignore: parseIgnore(raw.ignore),
		contract: parseContract(raw.contract),
		source: envGame !== null ? "env" : gameRaw !== null || fileMode !== null ? "target-yml" : "default",
	};
}

/**
 * Resolve {uproject} (D-014): explicit field wins (must exist on disk);
 * otherwise exactly one *.uproject under the game root. 0 or many is an
 * error carrying the count — never a guess.
 */
export function discoverUproject(gameRoot: string, explicit?: string | null): string {
	if (explicit !== null && explicit !== undefined) {
		const p = path.resolve(gameRoot, explicit);
		if (!fs.existsSync(p)) {
			fail("uproject-not-found", `explicit uproject '${explicit}' not found under game root ${gameRoot}`);
		}
		return p;
	}
	let entries: string[];
	try {
		entries = fs.readdirSync(gameRoot);
	} catch (err) {
		fail(
			"invalid-config",
			`game root is not readable (${gameRoot}): ${err instanceof Error ? err.message : String(err)}`,
		);
	}
	const matches = entries.filter((e) => e.toLowerCase().endsWith(".uproject"));
	if (matches.length !== 1) {
		fail(
			"ambiguous-uproject",
			`expected exactly one *.uproject under game root ${gameRoot}, found ${matches.length}` +
				(matches.length > 1 ? ` (${matches.join(", ")})` : ""),
		);
	}
	return path.join(gameRoot, matches[0]);
}

/**
 * Render one toolchain command template (AC-004, fail-closed). Replaces
 * {game}/{engine}/{uproject}; a token whose root is unconfigured throws
 * with the field name and the original command — no game-root fallback.
 */
export function renderToolchainCommand(command: string, config: WorkspaceConfig): string {
	let out = command;
	if (out.includes("{game}")) {
		out = out.split("{game}").join(config.gameRoot);
	}
	if (out.includes("{engine}")) {
		if (config.engineRoot === null) {
			fail(
				"missing-field",
				`toolchain command references {engine} but engine is not configured (dual mode requires it): ${command}`,
			);
		}
		out = out.split("{engine}").join(config.engineRoot);
	}
	if (out.includes("{uproject}")) {
		const uproject = discoverUproject(config.gameRoot, config.uproject);
		out = out.split("{uproject}").join(uproject);
	}
	return out;
}
