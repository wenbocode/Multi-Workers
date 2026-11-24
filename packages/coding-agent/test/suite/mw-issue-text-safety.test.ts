/**
 * mw-issue-text-safety.test.ts — T-09C / R03 control-text safety regression.
 *
 * Threat (B-03): untrusted report/update/reply/status text that contains real
 * ESC/C0/C1/ANSI/OSC/APC/cursor-erase/bidi control bytes is handed to the real
 * full-text preview overlay, whose wrapTextWithAnsi PRESERVES ANSI. A terminal
 * then executes those bytes (SGR 8 conceal, CSI erase, cursor move, OSC ...),
 * so "the buffer string still contains the sentinel" is NOT proof the user can
 * verify the payload word-by-word.
 *
 * These cases go through the ACTUAL registered /mw handler
 * (registerMwCommands -> "mw" -> runMwIssueCommand -> frozen T-04 module) with
 * a REAL IssueStore over temp fixtures, the REAL full-text preview component
 * (presentIssueFullText via ctx.ui.custom), the REAL TuiMainScreen overlay
 * compositor and a REAL @xterm/headless terminal. We inspect xterm CELL
 * attributes (isInvisible / position / chars), not just translateToString.
 *
 * Long-text tail clipping is R01 / T-09A (in-flight, parallel). Its sentinels
 * live in EARLY scene fields reachable in the first overlay window; this suite
 * does not depend on that fix and does not weaken T-06's four reds.
 *
 * Frozen T-01..T-05 sources/tests are consumed, never modified.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import { createRequire } from "node:module";
import * as os from "node:os";
import * as path from "node:path";
import {
	type Component,
	KeybindingsManager,
	type OverlayOptions,
	TuiMainScreen,
	wrapTextWithAnsi,
} from "@earendil-works/pi-tui";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { VirtualTerminal } from "../../../tui/test/virtual-terminal.ts";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import { KEYBINDINGS } from "../../src/core/keybindings.ts";
import type { IssueCommandStore } from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import {
	canonicalPayload,
	confirmIssue,
	type IssueDraft,
	type PrepareOptions,
	prepareIssue,
	redactSecrets,
	renderPreview,
	unknownObservation,
	userObservation,
} from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	ISSUE_EVENTS_DIR_BASENAME,
	IssueStore,
	issueAuthorityBasePath,
	issueAuthorityLogPath,
	issueLocalIndexPath,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";
import {
	countUnsafeControls,
	escapeUntrustedText,
	hasUnsafeControls,
	ISSUE_CONTROL_ESCAPE_PREFIX,
	ISSUE_CONTROL_ESCAPE_RULE,
	ISSUE_CONTROL_ESCAPE_SUFFIX,
	isUnsafeControlCode,
	neutralizeControlText,
} from "../../src/extensions/agent-team-loop/shared/issue-text.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

// ── Real xterm headless terminal, accessed at the CELL level ─────────────────

interface CellLike {
	getChars(): string;
	isInvisible(): number;
	getWidth(): number;
}
interface LineLike {
	length: number;
	translateToString(trimRight?: boolean): string;
	getCell(x: number): CellLike | undefined;
}
interface BufferLike {
	active: {
		length: number;
		viewportY: number;
		cursorX: number;
		cursorY: number;
		getLine(y: number): LineLike | undefined;
	};
}
interface XtermLike {
	buffer: BufferLike;
	write(data: string, callback?: () => void): void;
}
interface XtermOptions {
	cols: number;
	rows: number;
	allowProposedApi: boolean;
	disableStdin: boolean;
}

const requireFromHere = createRequire(import.meta.url);
const XtermTerminalCtor = requireFromHere("@xterm/headless").Terminal as new (o: XtermOptions) => XtermLike;

interface CellScan {
	all: string;
	visible: string;
	invisible: string;
	invisibleCount: number;
	viewport: string;
}

/** Write screen lines into a fresh real xterm and inspect EVERY cell. This is
 * deliberately NOT translateToString: invisible (SGR 8) cells keep their chars,
 * so a plain "buffer contains the sentinel" check would be a false PASS. */
