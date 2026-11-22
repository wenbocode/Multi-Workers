import { describe, expect, it } from "vitest";
import {
	type BudgetRefreshAttempt,
	type CollectEvidenceInput,
	classifyDecisionFeedback,
	compareLocalSelectionToHost,
	DECISION_HANDOFF_SCHEMA_ID,
	DECISION_HANDOFF_SCHEMA_VERSION,
	type DecisionFeedback,
	evaluateBudgetContinuation,
	FEEDBACK_CATEGORIES,
	type FeedbackEnvelope,
	type HostBinding,
	type HostFacts,
	isDecisionRef,
	type LocalBusinessSelectionInput,
	type LocalExecutionRecordV1,
	type LocalSelectionRecordV1,
	type MatterBudgetV1,
	parseBudgetReservationRequest,
	parseBudgetReservationResult,
	parseDecisionFeedback,
	parseDecisionRef,
	parseLocalExecutionRecord,
	parseLocalSelectionRecord,
	parsePmDisposition,
	SCHEMA_V1,
	type StopSignalKind,
	stopScopeForBudgetFact,
	stopScopeForSignal,
	validateCollectEvidenceDisposition,
	validateLocalBusinessSelection,
	validateMatterBudget,
} from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";

const NOW = "2026-11-12T12:30:00+08:00";
const DEADLINE = "2026-11-12T13:00:00+08:00";
const HOST_OWNER = "WENBOZHOU-PC5:13148";
const MATTER = "matter:T01";

/** Untrusted observations are always handed in as `unknown` (no `any`). */
function untrusted(value: unknown): unknown {
	return value;
}

function binding(overrides: Partial<HostBinding> = {}): HostBinding {
	return {
		role: "pm",
		owner: HOST_OWNER,
		claim_id: "claim:1",
		key: "mw-pm-dp-continuity",
		binding_version: "v3",
		observed_at: NOW,
		...overrides,
	};
}

function hostFacts(overrides: Partial<HostFacts> = {}): HostFacts {
	return { binding: binding(), ...overrides };
}

function feedbackEnvelope(overrides: Partial<FeedbackEnvelope> = {}): FeedbackEnvelope {
	return {
		feedback_ref: "fb:1",
		matter_ref: MATTER,
		origin: "ask",
		stage: "response",
		evidence_refs: ["trace:1"],
		...overrides,
	};
}

function classify(
	raw: unknown,
	host: HostFacts = hostFacts(),
	envelope: FeedbackEnvelope = feedbackEnvelope(),
): DecisionFeedback {
	return classifyDecisionFeedback({ envelope, host, raw: untrusted(raw) });
}

function matterBudget(overrides: Partial<MatterBudgetV1> = {}): MatterBudgetV1 {
	return {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		budget_ref: "budget:T01",
		matter_ref: MATTER,
		parent_matter_ref: "matter:parent",
		deadline: DEADLINE,
		max_steps: 3,
		no_progress_limit: 2,
		remaining_cost: 5,
		steps_consumed: 1,
		cost_consumed: 1,
		no_progress_count: 0,
		source_refs: ["tasks/T01-local-contract.md:timeout=90", "run.json:remaining"],
		...overrides,
	};
}

function collectInput(overrides: Partial<CollectEvidenceInput> = {}): CollectEvidenceInput {
	return {
		disposition_ref: "disp:1",
		feedback_ref: "fb:1",
		matter_ref: MATTER,
		goal_ref: "goal.md:1",
		host: hostFacts(),
		tool_scope: { tools: ["read", "find"], scope_ref: "card:T01:read-face", read_only: true },
		planned_action: { tool: "read", scope_ref: "card:T01:read-face", read_only: true },
		gap_refs: ["gap:material"],
		expected_result: "two independent reads",
		result_consumer: "pm-orchestrator:ack",
		budget: matterBudget(),
		...overrides,
	};
}

function selectionInput(overrides: Partial<LocalBusinessSelectionInput> = {}): LocalBusinessSelectionInput {
	return {
		local_ref: "local:T01:1",
		source: "pm",
		host: hostFacts(),
		feedback_ref: "fb:1",
		matter_ref: MATTER,
		matter_version: "v3",
		material: untrusted({
			material_ref: "card:T01",
			fields: { task_goal: "g", task_requirements: "r", task_deliverables: "d" },
			digest: "sha256:material",
			evidence_refs: ["card:T01:1"],
		}),
		preparation: untrusted({
			prepared_at: NOW,
			digest: "sha256:basis",
			basis_catalog: [{ id: "b1", text: "basis", material_refs: ["task_goal"], applies_to: ["c1", "c2"] }],
		}),
		candidates: untrusted({ version: "v3", ids: ["c1", "c2"] }),
		selected_action: "c1",
		selected_basis_id: "b1",
		budget: matterBudget(),
		created_at: NOW,
		...overrides,
	};
}

function validSelectionRecord(): LocalSelectionRecordV1 {
	const result = validateLocalBusinessSelection(selectionInput());
	if (!result.ok) throw new Error(`fixture must be valid: ${JSON.stringify(result.issues)}`);
	return result.value;
}

function validExecutionRecord(): LocalExecutionRecordV1 {
	return {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		kind: "local-execution",
		origin: "local-decision",
		source: "pm",
		local_ref: "local:T01:1",
		host_binding: binding(),
		action_ref: "tool_call:read:7",
		result_ref: "tool_result:read:7",
		executor: "pm-orchestrator",
		target_digest: "sha256:target",
		observed_effect: "two reads recorded",
		effect_state: "known",
		verified_by: "target-verifier:1",
		budget_ref: "budget:T01",
		created_at: NOW,
	};
}

function attempt(
	proposed: MatterBudgetV1,
	reason: BudgetRefreshAttempt["reason"] = "new-turn",
	matter = MATTER,
): BudgetRefreshAttempt {
	return { reason, matter_ref: matter, child_matter_ref: `${MATTER}:child`, proposed_budget: proposed };
}

