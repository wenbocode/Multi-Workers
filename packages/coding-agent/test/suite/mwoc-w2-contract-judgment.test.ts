/**
 * mwoc-w2-contract-judgment.test.ts — T-05 / key `mw-worker-output-contract`
 * (design §4, AC-001/002/003/004/005/014/015).
 *
 * What is pinned here:
 *   1. AC-001 — the H2-heading recovery predicate: the 8-case matrix (all five
 *      headings / missing 1 / missing 2 / missing 5 / body-only alias with no
 *      heading / alias heading / duplicate heading / blockquoted heading), plus
 *      fenced-code and `###` exclusions. Body text never satisfies a section
 *      (the FW-001 self-witness hole is closed).
 *   2. AC-002 — the settle readback names ALL missing sections exactly, and the
 *      per-case `exit=2` count matches the expected table.
 *   3. AC-015 — the judged product candidate order `report.md` →
 *      `report-<slug>.md` (mtime desc) → `output.md`, and the second entry point
 *      (`hasReportProduct`) agreeing with the judged text.
 *   4. AC-005 — the I2 mechanical `## 上下文来源` backfill: before the judgement,
 *      into the file the judgement reads, pure append, idempotent, fail-closed;
 *      plus a 3-case replay of real historical mechanical-only products
 *      (`exit=2 → exit=0`).
 *   5. AC-004 — the structured pre-settle gap (`recovery-gap` trace row) and the
 *      "first settle misses one section, fix, second settle is green" flow.
 *   6. I1 — the self-check follow-up turn fires once per process.
 *   7. AC-003 (TS half) — `renderCardSeedSections` injects
 *      `## 交付段契约（本角色）` for the card-declared writeless report roles,
 *      idempotently, and a card-less/type-less render is byte-stable.
 *   8. AC-014 — the corrected attribution in `output-sections.ts` matches the
 *      corrected `_framework-reflect.md` FW-001 修法 5.
 *
 * No provider APIs, keys or network: the settle cases drive `workerModeActivate`
 * through a fake ExtensionAPI (the `dispatch-recovery-terminal.test.ts` pattern).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	applyCardSeedSections,
	CARD_SEED_DISCLAIMER,
	CARD_SEED_MARKER,
	CARD_SEED_MARKER_END,
	type CardSections,
	readOutputSection,
	readTerminalDetail,
	renderCardSeedSections,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { RunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { readTaskType } from "../../src/extensions/agent-team-loop/shared/task-frontmatter.ts";
import {
	checkRecovery,
	h2Headings,
	MECHANICAL_SECTIONS,
	RECOVERY_CONTRACT_HEADING,
	RECOVERY_SECTIONS,
	recoveryContractSection,
	recoverySectionsFor,
} from "../../src/extensions/agent-team-loop/worker/output-sections.ts";
import {
	agentProductText,
	appendMechanicalContextSources,
	hasReportProduct,
	judgedProductFile,
	MECHANICAL_CONTEXT_MARKER,
	readTerminalGaps,
} from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const REPO_ROOT = fileURLToPath(new URL("../../../..", import.meta.url));

// ── fixtures ─────────────────────────────────────────────────────────────────

const tempDirs: string[] = [];
function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

let savedCwd = process.cwd();
beforeEach(() => {
	savedCwd = process.cwd();
});
afterEach(() => {
	process.chdir(savedCwd);
	delete process.env.PI_WORKER_TASK;
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function headings(names: string[]): string {
	return names.map((name) => `## ${name}\n\nbody\n`).join("\n");
}

const BASE = [...RECOVERY_SECTIONS];
const ALL_FIVE = headings([...BASE, "改动清单"]);
const COMPLETE_RESEARCH = headings([...BASE]);

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
	taskKey: string;
}

function makeFixture(
	opts: {
		type?: string;
		key?: string;
		task?: string;
		report?: string;
		output?: string;
		trace?: string;
		cardPath?: string;
		cardSha?: string;
	} = {},
): Fixture {
	const projectRoot = mkdtemp("mwoc-w2-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const key = opts.key ?? "mwoc-w2";
	const task = opts.task ?? "w2-worker";
	const keyDir = path.join(trueRoot, key);
	const taskDir = path.join(keyDir, "workers", task);
	fs.mkdirSync(taskDir, { recursive: true });
	const head = opts.type === undefined ? "" : `type: ${opts.type}\n`;
	const card =
		opts.cardPath === undefined
			? ""
			: `card_path: ${opts.cardPath}\n` + (opts.cardSha === undefined ? "" : `card_sha256: ${opts.cardSha}\n`);
	fs.writeFileSync(path.join(taskDir, "task.md"), `${head}${card}\nwork\n`, "utf8");
	if (opts.report !== undefined) fs.writeFileSync(path.join(taskDir, "report.md"), opts.report, "utf8");
	if (opts.output !== undefined) fs.writeFileSync(path.join(taskDir, "output.md"), opts.output, "utf8");
	if (opts.trace !== undefined) fs.writeFileSync(path.join(taskDir, "trace.log"), opts.trace, "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir, taskKey: `${key}/workers/${task}` };
}

interface SentMessage {
	text: string;
	deliverAs?: string;
}

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	sent: SentMessage[];
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => unknown>>();
	const sent: SentMessage[] = [];
	const pi = {
		on: (name: string, cb: (e: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: (text: string, opts?: { deliverAs?: string }) => {
			sent.push({ text, deliverAs: opts?.deliverAs });
		},
		setActiveTools: () => {},
		registerTool: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		sent,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
	};
}

async function startWorker(fx: Fixture): Promise<FakeWorker> {
	process.env.PI_WORKER_TASK = path.join(fx.taskDir, "task.md");
	process.chdir(fx.projectRoot);
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return worker;
}

function settle(worker: FakeWorker, reply: string): void {
	worker.emit("agent_end", { messages: [{ role: "assistant", content: [{ type: "text", text: reply }] }] });
	worker.emit("agent_settled");
}

function readRun(fx: Fixture): RunState {
	return JSON.parse(fs.readFileSync(path.join(fx.taskDir, "run.json"), "utf8")) as RunState;
}

function readTrace(fx: Fixture): string {
	try {
		return fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
	} catch {
		return "";
	}
}

/** The exact `缺失段：` list off the settle readback line, or `[]`. */
function readbackMissing(fx: Fixture): string[] {
	const detail = readTerminalDetail(fx.taskDir, "needs-clarification");
	const match = /缺失段：([^|\n]+)/.exec(detail);
	return match === null ? [] : (match[1] ?? "").split("、");
}

