import * as fs from "node:fs";
import { goalPath } from "../shared/paths.ts";

export type GoalStatus = "draft" | "active" | "unknown";

export interface Goal {
	status: GoalStatus;
	goal: string;
	context: string;
	keyConstraints: string;
}

function parseStatus(content: string): GoalStatus {
	// Matches `status: draft` optionally prefixed by a blockquote marker (`> `).
	const m = content.match(/^\s*>?\s*status:\s*(\w+)/im);
	if (!m) return "unknown";
	const v = m[1].toLowerCase();
	if (v === "draft") return "draft";
	if (v === "active") return "active";
	return "unknown";
}

export function parseGoalMd(content: string): Goal {
	const section = (heading: string): string => {
		const re = new RegExp(`## ${heading}\\s*\\n([\\s\\S]*?)(?=\\n## |$)`, "i");
		const m = content.match(re);
		return m ? m[1].trim() : "";
	};
	// A section that still holds only its scaffold comment counts as empty.
	const clean = (s: string): string => s.replace(/<!--[\s\S]*?-->/g, "").trim();
	return {
		status: parseStatus(content),
		goal: clean(section("Goal")),
		context: clean(section("Context")),
		keyConstraints: clean(section("Key Constraints")),
	};
}

/** Read goal.md if present; returns null when the file does not exist. Read-only. */
export function readGoal(agenticdocRoot: string): Goal | null {
	const resolved = goalPath(agenticdocRoot);
	if (!fs.existsSync(resolved)) return null;
	try {
		return parseGoalMd(fs.readFileSync(resolved, "utf8"));
	} catch {
		return null;
	}
}

/**
 * Whether the project goal is established (usable as the north-star anchor).
 * - status: active            → established
 * - status: draft / missing   → NOT established (needs /goal brainstorm)
 * - no status line (legacy)   → established iff any section has real content,
 *                               so pre-existing goal.md files are not blocked.
 */
export function isGoalEstablished(goal: Goal | null): boolean {
	if (!goal) return false;
	if (goal.status === "active") return true;
	if (goal.status === "draft") return false;
	return Boolean(goal.goal || goal.context || goal.keyConstraints);
}
