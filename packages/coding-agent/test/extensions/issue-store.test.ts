/**
 * issue-store.test.ts — T-03 of key `mw-issue-feedback`: offline two-project
 * storage evidence for AC-001/002/003/004/006 and VC-001/002/003/004/005/006/007.
 *
 * This suite uses synthetic temp dev repos/projects and an injected pointer
 * file. It never reads or writes the real machine pointer, the real shared
 * feedback table, a provider, a network endpoint, a service or a bundle. The
 * independent child processes import only the two accepted TS modules with
 * Node's strip-only loader; they exercise the real O_EXCL locks and JSONL
 * append path rather than a mocked store.
 *
 * T-03 claims store-level L2 evidence only. T-04 UI wiring, T-05 hot/restart
 * semantics and T-06 independent E2E acceptance remain separate tasks.
 */

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	type Confirmation,
	canonicalPayload,
	type IssueCard,
	type IssueDraft,
	type IssuePreparation,
	type LocalEvidence,
	NOT_VERIFIED_PHRASE,
	observedObservation,
	prepareIssue,
	REDACTION_MARK,
	renderPreview,
	unknownObservation,
	userObservation,
	VERIFIED_PHRASE,
} from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	bindIssueDevRoot,
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	ISSUE_DISPLAY_NOT_SUBMITTED,
	ISSUE_DISPLAY_SUBMITTED,
	ISSUE_DISPLAY_VERIFY_PENDING,
	ISSUE_STORE_ENTRY_ONLY_NOTICE,
	type IssueAuthorityEvent,
	type IssueEventSource,
	type IssueLocalIndex,
	type IssueProgressFields,
	type IssueReplyFields,
	IssueStore,
	type IssueStoreActor,
	IssueStoreError,
	type IssueStoreOptions,
	issueAuthorityBasePath,
	issueAuthorityLockPath,
	issueAuthorityLogPath,
	issueLocalBasePath,
	issueLocalIndexPath,
	issuePendingCopyPath,
	newIssueId,
	renderDevUpdatePreview,
	renderReporterReplyPreview,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";

// ── Synthetic constants ──────────────────────────────────────────────────────

const START_CWD = process.cwd();
const OCCURRED = "2026-11-12T14:02:11+08:00";
const SUBMITTED = "2026-11-12T21:10:00+08:00";
const OBSERVED_AT = "2026-11-12T21:09:58+08:00";
const CONFIRMED_AT = "2026-11-12T21:15:00+08:00";
const T1 = "2026-11-12T22:00:00+08:00";
const T2 = "2026-11-12T23:00:00+08:00";
const T3 = "2026-11-13T09:00:00+08:00";
const T4 = "2026-11-13T10:00:00+08:00";
const T5 = "2026-11-13T11:00:00+08:00";

const SECRET_A = "SENTINEL-APIKEY-9f3a2b7c";
const SECRET_B = "SUPERSECRET-VALUE-42";
const UNCONFIRMED = "UNCONFIRMED-RAW-SENTINEL-77";
const LONG_STEP = `1. 运行 /mw status 观察 serve 行；2. 重启；3. 再查询 ${"step-".repeat(120)} END-OF-REPRO-STEPS`;
const LONG_ERROR = `ERROR serve-stale: ${"E".repeat(500)} END-OF-KEY-ERROR`;
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
	env: NodeJS.ProcessEnv;
}

interface SubmissionFixture {
	id: string;
	draft: IssueDraft;
	preparation: IssuePreparation;
	confirmation: Confirmation;
	knownSecrets: readonly string[];
}

interface SubmissionOptions {
	id?: string;
	projectLabel?: string;
	title?: string;
	actual?: string;
	confirmed?: boolean;
	confirmedAt?: string;
	knownSecrets?: readonly string[];
}

function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
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
	const top = fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-store-"));
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
	const pointerFile = path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME);
	const bound = bindIssueDevRoot({
		callerProjectRoot: devRoot,
		candidateRoot: devRoot,
		userConfirmed: true,
		pointerFile,
		now: () => new Date("2026-11-12T12:00:00.000Z"),
	});
	if (!bound.ok) throw new Error(`fixture bind failed: ${bound.code} ${bound.reason}`);
	return {
		top,
		home,
		pointerFile,
		missingPointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, "missing-pointer.json"),
		devRoot,
		projectA,
		projectB,
		env: {},
	};
}

/** Byte-level tree snapshot (no mtimes, no symlink following). */
function snapshot(root: string): string[] {
	if (!fs.existsSync(root)) return ["<absent>"];
	const out: string[] = [];
	const walk = (dir: string): void => {
		const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
		for (const entry of entries) {
			const full = path.join(dir, entry.name);
			const rel = path.relative(root, full);
			if (entry.isSymbolicLink()) out.push(`l:${rel}:${fs.readlinkSync(full)}`);
			else if (entry.isDirectory()) {
				out.push(`d:${rel}`);
				walk(full);
			} else {
				const bytes = fs.readFileSync(full);
				out.push(`f:${rel}:${bytes.length}:${bytes.toString("utf8")}`);
			}
		}
	};
	walk(root);
	return out;
}

function filesUnder(root: string): string[] {
	if (!fs.existsSync(root)) return [];
	const out: string[] = [];
	const walk = (dir: string): void => {
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) walk(full);
			else if (entry.isFile()) out.push(full);
		}
	};
	walk(root);
	return out;
}

function allTextUnder(root: string): string {
	return filesUnder(root)
		.map((file) => fs.readFileSync(file, "utf8"))
		.join("\n");
}

function eventsDir(fx: Fixture): string {
	return path.join(issueAuthorityBasePath(fx.devRoot), "events");
}

function pendingDir(projectRoot: string): string {
	return path.join(issueLocalBasePath(projectRoot), "pending");
}

function authorityLogBytes(fx: Fixture, id: string): Buffer {
	return fs.readFileSync(issueAuthorityLogPath(fx.devRoot, id));
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

function readIndex(projectRoot: string): IssueLocalIndex | null {
	const file = issueLocalIndexPath(projectRoot);
	if (!fs.existsSync(file)) return null;
	return JSON.parse(fs.readFileSync(file, "utf8")) as IssueLocalIndex;
}

function countPending(projectRoot: string): number {
	if (!fs.existsSync(pendingDir(projectRoot))) return 0;
	return fs.readdirSync(pendingDir(projectRoot)).filter((name) => name.endsWith(".json")).length;
}

function countAuthorityLogs(fx: Fixture): number {
	if (!fs.existsSync(eventsDir(fx))) return 0;
	return fs.readdirSync(eventsDir(fx)).filter((name) => name.endsWith(".jsonl")).length;
}

function baseDraft(id: string, projectLabel: string, title?: string, actual?: string): IssueDraft {
	return {
		id,
		title: title ?? "/mw status 重启后显示旧 serve",
		projectLabel,
		component: unknownObservation(),
		occurredAt: userObservation(OCCURRED, SUBMITTED),
		trigger: userObservation("执行 /mw status 后重启 serve"),
		precondition: userObservation("serve 已运行超过一小时"),
		expected: userObservation("显示当前 serve 的 PID 与启动时间"),
		actual: userObservation(actual ?? "仍显示上一次启动的旧 PID"),
		impact: userObservation("误判 serve 未重启，卡住排障"),
		reproductionSteps: userObservation(LONG_STEP),
		reproductionFrequency: "偶发",
		errorExcerpt: userObservation(`${LONG_ERROR} Bearer ${SECRET_B}`),
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
			serveStatus: observedObservation("stale", OBSERVED_AT),
		},
		diagnosticCandidates: [
			{ id: "f1", kind: "error", text: `E123: api_key=${SECRET_A} 原始报错` },
			{ id: "f2", kind: "log", text: "用户选择的最小日志行 23:09:58" },
			{ id: "f3", kind: "log", text: `${UNCONFIRMED} 整段会话原文（未选择）` },
		],
		selectedFragmentIds: ["f1", "f2"],
	};
}