async function scanAllCells(lines: readonly string[], cols: number): Promise<CellScan> {
	const rows = Math.max(lines.length + 2, 4);
	const xt = new XtermTerminalCtor({ cols, rows, allowProposedApi: true, disableStdin: true });
	await new Promise<void>((resolve) => xt.write(lines.join("\r\n"), () => resolve()));
	const buf = xt.buffer.active;
	let all = "";
	let visible = "";
	let invisible = "";
	let invisibleCount = 0;
	for (let y = 0; y < buf.length; y++) {
		const line = buf.getLine(y);
		if (!line) continue;
		for (let x = 0; x < cols; x++) {
			const cell = line.getCell(x);
			if (!cell) continue;
			const chars = cell.getChars();
			all += chars;
			if (cell.isInvisible() !== 0) {
				invisible += chars;
				invisibleCount += 1;
			} else {
				visible += chars;
			}
		}
	}
	let viewport = "";
	for (let i = 0; i < rows; i++) {
		const line = buf.getLine(buf.viewportY + i);
		viewport += line ? line.translateToString(true) : "";
	}
	return { all, visible, invisible, invisibleCount, viewport };
}

/** The REAL wrap function used by presentIssueFullText (preserves ANSI, restores
 * SGR 8 across wrapped lines). */
function wrapLines(text: string, cols: number): string[] {
	const out: string[] = [];
	for (const line of text.replace(/\r\n/g, "\n").split("\n")) {
		if (line === "") {
			out.push("");
			continue;
		}
		out.push(...wrapTextWithAnsi(line, cols));
	}
	return out;
}

async function scanWrapped(text: string, cols: number): Promise<CellScan> {
	return scanAllCells(wrapLines(text, cols), cols);
}

/** The REAL overlay compositor (maxHeight clamp + column compositing). */
class OverlayProbeTui extends TuiMainScreen {
	composed(width: number, height: number): string[] {
		return this.compositeOverlays([], width, height);
	}
}

// ── Untrusted payloads: distinct ASCII sentinels per attack class ────────────

const ESC = "\x1b";
const BEL = "\x07";
const RLO = "\u202e";
const PDF = "\u202c";
const CSI8 = "\u009b";

const CONCEAL = `C-HEAD${ESC}[8mCONCEAL-SENTINEL${ESC}[0mC-TAIL`; // SGR 8 hide
const ERASE = `E-HEAD${ESC}[2K${ESC}[1GERASE-SENTINEL`; // erase line + cursor col 1
const CURSOR = `X-HEAD${ESC}[5DCURSOR-SENTINEL`; // cursor back 5 -> overwrite
const OSC = `O-HEAD${ESC}]0;pwned-title${BEL}OSC-SENTINEL`; // OSC title + BEL
const BIDI = `B-HEAD${RLO}BIDI-SENTINEL${PDF}B-TAIL`; // bidi override + PDF
const CSI_ERASE = `I-HEAD${CSI8}2JCSI-SENTINEL`; // 8-bit CSI erase display
const TABCR = `STEPS-HEAD\tTAB-SENTINEL\rCR-SENTINEL`; // tab + carriage return
const NORMAL = "正常中文前提 e\u0301 保留"; // normal CJK + combining mark must survive

const SENTINELS = [
	"CONCEAL-SENTINEL",
	"ERASE-SENTINEL",
	"CURSOR-SENTINEL",
	"OSC-SENTINEL",
	"BIDI-SENTINEL",
	"CSI-SENTINEL",
	"TAB-SENTINEL",
	"CR-SENTINEL",
] as const;
const ALL_HEADS = ["C-HEAD", "E-HEAD", "X-HEAD", "O-HEAD", "B-HEAD", "I-HEAD", "STEPS-HEAD"] as const;
// update only has 5 free-text fields; CSI/TAB/CR attacks are exercised in report/reply.
const UPDATE_SENTINELS = [
	"CONCEAL-SENTINEL",
	"ERASE-SENTINEL",
	"CURSOR-SENTINEL",
	"OSC-SENTINEL",
	"BIDI-SENTINEL",
] as const;
const UPDATE_HEADS = ["C-HEAD", "E-HEAD", "X-HEAD", "O-HEAD", "B-HEAD"] as const;

