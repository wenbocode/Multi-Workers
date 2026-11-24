/**
 * T-09E (R05) — dynamic regression for same-ID question/reply folding by
 * STABLE AUTHORITY EVENT IDENTITY (independent review finding F3).
 *
 * This suite uses a REAL temp dev repo + project, an injected pointer, real
 * O_EXCL locks, real JSONL hash chains and the real IssueStore/model. Nothing
 * is a static derivation: every question, reply and status/list read goes
 * through the production write/replay path.
 *
 * The bug (pre-fix `pendingQuestion`): a question was considered answered by
 * ANY reply whose clock is >= the question time, ignoring `inReplyTo`; the
 * store accepted a reference to ANY event of the issue (or null). So a late
 * reply to an OLD question (Q1) wrongly cleared the NEWER pending question
 * (Q2). The fix binds "answered" to the sha256 of the dev_update event that
 * owns the question, attached to the in-memory replay projection only.
 *
 * Coverage: multiple questions, identical timestamps, later no-question
 * progress, late old-question reply, null/created/no-question/time/duplicate
 * references, explicit Q2 answer, old-question-still-pending rule, cross-issue
 * refusal, created-byte immutability / append-only growth, and consistency of
 * model pendingQuestion, summarizeForList.needsReply, store.status/list and the
 * user-visible status rendering.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { renderIssueStatusText } from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import {
	type Confirmation,
	type IssueCard,
	type IssueDraft,
	type IssuePreparation,
	observedObservation,
	pendingQuestion,
	prepareIssue,
	summarizeForList,
	unknownObservation,
	userObservation,
} from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	bindIssueDevRoot,
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	type IssueAuthorityEvent,
	type IssueEventSource,
	type IssueProgressFields,
	type IssueReplyFields,
	IssueStore,
	type IssueStoreActor,
	type IssueStoreOptions,
	issueAuthorityLogPath,
	newIssueId,
	renderDevUpdatePreview,
	renderReporterReplyPreview,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";

// ── Synthetic constants ──────────────────────────────────────────────────────

const OCCURRED = "2026-11-12T14:02:11+08:00";
const SUBMITTED = "2026-11-12T21:10:00+08:00";
const OBSERVED_AT = "2026-11-12T21:09:58+08:00";
const CONFIRMED_AT = "2026-11-12T21:15:00+08:00";
const T1 = "2026-11-12T22:00:00+08:00";
const T2 = "2026-11-12T23:00:00+08:00";
const T3 = "2026-11-13T09:00:00+08:00";
const T4 = "2026-11-13T10:00:00+08:00";
const T5 = "2026-11-13T11:00:00+08:00";
const T6 = "2026-11-13T12:00:00+08:00";
const T7 = "2026-11-13T13:00:00+08:00";

const Q1 = "Q1-请补充重启后的原始报错";
const Q2 = "Q2-请补充故障时 MW 版本";

const temporaryRoots: string[] = [];
afterEach(() => {
	for (const dir of temporaryRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

// ── Fixture (mirrors issue-store.test.ts: real temp roots + bound pointer) ──

interface Fixture {
	top: string;
	pointerFile: string;
	devRoot: string;
	projectA: string;
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
	const top = fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-qalink-"));
	temporaryRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	makeDevRepo(devRoot);
	const projectA = path.join(top, "project-a");
	fs.mkdirSync(path.join(projectA, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(projectA, ".agenticdoc", "goal.md"), "# Project A goal\n", "utf8");
	const pointerFile = path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME);
	const bound = bindIssueDevRoot({
		callerProjectRoot: devRoot,
		candidateRoot: devRoot,
		userConfirmed: true,
		pointerFile,
		now: () => new Date("2026-11-12T12:00:00.000Z"),
	});
	if (!bound.ok) throw new Error(`fixture bind failed: ${bound.code} ${bound.reason}`);
	return { top, pointerFile, devRoot, projectA };
}

function pmActor(projectRoot: string, by = "pm-A"): IssueStoreActor {
	return {
		role: "pm",
		scope: "project",
		projectRoot,
		projectLabel: "project-A",
		by,
		trustedWindow: true,
		writeAuthorized: true,
	};
}

function devActor(devRoot: string, by = "mw-dev-pm"): IssueStoreActor {
	return {
		role: "pm",
		scope: "dev",
		projectRoot: devRoot,
		projectLabel: "mw-dev",
		by,
		trustedWindow: true,
		writeAuthorized: true,
	};
}

function store(fx: Fixture, projectRoot: string, overrides: Partial<IssueStoreOptions> = {}): IssueStore {
	return new IssueStore({ projectRoot, env: {}, pointerFile: fx.pointerFile, ...overrides });
}

function baseDraft(id: string): IssueDraft {
	return {
		id,
		title: "R05 追问/回复事件身份回归",
		projectLabel: "project-A",
		component: unknownObservation(),
		occurredAt: userObservation(OCCURRED, SUBMITTED),
		trigger: userObservation("执行 /mw issue status"),
		precondition: userObservation("多个 dev_update 与 reply"),
		expected: userObservation("最新未答追问始终可见"),
		actual: userObservation("晚回复旧问会误清新问"),
		impact: userObservation("追问丢失"),
		reproductionSteps: userObservation("1. 提两个问题；2. 晚回复旧问；3. 查询"),
		reproductionFrequency: "每次",
		errorExcerpt: userObservation("ERROR R05 synthetic"),
		environmentAtFailure: {
			mwVersion: userObservation("0.12.2", OCCURRED),
			piVersion: unknownObservation(),
			platform: userObservation("Windows 11"),
			windowType: userObservation("tui"),
		},
		observedEnvironment: {
			mwVersion: observedObservation("0.12.4", OBSERVED_AT),
			piVersion: unknownObservation(),
			platform: observedObservation("Windows 11", OBSERVED_AT),
			windowType: unknownObservation(),
			bundleStatus: observedObservation("fresh", OBSERVED_AT),
			serveStatus: observedObservation("fresh", OBSERVED_AT),
		},
		diagnosticCandidates: [],
		selectedFragmentIds: [],
	};
}

function makeSubmission(id: string): {
	id: string;
	preparation: IssuePreparation;
	confirmation: Confirmation;
} {
	const preparation = prepareIssue(baseDraft(id), {
		submittedAt: SUBMITTED,
		environmentObservedAt: OBSERVED_AT,
	});
	const confirmation: Confirmation = {
		confirmed: true,
		confirmedAt: CONFIRMED_AT,
		previewSha256: preparation.previewSha256,
	};
	return { id, preparation, confirmation };
}

async function submit(projectStore: IssueStore, actor: IssueStoreActor): Promise<string> {
	const sub = makeSubmission(newIssueId());
	const result = await projectStore.submit({
		actor,
		preparation: sub.preparation,
		confirmation: sub.confirmation,
		knownSecrets: [],
	});
	expect(result.ok).toBe(true);
	expect(result.code).toBe("submitted");
	return sub.id;
}

// ── Write/read helpers ────────────────────────────────────────────────────────

function progressRequest(actor: IssueStoreActor, id: string, at: string, fields: IssueProgressFields) {
	const source: IssueEventSource = "dev-pm";
	const preview = renderDevUpdatePreview(fields, { id, at, source, by: actor.by });
	return {
		actor,
		id,
		update: fields,
		preview,
		confirmation: { confirmed: true, confirmedAt: at, previewSha256: sha256(preview) } as Confirmation,
		knownSecrets: [] as readonly string[],
	};
}

function replyRequest(actor: IssueStoreActor, id: string, at: string, text: string, inReplyTo: string | null) {
	const fields: IssueReplyFields = { text, source: "user", inReplyTo };
	const source: IssueEventSource = "project-pm";
	const preview = renderReporterReplyPreview(fields, { id, at, source, by: actor.by });
	return {
		actor,
		id,
		reply: fields,
		preview,
		confirmation: { confirmed: true, confirmedAt: at, previewSha256: sha256(preview) } as Confirmation,
		knownSecrets: [] as readonly string[],
	};
}

function questionFields(question: string | null): IssueProgressFields {
	return {
		status: "修复中",
		statusNote: "定位中，等待补充",
		nextAction: "补充回归用例",
		fixCommit: null,
		releaseVersion: null,
		questionToReporter: question,
	};
}

async function ask(devStore: IssueStore, actorDev: IssueStoreActor, id: string, at: string, question: string) {
	const result = await devStore.appendProgress(progressRequest(actorDev, id, at, questionFields(question)));
	expect(result.ok).toBe(true);
	expect(result.code).toBe("written");
}

async function progress(devStore: IssueStore, actorDev: IssueStoreActor, id: string, at: string) {
	const fields: IssueProgressFields = questionFields(null);
	fields.status = "已修复";
	fields.statusNote = "修复已合并（无新问题）";
	fields.fixCommit = "abc1234";
	const result = await devStore.appendProgress(progressRequest(actorDev, id, at, fields));
	expect(result.ok).toBe(true);
	expect(result.code).toBe("written");
}

async function reply(
	projectStore: IssueStore,
	actorA: IssueStoreActor,
	id: string,
	at: string,
	inReplyTo: string | null,
) {
	return projectStore.reply(replyRequest(actorA, id, at, "补充现场信息（用户已确认）", inReplyTo));
}

function authorityLines(fx: Fixture, id: string): string[] {
	const file = issueAuthorityLogPath(fx.devRoot, id);
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.length > 0);
}

function readEvents(fx: Fixture, id: string): IssueAuthorityEvent[] {
	return authorityLines(fx, id).map((line) => JSON.parse(line) as IssueAuthorityEvent);
}

function hashForQuestion(fx: Fixture, id: string, question: string): string {
	const event = readEvents(fx, id).find(
		(item) => item.kind === "dev_update" && item.update.questionToReporter === question,
	);
	if (event === undefined) throw new Error(`missing question event: ${question}`);
	return event.sha256;
}

function createdHash(fx: Fixture, id: string): string {
	const event = readEvents(fx, id).find((item) => item.kind === "created");
	if (event === undefined) throw new Error("missing created event");
	return event.sha256;
}

function noQuestionUpdateHash(fx: Fixture, id: string): string {
	const event = readEvents(fx, id).find(
		(item) => item.kind === "dev_update" && item.update.questionToReporter === null,
	);
	if (event === undefined) throw new Error("missing no-question dev_update event");
	return event.sha256;
}

// ── Setup + the shared consistency assertion ────────────────────────────────

interface Context {
	fx: Fixture;
	projectStore: IssueStore;
	devStore: IssueStore;
	actorA: IssueStoreActor;
	actorDev: IssueStoreActor;
	id: string;
}

async function setup(): Promise<Context> {
	const fx = fixture();
	const projectStore = store(fx, fx.projectA);
	const devStore = store(fx, fx.devRoot);
	const actorA = pmActor(fx.projectA);
	const actorDev = devActor(fx.devRoot);
	const id = await submit(projectStore, actorA);
	return { fx, projectStore, devStore, actorA, actorDev, id };
}

/** ONE shared assertion: model pendingQuestion, summarizeForList.needsReply,
 * store.status.pendingQuestion, store.list[].needsReply and the user-visible
 * "最近未回复追问" section must all report the SAME pending question. */
