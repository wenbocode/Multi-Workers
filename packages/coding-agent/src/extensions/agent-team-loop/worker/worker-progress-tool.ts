import { Type } from "typebox";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { milestoneEvidence, recordRunProgress } from "../shared/run-progress.ts";

export const WORKER_PROGRESS_TOOL = "report_worker_progress";

export function registerWorkerProgressTool(pi: ExtensionAPI, taskDir: string, runId: string): void {
	pi.registerTool({
		name: WORKER_PROGRESS_TOOL,
		label: "Report worker progress",
		description:
			"Record this run's latest milestone or blocker for the PM. Completed items require existing evidence files.",
		promptGuidelines: [
			"Report progress before a long tool call and when a milestone, blocker, or ETA changes. Include all completed items still supported by evidence.",
		],
		parameters: Type.Object(
			{
				completed: Type.Array(
					Type.Object({
						acceptance: Type.String({ minLength: 1, maxLength: 200 }),
						evidence: Type.String({ minLength: 1, maxLength: 500 }),
					}),
					{ maxItems: 20 },
				),
				current: Type.String({ maxLength: 1000 }),
				remaining: Type.String({ maxLength: 1000 }),
				blocker: Type.String({ maxLength: 1000 }),
				next: Type.String({ maxLength: 1000 }),
				eta: Type.Optional(Type.String({ maxLength: 100 })),
			},
			{ additionalProperties: false },
		),
		async execute(_id, { completed, current, remaining, blocker, next, eta }) {
			const milestone = {
				completed: completed.map(({ acceptance, evidence }) => ({
					acceptance,
					evidence: milestoneEvidence(taskDir, evidence),
				})),
				current,
				remaining,
				blocker,
				next,
				eta,
				at: new Date().toISOString(),
			};
			if (!recordRunProgress(taskDir, runId, { milestone })) {
				throw new Error("Worker progress can only be reported for the current running run");
			}
			return { content: [{ type: "text", text: "Worker progress recorded." }], details: {} };
		},
	});
}
