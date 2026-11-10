import { normalizeForCompare } from "../worker/read-scope.ts";
import { resolveWorkspaceConfig } from "./target-config.ts";
import type { WriteFaceParseOptions } from "./write-face.ts";

/** Declarations remain control-relative; separated roots use absolute identities
 * so dispatch and worker cwd cannot give the same entry different meanings. */
export function workspaceWriteFaceOptions(controlRoot: string): WriteFaceParseOptions {
	const config = resolveWorkspaceConfig(controlRoot);
	const options = { base: config.controlRoot, caseInsensitive: process.platform === "win32" };
	if (config.mode === "single") return options;
	const roots =
		config.mode === "dual"
			? [config.controlRoot, config.gameRoot, config.engineRoot]
			: [config.controlRoot, config.partitionRoot, config.parentRoot, ...Object.values(config.roots ?? {})];
	return {
		...options,
		roots: [...new Set(roots.filter((root): root is string => root !== null))],
		canonicalize: (absolutePath) => normalizeForCompare(config.controlRoot, absolutePath),
	};
}
