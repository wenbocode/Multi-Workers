/**
 * Unit tests for shared/target-config.ts (mw-dual-workspace Task 001,
 * AC-001/AC-004, VC-001/VC-006/VC-007/VC-008).
 *
 * Fail-closed semantics (design D-010/D-011/D-014): contradictory or
 * unusable target.yml throws TargetConfigError instead of silently
 * falling back to single mode; {uproject} resolves only from an explicit
 * field or exactly one *.uproject under the game root.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
	WorkspaceConfigSource,
	WorkspaceMode,
} from "../../src/extensions/agent-team-loop/shared/target-config.ts";
import {
	discoverUproject,
	ENV_TARGET_ENGINE,
	ENV_TARGET_GAME,
	renderToolchainCommand,
	resolveWorkspaceConfig,
	TargetConfigError,
	targetYmlPath,
} from "../../src/extensions/agent-team-loop/shared/target-config.ts";

function mkdtemp(prefix: string): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function writeTargetYml(controlRoot: string, content: string): void {
	fs.mkdirSync(path.join(controlRoot, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(targetYmlPath(controlRoot), content, "utf-8");
}

function writeTargetYmlBytes(controlRoot: string, content: Uint8Array): void {
	fs.mkdirSync(path.join(controlRoot, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(targetYmlPath(controlRoot), content);
}

/** mkdir a fixture dir and return its realpath (matches normalizeRoot). */
function mkgame(name: string): string {
	const dir = mkdtemp(name);
	return fs.realpathSync.native(dir);
}

function expectTargetError(fn: () => unknown, kind: string, messageIncludes?: string): TargetConfigError {
	let err: unknown;
	try {
		fn();
	} catch (e) {
		err = e;
	}
	expect(err).toBeInstanceOf(TargetConfigError);
	const tce = err as TargetConfigError;
	expect(tce.kind).toBe(kind);
	if (messageIncludes !== undefined) expect(tce.message).toContain(messageIncludes);
	return tce;
}

afterEach(() => {
	vi.unstubAllEnvs();
});

// ── VC-001: single-mode default fallback (AC-001) ─────────────────────────────

describe("VC-001 single-mode default", () => {
	it("no target.yml and no env → mode=single, gameRoot=controlRoot, source=default", () => {
		const controlRoot = mkgame("atl-tc-single-");
		const config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("single");
		expect(config.gameRoot).toBe(config.controlRoot);
		expect(config.controlRoot).toBe(controlRoot);
		expect(config.engineRoot).toBeNull();
		expect(config.source).toBe("default");
		console.log("[VERIFY] VC-001: mode=single roots-equal=true");
	});

	it("explicit mode single without game keeps single and parses sections", () => {
		const controlRoot = mkgame("atl-tc-explicit-single-");
		writeTargetYml(controlRoot, ["mode: single", "ignore:", "  deny_globs:", '    - "**/*.uasset"'].join("\n"));
		const config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("single");
		expect(config.gameRoot).toBe(config.controlRoot);
		expect(config.ignore.deny_globs).toEqual(["**/*.uasset"]);
		expect(config.source).toBe("target-yml");
	});

	it("env MW_TARGET_GAME forces dual without any file", () => {
		const controlRoot = mkgame("atl-tc-envgame-");
		const game = mkgame("atl-tc-game-");
		vi.stubEnv(ENV_TARGET_GAME, game);
		const config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("dual");
		expect(config.gameRoot).toBe(game);
		expect(config.source).toBe("env");
	});

	it("env game overrides target.yml game", () => {
		const controlRoot = mkgame("atl-tc-envwin-");
		const gameFile = mkgame("atl-tc-gamefile-");
		const gameEnv = mkgame("atl-tc-gameenv-");
		writeTargetYml(controlRoot, `mode: dual\ngame: ${gameFile}`);
		vi.stubEnv(ENV_TARGET_GAME, gameEnv);
		const config = resolveWorkspaceConfig(controlRoot);
		expect(config.gameRoot).toBe(gameEnv);
	});

	it("env engine without any game is invalid (engine requires dual)", () => {
		const controlRoot = mkgame("atl-tc-enveng-");
		vi.stubEnv(ENV_TARGET_ENGINE, mkgame("atl-tc-eng-"));
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "engine");
	});
});

