/**
 * decide-controls.test.ts — offline unit matrix for the five new `/mw decide`
 * window controls (mw-decide-window-controls T-01, AC-001..005 / VC-001..005).
 *
 * Pure unit layer: no spawn, no network, no real model, no config/authority
 * file. Every runner is a recording stub and every dialog is a recorded fake.
 * The exact argv, the project dir handed to the runner, the keyless project
 * entry, the UI-confirm gate, the registry pre-check, the internal P0 flag and
 * the honest failure reporting are all asserted here. The suite-level entry
 * (harness + faux provider) is covered separately in
 * `test/suite/decide-controls.test.ts`.
 */

import * as path from "node:path";
import { describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import {
	DECIDE_DP_TIERS,
	DECIDE_USAGE,
	decideForwardArgs,
	isSafeDecideDpId,
	parseDecideArgs,
	parseDecideDpMetadata,
	parseDecideProbeOutput,
	registerMwCommands,
	runMwDecideCommand,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import type { MwCliResult } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

/** The suite config swallows console.log from green tests: write the evidence
 * markers straight to stdout, bound to the assertions above them. */
function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

/** Fixed control root for every runner call (project cwd / controlDir). */
const CONTROL_DIR = path.join(path.sep, "tmp", "mw-decide-controls", "project");
const DP = "dp-QG";
const P0_DP = "dp-gate-approve";

interface Call {
	projectDir: string;
	args: string[];
}

interface RecordingRunner {
	calls: Call[];
	runner: (projectDir: string, args: string[]) => MwCliResult;
}

/** One argv -> result map plus an optional throw on an exact argv. An unmapped
 * argv returns `unexpected argv` (a failure), so a stray write cannot pass. */
function recordingRunner(
	plan: { results?: Record<string, MwCliResult>; throwOn?: string; default?: MwCliResult } = {},
): RecordingRunner {
	const calls: Call[] = [];
	const runner = (projectDir: string, args: string[]): MwCliResult => {
		calls.push({ projectDir, args });
		const key = args.join(" ");
		if (plan.throwOn === key) throw new Error("spawn boom");
		return plan.results?.[key] ?? plan.default ?? { ok: false, error: `unexpected argv: ${key}` };
	};
	return { calls, runner };
}

interface Notify {
	message: string;
	type: string;
}

interface ConfirmCall {
	title: string;
	message: string;
}

/** One confirm dialog outcome (for the two-confirm P0 matrix). */
interface ConfirmStep {
	value?: unknown;
	throw?: Error;
}

interface FakeCtxOpts {
	hasUI?: boolean;
	confirm?: unknown;
	confirmThrow?: Error;
	/** Per-call confirm answers; when present it overrides confirm/confirmThrow
	 * and a missing step yields `undefined` (a non-true answer). */
	confirmSeq?: ConfirmStep[];
	/** Run mode; defaults to "tui". The sentinel "missing" omits `mode` so the
	 * new-control entry gate sees an untrusted, mode-less context. */
	mode?: string;
}

function fakeCtx(opts: FakeCtxOpts = {}): {
	ctx: ExtensionCommandContext;
	notifications: Notify[];
	confirmations: ConfirmCall[];
} {
	const notifications: Notify[] = [];
	const confirmations: ConfirmCall[] = [];
	const ctx: Record<string, unknown> = {
		hasUI: opts.hasUI ?? true,
		ui: {
			notify: (message: string, type?: string) => {
				notifications.push({ message, type: type ?? "" });
			},
			confirm: async (title: string, message: string): Promise<unknown> => {
				const index = confirmations.length;
				confirmations.push({ title, message });
				if (opts.confirmSeq) {
					const step = opts.confirmSeq[index];
					if (step?.throw) throw step.throw;
					return step?.value;
				}
				if (opts.confirmThrow) throw opts.confirmThrow;
				return opts.confirm;
			},
		},
	};
	const mode = opts.mode ?? "tui";
	if (mode !== "missing") ctx.mode = mode;
	return { ctx: ctx as unknown as ExtensionCommandContext, notifications, confirmations };
}

function dpShow(id: string, tier: string, consequences: unknown = null): MwCliResult {
	return { ok: true, output: JSON.stringify({ id, tier, p0_consequences: consequences }) };
}

function writes(calls: Call[]): string[][] {
	return calls
		.filter((call) => call.args[0] === "set" || call.args[1] === "on" || call.args[1] === "off")
		.map((c) => c.args);
}

const INVALID_COMMANDS = [
	"on --json",
	"on enabled=true",
	"on --project /tmp",
	"off --i-understand-p0",
	"off extra",
	"probe --json",
	"probe --live",
	"probe x",
	"dp on",
	"dp off",
	"dp on --i-understand-p0",
	`dp on ${DP} --i-understand-p0`,
	`dp on ${DP} extra`,
	`dp on "${DP};rm -rf"`,
	`dp on ${DP} --json`,
	"dp on $(whoami)",
	"dp on ../../evil",
	'dp off "dp|x"',
	"dp set dp-QG mode=auto",
	"dp apply sign-final.md",
	"dp export --write",
	"sign --i-understand-p0",
	"bogus",
];

describe("/mw decide controls — closed parser and safe dp ids", () => {
	it("accepts exactly the five new shapes and rejects every extra token/flag", () => {
		expect(parseDecideArgs("on")).toEqual({ action: "on" });
		expect(parseDecideArgs("off")).toEqual({ action: "off" });
		expect(parseDecideArgs("probe")).toEqual({ action: "probe" });
		expect(parseDecideArgs(`dp on ${DP}`)).toEqual({ action: "dp-on", dp: DP });
		expect(parseDecideArgs(`dp off ${P0_DP}`)).toEqual({ action: "dp-off", dp: P0_DP });
		for (const text of INVALID_COMMANDS) {
			const parsed = parseDecideArgs(text);
			expect(parsed.action, text).toBe("usage");
			expect(decideForwardArgs(parsed), text).toBeNull();
			if (parsed.action === "usage") expect(parsed.error.startsWith(DECIDE_USAGE), text).toBe(true);
		}
		expect(DECIDE_DP_TIERS).toEqual(["P0", "P1", "P2"]);
		expect(isSafeDecideDpId(DP)).toBe(true);
		expect(isSafeDecideDpId("dp-gate-approve")).toBe(true);
		for (const bad of ["", "-x", "--i-understand-p0", "a b", "a;rm", "a$(x)", "a|b", "a/b", "a'b", 'a"b', "a\tb"]) {
			expect(isSafeDecideDpId(bad), bad).toBe(false);
		}
	});
});

describe("VC-001: transport on/off — AC-001", () => {
	it("calls set once with exact argv/controlDir after confirm(true), keyless and warning-preserving", async () => {
		for (const [text, argv] of [
			["on", ["set", "--json", "enabled=true"]],
			["off", ["set", "--json", "enabled=false"]],
		] as const) {
			const output = "wrote .mw/decide.json\nWARNING: authority audit append failed";
			const { calls, runner } = recordingRunner({ results: { [argv.join(" ")]: { ok: true, output } } });
			const { ctx, notifications, confirmations } = fakeCtx({ confirm: true });
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, text, { runner, watchKey: () => undefined });
			expect(calls).toEqual([{ projectDir: CONTROL_DIR, args: argv }]);
			expect(confirmations).toHaveLength(1);
			expect(confirmations[0]?.message).toContain("传输总开关");
			expect(textOut).toContain(output);
			expect(textOut).toContain("WARNING: authority audit append failed");
			expect(notifications.at(-1)?.type).toBe("info");
		}
	});

	it("cancel / undefined / no UI / thrown dialog never call the write CLI", async () => {
		for (const opts of [
			{ label: "cancel", value: { confirm: false } },
			{ label: "undefined", value: {} },
			{ label: "no-ui", value: { hasUI: false, confirm: true } },
			{ label: "throw", value: { confirmThrow: new Error("dialog boom") } },
		] as const) {
			const { calls, runner } = recordingRunner();
			const { ctx, notifications, confirmations } = fakeCtx(opts.value);
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, "on", { runner, watchKey: () => undefined });
			expect(calls, opts.label).toEqual([]);
			expect(writes(calls), opts.label).toEqual([]);
			expect(confirmations, opts.label).toHaveLength(opts.label === "no-ui" ? 0 : 1);
			// Headless has no notify channel: the refusal is the returned text.
			if (opts.label === "no-ui") {
				expect(notifications, opts.label).toEqual([]);
				expect(textOut, opts.label).toContain("需要交互 UI");
			} else {
				expect(notifications.at(-1)?.type, opts.label).toBe(opts.label === "throw" ? "error" : "warning");
			}
			expect(textOut, opts.label).not.toContain("enabled=true) CLI 原文");
			if (opts.label === "throw") expect(textOut).toContain("dialog boom");
		}
	});

	it("CLI non-zero and thrown runner are reported verbatim, never as success", async () => {
		const argv = "set --json enabled=true";
		const failed = recordingRunner({
			results: { [argv]: { ok: false, error: "[mw decide set] cannot write: permission denied" } },
		});
		const failureText = await runMwDecideCommand(fakeCtx({ confirm: true }).ctx, CONTROL_DIR, "on", {
			runner: failed.runner,
		});
		expect(failureText).toContain("permission denied");
		expect(failed.calls).toEqual([{ projectDir: CONTROL_DIR, args: ["set", "--json", "enabled=true"] }]);
		const thrown = recordingRunner({ throwOn: argv });
		const thrownText = await runMwDecideCommand(fakeCtx({ confirm: true }).ctx, CONTROL_DIR, "on", {
			runner: thrown.runner,
		});
		expect(thrownText).toContain("spawn boom");
		expect(thrownText).toContain("写入失败");
		verify("VC-001: transport=pass");
	});
});

