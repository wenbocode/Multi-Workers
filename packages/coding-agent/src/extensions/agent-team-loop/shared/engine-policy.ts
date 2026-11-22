import * as path from "node:path";
import type { WorkspaceConfig } from "./target-config.ts";

/** Generated outputs relative to a canonical Engine repository root.
 * The anchors are literal concatenations — the helper never realpaths them, so
 * a junctioned artifact directory cannot migrate the exception to another
 * tree (design D-003). Mirrored by `mw_common.engine_build_artifact_roots`. */
export function engineBuildArtifactRoots(engineRoot: string): string[] {
	return [
		path.join(engineRoot, "Engine", "Intermediate"),
		path.join(engineRoot, "Engine", "Saved"),
		path.join(engineRoot, "Engine", "DerivedDataCache"),
		path.join(engineRoot, "Engine", "Programs", "UnrealBuildTool"),
		...["Win64", "Linux", "LinuxArm64", "Mac", "DotNET"].map((platform) =>
			path.join(engineRoot, "Engine", "Binaries", platform),
		),
	];
}

/** The three policy lines the dual `engine_writable: false` profile carries
 * before the Engine extension policy block. Frozen text: the Python mirror
 * (`mw_common.dual_engine_policy_lines`) must render byte-identical lines. */
const UBT_BUILD_POLICY_LINES = [
	"UBT builds: allowed without enabling Engine source writes. Declare generated output directories under Engine/Intermediate, Engine/Saved, Engine/DerivedDataCache or Engine/Binaries/{Win64,Linux,LinuxArm64,Mac,DotNET} (subject to task write_face/write_scope).",
	"Engine build outputs also include Programs/UnrealBuildTool logs, installed plugin Binaries/Intermediate/Saved directories and .NET program bin/obj/uatbin/uatobj directories.",
	"Engine feature development stays in Game. Preserve Engine source, build scripts, input configuration, bundled third-party binaries and InstalledBuild.txt.",
	"Static command guards are not an OS sandbox. Keep detached run_dir outside Engine unless it is an explicitly permitted build-artifact path; report any other required Engine write.",
];

/** Mirrored by mw_common.dual_engine_policy_lines; parity is regression tested. */
export function dualEnginePolicyLines(config: WorkspaceConfig): string[] {
	if (config.mode !== "dual") return [];
	const lines = [
		"Game writes: enabled (subject to task write_face/write_scope).",
		`Engine source writes: ${config.engineWritable === true ? "enabled" : "read-only"} (engine_writable: ${config.engineWritable === true}).`,
		"PM: Engine write permission never overrides project/task constraints. Never change engine_writable to unblock your own task.",
	];
	if (config.engineRoot !== null) {
		lines.push(
			"Windows UE runtime: declare the concrete local UnrealEngine version's Saved or Saved_<suffix> directory, Common/DerivedDataCache, local UnrealBuildTool logs, and the existing empty ProgramData/Epic/NotAllowedUnattendedBugReports marker as needed. The Editor manages the marker.",
		);
	}
	if (config.engineWritable === true) {
		lines.push(
			"PM: Plan direct Engine changes only within the approved scope, declare precise write_face/write_scope, and validate the affected target.",
		);
	} else {
		lines.push(
			...UBT_BUILD_POLICY_LINES,
			"Engine extension policy (mandatory):",
			"- Keep extensions in Game. Wrap each upstream implementation in a project-owned code file that references the original Engine code (include/public API); maintain only the added or changed behavior.",
			"- Never copy or fork Engine source into Game, another Engine tree, or any other directory to modify it. Renaming copied files or copying only part of an implementation is also forbidden.",
			"- Prefer public APIs, inheritance, delegates and composition. An implementation wrapper must reference the original file, isolate macros/symbols, and compile without duplicate definitions; do not assume a private cpp can safely be included.",
			"- Before acceptance, review the diff for copied Engine implementation, identify each wrapper and its upstream reference, and compile the affected target. If no safe extension point exists, report the limitation; do not copy code or change engine_writable to bypass it.",
		);
	}
	return lines;
}
