/**
 * mw-issue-inbox-fix.test.ts — T-09B independent positive L2 acceptance for
 * `/mw issue inbox [id]` (D002: the MW dev repo reads an incoming card BEFORE
 * triage). This suite is deliberately NOT the original T-06 DEV-INBOX green
 * "gap characterization" case: it asserts the dev window CAN open the confirmed
 * scene, three times/sources, dev progress, the stable pending question and the
 * same-ID replies, through the ACTUAL registered /mw handler.
 *
 * L2 rules:
 *  - One real MW dev repo, two ordinary same-machine projects (A/B), one
 *    explicit machine pointer bound through the real `/mw issue bind` window,
 *    and REAL IssueStore instances over temp files. No store-unit-only call is
 *    accepted as the L2 proof; store-level assertions are additional boundary
 *    evidence.
 *  - The dev read path is independent: no project local index/ACK/state is
 *    created or read to make a card visible, no foreign project cwd/source/env
 *    or credential is consulted, and no write (mkdir/lock/repair) is allowed.
 *  - Old isolation is kept verbatim: ordinary `status [ID]` still refuses a
 *    foreign ID, no-ID `status` still lists only the current project's IDs.
 *  - Damaged cards/directories, stray entries, links and offline pointers are
 *    explicit errors without silent filtering or repair; the original created
 *    bytes never change.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import type { IssueCommandStore } from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import {
	issueDevRootForSub,
	registerMwCommands,
	runMwIssueCommand,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { VERIFIED_PHRASE } from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	ISSUE_EVENTS_DIR_BASENAME,
	type IssueIncomingListResult,
	type IssueIncomingReadResult,
	IssueStore,
	type IssueStoreActor,
	type IssueStoreOptions,
	issueAuthorityBasePath,
	issueAuthorityLogPath,
	issueLocalIndexPath,
	issueTextSha256,
	renderReporterReplyPreview,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

// ── Offline synthetic scene (no credentials, no provider, no network) ───────

const RAW_CONTROL = "\u001b[2J"; // real ESC CSI: must never execute in the TUI
const TRIGGER = "TRIGGER-MARK 在项目A执行 /mw status";
const REPRO_TAIL = "END-OF-REPRO-STEPS";
const ERROR_TAIL = "END-OF-KEY-ERROR";
const UNCONFIRMED = "UNCONFIRMED-INBOX-SENTINEL-42";
const QUESTION_1 = "请补充 serve 重启的准确时间与窗口类型";
const QUESTION_2 = "请确认修复版本是否已在项目A重启后加载";
const REPLY_1 = "REPLY-MARK 补充：重启发生在 08:10，日志已人工脱敏";
const REPLY_2 = "REPLY-MARK 第二问答复：已在 09:00 重启并核对";

interface FieldPair {
	key: string;
	value: string;
}

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

function reportFields(marker: string): readonly FieldPair[] {
	return [
		{ key: "title", value: `${marker} /mw status 重启后显示旧 serve` },
		{ key: "component", value: "/mw status" },
		{ key: "occurredAt", value: "2026-11-13T08:12:00+08:00" },
		{ key: "trigger", value: `${marker} ${TRIGGER}${RAW_CONTROL}` },
		{ key: "precondition", value: "PRECONDITION-MARK serve 曾重启" },
		{ key: "expected", value: "EXPECTED-MARK 显示当前 serve 状态" },
		{ key: "actual", value: "ACTUAL-MARK 显示旧 serve 状态" },
		{ key: "impact", value: "IMPACT-MARK 决策误判" },
		{ key: "steps", value: `1. /mw status；2. 重启 serve；3. 再查询 ${REPRO_TAIL}` },
		{ key: "frequency", value: "偶发" },
		{ key: "error", value: `ERROR serve-stale ${ERROR_TAIL}` },
		{ key: "mwVersion", value: "0.8.1" },
		{ key: "piVersion", value: "0.12.2" },
		{ key: "platform", value: "Windows 11" },
		{ key: "windowType", value: "pi TUI" },
		{ key: "diagnostic", value: "DIAGNOSTIC-MARK 用户主动选择的日志片段" },
		{ key: "diagnosticKind", value: "log" },
		{ key: "candidate", value: UNCONFIRMED },
	];
}

function reportArgs(marker: string): string {
	return ["issue", "report", ...reportFields(marker).map((entry) => field(entry.key, entry.value))].join(" ");
}

function updateArgs(id: string, fields: ReadonlyArray<readonly [string, string]>): string {
	return ["issue", "update", id, ...fields.map(([key, value]) => field(key, value))].join(" ");
}

function replyArgs(id: string, fields: ReadonlyArray<readonly [string, string]>): string {
	return ["issue", "reply", id, ...fields.map(([key, value]) => field(key, value))].join(" ");
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

// ── Temp fixtures: dev repo + two ordinary projects + isolated pointer ──────

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
	fakeDevRoot: string;
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
	const top = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-inbox-")));
	tmpRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	const fakeDevRoot = path.join(top, "mw-dev-self-asserted");
	const projectA = path.join(top, "project-a");
	const projectB = path.join(top, "project-b");
	makeDevRepo(devRoot);
	makeDevRepo(fakeDevRoot); // markers exist, but NO pointer names this root
	makeProject(projectA, "project-a");
	makeProject(projectB, "project-b");
	return {
		top,
		pointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME),
		devRoot: fs.realpathSync(devRoot),
		fakeDevRoot: fs.realpathSync(fakeDevRoot),
		projectA: fs.realpathSync(projectA),
		projectB: fs.realpathSync(projectB),
	};
}

function eventsDir(fx: Fixture): string {
	return path.join(issueAuthorityBasePath(fx.devRoot), ISSUE_EVENTS_DIR_BASENAME);
}

// ── Real-window UI seam: the production FULL-text overlay factory runs ──────

interface CapturedCustom {
	fullText: string;
	options: unknown;
}

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
	readonly confirms: Array<{ title: string; message: string }> = [];
	readonly customs: CapturedCustom[] = [];
	readonly confirmAnswers: boolean[] = [];

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
		const tui = { requestRender: () => undefined };
		const keybindings = { matches: (data: string, id: string): boolean => data === id };
		const done = (_result: undefined): void => undefined;
		const component = (await fn(tui, undefined, keybindings, done)) as { fullText: string };
		this.customs.push({ fullText: component.fullText, options });
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

function storeFor(projectRoot: string, fx: Fixture, extra: Partial<IssueStoreOptions> = {}): IssueStore {
	return new IssueStore({ projectRoot, pointerFile: fx.pointerFile, env: {}, ...extra });
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
		full: ui.customs
			.slice(fromCustom)
			.map((custom) => custom.fullText)
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

async function bindViaWindow(fx: Fixture, clock: () => string): Promise<string> {
	const mw = makeMw(fx.devRoot, fx, storeFor(fx.devRoot, fx), clock);
	const ui = new FakeIssueUI();
	confirm(ui, true);
	await mw.handler("issue bind", fakeCtx(ui, fx.devRoot));
	if (!fs.existsSync(fx.pointerFile)) throw new Error("fixture /mw issue bind failed");
	return fs.readFileSync(fx.pointerFile, "utf8");
}

interface Report {
	id: string;
	full: string;
}

async function report(setupValue: Setup, projectRoot: string, marker: string): Promise<Report> {
	confirm(setupValue.ui, true);
	const result = await drive(setupValue.mw, setupValue.ui, projectRoot, reportArgs(marker));
	const file = issueLocalIndexPath(projectRoot);
	const index = JSON.parse(fs.readFileSync(file, "utf8")) as { records: Array<{ id: string }> };
	if (index.records.length !== 1) throw new Error(`expected exactly one local record, got ${index.records.length}`);
	return { id: index.records[0].id, full: result.full };
}

async function devUpdate(
	fx: Fixture,
	dev: Setup,
	id: string,
	fields: ReadonlyArray<readonly [string, string]>,
): Promise<string> {
	confirm(dev.ui, true);
	const result = await drive(dev.mw, dev.ui, fx.devRoot, updateArgs(id, fields));
	expect(result.full).toContain("已写入");
	return result.full;
}

async function projectReply(
	projectRoot: string,
	subject: Setup,
	id: string,
	fields: ReadonlyArray<readonly [string, string]>,
): Promise<string> {
	confirm(subject.ui, true);
	const result = await drive(subject.mw, subject.ui, projectRoot, replyArgs(id, fields));
	expect(result.full).toContain("已写入");
	return result.full;
}

/** The registered reply command auto-binds a missing `inReplyTo` to the newest
 * question hash. To prove a genuine NULL reference is only a supplement, write
 * that one typed reply through the real store with the real preview/hash
 * confirmation (no model-claimed identity, no fake local record). */
