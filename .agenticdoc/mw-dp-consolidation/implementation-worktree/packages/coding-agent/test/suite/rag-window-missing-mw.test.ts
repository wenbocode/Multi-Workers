/**
 * `findMwPy() === null` branch of the `/mw rag` wrapper (quality gate
 * 2026-09-23, Q-AC-303).
 *
 * Inside this repo `findMwPy()` always succeeds (the repo-relative fallback
 * finds `packages/multi-workers/mw.py`), so the "mw.py is missing" branch had
 * no test at all. Mocking `node:fs` to report every path as absent forces that
 * branch: the wrapper must surface the `MW_PY` hint as its output and must not
 * spawn anything, instead of throwing or printing an empty notice.
 */

import { describe, expect, it, vi } from "vitest";

vi.mock("node:fs", async (importOriginal) => {
	const actual = await importOriginal<typeof import("node:fs")>();
	return { ...actual, existsSync: () => false };
});

import { ragMw } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

describe("/mw rag without a resolvable mw.py (Q-AC-303)", () => {
	it("returns the MW_PY hint with ok=false instead of spawning", () => {
		const result = ragMw("/tmp/mw-rag-missing-mw", ["list"]);
		expect(result.ok).toBe(false);
		expect(result.code).toBe(-1);
		expect(result.output).toContain("MW_PY");
		expect(result.output).toContain("mw.py");
		verify(
			`[VERIFY] Q-AC-303: ok=${String(result.ok)} code=${result.code} hint_has_MW_PY=${result.output.includes(
				"MW_PY",
			)} output="${result.output}"`,
		);
	});
});
