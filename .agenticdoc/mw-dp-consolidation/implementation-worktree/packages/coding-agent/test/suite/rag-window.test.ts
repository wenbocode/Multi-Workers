/**
 * rag-window.test.ts — pi-window RAG surface + `skill.dir` parity
 * (mw-rag-window-parity T-1).
 *
 * T-1 covers the cross-language `skill.dir` contract (VC-301..VC-304): a
 * missing/`null` `dir` means the control workspace root, and the parsed value
 * stays `null` — never `"."` — so the locked TS==Python fingerprint stays
 * byte-identical. T-2/T-3 append the `/mw rag` and `/mw doctor` cases to this
 * same file; keep the existing tests below untouched when appending.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import {
	formatDoctorReport,
	formatRagDoctorLine,
	formatRagOutput,
	MW_COMMAND_DESCRIPTION,
	parseRagArgs,
	RAG_FULL_OUTPUT_HINT,
	RAG_OUTPUT_MAX_LINES,
	runMwRagCommand,
	shouldShowRagDoctorRow,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";
import {
	ENV_RAG_SERVERS_FILE,
	ENV_RAG_SERVERS_HOME,
	loadRagConfig,
	RagConfigError,
} from "../../src/extensions/agent-team-loop/rag/config.ts";
import { resolveCliDir } from "../../src/extensions/agent-team-loop/rag/tools.ts";
import type { DoctorJson } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { RAG_SUBCOMMANDS, ragMw } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";

/* The suite config swallows console.log from green tests; write the evidence
 * line straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

const tmpDirs: string[] = [];
const originalServersFile = process.env[ENV_RAG_SERVERS_FILE];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

afterEach(() => {
	if (originalServersFile === undefined) delete process.env[ENV_RAG_SERVERS_FILE];
	else process.env[ENV_RAG_SERVERS_FILE] = originalServersFile;
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/**
 * Build a control root whose project layer declares one `skill` server with
 * the given `skill` sub-block lines (YAML, 6-space indent already applied).
 * The machine layer is pointed at a non-existent file, so only the project
 * layer contributes.
 */
function skillRoot(skillLines: string[]): string {
	const root = mkdtemp("mw-rag-window-");
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	const lines = ["servers:", "  S:", "    transport: skill", "    skill:", ...skillLines];
	fs.writeFileSync(path.join(root, ".mw", "rag-servers.yml"), `${lines.join("\n")}\n`, "utf-8");
	fs.writeFileSync(path.join(root, ".agenticdoc", "target.yml"), "rag:\n  enabled: [S]\n", "utf-8");
	process.env[ENV_RAG_SERVERS_FILE] = path.join(root, "absent-machine.yml");
	return root;
}

describe("skill.dir parsing parity (VC-301..VC-303)", () => {
	it("VC-301: a missing skill.dir parses to null", () => {
		const root = skillRoot(["      cli_entry: scripts/cli.py"]);
		const config = loadRagConfig(root);
		const skill = config.servers.S.skill;
		expect(skill).not.toBeNull();
		expect(skill?.dir).toBeNull();
		verify(`[VERIFY] VC-301: dir=${String(skill?.dir)} parse=ok`);
	});

	it("VC-302: an explicit skill.dir: null parses to null", () => {
		const root = skillRoot(["      dir: null", "      cli_entry: scripts/cli.py"]);
		const config = loadRagConfig(root);
		const skill = config.servers.S.skill;
		expect(skill?.dir).toBeNull();
		verify(`[VERIFY] VC-302: dir=${String(skill?.dir)} parse=ok`);
	});

	it("VC-303: an empty skill.dir stays invalid-shape and names skill.dir", () => {
		const root = skillRoot(['      dir: ""', "      cli_entry: scripts/cli.py"]);
		let caught: unknown;
		try {
			loadRagConfig(root);
		} catch (error) {
			caught = error;
		}
		expect(caught).toBeInstanceOf(RagConfigError);
		const error = caught as RagConfigError;
		expect(error.kind).toBe("invalid-shape");
		expect(error.message).toContain("skill.dir");
		verify(`[VERIFY] VC-303: dir="" kind=${error.kind} mentions_skill_dir=${error.message.includes("skill.dir")}`);
	});
});

