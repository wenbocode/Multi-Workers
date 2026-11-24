/**
 * dual `additional_write_roots` (mw-dual-additional-write-roots T-001;
 * spec AC-001/AC-002/AC-003, design D-001..D-005, VC-001..VC-010 /
 * VC-013..VC-017).
 *
 * Scope: the TS half of the slice — config shape + anti-overlap validation
 * (shared/target-config.ts), the host write-face roots (shared/
 * workspace-write-face.ts), the conditional PM profile section
 * (pm/task-dispatcher.ts) and the worker runtime that re-parses the same
 * target.yml. The refusal codes are the FROZEN existing ones
 * (`write-face-outside-base` / `write-face-escape` / `write-face-read-only`);
 * nothing here relaxes the parser, the Engine read-only set or the deny
 * order.
 *
 * Fixtures live in the real system temp dir (`os.tmpdir()`); the junction
 * case uses a real Windows junction (`fs.symlinkSync(..., "junction")`) and
 * is skipped elsewhere. Junctions are removed with rmdir (never a recursive
 * delete of the target) before the temp trees are removed.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import {
	ENV_TARGET_ENGINE,
	ENV_TARGET_GAME,
	resolveWorkspaceConfig,
	TargetConfigError,
	targetYmlPath,
} from "../../src/extensions/agent-team-loop/shared/target-config.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { workspaceWriteFaceOptions } from "../../src/extensions/agent-team-loop/shared/workspace-write-face.ts";
import {
	parseWriteFace,
	WRITE_FACE_ESCAPE,
	WRITE_FACE_OUTSIDE_BASE,
	WRITE_FACE_READ_ONLY,
} from "../../src/extensions/agent-team-loop/shared/write-face.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const WIN32 = process.platform === "win32";
const KEY = "add-roots";
const PROFILE_MARK = "<!-- mw-profile: v1 -->";

const temporary: string[] = [];
const junctions: string[] = [];
const cwd = process.cwd();
const exitListeners = new Set(process.listeners("exit"));

afterEach(() => {
	process.chdir(cwd);
	vi.unstubAllEnvs();
	// Remove junction links first: rmdir drops the link, never the target.
	for (const link of junctions.splice(0)) {
		try {
			fs.rmdirSync(link);
		} catch {
			// already gone
		}
	}
	for (const dir of temporary.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	for (const listener of process.listeners("exit")) {
		if (!exitListeners.has(listener)) process.removeListener("exit", listener);
	}
});

interface Project {
	/** Canonical temp root (realpath) that contains every fixture dir. */
	top: string;
	control: string;
	game: string;
	engine: string;
	extra: string;
	extra2: string;
	agenticdoc: string;
}

/** Control + game + engine + two extra dirs under one canonical temp root. */
function project(): Project {
	for (const name of [ENV_TARGET_GAME, ENV_TARGET_ENGINE, "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"]) {
		vi.stubEnv(name, "");
	}
	const top = fs.realpathSync.native(fs.mkdtempSync(path.join(os.tmpdir(), "mw-add-roots-")));
	temporary.push(top);
	const control = path.join(top, "control");
	for (const name of ["game", "engine", "extra", "extra2"]) fs.mkdirSync(path.join(top, name));
	fs.mkdirSync(path.join(control, ".agenticdoc"), { recursive: true });
	return {
		top,
		control,
		game: path.join(top, "game"),
		engine: path.join(top, "engine"),
		extra: path.join(top, "extra"),
		extra2: path.join(top, "extra2"),
		agenticdoc: path.join(control, ".agenticdoc"),
	};
}

/** YAML path scalar: absolute fixture path with forward slashes. */
function yamlPath(value: string): string {
	return `'${value.replaceAll("\\", "/")}'`;
}

function writeYml(p: Project, body: string): void {
	fs.writeFileSync(targetYmlPath(p.control), body, "utf-8");
}