describe("feedback classification (design §4.1, 13 categories)", () => {
	it("classifies a normal DP answer and keeps the trusted host owner/binding", () => {
		const feedback = classify({
			available: true,
			decision_id: "dp-auto:2026-11-12T04:00:00Z",
			answers: { q: { value: "ok" } },
			mode: "auto",
		});
		expect(feedback.category).toBe("answer");
		expect(feedback.effect_state).toBe("none");
		expect(feedback.stop_scope).toBe("none");
		expect(feedback.owner).toBe(HOST_OWNER);
		expect(feedback.binding?.binding_version).toBe("v3");
		expect(parseDecisionFeedback(JSON.parse(JSON.stringify(feedback))).ok).toBe(true);
	});

	it("keeps suggest as advisory, not an approval", () => {
		const feedback = classify({
			available: true,
			decision_id: "dp-QG:1",
			answers: { q: { value: "pass" } },
			mode: "suggest",
		});
		expect(feedback.category).toBe("advisory");
		expect(feedback.stop_scope).toBe("none");
	});

	it("preserves disabled and unconfigured transport facts with their disable_scope", () => {
		const disabled = classify({ available: false, unavailable: "disabled", disable_scope: "single-dp" });
		expect(disabled.category).toBe("service-unavailable");
		expect(disabled.raw_reason).toBe("disabled");
		expect(disabled.disable_scope).toBe("single-dp");
		expect(disabled.stop_scope).toBe("none");
		const unconfigured = classify({ available: false, unavailable: "entry-unavailable", disable_scope: "transport" });
		expect(unconfigured.category).toBe("service-unavailable");
		expect(unconfigured.disable_scope).toBe("transport");
	});

	it("requires a real host exemption fact; exemption carries no unavailable claim", () => {
		const feedback = classify(
			{ available: false, unavailable: "disabled" },
			hostFacts({ exemption: { config_ref: "decide.json:signoff", kind: "signoff-disabled" } }),
		);
		expect(feedback.category).toBe("exemption");
		expect(feedback.exemption_fact).toEqual({ config_ref: "decide.json:signoff", kind: "signoff-disabled" });
		expect(feedback.stop_scope).toBe("none");
		expect(feedback.authority_fact).toBeUndefined();
		expect(Object.hasOwn(feedback, "unavailable")).toBe(false);
	});

	it("does not turn an unknown reason / p0 model text into authority-required", () => {
		const feedback = classify({
			available: false,
			unavailable: "quantum-fluke",
			escalated_reason: "p0-over-authority",
		});
		expect(feedback.category).toBe("unclassified");
		expect(feedback.raw_reason).toBe("quantum-fluke");
		expect(feedback.escalated_reason).toBe("p0-over-authority");
		expect(feedback.untrusted_signals).toContain("authority-claim");
		expect(feedback.authority_fact).toBeUndefined();
		expect(feedback.stop_scope).not.toBe("user-global");
	});

	it("requires a host policy fact for authority-required (p0 text alone is not enough)", () => {
		const raw = { available: false, unavailable: "quantum-fluke", escalated_reason: "p0-over-authority" };
		const withFact = classify(
			raw,
			hostFacts({ authority_gap: { policy_ref: "policy:human-only", condition: "gate is human-only" } }),
		);
		expect(withFact.category).toBe("authority-required");
		expect(withFact.authority_fact?.policy_ref).toBe("policy:human-only");
		expect(withFact.stop_scope).toBe("matter");
		const withoutFact = classify(raw);
		expect(withoutFact.category).toBe("unclassified");
		expect(withoutFact.authority_fact).toBeUndefined();
	});

	it("keeps service timeout at service-request scope, never a global stop or new authority", () => {
		const feedback = classify({ available: false, unavailable: "timeout", error: "aborted", aborted: true });
		expect(feedback.category).toBe("service-unavailable");
		expect(feedback.stop_scope).toBe("service-request");
		expect(feedback.effect_state).toBe("none");
		expect(feedback.untrusted_signals).toContain("stop-claim");
		expect(feedback.authority_fact).toBeUndefined();
		expect(feedback.stop_signal_ref).toBeUndefined();
	});

	it("preserves malformed and contradictory replies as integrity-error with raw text", () => {
		const badType = classify({ available: "yes", decision_id: "dp:1" });
		expect(badType.category).toBe("integrity-error");
		expect(badType.stop_scope).toBe("unknown");
		const missingAnswers = classify({ available: true, decision_id: "dp:1" });
		expect(missingAnswers.category).toBe("integrity-error");
		const contradictory = classify({ available: true, decision_id: "dp:1", answers: {}, unavailable: "timeout" });
		expect(contradictory.category).toBe("integrity-error");
	});

	it("keeps low-confidence answers untrusted with the original confidence value", () => {
		const feedback = classify({
			available: true,
			decision_id: "dp:1",
			answers: { q: { value: "x" } },
			confidence: 0.21,
			low_confidence: true,
		});
		expect(feedback.category).toBe("uncertain-answer");
		expect(feedback.confidence).toBe(0.21);
		expect(feedback.effect_state).toBe("none");
	});

	it("preserves an unknown non-object observation verbatim", () => {
		const feedback = classify("mystery failure");
		expect(feedback.category).toBe("unclassified");
		expect(feedback.raw_reason).toBe("mystery failure");
		expect(feedback.raw_payload).toBe("mystery failure");
		expect(parseDecisionFeedback(JSON.parse(JSON.stringify(feedback))).ok).toBe(true);
	});

	it("never truncates an oversize transport payload and marks it as a transport gap", () => {
		const long = "X".repeat(9000);
		const feedback = classify({
			available: false,
			unavailable: "input-oversize",
			raw_reason: long,
			transport_oversize: true,
		});
		expect(feedback.category).toBe("input-gap");
		expect(feedback.raw_reason).toBe(long);
		expect(feedback.raw_reason?.length).toBe(9000);
		expect(JSON.stringify(feedback.raw_payload)).toContain(long);
		expect(feedback.transport_oversize).toBe(true);
		expect(feedback.gaps).toContain("transport.oversize");
	});

	it("derives owner from the host snapshot, rejecting model self-report", () => {
		const mismatch = classify({ available: false, unavailable: "disabled", owner: "impostor" });
		expect(mismatch.category).toBe("binding-invalid");
		expect(mismatch.owner).toBe(HOST_OWNER);
		expect(mismatch.untrusted_signals).toContain("owner-self-report");
		const match = classify({
			available: true,
			decision_id: "dp:1",
			answers: { q: { value: "x" } },
			owner: HOST_OWNER,
		});
		expect(match.category).toBe("answer");
		expect(match.owner).toBe(HOST_OWNER);
	});

	it("rejects role self-report and stale binding_version against the host snapshot", () => {
		const role = classify({ available: false, unavailable: "disabled", role: "coding" });
		expect(role.category).toBe("binding-invalid");
		const stale = classify({ available: false, unavailable: "disabled", binding_version: "v1" });
		expect(stale.category).toBe("binding-invalid");
	});

	it("takes user-stop / parent-cancel only from host stop signals, with distinct scopes", () => {
		const userStop = classify(
			{ available: false, unavailable: "timeout" },
			hostFacts({ stop_signals: [{ signal_ref: "user:1", kind: "user-stop" }] }),
		);
		expect(userStop.category).toBe("cancelled");
		expect(userStop.stop_scope).toBe("user-global");
		expect(userStop.stop_signal_ref).toBe("user:1");
		expect(userStop.effect_state).toBe("unknown");
		const parentCancel = classify(
			{ available: false, unavailable: "timeout" },
			hostFacts({ stop_signals: [{ signal_ref: "parent:1", kind: "parent-cancel" }] }),
		);
		expect(parentCancel.stop_scope).toBe("pm-or-key");
		expect(stopScopeForSignal("worker-deadline")).toBe("worker-run");
		expect(stopScopeForSignal("key-budget")).toBe("pm-or-key");
		expect(stopScopeForSignal("service-timeout")).toBe("service-request");
	});

	it("separates worker deadline, key budget and service timeout scopes", () => {
		const deadline = classify(
			{ available: false, unavailable: "timeout" },
			hostFacts({ stop_signals: [{ signal_ref: "wd:1", kind: "worker-deadline" }] }),
		);
		expect(deadline.category).toBe("budget-exhausted");
		expect(deadline.stop_scope).toBe("worker-run");
		const serviceTimeout = classify(
			{ available: false, unavailable: "timeout" },
			hostFacts({ stop_signals: [{ signal_ref: "svc:1", kind: "service-timeout" }] }),
		);
		expect(serviceTimeout.category).toBe("service-unavailable");
		expect(serviceTimeout.stop_scope).toBe("service-request");
	});

	it("separates service-budget and task-budget exhaustion facts", () => {
		const service = classify(
			{ available: false, unavailable: "timeout" },
			hostFacts({ budget_facts: [{ budget_ref: "b:svc", scope: "service" }] }),
		);
		expect(service.category).toBe("budget-exhausted");
		expect(service.stop_scope).toBe("service-request");
		expect(service.budget_fact?.scope).toBe("service");
		const task = classify(
			{ available: false, unavailable: "timeout" },
			hostFacts({ budget_facts: [{ budget_ref: "b:task", scope: "task" }] }),
		);
		expect(task.stop_scope).toBe("matter");
		expect(task.budget_fact?.scope).toBe("task");
		expect(stopScopeForBudgetFact("service")).toBe("service-request");
		expect(stopScopeForBudgetFact("task")).toBe("matter");
	});

	it("marks a host-observed unknown side effect as effect-unknown", () => {
		const feedback = classify(
			{ available: false, unavailable: "timeout" },
			hostFacts({ effect_unknown: { action_ref: "tool:write:1" } }),
		);
		expect(feedback.category).toBe("effect-unknown");
		expect(feedback.effect_state).toBe("unknown");
		expect(feedback.stop_scope).toBe("none");
	});

	it("rejects unknown categories and DP impersonation fields in a feedback JSON row", () => {
		const feedback = classify({ available: false, unavailable: "disabled" });
		const serialized = JSON.parse(JSON.stringify(feedback)) as Record<string, unknown>;
		expect(parseDecisionFeedback({ ...serialized, category: "made-up" }).ok).toBe(false);
		expect(parseDecisionFeedback({ ...serialized, available: true }).ok).toBe(false);
	});
});

