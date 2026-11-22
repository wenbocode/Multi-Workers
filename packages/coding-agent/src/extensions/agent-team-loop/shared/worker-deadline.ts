import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { PmChannel } from "../pm/codex-channel.ts";
import { sha256EolNormalizedBytes } from "./card-digest.ts";
import { acquireLock } from "./file-lock.ts";
import { IndexStore, keyNameRefusal } from "./index-store.ts";
import { milestoneEvidence, PROGRESS_STALE_MS, readRunProgress } from "./run-progress.ts";
import { type RunState, readRunState } from "./run-store.ts";
import { readTaskHeaderScalar } from "./task-frontmatter.ts";

export interface DeadlineUsage {
	steps: number;
	cost: number;
	noProgress: number;
	evidenceVersions?: string[];
}

export interface WorkerDeadlineBinding {
	claim: string;
	policy: string;
	initial: number;
	ceiling: number;
	started: number;
	fixedSteps?: number;
	usage: DeadlineUsage;
}

interface Policy {
	card_sha256: string;
	expires_at: number;
	review_after_ms: number;
	max_run_ms: number;
	max_extension_ms: number;
	max_total_extension_ms: number;
	max_approvals: number;
	max_steps: number;
	max_cost: number;
	no_progress_limit: number;
	cancelled?: boolean;
}

export interface DeadlineApproval {
	requestId: string;
	version: number;
	deadline: number;
	reviewAt: number;
	reason: string;
	next: string;
}

interface Receipt extends DeadlineApproval {
	workspace: string;
	key: string;
	task: string;
	runId: string;
	claim: string;
	policy: string;
	at: number;
	evidence: string;
}

export type DeadlineStop = "worker-deadline" | "user-stop" | "parent-cancel" | "authority-revoked" | "budget-exhausted";

function digest(value: string | Buffer): string {
	return createHash("sha256").update(value).digest("hex");
}

function positive(value: number): boolean {
	return Number.isSafeInteger(value) && value > 0;
}

function readBytes(file: string, limit = 1024 * 1024): Buffer | undefined {
	const stat = fs.lstatSync(file, { throwIfNoEntry: false });
	if (!stat?.isFile() || stat.size > limit || fs.realpathSync(file) !== path.resolve(file)) return;
	return fs.readFileSync(file);
}

/** Private PM channel storage is outside the worker workspace. Policy is operator provisioned. */
export function workerDeadlineFiles(root: string, key: string, task: string, runId: string, home?: string) {
	if (keyNameRefusal(key) || keyNameRefusal(task)) throw new Error("Invalid worker deadline identity");
	const channel = new PmChannel(path.dirname(root), home);
	const dir = path.join(channel.dir, "worker-deadlines", key);
	return {
		workspace: path.basename(channel.dir),
		policy: path.join(dir, `${task}.json`),
		journal: path.join(dir, `${task}-${digest(runId)}.json`),
	};
}

function currentClaim(root: string, key: string): string | undefined {
	const rows = new IndexStore(root).readAuthorityRows().filter((row) => row.key.toLowerCase() === key.toLowerCase());
	const row = rows.length === 1 ? rows[0] : undefined;
	return row?.key === key &&
		row.status === "active" &&
		row.phase === "EXECUTE" &&
		row.claimId &&
		row.claimId !== "—" &&
		row.claimId !== "-"
		? row.claimId
		: undefined;
}

function readPolicy(file: string): { hash: string; policy: Policy } | undefined {
	const bytes = readBytes(file, 16 * 1024);
	if (!bytes) return;
	const policy: Policy = JSON.parse(bytes.toString("utf8"));
	if (
		!policy ||
		!/^[a-f0-9]{64}$/.test(policy.card_sha256) ||
		![
			policy.expires_at,
			policy.review_after_ms,
			policy.max_run_ms,
			policy.max_extension_ms,
			policy.max_total_extension_ms,
			policy.max_approvals,
			policy.max_steps,
			policy.max_cost,
			policy.no_progress_limit,
		].every(positive)
	)
		return;
	return { hash: digest(bytes), policy };
}

