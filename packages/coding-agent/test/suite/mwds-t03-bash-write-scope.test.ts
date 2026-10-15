/**
 * mwds-t03-bash-write-scope.test.ts — AC-005b (VC-020…VC-024):
 * `research` (the only role with `bash` but no `write`/`edit`) could bypass its
 * narrow `worker_file` channel with a shell command (old gap R23). The
 * `tool_call` guard in `worker-mode.ts` now classifies KNOWN bash write
 * patterns, extracts the target paths and blocks only targets outside the
 * worker's write surface (own taskDir + `<key>/evidence/**`, narrowed by the
 * task's `write_scope:` header when present).
 *
 * P1 (design DD-03): the failure mode is a MISS, never a false block — pure-read
 * and unclassifiable commands must pass without a trace line. The deny list
 * (`pm-state.md`, `workers/_workers*`, `_index.parallel`, other keys,
 * `packages/**`, `.git/**`) is absolute priority and cannot be widened by a
 * `write_scope:` header.
 *
 * No provider APIs, keys or network: the `tool_call` handlers are invoked
 * directly against a fake ExtensionAPI (same pattern as
 * `autopilot-read-scope.test.ts`), iterating every registered handler in
 * production order and stopping at the first `block`.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	countWriteScopeResidualRisks,
	describeDispatchAlarm,
	recordWriteScopeResidualRisks,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	WRITE_SURFACE_MARKER,
	WRITE_SURFACE_MARKER_END,
	writeDispatchTaskMd,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	type BashWriteCandidate,
	type BashWriteScopeConfig,
	type BashWriteScopeVerdict,
	checkBashWriteScopeTarget,
	extractBashWriteCandidates,
	isShellRole,
	isWritelessRole,
	parseTaskMd,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const KEY = "mwds-t03";
const TASK = "t03-worker";

interface Fixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
}

const tempDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwds-t03-"));
	tempDirs.push(dir);
	return dir;
}

/** Realistic layout: <project>/.agenticdoc/<key>/workers/<task> + evidence,
 * plus one other key, packages/ and .git/ for the deny-list cases. */
function makeFixture(): Fixture {
	const projectRoot = mkdtemp();
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, KEY);
	const taskDir = path.join(keyDir, "workers", TASK);
	for (const dir of [
		taskDir,
		path.join(keyDir, "evidence"),
		path.join(keyDir, "workers", "_scratch"),
		path.join(trueRoot, "other-key", "workers", "o1"),
		path.join(projectRoot, "packages", "coding-agent", "src"),
		path.join(projectRoot, ".git"),
	]) {
		fs.mkdirSync(dir, { recursive: true });
	}
	fs.writeFileSync(path.join(trueRoot, "_index.parallel"), "x\n", "utf8");
	fs.writeFileSync(path.join(trueRoot, "goal.md"), "x\n", "utf8");
	fs.writeFileSync(path.join(keyDir, "pm-state.md"), "x\n", "utf8");
	fs.writeFileSync(path.join(keyDir, "workers", "_workers.parallel"), "x\n", "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir };
}

function writeTask(fx: Fixture, type: string, frontmatter: string[] = []): void {
	const lines = [`---`, `type: ${type}`, ...frontmatter, `---`, ``, `Do the research task.`, ``];
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
			// Production order (runner.emitToolCall): every handler runs, the
			// first `block` wins.
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

function writeScopeTraceLines(taskDir: string): string[] {
	return fs
		.readFileSync(path.join(taskDir, "trace.log"), "utf8")
		.split("\n")
		.filter((line) => line.startsWith("[WRITE_SCOPE]"));
}

// ── role capability predicates (contract C3) ─────────────────────────────────

describe("AC-005b role predicates (C3)", () => {
	it("research is the only writeless shell role", () => {
		expect(isShellRole("research")).toBe(true);
		expect(isWritelessRole("research")).toBe(true);

		for (const type of ["coding", "phase-writer", "repair", "roadmap-writer", "vision", "fallback"]) {
			expect(isWritelessRole(type), type).toBe(false);
		}
		for (const type of ["review", "verifier", "reviewer", "rag-research"]) {
			expect(isShellRole(type), type).toBe(false);
		}
	});
});

// ── VC-020: the five deny categories ─────────────────────────────────────────

describe("AC-005b deny list (VC-020)", () => {
	it("VC-020: five deny categories block with one write-scope audit line each", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");
		expect(worker.interceptorCount()).toBe(1);

		const denied: Array<[string, string, string]> = [
			["a", "echo x > .agenticdoc/mwds-t03/pm-state.md", "denied:pm-state.md"],
			["b", "echo x > .agenticdoc/mwds-t03/workers/_workers.parallel", "denied:workers/_workers*"],
			["c", "echo x >> .agenticdoc/_index.parallel", "denied:_index.parallel"],
			["d", "touch .agenticdoc/other-key/design.md", "denied:other key dir / .agenticdoc root"],
			["e", "mkdir -p packages/coding-agent/foo", "denied:packages/**"],
		];
		for (const [label, command, detail] of denied) {
			const result = worker.toolCall("bash", { command });
			expect(result?.block, label).toBe(true);
			expect(result?.reason, label).toContain("rule=deny");
			expect(result?.reason, label).toContain(detail.split(":")[1]);
		}

		const lines = writeScopeTraceLines(fx.taskDir);
		expect(lines).toHaveLength(5);
		expect(lines.every((line) => line.includes("write-scope") && line.includes("rule=deny"))).toBe(true);
		expect(lines[0]).toContain("detail=denied:pm-state.md");
		expect(lines[0]).toContain("cmd=echo x > .agenticdoc/mwds-t03/pm-state.md");
		settle(worker);
	});

	it("VC-020e2: .git/** is denied too", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");
		const result = worker.toolCall("bash", { command: "touch .git/config" });
		expect(result?.block).toBe(true);
		expect(result?.reason).toContain("rule=deny");
		const lines = writeScopeTraceLines(fx.taskDir);
		expect(lines).toHaveLength(1);
		expect(lines[0]).toContain("detail=denied:.git/**");
		settle(worker);
	});
});

// ── VC-021 / VC-022: allowed writes + pure reads + unclassifiable ────────────

describe("AC-005b allowed surface, pure reads, unclassifiable (VC-021/VC-022)", () => {
	it("VC-021+VC-022: own taskDir/evidence allowed; reads and unclassifiable commands pass with no audit noise", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");

		// (f) own surface
		const allowed = [
			"echo hi > .agenticdoc/mwds-t03/workers/t03-worker/report.md",
			"mkdir -p .agenticdoc/mwds-t03/workers/t03-worker/scratch",
			"cp /tmp/src.md .agenticdoc/mwds-t03/evidence/e.md",
			"tee .agenticdoc/mwds-t03/evidence/t.json",
			`python -c "open('.agenticdoc/mwds-t03/evidence/e2.md','w').write('x')"`,
		];
		for (const command of allowed) {
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}

		// (g) pure reads (>=6)
		const reads = [
			'rg -n "write_scope" .agenticdoc',
			'grep -rn "foo" packages/coding-agent/src',
			"ls -la .agenticdoc/mwds-t03/workers/t03-worker",
			'find . -name "*.md" -path "*workers*"',
			"cat .agenticdoc/mwds-t03/design.md",
			"git status --porcelain",
			"git log --oneline -5",
			"git diff --stat",
			`python -c "print(open('.agenticdoc/mwds-t03/design.md').read())"`,
			`node -e "console.log(require('fs').readFileSync('.agenticdoc/mwds-t03/design.md').toString())"`,
		];
		expect(reads.length).toBeGreaterThanOrEqual(6);
		for (const command of reads) {
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}

		// (h) unclassifiable commands (including a quoted `>` inside a read)
		for (const command of ['echo "a > b"', "foobar --flag value", "echo hello"]) {
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}

		expect(writeScopeTraceLines(fx.taskDir)).toHaveLength(0);
		settle(worker);
	});

	it("inline python/node read scripts pass, inline write scripts block", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");
		expect(worker.toolCall("bash", { command: `node -e "require('fs').readFileSync('x.md')"` })).toBeUndefined();
		const pyWrite = worker.toolCall("bash", {
			command: `python -c "open('.agenticdoc/mwds-t03/pm-state.md','w').write('x')"`,
		});
		expect(pyWrite?.block).toBe(true);
		expect(pyWrite?.reason).toContain("rule=deny");
		const nodeWrite = worker.toolCall("bash", {
			command: `node -e "require('fs').writeFileSync('.agenticdoc/other-key/workers/x.md','x')"`,
		});
		expect(nodeWrite?.block).toBe(true);
		expect(writeScopeTraceLines(fx.taskDir)).toHaveLength(2);
		settle(worker);
	});
});

// ── VC-023: write_scope consumer symmetry + single write point ───────────────

describe("AC-005b write_scope header (VC-023)", () => {
	function parseFrontmatter(frontmatter: string): ReturnType<typeof parseTaskMd> {
		const root = mkdtemp();
		const taskDir = path.join(root, KEY, "workers", TASK);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), `---\ntype: research\n${frontmatter}\n---\n\nwork\n`, "utf8");
		return parseTaskMd(path.join(taskDir, "task.md"));
	}

	it("parses the producer's one-line comma form and the read_scope block-list form; blank stays defined", () => {
		expect(parseFrontmatter("write_scope: .agenticdoc/k/workers/t, .agenticdoc/k/evidence").writeScope).toEqual([
			".agenticdoc/k/workers/t",
			".agenticdoc/k/evidence",
		]);
		expect(parseFrontmatter("write_scope:\n  - .agenticdoc/k/evidence").writeScope).toEqual([
			".agenticdoc/k/evidence",
		]);
		expect(parseFrontmatter("read_scope:\n  - .agenticdoc/k").writeScope).toBeUndefined();
		expect(parseFrontmatter("write_scope:").writeScope).toEqual([]);
	});

	it("the single write point renders no line for an absent/blank write_scope", () => {
		const root = mkdtemp();
		const deps = { agenticdocRoot: root, ownerKey: "_scratch" };
		const absent = writeDispatchTaskMd(deps, {
			taskKey: "t1",
			type: "research",
			body: "work",
			frontmatter: "type: research\n",
		});
		expect(fs.readFileSync(absent.path, "utf8")).toBe("type: research\n\nwork\n");
		const present = writeDispatchTaskMd(deps, {
			taskKey: "t2",
			type: "research",
			body: "work",
			frontmatter: "type: research\n",
			writeScope: "write_scope: .agenticdoc/k/workers/t, .agenticdoc/k/evidence",
		});
		expect(fs.readFileSync(present.path, "utf8")).toBe(
			"type: research\nwrite_scope: .agenticdoc/k/workers/t, .agenticdoc/k/evidence\n\nwork\n",
		);
		expect(parseTaskMd(present.path).writeScope).toEqual([".agenticdoc/k/workers/t", ".agenticdoc/k/evidence"]);
	});

	it("write_scope narrows the surface (intersection) and cannot widen past the deny list", async () => {
		const narrow = makeFixture();
		const worker = await startWorker(narrow, "research", ["write_scope: .agenticdoc/mwds-t03/evidence"]);
		expect(worker.toolCall("bash", { command: "echo hi > .agenticdoc/mwds-t03/evidence/e.md" })).toBeUndefined();
		const narrowed = worker.toolCall("bash", {
			command: "echo hi > .agenticdoc/mwds-t03/workers/t03-worker/report.md",
		});
		expect(narrowed?.block).toBe(true);
		expect(narrowed?.reason).toContain("rule=write-scope");
		settle(worker);

		const wide = makeFixture();
		const wideWorker = await startWorker(wide, "research", ["write_scope: ."]);
		// `write_scope: .` matches the path, but the default surface (taskDir +
		// evidence) is the intersection, so a project-root write stays blocked.
		const outside = wideWorker.toolCall("bash", { command: "echo hi > README.md" });
		expect(outside?.block).toBe(true);
		expect(outside?.reason).toContain("rule=scope");
		// The deny list is absolute priority over any write_scope.
		const pmState = wideWorker.toolCall("bash", { command: "echo hi > .agenticdoc/mwds-t03/pm-state.md" });
		expect(pmState?.block).toBe(true);
		expect(pmState?.reason).toContain("rule=deny");
		settle(wideWorker);
	});
});

