/**
 * mwoc-w3-ledger-extractor.test.ts — T-02 (key `mw-worker-output-contract`, W3):
 * the change-ledger extractor hardening (AC-008 / AC-017).
 *
 * The three data-flow constraints this file verifies (design §5):
 *   1. data regions are stripped BEFORE the lexer (`stripDataRegions`): a
 *      PowerShell here-string body and a POSIX heredoc body are DATA, so a
 *      literal `>` / `->` inside them can never become a redirect operator;
 *   2. a target is only taken from a write verb's target position and resolved
 *      through `verbatim` + a single-command literal value environment;
 *   3. an unresolved write verb becomes `[WRITE_UNRESOLVED]` (never a
 *      `[WRITE_FILE]`), and `diffLedger.unjudgeable` is derived from the count
 *      of USABLE `[WRITE_FILE]` events, so a garbage event cannot close the
 *      gate.
 *
 * The four AC-017(a) minimal forms are the RQ-3 byte-exact 13 / 55 / 319 / 336
 * character here-string fixtures (`spec-rq3-ledger-20261014.md` §2.3). The
 * rq1 replay loads the cached real command text when present (the untracked
 * research corpus) and otherwise falls back to reduced inline fixtures of the
 * same shape — the assertion is identical either way.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
	appendUnresolvedWriteEvent,
	diffLedger,
	formatUnresolvedWriteEvent,
	parseUnresolvedWriteEvents,
	parseWriteFileEvents,
} from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import {
	type BashWriteScopeConfig,
	checkBashWriteScopeTarget,
	classifyLedgerTargets,
	extractBashWriteCandidates,
	stripDataRegions,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const CACHED_CORPUS = path.join(REPO_ROOT, ".agenticdoc", "mw-worker-output-contract", "workers", "woc-rq3-ledger");

// ── AC-017(a): the four RQ-3 minimal here-string forms ──────────────────────

const MIN13 = "@'\n'-> `:1175";
const RQ2_55 = "$py = @'\n ('-> `:1175 release`', '-> `:1184 release`'),";
const RQ3_319 = [
	"$code = @'",
	"[VERIFY] RQ-W3: self_guard_hit=1 (xkey-gate-guard blocked this worker's own evidence-write command: quote-of-autopilot-dir plus PowerShell delete cmdlet inside here-string, a false positive; bypassed by splitting the quoted literal)",
	'"""',
	'CHUNK = CHUNK.replace("<AUTOPILOT_DIR>", ".agenticdoc/_aut" + "opilot")',
].join("\n");
const RQ3_336 = `${RQ3_319}\n$code | python -`;

const AC_017A_FORMS: ReadonlyArray<readonly [string, string]> = [
	["13", MIN13],
	["55", RQ2_55],
	["319", RQ3_319],
	["336", RQ3_336],
];

describe("AC-017(a) — data regions are stripped before the lexer", () => {
	it("the four minimal forms are the byte-exact 13/55/319/336 fixtures", () => {
		expect(MIN13).toHaveLength(13);
		expect(RQ2_55).toHaveLength(55);
		expect(RQ3_319).toHaveLength(319);
		expect(RQ3_336).toHaveLength(336);
		console.log(`[VERIFY] AC-017(a) fixture_lengths=13,55,319,336`);
	});

	it("each form produces zero candidates and zero ledger events", () => {
		const rows: string[] = [];
		for (const [label, form] of AC_017A_FORMS) {
			const candidates = extractBashWriteCandidates(form);
			rows.push(`${label}:${candidates.length}`);
			expect(candidates, `candidates ${label}`).toEqual([]);
			expect(classifyLedgerTargets(form), `ledger ${label}`).toEqual({ recorded: [], unresolved: [] });
		}
		console.log(`[VERIFY] AC-017(a) candidate_counts=${rows.join(",")}`);
	});

	it("stripDataRegions is an independently testable stage", () => {
		// The here-string region (including the `->` body) is gone from the
		// lexical input; the surviving text is the inert prefix.
		expect(stripDataRegions(MIN13)).not.toContain("->");
		expect(stripDataRegions(RQ2_55)).not.toContain("1175");
		// A heredoc body is data too, and the opener line's redirect survives.
		expect(stripDataRegions("cat <<EOF > out.md\nbody > notafile\nEOF\n")).not.toContain("notafile");
		expect(classifyLedgerTargets("cat <<EOF > out.md\nbody > notafile\nEOF\n")).toEqual({
			recorded: ["out.md"],
			unresolved: [],
		});
	});
});

// ── AC-017(b): the `net-file-api` branch ─────────────────────────────────────

describe("AC-017(b) — System.IO.File writes extract exactly once", () => {
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

	it("the single-command literal value environment resolves $var; an unbound $var is unresolved", () => {
		expect(classifyLedgerTargets('$path = "evidence/x.md"\n[System.IO.File]::WriteAllText($path, $c)')).toEqual({
			recorded: ["evidence/x.md"],
			unresolved: [],
		});
		expect(classifyLedgerTargets("$p = $args[0]\n[System.IO.File]::AppendAllText($p, $c)")).toEqual({
			recorded: [],
			unresolved: [{ pattern: "net-file-api", target: "$p" }],
		});
	});

	it("ReadAllText stays a read (no candidate, no event)", () => {
		expect(extractBashWriteCandidates('[System.IO.File]::ReadAllText("src/a.ts")')).toEqual([]);
	});

	it("a resolved .NET write is exactly one [WRITE_FILE] event, not the old 0", () => {
		const command = '$path = "evidence/x.md"\n[System.IO.File]::WriteAllText($path, $c)';
		const classification = classifyLedgerTargets(command);
		expect(classification.recorded).toEqual(["evidence/x.md"]);
		const eventLines = classification.recorded.map((target) => `[WRITE_FILE] path=${target}\n`).join("");
		expect(parseWriteFileEvents(eventLines)).toEqual(["evidence/x.md"]);
	});
});

// ── AC-017(c): the real rq1 blocked commands now replay as allow=2 deny=0 ────

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

/** The production guard sequence (worker-mode.ts `pi.on("tool_call")`): first
 * blocked candidate ends the command's judgement; `allow-unknown` is audited and
 * continued. `allowDetermined` counts the allowed candidates. */
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