async function nullReferenceReply(
	fx: Fixture,
	subject: Setup,
	id: string,
	text: string,
	clock: () => string,
): Promise<void> {
	const actor: IssueStoreActor = {
		role: "pm",
		scope: "project",
		projectRoot: fx.projectA,
		projectLabel: path.basename(fx.projectA),
		by: "pm:project-a",
		trustedWindow: true,
		writeAuthorized: true,
	};
	const at = clock();
	const reply = { text, source: "user" as const, inReplyTo: null };
	const preview = renderReporterReplyPreview(reply, { id, at, source: "project-pm", by: actor.by });
	const outcome = await subject.store.reply({
		actor,
		id,
		reply,
		preview,
		confirmation: { confirmed: true, confirmedAt: at, previewSha256: issueTextSha256(preview) },
	});
	expect(outcome.ok).toBe(true);
}

// ── On-disk evidence readers ────────────────────────────────────────────────

interface EventRow {
	kind: string;
	seq: number;
	sha256: string;
	at: string;
	update?: { status: string; questionToReporter: string | null };
	reply?: { text: string; inReplyTo: string | null };
	card?: { scene: { trigger: { value: string | null; source: string } } };
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

function createdBytes(fx: Fixture, id: string): string {
	return fs.readFileSync(issueAuthorityLogPath(fx.devRoot, id), "utf8").split("\n")[0];
}

/** Recursive, fully ordered snapshot of the whole fixture tree: exact file
 * bytes + entry kinds. Any mkdir/lock/index/timeline write changes it. */
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
			} else rows.push(`${child}:file:${fs.readFileSync(full, "utf8")}`);
		}
	};
	walk(fx.top, "");
	return rows;
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