describe("layered material validation (design §4.3)", () => {
	it("accepts collect-evidence without any complete business conclusion material", () => {
		const input = collectInput();
		expect("material" in input).toBe(false);
		expect("preparation" in input).toBe(false);
		expect("candidates" in input).toBe(false);
		const result = validateCollectEvidenceDisposition(input);
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.value.kind).toBe("collect-evidence");
		expect(result.value.status).toBe("planned");
		expect(result.value.owner).toBe(HOST_OWNER);
		expect(result.value.budget_ref).toBe("budget:T01");
		expect(result.host_source_verified).toBe(false);
		expect(parsePmDisposition(JSON.parse(JSON.stringify(result.value))).ok).toBe(true);
	});

	it("requires a legal host owner, pm role, legal tool scope and parent budget", () => {
		const noOwner = validateCollectEvidenceDisposition(
			collectInput({ host: hostFacts({ binding: binding({ owner: undefined }) }) }),
		);
		expect(noOwner.ok).toBe(false);
		if (!noOwner.ok) expect(noOwner.authority_required).toBe(false);
		expect(
			validateCollectEvidenceDisposition(collectInput({ host: hostFacts({ binding: binding({ role: "coding" }) }) }))
				.ok,
		).toBe(false);
		expect(
			validateCollectEvidenceDisposition(
				collectInput({ planned_action: { tool: "write", scope_ref: "card:T01:read-face", read_only: true } }),
			).ok,
		).toBe(false);
		expect(validateCollectEvidenceDisposition(collectInput({ goal_ref: "" })).ok).toBe(false);
	});

	it("returns only fillable budget gaps, never a fabricated human-authority question", () => {
		const result = validateCollectEvidenceDisposition(collectInput({ budget: {} }));
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.authority_required).toBe(false);
			expect(result.gaps.some((gap) => gap.startsWith("budget."))).toBe(true);
			expect(result.issues.every((item) => !item.rule.includes("authorization"))).toBe(true);
		}
	});

	it("accepts a complete local business selection with current candidates and basis", () => {
		const result = validateLocalBusinessSelection(selectionInput());
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.value.kind).toBe("local-selection");
		expect(result.value.action_state).toBe("planned");
		expect(result.value.business_completed).toBe(false);
		expect(result.value.source).toBe("pm");
		expect(result.value.material_digest).toBe("sha256:material");
		expect(result.value.basis_digest).toBe("sha256:basis");
		expect(Object.hasOwn(result.value, "action_ref")).toBe(false);
		expect(Object.hasOwn(result.value, "result_ref")).toBe(false);
		expect(result.host_source_verified).toBe(false);
		expect(parseLocalSelectionRecord(JSON.parse(JSON.stringify(result.value))).ok).toBe(true);
	});

	it("requires a separate dp-kind ref for a real parent DP, never a local ref", () => {
		const withParent = validateLocalBusinessSelection(
			selectionInput({ parent_decision_ref: untrusted({ kind: "dp", decision_id: "dp-auto:real" }) }),
		);
		expect(withParent.ok).toBe(true);
		if (withParent.ok) expect(withParent.value.parent_decision_ref?.kind).toBe("dp");
		const fakeParent = validateLocalBusinessSelection(
			selectionInput({ parent_decision_ref: untrusted({ kind: "local", local_ref: "local:T01:1" }) }),
		);
		expect(fakeParent.ok).toBe(false);
	});

	it("rejects missing basis, non-applicable basis and unknown material refs", () => {
		const emptyBasis = validateLocalBusinessSelection(
			selectionInput({ preparation: untrusted({ prepared_at: NOW, digest: "d", basis_catalog: [] }) }),
		);
		expect(emptyBasis.ok).toBe(false);
		const wrongBasis = validateLocalBusinessSelection(
			selectionInput({
				preparation: untrusted({
					prepared_at: NOW,
					digest: "d",
					basis_catalog: [{ id: "b1", text: "b", material_refs: ["task_goal"], applies_to: ["c2"] }],
				}),
			}),
		);
		expect(wrongBasis.ok).toBe(false);
		const unknownRef = validateLocalBusinessSelection(
			selectionInput({
				preparation: untrusted({
					prepared_at: NOW,
					digest: "d",
					basis_catalog: [{ id: "b1", text: "b", material_refs: ["missing"], applies_to: ["c1"] }],
				}),
			}),
		);
		expect(unknownRef.ok).toBe(false);
	});

	it("rejects a wrong role for a pm-sourced selection", () => {
		const result = validateLocalBusinessSelection(
			selectionInput({ host: hostFacts({ binding: binding({ role: "coding" }) }) }),
		);
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.authority_required).toBe(false);
	});

	it("rejects stale binding, owner/role drift and stop/authority scope against the current host", () => {
		const record = validSelectionRecord();
		expect(compareLocalSelectionToHost(record, hostFacts()).ok).toBe(true);
		const stale = compareLocalSelectionToHost(record, hostFacts({ binding: binding({ binding_version: "v4" }) }));
		expect(stale.ok).toBe(false);
		if (!stale.ok) expect(stale.issues.some((item) => item.rule.includes("stale"))).toBe(true);
		const ownerDrift = compareLocalSelectionToHost(
			record,
			hostFacts({ binding: binding({ owner: "other-window" }) }),
		);
		expect(ownerDrift.ok).toBe(false);
		expect(
			compareLocalSelectionToHost(record, hostFacts({ stop_signals: [{ signal_ref: "u:1", kind: "user-stop" }] }))
				.ok,
		).toBe(false);
		expect(
			compareLocalSelectionToHost(record, hostFacts({ authority_gap: { policy_ref: "p", condition: "c" } })).ok,
		).toBe(false);
		const consistent = compareLocalSelectionToHost(record, hostFacts());
		expect(consistent.ok).toBe(true);
		if (consistent.ok) expect(consistent.host_source_verified).toBe(false);
	});

	it("does not let a transport oversize flag stand in for complete business material", () => {
		const oversize = classify({
			available: false,
			unavailable: "input-oversize",
			raw_reason: "X".repeat(9000),
			transport_oversize: true,
		});
		expect(oversize.transport_oversize).toBe(true);
		expect(oversize.raw_reason?.length).toBe(9000);
		const asMaterial = validateLocalBusinessSelection(
			selectionInput({ material: untrusted({ transport_oversize: true }) }),
		);
		expect(asMaterial.ok).toBe(false);
		if (!asMaterial.ok) expect(asMaterial.authority_required).toBe(false);
		const absent = validateLocalBusinessSelection(
			selectionInput({ material: undefined, preparation: undefined, candidates: undefined }),
		);
		expect(absent.ok).toBe(false);
		if (!absent.ok) {
			expect(absent.gaps).toContain("material");
			expect(absent.gaps).toContain("preparation");
			expect(absent.gaps).toContain("candidates");
			expect(absent.authority_required).toBe(false);
		}
	});
});

