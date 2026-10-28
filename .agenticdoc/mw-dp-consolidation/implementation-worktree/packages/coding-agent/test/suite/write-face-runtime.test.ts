/**
 * write-face-runtime.test.ts — runtime write-surface gate for the full role set
 * (mw-write-face-guard W-05 / card T-W-I10 / design D-007 IP-1b).
 *
 * Until this card only `research` (the single `shell && writeless` role) was
 * guarded, and only on bash (`worker-mode.ts` `pi.on("tool_call")`). A `coding`
 * worker's `write`/`edit` had no runtime face at all, so a declared write face
 * was not enforced (spec risk 3). This suite locks the widened gate:
 *
 *  - AC-004: `write`/`edit` targets are judged against the declared face; a
 *    writable role's default face is the working tree (its work surface is
 *    `packages/**`), while the writeless default face stays own taskDir +
 *    `<key>/evidence/**` (spec risk 10 — the naive widening false-blocks every
 *    legitimate coding write).
 *  - AC-010: bash writes stay classified for every shell role.
 *  - AC-013: the `Write-Output a <term> --glob x` family (flag-shaped redirect
 *    operands, PowerShell here-strings, quoted `>`, comparisons, fd dups,
 *    null-device redirects) produces no candidate and therefore no false block.
 *  - D-003 direction: a not-statically-determinable bash target is never
 *    silently dropped — it is audited (`allow-unknown`).
 *  - D-115: `write_face:` is the authoritative allow carrier at runtime; a
 *    writable card that declares only `write_face:` (no `write_scope:`) is
 *    enforced, the two carriers intersect (fail-closed) when both are present,
 *    and a writable bash-less role (`roadmap-writer`) is guarded on
 *    `write`/`edit` (W-10 residuals R1/R3).
 *
 * No provider, key or network: the handlers are driven directly through a fake
 * ExtensionAPI in production registration order (same pattern as
 * `mwds-t03-bash-write-scope.test.ts`).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	type BashWriteScopeConfig,
	checkBashWriteScopeTarget,
	extractBashWriteCandidates,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const KEY = "wfr-key";
const TASK = "wfr-task";

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
}

const tempDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wfr-"));
	tempDirs.push(dir);
	return dir;
}

/** Realistic layout: <project>/.agenticdoc/<key>/workers/<task> + evidence,
 * plus one other key, packages/ and .git/ so the deny list is reachable. */
function makeFixture(): Fixture {
	const projectRoot = mkdtemp();
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, KEY);
	const taskDir = path.join(keyDir, "workers", TASK);
	for (const dir of [
		taskDir,
		path.join(keyDir, "evidence"),
		path.join(trueRoot, "other-key", "workers", "o1"),
		path.join(projectRoot, "packages", "coding-agent", "src"),
		path.join(projectRoot, "packages", "other"),
		path.join(projectRoot, ".git"),
	]) {
		fs.mkdirSync(dir, { recursive: true });
	}
	fs.writeFileSync(path.join(trueRoot, "_index.parallel"), "x\n", "utf8");
	fs.writeFileSync(path.join(keyDir, "pm-state.md"), "x\n", "utf8");
	fs.writeFileSync(path.join(keyDir, "workers", "_workers.parallel"), "x\n", "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir };
}

function writeTask(fx: Fixture, type: string, frontmatter: string[] = []): void {
	const lines = [`---`, `type: ${type}`, ...frontmatter, `---`, ``, `Do the task.`, ``];
	fs.writeFileSync(path.join(fx.taskDir, "task.md"), lines.join("\n"), "utf8");
}

// ── fake ExtensionAPI (production handler order) ─────────────────────────────

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	toolCall: (toolName: string, input: Record<string, unknown>) => { block?: boolean; reason?: string } | undefined;
	interceptorCount: () => number;
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
			// Production order (runner.emitToolCall): every handler runs, first block wins.
			for (const cb of handlers.get("tool_call") ?? []) {
				const result = cb({ type: "tool_call", toolCallId: "tc", toolName, input }) as
					| { block?: boolean; reason?: string }
					| undefined;
				if (result?.block) return result;
			}
			return undefined;
		},
		interceptorCount: () => handlers.get("tool_call")?.length ?? 0,
	};
}

