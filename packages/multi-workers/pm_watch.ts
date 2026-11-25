/** Read-only event stream consumed by the active Codex desktop chat. */
import { existsSync, readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { dirname, join, resolve } from "node:path";
import { setTimeout } from "node:timers/promises";
import { parseArgs } from "node:util";
import { PmChannel } from "../coding-agent/src/extensions/agent-team-loop/pm/codex-channel.ts";
import { normalizeKey } from "../coding-agent/src/extensions/agent-team-loop/shared/index-store.ts";
import { type WorkerEntry, WorkerStore, workerOwnerKey } from "../coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts";

type State = "working" | "waiting-for-worker" | "worker-lost" | "idle" | "offline" | "binding-changed" | "finished" | "unobservable";

function hasExited(worker: WorkerEntry, project: string, key: string): boolean {
	const runFile = join(dirname(resolve(project, worker.taskPath)), "run.json");
	if (!existsSync(runFile)) return false;
	const run = JSON.parse(readFileSync(runFile, "utf8"));
	const heartbeat = Date.parse(run.last_heartbeat_at);
	if (run.task_key !== worker.taskKey || run.owner_key !== key || run.status !== "running" ||
		!Number.isSafeInteger(run.pid) || run.pid <= 0 || !Number.isFinite(heartbeat) ||
		Date.now() - heartbeat < 90_000) return false;
	const dispatched = Date.parse(worker.dispatchedAt);
	const started = Date.parse(run.started_at);
	if (!Number.isFinite(dispatched) || !Number.isFinite(started) || started < dispatched) return false;
	try {
		process.kill(run.pid, 0);
		return false;
	} catch (error) {
		return (error as NodeJS.ErrnoException).code === "ESRCH";
	}
}

export class StopWatch {
	readonly channel: PmChannel;
	readonly workers: WorkerStore;
	readonly target: { project: string; key: string; claim: string; binding: string };
	private last?: State;
	private since = 0;
	private reported = false;
	private readonly requirePm: boolean;

	constructor(project: string, key: string, claim: string, binding: string, home?: string, options?: { requirePm?: boolean }) {
		this.target = { project: resolve(project), key, claim, binding };
		this.channel = new PmChannel(project, home);
		this.workers = new WorkerStore(join(project, ".agenticdoc"));
		this.requirePm = options?.requirePm ?? true;
	}

	/** `requirePm=false` (single-window observation): the worker queue is the primary
	 *  source, so a dead worker is reported as `worker-lost` even when no PM heartbeat
	 *  is live. A missing/stale heartbeat is a `PM offline` detail, never `offline`.
	 *  Bounded to the queue file and the targeted workers' run.json, same as the
	 *  default path; `hasExited()` keeps its 90s + pid ESRCH criterion (GC-3). */
	private sampleFileFirst(status: ReturnType<PmChannel["status"]>): { state: State; detail?: string } {
		const { key } = this.target;
		if (!existsSync(this.workers.queuePath)) return { state: "unobservable", detail: "Worker queue missing" };
		const queue = this.workers.readQueue();
		if (queue.version > 2 || queue.unparsable.length) return { state: "unobservable", detail: "Unreadable worker queue" };
		let pending = false;
		const exited: string[] = [];
		for (const worker of queue.rows) {
			if (normalizeKey(workerOwnerKey(worker)) !== normalizeKey(key)) continue;
			if (worker.status === "running" && hasExited(worker, this.target.project, key)) exited.push(worker.taskKey);
			else if (worker.status === "pending" || worker.status === "running") pending = true;
			else if (!["done", "failed", "needs-clarification", "lost", "cancelled"].includes(worker.status))
				return { state: "unobservable", detail: "Unknown worker state" };
		}
		const state: State = pending ? "waiting-for-worker" : exited.length ? "worker-lost" : "idle";
		const detail = exited.length ? exited.join(", ") : undefined;
		if (status.connected && status.activity !== "idle") {
			if (status.activity === "working" && state === "idle") return { state: "working" };
			if (status.activity !== "working") return { state: "unobservable", detail: "Unknown PM activity" };
		}
		if (status.connected) return detail === undefined ? { state } : { state, detail };
		return { state, detail: detail === undefined ? "PM offline" : `${detail}, PM offline` };
	}

	sample(): { state: State; detail?: string } {
		try {
			const { key, claim, binding } = this.target;
			const status = this.channel.status(key);
			if (status.phase === "DONE") return { state: "finished" };
			if (!this.requirePm) return this.sampleFileFirst(status);
			if (status.status !== "active" || status.claim !== claim) return { state: "binding-changed" };
			if (!status.connected) return { state: "offline" };
			if (status.binding !== binding) return { state: "binding-changed" };
			if (status.activity === "working") return { state: "working" };
			if (status.activity !== "idle") return { state: "unobservable", detail: "Unknown PM activity" };
			if (!existsSync(this.workers.queuePath)) return { state: "unobservable", detail: "Worker queue missing" };
			const queue = this.workers.readQueue();
			if (queue.version > 2 || queue.unparsable.length) return { state: "unobservable", detail: "Unreadable worker queue" };
			let pending = false;
			const exited: string[] = [];
			for (const worker of queue.rows) {
				if (normalizeKey(workerOwnerKey(worker)) !== normalizeKey(key)) continue;
				if (worker.status === "running" && hasExited(worker, this.target.project, key)) exited.push(worker.taskKey);
				else if (worker.status === "pending" || worker.status === "running") pending = true;
				else if (!["done", "failed", "needs-clarification", "lost", "cancelled"].includes(worker.status))
					return { state: "unobservable", detail: "Unknown worker state" };
			}
			if (pending) return { state: "waiting-for-worker" };
			if (exited.length) return { state: "worker-lost", detail: exited.join(", ") };
			return { state: "idle" };
		} catch (error) {
			return { state: "unobservable", detail: String(error) };
		}
	}

	observe(now: number) {
		const sample = this.sample();
		if (this.last !== sample.state) {
			this.last = sample.state;
			this.since = now;
			this.reported = false;
		}
		if (this.reported || sample.state === "working" || sample.state === "waiting-for-worker") return;
		if (now - this.since < 45_000 && sample.state !== "finished" && sample.state !== "binding-changed") return;
		this.reported = true;
		return { ...this.target, ...sample, at: new Date().toISOString() };
	}
}

if (import.meta.main) {
	try {
		const { values, positionals } = parseArgs({ allowPositionals: true, options: { status: { type: "boolean" } } });
		if (!positionals.length || positionals.length % 4 !== 0)
			throw new Error("Usage: node pm_watch.ts [--status] PROJECT KEY CLAIM BINDING [PROJECT KEY CLAIM BINDING ...]");
		const watches: StopWatch[] = [];
		for (let i = 0; i < positionals.length; i += 4) {
			const [project, key, claim, binding] = positionals.slice(i, i + 4);
			watches.push(new StopWatch(project, key, claim, binding));
		}
		console.log(JSON.stringify({ targets: watches.map(w => ({ ...w.target, ...w.sample() })) }));
		if (!values.status) {
			for (;;) {
				for (const watch of watches) {
					const event = watch.observe(performance.now());
					if (event) console.log(JSON.stringify(event));
				}
				await setTimeout(5000);
			}
		}
	} catch (error) {
		console.error(String(error));
		process.exitCode = 1;
	}
}