function expectViews(ctx: Context, expected: string | null): void {
	const status = ctx.projectStore.status({ actor: ctx.actorA, id: ctx.id });
	expect(status.ok).toBe(true);
	expect(status.card).not.toBeNull();
	const card: IssueCard | null = status.card;
	if (card === null) throw new Error("status.card is null on a live authority card");
	expect(status.pendingQuestion).toBe(expected);
	expect(pendingQuestion(card)).toBe(expected);
	expect(summarizeForList(card).needsReply).toBe(expected !== null);
	const row = ctx.projectStore.list({ actor: ctx.actorA }).rows.find((item) => item.id === ctx.id);
	expect(row?.needsReply).toBe(expected !== null);
	const userText = renderIssueStatusText(status);
	const section = userText.split("## 最近未回复追问")[1]?.split("\n## ")[0] ?? "";
	expect(section).toContain(expected === null ? "- 无" : `- ${expected}`);
}

/** Verify the created event bytes and the whole pre-existing log survive every
 * append, that seqs are 1..N, and that the in-memory identity projection never
 * leaked to disk. */
function expectAppendOnly(ctx: Context, before: readonly string[]): void {
	const after = authorityLines(ctx.fx, ctx.id);
	expect(before.length).toBeGreaterThan(0);
	// Strict prefix: earlier lines are byte-identical, later events only appended.
	expect(after.slice(0, before.length)).toEqual([...before]);
	expect(after.length).toBeGreaterThan(before.length);
	expect(after[0]).toBe(before[0]); // created raw bytes never rewritten
	const seqs = after.map((line) => (JSON.parse(line) as IssueAuthorityEvent).seq);
	expect(seqs).toEqual(after.map((_line, index) => index + 1));
	// The identity map is projection-only; no schema/history rewrite on disk.
	expect(after.join("\n")).not.toContain("questionEventHashes");
}

