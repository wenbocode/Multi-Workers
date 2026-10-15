import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
	lstatSync,
	mkdirSync,
	mkdtempSync,
	readdirSync,
	readFileSync,
	renameSync,
	rmSync,
	statSync,
	symlinkSync,
	unlinkSync,
	writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { detachNodeModulesLink } from "./detach-node-modules-link.mjs";

const isWindows = process.platform === "win32";

function createFixtureRoot() {
	return mkdtempSync(join(tmpdir(), "pi-detach-node-modules-link-"));
}

// A directory link: junction on Windows (no elevated rights needed), directory symlink elsewhere.
function createDirectoryLink(target, link) {
	if (isWindows) {
		execFileSync("cmd", ["/c", "mklink", "/J", link, target], { stdio: "ignore" });
	} else {
		symlinkSync(target, link, "dir");
	}
}

// Removes the link entry only (no /S, no trailing separator) so the target is never traversed.
function removeDirectoryLink(link) {
	if (isWindows) {
		execFileSync("cmd", ["/c", "rmdir", link], { stdio: "ignore" });
	} else {
		unlinkSync(link);
	}
}

// Cleanup per the task card: drop each link without /S first, then delete the fixture root. The root
// removal is Node's rmSync, which never follows reparse points; links that cmd cannot address (odd
// path characters) are covered by it as well.
function cleanupFixture(root, links = []) {
	for (const link of links) {
		try {
			removeDirectoryLink(link);
		} catch {
			// Already gone (POS-1) or not addressable via cmd (ABORT-3); the root removal below still runs.
		}
	}
	rmSync(root, { recursive: true, force: true });
}

function snapshotDirectory(root) {
	return readdirSync(root, { recursive: true })
		.map((entry) => entry.split("\\").join("/"))
		.sort()
		.map((entry) => {
			const path = join(root, entry);
			const stats = statSync(path);
			const isFile = stats.isFile();
			return {
				entry,
				type: isFile ? "file" : "dir",
				size: isFile ? stats.size : null,
				mtimeMs: stats.mtimeMs,
				content: isFile ? readFileSync(path, "utf8") : null,
			};
		});
}

function createLinkFixture(root, worktreeName = "worktree") {
	const worktree = join(root, worktreeName);
	const link = join(worktree, "node_modules");
	const target = join(root, "target");
	mkdirSync(worktree, { recursive: true });
	mkdirSync(join(target, "nested"), { recursive: true });
	writeFileSync(join(target, "a.txt"), "a\n");
	writeFileSync(join(target, "nested", "b.txt"), "b\n");
	createDirectoryLink(target, link);
	return { worktree, link, target };
}

test("NEG-1: a missing node_modules entry is skipped and changes nothing", () => {
	const root = createFixtureRoot();
	try {
		const worktree = join(root, "worktree");
		mkdirSync(worktree);
		writeFileSync(join(worktree, "tracked.txt"), "tracked\n");
		const before = snapshotDirectory(worktree);

		const result = detachNodeModulesLink(worktree);

		assert.equal(result.status, "skipped");
		assert.equal(result.link, join(worktree, "node_modules"));
		assert.deepEqual(snapshotDirectory(worktree), before);
	} finally {
		cleanupFixture(root);
	}
});

test("NEG-2: a plain non-empty node_modules directory is skipped and keeps its content", () => {
	const root = createFixtureRoot();
	try {
		const worktree = join(root, "worktree");
		const existing = join(worktree, "node_modules");
		mkdirSync(existing, { recursive: true });
		writeFileSync(join(existing, "keep.txt"), "keep\n");
		const before = snapshotDirectory(existing);

		const result = detachNodeModulesLink(worktree);

		assert.equal(result.status, "skipped");
		assert.deepEqual(snapshotDirectory(existing), before);
		assert.equal(lstatSync(existing).isDirectory(), true);
	} finally {
		cleanupFixture(root);
	}
});

test("NEG-3: a plain node_modules file is skipped and keeps its content", () => {
	const root = createFixtureRoot();
	try {
		const worktree = join(root, "worktree");
		const existing = join(worktree, "node_modules");
		mkdirSync(worktree);
		writeFileSync(existing, "not a link\n");

		const result = detachNodeModulesLink(worktree);

		assert.equal(result.status, "skipped");
		assert.equal(readFileSync(existing, "utf8"), "not a link\n");
		assert.equal(lstatSync(existing).isFile(), true);
	} finally {
		cleanupFixture(root);
	}
});

test("POS-1: a real directory link is detached without touching its target", () => {
	const root = createFixtureRoot();
	const { worktree, link, target } = createLinkFixture(root);
	const before = snapshotDirectory(target);
	try {
		const result = detachNodeModulesLink(worktree);

		assert.equal(result.status, "detached");
		assert.throws(() => lstatSync(link), { code: "ENOENT" });
		assert.deepEqual(snapshotDirectory(target), before);
		assert.equal(lstatSync(target).isDirectory(), true);
	} finally {
		cleanupFixture(root, [link]);
	}
});

test("ABORT-1: a throwing removal reports failed and preserves both the link and its target", () => {
	const root = createFixtureRoot();
	const { worktree, link, target } = createLinkFixture(root);
	const before = snapshotDirectory(target);
	try {
		const result = detachNodeModulesLink(worktree, {
			removeLink: () => {
				throw new Error("simulated rmdir failure");
			},
		});

		assert.equal(result.status, "failed");
		assert.match(result.reason, /simulated rmdir failure/);
		assert.deepEqual(snapshotDirectory(target), before);
		assert.equal(lstatSync(link).isSymbolicLink(), true);
	} finally {
		cleanupFixture(root, [link]);
	}
});

test("ABORT-2: a removal that leaves the link behind is reported as failed by the self-check", () => {
	const root = createFixtureRoot();
	const { worktree, link, target } = createLinkFixture(root);
	const before = snapshotDirectory(target);
	try {
		const result = detachNodeModulesLink(worktree, { removeLink: () => {} });

		assert.equal(result.status, "failed");
		assert.match(result.reason, /still exists after detaching the link/);
		assert.deepEqual(snapshotDirectory(target), before);
		assert.equal(lstatSync(link).isSymbolicLink(), true);
	} finally {
		cleanupFixture(root, [link]);
	}
});

test(
	"ABORT-3: a real cmd rmdir failure (link path outside cmd quoting) reports failed",
	{ skip: isWindows ? false : "win32-only: exercises the real `cmd /c rmdir` failure path" },
	() => {
		const root = createFixtureRoot();
		const { worktree, target } = createLinkFixture(root);
		// The junction has to be created at a plain path first: `cmd` is only handed the link path at
		// removal time, and an `&` in it makes `cmd` split the command, so `rmdir` fails for real.
		const renamedWorktree = join(root, "worktree&dir");
		renameSync(worktree, renamedWorktree);
		const link = join(renamedWorktree, "node_modules");
		const before = snapshotDirectory(target);
		try {
			const result = detachNodeModulesLink(renamedWorktree);

			assert.equal(result.status, "failed");
			assert.match(result.reason, /Command failed: cmd \/c rmdir/);
			assert.deepEqual(snapshotDirectory(target), before);
			assert.equal(lstatSync(link).isSymbolicLink(), true);
		} finally {
			cleanupFixture(root, [link]);
		}
	},
);
