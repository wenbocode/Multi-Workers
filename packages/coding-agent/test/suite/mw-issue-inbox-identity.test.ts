/**
 * mw-issue-inbox-identity.test.ts — T-12 independent identity × dev-inbox
 * combination regression. No production or old-test edits, no provider.
 *
 * Legal Windows project names go through the REAL registered /mw handler; its
 * host derives projectLabel from path.basename(projectRoot). Labels that cannot
 * be Windows basenames (ESC/bidi and literal tokens containing ':') are created
 * ONLY through the REAL low-level handleIssueCommand host seam + REAL IssueStore,
 * then read through the REAL registered dev /mw handler. That seam is not a
 * claim that production Windows can create such a directory.
 *
 * Identity is asserted from created-event bytes and typed store projections,
 * never from display text. Display may collide: a real control label and its
 * literal control-token string are two distinct stored identities with the same
 * terminal representation. This suite makes no global display-injectivity claim.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import type {
	IssueCommandDeps,
	IssueCommandHost,
	IssueCommandStore,
} from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import { handleIssueCommand } from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import {
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	ISSUE_EVENTS_DIR_BASENAME,
	IssueStore,
	type IssueStoreActor,
	issueAuthorityBasePath,
	issueAuthorityLogPath,
	issueLocalIndexPath,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";
import { escapeIssueIdentity, hasUnsafeControls } from "../../src/extensions/agent-team-loop/shared/issue-text.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const ZWJ = "\u200d";
const ZWNJ = "\u200c";
const ESC = "\u001b";
const RLO = "\u202e";
const LIT_OPEN = "[[LIT:U+005B]]";
const PLAIN_LABEL = "plain-project";
const BRACKET_LABEL = "project[a]";
const UNICODE_LABEL = `项目${ZWJ}团队${ZWNJ}A`;
const CONTROL_LABEL = `ctl${ESC}${RLO}[x]`;
const CONTROL_TOKEN_LABEL = "ctl[[CTL:U+001B]][[CTL:U+202E]][x]";
const TOKEN_LOOKING_LABEL = `project${LIT_OPEN}a]`;
const NORMAL_UNICODE = `中文👨${ZWJ}👩${ZWNJ}👧 e\u0301`;
const TRIGGER_MARK = "TRIGGER-MARK";
const REPRO_TAIL = "END-OF-REPRO-STEPS";
const ERROR_TAIL = "END-OF-KEY-ERROR";
const UNCONFIRMED = "UNCONFIRMED-INBOX-SENTINEL-42";

interface FieldPair {
	key: string;
	value: string;
}

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

function reportFields(marker: string): readonly FieldPair[] {
	return [
		{ key: "title", value: `${marker} /mw issue inbox 身份回归` },
		{ key: "component", value: "/mw issue inbox" },
		{ key: "occurredAt", value: "2026-11-13T08:12:00+08:00" },
		{ key: "trigger", value: `${marker} ${TRIGGER_MARK} 打开开发收件` },
		{ key: "precondition", value: NORMAL_UNICODE },
		{ key: "expected", value: `${marker} EXPECTED-MARK 显示完整现场` },
		{ key: "actual", value: `${marker} ACTUAL-MARK 身份需精确` },
		{ key: "impact", value: `${marker} IMPACT-MARK 收件隔离` },
		{ key: "steps", value: `1. /mw issue inbox；2. 按 ID 打开；3. 核对现场 ${REPRO_TAIL}` },
		{ key: "frequency", value: "偶发" },
		{ key: "error", value: `ERROR ${marker} ${ERROR_TAIL}` },
		{ key: "mwVersion", value: "0.8.1" },
		{ key: "piVersion", value: "0.12.2" },
		{ key: "platform", value: "Windows 11" },
		{ key: "windowType", value: "pi TUI" },
		{ key: "diagnostic", value: `${marker} DIAGNOSTIC-MARK 用户主动选择的日志片段` },
		{ key: "diagnosticKind", value: "log" },
		{ key: "candidate", value: UNCONFIRMED },
	];
}

function reportArgs(marker: string): string {
	return ["issue", "report", ...reportFields(marker).map((entry) => field(entry.key, entry.value))].join(" ");
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

const tmpRoots: string[] = [];
let savedWorkerTask: string | undefined;

beforeEach(() => {
	savedWorkerTask = process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_TASK;
});

afterEach(() => {
	if (savedWorkerTask === undefined) delete process.env.PI_WORKER_TASK;
	else process.env.PI_WORKER_TASK = savedWorkerTask;
	for (const root of tmpRoots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

interface Fixture {
	top: string;
	pointerFile: string;
	devRoot: string;
	plain: string;
	bracket: string;
	literal: string;
	unicode: string;
	control: string;
	controlToken: string;
	tokenLooking: string;
	foreign: string;
}

function makeDevRepo(root: string): void {
	fs.mkdirSync(path.join(root, "packages", "multi-workers"), { recursive: true });
	fs.writeFileSync(path.join(root, "packages", "multi-workers", "mw.py"), "# offline fixture\n", "utf8");
	fs.mkdirSync(path.join(root, "packages", "coding-agent", "src", "extensions", "agent-team-loop"), {
		recursive: true,
	});
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".agenticdoc", "goal.md"), "# MW dev goal\n", "utf8");
}

function makeProject(top: string, label: string): string {
	const root = path.join(top, label);
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".agenticdoc", "goal.md"), `# ${label} goal\n`, "utf8");
	return fs.realpathSync(root);
}

function fixture(): Fixture {
	const top = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-inbox-identity-")));
	tmpRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	makeDevRepo(devRoot);
	return {
		top,
		pointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME),
		devRoot: fs.realpathSync(devRoot),
		plain: makeProject(top, PLAIN_LABEL),
		bracket: makeProject(top, BRACKET_LABEL),
		literal: makeProject(top, "host-seam-literal"),
		unicode: makeProject(top, UNICODE_LABEL),
		control: makeProject(top, "host-seam-control"),
		controlToken: makeProject(top, "host-seam-control-token"),
		tokenLooking: makeProject(top, "host-seam-token-looking"),
		foreign: makeProject(top, "foreign-project"),
	};
}

function eventsDir(fx: Fixture): string {
	return path.join(issueAuthorityBasePath(fx.devRoot), ISSUE_EVENTS_DIR_BASENAME);
}

function authorityLogCount(fx: Fixture): number {
	if (!fs.existsSync(eventsDir(fx))) return 0;
	return fs.readdirSync(eventsDir(fx)).filter((name) => name.endsWith(".jsonl")).length;
}

// ── Real-window UI seam: the production FULL-text overlay factory runs ──────

type PreviewFactory = (
	tui: unknown,
	theme: unknown,
	keybindings: unknown,
	done: (result: undefined) => void,
) => unknown | Promise<unknown>;

class FakeIssueUI {
	hasUI = true;
	mode = "tui";
	readonly notifications: Array<{ message: string; type?: string }> = [];
	readonly customs: string[] = [];
	readonly confirmAnswers: boolean[] = [];
	readonly confirmDecisions: boolean[] = [];
	confirmCalls = 0;

	notify(message: string, type?: "info" | "warning" | "error"): void {
		this.notifications.push({ message, type });
	}
	async confirm(_title: string, _message: string): Promise<boolean> {
		this.confirmCalls += 1;
		const answer = this.confirmAnswers.shift() ?? false;
		this.confirmDecisions.push(answer);
		return answer;
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
	async present(_title: string, text: string): Promise<void> {
		await this.custom(() => ({ fullText: text }));
	}
	async custom(factory: PreviewFactory): Promise<void> {
		const fn = factory as PreviewFactory;
		const tui = { requestRender: () => undefined };
		const keybindings = { matches: (_data: string, _id: string): boolean => false };
		const done = (_result: undefined): void => undefined;
		const component = (await fn(tui, undefined, keybindings, done)) as { fullText: string };
		this.customs.push(component.fullText);
	}
}

function fakeCtx(ui: FakeIssueUI, projectDir: string): ExtensionCommandContext {
	return { mode: ui.mode, hasUI: ui.hasUI, cwd: projectDir, ui } as unknown as ExtensionCommandContext;
}

interface MwCommand {
	handler: (args: string, ctx: ExtensionCommandContext) => Promise<void>;
}

function makeMw(projectDir: string, fx: Fixture, store: IssueCommandStore, clock: () => string): MwCommand {
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
	registerMwCommands(pi, projectDir, new WorkerStore(projectDir), {} as AckStore, { key: undefined }, projectDir, {
		store,
		pointerFile: fx.pointerFile,
		now: clock,
	});
	const handler = commands.get("mw");
	if (!handler) throw new Error("/mw command not registered");
	return { handler };
}

function storeFor(projectRoot: string, fx: Fixture): IssueStore {
	return new IssueStore({ projectRoot, pointerFile: fx.pointerFile, env: {} });
}

/** Fixture-level typed forwarding wrapper (no store behaviour is faked). */
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

