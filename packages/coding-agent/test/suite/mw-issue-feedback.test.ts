/**
 * mw-issue-feedback.test.ts — T-06 independent two-project L2 acceptance for
 * key `mw-issue-feedback` (VC-001..VC-007, plus the two extra checks ordered by
 * the card: effective terminal-overlay clipping and the dev window's incoming
 * card read/triage flow).
 *
 * Independence rules (this suite is NOT a copy of the author's T-05 suite):
 *  - Every positive flow goes through the ACTUAL registered `/mw` handler
 *    (registerMwCommands -> "mw" -> runMwIssueCommand -> frozen T-04 module)
 *    with a REAL IssueStore over temporary, isolated fixtures: one MW dev repo,
 *    two same-machine ordinary projects (A and B) and one explicit machine
 *    pointer. No NoCallStore/hand-made actor is used as the L2 proof.
 *  - The pointer is bound through the real `/mw issue bind` window entry; the
 *    authority log, pending copies, local indexes and pointer are all real
 *    files under a temp root. No real machine config, credentials, network,
 *    paid provider, bundle build, serve restart or install is touched.
 *  - Fault hooks (documented in evidence): deleting/restoring the pointer file
 *    for offline recovery, `IssueStoreHooks.afterAuthorityCommit` throwing once
 *    for a lost ACK, a hand-written ambiguous pointer, a tampered local index,
 *    a corrupted authority JSONL, and an injected env/store-root seam. All store
 *    reads/writes themselves are real; only these seams are simulated.
 *  - The viewport cases use the REAL TUI component (the actual preview overlay
 *    component created by presentIssueFullText), the real TuiMainScreen
 *    overlay compositor (maxHeight clamping) and an offline xterm headless
 *    terminal. `component.fullText` or an unclipped render array is never
 *    accepted as proof that tail text is readable.
 *
 * Frozen T-01..T-05 sources/tests are consumed, never modified. Failing
 * assertions are kept red on purpose: a product gap must be reported to the PM
 * rather than fixed by weakening an assertion or patching product code.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage } from "@earendil-works/pi-ai";
import {
	type Component,
	KeybindingsManager,
	type OverlayOptions,
	stripTerminalSequences,
	TuiMainScreen,
} from "@earendil-works/pi-tui";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { VirtualTerminal } from "../../../tui/test/virtual-terminal.ts";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import { KEYBINDINGS } from "../../src/core/keybindings.ts";
import type { IssueCommandStore } from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import {
	ISSUE_PREVIEW_VIEWPORT_LINES,
	registerMwCommands,
	runMwIssueCommand,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import {
	type LocalEvidence,
	NOT_VERIFIED_PHRASE,
	REDACTION_MARK,
	VERIFIED_PHRASE,
} from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	ISSUE_EVENTS_DIR_BASENAME,
	ISSUE_LOCAL_DIR_PARTS,
	ISSUE_PENDING_DIR_BASENAME,
	IssueStore,
	type IssueStoreOptions,
	issueAuthorityBasePath,
	issueAuthorityLogPath,
	issueLocalIndexPath,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, getAssistantTexts, type Harness } from "./harness.ts";

function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

// ── Deterministic synthetic data (offline, no credential/network reading) ────

const SECRET = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const UNCONFIRMED_FRAGMENT = "UNCONFIRMED-DIAGNOSTIC-FRAGMENT-7788";
const REPLY_TEXT = "REPLY-MARK 补充：重启发生在 08:10，日志片段已人工脱敏";
const QUESTION = "请补充 serve 重启的准确时间与窗口类型";

const REPORT_FIELDS: ReadonlyArray<readonly [string, string]> = [
	["title", "/mw status 重启后显示旧 serve"],
	["component", "/mw status"],
	["occurredAt", "2026-11-13T08:12:00+08:00"],
	["trigger", "TRIGGER-MARK 在项目A执行 /mw status"],
	["precondition", "PRECONDITION-MARK serve 曾重启"],
	["expected", "EXPECTED-MARK 显示当前 serve 状态"],
	["actual", "ACTUAL-MARK 显示旧 serve 状态"],
	["impact", `IMPACT-MARK 决策误判 ${"影响-".repeat(120)} END-OF-IMPACT`],
	["steps", `1. 运行 /mw status；2. 重启 serve；3. 再查询 ${"step-".repeat(200)} END-OF-REPRO-STEPS`],
	["frequency", "偶发"],
	["error", `ERROR serve-stale: ${"E".repeat(300)} Bearer ${SECRET} END-OF-KEY-ERROR`],
	["mwVersion", "0.8.1"],
	["piVersion", "0.12.2"],
	["platform", "Windows 11"],
	["windowType", "pi TUI"],
	["diagnostic", `DIAGNOSTIC-MARK 用户主动选择的日志片段 ${"diag-".repeat(80)} END-OF-DIAGNOSTIC`],
	["diagnosticKind", "log"],
	["candidate", UNCONFIRMED_FRAGMENT],
];

/** Minimal short field set for the smallest reproducible overlay-clipping case:
 * no long repeats, only a head marker and a tail marker. */
function minimalReportArgs(): string {
	const short: ReadonlyArray<readonly [string, string]> = [
		["title", "MINIMAL-HEAD"],
		["component", "/mw status"],
		["occurredAt", "2026-11-13T08:12:00+08:00"],
		["trigger", "MINIMAL-TRIGGER"],
		["precondition", "MINIMAL-PRECONDITION"],
		["expected", "MINIMAL-EXPECTED"],
		["actual", "MINIMAL-ACTUAL"],
		["impact", "MINIMAL-IMPACT"],
		["steps", "MINIMAL-STEPS"],
		["frequency", "未知"],
		["error", "MINIMAL-ERROR"],
		["mwVersion", "0.8.1"],
		["piVersion", "0.12.2"],
		["platform", "Windows 11"],
		["windowType", "pi TUI"],
		["diagnostic", ""],
		["diagnosticKind", "log"],
		["candidate", ""],
	];
	return ["issue", "report", ...short.map(([key, value]) => field(key, value))].join(" ");
}

/** ASCII labels keep the [VERIFY] evidence readable on Windows OEM consoles;
 * the assertions themselves use the exact Chinese source strings. */
const TAIL_MARKERS = [
	{ label: "END-OF-REPRO-STEPS", text: "END-OF-REPRO-STEPS" },
	{ label: "END-OF-KEY-ERROR", text: "END-OF-KEY-ERROR" },
	{ label: "END-OF-IMPACT", text: "END-OF-IMPACT" },
	{ label: "END-OF-DIAGNOSTIC", text: "END-OF-DIAGNOSTIC" },
	{ label: "PREVIEW_LAST_LINE", text: "说明:未知项均明示未知" },
	{ label: "OVERLAY_FOOTER", text: "完整脱敏预览，未截断" },
] as const;

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