describe("VC-002: probe — AC-002", () => {
	it("calls only probe --json, no confirm, and renders each raw diagnostic (TUI+hasUI gate)", async () => {
		const rows = [
			{ target: "timi:model-a", method: "POST", path: "/decisions", status: 200, verdict: "ok" },
			{ target: "timi:model-b", method: "POST", path: "/decisions", status: 201, verdict: "ok" },
		];
		const output = JSON.stringify(rows);
		const { calls, runner } = recordingRunner({ results: { "probe --json": { ok: true, output } } });
		// probe is one of the five new faces: it now needs mode=tui + hasUI, but
		// still has NO confirm dialog (read-only diagnostic) and NO write.
		const { ctx, confirmations, notifications } = fakeCtx();
		const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, "probe", { runner, watchKey: () => undefined });
		expect(calls).toEqual([{ projectDir: CONTROL_DIR, args: ["probe", "--json"] }]);
		expect(confirmations).toEqual([]);
		expect(notifications.at(-1)?.type).toBe("info");
		expect(textOut).toContain("2 条诊断均 verdict=ok");
		expect(textOut).toContain("不是业务裁决或 QG verdict");
		expect(textOut).toContain(JSON.stringify(rows[0]));
		expect(textOut).toContain(JSON.stringify(rows[1]));
		expect(parseDecideProbeOutput(output)).toMatchObject({ ok: true, rows: 2 });
	});

	it("exit 0 with failed/empty/bad/mixed diagnostics never claims an available model", async () => {
		const cases = [
			{ label: "empty", output: "", level: "error" },
			{ label: "blank", output: "   \n", level: "error" },
			{ label: "not-json", output: "probe: 1 target(s)", level: "error" },
			{ label: "json-object", output: '{"ok":true,"status":200}', level: "error" },
			{ label: "empty-array", output: "[]", level: "error" },
			{ label: "bad-json", output: "[{status:200]", level: "error" },
			{ label: "http-401", output: JSON.stringify([{ status: 401, verdict: "upstream-error" }]), level: "warning" },
			{
				label: "status-null",
				output: JSON.stringify([{ status: null, verdict: "entry-unavailable" }]),
				level: "warning",
			},
			{ label: "verdict-bad", output: JSON.stringify([{ status: 200, verdict: "bad-response" }]), level: "warning" },
			{ label: "verdict-case", output: JSON.stringify([{ status: 200, verdict: "OK" }]), level: "warning" },
			{ label: "status-string", output: JSON.stringify([{ status: "200", verdict: "ok" }]), level: "warning" },
			{ label: "row-number", output: JSON.stringify([42]), level: "warning" },
			{
				label: "mixed",
				output: JSON.stringify([
					{ status: 200, verdict: "ok" },
					{ status: 200, verdict: "timeout" },
				]),
				level: "warning",
			},
		];
		for (const testCase of cases) {
			const { calls, runner } = recordingRunner({
				results: { "probe --json": { ok: true, output: testCase.output } },
			});
			const { ctx, notifications, confirmations } = fakeCtx();
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, "probe", { runner });
			expect(calls, testCase.label).toEqual([{ projectDir: CONTROL_DIR, args: ["probe", "--json"] }]);
			expect(writes(calls), testCase.label).toEqual([]);
			expect(confirmations, testCase.label).toEqual([]);
			expect(textOut, testCase.label).toContain("模型可用性未确认");
			expect(textOut, testCase.label).not.toContain("均 verdict=ok");
			expect(notifications.at(-1)?.type, testCase.label).toBe(testCase.level);
			expect(parseDecideProbeOutput(testCase.output).ok, testCase.label).toBe(false);
		}
	});

	it("probe CLI failure / throw is an honest error and spawns no write", async () => {
		const failed = recordingRunner({
			results: { "probe --json": { ok: false, error: "[mw decide probe] config unreadable" } },
		});
		const failedText = await runMwDecideCommand(fakeCtx().ctx, CONTROL_DIR, "probe", { runner: failed.runner });
		expect(failedText).toContain("config unreadable");
		const thrown = recordingRunner({ throwOn: "probe --json" });
		const thrownText = await runMwDecideCommand(fakeCtx().ctx, CONTROL_DIR, "probe", { runner: thrown.runner });
		expect(thrownText).toContain("spawn boom");
		expect(thrown.calls).toHaveLength(1);
		verify("VC-002: diagnostic=pass");
	});
});