// ── VC-024: guarded write roles (D-115 rule 7) ─────────────────────────────────────

describe("AC-005b guarded write roles (VC-024, D-115 rule 7)", () => {
	for (const type of ["coding", "repair", "vision"]) {
		it(`VC-024: ${type} registers the write-scope guard; declared-face writes pass and off-face writes block`, async () => {
			const fx = makeFixture();
			const worker = await startWorker(fx, type, ["write_face: packages/coding-agent/**"]);
			// D-115 rule 7 reverses the old "no guard for write roles" contract:
			// every writable shell role is guarded now.
			expect(worker.interceptorCount()).toBe(1);
			// The preserved substance of the old assertion: legitimate bash work is
			// not false-blocked by the widened guard.
			expect(worker.toolCall("bash", { command: "mkdir -p packages/coding-agent/foo" })).toBeUndefined();
			expect(worker.toolCall("bash", { command: "echo x > packages/coding-agent/src/out.ts" })).toBeUndefined();
			// NEW positive: an off-face write (inside the working tree, outside the
			// declared write_face) is blocked by the authoritative carrier.
			const offFace = worker.toolCall("bash", { command: "mkdir -p packages/other/foo" });
			expect(offFace?.block).toBe(true);
			expect(offFace?.reason).toContain("rule=write-scope");
			// The isolation red lines stay absolute for writable roles too.
			const deny = worker.toolCall("bash", { command: "echo x > .agenticdoc/mwds-t03/pm-state.md" });
			expect(deny?.block).toBe(true);
			expect(deny?.reason).toContain("rule=deny");
			const lines = writeScopeTraceLines(fx.taskDir);
			expect(lines).toHaveLength(2);
			expect(lines.some((line) => line.includes("detail=outside-declared-write-face"))).toBe(true);
			settle(worker);
		});
	}
});

// ── pure verdict matrix (config-level) ───────────────────────────────────────

describe("AC-005b verdict matrix (pure)", () => {
	function config(projectRoot: string, writeScope: string[] | undefined): BashWriteScopeConfig {
		const trueRoot = path.join(projectRoot, ".agenticdoc");
		const keyDir = path.join(trueRoot, KEY);
		return {
			projectRoot,
			trueRoot,
			keyDir,
			taskDir: path.join(keyDir, "workers", TASK),
			writeScope,
		};
	}

	/** VC-035 (spec AC-009): expected write targets for the mandatory pattern
	 * list, pinned as an EXTERNAL table instead of the old `targets.length > 0`
	 * criterion. The thin form stayed green for any non-empty result — e.g. a
	 * `truncate -s 0 a.txt` extraction that also returned the size operand `"0"`,
	 * or a `git apply` extraction that returned the subcommand name — while the
	 * exact table fails on a wrong target. Values are the measured semantics of
	 * the RQ-1 form inventory
	 * (`evidence/research/spec-form-inventory-20261011.md` §2.2/§2.3/§2.4),
	 * not a re-run of the implementation under test.
	 */
	const REQUIRED_WRITE_PATTERNS: Array<[string, string[]]> = [
		["echo x > a.txt", ["a.txt"]],
		["echo x >> a.txt", ["a.txt"]],
		["echo x | tee a.txt", ["a.txt"]],
		["cp a.txt b.txt", ["b.txt"]],
		["mv a.txt b.txt", ["b.txt"]],
		["rm a.txt", ["a.txt"]],
		["mkdir -p a", ["a"]],
		["touch a.txt", ["a.txt"]],
		["truncate -s 0 a.txt", ["a.txt"]],
		["sed -i s/a/b/ a.txt", ["a.txt"]],
		["git checkout -- a.txt", ["a.txt"]],
		["git clean -fd", ["."]],
		["git apply patch.diff", ["patch.diff"]],
		["curl -o a.txt https://example.invalid", ["a.txt"]],
		["wget -O a.txt https://example.invalid", ["a.txt"]],
		["Set-Content -Path a.txt -Value x", ["a.txt"]],
		["Out-File -FilePath a.txt", ["a.txt"]],
		["New-Item -ItemType Directory -Path a", ["a"]],
		["Remove-Item a.txt", ["a.txt"]],
	];

	it("extractBashWriteCandidates covers the required write patterns with exact targets (VC-035)", () => {
		const measured = REQUIRED_WRITE_PATTERNS.map(([command]): [string, string[]] => [
			command,
			extractBashWriteCandidates(command).map((c) => c.target),
		]);
		// Exact-target comparison for every row: a wrong target now fails here,
		// where `expect(targets.length).toBeGreaterThan(0)` could not see it.
		expect(Object.fromEntries(measured)).toEqual(Object.fromEntries(REQUIRED_WRITE_PATTERNS));
		// The row set itself must not shrink (guards against silently dropping a
		// required write pattern from the table).
		expect(REQUIRED_WRITE_PATTERNS).toHaveLength(19);
	});

	it("pure reads and unclassifiable commands extract nothing", () => {
		for (const command of [
			"rg foo",
			"grep -rn foo .",
			"ls -la",
			"find . -name '*.md'",
			"cat a.txt",
			"git status",
			"git log --oneline",
			'echo "a > b"',
			"foobar --flag",
		]) {
			expect(extractBashWriteCandidates(command), command).toEqual([]);
		}
	});

	it("checkBashWriteScopeTarget labels every rule", () => {
		const root = mkdtemp();
		const cfg = config(root, undefined);
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/mwds-t03/pm-state.md", true).rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, "packages/x.md", true).rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, "README.md", true).rule).toBe("scope");
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/mwds-t03/workers/t03-worker/report.md", true).allowed).toBe(
			true,
		);
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/mwds-t03/evidence/e.md", true).allowed).toBe(true);
		const narrowed = config(root, [".agenticdoc/mwds-t03/evidence"]);
		expect(checkBashWriteScopeTarget(narrowed, ".agenticdoc/mwds-t03/workers/t03-worker/report.md", true).rule).toBe(
			"write-scope",
		);
	});
});

// ── AC-002 write-form inventory (T-01 / VC-006…VC-010) ───────────────────────

