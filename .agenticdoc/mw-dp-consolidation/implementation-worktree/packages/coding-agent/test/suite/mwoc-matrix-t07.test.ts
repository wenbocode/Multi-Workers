/**
 * mwoc-matrix-t07.test.ts — T-07 / key `mw-worker-output-contract`: the
 * cross-cut matrix (design §10, task T-07 requirements 1-2).
 *
 * This is the CLOSING matrix: the five facets (write-face / ledger / judgement /
 * backfill / readback) were each fixed by batch A+B; this file is the one
 * re-runnable cross-cut verdict that stitches them together. Every assertion
 * carries its AC tag. No implementation is re-run or modified here — the tests
 * only read the landed source and the on-disk historical products.
 *
 * Sections:
 *   1. AC-001 × AC-015 — the 8-case judgement matrix driven through BOTH entry
 *      points: the judgement predicate (`checkRecovery`) and the candidate-set
 *      entry (`readTerminalGaps` over the file the settle would judge) give the
 *      same conclusion on the same text.
 *   2. AC-015 — candidate-set × judgement combinations: only `report-<slug>.md`,
 *      `report.md` + slug coexist, only `output.md`; the judged-file selection
 *      and the verdict come from one source (the two T-05 entries stay in sync).
 *   3. AC-005 — 3 historical mechanical-only products replay `exit=2 -> exit=0`
 *      through the full settle flow (I2 backfill lands in the judged file).
 *   4. AC-017 — the ledger-extractor four segments: (a) data regions produce 0
 *      `[WRITE_FILE]` rows; (b) the .NET APIs yield exactly 1 event each;
 *      (c) the `--glob` here-string no longer denies real writes
 *      (`allow=2 deny=0`); (d) `unjudgeable` derives from USABLE events, and
 *      the 12 existing ledger-family files show no regression (verified in
 *      evidence/woc-t07-baseline-diff-20261015.txt via the 24-file diff).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { diffLedger, parseWriteFileEvents } from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import { readTaskType } from "../../src/extensions/agent-team-loop/shared/task-frontmatter.ts";
import {
	checkRecovery,
	MECHANICAL_SECTIONS,
	RECOVERY_SECTIONS,
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
import {
	type BashWriteScopeConfig,
	checkBashWriteScopeTarget,
	classifyLedgerTargets,
	extractBashWriteCandidates,
	stripDataRegions,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const REPO_ROOT = fileURLToPath(new URL("../../../..", import.meta.url));

// ── shared fixtures (the mwoc-w2 harness pattern) ───────────────────────────

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
	const projectRoot = mkdtemp("mwoc-matrix-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const key = opts.key ?? "mwoc-matrix";
	const task = opts.task ?? "matrix-worker";
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

function gaps(fx: Fixture, summary: string, type?: string): ReturnType<typeof readTerminalGaps> {
	return readTerminalGaps({
		taskKey: fx.taskKey,
		agenticdocRoot: fx.trueRoot,
		summary,
		type,
		projectRoot: fx.projectRoot,
		judgeRecovery: true,
	});
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

// ── 1. AC-001 × AC-015: 8-case matrix through BOTH entry points ─────────────

describe("AC-001 cross-entry consistency (judgement entry = candidate-set entry)", () => {
	// The locked 8-case matrix (spec AC-001). For each case we drive the SAME
	// text through (a) the judgement predicate and (b) the candidate-set entry
	// (readTerminalGaps on a real on-disk report.md) and require the same
	// missing-section verdict.
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
		// (a) judgement entry.
		const verdict = checkRecovery(text, type);
		// (b) candidate-set entry: the same text lands in report.md and the
		//     settle reads the same product through agentProductText.
		const fx = makeFixture({ type, report: text });
		const selected = judgedProductFile(fx.taskDir);
		const viaCandidateSet = gaps(fx, "reply", type);
		console.log(
			`[VERIFY] AC-001 cross-entry ${JSON.stringify({
				type,
				judged: selected,
				predicateMissing: verdict.missing,
				gapsMissing: viaCandidateSet.missingSections,
				predicateOk: verdict.ok,
				gapsOk: viaCandidateSet.ok,
			})}`,
		);
		expect(selected).toBe(path.join(fx.taskDir, "report.md"));
		expect(viaCandidateSet.judged).toBe(true);
		expect(viaCandidateSet.missingSections).toEqual(expected);
		expect(verdict.missing).toEqual(expected);
		// Same conclusion from both entries on the same text.
		expect(viaCandidateSet.missingSections).toEqual(verdict.missing);
		expect(viaCandidateSet.ok).toBe(verdict.ok);
	});

	it("the mechanical whitelist is exactly 上下文来源 and stays a whitelist", () => {
		// AC-017(d) / R2 lock: only the mechanical section may be auto-filled.
		expect([...MECHANICAL_SECTIONS]).toEqual(["上下文来源"]);
		for (const name of ["结论", "证据", "残留与未验证", "改动清单", "未覆盖面声明"]) {
			expect(MECHANICAL_SECTIONS).not.toContain(name);
		}
	});
});

// ── 2. AC-015: candidate-set × judgement combinations ───────────────────────

describe("AC-015 candidate-set x judgement combinations", () => {
	function setMtime(file: string, ms: number): void {
		const when = new Date(ms);
		fs.utimesSync(file, when, when);
	}

	it("only report-<slug>.md: the slug is judged and the two entries agree", () => {
		// T-05 locked the second entry (hasReportProduct). This case asserts the
		// judged file IS the slug and the verdict comes from that file.
		const fx = makeFixture({ type: "research" });
		fs.writeFileSync(
			path.join(fx.taskDir, "report-matrix-slug.md"),
			headings(["结论", "证据", "残留与未验证"]),
			"utf8",
		);
		expect(hasReportProduct(fx.taskDir)).toBe(true);
		expect(judgedProductFile(fx.taskDir)).toBe(path.join(fx.taskDir, "report-matrix-slug.md"));
		// The slug misses 上下文来源: the I2 backfill appends it and the verdict flips.
		const before = gaps(fx, "reply", "research");
		expect(before.missingSections).toEqual(["上下文来源"]);
		expect(before.ok).toBe(false);
		expect(before.judged).toBe(true);
		console.log(
			`[VERIFY] AC-015 slug-only judged=${JSON.stringify(before.judged)} missing=${JSON.stringify(
				before.missingSections,
			)} predicate=${JSON.stringify(checkRecovery(agentProductText(fx.taskDir, "reply"), "research").missing)}`,
		);
		expect(checkRecovery(agentProductText(fx.taskDir, "reply"), "research").missing).toEqual(["上下文来源"]);
	});

	it("report.md + slug coexist: report.md wins, the slug content is ignored", () => {
		const fx = makeFixture({
			type: "research",
			report: COMPLETE_RESEARCH, // complete
		});
		// A slug that misses everything must NOT change the verdict.
		fs.writeFileSync(path.join(fx.taskDir, "report-loser-slug.md"), "no headings here", "utf8");
		setMtime(path.join(fx.taskDir, "report-loser-slug.md"), Date.now() + 10_000);
		expect(judgedProductFile(fx.taskDir)).toBe(path.join(fx.taskDir, "report.md"));
		const verdict = gaps(fx, "reply", "research");
		expect(verdict.missingSections).toEqual([]);
		expect(verdict.ok).toBe(true);
		console.log(
			`[VERIFY] AC-015 report+slug judged=${path.basename(judgedProductFile(fx.taskDir) ?? "")} missing=${JSON.stringify(verdict.missingSections)}`,
		);
	});

	it("only output.md: output.md is judged and the verdict comes from it", () => {
		const fx = makeFixture({ type: "research", output: "no headings in output" });
		expect(judgedProductFile(fx.taskDir)).toBe(path.join(fx.taskDir, "output.md"));
		expect(hasReportProduct(fx.taskDir)).toBe(false);
		const verdict = gaps(fx, "reply", "research");
		expect(verdict.judged).toBe(true);
		expect(verdict.missingSections).toEqual([...BASE]);
		console.log(
			`[VERIFY] AC-015 output-only judged=${path.basename(judgedProductFile(fx.taskDir) ?? "")} missing=${JSON.stringify(verdict.missingSections)}`,
		);
	});

	it("the settle exit agrees with the candidate-set verdict on all three forms", async () => {
		// slug-only complete research => exit=0 (I2 backfills nothing).
		const slug = makeFixture({ type: "research" });
		fs.writeFileSync(path.join(slug.taskDir, "report-complete-slug.md"), COMPLETE_RESEARCH, "utf8");
		const w1 = await startWorker(slug);
		settle(w1, "done");
		settle(w1, "done");
		const slugRun = JSON.parse(fs.readFileSync(path.join(slug.taskDir, "run.json"), "utf8")) as {
			exit: number;
			status: string;
		};
		expect(slugRun.exit).toBe(0);
		expect(slugRun.status).toBe("done");

		// report.md + slug: report wins => exit=0.
		const both = makeFixture({ type: "research", report: COMPLETE_RESEARCH });
		fs.writeFileSync(path.join(both.taskDir, "report-incomplete-slug.md"), "no headings", "utf8");
		const w2 = await startWorker(both);
		settle(w2, "done");
		settle(w2, "done");
		const bothRun = JSON.parse(fs.readFileSync(path.join(both.taskDir, "run.json"), "utf8")) as {
			exit: number;
			status: string;
		};
		expect(bothRun.exit).toBe(0);
		expect(bothRun.status).toBe("done");

		// output-only research with complete base four + a machine line => exit=0.
		const out = makeFixture({
			type: "research",
			output: `${COMPLETE_RESEARCH}\n[VERIFY] probe -> ok\n`,
		});
		const w3 = await startWorker(out);
		settle(w3, "done");
		settle(w3, "done");
		const outRun = JSON.parse(fs.readFileSync(path.join(out.taskDir, "run.json"), "utf8")) as {
			exit: number;
			status: string;
		};
		expect(outRun.exit).toBe(0);
		expect(outRun.status).toBe("done");
		console.log(
			`[VERIFY] AC-015 settle exits slug=${slugRun.exit} report+slug=${bothRun.exit} output-only=${outRun.exit}`,
		);
	});
});

// ── 3. AC-005: historical mechanical-only replay, exit=2 -> exit=0 ─────────

describe("AC-005 historical mechanical-only replay (3 cases, exit=2 -> exit=0)", () => {
	// The same 3 research products T-05 replayed, read from the on-disk text
	// that was never PM-patched (R-a snapshot; the flip disposition classifies
	// exactly these 3 as backfill-rescued under the current predicate).
	const REPLAY = [
		"mw-dynamic-concurrency/workers/mdc-rq1-dispatch-chain",
		"mw-guard-form-hardening/workers/mwgf-drq3-role-key-design",
		"mw-vision-role/workers/mvr-rq5-awareness-surface",
	];

	function makeReplayFixture(rel: string): Fixture & { judged: string; preText: string; type: string } {
		const source = path.join(REPO_ROOT, ".agenticdoc", rel);
		expect(fs.existsSync(path.join(source, "task.md")), `${rel} task.md`).toBe(true);
		const projectRoot = mkdtemp("mwoc-matrix-replay-");
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
		expect(pre.missing).toEqual(["上下文来源"]);
		// The disposition class is backfill-rescued: the only gap is mechanical.
		expect(recoverySectionsFor(fx.type)).toContain("上下文来源");

		const worker = await startWorker(fx);
		settle(worker, "done");

		const run = JSON.parse(fs.readFileSync(path.join(fx.taskDir, "run.json"), "utf8")) as {
			exit: number;
			status: string;
		};
		const after = fs.readFileSync(fx.judged, "utf8");
		console.log(`[VERIFY] AC-005 replay post task=${rel} exit=${run.exit} status=${run.status}`);
		expect(run.exit).toBe(0);
		expect(run.status).toBe("done");
		// Judgement and product agree (I1): the judged file carries the heading
		// now, the earlier bytes are a pure prefix, the marker is present, and
		// the candidate-set entry reports zero gaps on the same text.
		expect(after.startsWith(fx.preText)).toBe(true);
		expect(after).toContain("## 上下文来源");
		expect(after).toContain(MECHANICAL_CONTEXT_MARKER);
		expect(checkRecovery(after, fx.type).ok).toBe(true);
		const postGaps = gaps(fx, "", fx.type);
		expect(postGaps.judged).toBe(true);
		expect(postGaps.missingSections).toEqual([]);
		expect(postGaps.ok).toBe(true);
	});
});

// ── 4. AC-017: the ledger-extractor four segments ───────────────────────────

const MIN13 = "@'\n'-> `:1175";
const RQ2_55 = "$py = @'\n ('-> `:1175 release`', '-> `:1184 release`'),";
const RQ3_319 = [
	"$code = @'",
	"[VERIFY] RQ-W3: self_guard_hit=1 (xkey-gate-guard blocked this worker's own evidence-write command: quote-of-autopilot-dir plus PowerShell delete cmdlet inside here-string, a false positive; bypassed by splitting the quoted literal)",
	'"""',
	'CHUNK = CHUNK.replace("<AUTOPILOT_DIR>", ".agenticdoc/_aut" + "opilot")',
].join("\n");
const RQ3_336 = `${RQ3_319}\n$code | python -`;

describe("AC-017(a) data regions produce zero [WRITE_FILE] rows", () => {
	it("the 13/55/319/336 char here-string forms each extract zero candidates", () => {
		const rows: string[] = [];
		for (const [label, form] of [
			["13", MIN13],
			["55", RQ2_55],
			["319", RQ3_319],
			["336", RQ3_336],
		] as const) {
			expect(form).toHaveLength(Number(label) === 13 ? 13 : label === "55" ? 55 : label === "319" ? 319 : 336);
			const candidates = extractBashWriteCandidates(form);
			rows.push(`${label}:${candidates.length}`);
			expect(candidates, `candidates ${label}`).toEqual([]);
			expect(classifyLedgerTargets(form), `ledger ${label}`).toEqual({ recorded: [], unresolved: [] });
		}
		console.log(`[VERIFY] AC-017(a) candidate_counts=${rows.join(",")}`);
	});

	it("stripDataRegions is the pre-lexer stage and the redirect survives only on the opener line", () => {
		expect(stripDataRegions(MIN13)).not.toContain("->");
		expect(stripDataRegions("cat <<EOF > out.md\nbody > notafile\nEOF\n")).not.toContain("notafile");
		expect(classifyLedgerTargets("cat <<EOF > out.md\nbody > notafile\nEOF\n")).toEqual({
			recorded: ["out.md"],
			unresolved: [],
		});
	});
});

describe("AC-017(b) .NET file APIs extract exactly one event each", () => {
	it("WriteAllText / AppendAllText each yield exactly one candidate", () => {
		const writeAll = extractBashWriteCandidates('[System.IO.File]::WriteAllText("src/a.ts", "x")');
		const appendAll = extractBashWriteCandidates('[System.IO.File]::AppendAllText("evidence/x.md", "x")');
		console.log(
			`[VERIFY] AC-017(b) write_all_text=${writeAll.length} append_all_text=${appendAll.length} ` +
				`write_all=${JSON.stringify(writeAll)} append_all=${JSON.stringify(appendAll)}`,
		);
		expect(writeAll).toEqual([{ target: "src/a.ts", pattern: "net-file-api", verbatim: true }]);
		expect(appendAll).toEqual([{ target: "evidence/x.md", pattern: "net-file-api", verbatim: true }]);
	});

	it("a resolved .NET write lands as exactly one [WRITE_FILE] event", () => {
		const command = '$path = "evidence/x.md"\n[System.IO.File]::WriteAllText($path, $c)';
		const classification = classifyLedgerTargets(command);
		expect(classification.recorded).toEqual(["evidence/x.md"]);
		const eventLines = classification.recorded.map((target) => `[WRITE_FILE] path=${target}\n`).join("");
		expect(parseWriteFileEvents(eventLines)).toEqual(["evidence/x.md"]);
		console.log(
			`[VERIFY] AC-017(b) recorded=${JSON.stringify(classification.recorded)} events=${JSON.stringify(parseWriteFileEvents(eventLines))}`,
		);
	});
});

describe("AC-017(c) the --glob here-string no longer denies real writes", () => {
	const CACHED_CORPUS = path.join(REPO_ROOT, ".agenticdoc", "mw-worker-output-contract", "workers", "woc-rq3-ledger");

	const RQ1_WRITE_SCOPE = [
		".agenticdoc/mw-write-face-guard/workers/wfg-rq1-write-face-sources",
		".agenticdoc/mw-write-face-guard/evidence",
	];

	const RQ1_CONFIG: BashWriteScopeConfig = {
		projectRoot: REPO_ROOT,
		taskDir: path.join(REPO_ROOT, ".agenticdoc", "mw-write-face-guard", "workers", "wfg-rq1-write-face-sources"),
		keyDir: path.join(REPO_ROOT, ".agenticdoc", "mw-write-face-guard"),
		trueRoot: path.join(REPO_ROOT, ".agenticdoc"),
		writeScope: RQ1_WRITE_SCOPE,
	};

	/** The production guard sequence: first blocked candidate ends the
	 * command's judgement; allow-unknown is audited and continued. */
	function replayGuard(commands: readonly string[]): { allowDetermined: number; deny: number; allowUnknown: number } {
		const counts = { allowDetermined: 0, deny: 0, allowUnknown: 0 };
		for (const command of commands) {
			for (const candidate of extractBashWriteCandidates(command)) {
				const verdict = checkBashWriteScopeTarget(RQ1_CONFIG, candidate.target, candidate.verbatim);
				if (verdict.rule === "allow-unknown") {
					counts.allowUnknown += 1;
					continue;
				}
				if (verdict.allowed) {
					counts.allowDetermined += 1;
					continue;
				}
				counts.deny += 1;
				break;
			}
		}
		return counts;
	}

	/** Reduced inline analogues of the three blocked rq1 commands (same shape:
	 * two `.NET` writes with a here-string body carrying `--glob`, one bare
	 * `Write-Output … --glob x`). Used when the cached real corpus is absent. */
	const INLINE_RQ1_WRITES: readonly string[] = [
		[
			"cd H:\\git\\Multi-Workers",
			'$path = ".agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md"',
			"$enc = New-Object System.Text.UTF8Encoding($false)",
			"$part = @'",
			"rg -n --no-heading -F <term> --glob '!node_modules' .",
			"'@",
			"[System.IO.File]::WriteAllText($path, $part, $enc)",
		].join("\n"),
		[
			"cd H:\\git\\Multi-Workers",
			'$path = ".agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md"',
			"$enc = New-Object System.Text.UTF8Encoding($false)",
			"$t = [System.IO.File]::ReadAllText($path)",
			"$addition = @'",
			"[WRITE_SCOPE] ... detail=outside-allowed-surface target=--glob ...",
			"'@",
			'if ($t.Contains($anchor)) { [System.IO.File]::WriteAllText($path,$t,$enc); "inserted" }',
		].join("\n"),
		"cd H:\\git\\Multi-Workers\nWrite-Output a <term> --glob x",
	];

	/** The three real rq1 commands from the cached session corpus (indices 54 /
	 * 112 / 111 of `rq1-allbash.json`), or `undefined` on a clean checkout. */
	function cachedRq1BlockedCommands(): readonly string[] | undefined {
		const file = path.join(CACHED_CORPUS, "rq1-allbash.json");
		if (!fs.existsSync(file)) return undefined;
		const rows = JSON.parse(fs.readFileSync(file, "utf8")) as Array<{ command?: unknown }>;
		const pick = (index: number): string | undefined => {
			const value = rows[index]?.command;
			return typeof value === "string" ? value : undefined;
		};
		const write1 = pick(54);
		const write2 = pick(112);
		const nonWrite = pick(111);
		if (
			write1 !== undefined &&
			write1.includes("--glob") &&
			write1.includes("[System.IO.File]::WriteAllText") &&
			write2 !== undefined &&
			write2.includes("--glob") &&
			write2.includes("[System.IO.File]::WriteAllText") &&
			nonWrite === "cd H:\\git\\Multi-Workers\nWrite-Output a <term> --glob x"
		) {
			return [write1, write2, nonWrite];
		}
		return undefined;
	}

	it("replays the three blocked rq1 commands as allow=2 deny=0 (was allow=0 deny=3)", () => {
		const real = cachedRq1BlockedCommands();
		const commands = real ?? INLINE_RQ1_WRITES;
		const counts = replayGuard(commands);
		console.log(
			`[VERIFY] AC-017(c) source=${real === undefined ? "inline" : "real-corpus"} ` +
				`allow=${counts.allowDetermined} deny=${counts.deny} allow_unknown=${counts.allowUnknown}`,
		);
		expect(counts).toEqual({ allowDetermined: 2, deny: 0, allowUnknown: 0 });
	});

	it("`Write-Output a <term> --glob x` produces no candidate at all", () => {
		expect(extractBashWriteCandidates("cd H:\\git\\Multi-Workers\nWrite-Output a <term> --glob x")).toEqual([]);
	});
});