let savedCwd = process.cwd();

beforeEach(() => {
	savedCwd = process.cwd();
});

afterEach(() => {
	process.chdir(savedCwd);
	delete process.env.PI_WORKER_TASK;
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

async function startWorker(fx: Fixture, type: string, frontmatter: string[] = []): Promise<FakeWorker> {
	writeTask(fx, type, frontmatter);
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

function traceLines(taskDir: string): string[] {
	const file = path.join(taskDir, "trace.log");
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line !== "");
}

// ── pure role-classified surface table (D-007 / spec risk 10) ────────────────

describe("role-classified surface (D-007)", () => {
	function config(projectRoot: string, roleClass: "writeless" | "writable"): BashWriteScopeConfig {
		const trueRoot = path.join(projectRoot, ".agenticdoc");
		const keyDir = path.join(trueRoot, KEY);
		return {
			projectRoot,
			trueRoot,
			keyDir,
			taskDir: path.join(keyDir, "workers", TASK),
			writeScope: undefined,
			roleClass,
		};
	}

	it("writeless keeps the historical face and deny set byte for byte", () => {
		const root = mkdtemp();
		const cfg = config(root, "writeless");
		// AC-005b: default face = own taskDir + <key>/evidence; packages/** denied.
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/wfr-key/workers/wfr-task/a.md", true).allowed).toBe(true);
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/wfr-key/evidence/e.md", true).allowed).toBe(true);
		expect(checkBashWriteScopeTarget(cfg, "packages/x.ts", true).rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, "README.md", true).rule).toBe("scope");
		// Omitting roleClass preserves the writeless surface (pure-function callers).
		const noRole: BashWriteScopeConfig = { ...cfg };
		delete noRole.roleClass;
		expect(checkBashWriteScopeTarget(noRole, "packages/x.ts", true).rule).toBe("deny");
		expect(checkBashWriteScopeTarget(noRole, "README.md", true).rule).toBe("scope");
	});

	it("writable default face is the working tree; packages/** is NOT denied", () => {
		const root = mkdtemp();
		const cfg = config(root, "writable");
		// D-007 / spec risk 10: the coding role's work surface is packages/**.
		expect(checkBashWriteScopeTarget(cfg, "packages/coding-agent/src/a.ts", true).allowed).toBe(true);
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/wfr-key/workers/wfr-task/a.md", true).allowed).toBe(true);
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/wfr-key/evidence/e.md", true).allowed).toBe(true);
		// The isolation red lines stay absolute for every role (goal alignment).
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/wfr-key/pm-state.md", true).rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/wfr-key/workers/_workers.parallel", true).rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/_index.parallel", true).rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/other-key/workers/o1/report.md", true).rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, ".git/config", true).rule).toBe("deny");
		// A target outside the repo root leaves the default face.
		expect(checkBashWriteScopeTarget(cfg, path.join("..", "..", "escape.ts"), true).rule).toBe("scope");
	});
});

// ── AC-004: write/edit on the declared face ─────────────────────────────────