describe("AC-002 write-form inventory (VC-006/VC-007/VC-010)", () => {
	function targetsOf(command: string): string[] {
		return extractBashWriteCandidates(command).map((candidate) => candidate.target);
	}

	function guardConfig(projectRoot: string, writeScope: string[] | undefined = undefined): BashWriteScopeConfig {
		const trueRoot = path.join(projectRoot, ".agenticdoc");
		const keyDir = path.join(trueRoot, KEY);
		return {
			projectRoot,
			trueRoot,
			keyDir,
			taskDir: path.join(keyDir, "workers", TASK),
			writeScope,
		};
	}

	it("VC-MWGF-006 / VC-006/VC-010: wrapper A-group extracts the inner target and its read-only twin does not", () => {
		const positives: Array<[string, string, string[]]> = [
			["bash -c", `bash -c "echo x > o1.txt"`, ["o1.txt"]],
			["sh -c", `sh -c "echo x > o2.txt"`, ["o2.txt"]],
			["zsh -c", `zsh -c "echo x > o3.txt"`, ["o3.txt"]],
			["dash -c", `dash -c "echo x > o4.txt"`, ["o4.txt"]],
			["ksh -c", `ksh -c "echo x > o5.txt"`, ["o5.txt"]],
			["cmd /c", `cmd /c "echo x > o6.txt"`, ["o6.txt"]],
			["powershell -Command", `powershell -Command "Set-Content -Path o7.txt -Value x"`, ["o7.txt"]],
			["pwsh -c", `pwsh -c "Set-Content -Path o8.txt -Value x"`, ["o8.txt"]],
			["perl -e", `perl -e "open(F,'>','o9.txt')"`, ["o9.txt"]],
			["ruby -e", `ruby -e "File.write('o10.txt','x')"`, ["o10.txt"]],
			["env VAR=x", "env FOO=bar cp a b", ["b"]],
			["sudo -u", "sudo -u root cp a b", ["b"]],
			["doas", "doas cp a b", ["b"]],
			["xargs sh -c", `xargs -n1 sh -c "echo x > o11.txt"`, ["o11.txt"]],
			["timeout N", "timeout 5 cp a b", ["b"]],
			["setsid", "setsid cp a b", ["b"]],
			["stdbuf -o0", "stdbuf -o0 cp a b", ["b"]],
			["nice -n", "nice -n 5 cp a b", ["b"]],
			["time -p", "time -p cp a b", ["b"]],
		];
		for (const [label, command, expected] of positives) {
			expect(targetsOf(command), `${label} :: ${command}`).toEqual(expected);
		}

		const negatives: Array<[string, string]> = [
			["bash -c read", `bash -c "rg -n foo ."`],
			["sh script file", "sh build.sh"],
			["zsh null target", `zsh -c "ls > /dev/null"`],
			["dash quoted >", `dash -c "grep -n '>' f"`],
			["ksh plain", `ksh -c "echo hi"`],
			["cmd dir", `cmd /c "dir"`],
			["powershell read", `powershell -Command "Get-Content a.txt"`],
			["pwsh read", `pwsh -c "Get-ChildItem"`],
			["perl print", `perl -e "print 1"`],
			["ruby read", `ruby -e "puts File.read('x')"`],
			["env ls", "env FOO=bar ls"],
			["sudo ls", "sudo -u root ls"],
			["doas ls", "doas ls"],
			["xargs grep", "xargs -n1 grep foo"],
			["timeout grep", "timeout 5 grep foo"],
			["setsid ls", "setsid ls"],
			["stdbuf ls", "stdbuf -o0 ls"],
			["nice echo", "nice -n 5 echo hi"],
			["time ls", "time -p ls"],
		];
		for (const [label, command] of negatives) {
			expect(targetsOf(command), `${label} :: ${command}`).toEqual([]);
		}
	});

	it("VC-MWGF-010 / VC-010 (T-18/A): an `.exe` wrapper unwraps like its bare name; non-wrapper `.exe` words are not writes", () => {
		// P-1 (QG-B2): the unwrap sets are exact-name matches, so `bash.exe -c`
		// produced zero candidates — a fail-open bypass. The `.exe` suffix now folds
		// to the bare name at the same command-position unwrap (`commandBasename`),
		// including the quoted absolute-path PowerShell call form.
		const wrapperPositives: Array<[string, string, string[]]> = [
			["bash.exe -c", `bash.exe -c "printf x > e1.txt"`, ["e1.txt"]],
			["cmd.exe /c", `cmd.exe /c "printf x > e2.txt"`, ["e2.txt"]],
			["powershell.exe -Command", `powershell.exe -Command "Set-Content -Path e3.txt -Value x"`, ["e3.txt"]],
			["& quoted absolute path", `& "D:\\Program Files\\Git\\bin\\bash.exe" -c "printf x > e4.txt"`, ["e4.txt"]],
			["quoted absolute path", `"C:\\Program Files\\Git\\bin\\bash.exe" -c "printf x > e5.txt"`, ["e5.txt"]],
			// T-20/H-2: built with `path.win32.join` so the win32 separator form is
			// constructed platform-independently; after the `commandBasename` fix it
			// folds on POSIX too (the old `path.basename` used the host semantics and
			// left `D:\...\bash.exe` unfolded on Linux CI).
			[
				"path.win32.join absolute path",
				`"${path.win32.join("D:", "Program Files", "Git", "bin", "bash.exe")}" -c "printf x > e6.txt"`,
				["e6.txt"],
			],
		];
		for (const [label, command, expected] of wrapperPositives) {
			expect(targetsOf(command), `${label} :: ${command}`).toEqual(expected);
		}

		// Anti-examples: a `.exe` word that is an operand is not a command, so it
		// must never be judged a write (only a real redirect target is).
		for (const command of ["ls -la foo.exe", "grep x file.exe", `ls -la foo.exe 2>&1`]) {
			expect(targetsOf(command), command).toEqual([]);
		}
		expect(targetsOf(`ls -la foo.exe > listing.txt`)).toEqual(["listing.txt"]);
	});

	it("T-18/B (content is not a target): the QG-B2 P-2 forms yield only the real path", () => {
		// QG-B2 P-2 reported runtime false blocks whose target came from the
		// CONTENT of a write command (`[[`, `)`, `<MISSING>`). Current source must
		// extract only the `-Path` operand; a content token is never a target.
		const hereString = [
			"Set-Content -Path o.txt -Value @'",
			`[[ "$ts" > "2026-01-01" ]]`,
			"missing: <MISSING>",
			"x ))",
			"'@",
		].join("\n");
		const commands = [
			`Set-Content -Path "o.txt" -Value "x [[ y"`,
			`Set-Content -Path "o.txt" -Value "x )) y"`,
			`Set-Content -Path "o.txt" -Value 'printf x > out.txt'`,
			hereString,
			`powershell -Command "${hereString.replaceAll('"', '\\"')}"`,
		];
		for (const command of commands) {
			expect(targetsOf(command), command).toEqual(["o.txt"]);
		}
	});

	it("VC-MWGF-009 / VC-009: B-group redirect operators are three-state (>| and >& target, fd-dup does not)", () => {
		expect(targetsOf("echo x >| r3.txt")).toEqual(["r3.txt"]);
		expect(targetsOf("echo x >& r5.txt")).toEqual(["r5.txt"]);
		expect(targetsOf("echo x &> r6.txt")).toEqual(["r6.txt"]);
		expect(targetsOf("echo x <> r4.txt")).toEqual(["r4.txt"]);
		expect(targetsOf("echo x 2> r7.txt")).toEqual(["r7.txt"]);
		for (const command of ["echo x 2>&1", "echo x >&2", "exec 3>&-"]) {
			expect(targetsOf(command), command).toEqual([]);
		}
	});

	it("VC-006: C-group operands (install/dd/ln/rsync/tar/perl -i/-- terminator)", () => {
		const positive: Array<[string, string, string[]]> = [
			["install", "install a.txt b.txt", ["b.txt"]],
			["install -m", "install -m 755 a.txt b.txt", ["b.txt"]],
			["dd of=", "dd if=/dev/zero of=ddf.txt bs=1 count=1", ["ddf.txt"]],
			["ln", "ln a.txt b.txt", ["b.txt"]],
			["rsync", "rsync a.txt b.txt", ["b.txt"]],
			["rsync -e", "rsync -e ssh a.txt b.txt", ["b.txt"]],
			["tar -x -C", "tar -xzf x.tgz -C out", ["out"]],
			["tar -c", "tar -czf out.tgz dir", ["out.tgz"]],
			["perl -i", "perl -i -pe s/a/b/ p1.txt", ["p1.txt"]],
			["perl -i.bak", "perl -i.bak -pe s/a/b/ p.txt", ["p.txt", "p.txt.bak"]],
			["-- terminator", "rm -- -weird.txt", ["-weird.txt"]],
			["cp --", "cp -- a b", ["b"]],
		];
		for (const [label, command, expected] of positive) {
			expect(targetsOf(command), `${label} :: ${command}`).toEqual(expected);
		}
		const negative: Array<[string, string]> = [
			["install one arg", "install a.txt"],
			["dd null", "dd if=a.txt of=/dev/null"],
			["ln one arg", "ln a.txt"],
			["rsync read", "rsync -a a.txt"],
			["tar list", "tar -tzf x.tgz"],
			["perl no -i", "perl -pe s/a/b/ p1.txt"],
			["rm empty --", "rm --"],
		];
		for (const [label, command] of negative) {
			expect(targetsOf(command), `${label} :: ${command}`).toEqual([]);
		}
	});

	it("VC-007: D-group find (-exec recurses, -delete is a write)", () => {
		expect(targetsOf("find . -delete")).toEqual(["."]);
		expect(targetsOf("find . -name '*.tmp' -delete")).toEqual(["."]);
		expect(targetsOf("find . -exec rm {} \\;")).toEqual(["{}"]);
		expect(targetsOf("find . -exec grep -l foo {} \\;")).toEqual([]);
		expect(targetsOf("find . -name '*.md' -print")).toEqual([]);
	});

	it("VC-006/VC-007: E-group inline exec, truncate arity", () => {
		expect(targetsOf(`python3 -c "import os; os.system('cp a b')"`)).toEqual(["b"]);
		expect(targetsOf(`node -e "require('child_process').execSync('cp a b')"`)).toEqual(["b"]);
		expect(targetsOf("truncate -s 0 F")).toEqual(["F"]);
		expect(targetsOf(`python3 -c "import subprocess; subprocess.run(['ls','-la'])"`)).toEqual([]);
		expect(targetsOf(`node -e "console.log(1)"`)).toEqual([]);
	});

	it("VC-MWGF-007 / VC-007: the five completely-invisible classes produce a non-zero candidate", () => {
		const invisible = [
			`bash -c "echo x > o1.txt"`,
			`sh -c "echo x > o2.txt"`,
			`cmd /c "echo x > o6.txt"`,
			`powershell -Command "Set-Content -Path o7.txt -Value x"`,
			`pwsh -c "Set-Content -Path o8.txt -Value x"`,
			`perl -e "open(F,'>','o9.txt')"`,
			`ruby -e "File.write('o10.txt','x')"`,
			"echo x >| r3.txt",
		];
		for (const command of invisible) {
			expect(extractBashWriteCandidates(command).length, command).toBeGreaterThan(0);
		}
	});

	it("VC-MWGF-008 / VC-008: the historical false-positive forms are no longer judged as write targets", () => {
		const root = mkdtemp();
		const cfg = guardConfig(root);

		// truncate arity: the size argument is not a write target.
		expect(targetsOf("truncate -s 0 F")).toEqual(["F"]);
		// Bare write_text content capture removed; only Path("...") path remains.
		expect(targetsOf(`python3 -c "from pathlib import Path; Path('py2.txt').write_text('x')"`)).toEqual(["py2.txt"]);
		expect(targetsOf(`python3 -c "Path(F).write_text('x')"`)).toEqual([]);

		const unknownTier = [
			"echo x > $(date).txt",
			"echo x > `date`.txt",
			"echo x > $VAR",
			"echo x > *.txt",
			"rm *.txt",
			"echo x > ~/t1.txt",
			"echo x > {a,b}.txt",
		];
		for (const command of unknownTier) {
			const candidates = extractBashWriteCandidates(command);
			expect(candidates.length, command).toBeGreaterThan(0);
			for (const candidate of candidates) {
				expect(candidate.verbatim, `${command} :: ${candidate.target}`).toBe(false);
				const verdict = checkBashWriteScopeTarget(cfg, candidate.target, candidate.verbatim);
				expect(verdict.allowed, command).toBe(true);
				expect(verdict.rule, command).toBe("allow-unknown");
			}
		}

		// `$null` is a null-device target: no candidate, no audit noise.
		expect(targetsOf("echo x > $null")).toEqual([]);
	});

	it("VC-008 (handler): the historical false-positive commands pass the guard unblocked", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");
		const commands = [
			"truncate -s 0 .agenticdoc/mwds-t03/workers/t03-worker/report.md",
			"echo x > $(date).txt",
			"echo x > `date`.txt",
			"echo x > $VAR",
			"echo x > *.txt",
			"rm *.txt",
			"echo x > ~/t1.txt",
			"echo x > {a,b}.txt",
			"echo x > $null",
			`python3 -c "Path(F).write_text('x')"`,
		];
		for (const command of commands) {
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}
		settle(worker);
	});

	it("VC-010: the unwrap depth cap resolves three levels and stops without crashing", () => {
		function nest(levels: number): string {
			let command = "echo x > deep.txt";
			for (let i = 0; i < levels; i++) command = `bash -c ${JSON.stringify(command)}`;
			return command;
		}
		expect(targetsOf(nest(3))).toContain("deep.txt");
		const tooDeep = targetsOf(nest(5));
		expect(tooDeep).not.toContain("deep.txt");
	});

	it("VC-010: xargs -I placeholders and find -exec {} land in the allow-unknown tier", () => {
		const root = mkdtemp();
		const cfg = guardConfig(root);
		for (const command of [`xargs -I {} sh -c "echo x > {}"`, "find . -exec rm {} \\;"]) {
			const candidates = extractBashWriteCandidates(command);
			expect(candidates.length, command).toBeGreaterThan(0);
			for (const candidate of candidates) {
				expect(candidate.verbatim, `${command} :: ${candidate.target}`).toBe(false);
				expect(checkBashWriteScopeTarget(cfg, candidate.target, candidate.verbatim).allowed).toBe(true);
			}
		}
	});

	it("VC-004 guard: quoted and backslash-escaped `$` targets are still verbatim and still denied", () => {
		for (const command of ["printf x > '$T/x'", "printf x > \\$T/x"]) {
			const candidates = extractBashWriteCandidates(command);
			expect(candidates, command).toHaveLength(1);
			expect(candidates[0].target, command).toBe("$T/x");
			expect(candidates[0].verbatim, command).toBe(true);
		}
		const root = mkdtemp();
		const cfg = guardConfig(root, undefined);
		expect(checkBashWriteScopeTarget(cfg, "$T/x", false).rule).toBe("allow-unknown");
		expect(checkBashWriteScopeTarget(cfg, "$T/pm-state.md", false).risk).toBe("deny-basename");
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/mwds-t03/workers/t03-worker/report.md", true).allowed).toBe(
			true,
		);
	});
});

// ── AC-001 verbatim contract (T-02 / VC-001…VC-005) ──────────────────────────

const WORKER_MODE_SOURCE_PATH = fileURLToPath(
	new URL("../../src/extensions/agent-team-loop/worker/worker-mode.ts", import.meta.url),
);

interface CorpusCase {
	id: string;
	cls: "must-allow" | "must-block" | "contract-cost";
	expect: "allow" | "allow-unknown" | "deny";
	command: string;
}