// ── 1. AC-001: the H2-heading predicate matrix ──────────────────────────────

describe("AC-001 H2-heading recovery predicate", () => {
	const matrix: Array<{ name: string; text: string; type: string; expected: string[] }> = [
		{ name: "all five headings (coding) => ok", text: ALL_FIVE, type: "coding", expected: [] },
		{
			name: "missing 1 (证据)",
			text: headings(["结论", "残留与未验证", "上下文来源", "改动清单"]),
			type: "coding",
			expected: ["证据"],
		},
		{
			name: "missing 2 (证据 + 残留与未验证)",
			text: headings(["结论", "上下文来源", "改动清单"]),
			type: "coding",
			expected: ["证据", "残留与未验证"],
		},
		{
			name: "missing 5 (no headings at all)",
			text: "这是一段没有任何标题的正文，提到结论、证据、残留、上下文来源、改动清单。",
			type: "coding",
			expected: [...BASE, "改动清单"],
		},
		{
			name: "body-only aliases, no heading => missing (FW-001 hole closed)",
			text: [
				"结论：已经查清。",
				"证据：见 [VERIFY] 行。",
				"残留与未验证：无。",
				"上下文来源：spec.md:12。",
				"改动清单：src/a.ts。",
			].join("\n"),
			type: "coding",
			expected: [...BASE, "改动清单"],
		},
		{
			name: "alias headings satisfy the sections",
			text: headings(["Summary", "Evidence", "Remaining", "Sources", "Changed Files"]),
			type: "coding",
			expected: [],
		},
		{
			name: "duplicate heading is still one present section",
			text: headings(["结论", "结论", "证据", "残留与未验证", "上下文来源", "改动清单"]),
			type: "coding",
			expected: [],
		},
		{
			name: "blockquoted heading does not count",
			text: ["结论", "证据", "残留与未验证", "上下文来源"].map((n) => `> ## ${n}\n`).join("\n"),
			type: "research",
			expected: [...BASE],
		},
	];

	it.each(matrix)("$name", ({ text, type, expected }) => {
		const verdict = checkRecovery(text, type);
		console.log(`[VERIFY] AC-001 ${JSON.stringify({ type, missing: verdict.missing, ok: verdict.ok })}`);
		expect(verdict.missing).toEqual(expected);
		expect(verdict.ok).toBe(expected.length === 0);
	});

	it("fenced code blocks never contribute headings; `###` is not an H2", () => {
		const fenced = ["## 结论", "## 证据", "## 残留与未验证", "```", "## 上下文来源", "```", "### 上下文来源"].join(
			"\n",
		);
		expect(h2Headings(fenced)).toEqual(["结论", "证据", "残留与未验证"]);
		expect(checkRecovery(fenced, "research").missing).toEqual(["上下文来源"]);
		// A stray `~` fence is a fence too.
		const tilde = ["## 结论", "~~~", "## 证据", "~~~", "## 证据", "## 残留与未验证", "## 上下文来源"].join("\n");
		expect(h2Headings(tilde)).toEqual(["结论", "证据", "残留与未验证", "上下文来源"]);
	});

	it("normalization: trailing `#`, internal whitespace, ASCII case, CRLF", () => {
		expect(h2Headings("##   Changed   Files  ##  \r\n")).toEqual(["changed files"]);
		expect(h2Headings("##\tSummary\t\n")).toEqual(["summary"]);
		const crlf = COMPLETE_RESEARCH.replace(/\n/g, "\r\n");
		expect(checkRecovery(crlf, "research").ok).toBe(true);
		// `##NoSpace` is not a heading (the H2 marker requires whitespace).
		expect(h2Headings("##NoSpace\n")).toEqual([]);
	});

	it("the mechanical whitelist is exactly 上下文来源 and is a whitelist", () => {
		expect([...MECHANICAL_SECTIONS]).toEqual(["上下文来源"]);
		for (const name of ["结论", "证据", "残留与未验证", "改动清单", "未覆盖面声明", "Questions"]) {
			expect(MECHANICAL_SECTIONS).not.toContain(name);
		}
	});
});

