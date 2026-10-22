/**
 * claim-bypass.test.ts — L3 anti-bypass face of `claim-driven-review` (AC-008,
 * T-04b). The settlement wiring of `worker/worker-mode.ts` is pinned here:
 *
 *   1. `TaskMeta.claims` — `parseTaskMd` re-parses the `<!-- mw-claims: v1 -->`
 *      block T-02 injects into task.md (D-002: the card file is never re-read);
 *      an absent block leaves the field undefined (zero-branch legacy path).
 *   2. The five settlement-side AC-008 criteria, each with ONE negative case
 *      ("a compliant product that did not actually review") — ③ is split into
 *      its two frozen upper bounds, which is why six negative cases cover
 *      five criteria:
 *        ① B-1/B-4 self-witness  -> `claim:<id>:self-evidence`
 *        ② B-2  unverified share -> `claims:unverified-ratio:<u>/<n>><limit>%`
 *        ③ B-6  Σ取数 cap        -> `claims:fetches:<sum>><cap>`
 *        ③ B-6  Σ取数 vs trace   -> `claims:fetches:<sum>>trace:<n>`
 *        ④ B-10 struct / two-way -> `claim:<id>:struct-held`, `:missing-row`
 *        ⑥ B-7  re-used verdict  -> `claim:<id>:carried-from`
 *      The remaining AC-008 clause ⑤ (`[ENVELOPE_FALLBACK]` extras count as
 *      missing) is a DISPATCH-side criterion owned by T-02 (`pm/ui-bridge.ts`,
 *      `dispatch-card.ts`), not a settlement criterion — it is not asserted
 *      here and this file claims nothing about it.
 *   3. The independent `[CLAIMS] <iso> claims=<n> closed=<n> partial=<n>
 *      unverified=<n> fetches=<n>` trace row (design D-004: never folded into
 *      `[END]`), one positive + one negative format case, and the claims-free
 *      book writing no row at all.
 *   4. The `run.json` `claims` subobject (`{total, closed, partial, unverified,
 *      fetches, tokens}`) written by this layer and read back: five counters
 *      plus `tokens: null` when the run cannot attribute usage; the key is
 *      ABSENT on a claims-free run (T-05 reads absence as "not measured").
 *   5. The pre-settle self-check: claim gaps and recovery gaps render
 *      separately but share ONE trigger and the existing `selfCheckSent`.
 *
 * Everything is local: temp project/task dirs, the faux `ExtensionAPI` pattern
 * from `mwoc-w2-contract-judgment.test.ts` (no provider, no network, no keys).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { readOutputSection, readTerminalDetail } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { Claim } from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";
import { parseVerdictTable } from "../../src/extensions/agent-team-loop/worker/output-sections.ts";
import {
	CLAIM_UNVERIFIED_MAX_DEFAULT,
	CLAIM_UNVERIFIED_MAX_REVIEW,
	claimCounts,
	claimGapIds,
	claimSettlementGaps,
	formatClaimsTraceLine,
	parseTaskMd,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

// ── fixtures ─────────────────────────────────────────────────────────────────

const tempDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

function numberedLines(count: number): string {
	const lines: string[] = [];
	for (let i = 1; i <= count; i++) lines.push(`line ${i}`);
	return `${lines.join("\n")}\n`;
}

let savedCwd = "";

beforeEach(() => {
	savedCwd = process.cwd();
});

afterEach(() => {
	process.chdir(savedCwd);
	delete process.env.PI_WORKER_TASK;
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** `[CLAIMS]` line grammar, verbatim mirror of `usage.py::_CLAIMS_LINE_RE`
 * (T-05). `undefined` captures would mean the field order/name drifted. */
const CLAIMS_LINE_RE =
	/^\s*\[CLAIMS\]\s+(?:\S+\s+)?claims=(\d+)\s+closed=(\d+)\s+partial=(\d+)\s+unverified=(\d+)\s+fetches=(\d+)(?=\s|$)/;

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
	taskKey: string;
}