/** Raw unsafe control bytes, excluding the intentionally preserved LF (U+000A).
 * Locale-independent code-unit check (no dependency on the product helper). */
const RAW_CONTROL =
	/[\u0000-\u0009\u000b-\u001f\u007f-\u009f\u00ad\u061c\u180e\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff]/;

function hasRawControl(text: string): boolean {
	return RAW_CONTROL.test(text);
}

// ── Temp fixtures (real dev repo + pointer + one reporter project) ───────────

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

interface Fixture {
	top: string;
	pointerFile: string;
	devRoot: string;
	projectA: string;
}

function fixture(): Fixture {
	const top = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-ctl-")));
	tmpRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	const projectA = path.join(top, "project-a");
	fs.mkdirSync(path.join(devRoot, "packages", "multi-workers"), { recursive: true });
	fs.writeFileSync(path.join(devRoot, "packages", "multi-workers", "mw.py"), "# offline\n", "utf8");
	fs.mkdirSync(path.join(devRoot, "packages", "coding-agent", "src", "extensions", "agent-team-loop"), {
		recursive: true,
	});
	fs.mkdirSync(path.join(devRoot, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(devRoot, ".agenticdoc", "goal.md"), "# Project Goal\n", "utf8");
	fs.mkdirSync(path.join(projectA, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(projectA, ".agenticdoc", "goal.md"), "# project-a goal\n", "utf8");
	return {
		top,
		pointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME),
		devRoot: fs.realpathSync(devRoot),
		projectA: fs.realpathSync(projectA),
	};
}

function makeClock(): () => string {
	let tick = 0;
	const base = Date.parse("2026-11-13T09:00:00+08:00");
	return () => new Date(base + tick++ * 1000).toISOString();
}

function storeFor(projectRoot: string, fx: Fixture): IssueStore {
	return new IssueStore({ projectRoot, pointerFile: fx.pointerFile, env: {} });
}

interface MwCommand {
	handler: (args: string, ctx: ExtensionCommandContext) => Promise<void>;
}

function makeMw(projectDir: string, fx: Fixture, store: IssueStore, clock: () => string): MwCommand {
	const handlers = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const pi = {
		registerCommand: (
			name: string,
			def: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			handlers.set(name, def.handler);
		},
	} as unknown as ExtensionAPI;
	registerMwCommands(pi, projectDir, new WorkerStore(projectDir), {} as AckStore, { key: undefined }, projectDir, {
		store: store as unknown as IssueCommandStore,
		pointerFile: fx.pointerFile,
		now: clock,
	});
	const handler = handlers.get("mw");
	if (!handler) throw new Error("/mw command not registered");
	return { handler };
}

function fakeCtx(ui: object, projectDir: string): ExtensionCommandContext {
	return {
		mode: (ui as { mode: string }).mode,
		hasUI: (ui as { hasUI: boolean }).hasUI,
		cwd: projectDir,
		ui,
	} as unknown as ExtensionCommandContext;
}

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

// ── UI seam: real preview component + real compositor + real xterm cells ─────

interface CustomCapture {
	fullText: string;
	compositor: CellScan;
}

type PreviewFactory = (
	tui: unknown,
	theme: unknown,
	keybindings: unknown,
	done: (result: undefined) => void,
) => unknown | Promise<unknown>;

interface PreviewComponentLike {
	fullText: string;
	render(width: number): string[];
	invalidate(): void;
	handleInput?(data: string): void;
}

class XtermCellUI {
	hasUI = true;
	mode = "tui";
	readonly cols: number;
	readonly rows: number;
	readonly confirmAnswers: unknown[] = [];
	readonly confirms: Array<{ title: string; message: string }> = [];
	readonly customs: CustomCapture[] = [];
	readonly capturedTexts: string[] = [];
	readonly cellScans: CellScan[] = [];

	constructor(cols: number, rows: number) {
		this.cols = cols;
		this.rows = rows;
	}

	notify(): void {}
	async input(): Promise<string | undefined> {
		return "";
	}
	async editor(): Promise<string | undefined> {
		return "";
	}
	async select(): Promise<string | undefined> {
		return undefined;
	}
	async confirm(title: string, message: string): Promise<boolean> {
		this.confirms.push({ title, message });
		this.capturedTexts.push(message);
		this.cellScans.push(await scanWrapped(message, this.cols));
		return this.confirmAnswers.shift() as boolean;
	}
	async custom(factory: unknown, options?: unknown): Promise<void> {
		const fn = factory as PreviewFactory;
		const terminal = new VirtualTerminal(this.cols, this.rows);
		const tui = new OverlayProbeTui(terminal);
		const keybindings = new KeybindingsManager(KEYBINDINGS);
		const done = (_result: undefined): void => {};
		const component = (await fn(tui, undefined, keybindings, done)) as PreviewComponentLike;
		const opts = (options as { overlayOptions?: OverlayOptions }) ?? {};
		tui.showOverlay(component as unknown as Component, opts.overlayOptions ?? {});
		const fullText = component.fullText;
		this.capturedTexts.push(fullText);
		const wrapped = await scanWrapped(fullText, this.cols);
		const composed = tui.composed(this.cols, Math.max(this.rows, 24));
		const compositor = await scanAllCells(composed, this.cols);
		this.cellScans.push(wrapped, compositor);
		this.customs.push({ fullText, compositor });
		tui.stop();
	}
}

async function bindViaWindow(fx: Fixture, clock: () => string): Promise<void> {
	const mw = makeMw(fx.devRoot, fx, storeFor(fx.devRoot, fx), clock);
	const ui = new XtermCellUI(100, 30);
	ui.confirmAnswers.push(true);
	await mw.handler("issue bind", fakeCtx(ui, fx.devRoot));
	if (!fs.existsSync(fx.pointerFile)) throw new Error("fixture /mw issue bind failed");
}

interface ReportArgsOptions {
	readonly attacked: boolean;
}

function reportArgs(opts: ReportArgsOptions): string {
	const values: ReadonlyArray<readonly [string, string]> = [
		["title", opts.attacked ? CONCEAL : "普通故障标题"],
		["component", "/mw status"],
		["occurredAt", "2026-11-13T08:12:00+08:00"],
		["trigger", opts.attacked ? ERASE : "TRIGGER-MARK"],
		["precondition", NORMAL],
		["expected", opts.attacked ? CURSOR : "EXPECTED-MARK"],
		["actual", opts.attacked ? OSC : "ACTUAL-MARK"],
		["impact", opts.attacked ? BIDI : "IMPACT-MARK"],
		["steps", opts.attacked ? TABCR : "1. 运行 /mw status"],
		["frequency", "偶发"],
		["error", opts.attacked ? CSI_ERASE : "普通错误片段"],
		["mwVersion", "0.8.1"],
		["piVersion", "0.12.2"],
		["platform", "Windows 11"],
		["windowType", "pi TUI"],
		["diagnostic", ""],
		["diagnosticKind", "log"],
		["candidate", ""],
	];
	return ["issue", "report", ...values.map(([key, value]) => field(key, value))].join(" ");
}

function updateArgs(id: string, attacked: boolean): string {
	const values: ReadonlyArray<readonly [string, string]> = [
		["status", "已修复"],
		["statusNote", attacked ? `${CONCEAL} ${NORMAL}` : `普通分诊结论 ${NORMAL}`],
		["nextAction", attacked ? ERASE : "下一步"],
		["fixCommit", attacked ? CURSOR : "abc1234"],
		["releaseVersion", attacked ? OSC : "0.12.5"],
		["question", attacked ? BIDI : ""],
	];
	return ["issue", "update", id, ...values.map(([key, value]) => field(key, value))].join(" ");
}

function replyArgs(id: string, attacked: boolean): string {
	const text = attacked
		? `${CONCEAL} | ${ERASE} | ${CURSOR} | ${OSC} | ${BIDI} | ${CSI_ERASE} | ${TABCR} | ${NORMAL}`
		: `普通补充：重启发生在 08:10 ${NORMAL}`;
	return ["issue", "reply", id, field("text", text)].join(" ");
}

function localId(projectRoot: string): string {
	const file = issueLocalIndexPath(projectRoot);
	const index = JSON.parse(fs.readFileSync(file, "utf8")) as { records: Array<{ id: string }> };
	if (index.records.length !== 1) throw new Error(`expected 1 local record, got ${index.records.length}`);
	return index.records[0].id;
}

function authorityText(fx: Fixture, id: string): string {
	const file = issueAuthorityLogPath(fx.devRoot, id);
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
}

function authorityLogCount(fx: Fixture): number {
	const dir = path.join(issueAuthorityBasePath(fx.devRoot), ISSUE_EVENTS_DIR_BASENAME);
	if (!fs.existsSync(dir)) return 0;
	return fs.readdirSync(dir).filter((name) => name.endsWith(".jsonl")).length;
}

interface AggScan {
	all: string;
	visible: string;
	invisible: string;
	invisibleCount: number;
	viewport: string;
}

function aggregate(scans: readonly CellScan[]): AggScan {
	const out: AggScan = { all: "", visible: "", invisible: "", invisibleCount: 0, viewport: "" };
	for (const s of scans) {
		out.all += s.all;
		out.visible += s.visible;
		out.invisible += s.invisible;
		out.invisibleCount += s.invisibleCount;
		out.viewport += s.viewport;
	}
	return out;
}

/** The central R03 oracle. `label` names the flow/viewport for evidence. */
function assertSafe(
	ui: XtermCellUI,
	label: string,
	sentinels: readonly string[],
	heads: readonly string[] = ALL_HEADS,
): void {
	const cells = aggregate(ui.cellScans);
	// Log the oracle trap explicitly: translateToString (getViewport-style)
	// KEEPS invisible-cell chars, so "viewport contains the sentinel" is a false
	// PASS. Only isInvisible() per cell proves the payload is actually readable.
	const trap = sentinels.filter((s) => cells.viewport.includes(s));
	const hidden = sentinels.filter((s) => cells.invisible.includes(s));
	const shown = sentinels.filter((s) => cells.visible.includes(s));
	verify(
		`${label}: texts=${ui.capturedTexts.length} scans=${ui.cellScans.length} invisibleCells=${cells.invisibleCount} ` +
			`viewportContainsSentinel(trap)=${trap.length}/${sentinels.length} ` +
			`visibleCellSentinels=${shown.length}/${sentinels.length} hiddenCellSentinels=${hidden.length}`,
	);

	// CELL level (primary, discriminating oracle): sentinels are VISIBLE (never
	// in isInvisible cells), head/tail markers not erased/overwritten.
	for (const sentinel of sentinels) {
		expect(
			cells.visible,
			`${label}: ${sentinel} must be in VISIBLE xterm cells (buffer-contains is not enough)`,
		).toContain(sentinel);
		expect(cells.invisible, `${label}: ${sentinel} must NEVER be in invisible (SGR 8) cells`).not.toContain(sentinel);
		expect(cells.all, `${label}: ${sentinel} must not be erased`).toContain(sentinel);
	}
	for (const head of heads) {
		expect(cells.visible, `${label}: head marker ${head} was erased/moved away`).toContain(head);
	}

	// STRING level: no raw terminal-control bytes reached any user-facing text;
	// nothing deleted; normal CJK / combining text and LF structure survive.
	for (const text of ui.capturedTexts) {
		expect(hasRawControl(text), `${label}: raw control bytes leaked into a user-facing string`).toBe(false);
		expect(text, `${label}: normal CJK + combining mark must be preserved`).toContain(NORMAL);
	}
	const joined = ui.capturedTexts.join("\n");
	for (const sentinel of sentinels) {
		expect(joined, `${label}: sentinel ${sentinel} was silently deleted`).toContain(sentinel);
	}
	expect(joined.split("\n").length, `${label}: LF newlines must be preserved`).toBeGreaterThan(3);

	// Confirmation preview is byte-identical to the string fed to the real dialog
	// (hash/payload 1:1) and the same string reaches the compositor.
	const confirmed = ui.confirms.find((c) => ui.customs.some((cu) => cu.fullText === c.message));
	expect(confirmed, `${label}: confirm() must use the exact full preview text`).toBeDefined();
}

// ── report / update / reply / status flows ──────────────────────────────────

const VIEWPORTS = [
	{ label: "wide-100x30", cols: 100, rows: 30 },
	{ label: "narrow-30x24", cols: 30, rows: 24 },
	{ label: "short-80x10", cols: 80, rows: 10 },
] as const;

describe.each(VIEWPORTS)("R03 report: untrusted control text neutralized ($label)", (vp) => {
	it("no raw control bytes, visible cells, hash-bound preview, refusal zero-write", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = makeMw(fx.projectA, fx, storeFor(fx.projectA, fx), clock);
		const ui = new XtermCellUI(vp.cols, vp.rows);
		ui.confirmAnswers.push(true);
		await a.handler(reportArgs({ attacked: true }), fakeCtx(ui, fx.projectA));

		assertSafe(ui, `report ${vp.label}`, SENTINELS, ALL_HEADS);

		// Authoritative record is traceable: same sentinels, no raw control bytes.
		const id = localId(fx.projectA);
		const bytes = authorityText(fx, id);
		expect(bytes.length).toBeGreaterThan(0);
		for (const sentinel of SENTINELS) expect(bytes, `authority must keep ${sentinel}`).toContain(sentinel);
		expect(hasRawControl(bytes), "authority record must not hold raw control bytes").toBe(false);
	});
});

