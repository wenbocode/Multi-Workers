/**
 * T-09D (mw-issue-feedback): bounded R04/R06/R07 regressions for the unique
 * issue store. Synthetic temp dev repos/projects + an injected pointer only.
 *
 * Fault injection is a partial `node:fs` module mock: every export except the
 * five single-call wrappers below is the real one. Each injection is armed for
 * one exact call/path (or one exact fd recorded from wx lock creation) and is
 * disarmed before recovery. All store code, locks, JSONL chains and temp files
 * are real. No chmod/ACL assumption, no real credentials, no env/auth scan.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	type Confirmation,
	canonicalPayload,
	type IssueCard,
	type IssueDraft,
	type IssuePreparation,
	observedObservation,
	prepareIssue,
	REDACTION_MARK,
	renderPreview,
	unknownObservation,
	userObservation,
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
	ISSUE_EVENTS_DIR_BASENAME,
	ISSUE_PENDING_DIR_BASENAME,
	type IssueAuthorityEvent,
	type IssueProgressFields,
	type IssueReplyFields,
	IssueStore,
	type IssueStoreActor,
	type IssueStoreOptions,
	issueAuthorityBasePath,
	issueAuthorityLockPath,
	issueAuthorityLogPath,
	issueLocalBasePath,
	issueLocalIndexPath,
	issueLocalLockPath,
	issuePendingCopyPath,
	newIssueId,
	renderDevUpdatePreview,
	renderReporterReplyPreview,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";

type FaultMode =
	| "none"
	| "authority-mkdir"
	| "authority-open"
	| "local-open"
	| "lock-write"
	| "lock-fsync"
	| "lock-close"
	| "lock-close-replace"
	| "authority-partial-write";

const fault = vi.hoisted(() => ({
	mode: "none" as FaultMode,
	targetPath: "" as string,
	errorCode: "EACCES" as string,
	armed: false as boolean,
	targetFd: null as number | null,
	injections: 0 as number,
}));

vi.mock("node:fs", async (importOriginal) => {
	const actual = await importOriginal<typeof fs>();
	const realOpenSync = actual.openSync as (...args: unknown[]) => number;
	const realMkdirSync = actual.mkdirSync as (...args: unknown[]) => unknown;
	const realWriteFileSync = actual.writeFileSync as (...args: unknown[]) => void;
	const realFsyncSync = actual.fsyncSync as (...args: unknown[]) => void;
	const realCloseSync = actual.closeSync as (...args: unknown[]) => void;
	const realUnlinkSync = actual.unlinkSync as (...args: unknown[]) => void;
	const lockModes = new Set<FaultMode>(["lock-write", "lock-fsync", "lock-close", "lock-close-replace"]);

	function injectedError(code: string, message: string): never {
		const error: NodeJS.ErrnoException = new Error(message);
		error.code = code;
		throw error;
	}
	function matchesPath(value: unknown): boolean {
		return typeof value === "string" && value === fault.targetPath;
	}

	const openSync = ((...args: unknown[]): number => {
		if (
			fault.armed &&
			(fault.mode === "authority-open" || fault.mode === "local-open") &&
			matchesPath(args[0]) &&
			args[1] === "wx"
		) {
			fault.armed = false;
			fault.injections += 1;
			injectedError(fault.errorCode, `injected ${fault.errorCode} on openSync(wx)`);
		}
		const fd = realOpenSync(...args);
		if (fault.armed && lockModes.has(fault.mode) && matchesPath(args[0]) && args[1] === "wx") {
			fault.targetFd = fd;
		}
		return fd;
	}) as unknown as typeof actual.openSync;

	const mkdirSync = ((...args: unknown[]): unknown => {
		if (fault.armed && fault.mode === "authority-mkdir" && matchesPath(args[0])) {
			fault.armed = false;
			fault.injections += 1;
			injectedError(fault.errorCode, `injected ${fault.errorCode} on mkdirSync`);
		}
		return realMkdirSync(...args);
	}) as unknown as typeof actual.mkdirSync;

	const writeFileSync = ((...args: unknown[]): void => {
		if (
			fault.armed &&
			fault.mode === "authority-partial-write" &&
			typeof args[1] === "string" &&
			args[1].includes('"kind":"created"')
		) {
			fault.armed = false;
			fault.injections += 1;
			realWriteFileSync(args[0], String(args[1]).slice(0, 24), args[2]);
			injectedError("EIO", "injected partial authority event write");
		}
		if (fault.armed && fault.mode === "lock-write" && args[0] === fault.targetFd) {
			fault.armed = false;
			fault.injections += 1;
			const token = String(args[1]);
			realWriteFileSync(args[0], token.slice(0, Math.max(1, Math.floor(token.length / 2))), args[2]);
			injectedError("EIO", "injected lock token write failure");
		}
		realWriteFileSync(...args);
	}) as unknown as typeof actual.writeFileSync;

	const fsyncSync = ((...args: unknown[]): void => {
		if (fault.armed && fault.mode === "lock-fsync" && args[0] === fault.targetFd) {
			fault.armed = false;
			fault.injections += 1;
			injectedError("EIO", "injected lock fsync failure");
		}
		realFsyncSync(...args);
	}) as unknown as typeof actual.fsyncSync;

	const closeSync = ((...args: unknown[]): void => {
		if (
			fault.armed &&
			(fault.mode === "lock-close" || fault.mode === "lock-close-replace") &&
			args[0] === fault.targetFd
		) {
			fault.armed = false;
			fault.injections += 1;
			const mode = fault.mode;
			realCloseSync(args[0]);
			if (mode === "lock-close-replace") {
				realUnlinkSync(fault.targetPath);
				realWriteFileSync(fault.targetPath, "FOREIGN-REPLACEMENT", "utf8");
			}
			injectedError("EIO", "injected lock close failure");
		}
		realCloseSync(...args);
	}) as unknown as typeof actual.closeSync;

	return {
		...actual,
		default: actual,
		openSync,
		mkdirSync,
		writeFileSync,
		fsyncSync,
		closeSync,
	};
});

// ── Synthetic constants ──────────────────────────────────────────────────────

const OCCURRED = "2026-11-12T14:02:11+08:00";
const SUBMITTED = "2026-11-12T21:10:00+08:00";
const OBSERVED_AT = "2026-11-12T21:09:58+08:00";
const CONFIRMED_AT = "2026-11-12T21:15:00+08:00";
const PROGRESS_AT = "2026-11-13T09:00:00+08:00";
const REPLY_AT = "2026-11-13T10:00:00+08:00";

const SECRET_A = "SENTINEL-APIKEY-9f3a2b7c";
const SECRET_B = "SUPERSECRET-VALUE-42";
const CUSTOM_QUOTE_BACKSLASH = 'CRED-"Q"\\END';
const CUSTOM_BACKSLASH = "CRED-\\Q-END";
const CUSTOM_NEWLINE = "CRED-Q\nEND";
const CUSTOM_REPLY = 'CRED-"R"\\END\nSECOND-LINE';
const HIGH_CONFIDENCE_TOKEN = "sk-abcdefghijklmnopqrstuvwxyz";
const ORDINARY_CONTROL = 'line1\nline2 "quoted" backslash \\ end';
const REDACTED_ASSIGNMENT = `api_key=${REDACTION_MARK}`;
const FOREIGN_LOCK = Buffer.from([0x46, 0x4f, 0x52, 0x45, 0x49, 0x47, 0x4e, 0x00, 0xff, 0x0a]);

const temporaryRoots: string[] = [];

beforeEach(() => {
	fault.mode = "none";
	fault.targetPath = "";
	fault.errorCode = "EACCES";
	fault.armed = false;
	fault.targetFd = null;
	fault.injections = 0;
});

afterEach(() => {
	fault.armed = false;
	for (const dir of temporaryRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

function arm(mode: FaultMode, targetPath = "", errorCode = "EACCES"): void {
	fault.mode = mode;
	fault.targetPath = targetPath;
	fault.errorCode = errorCode;
	fault.armed = true;
	fault.targetFd = null;
	fault.injections = 0;
}

// ── Fixture ──────────────────────────────────────────────────────────────────

interface Fx {
	top: string;
	home: string;
	pointerFile: string;
	missingPointerFile: string;
	devRoot: string;
	projectA: string;
}

interface Submission {
	id: string;
	preparation: IssuePreparation;
	confirmation: Confirmation;
	knownSecrets: readonly string[];
}

interface SubmissionOptions {
	id?: string;
	title?: string;
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

function fixture(): Fx {
	const top = fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-store-fix-"));
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
	return {
		top,
		home,
		pointerFile,
		missingPointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, "missing-pointer.json"),
		devRoot,
		projectA,
	};
}

function store(fx: Fx, overrides: Partial<IssueStoreOptions> = {}): IssueStore {
	return new IssueStore({ projectRoot: fx.projectA, env: {}, pointerFile: fx.pointerFile, ...overrides });
}

function devStore(fx: Fx, overrides: Partial<IssueStoreOptions> = {}): IssueStore {
	return new IssueStore({ projectRoot: fx.devRoot, env: {}, pointerFile: fx.pointerFile, ...overrides });
}

function offlineStore(fx: Fx, overrides: Partial<IssueStoreOptions> = {}): IssueStore {
	return store(fx, { pointerFile: fx.missingPointerFile, ...overrides });
}

// ── Drafts / submissions ─────────────────────────────────────────────────────

function cleanDraft(id: string): IssueDraft {
	return {
		id,
		title: "状态窗口偶发不一致",
		projectLabel: "project-A",
		component: unknownObservation(),
		occurredAt: userObservation(OCCURRED, SUBMITTED),
		trigger: userObservation("执行 /mw status"),
		precondition: userObservation("serve 已运行超过一小时"),
		expected: userObservation("显示当前 serve 的 PID"),
		actual: userObservation("仍显示上一次启动的旧 PID"),
		impact: userObservation("误判 serve 未重启"),
		reproductionSteps: userObservation("1. 查询状态\n2. 重启\n3. 再查询"),
		reproductionFrequency: "偶发",
		errorExcerpt: userObservation(`ERROR serve-stale: ${ORDINARY_CONTROL}`),
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
		diagnosticCandidates: [{ id: "f1", kind: "log", text: "用户选择的最小日志行" }],
		selectedFragmentIds: ["f1"],
	};
}

function secretDraft(id: string): IssueDraft {
	return {
		...cleanDraft(id),
		errorExcerpt: userObservation(`ERROR serve-stale: Bearer ${SECRET_B}`),
		diagnosticCandidates: [{ id: "f1", kind: "error", text: `E123: api_key=${SECRET_A} 原始报错` }],
	};
}

function markerDraft(id: string): IssueDraft {
	return {
		...cleanDraft(id),
		errorExcerpt: userObservation(`ERROR serve-stale: ${REDACTED_ASSIGNMENT}`),
		diagnosticCandidates: [{ id: "f1", kind: "error", text: `E123: ${REDACTED_ASSIGNMENT} 原始报错` }],
	};
}

function makePreparation(
	draft: IssueDraft,
	knownSecrets: readonly string[],
): {
	preparation: IssuePreparation;
	confirmation: Confirmation;
} {
	const preparation = prepareIssue(draft, {
		submittedAt: SUBMITTED,
		environmentObservedAt: OBSERVED_AT,
		knownSecrets,
	});
	const confirmation: Confirmation = {
		confirmed: true,
		confirmedAt: CONFIRMED_AT,
		previewSha256: preparation.previewSha256,
	};
	return { preparation, confirmation };
}

function makeSubmission(options: SubmissionOptions = {}): Submission {
	const id = options.id ?? newIssueId();
	const draft = secretDraft(id);
	if (options.title !== undefined) draft.title = options.title;
	const { preparation, confirmation } = makePreparation(draft, [SECRET_A, SECRET_B]);
	return { id, preparation, confirmation, knownSecrets: [SECRET_A, SECRET_B] };
}

function makeMarkerSubmission(): Submission {
	const id = newIssueId();
	const { preparation, confirmation } = makePreparation(markerDraft(id), []);
	return { id, preparation, confirmation, knownSecrets: [] };
}

function makeCleanSubmission(): Submission {
	const id = newIssueId();
	const { preparation, confirmation } = makePreparation(cleanDraft(id), []);
	return { id, preparation, confirmation, knownSecrets: [] };
}

function makeCustomSecretSubmission(secret: string, mutate: (card: IssueCard) => void): Submission {
	const id = newIssueId();
	const base = makePreparation(cleanDraft(id), []).preparation;
	const card = structuredClone(base.card);
	mutate(card);
	const preview = renderPreview(card);
	const previewSha = sha256(preview);
	const preparation: IssuePreparation = {
		...base,
		card,
		preview,
		previewSha256: previewSha,
		submissionDigest: sha256(canonicalPayload(card)).slice(0, 16),
		redactions: 0,
		notes: [],
	};
	const confirmation: Confirmation = { confirmed: true, confirmedAt: CONFIRMED_AT, previewSha256: previewSha };
	return { id, preparation, confirmation, knownSecrets: [secret] };
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

function submitRequest(
	sub: Submission,
	actor: IssueStoreActor,
): {
	actor: IssueStoreActor;
	preparation: IssuePreparation;
	confirmation: Confirmation;
	knownSecrets: readonly string[];
} {
	return {
		actor,
		preparation: sub.preparation,
		confirmation: sub.confirmation,
		knownSecrets: sub.knownSecrets,
	};
}

// ── On-disk observations ─────────────────────────────────────────────────────

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

function eventsDir(devRoot: string): string {
	return path.join(issueAuthorityBasePath(devRoot), ISSUE_EVENTS_DIR_BASENAME);
}

function pendingDir(projectRoot: string): string {
	return path.join(issueLocalBasePath(projectRoot), ISSUE_PENDING_DIR_BASENAME);
}

function readEvents(fx: Fx, id: string): IssueAuthorityEvent[] {
	const file = issueAuthorityLogPath(fx.devRoot, id);
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.length > 0)
		.map((line) => JSON.parse(line) as IssueAuthorityEvent);
}

function readIndex(projectRoot: string): { records: { id: string; state: string }[] } | null {
	const file = issueLocalIndexPath(projectRoot);
	if (!fs.existsSync(file)) return null;
	return JSON.parse(fs.readFileSync(file, "utf8")) as { records: { id: string; state: string }[] };
}

function countPending(projectRoot: string): number {
	if (!fs.existsSync(pendingDir(projectRoot))) return 0;
	return fs.readdirSync(pendingDir(projectRoot)).filter((name) => name.endsWith(".json")).length;
}

function countAuthorityLogs(fx: Fx): number {
	if (!fs.existsSync(eventsDir(fx.devRoot))) return 0;
	return fs.readdirSync(eventsDir(fx.devRoot)).filter((name) => name.endsWith(".jsonl")).length;
}

function authorityLogBytes(fx: Fx, id: string): Buffer {
	return fs.readFileSync(issueAuthorityLogPath(fx.devRoot, id));
}

// ── R04: authority write-entry preflight failures ────────────────────────────

describe("T-09D R04: authority write-entry failures keep one same-ID pending copy", () => {
	it("mkdir EACCES leaves pending; restored retry twice creates exactly one event", async () => {
		const fx = fixture();
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		arm("authority-mkdir", issueAuthorityBasePath(fx.devRoot), "EACCES");
		const result = await store(fx).submit(submitRequest(sub, actor));
		expect(fault.injections).toBe(1);
		expect(result.code).toBe("authority-unavailable");
		expect(result.state).toBe("pending");
		expect(result.display).toBe(ISSUE_DISPLAY_NOT_SUBMITTED);
		expect(result.submitted).toBe(false);
		expect(result.authorityReachable).toBe(false);
		expect(result.id).toBe(sub.id);
		expect(result.reason).toContain("EACCES");
		expect(fs.existsSync(issueAuthorityBasePath(fx.devRoot))).toBe(false);
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(countPending(fx.projectA)).toBe(1);
		expect(readIndex(fx.projectA)?.records[0]?.state).toBe("pending");
		const pendingBytes = fs.readFileSync(issuePendingCopyPath(fx.projectA, sub.id), "utf8");
		expect(pendingBytes).not.toContain(SECRET_A);
		expect(pendingBytes).not.toContain(SECRET_B);
		expect(pendingBytes).toContain(REDACTION_MARK);

		fault.armed = false;
		const restored = store(fx);
		const first = await restored.retry({ actor, id: sub.id });
		expect(first.ok).toBe(true);
		expect(first.code).toBe("submitted");
		expect(first.created).toBe(true);
		const second = await restored.retry({ actor, id: sub.id });
		expect(second.ok).toBe(true);
		expect(second.code).toBe("already-submitted");
		expect(second.created).toBe(false);
		expect(readEvents(fx, sub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		expect(countPending(fx.projectA)).toBe(0);
		console.log("[VERIFY] R04 mkdir=EACCES pending=1 restored_retry=2 created=1");
	});

	it("open(wx) EROFS leaves pending; restored retry twice creates exactly one event", async () => {
		const fx = fixture();
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		fs.mkdirSync(issueAuthorityBasePath(fx.devRoot), { recursive: true });
		arm("authority-open", issueAuthorityLockPath(fx.devRoot), "EROFS");
		const result = await store(fx).submit(submitRequest(sub, actor));
		expect(fault.injections).toBe(1);
		expect(result.code).toBe("authority-unavailable");
		expect(result.state).toBe("pending");
		expect(result.submitted).toBe(false);
		expect(result.reason).toContain("EROFS");
		expect(fs.existsSync(issueAuthorityLockPath(fx.devRoot))).toBe(false);
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(countPending(fx.projectA)).toBe(1);

		fault.armed = false;
		const restored = store(fx);
		const first = await restored.retry({ actor, id: sub.id });
		expect(first.created).toBe(true);
		const second = await restored.retry({ actor, id: sub.id });
		expect(second.created).toBe(false);
		expect(readEvents(fx, sub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		console.log("[VERIFY] R04 open=EROFS pending=1 restored_retry=2 created=1");
	});

	it("own authority lock fsync failure tags preflight, cleans the lock and still leaves pending", async () => {
		const fx = fixture();
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		const lockPath = issueAuthorityLockPath(fx.devRoot);
		arm("lock-fsync", lockPath, "EIO");
		const result = await store(fx).submit(submitRequest(sub, actor));
		expect(fault.injections).toBe(1);
		expect(result.code).toBe("authority-unavailable");
		expect(result.state).toBe("pending");
		expect(result.submitted).toBe(false);
		expect(fs.existsSync(lockPath)).toBe(false);
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(countPending(fx.projectA)).toBe(1);

		fault.armed = false;
		const restored = store(fx);
		expect((await restored.retry({ actor, id: sub.id })).created).toBe(true);
		expect((await restored.retry({ actor, id: sub.id })).created).toBe(false);
		expect(readEvents(fx, sub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		console.log("[VERIFY] R04+R06 authority_fsync=preflight own_lock_cleaned=1 created=1");
	});

	it("does not turn a local lock I/O failure into a pending result", async () => {
		const fx = fixture();
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		arm("local-open", issueLocalLockPath(fx.projectA), "EACCES");
		await expect(store(fx).submit(submitRequest(sub, actor))).rejects.toThrow("E-ISSUE-STORE-WRITE_FAILED");
		expect(fault.injections).toBe(1);
		expect(countPending(fx.projectA)).toBe(0);
		expect(readIndex(fx.projectA)).toBeNull();
		expect(countAuthorityLogs(fx)).toBe(0);
		expect(fs.existsSync(issueAuthorityLockPath(fx.devRoot))).toBe(false);
		console.log("[VERIFY] R04 local_failure=raw_error pending=0 authority_lock_cleaned=1");
	});

	it("does not mask a corrupt authority log, a same-ID conflict or a partial authority write", async () => {
		const corruptFx = fixture();
		const corruptActor = pmActor(corruptFx.projectA);
		const corruptSub = makeSubmission();
		const logFile = issueAuthorityLogPath(corruptFx.devRoot, corruptSub.id);
		fs.mkdirSync(path.dirname(logFile), { recursive: true });
		fs.writeFileSync(logFile, '{"broken":true\n', "utf8");
		const before = snapshot(corruptFx.top);
		await expect(store(corruptFx).submit(submitRequest(corruptSub, corruptActor))).rejects.toThrow(
			"E-ISSUE-STORE-CORRUPT",
		);
		expect(snapshot(corruptFx.top)).toEqual(before);
		expect(countPending(corruptFx.projectA)).toBe(0);
		expect(fs.existsSync(issueAuthorityLockPath(corruptFx.devRoot))).toBe(false);

		const conflictFx = fixture();
		const conflictActor = pmActor(conflictFx.projectA);
		const first = makeSubmission();
		expect((await store(conflictFx).submit(submitRequest(first, conflictActor))).ok).toBe(true);
		const changed = makeSubmission({ id: first.id, title: "同 ID 不同标题" });
		const conflict = await store(conflictFx).submit(submitRequest(changed, conflictActor));
		expect(conflict.code).toBe("duplicate-conflict");
		expect(conflict.state).not.toBe("pending");
		expect(countPending(conflictFx.projectA)).toBe(0);

		const partialFx = fixture();
		const partialActor = pmActor(partialFx.projectA);
		const partialSub = makeSubmission();
		arm("authority-partial-write", "", "EIO");
		await expect(store(partialFx).submit(submitRequest(partialSub, partialActor))).rejects.toThrow(
			"E-ISSUE-STORE-WRITE_FAILED",
		);
		expect(fault.injections).toBe(1);
		expect(countAuthorityLogs(partialFx)).toBe(1);
		expect(readIndex(partialFx.projectA)?.records[0]?.state).toBe("in-flight");
		expect(fs.existsSync(issueAuthorityLockPath(partialFx.devRoot))).toBe(false);
		console.log("[VERIFY] R04 corrupt=raw conflict=raw partial_write=raw pending_claim=0");
	});

	it("keeps 待核实 / 已提交 (local ACK) instead of claiming 未提交 on preflight retry", async () => {
		const lostFx = fixture();
		const lostActor = pmActor(lostFx.projectA);
		const lostSub = makeSubmission();
		const lostStore = store(lostFx, {
			hooks: {
				afterAuthorityCommit: (commit) => {
					if (commit.created) throw new Error("simulated local ACK loss");
				},
			},
		});
		const lost = await lostStore.submit(submitRequest(lostSub, lostActor));
		expect(lost.code).toBe("ack-lost");
		expect(lost.state).toBe("in-flight");
		expect(readEvents(lostFx, lostSub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		arm("authority-open", issueAuthorityLockPath(lostFx.devRoot), "EACCES");
		const retried = await store(lostFx).retry({ actor: lostActor, id: lostSub.id });
		expect(fault.injections).toBe(1);
		expect(retried.code).toBe("authority-unavailable");
		expect(retried.state).toBe("in-flight");
		expect(retried.display).toBe(ISSUE_DISPLAY_VERIFY_PENDING);
		expect(retried.submitted).toBe(false);
		expect(retried.reason).toContain("EACCES");
		expect(countPending(lostFx.projectA)).toBe(1);
		expect(readIndex(lostFx.projectA)?.records[0]?.state).toBe("in-flight");

		const ackFx = fixture();
		const ackActor = pmActor(ackFx.projectA);
		const ackSub = makeSubmission();
		expect((await store(ackFx).submit(submitRequest(ackSub, ackActor))).ok).toBe(true);
		arm("authority-open", issueAuthorityLockPath(ackFx.devRoot), "EACCES");
		const ackRetry = await store(ackFx).retry({ actor: ackActor, id: ackSub.id });
		expect(ackRetry.code).toBe("authority-unavailable");
		expect(ackRetry.state).toBe("submitted");
		expect(ackRetry.submitted).toBe(true);
		expect(ackRetry.display).toBe(ISSUE_DISPLAY_SUBMITTED);
		expect(ackRetry.message).toContain("本地回执");
		expect(ackRetry.reason).toContain("EACCES");
		expect(readEvents(ackFx, ackSub.id).filter((event) => event.kind === "created")).toHaveLength(1);
		console.log("[VERIFY] R04 ack_lost=待核实 local_ack=已提交 no_false_未提交=1");
	});
});

// ── R06: own wx lock initialization failures ────────────────────────────────

const recoverableLockModes: FaultMode[] = ["lock-write", "lock-fsync", "lock-close"];

describe("T-09D R06: own wx lock initialization failures are safely released", () => {
	it.each(recoverableLockModes)("cleans %s failure without running the callback, then recovers", async (mode) => {
		const fx = fixture();
		const offline = offlineStore(fx);
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		const lockPath = issueLocalLockPath(fx.projectA);
		arm(mode, lockPath, "EIO");
		await expect(offline.submit(submitRequest(sub, actor))).rejects.toThrow("E-ISSUE-STORE-WRITE_FAILED");
		expect(fault.injections).toBe(1);
		expect(fs.existsSync(lockPath)).toBe(false);
		expect(countPending(fx.projectA)).toBe(0);
		expect(readIndex(fx.projectA)).toBeNull();

		fault.armed = false;
		const recovered = await offline.submit(submitRequest(sub, actor));
		expect(recovered.code).toBe("authority-unavailable");
		expect(recovered.state).toBe("pending");
		expect(countPending(fx.projectA)).toBe(1);
		expect(fs.existsSync(lockPath)).toBe(false);
		console.log(`[VERIFY] R06 ${mode}: callback=0 own_lock_cleaned=1 second_call=pending`);
	});

	it("preserves a competitor replacement after close failure and never runs the callback", async () => {
		const fx = fixture();
		const offline = offlineStore(fx);
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		const lockPath = issueLocalLockPath(fx.projectA);
		arm("lock-close-replace", lockPath, "EIO");
		await expect(offline.submit(submitRequest(sub, actor))).rejects.toThrow("E-ISSUE-STORE-WRITE_FAILED");
		expect(fault.injections).toBe(1);
		expect(fs.readFileSync(lockPath, "utf8")).toBe("FOREIGN-REPLACEMENT");
		expect(countPending(fx.projectA)).toBe(0);
		expect(readIndex(fx.projectA)).toBeNull();

		fault.armed = false;
		const blockedStore = offlineStore(fx, { lockOptions: { retries: 0, baseDelayMs: 1 } });
		const blocked = await blockedStore.submit(submitRequest(sub, actor));
		expect(blocked.code).toBe("lock-busy");
		expect(fs.readFileSync(lockPath, "utf8")).toBe("FOREIGN-REPLACEMENT");
		expect(countPending(fx.projectA)).toBe(0);
		console.log("[VERIFY] R06 close_replace: foreign_bytes=unchanged stale_steal=0 callback=0");
	});

	it("keeps a foreign EEXIST/stale lock byte-for-byte with no pending copy", async () => {
		const fx = fixture();
		const offline = offlineStore(fx, { lockOptions: { retries: 0, baseDelayMs: 1 } });
		const actor = pmActor(fx.projectA);
		const sub = makeSubmission();
		const lockPath = issueLocalLockPath(fx.projectA);
		fs.mkdirSync(path.dirname(lockPath), { recursive: true });
		fs.writeFileSync(lockPath, FOREIGN_LOCK);
		const result = await offline.submit(submitRequest(sub, actor));
		expect(result.code).toBe("lock-busy");
		expect(result.state).toBe("none");
		expect(fs.readFileSync(lockPath).equals(FOREIGN_LOCK)).toBe(true);
		expect(countPending(fx.projectA)).toBe(0);
		console.log("[VERIFY] R06 foreign_EEXIST=unchanged stale_cleanup=0 pending=0");
	});
});

// ── R07: raw string leaves / keys / metadata known-secret detection ──────────

describe("T-09D R07: raw known secrets and metadata fail closed before persistence", () => {
	it("detects a quote/backslash custom secret in a card field with zero persistent writes", async () => {
		const fx = fixture();
		const actor = pmActor(fx.projectA);
		const sub = makeCustomSecretSubmission(CUSTOM_QUOTE_BACKSLASH, (card) => {
			card.scene.actual = { ...card.scene.actual, value: CUSTOM_QUOTE_BACKSLASH };
		});
		const before = snapshot(fx.top);
		const result = await store(fx).submit(submitRequest(sub, actor));
		expect(result.ok).toBe(false);
		expect(result.code).toBe("credential-detected");
		expect(result.state).toBe("none");
		expect(snapshot(fx.top)).toEqual(before);
		console.log("[VERIFY] R07 card_quote_backslash=credential-detected writes=0");
	});

	it("detects a backslash custom secret in actor.by and a high-confidence token in metadata", async () => {
		const byFx = fixture();
		const bySub = makeCleanSubmission();
		const byActor = { ...pmActor(byFx.projectA), by: CUSTOM_BACKSLASH };
		const byBefore = snapshot(byFx.top);
		const byResult = await store(byFx).submit({
			actor: byActor,
			preparation: bySub.preparation,
			confirmation: bySub.confirmation,
			knownSecrets: [CUSTOM_BACKSLASH],
		});
		expect(byResult.code).toBe("credential-detected");
		expect(snapshot(byFx.top)).toEqual(byBefore);

		const tokenFx = fixture();
		const tokenSub = makeCleanSubmission();
		const tokenActor = { ...pmActor(tokenFx.projectA), by: HIGH_CONFIDENCE_TOKEN };
		const tokenBefore = snapshot(tokenFx.top);
		const tokenResult = await store(tokenFx).submit({
			actor: tokenActor,
			preparation: tokenSub.preparation,
			confirmation: tokenSub.confirmation,
			knownSecrets: [],
		});
		expect(tokenResult.code).toBe("invalid-input");
		expect(snapshot(tokenFx.top)).toEqual(tokenBefore);
		console.log("[VERIFY] R07 actor.by_known=credential-detected actor.by_shape=invalid-input writes=0");
	});

	it("detects newline custom secrets in progress and a quote/backslash/newline secret in reply", async () => {
		const fx = fixture();
		const actor = pmActor(fx.projectA);
		const dev = devActor(fx.devRoot);
		const clean = makeCleanSubmission();
		expect((await store(fx).submit(submitRequest(clean, actor))).ok).toBe(true);
		const before = authorityLogBytes(fx, clean.id);

		const fields: IssueProgressFields = {
			status: "修复中",
			statusNote: CUSTOM_NEWLINE,
			nextAction: null,
			fixCommit: null,
			releaseVersion: null,
			questionToReporter: null,
		};
		const progressContext = { id: clean.id, at: PROGRESS_AT, source: "dev-pm" as const, by: dev.by };
		const progressPreview = renderDevUpdatePreview(fields, progressContext);
		const progress = await devStore(fx).appendProgress({
			actor: dev,
			id: clean.id,
			update: fields,
			preview: progressPreview,
			confirmation: {
				confirmed: true,
				confirmedAt: PROGRESS_AT,
				previewSha256: sha256(progressPreview),
			},
			knownSecrets: [CUSTOM_NEWLINE],
		});
		expect(progress.ok).toBe(false);
		expect(progress.code).toBe("credential-detected");
		expect(authorityLogBytes(fx, clean.id).equals(before)).toBe(true);

		const replyFields: IssueReplyFields = { text: CUSTOM_REPLY, source: "user", inReplyTo: null };
		const replyContext = { id: clean.id, at: REPLY_AT, source: "project-pm" as const, by: actor.by };
		const replyPreview = renderReporterReplyPreview(replyFields, replyContext);
		const reply = await store(fx).reply({
			actor,
			id: clean.id,
			reply: replyFields,
			preview: replyPreview,
			confirmation: { confirmed: true, confirmedAt: REPLY_AT, previewSha256: sha256(replyPreview) },
			knownSecrets: [CUSTOM_REPLY],
		});
		expect(reply.ok).toBe(false);
		expect(reply.code).toBe("credential-detected");
		expect(authorityLogBytes(fx, clean.id).equals(before)).toBe(true);
		console.log(
			"[VERIFY] R07 progress_newline=credential-detected reply_control_secret=credential-detected writes=0",
		);
	});

	it("still accepts completed redaction markers and ordinary control text", async () => {
		const fx = fixture();
		const actor = pmActor(fx.projectA);
		const marker = makeMarkerSubmission();
		const markerResult = await store(fx).submit(submitRequest(marker, actor));
		expect(markerResult.ok).toBe(true);
		expect(markerResult.code).toBe("submitted");

		const clean = makeCleanSubmission();
		const cleanResult = await store(fx).submit(submitRequest(clean, actor));
		expect(cleanResult.ok).toBe(true);
		expect(cleanResult.code).toBe("submitted");

		const persisted = `${allTextUnder(issueAuthorityBasePath(fx.devRoot))}\n${allTextUnder(issueLocalBasePath(fx.projectA))}`;
		expect(persisted).toContain(REDACTION_MARK);
		expect(persisted).not.toContain(SECRET_A);
		expect(persisted).not.toContain(SECRET_B);
		expect(readEvents(fx, marker.id).filter((event) => event.kind === "created")).toHaveLength(1);
		expect(readEvents(fx, clean.id).filter((event) => event.kind === "created")).toHaveLength(1);
		console.log("[VERIFY] R07 redaction_marker=allowed ordinary_control_text=allowed created=2");
	});
});
