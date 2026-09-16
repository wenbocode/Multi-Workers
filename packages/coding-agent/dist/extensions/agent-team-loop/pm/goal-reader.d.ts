export type GoalStatus = "draft" | "active" | "unknown";
export interface Goal {
    status: GoalStatus;
    goal: string;
    context: string;
    keyConstraints: string;
}
export declare function parseGoalMd(content: string): Goal;
/** Read goal.md if present; returns null when the file does not exist. Read-only. */
export declare function readGoal(agenticdocRoot: string): Goal | null;
/**
 * Whether the project goal is established (usable as the north-star anchor).
 * - status: active            → established
 * - status: draft / missing   → NOT established (needs /goal brainstorm)
 * - no status line (legacy)   → established iff any section has real content,
 *                               so pre-existing goal.md files are not blocked.
 */
export declare function isGoalEstablished(goal: Goal | null): boolean;
//# sourceMappingURL=goal-reader.d.ts.map