describe("VC-003: dp on/off — AC-003", () => {
	it("P0 on: two independent confirms in order, both true, flag only after both (write last)", async () => {
		const consequences = "自动放行 gate 可能跳过未就绪的 stage/goal/预算/授权检查";
		const showArgv = ["dp", "show", P0_DP, "--json"];
		const writeArgv = ["dp", "on", P0_DP, "--i-understand-p0"];
		const { ctx, confirmations, notifications } = fakeCtx({ confirmSeq: [{ value: true }, { value: true }] });
		// Record how many confirmations had happened at each runner call, so the
		// write is proven to occur only AFTER both confirms (pre-check before any).
		const timeline: string[] = [];
		const runner = (_projectDir: string, args: string[]): MwCliResult => {
			timeline.push(`call ${args.join(" ")} after ${confirmations.length} confirms`);
			if (args.join(" ") === showArgv.join(" ")) return dpShow(P0_DP, "P0", consequences);
			if (args.join(" ") === writeArgv.join(" ")) {
				return { ok: true, output: "wrote .mw/decide-points.json\nWARNING: authority audit append failed" };
			}
			return { ok: false, error: `unexpected argv: ${args.join(" ")}` };
		};
		const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, `dp on ${P0_DP}`, {
			runner,
			watchKey: () => undefined,
		});
		expect(timeline).toEqual([
			`call ${showArgv.join(" ")} after 0 confirms`,
			`call ${writeArgv.join(" ")} after 2 confirms`,
		]);
		expect(confirmations).toHaveLength(2);
		// First = general id/on-off confirmation (no consequences); second =
		// independent risk confirmation showing registry consequences.
		expect(confirmations[0]?.message).toContain(P0_DP);
		expect(confirmations[0]?.message).toContain("开启");
		expect(confirmations[0]?.message).not.toContain(consequences);
		expect(confirmations[1]?.message).toContain(consequences);
		expect(confirmations[1]?.message).toContain("高风险");
		expect(confirmations[1]?.message).toContain("第二次");
		expect(confirmations[1]?.message).toContain("--i-understand-p0");
		expect(textOut).toContain("WARNING: authority audit append failed");
		expect(notifications.at(-1)?.type).toBe("info");
	});

	it("P0 on: any non-true/absent/throw confirm and first-cancel yield zero write; first cancel never opens the 2nd", async () => {
		const consequences = "自动放行 gate 可能跳过未就绪的 stage/goal/预算/授权检查";
		const showArgv = ["dp", "show", P0_DP, "--json"];
		const cases = [
			{ label: "true/false", seq: [{ value: true }, { value: false }], confirms: 2 },
			{ label: "true/undefined", seq: [{ value: true }], confirms: 2 },
			{ label: "second-throw", seq: [{ value: true }, { throw: new Error("risk dialog boom") }], confirms: 2 },
			{ label: "first-cancel", seq: [{ value: false }], confirms: 1 },
			{ label: "first-undefined", seq: [{}], confirms: 1 },
			{ label: "first-throw", seq: [{ throw: new Error("first dialog boom") }], confirms: 1 },
		] as const;
		for (const testCase of cases) {
			const { calls, runner } = recordingRunner({
				results: {
					[showArgv.join(" ")]: dpShow(P0_DP, "P0", consequences),
					[`dp on ${P0_DP} --i-understand-p0`]: { ok: true, output: "wrote .mw/decide-points.json" },
				},
			});
			const { ctx, confirmations } = fakeCtx({ confirmSeq: [...testCase.seq] });
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, `dp on ${P0_DP}`, { runner });
			expect(writes(calls), testCase.label).toEqual([]);
			expect(confirmations, testCase.label).toHaveLength(testCase.confirms);
			expect(calls, testCase.label).toEqual([{ projectDir: CONTROL_DIR, args: showArgv }]);
			expect(textOut, testCase.label).not.toContain("CLI 原文");
			if (testCase.label.includes("throw")) expect(textOut, testCase.label).toContain("dialog boom");
		}
	});

	it("P0 on: missing/null/blank consequences fail closed (no placeholder text, zero write)", async () => {
		const showArgv = ["dp", "show", P0_DP, "--json"];
		const outputs: MwCliResult[] = [
			// genuinely absent p0_consequences field
			{ ok: true, output: JSON.stringify({ id: P0_DP, tier: "P0" }) },
			...([null, "", "   "] as const).map((consequences) => dpShow(P0_DP, "P0", consequences)),
		];
		for (const shown of outputs) {
			const { calls, runner } = recordingRunner({ results: { [showArgv.join(" ")]: shown } });
			const { ctx, confirmations, notifications } = fakeCtx({ confirm: true });
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, `dp on ${P0_DP}`, { runner });
			expect(writes(calls)).toEqual([]);
			expect(calls).toEqual([{ projectDir: CONTROL_DIR, args: showArgv }]);
			expect(confirmations).toEqual([]);
			expect(notifications.at(-1)?.type).toBe("error");
			expect(textOut).toContain("p0_consequences 缺失/空白");
			expect(textOut).not.toContain("registry 未提供后果说明");
			expect(textOut).not.toContain("--i-understand-p0");
		}
		// ...but a P0 off (safe de-powering) with null consequences still works.
		const offShow = ["dp", "show", P0_DP, "--json"];
		const { calls, runner } = recordingRunner({
			results: {
				[offShow.join(" ")]: dpShow(P0_DP, "P0", null),
				[`dp off ${P0_DP}`]: { ok: true, output: "wrote .mw/decide-points.json" },
			},
		});
		const { ctx, confirmations } = fakeCtx({ confirm: true });
		await runMwDecideCommand(ctx, CONTROL_DIR, `dp off ${P0_DP}`, { runner });
		expect(calls).toEqual([
			{ projectDir: CONTROL_DIR, args: offShow },
			{ projectDir: CONTROL_DIR, args: ["dp", "off", P0_DP] },
		]);
		expect(confirmations).toHaveLength(1);
	});

	it("P1/P2 on and P0 off write exactly one dp argv without the P0 flag", async () => {
		for (const [text, tier, writeArgv] of [
			[`dp on ${DP}`, "P1", ["dp", "on", DP]],
			[`dp on ${DP}`, "P2", ["dp", "on", DP]],
			[`dp off ${P0_DP}`, "P0", ["dp", "off", P0_DP]],
		] as const) {
			const id = text.endsWith(P0_DP) ? P0_DP : DP;
			const showArgv = ["dp", "show", id, "--json"];
			const { calls, runner } = recordingRunner({
				results: {
					[showArgv.join(" ")]: dpShow(id, tier),
					[writeArgv.join(" ")]: { ok: true, output: "wrote .mw/decide-points.json" },
				},
			});
			const { ctx, confirmations } = fakeCtx({ confirm: true });
			await runMwDecideCommand(ctx, CONTROL_DIR, text, { runner, watchKey: () => undefined });
			expect(calls, text).toEqual([
				{ projectDir: CONTROL_DIR, args: showArgv },
				{ projectDir: CONTROL_DIR, args: writeArgv },
			]);
			expect(confirmations, text).toHaveLength(1);
			expect(
				calls.some((call) => call.args.includes("--i-understand-p0")),
				text,
			).toBe(false);
		}
	});

	it("cancel / undefined / no UI / thrown dialog never write a dp", async () => {
		const showArgv = ["dp", "show", DP, "--json"];
		for (const opts of [
			{ label: "cancel", value: { confirm: false }, calls: 1 },
			{ label: "undefined", value: {}, calls: 1 },
			{ label: "no-ui", value: { hasUI: false, confirm: true }, calls: 0 },
			{ label: "throw", value: { confirmThrow: new Error("dialog boom") }, calls: 1 },
		] as const) {
			const { calls, runner } = recordingRunner({
				results: { [showArgv.join(" ")]: dpShow(DP, "P1") },
			});
			const { ctx, confirmations, notifications } = fakeCtx(opts.value);
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, `dp on ${DP}`, { runner });
			expect(calls, opts.label).toHaveLength(opts.calls);
			expect(writes(calls), opts.label).toEqual([]);
			expect(confirmations, opts.label).toHaveLength(opts.label === "no-ui" ? 0 : 1);
			if (opts.label === "no-ui") {
				expect(notifications, opts.label).toEqual([]);
				expect(textOut, opts.label).toContain("需要交互 UI");
			} else {
				expect(notifications.at(-1)?.type, opts.label).toBe(opts.label === "throw" ? "error" : "warning");
			}
			if (opts.label === "throw") expect(textOut).toContain("dialog boom");
		}
	});

	it("unknown id / wrong id / bad metadata / pre-check throw all fail closed", async () => {
		const showArgv = ["dp", "show", DP, "--json"];
		const badCases = [
			{ label: "unknown", result: { ok: false, error: `[mw decide dp show] unknown dp '${DP}'` } as MwCliResult },
			{ label: "wrong-id", result: dpShow("dp-other", "P1") },
			{ label: "bad-tier", result: dpShow(DP, "P9") },
			{ label: "tier-missing", result: { ok: true, output: JSON.stringify({ id: DP }) } as MwCliResult },
			{ label: "not-json", result: { ok: true, output: "Traceback (most recent call last)" } as MwCliResult },
			{ label: "bad-consequences", result: dpShow(DP, "P0", { nested: true }) },
		];
		for (const testCase of badCases) {
			const { calls, runner } = recordingRunner({ results: { [showArgv.join(" ")]: testCase.result } });
			const { ctx, confirmations, notifications } = fakeCtx({ confirm: true });
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, `dp on ${DP}`, { runner });
			expect(calls, testCase.label).toEqual([{ projectDir: CONTROL_DIR, args: showArgv }]);
			expect(writes(calls), testCase.label).toEqual([]);
			expect(confirmations, testCase.label).toEqual([]);
			expect(notifications.at(-1)?.type, testCase.label).toBe("error");
			expect(textOut, testCase.label).toMatch(/预检失败|拒绝写入/);
		}
		const thrown = recordingRunner({ throwOn: showArgv.join(" ") });
		const thrownText = await runMwDecideCommand(fakeCtx({ confirm: true }).ctx, CONTROL_DIR, `dp on ${DP}`, {
			runner: thrown.runner,
		});
		expect(thrownText).toContain("spawn boom");
		expect(writes(thrown.calls)).toEqual([]);
		const valid = dpShow(DP, "P1");
		expect(parseDecideDpMetadata(valid.ok ? valid.output : "", DP)).toMatchObject({ ok: true });
	});

	it("dp write CLI non-zero / throw keeps the raw audit text at error level", async () => {
		const showArgv = ["dp", "show", DP, "--json"];
		const writeArgv = ["dp", "off", DP];
		const failed = recordingRunner({
			results: {
				[showArgv.join(" ")]: dpShow(DP, "P1"),
				[writeArgv.join(" ")]: {
					ok: false,
					error: "[mw decide dp] cannot write .mw/decide-points.json\nWARNING: audit append failed",
				},
			},
		});
		const failedText = await runMwDecideCommand(fakeCtx({ confirm: true }).ctx, CONTROL_DIR, `dp off ${DP}`, {
			runner: failed.runner,
		});
		expect(failedText).toContain("cannot write .mw/decide-points.json");
		expect(failedText).toContain("WARNING: audit append failed");
		expect(failedText).not.toContain("CLI 原文");
		const thrown = recordingRunner({
			results: { [showArgv.join(" ")]: dpShow(DP, "P1") },
			throwOn: writeArgv.join(" "),
		});
		const thrownText = await runMwDecideCommand(fakeCtx({ confirm: true }).ctx, CONTROL_DIR, `dp off ${DP}`, {
			runner: thrown.runner,
		});
		expect(thrownText).toContain("spawn boom");
		expect(writes(thrown.calls)).toEqual([writeArgv]);
		verify("VC-003: authority=pass");
	});
});