function makeSubmission(options: SubmissionOptions = {}): SubmissionFixture {
	const id = options.id ?? newIssueId();
	const projectLabel = options.projectLabel ?? "project-A";
	const knownSecrets = options.knownSecrets ?? [SECRET_A, SECRET_B];
	const draft = baseDraft(id, projectLabel, options.title, options.actual);
	const preparation = prepareIssue(draft, {
		submittedAt: SUBMITTED,
		environmentObservedAt: OBSERVED_AT,
		knownSecrets,
	});
	const confirmation: Confirmation = {
		confirmed: options.confirmed ?? true,
		confirmedAt: options.confirmedAt ?? CONFIRMED_AT,
		previewSha256: preparation.previewSha256,
	};
	return { id, draft, preparation, confirmation, knownSecrets };
}

/** A forged preparation that would pass confirmIssue's hash checks but carries
 * a high-confidence credential shape. The store must reject it before any I/O. */
function forgedCredentialSubmission(id: string, projectLabel = "project-A"): SubmissionFixture {
	const base = makeSubmission({ id, projectLabel });
	const card: IssueCard = {
		...base.preparation.card,
		scene: {
			...base.preparation.card.scene,
			errorExcerpt: {
				...base.preparation.card.scene.errorExcerpt,
				value: "sk-abcdefghijklmnopqrstuvwxyz",
			},
		},
	};
	const preview = renderPreview(card);
	const previewSha = sha256(preview);
	const preparation: IssuePreparation = {
		...base.preparation,
		card,
		preview,
		previewSha256: previewSha,
		submissionDigest: sha256(canonicalPayload(card)).slice(0, 16),
		redactions: 0,
		notes: [],
	};
	return {
		id,
		draft: base.draft,
		preparation,
		confirmation: { confirmed: true, confirmedAt: CONFIRMED_AT, previewSha256: previewSha },
		knownSecrets: [],
	};
}