interface Setup {
	mw: MwCommand;
	ui: FakeIssueUI;
	store: IssueStore;
}

function setup(fx: Fixture, projectRoot: string, clock: () => string): Setup {
	const store = storeFor(projectRoot, fx);
	return { store, mw: makeMw(projectRoot, fx, store, clock), ui: new FakeIssueUI() };
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
		full: ui.customs.slice(fromCustom).join("\n"),
		notices: ui.notifications
			.slice(fromNotice)
			.map((notification) => notification.message)
			.join("\n"),
	};
}

function confirm(ui: FakeIssueUI, answer = true): void {
	ui.confirmAnswers.push(answer);
}

interface Bound {
	pointer: string;
	ui: FakeIssueUI;
}

async function bindViaWindow(fx: Fixture, clock: () => string): Promise<Bound> {
	const mw = makeMw(fx.devRoot, fx, storeFor(fx.devRoot, fx), clock);
	const ui = new FakeIssueUI();
	confirm(ui, true);
	await mw.handler("issue bind", fakeCtx(ui, fx.devRoot));
	if (!fs.existsSync(fx.pointerFile)) throw new Error("fixture /mw issue bind failed");
	expect(ui.confirmDecisions).toEqual([true]);
	return { pointer: fs.readFileSync(fx.pointerFile, "utf8"), ui };
}

