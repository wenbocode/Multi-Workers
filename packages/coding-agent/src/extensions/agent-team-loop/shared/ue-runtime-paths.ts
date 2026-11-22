import * as fs from "node:fs";
import * as path from "node:path";

function epicProgramData(): string | undefined {
	const data = process.env.ProgramData;
	return data && path.isAbsolute(data) ? path.join(data, "Epic").replaceAll("\\", "/") : undefined;
}

export function isUnattendedBugReportOptOut(absolute: string): boolean {
	const epic = epicProgramData();
	return (
		epic !== undefined &&
		absolute.replaceAll("\\", "/").toLowerCase() === `${epic}/NotAllowedUnattendedBugReports`.toLowerCase()
	);
}

/** Mirror autopilot/ue_runtime_paths.py. The parser passes a canonical path. */
export function ueExternalWriteRoot(absolute: string): string | undefined {
	const localRoots = [process.env.LOCALAPPDATA];
	if (process.env.USERPROFILE) localRoots.push(path.join(process.env.USERPROFILE, "AppData", "Local"));
	for (const local of localRoots) {
		if (!local || !path.isAbsolute(local)) continue;
		const localDir = path.normalize(local).replaceAll("\\", "/").replace(/\/$/, "");
		const ubt = `${localDir}/UnrealBuildTool`.toLowerCase();
		const lower = absolute.toLowerCase();
		if (lower === ubt || lower.startsWith(`${ubt}/`)) return localDir;
		const ue = path.join(local, "UnrealEngine").replaceAll("\\", "/");
		const prefix = `${ue}/`;
		if (!absolute.toLowerCase().startsWith(prefix.toLowerCase())) continue;
		const [version, folder] = absolute.slice(prefix.length).split("/");
		if (
			folder !== undefined &&
			((/^[0-9]+\.[0-9]+$/.test(version) && /^Saved(?:_[A-Za-z0-9_-]+)?$/i.test(folder)) ||
				(version.toLowerCase() === "common" && folder.toLowerCase() === "deriveddatacache"))
		)
			return ue;
	}
	if (isUnattendedBugReportOptOut(absolute)) {
		try {
			const info = fs.lstatSync(absolute);
			if (info.isFile() && info.size === 0) return epicProgramData();
		} catch {
			return undefined;
		}
	}
	return undefined;
}

/** A project descriptor anchors generated folders under Engine/Plugins or Source/Programs. */
export function isEngineProjectOutput(engine: string, absolute: string): boolean {
	const root = path.join(engine, "Engine");
	const relative = path.relative(root, absolute);
	const parts = relative.split(path.sep);
	if (path.isAbsolute(relative) || parts.includes("..")) return false;
	const names = parts.map((part) => part.toLowerCase());
	for (let index = 2; index < parts.length; index += 1) {
		let extension: string;
		if (names[0] === "plugins" && ["binaries", "intermediate", "saved"].includes(names[index])) {
			extension = ".uplugin";
		} else if (
			index >= 3 &&
			names[0] === "source" &&
			names[1] === "programs" &&
			["obj", "bin", "uatobj", "uatbin"].includes(names[index])
		) {
			extension = ".csproj";
		} else continue;
		const parents = parts.slice(0, index);
		if (!parents.every((name) => /^[A-Za-z0-9_. -]+$/.test(name))) return false;
		try {
			const entries = fs.readdirSync(path.join(root, ...parents), { withFileTypes: true });
			if (entries.some((entry) => entry.isFile() && path.extname(entry.name).toLowerCase() === extension))
				return true;
		} catch {
			// A project directory can disappear while a task is being prepared.
		}
	}
	return false;
}