function reportArgs(): string {
	return ["issue", "report", ...REPORT_FIELDS.map(([key, value]) => field(key, value))].join(" ");
}

function makeClock(): () => string {
	let tick = 0;
	const base = Date.parse("2026-11-13T09:00:00+08:00");
	return () => {
		const value = new Date(base + tick * 1000).toISOString();
		tick += 1;
		return value;
	};
}

// ── Temp fixtures: real dev repo + two projects + an isolated pointer ────────

const tmpRoots: string[] = [];
const harnesses: Harness[] = [];
let savedWorkerTask: string | undefined;

beforeEach(() => {
	savedWorkerTask = process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_TASK; // default = clean PM window env
});

afterEach(() => {
	if (savedWorkerTask === undefined) delete process.env.PI_WORKER_TASK;
	else process.env.PI_WORKER_TASK = savedWorkerTask;
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	for (const dir of tmpRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

interface Fixture {
	top: string;
	pointerFile: string;
	devRoot: string;
	secondDevRoot: string;
	projectA: string;
	projectB: string;
}

function makeDevRepo(root: string): void {
	fs.mkdirSync(path.join(root, "packages", "multi-workers"), { recursive: true });
	fs.writeFileSync(path.join(root, "packages", "multi-workers", "mw.py"), "# offline fixture\n", "utf8");
	fs.mkdirSync(path.join(root, "packages", "coding-agent", "src", "extensions", "agent-team-loop"), {
		recursive: true,
	});
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".agenticdoc", "goal.md"), "# Project Goal\n", "utf8");
}

function makeProject(root: string, label: string): void {
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".agenticdoc", "goal.md"), `# ${label} goal\n`, "utf8");
}

function fixture(): Fixture {
	const top = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-e2e-")));
	tmpRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	const secondDevRoot = path.join(top, "mw-dev-second");
	const projectA = path.join(top, "project-a");
	const projectB = path.join(top, "project-b");
	makeDevRepo(devRoot);
	makeDevRepo(secondDevRoot);
	makeProject(projectA, "project-a");
	makeProject(projectB, "project-b");
	return {
		top,
		pointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME),
		devRoot: fs.realpathSync(devRoot),
		secondDevRoot: fs.realpathSync(secondDevRoot),
		projectA: fs.realpathSync(projectA),
		projectB: fs.realpathSync(projectB),
	};
}

// ── Real-window UI seam ──────────────────────────────────────────────────────

interface PreviewComponentLike {
	fullText: string;
	readonly lineCount: number;
	render(width: number): string[];
	invalidate(): void;
	handleInput?(data: string): void;
}

interface CapturedCustom {
	options: unknown;
	component: PreviewComponentLike;
}

type PreviewFactory = (
	tui: unknown,
	theme: unknown,
	keybindings: unknown,
	done: (result: undefined) => void,
) => unknown | Promise<unknown>;

interface Notification {
	message: string;
	type?: "info" | "warning" | "error";
}

/** Minimal fake of the real ExtensionUIContext: `custom` invokes the REAL
 * production preview factory, so the component under test is the actual
 * scrollable FULL-text overlay component from presentIssueFullText. */
class FakeIssueUI {
	hasUI = true;
	mode = "tui";
	readonly notifications: Notification[] = [];
	readonly confirms: Array<{ title: string; message: string }> = [];
	readonly customs: CapturedCustom[] = [];
	readonly confirmAnswers: boolean[] = [];
	readonly doneResults: unknown[] = [];
	readonly matchedKeybindings: string[] = [];
	renderRequests = 0;
	confirmThrow?: Error;
	customThrow?: Error;

	notify(message: string, type?: "info" | "warning" | "error"): void {
		this.notifications.push({ message, type });
	}
	async confirm(title: string, message: string): Promise<boolean> {
		this.confirms.push({ title, message });
		if (this.confirmThrow) throw this.confirmThrow;
		return this.confirmAnswers.shift() ?? false;
	}
	async input(): Promise<string | undefined> {
		return "";
	}
	async editor(): Promise<string | undefined> {
		return "";
	}
	async select(): Promise<string | undefined> {
		return undefined;
	}
	async custom(factory: unknown, options?: unknown): Promise<void> {
		if (this.customThrow) throw this.customThrow;
		const fn = factory as PreviewFactory;
		const tui = {
			requestRender: () => {
				this.renderRequests += 1;
			},
		};
		const keybindings = {
			matches: (data: string, id: string): boolean => {
				this.matchedKeybindings.push(id);
				return data === id;
			},
		};
		const done = (result: undefined): void => {
			this.doneResults.push(result);
		};
		const component = (await fn(tui, undefined, keybindings, done)) as PreviewComponentLike;
		this.customs.push({ options, component });
	}
}

function fakeCtx(ui: object, projectDir: string): ExtensionCommandContext {
	return {
		mode: (ui as { mode: string }).mode,
		hasUI: (ui as { hasUI: boolean }).hasUI,
		cwd: projectDir,
		ui,
	} as unknown as ExtensionCommandContext;
}

interface MwCommand {
	handler: (args: string, ctx: ExtensionCommandContext) => Promise<void>;
	summaries: string[];
}

/** The REAL registered /mw command (fake pi captures registration + summary). */
function makeMw(projectDir: string, fx: Fixture, store: IssueCommandStore, clock: () => string): MwCommand {
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
	registerMwCommands(pi, projectDir, new WorkerStore(projectDir), {} as AckStore, { key: undefined }, projectDir, {
		store,
		pointerFile: fx.pointerFile,
		now: clock,
	});
	const handler = commands.get("mw");
	if (!handler) throw new Error("/mw command not registered");
	return { handler, summaries };
}

function storeFor(projectRoot: string, fx: Fixture, extra: Partial<IssueStoreOptions> = {}): IssueStore {
	return new IssueStore({ projectRoot, pointerFile: fx.pointerFile, env: {}, ...extra });
}

/** Real store + call recorder (methods delegate; nothing is faked). */
function counting(inner: IssueStore, calls: string[]): IssueCommandStore {
	return {
		submit: (request) => {
			calls.push("submit");
			return inner.submit(request);
		},
		retry: (request) => {
			calls.push("retry");
			return inner.retry(request);
		},
		status: (request) => {
			calls.push("status");
			return inner.status(request);
		},
		list: (request) => {
			calls.push("list");
			return inner.list(request);
		},
		appendProgress: (request) => {
			calls.push("appendProgress");
			return inner.appendProgress(request);
		},
		reply: (request) => {
			calls.push("reply");
			return inner.reply(request);
		},
		listIncoming: (request) => {
			calls.push("listIncoming");
			return inner.listIncoming(request);
		},
		readIncoming: (request) => {
			calls.push("readIncoming");
			return inner.readIncoming(request);
		},
	};
}

