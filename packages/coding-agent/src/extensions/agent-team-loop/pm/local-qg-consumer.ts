/** T15-J explicit typed LOCAL QG consumer.
 *
 *  It separates three different facts that a frozen store never conflates:
 *   1. `local-selection` is a PLANNED choice (`business_completed:false`);
 *   2. `local-execution` + a REAL host tool_call/tool_result observation is an
 *      actual, target-verified effect — a byte manifest is NOT business proof;
 *   3. an independent, current-ref business review is the ONLY possible QG
 *      verification input. PARTIAL / empty / byte-only / selection-only results
 *      cannot release a gate or produce a QG PASS.
 *
 *  A PASS is possible ONLY from a provenance-bearing production review, i.e. a
 *  separate dispatched review run whose verified card/run/terminal artifact is
 *  bound to this exact local_ref/execution/tool_call. An editable blob that
 *  merely says `origin=independent-review` (or a PM self-review) carries no
 *  provenance and stays refused. Nothing here writes an execution, gate,
 *  sign-off, PASS or Done record; `business_completed` and `gate_released` stay
 *  false even for a legal QG PASS -- a PASS is not a gate release or a sign.
 */

import { createHash } from "node:crypto";
import type { LocalExecutionRecordV1, LocalSelectionRecordV1 } from "../shared/decision-handoff.ts";

export const LOCAL_QG_VERIFIER = "independent-review:current-refs@local-qg-consumer-v1";

export interface LocalQgStageSource {
	authority_kind: "user-delegated-duty-pm";
	key: string;
	claim_id: string;
	stage_id: string;
	scope_ref: string;
	matter_ref: string;
	grant_digest: string;
}

/** Host-owned observation captured from real tool_call/tool_result events. */
export interface LocalQgExecutionObservation {
	tool_call_id: string;
	local_ref: string;
	result_ref: string;
	executor: string;
	run_id: string;
	is_error: boolean;
	completion: "complete" | "unknown";
}

/** Typed independent-review fact. `source_digest` binds the CURRENT findings to
 *  this exact selection/execution; PARTIAL is never silently upgraded to pass. */
export interface LocalQgReview {
	origin: "independent-review";
	verdict: "fix" | "partial" | "pass" | "empty";
	selection_ref: string;
	execution_ref: string;
	tool_call_ref: string;
	verifier_ref: string;
	reviewed_at: string;
	findings: string[];
	/** Host-verified unresolved findings. Any entry keeps a PASS refused: an
	 *  unresolved finding is not a completed business verification. Absent is
	 *  treated as none, never as an implicit PASS. */
	unresolved_findings?: string[];
	refs: string[];
	/** Host-verified provenance of the separate review run that produced this
	 *  verdict. Absent for edited/model-authored review text: no trust bootstrap. */
	provenance?: LocalQgReviewProvenance;
	source_digest: string;
}

/** Facts a host producer re-derived from the REVIEWER's real dispatch: its own
 *  task card pin, its run record and its terminal verdict artifact. The
 *  consumer cannot re-read files, so it checks that this shape binds exactly
 *  THIS selection/execution and that the reviewer is a genuinely distinct
 *  review run -- never the implementer and never the PM itself. */
export interface LocalQgReviewProvenance {
	kind: "production-review-run";
	owner_key: string;
	review_kind: "review";
	reviewer_task_key: string;
	reviewer_run_id: string;
	reviewer_card_path: string;
	reviewer_card_sha256: string;
	artifact_ref: string;
	artifact_sha256: string;
	implementer_task_key: string;
	implementer_run_id: string;
	bound_local_ref: string;
	bound_execution_ref: string;
	bound_tool_call_ref: string;
	bound_material_digest: string;
	bound_basis_digest: string;
}

export interface LocalQgInput {
	stage: LocalQgStageSource | undefined;
	selection: LocalSelectionRecordV1 | undefined;
	execution: LocalExecutionRecordV1 | undefined;
	observation: LocalQgExecutionObservation | undefined;
	review: LocalQgReview | undefined;
	/** Host clock at judgement time. Without a finite current instant no upper
	 *  bound exists, so a future/backdated `reviewed_at` could pose as current
	 *  and the PASS path stays refused. Optional so an older caller still
	 *  compiles -- and then gets a fail-closed gap instead of a PASS. */
	nowMs?: number | undefined;
}

export type LocalQgVerdict = "pass" | "repair-required" | "insufficient" | "unsupported-pass";

export interface LocalQgDisposition {
	verdict: LocalQgVerdict;
	/** A legal review (fix/partial/pass) is NOT a completed delivery.
	 *  `qg_pass` is true only for a provenance-bearing current PASS; a PASS still
	 *  releases no gate and writes no sign-off. */
	business_completed: false;
	qg_pass: boolean;
	gate_released: false;
	sign_written: false;
	source_kind: "user-delegated-duty-pm" | "missing";
	selection_ref?: string;
	execution_ref?: string;
	target_verifier: typeof LOCAL_QG_VERIFIER;
	result_consumer: "owning-pm:repair" | "owning-pm:sign";
	findings: string[];
	basis_refs: string[];
	gaps: string[];
	reason: string;
}

