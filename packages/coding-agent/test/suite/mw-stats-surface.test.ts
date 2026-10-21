/**
 * mw-stats-surface.test.ts — pi-window `/mw stats` surface
 * (mw-usage-monitor T-04, covers AC-006).
 *
 * The window owns no aggregation: `statsMw` forwards `stats <argv...>` to
 * mw.py verbatim. The ledger is machine-level, so the runner does NOT append
 * `--project=<controlRoot>` for `stats` (AC-028): a bare `/mw stats` is the
 * same machine-wide report as the bare CLI, and an explicit `--project` in the
 * argv survives instead of being overridden by a trailing append.
 * `runMwStatsCommand` splits the command tail verbatim (no flag parsing, no
 * rewriting) and maps ok -> info / failure -> error while keeping Python's
 * stderr in the notify text. The spawn tests reuse the rag precedent: a stub
 * `MW_PY` script prints its argv or writes stderr, so the forwarding contract
 * is pinned end to end without touching the real usage ledger.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import {
	MW_COMMAND_DESCRIPTION,
	registerMwCommands,
	runMwStatsCommand,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { PYTHON_EXE, statsMw } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

/* The suite config swallows console.log from green tests; write the evidence
 * line straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

/** Python is needed for the stub spawn tests (same probe as rag-window). */
const pythonAvailable = (() => {
	try {
		return spawnSync(PYTHON_EXE, ["-V"], { encoding: "utf8", timeout: 10_000 }).status === 0;
	} catch {
		return false;
	}
})();

const tmpDirs: string[] = [];
const originalMwPy = process.env.MW_PY;

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