// ── 2. AC-002: the readback names every missing section, exit table ─────────

describe("AC-002 settle readback and exit table", () => {
	const cases: Array<{ name: string; report: string; exit: 0 | 2; expected: string[] }> = [
		{ name: "complete report => 0", report: COMPLETE_RESEARCH, exit: 0, expected: [] },
		{
			name: "missing 证据 => 2",
			report: headings(["结论", "残留与未验证", "上下文来源"]),
			exit: 2,
			expected: ["证据"],
		},
		{
			name: "missing 证据+残留 => 2",
			report: headings(["结论", "上下文来源"]),
			exit: 2,
			expected: ["证据", "残留与未验证"],
		},
		{
			name: "missing all four => 2 (the mechanical section is filled by I2)",
			report: "no headings here",
			exit: 2,
			expected: ["结论", "证据", "残留与未验证"],
		},
		{
			name: "missing only the mechanical section => 0 (I2 backfill)",
			report: headings(["结论", "证据", "残留与未验证"]),
			exit: 0,
			expected: [],
		},
	];

	it.each(cases)("$name", async ({ report, exit, expected }) => {
		const fx = makeFixture({ type: "research", report });
		const worker = await startWorker(fx);
		// Two settles: the first may self-check on a substantive gap, the second
		// settles on the actual product (I1 is once per process).
		settle(worker, "done");
		settle(worker, "done");
		const run = readRun(fx);
		console.log(`[VERIFY] AC-002 exit=${run.exit} status=${run.status} expected=${JSON.stringify(expected)}`);
		expect(run.exit).toBe(exit);
		expect(run.status).toBe(exit === 0 ? "done" : "needs-clarification");
		if (expected.length > 0) {
			const named = readbackMissing(fx);
			expect(named).toEqual(expected);
			expect(readOutputSection(fx.taskDir, "Questions")).toContain(`缺失段：${expected.join("、")}`);
		} else {
			expect(readTrace(fx)).not.toContain("缺失段");
		}
	});

	it("the readback line is a first-line machine contract (missing names verbatim)", () => {
		const fx = makeFixture({ type: "research", report: headings(["结论", "上下文来源"]) });
		const missing = readTerminalGaps({
			taskKey: fx.taskKey,
			agenticdocRoot: fx.trueRoot,
			summary: "",
			type: "research",
			projectRoot: fx.projectRoot,
			judgeRecovery: true,
		}).missingSections;
		expect(missing).toEqual(["证据", "残留与未验证"]);
	});
});

