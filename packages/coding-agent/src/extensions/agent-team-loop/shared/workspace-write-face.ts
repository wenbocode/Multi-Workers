import { normalizeForCompare } from "../worker/read-scope.ts";
import { engineBuildArtifactRoots } from "./engine-policy.ts";
import { resolveWorkspaceConfig, type WorkspaceConfig } from "./target-config.ts";
import type { WriteFaceParseOptions } from "./write-face.ts";

/** Declarations remain control-relative; separated roots use absolute identities
 * so dispatch and worker cwd cannot give the same entry different meanings. */
export function workspaceWriteFaceOptions(
	controlRoot: string,
	config: WorkspaceConfig = resolveWorkspaceConfig(controlRoot),
): WriteFaceParseOptions {
	const options = { base: config.controlRoot, caseInsensitive: process.platform === "win32" };
	if (config.mode === "single") return options;
	const roots =
		config.mode === "dual"
			? [config.controlRoot, config.gameRoot, config.engineRoot]
			: [config.controlRoot, config.partitionRoot, config.parentRoot, ...Object.values(config.roots ?? {})];
	const readOnly =
		config.mode === "dual" && config.engineRoot !== null && config.engineWritable !== true
			? { readOnlyRoots: [config.engineRoot], readOnlyAllowedRoots: engineBuildArtifactRoots(config.engineRoot) }
			: { readOnlyRoots: [], readOnlyAllowedRoots: [] };
	return {
		...options,
		...readOnly,
		roots: [...new Set(roots.filter((root): root is string => root !== null))],
		// design.md §4: the three build-generated UBT directories travel as
		// literal anchors derived from the canonical Engine root; every other
		// mode leaves the exception empty (no widening outside dual + false).
		canonicalize: (absolutePath) => normalizeForCompare(config.controlRoot, absolutePath),
	};
}