function projectActor(projectRoot: string): IssueStoreActor {
	return { ...devActor(projectRoot), scope: "project" };
}

function devInbox(fx: Fixture, dev: Setup): Promise<DriveResult> {
	return drive(dev.mw, dev.ui, fx.devRoot, "issue inbox");
}

function devCard(fx: Fixture, dev: Setup, id: string): Promise<DriveResult> {
	return drive(dev.mw, dev.ui, fx.devRoot, `issue inbox ${id}`);
}

// ── 1. Positive L2: dev reads the incoming scene, triages, asks, reads reply ─

describe("T-09B positive L2 — registered /mw issue inbox [id] in the dev window", () => {
	it("dev sees TRIGGER/repro/three times/source, triage question and same-ID reply; ordinary status stays isolated", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const b = setup(fx, fx.projectB, clock);
		const reportedA = await report(a, fx.projectA, "A-INBOX");
		const reportedB = await report(b, fx.projectB, "B-INBOX");
		const idA = reportedA.id;
		const idB = reportedB.id;
		expect(idA).toMatch(/^fb-[0-9a-f]{32}$/);
		expect(idB).not.toBe(idA);
		const originalCreated = createdBytes(fx, idA);

		const dev = setup(fx, fx.devRoot, clock);

		// (1) No-ID inbox enumerates BOTH authority cards from the events dir.
		const listed = await devInbox(fx, dev);
		expect(listed.full).toContain("权威收件");
		expect(listed.full).toContain("收件数: 2");
		expect(listed.full).toContain(idA);
		expect(listed.full).toContain(idB);
		expect(listed.full).toContain("project-a");
		expect(listed.full).toContain("project-b");
		expect(listed.full).not.toContain(VERIFIED_PHRASE);
		expect(listed.full).not.toContain("本地回执");
		expect(listed.full).toContain("authority/events");

		// (2) With-ID inbox opens the COMPLETE confirmed scene + three times +
		// sources. Foreign control bytes are visible escaped, never executable.
		const opened = await devCard(fx, dev, idA);
		expect(opened.full).toContain("已只读打开权威问题卡与时间线");
		expect(opened.full).toContain("TRIGGER-MARK");
		expect(opened.full).toContain(REPRO_TAIL);
		expect(opened.full).toContain(ERROR_TAIL);
		expect(opened.full).toContain("故障发生时间");
		expect(opened.full).toContain("提交时间（窗口记录，非故障时）");
		expect(opened.full).toContain("环境采集时间（窗口记录，非故障时）");
		expect(opened.full).toContain("[用户陈述");
		expect(opened.full).toContain("[[CTL:U+001B]]");
		expect(opened.full).not.toContain(RAW_CONTROL);
		expect(opened.full).not.toContain(UNCONFIRMED);
		expect(opened.full).toContain("来源项目（非敏感标识，不是安装证据）: project-a");
		expect(opened.full).toContain("权威事件数: 1");
		expect(opened.full).toContain("最近未回复追问（按 dev_update.sha256 事件身份判定");
		expect(opened.full).toContain("- 无");
		expect(opened.full).toContain("开发侧进展（权威记录，与报障事实分栏）");
		expect(opened.full).toContain("开发侧状态仅来自权威事件回放，不等于任意项目本地安装/已用上修复");
		expect(opened.full).not.toContain(VERIFIED_PHRASE);
		expect(opened.full).toContain(idA);
		// The dev window did NOT need any project local index: the dev root has none.
		expect(fs.existsSync(issueLocalIndexPath(fx.devRoot))).toBe(false);

		// (3) Triage: read first, then append a concrete question under the SAME ID.
		await devUpdate(fx, dev, idA, [
			["status", "待分诊"],
			["statusNote", "分诊：需要 serve 重启现场"],
			["nextAction", "等待项目补充"],
			["question", QUESTION_1],
		]);
		const asked = await devCard(fx, dev, idA);
		expect(asked.full).toContain(QUESTION_1);
		expect(asked.full).toContain("当前状态: 待分诊");
		expect(asked.full).toContain("权威事件数: 2");
		const askedList = await devInbox(fx, dev);
		expect(askedList.full).toContain(`- ${idA} |`);
		expect(askedList.full).toContain("待补充: 是");
		expect(askedList.full).toContain("待补充: 否");

		// (4) Same-ID reporter reply (auto-bound to the real question event hash).
		await projectReply(fx.projectA, a, idA, [["text", REPLY_1]]);
		const answered = await devCard(fx, dev, idA);
		expect(answered.full).toContain(REPLY_1);
		expect(answered.full).toContain("最近未回复追问");
		expect(answered.full).toContain("- 无");
		expect(answered.full).toContain("TRIGGER-MARK");
		expect(answered.full).toContain("权威事件数: 3");

		// (5) Fix + release: latest progress/version visible, original created
		// bytes untouched, dev status never equals local effectiveness.
		await devUpdate(fx, dev, idA, [
			["status", "已发布"],
			["statusNote", "随发布版本提供"],
			["fixCommit", "abc1234"],
			["releaseVersion", "0.9.2"],
		]);
		const released = await devCard(fx, dev, idA);
		expect(released.full).toContain("当前状态: 已发布");
		expect(released.full).toContain("修复提交: abc1234");
		expect(released.full).toContain("发布版本: 0.9.2");
		expect(released.full).toContain(REPLY_1);
		expect(released.full).not.toContain(VERIFIED_PHRASE);
		expect(createdBytes(fx, idA)).toBe(originalCreated);

		// (6) OLD isolation is unchanged: foreign-ID status stays refused for the
		// dev window and for the other ordinary project; no-ID status lists only
		// the current project's own IDs, and never widens into the authority.
		const devStatus = await drive(dev.mw, dev.ui, fx.devRoot, `issue status ${idA}`);
		expect(devStatus.full).toContain("当前项目未登记该反馈 ID");
		expect(devStatus.full).not.toContain("TRIGGER-MARK");
		const foreignA = await drive(a.mw, a.ui, fx.projectA, `issue status ${idB}`);
		expect(foreignA.full).toContain("当前项目未登记该反馈 ID");
		expect(foreignA.full).not.toContain("B-INBOX");
		const foreignB = await drive(b.mw, b.ui, fx.projectB, `issue status ${idA}`);
		expect(foreignB.full).toContain("当前项目未登记该反馈 ID");
		const devList = await drive(dev.mw, dev.ui, fx.devRoot, "issue status");
		expect(devList.full).toContain("本项目未登记反馈 ID");
		expect(devList.full).not.toContain(idA);
		expect(devList.full).not.toContain(idB);
		const aList = await drive(a.mw, a.ui, fx.projectA, "issue status");
		expect(aList.full).toContain(idA);
		expect(aList.full).not.toContain(idB);
		verify(
			"INBOX-L2: created=2 dev_list=2 dev_card=open scene=readable control=escaped question=1 reply=1 " +
				"latest=0.9.2 created_bytes=unchanged foreign_status=0 no-id-list=isolated",
		);
	});
});