function hostFor(fx: Fixture, projectRoot: string, projectLabel: string, clock: () => string): IssueCommandHost {
	return {
		projectRoot,
		projectLabel,
		by: "project-pm",
		role: "pm",
		trustedWindow: true,
		writeAuthorized: true,
		devRoot: null,
		pointerFile: fx.pointerFile,
		knownSecrets: [],
		localEvidence: null,
		observedEnvironment: null,
		now: clock,
	};
}

function depsFor(
	fx: Fixture,
	projectRoot: string,
	projectLabel: string,
	store: IssueStore,
	ui: FakeIssueUI,
	clock: () => string,
): IssueCommandDeps {
	return {
		host: hostFor(fx, projectRoot, projectLabel, clock),
		ui,
		store: store as unknown as IssueCommandStore,
	};
}

type CreationSource = "registered-path-basename" | "low-level-host-seam";

interface Created {
	id: string;
	marker: string;
	label: string;
	source: CreationSource;
	ui: FakeIssueUI;
}

async function reportRegistered(subject: Setup, projectRoot: string, marker: string, label: string): Promise<Created> {
	confirm(subject.ui, true);
	await drive(subject.mw, subject.ui, projectRoot, reportArgs(marker));
	const index = JSON.parse(fs.readFileSync(issueLocalIndexPath(projectRoot), "utf8")) as {
		records: Array<{ id: string }>;
	};
	if (index.records.length !== 1) throw new Error(`expected exactly one local record, got ${index.records.length}`);
	expect(subject.ui.confirmDecisions).toEqual([true]);
	return {
		id: index.records[0].id,
		marker,
		label,
		source: "registered-path-basename",
		ui: subject.ui,
	};
}

