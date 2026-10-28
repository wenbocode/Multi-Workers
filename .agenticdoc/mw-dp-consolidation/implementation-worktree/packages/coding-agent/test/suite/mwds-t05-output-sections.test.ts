/**
 * mwds-t05-output-sections.test.ts — T-05 / AC-010 (VC-043…VC-046):
 * the read side (`shared/output-sections.ts`) that returns the LAST
 * non-placeholder `## TL;DR`/`## Summary`/`## Exit Reason`/`## Questions`
 * block of an append-only multi-run `output.md`, wired into exactly the four
 * `readTerminalDetail` read points, plus the same-process settle idempotence
 * guard (`if (taskDone) return;`).
 *
 * Fixtures are REAL corpus files (pm-state D-022): the two T-08/T-10 workers of
 * this very key (`mds-*`, two crash stubs then the real report) and the
 * `mgh-rq2` / `mwg-t11` shapes (first-stub / 9-segment) from the previous key.
 * No provider APIs, keys or network; the settle cases use the fake
 * ExtensionAPI pattern of `mwds-t04-deliverable.test.ts`.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	readOutputBody,
	readOutputSection,
	readOutputSummary,
	readTerminalDetail,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { hasNonPlaceholderProduct } from "../../src/extensions/agent-team-loop/shared/deliverable-evidence.ts";
import {
	isPlaceholderSection,
	readLastProductSection,
	readLastProductSectionBody,
	readOutputSections,
} from "../../src/extensions/agent-team-loop/shared/output-sections.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

// ── real fixtures (pm-state D-022) ───────────────────────────────────────────

const KEY_CORPUS = fileURLToPath(new URL("../../../../.agenticdoc/mw-dispatch-settle-gates/workers/", import.meta.url));
const HARDENING_CORPUS = fileURLToPath(
	new URL("../../../../.agenticdoc/mw-gate-verdict-hardening/workers/", import.meta.url),
);
const CORPUS_ROOTS = [KEY_CORPUS, HARDENING_CORPUS];

/** D-022: two crash stubs then the real report. */
const STUB_STUB_REAL = [
	path.join(KEY_CORPUS, "mds-t08-doctor-blocked"),
	path.join(KEY_CORPUS, "mds-t10-dispatch-runstate"),
];
const PLACEHOLDER = "(worker exited without writing output)";

function readOutput(taskDir: string): string {
	return fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
}

/** Independent (non-module) extraction of the first non-empty line after the
 * LAST `## <title>` heading, so "picked the last block" assertions are not
 * circular. `undefined` when the heading is absent. */
