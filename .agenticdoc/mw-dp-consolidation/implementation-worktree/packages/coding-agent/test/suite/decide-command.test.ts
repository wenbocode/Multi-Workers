/**
 * decide-command.test.ts — `/mw decide show|sign` (mw-signoff-decide-only).
 *
 * The decision model signs; nothing else does. The window face is two argv
 * shapes plus one output split:
 *   - preview: `sign --key <k> --dry-run --json` (strictly zero-write: no
 *     decision-model call, no archive row, no sign-off file),
 *   - write:   `sign --key <k> --json` — Python asks the decision model and
 *     writes only when it answers. No caller-supplied conclusion, no
 *     `--human-confirmed` exemption, no `--auto` (it would persist
 *     `signoff: auto` over a project's `signoff: disable`), no `--project`
 *     (`decideMw` appends the control root),
 *   - `exit 0` is NOT "signed": the write counts as signed only when stdout
 *     carries a `signed_via:` line or the JSON payload a non-null `path`.
 *     Otherwise the run is reported as unsigned with Python's own reason
 *     (decision model unavailable / `signoff: disable` / not required).
 *
 * Headless (`-p` / worker) is supported on purpose: the runner still runs and
 * the result text comes back as the return value, because `ctx.ui.notify` is a
 * no-op there — the `/mw` handler puts that text into the transcript instead
 * (AC-007, no silent loss).
 *
 * Everything here is hermetic: the runner is a counting stub (no spawn, no
 * network) and the ctx is a fake with a recording `notify`. The preview payload
 * mirrors `mw decide sign --dry-run --json` (facts + the three per-conclusion
 * verdicts), and Python stays authoritative for the real verdict and the
 * machine lines.
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
const SIGNED_PATH = "/proj/.agenticdoc/k/evidence/review/sign-final.md";
const PREVIEW_ARGV = ["sign", "--key", "k", "--dry-run", "--json"];
const WRITE_ARGV = ["sign", "--key", "k", "--json"];

interface Notify {
	message: string;
	type: string;
}

interface FakeDecideCtx {
	ctx: ExtensionCommandContext;
	notifications: Notify[];
}

/** Fake command ctx: `notify` records; `hasUI` decides whether it is called at
 * all (the production `reportDecide` records nothing when there is no UI).
 * There is no dialog any more — `confirm` exists only to prove nobody asks. */
