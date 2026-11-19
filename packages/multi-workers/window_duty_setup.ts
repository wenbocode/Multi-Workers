import { existsSync, lstatSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { FileSettingsStorage } from "../coding-agent/src/core/settings-manager.ts";

/** Only add explicit paths to the selected project's config. pi discovers these on reload. */
export function receiverSettings(project: string) {
	const directory = join(project, ".pi");
	const file = join(directory, "settings.json");
	const here = dirname(fileURLToPath(import.meta.url));
	const receiver = resolve(here, "../../.pi/extensions/mw-pm-channel.ts");
	const duty = join(here, "window_duty_extension.ts");
	const checkPaths = () => {
		for (const path of [directory, file]) {
			if (lstatSync(path, { throwIfNoEntry: false })?.isSymbolicLink())
				throw Error(`Cannot automatically update linked project settings: ${path}`);
		}
	};
	function merge(current: string | undefined) {
		const settings = current === undefined ? {} : JSON.parse(current);
		if (!settings || typeof settings !== "object" || Array.isArray(settings))
			throw Error(`Invalid pi settings: ${file}`);
		const extensions: unknown = settings.extensions === undefined ? [] : settings.extensions;
		if (!Array.isArray(extensions) || !extensions.every((entry: unknown) => typeof entry === "string"))
			throw Error(`Invalid extensions list: ${file}`);
		const missing = [receiver, duty].filter((path) => {
			if (!existsSync(path)) throw Error(`MW extension missing: ${path}`);
			if (!relative(path, resolve(directory, "extensions", "mw-pm-channel.ts"))) return false;
			return !extensions.some((entry: string) => !relative(path, resolve(directory, entry)));
		});
		if (!missing.length) return undefined;
		return JSON.stringify({ ...settings, extensions: [...extensions, ...missing] }, null, 2) + "\n";
	}
	checkPaths();
	return {
		file,
		needsUpdate: merge(existsSync(file) ? readFileSync(file, "utf8") : undefined) !== undefined,
		install() {
			checkPaths();
			new FileSettingsStorage(project, directory).withLock("project", merge);
		},
	};
}
