/**
 * issue-command.test.ts — T-04 of key `mw-issue-feedback`: targeted offline
 * evidence for the pi-window guided form, full redacted preview, real-style
 * confirmation, same-ID dev progress / pending question / reporter reply,
 * reporter-facing status projection, explicit bind and trusted-window refusal.
 *
 * The main fixtures use the REAL `IssueStore` + a temporary dev repo/project +
 * an injected machine-level pointer: no real machine pointer, no real shared
 * feedback table, no provider, no network, no service, no bundle. A no-call
 * spy store is used only for pure argument/trust boundaries; it never replaces
 * the production-store integration evidence.
 *
 * This is window-module L2 evidence. T-05 real `/mw` wiring, T-06 independent
 * E2E and T-07 review remain separate tasks.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	createIssueCommandStore,
	handleIssueCommand,
	type IssueCommandDeps,
	type IssueCommandHost,
	type IssueCommandResult,
	type IssueCommandStore,
	type IssueCommandUI,
	parseIssueCommandArgs,
	renderIssueStatusText,
} from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
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
	ISSUE_DISPLAY_NOT_SUBMITTED,
	ISSUE_DISPLAY_SUBMITTED,
	type IssueAuthorityEvent,
	type IssueIncomingListRequest,
	type IssueIncomingReadRequest,
	type IssueListRequest,
	type IssueProgressRequest,
	type IssueReplyRequest,
	type IssueRetryRequest,
	type IssueStatusRequest,
	type IssueStatusResult,
	IssueStore,
	type IssueStoreActor,
	type IssueStoreOptions,
	type IssueSubmitRequest,
	issueAuthorityBasePath,
	issueAuthorityLogPath,
	issueLocalIndexPath,
	issuePendingCopyPath,
	issueTextSha256,
	renderDevUpdatePreview,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";

// ── Synthetic constants ──────────────────────────────────────────────────────

const NOW = "2026-11-12T21:15:00+08:00";
const OCCURRED = "2026-11-12T14:02:11+08:00";
const OBSERVED_AT = "2026-11-12T21:09:58+08:00";
const SECRET_A = "SENTINEL-APIKEY-9f3a2b7c";
const SECRET_B = "SUPERSECRET-VALUE-42";
const UNCONFIRMED = "UNCONFIRMED-RAW-SENTINEL-77";
const LONG_STEP = `1. 运行 /mw status；2. 重启 serve；3. 再查询 ${"step-".repeat(80)} END-OF-REPRO-STEPS`;
const LONG_ERROR = `ERROR serve-stale: ${"E".repeat(300)} END-OF-KEY-ERROR`;
const QUESTION = "请确认重启后是否仍见旧 PID";
const temporaryRoots: string[] = [];

afterEach(() => {
	for (const dir of temporaryRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

interface Fixture {
	top: string;
	home: string;
	pointerFile: string;
	missingPointerFile: string;
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

function fixture(): Fixture {
	const top = fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-command-"));
	temporaryRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	makeDevRepo(devRoot);
	const projectA = path.join(top, "project-a");
	const projectB = path.join(top, "project-b");
	fs.mkdirSync(path.join(projectA, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(projectB, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(projectA, ".agenticdoc", "goal.md"), "# Project A goal\n", "utf8");
	fs.writeFileSync(path.join(projectB, ".agenticdoc", "goal.md"), "# Project B goal\n", "utf8");
	return {
		top,
		home,
		pointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME),
		missingPointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, "missing-pointer.json"),
		devRoot,
		projectA,
		projectB,
	};
}

// ── Fake UI: records every full preview and the exact confirm message ────────

class FakeUI implements IssueCommandUI {
	hasUI: boolean;
	readonly confirms: Array<{ title: string; message: string }> = [];
	readonly presented: Array<{ title: string; text: string }> = [];
	readonly notifications: Array<{ message: string; type: string | undefined }> = [];
	readonly inputCalls: string[] = [];
	readonly editorCalls: string[] = [];
	readonly selectCalls: string[] = [];
	readonly answers: boolean[] = [];
	readonly inputs: string[] = [];
	readonly editors: string[] = [];
	readonly selects: string[] = [];

	constructor(hasUI = true) {
		this.hasUI = hasUI;
	}

	async confirm(title: string, message: string): Promise<boolean> {
		this.confirms.push({ title, message });
		return this.answers.shift() ?? false;
	}

	async input(title: string): Promise<string | undefined> {
		this.inputCalls.push(title);
		return this.inputs.shift() ?? "";
	}

	async editor(title: string): Promise<string | undefined> {
		this.editorCalls.push(title);
		return this.editors.shift() ?? "";
	}

	async select(title: string, options: readonly string[]): Promise<string | undefined> {
		this.selectCalls.push(`${title}:${options.join("|")}`);
		return this.selects.shift();
	}

	notify(message: string, type?: "info" | "warning" | "error"): void {
		this.notifications.push({ message, type });
	}

	async present(title: string, text: string): Promise<void> {
		this.presented.push({ title, text });
	}
}

/** Boundary-only spy: any call throws, so a refusal is provable at call level. */
class NoCallStore implements IssueCommandStore {
	readonly calls: string[] = [];
	submit(): never {
		this.calls.push("submit");
		throw new Error("store.submit must not be called");
	}
	retry(): never {
		this.calls.push("retry");
		throw new Error("store.retry must not be called");
	}
	status(): never {
		this.calls.push("status");
		throw new Error("store.status must not be called");
	}
	list(): never {
		this.calls.push("list");
		throw new Error("store.list must not be called");
	}
	appendProgress(): never {
		this.calls.push("appendProgress");
		throw new Error("store.appendProgress must not be called");
	}
	reply(): never {
		this.calls.push("reply");
		throw new Error("store.reply must not be called");
	}
	listIncoming(): never {
		this.calls.push("listIncoming");
		throw new Error("store.listIncoming must not be called");
	}
	readIncoming(): never {
		this.calls.push("readIncoming");
		throw new Error("store.readIncoming must not be called");
	}
}