// ── 2. Typed incoming results + zero writes ─────────────────────────────────

describe("T-09B typed incoming results are pure reads", () => {
	it("no mkdir/lock/index/timeline write; replay card carries real event hashes and no local ACK/state", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const id = (await report(a, fx.projectA, "ZERO-WRITE")).id;
		const dev = setup(fx, fx.devRoot, clock);
		await devUpdate(fx, dev, id, [
			["status", "修复中"],
			["statusNote", "等待复现信息"],
			["question", QUESTION_1],
		]);

		const before = snapshot(fx);
		const beforeCreated = createdBytes(fx, id);
		const list: IssueIncomingListResult = dev.store.listIncoming({ actor: devActor(fx.devRoot) });
		const read: IssueIncomingReadResult = dev.store.readIncoming({ actor: devActor(fx.devRoot), id });
		expect(list.ok).toBe(true);
		expect(list.rows).toHaveLength(1);
		expect(list.rows[0].needsReply).toBe(true);
		expect(Object.keys(list.rows[0])).not.toContain("localState");
		expect(Object.keys(list.rows[0])).not.toContain("submitted");
		expect(Object.keys(list.rows[0])).not.toContain("authorityVerified");
		expect(read.ok).toBe(true);
		expect(read.projectLabel).toBe("project-a");
		expect(read.events.map((event) => event.kind)).toEqual(["created", "dev_update"]);
		expect(read.pendingQuestion).toBe(QUESTION_1);
		expect(read.development?.status).toBe("修复中");
		expect(read.text).toContain("TRIGGER-MARK");
		expect(Object.keys(read)).not.toContain("localRecord");
		expect(Object.keys(read)).not.toContain("localEffective");
		expect(Object.keys(read)).not.toContain("localAck");
		// Real hash identities from the verified chain, in-memory projection only.
		const questionHashes = authorityEvents(fx, id)
			.filter((row) => row.kind === "dev_update")
			.map((row) => row.sha256);
		expect(read.card?.questionEventHashes).toEqual(questionHashes);
		expect(read.card?.devTimeline).toHaveLength(questionHashes.length);
		expect(fs.existsSync(issueLocalIndexPath(fx.devRoot))).toBe(false);

		// Also drive the same reads through the real registered /mw handler.
		await devInbox(fx, dev);
		await devCard(fx, dev, id);
		expect(snapshot(fx)).toEqual(before);
		expect(createdBytes(fx, id)).toBe(beforeCreated);
		verify("INBOX-ZERO-WRITE: list=1 read=1 snapshot=identical dev_local_index=absent hashes=real");
	});
});