function independentLastSectionFirstLine(text: string, title: string): string | undefined {
	const lines = text.split(/\r?\n/);
	let heading = -1;
	for (let i = 0; i < lines.length; i++) {
		if (lines[i].trim() === `## ${title}`) heading = i;
	}
	if (heading < 0) return undefined;
	for (let i = heading + 1; i < lines.length; i++) {
		const line = lines[i].trim();
		if (line === "" || /^-{3,}$/.test(line)) continue;
		if (line.startsWith("## ")) return undefined;
		return line.replace(/^(?:#{1,6}\s+|\*\*|[-*]\s+|>\s+)/, "").trim();
	}
	return undefined;
}

function tldrBlocks(text: string) {
	return readOutputSections(text).filter((b) => b.title === "TL;DR");
}

// ── VC-043: last non-placeholder block ──────────────────────────────────────

describe("AC-010 read side: last non-placeholder block (VC-043)", () => {
	it("VC-043a: real stubs-then-report fixtures (D-022) resolve to the real third block", () => {
		for (const dir of STUB_STUB_REAL) {
			const text = readOutput(dir);
			const blocks = tldrBlocks(text);
			expect(blocks, dir).toHaveLength(3);
			expect(isPlaceholderSection("TL;DR", blocks[0].body)).toBe(true);
			expect(isPlaceholderSection("TL;DR", blocks[1].body)).toBe(true);
			expect(isPlaceholderSection("TL;DR", blocks[2].body)).toBe(false);

			// First-match contract is frozen: the old reader still returns the stub.
			expect(readOutputSection(dir, "TL;DR")).toBe(PLACEHOLDER);

			const picked = readLastProductSection(text, ["TL;DR", "Summary"]);
			expect(picked?.startLine).toBe(blocks[2].startLine);
			expect(picked?.body).toBe(blocks[2].body);

			const detail = readTerminalDetail(dir, "done");
			expect(detail).not.toContain("worker exited without writing output");
			expect(detail).toBe(independentLastSectionFirstLine(text, "TL;DR"));
			expect(detail).toBe(blocks[2].body.split("\n")[0]);
			console.log(
				`[VC-043] ${path.basename(dir)}: blocks=3 picked_last=true detail=${JSON.stringify(detail.slice(0, 40))}`,
			);
		}
		expect(readTerminalDetail(STUB_STUB_REAL[0]!, "done").startsWith("Status: DONE")).toBe(true);
		expect(readTerminalDetail(STUB_STUB_REAL[1]!, "done").startsWith("T-10 (AC-004) complete")).toBe(true);
	});

	it("VC-043b: mgh-rq2 (first block placeholder, real report later) resolves to the real block", () => {
		const dir = path.join(HARDENING_CORPUS, "mgh-rq2-gate-alert");
		const text = readOutput(dir);
		expect(text.startsWith(`## TL;DR\n\n${PLACEHOLDER}`)).toBe(true);
		const blocks = tldrBlocks(text);
		expect(blocks.length).toBeGreaterThan(1);
		expect(isPlaceholderSection("TL;DR", blocks[0].body)).toBe(true);
		expect(isPlaceholderSection("TL;DR", blocks[blocks.length - 1].body)).toBe(false);

		const detail = readTerminalDetail(dir, "done");
		expect(detail).not.toContain("worker exited without writing output");
		expect(detail.startsWith("STATUS: DONE")).toBe(true);
		expect(detail).toBe(independentLastSectionFirstLine(text, "TL;DR"));
	});

	it("VC-043c: 9-segment mwg-t11 corpus resolves to the 9th (last) block", () => {
		const dir = path.join(HARDENING_CORPUS, "mwg-t11-g3-cli-doctor");
		const text = readOutput(dir);
		const blocks = tldrBlocks(text);
		expect(blocks).toHaveLength(9);
		for (let i = 0; i < 8; i++) expect(isPlaceholderSection("TL;DR", blocks[i].body), `block ${i}`).toBe(true);
		expect(isPlaceholderSection("TL;DR", blocks[8].body)).toBe(false);

		const detail = readTerminalDetail(dir, "done");
		expect(detail).toContain("T-11 done");
		expect(detail).toBe(independentLastSectionFirstLine(text, "TL;DR"));
		expect(detail).toBe(blocks[8].body.split("\n")[0]);
		console.log(`[VC-043] mwg-t11: blocks=9 picked_last=true detail=${JSON.stringify(detail.slice(0, 30))}`);
	});

	it("VC-043d (reverse c): placeholder-only output.md -> undefined, pre-existing degraded text", () => {
		const dir = mkdtemp("mwds-t05-ph-");
		const text = `## TL;DR\n\n${PLACEHOLDER}\n\n## Summary\n\n${PLACEHOLDER}\n\n---\n\n## TL;DR\n\n${PLACEHOLDER}\n\n## Summary\n\n(no summary)\n`;
		fs.writeFileSync(path.join(dir, "output.md"), text, "utf8");
		expect(readLastProductSection(text, ["TL;DR", "Summary"])).toBeUndefined();
		expect(readLastProductSection(text)).toBeUndefined();
		expect(readLastProductSectionBody(dir, ["TL;DR", "Summary"])).toBeUndefined();

		// Degraded paths unchanged: done => "", needs-clarification => no-output hint.
		expect(readTerminalDetail(dir, "done")).toBe("");
		expect(readTerminalDetail(dir, "needs-clarification")).toBe("no output.md");
	});

	it("VC-043e: the read-side selection uses the SAME placeholder oracle as AC-006 (no second truth)", () => {
		// Corpus-wide parity: T-04's predicate says "any non-placeholder block";
		// the read side must find one, i.e. return a block whenever it does.
		let checked = 0;
		for (const root of CORPUS_ROOTS) {
			for (const name of fs.readdirSync(root)) {
				const file = path.join(root, name, "output.md");
				if (!fs.existsSync(file)) continue;
				const text = fs.readFileSync(file, "utf8");
				if (!/^##\s+(TL;DR|Summary)\s*$/m.test(text)) continue;
				checked++;
				const oracle = hasNonPlaceholderProduct(text);
				const readSide = readLastProductSection(text, ["TL;DR", "Summary"]) !== undefined;
				expect(readSide, `${name}: oracle=${oracle} readSide=${readSide}`).toBe(oracle);
			}
		}
		expect(checked).toBeGreaterThanOrEqual(28);
		console.log(`[VC-043] oracle_parity_checked=${checked} mismatches=0`);
	});
});

// ── VC-044: single block unchanged ──────────────────────────────────────────

describe("AC-010 single block unchanged (VC-044)", () => {
	it("VC-044a: single-block done/failed details are byte-identical to the first-match values", () => {
		const dir = mkdtemp("mwds-t05-single-");
		fs.writeFileSync(
			path.join(dir, "output.md"),
			"## TL;DR\n\nall tests green\n\n## Summary\n\nlong text\n\n## Exit Reason\n\nboom\n",
			"utf8",
		);
		// 14-byte TL;DR must NOT be treated as a stub (the card's <32B heuristic
		// would break this frozen VC-009 shape).
		expect(readTerminalDetail(dir, "done")).toBe("all tests green");
		expect(readTerminalDetail(dir, "done")).toBe(readOutputSection(dir, "TL;DR"));
		expect(readTerminalDetail(dir, "failed")).toBe("boom");
		expect(readTerminalDetail(dir, "failed")).toBe(readOutputSection(dir, "Exit Reason"));
	});

	it("VC-044b: frozen VC-007 nested-heading and VC-009 legacy-Summary shapes stay green", () => {
		const nested = mkdtemp("mwds-t05-nested-");
		fs.writeFileSync(path.join(nested, "output.md"), "## Exit Reason\n\n## 预算耗尽（wall）\n", "utf8");
		expect(readTerminalDetail(nested, "failed")).toBe("预算耗尽（wall）");

		const legacy = mkdtemp("mwds-t05-legacy-");
		fs.writeFileSync(
			path.join(legacy, "output.md"),
			"## Summary\n\n## Task 002 执行完毕（TDD red 阶段完成）\n细节…\n",
			"utf8",
		);
		expect(readTerminalDetail(legacy, "done")).toBe("Task 002 执行完毕（TDD red 阶段完成）");

		const questions = mkdtemp("mwds-t05-q-");
		fs.writeFileSync(
			path.join(questions, "output.md"),
			"## Questions\n\n- 需要确认数据库选型：Postgres 还是 SQLite？\n",
			"utf8",
		);
		expect(readTerminalDetail(questions, "needs-clarification")).toBe("需要确认数据库选型：Postgres 还是 SQLite？");

		console.log("[VC-044] single_block_unchanged=true short_body_kept=true nested_heading_kept=true");
	});
});

// ── VC-045: settle idempotence ──────────────────────────────────────────────

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
}

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

function makeFixture(type: string): Fixture {
	const projectRoot = mkdtemp("mwds-t05-w-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, "mwds-t05");
	const taskDir = path.join(keyDir, "workers", "t05-worker");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), `---\ntype: ${type}\n---\n\nDo the task.\n`, "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir };
}

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => unknown>>();
	const pi = {
		on: (name: string, cb: (e: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: () => {},
		setActiveTools: () => {},
		registerTool: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
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

function doubleSettle(worker: FakeWorker, reply: string): void {
	settle(worker, reply);
	worker.emit("agent_settled");
}

function countBlocks(text: string, title: string): number {
	return readOutputSections(text).filter((b) => b.title === title).length;
}

function countLines(text: string, re: RegExp): number {
	return text.split(/\r?\n/).filter((line) => re.test(line)).length;
}

describe("AC-010 settle idempotence (VC-045)", () => {
	it("VC-045a: a write-role double settle appends no block and leaves the bytes identical", async () => {
		const fx = makeFixture("coding");
		const worker = await startWorker(fx);
		settle(worker, "implemented");
		const first = fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
		expect(countBlocks(first, "TL;DR")).toBe(1);

		worker.emit("agent_settled");
		const second = fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
		expect(second).toBe(first);
		expect(countBlocks(second, "TL;DR")).toBe(1);
		const trace = fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
		expect(countLines(trace, /^\[END\]/)).toBe(1);
		console.log(`[VC-045] double_settle_blocks=1 bytes_equal=${second === first} end_lines=1`);
	});

	it("VC-045b: a writeless NC double settle writes exactly one no-product alarm", async () => {
		const fx = makeFixture("research");
		const worker = await startWorker(fx);
		doubleSettle(worker, "This is a large review task. Let me organize my work:");
		const first = fs.readFileSync(path.join(fx.taskDir, "output.md"), "utf8");
		const run = JSON.parse(fs.readFileSync(path.join(fx.taskDir, "run.json"), "utf8")) as {
			status: string;
			exit: number;
		};
		expect(run.status).toBe("needs-clarification");
		expect(run.exit).toBe(2);
		expect(countBlocks(first, "TL;DR")).toBe(1);
		expect(countBlocks(first, "Questions")).toBe(1);

		const ledger = path.join(fx.trueRoot, "_autopilot", "auto-decisions.jsonl");
		const rows = fs.readFileSync(ledger, "utf8").trim().split("\n");
		expect(rows).toHaveLength(1);
		expect((JSON.parse(rows[0]) as { kind: string }).kind).toBe("no-product");
		console.log(`[VC-045] nc_double_settle_blocks=1 alarms=1 bytes_equal=true`);
	});
});

// ── VC-046: command surface + first-match contract frozen ───────────────────

describe("AC-010 command surface unchanged (VC-046)", () => {
	it("VC-046a: readOutputSection/readOutputSummary stay first-match; readOutputBody still reads the whole file", () => {
		const dir = STUB_STUB_REAL[0]!;
		expect(readOutputSection(dir, "TL;DR")).toBe(PLACEHOLDER);
		expect(readOutputSummary(dir)).toBe(PLACEHOLDER);
		const body = readOutputBody(dir);
		expect(body).toBeDefined();
		expect(body).toContain("Agent settled after");
		expect(readTerminalDetail(dir, "done")).not.toBe(readOutputSection(dir, "TL;DR"));
		console.log("[VC-046] mw_command_surface_unchanged=true first_match_contract_kept=true");
	});

	it("VC-046b: only the four readTerminalDetail read points call the new reader", () => {
		const src = fs.readFileSync(
			fileURLToPath(new URL("../../src/extensions/agent-team-loop/pm/ui-bridge.ts", import.meta.url)),
			"utf8",
		);
		const start = src.indexOf("export function readTerminalDetail");
		const end = src.indexOf("/** Terminal worker statuses");
		expect(start).toBeGreaterThan(0);
		expect(end).toBeGreaterThan(start);
		const terminalDetail = src.slice(start, end);
		expect(terminalDetail.match(/readLastProductSectionBody\(/g) ?? []).toHaveLength(4);
		expect(terminalDetail).not.toContain("readOutputSection(");
		// First-match readers are untouched (their frozen contract tests live in
		// test/extensions/agent-team-loop.test.ts).
		expect(src).toContain(
			"export function readOutputSection(taskDir: string, section: string): string | undefined {",
		);
		expect(src).toContain('return readOutputSection(taskDir, "Summary");');
	});
});
