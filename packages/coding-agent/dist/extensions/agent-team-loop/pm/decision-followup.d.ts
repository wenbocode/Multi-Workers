declare const TARGET_DPS: readonly ["dp-pm-steer", "dp-auto"];
declare const INTENT_STATUSES: readonly ["prepared", "requesting", "answered", "failed", "executed"];
declare const TASK_STATUSES: readonly ["not-queued", "pending", "running", "done", "failed", "needs-clarification", "lost", "unknown"];
type TargetDp = (typeof TARGET_DPS)[number];
type IntentStatus = (typeof INTENT_STATUSES)[number];
export type FollowupTaskStatus = (typeof TASK_STATUSES)[number];
export interface BoundPmIdentity {
    role: "pm";
    key: string;
    window_id: string;
}
export interface DecisionFollowupIntent {
    schema_version: 1;
    parent_ref: string;
    parent_logical_id: string;
    parent_decision_id: string;
    parent_matter_version: string;
    target_dp: TargetDp;
    material_version: string;
    basis_version: string;
    owner_key: string;
    task_key: string | null;
    prepared_by: BoundPmIdentity;
    restricted_action: string;
    restricted_executor: string;
    status: IntentStatus;
    request_ref: string | null;
    answer: string | null;
    failure_reason: string | null;
    action_evidence?: string;
}
/** Obtained from the current gate, prepared material, and bound PM window. */
export type ExpectedDecisionFollowup = Pick<DecisionFollowupIntent, (typeof BINDING_FIELDS)[number]>;
declare const BINDING_FIELDS: readonly ["parent_ref", "parent_logical_id", "parent_decision_id", "parent_matter_version", "material_version", "basis_version", "target_dp", "owner_key", "task_key", "restricted_action", "restricted_executor"];
/** This scope comes from the host, never the prepared intent or a tool argument. */
type LifecycleScope = {
    projectDir: string;
    parentEvidence?: {
        pmNote: string;
        modelBasis: string;
        stageNoteEvent?: string;
    };
} | {
    isolatedTestRoot: string;
    projectId: string;
};
export type DecisionFollowupRequestResult = {
    available: true;
    request_ref: string;
    answer: string;
} | {
    available: false;
    reason: string;
};
export interface DecisionFollowupResult {
    state: "not-started" | "in-progress" | "answered" | "failed" | "executed" | "blocked" | "unknown";
    reason?: string;
    request_ref?: string;
    answer?: string;
    basis_id?: string;
    request_started: boolean;
    duplicate: boolean;
    parent_released: false;
}
interface ResumeInput {
    intent_path: string;
    expected: ExpectedDecisionFollowup;
    bound_pm: BoundPmIdentity | null;
    observe_task: (ownerKey: string, taskKey: string | null) => FollowupTaskStatus;
    request: (intent: Readonly<DecisionFollowupIntent>) => Promise<DecisionFollowupRequestResult>;
    lifecycle?: LifecycleScope;
}
interface ExecutedInput {
    intent_path: string;
    expected: ExpectedDecisionFollowup;
    bound_pm: BoundPmIdentity | null;
    request_ref: string;
    action_evidence: string;
    lifecycle?: LifecycleScope;
}
/**
 * Resume one already-prepared PM follow-up. The intent file is coordination
 * state only: the real request still goes through the injected decision client.
 * A persisted `requesting` state is deliberately unknown after a crash, because
 * the filesystem and remote request are not one transaction.
 */
export declare function resumeDecisionFollowup(input: ResumeInput): Promise<DecisionFollowupResult>;
/** Record a real, already-performed follow-up action. This never performs the
 * action and never releases the parent gate; later consumers must independently
 * validate the action evidence and gate conditions. */
export declare function markDecisionFollowupExecuted(input: ExecutedInput): Promise<DecisionFollowupResult>;
export {};
//# sourceMappingURL=decision-followup.d.ts.map