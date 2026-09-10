/**
 * Tests for the agent-team-loop TL;DR normalization (mw-widget-terminal-lifecycle
 * T-03, AC-009 write half / D-005).
 *
 * Kept separate from agent-team-loop.test.ts by dispatch constraint. Covers:
 * - headline() sample regression (design-terminal-summary-quality research),
 * - the writeOutput `## TL;DR` first section across exit codes, with the
 *   verbatim `## Summary` still readable by the old readOutputSummary regex
 *   (spec §5 pitfall),
 * - the deadline-steer first-line-conclusion wording (steer half of AC-009).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { readOutputSummary } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { headline, writeOutput } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "atl-tldr-"));
}

/** Extract the `## TL;DR` section body (trimmed) from an output.md string —
 * the same section-regex shape readOutputSummary uses on `## Summary`. */
function readTldr(out: string): string | undefined {
	const m = out.match(/## TL;DR\s*\n+([\s\S]*?)(?=\n## |$)/);
	return m ? m[1].trim() : undefined;
}

// ── headline normalization (D-005) ────────────────────────────────────────────

describe("headline normalization (D-005)", () => {
	it("strips leading markdown markers from the research samples", () => {
		expect(headline("## (a) BLOCKING issues")).toBe("(a) BLOCKING issues");
		expect(headline("## Task 002 执行完毕（TDD red 阶段完成）")).toBe("Task 002 执行完毕（TDD red 阶段完成）");
		expect(headline("T-03 complete. All deliverables in place, tests green.")).toBe(
			"T-03 complete. All deliverables in place, tests green.",
		);
		expect(headline("**bold** 开头")).toBe("bold** 开头");
		expect(headline("- list item")).toBe("list item");
		expect(headline("> quoted conclusion")).toBe("quoted conclusion");
	});

	it("takes the first non-empty line, strips stacked markers, collapses whitespace", () => {
		expect(headline("\n\n   \nfirst   line\twith gaps\nsecond line")).toBe("first line with gaps");
		expect(headline("- **## deep** marker")).toBe("deep** marker");
	});

	it("caps the result at 100 chars (ellipsis, truncLine style)", () => {
		expect(headline("y".repeat(100))).toBe("y".repeat(100));
		const over = headline("z".repeat(150));
		expect(over.length).toBe(100);
		expect(over).toBe(`${"z".repeat(99)}…`);
		expect(headline("z".repeat(101)).length).toBe(100);
	});

	it("returns (no conclusion) for empty, blank, or marker-only input", () => {
		expect(headline("")).toBe("(no conclusion)");
		expect(headline("   \n\t\n  \n")).toBe("(no conclusion)");
		// `**` needs no trailing whitespace, so a bold-only line strips to nothing;
		// hash/bullet/quote markers DO (spec: marker + whitespace — `#5` issue
		// refs must survive), so a hash-only residue stays. T-05's display-side
		// fallback mirrors this same rule (D-004 shared cleaning).
		expect(headline("**")).toBe("(no conclusion)");
		expect(headline("## ")).toBe("##");
	});
});

// ── writeOutput TL;DR first section (AC-009 write half) ──────────────────────

describe("writeOutput TL;DR first section (AC-009 write half)", () => {
	it("prepends ## TL;DR before ## Summary on exit codes 0/1/2; Summary stays verbatim", () => {
		const summary = "## Done: headline normalization shipped";
		for (const exitCode of [0, 1, 2] as const) {
			const root = mkdtemp();
			const key = `tldr-exit-${exitCode}`;
			writeOutput({
				taskKey: key,
				agenticdocRoot: root,
				exitCode,
				summary,
				changedFiles: ["src/a.ts"],
				verificationSteps: "vitest green",
				questions: "Which scope?",
				exitReason: "settled",
			});
			const dir = path.join(root, key);
			const out = fs.readFileSync(path.join(dir, "output.md"), "utf8");
			// TL;DR is the first section on every exit path, ahead of Summary.
			expect(out.startsWith("## TL;DR\n\nDone: headline normalization shipped\n\n## Summary\n\n")).toBe(true);
			expect(readTldr(out)).toBe("Done: headline normalization shipped");
			// The verbatim ## Summary section is unchanged and still readable by
			// the old regex (readOutputSummary compatibility).
			expect(readOutputSummary(dir)).toBe(summary);
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("caps the TL;DR at 100 chars with no markdown prefix (VC-009)", () => {
		const root = mkdtemp();
		const key = "tldr-vc009";
		writeOutput({
			taskKey: key,
			agenticdocRoot: root,
			exitCode: 0,
			summary: `## ${"x".repeat(140)}`,
		});
		const out = fs.readFileSync(path.join(root, key, "output.md"), "utf8");
		const tldr = readTldr(out);
		if (!tldr) throw new Error("TL;DR section missing from output.md");
		expect(tldr.length).toBeLessThanOrEqual(100);
		expect(tldr.endsWith("…")).toBe(true);
		expect(tldr).not.toMatch(/^(?:#{1,6}\s|\*\*|[-*]\s|>\s)/);
		console.log("[VERIFY] VC-009: tldr_len<=100, markdown_prefix=absent");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("falls back to (no conclusion) when the summary is empty", () => {
		const root = mkdtemp();
		const key = "tldr-empty";
		writeOutput({ taskKey: key, agenticdocRoot: root, exitCode: 1, summary: "" });
		const out = fs.readFileSync(path.join(root, key, "output.md"), "utf8");
		expect(readTldr(out)).toBe("(no conclusion)");
		expect(readOutputSummary(path.join(root, key))).toBe("(no summary)");
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── deadline steer first-line conclusion (AC-009 steer half) ─────────────────

describe("deadline steer first-line conclusion (AC-009 steer half)", () => {
	it("the [mw deadline] message demands a single-line conclusion as the first line", async () => {
		const root = mkdtemp();
		const taskDir = path.join(root, "key-a", "workers", "t-steer");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\ntimeout: 3\n\nwork\n", "utf8");
		const sent: Array<{ text: string; options?: { deliverAs?: string } }> = [];
		const pi = {
			on: () => {},
			sendUserMessage: (text: string, options?: { deliverAs?: string }) => {
				sent.push({ text, options });
			},
		} as unknown as ExtensionAPI;
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
			await workerModeActivate(pi);
			// Budget 3m → steer at 180s - min(5m, 45s) = 135s; the wall kill (180s)
			// and the 10m default idle watchdog stay out of the way at 140s.
			vi.advanceTimersByTime(140_000);
			const steer = sent.find((m) => m.text.includes("[mw deadline]"));
			expect(steer).toBeDefined();
			expect(steer?.text).toContain("最终回复第一行必须是单行结论（状态 + 关键产出/卡点）");
			expect(steer?.options?.deliverAs).toBe("steer");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});
