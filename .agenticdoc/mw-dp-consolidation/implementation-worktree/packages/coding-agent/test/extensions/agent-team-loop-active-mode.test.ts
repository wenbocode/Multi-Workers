/**
 * mw-target-partition rule-table tests (T-02, spec §1.5, AC-017, VC-017).
 *
 * Two layers, mirroring packages/multi-workers/test_active_mode.py:
 * 1. The shared parameterized table
 *    packages/multi-workers/test/fixtures/active-mode-table.json — the full
 *    enumeration of file shape × active value × EP/ET state for
 *    decideActiveMode, rows 2-12. The JSON is the parity contract; the Py
 *    runner executes the SAME table.
 * 2. Entry-level unit tests for the two rows the pure inputs cannot
 *    express: row 1 (mixed format) and row 4 (missing mode block), driven
 *    through resolveWorkspaceConfig. Rows 5-12 are additionally covered
 *    end-to-end by the target-config-cases fixtures.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	type ActiveModeResult,
	decideActiveMode,
	ENV_PARTITION_PARENT,
	ENV_PARTITION_ROOT,
	resolveWorkspaceConfig,
	TargetConfigError,
	targetYmlPath,
} from "../../src/extensions/agent-team-loop/shared/target-config.ts";

const TABLE_PATH = fileURLToPath(
	new URL("../../../multi-workers/test/fixtures/active-mode-table.json", import.meta.url),
);

interface TableCase {
	id: string;
	row: number;
	file_shape: "none" | "v1" | "v2";
	active: string | null;
	env: Record<string, string | null>;
	expect:
		| { mode: ActiveModeResult["mode"]; block: ActiveModeResult["block"] }
		| { error: { kind: string; contains: string[] } };
}

const CASES = (JSON.parse(fs.readFileSync(TABLE_PATH, "utf-8")) as { cases: TableCase[] }).cases;

function mkdtemp(prefix: string): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function expectTargetError(fn: () => unknown, kind: string, ...contains: string[]): TargetConfigError {
	let err: unknown;
	try {
		fn();
	} catch (e) {
		err = e;
	}
	expect(err).toBeInstanceOf(TargetConfigError);
	const tce = err as TargetConfigError;
	expect(tce.kind).toBe(kind);
	for (const part of contains) expect(tce.message).toContain(part);
	return tce;
}

function writeTargetYml(controlRoot: string, content: string): void {
	fs.mkdirSync(path.join(controlRoot, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(targetYmlPath(controlRoot), content, "utf-8");
}

/** Expected normalized root: realpath when the path exists; a missing
 * tail canonicalizes the longest existing prefix — mirrors normalizeRoot()
 * (and Python's Path.resolve(strict=False)) so non-existing roots compare
 * exactly. */
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

afterEach(() => {
	vi.unstubAllEnvs();
});

describe("shared active-mode table (spec §1.5 rows 2-12)", () => {
	it("table shape lock: 112 cases, rows 2-12 all present", () => {
		expect(CASES.length).toBe(112);
		const rows = [...new Set(CASES.map((c) => c.row))].sort((a, b) => a - b);
		expect(rows).toEqual([2, 3, 5, 6, 7, 8, 9, 10, 11, 12]);
	});

	it.each(CASES)("$id", (case_) => {
		const env = case_.env;
		const run = () =>
			decideActiveMode({
				fileShape: case_.file_shape,
				active: case_.active,
				envPartitionParent: env.MW_PARTITION_PARENT ?? null,
				envPartitionRoot: env.MW_PARTITION_ROOT ?? null,
				envTargetGame: env.MW_TARGET_GAME ?? null,
				envTargetEngine: env.MW_TARGET_ENGINE ?? null,
			});
		const expected = case_.expect;
		if ("error" in expected) {
			expectTargetError(run, expected.error.kind, ...expected.error.contains);
		} else {
			expect(run()).toEqual({ mode: expected.mode, block: expected.block });
		}
	});

	it("parity summary markers", () => {
		const rows = [...new Set(CASES.map((c) => c.row))].sort((a, b) => a - b);
		console.log(`[PARITY] active-mode table cases=${CASES.length} rows=${rows}`);
		console.log("[VERIFY] VC-017: table=rows-2-12 (rows 1/4 via entry tests + fixtures), parity=ts-side");
	});
});

// ── rows not expressible as pure inputs (entry-level, AC-017) ─────────────────

describe("entry-level rows 1/4/5/9", () => {
	it("row 1: active key + v1 top-level field is a mixed-format error naming both shapes", () => {
		const controlRoot = mkdtemp("atl-am-mixed-");
		writeTargetYml(controlRoot, "active: partition\nmode: dual\ngame: ./game\n");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "mixed", "v2", "v1");
		fs.rmSync(controlRoot, { recursive: true, force: true });
	});

	it("row 4: active partition without a partition block names the missing block", () => {
		const controlRoot = mkdtemp("atl-am-noblock-");
		writeTargetYml(controlRoot, "active: partition\ndual:\n  game: ./game\n");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "partition", "missing");
		fs.rmSync(controlRoot, { recursive: true, force: true });
	});

	it("row 4: active dual without a dual block names the missing block", () => {
		const controlRoot = mkdtemp("atl-am-nodual-");
		writeTargetYml(controlRoot, "active: dual\n");
		expectTargetError(() => resolveWorkspaceConfig(controlRoot), "invalid-config", "dual", "missing");
		fs.rmSync(controlRoot, { recursive: true, force: true });
	});

	it("row 5: active single parks the mode blocks (invalid-if-parsed content must not raise)", () => {
		const controlRoot = mkdtemp("atl-am-parked-");
		writeTargetYml(
			controlRoot,
			[
				"active: single",
				"dual:",
				"  game: ./game",
				"  parent: ../oops",
				"partition:",
				"  parent: ../p",
				"  partition: ./q",
				"",
			].join("\n"),
		);
		const config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("single");
		expect(config.source).toBe("target-yml");
		expect(config.gameRoot).toBe(config.controlRoot);
		expect(config.roots).toBeNull();
		fs.rmSync(controlRoot, { recursive: true, force: true });
	});

	it("row 9: no file + both partition env vars → partition, source=env", () => {
		const controlRoot = mkdtemp("atl-am-envpart-");
		vi.stubEnv(ENV_PARTITION_PARENT, "../parentproj");
		vi.stubEnv(ENV_PARTITION_ROOT, "./frag");
		const config = resolveWorkspaceConfig(controlRoot);
		expect(config.mode).toBe("partition");
		expect(config.source).toBe("env");
		expect(config.parentRoot).toBe(expectRoot(controlRoot, "../parentproj"));
		expect(config.partitionRoot).toBe(expectRoot(controlRoot, "./frag"));
		expect(config.gameRoot).toBeNull();
		expect(config.roots).toEqual({});
		fs.rmSync(controlRoot, { recursive: true, force: true });
	});
});