describe("R03 update/reply/status through the registered handler", () => {
	it("update: dev-window progress preview is safe and hash-bound", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = makeMw(fx.projectA, fx, storeFor(fx.projectA, fx), clock);
		const setupUi = new XtermCellUI(100, 30);
		setupUi.confirmAnswers.push(true);
		await a.handler(reportArgs({ attacked: false }), fakeCtx(setupUi, fx.projectA));
		const id = localId(fx.projectA);

		const d = makeMw(fx.devRoot, fx, storeFor(fx.devRoot, fx), clock);
		const ui = new XtermCellUI(40, 24);
		ui.confirmAnswers.push(true);
		await d.handler(updateArgs(id, true), fakeCtx(ui, fx.devRoot));

		assertSafe(ui, "update 40x24", UPDATE_SENTINELS, UPDATE_HEADS);
		const bytes = authorityText(fx, id);
		for (const sentinel of UPDATE_SENTINELS) expect(bytes, `authority must keep ${sentinel}`).toContain(sentinel);
		expect(hasRawControl(bytes)).toBe(false);
	});

	it("reply: reporter reply preview is safe and hash-bound", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = makeMw(fx.projectA, fx, storeFor(fx.projectA, fx), clock);
		const setupUi = new XtermCellUI(100, 30);
		setupUi.confirmAnswers.push(true);
		await a.handler(reportArgs({ attacked: false }), fakeCtx(setupUi, fx.projectA));
		const id = localId(fx.projectA);

		const ui = new XtermCellUI(30, 24);
		ui.confirmAnswers.push(true);
		await a.handler(replyArgs(id, true), fakeCtx(ui, fx.projectA));

		assertSafe(ui, "reply 30x24", SENTINELS, ALL_HEADS);
		const bytes = authorityText(fx, id);
		for (const sentinel of SENTINELS) expect(bytes, `authority must keep ${sentinel}`).toContain(sentinel);
		expect(hasRawControl(bytes)).toBe(false);
	});

	it("status/result: displayed projection carries no raw control bytes", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = makeMw(fx.projectA, fx, storeFor(fx.projectA, fx), clock);
		const setupUi = new XtermCellUI(100, 30);
		setupUi.confirmAnswers.push(true);
		await a.handler(reportArgs({ attacked: true }), fakeCtx(setupUi, fx.projectA));
		const id = localId(fx.projectA);

		const ui = new XtermCellUI(80, 24);
		await a.handler(`issue status ${id}`, fakeCtx(ui, fx.projectA));
		for (const text of ui.capturedTexts) {
			expect(hasRawControl(text), "status projection must not hold raw control bytes").toBe(false);
		}
		expect(ui.capturedTexts.join("\n")).toContain("CONCEAL-SENTINEL");
	});

	it("refusal (no true) and non-boolean truthy answers leave zero writes", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = makeMw(fx.projectA, fx, storeFor(fx.projectA, fx), clock);

		const refused = new XtermCellUI(80, 24);
		refused.confirmAnswers.push(false);
		await a.handler(reportArgs({ attacked: true }), fakeCtx(refused, fx.projectA));
		expect(authorityLogCount(fx)).toBe(0);

		const truthy = new XtermCellUI(80, 24);
		truthy.confirmAnswers.push("true" as unknown as boolean); // truthy but NOT === true
		await a.handler(reportArgs({ attacked: true }), fakeCtx(truthy, fx.projectA));
		expect(authorityLogCount(fx)).toBe(0);
		expect(issueLocalIndexPath(fx.projectA) && fs.existsSync(issueLocalIndexPath(fx.projectA))).toBe(false);
	});
});