/** v1 flat dual file with an optional top-level declaration. */
function v1Dual(p: Project, extra: string[] | null, engine: string | null = p.engine): string {
	const lines = ["mode: dual", `game: ${yamlPath(p.game)}`];
	if (engine !== null) lines.push(`engine: ${yamlPath(engine)}`);
	if (extra !== null) {
		// An explicit empty list is a no-op; a bare `additional_write_roots:`
		// header (no items) is YAML null and is covered by the rejection cases.
		if (extra.length === 0) lines.push("additional_write_roots: []");
		else lines.push("additional_write_roots:", ...extra.map((root) => `  - ${yamlPath(root)}`));
	}
	return lines.join("\n");
}

interface V2DualShape {
	/** Declaration inside the `dual:` block (canonical v2 location). */
	block?: string[] | null;
	/** Top-level declaration (v2 read-side compatibility). */
	top?: string[] | null;
}

/** v2 file with `active: dual` and an optional declaration in either place. */
function v2Dual(p: Project, shape: V2DualShape): string {
	const lines = ["active: dual"];
	if (shape.top !== undefined && shape.top !== null) {
		if (shape.top.length === 0) lines.push("additional_write_roots: []");
		else lines.push("additional_write_roots:", ...shape.top.map((root) => `  - ${yamlPath(root)}`));
	}
	lines.push("dual:", `  game: ${yamlPath(p.game)}`, `  engine: ${yamlPath(p.engine)}`);
	if (shape.block !== undefined && shape.block !== null) {
		if (shape.block.length === 0) lines.push("  additional_write_roots: []");
		else lines.push("  additional_write_roots:", ...shape.block.map((root) => `    - ${yamlPath(root)}`));
	}
	return lines.join("\n");
}

/** A real Windows junction (skipped tests on other platforms). */
function junction(target: string, link: string): void {
	fs.symlinkSync(target, link, "junction");
	junctions.push(link);
}

function expectConfigError(fn: () => unknown, ...messageIncludes: string[]): TargetConfigError {
	let error: unknown;
	try {
		fn();
	} catch (e) {
		error = e;
	}
	expect(error).toBeInstanceOf(TargetConfigError);
	const tce = error as TargetConfigError;
	expect(tce.kind).toBe("invalid-config");
	for (const part of messageIncludes) expect(tce.message).toContain(part);
	return tce;
}

function hasAdditionalRoots(config: ReturnType<typeof resolveWorkspaceConfig>): boolean {
	return Object.hasOwn(config, "additionalWriteRoots");
}

// ── config shape + anti-overlap validation (AC-001 / VC-001..VC-006) ─────────