async function reportViaHostSeam(
	fx: Fixture,
	projectRoot: string,
	label: string,
	marker: string,
	clock: () => string,
): Promise<Created> {
	const store = storeFor(projectRoot, fx);
	const ui = new FakeIssueUI();
	confirm(ui, true);
	const result = await handleIssueCommand(reportArgs(marker), depsFor(fx, projectRoot, label, store, ui, clock));
	expect(result.ok, `host-seam report code=${result.code}`).toBe(true);
	expect(result.confirmed).toBe(true);
	expect(result.writesAttempted).toContain("submit");
	expect(ui.confirmDecisions).toEqual([true]);
	if (result.id === null) throw new Error("host-seam report returned no ID");
	return { id: result.id, marker, label, source: "low-level-host-seam", ui };
}

// ── On-disk evidence readers ────────────────────────────────────────────────

interface CreatedEvent {
	kind: string;
	project_label: string;
	card: { projectLabel: string };
}

function createdEvent(fx: Fixture, id: string): CreatedEvent {
	const first = fs.readFileSync(issueAuthorityLogPath(fx.devRoot, id), "utf8").split("\n")[0];
	return JSON.parse(first ?? "") as CreatedEvent;
}

function authorityBytes(fx: Fixture, id: string): string {
	return fs.readFileSync(issueAuthorityLogPath(fx.devRoot, id)).toString("hex");
}

/** Recursive, fully ordered whole-fixture snapshot: exact file bytes + kinds. */
function snapshot(fx: Fixture): string[] {
	const rows: string[] = [];
	const walk = (dir: string, rel: string): void => {
		const entries = fs.readdirSync(dir, { withFileTypes: true });
		entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
		for (const entry of entries) {
			const full = path.join(dir, entry.name);
			const child = rel === "" ? entry.name : `${rel}/${entry.name}`;
			if (entry.isSymbolicLink()) rows.push(`${child}:link:${fs.readlinkSync(full)}`);
			else if (entry.isDirectory()) {
				rows.push(`${child}:dir`);
				walk(full, child);
			} else rows.push(`${child}:file:${fs.readFileSync(full).toString("hex")}`);
		}
	};
	walk(fx.top, "");
	return rows;
}

function listRows(text: string): string[] {
	return text.split("\n").filter((line) => /^- fb-[0-9a-f]{32} \| 来源项目: /.test(line));
}

function devActor(projectRoot: string): IssueStoreActor {
	return {
		role: "pm",
		scope: "dev",
		projectRoot,
		projectLabel: path.basename(projectRoot),
		by: "pm:dev-window",
		trustedWindow: true,
		writeAuthorized: true,
	};
}

function devInbox(fx: Fixture, dev: Setup): Promise<DriveResult> {
	return drive(dev.mw, dev.ui, fx.devRoot, "issue inbox");
}

function devCard(fx: Fixture, dev: Setup, id: string): Promise<DriveResult> {
	return drive(dev.mw, dev.ui, fx.devRoot, `issue inbox ${id}`);
}

function totalConfirms(uis: readonly FakeIssueUI[]): number {
	return uis.reduce((total, ui) => total + ui.confirmCalls, 0);
}

