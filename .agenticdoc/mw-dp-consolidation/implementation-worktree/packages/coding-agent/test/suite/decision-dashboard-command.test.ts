/**
 * decision-dashboard-command.test.ts — T12a read-only window entry
 * (mw-decision-dashboard AC-001/AC-017, VC-001/VC-015).
 *
 * The window's `/mw decide` face only knew `show` / `sign`, so every dp and
 * monitor command hit `unknown sub` before the watched-key requirement was even
 * reached (RQ-1: the dp preview splits off BEFORE the key resolution, otherwise
 * a generic pass-through would bypass the sign guard). This slice adds exactly
 * four read-only forwards — `dp list`, `dp show <id>`, `dp export`, `monitor` —
 * and nothing else: `dp on/off/set/refresh/check/apply/verify`, `export
 * --write`, `monitor status|stop` and any unknown tail argument are refused
 * before any spawn, so the authorization table and business executors see zero
 * writes from this entry.
 *
 * Layers (P-002: parser-only green would not prove the entry):
 *   1. pure parse + argv contract (`decideForwardArgs` is the single mapping, so
 *      `--write`/`--json`/`--live`/paths are unrepresentable),
 *   2. refusal paths through the real command function with a counting stub
 *      runner (zero spawns, zero writes),
 *   3. the REAL entry: the suite harness (faux provider) dispatches
 *      `/mw decide dp list|show|export` through the registered `/mw` command, the
 *      real `decideMw` runner spawns the real `mw.py decide`, and that output is
 *      compared against the Python CLI's own `--json` listing. Monitor is only
 *      routed: its Python CLI belongs to the undelivered T08, so a stub runner
 *      pins the argv and the assertion proves no service state/window is
 *      created — no browser and no shared service run in this test.
 *
 * Hermetic: every spawn runs under a throwaway HOME/USERPROFILE/
 * PI_CODING_AGENT_DIR with provider credentials masked, against a temp project
 * dir, so no real auth is read and no repo file is written.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionCommandContext, ExtensionUIContext } from "../../src/core/extensions/types.ts";
import {
	DECIDE_USAGE,
	decideForwardArgs,
	parseDecideArgs,
	registerMwCommands,
	runMwDecideCommand,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { decideMw, findMwPy, type MwCliResult } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, type Harness } from "./harness.ts";

/* The suite config swallows console.log from green tests; write the evidence
 * line straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

interface Notify {
	message: string;
	type: string;
}

const tmpDirs: string[] = [];
const harnesses: Harness[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const harness of harnesses.splice(0)) harness.cleanup();
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Fake command ctx: records notifications; `hasUI` is explicit because the
 * read-only forwards must work in headless (`-p`) windows too. No dialog. */