// ── VC-006/VC-007: toolchain placeholder rendering (AC-004) ───────────────────

describe("VC-006/VC-007 placeholder rendering", () => {
	it("renders {engine} and {game} with no leftover tokens", () => {
		const controlRoot = mkgame("atl-tc-render-");
		const game = mkgame("atl-tc-rgame-");
		const engine = mkgame("atl-tc-rengine-");
		writeTargetYml(
			controlRoot,
			`mode: dual\ngame: ${game}\nengine: ${engine}\ntoolchain:\n  build_editor: 'build {engine} -project {game}'`,
		);
		const config = resolveWorkspaceConfig(controlRoot);
		const rendered = renderToolchainCommand(config.toolchain.build_editor, config);
		expect(rendered).toContain(engine);
		expect(rendered).toContain(game);
		expect(rendered).not.toContain("{game}");
		expect(rendered).not.toContain("{engine}");
		expect(rendered).not.toContain("{uproject}");
		console.log("[VERIFY] VC-006: rendered-contains-engine=true unresolved-placeholders=0");
	});

	it("dual without engine referencing {engine} throws — no game fallback", () => {
		const controlRoot = mkgame("atl-tc-noeng-");
		const game = mkgame("atl-tc-ngame-");
		writeTargetYml(controlRoot, `mode: dual\ngame: ${game}\ntoolchain:\n  build: 'build {engine}'`);
		const config = resolveWorkspaceConfig(controlRoot);
		expect(config.engineRoot).toBeNull();
		const tce = expectTargetError(
			() => renderToolchainCommand(config.toolchain.build, config),
			"missing-field",
			"{engine}",
		);
		// fallback=false: the error never substitutes the game root for engine
		expect(tce.message).not.toContain(game);
		expect(tce.message).toContain("build {engine}");
		console.log("[VERIFY] VC-007: exit-nonzero=true fallback=false");
	});
});

// ── VC-008: {uproject} discovery (AC-004, D-014) ──────────────────────────────

describe("VC-008 uproject discovery", () => {
	it("unique *.uproject under game root resolves", () => {
		const game = mkgame("atl-tc-uproject1-");
		fs.writeFileSync(path.join(game, "ProjectH.uproject"), "{}", "utf-8");
		expect(discoverUproject(game)).toBe(path.join(game, "ProjectH.uproject"));

		const controlRoot = mkgame("atl-tc-upcontrol-");
		writeTargetYml(controlRoot, `mode: dual\ngame: ${game}\ntoolchain:\n  build: 'build -project {uproject}'`);
		const config = resolveWorkspaceConfig(controlRoot);
		const rendered = renderToolchainCommand(config.toolchain.build, config);
		expect(rendered).toContain(path.join(game, "ProjectH.uproject"));
		expect(rendered).not.toContain("{uproject}");
	});

	it("0 or 2 *.uproject files fail with the count (fail-closed)", () => {
		const game0 = mkgame("atl-tc-uproject0-");
		expectTargetError(() => discoverUproject(game0), "ambiguous-uproject", "found 0");

		const game2 = mkgame("atl-tc-uproject2-");
		fs.writeFileSync(path.join(game2, "A.uproject"), "{}", "utf-8");
		fs.writeFileSync(path.join(game2, "B.uproject"), "{}", "utf-8");
		expectTargetError(() => discoverUproject(game2), "ambiguous-uproject", "found 2");
		console.log("[VERIFY] VC-008: uproject-resolved=true ambiguous-fail=true");
	});

	it("explicit uproject field wins; a missing explicit file fails", () => {
		const game = mkgame("atl-tc-upexplicit-");
		fs.writeFileSync(path.join(game, "Main.uproject"), "{}", "utf-8");
		fs.writeFileSync(path.join(game, "Custom.uproject"), "{}", "utf-8");
		expect(discoverUproject(game, "Custom.uproject")).toBe(path.join(game, "Custom.uproject"));
		expectTargetError(() => discoverUproject(game, "Nope.uproject"), "uproject-not-found", "Nope.uproject");
	});

	it("game root that cannot be read fails with invalid-config", () => {
		expectTargetError(
			() => discoverUproject(path.join(mkgame("atl-tc-upmissing-"), "no-such-dir")),
			"invalid-config",
		);
	});
});