/** Fixture seam: the production wiring passes localEvidence=null (explicit
 * unknown). This wrapper injects an OLD local environment into a real status
 * read so AC-005 is exercised with an actually stale installed version. */
function withLocalEvidence(inner: IssueStore, evidence: LocalEvidence): IssueCommandStore {
	return {
		submit: (request) => inner.submit(request),
		retry: (request) => inner.retry(request),
		status: (request) => inner.status({ ...request, localEvidence: evidence }),
		list: (request) => inner.list(request),
		appendProgress: (request) => inner.appendProgress(request),
		reply: (request) => inner.reply(request),
		listIncoming: (request) => inner.listIncoming(request),
		readIncoming: (request) => inner.readIncoming(request),
	};
}

async function bindViaWindow(fx: Fixture, clock: () => string): Promise<string> {
	const mw = makeMw(fx.devRoot, fx, storeFor(fx.devRoot, fx), clock);
	const ui = new FakeIssueUI();
	ui.confirmAnswers.push(true);
	await mw.handler("issue bind", fakeCtx(ui, fx.devRoot));
	if (!fs.existsSync(fx.pointerFile)) throw new Error("fixture /mw issue bind failed");
	return fs.readFileSync(fx.pointerFile, "utf8");
}

interface DriveResult {
	full: string;
	notices: string;
}

async function drive(mw: MwCommand, ui: FakeIssueUI, projectRoot: string, args: string): Promise<DriveResult> {
	const fromCustom = ui.customs.length;
	const fromNotice = ui.notifications.length;
	await mw.handler(args, fakeCtx(ui, projectRoot));
	return {
		full: ui.customs
			.slice(fromCustom)
			.map((custom) => custom.component.fullText)
			.join("\n"),
		notices: ui.notifications
			.slice(fromNotice)
			.map((notification) => notification.message)
			.join("\n"),
	};
}

function confirm(ui: FakeIssueUI, answer = true): void {
	ui.confirmAnswers.push(answer);
}

// ── Real on-disk evidence readers (no store-internal state) ─────────────────

interface SceneFact {
	value: string | null;
	source: string;
}

interface CreatedCard {
	scene: {
		trigger: SceneFact;
		expected: SceneFact;
		actual: SceneFact;
		reproductionSteps: SceneFact;
		impact: SceneFact;
		errorExcerpt: SceneFact;
	};
	diagnostics: Array<{ text: string }>;
}

interface EventRow {
	kind: string;
	seq: number;
	sha256: string;
	card?: CreatedCard;
	update?: {
		status: string;
		questionToReporter: string | null;
		fixCommit: string | null;
		releaseVersion: string | null;
	};
	reply?: { text: string; inReplyTo: string | null };
}

interface IndexFile {
	records: Array<{ id: string; state: string; project_label: string; attempts: number }>;
}

function authorityEvents(fx: Fixture, id: string): EventRow[] {
	const file = issueAuthorityLogPath(fx.devRoot, id);
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.length > 0)
		.map((line) => JSON.parse(line) as EventRow);
}

function authorityBytes(fx: Fixture, id: string): string {
	return readBytes(issueAuthorityLogPath(fx.devRoot, id));
}

function authorityLogCount(fx: Fixture, devRoot: string = fx.devRoot): number {
	const dir = path.join(issueAuthorityBasePath(devRoot), ISSUE_EVENTS_DIR_BASENAME);
	if (!fs.existsSync(dir)) return 0;
	return fs.readdirSync(dir).filter((name) => name.endsWith(".jsonl")).length;
}

function localIndex(projectRoot: string): IndexFile {
	const file = issueLocalIndexPath(projectRoot);
	if (!fs.existsSync(file)) return { records: [] };
	return JSON.parse(fs.readFileSync(file, "utf8")) as IndexFile;
}

function indexBytes(projectRoot: string): string {
	return readBytes(issueLocalIndexPath(projectRoot));
}

function pendingCount(projectRoot: string): number {
	const dir = path.join(projectRoot, ...ISSUE_LOCAL_DIR_PARTS, ISSUE_PENDING_DIR_BASENAME);
	if (!fs.existsSync(dir)) return 0;
	return fs.readdirSync(dir).filter((name) => name.endsWith(".json")).length;
}

function readBytes(file: string): string {
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "<absent>";
}

function allFixtureText(fx: Fixture): string {
	const chunks: string[] = [];
	const walk = (dir: string): void => {
		if (!fs.existsSync(dir)) return;
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) walk(full);
			else chunks.push(fs.readFileSync(full, "utf8"));
		}
	};
	walk(path.join(fx.top, "machine-home"));
	walk(path.join(fx.top, "mw-dev"));
	walk(path.join(fx.top, "project-a"));
	walk(path.join(fx.top, "project-b"));
	return chunks.join("\n");
}

// ── Shared setup helpers ────────────────────────────────────────────────────

interface Setup {
	mw: MwCommand;
	ui: FakeIssueUI;
	store: IssueStore;
}

function setup(fx: Fixture, projectRoot: string, clock: () => string, extra: Partial<IssueStoreOptions> = {}): Setup {
	const store = storeFor(projectRoot, fx, extra);
	return { store, mw: makeMw(projectRoot, fx, store, clock), ui: new FakeIssueUI() };
}

async function report(setupValue: Setup, projectRoot: string): Promise<{ full: string; notices: string; id: string }> {
	confirm(setupValue.ui, true);
	const result = await drive(setupValue.mw, setupValue.ui, projectRoot, reportArgs());
	const rows = localIndex(projectRoot).records;
	if (rows.length !== 1) throw new Error(`expected exactly one local record, got ${rows.length}`);
	return { ...result, id: rows[0].id };
}

function updateArgs(id: string, fields: ReadonlyArray<readonly [string, string]>): string {
	return ["issue", "update", id, ...fields.map(([key, value]) => field(key, value))].join(" ");
}

// ── VC-001 — two projects, real /mw report, one authority card ───────────────

