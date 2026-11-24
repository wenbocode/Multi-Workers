import * as fs from "node:fs";
import * as path from "node:path";
import { keyNameRefusal } from "./index-store.ts";

const KEY_GOAL_HEADING = "## [mw] Current key goal";
const GOAL_ALIGNMENT = /^(?:§0(?:\s|$)|Goal Alignment$)/i;
const SPEC_GOAL = /^spec_goal$/;

function readKeyDoc(docRoot: string, key: string, file: string): string {
	try {
		const expected = path.join(fs.realpathSync(docRoot), key, file);
		const resolved = fs.realpathSync(expected);
		if (path.relative(expected, resolved) !== "" || !fs.statSync(resolved).isFile()) return "";
		return fs
			.readFileSync(resolved, "utf8")
			.replace(/^\uFEFF/, "")
			.replace(/\r\n?/g, "\n")
			.replace(/<!--[\s\S]*?(?:-->|$)/g, "");
	} catch {
		return "";
	}
}

function sectionRange(lines: readonly string[], level: number, title: RegExp): [number, number] | undefined {
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
		if (start !== -1 && headingLevel <= level) return [start, index];
		if (start === -1 && headingLevel === level && title.test(heading[2])) start = index + 1;
	}
	return start === -1 ? undefined : [start, lines.length];
}

function sectionBody(text: string, level: number, title: RegExp): string {
	const lines = text.split("\n");
	const range = sectionRange(lines, level, title);
	return range
		? lines
				.slice(...range)
				.join("\n")
				.trim()
		: "";
}

function specGoal(text: string): string {
	return sectionBody(sectionBody(text, 2, GOAL_ALIGNMENT), 3, SPEC_GOAL);
}

/** Add a confirmed goal while retaining the existing spec's bytes and line endings. */
export function insertKeySpecGoal(spec: string, goal: string): string | undefined {
	const lines = spec.split("\n");
	const visible = spec
		.replace(/^\uFEFF/, "")
		.replace(/<!--[\s\S]*?(?:-->|$)/g, (comment) => comment.replace(/[^\n]/g, " "))
		.split("\n");
	const alignment = sectionRange(visible, 2, GOAL_ALIGNMENT);
	const existing = alignment && sectionRange(visible.slice(...alignment), 3, SPEC_GOAL);
	if (
		alignment &&
		existing &&
		visible
			.slice(alignment[0] + existing[0], alignment[0] + existing[1])
			.join("")
			.trim()
	)
		return undefined;

	const eol = spec.includes("\r\n") ? "\r\n" : "\n";
	const heading = alignment ? "" : `## §0 Goal Alignment${eol}${eol}`;
	const subheading = existing ? "" : `### spec_goal${eol}${eol}`;
	let position = 0;
	if (alignment) {
		position = existing ? alignment[0] + existing[0] : alignment[1];
	} else {
		const firstSection = sectionRange(visible, 2, /./);
		position = firstSection ? firstSection[0] - 1 : lines.length;
	}
	const before = lines.slice(0, position).join("\n");
	const after = lines.slice(position).join("\n");
	const bom = position === 0 && spec.startsWith("\uFEFF") ? "\uFEFF" : "";
	const separator = !position ? bom : before.endsWith("\n") ? eol : `${before.endsWith("\r") ? "\n" : eol}${eol}`;
	const updated = `${before}${separator}${heading}${subheading}${goal.replace(/\r?\n/g, eol)}${eol}${eol}${after.slice(bom.length)}`;
	if (
		specGoal(
			updated
				.replace(/^\uFEFF/, "")
				.replace(/\r\n?/g, "\n")
				.replace(/<!--[\s\S]*?(?:-->|$)/g, ""),
		) !== goal.replace(/\r\n?/g, "\n")
	)
		throw new Error("无法在 spec.md 中找到可读取的 spec_goal 位置，请检查 Markdown 结构。");
	return updated;
}

export function appendKeyGoal(systemPrompt: string, docRoot: string, key: string | undefined): string {
	if (!key || keyNameRefusal(key) || systemPrompt.includes(KEY_GOAL_HEADING)) return systemPrompt;
	const lite = readKeyDoc(docRoot, key, "codex_doc.md");
	const liteHeader = lite.split(/^##[ \t]+/m, 1)[0];
	const goal = /^- Workflow:[ \t]*codex-lite[ \t]*$/m.test(liteHeader)
		? sectionBody(lite, 2, /^目标$/)
		: specGoal(readKeyDoc(docRoot, key, "spec.md"));
	if (!goal) return systemPrompt;
	const block = `${KEY_GOAL_HEADING} (${key})\n\n${goal}`;
	return systemPrompt ? `${systemPrompt}\n\n${block}` : block;
}
