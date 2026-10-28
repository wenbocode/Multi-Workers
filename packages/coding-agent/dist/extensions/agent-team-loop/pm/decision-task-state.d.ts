import { Type } from "typebox";
import { type WorkerStore } from "../shared/worker-store.ts";
declare const STATUSES: readonly ["not-queued", "pending", "running", "done", "failed", "needs-clarification", "lost", "unknown"];
declare const SOURCES: readonly ["worker-registry", "dispatch-result", "agent-report"];
export interface TaskStateSnapshot {
    status: (typeof STATUSES)[number];
    source: (typeof SOURCES)[number];
    observed_at: string;
    completed: string[] | null;
    remaining: string[] | null;
    blockers: string[] | null;
}
export declare const AGENT_TASK_STATE_SCHEMA: Type.TObject<{
    status: Type.TUnion<Type.TLiteral<"done" | "failed" | "lost" | "needs-clarification" | "not-queued" | "pending" | "running" | "unknown">[]>;
    source: Type.TLiteral<"agent-report">;
    observed_at: Type.TString;
    completed: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
    remaining: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
    blockers: Type.TUnion<[Type.TArray<Type.TString>, Type.TNull]>;
}>;
export declare function isTaskStateSnapshot(value: unknown): value is TaskStateSnapshot;
export declare function copyTaskState(snapshot: TaskStateSnapshot): TaskStateSnapshot;
/** Observe only this queue, at this instant. Absence is not execution history.
 * Never emits queue text or substitutes a later observation for an old fact. */
export declare function captureDecisionTaskState(store: WorkerStore, owner: string, task: string): TaskStateSnapshot;
export {};
//# sourceMappingURL=decision-task-state.d.ts.map