describe("resolveCliDir parity (VC-304)", () => {
	it("VC-304: null maps to the control root and an explicit dir resolves against it", () => {
		const root = mkdtemp("mw-rag-window-dir-");
		const explicit = path.resolve(root, "skills/x");
		const nullMapsToRoot = resolveCliDir(root, null) === root;
		expect(nullMapsToRoot).toBe(true);
		expect(resolveCliDir(root, "skills/x")).toBe(explicit);
		verify(`[VERIFY] VC-304: null_to_root=${nullMapsToRoot} explicit=${resolveCliDir(root, "skills/x")}`);
	});
});

// ── T-2: pi-window `/mw rag` thin wrapper (VC-306..VC-308, VC-311) ──────────
//
// The window side owns no RAG semantics: parseRagArgs decides whether a spawn
// is worth it (and never spawns for an unknown/empty sub), formatRagOutput maps
// the Python exit code 0/1/2 to a notify level and shortens long output. Both
// are pure; runMwRagCommand takes an injectable runner so the spawn-free path
// is proven with a counting stub.

interface RagNotify {
	message: string;
	type: string;
}

function fakeRagCtx(): { ctx: ExtensionCommandContext; notifications: RagNotify[] } {
	const notifications: RagNotify[] = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string, type?: string) => {
				notifications.push({ message, type: type ?? "" });
			},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

describe("/mw rag argument parsing (VC-306)", () => {
	it("VC-306: returns sub + verbatim rest for a known sub, usage for unknown", () => {
		const list = parseRagArgs("list");
		const audit = parseRagArgs("audit --key K");
		const bogus = parseRagArgs("bogus");
		expect(list).toEqual({ sub: "list", rest: [] });
		expect(audit).toEqual({ sub: "audit", rest: ["--key", "K"] });
		expect("usage" in bogus).toBe(true);
		const usage = "usage" in bogus ? bogus.usage : "";
		const allFive = RAG_SUBCOMMANDS.every((sub) => usage.includes(sub));
		expect(allFive).toBe(true);
		verify(
			`[VERIFY] VC-306: list=${JSON.stringify(list)} audit=${JSON.stringify(audit)} bogus=usage(all_5=${allFive})`,
		);
	});

	it("VC-306: empty and whitespace-only input also yield usage", () => {
		for (const raw of ["", "   ", "\t"]) {
			const parsed = parseRagArgs(raw);
			expect("usage" in parsed).toBe(true);
		}
	});
});

describe("/mw rag dispatch never spawns on an unknown sub (VC-307)", () => {
	it("VC-307: unknown/empty sub returns usage and calls no runner", async () => {
		let calls = 0;
		const { ctx, notifications } = fakeRagCtx();
		for (const raw of ["", "bogus", "  "]) {
			await runMwRagCommand(ctx, "/proj", raw, () => {
				calls += 1;
				return { ok: true, code: 0, output: "spawned" };
			});
		}
		expect(calls).toBe(0);
		expect(notifications.length).toBe(3);
		expect(notifications.every((n) => n.type === "warning")).toBe(true);
		expect(notifications.every((n) => RAG_SUBCOMMANDS.every((sub) => n.message.includes(sub)))).toBe(true);
		verify(`[VERIFY] VC-307: unknown_sub_runner_calls=${calls} usage_notices=${notifications.length}`);
	});

	it("VC-307: a known sub forwards sub + rest through the runner", async () => {
		const calls: Array<[string, string[]]> = [];
		const { ctx, notifications } = fakeRagCtx();
		await runMwRagCommand(ctx, "/proj", "audit --key K", (projectDir, args) => {
			calls.push([projectDir, args]);
			return { ok: false, code: 1, output: "audit: 2 findings" };
		});
		expect(calls).toEqual([["/proj", ["audit", "--key", "K"]]]);
		expect(notifications).toEqual([{ message: "audit: 2 findings", type: "warning" }]);
	});
});