/** RQ-2 §7 corpus (36 rows: 19 must-allow / 14 must-block / 3 contract-cost).
 * Commands are byte-identical to the evidence apart from keying the paths to
 * this suite's fixture (`mwds-t03` / `t03-worker` / `other-key`). */
const VERBATIM_CORPUS: CorpusCase[] = [
	{ id: "M1", cls: "must-allow", expect: "allow-unknown", command: "printf x > $T/report.md" },
	{ id: "M2", cls: "must-allow", expect: "allow-unknown", command: 'printf x > "$T/report.md"' },
	// biome-ignore lint/suspicious/noTemplateCurlyInString: shell parameter expansion inside the corpus literal, not a JS placeholder
	{ id: "M3", cls: "must-allow", expect: "allow-unknown", command: "printf x > ${T}/x.md" },
	{ id: "M4", cls: "must-allow", expect: "allow-unknown", command: "printf x > $UNSET/x.md" },
	{ id: "M5", cls: "must-allow", expect: "allow-unknown", command: "printf x > $(dirname $0)/x.md" },
	{ id: "M6", cls: "must-allow", expect: "allow-unknown", command: "printf x > `dirname $0`/x.md" },
	{ id: "M7", cls: "must-allow", expect: "allow-unknown", command: "printf x > $T/*.md" },
	{ id: "M8", cls: "must-allow", expect: "allow-unknown", command: "printf x > ~/x.md" },
	{ id: "M9", cls: "must-allow", expect: "allow-unknown", command: 'printf x > "$T/$FILE.md"' },
	{ id: "M10", cls: "must-allow", expect: "allow-unknown", command: "printf x > $T/report-$(date +%s).md" },
	{ id: "M11", cls: "must-allow", expect: "allow-unknown", command: "echo x | tee $T/report.md" },
	{ id: "M12", cls: "must-allow", expect: "allow-unknown", command: `printf x > $T/../${TASK}/report.md` },
	{
		id: "M13",
		cls: "must-allow",
		expect: "allow-unknown",
		command: `T=.agenticdoc/${KEY}/workers/${TASK}/report.md; echo x > $T`,
	},
	{ id: "M14", cls: "must-allow", expect: "allow-unknown", command: "Get-Content a.txt > $null" },
	{
		id: "M15",
		cls: "must-allow",
		expect: "allow",
		command: `printf x > .agenticdoc/${KEY}/workers/${TASK}/report.md`,
	},
	{
		id: "M16",
		cls: "must-allow",
		expect: "allow",
		command: `printf x > .agenticdoc/${KEY}/workers/${TASK}/../${TASK}/progress.md`,
	},
	{ id: "M17", cls: "must-allow", expect: "allow", command: `printf x > .agenticdoc/${KEY}/evidence/x.json` },
	{ id: "M18", cls: "must-allow", expect: "allow-unknown", command: "printf x > $T/pm-state.md" },
	{ id: "M19", cls: "must-allow", expect: "allow-unknown", command: "printf x > *.md" },
	{ id: "B1", cls: "must-block", expect: "deny", command: "printf x > .agenticdoc/other-key/pm-state.md" },
	{ id: "B2", cls: "must-block", expect: "deny", command: "printf x >> ../other-key/workers/x/report.md" },
	{ id: "B3", cls: "must-block", expect: "deny", command: "printf x > packages/coding-agent/src/a.ts" },
	{ id: "B4", cls: "must-block", expect: "deny", command: "printf x > .git/config" },
	{ id: "B5", cls: "must-block", expect: "deny", command: "printf x > report.md" },
	{
		id: "B6",
		cls: "must-block",
		expect: "deny",
		command: `printf x > .agenticdoc/${KEY}/workers/_workers.parallel`,
	},
	{ id: "B7", cls: "must-block", expect: "deny", command: "printf x > .agenticdoc/_index.parallel" },
	{
		id: "B8",
		cls: "must-block",
		expect: "deny",
		command: "printf x > .agenticdoc/other-key/workers/other/report.md",
	},
	{
		id: "B9",
		cls: "must-block",
		expect: "deny",
		command: `printf x > .agenticdoc/${KEY}/workers/${TASK}/../../../other-key/pm-state.md`,
	},
	{ id: "B10", cls: "must-block", expect: "deny", command: "printf x > /tmp/evil.md" },
	{ id: "B11", cls: "must-block", expect: "deny", command: "printf x > ../../foo.txt" },
	{ id: "B12", cls: "must-block", expect: "deny", command: "printf x > '$T/report.md'" },
	{ id: "B13", cls: "must-block", expect: "deny", command: "printf x > \\$T/report.md" },
	{
		id: "B14",
		cls: "must-block",
		expect: "deny",
		command: `printf x > .agenticdoc/${KEY}/workers/${TASK}/../../pm-state.md`,
	},
	{ id: "F1", cls: "contract-cost", expect: "allow-unknown", command: "printf x > $X/pm-state.md" },
	{
		id: "F2",
		cls: "contract-cost",
		expect: "allow-unknown",
		command: "printf x > .agenticdoc/other-key/$X/pm-state.md",
	},
	{
		id: "F3",
		cls: "contract-cost",
		expect: "allow-unknown",
		command: 'printf x > "$T/../../other-key/pm-state.md"',
	},
];

describe("AC-001 verbatim contract (VC-001…VC-005)", () => {
	function corpusConfig(fx: Fixture): BashWriteScopeConfig {
		return {
			projectRoot: fx.projectRoot,
			trueRoot: fx.trueRoot,
			keyDir: fx.keyDir,
			taskDir: fx.taskDir,
			writeScope: undefined,
		};
	}

	/** The production sequence: lexer → per-candidate `verbatim` → verdict. */
	function judge(cfg: BashWriteScopeConfig, command: string): BashWriteScopeVerdict[] {
		return extractBashWriteCandidates(command).map((candidate) =>
			checkBashWriteScopeTarget(cfg, candidate.target, candidate.verbatim),
		);
	}

	it("VC-MWGF-005 / VC-005: 36-case corpus — false_positives=0, must_block leaks=0, contract-cost=3", () => {
		const fx = makeFixture();
		const cfg = corpusConfig(fx);
		const counts = {
			falsePositives: 0,
			leaks: 0,
			contractCost: 0,
			allowDetermined: 0,
			allowUnknown: 0,
			noCandidate: 0,
		};
		const noCandidateIds: string[] = [];
		const failures: string[] = [];
		for (const row of VERBATIM_CORPUS) {
			const verdicts = judge(cfg, row.command);
			const blocked = verdicts.some((verdict) => !verdict.allowed);
			if (row.cls === "must-allow") {
				if (blocked) {
					counts.falsePositives++;
					failures.push(`${row.id} false-positive :: ${row.command}`);
				}
				if (row.expect === "allow") {
					if (verdicts.length > 0 && verdicts.every((v) => v.allowed && v.rule === undefined))
						counts.allowDetermined++;
					else failures.push(`${row.id} expected allow :: ${row.command}`);
				} else if (verdicts.length === 0) {
					counts.noCandidate++;
					noCandidateIds.push(row.id);
				} else if (verdicts.every((v) => v.allowed && v.rule === "allow-unknown")) {
					counts.allowUnknown++;
				} else {
					failures.push(`${row.id} expected allow-unknown :: ${row.command}`);
				}
			} else if (row.cls === "must-block") {
				if (!blocked) {
					counts.leaks++;
					failures.push(`${row.id} leaked :: ${row.command}`);
				}
			} else if (verdicts.length > 0 && verdicts.every((v) => v.allowed && v.rule === "allow-unknown")) {
				counts.contractCost++;
			} else {
				failures.push(`${row.id} expected contract-cost allow-unknown :: ${row.command}`);
			}
		}
		expect(failures).toEqual([]);
		expect(noCandidateIds).toEqual(["M14"]);
		expect(counts.falsePositives).toBe(0);
		expect(counts.leaks).toBe(0);
		expect(counts.contractCost).toBe(3);
		expect(counts.allowDetermined).toBe(3);
		// Must-allow rows in the allow-unknown tier: M1–M13 + M18 + M19 = 15.
		// M14 (`> $null`) is dropped by the extractor (NULL_WRITE_TARGETS) and
		// produces no candidate at all. The 3 contract-cost rows (F1–F3) also
		// land in the allow-unknown tier, counted separately: 15 + 3 = 18.
		expect(counts.allowUnknown).toBe(15);
		expect(counts.noCandidate).toBe(1);
		expect(VERBATIM_CORPUS).toHaveLength(36);
		expect(VERBATIM_CORPUS.filter((row) => row.cls === "must-allow")).toHaveLength(19);
		expect(VERBATIM_CORPUS.filter((row) => row.cls === "must-block")).toHaveLength(14);
	});

	it("VC-MWGF-004 / VC-004: single-quoted and backslash-escaped `$` stay verbatim and stay denied end to end", async () => {
		const fx = makeFixture();
		const cfg = corpusConfig(fx);
		for (const command of ["printf x > '$T/report.md'", "printf x > \\$T/report.md"]) {
			const candidates = extractBashWriteCandidates(command);
			expect(candidates, command).toHaveLength(1);
			expect(candidates[0].target, command).toBe("$T/report.md");
			expect(candidates[0].verbatim, command).toBe(true);
			const verdict = checkBashWriteScopeTarget(cfg, candidates[0].target, candidates[0].verbatim);
			expect(verdict.allowed, command).toBe(false);
			expect(verdict.rule, command).toBe("scope");
		}
		// Behavior level: the production guard blocks both forms.
		const worker = await startWorker(fx, "research");
		for (const command of ["printf x > '$T/report.md'", "printf x > \\$T/report.md"]) {
			expect(worker.toolCall("bash", { command })?.block, command).toBe(true);
		}
		settle(worker);
	});

	it("VC-004: double quotes do not deactivate `$`, single quotes do", () => {
		const fx = makeFixture();
		const cfg = corpusConfig(fx);
		const doubleQuoted = extractBashWriteCandidates('printf x > "$T/report.md"');
		expect(doubleQuoted).toHaveLength(1);
		expect(doubleQuoted[0].verbatim).toBe(false);
		expect(judge(cfg, 'printf x > "$T/report.md"')[0].rule).toBe("allow-unknown");
		const singleQuoted = extractBashWriteCandidates("printf x > '$T/report.md'");
		expect(singleQuoted[0].verbatim).toBe(true);
		expect(judge(cfg, "printf x > '$T/report.md'")[0].rule).toBe("scope");
	});

	it("VC-MWGF-001 / VC-001: production guard yields allow-unknown for live-expansion targets and never blocks them", async () => {
		const fx = makeFixture();
		const cfg = corpusConfig(fx);
		const worker = await startWorker(fx, "research");
		const liveExpansion = [
			"printf x > $T/report.md",
			'printf x > "$T/report.md"',
			"printf x > $T/*.md",
			"printf x > ~/x.md",
			"printf x > {a,b}.txt",
			"printf x > `date`.txt",
		];
		for (const command of liveExpansion) {
			const candidates = extractBashWriteCandidates(command);
			expect(candidates.length, command).toBeGreaterThan(0);
			for (const candidate of candidates) {
				expect(candidate.verbatim, `${command} :: ${candidate.target}`).toBe(false);
				const verdict = checkBashWriteScopeTarget(cfg, candidate.target, candidate.verbatim);
				expect(verdict.allowed, command).toBe(true);
				expect(verdict.rule, command).toBe("allow-unknown");
			}
			expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		}
		settle(worker);
	});

	it("VC-MWGF-002 / VC-002: the third `verbatim` argument is required and threaded on the production call site", () => {
		const source = fs.readFileSync(WORKER_MODE_SOURCE_PATH, "utf8");
		// No default: an omitted argument is a type error instead of a silent
		// `true` that would restore the old false-block direction.
		expect(source).not.toMatch(/verbatim\s*=\s*true/);
		expect(source).toMatch(/rawTarget: string,\s*verbatim: boolean,/);
		expect(source).toMatch(/checkBashWriteScopeTarget\(\s*config,\s*candidate\.target,\s*candidate\.verbatim,?\s*\)/);
	});
});