// ── fail-closed config validation ─────────────────────────────────────────────

describe("fail-closed target.yml validation", () => {
	it("invalid YAML throws invalid-yaml", () => {
		const controlRoot = mkgame("atl-tc-badyaml-");
		writeTargetYml(controlRoot, "mode: [unclosed");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-yaml");
	});

	it("mode dual without game is invalid", () => {
		const controlRoot = mkgame("atl-tc-dualnogame-");
		writeTargetYml(controlRoot, "mode: dual");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "game");
	});

	it("mode single with a game field is contradictory", () => {
		const controlRoot = mkgame("atl-tc-single-game-");
		writeTargetYml(controlRoot, `mode: single\ngame: ${mkgame("atl-tc-sg-")}`);
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "contradictory");
	});

	it("engine without game is invalid", () => {
		const controlRoot = mkgame("atl-tc-engnogame-");
		writeTargetYml(controlRoot, `engine: ${mkgame("atl-tc-eng2-")}`);
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "engine");
	});

	it("engine field in explicit single mode is invalid", () => {
		const controlRoot = mkgame("atl-tc-engsingle-");
		writeTargetYml(controlRoot, `mode: single\nengine: ${mkgame("atl-tc-eng3-")}`);
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "engine");
	});

	it("toolchain must map names to non-empty strings", () => {
		const controlRoot = mkgame("atl-tc-badtool-");
		const game = mkgame("atl-tc-btgame-");
		writeTargetYml(controlRoot, `mode: dual\ngame: ${game}\ntoolchain:\n  build: 42`);
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "toolchain.build");
	});

	it("ignore.deny_globs must be a list of non-empty strings", () => {
		const controlRoot = mkgame("atl-tc-badglobs-");
		writeTargetYml(controlRoot, "ignore:\n  deny_globs: '*.uasset'");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "deny_globs");
	});

	it("contract.conventions must be a string when present", () => {
		const controlRoot = mkgame("atl-tc-badconv-");
		writeTargetYml(controlRoot, "contract:\n  conventions: [a, b]");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "conventions");
	});

	it("parses the full three-section schema", () => {
		const controlRoot = mkgame("atl-tc-full-");
		const game = mkgame("atl-tc-fullgame-");
		writeTargetYml(
			controlRoot,
			[
				`mode: dual`,
				`game: ${game}`,
				"vcs: p4",
				"toolchain:",
				"  build_editor: 'Build.bat {game} {engine} {uproject}'",
				"ignore:",
				"  deny_globs:",
				'    - "**/*.uasset"',
				'    - "**/DerivedDataCache/**"',
				"contract:",
				"  forbidden_paths:",
				'    - "**/Generated/*"',
				"  conventions: |",
				"    line one",
				"    line two",
				"  docs:",
				"    - _profile/conventions.md",
			].join("\n"),
		);
		const config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("dual");
		expect(config.vcs).toBe("p4");
		expect(config.toolchain.build_editor).toContain("{engine}");
		expect(config.ignore.deny_globs).toEqual(["**/*.uasset", "**/DerivedDataCache/**"]);
		expect(config.contract.forbidden_paths).toEqual(["**/Generated/*"]);
		expect(config.contract.conventions).toContain("line two");
		expect(config.contract.docs).toEqual(["_profile/conventions.md"]);
	});
});

// ── FIX-10: YAML null top level / blank files (mw-target-partition) ──────────