// ── Helper + pipeline unit tests (representation / idempotency / 1:1 hash) ──

const P = ISSUE_CONTROL_ESCAPE_PREFIX;
const S = ISSUE_CONTROL_ESCAPE_SUFFIX;

function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

const CTL_OPTIONS: PrepareOptions = {
	submittedAt: "2026-11-13T09:00:00+08:00",
	environmentObservedAt: "2026-11-13T09:00:00+08:00",
	knownSecrets: [],
};

function ctlDraft(): IssueDraft {
	return {
		id: "fb-0123456789abcdef0123456789abcdef",
		title: `CTL 标题${ESC}[8mCONCEAL-SENTINEL${ESC}[0m结尾`,
		projectLabel: "project-A",
		component: unknownObservation(),
		occurredAt: userObservation("2026-11-13T08:12:00+08:00", "2026-11-13T09:00:00+08:00"),
		trigger: userObservation(`TRIG\tTAB\rCR${BEL}`),
		precondition: unknownObservation(),
		expected: userObservation("EXPECTED"),
		actual: userObservation(`ACTUAL${CSI8}2JCSI-SENTINEL 正常中文 e\u0301 😀`),
		impact: userObservation(`IMPACT${RLO}BIDI${PDF}`),
		reproductionSteps: userObservation("1. a\n2. b\n3. c"),
		reproductionFrequency: "偶发",
		errorExcerpt: userObservation(`ERR${ESC}]0;x${BEL}OSC`),
		environmentAtFailure: {
			mwVersion: unknownObservation(),
			piVersion: unknownObservation(),
			platform: unknownObservation(),
			windowType: unknownObservation(),
		},
		observedEnvironment: {
			mwVersion: unknownObservation(),
			piVersion: unknownObservation(),
			platform: unknownObservation(),
			windowType: unknownObservation(),
			bundleStatus: unknownObservation(),
			serveStatus: unknownObservation(),
		},
		diagnosticCandidates: [{ id: "d1", kind: "log", text: `diag${ESC}[2Kerase` }],
		selectedFragmentIds: ["d1"],
	};
}

