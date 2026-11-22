/**
 * T15-M3C: trusted independent CURRENT review -> local QG PASS.
 *
 * FIXTURE BOUNDARY (read before interpreting results):
 *  - The producer under test is the REAL `readCurrentIndependentReview` and the
 *    consumer is the REAL `evaluateLocalQg`. They read a REAL `_index.parallel`,
 *    real card/envelope/run.json bytes, real O_EXCL-free reads, and the real
 *    `readRuntimeAuthority` verifier (card pin, live claim, role, run status).
 *  - The review run itself is an AUTHOR-built fixture (run.json + envelope +
 *    pinned card copy + verdict artifact). It is NOT evidence that a native
 *    reviewer/worker ran, and it is NOT a business or Done result. It only
 *    exercises the producer/consumer/validator branches with production-shaped
 *    inputs, exactly as the negative cases exercise their refusals.
 *  - No store/gate/sign/Done product is written; `qg_pass` never releases a gate
 *    and never writes a sign-off.
 */

import { createHash } from "node:crypto";
import fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
	evaluateLocalQg,
	LOCAL_QG_VERIFIER,
	type LocalQgInput,
	type LocalQgReview,
	localQgReviewDigest,
} from "../../src/extensions/agent-team-loop/pm/local-qg-consumer.ts";
import { readCurrentIndependentReview } from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import { sha256EolNormalizedBytes } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";

const KEY = "mw-pm-dp-continuity-fixture";
const CLAIM = "WENBOZHOU-PC5:55292";
const IMPLEMENTER_TASK = "T15-M3C-impl-fixture";
const IMPLEMENTER_RUN = `${IMPLEMENTER_TASK}@2026-11-20T06:00:00.000Z`;
const REVIEW_TASK = "T15-M3C-review-fixture";
const REVIEW_RUN = `${REVIEW_TASK}@2026-11-20T06:30:00.000Z`;
const LOCAL_REF = "local:T15-M3C:fixture";
const EXECUTION_REF = "tool_result:tc-1";
const TOOL_CALL_REF = "tool_call:tc-1";
const MATERIAL_DIGEST = createHash("sha256").update("fixture-material").digest("hex");
const BASIS_DIGEST = createHash("sha256").update("fixture-basis").digest("hex");
const EXECUTED_AT = "2026-11-20T06:05:00.000Z";
const REVIEWED_AT = "2026-11-20T06:40:00.000Z";
/** Host judgement instant: after the review, so a legal PASS has both bounds. */
const NOW_MS = Date.parse("2026-11-20T07:00:00.000Z");

const CARD_SOURCE = path.join(
	path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")),
	"..",
	"..",
	"..",
	"..",
	".agenticdoc",
	"mw-pm-dp-continuity",
	"tasks",
	"T06-C-budget.md",
);

let tmp: string;
let root: string;
let cardBytes: Buffer;
let cardSha: string;

function writeReviewFixture(options: { kind?: string; status?: string; exit?: number; artifacts?: boolean } = {}) {
	const taskDir = path.join(root, KEY, "workers", REVIEW_TASK);
	fs.mkdirSync(taskDir, { recursive: true });
	const envelope = [
		"# review envelope",
		"type: review",
		"phase: EXECUTE",
		`card_path: tasks/${KEY}-review-card.md`,
		`card_sha256: ${cardSha}`,
		"",
		"## body",
	].join("\n");
	fs.writeFileSync(path.join(taskDir, "task.md"), envelope, "utf8");
	const run = {
		schema: 1,
		task_key: REVIEW_TASK,
		run_id: REVIEW_RUN,
		owner_key: KEY,
		kind: options.kind ?? "review",
		status: options.status ?? "done",
		started_at: "2026-11-20T06:30:00.000Z",
		exit: options.exit ?? 0,
		artifacts: options.artifacts === false ? [] : ["review-verdict.json"],
		pid: 4242,
	};
	fs.writeFileSync(path.join(taskDir, "run.json"), JSON.stringify(run, null, 2), "utf8");
	return taskDir;
}