describe("VC-001 (AC-001) two same-machine projects through the registered /mw entry", () => {
	it("created=1 id=same scene=readable foreign=0 with real store writes in both projects", async () => {
		const fx = fixture();
		const clock = makeClock();
		const pointer = await bindViaWindow(fx, clock);
		expect(pointer).toContain("mw-dev");

		const a = setup(fx, fx.projectA, clock);
		const submitted = await report(a, fx.projectA);
		expect(submitted.id).toMatch(/^fb-[0-9a-f]{32}$/);
		expect(submitted.full).toContain("反馈 ID");
		expect(submitted.full).toContain("已提交");

		// REAL authority log: exactly one created event, by the same ID.
		const rows = authorityEvents(fx, submitted.id);
		expect(rows).toHaveLength(1);
		expect(rows.filter((row) => row.kind === "created")).toHaveLength(1);
		expect(authorityLogCount(fx)).toBe(1);
		expect(localIndex(fx.projectA).records[0].id).toBe(submitted.id);
		expect(rows[0].card?.scene.trigger.value).toContain("TRIGGER-MARK");
		expect(rows[0].card?.scene.trigger.source).toBe("user");
		expect(rows[0].card?.scene.expected.value).toContain("EXPECTED-MARK");
		expect(rows[0].card?.scene.actual.value).toContain("ACTUAL-MARK");
		expect(rows[0].card?.scene.reproductionSteps.value).toContain("END-OF-REPRO-STEPS");
		expect(rows[0].card?.scene.impact.value).toContain("END-OF-IMPACT");
		expect(rows[0].card?.scene.errorExcerpt.value).toContain(REDACTION_MARK);
		expect(rows[0].card?.scene.errorExcerpt.value).not.toContain(SECRET);
		expect(authorityBytes(fx, submitted.id)).not.toContain(UNCONFIRMED_FRAGMENT);

		// Project B submits its own card through its OWN real store / window.
		const b = setup(fx, fx.projectB, clock);
		const submittedB = await report(b, fx.projectB);
		expect(submittedB.id).not.toBe(submitted.id);
		expect(authorityLogCount(fx)).toBe(2);

		const listA = await drive(a.mw, a.ui, fx.projectA, "issue status");
		const listB = await drive(b.mw, b.ui, fx.projectB, "issue status");
		expect(listA.full).toContain(submitted.id);
		expect(listA.full).not.toContain(submittedB.id);
		expect(listB.full).toContain(submittedB.id);
		expect(listB.full).not.toContain(submitted.id);
		const foreign = await drive(b.mw, b.ui, fx.projectB, `issue status ${submitted.id}`);
		expect(foreign.full).toContain("当前项目未登记该反馈 ID");
		verify("VC-001: created=1 id=same scene=readable foreign=0 two-projects=real-store");
	});
});

// ── VC-002 — refusal, unconfirmed fragment and credential leakage ────────────

describe("VC-002 (AC-002) refusal and redaction through the real window entry", () => {
	it("created=0 leaked=0 when confirmation is refused; no pending/index/pointer delta", async () => {
		const fx = fixture();
		const clock = makeClock();
		const pointer = await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		confirm(a.ui, false); // explicit user refusal
		const refused = await drive(a.mw, a.ui, fx.projectA, reportArgs());

		expect(refused.full).toContain("未提交");
		expect(refused.full).toContain("共享端新增记录数为 0");
		expect(authorityLogCount(fx)).toBe(0);
		expect(pendingCount(fx.projectA)).toBe(0);
		expect(localIndex(fx.projectA).records).toHaveLength(0);
		expect(readBytes(fx.pointerFile)).toBe(pointer);
		expect(allFixtureText(fx)).not.toContain(UNCONFIRMED_FRAGMENT);
		expect(allFixtureText(fx)).not.toContain(SECRET);
		// The FULL preview survived in the unconfirmed overlay, but nothing was persisted.
		expect(refused.full).toContain("END-OF-REPRO-STEPS");
		verify("VC-002: created=0 leaked=0 refused=1");
	});

	it("a confirmed report redacts credential shapes and never persists the unselected fragment", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const submitted = await report(a, fx.projectA);
		// The exact token appears in the FULL preview only as a redaction (or not at all):
		// neither the preview nor the persisted authority/local files contain it.
		expect(submitted.full).not.toContain(SECRET);
		expect(submitted.full).toContain(REDACTION_MARK);
		const persisted = `${authorityBytes(fx, submitted.id)}${indexBytes(fx.projectA)}`;
		expect(persisted).not.toContain(SECRET);
		expect(persisted).not.toContain(UNCONFIRMED_FRAGMENT);
		expect(authorityBytes(fx, submitted.id)).toContain(REDACTION_MARK);
		verify("VC-002: confirmed report stored no credential/unconfirmed fragment");
	});
});

// ── VC-003 — offline, lost ACK, repeated same-ID retries ────────────────────

describe("VC-003 (AC-003) offline recovery, lost receipt and idempotence", () => {
	it("pending=1 submitted=0 offline; two retries incl. ACK loss leave created=1", async () => {
		const fx = fixture();
		const clock = makeClock();
		const pointer = await bindViaWindow(fx, clock);
		// FAULT HOOK 1: real pointer file removed -> genuine authority unavailability.
		fs.rmSync(fx.pointerFile);

		let losses = 1;
		// FAULT HOOK 2: one thrown hook simulates a lost local ACK. All store
		// reads/writes (locks, JSONL append, local index) remain real.
		const a = setup(fx, fx.projectA, clock, {
			hooks: {
				afterAuthorityCommit: () => {
					if (losses > 0) {
						losses -= 1;
						throw new Error("SIMULATED_ACK_LOSS");
					}
				},
			},
		});
		confirm(a.ui, true);
		const offline = await drive(a.mw, a.ui, fx.projectA, reportArgs());
		const rows = localIndex(fx.projectA).records;
		expect(rows).toHaveLength(1);
		const id = rows[0].id;
		expect(rows[0].state).toBe("pending");
		expect(offline.full).toContain("未提交");
		expect(offline.full).not.toContain("已提交（权威记录已创建）");
		expect(pendingCount(fx.projectA)).toBe(1);
		expect(authorityLogCount(fx)).toBe(0);
		expect(offline.full).toContain("E-ISSUE-DEV-ROOT-NOT_CONFIGURED");

		// FAULT HOOK 1 recovery: restore the exact bound pointer bytes.
		fs.writeFileSync(fx.pointerFile, pointer, "utf8");
		const first = await drive(a.mw, a.ui, fx.projectA, `issue retry ${id}`);
		expect(first.full).toContain("待核实");
		expect(first.full).toContain("SIMULATED_ACK_LOSS");
		expect(authorityLogCount(fx)).toBe(1);
		expect(authorityEvents(fx, id)).toHaveLength(1);
		expect(localIndex(fx.projectA).records[0].state).toBe("in-flight");

		const second = await drive(a.mw, a.ui, fx.projectA, `issue retry ${id}`);
		expect(second.full).toContain("已提交");
		expect(second.full).toContain("权威未新增记录");
		const third = await drive(a.mw, a.ui, fx.projectA, `issue retry ${id}`);
		expect(third.full).toContain("权威未新增记录");
		expect(authorityEvents(fx, id)).toHaveLength(1);
		expect(authorityEvents(fx, id).filter((row) => row.kind === "created")).toHaveLength(1);
		expect(pendingCount(fx.projectA)).toBe(0);
		expect(localIndex(fx.projectA).records[0].state).toBe("submitted");
		verify("VC-003: pending=1 created=1 retries=3 ackloss=1 idempotent=1");
	});
});

