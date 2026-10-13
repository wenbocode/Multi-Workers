/**
 * T-13 — serve code identity / drift self-check (AC-005 fresh-process-side
 * entry).
 *
 * The Python side owns `serve.meta` identity (commit / dirty / code_digest /
 * schema) and the persistent double-channel alarm; this TS half is limited to
 * two things by the task card:
 *   1. the runtime-source skip set must also drop the `test/` DIRECTORY
 *      (69% of the files under the mw tree are fixtures — editing one must not
 *      mark a healthy serve stale), and
 *   2. the entry wiring: `readServeMeta` parses the new fields, and
 *      `serveStaleness` baselines on `meta.code_dir` instead of the checker's
 *      own tree. The mtime judge itself is unchanged.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	mwCodeNewestMtimeMs,
	readServeMeta,
	serveStaleness,
} from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";

const T = 1_700_000_000_000;
const at = (ms: number): Date => new Date(ms);

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "mwgal-t13-"));
}

function touch(rel: string, atime: number): void {
	const p = rel;
	fs.mkdirSync(path.dirname(p), { recursive: true });
	fs.writeFileSync(p, "x", "utf8");
	fs.utimesSync(p, at(atime), at(atime));
}

function writeMeta(project: string, meta: Record<string, unknown>): void {
	const mwDir = path.join(project, ".mw");
	fs.mkdirSync(mwDir, { recursive: true });
	fs.writeFileSync(path.join(mwDir, "serve.meta"), JSON.stringify(meta), "utf8");
}

const savedMwPy = process.env.MW_PY;
afterEach(() => {
	if (savedMwPy === undefined) delete process.env.MW_PY;
	else process.env.MW_PY = savedMwPy;
});

describe("mwCodeNewestMtimeMs skip set (T-13 dir-level `test`)", () => {
	it("skips the test/ directory as well as test_* files, __pycache__, dist, .tmp", () => {
		const dir = mkdtemp();
		try {
			touch(path.join(dir, "mw.py"), T);
			touch(path.join(dir, "providers.json"), T + 5_000);
			touch(path.join(dir, "autopilot", "conductor.py"), T + 10_000);
			// All newer — none may move the baseline:
			touch(path.join(dir, "test", "fixtures", "case.json"), T + 100_000);
			touch(path.join(dir, "test_dev.py"), T + 100_000);
			touch(path.join(dir, "_scratch.py"), T + 100_000);
			touch(path.join(dir, "__pycache__", "mw.cpython-314.pyc"), T + 100_000);
			touch(path.join(dir, "dist", "agent-team-loop.js"), T + 100_000);
			touch(path.join(dir, ".tmp", "framework.json"), T + 100_000);
			expect(mwCodeNewestMtimeMs(path.join(dir, "mw.py"))).toBe(T + 10_000);
		} finally {
			fs.rmSync(dir, { recursive: true, force: true });
		}
	});
});

describe("readServeMeta identity fields (T-13)", () => {
	it("parses the identity fields and keeps legacy meta readable", () => {
		const root = mkdtemp();
		try {
			writeMeta(root, {
				pid: 7,
				started_at_ms: T,
				code_dir: "/some/tree",
				commit: "a".repeat(40),
				dirty_tracked: 11,
				dirty_untracked: 9,
				code_mtime_ms: T - 1_000,
				code_digest: `sha256:${"b".repeat(64)}`,
				schema: 1,
			});
			const meta = readServeMeta(root);
			expect(meta).not.toBeNull();
			expect(meta?.pid).toBe(7);
			expect(meta?.startedAtMs).toBe(T);
			expect(meta?.codeDir).toBe("/some/tree");
			expect(meta?.commit).toBe("a".repeat(40));
			expect(meta?.dirtyTracked).toBe(11);
			expect(meta?.dirtyUntracked).toBe(9);
			expect(meta?.codeMtimeMs).toBe(T - 1_000);
			expect(meta?.codeDigest).toBe(`sha256:${"b".repeat(64)}`);
			expect(meta?.schema).toBe(1);

			// Legacy meta: only pid/started_at_ms/code_dir — still valid.
			writeMeta(root, { pid: 8, started_at_ms: T, code_dir: "/old/tree" });
			const legacy = readServeMeta(root);
			expect(legacy?.pid).toBe(8);
			expect(legacy?.codeDir).toBe("/old/tree");
			expect(legacy?.codeDigest).toBeUndefined();
			expect(legacy?.schema).toBeUndefined();
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("still rejects garbage / missing required fields", () => {
		const root = mkdtemp();
		try {
			writeMeta(root, { commit: "x" });
			expect(readServeMeta(root)).toBeNull(); // no pid/started_at_ms
			fs.writeFileSync(path.join(root, ".mw", "serve.meta"), "{not json", "utf8");
			expect(readServeMeta(root)).toBeNull();
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

describe("serveStaleness baselines on meta.code_dir (T-13 entry wiring)", () => {
	it("uses the serve's own tree, not the checker's tree", () => {
		const checker = mkdtemp();
		const serveTree = mkdtemp();
		const root = mkdtemp();
		try {
			// Checker tree (what MW_PY resolves to) is OLD.
			touch(path.join(checker, "mw.py"), T - 100_000);
			process.env.MW_PY = path.join(checker, "mw.py");
			// The serve was stamped with a DIFFERENT tree, 60s newer than start.
			touch(path.join(serveTree, "mw.py"), T + 60_000);
			writeMeta(root, {
				pid: 1,
				started_at_ms: T,
				code_dir: serveTree,
				schema: 1,
			});
			// Only the meta tree is newer; the checker's tree would say "fresh".
			expect(serveStaleness(root)?.stale).toBe(true);
			expect(serveStaleness(root)?.detail).toContain("mw code changed");
		} finally {
			fs.rmSync(checker, { recursive: true, force: true });
			fs.rmSync(serveTree, { recursive: true, force: true });
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("falls back to the checker tree when meta has no code_dir", () => {
		const checker = mkdtemp();
		const root = mkdtemp();
		try {
			touch(path.join(checker, "mw.py"), T + 60_000);
			process.env.MW_PY = path.join(checker, "mw.py");
			writeMeta(root, { pid: 1, started_at_ms: T }); // legacy, no code_dir
			expect(serveStaleness(root)?.stale).toBe(true);
		} finally {
			fs.rmSync(checker, { recursive: true, force: true });
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("keeps the mtime judge semantics (same age = fresh, newer = stale)", () => {
		const root = mkdtemp();
		try {
			writeMeta(root, { pid: 1, started_at_ms: T, code_dir: "x", schema: 1 });
			expect(serveStaleness(root, T)?.stale).toBe(false);
			expect(serveStaleness(root, T + 60_000)?.stale).toBe(true);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("still falls back to the PID file mtime when meta is gone", () => {
		const root = mkdtemp();
		try {
			const pidFile = path.join(root, ".mw", "mw.pid");
			fs.mkdirSync(path.dirname(pidFile), { recursive: true });
			fs.writeFileSync(pidFile, "1", "utf8");
			fs.utimesSync(pidFile, at(T), at(T));
			expect(serveStaleness(root, T)?.stale).toBe(false);
			expect(serveStaleness(root, T + 60_000)?.stale).toBe(true);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