describe("/mw rag output formatting (VC-308)", () => {
	it("VC-308: exit code 0/1/2 maps to info/warning/error", () => {
		const levels = [
			formatRagOutput("out", 0).level,
			formatRagOutput("out", 1).level,
			formatRagOutput("out", 2).level,
		];
		expect(levels).toEqual(["info", "warning", "error"]);
		verify(`[VERIFY] VC-308: level0=${levels[0]} level1=${levels[1]} level2=${levels[2]}`);
	});

	it("VC-308: >30 lines truncates and appends the full-command hint; exactly 30 stays intact", () => {
		const lines = Array.from({ length: RAG_OUTPUT_MAX_LINES + 5 }, (_, i) => `line ${i + 1}`);
		const truncated = formatRagOutput(lines.join("\n"), 0);
		const shown = truncated.text.split("\n");
		expect(shown.length).toBe(RAG_OUTPUT_MAX_LINES + 1);
		expect(truncated.text).toContain("line 1");
		expect(truncated.text).toContain(`line ${RAG_OUTPUT_MAX_LINES}`);
		expect(truncated.text).not.toContain(`line ${RAG_OUTPUT_MAX_LINES + 1}`);
		expect(truncated.text).toContain(RAG_FULL_OUTPUT_HINT);

		const exact = lines.slice(0, RAG_OUTPUT_MAX_LINES).join("\n");
		expect(formatRagOutput(exact, 0).text).toBe(exact);
		verify(
			`[VERIFY] VC-308: truncated_lines=${shown.length} hint_present=${truncated.text.includes(
				RAG_FULL_OUTPUT_HINT,
			)} exact30_intact=true`,
		);
	});
});

describe("/mw command description documents rag (VC-311)", () => {
	it("VC-311: the registered description names the rag subcommand", () => {
		expect(MW_COMMAND_DESCRIPTION).toContain("rag");
		verify(`[VERIFY] VC-311: mw_description_has_rag=${MW_COMMAND_DESCRIPTION.includes("rag")}`);
	});
});

// ── T-3: `/mw doctor` RAG row (VC-309, VC-310) ──────────────────────────────
//
// The window never re-renders the RAG section itself: `formatRagDoctorLine` is
// a pure mirror of `mw.py:_format_rag_doctor_line`, proven by feeding it the
// JSON half of one `mw.py doctor` run and comparing byte-for-byte against the
// `rag: ` line of the text half. The three fixtures cover the error branch, the
// empty-enabled branch, and the enabled + probe-unreachable branch.

/** Repo `packages/multi-workers` (the Python ground truth sources). */
const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
const MW_PY = path.join(MULTI_WORKERS_DIR, "mw.py");

/** Python + PyYAML availability probe: the parity run is skipped without them. */
const pythonAvailable = (() => {
	try {
		return (
			spawnSync(resolveRagPython(), ["-c", "import yaml; print(1)"], { encoding: "utf8", timeout: 10_000 })
				.status === 0
		);
	} catch {
		return false;
	}
})();

/**
 * A control root with a project RAG layer (`.mw/rag-servers.yml`) and a
 * `target.yml` `rag.enabled` list. The project layer is what makes doctor's
 * `exists: true`, so the text half prints its `rag: ` line.
 */
function doctorRoot(serversYml: string, enabled: string[]): string {
	const root = mkdtemp("mw-rag-doctor-");
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "rag-servers.yml"), serversYml, "utf-8");
	fs.writeFileSync(
		path.join(root, ".agenticdoc", "target.yml"),
		`rag:\n  enabled: [${enabled.join(", ")}]\n`,
		"utf-8",
	);
	return root;
}

/** Run `mw.py doctor` for a fixture, isolated from the real machine layer. */
function runDoctor(root: string, json: boolean): string {
	const env = {
		...process.env,
		[ENV_RAG_SERVERS_FILE]: path.join(root, "absent-machine.yml"),
		[ENV_RAG_SERVERS_HOME]: root,
	};
	const args = [MW_PY, "doctor", `--project=${root}`];
	if (json) args.push("--json");
	const result = spawnSync(resolveRagPython(), args, { encoding: "utf8", timeout: 60_000, env });
	if (result.error) throw new Error(`failed to spawn mw.py doctor: ${result.error.message}`);
	const stdout = result.stdout ?? "";
	if (json && !stdout.trim()) {
		throw new Error(`mw.py doctor --json produced no stdout (status=${result.status}): ${result.stderr ?? ""}`);
	}
	return stdout;
}

/** Whether one `mw.py doctor` text run printed a `rag: ` row. */
function hasRagTextRow(stdout: string): boolean {
	return stdout
		.replace(/\r\n/g, "\n")
		.split("\n")
		.some((line) => line.startsWith("rag: "));
}

