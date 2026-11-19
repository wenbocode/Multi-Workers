import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import { registerMwCommands, windowClaimId } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { PYTHON_EXE, pmStateMw, thinkingMw } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";

vi.mock("node:child_process", () => ({ spawn: vi.fn(), spawnSync: vi.fn() }));

const mwPy = fileURLToPath(new URL("../../../multi-workers/mw.py", import.meta.url));
const compactor = path.join(path.dirname(mwPy), "pm_state.py");
const project = path.resolve("control root");
const summary = path.join(project, "handoff with spaces.md");
const temp = fileURLToPath(new URL("../../../../.tmp/", import.meta.url));

beforeEach(() => {
	vi.stubEnv("PI_CODING_AGENT_DIR", path.join(temp, "no-global-pm-state-config"));
});

afterEach(() => {
	vi.unstubAllEnvs();
	vi.resetAllMocks();
});

it.each(["owned", "foreign", "busy"])(
	"starts bare compaction only for the idle owning window ($case)",
	async (mode) => {
		vi.stubEnv("MW_PY", mwPy);
		fs.mkdirSync(temp, { recursive: true });
		const control = fs.mkdtempSync(path.join(temp, "pm-state-slash-test-"));
		const root = path.join(control, ".agenticdoc");
		const dir = path.join(root, "sample");
		try {
			fs.mkdirSync(dir, { recursive: true });
			fs.writeFileSync(path.join(dir, "pm-state.md"), "current bytes\n");
			const claim = windowClaimId();
			const index = {
				readAuthorityRows: () => [
					{ key: "sample", status: "active", phase: "EXECUTE", claimId: mode === "foreign" ? "other:1" : claim },
				],
			} as unknown as IndexStore;
			const registerCommand = vi.fn<ExtensionAPI["registerCommand"]>();
			const registerTool = vi.fn<ExtensionAPI["registerTool"]>();
			const sendUserMessage = vi.fn();
			const setActiveTools = vi.fn();
			const pi = {
				registerCommand,
				registerTool,
				sendUserMessage,
				setActiveTools,
				getActiveTools: () => [],
				on: vi.fn(),
			};
			registerMwCommands(pi as unknown as ExtensionAPI, control, {} as never, {} as never, {} as never, root, index);
			const command = registerCommand.mock.calls[0][1];
			const tool = registerTool.mock.calls[0][0];
			const ctx = { isIdle: () => mode !== "busy", ui: { notify: vi.fn() } } as unknown as ExtensionCommandContext;
			const submit = (request: string) =>
				tool.execute("call", { request, summary: "reviewed body" }, undefined, undefined, ctx);
			await expect(submit("1")).rejects.toThrow("No matching");
			await command.handler("pm-state compact", ctx);
			expect(spawnSync).not.toHaveBeenCalled();
			if (mode !== "owned") {
				expect(sendUserMessage).not.toHaveBeenCalled();
				return;
			}
			expect(sendUserMessage).toHaveBeenCalledWith(expect.stringContaining("submit_pm_state_summary"));
			expect(setActiveTools).toHaveBeenCalledWith(["submit_pm_state_summary"]);
			vi.mocked(spawnSync).mockImplementation(() => ({
				pid: 1,
				status: 0,
				stdout: '{"applied":true}',
				stderr: "",
				signal: null,
				output: [],
			}));
			await expect(submit("1")).resolves.toMatchObject({ content: [{ text: '{"applied":true}' }] });
			expect(spawnSync).toHaveBeenCalledExactlyOnceWith(
				PYTHON_EXE,
				[
					compactor,
					"compact",
					"--key",
					"sample",
					"--summary",
					"-",
					"--apply",
					createHash("sha256").update("current bytes\n").digest("hex"),
					"--window-claim-id",
					claim,
					`--project=${control}`,
				],
				{ encoding: "utf8", timeout: 30_000, input: "reviewed body" },
			);
			await expect(submit("1")).rejects.toThrow("No matching");
		} finally {
			fs.rmSync(control, { recursive: true, force: true });
		}
	},
);

it.each([
	{ args: "", status: 0, stdout: '{"applied":false}', stderr: "", level: "info" },
	{ args: ` --apply ${"1".repeat(64)}`, status: 0, stdout: '{"applied":true}', stderr: "", level: "info" },
	{ args: " --apply stale", status: 2, stdout: "", stderr: "pm-state: changed since preview", level: "error" },
])("runs the registered pm-state command ($args)", async ({ args, status, stdout, stderr, level }) => {
	vi.stubEnv("MW_PY", mwPy);
	vi.mocked(spawnSync).mockImplementation(() => ({ pid: 1, status, stdout, stderr, signal: null, output: [] }));
	const registerCommand = vi.fn<ExtensionAPI["registerCommand"]>();
	registerMwCommands(
		{ registerCommand } as unknown as ExtensionAPI,
		project,
		{} as never,
		{} as never,
		{} as never,
		path.join(project, ".agenticdoc"),
	);
	const command = registerCommand.mock.calls.find(([name]) => name === "mw")?.[1];
	if (!command) throw new Error("The /mw command was not registered");
	const notify = vi.fn();
	const ctx = { ui: { notify } } as unknown as ExtensionCommandContext;
	await command.handler(`pm-state compact --key sample --summary "${summary}"${args}`, ctx);
	expect(spawnSync).toHaveBeenCalledExactlyOnceWith(
		PYTHON_EXE,
		[
			compactor,
			"compact",
			"--key",
			"sample",
			"--summary",
			summary,
			...args.trim().split(/\s+/).filter(Boolean),
			`--project=${project}`,
		],
		{ encoding: "utf8", timeout: 30_000 },
	);
	expect(notify).toHaveBeenCalledWith(stdout || stderr, level);
	expect(command.description).toContain("pm-state compact");
});

it("uses the dedicated compactor when the installed MW release has no pm-state command", () => {
	fs.mkdirSync(temp, { recursive: true });
	const agent = fs.mkdtempSync(path.join(temp, "pm-state-runtime-test-"));
	const extensions = path.join(agent, "extensions");
	const legacy = path.join(agent, "mw.py");
	vi.stubEnv("PI_CODING_AGENT_DIR", agent);
	vi.stubEnv("MW_PY", legacy);
	vi.mocked(spawnSync).mockImplementation(() => ({
		pid: 1,
		status: 0,
		stdout: "ok",
		stderr: "",
		signal: null,
		output: [],
	}));
	fs.mkdirSync(extensions);
	fs.writeFileSync(legacy, "# Older MW release\n");
	fs.writeFileSync(path.join(extensions, ".mw-pm-state-path"), `${compactor}\n`);
	try {
		expect(pmStateMw(project, ["compact", "--help"])).toEqual({ ok: true, output: "ok" });
		expect(thinkingMw(project, ["show"])).toEqual({ ok: true, output: "ok" });
		expect(vi.mocked(spawnSync).mock.calls.map((call) => call[1])).toEqual([
			[compactor, "compact", "--help", `--project=${project}`],
			[legacy, "thinking", "show", `--project=${project}`],
		]);
	} finally {
		fs.unlinkSync(path.join(extensions, ".mw-pm-state-path"));
		fs.unlinkSync(legacy);
		fs.rmdirSync(extensions);
		fs.rmdirSync(agent);
	}
});
