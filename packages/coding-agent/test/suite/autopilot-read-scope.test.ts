/**
 * Tests for the autopilot L2 read_scope interceptor (goal-autopilot T-13,
 * design D-106, AC-009/VC-011).
 *
 * - Pure containment/cap algorithm: worker/read-scope.ts (realpath-based
 *   containment, segment boundary, caps with defaults).
 * - Worker wiring: workerModeActivate registers a tool_call blocker when
 *   task.md carries read_scope; rejections land in trace.log ([READ_SCOPE])
 *   at block time and in output.md (## Read Scope Rejections) at exit.
 * - No read_scope → no interceptor at all (AC-012 red line).
 *
 * No provider APIs, keys, or network: the tool_call handler is invoked
 * directly against a fake ExtensionAPI (same pattern as the watchdog
 * integration tests in test/extensions/agent-team-loop.test.ts).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	applyParentRootUnion,
	checkReadScopeCall,
	DEFAULT_READ_BYTE_CAP,
	DEFAULT_READ_FILE_CAP,
	isSameOrUnder,
	isWithinScope,
	normalizeForCompare,
	parentRootFromTaskContent,
	type ReadScopeState,
	readScopeConfigFromMeta,
} from "../../src/extensions/agent-team-loop/worker/read-scope.ts";
import { parseTaskMd, workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "rs-test-"));
}

// ── Pure containment algorithm (D-106) ───────────────────────────────────────

describe("read-scope containment (D-106)", () => {
	it("segment boundary: goal-autopilot-evil never matches scope goal-autopilot", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "goal-autopilot"), { recursive: true });
		fs.mkdirSync(path.join(root, "goal-autopilot-evil"), { recursive: true });
		expect(isWithinScope(root, ["goal-autopilot"], "goal-autopilot")).toBe(true);
		expect(isWithinScope(root, ["goal-autopilot"], "goal-autopilot/design.md")).toBe(true);
		expect(isWithinScope(root, ["goal-autopilot"], "goal-autopilot-evil")).toBe(false);
		expect(isWithinScope(root, ["goal-autopilot"], "goal-autopilot-evil/task.md")).toBe(false);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("../ escapes are collapsed lexically before comparison", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.writeFileSync(path.join(root, "outside.txt"), "x", "utf8");
		expect(isWithinScope(root, ["allowed"], "allowed/../../outside.txt")).toBe(false);
		expect(isWithinScope(root, ["allowed"], "../outside.txt")).toBe(false);
		expect(isWithinScope(root, ["allowed"], "allowed/../allowed/file.txt")).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("symlink/junction inside the scope pointing out is blocked, including for nonexistent tails", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.mkdirSync(path.join(root, "outside"), { recursive: true });
		fs.writeFileSync(path.join(root, "outside", "data.txt"), "x", "utf8");
		// "junction" is a no-op type argument on POSIX (plain symlink there) and
		// needs no privileges on Windows.
		fs.symlinkSync(path.join(root, "outside"), path.join(root, "allowed", "escape"), "junction");
		expect(isWithinScope(root, ["allowed"], "allowed/escape/data.txt")).toBe(false);
		// Nonexistent tail: the deepest existing ancestor (the symlink) still
		// resolves, so normalization cannot be bypassed through missing paths.
		expect(isWithinScope(root, ["allowed"], "allowed/escape/missing.txt")).toBe(false);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("symlink/junction outside the scope pointing in resolves in-scope (allowed)", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed", "deep"), { recursive: true });
		fs.symlinkSync(path.join(root, "allowed"), path.join(root, "shortcut"), "junction");
		expect(isWithinScope(root, ["allowed"], "shortcut/deep/file.txt")).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("nonexistent paths normalize through the deepest existing ancestor", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "a"), { recursive: true });
		const n = normalizeForCompare(root, "a/b/c.txt");
		expect(n).toBe(path.join(fs.realpathSync(path.join(root, "a")), "b", "c.txt"));
		// Missing path under the scope root stays contained; a missing path that
		// lexically escapes does not.
		expect(isWithinScope(root, ["a"], "a/missing/deeper/file.txt")).toBe(true);
		expect(isWithinScope(root, ["a"], "a/../../missing/file.txt")).toBe(false);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("nonexistent scope entries still contain their equally nonexistent children", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
		expect(
			isWithinScope(root, [".agenticdoc/goal-autopilot/keys/k13"], ".agenticdoc/goal-autopilot/keys/k13/e/x.md"),
		).toBe(true);
		// Segment boundary holds on nonexistent paths too.
		expect(
			isWithinScope(
				root,
				[".agenticdoc/goal-autopilot/keys/k13"],
				".agenticdoc/goal-autopilot/keys/k13-evil/e/x.md",
			),
		).toBe(false);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("win32: case-insensitive comparison with drive-letter normalization; POSIX stays case-sensitive", () => {
		if (process.platform === "win32") {
			expect(isSameOrUnder("H:\\Repo", "h:\\repo\\sub")).toBe(true);
			expect(isSameOrUnder("H:\\Repo", "h:\\repo-evil")).toBe(false);
		} else {
			expect(isSameOrUnder("/repo", "/Repo/sub")).toBe(false);
		}
		// Filesystem level: a differently-cased spelling of the same file matches
		// on win32 (case-insensitive fs) and not on POSIX (different file).
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.writeFileSync(path.join(root, "allowed", "File.TXT"), "x", "utf8");
		const cased = isWithinScope(root, ["allowed"], path.join(root, "ALLOWED", "file.txt"));
		expect(cased).toBe(process.platform === "win32");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("absolute requests, forward-slash entries, and file scope entries all normalize identically", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.writeFileSync(path.join(root, "allowed", "file.txt"), "x", "utf8");
		fs.writeFileSync(path.join(root, "goal.md"), "x", "utf8");
		// Forward-slash (conductor format) + absolute request path.
		expect(isWithinScope(root, ["allowed/"], path.join(root, "allowed", "file.txt"))).toBe(true);
		// File entry: exact match allowed, sibling file not.
		expect(isWithinScope(root, ["goal.md"], "goal.md")).toBe(true);
		expect(isWithinScope(root, ["goal.md"], "secret.txt")).toBe(false);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Caps (D-106) ─────────────────────────────────────────────────────────────

describe("read-scope caps", () => {
	it("file cap: the (cap+1)-th read-ish call blocks with rule=cap-file", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.writeFileSync(path.join(root, "allowed", "a.txt"), "x", "utf8");
		const config = { scope: ["allowed"], denyGlobs: [], fileCap: 2, byteCap: DEFAULT_READ_BYTE_CAP };
		const state: ReadScopeState = { allowedCalls: 0, bytesRead: 0 };

		const v1 = checkReadScopeCall(root, config, state, "read", "allowed/a.txt");
		expect(v1.allowed).toBe(true);
		state.allowedCalls += 1;
		const v2 = checkReadScopeCall(root, config, state, "ls", "allowed");
		expect(v2.allowed).toBe(true);
		state.allowedCalls += 1;

		const v3 = checkReadScopeCall(root, config, state, "read", "allowed/a.txt");
		expect(v3.allowed).toBe(false);
		expect(v3.rule).toBe("cap-file");
		expect(v3.reason).toContain("allowed/a.txt");
		expect(v3.reason).toContain("rule=cap-file");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("byte cap: read charges statSync bytes, ls/find/grep charge none; exactly reaching the cap is allowed", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.writeFileSync(path.join(root, "allowed", "a.txt"), "x".repeat(60), "utf8");
		fs.writeFileSync(path.join(root, "allowed", "b.txt"), "x".repeat(50), "utf8");
		fs.writeFileSync(path.join(root, "allowed", "c.txt"), "x".repeat(100), "utf8");
		fs.writeFileSync(path.join(root, "allowed", "d.txt"), "x", "utf8");
		const config = { scope: ["allowed"], denyGlobs: [], fileCap: DEFAULT_READ_FILE_CAP, byteCap: 100 };
		const state: ReadScopeState = { allowedCalls: 0, bytesRead: 0 };

		// 60B read passes and charges 60.
		const v1 = checkReadScopeCall(root, config, state, "read", "allowed/a.txt");
		expect(v1.allowed).toBe(true);
		expect(v1.chargedBytes).toBe(60);
		state.allowedCalls += 1;
		state.bytesRead += v1.chargedBytes;

		// 60 + 50 > 100 → cap-byte.
		const v2 = checkReadScopeCall(root, config, state, "read", "allowed/b.txt");
		expect(v2.allowed).toBe(false);
		expect(v2.rule).toBe("cap-byte");
		expect(v2.reason).toContain("allowed/b.txt");
		expect(v2.reason).toContain("rule=cap-byte");

		// ls/grep/find never charge bytes.
		for (const tool of ["ls", "grep", "find"] as const) {
			const v = checkReadScopeCall(root, config, state, tool, "allowed");
			expect(v.allowed).toBe(true);
			expect(v.chargedBytes).toBe(0);
		}

		// A read that lands exactly on the cap (0 + 100 = 100) is allowed...
		const fresh: ReadScopeState = { allowedCalls: 0, bytesRead: 0 };
		const v3 = checkReadScopeCall(root, config, fresh, "read", "allowed/c.txt");
		expect(v3.allowed).toBe(true);
		expect(v3.chargedBytes).toBe(100);
		// ...and the very next byte over it blocks.
		fresh.bytesRead += v3.chargedBytes;
		const v4 = checkReadScopeCall(root, config, fresh, "read", "allowed/d.txt");
		expect(v4.allowed).toBe(false);
		expect(v4.rule).toBe("cap-byte");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("out-of-scope is checked before caps; defaults are 8 files / 65536 bytes", () => {
		const root = mkdtemp();
		fs.writeFileSync(path.join(root, "outside.txt"), "x", "utf8");
		const config = { scope: ["allowed"], denyGlobs: [], fileCap: 0, byteCap: 0 };
		// Cap would fire on everything, but the scope violation wins.
		const v = checkReadScopeCall(root, config, { allowedCalls: 0, bytesRead: 0 }, "read", "outside.txt");
		expect(v.rule).toBe("scope");

		expect(DEFAULT_READ_FILE_CAP).toBe(8);
		expect(DEFAULT_READ_BYTE_CAP).toBe(65536);
		expect(readScopeConfigFromMeta({ readScope: ["x"] })).toEqual({
			scope: ["x"],
			denyGlobs: [],
			fileCap: 8,
			byteCap: 65536,
		});
		expect(readScopeConfigFromMeta({ readScope: ["x"], readFileCap: 3, readByteCap: 100 })).toEqual({
			scope: ["x"],
			denyGlobs: [],
			fileCap: 3,
			byteCap: 100,
		});
		// No read_scope and no deny_globs → undefined → interception disabled.
		expect(readScopeConfigFromMeta({})).toBeUndefined();
		// Present-but-empty scope fails closed.
		expect(readScopeConfigFromMeta({ readScope: [] })?.scope).toEqual([]);
		// deny_globs without read_scope → deny-only mode (scope=null).
		expect(readScopeConfigFromMeta({ denyGlobs: ["**/*.uasset"] })).toEqual({
			scope: null,
			denyGlobs: ["**/*.uasset"],
			fileCap: 8,
			byteCap: 65536,
		});
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── deny globs (mw-dual-workspace AC-006, D-003 dual basis) ──────────────────