describe("R03 helper (issue-text.ts): deterministic, visible, idempotent escape", () => {
	it("idempotent, ASCII-only output, LF kept, normal CJK/combining/emoji preserved", () => {
		const src = `A${ESC}[8mHIDE${ESC}[0m\tB\rC${RLO}D${PDF}${BEL}${CSI8}2J\nLINE2 中文 e\u0301 😀`;
		const once = escapeUntrustedText(src);
		expect(escapeUntrustedText(once)).toBe(once); // f(f(x)) === f(x)
		expect(hasUnsafeControls(once)).toBe(false);
		expect(RAW_CONTROL.test(once)).toBe(false);
		expect(once).toContain("\n"); // normal LF preserved
		expect(once).toContain("中文 e\u0301 😀"); // no over-neutralization
		expect(once).toContain(`${P}001B${S}`); // ESC made visible
		expect(once).toContain("HIDE"); // original text not deleted
	});

	it("maps each control class to a documented, traceable token; keeps LF", () => {
		const cases: ReadonlyArray<readonly [string, string]> = [
			["\t", "0009"],
			["\r", "000d"],
			[ESC, "001b"],
			[BEL, "0007"],
			["\u007f", "007f"],
			[CSI8, "009b"],
			[RLO, "202e"],
			[PDF, "202c"],
			["\ufeff", "feff"],
			["\u200b", "200b"],
		];
		for (const [raw, hex] of cases) {
			expect(escapeUntrustedText(raw), `code U+${hex}`).toBe(`${P}${hex.toUpperCase()}${S}`);
		}
		expect(escapeUntrustedText("\n")).toBe("\n");
		expect(isUnsafeControlCode(0x000a)).toBe(false);
		expect(isUnsafeControlCode(0x001b)).toBe(true);
		expect(ISSUE_CONTROL_ESCAPE_RULE).toContain("LF");
	});

	it("leaves 7-bit IDs / event hashes / filesystem-like paths untouched (no access confusion)", () => {
		for (const value of [
			"fb-0123456789abcdef0123456789abcdef",
			"a1b2c3d4".repeat(8),
			"C:/work/mw-dev/.agenticdoc/mw-issue-feedback/authority",
		]) {
			expect(escapeUntrustedText(value)).toBe(value);
			expect(hasUnsafeControls(value)).toBe(false);
		}
	});

	it("counts ONLY control code points (never secret hits); redactSecrets stays raw-leaf", () => {
		expect(neutralizeControlText(`x${ESC}${BEL}${RLO}y`).count).toBe(3);
		expect(countUnsafeControls("plain ASCII 中文")).toBe(0);
		// D's store raw-leaf check depends on redactSecrets NOT neutralizing controls.
		const raw = `a${ESC}b`;
		const red = redactSecrets(raw, []);
		expect(red.text).toBe(raw); // unchanged: control bytes left raw for the leaf check
		expect(red.redactions).toBe(0);
	});
});