/** A claims block in the exact shape T-02 copies into task.md. */
function claimsBlock(rows: string[]): string {
	return [
		"<!-- mw-claims: v1 -->",
		"| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |",
		"| --- | --- | --- | --- | --- | --- | --- |",
		...rows,
		"<!-- /mw-claims -->",
		"",
	].join("\n");
}

/** One card claim row. Statement/falsifier/judgement differ enough that T-01's
 * tautology judge stays quiet, so a fixture only trips the criterion it targets. */
function claimRow(spec: { id: string; type?: string; budget?: number; locator?: string; judgement?: string }): string {
	const type = spec.type ?? "grep";
	const judgement = spec.judgement ?? "grep: readFileSync => count=0";
	return `| ${spec.id} | ${type} | \`worker-mode.ts\` 不再读取旧决策点路径 | 出现 readFileSync 命中该路径 | ${
		spec.locator ?? "src/a.ts"
	} | ${judgement} | ${spec.budget ?? 1} |`;
}

/** One `## 断言裁决` row (all seven columns). */
function verdictRow(spec: {
	id: string;
	type?: string;
	verdict: string;
	finding: string;
	evidence?: string;
	fetches?: string;
	reason?: string;
}): string {
	return `| ${spec.id} | ${spec.type ?? "grep"} | ${spec.verdict} | ${spec.finding} | ${
		spec.evidence ?? "-"
	} | ${spec.fetches ?? "0"} | ${spec.reason ?? "-"} |`;
}

/** `## 断言裁决` table appended to a product. */
function verdictTable(rows: string[]): string {
	return [
		"## 断言裁决",
		"",
		"| claim | 类型 | 裁决 | 判定 | 证据 | 取数 | 原因 |",
		"| --- | --- | --- | --- | --- | --- | --- |",
		...rows,
		"",
	].join("\n");
}

/** Product that satisfies the research-role recovery contract (base four). */
function researchProduct(table?: string[]): string {
	const body = [
		"## 结论",
		"",
		"claims settled.",
		"",
		"## 证据",
		"",
		"[VERIFY] probe -> ok",
		"",
		"## 残留与未验证",
		"",
		"none.",
		"",
		"## 上下文来源",
		"",
		"src/a.ts:3",
		"",
	].join("\n");
	return table === undefined ? body : `${body}${verdictTable(table)}`;
}

/** Product that satisfies the review-role contract (base four + 未覆盖面声明). */
function reviewProduct(table?: string[]): string {
	const body = `${researchProduct()}\n## 未覆盖面声明\n\nnone.\n`;
	return table === undefined ? body : `${body}${verdictTable(table)}`;
}

