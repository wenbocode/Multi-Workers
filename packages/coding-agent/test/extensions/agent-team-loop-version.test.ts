import * as path from "node:path";
import { expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";

it("queries the global default and registered windows from the real /mw command", async () => {
	const project = path.resolve("version test project");
	const registerCommand = vi.fn<ExtensionAPI["registerCommand"]>();
	const exec = vi.fn<ExtensionAPI["exec"]>().mockResolvedValue({
		code: 0,
		stdout: "全局默认 MW\n当前 pi 窗口\n已注册在线窗口",
		stderr: "",
		killed: false,
	});
	const pi = { registerCommand, exec } as unknown as ExtensionAPI;
	registerMwCommands(pi, project, {} as never, {} as never, { key: undefined }, path.join(project, ".agenticdoc"));
	const command = registerCommand.mock.calls.find(([name]) => name === "mw")?.[1];
	expect(command?.description).toContain("version");
	const notify = vi.fn();
	await command?.handler("version", { ui: { notify } } as unknown as ExtensionCommandContext);
	expect(exec).toHaveBeenCalledWith(
		expect.any(String),
		expect.arrayContaining([
			expect.stringMatching(/mw_version\.py$/),
			`--project=${project}`,
			`--pi-window=${process.pid}`,
			`--pi-cli=${process.argv[1]}`,
		]),
		expect.objectContaining({ cwd: project }),
	);
	expect(notify).toHaveBeenCalledWith("全局默认 MW\n当前 pi 窗口\n已注册在线窗口", "info");
});