function fakeDecideCtx(opts: { hasUI?: boolean } = {}): FakeDecideCtx {
	const notifications: Notify[] = [];
	const ctx = {
		hasUI: opts.hasUI ?? true,
		ui: {
			notify: (message: string, type?: string) => {
				notifications.push({ message, type: type ?? "" });
			},
			confirm: async () => {
				throw new Error("no confirmation dialog exists on the sign-off face");
			},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

/** One `mw decide sign --dry-run --json` payload (facts + verdicts). */
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

/** A signed `--json` write payload: Python reports the written `path` and the
 * conclusion the decision model produced (no `signed_via` field in JSON). */
function signedWritePayload(): string {
	return previewPayload({
		conclusion: "continue",
		ok: true,
		path: SIGNED_PATH,
	});
}

/** Counting stub runner: `--dry-run` gets the preview payload, the bare write
 * argv gets a signed write. Every call is recorded verbatim, so the argv
 * contract (no `--auto` / `--project` / `--human-confirmed` / `--conclusion`)
 * is provable without a spawn. */
function stubRunner(opts: { preview?: MwCliResult; write?: MwCliResult } = {}): {
	calls: string[][];
	runner: (projectDir: string, args: string[]) => MwCliResult;
} {
	const calls: string[][] = [];
	const preview = opts.preview ?? { ok: true, output: previewPayload() };
	const write = opts.write ?? { ok: true, output: signedWritePayload() };
	const runner = (_projectDir: string, args: string[]): MwCliResult => {
		calls.push(args);
		return args.includes("--dry-run") ? preview : write;
	};
	return { calls, runner };
}

/** The write-side argv only (the calls without `--dry-run`). */
function writeCalls(calls: string[][]): string[][] {
	return calls.filter((args) => !args.includes("--dry-run"));
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

describe("/mw decide argument parsing (mw-signoff-decide-only)", () => {
	it("accepts the documented shapes and rejects the malformed ones", () => {
		const empty = parseDecideArgs("");
		const show = parseDecideArgs("show");
		const bare = parseDecideArgs("sign");
		const keyed = parseDecideArgs("sign --key k");
		const allowEmpty = parseDecideArgs("sign --allow-empty --key k");
		// A conclusion is no longer a window input: the decision model produces it
		// during the write, so any positional (including a valid conclusion name)
		// is a usage error.
		const conclusion = parseDecideArgs("sign continue");
		const reason = parseDecideArgs('sign --reason "dp3 held up"');
		const stray = parseDecideArgs("sign extra");
		const noValue = parseDecideArgs("sign --key");
		const showArg = parseDecideArgs("show --key k");
		const unknown = parseDecideArgs("bogus");

		expect(empty).toEqual({ action: "show" });
		expect(show).toEqual({ action: "show" });
		expect(bare).toEqual({ action: "sign", allowEmpty: false, key: undefined });
		expect(keyed).toEqual({ action: "sign", allowEmpty: false, key: "k" });
		expect(allowEmpty).toEqual({ action: "sign", allowEmpty: true, key: "k" });
		for (const parsed of [conclusion, reason, stray, noValue, showArg, unknown]) {
			expect(parsed.action).toBe("usage");
		}
		expect(conclusion.action === "usage" && conclusion.error).toContain("unexpected argument 'continue'");
		expect(noValue.action === "usage" && noValue.error).toContain("--key needs a value");
		expect(unknown.action === "usage" && unknown.error).toContain("unknown sub 'bogus'");
		verify(
			`parse: empty=${JSON.stringify(empty)} keyed=${JSON.stringify(keyed)} allow_empty=${JSON.stringify(
				allowEmpty,
			)} usage_conclusion=${conclusion.action} usage_flag=${noValue.action} usage_unknown=${unknown.action} verdict_keys=${DECIDE_CONCLUSIONS.join("|")}`,
		);
	});
});

describe("/mw decide sign is headless-capable (AC-007)", () => {
	it("headless sign runs and reports through the return value", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications } = fakeDecideCtx({ hasUI: false });

		const text = await runMwDecideCommand(ctx, "/proj", "sign --key k", { runner, watchKey: () => "k" });

		// The runner runs in full (preview + write): no `hasUI` gate exists.
		expect(calls).toEqual([PREVIEW_ARGV, WRITE_ARGV]);
		// No UI → notify is never called, but nothing is lost: the same text is
		// the return value the `/mw` handler puts into the transcript.
		expect(notifications).toEqual([]);
		expect(text).toContain("已签收 k");
		expect(text).toContain("signed_via: auto-decide");
		expect(text).toContain(SIGNED_PATH);
		verify(
			`headless-sign: calls=${calls.length} preview=${JSON.stringify(calls[0])} write=${JSON.stringify(
				calls[1],
			)} notifies=0 signed_via_echoed=${text.includes("signed_via:")}`,
		);
	});

	it("exit 0 without a signed_via line is reported as not signed", async () => {
		// AC-005: `exit 0` also covers "the decision model was unavailable" and
		// "`signoff: disable`", both of which write no file.
		const unsigned =
			"signoff=auto but no conclusion available (decision model unavailable (no credentials)); sign-off not required";
		const { calls, runner } = stubRunner({ write: { ok: true, output: unsigned } });
		const { ctx, notifications } = fakeDecideCtx({ hasUI: false });

		const text = await runMwDecideCommand(ctx, "/proj", "sign --key k", { runner, watchKey: () => "k" });

		expect(calls).toEqual([PREVIEW_ARGV, WRITE_ARGV]);
		expect(notifications).toEqual([]);
		expect(text).toContain("未签收 k");
		expect(text).toContain("decision model unavailable");
		// Never displays as a signature: no success arrow, no signed_via line,
		// and the sign-off path appears only inside the explicit "not written" clause.
		expect(text).not.toContain("已签收");
		expect(text).not.toContain("→");
		expect(text).not.toContain("signed_via:");
		expect(text).toContain("未写 k/evidence/review/sign-final.md");
		verify(
			`unsigned-exit0: calls=${calls.length} claimed_signed=${text.includes("已签收")} wrote_claim=${
				text.includes("→") ? 1 : 0
			} reason_passthrough=${text.includes("decision model unavailable")}`,
		);
	});
});

describe("/mw decide show is a read-only preview (mw-signoff-decide-only)", () => {
	it("forwards `sign --key <k> --dry-run --json` and renders the facts without writing", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications } = fakeDecideCtx();

		const text = await runMwDecideCommand(ctx, "/proj", "show", { runner, watchKey: () => "k" });

		expect(calls).toEqual([PREVIEW_ARGV]);
		expect(writeCalls(calls)).toEqual([]);
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
		expect(text).toBe(message);
		verify(
			`show: argv=${JSON.stringify(calls[0])} sha12=${SHA.slice(0, 12)} write_calls=${
				writeCalls(calls).length
			} verdict_lines=3`,
		);
	});

	it("preview never touches the write path", async () => {
		const { calls, runner } = stubRunner();
		const { ctx } = fakeDecideCtx({ hasUI: false });

		await runMwDecideCommand(ctx, "/proj", "show", { runner, watchKey: () => "k" });

		expect(calls).toHaveLength(1);
		expect(calls[0]).toContain("--dry-run");
		// The write face is exactly "the calls that are not the dry run".
		expect(writeCalls(calls)).toEqual([]);
		expect(calls.every((args) => args.includes("--dry-run"))).toBe(true);
		verify(`preview-zero-write: calls=${calls.length} dry_run_only=true write_calls=0`);
	});

	it("`--allow-empty` rides on the preview only, never on the write argv", async () => {
		const { calls, runner } = stubRunner();
		const { ctx } = fakeDecideCtx({ hasUI: false });

		await runMwDecideCommand(ctx, "/proj", "sign --allow-empty", {
			runner,
			watchKey: () => "k",
		});

		expect(calls[0]).toEqual([...PREVIEW_ARGV, "--allow-empty"]);
		expect(calls[1]).toEqual(WRITE_ARGV);
		expect(calls[1]).not.toContain("--allow-empty");
		verify(`allow-empty: preview=${JSON.stringify(calls[0])} write=${JSON.stringify(calls[1])}`);
	});

	it("a failing preview notifies Python's reason and never reaches the write", async () => {
		const { calls, runner } = stubRunner({
			preview: { ok: false, error: "[mw decide sign] exit 2: archive table is unreadable" },
		});
		const { ctx, notifications } = fakeDecideCtx();

		const text = await runMwDecideCommand(ctx, "/proj", "sign --key k", { runner });

		expect(calls).toEqual([PREVIEW_ARGV]);
		expect(writeCalls(calls)).toEqual([]);
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("error");
		expect(notifications[0]?.message).toContain("archive table is unreadable");
		expect(text).toContain("预览失败");
		verify(`preview-failure: calls=${calls.length} write_calls=0 level=${notifications[0]?.type}`);
	});

	it("a preview that is not JSON notifies the raw tail instead of guessing", async () => {
		const { calls, runner } = stubRunner({
			preview: { ok: true, output: "Traceback (most recent call last):\nValueError: boom" },
		});
		const { ctx, notifications } = fakeDecideCtx();

		await runMwDecideCommand(ctx, "/proj", "sign --key k", { runner });

		expect(calls).toHaveLength(1);
		expect(writeCalls(calls)).toEqual([]);
		expect(notifications[0]?.type).toBe("error");
		expect(notifications[0]?.message).toContain("ValueError: boom");
	});
});