// ── AC-007 audit line + summary (T-03 / VC-029…VC-030) ───────────────────────

describe("AC-007 write-scope audit line + summary (VC-029/VC-030)", () => {
	function summaryLines(taskDir: string): string[] {
		return fs
			.readFileSync(path.join(taskDir, "trace.log"), "utf8")
			.split("\n")
			.filter((line) => line.startsWith("[WRITE_SCOPE_SUMMARY]"));
	}

	it("VC-MWGF-003 / VC-MWGF-030 / VC-030: the audit line carries blocked= and the optional risk=deny-basename in field order", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");

		// Contract-cost F1 (AC-001): a live-expansion target whose basename still
		// names a deny-list artifact. The guard lets it through by contract and
		// marks the residual risk; the target word is not statically determinable.
		expect(worker.toolCall("bash", { command: "printf x > $X/pm-state.md" })).toBeUndefined();
		// A hard block keeps `blocked=true` and omits `risk=` (only allow-unknown
		// can carry it).
		expect(worker.toolCall("bash", { command: "printf x > .agenticdoc/mwds-t03/pm-state.md" })?.block).toBe(true);
		// A determined-allowed target is silent (no audit noise, P1).
		expect(
			worker.toolCall("bash", { command: "printf x > .agenticdoc/mwds-t03/workers/t03-worker/a.md" }),
		).toBeUndefined();

		const lines = writeScopeTraceLines(fx.taskDir);
		expect(lines).toHaveLength(2);
		// Field order is contract (T-03 item 2): blocked=<bool> [risk=<token>]
		// rule= detail= pattern= target= cmd=.
		expect(lines[0]).toMatch(
			/^\[WRITE_SCOPE\] \S+ write-scope blocked=false risk=deny-basename rule=allow-unknown detail=target-not-statically-determinable pattern=\S+ target=\$X\/pm-state\.md cmd=\S.*$/,
		);
		expect(lines[1]).toContain("write-scope blocked=true rule=deny detail=denied:pm-state.md");
		expect(lines[1]).not.toContain("risk=");
		settle(worker);
	});

	it("VC-MWGF-029 / VC-029/VC-030: the three summary counts equal the actual verdicts, audited unknowns == summary unknown", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");

		const allowed = [
			"echo hi > .agenticdoc/mwds-t03/workers/t03-worker/a.md",
			"echo hi > .agenticdoc/mwds-t03/evidence/b.json",
		];
		for (const command of allowed) expect(worker.toolCall("bash", { command }), command).toBeUndefined();
		expect(worker.toolCall("bash", { command: "printf x > .agenticdoc/mwds-t03/pm-state.md" })?.block).toBe(true);
		const unknowns = ["printf x > $X/pm-state.md", "printf x > $T/report.md", "printf x > $X/_workers.parallel"];
		for (const command of unknowns) expect(worker.toolCall("bash", { command }), command).toBeUndefined();

		settle(worker);

		const trace = fs.readFileSync(path.join(fx.taskDir, "trace.log"), "utf8").split("\n");
		const audit = trace.filter((line) => line.startsWith("[WRITE_SCOPE] "));
		const summary = summaryLines(fx.taskDir);
		expect(summary).toHaveLength(1);
		expect(summary[0]).toBe("[WRITE_SCOPE_SUMMARY] allow=2 deny=1 allow-unknown=3");

		// One-to-one with the produced verdicts: 1 deny + 3 allow-unknown rows.
		expect(audit.filter((line) => line.includes("blocked=true"))).toHaveLength(1);
		expect(audit.filter((line) => line.includes("blocked=false"))).toHaveLength(3);
		expect(audit.filter((line) => line.includes("rule=allow-unknown"))).toHaveLength(3);
		expect(audit).toHaveLength(4);

		// VC-029 (equality, never `> 0`): the count derived from the audit rows is
		// the count in the summary line — two independent producers.
		const allowUnknownAudited = audit.filter(
			(line) => line.includes("blocked=false") && line.includes("rule=allow-unknown"),
		).length;
		const allowUnknownCount = Number(summary[0].match(/allow-unknown=(\d+)/)?.[1]);
		expect(allowUnknownAudited).toBe(allowUnknownCount);
		expect(allowUnknownAudited).toBe(3);
		expect(audit.filter((line) => line.includes("risk=deny-basename"))).toHaveLength(2);
	});

	it("the summary is written once at recordEnd for every guarded role (D-115 rule 7)", async () => {
		// Every role with `write`/`edit` or `bash` is guarded now, so every one of
		// them writes exactly one [WRITE_SCOPE_SUMMARY] line at settle.
		for (const type of ["research", "coding", "repair", "vision", "phase-writer", "roadmap-writer"]) {
			const fx = makeFixture();
			const worker = await startWorker(fx, type);
			expect(summaryLines(fx.taskDir), type).toHaveLength(0); // before settle
			settle(worker);
			expect(summaryLines(fx.taskDir), type).toHaveLength(1);
		}
		// An unguarded read-only role registers no guard and writes none.
		const review = makeFixture();
		const reviewer = await startWorker(review, "review");
		expect(reviewer.interceptorCount()).toBe(0);
		settle(reviewer);
		expect(summaryLines(review.taskDir)).toHaveLength(0);
	});
});

// ── AC-007 PM residual-risk alarm (T-03 / VC-031) ────────────────────────────

describe("AC-007 PM residual-risk alarm (VC-MWGF-031 / VC-031)", () => {
	function riskTrace(): string {
		return [
			"[WRITE_SCOPE] 2026-10-11T15:35:02.104Z write-scope blocked=false risk=deny-basename rule=allow-unknown detail=target-not-statically-determinable pattern=redirect target=$X/pm-state.md cmd=printf x > $X/pm-state.md",
			"[WRITE_SCOPE] 2026-10-11T15:35:03.104Z write-scope blocked=false risk=deny-basename rule=allow-unknown detail=target-not-statically-determinable pattern=redirect target=$Y/_workers.parallel cmd=printf x > $Y/_workers.parallel",
			// allow-unknown WITHOUT a deny-list basename is not residual risk.
			"[WRITE_SCOPE] 2026-10-11T15:35:04.104Z write-scope blocked=false rule=allow-unknown detail=target-not-statically-determinable pattern=redirect target=$T/report.md cmd=printf x > $T/report.md",
			// A hard block is not residual risk either.
			"[WRITE_SCOPE] 2026-10-11T15:35:05.104Z write-scope blocked=true rule=deny detail=denied:pm-state.md pattern=redirect target=.agenticdoc/k/pm-state.md cmd=echo x > .agenticdoc/k/pm-state.md",
			"",
		].join("\n");
	}

	it("VC-031: only blocked=false + risk=deny-basename rows raise one ledger alarm", () => {
		const root = mkdtemp();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const taskDir = path.join(agenticdocRoot, "mwds-t03", "workers", "t03-worker");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "trace.log"), riskTrace(), "utf8");

		expect(countWriteScopeResidualRisks(taskDir)).toBe(2);
		expect(recordWriteScopeResidualRisks(agenticdocRoot, "t03-worker", taskDir)).toBe(2);

		const ledger = path.join(agenticdocRoot, "_autopilot", "auto-decisions.jsonl");
		const rows = fs
			.readFileSync(ledger, "utf8")
			.split("\n")
			.filter((line) => line.trim() !== "")
			.map(
				(line) => JSON.parse(line) as { seq: number; phase: string; kind: string; count: number; detail: string },
			);
		// Reuses the single dispatch-alarm channel and its row shape.
		expect(rows).toEqual([
			{ seq: 1, phase: "dispatch-alarm", kind: "write-scope-risk", count: 2, detail: "t03-worker" },
		]);
		expect(describeDispatchAlarm({ kind: "write-scope-risk", count: 2, detail: "t03-worker" })).toContain("2");
	});

	it("VC-031: a trace without a residual-risk row writes no ledger row", () => {
		const root = mkdtemp();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const taskDir = path.join(agenticdocRoot, "mwds-t03", "workers", "t03-worker");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(
			path.join(taskDir, "trace.log"),
			"[WRITE_SCOPE] 2026-10-11T15:35:05.104Z write-scope blocked=true rule=deny detail=denied:pm-state.md pattern=redirect target=.agenticdoc/k/pm-state.md cmd=x\n",
			"utf8",
		);
		expect(countWriteScopeResidualRisks(taskDir)).toBe(0);
		expect(recordWriteScopeResidualRisks(agenticdocRoot, "t03-worker", taskDir)).toBe(0);
		expect(fs.existsSync(path.join(agenticdocRoot, "_autopilot", "auto-decisions.jsonl"))).toBe(false);
	});

	it("VC-031: a missing trace is not an error", () => {
		const root = mkdtemp();
		expect(countWriteScopeResidualRisks(path.join(root, "nope"))).toBe(0);
	});
});

// ── AC-008 branch coverage (T-10 / VC-032…VC-034) ───────────────────────────
// The 14 QG-B branches are re-anchored to the current tree. BR-01…BR-05 live in
// the S1 extractor/verdict, BR-06 in the task header parser; each case pairs one
// positive (must be classified or blocked) with one "must not misfire" negative.