describe("AC-017(d) unjudgeable derives from USABLE events", () => {
	const DECLARED = "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts";

	function report(declared: string[]): string {
		return [
			"## 结论",
			"",
			"done",
			"",
			"## 改动清单",
			"",
			...declared.map((file) => `- ${file} — intent`),
			"",
			"## 残留与未验证",
			"",
			"none",
		].join("\n");
	}

	it("a garbage [WRITE_FILE] line cannot close the gate (unjudgeable stays true)", () => {
		const trace = "[WRITE_FILE] path=`:1175\n";
		const rawRecorded = parseWriteFileEvents(trace);
		const ledger = diffLedger(report([DECLARED]), trace, { projectRoot: REPO_ROOT });
		console.log(
			`[VERIFY] AC-017(d) garbage_event raw_recorded=${rawRecorded.length} ` +
				`old_gate_closed=${rawRecorded.length > 0} new_unjudgeable=${ledger.unjudgeable}`,
		);
		expect(rawRecorded).toEqual(["`:1175"]);
		expect(ledger.unjudgeable).toBe(true);
		expect(ledger.extra).toEqual([]);
	});

	it("a zero-event trace with a declaration stays unjudgeable; without one it is green", () => {
		expect(diffLedger(report([DECLARED]), "", { projectRoot: REPO_ROOT }).unjudgeable).toBe(true);
		expect(diffLedger(report([]), "", { projectRoot: REPO_ROOT }).unjudgeable).toBe(false);
		console.log(`[VERIFY] AC-017(d) zero_events declared_unjudgeable=true undeclared_unjudgeable=false`);
	});

	it("a usable [WRITE_FILE] for the declared file is green", () => {
		const ledger = diffLedger(report([DECLARED]), `[WRITE_FILE] path=${DECLARED}\n`, { projectRoot: REPO_ROOT });
		expect(ledger.unjudgeable).toBe(false);
		expect(ledger.extra).toEqual([]);
		console.log(`[VERIFY] AC-017(d) usable_event unjudgeable=${ledger.unjudgeable}`);
	});
});
