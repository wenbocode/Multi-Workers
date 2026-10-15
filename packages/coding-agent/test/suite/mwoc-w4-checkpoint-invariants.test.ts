/**
 * mwoc-w4-checkpoint-invariants.test.ts — T-04 / AC-009 (design §6):
 * the writeless convergence checkpoint now judges LANDING, not write-tool
 * calls.
 *
 * What this file locks:
 *   - `computeRisk` writeless branch (`landed !== undefined`): artifact on disk
 *     ⇒ low, zero landing past the anchor ⇒ high, landed-but-stale with read
 *     spin / stalled phases ⇒ mid, everything else ⇒ low (all three writeless
 *     tiers covered); `landed === undefined` keeps the legacy three branches
 *     byte for byte (write roles).
 *   - the landing signals come from `parseWriteFileEvents` (the change-ledger
 *     grammar the settle judgement reads), never from `[TOOL] worker_file`
 *     counts: a duplicated `[WRITE_FILE] progress.md` is ONE landed target.
 *   - `CHECKPOINT_LINE_RE` parses both the old suffix-free line and the new
 *     `land= last_land= artifact= done=` suffix (optional non-capturing group),
 *     and the suffix is emitted for writeless roles only.
 *   - AC-009 replay: the wjg-w12 shape (`[WRITE_FILE]`×4 + a 37,149 B product
 *     on disk) is `risk=low` / `land=2`; the zero-landing shape is `high`.
 *   - I3 invariants: the idle watchdog, the wall clock and the deadline steer
 *     do not read `risk` — a writeless (research) run still behaves exactly as
 *     a coding one in all three timing scenarios.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { appendWriteFileEvent } from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import { readTaskProgress } from "../../src/extensions/agent-team-loop/shared/heartbeat.ts";
import {
	collectLandingSignals,
	computeRisk,
	landFreshMs,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

// worker-mode registers a process-exit hook per activation; this file activates
// several workers in one process, tripping Node's listener-leak heuristic.
process.setMaxListeners(50);

const tmpRoots: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwoc-w4-ckpt-"));
	tmpRoots.push(dir);
	return dir;
}

afterEach(() => {
	vi.useRealTimers();
	for (const dir of tmpRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	delete process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_IDLE_MS;
});

// ── computeRisk: writeless landing branch + legacy write-role branch ─────────

describe("computeRisk writeless landing signals (T-04/AC-009)", () => {
	const anchor = 30 * 60_000;

	it("writeless low: a non-empty product on disk outranks read spin (wjg-w12 shape)", () => {
		expect(
			computeRisk({
				elapsedMs: 33 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 16,
				landed: 2,
				lastLandingAgeMs: 84_000,
				artifactPresent: true,
				progressDone: true,
			}),
		).toBe("low");
	});

	it("writeless high: zero landing past the anchor is pure exploration", () => {
		expect(
			computeRisk({
				elapsedMs: 31 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 0,
				landed: 0,
				progressDone: false,
				artifactPresent: false,
			}),
		).toBe("high");
	});

	it("writeless mid: landed-but-stale with no artifact, by read spin or stalled phases", () => {
		// Same target read ≥4 times — spinning.
		expect(
			computeRisk({
				elapsedMs: 31 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 4,
				landed: 1,
				lastLandingAgeMs: 25 * 60_000,
				artifactPresent: false,
				progressDone: false,
			}),
		).toBe("mid");
		// Phase framework present but nothing completed past the anchor.
		expect(
			computeRisk({
				elapsedMs: 31 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 4,
				phasesDone: 0,
				repeatTop: 1,
				landed: 1,
				lastLandingAgeMs: 25 * 60_000,
				artifactPresent: false,
				progressDone: false,
			}),
		).toBe("mid");
	});

	it("writeless low: stale landing without spin/stall, and zero landing before the anchor", () => {
		expect(
			computeRisk({
				elapsedMs: 31 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 3,
				phasesDone: 1,
				repeatTop: 1,
				landed: 1,
				lastLandingAgeMs: 25 * 60_000,
				artifactPresent: false,
				progressDone: false,
			}),
		).toBe("low");
		expect(
			computeRisk({
				elapsedMs: 20 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 1,
				landed: 0,
				artifactPresent: false,
				progressDone: false,
			}),
		).toBe("low");
	});

	it("writeless low: a fresh landing plus the role's own converging=yes note (W2b)", () => {
		expect(
			computeRisk({
				elapsedMs: 31 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 0,
				landed: 1,
				lastLandingAgeMs: 30_000,
				artifactPresent: false,
				progressDone: true,
			}),
		).toBe("low");
	});

	it("landed === undefined keeps the legacy three branches byte for byte (write roles)", () => {
		// cpr-007 pattern: 30m+ of reads, zero writes.
		expect(
			computeRisk({
				elapsedMs: 32 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 1,
			}),
		).toBe("high");
		// Phase framework present but nothing completed past the anchor.
		expect(
			computeRisk({
				elapsedMs: 31 * 60_000,
				anchorMs: anchor,
				writes: 3,
				phasesTotal: 4,
				phasesDone: 0,
				repeatTop: 1,
			}),
		).toBe("mid");
		// Same target read 4+ times — spinning.
		expect(
			computeRisk({
				elapsedMs: 5 * 60_000,
				anchorMs: anchor,
				writes: 2,
				phasesTotal: 3,
				phasesDone: 1,
				repeatTop: 4,
			}),
		).toBe("mid");
		// Writes advancing before the anchor — still warming up, not divergence.
		expect(
			computeRisk({
				elapsedMs: 20 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 0,
			}),
		).toBe("low");
		// Implementation underway.
		expect(
			computeRisk({
				elapsedMs: 35 * 60_000,
				anchorMs: anchor,
				writes: 9,
				phasesTotal: 3,
				phasesDone: 1,
				repeatTop: 2,
			}),
		).toBe("low");
	});

	it("landFreshMs = max(60s, anchor/3)", () => {
		expect(landFreshMs(30 * 60_000)).toBe(10 * 60_000);
		expect(landFreshMs(3 * 60_000)).toBe(60_000);
		expect(landFreshMs(60_000)).toBe(60_000);
	});
});

// ── landing signals: the ledger is the single source ─────────────────────────

describe("collectLandingSignals (ledger-sourced)", () => {
	it("dedups repeated targets like parseWriteFileEvents and ignores [TOOL] worker_file lines", () => {
		const root = mkdtemp();
		const taskDir = path.join(root, "key-a", "workers", "t-land");
		fs.mkdirSync(taskDir, { recursive: true });
		// wjg-w12 shape: 3 appends to progress.md + one report. `[TOOL] worker_file`
		// lines exist too but must NOT add a second source of truth.
		const report = path.join(taskDir, "report-negative-space-audit-20261013.md").replaceAll("\\", "/");
		const progress = path.join(taskDir, "progress.md").replaceAll("\\", "/");
		const tracePath = path.join(taskDir, "trace.log");
		appendWriteFileEvent(tracePath, progress);
		appendWriteFileEvent(tracePath, progress);
		appendWriteFileEvent(tracePath, progress);
		appendWriteFileEvent(tracePath, report);
		fs.appendFileSync(tracePath, `[TOOL] 2026-10-13T17:30:00.000Z worker_file progress.md\n`, "utf8");
		fs.appendFileSync(tracePath, `[TOOL] 2026-10-13T17:31:00.000Z worker_file report-…md\n`, "utf8");
		fs.writeFileSync(path.join(taskDir, "progress.md"), "note\n", "utf8");
		fs.writeFileSync(path.join(taskDir, "report-negative-space-audit-20261013.md"), "x".repeat(37_149), "utf8");
		// T-12: pin the clock from the real mtime instead of `Date.now()`. NTFS
		// mtime granularity can land a few ms after `Date.now()`, which used to
		// make this assertion flaky (write looked "in the future").
		const writtenMtimeMs = Math.max(
			fs.statSync(path.join(taskDir, "progress.md")).mtimeMs,
			fs.statSync(path.join(taskDir, "report-negative-space-audit-20261013.md")).mtimeMs,
		);

		const signals = collectLandingSignals({
			taskDir,
			traceText: fs.readFileSync(tracePath, "utf8"),
			progressText: "CKPT 30m converging=yes eta≈0m 任务已完成\n",
			startedAtMs: writtenMtimeMs - 60_000,
			nowMs: writtenMtimeMs + 100,
		});
		expect(signals.landed).toBe(2);
		expect(signals.artifactPresent).toBe(true);
		expect(signals.progressDone).toBe(true);
		expect(signals.lastLandingAgeMs).toBeDefined();
	});

	it("clamps a future target mtime to age 0 instead of skipping the landing (T-12)", () => {
		const root = mkdtemp();
		const taskDir = path.join(root, "key-a", "workers", "t-future");
		fs.mkdirSync(taskDir, { recursive: true });
		const report = path.join(taskDir, "report-future.md").replaceAll("\\", "/");
		appendWriteFileEvent(path.join(taskDir, "trace.log"), report);
		fs.writeFileSync(path.join(taskDir, "report-future.md"), "x".repeat(1_024), "utf8");
		const mtimeMs = fs.statSync(path.join(taskDir, "report-future.md")).mtimeMs;

		const signals = collectLandingSignals({
			taskDir,
			traceText: fs.readFileSync(path.join(taskDir, "trace.log"), "utf8"),
			progressText: "",
			startedAtMs: mtimeMs - 60_000,
			// One millisecond BEFORE the file's mtime: a future mtime. The upper
			// bound must clamp to nowMs (age 0), not drop the landing.
			nowMs: mtimeMs - 1,
		});
		process.stdout.write(
			`[VERIFY] future target mtime: mtime=${mtimeMs} nowMs=${mtimeMs - 1} age=${String(signals.lastLandingAgeMs)} artifact=${String(signals.artifactPresent)}\n`,
		);
		expect(signals.landed).toBe(1);
		expect(signals.lastLandingAgeMs).toBe(0);
		expect(signals.artifactPresent).toBe(true);
	});

	it("clamps a future mtime in the evidence walk too (T-12)", () => {
		const root = mkdtemp();
		const taskDir = path.join(root, "key-b", "workers", "t-evidence-future");
		const evidenceDir = path.join(root, "key-b", "evidence");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.mkdirSync(evidenceDir, { recursive: true });
		const artifact = path.join(evidenceDir, "landing-20261013.md");
		fs.writeFileSync(artifact, "played\n", "utf8");
		const mtimeMs = fs.statSync(artifact).mtimeMs;

		const signals = collectLandingSignals({
			taskDir,
			traceText: "",
			progressText: "",
			startedAtMs: mtimeMs - 60_000,
			nowMs: mtimeMs - 1,
		});
		process.stdout.write(
			`[VERIFY] future evidence mtime: mtime=${mtimeMs} nowMs=${mtimeMs - 1} age=${String(signals.lastLandingAgeMs)} artifact=${String(signals.artifactPresent)}\n`,
		);
		expect(signals.lastLandingAgeMs).toBe(0);
		expect(signals.artifactPresent).toBe(true);
	});

	it("counts a landed-but-vanished target as landed with no age and no artifact", () => {
		const root = mkdtemp();
		const taskDir = path.join(root, "key-a", "workers", "t-gone");
		fs.mkdirSync(taskDir, { recursive: true });
		const ghost = path.join(taskDir, "report-ghost.md").replaceAll("\\", "/");
		appendWriteFileEvent(path.join(taskDir, "trace.log"), ghost);
		const signals = collectLandingSignals({
			taskDir,
			traceText: fs.readFileSync(path.join(taskDir, "trace.log"), "utf8"),
			progressText: "",
			startedAtMs: Date.now() - 60_000,
			nowMs: Date.now(),
		});
		expect(signals.landed).toBe(1);
		expect(signals.lastLandingAgeMs).toBeUndefined();
		expect(signals.artifactPresent).toBe(false);
		expect(signals.progressDone).toBe(false);
	});
});

// ── CHECKPOINT_LINE_RE: old suffix-free line and new suffix both parse ───────

describe("CHECKPOINT_LINE_RE landing suffix compatibility", () => {
	function writeTrace(root: string, taskKey: string, lines: string[]): string {
		const taskDir = path.join(root, "key-a", "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "trace.log"), `${lines.join("\n")}\n`, "utf8");
		return taskDir;
	}

	it("parses the old suffix-free line and leaves the landing fields undefined", () => {
		const root = mkdtemp();
		const taskDir = writeTrace(root, "t-old", [
			"[CHECKPOINT] 2026-10-13T17:33:36.128Z elapsed=1800s reads=111 writes=0 phases=- uniq_targets=0 repeat_top=16 risk=mid",
		]);
		const ck = readTaskProgress(taskDir)?.checkpoint;
		process.stdout.write(
			`[VERIFY] CHECKPOINT_LINE_RE old: risk=${ck?.risk} land=${String(ck?.land)} artifact=${String(ck?.artifactPresent)} done=${String(ck?.progressDone)}\n`,
		);
		expect(ck?.risk).toBe("mid");
		expect(ck?.uniqTargets).toBe(0);
		expect(ck?.land).toBeUndefined();
		expect(ck?.lastLandingS).toBeUndefined();
		expect(ck?.artifactPresent).toBeUndefined();
		expect(ck?.progressDone).toBeUndefined();
	});

	it("parses the new writeless suffix", () => {
		const root = mkdtemp();
		const taskDir = writeTrace(root, "t-new", [
			"[CHECKPOINT] 2026-10-13T17:33:36.128Z elapsed=1800s reads=111 writes=0 phases=- uniq_targets=0 repeat_top=16 risk=low land=2 last_land=84s artifact=yes done=yes",
		]);
		const ck = readTaskProgress(taskDir)?.checkpoint;
		process.stdout.write(
			`[VERIFY] CHECKPOINT_LINE_RE new: risk=${ck?.risk} land=${String(ck?.land)} last_land=${String(ck?.lastLandingS)}s artifact=${String(ck?.artifactPresent)} done=${String(ck?.progressDone)}\n`,
		);
		expect(ck?.risk).toBe("low");
		expect(ck?.land).toBe(2);
		expect(ck?.lastLandingS).toBe(84);
		expect(ck?.artifactPresent).toBe(true);
		expect(ck?.progressDone).toBe(true);
	});

	it("parses the suffix with no surviving landing (last_land=-)", () => {
		const root = mkdtemp();
		const taskDir = writeTrace(root, "t-dash", [
			"[CHECKPOINT] 2026-10-13T17:33:36.128Z elapsed=1800s reads=111 writes=0 phases=- uniq_targets=0 repeat_top=16 risk=mid land=1 last_land=- artifact=no done=no",
		]);
		const ck = readTaskProgress(taskDir)?.checkpoint;
		expect(ck?.land).toBe(1);
		expect(ck?.lastLandingS).toBeUndefined();
		expect(ck?.artifactPresent).toBe(false);
		expect(ck?.progressDone).toBe(false);
	});
});

// ── fake-timer worker driver (same shape as the checkpoint-wiring suite) ─────

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	sent: Array<{ text: string; options?: { deliverAs?: string } }>;
	registered: string[];
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => void>>();
	const sent: Array<{ text: string; options?: { deliverAs?: string } }> = [];
	const registered: string[] = [];
	const pi = {
		on: (name: string, cb: (e: unknown) => void) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: (text: string, options?: { deliverAs?: string }) => {
			sent.push({ text, options });
		},
		setActiveTools: () => {},
		registerTool: (tool: { name?: string }) => {
			if (tool.name) registered.push(tool.name);
		},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		sent,
		registered,
	};
}

/** Activate the worker loop against root/{owner}/workers/{task}; idle threshold
 * is shortened to 60s via env so the interval logic is reachable in-test. */
