/**
 * issue-root.test.ts — offline two-project fixture for the explicit, same-machine
 * MW dev repo binding (mw-issue-feedback T-02/T-08B, AC-001/003/006, VC-001/003/007).
 *
 * All paths are temp dirs injected through IssueDevRootLocator / pointerFile:
 * no network, no real machine pointer write, no service/bundle rebuild.
 * The fixture has a dev repo (authority) and a separate project (read-only
 * consumer); snapshots prove resolution and every failure branch write zero
 * bytes into both trees. T-08B adds byte-level foreign-temp ownership and
 * independent concurrent bind-window coverage.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	type BindIssueDevRootResult,
	bindIssueDevRoot,
	formatIssueDevRootFailure,
	ISSUE_DEV_ROOT_FILE_ENV,
	ISSUE_DEV_ROOT_HOME_ENV,
	ISSUE_DEV_ROOT_KIND,
	ISSUE_DEV_ROOT_MW_PY_RELATIVE,
	ISSUE_DEV_ROOT_NOTICE,
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
	ISSUE_DEV_ROOT_POINTER_KEYS,
	ISSUE_DEV_ROOT_WRITTEN_BY,
	type IssueDevRootFailure,
	type IssueDevRootPointer,
	type IssueDevRootResult,
	issueDevRootMarkerFingerprint,
	issueDevRootPointerPath,
	parseIssueDevRootPointer,
	type ResolveIssueDevRootOptions,
	resolveIssueDevRoot,
	serializeIssueDevRootPointer,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";

const START_CWD = process.cwd();
const temporaryRoots: string[] = [];

afterEach(() => {
	process.chdir(START_CWD);
	for (const dir of temporaryRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

interface Fixture {
	top: string;
	home: string;
	pointerFile: string;
	devRoot: string;
	devMwPy: string;
	externalRoot: string;
	env: NodeJS.ProcessEnv;
}

/** Independent canonicalization for assertions (native realpath + `\\?\` strip). */
function realPath(value: string): string {
	const real = fs.realpathSync.native(value);
	if (process.platform === "win32") {
		if (real.startsWith("\\\\?\\UNC\\")) return `\\\\${real.slice(8)}`;
		if (real.startsWith("\\\\?\\")) return real.slice(4);
	}
	return real;
}

function makeDevRepo(root: string): string {
	fs.mkdirSync(path.join(root, "packages", "multi-workers"), { recursive: true });
	const mwPy = path.join(root, "packages", "multi-workers", "mw.py");
	fs.writeFileSync(mwPy, "# offline fixture\n", "utf8");
	fs.mkdirSync(path.join(root, "packages", "coding-agent", "src", "extensions", "agent-team-loop"), {
		recursive: true,
	});
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".agenticdoc", "goal.md"), "# Project Goal\n", "utf8");
	return mwPy;
}

function fixture(): Fixture {
	const top = fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-root-"));
	temporaryRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	const devMwPy = makeDevRepo(devRoot);
	const externalRoot = path.join(top, "project-a");
	fs.mkdirSync(path.join(externalRoot, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(externalRoot, ".agenticdoc", "goal.md"), "# Project A goal\n", "utf8");
	return {
		top,
		home,
		devRoot,
		devMwPy,
		externalRoot,
		pointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME),
		env: { [ISSUE_DEV_ROOT_HOME_ENV]: home },
	};
}

