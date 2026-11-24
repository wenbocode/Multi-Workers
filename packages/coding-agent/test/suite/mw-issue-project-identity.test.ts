/**
 * mw-issue-project-identity.test.ts — T-09C2R1 independent regression.
 *
 * Project labels are identity values, not raw report text: brackets, literal
 * escape tokens and normal Unicode must survive byte-for-byte through the real
 * command + real dev-root pointer + real temp IssueStore. Display text is a
 * separate canonical, terminal-safe representation. Raw report fields keep the
 * existing exactly-once raw encoding and canonical replay fixed point.
 *
 * Offline fixture only: no provider, no install/runtime claim.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type {
	IssueCommandDeps,
	IssueCommandHost,
	IssueCommandResult,
	IssueCommandStore,
	IssueCommandUI,
} from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import { handleIssueCommand } from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import {
	canonicalPayload,
	type IssueCard,
	renderPreview,
} from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	bindIssueDevRoot,
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
import { escapeUntrustedText, hasUnsafeControls } from "../../src/extensions/agent-team-loop/shared/issue-text.ts";

const ZWJ = "\u200d";
const ZWNJ = "\u200c";
const ESC = "\x1b";
const RLO = "\u202e";
const LIT_OPEN = "[[LIT:U+005B]]";
const CTL_PREFIX = "[[CTL:U+";
const CTL_SUFFIX = "]]";
const NORMAL_UNICODE = `中文👨${ZWJ}👩${ZWNJ}👧 e\u0301`;
const RAW_TITLE = `TITLE[${LIT_OPEN}]${ESC}${RLO}${NORMAL_UNICODE}`;
const RAW_ACTUAL = `ACTUAL[${LIT_OPEN}]${ESC}${RLO}${NORMAL_UNICODE}`;
const QUESTION = `QUESTION[?]${ESC}${RLO}${NORMAL_UNICODE}`;
const REPLY = `REPLY[ok]${ESC}${NORMAL_UNICODE}`;
const LABELS = ["plain-project", "project[a]", LIT_OPEN, `项目${ZWJ}团队${ZWNJ}A`, `ctl${ESC}${RLO}[x]`] as const;

interface Fixture {
	readonly top: string;
	readonly pointerFile: string;
	readonly devRoot: string;
	readonly projectRoots: readonly string[];
}

interface CreatedEvent {
	readonly kind: string;
	readonly project_label: string;
	readonly card_sha256: string;
	readonly preview_sha256: string;
	readonly card: IssueCard;
}

const tmpRoots: string[] = [];

afterEach(() => {
	for (const root of tmpRoots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

function unsafeControl(cp: number): boolean {
	if (cp === 0x000a || cp === 0x200c || cp === 0x200d) return false;
	if (cp <= 0x001f || (cp >= 0x007f && cp <= 0x009f)) return true;
	if (cp === 0x200b || cp === 0x200e || cp === 0x200f) return true;
	if ((cp >= 0x2028 && cp <= 0x202e) || (cp >= 0x2060 && cp <= 0x206f)) return true;
	return cp === 0x00ad || cp === 0x061c || cp === 0x180e || cp === 0xfeff;
}

function controlToken(cp: number): string {
	return `${CTL_PREFIX}${cp.toString(16).toUpperCase().padStart(4, "0")}${CTL_SUFFIX}`;
}

/** Independent raw-ingress oracle for fields that ARE untrusted report text. */
function encodeRawOracle(text: string): string {
	let out = "";
	for (let i = 0; i < text.length; i += 1) {
		const cp = text.charCodeAt(i);
		if (cp === 0x005b) out += LIT_OPEN;
		else if (unsafeControl(cp)) out += controlToken(cp);
		else out += text[i];
	}
	return out;
}

