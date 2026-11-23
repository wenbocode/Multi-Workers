import * as fs from "node:fs";
import * as path from "node:path";
import { keyNameRefusal } from "./index-store.ts";

const KEY_GOAL_HEADING = "## [mw] Current key goal";

function readKeyDoc(docRoot: string, key: string, file: string): string {
	try {
		const expected = path.join(fs.realpathSync(docRoot), key, file);
		const resolved = fs.realpathSync(expected);
		if (path.relative(expected, resolved) !== "" || !fs.statSync(resolved).isFile()) return "";
		return fs
			.readFileSync(resolved, "utf8")
			.replace(/\r\n?/g, "\n")
			.replace(/<!--[\s\S]*?(?:-->|$)/g, "");
	} catch {
		return "";
	}
}

function sectionBody(text: string, level: number, title: RegExp): string {
	const lines = text.split("\n");
	let start = -1;
	let fence = "";
	for (const [index, line] of lines.entries()) {
		const marker = /^ {0,3}(`{3,}|~{3,})/.exec(line)?.[1];
		if (fence) {
			if (marker?.[0] === fence[0] && marker.length >= fence.length && line.trim() === marker) fence = "";
			continue;
		}
		if (marker) {
			fence = marker;
			continue;
		}
		const heading = /^ {0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$/.exec(line);
		if (!heading) continue;
		const headingLevel = heading[1].length;
		if (start !== -1 && headingLevel <= level) return lines.slice(start, index).join("\n").trim();
		if (start === -1 && headingLevel === level && title.test(heading[2])) start = index + 1;
	}
	return start === -1 ? "" : lines.slice(start).join("\n").trim();
}

export function appendKeyGoal(systemPrompt: string, docRoot: string, key: string | undefined): string {
	if (!key || keyNameRefusal(key) || systemPrompt.includes(KEY_GOAL_HEADING)) return systemPrompt;
	const lite = readKeyDoc(docRoot, key, "codex_doc.md");
	const liteHeader = lite.split(/^##[ \t]+/m, 1)[0];
	const goal = /^- Workflow:[ \t]*codex-lite[ \t]*$/m.test(liteHeader)
		? sectionBody(lite, 2, /^目标$/)
		: sectionBody(
				sectionBody(readKeyDoc(docRoot, key, "spec.md"), 2, /^(?:§0(?:\s|$)|Goal Alignment$)/i),
				3,
				/^spec_goal$/,
			);
	if (!goal) return systemPrompt;
	const block = `${KEY_GOAL_HEADING} (${key})\n\n${goal}`;
	return systemPrompt ? `${systemPrompt}\n\n${block}` : block;
}
