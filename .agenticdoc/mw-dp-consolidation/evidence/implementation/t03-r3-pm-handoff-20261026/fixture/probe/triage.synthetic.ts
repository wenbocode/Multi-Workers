// SYNTHETIC PARSER INPUT ONLY
const UNIVERSAL_REQUIRED_FIELDS = ["schema_version", "decision_point", "key", "phase", "task_type", "risk", "risk_source", "authority_tier", "questions_version"];
export const REQUIRED_FIELDS_BY_DP: Record<string, string[]> = {
"dp-w-type": ["task_goal", "task_requirements", "task_deliverables"],
"dp-pm-steer": ["task_goal", "task_requirements", "task_deliverables", "pm_decision_background"],
"dp-w-check-task": ["task_goal", "reachability_facts", "completed", "remaining", "blockers", "constraints"],
"dp-QG": ["review_requirements", "review_evidence", "review_findings", "uncovered_scope"],
"dp-gate-approve": ["gate_background", "current_state", "condition_evidence", "pm_note.subject", "pm_note.planned_action", "pm_note.basis.goal", "pm_note.basis.evidence", "pm_note.basis.budget", "pm_note.basis.authority"],
"dp-sign-key": ["delivery_goal", "actual_completion", "verification_evidence.verified", "verification_evidence.unverified", "unfinished_impact"],
"dp-auto": ["question", "background.task_goal", "background.current_state", "background.tried", "background.unknowns", "background.constraints", "handling_options"],
"dp-route": ["decision_actor", "decision_object", "question"],

};
