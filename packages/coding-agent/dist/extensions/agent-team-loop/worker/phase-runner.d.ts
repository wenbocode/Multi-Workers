export interface TaskPhase {
    name: string;
    prompt: string;
}
export interface PhaseContext {
    taskKey: string;
    agenticdocRoot: string;
}
export interface PhaseResult {
    phaseIndex: number;
    summary: string;
    goalMtime: number;
}
export declare function goalMtime(agenticdocRoot: string): number;
export declare function writePhaseFile(taskKey: string, agenticdocRoot: string, phaseIndex: number, summary: string): void;
//# sourceMappingURL=phase-runner.d.ts.map