function fakeDecideCtx(opts: { hasUI?: boolean } = {}): { ctx: ExtensionCommandContext; notifications: Notify[] } {
	const notifications: Notify[] = [];
	const ctx = {
		hasUI: opts.hasUI ?? true,
		ui: {
			notify: (message: string, type?: string) => {
				notifications.push({ message, type: type ?? "info" });
			},
			confirm: async () => false,
			select: async () => undefined,
			input: async () => undefined,
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

/** Counting stub runner — the argv contract is provable without a spawn. */
function stubRunner(output = "stub output"): {
	calls: string[][];
	runner: (projectDir: string, args: string[]) => MwCliResult;
} {
	const calls: string[][] = [];
	const runner = (_projectDir: string, args: string[]): MwCliResult => {
		calls.push(args);
		return { ok: true, output };
	};
	return { calls, runner };
}

const CREDENTIAL_KEYS = ["TIMI_API_KEY", "TAI_PAT_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"] as const;

/** Run `fn` with every credential-bearing input the spawn could reach masked:
 * a throwaway HOME/USERPROFILE (Python's home), a throwaway pi agent dir (no
 * `.mw-py-path` sidecar), no MW_PY override, and provider keys unset. The real
 * mw.py is therefore resolved from this checkout, and a read-only dp path cannot
 * read the operator's auth files. Restored in `finally`. */
async function withIsolatedHome<T>(fn: () => Promise<T> | T): Promise<T> {
	const home = mkdtemp("mw-dd-home-");
	const saved = new Map<string, string | undefined>();
	for (const key of ["HOME", "USERPROFILE", "PI_CODING_AGENT_DIR", "MW_PY", ...CREDENTIAL_KEYS]) {
		saved.set(key, process.env[key]);
	}
	process.env.HOME = home;
	process.env.USERPROFILE = home;
	process.env.PI_CODING_AGENT_DIR = path.join(home, "agent");
	delete process.env.MW_PY;
	for (const key of CREDENTIAL_KEYS) delete process.env[key];
	try {
		return await fn();
	} finally {
		for (const [key, value] of saved) {
			if (value === undefined) delete process.env[key];
			else process.env[key] = value;
		}
	}
}

function sha256File(file: string): string {
	return createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

/** Harness extension factory: the production `/mw` command registration, with
 * NO watched key — the read-only faces must not need one. */
async function createCommandHarness(root: string): Promise<{ harness: Harness; notifications: Notify[] }> {
	const notifications: Notify[] = [];
	const harness = await createHarness({
		extensionFactories: [
			(pi) => {
				registerMwCommands(pi, root, new WorkerStore(root), {} as AckStore, { key: undefined }, root);
			},
		],
	});
	const ui = {
		notify: (message: string, type?: string) => {
			notifications.push({ message, type: type ?? "info" });
		},
		confirm: async () => false,
		select: async () => undefined,
		input: async () => undefined,
	} as unknown as ExtensionUIContext;
	await harness.session.bindExtensions({ uiContext: ui, mode: "tui" });
	harnesses.push(harness);
	return { harness, notifications };
}

describe("/mw decide dp read-only parsing (T12a)", () => {
	it("accepts exactly dp list / dp show <id> / dp export and maps the argv", () => {
		const list = parseDecideArgs("dp list");
		const show = parseDecideArgs("dp show dp3-worker-clarify");
		const exported = parseDecideArgs("dp export");

		expect(list).toEqual({ action: "dp-list" });
		expect(show).toEqual({ action: "dp-show", dp: "dp3-worker-clarify" });
		expect(exported).toEqual({ action: "dp-export" });
		expect(decideForwardArgs(list)).toEqual({ action: "dp-list", argv: ["dp", "list"] });
		expect(decideForwardArgs(show)).toEqual({ action: "dp-show", argv: ["dp", "show", "dp3-worker-clarify"] });
		expect(decideForwardArgs(exported)).toEqual({ action: "dp-export", argv: ["dp", "export"] });
		expect(decideForwardArgs(parseDecideArgs("monitor"))).toEqual({ action: "monitor", argv: ["monitor"] });
		// The read-only actions carry no argv of their own on the sign face.
		expect(decideForwardArgs({ action: "show" })).toBeNull();
		expect(decideForwardArgs({ action: "usage", error: "x" })).toBeNull();
		verify(
			`T12a parse-readonly: list=${JSON.stringify(decideForwardArgs(list)?.argv)} show=${JSON.stringify(
				decideForwardArgs(show)?.argv,
			)} export=${JSON.stringify(decideForwardArgs(exported)?.argv)}`,
		);
	});

	it("refuses every write/act face, --write, --live and unknown tails", () => {
		const refused = [
			"dp",
			"dp on dp1-dispatch-type",
			"dp off dp1-dispatch-type",
			"dp set dp1-dispatch-type mode=auto",
			"dp refresh",
			"dp check",
			"dp apply sign-final.md",
			"dp verify",
			"dp verify --live",
			"dp export --write",
			"dp export --json",
			"dp list --json",
			"dp list extra",
			"dp show",
			"dp show dp1 extra",
			"dp show --write",
			"dp bogus",
			"monitor status",
			"monitor stop",
			"monitor --url http://evil",
		];
		for (const text of refused) {
			const parsed = parseDecideArgs(text);
			expect(parsed.action, text).toBe("usage");
			expect(decideForwardArgs(parsed), text).toBeNull();
			if (parsed.action === "usage") expect(parsed.error.startsWith(DECIDE_USAGE), text).toBe(true);
		}
		// The pre-existing show/sign faces are untouched. A conclusion is no longer
		// a window input (the decision model produces it during the write), so the
		// sign face accepts only `--allow-empty` / `--key`.
		expect(parseDecideArgs("show")).toEqual({ action: "show" });
		expect(parseDecideArgs("sign --key k")).toEqual({ action: "sign", allowEmpty: false, key: "k" });
		expect(parseDecideArgs("sign continue").action).toBe("usage");
		const write = parseDecideArgs("dp export --write");
		expect(write.action === "usage" && write.error).toContain("read-only");
		verify(`T12a parse-refused: cases=${refused.length} sign_kept=true show_kept=true`);
	});

	it("refuses dp on/off/set/apply/verify with zero runner calls (AC-017)", async () => {
		const writes = [
			"dp on dp1-dispatch-type",
			"dp off dp1-dispatch-type",
			"dp set dp1-dispatch-type mode=auto",
			"dp apply .agenticdoc/k/evidence/review/sign-final.md",
			"dp verify --live",
			"dp export --write",
		];
		for (const text of writes) {
			const { calls, runner } = stubRunner();
			const { ctx, notifications } = fakeDecideCtx();
			await runMwDecideCommand(ctx, mkdtemp("mw-dd-refuse-"), text, { runner });
			expect(calls, text).toEqual([]);
			expect(notifications, text).toHaveLength(1);
			expect(notifications[0]?.type, text).toBe("warning");
		}
		verify(`T12a refusal-spawns: cases=${writes.length} runner_calls=0 auth_writes=0`);
	});
});

describe("/mw decide read-only forwards need no watched key (T12a)", () => {
	it("forwards dp list/export from a headless window without a watch key", async () => {
		for (const [text, argv] of [
			["dp list", ["dp", "list"]],
			["dp export", ["dp", "export"]],
		] as const) {
			const { calls, runner } = stubRunner("python text");
			const { ctx, notifications } = fakeDecideCtx({ hasUI: false });
			// Headless: `ctx.ui.notify` is a no-op, so the read-only text comes back
			// as the return value the `/mw` handler puts into the transcript
			// (mw-signoff-decide-only AC-007), not as a notification.
			const resultText = await runMwDecideCommand(ctx, "/proj", text, { runner, watchKey: () => undefined });
			expect(calls).toEqual([argv]);
			expect(notifications).toEqual([]);
			expect(resultText).toBe("python text");
		}
		verify(
			"T12a no-key: dp_list_argv=[dp,list] dp_export_argv=[dp,export] key_required=false headless_return_text=true",
		);
	});

	it("reports a Python failure verbatim at error level instead of throwing", async () => {
		const calls: string[][] = [];
		const runner = (_projectDir: string, args: string[]): MwCliResult => {
			calls.push(args);
			return { ok: false, error: "[mw decide dp show] unknown dp 'nope'" };
		};
		const { ctx, notifications } = fakeDecideCtx();
		await runMwDecideCommand(ctx, "/proj", "dp show nope", { runner });
		expect(calls).toEqual([["dp", "show", "nope"]]);
		expect(notifications[0]?.type).toBe("error");
		expect(notifications[0]?.message).toContain("unknown dp 'nope'");
		expect(notifications[0]?.message).toContain("dp show");
	});
});

describe("/mw decide monitor routing only (T12a, no window/service)", () => {
	it("forwards exactly `monitor`, once, and creates no monitor state", async () => {
		const root = mkdtemp("mw-dd-monitor-");
		const { calls, runner } = stubRunner("monitor reused at http://127.0.0.1:43170/");
		const { ctx, notifications } = fakeDecideCtx({ hasUI: false });

		// Headless: the routing result is the return value, not a notification.
		const resultText = await runMwDecideCommand(ctx, root, "monitor", { runner, watchKey: () => undefined });

		expect(calls).toEqual([["monitor"]]);
		expect(notifications).toEqual([]);
		expect(resultText).toBe("monitor reused at http://127.0.0.1:43170/");
		// Routing only: the window never starts the service, opens a browser or
		// creates the monitor identity/secret/lock by itself.
		for (const name of ["decide-monitor.json", "decide-monitor.secret", "decide-monitor.start.lock"]) {
			expect(fs.existsSync(path.join(root, ".mw", name)), name).toBe(false);
		}
		verify("T12a monitor: argv=[monitor] calls=1 state_files=0 browser_launched=false");
	});

	it("explains the CLI-only status/stop faces instead of forwarding them", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications } = fakeDecideCtx();
		await runMwDecideCommand(ctx, "/proj", "monitor stop", { runner });
		expect(calls).toEqual([]);
		expect(notifications[0]?.type).toBe("warning");
		expect(notifications[0]?.message).toContain("mw decide monitor status|stop");
	});
});

describe("/mw decide real entry through the harness (T12a)", () => {
	it("dp list in a key-less window equals the Python CLI's dp set (AC-001)", async () => {
		const root = mkdtemp("mw-dd-reallist-");
		const { harness, notifications } = await createCommandHarness(root);

		await withIsolatedHome(() => harness.session.prompt("/mw decide dp list"));

		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("info");
		const windowText = notifications[0]?.message ?? "";
		expect(windowText).not.toContain("unknown sub");

		const rows = windowText
			.split(/\r?\n/)
			.filter((line) => /^dp[0-9]/.test(line))
			.map((line) => line.split(/\s+/)[0] ?? "");
		expect(rows).toHaveLength(25);
		expect(windowText).toContain("25 decision point(s)");

		const cli = await withIsolatedHome(() => decideMw(root, ["dp", "list", "--json"]));
		expect(cli.ok).toBe(true);
		const payload = cli.ok ? (JSON.parse(cli.output) as { points: Array<{ id: string }> }) : { points: [] };
		const cliIds = payload.points.map((point) => point.id);
		expect(cliIds).toHaveLength(25);
		expect(rows).toEqual(cliIds);

		// The entry consumed no model turn: the faux provider was never asked.
		expect(harness.session.messages).toEqual([]);
		expect(harness.eventsOfType("turn_start")).toHaveLength(0);
		verify(
			`T12a real-dp-list: window_rows=${rows.length} cli_ids=${cliIds.length} equal=${
				JSON.stringify(rows) === JSON.stringify(cliIds)
			} unknown_sub=0 provider_turns=0`,
		);
	});

	it("dp show <id> and dp export reach the real CLI and write nothing (VC-001)", async () => {
		const root = mkdtemp("mw-dd-realshow-");
		const { harness, notifications } = await createCommandHarness(root);

		await withIsolatedHome(() => harness.session.prompt("/mw decide dp show dp1-dispatch-type"));
		expect(notifications).toHaveLength(1);
		const showText = notifications[0]?.message ?? "";
		expect(showText).toContain("dp1-dispatch-type (P2)");
		expect(showText).toContain("enabled=true mode=auto source=default");
		expect(showText).toContain("questions:");

		// `dp export` is stdout-only: the packaged registry must stay byte-identical.
		// The path comes from the runner's own mw.py resolution, so this pins the
		// file the real CLI would have rewritten with --write.
		const mwPy = await withIsolatedHome(() => findMwPy());
		expect(mwPy).not.toBeNull();
		const registry = path.join(path.dirname(mwPy ?? ""), "decide_registry.json");
		expect(fs.existsSync(registry)).toBe(true);
		const before = sha256File(registry);
		await withIsolatedHome(() => harness.session.prompt("/mw decide dp export"));
		const exportText = notifications.at(-1)?.message ?? "";
		expect(exportText).toContain("25 decision point(s)");
		expect(sha256File(registry)).toBe(before);
		expect(fs.existsSync(path.join(root, ".mw", "decide-points.json"))).toBe(false);
		expect(harness.session.messages).toEqual([]);
		verify(
			`T12a real-show/export: show_dp=dp1-dispatch-type export_points=25 registry_sha256=${before.slice(
				0,
				12,
			)} registry_unchanged=true points_table_written=false provider_turns=0`,
		);
	});

	it("the registered /mw dispatcher documents the read-only faces", async () => {
		const root = mkdtemp("mw-dd-usage-");
		const { harness, notifications } = await createCommandHarness(root);
		await harness.session.prompt("/mw bogus");
		const usageLine = notifications.at(-1)?.message ?? "";
		expect(usageLine).toContain("decide dp list|show <id>|export");
		expect(usageLine).toContain("decide monitor");
		// The sign face documents only `--allow-empty`/`--key`: no caller-supplied
		// conclusion survives (mw-signoff-decide-only).
		expect(usageLine).toContain("| decide show|sign [--allow-empty] [--key <k>]");
		expect(usageLine).not.toContain("<continue|narrow|revoke>");
		expect(DECIDE_USAGE.startsWith("Usage: /mw decide show | sign")).toBe(true);
		expect(DECIDE_USAGE).toContain("dp list | dp show <id> | dp export | monitor");
		verify(
			`T12a usage: usage_documents_dp=${usageLine.includes("decide dp list|show <id>|export")} usage_documents_monitor=${usageLine.includes(
				"decide monitor",
			)} legacy_sign_kept=${DECIDE_USAGE.startsWith("Usage: /mw decide show | sign")}`,
		);
	});
});