describe("local selection / execution separation (design §4.4)", () => {
	it("rejects a selection carrying execution facts or a completed/executed claim", () => {
		const record = validSelectionRecord();
		const smuggled: unknown[] = [
			{ ...record, action_ref: "tool:1", result_ref: "res:1" },
			{ ...record, observed_effect: "done", effect_state: "known" },
			{ ...record, business_completed: true },
			{ ...record, action_state: "executed" },
			{ ...record, effect_state: "unknown" },
		];
		for (const row of smuggled) expect(parseLocalSelectionRecord(row).ok).toBe(false);
		expect(parseLocalExecutionRecord(record).ok).toBe(false);
	});

	it("accepts an execution record only with real action/result refs and a verifier", () => {
		const execution = validExecutionRecord();
		const result = parseLocalExecutionRecord(JSON.parse(JSON.stringify(execution)));
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.value.effect_state).toBe("known");
			expect(result.host_source_verified).toBe(false);
		}
		expect(parseLocalExecutionRecord({ ...execution, effect_state: "none" }).ok).toBe(false);
		expect(parseLocalExecutionRecord({ ...execution, result_ref: "" }).ok).toBe(false);
	});

	it("rejects every local record that impersonates a DP fact", () => {
		const record = validSelectionRecord();
		for (const field of [
			"decision_id",
			"answers",
			"available",
			"business_decisions",
			"decision_ref",
			"request_ref",
			"receipt",
		]) {
			const bad = { ...record, [field]: "fabricated" };
			const result = parseLocalSelectionRecord(bad);
			expect(result.ok).toBe(false);
			if (!result.ok)
				expect(result.issues.some((item) => item.rule.includes("forbidden DP impersonation"))).toBe(true);
		}
		expect(parseLocalExecutionRecord({ ...validExecutionRecord(), decision_id: "dp:1" }).ok).toBe(false);
	});

	it("treats source and local_ref as data, not capabilities", () => {
		const record = validSelectionRecord();
		expect(parseLocalSelectionRecord({ ...record, source: "dp" }).ok).toBe(false);
		expect(parseLocalSelectionRecord({ ...record, local_ref: "" }).ok).toBe(false);
		const parsed = parseLocalSelectionRecord(JSON.parse(JSON.stringify(record)));
		expect(parsed.ok).toBe(true);
		if (parsed.ok) {
			expect(parsed.verification).toBe("shape-only");
			expect(parsed.host_source_verified).toBe(false);
		}
	});

	it("uses a discriminated DecisionRef and never verifies DP reality by shape", () => {
		expect(isDecisionRef({ kind: "dp", decision_id: "dp:1" })).toBe(true);
		expect(isDecisionRef({ kind: "local", local_ref: "l:1" })).toBe(true);
		expect(isDecisionRef({ kind: "dp", decision_id: "dp:1", extra: 1 })).toBe(false);
		expect(isDecisionRef({ kind: "local", decision_id: "dp:1" })).toBe(false);
		const parsed = parseDecisionRef({ kind: "dp", decision_id: "local:T01:1" });
		expect(parsed.ok).toBe(true);
		if (parsed.ok) expect(parsed.host_source_verified).toBe(false);
		expect(parseDecisionRef({ kind: "unknown", decision_id: "x" }).ok).toBe(false);
	});
});

