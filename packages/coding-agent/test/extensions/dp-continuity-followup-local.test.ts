/**
 * T07 — discriminated LOCAL follow-up continuation evidence.
 *
 * FIXTURE BOUNDARY (read before interpreting results):
 *  - Local POSITIVE records are produced ONLY by the real frozen
 *    `LocalSelectionStore.commitSelection` / `appendExecution`. The ONLY host
 *    injection is a `LocalSelectionHostAdapter` (the established trusted-host
 *    boundary): `readTrustedContext` supplies the real live-claim context and
 *    `verifyExecution` supplies a structured `ExecutionProof`. No passing
 *    local-selection/execution/proof/QG record is ever hand-written. Negative
 *    fixtures (forged/corrupt DP-shaped bytes) are deliberately hand-written
 *    into an isolated temp dir and must be REFUSED.
 *  - Real `_index.parallel`, real O_EXCL locks, real tmp/fsync/rename are used.
 *  - Helper positives use fixture-supplied executor/offer certificates and are
 *    NOT ProductionRuntimeHost positives. The M1 describe separately uses a real
 *    registered dispatch, default request, production offer, controlled selection,
 *    harness action/result and unchanged strict runtime verifier.
 *  - No paid/external provider. The native over-cap request targets only an
 *    isolated loopback counter. Parent lifecycle fixtures use the real writer;
 *    LOCAL continuation preserves the failed intent/ledger and never releases
 *    the parent, writes sign-off or marks the key Done.
 */

import childProcess, { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import { createServer, type Server } from "node:http";
import { syncBuiltinESMExports } from "node:module";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai/compat";
import { Type } from "typebox";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { answerPreparedGate } from "../../src/extensions/agent-team-loop/autopilot/gate-writer.ts";
import {
	type DecisionFollowupIntent,
	type ExpectedDecisionFollowup,
	hasDuplicateJsonMembers,
	type LocalExecutionVerdict,
	type LocalFollowupCheckpoint,
	type LocalFollowupIntent,
	type LocalFollowupOwner,
	type LocalFollowupRecords,
	type LocalTrustedExecutorCertificate,
	type LocalTrustedOfferCertificate,
	localFollowupSidecarPath,
	resumeDecisionFollowup,
	sharedFollowupLockPath,
	verifyLocalFollowupEvidence,
} from "../../src/extensions/agent-team-loop/pm/decision-followup.ts";
import { captureDecisionTaskState } from "../../src/extensions/agent-team-loop/pm/decision-task-state.ts";
import {
	registerSubmitDecisionHandoffTool,
	SUBMIT_DECISION_HANDOFF_TOOL,
	type SubmitDecisionHostHandle,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import { registerPmGateFollowup } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	ProductionRuntimeHost,
	RUNTIME_BUDGET_ENTRY_TYPE,
	registerProductionRuntimeEvents,
} from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import { canonicalStateJson } from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import { extractCardSections, windowClaimId } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { sha256EolNormalizedBytes } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import type { DecisionPreparation } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import type { LocalExecutionRecordV1 } from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { readTaskProgress } from "../../src/extensions/agent-team-loop/shared/heartbeat.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import {
	type AppendExecutionRequest,
	type CommitSelectionRequest,
	EXECUTION_FILE_SUFFIX,
	type ExecutionProof,
	type LocalSelectionHostAdapter,
	LocalSelectionStore,
	SELECTION_FILE_SUFFIX,
	storedRecordPath,
	type TrustedHostContext,
} from "../../src/extensions/agent-team-loop/shared/local-selection-store.ts";
import { PYTHON_EXE } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, getMessageText, type Harness } from "../suite/harness.ts";

// ── Fixed, mutually-consistent binding facts ───────────────────────────────

const KEY = "mw-pm-dp-continuity";
const CLAIM = "WENBOZHOU-PC5:13148"; // unique active exact-self row claimId == host_binding.owner/claim_id
const WINDOW = "window-1";
const MATTER = "matter:T07";
const MATTER_VERSION = "mv1";
const MATERIAL_DIGEST = "sha256:material";
const BASIS_DIGEST = "sha256:basis";
const TARGET_DIGEST = "sha256:target";
const PARENT_DP = "dp-gate-approve:gate-v1";
const LOCAL_REF = "local:T07:1";
const RESTRICTED_ACTION = "continue";
const RESTRICTED_EXECUTOR = "pm-orchestrator";
const PARENT_LOGICAL_ID = "11111111-1111-4111-8111-111111111111";
const NOW = new Date().toISOString();
const DEADLINE = new Date(Date.now() + 30 * 60 * 1000).toISOString();

const boundPm = { role: "pm" as const, key: KEY, window_id: WINDOW };

// The eleven original binding fields, computed from real material/preparation.
const expected: ExpectedDecisionFollowup = {
	parent_ref: "gate:matter-v1",
	parent_logical_id: PARENT_LOGICAL_ID,
	parent_decision_id: PARENT_DP,
	parent_matter_version: "matter-v1",
	target_dp: "dp-pm-steer",
	material_version: createHash("sha256").update("material").digest("hex"),
	basis_version: createHash("sha256").update("basis").digest("hex"),
	owner_key: KEY,
	task_key: null,
	restricted_action: RESTRICTED_ACTION,
	restricted_executor: RESTRICTED_EXECUTOR,
};

function ownerFact(overrides: Partial<LocalFollowupOwner> = {}): LocalFollowupOwner {
	return {
		owner_key: KEY,
		claim_id: CLAIM,
		window_id: WINDOW,
		unique_active: true,
		material_digest: MATERIAL_DIGEST,
		basis_digest: BASIS_DIGEST,
		parent_decision_id: PARENT_DP,
		...overrides,
	};
}

interface SourceFacts {
	gateVersion: string;
	business: string;
	effect: string;
	config: string;
	watchKey: string;
	sourceCard: string;
	workerEvidence: string;
	currentOffer: string;
}

let tmp: string;
let root: string;
let intentPath: string;
let sourceFacts: SourceFacts;
let sourceBaseline: string;
let sourceChecks: LocalFollowupCheckpoint[];

function sourceSnapshot(): string {
	return JSON.stringify(sourceFacts);
}

beforeEach(() => {
	tmp = fs.mkdtempSync(path.join(os.tmpdir(), "t07-followup-local-"));
	root = path.join(tmp, ".agenticdoc");
	fs.mkdirSync(root, { recursive: true });
	fs.mkdirSync(path.join(root, "..", ".mw"), { recursive: true });
	sourceFacts = {
		gateVersion: "v1",
		business: "steer",
		effect: "not-started",
		config: "live",
		watchKey: KEY,
		sourceCard: "card-v1",
		workerEvidence: "worker-v1",
		currentOffer: "offer-v1",
	};
	sourceBaseline = sourceSnapshot();
	sourceChecks = [];
	// Real authoritative index: UNIQUE active exact-self row.
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		"# Index Parallel\n| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |\n| --- | --- | --- | --- | --- | --- | --- |\n" +
			`| ${KEY} | active | EXECUTE | ${CLAIM} |  |  | ${NOW} |\n`,
		"utf8",
	);
	fs.writeFileSync(path.join(root, "_index.md"), "# AgenticTask Index\n\nactive_keys: []\n", "utf8");
	intentPath = path.join(tmp, "local-followup.json");
	writeLocalIntent({});
});

afterEach(() => {
	fs.rmSync(tmp, { recursive: true, force: true });
});

// ── Real store fixtures ────────────────────────────────────────────────────

function trustedContext(): TrustedHostContext {
	return {
		self_claim_id: CLAIM,
		binding_version: "v3",
		role: "pm",
		observed_at: NOW,
		expected: {
			matter_ref: MATTER,
			matter_version: MATTER_VERSION,
			material_digest: MATERIAL_DIGEST,
			basis_digest: BASIS_DIGEST,
			budget_ref: "budget:T07",
			parent_decision_id: PARENT_DP,
		},
		budget: {
			schema_version: 1,
			budget_ref: "budget:T07",
			matter_ref: MATTER,
			deadline: DEADLINE,
			max_steps: 8,
			no_progress_limit: 6,
			remaining_cost: 40,
			steps_consumed: 1,
			cost_consumed: 1,
			no_progress_count: 0,
			source_refs: ["tasks/T07-local-followup.md#事项预算事实", "run.json:started_at"],
		},
		budget_preflight: {
			granted: true,
			reserved_steps: 1,
			reserved_cost: 1,
			remaining_after_steps: 7,
			remaining_after_cost: 39,
			reason: "granted",
		},
	};
}

interface AdapterOptions {
	effectState?: "known" | "unknown";
}

/** REAL trusted-host verifier: structured proof, never a boolean/self-report. */
function hostAdapter(opts: AdapterOptions = {}): LocalSelectionHostAdapter {
	const effectState = opts.effectState ?? "known";
	return {
		readTrustedContext: async () => trustedContext(),
		verifyExecution: async (request): Promise<ExecutionProof> => ({
			action_ref: request.action_ref,
			result_ref: request.result_ref,
			verifier_ref: "target-verifier:1",
			target_digest: TARGET_DIGEST,
			observed_effect: request.observed_effect,
			effect_state: effectState,
			local_ref: request.local_ref,
			executor: request.executor,
		}),
	};
}

function selectionFields(
	overrides: Partial<CommitSelectionRequest["selection"]> = {},
): CommitSelectionRequest["selection"] {
	return {
		matter_ref: MATTER,
		matter_version: MATTER_VERSION,
		material: {
			material_ref: "mat:1",
			fields: { task_goal: "g", task_requirements: "r", task_deliverables: "d" },
			digest: MATERIAL_DIGEST,
			evidence_refs: ["card:1"],
		},
		preparation: {
			prepared_at: NOW,
			digest: BASIS_DIGEST,
			basis_catalog: [
				{ id: "b1", text: "basis one", material_refs: ["task_goal"], applies_to: [RESTRICTED_ACTION, "narrow"] },
			],
		},
		candidates: { version: "v1", ids: [RESTRICTED_ACTION, "narrow"] },
		selected_action: RESTRICTED_ACTION,
		selected_basis_id: "b1",
		parent_decision_ref: { kind: "dp", decision_id: PARENT_DP },
		created_at: NOW,
		...overrides,
	} as CommitSelectionRequest["selection"];
}

function execRequest(): AppendExecutionRequest {
	return {
		source: "pm",
		local_ref: LOCAL_REF,
		action_ref: "tool_call:read:7",
		result_ref: "tool_result:read:7",
		executor: RESTRICTED_EXECUTOR,
		observed_effect: "two reads recorded",
		created_at: NOW,
	};
}

function makeStore(adapter: LocalSelectionHostAdapter): LocalSelectionStore {
	return new LocalSelectionStore({
		agenticdoc_root: root,
		key: KEY,
		host_adapter: adapter,
		lock_options: { retries: 16, baseDelayMs: 3 },
	});
}

function selectionFile(): string {
	return storedRecordPath(root, KEY, "pm", undefined, LOCAL_REF, SELECTION_FILE_SUFFIX);
}
function executionFile(): string {
	return storedRecordPath(root, KEY, "pm", undefined, LOCAL_REF, EXECUTION_FILE_SUFFIX);
}

/** Real committed PLANNED selection (no execution). */
async function commitSelection(adapter: LocalSelectionHostAdapter): Promise<void> {
	const store = makeStore(adapter);
	const result = await store.commitSelection({ source: "pm", local_ref: LOCAL_REF, selection: selectionFields() });
	expect(result.code, result.reason).toBe("written");
}

/** Real committed selection + execution, both produced by the frozen store. */
async function commitExecution(
	adapter: LocalSelectionHostAdapter,
	selOverrides: Partial<CommitSelectionRequest["selection"]> = {},
): Promise<void> {
	const store = makeStore(adapter);
	const sel = await store.commitSelection({
		source: "pm",
		local_ref: LOCAL_REF,
		selection: selectionFields(selOverrides),
	});
	expect(sel.code, sel.reason).toBe("written");
	const exe = await store.appendExecution(execRequest());
	expect(exe.code, exe.reason).toBe("written");
}

// ── Local intent (discriminated; never a DP intent) ────────────────────────

/** Fixture-only trusted certificates. They are NOT a production host/runtime
 *  positive: the real registered consumer has no equivalent public API yet. */
function executorCertificate(): LocalTrustedExecutorCertificate {
	return {
		current: true,
		local_ref: LOCAL_REF,
		run_id: "run:t07:fixture",
		tool_call_id: "tool_call:read:7",
		executor: RESTRICTED_EXECUTOR,
	};
}

function offerCertificate(): LocalTrustedOfferCertificate {
	return {
		current: true,
		current_by_matter: true,
		offer_id: "offer:T07:fixture",
		local_ref: LOCAL_REF,
		parent_decision_id: expected.parent_decision_id,
		parent_matter_version: expected.parent_matter_version,
		matter_ref: MATTER,
		matter_version: MATTER_VERSION,
		canonical_material_digest: expected.material_version,
		canonical_catalog_digest: expected.basis_version,
		target_dp: expected.target_dp,
		selected_action: RESTRICTED_ACTION,
		selected_basis_id: "b1",
		basis_applies_to: [RESTRICTED_ACTION],
	};
}

function writeLocalIntent(
	overrides: Partial<LocalFollowupIntent> & { dpField?: string } = {},
	target: string = intentPath,
): void {
	const { dpField, ...rest } = overrides;
	const intent: Record<string, unknown> = {
		schema_version: 1,
		source: "local",
		local_ref: LOCAL_REF,
		local_source: "pm",
		...expected,
		prepared_by: boundPm,
		local_progress: null,
		local_action_evidence: null,
		...rest,
	};
	if (dpField !== undefined) intent[dpField] = "forged";
	fs.writeFileSync(target, `${JSON.stringify(intent, null, 2)}\n`, "utf8");
}

// ── Trusted boundaries for verifyLocalFollowupEvidence ─────────────────────

type VerifierBoundary = (
	execution: LocalExecutionRecordV1,
) => LocalExecutionVerdict | undefined | Promise<LocalExecutionVerdict | undefined>;

interface BoundaryOptions {
	owner?: LocalFollowupOwner | undefined;
	verifier?: VerifierBoundary;
	records?: LocalFollowupRecords;
	intentPath?: string;
	barrier?: (checkpoint: LocalFollowupCheckpoint) => void;
	readCurrentSource?: (checkpoint: LocalFollowupCheckpoint) => boolean;
	executorCertificate?: LocalTrustedExecutorCertificate | undefined;
	offerCertificate?: LocalTrustedOfferCertificate | undefined;
}

function boundaries(opts: BoundaryOptions = {}) {
	const adapter = hostAdapter();
	const store = makeStore(adapter);
	return {
		readRecords: (): LocalFollowupRecords => {
			if (opts.records !== undefined) return opts.records;
			const selection = store.readSelection({ source: "pm", ref: LOCAL_REF });
			const execution = store.readExecution({ source: "pm", ref: LOCAL_REF });
			return {
				selection: selection.status === "ok" ? selection.record : undefined,
				execution: execution.status === "ok" ? execution.record : undefined,
				selection_status: selection.status,
				execution_status: execution.status,
			};
		},
		readCurrentOwner: (): LocalFollowupOwner | undefined => (opts.owner === undefined ? ownerFact() : opts.owner),
		readCurrentSource: (checkpoint: LocalFollowupCheckpoint): boolean => {
			sourceChecks.push(checkpoint);
			opts.barrier?.(checkpoint);
			if (opts.readCurrentSource !== undefined) return opts.readCurrentSource(checkpoint);
			let persistedRef = LOCAL_REF;
			try {
				const row = JSON.parse(fs.readFileSync(opts.intentPath ?? intentPath, "utf8")) as { local_ref?: unknown };
				if (typeof row.local_ref === "string") persistedRef = row.local_ref;
			} catch {
				return false;
			}
			return sourceSnapshot() === sourceBaseline && persistedRef === LOCAL_REF;
		},
		readTrustedExecutor: () =>
			opts.executorCertificate === undefined ? executorCertificate() : opts.executorCertificate,
		readCurrentOffer: () => (opts.offerCertificate === undefined ? offerCertificate() : opts.offerCertificate),
		// REAL independent verifier: the SAME trusted host adapter used by
		// appendExecution re-observes the committed action/result/target effect.
		verifyExecution: async (execution: LocalExecutionRecordV1): Promise<LocalExecutionVerdict | undefined> => {
			if (opts.verifier !== undefined) return opts.verifier(execution);
			const proof = await adapter.verifyExecution?.({
				key: KEY,
				source: "pm",
				local_ref: LOCAL_REF,
				action_ref: execution.action_ref,
				result_ref: execution.result_ref,
				executor: execution.executor,
				observed_effect: execution.observed_effect,
				binding: execution.host_binding,
			});
			if (proof === undefined) return undefined;
			return {
				verifier_ref: proof.verifier_ref,
				target_digest: proof.target_digest,
				observed_effect: proof.observed_effect,
				confirmed: proof.effect_state === "known",
			};
		},
	};
}

function invoke(opts: BoundaryOptions = {}) {
	return verifyLocalFollowupEvidence({
		intent_path: intentPath,
		expected,
		bound_pm: boundPm,
		source: "pm",
		local_ref: LOCAL_REF,
		...boundaries(opts),
	});
}

// ── DP regression (unchanged path; pure cases need no Python/ledger) ───────

function dpFixture(overrides: Partial<DecisionFollowupIntent> = {}): DecisionFollowupIntent {
	return {
		schema_version: 1,
		...expected,
		prepared_by: boundPm,
		status: "prepared",
		request_ref: null,
		answer: null,
		failure_reason: null,
		...overrides,
	};
}

describe("existing DP request/receipt path stays strict", () => {
	it("rejects a changed substantive version without issuing a request", async () => {
		const file = path.join(tmp, "dp.json");
		fs.writeFileSync(file, `${JSON.stringify(dpFixture())}\n`, "utf8");
		let called = 0;
		const out = await resumeDecisionFollowup({
			intent_path: file,
			expected: { ...expected, material_version: "changed" },
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request: () => {
				called += 1;
				return Promise.resolve({ available: false as const, reason: "disabled" });
			},
		});
		expect(out).toMatchObject({ state: "blocked", reason: "version-mismatch", parent_released: false });
		expect(called).toBe(0);
	});

	it("treats a persisted requesting state as crash-unknown", async () => {
		const file = path.join(tmp, "dp.json");
		fs.writeFileSync(file, `${JSON.stringify(dpFixture({ status: "requesting" }))}\n`, "utf8");
		const out = await resumeDecisionFollowup({
			intent_path: file,
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request: () => Promise.resolve({ available: false as const, reason: "disabled" }),
		});
		expect(out).toMatchObject({ state: "unknown", reason: "request-outcome-unknown" });
	});

	it("a local-source file is rejected by the DP parser (discriminated source)", async () => {
		const file = path.join(tmp, "local-as-dp.json");
		fs.writeFileSync(file, `${JSON.stringify({ ...dpFixture(), source: "local" })}\n`, "utf8");
		const out = await resumeDecisionFollowup({
			intent_path: file,
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request: () => Promise.resolve({ available: false as const, reason: "disabled" }),
		});
		expect(out).toMatchObject({ state: "blocked", reason: "intent-invalid" });
	});
});

// ── LOCAL continuation evidence ───────────────────────────────────────────

describe("discriminated local follow-up", () => {
	it("REFUSES a real selection-only record: never executed, never releases the parent", async () => {
		await commitSelection(hostAdapter());
		expect(fs.existsSync(selectionFile())).toBe(true);
		expect(fs.existsSync(executionFile())).toBe(false);
		const out = await invoke();
		expect(out).toMatchObject({
			state: "in-progress",
			reason: "selection-only-no-execution",
			parent_released: false,
			request_started: false,
		});
		expect(out.state).not.toBe("executed");
		expect(out.request_ref).toBeUndefined();
		expect(out.answer).toBeUndefined();
		expect(JSON.parse(fs.readFileSync(intentPath, "utf8")).local_progress).toBe("selected");
		// No DP lifecycle ledger artifact is ever created by the local path.
		expect(fs.existsSync(path.join(root, "..", ".mw", "decision-lifecycle.ndjson"))).toBe(false);
	});

	it("a real, independently verified local successor satisfies continuation evidence WITHOUT a DP receipt", async () => {
		await commitExecution(hostAdapter());
		const out = await invoke();
		expect(out).toMatchObject({
			state: "executed",
			verified_source: "local",
			ref: LOCAL_REF,
			action: RESTRICTED_ACTION,
			parent_released: false,
			duplicate: false,
			local_progress: "verified",
		});
		expect(out.request_ref).toBeUndefined();
		expect(out.answer).toBeUndefined();
		expect(out.basis_id).toBeUndefined();
		expect(out.request_started).toBe(false);
		const persisted = JSON.parse(fs.readFileSync(intentPath, "utf8"));
		expect(persisted.local_progress).toBe("verified");
		for (const dpKey of ["status", "request_ref", "answer", "decision_id", "available", "business_decisions"]) {
			expect(persisted).not.toHaveProperty(dpKey);
		}
	});

	it("is idempotent on repeat (duplicate, no second execution)", async () => {
		await commitExecution(hostAdapter());
		expect((await invoke()).state).toBe("executed");
		const repeat = await invoke();
		expect(repeat).toMatchObject({ state: "executed", duplicate: true, parent_released: false });
	});

	it("a persisted executing state is crash-unknown; a missing/throwing verifier is unknown, not success", async () => {
		await commitExecution(hostAdapter());
		writeLocalIntent({ local_progress: "executing" });
		expect(await invoke()).toMatchObject({ state: "unknown", reason: "local-outcome-unknown" });

		writeLocalIntent({});
		const noVerifier = await invoke({ verifier: () => undefined });
		expect(noVerifier).toMatchObject({ state: "unknown" });
		expect(noVerifier.reason).toContain("missing-interface:verifyExecution");
		expect(noVerifier.state).not.toBe("executed");

		writeLocalIntent({});
		const throwing = await verifyLocalFollowupEvidence({
			intent_path: intentPath,
			expected,
			bound_pm: boundPm,
			source: "pm",
			local_ref: LOCAL_REF,
			...boundaries(),
			verifyExecution: () => {
				throw new Error("verifier down");
			},
		});
		expect(throwing).toMatchObject({ state: "unknown" });
		expect(throwing.state).not.toBe("executed");
	});

	it("a CURRENT binding/owner change after verification refuses the repeat (never a stale executed)", async () => {
		await commitExecution(hostAdapter());
		expect((await invoke()).state).toBe("executed");
		const changedOwner = await invoke({ owner: ownerFact({ claim_id: "WENBOZHOU-PC5:99999" }) });
		expect(changedOwner).toMatchObject({ state: "blocked" });
		expect(changedOwner.state).not.toBe("executed");
		const notUnique = await invoke({ owner: ownerFact({ unique_active: false }) });
		expect(notUnique).toMatchObject({ state: "blocked", reason: "current-owner-not-unique-active" });
	});

	it("a changed owner key, stale material digest, wrong target and unproven verifier all refuse", async () => {
		await commitExecution(hostAdapter());
		const changedKey = await invoke({ owner: ownerFact({ owner_key: "other" }) });
		expect(changedKey).toMatchObject({ state: "blocked", reason: "current-claim-changed" });

		writeLocalIntent({});
		const staleMaterial = await invoke({ owner: ownerFact({ material_digest: "sha256:stale" }) });
		expect(staleMaterial).toMatchObject({ state: "blocked", reason: "material-or-basis-drift" });

		writeLocalIntent({});
		const wrongTarget = await invoke({
			verifier: (e) => ({
				verifier_ref: e.verified_by,
				target_digest: "sha256:WRONG",
				observed_effect: e.observed_effect,
				confirmed: true,
			}),
		});
		expect(wrongTarget).toMatchObject({ state: "unknown", reason: "target-digest-drift" });

		writeLocalIntent({});
		const unproven = await invoke({
			verifier: (e) => ({
				verifier_ref: e.verified_by,
				target_digest: TARGET_DIGEST,
				observed_effect: e.observed_effect,
				confirmed: false,
			}),
		});
		expect(unproven).toMatchObject({ state: "unknown", reason: "execution-verifier-unproven" });
	});

	it("an unknown execution effect can never become executed", async () => {
		await commitExecution(hostAdapter({ effectState: "unknown" }));
		const out = await invoke();
		expect(out).toMatchObject({ state: "unknown", reason: "execution-effect-unknown" });
		expect(out.state).not.toBe("executed");
	});

	it("a forged DP-shaped execution file (DP impersonation) is refused", async () => {
		await commitSelection(hostAdapter());
		// Negative fixture: hand-written forged bytes with a DP decision_id.
		fs.mkdirSync(path.dirname(executionFile()), { recursive: true });
		fs.writeFileSync(
			executionFile(),
			`${JSON.stringify({
				schema_version: 1,
				kind: "local-execution",
				origin: "local-decision",
				source: "pm",
				local_ref: LOCAL_REF,
				decision_id: "dp-auto:forged",
				host_binding: {
					role: "pm",
					owner: CLAIM,
					claim_id: CLAIM,
					key: KEY,
					binding_version: "v3",
					observed_at: NOW,
				},
				action_ref: "tool_call:read:7",
				result_ref: "tool_result:read:7",
				executor: RESTRICTED_EXECUTOR,
				target_digest: TARGET_DIGEST,
				observed_effect: "two reads recorded",
				effect_state: "known",
				verified_by: "target-verifier:1",
				budget_ref: "budget:T07",
				created_at: NOW,
			})}\n`,
			"utf8",
		);
		const out = await invoke();
		expect(out).toMatchObject({ state: "blocked", reason: "execution-record-invalid" });
		expect(out.state).not.toBe("executed");
	});

	it("a local intent carrying a DP status field is refused (no DP statuses)", async () => {
		await commitExecution(hostAdapter());
		writeLocalIntent({ dpField: "status" });
		expect(await invoke()).toMatchObject({ state: "blocked", reason: "local-intent-invalid" });
	});

	it("a committed selection whose action differs from the restricted action is refused", async () => {
		await commitExecution(hostAdapter(), { selected_action: "narrow" });
		const out = await invoke();
		expect(out).toMatchObject({ state: "blocked", reason: "restricted-action-mismatch" });
		expect(out.state).not.toBe("executed");
	});

	it("an unbound PM window is refused and never executed", async () => {
		await commitExecution(hostAdapter());
		const out = await verifyLocalFollowupEvidence({
			intent_path: intentPath,
			expected,
			bound_pm: null,
			source: "pm",
			local_ref: LOCAL_REF,
			...boundaries(),
		});
		expect(out).toMatchObject({ state: "blocked", reason: "pm-window-unbound" });
	});
});

