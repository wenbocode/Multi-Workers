import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { isSameOrUnder, normalizeForCompare } from "../worker/read-scope.ts";
import { extractBashWriteCandidates, tokenizeShellCommand } from "../worker/worker-mode.ts";
import { dualEnginePolicyLines, engineBuildArtifactRoots } from "./engine-policy.ts";
import { resolveWorkspaceConfig, type WorkspaceConfig } from "./target-config.ts";

/** Engine-root containment WITHOUT the build-artifact exception. The artifact
 * anchors are literal concatenations of the canonical Engine root (never
 * realpath-migrated), so a junctioned artifact directory cannot move the
 * exception to another tree (design D-003). */
function engineRootIdentity(config: WorkspaceConfig): string | null {
	return config.engineRoot === null ? null : normalizeForCompare(config.controlRoot, config.engineRoot);
}

function isUnderEngineRoot(config: WorkspaceConfig, cwd: string, target: string): boolean {
	const root = engineRootIdentity(config);
	return root !== null && isSameOrUnder(root, normalizeForCompare(cwd, target));
}

/** Is the already-normalized target inside one of the three frozen UBT build
 * directories? */
export function isEngineBuildArtifactTarget(engineRoot: string, resolvedTarget: string): boolean {
	return engineBuildArtifactRoots(engineRoot).some((root) => isSameOrUnder(root, resolvedTarget));
}

export function engineWriteBlockReason(config: WorkspaceConfig, cwd: string, target: string): string | undefined {
	if (config.mode !== "dual" || config.engineRoot === null || config.engineWritable === true) return undefined;
	const resolved = normalizeForCompare(cwd, target);
	const root = engineRootIdentity(config);
	if (root === null || !isSameOrUnder(root, resolved)) return undefined;
	// design.md §4: the build-generated UBT directories are the ONLY Engine
	// write exception, and they never create one on their own — the role/task
	// write face still decides (worker runtime). A declared name is not a write
	// exemption, so everything else keeps the read-only verdict.
	if (isEngineBuildArtifactTarget(config.engineRoot, resolved)) return undefined;
	return `engine-read-only: ${target}; Engine writes require engine_writable: true in target.yml. Keep extensions in Game and reference original Engine code; never copy it to another tree.`;
}

/** Covers explicit copy commands; arbitrary programs still require OS isolation. */
export function engineCopyBlockReason(config: WorkspaceConfig, cwd: string, command: string): string | undefined {
	if (config.mode !== "dual" || config.engineRoot === null || config.engineWritable === true) return undefined;
	const tokens = tokenizeShellCommand(command);
	const copyCommands = new Set(["cp", "copy", "xcopy", "robocopy", "rsync", "copy-item"]);
	let copying = false;
	let commandPosition = true;
	for (const token of tokens) {
		if (token.operator) {
			copying = false;
			commandPosition = [";", "|", "||", "&&", "&"].includes(token.text);
			continue;
		}
		if (commandPosition) {
			copying = copyCommands.has(
				path
					.basename(token.text.replaceAll("\\", "/"))
					.toLowerCase()
					.replace(/\.exe$/, ""),
			);
			commandPosition = false;
			continue;
		}
		const extension = path.extname(token.text).toLowerCase();
		const source = token.verbatim ? token.text : /[$`~]/.test(token.text) ? undefined : token.text.split(/[*?[{]/)[0];
		if (
			copying &&
			source &&
			(extension === "" ||
				[".h", ".hpp", ".hh", ".cpp", ".c", ".cc", ".cxx", ".inl", ".ipp", ".cs", ".ixx", ".ush", ".usf"].includes(
					extension,
				)) &&
			// Copying generated artifacts does not need an exemption, so this rule
			// stays strict (whole Engine root): the artifact exception can never be
			// used to move generated code either.
			isUnderEngineRoot(config, cwd, source)
		) {
			return "engine-copy-forbidden: reference original Engine code from a Game wrapper; do not copy Engine source to modify it.";
		}
	}
	return undefined;
}

/** Applies to PM and workers; current policy is re-read before every write. */
export function registerWorkspaceEngineGuard(pi: ExtensionAPI, controlRoot: string): void {
	pi.on("before_agent_start", (event) => {
		const lines = dualEnginePolicyLines(resolveWorkspaceConfig(controlRoot));
		return lines.length === 0
			? undefined
			: { systemPrompt: `${event.systemPrompt}\n\n[mw dual policy]\n${lines.join("\n")}` };
	});
	pi.on("tool_call", (event, ctx) => {
		const input = event.input as Record<string, unknown>;
		const detached = event.toolName === "mw_run_detached";
		if (!["write", "edit", "bash"].includes(event.toolName) && !detached) return undefined;
		let config: WorkspaceConfig;
		try {
			config = resolveWorkspaceConfig(controlRoot);
		} catch (error) {
			return { block: true, reason: `target-config-unusable: ${String(error)}` };
		}
		if (config.mode !== "dual" || config.engineWritable === true) return undefined;
		const cwd = detached
			? typeof input.cwd === "string"
				? path.resolve(ctx.cwd, input.cwd)
				: config.controlRoot
			: ctx.cwd;
		const targets: string[] = [];
		let command: string | undefined;
		if (detached) {
			targets.push(
				typeof input.run_dir === "string" ? path.resolve(ctx.cwd, input.run_dir) : path.join(cwd, ".mw", "runs"),
			);
			if (Array.isArray(input.cmd)) {
				const argv = input.cmd as unknown[];
				if (argv.every((item): item is string => typeof item === "string")) {
					command = argv.map((item) => `'${item.replaceAll("'", "'\\''")}'`).join(" ");
				}
			}
		} else if (event.toolName === "bash") {
			if (typeof input.command === "string") command = input.command;
		} else if (typeof input.path === "string") targets.push(input.path);
		if (command !== undefined) {
			const copyReason = engineCopyBlockReason(config, cwd, command);
			if (copyReason) return { block: true, reason: copyReason };
			for (const candidate of extractBashWriteCandidates(command)) {
				if (candidate.verbatim) targets.push(candidate.target);
			}
		}
		for (const target of targets) {
			const reason = engineWriteBlockReason(config, cwd, target);
			if (reason) return { block: true, reason };
		}
		return undefined;
	});
}
