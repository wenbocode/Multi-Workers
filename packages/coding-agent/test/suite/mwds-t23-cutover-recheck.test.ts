/**
 * mwds-t23-cutover-recheck.test.ts — T-23 (key mw-dispatch-card-gate, wave 15):
 * post-cutover runtime re-check. After `mw build --install` (bundle
 * A5B0FC9C…4932 -> 975D4066…978D) + service restart, verify on the REAL
 * runtime path that
 *
 *   (2) `card_audit` counts this card as a dispatch (not unlisted), and
 *   (3) the T-21 write-intent judgement still holds: a forbidden-surface /
 *       negated report is NOT red, while a real declared-but-unrecorded write
 *       IS still red, and the dotless (`scripts/deploy`) case is reported
 *       honestly (miss-analysis, not silently green-washed);
 *   (4) the repo bundle and the globally installed bundle are the same source
 *       (verified separately by the read-only script in the worker taskDir;
 *       the sha256 expectation is asserted here from the card text).
 *
 * Requirement 1 (the T-18 identity header) is asserted as a live sample: this
 * worker's own `task.md` is read (read-only) and its pre-`##` header region
 * must carry `card_path:` / `card_sha256:` / `envelope_producer:`.
 *
 * The judgement chain under test is imported directly:
 * `change-ledger.ts::diffLedger` / `collectMalformedCandidates` /
 * `stripNonDeclarativeSpans` and `output-writer.ts::readTerminalGaps`.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
	collectMalformedCandidates,
	diffLedger,
	stripNonDeclarativeSpans,
} from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import { readTerminalGaps } from "../../src/extensions/agent-team-loop/worker/output-writer.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const KEY_DIR = path.join(REPO_ROOT, ".agenticdoc", "mw-dispatch-card-gate");
const WORKERS_DIR = path.join(KEY_DIR, "workers");
const WORKER_ID = "mwd-t23-cutover-recheck";
const TASK_MD = path.join(WORKERS_DIR, WORKER_ID, "task.md");
const CARD_MD = path.join(KEY_DIR, "tasks", "T-23-cutover-runtime-recheck.md");

const EXPECTED_BUNDLE_SHA = "975D4066967E35CC7F23713827F5CA85809578B96A07D3283206931341F9978D";
const ALLOWED_TEST_FILE = "packages/coding-agent/test/suite/mwds-t23-cutover-recheck.test.ts";

// ── helpers ──────────────────────────────────────────────────────────────────

function report(section: string, body: readonly string[]): string {
	return ["## 结论", "", "done", "", `## ${section}`, "", ...body, "", "## 残留与未验证", "", "none"].join("\n");
}

function trace(recorded: readonly string[]): string {
	return recorded.map((file) => `[WRITE_FILE] path=${file}`).join("\n");
}

/** Read a worker's task.md header region: the lines before the first `##`. */
function headerRegion(text: string): string {
	const lines = text.split(/\r?\n/);
	const end = lines.findIndex((line) => line.startsWith("## "));
	return lines.slice(0, end === -1 ? lines.length : end).join("\n");
}

function headerValue(text: string, key: string): string {
	for (const line of headerRegion(text).split(/\r?\n/)) {
		const match = new RegExp(`^${key}\\s*:\\s*(.*)$`).exec(line);
		if (match !== null) return match[1].trim();
	}
	return "";
}

/** Verbatim lines of the card's `写入允许面` / `写入禁止面` bullets (交付格式). */
function surfaceLines(text: string): { allowed: string; forbidden: string } {
	let allowed = "";
	let forbidden = "";
	for (const line of text.split(/\r?\n/)) {
		if (line.startsWith("- 写入允许面：") && allowed === "") allowed = line;
		if (line.startsWith("- 写入禁止面：") && forbidden === "") forbidden = line;
	}
	return { allowed, forbidden };
}

const FORBIDDEN_PATHS = ["packages/coding-agent/src/**", "packages/multi-workers/**", ".agenticdoc/**"] as const;
const RESIDUE = ["host/pid", "/workers", "/task.md", "trace.log"] as const;

/** Run `readTerminalGaps` (the real worker-mode settle path) against a
 * disposable agenticdoc root: `<tmp>/<taskKey>/{task.md,report.md,trace.log}`. */
function terminalGaps(taskKey: string, reportText: string, traceText: string): ReturnType<typeof readTerminalGaps> {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mwds-t23-"));
	const dir = path.join(root, taskKey);
	try {
		fs.mkdirSync(dir, { recursive: true });
		fs.writeFileSync(path.join(dir, "task.md"), "type: coding\n", "utf8");
		fs.writeFileSync(path.join(dir, "report.md"), reportText, "utf8");
		fs.writeFileSync(path.join(dir, "trace.log"), traceText, "utf8");
		return readTerminalGaps({
			taskKey,
			agenticdocRoot: root,
			summary: "done",
			type: "coding",
			judgeRecovery: false,
		});
	} finally {
		fs.rmSync(root, { recursive: true, force: true });
	}
}