describe("deny globs: dual-basis matching and deny priority", () => {
	it("VC-011: **/*.uasset matches absolute (backslash) and relative bases", () => {
		const root = mkdtemp();
		const config = { scope: null, denyGlobs: ["**/*.uasset"], fileCap: 8, byteCap: 65536 };
		fs.mkdirSync(path.join(root, "Content"), { recursive: true });
		const asset = path.join(root, "Content", "X.uasset");
		fs.writeFileSync(asset, "bin", "utf8");

		// relative request + absolute request both hit
		const vRel = checkReadScopeCall(root, config, { allowedCalls: 0, bytesRead: 0 }, "read", "Content/X.uasset");
		expect(vRel.allowed).toBe(false);
		expect(vRel.rule).toBe("deny-glob");
		const vAbs = checkReadScopeCall(root, config, { allowedCalls: 0, bytesRead: 0 }, "read", asset);
		expect(vAbs.allowed).toBe(false);
		expect(vAbs.rule).toBe("deny-glob");
		expect(vAbs.reason).toContain("deny glob '**/*.uasset'");
		expect(vAbs.reason).toContain("[rule=deny-glob]");
		// non-denied sibling passes (deny-only mode: no scope, no caps)
		fs.writeFileSync(path.join(root, "Content", "ok.txt"), "x", "utf8");
		const vOk = checkReadScopeCall(root, config, { allowedCalls: 0, bytesRead: 0 }, "read", "Content/ok.txt");
		expect(vOk.allowed).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-011: bare-directory form DerivedDataCache/** hits via the root-relative basis only", () => {
		const root = mkdtemp();
		const config = { scope: null, denyGlobs: ["DerivedDataCache/**"], fileCap: 8, byteCap: 65536 };
		const dd = path.join(root, "DerivedDataCache", "a", "b");
		fs.mkdirSync(dd, { recursive: true });

		const v = checkReadScopeCall(root, config, { allowedCalls: 0, bytesRead: 0 }, "ls", dd);
		expect(v.allowed).toBe(false);
		expect(v.rule).toBe("deny-glob");
		// nested path with ../ escape still normalizes into the deny basis
		const vEscape = checkReadScopeCall(
			root,
			config,
			{ allowedCalls: 0, bytesRead: 0 },
			"find",
			path.join(root, "Content", "..", "DerivedDataCache"),
		);
		expect(vEscape.allowed).toBe(false);
		// outside the denied dir is untouched
		const vOk = checkReadScopeCall(root, config, { allowedCalls: 0, bytesRead: 0 }, "ls", path.join(root, "Content"));
		expect(vOk.allowed).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-012: deny wins over an allow scope entry (deny priority)", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.writeFileSync(path.join(root, "allowed", "a.uasset"), "bin", "utf8");
		const config = {
			scope: ["allowed"],
			denyGlobs: ["**/*.uasset"],
			fileCap: 8,
			byteCap: 65536,
		};
		const v = checkReadScopeCall(root, config, { allowedCalls: 0, bytesRead: 0 }, "read", "allowed/a.uasset");
		expect(v.allowed).toBe(false);
		expect(v.rule).toBe("deny-glob"); // not "scope" — the allow entry does not rescue it
		fs.rmSync(root, { recursive: true, force: true });
		console.log("[VERIFY] VC-012: precedence=deny");
	});
});