describe("finite matter budget (design §4.5)", () => {
	it("accepts explicit finite values with real card/run provenance", () => {
		const result = validateMatterBudget(matterBudget());
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.value.remaining_cost).toBe(5);
			expect(result.value.deadline).toBe(DEADLINE);
			expect(result.host_source_verified).toBe(false);
		}
	});

	it("rejects missing/non-finite budgets as fillable gaps, never an authority question", () => {
		const missing = validateMatterBudget({});
		expect(missing.ok).toBe(false);
		if (!missing.ok) {
			expect(missing.authority_required).toBe(false);
			expect(missing.gaps).toEqual(
				expect.arrayContaining(["deadline", "max_steps", "no_progress_limit", "remaining_cost", "source_refs"]),
			);
		}
		for (const bad of [
			{ ...matterBudget(), remaining_cost: Number.POSITIVE_INFINITY },
			{ ...matterBudget(), max_steps: Number.NaN },
			{ ...matterBudget(), max_steps: -1 },
			{ ...matterBudget(), max_steps: 1.5 },
			{ ...matterBudget(), deadline: "not-a-date" },
			{ ...matterBudget(), source_refs: [] },
			{ ...matterBudget(), steps_consumed: 4 },
			{ ...matterBudget(), remaining_cost: -1 },
		]) {
			expect(validateMatterBudget(bad).ok).toBe(false);
		}
	});

	it("never refreshes budget on new turn / trigger / route / child", () => {
		const parent = matterBudget();
		const ok = evaluateBudgetContinuation(parent, attempt({ ...parent, steps_consumed: 2, cost_consumed: 2 }), NOW);
		expect(ok.allowed).toBe(true);
		expect(ok.reason).toBe("unchanged");
		expect(ok.budget_refreshed).toBe(false);
		const increase = evaluateBudgetContinuation(
			parent,
			attempt({ ...parent, remaining_cost: 6 }, "new-trigger"),
			NOW,
		);
		expect(increase.allowed).toBe(false);
		expect(increase.reason).toBe("budget-increase");
		expect(increase.budget_refreshed).toBe(false);
		const extended = evaluateBudgetContinuation(
			parent,
			attempt({ ...parent, deadline: "2026-11-12T14:00:00+08:00" }, "route"),
			NOW,
		);
		expect(extended.reason).toBe("deadline-extended");
		const reset = evaluateBudgetContinuation(
			{ ...parent, no_progress_count: 1 },
			attempt({ ...parent, no_progress_count: 0 }, "child-card"),
			NOW,
		);
		expect(reset.reason).toBe("counter-reset");
		const exhausted = evaluateBudgetContinuation(
			{ ...parent, remaining_cost: 0 },
			attempt(parent, "worker-restart"),
			NOW,
		);
		expect(exhausted.allowed).toBe(false);
		expect(exhausted.reason).toBe("budget-exhausted");
		const mismatch = evaluateBudgetContinuation(parent, attempt(parent, "new-turn", "other-matter"), NOW);
		expect(mismatch.reason).toBe("parent-mismatch");
	});

	it("defines reservation input/output shapes without implementing reservation", () => {
		const request = {
			parent_budget_ref: "budget:T01",
			matter_ref: MATTER,
			child_matter_ref: `${MATTER}:child`,
			requested_steps: 1,
			requested_cost: 1,
			lock_ref: "lock:intent",
		};
		expect(parseBudgetReservationRequest(request).ok).toBe(true);
		expect(parseBudgetReservationRequest({ ...request, requested_steps: 0 }).ok).toBe(false);
		expect(
			parseBudgetReservationResult({
				granted: true,
				reserved_steps: 1,
				reserved_cost: 1,
				child_budget_ref: "budget:child",
				remaining_after_steps: 2,
				remaining_after_cost: 4,
				reason: "granted",
			}).ok,
		).toBe(true);
		expect(
			parseBudgetReservationResult({
				granted: false,
				reserved_steps: 0,
				reserved_cost: 0,
				remaining_after_steps: 3,
				remaining_after_cost: 5,
				reason: "fabricated",
			}).ok,
		).toBe(false);
	});
});