async function startWorker(
	root: string,
	taskKey: string,
	body: string,
	owner = "key-a",
): Promise<{ worker: FakeWorker; taskDir: string }> {
	const taskDir = path.join(root, owner, "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), body, "utf8");
	const worker = fakeWorkerPi();
	process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
	process.env.PI_WORKER_IDLE_MS = "60000";
	await workerModeActivate(worker.pi);
	return { worker, taskDir };
}

/** Advance to just past the anchor with a stream of activity events, so the
 * 60s idle watchdog never fires first (anchor for a 2m budget is 60s). */
function trickleToAnchor(worker: FakeWorker, steps = 5, stepMs = 15_000): void {
	for (let i = 0; i < steps; i++) {
		vi.advanceTimersByTime(stepMs);
		worker.emit("message_update");
	}
}

function checkpointTraceLine(taskDir: string): string | undefined {
	const tracePath = path.join(taskDir, "trace.log");
	if (!fs.existsSync(tracePath)) return undefined;
	return fs
		.readFileSync(tracePath, "utf8")
		.split("\n")
		.find((line) => line.startsWith("[CHECKPOINT] "));
}

// ── AC-009 replay: wjg-w12 shape and the zero-landing shape ─────────────────

describe("AC-009 replay (wjg-w12 shape vs zero landing)", () => {
	it("wjg-w12 shape: 4 [WRITE_FILE] events + a 37,149 B product ⇒ risk=low (≠ mid)", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			const { worker, taskDir } = await startWorker(root, "t-wjg-w12", "type: review\ntimeout: 2\n\nreview\n");
			// The historical instance: 3 appends to progress.md + one report, and the
			// report is a real 37,149 B product on disk before the checkpoint.
			const report = path.join(taskDir, "report-negative-space-audit-20261013.md").replaceAll("\\", "/");
			const progress = path.join(taskDir, "progress.md").replaceAll("\\", "/");
			const tracePath = path.join(taskDir, "trace.log");
			appendWriteFileEvent(tracePath, progress);
			appendWriteFileEvent(tracePath, progress);
			appendWriteFileEvent(tracePath, progress);
			appendWriteFileEvent(tracePath, report);
			fs.writeFileSync(path.join(taskDir, "progress.md"), "CKPT 30m converging=yes eta≈0m 任务已完成\n", "utf8");
			fs.writeFileSync(path.join(taskDir, "report-negative-space-audit-20261013.md"), "x".repeat(37_149), "utf8");

			trickleToAnchor(worker);

			const line = checkpointTraceLine(taskDir);
			expect(line).toBeDefined();
			expect(line).toMatch(/ risk=low land=2 last_land=\d+s artifact=yes done=yes$/);
			process.stdout.write(`[VERIFY] AC-009 wjg-w12-shape line after: ${line}\n`);
			const ck = readTaskProgress(taskDir)?.checkpoint;
			expect(ck?.risk).not.toBe("mid");
			expect(ck?.risk).toBe("low");
			expect(ck?.land).toBe(2);
			expect(ck?.artifactPresent).toBe(true);
			expect(ck?.progressDone).toBe(true);
			expect(exitSpy).not.toHaveBeenCalled();
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});

	it("zero landing + no completion record ⇒ risk=high (≥ mid), land=0 artifact=no done=no", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			const { worker, taskDir } = await startWorker(root, "t-no-land", "type: review\ntimeout: 2\n\nreview\n");
			trickleToAnchor(worker);

			const line = checkpointTraceLine(taskDir);
			expect(line).toBeDefined();
			expect(line).toMatch(/ risk=high land=0 last_land=- artifact=no done=no$/);
			process.stdout.write(`[VERIFY] AC-009 zero-landing line after: ${line}\n`);
			const ck = readTaskProgress(taskDir)?.checkpoint;
			expect(ck?.risk).toBe("high");
			expect(ck?.land).toBe(0);
			expect(ck?.artifactPresent).toBe(false);
			expect(ck?.progressDone).toBe(false);
			expect(exitSpy).not.toHaveBeenCalled();
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});

	it("write role (coding) keeps the suffix-free [CHECKPOINT] line byte for byte", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			const { worker, taskDir } = await startWorker(root, "t-coding-ckpt", "type: coding\ntimeout: 2\n\nwork\n");
			trickleToAnchor(worker);
			const line = checkpointTraceLine(taskDir);
			expect(line).toBeDefined();
			expect(line).toMatch(
				/^\[CHECKPOINT\] \S+ elapsed=\d+s reads=\d+ writes=\d+ phases=\S+ uniq_targets=\d+ repeat_top=\d+ risk=(?:low|mid|high)$/,
			);
			expect(line).not.toContain("land=");
			expect(exitSpy).not.toHaveBeenCalled();
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});
});