/** Simulates a broken pending-question read; no mutation may follow it. */
class ThrowingStatusStore extends NoCallStore {
	override status(): never {
		throw new Error("status read boom");
	}
}

/** Delegates to the REAL store and records the exact requests, so the same
 * knownSecrets / actor / preview-digest contract is provable at call level. */
class RecordingStore implements IssueCommandStore {
	readonly inner: IssueStore;
	readonly submitRequests: IssueSubmitRequest[] = [];
	readonly progressRequests: IssueProgressRequest[] = [];
	readonly replyRequests: IssueReplyRequest[] = [];
	readonly actors: IssueStoreActor[] = [];

	constructor(inner: IssueStore) {
		this.inner = inner;
	}

	submit(request: IssueSubmitRequest) {
		this.submitRequests.push(request);
		this.actors.push(request.actor);
		return this.inner.submit(request);
	}
	retry(request: IssueRetryRequest) {
		return this.inner.retry(request);
	}
	status(request: IssueStatusRequest) {
		return this.inner.status(request);
	}
	list(request: IssueListRequest) {
		return this.inner.list(request);
	}
	appendProgress(request: IssueProgressRequest) {
		this.progressRequests.push(request);
		this.actors.push(request.actor);
		return this.inner.appendProgress(request);
	}
	reply(request: IssueReplyRequest) {
		this.replyRequests.push(request);
		this.actors.push(request.actor);
		return this.inner.reply(request);
	}
	listIncoming(request: IssueIncomingListRequest) {
		return this.inner.listIncoming(request);
	}
	readIncoming(request: IssueIncomingReadRequest) {
		return this.inner.readIncoming(request);
	}
}

// ── Host / store factories ───────────────────────────────────────────────────

function projectHost(fx: Fixture, overrides: Partial<IssueCommandHost> = {}): IssueCommandHost {
	return {
		projectRoot: fx.projectA,
		projectLabel: "project-A",
		by: "pm-A",
		role: "pm",
		trustedWindow: true,
		writeAuthorized: true,
		devRoot: null,
		pointerFile: fx.pointerFile,
		knownSecrets: [SECRET_A, SECRET_B],
		localEvidence: null,
		observedEnvironment: {
			observedAt: OBSERVED_AT,
			values: {
				mwVersion: "0.12.4",
				platform: "Windows 11",
				bundleStatus: "fresh",
				serveStatus: "stale",
			},
		},
		now: () => NOW,
		...overrides,
	};
}

function devHost(fx: Fixture, overrides: Partial<IssueCommandHost> = {}): IssueCommandHost {
	return projectHost(fx, {
		projectRoot: fx.devRoot,
		devRoot: fx.devRoot,
		projectLabel: "mw-dev",
		by: "mw-dev-pm",
		...overrides,
	});
}

/** Offline PM window: `env: {}` is the fixture's injected window env. The
 * PRODUCTION store is `createIssueCommandStore()` and never overrides env. */
function realStore(fx: Fixture, projectRoot: string, overrides: Partial<IssueStoreOptions> = {}): IssueStore {
	return new IssueStore({ projectRoot, env: {}, pointerFile: fx.pointerFile, ...overrides });
}

function deps(host: IssueCommandHost, ui: FakeUI, store: IssueCommandStore): IssueCommandDeps {
	return { host, ui, store };
}

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

function reportArgs(extra: readonly string[] = []): string {
	return [
		"report",
		field("title", "/mw status 重启后显示旧 serve"),
		field("component", "status 子命令"),
		field("occurredAt", OCCURRED),
		field("trigger", "执行 /mw status 后重启 serve"),
		field("precondition", "serve 已运行超过一小时"),
		field("expected", "显示当前 serve 的 PID 与启动时间"),
		field("actual", "仍显示上一次启动的旧 PID"),
		field("impact", "误判 serve 未重启，卡住排障"),
		field("steps", LONG_STEP),
		field("frequency", "偶发"),
		field("error", `${LONG_ERROR} Bearer ${SECRET_B}`),
		field("mwVersion", "0.12.2"),
		field("piVersion", "0.12.1"),
		field("platform", "Windows 11"),
		field("windowType", "tui"),
		field("diagnostic", `E123: api_key=${SECRET_A} 原始报错`),
		field("candidate", `${UNCONFIRMED} 整段会话原文（未选择）`),
		...extra,
	].join(" ");
}

