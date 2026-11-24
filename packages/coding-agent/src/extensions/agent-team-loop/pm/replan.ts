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
	const keyDir = path.join(project, ".agenticdoc", key);
	if (
		!hasFailure &&
		!fs.existsSync(path.join(keyDir, "spec.md")) &&
		!fs.existsSync(path.join(keyDir, "scope-review.json")) &&
		!fs.existsSync(path.join(keyDir, "evidence", "replan"))
	)
		return;
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
			"Replan when remaining work must change, a retry is refused by replan-required, or the user requests replanning. Inspect the specific task; reuse issue/snapshot until source evidence changes. Routine resume and successful completion follow the existing plan. Key inventory defaults to a bounded issues page and counts; request section/offset only as needed. Preview only a proposed plan change, then apply the frozen plan. For split/narrow/direct-exec/escalate include preview.basis_id in the applicable prepared basis for ask_decision(dp-pm-steer); apply its matching decision_id. For an unstarted card omit DP task_key; otherwise use facts.task. For direct-exec/escalate first perform the action and pass its executed decision_receipt event_id as action_evidence. Apply records the actual publication and settlement. Schedule reorders existing independent work. For changed historical deadline evidence, use inspect_deadline_recovery with card and exact parent run, review the observed differences, then authorize_deadline_recovery with the same card, parent, snapshot and recovery_reason. Dispatch still requires a fresh PM stage budget.",
		parameters: Type.Object({
			operation: Type.Union([
				Type.Literal("inspect"),
				Type.Literal("preview"),
				Type.Literal("apply"),
				Type.Literal("inspect_deadline_recovery"),
				Type.Literal("authorize_deadline_recovery"),
			]),
			key: Type.String(),
			task: Type.Optional(
				Type.String({
					description:
						"Queue task key or original card stem; omit for key inventory. Inspect returns status, acceptance, issue/snapshot and project-relative evidence_refs. Use read on those paths only when needed.",
				}),
			),
			section: Type.Optional(
				Type.Union(
					[Type.Literal("issues"), Type.Literal("cards"), Type.Literal("workers"), Type.Literal("applied_plans")],
					{ description: "Key inventory list to page; default issues. Counts cover all lists." },
				),
			),
			offset: Type.Optional(Type.Integer({ minimum: 0, description: "Inspect page offset; default 0" })),
			limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 50, description: "Inspect page size; default 20" })),
			issue: Type.Optional(Type.String()),
			snapshot: Type.Optional(Type.String()),
			card: Type.Optional(Type.String({ description: "Frozen tasks/<card>.md for deadline recovery" })),
			parent: Type.Optional(Type.String({ description: "Exact timed-out worker run ID for deadline recovery" })),
			recovery_reason: Type.Optional(Type.String({ description: "Why the reviewed historical recovery is valid" })),
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