function verdictBody(overrides: Record<string, unknown> = {}) {
	return {
		schema_version: 1,
		kind: "independent-review-verdict",
		verdict: "pass",
		reviewer: {
			role: "review",
			task_key: REVIEW_TASK,
			run_id: REVIEW_RUN,
			card_path: `tasks/${KEY}-review-card.md`,
			card_sha256: cardSha,
			reviewer_claim_id: CLAIM,
		},
		bound: {
			owner_key: KEY,
			local_ref: LOCAL_REF,
			execution_ref: EXECUTION_REF,
			tool_call_ref: TOOL_CALL_REF,
			material_digest: MATERIAL_DIGEST,
			basis_digest: BASIS_DIGEST,
			implementer_task_key: IMPLEMENTER_TASK,
			implementer_run_id: IMPLEMENTER_RUN,
		},
		verifier_ref: LOCAL_QG_VERIFIER,
		reviewed_at: REVIEWED_AT,
		findings: ["reviewed AC-004/AC-006 against the current action"],
		unresolved_findings: [] as string[],
		refs: [`${LOCAL_REF}#review`],
		...overrides,
	};
}

function writeVerdict(body: Record<string, unknown>): string {
	const taskDir = path.join(root, KEY, "workers", REVIEW_TASK);
	fs.mkdirSync(taskDir, { recursive: true });
	const file = path.join(taskDir, "review-verdict.json");
	fs.writeFileSync(file, JSON.stringify(body, null, 2), "utf8");
	return file;
}

function expected() {
	return {
		ownerKey: KEY,
		localRef: LOCAL_REF,
		executionRef: EXECUTION_REF,
		toolCallRef: TOOL_CALL_REF,
		materialDigest: MATERIAL_DIGEST,
		basisDigest: BASIS_DIGEST,
		implementerTaskKey: IMPLEMENTER_TASK,
		implementerRunId: IMPLEMENTER_RUN,
	};
}

function produce(reviewerTaskKey = REVIEW_TASK, reviewerRunId = REVIEW_RUN) {
	return readCurrentIndependentReview({
		agenticdocRoot: root,
		key: KEY,
		reviewerTaskKey,
		reviewerRunId,
		clockMs: NOW_MS,
		expected: expected(),
	});
}

function consumerInput(review: LocalQgReview | undefined): LocalQgInput {
	const stage = {
		authority_kind: "user-delegated-duty-pm" as const,
		key: KEY,
		claim_id: CLAIM,
		stage_id: "T15-M3C-stage",
		scope_ref: "scope:T15-M3C",
		matter_ref: "matter:T15-M3C",
		grant_digest: createHash("sha256").update("grant").digest("hex"),
	};
	const host_binding = {
		role: "pm" as const,
		claim_id: CLAIM,
		key: KEY,
		binding_version: "fixture-binding-v1",
		observed_at: EXECUTED_AT,
	};
	const selection = {
		schema_version: 1 as never,
		kind: "local-selection" as const,
		origin: "local-decision" as const,
		source: "pm" as const,
		local_ref: LOCAL_REF,
		matter_ref: stage.matter_ref,
		host_binding,
		matter_version: "matter-v1",
		material_digest: MATERIAL_DIGEST,
		basis_digest: BASIS_DIGEST,
		selected_action: "fixture",
		selected_basis_id: "fixture-basis",
		budget_ref: "fixture-budget",
		action_state: "planned" as const,
		business_completed: false as const,
		created_at: EXECUTED_AT,
	};
	const execution = {
		schema_version: 1 as never,
		kind: "local-execution" as const,
		origin: "local-decision" as const,
		source: "pm" as const,
		local_ref: LOCAL_REF,
		host_binding: { ...host_binding, run_id: IMPLEMENTER_RUN },
		action_ref: TOOL_CALL_REF,
		result_ref: EXECUTION_REF,
		executor: "fixture-executor",
		target_digest: createHash("sha256").update("target").digest("hex"),
		observed_effect: "files-changed=1;business-correctness=unverified",
		effect_state: "known" as const,
		verified_by: "target-verifier:1",
		budget_ref: "fixture-budget",
		created_at: EXECUTED_AT,
	};
	const observation = {
		tool_call_id: TOOL_CALL_REF,
		local_ref: LOCAL_REF,
		result_ref: EXECUTION_REF,
		executor: "fixture-executor",
		run_id: IMPLEMENTER_RUN,
		is_error: false,
		completion: "complete" as const,
	};
	return { stage, selection, execution, observation, review, nowMs: NOW_MS };
}