describe("AC-004 write/edit runtime face", () => {
	it("declared write_scope allows in-face write/edit and blocks out-of-face", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding", ["write_scope: packages/coding-agent/src/**"]);
		// The guard is registered for the writable shell role too (D-007 IP-1b).
		expect(worker.interceptorCount()).toBe(1);

		// In the declared face -> allowed.
		expect(worker.toolCall("write", { path: "packages/coding-agent/src/a.ts", content: "x" })).toBeUndefined();
		expect(worker.toolCall("edit", { path: "packages/coding-agent/src/b.ts", edits: [] })).toBeUndefined();
		// The worker's own sandbox stays writable even under a declaration.
		expect(
			worker.toolCall("write", { path: `.agenticdoc/${KEY}/workers/${TASK}/notes.md`, content: "x" }),
		).toBeUndefined();
		expect(worker.toolCall("write", { path: `.agenticdoc/${KEY}/evidence/e.md`, content: "x" })).toBeUndefined();

		// Outside the declared face -> blocked (rule=write-scope).
		const outside = worker.toolCall("write", { path: "packages/other/x.ts", content: "x" });
		expect(outside?.block).toBe(true);
		expect(outside?.reason).toContain("rule=write-scope");
		expect(worker.toolCall("edit", { path: "README.md", edits: [] })?.block).toBe(true);

		// Cross key / .. escape / absolute path -> blocked, deny or scope first.
		const crossKey = worker.toolCall("write", { path: `.agenticdoc/other-key/workers/o1/report.md`, content: "x" });
		expect(crossKey?.block).toBe(true);
		expect(crossKey?.reason).toContain("rule=deny");
		const dotDotEscape = worker.toolCall("write", { path: "../../escape.ts", content: "x" });
		expect(dotDotEscape?.block).toBe(true);
		expect(dotDotEscape?.reason).toContain("rule=scope");
		const absolute = worker.toolCall("edit", { path: path.join(fx.projectRoot, "..", "abs-evil.ts"), edits: [] });
		expect(absolute?.block).toBe(true);
		expect(absolute?.reason).toContain("rule=scope");

		// Trace: one write-scope audit row per blocked write/edit, pattern=<tool>.
		const audit = traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE] "));
		expect(audit).toHaveLength(5);
		expect(audit.every((line) => line.includes("blocked=true") && line.includes("write-scope"))).toBe(true);
		expect(audit.some((line) => line.includes("pattern=write"))).toBe(true);
		expect(audit.some((line) => line.includes("pattern=edit"))).toBe(true);
		settle(worker);
	});

	it("writable role without write_scope is not false-blocked (core counter-example)", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding"); // no write_scope header

		// Every legitimate coding write passes (spec risk 10).
		const legitimate = [
			["write", { path: "packages/coding-agent/src/legit.ts", content: "x" }],
			["edit", { path: "packages/agent/src/x.ts", edits: [] }],
			["write", { path: `.agenticdoc/${KEY}/workers/${TASK}/output-notes.md`, content: "x" }],
			["write", { path: `.agenticdoc/${KEY}/evidence/legit.json`, content: "{}" }],
		] as const;
		for (const [tool, input] of legitimate) {
			expect(worker.toolCall(tool, input), `${tool} ${JSON.stringify(input)}`).toBeUndefined();
		}
		// The widened bash guard must not false-block the normal shell work either.
		for (const command of [
			"mkdir -p packages/coding-agent/foo",
			`python3 -c "open('packages/coding-agent/src/gen.ts','w').write('x')"`,
			"echo x > packages/coding-agent/src/out.ts",
			"find packages -name '*.tmp' -delete",
		]) {
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}

		// Allow-list hits leave no audit noise (P1), but the isolation red lines
		// still block: denyAlways is role-independent.
		for (const [tool, input] of [
			["write", { path: `.agenticdoc/${KEY}/pm-state.md`, content: "x" }],
			["write", { path: ".git/config", content: "x" }],
			["write", { path: ".agenticdoc/other-key/workers/o1/report.md", content: "x" }],
		] as const) {
			expect(worker.toolCall(tool, input)?.block, `${tool} ${JSON.stringify(input)}`).toBe(true);
		}
		expect(traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE] "))).toHaveLength(3);
		settle(worker);
	});
});

// ── AC-010: bash widening for writable shell roles ──────────────────────────

describe("AC-010 bash face for writable roles", () => {
	it("out-of-face bash writes are blocked; reads and unknowns still pass", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding", ["write_scope: packages/coding-agent/src/**"]);

		// Real writes outside the declared face -> blocked (deny or write-scope).
		const blocked = [
			["echo x > packages/other/y.ts", "rule=write-scope"],
			[`python3 -c "open('packages/other/y.ts','w').write('x')"`, "rule=write-scope"],
			["find . -name '*.tmp' -delete", "rule=write-scope"],
			["echo x > .agenticdoc/other-key/workers/o1/report.md", "rule=deny"],
			["echo x > /tmp/wfr-evil.ts", "rule=scope"],
		] as const;
		for (const [command, rule] of blocked) {
			const result = worker.toolCall("bash", { command });
			expect(result?.block, command).toBe(true);
			expect(result?.reason, command).toContain(rule);
		}

		// Pure reads pass with no audit line.
		for (const command of ['rg -n "foo" packages', "cat package.json", "git status --porcelain"]) {
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}
		// Not statically determinable -> never blocked, but audited (D-003).
		expect(worker.toolCall("bash", { command: "printf x > $T/out.ts" })).toBeUndefined();

		const audit = traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE] "));
		const blockedRows = audit.filter((line) => line.includes("blocked=true"));
		const unknownRows = audit.filter((line) => line.includes("rule=allow-unknown"));
		expect(blockedRows).toHaveLength(5);
		expect(unknownRows).toHaveLength(1);
		settle(worker);
	});

	it("blocked write/edit and bash writes share the [WRITE_SCOPE_SUMMARY] counters", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding");
		expect(worker.toolCall("write", { path: "packages/coding-agent/src/ok.ts", content: "x" })).toBeUndefined();
		expect(worker.toolCall("bash", { command: "echo x > packages/coding-agent/src/ok2.ts" })).toBeUndefined();
		expect(worker.toolCall("bash", { command: "printf x > $T/u.ts" })).toBeUndefined();
		expect(worker.toolCall("write", { path: `.agenticdoc/${KEY}/pm-state.md`, content: "x" })?.block).toBe(true);
		settle(worker);

		const summary = traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE_SUMMARY]"));
		expect(summary).toHaveLength(1);
		// 2 determined allows (1 write + 1 bash) + 1 deny + 1 allow-unknown.
		expect(summary[0]).toBe("[WRITE_SCOPE_SUMMARY] allow=2 deny=1 allow-unknown=1");
	});
});

// ── AC-013: the false-block family produces no candidate ────────────────────

describe("AC-013 false-block family", () => {
	/** The 11 measured/derived vectors: probe text, flag operands, PowerShell
	 * here-strings, quoted/comparison/fd-dup/null-device redirects. None is a
	 * real write, so none may produce a candidate or a block. */
	const FALSE_WRITE_VECTORS = [
		"Write-Output a <term> --glob x",
		"Write-Output a <term>",
		`Write-Output "probe: <term> --glob '!x' done"`,
		"$code = @'\ndon't do x > y\n'@\nWrite-Output $code",
		'[[ "$ts" > "2026-01-01" ]]',
		'echo "a > b"',
		`bash -c "grep -n '>' f"`,
		"rg -n -F TERM --glob '!node_modules' .",
		"echo x 2>&1",
		"Get-Content a.txt > /dev/null",
		"echo x > $null",
	];

	it("all 11 vectors yield zero candidates and are never blocked (research)", async () => {
		const fx = makeFixture();
		const cfg: BashWriteScopeConfig = {
			projectRoot: fx.projectRoot,
			trueRoot: fx.trueRoot,
			keyDir: fx.keyDir,
			taskDir: fx.taskDir,
			writeScope: undefined,
		};
		// Pure extractor: the AC-013 fix is in the lexer, before any verdict.
		for (const command of FALSE_WRITE_VECTORS) {
			expect(extractBashWriteCandidates(command), command).toEqual([]);
			expect(checkBashWriteScopeTarget(cfg, path.join("packages", "x.ts"), true).rule, command).toBe("deny");
		}
		// Behavior level: the research guard lets every one of them through.
		const worker = await startWorker(fx, "research");
		for (const command of FALSE_WRITE_VECTORS) {
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}
		expect(traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE]"))).toHaveLength(0);
		settle(worker);
	});

	it("the same false-write family also passes for a writable role", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding");
		for (const command of FALSE_WRITE_VECTORS) {
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}
		settle(worker);
	});
});