describe("config shape", () => {
	it("v1 flat dual accepts a top-level declaration and returns normalized roots", () => {
		const p = project();
		writeYml(p, v1Dual(p, [p.extra, p.extra2]));
		const config = resolveWorkspaceConfig(p.control);
		expect(config.mode).toBe("dual");
		expect(config.additionalWriteRoots).toEqual([p.extra, p.extra2]);
		console.log("[VERIFY] VC-001: v1-flat-dual additional-roots=2 normalized=true");
	});

	it("v2 active dual accepts the canonical dual-block declaration", () => {
		const p = project();
		writeYml(p, v2Dual(p, { block: [p.extra] }));
		const config = resolveWorkspaceConfig(p.control);
		expect(config.mode).toBe("dual");
		expect(config.additionalWriteRoots).toEqual([p.extra]);
		console.log("[VERIFY] VC-002: v2-dual-block additional-roots=1");
	});

	it("v2 active dual accepts the top-level read-side compatibility declaration", () => {
		const p = project();
		writeYml(p, v2Dual(p, { top: [p.extra] }));
		expect(resolveWorkspaceConfig(p.control).additionalWriteRoots).toEqual([p.extra]);
		console.log("[VERIFY] VC-003: v2-dual-top-level additional-roots=1");
	});

	it("undeclared, empty list and parked dual blocks add no field", () => {
		const p = project();
		writeYml(p, v1Dual(p, null));
		expect(hasAdditionalRoots(resolveWorkspaceConfig(p.control))).toBe(false);

		writeYml(p, v1Dual(p, []));
		expect(hasAdditionalRoots(resolveWorkspaceConfig(p.control))).toBe(false);

		writeYml(p, v2Dual(p, {}));
		expect(hasAdditionalRoots(resolveWorkspaceConfig(p.control))).toBe(false);

		writeYml(p, v2Dual(p, { block: [] }));
		expect(hasAdditionalRoots(resolveWorkspaceConfig(p.control))).toBe(false);

		// Row 5: an active-single file parks the dual block, declaration included.
		writeYml(
			p,
			[
				"active: single",
				"dual:",
				`  game: ${yamlPath(p.game)}`,
				"  additional_write_roots:",
				`    - ${yamlPath(p.extra)}`,
			].join("\n"),
		);
		const parked = resolveWorkspaceConfig(p.control);
		expect(parked.mode).toBe("single");
		expect(hasAdditionalRoots(parked)).toBe(false);
		console.log("[VERIFY] VC-006: undeclared/[]/parked => no additionalWriteRoots field");
	});

	it("v2 declares the field twice (top level + dual block) => invalid-config", () => {
		const p = project();
		writeYml(p, v2Dual(p, { top: [p.extra], block: [p.extra2] }));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "twice");
		console.log("[VERIFY] VC-003: duplicate declaration rejected");
	});

	it("v2 active single/partition with a top-level declaration => invalid-config", () => {
		const p = project();
		writeYml(p, ["active: single", "additional_write_roots:", `  - ${yamlPath(p.extra)}`].join("\n"));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "single");

		writeYml(
			p,
			[
				"active: partition",
				"additional_write_roots:",
				`  - ${yamlPath(p.extra)}`,
				"partition:",
				`  parent: ${yamlPath(p.extra2)}`,
				`  partition: ${yamlPath(p.game)}`,
			].join("\n"),
		);
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "partition");
		console.log("[VERIFY] VC-004: unscoped top-level declaration rejected for single/partition");
	});

	it("v1 single or no game with a top-level declaration => invalid-config", () => {
		const p = project();
		writeYml(p, ["mode: single", "additional_write_roots:", `  - ${yamlPath(p.extra)}`].join("\n"));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "dual mode");

		writeYml(p, ["additional_write_roots:", `  - ${yamlPath(p.extra)}`].join("\n"));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "dual mode");
		console.log("[VERIFY] VC-004: v1 single/no-game declaration rejected");
	});

	it("rejects relative, null, empty, non-list and non-string declarations", () => {
		const p = project();
		writeYml(p, v1Dual(p, ["relative/extra"]));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "absolute");

		writeYml(p, v1Dual(p, null).concat("\nadditional_write_roots: null"));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "null");

		// A bare header with no items is YAML null (a declared empty value).
		writeYml(p, v1Dual(p, null).concat("\nadditional_write_roots:"));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "null");

		writeYml(p, v1Dual(p, null).concat('\nadditional_write_roots:\n  - ""'));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "non-empty string");

		writeYml(p, v1Dual(p, null).concat("\nadditional_write_roots: 'D:/one-only'"));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "must be a list");

		writeYml(p, v1Dual(p, null).concat("\nadditional_write_roots:\n  name: value"));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "must be a list");

		writeYml(p, v1Dual(p, null).concat("\nadditional_write_roots:\n  - 42"));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "non-empty string");
		console.log("[VERIFY] VC-005: relative/null/empty/non-list/non-string rejected");
	});

	it("rejects duplicate and mutually nested additional roots", () => {
		const p = project();
		writeYml(p, v1Dual(p, [p.extra, p.extra]));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "duplicates");

		const nested = path.join(p.extra, "nested");
		fs.mkdirSync(nested);
		writeYml(p, v1Dual(p, [p.extra, nested]));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "nested");
		console.log("[VERIFY] VC-005: duplicate/nested additional roots rejected");
	});

	it("rejects roots equal to or nested with control/game/engine", () => {
		const p = project();
		const controlNested = path.join(p.control, "inside");
		const gameNested = path.join(p.game, "Content");
		fs.mkdirSync(controlNested);
		fs.mkdirSync(gameNested);
		const cases: Array<{ root: string; label: string }> = [
			{ root: p.control, label: "control root" },
			{ root: controlNested, label: "control root" },
			{ root: p.game, label: "game root" },
			{ root: gameNested, label: "game root" },
			{ root: p.engine, label: "engine root" },
		];
		for (const { root, label } of cases) {
			writeYml(p, v1Dual(p, [root]));
			expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", label);
		}
		console.log("[VERIFY] VC-005: control/game/engine overlap rejected");
	});

	it("validates against the FINAL (env-overridden) game root", () => {
		const p = project();
		const envGame = path.join(p.top, "env-game");
		fs.mkdirSync(envGame);
		writeYml(p, v1Dual(p, [envGame]));
		// Without the env override the declaration is legal (file game is elsewhere).
		expect(resolveWorkspaceConfig(p.control).additionalWriteRoots).toEqual([envGame]);
		vi.stubEnv(ENV_TARGET_GAME, envGame);
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "game root");
		console.log("[VERIFY] VC-006: env-overridden final game root participates");
	});

	it("normalizes dot segments, trailing separators and case to one identity", () => {
		const p = project();
		const dotted = path.join(p.extra, "..", "extra");
		writeYml(p, v1Dual(p, [dotted]));
		expect(resolveWorkspaceConfig(p.control).additionalWriteRoots).toEqual([p.extra]);

		writeYml(p, v1Dual(p, [`${p.extra}${path.sep}`]));
		expect(resolveWorkspaceConfig(p.control).additionalWriteRoots).toEqual([p.extra]);

		if (WIN32) {
			writeYml(p, v1Dual(p, [p.extra.toUpperCase()]));
			expect(resolveWorkspaceConfig(p.control).additionalWriteRoots).toEqual([p.extra]);
		}
		console.log("[VERIFY] VC-017: realpath+normcase identity across spellings");
	});

	it.skipIf(!WIN32)("rejects an additional root that is a junction to Engine or Game", () => {
		const p = project();
		const engineAlias = path.join(p.top, "engine-alias");
		junction(p.engine, engineAlias);
		writeYml(p, v1Dual(p, [engineAlias]));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "engine root");

		const gameAlias = path.join(p.top, "game-alias");
		junction(p.game, gameAlias);
		writeYml(p, v1Dual(p, [gameAlias]));
		expectConfigError(() => resolveWorkspaceConfig(p.control), "additional_write_roots", "game root");
		console.log("[VERIFY] VC-005: junction alias to Engine/Game rejected at config time");
	});
});