/** A review record the way an EDITOR/model would author it: no provenance. */
function selfAuthoredReview(): LocalQgReview {
	const body = {
		origin: "independent-review" as const,
		verdict: "pass" as const,
		selection_ref: LOCAL_REF,
		execution_ref: EXECUTION_REF,
		tool_call_ref: TOOL_CALL_REF,
		verifier_ref: LOCAL_QG_VERIFIER,
		reviewed_at: REVIEWED_AT,
		findings: ["looks good"],
		unresolved_findings: [],
		refs: [`${LOCAL_REF}#review`],
	};
	return { ...body, source_digest: localQgReviewDigest(body) };
}

beforeEach(() => {
	tmp = fs.mkdtempSync(path.join(os.tmpdir(), "t15-m3c-qg-"));
	root = path.join(tmp, ".agenticdoc");
	fs.mkdirSync(path.join(root, KEY, "tasks"), { recursive: true });
	cardBytes = fs.readFileSync(CARD_SOURCE);
	cardSha = sha256EolNormalizedBytes(cardBytes);
	fs.writeFileSync(path.join(root, KEY, "tasks", `${KEY}-review-card.md`), cardBytes);
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		"# Index Parallel\n| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |\n" +
			"| --- | --- | --- | --- | --- | --- | --- |\n" +
			`| ${KEY} | active | EXECUTE | ${CLAIM} |  |  | 2026-11-20T06:00:00Z |\n`,
		"utf8",
	);
	fs.writeFileSync(path.join(root, "_index.md"), "# AgenticTask Index\n\nactive_keys: []\n", "utf8");
});

afterEach(() => {
	fs.rmSync(tmp, { recursive: true, force: true });
});

describe("T15-M3C current independent review producer", () => {
	it("produces a current review from a real dispatched review run and yields a QG PASS", () => {
		writeReviewFixture();
		writeVerdict(verdictBody());
		const read = produce();
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		expect(read.value.verdict).toBe("pass");
		expect(read.value.provenance?.reviewer_run_id).toBe(REVIEW_RUN);
		expect(read.value.provenance?.implementer_run_id).toBe(IMPLEMENTER_RUN);
		const disposition = evaluateLocalQg(consumerInput(read.value));
		expect(disposition.verdict).toBe("pass");
		expect(disposition.qg_pass).toBe(true);
		// A QG PASS is NOT a completed delivery, a gate release or a sign-off.
		expect(disposition.business_completed).toBe(false);
		expect(disposition.gate_released).toBe(false);
		expect(disposition.sign_written).toBe(false);
		expect(disposition.result_consumer).toBe("owning-pm:sign");
	});

	it("refuses a self-run (reviewer == implementer) without reading any artifact", () => {
		writeReviewFixture();
		writeVerdict(verdictBody());
		const read = produce(IMPLEMENTER_TASK, IMPLEMENTER_RUN);
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("review.identity");
	});

	it("refuses a run whose kind is not review", () => {
		writeReviewFixture({ kind: "coding" });
		writeVerdict(verdictBody());
		const read = produce();
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("review.role");
	});

	it("refuses an unfinished review run", () => {
		writeReviewFixture({ status: "running", exit: undefined as never });
		writeVerdict(verdictBody());
		const read = produce();
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("review.terminal");
	});

	it("refuses a verdict the run record never listed as a terminal artifact", () => {
		writeReviewFixture({ artifacts: false });
		writeVerdict(verdictBody());
		const read = produce();
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("review.artifact");
	});

	it("refuses a forged card pin in the verdict", () => {
		writeReviewFixture();
		const body = verdictBody();
		(body.reviewer as Record<string, unknown>).card_sha256 = "f".repeat(64);
		writeVerdict(body);
		const read = produce();
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("review.provenance");
	});

	it("refuses a verdict bound to a different action", () => {
		writeReviewFixture();
		const body = verdictBody();
		(body.bound as Record<string, unknown>).local_ref = "local:other";
		writeVerdict(body);
		const read = produce();
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("review.bound");
	});

	it("refuses a missing verdict artifact", () => {
		writeReviewFixture();
		const read = produce();
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("review.artifact");
	});
});

