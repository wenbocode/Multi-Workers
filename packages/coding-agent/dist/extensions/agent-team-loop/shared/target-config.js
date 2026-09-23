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
import * as fs from "node:fs";
import * as path from "node:path";
import { isMap, isScalar, parse, parseDocument } from "yaml";
/** Env override for the game root (highest precedence, D-011). */
export const ENV_TARGET_GAME = "MW_TARGET_GAME";
/** Env override for the engine root. */
export const ENV_TARGET_ENGINE = "MW_TARGET_ENGINE";
/** Env override for the partition parent root (spec §1.5 EP family; only
 * honored when partition is the active mode — cross-family env is a
 * rule-table row 3 error). */
export const ENV_PARTITION_PARENT = "MW_PARTITION_PARENT";
/** Env override for the partition root (= worker cwd). */
export const ENV_PARTITION_ROOT = "MW_PARTITION_ROOT";
export class TargetConfigError extends Error {
    kind;
    constructor(kind, message) {
        super(message);
        this.name = "TargetConfigError";
        this.kind = kind;
    }
}
const TARGET_YML = "target.yml";
function fail(kind, message) {
    throw new TargetConfigError(kind, message);
}
function requireString(value, field) {
    if (typeof value !== "string" || value.trim() === "") {
        fail("invalid-config", `target.yml: field '${field}' must be a non-empty string`);
    }
    return value;
}
function optionalString(value, field) {
    return value === undefined || value === null ? null : requireString(value, field);
}
function stringArray(value, field) {
    if (value === undefined || value === null)
        return [];
    if (!Array.isArray(value) || value.some((e) => typeof e !== "string" || e.trim() === "")) {
        fail("invalid-config", `target.yml: field '${field}' must be a list of non-empty strings`);
    }
    return value;
}
/**
 * Normalize a configured root: resolve against controlRoot (relative
 * entries allowed for local convenience), then realpath when the path
 * exists so junctions/case fold like the read-scope normalizer. A missing
 * tail canonicalizes the longest existing prefix first — mirrors Python's
 * Path.resolve(strict=False) (8.3/short-path and junction forms of every
 * existing component), keeping two roots comparable when only one exists
 * (the partition root-relation check depends on this).
 */