function makeFixture(opts: {
	type?: string;
	claims?: string;
	product?: string;
	/** Project-root-relative fixture files (numbered 20-line bodies). */
	projectFiles?: string[];
	/** Project-root-relative files whose mtime is forced older than task.md. */
	staleFiles?: string[];
}): Fixture {
	const projectRoot = mkdtemp("mw-claim-bypass-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const key = "cdr";
	const task = "t04b";
	const keyDir = path.join(trueRoot, key);
	const taskDir = path.join(keyDir, "workers", task);
	fs.mkdirSync(taskDir, { recursive: true });

	// task.md first: everything the fixture writes AFTER it is "produced by this
	// run" (fresh), which is what the ⑥ carried-from clock compares against.
	const head = `type: ${opts.type ?? "research"}\n`;
	const taskMd = `${head}\nwork\n\n${opts.claims ?? ""}`;
	fs.writeFileSync(path.join(taskDir, "task.md"), taskMd, "utf8");

	// Project-root fixtures: the evidence grammar resolves refs against cwd
	// (the launcher starts workers with cwd = project root).
	const files = opts.projectFiles ?? ["src/a.ts"];
	for (const rel of files) {
		const abs = path.join(projectRoot, rel);
		fs.mkdirSync(path.dirname(abs), { recursive: true });
		fs.writeFileSync(abs, numberedLines(20), "utf8");
	}

	if (opts.product !== undefined) fs.writeFileSync(path.join(taskDir, "report.md"), opts.product, "utf8");

	// A carried-from fixture needs citations that predate the run's task book.
	const taskMtimeMs = fs.statSync(path.join(taskDir, "task.md")).mtimeMs;
	for (const rel of opts.staleFiles ?? []) {
		const abs = path.join(projectRoot, rel);
		const when = new Date(taskMtimeMs - 60_000);
		fs.utimesSync(abs, when, when);
	}

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

/** Two settles: the first may spend the one self-check turn, the second lands
 * the terminal verdict (same helper shape as `mwoc-w2-contract-judgment`). */
function settleToTerminal(worker: FakeWorker, reply = "done"): void {
	settle(worker, reply);
	settle(worker, reply);
}

interface RunRecord {
	status?: string;
	exit?: number;
	claims?: Record<string, unknown>;
}

function readRun(fx: Fixture): RunRecord {
	return JSON.parse(fs.readFileSync(path.join(fx.taskDir, "run.json"), "utf8")) as RunRecord;
}

function readTrace(fx: Fixture): string {
	try {
		return fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8");
	} catch {
		return "";
	}
}

function claimsLines(trace: string): string[] {
	return trace.split(/\r?\n/).filter((line) => line.startsWith("[CLAIMS]"));
}

/** The readback line the PM consumes for an NC run. */
function readback(fx: Fixture): string {
	return readTerminalDetail(fx.taskDir, "needs-clarification");
}

function claimOf(id: string, overrides: Partial<Claim> = {}): Claim {
	return {
		id,
		type: "grep",
		parent: "",
		statement: `claim ${id}`,
		falsifier: `refute ${id} differently`,
		locator: "src/a.ts",
		judgement: "grep: readFileSync => count=0",
		budget: 1,
		row: 1,
		...overrides,
	};
}

// ── 1. claims block parsing (requirement 1) ─────────────────────────────────

describe("TaskMeta.claims parsing (T-04b requirement 1)", () => {
	it("re-parses the mw-claims block T-02 injects into task.md", () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01", budget: 2 }), claimRow({ id: "C-02", type: "manual" })]),
		});
		const meta = parseTaskMd(path.join(fx.taskDir, "task.md"));
		console.log(`[VERIFY] claims parsed=${JSON.stringify(meta.claims?.map((c) => [c.id, c.type, c.budget]))}`);
		expect(meta.claims?.map((claim) => claim.id)).toEqual(["C-01", "C-02"]);
		expect(meta.claims?.[0]?.budget).toBe(2);
		expect(meta.claims?.[1]?.type).toBe("manual");
	});

	it("no block => the field stays unset (zero-branch legacy path)", () => {
		const fx = makeFixture({});
		expect(parseTaskMd(path.join(fx.taskDir, "task.md")).claims).toBeUndefined();
	});

	it("a present-but-empty block is `[]`, never silently 'no claims'", () => {
		const fx = makeFixture({ claims: "<!-- mw-claims: v1 -->\n<!-- /mw-claims -->\n" });
		expect(parseTaskMd(path.join(fx.taskDir, "task.md")).claims).toEqual([]);
	});
});

// ── 2. AC-008 settlement criteria: one negative case each ───────────────────

describe("AC-008 ①-B-1: a self-witness verdict is blocked", () => {
	it("closed row whose only evidence is the product itself => exit 2", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01" })]),
			product: researchProduct([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "report.md:3" }),
			]),
			// The self-witness ref must resolve on disk, otherwise the fixture
			// would trip B-3's `:evidence` criterion instead of B-1.
			projectFiles: ["src/a.ts", "report.md"],
		});
		const worker = await startWorker(fx);
		settleToTerminal(worker);

		const run = readRun(fx);
		console.log(`[VERIFY] AC-008-1 exit=${run.exit} status=${run.status} steer=${worker.sent[0]?.text ?? "-"}`);
		expect(run.exit).toBe(2);
		expect(run.status).toBe("needs-clarification");
		expect(worker.sent[0]?.text).toContain("claim:C-01:self-evidence");
		expect(readback(fx)).toContain("未裁决断言：C-01");
	});
});

