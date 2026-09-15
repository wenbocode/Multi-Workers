/**
 * Workspace-profile injection at TS dispatch time (mw-dual-workspace
 * Task 007, AC-007 / VC-013): dispatchTask augments a task.md with the
 * target.yml essentials (toolchain/ignore/contract) plus the control-root
 * path, and injects deny_globs frontmatter in the same format the Python
 * renderer produces — the worker stays task.md-self-contained.
 *
 * Fixture shape mirrors production: <control>/.agenticdoc/_scratch/workers/
 * <taskKey>/task.md with target.yml at <control>/.agenticdoc/target.yml
 * (controlRootFromTaskPath must peel all five levels to find the config).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { dispatchNewTasks } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import { controlRootFromTaskPath } from "../../src/extensions/agent-team-loop/shared/paths.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { parseTaskMd } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

interface Project {
	/** Control workspace root (owns .agenticdoc and target.yml). */
	control: string;
	/** The .agenticdoc dir (WorkerStore + dispatch scan root). */
	agenticdoc: string;
	/** realpath-normalized control root (matches resolveWorkspaceConfig). */
	realControl: string;
}

function mkProject(): Project {
	const control = fs.mkdtempSync(path.join(os.tmpdir(), "atl-profile-"));
	const agenticdoc = path.join(control, ".agenticdoc");
	fs.mkdirSync(agenticdoc);
	return { control, agenticdoc, realControl: fs.realpathSync.native(control) };
}