describe("/mw decide sign forwards exactly one write argv (mw-signoff-decide-only)", () => {
	it("forwards `sign --key <k> --json` once and reports the signature", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications } = fakeDecideCtx();

		const text = await runMwDecideCommand(ctx, "/proj", "sign --key k", { runner });

		expect(calls).toHaveLength(2);
		expect(calls[0]).toEqual(PREVIEW_ARGV);
		expect(calls[1]).toEqual(WRITE_ARGV);
		// The window supplies no conclusion, no exemption flag and no project root.
		for (const flag of ["--auto", "--project", "--human-confirmed", "--conclusion"]) {
			expect(calls[1]).not.toContain(flag);
		}
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("info");
		const message = notifications[0]?.message ?? "";
		expect(message).toContain("已签收 k");
		expect(message).toContain(SIGNED_PATH);
		expect(message).toContain("signed_via: auto-decide");
		expect(message).toContain("conclusion: continue");
		expect(message).not.toContain("decision-scope.md");
		expect(text).toBe(message);
		verify(
			`write: argv=${JSON.stringify(calls[1])} level=${notifications[0]?.type} path_echoed=${message.includes(
				"sign-final.md",
			)} signed_via_echoed=${message.includes("signed_via:")}`,
		);
	});

	it("a write failure notifies Python's text at error level and never throws", async () => {
		const { calls, runner } = stubRunner({
			write: {
				ok: false,
				error: "[mw decide sign] refusing: machine-line verdict failed (N=0: no decide row) — zero writes",
			},
		});
		const { ctx, notifications } = fakeDecideCtx();

		const text = await runMwDecideCommand(ctx, "/proj", "sign --key k", { runner });

		expect(calls).toHaveLength(2);
		const last = notifications.at(-1);
		expect(last?.type).toBe("error");
		expect(last?.message).toContain("machine-line verdict failed");
		expect(text).toContain("machine-line verdict failed");
		expect(text).not.toContain("已签收");
		verify(`write-failure: calls=${calls.length} level=${last?.type} threw=false signed_claim=false`);
	});
});