function cardMatches(root: string, dir: string, run: RunState, pin: string): boolean {
	if (path.resolve(dir) !== path.join(path.resolve(root), run.owner_key, "workers", run.task_key)) return false;
	const envelope = readBytes(path.join(dir, "task.md"))?.toString("utf8") ?? "";
	const card = readTaskHeaderScalar(envelope, "card_path");
	if (!card || !/^tasks\/[\w-][\w.-]*\.md$/.test(card) || readTaskHeaderScalar(envelope, "card_sha256") !== pin)
		return false;
	const bytes = readBytes(path.join(root, run.owner_key, card));
	return !!bytes && sha256EolNormalizedBytes(bytes) === pin;
}

export function startWorkerDeadline(
	root: string,
	dir: string,
	run: RunState,
	started: number,
	deadline: number,
	ceilingLimit: number,
	fixedSteps?: number,
	home?: string,
): WorkerDeadlineBinding | undefined {
	try {
		const files = workerDeadlineFiles(root, run.owner_key, run.task_key, run.run_id, home);
		const record = readPolicy(files.policy);
		if (!record) return;
		const claim = currentClaim(root, run.owner_key);
		if (!claim || !cardMatches(root, dir, run, record.policy.card_sha256)) return;
		const ceiling = Math.min(started + record.policy.max_run_ms, record.policy.expires_at, ceilingLimit);
		return {
			claim,
			policy: record.hash,
			started,
			ceiling,
			fixedSteps,
			initial: Math.min(deadline, ceiling),
			usage: { steps: 0, cost: 0, noProgress: 0 },
		};
	} catch {
		return undefined;
	}
}

function parentStop(root: string, run: RunState): DeadlineStop | undefined {
	const seen = new Set([run.task_key]);
	for (let ref = run.parent_worker_run; ref; ) {
		const task = ref.split("@", 1)[0] ?? "";
		if (keyNameRefusal(task) || seen.has(task)) return "authority-revoked";
		seen.add(task);
		const dir = path.join(root, run.owner_key, "workers", task);
		const parent = readRunState(dir);
		if (!parent || parent.run_id !== ref || parent.task_key !== task || parent.owner_key !== run.owner_key) {
			return "authority-revoked";
		}
		if (parent.aborted || ["canceled", "stopped", "failed-by-stop"].includes(parent.status)) return "parent-cancel";
		if (parent.stop_kind === "authority-revoked") return "authority-revoked";
		const envelope = readBytes(path.join(dir, "task.md"))?.toString("utf8") ?? "";
		ref = parent.parent_worker_run ?? readTaskHeaderScalar(envelope, "parent_worker_run");
	}
}

export function deadlineEvidence(dir: string, runId: string, now: number) {
	const progress = readRunProgress(dir, runId, now);
	const milestone = "milestone" in progress && progress.status === "current" ? progress.milestone : undefined;
	if (
		!milestone ||
		typeof milestone.remaining !== "string" ||
		typeof milestone.next !== "string" ||
		!milestone.remaining.trim() ||
		!milestone.next.trim() ||
		!milestone.completed.length
	)
		return;
	try {
		const project = path.dirname(path.dirname(path.dirname(path.dirname(dir))));
		const items = milestone.completed.map(({ acceptance, evidence }) => {
			const ref = milestoneEvidence(dir, evidence);
			const bytes = readBytes(path.join(project, ref));
			if (!acceptance.trim() || !bytes?.length) throw new Error("Unverifiable progress evidence");
			return JSON.stringify([acceptance.trim(), digest(bytes)]);
		});
		return { version: digest(JSON.stringify([...new Set(items)].sort())), reportedAt: Date.parse(milestone.at) };
	} catch {
		return undefined;
	}
}