function writeScratchTask(project: Project, taskKey: string, body: string): string {
	const dir = path.join(project.agenticdoc, "_scratch", "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	const md = path.join(dir, "task.md");
	fs.writeFileSync(md, body, "utf8");
	return md;
}

function writeTargetYml(project: Project, body: string): void {
	fs.writeFileSync(path.join(project.agenticdoc, "target.yml"), body, "utf8");
}

/** yml body for a dual project with all three sections present. */
function fullYml(game: string, engine: string): string {
	return [
		"mode: dual",
		`game: '${game.replace(/\\/g, "/")}'`,
		`engine: '${engine.replace(/\\/g, "/")}'`,
		"toolchain:",
		'  build_editor: \'"{engine}/Build.bat" ProjectHEditor -project="{uproject}"\'',
		"ignore:",
		"  deny_globs:",
		'    - "**/*.uasset"',
		"contract:",
		'  forbidden_paths: ["**/Generated/*"]',
		"  conventions: |",
		"    No direct edits under Source/Generated.",
		"  docs:",
		"    - docs/contract-notes.md",
		"",
	].join("\n");
}

describe("workspace profile injection (mw-dual-workspace AC-007)", () => {
	const savedEnv: Record<string, string | undefined> = {};
	const envKeys = ["MW_TARGET_GAME", "MW_TARGET_ENGINE"];

	beforeEach(() => {
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
	});

	it("VC-013: injects toolchain/ignore/contract essentials + control root", async () => {
		const project = mkProject();
		const game = path.join(project.control, "game");
		const engine = path.join(project.control, "engine");
		fs.mkdirSync(game);
		fs.mkdirSync(engine);
		fs.writeFileSync(path.join(game, "ProjectH.uproject"), "{}", "utf8");
		writeTargetYml(project, fullYml(game, engine));
		const md = writeScratchTask(project, "ap-vc013", "type: coding\n\nBuild the editor.\n");
		const store = new WorkerStore(project.agenticdoc);

		await dispatchTask(
			{ taskKey: "ap-vc013", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			store,
		);

		const text = fs.readFileSync(md, "utf8");
		const realGame = fs.realpathSync.native(game);
		const realEngine = fs.realpathSync.native(engine);
		// Toolchain essentials: placeholders resolved, fail-closed render. The
		// template keeps its own `/` separator after substitution.
		expect(text).toContain(`- build_editor: "${realEngine}/Build.bat"`);
		expect(text).toContain(path.join(realGame, "ProjectH.uproject"));
		// Ignore essentials + frontmatter deny_globs (Py renderer format).
		expect(text).toContain("- **/*.uasset");
		expect(text).toContain("deny_globs:\n  - '**/*.uasset'");
		// Contract essentials + docs as reference (not inlined).
		expect(text).toContain("- forbidden paths: **/Generated/*");
		expect(text).toContain("No direct edits under Source/Generated.");
		expect(text).toContain(`- ${path.join(project.realControl, "docs", "contract-notes.md")}`);
		// Control-root reference (dual: cwd is the game root, the worker needs
		// the control path to reach the profile and coordination files).
		expect(text).toContain(`Control workspace: ${project.realControl}`);
		// The injected task.md still parses: worker sees the firewall.
		const meta = parseTaskMd(md);
		expect(meta.denyGlobs).toEqual(["**/*.uasset"]);

		console.log("[VERIFY] VC-013: toolchain-mark=true ignore-mark=true contract-mark=true");
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("section missing: renders what exists, never blocks the dispatch", async () => {
		const project = mkProject();
		const game = path.join(project.control, "game");
		fs.mkdirSync(game);
		writeTargetYml(
			project,
			["mode: dual", `game: '${game.replace(/\\/g, "/")}'`, "toolchain:", '  build: "echo {game}"', ""].join("\n"),
		);
		const md = writeScratchTask(project, "ap-partial", "type: coding\n\nPartial profile.\n");
		const store = new WorkerStore(project.agenticdoc);

		await dispatchTask(
			{ taskKey: "ap-partial", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			store,
		);
		const text = fs.readFileSync(md, "utf8");
		expect(text).toContain(`- build: echo ${fs.realpathSync.native(game)}`);
		expect(text).not.toContain("Context firewall");
		expect(text).not.toContain("Contract:");
		expect(store.readAll().map((e) => e.taskKey)).toEqual(["ap-partial"]);
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("single mode without target.yml: task.md byte-identical (snapshot)", async () => {
		const project = mkProject();
		const body = "type: coding\n\nPlain manual task.\n";
		const md = writeScratchTask(project, "ap-snap", body);
		const store = new WorkerStore(project.agenticdoc);

		await dispatchTask(
			{ taskKey: "ap-snap", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			store,
		);
		expect(fs.readFileSync(md, "utf8")).toBe(body);
		expect(store.readAll()).toHaveLength(1);
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("re-dispatch is idempotent: profile block appended once", async () => {
		const project = mkProject();
		writeTargetYml(project, 'mode: single\nignore:\n  deny_globs:\n    - "**/*.uasset"\n');
		const md = writeScratchTask(project, "ap-idem", "type: coding\n\nTask.\n");
		const store = new WorkerStore(project.agenticdoc);

		for (let i = 0; i < 2; i++) {
			await dispatchTask(
				{ taskKey: "ap-idem", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
				store,
			);
		}
		const text = fs.readFileSync(md, "utf8");
		expect(text.split("<!-- mw-profile: v1 -->").length - 1).toBe(1);
		expect(text.split("deny_globs:").length - 1).toBe(1);
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("task-level deny_globs is never overwritten", async () => {
		const project = mkProject();
		writeTargetYml(project, 'mode: single\nignore:\n  deny_globs:\n    - "**/*.uasset"\n');
		const md = writeScratchTask(project, "ap-own", "type: coding\ndeny_globs:\n  - 'Saved/**'\n\nTask.\n");
		const store = new WorkerStore(project.agenticdoc);

		await dispatchTask(
			{ taskKey: "ap-own", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			store,
		);
		const text = fs.readFileSync(md, "utf8");
		expect(text).toContain("  - 'Saved/**'");
		expect(text).not.toContain("*.uasset");
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("broken target.yml: dispatch refused via the scan, zero queue rows", async () => {
		const project = mkProject();
		writeTargetYml(project, "mode: [unclosed\n");
		writeScratchTask(project, "ap-brk", "type: coding\n\nTask.\n");
		const store = new WorkerStore(project.agenticdoc);

		await dispatchNewTasks(store, project.agenticdoc, { warnedKeys: new Set<string>() });
		expect(store.readAll()).toEqual([]); // fail-closed: nothing queued

		// Fixing the config unblocks the next scan (self-healing).
		writeTargetYml(project, "mode: single\n");
		await dispatchNewTasks(store, project.agenticdoc, { warnedKeys: new Set<string>() });
		expect(store.readAll().map((e) => e.taskKey)).toEqual(["ap-brk"]);
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("controlRootFromTaskPath anchors injection at the task's control root", async () => {
		const project = mkProject();
		// target.yml sits in the control root owning the task dir, not in cwd.
		writeTargetYml(project, 'mode: single\nignore:\n  deny_globs:\n    - "**/*.uasset"\n');
		const md = writeScratchTask(project, "ap-anchor", "type: coding\n\nTask.\n");
		expect(fs.realpathSync.native(controlRootFromTaskPath(md))).toBe(project.realControl);
		const store = new WorkerStore(project.agenticdoc);
		await dispatchTask(
			{ taskKey: "ap-anchor", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			store,
		);
		expect(fs.readFileSync(md, "utf8")).toContain("deny_globs:");
		fs.rmSync(project.control, { recursive: true, force: true });
	});
});
