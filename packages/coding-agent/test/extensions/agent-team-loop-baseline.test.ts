/**
 * Golden baseline for the CURRENT target-config behavior on the TS side
 * (mw-target-partition T-00, spec AC-016, design D-011 + VC-016).
 *
 * Recorded BEFORE any partition implementation lands, mirroring the Python
 * baseline in packages/multi-workers/test/test_target_baseline.py (the dual
 * sample yml DUAL_YML below is byte-for-byte the same — keep both in sync):
 *
 *   a. resolveWorkspaceConfig projection — the 10 v1 fields
 *      (mode/controlRoot/gameRoot/engineRoot/vcs/uproject/toolchain/ignore/
 *      contract/source), toolchain/ignore/contract serialized by value.
 *   d. task-dispatcher profile injection block — the COMPLETE text from the
 *      PROFILE_MARK marker line to the end of the file, produced by the real
 *      dispatchTask() on a minimal task.md. (The marker literal is
 *      duplicated here on purpose: task-dispatcher keeps it module-private,
 *      and this test must not import partition-era symbols.)
 *   render. renderToolchainCommand results — the sample's toolchain commands
 *      (dual) and a fixed {game} template (single: {game} === controlRoot).
 *
 * Golden protocol (AC-016): a missing golden file is written and the test
 * PASSES with a "RECORDED" line; an existing golden is compared BYTE-EXACT
 * after replacing the sample control root's absolute path with "<CTRL>" —
 * everything else must match to the byte. A mismatch prints a diff summary
 * and fails the test. To re-record a baseline, delete the golden file and
 * re-run.
 *
 * The sample places game/engine/docs under the control root and uses
 * RELATIVE yml roots, so every recorded path normalizes to <CTRL>/... and
 * the golden stays machine-independent.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import {
	renderToolchainCommand,
	resolveWorkspaceConfig,
	targetYmlPath,
} from "../../src/extensions/agent-team-loop/shared/target-config.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const GOLDEN_DIR = fileURLToPath(new URL("./golden/target-baseline", import.meta.url));
const CTRL = "<CTRL>";

/** task-dispatcher's PROFILE_MARK (module-private; duplicated so the golden
 * slice can locate the injected block without importing new symbols). */
const PROFILE_MARK = "<!-- mw-profile: v1 -->";

/** Mirrors DUAL_YML in packages/multi-workers/test/test_target_baseline.py
 * byte-for-byte (AC-016 cross-side sample contract). */
const DUAL_YML = [
	"# mw-target-partition AC-016 baseline sample: full v1 dual target.yml.",
	"mode: dual",
	"game: game",
	"engine: engine",
	"vcs: git",
	"uproject: MyGame.uproject",
	"toolchain:",
	'  build_editor: \'"{engine}/Engine/Build/BatchFiles/Build.bat" MyGameEditor Win64 Development -project="{uproject}"\'',
	"  regen: 'python {game}/Tools/regen.py --engine {engine}'",
	"ignore:",
	"  deny_globs:",
	'    - "**/*.uasset"',
	'    - "**/DerivedDataCache/**"',
	"contract:",
	"  forbidden_paths:",
	'    - "**/Generated/*"',
	"  conventions: |",
	"    Line one of the conventions.",
	"    Line two of the conventions.",
	"  docs:",
	"    - docs/contract-notes.md",
	"",
].join("\n");

/** The 10 legacy (v1) fields the AC-016 projection covers, in order. */
const PROJECTION_KEYS = [
	"mode",
	"controlRoot",
	"gameRoot",
	"engineRoot",
	"vcs",
	"uproject",
	"toolchain",
	"ignore",
	"contract",
	"source",
] as const;

interface Project {
	/** Control workspace root (owns .agenticdoc and target.yml). */
	control: string;
	/** The .agenticdoc dir (WorkerStore + dispatch scan root). */
	agenticdoc: string;
	/** realpath-normalized control root (matches resolveWorkspaceConfig). */
	realControl: string;
}

function mkProject(prefix: string): Project {
	const control = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	const agenticdoc = path.join(control, ".agenticdoc");
	fs.mkdirSync(agenticdoc);
	return { control, agenticdoc, realControl: fs.realpathSync.native(control) };
}

function writeDualSample(control: string): void {
	fs.mkdirSync(path.join(control, "game"));
	fs.writeFileSync(path.join(control, "game", "MyGame.uproject"), "{}", "utf8");
	fs.mkdirSync(path.join(control, "engine"));
	fs.mkdirSync(path.join(control, "docs"), { recursive: true });
	fs.writeFileSync(path.join(control, "docs", "contract-notes.md"), "# contract notes\n", "utf8");
	fs.writeFileSync(targetYmlPath(control), DUAL_YML, "utf8");
}

/** Replace the sample control root's absolute path with <CTRL>; every other
 * byte must match exactly (AC-016 path normalization). */
function normalizeValue(value: unknown, realControl: string): unknown {
	if (typeof value === "string") return value.split(realControl).join(CTRL);
	if (Array.isArray(value)) return value.map((v) => normalizeValue(v, realControl));
	if (value !== null && typeof value === "object") {
		const out: Record<string, unknown> = {};
		for (const [k, v] of Object.entries(value)) out[k] = normalizeValue(v, realControl);
		return out;
	}
	return value;
}