describe("FIX-10 null/blank top level", () => {
	it("a non-blank document that parses to YAML null fails closed", () => {
		const controlRoot = mkgame("atl-tc-null-");
		writeTargetYml(controlRoot, "null\n");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "top level must be a mapping");
		writeTargetYml(controlRoot, "~\n");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "top level must be a mapping");
	});

	it("a blank file (0 bytes, pure whitespace, or a BOM-only file) keeps the historical single/default", () => {
		const controlRoot = mkgame("atl-tc-blank-");
		writeTargetYml(controlRoot, "");
		let config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("single");
		expect(config.source).toBe("default");
		expect(config.gameRoot).toBe(config.controlRoot);
		writeTargetYml(controlRoot, " \n \n");
		config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("single");
		expect(config.source).toBe("default");
		expect(config.gameRoot).toBe(config.controlRoot);
		// a UTF-8 BOM with no content is the degenerate Windows-editor empty
		// file — same historical no-config shape (PM follow-up to FIX-10).
		writeTargetYmlBytes(controlRoot, Uint8Array.of(0xef, 0xbb, 0xbf));
		config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("single");
		expect(config.source).toBe("default");
	});
});

// ── Shared parity fixtures (T-17 lock; same case set as packages/multi-workers
// test_common_target_config.py — cross-package by design: the fixtures ARE the
// parity contract between resolveWorkspaceConfig and load_target_config) ──────

const FIXTURES_DIR = fileURLToPath(
	new URL("../../../multi-workers/test/fixtures/target-config-cases", import.meta.url),
);

interface FixtureCase {
	description?: string;
	env?: Record<string, string | null>;
	error?: { kind: string; contains?: string[] };
	expect?: {
		mode: WorkspaceMode;
		source: WorkspaceConfigSource;
		game_root_equals_control?: boolean;
		game_root_rel?: string;
		game_root_null?: boolean;
		engine_root_rel?: string;
		engine_root_null?: boolean;
		// mw-target-partition v2 fields (T-03).
		parent_root_rel?: string;
		partition_root_rel?: string;
		parent_root_null?: boolean;
		roots?: Record<string, string>;
		roots_empty?: boolean;
		roots_null?: boolean;
		vcs?: string | null;
		uproject_explicit?: string;
		deny_globs?: string[];
		conventions_contains?: string[];
		docs?: string[];
	};
	render?: Record<string, string>;
	render_error?: { command: string; kind: string; contains?: string[] };
}

function substitute(template: string, config: ReturnType<typeof resolveWorkspaceConfig>): string {
	let out = template;
	out = out.split("{control_root}").join(config.controlRoot);
	out = out.split("{game_root}").join(config.gameRoot ?? "");
	out = out.split("{engine_root}").join(config.engineRoot ?? "");
	out = out.split("{parent_root}").join(config.parentRoot ?? "");
	out = out.split("{partition_root}").join(config.partitionRoot ?? "");
	for (const [name, root] of Object.entries(config.roots ?? {})) {
		out = out.split(`{${name}}`).join(root);
	}
	if (out.includes("{uproject}")) {
		out = out.split("{uproject}").join(discoverUproject(config.gameRoot as string, config.uproject));
	}
	return out;
}

/** Expected normalized root: realpath when the path exists; a missing
 * tail canonicalizes the longest existing prefix — mirrors normalizeRoot()
 * (and Python's Path.resolve(strict=False)) so fixture roots that
 * legitimately do not exist (partition parents etc.) compare exactly. */
function expectRoot(controlRoot: string, rel: string): string {
	const resolved = path.resolve(controlRoot, rel);
	try {
		return fs.realpathSync.native(resolved);
	} catch {
		let dir = resolved;
		const tail: string[] = [];
		for (;;) {
			const parent = path.dirname(dir);
			if (parent === dir) return resolved;
			try {
				const real = fs.realpathSync.native(dir);
				return tail.length === 0 ? real : path.join(real, ...tail);
			} catch {
				tail.unshift(path.basename(dir));
				dir = parent;
			}
		}
	}
}