function pmActor(projectRoot: string, projectLabel = "project-A", by = "pm-A"): IssueStoreActor {
	return {
		role: "pm",
		scope: "project",
		projectRoot,
		projectLabel,
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

function localEvidence(): LocalEvidence {
	return {
		localVersion: "0.12.2",
		bundleStale: false,
		serveStale: false,
		entrypointInstalled: false,
		collectedAt: T5,
	};
}

function progressRequest(
	actor: IssueStoreActor,
	id: string,
	at: string,
	fields: IssueProgressFields,
): {
	actor: IssueStoreActor;
	id: string;
	update: IssueProgressFields;
	preview: string;
	confirmation: Confirmation;
	knownSecrets: readonly string[];
} {
	const source: IssueEventSource = "dev-pm";
	const preview = renderDevUpdatePreview(fields, { id, at, source, by: actor.by });
	return {
		actor,
		id,
		update: fields,
		preview,
		confirmation: { confirmed: true, confirmedAt: at, previewSha256: sha256(preview) },
		knownSecrets: [],
	};
}

function replyRequest(
	actor: IssueStoreActor,
	id: string,
	at: string,
	text: string,
	inReplyTo: string | null,
): {
	actor: IssueStoreActor;
	id: string;
	reply: IssueReplyFields;
	preview: string;
	confirmation: Confirmation;
	knownSecrets: readonly string[];
} {
	const fields: IssueReplyFields = { text, source: "user", inReplyTo };
	const source: IssueEventSource = "project-pm";
	const preview = renderReporterReplyPreview(fields, { id, at, source, by: actor.by });
	return {
		actor,
		id,
		reply: fields,
		preview,
		confirmation: { confirmed: true, confirmedAt: at, previewSha256: sha256(preview) },
		knownSecrets: [],
	};
}

function expectStoreError(action: () => unknown, code: IssueStoreError["code"]): IssueStoreError {
	try {
		action();
	} catch (error) {
		if (!(error instanceof IssueStoreError)) throw error;
		expect(error.code).toBe(code);
		return error;
	}
	throw new Error(`expected IssueStoreError ${code}`);
}

// ── Independent child process: static imports, real locks, no mocks ─────────

const ISSUE_MODEL_URL = new URL("../../src/extensions/agent-team-loop/shared/issue-model.ts", import.meta.url).href;
const ISSUE_STORE_URL = new URL("../../src/extensions/agent-team-loop/shared/issue-store.ts", import.meta.url).href;

const CHILD_SOURCE = `
import * as fs from 'node:fs';
import { prepareIssue, unknownObservation, userObservation, observedObservation } from ${JSON.stringify(ISSUE_MODEL_URL)};
import { IssueStore, issueTextSha256, renderDevUpdatePreview } from ${JSON.stringify(ISSUE_STORE_URL)};

const SUBMITTED = '2026-11-12T21:10:00+08:00';
const OBSERVED_AT = '2026-11-12T21:09:58+08:00';
const options = JSON.parse(process.env.MW_ISSUE_CHILD_OPTIONS || '{}');
const report = (payload) => {
	const text = JSON.stringify(payload);
	process.stdout.write(text);
	fs.writeFileSync(options.resultFlag, text, 'utf8');
};
const childDraft = (id, label, title) => ({
	id: id,
	title: title,
	projectLabel: label,
	component: unknownObservation(),
	occurredAt: userObservation('2026-11-12T14:02:11+08:00', SUBMITTED),
	trigger: userObservation('执行 /mw status 后重启 serve'),
	precondition: userObservation('serve 已运行超过一小时'),
	expected: userObservation('显示当前 serve 的 PID'),
	actual: userObservation('仍显示上一次启动的旧 PID'),
	impact: userObservation('误判 serve 未重启'),
	reproductionSteps: userObservation('1. 查询状态；2. 重启；3. 再查询'),
	reproductionFrequency: '偶发',
	errorExcerpt: userObservation('ERROR serve-stale: synthetic child error'),
	environmentAtFailure: {
		mwVersion: userObservation('0.12.2'),
		piVersion: unknownObservation(),
		platform: userObservation('Windows 11'),
		windowType: userObservation('tui'),
	},
	observedEnvironment: {
		mwVersion: observedObservation('0.12.4', OBSERVED_AT),
		piVersion: unknownObservation(),
		platform: observedObservation('Windows 11', OBSERVED_AT),
		windowType: unknownObservation(),
		bundleStatus: observedObservation('fresh', OBSERVED_AT),
		serveStatus: observedObservation('stale', OBSERVED_AT),
	},
	diagnosticCandidates: [{ id: 'f1', kind: 'log', text: 'child selected log line' }],
	selectedFragmentIds: ['f1'],
});
try {
	fs.writeFileSync(options.readyFlag, 'ready', 'utf8');
	const deadline = Date.now() + 10000;
	while (!fs.existsSync(options.startFlag)) {
		if (Date.now() >= deadline) throw new Error('timed out waiting for the start flag');
		await new Promise((resolve) => setTimeout(resolve, 5));
	}
	const actor = {
		role: 'pm',
		scope: options.scope,
		projectRoot: options.actorRoot,
		projectLabel: options.projectLabel,
		by: options.by,
		trustedWindow: true,
		writeAuthorized: true,
	};
	const childStore = new IssueStore({
		projectRoot: options.projectRoot,
		env: {},
		pointerFile: options.pointerFile,
		lockOptions: { retries: 200, baseDelayMs: 2 },
	});
	if (options.mode === 'submit') {
		const prep = prepareIssue(childDraft(options.id, options.projectLabel, options.title), {
			submittedAt: SUBMITTED,
			environmentObservedAt: OBSERVED_AT,
			knownSecrets: [],
		});
		const confirmation = { confirmed: true, confirmedAt: options.at, previewSha256: prep.previewSha256 };
		const result = await childStore.submit({ actor, preparation: prep, confirmation, knownSecrets: [] });
		report({
			ok: result.ok,
			code: result.code,
			id: result.id,
			created: result.created,
			verifiedById: result.verifiedById,
			state: result.state,
			submitted: result.submitted,
		});
	} else {
		const fields = {
			status: '修复中',
			statusNote: options.statusNote,
			nextAction: null,
			fixCommit: null,
			releaseVersion: null,
			questionToReporter: null,
		};
		const preview = renderDevUpdatePreview(fields, {
			id: options.id,
			at: options.at,
			source: 'dev-pm',
			by: options.by,
		});
		const confirmation = { confirmed: true, confirmedAt: options.at, previewSha256: issueTextSha256(preview) };
		const result = await childStore.appendProgress({
			actor,
			id: options.id,
			update: fields,
			preview,
			confirmation,
			knownSecrets: [],
		});
		report({
			ok: result.ok,
			code: result.code,
			seq: result.seq,
			eventSha: result.event ? result.event.sha256 : null,
		});
	}
} catch (error) {
	report({ ok: false, error: error instanceof Error ? error.message : String(error) });
}
`;

interface ChildOptions {
	mode: "submit" | "progress";
	projectRoot: string;
	actorRoot: string;
	pointerFile: string;
	id: string;
	projectLabel: string;
	by: string;
	scope: "project" | "dev";
	at: string;
	title?: string;
	statusNote?: string;
	readyFlag: string;
	startFlag: string;
	resultFlag: string;
}

interface ChildResult {
	ok: boolean;
	code?: string;
	created?: boolean;
	verifiedById?: boolean;
	state?: string;
	submitted?: boolean;
	seq?: number;
	eventSha?: string | null;
	error?: string;
}

function childScriptPath(top: string): string {
	const file = path.join(top, "issue-store-child.mjs");
	fs.writeFileSync(file, CHILD_SOURCE, "utf8");
	return file;
}

function readChildResult(file: string): ChildResult {
	return JSON.parse(fs.readFileSync(file, "utf8")) as ChildResult;
}

function runChild(childFile: string, options: ChildOptions): Promise<ChildResult> {
	return new Promise((resolve, reject) => {
		const child = spawn(process.execPath, ["--no-warnings", "--experimental-strip-types", childFile], {
			cwd: START_CWD,
			env: { ...process.env, MW_ISSUE_CHILD_OPTIONS: JSON.stringify(options) },
			stdio: ["ignore", "pipe", "pipe"],
			windowsHide: true,
		});
		let stdout = "";
		let stderr = "";
		child.stdout?.on("data", (chunk: unknown) => {
			stdout += String(chunk);
		});
		child.stderr?.on("data", (chunk: unknown) => {
			stderr += String(chunk);
		});
		child.on("error", reject);
		child.on("close", (code) => {
			if (code !== 0) {
				reject(new Error(`issue-store child exited ${code}: ${stderr.trim() || stdout.trim()}`));
				return;
			}
			try {
				resolve(readChildResult(options.resultFlag));
			} catch (error) {
				reject(error);
			}
		});
	});
}

async function waitForFiles(files: readonly string[], timeoutMs = 10_000): Promise<void> {
	const deadline = Date.now() + timeoutMs;
	while (!files.every((file) => fs.existsSync(file))) {
		if (Date.now() >= deadline) throw new Error(`timed out waiting for child flags: ${files.join(", ")}`);
		await new Promise<void>((resolve) => setTimeout(resolve, 10));
	}
}

describe("T-03 frozen store contract and confirmed scene submission", () => {
	it("consumes the accepted model/root exports, keeps entry-path-only security wording, and forbids cwd/dynamic discovery", () => {
		const source = fs.readFileSync(
			new URL("../../src/extensions/agent-team-loop/shared/issue-store.ts", import.meta.url),
			"utf8",
		);
		for (const name of [
			"confirmIssue",
			"renderPreview",
			"canonicalPayload",
			"redactSecrets",
			"appendDevUpdate",
			"appendReporterReply",
			"latestDevState",
			"pendingQuestion",
			"projectForUser",
			"listIssuesForProject",
			"summarizeForList",
			"resolveIssueDevRoot",
			"formatIssueDevRootFailure",
		]) {
			expect(source).toContain(name);
		}
		expect(source).toContain('from "./issue-model.ts"');
		expect(source).toContain('from "./issue-root.ts"');
		expect(source).not.toContain("process.cwd(");
		expect(source).not.toContain("await import(");
		expect(source).not.toContain("os.homedir(");
		expect(source).not.toContain("fetch(");
		expect(source).not.toContain("ui-bridge.ts");
		expect(ISSUE_STORE_ENTRY_ONLY_NOTICE).toContain("same-OS-user");
		expect(ISSUE_STORE_ENTRY_ONLY_NOTICE).toContain("entry-path");
		console.log("[VERIFY] VC-000: model/root-exports=consumed cwd=0 dynamic-import=0 notice=entry-only");
	});

	it("creates one confirmed scene per ID, keeps a minimal local index, hides foreign IDs and persists no secret/unconfirmed sentinel", async () => {
		const fx = fixture();
		const storeA = store(fx, fx.projectA);
		const storeB = store(fx, fx.projectB);
		const actorA = pmActor(fx.projectA, "project-A", "pm-A");
		const actorB = pmActor(fx.projectB, "project-B", "pm-B");
		const subA = makeSubmission({ projectLabel: "project-A" });
		const subB = makeSubmission({ projectLabel: "project-B", title: "project-B serve 状态不一致" });
		const resultA = await storeA.submit({
			actor: actorA,
			preparation: subA.preparation,
			confirmation: subA.confirmation,
			knownSecrets: subA.knownSecrets,
		});
		const resultB = await storeB.submit({
			actor: actorB,
			preparation: subB.preparation,
			confirmation: subB.confirmation,
			knownSecrets: subB.knownSecrets,
		});
		expect(resultA.ok).toBe(true);
		expect(resultB.ok).toBe(true);
		expect(resultA.code).toBe("submitted");
		expect(resultA.id).toBe(subA.id);
		expect(resultA.state).toBe("submitted");
		expect(resultA.display).toBe(ISSUE_DISPLAY_SUBMITTED);
		expect(resultA.event?.id).toBe(subA.id);
		expect(readEvents(fx, subA.id).filter((event) => event.kind === "created")).toHaveLength(1);
		expect(readEvents(fx, subB.id).filter((event) => event.kind === "created")).toHaveLength(1);
		expect(countAuthorityLogs(fx)).toBe(2);
		expect(readIndex(fx.projectA)?.records).toHaveLength(1);
		expect(readIndex(fx.projectB)?.records).toHaveLength(1);
		expect(countPending(fx.projectA)).toBe(0);
		expect(countPending(fx.projectB)).toBe(0);
		const createdA = readEvents(fx, subA.id)[0];
		if (createdA.kind !== "created") throw new Error("first event must be created");
		expect(canonicalPayload(createdA.card)).toBe(canonicalPayload(subA.preparation.card));
		expect(createdA.card.scene.errorExcerpt.value).toContain(REDACTION_MARK);
		const persisted = `${allTextUnder(issueAuthorityBasePath(fx.devRoot))}\n${allTextUnder(issueLocalBasePath(fx.projectA))}\n${allTextUnder(issueLocalBasePath(fx.projectB))}`;
		expect(persisted).not.toContain(SECRET_A);
		expect(persisted).not.toContain(SECRET_B);
		expect(persisted).not.toContain(UNCONFIRMED);
		expect(persisted).toContain(REDACTION_MARK);
		expect(fs.readFileSync(issueLocalIndexPath(fx.projectA), "utf8")).not.toContain('"scene"');
		expect(fs.readFileSync(issueLocalIndexPath(fx.projectA), "utf8")).not.toContain('"diagnostics"');
		const statusA = storeA.status({ actor: actorA, id: subA.id, localEvidence: localEvidence() });
		expect(statusA.ok).toBe(true);
		expect(statusA.card?.id).toBe(subA.id);
		expect(statusA.text).toContain(LONG_STEP);
		expect(statusA.text).toContain(REDACTION_MARK);
		const foreignStatus = storeB.status({ actor: actorB, id: subA.id, localEvidence: localEvidence() });
		expect(foreignStatus.code).toBe("not-owned");
		expect(foreignStatus.card).toBeNull();
		const listA = storeA.list({ actor: actorA });
		const listB = storeB.list({ actor: actorB });
		expect(listA.rows.map((row) => row.id)).toEqual([subA.id]);
		expect(listB.rows.map((row) => row.id)).toEqual([subB.id]);
		expect(listA.rows.some((row) => row.id === subB.id)).toBe(false);
		expect(listB.rows.some((row) => row.id === subA.id)).toBe(false);
		console.log("[VERIFY] VC-001: created=1 id=same scene=readable foreign=0 secrets=0");
	});

	it("refuses unconfirmed or credential-bearing input with zero writes", async () => {
		const fx = fixture();
		const storeA = store(fx, fx.projectA);
		const actor = pmActor(fx.projectA);
		const id = newIssueId();
		const before = snapshot(fx.top);
		const refused = makeSubmission({ id, confirmed: false });
		const refusal = await storeA.submit({
			actor,
			preparation: refused.preparation,
			confirmation: refused.confirmation,
			knownSecrets: refused.knownSecrets,
		});
		expect(refusal.ok).toBe(false);
		expect(refusal.code).toBe("unconfirmed");
		expect(refusal.state).toBe("none");
		const forged = forgedCredentialSubmission(id);
		const credential = await storeA.submit({
			actor,
			preparation: forged.preparation,
			confirmation: forged.confirmation,
			knownSecrets: forged.knownSecrets,
		});
		expect(credential.ok).toBe(false);
		expect(credential.code).toBe("credential-detected");
		expect(credential.state).toBe("none");
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(readIndex(fx.projectA)).toBeNull();
		expect(countPending(fx.projectA)).toBe(0);
		expect(snapshot(fx.top)).toEqual(before);
		console.log("[VERIFY] VC-002: created=0 leaked=0 unconfirmed_diagnostics=0");
	});

	it("leaves one confirmed redacted pending copy offline; restored retry and repeated calls create exactly one authority event", async () => {
		const fx = fixture();
		const offline = store(fx, fx.projectA, { pointerFile: fx.missingPointerFile });
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		const devBefore = snapshot(fx.devRoot);
		const first = await offline.submit({
			actor,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		expect(first.code).toBe("authority-unavailable");
		expect(first.state).toBe("pending");
		expect(first.display).toBe(ISSUE_DISPLAY_NOT_SUBMITTED);
		expect(first.authorityReachable).toBe(false);
		expect(first.rootFailure?.code).toBe("E-ISSUE-DEV-ROOT-NOT_CONFIGURED");
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(snapshot(fx.devRoot)).toEqual(devBefore);
		expect(countPending(fx.projectA)).toBe(1);
		expect(readIndex(fx.projectA)?.records[0]?.state).toBe("pending");
		const pendingBytes = fs.readFileSync(issuePendingCopyPath(fx.projectA, sub.id), "utf8");
		expect(pendingBytes).not.toContain(SECRET_A);
		expect(pendingBytes).not.toContain(SECRET_B);
		expect(pendingBytes).not.toContain(UNCONFIRMED);
		expect(pendingBytes).toContain(REDACTION_MARK);
		const second = await offline.retry({ actor, id: sub.id });
		expect(second.code).toBe("authority-unavailable");
		expect(second.state).toBe("pending");
		expect(countPending(fx.projectA)).toBe(1);
		expect(countAuthorityLogs(fx)).toBe(0);
		const rebound = bindIssueDevRoot({
			callerProjectRoot: fx.devRoot,
			candidateRoot: fx.devRoot,
			userConfirmed: true,
			pointerFile: fx.missingPointerFile,
			now: () => new Date("2026-11-12T12:05:00.000Z"),
		});
		expect(rebound.ok).toBe(true);
		const restored = store(fx, fx.projectA, { pointerFile: fx.missingPointerFile });
		const third = await restored.retry({ actor, id: sub.id });
		expect(third.ok).toBe(true);
		expect(third.code).toBe("submitted");
		expect(third.created).toBe(true);
		expect(third.state).toBe("submitted");
		expect(countAuthorityLogs(fx)).toBe(1);
		expect(readEvents(fx, sub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		expect(countPending(fx.projectA)).toBe(0);
		expect(readIndex(fx.projectA)?.records[0]?.state).toBe("submitted");
		expect(readIndex(fx.projectA)?.records[0]?.authority_ack).not.toBeNull();
		const fourth = await restored.retry({ actor, id: sub.id });
		expect(fourth.code).toBe("already-submitted");
		expect(fourth.created).toBe(false);
		expect(fourth.verifiedById).toBe(true);
		const replay = await restored.submit({
			actor,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		expect(replay.code).toBe("already-submitted");
		expect(readEvents(fx, sub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		console.log("[VERIFY] VC-003: pending=1 offline_retry=0_created restored=1_created ack=1 duplicate=0");
	});

	it("keeps 待核实 when authority succeeded but local ACK was lost; the next ID retry verifies without a second event", async () => {
		const fx = fixture();
		let hookCalls = 0;
		const storeA = store(fx, fx.projectA, {
			hooks: {
				afterAuthorityCommit: (commit) => {
					if (commit.created) {
						hookCalls += 1;
						throw new Error("simulated local ACK loss");
					}
				},
			},
		});
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		const lost = await storeA.submit({
			actor,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		expect(lost.ok).toBe(false);
		expect(lost.code).toBe("ack-lost");
		expect(lost.state).toBe("in-flight");
		expect(lost.display).toBe(ISSUE_DISPLAY_VERIFY_PENDING);
		expect(lost.submitted).toBe(false);
		expect(lost.authorityReachable).toBe(true);
		expect(hookCalls).toBe(1);
		expect(readEvents(fx, sub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		expect(readIndex(fx.projectA)?.records[0]?.state).toBe("in-flight");
		expect(readIndex(fx.projectA)?.records[0]?.authority_ack).toBeNull();
		expect(countPending(fx.projectA)).toBe(1);
		const pendingStatus = storeA.status({ actor, id: sub.id, localEvidence: localEvidence() });
		expect(pendingStatus.ok).toBe(true);
		expect(pendingStatus.authorityVerifiedById).toBe(true);
		expect(pendingStatus.localAck).toBe(false);
		expect(pendingStatus.submitted).toBe(false);
		expect(pendingStatus.display).toBe(ISSUE_DISPLAY_VERIFY_PENDING);
		expect(pendingStatus.message).toContain("待核实");
		const recovered = await storeA.retry({ actor, id: sub.id });
		expect(recovered.ok).toBe(true);
		expect(recovered.code).toBe("already-submitted");
		expect(recovered.created).toBe(false);
		expect(recovered.verifiedById).toBe(true);
		expect(recovered.display).toBe(ISSUE_DISPLAY_SUBMITTED);
		expect(readIndex(fx.projectA)?.records[0]?.state).toBe("submitted");
		expect(readIndex(fx.projectA)?.records[0]?.authority_ack).not.toBeNull();
		expect(countPending(fx.projectA)).toBe(0);
		const repeated = await storeA.retry({ actor, id: sub.id });
		expect(repeated.ok).toBe(true);
		expect(readEvents(fx, sub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		expect(hookCalls).toBe(1);
		console.log("[VERIFY] VC-003: ack_lost=in_flight display=待核实 by_id_retry=1 authority_created=1");
	});
});

async function expectStoreErrorAsync(
	action: () => Promise<unknown>,
	code: IssueStoreError["code"],
): Promise<IssueStoreError> {
	try {
		await action();
	} catch (error) {
		if (!(error instanceof IssueStoreError)) throw error;
		expect(error.code).toBe(code);
		return error;
	}
	throw new Error(`expected async IssueStoreError ${code}`);
}

describe("T-03 same-ID conflicts, progress/replies, worker gates and file faults", () => {
	it("refuses same-ID/different-content overwrite in authority, local index and confirmed pending copy", async () => {
		const fx = fixture();
		const storeA = store(fx, fx.projectA);
		const actorA = pmActor(fx.projectA);
		const sub = makeSubmission();
		const first = await storeA.submit({
			actor: actorA,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		expect(first.ok).toBe(true);
		const logBefore = authorityLogBytes(fx, sub.id);
		const indexBefore = fs.readFileSync(issueLocalIndexPath(fx.projectA));
		const changed = makeSubmission({ id: sub.id, title: "同 ID 不同标题", actual: "同 ID 不同现象" });
		const conflict = await storeA.submit({
			actor: actorA,
			preparation: changed.preparation,
			confirmation: changed.confirmation,
			knownSecrets: changed.knownSecrets,
		});
		expect(conflict.ok).toBe(false);
		expect(conflict.code).toBe("duplicate-conflict");
		expect(authorityLogBytes(fx, sub.id).equals(logBefore)).toBe(true);
		expect(fs.readFileSync(issueLocalIndexPath(fx.projectA)).equals(indexBefore)).toBe(true);
		expect(readEvents(fx, sub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		const beforeB = snapshot(fx.projectB);
		const storeB = store(fx, fx.projectB);
		const foreign = makeSubmission({ id: sub.id, projectLabel: "project-B", title: "project-B 同 ID 冲突" });
		const foreignConflict = await storeB.submit({
			actor: pmActor(fx.projectB, "project-B", "pm-B"),
			preparation: foreign.preparation,
			confirmation: foreign.confirmation,
			knownSecrets: foreign.knownSecrets,
		});
		expect(foreignConflict.code).toBe("duplicate-conflict");
		expect(snapshot(fx.projectB)).toEqual(beforeB);
		expect(authorityLogBytes(fx, sub.id).equals(logBefore)).toBe(true);
		expect(countAuthorityLogs(fx)).toBe(1);
		const offline = store(fx, fx.projectA, { pointerFile: fx.missingPointerFile });
		const offId = newIssueId();
		const offlineSub = makeSubmission({ id: offId });
		await offline.submit({
			actor: actorA,
			preparation: offlineSub.preparation,
			confirmation: offlineSub.confirmation,
			knownSecrets: offlineSub.knownSecrets,
		});
		const pendingFile = issuePendingCopyPath(fx.projectA, offId);
		const pendingBefore = fs.readFileSync(pendingFile);
		const offlineChanged = makeSubmission({ id: offId, title: "离线同 ID 不同标题" });
		const pendingConflict = await offline.submit({
			actor: actorA,
			preparation: offlineChanged.preparation,
			confirmation: offlineChanged.confirmation,
			knownSecrets: offlineChanged.knownSecrets,
		});
		expect(pendingConflict.code).toBe("duplicate-conflict");
		expect(fs.readFileSync(pendingFile).equals(pendingBefore)).toBe(true);
		expect(countPending(fx.projectA)).toBe(1);
		expect(countAuthorityLogs(fx)).toBe(1);
		console.log("[VERIFY] VC-007: duplicate=0 overwrite=0 foreign_local_writes=0 pending_overwrite=0");
	});

	it("keeps four-state progress, fix commit/version, question/reply provenance and fail-closed local effectiveness on one ID", async () => {
		const fx = fixture();
		const storeA = store(fx, fx.projectA);
		const devStore = store(fx, fx.devRoot);
		const actorA = pmActor(fx.projectA);
		const actorDev = devActor(fx.devRoot);
		const sub = makeSubmission();
		await storeA.submit({
			actor: actorA,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		const updates: IssueProgressFields[] = [
			{
				status: "待分诊",
				statusNote: "已登记",
				nextAction: "定位入口",
				fixCommit: null,
				releaseVersion: null,
				questionToReporter: null,
			},
			{
				status: "修复中",
				statusNote: "已定位陈旧 serve 缓存",
				nextAction: "补回归测试",
				fixCommit: null,
				releaseVersion: null,
				questionToReporter: "请确认重启后是否仍见旧 PID",
			},
			{
				status: "已修复",
				statusNote: "修复已合并",
				nextAction: null,
				fixCommit: "abc1234",
				releaseVersion: null,
				questionToReporter: null,
			},
			{
				status: "已发布",
				statusNote: "已发布到 0.12.5",
				nextAction: null,
				fixCommit: "abc1234",
				releaseVersion: "0.12.5",
				questionToReporter: null,
			},
		];
		const times = [T1, T2, T3, T4];
		for (let index = 0; index < updates.length; index += 1) {
			const progress = await devStore.appendProgress(
				progressRequest(actorDev, sub.id, times[index], updates[index]),
			);
			expect(progress.ok).toBe(true);
			expect(progress.code).toBe("written");
			expect(progress.seq).toBe(index + 2);
		}
		const beforeReply = storeA.status({ actor: actorA, id: sub.id, localEvidence: localEvidence() });
		expect(beforeReply.pendingQuestion).toBe("请确认重启后是否仍见旧 PID");
		expect(beforeReply.card?.devTimeline).toHaveLength(4);
		const eventsBeforeReply = readEvents(fx, sub.id);
		const questionEvent = eventsBeforeReply.find(
			(event) => event.kind === "dev_update" && event.update.questionToReporter !== null,
		);
		if (questionEvent === undefined || questionEvent.kind !== "dev_update") throw new Error("question event missing");
		const reply = await storeA.reply(
			replyRequest(actorA, sub.id, T5, "重启后仍见旧 PID；已提供最小日志", questionEvent.sha256),
		);
		expect(reply.ok).toBe(true);
		expect(reply.code).toBe("written");
		expect(reply.seq).toBe(6);
		const status = storeA.status({ actor: actorA, id: sub.id, localEvidence: localEvidence() });
		expect(status.ok).toBe(true);
		expect(status.development?.status).toBe("已发布");
		expect(status.development?.fixCommit).toBe("abc1234");
		expect(status.development?.releaseVersion).toBe("0.12.5");
		expect(status.pendingQuestion).toBeNull();
		expect(status.card?.reporterReplies).toHaveLength(1);
		expect(status.localEffective?.state).toBe("not-verified");
		expect(status.text).toContain(NOT_VERIFIED_PHRASE);
		expect(status.text).not.toContain(VERIFIED_PHRASE);
		expect(status.events).toHaveLength(6);
		const events = readEvents(fx, sub.id);
		expect(events.map((event) => event.seq)).toEqual([1, 2, 3, 4, 5, 6]);
		for (const event of events) {
			expect(event.at).toMatch(/([+-]\d{2}:\d{2}|Z)$/);
			if (event.kind === "created") {
				expect(event.source).toBe("project-pm");
				expect(event.confirmed_at).toBe(event.at);
				expect(event.confirmed_by).toBe(event.by);
			} else if (event.kind === "dev_update") {
				expect(event.source).toBe("dev-pm");
				expect(event.update.at).toBe(event.at);
				expect(event.update.by).toBe(event.by);
			} else {
				expect(event.source).toBe("project-pm");
				expect(event.reply.at).toBe(event.at);
				expect(event.reply.source).toBe("user");
				expect(event.reply.inReplyTo).toBe(questionEvent.sha256);
			}
		}
		const listA = storeA.list({ actor: actorA });
		const listB = store(fx, fx.projectB).list({ actor: pmActor(fx.projectB, "project-B", "pm-B") });
		expect(listA.rows).toHaveLength(1);
		expect(listA.rows[0].status).toBe("已发布");
		expect(listB.rows).toHaveLength(0);
		expect(status.card?.scene.errorExcerpt.value).toContain(REDACTION_MARK);
		expect(status.card?.scene.reproductionSteps.value).toContain("END-OF-REPRO-STEPS");
		console.log("[VERIFY] VC-004: latest=已发布 foreign=0 question=1 reply=1 time_source=ok");
		console.log("[VERIFY] VC-005: local_effective=not-verified verified_phrase=0");
	});

	it("denies worker/foreign-window writes through the MW entry gate with zero tree changes", async () => {
		const fx = fixture();
		const storeA = store(fx, fx.projectA);
		const actorA = pmActor(fx.projectA);
		const sub = makeSubmission();
		await storeA.submit({
			actor: actorA,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		const beforeDev = snapshot(fx.devRoot);
		const beforeA = snapshot(fx.projectA);
		const beforeB = snapshot(fx.projectB);
		const workerEnvStore = store(fx, fx.projectA, { env: { PI_WORKER_TASK: "worker-card.md" } });
		const newSub = makeSubmission({ id: newIssueId() });
		const workerEnv = await workerEnvStore.submit({
			actor: actorA,
			preparation: newSub.preparation,
			confirmation: newSub.confirmation,
			knownSecrets: newSub.knownSecrets,
		});
		expect(workerEnv.code).toBe("worker-forbidden");
		const workerActor: IssueStoreActor = { ...actorA, role: "worker", writeAuthorized: false, trustedWindow: true };
		const workerSubmit = await storeA.submit({
			actor: workerActor,
			preparation: newSub.preparation,
			confirmation: newSub.confirmation,
			knownSecrets: newSub.knownSecrets,
		});
		expect(workerSubmit.code).toBe("worker-forbidden");
		const workerDev: IssueStoreActor = { ...devActor(fx.devRoot), role: "worker", writeAuthorized: false };
		const workerProgress = await store(fx, fx.devRoot).appendProgress(
			progressRequest(workerDev, sub.id, T2, {
				status: "修复中",
				statusNote: "worker attempted progress",
				nextAction: null,
				fixCommit: null,
				releaseVersion: null,
				questionToReporter: null,
			}),
		);
		expect(workerProgress.code).toBe("worker-forbidden");
		const workerReply = await storeA.reply(replyRequest(workerActor, sub.id, T5, "worker attempted reply", null));
		expect(workerReply.code).toBe("worker-forbidden");
		const foreignActor = pmActor(fx.projectB, "project-A", "pm-B");
		const foreignSubmit = await storeA.submit({
			actor: foreignActor,
			preparation: newSub.preparation,
			confirmation: newSub.confirmation,
			knownSecrets: newSub.knownSecrets,
		});
		expect(foreignSubmit.code).toBe("foreign-project");
		expect(snapshot(fx.devRoot)).toEqual(beforeDev);
		expect(snapshot(fx.projectA)).toEqual(beforeA);
		expect(snapshot(fx.projectB)).toEqual(beforeB);
		console.log("[VERIFY] VC-006: denied=5 unchanged=1 os_bypass_note=present");
	});

	it("fails visibly on root ambiguity and writes to neither dev root", async () => {
		const fx = fixture();
		const devRoot2 = path.join(fx.top, "mw-dev-2");
		makeDevRepo(devRoot2);
		const before1 = snapshot(fx.devRoot);
		const before2 = snapshot(devRoot2);
		const ambiguous = store(fx, fx.projectA, { crossCheckRoots: [devRoot2] });
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		const result = await ambiguous.submit({
			actor,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		expect(result.code).toBe("authority-unavailable");
		expect(result.state).toBe("pending");
		expect(result.display).toBe(ISSUE_DISPLAY_NOT_SUBMITTED);
		expect(result.rootFailure?.code).toBe("E-ISSUE-DEV-ROOT-AMBIGUOUS");
		expect(countPending(fx.projectA)).toBe(1);
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(snapshot(fx.devRoot)).toEqual(before1);
		expect(snapshot(devRoot2)).toEqual(before2);
		expect(fs.existsSync(path.join(fx.devRoot, ".agenticdoc", "mw-issue-feedback", "authority"))).toBe(false);
		expect(fs.existsSync(path.join(devRoot2, ".agenticdoc", "mw-issue-feedback", "authority"))).toBe(false);
		console.log("[VERIFY] VC-007: duplicate=0 wrong_root_writes=0 ambiguous=pending");
	});

	it("reports corrupt authority, duplicate-key local index and corrupt pending copy explicitly without repair", async () => {
		const authorityFx = fixture();
		const authorityStore = store(authorityFx, authorityFx.projectA);
		const authorityActor = pmActor(authorityFx.projectA);
		const authoritySub = makeSubmission();
		await authorityStore.submit({
			actor: authorityActor,
			preparation: authoritySub.preparation,
			confirmation: authoritySub.confirmation,
			knownSecrets: authoritySub.knownSecrets,
		});
		const logFile = issueAuthorityLogPath(authorityFx.devRoot, authoritySub.id);
		const validLog = fs.readFileSync(logFile, "utf8");
		fs.writeFileSync(logFile, `${validLog}{"broken":true}\n`, "utf8");
		const corruptLogBytes = fs.readFileSync(logFile);
		const authorityTreeBefore = snapshot(authorityFx.devRoot);
		expectStoreError(
			() => authorityStore.status({ actor: authorityActor, id: authoritySub.id, localEvidence: localEvidence() }),
			"E-ISSUE-STORE-CORRUPT",
		);
		expect(snapshot(authorityFx.devRoot)).toEqual(authorityTreeBefore);
		expect(fs.readFileSync(logFile).equals(corruptLogBytes)).toBe(true);

		const indexFx = fixture();
		const indexStore = store(indexFx, indexFx.projectA);
		const indexActor = pmActor(indexFx.projectA);
		const indexSub = makeSubmission();
		await indexStore.submit({
			actor: indexActor,
			preparation: indexSub.preparation,
			confirmation: indexSub.confirmation,
			knownSecrets: indexSub.knownSecrets,
		});
		const indexFile = issueLocalIndexPath(indexFx.projectA);
		fs.writeFileSync(indexFile, '{\n  "schema": 1,\n  "schema": 1,\n  "kind": "mw-issue-local-index"\n}\n', "utf8");
		const corruptIndexBytes = fs.readFileSync(indexFile);
		const projectTreeBefore = snapshot(indexFx.projectA);
		expectStoreError(() => indexStore.list({ actor: indexActor }), "E-ISSUE-STORE-CORRUPT");
		expect(snapshot(indexFx.projectA)).toEqual(projectTreeBefore);
		expect(fs.readFileSync(indexFile).equals(corruptIndexBytes)).toBe(true);

		const pendingFx = fixture();
		const offline = store(pendingFx, pendingFx.projectA, { pointerFile: pendingFx.missingPointerFile });
		const pendingActor = pmActor(pendingFx.projectA);
		const pendingSub = makeSubmission();
		await offline.submit({
			actor: pendingActor,
			preparation: pendingSub.preparation,
			confirmation: pendingSub.confirmation,
			knownSecrets: pendingSub.knownSecrets,
		});
		const rebound = bindIssueDevRoot({
			callerProjectRoot: pendingFx.devRoot,
			candidateRoot: pendingFx.devRoot,
			userConfirmed: true,
			pointerFile: pendingFx.missingPointerFile,
			now: () => new Date("2026-11-12T12:05:00.000Z"),
		});
		expect(rebound.ok).toBe(true);
		const pendingFile = issuePendingCopyPath(pendingFx.projectA, pendingSub.id);
		fs.writeFileSync(pendingFile, '{"broken":true', "utf8");
		const corruptPendingBytes = fs.readFileSync(pendingFile);
		const pendingProjectBefore = snapshot(pendingFx.projectA);
		const restored = store(pendingFx, pendingFx.projectA, { pointerFile: pendingFx.missingPointerFile });
		await expectStoreErrorAsync(
			() => restored.retry({ actor: pendingActor, id: pendingSub.id }),
			"E-ISSUE-STORE-CORRUPT",
		);
		expect(snapshot(pendingFx.projectA)).toEqual(pendingProjectBefore);
		expect(fs.readFileSync(pendingFile).equals(corruptPendingBytes)).toBe(true);
		expect(countAuthorityLogs(pendingFx)).toBe(0);
		console.log("[VERIFY] VC-007: corrupt=explicit bytes=unchanged repair=0 authority_created=0");
	});

	it("keeps a foreign O_EXCL lock byte-for-byte and never silently cleans a stale lock", async () => {
		const fx = fixture();
		const authorityBase = issueAuthorityBasePath(fx.devRoot);
		fs.mkdirSync(authorityBase, { recursive: true });
		const lockFile = issueAuthorityLockPath(fx.devRoot);
		const foreignLock = Buffer.from([0x46, 0x4f, 0x52, 0x45, 0x49, 0x47, 0x4e, 0x00, 0xff, 0x0a]);
		fs.writeFileSync(lockFile, foreignLock);
		const blocked = store(fx, fx.projectA, { lockOptions: { retries: 0, baseDelayMs: 1 } });
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		const result = await blocked.submit({
			actor,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		expect(result.code).toBe("lock-busy");
		expect(result.state).toBe("pending");
		expect(result.display).toBe(ISSUE_DISPLAY_NOT_SUBMITTED);
		expect(fs.readFileSync(lockFile).equals(foreignLock)).toBe(true);
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(countPending(fx.projectA)).toBe(1);
		expect(readIndex(fx.projectA)?.records[0]?.state).toBe("pending");
		console.log("[VERIFY] VC-007: foreign_lock=unchanged stale_cleanup=0 created=0 pending=1");
	});
});

describe("T-03 authority-unavailable visibility", () => {
	it("refuses to present stale development state when the authority becomes unavailable", async () => {
		const fx = fixture();
		const storeA = store(fx, fx.projectA);
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		await storeA.submit({
			actor,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		await store(fx, fx.devRoot).appendProgress(
			progressRequest(devActor(fx.devRoot), sub.id, T4, {
				status: "已发布",
				statusNote: "权威侧已发布",
				nextAction: null,
				fixCommit: "abc1234",
				releaseVersion: "0.12.5",
				questionToReporter: null,
			}),
		);
		const offline = store(fx, fx.projectA, { pointerFile: fx.missingPointerFile });
		const devBefore = snapshot(fx.devRoot);
		const status = offline.status({ actor, id: sub.id, localEvidence: localEvidence() });
		expect(status.code).toBe("authority-unavailable");
		expect(status.authorityReachable).toBe(false);
		expect(status.card).toBeNull();
		expect(status.projection).toBeNull();
		expect(status.development).toBeNull();
		expect(status.text).toContain("权威记录入口不可达，状态无法更新");
		expect(status.text).not.toContain("已发布");
		expect(snapshot(fx.devRoot)).toEqual(devBefore);
		const list = offline.list({ actor });
		expect(list.code).toBe("authority-unavailable");
		expect(list.rows).toHaveLength(1);
		expect(list.rows[0].status).toBe("未知");
		expect(list.rows[0].updatedAt).toBeNull();
		expect(list.rows[0].authorityVerified).toBe(false);
		expect(list.message).toContain("状态无法更新");
		console.log("[VERIFY] VC-003: stale_dev_state=0 authority_unavailable=visible list_status=未知");
	});
});

describe("T-03 independent child-process lock serialization", () => {
	it("serializes two same-ID submissions and refuses a third different-content ID without a second created event", async () => {
		const fx = fixture();
		const childFile = childScriptPath(fx.top);
		const id = newIssueId();
		const startFlag = path.join(fx.top, "start-submit.flag");
		const common = {
			mode: "submit" as const,
			pointerFile: fx.pointerFile,
			id,
			projectLabel: "project-A",
			scope: "project" as const,
			at: CONFIRMED_AT,
			title: "cross-process same content",
			startFlag,
		};
		const firstOptions: ChildOptions = {
			...common,
			projectRoot: fx.projectA,
			actorRoot: fx.projectA,
			by: "pm-A-1",
			readyFlag: path.join(fx.top, "ready-submit-1.flag"),
			resultFlag: path.join(fx.top, "result-submit-1.json"),
		};
		const secondOptions: ChildOptions = {
			...common,
			projectRoot: fx.projectA,
			actorRoot: fx.projectA,
			by: "pm-A-2",
			readyFlag: path.join(fx.top, "ready-submit-2.flag"),
			resultFlag: path.join(fx.top, "result-submit-2.json"),
		};
		const firstPromise = runChild(childFile, firstOptions);
		const secondPromise = runChild(childFile, secondOptions);
		await waitForFiles([firstOptions.readyFlag, secondOptions.readyFlag]);
		fs.writeFileSync(startFlag, "go", "utf8");
		const firstResults = await Promise.all([firstPromise, secondPromise]);
		for (const result of firstResults) {
			expect(result.ok).toBe(true);
			expect(result.error).toBeUndefined();
		}
		expect(firstResults.filter((result) => result.created === true)).toHaveLength(1);
		expect(firstResults.filter((result) => result.created === false && result.verifiedById === true)).toHaveLength(1);
		expect(readEvents(fx, id).filter((event) => event.kind === "created")).toHaveLength(1);
		expect(countAuthorityLogs(fx)).toBe(1);
		expect(readIndex(fx.projectA)?.records).toHaveLength(1);
		const status = store(fx, fx.projectA).status({
			actor: pmActor(fx.projectA),
			id,
			localEvidence: localEvidence(),
		});
		expect(status.ok).toBe(true);
		expect(status.events).toHaveLength(1);
		expect(status.display).toBe(ISSUE_DISPLAY_SUBMITTED);
		const beforeB = snapshot(fx.projectB);
		const conflictStart = path.join(fx.top, "start-conflict.flag");
		fs.writeFileSync(conflictStart, "go", "utf8");
		const conflict = await runChild(childFile, {
			mode: "submit",
			projectRoot: fx.projectB,
			actorRoot: fx.projectB,
			pointerFile: fx.pointerFile,
			id,
			projectLabel: "project-B",
			by: "pm-B",
			scope: "project",
			at: CONFIRMED_AT,
			title: "cross-process different content",
			readyFlag: path.join(fx.top, "ready-conflict.flag"),
			startFlag: conflictStart,
			resultFlag: path.join(fx.top, "result-conflict.json"),
		});
		expect(conflict.ok).toBe(false);
		expect(conflict.code).toBe("duplicate-conflict");
		expect(snapshot(fx.projectB)).toEqual(beforeB);
		expect(readEvents(fx, id).filter((event) => event.kind === "created")).toHaveLength(1);
		console.log("[VERIFY] VC-007: concurrent_created=1 duplicate=0 conflict=1 chain=ok foreign_local_writes=0");
	});

	it("serializes two independent development-update processes with a strict seq/hash chain", async () => {
		const fx = fixture();
		const storeA = store(fx, fx.projectA);
		const actorA = pmActor(fx.projectA);
		const sub = makeSubmission();
		await storeA.submit({
			actor: actorA,
			preparation: sub.preparation,
			confirmation: sub.confirmation,
			knownSecrets: sub.knownSecrets,
		});
		const childFile = childScriptPath(fx.top);
		const startFlag = path.join(fx.top, "start-progress.flag");
		const common = {
			mode: "progress" as const,
			projectRoot: fx.devRoot,
			actorRoot: fx.devRoot,
			pointerFile: fx.pointerFile,
			id: sub.id,
			projectLabel: "mw-dev",
			scope: "dev" as const,
			startFlag,
		};
		const firstOptions: ChildOptions = {
			...common,
			by: "dev-pm-1",
			at: T1,
			statusNote: "child progress one",
			readyFlag: path.join(fx.top, "ready-progress-1.flag"),
			resultFlag: path.join(fx.top, "result-progress-1.json"),
		};
		const secondOptions: ChildOptions = {
			...common,
			by: "dev-pm-2",
			at: T2,
			statusNote: "child progress two",
			readyFlag: path.join(fx.top, "ready-progress-2.flag"),
			resultFlag: path.join(fx.top, "result-progress-2.json"),
		};
		const firstPromise = runChild(childFile, firstOptions);
		const secondPromise = runChild(childFile, secondOptions);
		await waitForFiles([firstOptions.readyFlag, secondOptions.readyFlag]);
		fs.writeFileSync(startFlag, "go", "utf8");
		const results = await Promise.all([firstPromise, secondPromise]);
		for (const result of results) {
			expect(result.ok).toBe(true);
			expect(result.code).toBe("written");
			expect(result.error).toBeUndefined();
		}
		expect(results.map((result) => result.seq).sort((a, b) => (a ?? 0) - (b ?? 0))).toEqual([2, 3]);
		expect(new Set(results.map((result) => result.eventSha)).size).toBe(2);
		const status = storeA.status({ actor: actorA, id: sub.id, localEvidence: localEvidence() });
		expect(status.ok).toBe(true);
		expect(status.events.map((event) => event.seq)).toEqual([1, 2, 3]);
		expect(status.card?.devTimeline).toHaveLength(2);
		expect(countAuthorityLogs(fx)).toBe(1);
		console.log("[VERIFY] VC-007: concurrent_updates=2 seq=2,3 chain=ok lost_update=0");
	});
});