// ── Dynamic reproductions ────────────────────────────────────────────────────

describe("R05: same-ID question/reply folded by stable dev_update event hash", () => {
	it("A: two questions; a LATE reply to Q1 keeps Q2 pending; explicit/duplicate reply to Q2 clears it; old Q1 stays superseded; created bytes immutable", async () => {
		const ctx = await setup();
		const createdBefore = authorityLines(ctx.fx, ctx.id);

		await ask(ctx.devStore, ctx.actorDev, ctx.id, T1, Q1);
		await ask(ctx.devStore, ctx.actorDev, ctx.id, T2, Q2);
		const h1 = hashForQuestion(ctx.fx, ctx.id, Q1);
		const h2 = hashForQuestion(ctx.fx, ctx.id, Q2);
		expect(h1).not.toBe(h2);
		// Newest question Q2 is pending across every view.
		expectViews(ctx, Q2);

		// A reply whose CLOCK is later than Q2, but which names Q1's event, must
		// NOT clear Q2 (this is the F3 bug: the old model used reply.at>=Q2.at).
		const late = await reply(ctx.projectStore, ctx.actorA, ctx.id, T5, h1);
		expect(late.ok).toBe(true);
		expectViews(ctx, Q2);

		// Only a reply naming Q2's exact event hash clears Q2.
		const answerQ2 = await reply(ctx.projectStore, ctx.actorA, ctx.id, T6, h2);
		expect(answerQ2.ok).toBe(true);
		expectViews(ctx, null);

		// A duplicate answer to Q2 is idempotent and Q1 is NOT re-surfaced: the
		// single-newest-question rule keeps older questions superseded.
		const duplicate = await reply(ctx.projectStore, ctx.actorA, ctx.id, T7, h2);
		expect(duplicate.ok).toBe(true);
		expectViews(ctx, null);

		expectAppendOnly(ctx, createdBefore);
	});

	it("B: two questions with an IDENTICAL timestamp are still distinguished by their event hashes", async () => {
		const ctx = await setup();
		const createdBefore = authorityLines(ctx.fx, ctx.id);

		// Q1 and Q2 share the exact same `at`; only their hash-chain identity
		// (sha256) differs, so a clock could never tell them apart.
		await ask(ctx.devStore, ctx.actorDev, ctx.id, T2, Q1);
		await ask(ctx.devStore, ctx.actorDev, ctx.id, T2, Q2);
		const h1 = hashForQuestion(ctx.fx, ctx.id, Q1);
		const h2 = hashForQuestion(ctx.fx, ctx.id, Q2);
		expect(h1).not.toBe(h2);
		expectViews(ctx, Q2);

		// Reply to the old/same-time Q1 -> Q2 still pending.
		const oldReply = await reply(ctx.projectStore, ctx.actorA, ctx.id, T5, h1);
		expect(oldReply.ok).toBe(true);
		expectViews(ctx, Q2);

		// Reply to Q2 by hash -> cleared.
		const answerQ2 = await reply(ctx.projectStore, ctx.actorA, ctx.id, T6, h2);
		expect(answerQ2.ok).toBe(true);
		expectViews(ctx, null);

		expectAppendOnly(ctx, createdBefore);
	});

	it("C: later dev updates WITHOUT a question never swallow a pending question; an explicit reply still clears it", async () => {
		const ctx = await setup();

		await ask(ctx.devStore, ctx.actorDev, ctx.id, T1, Q1);
		// Two follow-up progress updates carry NO question (fix + release).
		await progress(ctx.devStore, ctx.actorDev, ctx.id, T2);
		await progress(ctx.devStore, ctx.actorDev, ctx.id, T3);
		const h1 = hashForQuestion(ctx.fx, ctx.id, Q1);
		// The single question survives the newer no-question updates.
		expectViews(ctx, Q1);

		const answer = await reply(ctx.projectStore, ctx.actorA, ctx.id, T5, h1);
		expect(answer.ok).toBe(true);
		expectViews(ctx, null);
	});

	it("D: null / created / no-question-update / time / duplicate references are mere supplements and never clear the newest question", async () => {
		const ctx = await setup();
		const createdBefore = authorityLines(ctx.fx, ctx.id);

		await ask(ctx.devStore, ctx.actorDev, ctx.id, T1, Q1);
		await ask(ctx.devStore, ctx.actorDev, ctx.id, T2, Q2);
		await progress(ctx.devStore, ctx.actorDev, ctx.id, T3); // no-question update after Q2
		const h1 = hashForQuestion(ctx.fx, ctx.id, Q1);
		const q2Hash = hashForQuestion(ctx.fx, ctx.id, Q2);
		const cHash = createdHash(ctx.fx, ctx.id);
		const nHash = noQuestionUpdateHash(ctx.fx, ctx.id);
		expectViews(ctx, Q2);

		// null reference (a no-link supplement).
		const r1 = await reply(ctx.projectStore, ctx.actorA, ctx.id, T4, null);
		expect(r1.ok).toBe(true);
		expectViews(ctx, Q2);

		// reference to the created event (allowed, but not a question).
		const r2 = await reply(ctx.projectStore, ctx.actorA, ctx.id, T5, cHash);
		expect(r2.ok).toBe(true);
		expectViews(ctx, Q2);

		// reference to a dev_update that carries no question.
		const r3 = await reply(ctx.projectStore, ctx.actorA, ctx.id, T6, nHash);
		expect(r3.ok).toBe(true);
		expectViews(ctx, Q2);

		// time-based reference to Q2's `at` (a clock, NOT the stable event hash):
		// a valid stored supplement that must NOT be mistaken for an answer.
		const r4 = await reply(ctx.projectStore, ctx.actorA, ctx.id, T7, T2);
		expect(r4.ok).toBe(true);
		expectViews(ctx, Q2);

		// A reply to the OLD Q1 (also a supplement with respect to Q2).
		const r5 = await reply(ctx.projectStore, ctx.actorA, ctx.id, T7, h1);
		expect(r5.ok).toBe(true);
		expectViews(ctx, Q2);

		// Only the exact Q2 event hash clears the pending question.
		const answer = await reply(ctx.projectStore, ctx.actorA, ctx.id, T7, q2Hash);
		expect(answer.ok).toBe(true);
		expectViews(ctx, null);

		expectAppendOnly(ctx, createdBefore);
	});

	it("E: a cross-issue inReplyTo is refused and writes nothing; created bytes stay unchanged", async () => {
		const ctx = await setup();
		// A second, independent issue in the same project/dev root.
		const id2 = await submit(ctx.projectStore, ctx.actorA);
		await ask(ctx.devStore, ctx.actorDev, ctx.id, T1, Q1);
		const before = authorityLines(ctx.fx, ctx.id);
		const foreignHash = createdHash(ctx.fx, id2);
		expectViews(ctx, Q1);

		const refused = await reply(ctx.projectStore, ctx.actorA, ctx.id, T5, foreignHash);
		expect(refused.ok).toBe(false);
		expect(refused.code).toBe("invalid-input");
		// No event appended to the target issue; created bytes untouched.
		expect(authorityLines(ctx.fx, ctx.id)).toEqual([...before]);
		expectViews(ctx, Q1);
	});

	it("F: event identities equal the real hash-chain sha256 and are projection-only (never persisted)", async () => {
		const ctx = await setup();
		await ask(ctx.devStore, ctx.actorDev, ctx.id, T1, Q1);
		await ask(ctx.devStore, ctx.actorDev, ctx.id, T2, Q2);
		const h2 = hashForQuestion(ctx.fx, ctx.id, Q2);
		await reply(ctx.projectStore, ctx.actorA, ctx.id, T6, h2);

		const status = ctx.projectStore.status({ actor: ctx.actorA, id: ctx.id });
		expect(status.ok).toBe(true);
		if (status.card === null) throw new Error("status.card is null");
		// The projection carries one identity per dev_update, aligned to timeline.
		expect(status.card.questionEventHashes).toHaveLength(status.card.devTimeline.length);
		const updateEvents = readEvents(ctx.fx, ctx.id).filter((item) => item.kind === "dev_update");
		expect(status.card.questionEventHashes).toEqual(updateEvents.map((item) => item.sha256));
		// Disk history: created card timeline empty, no identity field anywhere.
		const raw = authorityLines(ctx.fx, ctx.id).join("\n");
		expect(raw).not.toContain("questionEventHashes");
		const created = readEvents(ctx.fx, ctx.id).find((item) => item.kind === "created");
		if (created === undefined || created.kind !== "created") throw new Error("missing created event");
		expect(created.card.devTimeline).toEqual([]);
		expect(created.card.reporterReplies).toEqual([]);
		expectViews(ctx, null);
	});
});