// ── VC-004 — dev progress, question/update/reply, list isolation ─────────────

describe("VC-004 (AC-004) same-ID dev progress, question, reply and per-project listing", () => {
	it("latest=已发布 foreign=0; question survives a later update without a question; reply preserves the original scene", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const submitted = await report(a, fx.projectA);
		const id = submitted.id;
		const originalCreatedBytes = authorityBytes(fx, id).split("\n")[0];

		const dev = setup(fx, fx.devRoot, clock);
		const updates: ReadonlyArray<ReadonlyArray<readonly [string, string]>> = [
			[
				["status", "待分诊"],
				["statusNote", "分诊结论：需确认 serve 重启现场"],
				["nextAction", "等待项目补充重启时间"],
				["question", QUESTION],
			],
			[
				["status", "修复中"],
				["statusNote", "开始修复 serve 状态缓存"],
				["nextAction", "补齐回归用例"],
				// deliberately NO question field: collectOptionalFields asks the
				// window, which returns an empty answer -> null.
			],
			[
				["status", "已修复"],
				["statusNote", "已修复缓存刷新"],
				["fixCommit", "abc1234"],
			],
			[
				["status", "已发布"],
				["statusNote", "随发布版本提供"],
				["releaseVersion", "0.9.2"],
			],
		];
		for (const fields of updates) {
			confirm(dev.ui, true);
			const written = await drive(dev.mw, dev.ui, fx.devRoot, updateArgs(id, fields));
			expect(written.full).toContain("已写入");
		}
		expect(authorityEvents(fx, id).filter((row) => row.kind === "dev_update")).toHaveLength(4);

		// Original project can still see the FIRST question even though the
		// later dev updates carried no question at all.
		const beforeReply = await drive(a.mw, a.ui, fx.projectA, `issue status ${id}`);
		expect(beforeReply.full).toContain("最近未回复追问");
		expect(beforeReply.full).toContain(QUESTION);
		expect(beforeReply.full).toContain("当前状态: 已发布");
		expect(beforeReply.full).toContain("修复提交: abc1234");
		expect(beforeReply.full).toContain("发布版本: 0.9.2");
		expect(beforeReply.full).toContain("TRIGGER-MARK");
		expect(beforeReply.full).toContain("END-OF-REPRO-STEPS");

		// Same-ID reporter reply, bound to the question event by a real status read.
		confirm(a.ui, true);
		const replied = await drive(a.mw, a.ui, fx.projectA, `issue reply ${id} ${field("text", REPLY_TEXT)}`);
		expect(replied.full).toContain("已写入");
		expect(replied.full).toContain(REPLY_TEXT);
		const afterReply = await drive(a.mw, a.ui, fx.projectA, `issue status ${id}`);
		expect(afterReply.full).toContain("最近未回复追问");
		expect(afterReply.full).toContain("- 无");
		expect(afterReply.full).toContain(REPLY_TEXT);
		expect(afterReply.full).toContain("TRIGGER-MARK");

		const rows = authorityEvents(fx, id);
		expect(rows.map((row) => row.kind)).toEqual([
			"created",
			"dev_update",
			"dev_update",
			"dev_update",
			"dev_update",
			"reporter_reply",
		]);
		expect(rows.filter((row) => row.kind === "created")).toHaveLength(1);
		expect(authorityBytes(fx, id).split("\n")[0]).toBe(originalCreatedBytes);
		expect(localIndex(fx.projectA).records).toHaveLength(1);

		// The dev window's no-ID list is its OWN local index, not the incoming
		// project's list; project A's list still shows its ID and dev status.
		const devList = await drive(dev.mw, dev.ui, fx.devRoot, "issue status");
		const aList = await drive(a.mw, a.ui, fx.projectA, "issue status");
		expect(devList.full).toContain("本项目未登记反馈 ID");
		expect(devList.full).not.toContain(id);
		expect(aList.full).toContain(id);
		expect(aList.full).toContain("已发布");
		verify("VC-004: latest=DEV_STATUS_RELEASED foreign=0 question=visible reply=same-id scene=preserved");
	});
});

// ── VC-005 — dev fixed but the local project has not verified the fix ────────

describe("VC-005 (AC-005) development fix never equals local effectiveness", () => {
	it("local_effective=not-verified with explicit-unknown and with an old installed version", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const submitted = await report(a, fx.projectA);
		const id = submitted.id;
		const dev = setup(fx, fx.devRoot, clock);
		confirm(dev.ui, true);
		await drive(
			dev.mw,
			dev.ui,
			fx.devRoot,
			updateArgs(id, [
				["status", "已修复"],
				["statusNote", "修复已提交"],
				["fixCommit", "abc1234"],
				["releaseVersion", "0.9.2"],
			]),
		);

		const unknownEvidence = await drive(a.mw, a.ui, fx.projectA, `issue status ${id}`);
		expect(unknownEvidence.full).toContain("开发侧状态 ≠ 本项目已用上修复");
		expect(unknownEvidence.full).toContain(NOT_VERIFIED_PHRASE);
		expect(unknownEvidence.full).not.toContain(VERIFIED_PHRASE);
		expect(unknownEvidence.full).toContain("当前状态: 已修复");

		// Fixture seam: real store status() with an OLD local version + stale
		// bundle/serve. Production wiring itself passes localEvidence=null.
		const stale: LocalEvidence = {
			localVersion: "0.8.1",
			bundleStale: true,
			serveStale: true,
			entrypointInstalled: true,
			collectedAt: "2026-11-13T09:30:00+08:00",
		};
		const staleStore = withLocalEvidence(a.store, stale);
		const staleMw = makeMw(fx.projectA, fx, staleStore, clock);
		const staleUi = new FakeIssueUI();
		const staleResult = await drive(staleMw, staleUi, fx.projectA, `issue status ${id}`);
		expect(staleResult.full).toContain(NOT_VERIFIED_PHRASE);
		expect(staleResult.full).not.toContain(VERIFIED_PHRASE);
		expect(staleResult.full).toContain("state=not-verified");
		expect(staleResult.full).toContain("本地版本 0.8.1 低于修复版本 0.9.2");
		verify("VC-005: local_effective=not-verified unknown-evidence=1 stale-version=1");
	});
});

// ── VC-006 — worker no-write, foreign project write face, byte preservation ──