describe("/mw doctor RAG row parity (VC-309)", () => {
	it.skipIf(!pythonAvailable)(
		"VC-309: renders byte-identical to the `mw.py doctor` text line for three configs",
		() => {
			const cases: Array<{ label: string; root: string }> = [
				{ label: "not-enabled", root: doctorRoot("servers: {}\n", []) },
				{
					label: "config-error",
					root: doctorRoot(
						"servers:\n  S:\n    transport: skill\n    adapter: v2\n    skill:\n      cli_entry: a.py\n",
						["S"],
					),
				},
				{
					label: "enabled-unreachable",
					root: doctorRoot("servers:\n  S:\n    transport: mcp\n    mcp:\n      url: http://127.0.0.1:19999/\n", [
						"S",
					]),
				},
			];
			const measured: string[] = [];
			for (const item of cases) {
				const report = JSON.parse(runDoctor(item.root, true)) as DoctorJson;
				if (!report.rag) throw new Error(`${item.label}: doctor JSON carried no rag section`);
				const tsLine = formatRagDoctorLine(report.rag);
				const pyLine = runDoctor(item.root, false)
					.replace(/\r\n/g, "\n")
					.split("\n")
					.find((line) => line.startsWith("rag: "));
				expect(pyLine).toBeDefined();
				expect(tsLine).toBe(pyLine);
				measured.push(`${item.label}[ts=py=${tsLine === pyLine}]"${tsLine}"`);
			}
			verify(`[VERIFY] VC-309: ${measured.join(" | ")}`);
		},
	);

	it.skipIf(!pythonAvailable)(
		"VC-309b: the render gate matches the Python gate for a project without RAG config",
		() => {
			const empty = mkdtemp("mw-rag-doctor-empty-");
			fs.mkdirSync(path.join(empty, ".agenticdoc"), { recursive: true });
			fs.writeFileSync(path.join(empty, ".agenticdoc", "target.yml"), "rag:\n  enabled: []\n", "utf-8");
			const emptyReport = JSON.parse(runDoctor(empty, true)) as DoctorJson;
			const emptyPyRow = hasRagTextRow(runDoctor(empty, false));
			const emptyTsRow = shouldShowRagDoctorRow(emptyReport.rag);
			expect(emptyPyRow).toBe(false);
			expect(emptyTsRow).toBe(false);

			const configured = doctorRoot("servers: {}\n", []);
			const configuredReport = JSON.parse(runDoctor(configured, true)) as DoctorJson;
			const configuredPyRow = hasRagTextRow(runDoctor(configured, false));
			const configuredTsRow = shouldShowRagDoctorRow(configuredReport.rag);
			expect(configuredPyRow).toBe(true);
			expect(configuredTsRow).toBe(true);

			verify(
				`[VERIFY] VC-309b: empty_py_row=${String(emptyPyRow)} empty_ts_row=${String(
					emptyTsRow,
				)} configured_py_row=${String(configuredPyRow)} configured_ts_row=${String(configuredTsRow)}`,
			);
		},
	);
});

describe("/mw doctor RAG row presence (VC-310)", () => {
	it("VC-310: a report without rag shows no rag row and never throws", () => {
		const text = formatDoctorReport({}, false);
		expect(text).not.toContain("rag:");
		verify(`[VERIFY] VC-310: no_rag_row=${!text.includes("rag:")} lines=${text.split("\n").length}`);
	});

	it("VC-310: a project without RAG config shows no row, matching the Python gate", () => {
		const inert: NonNullable<DoctorJson["rag"]> = { exists: false, enabled: [] };
		expect(shouldShowRagDoctorRow(undefined)).toBe(false);
		expect(shouldShowRagDoctorRow(inert)).toBe(false);
		expect(shouldShowRagDoctorRow({ exists: true, enabled: [] })).toBe(true);
		expect(shouldShowRagDoctorRow({ enabled: ["A"] })).toBe(true);
		const text = formatDoctorReport({ rag: inert }, false);
		expect(text).not.toContain("rag:");
		verify(
			`[VERIFY] VC-310: gate_absent=${String(shouldShowRagDoctorRow(undefined))} gate_inert=${String(
				shouldShowRagDoctorRow(inert),
			)} gate_exists=${String(shouldShowRagDoctorRow({ exists: true }))} gate_enabled=${String(
				shouldShowRagDoctorRow({ enabled: ["A"] }),
			)} rows=${text.split("\n").filter((line) => line.startsWith("rag: ")).length}`,
		);
	});

	it("VC-310: a report with a configured rag shows exactly one rag row", () => {
		const text = formatDoctorReport({ rag: { exists: true, enabled: [] } }, false);
		const ragLines = text.split("\n").filter((line) => line.startsWith("rag: "));
		expect(ragLines).toEqual(["rag: not enabled (skill unknown)"]);
		expect(text.match(/rag:/g) ?? []).toHaveLength(1);
		verify(`[VERIFY] VC-310: rag_rows=${ragLines.length} line="${ragLines[0]}"`);
	});
});