async function bindPointer(fx: Fixture, confirmed = true): Promise<IssueCommandResult> {
	const ui = new FakeUI();
	ui.answers.push(confirmed);
	return handleIssueCommand("bind", deps(devHost(fx), ui, realStore(fx, fx.devRoot)));
}

async function submitReport(
	fx: Fixture,
	ui: FakeUI,
	store: IssueCommandStore = realStore(fx, fx.projectA),
	host: IssueCommandHost = projectHost(fx),
): Promise<IssueCommandResult> {
	ui.answers.push(true);
	return handleIssueCommand(reportArgs(), deps(host, ui, store));
}

// ── Disk helpers ─────────────────────────────────────────────────────────────

function eventsDir(fx: Fixture): string {
	return path.join(issueAuthorityBasePath(fx.devRoot), "events");
}

function countAuthorityLogs(fx: Fixture): number {
	if (!fs.existsSync(eventsDir(fx))) return 0;
	return fs.readdirSync(eventsDir(fx)).filter((name) => name.endsWith(".jsonl")).length;
}

function readEvents(fx: Fixture, id: string): IssueAuthorityEvent[] {
	const file = issueAuthorityLogPath(fx.devRoot, id);
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.length > 0)
		.map((line) => JSON.parse(line) as IssueAuthorityEvent);
}

function allAuthorityBytes(fx: Fixture): string {
	if (!fs.existsSync(eventsDir(fx))) return "";
	return fs
		.readdirSync(eventsDir(fx))
		.filter((name) => name.endsWith(".jsonl"))
		.map((name) => fs.readFileSync(path.join(eventsDir(fx), name), "utf8"))
		.join("\n");
}

function localIndexBytes(projectRoot: string): string {
	const file = issueLocalIndexPath(projectRoot);
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
}

function pendingCount(projectRoot: string): number {
	const dir = path.join(projectRoot, ".agenticdoc", "mw-issue-feedback", "pending");
	if (!fs.existsSync(dir)) return 0;
	return fs.readdirSync(dir).filter((name) => name.endsWith(".json")).length;
}

function expectNoSecrets(text: string): void {
	expect(text).not.toContain(SECRET_A);
	expect(text).not.toContain(SECRET_B);
	expect(text).not.toContain(UNCONFIRMED);
}

describe("production store wiring", () => {
	it("createIssueCommandStore never overrides env: the store keeps process.env for its own PI_WORKER_TASK gate", () => {
		const fx = fixture();
		const store = createIssueCommandStore(fx.projectA) as IssueStore;
		expect(store.env).toBe(process.env);
		expect(store.projectRoot).toBeTruthy();
	});
});

// ── Argument parsing ─────────────────────────────────────────────────────────

describe("parseIssueCommandArgs", () => {
	it("keeps quoted multi-line values verbatim and rejects host-fact injection", () => {
		const parsed = parseIssueCommandArgs(
			`issue report ${field("steps", "1. 第一步\n2. 第二步含空格")} ${field("title", "标题里有空格")}`,
		);
		expect(parsed.error).toBeNull();
		expect(parsed.sub).toBe("report");
		expect(parsed.fields.get("steps")).toBe("1. 第一步\n2. 第二步含空格");
		expect(parsed.fields.get("title")).toBe("标题里有空格");

		for (const key of ["role", "trustedWindow", "writeAuthorized", "projectRoot", "knownSecrets", "pointerFile"]) {
			const forged = parseIssueCommandArgs(`report ${key}=pm`);
			expect(forged.error).toContain("host/真实 UI 事实");
		}
		expect(parseIssueCommandArgs("frobnicate").error).toContain("未知 issue 子命令");
		expect(parseIssueCommandArgs("status not-an-id").error).toContain("反馈 ID 无效");
		expect(parseIssueCommandArgs("retry").error).toContain("缺少反馈 ID");
		expect(parseIssueCommandArgs("report nonsense=true").error).toContain("不接受参数");
	});
});

// ── Real store + temp pointer integration ───────────────────────────────────