// ── 3. Dev identity gates: ordinary projects, worker/headless, self-assertion ─

describe("T-09B dev read identity is not a pointer, a model claim or an arbitrary path", () => {
	it("ordinary A/B, worker env, RPC window, forged actor root and a marker-only path are all refused", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const id = (await report(a, fx.projectA, "GATED")).id;
		const dev = setup(fx, fx.devRoot, clock);
		const positive = await devInbox(fx, dev);
		expect(positive.full).toContain(id);

		// (1) Ordinary project A: host supplies NO validated devRoot -> refusal
		// before any store call; B cannot open A's card either.
		const callsA: string[] = [];
		const aSpy = counting(a.store, callsA);
		const aMw = makeMw(fx.projectA, fx, aSpy, clock);
		const aUi = new FakeIssueUI();
		const aInbox = await drive(aMw, aUi, fx.projectA, "issue inbox");
		expect(aInbox.full).toContain("拒绝");
		expect(aInbox.full).toContain("devRoot");
		expect(aInbox.full).not.toContain("TRIGGER-MARK");
		expect(callsA).toEqual([]);
		const b = setup(fx, fx.projectB, clock);
		const bInbox = await drive(b.mw, b.ui, fx.projectB, `issue inbox ${id}`);
		expect(bInbox.full).toContain("拒绝");
		expect(bInbox.full).not.toContain("TRIGGER-MARK");

		// (2) Store-level independent gates. An ordinary project holding the SAME
		// pointer resolves mode=external and is refused by the dev API.
		const projectStore = storeFor(fx.projectA, fx);
		const projectList = projectStore.listIncoming({ actor: devActor(fx.projectA) });
		expect(projectList.ok).toBe(false);
		expect(projectList.code).toBe("foreign-project");
		expect(projectList.rows).toEqual([]);
		const projectRead = projectStore.readIncoming({ actor: devActor(fx.projectA), id });
		expect(projectRead.ok).toBe(false);
		expect(projectRead.text).not.toContain("TRIGGER-MARK");

		// (3) "not any path self-certifies": a directory with all repo markers but
		// NOT bound by the pointer cannot declare itself the dev authority.
		const fakeStore = storeFor(fx.fakeDevRoot, fx);
		expect(fakeStore.listIncoming({ actor: devActor(fx.fakeDevRoot) }).code).toBe("foreign-project");
		expect(fakeStore.readIncoming({ actor: devActor(fx.fakeDevRoot), id }).code).toBe("foreign-project");
		// A forged actor root on an ordinary store is refused before resolution.
		const forged = dev.store.readIncoming({ actor: devActor(fx.projectA), id });
		expect(forged.ok).toBe(false);
		expect(forged.code).toBe("foreign-project");
		// A non-dev actor scope / untrusted window is refused even at the dev root.
		const scopeRefusal = dev.store.listIncoming({ actor: projectActor(fx.devRoot) });
		expect(scopeRefusal.code).toBe("untrusted-window");

		// (4) Worker env: the registered window refuses before ANY store method;
		// the store's OWN env gate independently refuses a worker-env dev store.
		const workerCalls: string[] = [];
		const workerMw = makeMw(fx.devRoot, fx, counting(dev.store, workerCalls), clock);
		const workerUi = new FakeIssueUI();
		process.env.PI_WORKER_TASK = path.join(fx.top, "worker-task.md");
		try {
			const worker = await drive(workerMw, workerUi, fx.devRoot, "issue inbox");
			// The window gate refuses BEFORE any command/overlay: the refusal is
			// notified, and no card text is ever presented.
			expect(worker.notices).toContain("拒绝");
			expect(worker.notices).toContain("worker");
			expect(worker.full).toBe("");
			expect(worker.full).not.toContain("TRIGGER-MARK");
		} finally {
			delete process.env.PI_WORKER_TASK;
		}
		expect(workerCalls).toEqual([]);
		const workerStore = storeFor(fx.devRoot, fx, { env: { PI_WORKER_TASK: "worker-task.md" } });
		expect(workerStore.listIncoming({ actor: devActor(fx.devRoot) }).code).toBe("worker-forbidden");

		// (5) RPC/headless window: runMwIssueCommand refuses with zero store calls.
		const rpcCalls: string[] = [];
		const rpcUi = new FakeIssueUI();
		rpcUi.mode = "rpc";
		const rpcText = await runMwIssueCommand(fakeCtx(rpcUi, fx.devRoot), fx.devRoot, "issue inbox", {
			store: counting(dev.store, rpcCalls),
			pointerFile: fx.pointerFile,
			now: clock,
		});
		expect(rpcText).toContain("拒绝");
		expect(rpcCalls).toEqual([]);

		// (6) Wiring: inbox gets a devRoot ONLY from the validated local root.
		expect(issueDevRootForSub("inbox", fx.projectA, fx.pointerFile)).toBeNull();
		const local = issueDevRootForSub("inbox", fx.devRoot, fx.pointerFile);
		expect(local).not.toBeNull();
		expect(fs.realpathSync.native(local ?? "")).toBe(fs.realpathSync.native(fx.devRoot));
		verify(
			"INBOX-GATE: ordinary=refused worker=refused rpc=refused forged-root=refused " +
				"marker-only-path=refused scope=refused store_calls=0",
		);
	});
});