// Q-X-04: the window whitelist must not drift from the Python dispatcher. The
// gate report proved the two sets equal by reading both; this makes it
// automatic (a new `rag <sub>` in mw.py, or a typo here, now fails the suite).
describe("rag subcommand whitelist = mw.py _RAG_ACTIONS (Q-X-04)", () => {
	it("keeps RAG_SUBCOMMANDS identical to the Python dispatcher's keys", () => {
		const source = fs.readFileSync(path.join(MULTI_WORKERS_DIR, "mw.py"), "utf-8");
		// mw.py ships CRLF; split on the line break, not on "\n" alone, or the
		// closing brace never matches and the block swallows the whole file.
		const lines = source.split(/\r?\n/);
		const start = lines.findIndex((line) => line.startsWith("_RAG_ACTIONS") && line.includes("{"));
		expect(start).toBeGreaterThan(-1);
		const block: string[] = [];
		for (let i = start; i < lines.length; i += 1) {
			block.push(lines[i]);
			if (i > start && lines[i] === "}") break;
		}
		const pythonNames = [...block.join("\n").matchAll(/^\s+"([a-z][a-z_-]*)"\s*:/gm)].map((match) => match[1]).sort();
		const tsNames = [...RAG_SUBCOMMANDS].sort();
		expect(pythonNames.length).toBeGreaterThan(0);
		expect(pythonNames).toEqual(tsNames);
		verify(
			`[VERIFY] Q-X-04: py=${pythonNames.join(",")} ts=${tsNames.join(",")} equal=${String(
				JSON.stringify(pythonNames) === JSON.stringify(tsNames),
			)}`,
		);
	});
});

// T-3C: the pure functions cannot prove that the wrapper really spawns
// `mw.py rag <sub> --project=<controlRoot>`. A stub `MW_PY` script prints its
// argv and exits with a chosen code, so the concatenation and the 0/1/2
// propagation are pinned end to end (T-4 finding 1: counter-example B on
// `--project=.` left every existing test green).
describe("/mw rag spawn contract (VC-308b)", () => {
	it("forwards `rag <sub>` plus --project=<controlRoot> and keeps the exit code", () => {
		const root = mkdtemp("mw-rag-spawn-");
		const stub = path.join(root, "stub_mw.py");
		fs.writeFileSync(
			stub,
			[
				"import json, sys",
				"print(json.dumps(sys.argv[1:]))",
				"sys.exit(1 if '--fail' in sys.argv[1:] else 0)",
				"",
			].join("\n"),
			"utf-8",
		);
		const originalMwPy = process.env.MW_PY;
		process.env.MW_PY = stub;
		try {
			const zero = ragMw(root, ["list"]);
			expect(zero.code).toBe(0);
			expect(zero.ok).toBe(true);
			expect(JSON.parse(zero.output)).toEqual(["rag", "list", `--project=${root}`]);

			const one = ragMw(root, ["audit", "--fail"]);
			expect(one.code).toBe(1);
			expect(one.ok).toBe(false);
			expect(JSON.parse(one.output)).toEqual(["rag", "audit", "--fail", `--project=${root}`]);

			verify(
				`[VERIFY] VC-308b: argv0=${JSON.stringify(
					JSON.parse(zero.output),
				)} argv1_code=${one.code} ok0=${String(zero.ok)} ok1=${String(one.ok)}`,
			);
		} finally {
			if (originalMwPy === undefined) delete process.env.MW_PY;
			else process.env.MW_PY = originalMwPy;
		}
	});
});