// The real historical instance (design DR4 §2.5): the only run in the corpus
// with an observable [CHECKPOINT] line. It ships with the repo, so the replay is
// reproducible; when the artifact is absent (a shallow checkout) the case is a
// no-op with an explicit log line instead of a false green.
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const WJG_W12_DIR = path.join(REPO_ROOT, ".agenticdoc/mw-worktree-junction-guard/workers/wjg-w12-negative-space-audit");

describe("wjg-w12 artifact replay", () => {
	it("replays the real trace through the new criterion (mid → low) and prints both lines", () => {
		const tracePath = path.join(WJG_W12_DIR, "trace.log");
		if (!fs.existsSync(tracePath)) {
			process.stdout.write("[VERIFY] wjg-w12 replay: artifact absent, skipped\n");
			return;
		}
		const traceText = fs.readFileSync(tracePath, "utf8");
		const progressText = fs.readFileSync(path.join(WJG_W12_DIR, "progress.md"), "utf8");
		const before = traceText.split("\n").find((line) => line.startsWith("[CHECKPOINT] "));
		expect(before).toBeDefined();
		const ts = (before ?? "").slice("[CHECKPOINT] ".length).split(" ")[0] ?? "";
		const checkpointMs = Date.parse(ts);

		const cwd = process.cwd();
		let signals: ReturnType<typeof collectLandingSignals>;
		try {
			// The real trace stores project-root-relative [WRITE_FILE] paths.
			process.chdir(REPO_ROOT);
			signals = collectLandingSignals({
				taskDir: WJG_W12_DIR,
				traceText,
				progressText,
				startedAtMs: checkpointMs - 1800_000,
				nowMs: checkpointMs,
			});
		} finally {
			process.chdir(cwd);
		}
		const risk = computeRisk({
			elapsedMs: 1800_000,
			anchorMs: 30 * 60_000,
			writes: 0,
			phasesTotal: 0,
			phasesDone: 0,
			repeatTop: 16,
			...signals,
		});
		const lastLand = signals.lastLandingAgeMs === undefined ? "-" : `${Math.round(signals.lastLandingAgeMs / 1000)}s`;
		const after = `[CHECKPOINT] ${ts} elapsed=1800s reads=111 writes=0 phases=- uniq_targets=0 repeat_top=16 risk=${risk} land=${signals.landed} last_land=${lastLand} artifact=${signals.artifactPresent ? "yes" : "no"} done=${signals.progressDone ? "yes" : "no"}`;
		process.stdout.write(`[VERIFY] wjg-w12 replay before: ${before}
`);
		process.stdout.write(`[VERIFY] wjg-w12 replay after:  ${after}
`);
		expect(risk).not.toBe("mid");
		expect(risk).toBe("low");
		expect(signals.landed).toBe(2);
	});
});