describe("frozen schema v1", () => {
	it("is JSON-serializable and declares shape-only verification", () => {
		expect(SCHEMA_V1.id).toBe(DECISION_HANDOFF_SCHEMA_ID);
		expect(SCHEMA_V1.schema_version).toBe(1);
		expect(SCHEMA_V1.feedback_categories).toHaveLength(13);
		expect(FEEDBACK_CATEGORIES).toContain("unclassified");
		expect(SCHEMA_V1.forbidden_dp_fields).toEqual(
			expect.arrayContaining(["decision_id", "answers", "available", "business_decisions"]),
		);
		expect(SCHEMA_V1.verification_scope).toBe("shape-only");
		expect(SCHEMA_V1.host_source_verified).toBe(false);
		expect(JSON.parse(JSON.stringify(SCHEMA_V1))).toEqual(SCHEMA_V1);
	});

	it("parses the exact minimal JSON examples documented in T01-contract.md", () => {
		const hostBindingJson = `{
			"role": "pm",
			"owner": "WENBOZHOU-PC5:13148",
			"claim_id": "claim:1",
			"key": "mw-pm-dp-continuity",
			"binding_version": "v3",
			"observed_at": "2026-11-12T12:30:00+08:00"
		}`;
		const feedbackExample = `{
			"schema_version": 1,
			"feedback_ref": "fb:20261112-1",
			"matter_ref": "matter:T01",
			"origin": "ask",
			"stage": "response",
			"category": "service-unavailable",
			"raw_reason": "disabled",
			"disable_scope": "single-dp",
			"owner": "WENBOZHOU-PC5:13148",
			"binding": ${hostBindingJson},
			"effect_state": "none",
			"stop_scope": "none"
		}`;
		const selectionExample = `{
			"schema_version": 1,
			"kind": "local-selection",
			"origin": "local-decision",
			"source": "pm",
			"local_ref": "local:T01:1",
			"parent_decision_ref": { "kind": "dp", "decision_id": "dp-auto:2026-11-12T04:00:00Z" },
			"feedback_ref": "fb:20261112-1",
			"matter_ref": "matter:T01",
			"host_binding": ${hostBindingJson},
			"matter_version": "v3",
			"material_digest": "sha256:material",
			"basis_digest": "sha256:basis",
			"selected_action": "continue",
			"selected_basis_id": "b1",
			"budget_ref": "budget:T01",
			"action_state": "planned",
			"business_completed": false,
			"result_consumer": "pm-orchestrator:ack",
			"created_at": "2026-11-12T12:30:00+08:00"
		}`;
		const executionExample = `{
			"schema_version": 1,
			"kind": "local-execution",
			"origin": "local-decision",
			"source": "pm",
			"local_ref": "local:T01:1",
			"host_binding": ${hostBindingJson},
			"action_ref": "tool_call:read:7",
			"result_ref": "tool_result:read:7",
			"executor": "pm-orchestrator",
			"target_digest": "sha256:target",
			"observed_effect": "two reads recorded",
			"effect_state": "known",
			"verified_by": "target-verifier:1",
			"budget_ref": "budget:T01",
			"created_at": "2026-11-12T12:30:00+08:00"
		}`;
		const budgetExample = `{
			"schema_version": 1,
			"budget_ref": "budget:T01",
			"matter_ref": "matter:T01",
			"parent_matter_ref": "matter:parent",
			"deadline": "2026-11-12T13:00:00+08:00",
			"max_steps": 3,
			"no_progress_limit": 2,
			"remaining_cost": 5,
			"steps_consumed": 1,
			"cost_consumed": 1,
			"no_progress_count": 0,
			"source_refs": ["tasks/T01-local-contract.md:timeout=90", "run.json:remaining"]
		}`;
		expect(parseDecisionFeedback(JSON.parse(feedbackExample)).ok).toBe(true);
		expect(parseLocalSelectionRecord(JSON.parse(selectionExample)).ok).toBe(true);
		expect(parseLocalExecutionRecord(JSON.parse(executionExample)).ok).toBe(true);
		expect(validateMatterBudget(JSON.parse(budgetExample)).ok).toBe(true);
		expect(parseDecisionRef(JSON.parse(`{"kind":"dp","decision_id":"dp-auto:2026-11-12T04:00:00Z"}`)).ok).toBe(true);
		expect(parseDecisionRef(JSON.parse(`{"kind":"local","local_ref":"local:T01:1"}`)).ok).toBe(true);
	});
});

// ── T01-R1: PM's 14 independent L1 counter-examples + adjacent boundaries ──

function probeBinding(overrides: Partial<HostBinding> = {}): HostBinding {
	return {
		role: "pm",
		owner: "window:1",
		claim_id: "claim:1",
		key: "key-a",
		binding_version: "v1",
		observed_at: NOW,
		...overrides,
	};
}

function probeSelection(host_binding: HostBinding = probeBinding()): LocalSelectionRecordV1 {
	return {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		kind: "local-selection",
		origin: "local-decision",
		source: "pm",
		local_ref: "local:probe",
		matter_ref: "matter:1",
		host_binding,
		matter_version: "v1",
		material_digest: "material",
		basis_digest: "basis",
		selected_action: "continue",
		selected_basis_id: "b1",
		budget_ref: "budget:1",
		action_state: "planned",
		business_completed: false,
		created_at: NOW,
	};
}