// ── host write-face options + parser refusals (AC-002 / VC-007/VC-009) ───────

describe("dispatch", () => {
	it("workspaceWriteFaceOptions appends declared roots; single/partition unchanged", () => {
		const p = project();
		writeYml(p, v1Dual(p, [p.extra]));
		const withExtra = workspaceWriteFaceOptions(p.control, resolveWorkspaceConfig(p.control));
		expect(withExtra.roots).toEqual([p.control, p.game, p.engine, p.extra]);
		expect(withExtra.roots?.at(-1)).toBe(p.extra);

		writeYml(p, v1Dual(p, null));
		const without = workspaceWriteFaceOptions(p.control, resolveWorkspaceConfig(p.control));
		expect(without.roots).toEqual([p.control, p.game, p.engine]);

		writeYml(p, "mode: single");
		const single = workspaceWriteFaceOptions(p.control, resolveWorkspaceConfig(p.control));
		expect(Object.hasOwn(single, "roots")).toBe(false);

		writeYml(
			p,
			[
				"active: partition",
				"partition:",
				`  parent: ${yamlPath(p.extra2)}`,
				`  partition: ${yamlPath(p.game)}`,
				"  roots:",
				`    sdk: ${yamlPath(p.engine)}`,
			].join("\n"),
		);
		const partition = workspaceWriteFaceOptions(p.control, resolveWorkspaceConfig(p.control));
		expect(partition.roots).toEqual([p.control, p.game, p.extra2, p.engine]);
		console.log("[VERIFY] VC-007: dual roots carry the declared extra; single has no roots property");
	});

	it("parseWriteFace accepts declared extra roots and keeps the frozen refusals", () => {
		const p = project();
		writeYml(p, v1Dual(p, [p.extra]));
		const options = workspaceWriteFaceOptions(p.control, resolveWorkspaceConfig(p.control));
		const head = (value: string): string => `write_face:\n  - ${value.replaceAll("\\", "/")}\n`;

		const declaredPath = path.join(p.extra, "Saved", "notes.txt");
		const declared = parseWriteFace(head(declaredPath), options);
		expect(declared.kind).toBe("declared");
		if (declared.kind === "declared") {
			expect(declared.face.entries).toEqual([declaredPath.replaceAll("\\", "/")]);
		}

		expect(parseWriteFace(head(path.join(p.top, "outside.txt")), options)).toMatchObject({
			kind: "rejected",
			code: WRITE_FACE_OUTSIDE_BASE,
		});
		expect(parseWriteFace(head(`${p.extra}/../escape.txt`), options)).toMatchObject({
			kind: "rejected",
			code: WRITE_FACE_ESCAPE,
		});

		const engineLink = path.join(p.extra, "engine-link");
		junction(p.engine, engineLink);
		expect(parseWriteFace(head(path.join(engineLink, "Source", "A.cpp")), options)).toMatchObject({
			kind: "rejected",
			code: WRITE_FACE_READ_ONLY,
		});
		console.log("[VERIFY] VC-009: declared accepted; outside/escape/read-only codes preserved");
	});

	it("a declaration that is removed again stops admitting the external path", () => {
		const p = project();
		writeYml(p, v1Dual(p, [p.extra]));
		const entry = path.join(p.extra, "Saved", "notes.txt").replaceAll("\\", "/");
		expect(parseWriteFace(`write_face:\n  - ${entry}\n`, workspaceWriteFaceOptions(p.control)).kind).toBe("declared");

		writeYml(p, v1Dual(p, null));
		expect(parseWriteFace(`write_face:\n  - ${entry}\n`, workspaceWriteFaceOptions(p.control))).toMatchObject({
			kind: "rejected",
			code: WRITE_FACE_OUTSIDE_BASE,
		});
		console.log("[VERIFY] VC-009: declaration removal withdraws the root");
	});
});