/** Byte-level tree snapshot: path, type, size and content. */
function snapshot(root: string): string[] {
	if (!fs.existsSync(root)) return ["<absent>"];
	const out: string[] = [];
	const walk = (dir: string): void => {
		const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
		for (const entry of entries) {
			const full = path.join(dir, entry.name);
			const rel = path.relative(root, full);
			if (entry.isSymbolicLink()) {
				out.push(`l:${rel}:${fs.readlinkSync(full)}`);
			} else if (entry.isDirectory()) {
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

function validPointer(fx: Fixture, root: string = fx.devRoot, mwPy?: string): IssueDevRootPointer {
	return {
		schema: 1,
		kind: ISSUE_DEV_ROOT_KIND,
		canonical_dev_root: realPath(root),
		canonical_mw_py: realPath(mwPy ?? path.join(root, ISSUE_DEV_ROOT_MW_PY_RELATIVE)),
		marker_fingerprint: issueDevRootMarkerFingerprint(),
		written_by: ISSUE_DEV_ROOT_WRITTEN_BY,
		written_at: "2026-11-12T12:00:00.000Z",
		notice: ISSUE_DEV_ROOT_NOTICE,
	};
}

function writeRaw(pointerFile: string, raw: string): void {
	fs.writeFileSync(pointerFile, raw, "utf8");
}

function writeValidPointer(fx: Fixture, root?: string, mwPy?: string): IssueDevRootPointer {
	const pointer = validPointer(fx, root, mwPy);
	writeRaw(fx.pointerFile, serializeIssueDevRootPointer(pointer));
	return pointer;
}

function bind(fx: Fixture) {
	return bindIssueDevRoot({
		callerProjectRoot: fx.devRoot,
		candidateRoot: fx.devRoot,
		userConfirmed: true,
		pointerFile: fx.pointerFile,
		now: () => new Date("2026-11-12T12:00:00.000Z"),
	});
}

function resolve(fx: Fixture, projectRoot: string = fx.externalRoot, extra: Partial<ResolveIssueDevRootOptions> = {}) {
	return resolveIssueDevRoot({ projectRoot, env: fx.env, ...extra });
}

function expectFailure(
	result: IssueDevRootResult | BindIssueDevRootResult,
	code: IssueDevRootFailure["code"],
): IssueDevRootFailure {
	expect(result.ok).toBe(false);
	if (result.ok) throw new Error("expected a structured failure");
	const failure: IssueDevRootFailure = result;
	expect(failure.code).toBe(code);
	expect(failure.wrote).toBe(false);
	expect(failure.reason.length).toBeGreaterThan(0);
	expect(formatIssueDevRootFailure(failure)).toContain(code);
	return failure;
}

const ISSUE_ROOT_MODULE_URL = new URL("../../src/extensions/agent-team-loop/shared/issue-root.ts", import.meta.url)
	.href;

interface BindWindowOptions {
	callerProjectRoot: string;
	candidateRoot: string;
	pointerFile: string;
	writtenAt: string;
	readyFlag: string;
	startFlag: string;
	resultFlag: string;
}

interface BindWindowResult {
	ok: boolean;
	code?: string;
	reason?: string;
	pointer?: IssueDevRootPointer;
	bytes?: string;
	error?: string;
}

const BIND_WINDOW_SOURCE = `
import * as fs from "node:fs";
import { bindIssueDevRoot, serializeIssueDevRootPointer } from ${JSON.stringify(ISSUE_ROOT_MODULE_URL)};

const options = JSON.parse(process.env.MW_ISSUE_BIND_OPTIONS ?? "{}");
if (!options.readyFlag || !options.startFlag || !options.resultFlag) {
	throw new Error("missing bind window options");
}
fs.writeFileSync(options.readyFlag, "ready", "utf8");
while (!fs.existsSync(options.startFlag)) {
	await new Promise((resolve) => setTimeout(resolve, 5));
}
const report = (payload) => {
	const text = JSON.stringify(payload);
	process.stdout.write(text);
	fs.writeFileSync(options.resultFlag, text, "utf8");
};
try {
	const result = bindIssueDevRoot({
		callerProjectRoot: options.callerProjectRoot,
		candidateRoot: options.candidateRoot,
		userConfirmed: true,
		pointerFile: options.pointerFile,
		now: () => new Date(options.writtenAt),
	});
	if (result.ok) {
		report({ ok: true, pointer: result.pointer, bytes: serializeIssueDevRootPointer(result.pointer) });
	} else {
		report({ ok: false, code: result.code, reason: result.reason });
	}
} catch (error) {
	report({ ok: false, error: error instanceof Error ? error.message : String(error) });
}
`;

const RENAME_HOLD_PRELOAD = `
const fs = require("node:fs");
const original = fs.renameSync;
fs.renameSync = function (...args) {
	const hold = process.env.MW_ISSUE_RENAME_HOLD;
	if (hold) {
		while (fs.existsSync(hold)) {
			Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10);
		}
	}
	return original.apply(this, args);
};
`;

function foreignTmpBytes(): Buffer {
	return Buffer.from([0x46, 0x4f, 0x52, 0x45, 0x49, 0x47, 0x4e, 0x00, 0xff, 0x0a]);
}

function pointerDirEntries(fx: Fixture): string[] {
	return fs.readdirSync(path.dirname(fx.pointerFile)).sort();
}

function readBindWindowResult(file: string): BindWindowResult {
	const parsed: unknown = JSON.parse(fs.readFileSync(file, "utf8"));
	if (typeof parsed !== "object" || parsed === null) throw new Error("bind window result is not an object");
	return parsed as BindWindowResult;
}

async function waitForFiles(files: readonly string[], timeoutMs = 10_000): Promise<void> {
	const deadline = Date.now() + timeoutMs;
	while (!files.every((file) => fs.existsSync(file))) {
		if (Date.now() >= deadline) throw new Error(`timed out waiting for bind windows: ${files.join(", ")}`);
		await new Promise<void>((resolve) => setTimeout(resolve, 10));
	}
}

async function waitForAnyResult(files: readonly string[], timeoutMs = 10_000): Promise<BindWindowResult> {
	const deadline = Date.now() + timeoutMs;
	for (;;) {
		for (const file of files) {
			if (!fs.existsSync(file)) continue;
			try {
				return readBindWindowResult(file);
			} catch {
				// The result file is still being written.
			}
		}
		if (Date.now() >= deadline) throw new Error(`timed out waiting for a bind result: ${files.join(", ")}`);
		await new Promise<void>((resolve) => setTimeout(resolve, 10));
	}
}

function runBindWindow(options: BindWindowOptions, preload?: string, holdFlag?: string): Promise<BindWindowResult> {
	return new Promise((resolve, reject) => {
		const args = ["--no-warnings", "--experimental-strip-types"];
		if (preload) args.push("--require", preload);
		args.push("--input-type=module", "-e", BIND_WINDOW_SOURCE);
		const env: NodeJS.ProcessEnv = { ...process.env, MW_ISSUE_BIND_OPTIONS: JSON.stringify(options) };
		if (holdFlag) env.MW_ISSUE_RENAME_HOLD = holdFlag;
		const child = spawn(process.execPath, args, {
			cwd: START_CWD,
			env,
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
				reject(new Error(`bind window exited ${code}: ${stderr.trim() || stdout.trim()}`));
				return;
			}
			try {
				const parsed: unknown = JSON.parse(stdout);
				if (typeof parsed !== "object" || parsed === null) throw new Error("output is not an object");
				resolve(parsed as BindWindowResult);
			} catch (err) {
				reject(
					new Error(
						`bind window output is not JSON: ${err instanceof Error ? err.message : String(err)}; stderr=${stderr.trim()}`,
					),
				);
			}
		});
	});
}

describe("issue-root: pointer location and file format are pinned", () => {
	it("single machine-level pointer path with whole-file override precedence", () => {
		const fx = fixture();
		const expected = path.join(fx.home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME);
		expect(expected).toBe(path.join(fx.home, ".agents", "mw-issue-dev-root.json"));
		expect(issueDevRootPointerPath({ env: fx.env })).toBe(expected);
		expect(issueDevRootPointerPath({ home: fx.home, env: {} })).toBe(expected);
		expect(issueDevRootPointerPath({ env: { HOME: fx.home } })).toBe(expected);
		expect(issueDevRootPointerPath({ env: { USERPROFILE: fx.home } })).toBe(expected);
		expect(issueDevRootPointerPath({ env: { HOME: "", USERPROFILE: fx.home } })).toBe(expected);
		const override = path.join(fx.top, "override-pointer.json");
		expect(
			issueDevRootPointerPath({ env: { [ISSUE_DEV_ROOT_FILE_ENV]: override, [ISSUE_DEV_ROOT_HOME_ENV]: fx.home } }),
		).toBe(override);
		expect(
			issueDevRootPointerPath({
				pointerFile: override,
				env: { [ISSUE_DEV_ROOT_FILE_ENV]: path.join(fx.top, "other-pointer.json") },
			}),
		).toBe(override);
	});

	it("bind writes exactly the pinned UTF-8/LF JSON (no BOM, fixed key set)", () => {
		const fx = fixture();
		const bound = bind(fx);
		expect(bound.ok).toBe(true);
		if (!bound.ok) return;
		expect(bound.wrote).toBe(true);
		expect(bound.pointerPath).toBe(fx.pointerFile);
		const raw = fs.readFileSync(fx.pointerFile, "utf8");
		expect(raw.charCodeAt(0)).not.toBe(0xfeff);
		expect(raw).not.toContain("\r");
		expect(raw.endsWith("\n")).toBe(true);
		const parsed = JSON.parse(raw) as Record<string, unknown>;
		expect(Object.keys(parsed).sort()).toEqual([...ISSUE_DEV_ROOT_POINTER_KEYS].sort());
		expect(parsed.schema).toBe(1);
		expect(parsed.kind).toBe(ISSUE_DEV_ROOT_KIND);
		expect(parsed.canonical_dev_root).toBe(realPath(fx.devRoot));
		expect(parsed.canonical_mw_py).toBe(realPath(fx.devMwPy));
		expect(parsed.marker_fingerprint).toBe(issueDevRootMarkerFingerprint());
		expect(parsed.written_by).toBe(ISSUE_DEV_ROOT_WRITTEN_BY);
		expect(parsed.written_at).toBe("2026-11-12T12:00:00.000Z");
		expect(parsed.notice).toBe(ISSUE_DEV_ROOT_NOTICE);
		expect(String(parsed.notice)).toContain("Not an OS permission grant");
		expect(serializeIssueDevRootPointer(bound.pointer)).toBe(raw);
		expect(parseIssueDevRootPointer(raw)).toEqual({ ok: true, pointer: bound.pointer });
	});

	it("malformed pointer variants all fail as INVALID_POINTER, without writes", () => {
		const fx = fixture();
		const good = validPointer(fx);
		const variants: Array<{ name: string; raw: string }> = [
			{ name: "not JSON", raw: "{oops" },
			{ name: "JSON array", raw: "[]\n" },
			{ name: "UTF-8 BOM", raw: `\ufeff${serializeIssueDevRootPointer(good)}` },
			{ name: "wrong schema", raw: `${JSON.stringify({ ...good, schema: 2 }, null, 2)}\n` },
			{ name: "wrong kind", raw: `${JSON.stringify({ ...good, kind: "other" }, null, 2)}\n` },
			{ name: "missing field", raw: `${JSON.stringify({ ...good, marker_fingerprint: undefined }, null, 2)}\n` },
			{ name: "extra field", raw: `${JSON.stringify({ ...good, extra: "x" }, null, 2)}\n` },
			{ name: "relative root", raw: `${JSON.stringify({ ...good, canonical_dev_root: "mw-dev" }, null, 2)}\n` },
			{ name: "empty mw.py", raw: `${JSON.stringify({ ...good, canonical_mw_py: "" }, null, 2)}\n` },
			{
				name: "wrong fingerprint",
				raw: `${JSON.stringify({ ...good, marker_fingerprint: "sha256:bad" }, null, 2)}\n`,
			},
			{ name: "wrong written_by", raw: `${JSON.stringify({ ...good, written_by: "someone-else" }, null, 2)}\n` },
			{ name: "wrong notice", raw: `${JSON.stringify({ ...good, notice: "OS authorization granted" }, null, 2)}\n` },
			{ name: "empty written_at", raw: `${JSON.stringify({ ...good, written_at: "" }, null, 2)}\n` },
		];
		for (const variant of variants) {
			writeRaw(fx.pointerFile, variant.raw);
			const before = snapshot(fx.top);
			const result = resolve(fx);
			const failure = expectFailure(result, "E-ISSUE-DEV-ROOT-INVALID_POINTER");
			expect(failure.reason, variant.name).toBeTruthy();
			expect(snapshot(fx.top), variant.name).toEqual(before);
		}
	});
});

describe("issue-root: binding only from the dev repo pi window after confirmation", () => {
	it("refuses an unconfirmed bind and a foreign-window bind with zero writes", () => {
		const fx = fixture();
		const before = snapshot(fx.top);
		const unconfirmed = bindIssueDevRoot({
			callerProjectRoot: fx.devRoot,
			candidateRoot: fx.devRoot,
			userConfirmed: false,
			pointerFile: fx.pointerFile,
		});
		expectFailure(unconfirmed, "E-ISSUE-DEV-ROOT-BIND_NOT_CONFIRMED");
		expect(fs.existsSync(fx.pointerFile)).toBe(false);
		const foreign = bindIssueDevRoot({
			callerProjectRoot: fx.externalRoot,
			candidateRoot: fx.devRoot,
			userConfirmed: true,
			pointerFile: fx.pointerFile,
		});
		const failure = expectFailure(foreign, "E-ISSUE-DEV-ROOT-BIND_FOREIGN_WINDOW");
		expect(failure.reason).toContain("dev repo's own pi window");
		expect(fs.existsSync(fx.pointerFile)).toBe(false);
		expect(snapshot(fx.top)).toEqual(before);
	});

	it("refuses a missing pointer parent (no mkdir) and a candidate without markers", () => {
		const fx = fixture();
		const missingParent = path.join(fx.top, "no-home", ".agents", "pointer.json");
		const beforeDev = snapshot(fx.devRoot);
		const beforeHome = snapshot(fx.home);
		const unreachable = bindIssueDevRoot({
			callerProjectRoot: fx.devRoot,
			candidateRoot: fx.devRoot,
			userConfirmed: true,
			pointerFile: missingParent,
		});
		expectFailure(unreachable, "E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE");
		expect(fs.existsSync(path.dirname(missingParent))).toBe(false);
		expect(snapshot(fx.devRoot)).toEqual(beforeDev);
		expect(snapshot(fx.home)).toEqual(beforeHome);

		const notDev = path.join(fx.top, "not-dev");
		fs.mkdirSync(path.join(notDev, ".agenticdoc"), { recursive: true });
		fs.writeFileSync(path.join(notDev, ".agenticdoc", "goal.md"), "foreign goal\n", "utf8");
		const mismatch = bindIssueDevRoot({
			callerProjectRoot: notDev,
			candidateRoot: notDev,
			userConfirmed: true,
			pointerFile: fx.pointerFile,
		});
		expectFailure(mismatch, "E-ISSUE-DEV-ROOT-MARKER_MISMATCH");
		expect(fs.existsSync(fx.pointerFile)).toBe(false);
		expect(snapshot(fx.devRoot)).toEqual(beforeDev);
		expect(snapshot(fx.home)).toEqual(beforeHome);
	});

	it("refuses a pointer located inside the dev repo (not machine-readable by others)", () => {
		const fx = fixture();
		const localPointer = path.join(fx.devRoot, ".agents", "pointer.json");
		fs.mkdirSync(path.dirname(localPointer), { recursive: true });
		const result = bindIssueDevRoot({
			callerProjectRoot: fx.devRoot,
			candidateRoot: fx.devRoot,
			userConfirmed: true,
			pointerFile: localPointer,
		});
		expectFailure(result, "E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE");
		expect(fs.existsSync(localPointer)).toBe(false);
	});
});

describe("issue-root: read-only resolution and explicit failure branches", () => {
	it("resolves the bound dev root for another same-machine project and writes nothing", () => {
		const fx = fixture();
		expect(bind(fx).ok).toBe(true);
		const before = {
			home: snapshot(fx.home),
			dev: snapshot(fx.devRoot),
			external: snapshot(fx.externalRoot),
		};
		process.chdir(fx.externalRoot);
		const result = resolve(fx);
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.canonicalRoot).toBe(realPath(fx.devRoot));
		expect(result.canonicalMwPy).toBe(realPath(fx.devMwPy));
		expect(result.projectRoot).toBe(realPath(fx.externalRoot));
		expect(result.pointerPath).toBe(fx.pointerFile);
		expect(result.mode).toBe("external");
		expect(result.source).toBe("explicit-binding");
		expect(result.wrote).toBe(false);
		expect(result.markers).toHaveLength(3);
		for (const marker of result.markers) {
			expect(marker.startsWith(`${result.canonicalRoot}${path.sep}`)).toBe(true);
		}
		expect(snapshot(fx.home)).toEqual(before.home);
		expect(snapshot(fx.devRoot)).toEqual(before.dev);
		expect(snapshot(fx.externalRoot)).toEqual(before.external);
	});

	it("marks the dev repo itself as local mode", () => {
		const fx = fixture();
		expect(bind(fx).ok).toBe(true);
		const result = resolve(fx, fx.devRoot);
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.mode).toBe("local");
		expect(result.canonicalRoot).toBe(result.projectRoot);
	});

	it("missing pointer is NOT_CONFIGURED even from a valid dev repo cwd with installed-script hints", () => {
		const fx = fixture();
		process.chdir(fx.devRoot);
		const fakeMwPy = path.join(fx.externalRoot, "installed-mw.py");
		fs.writeFileSync(fakeMwPy, "# installed copy\n", "utf8");
		const before = snapshot(fx.top);
		const result = resolve(fx, fx.devRoot, {
			env: {
				...fx.env,
				MW_PY: fakeMwPy,
				PI_CODING_AGENT_DIR: path.join(fx.externalRoot, ".pi", "agent"),
			},
		});
		const failure = expectFailure(result, "E-ISSUE-DEV-ROOT-NOT_CONFIGURED");
		expect(failure.reason).toContain("no explicit MW dev repo binding");
		expect(fs.existsSync(fx.pointerFile)).toBe(false);
		expect(snapshot(fx.top)).toEqual(before);
	});

	it("whole-file override never silently falls back to a home pointer", () => {
		const fx = fixture();
		writeValidPointer(fx);
		const override = path.join(fx.top, "override-pointer.json");
		const result = resolve(fx, fx.externalRoot, {
			env: { [ISSUE_DEV_ROOT_HOME_ENV]: fx.home, [ISSUE_DEV_ROOT_FILE_ENV]: override },
		});
		const failure = expectFailure(result, "E-ISSUE-DEV-ROOT-NOT_CONFIGURED");
		expect(failure.pointerPath).toBe(override);
		expect(fs.existsSync(override)).toBe(false);

		const relativeOverride = path.join("relative", "pointer.json");
		const relative = resolve(fx, fx.externalRoot, {
			env: { [ISSUE_DEV_ROOT_FILE_ENV]: relativeOverride },
		});
		const relativeFailure = expectFailure(relative, "E-ISSUE-DEV-ROOT-INVALID_POINTER");
		expect(relativeFailure.reason).toContain("not absolute");
	});

	it("unreachable root / mw.py is UNREACHABLE; marker loss is MARKER_MISMATCH", () => {
		const fx = fixture();
		writeValidPointer(fx);
		fs.rmSync(fx.devRoot, { recursive: true, force: true });
		const beforeRootGone = snapshot(fx.devRoot);
		expectFailure(resolve(fx), "E-ISSUE-DEV-ROOT-UNREACHABLE");
		expect(snapshot(fx.devRoot)).toEqual(beforeRootGone);

		const fx2 = fixture();
		writeValidPointer(fx2);
		fs.rmSync(fx2.devMwPy);
		expectFailure(resolve(fx2), "E-ISSUE-DEV-ROOT-UNREACHABLE");

		const fx3 = fixture();
		writeValidPointer(fx3);
		const goal = path.join(fx3.devRoot, ".agenticdoc", "goal.md");
		fs.rmSync(goal);
		const before = snapshot(fx3.top);
		const markerFailure = expectFailure(resolve(fx3), "E-ISSUE-DEV-ROOT-MARKER_MISMATCH");
		expect(markerFailure.reason).toContain("goal.md");
		expect(snapshot(fx3.top)).toEqual(before);
	});

	it("a fake external marker tree and a wrong marker type are MARKER_MISMATCH with zero writes", () => {
		const fx = fixture();
		const fake = path.join(fx.top, "fake-dev");
		fs.mkdirSync(path.join(fake, "packages", "multi-workers"), { recursive: true });
		fs.writeFileSync(path.join(fake, ISSUE_DEV_ROOT_MW_PY_RELATIVE), "# fake\n", "utf8");
		fs.mkdirSync(path.join(fake, "packages", "coding-agent", "src", "extensions", "agent-team-loop"), {
			recursive: true,
		});
		// Deliberately no .agenticdoc/goal.md.
		writeValidPointer(fx, fake);
		const before = snapshot(fx.top);
		expectFailure(resolve(fx), "E-ISSUE-DEV-ROOT-MARKER_MISMATCH");
		expect(snapshot(fx.top)).toEqual(before);

		const fx2 = fixture();
		writeValidPointer(fx2);
		const goal = path.join(fx2.devRoot, ".agenticdoc", "goal.md");
		fs.rmSync(goal);
		fs.mkdirSync(goal, { recursive: true });
		expectFailure(resolve(fx2), "E-ISSUE-DEV-ROOT-MARKER_MISMATCH");
	});

	it("two distinct canonical roots, a mismatched mw.py copy and a disagreeing cross-check are AMBIGUOUS", () => {
		const fx = fixture();
		const repoB = path.join(fx.top, "mw-dev-b");
		makeDevRepo(repoB);
		writeValidPointer(fx, fx.devRoot, path.join(repoB, ISSUE_DEV_ROOT_MW_PY_RELATIVE));
		const before = snapshot(fx.top);
		const failure = expectFailure(resolve(fx), "E-ISSUE-DEV-ROOT-AMBIGUOUS");
		expect(failure.reason).toContain("two different dev roots");
		expect(snapshot(fx.top)).toEqual(before);

		const fx2 = fixture();
		const copy = path.join(fx2.devRoot, "packages", "multi-workers", "mw-copy.py");
		fs.writeFileSync(copy, "# copy\n", "utf8");
		writeValidPointer(fx2, fx2.devRoot, copy);
		const copyFailure = expectFailure(resolve(fx2), "E-ISSUE-DEV-ROOT-AMBIGUOUS");
		expect(copyFailure.reason).toContain("disagrees with the bound root's marker");

		const fx3 = fixture();
		writeValidPointer(fx3);
		expectFailure(
			resolve(fx3, fx3.externalRoot, { crossCheckRoots: [fx3.externalRoot] }),
			"E-ISSUE-DEV-ROOT-AMBIGUOUS",
		);
		const agreed = resolve(fx3, fx3.externalRoot, {
			crossCheckRoots: [path.join(fx3.devRoot, "packages", "..")],
		});
		expect(agreed.ok).toBe(true);
	});

	it("an unreachable current project root is PROJECT_UNREACHABLE (never used as authority)", () => {
		const fx = fixture();
		writeValidPointer(fx);
		const missing = path.join(fx.top, "missing-project");
		const result = resolve(fx, missing);
		const failure = expectFailure(result, "E-ISSUE-DEV-ROOT-PROJECT_UNREACHABLE");
		expect(failure.reason).toContain("current project root");
		expect(fs.existsSync(missing)).toBe(false);
	});

	it("both pointer sides are canonicalized: '..' and directory-link aliases stay one root", () => {
		const fx = fixture();
		const dotted = path.join(fx.devRoot, "packages", "..");
		writeRaw(
			fx.pointerFile,
			serializeIssueDevRootPointer({
				...validPointer(fx),
				canonical_dev_root: dotted,
				canonical_mw_py: path.join(dotted, ISSUE_DEV_ROOT_MW_PY_RELATIVE),
			}),
		);
		const dottedResult = resolve(fx);
		expect(dottedResult.ok).toBe(true);
		if (!dottedResult.ok) return;
		expect(dottedResult.canonicalRoot).toBe(realPath(fx.devRoot));
		expect(dottedResult.canonicalMwPy).toBe(realPath(fx.devMwPy));

		const link = path.join(fx.top, "dev-alias");
		let created = false;
		try {
			fs.symlinkSync(fx.devRoot, link, process.platform === "win32" ? "junction" : "dir");
			created = true;
		} catch {
			// Platform forbids directory links; the portable '..' case above still covers aliases.
		}
		if (!created) return;
		writeRaw(
			fx.pointerFile,
			serializeIssueDevRootPointer({
				...validPointer(fx),
				canonical_dev_root: link,
				canonical_mw_py: path.join(link, ISSUE_DEV_ROOT_MW_PY_RELATIVE),
			}),
		);
		const linkedResult = resolve(fx);
		expect(linkedResult.ok).toBe(true);
		if (!linkedResult.ok) return;
		expect(linkedResult.canonicalRoot).toBe(realPath(fx.devRoot));
		expect(linkedResult.canonicalMwPy).toBe(realPath(fx.devMwPy));
	});

	it("a marker that links to a foreign tree is rejected", () => {
		const fx = fixture();
		const foreign = path.join(fx.externalRoot, "linked-extension-dir");
		fs.mkdirSync(foreign, { recursive: true });
		const marker = path.join(fx.devRoot, "packages", "coding-agent", "src", "extensions", "agent-team-loop");
		fs.rmSync(marker, { recursive: true, force: true });
		let created = false;
		try {
			fs.symlinkSync(foreign, marker, process.platform === "win32" ? "junction" : "dir");
			created = true;
		} catch {
			// Platform forbids directory links; wrong-marker-type case covers the same guard.
		}
		if (!created) return;
		writeValidPointer(fx);
		const before = snapshot(fx.top);
		const failure = expectFailure(resolve(fx), "E-ISSUE-DEV-ROOT-MARKER_MISMATCH");
		expect(failure.reason).toContain("outside the bound root");
		expect(snapshot(fx.top)).toEqual(before);
	});
});

describe("issue-root: honest OS boundary and no machine side effects", () => {
	it("an out-of-band pointer edit is visible: the binding is not OS authorization", () => {
		const fx = fixture();
		expect(bind(fx).ok).toBe(true);
		const repoB = path.join(fx.top, "mw-dev-b");
		makeDevRepo(repoB);
		const tampered = validPointer(fx, repoB);
		writeRaw(fx.pointerFile, serializeIssueDevRootPointer(tampered));
		const result = resolve(fx);
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.canonicalRoot).toBe(realPath(repoB));
		expect(ISSUE_DEV_ROOT_NOTICE).toContain("Not an OS permission grant");
		expect(ISSUE_DEV_ROOT_NOTICE).toContain("same-OS user");
	});

	it("bind and resolve never touch the real machine pointer", () => {
		const realPointer = issueDevRootPointerPath();
		const before = fs.existsSync(realPointer) ? fs.readFileSync(realPointer, "utf8") : null;
		const fx = fixture();
		expect(bind(fx).ok).toBe(true);
		expect(resolve(fx).ok).toBe(true);
		expect(fs.existsSync(fx.pointerFile)).toBe(true);
		const after = fs.existsSync(realPointer) ? fs.readFileSync(realPointer, "utf8") : null;
		expect(after).toBe(before);
		expect(fx.pointerFile.startsWith(os.tmpdir())).toBe(true);
	});

	it("a foreign .tmp lock makes bind fail visibly and stays byte-identical", () => {
		const fx = fixture();
		writeValidPointer(fx);
		const pointerBefore = fs.readFileSync(fx.pointerFile);
		const foreignLock = `${fx.pointerFile}.tmp`;
		const foreignBytes = foreignTmpBytes();
		fs.writeFileSync(foreignLock, foreignBytes);
		const beforeHome = snapshot(fx.home);
		const result = bind(fx);
		const failure = expectFailure(result, "E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE");
		expect(failure.reason).toContain("another explicit bind");
		expect(fs.readFileSync(foreignLock).equals(foreignBytes)).toBe(true);
		expect(fs.readFileSync(fx.pointerFile).equals(pointerBefore)).toBe(true);
		expect(snapshot(fx.home)).toEqual(beforeHome);
		expect(pointerDirEntries(fx)).toEqual(
			[path.basename(fx.pointerFile), `${path.basename(fx.pointerFile)}.tmp`].sort(),
		);
	});
});

