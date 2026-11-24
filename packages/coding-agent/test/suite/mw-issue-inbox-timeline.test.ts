/**
 * mw-issue-inbox-timeline.test.ts — T-09B1 independent registered-handler L2.
 *
 * The full authority event chain must be readable in `/mw issue inbox <id>`.
 * This suite does not import the B suite as an oracle. It registers the real
 * `/mw` command over a real temp IssueStore, one explicit-bound MW dev repo and
 * two ordinary projects, then proves every verified event is displayed in its
 * real seq/append order without time sorting or text deduplication.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import type { IssueCommandStore } from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { VERIFIED_PHRASE } from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	type IssueAuthorityEvent,
	type IssueProgressFields,
	IssueStore,
	type IssueStoreActor,
	issueAuthorityLogPath,
	issueLocalIndexPath,
	issueTextSha256,
	renderDevUpdatePreview,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

// ── Unique sentinels: every historical field must remain distinguishable ─────

const RAW_CONTROL = "\u001b[2J";
const CONTROL_TOKEN = "[[CTL:U+001B]]";
const TRIGGER = "TIMELINE-TRIGGER-SENTINEL-5401";
const REPRO_TAIL = "TIMELINE-REPRO-TAIL-5402";
const ERROR_TAIL = "TIMELINE-ERROR-TAIL-5403";
const UNCONFIRMED = "TIMELINE-UNCONFIRMED-SENTINEL-5404";
const REPORT_AT = "2026-11-13T08:00:00+08:00";
const QUESTION_AT = "2026-11-13T09:00:00+08:00";
const SHARED_AT = "2026-11-13T10:00:00+08:00";
const REPLY_AT = "2026-11-13T11:00:00+08:00";
const RELEASE_AT = "2026-11-13T12:00:00+08:00";
const OLD_1_NOTE = "TIMELINE-OLD1-STATUS-NOTE-5411";
const OLD_1_NEXT = "TIMELINE-OLD1-NEXT-ACTION-5412";
const OLD_1_FIX = "TIMELINE-OLD1-FIX-COMMIT-5413";
const OLD_1_VERSION = "TIMELINE-OLD1-RELEASE-VERSION-5414";
const OLD_1_BY = "pm:timeline-old-1-by-5415";
const OLD_2_NOTE = "TIMELINE-OLD2-STATUS-NOTE-5416";
const OLD_2_NEXT = "TIMELINE-OLD2-NEXT-ACTION-5417";
const OLD_2_FIX = "TIMELINE-OLD2-FIX-COMMIT-5418";
const OLD_2_VERSION = "TIMELINE-OLD2-RELEASE-VERSION-5419";
const OLD_2_BY = "pm:timeline-old-2-by-5420";
const QUESTION_NOTE = "TIMELINE-QUESTION-STATUS-NOTE-5421";
const QUESTION = "TIMELINE-QUESTION-SENTINEL-5422";
const QUESTION_BY = "pm:timeline-question-by-5423";
const REPLY_SENTINEL = "TIMELINE-REPLY-SENTINEL-5424";
const RELEASE_NOTE = "TIMELINE-FINAL-STATUS-NOTE-5425";
const RELEASE_FIX = "TIMELINE-FINAL-FIX-COMMIT-5426";
const RELEASE_VERSION = "TIMELINE-FINAL-RELEASE-VERSION-5427";
const RELEASE_BY = "pm:timeline-final-by-5428";

interface FieldPair {
	key: string;
	value: string;
}

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

function reportFields(marker: string): readonly FieldPair[] {
	return [
		{ key: "title", value: `${marker} /mw inbox timeline regression` },
		{ key: "component", value: "/mw issue inbox" },
		{ key: "occurredAt", value: "2026-11-13T07:45:00+08:00" },
		{ key: "trigger", value: `${marker} ${TRIGGER}${RAW_CONTROL}` },
		{ key: "precondition", value: "TIMELINE-PRECONDITION-5405" },
		{ key: "expected", value: "TIMELINE-EXPECTED-5406" },
		{ key: "actual", value: "TIMELINE-ACTUAL-5407" },
		{ key: "impact", value: "TIMELINE-IMPACT-5408" },
		{ key: "steps", value: `1. /mw issue report；2. /mw issue inbox ${REPRO_TAIL}` },
		{ key: "frequency", value: "偶发" },
		{ key: "error", value: `ERROR timeline ${ERROR_TAIL}` },
		{ key: "mwVersion", value: "0.8.1" },
		{ key: "piVersion", value: "0.12.2" },
		{ key: "platform", value: "Windows 11" },
		{ key: "windowType", value: "pi TUI" },
		{ key: "diagnostic", value: "TIMELINE-SELECTED-DIAGNOSTIC-5409" },
		{ key: "diagnosticKind", value: "log" },
		{ key: "candidate", value: UNCONFIRMED },
	];
}

function reportArgs(marker: string): string {
	return ["issue", "report", ...reportFields(marker).map((entry) => field(entry.key, entry.value))].join(" ");
}

// ── Real temp dev repo + two ordinary projects + explicit pointer ───────────

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
	const top = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-timeline-")));
	tmpRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	const projectA = path.join(top, "project-a");
	const projectB = path.join(top, "project-b");
	makeDevRepo(devRoot);
	makeProject(projectA, "project-a");
	makeProject(projectB, "project-b");
	return {
		top,
		pointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME),
		devRoot: fs.realpathSync(devRoot),
		projectA: fs.realpathSync(projectA),
		projectB: fs.realpathSync(projectB),
	};
}

// ── Registered /mw command + production FULL-text overlay fake ──────────────

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

function storeFor(projectRoot: string, fx: Fixture): IssueStore {
	return new IssueStore({ projectRoot, pointerFile: fx.pointerFile, env: {} });
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

async function bindViaWindow(fx: Fixture, clock: () => string): Promise<void> {
	const bound = setup(fx, fx.devRoot, clock);
	confirm(bound.ui, true);
	await bound.mw.handler("issue bind", fakeCtx(bound.ui, fx.devRoot));
	if (!fs.existsSync(fx.pointerFile)) throw new Error("fixture /mw issue bind failed");
}

async function report(subject: Setup, projectRoot: string, marker: string): Promise<string> {
	confirm(subject.ui, true);
	await drive(subject.mw, subject.ui, projectRoot, reportArgs(marker));
	const index = JSON.parse(fs.readFileSync(issueLocalIndexPath(projectRoot), "utf8")) as {
		records: Array<{ id: string }>;
	};
	if (index.records.length !== 1) throw new Error(`expected one local record, got ${index.records.length}`);
	return index.records[0].id;
}

async function appendDevUpdate(
	fx: Fixture,
	store: IssueStore,
	id: string,
	at: string,
	by: string,
	fields: IssueProgressFields,
): Promise<void> {
	const actor: IssueStoreActor = {
		role: "pm",
		scope: "dev",
		projectRoot: fx.devRoot,
		projectLabel: path.basename(fx.devRoot),
		by,
		trustedWindow: true,
		writeAuthorized: true,
	};
	const preview = renderDevUpdatePreview(fields, { id, at, source: "dev-pm", by });
	const result = await store.appendProgress({
		actor,
		id,
		update: fields,
		preview,
		confirmation: { confirmed: true, confirmedAt: at, previewSha256: issueTextSha256(preview) },
	});
	expect(result.ok).toBe(true);
}

// ── Exact on-disk evidence ──────────────────────────────────────────────────

function authorityEvents(fx: Fixture, id: string): IssueAuthorityEvent[] {
	return fs
		.readFileSync(issueAuthorityLogPath(fx.devRoot, id), "utf8")
		.split("\n")
		.filter((line) => line.length > 0)
		.map((line) => JSON.parse(line) as IssueAuthorityEvent);
}

function createdBytes(fx: Fixture, id: string): string {
	return fs.readFileSync(issueAuthorityLogPath(fx.devRoot, id), "utf8").split("\n")[0];
}

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

it("registered dev inbox FULL text reads every authority event in append order without inventing current/local state", async () => {
	const fx = fixture();
	let clockAt = REPORT_AT;
	const clock = (): string => clockAt;
	await bindViaWindow(fx, clock);
	const a = setup(fx, fx.projectA, clock);
	const b = setup(fx, fx.projectB, clock);
	const idA = await report(a, fx.projectA, "A-TIMELINE");
	const idB = await report(b, fx.projectB, "B-TIMELINE");
	expect(idA).toMatch(/^fb-[0-9a-f]{32}$/);
	expect(idB).not.toBe(idA);
	const originalCreated = createdBytes(fx, idA);
	const dev = setup(fx, fx.devRoot, clock);

	// Two old zero-question updates share one timestamp but have different seq.
	await appendDevUpdate(fx, dev.store, idA, SHARED_AT, OLD_1_BY, {
		status: "待分诊",
		statusNote: OLD_1_NOTE,
		nextAction: OLD_1_NEXT,
		fixCommit: OLD_1_FIX,
		releaseVersion: OLD_1_VERSION,
		questionToReporter: null,
	});
	await appendDevUpdate(fx, dev.store, idA, SHARED_AT, OLD_2_BY, {
		status: "修复中",
		statusNote: OLD_2_NOTE,
		nextAction: OLD_2_NEXT,
		fixCommit: OLD_2_FIX,
		releaseVersion: OLD_2_VERSION,
		questionToReporter: null,
	});
	// This later event has an EARLIER timestamp: append order must beat sorting.
	await appendDevUpdate(fx, dev.store, idA, QUESTION_AT, QUESTION_BY, {
		status: "修复中",
		statusNote: QUESTION_NOTE,
		nextAction: null,
		fixCommit: null,
		releaseVersion: null,
		questionToReporter: QUESTION,
	});
	const beforeReplyRows = authorityEvents(fx, idA);
	const old1 = beforeReplyRows.find((event) => event.kind === "dev_update" && event.update.statusNote === OLD_1_NOTE);
	const old2 = beforeReplyRows.find((event) => event.kind === "dev_update" && event.update.statusNote === OLD_2_NOTE);
	const questionEvent = beforeReplyRows.find(
		(event) => event.kind === "dev_update" && event.update.questionToReporter === QUESTION,
	);
	if (
		old1 === undefined ||
		old1.kind !== "dev_update" ||
		old2 === undefined ||
		old2.kind !== "dev_update" ||
		questionEvent === undefined ||
		questionEvent.kind !== "dev_update"
	) {
		throw new Error("fixture did not append three typed dev_update events");
	}
	expect(old1.at).toBe(SHARED_AT);
	expect(old2.at).toBe(SHARED_AT);
	expect(old1.seq).not.toBe(old2.seq);
	expect(questionEvent.at).toBe(QUESTION_AT);
	expect(questionEvent.seq).toBeGreaterThan(old2.seq);
	expect(createdBytes(fx, idA)).toBe(originalCreated);

	const askedRead = dev.store.readIncoming({
		actor: {
			role: "pm",
			scope: "dev",
			projectRoot: fx.devRoot,
			projectLabel: path.basename(fx.devRoot),
			by: "pm:timeline-read",
			trustedWindow: true,
			writeAuthorized: true,
		},
		id: idA,
	});
	expect(askedRead.pendingQuestion).toBe(QUESTION);
	const asked = await drive(dev.mw, dev.ui, fx.devRoot, `issue inbox ${idA}`);
	expect(asked.full).toContain(`- ${QUESTION}`);

	// Registered same-ID reply binds inReplyTo to the question event hash.
	clockAt = REPLY_AT;
	confirm(a.ui, true);
	const replyResult = await drive(
		a.mw,
		a.ui,
		fx.projectA,
		["issue", "reply", idA, field("text", `${REPLY_SENTINEL}${RAW_CONTROL}`)].join(" "),
	);
	expect(replyResult.full).toContain("已写入");
	const afterReplyRows = authorityEvents(fx, idA);
	const replyEvent = afterReplyRows.find(
		(event) => event.kind === "reporter_reply" && event.reply.text.includes(REPLY_SENTINEL),
	);
	if (replyEvent === undefined || replyEvent.kind !== "reporter_reply") {
		throw new Error("registered reply did not append a reporter_reply event");
	}
	expect(replyEvent.reply.inReplyTo).toBe(questionEvent.sha256);
	expect(replyEvent.at).toBe(REPLY_AT);
	expect(replyEvent.source).toBe("project-pm");

	// Final zero-question release: no pending question re-float.
	await appendDevUpdate(fx, dev.store, idA, RELEASE_AT, RELEASE_BY, {
		status: "已发布",
		statusNote: RELEASE_NOTE,
		nextAction: null,
		fixCommit: RELEASE_FIX,
		releaseVersion: RELEASE_VERSION,
		questionToReporter: null,
	});
	const rows = authorityEvents(fx, idA);
	expect(rows.map((event) => event.seq)).toEqual([1, 2, 3, 4, 5, 6]);
	expect(createdBytes(fx, idA)).toBe(originalCreated);

	const pureReadBefore = snapshot(fx);
	const read = dev.store.readIncoming({
		actor: {
			role: "pm",
			scope: "dev",
			projectRoot: fx.devRoot,
			projectLabel: path.basename(fx.devRoot),
			by: "pm:timeline-read",
			trustedWindow: true,
			writeAuthorized: true,
		},
		id: idA,
	});
	expect(read.ok).toBe(true);
	expect(read.events).toHaveLength(6);
	expect(read.pendingQuestion).toBeNull();
	expect(read.development?.status).toBe("已发布");
	expect(read.development?.statusNote).toBe(RELEASE_NOTE);
	expect(read.development?.fixCommit).toBe(RELEASE_FIX);
	expect(read.development?.releaseVersion).toBe(RELEASE_VERSION);
	expect(read.development?.updatedAt).toBe(RELEASE_AT);
	expect(read.development?.by).toBe(RELEASE_BY);

	const opened = await drive(dev.mw, dev.ui, fx.devRoot, `issue inbox ${idA}`);
	const full = opened.full;
	// FIRST positive assertion that B's production renderer fails: older
	// no-question dev_update status notes are absent from the FULL text.
	expect(full).toContain(OLD_1_NOTE);
	expect(full).toContain(OLD_2_NOTE);
	expect(full).toContain("权威事件时间线（仅历史，按 seq/追加顺序");
	for (const sentinel of [
		OLD_1_NEXT,
		OLD_1_FIX,
		OLD_1_VERSION,
		OLD_1_BY,
		OLD_2_NEXT,
		OLD_2_FIX,
		OLD_2_VERSION,
		OLD_2_BY,
		QUESTION_NOTE,
		QUESTION,
		QUESTION_BY,
		REPLY_SENTINEL,
		RELEASE_NOTE,
		RELEASE_FIX,
		RELEASE_VERSION,
		RELEASE_BY,
	]) {
		expect(full).toContain(sentinel);
	}
	for (const at of [REPORT_AT, SHARED_AT, QUESTION_AT, REPLY_AT, RELEASE_AT]) {
		expect(full).toContain(`at=${at}`);
	}
	for (const event of rows) {
		expect(full).toContain(`#${event.seq} ${event.kind} | seq=${event.seq}`);
		expect(full).toContain(`sha256=${event.sha256}`);
		expect(full).toContain(`prev_sha256=${event.prev_sha256}`);
		expect(full).toContain(`source=${event.source}`);
		expect(full).toContain(`by=${event.by}`);
		expect(full).toContain(`project_label=${event.project_label}`);
		expect(full).toContain(`submission_digest=${event.submission_digest}`);
	}
	expect(full).toContain(`update.at=${SHARED_AT}`);
	expect(full).toContain(`update.by=${OLD_1_BY}`);
	expect(full).toContain(`statusNote=${OLD_1_NOTE}`);
	expect(full).toContain(`statusNote=${OLD_2_NOTE}`);
	expect(full).toContain(`questionToReporter=${QUESTION}`);
	expect(full).toContain(`reply.at=${REPLY_AT}`);
	expect(full).toContain("reply.source=user");
	expect(full).toContain(`reply.text=${REPLY_SENTINEL}`);
	expect(full).toContain(`reply.inReplyTo=${questionEvent.sha256}`);
	expect(full).toContain(`关联 #${questionEvent.seq} dev_update sha256=${questionEvent.sha256}`);
	expect(full).toContain("已回复");
	expect(full).toContain("- 无");
	expect(full).not.toContain(`- ${QUESTION}`);
	expect(full).toContain("当前状态: 已发布");
	expect(full).toContain(`修复提交: ${RELEASE_FIX}`);
	expect(full).toContain(`发布版本: ${RELEASE_VERSION}`);
	expect(full).toContain(`最后更新时间: ${RELEASE_AT}`);
	expect(full).toContain(`更新者: ${RELEASE_BY}`);
	expect(full).not.toContain("- 当前状态: 待分诊");
	expect(full).not.toContain("- 当前状态: 修复中");
	expect(full).not.toContain(VERIFIED_PHRASE);
	expect(full).toContain("开发侧状态仅来自权威事件回放，不等于任意项目本地安装/已用上修复");
	expect(full).toContain(TRIGGER);
	expect(full).toContain(REPRO_TAIL);
	expect(full).toContain(ERROR_TAIL);
	expect(full).toContain("故障发生时间");
	expect(full).toContain("提交时间（窗口记录，非故障时）");
	expect(full).toContain("环境采集时间（窗口记录，非故障时）");
	expect(full).toContain("[用户陈述");
	expect(full).toContain(CONTROL_TOKEN);
	expect(full).not.toContain(RAW_CONTROL);
	expect(full).not.toContain(UNCONFIRMED);
	const positions = [
		full.indexOf("#2 dev_update"),
		full.indexOf("#3 dev_update"),
		full.indexOf("#4 dev_update"),
		full.indexOf("#5 reporter_reply"),
		full.indexOf("#6 dev_update"),
	];
	for (const position of positions) expect(position).toBeGreaterThanOrEqual(0);
	for (let index = 1; index < positions.length; index += 1) {
		expect(positions[index]).toBeGreaterThan(positions[index - 1]);
	}

	// No-ID inbox + ordinary foreign-ID status/inbox isolation stay unchanged.
	const listed = await drive(dev.mw, dev.ui, fx.devRoot, "issue inbox");
	expect(listed.full).toContain("收件数: 2");
	expect(listed.full).toContain(idA);
	expect(listed.full).toContain(idB);
	expect(fs.existsSync(issueLocalIndexPath(fx.devRoot))).toBe(false);
	const foreignStatusA = await drive(a.mw, a.ui, fx.projectA, `issue status ${idB}`);
	expect(foreignStatusA.full).toContain("当前项目未登记该反馈 ID");
	expect(foreignStatusA.full).not.toContain("B-TIMELINE");
	const foreignStatusB = await drive(b.mw, b.ui, fx.projectB, `issue status ${idA}`);
	expect(foreignStatusB.full).toContain("当前项目未登记该反馈 ID");
	expect(foreignStatusB.full).not.toContain(TRIGGER);
	const ordinaryInboxA = await drive(a.mw, a.ui, fx.projectA, `issue inbox ${idA}`);
	expect(ordinaryInboxA.full).toContain("拒绝");
	expect(ordinaryInboxA.full).toContain("devRoot");
	expect(ordinaryInboxA.full).not.toContain(TRIGGER);
	const ordinaryInboxB = await drive(b.mw, b.ui, fx.projectB, `issue inbox ${idB}`);
	expect(ordinaryInboxB.full).toContain("拒绝");
	expect(ordinaryInboxB.full).not.toContain("B-TIMELINE");
	const noIdStatusA = await drive(a.mw, a.ui, fx.projectA, "issue status");
	expect(noIdStatusA.full).toContain(idA);
	expect(noIdStatusA.full).not.toContain(idB);
	const noIdStatusB = await drive(b.mw, b.ui, fx.projectB, "issue status");
	expect(noIdStatusB.full).toContain(idB);
	expect(noIdStatusB.full).not.toContain(idA);
	expect(snapshot(fx)).toEqual(pureReadBefore);
	expect(createdBytes(fx, idA)).toBe(originalCreated);
	verify(
		"TIMELINE-L2: registered=1 dev=1 ordinary=2 bind=1 events=6 same_at=2 append_order=1 " +
			"old_fields=visible latest=released pending=none created=unchanged pure_read=zero_write foreign=isolated",
	);
});