// ── 3. AC-015: judged product candidate set ─────────────────────────────────

describe("AC-015 judged product candidates", () => {
	function setMtime(file: string, ms: number): void {
		const when = new Date(ms);
		fs.utimesSync(file, when, when);
	}

	it("report.md wins over output.md", () => {
		const fx = makeFixture({ type: "coding", report: ALL_FIVE, output: "no headings" });
		expect(judgedProductFile(fx.taskDir)).toBe(path.join(fx.taskDir, "report.md"));
		expect(checkRecovery(agentProductText(fx.taskDir, "reply"), "coding").ok).toBe(true);
	});

	it("output.md is used when report.md is absent/empty", () => {
		const fx = makeFixture({ type: "research", report: "   \n", output: COMPLETE_RESEARCH });
		expect(judgedProductFile(fx.taskDir)).toBe(path.join(fx.taskDir, "output.md"));
		expect(checkRecovery(agentProductText(fx.taskDir, "reply"), "research").ok).toBe(true);
	});

	it("the settle summary is used when no product exists", () => {
		const fx = makeFixture({ type: "research" });
		expect(judgedProductFile(fx.taskDir)).toBeUndefined();
		expect(agentProductText(fx.taskDir, "the reply")).toBe("the reply");
	});

	it("report-<slug>.md is judged before output.md, newest mtime first", () => {
		const fx = makeFixture({ type: "research", output: "no headings" });
		const older = path.join(fx.taskDir, "report-old.md");
		const newer = path.join(fx.taskDir, "report-new.md");
		fs.writeFileSync(older, COMPLETE_RESEARCH, "utf8");
		fs.writeFileSync(newer, headings(["结论", "证据", "残留与未验证"]), "utf8");
		setMtime(older, Date.now() - 10_000);
		setMtime(newer, Date.now());
		expect(judgedProductFile(fx.taskDir)).toBe(newer);
		// The newest slug file is judged (it misses 上下文来源), not output.md.
		expect(checkRecovery(agentProductText(fx.taskDir, ""), "research").missing).toEqual(["上下文来源"]);
		// ... and the two entry points agree.
		expect(hasReportProduct(fx.taskDir)).toBe(true);
		// Newest-first ordering is mtime-driven: flip the mtimes and the other wins.
		setMtime(older, Date.now() + 10_000);
		expect(judgedProductFile(fx.taskDir)).toBe(older);
	});

	it("hasReportProduct and the judged text agree on a slug-only product (second entry point)", () => {
		const fx = makeFixture({ type: "coding" });
		fs.writeFileSync(
			path.join(fx.taskDir, "report-w2-slug.md"),
			headings(["结论", "证据", "残留与未验证", "上下文来源"]),
			"utf8",
		);
		expect(hasReportProduct(fx.taskDir)).toBe(true);
		const gaps = readTerminalGaps({
			taskKey: fx.taskKey,
			agenticdocRoot: fx.trueRoot,
			summary: "terse reply",
			type: "coding",
			projectRoot: fx.projectRoot,
			judgeRecovery: true,
		});
		expect(gaps.judged).toBe(true);
		// The slug product is judged and misses 改动清单 — before AC-015 this run
		// was never judged at all (only report.md was stat'ed).
		expect(gaps.missingSections).toEqual(["改动清单"]);
	});

	it("a slug-only coding run settles needs-clarification (not silently green)", async () => {
		const fx = makeFixture({ type: "coding" });
		fs.writeFileSync(
			path.join(fx.taskDir, "report-w2-slug.md"),
			headings(["结论", "证据", "残留与未验证", "上下文来源"]),
			"utf8",
		);
		const worker = await startWorker(fx);
		settle(worker, "done");
		settle(worker, "done");
		const run = readRun(fx);
		console.log(`[VERIFY] AC-015 slug-only exit=${run.exit} status=${run.status}`);
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);
		expect(readbackMissing(fx)).toEqual(["改动清单"]);
	});
});

