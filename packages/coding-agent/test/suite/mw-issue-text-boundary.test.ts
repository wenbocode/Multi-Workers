/**
 * mw-issue-text-boundary.test.ts — T-09C1 independent regression.
 *
 * This suite imports NO old suite. It separates RAW ingress from CANONICAL
 * render/replay: a non-identity pure string function cannot be both globally
 * injective and idempotent, so `escapeUntrustedText` remains the canonical
 * fixed point while the raw boundary is selected explicitly by `textMode`.
 * Production must not infer source by matching token text, use a cache, or
 * depend on time/randomness.
 *
 * Real evidence: registered /mw handler + real bind + real temp IssueStore +
 * real full-text overlay compositor + real @xterm/headless cell scans. This is
 * an offline fixture, NOT proof of an installed/running MW deployment.
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
	appendDevUpdate,
	appendReporterReply,
	canonicalPayload,
	confirmIssue,
	type DevUpdate,
	type IssueCard,
	type IssueDraft,
	NOT_VERIFIED_PHRASE,
	type PrepareOptions,
	prepareIssue,
	REDACTION_MARK,
	type ReporterReply,
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
	escapeUntrustedText,
	hasUnsafeControls,
	ISSUE_CONTROL_ESCAPE_PREFIX,
	ISSUE_CONTROL_ESCAPE_SUFFIX,
	neutralizeControlText,
} from "../../src/extensions/agent-team-loop/shared/issue-text.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

type TextBoundaryMode = "raw" | "canonical";
interface BoundaryPrepareOptions extends PrepareOptions {
	readonly textMode?: TextBoundaryMode;
}

const P = ISSUE_CONTROL_ESCAPE_PREFIX;
const S = ISSUE_CONTROL_ESCAPE_SUFFIX;
const LIT_OPEN = "[[LIT:U+005B]]";
const ESC = "\x1b";
const BEL = "\x07";
const RLO = "\u202e";
const PDF = "\u202c";
const CSI8 = "\u009b";
const ZWJ = "\u200d";
const ZWNJ = "\u200c";
const TOKEN_ESC = `${P}001B${S}`;
const NESTED = `[[CTL:U+[[CTL:U+001B]]]]`;
const RULE_LITERAL = `[[LIT:U+005B]] and [[LIT:U+005B]][[LIT:U+005B]]LIT:U+005B]]`;
const NORMAL_UNICODE = `中文👨${ZWJ}👩${ZWJ}👧${ZWJ}👦 क्${ZWJ}ष क्${ZWNJ}ष می${ZWNJ}روم e\u0301\n第二行 CJK`;
const RAW_UNSAFE =
	/[\u0000-\u0009\u000b-\u001f\u007f-\u009f\u00ad\u061c\u180e\u200b\u200e\u200f\u2028-\u202e\u2060-\u206f\ufeff]/;

function controlToken(cp: number): string {
	return `${P}${cp.toString(16).toUpperCase().padStart(4, "0")}${S}`;
}

function unsafeInNewOracle(cp: number): boolean {
	if (cp === 0x000a || cp === 0x200c || cp === 0x200d) return false;
	if (cp <= 0x001f || (cp >= 0x007f && cp <= 0x009f)) return true;
	if (cp === 0x200b || cp === 0x200e || cp === 0x200f) return true;
	if ((cp >= 0x2028 && cp <= 0x202e) || (cp >= 0x2060 && cp <= 0x206f)) return true;
	return cp === 0x00ad || cp === 0x061c || cp === 0x180e || cp === 0xfeff;
}

function encodeRawCore(text: string): string {
	let out = "";
	for (let i = 0; i < text.length; i += 1) {
		const cp = text.charCodeAt(i);
		if (cp === 0x005b) out += LIT_OPEN;
		else if (unsafeInNewOracle(cp)) out += controlToken(cp);
		else out += text[i];
	}
	return out;
}

/** Independent oracle for the declared raw-entry rule. `[REDACTED]` is the
 * one explicit canonical fixed-point literal inserted after raw redaction. */
function encodeRawOracle(text: string): string {
	return encodeRawCore(text).replaceAll(encodeRawCore(REDACTION_MARK), REDACTION_MARK);
}

/** Independent decoder: proves visible canonical text maps back to the exact
 * post-redaction raw field, including generated control tokens and every
 * literal `[`/delimiter. It never guesses a source from a token; it verifies
 * the declared canonical grammar. */