const taskText = fs.existsSync(TASK_MD) ? fs.readFileSync(TASK_MD, "utf8") : "";
const cardText = fs.existsSync(CARD_MD) ? fs.readFileSync(CARD_MD, "utf8") : "";
const surfaces = taskText === "" ? { allowed: "", forbidden: "" } : surfaceLines(taskText);

// ── requirement 1: T-18 runtime identity header (live sample) ────────────────

describe("T-23 requirement 1 — T-18 identity header on the real dispatch", () => {
	it("this worker's task.md carries card_path / card_sha256 / envelope_producer", () => {
		expect(taskText).not.toBe("");
		const header = headerRegion(taskText);
		console.log(`[VERIFY] T23-1 header_region_start\n${header}\n[VERIFY] T23-1 header_region_end`);

		const cardPath = headerValue(taskText, "card_path");
		const cardSha = headerValue(taskText, "card_sha256");
		const producer = headerValue(taskText, "envelope_producer");

		expect(cardPath).toBe("tasks/T-23-cutover-runtime-recheck.md");
		expect(cardSha).toMatch(/^[0-9a-f]{64}$/);
		expect(producer).toMatch(/^agent-team-loop-pm@\S+$/);

		// The recorded digest must be the card's real, EOL-normalized sha256
		// (same recipe as card_audit.py / mw_common.sha256_eol_normalized).
		const computed = createHash("sha256").update(cardText.replace(/\r\n/g, "\n"), "utf8").digest("hex");
		expect(cardSha).toBe(computed);

		console.log(`[VERIFY] T23-1 card_path=${cardPath} sha_ok=${cardSha === computed} producer=${producer}`);
	});

	it("a missing header line is reported as T-18-not-in-effect (the assertion that would fire)", () => {
		// Shape guard: a header-less dispatch (the pre-T-18 form) fails all three
		// checks above, so the test cannot silently pass on a stale dispatch.
		const legacy = "type: coding\n\n卡（唯一权威…）：tasks/T-23.md\n";
		expect(headerValue(legacy, "card_path")).toBe("");
		expect(headerValue(legacy, "card_sha256")).toBe("");
		expect(headerValue(legacy, "envelope_producer")).toBe("");
	});
});

// ── requirement 3a: positive case must not be red ────────────────────────────

describe("T-23 requirement 3a — forbidden surface / negation is not a declaration", () => {
	it("the verbatim 写入禁止面 bullet + negated prose leave extra empty and leak no residue", () => {
		expect(surfaces.forbidden).not.toBe("");
		expect(surfaces.allowed).toContain(ALLOWED_TEST_FILE);

		const body = [
			// The real 写入允许面 bullet (declares the one file this worker writes)
			// with report-flavoured residue appended AFTER the declaration token.
			`${surfaces.allowed} 取证见 trace.log 与 task.md（只读），含 host/pid、/workers 之类词元。`,
			// The real 写入禁止面 bullet, verbatim.
			surfaces.forbidden,
			// The required negated prose.
			"未写入 `src/**`、`packages/multi-workers/**`、`.agenticdoc/**`；未写 `host/pid`，也未触碰 `/workers`、`/task.md`、`trace.log`。",
		];
		const reportText = report("改动清单", body);
		const ledger = diffLedger(reportText, trace([ALLOWED_TEST_FILE]));
		const malformed = collectMalformedCandidates(reportText);

		console.log(`[VERIFY] T23-3a declared=[${ledger.declared.join(",")}]`);
		console.log(`[VERIFY] T23-3a extra=[${ledger.extra.join(",")}]`);
		console.log(`[VERIFY] T23-3a malformed=[${malformed.join(",")}]`);

		// Only the real write is declared; the forbidden surface and the residue
		// never become declarations, so `extra` is empty.
		expect(ledger.declared).toEqual([ALLOWED_TEST_FILE]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);

		for (const forbidden of [...FORBIDDEN_PATHS, ...RESIDUE]) {
			expect(ledger.declared).not.toContain(forbidden);
			expect(ledger.extra).not.toContain(forbidden);
		}
		// The separator-bearing forbidden shapes are counted as warn-only
		// malformed candidates, not as judgement.
		expect(malformed).toContain("packages/coding-agent/src/**");
		expect(malformed).toContain("packages/multi-workers/**");
		expect(malformed).toContain(".agenticdoc/**");
		expect(malformed).toContain("host/pid");
		expect(malformed).toContain("/workers");
	});

	it("the same positive report is green through readTerminalGaps (worker settle path)", () => {
		expect(surfaces.forbidden).not.toBe("");
		const reportText = report("改动清单", [surfaces.allowed, surfaces.forbidden]);
		const gaps = terminalGaps(WORKER_ID, reportText, trace([ALLOWED_TEST_FILE]));
		console.log(
			`[VERIFY] T23-3a terminal judged=${gaps.judged} unrecorded=[${gaps.unrecordedFiles.join(",")}] ` +
				`unjudgeable=[${gaps.unjudgeableFiles.join(",")}] ok=${gaps.ok}`,
		);
		expect(gaps.judged).toBe(true);
		expect(gaps.unrecordedFiles).toEqual([]);
		expect(gaps.unjudgeableFiles).toEqual([]);
		expect(gaps.ok).toBe(true);
	});

	it("stripNonDeclarativeSpans drops the mw-dispatch-card contract block", () => {
		const stripped = stripNonDeclarativeSpans(taskText);
		expect(stripped).not.toContain("mw-dispatch-card: v1");
		// The card-internal 交付格式 bullet (leading `- `, backticked path) sits
		// inside the marker and is stripped; the out-of-marker tail prose of the
		// same bullet survives because it is plain markdown.
		expect(stripped).not.toContain("- 写入允许面：`");
		expect(stripped).toContain("写入允许面：packages/coding-agent/test/suite/mwds-t23-cutover-recheck.test.ts");
	});
});