/** Dispatch a minimal task.md through the real injection path and return the
 * injected file's text. */
async function dispatchMinimalTask(project: Project, taskKey: string, body: string): Promise<string> {
	const taskDir = path.join(project.agenticdoc, "_scratch", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	const md = path.join(taskDir, "task.md");
	fs.writeFileSync(md, body, "utf8");
	await dispatchTask(
		{ taskKey, status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
		new WorkerStore(project.agenticdoc),
	);
	return fs.readFileSync(md, "utf8");
}

/** Slice the profile injection block: PROFILE_MARK line to end of file. */
function profileBlockOf(text: string): string | null {
	const mark = text.indexOf(PROFILE_MARK);
	return mark === -1 ? null : text.slice(mark);
}

/** Record-if-missing / byte-exact-compare golden gate (AC-016). */
function goldenCheck(name: string, record: Record<string, unknown>): "RECORDED" | "MATCH" {
	fs.mkdirSync(GOLDEN_DIR, { recursive: true });
	const file = path.join(GOLDEN_DIR, `${name}.json`);
	const text = `${JSON.stringify(record, null, 2)}\n`;
	const rel = `test/extensions/golden/target-baseline/${name}.json`;
	if (!fs.existsSync(file)) {
		fs.writeFileSync(file, text, "utf8"); // UTF-8, no BOM
		console.log(`[BASELINE] RECORDED: ${rel} (${Object.keys(record).length - 1} entries)`);
		return "RECORDED";
	}
	const golden = fs.readFileSync(file, "utf8");
	if (golden === text) {
		console.log(`[BASELINE] MATCH: ${rel}`);
		return "MATCH";
	}
	const goldenLines = golden.split("\n");
	const currentLines = text.split("\n");
	const diff: string[] = [];
	for (let i = 0; i < Math.max(goldenLines.length, currentLines.length) && diff.length < 40; i++) {
		if (goldenLines[i] !== currentLines[i]) {
			diff.push(
				`line ${i + 1}: golden=${JSON.stringify(goldenLines[i])} current=${JSON.stringify(currentLines[i])}`,
			);
		}
	}
	console.error(`[BASELINE] MISMATCH: ${rel}\n${diff.join("\n")}`);
	throw new Error(`target baseline ${name} differs from the golden file (AC-016)`);
}

describe("target baseline golden (mw-target-partition AC-016)", () => {
	const savedEnv: Record<string, string | undefined> = {};
	const envKeys = ["MW_TARGET_GAME", "MW_TARGET_ENGINE"];
	let control = "";

	beforeEach(() => {
		// No env overrides may leak into the recorded resolution.
		for (const key of envKeys) {
			savedEnv[key] = process.env[key];
			delete process.env[key];
		}
	});

	afterEach(() => {
		for (const key of envKeys) {
			if (savedEnv[key] === undefined) delete process.env[key];
			else process.env[key] = savedEnv[key];
		}
		if (control !== "") {
			fs.rmSync(control, { recursive: true, force: true });
			control = "";
		}
	});

	it("dual sample: projection / profile block / toolchain render", async () => {
		const project = mkProject("atl-base-dual-");
		control = project.control;
		writeDualSample(project.control);
		const config = resolveWorkspaceConfig(project.control);

		const injected = await dispatchMinimalTask(
			project,
			"ap-baseline-dual",
			"type: coding\n\nBaseline dual sample task.\n",
		);
		const profileBlock = profileBlockOf(injected);
		expect(profileBlock).not.toBeNull(); // dual always injects (D-005)

		const record: Record<string, unknown> = {
			sample: "dual",
			a_projection: Object.fromEntries(PROJECTION_KEYS.map((key) => [key, config[key]])),
			d_profile_block: profileBlock,
			render_toolchain: Object.fromEntries(
				Object.keys(config.toolchain)
					.sort()
					.map((name) => [name, renderToolchainCommand(config.toolchain[name], config)]),
			),
		};
		const status = goldenCheck("dual", normalizeValue(record, project.realControl) as Record<string, unknown>);
		expect(status === "RECORDED" || status === "MATCH").toBe(true);
		console.log(`[VERIFY] VC-016: baseline_dual=${status === "MATCH" ? "identical" : "recorded"}`);
	});

	it("single sample: no file, no injection, {game} renders to the control root", async () => {
		const project = mkProject("atl-base-single-");
		control = project.control;
		const config = resolveWorkspaceConfig(project.control);

		const body = "type: coding\n\nBaseline single sample task.\n";
		const injected = await dispatchMinimalTask(project, "ap-baseline-single", body);
		const profileBlock = profileBlockOf(injected);
		// No target.yml, no env: nothing to inject — byte-identical task.md.
		expect(profileBlock).toBeNull();
		expect(injected).toBe(body);

		const record: Record<string, unknown> = {
			sample: "single",
			a_projection: Object.fromEntries(PROJECTION_KEYS.map((key) => [key, config[key]])),
			d_profile_block: profileBlock,
			render_toolchain: { "echo {game}": renderToolchainCommand("echo {game}", config) },
		};
		const status = goldenCheck("single", normalizeValue(record, project.realControl) as Record<string, unknown>);
		expect(status === "RECORDED" || status === "MATCH").toBe(true);
		console.log(`[VERIFY] VC-016: baseline_single=${status === "MATCH" ? "identical" : "recorded"}`);
	});
});