describe("T15-M3C current QG consumer", () => {
	it("a verified current PASS still releases no gate and writes no sign", () => {
		writeReviewFixture();
		writeVerdict(verdictBody());
		const read = produce();
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		const disposition = evaluateLocalQg(consumerInput(read.value));
		expect(disposition.qg_pass).toBe(true);
		expect(disposition.gate_released).toBe(false);
		expect(disposition.sign_written).toBe(false);
		expect(disposition.business_completed).toBe(false);
	});

	it("refuses an edited/model review that claims origin=independent-review but carries no provenance", () => {
		const disposition = evaluateLocalQg(consumerInput(selfAuthoredReview()));
		// A PASS shape without a verified production review run keeps the legacy
		// fail-closed label: the PASS path stays unsupported for it.
		expect(disposition.verdict).toBe("unsupported-pass");
		expect(disposition.qg_pass).toBe(false);
		expect(disposition.gaps).toContain("pass-path-unsupported");
		expect(disposition.gaps).toContain("review-provenance-missing");
	});

	it("refuses a PASS with unresolved findings", () => {
		writeReviewFixture();
		writeVerdict(verdictBody({ unresolved_findings: ["AC-006 evidence not re-read"] }));
		const read = produce();
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		const disposition = evaluateLocalQg(consumerInput(read.value));
		expect(disposition.verdict).toBe("insufficient");
		expect(disposition.gaps).toContain("review-unresolved-findings");
	});

	it("refuses a stale PASS that predates the execution", () => {
		writeReviewFixture();
		writeVerdict(verdictBody({ reviewed_at: "2026-11-20T05:00:00.000Z" }));
		const read = produce();
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		const disposition = evaluateLocalQg(consumerInput(read.value));
		expect(disposition.verdict).toBe("insufficient");
		expect(disposition.gaps).toContain("review-stale");
	});

	it("refuses a review whose verified bytes were edited after the host read them", () => {
		writeReviewFixture();
		writeVerdict(verdictBody());
		const read = produce();
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		const tampered: LocalQgReview = {
			...read.value,
			provenance: { ...read.value.provenance!, artifact_sha256: "e".repeat(64) },
		};
		const disposition = evaluateLocalQg(consumerInput(tampered));
		expect(disposition.verdict).toBe("insufficient");
		expect(disposition.gaps).toContain("business-verification-missing");
	});

	it("keeps a legitimate fix verdict at repair-required with real findings", () => {
		writeReviewFixture();
		writeVerdict(verdictBody({ verdict: "fix", findings: ["AC-006 evidence missing"] }));
		const read = produce();
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		const disposition = evaluateLocalQg(consumerInput(read.value));
		expect(disposition.verdict).toBe("repair-required");
		expect(disposition.findings).toEqual(["AC-006 evidence missing"]);
		expect(disposition.qg_pass).toBe(false);
	});

	// ── M3E: forged-provenance / currentness negatives ───────────────────────

	it("refuses a forged complete provenance whose material/basis digests are not the selection's", () => {
		// The whole object below is author-forged, INCLUDING a correctly recomputed
		// source_digest, exactly as a caller with the pure consumer in hand could do.
		// Only the two bound digests differ from the real selection material/basis.
		const forgedBody = {
			origin: "independent-review" as const,
			verdict: "pass" as const,
			selection_ref: LOCAL_REF,
			execution_ref: EXECUTION_REF,
			tool_call_ref: TOOL_CALL_REF,
			verifier_ref: LOCAL_QG_VERIFIER,
			reviewed_at: REVIEWED_AT,
			findings: ["looks fine"],
			unresolved_findings: [],
			refs: [`${LOCAL_REF}#review`],
			provenance: {
				kind: "production-review-run" as const,
				owner_key: KEY,
				review_kind: "review" as const,
				reviewer_task_key: REVIEW_TASK,
				reviewer_run_id: REVIEW_RUN,
				reviewer_card_path: `tasks/${KEY}-review-card.md`,
				reviewer_card_sha256: cardSha,
				artifact_ref: `workers/${REVIEW_TASK}/review-verdict.json`,
				artifact_sha256: "a".repeat(64),
				implementer_task_key: IMPLEMENTER_TASK,
				implementer_run_id: IMPLEMENTER_RUN,
				bound_local_ref: LOCAL_REF,
				bound_execution_ref: EXECUTION_REF,
				bound_tool_call_ref: TOOL_CALL_REF,
				bound_material_digest: createHash("sha256").update("other-material").digest("hex"),
				bound_basis_digest: createHash("sha256").update("other-basis").digest("hex"),
			},
		};
		const forged: LocalQgReview = { ...forgedBody, source_digest: localQgReviewDigest(forgedBody) };
		const disposition = evaluateLocalQg(consumerInput(forged));
		expect(disposition.qg_pass).toBe(false);
		expect(disposition.verdict).toBe("unsupported-pass");
		expect(disposition.gaps).toContain("review-provenance-missing");
	});

	it("refuses a forged provenance whose reviewer is the implementer task", () => {
		writeReviewFixture();
		writeVerdict(verdictBody());
		const read = produce();
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		const selfProvenance: LocalQgReview = {
			...read.value,
			provenance: { ...read.value.provenance!, implementer_task_key: REVIEW_TASK },
		};
		const body = { ...selfProvenance } as Record<string, unknown>;
		delete body.source_digest;
		const disposition = evaluateLocalQg(
			consumerInput({ ...selfProvenance, source_digest: localQgReviewDigest(body as never) }),
		);
		expect(disposition.qg_pass).toBe(false);
		expect(disposition.verdict).toBe("unsupported-pass");
	});

	it("refuses a review dated after the host clock", () => {
		writeReviewFixture();
		writeVerdict(verdictBody({ reviewed_at: "2026-11-20T07:30:00.000Z" }));
		// The producer's own clock is later than the verdict, so the reader accepts
		// the bytes; the JUDGEMENT clock is still earlier than the review instant.
		const read = readCurrentIndependentReview({
			agenticdocRoot: root,
			key: KEY,
			reviewerTaskKey: REVIEW_TASK,
			reviewerRunId: REVIEW_RUN,
			clockMs: Date.parse("2026-11-20T07:45:00.000Z"),
			expected: expected(),
		});
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		const disposition = evaluateLocalQg(consumerInput(read.value));
		expect(disposition.verdict).toBe("insufficient");
		expect(disposition.gaps).toContain("review-future");
	});

	it("refuses a PASS when no host clock bounds the review instant", () => {
		writeReviewFixture();
		writeVerdict(verdictBody());
		const read = produce();
		expect(read.ok).toBe(true);
		if (!read.ok) return;
		const disposition = evaluateLocalQg({ ...consumerInput(read.value), nowMs: undefined });
		expect(disposition.qg_pass).toBe(false);
		expect(disposition.gaps).toContain("review-currentness-unbounded");
	});

	it("the producer refuses a verdict dated after its own host clock", () => {
		writeReviewFixture();
		writeVerdict(verdictBody());
		const read = readCurrentIndependentReview({
			agenticdocRoot: root,
			key: KEY,
			reviewerTaskKey: REVIEW_TASK,
			reviewerRunId: REVIEW_RUN,
			clockMs: Date.parse("2026-11-20T06:35:00.000Z"),
			expected: expected(),
		});
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("review.future");
	});
});
