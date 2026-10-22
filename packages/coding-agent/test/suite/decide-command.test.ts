/**
 * decide-command.test.ts — `/mw decide show|sign` (FIX-Q, user ruling 2026-10-21).
 *
 * The user ruled that the sign-off entry point moves into the pi window as
 * option (B): `/mw decide sign` shows the preview, `ctx.ui.confirm` collects one
 * human click, and only then does the window forward the write with the Python
 * side's explicit `--human-confirmed` exemption. The guard-rail semantics drop
 * from "an agent cannot sign at all" to "signing on purpose means forging a
 * flag, and the file records `signed_via: tui`" — tamper-evidence, not
 * tamper-proof.
 *
 * Everything here is hermetic: the runner is a counting stub (no spawn, no
 * network) and the ctx is a fake with a recording `notify` / `confirm`. The
 * preview payload mirrors `mw decide sign --json` (facts + the three
 * per-conclusion verdicts), and Python stays authoritative for the real verdict
 * and the machine lines.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import {
	DECIDE_CONCLUSIONS,
	DECIDE_USAGE,
	parseDecideArgs,
	registerMwCommands,
	runMwDecideCommand,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import type { MwCliResult } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

/* The suite config swallows console.log from green tests; write the evidence
 * line straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

const SHA = "0123456789abcdef0123456789abcdef";
const WRITE_OUTPUT = "wrote /proj/.agenticdoc/k/evidence/review/sign-final.md";

interface Notify {
	message: string;
	type: string;
}

interface ConfirmCall {
	title: string;
	message: string;
}

interface FakeDecideCtx {
	ctx: ExtensionCommandContext;
	notifications: Notify[];
	confirms: ConfirmCall[];
}

/** Fake command ctx: `notify` records, `confirm` records and answers with
 * `confirmResult` — no real dialog exists in a test. */
function fakeDecideCtx(opts: { hasUI?: boolean; confirmResult?: boolean } = {}): FakeDecideCtx {
	const notifications: Notify[] = [];
	const confirms: ConfirmCall[] = [];
	const confirmResult = opts.confirmResult ?? true;
	const ctx = {
		hasUI: opts.hasUI ?? true,
		ui: {
			notify: (message: string, type?: string) => {
				notifications.push({ message, type: type ?? "" });
			},
			confirm: async (title: string, message: string) => {
				confirms.push({ title, message });
				return confirmResult;
			},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications, confirms };
}

/** One `mw decide sign --key <k> --json` preview payload (facts + verdicts). */
function previewPayload(overrides: Record<string, unknown> = {}): string {
	return JSON.stringify({
		conclusion: null,
		ok: null,
		problems: [],
		facts: {
			key: "k",
			counted_rows: 1,
			n_available: 1,
			n_acted: 1,
			n_escalated: 0,
			engines: { "timi-decisions/jev-latest/api": 1 },
			sha256: SHA,
			chain_ok: true,
			p0_open: [],
			p0_source: "config",
			rows: [],
		},
		path: null,
		verdicts: {
			continue: { ok: true, problems: [] },
			narrow: { ok: true, problems: [] },
			revoke: { ok: true, problems: [] },
		},
		...overrides,
	});
}

/** Counting stub runner: preview argv gets the preview payload, the write argv
 * (only it carries `--human-confirmed`) gets the `wrote <path>` line. */
function stubRunner(opts: { preview?: string; write?: MwCliResult } = {}): {
	calls: string[][];
	runner: (projectDir: string, args: string[]) => MwCliResult;
} {
	const calls: string[][] = [];
	const preview = opts.preview ?? previewPayload();
	const runner = (_projectDir: string, args: string[]): MwCliResult => {
		calls.push(args);
		if (args.includes("--human-confirmed")) return opts.write ?? { ok: true, output: WRITE_OUTPUT };
		return { ok: true, output: preview };
	};
	return { calls, runner };
}

const tmpDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

describe("/mw decide argument parsing (FIX-Q)", () => {
	it("accepts the six documented shapes and rejects the four malformed ones", () => {
		const empty = parseDecideArgs("");
		const show = parseDecideArgs("show");
		const full = parseDecideArgs('sign continue --reason "dp3 held up" --allow-empty --key k');
		const missing = parseDecideArgs("sign");
		const invalid = parseDecideArgs("sign approve");
		const unknown = parseDecideArgs("bogus");

		expect(empty).toEqual({ action: "show" });
		expect(show).toEqual({ action: "show" });
		expect(full).toEqual({
			action: "sign",
			conclusion: "continue",
			reason: "dp3 held up",
			allowEmpty: true,
			key: "k",
		});
		for (const parsed of [missing, invalid, unknown]) expect(parsed.action).toBe("usage");
		expect(missing.action === "usage" && missing.error).toContain("needs a conclusion");
		expect(invalid.action === "usage" && invalid.error).toContain("invalid conclusion 'approve'");
		expect(unknown.action === "usage" && unknown.error).toContain("unknown sub 'bogus'");
		// A flag without a value and a stray positional are usage errors too.
		const noValue = parseDecideArgs("sign narrow --reason");
		const stray = parseDecideArgs("sign narrow extra");
		const showArg = parseDecideArgs("show --key k");
		for (const parsed of [noValue, stray, showArg]) expect(parsed.action).toBe("usage");

		verify(
			`FIX-Q parse: empty=${JSON.stringify(empty)} show=${JSON.stringify(show)} full=${JSON.stringify(
				full,
			)} usage_missing=${missing.action} usage_invalid=${invalid.action} usage_unknown=${unknown.action} conclusions=${DECIDE_CONCLUSIONS.join("|")}`,
		);
	});
});

describe("/mw decide refuses without an interactive TUI (FIX-Q)", () => {
	it("hasUI=false notifies a warning and never calls the runner", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications } = fakeDecideCtx({ hasUI: false });

		await runMwDecideCommand(ctx, "/proj", "sign continue --key k", {
			runner,
			watchKey: () => "k",
		});

		expect(calls).toEqual([]);
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("warning");
		expect(notifications[0]?.message).toContain("需要交互 TUI");
		verify(`FIX-Q hasUI: runner_calls=${calls.length} level=${notifications[0]?.type}`);
	});
});

