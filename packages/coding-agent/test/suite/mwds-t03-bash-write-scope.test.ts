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
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { writeDispatchTaskMd } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	type BashWriteScopeConfig,
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

// ── VC-024: coding-like roles unaffected ─────────────────────────────────────

describe("AC-005b zero impact on write roles (VC-024)", () => {
	for (const type of ["coding", "repair", "vision"]) {
		it(`VC-024: ${type} registers no write-scope guard and its bash commands pass`, async () => {
			const fx = makeFixture();
			const worker = await startWorker(fx, type);
			expect(worker.interceptorCount()).toBe(0);
			expect(worker.toolCall("bash", { command: "echo x > .agenticdoc/mwds-t03/pm-state.md" })).toBeUndefined();
			expect(worker.toolCall("bash", { command: "mkdir -p packages/coding-agent/foo" })).toBeUndefined();
			expect(writeScopeTraceLines(fx.taskDir)).toHaveLength(0);
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

	it("extractBashWriteCandidates covers the required write patterns", () => {
		const patterns = new Map<string, string[]>();
		const commands = [
			"echo x > a.txt",
			"echo x >> a.txt",
			"echo x | tee a.txt",
			"cp a.txt b.txt",
			"mv a.txt b.txt",
			"rm a.txt",
			"mkdir -p a",
			"touch a.txt",
			"truncate -s 0 a.txt",
			"sed -i s/a/b/ a.txt",
			"git checkout -- a.txt",
			"git clean -fd",
			"git apply patch.diff",
			"curl -o a.txt https://example.invalid",
			"wget -O a.txt https://example.invalid",
			"Set-Content -Path a.txt -Value x",
			"Out-File -FilePath a.txt",
			"New-Item -ItemType Directory -Path a",
			"Remove-Item a.txt",
		];
		for (const command of commands) {
			const targets = extractBashWriteCandidates(command).map((c) => c.target);
			patterns.set(command, targets);
			expect(targets.length, command).toBeGreaterThan(0);
		}
		expect(patterns.get("cp a.txt b.txt")).toEqual(["b.txt"]);
		expect(patterns.get("mv a.txt b.txt")).toEqual(["b.txt"]);
		expect(patterns.get("Set-Content -Path a.txt -Value x")).toEqual(["a.txt"]);
		expect(patterns.get("git clean -fd")).toEqual(["."]);
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
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/mwds-t03/pm-state.md").rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, "packages/x.md").rule).toBe("deny");
		expect(checkBashWriteScopeTarget(cfg, "README.md").rule).toBe("scope");
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/mwds-t03/workers/t03-worker/report.md").allowed).toBe(true);
		expect(checkBashWriteScopeTarget(cfg, ".agenticdoc/mwds-t03/evidence/e.md").allowed).toBe(true);
		const narrowed = config(root, [".agenticdoc/mwds-t03/evidence"]);
		expect(checkBashWriteScopeTarget(narrowed, ".agenticdoc/mwds-t03/workers/t03-worker/report.md").rule).toBe(
			"write-scope",
		);
	});
});
