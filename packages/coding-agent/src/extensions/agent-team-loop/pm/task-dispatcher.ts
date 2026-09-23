import * as fs from "node:fs";
import * as path from "node:path";
import { RAG_MARKER_V1, type RagTaskMeta, renderRagBlock } from "../rag/block.ts";
import { loadRagConfig } from "../rag/config.ts";
import { controlRootFromTaskPath } from "../shared/paths.ts";
import { renderToolchainCommand, resolveWorkspaceConfig, type WorkspaceConfig } from "../shared/target-config.ts";
import type { WorkerEntry, WorkerStore } from "../shared/worker-store.ts";

/** Sentinel opening the legacy (dual/single) profile block — makes
 * re-dispatch idempotent (the block is appended at most once per task.md).
 * Dual/single keep this marker and its rendered text byte-identical
 * (mw-target-partition AC-016d: the golden d baseline was recorded against
 * the v1 marker; the v2 marker is partition-only). */
const PROFILE_MARK = "<!-- mw-profile: v1 -->";
/** v2 marker (mw-target-partition D-005): a partition block carries an
 * explicit mode line right under the marker — the anchor both the
 * launcher's tear check (AC-020) and the switch-replacement boundary
 * (AC-019) read. */
const PROFILE_MARK_V2 = "<!-- mw-profile: v2 -->";

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

/** Locate the (single) profile block in a task.md: the index of the
 * earliest marker of either version — the replacement boundary (AC-019:
 * marker line to end of file, so a corrupt double block also clears
 * wholesale). */
function findProfileBlock(content: string): number | null {
	const v1 = content.indexOf(PROFILE_MARK);
	const v2 = content.indexOf(PROFILE_MARK_V2);
	if (v1 === -1 && v2 === -1) return null;
	if (v2 === -1) return v1;
	if (v1 === -1) return v2;
	return Math.min(v1, v2);
}

/** Drop the `<!-- mw-rag: v1 -->` block (marker line to EOF) from a task.md,
 * collapsing the tail whitespace to a single newline. The RAG block is always
 * the last block, so this re-anchors the profile boundary cleanly. */
function stripRagBlock(content: string): string {
	const index = content.indexOf(RAG_MARKER_V1);
	if (index === -1) return content;
	return content.slice(0, index).replace(/\s+$/, "\n");
}

/** Positive-integer task.md header (`<header>      12`). */
function headerInt(content: string, header: string): number | undefined {
	const match = new RegExp(`^${header}[ \\t]*(\\d+)[ \\t]*$`, "m").exec(content);
	if (match === null) return undefined;
	const value = Number(match[1]);
	return Number.isFinite(value) && value > 0 ? value : undefined;
}

/** Task metadata `renderRagBlock` needs, read from the task.md frontmatter. */
function parseRagTaskMeta(content: string): RagTaskMeta {
	return {
		type: /^type:[ \t]*(.+?)[ \t]*$/m.exec(content)?.[1],
		phase: /^phase:[ \t]*(.+?)[ \t]*$/m.exec(content)?.[1],
		chatBudget: headerInt(content, "rag_chat_budget:"),
		timeBudgetS: headerInt(content, "rag_time_budget_s:"),
	};
}

/** AC-019/FIX-2 freshness predicate: an existing block is fresh exactly
 * when it is byte-identical to what the current config renders — the
 * render is a pure function of the config, so a same-config re-dispatch is
 * byte-stable (AC-007 idempotency) while ANY config change under the same
 * mode (parent/partition/roots paths, toolchain, firewall, contract)
 * produces a different block and the stale one is replaced wholesale
 * (marker line to EOF). The firewall arm is rendered both ways because
 * that section depends on whether the task file already carries a
 * deny_globs line: a first dispatch inserts the line AND renders the
 * section, so both renders must count as fresh for the re-dispatch to
 * stay byte-identical. A config with nothing to inject (parked single)
 * renders no block at all — any existing block is stale and gets dropped. */
function blockIsFresh(existingText: string, config: WorkspaceConfig): boolean {
	if (config.mode === "partition") {
		return (
			existingText === `${renderPartitionProfileBlock(config, true)}\n` ||
			existingText === `${renderPartitionProfileBlock(config, false)}\n`
		);
	}
	if (!hasProfileContent(config)) return false;
	return (
		existingText === `${renderProfileBlock(config, true)}\n` ||
		existingText === `${renderProfileBlock(config, false)}\n`
	);
}