// ── requirement 3b: negative case must stay red ──────────────────────────────

describe("T-23 requirement 3b — a real unrecorded write is still red", () => {
	const declared = "packages/multi-workers/launcher.py";

	it("diffLedger: declared launcher.py without a [WRITE_FILE] event lands in extra", () => {
		const ledger = diffLedger(report("改动清单", [`- ${declared} — 越界声明`]), trace([ALLOWED_TEST_FILE]));
		console.log(`[VERIFY] T23-3b declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`);
		expect(ledger.declared).toEqual([declared]);
		expect(ledger.extra).toEqual([declared]);
	});

	it("readTerminalGaps: the same report makes the settle verdict not-ok", () => {
		const gaps = terminalGaps(
			WORKER_ID,
			report("改动清单", [`- ${declared} — 越界声明`]),
			trace([ALLOWED_TEST_FILE]),
		);
		console.log(`[VERIFY] T23-3b terminal unrecorded=[${gaps.unrecordedFiles.join(",")}] ok=${gaps.ok}`);
		expect(gaps.unrecordedFiles).toEqual([declared]);
		expect(gaps.ok).toBe(false);
	});
});

// ── requirement 3c: dotless declaration (PM-registered miss risk) ────────────

describe("T-23 requirement 3c — dotless `scripts/deploy`", () => {
	const declared = "scripts/deploy";

	it("with a matching event: not declared, counted malformed (extra empty by luck)", () => {
		const reportText = report("改动清单", [`- ${declared} — 无扩展名部署脚本`]);
		const ledger = diffLedger(reportText, trace([declared]));
		const malformed = collectMalformedCandidates(reportText);
		console.log(
			`[VERIFY] T23-3c declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] ` +
				`malformed=[${malformed.join(",")}]`,
		);
		// The token is refused by the shape whitelist (dotted-basename rule),
		// so it is malformed, never a declaration — even though the trace
		// recorded exactly this file.
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
		expect(malformed).toContain(declared);
	});

	it("miss proof: without the event it is still not red (the judge cannot see it)", () => {
		const reportText = report("改动清单", [`- ${declared} — 无扩展名部署脚本`]);
		// Non-empty trace so this is not the "zero events ⇒ unjudgeable" branch.
		const ledger = diffLedger(reportText, trace(["packages/coding-agent/src/other.ts"]));
		const gaps = terminalGaps(WORKER_ID, reportText, trace(["packages/coding-agent/src/other.ts"]));
		console.log(
			`[VERIFY] T23-3c-miss diffLedger_extra=[${ledger.extra.join(",")}] ` +
				`terminal_unrecorded=[${gaps.unrecordedFiles.join(",")}] terminal_ok=${gaps.ok}`,
		);
		expect(ledger.extra).toEqual([]); // would be [scripts/deploy] if it were declared
		expect(gaps.unrecordedFiles).toEqual([]);
		expect(gaps.ok).toBe(true);
	});
});

// ── requirement 4 (asserted from card text): bundle sha expectation ──────────

describe("T-23 requirement 4 — same-source bundle sha expectation", () => {
	it("the card names the expected bundle sha256 (read-only script compares both copies)", () => {
		const shaInCard = /975D4066967E35CC7F23713827F5CA85809578B96A07D3283206931341F9978D/.test(cardText);
		expect(shaInCard).toBe(true);
		expect(EXPECTED_BUNDLE_SHA).toMatch(/^[0-9A-F]{64}$/);
		const repoBundle = path.join(REPO_ROOT, "packages", "multi-workers", "dist", "extensions", "agent-team-loop.js");
		expect(fs.existsSync(repoBundle)).toBe(true);
		const digest = createHash("sha256").update(fs.readFileSync(repoBundle)).digest("hex").toUpperCase();
		console.log(`[VERIFY] T23-4 repo_bundle_sha=${digest}`);
		// The repo bundle is the expected one; the global copy's equality is
		// proven by the worker taskDir script (no literal protected-config path
		// in any command here).
		expect(digest).toBe(EXPECTED_BUNDLE_SHA);
	});
});