// ── parseTaskMd frontmatter extension ────────────────────────────────────────

describe("parseTaskMd read_scope frontmatter", () => {
	function writeTask(root: string, content: string): string {
		const taskDir = path.join(root, "k", "workers", "t-scope");
		fs.mkdirSync(taskDir, { recursive: true });
		const md = path.join(taskDir, "task.md");
		fs.writeFileSync(md, content, "utf8");
		return md;
	}

	it("parses the read_scope block list and both cap keys (dispatch.py render shape)", () => {
		const root = mkdtemp();
		const md = writeTask(
			root,
			[
				"---",
				"type: verifier",
				"origin: conductor",
				"loop: L1",
				"attempt: 1",
				"read_scope:",
				"  - .agenticdoc/goal-autopilot/keys/k13",
				"  - goal.md",
				"l2_read_file_cap: 4",
				"l2_read_byte_cap: 2048",
				"---",
				"",
				"Verify the phase gate.",
				"",
			].join("\n"),
		);
		const meta = parseTaskMd(md);
		expect(meta.readScope).toEqual([".agenticdoc/goal-autopilot/keys/k13", "goal.md"]);
		expect(meta.readFileCap).toBe(4);
		expect(meta.readByteCap).toBe(2048);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("missing read_scope / caps stay undefined; invalid caps are ignored", () => {
		const root = mkdtemp();
		let meta = parseTaskMd(writeTask(root, "type: coding\n\nwork\n"));
		expect(meta.readScope).toBeUndefined();
		expect(meta.readFileCap).toBeUndefined();
		expect(meta.readByteCap).toBeUndefined();

		meta = parseTaskMd(
			writeTask(root, "type: coding\nl2_read_file_cap: abc\nl2_read_byte_cap: -5\nread_scope:\n  - ok\n\nwork\n"),
		);
		expect(meta.readScope).toEqual(["ok"]);
		expect(meta.readFileCap).toBeUndefined();
		expect(meta.readByteCap).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("read_scope present but empty stays defined (fail-closed)", () => {
		const root = mkdtemp();
		const meta = parseTaskMd(writeTask(root, "type: verifier\nread_scope:\n---\n\nwork\n"));
		expect(meta.readScope).toEqual([]);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("deny_globs parses as a quoted/unquoted block list (mw-dual-workspace)", () => {
		const root = mkdtemp();
		const meta = parseTaskMd(
			writeTask(
				root,
				`${["type: coding", "deny_globs:", '  - "**/*.uasset"', "  - '**/*.umap'", "  - DerivedDataCache/**", ""].join("\n")}\nwork\n`,
			),
		);
		expect(meta.denyGlobs).toEqual(["**/*.uasset", "**/*.umap", "DerivedDataCache/**"]);
		// readScope untouched by deny_globs parsing
		expect(meta.readScope).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Worker-mode wiring (VC-011) ──────────────────────────────────────────────

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
			const cbs = handlers.get("tool_call") ?? [];
			return cbs[0]?.({ type: "tool_call", toolCallId: "tc", toolName, input }) as
				| { block?: boolean; reason?: string }
				| undefined;
		},
		interceptorCount: () => handlers.get("tool_call")?.length ?? 0,
	};
}

/** Write a conductor-shaped task.md ({owner}/workers/{taskKey}/task.md) with
 * the given frontmatter lines, activate worker-mode against it with cwd =
 * root (the launcher guarantee the containment base relies on). */
async function startScopedWorker(
	root: string,
	taskKey: string,
	frontmatter: string[],
): Promise<{ worker: FakeWorker; taskDir: string }> {
	const taskDir = path.join(root, "goal-autopilot", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(
		path.join(taskDir, "task.md"),
		`---\ntype: verifier\n${frontmatter.join("\n")}\n---\n\nVerify the phase gate.\n`,
		"utf8",
	);
	process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return { worker, taskDir };
}

describe("worker-mode read_scope wiring (AC-009)", () => {
	it("VC-011: out-of-scope read blocked with path+rule in the reason, logged to output.md, in-scope read allowed", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.writeFileSync(path.join(root, "allowed", "file.txt"), "in scope", "utf8");
		fs.writeFileSync(path.join(root, "secret.txt"), "out of scope", "utf8");

		const cwd = process.cwd();
		process.chdir(root);
		try {
			const { worker, taskDir } = await startScopedWorker(root, "ap-t13-vc011", ["read_scope:", "  - allowed"]);
			expect(worker.interceptorCount()).toBe(1);

			// (3) In-scope call passes: no block.
			expect(worker.toolCall("read", { path: "allowed/file.txt" })).toBeUndefined();

			// (1) Out-of-scope call is blocked; the reason carries path + rule.
			const blocked = worker.toolCall("read", { path: "secret.txt" });
			expect(blocked?.block).toBe(true);
			expect(blocked?.reason).toContain("secret.txt");
			expect(blocked?.reason).toContain("rule=scope");

			// The block is recorded in trace.log at block time.
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toMatch(/\[READ_SCOPE\] \S+ blocked path=secret\.txt rule=scope tool=read/);

			// (2) The rejection section lands in output.md on the exit write.
			worker.emit("agent_end", { messages: [] });
			worker.emit("agent_settled");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("## Read Scope Rejections");
			expect(output).toMatch(/\| read \| scope \| secret\.txt \| \S+ \|/);
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("containment matrix through the wiring: segment boundary, ../, non-read tools untouched", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "goal-autopilot"), { recursive: true });
		fs.mkdirSync(path.join(root, "goal-autopilot-evil"), { recursive: true });
		fs.writeFileSync(path.join(root, "goal-autopilot", "design.md"), "d", "utf8");
		fs.writeFileSync(path.join(root, "goal-autopilot-evil", "task.md"), "e", "utf8");
		fs.writeFileSync(path.join(root, "outside.txt"), "x", "utf8");

		const cwd = process.cwd();
		process.chdir(root);
		try {
			const { worker } = await startScopedWorker(root, "ap-t13-matrix", ["read_scope:", "  - goal-autopilot"]);

			expect(worker.toolCall("read", { path: "goal-autopilot/design.md" })).toBeUndefined();
			expect(worker.toolCall("read", { path: "goal-autopilot/sub/../design.md" })).toBeUndefined();
			expect(worker.toolCall("grep", { pattern: "x", path: "goal-autopilot" })).toBeUndefined();
			expect(worker.toolCall("find", { pattern: "*.md", path: "goal-autopilot" })).toBeUndefined();

			const evil = worker.toolCall("read", { path: "goal-autopilot-evil/task.md" });
			expect(evil?.block).toBe(true);
			expect(evil?.reason).toContain("rule=scope");

			const escapeBlocked = worker.toolCall("ls", { path: "goal-autopilot/../outside.txt" });
			expect(escapeBlocked?.block).toBe(true);

			// Non-read tools are never intercepted by the read scope.
			expect(worker.toolCall("write", { path: "outside/new.txt", content: "x" })).toBeUndefined();
			expect(worker.toolCall("bash", { command: "cat outside.txt" })).toBeUndefined();
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("ls/find/grep without a path target the project root and are blocked when it is out of scope", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });

		const cwd = process.cwd();
		process.chdir(root);
		try {
			const { worker } = await startScopedWorker(root, "ap-t13-nopath", ["read_scope:", "  - allowed"]);

			for (const [tool, input] of [
				["ls", {}],
				["grep", { pattern: "x" }],
				["find", { pattern: "*.ts" }],
			] as const) {
				const blocked = worker.toolCall(tool, input);
				expect(blocked?.block, tool).toBe(true);
				expect(blocked?.reason).toContain("rule=scope");
			}
			// An explicit in-scope path on the same tools passes.
			expect(worker.toolCall("ls", { path: "allowed" })).toBeUndefined();
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("cap-file and cap-byte block through the wiring and land in the output.md section", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.writeFileSync(path.join(root, "allowed", "a.txt"), "x".repeat(100), "utf8");
		fs.writeFileSync(path.join(root, "allowed", "b.txt"), "x".repeat(60), "utf8");
		fs.writeFileSync(path.join(root, "allowed", "c.txt"), "x".repeat(10), "utf8");

		const cwd = process.cwd();
		process.chdir(root);
		try {
			const { worker, taskDir } = await startScopedWorker(root, "ap-t13-caps", [
				"read_scope:",
				"  - allowed",
				"l2_read_file_cap: 2",
				"l2_read_byte_cap: 150",
			]);

			// 1st call: allowed, charges 100 bytes.
			expect(worker.toolCall("read", { path: "allowed/a.txt" })).toBeUndefined();
			// 2nd read would push 100 + 60 > 150 → cap-byte.
			const byte = worker.toolCall("read", { path: "allowed/b.txt" });
			expect(byte?.block).toBe(true);
			expect(byte?.reason).toContain("rule=cap-byte");
			// ls charges no bytes: 2nd allowed call.
			expect(worker.toolCall("ls", { path: "allowed" })).toBeUndefined();
			// 3rd read-ish call → cap-file.
			const file = worker.toolCall("read", { path: "allowed/c.txt" });
			expect(file?.block).toBe(true);
			expect(file?.reason).toContain("rule=cap-file");

			worker.emit("agent_end", { messages: [] });
			worker.emit("agent_settled");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toMatch(/\| read \| cap-byte \| allowed\/b\.txt \| \S+ \|/);
			expect(output).toMatch(/\| read \| cap-file \| allowed\/c\.txt \| \S+ \|/);
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toMatch(/\[READ_SCOPE\] \S+ blocked path=allowed\/b\.txt rule=cap-byte tool=read/);
			expect(trace).toMatch(/\[READ_SCOPE\] \S+ blocked path=allowed\/c\.txt rule=cap-file tool=read/);
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-012: task.md without read_scope registers no interceptor (zero behavior change)", async () => {
		const root = mkdtemp();
		fs.writeFileSync(path.join(root, "secret.txt"), "x", "utf8");

		const cwd = process.cwd();
		process.chdir(root);
		try {
			const { worker, taskDir } = await startScopedWorker(root, "ap-t13-legacy", []);
			expect(worker.interceptorCount()).toBe(0);

			// An out-of-scope read passes untouched.
			expect(worker.toolCall("read", { path: "secret.txt" })).toBeUndefined();

			worker.emit("agent_end", { messages: [] });
			worker.emit("agent_settled");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).not.toContain("## Read Scope Rejections");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).not.toContain("[READ_SCOPE]");
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("mw-dual-workspace VC-011: deny globs block read/ls/find/grep 100% with rule=deny-glob in trace", async () => {
		const root = mkdtemp();
		for (const dir of ["Content", "DerivedDataCache/a", "allowed"]) {
			fs.mkdirSync(path.join(root, dir), { recursive: true });
		}
		fs.writeFileSync(path.join(root, "Content", "X.uasset"), "bin", "utf8");
		fs.writeFileSync(path.join(root, "DerivedDataCache", "a", "b"), "x", "utf8");
		fs.writeFileSync(path.join(root, "allowed", "ok.txt"), "x", "utf8");

		const cwd = process.cwd();
		process.chdir(root);
		try {
			const { worker, taskDir } = await startScopedWorker(root, "ap-dual-vc011", [
				"read_scope:",
				"  - allowed",
				"  - Content",
				"  - DerivedDataCache",
				"deny_globs:",
				'  - "**/*.uasset"',
				"  - DerivedDataCache/**",
			]);
			expect(worker.interceptorCount()).toBe(1);

			// Both deny forms x all four read-ish tools: 100% blocked.
			const blocked = [
				worker.toolCall("read", { path: "Content/X.uasset" }),
				worker.toolCall("ls", { path: "Content/X.uasset" }),
				worker.toolCall("find", { path: "Content/X.uasset" }),
				worker.toolCall("grep", { path: "Content/X.uasset" }),
				worker.toolCall("ls", { path: "DerivedDataCache/a" }),
				worker.toolCall("find", { path: "DerivedDataCache" }),
			];
			for (const b of blocked) {
				expect(b?.block).toBe(true);
				expect(b?.reason).toContain("[rule=deny-glob]");
			}
			// In-scope, non-denied read still passes.
			expect(worker.toolCall("read", { path: "allowed/ok.txt" })).toBeUndefined();

			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toMatch(/\[READ_SCOPE\] \S+ blocked path=Content\/X\.uasset rule=deny-glob tool=read/);
			expect(trace).toMatch(/\[READ_SCOPE\] \S+ blocked path=Content\/X\.uasset rule=deny-glob tool=grep/);
			expect(trace).toMatch(/\[READ_SCOPE\] \S+ blocked path=DerivedDataCache\/a rule=deny-glob tool=ls/);
			const denyLines = trace.split("\n").filter((l) => l.includes("rule=deny-glob"));
			expect(denyLines.length).toBe(6);
			console.log(
				`[VERIFY] VC-011: deny-block-rate=100 trace-has-reason=true (blocks=${blocked.length}, trace-lines=${denyLines.length})`,
			);
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Partition extended-workspace union (mw-partition-parent-extended) ────────

describe("partition parent-root union (mw-partition-parent-extended)", () => {
	const PROFILE_BODY_OLD_LABEL = (parent: string, partition: string) =>
		`<!-- mw-profile: v2 -->\n[mw] mode: partition\n[mw] Workspace profile (target.yml essentials, injected at dispatch;\nfull file: ${partition}\\.agenticdoc\\target.yml)\nControl workspace: ${partition}\nParent root: ${parent}\nPartition root (worker cwd): ${partition}\n`;
	const PROFILE_BODY_NEW_LABEL = (parent: string, partition: string) =>
		PROFILE_BODY_OLD_LABEL(parent, partition).replace(
			`Parent root: ${parent}`,
			`Parent root (extended workspace, writable): ${parent}`,
		);

	it("VC-002: parentRootFromTaskContent parses old and annotated labels, gates on the mode line", () => {
		const oldLabel = PROFILE_BODY_OLD_LABEL("P:/parent", "P:/shard");
		expect(parentRootFromTaskContent(oldLabel)).toBe("P:/parent");
		const newLabel = PROFILE_BODY_NEW_LABEL("P:/parent", "P:/shard");
		expect(parentRootFromTaskContent(newLabel)).toBe("P:/parent");
		// No mode line → null even with a Parent root line present.
		expect(parentRootFromTaskContent(`Parent root: P:/parent\n`)).toBeNull();
		// Non-partition mode line → null.
		expect(parentRootFromTaskContent(`[mw] mode: dual\nParent root: P:/parent\n`)).toBeNull();
		// Mode line but no Parent root line → null.
		expect(parentRootFromTaskContent(`[mw] mode: partition\nPartition root: P:/shard\n`)).toBeNull();
		console.log("[VERIFY] VC-002: parentRoot=P (old+new label), null (no mode/no line/dual)");
	});

	it("VC-003: applyParentRootUnion appends only to a non-empty scope, never to empty/deny-only/undefined", () => {
		const scoped = readScopeConfigFromMeta({ readScope: ["src/"], denyGlobs: [] })!;
		const unioned = applyParentRootUnion(scoped, "P:/parent");
		expect(unioned).not.toBe(scoped);
		expect(unioned?.scope).toEqual(["src/", "P:/parent"]);
		expect(unioned?.denyGlobs).toEqual(scoped.denyGlobs);
		expect(unioned?.fileCap).toBe(scoped.fileCap);
		// undefined config (no read_scope/deny_globs at all).
		expect(applyParentRootUnion(undefined, "P:/parent")).toBeUndefined();
		// Deny-only (scope=null) and the fail-closed empty form stay untouched —
		// same reference back, never a manufactured containment.
		const denyOnly = readScopeConfigFromMeta({ denyGlobs: ["**/x"] })!;
		expect(applyParentRootUnion(denyOnly, "P:/parent")).toBe(denyOnly);
		const emptyScope = readScopeConfigFromMeta({ readScope: [] })!;
		expect(applyParentRootUnion(emptyScope, "P:/parent")).toBe(emptyScope);
		// parentRoot null → unchanged.
		expect(applyParentRootUnion(scoped, null)).toBe(scoped);
		console.log("[VERIFY] VC-003: union=appended (non-empty scope), unchanged (undefined/null/empty)");
	});

	it("VC-004/VC-006: wiring — parent reads allowed via union, writes never intercepted, outside still blocked", async () => {
		const root = mkdtemp();
		const parent = mkdtemp();
		fs.mkdirSync(path.join(root, "allowed"), { recursive: true });
		fs.mkdirSync(path.join(parent, "combat"), { recursive: true });
		fs.writeFileSync(path.join(root, "allowed", "file.txt"), "in scope", "utf8");
		fs.writeFileSync(path.join(parent, "combat", "existing.cpp"), "parent code", "utf8");
		fs.writeFileSync(path.join(root, "secret.txt"), "out of scope", "utf8");

		const cwd = process.cwd();
		process.chdir(root);
		try {
			// Local variant of startScopedWorker carrying the v2 profile body
			// (old label form — the union must keep working across the label change).
			const taskDir = path.join(root, "goal-autopilot", "workers", "mwppe-union");
			fs.mkdirSync(taskDir, { recursive: true });
			fs.writeFileSync(
				path.join(taskDir, "task.md"),
				`---\ntype: coding\nread_scope:\n  - allowed\n---\n\n${PROFILE_BODY_OLD_LABEL(parent, root)}`,
				"utf8",
			);
			process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
			const worker = fakeWorkerPi();
			await workerModeActivate(worker.pi);
			expect(worker.interceptorCount()).toBe(1);

			// In-scope read passes.
			expect(worker.toolCall("read", { path: "allowed/file.txt" })).toBeUndefined();
			// Parent read passes via the union (extended workspace).
			expect(worker.toolCall("read", { path: path.join(parent, "combat", "existing.cpp") })).toBeUndefined();
			// Out-of-scope (non-parent) read still blocks.
			const blocked = worker.toolCall("read", { path: "secret.txt" });
			expect(blocked?.block).toBe(true);
			expect(blocked?.reason).toContain("rule=scope");

			// Writes into the parent are never intercepted (AC-004): write/edit/bash.
			expect(
				worker.toolCall("write", { path: path.join(parent, "combat", "new.cpp"), content: "x" }),
			).toBeUndefined();
			expect(worker.toolCall("edit", { path: path.join(parent, "combat", "existing.cpp") })).toBeUndefined();
			expect(
				worker.toolCall("bash", { command: `type "${path.join(parent, "combat", "existing.cpp")}"` }),
			).toBeUndefined();

			worker.emit("agent_end", { messages: [] });
			worker.emit("agent_settled");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("## Read Scope Rejections");
			expect(output).not.toContain("new.cpp");
			expect(output).not.toContain("existing.cpp");
			console.log("[VERIFY] VC-004: parent_read=allowed, outside=blocked; VC-006: write/edit/bash=unintercepted");
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
		fs.rmSync(parent, { recursive: true, force: true });
	});

	it("VC-005: deny globs still win over the parent union (rule=deny-glob)", async () => {
		const root = mkdtemp();
		const parent = mkdtemp();
		fs.mkdirSync(path.join(parent, "DerivedDataCache", "a"), { recursive: true });
		fs.mkdirSync(path.join(parent, "combat"), { recursive: true });
		fs.writeFileSync(path.join(parent, "DerivedDataCache", "a", "b"), "x", "utf8");
		fs.writeFileSync(path.join(parent, "combat", "ok.cpp"), "x", "utf8");

		const cwd = process.cwd();
		process.chdir(root);
		try {
			const taskDir = path.join(root, "goal-autopilot", "workers", "mwppe-deny");
			fs.mkdirSync(taskDir, { recursive: true });
			// Annotated label form through the wiring (post-T-03 shape).
			fs.writeFileSync(
				path.join(taskDir, "task.md"),
				`---\ntype: coding\nread_scope:\n  - .\ndeny_globs:\n  - '**/DerivedDataCache/**'\n---\n\n${PROFILE_BODY_NEW_LABEL(parent, root)}`,
				"utf8",
			);
			process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
			const worker = fakeWorkerPi();
			await workerModeActivate(worker.pi);
			expect(worker.interceptorCount()).toBe(1);

			// Parent path matching a deny glob blocks even though the parent root
			// is in the allowed scope (deny first).
			const blocked = worker.toolCall("read", {
				path: path.join(parent, "DerivedDataCache", "a", "b"),
			});
			expect(blocked?.block).toBe(true);
			expect(blocked?.reason).toContain("rule=deny-glob");
			// Non-denied parent path still passes via the union.
			expect(worker.toolCall("read", { path: path.join(parent, "combat", "ok.cpp") })).toBeUndefined();
			console.log("[VERIFY] VC-005: parent_deny=blocked (rule=deny-glob), parent_ok=allowed");
		} finally {
			process.chdir(cwd);
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
		fs.rmSync(parent, { recursive: true, force: true });
	});
});