describe("metadata fail-closed: strict top-level object only (AC-003 / RQ2)", () => {
	it("parseDecideDpMetadata accepts one top-level object and rejects arrays/garbage/duplicates", () => {
		// Valid: P1/P2 with null consequences and P0 with a real consequence string.
		expect(parseDecideDpMetadata(JSON.stringify({ id: DP, tier: "P1", p0_consequences: null }), DP)).toEqual({
			ok: true,
			metadata: { id: DP, tier: "P1", p0_consequences: "" },
		});
		expect(parseDecideDpMetadata(JSON.stringify({ id: DP, tier: "P2" }), DP)).toMatchObject({ ok: true });
		const p0 = JSON.stringify({ id: P0_DP, tier: "P0", p0_consequences: "risk text" });
		expect(parseDecideDpMetadata(p0, P0_DP)).toMatchObject({
			ok: true,
			metadata: { p0_consequences: "risk text" },
		});
		const inner = JSON.stringify({ id: P0_DP, tier: "P0", p0_consequences: "risk" });
		const bad = [
			{ label: "array-wrapped", output: `[${inner}]` },
			{ label: "array-of-objects", output: `[${inner},${inner}]` },
			{ label: "null", output: "null" },
			{ label: "primitive-number", output: "42" },
			{ label: "primitive-string", output: JSON.stringify("obj") },
			{ label: "primitive-bool", output: "true" },
			{ label: "garbage-prefix", output: `WARN line\n${inner}` },
			{ label: "garbage-suffix", output: `${inner}\ntrailer` },
			{ label: "two-objects", output: `${inner}${inner}` },
			{ label: "corrupted", output: '{"id":"dp-QG","tier":' },
			{ label: "empty", output: "" },
		];
		for (const testCase of bad) {
			expect(parseDecideDpMetadata(testCase.output, P0_DP).ok, testCase.label).toBe(false);
		}
	});

	it("array/garbage dp show output is rejected at the handler with zero write and zero confirm", async () => {
		const showArgv = ["dp", "show", P0_DP, "--json"];
		const inner = JSON.stringify({ id: P0_DP, tier: "P0", p0_consequences: "risk" });
		for (const output of [`[${inner}]`, `garbage\n${inner}`, `${inner}\ntrailer`, `${inner}${inner}`]) {
			const { calls, runner } = recordingRunner({
				results: { [showArgv.join(" ")]: { ok: true, output } },
			});
			const { ctx, confirmations, notifications } = fakeCtx({ confirm: true });
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, `dp on ${P0_DP}`, { runner });
			expect(calls, output).toEqual([{ projectDir: CONTROL_DIR, args: showArgv }]);
			expect(writes(calls), output).toEqual([]);
			expect(confirmations, output).toEqual([]);
			expect(notifications.at(-1)?.type, output).toBe("error");
			expect(textOut, output).toMatch(/拒绝写入|预检失败/);
		}
	});
});