// ── research no-regression (in addition to mwds-t03) ────────────────────────

describe("research no-regression (AC-005b preserved)", () => {
	it("the research guard keeps its deny list, surface and summary counts", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");
		expect(worker.interceptorCount()).toBe(1);

		// Deny list (writeless): packages/** stays a hard block.
		expect(worker.toolCall("bash", { command: "echo x > packages/coding-agent/src/a.ts" })?.block).toBe(true);
		expect(worker.toolCall("bash", { command: "echo x > .agenticdoc/wfr-key/pm-state.md" })?.block).toBe(true);
		// Default face.
		expect(
			worker.toolCall("bash", { command: "printf x > .agenticdoc/wfr-key/workers/wfr-task/r.md" }),
		).toBeUndefined();
		expect(worker.toolCall("bash", { command: "printf x > .agenticdoc/wfr-key/evidence/e.md" })).toBeUndefined();
		// Outside the face (rule=scope) and unknown (allow-unknown) tiers.
		expect(worker.toolCall("bash", { command: "echo x > README.md" })?.block).toBe(true);
		expect(worker.toolCall("bash", { command: "printf x > $T/r.md" })).toBeUndefined();
		settle(worker);

		const audit = traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE] "));
		expect(audit.filter((line) => line.includes("blocked=true"))).toHaveLength(3);
		expect(audit.filter((line) => line.includes("rule=allow-unknown"))).toHaveLength(1);
		const summary = traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE_SUMMARY]"));
		expect(summary).toHaveLength(1);
		expect(summary[0]).toBe("[WRITE_SCOPE_SUMMARY] allow=2 deny=3 allow-unknown=1");
	});
});