describe("AC-008 S1 branch coverage (VC-MWGF-032 / BR-01…BR-06)", () => {
	function targetsOf(command: string): string[] {
		return extractBashWriteCandidates(command).map((candidate) => candidate.target);
	}

	it("BR-01 redirect operator variants (worker-mode.ts:820-826)", async () => {
		// Positive: >| (clobber), <> (read-write), &> and >& (combined), 2>
		// (fd-prefixed) each name a real write target.
		const writes: Array<[string, string, string[]]> = [
			[">|", "echo x >| r3.txt", ["r3.txt"]],
			["<>", "echo x <> r4.txt", ["r4.txt"]],
			["&>", "echo x &> r6.txt", ["r6.txt"]],
			[">&", "echo x >& r5.txt", ["r5.txt"]],
			["2>", "echo x 2> r7.txt", ["r7.txt"]],
		];
		for (const [label, command, expected] of writes) {
			expect(targetsOf(command), `${label} :: ${command}`).toEqual(expected);
		}
		// Negative: the fd-dup forms are descriptor plumbing, never write targets.
		for (const command of ["echo x 2>&1", "echo x >&2", "exec 3>&-"]) {
			expect(targetsOf(command), command).toEqual([]);
		}
		// Behavior: the production guard blocks a >| write off-surface and stays
		// silent for an fd-dup (no audit noise, P1).
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");
		const blocked = worker.toolCall("bash", { command: "echo x >| .agenticdoc/mwds-t03/pm-state.md" });
		expect(blocked?.block).toBe(true);
		expect(blocked?.reason).toContain("rule=deny");
		expect(worker.toolCall("bash", { command: "echo x >&2" })).toBeUndefined();
		expect(writeScopeTraceLines(fx.taskDir)).toHaveLength(1);
		console.log(`[VERIFY] AC-008/BR-01: redirect_variants=${writes.length} fd_dup_negative=3 blocked=true`);
		settle(worker);
	});

	it("BR-02 wrapper command position: the wrapped word is the command (worker-mode.ts:733,735-740)", () => {
		// Positive: the wrapper prefix is skipped and the inner command's operand
		// is the target (sudo rm / xargs rm / env VAR=x rm / sudo -n rm).
		const positives: Array<[string, string[]]> = [
			["sudo rm a.txt", ["a.txt"]],
			["xargs -n1 rm a.txt", ["a.txt"]],
			["env FOO=bar rm a.txt", ["a.txt"]],
			["sudo -n rm a.txt", ["a.txt"]],
		];
		for (const [command, expected] of positives) expect(targetsOf(command), command).toEqual(expected);
		// Negative: a read-only wrapped command extracts nothing.
		for (const command of ["sudo -u root ls", "xargs -n1 grep foo", "env FOO=bar ls"]) {
			expect(targetsOf(command), command).toEqual([]);
		}
		console.log(`[VERIFY] AC-008/BR-02: wrapper_command_position=${positives.length} read_only_negative=3`);
	});

	it("BR-03 cp -t / mv -t target-directory form (worker-mode.ts:872-873,946-967)", () => {
		// Positive: the directory operand is the target, not the last positional.
		const positives: Array<[string, string[]]> = [
			["cp -t out a.txt b.txt", ["out"]],
			["cp --target-directory=out a.txt", ["out"]],
			["mv -t out a.txt", ["out"]],
			["mv --target-directory out a.txt", ["out"]],
			["install -t out a.txt", ["out", "a.txt"]],
		];
		for (const [command, expected] of positives) expect(targetsOf(command), command).toEqual(expected);
		// Negative: `-T` (no-target-directory) is not the `-t` flag, so the
		// destination stays the last operand.
		expect(targetsOf("cp -T out a.txt")).toEqual(["a.txt"]);
		console.log(`[VERIFY] AC-008/BR-03: target_directory=${positives.length} dash_T_negative=1`);
	});

	it("BR-04 wrapper + operand form table (worker-mode.ts:786-905)", () => {
		const forms: Array<[string, string, string[]]> = [
			["bash -c", `bash -c "echo x > o1.txt"`, ["o1.txt"]],
			["sh -c", `sh -c "echo x > o2.txt"`, ["o2.txt"]],
			["powershell -Command", `powershell -Command "Set-Content -Path o7.txt -Value x"`, ["o7.txt"]],
			["pwsh -Command", `pwsh -Command "Add-Content -Path o8.txt -Value x"`, ["o8.txt"]],
			["cmd /c", `cmd /c "echo x > o6.txt"`, ["o6.txt"]],
			["perl -e", `perl -e "open(F,'>','o9.txt')"`, ["o9.txt"]],
			["ruby -e", `ruby -e "File.write('o10.txt','x')"`, ["o10.txt"]],
			["dd of=", "dd if=/dev/zero of=ddf.txt bs=1 count=1", ["ddf.txt"]],
			["install", "install a.txt b.txt", ["b.txt"]],
			["rsync", "rsync a.txt b.txt", ["b.txt"]],
		];
		for (const [label, command, expected] of forms) {
			expect(targetsOf(command), `${label} :: ${command}`).toEqual(expected);
		}
		// Negative: read-only twins of the same wrappers/commands.
		for (const command of [
			`powershell -Command "Get-Content a.txt"`,
			`pwsh -Command "Get-ChildItem"`,
			`perl -E "say 1"`,
			`ruby -E "puts 1"`,
			"dd if=a.txt of=/dev/null",
			"install a.txt",
			"rsync -a a.txt",
		]) {
			expect(targetsOf(command), command).toEqual([]);
		}
		// Documented boundary (design §3.9 optional, outside the 33-form table):
		// `awk '{print > "f"}'` and the cmd builtins `copy`/`del` were NOT
		// implemented by T-01. Pinning the current no-candidate result keeps the gap
		// visible: a later implementation flips this case instead of silently
		// adding coverage.
		for (const command of [`awk '{print > "o.txt"}' f`, `cmd /c "copy a b"`, `cmd /c "del a"`]) {
			expect(targetsOf(command), command).toEqual([]);
		}
		console.log(
			`[VERIFY] AC-008/BR-04: implemented_forms=${forms.length} read_only_negative=7 optional_unimplemented=3`,
		);
	});

	it("BR-05 non-verbatim target gate: $T, $(date), backtick and glob are allow-unknown, never denied (worker-mode.ts:1506-1521)", () => {
		const root = mkdtemp();
		const cfg: BashWriteScopeConfig = {
			projectRoot: root,
			trueRoot: path.join(root, ".agenticdoc"),
			keyDir: path.join(root, ".agenticdoc", KEY),
			taskDir: path.join(root, ".agenticdoc", KEY, "workers", TASK),
			writeScope: undefined,
		};
		const forms = ["printf x > $T/pm-state.md", "printf x > $(date).md", "printf x > `date`.md", "printf x > *.md"];
		const judged = forms.map((command) => {
			const candidates = extractBashWriteCandidates(command);
			expect(candidates, command).toHaveLength(1);
			const verdict = checkBashWriteScopeTarget(cfg, candidates[0].target, candidates[0].verbatim);
			return { command, allowed: verdict.allowed, rule: verdict.rule, risk: verdict.risk };
		});
		expect(judged).toEqual([
			{ command: "printf x > $T/pm-state.md", allowed: true, rule: "allow-unknown", risk: "deny-basename" },
			{ command: "printf x > $(date).md", allowed: true, rule: "allow-unknown", risk: undefined },
			{ command: "printf x > `date`.md", allowed: true, rule: "allow-unknown", risk: undefined },
			{ command: "printf x > *.md", allowed: true, rule: "allow-unknown", risk: undefined },
		]);
		console.log(`[VERIFY] AC-008/BR-05: non_verbatim_forms=${forms.length} denied=0 deny_basename_risk=1`);
	});

	it("BR-06 a body line cannot override the header role; the body write_scope: boundary is pinned (worker-mode.ts:331-335,384-402)", async () => {
		const root = mkdtemp();
		const taskDir = path.join(root, KEY, "workers", TASK);
		fs.mkdirSync(taskDir, { recursive: true });

		// `type:`: the header value wins over a later body line (the full AC-005
		// matrix is T-07's; this is the AC-008 branch pin).
		const typePath = path.join(taskDir, "type-body.md");
		fs.writeFileSync(typePath, "type: review\n\nwork\n\ntype: coding\n", "utf8");
		expect(parseTaskMd(typePath).type).toBe("review");

		// Documented boundary (design §8.1): only `type:` is header-scoped; a body
		// `write_scope:` with an empty value still narrows the surface to [] (the
		// DoS). The behavior is pinned here as the current truth, not fixed.
		const fx = makeFixture();
		fs.writeFileSync(
			path.join(fx.taskDir, "task.md"),
			"---\ntype: research\n---\n\nDo the research task.\n\nwrite_scope:\n",
			"utf8",
		);
		expect(parseTaskMd(path.join(fx.taskDir, "task.md")).writeScope).toEqual([]);
		process.env.PI_WORKER_TASK = path.join(fx.taskDir, "task.md");
		process.chdir(fx.projectRoot);
		const worker = fakeWorkerPi();
		await workerModeActivate(worker.pi);
		const blocked = worker.toolCall("bash", {
			command: "echo x > .agenticdoc/mwds-t03/workers/t03-worker/report.md",
		});
		expect(blocked?.block).toBe(true);
		expect(blocked?.reason).toContain("rule=write-scope");

		// Control: without the body line the same write is allowed (default surface).
		const clean = makeFixture();
		const cleanWorker = await startWorker(clean, "research");
		expect(
			cleanWorker.toolCall("bash", {
				command: "echo x > .agenticdoc/mwds-t03/workers/t03-worker/report.md",
			}),
		).toBeUndefined();
		console.log("[VERIFY] AC-008/BR-06: header_type_wins=1 body_write_scope_dos_pinned=1 control_allowed=1");
		settle(worker);
		settle(cleanWorker);
	});
});

// ── T-17/B-6 forms coverage metric (AC-002) ────────────────────────────────
// Machine-readable replay of the RQ-1 79-form inventory
// (`evidence/research/spec-form-inventory-20261011.md` §2, R01–R79) against the
// extractor as it stands now. Covered = the candidate set satisfies the row's
// AC-002 expectation (correct target(s) / correct unknown tier / correctly no
// target). The `[FORMS]` line is the machine-readable value; the raw run is
// landed in `evidence/runs/t17-forms-baseline-20261012.md`. No assertion
// depends on the growing task.md corpus.

interface FormsMetricRow {
	id: string;
	command: string;
	expect: { targets: string[]; forbid?: string[] } | { unknown: true } | { none: true } | { any: true };
}