describe("VC-006 (AC-006) unauthorized worker writes and path conflicts are refused", () => {
	it("denied=1 unchanged=1 for a worker window, a worker-env store and a mismatched store root", async () => {
		const fx = fixture();
		const clock = makeClock();
		const pointer = await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const submitted = await report(a, fx.projectA);
		const b = setup(fx, fx.projectB, clock);
		const submittedB = await report(b, fx.projectB);
		const before = {
			authorityA: authorityBytes(fx, submitted.id),
			authorityB: authorityBytes(fx, submittedB.id),
			indexA: indexBytes(fx.projectA),
			indexB: indexBytes(fx.projectB),
			pointer: readBytes(fx.pointerFile),
		};
		expect(before.pointer).toBe(pointer);

		// (1) REAL worker window env: the registered /mw issue entry refuses
		// BEFORE any store method is reached.
		const calls: string[] = [];
		const workerStore = counting(a.store, calls);
		const workerMw = makeMw(fx.projectA, fx, workerStore, clock);
		const workerUi = new FakeIssueUI();
		process.env.PI_WORKER_TASK = path.join(fx.top, "worker-task.md");
		try {
			confirm(workerUi, true);
			await drive(workerMw, workerUi, fx.projectA, reportArgs());
			confirm(workerUi, true);
			await drive(workerMw, workerUi, fx.projectA, updateArgs(submitted.id, [["status", "已修复"]]));
			confirm(workerUi, true);
			await drive(workerMw, workerUi, fx.projectA, `issue reply ${submitted.id} ${field("text", "worker reply")}`);
			await drive(workerMw, workerUi, fx.projectA, `issue retry ${submitted.id}`);
		} finally {
			delete process.env.PI_WORKER_TASK;
		}
		expect(calls).toEqual([]);
		expect(workerUi.notifications.map((n) => n.message).join("\n")).toContain("拒绝");
		expect(workerUi.notifications.map((n) => n.message).join("\n")).toContain("共享端新增记录数为 0");
		expect(workerUi.confirms).toHaveLength(0);

		// (2) Store-level independent worker gate: real actor from the real
		// window, but the store's OWN env carries PI_WORKER_TASK.
		const devWorkerStore = storeFor(fx.devRoot, fx, {
			env: { PI_WORKER_TASK: path.join(fx.top, "worker-task.md") },
		});
		const devWorkerMw = makeMw(fx.devRoot, fx, devWorkerStore, clock);
		const devWorkerUi = new FakeIssueUI();
		confirm(devWorkerUi, true);
		const storeRefusal = await drive(
			devWorkerMw,
			devWorkerUi,
			fx.devRoot,
			updateArgs(submitted.id, [["status", "已修复"]]),
		);
		expect(storeRefusal.full).toContain("worker-forbidden");
		expect(storeRefusal.full).toContain("未写入");

		// (3) Path conflict: a /mw handler rooted at project B is handed a
		// store rooted at project A (a wrong-root write attempt).
		const mismatchMw = makeMw(fx.projectB, fx, a.store, clock);
		const mismatchUi = new FakeIssueUI();
		confirm(mismatchUi, true);
		const mismatch = await drive(mismatchMw, mismatchUi, fx.projectB, reportArgs());
		expect(mismatch.full).toContain("foreign-project");

		expect(authorityBytes(fx, submitted.id)).toBe(before.authorityA);
		expect(authorityBytes(fx, submittedB.id)).toBe(before.authorityB);
		expect(indexBytes(fx.projectA)).toBe(before.indexA);
		expect(indexBytes(fx.projectB)).toBe(before.indexB);
		expect(readBytes(fx.pointerFile)).toBe(before.pointer);
		expect(authorityLogCount(fx)).toBe(2);
		verify("VC-006: denied=3 unchanged=1 worker-store-calls=0 wrong-project=refused");
	});
});

// ── VC-007 — concurrency, ambiguous root, corrupted log, visible errors ──────

describe("VC-007 (AC-001/AC-003) duplicate=0 wrong_root_writes=0 errors visible", () => {
	it("two concurrent real retries of one pending ID create exactly one authority card", async () => {
		const fx = fixture();
		const clock = makeClock();
		const pointer = await bindViaWindow(fx, clock);
		fs.rmSync(fx.pointerFile); // offline fault hook
		const a = setup(fx, fx.projectA, clock);
		confirm(a.ui, true);
		await drive(a.mw, a.ui, fx.projectA, reportArgs());
		const id = localIndex(fx.projectA).records[0].id;
		fs.writeFileSync(fx.pointerFile, pointer, "utf8");

		const firstUi = new FakeIssueUI();
		const secondUi = new FakeIssueUI();
		await Promise.all([
			a.mw.handler(`issue retry ${id}`, fakeCtx(firstUi, fx.projectA)),
			a.mw.handler(`issue retry ${id}`, fakeCtx(secondUi, fx.projectA)),
		]);
		expect(authorityLogCount(fx)).toBe(1);
		expect(authorityEvents(fx, id)).toHaveLength(1);
		expect(authorityEvents(fx, id).filter((row) => row.kind === "created")).toHaveLength(1);
		expect(localIndex(fx.projectA).records[0].state).toBe("submitted");
		verify("VC-007: concurrent-retries=2 created=1 duplicate=0");
	});

	it("ambiguous pointer and corrupted authority log: no wrong-root writes, no silent repair, errors visible", async () => {
		const fx = fixture();
		const clock = makeClock();
		const pointer = await bindViaWindow(fx, clock);
		// FAULT HOOK: a structurally valid pointer naming TWO different roots.
		const tampered = JSON.parse(pointer) as { canonical_mw_py: string };
		tampered.canonical_mw_py = path.join(fx.secondDevRoot, "packages", "multi-workers", "mw.py");
		fs.writeFileSync(fx.pointerFile, `${JSON.stringify(tampered, null, 2)}\n`, "utf8");

		const a = setup(fx, fx.projectA, clock);
		confirm(a.ui, true);
		const ambiguous = await drive(a.mw, a.ui, fx.projectA, reportArgs());
		expect(ambiguous.full).toContain("未提交");
		expect(ambiguous.full).toContain("E-ISSUE-DEV-ROOT-AMBIGUOUS");
		expect(localIndex(fx.projectA).records[0].state).toBe("pending");
		expect(pendingCount(fx.projectA)).toBe(1);
		expect(authorityLogCount(fx, fx.devRoot)).toBe(0);
		expect(authorityLogCount(fx, fx.secondDevRoot)).toBe(0);
		expect(readBytes(fx.pointerFile)).toContain(fx.secondDevRoot.replaceAll("\\", "\\\\"));
		expect(indexBytes(fx.projectB)).toBe("<absent>");

		// Restore the exact pointer and finish the SAME pending ID.
		fs.writeFileSync(fx.pointerFile, pointer, "utf8");
		const id = localIndex(fx.projectA).records[0].id;
		const recovered = await drive(a.mw, a.ui, fx.projectA, `issue retry ${id}`);
		expect(recovered.full).toContain("已提交");
		expect(authorityLogCount(fx, fx.devRoot)).toBe(1);
		expect(authorityLogCount(fx, fx.secondDevRoot)).toBe(0);
		expect(authorityEvents(fx, id)).toHaveLength(1);

		// FAULT HOOK: same-ID different local content -> conflict, no overwrite.
		const indexFile = issueLocalIndexPath(fx.projectA);
		const index = JSON.parse(fs.readFileSync(indexFile, "utf8")) as {
			records: Array<{ card_sha256: string }>;
		};
		index.records[0].card_sha256 = "f".repeat(64);
		fs.writeFileSync(indexFile, `${JSON.stringify(index, null, 2)}\n`, "utf8");
		const conflict = await drive(a.mw, a.ui, fx.projectA, `issue retry ${id}`);
		expect(conflict.full).toContain("duplicate-conflict");
		expect(authorityBytes(fx, id)).toContain('"kind":"created"');

		// FAULT HOOK: corrupt the authority JSONL. Status must report the error,
		// and must NOT silently repair the file.
		fs.appendFileSync(issueAuthorityLogPath(fx.devRoot, id), "{not-json}\n", "utf8");
		const corruptedBytes = authorityBytes(fx, id);
		const broken = await drive(a.mw, a.ui, fx.projectA, `issue status ${id}`);
		expect(broken.notices).toContain("存储层异常");
		expect(authorityBytes(fx, id)).toBe(corruptedBytes);
		verify("VC-007: duplicate=0 wrong_root_writes=0 ambiguous=visible corrupt=visible");
	});
});

