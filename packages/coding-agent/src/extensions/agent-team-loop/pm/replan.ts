import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { Type } from "typebox";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.ts";

export function requestReplan(project: string, args: Record<string, unknown>): Record<string, unknown> {
	const mw = findMwPy();
	if (!mw) return { ok: false, reason: "MW Python installation is unavailable" };
	const child = spawnSync(PYTHON_EXE, ["-B", "-X", "utf8", path.join(path.dirname(mw), "replan_tasks.py")], {
		input: JSON.stringify({ ...args, project }),
		encoding: "utf8",
		windowsHide: true,
		timeout: 30000,
		maxBuffer: 8 * 1024 * 1024,
	});
	if (child.status !== 0) return { ok: false, reason: child.error?.message ?? child.stderr.trim() };
	try {
		const answer: unknown = JSON.parse(child.stdout);
		if (typeof answer === "object" && answer !== null && "ok" in answer) return { ...answer };
	} catch {
		// Incomplete responses must not admit a managed successor.
	}
	return { ok: false, reason: "invalid replan response" };
}

export function replanAdmission(
	project: string,
	key: string,
	task: string,
	card: string,
	hash: string,
	hasFailure: boolean,
	supersedes?: string,
) {
	if (!hasFailure && !fs.existsSync(path.join(project, ".agenticdoc", key, "evidence", "replan"))) return;
	const result = requestReplan(project, { operation: "admission", key, task, card, card_hash: hash, supersedes });
	return result.ok === true ? undefined : String(result.reason ?? "replan admission unavailable");
}

const unit = Type.Object({
	id: Type.String({ description: "Fresh task card stem under this key" }),
	markdown: Type.String({
		description: "Complete original dispatch card with type and positive timeout headers and role-specific sections",
	}),
	depends_on: Type.Array(Type.String()),
	resources: Type.Optional(
		Type.Array(Type.String(), {
			description: "Exclusive resources; [] explicitly declares none; omitted is unknown",
		}),
	),
	covers: Type.Array(Type.String({ description: "Required AC, FLOW or VC ID carried by this unit" })),
	reuse: Type.String(),
	first_check: Type.String(),
	expected: Type.String(),
});

export function registerReplanTool(pi: ExtensionAPI, project: string, claim: () => string) {
	pi.registerTool({
		name: "replan_tasks",
		label: "Replan remaining tasks",
		description:
			"Inspect an owned key or run, preview the remaining acceptance and safe parallel batch, then apply the frozen plan. For split/narrow/direct-exec/escalate include preview.basis_id in the applicable prepared basis for ask_decision(dp-pm-steer); apply its matching decision_id. For an unstarted card omit DP task_key; otherwise use facts.task. For direct-exec/escalate first perform the action and pass its executed decision_receipt event_id as action_evidence. Apply records the actual publication and settlement. Schedule reorders existing independent work.",
		parameters: Type.Object({
			operation: Type.Union([Type.Literal("inspect"), Type.Literal("preview"), Type.Literal("apply")]),
			key: Type.String(),
			task: Type.Optional(
				Type.String({ description: "Queue task key or original card stem; omit for key inventory" }),
			),
			issue: Type.Optional(Type.String()),
			snapshot: Type.Optional(Type.String()),
			version: Type.Optional(Type.String()),
			decision_id: Type.Optional(Type.String()),
			action_evidence: Type.Optional(Type.String()),
			plan: Type.Optional(
				Type.Object({
					action: Type.Union([
						Type.Literal("split"),
						Type.Literal("narrow"),
						Type.Literal("direct-exec"),
						Type.Literal("escalate"),
						Type.Literal("schedule"),
					]),
					reason: Type.String(),
					retained: Type.Optional(
						Type.Record(
							Type.String(),
							Type.String({
								description: "Existing tasks/<card>.md owning the ID, or evidence/<file>.md recording its PASS",
							}),
						),
					),
					ready_existing: Type.Optional(Type.Array(Type.String())),
					units: Type.Array(unit),
				}),
			),
		}),
		executionMode: "sequential",
		async execute(_id, params) {
			const result = requestReplan(project, { ...params, claim: claim() });
			return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
		},
	});
}