// ── D-115 carrier convergence: `write_face:` is the runtime authority ────────
// W-10 residual R1: a writable card that declares only `write_face:` (the
// authoritative carrier rendered by both dispatch channels) had no runtime
// face at all — the gate read `write_scope:` only, so the declaration fell back
// to the working-tree default and every off-face repo write passed. These cases
// drive the REAL task.md text through `workerModeActivate`/`parseTaskMd` (never
// a bare pure-function call).

describe("D-115 write_face runtime authority", () => {
	it("single-line write_face: in-face writes pass; off-face (repo-internal / cross-key / `..` / absolute) block", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding", ["write_face: packages/coding-agent/src/**"]);
		expect(worker.interceptorCount()).toBe(1);

		// In-face on all three channels, plus the own-sandbox bookkeeping.
		expect(worker.toolCall("write", { path: "packages/coding-agent/src/a.ts", content: "x" })).toBeUndefined();
		expect(worker.toolCall("edit", { path: "packages/coding-agent/src/b.ts", edits: [] })).toBeUndefined();
		expect(worker.toolCall("bash", { command: "echo x > packages/coding-agent/src/c.ts" })).toBeUndefined();
		expect(
			worker.toolCall("write", { path: `.agenticdoc/${KEY}/workers/${TASK}/notes.md`, content: "x" }),
		).toBeUndefined();

		// Off-face but inside the working tree: only the declared face catches
		// this (the R1 counterexample — the default writable face is the whole
		// repo).
		const offGlob = worker.toolCall("write", { path: "packages/coding-agent/outside.ts", content: "x" });
		expect(offGlob?.block).toBe(true);
		expect(offGlob?.reason).toContain("rule=write-scope");
		const offGlobBash = worker.toolCall("bash", { command: "echo x > packages/coding-agent/outside2.ts" });
		expect(offGlobBash?.block).toBe(true);
		expect(offGlobBash?.reason).toContain("rule=write-scope");
		// Cross key -> the isolation deny list.
		const crossKey = worker.toolCall("write", {
			path: ".agenticdoc/other-key/workers/o1/report.md",
			content: "x",
		});
		expect(crossKey?.block).toBe(true);
		expect(crossKey?.reason).toContain("rule=deny");
		// `..` collapsing inside the repo -> still off the declared face.
		const dotDot = worker.toolCall("write", {
			path: "packages/coding-agent/src/../../../evil.ts",
			content: "x",
		});
		expect(dotDot?.block).toBe(true);
		expect(dotDot?.reason).toContain("rule=write-scope");
		// Absolute path outside the repo root -> outside the default face.
		const absolute = worker.toolCall("edit", { path: path.join(fx.projectRoot, "..", "abs-evil.ts"), edits: [] });
		expect(absolute?.block).toBe(true);
		expect(absolute?.reason).toContain("rule=scope");

		const audit = traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE] "));
		expect(audit.filter((line) => line.includes("blocked=true"))).toHaveLength(5);
		expect(audit.filter((line) => line.includes("detail=outside-declared-write-face"))).toHaveLength(3);
		// Dual-carrier audit must NOT fire: there is no `write_scope:` here.
		expect(traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_FACE] "))).toHaveLength(0);
		const taskMd = fs.readFileSync(path.join(fx.taskDir, "task.md"), "utf8").split("\n").slice(0, 4).join("\\n");
		process.stdout.write(
			`[EVIDENCE] d115-single task.md="${taskMd}" inFace=write/edit/bash:allow ` +
				`offGlob=${offGlob?.block ?? false} offGlobBash=${offGlobBash?.block ?? false} ` +
				`crossKey=${crossKey?.block ?? false} dotdot=${dotDot?.block ?? false} abs=${absolute?.block ?? false} ` +
				`audit_blocks=${audit.filter((line) => line.includes("blocked=true")).length}\n`,
		);
		settle(worker);
	});

	it("block-list write_face with a comma entry (D-113): each brace alternative is part of the face", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding", ["write_face:", "  - packages/coding-agent/src/{x,y}/**"]);
		expect(worker.interceptorCount()).toBe(1);
		const inX = worker.toolCall("write", { path: "packages/coding-agent/src/x/a.ts", content: "x" });
		const inY = worker.toolCall("write", { path: "packages/coding-agent/src/y/b.ts", content: "x" });
		expect(inX).toBeUndefined();
		expect(inY).toBeUndefined();
		const off = worker.toolCall("write", { path: "packages/coding-agent/src/z/c.ts", content: "x" });
		expect(off?.block).toBe(true);
		expect(off?.reason).toContain("rule=write-scope");
		process.stdout.write(
			`[EVIDENCE] d115-blocklist face=packages/coding-agent/src/{x,y}/** x_allow=${inX === undefined} y_allow=${inY === undefined} z_block=${off?.block ?? false}\n`,
		);
		settle(worker);
	});

	it("`*` does not cross `/` while `**` does (shared operator semantics, D-009)", async () => {
		const single = makeFixture();
		const star = await startWorker(single, "coding", ["write_face: packages/coding-agent/*.ts"]);
		expect(star.toolCall("write", { path: "packages/coding-agent/a.ts", content: "x" })).toBeUndefined();
		const deep = star.toolCall("write", { path: "packages/coding-agent/sub/a.ts", content: "x" });
		expect(deep?.block).toBe(true);
		expect(deep?.reason).toContain("rule=write-scope");
		settle(star);

		const doubled = makeFixture();
		const globstar = await startWorker(doubled, "coding", ["write_face: packages/coding-agent/**"]);
		expect(globstar.toolCall("write", { path: "packages/coding-agent/sub/a.ts", content: "x" })).toBeUndefined();
		settle(globstar);
	});

	it("case mode follows the platform (D-006: win32 insensitive, POSIX byte-exact)", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding", ["write_face: packages/coding-agent/SRC/**"]);
		const mismatchedCase = worker.toolCall("write", { path: "packages/coding-agent/src/a.ts", content: "x" });
		if (process.platform === "win32") expect(mismatchedCase).toBeUndefined();
		else {
			expect(mismatchedCase?.block).toBe(true);
			expect(mismatchedCase?.reason).toContain("rule=write-scope");
		}
		settle(worker);
	});

	it("declared face carrying unsupported syntax never fails open (fail-closed, D-006/D-111)", async () => {
		const fx = makeFixture();
		// `!(x)` is an unsupported extglob form: the shared operator cannot decide
		// it, so a target that is not provably inside a supported glob must be
		// blocked rather than admitted via the conservative `{unsupported}` result.
		const worker = await startWorker(fx, "coding", ["write_face: packages/coding-agent/!(x)/**"]);
		const off = worker.toolCall("write", { path: "packages/coding-agent/foo/bar.ts", content: "x" });
		expect(off?.block).toBe(true);
		expect(off?.reason).toContain("rule=write-scope");
		process.stdout.write(`[EVIDENCE] d115-unsupported fail_closed_block=${off?.block ?? false}\n`);
		settle(worker);
	});

	it("both carriers present and unequal -> intersection (fail-closed) + one audit line naming both", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding", [
			"write_face: packages/coding-agent/src/a/**",
			"write_scope: packages/coding-agent/src/a/b",
		]);
		// Inside both carriers -> allowed.
		expect(worker.toolCall("write", { path: "packages/coding-agent/src/a/b/c.ts", content: "x" })).toBeUndefined();
		// Inside write_face but outside the legacy write_scope -> the legacy carrier
		// narrows (never widens).
		const narrowed = worker.toolCall("write", { path: "packages/coding-agent/src/a/x.ts", content: "x" });
		expect(narrowed?.block).toBe(true);
		expect(narrowed?.reason).toContain("rule=write-scope");
		const audit = traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_SCOPE] "));
		expect(audit.some((line) => line.includes("detail=outside-declared-write-scope"))).toBe(true);
		settle(worker);

		const carriers = traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_FACE] "));
		expect(carriers).toHaveLength(1);
		expect(carriers[0]).toContain("carrier=dual");
		expect(carriers[0]).toContain("unequal=true");
		expect(carriers[0]).toContain('write_face=["packages/coding-agent/src/a/**"]');
		expect(carriers[0]).toContain('write_scope=["packages/coding-agent/src/a/b"]');
		expect(carriers[0]).toContain("intersection");
		process.stdout.write(`[EVIDENCE] d115-dual ${carriers[0]}\n`);
	});

	it("writable role without write_face falls back to the legacy write_scope (read-only compatibility)", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "coding", ["write_scope: packages/coding-agent/src/**"]);
		expect(worker.toolCall("write", { path: "packages/coding-agent/src/a.ts", content: "x" })).toBeUndefined();
		const outside = worker.toolCall("write", { path: "packages/other/x.ts", content: "x" });
		expect(outside?.block).toBe(true);
		expect(outside?.reason).toContain("rule=write-scope");
		expect(traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_FACE] "))).toHaveLength(0);
		settle(worker);
	});

	it("writeless role ignores write_face (D-115 rule 2: research stays byte-identical)", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research", ["write_face: packages/coding-agent/**"]);
		// If the authoritative carrier applied to research this would be allowed;
		// the writeless face keeps packages/** denied.
		const blocked = worker.toolCall("bash", { command: "echo x > packages/coding-agent/src/a.ts" });
		expect(blocked?.block).toBe(true);
		expect(blocked?.reason).toContain("rule=deny");
		expect(traceLines(fx.taskDir).filter((line) => line.startsWith("[WRITE_FACE] "))).toHaveLength(0);
		settle(worker);
	});
});

// ── D-115 rule 6: writable bash-less roles get the write/edit branch ────────

describe("D-115 guard installation (writable, no bash)", () => {
	it("roadmap-writer registers the guard on write/edit (bash sub-judgement stays off)", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "roadmap-writer", ["write_scope: packages/coding-agent/src/**"]);
		// R3: a writable but bash-less role had no runtime gate at all before.
		expect(worker.interceptorCount()).toBe(1);
		const inFace = worker.toolCall("write", { path: "packages/coding-agent/src/a.ts", content: "x" });
		expect(inFace).toBeUndefined();
		const off = worker.toolCall("write", { path: "packages/other/x.ts", content: "x" });
		expect(off?.block).toBe(true);
		expect(off?.reason).toContain("rule=write-scope");
		// The bash branch is only installed for roles that actually carry bash.
		const bashCall = worker.toolCall("bash", { command: "echo x > README.md" });
		expect(bashCall).toBeUndefined();
		process.stdout.write(
			`[EVIDENCE] d115-roadmap-writer interceptors=${worker.interceptorCount()} inFace_allow=${inFace === undefined} offFace_block=${off?.block ?? false} bash_judged=${bashCall !== undefined}\n`,
		);
		settle(worker);
	});
});
