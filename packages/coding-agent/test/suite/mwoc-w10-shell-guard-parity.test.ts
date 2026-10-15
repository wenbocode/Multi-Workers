/**
 * mwoc-w10-shell-guard-parity.test.ts — T-10 / AC-016: the shell guard's ALLOW
 * face and the `write_scope:` parse are the write-surface single source.
 *
 * Three faces are exercised on the SAME target set:
 *   1. dispatch-time predicate  `pm/ui-bridge.ts::judgeWriteTarget`
 *      (delegating to `shared/write-surface.ts::judgeWriteTarget`),
 *   2. the narrow runtime channel `worker/worker-file-tool.ts::writeWorkerFile`,
 *   3. the shell guard `worker/worker-mode.ts::checkBashWriteScopeTarget`
 *      (plus a production `tool_call` integration section).
 *
 * For the writeless (`research`) role the three must agree on the common
 * target set. The DR1 ruling is a DESIGNED difference and is asserted as such:
 * a bash target is a cwd-resolved literal, so a keyDir-relative `evidence/x.md`
 * resolves to `<cwd>/evidence/x.md` and the shell channel stays fail-closed,
 * while the dual-basis dispatch/`worker_file` channels accept it. The same
 * cwd-resolved-literal rule makes bare basenames (`report.md`) shell-blocked
 * even though the basename channel accepts them; both classes are listed and
 * locked explicitly rather than flattened.
 *
 * The deliberately kept deny table is the shell-role-classified one (only it
 * makes `packages/**` writeless-only); the test proves the five shared rules
 * match `shared/write-surface.ts::pmWriteDenyReason` and that the one role
 * difference is exactly `packages/**`.
 *
 * No provider APIs, keys or network: the guard is invoked directly and through
 * a fake ExtensionAPI (same pattern as `mwds-t03-bash-write-scope.test.ts`).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { judgeWriteTarget as pmJudgeWriteTarget } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	evidenceDirOf,
	judgeWriteTarget as judgeSurfaceTarget,
	pmWriteDenyReason,
	resolveOwnWriteTarget,
	resolveWriteSurfacePaths,
} from "../../src/extensions/agent-team-loop/shared/write-surface.ts";
import { normalizeForCompare } from "../../src/extensions/agent-team-loop/worker/read-scope.ts";
import {
	resolveWorkerFileSurface,
	writeWorkerFile,
} from "../../src/extensions/agent-team-loop/worker/worker-file-tool.ts";
import {
	type BashWriteScopeConfig,
	checkBashWriteScopeTarget,
	parseTaskMd,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const KEY = "mwoc-w10";
const TASK = "w10-shell";

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

const tempDirs: string[] = [];
let savedCwd = process.cwd();

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
}

function mkFixture(taskBody = "---\ntype: research\n---\n\nwork\n"): Fixture {
	const projectRoot = fs.mkdtempSync(path.join(os.tmpdir(), "mwoc-w10-"));
	tempDirs.push(projectRoot);
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, KEY);
	const taskDir = path.join(keyDir, "workers", TASK);
	for (const dir of [
		taskDir,
		path.join(keyDir, "evidence", "research", "deep"),
		path.join(keyDir, "workers", "other-task"),
		path.join(trueRoot, "other-key", "workers", "o1"),
		path.join(projectRoot, "packages", "coding-agent", "src"),
		path.join(projectRoot, ".git"),
		path.join(projectRoot, "node_modules", "dep"),
	]) {
		fs.mkdirSync(dir, { recursive: true });
	}
	fs.writeFileSync(path.join(taskDir, "task.md"), taskBody, "utf8");
	fs.writeFileSync(path.join(trueRoot, "_index.parallel"), "x\n", "utf8");
	fs.writeFileSync(path.join(keyDir, "pm-state.md"), "x\n", "utf8");
	fs.writeFileSync(path.join(keyDir, "workers", "_workers.parallel"), "x\n", "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir };
}

interface Faces {
	dispatch: (token: string) => boolean;
	workerFile: (token: string) => boolean;
	shell: (token: string, roleClass?: "writeless" | "writable", writeScope?: string[]) => boolean;
	shellVerdict: (
		token: string,
		roleClass?: "writeless" | "writable",
		writeScope?: string[],
	) => ReturnType<typeof checkBashWriteScopeTarget>;
	config: BashWriteScopeConfig;
}

function faces(fx: Fixture): Faces {
	const pmCtx = { taskDir: fx.taskDir, projectRoot: fx.projectRoot, keyDir: fx.keyDir, trueRoot: fx.trueRoot };
	const surface = resolveWorkerFileSurface(fx.taskDir);
	const config: BashWriteScopeConfig = {
		projectRoot: fx.projectRoot,
		taskDir: fx.taskDir,
		keyDir: fx.keyDir,
		trueRoot: fx.trueRoot,
		writeScope: undefined,
		roleClass: "writeless",
	};
	return {
		config,
		dispatch: (token) => pmJudgeWriteTarget(token, pmCtx).allowed,
		workerFile: (token) => writeWorkerFile(fx.taskDir, token, "x\n", "write", surface).ok,
		shell: (token, roleClass = "writeless", writeScope = undefined) =>
			checkBashWriteScopeTarget({ ...config, roleClass, writeScope }, token, true).allowed,
		shellVerdict: (token, roleClass = "writeless", writeScope = undefined) =>
			checkBashWriteScopeTarget({ ...config, roleClass, writeScope }, token, true),
	};
}

beforeEach(() => {
	savedCwd = process.cwd();
});

afterEach(() => {
	process.chdir(savedCwd);
	delete process.env.PI_WORKER_TASK;
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

// ── three-face parity on the writeless role ─────────────────────────────────

describe("T-10 three-face parity (AC-016)", () => {
	it("the same target set yields the same verdict on all three faces", () => {
		const fx = mkFixture();
		const f = faces(fx);
		const rows: Array<{ token: string; allowed: boolean }> = [
			// allowed: own-key evidence face (project-root relative + absolute)
			{ token: `.agenticdoc/${KEY}/evidence/x.md`, allowed: true },
			{ token: `.agenticdoc/${KEY}/evidence/research/deep/notes.txt`, allowed: true },
			{ token: path.join(fx.keyDir, "evidence", "abs.md"), allowed: true },
			// refused: evidence dir itself is not a target
			{ token: `.agenticdoc/${KEY}/evidence`, allowed: false },
			// refused: other key / other task dir / framework files / repo source / .git / node_modules
			{ token: `.agenticdoc/other-key/evidence/x.md`, allowed: false },
			{ token: `.agenticdoc/other-key/workers/o1/report.md`, allowed: false },
			{ token: `.agenticdoc/${KEY}/workers/other-task/report.md`, allowed: false },
			{ token: `.agenticdoc/${KEY}/pm-state.md`, allowed: false },
			{ token: `.agenticdoc/${KEY}/workers/_workers.parallel`, allowed: false },
			{ token: `.agenticdoc/_index.parallel`, allowed: false },
			{ token: `packages/coding-agent/src/x.ts`, allowed: false },
			{ token: `.git/config`, allowed: false },
			{ token: `node_modules/dep/index.js`, allowed: false },
			{ token: `../..`, allowed: false },
		];
		const mismatches: string[] = [];
		for (const row of rows) {
			const d = f.dispatch(row.token);
			const w = f.workerFile(row.token);
			const s = f.shell(row.token);
			if (d !== row.allowed || w !== row.allowed || s !== row.allowed) {
				mismatches.push(`${row.token}: expected=${row.allowed} dispatch=${d} worker_file=${w} shell=${s}`);
			}
		}
		expect(mismatches).toEqual([]);
		verify(`[VERIFY] T-10 parity: cases=${rows.length} mismatches=0`);
	});

	it("DR1 exception: keyDir-relative evidence is accepted by dispatch/worker_file and fail-closed on the shell channel (designed)", () => {
		const fx = mkFixture();
		const f = faces(fx);
		const rows = ["evidence/x.md", "evidence/research/deep/notes.md"];
		for (const token of rows) {
			expect(f.dispatch(token), token).toBe(true);
			expect(f.workerFile(token), token).toBe(true);
			const verdict = f.shellVerdict(token);
			expect(verdict.allowed, token).toBe(false);
			expect(verdict.rule, token).toBe("scope");
		}
		// Direct lock on the basis switch: dual accepts, project-root-only refuses.
		const paths = resolveWriteSurfacePaths({
			taskDir: fx.taskDir,
			keyDir: fx.keyDir,
			trueRoot: fx.trueRoot,
			projectRoot: fx.projectRoot,
		});
		expect(judgeSurfaceTarget("evidence/x.md", { ...paths }).allowed).toBe(true);
		expect(resolveOwnWriteTarget("evidence/x.md", paths, { evidenceBasis: "dual" })).not.toBeNull();
		expect(
			resolveOwnWriteTarget("evidence/x.md", paths, { evidenceBasis: "project-root", basenameChannel: false }),
		).toBeNull();
		expect(evidenceDirOf(paths)).toBe(path.join(fx.keyDir, "evidence"));
		verify(`[VERIFY] T-10 DR1: cases=${rows.length} dispatch=true worker_file=true shell_blocked=true`);
	});

	it("shell-semantics divergence: a bare basename is cwd-relative to bash, so the shell channel blocks it (designed)", () => {
		const fx = mkFixture();
		const f = faces(fx);
		const rows = ["report.md", "progress.md", "report-abc.md"];
		for (const token of rows) {
			expect(f.dispatch(token), token).toBe(true);
			expect(f.workerFile(token), token).toBe(true);
			const verdict = f.shellVerdict(token);
			expect(verdict.allowed, token).toBe(false);
			expect(verdict.rule, token).toBe("scope");
		}
		verify(`[VERIFY] T-10 shell-literal: bare_basenames=${rows.length} shell_blocked=true`);
	});
});

// ── fail-closed evidence at the shell layer ─────────────────────────────────

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	toolCall: (toolName: string, input: Record<string, unknown>) => { block?: boolean; reason?: string } | undefined;
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => unknown>>();
	const pi = {
		on: (name: string, cb: (e: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: () => {},
		setActiveTools: () => {},
		registerTool: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		toolCall: (toolName: string, input: Record<string, unknown>) => {
			for (const cb of handlers.get("tool_call") ?? []) {
				const result = cb({ type: "tool_call", toolCallId: "tc", toolName, input }) as
					| { block?: boolean; reason?: string }
					| undefined;
				if (result?.block) return result;
			}
			return undefined;
		},
	};
}

async function startWorker(fx: Fixture, type: string): Promise<FakeWorker> {
	fs.writeFileSync(path.join(fx.taskDir, "task.md"), `---\ntype: ${type}\n---\n\nwork\n`, "utf8");
	process.env.PI_WORKER_TASK = path.join(fx.taskDir, "task.md");
	process.chdir(fx.projectRoot);
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return worker;
}

function settle(worker: FakeWorker): void {
	worker.emit("agent_end", { messages: [] });
	worker.emit("agent_settled");
}

describe("T-10 shell-layer fail-closed evidence (production tool_call)", () => {
	it("the 3 out-of-surface classes are blocked by the live guard", async () => {
		const fx = mkFixture();
		const worker = await startWorker(fx, "research");
		const cases: Array<{ id: string; command: string; rule: string }> = [
			{ id: "../..", command: "printf x > ../..", rule: "scope" },
			{
				id: "other-key",
				command: `printf x > .agenticdoc/other-key/workers/o1/report.md`,
				rule: "deny",
			},
			{ id: "repo-source", command: "printf x > packages/coding-agent/src/x.ts", rule: "deny" },
		];
		for (const row of cases) {
			const blocked = worker.toolCall("bash", { command: row.command });
			expect(blocked?.block, row.id).toBe(true);
			expect(blocked?.reason, row.id).toContain(`rule=${row.rule}`);
		}
		// DR1 end to end: keyDir-relative evidence blocked, project-root-relative allowed.
		expect(worker.toolCall("bash", { command: "printf x > evidence/x.md" })?.block).toBe(true);
		expect(worker.toolCall("bash", { command: `printf x > .agenticdoc/${KEY}/evidence/x.md` })).toBeUndefined();
		settle(worker);
		verify(`[VERIFY] T-10 shell-fail-closed: out_of_surface=3 blocked=3 dr1_blocked=true`);
	});
});

// ── deny table: shared rules vs the role-classified difference ──────────────

describe("T-10 deny classification (shared rules + kept role difference)", () => {
	it("the five shared deny rules match pmWriteDenyReason; only packages/** is role-classified", () => {
		const fx = mkFixture();
		const f = faces(fx);
		const paths = resolveWriteSurfacePaths({
			taskDir: fx.taskDir,
			keyDir: fx.keyDir,
			trueRoot: fx.trueRoot,
			projectRoot: fx.projectRoot,
		});
		const sharedTokens = [
			path.join(fx.keyDir, "pm-state.md"),
			path.join(fx.keyDir, "workers", "_workers.parallel"),
			path.join(fx.trueRoot, "_index.parallel"),
			path.join(fx.trueRoot, "other-key", "workers", "o1", "report.md"),
			path.join(fx.projectRoot, ".git", "config"),
		];
		for (const token of sharedTokens) {
			const expected = pmWriteDenyReason(paths, normalizeForCompare(fx.projectRoot, token));
			expect(expected, token).not.toBeNull();
			const verdict = f.shellVerdict(token);
			expect(verdict.rule, token).toBe("deny");
			expect(verdict.detail, token).toBe(`denied:${expected}`);
		}
		// Deliberately kept: writeless shell denies packages/**, writable shell allows it.
		const packagesToken = "packages/coding-agent/src/x.ts";
		expect(pmWriteDenyReason(paths, normalizeForCompare(fx.projectRoot, packagesToken))).toBe("packages/**");
		expect(f.shellVerdict(packagesToken, "writeless").detail).toBe("denied:packages/**");
		expect(f.shell(packagesToken, "writable")).toBe(true);
		verify(
			`[VERIFY] T-10 deny: shared_rules=${sharedTokens.length} matched=${sharedTokens.length} packages_writeless=deny packages_writable=allow`,
		);
	});
});

// ── write_scope: one implementation, one behaviour ──────────────────────────

describe("T-10 write_scope single implementation", () => {
	it("parseTaskMeta and worker_file load the same parser (source + behaviour)", () => {
		const fx = mkFixture();
		const taskPath = path.join(fx.taskDir, "task.md");
		// comma form
		fs.writeFileSync(
			taskPath,
			`---\ntype: research\nwrite_scope: .agenticdoc/${KEY}/evidence\n---\n\nwork\n`,
			"utf8",
		);
		const commaMeta = parseTaskMd(taskPath).writeScope;
		const commaSurface = resolveWorkerFileSurface(fx.taskDir).writeScope;
		expect(commaMeta).toEqual([`.agenticdoc/${KEY}/evidence`]);
		expect(commaSurface).toEqual(commaMeta);
		// YAML block-list form
		fs.writeFileSync(
			taskPath,
			`---\ntype: research\nwrite_scope:\n  - .agenticdoc/${KEY}/evidence\n---\n\nwork\n`,
			"utf8",
		);
		const listMeta = parseTaskMd(taskPath).writeScope;
		const listSurface = resolveWorkerFileSurface(fx.taskDir).writeScope;
		expect(listMeta).toEqual([`.agenticdoc/${KEY}/evidence`]);
		expect(listSurface).toEqual(listMeta);
		// absent header
		fs.writeFileSync(taskPath, `---\ntype: research\n---\n\nwork\n`, "utf8");
		expect(parseTaskMd(taskPath).writeScope).toBeUndefined();
		expect(resolveWorkerFileSurface(fx.taskDir).writeScope).toBeUndefined();

		const workerModeSrc = fs.readFileSync(
			path.join(REPO_ROOT, "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts"),
			"utf8",
		);
		expect(workerModeSrc).toContain("parseWriteScopeHeader(");
		expect(workerModeSrc).not.toContain('startsWith("write_scope:")');
		expect(workerModeSrc).not.toMatch(/function matchesWriteScopeEntry/);
		expect(workerModeSrc).not.toMatch(/const GLOB_MAGIC_RE/);
		expect(workerModeSrc).toContain("resolveOwnWriteTarget(");
		const surfaceSrc = fs.readFileSync(
			path.join(REPO_ROOT, "packages/coding-agent/src/extensions/agent-team-loop/shared/write-surface.ts"),
			"utf8",
		);
		expect(surfaceSrc).toContain("export function parseWriteScopeHeader");
		expect(surfaceSrc).toContain("export function matchesWriteScopeEntry");
		verify("[VERIFY] T-10 write_scope: comma=parity list=parity absent=parity one_impl=true");
	});

	it("a narrowed write_scope closes both runtime channels identically", () => {
		const fx = mkFixture();
		const narrow = [`.agenticdoc/${KEY}/evidence`];
		const f = faces(fx);
		// shell (a cwd-resolved literal inside the own taskDir, then narrowed away)
		expect(f.shellVerdict(`.agenticdoc/${KEY}/workers/${TASK}/report.md`, "writeless", narrow).rule).toBe(
			"write-scope",
		);
		expect(f.shellVerdict(`.agenticdoc/${KEY}/evidence/x.md`, "writeless", narrow).allowed).toBe(true);
		// worker_file
		const surface = { ...resolveWorkerFileSurface(fx.taskDir), writeScope: narrow };
		expect(writeWorkerFile(fx.taskDir, "progress.md", "x\n", "write", surface).ok).toBe(false);
		expect(writeWorkerFile(fx.taskDir, "evidence/x.md", "x\n", "write", surface).ok).toBe(true);
		verify("[VERIFY] T-10 write_scope-narrow: shell_blocked=true worker_file_blocked=true evidence_allowed=true");
	});

	it("the whole-repo scan finds exactly one write_scope: header parser", () => {
		const root = path.join(REPO_ROOT, "packages/coding-agent/src/extensions/agent-team-loop");
		const hits: string[] = [];
		const walk = (dir: string): void => {
			for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
				const full = path.join(dir, entry.name);
				if (entry.isDirectory()) walk(full);
				else if (entry.name.endsWith(".ts")) {
					if (fs.readFileSync(full, "utf8").includes('startsWith("write_scope:")')) {
						hits.push(path.relative(REPO_ROOT, full).replaceAll("\\", "/"));
					}
				}
			}
		};
		walk(root);
		expect(hits).toEqual(["packages/coding-agent/src/extensions/agent-team-loop/shared/write-surface.ts"]);
		verify(`[VERIFY] T-10 write_scope-scan: implementations=${hits.length} file=${hits[0]}`);
	});
});