describe("issue-root: atomic bind owns only its own temporary files", () => {
	it("same-window explicit rebind succeeds and leaves no transient files", () => {
		const fx = fixture();
		expect(bind(fx).ok).toBe(true);
		const first = fs.readFileSync(fx.pointerFile, "utf8");
		const rebind = bindIssueDevRoot({
			callerProjectRoot: fx.devRoot,
			candidateRoot: fx.devRoot,
			userConfirmed: true,
			pointerFile: fx.pointerFile,
			now: () => new Date("2026-11-12T13:00:00.000Z"),
		});
		expect(rebind.ok).toBe(true);
		if (!rebind.ok) return;
		const second = fs.readFileSync(fx.pointerFile, "utf8");
		expect(second).not.toBe(first);
		expect(second).toBe(serializeIssueDevRootPointer(rebind.pointer));
		expect(pointerDirEntries(fx)).toEqual([path.basename(fx.pointerFile)]);
	});

	it("cleans only its own lock and unique temp when the final rename fails", () => {
		const fx = fixture();
		fs.mkdirSync(fx.pointerFile);
		fs.writeFileSync(path.join(fx.pointerFile, "occupied"), "x", "utf8");
		const beforeHome = snapshot(fx.home);
		const result = bind(fx);
		const failure = expectFailure(result, "E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE");
		expect(failure.reason).toContain("could not write pointer atomically");
		expect(snapshot(fx.home)).toEqual(beforeHome);
		expect(pointerDirEntries(fx)).toEqual([path.basename(fx.pointerFile)]);
	});

	it("two independent bind windows never silently rebind or delete foreign temp bytes", async () => {
		const fx = fixture();
		const repoB = path.join(fx.top, "mw-dev-b");
		makeDevRepo(repoB);
		const foreignSentinel = `${fx.pointerFile}.999999.deadbeef.tmp`;
		const foreignBytes = foreignTmpBytes();
		fs.writeFileSync(foreignSentinel, foreignBytes);
		const startFlag = path.join(fx.top, "start-binds.flag");
		const holdFlag = path.join(fx.top, "hold-rename.flag");
		const preload = path.join(fx.top, "hold-rename.cjs");
		const readyA = path.join(fx.top, "window-a.ready");
		const readyB = path.join(fx.top, "window-b.ready");
		const resultA = path.join(fx.top, "window-a.result.json");
		const resultB = path.join(fx.top, "window-b.result.json");
		fs.writeFileSync(preload, RENAME_HOLD_PRELOAD, "utf8");
		fs.writeFileSync(holdFlag, "hold", "utf8");

		const windows = [
			runBindWindow(
				{
					callerProjectRoot: fx.devRoot,
					candidateRoot: fx.devRoot,
					pointerFile: fx.pointerFile,
					writtenAt: "2026-11-12T12:00:00.000Z",
					readyFlag: readyA,
					startFlag,
					resultFlag: resultA,
				},
				preload,
				holdFlag,
			),
			runBindWindow(
				{
					callerProjectRoot: repoB,
					candidateRoot: repoB,
					pointerFile: fx.pointerFile,
					writtenAt: "2026-11-12T13:00:00.000Z",
					readyFlag: readyB,
					startFlag,
					resultFlag: resultB,
				},
				preload,
				holdFlag,
			),
		];
		let firstResult: BindWindowResult;
		try {
			await waitForFiles([readyA, readyB]);
			fs.writeFileSync(startFlag, "go", "utf8");
			firstResult = await waitForAnyResult([resultA, resultB]);
		} finally {
			fs.writeFileSync(startFlag, "go", "utf8");
			fs.rmSync(holdFlag, { force: true });
		}
		const results = await Promise.all(windows);
		expect(firstResult.ok).toBe(false);
		expect(firstResult.code).toBe("E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE");
		expect(firstResult.reason).toContain("another explicit bind");
		const winners = results.filter((result) => result.ok);
		const losers = results.filter((result) => !result.ok);
		expect(winners).toHaveLength(1);
		expect(losers).toHaveLength(1);
		const winner = winners[0];
		if (!winner?.bytes || !winner.pointer) throw new Error("winning bind window returned no pointer bytes");
		expect(fs.readFileSync(fx.pointerFile, "utf8")).toBe(winner.bytes);
		expect(parseIssueDevRootPointer(winner.bytes)).toEqual({ ok: true, pointer: winner.pointer });
		expect([realPath(fx.devRoot), realPath(repoB)]).toContain(winner.pointer.canonical_dev_root);
		expect(losers[0]?.code).toBe("E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE");
		expect(losers[0]?.reason).toContain("another explicit bind");
		expect(fs.readFileSync(foreignSentinel).equals(foreignBytes)).toBe(true);
		expect(fs.existsSync(`${fx.pointerFile}.tmp`)).toBe(false);
		expect(pointerDirEntries(fx)).toEqual([path.basename(fx.pointerFile), path.basename(foreignSentinel)].sort());
	});
});