const FORMS_METRIC_CORPUS: FormsMetricRow[] = [
	{ id: "R01", command: `bash -c "echo x > o1.txt"`, expect: { targets: ["o1.txt"] } },
	{ id: "R02", command: `sh -c "echo x > o2.txt"`, expect: { targets: ["o2.txt"] } },
	{ id: "R03", command: `zsh -c "echo x > o3.txt"`, expect: { targets: ["o3.txt"] } },
	{ id: "R04", command: `dash -c "echo x > o4.txt"`, expect: { targets: ["o4.txt"] } },
	{ id: "R05", command: `ksh -c "echo x > o5.txt"`, expect: { targets: ["o5.txt"] } },
	{ id: "R06", command: `cmd /c "echo x > o6.txt"`, expect: { targets: ["o6.txt"] } },
	{ id: "R07", command: `powershell -Command "Set-Content -Path o7.txt -Value x"`, expect: { targets: ["o7.txt"] } },
	{ id: "R08", command: `pwsh -c "Set-Content -Path o8.txt -Value x"`, expect: { targets: ["o8.txt"] } },
	{ id: "R09", command: `perl -e "open(F,'>','o9.txt')"`, expect: { targets: ["o9.txt"] } },
	{ id: "R10", command: `ruby -e "File.write('o10.txt','x')"`, expect: { targets: ["o10.txt"] } },
	{ id: "R11", command: "env FOO=bar cp a b", expect: { targets: ["b"] } },
	{ id: "R12", command: "env cp a b", expect: { targets: ["b"] } },
	{ id: "R13", command: "sudo cp a b", expect: { targets: ["b"] } },
	{ id: "R14", command: "sudo -u root cp a b", expect: { targets: ["b"] } },
	{ id: "R15", command: "doas cp a b", expect: { targets: ["b"] } },
	{ id: "R16", command: `xargs -n1 sh -c "echo x > o11.txt"`, expect: { targets: ["o11.txt"] } },
	{ id: "R17", command: "xargs rm a", expect: { targets: ["a"] } },
	{ id: "R18", command: "timeout 5 cp a b", expect: { targets: ["b"] } },
	{ id: "R19", command: "setsid cp a b", expect: { targets: ["b"] } },
	{ id: "R20", command: "stdbuf -o0 cp a b", expect: { targets: ["b"] } },
	{ id: "R21", command: "stdbuf cp a b", expect: { targets: ["b"] } },
	{ id: "R22", command: "nice cp a b", expect: { targets: ["b"] } },
	{ id: "R23", command: "nice -n 5 cp a b", expect: { targets: ["b"] } },
	{ id: "R24", command: "time cp a b", expect: { targets: ["b"] } },
	{ id: "R25", command: "time -p cp a b", expect: { targets: ["b"] } },
	{ id: "R26", command: "command cp a b", expect: { targets: ["b"] } },
	{ id: "R27", command: "nohup cp a b", expect: { targets: ["b"] } },
	{ id: "R28", command: "echo x > r1.txt", expect: { targets: ["r1.txt"] } },
	{ id: "R29", command: "echo x >> r2.txt", expect: { targets: ["r2.txt"] } },
	{ id: "R30", command: "echo x >| r3.txt", expect: { targets: ["r3.txt"] } },
	{ id: "R31", command: "echo x <> r4.txt", expect: { targets: ["r4.txt"] } },
	{ id: "R32", command: "echo x >& r5.txt", expect: { targets: ["r5.txt"] } },
	{ id: "R33", command: "echo x &> r6.txt", expect: { targets: ["r6.txt"] } },
	{ id: "R34", command: "echo x 2> r7.txt", expect: { targets: ["r7.txt"] } },
	{ id: "R35", command: "echo x 2>> r8.txt", expect: { targets: ["r8.txt"] } },
	{ id: "R36", command: "echo x 1> r9.txt", expect: { targets: ["r9.txt"] } },
	{ id: "R37", command: "echo x 2>&1", expect: { none: true } },
	{ id: "R38", command: "echo x > r10.txt 2>&1", expect: { targets: ["r10.txt"] } },
	{ id: "R39", command: "exec 3> r11.txt", expect: { targets: ["r11.txt"] } },
	{ id: "R40", command: "cp a.txt b.txt", expect: { targets: ["b.txt"] } },
	{ id: "R41", command: "cp -- a.txt b.txt", expect: { targets: ["b.txt"] } },
	{ id: "R42", command: "mv a.txt b.txt", expect: { targets: ["b.txt"] } },
	{ id: "R43", command: "install a.txt b.txt", expect: { targets: ["b.txt"] } },
	{ id: "R44", command: "tee t.txt", expect: { targets: ["t.txt"] } },
	{ id: "R45", command: "tee -a t.txt", expect: { targets: ["t.txt"] } },
	{ id: "R46", command: "dd if=/dev/zero of=ddf.txt bs=1 count=1", expect: { targets: ["ddf.txt"] } },
	{ id: "R47", command: "truncate -s 0 tr1.txt", expect: { targets: ["tr1.txt"], forbid: ["0"] } },
	{ id: "R48", command: "ln a.txt b.txt", expect: { targets: ["b.txt"] } },
	{ id: "R49", command: "rsync a.txt b.txt", expect: { targets: ["b.txt"] } },
	{ id: "R50", command: "tar -xf x.tar", expect: { any: true } },
	{ id: "R51", command: "tar -xzf x.tgz", expect: { any: true } },
	{ id: "R52", command: "sed -i s/a/b/ s1.txt", expect: { targets: ["s1.txt"] } },
	{ id: "R53", command: "sed -i.bak s/a/b/ s2.txt", expect: { targets: ["s2.txt", "s2.txt.bak"] } },
	{ id: "R54", command: "sed --in-place s/a/b/ s3.txt", expect: { targets: ["s3.txt"] } },
	{ id: "R55", command: "perl -i -pe s/a/b/ p1.txt", expect: { targets: ["p1.txt"] } },
	{ id: "R56", command: "find . -exec rm {} \\;", expect: { any: true } },
	{ id: "R57", command: "find . -delete", expect: { any: true } },
	{ id: "R58", command: "cat <<< x", expect: { none: true } },
	{ id: "R59", command: "cat <<< x > h1.txt", expect: { targets: ["h1.txt"] } },
	{ id: "R60", command: "rm -- -weird.txt", expect: { targets: ["-weird.txt"] } },
	{ id: "R61", command: 'echo x > "a b.txt"', expect: { targets: ["a b.txt"] } },
	{ id: "R62", command: "echo x > a\\ b.txt", expect: { targets: ["a b.txt"] } },
	{ id: "R63", command: "echo x > $(date).txt", expect: { unknown: true } },
	{ id: "R64", command: "$(rm cst.txt)", expect: { targets: ["cst.txt"] } },
	{ id: "R65", command: "echo x > `date`.txt", expect: { unknown: true } },
	{ id: "R66", command: "echo x > *.txt", expect: { unknown: true } },
	{ id: "R67", command: "rm *.txt", expect: { unknown: true } },
	{ id: "R68", command: "echo x > ~/t1.txt", expect: { unknown: true } },
	{ id: "R69", command: "cd /tmp && echo x > cd1.txt", expect: { any: true } },
	{ id: "R70", command: "cd /tmp && > cd2.txt", expect: { any: true } },
	{ id: "R71", command: "echo x > {a,b}.txt", expect: { unknown: true } },
	{ id: "R72", command: `python3 -c "open('py1.txt','w')"`, expect: { targets: ["py1.txt"] } },
	{
		id: "R73",
		command: `python3 -c "from pathlib import Path; Path('py2.txt').write_text('x')"`,
		expect: { targets: ["py2.txt"], forbid: ["x"] },
	},
	{ id: "R74", command: `python3 -c "import os; os.system('cp a b')"`, expect: { targets: ["b"] } },
	{ id: "R75", command: `node -e "require('fs').writeFileSync('n1.txt','x')"`, expect: { targets: ["n1.txt"] } },
	{ id: "R76", command: `node -e "require('child_process').execSync('cp a b')"`, expect: { targets: ["b"] } },
	{ id: "R77", command: `node -e "console.log(1)"`, expect: { none: true } },
	{ id: "R78", command: "rg foo", expect: { none: true } },
	{ id: "R79", command: 'echo "a > b"', expect: { none: true } },
];

describe("T-17/B-6 forms coverage metric (AC-002)", () => {
	function satisfied(rows: BashWriteCandidate[], expect_: FormsMetricRow["expect"]): boolean {
		const targets = rows.map((row) => row.target);
		if ("none" in expect_) return rows.length === 0;
		if ("any" in expect_) return rows.length > 0;
		if ("unknown" in expect_) return rows.length === 0 || rows.every((row) => !row.verbatim);
		if (expect_.targets.some((target) => !targets.includes(target))) return false;
		return (expect_.forbid ?? []).every((target) => !targets.includes(target));
	}

	it("replays the RQ-1 79-form inventory and reports [FORMS] total/covered/missing", () => {
		const missing: string[] = [];
		for (const row of FORMS_METRIC_CORPUS) {
			const rows = extractBashWriteCandidates(row.command);
			if (!satisfied(rows, row.expect)) missing.push(`${row.id}: ${row.command} => ${JSON.stringify(rows)}`);
		}
		const total = FORMS_METRIC_CORPUS.length;
		const covered = total - missing.length;
		process.stdout.write(`[FORMS] total=${total} covered=${covered} missing=${missing.length}\n`);
		for (const line of missing) process.stdout.write(`[FORMS] missing ${line}\n`);
		expect(total).toBe(79);
		expect(covered + missing.length).toBe(total);
		expect(missing).toEqual([]);
	});
});
// QG-A (static only) alleged three false blocks and one missing consumer test.
// These cases are the measured verdicts: F-2 (`[[`/`((` comparisons) and F-1
// (tar / `-i$SUFFIX` verbatim loss) were reproduced against the real extractor
// and repaired; the marker pair audit (C-13) gains its 1 positive + 1 negative.

describe("T-17 F-2 comparison contexts (AC-001 direction)", () => {
	function cfgOf(fx: Fixture): BashWriteScopeConfig {
		return {
			projectRoot: fx.projectRoot,
			trueRoot: fx.trueRoot,
			keyDir: fx.keyDir,
			taskDir: fx.taskDir,
			writeScope: undefined,
		};
	}

	it("comparisons in [[ ]] / (( )) / $(( )) produce no write candidate", () => {
		const commands = [
			'if [[ "$ts" > "2026-01-01" ]]; then echo new; fi',
			"if (( x > 5 )); then echo big; fi",
			"echo $(( a > b ))",
			'[[ "$a" < "b" ]]',
		];
		for (const command of commands) {
			expect(extractBashWriteCandidates(command), command).toEqual([]);
		}
		console.log(`[VERIFY] T-17/F-2: comparison_forms=${commands.length} candidates=0`);
	});

	it("a real redirect after a comparison context is still blocked", async () => {
		const fx = makeFixture();
		const cfg = cfgOf(fx);
		const commands = [
			"printf x > f.txt",
			"(( x > 5 )) && printf y > f.txt",
			'[[ "$a" == "$b" ]] && printf y > f.txt',
		];
		for (const command of commands) {
			const verdicts = extractBashWriteCandidates(command).map((candidate) =>
				checkBashWriteScopeTarget(cfg, candidate.target, candidate.verbatim),
			);
			expect(
				verdicts.some((verdict) => !verdict.allowed),
				command,
			).toBe(true);
		}
		const worker = await startWorker(fx, "research");
		for (const command of commands) expect(worker.toolCall("bash", { command })?.block, command).toBe(true);
		console.log(`[VERIFY] T-17/F-2: post_comparison_redirects_blocked=${commands.length}`);
		settle(worker);
	});
});