describe("/mw decide key resolution (mw-signoff-decide-only)", () => {
	it("without --key and without a watched key it is a usage error and spawns nothing", async () => {
		const { calls, runner } = stubRunner();
		const { ctx, notifications } = fakeDecideCtx();

		const text = await runMwDecideCommand(ctx, "/proj", "sign", {
			runner,
			watchKey: () => undefined,
		});

		expect(calls).toEqual([]);
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.type).toBe("warning");
		expect(notifications[0]?.message).toContain("无法确定 key，请给 --key");
		expect(text).toContain("无法确定 key");
		verify(`no-key: runner_calls=${calls.length} level=${notifications[0]?.type}`);
	});
});

describe("/mw decide dispatcher wiring (mw-signoff-decide-only)", () => {
	it("the registered /mw command routes `decide` and the usage line documents it", async () => {
		const root = mkdtemp("mw-decide-dispatch-");
		const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
		const summaries: string[] = [];
		const pi = {
			registerCommand: (
				name: string,
				def: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
			) => {
				commands.set(name, def.handler);
			},
			sendMessage: (message: { content: string }) => {
				summaries.push(message.content);
			},
		} as unknown as ExtensionAPI;
		registerMwCommands(pi, root, new WorkerStore(root), {} as AckStore, { key: undefined }, root);
		const handler = commands.get("mw");
		if (!handler) throw new Error("/mw command not registered");

		// Headless routing: a usage-level decide tail proves the `decide` branch is
		// reached without spawning python, and the result lands in the transcript
		// through displaySummary instead of the no-op notify (AC-007).
		const headless = fakeDecideCtx({ hasUI: false });
		await handler("decide bogus", headless.ctx);
		expect(headless.notifications).toEqual([]);
		expect(summaries).toHaveLength(1);
		expect(summaries[0]).toContain("unknown sub 'bogus'");
		expect(summaries[0]).toContain(DECIDE_USAGE);

		const usage = fakeDecideCtx({ hasUI: true });
		await handler("bogus", usage.ctx);
		const usageLine = usage.notifications.at(-1)?.message ?? "";
		expect(usageLine).toContain("| decide show|sign [--allow-empty] [--key <k>]");
		expect(usageLine).not.toContain("<continue|narrow|revoke>");
		expect(DECIDE_USAGE.startsWith("Usage: /mw decide show | sign")).toBe(true);
		verify(
			`dispatch: routed=${summaries.length === 1} headless_summary=true usage_has_decide=${usageLine.includes(
				"| decide show|sign",
			)} usage_export=${DECIDE_USAGE.startsWith("Usage: /mw decide show | sign")}`,
		);
	});
});
