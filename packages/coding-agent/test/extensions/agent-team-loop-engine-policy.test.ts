import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import {
	dualEnginePolicyLines,
	engineBuildArtifactRoots,
} from "../../src/extensions/agent-team-loop/shared/engine-policy.ts";
import { resolveWorkspaceConfig } from "../../src/extensions/agent-team-loop/shared/target-config.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import {
	engineCopyBlockReason,
	engineWriteBlockReason,
	registerWorkspaceEngineGuard,
} from "../../src/extensions/agent-team-loop/shared/workspace-engine-guard.ts";
import { workspaceWriteFaceOptions } from "../../src/extensions/agent-team-loop/shared/workspace-write-face.ts";
import { parseWriteFaceEntries } from "../../src/extensions/agent-team-loop/shared/write-face.ts";
import { matchesWriteScopeEntry } from "../../src/extensions/agent-team-loop/shared/write-surface.ts";
import { matchedDenyGlob, normalizeForCompare } from "../../src/extensions/agent-team-loop/worker/read-scope.ts";
import {
	checkBashWriteScopeTarget,
	parseTaskMd,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

/** design.md §4 frozen TS/Python contract (dual engine_writable=false only). */
const UBT_ARTIFACT_SUFFIXES = ["Engine/Intermediate/Build", "Engine/Saved/UnrealBuildTool", "Engine/Saved/Logs"];
const UBT_POLICY_LINES = [
	"UBT builds: allowed without enabling Engine source writes. Build-generated files, caches and logs are writable only under Engine/Intermediate/Build/**, Engine/Saved/UnrealBuildTool/** and Engine/Saved/Logs/** (relative to the configured Engine root; subject to task write_face/write_scope).",
	"UBT build permission does not allow rebuilding UBT itself or writing other Engine/Binaries paths, changing Engine source/build/config files or InstalledBuild.txt. A command name is not a write exemption.",
	"Static command guards are not an OS sandbox. Keep detached run_dir outside Engine unless it is an explicitly permitted build-artifact path; report any other required Engine write.",
];

const temporary: string[] = [];
const cwd = process.cwd();
const exitListeners = new Set(process.listeners("exit"));
const probePath = fileURLToPath(new URL("../../../multi-workers/test/engine_policy_probe.py", import.meta.url));

afterEach(() => {
	process.chdir(cwd);
	vi.unstubAllEnvs();
	for (const listener of process.listeners("exit")) {
		if (!exitListeners.has(listener)) process.removeListener("exit", listener);
	}
	for (const root of temporary.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

function fixture(v2 = true, writable?: unknown) {
	for (const name of ["MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"])
		vi.stubEnv(name, "");
	const control = fs.realpathSync.native(fs.mkdtempSync(path.join(os.tmpdir(), "mw-engine-policy-")));
	temporary.push(control);
	const game = path.join(control, "Game");
	const engine = path.join(game, "Engine");
	fs.mkdirSync(engine, { recursive: true });
	fs.mkdirSync(path.join(control, ".agenticdoc"));
	const config = path.join(control, ".agenticdoc", "target.yml");
	const block = { game, engine, ...(writable === undefined ? {} : { engine_writable: writable }) };
	fs.writeFileSync(config, JSON.stringify(v2 ? { active: "dual", dual: block } : { mode: "dual", ...block }));
	const taskPath = path.join(control, ".agenticdoc", "test", "workers", "one", "task.md");
	fs.mkdirSync(path.dirname(taskPath), { recursive: true });
	return { control, game, engine, config, taskPath };
}

function python(control: string, entries: string[] = []) {
	const result = spawnSync("python", ["-B", probePath], {
		input: JSON.stringify({ control, entries }),
		encoding: "utf8",
		windowsHide: true,
	});
	expect(result.status, result.stderr).toBe(0);
	return JSON.parse(result.stdout) as {
		error?: string;
		writable: boolean;
		lines: string[];
		profile: string;
		artifact_roots: string[];
		faces: string[];
	};
}

describe.each([false, true])("dual engine policy (v2=%s)", (v2) => {
	it.each([undefined, false, true])(
		"resolves explicit boolean %s and enforces nested roots with Python parity",
		(writable) => {
			const fx = fixture(v2, writable);
			const config = resolveWorkspaceConfig(fx.control);
			expect(config.engineWritable).toBe(writable === true);
			const entries = [
				path.join(fx.game, "Plugin.cpp"),
				path.join(fx.engine, "Source", "Engine.cpp"),
				`${fx.game}/**`,
			];
			const options = workspaceWriteFaceOptions(fx.control, config);
			const results = entries.map((entry) => {
				const parsed = parseWriteFaceEntries([entry], options);
				return parsed.kind === "rejected" ? parsed.code : parsed.kind;
			});
			expect(results).toEqual([
				"declared",
				writable === true ? "declared" : "write-face-read-only",
				writable === true ? "declared" : "write-face-read-only",
			]);
			const py = python(fx.control, entries);
			expect(py.writable).toBe(config.engineWritable);
			expect(py.lines).toEqual(dualEnginePolicyLines(config));
			expect(py.faces).toEqual(results);
		},
	);

	it.each([null, "true", "false", 1, [], {}])("rejects non-boolean %j on both resolvers", (writable) => {
		const fx = fixture(v2, writable);
		expect(() => resolveWorkspaceConfig(fx.control)).toThrow("engine_writable must be a boolean");
		expect(python(fx.control).error).toBe("invalid-config");
	});
	it("refuses an Engine write grant with no Engine root", () => {
		const fx = fixture(v2, true);
		const block = { game: fx.game, engine_writable: true };
		fs.writeFileSync(fx.config, JSON.stringify(v2 ? { active: "dual", dual: block } : { mode: "dual", ...block }));
		expect(() => resolveWorkspaceConfig(fx.control)).toThrow("requires a configured dual engine root");
		expect(python(fx.control).error).toBe("invalid-config");
	});
	it.each(["yes", "no", "on", "off"])("rejects the YAML 1.1 boolean spelling %s on both resolvers", (value) => {
		const fx = fixture(v2);
		const block = `game: '${fx.game}'\nengine: '${fx.engine}'\nengine_writable: ${value}\n`;
		fs.writeFileSync(
			fx.config,
			v2
				? `active: dual\ndual:\n${block
						.split("\n")
						.filter(Boolean)
						.map((line) => `  ${line}`)
						.join("\n")}\n`
				: `mode: dual\n${block}`,
		);
		expect(() => resolveWorkspaceConfig(fx.control)).toThrow("engine_writable must be a boolean");
		expect(python(fx.control).error).toBe("invalid-config");
	});
});

it("dispatch refuses Engine and broad glob declarations without queue mutation; injects Python-identical policy", async () => {
	const fx = fixture();
	const store = new WorkerStore(path.join(fx.control, ".agenticdoc"));
	const entry = {
		taskKey: "one",
		status: "pending" as const,
		cli: "pi",
		provider: "timi",
		model: "",
		taskPath: fx.taskPath,
	};
	fs.writeFileSync(fx.taskPath, `type: coding\nwrite_face: ${fx.engine}/**\n\nWork.\n`);
	expect(await dispatchTask(entry, store)).toMatchObject({ ok: false, code: "write-face-read-only" });
	expect(fs.existsSync(store.queuePath)).toBe(false);
	fs.writeFileSync(fx.taskPath, `type: coding\nwrite_face: ${fx.game}/Plugin.cpp\n\nWork.\n`);
	expect(await dispatchTask(entry, store)).toEqual({ ok: true });
	const first = fs.readFileSync(fx.taskPath, "utf8");
	const block = first.slice(first.indexOf("<!-- mw-profile: v1 -->")).trimEnd();
	expect(block).toBe(python(fx.control).profile);
	expect(first).toContain("Never copy or fork Engine source");
	await dispatchTask(entry, store);
	expect(fs.readFileSync(fx.taskPath, "utf8")).toBe(first);
	const meta = parseTaskMd(fx.taskPath);
	expect(
		checkBashWriteScopeTarget(
			{
				projectRoot: fx.game,
				taskDir: path.dirname(fx.taskPath),
				keyDir: path.resolve(fx.taskPath, "../../.."),
				trueRoot: path.join(fx.control, ".agenticdoc"),
				writeScope: undefined,
				roleClass: "writable",
				writeRoots: meta.writeRoots,
				readOnlyWriteRoots: meta.readOnlyWriteRoots,
			},
			path.join(fx.engine, "Engine.cpp"),
			true,
		),
	).toMatchObject({ allowed: false, rule: "deny", detail: "denied:engine-read-only" });
});

it("PM and worker guard blocks direct, shell, detached and junction writes; refreshes config every call", () => {
	const fx = fixture();
	const handlers = new Map<
		string,
		(
			event: { toolName: string; input: Record<string, unknown>; systemPrompt?: string },
			ctx: { cwd: string },
		) => { block?: boolean; reason?: string; systemPrompt?: string } | undefined
	>();
	registerWorkspaceEngineGuard(
		{
			on: (name: string, handler: unknown) =>
				handlers.set(name, handler as typeof handlers extends Map<string, infer H> ? H : never),
		} as unknown as ExtensionAPI,
		fx.control,
	);
	const call = (toolName: string, input: Record<string, unknown>) =>
		handlers.get("tool_call")?.({ toolName, input }, { cwd: fx.game });
	const engineFile = path.join(fx.engine, "Source", "Engine.cpp");
	expect(call("write", { path: "Plugin.cpp" })).toBeUndefined();
	expect(call("read", { path: engineFile })).toBeUndefined();
	for (const toolName of ["write", "edit"])
		expect(call(toolName, { path: engineFile })?.reason).toContain("engine-read-only");
	expect(call("bash", { command: `echo x > '${engineFile}'` })?.block).toBe(true);
	expect(call("mw_run_detached", { cmd: ["sh", "-c", `echo x > '${engineFile}'`], cwd: fx.game })?.block).toBe(true);
	expect(call("mw_run_detached", { cmd: ["echo", "hello"], cwd: fx.engine })?.block).toBe(true);
	const alias = path.join(fx.game, "alias");
	fs.symlinkSync(fx.engine, alias, "junction");
	expect(call("write", { path: path.join(alias, "Source", "missing.cpp") })?.block).toBe(true);
	const parsed = parseWriteFaceEntries([`${alias}/**`], workspaceWriteFaceOptions(fx.control));
	expect(parsed).toMatchObject({ kind: "rejected", code: "write-face-read-only" });
	for (const command of [
		`cp '${engineFile}' Plugin.cpp`,
		`cp '${fx.engine}/Source/'*.cpp .`,
		`Copy-Item -LiteralPath '${engineFile}' -Destination Plugin.cpp`,
	])
		expect(call("bash", { command })?.reason).toContain("engine-copy-forbidden");
	expect(engineCopyBlockReason(resolveWorkspaceConfig(fx.control), fx.game, `cat '${engineFile}'`)).toBeUndefined();
	expect(
		engineCopyBlockReason(resolveWorkspaceConfig(fx.control), fx.game, `echo cp '${engineFile}'`),
	).toBeUndefined();
	expect(
		engineCopyBlockReason(resolveWorkspaceConfig(fx.control), fx.game, `cp '${fx.engine}/Tool.exe' Tool.exe`),
	).toBeUndefined();
	const prompt = handlers.get("before_agent_start")?.(
		{ toolName: "", input: {}, systemPrompt: "base" },
		{ cwd: fx.game },
	);
	expect(prompt?.systemPrompt).toContain("Engine extension policy (mandatory)");
	fs.writeFileSync(
		fx.config,
		JSON.stringify({ active: "dual", dual: { game: fx.game, engine: fx.engine, engine_writable: true } }),
	);
	const enabledPrompt = handlers.get("before_agent_start")?.(
		{ toolName: "", input: {}, systemPrompt: "base" },
		{ cwd: fx.game },
	)?.systemPrompt;
	expect(enabledPrompt).toContain("Engine source writes: enabled");
	expect(enabledPrompt).toContain("Plan direct Engine changes only within the approved scope");
	expect(enabledPrompt).toContain("never overrides project/task constraints");
	expect(enabledPrompt).not.toContain("Engine extension policy (mandatory)");
	for (const toolName of ["write", "edit"]) expect(call(toolName, { path: engineFile })).toBeUndefined();
	expect(call("bash", { command: `echo x > '${engineFile}'` })).toBeUndefined();
	expect(call("mw_run_detached", { cmd: ["sh", "-c", `echo x > '${engineFile}'`], cwd: fx.game })).toBeUndefined();
	fs.writeFileSync(
		fx.config,
		JSON.stringify({ active: "dual", dual: { game: fx.game, engine: fx.engine, engine_writable: false } }),
	);
	const disabledPrompt = handlers.get("before_agent_start")?.(
		{ toolName: "", input: {}, systemPrompt: "base" },
		{ cwd: fx.game },
	)?.systemPrompt;
	expect(disabledPrompt).toContain("Engine source writes: read-only");
	expect(disabledPrompt).toContain("Engine extension policy (mandatory)");
	expect(disabledPrompt).not.toContain("Plan direct Engine changes");
	expect(call("write", { path: engineFile })?.reason).toContain("engine-read-only");
	expect(call("write", { path: "Plugin.cpp" })).toBeUndefined();
	fs.writeFileSync(fx.config, "active: dual\n");
	expect(call("write", { path: "Plugin.cpp" })?.reason).toContain("target-config-unusable");
});

it("PM re-dispatch refreshes permissions and Engine admission across false/true/false", async () => {
	const fx = fixture();
	const store = new WorkerStore(path.join(fx.control, ".agenticdoc"));
	fs.writeFileSync(fx.taskPath, `type: coding\nwrite_face: ${fx.game}/Plugin.cpp\n\nWork.\n`);
	const gameEntry = {
		taskKey: "one",
		status: "pending" as const,
		cli: "pi",
		provider: "timi",
		model: "",
		taskPath: fx.taskPath,
	};
	const engineTask = path.join(path.dirname(path.dirname(fx.taskPath)), "engine-direct", "task.md");
	fs.mkdirSync(path.dirname(engineTask));
	fs.writeFileSync(engineTask, `type: coding\nwrite_face: ${fx.engine}/Source/Engine.cpp\n\nWork.\n`);
	for (const writable of [false, true, false]) {
		fs.writeFileSync(
			fx.config,
			JSON.stringify({ active: "dual", dual: { game: fx.game, engine: fx.engine, engine_writable: writable } }),
		);
		expect(await dispatchTask(gameEntry, store)).toEqual({ ok: true });
		const content = fs.readFileSync(fx.taskPath, "utf8");
		expect(content.match(/<!-- mw-profile: v1 -->/g)).toHaveLength(1);
		expect(content).toContain(`Engine source writes: ${writable ? "enabled" : "read-only"}`);
		expect(content.includes("Engine extension policy (mandatory)")).toBe(!writable);
		expect(content.includes("Plan direct Engine changes")).toBe(writable);
		expect(content.slice(content.indexOf("<!-- mw-profile: v1 -->")).trimEnd()).toBe(python(fx.control).profile);
		const before = fs.readFileSync(store.queuePath, "utf8");
		const outcome = await dispatchTask({ ...gameEntry, taskKey: "engine-direct", taskPath: engineTask }, store);
		if (writable) expect(outcome).toEqual({ ok: true });
		else {
			expect(outcome).toMatchObject({ ok: false, code: "write-face-read-only" });
			expect(fs.readFileSync(store.queuePath, "utf8")).toBe(before);
		}
	}
});

it("canonicalizes OS temporary-path aliases before comparing Engine roots", () => {
	const fx = fixture();
	const rawControl = path.join(os.tmpdir(), path.relative(fs.realpathSync.native(os.tmpdir()), fx.control));
	const rawEngineFile = path.join(rawControl, "Game", "Engine", "Source", "Engine.cpp");
	expect(matchedDenyGlob(rawControl, ["Game/Engine/**"], rawEngineFile)).toBe("Game/Engine/**");
	expect(matchesWriteScopeEntry(rawControl, "Game/**", normalizeForCompare(rawControl, rawEngineFile))).toBe(true);
	expect(engineWriteBlockReason(resolveWorkspaceConfig(fx.control), rawControl, rawEngineFile)).toContain(
		"engine-read-only",
	);
	expect(parseWriteFaceEntries([rawEngineFile], workspaceWriteFaceOptions(fx.control))).toMatchObject({
		kind: "rejected",
		code: "write-face-read-only",
	});
});

it("renders the frozen UBT build policy before the read-only extension policy", () => {
	const fx = fixture();
	const config = resolveWorkspaceConfig(fx.control);
	const lines = dualEnginePolicyLines(config);
	expect(lines).toContain("Engine source writes: read-only (engine_writable: false).");
	expect(lines.some((line) => line.startsWith("Engine writes:"))).toBe(false);
	const anchor = lines.indexOf("Engine extension policy (mandatory):");
	expect(anchor).toBeGreaterThanOrEqual(UBT_POLICY_LINES.length);
	expect(lines.slice(anchor - UBT_POLICY_LINES.length, anchor)).toEqual(UBT_POLICY_LINES);
	expect(python(fx.control).lines).toEqual(lines);
	expect(python(fx.control).artifact_roots).toEqual(engineBuildArtifactRoots(fx.engine));
	fs.writeFileSync(
		fx.config,
		JSON.stringify({ active: "dual", dual: { game: fx.game, engine: fx.engine, engine_writable: true } }),
	);
	const writable = dualEnginePolicyLines(resolveWorkspaceConfig(fx.control));
	expect(writable).toContain("Engine source writes: enabled (engine_writable: true).");
	expect(writable.some((line) => line.startsWith("UBT builds:"))).toBe(false);
	expect(python(fx.control).lines).toEqual(writable);
	expect(python(fx.control).artifact_roots).toEqual([]);
	process.stdout.write("[VERIFY] VC-001: policy_parity=PASS dual=false/true lines+artifact_roots\n");
});

it("admits only the three frozen UBT build-artifact directories under the read-only Engine root", () => {
	const fx = fixture();
	const options = workspaceWriteFaceOptions(fx.control);
	const admitted = UBT_ARTIFACT_SUFFIXES.flatMap((suffix) => [
		`${fx.engine}/${suffix}`,
		`${fx.engine}/${suffix}/**`,
		`${fx.engine}/${suffix}/generated/file.bin`,
	]);
	const denied = [
		`${fx.engine}/**`,
		`${fx.engine}/Engine/**`,
		`${fx.engine}/Engine/Intermediate/**`,
		`${fx.engine}/Engine/Intermediate/BuildOther/file.bin`,
		`${fx.engine}/Engine/Saved/Logs2/file.log`,
		`${fx.engine}/Engine/Build/Build.version`,
		`${fx.engine}/Engine/Config/BaseEngine.ini`,
		`${fx.engine}/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll`,
		`${fx.engine}/Engine/Source/Programs/Probe.cpp`,
		`${fx.engine}/InstalledBuild.txt`,
	];
	const code = (entry: string) => {
		const parsed = parseWriteFaceEntries([entry], options);
		return parsed.kind === "rejected" ? parsed.code : parsed.kind;
	};
	expect(admitted.map(code)).toEqual(admitted.map(() => "declared"));
	expect(denied.map(code)).toEqual(denied.map(() => "write-face-read-only"));
	if (process.platform === "win32") {
		// The artifact prefix follows the configured case mode (Windows folds).
		expect(code(`${fx.engine}/ENGINE/intermediate/Build/generated/file.bin`)).toBe("declared");
		expect(code(`${fx.engine}/ENGINE/intermediate/BuildOther/file.bin`)).toBe("write-face-read-only");
	}
	expect(parseWriteFaceEntries([`${fx.engine}/Engine/Intermediate/Build/../Source/Probe.cpp`], options)).toMatchObject(
		{ kind: "rejected", code: "write-face-escape" },
	);
	const entries = [...admitted, ...denied];
	expect(python(fx.control, entries).faces).toEqual(entries.map(code));
	process.stdout.write(
		"[VERIFY] VC-002: artifact_dispatch=PASS declared=3dirs/[dir]/**/file; " +
			"[VERIFY] VC-005: source_and_alias_denied=PASS build/config/binaries/source/marker/boundary\n",
	);
});

it("does not migrate the artifact exception through a junction under Intermediate", () => {
	const fx = fixture();
	const source = path.join(fx.engine, "Engine", "Source");
	fs.mkdirSync(source, { recursive: true });
	fs.symlinkSync(source, path.join(fx.engine, "Engine", "Intermediate"), "junction");
	const options = workspaceWriteFaceOptions(fx.control);
	expect(parseWriteFaceEntries([`${fx.engine}/Engine/Intermediate/Build/x.bin`], options)).toMatchObject({
		kind: "rejected",
		code: "write-face-read-only",
	});
	expect(
		engineWriteBlockReason(
			resolveWorkspaceConfig(fx.control),
			fx.game,
			`${fx.engine}/Engine/Intermediate/Build/x.bin`,
		),
	).toContain("engine-read-only");
	expect(python(fx.control, [`${fx.engine}/Engine/Intermediate/Build/x.bin`]).faces).toEqual(["write-face-read-only"]);
	process.stdout.write("[VERIFY] VC-005: source_and_alias_denied=PASS junction=intermediate->source\n");
});

it("dispatches precise UBT artifact faces and keeps broad-glob and conflict refusals", async () => {
	const fx = fixture();
	const store = new WorkerStore(path.join(fx.control, ".agenticdoc"));
	const artifact = `${fx.engine}/${UBT_ARTIFACT_SUFFIXES[0]}/SourceFileCache.bin`;
	const entry = (taskKey: string, taskPath: string) => ({
		taskKey,
		status: "pending" as const,
		cli: "pi",
		provider: "timi",
		model: "",
		taskPath,
	});
	const taskOf = (name: string, face: string) => {
		const taskPath = path.join(fx.control, ".agenticdoc", "test", "workers", name, "task.md");
		fs.mkdirSync(path.dirname(taskPath), { recursive: true });
		fs.writeFileSync(taskPath, `type: coding\nwrite_face: ${face}\n\nWork.\n`);
		return taskPath;
	};
	const first = taskOf("artifact", artifact);
	expect(await dispatchTask(entry("artifact", first), store)).toEqual({ ok: true });
	const content = fs.readFileSync(first, "utf8");
	expect(content).toContain(UBT_POLICY_LINES[0]);
	expect(content).toContain("Engine source writes: read-only");
	expect(content.slice(content.indexOf("<!-- mw-profile: v1 -->")).trimEnd()).toBe(python(fx.control).profile);
	const queued = fs.readFileSync(store.queuePath, "utf8");
	const conflict = taskOf("artifact-two", artifact);
	expect(await dispatchTask(entry("artifact-two", conflict), store)).toMatchObject({
		ok: false,
		code: "write-face-overlap",
		overlapWith: "artifact",
	});
	expect(fs.readFileSync(store.queuePath, "utf8")).toBe(queued);
	for (const [name, face] of [
		["broad-engine", `${fx.engine}/**`],
		["broad-build", `${fx.engine}/Engine/Intermediate/**`],
		["engine-source", `${fx.engine}/Engine/Source/Programs/Probe.cpp`],
		["engine-binaries", `${fx.engine}/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll`],
		["installed-build", `${fx.engine}/InstalledBuild.txt`],
	] as const) {
		const taskPath = taskOf(name, face);
		expect(await dispatchTask(entry(name, taskPath), store)).toMatchObject({
			ok: false,
			code: "write-face-read-only",
		});
		expect(fs.readFileSync(store.queuePath, "utf8")).toBe(queued);
	}
	const mixedFx = fixture();
	const mixedStore = new WorkerStore(path.join(mixedFx.control, ".agenticdoc"));
	const mixedTask = path.join(mixedFx.control, ".agenticdoc", "test", "workers", "mixed", "task.md");
	fs.mkdirSync(path.dirname(mixedTask), { recursive: true });
	fs.writeFileSync(
		mixedTask,
		`type: coding\nwrite_face:\n  - ${mixedFx.game}/Plugin.cpp\n  - ${mixedFx.engine}/${UBT_ARTIFACT_SUFFIXES[2]}/build.log\n\nWork.\n`,
	);
	expect(await dispatchTask(entry("mixed", mixedTask), mixedStore)).toEqual({ ok: true });
	process.stdout.write("[VERIFY] VC-002/VC-003: artifact_dispatch=PASS broad_and_conflict=PASS queue_untouched\n");
});

it("PM guard admits UBT artifact targets and still blocks source, copied source and an Engine-defaulted run_dir", () => {
	const fx = fixture();
	const handlers = new Map<
		string,
		(
			event: { toolName: string; input: Record<string, unknown>; systemPrompt?: string },
			ctx: { cwd: string },
		) => { block?: boolean; reason?: string; systemPrompt?: string } | undefined
	>();
	registerWorkspaceEngineGuard(
		{
			on: (name: string, handler: unknown) =>
				handlers.set(name, handler as typeof handlers extends Map<string, infer H> ? H : never),
		} as unknown as ExtensionAPI,
		fx.control,
	);
	const call = (toolName: string, input: Record<string, unknown>) =>
		handlers.get("tool_call")?.({ toolName, input }, { cwd: fx.game });
	const buildDir = `${fx.engine}/${UBT_ARTIFACT_SUFFIXES[0]}`;
	const cache = `${buildDir}/SourceFileCache.bin`;
	expect(call("write", { path: cache })).toBeUndefined();
	expect(call("edit", { path: `${buildDir}/Build.rsp` })).toBeUndefined();
	expect(call("bash", { command: `echo x > '${cache}'` })).toBeUndefined();
	expect(call("bash", { command: `echo x > '${fx.engine}/${UBT_ARTIFACT_SUFFIXES[2]}/Build.log'` })).toBeUndefined();
	expect(call("write", { path: `${fx.engine}/Engine/Source/Probe.cpp` })?.reason).toContain("engine-read-only");
	expect(
		call("write", { path: `${fx.engine}/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll` })?.block,
	).toBe(true);
	expect(call("write", { path: `${fx.engine}/Engine/Build/Build.version` })?.block).toBe(true);
	expect(call("bash", { command: `cp '${buildDir}/Generated.cpp' Plugin.cpp` })?.reason).toContain(
		"engine-copy-forbidden",
	);
	const ubt = [
		"dotnet",
		`${fx.engine}/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll`,
		"ProbeEditor",
		"Win64",
		"Development",
	];
	expect(call("mw_run_detached", { cmd: ubt, cwd: fx.engine, run_dir: `${buildDir}/runs/run-1` })).toBeUndefined();
	expect(
		call("mw_run_detached", {
			cmd: ["sh", "-c", `echo x > '${fx.engine}/Engine/Source/Probe.cpp'`],
			cwd: fx.game,
			run_dir: `${buildDir}/runs/run-2`,
		})?.reason,
	).toContain("engine-read-only");
	expect(call("mw_run_detached", { cmd: ubt, cwd: fx.engine })?.block).toBe(true);
	expect(call("mw_run_detached", { cmd: ubt, cwd: fx.engine, run_dir: `${fx.engine}/Engine/Saved/runs` })?.block).toBe(
		true,
	);
	process.stdout.write("[VERIFY] VC-007/VC-005: command_guards=PASS ubt_argv+run_dir+copy+source\n");
});

async function worker(taskPath: string, target: string) {
	const handlers = new Map<string, Array<(event: unknown) => unknown>>();
	const pi = {
		on(name: string, handler: (event: unknown) => unknown) {
			const list = handlers.get(name) ?? [];
			list.push(handler);
			handlers.set(name, list);
		},
		sendUserMessage() {},
		setActiveTools() {},
		registerTool() {},
	};
	vi.stubEnv("PI_WORKER_TASK", taskPath);
	process.chdir(target);
	await workerModeActivate(pi as unknown as ExtensionAPI);
	return {
		call(toolName: string, input: Record<string, unknown>) {
			for (const handler of handlers.get("tool_call") ?? []) {
				const result = handler({ type: "tool_call", toolCallId: "probe", toolName, input }) as
					| { block?: boolean; reason?: string }
					| undefined;
				if (result?.block) return result;
			}
			return undefined;
		},
		settle() {
			for (const handler of handlers.get("agent_end") ?? []) handler({ messages: [] });
			for (const handler of handlers.get("agent_settled") ?? []) handler({});
		},
	};
}

it("carries the artifact exception into the worker runtime without widening role or declared scope", async () => {
	const fx = fixture();
	const artifact = `${fx.engine}/${UBT_ARTIFACT_SUFFIXES[0]}/SourceFileCache.bin`;
	const shellTask = (name: string, face: string | undefined, type = "coding") => {
		const dir = path.join(fx.control, ".agenticdoc", "test", "workers", name);
		fs.mkdirSync(dir, { recursive: true });
		const taskPath = path.join(dir, "task.md");
		fs.writeFileSync(taskPath, `type: ${type}\n${face === undefined ? "" : `write_face: ${face}\n`}\nWork.\n`);
		return taskPath;
	};
	const declared = shellTask("artifact", artifact);
	const meta = parseTaskMd(declared);
	expect(meta.readOnlyWriteRoots).toEqual([fx.engine]);
	expect(meta.readOnlyArtifactRoots).toEqual(engineBuildArtifactRoots(fx.engine));
	expect(meta.readOnlyArtifactRoots).toHaveLength(UBT_ARTIFACT_SUFFIXES.length);
	const guard = await worker(declared, fx.game);
	try {
		expect(guard.call("write", { path: artifact, content: "x" })).toBeUndefined();
		expect(guard.call("edit", { path: artifact, oldText: "a", newText: "b" })).toBeUndefined();
		expect(guard.call("bash", { command: `echo x > "${artifact}"` })).toBeUndefined();
		expect(guard.call("write", { path: path.join(fx.engine, "Engine", "Source", "Probe.cpp") })?.reason).toContain(
			"engine-read-only",
		);
		expect(guard.call("write", { path: path.join(fx.game, "Unrelated.cpp") })?.reason).toContain("write-scope");
	} finally {
		guard.settle();
	}
	const narrowed = shellTask("narrowed", `${fx.game}/Plugin.cpp`);
	const narrowedGuard = await worker(narrowed, fx.game);
	try {
		expect(narrowedGuard.call("write", { path: path.join(fx.game, "Plugin.cpp") })).toBeUndefined();
		expect(narrowedGuard.call("write", { path: artifact })?.reason).toContain("write-scope");
	} finally {
		narrowedGuard.settle();
	}
	const research = shellTask("research", artifact, "research");
	const researchGuard = await worker(research, fx.game);
	try {
		expect(researchGuard.call("bash", { command: `echo x > "${artifact}"` })?.reason).toContain(
			"outside the worker write surface",
		);
	} finally {
		researchGuard.settle();
	}
	process.stdout.write("[VERIFY] VC-004/VC-006: artifact_runtime=PASS role_and_declared_scope_narrow\n");
});

it("checks all three artifact roots and legacy scope through the production worker shell guard", async () => {
	const fx = fixture();
	const artifacts = UBT_ARTIFACT_SUFFIXES.map((suffix) => `${fx.engine}/${suffix}/generated.bin`);
	const face = artifacts.map((target) => `  - ${target}`).join("\n");
	fs.writeFileSync(fx.taskPath, `type: coding\nwrite_face:\n${face}\n\nWork.\n`);
	const guard = await worker(fx.taskPath, fx.game);
	const ubt = `dotnet "${fx.engine}/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll" ProbeEditor Win64 Development`;
	try {
		for (const target of artifacts) {
			expect(guard.call("write", { path: target })).toBeUndefined();
			expect(guard.call("edit", { path: target })).toBeUndefined();
			expect(guard.call("bash", { command: `echo x > "${target}"` })).toBeUndefined();
		}
		expect(guard.call("bash", { command: ubt })).toBeUndefined();
		expect(
			guard.call("bash", { command: `${ubt}; echo x > "${fx.engine}/Engine/Source/Probe.cpp"` })?.reason,
		).toContain("engine-read-only");
		expect(
			guard.call("bash", { command: `echo UBT > "${fx.engine}/Engine/Config/BaseEngine.ini"` })?.reason,
		).toContain("engine-read-only");
	} finally {
		guard.settle();
	}
	const scopedTask = path.join(fx.control, ".agenticdoc", "test", "workers", "legacy-scope", "task.md");
	fs.mkdirSync(path.dirname(scopedTask), { recursive: true });
	fs.writeFileSync(scopedTask, `type: coding\nwrite_face:\n${face}\nwrite_scope:\n  - ${artifacts[0]}\n\nWork.\n`);
	const scoped = await worker(scopedTask, fx.game);
	try {
		expect(scoped.call("write", { path: artifacts[0] })).toBeUndefined();
		for (const target of artifacts.slice(1)) {
			expect(scoped.call("write", { path: target })?.block).toBe(true);
			expect(scoped.call("edit", { path: target })?.block).toBe(true);
			expect(scoped.call("bash", { command: `echo x > "${target}"` })?.block).toBe(true);
		}
	} finally {
		scoped.settle();
	}
	process.stdout.write("[VERIFY] VC-004/VC-006/VC-007: three_roots_runtime_and_scope=PASS worker_ubt_and_spoof\n");
});

it("keeps the artifact exception out of single, partition and engine_writable=true modes", () => {
	const fx = fixture();
	fs.writeFileSync(
		fx.config,
		JSON.stringify({ active: "dual", dual: { game: fx.game, engine: fx.engine, engine_writable: true } }),
	);
	const writable = workspaceWriteFaceOptions(fx.control);
	expect(writable.readOnlyRoots).toEqual([]);
	expect(writable.readOnlyAllowedRoots ?? []).toEqual([]);
	expect(parseWriteFaceEntries([`${fx.engine}/Engine/Source/Engine.cpp`], writable).kind).toBe("declared");
	const parent = path.join(fx.control, "Parent");
	const partition = path.join(fx.control, "Partition");
	fs.mkdirSync(parent);
	fs.mkdirSync(partition);
	fs.writeFileSync(fx.config, JSON.stringify({ active: "partition", partition: { parent, partition } }));
	const partitioned = workspaceWriteFaceOptions(fx.control);
	expect(partitioned.readOnlyRoots ?? []).toEqual([]);
	expect(partitioned.readOnlyAllowedRoots ?? []).toEqual([]);
	expect(parseWriteFaceEntries([`${parent}/Engine/Intermediate/Build/x.bin`], partitioned).kind).toBe("declared");
	fs.writeFileSync(fx.config, JSON.stringify({ mode: "single" }));
	const single = workspaceWriteFaceOptions(fx.control);
	expect(single).not.toHaveProperty("roots");
	expect(single).not.toHaveProperty("readOnlyAllowedRoots");
	process.stdout.write("[VERIFY] VC-006: boundary_preserved=PASS single=none partition=none writable=empty\n");
});