describe("new-control entry gate: mode=tui + hasUI before any runner (AC-005 / RQ2)", () => {
	const faces = ["on", "off", "probe", `dp on ${DP}`, `dp off ${DP}`];
	const blocked: { label: string; opts: FakeCtxOpts }[] = [
		{ label: "rpc+hasUI+confirm", opts: { mode: "rpc", hasUI: true, confirm: true } },
		{ label: "print", opts: { mode: "print", hasUI: true, confirm: true } },
		{ label: "json", opts: { mode: "json", hasUI: true, confirm: true } },
		{ label: "missing-mode", opts: { mode: "missing", hasUI: true, confirm: true } },
		{ label: "no-ui", opts: { hasUI: false, confirm: true } },
	];

	it("every new face is refused with zero runner and zero confirm for untrusted/no-UI entries", async () => {
		for (const face of faces) {
			for (const entry of blocked) {
				const { calls, runner } = recordingRunner({ default: { ok: true, output: "should-not-run" } });
				const { ctx, confirmations, notifications } = fakeCtx(entry.opts);
				const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, face, { runner, watchKey: () => undefined });
				expect(calls, `${face}/${entry.label}`).toEqual([]);
				expect(confirmations, `${face}/${entry.label}`).toEqual([]);
				expect(textOut, `${face}/${entry.label}`).toContain("控制命令拒绝");
				expect(notifications.at(-1)?.type, `${face}/${entry.label}`).toBe(
					entry.label === "no-ui" ? undefined : "warning",
				);
			}
		}
	});

	it("mode=tui + hasUI is the only entry that reaches the runner (fake ctx is explicitly tui)", async () => {
		const { ctx } = fakeCtx({ mode: "tui" });
		expect((ctx as unknown as { mode?: string }).mode).toBe("tui");
		const { calls, runner } = recordingRunner({
			results: { "probe --json": { ok: true, output: JSON.stringify([{ status: 200, verdict: "ok" }]) } },
		});
		await runMwDecideCommand(ctx, CONTROL_DIR, "probe", { runner });
		expect(calls).toEqual([{ projectDir: CONTROL_DIR, args: ["probe", "--json"] }]);
		// Legacy headless faces are NOT gated even without a mode: sign/show still
		// resolve normally (no TUI gate), preserving their headless semantics.
		const legacy = recordingRunner({
			results: { "sign --key k --dry-run --json": { ok: false, error: "legacy still runs" } },
		});
		const headless = fakeCtx({ mode: "missing", hasUI: false });
		const legacyOut = await runMwDecideCommand(headless.ctx, CONTROL_DIR, "show", {
			runner: legacy.runner,
			watchKey: () => "k",
		});
		expect(legacyOut).toContain("legacy still runs");
		expect(legacy.calls).toEqual([{ projectDir: CONTROL_DIR, args: ["sign", "--key", "k", "--dry-run", "--json"] }]);
	});
});