describe("/mw decide show is a read-only preview (FIX-Q)", () => {
	it("forwards `sign --key <k> --json` and renders the facts without writing", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications, confirms } = fakeDecideCtx();

		await runMwDecideCommand(ctx, "/proj", "show", { runner, watchKey: () => "k" });

		expect(calls).toEqual([["sign", "--key", "k", "--json"]]);
		expect(confirms).toEqual([]);
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("info");
		const message = notifications[0]?.message ?? "";
		expect(message).toContain("counted_rows=1 available=1 acted=1 escalated=0");
		expect(message).toContain("engines:");
		expect(message).toContain("timi-decisions/jev-latest/api=1");
		expect(message).toContain("verdict continue: ok");
		expect(message).toContain("verdict narrow: ok");
		expect(message).toContain("verdict revoke: ok");
		expect(message).toContain(SHA.slice(0, 12));
		expect(message).toContain("p0-open: -");
		expect(message).toContain("preview only");
		verify(
			`FIX-Q show: argv=${JSON.stringify(calls[0])} sha12=${SHA.slice(0, 12)} writes=${
				calls.filter((args) => args.includes("--human-confirmed")).length
			} verdict_lines=3`,
		);
	});
});

describe("/mw decide sign refuses before the dialog (FIX-Q)", () => {
	it("a failing preview verdict notifies the problems, no confirm, no write argv", async () => {
		const refused = previewPayload({
			verdicts: {
				continue: {
					ok: false,
					problems: ["N=0: no decide row for this key in the archive", "engine mismatch at seq 2"],
				},
				narrow: { ok: true, problems: [] },
				revoke: { ok: true, problems: [] },
			},
		});
		const { calls, runner } = stubRunner({ preview: refused });
		const { ctx, notifications, confirms } = fakeDecideCtx();

		await runMwDecideCommand(ctx, "/proj", "sign continue --key k", { runner });

		expect(confirms).toEqual([]);
		expect(calls).toEqual([["sign", "--key", "k", "--json"]]);
		expect(notifications[0]?.type).toBe("error");
		const message = notifications[0]?.message ?? "";
		expect(message).toContain("N=0: no decide row for this key in the archive");
		expect(message).toContain("engine mismatch at seq 2");
		expect(message).toContain("零写入");
		verify(
			`FIX-Q sign-refused: confirms=${confirms.length} write_calls=${
				calls.filter((args) => args.includes("--human-confirmed")).length
			} level=${notifications[0]?.type}`,
		);
	});

	it("a top-level problems list is honoured the same way (older preview shape)", async () => {
		const { calls, runner } = stubRunner({
			preview: previewPayload({ verdicts: undefined, problems: ["archive hash chain is broken"] }),
		});
		const { ctx, notifications, confirms } = fakeDecideCtx();

		await runMwDecideCommand(ctx, "/proj", "sign narrow --key k", { runner });

		expect(confirms).toEqual([]);
		expect(calls).toHaveLength(1);
		expect(notifications[0]?.message).toContain("archive hash chain is broken");
	});
});