function probeBudget(): MatterBudgetV1 {
	return {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		budget_ref: "budget:1",
		matter_ref: "matter:1",
		deadline: DEADLINE,
		max_steps: 3,
		no_progress_limit: 2,
		remaining_cost: 5,
		steps_consumed: 1,
		cost_consumed: 1,
		no_progress_count: 1,
		source_refs: ["synthetic:probe"],
	};
}

function probeAttempt(proposed: unknown): BudgetRefreshAttempt {
	return {
		reason: "new-turn",
		matter_ref: "matter:1",
		child_matter_ref: "matter:child",
		proposed_budget: proposed as MatterBudgetV1,
	};
}

function probeClassify(kinds: StopSignalKind[], extras: Partial<HostFacts> = {}): DecisionFeedback {
	return classify(
		{ available: false, unavailable: "timeout" },
		{
			binding: probeBinding(),
			stop_signals: kinds.map((kind, index) => ({ signal_ref: `s:${index}`, kind })),
			...extras,
		},
	);
}

describe("T01-R1 contract repair regressions (PM 14 L1 probes + adjacent boundaries)", () => {
	it("1-3: inherited Object.prototype / unknown reasons stay unclassified in both mapping branches", () => {
		for (const reason of ["toString", "__proto__", "constructor"]) {
			for (const raw of [
				{ available: false, unavailable: reason },
				{ available: false, raw_reason: reason },
				{ error: reason },
				reason,
			]) {
				const feedback = classify(untrusted(raw));
				expect(feedback.category).toBe("unclassified");
				expect(typeof feedback.category).toBe("string");
				expect(FEEDBACK_CATEGORIES).toContain(feedback.category);
				expect(feedback.raw_reason).toBe(reason);
			}
			expect(classify({ available: false, unavailable: reason }).raw_payload).toEqual({
				available: false,
				unavailable: reason,
			});
		}
		expect(classify({ available: false, unavailable: "timeout" }).category).toBe("service-unavailable");
		expect(classify({ available: false, unavailable: "input-incomplete" }).category).toBe("input-gap");
	});

	it("4: trusted unknown effect dominates a contradictory raw effect_state=known", () => {
		const feedback = classify(
			{ available: false, unavailable: "timeout", effect_state: "known" },
			hostFacts({ effect_unknown: { action_ref: "tool:1" } }),
		);
		expect(feedback.category).toBe("effect-unknown");
		expect(feedback.effect_state).toBe("unknown");
		expect(feedback.raw_payload).toEqual({ available: false, unavailable: "timeout", effect_state: "known" });
		expect(feedback.untrusted_signals).toContain("effect-known-claim");
		expect(parseDecisionFeedback(JSON.parse(JSON.stringify(feedback))).ok).toBe(true);
		const rawUnknown = classify({
			available: false,
			unavailable: "timeout",
			effect_state: "known",
			side_effect: "unknown",
		});
		expect(rawUnknown.category).toBe("effect-unknown");
		expect(rawUnknown.effect_state).toBe("unknown");
		const cancelled = classify(
			{ available: false, unavailable: "timeout", effect_state: "known" },
			hostFacts({ stop_signals: [{ signal_ref: "u:1", kind: "user-stop" }] }),
		);
		expect(cancelled.category).toBe("cancelled");
		expect(cancelled.effect_state).toBe("unknown");
	});

	it("5-8: every binding identity coordinate + absent/present drift is rejected; success stays shape-only", () => {
		const record = probeSelection();
		const clean = compareLocalSelectionToHost(record, { binding: probeBinding() });
		expect(clean.ok).toBe(true);
		if (clean.ok) {
			expect(clean.host_source_verified).toBe(false);
			expect(clean.verification).toBe("shape-only");
		}
		const drifted: Partial<HostBinding>[] = [
			{ owner: "window:2" },
			{ role: "coding" },
			{ claim_id: "claim:2" },
			{ key: "key-b" },
			{ task_key: "task:other" },
			{ run_id: "run:other" },
			{ binding_version: "v2" },
		];
		for (const patch of drifted) {
			expect(compareLocalSelectionToHost(record, { binding: probeBinding(patch) }).ok).toBe(false);
		}
		const withCoords = probeSelection(probeBinding({ task_key: "task:1", run_id: "run:1" }));
		expect(compareLocalSelectionToHost(withCoords, { binding: probeBinding() }).ok).toBe(false);
		expect(
			compareLocalSelectionToHost(withCoords, { binding: probeBinding({ task_key: "task:1", run_id: "run:1" }) }).ok,
		).toBe(true);
		expect(
			compareLocalSelectionToHost(record, { binding: probeBinding({ observed_at: "2026-11-12T12:59:00+08:00" }) })
				.ok,
		).toBe(true);
	});

	it("9-11: budget rebind / reassociation / limit increases / counter resets rejected; finite consumption allowed", () => {
		const parent = probeBudget();
		const patches: Partial<MatterBudgetV1>[] = [
			{ no_progress_limit: 100 },
			{ budget_ref: "budget:new" },
			{ matter_ref: "matter:other" },
			{ parent_matter_ref: "matter:other-parent" },
			{ max_steps: 4 },
			{ remaining_cost: 6 },
			{ deadline: "2026-11-12T14:00:00+08:00" },
			{ steps_consumed: 0 },
			{ cost_consumed: 0 },
			{ no_progress_count: 0 },
		];
		for (const patch of patches) {
			const result = evaluateBudgetContinuation(parent, probeAttempt({ ...parent, ...patch }), NOW);
			expect(result.allowed).toBe(false);
			expect(result.budget_refreshed).toBe(false);
		}
		const legit = evaluateBudgetContinuation(
			parent,
			probeAttempt({ ...parent, steps_consumed: 2, cost_consumed: 2, remaining_cost: 4, no_progress_count: 2 }),
			NOW,
		);
		expect(legit.allowed).toBe(true);
		expect(legit.reason).toBe("unchanged");
		expect(legit.budget_refreshed).toBe(false);
	});

	it("non-finite / malformed runtime budget values cannot bypass via NaN comparisons", () => {
		const parent = probeBudget();
		const bad: unknown[] = [
			{ ...parent, remaining_cost: Number.NaN },
			{ ...parent, max_steps: Number.NaN },
			{ ...parent, no_progress_limit: Number.POSITIVE_INFINITY },
			{ ...parent, steps_consumed: Number.NaN },
			{ ...parent, cost_consumed: Number.POSITIVE_INFINITY },
			{ ...parent, remaining_cost: "6" },
			{ ...parent, max_steps: 2.5 },
			{ ...parent, no_progress_limit: -1 },
			{ ...parent, deadline: "not-a-date" },
			{ ...parent, source_refs: [] },
			null,
			"not-an-object",
		];
		for (const proposed of bad) {
			const result = evaluateBudgetContinuation(parent, probeAttempt(proposed), NOW);
			expect(result.allowed).toBe(false);
			expect(result.reason).toBe("invalid-budget");
		}
		expect(
			evaluateBudgetContinuation({ ...parent, remaining_cost: Number.NaN }, probeAttempt(parent), NOW).reason,
		).toBe("invalid-budget");
		expect(evaluateBudgetContinuation(parent, probeAttempt(parent), "not-a-date").reason).toBe("invalid-now");
	});

	it("12-13: stops rank by real scope, not array order; authority/exemption diagnostics cannot mask them", () => {
		expect(probeClassify(["parent-cancel", "user-stop"]).stop_scope).toBe("user-global");
		expect(probeClassify(["user-stop", "parent-cancel"]).stop_scope).toBe("user-global");
		expect(probeClassify(["service-timeout", "key-budget"]).stop_scope).toBe("pm-or-key");
		expect(probeClassify(["key-budget", "service-timeout"]).stop_scope).toBe("pm-or-key");
		expect(probeClassify(["service-timeout", "worker-deadline"]).stop_scope).toBe("worker-run");
		expect(probeClassify(["worker-deadline", "service-timeout"]).stop_scope).toBe("worker-run");
		expect(probeClassify(["key-budget"], { authority_gap: { policy_ref: "p:1", condition: "c" } }).category).toBe(
			"budget-exhausted",
		);
		expect(
			probeClassify(["user-stop"], { exemption: { config_ref: "c:1", kind: "signoff-disabled" } }).stop_scope,
		).toBe("user-global");
		const serviceFact = { budget_ref: "b:svc", scope: "service" } as const;
		const taskFact = { budget_ref: "b:task", scope: "task" } as const;
		for (const facts of [
			[serviceFact, taskFact],
			[taskFact, serviceFact],
		]) {
			const feedback = classify(
				{ available: false, unavailable: "timeout" },
				{ binding: probeBinding(), budget_facts: facts },
			);
			expect(feedback.stop_scope).toBe("matter");
			expect(feedback.budget_fact?.scope).toBe("task");
		}
	});

	it("14 + applicability: global/key stops forbid new work; worker deadline only stops its worker; service-only stop does not", () => {
		const stopped = (kind: StopSignalKind) => hostFacts({ stop_signals: [{ signal_ref: "s:1", kind }] });
		expect(
			compareLocalSelectionToHost(probeSelection(), {
				binding: probeBinding(),
				stop_signals: [{ signal_ref: "k:1", kind: "key-budget" }],
			}).ok,
		).toBe(false);
		expect(validateLocalBusinessSelection(selectionInput({ host: stopped("key-budget") })).ok).toBe(false);
		expect(validateLocalBusinessSelection(selectionInput({ host: stopped("user-stop") })).ok).toBe(false);
		expect(validateCollectEvidenceDisposition(collectInput({ host: stopped("user-stop") })).ok).toBe(false);
		expect(validateCollectEvidenceDisposition(collectInput({ host: stopped("key-budget") })).ok).toBe(false);
		expect(validateCollectEvidenceDisposition(collectInput({ host: stopped("service-timeout") })).ok).toBe(true);
		expect(validateCollectEvidenceDisposition(collectInput({ host: stopped("worker-deadline") })).ok).toBe(true);
		expect(validateLocalBusinessSelection(selectionInput({ host: stopped("worker-deadline") })).ok).toBe(true);
		const workerBinding = binding({ role: "coding", task_key: "task:1", run_id: "run:1" });
		expect(
			validateLocalBusinessSelection(
				selectionInput({ source: "worker-local", host: hostFacts({ binding: workerBinding }) }),
			).ok,
		).toBe(true);
		expect(
			validateLocalBusinessSelection(
				selectionInput({
					source: "worker-local",
					host: hostFacts({
						binding: workerBinding,
						stop_signals: [{ signal_ref: "w:1", kind: "worker-deadline" }],
					}),
				}),
			).ok,
		).toBe(false);
		expect(
			validateCollectEvidenceDisposition(
				collectInput({ host: hostFacts({ budget_facts: [{ budget_ref: "b:task", scope: "task" }] }) }),
			).ok,
		).toBe(false);
		expect(
			validateCollectEvidenceDisposition(
				collectInput({ host: hostFacts({ budget_facts: [{ budget_ref: "b:svc", scope: "service" }] }) }),
			).ok,
		).toBe(true);
		// Pure read-only shape checks / classification stay available under a stop:
		// the later host writer owns the dedicated wrap-up path, not this API.
		expect(parseLocalSelectionRecord(JSON.parse(JSON.stringify(probeSelection()))).ok).toBe(true);
		expect(validateMatterBudget(JSON.parse(JSON.stringify(probeBudget()))).ok).toBe(true);
		expect(classify({ available: false, unavailable: "timeout" }, stopped("user-stop")).category).toBe("cancelled");
	});
});
