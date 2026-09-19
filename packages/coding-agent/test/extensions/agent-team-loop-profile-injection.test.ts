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
import { fileURLToPath } from "node:url";
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

describe("partition profile injection (mw-target-partition AC-007/AC-019)", () => {
	const savedEnv: Record<string, string | undefined> = {};
	const envKeys = ["MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"];

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

	/** yml body for a full partition project (every AC-007 section present). */
	function partitionYml(parent: string, partition: string, sdk: string): string {
		const q = (p: string) => `'${p.replace(/\\/g, "/")}'`;
		return [
			"active: partition",
			"partition:",
			`  parent: ${q(parent)}`,
			`  partition: ${q(partition)}`,
			"  roots:",
			`    sdk: ${q(sdk)}`,
			"  toolchain:",
			"    build: 'make -C {partition} SDK={sdk}'",
			"  ignore:",
			"    deny_globs:",
			'      - "**/*.tmp"',
			"  contract:",
			'    forbidden_paths: ["**/Generated/*"]',
			"    conventions: |",
			"      Keep the shard self-contained.",
			"    docs:",
			"      - docs/contract-notes.md",
			"",
		].join("\n");
	}

	function dualBlockYml(game: string): string {
		return ["active: dual", "dual:", `  game: '${game.replace(/\\/g, "/")}'`, ""].join("\n");
	}

	/** Create the partition sample dirs (all distinct, none nested in each
	 * other) inside the project tmp root and return their realpath form. */
	function mkPartitionDirs(project: Project): {
		parent: string;
		partition: string;
		sdk: string;
	} {
		const parent = path.join(project.control, "parent");
		const partition = path.join(project.control, "shard");
		const sdk = path.join(project.control, "sdk");
		for (const d of [parent, partition, sdk]) fs.mkdirSync(d);
		return {
			parent: fs.realpathSync.native(parent),
			partition: fs.realpathSync.native(partition),
			sdk: fs.realpathSync.native(sdk),
		};
	}

	async function dispatch(project: Project, taskKey: string): Promise<void> {
		const md = path.join(project.agenticdoc, "_scratch", "workers", taskKey, "task.md");
		fs.mkdirSync(path.dirname(md), { recursive: true });
		fs.writeFileSync(md, `type: coding\n\n${taskKey} body.\n`, "utf8");
		await dispatchTask(
			{ taskKey, status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			new WorkerStore(project.agenticdoc),
		);
	}

	/** task.md path for a key (no rewrite — re-dispatch must operate on the
	 * file the previous dispatch left behind, or the AC-019 replacement
	 * path is never exercised). */
	function taskPath(project: Project, taskKey: string): string {
		return path.join(project.agenticdoc, "_scratch", "workers", taskKey, "task.md");
	}

	function writeTaskBody(project: Project, taskKey: string, body: string): string {
		const md = taskPath(project, taskKey);
		fs.mkdirSync(path.dirname(md), { recursive: true });
		fs.writeFileSync(md, body, "utf8");
		return md;
	}

	async function reDispatch(project: Project, taskKey: string): Promise<void> {
		await dispatchTask(
			{ taskKey, status: "pending", cli: "pi", provider: "timi", model: "", taskPath: taskPath(project, taskKey) },
			new WorkerStore(project.agenticdoc),
		);
	}

	it("VC-007: injects the v2 block with mode line, roots, toolchain, firewall, contract", async () => {
		const project = mkProject();
		const dirs = mkPartitionDirs(project);
		fs.mkdirSync(path.join(project.control, "docs"), { recursive: true });
		writeTargetYml(project, partitionYml(dirs.parent, dirs.partition, dirs.sdk));
		await dispatch(project, "ap-part-full");

		const md = path.join(project.agenticdoc, "_scratch", "workers", "ap-part-full", "task.md");
		const text = fs.readFileSync(md, "utf8");
		// v2 marker + explicit mode line right under it (the tear-check anchor).
		expect(text).toContain("<!-- mw-profile: v2 -->\n[mw] mode: partition");
		expect(text.split("<!-- mw-profile:").length - 1).toBe(1); // single block
		// Roots (realpath-normalized) replace the dual game/engine lines.
		expect(text).toContain(`Parent root: ${dirs.parent}`);
		expect(text).toContain(`Partition root (worker cwd): ${dirs.partition}`);
		expect(text).toContain(`- sdk: ${dirs.sdk}`);
		expect(text).not.toContain("Game root:");
		// Toolchain with every placeholder resolved ({partition}/{sdk}).
		expect(text).toContain(`- build: make -C ${dirs.partition} SDK=${dirs.sdk}`);
		// Firewall section + frontmatter deny_globs (Py renderer format).
		expect(text).toContain("Context firewall (deny globs, enforced by the read-scope layer):");
		expect(text).toContain("- **/*.tmp");
		expect(text).toContain("deny_globs:\n  - '**/*.tmp'");
		// Contract essentials; docs as control-root-anchored references.
		expect(text).toContain("- forbidden paths: **/Generated/*");
		expect(text).toContain("Keep the shard self-contained.");
		expect(text).toContain(`- ${path.join(project.realControl, "docs", "contract-notes.md")}`);
		// The full-file line always names target.yml.
		expect(text).toContain(path.join(project.realControl, ".agenticdoc", "target.yml"));
		// The injected task.md still parses: the worker sees the firewall.
		const meta = parseTaskMd(md);
		expect(meta.denyGlobs).toEqual(["**/*.tmp"]);
		console.log("[VERIFY] VC-007: profile_block=present, mode_line=partition");
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("same-mode re-dispatch is byte-identical (idempotent)", async () => {
		const project = mkProject();
		const dirs = mkPartitionDirs(project);
		writeTargetYml(project, partitionYml(dirs.parent, dirs.partition, dirs.sdk));
		writeTaskBody(project, "ap-part-idem", "type: coding\n\nap-part-idem body.\n");
		await reDispatch(project, "ap-part-idem");
		const first = fs.readFileSync(taskPath(project, "ap-part-idem"), "utf8");
		await reDispatch(project, "ap-part-idem"); // same file, same config
		expect(fs.readFileSync(taskPath(project, "ap-part-idem"), "utf8")).toBe(first);
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("FIX-2: same-mode config change (partition root) replaces the stale block", async () => {
		const project = mkProject();
		const dirs = mkPartitionDirs(project);
		writeTargetYml(project, partitionYml(dirs.parent, dirs.partition, dirs.sdk));
		writeTaskBody(project, "ap-part-cfgchange", "type: coding\n\nap-part-cfgchange body.\n");
		await reDispatch(project, "ap-part-cfgchange");
		const md = taskPath(project, "ap-part-cfgchange");
		const first = fs.readFileSync(md, "utf8");
		expect(first).toContain(`Partition root (worker cwd): ${dirs.partition}`);

		// Same active mode, re-pointed shard: the recorded block no longer
		// matches what the config renders — it must be replaced wholesale
		// (marker to EOF), never left stale while partition stays active.
		// (The new root name deliberately does not contain the old one, so
		// the not.toContain assertions cannot pass on a shared prefix.)
		const reshard = path.join(project.control, "reshard-root");
		fs.mkdirSync(reshard);
		const partitionB = fs.realpathSync.native(reshard);
		writeTargetYml(project, partitionYml(dirs.parent, partitionB, dirs.sdk));
		await reDispatch(project, "ap-part-cfgchange");
		const second = fs.readFileSync(md, "utf8");
		expect(second).not.toBe(first);
		expect(second).toContain(`Partition root (worker cwd): ${partitionB}`);
		expect(second).not.toContain(`Partition root (worker cwd): ${dirs.partition}`);
		expect(second.split("<!-- mw-profile:").length - 1).toBe(1); // replaced, not appended
		expect(second).toContain("ap-part-cfgchange body."); // body survives the replacement
		// the replaced block is itself idempotent under the new config
		await reDispatch(project, "ap-part-cfgchange");
		expect(fs.readFileSync(md, "utf8")).toBe(second);
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("FIX-2: same-mode dual game change replaces the legacy v1 block", async () => {
		const project = mkProject();
		fs.mkdirSync(path.join(project.control, "game-a"));
		fs.mkdirSync(path.join(project.control, "game-b"));
		const game1 = fs.realpathSync.native(path.join(project.control, "game-a"));
		const game2 = fs.realpathSync.native(path.join(project.control, "game-b"));
		writeTargetYml(project, dualBlockYml(game1));
		writeTaskBody(project, "ap-dual-cfgchange", "type: coding\n\nap-dual-cfgchange body.\n");
		await reDispatch(project, "ap-dual-cfgchange");
		const md = taskPath(project, "ap-dual-cfgchange");
		expect(fs.readFileSync(md, "utf8")).toContain(`Game root: ${game1}`);

		// dual stays active but the game root moves: the v1-marked block is
		// stale by content, not by mode — it must be replaced too.
		writeTargetYml(project, dualBlockYml(game2));
		await reDispatch(project, "ap-dual-cfgchange");
		const text = fs.readFileSync(md, "utf8");
		expect(text).toContain(`Game root: ${game2}`);
		expect(text).not.toContain(`Game root: ${game1}`);
		expect(text.split("<!-- mw-profile:").length - 1).toBe(1);
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("AC-019: active switched to dual -> block replaced wholesale (marker to EOF)", async () => {
		const project = mkProject();
		const dirs = mkPartitionDirs(project);
		writeTargetYml(project, partitionYml(dirs.parent, dirs.partition, dirs.sdk));
		writeTaskBody(project, "ap-part-torn", "type: coding\n\nap-part-torn body.\n");
		await reDispatch(project, "ap-part-torn");
		const md = taskPath(project, "ap-part-torn");
		const torn = fs.readFileSync(md, "utf8");
		expect(torn).toContain("[mw] mode: partition");
		expect(torn).toContain("deny_globs:\n  - '**/*.tmp'"); // inserted by dispatch 1

		// Switch the workspace to dual (same task re-dispatched by the PM).
		writeTargetYml(project, dualBlockYml(dirs.parent));
		await reDispatch(project, "ap-part-torn");
		const text = fs.readFileSync(md, "utf8");
		expect(text).not.toContain("<!-- mw-profile: v2 -->");
		expect(text).not.toContain("[mw] mode:");
		expect(text.split("<!-- mw-profile:").length - 1).toBe(1); // replaced, not appended
		expect(text).toContain("<!-- mw-profile: v1 -->");
		expect(text).toContain(`Game root: ${dirs.parent}`); // dual block content
		// The deny_globs frontmatter the partition dispatch inserted survives
		// the switch (enforcement continues) and is never duplicated.
		expect(text).toContain("deny_globs:\n  - '**/*.tmp'");
		expect(text.split("deny_globs:").length - 1).toBe(1);
		// The pre-block task body survives the wholesale replacement.
		expect(text).toContain("ap-part-torn body.");
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("AC-019: v1-marked legacy block is replaced under partition activation", async () => {
		const project = mkProject();
		const dirs = mkPartitionDirs(project);
		writeTargetYml(project, dualBlockYml(dirs.parent));
		writeTaskBody(project, "ap-legacy-v1", "type: coding\n\nap-legacy-v1 body.\n");
		await reDispatch(project, "ap-legacy-v1");
		const md = taskPath(project, "ap-legacy-v1");
		expect(fs.readFileSync(md, "utf8")).toContain("<!-- mw-profile: v1 -->");

		// Partition activates afterwards: the legacy block cannot record the
		// mode, so it is provably stale and replaced wholesale.
		writeTargetYml(project, partitionYml(dirs.parent, dirs.partition, dirs.sdk));
		await reDispatch(project, "ap-legacy-v1");
		const text = fs.readFileSync(md, "utf8");
		expect(text).not.toContain("<!-- mw-profile: v1 -->");
		expect(text.split("<!-- mw-profile:").length - 1).toBe(1);
		expect(text).toContain("<!-- mw-profile: v2 -->\n[mw] mode: partition");
		expect(text).toContain(`Partition root (worker cwd): ${dirs.partition}`);
		expect(text).toContain("ap-legacy-v1 body."); // body survives the replacement
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("AC-019: active switched to single -> stale block stripped, file byte-restored", async () => {
		const project = mkProject();
		const dirs = mkPartitionDirs(project);
		// Sections-free partition yml: nothing but the block (and no
		// deny_globs frontmatter) stands between the file and its original
		// bytes once the block is replaced by parked single's empty content.
		const q = (p: string) => `'${p.replace(/\\/g, "/")}'`;
		writeTargetYml(
			project,
			[
				"active: partition",
				"partition:",
				`  parent: ${q(dirs.parent)}`,
				`  partition: ${q(dirs.partition)}`,
				"",
			].join("\n"),
		);
		const md = path.join(project.agenticdoc, "_scratch", "workers", "ap-part-single", "task.md");
		fs.mkdirSync(path.dirname(md), { recursive: true });
		const body = "type: coding\n\nap-part-single body.\n";
		fs.writeFileSync(md, body, "utf8");
		await dispatchTask(
			{ taskKey: "ap-part-single", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			new WorkerStore(project.agenticdoc),
		);
		expect(fs.readFileSync(md, "utf8")).toContain("[mw] mode: partition");

		// Parked single (row 5) injects nothing: the replacement content is
		// empty, so the file must return to its pre-injection bytes.
		writeTargetYml(project, "active: single\n");
		await dispatchTask(
			{ taskKey: "ap-part-single", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			new WorkerStore(project.agenticdoc),
		);
		expect(fs.readFileSync(md, "utf8")).toBe(body);
		fs.rmSync(project.control, { recursive: true, force: true });
	});

	it("dual injection keeps the v1 marker and no mode line (AC-016d zero change)", async () => {
		const project = mkProject();
		const game = path.join(project.control, "game");
		fs.mkdirSync(game);
		writeTargetYml(project, dualBlockYml(game));
		writeTaskBody(project, "ap-dual-v1", "type: coding\n\nap-dual-v1 body.\n");
		await reDispatch(project, "ap-dual-v1");
		const md = taskPath(project, "ap-dual-v1");
		const text = fs.readFileSync(md, "utf8");
		expect(text).not.toContain("<!-- mw-profile: v2 -->");
		expect(text).not.toContain("[mw] mode:");
		const mark = text.indexOf("<!-- mw-profile: v1 -->");
		expect(mark).not.toBe(-1);
		// The line under the marker is the legacy header, byte-for-byte the
		// pre-partition render (golden d in agent-team-loop-baseline.test.ts).
		expect(text.slice(mark).startsWith("<!-- mw-profile: v1 -->\n[mw] Workspace profile")).toBe(true);
		fs.rmSync(project.control, { recursive: true, force: true });
	});
});

// ── FIX-13: partition profile full-text parity golden (Py/TS) ─────────────────

/** Shared golden location: packages/multi-workers/test/fixtures/
 * partition-profile-block.golden.md (the SAME file the Python side asserts
 * against — cross-package by design, like the target-config fixtures). */
const PARTITION_GOLDEN_FILE = fileURLToPath(
	new URL("../../../multi-workers/test/fixtures/partition-profile-block.golden.md", import.meta.url),
);

/** Path placeholder recorded in the golden (AC-016 golden protocol). */
const CTRL_PLACEHOLDER = "<CTRL>";

/** mw-target-partition FIX-13 parity sample: every partition profile field
 * (parent/partition/roots/toolchain with placeholders/firewall/contract) —
 * byte-for-byte the same sample as _PARTITION_GOLDEN_YML in
 * packages/multi-workers/test_partition_dispatch.py (keep both in sync). */
const PARTITION_GOLDEN_YML = [
	"# mw-target-partition FIX-13 parity sample: full partition profile fields.",
	"active: partition",
	"partition:",
	"  parent: parent",
	"  partition: shard",
	"  roots:",
	"    sdk: sdk",
	"    data: data",
	"  vcs: git",
	"  toolchain:",
	"    build: 'make -C {partition} SDK={sdk} --parent {parent}'",
	"    regen: 'python {data}/Tools/regen.py'",
	"  ignore:",
	"    deny_globs:",
	'      - "**/*.uasset"',
	'      - "**/DerivedDataCache/**"',
	"  contract:",
	"    forbidden_paths:",
	'      - "**/Generated/*"',
	"    conventions: |",
	"      Line one of the conventions.",
	"      Line two of the conventions.",
	"    docs:",
	"      - docs/contract-notes.md",
	"",
].join("\n");

/** Record-if-missing / byte-exact-compare golden gate (FIX-13, AC-016
 * protocol): the golden is written by THIS side's renderer
 * (renderPartitionProfileBlock, captured through the real dispatchTask
 * injection: marker line to EOF) with the temp control root replaced by
 * "<CTRL>" — everything else must match to the byte. The Python side
 * (test_partition_dispatch.py) renders the same sample config through
 * mw_common.render_partition_profile_md and asserts the identical bytes,
 * locking the Py/TS profile protocol. Newline strategy (fixture-runner
 * convention): the golden is LF and CRLF is normalized on read. To
 * re-record, delete the golden file and re-run. */
function partitionGoldenCheck(block: string): "RECORDED" | "MATCH" {
	fs.mkdirSync(path.dirname(PARTITION_GOLDEN_FILE), { recursive: true });
	const rel = "multi-workers/test/fixtures/partition-profile-block.golden.md";
	if (!fs.existsSync(PARTITION_GOLDEN_FILE)) {
		fs.writeFileSync(PARTITION_GOLDEN_FILE, block, "utf8"); // UTF-8, no BOM, LF
		console.log(`[GOLDEN] RECORDED: ${rel}`);
		return "RECORDED";
	}
	const golden = fs.readFileSync(PARTITION_GOLDEN_FILE, "utf8").replace(/\r\n/g, "\n");
	if (golden === block) {
		console.log(`[GOLDEN] MATCH: ${rel}`);
		return "MATCH";
	}
	const goldenLines = golden.split("\n");
	const blockLines = block.split("\n");
	const diff: string[] = [];
	for (let i = 0; i < Math.max(goldenLines.length, blockLines.length) && diff.length < 40; i++) {
		if (goldenLines[i] !== blockLines[i]) {
			diff.push(`line ${i + 1}: golden=${JSON.stringify(goldenLines[i])} current=${JSON.stringify(blockLines[i])}`);
		}
	}
	console.error(`[GOLDEN] MISMATCH: ${rel}\n${diff.join("\n")}`);
	throw new Error("partition profile block differs from the shared golden (mw-target-partition FIX-13)");
}

describe("partition profile full-text parity golden (mw-target-partition FIX-13)", () => {
	const savedEnv: Record<string, string | undefined> = {};
	const envKeys = ["MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"];

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

	it("TS-rendered partition block is byte-identical to the shared golden (Py asserts the same file)", async () => {
		const project = mkProject();
		// Every root the sample names, as siblings under the control root
		// (none nested — AC-003(g) legal; every recorded path is <CTRL>/...).
		for (const name of ["parent", "shard", "sdk", "data", "docs"]) {
			fs.mkdirSync(path.join(project.control, name));
		}
		writeTargetYml(project, PARTITION_GOLDEN_YML);
		const md = writeScratchTask(project, "ap-part-golden", "type: coding\n\nParity golden sample task.\n");
		await dispatchTask(
			{ taskKey: "ap-part-golden", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md },
			new WorkerStore(project.agenticdoc),
		);

		const text = fs.readFileSync(md, "utf8");
		const mark = text.indexOf("<!-- mw-profile: v2 -->");
		expect(mark).not.toBe(-1);
		// The dispatched block (marker line to EOF, exactly what the dispatcher
		// appends: renderPartitionProfileBlock output + trailing newline).
		const block = text.slice(mark).split(project.realControl).join(CTRL_PLACEHOLDER);
		const status = partitionGoldenCheck(block);
		expect(status === "RECORDED" || status === "MATCH").toBe(true);
		console.log(`[VERIFY] FIX-13: partition_profile_parity=${status === "MATCH" ? "byte-identical" : "recorded"}`);
		fs.rmSync(project.control, { recursive: true, force: true });
	});
});
