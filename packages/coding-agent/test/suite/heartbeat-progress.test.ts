/**
 * heartbeat-progress.test.ts — re-dispatch trace.log pairing (regression).
 *
 * A worker that hit a model error is re-dispatched by the launcher (same-model
 * retry, then the `fallback_models` chain) and the new process APPENDS to the
 * same trace.log. The previous attempt's `[END] exit=3` therefore sits above the
 * new `[START]`.
 *
 * Before the fix `readTaskProgress` kept the last `[END]` unconditionally, so the
 * watch widget paired the new start with the older end:
 *   elapsed = max(0, end - start) = max(0, -4s) = 0   → "up 0s" never grew
 * and `exitCode` stayed 3, which reads a running task as model-exhausted.
 *
 * Verified against the live trace of `workers/ds-qg-review` (2 retries + 1
 * fallback): END 09:23:12 exit=3, START 09:23:16, real runtime > 12 min.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { readTaskProgress } from "../../src/extensions/agent-team-loop/shared/heartbeat.ts";

const dirs: string[] = [];

function taskDirWith(trace: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-hb-"));
	dirs.push(dir);
	fs.writeFileSync(path.join(dir, "trace.log"), trace, "utf8");
	return dir;
}

afterEach(() => {
	for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** A start line `ageMs` in the past, so elapsed is deterministic and positive. */
function startLine(ageMs: number): string {
	return `[START] ${new Date(Date.now() - ageMs).toISOString()} task=t type=coding phases=-`;
}

describe("readTaskProgress across re-dispatched attempts", () => {
	it("does not pair the new [START] with the previous attempt's [END]", () => {
		const dir = taskDirWith(
			[
				"[START] 2026-10-20T09:15:48.218Z task=t type=coding phases=-",
				"[MODEL] 2026-10-20T09:15:48.255Z model=primary",
				"[END] 2026-10-20T09:18:29.211Z exit=3 elapsed=161s tools=35 phases=-",
				startLine(60_000),
				"[MODEL] 2026-10-20T09:23:16.639Z model=fallback",
				"[HEARTBEAT] 2026-10-20T09:23:46.656Z task=t phase=-",
			].join("\n"),
		);

		const prog = readTaskProgress(dir);
		expect(prog).toBeDefined();
		// The terminal fields belong to the finished attempt, not to this one.
		expect(prog?.endTs).toBeUndefined();
		expect(prog?.exitCode).toBeUndefined();
		expect(prog?.endPhases).toBeUndefined();
		// Runtime is measured from the live attempt (≈60s), never clamped to 0.
		expect(prog?.elapsedMs).toBeGreaterThanOrEqual(59_000);
		// The newest [MODEL] line wins, so the widget names the model actually running.
		expect(prog?.model).toBe("fallback");
	});

	it("keeps the terminal fields for a single-attempt trace", () => {
		const dir = taskDirWith(
			[
				"[START] 2026-10-20T09:15:48.218Z task=t type=coding phases=2/2",
				"[END] 2026-10-20T09:18:29.211Z exit=0 elapsed=161s tools=35 phases=2/2",
			].join("\n"),
		);

		const prog = readTaskProgress(dir);
		expect(prog?.endTs).toBe("2026-10-20T09:18:29.211Z");
		expect(prog?.exitCode).toBe(0);
		expect(prog?.endPhases).toBe("2/2");
		// Derived from the two timestamps (the line's rounded `elapsed=161s` is not used).
		expect(Math.round((prog?.elapsedMs ?? 0) / 1000)).toBe(161);
	});
});