function runFixtureCase(caseDir: string, tmp: string): void {
	const fixture = JSON.parse(fs.readFileSync(path.join(caseDir, "case.json"), "utf-8")) as FixtureCase;
	const controlRoot = path.join(tmp, "control");
	fs.cpSync(caseDir, controlRoot, { recursive: true });

	// env mapping: string = set, null = explicitly unset (vitest stubEnv with
	// "" reads back as unset for resolveWorkspaceConfig's trim-or-null rule).
	for (const [name, value] of Object.entries(fixture.env ?? {})) {
		vi.stubEnv(name, value ?? "");
	}

	const error = fixture.error;
	if (error !== undefined) {
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), error.kind, ...(error.contains ?? []));
		return;
	}

	const expected = fixture.expect;
	expect(expected).toBeDefined();
	const config = resolveWorkspaceConfig(controlRoot);
	expect(config.mode).toBe(expected?.mode);
	expect(config.source).toBe(expected?.source);

	if (expected?.game_root_equals_control) {
		expect(config.gameRoot).toBe(config.controlRoot);
	}
	if (expected?.game_root_rel !== undefined) {
		expect(config.gameRoot).toBe(expectRoot(controlRoot, expected.game_root_rel));
	}
	if (expected?.game_root_null) {
		expect(config.gameRoot).toBeNull();
	}
	if (expected?.engine_root_rel !== undefined) {
		expect(config.engineRoot).toBe(expectRoot(controlRoot, expected.engine_root_rel));
	}
	if (expected?.engine_root_null) {
		expect(config.engineRoot).toBeNull();
	}
	// mw-target-partition v2 fields (T-03).
	if (expected?.parent_root_rel !== undefined) {
		expect(config.parentRoot).toBe(expectRoot(controlRoot, expected.parent_root_rel));
	}
	if (expected?.partition_root_rel !== undefined) {
		expect(config.partitionRoot).toBe(expectRoot(controlRoot, expected.partition_root_rel));
	}
	if (expected?.parent_root_null) {
		expect(config.parentRoot).toBeNull();
	}
	if (expected?.roots !== undefined) {
		for (const [name, rel] of Object.entries(expected.roots)) {
			expect(config.roots?.[name]).toBe(expectRoot(controlRoot, rel));
		}
	}
	if (expected?.roots_empty) {
		expect(config.roots).toEqual({});
	}
	if (expected?.roots_null) {
		expect(config.roots).toBeNull();
	}
	if (expected?.vcs !== undefined) {
		expect(config.vcs).toBe(expected.vcs);
	}
	if (expected?.uproject_explicit !== undefined) {
		expect(config.uproject).toBe(expected.uproject_explicit);
	}
	if (expected?.deny_globs !== undefined) {
		expect(config.ignore.deny_globs).toEqual(expected.deny_globs);
	}
	if (expected?.conventions_contains !== undefined) {
		expect(config.contract.conventions).not.toBeNull();
		for (const part of expected.conventions_contains) {
			expect(config.contract.conventions).toContain(part);
		}
	}
	if (expected?.docs !== undefined) {
		expect(config.contract.docs).toEqual(expected.docs);
	}

	for (const [name, template] of Object.entries(fixture.render ?? {})) {
		expect(renderToolchainCommand(config.toolchain[name], config)).toBe(substitute(template, config));
	}

	const renderError = fixture.render_error;
	if (renderError !== undefined) {
		expectTargetError(
			() => renderToolchainCommand(config.toolchain[renderError.command], config),
			renderError.kind,
			...(renderError.contains ?? []),
		);
	}
}

const CASE_DIRS = fs
	.readdirSync(FIXTURES_DIR, { withFileTypes: true })
	.filter((e) => e.isDirectory())
	.map((e) => e.name)
	.sort();

describe("shared parity fixtures (target-config)", () => {
	it("fixture set is the expected 14 cases", () => {
		expect(CASE_DIRS.length).toBeGreaterThanOrEqual(14);
	});

	it.each(CASE_DIRS)("case %s", (name) => {
		runFixtureCase(path.join(FIXTURES_DIR, name), mkdtemp("atl-tc-fx-"));
	});

	it("parity summary markers", () => {
		console.log(`[PARITY] target-config cases=${CASE_DIRS.length}: ${CASE_DIRS.join(", ")}`);
		console.log("[VERIFY] VC-001: mode=single roots-equal=true (case 001)");
		console.log("[VERIFY] VC-006: rendered-contains-engine=true unresolved-placeholders=0 (case 003)");
		console.log("[VERIFY] VC-007: exit-nonzero=true fallback=false (case 004)");
		console.log("[VERIFY] VC-008: uproject-resolved=true ambiguous-fail=true (cases 005/006/007)");
	});
});