// ── PM profile conditional section (AC-002 / VC-010) ────────────────────────

function scratchTask(p: Project, name: string, entries: string[] | undefined): string {
	const dir = path.join(p.agenticdoc, KEY, "workers", name);
	fs.mkdirSync(dir, { recursive: true });
	const file = path.join(dir, "task.md");
	fs.writeFileSync(
		file,
		[
			"---",
			"type: coding",
			"card_path: tasks/test.md",
			...(entries === undefined ? [] : ["write_face:", ...entries.map((entry) => `  - ${entry}`)]),
			"---",
			"Do the task.",
		].join("\n"),
		"utf-8",
	);
	return file;
}

async function dispatch(name: string, taskPath: string, p: Project): Promise<unknown> {
	return dispatchTask(
		{ taskKey: name, status: "pending", cli: "pi", provider: "timi", model: "", taskPath },
		new WorkerStore(p.agenticdoc),
	);
}

function profileBlock(text: string): string {
	const index = text.indexOf(PROFILE_MARK);
	expect(index).toBeGreaterThanOrEqual(0);
	return text.slice(index);
}

describe("profile", () => {
	it("adds the conditional section byte-for-byte and replaces a stale block", async () => {
		const p = project();
		writeYml(p, v1Dual(p, null));
		const taskPath = scratchTask(p, "profile", [path.join(p.control, "notes.md")]);
		expect(await dispatch("profile", taskPath, p)).toEqual({ ok: true });
		const blockBefore = profileBlock(fs.readFileSync(taskPath, "utf8"));
		expect(blockBefore).not.toContain("Additional write roots:");

		writeYml(p, v1Dual(p, [p.extra]));
		expect(await dispatch("profile", taskPath, p)).toEqual({ ok: true });
		const blockAfter = profileBlock(fs.readFileSync(taskPath, "utf8"));
		const expected = blockBefore.replace(
			`Engine root: ${p.engine}\n`,
			`Engine root: ${p.engine}\nAdditional write roots:\n- ${p.extra}\n`,
		);
		expect(blockAfter).toBe(expected);

		// Same-config re-dispatch is byte-stable (freshness predicate).
		expect(await dispatch("profile", taskPath, p)).toEqual({ ok: true });
		expect(profileBlock(fs.readFileSync(taskPath, "utf8"))).toBe(blockAfter);
		console.log("[VERIFY] VC-010: conditional profile section + stale replacement");
	});
});

