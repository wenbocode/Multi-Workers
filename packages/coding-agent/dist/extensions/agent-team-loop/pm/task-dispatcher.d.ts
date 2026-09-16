import type { WorkerEntry, WorkerStore } from "../shared/worker-store.ts";
export declare function dispatchTask(entry: Omit<WorkerEntry, "dispatchedAt" | "updatedAt">, store: WorkerStore): Promise<void>;
//# sourceMappingURL=task-dispatcher.d.ts.map