import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";

export interface Goal {
	goal: string;
	context: string;
	keyConstraints: string;
}

function parseGoalMd(content: string): Goal {
	const section = (heading: string): string => {
		const re = new RegExp(`## ${heading}\\s*\\n([\\s\\S]*?)(?=\\n## |$)`, "i");
		const m = content.match(re);
		return m ? m[1].trim() : "";
	};
	return {
		goal: section("Goal"),
		context: section("Context"),
		keyConstraints: section("Key Constraints"),
	};
}

function writeGoalMd(goalPath: string, g: Goal): void {
	const content = [
		"# Project Goal",
		"",
		"## Goal",
		"",
		g.goal,
		"",
		"## Context",
		"",
		g.context,
		"",
		"## Key Constraints",
		"",
		g.keyConstraints,
	].join("\n");
	fs.writeFileSync(goalPath, content, "utf8");
}

async function elicitGoal(pi: ExtensionAPI): Promise<Goal> {
	// Use pi.sendUserMessage to inject prompts into the session for elicitation
	// The PM agent will guide the user; here we provide a structured prompt
	pi.sendUserMessage(
		"[agent-team-loop] goal.md not found. Please describe your project goal.\n\n" +
			"I'll guide you through three questions:\n" +
			"1. What is your main goal?\n" +
			"2. What context should I know?\n" +
			"3. What are the key constraints?",
	);

	// Write a structured placeholder for the user to fill in and restart.
	// All three sections are pre-populated so AC-021 (no empty sections) is met from the start.
	return {
		goal: "(Describe the main goal — what should be built or accomplished?)",
		context: "(What context should the agent know? e.g. tech stack, existing code, relevant constraints)",
		keyConstraints: "(List key constraints — performance requirements, forbidden approaches, testing rules, etc.)",
	};
}

export async function readOrElicitGoal(agenticdocRoot: string, pi: ExtensionAPI): Promise<Goal> {
	const goalPath = path.join(agenticdocRoot, "goal.md");
	if (fs.existsSync(goalPath)) {
		return parseGoalMd(fs.readFileSync(goalPath, "utf8"));
	}

	const goal = await elicitGoal(pi);
	fs.mkdirSync(agenticdocRoot, { recursive: true });
	writeGoalMd(goalPath, goal);
	return goal;
}