function receipts(
	file: string,
	workspace: string,
	run: RunState,
	binding: WorkerDeadlineBinding,
	policy: Policy,
): Receipt[] | undefined {
	if (!fs.existsSync(file)) return [];
	const bytes = readBytes(file);
	if (!bytes) return;
	const records: Receipt[] = JSON.parse(bytes.toString("utf8"));
	if (!Array.isArray(records) || records.length > policy.max_approvals) return;
	let previous = binding.initial;
	let priorAt = binding.started;
	const ids = new Set<string>();
	const evidence = new Set<string>();
	for (let index = 0; index < records.length; index++) {
		const r = records[index];
		if (
			!r ||
			r.version !== index ||
			r.workspace !== workspace ||
			r.key !== run.owner_key ||
			r.task !== run.task_key ||
			r.runId !== run.run_id ||
			r.claim !== binding.claim ||
			r.policy !== binding.policy ||
			typeof r.requestId !== "string" ||
			!r.requestId ||
			ids.has(r.requestId) ||
			typeof r.evidence !== "string" ||
			!/^[a-f0-9]{64}$/.test(r.evidence) ||
			evidence.has(r.evidence) ||
			!positive(r.at) ||
			r.at < priorAt ||
			r.at >= previous ||
			!positive(r.deadline) ||
			r.deadline <= previous ||
			r.deadline > binding.ceiling ||
			r.deadline - previous > policy.max_extension_ms ||
			r.deadline - binding.initial > policy.max_total_extension_ms ||
			!positive(r.reviewAt) ||
			r.reviewAt <= r.at ||
			r.reviewAt >= r.deadline ||
			typeof r.reason !== "string" ||
			!r.reason.trim() ||
			typeof r.next !== "string" ||
			!r.next.trim()
		)
			return;
		ids.add(r.requestId);
		evidence.add(r.evidence);
		previous = r.deadline;
		priorAt = r.at;
	}
	return records;
}

/** Every reader evaluates the same persisted deadline version and stop facts. */
export function readWorkerDeadline(root: string, dir: string, run: RunState, now = Date.now(), home?: string) {
	const binding = run.live_deadline;
	if (!binding) return;
	const fallback = { deadline: binding.initial, stop: "authority-revoked" as DeadlineStop };
	try {
		const files = workerDeadlineFiles(root, run.owner_key, run.task_key, run.run_id, home);
		const record = readPolicy(files.policy);
		if (run.aborted || record?.policy.cancelled === true) return { ...fallback, stop: "user-stop" as const };
		const parent = parentStop(root, run);
		if (parent) return { ...fallback, stop: parent };
		if (
			!record ||
			record.hash !== binding.policy ||
			currentClaim(root, run.owner_key) !== binding.claim ||
			!cardMatches(root, dir, run, record.policy.card_sha256)
		)
			return fallback;
		const { policy } = record;
		const usage = binding.usage;
		if (
			!positive(binding.started) ||
			!positive(binding.initial) ||
			!positive(binding.ceiling) ||
			binding.initial > binding.ceiling ||
			binding.ceiling > Math.min(binding.started + policy.max_run_ms, policy.expires_at) ||
			![usage.steps, usage.cost, usage.noProgress].every((count) => Number.isSafeInteger(count) && count >= 0)
		)
			return fallback;
		const history = receipts(files.journal, files.workspace, run, binding, policy);
		if (!history) return fallback;
		const last = history.at(-1);
		if (last && last.at > now) return fallback;
		const deadline = last?.deadline ?? binding.initial;
		const budget = {
			steps: Math.min(policy.max_steps, binding.fixedSteps ?? Infinity) - usage.steps,
			cost: Math.min(policy.max_cost, binding.fixedSteps ?? Infinity) - usage.cost,
			noProgress: policy.no_progress_limit - usage.noProgress,
		};
		const stop: DeadlineStop | undefined =
			now >= deadline
				? "worker-deadline"
				: Object.values(budget).some((left) => !Number.isSafeInteger(left) || left <= 0)
					? "budget-exhausted"
					: undefined;
		return {
			deadline,
			stop,
			budget,
			history,
			files,
			policy,
			version: history.length,
			reviewAt: last?.reviewAt ?? binding.started + policy.review_after_ms,
			availableExtensionMs: Math.max(
				0,
				Math.min(
					policy.max_extension_ms,
					binding.ceiling - deadline,
					policy.max_total_extension_ms - (deadline - binding.initial),
				),
			),
			availableApprovals: policy.max_approvals - history.length,
		};
	} catch {
		return fallback;
	}
}

