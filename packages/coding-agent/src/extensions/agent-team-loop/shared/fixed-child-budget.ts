import * as fs from "node:fs";
import * as path from "node:path";
import { cardDigest } from "./card-digest.ts";
import { readRunState } from "./run-store.ts";
import { readTaskHeaderScalar } from "./task-frontmatter.ts";

export const FIXED_PARENT_FIELD = /^\s*-\s*.*`parent_matter_ref`\s*[:：]/m;

export function allocationFile(taskDir: string): string {
	const keyDir = path.dirname(path.dirname(taskDir));
	return path.join(
		path.dirname(keyDir),
		"_runtime",
		"fixed-child-budgets",
		path.basename(keyDir),
		`${path.basename(taskDir)}.json`,
	);
}

export function deadlineAllocationFile(taskDir: string, pin: string): string {
	return path.join(path.dirname(allocationFile(taskDir)), `deadline-${pin}.json`);
}

/** Read the PM allocation once. Missing evidence for a declared child leaves zero allowance. */
export function openFixedAllocation(
	taskDir: string,
	envelope: string,
): { steps: number; deadline: number; alreadyStarted?: true } | undefined {
	const card = readTaskHeaderScalar(envelope, "card_path");
	const pin = readTaskHeaderScalar(envelope, "card_sha256");
	const successor = readTaskHeaderScalar(envelope, "deadline_successor") === "yes";
	const blocked = { steps: 0, deadline: 0 };
	if (successor && !/^[0-9a-f]{64}$/.test(pin ?? "")) return blocked;
	const file = successor && pin ? deadlineAllocationFile(taskDir, pin) : allocationFile(taskDir);
	const keyDir = path.dirname(path.dirname(taskDir));
	const cardPath =
		card && /^tasks\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_.-]+\.md$/.test(card) ? path.join(keyDir, card) : undefined;
	try {
		if (fs.existsSync(`${file}.started`)) return { ...blocked, alreadyStarted: true };
		if (successor && fs.existsSync(`${file}.cancelled`)) return blocked;
		if (cardPath && pin && cardDigest(cardPath) !== pin) return blocked;
		const declared =
			cardPath && fs.existsSync(cardPath) && FIXED_PARENT_FIELD.test(fs.readFileSync(cardPath, "utf8"));
		if (
			!declared &&
			!successor &&
			!fs.existsSync(file) &&
			readTaskHeaderScalar(envelope, "fixed_child_steps") === undefined &&
			readTaskHeaderScalar(envelope, "fixed_child_deadline") === undefined
		)
			return undefined;
		if (!declared || !cardPath) return blocked;
		const grant = JSON.parse(fs.readFileSync(file, "utf8"));
		if (
			fs.realpathSync(file) !== path.resolve(file) ||
			String(grant.steps) !== readTaskHeaderScalar(envelope, "fixed_child_steps") ||
			grant.deadline !== readTaskHeaderScalar(envelope, "fixed_child_deadline") ||
			grant.task !== path.basename(taskDir) ||
			grant.card !== card ||
			grant.pin !== cardDigest(cardPath) ||
			grant.pin !== readTaskHeaderScalar(envelope, "card_sha256") ||
			(successor &&
				(typeof grant.approval?.parent !== "string" ||
					grant.approval.parent !== readTaskHeaderScalar(envelope, "parent_worker_run") ||
					Date.parse(grant.deadline) <= Date.now())) ||
			!Number.isSafeInteger(grant.steps) ||
			grant.steps <= 0 ||
			!Number.isFinite(Date.parse(grant.deadline))
		)
			return blocked;
		if (successor) {
			const parent = readTaskHeaderScalar(envelope, "parent_worker_run");
			const parentTask = parent?.split("@", 1)[0] ?? "";
			if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(parentTask) || parentTask === path.basename(taskDir)) {
				return blocked;
			}
			const run = readRunState(path.join(keyDir, "workers", parentTask));
			if (
				run?.run_id !== parent ||
				run?.task_key !== parentTask ||
				run.owner_key !== path.basename(keyDir) ||
				run.status !== "failed" ||
				run.stop_kind !== "worker-deadline" ||
				run.aborted
			)
				return blocked;
		}
		fs.writeFileSync(`${file}.started`, String(process.pid), { flag: "wx" });
		return { steps: grant.steps, deadline: Date.parse(grant.deadline) };
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code === "EEXIST") return { ...blocked, alreadyStarted: true };
		return blocked;
	}
}