describe("AC-008 ②-B-2: too many unverified claims is not a PASS", () => {
	it("3/5 unverified (research role, 60% > 40%) => exit 2", async () => {
		const ids = ["C-01", "C-02", "C-03", "C-04", "C-05"];
		const fx = makeFixture({
			claims: claimsBlock(ids.map((id) => claimRow({ id }))),
			product: researchProduct([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" }),
				verdictRow({ id: "C-02", verdict: "closed", finding: "不成立", evidence: "src/a.ts:4" }),
				verdictRow({ id: "C-03", verdict: "unverified", finding: "无法判定", reason: "budget" }),
				verdictRow({ id: "C-04", verdict: "unverified", finding: "无法判定", reason: "not-found" }),
				verdictRow({ id: "C-05", verdict: "unverified", finding: "无法判定", reason: "no-access" }),
			]),
		});
		const worker = await startWorker(fx);
		settleToTerminal(worker);

		const run = readRun(fx);
		console.log(`[VERIFY] AC-008-2 exit=${run.exit} ratio=${run.claims?.unverified}/${run.claims?.total}`);
		expect(run.exit).toBe(2);
		expect(worker.sent[0]?.text).toContain("claims:unverified-ratio:3/5>40%");
		expect(run.claims).toMatchObject({ total: 5, closed: 2, partial: 0, unverified: 3 });
	});

	it("the boundary itself passes: 2/5 = 40% and the review role's 3/5 = 60%", () => {
		const table = parseVerdictTable(
			verdictTable([
				verdictRow({ id: "C-01", verdict: "unverified", finding: "无法判定", reason: "budget" }),
				verdictRow({ id: "C-02", verdict: "unverified", finding: "无法判定", reason: "budget" }),
				verdictRow({ id: "C-03", verdict: "unverified", finding: "无法判定", reason: "not-found" }),
				verdictRow({ id: "C-04", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" }),
				verdictRow({ id: "C-05", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" }),
			]),
		);
		const claims = ["C-01", "C-02", "C-03", "C-04", "C-05"].map((id) => claimOf(id));
		const base = { claims, table, traceReads: 99, projectDir: process.cwd() };
		console.log(
			`[VERIFY] AC-008-2 boundary researcher=${JSON.stringify(claimSettlementGaps({ ...base, role: "research" }))}`,
		);
		// 3/5 = 60% > 40%: the research role is over its limit.
		expect(claimSettlementGaps({ ...base, role: "research" })).toEqual(["claims:unverified-ratio:3/5>40%"]);
		// ... but the review role's own limit is 60%, and `>` keeps the boundary green.
		expect(claimSettlementGaps({ ...base, role: "review" })).toEqual([]);
		expect(CLAIM_UNVERIFIED_MAX_REVIEW).toBeGreaterThan(CLAIM_UNVERIFIED_MAX_DEFAULT);
	});

	it("review role: 3/5 unverified sits ON its 60% limit => done, not NC", async () => {
		const ids = ["C-01", "C-02", "C-03", "C-04", "C-05"];
		const fx = makeFixture({
			type: "review",
			claims: claimsBlock(ids.map((id) => claimRow({ id }))),
			product: reviewProduct([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" }),
				verdictRow({ id: "C-02", verdict: "closed", finding: "不成立", evidence: "src/a.ts:4" }),
				verdictRow({ id: "C-03", verdict: "unverified", finding: "无法判定", reason: "no-access" }),
				verdictRow({ id: "C-04", verdict: "unverified", finding: "无法判定", reason: "no-access" }),
				verdictRow({ id: "C-05", verdict: "unverified", finding: "无法判定", reason: "no-access" }),
			]),
		});
		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		console.log(`[VERIFY] AC-008-2 review exit=${run.exit} unverified=${run.claims?.unverified}`);
		expect(run.exit).toBe(0);
		expect(run.claims).toMatchObject({ total: 5, closed: 2, unverified: 3, tokens: null });
	});
});

describe("AC-008 ③-B-6: Σ取数 upper bounds", () => {
	it("Σ取数 above min(Σ预算, fileCap) => gap (unit)", () => {
		const claims = [claimOf("C-01", { budget: 1 }), claimOf("C-02", { budget: 1 })];
		const table = parseVerdictTable(
			verdictTable([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3", fetches: "1" }),
				verdictRow({ id: "C-02", verdict: "closed", finding: "成立", evidence: "src/a.ts:4", fetches: "1" }),
			]),
		);
		const gaps = claimSettlementGaps({
			claims,
			table,
			role: "research",
			traceReads: 10,
			projectDir: process.cwd(),
		});
		console.log(`[VERIFY] AC-008-3a cap gaps=${JSON.stringify(gaps)}`);
		// Σ预算 = 2 => fileCap = 2, and the table reports 2 fetches... push it over:
		expect(gaps).toEqual([]);
		const over = parseVerdictTable(
			verdictTable([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3", fetches: "2" }),
				verdictRow({ id: "C-02", verdict: "closed", finding: "成立", evidence: "src/a.ts:4", fetches: "1" }),
			]),
		);
		expect(
			claimSettlementGaps({ claims, table: over, role: "research", traceReads: 10, projectDir: process.cwd() }),
		).toEqual(["claims:fetches:3>2"]);
	});

	it("Σ取数 above the trace's own read-class tool_call count => exit 2", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01", budget: 3 })]),
			product: researchProduct([
				verdictRow({
					id: "C-01",
					verdict: "closed",
					finding: "成立",
					evidence: "src/a.ts:3",
					fetches: "2",
				}),
			]),
		});
		const worker = await startWorker(fx);
		settleToTerminal(worker);

		const run = readRun(fx);
		console.log(`[VERIFY] AC-008-3b exit=${run.exit} fetches=${run.claims?.fetches}`);
		expect(run.exit).toBe(2);
		// 2 fetches reported against 0 recorded read-class tool calls: the cap (3)
		// is not the binding limit, the trace is.
		expect(worker.sent[0]?.text).toContain("claims:fetches:2>trace:0");
		expect(worker.sent[0]?.text).not.toContain("claims:fetches:2>3");
	});
});

describe("AC-008 ④-B10: struct rows and two-way id equality", () => {
	it("a struct row counted as closed => exit 2", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01", type: "struct", judgement: "shape: report.md x 6" })]),
			product: researchProduct([
				verdictRow({ id: "C-01", type: "struct", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" }),
			]),
		});
		const worker = await startWorker(fx);
		settleToTerminal(worker);

		const run = readRun(fx);
		console.log(`[VERIFY] AC-008-4a exit=${run.exit} struct-held`);
		expect(run.exit).toBe(2);
		expect(worker.sent[0]?.text).toContain("claim:C-01:struct-held");
	});

	it("a card claim the table never adjudicates => exit 2", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01" }), claimRow({ id: "C-02" })]),
			product: researchProduct([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" }),
			]),
		});
		const worker = await startWorker(fx);
		settleToTerminal(worker);

		const run = readRun(fx);
		console.log(`[VERIFY] AC-008-4b exit=${run.exit} missing-row=${worker.sent[0]?.text ?? "-"}`);
		expect(run.exit).toBe(2);
		expect(worker.sent[0]?.text).toContain("claim:C-02:missing-row");
		expect(readback(fx)).toContain("未裁决断言：C-02");
	});
});