// Exact PM review negative probes, retained at the helper fixture boundary.
// These are not a live ProductionRuntimeHost positive.
describe("PM review negative probes (fixture helper boundary, expected refusals)", () => {
	it("must refuse an old selection when the CURRENT requested material digest changes", async () => {
		await commitExecution(hostAdapter());
		const changed = {
			...expected,
			material_version: createHash("sha256").update("different-current-material").digest("hex"),
		};
		writeLocalIntent({ material_version: changed.material_version });
		const out = await verifyLocalFollowupEvidence({
			intent_path: intentPath,
			expected: changed,
			bound_pm: boundPm,
			source: "pm",
			local_ref: LOCAL_REF,
			...boundaries(),
		});
		expect(out.state, JSON.stringify(out)).toBe("blocked");
	});

	it("must refuse a changed matter version even with an old matching host offer", async () => {
		await commitExecution(hostAdapter());
		const changed = { ...expected, parent_matter_version: "NEW-current-matter-version" };
		writeLocalIntent({ parent_matter_version: changed.parent_matter_version });
		const out = await verifyLocalFollowupEvidence({
			intent_path: intentPath,
			expected: changed,
			bound_pm: boundPm,
			source: "pm",
			local_ref: LOCAL_REF,
			...boundaries(),
		});
		expect(out.state, JSON.stringify(out)).toBe("blocked");
	});

	it("must refuse a changed local_ref across the asynchronous verifier boundary", async () => {
		await commitExecution(hostAdapter());
		const out = await invoke({
			verifier: (e) => {
				const current = JSON.parse(fs.readFileSync(intentPath, "utf8"));
				fs.writeFileSync(
					intentPath,
					`${JSON.stringify({ ...current, local_ref: "different-ref-during-await" })}\n`,
				);
				return {
					verifier_ref: e.verified_by,
					target_digest: e.target_digest,
					observed_effect: e.observed_effect,
					confirmed: true,
				};
			},
		});
		expect(out.state, JSON.stringify(out)).not.toBe("executed");
	});
});

// F2: strict local child/sidecar under shared same-matter coordination.
describe("F2 source-separated local child", () => {
	it("preserves a truthful failed DP intent while local planning/verification proceeds", async () => {
		await commitExecution(hostAdapter());
		const shared = path.join(tmp, "shared-followup.json");
		const sidecar = localFollowupSidecarPath(shared);
		expect(sidecar).not.toBe(shared);
		const dpBytes = `${JSON.stringify(dpFixture({ status: "failed", failure_reason: "provider-unavailable" }), null, 2)}\n`;
		fs.writeFileSync(shared, dpBytes, "utf8");
		writeLocalIntent({}, sidecar);
		const out = await verifyLocalFollowupEvidence({
			intent_path: sidecar,
			lock_path: sharedFollowupLockPath(shared),
			expected,
			bound_pm: boundPm,
			source: "pm",
			local_ref: LOCAL_REF,
			...boundaries({ intentPath: sidecar }),
		});
		expect(out).toMatchObject({ state: "executed", verified_source: "local", parent_released: false });
		expect(fs.readFileSync(shared, "utf8")).toBe(dpBytes);
		const persisted = JSON.parse(fs.readFileSync(sidecar, "utf8"));
		for (const dpKey of ["status", "request_ref", "answer", "decision_id", "available", "business_decisions"])
			expect(persisted).not.toHaveProperty(dpKey);
		expect(fs.existsSync(path.join(root, "..", ".mw", "decision-lifecycle.ndjson"))).toBe(false);
	});

	it("reverse source order leaves the strict DP parser and failed history intact", async () => {
		await commitExecution(hostAdapter());
		const shared = path.join(tmp, "shared-followup.json");
		const sidecar = localFollowupSidecarPath(shared);
		writeLocalIntent({}, sidecar);
		const localOut = await verifyLocalFollowupEvidence({
			intent_path: sidecar,
			lock_path: sharedFollowupLockPath(shared),
			expected,
			bound_pm: boundPm,
			source: "pm",
			local_ref: LOCAL_REF,
			...boundaries({ intentPath: sidecar }),
		});
		expect(localOut.state).toBe("executed");
		const localBytes = fs.readFileSync(sidecar, "utf8");
		const dpBytes = `${JSON.stringify(dpFixture({ status: "failed", failure_reason: "provider-unavailable" }), null, 2)}\n`;
		fs.writeFileSync(shared, dpBytes, "utf8");
		let requested = 0;
		const out = await resumeDecisionFollowup({
			intent_path: shared,
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request: () => {
				requested += 1;
				return Promise.resolve({ available: false as const, reason: "disabled" });
			},
		});
		expect(out).toMatchObject({
			state: "failed",
			reason: "provider-unavailable",
			duplicate: true,
			parent_released: false,
		});
		expect(requested).toBe(0);
		expect(fs.readFileSync(shared, "utf8")).toBe(dpBytes);
		expect(fs.readFileSync(sidecar, "utf8")).toBe(localBytes);
	});

	it("refuses a conclusion when production-equivalent trusted certificates are absent", async () => {
		await commitExecution(hostAdapter());
		const out = await verifyLocalFollowupEvidence({
			intent_path: intentPath,
			expected,
			bound_pm: boundPm,
			source: "pm",
			local_ref: LOCAL_REF,
			...boundaries(),
			readTrustedExecutor: () => undefined,
			readCurrentOffer: () => undefined,
		});
		expect(out.state).toBe("blocked");
		expect(out.reason).toContain("missing-interface:readTrustedExecutor");
	});
});

// F4: authoritative source-currentness barriers at every await and save.
describe("F4 source currentness and local_ref await barriers", () => {
	const driftCases: Array<[string, keyof SourceFacts, LocalFollowupCheckpoint]> = [
		["gate version", "gateVersion", "initial-lock"],
		["business", "business", "before-verifier"],
		["effect", "effect", "after-verifier"],
		["config", "config", "final-lock"],
		["watch key", "watchKey", "before-save"],
		["source card", "sourceCard", "before-write"],
		["worker evidence", "workerEvidence", "after-verifier"],
		["current offer", "currentOffer", "final-lock"],
	];

	it.each(driftCases)("refuses %s drift at %s", async (_label, field, checkpoint) => {
		await commitExecution(hostAdapter());
		const out = await invoke({
			barrier: (at) => {
				if (at === checkpoint) sourceFacts[field] = `${sourceFacts[field]}-changed`;
			},
		});
		expect(out.state, JSON.stringify(out)).not.toBe("executed");
		expect(out.reason).toContain("source-evidence-not-current");
		expect(JSON.parse(fs.readFileSync(intentPath, "utf8")).local_progress).not.toBe("verified");
	});

	it("refuses a persisted local_ref change while the verifier is suspended", async () => {
		await commitExecution(hostAdapter());
		const out = await invoke({
			barrier: (at) => {
				if (at !== "after-verifier") return;
				const current = JSON.parse(fs.readFileSync(intentPath, "utf8"));
				fs.writeFileSync(intentPath, `${JSON.stringify({ ...current, local_ref: "different-ref-at-barrier" })}\n`);
			},
		});
		expect(out.state, JSON.stringify(out)).not.toBe("executed");
		expect(out.reason).toContain("source-evidence-not-current:after-verifier");
		expect(JSON.parse(fs.readFileSync(intentPath, "utf8")).local_progress).not.toBe("verified");
	});

	it("unchanged controls succeed and every currentness checkpoint is exercised", async () => {
		await commitExecution(hostAdapter());
		const out = await invoke();
		expect(out).toMatchObject({ state: "executed", verified_source: "local", parent_released: false });
		expect(sourceChecks).toEqual(
			expect.arrayContaining([
				"initial-lock",
				"before-write",
				"before-verifier",
				"after-verifier",
				"final-lock",
				"before-save",
			]),
		);
	});
});

const registeredConsumerParentFixture = `
import hashlib, json, pathlib, sys
import pytest
from autopilot import gates
import decision_lifecycle as life
import decision_wire as wire
import test_dp_consolidation_materials as f
argv = sys.argv[1:]
root, owner, phase, target, choice, window = argv[:6]
stage = int(argv[6]) if len(argv) > 6 else 1
version = argv[7] if len(argv) > 7 else "v1"
root = pathlib.Path(root)
dp = "dp-gate-approve"
key = life.DecisionMeta.create(owner, initiator_role="pm")
gate = gates.create(root/".agenticdoc"/"_autopilot"/"gates", "stage-confirm", "Review this step",
                    stage=stage, key=owner, pm_note="Prepared PM plan", matter_ref="task-main", substantive_version=version)
ref = dp + ":" + key.logical_id
material = f._material(dp)
prep = f._preparation(dp, material)
store = life.LifecycleStore.production(root, redact=wire.SubstringRedactor([f.API_KEY]))
actor = ("system", "pm:" + window)
assert life.record_start(store,key,decision_id=ref,actor=actor).recorded
stage_note = "nt:stage-gate:" + hashlib.sha256(json.dumps(
    [owner, gate.stem, stage, "task-main", version, ref], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
assert life.record_note(store,key,decision_id=ref,pm_note="Prepared PM plan",prepared_at=prep["prepared_at"],
                        event_id=None,actor=actor).recorded
with pytest.MonkeyPatch.context() as patch:
    answers = {f.BUSINESS_QIDS[dp]: f._choice_answer("steer"), "basis_id": f._choice_answer(prep["basis_catalog"][0]["id"])}
    fake = f.FakeHttp(lambda *args:f._body(dp,answers))
    patch.setattr(f.backends,"_http_post",fake)
    result = f._make_client(root,patch).request_prepared(dp,material,prep,actor_role="pm")
    assert len(fake.calls)==1 and result["business_decisions"]==1, result.get("issues")
    assert life.record_request(store,key,decision_id=ref,result=result,material=material,preparation=prep,
        parent_ref=None,actor=actor).recorded
assert life.record_consumed(store,key,decision_id=ref,dp=dp,answer="steer",actor=actor).recorded
subject=f._material(target)
print(json.dumps({"gate":str(gate),"gate_ref":ref,"logical_id":key.logical_id,
    "matter_ref":"task-main","substantive_version":version,"parent_basis":result["basis_text"],
    "material":subject,"preparation":f._preparation(target,subject)}))
`;

describe("registered PM consumer sequence (F2/F4 integration, fail-closed production boundary)", () => {
	it("DP unavailable -> truthful failed DP intent -> strict local sidecar -> no execution without trusted interfaces", async () => {
		type ToolOutcome = { details?: unknown };
		type CapturedExecute = (
			toolCallId: string,
			params: Record<string, unknown>,
			signal: AbortSignal,
		) => Promise<ToolOutcome>;
		const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
		const previousMwPy = process.env.MW_PY;
		process.env.MW_PY = path.join(mw, "mw.py");
		try {
			const window = windowClaimId();
			expect((await new IndexStore(root).claim(KEY, window, () => false)).ok).toBe(true);
			const initial: {
				gate: string;
				gate_ref: string;
				parent_basis: string;
				material: Record<string, unknown>;
				preparation: DecisionPreparation;
			} = JSON.parse(
				execFileSync(
					PYTHON_EXE,
					[
						"-B",
						"-X",
						"utf8",
						"-c",
						registeredConsumerParentFixture,
						tmp,
						KEY,
						"gate",
						"dp-pm-steer",
						"steer",
						window,
					],
					{ cwd: mw, encoding: "utf8", windowsHide: true },
				),
			);
			fs.mkdirSync(path.join(root, KEY), { recursive: true });
			const configPath = path.join(root, "_autopilot", "config.json");
			fs.mkdirSync(path.dirname(configPath), { recursive: true });
			fs.writeFileSync(configPath, JSON.stringify({ enabled: true, auto_gate_mode: "live" }));
			expect(
				(
					await answerPreparedGate({
						gateFile: initial.gate,
						lockFile: path.join(tmp, ".mw", "gates.lock"),
						decision: "steer",
						matterRef: "task-main",
						substantiveVersion: "v1",
						note: "Prepared PM plan",
						modelBasis: initial.parent_basis,
						decisionRef: initial.gate_ref,
						answeredBy: window,
					})
				).ok,
			).toBe(true);

			let execute: CapturedExecute | undefined;
			const pi = {
				registerTool: (tool: unknown) => {
					const candidate = tool as { execute?: unknown };
					if (typeof candidate.execute === "function") execute = candidate.execute as CapturedExecute;
				},
			} as unknown as ExtensionAPI;
			let decideCalls = 0;
			const decideUnavailable = (async () => {
				decideCalls += 1;
				return { payload: { available: false, unavailable: "provider-unavailable" } };
			}) as unknown as Parameters<typeof registerPmGateFollowup>[4];
			registerPmGateFollowup(pi, tmp, new WorkerStore(root), { key: KEY }, decideUnavailable, {});
			expect(execute).toBeTypeOf("function");
			const invokeTool = async (params: Record<string, unknown>): Promise<Record<string, unknown>> => {
				if (!execute) throw new Error("pm_gate_followup was not registered");
				const outcome = await execute("registered-consumer", params, new AbortController().signal);
				return (outcome.details ?? {}) as Record<string, unknown>;
			};
			const baseParams: Record<string, unknown> = {
				gate_id: path.basename(initial.gate, ".md"),
				restricted_action: "continue",
				material: initial.material,
				preparation: initial.preparation,
			};
			const dpDetails = await invokeTool(baseParams);
			expect(dpDetails).toMatchObject({ state: "failed", reason: "provider-unavailable", parent_released: false });
			expect(decideCalls).toBe(1);
			const followupDir = path.join(root, KEY, "evidence", "decision-followups");
			const sharedName = fs
				.readdirSync(followupDir)
				.find((name) => name.endsWith(".json") && !name.endsWith(".local.json"));
			expect(sharedName).toBeTypeOf("string");
			const sharedPath = path.join(followupDir, sharedName ?? "");
			const sidecarPath = localFollowupSidecarPath(sharedPath);
			const sharedBytes = fs.readFileSync(sharedPath, "utf8");
			const ledgerPath = path.join(root, "_autopilot", "decision-lifecycle.jsonl");
			const ledgerBytes = fs.readFileSync(ledgerPath, "utf8");
			expect(JSON.parse(sharedBytes)).toMatchObject({ status: "failed", failure_reason: "provider-unavailable" });

			const localDetails = await invokeTool({ ...baseParams, local_ref: "lref:fixture" });
			expect(localDetails.state, JSON.stringify(localDetails)).toBe("blocked");
			expect(localDetails.reason).toContain("missing-interface:readTrustedExecutor");
			expect(localDetails.parent_released).toBe(false);
			expect(localDetails.verified_source).toBeUndefined();
			expect(decideCalls).toBe(1);
			expect(fs.readFileSync(sharedPath, "utf8")).toBe(sharedBytes);
			expect(fs.readFileSync(ledgerPath, "utf8")).toBe(ledgerBytes);
			expect(fs.existsSync(sidecarPath)).toBe(true);
			const persisted = JSON.parse(fs.readFileSync(sidecarPath, "utf8"));
			for (const dpKey of ["status", "answer", "decision_id", "available", "business_decisions"])
				expect(persisted).not.toHaveProperty(dpKey);
		} finally {
			if (previousMwPy === undefined) delete process.env.MW_PY;
			else process.env.MW_PY = previousMwPy;
		}
	});
});

// ── PM N1 sidecar recovery (registered consumer; frozen-store boundary) ────
// Reuses the PM's three registered N1 probes with meaningful controls. The
// executor/offer certificates below are HYPOTHETICAL fixtures: they are NOT a
// production host/runtime positive and never claim a real execution.
type N1LocalHost = NonNullable<Parameters<typeof registerPmGateFollowup>[5]>;
type R6WatchState = Parameters<typeof registerPmGateFollowup>[3];
type N1Execute = (id: string, params: Record<string, unknown>, signal: AbortSignal) => Promise<{ details?: unknown }>;

function n1Certs(): NonNullable<N1LocalHost["certificates"]> {
	return {
		readTrustedExecutor: () => ({
			current: true,
			local_ref: "lref:fixture",
			run_id: "pm-probe-run",
			tool_call_id: "pm-probe-call",
			executor: JSON.stringify(["pm-probe-run", "pm-probe-call"]),
		}),
		readCurrentOffer: () => undefined,
	};
}

interface N1Harness {
	invokeTool: (params: Record<string, unknown>) => Promise<Record<string, unknown>>;
	baseParams: Record<string, unknown>;
	localHost: N1LocalHost;
	sidecarPath: string;
	ledgerPath: string;
	sharedBytes: string;
	ledgerBytes: string;
	decideCalls: () => number;
	configPath: string;
	followupDir: string;
	watch: R6WatchState;
}

async function n1Harness(watch: R6WatchState = { key: KEY }): Promise<N1Harness> {
	const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
	const window = windowClaimId();
	expect((await new IndexStore(root).claim(KEY, window, () => false)).ok).toBe(true);
	const initial: {
		gate: string;
		gate_ref: string;
		parent_basis: string;
		material: Record<string, unknown>;
		preparation: DecisionPreparation;
	} = JSON.parse(
		execFileSync(
			PYTHON_EXE,
			["-B", "-X", "utf8", "-c", registeredConsumerParentFixture, tmp, KEY, "gate", "dp-pm-steer", "steer", window],
			{ cwd: mw, encoding: "utf8", windowsHide: true },
		),
	);
	fs.mkdirSync(path.join(root, KEY), { recursive: true });
	const configPath = path.join(root, "_autopilot", "config.json");
	fs.mkdirSync(path.dirname(configPath), { recursive: true });
	fs.writeFileSync(configPath, JSON.stringify({ enabled: true, auto_gate_mode: "live" }));
	expect(
		(
			await answerPreparedGate({
				gateFile: initial.gate,
				lockFile: path.join(tmp, ".mw", "gates.lock"),
				decision: "steer",
				matterRef: "task-main",
				substantiveVersion: "v1",
				note: "Prepared PM plan",
				modelBasis: initial.parent_basis,
				decisionRef: initial.gate_ref,
				answeredBy: window,
			})
		).ok,
	).toBe(true);
	let execute: N1Execute | undefined;
	const pi = {
		registerTool: (tool: unknown) => {
			const candidate = tool as { execute?: unknown };
			if (typeof candidate.execute === "function") execute = candidate.execute as N1Execute;
		},
	} as unknown as ExtensionAPI;
	const localHost: N1LocalHost = {};
	let calls = 0;
	const decideUnavailable = (async () => {
		calls += 1;
		return { payload: { available: false, unavailable: "provider-unavailable" } };
	}) as unknown as Parameters<typeof registerPmGateFollowup>[4];
	registerPmGateFollowup(pi, tmp, new WorkerStore(root), watch, decideUnavailable, localHost);
	const invokeTool = async (params: Record<string, unknown>): Promise<Record<string, unknown>> => {
		if (!execute) throw new Error("pm_gate_followup was not registered");
		const outcome = await execute("registered-consumer", params, new AbortController().signal);
		return (outcome.details ?? {}) as Record<string, unknown>;
	};
	const baseParams: Record<string, unknown> = {
		gate_id: path.basename(initial.gate, ".md"),
		restricted_action: "continue",
		material: initial.material,
		preparation: initial.preparation,
	};
	const dpDetails = await invokeTool(baseParams);
	expect(dpDetails).toMatchObject({ state: "failed", reason: "provider-unavailable", parent_released: false });
	expect(calls).toBe(1);
	const followupDir = path.join(root, KEY, "evidence", "decision-followups");
	const sharedName = fs.readdirSync(followupDir).find((n) => n.endsWith(".json") && !n.endsWith(".local.json"));
	expect(sharedName).toBeTypeOf("string");
	const sharedPath = path.join(followupDir, sharedName ?? "");
	const sidecarPath = localFollowupSidecarPath(sharedPath);
	const ledgerPath = path.join(root, "_autopilot", "decision-lifecycle.jsonl");
	const sharedBytes = fs.readFileSync(sharedPath, "utf8");
	const ledgerBytes = fs.readFileSync(ledgerPath, "utf8");
	expect(JSON.parse(sharedBytes)).toMatchObject({ status: "failed", failure_reason: "provider-unavailable" });
	return {
		invokeTool,
		baseParams,
		localHost,
		sidecarPath,
		ledgerPath,
		sharedBytes,
		ledgerBytes,
		decideCalls: () => calls,
		configPath,
		followupDir,
		watch,
	};
}

describe("PM N1 sidecar recovery (registered consumer)", () => {
	let savedMwPy: string | undefined;
	beforeAll(() => {
		savedMwPy = process.env.MW_PY;
		const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
		process.env.MW_PY = path.join(mw, "mw.py");
	});
	afterAll(() => {
		if (savedMwPy === undefined) delete process.env.MW_PY;
		else process.env.MW_PY = savedMwPy;
	});

	const dpKeys = ["status", "answer", "decision_id", "available", "business_decisions"];

	it("PM N1 fresh executor control: fresh sidecar reaches the missing-offer boundary (unchanged control)", async () => {
		const h = await n1Harness();
		h.localHost.certificates = n1Certs();
		const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		expect(out.state, JSON.stringify(out)).toBe("blocked");
		expect(out.reason).toContain("missing-interface:readCurrentOffer");
		expect(out.parent_released).toBe(false);
		expect(out.verified_source).toBeUndefined();
		expect(h.decideCalls()).toBe(1);
		expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
		expect(fs.existsSync(h.sidecarPath)).toBe(true);
		const persisted = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8"));
		for (const dpKey of dpKeys) expect(persisted).not.toHaveProperty(dpKey);
		expect(persisted.restricted_executor).toBe(n1Certs().readTrustedExecutor("")?.executor);
	});

	it("PM N1 same locator executor recovery: same ref + recovered executor reaches missing-offer, not version-mismatch", async () => {
		const h = await n1Harness();
		const first = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		expect(first.state, JSON.stringify(first)).toBe("blocked");
		expect(first.reason).toContain("missing-interface:readTrustedExecutor");
		expect(fs.existsSync(h.sidecarPath)).toBe(true);
		const placeholder = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8"));
		expect(placeholder.local_progress).toBe(null);
		expect(placeholder.local_action_evidence).toBe(null);
		h.localHost.certificates = n1Certs();
		const upgraded = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		expect(upgraded.state, JSON.stringify(upgraded)).toBe("blocked");
		expect(upgraded.reason).toContain("missing-interface:readCurrentOffer");
		expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
		const recovered = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8"));
		expect(recovered.restricted_executor).toBe(n1Certs().readTrustedExecutor("")?.executor);
		for (const dpKey of dpKeys) expect(recovered).not.toHaveProperty(dpKey);
	});

	it("PM N1 locator recovery: corrected ref reaches missing-interface, not initial-lock", async () => {
		const h = await n1Harness();
		const first = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		expect(first.reason).toContain("missing-interface:readTrustedExecutor");
		expect(fs.existsSync(h.sidecarPath)).toBe(true);
		const corrected = await h.invokeTool({ ...h.baseParams, local_ref: "lref:corrected" });
		expect(corrected.state, JSON.stringify(corrected)).toBe("blocked");
		expect(corrected.reason).toContain("missing-interface:readTrustedExecutor");
		expect(corrected.reason).not.toContain("initial-lock");
		const persisted = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8"));
		expect(persisted.local_ref).toBe("lref:corrected");
		expect(persisted.local_progress).toBe(null);
		expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
	});

	it("unchanged control: repeated authenticated same-ref call is idempotent, safe placeholder preserved", async () => {
		const h = await n1Harness();
		h.localHost.certificates = n1Certs();
		const first = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		const bytes = fs.readFileSync(h.sidecarPath, "utf8");
		const second = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		for (const out of [first, second]) {
			expect(out.reason).toContain("missing-interface:readCurrentOffer");
			expect(out.state).not.toBe("executed");
		}
		expect(fs.readFileSync(h.sidecarPath, "utf8")).toBe(bytes);
		const persisted = JSON.parse(bytes);
		expect(persisted.local_progress).toBe(null);
		expect(persisted.local_action_evidence).toBe(null);
		expect(h.decideCalls()).toBe(1);
	});

	it("lock-wait source drift: authoritative config drift during the shared-lock await refuses, no child pinned", async () => {
		const h = await n1Harness();
		// The consumer captures `parent` synchronously, then awaits the shared
		// matter lock. Drift the REAL authoritative config in that await window.
		const pending = h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		fs.writeFileSync(h.configPath, JSON.stringify({ enabled: true, auto_gate_mode: "off" }));
		const out = await pending;
		expect(out.state, JSON.stringify(out)).toBe("blocked");
		expect(out.reason).toContain("source-evidence-not-current:create-lock");
		expect(fs.existsSync(h.sidecarPath)).toBe(false);
		expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
	});

	it("no blind overwrite: an executing/crash-unknown child is preserved untouched on a later call", async () => {
		const h = await n1Harness();
		await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		expect(fs.existsSync(h.sidecarPath)).toBe(true);
		const seeded = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8"));
		seeded.local_progress = "executing";
		const seededBytes = `${JSON.stringify(seeded, null, 2)}\n`;
		fs.writeFileSync(h.sidecarPath, seededBytes);
		const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		expect(out.state, JSON.stringify(out)).toBe("unknown");
		expect(out.reason).toContain("local-outcome-unknown");
		expect(fs.readFileSync(h.sidecarPath, "utf8")).toBe(seededBytes);
	});

	it("a stale selection-only plan is refused BEFORE any selected label (helper-level control)", async () => {
		await commitSelection(hostAdapter());
		const out = await invoke({ owner: ownerFact({ material_digest: "sha256:stale" }) });
		expect(out.state, JSON.stringify(out)).toBe("blocked");
		expect(out.reason).toBe("material-or-basis-drift");
		expect(JSON.parse(fs.readFileSync(intentPath, "utf8")).local_progress).toBe(null);
	});
});