// ── I3: idle / wall / deadline-steer never read risk ────────────────────────

describe("watchdog invariants with the writeless checkpoint (I3)", () => {
	it("I3-a normal activity: no idle kill, checkpoint written, no [TIMEOUT]", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			// budget 3m: anchor = min(30m, 90s) = 90s. 7 x 15s = 105s crosses the
			// anchor while activity every 15s keeps the 60s idle clock fresh.
			const { worker, taskDir } = await startWorker(root, "t-i3-active", "type: research\ntimeout: 3\n\nresearch\n");
			for (let i = 0; i < 7; i++) {
				vi.advanceTimersByTime(15_000);
				worker.emit("message_update");
			}
			expect(exitSpy).not.toHaveBeenCalled();
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).not.toContain("[TIMEOUT]");
			// A writeless run past its anchor wrote the landing-suffixed line.
			expect(trace).toContain("[CHECKPOINT] ");
			expect(trace).toMatch(
				/risk=(?:low|mid|high) land=\d+ last_land=(?:\d+s|-) artifact=(?:yes|no) done=(?:yes|no)/,
			);
			// Normal settle: an [END] line and still no watchdog kill (the research
			// role has no product, so the exit code is 2 — irrelevant here).
			worker.emit("agent_end", { messages: [] });
			worker.emit("agent_settled");
			expect(exitSpy).not.toHaveBeenCalled();
			const settled = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			process.stdout.write(
				`[VERIFY] I3-a active: exit_called=${exitSpy.mock.calls.length > 0} timeout=${settled.includes("[TIMEOUT]")} checkpoint=${checkpointTraceLine(taskDir)}\n`,
			);
			expect(settled).toContain("[END] ");
			expect(settled).not.toContain("[TIMEOUT]");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});

	it("I3-b true hang: no activity for idleMs still kills with the idle evidence", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			const { taskDir } = await startWorker(root, "t-i3-hang", "type: research\ntimeout: 30\n\nresearch\n");
			vi.advanceTimersByTime(60_000);
			expect(exitSpy).toHaveBeenCalledWith(1);
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			const timeoutLine = trace.split("\n").find((line) => line.startsWith("[TIMEOUT] ")) ?? "(none)";
			process.stdout.write(`[VERIFY] I3-b hang: exit=${String(exitSpy.mock.calls[0]?.[0])} ${timeoutLine}\n`);
			expect(trace).toContain("[TIMEOUT]");
			expect(trace).toContain("idle: no activity for 60s");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("idle timeout: no activity for 60s");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});

	it("I3-c budget tail: checkpoint → deadline steer → wall kill, in order", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			// budget 3m: anchor = min(30m, 90s) = 90s, steer at 135s, wall at 180s.
			const { worker, taskDir } = await startWorker(root, "t-i3-tail", "type: research\ntimeout: 3\n\nresearch\n");
			for (let t = 0; t < 12; t++) {
				vi.advanceTimersByTime(15_000);
				worker.emit("message_update");
			}
			const steer = worker.sent.find((m) => m.text.includes("[mw deadline]"));
			const ckpt = worker.sent.find((m) => m.text.includes("[mw checkpoint]"));
			expect(steer?.options?.deliverAs).toBe("steer");
			expect(ckpt?.options?.deliverAs).toBe("followUp");
			expect(worker.sent.findIndex((m) => m.text.includes("[mw checkpoint]"))).toBeLessThan(
				worker.sent.findIndex((m) => m.text.includes("[mw deadline]")),
			);
			expect(exitSpy).toHaveBeenCalledWith(1);
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			const wallLine = trace.split("\n").find((line) => line.startsWith("[TIMEOUT] ")) ?? "(none)";
			process.stdout.write(
				`[VERIFY] I3-c tail: exit=${String(exitSpy.mock.calls[0]?.[0])} order=checkpoint<deadline wall_line=${wallLine}\n`,
			);
			expect(trace).toContain("wall: budget 180s exceeded");
			expect(trace).toContain("exit=1");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
		}
	});
});