// ── 4. Damage / offline / links: explicit errors, no silent repair or filter ─

describe("T-09B read failures are explicit, fail-closed and never repair bytes", () => {
	it("offline pointer, stray entry, damaged card and a linked events dir each refuse without partial success", async () => {
		const fx = fixture();
		const clock = makeClock();
		const pointer = await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const b = setup(fx, fx.projectB, clock);
		const idA = (await report(a, fx.projectA, "DAMAGE-A")).id;
		const idB = (await report(b, fx.projectB, "DAMAGE-B")).id;
		const dev = setup(fx, fx.devRoot, clock);

		// (1) Offline: no pointer -> explicit root failure, no wrong-root fallback.
		fs.rmSync(fx.pointerFile);
		const offlineBefore = snapshot(fx);
		const offlineList = await devInbox(fx, dev);
		expect(offlineList.full).toContain("拒绝");
		expect(offlineList.full).toContain("devRoot");
		expect(offlineList.full).not.toContain(idB);
		const offlineCard = await devCard(fx, dev, idA);
		expect(offlineCard.full).toContain("拒绝");
		expect(offlineCard.full).not.toContain("TRIGGER-MARK");
		// The store's own resolver reports the concrete offline failure; no
		// fallback root is guessed by either layer.
		const offlineStoreList = dev.store.listIncoming({ actor: devActor(fx.devRoot) });
		expect(offlineStoreList.ok).toBe(false);
		expect(offlineStoreList.rootFailure?.code).toBe("E-ISSUE-DEV-ROOT-NOT_CONFIGURED");
		const offlineStoreRead = dev.store.readIncoming({ actor: devActor(fx.devRoot), id: idA });
		expect(offlineStoreRead.ok).toBe(false);
		expect(offlineStoreRead.rootFailure?.code).toBe("E-ISSUE-DEV-ROOT-NOT_CONFIGURED");
		expect(offlineStoreRead.text).toContain("E-ISSUE-DEV-ROOT-NOT_CONFIGURED");
		expect(snapshot(fx)).toEqual(offlineBefore);
		fs.writeFileSync(fx.pointerFile, pointer, "utf8");

		// (2) ONE damaged card: the WHOLE enumeration fails, never a filtered
		// "complete" list; the good card is not silently presented as the inbox.
		fs.appendFileSync(issueAuthorityLogPath(fx.devRoot, idA), "{not-json}\n", "utf8");
		const damagedBytes = fs.readFileSync(issueAuthorityLogPath(fx.devRoot, idA), "utf8");
		const damagedBefore = snapshot(fx);
		const damagedList = await devInbox(fx, dev);
		expect(damagedList.full).toContain("损坏");
		expect(damagedList.full).toContain("未执行任何静默修复");
		expect(damagedList.full).not.toContain(idB);
		const damagedCard = await devCard(fx, dev, idA);
		expect(damagedCard.full).toContain("损坏");
		expect(damagedCard.full).not.toContain("TRIGGER-MARK");
		expect(fs.readFileSync(issueAuthorityLogPath(fx.devRoot, idA), "utf8")).toBe(damagedBytes);
		expect(snapshot(fx)).toEqual(damagedBefore);
		// The other ID remains readable through its own strict replay.
		const goodCard = await devCard(fx, dev, idB);
		expect(goodCard.full).toContain("DAMAGE-B");
		// Restore the exact original log bytes (fixture repair, NOT product repair).
		fs.writeFileSync(issueAuthorityLogPath(fx.devRoot, idA), damagedBytes.replace("{not-json}\n", ""), "utf8");

		// (3) A stray non-card entry is an explicit error, not a filtered row.
		const stray = path.join(eventsDir(fx), "notes.txt");
		fs.writeFileSync(stray, "not a card\n", "utf8");
		const strayList = await devInbox(fx, dev);
		expect(strayList.full).toContain("非法项");
		expect(strayList.full).not.toContain(`- ${idA} |`);
		expect(strayList.full).not.toContain(`- ${idB} |`);
		fs.rmSync(stray);

		// (4) A link/junction as the events directory is refused explicitly.
		const realEvents = path.join(fx.top, "events-elsewhere");
		fs.renameSync(eventsDir(fx), realEvents);
		let linked = false;
		try {
			fs.symlinkSync(realEvents, eventsDir(fx), process.platform === "win32" ? "junction" : "dir");
			linked = true;
		} catch (error) {
			// A platform without link support cannot exercise this seam; the other
			// damage cases still prove fail-closed behaviour.
			verify(`INBOX-DAMAGE: link-seam-unavailable reason=${error instanceof Error ? error.message : String(error)}`);
		}
		if (linked) {
			const linkedList = await devInbox(fx, dev);
			expect(linkedList.full).toContain("损坏");
			expect(linkedList.full).toContain("未执行任何静默修复");
			expect(linkedList.full).not.toContain(idB);
			const linkedCard = await devCard(fx, dev, idA);
			expect(linkedCard.full).toContain("损坏");
			fs.rmSync(eventsDir(fx), { recursive: true, force: true });
			fs.renameSync(realEvents, eventsDir(fx));
		} else {
			fs.renameSync(realEvents, eventsDir(fx));
		}
		// Authority is intact again and the dev inbox works with zero repair from
		// the product's side.
		const recovered = await devInbox(fx, dev);
		expect(recovered.full).toContain("收件数: 2");
		verify("INBOX-DAMAGE: offline=stray=damaged=link explicit no_partial_list=1 no_repair=1 zero_read_writes=1");
	});
});

