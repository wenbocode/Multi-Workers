import * as fs from "node:fs";
import * as path from "node:path";
import { Type } from "typebox";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { keyNameRefusal } from "../shared/index-store.ts";
import { readRunProgress } from "../shared/run-progress.ts";
import { type RunState, readRunState } from "../shared/run-store.ts";
import { approveWorkerDeadline, readWorkerDeadline } from "../shared/worker-deadline.ts";

export function workerDeadlineStatus(root: string, dir: string, run: RunState, now = Date.now(), home?: string) {
	const view = readWorkerDeadline(root, dir, run, now, home);
	if (!view) return;
	return {
		deadline: view.deadline,
		stop: view.stop,
		...("history" in view && view.history
			? {
					version: view.version,
					reviewAt: view.reviewAt,
					availableExtensionMs: view.availableExtensionMs,
					availableApprovals: view.availableApprovals,
					budget: view.budget,
				}
			: {}),
	};
}

/** Claim a review reminder once per run and deadline revision across PM restarts. */
export function takeDeadlineReview(root: string, dir: string, claim: string, now = Date.now(), home?: string) {
	const run = readRunState(dir);
	if (!run || run.status !== "running" || run.live_deadline?.claim !== claim) return;
	const view = readWorkerDeadline(root, dir, run, now, home);
	if (!view || !("history" in view) || !view.history || view.stop || now < view.reviewAt) return;
	try {
		fs.writeFileSync(`${view.files.journal}.review-${view.version}`, run.run_id, { flag: "wx", mode: 0o600 });
	} catch {
		return;
	}
	const progress = readRunProgress(dir, run.run_id, now);
	return {
		runId: run.run_id,
		progress,
		eta: "milestone" in progress ? (progress.milestone?.eta ?? "unknown") : "unknown",
		version: view.version,
		deadline: view.deadline,
		availableExtensionMs: view.availableExtensionMs,
		availableApprovals: view.availableApprovals,
		budget: view.budget,
	};
}

export function registerWorkerDeadlineApproval(pi: ExtensionAPI, root: string, claim: () => string, home?: string) {
	pi.registerTool({
		name: "extend_worker_deadline",
		label: "Approve worker deadline extension",
		description:
			"Approve bounded extra time for a running worker with fresh verifiable progress and remaining authorization. Read worker progress for the current deadline version.",
		parameters: Type.Object({
			key: Type.String(),
			task_key: Type.String(),
			run_id: Type.String(),
			request_id: Type.String({ minLength: 1, maxLength: 120 }),
			version: Type.Integer({ minimum: 0 }),
			deadline_ms: Type.Integer({ description: "Requested absolute deadline in Unix milliseconds" }),
			review_at_ms: Type.Integer({ description: "Next PM review in Unix milliseconds" }),
			reason: Type.String({ minLength: 1, maxLength: 2000 }),
			next: Type.String({ minLength: 1, maxLength: 2000 }),
		}),
		async execute(_id, params, signal) {
			if (keyNameRefusal(params.key) || keyNameRefusal(params.task_key)) throw new Error("Invalid worker identity");
			const dir = path.join(root, params.key, "workers", params.task_key);
			const receipt = await approveWorkerDeadline(
				root,
				dir,
				claim(),
				params.run_id,
				{
					requestId: params.request_id,
					version: params.version,
					deadline: params.deadline_ms,
					reviewAt: params.review_at_ms,
					reason: params.reason,
					next: params.next,
				},
				{ signal, home },
			);
			return { content: [{ type: "text", text: JSON.stringify(receipt) }], details: receipt };
		},
	});
}
