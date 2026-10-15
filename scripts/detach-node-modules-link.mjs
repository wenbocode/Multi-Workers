import { execFileSync } from "node:child_process";
import { lstatSync, unlinkSync } from "node:fs";
import { join } from "node:path";

// Removes only the link entry. On Windows `rmdir` without /S deletes the reparse point and never the
// directory it points at; elsewhere unlinkSync drops the symlink without touching its target.
function removeNodeModulesLink(link) {
	if (process.platform === "win32") {
		// No /S and no trailing separator: this removes only the reparse point, never the target.
		execFileSync("cmd", ["/c", "rmdir", link], { stdio: "inherit" });
	} else {
		unlinkSync(link);
	}
}

// Detaches <worktreePath>/node_modules without following the link. `git worktree remove --force`
// follows reparse points and would recursively delete the link target (the real node_modules tree),
// so the link must be gone before the worktree is removed.
//
// Returns {status, link, reason}:
// - "skipped": no entry, or the entry is not a link/reparse point; nothing was changed;
// - "detached": the link is gone (verified with lstat);
// - "failed": removal threw or the link still exists afterwards. The caller decides whether to keep
//   the worktree site, the exit code, and the manual-detach hint.
//
// `options.removeLink` is a test seam that replaces the platform removal call; production callers omit it.
export function detachNodeModulesLink(worktreePath, options = {}) {
	const removeLink = options.removeLink ?? removeNodeModulesLink;
	const link = join(worktreePath, "node_modules");
	let stats;
	try {
		stats = lstatSync(link);
	} catch (error) {
		// lstat (not existsSync) so a dangling link is still recognized as a link.
		if (error instanceof Error && error.code === "ENOENT") {
			return { status: "skipped", link, reason: "link not present" };
		}
		return { status: "failed", link, reason: error instanceof Error ? error.message : String(error) };
	}
	if (!stats.isSymbolicLink()) return { status: "skipped", link, reason: "not a link" };

	try {
		removeLink(link);
	} catch (error) {
		return { status: "failed", link, reason: error instanceof Error ? error.message : String(error) };
	}

	try {
		lstatSync(link);
	} catch (error) {
		if (error instanceof Error && error.code === "ENOENT") {
			return { status: "detached", link, reason: "link removed" };
		}
		return { status: "failed", link, reason: error instanceof Error ? error.message : String(error) };
	}
	return { status: "failed", link, reason: `${link} still exists after detaching the link` };
}
