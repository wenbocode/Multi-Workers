import type { WorkerEntry, WorkerStore } from "../shared/worker-store.ts";

export async function dispatchTask(
	entry: Omit<WorkerEntry, "dispatchedAt" | "updatedAt">,
	store: WorkerStore,
): Promise<void> {
	const now = new Date().toISOString();
	const full: WorkerEntry = {
		...entry,
		dispatchedAt: now,
		updatedAt: now,
	};
	await store.upsert(full);
}
