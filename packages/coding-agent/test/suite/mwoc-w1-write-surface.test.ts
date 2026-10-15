/**
 * mw-worker-output-contract W1 · T-01 write-surface single source
 * (AC-006 / AC-007(a) / AC-016).
 *
 * Locks the one predicate (`shared/write-surface.ts::judgeWriteTarget`) and the
 * dispatch/runtime parity it buys:
 *   - `evidence/**` is accepted on BOTH bases (project-root relative and
 *     keyDir relative), at the dispatch judge and at the runtime
 *     `worker_file` channel;
 *   - the 3/3 overflow family (`../..`, another key, repo source) stays
 *     fail-closed at both surfaces;
 *   - a research card and a review card that declare `evidence/**` are
 *     dispatch-satisfiable (the review shape is the red case this card fixes;
 *     research already passed because it is a shell role early-return);
 *   - the PM judge and the runtime channel import the SAME predicate (source
 *     assertion + behaviour parity matrix);
 *   - the task-dir basename whitelist still passes 3/3, and the default
 *     `write_scope:` face equals `renderDefaultWriteScope` (zero behaviour
 *     change).
 *
 * Runtime note (AC-006 "留 trace"): the shell guard's `[WRITE_SCOPE]` audit
 * lines are covered by `test/suite/mwds-t03-bash-write-scope.test.ts` (63/63 at
 * HEAD); this file pins the decision layer, and the runtime rejection reason
 * carries the same machine rule token.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	judgeWriteIntent,
	judgeWriteTarget as pmJudgeWriteTarget,
	renderDefaultWriteScope,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	deriveWriteSurfacePaths,
	isAllowedWorkerFileName,
	judgeWriteTarget as judgeSurfaceTarget,
	parseWriteScopeHeader,
	WORKER_FILE_NAME_RE,
} from "../../src/extensions/agent-team-loop/shared/write-surface.ts";
import {
	registerWorkerFileTool,
	WORKER_FILE_TOOL,
	writeWorkerFile,
} from "../../src/extensions/agent-team-loop/worker/worker-file-tool.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

interface SurfaceFixture {
	root: string;
	key: string;
	keyDir: string;
	taskDir: string;
	ctx: { taskDir: string; projectRoot: string; keyDir: string; trueRoot: string };
}

const roots: string[] = [];

/** Real canonical layout: <root>/.agenticdoc/<key>/workers/<taskKey>. */
function mkFixture(key = "woc-w1"): SurfaceFixture {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mwoc-w1-"));
	roots.push(root);
	const agenticdocRoot = path.join(root, ".agenticdoc");
	const keyDir = path.join(agenticdocRoot, key);
	const taskDir = path.join(keyDir, "workers", "t1");
	fs.mkdirSync(path.join(keyDir, "evidence", "research"), { recursive: true });
	fs.mkdirSync(taskDir, { recursive: true });
	return { root, key, keyDir, taskDir, ctx: { taskDir, projectRoot: root, keyDir, trueRoot: agenticdocRoot } };
}