/** Reduced inline analogues of the three blocked rq1 commands (same shape: two
 * `.NET` writes with a here-string body carrying `--glob`, one bare
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

/** The three real rq1 commands from the cached session corpus (indices 54 / 112
 * / 111 of `rq1-allbash.json`), or `undefined` on a clean checkout. */
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

describe("AC-017(c) — the `--glob` here-string no longer denies the real writes", () => {
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

	it("no candidate target is flag-like, backtick-bearing or newline-bearing", () => {
		for (const [label, form] of AC_017A_FORMS) {
			for (const candidate of extractBashWriteCandidates(form)) {
				expect(candidate.target.startsWith("-"), label).toBe(false);
				expect(candidate.target.includes("`"), label).toBe(false);
				expect(candidate.target.includes("\n"), label).toBe(false);
			}
		}
	});
});

// ── AC-008: real rq2 / rq3 command text, and the rq1 write form ─────────────

function cachedCommands(file: string): readonly string[] | undefined {
	const full = path.join(CACHED_CORPUS, file);
	if (!fs.existsSync(full)) return undefined;
	const rows = JSON.parse(fs.readFileSync(full, "utf8")) as Array<{ command?: unknown }>;
	const commands = rows.map((row) => row.command).filter((value): value is string => typeof value === "string");
	return commands.length > 0 ? commands : undefined;
}

describe("AC-008 — real enforcement/safety command text yields zero false [WRITE_FILE]", () => {
	it("rq2 / rq3 minimal forms extract nothing and record no path", () => {
		const rows: string[] = [];
		for (const [label, form] of [
			["rq2-55", RQ2_55],
			["rq3-319", RQ3_319],
			["rq3-336", RQ3_336],
		] as const) {
			const candidates = extractBashWriteCandidates(form);
			rows.push(`${label}:${candidates.length}`);
			expect(candidates, label).toEqual([]);
			expect(classifyLedgerTargets(form), label).toEqual({ recorded: [], unresolved: [] });
		}
		console.log(`[VERIFY] AC-008 minimized_false_rows=${rows.join(",")}`);
	});

	it("all cached rq2 / rq3 commands extract no false target", () => {
		const rq2 = cachedCommands("rq2-cmd.json");
		const rq3 = cachedCommands("rq3-cmd.json");
		if (rq2 === undefined || rq3 === undefined) {
			console.log("[VERIFY] AC-008 real corpus unavailable — inline minimal forms asserted above");
			return;
		}
		for (const command of [...rq2, ...rq3]) {
			for (const candidate of extractBashWriteCandidates(command)) {
				expect(candidate.target.startsWith("-")).toBe(false);
				expect(candidate.target.includes("`")).toBe(false);
				expect(candidate.target.includes("\n")).toBe(false);
			}
			expect(classifyLedgerTargets(command).recorded.filter((target) => target.startsWith("-"))).toEqual([]);
		}
		console.log(`[VERIFY] AC-008 real_corpus rq2=${rq2.length} rq3=${rq3.length} false_targets=0`);
	});

	it("a python-heredoc write to evidence/** is unjudgeable, not a silent zero-row green", () => {
		// The write form named by AC-008: a here-string payload piped into
		// `python -`. The extractor cannot see inside the payload, so there is no
		// `[WRITE_FILE]` event — and a declaration must therefore surface as
		// `unjudgeable` (never as a clean pass).
		const command = ["$code = @'", "open('evidence/research/out-20261014.md', 'w')", "'@", "$code | python -"].join(
			"\n",
		);
		expect(extractBashWriteCandidates(command)).toEqual([]);
		expect(classifyLedgerTargets(command)).toEqual({ recorded: [], unresolved: [] });

		const declared = ".agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md";
		expect(fs.existsSync(path.join(REPO_ROOT, declared))).toBe(true);
		const reportText = [
			"## 结论",
			"",
			"done",
			"",
			"## 改动清单",
			"",
			`- ${declared} — 新增证据`,
			"",
			"## 残留与未验证",
			"",
			"none",
		].join("\n");
		const ledger = diffLedger(reportText, "", { projectRoot: REPO_ROOT });
		console.log(`[VERIFY] AC-008 python_heredoc unjudgeable=${ledger.unjudgeable} extra=[${ledger.extra.join(",")}]`);
		expect(ledger.unjudgeable).toBe(true);
		expect(ledger.extra).toEqual([]);
	});

	it("the rq1 .NET write form now records exactly one event and no false path", () => {
		const command = [
			'$path = ".agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md"',
			"$enc = New-Object System.Text.UTF8Encoding($false)",
			"$part = @'",
			"rg -n --no-files-with-matches --glob '!node_modules' .",
			"'@",
			"[System.IO.File]::WriteAllText($path, $part, $enc)",
		].join("\n");
		expect(classifyLedgerTargets(command)).toEqual({
			recorded: [".agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md"],
			unresolved: [],
		});
	});
});