// ── 4. AC-005: mechanical backfill + historical replay ──────────────────────

describe("AC-005 mechanical 上下文来源 backfill", () => {
	it("appends to the judged file before judgement, with card + product facts", () => {
		const fx = makeFixture({
			type: "research",
			report: headings(["结论", "证据", "残留与未验证"]),
			output: "no headings",
			trace: "[TOOL] 2026-10-14T00:00:00Z read src/a.ts\n[TOOL] 2026-10-14T00:00:01Z grep src/b.ts\n",
			cardPath: "tasks/T-05-contract-judgment.md",
			cardSha: "a".repeat(64),
		});
		const before = fs.readFileSync(path.join(fx.taskDir, "report.md"), "utf8");
		const result = appendMechanicalContextSources({
			taskKey: fx.taskKey,
			agenticdocRoot: fx.trueRoot,
			summary: "reply",
			type: "research",
		});
		console.log(`[VERIFY] AC-005 backfill=${JSON.stringify(result)}`);
		expect(result.appended).toBe(true);
		expect(result.ok).toBe(true);
		expect(result.target).toBe(path.join(fx.taskDir, "report.md"));
		const after = fs.readFileSync(path.join(fx.taskDir, "report.md"), "utf8");
		// Pure append: the pre-existing bytes are untouched.
		expect(after.startsWith(before)).toBe(true);
		expect(after).toContain(MECHANICAL_CONTEXT_MARKER);
		expect(after).toContain("## 上下文来源");
		expect(after).toContain("tasks/T-05-contract-judgment.md");
		expect(after).toContain("report.md");
		expect(after).toContain("src/a.ts");
		// The "only append output.md" failure mode is excluded: output.md is untouched.
		expect(fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8")).not.toContain(MECHANICAL_CONTEXT_MARKER);
		// The judgement now reads the backfilled file (invariant I1).
		expect(checkRecovery(agentProductText(fx.taskDir, ""), "research").ok).toBe(true);
	});

	it("is idempotent (marker present => no second append)", () => {
		const fx = makeFixture({ type: "research", report: headings(["结论", "证据", "残留与未验证"]) });
		const first = appendMechanicalContextSources({
			taskKey: fx.taskKey,
			agenticdocRoot: fx.trueRoot,
			summary: "",
			type: "research",
		});
		const afterFirst = fs.readFileSync(path.join(fx.taskDir, "report.md"), "utf8");
		const second = appendMechanicalContextSources({
			taskKey: fx.taskKey,
			agenticdocRoot: fx.trueRoot,
			summary: "",
			type: "research",
		});
		const afterSecond = fs.readFileSync(path.join(fx.taskDir, "report.md"), "utf8");
		expect(first.appended).toBe(true);
		expect(second.appended).toBe(false);
		expect(afterSecond).toBe(afterFirst);
		expect(afterSecond.split(MECHANICAL_CONTEXT_MARKER).length - 1).toBe(1);
	});

	it("fail-closed: no product file on disk", () => {
		const fx = makeFixture({ type: "research" });
		const result = appendMechanicalContextSources({
			taskKey: fx.taskKey,
			agenticdocRoot: fx.trueRoot,
			summary: "a reply without headings",
			type: "research",
		});
		console.log(`[VERIFY] AC-005 fail-closed no-product-file=${JSON.stringify(result)}`);
		expect(result.appended).toBe(false);
		expect(result.ok).toBe(false);
		expect(result.reason).toBe("no-product-file");
		expect(result.missing).toEqual([...BASE]);
		expect(fs.existsSync(path.join(fx.taskDir, "report.md"))).toBe(false);
	});

	it("fail-closed: marker present without the section (no double append)", () => {
		const fx = makeFixture({
			type: "research",
			report: `${headings(["结论", "证据", "残留与未验证"])}\n${MECHANICAL_CONTEXT_MARKER}\n`,
		});
		const before = fs.readFileSync(path.join(fx.taskDir, "report.md"), "utf8");
		const result = appendMechanicalContextSources({
			taskKey: fx.taskKey,
			agenticdocRoot: fx.trueRoot,
			summary: "",
			type: "research",
		});
		expect(result.appended).toBe(false);
		expect(result.ok).toBe(false);
		expect(result.reason).toBe("already-marked");
		expect(fs.readFileSync(path.join(fx.taskDir, "report.md"), "utf8")).toBe(before);
	});

	it("fail-closed: the candidate file is not writable", () => {
		const fx = makeFixture({ type: "research", report: headings(["结论", "证据", "残留与未验证"]) });
		const file = path.join(fx.taskDir, "report.md");
		fs.chmodSync(file, 0o444);
		try {
			const result = appendMechanicalContextSources({
				taskKey: fx.taskKey,
				agenticdocRoot: fx.trueRoot,
				summary: "",
				type: "research",
			});
			console.log(`[VERIFY] AC-005 fail-closed not-writable=${JSON.stringify(result)}`);
			expect(result.appended).toBe(false);
			expect(result.ok).toBe(false);
			expect(result.reason).toBe("not-writable");
		} finally {
			fs.chmodSync(file, 0o666);
		}
	});

	it("never fills a non-mechanical section", () => {
		const fx = makeFixture({ type: "coding", report: headings(["结论", "证据", "残留与未验证", "上下文来源"]) });
		const result = appendMechanicalContextSources({
			taskKey: fx.taskKey,
			agenticdocRoot: fx.trueRoot,
			summary: "",
			type: "coding",
		});
		// 改动清单 is substantive: the backfill must not invent it.
		expect(result.appended).toBe(false);
		expect(result.ok).toBe(false);
		expect(result.missing).toEqual(["改动清单"]);
		expect(fs.readFileSync(path.join(fx.taskDir, "report.md"), "utf8")).not.toContain("## 改动清单");
	});
});

describe("AC-005 historical mechanical-only replay (exit=2 -> exit=0)", () => {
	// The task lists 8 `class=mechanical-only` cases; under the H2-only predicate
	// only five still have EXACTLY one gap, and only the writeless (research)
	// ones actually go through the recovery judgement — a `coding` role with no
	// report product keeps the AC-006/C5 write-role exemption, so its `exit=0`
	// would be vacuous (the contract is never applied). These three research
	// products are the genuine `exit=2 -> exit=0` flips, read from the on-disk
	// text the PM never patched.
	const REPLAY = [
		"mw-dynamic-concurrency/workers/mdc-rq1-dispatch-chain",
		"mw-guard-form-hardening/workers/mwgf-drq3-role-key-design",
		"mw-vision-role/workers/mvr-rq5-awareness-surface",
	];

	/** Copy the real (never PM-patched) task dir into a disposable fixture. */
	function makeReplayFixture(rel: string): Fixture & { judged: string; preText: string; type: string } {
		const source = path.join(REPO_ROOT, ".agenticdoc", rel);
		expect(fs.existsSync(path.join(source, "task.md")), `${rel} task.md`).toBe(true);
		const projectRoot = mkdtemp("mwoc-w2-replay-");
		const trueRoot = path.join(projectRoot, ".agenticdoc");
		const taskDir = path.join(trueRoot, ...rel.split("/"));
		fs.mkdirSync(taskDir, { recursive: true });
		for (const name of ["task.md", "trace.log", "report.md", "output.md"]) {
			const from = path.join(source, name);
			if (fs.existsSync(from)) fs.copyFileSync(from, path.join(taskDir, name));
		}
		const type = readTaskType(fs.readFileSync(path.join(taskDir, "task.md"), "utf8")).type ?? "";
		const judged = judgedProductFile(taskDir);
		expect(judged, `${rel} judged product`).toBeDefined();
		const preText = fs.readFileSync(judged as string, "utf8");
		const key = rel.split("/")[0] ?? "k";
		const task = rel.split("/").at(-1) ?? "t";
		return {
			projectRoot,
			trueRoot,
			keyDir: path.join(trueRoot, key),
			taskDir,
			taskKey: `${key}/workers/${task}`,
			judged: judged as string,
			preText,
			type,
		};
	}

	it.each(REPLAY)("%s: missing only 上下文来源, then exit=2 -> exit=0", async (rel) => {
		const fx = makeReplayFixture(rel);
		const pre = checkRecovery(fx.preText, fx.type);
		console.log(`[VERIFY] AC-005 replay pre task=${rel} type=${fx.type} missing=${JSON.stringify(pre.missing)}`);
		// The pre-state is the `exit=2` expectation: the judgement read would miss
		// exactly the mechanical section (design §5.2 step 2).
		expect(pre.missing).toEqual(["上下文来源"]);
		// A writeless role is always judged, so the flip is a real verdict change.
		expect(["research", "review"]).toContain(fx.type);

		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		const after = fs.readFileSync(fx.judged, "utf8");
		console.log(`[VERIFY] AC-005 replay post task=${rel} exit=${run.exit} status=${run.status}`);
		expect(run.exit).toBe(0);
		expect(run.status).toBe("done");
		// Judgement and product agree (I1): the judged file now carries the
		// heading, its earlier bytes are a pure prefix, and the marker is present.
		expect(after.startsWith(fx.preText)).toBe(true);
		expect(after).toContain("## 上下文来源");
		expect(after).toContain(MECHANICAL_CONTEXT_MARKER);
		expect(checkRecovery(after, fx.type).ok).toBe(true);
		expect(fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8")).not.toContain("## Recovery Gaps");
		expect(readTrace(fx)).toContain("recovery-backfill section=上下文来源");
	});
});

// ── 5. AC-004 + I1: structured pre-settle gap and one self-check turn ────────

describe("AC-004 structured gap and I1 self-check", () => {
	it("first settle misses one section, the worker fixes it, the second settle is green", async () => {
		const fx = makeFixture({ type: "research", report: headings(["结论", "残留与未验证", "上下文来源"]) });
		const worker = await startWorker(fx);

		settle(worker, "done");
		console.log(`[VERIFY] AC-004 selfcheck=${JSON.stringify(worker.sent)}`);
		expect(worker.sent).toHaveLength(1);
		expect(worker.sent[0]?.deliverAs).toBe("followUp");
		expect(worker.sent[0]?.text).toContain("证据");
		expect(readRun(fx).status).toBe("running");
		const trace = readTrace(fx);
		expect(trace).toMatch(/recovery-gap missing=证据 selfcheck=pending/);

		// The worker fills the reported gap, then settles again.
		fs.appendFileSync(path.join(fx.taskDir, "report.md"), "\n## 证据\n\n[VERIFY] probe -> ok\n", "utf8");
		settle(worker, "done");

		const run = readRun(fx);
		console.log(`[VERIFY] AC-004 resolved exit=${run.exit} status=${run.status}`);
		expect(run.exit).toBe(0);
		expect(run.status).toBe("done");
		expect(worker.sent).toHaveLength(1);
	});

	it("the self-check turn is sent at most once per process", async () => {
		const fx = makeFixture({ type: "research", report: headings(["结论", "上下文来源"]) });
		const worker = await startWorker(fx);
		settle(worker, "done");
		expect(worker.sent).toHaveLength(1);
		expect(readRun(fx).status).toBe("running");
		settle(worker, "done");
		expect(worker.sent).toHaveLength(1);
		console.log(`[VERIFY] I1 sent=${worker.sent.length} exit=${readRun(fx).exit}`);
		expect(readRun(fx).exit).toBe(2);
		// A later settle of the already-terminal run is a no-op.
		settle(worker, "done");
		expect(worker.sent).toHaveLength(1);
	});

	it("a mechanical-only gap does not burn an agent turn", async () => {
		const fx = makeFixture({ type: "research", report: headings(["结论", "证据", "残留与未验证"]) });
		const worker = await startWorker(fx);
		settle(worker, "done");
		console.log(`[VERIFY] AC-004 mechanical-only sent=${worker.sent.length} exit=${readRun(fx).exit}`);
		expect(worker.sent).toHaveLength(0);
		expect(readRun(fx).exit).toBe(0);
		expect(readTrace(fx)).toMatch(/recovery-gap missing=上下文来源 selfcheck=pending/);
	});
});

// ── 6. AC-003 (TS half): card-seed contract checklist ───────────────────────

describe("AC-003 TS card-seed contract checklist", () => {
	const SECTIONS: CardSections = {
		context: "ctx",
		requirements: "req",
		deliverables: "report.md",
		extras: [],
	};

	it("research/review card renders carry the role checklist with copyable headings", () => {
		for (const [type, extra] of [
			["research", "上下文来源"],
			["review", "未覆盖面声明"],
		] as const) {
			const seed = renderCardSeedSections({ ...SECTIONS, type });
			console.log(`[VERIFY] AC-003 seed type=${type} contains=${seed.includes(RECOVERY_CONTRACT_HEADING)}`);
			expect(seed).toContain(RECOVERY_CONTRACT_HEADING);
			expect(seed).toContain(`- \`## ${extra}\``);
			for (const name of recoverySectionsFor(type)) expect(seed).toContain(`- \`## ${name}\``);
		}
		expect(recoveryContractSection("coding")).toContain("改动清单");
	});

	it("a card-less / type-less render is byte-stable (no checklist)", () => {
		const seed = renderCardSeedSections(SECTIONS);
		expect(seed).not.toContain(RECOVERY_CONTRACT_HEADING);
		expect(seed).toBe(
			[
				CARD_SEED_MARKER,
				"## 上下文",
				"",
				"ctx",
				"",
				"## 要求",
				"",
				"req",
				"",
				"## 交付格式",
				"",
				"report.md",
				"",
				CARD_SEED_DISCLAIMER,
				CARD_SEED_MARKER_END,
			].join("\n"),
		);
	});

	it("injection is idempotent and never doubles against a declared section", () => {
		const sections: CardSections = { ...SECTIONS, type: "review" };
		const once = applyCardSeedSections("body", sections);
		const twice = applyCardSeedSections(once, sections);
		expect(twice).toBe(once);
		expect(once.split(RECOVERY_CONTRACT_HEADING).length - 1).toBe(1);
		// A card that already declares the heading stays a fixed point too.
		const declared: CardSections = {
			...sections,
			extras: [{ title: "交付段契约（本角色）", body: "- `## 结论`" }],
		};
		const rendered = renderCardSeedSections(declared);
		expect(rendered.split("## 交付段契约（本角色）").length - 1).toBe(1);
	});
});

// ── 7. AC-014: corrected attribution, two places consistent ─────────────────

describe("AC-014 corrected 99.4%/87.2% attribution", () => {
	const source = fs.readFileSync(
		path.join(REPO_ROOT, "packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts"),
		"utf8",
	);
	const reflect = fs.readFileSync(path.join(REPO_ROOT, ".agenticdoc/_framework-reflect.md"), "utf8");

	it("output-sections.ts cites the OTHER contract's sources with file:line, not as its own proof", () => {
		// AC-014: the numbers may still be NAMED (with the corrected attribution),
		// but they must not be presented as this contract's evidence.
		expect(source).not.toContain("historical corpus is the");
		expect(source).not.toContain("Strict heading matching would over-block");
		expect(source).toContain("spec-dispatch-input-format-20261012.md:142");
		expect(source).toContain("spec-card-format-corpus-20261012.md:281");
		expect(source).toContain("dispatch-envelope/card compliance");
		expect(source).toContain("cited as this contract's evidence");
		console.log("[VERIFY] AC-014 output-sections misattribution_removed=true real_sources_cited=true");
	});

	it("FW-001 修法 5 carries the same correction (two places consistent)", () => {
		expect(reflect).toContain("spec-dispatch-input-format-20261012.md:142");
		expect(reflect).toContain("spec-card-format-corpus-20261012.md:281");
		expect(reflect).toContain("33.5%");
		expect(reflect).toContain("8.1%");
		console.log("[VERIFY] AC-014 reflect_correction_present=true equal_attribution=true");
	});
});