// ── Development window: incoming-card read/triage (spec §1.1, design D002) ──

describe("development window incoming-card read/triage through the ORIGINAL /mw entry", () => {
	it("records the real gap: the dev window cannot open the incoming scene, while project lists stay isolated", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const submitted = await report(a, fx.projectA);
		const id = submitted.id;

		const dev = setup(fx, fx.devRoot, clock);
		const devCard = await drive(dev.mw, dev.ui, fx.devRoot, `issue status ${id}`);
		expect(devCard.full).toContain("当前项目未登记该反馈 ID");
		expect(devCard.full).not.toContain("TRIGGER-MARK");
		expect(devCard.full).not.toContain("END-OF-REPRO-STEPS");

		const devList = await drive(dev.mw, dev.ui, fx.devRoot, "issue status");
		expect(devList.full).toContain("本项目未登记反馈 ID");
		expect(devList.full).not.toContain(id);
		const aList = await drive(a.mw, a.ui, fx.projectA, "issue status");
		expect(aList.full).toContain(id);

		// An update CAN be appended by the dev window, but only with an ID the
		// human already knows out-of-band. appendProgress success is NOT proof
		// that the dev window can read/triage the incoming card (design D002).
		confirm(dev.ui, true);
		const triage = await drive(
			dev.mw,
			dev.ui,
			fx.devRoot,
			updateArgs(id, [
				["status", "待分诊"],
				["statusNote", "分诊：需要现场"],
				["question", QUESTION],
			]),
		);
		expect(triage.full).toContain("已写入");
		expect(authorityEvents(fx, id).filter((row) => row.kind === "dev_update")).toHaveLength(1);
		const stillNoCard = await drive(dev.mw, dev.ui, fx.devRoot, `issue status ${id}`);
		expect(stillNoCard.full).toContain("当前项目未登记该反馈 ID");
		verify("DEV-INBOX: gap=dev-window-cannot-read-incoming-scene lists=isolated appendProgress=not-a-read");
	});
});

// ── Faux-provider harness: real /mw registration, zero provider requests ────

describe("suite harness + faux provider integration", () => {
	it("/mw issue dispatched through a registered command makes zero provider requests and zero writes", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const calls: string[] = [];
		const store = counting(storeFor(fx.projectA, fx), calls);
		const captured: string[] = [];
		const harness = await createHarness({
			extensionFactories: [
				(pi) => {
					registerMwCommands(
						pi,
						fx.projectA,
						new WorkerStore(fx.projectA),
						{} as AckStore,
						{ key: undefined },
						fx.projectA,
						{ store, pointerFile: fx.pointerFile, now: clock },
					);
					pi.registerCommand("issueprobe", {
						description: "probe",
						handler: async (args, ctx) => {
							captured.push(
								await runMwIssueCommand(ctx, fx.projectA, args, {
									store,
									pointerFile: fx.pointerFile,
									now: clock,
								}),
							);
						},
					});
				},
			],
		});
		harnesses.push(harness);
		harness.setResponses([fauxAssistantMessage("MODEL-SHOULD-NOT-RUN")]);
		await harness.session.prompt("/issueprobe issue status");
		await harness.session.prompt("/mw issue status");
		expect(harness.getPendingResponseCount()).toBe(1);
		expect(getAssistantTexts(harness).join("\n")).not.toContain("MODEL-SHOULD-NOT-RUN");
		expect(captured).toHaveLength(1);
		expect(captured[0]).toContain("拒绝");
		expect(calls).toEqual([]);
		verify("HARNESS: real /mw registered faux-provider requests=0 writes=0 headless-refused=1");
	});
});

// ── Real TUI overlay: effective viewport clipping of the FULL preview ────────

class OverlayProbeTui extends TuiMainScreen {
	/** Expose the REAL overlay compositor (maxHeight slice + terminal bounds). */
	clippedLines(width: number, height: number): string[] {
		return this.compositeOverlays([], width, height);
	}
}

interface OverlayFrame {
	screen: string;
	terminal: string;
	header: string;
	rows: number;
	componentRows: number;
}

/** Human-visible text: strip real ANSI/OSC segment resets inserted by the
 * compositor (xterm's viewport already does this), then join wrapped rows. */
function flatten(lines: readonly string[]): string {
	return lines
		.map((line) => stripTerminalSequences(line))
		.join("")
		.replace(/\s+/g, "");
}

/** Real `ctx.ui.custom` seam for the viewport cases: the production preview
 * factory is invoked with a REAL TuiMainScreen, a REAL KeybindingsManager and
 * the real xterm-based offline terminal. showOverlay applies the exact
 * production overlayOptions (width 92%, maxHeight, anchor). Each render frame
 * is captured from BOTH the real compositor output and the real terminal
 * viewport; only those clipped frames count as readable text. */
class RealOverlayUI {
	hasUI = true;
	mode = "tui";
	readonly viewport: { cols: number; rows: number };
	readonly notifications: Notification[] = [];
	readonly confirms: Array<{ title: string; message: string }> = [];
	readonly customs: Array<{ options: unknown; component: PreviewComponentLike; frames: OverlayFrame[] }> = [];
	readonly confirmAnswers: boolean[] = [true];
	readonly doneResults: unknown[] = [];

	constructor(cols: number, rows: number) {
		this.viewport = { cols, rows };
	}