describe("AC-008 ⑥-B-7: a re-used previous-round verdict needs carried-from", () => {
	it("a closed row citing only pre-run artifacts => exit 2", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01" })]),
			product: researchProduct([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "evidence/claims/qg.md:2" }),
			]),
			projectFiles: ["src/a.ts", "evidence/claims/qg.md"],
			staleFiles: ["evidence/claims/qg.md"],
		});
		const worker = await startWorker(fx);
		settleToTerminal(worker);

		const run = readRun(fx);
		console.log(`[VERIFY] AC-008-6 exit=${run.exit} carried-from`);
		expect(run.exit).toBe(2);
		expect(worker.sent[0]?.text).toContain("claim:C-01:carried-from");
	});

	it("the same row WITH `carried-from:` passes (the only legal reuse channel)", () => {
		const fx = makeFixture({ projectFiles: ["src/a.ts", "evidence/claims/qg.md"] });
		const withMarker = parseVerdictTable(
			verdictTable([
				verdictRow({
					id: "C-01",
					verdict: "closed",
					finding: "成立",
					evidence: "evidence/claims/qg.md:2",
					reason: "carried-from: evidence/claims/qg.md:2",
				}),
			]),
		);
		const withoutMarker = parseVerdictTable(
			verdictTable([
				verdictRow({
					id: "C-01",
					verdict: "closed",
					finding: "成立",
					evidence: "evidence/claims/qg.md:2",
				}),
			]),
		);
		// A clock far in the future makes every citation "stale"; only the
		// explicit marker may rescue it.
		const base = {
			claims: [claimOf("C-01")],
			role: "research",
			traceReads: 99,
			taskMtimeMs: Date.now() + 3_600_000,
			projectDir: fx.projectRoot,
		};
		console.log(
			`[VERIFY] AC-008-6 marker gaps=${JSON.stringify(claimSettlementGaps({ ...base, table: withoutMarker }))}`,
		);
		expect(claimSettlementGaps({ ...base, table: withoutMarker })).toEqual(["claim:C-01:carried-from"]);
		expect(claimSettlementGaps({ ...base, table: withMarker })).toEqual([]);
	});
});

