export type Phase = "SPEC" | "DESIGN" | "PLAN" | "TASKS" | "EXECUTE" | "DONE";
export interface PmState {
    phase: Phase;
    claimId: string;
    taskKey: string;
    notes: string;
    updatedAt: string;
}
export declare class StateManager {
    private readonly statePath;
    constructor(agenticdocRoot: string, taskKey: string);
    read(): Partial<PmState>;
    write(state: Partial<PmState>): Promise<void>;
}
//# sourceMappingURL=state-manager.d.ts.map