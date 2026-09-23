/**
 * Tests for the worker progress machine-checkpoint writer (mw-worker-progress-persist
 * T-1, AC-001/AC-002, design D-105/D-107).
 *
 * The suite config is `silent: "passed-only"` and swallows console.log from
 * green tests, so `[VERIFY]` lines go straight to stdout via process.stdout.write.
 * Covers:
 * - formatMachineCheckpoint: exactly one line, no trailing newline, D-105 field
 *   order, every phases/risk variant,
 * - appendProgressLine: directory auto-creation, append-only preservation of a
 *   pre-existing sentinel line (PM note / worker self-assessment),
 * - the base outputDir() taskKey traversal guard still rejects escaping keys.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	appendProgressLine,
	formatMachineCheckpoint,
	type MachineCheckpointOpts,
} from "../../src/extensions/agent-team-loop/worker/output-writer.ts";

/* The suite swallows console.log from green tests; write the evidence line
 * straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

/** design D-105 machine line contract (progress.md side). */
const MACHINE_LINE_RE =
	/^CKPT \d+m \[machine\] ts=\S+ reads=\d+ writes=\d+ phases=(\d+\/\d+|-) repeat_top=\d+ risk=(low|mid|high)$/;

const tmpRoots: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "atl-progress-"));
	tmpRoots.push(dir);
	return dir;
}

function progressPath(root: string, taskKey: string): string {
	return path.join(root, taskKey, "progress.md");
}

function machineLineCount(content: string): number {
	return content.split("\n").filter((line) => line.startsWith("CKPT ") && line.includes("[machine]")).length;
}

afterEach(() => {
	for (const dir of tmpRoots.splice(0)) {
		fs.rmSync(dir, { recursive: true, force: true });
	}
});

// ── formatMachineCheckpoint (D-105) ───────────────────────────────────────────

describe("formatMachineCheckpoint (D-105)", () => {
	it("emits exactly one line with no trailing newline and the fixed field order", () => {
		const opts: MachineCheckpointOpts = {
			elapsedMs: 7 * 60_000 + 20_000,
			reads: 12,
			writes: 0,
			phases: "2/5",
			repeatTop: 3,
			risk: "mid",
		};
		const line = formatMachineCheckpoint(opts);
		expect(line.includes("\n")).toBe(false);
		expect(line).toMatch(MACHINE_LINE_RE);
		expect(line.startsWith("CKPT 7m [machine] ")).toBe(true);
		expect(line.endsWith("reads=12 writes=0 phases=2/5 repeat_top=3 risk=mid")).toBe(true);
	});

	it("rounds elapsedMs to whole minutes and covers every phases/risk variant", () => {
		const variants: Array<Pick<MachineCheckpointOpts, "elapsedMs" | "phases" | "risk">> = [
			{ elapsedMs: 30_000, phases: "-", risk: "low" },
			{ elapsedMs: 89_000, phases: "1/3", risk: "mid" },
			{ elapsedMs: 5 * 60_000 + 40_000, phases: "4/4", risk: "high" },
		];
		const seenPhases = new Set<string>();
		const seenRisk = new Set<string>();
		for (const variant of variants) {
			const line = formatMachineCheckpoint({ ...variant, reads: 1, writes: 1, repeatTop: 0 });
			expect(line).toMatch(MACHINE_LINE_RE);
			const m = line.match(/phases=(\S+) repeat_top=\d+ risk=(\S+)$/);
			expect(m).not.toBeNull();
			seenPhases.add(m?.[1] ?? "");
			seenRisk.add(m?.[2] ?? "");
		}
		expect([...seenPhases].sort()).toEqual(["-", "1/3", "4/4"]);
		expect([...seenRisk].sort()).toEqual(["high", "low", "mid"]);
		// 30s -> 1m (round, not floor); 89s -> 1m; 5m40s -> 6m.
		expect(formatMachineCheckpoint({ ...variants[0], reads: 0, writes: 0, repeatTop: 0 })).toContain("CKPT 1m ");
		expect(formatMachineCheckpoint({ ...variants[2], reads: 0, writes: 0, repeatTop: 0 })).toContain("CKPT 6m ");
	});
});

// ── appendProgressLine (D-107) ────────────────────────────────────────────────

describe("appendProgressLine (D-107)", () => {
	it("creates the directory and file with exactly the formatted line (VC-001)", () => {
		const root = mkdtemp();
		const taskKey = path.join("key-a", "workers", "t-review");
		const line = formatMachineCheckpoint({
			elapsedMs: 30 * 60_000,
			reads: 9,
			writes: 0,
			phases: "-",
			repeatTop: 2,
			risk: "low",
		});
		appendProgressLine(taskKey, root, line);
		const file = progressPath(root, taskKey);
		expect(fs.existsSync(file)).toBe(true);
		expect(fs.readFileSync(file, "utf8")).toBe(`${line}\n`);
		const lines = fs
			.readFileSync(file, "utf8")
			.split("\n")
			.filter((l) => l !== "");
		verify(`[VERIFY] VC-001: progress_exists=true machine_lines=${machineLineCount(fs.readFileSync(file, "utf8"))}`);
		expect(lines).toHaveLength(1);
	});

	it("is append-only: a pre-existing sentinel line stays first and unchanged (VC-002)", () => {
		const root = mkdtemp();
		const taskKey = path.join("key-b", "workers", "t-research");
		const file = progressPath(root, taskKey);
		fs.mkdirSync(path.dirname(file), { recursive: true });
		// Simulates a PM backfill or a worker self-assessment line already on disk.
		const sentinel = "CKPT 20m converging=yes eta≈10m 只差最后一段证据";
		fs.writeFileSync(file, `${sentinel}\n`, "utf8");

		const first = formatMachineCheckpoint({
			elapsedMs: 30 * 60_000,
			reads: 4,
			writes: 0,
			phases: "1/2",
			repeatTop: 1,
			risk: "mid",
		});
		const second = formatMachineCheckpoint({
			elapsedMs: 40 * 60_000,
			reads: 7,
			writes: 0,
			phases: "2/2",
			repeatTop: 0,
			risk: "low",
		});
		appendProgressLine(taskKey, root, first);
		appendProgressLine(taskKey, root, second);

		const content = fs.readFileSync(file, "utf8");
		const lines = content.split("\n").filter((l) => l !== "");
		expect(lines).toEqual([sentinel, first, second]);
		expect(lines[0]).toBe(sentinel);
		const machineCount = machineLineCount(content);
		verify(`[VERIFY] VC-002: machine_lines=${machineCount} sentinel_first=${lines[0] === sentinel}`);
		expect(machineCount).toBe(2);
		// No truncation/overwrite: the sentinel byte length plus the two appended
		// machine lines plus the three newlines account for the whole file.
		expect(content.length).toBe(sentinel.length + first.length + second.length + 3);
	});

	it("rejects a taskKey that escapes the agenticdoc root", () => {
		const root = mkdtemp();
		expect(() => appendProgressLine(path.join("..", "evil"), root, "CKPT 1m [machine] x")).toThrow(/path traversal/);
		expect(fs.existsSync(path.join(root, "..", "evil", "progress.md"))).toBe(false);
	});
});