// ── 5. E's stable question identity rules consumed by the dev inbox ──────────

describe("T-09B pending question uses dev_update.sha256 identity, not the last snapshot", () => {
	it("newer question supersedes the old one; null/created/time references clear nothing; a later no-question update does not re-surface it", async () => {
		const fx = fixture();
		const clock = makeClock();
		await bindViaWindow(fx, clock);
		const a = setup(fx, fx.projectA, clock);
		const id = (await report(a, fx.projectA, "IDENTITY")).id;
		const dev = setup(fx, fx.devRoot, clock);

		await devUpdate(fx, dev, id, [
			["status", "待分诊"],
			["statusNote", "第一问"],
			["question", QUESTION_1],
		]);
		await devUpdate(fx, dev, id, [
			["status", "修复中"],
			["statusNote", "第二问取代第一问"],
			["question", QUESTION_2],
		]);
		const rows = authorityEvents(fx, id);
		const q1 = rows.find((row) => row.update?.questionToReporter === QUESTION_1);
		const q2 = rows.find((row) => row.update?.questionToReporter === QUESTION_2);
		expect(q1?.sha256).toBeTruthy();
		expect(q2?.sha256).toBeTruthy();
		expect(q1?.sha256).not.toBe(q2?.sha256);
		const created = rows.find((row) => row.kind === "created");
		expect(created?.sha256).toBeTruthy();

		const both = dev.store.readIncoming({ actor: devActor(fx.devRoot), id });
		expect(both.pendingQuestion).toBe(QUESTION_2);
		expect(both.card?.questionEventHashes).toEqual(rows.filter((r) => r.kind === "dev_update").map((r) => r.sha256));
		const bothText = await devCard(fx, dev, id);
		expect(bothText.full).toContain(QUESTION_2);
		expect(bothText.full).toContain(QUESTION_1); // timeline still shows the old question as history
		const bothList = dev.store.listIncoming({ actor: devActor(fx.devRoot) });
		expect(bothList.rows[0].needsReply).toBe(true);

		// A late reply bound to the OLD question's event hash does NOT clear Q2.
		await projectReply(fx.projectA, a, id, [
			["text", REPLY_1],
			["inReplyTo", q1?.sha256 ?? ""],
		]);
		expect(dev.store.readIncoming({ actor: devActor(fx.devRoot), id }).pendingQuestion).toBe(QUESTION_2);
		// created-event and time references are mere supplements: clear nothing.
		await projectReply(fx.projectA, a, id, [
			["text", "REPLY-MARK created 引用"],
			["inReplyTo", created?.sha256 ?? ""],
		]);
		await projectReply(fx.projectA, a, id, [
			["text", "REPLY-MARK time 引用"],
			["inReplyTo", q1?.at ?? ""],
		]);
		expect(dev.store.readIncoming({ actor: devActor(fx.devRoot), id }).pendingQuestion).toBe(QUESTION_2);
		// A null reference is also only a supplement.
		await nullReferenceReply(fx, a, id, "REPLY-MARK null 引用", clock);
		expect(dev.store.readIncoming({ actor: devActor(fx.devRoot), id }).pendingQuestion).toBe(QUESTION_2);

		// Exactly the newest question's event hash clears the pending question.
		await projectReply(fx.projectA, a, id, [
			["text", REPLY_2],
			["inReplyTo", q2?.sha256 ?? ""],
		]);
		const cleared = dev.store.readIncoming({ actor: devActor(fx.devRoot), id });
		expect(cleared.pendingQuestion).toBeNull();
		expect(dev.store.listIncoming({ actor: devActor(fx.devRoot) }).rows[0].needsReply).toBe(false);
		// A later dev update with NO question neither invents nor re-surfaces one.
		await devUpdate(fx, dev, id, [
			["status", "已发布"],
			["statusNote", "已发布，无新追问"],
			["releaseVersion", "0.9.3"],
		]);
		const finalRead = dev.store.readIncoming({ actor: devActor(fx.devRoot), id });
		expect(finalRead.pendingQuestion).toBeNull();
		expect(finalRead.development?.status).toBe("已发布");
		expect(finalRead.development?.releaseVersion).toBe("0.9.3");
		const finalText = await devCard(fx, dev, id);
		expect(finalText.full).toContain("- 无");
		expect(finalText.full).toContain(REPLY_2);
		expect(finalText.full).toContain("发布版本: 0.9.3");
		expect(finalText.full).not.toContain(VERIFIED_PHRASE);
		verify(
			"INBOX-IDENTITY: q2=supersedes_q1 late_q1=kept created/time/null=kept " +
				"q2_hash=cleared no-question-update=no-resurface needsReply=false",
		);
	});
});