// PM safety probes: isolated malformed/wrong-owner placeholders must NOT be
// silently reinitialized before strict validation. These are no-execution tests.
describe("PM R2 strict placeholder preservation (registered, NOT production positive)", () => {
	let previous: string | undefined;
	beforeAll(() => {
		previous = process.env.MW_PY;
		process.env.MW_PY = path.join(fileURLToPath(new URL("../../../multi-workers/", import.meta.url)), "mw.py");
	});
	afterAll(() => {
		if (previous === undefined) delete process.env.MW_PY;
		else process.env.MW_PY = previous;
	});
	it.each(["extra-dp-key", "wrong-owner", "missing-binding", "bad-field-type"])(
		"must preserve/refuse %s instead of repairing it into a valid local intent",
		async (scenario) => {
			const h = await n1Harness();
			await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
			const seeded = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")) as Record<string, unknown>;
			if (scenario === "extra-dp-key") seeded.decision_id = "dp-pm-steer:forged-fixture-only";
			if (scenario === "wrong-owner") seeded.owner_key = "foreign-fixture-owner";
			if (scenario === "missing-binding") delete seeded.parent_decision_id;
			if (scenario === "bad-field-type") seeded.material_version = 123;
			const seededBytes = `${JSON.stringify(seeded, null, 2)}\n`;
			fs.writeFileSync(h.sidecarPath, seededBytes);
			const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
			expect(out.state, JSON.stringify(out)).not.toBe("executed");
			expect(out.parent_released).toBe(false);
			expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
			expect(fs.readFileSync(h.sidecarPath, "utf8"), JSON.stringify({ scenario, out })).toBe(seededBytes);
		},
	);
	it("unchanged valid no-execution placeholder remains byte-identical", async () => {
		const h = await n1Harness();
		await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		const before = fs.readFileSync(h.sidecarPath, "utf8");
		const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		expect(out.reason).toContain("missing-interface:readTrustedExecutor");
		expect(fs.readFileSync(h.sidecarPath, "utf8")).toBe(before);
	});
	it("executing control remains byte-identical and unknown", async () => {
		const h = await n1Harness();
		await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		const row = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")) as Record<string, unknown>;
		row.local_progress = "executing";
		const before = `${JSON.stringify(row, null, 2)}\n`;
		fs.writeFileSync(h.sidecarPath, before);
		const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		expect(out.state).toBe("unknown");
		expect(fs.readFileSync(h.sidecarPath, "utf8")).toBe(before);
	});
});

describe("PM N1 fresh executor control (hypothetical certificate, NOT production proof)", () => {
	it("fresh sidecar with the same hypothetical executor reaches the missing-offer boundary", async () => {
		type ToolOutcome = { details?: unknown };
		type CapturedExecute = (
			toolCallId: string,
			params: Record<string, unknown>,
			signal: AbortSignal,
		) => Promise<ToolOutcome>;
		const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
		const previousMwPy = process.env.MW_PY;
		process.env.MW_PY = path.join(mw, "mw.py");
		try {
			const window = windowClaimId();
			expect((await new IndexStore(root).claim(KEY, window, () => false)).ok).toBe(true);
			const initial: {
				gate: string;
				gate_ref: string;
				parent_basis: string;
				material: Record<string, unknown>;
				preparation: DecisionPreparation;
			} = JSON.parse(
				execFileSync(
					PYTHON_EXE,
					[
						"-B",
						"-X",
						"utf8",
						"-c",
						registeredConsumerParentFixture,
						tmp,
						KEY,
						"gate",
						"dp-pm-steer",
						"steer",
						window,
					],
					{ cwd: mw, encoding: "utf8", windowsHide: true },
				),
			);
			fs.mkdirSync(path.join(root, KEY), { recursive: true });
			const configPath = path.join(root, "_autopilot", "config.json");
			fs.mkdirSync(path.dirname(configPath), { recursive: true });
			fs.writeFileSync(configPath, JSON.stringify({ enabled: true, auto_gate_mode: "live" }));
			expect(
				(
					await answerPreparedGate({
						gateFile: initial.gate,
						lockFile: path.join(tmp, ".mw", "gates.lock"),
						decision: "steer",
						matterRef: "task-main",
						substantiveVersion: "v1",
						note: "Prepared PM plan",
						modelBasis: initial.parent_basis,
						decisionRef: initial.gate_ref,
						answeredBy: window,
					})
				).ok,
			).toBe(true);

			let execute: CapturedExecute | undefined;
			const pi = {
				registerTool: (tool: unknown) => {
					const candidate = tool as { execute?: unknown };
					if (typeof candidate.execute === "function") execute = candidate.execute as CapturedExecute;
				},
			} as unknown as ExtensionAPI;
			type LocalHost = NonNullable<Parameters<typeof registerPmGateFollowup>[5]>;
			const localHost: LocalHost = {};
			let decideCalls = 0;
			const decideUnavailable = (async () => {
				decideCalls += 1;
				return { payload: { available: false, unavailable: "provider-unavailable" } };
			}) as unknown as Parameters<typeof registerPmGateFollowup>[4];
			registerPmGateFollowup(pi, tmp, new WorkerStore(root), { key: KEY }, decideUnavailable, localHost);
			expect(execute).toBeTypeOf("function");
			const invokeTool = async (params: Record<string, unknown>): Promise<Record<string, unknown>> => {
				if (!execute) throw new Error("pm_gate_followup was not registered");
				const outcome = await execute("registered-consumer", params, new AbortController().signal);
				return (outcome.details ?? {}) as Record<string, unknown>;
			};
			const baseParams: Record<string, unknown> = {
				gate_id: path.basename(initial.gate, ".md"),
				restricted_action: "continue",
				material: initial.material,
				preparation: initial.preparation,
			};
			const dpDetails = await invokeTool(baseParams);
			expect(dpDetails).toMatchObject({ state: "failed", reason: "provider-unavailable", parent_released: false });
			expect(decideCalls).toBe(1);
			const followupDir = path.join(root, KEY, "evidence", "decision-followups");
			const sharedName = fs
				.readdirSync(followupDir)
				.find((name) => name.endsWith(".json") && !name.endsWith(".local.json"));
			expect(sharedName).toBeTypeOf("string");
			const sharedPath = path.join(followupDir, sharedName ?? "");
			const sidecarPath = localFollowupSidecarPath(sharedPath);
			const sharedBytes = fs.readFileSync(sharedPath, "utf8");
			const ledgerPath = path.join(root, "_autopilot", "decision-lifecycle.jsonl");
			const ledgerBytes = fs.readFileSync(ledgerPath, "utf8");
			expect(JSON.parse(sharedBytes)).toMatchObject({ status: "failed", failure_reason: "provider-unavailable" });

			localHost.certificates = {
				readTrustedExecutor: () => ({
					current: true,
					local_ref: "lref:fixture",
					run_id: "pm-probe-run",
					tool_call_id: "pm-probe-call",
					executor: JSON.stringify(["pm-probe-run", "pm-probe-call"]),
				}),
				readCurrentOffer: () => undefined,
			};
			const localDetails = await invokeTool({ ...baseParams, local_ref: "lref:fixture" });
			expect(localDetails.state, JSON.stringify(localDetails)).toBe("blocked");
			expect(localDetails.reason).toContain("missing-interface:readCurrentOffer");
			expect(localDetails.parent_released).toBe(false);
			expect(localDetails.verified_source).toBeUndefined();
			expect(decideCalls).toBe(1);
			expect(fs.readFileSync(sharedPath, "utf8")).toBe(sharedBytes);
			expect(fs.readFileSync(ledgerPath, "utf8")).toBe(ledgerBytes);
			expect(fs.existsSync(sidecarPath)).toBe(true);
			const persisted = JSON.parse(fs.readFileSync(sidecarPath, "utf8"));
			for (const dpKey of ["status", "answer", "decision_id", "available", "business_decisions"])
				expect(persisted).not.toHaveProperty(dpKey);
		} finally {
			if (previousMwPy === undefined) delete process.env.MW_PY;
			else process.env.MW_PY = previousMwPy;
		}
	});
});

describe("PM N1 same locator executor recovery (hypothetical certificate, NOT production proof)", () => {
	it("MUST reach the now-missing offer check after executor interface recovers, as a fresh identical control does", async () => {
		type ToolOutcome = { details?: unknown };
		type CapturedExecute = (
			toolCallId: string,
			params: Record<string, unknown>,
			signal: AbortSignal,
		) => Promise<ToolOutcome>;
		const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
		const previousMwPy = process.env.MW_PY;
		process.env.MW_PY = path.join(mw, "mw.py");
		try {
			const window = windowClaimId();
			expect((await new IndexStore(root).claim(KEY, window, () => false)).ok).toBe(true);
			const initial: {
				gate: string;
				gate_ref: string;
				parent_basis: string;
				material: Record<string, unknown>;
				preparation: DecisionPreparation;
			} = JSON.parse(
				execFileSync(
					PYTHON_EXE,
					[
						"-B",
						"-X",
						"utf8",
						"-c",
						registeredConsumerParentFixture,
						tmp,
						KEY,
						"gate",
						"dp-pm-steer",
						"steer",
						window,
					],
					{ cwd: mw, encoding: "utf8", windowsHide: true },
				),
			);
			fs.mkdirSync(path.join(root, KEY), { recursive: true });
			const configPath = path.join(root, "_autopilot", "config.json");
			fs.mkdirSync(path.dirname(configPath), { recursive: true });
			fs.writeFileSync(configPath, JSON.stringify({ enabled: true, auto_gate_mode: "live" }));
			expect(
				(
					await answerPreparedGate({
						gateFile: initial.gate,
						lockFile: path.join(tmp, ".mw", "gates.lock"),
						decision: "steer",
						matterRef: "task-main",
						substantiveVersion: "v1",
						note: "Prepared PM plan",
						modelBasis: initial.parent_basis,
						decisionRef: initial.gate_ref,
						answeredBy: window,
					})
				).ok,
			).toBe(true);

			let execute: CapturedExecute | undefined;
			const pi = {
				registerTool: (tool: unknown) => {
					const candidate = tool as { execute?: unknown };
					if (typeof candidate.execute === "function") execute = candidate.execute as CapturedExecute;
				},
			} as unknown as ExtensionAPI;
			type LocalHost = NonNullable<Parameters<typeof registerPmGateFollowup>[5]>;
			const localHost: LocalHost = {};
			let decideCalls = 0;
			const decideUnavailable = (async () => {
				decideCalls += 1;
				return { payload: { available: false, unavailable: "provider-unavailable" } };
			}) as unknown as Parameters<typeof registerPmGateFollowup>[4];
			registerPmGateFollowup(pi, tmp, new WorkerStore(root), { key: KEY }, decideUnavailable, localHost);
			expect(execute).toBeTypeOf("function");
			const invokeTool = async (params: Record<string, unknown>): Promise<Record<string, unknown>> => {
				if (!execute) throw new Error("pm_gate_followup was not registered");
				const outcome = await execute("registered-consumer", params, new AbortController().signal);
				return (outcome.details ?? {}) as Record<string, unknown>;
			};
			const baseParams: Record<string, unknown> = {
				gate_id: path.basename(initial.gate, ".md"),
				restricted_action: "continue",
				material: initial.material,
				preparation: initial.preparation,
			};
			const dpDetails = await invokeTool(baseParams);
			expect(dpDetails).toMatchObject({ state: "failed", reason: "provider-unavailable", parent_released: false });
			expect(decideCalls).toBe(1);
			const followupDir = path.join(root, KEY, "evidence", "decision-followups");
			const sharedName = fs
				.readdirSync(followupDir)
				.find((name) => name.endsWith(".json") && !name.endsWith(".local.json"));
			expect(sharedName).toBeTypeOf("string");
			const sharedPath = path.join(followupDir, sharedName ?? "");
			const sidecarPath = localFollowupSidecarPath(sharedPath);
			const sharedBytes = fs.readFileSync(sharedPath, "utf8");
			const ledgerPath = path.join(root, "_autopilot", "decision-lifecycle.jsonl");
			const ledgerBytes = fs.readFileSync(ledgerPath, "utf8");
			expect(JSON.parse(sharedBytes)).toMatchObject({ status: "failed", failure_reason: "provider-unavailable" });

			const localDetails = await invokeTool({ ...baseParams, local_ref: "lref:fixture" });
			expect(localDetails.state, JSON.stringify(localDetails)).toBe("blocked");
			expect(localDetails.reason).toContain("missing-interface:readTrustedExecutor");
			expect(localDetails.parent_released).toBe(false);
			expect(localDetails.verified_source).toBeUndefined();
			expect(decideCalls).toBe(1);
			expect(fs.readFileSync(sharedPath, "utf8")).toBe(sharedBytes);
			expect(fs.readFileSync(ledgerPath, "utf8")).toBe(ledgerBytes);
			expect(fs.existsSync(sidecarPath)).toBe(true);
			const persisted = JSON.parse(fs.readFileSync(sidecarPath, "utf8"));
			for (const dpKey of ["status", "answer", "decision_id", "available", "business_decisions"])
				expect(persisted).not.toHaveProperty(dpKey);
			// No offer certificate and no real execution are claimed. This only
			// tests progress from a missing-executor boundary to missing-offer.
			localHost.certificates = {
				readTrustedExecutor: () => ({
					current: true,
					local_ref: "lref:fixture",
					run_id: "pm-probe-run",
					tool_call_id: "pm-probe-call",
					executor: JSON.stringify(["pm-probe-run", "pm-probe-call"]),
				}),
				readCurrentOffer: () => undefined,
			};

			const upgraded = await invokeTool({ ...baseParams, local_ref: "lref:fixture" });
			expect(upgraded.state).toBe("blocked");
			expect(upgraded.reason, JSON.stringify(upgraded)).toContain("missing-interface:readCurrentOffer");
		} finally {
			if (previousMwPy === undefined) delete process.env.MW_PY;
			else process.env.MW_PY = previousMwPy;
		}
	});
});

describe("PM N1 locator recovery (no execution claimed)", () => {
	it("MUST not let an unauthenticated first locator permanently preempt the next locator before interface validation", async () => {
		type ToolOutcome = { details?: unknown };
		type CapturedExecute = (
			toolCallId: string,
			params: Record<string, unknown>,
			signal: AbortSignal,
		) => Promise<ToolOutcome>;
		const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
		const previousMwPy = process.env.MW_PY;
		process.env.MW_PY = path.join(mw, "mw.py");
		try {
			const window = windowClaimId();
			expect((await new IndexStore(root).claim(KEY, window, () => false)).ok).toBe(true);
			const initial: {
				gate: string;
				gate_ref: string;
				parent_basis: string;
				material: Record<string, unknown>;
				preparation: DecisionPreparation;
			} = JSON.parse(
				execFileSync(
					PYTHON_EXE,
					[
						"-B",
						"-X",
						"utf8",
						"-c",
						registeredConsumerParentFixture,
						tmp,
						KEY,
						"gate",
						"dp-pm-steer",
						"steer",
						window,
					],
					{ cwd: mw, encoding: "utf8", windowsHide: true },
				),
			);
			fs.mkdirSync(path.join(root, KEY), { recursive: true });
			const configPath = path.join(root, "_autopilot", "config.json");
			fs.mkdirSync(path.dirname(configPath), { recursive: true });
			fs.writeFileSync(configPath, JSON.stringify({ enabled: true, auto_gate_mode: "live" }));
			expect(
				(
					await answerPreparedGate({
						gateFile: initial.gate,
						lockFile: path.join(tmp, ".mw", "gates.lock"),
						decision: "steer",
						matterRef: "task-main",
						substantiveVersion: "v1",
						note: "Prepared PM plan",
						modelBasis: initial.parent_basis,
						decisionRef: initial.gate_ref,
						answeredBy: window,
					})
				).ok,
			).toBe(true);

			let execute: CapturedExecute | undefined;
			const pi = {
				registerTool: (tool: unknown) => {
					const candidate = tool as { execute?: unknown };
					if (typeof candidate.execute === "function") execute = candidate.execute as CapturedExecute;
				},
			} as unknown as ExtensionAPI;
			type LocalHost = NonNullable<Parameters<typeof registerPmGateFollowup>[5]>;
			const localHost: LocalHost = {};
			let decideCalls = 0;
			const decideUnavailable = (async () => {
				decideCalls += 1;
				return { payload: { available: false, unavailable: "provider-unavailable" } };
			}) as unknown as Parameters<typeof registerPmGateFollowup>[4];
			registerPmGateFollowup(pi, tmp, new WorkerStore(root), { key: KEY }, decideUnavailable, localHost);
			expect(execute).toBeTypeOf("function");
			const invokeTool = async (params: Record<string, unknown>): Promise<Record<string, unknown>> => {
				if (!execute) throw new Error("pm_gate_followup was not registered");
				const outcome = await execute("registered-consumer", params, new AbortController().signal);
				return (outcome.details ?? {}) as Record<string, unknown>;
			};
			const baseParams: Record<string, unknown> = {
				gate_id: path.basename(initial.gate, ".md"),
				restricted_action: "continue",
				material: initial.material,
				preparation: initial.preparation,
			};
			const dpDetails = await invokeTool(baseParams);
			expect(dpDetails).toMatchObject({ state: "failed", reason: "provider-unavailable", parent_released: false });
			expect(decideCalls).toBe(1);
			const followupDir = path.join(root, KEY, "evidence", "decision-followups");
			const sharedName = fs
				.readdirSync(followupDir)
				.find((name) => name.endsWith(".json") && !name.endsWith(".local.json"));
			expect(sharedName).toBeTypeOf("string");
			const sharedPath = path.join(followupDir, sharedName ?? "");
			const sidecarPath = localFollowupSidecarPath(sharedPath);
			const sharedBytes = fs.readFileSync(sharedPath, "utf8");
			const ledgerPath = path.join(root, "_autopilot", "decision-lifecycle.jsonl");
			const ledgerBytes = fs.readFileSync(ledgerPath, "utf8");
			expect(JSON.parse(sharedBytes)).toMatchObject({ status: "failed", failure_reason: "provider-unavailable" });

			const localDetails = await invokeTool({ ...baseParams, local_ref: "lref:fixture" });
			expect(localDetails.state, JSON.stringify(localDetails)).toBe("blocked");
			expect(localDetails.reason).toContain("missing-interface:readTrustedExecutor");
			expect(localDetails.parent_released).toBe(false);
			expect(localDetails.verified_source).toBeUndefined();
			expect(decideCalls).toBe(1);
			expect(fs.readFileSync(sharedPath, "utf8")).toBe(sharedBytes);
			expect(fs.readFileSync(ledgerPath, "utf8")).toBe(ledgerBytes);
			expect(fs.existsSync(sidecarPath)).toBe(true);
			const persisted = JSON.parse(fs.readFileSync(sidecarPath, "utf8"));
			for (const dpKey of ["status", "answer", "decision_id", "available", "business_decisions"])
				expect(persisted).not.toHaveProperty(dpKey);
			const corrected = await invokeTool({ ...baseParams, local_ref: "lref:corrected" });
			expect(corrected.state).toBe("blocked");
			expect(corrected.reason, JSON.stringify(corrected)).toContain("missing-interface:readTrustedExecutor");
		} finally {
			if (previousMwPy === undefined) delete process.env.MW_PY;
			else process.env.MW_PY = previousMwPy;
		}
	});
});

// Helper-boundary proof only: these controls drive the real registered helper
// with fixture certificates. They are NOT a registered consumer verifier-await
// integration and NOT a production current-offer/executor positive.
describe("PM R3 current-offer applicability (helper boundary, NOT production positive)", () => {
	it("stale offer matter/version and selected basis refuse BEFORE any selected label", async () => {
		await commitSelection(hostAdapter());
		const staleOffer: LocalTrustedOfferCertificate = {
			...offerCertificate(),
			matter_version: `${MATTER_VERSION}-stale`,
			selected_basis_id: "b2",
			basis_applies_to: ["narrow"],
		};
		const out = await invoke({ offerCertificate: staleOffer });
		expect(out.state, JSON.stringify(out)).toBe("blocked");
		expect(out.reason).toBe("current-offer-selection-applicability-mismatch");
		expect(out.parent_released).toBe(false);
		expect(out.state).not.toBe("executed");
		expect(JSON.parse(fs.readFileSync(intentPath, "utf8")).local_progress).toBe(null);
		expect(fs.existsSync(path.join(root, "..", ".mw", "decision-lifecycle.ndjson"))).toBe(false);
	});

	it("a current offer whose basis no longer applies to the choice refuses before selected", async () => {
		await commitSelection(hostAdapter());
		const nonApplicableOffer: LocalTrustedOfferCertificate = {
			...offerCertificate(),
			basis_applies_to: ["narrow"],
		};
		const out = await invoke({ offerCertificate: nonApplicableOffer });
		expect(out.state, JSON.stringify(out)).toBe("blocked");
		expect(out.reason).toBe("current-offer-selection-applicability-mismatch");
		expect(out.parent_released).toBe(false);
		expect(JSON.parse(fs.readFileSync(intentPath, "utf8")).local_progress).toBe(null);
	});

	it("unchanged current offer keeps selection-only non-execution and sets selected only after checks", async () => {
		await commitSelection(hostAdapter());
		const out = await invoke();
		expect(out).toMatchObject({
			state: "in-progress",
			reason: "selection-only-no-execution",
			parent_released: false,
			request_started: false,
		});
		expect(out.state).not.toBe("executed");
		expect(out.request_ref).toBeUndefined();
		expect(out.answer).toBeUndefined();
		expect(JSON.parse(fs.readFileSync(intentPath, "utf8")).local_progress).toBe("selected");
		expect(fs.existsSync(path.join(root, "..", ".mw", "decision-lifecycle.ndjson"))).toBe(false);
	});
});