// ── AC-017(d): unjudgeable is derived from USABLE events ────────────────────

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

describe("AC-017(d) — a garbage event cannot close the unjudgeable gate", () => {
	const opts = { projectRoot: REPO_ROOT };

	it("a garbage `[WRITE_FILE]` line leaves the run unjudgeable (was false)", () => {
		const trace = "[WRITE_FILE] path=`:1175\n";
		// The OLD gate was `recorded.length === 0`; this raw count is what closed
		// it (documented before: unjudgeable=false for this exact trace).
		const rawRecorded = parseWriteFileEvents(trace);
		const ledger = diffLedger(report([DECLARED]), trace, opts);
		console.log(
			`[VERIFY] AC-017(d) garbage_event raw_recorded=${rawRecorded.length} ` +
				`old_gate_closed=${rawRecorded.length > 0} new_unjudgeable=${ledger.unjudgeable}`,
		);
		expect(rawRecorded).toEqual(["`:1175"]);
		expect(ledger.unjudgeable).toBe(true);
		expect(ledger.extra).toEqual([]);
	});

	it("an `[WRITE_UNRESOLVED]`-only trace stays unjudgeable (not a pass, not a false red)", () => {
		const trace = `${formatUnresolvedWriteEvent("net-file-api", "$p")}\n`;
		const ledger = diffLedger(report([DECLARED]), trace, opts);
		expect(ledger.unjudgeable).toBe(true);
		expect(ledger.extra).toEqual([]);
	});

	it("a usable `[WRITE_FILE]` for the declared file is green", () => {
		const ledger = diffLedger(report([DECLARED]), `[WRITE_FILE] path=${DECLARED}\n`, opts);
		expect(ledger.unjudgeable).toBe(false);
		expect(ledger.extra).toEqual([]);
	});

	it("a zero-event trace with a declaration stays unjudgeable (regression lock)", () => {
		const ledger = diffLedger(report([DECLARED]), "", opts);
		expect(ledger.unjudgeable).toBe(true);
	});

	it("a zero-event trace with no declaration stays trivially green", () => {
		const ledger = diffLedger(report([]), "", opts);
		expect(ledger.unjudgeable).toBe(false);
		expect(ledger.extra).toEqual([]);
	});
});

// ── the new event grammar (AC-017 compatibility statement) ──────────────────

describe("WRITE_UNRESOLVED event grammar", () => {
	it("formats, appends and parses back, folding newlines to one physical line", () => {
		expect(formatUnresolvedWriteEvent("net-file-api", "$p")).toBe(
			"[WRITE_UNRESOLVED] pattern=net-file-api target=$p",
		);
		const line = formatUnresolvedWriteEvent("redirect", "a\nb");
		expect(line).not.toContain("\n");
		expect(parseUnresolvedWriteEvents(`${line}\n`)).toEqual([{ pattern: "redirect", target: "a\\nb" }]);
	});

	it("appends best-effort and is invisible to the [WRITE_FILE] parser", () => {
		const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwoc-t02-"));
		try {
			const tracePath = path.join(dir, "trace.log");
			appendUnresolvedWriteEvent(tracePath, "net-file-api", "$p");
			appendUnresolvedWriteEvent(tracePath, "redirect", "a\nb");
			const text = fs.readFileSync(tracePath, "utf8");
			expect(text.split("\n").filter((l) => l.startsWith("[WRITE_UNRESOLVED]"))).toHaveLength(2);
			// The legacy parser only sees its own grammar.
			expect(parseWriteFileEvents(text)).toEqual([]);
			expect(parseUnresolvedWriteEvents(text)).toHaveLength(2);
		} finally {
			fs.rmSync(dir, { recursive: true, force: true });
		}
	});
});