describe("VC-004: rejection and honest CLI errors — AC-004", () => {
	it("every illegal/injected input has zero runner calls and zero confirmations", async () => {
		for (const text of INVALID_COMMANDS) {
			const { calls, runner } = recordingRunner();
			const { ctx, confirmations, notifications } = fakeCtx({ confirm: true });
			const textOut = await runMwDecideCommand(ctx, CONTROL_DIR, text, { runner, watchKey: () => undefined });
			expect(calls, text).toEqual([]);
			expect(confirmations, text).toEqual([]);
			expect(notifications.at(-1)?.type, text).toBe("warning");
			expect(textOut, text).toContain("Usage: /mw decide");
		}
		verify("VC-004: rejection=pass");
	});
});

describe("VC-005: legacy faces, keyless read-only forwards and help — AC-005", () => {
	it("legacy show/sign stay headless, read-only forwards stay keyless, help lists the new faces", async () => {
		const preview = {
			facts: {
				counted_rows: 1,
				n_available: 1,
				n_acted: 1,
				n_escalated: 0,
				engines: {},
				sha256: "0123456789abcdef",
			},
			verdicts: { finalize: { ok: true }, continue: { ok: true }, "user-confirm": { ok: true } },
		};
		const signed = {
			dp: "dp-sign-key",
			key: "k",
			logical_id: "logical-1",
			decision_id: "dp-sign-key:logical-1",
			conclusion: "finalize",
			signoff_status: "written",
			signoff_path: "k/evidence/review/sign-final.md",
		};
		const { calls, runner } = recordingRunner({
			results: {
				"sign --key k --dry-run --json": { ok: true, output: JSON.stringify(preview) },
				"sign --key k --json": { ok: true, output: JSON.stringify(signed) },
				"dp list": { ok: true, output: "25 decision point(s)" },
				"dp export": { ok: true, output: "export" },
				monitor: { ok: true, output: "monitor" },
			},
		});
		const shown = await runMwDecideCommand(fakeCtx({ hasUI: false }).ctx, CONTROL_DIR, "show", {
			runner,
			watchKey: () => "k",
		});
		expect(shown).toContain("preview only");
		expect(calls.at(-1)?.args).toEqual(["sign", "--key", "k", "--dry-run", "--json"]);
		const signedText = await runMwDecideCommand(fakeCtx({ hasUI: false }).ctx, CONTROL_DIR, "sign", {
			runner,
			watchKey: () => "k",
		});
		expect(signedText).toContain("已签收 k");
		expect(signedText).toContain("conclusion: finalize");
		for (const [text, argv] of [
			["dp list", ["dp", "list"]],
			["dp export", ["dp", "export"]],
			["monitor", ["monitor"]],
		] as const) {
			const forwarded = await runMwDecideCommand(fakeCtx({ hasUI: false }).ctx, CONTROL_DIR, text, {
				runner,
				watchKey: () => undefined,
			});
			expect(forwarded, text).not.toContain("unknown sub");
			expect(calls.at(-1)?.args, text).toEqual(argv);
		}
		expect(DECIDE_USAGE.startsWith("Usage: /mw decide show | sign")).toBe(true);
		expect(DECIDE_USAGE).toContain("dp list | dp show <id> | dp export | monitor");
		expect(DECIDE_USAGE).toContain("on | off | probe | dp on <id> | dp off <id>");
		expect(DECIDE_USAGE).toContain("P0");
		expect(DECIDE_USAGE).toContain("QG verdict");

		const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
		const pi = {
			registerCommand: (
				name: string,
				def: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
			) => {
				commands.set(name, def.handler);
			},
			sendMessage: () => undefined,
		} as unknown as ExtensionAPI;
		registerMwCommands(
			pi,
			CONTROL_DIR,
			new WorkerStore(CONTROL_DIR),
			{} as AckStore,
			{ key: undefined },
			CONTROL_DIR,
		);
		const handler = commands.get("mw");
		if (!handler) throw new Error("/mw command not registered");
		const { ctx, notifications } = fakeCtx();
		await handler("bogus", ctx);
		const usage = notifications.at(-1)?.message ?? "";
		expect(usage).toContain("decide on|off|probe");
		expect(usage).toContain("decide dp on|off <id>");
		expect(usage).toContain("decide dp list|show <id>|export");
		expect(usage).toContain("decide monitor");
		expect(usage).toContain("| decide show|sign [--allow-empty] [--key <k>]");
		verify("VC-005: regression=pass");
	});
});