describe("handleIssueCommand with the real IssueStore", () => {
	it("bind refuses without confirmation (pointer zero writes), confirms only with boolean true", async () => {
		const fx = fixture();
		const refusedUI = new FakeUI();
		refusedUI.answers.push(false);
		const refused = await handleIssueCommand("bind", deps(devHost(fx), refusedUI, new NoCallStore()));
		expect(refused.refused).toBe(true);
		expect(refused.code).toBe("unconfirmed");
		expect(refused.writesAttempted).toEqual([]);
		expect(fs.existsSync(fx.pointerFile)).toBe(false);
		expect(refusedUI.confirms[0].message).toContain("不是 OS 权限授予");

		const undefinedUI = new FakeUI();
		undefinedUI.answers.push(false); // cancel/timeout/undefined answer: confirm returns false
		const cancelled = await handleIssueCommand("bind", deps(devHost(fx), undefinedUI, new NoCallStore()));
		expect(cancelled.refused).toBe(true);
		expect(fs.existsSync(fx.pointerFile)).toBe(false);

		const bound = await bindPointer(fx, true);
		expect(bound.ok).toBe(true);
		expect(bound.code).toBe("bound");
		expect(bound.writesAttempted).toEqual(["bind"]);
		expect(fs.existsSync(fx.pointerFile)).toBe(true);
	});

	it("report shows the FULL redacted card and a rejected confirmation produces zero shared writes", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const ui = new FakeUI();
		ui.answers.push(false);
		const result = await handleIssueCommand(reportArgs(), deps(projectHost(fx), ui, realStore(fx, fx.projectA)));

		expect(result.refused).toBe(true);
		expect(result.code).toBe("unconfirmed");
		expect(result.confirmed).toBe(false);
		expect(result.writesAttempted).toEqual([]);
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(localIndexBytes(fx.projectA)).toBe("");
		expect(pendingCount(fx.projectA)).toBe(0);

		// The COMPLETE card (not a summary) is what the real confirm dialog got.
		const preview = result.preview ?? "";
		expect(ui.confirms).toHaveLength(1);
		expect(ui.confirms[0].message).toBe(preview);
		expect(ui.presented[0].text).toBe(preview);
		expect(preview).toContain("END-OF-REPRO-STEPS");
		expect(preview).toContain("END-OF-KEY-ERROR");
		expect(preview).toContain(REDACTION_MARK);
		expect(preview).toContain("故障发生时间");
		expect(preview).toContain("提交时间（窗口记录，非故障时）");
		expect(preview).toContain(`窗口实测 @ ${OBSERVED_AT}`);
		expect(preview).toContain("用户陈述");
		expect(preview).toContain("复现与影响");
		expect(preview).toContain("触发与现象（报障事实）");
		expectNoSecrets(preview);
	});

	it("report confirmation writes exactly one authority card with the same ID and separated times/sources", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const ui = new FakeUI();
		const result = await submitReport(fx, ui);

		expect(result.ok).toBe(true);
		expect(result.code).toBe("submitted");
		expect(result.display).toBe(ISSUE_DISPLAY_SUBMITTED);
		expect(result.writesAttempted).toEqual(["submit"]);
		const id = result.id ?? "";
		expect(id).toMatch(/^fb-[0-9a-f]{32}$/);
		expect(countAuthorityLogs(fx)).toBe(1);
		const events = readEvents(fx, id);
		expect(events).toHaveLength(1);
		expect(events[0].kind).toBe("created");
		const index = JSON.parse(localIndexBytes(fx.projectA)) as { records: Array<{ id: string }> };
		expect(index.records.map((record) => record.id)).toEqual([id]);

		expect(ui.confirms[0].message).toBe(result.preview);
		expect(result.text).toContain(result.preview ?? "");
		expect(result.preview).toContain(`- 反馈 ID: ${id}`);
		expect(result.preview).toContain("触发操作");
		expect(result.preview).toContain("预期结果");
		expect(result.preview).toContain("实际结果");
		expect(result.preview).toContain("复现步骤（未知时明确标注，不编造）");
		expect(result.preview).toContain("复现频率: 偶发");
		expect(result.preview).toContain(`- 故障发生时间: ${OCCURRED}`);
		expect(result.preview).toContain(`- 提交时间（窗口记录，非故障时）: ${NOW}`);
		expect(result.preview).toContain(`- 环境采集时间（窗口记录，非故障时）: ${OBSERVED_AT}`);
		expect(result.preview).toContain(`[窗口实测 @ ${OBSERVED_AT}]`);
		expect(result.preview).toContain("[用户陈述");
		expect(result.notes.join("\n")).toContain("1 个未选择的诊断片段仅留在内存");
		expect(result.text).toContain("1 个未选择的诊断片段仅留在内存");
		expectNoSecrets(allAuthorityBytes(fx));
		expectNoSecrets(localIndexBytes(fx.projectA));
		expect(allAuthorityBytes(fx)).toContain("END-OF-REPRO-STEPS");
		expect(allAuthorityBytes(fx)).toContain("END-OF-KEY-ERROR");
	});

	it("offline report leaves one confirmed pending copy; same-ID retry creates at most one authority card", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const offlineStore = realStore(fx, fx.projectA, { pointerFile: fx.missingPointerFile });
		const offline = await submitReport(fx, new FakeUI(), offlineStore);
		expect(offline.display).toBe(ISSUE_DISPLAY_NOT_SUBMITTED);
		expect(offline.ok).toBe(false);
		expect(offline.code).toBe("authority-unavailable");
		expect(offline.text).toContain("权威根定位失败");
		const id = offline.id ?? "";
		expect(id).toMatch(/^fb-[0-9a-f]{32}$/);
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(pendingCount(fx.projectA)).toBe(1);
		expect(fs.existsSync(issuePendingCopyPath(fx.projectA, id))).toBe(true);
		expectNoSecrets(allAuthorityBytes(fx) + localIndexBytes(fx.projectA));
		const pendingBytes = fs.readFileSync(issuePendingCopyPath(fx.projectA, id), "utf8");
		expectNoSecrets(pendingBytes);

		const unavailable = await handleIssueCommand(`status ${id}`, deps(projectHost(fx), new FakeUI(), offlineStore));
		expect(unavailable.code).toBe("authority-unavailable");
		expect(unavailable.text).toContain("权威记录入口不可达，状态无法更新");
		expect(unavailable.text).toContain("不展示过期开发进展");
		expect(unavailable.text).toContain(NOT_VERIFIED_PHRASE);
		expect(unavailable.text).not.toContain(VERIFIED_PHRASE);

		const restored = realStore(fx, fx.projectA);
		const first = await handleIssueCommand(`retry ${id}`, deps(projectHost(fx), new FakeUI(), restored));
		expect(first.ok).toBe(true);
		expect(first.id).toBe(id);
		expect(first.display).toBe(ISSUE_DISPLAY_SUBMITTED);
		expect(countAuthorityLogs(fx)).toBe(1);
		const second = await handleIssueCommand(`retry ${id}`, deps(projectHost(fx), new FakeUI(), restored));
		expect(second.id).toBe(id);
		expect(second.code).toBe("already-submitted");
		expect(countAuthorityLogs(fx)).toBe(1);
		expect(readEvents(fx, id)).toHaveLength(1);
		expect(pendingCount(fx.projectA)).toBe(0);
	});

	it("ask then update without re-asking: status.pendingQuestion still shows the question and the project can reply on the same ID", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const report = await submitReport(fx, new FakeUI());
		const id = report.id ?? "";
		expect(id).not.toBe("");

		const askUI = new FakeUI();
		askUI.answers.push(true);
		const ask = await handleIssueCommand(
			`update ${id} ${field("status", "修复中")} ${field("statusNote", `定位陈旧 serve 缓存 ${SECRET_B}`)} ${field(
				"nextAction",
				"补回归测试",
			)} ${field("question", QUESTION)}`,
			deps(devHost(fx), askUI, realStore(fx, fx.devRoot)),
		);
		expect(ask.ok).toBe(true);
		expect(ask.code).toBe("written");
		expect(ask.preview).toContain(REDACTION_MARK);
		expectNoSecrets(ask.preview ?? "");
		expect(askUI.confirms[0].message).toBe(ask.preview);

		const fixUI = new FakeUI();
		fixUI.answers.push(true);
		const fix = await handleIssueCommand(
			`update ${id} ${field("status", "已修复")} ${field("statusNote", "已合入缓存修复")} ${field(
				"fixCommit",
				"abc1234",
			)}`,
			deps(devHost(fx), fixUI, realStore(fx, fx.devRoot)),
		);
		expect(fix.ok).toBe(true);
		expect(fix.preview).not.toContain(QUESTION); // deliberately NOT re-asked

		const statusUI = new FakeUI();
		const status = await handleIssueCommand(
			`status ${id}`,
			deps(projectHost(fx), statusUI, realStore(fx, fx.projectA)),
		);
		expect(status.pendingQuestion).toBe(QUESTION);
		// status.text's last-update line says 未知; the command must NOT rely on it.
		expect(status.text).toContain("- 待补充问题: 未知");
		expect(status.text).toContain("最近未回复追问");
		expect(status.text).toContain(`- ${QUESTION}`);
		expect(statusUI.presented[0].text).toBe(status.text);
		// The original scene / verbatim error text survives both dev updates.
		expect(status.text).toContain("END-OF-REPRO-STEPS");
		expect(status.text).toContain("END-OF-KEY-ERROR");
		expect(status.text).toContain("后续消息");
		expectNoSecrets(status.text);

		const replyUI = new FakeUI();
		replyUI.answers.push(true);
		const reply = await handleIssueCommand(
			`reply ${id} ${field("text", `重启后仍见旧 PID；补充现场 Bearer ${SECRET_B}`)}`,
			deps(projectHost(fx), replyUI, realStore(fx, fx.projectA)),
		);
		expect(reply.ok).toBe(true);
		expect(reply.code).toBe("written");
		expect(reply.id).toBe(id);
		expect(reply.preview).toContain(REDACTION_MARK);
		expectNoSecrets(reply.preview ?? "");
		expect(replyUI.confirms[0].message).toBe(reply.preview);
		expect(reply.writesAttempted).toEqual(["reply"]);
		expect(countAuthorityLogs(fx)).toBe(1); // same ID, no new issue

		const events = readEvents(fx, id);
		expect(events.map((event) => event.kind)).toEqual(["created", "dev_update", "dev_update", "reporter_reply"]);
		const questionEvent = events[1];
		expect(questionEvent.kind).toBe("dev_update");
		const replyEvent = events[3];
		expect(replyEvent.kind).toBe("reporter_reply");
		if (replyEvent.kind === "reporter_reply") {
			expect(replyEvent.reply.source).toBe("user");
			expect(replyEvent.reply.inReplyTo).toBe(questionEvent.sha256);
			expect(replyEvent.reply.text).toContain(REDACTION_MARK);
		}
		const created = events[0];
		expect(created.kind).toBe("created");
		if (created.kind === "created") {
			expect(created.card.scene.errorExcerpt.value).toContain("END-OF-KEY-ERROR");
			expect(created.card.scene.reproductionSteps.value).toContain("END-OF-REPRO-STEPS");
		}
		expectNoSecrets(allAuthorityBytes(fx));

		const after = await handleIssueCommand(
			`status ${id}`,
			deps(projectHost(fx), new FakeUI(), realStore(fx, fx.projectA)),
		);
		expect(after.pendingQuestion).toBeNull();
		expect(after.text).toContain("最近未回复追问");
		expect(after.text).toContain("- 无");
		expect(after.text).toContain("END-OF-KEY-ERROR");
		expect(after.text).toContain("重启后仍见旧 PID");
		expect(after.text).toContain("不被后续消息覆盖");
	});

	it("status separates dev fix/release from local effectiveness and stays fail-closed when unverifiable", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const report = await submitReport(fx, new FakeUI());
		const id = report.id ?? "";
		const publishUI = new FakeUI();
		publishUI.answers.push(true);
		const published = await handleIssueCommand(
			`update ${id} ${field("status", "已发布")} ${field("fixCommit", "abc1234")} ${field(
				"releaseVersion",
				"0.12.5",
			)}`,
			deps(devHost(fx), publishUI, realStore(fx, fx.devRoot)),
		);
		expect(published.ok).toBe(true);

		const favorable: LocalEvidence = {
			localVersion: "0.12.6",
			bundleStale: false,
			serveStale: false,
			entrypointInstalled: true,
			collectedAt: NOW,
		};
		const withEvidence = await handleIssueCommand(
			`status ${id}`,
			deps(projectHost(fx, { localEvidence: favorable }), new FakeUI(), realStore(fx, fx.projectA)),
		);
		expect(withEvidence.development?.status).toBe("已发布");
		expect(withEvidence.development?.fixCommit).toBe("abc1234");
		expect(withEvidence.development?.releaseVersion).toBe("0.12.5");
		expect(withEvidence.localEffective?.state).not.toBe("verified");
		expect(withEvidence.text).toContain("修复提交: abc1234");
		expect(withEvidence.text).toContain("发布版本: 0.12.5");
		expect(withEvidence.text).toContain("开发侧状态 ≠ 本项目已用上修复");
		expect(withEvidence.text).toContain(NOT_VERIFIED_PHRASE);
		expect(withEvidence.text).not.toContain(VERIFIED_PHRASE);

		const noEvidence = await handleIssueCommand(
			`status ${id}`,
			deps(projectHost(fx), new FakeUI(), realStore(fx, fx.projectA)),
		);
		expect(noEvidence.localEffective?.state).not.toBe("verified");
		expect(noEvidence.text).toContain(NOT_VERIFIED_PHRASE);
		expect(noEvidence.text).not.toContain(VERIFIED_PHRASE);
	});

	it("no-ID status lists only this project's IDs; the other project's card is not listed", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const a = await submitReport(fx, new FakeUI());
		const bHost = projectHost(fx, {
			projectRoot: fx.projectB,
			projectLabel: "project-B",
			by: "pm-B",
		});
		const bReport = await submitReport(fx, new FakeUI(), realStore(fx, fx.projectB), bHost);
		expect(bReport.ok).toBe(true);

		const list = await handleIssueCommand("status", deps(projectHost(fx), new FakeUI(), realStore(fx, fx.projectA)));
		expect(list.rows).toHaveLength(1);
		expect(list.rows[0].id).toBe(a.id);
		expect(list.text).toContain("只列本项目");
		expect(list.text).not.toContain(bReport.id ?? "unreachable");
		expect(countAuthorityLogs(fx)).toBe(2);
	});

	it("untrusted/unauthorized/non-PM/no-UI windows and forged args never reach a store write", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const spy = new NoCallStore();
		const variants: Array<{ label: string; host: IssueCommandHost; ui: FakeUI; args: string }> = [
			{
				label: "untrusted",
				host: projectHost(fx, { trustedWindow: false }),
				ui: new FakeUI(),
				args: reportArgs(),
			},
			{
				label: "unauthorized",
				host: projectHost(fx, { writeAuthorized: false }),
				ui: new FakeUI(),
				args: reportArgs(),
			},
			{ label: "worker", host: projectHost(fx, { role: "worker" }), ui: new FakeUI(), args: reportArgs() },
			{ label: "no-ui", host: projectHost(fx), ui: new FakeUI(false), args: reportArgs() },
			{
				label: "forged-args",
				host: projectHost(fx),
				ui: new FakeUI(),
				args: `report ${field("trustedWindow", "true")}`,
			},
			{ label: "unknown-sub", host: projectHost(fx), ui: new FakeUI(), args: "delete-everything" },
		];
		for (const variant of variants) {
			const result = await handleIssueCommand(variant.args, deps(variant.host, variant.ui, spy));
			expect(result.refused, variant.label).toBe(true);
			expect(result.writesAttempted, variant.label).toEqual([]);
			expect(variant.ui.confirms, variant.label).toHaveLength(0);
		}
		expect(spy.calls).toEqual([]);
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(localIndexBytes(fx.projectA)).toBe("");
	});

	it("keeps the store's independent PI_WORKER_TASK refusal even when host claims a PM window", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const workerEnvStore = realStore(fx, fx.projectA, {
			env: { PI_WORKER_TASK: "E:\\some\\task.md" },
		});
		const ui = new FakeUI();
		const result = await submitReport(fx, ui, workerEnvStore);
		expect(result.code).toBe("worker-forbidden");
		expect(result.ok).toBe(false);
		expect(result.text).toContain("拒绝写入");
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(localIndexBytes(fx.projectA)).toBe("");
		expect(pendingCount(fx.projectA)).toBe(0);
		expectNoSecrets(allAuthorityBytes(fx));
	});

	it("guided collection leaves unknown fields explicit and never invents a failure-time snapshot", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const ui = new FakeUI();
		ui.answers.push(true);
		const host = projectHost(fx, {
			observedEnvironment: { observedAt: "not-an-instant", values: { mwVersion: "0.12.9" } },
		});
		const result = await handleIssueCommand(
			`report ${field("occurredAt", "昨天下午")} ${field("title", "不可复现的偶发问题")}`,
			deps(host, ui, realStore(fx, fx.projectA)),
		);
		expect(result.ok).toBe(true);
		expect(ui.inputCalls.length).toBeGreaterThan(5); // guided form ran
		expect(ui.editorCalls.length).toBeGreaterThan(0);
		expect(result.preview).toContain("- 故障发生时间: 未知");
		expect(result.preview).toContain("- 环境采集时间（窗口记录，非故障时）: 未知");
		expect(result.preview).toContain("当前 MW 版本: 未知");
		expect(result.preview).toContain("- 复现频率: 未知");
		expect(ui.editorCalls.join("\n")).toContain("复现未知/仅发生一次"); // guided hint, never a stored guess
		expect(result.notes.join("\n")).toContain("故障发生时间缺时区或非法");
		expect(result.notes.join("\n")).toContain("窗口实测环境缺合法采集时间");
		expect(result.preview).not.toContain("0.12.9"); // invalid capture time -> no observed value
		expect(result.preview).toContain("不可复现的偶发问题");
		expectNoSecrets(result.preview ?? "");
	});

	it("passes the same transient knownSecrets, host actor facts and full preview digest to the real store for report/update/reply", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const projectRecorder = new RecordingStore(realStore(fx, fx.projectA));
		const reportUI = new FakeUI();
		const report = await submitReport(fx, reportUI, projectRecorder);
		expect(report.ok).toBe(true);
		const id = report.id ?? "";

		const submit = projectRecorder.submitRequests[0];
		expect(submit.knownSecrets).toEqual([SECRET_A, SECRET_B]);
		expect(submit.actor).toEqual({
			role: "pm",
			scope: "project",
			projectRoot: fx.projectA,
			projectLabel: "project-A",
			by: "pm-A",
			trustedWindow: true,
			writeAuthorized: true,
		});
		expect(submit.confirmation.previewSha256).toBe(issueTextSha256(submit.preparation.preview));
		expect(reportUI.confirms[0].message).toBe(submit.preparation.preview);
		expect(submit.preparation.preview).toBe(report.preview);

		const devRecorder = new RecordingStore(realStore(fx, fx.devRoot));
		const updateUI = new FakeUI();
		updateUI.answers.push(true);
		const update = await handleIssueCommand(
			`update ${id} ${field("status", "修复中")} ${field("statusNote", "已定位陈旧缓存")} ${field("question", QUESTION)}`,
			deps(devHost(fx), updateUI, devRecorder),
		);
		expect(update.ok).toBe(true);
		const progress = devRecorder.progressRequests[0];
		expect(progress.knownSecrets).toEqual([SECRET_A, SECRET_B]);
		expect(progress.actor.scope).toBe("dev");
		expect(progress.actor.projectRoot).toBe(fx.devRoot);
		expect(progress.actor.trustedWindow).toBe(true);
		expect(progress.actor.writeAuthorized).toBe(true);
		expect(progress.confirmation.previewSha256).toBe(issueTextSha256(progress.preview));
		expect(progress.confirmation.confirmedAt).not.toBeNull();
		expect(progress.preview).toBe(
			renderDevUpdatePreview(progress.update, {
				id,
				at: progress.confirmation.confirmedAt ?? "",
				source: "dev-pm",
				by: progress.actor.by,
			}),
		);
		expect(updateUI.confirms[0].message).toBe(progress.preview);

		const replyRecorder = new RecordingStore(realStore(fx, fx.projectA));
		const replyUI = new FakeUI();
		replyUI.answers.push(true);
		const reply = await handleIssueCommand(
			`reply ${id} ${field("text", "已按追问补充现场")}`,
			deps(projectHost(fx), replyUI, replyRecorder),
		);
		expect(reply.ok).toBe(true);
		const replyRequest = replyRecorder.replyRequests[0];
		expect(replyRequest.knownSecrets).toEqual([SECRET_A, SECRET_B]);
		expect(replyRequest.actor.scope).toBe("project");
		expect(replyRequest.reply.source).toBe("user");
		expect(replyRequest.confirmation.previewSha256).toBe(issueTextSha256(replyRequest.preview));
		expect(replyUI.confirms[0].message).toBe(replyRequest.preview);
		expect(projectRecorder.actors).toHaveLength(1);
		expect(devRecorder.actors).toHaveLength(1);
		expect(replyRecorder.actors).toHaveLength(1);
	});

	it("update/reply refusals add zero authority events and an unknown ID is reported as unknown", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const report = await submitReport(fx, new FakeUI());
		const id = report.id ?? "";
		const before = readEvents(fx, id).length;
		expect(before).toBe(1);

		const updateUI = new FakeUI();
		updateUI.answers.push(false);
		const refusedUpdate = await handleIssueCommand(
			`update ${id} ${field("status", "修复中")}`,
			deps(devHost(fx), updateUI, realStore(fx, fx.devRoot)),
		);
		expect(refusedUpdate.refused).toBe(true);
		expect(refusedUpdate.code).toBe("unconfirmed");
		expect(refusedUpdate.writesAttempted).toEqual([]);
		expect(readEvents(fx, id)).toHaveLength(before);

		const replyUI = new FakeUI();
		replyUI.answers.push(false);
		const refusedReply = await handleIssueCommand(
			`reply ${id} ${field("text", "补充现场")}`,
			deps(projectHost(fx), replyUI, realStore(fx, fx.projectA)),
		);
		expect(refusedReply.refused).toBe(true);
		expect(refusedReply.writesAttempted).toEqual([]);
		expect(readEvents(fx, id)).toHaveLength(before);

		const unknown = await handleIssueCommand(
			`status fb-${"a".repeat(32)}`,
			deps(projectHost(fx), new FakeUI(), realStore(fx, fx.projectA)),
		);
		expect(unknown.code).toBe("not-owned");
		expect(unknown.text).toContain("当前项目未登记该反馈 ID");
		expect(unknown.text).toContain("当前状态: 未知");
		expect(unknown.text).toContain(NOT_VERIFIED_PHRASE);
		expect(unknown.text).not.toContain(VERIFIED_PHRASE);
	});

	it("[SAMPLE] prints the human-readable redacted card and the same-ID feedback view", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const report = await submitReport(fx, new FakeUI());
		const id = report.id ?? "";
		const updateUI = new FakeUI();
		updateUI.answers.push(true);
		await handleIssueCommand(
			`update ${id} ${field("status", "修复中")} ${field("statusNote", "已定位陈旧 serve 缓存")} ${field("question", QUESTION)}`,
			deps(devHost(fx), updateUI, realStore(fx, fx.devRoot)),
		);
		const status = await handleIssueCommand(
			`status ${id}`,
			deps(projectHost(fx), new FakeUI(), realStore(fx, fx.projectA)),
		);
		console.log("[SAMPLE] === 完整脱敏问题卡（测试数据；确认对话框 message 即该全文） ===");
		console.log(report.preview);
		console.log("[SAMPLE] === 原项目回查视图（开发进展/最近未回复追问/本地生效分栏） ===");
		console.log(status.text);
		expect(status.pendingQuestion).toBe(QUESTION);
		expect(report.preview).toContain(REDACTION_MARK);
	});

	it("never lets a future verified claim through status.text or localEffective", async () => {
		const fx = fixture();
		await bindPointer(fx);
		const report = await submitReport(fx, new FakeUI());
		const id = report.id ?? "";
		const store = realStore(fx, fx.projectA);
		const actor: IssueStoreActor = {
			role: "pm",
			scope: "project",
			projectRoot: fx.projectA,
			projectLabel: "project-A",
			by: "pm-A",
			trustedWindow: true,
			writeAuthorized: true,
		};
		const real = await store.status({ actor, id });
		expect(real.ok).toBe(true);
		const forged: IssueStatusResult = {
			...real,
			text: `${real.text}\n${VERIFIED_PHRASE}（伪造的已验证声明）`,
			localEffective: { state: "verified", phrase: VERIFIED_PHRASE, reason: "伪造的本地证据" },
		};
		const rendered = renderIssueStatusText(forged);
		expect(rendered).not.toContain(VERIFIED_PHRASE);
		expect(rendered).toContain(NOT_VERIFIED_PHRASE);
	});

	it("reply surfaces a failed pending-question read instead of dropping the link", async () => {
		const fx = fixture();
		const ui = new FakeUI();
		ui.answers.push(true);
		const result = await handleIssueCommand(
			`reply fb-${"a".repeat(32)} ${field("text", "补充现场")}`,
			deps(projectHost(fx), ui, new ThrowingStatusStore()),
		);
		expect(result.ok).toBe(false);
		expect(result.code).toBe("E-ISSUE-COMMAND-STORE");
		expect(result.preview).toBeNull();
		expect(result.writesAttempted).toEqual(["status"]);
		expect(ui.confirms).toEqual([]);
	});
});