describe("/mw decide sign confirm dialog (FIX-Q)", () => {
	it("cancelling writes nothing and notifies `cancelled, nothing written`", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications, confirms } = fakeDecideCtx({ confirmResult: false });

		await runMwDecideCommand(ctx, "/proj", "sign narrow --key k", { runner });

		expect(confirms).toHaveLength(1);
		expect(confirms[0]?.title).toContain("确认签收 k");
		expect(confirms[0]?.message).toContain(`rows_sha256=${SHA.slice(0, 12)}`);
		expect(confirms[0]?.message).toContain("conclusion=narrow");
		expect(calls).toEqual([["sign", "--key", "k", "--json"]]);
		const last = notifications.at(-1);
		expect(last?.message).toBe("cancelled, nothing written");
		expect(last?.type).toBe("info");
		verify(`FIX-Q cancel: confirms=${confirms.length} write_calls=${calls.length - 1} last=${last?.message}`);
	});

	it("confirming forwards the exact write argv with --human-confirmed", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications, confirms } = fakeDecideCtx({ confirmResult: true });

		await runMwDecideCommand(ctx, "/proj", "sign continue --key k", { runner });

		expect(confirms).toHaveLength(1);
		expect(calls).toHaveLength(2);
		expect(calls[1]).toEqual(["sign", "--key", "k", "--conclusion", "continue", "--human-confirmed"]);
		const last = notifications.at(-1);
		expect(last?.type).toBe("info");
		expect(last?.message).toContain("已签收 k");
		expect(last?.message).toContain("/proj/.agenticdoc/k/evidence/review/sign-final.md");
		expect(last?.message).toContain("advance_phase.py");
		verify(
			`FIX-Q write: argv=${JSON.stringify(calls[1])} level=${last?.type} path_echoed=${
				last?.message.includes("sign-final.md") ?? false
			}`,
		);
	});

	it("the reason/allowEmpty variant keeps the flag order and previews with --allow-empty", async () => {
		const { calls, runner } = stubRunner();
		const { ctx } = fakeDecideCtx({ confirmResult: true });

		await runMwDecideCommand(ctx, "/proj", 'sign continue --reason "dp3 held up" --allow-empty', {
			runner,
			watchKey: () => "k",
		});

		expect(calls[0]).toEqual(["sign", "--key", "k", "--json", "--allow-empty"]);
		expect(calls[1]).toEqual([
			"sign",
			"--key",
			"k",
			"--conclusion",
			"continue",
			"--human-confirmed",
			"--reason",
			"dp3 held up",
			"--allow-empty",
		]);
		verify(`FIX-Q write-variant: argv=${JSON.stringify(calls[1])}`);
	});

	it("a write failure notifies Python's text at error level and never throws", async () => {
		const { calls, runner } = stubRunner({
			write: { ok: false, error: "[mw decide sign] cannot write ...: refusing inside an agent session" },
		});
		const { ctx, notifications } = fakeDecideCtx({ confirmResult: true });

		await runMwDecideCommand(ctx, "/proj", "sign continue --key k", { runner });

		expect(calls).toHaveLength(2);
		const last = notifications.at(-1);
		expect(last?.type).toBe("error");
		expect(last?.message).toContain("refusing inside an agent session");
	});

	it("a preview that is not JSON notifies the raw tail instead of guessing", async () => {
		const { calls, runner } = stubRunner({ preview: "Traceback (most recent call last):\nValueError: boom" });
		const { ctx, notifications, confirms } = fakeDecideCtx();

		await runMwDecideCommand(ctx, "/proj", "sign narrow --key k", { runner });

		expect(confirms).toEqual([]);
		expect(calls).toHaveLength(1);
		expect(notifications[0]?.type).toBe("error");
		expect(notifications[0]?.message).toContain("ValueError: boom");
	});
});

describe("/mw decide key resolution (FIX-Q)", () => {
	it("without --key and without a watched key it is a usage error and spawns nothing", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications } = fakeDecideCtx();

		await runMwDecideCommand(ctx, "/proj", "sign continue", {
			runner,
			watchKey: () => undefined,
		});

		expect(calls).toEqual([]);
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("warning");
		expect(notifications[0]?.message).toContain("无法确定 key，请给 --key");
		verify(`FIX-Q no-key: runner_calls=${calls.length} level=${notifications[0]?.type}`);
	});
});

describe("/mw decide dispatcher wiring (FIX-Q)", () => {
	it("the registered /mw command routes `decide` and the usage line documents it", async () => {
		const root = mkdtemp("mw-decide-dispatch-");
		const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
		const pi = {
			registerCommand: (
				name: string,
				def: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
			) => {
				commands.set(name, def.handler);
			},
		} as unknown as ExtensionAPI;
		registerMwCommands(pi, root, new WorkerStore(root), {} as AckStore, { key: undefined }, root);
		const handler = commands.get("mw");
		if (!handler) throw new Error("/mw command not registered");

		// hasUI=false makes the decide branch refuse before any spawn, so the
		// routing is provable without python (the rag/stats precedent).
		const headless = fakeDecideCtx({ hasUI: false });
		await handler("decide sign continue", headless.ctx);
		expect(headless.notifications).toHaveLength(1);
		expect(headless.notifications[0]?.message).toContain("需要交互 TUI");

		const usage = fakeDecideCtx({ hasUI: true });
		await handler("bogus", usage.ctx);
		const usageLine = usage.notifications[0]?.message ?? "";
		expect(usageLine).toContain("| decide show|sign <continue|narrow|revoke>");
		expect(usageLine).toContain("[--allow-empty] [--key <k>]");
		verify(
			`FIX-Q dispatch: routed=${headless.notifications.length === 1} usage_has_decide=${usageLine.includes(
				"| decide show|sign",
			)} usage_export=${DECIDE_USAGE.startsWith("Usage: /mw decide show | sign")}`,
		);
	});
});
