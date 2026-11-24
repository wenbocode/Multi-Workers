/** T-09A independent minimal regressions for the FULL-preview overlay.
 *
 * The production `presentIssueFullText` component is reached through the real
 * `/mw issue report` path (runMwIssueCommand -> present -> ctx.ui.custom).
 * Frames are taken from the REAL TuiMainScreen compositor and the REAL xterm
 * VirtualTerminal viewport, both clipped to the terminal dimensions. This is
 * deliberately a small suite; T-06's four red assertions are not duplicated or
 * modified. */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { type Component, type OverlayOptions, stripTerminalSequences, TuiMainScreen } from "@earendil-works/pi-tui";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { VirtualTerminal } from "../../../tui/test/virtual-terminal.ts";
import type { ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import type { IssueCommandStore } from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import { ISSUE_PREVIEW_VIEWPORT_LINES, runMwIssueCommand } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";

const FOOTER_MARK = "完整脱敏预览，未截断";
const TAIL_MARK = "END-OF-VIEWPORT-TAIL";

interface PreviewComponentLike {
	readonly fullText: string;
	readonly lineCount: number;
	render(width: number): string[];
	invalidate(): void;
	handleInput(data: string): void;
}

type PreviewFactory = (
	tui: unknown,
	theme: unknown,
	keybindings: unknown,
	done: (result: undefined) => void,
) => unknown | Promise<unknown>;

/** Exposes the real overlay compositor (maxHeight slice + terminal bounds). */
class ProbeTui extends TuiMainScreen {
	clippedLines(width: number, height: number): string[] {
		return this.compositeOverlays([], width, height);
	}
}

interface CustomRecord {
	readonly fullText: string;
	readonly options: unknown;
	readonly component: PreviewComponentLike;
	readonly terminal: VirtualTerminal;
	readonly tui: ProbeTui;
}

function flatten(lines: readonly string[]): string {
	return lines
		.map((line) => stripTerminalSequences(line))
		.join("")
		.replace(/\s+/g, "");
}

/** Configured keybindings seam: no hardcoded matchesKey; ids are configurable
 * through the same matches(data, id) API the production component consumes. */
const keybindings = {
	matches: (data: string, id: string): boolean => data === id,
};

class ViewportUI {
	hasUI = true;
	mode = "tui";
	readonly cols: number;
	readonly rows: number;
	readonly deferred: boolean;
	readonly customReady: Promise<void>;
	private signalCustomReady: (() => void) | undefined;
	readonly confirms: Array<{ title: string; message: string }> = [];
	readonly customs: CustomRecord[] = [];
	readonly doneResults: unknown[] = [];
	readonly notifications: string[] = [];
	confirmAnswer = false;

	constructor(cols: number, rows: number, deferred = false) {
		this.cols = cols;
		this.rows = rows;
		this.deferred = deferred;
		this.customReady = new Promise<void>((resolve) => {
			this.signalCustomReady = resolve;
		});
	}
	notify(message: string): void {
		this.notifications.push(message);
	}
	async confirm(title: string, message: string): Promise<boolean> {
		this.confirms.push({ title, message });
		return this.confirmAnswer;
	}
	async input(): Promise<string | undefined> {
		return undefined;
	}
	async editor(): Promise<string | undefined> {
		return undefined;
	}
	async select(): Promise<string | undefined> {
		return undefined;
	}
	async custom(factory: unknown, options?: unknown): Promise<void> {
		const fn = factory as PreviewFactory;
		const terminal = new VirtualTerminal(this.cols, this.rows);
		const tui = new ProbeTui(terminal);
		// Real showExtensionCustom resolves ONLY when the component calls done().
		// Deferred mode emulates that promise for the FIRST (preview) overlay so a
		// live resize can happen before the flow reaches the final confirm; later
		// result-text overlays keep the immediate T-06 seam and never hang.
		const deferClose = this.deferred && this.customs.length === 0;
		const closeGate: { resolve: () => void } = { resolve: () => undefined };
		const closed = deferClose
			? new Promise<void>((resolve) => {
					closeGate.resolve = resolve;
				})
			: undefined;
		const done = (result: undefined): void => {
			this.doneResults.push(result);
			closeGate.resolve();
		};
		let component: PreviewComponentLike;
		try {
			component = (await fn(tui, undefined, keybindings, done)) as PreviewComponentLike;
		} catch (error) {
			this.signalCustomReady?.();
			tui.stop();
			throw error;
		}
		// The record stays live: frames are captured by the test AFTER custom()
		// resolves, so stop() must not clear the terminal viewport here.
		const opts = (options as { overlayOptions?: OverlayOptions }) ?? {};
		tui.showOverlay(component as unknown as Component, opts.overlayOptions ?? {});
		this.customs.push({ fullText: component.fullText, options, component, terminal, tui });
		this.signalCustomReady?.();
		if (closed) await closed;
	}
}

function preview(ui: ViewportUI): CustomRecord {
	const record = ui.customs.find((entry) => entry.fullText.includes(TAIL_MARK));
	expect(record, "real custom factory must produce the FULL preview overlay").toBeDefined();
	return record!;
}

/** A real clipped frame from BOTH the compositor and the terminal viewport. */
async function frame(record: CustomRecord, cols: number, rows: number): Promise<{ screen: string; terminal: string }> {
	record.tui.renderNow(true);
	await record.terminal.flush();
	const composed = record.tui.clippedLines(cols, rows);
	const visible = composed.slice(Math.max(0, composed.length - rows));
	return {
		screen: flatten(visible),
		terminal: flatten(record.terminal.getViewport()),
	};
}

const FIELDS: ReadonlyArray<readonly [string, string]> = [
	["title", "T09A viewport repair"],
	["component", "/mw issue report"],
	["occurredAt", "2026-11-13T08:12:00+08:00"],
	["trigger", "TRIGGER-VIEWPORT"],
	["precondition", "PRECONDITION-VIEWPORT"],
	["expected", "EXPECTED-VIEWPORT"],
	["actual", "ACTUAL-VIEWPORT"],
	["impact", "IMPACT-VIEWPORT"],
	["steps", `1. one; 2. two; 3. ${"tail-row-".repeat(40)} ${TAIL_MARK}`],
	["frequency", "每次"],
	["error", "ERROR-VIEWPORT"],
	["mwVersion", "0.8.1"],
	["piVersion", "0.12.2"],
	["platform", "Windows 11"],
	["windowType", "pi TUI"],
	["diagnostic", ""],
	["diagnosticKind", "log"],
	["candidate", ""],
];

function argsText(): string {
	return ["issue", "report", ...FIELDS.map(([key, value]) => `${key}="${value}"`)].join(" ");
}

const tmpRoots: string[] = [];
let savedWorkerTask: string | undefined;

beforeEach(() => {
	savedWorkerTask = process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_TASK;
});
afterEach(() => {
	if (savedWorkerTask === undefined) delete process.env.PI_WORKER_TASK;
	else process.env.PI_WORKER_TASK = savedWorkerTask;
	for (const dir of tmpRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function projectDir(): string {
	const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-t09a-")));
	tmpRoots.push(dir);
	fs.mkdirSync(path.join(dir, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(dir, ".agenticdoc", "goal.md"), "# goal\n", "utf8");
	return dir;
}

/** All writes are recorded; a refusal/cancel must leave this empty. */
function store(calls: string[]): IssueCommandStore {
	const record = (name: string): void => {
		calls.push(name);
	};
	return {
		submit: (request) => {
			record("submit");
			return {
				ok: true,
				code: "created",
				message: "",
				id: request.preparation.card.id,
				display: "created",
				reason: "",
				rootFailure: null,
			} as never;
		},
		retry: () => {
			record("retry");
			return {} as never;
		},
		status: () => {
			record("status");
			return {} as never;
		},
		list: () => {
			record("list");
			return {} as never;
		},
		appendProgress: () => {
			record("appendProgress");
			return {} as never;
		},
		reply: () => {
			record("reply");
			return {} as never;
		},
		listIncoming: () => {
			record("listIncoming");
			throw new Error("NO_CALL:listIncoming");
		},
		readIncoming: () => {
			record("readIncoming");
			throw new Error("NO_CALL:readIncoming");
		},
	};
}

async function run(ui: ViewportUI, calls: string[]): Promise<string> {
	const dir = projectDir();
	const ctx = { mode: "tui", hasUI: true, cwd: dir, ui } as unknown as ExtensionCommandContext;
	return runMwIssueCommand(ctx, dir, argsText(), {
		store: store(calls),
		pointerFile: path.join(dir, "pointer.json"),
		now: () => "2026-11-13T09:00:00.000Z",
	});
}

/** Starts /mw issue report with the FIRST overlay's close deferred, mirroring
 * the real showExtensionCustom promise: the final confirm is not reached until
 * the preview is closed, so a live resize can happen in between. */
function startDeferred(confirmAnswer = false): { ui: ViewportUI; calls: string[]; result: Promise<string> } {
	const ui = new ViewportUI(80, 12, true);
	ui.confirmAnswer = confirmAnswer;
	const calls: string[] = [];
	const result = run(ui, calls);
	void result.catch(() => undefined); // one handler; every test still awaits result
	return { ui, calls, result };
}

describe("T-09A effective viewport — real clipped frames", () => {
	it("80x12: footer and tail marker are reachable after real page-down scrolling", async () => {
		const ui = new ViewportUI(80, 12);
		const calls: string[] = [];
		await run(ui, calls);
		const record = preview(ui);
		const options = record.options as {
			overlay?: boolean;
			overlayOptions?: { width?: unknown; maxHeight?: unknown; anchor?: unknown };
		};
		expect(options.overlay).toBe(true);
		expect(options.overlayOptions?.width).toBe("92%");
		expect(options.overlayOptions?.maxHeight).toBe(ISSUE_PREVIEW_VIEWPORT_LINES + 4);

		const screens: string[] = [];
		const terminals: string[] = [];
		for (let step = 0; step < 80; step += 1) {
			const f = await frame(record, 80, 12);
			screens.push(f.screen);
			terminals.push(f.terminal);
			const before = f.screen;
			record.component.handleInput("tui.select.pageDown");
			const next = await frame(record, 80, 12);
			if (next.screen === before) break; // scrollTop clamped at the bottom
		}
		const screen = screens.join("");
		const terminal = terminals.join("");
		expect(record.component.fullText, "the exact FULL text is still handed to the overlay").toContain(TAIL_MARK);
		expect(screen, "tail marker missing from compositor-clipped frames").toContain(TAIL_MARK);
		expect(screen, "footer missing from compositor-clipped frames").toContain(FOOTER_MARK);
		expect(terminal, "tail marker missing from terminal viewport").toContain(TAIL_MARK);
		expect(terminal, "footer missing from terminal viewport").toContain(FOOTER_MARK);
		expect(calls, "no store write before a real confirmation").toEqual([]);
	});

	it("resize (height and width) recomputes the frame and keeps footer/tail reachable", async () => {
		const ui = new ViewportUI(80, 12);
		const calls: string[] = [];
		await run(ui, calls);
		const record = preview(ui);
		const width = Math.max(1, Math.min(Math.floor((80 * 92) / 100), 80));
		const shortRows = record.component.render(width).length;
		expect(shortRows).toBeLessThanOrEqual(12);

		// Real terminal resize: the component reads terminal.rows/columns live.
		record.terminal.resize(30, 10);
		const narrowWidth = Math.max(1, Math.min(Math.floor((30 * 92) / 100), 30));
		const narrowRows = record.component.render(narrowWidth).length;
		expect(narrowRows).toBeLessThanOrEqual(10);
		const f = await frame(record, 30, 10);
		expect(f.screen, "footer must survive a width+height resize").toContain(FOOTER_MARK);
		expect(f.terminal).toContain(FOOTER_MARK);

		// The wrapped header/footer now consume more rows: scrolling must still
		// reach the tail with the RECOMPUTED (smaller) content budget.
		const resizedScreens: string[] = [f.screen];
		for (let step = 0; step < 120; step += 1) {
			record.component.handleInput("tui.select.pageDown");
			resizedScreens.push((await frame(record, 30, 10)).screen);
		}
		expect(resizedScreens.join(""), "tail unreachable after resize").toContain(TAIL_MARK);
		for (const screen of resizedScreens) expect(screen).toContain(FOOTER_MARK);
		expect(calls).toEqual([]);
	});

	it("single-line down/up scrolls by exactly one source row (dynamic page step)", async () => {
		const ui = new ViewportUI(80, 12);
		const calls: string[] = [];
		await run(ui, calls);
		const record = preview(ui);
		const width = Math.max(1, Math.min(Math.floor((80 * 92) / 100), 80));
		const first = record.component.render(width);
		record.component.handleInput("tui.select.down");
		const second = record.component.render(width);
		// Exactly ONE content row advanced: the header's start line moves by 1.
		const startOf = (frame: readonly string[]): number => Number(/第 (\d+)-/.exec(frame[0] ?? "")?.[1] ?? "0");
		expect(startOf(second) - startOf(first)).toBe(1);
		record.component.handleInput("tui.select.up");
		expect(record.component.render(width)).toEqual(first);
		// A page step uses the effective content rows, never the fixed cap.
		record.component.handleInput("tui.select.pageDown");
		expect(record.component.render(width)).not.toEqual(first);
		expect(calls).toEqual([]);
	});

	it("Esc/CtrlC closes the preview, continues to the final confirm, and writes nothing", async () => {
		for (const key of ["tui.select.cancel", "app.interrupt", "tui.select.confirm"]) {
			const ui = new ViewportUI(80, 12);
			const calls: string[] = [];
			const text = await run(ui, calls);
			const record = preview(ui);
			record.component.handleInput(key);
			expect(ui.doneResults, `${key}: preview must close`).toHaveLength(1);
			expect(ui.confirms, `${key}: flow must CONTINUE to the final confirm`).toHaveLength(1);
			expect(ui.confirms[0]!.message, `${key}: confirm uses the exact FULL text`).toBe(record.fullText);
			expect(text).toContain("未提交");
			expect(calls, `${key}: zero store writes`).toEqual([]);
		}
	});

	it("extremely short terminal explicitly refuses instead of silently submitting", async () => {
		const ui = new ViewportUI(40, 3);
		const calls: string[] = [];
		const text = await run(ui, calls);
		expect(text).toContain("确认/预览界面异常");
		expect(text).toContain("终端高度");
		expect(text).toContain("未执行任何写入");
		expect(text).toContain("未提交");
		expect(ui.customs, "no overlay may claim an incomplete preview is complete").toEqual([]);
		expect(ui.confirms, "no confirm of a non-displayable preview").toEqual([]);
		expect(calls, "zero store writes").toEqual([]);
	});

	it("live resize 80x12 -> 3 rows: closing an unusable preview refuses before confirm/write", async () => {
		for (const key of ["tui.select.cancel", "app.interrupt", "tui.select.confirm"]) {
			const { ui, calls, result } = startDeferred();
			await ui.customReady;
			const record = preview(ui);
			const usable = await frame(record, 80, 12);
			expect(usable.screen, "80x12 preview starts usable").toContain(FOOTER_MARK);
			expect(usable.terminal).toContain(FOOTER_MARK);

			record.terminal.resize(80, 3);
			const degenerate = await frame(record, 80, 3);
			expect(degenerate.screen, `${key}: degenerate frame must state it is unusable`).toContain("终端高度不足");
			expect(degenerate.screen, `${key}: no FULL-preview footer in a degenerate frame`).not.toContain(FOOTER_MARK);
			expect(degenerate.screen, `${key}: no source tail in a degenerate frame`).not.toContain(TAIL_MARK);

			record.component.handleInput(key);
			expect(ui.doneResults, `${key}: preview closes`).toHaveLength(1);
			const text = await result;
			expect(text, `${key}: explicit refusal, never a silent submit`).toContain("确认/预览界面异常");
			expect(text).toContain("终端高度");
			expect(text).toContain("未执行任何写入");
			expect(text).toContain("未提交");
			expect(ui.confirms, `${key}: final confirm must NOT be entered`).toEqual([]);
			expect(calls, `${key}: zero store writes`).toEqual([]);
		}
	});

	it("resize back to a usable height keeps Esc/CtrlC continue-to-confirm semantics", async () => {
		for (const key of ["tui.select.cancel", "app.interrupt"]) {
			const { ui, calls, result } = startDeferred();
			await ui.customReady;
			const record = preview(ui);
			record.terminal.resize(80, 3);
			const degenerate = await frame(record, 80, 3);
			expect(degenerate.screen).toContain("终端高度不足");
			expect(degenerate.screen).not.toContain(FOOTER_MARK);

			record.terminal.resize(80, 12);
			const recovered = await frame(record, 80, 12);
			expect(recovered.screen, "footer returns after recovery").toContain(FOOTER_MARK);
			const screens: string[] = [recovered.screen];
			for (let step = 0; step < 120; step += 1) {
				record.component.handleInput("tui.select.pageDown");
				screens.push((await frame(record, 80, 12)).screen);
			}
			expect(screens.join(""), "tail reachable with the recomputed budget").toContain(TAIL_MARK);

			record.component.handleInput(key);
			expect(ui.doneResults, `${key}: preview closes`).toHaveLength(1);
			const text = await result;
			expect(text, `${key}: recovery must NOT turn a normal cancel into an abort`).not.toContain(
				"确认/预览界面异常",
			);
			expect(ui.confirms, `${key}: flow CONTINUES to the final confirm`).toHaveLength(1);
			expect(ui.confirms[0]!.message).toBe(record.fullText);
			expect(text).toContain("未提交");
			expect(calls, `${key}: no write without a real confirm`).toEqual([]);
		}
	});

	it("recovered usable height keeps the normal write path after a real confirm", async () => {
		const { ui, calls, result } = startDeferred(true);
		await ui.customReady;
		const record = preview(ui);
		record.terminal.resize(80, 3);
		expect((await frame(record, 80, 3)).screen).toContain("终端高度不足");
		record.terminal.resize(80, 12);
		expect((await frame(record, 80, 12)).screen).toContain(FOOTER_MARK);
		record.component.handleInput("tui.select.confirm");
		const text = await result;
		expect(ui.confirms).toHaveLength(1);
		expect(ui.confirms[0]!.message).toBe(record.fullText);
		expect(calls, "a real confirm must still reach the store").toEqual(["submit"]);
		expect(text).toContain("MW 问题反馈 — 提交结果");
		expect(text).toContain(TAIL_MARK);
	});
});
