/**
 * issue-lock-preflight-toctou.test.ts — T-10 of key `mw-issue-feedback`.
 *
 * Read-only regression harness: proves (or refutes) the authority.lock preflight
 * TOCTOU in `issue-store.ts` `assertSafeRegularFile` (lstat succeeds ->
 * realpathSync.native on a lock the cooperative holder just deleted -> ENOENT).
 * This file ONLY adds tests. It never edits production code or the old 13 suites.
 *
 * It uses the real IssueStore appendProgress path, a synthetic temp dev repo,
 * a single submitted issue, and TWO independent Node child processes that load
 * the frozen TS source through absolute file:// URLs (strip-only loader). An ESM
 * fs preload, installed through real Node APIs (createRequire + module
 * syncBuiltinESMExports), intercepts ONLY the exact synthetic authority.lock
 * absolute path supplied by MW_HOOK_LOCK_PATH; every other path pass-through.
 * A bounded flag barrier forces the exact interleaving; no fixed sleeps, no
 * random sampling, no provider/network/auth/real-user reads. Full A/B child
 * diagnostics are emitted to the test log and copied to the run report, so the
 * evidence survives fixture tempdir cleanup.
 *
 * `control` keeps the lock present during B's realpath (no dangerous delete) ->
 * both processes written. `regression` deletes it in that window and asserts
 * the CORRECT behavior (both written); on the current unfixed store that
 * assertion is a genuine product-red whose message carries the ENOENT diagnosis.
 * The historical 12:31 root cause stays UNKNOWN; this only proves an independent
 * code-level defect.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	type Confirmation,
	type IssueDraft,
	type IssuePreparation,
	observedObservation,
	prepareIssue,
	unknownObservation,
	userObservation,
} from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	bindIssueDevRoot,
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	IssueStore,
	type IssueStoreActor,
	type IssueStoreOptions,
	issueAuthorityLockPath,
	issueAuthorityLogPath,
	newIssueId,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";

// ── Frozen synthetic constants (mirrors the read-only old suite) ────────────

const START_CWD = process.cwd();
const OCCURRED = "2026-11-12T14:02:11+08:00";
const SUBMITTED = "2026-11-12T21:10:00+08:00";
const OBSERVED_AT = "2026-11-12T21:09:58+08:00";
const CONFIRMED_AT = "2026-11-12T21:15:00+08:00";
const T1 = "2026-11-12T22:00:00+08:00";
const T2 = "2026-11-12T23:00:00+08:00";
const SECRET_A = "SENTINEL-APIKEY-9f3a2b7c";
const SECRET_B = "SUPERSECRET-VALUE-42";
const UNCONFIRMED = "UNCONFIRMED-RAW-SENTINEL-77";
const LONG_STEP = `1. 运行 /mw status; 2. 重启; 3. 再观察 ${"step-".repeat(120)} END`;
const LONG_ERROR = `ERROR serve-stale: ${"E".repeat(500)} END-OF-KEY-ERROR`;

const BARRIER_TIMEOUT_MS = 15_000;
const CHILD_HARD_TIMEOUT_MS = 40_000;

const FLAG = {
	aAtRelease: "A_at_release",
	letARelease: "let_A_release",
	aReleased: "A_released",
	bAtRealpath: "B_at_realpath",
	letBRealpath: "let_B_realpath",
	bRealpathDone: "B_realpath_done",
} as const;

const temporaryRoots: string[] = [];
afterEach(() => {
	for (const dir of temporaryRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

interface Fixture {
	top: string;
	ctl: string;
	devRoot: string;
	projectA: string;
	pointerFile: string;
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
	const top = fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-lock-toctou-"));
	temporaryRoots.push(top);
	const ctl = path.join(top, "ctl");
	fs.mkdirSync(ctl, { recursive: true });
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
	return { top, ctl, devRoot, projectA, pointerFile };
}

function baseDraft(id: string, projectLabel: string): IssueDraft {
	return {
		id,
		title: "/mw status 重启后显示旧 serve",
		projectLabel,
		component: unknownObservation(),
		occurredAt: userObservation(OCCURRED, SUBMITTED),
		trigger: userObservation("执行 /mw status 后重启 serve"),
		precondition: userObservation("serve 已运行超过一小时"),
		expected: userObservation("显示当前 serve 的 PID"),
		actual: userObservation("仍显示上一次启动的旧 PID"),
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

function makeSubmission(): {
	id: string;
	preparation: IssuePreparation;
	confirmation: Confirmation;
	knownSecrets: readonly string[];
} {
	const id = newIssueId();
	const knownSecrets: readonly string[] = [SECRET_A, SECRET_B];
	const preparation = prepareIssue(baseDraft(id, "project-A"), {
		submittedAt: SUBMITTED,
		environmentObservedAt: OBSERVED_AT,
		knownSecrets,
	});
	const confirmation: Confirmation = {
		confirmed: true,
		confirmedAt: CONFIRMED_AT,
		previewSha256: preparation.previewSha256,
	};
	return { id, preparation, confirmation, knownSecrets };
}

function pmActor(projectRoot: string): IssueStoreActor {
	return {
		role: "pm",
		scope: "project",
		projectRoot,
		projectLabel: "project-A",
		by: "pm-A",
		trustedWindow: true,
		writeAuthorized: true,
	};
}

function makeStore(fx: Fixture, projectRoot: string): IssueStore {
	const options: IssueStoreOptions = { projectRoot, env: {}, pointerFile: fx.pointerFile };
	return new IssueStore(options);
}

// ── Generated child + preload (runtime temp files, cleaned in afterEach) ────

const ISSUE_STORE_URL = new URL("../../src/extensions/agent-team-loop/shared/issue-store.ts", import.meta.url).href;

const PRELOAD_SOURCE = String.raw`"use strict";
import { createRequire } from 'node:module';
import { syncBuiltinESMExports } from 'node:module';
const require = createRequire(import.meta.url);
const fs = require('node:fs');
const nodePath = require('node:path');
const HOOK_DIR = process.env.MW_HOOK_DIR;
const ROLE = process.env.MW_HOOK_ROLE;
const FIXTURE_ROOT = process.env.MW_HOOK_FIXTURE_ROOT;
const EXPECTED_LOCK = process.env.MW_HOOK_LOCK_PATH;
if (!HOOK_DIR || !ROLE || !FIXTURE_ROOT || !EXPECTED_LOCK) {
	throw new Error('MW_HOOK_* synthetic fixture markers are missing');
}
if (!nodePath.isAbsolute(FIXTURE_ROOT) || !nodePath.isAbsolute(EXPECTED_LOCK) || !nodePath.isAbsolute(HOOK_DIR)) {
	throw new Error('MW_HOOK_* paths must be absolute');
}
const TIMEOUT = Number(process.env.MW_BARRIER_TIMEOUT_MS || '15000');
const sleepBuf = new Int32Array(new SharedArrayBuffer(4));
function sleepSync(ms) { Atomics.wait(sleepBuf, 0, 0, ms); }
function norm(p) { return nodePath.resolve(p).split("\\").join("/").toLowerCase(); }
const TARGET_ROOT = norm(FIXTURE_ROOT) + '/';
const TARGET_LOCK = norm(EXPECTED_LOCK);
if (!TARGET_LOCK.startsWith(TARGET_ROOT) || !norm(HOOK_DIR).startsWith(TARGET_ROOT)) {
	throw new Error('MW_HOOK_* paths escaped the synthetic fixture root');
}
// Only this exact synthetic lock path is intercepted; all other paths pass through.
function isSyntheticLock(p) { return typeof p === 'string' && norm(p) === TARGET_LOCK; }
const origExists = fs.existsSync;
const origWrite = fs.writeFileSync;
function flagPath(name) { return nodePath.join(HOOK_DIR, name); }
function emit(name) { origWrite.call(fs, flagPath(name), String(Date.now()), 'utf8'); }
function waitFlag(name) {
	const file = flagPath(name);
	const deadline = Date.now() + TIMEOUT;
	while (!origExists.call(fs, file)) {
		if (Date.now() >= deadline) throw new Error('child barrier timeout waiting for ' + name);
		sleepSync(4);
	}
}
const origUnlink = fs.unlinkSync;
const origRealpathNative = fs.realpathSync.native;
let unlinkFired = false;
let realpathFired = false;
function wrappedUnlink(p) {
	if (ROLE === 'A' && !unlinkFired && isSyntheticLock(p)) {
		unlinkFired = true;
		emit('A_at_release');
		waitFlag('let_A_release');
		const r = origUnlink.apply(fs, arguments);
		emit('A_released');
		return r;
	}
	return origUnlink.apply(fs, arguments);
}
function wrappedRealpathNative(p) {
	if (ROLE === 'B' && !realpathFired && isSyntheticLock(p)) {
		realpathFired = true;
		emit('B_at_realpath');
		waitFlag('let_B_realpath');
		try {
			return origRealpathNative.apply(fs.realpathSync, arguments);
		} finally {
			emit('B_realpath_done');
		}
	}
	return origRealpathNative.apply(fs.realpathSync, arguments);
}
fs.unlinkSync = wrappedUnlink;
fs.realpathSync.native = wrappedRealpathNative;
syncBuiltinESMExports();
`;

const CHILD_SOURCE = `import * as fs from 'node:fs';
import { syncBuiltinESMExports } from 'node:module';
import { IssueStore, issueTextSha256, renderDevUpdatePreview } from ${JSON.stringify(ISSUE_STORE_URL)};

// Re-sync so this module's node:fs namespace and issue-store.ts both observe
// the preload's hooks regardless of builtin module instantiation order.
syncBuiltinESMExports();
const options = JSON.parse(process.env.MW_ISSUE_CHILD_OPTIONS || '{}');
const report = (payload) => {
	const text = JSON.stringify(payload);
	process.stdout.write(text);
	fs.writeFileSync(options.resultFlag, text, 'utf8');
};
try {
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
		actor, id: options.id, update: fields, preview, confirmation, knownSecrets: [],
	});
	report({ ok: result.ok, code: result.code, seq: result.seq, eventSha: result.event ? result.event.sha256 : null });
} catch (error) {
	report({ ok: false, error: error instanceof Error ? error.message : String(error) });
}
`;

interface ChildOptions {
	projectRoot: string;
	actorRoot: string;
	pointerFile: string;
	id: string;
	projectLabel: string;
	by: string;
	scope: "dev";
	at: string;
	statusNote: string;
	resultFlag: string;
}

interface ChildResult {
	ok: boolean;
	code?: string;
	seq?: number;
	eventSha?: string | null;
	error?: string;
}

interface ChildOutcome {
	exitCode: number | null;
	signal: string | null;
	stdout: string;
	stderr: string;
	result: ChildResult | null;
	resultRaw: string | null;
}

function childEnv(fx: Fixture, role: "A" | "B", options: ChildOptions): NodeJS.ProcessEnv {
	// issueAuthorityLockPath canonicalizes devRoot through realpathSync.native.
	// On Windows that can expand an 8.3 temp path, so canonicalize the fixture
	// markers too; all of them still point only at this synthetic tempdir.
	const fixtureRoot = path.resolve(fs.realpathSync.native(path.resolve(fx.top)));
	const hookDir = path.resolve(fs.realpathSync.native(path.resolve(fx.ctl)));
	const lockPath = path.resolve(issueAuthorityLockPath(fx.devRoot));
	if (!lockPath.toLowerCase().startsWith(`${fixtureRoot.toLowerCase()}${path.sep}`)) {
		throw new Error(`fixture lock path escaped synthetic root: lock=${lockPath} root=${fixtureRoot}`);
	}
	const env: NodeJS.ProcessEnv = {
		...process.env,
		MW_HOOK_DIR: hookDir,
		MW_HOOK_FIXTURE_ROOT: fixtureRoot,
		MW_HOOK_LOCK_PATH: lockPath,
		MW_HOOK_ROLE: role,
		MW_BARRIER_TIMEOUT_MS: String(BARRIER_TIMEOUT_MS),
		MW_ISSUE_CHILD_OPTIONS: JSON.stringify(options),
	};
	// The store is constructed with env:{}; strip the worker marker anyway so a
	// MW worker context can never trip gateWrite inside the child process.
	delete env.PI_WORKER_TASK;
	return env;
}

function runChild(
	fx: Fixture,
	preloadUrl: string,
	childFile: string,
	role: "A" | "B",
	options: ChildOptions,
): Promise<ChildOutcome> {
	return new Promise((resolve, reject) => {
		const child = spawn(
			process.execPath,
			["--no-warnings", "--experimental-strip-types", "--import", preloadUrl, childFile],
			{ cwd: START_CWD, env: childEnv(fx, role, options), stdio: ["ignore", "pipe", "pipe"], windowsHide: true },
		);
		let stdout = "";
		let stderr = "";
		child.stdout?.on("data", (chunk: unknown) => {
			stdout += String(chunk);
		});
		child.stderr?.on("data", (chunk: unknown) => {
			stderr += String(chunk);
		});
		const timer = setTimeout(() => child.kill(), CHILD_HARD_TIMEOUT_MS);
		child.on("error", (error) => {
			clearTimeout(timer);
			reject(error);
		});
		child.on("close", (code, signal) => {
			clearTimeout(timer);
			// Keep the complete record in memory; the test log and run report are
			// the durable evidence after the synthetic temp fixture is removed.
			let result: ChildResult | null = null;
			let resultRaw: string | null = null;
			try {
				resultRaw = fs.readFileSync(options.resultFlag, "utf8");
				result = JSON.parse(resultRaw) as ChildResult;
			} catch {
				// Missing/invalid result stays null and is asserted by the caller.
			}
			resolve({ exitCode: code, signal, stdout, stderr, result, resultRaw });
		});
	});
}

function flagFile(fx: Fixture, name: string): string {
	return path.join(fx.ctl, name);
}

function emitFlag(fx: Fixture, name: string, label: string, order: string[]): void {
	fs.writeFileSync(flagFile(fx, name), String(Date.now()), "utf8");
	order.push(label);
}

async function waitFlag(fx: Fixture, name: string, label: string, order: string[]): Promise<void> {
	const file = flagFile(fx, name);
	const deadline = Date.now() + BARRIER_TIMEOUT_MS;
	while (!fs.existsSync(file)) {
		if (Date.now() >= deadline) throw new Error(`parent barrier timeout waiting for ${name}`);
		await new Promise<void>((resolve) => setTimeout(resolve, 5));
	}
	order.push(label);
}

interface AuthorityLogEvent {
	seq: unknown;
	sha256: unknown;
	prev_sha256: unknown;
}

interface Scenario {
	order: string[];
	orchestrationError: string | null;
	outA: ChildOutcome | null;
	outB: ChildOutcome | null;
	seqs: number[];
	chainOk: boolean;
	lockExistsAfter: boolean;
}

function childEventShas(out: ChildOutcome | null): string[] {
	const sha = out?.result?.eventSha;
	return typeof sha === "string" ? [sha] : [];
}

function outcomeDiagnosis(label: string, out: ChildOutcome | null): string {
	if (out === null) return `${label}={outcome:null}`;
	return `${label}=${JSON.stringify({
		exitCode: out.exitCode,
		signal: out.signal,
		stdout: out.stdout,
		stderr: out.stderr,
		result: out.result,
		resultRaw: out.resultRaw,
	})}`;
}

async function runScenario(fx: Fixture, id: string, mode: "control" | "race"): Promise<Scenario> {
	const childFile = path.join(fx.top, "child.mjs");
	const preloadFile = path.join(fx.top, "preload.mjs");
	fs.writeFileSync(childFile, CHILD_SOURCE, "utf8");
	fs.writeFileSync(preloadFile, PRELOAD_SOURCE, "utf8");
	const preloadUrl = pathToFileURL(preloadFile).href;

	const common = {
		projectRoot: fx.devRoot,
		actorRoot: fx.devRoot,
		pointerFile: fx.pointerFile,
		id,
		projectLabel: "mw-dev",
		scope: "dev" as const,
	};
	const optionsA: ChildOptions = {
		...common,
		by: "dev-pm-A",
		at: T1,
		statusNote: "holder A progress",
		resultFlag: path.join(fx.top, "result-A.json"),
	};
	const optionsB: ChildOptions = {
		...common,
		by: "dev-pm-B",
		at: T2,
		statusNote: "waiter B progress",
		resultFlag: path.join(fx.top, "result-B.json"),
	};

	const order: string[] = [];
	let orchestrationError: string | null = null;
	const childA = runChild(fx, preloadUrl, childFile, "A", optionsA);
	let childB: Promise<ChildOutcome> | null = null;
	try {
		// A boots, acquires authority.lock, appends, then blocks at the real
		// unlinkSync release while still holding the lock.
		await waitFlag(fx, FLAG.aAtRelease, "A:holds-lock-at-release-gate", order);
		// Only now spawn B: its preflight lstat deterministically sees A's lock.
		childB = runChild(fx, preloadUrl, childFile, "B", optionsB);
		await waitFlag(fx, FLAG.bAtRealpath, "B:paused-at-preflight-realpath", order);
		if (mode === "race") {
			// Force A to delete the lock inside B's lstat->realpath window.
			emitFlag(fx, FLAG.letARelease, "parent:let-A-release", order);
			await waitFlag(fx, FLAG.aReleased, "A:deleted-authority.lock", order);
			emitFlag(fx, FLAG.letBRealpath, "parent:let-B-realpath", order);
			await waitFlag(fx, FLAG.bRealpathDone, "B:called-realpath-on-missing-lock", order);
		} else {
			// Control: let B's realpath run while A still holds the lock.
			emitFlag(fx, FLAG.letBRealpath, "parent:let-B-realpath", order);
			await waitFlag(fx, FLAG.bRealpathDone, "B:realpath-returned-on-present-lock", order);
			emitFlag(fx, FLAG.letARelease, "parent:let-A-release", order);
			await waitFlag(fx, FLAG.aReleased, "A:deleted-authority.lock", order);
		}
	} catch (error) {
		orchestrationError = error instanceof Error ? error.message : String(error);
	} finally {
		// Always unblock any child parked on the bounded barriers; the hard
		// child timer guarantees both scenarios settle before fixture cleanup.
		for (const name of [FLAG.letARelease, FLAG.letBRealpath]) {
			if (!fs.existsSync(flagFile(fx, name))) fs.writeFileSync(flagFile(fx, name), "cleanup", "utf8");
		}
	}

	const pending: Promise<ChildOutcome>[] = [childA];
	if (childB !== null) pending.push(childB);
	const settled = await Promise.allSettled(pending);
	const outA = settled[0].status === "fulfilled" ? settled[0].value : null;
	const outB = settled.length > 1 && settled[1].status === "fulfilled" ? settled[1].value : null;

	const logPath = issueAuthorityLogPath(fx.devRoot, id);
	const lines = fs.existsSync(logPath)
		? fs
				.readFileSync(logPath, "utf8")
				.split("\n")
				.filter((line) => line.length > 0)
		: [];
	const events = lines.map((line) => JSON.parse(line) as AuthorityLogEvent);
	const seqs = events.map((event) => Number(event.seq));
	const shas = events.map((event) => String(event.sha256));
	const prevs = events.map((event) => String(event.prev_sha256));
	const chainOk =
		events.length > 0 &&
		shas.every((sha) => /^[0-9a-f]{64}$/.test(sha)) &&
		new Set(shas).size === shas.length &&
		events.every((_event, index) => index === 0 || prevs[index] === shas[index - 1]) &&
		seqs.every((seq, index) => seq === index + 1);
	const lockExistsAfter = fs.existsSync(issueAuthorityLockPath(fx.devRoot));
	return { order, orchestrationError, outA, outB, seqs, chainOk, lockExistsAfter };
}

function buildDiagnosis(s: Scenario): string {
	const bErr = s.outB?.result?.error ?? "(none)";
	const bCode = s.outB?.result?.code ?? "(none)";
	return [
		"stage=withExclusiveLock preflight assertSafeRegularFile (lstat->realpathSync.native) on authority.lock",
		"interleave=[A holds lock; B lstat saw A's lock; A unlinkSync released BEFORE B realpath; B realpath on deleted path]",
		`order=${JSON.stringify(s.order)}`,
		outcomeDiagnosis("A", s.outA),
		outcomeDiagnosis("B", s.outB),
		`A_summary={ok:${s.outA?.result?.ok},code:${s.outA?.result?.code},seq:${s.outA?.result?.seq}}`,
		`B_summary={ok:${s.outB?.result?.ok},code:${bCode},error:${bErr}}`,
		`B_exit=${s.outB?.exitCode} B_signal=${s.outB?.signal} B_stderr=${(s.outB?.stderr ?? "").trim() || "(empty)"}`,
		`authority_seqs=${JSON.stringify(s.seqs)} chainOk=${s.chainOk} leftoverLock=${s.lockExistsAfter}`,
		`orchestrationError=${s.orchestrationError ?? "none"}`,
	].join(" | ");
}

const RACE_ORDER = [
	"A:holds-lock-at-release-gate",
	"B:paused-at-preflight-realpath",
	"parent:let-A-release",
	"A:deleted-authority.lock",
	"parent:let-B-realpath",
	"B:called-realpath-on-missing-lock",
];
const CONTROL_ORDER = [
	"A:holds-lock-at-release-gate",
	"B:paused-at-preflight-realpath",
	"parent:let-B-realpath",
	"B:realpath-returned-on-present-lock",
	"parent:let-A-release",
	"A:deleted-authority.lock",
];

async function submittedId(fx: Fixture): Promise<string> {
	const sub = makeSubmission();
	const result = await makeStore(fx, fx.projectA).submit({
		actor: pmActor(fx.projectA),
		preparation: sub.preparation,
		confirmation: sub.confirmation,
		knownSecrets: sub.knownSecrets,
	});
	if (!result.ok) throw new Error(`fixture submit failed: ${result.reason}`);
	return sub.id;
}

describe("issue-lock preflight TOCTOU (frozen store, real dual-process barrier)", () => {
	it("control: both progress writers serialize to written with a valid seq/hash chain", async () => {
		const fx = fixture();
		const id = await submittedId(fx);
		const s = await runScenario(fx, id, "control");
		const diag = buildDiagnosis(s);
		console.log(`[CONTROL-DIAGNOSIS] ${diag}`);
		expect(s.orchestrationError).toBeNull();
		expect(s.order).toEqual(CONTROL_ORDER);
		expect(s.outA?.exitCode).toBe(0);
		expect(s.outB?.exitCode).toBe(0);
		expect(s.outA?.result).not.toBeNull();
		expect(s.outB?.result).not.toBeNull();
		expect(s.outA?.result?.ok).toBe(true);
		expect(s.outA?.result?.code).toBe("written");
		expect(s.outB?.result?.ok, `CONTROL diag: ${diag}`).toBe(true);
		expect(s.outB?.result?.code).toBe("written");
		expect(s.seqs).toEqual([1, 2, 3]);
		expect(s.chainOk).toBe(true);
		expect(s.lockExistsAfter).toBe(false);
		const shas = [...childEventShas(s.outA), ...childEventShas(s.outB)];
		expect(shas).toHaveLength(2);
		expect(new Set(shas).size).toBe(2);
	}, 60_000);

	it("regression: a lock release between lstat and realpath must not lose B (both must be written)", async () => {
		const fx = fixture();
		const id = await submittedId(fx);
		const s = await runScenario(fx, id, "race");
		const diag = buildDiagnosis(s);
		console.log(`[REGRESSION-DIAGNOSIS] ${diag}`);
		// Fixture/barrier proof: everything below (except the final acceptance)
		// holds on both the buggy and a fixed store, so a failure here is a
		// fixture error, not a product result.
		expect(s.orchestrationError).toBeNull();
		expect(s.order).toEqual(RACE_ORDER);
		expect(s.outA?.exitCode).toBe(0);
		expect(s.outB?.exitCode).toBe(0);
		expect(s.outA?.result).not.toBeNull();
		expect(s.outB?.result).not.toBeNull();
		expect(s.outA?.result?.ok).toBe(true);
		expect(s.outA?.result?.code).toBe("written");
		expect(s.chainOk).toBe(true);
		expect(s.lockExistsAfter).toBe(false);
		// Full product diagnosis (ENOENT + stage) is in the emitted log above.
		// ACCEPTANCE = expected CORRECT behavior: both processes written.
		// On the current unfixed store this is a genuine product-red; the
		// message carries the ENOENT diagnosis. After a minimal store fix it
		// turns green. We never assert the buggy ok=false.
		expect(s.outB?.result?.ok, diag).toBe(true);
		expect(s.outB?.result?.code).toBe("written");
		expect(s.seqs).toEqual([1, 2, 3]);
		const shas = [...childEventShas(s.outA), ...childEventShas(s.outB)];
		expect(shas).toHaveLength(2);
		expect(new Set(shas).size).toBe(2);
	}, 60_000);
});