// ── worker runtime re-parse of target.yml (AC-003 / VC-013..VC-016) ─────────

async function startWorker(taskPath: string, target: string) {
	const handlers = new Map<string, Array<(event: unknown) => unknown>>();
	const pi = {
		on(name: string, handler: (event: unknown) => unknown) {
			const list = handlers.get(name) ?? [];
			list.push(handler);
			handlers.set(name, list);
		},
		sendUserMessage() {},
		setActiveTools() {},
		registerTool() {},
	};
	vi.stubEnv("PI_WORKER_TASK", taskPath);
	process.chdir(target);
	await workerModeActivate(pi as unknown as ExtensionAPI);
	return {
		call(toolName: string, input: Record<string, unknown>) {
			for (const handler of handlers.get("tool_call") ?? []) {
				const result = handler({ type: "tool_call", toolCallId: "probe", toolName, input }) as
					| { block?: boolean; reason?: string }
					| undefined;
				if (result?.block) return result;
			}
			return undefined;
		},
		settle() {
			for (const handler of handlers.get("agent_end") ?? []) handler({ messages: [] });
			for (const handler of handlers.get("agent_settled") ?? []) handler({});
		},
	};
}

describe("worker runtime", () => {
	it("re-parses target.yml: declared roots are writable, outside/escape are blocked", async () => {
		const p = project();
		writeYml(p, v1Dual(p, [p.extra]));
		fs.mkdirSync(path.join(p.extra, "Saved"));
		const allowed = path.join(p.extra, "Saved", "notes.txt");
		const taskPath = scratchTask(p, "allow", [allowed]);
		const guard = await startWorker(taskPath, p.game);
		try {
			expect(guard.call("write", { path: allowed, content: "x" })).toBeUndefined();
			expect(guard.call("edit", { path: allowed, edits: [] })).toBeUndefined();
			expect(guard.call("bash", { command: `echo x > "${allowed}"` })).toBeUndefined();
			for (const blocked of [path.join(p.top, "outside.txt"), `${p.extra}/../escape.txt`]) {
				expect(guard.call("write", { path: blocked, content: "x" })?.block, blocked).toBe(true);
				expect(guard.call("bash", { command: `echo x > "${blocked}"` })?.block, blocked).toBe(true);
			}
		} finally {
			guard.settle();
		}
		console.log("[VERIFY] VC-013/VC-014/VC-015: worker inherits declared roots; outside/escape blocked");
	});

	it.skipIf(!WIN32)("keeps Engine read-only through a junction inside a declared root", async () => {
		const p = project();
		writeYml(p, v1Dual(p, [p.extra]));
		const saved = path.join(p.extra, "Saved");
		fs.mkdirSync(saved);
		const engineLink = path.join(p.extra, "engine-link");
		junction(p.engine, engineLink);
		// The whole declared root is in the face, so a block on a junction path
		// can only come from the resolved Engine identity, not from face narrowing.
		const taskPath = scratchTask(p, "engine-junction", [`${p.extra}/**`]);
		const guard = await startWorker(taskPath, p.game);
		try {
			expect(guard.call("write", { path: path.join(saved, "x.txt"), content: "x" })).toBeUndefined();
			for (const blocked of [
				path.join(engineLink, "Source", "A.cpp"),
				path.join(engineLink, "Binaries", "Win64", "B.dll"),
			]) {
				const result = guard.call("write", { path: blocked, content: "x" });
				expect(result?.block, blocked).toBe(true);
				expect(result?.reason?.toLowerCase(), blocked).toContain("engine");
			}
		} finally {
			guard.settle();
		}
		console.log("[VERIFY] VC-016: Engine read-only holds for a junction inside a declared root");
	});
});