afterEach(() => {
	for (const dir of roots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

// ── AC-016: evidence dual basis, dispatch + runtime ──────────────────────────

describe("AC-016 evidence dual basis", () => {
	it("the shared predicate accepts both bases; the PM judge agrees", () => {
		const { ctx, keyDir } = mkFixture();
		const projectRelative = ".agenticdoc/woc-w1/evidence/research/x.md";
		const keyRelative = "evidence/research/x.md";

		const a = judgeSurfaceTarget(projectRelative, ctx);
		const b = judgeSurfaceTarget(keyRelative, ctx);
		expect(a.allowed, projectRelative).toBe(true);
		expect(a.domain).toBe("evidence");
		expect(a.target).toBe(path.join(keyDir, "evidence", "research", "x.md"));
		expect(b.allowed, keyRelative).toBe(true);
		expect(b.domain).toBe("evidence");
		expect(b.target).toBe(path.join(keyDir, "evidence", "research", "x.md"));

		expect(pmJudgeWriteTarget(projectRelative, ctx).allowed).toBe(true);
		expect(pmJudgeWriteTarget(keyRelative, ctx).allowed).toBe(true);

		verify(
			`[VERIFY] AC-016 evidence: project_relative=${a.allowed} key_relative=${b.allowed} both_resolve_same=${a.target === b.target}`,
		);
	});

	it("the runtime worker_file channel actually writes both bases (AC-006)", () => {
		const { taskDir, keyDir } = mkFixture();
		const first = writeWorkerFile(
			taskDir,
			".agenticdoc/woc-w1/evidence/research/r1.md",
			"project relative\n",
			"write",
		);
		const second = writeWorkerFile(taskDir, "evidence/research/r2.md", "key relative\n", "write");
		expect(first.ok).toBe(true);
		expect(second.ok).toBe(true);
		if (!first.ok || !second.ok) throw new Error("evidence write rejected");

		const e1 = path.join(keyDir, "evidence", "research", "r1.md");
		const e2 = path.join(keyDir, "evidence", "research", "r2.md");
		const ok =
			fs.readFileSync(e1, "utf8") === "project relative\n" && fs.readFileSync(e2, "utf8") === "key relative\n";
		expect(ok).toBe(true);
		verify(`[VERIFY] AC-006 runtime evidence: project_write=${fs.existsSync(e1)} key_write=${fs.existsSync(e2)}`);
	});

	it("the registered tool executes an evidence write and advertises the only channel (AC-007a)", async () => {
		const { taskDir, keyDir } = mkFixture();
		const tools = new Map<
			string,
			{ description: string; execute: (id: string, params: unknown) => Promise<unknown> }
		>();
		const pi = {
			registerTool: (tool: unknown) => {
				const t = tool as {
					name: string;
					description: string;
					execute: (id: string, params: unknown) => Promise<unknown>;
				};
				tools.set(t.name, t);
			},
		};
		registerWorkerFileTool(pi as never, taskDir);
		const tool = tools.get(WORKER_FILE_TOOL);
		if (!tool) throw new Error("worker_file not registered");
		expect(tool.description.toLowerCase()).toContain("only write channel");
		expect(tool.description).toContain("evidence");

		await tool.execute("id1", { file: "evidence/research/via-tool.md", content: "via tool\n", mode: "write" });
		const written = fs.existsSync(path.join(keyDir, "evidence", "research", "via-tool.md"));
		expect(written).toBe(true);
		verify(`[VERIFY] AC-007a: description_only_channel=true tool_evidence_write=${written}`);
	});
});

// ── AC-016: the 3/3 overflow family stays fail-closed ────────────────────────

describe("AC-016 overflow family fail-closed 3/3", () => {
	it("rejects ../.., another key and repo source at the shared predicate and the PM judge", () => {
		const { ctx, taskDir } = mkFixture();
		const cases: Array<{ token: string; rule: "deny" | "scope" }> = [
			{ token: "../..", rule: "scope" },
			{ token: ".agenticdoc/other-key/evidence/x.md", rule: "deny" },
			{ token: "packages/coding-agent/src/x.ts", rule: "deny" },
		];
		for (const c of cases) {
			const shared = judgeSurfaceTarget(c.token, ctx);
			expect(shared.allowed, c.token).toBe(false);
			expect(shared.rule, c.token).toBe(c.rule);
			const pm = pmJudgeWriteTarget(c.token, ctx);
			expect(pm.allowed, c.token).toBe(false);
			expect(pm.rule, c.token).toBe(c.rule);
			const runtime = writeWorkerFile(taskDir, c.token, "x", "write");
			expect(runtime.ok, c.token).toBe(false);
			if (!runtime.ok) expect(runtime.reason).toContain(c.rule === "deny" ? "denied:" : "outside-write-surface");
		}
		verify("[VERIFY] AC-016 overflow: rejected=3/3 surfaces=shared+pm+runtime rules=deny/scope");
	});

	it("rejects .git and the evidence directory body", () => {
		const { ctx } = mkFixture();
		expect(judgeSurfaceTarget(".git/config", ctx).allowed).toBe(false);
		// `evidence/` normalizes to the evidence dir itself, which is not a file
		// target; a deeper evidence path is a file target and stays writable.
		expect(judgeSurfaceTarget("evidence/", ctx).allowed).toBe(false);
		expect(judgeSurfaceTarget("evidence/research/x.md", ctx).allowed).toBe(true);
		verify("[VERIFY] AC-016 evidence body: git=false dir_body=false depth_paths_allowed=true");
	});
});

// ── AC-016: dispatch satisfiability for research + review cards ──────────────

describe("AC-016 dispatch satisfiability", () => {
	function cardVerdict(type: string, description: string) {
		const { ctx } = mkFixture();
		return judgeWriteIntent({
			type,
			description,
			taskDir: ctx.taskDir,
			projectRoot: ctx.projectRoot,
			keyDir: ctx.keyDir,
			trueRoot: ctx.trueRoot,
		});
	}

	it("a review card declaring evidence/** is now satisfiable (the red case this card fixes)", () => {
		const description = "## 唯一证据文件\n把结论写入 evidence/research/review-notes.md";
		const verdict = cardVerdict("review", description);
		expect(verdict.ok).toBe(true);
		expect(verdict.violations).toEqual([]);
		const projectRelative = cardVerdict("review", "## 唯一证据文件\n写到 .agenticdoc/woc-w1/evidence/review.md");
		expect(projectRelative.ok).toBe(true);
		verify(`[VERIFY] AC-016 review: key_relative=${verdict.ok} project_relative=${projectRelative.ok}`);
	});

	it("a research card declaring evidence/** stays satisfiable (shell role early-return; already green at HEAD)", () => {
		const verdict = cardVerdict("research", "## 唯一证据文件\n把结果写到 evidence/research/research-notes.md");
		expect(verdict.ok).toBe(true);
		expect(verdict.violations).toEqual([]);
		verify("[VERIFY] AC-016 research: satisfiable=true (shell role early-return, pre-existing)");
	});
});

// ── AC-016: one predicate, two call sites ────────────────────────────────────

describe("AC-016 single predicate evidence", () => {
	it("both call sites import judgeWriteTarget from shared/write-surface.ts", () => {
		const uiBridge = fs.readFileSync(
			path.join(REPO_ROOT, "packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts"),
			"utf8",
		);
		const workerFileTool = fs.readFileSync(
			path.join(REPO_ROOT, "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts"),
			"utf8",
		);
		expect(uiBridge).toContain('from "../shared/write-surface.ts"');
		expect(uiBridge).toMatch(/judgeWriteTarget as judgeSharedWriteTarget/);
		expect(workerFileTool).toContain('from "../shared/write-surface.ts"');
		expect(workerFileTool).toMatch(/\bjudgeWriteTarget,/);
		// No second copy of the deny table / basename regex in either adapter.
		expect(uiBridge).not.toMatch(/function pmWriteDenyReason/);
		expect(workerFileTool).not.toMatch(/WORKER_FILE_NAME_RE = \//);
		verify("[VERIFY] AC-016 single-source: ui_bridge_import=true worker_tool_import=true duplicate_deny=false");
	});

	it("behaviour parity matrix: shared predicate === PM judge on the same ctx", () => {
		const { ctx, taskDir } = mkFixture();
		const matrix = [
			".agenticdoc/woc-w1/evidence/research/x.md",
			"evidence/research/x.md",
			"report.md",
			"progress.md",
			path.join(taskDir, "notes.md"),
			".agenticdoc/other-key/evidence/x.md",
			"packages/coding-agent/src/x.ts",
			"../..",
			".git/config",
		];
		for (const token of matrix) {
			expect(judgeSurfaceTarget(token, ctx).allowed, token).toBe(pmJudgeWriteTarget(token, ctx).allowed);
		}
		verify(`[VERIFY] AC-016 parity: cases=${matrix.length} mismatches=0`);
	});
});

// ── AC-006: task-dir basename whitelist 3/3 + write_scope default face ───────

describe("AC-006 task-dir basename whitelist and default face", () => {
	it("the 3 basenames still pass at the surface and the runtime channel", () => {
		const { ctx, taskDir } = mkFixture();
		const names = ["progress.md", "report.md", "report-finding.md"];
		for (const name of names) {
			expect(judgeSurfaceTarget(name, ctx).allowed, name).toBe(true);
			expect(isAllowedWorkerFileName(name), name).toBe(true);
			expect(writeWorkerFile(taskDir, name, "x\n", "append").ok, name).toBe(true);
		}
		// Directory blindness: a whitelisted basename in a foreign dir is refused.
		expect(judgeSurfaceTarget(".agenticdoc/other-key/workers/t/report.md", ctx).allowed).toBe(false);
		verify(`[VERIFY] AC-006 basenames: allowed=3/3 directory_blind_foreign=false`);
	});

	it("the default write_scope face equals renderDefaultWriteScope (zero behaviour change)", () => {
		const { ctx, taskDir, key } = mkFixture();
		const rendered = renderDefaultWriteScope(key, "t1");
		const entries = parseWriteScopeHeader(rendered);
		expect(entries).toBeDefined();
		const tokens = [
			"progress.md",
			"report.md",
			path.join(taskDir, "notes.md"),
			".agenticdoc/woc-w1/evidence/research/x.md",
			"evidence/research/x.md",
		];
		for (const token of tokens) {
			const withDefault = judgeSurfaceTarget(token, { ...ctx, writeScope: entries });
			const without = judgeSurfaceTarget(token, ctx);
			expect(without.allowed, token).toBe(true);
			expect(withDefault.allowed, token).toBe(true);
		}
		expect(parseWriteScopeHeader("write_scope: .agenticdoc/woc-w1/workers/t1")).toEqual([
			".agenticdoc/woc-w1/workers/t1",
		]);
		verify(
			`[VERIFY] AC-006 default-face: renderDefaultWriteScope=${rendered} entries=${entries?.length} parity=${tokens.length}/${tokens.length}`,
		);
	});

	it("a narrowed write_scope fail-closes the runtime channel", () => {
		const { ctx, taskDir } = mkFixture();
		const narrow = [".agenticdoc/woc-w1/evidence"];
		const verdict = judgeSurfaceTarget("progress.md", { ...ctx, writeScope: narrow });
		expect(verdict.allowed).toBe(false);
		expect(verdict.rule).toBe("write-scope");
		const denied = writeWorkerFile(taskDir, "progress.md", "x", "append", { ...ctx, writeScope: narrow });
		expect(denied.ok).toBe(false);
		verify(`[VERIFY] AC-006 narrow-scope: progress.md_allowed=false rule=${verdict.rule}`);
	});

	it("derives the evidence anchors from the canonical taskDir layout", () => {
		const { taskDir, keyDir, root } = mkFixture();
		const derived = deriveWriteSurfacePaths(taskDir);
		expect(derived.keyDir).toBe(keyDir);
		expect(derived.trueRoot).toBe(path.join(root, ".agenticdoc"));
		expect(derived.projectRoot).toBe(root);
		expect(WORKER_FILE_NAME_RE.test("report-finding.md")).toBe(true);
		verify("[VERIFY] AC-006 derive: canonical_layout=true");
	});
});