function normalizeRoot(raw, controlRoot) {
    const resolved = path.resolve(controlRoot, raw);
    try {
        return fs.realpathSync.native(resolved);
    }
    catch {
        let dir = resolved;
        const tail = [];
        for (;;) {
            const parent = path.dirname(dir);
            if (parent === dir)
                return resolved; // reached the drive root with nothing existing
            try {
                const real = fs.realpathSync.native(dir);
                return tail.length === 0 ? real : path.join(real, ...tail);
            }
            catch {
                tail.unshift(path.basename(dir));
                dir = parent;
            }
        }
    }
}
/** Resolve the target.yml path for a control root (exported for tests). */
export function targetYmlPath(controlRoot) {
    return path.join(controlRoot, ".agenticdoc", TARGET_YML);
}
function parseToolchain(value) {
    if (value === undefined || value === null)
        return {};
    if (typeof value !== "object" || Array.isArray(value)) {
        fail("invalid-config", "target.yml: 'toolchain' must be a mapping of name to command");
    }
    const out = {};
    for (const [name, cmd] of Object.entries(value)) {
        if (typeof cmd !== "string" || cmd.trim() === "") {
            fail("invalid-config", `target.yml: toolchain.${name} must be a non-empty string`);
        }
        out[name] = cmd;
    }
    return out;
}
function parseIgnore(value) {
    if (value === undefined || value === null)
        return { deny_globs: [] };
    if (typeof value !== "object" || Array.isArray(value)) {
        fail("invalid-config", "target.yml: 'ignore' must be a mapping");
    }
    const raw = value;
    return { deny_globs: stringArray(raw.deny_globs, "ignore.deny_globs") };
}
function parseContract(value) {
    if (value === undefined || value === null) {
        return { forbidden_paths: [], conventions: null, docs: [] };
    }
    if (typeof value !== "object" || Array.isArray(value)) {
        fail("invalid-config", "target.yml: 'contract' must be a mapping");
    }
    const raw = value;
    const conventions = raw.conventions === undefined || raw.conventions === null
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
/**
 * Read the raw `.agenticdoc/target.yml` mapping for a control root. Exported
 * for rag/config.ts (T-01, mw-rag-integration) so the RAG layer reuses this
 * single target.yml reader instead of adding a second parser (P-003); no
 * semantic change to the resolver.
 */
export function rawTargetYml(controlRoot) {
    const file = targetYmlPath(controlRoot);
    let text;
    try {
        text = fs.readFileSync(file, "utf-8");
    }
    catch {
        return {};
    }
    let parsed;
    try {
        parsed = parse(text);
    }
    catch (err) {
        fail("invalid-yaml", `target.yml is not valid YAML (${targetYmlPath(controlRoot)}): ${err instanceof Error ? err.message : String(err)}`);
    }
    if (parsed === undefined || parsed === null) {
        // mw-target-partition FIX-10: a non-blank document that parses to YAML
        // null (`null` / `~`) is a non-mapping top level — fail closed like the
        // list/scalar shapes. Only a blank file (0 bytes, pure whitespace, or a
        // leading UTF-8 BOM with no content — the degenerate Windows-editor
        // shape) keeps the historical no-config shape (single).
        if (text.trim() === "" || text.replace(/^\uFEFF/, "").trim() === "")
            return {};
        fail("invalid-config", "target.yml: top level must be a mapping");
    }
    if (typeof parsed !== "object" || Array.isArray(parsed)) {
        fail("invalid-config", "target.yml: top level must be a mapping");
    }
    return parsed;
}
// ── v2 single-file format (mw-target-partition spec §1.3/§1.5, design
// D-001..D-004) ──────────────────────────────────────────────────────────────
/** Rule-table row 1: a v2 file (top-level `active:`) must not carry v1
 * flat fields alongside. */
const V1_SHAPE_KEYS = ["mode", "game", "engine", "uproject"];
/** v2 top-level whitelist (AC-003(c)). */
const V2_TOP_KEYS = new Set(["active", "dual", "partition"]);
/** Mode-block whitelists (AC-003(d)/(e)). */
const DUAL_BLOCK_KEYS = new Set(["game", "engine", "vcs", "uproject", "toolchain", "ignore", "contract"]);
const PARTITION_BLOCK_KEYS = new Set(["parent", "partition", "vcs", "roots", "toolchain", "ignore", "contract"]);
/** roots key constraints (AC-003(f)). */
const ROOTS_RESERVED = new Set(["parent", "partition", "game", "engine", "uproject"]);
const ROOTS_NAME_RE = /^[A-Za-z0-9_-]+$/;
/** File-shape judgment (design D-001) + rule-table row 1: "none" when no
 * target.yml exists, "v2" when the top level has an `active:` key (a v1
 * flat field alongside raises the mixed-format error), else "v1". */
function detectShape(raw, fileExists) {
    if (!fileExists)
        return "none";
    if ("active" in raw) {
        const mixed = V1_SHAPE_KEYS.filter((k) => k in raw);
        if (mixed.length > 0) {
            fail("invalid-config", `target.yml: mixed format — 'active:' key (v2) together with v1 top-level field(s) ${mixed.join(", ")}; use either v2 (active + mode blocks) or v1 (flat fields), not both`);
        }
        return "v2";
    }
    return "v1";
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
export function decideActiveMode(input) {
    const ep = [];
    if (input.envPartitionParent !== null)
        ep.push(ENV_PARTITION_PARENT);
    if (input.envPartitionRoot !== null)
        ep.push(ENV_PARTITION_ROOT);
    const et = [];
    if (input.envTargetGame !== null)
        et.push(ENV_TARGET_GAME);
    if (input.envTargetEngine !== null)
        et.push(ENV_TARGET_ENGINE);
    if (input.fileShape === "v2") {
        const active = input.active;
        if (active === null || (active !== "single" && active !== "dual" && active !== "partition")) {
            // row 2
            fail("invalid-config", `target.yml: 'active' must be one of 'single', 'dual', 'partition', got ${active === null ? "null" : `'${active}'`}`);
        }
        if (active === "dual" && ep.length > 0) {
            // row 3
            fail("invalid-config", `cross env: ${ep.join(", ")} must not be set when active is 'dual' (dual mode uses MW_TARGET_GAME/MW_TARGET_ENGINE)`);
        }
        if (active === "partition" && et.length > 0) {
            // row 3
            fail("invalid-config", `cross env: ${et.join(", ")} must not be set when active is 'partition' (partition mode uses MW_PARTITION_PARENT/MW_PARTITION_ROOT)`);
        }
        if (active === "single" && ep.length + et.length > 0) {
            // row 3
            fail("invalid-config", `cross env: ${[...ep, ...et].join(", ")} must not be set when active is 'single'`);
        }
        if (active === "single")
            return { mode: "single", block: null }; // row 5
        return { mode: active, block: active }; // rows 6/7
    }
    if (input.fileShape === "v1") {
        if (ep.length > 0) {
            // row 3 (v1 clause)
            fail("invalid-config", `cross env: ${ep.join(", ")} requires a v2 target.yml with 'active: partition' (v1 format has no partition mode)`);
        }
        return { mode: "legacy", block: null }; // row 8
    }
    // fileShape === "none"
    if (ep.length > 0 && et.length > 0) {
        // row 3 (no-file clause)
        fail("invalid-config", `cross env: ${ep.join(", ")} and ${et.join(", ")} are mutually exclusive (partition env vs dual env); set only one family`);
    }
    if (ep.length === 2)
        return { mode: "partition", block: null }; // row 9
    if (ep.length === 1) {
        // row 10
        const missing = input.envPartitionRoot === null ? ENV_PARTITION_ROOT : ENV_PARTITION_PARENT;
        fail("invalid-config", `incomplete partition env activation: ${missing} is not set (partition env requires both MW_PARTITION_PARENT and MW_PARTITION_ROOT)`);
    }
    return { mode: "legacy", block: null }; // rows 11/12
}
/** AC-003(c): the v2 top level allows exactly active/dual/partition. */
function checkV2TopWhitelist(raw) {
    const extra = Object.keys(raw).filter((k) => !V2_TOP_KEYS.has(k));
    if (extra.length > 0) {
        fail("invalid-config", `target.yml: unexpected top-level key(s) in v2 format: ${extra.join(", ")} (allowed: active, dual, partition)`);
    }
}
/** Rule-table row 4: active names a mode whose block must exist. */
function v2Block(raw, name) {
    if (!(name in raw) || raw[name] === null || raw[name] === undefined) {
        fail("invalid-config", `target.yml: active '${name}' but the '${name}' block is missing`);
    }
    const block = raw[name];
    if (typeof block !== "object" || Array.isArray(block)) {
        fail("invalid-config", `target.yml: the '${name}' block must be a mapping`);
    }
    return block;
}
/** AC-003(d)/(e): mode-block whitelists (fields of the other mode — or any
 * unknown key — inside a block are a structural error). */
function checkBlockKeys(block, name, allowed) {
    const extra = Object.keys(block).filter((k) => !allowed.has(k));
    if (extra.length > 0) {
        fail("invalid-config", `target.yml: unexpected key(s) in the '${name}' block: ${extra.join(", ")}`);
    }
}
/** partition.roots (AC-001/AC-003(f)): name -> normalized path; names must
 * match [A-Za-z0-9_-]+ and avoid the reserved names; relative paths anchor
 * to the control root (same rule as game/engine).
 *
 * mw-target-partition FIX-5 (TS/Py parity): parse() objectifies mapping
 * keys — an unquoted `123:` / `true:` arrives here as the string
 * "123"/"true" and slips past the charset check, while Python's yaml keeps
 * the int/bool key and rejects it. The AST document preserves the source
 * key types, so the v2 partition path hands the roots node in and every
 * Pair's key is type-checked (mirroring mw_common's isinstance walk and its
 * exact rejection message); a quoted `"123":` key is a string on both
 * sides and stays legal. */
function checkRootsKeyTypes(rootsAst) {
    for (const pair of rootsAst.items) {
        if (!isScalar(pair.key) || typeof pair.key.value !== "string") {
            fail("invalid-config", "target.yml: roots keys must be strings");
        }
    }
}
/** Read the roots mapping NODE of a v2 partition block (source-order Pairs
 * with unstringified key types); null when there is no file (rule-table row
 * 9: env-only partition) or the node is not a mapping (the objectified
 * value's own mapping check rejects that shape first). */
function readRootsAst(controlRoot) {
    const file = targetYmlPath(controlRoot);
    let text;
    try {
        text = fs.readFileSync(file, "utf-8");
    }
    catch {
        return null;
    }
    const node = parseDocument(text).getIn(["partition", "roots"], true);
    return isMap(node) ? node : null;
}
function parseRoots(value, controlRoot, rootsAst) {
    if (value === undefined || value === null)
        return {};
    if (typeof value !== "object" || Array.isArray(value)) {
        fail("invalid-config", "target.yml: partition field 'roots' must be a mapping of name to path");
    }
    if (rootsAst !== null)
        checkRootsKeyTypes(rootsAst);
    const out = {};
    for (const [name, rawPath] of Object.entries(value)) {
        if (name === "" || !ROOTS_NAME_RE.test(name) || ROOTS_RESERVED.has(name)) {
            fail("invalid-config", `target.yml: roots key '${name}' is invalid (must match [A-Za-z0-9_-]+ and must not be a reserved name: parent, partition, game, engine, uproject)`);
        }
        if (typeof rawPath !== "string" || rawPath.trim() === "") {
            fail("invalid-config", `target.yml: roots.${name} must be a non-empty string`);
        }
        out[name] = normalizeRoot(rawPath, controlRoot);
    }
    return out;
}
/** Case-insensitive-on-Windows comparison form (mirrors os.path.normcase). */
function relationNorm(p) {
    const normalized = path.normalize(p);
    return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}
/** AC-003(g): parent and partition must be distinct and non-nested
 * (compared on the normalized roots, case-insensitive on Windows). */
function checkRootRelation(parentRoot, partitionRoot) {
    const a = relationNorm(parentRoot);
    const b = relationNorm(partitionRoot);
    if (a === b || a.startsWith(b + path.sep) || b.startsWith(a + path.sep)) {
        fail("invalid-config", `target.yml: partition root relation is invalid — parent (${parentRoot}) and partition (${partitionRoot}) must not be equal or nested`);
    }
}
/** Partition-mode assembly (rule-table rows 7/9): EP overlay over the block
 * fields, required-field checks, roots + root-relation validation (field
 * layer, applied after the row hit). rootsAst carries the v2 partition
 * block's roots mapping node for the AST-level key-type check (FIX-5);
 * null for the env-only row 9 (no file to read). */
function loadPartitionConfig(controlRoot, controlNorm, block, envParent, envPartition, rootsAst) {
    let parentRaw = block === null ? null : block.parent;
    let partitionRaw = block === null ? null : block.partition;
    if (envParent !== null)
        parentRaw = envParent;
    if (envPartition !== null)
        partitionRaw = envPartition;
    if (parentRaw === null || parentRaw === undefined) {
        fail("invalid-config", "target.yml: partition mode requires field 'parent' (partition block or env MW_PARTITION_PARENT)");
    }
    if (partitionRaw === null || partitionRaw === undefined) {
        fail("invalid-config", "target.yml: partition mode requires field 'partition' (partition block or env MW_PARTITION_ROOT)");
    }
    const parent = requireString(parentRaw, "parent");
    const partition = requireString(partitionRaw, "partition");
    const parentRoot = normalizeRoot(parent, controlRoot);
    const partitionRoot = normalizeRoot(partition, controlRoot);
    const roots = parseRoots(block === null ? null : block.roots, controlRoot, rootsAst);
    checkRootRelation(parentRoot, partitionRoot);
    return {
        mode: "partition",
        controlRoot: controlNorm,
        gameRoot: null,
        engineRoot: null,
        parentRoot,
        partitionRoot,
        roots,
        vcs: optionalString(block === null ? null : block.vcs, "vcs"),
        uproject: null,
        toolchain: parseToolchain(block === null ? null : block.toolchain),
        ignore: parseIgnore(block === null ? null : block.ignore),
        contract: parseContract(block === null ? null : block.contract),
        source: envParent !== null || envPartition !== null ? "env" : "target-yml",
    };
}
/** v1 / no-file resolution — the pre-partition logic, byte-identical (spec
 * §1.5 rows 8/11/12; AC-013 zero-regression). */
function resolveLegacyConfig(controlRoot, raw, envGame, envEngine) {
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
    let mode;
    if (gameRaw !== null) {
        mode = "dual";
    }
    else {
        mode = "single";
    }
    if (engineRaw !== null && mode === "single") {
        fail("invalid-config", "target.yml: 'engine' requires dual mode (configure 'game' first)");
    }
    const gameRoot = mode === "dual" ? normalizeRoot(gameRaw, controlRoot) : normalizeRoot(controlRoot, controlRoot);
    return {
        mode,
        controlRoot: normalizeRoot(controlRoot, controlRoot),
        gameRoot,
        engineRoot: engineRaw === null ? null : normalizeRoot(engineRaw, controlRoot),
        parentRoot: null,
        partitionRoot: null,
        roots: null,
        vcs: optionalString(raw.vcs, "vcs"),
        uproject: optionalString(raw.uproject, "uproject"),
        toolchain: parseToolchain(raw.toolchain),
        ignore: parseIgnore(raw.ignore),
        contract: parseContract(raw.contract),
        source: envGame !== null ? "env" : gameRaw !== null || fileMode !== null ? "target-yml" : "default",
    };
}
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
export function resolveWorkspaceConfig(controlRoot) {
    const fileExists = fs.existsSync(targetYmlPath(controlRoot));
    const raw = rawTargetYml(controlRoot);
    const envGame = process.env[ENV_TARGET_GAME]?.trim() || null;
    const envEngine = process.env[ENV_TARGET_ENGINE]?.trim() || null;
    const envParent = process.env[ENV_PARTITION_PARENT]?.trim() || null;
    const envPartition = process.env[ENV_PARTITION_ROOT]?.trim() || null;
    const fileShape = detectShape(raw, fileExists);
    let active = null;
    if (fileShape === "v2") {
        const value = raw.active;
        active = typeof value === "string" ? value : value === null || value === undefined ? null : String(value);
    }
    const decision = decideActiveMode({
        fileShape,
        active,
        envPartitionParent: envParent,
        envPartitionRoot: envPartition,
        envTargetGame: envGame,
        envTargetEngine: envEngine,
    });
    if (decision.mode === "legacy") {
        return resolveLegacyConfig(controlRoot, raw, envGame, envEngine);
    }
    const controlNorm = normalizeRoot(controlRoot, controlRoot);
    if (decision.mode === "single") {
        // Row 5: mode blocks are parked (not parsed, not validated); the
        // top-level whitelist still applies (AC-003(c)).
        checkV2TopWhitelist(raw);
        return {
            mode: "single",
            controlRoot: controlNorm,
            gameRoot: controlNorm,
            engineRoot: null,
            parentRoot: null,
            partitionRoot: null,
            roots: null,
            vcs: null,
            uproject: null,
            toolchain: {},
            ignore: { deny_globs: [] },
            contract: { forbidden_paths: [], conventions: null, docs: [] },
            source: "target-yml",
        };
    }
    if (decision.mode === "dual") {
        // Row 6: fields from the dual block; the ET overlay keeps the legacy
        // precedence rules (env > block).
        const block = v2Block(raw, "dual"); // row 4
        checkV2TopWhitelist(raw);
        checkBlockKeys(block, "dual", DUAL_BLOCK_KEYS);
        const config = resolveLegacyConfig(controlRoot, {
            mode: "dual",
            game: block.game,
            engine: block.engine,
            vcs: block.vcs,
            uproject: block.uproject,
            toolchain: block.toolchain,
            ignore: block.ignore,
            contract: block.contract,
        }, envGame, envEngine);
        return config;
    }
    // decision.mode === "partition"
    if (fileShape === "v2") {
        // Row 7: fields from the partition block, EP overlay on top.
        const block = v2Block(raw, "partition"); // row 4
        checkV2TopWhitelist(raw);
        checkBlockKeys(block, "partition", PARTITION_BLOCK_KEYS);
        return loadPartitionConfig(controlRoot, controlNorm, block, envParent, envPartition, readRootsAst(controlRoot));
    }
    // Row 9: partition activated purely by env (no file).
    return loadPartitionConfig(controlRoot, controlNorm, null, envParent, envPartition, null);
}
/**
 * Resolve {uproject} (D-014): explicit field wins (must exist on disk);
 * otherwise exactly one *.uproject under the game root. 0 or many is an
 * error carrying the count — never a guess.
 */
export function discoverUproject(gameRoot, explicit) {
    if (explicit !== null && explicit !== undefined) {
        const p = path.resolve(gameRoot, explicit);
        if (!fs.existsSync(p)) {
            fail("uproject-not-found", `explicit uproject '${explicit}' not found under game root ${gameRoot}`);
        }
        return p;
    }
    let entries;
    try {
        entries = fs.readdirSync(gameRoot);
    }
    catch (err) {
        fail("invalid-config", `game root is not readable (${gameRoot}): ${err instanceof Error ? err.message : String(err)}`);
    }
    const matches = entries.filter((e) => e.toLowerCase().endsWith(".uproject"));
    if (matches.length !== 1) {
        fail("ambiguous-uproject", `expected exactly one *.uproject under game root ${gameRoot}, found ${matches.length}` +
            (matches.length > 1 ? ` (${matches.join(", ")})` : ""));
    }
    return path.join(gameRoot, matches[0]);
}
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
export function renderToolchainCommand(command, config) {
    if (config.mode === "partition") {
        return renderPartitionCommand(command, config);
    }
    // dual/single always carry a game root — partition (the only null case)
    // is dispatched above; the guard is the type-level proof.
    const gameRoot = config.gameRoot;
    if (gameRoot === null) {
        fail("missing-field", `toolchain command requires a game root but none is configured: ${command}`);
    }
    let out = command;
    if (out.includes("{game}")) {
        out = out.split("{game}").join(gameRoot);
    }
    if (out.includes("{engine}")) {
        if (config.engineRoot === null) {
            fail("missing-field", `toolchain command references {engine} but engine is not configured (dual mode requires it): ${command}`);
        }
        out = out.split("{engine}").join(config.engineRoot);
    }
    if (out.includes("{uproject}")) {
        const uproject = discoverUproject(gameRoot, config.uproject);
        out = out.split("{uproject}").join(uproject);
    }
    return out;
}
/** Placeholder-shaped token in a partition toolchain command (AC-004). */
const TOKEN_RE = /\{([A-Za-z0-9_-]+)\}/;
/** partition-mode token set (AC-004): {parent}/{partition}/{<root name>};
 * any leftover placeholder-shaped token is an undefined placeholder. */
function renderPartitionCommand(command, config) {
    let out = command;
    if (config.parentRoot !== null) {
        out = out.split("{parent}").join(config.parentRoot);
    }
    if (config.partitionRoot !== null) {
        out = out.split("{partition}").join(config.partitionRoot);
    }
    const roots = config.roots ?? {};
    for (const [name, root] of Object.entries(roots)) {
        out = out.split(`{${name}}`).join(root);
    }
    const leftover = TOKEN_RE.exec(out);
    if (leftover !== null) {
        const defined = ["{parent}", "{partition}", ...[...Object.keys(roots)].sort().map((n) => `{${n}}`)];
        fail("missing-field", `toolchain command references undefined placeholder '${leftover[0]}' (partition mode defines: ${defined.join(", ")}): ${command}`);
    }
    return out;
}
//# sourceMappingURL=target-config.js.map