export async function approveWorkerDeadline(
	root: string,
	dir: string,
	claim: string,
	runId: string,
	request: DeadlineApproval,
	options: { home?: string; now?: () => number; signal?: AbortSignal } = {},
): Promise<Receipt> {
	const run = readRunState(dir);
	if (run?.run_id !== runId || !run.live_deadline || run.live_deadline.claim !== claim)
		throw new Error("unbound PM approval");
	const { journal, workspace } = workerDeadlineFiles(root, run.owner_key, run.task_key, runId, options.home);
	const release = await acquireLock(`${journal}.lock`, { retries: 4, baseDelayMs: 25 });
	const now = options.now ?? Date.now;
	const tmp = `${journal}.${randomUUID()}.tmp`;
	try {
		function current() {
			const at = now();
			const fresh = readRunState(dir);
			if (
				fresh?.run_id !== runId ||
				fresh.status !== "running" ||
				fresh.live_deadline?.claim !== claim ||
				fresh.live_deadline.policy !== run?.live_deadline?.policy
			)
				throw new Error("run no longer eligible");
			const view = readWorkerDeadline(root, dir, fresh, at, options.home);
			if (options.signal?.aborted) throw new Error("user-stop");
			if (view?.stop) throw new Error(view.stop);
			if (!view || !("history" in view) || !view.history) throw new Error("deadline authority unavailable");
			return { at, fresh, view, history: view.history };
		}
		const { at, fresh, view, history } = current();
		const replay = history.find((r) => r.requestId === request.requestId);
		if (replay) {
			if ((Object.keys(request) as (keyof DeadlineApproval)[]).some((name) => replay[name] !== request[name])) {
				throw new Error("approval request changed");
			}
			return replay;
		}
		if (
			view.version !== request.version ||
			!/^[\w.-]{1,120}$/.test(request.requestId) ||
			!request.reason.trim() ||
			!request.next.trim() ||
			!positive(request.deadline) ||
			!positive(request.reviewAt) ||
			request.reviewAt <= at ||
			request.reviewAt >= request.deadline
		)
			throw new Error("invalid or stale approval request");
		if (
			!view.availableApprovals ||
			request.deadline <= view.deadline ||
			request.deadline - view.deadline > view.availableExtensionMs
		)
			throw new Error("extension allowance exceeded");
		const progress = deadlineEvidence(dir, runId, at);
		if (
			!progress ||
			progress.reportedAt < run.live_deadline.started ||
			history.some((r) => r.evidence === progress.version)
		)
			throw new Error("fresh business progress required");
		const receipt: Receipt = {
			...request,
			workspace,
			key: fresh.owner_key,
			task: fresh.task_key,
			at,
			runId,
			claim,
			policy: fresh.live_deadline!.policy,
			evidence: progress.version,
		};
		const fd = fs.openSync(tmp, "wx", 0o600);
		try {
			fs.writeFileSync(fd, JSON.stringify([...history, receipt]));
			fs.fsyncSync(fd);
		} finally {
			fs.closeSync(fd);
		}
		if (deadlineEvidence(dir, runId, now())?.version !== receipt.evidence) {
			throw new Error("progress evidence changed before commit");
		}
		const boundary = current();
		if (
			boundary.view.version !== request.version ||
			boundary.at >= request.reviewAt ||
			boundary.at - progress.reportedAt >= PROGRESS_STALE_MS ||
			now() >= boundary.view.deadline ||
			options.signal?.aborted
		)
			throw new Error("approval expired before commit");
		fs.renameSync(tmp, journal);
		return receipt;
	} finally {
		try {
			if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
		} finally {
			release();
		}
	}
}