function decodeCanonicalOracle(text: string): string {
	let out = "";
	let i = 0;
	while (i < text.length) {
		if (text.startsWith(LIT_OPEN, i)) {
			out += "[";
			i += LIT_OPEN.length;
			continue;
		}
		if (text.startsWith(P, i)) {
			const end = text.indexOf(S, i + P.length);
			if (end > 0) {
				const hex = text.slice(i + P.length, end);
				if (/^[0-9A-F]{4,6}$/.test(hex)) {
					const cp = Number.parseInt(hex, 16);
					if (unsafeInNewOracle(cp) && text.slice(i, end + S.length) === controlToken(cp)) {
						out += String.fromCharCode(cp);
						i = end + S.length;
						continue;
					}
				}
			}
		}
		out += text[i];
		i += 1;
	}
	return out;
}

function sha(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

function stableStringify(value: unknown): string {
	if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
	if (Array.isArray(value)) return `[${value.map((item) => stableStringify(item)).join(",")}]`;
	const obj = value as Record<string, unknown>;
	return `{${Object.keys(obj)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${stableStringify(obj[key])}`)
		.join(",")}}`;
}

// ── Pure model boundary ─────────────────────────────────────────────────────

const MODEL_OPTIONS: BoundaryPrepareOptions = {
	submittedAt: "2026-11-13T09:00:00+08:00",
	environmentObservedAt: "2026-11-13T09:00:00+08:00",
	knownSecrets: [],
	textMode: "raw",
};
const CANONICAL_OPTIONS: BoundaryPrepareOptions = { ...MODEL_OPTIONS, textMode: "canonical" };

function draftWith(actual: string): IssueDraft {
	const unknown = unknownObservation();
	return {
		id: "fb-0123456789abcdef0123456789abcdef",
		title: "边界回归标题",
		projectLabel: "project-a",
		component: unknown,
		occurredAt: userObservation("2026-11-13T08:12:00+08:00", "2026-11-13T09:00:00+08:00"),
		trigger: unknown,
		precondition: userObservation(NORMAL_UNICODE),
		expected: unknown,
		actual: userObservation(actual),
		impact: unknown,
		reproductionSteps: userObservation("1. a\n2. b\n3. c"),
		reproductionFrequency: "偶发",
		errorExcerpt: unknown,
		environmentAtFailure: { mwVersion: unknown, piVersion: unknown, platform: unknown, windowType: unknown },
		observedEnvironment: {
			mwVersion: unknown,
			piVersion: unknown,
			platform: unknown,
			windowType: unknown,
			bundleStatus: unknown,
			serveStatus: unknown,
		},
		diagnosticCandidates: [],
		selectedFragmentIds: [],
	};
}

function devUpdate(statusNote: string): DevUpdate {
	return {
		at: "2026-11-13T09:01:00+08:00",
		by: "dev-pm",
		status: "修复中",
		statusNote,
		nextAction: null,
		fixCommit: null,
		releaseVersion: null,
		questionToReporter: null,
	};
}

function reporterReply(text: string): ReporterReply {
	return { at: "2026-11-13T09:02:00+08:00", text, source: "user", inReplyTo: null };
}

describe("T-09C1 pure model: raw ingress vs canonical fixed point", () => {
	it("preserves normal Unicode, maps mixed sources visibly, and keeps the canonical fixed point", () => {
		const raw =
			`A${ESC}[8mCONCEAL${ESC}[0m${BEL}${CSI8}2J${RLO}BIDI${PDF} ` +
			`${NORMAL_UNICODE} LITERAL:${TOKEN_ESC} NESTED:${NESTED} RULE:${RULE_LITERAL}\t\r`;
		const encoded = encodeRawOracle(raw);
		const prep = prepareIssue(draftWith(raw), MODEL_OPTIONS);

		expect(escapeUntrustedText(NORMAL_UNICODE), "ZWJ/ZWNJ/CJK/combining/LF preserved by canonical helper").toBe(
			NORMAL_UNICODE,
		);
		expect(hasUnsafeControls(NORMAL_UNICODE)).toBe(false);
		expect(prep.card.scene.actual.value).toBe(encoded);
		expect(prep.preview).toContain(encoded);
		const serializedCard = canonicalPayload(prep.card);
		expect((JSON.parse(serializedCard) as IssueCard).scene.actual.value).toBe(encoded);
		expect(serializedCard).toContain(JSON.stringify(encoded).slice(1, -1));
		expect(decodeCanonicalOracle(prep.card.scene.actual.value ?? "")).toBe(raw);
		expect(prep.preview).toContain(NORMAL_UNICODE);
		expect(RAW_UNSAFE.test(prep.preview), "no unsafe control reaches confirmed text").toBe(false);
		expect(renderPreview(prep.card)).toBe(prep.preview);
		expect(escapeUntrustedText(prep.preview)).toBe(prep.preview);
		expect(renderPreview(prep.card)).toBe(renderPreview(prep.card));
		expect(
			confirmIssue(prep, {
				confirmed: true,
				confirmedAt: "2026-11-13T10:00:00+08:00",
				previewSha256: prep.previewSha256,
			}),
		).not.toBeNull();
	});

	it("distinguishes real ESC, literal token, mixed/repeated/nested pseudo-tokens and delimiter-rule literals", () => {
		const cases = [
			ESC,
			TOKEN_ESC,
			`${TOKEN_ESC}${TOKEN_ESC}`,
			NESTED,
			RULE_LITERAL,
			`${ESC}${TOKEN_ESC}${NESTED}${RULE_LITERAL}${LIT_OPEN}`,
		];
		const preps = cases.map((value) => prepareIssue(draftWith(value), MODEL_OPTIONS));
		const canonicalValues = preps.map((prep) => prep.card.scene.actual.value ?? "");
		expect(new Set(canonicalValues).size, "no raw source collision in card payload").toBe(cases.length);
		expect(new Set(preps.map((prep) => prep.preview)).size).toBe(cases.length);
		expect(new Set(preps.map((prep) => prep.submissionDigest)).size).toBe(cases.length);
		expect(new Set(preps.map((prep) => canonicalPayload(prep.card))).size).toBe(cases.length);
		for (let i = 0; i < cases.length; i += 1) {
			expect(canonicalValues[i]).toBe(encodeRawOracle(cases[i]));
			expect(decodeCanonicalOracle(canonicalValues[i]), `case ${i} maps back to raw source`).toBe(cases[i]);
			expect(RAW_UNSAFE.test(preps[i].preview)).toBe(false);
		}
		expect(canonicalValues[0]).toBe(TOKEN_ESC);
		expect(canonicalValues[1]).toBe(`${LIT_OPEN}${LIT_OPEN}CTL:U+001B]]`);
		expect(preps[0].previewSha256).not.toBe(preps[1].previewSha256);
		expect(preps[0].submissionDigest).not.toBe(preps[1].submissionDigest);
		expect(canonicalPayload(preps[0].card)).not.toBe(canonicalPayload(preps[1].card));
	});

	it("canonical mode is a replay/render boundary; old helper f(f(x)) remains true without impossible claims", () => {
		const raw = `MIX${ESC}${TOKEN_ESC}${NESTED}${RLO}${PDF}${NORMAL_UNICODE}`;
		const canonical = encodeRawOracle(raw);
		const once = prepareIssue(draftWith(canonical), CANONICAL_OPTIONS);
		const twice = prepareIssue(draftWith(once.card.scene.actual.value ?? ""), CANONICAL_OPTIONS);
		expect(once.card.scene.actual.value).toBe(canonical);
		expect(twice.card.scene.actual.value).toBe(canonical);
		expect(twice.preview).toBe(once.preview);
		expect(twice.previewSha256).toBe(once.previewSha256);
		expect(escapeUntrustedText(once.preview)).toBe(once.preview);
		expect(renderPreview(once.card)).toBe(once.preview);

		const helperOnce = escapeUntrustedText(`X${ESC}[8mHIDE${ESC}[0m\tY\nZ`);
		expect(escapeUntrustedText(helperOnce), "old f(f(x)) assertion is preserved").toBe(helperOnce);
		expect(neutralizeControlText(`x${ESC}${BEL}${RLO}y`).count).toBe(3);
		expect(escapeUntrustedText("\u200b")).toBe(`${P}200B${S}`);
		expect(escapeUntrustedText(ZWJ)).toBe(ZWJ);
		expect(escapeUntrustedText(ZWNJ)).toBe(ZWNJ);
		expect(escapeUntrustedText("\n")).toBe("\n");
		expect(decodeCanonicalOracle(canonical)).toBe(raw);
	});

	it("redacts raw known-secret leaves/keys before representation; append raw/canonical modes are explicit", () => {
		const known = "literal[secret]value";
		const raw = `field=${known}${ESC}${TOKEN_ESC}`;
		const baseline = redactSecrets(raw, [known]);
		const prep = prepareIssue(draftWith(raw), { ...MODEL_OPTIONS, knownSecrets: [known] });
		const canonicalField = prep.card.scene.actual.value ?? "";
		expect(baseline.redactions).toBe(1);
		expect(prep.redactions).toBeGreaterThanOrEqual(1);
		expect(canonicalPayload(prep.card)).not.toContain(known);
		expect(prep.preview).toContain(REDACTION_MARK);
		expect(decodeCanonicalOracle(canonicalField)).toBe(baseline.text);

		const baseCard = prepareIssue(draftWith("BASE"), CANONICAL_OPTIONS).card;
		const rawAppend = `UPDATE${ESC}${TOKEN_ESC}${NORMAL_UNICODE}`;
		const encodedAppend = encodeRawOracle(rawAppend);
		const appended = appendDevUpdate(baseCard, devUpdate(rawAppend));
		expect(appended.devTimeline[0]?.statusNote).toBe(encodedAppend);
		const replayed = appendDevUpdate(baseCard, devUpdate(encodedAppend), [], "canonical");
		expect(replayed.devTimeline[0]?.statusNote).toBe(encodedAppend);

		const rawReply = `REPLY${ESC}${TOKEN_ESC}${NORMAL_UNICODE}`;
		const encodedReply = encodeRawOracle(rawReply);
		const replied = appendReporterReply(baseCard, reporterReply(rawReply));
		expect(replied.reporterReplies[0]?.text).toBe(encodedReply);
		const replayedReply = appendReporterReply(baseCard, reporterReply(encodedReply), [], "canonical");
		expect(replayedReply.reporterReplies[0]?.text).toBe(encodedReply);
	});
});

// ── Real xterm cells ────────────────────────────────────────────────────────

interface CellLike {
	getChars(): string;
	isInvisible(): number;
}
interface LineLike {
	translateToString(trimRight?: boolean): string;
	getCell(x: number): CellLike | undefined;
}
interface BufferLike {
	active: {
		length: number;
		viewportY: number;
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

async function scanAllCells(lines: readonly string[], cols: number): Promise<CellScan> {
	const rows = Math.max(lines.length + 2, 4);
	const xt = new XtermTerminalCtor({ cols, rows, allowProposedApi: true, disableStdin: true });
	await new Promise<void>((resolve) => xt.write(lines.join("\r\n"), () => resolve()));
	const buf = xt.buffer.active;
	let all = "";
	let visible = "";
	let invisible = "";
	let invisibleCount = 0;
	for (let y = 0; y < buf.length; y += 1) {
		const line = buf.getLine(y);
		if (!line) continue;
		for (let x = 0; x < cols; x += 1) {
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
	for (let i = 0; i < rows; i += 1) {
		const line = buf.getLine(buf.viewportY + i);
		viewport += line ? line.translateToString(true) : "";
	}
	return { all, visible, invisible, invisibleCount, viewport };
}

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

class OverlayProbeTui extends TuiMainScreen {
	composed(width: number, height: number): string[] {
		return this.compositeOverlays([], width, height);
	}
}

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

class ThrowingConfirmUI extends XtermCellUI {
	async confirm(): Promise<boolean> {
		throw new Error("simulated dialog failure");
	}
}

function aggregate(scans: readonly CellScan[]): CellScan {
	const out: CellScan = { all: "", visible: "", invisible: "", invisibleCount: 0, viewport: "" };
	for (const scan of scans) {
		out.all += scan.all;
		out.visible += scan.visible;
		out.invisible += scan.invisible;
		out.invisibleCount += scan.invisibleCount;
		out.viewport += scan.viewport;
	}
	return out;
}

function assertSafeCells(ui: XtermCellUI, label: string, sentinels: readonly string[], heads: readonly string[]): void {
	const cells = aggregate(ui.cellScans);
	for (const sentinel of sentinels) {
		expect(cells.visible, `${label}: ${sentinel} must be in VISIBLE xterm cells`).toContain(sentinel);
		expect(cells.invisible, `${label}: ${sentinel} must NEVER be concealed`).not.toContain(sentinel);
		expect(cells.all, `${label}: ${sentinel} must not be erased`).toContain(sentinel);
	}
	for (const head of heads) {
		expect(cells.visible, `${label}: head ${head} was erased/moved away`).toContain(head);
	}
	for (const text of ui.capturedTexts) {
		expect(RAW_UNSAFE.test(text), `${label}: raw unsafe control leaked into user-facing text`).toBe(false);
		expect(text, `${label}: normal Unicode must survive`).toContain(NORMAL_UNICODE);
	}
	const joined = ui.capturedTexts.join("\n");
	expect(joined.split("\n").length, `${label}: LF structure preserved`).toBeGreaterThan(3);
	expect(
		ui.confirms.some((entry) => ui.customs.some((custom) => custom.fullText === entry.message)),
		`${label}: confirm must use the exact full preview text`,
	).toBe(true);
	process.stdout.write(
		`[VERIFY] ${label}: texts=${ui.capturedTexts.length} scans=${ui.cellScans.length} ` +
			`invisibleCells=${cells.invisibleCount} visibleSentinels=${sentinels.length}\n`,
	);
}

// ── Registered /mw + real bind + temp store ─────────────────────────────────

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
	const top = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-boundary-")));
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

function fakeCtx(ui: XtermCellUI, projectDir: string): ExtensionCommandContext {
	return {
		mode: ui.mode,
		hasUI: ui.hasUI,
		cwd: projectDir,
		ui,
	} as unknown as ExtensionCommandContext;
}

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

async function bindViaWindow(fx: Fixture, clock: () => string): Promise<void> {
	const mw = makeMw(fx.devRoot, fx, storeFor(fx.devRoot, fx), clock);
	const ui = new XtermCellUI(100, 30);
	ui.confirmAnswers.push(true);
	await mw.handler("issue bind", fakeCtx(ui, fx.devRoot));
	if (!fs.existsSync(fx.pointerFile)) throw new Error("fixture /mw issue bind failed");
}

const ATTACK_TITLE = `TITLE-HEAD${ESC}[8mCONCEAL-SENTINEL${ESC}[0m`;
const ERASE = `TRIGGER-HEAD${ESC}[2KERASE-SENTINEL`;
const CURSOR = `EXPECTED-HEAD${ESC}[5DCURSOR-SENTINEL`;
const OSC = `ACTUAL-HEAD${ESC}]0;pwned${BEL}OSC-SENTINEL`;
const BIDI = `IMPACT-HEAD${RLO}BIDI-SENTINEL${PDF}`;
const CSI_ERASE = `ERROR-HEAD${CSI8}2JCSI-SENTINEL`;
const TABCR = `STEPS-HEAD\tTAB-SENTINEL\rCR-SENTINEL`;
const RAW_ACTUAL =
	`${OSC} ${CURSOR} ${BIDI} ${CSI_ERASE} ${NORMAL_UNICODE} ` +
	`LITERAL-SOURCE:${TOKEN_ESC} NESTED-SOURCE:${NESTED} RULE-SOURCE:${RULE_LITERAL}`;
const DIAGNOSTIC = `DIAG-HEAD ${TOKEN_ESC} ${NESTED} ${RULE_LITERAL}${NORMAL_UNICODE}`;
const REPORT_SENTINELS = [
	"CONCEAL-SENTINEL",
	"ERASE-SENTINEL",
	"CURSOR-SENTINEL",
	"OSC-SENTINEL",
	"BIDI-SENTINEL",
	"CSI-SENTINEL",
	"TAB-SENTINEL",
	"CR-SENTINEL",
	"LITERAL-SOURCE",
	"NESTED-SOURCE",
	"RULE-SOURCE",
] as const;
const REPORT_HEADS = [
	"TITLE-HEAD",
	"TRIGGER-HEAD",
	"EXPECTED-HEAD",
	"ACTUAL-HEAD",
	"IMPACT-HEAD",
	"STEPS-HEAD",
] as const;

function reportArgs(): string {
	const values: ReadonlyArray<readonly [string, string]> = [
		["title", ATTACK_TITLE],
		["component", "/mw status"],
		["occurredAt", "2026-11-13T08:12:00+08:00"],
		["trigger", ERASE],
		["precondition", NORMAL_UNICODE],
		["expected", CURSOR],
		["actual", RAW_ACTUAL],
		["impact", BIDI],
		["steps", `${TABCR}\n1. a\n2. b\n3. c`],
		["frequency", "偶发"],
		["error", CSI_ERASE],
		["mwVersion", "0.8.1"],
		["piVersion", "0.12.2"],
		["platform", "Windows 11"],
		["windowType", "pi TUI"],
		["diagnostic", DIAGNOSTIC],
		["diagnosticKind", "log"],
		["candidate", "UNSELECTED-CANDIDATE"],
	];
	return ["issue", "report", ...values.map(([key, value]) => field(key, value))].join(" ");
}

function updateArgs(id: string, question: string, statusNote: string): string {
	const values: ReadonlyArray<readonly [string, string]> = [
		["status", "修复中"],
		["statusNote", statusNote],
		["nextAction", `NEXT${ESC}${TOKEN_ESC}${NORMAL_UNICODE}`],
		["fixCommit", "abc1234"],
		["releaseVersion", "0.12.5"],
		["question", question],
	];
	return ["issue", "update", id, ...values.map(([key, value]) => field(key, value))].join(" ");
}

function replyArgs(id: string, text: string, inReplyTo: string): string {
	return ["issue", "reply", id, field("text", text), field("inReplyTo", inReplyTo)].join(" ");
}

function localId(projectRoot: string): string {
	const file = issueLocalIndexPath(projectRoot);
	const index = JSON.parse(fs.readFileSync(file, "utf8")) as { records: Array<{ id: string }> };
	if (index.records.length !== 1) throw new Error(`expected 1 local record, got ${index.records.length}`);
	return index.records[0].id;
}

function authorityRawLines(fx: Fixture, id: string): string[] {
	const file = issueAuthorityLogPath(fx.devRoot, id);
	if (!fs.existsSync(file)) return [];
	const raw = fs.readFileSync(file, "utf8");
	return raw.split("\n").filter((line) => line !== "");
}

function authorityEvents(fx: Fixture, id: string): Array<Record<string, unknown>> {
	return authorityRawLines(fx, id).map((line) => JSON.parse(line) as Record<string, unknown>);
}

function authorityLogCount(fx: Fixture): number {
	const dir = path.join(issueAuthorityBasePath(fx.devRoot), ISSUE_EVENTS_DIR_BASENAME);
	if (!fs.existsSync(dir)) return 0;
	return fs.readdirSync(dir).filter((name) => name.endsWith(".jsonl")).length;
}

function eventCard(event: Record<string, unknown>): IssueCard {
	if (typeof event.card !== "object" || event.card === null) throw new Error("created event has no card");
	return event.card as IssueCard;
}

function eventQuestion(event: Record<string, unknown>): string | null {
	const update = event.update;
	if (typeof update !== "object" || update === null) return null;
	const question = (update as Record<string, unknown>).questionToReporter;
	return typeof question === "string" ? question : null;
}

function verifyChain(events: ReadonlyArray<Record<string, unknown>>): void {
	const genesis = "0".repeat(64);
	let previous = genesis;
	for (let i = 0; i < events.length; i += 1) {
		const event = events[i];
		expect(event.seq, `event ${i + 1} seq`).toBe(i + 1);
		expect(event.prev_sha256, `event ${i + 1} prev_sha256`).toBe(previous);
		const withoutHash = { ...event };
		delete withoutHash.sha256;
		expect(sha(`${String(event.prev_sha256)}\n${stableStringify(withoutHash)}`), `event ${i + 1} sha256`).toBe(
			event.sha256,
		);
		previous = String(event.sha256);
	}
	const first = events[0];
	for (const event of events) {
		expect(event.submission_digest).toBe(first.submission_digest);
		expect(event.project_label).toBe(first.project_label);
	}
}

function projectActor(projectRoot: string): {
	role: "pm";
	scope: "project";
	projectRoot: string;
	projectLabel: string;
	by: string;
	trustedWindow: boolean;
	writeAuthorized: boolean;
} {
	return {
		role: "pm",
		scope: "project",
		projectRoot,
		projectLabel: path.basename(projectRoot),
		by: "boundary-test-pm",
		trustedWindow: true,
		writeAuthorized: true,
	};
}

describe("T-09C1 registered /mw report: exact preview, payload, hash and real xterm cells", () => {
	it("normal Unicode plus control attacks keep visible cells and distinguishable canonical sources", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = makeMw(fx.projectA, fx, storeFor(fx.projectA, fx), clock);
		const ui = new XtermCellUI(100, 30);
		ui.confirmAnswers.push(true);
		await a.handler(reportArgs(), fakeCtx(ui, fx.projectA));

		assertSafeCells(ui, "report 100x30", REPORT_SENTINELS, REPORT_HEADS);
		const id = localId(fx.projectA);
		const events = authorityEvents(fx, id);
		expect(events).toHaveLength(1);
		const created = events[0];
		const card = eventCard(created);
		const preview = ui.customs[0]?.fullText ?? "";
		const confirmed = ui.confirms[0]?.message ?? "";
		const encodedActual = encodeRawOracle(RAW_ACTUAL);
		const encodedLiteral = encodeRawOracle(TOKEN_ESC);

		expect(confirmed).toBe(preview);
		expect(created.preview_sha256).toBe(sha(preview));
		expect(created.preview_sha256).toBe(sha(renderPreview(card)));
		expect(created.card_sha256).toBe(sha(canonicalPayload(card)));
		expect(created.submission_digest).toBe(sha(canonicalPayload(card)).slice(0, 16));
		expect(card.scene.actual.value).toBe(encodedActual);
		expect(decodeCanonicalOracle(card.scene.actual.value ?? "")).toBe(RAW_ACTUAL);
		expect(preview).toContain(encodedActual);
		expect(preview).toContain(encodedLiteral);
		expect(preview).toContain(TOKEN_ESC);
		expect(preview).toContain(NORMAL_UNICODE);
		expect(preview).not.toContain(encodeRawOracle(encodedLiteral));
		expect(RAW_UNSAFE.test(preview)).toBe(false);
		expect(RAW_UNSAFE.test(canonicalPayload(card))).toBe(false);
		expect(authorityRawLines(fx, id)[0]).toContain(encodedLiteral);
		verifyChain(events);
	});

	it("cancel, non-boolean true and dialog exception leave zero authority/local writes", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = makeMw(fx.projectA, fx, storeFor(fx.projectA, fx), clock);
		const answers: unknown[] = [false, "true"];
		for (const answer of answers) {
			const ui = new XtermCellUI(100, 30);
			ui.confirmAnswers.push(answer);
			await a.handler(reportArgs(), fakeCtx(ui, fx.projectA));
		}
		const thrown = new ThrowingConfirmUI(100, 30);
		await a.handler(reportArgs(), fakeCtx(thrown, fx.projectA));
		expect(authorityLogCount(fx)).toBe(0);
		expect(fs.existsSync(issueLocalIndexPath(fx.projectA))).toBe(false);
	});
});

describe("T-09C1 update/reply/status/inbox replay: no secondary drift, created bytes unchanged", () => {
	it("seq/hash chain, newest single question, full history and fail-closed local verdict", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const projectStore = storeFor(fx.projectA, fx);
		const a = makeMw(fx.projectA, fx, projectStore, clock);
		const setupUi = new XtermCellUI(100, 30);
		setupUi.confirmAnswers.push(true);
		await a.handler(reportArgs(), fakeCtx(setupUi, fx.projectA));
		const id = localId(fx.projectA);
		const createdLine = authorityRawLines(fx, id)[0];

		const ordinaryInbox = new XtermCellUI(100, 30);
		await a.handler(`issue inbox ${id}`, fakeCtx(ordinaryInbox, fx.projectA));
		expect(ordinaryInbox.capturedTexts.join("\n"), "ordinary project cannot use dev inbox").toContain("拒绝");

		const d = makeMw(fx.devRoot, fx, storeFor(fx.devRoot, fx), clock);
		const q1 = `Q1${ESC}${TOKEN_ESC}${NESTED}${NORMAL_UNICODE}`;
		const q2 = `Q2${ESC}${TOKEN_ESC}${RULE_LITERAL}${NORMAL_UNICODE}`;
		const encodedQ1 = encodeRawOracle(q1);
		const encodedQ2 = encodeRawOracle(q2);
		const note1 = `NOTE1${ESC}${TOKEN_ESC}${NORMAL_UNICODE}`;
		const note2 = `NOTE2${CSI8}${TOKEN_ESC}${NORMAL_UNICODE}`;
		const updateUi1 = new XtermCellUI(100, 30);
		updateUi1.confirmAnswers.push(true);
		await d.handler(updateArgs(id, q1, note1), fakeCtx(updateUi1, fx.devRoot));
		const updateUi2 = new XtermCellUI(100, 30);
		updateUi2.confirmAnswers.push(true);
		await d.handler(updateArgs(id, q2, note2), fakeCtx(updateUi2, fx.devRoot));

		const twoUpdateEvents = authorityEvents(fx, id);
		expect(twoUpdateEvents).toHaveLength(3);
		expect(eventQuestion(twoUpdateEvents[1])).toBe(encodedQ1);
		expect(eventQuestion(twoUpdateEvents[2])).toBe(encodedQ2);
		const q2Hash = String(twoUpdateEvents[2].sha256);

		const actor = projectActor(fx.projectA);
		const beforeReply = projectStore.status({ actor, id });
		expect(beforeReply.pendingQuestion, "newest single question wins").toBe(encodedQ2);
		expect(beforeReply.text).toContain(encodedQ1);
		expect(beforeReply.text).toContain(encodedQ2);
		expect(beforeReply.text).toContain(NOT_VERIFIED_PHRASE);
		expect(beforeReply.text).not.toContain(encodeRawOracle(encodedQ2));
		expect(RAW_UNSAFE.test(beforeReply.text)).toBe(false);

		const replyText = `REPLY${ESC}${TOKEN_ESC}${NESTED}${NORMAL_UNICODE}`;
		const encodedReply = encodeRawOracle(replyText);
		const replyUi = new XtermCellUI(100, 30);
		replyUi.confirmAnswers.push(true);
		await a.handler(replyArgs(id, replyText, q2Hash), fakeCtx(replyUi, fx.projectA));
		const afterReply = projectStore.status({ actor, id });
		expect(afterReply.pendingQuestion, "explicit reply to Q2 clears Q2 only").toBeNull();
		expect(afterReply.text).toContain(encodedReply);
		expect(afterReply.text).not.toContain(encodeRawOracle(encodedReply));
		expect(afterReply.text).toContain(NOT_VERIFIED_PHRASE);
		expect(RAW_UNSAFE.test(afterReply.text)).toBe(false);

		const statusUi = new XtermCellUI(100, 30);
		await a.handler(`issue status ${id}`, fakeCtx(statusUi, fx.projectA));
		const statusText = statusUi.customs.map((custom) => custom.fullText).join("\n");
		expect(statusText).toContain(encodedQ1);
		expect(statusText).toContain(encodedQ2);
		expect(statusText).toContain(encodedReply);
		expect(statusText).toContain(NOT_VERIFIED_PHRASE);
		expect(statusText).not.toContain(encodeRawOracle(encodedQ2));
		expect(RAW_UNSAFE.test(statusText)).toBe(false);

		const inboxUi = new XtermCellUI(100, 30);
		await d.handler(`issue inbox ${id}`, fakeCtx(inboxUi, fx.devRoot));
		const inboxText = inboxUi.customs.map((custom) => custom.fullText).join("\n");
		expect(inboxText).toContain(encodedQ1);
		expect(inboxText).toContain(encodedQ2);
		expect(inboxText).toContain(encodedReply);
		expect(inboxText).toContain("追问历史");
		expect(inboxText).toContain("未回复");
		expect(inboxText).toContain("已回复");
		expect(inboxText).not.toContain(encodeRawOracle(encodedQ1));
		expect(RAW_UNSAFE.test(inboxText)).toBe(false);

		const finalEvents = authorityEvents(fx, id);
		expect(finalEvents).toHaveLength(4);
		expect(authorityRawLines(fx, id)[0], "created bytes unchanged by appended events").toBe(createdLine);
		verifyChain(finalEvents);
		const finalCreated = eventCard(finalEvents[0]);
		expect(finalEvents[0].card_sha256).toBe(sha(canonicalPayload(finalCreated)));
		expect(finalEvents[0].preview_sha256).toBe(sha(renderPreview(finalCreated)));
		expect(decodeCanonicalOracle(finalCreated.scene.actual.value ?? "")).toBe(RAW_ACTUAL);
		expect(decodeCanonicalOracle(encodedQ1)).toBe(q1);
		expect(decodeCanonicalOracle(encodedReply)).toBe(replyText);
	});
});