/** Independent inverse of the declared canonical grammar (never a display). */
function decodeCanonicalOracle(text: string): string {
	let out = "";
	let i = 0;
	while (i < text.length) {
		if (text.startsWith(LIT_OPEN, i)) {
			out += "[";
			i += LIT_OPEN.length;
			continue;
		}
		if (text.startsWith(CTL_PREFIX, i)) {
			const end = text.indexOf(CTL_SUFFIX, i + CTL_PREFIX.length);
			if (end > 0) {
				const hex = text.slice(i + CTL_PREFIX.length, end);
				if (/^[0-9A-F]{4,6}$/.test(hex)) {
					const cp = Number.parseInt(hex, 16);
					if (unsafeControl(cp) && text.slice(i, end + 2) === controlToken(cp)) {
						out += String.fromCharCode(cp);
						i = end + 2;
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

function idFor(seed: string): string {
	return `fb-${sha(seed).slice(0, 32)}`;
}

function makeClock(): () => string {
	let tick = 0;
	const base = Date.parse("2026-11-13T09:00:00+08:00");
	return () => new Date(base + tick++ * 1000).toISOString();
}

function makeProjectRoot(top: string, index: number): string {
	const root = path.join(top, `project-${index}`);
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".agenticdoc", "goal.md"), `# project-${index} goal\n`, "utf8");
	return fs.realpathSync(root);
}

function fixture(projectCount: number): Fixture {
	const top = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-project-identity-")));
	tmpRoots.push(top);
	const pointerFile = path.join(top, "machine-home", ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME);
	fs.mkdirSync(path.dirname(pointerFile), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	fs.mkdirSync(path.join(devRoot, "packages", "multi-workers"), { recursive: true });
	fs.writeFileSync(path.join(devRoot, "packages", "multi-workers", "mw.py"), "# offline\n", "utf8");
	fs.mkdirSync(path.join(devRoot, "packages", "coding-agent", "src", "extensions", "agent-team-loop"), {
		recursive: true,
	});
	fs.mkdirSync(path.join(devRoot, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(devRoot, ".agenticdoc", "goal.md"), "# MW dev goal\n", "utf8");
	const projectRoots = Array.from({ length: projectCount }, (_, index) => makeProjectRoot(top, index));
	return { top, pointerFile, devRoot: fs.realpathSync(devRoot), projectRoots };
}

function bindFixture(fx: Fixture, clock: () => string): void {
	const bound = bindIssueDevRoot({
		callerProjectRoot: fx.devRoot,
		candidateRoot: fx.devRoot,
		pointerFile: fx.pointerFile,
		userConfirmed: true,
		now: () => new Date(clock()),
	});
	if (!bound.ok) throw new Error(`fixture dev-root bind failed: ${JSON.stringify(bound)}`);
}

function storeFor(fx: Fixture, projectRoot: string): IssueStore {
	// Explicit empty env: the injected real store never consults the live worker env.
	return new IssueStore({ projectRoot, pointerFile: fx.pointerFile, env: {} });
}

class CaptureUI implements IssueCommandUI {
	readonly hasUI = true;
	readonly capturedTexts: string[] = [];
	readonly confirmAnswers: boolean[] = [];
	confirmCalls = 0;

	constructor(answers: readonly boolean[] = []) {
		this.confirmAnswers.push(...answers);
	}

	async confirm(_title: string, message: string): Promise<boolean> {
		this.confirmCalls += 1;
		this.capturedTexts.push(message);
		return this.confirmAnswers.shift() ?? false;
	}

	async input(): Promise<string> {
		return "";
	}

	async editor(): Promise<string> {
		return "";
	}

	async select(): Promise<undefined> {
		return undefined;
	}

	notify(message: string, _type?: "info" | "warning" | "error"): void {
		this.capturedTexts.push(message);
	}

	async present(_title: string, text: string): Promise<void> {
		this.capturedTexts.push(text);
	}
}

function hostFor(
	fx: Fixture,
	projectRoot: string,
	projectLabel: string,
	by: string,
	devRoot: string | null,
	clock: () => string,
): IssueCommandHost {
	return {
		projectRoot,
		projectLabel,
		by,
		role: "pm",
		trustedWindow: true,
		writeAuthorized: true,
		devRoot,
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
	by: string,
	devRoot: string | null,
	store: IssueStore,
	ui: CaptureUI,
	clock: () => string,
	id: string,
): IssueCommandDeps {
	return {
		host: hostFor(fx, projectRoot, projectLabel, by, devRoot, clock),
		ui,
		store: store as unknown as IssueCommandStore,
		newId: () => id,
	};
}

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

function reportArgs(): string {
	const values: ReadonlyArray<readonly [string, string]> = [
		["title", RAW_TITLE],
		["component", "/mw issue status"],
		["occurredAt", "2026-11-13T08:12:00+08:00"],
		["trigger", "trigger"],
		["precondition", NORMAL_UNICODE],
		["expected", "expected"],
		["actual", RAW_ACTUAL],
		["impact", "impact"],
		["steps", "1. open\n2. report"],
		["frequency", "偶发"],
		["error", "error"],
		["mwVersion", "0.8.1"],
		["piVersion", "0.12.2"],
		["platform", "Windows 11"],
		["windowType", "pi TUI"],
		["diagnostic", ""],
	];
	return ["issue", "report", ...values.map(([key, value]) => field(key, value))].join(" ");
}

function updateArgs(id: string): string {
	const values: ReadonlyArray<readonly [string, string]> = [
		["status", "修复中"],
		["statusNote", "triage"],
		["nextAction", "investigate"],
		["fixCommit", "abc1234"],
		["releaseVersion", "0.12.5"],
		["question", QUESTION],
	];
	return ["issue", "update", id, ...values.map(([key, value]) => field(key, value))].join(" ");
}

function replyArgs(id: string, text = REPLY): string {
	return ["issue", "reply", id, field("text", text)].join(" ");
}

function authorityRawLines(fx: Fixture, id: string): string[] {
	const file = issueAuthorityLogPath(fx.devRoot, id);
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line !== "");
}

function authorityEvents(fx: Fixture, id: string): Array<Record<string, unknown>> {
	return authorityRawLines(fx, id).map((line) => JSON.parse(line) as Record<string, unknown>);
}

function createdEvent(fx: Fixture, id: string): CreatedEvent {
	const lines = authorityRawLines(fx, id);
	expect(lines.length, "created authority event exists").toBeGreaterThan(0);
	return JSON.parse(lines[0]) as CreatedEvent;
}

function localIds(projectRoot: string): string[] {
	const file = issueLocalIndexPath(projectRoot);
	if (!fs.existsSync(file)) return [];
	const index = JSON.parse(fs.readFileSync(file, "utf8")) as { records: Array<{ id: string }> };
	return index.records.map((record) => record.id);
}

function authorityLogCount(fx: Fixture): number {
	const dir = path.join(issueAuthorityBasePath(fx.devRoot), ISSUE_EVENTS_DIR_BASENAME);
	if (!fs.existsSync(dir)) return 0;
	return fs.readdirSync(dir).filter((name) => name.endsWith(".jsonl")).length;
}

function snapshotTree(root: string): string[] {
	const rows: string[] = [];
	const walk = (dir: string): void => {
		const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
		for (const entry of entries) {
			const full = path.join(dir, entry.name);
			const rel = path.relative(root, full).split(path.sep).join("/");
			if (entry.isDirectory()) {
				rows.push(`D ${rel}`);
				walk(full);
			} else {
				rows.push(`F ${rel} ${sha(fs.readFileSync(full).toString("hex"))}`);
			}
		}
	};
	walk(root);
	return rows;
}

function collect(texts: string[], ui: CaptureUI): void {
	texts.push(...ui.capturedTexts);
}

function identityDisplayLines(texts: readonly string[]): string[] {
	return texts
		.flatMap((text) => text.split("\n"))
		.filter((line) => line.includes("来源项目") || line.includes("project_label="));
}

describe("T-09C2R1 exact project identity, raw text and safe display", () => {
	it.each(LABELS)("same-ID lifecycle preserves literal label %j", async (label) => {
		const fx = fixture(2);
		const clock = makeClock();
		bindFixture(fx, clock);
		const projectRoot = fx.projectRoots[0];
		const foreignRoot = fx.projectRoots[1];
		const store = storeFor(fx, projectRoot);
		const id = idFor(`lifecycle:${label}`);
		const texts: string[] = [];

		const reportUi = new CaptureUI([true]);
		const report = await handleIssueCommand(
			reportArgs(),
			depsFor(fx, projectRoot, label, "project-pm", null, store, reportUi, clock, id),
		);
		collect(texts, reportUi);
		expect(report.ok, `report code=${report.code} message=${report.message}`).toBe(true);
		expect(report.code).not.toBe("foreign-project");
		expect(report.id).toBe(id);
		expect(report.confirmed).toBe(true);

		const created = createdEvent(fx, id);
		const card = created.card;
		expect(created.kind).toBe("created");
		expect(created.project_label, "authority identity bytes").toBe(label);
		expect(card.projectLabel, "card identity bytes").toBe(label);
		expect(card.id).toBe(id);
		expect(card.title, "raw title encoded exactly once").toBe(encodeRawOracle(RAW_TITLE));
		expect(card.scene.actual.value, "raw actual encoded exactly once").toBe(encodeRawOracle(RAW_ACTUAL));
		expect(decodeCanonicalOracle(card.title)).toBe(RAW_TITLE);
		expect(escapeUntrustedText(card.title), "canonical replay fixed point").toBe(card.title);
		expect(created.card_sha256).toBe(sha(canonicalPayload(card)));
		expect(created.preview_sha256).toBe(sha(renderPreview(card)));
		expect(report.preview).toBe(renderPreview(card));
		// The canonical payload may carry exact identity bytes; only terminal
		// representations are required to be control-free.
		expect(hasUnsafeControls(renderPreview(card))).toBe(false);
		const createdLine = authorityRawLines(fx, id)[0];

		const statusUi = new CaptureUI();
		const status = await handleIssueCommand(
			`issue status ${id}`,
			depsFor(fx, projectRoot, label, "project-pm", null, store, statusUi, clock, id),
		);
		collect(texts, statusUi);
		expect(status.ok, `status code=${status.code}`).toBe(true);
		expect(status.id).toBe(id);
		expect(status.pendingQuestion).toBeNull();

		const listUi = new CaptureUI();
		const list = await handleIssueCommand(
			"issue status",
			depsFor(fx, projectRoot, label, "project-pm", null, store, listUi, clock, id),
		);
		collect(texts, listUi);
		expect(list.ok, `list code=${list.code}`).toBe(true);
		expect(list.rows.map((row) => row.id)).toEqual([id]);

		const devStore = storeFor(fx, fx.devRoot);
		const updateUi = new CaptureUI([true]);
		const update = await handleIssueCommand(
			updateArgs(id),
			depsFor(fx, fx.devRoot, label, "dev-pm", fx.devRoot, devStore, updateUi, clock, id),
		);
		collect(texts, updateUi);
		expect(update.ok, `update code=${update.code} message=${update.message}`).toBe(true);
		expect(update.writesAttempted).toContain("appendProgress");

		const questionStatusUi = new CaptureUI();
		const questionStatus = await handleIssueCommand(
			`issue status ${id}`,
			depsFor(fx, projectRoot, label, "project-pm", null, store, questionStatusUi, clock, id),
		);
		collect(texts, questionStatusUi);
		expect(questionStatus.ok).toBe(true);
		expect(questionStatus.pendingQuestion).toBe(encodeRawOracle(QUESTION));

		const replyUi = new CaptureUI([true]);
		const reply = await handleIssueCommand(
			replyArgs(id),
			depsFor(fx, projectRoot, label, "project-pm", null, store, replyUi, clock, id),
		);
		collect(texts, replyUi);
		expect(reply.ok, `reply code=${reply.code} message=${reply.message}`).toBe(true);
		expect(reply.writesAttempted).toContain("reply");

		const answeredUi = new CaptureUI();
		const answered = await handleIssueCommand(
			`issue status ${id}`,
			depsFor(fx, projectRoot, label, "project-pm", null, store, answeredUi, clock, id),
		);
		collect(texts, answeredUi);
		expect(answered.ok).toBe(true);
		expect(answered.pendingQuestion, "reply bound to real question event").toBeNull();

		const retryUi = new CaptureUI();
		const retry = await handleIssueCommand(
			`issue retry ${id}`,
			depsFor(fx, projectRoot, label, "project-pm", null, store, retryUi, clock, id),
		);
		collect(texts, retryUi);
		expect(retry.ok, `retry code=${retry.code} message=${retry.message}`).toBe(true);
		expect(retry.writesAttempted).toContain("retry");

		const events = authorityEvents(fx, id);
		expect(
			events.map((event) => event.kind),
			"one created + one question + one reply, no duplicate",
		).toEqual(["created", "dev_update", "reporter_reply"]);
		expect(authorityRawLines(fx, id)[0], "created bytes unchanged").toBe(createdLine);
		expect(localIds(projectRoot)).toEqual([id]);
		expect(localIds(foreignRoot)).toEqual([]);

		const joined = texts.join("\n");
		const identityLines = identityDisplayLines(texts);
		expect(identityLines.length, "identity display lines reached").toBeGreaterThan(0);
		expect(identityLines.join("\n")).toContain(escapeUntrustedText(label));
		expect(joined).toContain(NORMAL_UNICODE);
		if (label !== encodeRawOracle(label)) {
			for (const line of identityLines) {
				expect(line, "identity must not be raw-text encoded on display").not.toContain(encodeRawOracle(label));
			}
		}
		expect(hasUnsafeControls(joined), "no raw control/bidi reaches the terminal").toBe(false);
	});

	it("bracket and encoded-token labels stay distinct; a real foreign project gets zero writes", async () => {
		const fx = fixture(3);
		const clock = makeClock();
		bindFixture(fx, clock);
		const labelA = "project[a]";
		const labelB = `project${LIT_OPEN}a]`;
		const rootA = fx.projectRoots[0];
		const rootB = fx.projectRoots[1];
		const foreignRoot = fx.projectRoots[2];
		const storeA = storeFor(fx, rootA);
		const storeB = storeFor(fx, rootB);
		const foreignStore = storeFor(fx, foreignRoot);
		const idA = idFor("collision:a");
		const idB = idFor("collision:b");
		const texts: string[] = [];

		const uiA = new CaptureUI([true]);
		const reportA = await handleIssueCommand(
			reportArgs(),
			depsFor(fx, rootA, labelA, "project-a-pm", null, storeA, uiA, clock, idA),
		);
		collect(texts, uiA);
		expect(reportA.ok, `A report code=${reportA.code}`).toBe(true);
		expect(createdEvent(fx, idA).project_label).toBe(labelA);

		const uiB = new CaptureUI([true]);
		const reportB = await handleIssueCommand(
			reportArgs(),
			depsFor(fx, rootB, labelB, "project-b-pm", null, storeB, uiB, clock, idB),
		);
		collect(texts, uiB);
		expect(reportB.ok, `B report code=${reportB.code}`).toBe(true);
		expect(createdEvent(fx, idB).project_label).toBe(labelB);
		expect(labelA).not.toBe(labelB);
		expect(idA).not.toBe(idB);

		const listUiA = new CaptureUI();
		const listA = await handleIssueCommand(
			"issue status",
			depsFor(fx, rootA, labelA, "project-a-pm", null, storeA, listUiA, clock, idA),
		);
		collect(texts, listUiA);
		expect(listA.ok).toBe(true);
		expect(listA.rows.map((row) => row.id)).toEqual([idA]);

		const listUiB = new CaptureUI();
		const listB = await handleIssueCommand(
			"issue status",
			depsFor(fx, rootB, labelB, "project-b-pm", null, storeB, listUiB, clock, idB),
		);
		collect(texts, listUiB);
		expect(listB.ok).toBe(true);
		expect(listB.rows.map((row) => row.id)).toEqual([idB]);

		const before = snapshotTree(fx.top);
		const beforeA = authorityRawLines(fx, idA)[0];
		const beforeB = authorityRawLines(fx, idB)[0];
		const foreignResults: IssueCommandResult[] = [];
		const foreignUis: CaptureUI[] = [];

		const crossStatusUi = new CaptureUI();
		foreignUis.push(crossStatusUi);
		foreignResults.push(
			await handleIssueCommand(
				`issue status ${idB}`,
				depsFor(fx, rootA, labelA, "project-a-pm", null, storeA, crossStatusUi, clock, idA),
			),
		);

		const foreignLabel = "foreign-project";
		const negativeCommands = [
			`issue status ${idA}`,
			replyArgs(idA, "foreign reply"),
			`issue retry ${idA}`,
			"issue status",
		];
		for (const command of negativeCommands) {
			const ui = new CaptureUI();
			foreignUis.push(ui);
			foreignResults.push(
				await handleIssueCommand(
					command,
					depsFor(fx, foreignRoot, foreignLabel, "foreign-pm", null, foreignStore, ui, clock, idA),
				),
			);
		}

		const mismatchedStatusUi = new CaptureUI();
		foreignUis.push(mismatchedStatusUi);
		const mismatchedStatus = await handleIssueCommand(
			`issue status ${idA}`,
			depsFor(fx, rootA, labelB, "mismatched-pm", null, storeA, mismatchedStatusUi, clock, idA),
		);
		foreignResults.push(mismatchedStatus);
		expect(mismatchedStatus.code, "strict label identity gate remains").toBe("foreign-project");

		for (const ui of foreignUis) collect(texts, ui);
		const foreignListIndex = foreignResults.length - 2;
		for (const [index, result] of foreignResults.entries()) {
			if (index !== foreignListIndex) expect(result.ok, `refusal code=${result.code}`).toBe(false);
		}
		for (const ui of foreignUis) expect(ui.confirmCalls, "no foreign confirmation/write").toBe(0);
		const foreignList = foreignResults[foreignListIndex];
		expect(foreignList.rows, "foreign no-ID list exposes no target").toEqual([]);

		expect(snapshotTree(fx.top), "all refused reads/writes leave byte-identical tree").toEqual(before);
		expect(authorityRawLines(fx, idA)[0]).toBe(beforeA);
		expect(authorityRawLines(fx, idB)[0]).toBe(beforeB);
		expect(authorityLogCount(fx)).toBe(2);
		expect(localIds(rootA)).toEqual([idA]);
		expect(localIds(rootB)).toEqual([idB]);
		expect(localIds(foreignRoot)).toEqual([]);
		expect(hasUnsafeControls(texts.join("\n"))).toBe(false);
	});
});