afterEach(() => {
	if (originalMwPy === undefined) delete process.env.MW_PY;
	else process.env.MW_PY = originalMwPy;
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Stub `mw.py`: prints its argv as JSON (ok) or writes one stderr line and
 * exits 2 (fail), so both the forwarding and the stderr passthrough are
 * observable without a real ledger. */
function stubMw(root: string, kind: "ok" | "fail"): string {
	const file = path.join(root, `stub_mw_${kind}.py`);
	const body =
		kind === "ok"
			? ["import json, sys", "print(json.dumps(sys.argv[1:]))", ""]
			: [
					"import sys",
					"sys.stderr.write('[mw stats] invalid --since \\'zzz\\'; use 7d / 24h / 30m / YYYY-MM-DD\\n')",
					"sys.exit(2)",
					"",
				];
	fs.writeFileSync(file, body.join("\n"), "utf-8");
	return file;
}

interface Notify {
	message: string;
	type: string;
}

function fakeCtx(): { ctx: ExtensionCommandContext; notifications: Notify[] } {
	const notifications: Notify[] = [];
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

/** Minimal ExtensionAPI: `/mw` registration only needs registerCommand. */
function fakeCmdPi(): {
	pi: ExtensionAPI;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
} {
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const pi = {
		registerCommand: (
			name: string,
			def: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, def.handler);
		},
	} as unknown as ExtensionAPI;
	return { pi, commands };
}

/** Registered `/mw` handler bound to a throwaway control root. */
function mwHandler(root: string) {
	const { pi, commands } = fakeCmdPi();
	registerMwCommands(pi, root, new WorkerStore(root), {} as AckStore, { key: undefined }, root);
	const handler = commands.get("mw");
	if (!handler) throw new Error("/mw command not registered");
	return handler;
}

function projectArgs(argv: string[]): string[] {
	return argv.filter((arg) => arg.startsWith("--project"));
}

describe("/mw stats spawn contract (AC-006/AC-028)", () => {
	it.skipIf(!pythonAvailable)("forwards `stats` plus argv and never appends --project", () => {
		const root = mkdtemp("mw-stats-spawn-");
		process.env.MW_PY = stubMw(root, "ok");

		const bare = statsMw(root, []);
		if (!bare.ok) throw new Error(`statsMw failed: ${bare.error}`);
		const bareArgv = JSON.parse(bare.output) as string[];
		expect(bareArgv).toEqual(["stats"]);
		expect(projectArgs(bareArgv)).toEqual([]);

		const filtered = statsMw(root, ["--since", "24h", "--source", "pm"]);
		if (!filtered.ok) throw new Error(`statsMw failed: ${filtered.error}`);
		const filteredArgv = JSON.parse(filtered.output) as string[];
		expect(filteredArgv).toEqual(["stats", "--since", "24h", "--source", "pm"]);
		expect(projectArgs(filteredArgv)).toEqual([]);

		// An explicit scope is the caller's, not the runner's: exactly one
		// `--project`, and it is the one that was asked for.
		const scoped = statsMw(root, ["--project", "H:/x"]);
		if (!scoped.ok) throw new Error(`statsMw failed: ${scoped.error}`);
		const scopedArgv = JSON.parse(scoped.output) as string[];
		expect(scopedArgv).toEqual(["stats", "--project", "H:/x"]);
		expect(projectArgs(scopedArgv)).toEqual(["--project"]); // exactly one, no control root

		verify(
			`[VERIFY] AC-028: bare=${JSON.stringify(bareArgv)} filtered=${JSON.stringify(
				filteredArgv,
			)} scoped=${JSON.stringify(scopedArgv)} project_appends=${
				projectArgs(bareArgv).length + projectArgs(filteredArgv).length
			}`,
		);
	});
});

describe("/mw stats dispatch wiring (AC-006/AC-028)", () => {
	it.skipIf(!pythonAvailable)("the registered /mw command routes `stats` instead of the usage line", async () => {
		const root = mkdtemp("mw-stats-dispatch-");
		process.env.MW_PY = stubMw(root, "ok");
		const handler = mwHandler(root);
		const { ctx, notifications } = fakeCtx();

		await handler("stats", ctx);
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("info");
		expect(JSON.parse(notifications[0]?.message ?? "")).toEqual(["stats"]);

		await handler("stats --since 24h --source pm", ctx);
		const argv = JSON.parse(notifications[1]?.message ?? "") as string[];
		expect(argv).toEqual(["stats", "--since", "24h", "--source", "pm"]);
		expect(projectArgs(argv)).toEqual([]);
		expect(notifications.some((n) => n.message.startsWith("Usage: /mw build"))).toBe(false);

		verify(`[VERIFY] AC-028: dispatch_notifies=${notifications.length} argv=${JSON.stringify(argv)}`);
	});

	it("the usage尾行 documents stats", async () => {
		const root = mkdtemp("mw-stats-usage-");
		const handler = mwHandler(root);
		const { ctx, notifications } = fakeCtx();

		await handler("bogus", ctx);
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("warning");
		expect(notifications[0]?.message).toContain("| stats ");
		verify(`[VERIFY] AC-006: usage_mentions_stats=${notifications[0]?.message.includes("| stats ") ?? false}`);
	});
});

describe("/mw stats argument passthrough (AC-006)", () => {
	it("forwards the split argument tail verbatim (no parsing, no rewriting)", async () => {
		const calls: Array<[string, string[]]> = [];
		const { ctx, notifications } = fakeCtx();

		await runMwStatsCommand(ctx, "/proj", '--since 24h --source pm --key "my key"', (projectDir, args) => {
			calls.push([projectDir, args]);
			return { ok: true, output: "usage since ..." };
		});

		expect(calls).toEqual([["/proj", ["--since", "24h", "--source", "pm", "--key", "my key"]]]);
		expect(notifications).toEqual([{ message: "usage since ...", type: "info" }]);
		verify(`[VERIFY] AC-006: forwarded=${JSON.stringify(calls[0]?.[1])} level=${notifications[0]?.type}`);
	});

	it("a bare /mw stats forwards an empty tail (Python applies the defaults)", async () => {
		const calls: string[][] = [];
		const { ctx } = fakeCtx();
		await runMwStatsCommand(ctx, "/proj", "", (_projectDir, args) => {
			calls.push(args);
			return { ok: true, output: "ok" };
		});
		expect(calls).toEqual([[]]);
	});
});

describe("/mw stats failure surface (AC-006)", () => {
	it.skipIf(!pythonAvailable)("keeps Python stderr verbatim and notifies at error level", async () => {
		const root = mkdtemp("mw-stats-fail-");
		process.env.MW_PY = stubMw(root, "fail");
		const { ctx, notifications } = fakeCtx();

		const result = statsMw(root, ["--since", "zzz"]);
		expect(result.ok).toBe(false);
		const stderrText = result.ok ? "" : result.error;
		expect(stderrText).toContain("[mw stats] invalid --since 'zzz'");

		await runMwStatsCommand(ctx, root, "--since zzz");
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("error");
		expect(notifications[0]?.message).toContain("[mw stats] invalid --since 'zzz'");
		expect(notifications[0]?.message).toContain("7d / 24h / 30m / YYYY-MM-DD");

		verify(
			`[VERIFY] AC-006: spawn_ok=${String(result.ok)} level=${notifications[0]?.type} stderr_kept=${notifications[0]?.message.includes(
				"invalid --since",
			)}`,
		);
	});

	it("a throwing runner is reported as an error notify, never escapes", async () => {
		const { ctx, notifications } = fakeCtx();
		await runMwStatsCommand(ctx, "/proj", "", () => {
			throw new Error("spawn ENOENT [mw stats]");
		});
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("error");
		expect(notifications[0]?.message).toContain("spawn ENOENT [mw stats]");
		verify(`[VERIFY] AC-006: throw_notify=${notifications[0]?.type} text_kept=true`);
	});
});

describe("/mw command description documents stats (AC-006)", () => {
	it("the registered description names the stats subcommand", () => {
		expect(MW_COMMAND_DESCRIPTION).toContain("stats");
		verify(`[VERIFY] AC-006: mw_description_has_stats=${MW_COMMAND_DESCRIPTION.includes("stats")}`);
	});
});