// PM R4 raw duplicate-field preservation (frozen five PM cases, registered).
// Anomalous/evidence-bearing RAW bytes must be refused and preserved; the
// unambiguous null/null control keeps the intentional locator recovery.
describe("PM R3 raw duplicate-field preservation (registered, no execution)", () => {
	let previous: string | undefined;
	beforeAll(() => {
		previous = process.env.MW_PY;
		process.env.MW_PY = path.join(fileURLToPath(new URL("../../../multi-workers/", import.meta.url)), "mw.py");
	});
	afterAll(() => {
		if (previous === undefined) delete process.env.MW_PY;
		else process.env.MW_PY = previous;
	});
	it.each(["shadowed-progress", "shadowed-evidence", "explicit-progress", "explicit-evidence"])(
		"must preserve anomalous/evidence-bearing %s bytes on locator correction",
		async (scenario) => {
			const h = await n1Harness();
			await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
			const row = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")) as Record<string, unknown>;
			if (scenario === "explicit-progress") row.local_progress = "executing";
			if (scenario === "explicit-evidence") row.local_action_evidence = "negative-fixture-untrusted-prior-result";
			let bytes = `${JSON.stringify(row)}\n`;
			if (scenario === "shadowed-progress")
				bytes = bytes.replace('"local_progress":null', '"local_progress":"executing","local_progress":null');
			if (scenario === "shadowed-evidence")
				bytes = bytes.replace(
					'"local_action_evidence":null',
					'"local_action_evidence":"negative-fixture-untrusted-prior-result","local_action_evidence":null',
				);
			if (scenario.startsWith("shadowed")) expect(bytes.length).toBeGreaterThan(JSON.stringify(row).length + 1);
			fs.writeFileSync(h.sidecarPath, bytes);
			const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:corrected" });
			expect(out.state, JSON.stringify(out)).not.toBe("executed");
			expect(out.parent_released).toBe(false);
			expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
			expect(fs.readFileSync(h.sidecarPath, "utf8"), JSON.stringify({ scenario, out })).toBe(bytes);
		},
	);
	it("unambiguous null control retains intentional locator recovery", async () => {
		const h = await n1Harness();
		await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:corrected" });
		expect(out.state).toBe("blocked");
		expect(out.reason).toContain("missing-interface:readTrustedExecutor");
		expect(JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")).local_ref).toBe("lref:corrected");
	});
});

// R4 H1: a locator correction records the child's prior association in the
// recovered sidecar instead of discarding it. Frozen-store absence is NOT host
// effect-history proof; no certificate or execution is claimed here.
describe("PM R4 locator-correction association preservation (registered, no execution)", () => {
	it("records the old locator as prior-association coordination evidence", async () => {
		const h = await n1Harness();
		await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:corrected" });
		expect(out.state, JSON.stringify(out)).toBe("blocked");
		expect(out.reason).toContain("missing-interface:readTrustedExecutor");
		expect(out.parent_released).toBe(false);
		expect(out.verified_source).toBeUndefined();
		const persisted = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8"));
		expect(persisted.local_ref).toBe("lref:corrected");
		expect(persisted.local_progress).toBe(null);
		expect(persisted.local_action_evidence).toContain('"lref:fixture"');
		expect(hasDuplicateJsonMembers(fs.readFileSync(h.sidecarPath, "utf8"))).toBe(false);
		expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
		expect(fs.readFileSync(h.sidecarPath, "utf8")).not.toContain('"local_progress":"executing","local_progress"');
	});

	it("a recovered child carrying prior association refuses a fabricated evidence string", async () => {
		const h = await n1Harness();
		await h.invokeTool({ ...h.baseParams, local_ref: "lref:fixture" });
		await h.invokeTool({ ...h.baseParams, local_ref: "lref:corrected" });
		const row = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")) as Record<string, unknown>;
		row.local_action_evidence = "forged-result-ref";
		const bytes = `${JSON.stringify(row)}\n`;
		fs.writeFileSync(h.sidecarPath, bytes);
		const out = await h.invokeTool({ ...h.baseParams, local_ref: "lref:third" });
		expect(out.state, JSON.stringify(out)).not.toBe("executed");
		expect(out.parent_released).toBe(false);
		expect(fs.readFileSync(h.sidecarPath, "utf8")).toBe(bytes);
		expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
	});
});

// R4 helper boundary: the RAW duplicate-member detector itself.
describe("R4 raw duplicate JSON member detection (helper boundary)", () => {
	it("detects duplicated and escaped-key members before any parse", () => {
		expect(hasDuplicateJsonMembers('{"a":1,"a":2}')).toBe(true);
		expect(hasDuplicateJsonMembers('{"a":1,"b":{"c":2,"c":3}}')).toBe(true);
		expect(hasDuplicateJsonMembers('{"a":1,"\\u0061":2}')).toBe(true);
		expect(hasDuplicateJsonMembers('{"a":"x\\"y","b":null}')).toBe(false);
		expect(hasDuplicateJsonMembers('{"a":[1,{"b":2}],"c":true}')).toBe(false);
		expect(hasDuplicateJsonMembers('{"a":1,}')).toBe(true);
	});
});

// ─────────────────────────────────────────────────────────────────────────────
// T07 R5 — registered pm_gate_followup verifier-ENTRY boundary evidence.
//
// FIXTURE CLASSIFICATION (read before interpreting any result):
//  * The executor/offer certificates, the submitHandle projection and the host
//    verifier injected through `localHost` are HYPOTHETICAL FIXTURES. They are
//    NOT a ProductionRuntimeHost positive and NOT F1/F3 production proof. The
//    real registered consumer exposes no public API that mints a trusted
//    current-run executor, canonical current-offer or host execution verifier;
//    that gap is reported, never manufactured as a trusted production fact.
//  * Committed local selection/execution records come ONLY from the real frozen
//    LocalSelectionStore.commitSelection / appendExecution. No passing
//    selection/execution/proof record is hand-written.
//  * The verifier carries (a) an ACTUAL ENTRY COUNTER and (b) a CONTROLLABLE
//    UNRESOLVED PROMISE (a deferred we resolve explicitly). A refusal BEFORE
//    the verifier leaves the counter at 0 = "refusal-before-verifier", NOT
//    verifier-entered coverage.
//  * parent_released stays false; the original failed-DP bytes and the DP
//    lifecycle ledger are asserted byte-identical; zero DP request/receipt.
// ─────────────────────────────────────────────────────────────────────────────

// Evidence is also appended under the child's pinned TEMP (authorized root) so
// green tests' verifier-entry counters remain observable after the run.
const R5_EVIDENCE = path.join(os.tmpdir(), "r5-verifier-evidence.jsonl");
function r5Log(line: string): void {
	console.log(line);
	try {
		fs.appendFileSync(R5_EVIDENCE, `pid=${process.pid} ${line}\n`);
	} catch {
		// evidence file is best-effort; assertions never depend on it
	}
}

interface R5Verifier {
	host: N1LocalHost["host"];
	entries: () => number;
	entered: Promise<void>;
	resolve: (proof: ExecutionProof | undefined) => void;
}

/** HYPOTHETICAL host verifier: real entry counter + controllable unresolved
 *  Promise. NOT a ProductionRuntimeHost proof. */
function r5Verifier(): R5Verifier {
	let count = 0;
	let resolveProof!: (proof: ExecutionProof | undefined) => void;
	let markEntered!: () => void;
	const proofPromise = new Promise<ExecutionProof | undefined>((r) => {
		resolveProof = r;
	});
	const entered = new Promise<void>((r) => {
		markEntered = r;
	});
	return {
		host: {
			adapterHooks: () => ({
				verifyExecution: () => {
					count += 1;
					if (count === 1) markEntered();
					return proofPromise;
				},
			}),
		} as unknown as N1LocalHost["host"],
		entries: () => count,
		entered,
		resolve: (proof) => resolveProof(proof),
	};
}

/** Read the gate-derived parent decision_ref from the REAL persisted gate. */
function r5ParentRef(): string {
	try {
		const gates = path.join(root, "_autopilot", "gates");
		for (const name of fs.readdirSync(gates)) {
			if (!name.endsWith(".md")) continue;
			const text = fs.readFileSync(path.join(gates, name), "utf8");
			const m = /decision_ref:\s*["']?([^"'\s]+)["']?/.exec(text) ?? /(dp-gate-approve:[^\s"']+)/.exec(text);
			if (m?.[1]) return m[1];
		}
	} catch {
		// fall through to the fixture constant; alignment then simply fails
		// closed before the verifier (an honest boundary, not a hung test).
	}
	return PARENT_DP;
}

/** HYPOTHETICAL executor + offer certificates aligned to the gate binding. */
function r5Certificates(localRef: string, parentRef: string, executor: string, materialV: string, basisV: string) {
	const execCert: LocalTrustedExecutorCertificate = {
		current: true,
		local_ref: localRef,
		run_id: "r5:fixture:run",
		tool_call_id: "r5:fixture:call",
		executor,
	};
	const offerCert: LocalTrustedOfferCertificate = {
		current: true,
		current_by_matter: true,
		offer_id: "r5:fixture:offer",
		local_ref: localRef,
		parent_decision_id: parentRef,
		parent_matter_version: "v1",
		matter_ref: MATTER,
		matter_version: MATTER_VERSION,
		canonical_material_digest: materialV,
		canonical_catalog_digest: basisV,
		target_dp: "dp-pm-steer",
		selected_action: "continue",
		selected_basis_id: "b1",
		basis_applies_to: ["continue", "narrow"],
	};
	return { readTrustedExecutor: () => execCert, readCurrentOffer: () => offerCert };
}

/** Commit a REAL selection + execution via the frozen store. Returns the real
 *  write codes; a non-written code is an honest alignment boundary, never an
 *  asserted success and never a hand-written record. */
async function r5Commit(localRef: string, parentRef: string, window: string, executor: string): Promise<string> {
	const base = trustedContext();
	const adapter: LocalSelectionHostAdapter = {
		readTrustedContext: async () => ({
			...base,
			self_claim_id: window,
			expected: { ...base.expected, parent_decision_id: parentRef },
		}),
		verifyExecution: async (request): Promise<ExecutionProof> => ({
			action_ref: request.action_ref,
			result_ref: request.result_ref,
			verifier_ref: "target-verifier:1",
			target_digest: TARGET_DIGEST,
			observed_effect: request.observed_effect,
			effect_state: "known",
			local_ref: request.local_ref,
			executor: request.executor,
		}),
	};
	const store = new LocalSelectionStore({
		agenticdoc_root: root,
		key: KEY,
		host_adapter: adapter,
		lock_options: { retries: 16, baseDelayMs: 3 },
	});
	try {
		const sel = await store.commitSelection({
			source: "pm",
			local_ref: localRef,
			selection: selectionFields({ parent_decision_ref: { kind: "dp", decision_id: parentRef } }),
		});
		const exe = await store.appendExecution({ ...execRequest(), local_ref: localRef, executor });
		return `selection=${sel.code}/execution=${exe.code}`;
	} catch (err) {
		return `threw=${String(err)}`;
	}
}

interface R5Case {
	out: Record<string, unknown>;
	entries: number;
	commit: string;
	driftApplied: boolean;
}

interface R5RunOptions {
	params?: Record<string, unknown>;
	materialDigest?: string;
}

interface R5Mutation {
	target: string;
	beforeBytes: Buffer;
	afterBytes: Buffer;
	beforeValue: string;
	afterValue: string;
	expectedValue: string;
}

type R5Drift = () => R5Mutation;

const R5_COMMIT_WRITTEN = "selection=written/execution=written";
const R5_CONTROL_REASON = "missing-interface:verifyExecution (independent execution/result verifier unavailable)";
const R5_AFTER_VERIFIER_REASON = "source-evidence-not-current:after-verifier";
const R5_BOUNDARY_REASONS = {
	"no-certificates":
		"missing-interface:readTrustedExecutor (current run and actual toolCallId executor certificate unavailable)",
	"executor-only":
		"missing-interface:readCurrentOffer (current offer canonical material/context/catalog/matter/version/target/choice/basis certificate unavailable)",
} as const;

function r5Mutation(
	target: string,
	beforeBytes: Buffer,
	readValue: (bytes: Buffer) => string,
	write: () => void,
	expectedValue: string,
	targetPath: string,
): R5Mutation {
	const beforeValue = readValue(beforeBytes);
	write();
	const afterBytes = fs.readFileSync(targetPath);
	return { target, beforeBytes, afterBytes, beforeValue, afterValue: readValue(afterBytes), expectedValue };
}

function r5AssertMutation(mutation: R5Mutation): void {
	expect(mutation.beforeValue, `${mutation.target} field was absent`).not.toBe("");
	expect(mutation.afterBytes.equals(mutation.beforeBytes), `${mutation.target} bytes were unchanged`).toBe(false);
	expect(mutation.afterValue, `${mutation.target} field value was unchanged`).not.toBe(mutation.beforeValue);
	expect(mutation.afterValue, `${mutation.target} field value was not the targeted value`).toBe(
		mutation.expectedValue,
	);
}

/** Explicit bounded wait for the verifier-entry event; a missed entry fails
 *  instead of being hidden by an unchecked sleep. The timer is always cleared. */
async function r5AwaitVerifierEntry(hv: R5Verifier): Promise<void> {
	let timer: ReturnType<typeof setTimeout> | undefined;
	const timeout = new Promise<never>((_, reject) => {
		timer = setTimeout(() => reject(new Error("R5 registered path did not enter the verifier within 2000ms")), 2000);
	});
	try {
		await Promise.race([hv.entered, timeout]);
	} finally {
		if (timer !== undefined) clearTimeout(timer);
	}
}

/** Full HYPOTHETICAL injection + real committed records + registered tool call.
 *  The verifier-entry event is awaited and required; the targeted drift is
 *  asserted from persisted bytes/field values during the suspension. The
 *  deferred proof Promise and the tool Promise are always settled, including
 *  when an assertion fails. */
async function r5Run(h: N1Harness, localRef: string, drift?: R5Drift, options: R5RunOptions = {}): Promise<R5Case> {
	const window = windowClaimId();
	const parentRef = r5ParentRef();
	const executor = "r5:fixture:executor";
	const materialV =
		options.materialDigest ?? createHash("sha256").update(canonicalStateJson(h.baseParams.material)).digest("hex");
	const basisV = createHash("sha256").update(canonicalStateJson(h.baseParams.preparation)).digest("hex");
	const hv = r5Verifier();
	const projection = { material_digest: MATERIAL_DIGEST, basis_digest: BASIS_DIGEST, parent_decision_id: parentRef };
	h.localHost.certificates = r5Certificates(localRef, parentRef, executor, materialV, basisV);
	h.localHost.submitHandle = { hostExpectedFor: () => projection } as unknown as N1LocalHost["submitHandle"];
	h.localHost.host = hv.host;
	const commit = await r5Commit(localRef, parentRef, window, executor);
	const invokeParams = { ...h.baseParams, ...options.params, local_ref: localRef };
	const pending = h.invokeTool(invokeParams);
	void pending.catch(() => undefined);
	let entered = 0;
	let driftApplied = false;
	let mutationTarget = "none";
	let settled: PromiseSettledResult<Record<string, unknown>> | undefined;
	try {
		await r5AwaitVerifierEntry(hv);
		entered = hv.entries();
		expect(entered, "registered path did not enter the suspended verifier exactly once").toBe(1);
		if (drift !== undefined) {
			const mutation = drift();
			r5AssertMutation(mutation);
			mutationTarget = mutation.target;
			driftApplied = true;
		}
	} finally {
		hv.resolve(undefined);
		const [first] = await Promise.allSettled([pending]);
		settled = first;
		const observed = settled?.status === "fulfilled" ? settled.value : undefined;
		r5Log(
			`R5_CASE localRef=${localRef} verifier_entries=${entered} drift_applied=${driftApplied} mutation=${mutationTarget} commit=${commit} state=${observed ? String(observed.state) : "tool-error"} reason=${observed ? String(observed.reason) : "tool-error"}`,
		);
	}
	if (settled?.status === "rejected") throw settled.reason;
	if (settled?.status !== "fulfilled") throw new Error("R5 registered tool call did not settle");
	return { out: settled.value, entries: entered, commit, driftApplied };
}

function r5SharedPath(h: N1Harness): string {
	const name = fs.readdirSync(h.followupDir).find((n) => n.endsWith(".json") && !n.endsWith(".local.json"));
	return path.join(h.followupDir, name ?? "");
}

function r5JsonFieldValue(bytes: Buffer, field: string): string {
	const row = JSON.parse(bytes.toString("utf8")) as Record<string, unknown>;
	const value = row[field];
	return typeof value === "string" ? value : "";
}

function r5GateFieldValue(bytes: Buffer, field: string): string {
	const match = new RegExp(`^${field}:\\s*(.*)$`, "m").exec(bytes.toString("utf8"));
	return match?.[1]?.trim() ?? "";
}

function r5DriftSidecarRef(h: N1Harness): R5Drift {
	return () => {
		const beforeBytes = fs.readFileSync(h.sidecarPath);
		return r5Mutation(
			"sidecar.local_ref",
			beforeBytes,
			(bytes) => r5JsonFieldValue(bytes, "local_ref"),
			() => {
				const row = JSON.parse(beforeBytes.toString("utf8")) as Record<string, unknown>;
				fs.writeFileSync(h.sidecarPath, `${JSON.stringify({ ...row, local_ref: "r5:drifted-ref" })}\n`);
			},
			"r5:drifted-ref",
			h.sidecarPath,
		);
	};
}

/** Config-only drift: only auto_gate_mode changes. No watched key is tested. */
function r5DriftConfigOnly(h: N1Harness): R5Drift {
	return () => {
		const beforeBytes = fs.readFileSync(h.configPath);
		return r5Mutation(
			"config.auto_gate_mode",
			beforeBytes,
			(bytes) => r5JsonFieldValue(bytes, "auto_gate_mode"),
			() => {
				const row = JSON.parse(beforeBytes.toString("utf8")) as Record<string, unknown>;
				fs.writeFileSync(h.configPath, JSON.stringify({ ...row, auto_gate_mode: "off" }));
			},
			"off",
			h.configPath,
		);
	};
}

function r5DriftGate(field: string, value: string): R5Drift {
	return () => {
		const gates = path.join(root, "_autopilot", "gates");
		for (const name of fs.readdirSync(gates)) {
			if (!name.endsWith(".md")) continue;
			const p = path.join(gates, name);
			const beforeBytes = fs.readFileSync(p);
			if (r5GateFieldValue(beforeBytes, field) === "") continue;
			const changed = beforeBytes
				.toString("utf8")
				.replace(new RegExp(`^(${field}:\\s*)[^\\r\\n]+`, "m"), `$1${value}`);
			return r5Mutation(
				`gate.${field}`,
				beforeBytes,
				(bytes) => r5GateFieldValue(bytes, field),
				() => fs.writeFileSync(p, changed),
				value,
				p,
			);
		}
		throw new Error(`R5 gate field ${field} was not present for a targeted mutation`);
	};
}

describe("T07 R5 registered verifier-entry boundary (HYPOTHETICAL fixture host, NOT ProductionRuntimeHost proof)", () => {
	let savedMwPy: string | undefined;
	beforeAll(() => {
		savedMwPy = process.env.MW_PY;
		process.env.MW_PY = path.join(fileURLToPath(new URL("../../../multi-workers/", import.meta.url)), "mw.py");
	});
	afterAll(() => {
		if (savedMwPy === undefined) delete process.env.MW_PY;
		else process.env.MW_PY = savedMwPy;
	});

	const assertNoStaleConclusion = (h: N1Harness, out: Record<string, unknown>): void => {
		expect(out.state, JSON.stringify(out)).not.toBe("executed");
		expect(out.parent_released).toBe(false);
		expect(out.verified_source).toBeUndefined();
		expect(fs.readFileSync(r5SharedPath(h), "utf8")).toBe(h.sharedBytes);
		expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
		expect(h.decideCalls()).toBe(1);
		if (fs.existsSync(h.sidecarPath)) {
			const sidecar = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")) as Record<string, unknown>;
			expect(sidecar.local_progress).not.toBe("verified");
			for (const dpKey of ["status", "answer", "decision_id", "available", "business_decisions"])
				expect(sidecar).not.toHaveProperty(dpKey);
		}
	};

	const assertR5MainCase = (h: N1Harness, r: R5Case, expectedDrift: boolean, expectedReason: string): void => {
		assertNoStaleConclusion(h, r.out);
		expect(r.commit).toBe(R5_COMMIT_WRITTEN);
		expect(r.entries).toBe(1);
		expect(r.driftApplied).toBe(expectedDrift);
		expect(r.out.state).toBe("unknown");
		expect(r.out.reason).toBe(expectedReason);
	};

	it("unchanged registered-path control: verifier entry counter + controllable unresolved Promise", async () => {
		const h = await n1Harness();
		const r = await r5Run(h, "r5:control");
		assertR5MainCase(h, r, false, R5_CONTROL_REASON);
	});

	const driftCases: Array<[string, (h: N1Harness) => R5Drift]> = [
		["persisted local_ref", r5DriftSidecarRef],
		["gate version", () => r5DriftGate("substantive_version", "v1-R5-DRIFT")],
		["gate business", () => r5DriftGate("business", "reject")],
		["gate effect", () => r5DriftGate("effect", "done")],
		// Config-only: auto_gate_mode is changed; no actual watched key is tested.
		["config-only", r5DriftConfigOnly],
	];

	it.each(driftCases)("no stale conclusion on %s drift during verifier suspension", async (_label, makeDrift) => {
		const h = await n1Harness();
		const r = await r5Run(h, `r5:drift:${_label.replace(/\s+/g, "-")}`, makeDrift(h));
		assertR5MainCase(h, r, true, R5_AFTER_VERIFIER_REASON);
	});

	// Precise first-boundary chain, WITHOUT committed records: with a real
	// verifier-entry counter injected at every level, the registered path must
	// refuse BEFORE the verifier (entries === 0). This is explicitly NOT
	// verifier-entered coverage. Each level gets a fresh harness (fresh tmp).
	const boundaryLevels = ["no-certificates", "executor-only"] as const;
	it.each(boundaryLevels)("boundary %s refuses before the verifier (counter 0)", async (level) => {
		const h = await n1Harness();
		const hv = r5Verifier();
		h.localHost.host = hv.host;
		if (level === "executor-only") {
			h.localHost.certificates = {
				readTrustedExecutor: () => ({
					current: true,
					local_ref: "r5:boundary",
					run_id: "r5:b:run",
					tool_call_id: "r5:b:call",
					executor: "r5:boundary:executor",
				}),
				readCurrentOffer: () => undefined,
			};
		}
		let out: Record<string, unknown>;
		try {
			out = await h.invokeTool({ ...h.baseParams, local_ref: "r5:boundary" });
		} finally {
			hv.resolve(undefined);
		}
		r5Log(
			`R5_BOUNDARY level=${level} verifier_entries=${hv.entries()} state=${String(out.state)} reason=${String(out.reason)}`,
		);
		expect(hv.entries()).toBe(0);
		expect(out.state).not.toBe("executed");
		expect(out.reason).toBe(R5_BOUNDARY_REASONS[level]);
		expect(out.parent_released).toBe(false);
		expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
	});
});

// ─────────────────────────────────────────────────────────────────────────────
// T07 R6 — registered verifier-ENTRY coverage for the three retained ACTUAL
// watch-object, source-card and worker-evidence drift dimensions.
//
// FIXTURE CLASSIFICATION: executor/offer certificates, submitHandle projection
// and host verifier remain HYPOTHETICAL FIXTURES, NOT a ProductionRuntimeHost
// positive. Local selection/execution records are written only by the real
// frozen LocalSelectionStore. No passing proof or authenticated production
// record is hand-written. The unchanged controls resolve the verifier with
// undefined proof and must reach missing-interface:verifyExecution.
// ─────────────────────────────────────────────────────────────────────────────

const R6_WATCH_DRIFT_KEY = "r6:watch-drift";

function r6WatchKey(bytes: Buffer): string {
	const row = JSON.parse(bytes.toString("utf8")) as { key?: unknown };
	return typeof row.key === "string" ? row.key : "";
}

/** Mutate the ACTUAL watch object passed to registerPmGateFollowup. The
 *  canonical before/after bytes are a real field/byte mutation, not a renamed
 *  config label. */
function r6WatchMutation(h: N1Harness, changedKey: string): R5Mutation {
	const beforeBytes = Buffer.from(canonicalStateJson(h.watch), "utf8");
	const beforeValue = r6WatchKey(beforeBytes);
	h.watch.key = changedKey;
	const afterBytes = Buffer.from(canonicalStateJson(h.watch), "utf8");
	return {
		target: "watch.key",
		beforeBytes,
		afterBytes,
		beforeValue,
		afterValue: r6WatchKey(afterBytes),
		expectedValue: changedKey,
	};
}

function r6NoStaleConclusion(h: N1Harness, out: Record<string, unknown>): void {
	expect(out.state, JSON.stringify(out)).not.toBe("executed");
	expect(out.parent_released).toBe(false);
	expect(out.verified_source).toBeUndefined();
	expect(fs.readFileSync(r5SharedPath(h), "utf8")).toBe(h.sharedBytes);
	expect(fs.readFileSync(h.ledgerPath, "utf8")).toBe(h.ledgerBytes);
	expect(h.decideCalls()).toBe(1);
	if (fs.existsSync(h.sidecarPath)) {
		const sidecar = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")) as Record<string, unknown>;
		expect(sidecar.local_progress).not.toBe("verified");
		for (const dpKey of ["status", "answer", "decision_id", "available", "business_decisions"])
			expect(sidecar).not.toHaveProperty(dpKey);
	}
}

function r6AssertMainCase(h: N1Harness, r: R5Case, expectedDrift: boolean, expectedReason: string): void {
	r6NoStaleConclusion(h, r.out);
	expect(r.commit).toBe(R5_COMMIT_WRITTEN);
	expect(r.entries).toBe(1);
	expect(r.driftApplied).toBe(expectedDrift);
	expect(r.out.state).toBe("unknown");
	expect(r.out.reason).toBe(expectedReason);
}

const R6_SOURCE_CARD_STEM = "r6-source-card";
const R6_SOURCE_CARD_DRIFT = "r6:source-card-drift";
const R6_WORKER = "r6-worker-evidence";
const R6_WORKER_INITIAL_FACE = "r6-worker-initial-write-face";
const R6_WORKER_DRIFT_FACE = "r6-worker-drift-write-face";

function r6Digest(value: unknown): string {
	return createHash("sha256").update(canonicalStateJson(value)).digest("hex");
}

interface R6SourceCardFixture {
	stem: string;
	cardPath: string;
	cardText: string;
	materialDigest: string;
}

/** Write an ACTUAL source card and establish the resulting material digest
 *  BEFORE the registered verifier-entering invocation. The three extracted
 *  sections reproduce the PM fixture's original material exactly. */
function r6SourceCardFixture(h: N1Harness, stem = R6_SOURCE_CARD_STEM): R6SourceCardFixture {
	const material = h.baseParams.material as Record<string, unknown>;
	const goal = String(material.task_goal);
	const requirements = String(material.task_requirements);
	const deliverables = String(material.task_deliverables);
	const cardText = [
		"## Context",
		goal,
		"",
		"## Requirements",
		requirements,
		"",
		"## Deliverables",
		deliverables,
		"",
	].join("\n");
	const cardPath = path.join(root, KEY, "tasks", `${stem}.md`);
	fs.mkdirSync(path.dirname(cardPath), { recursive: true });
	fs.writeFileSync(cardPath, cardText, "utf8");
	const sections = extractCardSections(cardText);
	expect(sections.context).toBe(goal);
	expect(sections.requirements).toBe(requirements);
	expect(sections.deliverables).toBe(deliverables);
	const derivedMaterial = {
		...material,
		task_goal: sections.context,
		task_requirements: sections.requirements,
		task_deliverables: sections.deliverables,
	};
	const materialDigest = r6Digest(derivedMaterial);
	r5Log(`R6_SOURCE_CARD_SETUP stem=${stem} card_sha256=${r6Digest(cardText)} material_digest=${materialDigest}`);
	return { stem, cardPath, cardText, materialDigest };
}

function r6SourceCardMutation(fixture: R6SourceCardFixture): R5Mutation {
	const beforeBytes = fs.readFileSync(fixture.cardPath);
	const readGoal = (bytes: Buffer): string => extractCardSections(bytes.toString("utf8")).context;
	const beforeGoal = readGoal(beforeBytes);
	return r5Mutation(
		"source_card.task_goal",
		beforeBytes,
		readGoal,
		() => {
			fs.writeFileSync(
				fixture.cardPath,
				beforeBytes.toString("utf8").replace(beforeGoal, R6_SOURCE_CARD_DRIFT),
				"utf8",
			);
		},
		R6_SOURCE_CARD_DRIFT,
		fixture.cardPath,
	);
}

/** Re-derive the ACTUAL worker evidence snapshot from the real queue,
 *  task.md and trace.log using the same trusted readers as the consumer. */
function r6WorkerEvidenceSnapshot(worker: string): string {
	const observation = captureDecisionTaskState(new WorkerStore(root), KEY, worker);
	const taskDir = path.join(root, KEY, "workers", worker);
	const progress = readTaskProgress(taskDir);
	if (progress === undefined) throw new Error("R6 worker trace.log did not produce a real progress snapshot");
	const writeFace = extractCardSections(fs.readFileSync(path.join(taskDir, "task.md"), "utf8")).extras.find(
		(extra) => extra.title === "写入允许面",
	)?.body;
	const { startTs, endTs, exitCode, lastAction, checkpoint } = progress;
	return canonicalStateJson({
		task_key: worker,
		status: observation.status,
		startTs,
		endTs,
		exitCode,
		lastAction,
		checkpoint,
		lastHeartbeat: progress.heartbeat?.lastTs,
		writeFace,
	});
}

interface R6WorkerFixture {
	worker: string;
	taskPath: string;
	tracePath: string;
	queuePath: string;
	beforeEvidence: string;
	materialDigest: string;
}

/** Create a REAL source_worker queue row, task.md and trace.log, then read the
 *  actual evidence snapshot and resulting material digest before invocation. */
function r6WorkerFixture(h: N1Harness): R6WorkerFixture {
	const worker = R6_WORKER;
	const taskDir = path.join(root, KEY, "workers", worker);
	const taskPath = path.join(taskDir, "task.md");
	const tracePath = path.join(taskDir, "trace.log");
	const queuePath = path.join(root, "_workers.parallel");
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(taskPath, `## 写入允许面\n${R6_WORKER_INITIAL_FACE}\n`, "utf8");
	fs.writeFileSync(
		tracePath,
		`[START] ${NOW} task=${worker} type=coding phases=-\n[HEARTBEAT] ${NOW} task=${worker} phase=-\n[TOOL] ${NOW} read task.md\n`,
		"utf8",
	);
	fs.writeFileSync(
		queuePath,
		`# mw-queue:v2\n${[worker, "running", "pi", "local", taskPath, NOW, NOW, "fixture", "manual"].join(" | ")}\n`,
		"utf8",
	);
	const beforeEvidence = r6WorkerEvidenceSnapshot(worker);
	const derivedMaterial = {
		...(h.baseParams.material as Record<string, unknown>),
		worker_execution: beforeEvidence,
	};
	const materialDigest = r6Digest(derivedMaterial);
	r5Log(
		`R6_WORKER_SETUP worker=${worker} evidence_sha256=${r6Digest(beforeEvidence)} material_digest=${materialDigest}`,
	);
	return { worker, taskPath, tracePath, queuePath, beforeEvidence, materialDigest };
}

interface R6WorkerMutation {
	mutation: R5Mutation;
	beforeEvidence: string;
	afterEvidence: string;
}

function r6WorkerEvidenceMutation(fixture: R6WorkerFixture): R6WorkerMutation {
	const beforeBytes = fs.readFileSync(fixture.taskPath);
	const readFace = (bytes: Buffer): string =>
		extractCardSections(bytes.toString("utf8")).extras.find((extra) => extra.title === "写入允许面")?.body ?? "";
	const beforeFace = readFace(beforeBytes);
	const mutation = r5Mutation(
		"worker_evidence.writeFace",
		beforeBytes,
		readFace,
		() => {
			fs.writeFileSync(
				fixture.taskPath,
				beforeBytes.toString("utf8").replace(beforeFace, R6_WORKER_DRIFT_FACE),
				"utf8",
			);
		},
		R6_WORKER_DRIFT_FACE,
		fixture.taskPath,
	);
	const afterEvidence = r6WorkerEvidenceSnapshot(fixture.worker);
	return { mutation, beforeEvidence: fixture.beforeEvidence, afterEvidence };
}

describe("T07 R6 registered verifier-entry actual drift (HYPOTHETICAL fixture host, NOT ProductionRuntimeHost proof)", () => {
	it("actual watch object unchanged control reaches missing-interface:verifyExecution after entry", async () => {
		const watch: R6WatchState = { key: KEY };
		const h = await n1Harness(watch);
		expect(h.watch).toBe(watch);
		const beforeBytes = Buffer.from(canonicalStateJson(h.watch), "utf8");
		const r = await r5Run(h, "r6:watch:control");
		r6AssertMainCase(h, r, false, R5_CONTROL_REASON);
		expect(h.watch.key).toBe(KEY);
		expect(Buffer.from(canonicalStateJson(h.watch), "utf8").equals(beforeBytes)).toBe(true);
	});

	it("actual watch object key drift rejects at exact after-verifier boundary", async () => {
		const watch: R6WatchState = { key: KEY };
		const h = await n1Harness(watch);
		expect(h.watch).toBe(watch);
		let mutation: R5Mutation | undefined;
		const r = await r5Run(h, "r6:watch:drift", () => {
			mutation = r6WatchMutation(h, R6_WATCH_DRIFT_KEY);
			return mutation;
		});
		r6AssertMainCase(h, r, true, R5_AFTER_VERIFIER_REASON);
		if (mutation === undefined) throw new Error("R6 watch mutation was not applied during verifier suspension");
		expect(mutation.target).toBe("watch.key");
		expect(mutation.beforeValue).toBe(KEY);
		expect(mutation.afterValue).toBe(R6_WATCH_DRIFT_KEY);
		expect(mutation.beforeBytes.equals(mutation.afterBytes)).toBe(false);
		expect(h.watch.key).toBe(R6_WATCH_DRIFT_KEY);
	});

	it("actual source_card unchanged control reaches missing-interface:verifyExecution after entry", async () => {
		const h = await n1Harness();
		const card = r6SourceCardFixture(h);
		const beforeBytes = fs.readFileSync(card.cardPath);
		const r = await r5Run(h, "r6:source-card:control", undefined, {
			params: { source_card: card.stem },
			materialDigest: card.materialDigest,
		});
		r6AssertMainCase(h, r, false, R5_CONTROL_REASON);
		expect(fs.readFileSync(card.cardPath).equals(beforeBytes)).toBe(true);
		expect(card.materialDigest).toBe(r6Digest(h.baseParams.material));
		const sidecar = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")) as Record<string, unknown>;
		expect(sidecar.material_version).toBe(card.materialDigest);
	});

	it("actual source_card byte drift rejects at exact after-verifier boundary", async () => {
		const h = await n1Harness();
		const card = r6SourceCardFixture(h);
		const beforeBytes = fs.readFileSync(card.cardPath);
		let mutation: R5Mutation | undefined;
		const r = await r5Run(
			h,
			"r6:source-card:drift",
			() => {
				mutation = r6SourceCardMutation(card);
				return mutation;
			},
			{ params: { source_card: card.stem }, materialDigest: card.materialDigest },
		);
		r6AssertMainCase(h, r, true, R5_AFTER_VERIFIER_REASON);
		if (mutation === undefined) throw new Error("R6 source-card mutation was not applied during verifier suspension");
		expect(mutation.target).toBe("source_card.task_goal");
		expect(mutation.beforeValue).toBe(String((h.baseParams.material as Record<string, unknown>).task_goal));
		expect(mutation.afterValue).toBe(R6_SOURCE_CARD_DRIFT);
		expect(mutation.beforeBytes.equals(mutation.afterBytes)).toBe(false);
		expect(fs.readFileSync(card.cardPath).equals(beforeBytes)).toBe(false);
		expect(extractCardSections(fs.readFileSync(card.cardPath, "utf8")).context).toBe(R6_SOURCE_CARD_DRIFT);
	});

	it("actual source_worker evidence unchanged control reaches missing-interface:verifyExecution after entry", async () => {
		const h = await n1Harness();
		const worker = r6WorkerFixture(h);
		const beforeBytes = fs.readFileSync(worker.taskPath);
		const r = await r5Run(h, "r6:worker:control", undefined, {
			params: { source_worker: worker.worker },
			materialDigest: worker.materialDigest,
		});
		r6AssertMainCase(h, r, false, R5_CONTROL_REASON);
		expect(fs.readFileSync(worker.taskPath).equals(beforeBytes)).toBe(true);
		expect(r6WorkerEvidenceSnapshot(worker.worker)).toBe(worker.beforeEvidence);
		const sidecar = JSON.parse(fs.readFileSync(h.sidecarPath, "utf8")) as Record<string, unknown>;
		expect(sidecar.material_version).toBe(worker.materialDigest);
	});

	it("actual source_worker evidence drift rejects at exact after-verifier boundary", async () => {
		const h = await n1Harness();
		const worker = r6WorkerFixture(h);
		const beforeBytes = fs.readFileSync(worker.taskPath);
		let mutation: R6WorkerMutation | undefined;
		const r = await r5Run(
			h,
			"r6:worker:drift",
			() => {
				mutation = r6WorkerEvidenceMutation(worker);
				return mutation.mutation;
			},
			{ params: { source_worker: worker.worker }, materialDigest: worker.materialDigest },
		);
		r6AssertMainCase(h, r, true, R5_AFTER_VERIFIER_REASON);
		if (mutation === undefined)
			throw new Error("R6 worker-evidence mutation was not applied during verifier suspension");
		expect(mutation.mutation.target).toBe("worker_evidence.writeFace");
		expect(mutation.mutation.beforeValue).toBe(R6_WORKER_INITIAL_FACE);
		expect(mutation.mutation.afterValue).toBe(R6_WORKER_DRIFT_FACE);
		expect(mutation.mutation.beforeBytes.equals(mutation.mutation.afterBytes)).toBe(false);
		expect(mutation.afterEvidence).not.toBe(mutation.beforeEvidence);
		expect(fs.readFileSync(worker.taskPath).equals(beforeBytes)).toBe(false);
		expect(r6WorkerEvidenceSnapshot(worker.worker)).toBe(mutation.afterEvidence);
	});
});

// ─────────────────────────────────────────────────────────────────────────────
// T07 M1 — genuine ProductionRuntimeHost → registered pm_gate_followup.
// The parent fixture above is an isolated, explicitly labelled trusted source.
// Selection/execution/proof are produced only by the registered submit tool,
// real tool_call/tool_result events, RuntimeExecutionController and the frozen
// LocalSelectionStore. No passing record/certificate is hand-written.
// ─────────────────────────────────────────────────────────────────────────────

interface M1ParentFixtureOutput {
	gate: string;
	gate_ref: string;
	logical_id: string;
	matter_ref: string;
	substantive_version: string;
	parent_basis: string;
	material: Record<string, unknown>;
	preparation: DecisionPreparation;
}

interface M1ToolResult {
	toolCallId: string;
	error: boolean;
	text: string;
	details: Record<string, unknown>;
}

function m1Details(value: unknown): Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}

async function m1Tool(h: Harness, name: string, args: Record<string, unknown>): Promise<M1ToolResult> {
	const toolCallId = randomUUID();
	h.setResponses([
		fauxAssistantMessage([fauxToolCall(name, args, { id: toolCallId })], { stopReason: "toolUse" }),
		fauxAssistantMessage("done"),
	]);
	await h.session.prompt(`m1 ${name}`);
	const result = h.session.messages.find(
		(message) => message.role === "toolResult" && message.toolCallId === toolCallId,
	);
	if (!result || result.role !== "toolResult") throw new Error(`M1 tool result missing: ${name}`);
	return {
		toolCallId,
		error: result.isError,
		text: getMessageText(result),
		details: m1Details(result.details),
	};
}

function m1Card(
	claim: string,
	taskKey: string,
	deadline: string,
	material: Record<string, unknown>,
	budgetSteps: number,
): string {
	return [
		`owning_pm_claim: ${claim}`,
		"",
		"## 上下文",
		String(material.task_goal),
		"",
		"## 要求",
		String(material.task_requirements),
		"",
		"## 交付格式",
		String(material.task_deliverables),
		"",
		"## 事项预算事实",
		`- \`budget_ref\`: \`tasks/${taskKey}.md#事项预算事实\``,
		`- \`matter_ref\`: \`${KEY}/${taskKey}\``,
		`- \`deadline\`: \`${deadline}\``,
		`- \`max_steps\`: ${budgetSteps}`,
		`- \`remaining_cost\`: ${budgetSteps}`,
		"- `no_progress_limit`: 2",
		"- `steps_consumed`: 0",
		"- `cost_consumed`: 0",
		"- `no_progress_count`: 0",
		"- `cost_unit`: 1 cost unit = 1 tool call",
		"- `source_refs`: card SHA, `_index.parallel`, `task.md`",
		"",
	].join("\n");
}

describe("T07 M1 production-runtime registered follow-up positive", () => {
	it.each([
		["disabled", 3],
		["disabled", 1],
		["over-cap", 3],
	] as const)(
		"real default %s request uses the registered host boundary (matter budget %i)",
		async (failureMode, budgetSteps) => {
			const previousMwPy = process.env.MW_PY;
			const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
			process.env.MW_PY = path.join(mw, "mw.py");
			let h: Harness | undefined;
			let capServer: Server | undefined;
			let posts = 0;
			try {
				const claim = currentClaimId();
				const taskKey = "m1-task";
				const target = "m1.txt";
				const now = Math.floor(Date.now() / 1000) * 1000;
				const startedAt = new Date(now - 60_000).toISOString().replace(".000Z", "Z");
				const deadline = new Date(now + 1_800_000).toISOString().replace(".000Z", "Z");
				const clock = { at: now };
				const projectRoot = tmp;
				const doc = root;
				expect((await new IndexStore(doc).claim(KEY, claim, () => false)).ok).toBe(true);
				const initial = JSON.parse(
					execFileSync(
						PYTHON_EXE,
						[
							"-B",
							"-X",
							"utf8",
							"-c",
							registeredConsumerParentFixture,
							projectRoot,
							KEY,
							"gate",
							"dp-pm-steer",
							"steer",
							claim,
						],
						{ cwd: mw, encoding: "utf8", windowsHide: true },
					),
				) as M1ParentFixtureOutput;
				expect(initial.gate_ref.startsWith("dp-gate-approve:")).toBe(true);
				expect(initial.logical_id).toBe(initial.gate_ref.slice("dp-gate-approve:".length));
				expect(initial.matter_ref).toBe("task-main");
				expect(initial.substantive_version).toBe("v1");
				fs.mkdirSync(path.join(doc, KEY, "tasks"), { recursive: true });
				fs.mkdirSync(path.join(doc, "_autopilot"), { recursive: true });
				fs.writeFileSync(
					path.join(doc, "_autopilot", "config.json"),
					JSON.stringify({ enabled: true, auto_gate_mode: "live" }),
					"utf8",
				);
				expect(
					(
						await answerPreparedGate({
							gateFile: initial.gate,
							lockFile: path.join(projectRoot, ".mw", "gates.lock"),
							decision: "steer",
							matterRef: initial.matter_ref,
							substantiveVersion: initial.substantive_version,
							note: "Prepared PM plan",
							modelBasis: initial.parent_basis,
							decisionRef: initial.gate_ref,
							answeredBy: claim,
						})
					).ok,
				).toBe(true);
				if (failureMode === "over-cap")
					initial.material.pm_decision_background = `${initial.material.pm_decision_background}${"x".repeat(150_000)}`;
				const cardText = m1Card(claim, taskKey, deadline, initial.material, budgetSteps);
				const cardPath = path.join(doc, KEY, "tasks", `${taskKey}.md`);
				fs.writeFileSync(cardPath, cardText, "utf8");
				const cardSha = sha256EolNormalizedBytes(Buffer.from(cardText));
				const envelope = path.join(projectRoot, `${taskKey}.md`);
				fs.writeFileSync(
					envelope,
					`card_path: tasks/${taskKey}.md\ncard_sha256: ${cardSha}\nwrite_face: ${target}\n`,
					"utf8",
				);
				const targetFile = path.join(projectRoot, target);
				fs.writeFileSync(targetFile, `original-${taskKey}`, "utf8");
				const host = new ProductionRuntimeHost(projectRoot, () => clock.at);
				let handle: SubmitDecisionHostHandle | undefined;
				const bodies: string[] = [];
				fs.writeFileSync(
					path.join(projectRoot, ".mw", "decide-points.json"),
					JSON.stringify({ points: { "dp-pm-steer": { enabled: false } } }),
				);
				fs.writeFileSync(path.join(projectRoot, ".mw", "decide.json"), JSON.stringify({ enabled: true }));
				if (failureMode === "over-cap") {
					capServer = createServer((_request, response) => {
						posts += 1;
						response.writeHead(500).end("unexpected DP POST");
					});
					await new Promise<void>((resolve) => capServer!.listen(0, "127.0.0.1", resolve));
					const address = capServer.address();
					if (!address || typeof address === "string") throw new Error("loopback address unavailable");
					fs.writeFileSync(
						path.join(projectRoot, ".mw", "decide-points.json"),
						JSON.stringify({ points: { "dp-pm-steer": { enabled: true } } }),
					);
					fs.writeFileSync(
						path.join(projectRoot, ".mw", "decide.json"),
						JSON.stringify({
							enabled: true,
							base_url: `http://127.0.0.1:${address.port}`,
							api_key: "synthetic-m1-cap",
							max_retries: 0,
							timeout_s: 2,
						}),
					);
				}
				h = await createHarness({
					// The over-cap case deliberately carries 150k+ characters of real
					// prepared material through the REGISTERED tool call, so this fixture
					// session needs a context window that can actually hold it instead of
					// compacting mid-proof and losing the queued faux turn.
					models: [{ id: "faux-1", contextWindow: 512_000, maxTokens: 65_536 }],
					extensionFactories: [
						(pi) => {
							registerProductionRuntimeEvents(pi, host);
							handle = registerSubmitDecisionHandoffTool(pi, {
								projectDir: projectRoot,
								hostRuntime: host,
								runtimeHost: host.adapterHooks(),
								clock: () => clock.at,
							});
							for (const name of ["read", "ls", "find", "grep", "write"]) {
								pi.registerTool({
									name,
									label: name,
									description: "isolated M1 fixture tool",
									parameters: Type.Object({ path: Type.String(), content: Type.Optional(Type.String()) }),
									execute: async (_id, params) => {
										bodies.push(name);
										if (name === "write")
											fs.writeFileSync(path.join(projectRoot, params.path), params.content ?? "changed");
										return {
											content: [
												{
													type: "text",
													text:
														name === "read"
															? fs.readFileSync(path.join(projectRoot, params.path), "utf8")
															: "fixture-result",
												},
											],
											details: {},
										};
									},
								});
							}
							registerPmGateFollowup(pi, projectRoot, new WorkerStore(doc), { key: KEY }, undefined, {
								submitHandle: handle,
								host,
							});
						},
					],
				});
				await h.session.bindExtensions({});
				if (!handle) throw new Error("M1 submit handle missing");
				const registered = host.registerPmDispatch({
					key: KEY,
					taskKey,
					claimId: claim,
					taskMdPath: envelope,
					dispatchedAt: startedAt,
				});
				expect(registered.ok, JSON.stringify(registered)).toBe(true);
				const choice = "direct-exec";
				const basisId = String(initial.preparation.basis_catalog[0].id);
				const baseParams: Record<string, unknown> = {
					gate_id: path.basename(initial.gate, ".md"),
					source_card: taskKey,
					restricted_action: choice,
					material: initial.material,
					preparation: initial.preparation,
				};
				const sourceInput = { key: KEY, claimId: claim, cardPath: `tasks/${taskKey}.md` };
				const sourceBefore = host.readPmDispatchSource(sourceInput);
				expect(sourceBefore.ok).toBe(true);
				expect(host.readPmDispatchSource({ ...sourceInput, cardPath: "tasks/unregistered.md" }).ok).toBe(false);
				expect(host.readPmDispatchSource({ ...sourceInput, cardPath: `tasks/../tasks/${taskKey}.md` }).ok).toBe(
					false,
				);
				expect(host.readPmDispatchSource({ ...sourceInput, claimId: `${claim}-foreign` }).ok).toBe(false);
				let rawChild = "";
				const originalSpawn = childProcess.spawn;
				const spawnObserver = vi
					.spyOn(childProcess, "spawn")
					.mockImplementation((...args: Parameters<typeof childProcess.spawn>) => {
						const child = originalSpawn(...args);
						child.stdout?.on("data", (chunk: Buffer) => {
							rawChild += chunk.toString();
						});
						child.stderr?.on("data", (chunk: Buffer) => {
							rawChild += chunk.toString();
						});
						return child;
					});
				syncBuiltinESMExports();
				let dpOut: Awaited<ReturnType<typeof m1Tool>>;
				try {
					dpOut = await m1Tool(h, "pm_gate_followup", baseParams);
				} finally {
					spawnObserver.mockRestore();
					syncBuiltinESMExports();
				}
				expect(dpOut.error, dpOut.text).toBe(false);
				let overCapIntent: Record<string, unknown> | undefined;
				if (failureMode === "over-cap") {
					// Prepared-book material uses the REAL default 32768-token
					// state+questions gate, not the legacy 8192-byte fitting path.
					expect(Buffer.byteLength(canonicalStateJson(initial.material), "utf8")).toBeGreaterThan(32768 * 4);
					const native = JSON.parse(rawChild.trim()) as Record<string, unknown>;
					expect(native, rawChild).toMatchObject({
						available: false,
						attempts: 0,
						transport_attempts: 0,
						escalated_reason: "budget-exhausted",
					});
					expect(String(native.detail)).toContain("max_state_plus_question_tokens=32768");
					expect(Number(/state=(\d+)/.exec(String(native.detail))?.[1])).toBeGreaterThanOrEqual(150_000 / 4);
					expect(native.truncated ?? []).toEqual([]);
					expect(dpOut.details, `${dpOut.text}\n${rawChild}`).toMatchObject({
						state: "failed",
						reason: "budget-exhausted",
						parent_released: false,
					});
					expect(posts).toBe(0);
					expect(initial.material.pm_decision_background).toContain("x".repeat(150_000));
					expect(bodies).toEqual([]);
					expect(host.countsSnapshot()).toMatchObject({
						selectionCommits: 0,
						reserves: 0,
						observes: 0,
						appends: 0,
					});
					const intents = fs
						.readdirSync(path.join(doc, KEY, "evidence", "decision-followups"))
						.filter((name) => name.endsWith(".json"));
					expect(intents).toHaveLength(1);
					const failedIntent = JSON.parse(
						fs.readFileSync(path.join(doc, KEY, "evidence", "decision-followups", intents[0]), "utf8"),
					) as Record<string, unknown>;
					expect(failedIntent.material_version).toBe(
						createHash("sha256").update(canonicalStateJson(initial.material)).digest("hex"),
					);
					expect(failedIntent.task_key).toBeNull();
					overCapIntent = failedIntent;
					// F3 closure: the real native cap refusal keeps the FULL material,
					// sends zero POST and truncates nothing, and STILL hands the PM a
					// lawful local offer. Continuing is required here — an early return
					// would leave the whole downstream continuation unproved.
					expect(dpOut.details.submit_offer, dpOut.text).toMatchObject({ submittable: true });
				} else {
					expect(dpOut.details).toMatchObject({ state: "failed", reason: "disabled", parent_released: false });
				}
				const metadata = m1Details(dpOut.details.submit_offer);
				expect(metadata, dpOut.text).toMatchObject({ submittable: true });
				const offerId = metadata.offer_id;
				const localRef = metadata.local_ref;
				if (typeof offerId !== "string" || typeof localRef !== "string")
					throw new Error("M1 prepared offer missing identity");
				const followupDir = path.join(doc, KEY, "evidence", "decision-followups");
				const sharedName = fs
					.readdirSync(followupDir)
					.find((name) => name.endsWith(".json") && !name.endsWith(".local.json"));
				const sharedPath = path.join(followupDir, sharedName ?? "");
				const ledgerPath = path.join(doc, "_autopilot", "decision-lifecycle.jsonl");
				const sharedBytes = fs.readFileSync(sharedPath, "utf8");
				const ledgerBytes = fs.readFileSync(ledgerPath, "utf8");
				const recovered = await m1Tool(h, "pm_gate_followup", baseParams);
				expect(recovered.details).toMatchObject({
					state: "failed",
					duplicate: true,
					submit_offer: { submittable: true, offer_id: offerId, local_ref: localRef },
				});
				expect(fs.readFileSync(sharedPath, "utf8")).toBe(sharedBytes);
				expect(fs.readFileSync(ledgerPath, "utf8")).toBe(ledgerBytes);
				const submitParams = { offer_id: offerId, choice, basis_id: basisId };
				const selectionFile = storedRecordPath(doc, KEY, "pm", undefined, localRef, SELECTION_FILE_SUFFIX);
				const expectRefused = async () => {
					const result = await m1Tool(h!, SUBMIT_DECISION_HANDOFF_TOOL, submitParams);
					expect(result.details, result.text).toMatchObject({
						status: "refused",
						selection_written: false,
						business_completed: false,
					});
					expect(fs.existsSync(selectionFile)).toBe(false);
					expect(fs.readFileSync(targetFile, "utf8")).toBe(`original-${taskKey}`);
					expect(host.countsSnapshot()).toMatchObject({
						selectionCommits: 0,
						reserves: 0,
						observes: 0,
						appends: 0,
					});
					return result;
				};
				fs.writeFileSync(cardPath, `${cardText}\nsource pin drift`);
				await expectRefused();
				fs.writeFileSync(cardPath, cardText);
				const indexPath = path.join(doc, "_index.parallel");
				const indexBytes = fs.readFileSync(indexPath, "utf8");
				fs.writeFileSync(indexPath, indexBytes.replace(claim, `${claim}-foreign`));
				await expectRefused();
				fs.writeFileSync(indexPath, indexBytes);
				const autopilotConfig = path.join(doc, "_autopilot", "config.json");
				const configBytes = fs.readFileSync(autopilotConfig, "utf8");
				fs.writeFileSync(autopilotConfig, JSON.stringify({ enabled: true, auto_gate_mode: "live", paused: true }));
				await expectRefused();
				fs.writeFileSync(autopilotConfig, configBytes);
				// Negative-only removal: no synthetic passing receipt is ever minted.
				fs.writeFileSync(
					ledgerPath,
					ledgerBytes
						.split("\n")
						.filter((line) => !line || JSON.parse(line).lifecycle !== "consumed")
						.join("\n"),
				);
				await expectRefused();
				fs.writeFileSync(ledgerPath, ledgerBytes);
				clock.at = now + 1_800_001;
				await expectRefused();
				clock.at = now;
				expect(host.readPmDispatchSource(sourceInput)).toEqual(sourceBefore);
				// The REAL frozen store owns both failures; no success/proof seam.
				fs.mkdirSync(path.dirname(selectionFile), { recursive: true });
				const selectionLock = `${selectionFile}.lock`;
				fs.writeFileSync(selectionLock, "foreign-owner");
				const busy = await expectRefused();
				expect(busy.details.code).toBe("lock-busy");
				expect(fs.readFileSync(selectionLock, "utf8")).toBe("foreign-owner");
				fs.unlinkSync(selectionLock);
				const originalRename = fs.renameSync;
				const renameFault = vi.spyOn(fs, "renameSync").mockImplementation((from, to) => {
					if (String(to) === selectionFile) throw new Error("M1 negative selection persistence fault");
					originalRename(from, to);
				});
				syncBuiltinESMExports();
				try {
					const failedWrite = await expectRefused();
					expect(failedWrite.details.code).toBe("write-failed");
				} finally {
					renameFault.mockRestore();
					syncBuiltinESMExports();
				}
				const independentRead = await m1Tool(h, "read", { path: target });
				expect(independentRead.error, independentRead.text).toBe(false);
				const submit = await m1Tool(h, SUBMIT_DECISION_HANDOFF_TOOL, submitParams);
				expect(submit.error, submit.text).toBe(false);
				expect(submit.details).toMatchObject({ status: "planned", business_completed: false });
				const committed = handle.readCommittedSelection(submit.toolCallId);
				expect(committed?.record.action_state).toBe("planned");
				expect(committed?.record.business_completed).toBe(false);
				if (overCapIntent !== undefined) {
					// The committed plan carries the host projection of the FULL
					// over-cap material (never a truncated/contentless summary) and the
					// real cap endpoint was still never contacted.
					expect(committed?.record.material_digest).toBe(handle.hostExpectedFor(localRef)?.material_digest);
					expect(overCapIntent.material_version).toBe(
						createHash("sha256").update(canonicalStateJson(initial.material)).digest("hex"),
					);
					expect(posts).toBe(0);
				}
				const materialVersion = createHash("sha256").update(canonicalStateJson(initial.material)).digest("hex");
				const basisVersion = createHash("sha256").update(canonicalStateJson(initial.preparation)).digest("hex");
				const offerScope = {
					key: KEY,
					source: "pm" as const,
					claim_id: claim,
					parent_ref: initial.matter_ref,
					parent_decision_id: initial.gate_ref,
					parent_logical_id: initial.logical_id,
					parent_matter_version: initial.substantive_version,
					target_dp: "dp-pm-steer",
					material_version: materialVersion,
					basis_version: basisVersion,
					restricted_action: choice,
				};
				const executionScope = {
					key: KEY,
					source: "pm" as const,
					claim_id: claim,
				};
				const executorBeforeAction = host.currentExecutionCertificateFor(localRef, executionScope);
				const wrongLocalRefExecutor = host.currentExecutionCertificateFor("lref:wrong-local-ref", executionScope);
				const wrongClaimExecutor = host.currentExecutionCertificateFor(localRef, {
					...executionScope,
					claim_id: `${claim}-forged`,
				});
				const offerBeforeAction = handle.currentOfferCertificateFor?.(localRef, offerScope);
				const wrongParentOffer = handle.currentOfferCertificateFor?.(localRef, {
					...offerScope,
					parent_decision_id: "dp-gate-approve:forged-parent",
				});
				const wrongBasisOffer = handle.currentOfferCertificateFor?.(localRef, {
					...offerScope,
					basis_version: "forged-basis-version",
				});
				fs.writeFileSync(cardPath, `${cardText}\nsource drift after planned`);
				const blockedWrite = await m1Tool(h, "write", { path: target, content: "must-not-run" });
				expect(blockedWrite.error).toBe(true);
				expect(fs.readFileSync(targetFile, "utf8")).toBe(`original-${taskKey}`);
				expect(bodies).not.toContain("write");
				fs.writeFileSync(cardPath, cardText);
				const write = await m1Tool(h, "write", { path: target, content: "m1-changed" });
				expect(write.error, write.text).toBe(false);
				expect(fs.readFileSync(targetFile, "utf8")).toBe("m1-changed");
				expect(host.countsSnapshot()).toMatchObject({ selectionCommits: 1, reserves: 1, observes: 1, appends: 1 });
				const sidecarPath = localFollowupSidecarPath(sharedPath);
				const beforeCounts = host.countsSnapshot();
				const beforeBodies = bodies.length;
				const localOut = await m1Tool(h, "pm_gate_followup", { ...baseParams, local_ref: localRef });
				expect(localOut.error, localOut.text).toBe(false);
				expect(localOut.details, JSON.stringify(localOut.details)).toMatchObject({
					state: "executed",
					verified_source: "local",
					parent_released: false,
					local_progress: "verified",
					duplicate: false,
					ref: localRef,
					action: choice,
					evidence: `tool_result:${write.toolCallId}`,
				});
				const executionFile = storedRecordPath(doc, KEY, "pm", undefined, localRef, EXECUTION_FILE_SUFFIX);
				const executionBytes = fs.readFileSync(executionFile, "utf8");
				const sidecarBytes = fs.readFileSync(sidecarPath, "utf8");
				const repeat = await m1Tool(h, "pm_gate_followup", { ...baseParams, local_ref: localRef });
				expect(repeat.error, repeat.text).toBe(false);
				expect(repeat.details, JSON.stringify(repeat.details)).toMatchObject({
					state: "executed",
					verified_source: "local",
					parent_released: false,
					duplicate: true,
				});
				expect(fs.existsSync(path.join(doc, "_autopilot", "decisions.jsonl"))).toBe(false);
				expect(fs.readFileSync(sharedPath, "utf8")).toBe(sharedBytes);
				expect(fs.readFileSync(ledgerPath, "utf8")).toBe(ledgerBytes);
				expect(fs.readFileSync(executionFile, "utf8")).toBe(executionBytes);
				expect(fs.readFileSync(sidecarPath, "utf8")).toBe(sidecarBytes);
				expect(host.countsSnapshot().appends).toBe(beforeCounts.appends);
				expect(bodies.length).toBe(beforeBodies);
				// F1 final-unit regression: the single lawful action above is the
				// ONLY action this matter budget may ever spend. A refused second
				// action must be vetoed before any allowance is held, and must not
				// spend, refund, charge unknown or reset the consumed final unit.
				const consumedCounts = host.countsSnapshot();
				expect(consumedCounts.reserves).toBe(1);
				expect(consumedCounts.observes).toBe(1);
				const vetoBodies = bodies.length;
				const secondAction = await m1Tool(h, "write", { path: target, content: "must-not-run-second" });
				expect(secondAction.error).toBe(true);
				expect(fs.readFileSync(targetFile, "utf8")).toBe("m1-changed");
				expect(bodies.length).toBe(vetoBodies);
				const afterVeto = host.countsSnapshot();
				expect(afterVeto.reserves).toBe(consumedCounts.reserves);
				expect(afterVeto.observes).toBe(consumedCounts.observes);
				expect(afterVeto.appends).toBe(consumedCounts.appends);
				expect(afterVeto.unknowns).toBe(consumedCounts.unknowns);
				expect(afterVeto.blocks).toBeGreaterThan(consumedCounts.blocks);
				// At budget 1 the second action is refused by the exhaustion preflight;
				// with a spare unit it reaches pre-body admission and is vetoed there.
				expect(afterVeto.vetoes).toBe(consumedCounts.vetoes + (budgetSteps === 1 ? 0 : 1));
				// Persisted host journal (the same channel the adapter replays): the
				// refused call must have left NO reservation, so the exact real action
				// stays the only reserve/observe pair for this authorization unit.
				const budgetEvents = h.sessionManager.getEntries().flatMap((entry) => {
					if (entry.type !== "custom" || entry.customType !== RUNTIME_BUDGET_ENTRY_TYPE) return [];
					const data = entry.data as {
						unit?: unknown;
						kind?: unknown;
						event?: { kind?: string; request?: { call_id?: string } };
					};
					if (data?.unit !== `${KEY}/${taskKey}` || data.kind !== "event") return [];
					return [data.event ?? {}];
				});
				expect(
					budgetEvents.filter((event) => event.kind === "reserve").map((event) => event.request?.call_id),
				).toEqual([write.toolCallId]);
				expect(
					budgetEvents.filter((event) => event.kind === "observe").map((event) => event.request?.call_id),
				).toEqual([write.toolCallId]);
				expect(secondAction.toolCallId).not.toBe(write.toolCallId);
				// Exact final-unit accounting stays the ONLY committed spend: the
				// terminal archival below can only be captured while nothing is held
				// or in flight, and a phantom veto hold would fail that public path.
				const recheck = await m1Tool(h, "pm_gate_followup", { ...baseParams, local_ref: localRef });
				expect(recheck.details, JSON.stringify(recheck.details)).toMatchObject({
					state: "executed",
					verified_source: "local",
					parent_released: false,
					duplicate: true,
				});
				expect(fs.readFileSync(executionFile, "utf8")).toBe(executionBytes);
				const store = new LocalSelectionStore({ agenticdoc_root: doc, key: KEY });
				const selection = store.readSelection({ source: "pm", ref: localRef });
				const execution = store.readExecution({ source: "pm", ref: localRef });
				expect(selection.status).toBe("ok");
				expect(selection.record?.business_completed).toBe(false);
				expect(execution.status).toBe("ok");
				expect(execution.record?.effect_state).toBe("known");
				expect(execution.record?.verified_by).toBe("target-digest-v1@runtime-execution-1");
				const executorCertificate = host.currentExecutionCertificateFor(localRef, executionScope);
				const currentOffer = handle.currentOfferCertificateFor?.(localRef, offerScope);
				expect(executorBeforeAction).toBeUndefined();
				expect(wrongLocalRefExecutor).toBeUndefined();
				expect(wrongClaimExecutor).toBeUndefined();
				expect(wrongParentOffer).toBeUndefined();
				expect(wrongBasisOffer).toBeUndefined();
				expect(offerBeforeAction?.current_by_matter).toBe(true);
				expect(executorCertificate?.current).toBe(true);
				expect(executorCertificate?.local_ref).toBe(localRef);
				expect(executorCertificate?.tool_call_id).toBe(write.toolCallId);
				expect(executorCertificate?.run_id).toBe(`${taskKey}@${startedAt}`);
				expect(executorCertificate?.task_key).toBe(taskKey);
				expect(executorCertificate?.executor).toBe(JSON.stringify([`${taskKey}@${startedAt}`, write.toolCallId]));
				expect(executorCertificate?.effect_state).toBe("known");
				expect(executorCertificate?.verifier_ref).toBe(execution.record?.verified_by);
				expect(executorCertificate?.target_digest).toBe(execution.record?.target_digest);
				expect(executorCertificate?.binding.owner).toBe(claim);
				expect(executorCertificate?.binding.key).toBe(KEY);
				expect(currentOffer?.current_by_matter).toBe(true);
				expect(currentOffer?.identity_task_key).toBe(taskKey);
				expect(currentOffer?.offer_id).toBe(offerId);
				expect(currentOffer?.local_ref).toBe(localRef);
				expect(currentOffer?.canonical_material_digest).toBe(materialVersion);
				expect(currentOffer?.canonical_catalog_digest).toBe(basisVersion);
				if (overCapIntent !== undefined) {
					// F3: the CURRENT certificate is still computed from the FULL over-cap
					// material — the same canonical digest the native cap refusal retained —
					// and the real DP endpoint was never contacted by the local chain.
					expect(currentOffer?.canonical_material_digest).toBe(overCapIntent.material_version);
					expect(currentOffer?.provenance.material.pm_decision_background).toBe(
						initial.material.pm_decision_background,
					);
					expect(posts).toBe(0);
				}
				expect(currentOffer?.selected_action).toBe(choice);
				expect(currentOffer?.selected_basis_id).toBe(basisId);
				expect(currentOffer?.basis_applies_to).toContain(choice);
				expect(currentOffer?.provenance.origin).toBe("host-submit:FrozenOffer");
				expect(currentOffer?.provenance.context).toBeNull();
				expect(currentOffer?.provenance.current_offer_id).toBe(offerId);
				expect(currentOffer?.provenance.parent_decision_id).toBe(initial.gate_ref);
				expect(currentOffer?.provenance.parent_logical_id).toBe(initial.logical_id);
				expect(currentOffer?.provenance.parent_ref).toBe(initial.matter_ref);
				expect(currentOffer?.provenance.parent_matter_version).toBe(initial.substantive_version);
				expect(currentOffer?.provenance.identity_task_key).toBe(taskKey);
				expect(currentOffer?.provenance.material_fields).toContain("pm_decision_background");
				expect(currentOffer?.provenance.basis_material_refs).toContain("task_goal");
				expect(currentOffer?.provenance.basis_catalog.map((item) => item.id)).toContain(basisId);
				const sidecar = JSON.parse(sidecarBytes) as Record<string, unknown>;
				for (const dpKey of ["status", "answer", "decision_id", "available", "business_decisions"])
					expect(sidecar).not.toHaveProperty(dpKey);
				// P1-03 cross-checks below need the second lawful identity outside the
				// block that creates it; here they are host values, never model input.
				let secondLawfulOfferId: string | undefined;
				let secondLawfulLocalRef: string | undefined;
				let secondLawfulScope: typeof offerScope | undefined;
				if (overCapIntent !== undefined) {
					// F3 supersession POSITIVE: a SECOND genuinely lawful registered
					// parent-joined offer — a real new gate answer for a new substantive
					// version of the same matter — must replace the old offer at the
					// submit, current-certificate and action boundaries. The blocked
					// second request and the removed gate below are NEGATIVES and are
					// never accepted as replacement proof.
					const second = JSON.parse(
						execFileSync(
							PYTHON_EXE,
							[
								"-B",
								"-X",
								"utf8",
								"-c",
								registeredConsumerParentFixture,
								projectRoot,
								KEY,
								"gate",
								"dp-pm-steer",
								"steer",
								claim,
								"2",
								"v2",
							],
							{ cwd: mw, encoding: "utf8", windowsHide: true },
						),
					) as M1ParentFixtureOutput;
					expect(second.gate_ref).not.toBe(initial.gate_ref);
					expect(second.logical_id).not.toBe(initial.logical_id);
					expect(second.substantive_version).toBe("v2");
					expect(
						(
							await answerPreparedGate({
								gateFile: second.gate,
								lockFile: path.join(projectRoot, ".mw", "gates.lock"),
								decision: "steer",
								matterRef: second.matter_ref,
								substantiveVersion: second.substantive_version,
								note: "Prepared PM plan",
								modelBasis: second.parent_basis,
								decisionRef: second.gate_ref,
								answeredBy: claim,
							})
						).ok,
					).toBe(true);
					const secondOut = await m1Tool(h!, "pm_gate_followup", {
						...baseParams,
						gate_id: path.basename(second.gate, ".md"),
					});
					expect(secondOut.error, secondOut.text).toBe(false);
					expect(secondOut.details, JSON.stringify(secondOut.details)).toMatchObject({
						state: "failed",
						reason: "budget-exhausted",
						parent_released: false,
					});
					const secondMeta = m1Details(secondOut.details.submit_offer);
					expect(secondMeta, secondOut.text).toMatchObject({ submittable: true });
					const secondOfferId = String(secondMeta.offer_id);
					const secondLocalRef = String(secondMeta.local_ref);
					secondLawfulOfferId = secondOfferId;
					secondLawfulLocalRef = secondLocalRef;
					expect(secondOfferId).not.toBe(offerId);
					expect(secondLocalRef).not.toBe(localRef);
					expect(posts).toBe(0);
					// CURRENT-CERTIFICATE boundary: the old offer is no longer current
					// for the matter, while the second lawful offer is.
					expect(handle.currentOfferCertificateFor?.(localRef, offerScope)).toBeUndefined();
					expect(handle.hostExpectedFor(localRef)).toBeUndefined();
					expect(handle.hostExpectedFor(secondLocalRef)).toBeDefined();
					const secondScope = {
						...offerScope,
						parent_decision_id: second.gate_ref,
						parent_logical_id: second.logical_id,
						parent_matter_version: second.substantive_version,
					};
					secondLawfulScope = secondScope;
					// SUBMIT boundary: the superseded offer can never commit again ...
					const oldSubmit = await m1Tool(h!, SUBMIT_DECISION_HANDOFF_TOOL, submitParams);
					expect(oldSubmit.details, oldSubmit.text).toMatchObject({
						status: "refused",
						business_completed: false,
						selection_written: false,
						reason: "offer-superseded",
					});
					// P1-04 ACTION boundary: with the second lawful offer PREPARED but NOT
					// yet committed, the replaced plan's action window is already closed. This
					// is a REAL attempted action under the ORIGINAL remaining budget, not a
					// missing-certificate/absent-call proxy, and it must leave no hold.
					const windowCounts = host.countsSnapshot();
					const windowBodies = bodies.length;
					const supersededAction = await m1Tool(h!, "write", { path: target, content: "superseded-must-not-run" });
					expect(supersededAction.error).toBe(true);
					expect(fs.readFileSync(targetFile, "utf8")).toBe("m1-changed");
					expect(bodies.length).toBe(windowBodies);
					expect(host.countsSnapshot()).toMatchObject({
						reserves: windowCounts.reserves,
						observes: windowCounts.observes,
						selectionCommits: windowCounts.selectionCommits,
						unknowns: windowCounts.unknowns,
					});
					// ... while the second lawful offer commits a real planned selection.
					const secondSubmit = await m1Tool(h!, SUBMIT_DECISION_HANDOFF_TOOL, {
						offer_id: secondOfferId,
						choice,
						basis_id: basisId,
					});
					expect(secondSubmit.error, secondSubmit.text).toBe(false);
					expect(secondSubmit.details).toMatchObject({
						status: "planned",
						business_completed: false,
						local_ref: secondLocalRef,
					});
					expect(handle.readCommittedSelection(secondSubmit.toolCallId)?.record.action_state).toBe("planned");
					// The second lawful offer is the CURRENT certified offer of the matter
					// (the earlier certificate probe ran before its own selection existed).
					expect(handle.currentOfferCertificateFor?.(secondLocalRef, secondScope)?.current_by_matter).toBe(true);
					expect(handle.currentOfferCertificateFor?.(secondLocalRef, secondScope)?.local_ref).toBe(secondLocalRef);
					expect(handle.currentOfferCertificateFor?.(secondLocalRef, secondScope)?.offer_id).toBe(secondOfferId);
					// ACTION boundary: no executor certificate exists for either locator
					// (the second offer is a plan only, and the replaced offer can never
					// act), and the target file is untouched by this boundary check.
					expect(host.currentExecutionCertificateFor(localRef, executionScope)).toBeUndefined();
					expect(host.currentExecutionCertificateFor(secondLocalRef, executionScope)).toBeUndefined();
					expect(fs.readFileSync(targetFile, "utf8")).toBe("m1-changed");
					expect(posts).toBe(0);
				}
				if (overCapIntent !== undefined) {
					// F2 negative: an UNCHANGED persisted non-disabled failure is only
					// recoverable while the authoritative retained effect facts still
					// certify zero attempts / zero transport / zero business decisions.
					// A missing fact row and an effect-bearing attempt are both UNKNOWN:
					// the ordinary ingress keeps refusing, spawns no DP child and the
					// matter's offer becomes sticky-uncommittable.
					// F2 positive retention: the REAL native effect facts of the cap
					// refusal are retained next to the frozen reason, so this later
					// ordinary ingress re-reads them instead of inferring from the reason.
					const persistedFailure = JSON.parse(sharedBytes) as Record<string, unknown>;
					expect(persistedFailure).toMatchObject({
						status: "failed",
						failure_reason: "budget-exhausted",
						effect_facts: {
							attempts: 0,
							transport_attempts: 0,
							business_decisions: 0,
							replayed: false,
						},
					});
					const mutateShared = (mutate: (row: Record<string, unknown>) => void): void => {
						const row = JSON.parse(sharedBytes) as Record<string, unknown>;
						mutate(row);
						fs.writeFileSync(sharedPath, `${JSON.stringify(row, null, 2)}\n`);
					};
					const observeNoDpChild = async (
						run: () => Promise<M1ToolResult>,
					): Promise<{ out: M1ToolResult; raw: string }> => {
						let raw = "";
						const originalSpawn = childProcess.spawn;
						const observer = vi
							.spyOn(childProcess, "spawn")
							.mockImplementation((...args: Parameters<typeof childProcess.spawn>) => {
								const child = originalSpawn(...args);
								child.stdout?.on("data", (chunk: Buffer) => {
									raw += chunk.toString();
								});
								child.stderr?.on("data", (chunk: Buffer) => {
									raw += chunk.toString();
								});
								return child;
							});
						syncBuiltinESMExports();
						try {
							return { out: await run(), raw };
						} finally {
							observer.mockRestore();
							syncBuiltinESMExports();
						}
					};
					try {
						// Missing authoritative fact -> sticky refusal, no DP resend.
						mutateShared((row) => {
							delete row.effect_facts;
						});
						const missing = await observeNoDpChild(() => m1Tool(h!, "pm_gate_followup", baseParams));
						expect(missing.raw).toBe("");
						expect(missing.out.details, JSON.stringify(missing.out.details)).toMatchObject({
							state: "failed",
							reason: "budget-exhausted",
							duplicate: true,
							submit_offer: { submittable: false },
						});
						expect(m1Details(missing.out.details.submit_offer).gaps).toContain("effect-unknown-no-replay");
						// Effect-bearing attempt -> sticky refusal, no DP resend.
						mutateShared((row) => {
							row.effect_facts = {
								attempts: 1,
								transport_attempts: 1,
								business_decisions: 0,
								replayed: false,
							};
						});
						const effectBearing = await observeNoDpChild(() => m1Tool(h!, "pm_gate_followup", baseParams));
						expect(effectBearing.raw).toBe("");
						expect(effectBearing.out.details, JSON.stringify(effectBearing.out.details)).toMatchObject({
							state: "failed",
							reason: "budget-exhausted",
							duplicate: true,
							submit_offer: { submittable: false },
						});
						expect(m1Details(effectBearing.out.details.submit_offer).gaps).toContain("effect-unknown-no-replay");
						// Sticky: once the effect facts became unknown this matter's offer
						// can no longer be committed, and nothing is spent or replayed.
						const sticky = await m1Tool(h!, SUBMIT_DECISION_HANDOFF_TOOL, submitParams);
						expect(sticky.details, sticky.text).toMatchObject({
							status: "refused",
							business_completed: false,
							selection_written: false,
							reason: "effect-unknown-no-replay",
						});
						expect(posts).toBe(0);
						expect(fs.readFileSync(targetFile, "utf8")).toBe("m1-changed");
						// P1-03: these OLD-v1 ingresses must never regain currentness. The
						// second lawful offer stays the current one and its action boundary
						// stays the only live one.
						if (secondLawfulLocalRef === undefined || secondLawfulScope === undefined)
							throw new Error("second lawful offer missing");
						expect(
							handle.currentOfferCertificateFor?.(secondLawfulLocalRef, secondLawfulScope)?.current_by_matter,
						).toBe(true);
						expect(handle.currentOfferCertificateFor?.(secondLawfulLocalRef, secondLawfulScope)?.offer_id).toBe(
							secondLawfulOfferId,
						);
						expect(handle.currentOfferCertificateFor?.(localRef, offerScope)).toBeUndefined();
						expect(handle.hostExpectedFor(secondLawfulLocalRef)).toBeDefined();
						expect(handle.hostExpectedFor(localRef)).toBeUndefined();
						expect(host.countsSnapshot()).toMatchObject({
							// Two PLANNED selections (the first local plan and the second lawful
							// superseding plan); still exactly ONE action unit spent.
							selectionCommits: 2,
							reserves: 1,
							observes: 1,
						});
					} finally {
						fs.writeFileSync(sharedPath, sharedBytes);
					}
				}
				const superseded = await m1Tool(h, "pm_gate_followup", {
					...baseParams,
					material: { ...initial.material, pm_decision_background: "superseding material" },
				});
				expect(superseded.details.state).toBe("blocked");
				fs.renameSync(initial.gate, `${initial.gate}.drift`);
				expect(handle.currentOfferCertificateFor?.(localRef, offerScope)).toBeUndefined();
			} finally {
				capServer?.closeAllConnections();
				if (capServer)
					await new Promise<void>((resolve, reject) => capServer!.close((err) => (err ? reject(err) : resolve())));
				h?.cleanup();
				if (previousMwPy === undefined) delete process.env.MW_PY;
				else process.env.MW_PY = previousMwPy;
			}
		},
		90_000,
	);
});

// ── M1AC: recovery / supersession residual (fresh fixture per case) ────────
// The M1Y parametrized case above proves the native cap -> full material ->
// planned -> real body chain, and that an OLD ingress no longer wins
// currentness back. The two cases below are the residual, independently
// reviewed gaps:
//  - a PLANNED offer whose FIRST action is already closed by a newer lawful
//    offer that is prepared but NOT yet committed (the real old-vs-current
//    action window), while the current offer is still legally actionable;
//  - a FRESH (before any supersession/spend) effect-bearing/unknown failure
//    that must never become a submittable plan, plus the ambiguous-bytes
//    (duplicate JSON member) and restored-row negatives.

interface M1Flow {
	h: Harness;
	handle: SubmitDecisionHostHandle;
	host: ProductionRuntimeHost;
	claim: string;
	taskKey: string;
	target: string;
	projectRoot: string;
	doc: string;
	clock: { at: number };
	bodies: string[];
	targetFile: string;
	posts: () => number;
	initial: M1ParentFixtureOutput;
	initialGateId: string;
	followup: (gateId: string, extra?: Record<string, unknown>) => Promise<M1ToolResult>;
	newGate: (
		stage: number,
		version: string,
	) => Promise<{
		gateId: string;
		gateRef: string;
		logicalId: string;
		matterRef: string;
		substantiveVersion: string;
	}>;
	submit: (offerId: string, choice: string, basisId: string) => Promise<M1ToolResult>;
	cleanup: () => Promise<void>;
}

async function createM1Flow(opts: {
	failureMode: "disabled" | "cap-500" | "byte-cap";
	budgetSteps: number;
}): Promise<M1Flow> {
	const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
	const previousMwPy = process.env.MW_PY;
	process.env.MW_PY = path.join(mw, "mw.py");
	const claim = currentClaimId();
	const taskKey = "m1-task";
	const target = "m1.txt";
	const now = Math.floor(Date.now() / 1000) * 1000;
	const startedAt = new Date(now - 60_000).toISOString().replace(".000Z", "Z");
	const deadline = new Date(now + 1_800_000).toISOString().replace(".000Z", "Z");
	const clock = { at: now };
	const projectRoot = tmp;
	const doc = root;
	const bodies: string[] = [];
	let posts = 0;
	let server: Server | undefined;
	expect((await new IndexStore(doc).claim(KEY, claim, () => false)).ok).toBe(true);
	fs.mkdirSync(path.join(doc, KEY, "tasks"), { recursive: true });
	fs.mkdirSync(path.join(doc, "_autopilot"), { recursive: true });
	fs.writeFileSync(
		path.join(doc, "_autopilot", "config.json"),
		JSON.stringify({ enabled: true, auto_gate_mode: "live" }),
		"utf8",
	);
	const createParent = (stage: number, version: string): M1ParentFixtureOutput =>
		JSON.parse(
			execFileSync(
				PYTHON_EXE,
				[
					"-B",
					"-X",
					"utf8",
					"-c",
					registeredConsumerParentFixture,
					projectRoot,
					KEY,
					"gate",
					"dp-pm-steer",
					"steer",
					claim,
					String(stage),
					version,
				],
				{ cwd: mw, encoding: "utf8", windowsHide: true },
			),
		) as M1ParentFixtureOutput;
	const answerGate = async (parent: M1ParentFixtureOutput): Promise<void> => {
		expect(
			(
				await answerPreparedGate({
					gateFile: parent.gate,
					lockFile: path.join(projectRoot, ".mw", "gates.lock"),
					decision: "steer",
					matterRef: parent.matter_ref,
					substantiveVersion: parent.substantive_version,
					note: "Prepared PM plan",
					modelBasis: parent.parent_basis,
					decisionRef: parent.gate_ref,
					answeredBy: claim,
				})
			).ok,
		).toBe(true);
	};
	const initial = createParent(1, "v1");
	await answerGate(initial);
	const cardText = m1Card(claim, taskKey, deadline, initial.material, opts.budgetSteps);
	const cardPath = path.join(doc, KEY, "tasks", `${taskKey}.md`);
	fs.writeFileSync(cardPath, cardText, "utf8");
	const cardSha = sha256EolNormalizedBytes(Buffer.from(cardText));
	const envelope = path.join(projectRoot, `${taskKey}.md`);
	fs.writeFileSync(
		envelope,
		`card_path: tasks/${taskKey}.md\ncard_sha256: ${cardSha}\nwrite_face: ${target}\n`,
		"utf8",
	);
	const targetFile = path.join(projectRoot, target);
	fs.writeFileSync(targetFile, `original-${taskKey}`, "utf8");
	if (opts.failureMode === "cap-500") {
		server = createServer((_request, response) => {
			posts += 1;
			response.writeHead(500).end("synthetic upstream failure");
		});
		await new Promise<void>((resolve) => {
			server?.listen(0, "127.0.0.1", resolve);
		});
		const address = server.address();
		if (!address || typeof address === "string") throw new Error("loopback address unavailable");
		fs.writeFileSync(
			path.join(projectRoot, ".mw", "decide-points.json"),
			JSON.stringify({ points: { "dp-pm-steer": { enabled: true } } }),
		);
		fs.writeFileSync(
			path.join(projectRoot, ".mw", "decide.json"),
			JSON.stringify({
				enabled: true,
				base_url: `http://127.0.0.1:${address.port}`,
				api_key: "synthetic-m1ac",
				max_retries: 0,
				timeout_s: 2,
			}),
		);
	} else if (opts.failureMode === "byte-cap") {
		// A REAL native zero-transport refusal: the decision child's byte gate fires
		// before any transport attempt, so the frozen reply keeps attempts=0 /
		// transport_attempts=0 with a NON-disabled reason. It uses the real config
		// file; the official consumer fixtures build their own DecisionConfig, so
		// this cap never reaches them.
		fs.writeFileSync(
			path.join(projectRoot, ".mw", "decide-points.json"),
			JSON.stringify({ points: { "dp-pm-steer": { enabled: true } } }),
		);
		fs.writeFileSync(
			path.join(projectRoot, ".mw", "decide.json"),
			JSON.stringify({ enabled: true, max_state_bytes: 128 }),
		);
	} else {
		fs.writeFileSync(
			path.join(projectRoot, ".mw", "decide-points.json"),
			JSON.stringify({ points: { "dp-pm-steer": { enabled: false } } }),
		);
		fs.writeFileSync(path.join(projectRoot, ".mw", "decide.json"), JSON.stringify({ enabled: true }));
	}
	const host = new ProductionRuntimeHost(projectRoot, () => clock.at);
	let handle: SubmitDecisionHostHandle | undefined;
	const h = await createHarness({
		extensionFactories: [
			(pi) => {
				registerProductionRuntimeEvents(pi, host);
				handle = registerSubmitDecisionHandoffTool(pi, {
					projectDir: projectRoot,
					hostRuntime: host,
					runtimeHost: host.adapterHooks(),
					clock: () => clock.at,
				});
				for (const name of ["read", "ls", "find", "grep", "write"]) {
					pi.registerTool({
						name,
						label: name,
						description: "isolated M1AC fixture tool",
						parameters: Type.Object({ path: Type.String(), content: Type.Optional(Type.String()) }),
						execute: async (_id, params) => {
							bodies.push(name);
							if (name === "write")
								fs.writeFileSync(path.join(projectRoot, params.path), params.content ?? "changed");
							return {
								content: [
									{
										type: "text",
										text:
											name === "read"
												? fs.readFileSync(path.join(projectRoot, params.path), "utf8")
												: "fixture-result",
									},
								],
								details: {},
							};
						},
					});
				}
				registerPmGateFollowup(pi, projectRoot, new WorkerStore(doc), { key: KEY }, undefined, {
					submitHandle: handle,
					host,
				});
			},
		],
	});
	await h.session.bindExtensions({});
	if (!handle) throw new Error("M1AC submit handle missing");
	const registered = host.registerPmDispatch({
		key: KEY,
		taskKey,
		claimId: claim,
		taskMdPath: envelope,
		dispatchedAt: startedAt,
	});
	expect(registered.ok, JSON.stringify(registered)).toBe(true);
	const baseParams = (gateId: string): Record<string, unknown> => ({
		gate_id: gateId,
		source_card: taskKey,
		restricted_action: "direct-exec",
		material: initial.material,
		preparation: initial.preparation,
	});
	return {
		h,
		handle,
		host,
		claim,
		taskKey,
		target,
		projectRoot,
		doc,
		clock,
		bodies,
		targetFile,
		posts: () => posts,
		initial,
		initialGateId: path.basename(initial.gate, ".md"),
		followup: (gateId, extra) => m1Tool(h, "pm_gate_followup", { ...baseParams(gateId), ...extra }),
		newGate: async (stage, version) => {
			const parent = createParent(stage, version);
			await answerGate(parent);
			return {
				gateId: path.basename(parent.gate, ".md"),
				gateRef: parent.gate_ref,
				logicalId: parent.logical_id,
				matterRef: parent.matter_ref,
				substantiveVersion: parent.substantive_version,
			};
		},
		submit: (offerId, choice, basisId) =>
			m1Tool(h, SUBMIT_DECISION_HANDOFF_TOOL, { offer_id: offerId, choice, basis_id: basisId }),
		cleanup: async () => {
			if (server) {
				server.closeAllConnections();
				await new Promise<void>((resolve, reject) => {
					server?.close((err) => (err ? reject(err) : resolve()));
				});
			}
			h.cleanup();
			if (previousMwPy === undefined) delete process.env.MW_PY;
			else process.env.MW_PY = previousMwPy;
		},
	};
}

describe("T07 M1AC recovery/supersession residual", () => {
	it("a PLANNED offer's first real action is closed by a newer lawful offer, and the current offer still acts", async () => {
		const flow = await createM1Flow({ failureMode: "disabled", budgetSteps: 3 });
		try {
			const choice = "direct-exec";
			const basisId = String(flow.initial.preparation.basis_catalog[0].id);
			const first = await flow.followup(flow.initialGateId);
			expect(first.error, first.text).toBe(false);
			const firstMeta = m1Details(first.details.submit_offer);
			expect(firstMeta, first.text).toMatchObject({ submittable: true });
			const firstOfferId = String(firstMeta.offer_id);
			const firstLocalRef = String(firstMeta.local_ref);
			const firstSubmit = await flow.submit(firstOfferId, choice, basisId);
			expect(firstSubmit.error, firstSubmit.text).toBe(false);
			expect(firstSubmit.details).toMatchObject({ status: "planned", local_ref: firstLocalRef });
			// A plan only: nothing spent, target untouched.
			expect(flow.host.countsSnapshot()).toMatchObject({ selectionCommits: 1, reserves: 0, observes: 0 });
			expect(fs.readFileSync(flow.targetFile, "utf8")).toBe(`original-${flow.taskKey}`);

			// A newer lawful parent answers a new substantive version and reaches a
			// joined offer that is PREPARED but deliberately NOT committed yet.
			const second = await flow.newGate(2, "v2");
			const newer = await flow.followup(second.gateId);
			expect(newer.error, newer.text).toBe(false);
			const newerMeta = m1Details(newer.details.submit_offer);
			expect(newerMeta, newer.text).toMatchObject({ submittable: true });
			const newerOfferId = String(newerMeta.offer_id);
			const newerLocalRef = String(newerMeta.local_ref);
			expect(newerOfferId).not.toBe(firstOfferId);
			expect(newerLocalRef).not.toBe(firstLocalRef);
			// The replaced plan keeps NO action projection while the newer lawful
			// offer does — real host projections, not model input.
			expect(flow.handle.hostExpectedFor(firstLocalRef)).toBeUndefined();
			expect(flow.handle.hostExpectedFor(newerLocalRef)).toBeDefined();
			expect(
				flow.handle.currentOfferCertificateFor?.(firstLocalRef, {
					key: KEY,
					source: "pm",
					claim_id: flow.claim,
					parent_ref: second.matterRef,
					parent_decision_id: second.gateRef,
					parent_logical_id: second.logicalId,
					parent_matter_version: second.substantiveVersion,
					target_dp: "dp-pm-steer",
					material_version: createHash("sha256").update(canonicalStateJson(flow.initial.material)).digest("hex"),
					basis_version: createHash("sha256").update(canonicalStateJson(flow.initial.preparation)).digest("hex"),
					restricted_action: choice,
				}),
			).toBeUndefined();

			// THE WINDOW: the OLD plan's FIRST real action attempt, after the newer
			// lawful offer exists but before it commits, under the ORIGINAL remaining
			// budget (3 units, none spent). It must be refused with no hold.
			const beforeWindow = flow.host.countsSnapshot();
			const beforeBodies = flow.bodies.length;
			const oldAction = await m1Tool(flow.h, "write", { path: flow.target, content: "old-plan-must-not-run" });
			expect(oldAction.error).toBe(true);
			// The veto comes from the SHARED currentness boundary, not from budget
			// exhaustion (3 units, none spent) and not from a missing certificate.
			expect(oldAction.text).toContain("offer-source-not-current");
			expect(fs.readFileSync(flow.targetFile, "utf8")).toBe(`original-${flow.taskKey}`);
			expect(flow.bodies.length).toBe(beforeBodies);
			expect(flow.host.countsSnapshot()).toMatchObject({
				selectionCommits: beforeWindow.selectionCommits,
				reserves: beforeWindow.reserves,
				observes: beforeWindow.observes,
				unknowns: beforeWindow.unknowns,
				appends: beforeWindow.appends,
			});
			expect(
				flow.host.currentExecutionCertificateFor(firstLocalRef, {
					key: KEY,
					source: "pm",
					claim_id: flow.claim,
				}),
			).toBeUndefined();

			// A stale re-ingress of the OLD parent can never win currentness back.
			const stale = await flow.followup(flow.initialGateId);
			expect(stale.details).toMatchObject({ state: "failed", duplicate: true });
			expect(flow.handle.hostExpectedFor(firstLocalRef)).toBeUndefined();
			expect(flow.handle.hostExpectedFor(newerLocalRef)).toBeDefined();

			// Not a blanket deny: the CURRENT lawful plan commits and ITS real body
			// executes, with a real execution certificate bound to that action.
			const newerSubmit = await flow.submit(newerOfferId, choice, basisId);
			expect(newerSubmit.error, newerSubmit.text).toBe(false);
			expect(newerSubmit.details).toMatchObject({ status: "planned", local_ref: newerLocalRef });
			const write = await m1Tool(flow.h, "write", { path: flow.target, content: "v2-lawful-body" });
			expect(write.error, write.text).toBe(false);
			expect(fs.readFileSync(flow.targetFile, "utf8")).toBe("v2-lawful-body");
			expect(flow.host.countsSnapshot()).toMatchObject({ selectionCommits: 2, reserves: 1, observes: 1 });
			const projection = flow.handle.hostExpectedFor(newerLocalRef);
			const committed = flow.handle.readCommittedSelection(newerSubmit.toolCallId);
			// FULL material digest, never a truncated projection.
			expect(committed?.record.material_digest).toBe(projection?.material_digest);
			const certificate = flow.host.currentExecutionCertificateFor(newerLocalRef, {
				key: KEY,
				source: "pm",
				claim_id: flow.claim,
			});
			expect(certificate?.tool_call_id).toBe(write.toolCallId);
			expect(certificate?.effect_state).toBe("known");
			// The superseded plan still cannot commit, and its reason is currentness.
			const oldSubmit = await flow.submit(firstOfferId, choice, basisId);
			expect(oldSubmit.details, oldSubmit.text).toMatchObject({
				status: "refused",
				selection_written: false,
				business_completed: false,
				reason: "offer-superseded",
			});
		} finally {
			await flow.cleanup();
		}
	}, 90_000);

	it("a FRESH effect-bearing/unknown failure never becomes a submittable plan before supersession or spend", async () => {
		const flow = await createM1Flow({ failureMode: "cap-500", budgetSteps: 3 });
		try {
			const first = await flow.followup(flow.initialGateId);
			expect(first.error, first.text).toBe(false);
			expect(first.details, first.text).toMatchObject({ state: "failed", parent_released: false });
			// A REAL transport attempt happened (never an empty-stdout proxy).
			expect(flow.posts()).toBeGreaterThanOrEqual(1);
			const firstOffer = m1Details(first.details.submit_offer);
			expect(firstOffer.submittable).toBe(false);
			expect(firstOffer.gaps).toContain("effect-unknown-no-replay");
			expect(flow.host.countsSnapshot()).toMatchObject({ selectionCommits: 0, reserves: 0, observes: 0 });
			expect(fs.readFileSync(flow.targetFile, "utf8")).toBe(`original-${flow.taskKey}`);
			const followupDir = path.join(flow.doc, KEY, "evidence", "decision-followups");
			const sharedName = fs
				.readdirSync(followupDir)
				.find((name) => name.endsWith(".json") && !name.endsWith(".local.json"));
			const sharedPath = path.join(followupDir, sharedName ?? "");
			const sharedBytes = fs.readFileSync(sharedPath, "utf8");
			const persisted = JSON.parse(sharedBytes) as Record<string, unknown>;
			expect(persisted.status).toBe("failed");
			const facts = persisted.effect_facts as Record<string, unknown> | undefined;
			// The REAL 500 reply retains its frozen effect facts, and they are
			// effect-bearing (a transport attempt happened), so the retained row is a
			// CLUE that this failure must stay unknown — never a plan.
			expect(facts, sharedBytes).toBeDefined();
			expect(Number(facts?.attempts), sharedBytes).toBeGreaterThanOrEqual(1);
			expect(Number(facts?.transport_attempts), sharedBytes).toBeGreaterThanOrEqual(1);
			const observeNoDpChild = async (
				run: () => Promise<M1ToolResult>,
			): Promise<{ out: M1ToolResult; raw: string }> => {
				let raw = "";
				const originalSpawn = childProcess.spawn;
				const observer = vi
					.spyOn(childProcess, "spawn")
					.mockImplementation((...args: Parameters<typeof childProcess.spawn>) => {
						const child = originalSpawn(...args);
						child.stdout?.on("data", (chunk: Buffer) => {
							raw += chunk.toString();
						});
						child.stderr?.on("data", (chunk: Buffer) => {
							raw += chunk.toString();
						});
						return child;
					});
				syncBuiltinESMExports();
				try {
					return { out: await run(), raw };
				} finally {
					observer.mockRestore();
					syncBuiltinESMExports();
				}
			};
			// Unchanged failure: no resend, still no plan, still no spend.
			const replayed = await observeNoDpChild(() => flow.followup(flow.initialGateId));
			expect(replayed.raw).toBe("");
			expect(replayed.out.details).toMatchObject({ state: "failed", duplicate: true });
			expect(m1Details(replayed.out.details.submit_offer).submittable).toBe(false);
			// Ambiguous RAW bytes (duplicated member) are never authority: JSON.parse
			// would silently keep the LAST member, so the intent is refused whole.
			fs.writeFileSync(
				sharedPath,
				sharedBytes.replace('"status": "failed"', '"status": "failed",\n  "status": "answered"'),
			);
			const duplicate = await observeNoDpChild(() => flow.followup(flow.initialGateId));
			expect(duplicate.raw).toBe("");
			expect(duplicate.out.details, JSON.stringify(duplicate.out.details)).toMatchObject({
				state: "blocked",
				reason: "intent-invalid",
			});
			// Restored row WITHOUT the retained facts: still unknown, still refused.
			fs.writeFileSync(sharedPath, sharedBytes);
			const missingRow = JSON.parse(sharedBytes) as Record<string, unknown>;
			delete missingRow.effect_facts;
			fs.writeFileSync(sharedPath, `${JSON.stringify(missingRow, null, 2)}\n`);
			const missing = await observeNoDpChild(() => flow.followup(flow.initialGateId));
			expect(missing.raw).toBe("");
			expect(missing.out.details).toMatchObject({ state: "failed", duplicate: true });
			expect(m1Details(missing.out.details.submit_offer).submittable).toBe(false);
			expect(m1Details(missing.out.details.submit_offer).gaps).toContain("effect-unknown-no-replay");
			fs.writeFileSync(sharedPath, sharedBytes);
			// No spend, no fabricated write, no selection, no unauthorized cost.
			expect(flow.posts()).toBeGreaterThanOrEqual(1);
			expect(flow.host.countsSnapshot()).toMatchObject({
				selectionCommits: 0,
				reserves: 0,
				observes: 0,
				unknowns: 0,
			});
			expect(fs.readFileSync(flow.targetFile, "utf8")).toBe(`original-${flow.taskKey}`);
			expect(flow.bodies).not.toContain("write");
			// VC026 (narrow layer only): an independent legal read still succeeds
			// after the refusals, so no global stop was created. This is NOT a
			// whole-VC-026 independent delivery claim.
			const independentRead = await m1Tool(flow.h, "read", { path: flow.target });
			expect(independentRead.error, independentRead.text).toBe(false);
			expect(independentRead.text).toBe(`original-${flow.taskKey}`);
		} finally {
			await flow.cleanup();
		}
	}, 90_000);
});

// ── M1AF2: host-minted failed-row witness (F2/P1-01 residual) ──────────────
// FIXTURE BOUNDARY (read before interpreting results):
//  * The failed rows here are produced ONLY by the registered PM ingress, the
//    real default decision child and the real lifecycle writer. No passing
//    fact set, witness or committed child is hand-written.
//  * `byte-cap` is a REAL native zero-transport refusal (the byte gate fires in
//    the decision child before any transport), so its reply carries genuine
//    attempts=0 / transport_attempts=0 with the NON-disabled reason
//    `budget-exhausted`. `cap-500` is a REAL loopback 500 (a real POST).
//  * The ONLY negative fixtures are byte rewrites of a genuine row (counters,
//    witness) and a byte copy of a genuine row onto a path this host never
//    wrote — the M1AE-1 attack shape and the fresh-host shape.
//  * The contradictory committed child is written by the REAL production
//    lifecycle store through the official request_prepared/record_request
//    writer (the M1AE-2 fixture technique), never by a fake append.

interface M1AF2Observation {
	out: M1ToolResult;
	raw: string;
	spawnCount: number;
	spawns: string[];
}

/** Observe the REAL child-process spawns of one registered ingress. */
async function m1af2Observe(run: () => Promise<M1ToolResult>): Promise<M1AF2Observation> {
	let raw = "";
	const spawns: string[] = [];
	const original = childProcess.spawn;
	const spy = vi.spyOn(childProcess, "spawn").mockImplementation((...args: Parameters<typeof childProcess.spawn>) => {
		const argv = Array.isArray(args[1]) ? args[1].map(String).join(" ") : "";
		spawns.push(argv);
		const child = original(...args);
		child.stdout?.on("data", (chunk: Buffer) => {
			raw += chunk.toString();
		});
		child.stderr?.on("data", (chunk: Buffer) => {
			raw += chunk.toString();
		});
		return child;
	});
	syncBuiltinESMExports();
	try {
		return { out: await run(), raw, spawnCount: spawns.length, spawns };
	} finally {
		spy.mockRestore();
		syncBuiltinESMExports();
	}
}

function m1af2SharedPath(flow: M1Flow): string {
	const dir = path.join(flow.doc, KEY, "evidence", "decision-followups");
	const name = fs.readdirSync(dir).find((entry) => entry.endsWith(".json") && !entry.endsWith(".local.json"));
	if (name === undefined) throw new Error("M1AF2 shared DP intent missing");
	return path.join(dir, name);
}

function m1af2Binding(row: Record<string, unknown>): ExpectedDecisionFollowup {
	const targetDp = row.target_dp;
	if (targetDp !== "dp-pm-steer" && targetDp !== "dp-auto") throw new Error("unexpected target dp");
	const taskKey = row.task_key;
	return {
		parent_ref: String(row.parent_ref),
		parent_logical_id: String(row.parent_logical_id),
		parent_decision_id: String(row.parent_decision_id),
		parent_matter_version: String(row.parent_matter_version),
		target_dp: targetDp,
		material_version: String(row.material_version),
		basis_version: String(row.basis_version),
		owner_key: String(row.owner_key),
		task_key: typeof taskKey === "string" ? taskKey : null,
		restricted_action: String(row.restricted_action),
		restricted_executor: String(row.restricted_executor),
	};
}

function m1af2PreparedBy(row: Record<string, unknown>): { role: "pm"; key: string; window_id: string } {
	const pm = m1Details(row.prepared_by);
	if (pm.role !== "pm") throw new Error("unexpected preparer role");
	return { role: "pm", key: String(pm.key), window_id: String(pm.window_id) };
}

function m1af2Sha(file: string): string {
	return createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

/** Re-read a genuine failed row through a path this host never wrote (a
 *  fresh-host lifetime) WITH the real production lifecycle scope supplied: the
 *  ledger corroboration is available, so an `unknown` here can only come from
 *  the missing host observation. */
async function m1af2ResumeCopy(
	flow: M1Flow,
	rowBytes: string,
	copyName: string,
	mutate?: (row: Record<string, unknown>) => void,
): Promise<{ out: Awaited<ReturnType<typeof resumeDecisionFollowup>>; requests: number; path: string }> {
	const copyPath = path.join(flow.projectRoot, copyName);
	const row = JSON.parse(rowBytes) as Record<string, unknown>;
	if (mutate !== undefined) mutate(row);
	fs.writeFileSync(copyPath, mutate === undefined ? rowBytes : `${JSON.stringify(row, null, 2)}\n`, "utf8");
	let requests = 0;
	const out = await resumeDecisionFollowup({
		intent_path: copyPath,
		expected: m1af2Binding(row),
		bound_pm: m1af2PreparedBy(row),
		observe_task: () => "not-queued",
		lifecycle: { projectDir: flow.projectRoot },
		request: () => {
			requests += 1;
			return Promise.resolve({ available: false as const, reason: "budget-exhausted" });
		},
	});
	return { out, requests, path: copyPath };
}

const m1af2CommittedChildFixture = `
import json, pathlib, sys
import pytest
from autopilot import gates
import decision_lifecycle as life
import decision_wire as wire
import test_dp_consolidation_materials as f
root, owner, window, parent_ref = sys.argv[1:5]
root = pathlib.Path(root)
dp = "dp-pm-steer"
key = life.DecisionMeta.create(owner, initiator_role="pm")
store = life.LifecycleStore.production(root, redact=wire.SubstringRedactor([f.API_KEY]))
actor = ("system", "pm:" + window)
ref = dp + ":" + key.logical_id
assert life.record_start(store, key, decision_id=ref, actor=actor).recorded
material = f._material(dp)
prep = f._preparation(dp, material)
with pytest.MonkeyPatch.context() as patch:
    answers = {f.BUSINESS_QIDS[dp]: f._choice_answer("direct-exec"), "basis_id": f._choice_answer(prep["basis_catalog"][0]["id"])}
    fake = f.FakeHttp(lambda *args: f._body(dp, answers))
    patch.setattr(f.backends, "_http_post", fake)
    result = f._make_client(root, patch).request_prepared(dp, material, prep, actor_role="pm")
    assert len(fake.calls) == 1 and result["business_decisions"] == 1, result.get("issues")
    recorded = life.record_request(store, key, decision_id=ref, result=result, material=material,
        preparation=prep, parent_ref=parent_ref, actor=actor)
    assert recorded.recorded, recorded
print(json.dumps({"child_ref": ref, "parent_ref": parent_ref, "dp": dp,
    "business_decisions": result["business_decisions"]}))
`;

/** Official-writer committed child business decision for THIS parent + target. */
function m1af2CommitChild(flow: M1Flow): Record<string, unknown> {
	const mw = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
	return JSON.parse(
		execFileSync(
			PYTHON_EXE,
			["-B", "-X", "utf8", "-c", m1af2CommittedChildFixture, flow.projectRoot, KEY, WINDOW, flow.initial.gate_ref],
			{ cwd: mw, encoding: "utf8", windowsHide: true },
		),
	) as Record<string, unknown>;
}

function m1af2CommittedChildren(flow: M1Flow): Record<string, unknown>[] {
	const file = path.join(flow.doc, "_autopilot", "decision-lifecycle.jsonl");
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.trim() !== "")
		.map((line) => JSON.parse(line) as Record<string, unknown>)
		.filter(
			(entry) =>
				entry.kind === "request" &&
				entry.parent_ref === flow.initial.gate_ref &&
				entry.dp === "dp-pm-steer" &&
				Number(entry.business_decisions ?? 0) > 0,
		);
}

describe("T07 M1AF2 host-minted failed-row witness (F2/P1-01 residual)", () => {
	it("a real native zero-transport failure at budget 3 stays recoverable on the SAME host, and a copied row on an unobserved path does not", async () => {
		const flow = await createM1Flow({ failureMode: "byte-cap", budgetSteps: 3 });
		const choice = "direct-exec";
		const basisId = String(flow.initial.preparation.basis_catalog[0].id);
		try {
			const targetBefore = m1af2Sha(flow.targetFile);
			// (a) FIRST ingress: a genuine native zero-transport refusal.
			const first = await m1af2Observe(() => flow.followup(flow.initialGateId));
			expect(first.out.error, first.out.text).toBe(false);
			expect(first.out.details, JSON.stringify(first.out.details)).toMatchObject({
				state: "failed",
				reason: "budget-exhausted",
				duplicate: false,
				parent_released: false,
				failure_effect: "known-no-effect",
			});
			expect(first.spawnCount, first.spawns.join(" | ")).toBe(1);
			expect(String(first.raw)).toContain('"transport_attempts": 0');
			expect(flow.posts()).toBe(0);
			const sharedPath = m1af2SharedPath(flow);
			const rowBytes = fs.readFileSync(sharedPath, "utf8");
			const row = JSON.parse(rowBytes) as Record<string, unknown>;
			expect(row, rowBytes).toMatchObject({
				status: "failed",
				failure_reason: "budget-exhausted",
				effect_facts: { attempts: 0, transport_attempts: 0, business_decisions: 0, replayed: false },
			});
			// The host minted its own witness together with the row.
			expect(typeof row.effect_witness).toBe("string");
			expect(String(row.effect_witness)).toMatch(/^[0-9a-f]{64}$/);
			const firstOffer = m1Details(first.out.details.submit_offer);
			expect(firstOffer, first.out.text).toMatchObject({ submittable: true });
			const offerId = String(firstOffer.offer_id);
			const localRef = String(firstOffer.local_ref);

			// (b) REPEATED ingress: still positive, no resend, no body, same offer.
			const repeat = await m1af2Observe(() => flow.followup(flow.initialGateId));
			expect(repeat.raw).toBe("");
			expect(repeat.spawnCount).toBe(0);
			expect(repeat.out.details, JSON.stringify(repeat.out.details)).toMatchObject({
				state: "failed",
				duplicate: true,
				failure_effect: "known-no-effect",
			});
			expect(m1Details(repeat.out.details.submit_offer)).toMatchObject({
				submittable: true,
				offer_id: offerId,
				local_ref: localRef,
			});
			expect(flow.posts()).toBe(0);
			expect(fs.readFileSync(sharedPath, "utf8")).toBe(rowBytes);

			// (c) The SAME genuine bytes on a path this host never wrote are NOT
			// recovery authority: the real lifecycle corroboration is available
			// here, so only the unobserved-path boundary can be the refusal.
			const copied = await m1af2ResumeCopy(flow, rowBytes, "restored-host-copy.json");
			expect(copied.out, JSON.stringify(copied.out)).toMatchObject({
				state: "failed",
				duplicate: true,
				failure_effect: "unknown",
				request_started: false,
				parent_released: false,
			});
			expect(copied.requests).toBe(0);

			// (d) CONTROL: the SAME path with the SAME lifecycle is still positive.
			const samePath = await resumeDecisionFollowup({
				intent_path: sharedPath,
				expected: m1af2Binding(row),
				bound_pm: m1af2PreparedBy(row),
				observe_task: () => "not-queued",
				lifecycle: { projectDir: flow.projectRoot },
				request: () => {
					throw new Error("M1AF2 must not resend");
				},
			});
			expect(samePath, JSON.stringify(samePath)).toMatchObject({
				state: "failed",
				duplicate: true,
				failure_effect: "known-no-effect",
				parent_released: false,
			});

			// (e) The SAME host keeps genuine recovery: a real planned selection
			// and ONE real body under the ORIGINAL remaining budget (3).
			const submit = await flow.submit(offerId, choice, basisId);
			expect(submit.error, submit.text).toBe(false);
			expect(submit.details).toMatchObject({ status: "planned", business_completed: false, local_ref: localRef });
			const write = await m1Tool(flow.h, "write", { path: flow.target, content: "m1af2-body" });
			expect(write.error, write.text).toBe(false);
			expect(fs.readFileSync(flow.targetFile, "utf8")).toBe("m1af2-body");
			expect(m1af2Sha(flow.targetFile)).not.toBe(targetBefore);
			expect(flow.host.countsSnapshot()).toMatchObject({ selectionCommits: 1, reserves: 1, observes: 1 });
			expect(flow.posts()).toBe(0);
		} finally {
			await flow.cleanup();
		}
	}, 120_000);

	it("rewritten counters and a rewritten/foreign witness on a real transport failure stay unknown with zero resend and no body", async () => {
		const flow = await createM1Flow({ failureMode: "cap-500", budgetSteps: 3 });
		const choice = "direct-exec";
		const basisId = String(flow.initial.preparation.basis_catalog[0].id);
		try {
			const targetBefore = m1af2Sha(flow.targetFile);
			const first = await m1af2Observe(() => flow.followup(flow.initialGateId));
			expect(first.out.error, first.out.text).toBe(false);
			expect(first.out.details, JSON.stringify(first.out.details)).toMatchObject({
				state: "failed",
				duplicate: false,
				failure_effect: "unknown",
				parent_released: false,
			});
			expect(first.spawnCount).toBe(1);
			expect(flow.posts()).toBeGreaterThanOrEqual(1);
			const sharedPath = m1af2SharedPath(flow);
			const rowBytes = fs.readFileSync(sharedPath, "utf8");
			const row = JSON.parse(rowBytes) as Record<string, unknown>;
			const facts = row.effect_facts as Record<string, unknown> | undefined;
			expect(Number(facts?.attempts), rowBytes).toBeGreaterThanOrEqual(1);
			expect(Number(facts?.transport_attempts), rowBytes).toBeGreaterThanOrEqual(1);
			expect(String(row.effect_witness)).toMatch(/^[0-9a-f]{64}$/);
			const postsAfterFirst = flow.posts();
			const offer = m1Details(first.out.details.submit_offer);
			expect(offer.submittable).toBe(false);
			expect(offer.gaps).toContain("effect-unknown-no-replay");
			const mutateShared = (mutate: (target: Record<string, unknown>) => void): void => {
				const next = JSON.parse(rowBytes) as Record<string, unknown>;
				mutate(next);
				fs.writeFileSync(sharedPath, `${JSON.stringify(next, null, 2)}\n`, "utf8");
			};
			try {
				// (1) M1AE-1 shape: ONLY the counters are rewritten to the positive
				// shape. The witness stays, so the digest no longer reproduces it.
				mutateShared((next) => {
					next.effect_facts = { attempts: 0, transport_attempts: 0, business_decisions: 0, replayed: false };
				});
				const rewritten = await m1af2Observe(() => flow.followup(flow.initialGateId));
				expect(rewritten.raw).toBe("");
				expect(rewritten.spawnCount).toBe(0);
				expect(rewritten.out.details, JSON.stringify(rewritten.out.details)).toMatchObject({
					state: "failed",
					duplicate: true,
					failure_effect: "unknown",
					parent_released: false,
				});
				expect(m1Details(rewritten.out.details.submit_offer)).toMatchObject({ submittable: false });
				expect(m1Details(rewritten.out.details.submit_offer).gaps).toContain("effect-unknown-no-replay");
				expect(flow.posts()).toBe(postsAfterFirst);

				// (2) A FOREIGN witness over the positive counters: still unknown.
				mutateShared((next) => {
					next.effect_facts = { attempts: 0, transport_attempts: 0, business_decisions: 0, replayed: false };
					next.effect_witness = "f".repeat(64);
				});
				const foreign = await m1af2Observe(() => flow.followup(flow.initialGateId));
				expect(foreign.raw).toBe("");
				expect(foreign.spawnCount).toBe(0);
				expect(foreign.out.details, JSON.stringify(foreign.out.details)).toMatchObject({
					state: "failed",
					duplicate: true,
					failure_effect: "unknown",
				});
				expect(m1Details(foreign.out.details.submit_offer).gaps).toContain("effect-unknown-no-replay");

				// (3) The sticky unknown can never be committed or executed.
				const submit = await flow.submit(String(offer.offer_id), choice, basisId);
				expect(submit.details, submit.text).toMatchObject({
					status: "refused",
					business_completed: false,
					selection_written: false,
					reason: "effect-unknown-no-replay",
				});
				expect(flow.posts()).toBe(postsAfterFirst);
				expect(fs.readFileSync(flow.targetFile, "utf8")).toBe(`original-${flow.taskKey}`);
				expect(m1af2Sha(flow.targetFile)).toBe(targetBefore);
				expect(flow.bodies).not.toContain("write");
				expect(flow.host.countsSnapshot()).toMatchObject({ selectionCommits: 0, reserves: 0, observes: 0 });
			} finally {
				fs.writeFileSync(sharedPath, rowBytes);
			}
			// (4) Restoring the genuine bytes does not rewind the sticky unknown:
			// the offer stays uncommittable (no replay), never silently reopened.
			const replay = await flow.submit(String(offer.offer_id), choice, basisId);
			expect(replay.details).toMatchObject({ status: "refused", reason: "effect-unknown-no-replay" });
		} finally {
			await flow.cleanup();
		}
	}, 120_000);

	it("a real committed child for this parent still refuses the positive verdict on the SAME host", async () => {
		const flow = await createM1Flow({ failureMode: "byte-cap", budgetSteps: 3 });
		const choice = "direct-exec";
		const basisId = String(flow.initial.preparation.basis_catalog[0].id);
		try {
			const targetBefore = m1af2Sha(flow.targetFile);
			const first = await m1af2Observe(() => flow.followup(flow.initialGateId));
			expect(first.out.error, first.out.text).toBe(false);
			expect(first.out.details).toMatchObject({
				state: "failed",
				reason: "budget-exhausted",
				failure_effect: "known-no-effect",
			});
			expect(flow.posts()).toBe(0);
			const sharedPath = m1af2SharedPath(flow);
			const rowBytes = fs.readFileSync(sharedPath, "utf8");
			const row = JSON.parse(rowBytes) as Record<string, unknown>;
			const offer = m1Details(first.out.details.submit_offer);
			expect(offer.submittable).toBe(true);

			// CONTROL on the same host + same row: with no committed child the
			// authenticated positive verdict holds and no child is spawned.
			const control = await m1af2Observe(() => flow.followup(flow.initialGateId));
			expect(control.raw).toBe("");
			expect(control.spawnCount).toBe(0);
			expect(control.out.details).toMatchObject({ failure_effect: "known-no-effect" });
			expect(m1Details(control.out.details.submit_offer)).toMatchObject({ submittable: true });
			expect(m1af2CommittedChildren(flow)).toHaveLength(0);

			// A REAL committed child business decision for THIS parent/target,
			// written by the official lifecycle writer.
			const child = m1af2CommitChild(flow);
			expect(child, JSON.stringify(child)).toMatchObject({ business_decisions: 1, dp: "dp-pm-steer" });
			expect(child.parent_ref).toBe(flow.initial.gate_ref);
			expect(m1af2CommittedChildren(flow).length).toBeGreaterThanOrEqual(1);

			// The witness still authenticates, the ledger now contradicts it: the
			// independent corroboration keeps the verdict unknown.
			const contradicted = await m1af2Observe(() => flow.followup(flow.initialGateId));
			expect(contradicted.raw).toBe("");
			expect(contradicted.spawnCount).toBe(0);
			expect(contradicted.out.details, JSON.stringify(contradicted.out.details)).toMatchObject({
				state: "failed",
				duplicate: true,
				failure_effect: "unknown",
				parent_released: false,
			});
			expect(m1Details(contradicted.out.details.submit_offer)).toMatchObject({ submittable: false });
			expect(m1Details(contradicted.out.details.submit_offer).gaps).toContain("effect-unknown-no-replay");
			expect(flow.posts()).toBe(0);
			expect(fs.readFileSync(sharedPath, "utf8")).toBe(rowBytes);

			const submit = await flow.submit(String(offer.offer_id), choice, basisId);
			expect(submit.details, submit.text).toMatchObject({
				status: "refused",
				business_completed: false,
				selection_written: false,
				reason: "effect-unknown-no-replay",
			});
			expect(fs.readFileSync(flow.targetFile, "utf8")).toBe(`original-${flow.taskKey}`);
			expect(m1af2Sha(flow.targetFile)).toBe(targetBefore);
			expect(flow.bodies).not.toContain("write");
			expect(flow.host.countsSnapshot()).toMatchObject({ selectionCommits: 0, reserves: 0, observes: 0 });
			expect(row.effect_witness).toBe((JSON.parse(rowBytes) as Record<string, unknown>).effect_witness);
		} finally {
			await flow.cleanup();
		}
	}, 120_000);

	it("the disabled path is NOT exempt: a genuine zero-fact disabled row is positive only where this host observed it", async () => {
		// `disabled` skips the ledger corroboration, so a disabled row is the one
		// shape where a stolen zero-fact copy would otherwise pass. The row below
		// is written by the real follow-up writer onto the REAL production
		// lifecycle fixture of this flow (parent start + gate request), with the
		// real child `disabled` reply shape (0/0/0/false, as mw.py emits).
		const flow = await createM1Flow({ failureMode: "byte-cap", budgetSteps: 3 });
		const zeroFacts = { attempts: 0, transport_attempts: 0, business_decisions: 0, replayed: false };
		const binding: ExpectedDecisionFollowup = {
			...expected,
			parent_ref: "gate:m1-matter-v1",
			parent_decision_id: flow.initial.gate_ref,
			parent_logical_id: flow.initial.logical_id,
			parent_matter_version: flow.initial.substantive_version,
			task_key: flow.taskKey,
		};
		const lifecycle = {
			projectDir: flow.projectRoot,
			parentEvidence: { pmNote: "Prepared PM plan", modelBasis: flow.initial.parent_basis },
		};
		const file = path.join(flow.projectRoot, "m1af2-disabled-witness.json");
		try {
			fs.writeFileSync(file, `${JSON.stringify({ ...dpFixture({ ...binding, status: "prepared" }) })}\n`, "utf8");
			let requests = 0;
			const first = await resumeDecisionFollowup({
				intent_path: file,
				expected: binding,
				bound_pm: boundPm,
				observe_task: () => "not-queued",
				lifecycle,
				request: () => {
					requests += 1;
					return Promise.resolve({ available: false as const, reason: "disabled", effect_facts: zeroFacts });
				},
			});
			expect(first, JSON.stringify(first)).toMatchObject({
				state: "failed",
				reason: "disabled",
				request_started: true,
				failure_effect: "known-no-effect",
			});
			expect(requests).toBe(1);
			const rowBytes = fs.readFileSync(file, "utf8");
			const row = JSON.parse(rowBytes) as Record<string, unknown>;
			expect(row, rowBytes).toMatchObject({ status: "failed", failure_reason: "disabled", effect_facts: zeroFacts });
			expect(String(row.effect_witness)).toMatch(/^[0-9a-f]{64}$/);
			// Repeated on the SAME host + SAME path: still positive, no resend.
			const repeat = await resumeDecisionFollowup({
				intent_path: file,
				expected: binding,
				bound_pm: boundPm,
				observe_task: () => "not-queued",
				lifecycle,
				request: () => {
					throw new Error("M1AF2 must not resend");
				},
			});
			expect(repeat, JSON.stringify(repeat)).toMatchObject({
				state: "failed",
				duplicate: true,
				reason: "disabled",
				failure_effect: "known-no-effect",
				request_started: false,
			});
			expect(requests).toBe(1);
			expect(fs.readFileSync(file, "utf8")).toBe(rowBytes);
			// The SAME genuine bytes on a path this host never wrote: unknown, even
			// though `disabled` needs no ledger corroboration.
			const copyPath = path.join(flow.projectRoot, "m1af2-disabled-restored-host-copy.json");
			fs.writeFileSync(copyPath, rowBytes, "utf8");
			let copyRequests = 0;
			const copied = await resumeDecisionFollowup({
				intent_path: copyPath,
				expected: binding,
				bound_pm: boundPm,
				observe_task: () => "not-queued",
				lifecycle,
				request: () => {
					copyRequests += 1;
					return Promise.resolve({ available: false as const, reason: "disabled", effect_facts: zeroFacts });
				},
			});
			expect(copied, JSON.stringify(copied)).toMatchObject({
				state: "failed",
				reason: "disabled",
				duplicate: true,
				failure_effect: "unknown",
				request_started: false,
				parent_released: false,
			});
			expect(copyRequests).toBe(0);
			// A foreign digest over the same authentic counters: same refusal.
			const foreignPath = path.join(flow.projectRoot, "m1af2-disabled-foreign-witness.json");
			fs.writeFileSync(
				foreignPath,
				`${JSON.stringify({ ...row, effect_witness: "0".repeat(64) }, null, 2)}\n`,
				"utf8",
			);
			let foreignRequests = 0;
			const foreign = await resumeDecisionFollowup({
				intent_path: foreignPath,
				expected: binding,
				bound_pm: boundPm,
				observe_task: () => "not-queued",
				lifecycle,
				request: () => {
					foreignRequests += 1;
					return Promise.resolve({ available: false as const, reason: "disabled", effect_facts: zeroFacts });
				},
			});
			expect(foreign, JSON.stringify(foreign)).toMatchObject({ state: "failed", failure_effect: "unknown" });
			expect(foreignRequests).toBe(0);
		} finally {
			await flow.cleanup();
		}
	}, 120_000);
});
