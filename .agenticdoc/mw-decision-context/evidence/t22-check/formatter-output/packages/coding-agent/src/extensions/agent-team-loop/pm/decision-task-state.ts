import * as fs from "node:fs";
import * as path from "node:path";
import { Type } from "typebox";
import { type WorkerStore, workerOwnerKey } from "../shared/worker-store.ts";

const STATUSES = [
	"not-queued",
	"pending",
	"running",
	"done",
	"failed",
	"needs-clarification",
	"lost",
	"unknown",
] as const;
const SOURCES = ["worker-registry", "dispatch-result", "agent-report"] as const;
export interface TaskStateSnapshot {
	status: (typeof STATUSES)[number];
	source: (typeof SOURCES)[number];
	observed_at: string;
	completed: string[] | null;
	remaining: string[] | null;
	blockers: string[] | null;
}
export const AGENT_TASK_STATE_SCHEMA = Type.Object(
	{
		status: Type.Union(STATUSES.map((status) => Type.Literal(status))),
		source: Type.Literal("agent-report"),
		observed_at: Type.String({ pattern: "^.+T.+(?:Z|[+-][0-9]{2}:[0-9]{2})$" }),
		completed: Type.Union([Type.Array(Type.String({ minLength: 1 })), Type.Null()]),
		remaining: Type.Union([Type.Array(Type.String({ minLength: 1 })), Type.Null()]),
		blockers: Type.Union([Type.Array(Type.String({ minLength: 1 })), Type.Null()]),
	},
	{ additionalProperties: false },
);

export function isTaskStateSnapshot(value: unknown): value is TaskStateSnapshot {
	if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
	const snapshot = value as Record<string, unknown>;
	const fields = ["status", "source", "observed_at", "completed", "remaining", "blockers"];
	if (Object.keys(snapshot).length !== fields.length || fields.some((name) => !(name in snapshot))) return false;
	if (
		!(STATUSES as readonly unknown[]).includes(snapshot.status) ||
		!(SOURCES as readonly unknown[]).includes(snapshot.source)
	)
		return false;
	if (
		typeof snapshot.observed_at !== "string" ||
		!/^.+T.+(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(snapshot.observed_at) ||
		!Number.isFinite(Date.parse(snapshot.observed_at))
	)
		return false;
	return [snapshot.completed, snapshot.remaining, snapshot.blockers].every(
		(items) =>
			items === null ||
			(Array.isArray(items) &&
				items.every((item) => typeof item === "string" && item.length > 0 && !item.includes("\0"))),
	);
}

export function copyTaskState(snapshot: TaskStateSnapshot): TaskStateSnapshot {
	return {
		...snapshot,
		completed: snapshot.completed?.slice() ?? null,
		remaining: snapshot.remaining?.slice() ?? null,
		blockers: snapshot.blockers?.slice() ?? null,
	};
}

/** Observe only this queue, at this instant. Absence is not execution history.
 * Never emits queue text or substitutes a later observation for an old fact. */
export function captureDecisionTaskState(store: WorkerStore, owner: string, task: string): TaskStateSnapshot {
	let status: TaskStateSnapshot["status"] = "unknown";
	try {
		const parents: Array<{ name: string; stat: fs.Stats }> = [];
		let parent = path.dirname(store.queuePath);
		while (true) {
			const stat = fs.lstatSync(parent);
			if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error("unprovable queue parent");
			parents.push({ name: parent, stat });
			const next = path.dirname(parent);
			if (next === parent) break;
			parent = next;
		}
		let first: fs.Stats | undefined;
		try {
			first = fs.lstatSync(store.queuePath);
		} catch (error) {
			if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
		}
		if (first === undefined) {
			status = "not-queued";
		} else {
			if (!first.isFile() || first.isSymbolicLink()) throw new Error("unprovable queue file");
			const queue = store.readQueue();
			const last = fs.lstatSync(store.queuePath);
			if (
				last.isSymbolicLink() ||
				first.ino !== last.ino ||
				first.dev !== last.dev ||
				first.size !== last.size ||
				first.mtimeMs !== last.mtimeMs
			)
				throw new Error("queue changed during observation");
			if (queue.unparsable.length > 0 || (queue.version !== 1 && queue.version !== 2))
				throw new Error("ambiguous queue");
			const rows = queue.rows.filter((row) => row.taskKey === task);
			if (rows.length === 0) status = "not-queued";
			else if (rows.length === 1) {
				const row = rows[0];
				const expected = path.resolve(path.dirname(store.queuePath), owner, "workers", task, "task.md");
				const actual = path.resolve(row.taskPath);
				const samePath =
					process.platform === "win32" ? actual.toLowerCase() === expected.toLowerCase() : actual === expected;
				if (samePath && workerOwnerKey(row) === owner && (STATUSES as readonly string[]).includes(row.status))
					status = row.status;
			}
		}
		for (const item of parents) {
			const last = fs.lstatSync(item.name);
			if (last.isSymbolicLink() || last.ino !== item.stat.ino || last.dev !== item.stat.dev)
				throw new Error("queue parent changed");
		}
	} catch {
		status = "unknown";
	}
	return {
		status,
		source: "worker-registry",
		observed_at: new Date().toISOString(),
		completed: null,
		remaining: null,
		blockers: null,
	};
}