/** Render the partition workspace profile (mw-target-partition D-005,
 * AC-007): v2 marker + explicit mode line, then the same essentials shape
 * as the dual block — parent/partition/named roots replace the game/engine
 * lines (partition has neither). The toolchain/firewall/contract sections
 * are intentionally duplicated from renderProfileBlock rather than shared:
 * the dual render is frozen byte-exact by the AC-016d golden. The full-file
 * line always names target.yml (the single config file). */
function renderPartitionProfileBlock(config: WorkspaceConfig, ignoreEnforced: boolean): string {
	const lines: string[] = [
		PROFILE_MARK_V2,
		`[mw] mode: ${config.mode}`,
		"[mw] Workspace profile (target.yml essentials, injected at dispatch;",
		`full file: ${path.join(config.controlRoot, ".agenticdoc", "target.yml")})`,
		`Control workspace: ${config.controlRoot}`,
		`Parent root (extended workspace, writable): ${config.parentRoot}`,
		`Partition root (worker cwd): ${config.partitionRoot}`,
	];
	const roots = config.roots ?? {};
	if (Object.keys(roots).length > 0) {
		lines.push("Named roots:");
		for (const [name, root] of Object.entries(roots)) lines.push(`- ${name}: ${root}`);
	}
	const toolNames = Object.keys(config.toolchain);
	if (toolNames.length > 0) {
		lines.push("Toolchain commands (placeholders resolved):");
		for (const name of toolNames) {
			// Fail-closed render (AC-004): an undefined placeholder throws and
			// the dispatch is refused — never a half-resolved command.
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
 * lands and the launcher's own task-file validation fails visibly.
 *
 * Marker semantics (mw-target-partition D-005): dual/single render the v1
 * marker exactly as before; partition renders the v2 marker + mode line.
 * Re-dispatch is idempotent while the existing block is byte-identical to
 * what the current config renders (FIX-2: staleness is content-based, not
 * mode-only — any same-mode config change replaces the block too); when
 * the block no longer matches, it is replaced wholesale from its marker
 * line to EOF (AC-019) — including a v1-marked legacy block under partition
 * activation, and a drop to nothing under a non-injecting mode (parked
 * single restores the pre-injection bytes). */
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
	// The RAG block is the last block (marker line to EOF), so strip it before
	// the profile replacement boundary (also marker -> EOF) is computed, then
	// re-append the freshly rendered block at the very end. This keeps both
	// blocks idempotent under re-dispatch and drops a stale RAG block when the
	// project no longer enables RAG (D-009).
	const base = stripRagBlock(original);
	const existing = findProfileBlock(base);
	const ownDenyGlobs = /^deny_globs:/m.test(base);
	let out = base;
	const profileFresh = existing !== null && blockIsFresh(base.slice(existing).replace(/\s+$/, "\n"), config);
	if (!profileFresh) {
		// Stale block: drop everything from its marker line (AC-019 wholesale
		// replacement — a mode switch, any same-mode config change, or a switch
		// to a non-injecting mode (parked single) that restores the pre-injection
		// bytes); fresh dispatch: anchor at the original content. The tail
		// collapses to a single newline so the replacement re-anchors cleanly.
		out = existing !== null ? base.slice(0, existing).replace(/\s+$/, "\n") : base;
		if (config.ignore.deny_globs.length > 0 && !ownDenyGlobs) {
			out = insertDenyGlobs(out, config.ignore.deny_globs);
		}
		if (config.mode === "partition") {
			// Partition always injects: the parent/partition roots are the key
			// facts for a worker whose cwd is the partition root (D-005).
			out = `${out.replace(/\s+$/, "\n")}\n${renderPartitionProfileBlock(config, !ownDenyGlobs)}\n`;
		} else if (hasProfileContent(config)) {
			out = `${out.replace(/\s+$/, "\n")}\n${renderProfileBlock(config, !ownDenyGlobs)}\n`;
		}
	}
	// Zero-impact when disabled: renderRagBlock returns null and writes not one
	// byte (D-014/AC-001).
	const ragBlock = renderRagBlock(loadRagConfig(controlRoot), parseRagTaskMeta(base));
	if (ragBlock !== null) out = `${out.replace(/\s+$/, "")}\n\n${ragBlock}\n`;
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