describe("R03 pipeline: canonical payload === preview === digest (1:1), idempotent", () => {
	it("prepareIssue stores the SAME visible representation in payload and preview; hash binds; re-prepare identical", () => {
		const draft = ctlDraft();
		const a = prepareIssue(draft, CTL_OPTIONS);
		const b = prepareIssue(draft, CTL_OPTIONS);
		const marker = `${P}001B${S}`;

		// No raw control bytes in either the confirmed preview or the payload.
		expect(hasUnsafeControls(a.preview)).toBe(false);
		expect(hasUnsafeControls(canonicalPayload(a.card))).toBe(false);
		// The SAME deterministic visible token lives in BOTH (no show-A/submit-B).
		expect(canonicalPayload(a.card)).toContain(marker);
		expect(a.preview).toContain(marker);
		expect(a.preview).toContain("CONCEAL-SENTINEL"); // not deleted
		expect(a.preview).toContain("正常中文 e\u0301 😀"); // normal text kept
		expect(a.preview).toContain("1. a\n2. b\n3. c"); // LF structure preserved

		// Digest binds 1:1 to exactly the preview the user confirms.
		expect(a.previewSha256).toBe(sha256(a.preview));
		expect(renderPreview(a.card)).toBe(a.preview); // re-render is a fixed point
		expect(b.preview).toBe(a.preview);
		expect(b.previewSha256).toBe(a.previewSha256);
		expect(b.submissionDigest).toBe(a.submissionDigest);
		expect(b.card).toEqual(a.card);
		expect(
			confirmIssue(a, { confirmed: true, confirmedAt: "2026-11-13T10:00:00+08:00", previewSha256: a.previewSha256 }),
		).not.toBeNull();
		expect(
			confirmIssue(a, { confirmed: true, confirmedAt: "2026-11-13T10:00:00+08:00", previewSha256: "0".repeat(64) }),
		).toBeNull();

		// Control escapes are NOT counted as credential hits (draft has no secrets).
		expect(a.redactions).toBe(0);
		expect(a.notes.some((note) => note.includes("可见转义"))).toBe(true);
	});

	it("redactSecrets credential replacement/count unchanged; control escaping is a separate layer", () => {
		const cred = `token=SUPERSECRETVALUE123 ${ESC}[8mX${ESC}[0m`;
		const clean = redactSecrets(cred, []);
		expect(clean.text).toContain("[REDACTED]");
		expect(clean.redactions).toBeGreaterThan(0);
		const escaped = escapeUntrustedText(clean.text);
		expect(hasUnsafeControls(escaped)).toBe(false);
		expect(escaped).toContain("[REDACTED]"); // redaction preserved through escape
		expect(escaped).toContain(`${P}001B${S}`); // control neutralized separately
	});
});
