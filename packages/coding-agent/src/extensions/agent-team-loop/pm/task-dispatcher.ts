import * as fs from "node:fs";
import * as path from "node:path";
import { controlRootFromTaskPath } from "../shared/paths.ts";
import { renderToolchainCommand, resolveWorkspaceConfig, type WorkspaceConfig } from "../shared/target-config.ts";
import type { WorkerEntry, WorkerStore } from "../shared/worker-store.ts";

/** Sentinel opening the injected profile block — makes re-dispatch
 * idempotent (the block is appended at most once per task.md). */
const PROFILE_MARK = "<!-- mw-profile: v1 -->";

/** Does the resolved config carry anything worth injecting? Dual mode
 * alone qualifies: the control-root path is the key fact for a worker whose
 * cwd is the game root (D-005). Sections missing → their block is skipped
 * without blocking the dispatch (AC-007). */
function hasProfileContent(config: WorkspaceConfig): boolean {
	return (
		config.mode === "dual" ||
		Object.keys(config.toolchain).length > 0 ||
		config.ignore.deny_globs.length > 0 ||
		config.contract.forbidden_paths.length > 0 ||
		config.contract.conventions !== null ||
		config.contract.docs.length > 0
	);
}

/** Render the workspace-profile essentials (AC-007: 要点, not the full file).
 * Line prefixes are deliberately not `key:`-shaped so the worker's
 * whole-file frontmatter scan (parseTaskMd) never misreads them.
 * `ignoreEnforced=false` (the task carries its own deny_globs) skips the
 * firewall section — rendering the yml defaults there would claim an
 * enforcement that is not active for this task. */
function renderProfileBlock(config: WorkspaceConfig, ignoreEnforced: boolean): string {
	const lines: string[] = [
		PROFILE_MARK,
		"[mw] Workspace profile (target.yml essentials, injected at dispatch;",
		`full file: ${path.join(config.controlRoot, ".agenticdoc", "target.yml")})`,
	];
	if (config.mode === "dual") {
		lines.push(`Control workspace: ${config.controlRoot}`);
		lines.push(`Game root: ${config.gameRoot}`);
		if (config.engineRoot !== null) lines.push(`Engine root: ${config.engineRoot}`);
	}
	const toolNames = Object.keys(config.toolchain);
	if (toolNames.length > 0) {
		lines.push("Toolchain commands (placeholders resolved):");
		for (const name of toolNames) {
			// Fail-closed render (AC-004): a referenced-but-unconfigured root
			// throws and the dispatch is refused — never a half-resolved command.
			lines.push(`- ${name}: ${renderToolchainCommand(config.toolchain[name], config)}`);
		}
	}
	if (ignoreEnforced && config.ignore.deny_globs.length > 0) {
		lines.push("Context firewall (deny globs, enforced by the read-scope layer):");
		for (const glob of config.ignore.deny_globs) lines.push(`- ${glob}`);
	}
	const contract = config.contract;
	if (contract.forbidden_paths.length > 0 || contract.conventions !== null || contract.docs.length > 0) {
		lines.push("Contract:");
		if (contract.forbidden_paths.length > 0) {
			lines.push(`- forbidden paths: ${contract.forbidden_paths.join(", ")}`);
		}
		if (contract.conventions !== null) {
			lines.push("- conventions:");
			for (const line of contract.conventions.split("\n")) lines.push(`  ${line}`);
		}
		if (contract.docs.length > 0) {
			lines.push("- docs (references, not inlined):");
			for (const doc of contract.docs) lines.push(`  - ${path.resolve(config.controlRoot, doc)}`);
		}
	}
	return lines.join("\n");
}

/** Insert the deny_globs block into a task.md. When the file opens with a
 * `---` frontmatter pair, the block goes before the closing marker (same
 * shape as dispatch.py's renderer); otherwise it is prepended — the worker
 * parser scans the whole file, not just the frontmatter. An existing
 * `deny_globs:` line (task-level override) is never touched. */
function insertDenyGlobs(content: string, denyGlobs: string[]): string {
	const block = ["deny_globs:", ...denyGlobs.map((g) => `  - '${g}'`)].join("\n");
	const lines = content.split("\n");
	if (lines[0]?.trim() === "---") {
		const close = lines.findIndex((line, i) => i > 0 && line.trim() === "---");
		if (close !== -1) {
			lines.splice(close, 0, block);
			return lines.join("\n");
		}
	}
	return `${block}\n${content}`;
}

/** Inject the workspace profile into a task.md at dispatch time (AC-007:
 * the worker reads task.md only — it never needs to know target.yml exists).
 * Throws TargetConfigError on an unusable target.yml (fail-closed: the
 * caller must refuse the dispatch, never queue an un-injected task.md).
 * An unreadable task.md skips injection (warned) — the queue row still
 * lands and the launcher's own task-file validation fails visibly. */
function injectWorkspaceProfile(taskPath: string): void {
	const controlRoot = controlRootFromTaskPath(taskPath);
	const config = resolveWorkspaceConfig(controlRoot);
	let original: string;
	try {
		original = fs.readFileSync(taskPath, "utf8");
	} catch (err) {
		console.error(
			`[mw] profile injection skipped for ${taskPath}: ${err instanceof Error ? err.message : String(err)}`,
		);
		return;
	}
	if (original.includes(PROFILE_MARK)) return; // already injected (re-dispatch)

	let out = original;
	const ownDenyGlobs = /^deny_globs:/m.test(original);
	if (config.ignore.deny_globs.length > 0 && !ownDenyGlobs) {
		out = insertDenyGlobs(out, config.ignore.deny_globs);
	}
	if (hasProfileContent(config)) {
		out = `${out.replace(/\s+$/, "\n")}\n${renderProfileBlock(config, !ownDenyGlobs)}\n`;
	}
	if (out !== original) fs.writeFileSync(taskPath, out, "utf8");
}

export async function dispatchTask(
	entry: Omit<WorkerEntry, "dispatchedAt" | "updatedAt">,
	store: WorkerStore,
): Promise<void> {
	injectWorkspaceProfile(entry.taskPath);
	const now = new Date().toISOString();
	const full: WorkerEntry = {
		...entry,
		dispatchedAt: now,
		updatedAt: now,
	};
	await store.upsert(full);
}