describe("T-17 F-1 tar / -i suffix verbatim passthrough (AC-001 tier 3)", () => {
	function cfgOf(fx: Fixture): BashWriteScopeConfig {
		return {
			projectRoot: fx.projectRoot,
			trueRoot: fx.trueRoot,
			keyDir: fx.keyDir,
			taskDir: fx.taskDir,
			writeScope: undefined,
		};
	}

	it("a tar target with live expansion is allow-unknown, never a literal deny", () => {
		const fx = makeFixture();
		const cfg = cfgOf(fx);
		const commands = ["tar -czf $OUT.tar dir", "tar -xzf a.tgz -C $X", "tar --file=$OUT.tar -c dir"];
		for (const command of commands) {
			const candidates = extractBashWriteCandidates(command);
			expect(candidates, command).toHaveLength(1);
			expect(candidates[0].verbatim, command).toBe(false);
			const verdict = checkBashWriteScopeTarget(cfg, candidates[0].target, candidates[0].verbatim);
			expect(verdict.allowed, command).toBe(true);
			expect(verdict.rule, command).toBe("allow-unknown");
			expect(verdict.detail, command).toBe("target-not-statically-determinable");
		}
		console.log(`[VERIFY] T-17/F-1: tar_live_expansion=${commands.length} allow_unknown=${commands.length}`);
	});

	it("literal tar targets keep the verbatim path (in-surface allowed, off-surface denied)", () => {
		const fx = makeFixture();
		const cfg = cfgOf(fx);
		const inSurface = `tar -czf .agenticdoc/${KEY}/workers/${TASK}/out.tar dir`;
		const inside = extractBashWriteCandidates(inSurface);
		expect(inside).toHaveLength(1);
		expect(inside[0].verbatim).toBe(true);
		expect(checkBashWriteScopeTarget(cfg, inside[0].target, inside[0].verbatim).allowed).toBe(true);
		const outside = extractBashWriteCandidates("tar -czf out.tar dir");
		expect(outside).toHaveLength(1);
		expect(outside[0].verbatim).toBe(true);
		expect(checkBashWriteScopeTarget(cfg, outside[0].target, outside[0].verbatim).rule).toBe("scope");
		console.log("[VERIFY] T-17/F-1: literal_tar_in_surface=1 off_surface_scope=1");
	});

	it("sed/perl -i$SUFFIX keeps the expansion, -i.bak stays literal", () => {
		expect(extractBashWriteCandidates("sed -i$S s/a/b/ a.txt")).toEqual([
			{ target: "a.txt", pattern: "sed -i", verbatim: true },
			{ target: "a.txt$S", pattern: "sed -i", verbatim: false },
		]);
		expect(extractBashWriteCandidates("perl -i$S -pe s/a/b/ p.txt")).toEqual([
			{ target: "p.txt", pattern: "perl -i", verbatim: true },
			{ target: "p.txt$S", pattern: "perl -i", verbatim: false },
		]);
		expect(extractBashWriteCandidates("sed -i.bak s/a/b/ a.txt")).toEqual([
			{ target: "a.txt", pattern: "sed -i", verbatim: true },
			{ target: "a.txt.bak", pattern: "sed -i", verbatim: true },
		]);
		console.log("[VERIFY] T-17/F-1: suffix_var_non_verbatim=2 suffix_literal_verbatim=2");
	});

	it("VC-MWGF-045 / C-2 residual: `cd <taskDir> && > report.md` is still denied (known deny, pinned)", async () => {
		const fx = makeFixture();
		const worker = await startWorker(fx, "research");
		const blocked = worker.toolCall("bash", {
			command: `cd .agenticdoc/${KEY}/workers/${TASK} && > report.md`,
		});
		expect(blocked?.block).toBe(true);
		expect(blocked?.reason).toContain("rule=scope");
		console.log("[VERIFY] T-17/C-2: cd_relative_redirect_deny=1 rule=scope");
		settle(worker);
	});
});

describe("T-17 C-13 write-surface marker audit (VC-MWGF-036 / AC-010)", () => {
	function writeSurfaceLines(taskDir: string): string[] {
		return fs
			.readFileSync(path.join(taskDir, "trace.log"), "utf8")
			.split("\n")
			.filter((line) => line.includes("[WRITE_SURFACE] "));
	}

	it("a legal ordered marker pair emits no [WRITE_SURFACE] audit line", async () => {
		const fx = makeFixture();
		await startWorker(fx, "research", [WRITE_SURFACE_MARKER, "write contract", WRITE_SURFACE_MARKER_END]);
		expect(writeSurfaceLines(fx.taskDir)).toEqual([]);
		console.log("[VERIFY] T-17/C-13: legal_marker_pair_audit_lines=0");
	});

	it("dangling / duplicate / reversed marker pairs each emit exactly one audit line", async () => {
		const cases: Array<[string, string[]]> = [
			["dangling", [WRITE_SURFACE_MARKER]],
			["duplicate", [WRITE_SURFACE_MARKER, WRITE_SURFACE_MARKER_END, WRITE_SURFACE_MARKER]],
			["reversed", [WRITE_SURFACE_MARKER_END, WRITE_SURFACE_MARKER]],
		];
		for (const [label, frontmatter] of cases) {
			const fx = makeFixture();
			await startWorker(fx, "research", frontmatter);
			const lines = writeSurfaceLines(fx.taskDir);
			expect(lines, label).toHaveLength(1);
			expect(lines[0], label).toMatch(
				/^\[FLOW\] \S+ \[WRITE_SURFACE\] contract-section markers malformed \(expected exactly one ordered marker pair\)$/,
			);
		}
		console.log(`[VERIFY] T-17/C-13: malformed_marker_pairs=${cases.length} audit_lines_each=1`);
	});
});

// ── T-19/C-17 heredoc bodies (AC-001 direction) ─────────────────────────────
// A heredoc body is DATA: `cat <<EOF > out.md` writes only out.md, and a body
// line `x > y` writes nothing. The tokenizer cannot drop the body (it has no
// line state), so the body ranges are removed before the redirect scan.
describe("T-19/C-17 heredoc bodies are not redirect sources (AC-001 direction)", () => {
	it("keeps the header redirect and drops a body `>` (negative)", () => {
		expect(extractBashWriteCandidates("cat <<EOF > out.md\nbody > notafile\nEOF\n")).toEqual([
			{ target: "out.md", pattern: "redirect", verbatim: true },
		]);
		// A `<<` arithmetic shift is not a heredoc: the redirect after the `(( ))`
		// must survive the body pass.
		expect(extractBashWriteCandidates("echo $(( 1 << 2 )) > shift.txt")).toEqual([
			{ target: "shift.txt", pattern: "redirect", verbatim: true },
		]);
	});

	it("quote-agnostic delimiters (quoted / dashed) and here-strings", () => {
		expect(extractBashWriteCandidates("cat <<'EOF' > out.md\nbody > notafile\nEOF\n")).toEqual([
			{ target: "out.md", pattern: "redirect", verbatim: true },
		]);
		expect(extractBashWriteCandidates("cat <<-EOF > out.md\n\tbody > notafile\n\tEOF\n")).toEqual([
			{ target: "out.md", pattern: "redirect", verbatim: true },
		]);
		expect(extractBashWriteCandidates('cat <<< "x > f" > out.md\n')).toEqual([
			{ target: "out.md", pattern: "redirect", verbatim: true },
		]);
	});

	it("a real redirect outside the heredoc is still extracted (positive)", () => {
		expect(extractBashWriteCandidates("cat <<EOF > out.md\nbody > notafile\nEOF\nprintf y > tail.md\n")).toEqual([
			{ target: "out.md", pattern: "redirect", verbatim: true },
			{ target: "tail.md", pattern: "redirect", verbatim: true },
		]);
	});

	function cfgOf(fx: Fixture): BashWriteScopeConfig {
		return {
			projectRoot: fx.projectRoot,
			trueRoot: fx.trueRoot,
			keyDir: fx.keyDir,
			taskDir: fx.taskDir,
			writeScope: undefined,
		};
	}

	it("T-20/H-3: a mixed-EOL heredoc (CRLF opener / LF closer) still extracts the real redirect and blocks it cross-key (positive)", () => {
		// QG-A3 H-3: a `<<EOF\r` opener left the delimiter as `EOF\r`, so the
		// LF-closed `EOF` never matched and the search swallowed every later line.
		expect(extractBashWriteCandidates("cat <<EOF\r\nbody\r\nEOF\nprintf y > real4.md\n")).toEqual([
			{ target: "real4.md", pattern: "redirect", verbatim: true },
		]);
		const fx = makeFixture();
		const cfg = cfgOf(fx);
		const crossKey = extractBashWriteCandidates("cat <<EOF\r\nbody\r\nEOF\nprintf y > ../other-key/x.md\n");
		expect(crossKey).toEqual([{ target: "../other-key/x.md", pattern: "redirect", verbatim: true }]);
		const verdict = checkBashWriteScopeTarget(cfg, crossKey[0].target, crossKey[0].verbatim);
		expect(verdict.allowed).toBe(false);
		expect(verdict.rule).toBe("scope");
	});

	it("T-20/H-3: a `>` inside a mixed-EOL heredoc body is still data, not a write (negative)", () => {
		expect(extractBashWriteCandidates("cat <<EOF\r\nbody > phantom\r\nEOF\n")).toEqual([]);
	});

	it("T-20/H-4: a same-line `;` after `<<EOF` keeps the real redirect and blocks it cross-key (positive)", () => {
		// QG-A3 H-4: the heredoc body starts at the next physical newline, so
		// `printf y > real.md` on the opener line executes and must be extracted.
		expect(extractBashWriteCandidates("cat <<EOF; printf y > real.md\nbody\nEOF\n")).toEqual([
			{ target: "real.md", pattern: "redirect", verbatim: true },
		]);
		const fx = makeFixture();
		const cfg = cfgOf(fx);
		const crossKey = extractBashWriteCandidates("cat <<EOF; printf y > ../other-key/x.md\nbody\nEOF\n");
		expect(crossKey).toEqual([{ target: "../other-key/x.md", pattern: "redirect", verbatim: true }]);
		const verdict = checkBashWriteScopeTarget(cfg, crossKey[0].target, crossKey[0].verbatim);
		expect(verdict.allowed).toBe(false);
		expect(verdict.rule).toBe("scope");
	});

	it("T-20/H-4: a body `>` after a same-line `;` opener is still not a write (negative)", () => {
		expect(extractBashWriteCandidates("cat <<EOF; true\nbody > phantom\nEOF\n")).toEqual([]);
	});
});

// ── T-19/C-18 tar `-C` chdir vs `-f` archive (AC-001 direction) ─────────────
// `-C <dir>` is a chdir, never a write target of a CREATE; the archive named
// by `-f` is. Extraction (`-x`) keeps `-C`: there it IS the unpack destination.
describe("T-19/C-18 tar -C is chdir, -f is the write target (AC-001 direction)", () => {
	function cfgOf(fx: Fixture): BashWriteScopeConfig {
		return {
			projectRoot: fx.projectRoot,
			trueRoot: fx.trueRoot,
			keyDir: fx.keyDir,
			taskDir: fx.taskDir,
			writeScope: undefined,
		};
	}

	it("create: the chdir dir is not a candidate and the archive is (positive)", () => {
		expect(extractBashWriteCandidates("tar -czf $OUT.tar -C $D src")).toEqual([
			{ target: "$OUT.tar", pattern: "tar -c", verbatim: false },
		]);
		expect(extractBashWriteCandidates("tar -czf out.tar -C srcDir src")).toEqual([
			{ target: "out.tar", pattern: "tar -c", verbatim: true },
		]);
		expect(extractBashWriteCandidates("tar -xzf x.tgz -C out")).toEqual([
			{ target: "out", pattern: "tar -C", verbatim: true },
		]);
	});

	it("an in-surface archive with an off-surface -C source is allowed (positive)", () => {
		const fx = makeFixture();
		const cfg = cfgOf(fx);
		const archive = `.agenticdoc/${KEY}/workers/${TASK}/out.tar`;
		const candidates = extractBashWriteCandidates(`tar -czf ${archive} -C C:/Windows/Temp a`);
		expect(candidates).toEqual([{ target: archive, pattern: "tar -c", verbatim: true }]);
		expect(checkBashWriteScopeTarget(cfg, candidates[0].target, candidates[0].verbatim).allowed).toBe(true);
		console.log("[VERIFY] T-19/C-18: tar_create_C_not_candidate=1 archive_judged=1");
	});

	it("a literal off-surface archive is still denied (negative)", () => {
		const fx = makeFixture();
		const cfg = cfgOf(fx);
		const candidates = extractBashWriteCandidates(`tar -czf /etc/x.tar -C .agenticdoc/${KEY}/workers/${TASK} a`);
		expect(candidates).toEqual([{ target: "/etc/x.tar", pattern: "tar -c", verbatim: true }]);
		const verdict = checkBashWriteScopeTarget(cfg, candidates[0].target, candidates[0].verbatim);
		expect(verdict.allowed).toBe(false);
		expect(verdict.rule).toBe("scope");
	});
});