describe("T-12 special identity labels × registered dev inbox list/read", () => {
	it("preserves exact authority identity, safe display, collision rows and read-only isolation", async () => {
		const fx = fixture();
		const clock = makeClock();
		const bound = await bindViaWindow(fx, clock);
		const plain = setup(fx, fx.plain, clock);
		const bracket = setup(fx, fx.bracket, clock);
		const unicode = setup(fx, fx.unicode, clock);
		const dev = setup(fx, fx.devRoot, clock);
		const foreign = setup(fx, fx.foreign, clock);

		const records: Created[] = [
			await reportRegistered(plain, fx.plain, "PLAIN-SCENE", PLAIN_LABEL),
			await reportRegistered(bracket, fx.bracket, "BRACKET-SCENE", BRACKET_LABEL),
			await reportViaHostSeam(fx, fx.literal, LIT_OPEN, "LITERAL-SCENE", clock),
			await reportRegistered(unicode, fx.unicode, "UNICODE-SCENE", UNICODE_LABEL),
			await reportViaHostSeam(fx, fx.control, CONTROL_LABEL, "CONTROL-SCENE", clock),
			await reportViaHostSeam(fx, fx.controlToken, CONTROL_TOKEN_LABEL, "CONTROL-TOKEN-SCENE", clock),
			await reportViaHostSeam(fx, fx.tokenLooking, TOKEN_LOOKING_LABEL, "TOKEN-LOOKING-SCENE", clock),
		];
		const ids = records.map((record) => record.id);
		expect(new Set(ids).size).toBe(records.length);
		for (const id of ids) expect(id).toMatch(/^fb-[0-9a-f]{32}$/);
		expect(authorityLogCount(fx)).toBe(records.length);
		const pointer = JSON.parse(bound.pointer) as { canonical_dev_root: string };
		expect(fs.realpathSync.native(pointer.canonical_dev_root)).toBe(fs.realpathSync.native(fx.devRoot));

		// Exact identity comes ONLY from created bytes/card and typed store results.
		const typedList = dev.store.listIncoming({ actor: devActor(fx.devRoot) });
		expect(typedList.ok).toBe(true);
		expect(typedList.rows).toHaveLength(records.length);
		for (const record of records) {
			const rows = typedList.rows.filter((row) => row.id === record.id);
			expect(rows).toHaveLength(1);
			expect(rows[0]?.projectLabel).toBe(record.label);
			const event = createdEvent(fx, record.id);
			expect(event.kind).toBe("created");
			expect(event.project_label, "authority identity bytes").toBe(record.label);
			expect(event.card.projectLabel, "created card identity bytes").toBe(record.label);
			const typedRead = dev.store.readIncoming({ actor: devActor(fx.devRoot), id: record.id });
			expect(typedRead.ok).toBe(true);
			expect(typedRead.projectLabel, "read.projectLabel exact value").toBe(record.label);
			expect(typedRead.card?.projectLabel, "replayed card identity bytes").toBe(record.label);
		}

		// A specific display collision is expected, never a global no-collision oracle.
		const control = records.find((record) => record.label === CONTROL_LABEL);
		const controlToken = records.find((record) => record.label === CONTROL_TOKEN_LABEL);
		const bracketRecord = records.find((record) => record.label === BRACKET_LABEL);
		const tokenRecord = records.find((record) => record.label === TOKEN_LOOKING_LABEL);
		if (!control || !controlToken || !bracketRecord || !tokenRecord) throw new Error("required pair missing");
		expect(CONTROL_LABEL).not.toBe(CONTROL_TOKEN_LABEL);
		expect(escapeIssueIdentity(CONTROL_LABEL)).toBe(CONTROL_TOKEN_LABEL);
		expect(escapeIssueIdentity(CONTROL_TOKEN_LABEL)).toBe(CONTROL_TOKEN_LABEL);
		expect(BRACKET_LABEL).not.toBe(TOKEN_LOOKING_LABEL);

		const allUis = [bound.ui, ...records.map((record) => record.ui), dev.ui, foreign.ui];
		const confirmsBefore = totalConfirms(allUis);
		const before = snapshot(fx);
		const bytesBefore = new Map(records.map((record) => [record.id, authorityBytes(fx, record.id)]));

		// REAL registered /mw handler: no-ID list, one row per exact ID.
		const listed = await devInbox(fx, dev);
		expect(listed.full).toContain(`收件数: ${records.length}`);
		expect(hasUnsafeControls(listed.full)).toBe(false);
		expect(listed.full).toContain(UNICODE_LABEL);
		const rows = listRows(listed.full);
		expect(rows).toHaveLength(records.length);
		for (const record of records) {
			const idRows = rows.filter((line) => line.startsWith(`- ${record.id} |`));
			expect(idRows).toHaveLength(1);
			expect(idRows[0]).toContain(`来源项目: ${escapeIssueIdentity(record.label)} |`);
		}
		const collisionDisplay = `来源项目: ${escapeIssueIdentity(CONTROL_LABEL)} |`;
		const collisionRows = rows.filter((line) => line.includes(collisionDisplay));
		expect(collisionRows).toHaveLength(2);
		expect(collisionRows.some((line) => line.startsWith(`- ${control.id} |`))).toBe(true);
		expect(collisionRows.some((line) => line.startsWith(`- ${controlToken.id} |`))).toBe(true);
		const bracketRow = rows.find((line) => line.startsWith(`- ${bracketRecord.id} |`));
		const tokenRow = rows.find((line) => line.startsWith(`- ${tokenRecord.id} |`));
		expect(bracketRow).toBeTruthy();
		expect(tokenRow).toBeTruthy();
		expect(bracketRow).not.toBe(tokenRow);

		// REAL registered /mw handler: open each ID's unique complete scene.
		const openedById = new Map<string, string>();
		for (const record of records) {
			const opened = await devCard(fx, dev, record.id);
			openedById.set(record.id, opened.full);
			expect(opened.full).toContain("已只读打开权威问题卡与时间线");
			expect(opened.full).toContain(`来源项目（非敏感标识，不是安装证据）: ${escapeIssueIdentity(record.label)}`);
			expect(opened.full).toContain(record.marker);
			expect(opened.full).toContain(TRIGGER_MARK);
			expect(opened.full).toContain(REPRO_TAIL);
			expect(opened.full).toContain(ERROR_TAIL);
			expect(opened.full).toContain(NORMAL_UNICODE);
			expect(opened.full).not.toContain(UNCONFIRMED);
			expect(hasUnsafeControls(opened.full)).toBe(false);
			for (const other of records) {
				if (other.id !== record.id) expect(opened.full).not.toContain(other.marker);
			}
		}
		expect(openedById.get(control.id)).toContain("[[CTL:U+001B]]");
		expect(openedById.get(control.id)).toContain("[[CTL:U+202E]]");
		expect(openedById.get(bracketRecord.id)).not.toContain(tokenRecord.marker);
		expect(openedById.get(tokenRecord.id)).not.toContain(bracketRecord.marker);

		// Two ordinary projects: no-ID status lists only their own ID. Foreign
		// with-ID status is refused and leaks no confirmed scene.
		const plainStatus = await drive(plain.mw, plain.ui, fx.plain, "issue status");
		expect(plainStatus.full).toContain(records[0]?.id ?? "");
		for (const id of ids.slice(1)) expect(plainStatus.full).not.toContain(id);
		const bracketStatus = await drive(bracket.mw, bracket.ui, fx.bracket, "issue status");
		expect(bracketStatus.full).toContain(bracketRecord.id);
		for (const id of ids.filter((id) => id !== bracketRecord.id)) expect(bracketStatus.full).not.toContain(id);
		const foreignTarget = records[0];
		if (!foreignTarget) throw new Error("no foreign target");
		const foreignStatus = await drive(foreign.mw, foreign.ui, fx.foreign, `issue status ${foreignTarget.id}`);
		expect(foreignStatus.full).toContain("当前项目未登记该反馈 ID");
		expect(foreignStatus.full).not.toContain(foreignTarget.marker);
		expect(foreignStatus.full).not.toContain(TRIGGER_MARK);
		const foreignList = await drive(foreign.mw, foreign.ui, fx.foreign, "issue status");
		expect(foreignList.full).toContain("本项目未登记反馈 ID");
		for (const id of ids) expect(foreignList.full).not.toContain(id);

		const after = snapshot(fx);
		expect(after, "all dev reads, typed reads and status reads are pure").toEqual(before);
		for (const record of records) {
			expect(authorityBytes(fx, record.id), "created/authority original bytes unchanged").toBe(
				bytesBefore.get(record.id),
			);
		}
		expect(totalConfirms(allUis), "zero confirmations on reads").toBe(confirmsBefore);
		expect(fs.existsSync(issueLocalIndexPath(fx.devRoot))).toBe(false);
		const devRel = path.relative(fx.top, fx.devRoot).split(path.sep).join("/");
		const devArtifactRows = after.filter(
			(row) =>
				row.startsWith(`${devRel}/.agenticdoc/mw-issue-feedback/`) &&
				(row.includes("/index.json:") ||
					row.includes(".lock:") ||
					row.includes("/pending/") ||
					row.includes("/authority_ack") ||
					row.includes("repair")),
		);
		expect(devArtifactRows, "no dev local index/ACK/lock/repair generation").toEqual([]);
		process.stdout.write(
			"[VERIFY] T12: labels=7 registered_list=1 registered_reads=7 exact_identity=7 collision_rows=2 " +
				"snapshot=identical read_confirms=0 foreign=refused status=isolated\n",
		);
	});

	it("a non-true report confirmation creates no local or authority record", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const before = snapshot(fx);
		const ui = new FakeIssueUI();
		const result = await handleIssueCommand(
			reportArgs("UNCONFIRMED-SCENE"),
			depsFor(fx, fx.plain, PLAIN_LABEL, storeFor(fx.plain, fx), ui, clock),
		);
		expect(result.ok).toBe(false);
		expect(result.code).toBe("unconfirmed");
		expect(result.confirmed).toBe(false);
		expect(result.writesAttempted).toEqual([]);
		expect(result.text).toContain("共享端新增记录数为 0");
		expect(ui.confirmCalls).toBe(1);
		expect(ui.confirmDecisions).toEqual([false]);
		expect(authorityLogCount(fx)).toBe(0);
		expect(fs.existsSync(issueLocalIndexPath(fx.plain))).toBe(false);
		expect(snapshot(fx)).toEqual(before);
		process.stdout.write("[VERIFY] T12-CONFIRM: false_answer=zero_writes true_creation=real_store\n");
	});

	it("production /mw window refuses temporary worker env before any dev store call", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const plain = setup(fx, fx.plain, clock);
		const record = await reportRegistered(plain, fx.plain, "WORKER-GATE-SCENE", PLAIN_LABEL);
		const dev = setup(fx, fx.devRoot, clock);
		const before = snapshot(fx);
		const calls: string[] = [];
		const workerMw = makeMw(fx.devRoot, fx, counting(dev.store, calls), clock);
		const workerUi = new FakeIssueUI();
		process.env.PI_WORKER_TASK = path.join(fx.top, "worker-task.md");
		try {
			const worker = await drive(workerMw, workerUi, fx.devRoot, "issue inbox");
			expect(worker.notices).toContain("拒绝");
			expect(worker.notices).toContain("worker");
			expect(worker.full).toBe("");
			expect(worker.full).not.toContain(record.marker);
		} finally {
			delete process.env.PI_WORKER_TASK;
		}
		expect(calls).toEqual([]);
		expect(workerUi.confirmCalls).toBe(0);
		expect(fs.existsSync(issueLocalIndexPath(fx.devRoot))).toBe(false);
		expect(snapshot(fx)).toEqual(before);
		process.stdout.write("[VERIFY] T12-WINDOW: worker_env=refused store_calls=0 snapshot=identical\n");
	});
});