	notify(message: string, type?: "info" | "warning" | "error"): void {
		this.notifications.push({ message, type });
	}
	async confirm(title: string, message: string): Promise<boolean> {
		this.confirms.push({ title, message });
		return this.confirmAnswers.shift() ?? false;
	}
	async input(): Promise<string | undefined> {
		return "";
	}
	async editor(): Promise<string | undefined> {
		return "";
	}
	async select(): Promise<string | undefined> {
		return undefined;
	}
	async custom(factory: unknown, options?: unknown): Promise<void> {
		const fn = factory as PreviewFactory;
		const terminal = new VirtualTerminal(this.viewport.cols, this.viewport.rows);
		const tui = new OverlayProbeTui(terminal);
		const keybindings = new KeybindingsManager(KEYBINDINGS);
		const done = (result: undefined): void => {
			this.doneResults.push(result);
		};
		const component = (await fn(tui, undefined, keybindings, done)) as PreviewComponentLike;
		const opts = (options as { overlay?: boolean; overlayOptions?: OverlayOptions }) ?? {};
		tui.showOverlay(component as Component, opts.overlayOptions ?? {});

		const frames: OverlayFrame[] = [];
		const overlayWidth = Math.max(1, Math.min(Math.floor((this.viewport.cols * 92) / 100), this.viewport.cols));
		const capture = async (): Promise<void> => {
			tui.renderNow(true);
			await terminal.flush();
			const componentRows = component.render(overlayWidth).length; // diagnostic only
			const composed = tui.clippedLines(this.viewport.cols, this.viewport.rows);
			const visible = composed.slice(Math.max(0, composed.length - this.viewport.rows));
			frames.push({
				screen: flatten(visible),
				terminal: flatten(terminal.getViewport()),
				header: visible.find((line) => line.includes("行 · 第")) ?? "",
				rows: visible.length,
				componentRows,
			});
		};
		if (component.fullText.includes("# 脱敏预览")) {
			await capture();
			for (let step = 0; step < 60; step += 1) {
				const before = frames.at(-1)?.screen ?? "";
				component.handleInput?.("\x1b[6~"); // real pageDown key sequence
				await capture();
				if (frames.at(-1)?.screen === before) break; // scrollTop clamped at bottom
			}
			component.handleInput?.("\x1b"); // Esc closes via the real keybinding manager
		} else {
			await capture();
			done(undefined);
		}
		this.customs.push({ options, component, frames });
		tui.stop();
	}
}

const VIEWPORTS = [
	{ label: "80x24", cols: 80, rows: 24 },
	{ label: "60x24", cols: 60, rows: 24 },
	{ label: "30x24-narrow", cols: 30, rows: 24 },
	{ label: "80x12-short", cols: 80, rows: 12 },
	{ label: "60x10-short", cols: 60, rows: 10 },
] as const;

describe.each(VIEWPORTS)("effective TUI overlay viewport $label — every tail text must be reachable", (vp) => {
	it("all tail markers appear in real clipped overlay frames after scrolling", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const store = storeFor(fx.projectA, fx);
		const mw = makeMw(fx.projectA, fx, store, clock);
		const ui = new RealOverlayUI(vp.cols, vp.rows);
		await mw.handler(reportArgs(), fakeCtx(ui, fx.projectA));

		const previewCustom = ui.customs.find((custom) => custom.component.fullText.includes("# 脱敏预览"));
		expect(previewCustom, "preview overlay must be created by the real custom factory").toBeDefined();
		const custom = previewCustom!;
		const options = custom.options as {
			overlay?: boolean;
			overlayOptions?: { width?: unknown; maxHeight?: unknown; anchor?: unknown };
		};
		expect(options.overlay).toBe(true);
		expect(options.overlayOptions?.width).toBe("92%");
		expect(options.overlayOptions?.maxHeight).toBe(ISSUE_PREVIEW_VIEWPORT_LINES + 4);
		expect(custom.frames.length).toBeGreaterThan(1);
		for (const frame of custom.frames) expect(frame.rows).toBeLessThanOrEqual(vp.rows);

		// The comp.fullText property is only a baseline; the assertion below is
		// on the ACTUAL clipped frames (real compositor + real terminal).
		expect(custom.component.fullText).toContain("END-OF-REPRO-STEPS");
		const screen = custom.frames.map((frame) => frame.screen).join("\n");
		const terminal = custom.frames.map((frame) => frame.terminal).join("\n");
		const missingScreen = TAIL_MARKERS.filter((marker) => !screen.includes(marker.text.replace(/\s+/g, ""))).map(
			(marker) => marker.label,
		);
		const missingTerminal = TAIL_MARKERS.filter((marker) => !terminal.includes(marker.text.replace(/\s+/g, ""))).map(
			(marker) => marker.label,
		);
		verify(
			`VIEWPORT ${vp.label}: frames=${custom.frames.length} lineCount=${custom.component.lineCount} ` +
				`componentRows=${custom.frames[0]?.componentRows ?? 0} maxHeight=${ISSUE_PREVIEW_VIEWPORT_LINES + 4} ` +
				`termRows=${vp.rows} missingScreen=${missingScreen.join(",") || "none"} ` +
				`missingTerminal=${missingTerminal.join(",") || "none"}`,
		);
		expect(missingScreen, `${vp.label}: tail text missing from real maxHeight-clipped overlay`).toEqual([]);
		expect(missingTerminal, `${vp.label}: tail text missing from real terminal viewport`).toEqual([]);
	});
});

/** Minimal reproducible failure for the PM: a short preview (no long tokens),
 * an ordinary 80-column terminal with only 12 rows, and a real scroll to the
 * bottom. The fixed 16 content rows + wrapped header/footer still exceed the
 * real maxHeight, and compositeOverlays slices from the TOP, so the LAST preview
 * line and the component's own footer never reach the effective viewport. */
describe("MINIMAL REPRO — real overlay maxHeight clipping hides the preview tail", () => {
	it("80x12: the final preview line is visible after scrolling to the bottom", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const mw = makeMw(fx.projectA, fx, storeFor(fx.projectA, fx), clock);
		const ui = new RealOverlayUI(80, 12);
		await mw.handler(minimalReportArgs(), fakeCtx(ui, fx.projectA));
		const custom = ui.customs.find((entry) => entry.component.fullText.includes("# 脱敏预览"));
		expect(custom).toBeDefined();
		const frames = custom!.frames;
		const screen = frames.map((frame) => frame.screen).join("\n");
		const lastPreviewLine = custom!.component.fullText.split("\n").at(-1) ?? "";
		const normalizedTail = lastPreviewLine.replace(/\s+/g, "");
		verify(
			`MINIMAL-REPRO: frames=${frames.length} componentRows=${frames[0]?.componentRows ?? 0} ` +
				`termRows=12 tail=PREVIEW_LAST_LINE tailVisible=${screen.includes(normalizedTail)}`,
		);
		expect(lastPreviewLine).toContain("说明:");
		expect(screen, "tail of the FULL preview must be reachable in the clipped 80x12 viewport").toContain(
			normalizedTail,
		);
	});
});