// ── 3. `[CLAIMS]` trace row ────────────────────────────────────────────────

describe("[CLAIMS] trace row (design D-004)", () => {
	it("a settled claims run writes exactly one machine row, never into [END]", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01" })]),
			product: researchProduct([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" }),
			]),
		});
		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		const trace = readTrace(fx);
		const rows = claimsLines(trace);
		console.log(`[VERIFY] CLAIMS row exit=${run.exit} rows=${JSON.stringify(rows)}`);
		expect(run.exit).toBe(0);
		expect(rows).toHaveLength(1);
		const row = rows[0] ?? "";
		expect(row).toMatch(CLAIMS_LINE_RE);
		expect(row).toMatch(/ claims=1 closed=1 partial=0 unverified=0 fetches=0$/);
		// The independent-line rule: `[END]` is untouched (both sides anchor it).
		const end = trace.split(/\r?\n/).find((line) => line.startsWith("[END]")) ?? "";
		expect(end).not.toContain("claims=");
		// Position: the row precedes the terminal line.
		expect(trace.indexOf("[CLAIMS]")).toBeLessThan(trace.indexOf("[END]"));
	});

	it("format negative: a truncated / reordered row is NOT a measurement", () => {
		const counts = claimCounts(
			[claimOf("C-01")],
			parseVerdictTable(
				verdictTable([verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" })]),
			),
			4,
		);
		const line = formatClaimsTraceLine(counts, new Date("2026-10-21T10:00:00.000Z"));
		console.log(`[VERIFY] CLAIMS format=${line}`);
		expect(line).toBe("[CLAIMS] 2026-10-21T10:00:00.000Z claims=1 closed=1 partial=0 unverified=0 fetches=4");
		expect(line).toMatch(CLAIMS_LINE_RE);
		// Missing field => unparseable (usage.py refuses to guess).
		expect(CLAIMS_LINE_RE.test("[CLAIMS] 2026-10-21T10:00:00Z claims=1 closed=1 partial=0 unverified=0")).toBe(false);
		// Reordered fields => unparseable (the order is frozen on both sides).
		expect(
			CLAIMS_LINE_RE.test("[CLAIMS] 2026-10-21T10:00:00Z closed=1 claims=1 partial=0 unverified=0 fetches=4"),
		).toBe(false);
	});

	it("a claims-free book writes NO [CLAIMS] row and keeps the recovery-gap row unchanged", async () => {
		const fx = makeFixture({ product: researchProduct() });
		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		const trace = readTrace(fx);
		console.log(`[VERIFY] CLAIMS absent exit=${run.exit} lines=${JSON.stringify(claimsLines(trace))}`);
		expect(run.exit).toBe(0);
		expect(claimsLines(trace)).toEqual([]);
		expect(trace).not.toContain("[CLAIMS]");
		// The pre-settle row keeps its exact pre-T-04b shape (no ` claims=` tail).
		expect(trace).toMatch(/recovery-gap missing=- selfcheck=pending\n/);
	});
});