function stableJson(value: unknown): string {
	if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
	if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
	const record = value as Record<string, unknown>;
	return `{${Object.keys(record)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`)
		.join(",")}}`;
}

/** Digest of the CURRENT review facts, never of a copied/old report. */
export function localQgReviewDigest(review: Omit<LocalQgReview, "source_digest">): string {
	return createHash("sha256").update(stableJson(review)).digest("hex");
}

function nonblank(value: unknown): value is string {
	return typeof value === "string" && value.trim() !== "";
}
/** Normalized non-empty digest, or `undefined`: an absent digest cannot equal
 *  an expected one and must never be compared as the empty string. */
function digestOf(value: unknown): string | undefined {
	return typeof value === "string" && value.trim() !== "" ? value.trim().toLowerCase() : undefined;
}
function iso(value: unknown): boolean {
	return (
		typeof value === "string" &&
		Number.isFinite(Date.parse(value)) &&
		/^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(value)
	);
}

function result(
	verdict: LocalQgVerdict,
	reason: string,
	gaps: string[],
	input: LocalQgInput,
	findings: string[] = [],
): LocalQgDisposition {
	const qgPass = verdict === "pass";
	const refs = [
		input.selection?.local_ref,
		input.execution?.action_ref,
		input.execution?.result_ref,
		...(input.review?.refs ?? []),
	].filter((ref): ref is string => typeof ref === "string" && ref !== "");
	return {
		verdict,
		business_completed: false,
		qg_pass: qgPass,
		gate_released: false,
		sign_written: false,
		source_kind: input.stage === undefined ? "missing" : "user-delegated-duty-pm",
		...(input.selection === undefined ? {} : { selection_ref: input.selection.local_ref }),
		...(input.execution === undefined ? {} : { execution_ref: input.execution.result_ref }),
		target_verifier: LOCAL_QG_VERIFIER,
		result_consumer: qgPass ? "owning-pm:sign" : "owning-pm:repair",
		findings: [...new Set(findings)],
		basis_refs: [...new Set(refs)],
		gaps,
		reason,
	};
}

/** Pure typed judgement. Every input is a host-owned fact; model report text is
 *  never promoted to source, execution or business verification. */
export function evaluateLocalQg(input: LocalQgInput): LocalQgDisposition {
	const stage = input.stage;
	if (
		stage === undefined ||
		stage.authority_kind !== "user-delegated-duty-pm" ||
		!nonblank(stage.key) ||
		!nonblank(stage.claim_id) ||
		!nonblank(stage.stage_id) ||
		!nonblank(stage.scope_ref) ||
		!nonblank(stage.matter_ref) ||
		!/^[a-f0-9]{64}$/.test(stage.grant_digest)
	)
		return result("insufficient", "no trusted PM stage source", ["stage-source-missing"], input);
	const selection = input.selection;
	if (
		selection === undefined ||
		selection.kind !== "local-selection" ||
		selection.source !== "pm" ||
		selection.action_state !== "planned" ||
		selection.business_completed !== false ||
		selection.host_binding.role !== "pm" ||
		selection.host_binding.key !== stage.key ||
		selection.host_binding.claim_id !== stage.claim_id ||
		!nonblank(selection.local_ref)
	)
		return result("insufficient", "no current verified PLANNED selection", ["planned-selection-missing"], input);
	const execution = input.execution;
	const observation = input.observation;
	if (execution === undefined || observation === undefined)
		return result(
			"insufficient",
			"selection/planned is not business completion; no gate release from a selection or empty result",
			["selection-only-no-release", "business-result-empty"],
			input,
		);
	if (
		execution.kind !== "local-execution" ||
		execution.effect_state !== "known" ||
		execution.action_ref !== observation.tool_call_id ||
		execution.result_ref !== observation.result_ref ||
		execution.local_ref !== selection.local_ref ||
		execution.executor !== observation.executor ||
		observation.local_ref !== selection.local_ref ||
		observation.is_error ||
		observation.completion !== "complete" ||
		!nonblank(execution.verified_by) ||
		!nonblank(execution.observed_effect)
	)
		return result(
			"insufficient",
			"no correlated real host tool_call/tool_result execution",
			["execution-unproven"],
			input,
		);
	const review = input.review;
	if (
		review === undefined ||
		review.verdict === "empty" ||
		review.findings.length === 0 ||
		review.refs.length === 0 ||
		review.findings.some((finding) => !nonblank(finding)) ||
		review.refs.some((ref) => !nonblank(ref))
	)
		return result(
			"insufficient",
			"empty business result cannot release the QG gate",
			["empty-result-no-release"],
			input,
		);
	const digestInput = { ...review } as Record<string, unknown>;
	delete digestInput.source_digest;
	if (
		review.origin !== "independent-review" ||
		!iso(review.reviewed_at) ||
		review.verifier_ref !== LOCAL_QG_VERIFIER ||
		review.selection_ref !== selection.local_ref ||
		review.execution_ref !== execution.result_ref ||
		review.tool_call_ref !== execution.action_ref ||
		review.source_digest !== createHash("sha256").update(stableJson(digestInput)).digest("hex") ||
		!execution.observed_effect.includes("business-correctness=unverified")
	)
		return result(
			"insufficient",
			"business review is not an independent current-ref verification of this exact action; byte proof is not QG verification",
			["business-verification-missing", "byte-proof-not-business-verification"],
			input,
		);
	const provenance = review.provenance;
	// The provenance digests are only meaningful when they equal the digests of
	// the selection/material/basis this judgement is actually about: a provider
	// that merely carries two non-empty hashes proves no binding at all.
	const materialDigest = digestOf(selection.material_digest);
	const basisDigest = digestOf(selection.basis_digest);
	// Provenance gates the PASS upgrade only. A fix/partial review already grants
	// nothing (FIX grants nothing either), so a provenance-less fix review must
	// still reach repair-required with its real findings; only an ASCENT to PASS
	// needs a separate production review run. A fix/partial PASS-shaped verdict
	// still cannot release a gate.
	const provenanceOk =
		provenance !== undefined &&
		provenance.kind === "production-review-run" &&
		provenance.review_kind === "review" &&
		nonblank(provenance.owner_key) &&
		provenance.owner_key === stage.key &&
		nonblank(provenance.reviewer_task_key) &&
		nonblank(provenance.reviewer_run_id) &&
		nonblank(provenance.reviewer_card_path) &&
		/^[a-f0-9]{64}$/.test(provenance.reviewer_card_sha256) &&
		nonblank(provenance.artifact_ref) &&
		/^[a-f0-9]{64}$/.test(provenance.artifact_sha256) &&
		nonblank(provenance.implementer_run_id) &&
		provenance.implementer_run_id === observation.run_id &&
		provenance.reviewer_run_id !== observation.run_id &&
		provenance.bound_local_ref === selection.local_ref &&
		provenance.bound_execution_ref === execution.result_ref &&
		provenance.bound_tool_call_ref === execution.action_ref &&
		nonblank(provenance.implementer_task_key) &&
		provenance.reviewer_task_key !== provenance.implementer_task_key &&
		materialDigest !== undefined &&
		basisDigest !== undefined &&
		digestOf(provenance.bound_material_digest) === materialDigest &&
		digestOf(provenance.bound_basis_digest) === basisDigest;
	if (review.verdict === "pass") {
		if (!provenanceOk)
			return result(
				// The PASS path stays UNSUPPORTED for a review that carries no verified
				// separate production run: an edited/model/self review or its digest
				// cannot bootstrap trust, so the legacy fail-closed label is kept.
				"unsupported-pass",
				"the PASS has no verifiable separate production review run bound to this exact action; " +
					"an edited/model/self review or its digest cannot bootstrap trust",
				["pass-path-unsupported", "review-provenance-missing", "self-review-not-business-verification"],
				input,
			);
		if ((review.unresolved_findings ?? []).length !== 0)
			return result(
				"insufficient",
				"a PASS with unresolved findings is not a completed business verification",
				["review-unresolved-findings"],
				input,
				review.findings,
			);
		if (Date.parse(review.reviewed_at) < Date.parse(execution.created_at))
			return result(
				"insufficient",
				"the review predates this execution; a stale review is not a current verification",
				["review-stale"],
				input,
			);
		// Current-ness needs an upper bound as well: a review dated after the host
		// clock is not an observation, and without a real clock it is unverifiable.
		const nowMs = input.nowMs;
		if (typeof nowMs !== "number" || !Number.isFinite(nowMs))
			return result(
				"insufficient",
				"no host clock bounds the review instant; an unbounded timestamp is not current",
				["review-currentness-unbounded"],
				input,
			);
		if (Date.parse(review.reviewed_at) > nowMs)
			return result(
				"insufficient",
				"the review is dated after the host clock; a future review is not a current verification",
				["review-future"],
				input,
			);
		if (Date.parse(execution.created_at) > nowMs)
			return result(
				"insufficient",
				"the execution itself is dated after the host clock; an unverifiable execution is no verification",
				["execution-future"],
				input,
			);
		return result(
			"pass",
			"current independent production review passed this exact action; the owning PM still owns " +
				"gate release and sign-off -- a QG PASS writes neither",
			[],
			input,
			review.findings,
		);
	}
	if (review.verdict !== "fix" && review.verdict !== "partial")
		return result("insufficient", "unsupported business review verdict", ["business-verification-missing"], input);
	return result(
		"repair-required",
		review.verdict === "partial"
			? "PARTIAL independent review requires repair; no QG PASS, gate release or sign"
			: "independent fix review requires repair; no QG PASS, gate release or sign",
		review.verdict === "partial" ? ["partial-review-no-pass"] : [],
		input,
		review.findings,
	);
}