// ── 4. run.json `claims` subobject ─────────────────────────────────────────

describe("run.json claims subobject (design §3.4, T-05 readback)", () => {
	/** Local mirror of `status-model.ts::readRunClaims` (private there): five
	 * counters required, `tokens` missing/null = not attributable. Returns
	 * `null` for a run that carries no claims key at all. */
	function readRunClaims(file: string): Record<string, number | null> | null {
		const data = JSON.parse(fs.readFileSync(file, "utf8")) as { claims?: Record<string, unknown> };
		const claims = data.claims;
		if (typeof claims !== "object" || claims === null) return null;
		const counter = (value: unknown): number | null =>
			typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.trunc(value) : null;
		const total = counter(claims.total);
		if (total === null) return null;
		return {
			total,
			closed: counter(claims.closed),
			partial: counter(claims.partial),
			unverified: counter(claims.unverified),
			fetches: counter(claims.fetches),
			tokens: counter(claims.tokens),
		};
	}

	it("write: the six keys are persisted, tokens null when not attributable", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01" })]),
			product: researchProduct([
				verdictRow({ id: "C-01", verdict: "partial", finding: "部分成立", evidence: "src/a.ts:3" }),
			]),
		});
		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		console.log(`[VERIFY] run.json claims=${JSON.stringify(run.claims)}`);
		expect(Object.keys(run.claims ?? {}).sort()).toEqual([
			"closed",
			"fetches",
			"partial",
			"tokens",
			"total",
			"unverified",
		]);
		expect(run.claims).toEqual({ total: 1, closed: 0, partial: 1, unverified: 0, fetches: 0, tokens: null });
	});

	it("read back: run.json and the [CLAIMS] row carry the same counters", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01" }), claimRow({ id: "C-02" })]),
			product: researchProduct([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "src/a.ts:3" }),
				verdictRow({ id: "C-02", verdict: "unverified", finding: "无法判定", reason: "budget" }),
			]),
		});
		const worker = await startWorker(fx);
		settleToTerminal(worker);

		const claims = readRunClaims(path.join(fx.taskDir, "run.json"));
		const row = claimsLines(readTrace(fx))[0] ?? "";
		const match = CLAIMS_LINE_RE.exec(row);
		console.log(`[VERIFY] claims readback=${JSON.stringify(claims)} row=${row}`);
		expect(claims).toEqual({ total: 2, closed: 1, partial: 0, unverified: 1, fetches: 0, tokens: null });
		expect(match?.slice(1).map((value) => Number(value))).toEqual([2, 1, 0, 1, 0]);
		expect(claims?.tokens).toBeNull();
	});

	it("no claims block => the key is ABSENT (T-05 renders n/a, never zero)", async () => {
		const fx = makeFixture({ product: researchProduct() });
		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = readRun(fx);
		expect(run.exit).toBe(0);
		expect("claims" in run).toBe(false);
		expect(readRunClaims(path.join(fx.taskDir, "run.json"))).toBeNull();
	});
});

// ── 5. one self-check trigger, one `selfCheckSent` ─────────────────────────

describe("pre-settle self-check shares the trigger and the one-shot state", () => {
	it("a claims-free book keeps the pre-T-04b steer sentence byte for byte", async () => {
		const fx = makeFixture({
			// All sections except the substantive 残留与未验证, no claims block at all.
			product: [
				"## 结论",
				"",
				"done.",
				"",
				"## 证据",
				"",
				"[VERIFY] probe -> ok",
				"",
				"## 上下文来源",
				"",
				"src/a.ts:3",
				"",
			].join("\n"),
		});
		const worker = await startWorker(fx);
		settle(worker, "done");

		console.log(`[VERIFY] selfcheck byte-stable=${worker.sent[0]?.text ?? "-"}`);
		expect(worker.sent[0]?.text).toBe(
			"[mw recovery self-check] 你的产物缺少恢复契约段：残留与未验证。请在 report.md / output.md 中用 `## <段名>` 标题补上这些段落，然后重新收尾；本进程只自检一次，之后按实际产物判定。",
		);
		expect(claimsLines(readTrace(fx))).toEqual([]);
	});

	it("recovery gap + claim gap render separately in ONE steer, then exit 2", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01" })]),
			// Missing 残留与未验证 (substantive) AND an unsettled claim.
			product: [
				"## 结论",
				"",
				"claims settled.",
				"",
				"## 证据",
				"",
				"[VERIFY] probe -> ok",
				"",
				"## 上下文来源",
				"",
				"src/a.ts:3",
				"",
				verdictTable([verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "report.md:3" })]),
			].join("\n"),
			projectFiles: ["src/a.ts", "report.md"],
		});
		const worker = await startWorker(fx);
		settle(worker, "done");

		const first = readRun(fx);
		const steer = worker.sent[0]?.text ?? "";
		console.log(`[VERIFY] selfcheck status=${first.status} sent=${worker.sent.length} steer=${steer}`);
		expect(first.status).toBe("running");
		expect(worker.sent).toHaveLength(1);
		expect(worker.sent[0]?.deliverAs).toBe("followUp");
		// Both halves of the ONE message: the recovery render and the claim render.
		expect(steer).toContain("恢复契约段：残留与未验证");
		expect(steer).toContain("首个缺失 claim id：C-01");
		expect(steer).toContain("claim:C-01:self-evidence");
		expect(readTrace(fx)).toMatch(/recovery-gap missing=残留与未验证 selfcheck=pending claims=C-01/);

		settle(worker, "done");
		const run = readRun(fx);
		console.log(`[VERIFY] selfcheck terminal exit=${run.exit} sent=${worker.sent.length}`);
		expect(run.exit).toBe(2);
		expect(run.status).toBe("needs-clarification");
		expect(worker.sent).toHaveLength(1);
	});

	it("claim gaps alone fire the one turn; the terminal readback names the id", async () => {
		const fx = makeFixture({
			claims: claimsBlock([claimRow({ id: "C-01" })]),
			product: researchProduct([
				verdictRow({ id: "C-01", verdict: "closed", finding: "成立", evidence: "report.md:3" }),
			]),
			projectFiles: ["src/a.ts", "report.md"],
		});
		const worker = await startWorker(fx);
		settle(worker, "done");
		expect(worker.sent).toHaveLength(1);
		expect(claimGapIds(["claim:C-01:self-evidence", "claims:fetches:9>1"])).toEqual(["C-01"]);
		settle(worker, "done");
		expect(readRun(fx).exit).toBe(2);
		expect(readback(fx)).toContain("未裁决断言：C-01");
		expect(readOutputSection(fx.taskDir, "Questions")).toContain("未裁决断言：C-01");
	});
});
