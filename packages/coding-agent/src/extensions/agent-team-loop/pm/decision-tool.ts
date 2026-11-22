/** Registered PM/worker decision tools. One stdin envelope carries business
 * material, the independently prepared basis catalog, optional context and local
 * identity. Only the generated active entries and the registering window's role
 * can reach the service. A valid reply records consumption. Explicit receipts
 * describe subsequent actions. Signing uses its single dedicated writer. */

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { type TLiteral, Type } from "typebox";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import {
	type DecideConfigFacts,
	type DecisionPreparation,
	decisionActorAllowed,
	decisionChoices,
	decisionIdRefusal,
	inspectPmClaim,
	type MaterialIssue,
	type MaterialReferenceIssue,
	type PmClaimReason,
	type PreparedBasis,
	preparationProblems,
	readDecideConfigFacts,
	resolveDecidePolicy,
	selectedDecisionBasis,
	validateDecisionMaterial,
} from "../shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.ts";
import {
	classifyDecisionFeedback,
	DECISION_HANDOFF_SCHEMA_ID,
	type DecisionFeedback,
	type ExemptionFact,
	type HostBinding,
	type HostFacts,
	isJsonValue,
	type StopSignal,
} from "../shared/decision-handoff.ts";
import { currentClaimId } from "../shared/implementation-gate.ts";
import { readRunState } from "../shared/run-store.ts";
export { validateDecisionMaterial };
export type { MaterialIssue, MaterialValidation } from "../shared/decide-policy.ts";

import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.ts";
import { controlRootFromTaskPath } from "../shared/paths.ts";
import { readTaskType } from "../shared/task-frontmatter.ts";
import {
	type DecisionInputDiagnostics,
	formatInputDiagnostics,
	readInputDiagnostics,
} from "./decision-input-diagnostics.ts";
import {
	AGENT_TASK_STATE_SCHEMA,
	copyTaskState,
	isTaskStateSnapshot,
	type TaskStateSnapshot,
} from "./decision-task-state.ts";
import { checkFileEvidence, type FileEvidenceDependency, parseFileEvidence } from "./file-evidence-cache.ts";
import { PM_GATE_ROUTING_RULE, resolvePmGateRoute } from "./gate-route.ts";
// T04B: the host offer/submit handle is shared in from the registering window.
// Type-only import: host-submit.ts never imports this module at runtime, so the
// composition stays acyclic and no ask/receipt/sign path changes.
import type { PrepareOfferInput, SubmitDecisionHostHandle, SubmitOfferMetadata } from "./host-submit.ts";
import {
	canonicalStateBytes,
	MAX_STRUCTURED_STATE_BYTES,
	prepareDecisionEnvelope,
	readDecidePolicy,
	validateStructuredState,
} from "./triage-client.ts";
import { canPmSelectType, PM_TYPE_FALLBACK_DIRECTIVE } from "./type-fallback.ts";

/** Registered tool name (referenced by `activeToolsForType` wiring in index.ts). */
export const ASK_DECISION_TOOL = "ask_decision";

/** The receipt op: the asking agent records what it ACTUALLY did with a
 * selection (`executed`) and when this round of handling is done (`settled`).
 * It never records on the model's return alone (AC-014). */
export const DECISION_RECEIPT_TOOL = "decision_receipt";

/** Hard client-side wall for one `mw decide run` child (design D-017/D-006). */
export const ASK_DECISION_TIMEOUT_MS = 20_000;

/** Same-dp blocks inside one turn before the tool loop is terminated. */
export const ASK_DECISION_MAX_BLOCKED_PER_TURN = 2;

/** The only failure action the model is ever told about (spec §5.1 fail-closed). */
export const ASK_DECISION_BLOCKED_ACTION = "blocked-ask-human";

/** Client-side canonical state budget for the LEGACY structured path only
 * (spec AC-013 / §5.4). Same number as the structured-input contract, taken
 * from it instead of restated here.
 *
 * It deliberately does NOT gate business material: the four material dps
 * (dp1/dp2/dp3/dp25) are bounded by the single published authority,
 * `decision_points.MAX_STATE_BYTES` (8192B), which refuses the WHOLE material
 * with zero POST and never truncates it. Mirroring that number here would be a
 * second authority, and lowering it would silently shrink real task material
 * the service already accepted (T08 gap 1). */
export const ASK_DECISION_MAX_STATE_BYTES = MAX_STRUCTURED_STATE_BYTES;

/** L1 note cap carried as `task_summary` (matches the Python field validator). */
const NOTE_MAX_BYTES = 600;

/** `key` / `task_key` field cap in the Python state schema. */
const TASK_KEY_MAX_BYTES = 48;

/** IDs and per-entry eligibility follow the generated Python contracts. */
export const ASK_DECISION_DP_IDS = Object.keys(DECIDE_REGISTRY);
export type AskDecisionDpId = string;
export const ASK_DECISION_ENFORCED_STATE_DP_IDS = ASK_DECISION_DP_IDS;

/** Frozen transport reasons (`decision.py:REASON_CODES`). A reason outside this
 * set is normalised to `upstream-error` exactly like `decision.py` does. */
export const ASK_DECISION_PYTHON_REASONS: ReadonlySet<string> = new Set([
	"disabled",
	"entry-unavailable",
	"timeout",
	"rate-limited",
	"upstream-error",
	"transport-unknown",
	"bad-response",
	"unsupported-question-type",
	"budget-exhausted",
	"input-incomplete",
	"input-oversize",
	"role-forbidden",
	"retired",
	"unknown-dp",
]);

/** TS-local refusal reasons (never produced by the Python service; the T-04
 * precedent D-028 keeps them distinct from the frozen 8-value set). */
export const ASK_DECISION_REASON_INPUT_INCOMPLETE = "input-incomplete";
export const ASK_DECISION_REASON_INPUT_OVERSIZE = "input-oversize";

/** Fixed phrase every unavailable payload carries (spec AC-005: no default
 * action, no guessing). */
export const ASK_DECISION_GUESS_DIRECTIVE = "不要自行猜测";

// ── Claim-refusal diagnosis (mw-decision-claim-diagnostics) ──────────────────

/** Stable machine reason carried ONLY by a local claim/key-binding refusal.
 *  PmClaimReason comes from the single inspectPmClaim pass; the two extra codes
 *  are the tool's own worker/role identity branches (never a PM claim reason,
 *  so a non-PM window is never told to re-claim or wait for a PM claim). */
export type ClaimDiagnosisReason = PmClaimReason | "worker-key-mismatch" | "unknown-role";

/** Independent, OPTIONAL diagnosis attached only to the ask/receipt claim
 *  refusals. It never enters the model material or metadata schema. */
export interface ClaimDiagnosis {
	reason: ClaimDiagnosisReason;
	message: string;
	recovery: string;
}

/** Structured result of one boundKey call: the gate value plus the diagnosis
 *  produced by the SAME single read. Diagnosis is present exactly when the
 *  binding was refused (key === undefined); success carries no diagnosis leak. */
export type BoundKeyResult =
	| { key: string; owner?: string; diagnosis?: undefined }
	| { key: undefined; owner?: undefined; diagnosis: ClaimDiagnosis };

/** Common safety constraints reused by every reason-specific diagnosis: no
 *  foreign owner/key list, no absolute path, no raw exception, no extra
 *  MATERIAL field and no local recovery action. The two index-level reasons
 *  keep their separate, precise unknown boundaries below; `meta.key` is named
 *  only to say it is NOT a material field to add. */
export const CLAIM_DIAGNOSIS_MESSAGE =
	"这是本地身份核验未成立，不是审核正文漏填 meta.key；不得把 meta.key 写进 material，" +
	"不得重复提交、抢占认领、自行 re-claim、写索引或更换 CLI 绕过。";

/** PM reasons stop this round and wait for human coordination. This is human
 *  guidance only; the diagnosis never performs a reclaim or an index write. */
export const CLAIM_DIAGNOSIS_RECOVERY =
	'安全下一步：本轮停止，上报 "blocked on decision <dp>" 并等待人工或当前持有窗口协调；' +
	"由人工协调后按框架正常 claim/switch 流程重建本窗口 active 认领（或等待持有窗口释放），" +
	"或带外修复协调索引后由正常流程继续；available:false 为本轮终态，" +
	"诊断不自动重试、不强制接管、不补 material、不写索引、不放宽权限。";

const WORKER_KEY_MISMATCH_RECOVERY =
	'安全下一步：本轮停止，上报 "blocked on decision <dp>"；' +
	"由所属 PM 核对原 task 卡 ownerKey、请求 key 与派发身份；" +
	"available:false 为本轮终态，不补 material、不写索引、不放宽权限。";

const UNKNOWN_ROLE_RECOVERY =
	'安全下一步：本轮停止，上报 "blocked on decision <dp>"；' +
	"由所属 PM 核对注册窗口角色与 task 卡 type 的派发身份；" +
	"available:false 为本轮终态，不补 material、不写索引、不放宽权限。";

/** Short reason-specific facts, never a second authorization verdict. The
 *  empty/unparseable case names exactly the three states the reader cannot
 *  distinguish; the unreadable case names the thrown read without raw errors. */
const CLAIM_DIAGNOSIS_EXPLANATIONS: Readonly<Record<ClaimDiagnosisReason, string>> = {
	ok: "认领校验未通过：未取得唯一有效绑定。",
	"index-unreadable":
		"PM 认领校验未通过：本次索引读取抛出异常，底层原因 unknown；" +
		"该状态不等同于索引缺失、空文件或全部数据行损坏，也不输出异常内容。",
	"index-empty-or-unparseable":
		"PM 认领校验未通过：本次索引读取返回 0 行；" +
		"索引缺失、空文件或全部数据行损坏在既有读取器下无法区分，具体状态 unknown，不得据空结果猜测具体原因。",
	"invalid-key": "PM 认领校验未通过：解析到的 key 名称不符合现有注册约束。",
	"ambiguous-claim": "PM 认领校验未通过：满足本次判定的 active 认领或同名 key 行不唯一，无法解析出唯一绑定。",
	"key-not-found": "PM 认领校验未通过：请求 key 在已解析索引行中不存在。",
	"key-inactive": "PM 认领校验未通过：请求 key 对应行不是 active。",
	"foreign-owner": "PM 认领校验未通过：请求 key 对应的 active 行由另一窗口持有。",
	"no-active-claim": "PM 认领校验未通过：已解析索引中没有本窗口唯一 active 认领。",
	"worker-key-mismatch":
		"worker 身份来自 task 卡：请求 key 与卡路径派生的 ownerKey 不一致，本次卡/请求 key 绑定未成立。",
	"unknown-role": "注册窗口角色或 task 卡 type 未识别，本次身份不能归属到有效 worker/PM 分支。",
};

const CLAIM_DIAGNOSIS_RECOVERIES: Readonly<Record<ClaimDiagnosisReason, string>> = {
	ok: CLAIM_DIAGNOSIS_RECOVERY,
	"index-unreadable": CLAIM_DIAGNOSIS_RECOVERY,
	"index-empty-or-unparseable": CLAIM_DIAGNOSIS_RECOVERY,
	"invalid-key": CLAIM_DIAGNOSIS_RECOVERY,
	"ambiguous-claim": CLAIM_DIAGNOSIS_RECOVERY,
	"key-not-found": CLAIM_DIAGNOSIS_RECOVERY,
	"key-inactive": CLAIM_DIAGNOSIS_RECOVERY,
	"foreign-owner": CLAIM_DIAGNOSIS_RECOVERY,
	"no-active-claim": CLAIM_DIAGNOSIS_RECOVERY,
	"worker-key-mismatch": WORKER_KEY_MISMATCH_RECOVERY,
	"unknown-role": UNKNOWN_ROLE_RECOVERY,
};

// ── Roles and per-dp permissions (AC-006 / AC-010) ──────────────────────────

/** The real initiating role of a decision (lowercase: the vocabulary of the
 * Python lifecycle writer `decision_lifecycle.INITIATOR_ROLES`). The role is
 * structural — taken from the window that registered the tool, never from a
 * model-supplied parameter. */
export type DecisionToolRole = "pm" | "coding" | "research" | "review";

/** `unknown` is the honest role of a worker whose card cannot be read; Python
 * accepts it (`INITIATOR_ROLES`) and it never impersonates the PM. */
export type DecisionInitiatorRole = DecisionToolRole | "unknown";

export const ASK_DECISION_PM_ONLY_DP_IDS = ASK_DECISION_DP_IDS.filter((dp) => DECIDE_REGISTRY[dp].roleScope === "pm");
export const ASK_DECISION_MATERIAL_DP_IDS = ASK_DECISION_DP_IDS;

/** dp3 native dynamic-choice protocol (`decision_points.dynamic_choices_value_error`). */
export const DP3_ID = "dp3-worker-clarify";
export const DP3_HANDLING_MIN_OPTIONS = 2;
export const DP3_HANDLING_MAX_OPTIONS = 5;
export const DP3_HANDLING_LABEL_MAX = 80;

/** TS-local refusal reasons (never produced by the Python service, D-028). */
export const ASK_DECISION_REASON_ROLE_FORBIDDEN = "role-forbidden";
export const ASK_DECISION_REASON_UNKNOWN_DECISION = "unknown-decision";
export const ASK_DECISION_REASON_UNKNOWN_ACTION = "unknown-action";

/** Record version of the local envelope (design §4.1; T02's
 * `decision_lifecycle.RECORD_VERSION`). The meta never reaches the model. */
export const DECISION_RECORD_VERSION = 2;

// ── Payload shapes ──────────────────────────────────────────────────────────

export type AskDecisionMode = "auto" | "suggest";

/** `answers` is the registry question set echoed by the service: question id →
 * `{value, confidence?}`. Mutable JSON only. */
export type AskDecisionAnswers = Record<string, { value: unknown; confidence?: number | null }>;

/** The native choice resolved back to the candidate the ORIGINAL asker sent.
 * `label`/`description` are present only when this tool holds the candidate
 * list itself (dp3's `handling_options`); dp2/dp25 labels stay in the Python
 * registry and are never re-declared here. */
export interface DecisionSelection {
	question: string;
	id: string;
	label?: string;
	description?: string;
}

/** One feedback fact this consumer actually wrote / failed to write (AC-014). */
export interface DecisionFeedbackResult {
	stage: "consumed" | "executed" | "settled";
	/** The writer's own verdict. `written`/`duplicate` are recorded facts (a
	 * duplicate is the SAME event replayed, never a second row); `failed` means
	 * the ledger holds no fact for this stage. */
	status: "written" | "duplicate" | "failed";
	/** The writer's `recorded` flag, taken verbatim from its `--json` receipt. */
	recorded: boolean;
	reason?: string;
}

export interface AskDecisionAvailable {
	available: true;
	decision_id: string;
	/** The child's execution mode. Omitted on the dp25 sign path: `decide sign`
	 * has no mode verdict, and inventing one here would misreport authority. */
	mode?: AskDecisionMode;
	acted: boolean;
	answers: AskDecisionAnswers;
	confidence_source: string;
	latency_ms: number;
	/** Set on the prepared material path: the exact candidate the selection names. */
	selection?: DecisionSelection;
	basis?: PreparedBasis;
	/** Set on the prepared material path: the automatic `consumed` write result. */
	feedback?: DecisionFeedbackResult;
	/** Set on the dp25 path: the sign CLI's own receipt (one judgment, real
	 * sign-off write or a concrete PM/user handoff). */
	signoff?: DecisionSignoffResult;
	/** T04A: the frozen T01 classification of THIS result. Independent of the
	 * typed `feedback` lifecycle result above; never overwrites consumed/executed/
	 * settled facts. Present on every public ask result. */
	decision_feedback?: DecisionFeedback;
	/** True only when an identical matter was already answered/failed and the
	 * cached frozen feedback is replayed instead of sending a new DP request. */
	matter_suppressed?: true;
}

/** The dp25 sign CLI's receipt, mapped 1:1 (no derived success).
 *
 * `status` is the CLI's `signoff_status`: `written`/`existing` mean the
 * `evidence/review/sign-final.md` file really validates for this
 * `logical_id`; `not-required` means continue/user-confirm wrote no file;
 * `failed`/`invalid-existing`/`disabled` are reported as-is. */
export interface DecisionSignoffResult {
	status: "written" | "existing" | "not-required" | "failed" | "invalid-existing" | "disabled";
	path?: string;
	/** Always 0: the one judgment IS the sign-off (no second approval). */
	second_approval: number;
	/** The persisted dp25 result record status (`written`/`existing`/`failed:*`). */
	record_status?: string;
	/** False when the CLI replayed an existing result instead of calling the
	 * model (a retry of the same logical id). */
	model_called?: boolean;
	/** The lifecycle feedback aggregate the CLI recorded (`recorded`/`partial`/...). */
	feedback_status?: string;
	feedback_stages?: Array<{ stage?: string | null; status?: string | null; event_id?: string | null }>;
	problems?: string[];
	/** continue/user-confirm: the concrete next step for the PM or the user. */
	handoff?: { owner?: string; kind?: string; signoff_writes?: number; instruction?: string };
}

export interface AskDecisionUnavailable {
	available: false;
	unavailable: string;
	action: typeof ASK_DECISION_BLOCKED_ACTION | "pm-select-type";
	/** The child's own escalation verdict (`decision_points.ESCALATED_REASONS`,
	 * 7 values) passed through verbatim. `unavailable` keeps the frozen legacy
	 * transport vocabulary; the two coexist, neither is folded into the other
	 * (D-021 / `_DECIDE_RUN_REASON_MAP`). */
	escalated_reason?: string;
	/** State fields the registry requires and this call site could not supply
	 * (names only, L0). Only present on a zero-spawn `input-incomplete` refusal. */
	missing_fields?: string[];
	/** Registry-owned validation rules/counts for locally refused material.
	 * Present-but-invalid values are not reported as missing fields. */
	material_issues?: MaterialIssue[];
	/** Independent diagnosis for a LOCAL claim/key-binding refusal only. Never
	 * present on the default unavailable payload or the pm-select-type path. */
	claim_diagnosis?: ClaimDiagnosis;
	/** T04A: the frozen T01 classification of THIS result, including verbatim
	 * `raw_reason` captured before frozen-transport normalisation. */
	decision_feedback?: DecisionFeedback;
	/** True only on a same-matter replay (no new DP request was sent). */
	matter_suppressed?: true;
	input_diagnostics?: DecisionInputDiagnostics;
	preparation_status?: "needs-evidence" | "equivalent" | "needs-review";
	original_blocked_event_id?: string;
}

export type AskDecisionPayload = AskDecisionAvailable | AskDecisionUnavailable;

/** Result of one tool attempt: the payload plus the exact text handed back. */
export interface AskDecisionOutcome {
	payload: AskDecisionPayload;
	/** Single-line JSON, plus the fixed directive line when unavailable. */
	text: string;
	/** False means the tool refused before any spawn (unregistered dp /
	 * structurally incomplete state). Never a local authorization verdict. */
	spawned: boolean;
	/** The local envelope meta this call minted (material path only). It is the
	 * join key of every feedback row and is NEVER handed to the model. */
	meta?: DecisionToolMeta;
	/** INTERNAL ONLY. The verbatim untrusted observation captured BEFORE
	 * `unavailable()` normalises a child reason into the frozen transport
	 * vocabulary. Never serialised into the payload or the model text. */
	observation?: DecisionFeedbackObservation;
	/** T04A: the frozen T01 classification of this result. It lives on the
	 * outcome (NOT inside the legacy `payload`), so the frozen D-036 payload
	 * shape, its exact-key tests and the DP receipt join stay byte-identical.
	 * The registered tool exposes it in `details` and as the second text line. */
	decision_feedback?: DecisionFeedback;
}

/** One real host-observed feedback source/stage. `raw` is verbatim data
 *  (child JSON, child stdout text or a local refusal fact), never model text
 *  promoted to an authority/stop fact. */
export interface DecisionFeedbackObservation {
	origin: string;
	stage: string;
	raw: unknown;
	evidenceRefs?: string[];
	/** A real host business exemption (signoff=disable), never a service fault. */
	exemption?: ExemptionFact;
	/** Set only when a structured service reply carried a missing, empty,
	 *  non-string or unknown reason and was folded to `upstream-error`. The
	 *  verbatim reply stays in `raw` for diagnosis; this flag stops the folded
	 *  value from buying the legacy PM type-handoff permission. Internal only. */
	reasonFolded?: boolean;
}

/** Trusted host context for one public ask. `binding` is built ONLY from this
 *  window's live claim or its worker task/run record; model-supplied owner/p0/
 *  stop text can never enter `host`. `host.stop_signals`/`budget_facts` is a
 *  typed T06 connection point for real cancellation/budget signals; T04A
 *  leaves it absent by default and never invents a stop or a budget. */
/** Host-only typed PM stage coordinates. A model parameter can never mint one. */
export interface DecisionStageIdentity {
	key: string;
	claimId: string;
	stageId: string;
	scopeRef: string;
	matterRef: string;
	grantDigest: string;
}

export interface DecisionHostContext {
	host: HostFacts;
	binding: HostBinding;
	/** Stable matter identity: real binding coordinates + substantive request
	 * facts + the frozen contract/mode version. Never includes trigger or turn. */
	matterRef: string;
	origin: string;
	stage: string;
	/** Verified PM stage source, when this window owns a real admitted stage. */
	stageSource?: DecisionStageIdentity;
}

/** Config facts reader (unit-injectable). Production uses the real reader. */
export type DecideConfigReader = (dp: string, projectDir: string) => DecideConfigFacts;

/** Real production reader: `readDecidePolicy` (the dispatch path's existing
 *  `.mw/decide.json` switch) plus the read-only per-dp/signoff facts from
 *  decide-policy's own `readJsonRecord` chain. A disagreement can only make a
 *  transport fact more conservative, never silently "on". */
export const readRealDecideConfigFacts: DecideConfigReader = (dp, projectDir) => {
	const facts = readDecideConfigFacts(dp, projectDir);
	if (readDecidePolicy(projectDir).enabled) return facts;
	return { ...facts, transport: facts.transport === "on" ? "off" : facts.transport };
};

/** Canonical JSON with sorted object keys: stable across turns/serialisers. */
function stableJson(value: unknown): string {
	if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
	if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
	const record = value as Record<string, unknown>;
	return `{${Object.keys(record)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`)
		.join(",")}}`;
}

/** Matter digest: the dedup key AND `matter_ref`. `trigger` and turn are
 *  deliberately absent, so neither can buy another DP request or more scope
 *  budget. A genuinely changed material/preparation/context re-prepares. */
export function decisionMatterRef(parts: Record<string, unknown>): string {
	return createHash("sha256").update(stableJson(parts)).digest("hex").slice(0, 32);
}

/** Observation timestamps are NOT substantive matter facts. Re-stamping only
 *  `prepared_at` or `task_before.observed_at` must not mint a new matter or a
 *  second DP request, while every substantive preparation, material, binding,
 *  deadline, budget and stop fact keeps distinguishing matters. The excluded
 *  fields are still really validated on every call (shape/freshness), so a
 *  timestamp cannot buy a suppressed safety refusal. */
function matterIdentityParts(value: unknown, observationFields: readonly string[]): unknown {
	if (!isRecord(value)) return value;
	const parts: Record<string, unknown> = {};
	for (const [key, item] of Object.entries(value)) {
		if (!observationFields.includes(key)) parts[key] = item;
	}
	return parts;
}

/** The frozen contract/mode version of this public entry (T01 schema + the
 *  local envelope record version). It is part of every matter identity. */
export function decisionMatterVersion(): string {
	return `${DECISION_HANDOFF_SCHEMA_ID}:record-v${DECISION_RECORD_VERSION}`;
}

/** Mint a real host binding snapshot. Unknown coordinates stay absent (the T01
 *  classifier records them as gaps); `binding_version` is the frozen contract
 *  id, NOT a fabricated live claim version. */
function hostBinding(input: {
	role: DecisionInitiatorRole;
	key?: string;
	taskKey?: string | null;
	claimId?: string;
	runId?: string;
	owner?: string;
}): HostBinding {
	return {
		role: input.role,
		...(input.owner === undefined ? {} : { owner: input.owner }),
		...(input.claimId === undefined ? {} : { claim_id: input.claimId }),
		...(input.key === undefined ? {} : { key: input.key }),
		...(input.taskKey === undefined || input.taskKey === null ? {} : { task_key: input.taskKey }),
		...(input.runId === undefined ? {} : { run_id: input.runId }),
		binding_version: DECISION_HANDOFF_SCHEMA_ID,
		observed_at: new Date().toISOString(),
	};
}

/** Attach the frozen T01 classification to a public ask result. `raw` is the
 *  verbatim pre-normalisation observation when one exists; otherwise the local
 *  payload itself is the honest raw fact (nothing was lost upstream). The text
 *  suffix (directives/diagnosis) is preserved byte-for-byte. */
export function attachDecisionFeedback(
	outcome: AskDecisionOutcome,
	context: DecisionHostContext,
	observation?: DecisionFeedbackObservation,
): AskDecisionOutcome {
	const payload = outcome.payload;
	const obs = observation ?? outcome.observation;
	// A malformed SUCCESS reply that LOCAL business validation refused keeps its
	// verbatim child JSON (raw_payload) and mw-decide-run / service-reply
	// origin/stage, but the frozen classifier must classify the LOCAL
	// bad-response fact: handing it an available:true child reply would promote
	// a wrong id / illegal mode / bad basis / acted / answers to answer|advisory.
	// The verbatim reply is preserved as evidence, never rewritten to classify.
	const localBadResponse =
		!payload.available &&
		payload.unavailable === "bad-response" &&
		obs !== undefined &&
		isRecord(obs.raw) &&
		obs.raw.available === true;
	const verbatimRaw = localBadResponse && obs !== undefined ? obs.raw : undefined;
	// R6 (RV3-F1): a child `effect_state`/`side_effect` = "unknown" is ONLY
	// conservative uncertainty, never a trusted host authority or an
	// ExecutionProof. Carry just those two markers into the synthetic local
	// bad-response classification raw so the frozen classifier keeps
	// effect_state=unknown / category=effect-unknown from its own signal read.
	// No available:true / answers / mode / acted / id is carried, so a malformed
	// success can never be promoted to answer|advisory or any authority. The
	// verbatim child JSON is still re-attached as raw_payload below; a child with
	// no unknown marker keeps the structured "none".
	const localUnknownMarkers: Record<string, "unknown"> = {};
	if (isRecord(verbatimRaw)) {
		if (verbatimRaw.effect_state === "unknown") localUnknownMarkers.effect_state = "unknown";
		if (verbatimRaw.side_effect === "unknown") localUnknownMarkers.side_effect = "unknown";
	}
	const raw: unknown = localBadResponse
		? { unavailable: "bad-response", raw_reason: "bad-response", ...localUnknownMarkers }
		: obs !== undefined
			? obs.raw
			: payload.available
				? { available: true, decision_id: payload.decision_id, answers: payload.answers, mode: payload.mode }
				: {
						unavailable: payload.unavailable,
						raw_reason: payload.unavailable,
						...(payload.escalated_reason === undefined ? {} : { escalated_reason: payload.escalated_reason }),
						...(payload.missing_fields === undefined ? {} : { missing_fields: payload.missing_fields }),
						...(payload.material_issues === undefined ? {} : { material_issues: payload.material_issues }),
						...(payload.claim_diagnosis === undefined ? {} : { claim_reason: payload.claim_diagnosis.reason }),
					};
	const host: HostFacts = obs?.exemption === undefined ? context.host : { ...context.host, exemption: obs.exemption };
	outcome.decision_feedback = classifyDecisionFeedback({
		envelope: {
			feedback_ref: randomUUID(),
			matter_ref: context.matterRef,
			origin: obs?.origin ?? context.origin,
			stage: obs?.stage ?? context.stage,
			...(obs?.evidenceRefs === undefined ? {} : { evidence_refs: obs.evidenceRefs }),
		},
		host,
		raw,
	});
	if (verbatimRaw !== undefined && isJsonValue(verbatimRaw)) {
		outcome.decision_feedback.raw_payload = verbatimRaw;
	}
	return outcome;
}

// ── Structured state: per-dp required fields (single source: triage-client) ──

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** True for the active IDs the tool exposes (and therefore for every id Python can
 * resolve); the enum itself is pinned to `DP_REGISTRY` by the suite. */
export function isRegisteredDp(dp: string): dp is AskDecisionDpId {
	return (ASK_DECISION_DP_IDS as readonly string[]).includes(dp);
}

// ── Request envelope ────────────────────────────────────────────────────────

/** Code-point-safe UTF-8 truncation (never splits a surrogate pair). */
export function truncateUtf8(text: string, maxBytes: number): string {
	if (Buffer.byteLength(text, "utf8") <= maxBytes) return text;
	let out = "";
	let used = 0;
	for (const char of text) {
		const size = Buffer.byteLength(char, "utf8");
		if (used + size > maxBytes) break;
		out += char;
		used += size;
	}
	return out;
}

export interface AskDecisionStateInput {
	dp: string;
	note?: string;
	taskKey?: string | null;
}

/**
 * Build the bounded structured `state` sent to the service (spec §5.4 L0/L1).
 *
 * Only registry-schema keys this call site actually knows are used
 * (`schema_version`/`decision_point`/`key`/`task_key`/`task_summary`): the dp's own required block
 * (`phase`/`risk`/`scope.*`/`progress.*`/`ambiguity.*`, ...) has no honest
 * source here, so it stays absent and {@link missingDecisionStateFields}
 * reports it instead of the envelope inventing values. Python fills
 * `questions_version` from the registry (`decision_points._state_builder`).
 * L2 material (code, transcripts, absolute paths) has no key to ride and the
 * prompt guidelines forbid putting it in `note`.
 */
export function buildDecisionState(input: AskDecisionStateInput): Record<string, unknown> {
	const state: Record<string, unknown> = { schema_version: 2, decision_point: input.dp };
	if (input.taskKey !== undefined && input.taskKey !== null && input.taskKey !== "") {
		const key = truncateUtf8(input.taskKey, TASK_KEY_MAX_BYTES);
		state.key = key;
		state.task_key = key;
	}
	if (input.note !== undefined && input.note.trim() !== "") {
		state.task_summary = truncateUtf8(input.note.trim(), NOTE_MAX_BYTES);
	}
	return state;
}

/** Fields the client-side check must not ask for: Python's `_state_builder`
 * fills `questions_version` from the registry (`decision_points.py:278`), so it
 * is never missing at step 5 and the caller cannot supply it. */
const PYTHON_AUTO_FILLED_FIELDS: ReadonlySet<string> = new Set([
	"questions_version",
	"schema_version",
	"decision_point",
]);

/**
 * The refusal list `decide_for` step 5 would produce for `dp` and `state` —
 * field names only (L0), empty when the state is sendable.
 *
 * The field list is the GENERATED REGISTRY (`DECIDE_REGISTRY`, from
 * `decision_points.REQUIRED_STATE_FIELDS`), never a second local table: the four
 * DPs moved to the business contract in T01, so the old structured-input table
 * (`triage-client.REQUIRED_FIELDS_BY_DP`) no longer describes them. Identity
 * keys Python fills itself are not the caller's to supply.
 */
export function missingDecisionStateFields(dp: string, state: Record<string, unknown>): string[] {
	if (!isMaterialStateDp(dp)) {
		// The other 21 dps keep the pre-existing structured-input table (their
		// contract did not change in T01); over-gating them here would narrow a
		// call Python already accepts.
		if (!(ASK_DECISION_ENFORCED_STATE_DP_IDS as readonly string[]).includes(dp)) return [];
		return validateStructuredState(dp, state).filter((field) => !PYTHON_AUTO_FILLED_FIELDS.has(field));
	}
	const entry = DECIDE_REGISTRY[dp];
	if (entry === undefined) return [];
	const missing: string[] = [];
	for (const field of entry.requiredStateFields) {
		if (PYTHON_AUTO_FILLED_FIELDS.has(field.name)) continue;
		const value = readMaterialPath(state, field.name);
		if (value === undefined || value === null) missing.push(field.name);
		else if (field.type === "string" && (typeof value !== "string" || value.trim() === "")) {
			missing.push(field.name);
		}
	}
	return missing;
}

/** Serialise the request envelope (single line; questions come from the
 * registry because `--dp` is always given, design D-027). */
export function buildDecisionRequestJson(state: Record<string, unknown>): string {
	return JSON.stringify({ state });
}

// ── Business material: dp2 / dp3 / dp25 (design §2, T01 registry) ────────────

/** The local envelope metadata (design §4.1). Never part of the material. */
export interface DecisionToolMeta {
	record_version: typeof DECISION_RECORD_VERSION;
	/** One fresh UUID per real decision; every feedback row joins on it. */
	logical_id: string;
	key: string;
	/** The REAL task this decision belongs to, or `null` (a PM decision with no
	 * task). Never "the latest task" by inference (AC-010). */
	task_key: string | null;
	initiator_role: DecisionInitiatorRole;
	/** Set only when this decision retries another one (new id, points at前次). */
	retry_of: string | null;
	task_before?: TaskStateSnapshot;
}

/** The stdin payload for `mw decide run <dp> --stdin` (design §4.1). */
export interface DecisionToolEnvelope {
	parent_decision_ref?: string;
	preparation: DecisionPreparation;
	context?: Record<string, unknown>;
	material: Record<string, unknown>;
	meta: DecisionToolMeta;
	evidence_refs?: DecisionEvidenceRef[];
}

interface DecisionEvidenceRef {
	field: string;
	path: string;
	lines?: { start: number; end: number };
}

/** True when `dp` is one the PM alone may prepare (checkpoint / sign-off). */
export function isPmOnlyDp(dp: string): boolean {
	return (ASK_DECISION_PM_ONLY_DP_IDS as readonly string[]).includes(dp);
}

/** True when `dp` carries the business material contract instead of the legacy
 * L0/L1 `task_summary` state. */
export function isMaterialDp(dp: string): boolean {
	return (ASK_DECISION_MATERIAL_DP_IDS as readonly string[]).includes(dp);
}

/** The dps whose field contract T01 replaced with the four-dp business schema:
 * the three workers' material dps plus dp1 (the PM dispatch producer, whose
 * material belongs to T03 but whose required fields are the same registry). */
function isMaterialStateDp(dp: string): boolean {
	return isMaterialDp(dp);
}

/** Look one registry path (dotted) up in a material/state object. */
function readMaterialPath(source: unknown, dotted: string): unknown {
	let current: unknown = source;
	for (const segment of dotted.split(".")) {
		if (!isRecord(current)) return undefined;
		current = current[segment];
	}
	return current;
}

/** Read the declared business paths of a material object (registry order). */
export function missingMaterialPaths(dp: string, material: unknown): string[] {
	const entry = DECIDE_REGISTRY[dp];
	if (entry === undefined) return ["dp"];
	const missing: string[] = [];
	for (const field of entry.requiredStateFields) {
		if (readMaterialPath(material, field.name) === undefined) missing.push(field.name);
	}
	return missing;
}

/** Build the local envelope metadata for ONE new decision.
 *
 * A registered PM can supply its host-derived matter identity across sessions.
 * Other callers mint a fresh ID. An explicit retry points at its previous ID.
 */
export function buildDecisionToolMeta(input: {
	key: string;
	logicalId?: string;
	taskKey?: string | null;
	initiatorRole: DecisionInitiatorRole;
	retryOf?: string | null;
	taskBefore?: TaskStateSnapshot;
}): DecisionToolMeta {
	const taskKey = input.taskKey?.trim() ?? "";
	const retryOf = input.retryOf?.trim() ?? "";
	return {
		record_version: DECISION_RECORD_VERSION,
		logical_id: input.logicalId ?? randomUUID(),
		key: input.key.trim(),
		task_key: taskKey === "" ? null : taskKey,
		initiator_role: input.initiatorRole,
		retry_of: retryOf === "" ? null : retryOf,
		...(input.taskBefore === undefined ? {} : { task_before: copyTaskState(input.taskBefore) }),
	};
}

/** Assemble the `{material, meta}` envelope after a last closed-set check. */
export function buildDecisionEnvelope(input: {
	dp: string;
	material: Record<string, unknown>;
	meta: DecisionToolMeta;
	/** Local reference supplied by the host consuming a prepared follow-up. */
	parentDecisionRef?: string;
	preparation?: DecisionPreparation;
	context?: Record<string, unknown>;
}): DecisionToolEnvelope {
	const prepared = prepareDecisionEnvelope(
		input.dp,
		input.material,
		input.meta,
		0,
		input.preparation,
		input.context,
		input.parentDecisionRef,
	);
	if (!prepared.ok) throw new Error(`invalid decision envelope: ${prepared.reason} ${prepared.missing.join(", ")}`);
	return prepared.envelope;
}

/** The worker's real lifecycle role, read from its own card's `type:`.
 *
 * Framework types follow the approved Python `_FRAMEWORK_CARD_ROLES` mapping,
 * not the model-role buckets or the four-choice dispatch menu. Unknown, retired
 * and PM card types stay unknown; a caller option cannot upgrade the card. */
export function initiatorRoleFromWorkerTask(taskPath: string | undefined): DecisionInitiatorRole {
	if (taskPath === undefined || taskPath === "") return "unknown";
	let text: string;
	try {
		text = fs.readFileSync(taskPath, "utf8");
	} catch {
		return "unknown";
	}
	const type = readTaskType(text).type;
	switch (type) {
		case "coding":
		case "vision":
		case "repair":
		case "roadmap-writer":
		case "phase-writer":
			return "coding";
		case "research":
		case "verifier":
		case "reviewer":
		case "rag-research":
		case "decide_prepare":
			return "research";
		case "review":
			return "review";
		default:
			return "unknown";
	}
}

/** Resolve dp3's native `handling` answer to the candidate the asker supplied. */
export function resolveHandlingSelection(answers: unknown, options: unknown): DecisionSelection | undefined {
	if (!isRecord(answers) || !Array.isArray(options)) return undefined;
	const entry = answers.handling;
	const value = isRecord(entry) ? entry.value : undefined;
	if (typeof value !== "string" || value === "") return undefined;
	for (const raw of options) {
		if (!isRecord(raw) || raw.id !== value) continue;
		const label = typeof raw.label === "string" ? raw.label : undefined;
		const description = typeof raw.description === "string" ? raw.description : undefined;
		return { question: "handling", id: value, label, description };
	}
	return undefined;
}

/** The selection a four-dp answer names, or `undefined` when the child answered
 * a question set this contract no longer owns. */
function buildSelection(
	dp: string,
	answers: AskDecisionAnswers,
	material: Record<string, unknown>,
): DecisionSelection | undefined {
	if (DECIDE_REGISTRY[dp].kind === "dynamic-candidates")
		return resolveHandlingSelection(answers, material.handling_options);
	const question = DECIDE_REGISTRY[dp].businessQuestionId;
	if (question === undefined) return undefined;
	const value = answers[question]?.value;
	if (typeof value !== "string" || value.trim() === "") return undefined;
	return { question, id: value };
}

/** Read-only composition aid. A preview neither checks authority nor issues a ruling. */
export function previewDecisionInput(
	dp: string,
	material: Record<string, unknown> = {},
	preparation?: DecisionPreparation,
	context?: Record<string, unknown>,
	refs: readonly { field: string }[] = [],
) {
	const allowed_choices = decisionChoices(dp, material);
	const evidence_fields: string[] = [];
	function collect(value: unknown, field: string): void {
		if (typeof value === "string") evidence_fields.push(field);
		else if (Array.isArray(value)) {
			for (const [index, item] of value.entries()) collect(item, `${field}[${index}]`);
		} else if (value && typeof value === "object") {
			for (const [name, item] of Object.entries(value)) {
				if (/^[A-Za-z_][A-Za-z0-9_-]*$/.test(name)) collect(item, `${field}.${name}`);
			}
		}
	}
	collect(material, "material");
	preparation?.basis_catalog.forEach((item, index) => {
		if (typeof item.text === "string") evidence_fields.push(`preparation.basis_catalog[${index}].text`);
	});
	collect(preparation?.model_context?.desc, "preparation.model_context.desc");
	if (isRecord(preparation?.model_context?.review)) {
		for (const [name, row] of Object.entries(preparation.model_context.review)) {
			if (/^(?:AC|VC)-[0-9]{3}$/.test(name) && isRecord(row) && typeof row.evidence === "string")
				evidence_fields.push(`preparation.model_context.review.${name}.evidence`);
		}
	}
	const valid = validateDecisionMaterial(dp, material);
	const issues: MaterialIssue[] = valid.ok ? [] : [...valid.issues];
	const references: MaterialReferenceIssue[] = [];
	const problems = preparationProblems(dp, material, preparation, context, references, issues);
	for (const field of problems) {
		if (
			!issues.some((issue) => issue.field === field) &&
			!references.some((issue) => issue.field === field || issue.field.startsWith(`${field}[`))
		)
			issues.push({ field, rule: "required or invalid preparation field" });
	}
	issues.push(...references);
	for (const [index, ref] of refs.entries()) {
		if (!evidence_fields.includes(ref.field))
			issues.push({
				field: `evidence_refs[${index}].field`,
				code: "unknown-field",
				rule: "select an existing evidence field",
			});
	}
	return { preview: true as const, transport: "not-sent" as const, allowed_choices, evidence_fields, issues };
}

/** The fixed material-preparation prompts handed to the asking agent
 * (design §2 "固定提示"). They are part of the tool contract, not UI copy. */
export const DECISION_MATERIAL_PROMPTS = Object.fromEntries(
	Object.entries(DECIDE_REGISTRY).map(([id, entry]) => [
		id,
		`${id} (${entry.roleScope}, applies_to: ${entry.kind === "dynamic-candidates" ? "IDs from material.handling_options" : decisionChoices(id, {}).join(", ")}): ${[...entry.requiredStateFields, ...entry.optionalStateFields].map((field) => `${field.name} — ${field.description}`).join("; ")}`,
	]),
);

// ── Feedback: `mw decide lifecycle --stdin` (T02 writer, AC-014) ─────────────

/** The closed action set of T02's `decision_lifecycle.EXECUTED_ACTIONS`. An
 * action outside it is never recorded ("未知动作只未记录"). */
export const DECISION_EXECUTED_ACTIONS: readonly string[] = [
	"type-read",
	"pm-handoff",
	"clarify",
	"narrow",
	"split",
	"direct-exec",
	"escalate",
	"continue",
	"user-confirm",
	"record",
];

/** The closed outcome set of T02's `decision_lifecycle.OUTCOMES`. */
export const DECISION_OUTCOMES: readonly string[] = ["pending", "ok", "rework", "rollback", "inconclusive"];

/** One lifecycle fact envelope (`mw decide lifecycle --stdin`). */
export interface DecisionLifecycleEnvelope {
	meta: DecisionToolMeta;
	decision_id: string;
	dp: string | null;
	stage: "consumed" | "executed" | "settled";
	event_id: string;
	task_after?: TaskStateSnapshot;
	answer?: string;
	action?: string;
	result?: string;
	outcome?: string;
	reason?: string;
}

/** One lifecycle child invocation (stdin payload included). */
export interface LifecycleRequest {
	projectDir: string;
	input: string;
	timeoutMs: number;
}

/** Injectable lifecycle runner (tests stub this; production spawns the CLI). */
export type LifecycleRunner = (request: LifecycleRequest) => Promise<RawDecideResult>;

/** Hard wall for one feedback child: a feedback write must never stall a tool. */
export const DECISION_LIFECYCLE_TIMEOUT_MS = 10_000;

/** Build `python -X utf8 mw.py decide lifecycle --stdin --json ...` (T05
 * contract). `--json` makes the writer report its own `recorded`/`status`, so a
 * consumer never infers success from exit code 0 (a `duplicate` replay is a
 * recorded fact too, and the payload says which one it was). */
export function buildLifecycleArgv(mwPy: string, projectDir: string): string[] {
	return ["-X", "utf8", mwPy, "decide", "lifecycle", `--project=${projectDir}`, "--stdin", "--json"];
}

/** The real feedback child: the payload rides stdin, never argv. */
export const runLifecycleMw: LifecycleRunner = async (request) => {
	const mwPy = findMwPy();
	if (!mwPy) return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
	return spawnWithTimeout([PYTHON_EXE, ...buildLifecycleArgv(mwPy, request.projectDir)], {
		timeoutMs: request.timeoutMs,
		stdin: request.input,
	});
};

// ── dp25: one judgment that really signs (T05 `decide sign --stdin`) ────────

/** The dp25 sign-off conclusion point (the managed PM sign path). */
export const DP25_ID = "dp25-signoff-conclusion";
export const SIGN_KEY_ID = "dp-sign-key";

/** The three conclusions T05 accepts (`decision_signoff_result.CONCLUSIONS`). */
export const DECISION_SIGNOFF_CONCLUSIONS: readonly string[] = ["finalize", "continue", "user-confirm"];

/** One `mw decide sign <key> --stdin --json` invocation. */
export interface SignRequest {
	projectDir: string;
	key: string;
	input: string;
	timeoutMs: number;
	explicitEvidence?: boolean;
}

/** Injectable sign runner (tests stub this; production spawns the CLI). */
export type SignRunner = (request: SignRequest) => Promise<RawDecideResult>;

/** Build `python -X utf8 mw.py decide sign <key> --stdin --json`.
 *
 * `--stdin` selects T05's versioned PM-material path; WITHOUT it the command
 * falls back to the legacy signoff-only auto path, which has no typed material
 * and therefore cannot be this feature's writer. */
export function buildSignArgv(mwPy: string, key: string, projectDir: string): string[] {
	return ["-X", "utf8", mwPy, "decide", "sign", key, `--project=${projectDir}`, "--stdin", "--json"];
}

/** The real sign child: the envelope rides stdin, never argv. */
export const runSignMw: SignRunner = async (request) => {
	const mwPy = findMwPy();
	if (!mwPy) return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
	if (request.explicitEvidence && !(await probeDecisionCapabilities(mwPy)).explicitEvidence) {
		return unsupportedEvidenceReply();
	}
	return spawnWithTimeout([PYTHON_EXE, ...buildSignArgv(mwPy, request.key, request.projectDir)], {
		timeoutMs: request.timeoutMs,
		stdin: request.input,
	});
};

/** Write one feedback fact through the single Python lifecycle writer.
 *
 * Never throws and never claims success: a timeout, a non-zero exit, a missing
 * CLI, an unparsable receipt or `recorded:false` all become `status:"failed"`
 * with the child's own class, so the caller can report "反馈缺失" instead of
 * fabricating the row. A `duplicate` receipt is reported as `duplicate` (the
 * same event replayed), never silently rewritten to `written`.
 *
 * Exported because the dp1 dispatch consumer is a second real writer face: one
 * CLI writer implementation serves dp1, dp3 and dp25.
 */
export async function writeDecisionLifecycle(
	projectDir: string,
	envelope: DecisionLifecycleEnvelope,
	runner: LifecycleRunner = runLifecycleMw,
): Promise<DecisionFeedbackResult> {
	const stage = envelope.stage;
	try {
		const raw = await runner({
			projectDir,
			input: JSON.stringify(envelope),
			timeoutMs: DECISION_LIFECYCLE_TIMEOUT_MS,
		});
		if (raw.timedOut) return { stage, status: "failed", recorded: false, reason: "timeout" };
		if (raw.error !== undefined) return { stage, status: "failed", recorded: false, reason: "unavailable" };
		const receipt = parseDecisionJson(raw.stdout);
		if (receipt === undefined) {
			return { stage, status: "failed", recorded: false, reason: raw.status === 0 ? "bad-response" : "cli-error" };
		}
		if (receipt.recorded !== true) {
			const errorClass = typeof receipt.error_class === "string" ? receipt.error_class : "rejected";
			return { stage, status: "failed", recorded: false, reason: errorClass };
		}
		const status = receipt.status === "duplicate" ? "duplicate" : "written";
		return { stage, status, recorded: true };
	} catch {
		return { stage, status: "failed", recorded: false, reason: "runner-threw" };
	}
}

// ── Async spawn with a hard wall ────────────────────────────────────────────

export interface RawDecideResult {
	status: number | null;
	stdout: string;
	stderr: string;
	/** Spawn-level failure text (missing mw.py, ENOENT, aborted, ...). */
	error?: string;
	timedOut: boolean;
}

export interface SpawnWithTimeoutOptions {
	timeoutMs?: number;
	signal?: AbortSignal;
	/** Payload piped on the child's stdin and then closed (never argv). */
	stdin?: string;
}

/** Cap on captured child output so a runaway child cannot exhaust memory. */
const MAX_CHILD_OUTPUT_BYTES = 1_048_576;

/**
 * Spawn `argv` (no shell) and race it against a hard wall-clock timeout.
 *
 * `timedOut:true` means the child was killed after `timeoutMs`. The promise
 * settles on `close` (stdio drained); a killed child that never emits `close`
 * is force-resolved after a short grace so a tool call can never hang.
 */
export function spawnWithTimeout(argv: string[], options: SpawnWithTimeoutOptions = {}): Promise<RawDecideResult> {
	const timeoutMs = options.timeoutMs ?? ASK_DECISION_TIMEOUT_MS;
	return new Promise<RawDecideResult>((resolve) => {
		let settled = false;
		let stdout = "";
		let stderr = "";
		let timedOut = false;
		let spawnError: string | undefined;
		let wallTimer: NodeJS.Timeout | undefined;
		let graceTimer: NodeJS.Timeout | undefined;

		const finish = (status: number | null): void => {
			if (settled) return;
			settled = true;
			if (wallTimer !== undefined) clearTimeout(wallTimer);
			if (graceTimer !== undefined) clearTimeout(graceTimer);
			options.signal?.removeEventListener("abort", onAbort);
			const result: RawDecideResult = { status, stdout, stderr, timedOut };
			if (spawnError !== undefined) result.error = spawnError;
			resolve(result);
		};

		const append = (current: string, chunk: string): string => {
			if (Buffer.byteLength(current, "utf8") >= MAX_CHILD_OUTPUT_BYTES) return current;
			return current + chunk;
		};

		const child = spawn(argv[0], argv.slice(1), {
			windowsHide: true,
			stdio: [options.stdin === undefined ? "ignore" : "pipe", "pipe", "pipe"],
		});
		if (options.stdin !== undefined) {
			// The whole request rides stdin: no temp file, nothing on argv.
			child.stdin?.on("error", () => {
				// A child that exits before reading its stdin is not a spawn failure.
			});
			child.stdin?.end(options.stdin, "utf8");
		}

		const kill = (): void => {
			try {
				// SIGKILL maps to TerminateProcess on Windows; no grandchildren are
				// left behind by `mw decide run` (it is a single Python process).
				child.kill("SIGKILL");
			} catch {
				// Already gone — `close` will settle the promise.
			}
			// A process killed mid-write may hold stdio open; never hang the tool.
			graceTimer = setTimeout(() => finish(child.exitCode), 2_000);
		};
		const onAbort = (): void => {
			if (settled) return;
			spawnError = "aborted";
			kill();
		};

		child.stdout?.setEncoding("utf8");
		child.stderr?.setEncoding("utf8");
		child.stdout?.on("data", (chunk: string) => {
			stdout = append(stdout, chunk);
		});
		child.stderr?.on("data", (chunk: string) => {
			stderr = append(stderr, chunk);
		});
		child.on("error", (err: Error) => {
			spawnError = err.message;
			finish(null);
		});
		child.on("close", (code: number | null) => finish(code));

		if (options.signal !== undefined) {
			if (options.signal.aborted) onAbort();
			else options.signal.addEventListener("abort", onAbort, { once: true });
		}
		wallTimer = setTimeout(() => {
			if (settled) return;
			timedOut = true;
			kill();
		}, timeoutMs);
	});
}

export interface DecideRunRequest {
	projectDir: string;
	dp: string;
	/** Request JSON — piped on stdin (`viaStdin`) or written to a temp file. */
	input: string;
	timeoutMs: number;
	/** True for the four-dp material envelope: `{material, meta}` rides stdin
	 * under `mw decide run <dp> --stdin` (design §4.1). The legacy 21 dps keep
	 * the pre-existing `--request-file` + `{state}` path byte-identical. */
	viaStdin?: boolean;
	explicitEvidence?: boolean;
}

/** Injectable runner (tests replace this; production uses {@link runDecideMw}). */
export type DecideRunner = (request: DecideRunRequest, signal?: AbortSignal) => Promise<RawDecideResult>;

/** Build the `python -X utf8 mw.py decide run ...` argv.
 *
 * `viaStdin` (the four-dp envelope) carries routing only: the whole
 * `{material, meta}` payload rides stdin. The legacy path keeps riding a temp
 * `--request-file` (design D-003). The caller prepends {@link PYTHON_EXE}; this
 * list is platform-independent on purpose. */
export function buildDecideArgv(mwPy: string, request: DecideRunRequest, requestFile?: string): string[] {
	const routing = ["-X", "utf8", mwPy, "decide", "run", `--project=${request.projectDir}`, "--dp", request.dp];
	if (request.viaStdin === true) return [...routing, "--stdin", "--json"];
	return [...routing, "--request-file", requestFile ?? "", "--json"];
}

/** Write the request JSON to a private temp dir and return `{dir, file}`. */
function writeRequestFile(input: string): { dir: string; file: string } {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-decide-"));
	const file = path.join(dir, "request.json");
	fs.writeFileSync(file, input, { encoding: "utf8", mode: 0o600 });
	return { dir, file };
}

/**
 * The real child: reuse mw-runner's interpreter/path resolution. The four-dp
 * envelope is piped on stdin (`--stdin`); the legacy path writes the request to
 * a temp file and always cleans it up.
 */
export const runDecideMw: DecideRunner = async (request, signal) => {
	const refused = decisionIdRefusal(request.dp);
	if (refused || !request.viaStdin)
		return { status: 2, stdout: "", stderr: refused ?? "preparation required", timedOut: false };
	const mwPy = findMwPy();
	if (!mwPy) return { status: null, stdout: "", stderr: "", error: "mw.py not found", timedOut: false };
	if (request.explicitEvidence && !(await probeDecisionCapabilities(mwPy, signal)).explicitEvidence) {
		return unsupportedEvidenceReply();
	}
	if (request.viaStdin === true) {
		return spawnWithTimeout([PYTHON_EXE, ...buildDecideArgv(mwPy, request)], {
			timeoutMs: request.timeoutMs,
			signal,
			stdin: request.input,
		});
	}
	let files: { dir: string; file: string };
	try {
		files = writeRequestFile(request.input);
	} catch (err) {
		return {
			status: null,
			stdout: "",
			stderr: "",
			error: err instanceof Error ? err.message : String(err),
			timedOut: false,
		};
	}
	try {
		return await spawnWithTimeout([PYTHON_EXE, ...buildDecideArgv(mwPy, request, files.file)], {
			timeoutMs: request.timeoutMs,
			signal,
		});
	} finally {
		try {
			fs.rmSync(files.dir, { recursive: true, force: true });
		} catch {
			// Best effort: a leaked temp dir is not worth failing the tool call.
		}
	}
};

// ── Response mapping ────────────────────────────────────────────────────────

function asAnswers(value: unknown): AskDecisionAnswers | undefined {
	if (!isRecord(value)) return undefined;
	const answers: AskDecisionAnswers = {};
	for (const [qid, raw] of Object.entries(value)) {
		if (!isRecord(raw) || !("value" in raw)) continue;
		const entry: { value: unknown; confidence?: number | null } = { value: raw.value };
		if (typeof raw.confidence === "number" && Number.isFinite(raw.confidence)) entry.confidence = raw.confidence;
		answers[qid] = entry;
	}
	return Object.keys(answers).length > 0 ? answers : undefined;
}

/** Parse a child's stdout: the whole payload first, then each non-empty line
 * from the last one backwards (a child may print a diagnostic after its JSON
 * receipt). Never throws. */
export function parseDecisionJson(stdout: string): Record<string, unknown> | undefined {
	const trimmed = stdout.trim();
	const lines = trimmed.split("\n");
	const candidates = [trimmed, ...[...lines].reverse().map((line) => line.trim())];
	for (const text of candidates) {
		if (!text) continue;
		try {
			const parsed = JSON.parse(text) as unknown;
			if (isRecord(parsed)) return parsed;
		} catch {
			// Try the next candidate.
		}
	}
	return undefined;
}

/** The fixed no-guessing line appended to every unavailable payload.
 *  r2: a DP failure is matter-scoped, never an unconditional human wait for
 *  the whole PM. `decision_feedback` carries the concrete category/gaps; only
 *  a REAL host stop/authority/budget fact stops wider work. */
export function unavailableDirective(reason: string, dp: string): string {
	const common =
		`UNAVAILABLE(${reason}) — ${ASK_DECISION_GUESS_DIRECTIVE}，不要执行被门控的动作，` +
		`不要用别的工具绕过。上报 "blocked on decision ${dp}" 与本条 decision_feedback 的具体缺口；` +
		`同一事项同一事实不要重发（返回已有反馈），在现有权限/角色/写面内可继续其他独立合法工具；` +
		`只有真实用户停止、父取消、权限/预算或角色事实才停止更大范围工作。`;
	if (reason === "disabled") {
		return `${common} disabled ≠ approval：决策点未开启不等于放行，被门控的动作仍受其常规工具权限约束。`;
	}
	if (reason === "unconfigured" || reason === "signoff-disabled") {
		return `${common} 该结论来自真实配置读取，零 DP 网络；这不是服务故障，不要按故障重试或等待人工放行。`;
	}
	return common;
}

/** Terminal directive emitted once a dp hits the per-turn block cap. */
export function terminalDirective(dp: string, blocks: number): string {
	return (
		`TERMINAL: "${dp}" has been blocked ${blocks} time(s) in this turn. ${ASK_DECISION_GUESS_DIRECTIVE}。` +
		`停止重试，上报 "blocked on decision ${dp}" 并结束本轮（不要再次调用 ask_decision）。`
	);
}

// ── The one decision call ───────────────────────────────────────────────────

export interface AskDecisionInput {
	/** Durable logical identity supplied by a registered PM, never by tool parameters. */
	logicalId?: string;
	projectDir: string;
	dp: string;
	/** Audit label for the trace line only; the decision id comes from Python. */
	trigger: string;
	question?: string;
	note?: string;
	/** Owner key, carried as `key`/`task_key` in the LEGACY state when known. */
	taskKey?: string | null;
	/** Owning AgenticTask key of the local envelope (material path). */
	key?: string;
	/** The REAL task this decision belongs to; `null` for a task-less PM decision. */
	initiatorRole?: DecisionInitiatorRole;
	/** Business material of the selected active entry, verbatim. */
	material?: Record<string, unknown>;
	/** Local reference supplied by the host consuming a prepared follow-up. */
	parentDecisionRef?: string;
	preparation?: DecisionPreparation;
	context?: Record<string, unknown>;
	evidenceRefs?: DecisionEvidenceRef[];
	/** Points at the previous `logical_id` when this call retries another one. */
	retryOf?: string | null;
	taskBefore?: TaskStateSnapshot;
	/** Runner override (tests); the real async child when omitted. */
	runner?: DecideRunner;
	/** Feedback runner override (tests); the real `decide lifecycle` child when omitted. */
	lifecycleRunner?: LifecycleRunner;
	/** dp25 sign runner override (tests); the real `decide sign` child when omitted. */
	signRunner?: SignRunner;
	timeoutMs?: number;
	signal?: AbortSignal;
	/** Trusted host context minted by the registering window (real claim /
	 * worker task/run). A direct caller without a registered window gets an
	 * owner-absent `unknown` binding, never a fabricated PM claim. */
	hostContext?: DecisionHostContext;
	/** Real typed host stop/budget/authority facts (T06 connection point).
	 * T04A supplies none by default and never derives them from model text. */
	hostFacts?: HostFacts;
	/** Config-facts injection for isolated unit runs. Omitted production calls
	 * always use `readRealDecideConfigFacts` (the existing readers). */
	configReader?: DecideConfigReader;
}

function jsonText(payload: unknown): string {
	return JSON.stringify(payload);
}

export async function probeDecisionCapabilities(mwPy: string | null, signal?: AbortSignal) {
	if (!mwPy) return { explicitEvidence: false, inputDiagnostics: false };
	const raw = await spawnWithTimeout([PYTHON_EXE, "-X", "utf8", mwPy, "decide", "capabilities"], {
		timeoutMs: 5000,
		signal,
	});
	const reply = raw.status === 0 ? parseDecisionJson(raw.stdout) : undefined;
	return { explicitEvidence: reply?.evidence_refs === 1, inputDiagnostics: reply?.input_diagnostics === 1 };
}

function unsupportedEvidenceReply(): RawDecideResult {
	return {
		status: 2,
		stderr: "",
		timedOut: false,
		stdout: jsonText({
			available: false,
			reason: "input-incomplete",
			problems: ["input-incomplete: explicit evidence protocol unsupported"],
			input_diagnostics: {
				stage: "evidence-preparation",
				transport: "not-sent",
				truncated: false,
				issues: [{ field: "evidence_refs", code: "evidence-protocol-unsupported" }],
			},
		}),
	};
}

function unavailable(
	reason: string,
	dp: string,
	spawned: boolean,
	extra: {
		escalated_reason?: string;
		missing_fields?: string[];
		material_issues?: MaterialIssue[];
		material_ref_issues?: MaterialReferenceIssue[];
		observation?: DecisionFeedbackObservation;
		input_diagnostics?: DecisionInputDiagnostics;
		preparation_status?: AskDecisionUnavailable["preparation_status"];
		original_blocked_event_id?: string;
	} = {},
): AskDecisionOutcome {
	const payload: AskDecisionUnavailable = {
		available: false,
		unavailable: reason,
		action: ASK_DECISION_BLOCKED_ACTION,
	};
	if (extra.escalated_reason !== undefined) payload.escalated_reason = extra.escalated_reason;
	if (extra.missing_fields !== undefined && extra.missing_fields.length > 0) {
		payload.missing_fields = extra.missing_fields;
	}
	if (extra.material_issues?.length) payload.material_issues = extra.material_issues;
	if (extra.input_diagnostics) payload.input_diagnostics = extra.input_diagnostics;
	if (extra.preparation_status) payload.preparation_status = extra.preparation_status;
	if (extra.original_blocked_event_id) payload.original_blocked_event_id = extra.original_blocked_event_id;
	return {
		payload,
		text:
			`${jsonText(payload)}\n${unavailableDirective(reason, dp)}` +
			(extra.material_ref_issues?.length
				? `\nMATERIAL_REFS_DIAGNOSIS: ${jsonText(extra.material_ref_issues)}`
				: "") +
			(extra.input_diagnostics ? `\n${formatInputDiagnostics(extra.input_diagnostics)}` : ""),
		spawned,
		...(extra.observation === undefined ? {} : { observation: extra.observation }),
	};
}

/**
 * Ask one decision point. Never throws: every failure (unregistered dp, wrong
 * role, structurally incomplete material, missing mw.py, timeout, non-zero
 * exit, unparsable JSON, absent answer) returns the structured unavailable
 * payload plus the fixed directive.
 *
 * It performs no authorization check of its own beyond the ROLE surface
 * (a worker may not borrow the PM's dp2/dp25): `decide_for` owns
 * `enabled`/`mode`/`acted` (D-036) and this function only reports what the
 * child said.
 */
export async function runAskDecision(input: AskDecisionInput): Promise<AskDecisionOutcome> {
	const context = input.hostContext ?? fallbackHostContext(input);
	const outcome = await runAskDecisionCore(input);
	return attachDecisionFeedback(outcome, context);
}

/** Honest host context for a direct `runAskDecision` call: no live claim is
 *  known here, so owner/claim/run stay absent and the T01 classifier reports
 *  them as gaps. `hostFacts` (real host signals) can only come from the caller,
 *  never from model material. */
function fallbackHostContext(input: AskDecisionInput): DecisionHostContext {
	const binding = hostBinding({
		role: input.initiatorRole ?? "unknown",
		key: input.key,
		taskKey: input.taskKey,
	});
	return {
		binding,
		host: { ...(input.hostFacts ?? {}), binding },
		matterRef: decisionMatterRef({
			version: decisionMatterVersion(),
			owner: binding.owner ?? null,
			role: binding.role,
			key: binding.key ?? null,
			task_key: binding.task_key ?? null,
			run_id: binding.run_id ?? null,
			claim_id: binding.claim_id ?? null,
			dp: input.dp,
			question: input.question ?? null,
			note: input.note ?? null,
			material: input.material ?? null,
			...(input.evidenceRefs === undefined ? {} : { evidence_refs: input.evidenceRefs }),
			preparation: matterIdentityParts(input.preparation, ["prepared_at"]) ?? null,
			context: input.context ?? null,
			task_before: matterIdentityParts(input.taskBefore, ["observed_at"]) ?? null,
			parent_decision_ref: input.parentDecisionRef ?? null,
		}),
		origin: "ask_decision",
		stage: "public-ask",
	};
}

/** The one legal PM type handoff applies to ANY unavailable outcome of a real
 *  dp-w-type call — including a zero-network config refusal — through the SAME
 *  claim/role/material/preparation gate. No other dp, reason or identity gains
 *  dispatch authority, and no DP success is fabricated. */
function withPmTypeFallback(input: AskDecisionInput, outcome: AskDecisionOutcome): AskDecisionOutcome {
	// An untrusted SERVICE reply reason (missing/empty/non-string/unknown) was
	// folded into a frozen transport value. That value must never be handed to
	// the legacy PM type gate: the verbatim reply stays in decision_feedback for
	// diagnosis, but no dispatch authority is derived from it. Known reasons,
	// zero-network off/unconfigured facts and real host-observed transport
	// faults keep the existing gate.
	if (outcome.observation?.reasonFolded === true) return outcome;
	if (
		outcome.payload.available ||
		!canPmSelectType({
			projectDir: input.projectDir,
			dp: input.dp,
			key: input.key,
			role: input.initiatorRole ?? "unknown",
			reason: outcome.payload.unavailable,
			material: input.material,
			preparation: input.preparation,
			context: input.context,
		})
	)
		return outcome;
	outcome.payload.action = "pm-select-type";
	outcome.text = `${jsonText(outcome.payload)}\n${PM_TYPE_FALLBACK_DIRECTIVE}`;
	return outcome;
}

/** The decision call itself. Every return is classified once by the wrapper,
 *  with the verbatim pre-normalisation observation when one exists. */
async function runAskDecisionCore(input: AskDecisionInput): Promise<AskDecisionOutcome> {
	const started = Date.now();
	const dp = input.dp;
	// Zero-spawn refusal for an id the registry cannot resolve. The enum in the
	// tool schema already rejects it; `runAskDecision` is also called directly.
	const refusal = decisionIdRefusal(dp);
	if (refusal) return unavailable(refusal, dp, false);
	const role = input.initiatorRole ?? "unknown";
	// The originator is structural (the registering window), so a worker cannot
	// reach a PM decision point even by naming it (AC-006).
	if (!decisionActorAllowed(dp, role) || (DECIDE_REGISTRY[dp].roleScope === "worker" && !input.taskKey?.trim()))
		return unavailable(ASK_DECISION_REASON_ROLE_FORBIDDEN, dp, false);
	if (
		input.taskBefore !== undefined &&
		(!(input.taskKey ?? "").trim() || !isTaskStateSnapshot(input.taskBefore) || !isMaterialDp(dp))
	)
		return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, { missing_fields: ["meta.task_before"] });
	// r2 pre-transport facts: known single-DP off / transport off / unconfigured
	// / signoff=disable produce a real feedback with ZERO DP network. Production
	// (no runner override) always reads the real config readers; a unit run that
	// replaces the child with a fake runner SKIPS this preflight unless it also
	// injects config facts explicitly (never a fabricated zero-POST claim).
	const isolatedChild = input.runner !== undefined || input.signRunner !== undefined;
	const reader = input.configReader ?? (isolatedChild ? undefined : readRealDecideConfigFacts);
	if (reader !== undefined) {
		const facts = reader(dp, input.projectDir);
		const signoffExempt = dp === SIGN_KEY_ID && facts.signoffDisabled;
		const transportOff = facts.transport === "off" || facts.transport === "unconfigured";
		// An illegal declared mode is an explicit L3 force-off behind the same
		// reader: close the DP, never promote it to the default auto. An unknown
		// table/row keeps the reader-error contract (the child keeps its say).
		const modeInvalid = facts.mode === "invalid";
		if (signoffExempt || facts.dpDisabled || transportOff || modeInvalid) {
			const reason = signoffExempt
				? "signoff-disabled"
				: facts.dpDisabled || facts.transport === "off" || modeInvalid
					? "disabled"
					: "unconfigured";
			const observation: DecisionFeedbackObservation = {
				origin: "decide-config-reader",
				stage: "pre-transport",
				raw: {
					unavailable: reason,
					raw_reason: reason,
					disable_scope: facts.dpDisabled || modeInvalid ? dp : "transport",
					config_refs: facts.configRefs,
					mode: facts.mode,
				},
				evidenceRefs: facts.configRefs,
				...(signoffExempt
					? { exemption: { config_ref: ".mw/decide.json", kind: "signoff-disabled" } as ExemptionFact }
					: {}),
			};
			return withPmTypeFallback(input, unavailable(reason, dp, false, { observation }));
		}
	}
	// dp-sign-key is the ONE judgment that really signs (T05 `decide sign --stdin`): the
	// sign CLI calls the model itself and writes `sign-final.md` (or hands a
	// concrete next step back). Routing it through `decide run` would need a
	// second approval/sign step, which the approved design refuses.
	if (!isMaterialDp(dp)) return runLegacyAskDecision(input, dp, started);
	const meta = buildDecisionToolMeta({
		key: input.key ?? "",
		logicalId: input.logicalId,
		taskKey: input.taskKey,
		initiatorRole: role,
		retryOf: input.retryOf,
		taskBefore: input.taskBefore,
	});
	const prepared = prepareDecisionEnvelope(
		dp,
		input.material,
		meta,
		0,
		input.preparation,
		input.context,
		input.parentDecisionRef,
	);
	if (!prepared.ok) {
		const refusal = unavailable(prepared.reason, dp, false, {
			missing_fields: prepared.missing,
			material_issues: prepared.material_issues,
			material_ref_issues: prepared.material_ref_issues,
		});
		if (prepared.material_issues?.some((issue) => issue.allowed_choices)) {
			const preview = previewDecisionInput(dp, input.material, input.preparation, input.context, input.evidenceRefs);
			refusal.text += `\nLOCAL PREFLIGHT: ${jsonText(preview)}\nRepair and repeat preview=true before submitting.`;
		}
		return refusal;
	}
	const envelope: DecisionToolEnvelope =
		input.evidenceRefs === undefined
			? prepared.envelope
			: { ...prepared.envelope, evidence_refs: input.evidenceRefs };
	const outcome = await (dp === SIGN_KEY_ID
		? runSignoffAskDecision(input, dp, envelope, started)
		: runMaterialAskDecision(input, dp, envelope, started));
	return withPmTypeFallback(input, outcome);
}

/** Diagnostic for a locally refused call (no child ran). */
export function refusalOutcome(
	reason: string,
	dp: string,
	missing?: string[],
	materialRefIssues?: MaterialReferenceIssue[],
	materialIssues?: MaterialIssue[],
): AskDecisionOutcome {
	return unavailable(reason, dp, false, {
		missing_fields: missing,
		material_issues: materialIssues,
		material_ref_issues: materialRefIssues,
	});
}

/** Build one reason-specific diagnosis from the stable reason union. Worker
 *  and unknown-role recoveries are card/identity checks, never PM claim advice. */
export function claimDiagnosis(reason: ClaimDiagnosisReason): ClaimDiagnosis {
	return {
		reason,
		message: `${CLAIM_DIAGNOSIS_MESSAGE}${CLAIM_DIAGNOSIS_EXPLANATIONS[reason]}`,
		recovery: CLAIM_DIAGNOSIS_RECOVERIES[reason],
	};
}

/** Zero-spawn claim refusal. Built here (NOT through unavailable()) so the
 *  DEFAULT unavailable payload and the pm-select-type three-key payload stay
 *  byte-for-byte unchanged; only these two branches carry claim_diagnosis. The
 *  generic no-guessing directive is kept and the supplied diagnosis's own
 *  message/recovery are appended verbatim. */
export function claimRefusalOutcome(dp: string, diagnosis: ClaimDiagnosis): AskDecisionOutcome {
	const reason = ASK_DECISION_REASON_INPUT_INCOMPLETE;
	const payload: AskDecisionUnavailable = {
		available: false,
		unavailable: reason,
		action: ASK_DECISION_BLOCKED_ACTION,
		claim_diagnosis: diagnosis,
	};
	return {
		payload,
		text:
			`${jsonText(payload)}\n${unavailableDirective(reason, dp)}\n` + `${diagnosis.message}\n${diagnosis.recovery}`,
		spawned: false,
	};
}

interface ChildCallFailure {
	ok: false;
	outcome: AskDecisionOutcome;
}

/** Spawn one decision child and parse its payload; every failure is DATA. */
async function callDecideChild(
	dp: string,
	request: DecideRunRequest,
	runner: DecideRunner,
	signal: AbortSignal | undefined,
): Promise<
	{ ok: true; response: Record<string, unknown>; observation: DecisionFeedbackObservation } | ChildCallFailure
> {
	// The verbatim child fact is captured HERE, before any frozen-reason
	// normalisation. It is the only raw the T01 classifier ever sees.
	const childFact = (stage: string, rawValue: unknown): DecisionFeedbackObservation => ({
		origin: "mw-decide-run",
		stage,
		raw: rawValue,
	});
	let raw: RawDecideResult;
	try {
		raw = await runner(request, signal);
	} catch {
		return {
			ok: false,
			outcome: unavailable("upstream-error", dp, true, {
				observation: childFact("runner-threw", {
					unavailable: "upstream-error",
					raw_reason: "runner-threw",
				}),
			}),
		};
	}
	if (raw.timedOut)
		return {
			ok: false,
			outcome: unavailable("timeout", dp, true, {
				observation: childFact("child-timeout", { unavailable: "timeout", raw_reason: "timeout" }),
			}),
		};
	if (raw.error !== undefined)
		return {
			ok: false,
			outcome: unavailable("upstream-error", dp, true, {
				observation: childFact("spawn-error", {
					unavailable: "upstream-error",
					raw_reason: raw.error,
				}),
			}),
		};
	const response = parseDecisionJson(raw.stdout);
	if (raw.status !== 0 && response?.available !== false)
		return {
			ok: false,
			outcome: unavailable("upstream-error", dp, true, {
				observation: childFact("child-exit", {
					unavailable: "upstream-error",
					raw_reason: raw.stdout.trim() === "" ? `exit=${String(raw.status)}` : raw.stdout,
				}),
			}),
		};
	if (response === undefined)
		return {
			ok: false,
			outcome: unavailable("bad-response", dp, true, {
				observation: childFact("unparsable-reply", {
					unavailable: "bad-response",
					raw_reason: raw.stdout,
				}),
			}),
		};
	const { input_diagnostics: rawInputDiagnostics, ...serviceReply } = response;
	const inputDiagnostics = readInputDiagnostics(rawInputDiagnostics);
	if (response.available === true && response.low_confidence === true) {
		return {
			ok: false,
			outcome: unavailable("low-confidence", dp, true, {
				observation: childFact("service-reply", serviceReply),
				input_diagnostics: inputDiagnostics,
			}),
		};
	}
	if (response.available !== true) {
		const rawReason = response.reason;
		const knownReason =
			typeof rawReason === "string" && ASK_DECISION_PYTHON_REASONS.has(rawReason) ? rawReason : undefined;
		const reason = knownReason ?? "upstream-error";
		// A missing, empty, non-string or unknown reason is an UNTRUSTED service
		// reply, not a known transport failure. Normalising it for the frozen
		// payload must not become a legacy PM type-handoff license.
		const folded = knownReason === undefined;
		// The child's own 7-value escalation verdict travels beside (never instead
		// of) the frozen legacy reason (D-021 / D-030).
		const escalated =
			typeof response.escalated_reason === "string" && response.escalated_reason !== ""
				? response.escalated_reason
				: undefined;
		const observation = childFact("service-reply", {
			...serviceReply,
			...(inputDiagnostics === undefined ? {} : { input_diagnostics: inputDiagnostics }),
			// Classification key is the VERBATIM reason, so an unknown or
			// malformed reason stays diagnostic instead of being folded into a
			// known service fault; the tool payload keeps the frozen reason.
			...(rawReason === undefined ? {} : { unavailable: rawReason, raw_reason: rawReason }),
		});
		if (folded) observation.reasonFolded = true;
		return {
			ok: false,
			outcome: unavailable(reason, dp, true, {
				escalated_reason: escalated,
				input_diagnostics: inputDiagnostics,
				preparation_status:
					response.preparation_status === "needs-evidence" ||
					response.preparation_status === "equivalent" ||
					response.preparation_status === "needs-review"
						? response.preparation_status
						: undefined,
				original_blocked_event_id:
					typeof response.original_blocked_event_id === "string" &&
					/^[0-9a-f-]{36}$/.test(response.original_blocked_event_id)
						? response.original_blocked_event_id
						: undefined,
				observation,
			}),
		};
	}
	return {
		ok: true,
		response,
		observation: childFact("service-reply", { ...serviceReply, available: true }),
	};
}

/** Submit the prepared envelope and correlate its selected rationale.
 *
 * Order (design §2/§4.1): validate the material against the generated registry,
 * build the local envelope (the registered PM reuses its same-matter ID), refuse an
 * over-budget material instead of truncating it, send, then resolve the native
 * selection back to the candidate the asker wrote and record `consumed`
 * through the single Python lifecycle writer. Nothing here executes business
 * work or writes a sign-off.
 */
async function runMaterialAskDecision(
	input: AskDecisionInput,
	dp: string,
	envelope: DecisionToolEnvelope,
	started: number,
): Promise<AskDecisionOutcome> {
	const { material, preparation, meta } = envelope;
	const request: DecideRunRequest = {
		projectDir: input.projectDir,
		dp,
		input: JSON.stringify(envelope),
		timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
		viaStdin: true,
		...(envelope.evidence_refs === undefined ? {} : { explicitEvidence: true }),
	};
	const called = await callDecideChild(dp, request, input.runner ?? runDecideMw, input.signal);
	if (!called.ok) return called.outcome;
	const response = called.response;
	// Each LOCAL business-validation refusal keeps the child's verbatim service
	// observation (raw JSON + mw-decide-run/service-reply origin) for feedback;
	// attachDecisionFeedback classifies the bad-response fact, never the reply.
	const refused = (): AskDecisionOutcome => unavailable("bad-response", dp, true, { observation: called.observation });
	// Only framework-prepared dependency metadata can prove file freshness.
	// An explicit empty array means this request did not cite file evidence.
	if (parseFileEvidence(response) === null || parseFileEvidence(response) === undefined) return refused();

	if (
		response.decision_id !== `${dp}:${meta.logical_id}` ||
		(response.dp !== undefined && response.dp !== dp) ||
		(response.logical_id !== undefined && response.logical_id !== meta.logical_id)
	)
		return refused();
	const answers = asAnswers(response.answers);
	if (answers === undefined) return refused();
	// The four authority keys are the child's verdict, taken verbatim (D-036).
	const decisionId = typeof response.decision_id === "string" ? response.decision_id : "";
	const mode = response.mode;
	const acted = response.acted;
	if (decisionId === "" || (mode !== "auto" && mode !== "suggest") || acted !== false) {
		return refused();
	}
	const selection = buildSelection(dp, answers, material);
	const basis = selectedDecisionBasis(dp, material, preparation, selection?.id, answers.basis_id?.value);
	if (selection === undefined || basis === undefined) {
		// A mismatched business answer or basis is never
		// mapped onto a candidate: that would invent the receipt (AC-006).
		return refused();
	}
	const latency = typeof response.latency_ms === "number" ? response.latency_ms : Date.now() - started;
	const payload: AskDecisionAvailable = {
		available: true,
		decision_id: decisionId,
		mode,
		acted,
		answers,
		confidence_source:
			typeof response.confidence_source === "string" && response.confidence_source !== ""
				? response.confidence_source
				: "unknown",
		latency_ms: latency,
		selection,
		basis,
	};
	// The asker really received the selection => `consumed` is a fact, not a
	// completion. `executed`/`settled` stay with the explicit receipt op.
	payload.feedback = await writeDecisionLifecycle(
		input.projectDir,
		{
			meta,
			decision_id: decisionId,
			dp,
			stage: "consumed",
			event_id: `consumed-${meta.logical_id}`,
			answer: selection.id,
		},
		input.lifecycleRunner ?? runLifecycleMw,
	);
	return { payload, text: jsonText(payload), spawned: true, meta, observation: called.observation };
}

/** The dp-sign-key path: ONE judgment, the CLI signs or hands over.
 *
 * The child is `mw decide sign <key> --stdin --json` (never `decide run` + a
 * second `sign` call). It records the creation fact, asks
 * `dp-sign-key` ONCE, persists the result record, and:
 * - `finalize` → writes/validates `evidence/review/sign-final.md` and records
 *   its own consumed + signoff lifecycle facts;
 * - `continue`/`user-confirm` → zero sign-off writes, one executed fact and a
 *   concrete `handoff` for the PM/user.
 * This function only maps that receipt; it never signs, approves twice or
 * invents a mode/role verdict of its own.
 */
async function runSignoffAskDecision(
	input: AskDecisionInput,
	dp: string,
	envelope: DecisionToolEnvelope,
	started: number,
): Promise<AskDecisionOutcome> {
	const { material, preparation, meta } = envelope;
	let raw: RawDecideResult;
	try {
		raw = await (input.signRunner ?? runSignMw)({
			projectDir: input.projectDir,
			key: meta.key,
			input: JSON.stringify(envelope),
			timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
			...(envelope.evidence_refs === undefined ? {} : { explicitEvidence: true }),
		});
	} catch {
		return unavailable("upstream-error", dp, true);
	}
	if (raw.timedOut) return unavailable("timeout", dp, true);
	if (raw.error !== undefined) return unavailable("upstream-error", dp, true);
	const receipt = parseDecisionJson(raw.stdout);
	if (receipt === undefined) return unavailable("bad-response", dp, true);
	const { input_diagnostics: rawInputDiagnostics, ...signReply } = receipt;
	const inputDiagnostics = readInputDiagnostics(rawInputDiagnostics);
	const receiptObservation: DecisionFeedbackObservation = {
		origin: "mw-decide-sign",
		stage: "sign-receipt",
		raw: { ...signReply, ...(inputDiagnostics === undefined ? {} : { input_diagnostics: inputDiagnostics }) },
	};
	const receiptEvidence = parseFileEvidence(receipt);
	if (receiptEvidence === null || (raw.status === 0 && receiptEvidence === undefined)) {
		return unavailable("bad-response", dp, true, { observation: receiptObservation });
	}
	const conclusion = typeof receipt.conclusion === "string" ? receipt.conclusion : "";
	const rawStatus = typeof receipt.signoff_status === "string" ? receipt.signoff_status : "";
	const signoffStatus: DecisionSignoffResult["status"] =
		rawStatus === "written" ||
		rawStatus === "existing" ||
		rawStatus === "not-required" ||
		rawStatus === "invalid-existing" ||
		rawStatus === "disabled"
			? rawStatus
			: "failed";
	const problems = Array.isArray(receipt.problems)
		? receipt.problems.filter((item): item is string => typeof item === "string")
		: [];
	if (raw.status !== 0 || !DECISION_SIGNOFF_CONCLUSIONS.includes(conclusion) || signoffStatus === "failed") {
		// No fabricated success: the CLI's own problems are its stderr/receipt
		// channel. When the CLI refused the material itself (budget/shape), its
		// vocabulary is reported verbatim instead of a bare `upstream-error`, so a
		// caller can tell an over-budget refusal from a transport failure.
		const refusedOversize = problems.some((item) => item.includes(ASK_DECISION_REASON_INPUT_OVERSIZE));
		const refusedIncomplete = problems.some((item) => item.includes(ASK_DECISION_REASON_INPUT_INCOMPLETE));
		if (refusedOversize) {
			return unavailable(ASK_DECISION_REASON_INPUT_OVERSIZE, dp, true, {
				escalated_reason: ASK_DECISION_REASON_INPUT_OVERSIZE,
				input_diagnostics: inputDiagnostics,
				observation: receiptObservation,
			});
		}
		if (refusedIncomplete) {
			return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, true, {
				escalated_reason: ASK_DECISION_REASON_INPUT_INCOMPLETE,
				preparation_status: receipt.preparation_status === "needs-review" ? "needs-review" : undefined,
				input_diagnostics: inputDiagnostics,
				observation: receiptObservation,
			});
		}
		return unavailable("upstream-error", dp, true, {
			input_diagnostics: inputDiagnostics,
			observation: receiptObservation,
		});
	}
	const decisionId = typeof receipt.decision_id === "string" ? receipt.decision_id : "";
	const basis = selectedDecisionBasis(dp, material, preparation, conclusion, receipt.basis_id);
	if (
		!basis ||
		receipt.dp !== dp ||
		receipt.logical_id !== meta.logical_id ||
		receipt.key !== meta.key ||
		decisionId !== `${dp}:${meta.logical_id}` ||
		receipt.second_approval !== 0 ||
		(conclusion === "finalize" ? !["written", "existing"].includes(signoffStatus) : signoffStatus !== "not-required")
	)
		return unavailable("bad-response", dp, true, { observation: receiptObservation });
	const signoff: DecisionSignoffResult = {
		status: signoffStatus,
		second_approval: typeof receipt.second_approval === "number" ? receipt.second_approval : 0,
	};
	if (typeof receipt.signoff_path === "string" && receipt.signoff_path !== "") {
		signoff.path = receipt.signoff_path;
	}
	if (typeof receipt.record_status === "string") signoff.record_status = receipt.record_status;
	if (typeof receipt.model_called === "boolean") signoff.model_called = receipt.model_called;
	if (typeof receipt.feedback_status === "string") signoff.feedback_status = receipt.feedback_status;
	if (Array.isArray(receipt.feedback_stages)) {
		signoff.feedback_stages = receipt.feedback_stages.filter(
			(item): item is { stage?: string | null; status?: string | null; event_id?: string | null } => isRecord(item),
		);
	}
	if (problems.length > 0) signoff.problems = problems;
	if (isRecord(receipt.handoff)) {
		const handoff = receipt.handoff;
		signoff.handoff = {
			owner: typeof handoff.owner === "string" ? handoff.owner : undefined,
			kind: typeof handoff.kind === "string" ? handoff.kind : undefined,
			signoff_writes: typeof handoff.signoff_writes === "number" ? handoff.signoff_writes : undefined,
			instruction: typeof handoff.instruction === "string" ? handoff.instruction : undefined,
		};
	}
	const acted = signoffStatus === "written" || signoffStatus === "existing";
	const payload: AskDecisionAvailable = {
		available: true,
		decision_id: decisionId,
		// `decide sign` exposes no execution mode: reporting one would be a local
		// verdict the authority never gave (mode is optional on purpose).
		acted,
		answers: { [DECIDE_REGISTRY[dp].businessQuestionId]: { value: conclusion }, basis_id: { value: basis.id } },
		basis,
		// The sign receipt does not echo confidence provenance; the persisted
		// result record is the authority for it. `unknown` never gates anything.
		confidence_source: "unknown",
		latency_ms: Date.now() - started,
		selection: { question: "q-conclusion", id: conclusion },
		signoff,
	};
	return {
		payload,
		text: jsonText(payload),
		spawned: true,
		meta,
		observation: {
			origin: "mw-decide-sign",
			stage: "sign-receipt",
			raw: { ...receipt, available: true, decision_id: decisionId, answers: payload.answers },
		},
	};
}

/** The legacy L0/L1 path of the other 21 dps (unchanged behaviour). */
async function runLegacyAskDecision(input: AskDecisionInput, dp: string, started: number): Promise<AskDecisionOutcome> {
	const state = buildDecisionState({ dp, note: input.note, taskKey: input.taskKey });
	// `decide_for` step 5 refuses a state that misses a registry-required field,
	// so report the field names (L0) instead of spending a round trip that can
	// only come back `input-incomplete`/`bad-response` (MAJOR-2).
	const missing = missingDecisionStateFields(dp, state);
	if (missing.length > 0) {
		return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, false, { missing_fields: missing });
	}
	if (canonicalStateBytes(state) > ASK_DECISION_MAX_STATE_BYTES) {
		return unavailable(ASK_DECISION_REASON_INPUT_OVERSIZE, dp, false);
	}
	const request: DecideRunRequest = {
		projectDir: input.projectDir,
		dp,
		input: buildDecisionRequestJson(state),
		timeoutMs: input.timeoutMs ?? ASK_DECISION_TIMEOUT_MS,
	};
	const called = await callDecideChild(dp, request, input.runner ?? runDecideMw, input.signal);
	if (!called.ok) return called.outcome;
	const response = called.response;
	const latency = typeof response.latency_ms === "number" ? response.latency_ms : Date.now() - started;

	let answers = asAnswers(response.answers);
	if (answers === undefined) return unavailable("bad-response", dp, true);
	if (input.question !== undefined) {
		const picked = answers[input.question];
		if (picked === undefined) return unavailable(ASK_DECISION_REASON_INPUT_INCOMPLETE, dp, true);
		answers = { [input.question]: picked };
	}

	// The four authority keys are the child's verdict, taken verbatim (D-036 /
	// D-041): no local id concatenation, no `mode` mirror, no `acted` derived
	// from `mode` (an `intent="answer"` decision is archived `acted=false`).
	const decisionId = typeof response.decision_id === "string" ? response.decision_id : "";
	const mode = response.mode;
	const acted = response.acted;
	if (decisionId === "" || (mode !== "auto" && mode !== "suggest") || typeof acted !== "boolean") {
		return unavailable("bad-response", dp, true);
	}

	const payload: AskDecisionAvailable = {
		available: true,
		decision_id: decisionId,
		mode,
		acted,
		answers,
		confidence_source:
			typeof response.confidence_source === "string" && response.confidence_source !== ""
				? response.confidence_source
				: "unknown",
		latency_ms: latency,
	};
	return { payload, text: jsonText(payload), spawned: true, observation: called.observation };
}

// ── Anti-retry counter ──────────────────────────────────────────────────────

export interface DecisionBlockCounter {
	/** Start a new turn: every per-dp count returns to zero. */
	reset(): void;
	/** Count one blocked attempt for `dp`; returns the new count. */
	recordBlock(dp: string): number;
	/** Drop the count for `dp` (a successful answer resolves the block). */
	clear(dp: string): void;
	countFor(dp: string): number;
}

/** Per-dp, per-turn block counter (design Q3 §3.3). One instance per worker
 * window; `turn_start` calls {@link DecisionBlockCounter.reset}. */
export function createDecisionBlockCounter(): DecisionBlockCounter {
	const counts = new Map<string, number>();
	return {
		reset: () => counts.clear(),
		recordBlock: (dp) => {
			const next = (counts.get(dp) ?? 0) + 1;
			counts.set(dp, next);
			return next;
		},
		clear: (dp) => {
			counts.delete(dp);
		},
		countFor: (dp) => counts.get(dp) ?? 0,
	};
}

// ── Registration ────────────────────────────────────────────────────────────

export interface AskDecisionToolOptions {
	/** Control workspace root (`.agenticdoc`'s parent). Defaults to the root
	 * derived from `PI_WORKER_TASK`, else `process.cwd()`. */
	projectDir?: string;
	/** Worker task.md path (`PI_WORKER_TASK`); anchors trace.log + the key. */
	taskPath?: string;
	/** Explicit trace.log path (tests). */
	tracePath?: string;
	/** The registering window's real role: `pm` in the PM branch, the worker's own
	 * card type in the worker branch. Defaults to the card's type, else
	 * `unknown` (never inferred as the PM). */
	initiatorRole?: DecisionInitiatorRole;
	/** Owning AgenticTask key when the window has no worker task path (PM). */
	key?: string;
	/** The REAL task this window works on (worker); `null`/absent for the PM. */
	taskKey?: string | null;
	/** Runner override (tests). */
	runner?: DecideRunner;
	/** Feedback runner override (tests). */
	lifecycleRunner?: LifecycleRunner;
	/** dp25 sign runner override (tests). */
	signRunner?: SignRunner;
	/** Timeout override (tests); production is {@link ASK_DECISION_TIMEOUT_MS}. */
	timeoutMs?: number;
	/** Config-facts injection for isolated unit runs. Production omits this and
	 * uses `readRealDecideConfigFacts` (existing real config readers). */
	configReader?: DecideConfigReader;
	/** Real trusted host stop/budget/authority facts (T06 connection point).
	 * T04A never supplies or invents one; model text never enters host facts. */
	hostFacts?: HostFacts;
	/** Host-only reader of the CURRENT admitted PM stage; absent for ordinary
	 * PM/worker windows. It is re-read at prepare AND submit revalidation. */
	stageSource?: () => DecisionStageIdentity | undefined;
	/** T04B: shared host offer/submit handle. When absent (all legacy callers)
	 * the ask result stays byte-for-byte unchanged and NO offer is prepared. */
	submitHandle?: SubmitDecisionHostHandle;
}

/** `ask_decision` details: frozen legacy payload + T04A feedback. T04B adds
 *  `submit_offer` as an INDEPENDENT field only when a handle is shared in; the
 *  first-line legacy payload never gains a field. */
export type AskDecisionToolDetails = AskDecisionPayload & {
	blocked_event_id?: string;
	gate_route?: ReturnType<typeof resolvePmGateRoute>;
	decision_feedback?: DecisionFeedback;
	matter_suppressed?: true;
	submit_offer?: SubmitOfferMetadata;
};

export interface AskDecisionToolHandle {
	projectDir: string;
	tracePath?: string;
	counter: DecisionBlockCounter;
}

function ownerKeyFromTaskPath(taskPath: string): string | undefined {
	// <control>/.agenticdoc/<key>/workers/<task>/task.md
	const key = path.basename(path.dirname(path.dirname(path.dirname(taskPath))));
	return key === "" || key === "." ? undefined : key;
}

/** The REAL task id of a worker card path (never "the latest task"). */
function workerTaskKeyFromTaskPath(taskPath: string): string | undefined {
	const task = path.basename(path.dirname(taskPath));
	return task === "" || task === "." || task === "workers" ? undefined : task;
}

function appendDecisionTrace(tracePath: string | undefined, line: string): void {
	if (tracePath === undefined) return;
	try {
		fs.mkdirSync(path.dirname(tracePath), { recursive: true });
		fs.appendFileSync(tracePath, `${line}\n`, "utf8");
	} catch {
		// Diagnostic append — a failure must never break the tool call.
	}
}

/** DP enum schema. A tuple cast keeps `Static` at the literal union — a plain
 * mapped array widens to `TSchema[]` and `Static` would collapse to `never`. */
type AskDecisionDpLiteral = TLiteral<AskDecisionDpId>;

const DP_ENUM_SCHEMA = Type.Union(
	ASK_DECISION_DP_IDS.map((id) => Type.Literal(id)) as [AskDecisionDpLiteral, ...AskDecisionDpLiteral[]],
	{ description: "Registered decision point id (unknown ids are rejected)" },
);

/** The material alternatives and their closed nested field sets are generated from the active registry. */
interface MaterialObjectSchema {
	type: "object";
	properties: Record<string, MaterialObjectSchema | Record<string, unknown>>;
	required: string[];
	additionalProperties: false;
}

const MATERIAL_SCHEMA = Type.Optional(
	Type.Unsafe<Record<string, unknown>>({
		anyOf: Object.entries(DECIDE_REGISTRY).map(([id, entry]) => {
			const schema: MaterialObjectSchema = {
				type: "object",
				properties: {},
				required: [],
				additionalProperties: false,
			};
			for (const field of [...entry.requiredStateFields, ...entry.optionalStateFields]) {
				const names = field.name.split(".");
				let parent = schema;
				for (const [index, name] of names.entries()) {
					if (entry.requiredStateFields.includes(field) && !parent.required.includes(name))
						parent.required.push(name);
					if (index === names.length - 1) {
						parent.properties[name] = {
							type: field.type,
							description: field.description,
							...(field.itemType ? { items: { type: field.itemType } } : {}),
							...(field.maxItems === undefined ? {} : { maxItems: field.maxItems }),
						};
					} else {
						const nested = parent.properties[name] ?? {
							type: "object",
							properties: {},
							required: [],
							additionalProperties: false,
						};
						parent.properties[name] = nested;
						parent = nested as MaterialObjectSchema;
					}
				}
			}
			return { ...schema, title: id };
		}),
		description:
			"Business material for the selected entry. Identity, preparation and optional context travel separately.",
	}),
);
const PREPARATION_SCHEMA = Type.Optional(
	Type.Object(
		{
			prepared_at: Type.String(),
			model_context: Type.Optional(
				Type.Object(
					{
						desc: Type.Array(Type.String(), {
							minItems: 1,
							maxItems: 10,
							description: "Brief sentences covering the goal, deviation, event and evidence or unknowns.",
						}),
						terminology: Type.Optional(Type.Record(Type.String(), Type.String())),
						enum_meanings: Type.Optional(Type.Record(Type.String(), Type.String())),
						references: Type.Optional(
							Type.Record(
								Type.String(),
								Type.Union([
									Type.Object({ kind: Type.String(), text: Type.String() }, { additionalProperties: false }),
									Type.Object(
										{
											kind: Type.String(),
											path: Type.String(),
											lines: Type.Optional(
												Type.Object({
													start: Type.Integer({ minimum: 1 }),
													end: Type.Integer({ minimum: 1 }),
												}),
											),
										},
										{ additionalProperties: false },
									),
								]),
							),
						),
						review: Type.Optional(
							Type.Record(
								Type.String(),
								Type.Object({
									status: Type.Union([Type.Literal("met"), Type.Literal("unmet"), Type.Literal("unverified")]),
									evidence: Type.String(),
								}),
							),
						),
						reasons: Type.Optional(Type.Record(Type.String(), Type.String())),
						auto_comparison: Type.Optional(
							Type.Object({
								budget: Type.Object({
									remaining_seconds: Type.Integer({ minimum: 1 }),
									reserve_seconds: Type.Integer({ minimum: 0 }),
								}),
								priority: Type.Optional(
									Type.Object({
										rule: Type.String(),
										source: Type.Union([
											Type.Literal("background.task_goal"),
											Type.Literal("background.constraints"),
										]),
									}),
								),
								paths: Type.Record(
									Type.String(),
									Type.Object({
										max_seconds: Type.Integer({ minimum: 1 }),
										observation: Type.String(),
										stop: Type.String(),
										successor: Type.String(),
										steps: Type.Array(
											Type.Object({
												id: Type.String(),
												max_seconds: Type.Integer({ minimum: 1 }),
												on_success: Type.Union([Type.String(), Type.Null()]),
												on_failure: Type.Union([Type.String(), Type.Null()]),
											}),
											{ minItems: 1, maxItems: 16 },
										),
									}),
								),
								pairs: Type.Array(
									Type.Object({
										candidates: Type.Tuple([Type.String(), Type.String()]),
										criterion: Type.String(),
										reversal: Type.String(),
									}),
								),
							}),
						),
					},
					{ additionalProperties: false },
				),
			),
			basis_catalog: Type.Array(
				Type.Object(
					{
						id: Type.String(),
						text: Type.String(),
						material_refs: Type.Array(Type.String(), {
							description:
								"Existing field paths in this request's material, without the material. prefix. " +
								"For dp-auto: background.current_state; for dp-QG: review_evidence or review_findings. " +
								"Not repository file path:line (e.g. src/example.ts:12); put file locations in evidence field values.",
						}),
						applies_to: Type.Array(Type.String()),
						finding_ids: Type.Optional(Type.Array(Type.String())),
						remaining_ids: Type.Optional(Type.Array(Type.String())),
					},
					{ additionalProperties: false },
				),
				{ minItems: 1 },
			),
		},
		{ additionalProperties: false },
	),
);

/** Tool parameter schema (exported so tests can assert the dp enum surface). */
export const ASK_DECISION_PARAMETERS = Type.Object(
	{
		dp: DP_ENUM_SCHEMA,
		preview: Type.Optional(
			Type.Boolean({
				description: "Inspect choices, reference paths and local input issues without requesting a decision.",
			}),
		),
		trigger: Type.String({
			minLength: 1,
			maxLength: 256,
			pattern: "^[^\\s:]+$",
			description:
				"Audit trigger label, e.g. <task_key> or <task_key>#ckpt3 (no ':' per D-023); " +
				"use the actual framework gate ID for a gate lookup or a route concerning that gate",
		}),
		question: Type.Optional(
			Type.String({
				minLength: 1,
				maxLength: 64,
				description: "Single registry question id; omit for the full question set",
			}),
		),
		note: Type.Optional(
			Type.String({
				maxLength: 800,
				description: "Short L0/L1 context summary (no secrets/absolute paths/code)",
			}),
		),
		material: MATERIAL_SCHEMA,
		preparation: PREPARATION_SCHEMA,
		evidence_refs: Type.Optional(
			Type.Array(
				Type.Object(
					{
						field: Type.String({ minLength: 1, maxLength: 160 }),
						path: Type.String({ minLength: 1, maxLength: 1024 }),
						lines: Type.Optional(
							Type.Object(
								{
									start: Type.Integer({ minimum: 1, maximum: 2147483647 }),
									end: Type.Integer({ minimum: 1, maximum: 2147483647 }),
								},
								{ additionalProperties: false },
							),
						),
					},
					{ additionalProperties: false },
				),
				{
					maxItems: 64,
					description:
						"Explicit existing evidence files and optional inclusive line ranges. Use [] for inline material only.",
				},
			),
		),
		context: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
		key: Type.Optional(
			Type.String({
				minLength: 1,
				maxLength: 64,
				description:
					"A key claimed by this PM window. Omit for its sole active key. Worker identity comes from its task card.",
			}),
		),
		task_before: Type.Optional(AGENT_TASK_STATE_SCHEMA),
		task_key: Type.Optional(
			Type.String({
				minLength: 1,
				maxLength: 64,
				description: "The REAL task this decision belongs to; omit when the decision has no task",
			}),
		),
	},
	{ additionalProperties: false },
);

/** Receipt parameters: the ONLY way `executed`/`settled` are ever recorded. */
export const DECISION_RECEIPT_PARAMETERS = Type.Object(
	{
		decision_id: Type.String({ minLength: 1, description: "The decision this receipt is about" }),
		stage: Type.Union([Type.Literal("executed"), Type.Literal("settled")], {
			description: "executed = the action really happened; settled = this round of handling finished",
		}),
		action: Type.Optional(
			Type.String({ description: "executed: one closed action label (pm-handoff/clarify/narrow/...)" }),
		),
		result: Type.Optional(Type.String({ description: "executed: what the result was based on" })),
		outcome: Type.Optional(
			Type.String({ description: "settled: one closed outcome (ok/rework/rollback/inconclusive/pending)" }),
		),
		reason: Type.Optional(Type.String({ description: "settled/executed: short free-text reason" })),
		event_id: Type.Optional(Type.String({ description: "Reuse the SAME id only when retrying this very write" })),
		task_after: Type.Optional(AGENT_TASK_STATE_SCHEMA),
	},
	{ additionalProperties: false },
);

/** Receipt tool details: the outcome of ONE receipt attempt. */
export interface DecisionReceiptDetails {
	decision_id: string;
	dp: string | null;
	stage: string;
	status: DecisionFeedbackResult["status"] | "refused";
	unavailable?: string;
	/** Same independent diagnosis on a LOCAL claim/key-binding receipt refusal. */
	claim_diagnosis?: ClaimDiagnosis;
}

/**
 * Register the shared decision tools (`ask_decision` + `decision_receipt`).
 *
 * The SAME entry serves both asking roles (design D002): the worker branch calls
 * it with the worker's own card role, the PM branch with `initiatorRole: "pm"`.
 * The role is structural, so a worker cannot reach a PM-only dp (dp2/dp25) even
 * by naming it, and no model parameter can claim to be the PM (AC-006/AC-010).
 *
 * Visibility: the tool is registered unconditionally and then appended to the
 * per-turn active set by a `before_agent_start` handler that runs AFTER the
 * worker's own handler (index.ts registers this module after
 * `workerModeActivate`), so the append wins over the role allowlist
 * recomputation. It never enters `TOOL_ALLOWLISTS` (T-17 Python parity lock).
 *
 * The process keeps one in-memory map of the decisions this window asked. The
 * receipt op resolves a `decision_id` against it, so `executed`/`settled` can
 * only ever be written for a decision this window really made (and with the
 * same `logical_id` meta).
 */
export function registerAskDecisionTool(pi: ExtensionAPI, options: AskDecisionToolOptions = {}): AskDecisionToolHandle {
	const taskPath = options.taskPath ?? process.env.PI_WORKER_TASK;
	const resolvedTaskPath = taskPath !== undefined && taskPath !== "" ? path.resolve(taskPath) : undefined;
	const projectDir =
		options.projectDir ??
		(resolvedTaskPath !== undefined ? controlRootFromTaskPath(resolvedTaskPath) : process.cwd());
	const tracePath =
		options.tracePath ??
		(resolvedTaskPath !== undefined ? path.join(path.dirname(resolvedTaskPath), "trace.log") : undefined);
	// The worker's owning key/task come from its own card path; the PM has no
	// task path, so it must pass its `key` (and a task only when it names one).
	const ownerKey = resolvedTaskPath !== undefined ? ownerKeyFromTaskPath(resolvedTaskPath) : options.key;
	const workerTaskKey =
		resolvedTaskPath !== undefined
			? (workerTaskKeyFromTaskPath(resolvedTaskPath) ?? null)
			: (options.taskKey ?? null);
	const initiatorRole = resolvedTaskPath
		? initiatorRoleFromWorkerTask(resolvedTaskPath)
		: (options.initiatorRole ?? "unknown");

	function boundKey(requested: string | undefined): BoundKeyResult {
		if (ownerKey !== undefined) {
			const matches = requested === undefined || requested.trim() === ownerKey;
			return matches ? { key: ownerKey } : { key: undefined, diagnosis: claimDiagnosis("worker-key-mismatch") };
		}
		if (initiatorRole !== "pm") return { key: undefined, diagnosis: claimDiagnosis("unknown-role") };
		const inspection = inspectPmClaim(projectDir, requested);
		// inspectPmClaim resolves a key only when the unique active row's claimId
		// exactly equals currentClaimId(); the frozen store likewise uses that live
		// row.claimId as owner. No unbound/foreign/ambiguous read reaches this branch.
		return inspection.key !== undefined
			? { key: inspection.key, owner: currentClaimId() }
			: { key: undefined, diagnosis: claimDiagnosis(inspection.reason) };
	}

	/** Host-only current stage. Re-derived on every prepare/revalidate: a lost
	 *  live claim, stale session or foreign key cannot keep an old stage offer. */
	function stageFor(key: string | undefined): DecisionStageIdentity | undefined {
		if (key === undefined || initiatorRole !== "pm") return undefined;
		const stage = options.stageSource?.();
		if (
			stage === undefined ||
			stage.key !== key ||
			stage.claimId !== currentClaimId() ||
			!stage.stageId.trim() ||
			!stage.scopeRef.trim() ||
			!stage.matterRef.trim() ||
			!/^[a-f0-9]{64}$/.test(stage.grantDigest)
		)
			return undefined;
		return stage;
	}

	const counter = createDecisionBlockCounter();
	/** The decisions this window asked (receipt lookup + the join meta). */
	const asked = new Map<string, { meta: DecisionToolMeta; dp: string }>();
	/** r2 matter-scoped replay cache. NOT reset on `turn_start`: the same real
	 * binding + substantive facts + dp/mode version is ONE matter forever in
	 * this window, so a new turn/trigger cannot buy another DP request. A
	 * changed material/preparation/context produces a new key (re-prepare).
	 * R1: a real config/policy or host fact change is rechecked before ANY
	 * replay; unchanged facts never buy a second runner. */
	interface MatterOutcome {
		payload: AskDecisionPayload;
		firstLine: string;
		directiveSuffix: string;
		details: AskDecisionToolDetails;
		feedback?: DecisionFeedback;
		observation?: DecisionFeedbackObservation;
		configSignature: string;
		hostSignature: string;
		fileEvidence?: FileEvidenceDependency[];
		fileEvidenceRefused?: true;
	}
	const matterOutcomes = new Map<string, MatterOutcome>();
	const fileRevisions = new Map<string, string>();
	const isolatedChild = options.runner !== undefined || options.signRunner !== undefined;
	const configFactsReader: DecideConfigReader | undefined =
		options.configReader ?? (isolatedChild ? undefined : readRealDecideConfigFacts);
	/** Only real reader facts enter the signature: no model text, no
	 *  self-reported version, no new turn and no invented budget can refresh
	 *  a cached verdict or its permission. */
	const currentConfigSignature = (dp: string): string =>
		stableJson({
			config: configFactsReader?.(dp, projectDir),
			// ONLY the trusted real reader's current per-dp mode/validity fact
			// enters invalidation: never a model parameter, a bare mtime, raw
			// config text, a new turn or an invented budget.
			mode: readDecideConfigFacts(dp, projectDir).mode,
			policy: resolveDecidePolicy(dp, projectDir),
			decide: readDecidePolicy(projectDir),
		});
	const currentHostSignature = (): string => {
		const { stop_signals, ...facts } = options.hostFacts ?? {};
		// A timeout ends the service request. It does not change the authority
		// or invalidate the already prepared local action.
		const authorityStops = stop_signals?.filter((signal) => signal.kind !== "service-timeout") ?? [];
		return stableJson(authorityStops.length === 0 ? facts : { ...facts, stop_signals: authorityStops });
	};
	/** Only TYPED host facts can be a real cancellation. Model material,
	 *  context, note or trigger strings are never read as stop facts. */
	const currentTrustedStop = (): StopSignal | undefined =>
		(options.hostFacts?.stop_signals ?? []).find(
			(signal) => signal.kind === "user-stop" || signal.kind === "parent-cancel",
		);

	function recordBlockedAttempt(
		dp: string,
		payload: AskDecisionPayload,
		feedback: DecisionFeedback | undefined,
		observation?: DecisionFeedbackObservation,
	): string | undefined {
		if (payload.available) return undefined;
		const raw = observation?.raw;
		const serviceId = isRecord(raw) ? raw.blocked_event_id : undefined;
		if (
			payload.matter_suppressed !== true &&
			(observation?.origin === "mw-decide-run" || observation?.origin === "mw-decide-sign") &&
			typeof serviceId === "string" &&
			/^[0-9a-f-]{36}$/.test(serviceId)
		) {
			return serviceId;
		}
		const eventId = randomUUID();
		const directory = path.join(projectDir, ".agenticdoc", "_autopilot", "dp-blocked");
		const temporary = path.join(directory, `.${eventId}.tmp`);
		const identifier = (value: unknown): string | undefined =>
			typeof value === "string" && /^[a-zA-Z0-9_.:[\]/-]{1,160}$/.test(value) && !/^sk-/i.test(value)
				? value
				: undefined;
		const fields = (payload.missing_fields ?? []).flatMap((field) => {
			const name = identifier(field);
			return name === undefined ? [] : [{ field: name, issue: "required or invalid" }];
		});
		for (const issue of payload.material_issues ?? []) {
			const name = identifier(issue.field);
			if (name !== undefined) fields.push({ field: name, issue: issue.code ?? "invalid" });
		}
		const event = {
			schema_version: 1,
			event_id: eventId,
			ts: new Date().toISOString(),
			source: "ask_decision",
			stage: payload.matter_suppressed === true ? "replay" : (feedback?.stage ?? "preflight"),
			dp: identifier(dp),
			key: identifier(feedback?.binding?.key ?? ownerKey),
			task_key: identifier(feedback?.binding?.task_key ?? workerTaskKey),
			logical_id: identifier(isRecord(raw) ? raw.logical_id : undefined),
			matter_ref: identifier(feedback?.matter_ref),
			feedback_ref: identifier(feedback?.feedback_ref),
			reason: payload.unavailable,
			escalated_reason: identifier(payload.escalated_reason),
			category: feedback?.category,
			detail: payload.claim_diagnosis?.reason,
			issues: fields.slice(0, 8),
			...(payload.input_diagnostics ? { input_diagnostics: payload.input_diagnostics } : {}),
			original_blocked_event_id: identifier(payload.original_blocked_event_id),
		};
		try {
			fs.mkdirSync(directory, { recursive: true });
			fs.writeFileSync(temporary, `${JSON.stringify(event)}\n`, { flag: "wx", flush: true });
			fs.renameSync(temporary, path.join(directory, `${eventId}.json`));
			return eventId;
		} catch {
			try {
				fs.rmSync(temporary, { force: true });
			} catch {
				// A failed receipt must not replace the actual decision result.
			}
			appendDecisionTrace(tracePath, `[DECISION_BLOCK_AUDIT_FAILED] ${event.ts} reason=${event.reason}`);
			return undefined;
		}
	}

	/** The registered tool's host-facing result: the legacy frozen payload
	 * PLUS the frozen T01 feedback. The first text line stays the exact legacy
	 * JSON (exact-key contracts / DP receipt join); the feedback is the second
	 * line and a sibling `details` field so the model and the host both see it. */
	function publicResult(
		dp: string,
		outcome: AskDecisionOutcome,
		offer?: SubmitOfferMetadata,
	): {
		content: Array<{ type: "text"; text: string }>;
		details: AskDecisionToolDetails;
	} {
		const blockedEventId = recordBlockedAttempt(dp, outcome.payload, outcome.decision_feedback, outcome.observation);
		const details: AskDecisionToolDetails = {
			...outcome.payload,
			...(outcome.decision_feedback === undefined ? {} : { decision_feedback: outcome.decision_feedback }),
			...(offer === undefined ? {} : { submit_offer: offer }),
			...(blockedEventId === undefined ? {} : { blocked_event_id: blockedEventId }),
		};
		const firstLine = jsonText(outcome.payload);
		const suffix = outcome.text.startsWith(firstLine) ? outcome.text.slice(firstLine.length) : "";
		const feedbackLine =
			outcome.decision_feedback === undefined
				? ""
				: `\n${jsonText({ decision_feedback: outcome.decision_feedback })}`;
		// T04B: offer metadata is an INDEPENDENT field/line, never folded into the
		// frozen first-line payload. Absent when no handle was shared in.
		const offerLine = offer === undefined ? "" : `\n${jsonText({ submit_offer: offer })}`;
		return {
			content: [{ type: "text", text: `${firstLine}${feedbackLine}${offerLine}${suffix}` }],
			details,
		};
	}

	/** T04B host offer junction. Runs ONLY when a submit handle was shared in;
	 *  it prepares an immutable host offer when the STRUCTURAL identity and the
	 *  complete business material/preparation/context are valid — independent of
	 *  available=true/answers/decision_id/consumed. Incomplete material yields
	 *  fillable gaps, never a fabricated offer. `revalidate` re-derives current
	 *  config/host/identity/stop facts from the SAME real readers at submit time,
	 *  so drift cannot buy a stale offer. No child raw is used as an authority. */
	function buildOffer(
		payload: AskDecisionPayload,
		feedback: DecisionFeedback | undefined,
		params: {
			dp: string;
			material?: Record<string, unknown>;
			preparation?: DecisionPreparation;
			context?: Record<string, unknown>;
		},
		hostContext: DecisionHostContext,
		boundKey: string,
		requestedTask: string | null,
		fileEvidence?: FileEvidenceDependency[],
	): SubmitOfferMetadata | undefined {
		if (options.submitHandle === undefined) return undefined;
		if (fileEvidence !== undefined && checkFileEvidence(fileEvidence).changed) {
			return { submittable: false, submit_tool: "submit_decision_handoff", gaps: ["file-evidence-changed"] };
		}
		const source = initiatorRole === "pm" ? "pm" : "worker-local";
		const identityOf = (ctx: DecisionHostContext): PrepareOfferInput["identity"] => ({
			source,
			key: ctx.binding.key ?? "",
			role: ctx.binding.role,
			...(ctx.binding.claim_id === undefined ? {} : { claimId: ctx.binding.claim_id }),
			...(ctx.binding.owner === undefined ? {} : { owner: ctx.binding.owner }),
			...(ctx.binding.task_key === undefined ? {} : { taskKey: ctx.binding.task_key }),
			...(ctx.binding.run_id === undefined ? {} : { runId: ctx.binding.run_id }),
			...(ctx.stageSource === undefined
				? {}
				: { stageId: ctx.stageSource.stageId, scopeRef: ctx.stageSource.scopeRef }),
		});
		const input: PrepareOfferInput = {
			dp: params.dp,
			identity: identityOf(hostContext),
			material: params.material,
			preparation: params.preparation,
			context: params.context,
			parentDecisionId: payload.available ? payload.decision_id : undefined,
			matterRef: hostContext.matterRef,
			...(hostContext.stageSource === undefined ? {} : { stageMatterRef: hostContext.stageSource.matterRef }),
			feedbackEffectUnknown: feedback?.effect_state === "unknown",
			revalidate: () => {
				const fresh = hostContextFor(
					params,
					boundKey,
					requestedTask,
					initiatorRole === "pm" ? hostContext.binding.owner : undefined,
				);
				return {
					configSignature:
						fileEvidence === undefined
							? currentConfigSignature(params.dp)
							: stableJson({
									config: currentConfigSignature(params.dp),
									file_evidence: checkFileEvidence(fileEvidence).revision,
								}),
					hostSignature: currentHostSignature(),
					identity: identityOf(fresh),
					trustedStop: currentTrustedStop() !== undefined,
					...(fresh.stageSource === undefined ? {} : { stageMatterRef: fresh.stageSource.matterRef }),
				};
			},
		};
		return options.submitHandle.prepareOffer(input).metadata;
	}

	/** Real host context for one execute: live PM claim or worker run.json,
	 * never a model-supplied owner/p0/stop. */
	function hostContextFor(
		params: {
			dp: string;
			question?: string;
			note?: string;
			material?: unknown;
			evidence_refs?: DecisionEvidenceRef[];
			preparation?: unknown;
			context?: unknown;
			task_before?: unknown;
		},
		key: string | undefined,
		taskKey: string | null,
		trustedPmOwner?: string,
	): DecisionHostContext {
		const runState = resolvedTaskPath !== undefined ? readRunState(path.dirname(resolvedTaskPath)) : undefined;
		const verifiedPmOwner =
			initiatorRole === "pm" && trustedPmOwner === currentClaimId() ? trustedPmOwner : undefined;
		const stage = stageFor(key);
		const binding = hostBinding({
			role: initiatorRole,
			...(key === undefined ? {} : { key }),
			taskKey: stage === undefined ? (taskKey ?? undefined) : stage.stageId,
			...(key !== undefined && initiatorRole === "pm" ? { claimId: currentClaimId() } : {}),
			...(runState === undefined ? {} : { owner: runState.owner_key, runId: runState.run_id }),
			...(verifiedPmOwner === undefined ? {} : { owner: verifiedPmOwner }),
		});
		// A live PM claim grants access to the key. The matter survives that
		// claim, while a worker's matter remains bound to its individual run.
		const pmMatter = verifiedPmOwner !== undefined && key !== undefined;
		return {
			binding,
			host: { ...(options.hostFacts ?? {}), binding },
			matterRef: decisionMatterRef({
				version: decisionMatterVersion(),
				...(pmMatter ? {} : { owner: binding.owner ?? null, claim_id: binding.claim_id ?? null }),
				role: binding.role,
				key: binding.key ?? null,
				task_key: binding.task_key ?? null,
				run_id: binding.run_id ?? null,
				...(stage === undefined ? {} : { stage_matter_ref: stage.matterRef }),
				dp: params.dp,
				question: params.question ?? null,
				note: params.note ?? null,
				material: params.material ?? null,
				...(params.evidence_refs === undefined ? {} : { evidence_refs: params.evidence_refs }),
				preparation: matterIdentityParts(params.preparation, ["prepared_at"]) ?? null,
				context: params.context ?? null,
				task_before: matterIdentityParts(params.task_before, ["observed_at"]) ?? null,
			}),
			origin: "registered-ask-decision",
			stage: "public-execute",
			...(stage === undefined ? {} : { stageSource: stage }),
		};
	}

	// One turn = one per-dp TRACE count window. It deliberately does NOT reset
	// `matterOutcomes`: the matter identity outlives turns and triggers.
	pi.on("turn_start", () => counter.reset());

	pi.registerTool<
		typeof ASK_DECISION_PARAMETERS,
		| AskDecisionToolDetails
		| ReturnType<typeof previewDecisionInput>
		| { available: false; gate_route: ReturnType<typeof resolvePmGateRoute> }
	>({
		name: ASK_DECISION_TOOL,
		label: ASK_DECISION_TOOL,
		description:
			"Ask the external decision service for a human-style ruling on a gated decision point. " +
			"Returns ONE line of JSON: {available, decision_id, mode, acted, answers, confidence_source, latency_ms}" +
			", plus {selection, feedback} on the prepared material path. A direct PM dp-gate-approve lookup returns gate_route only and never issues a decision. Every decision attempt carries decision_feedback " +
			"(frozen T01 classification with origin/stage/raw_reason/category/effect_state/stop_scope/gaps). " +
			"For dp-w-type, action=pm-select-type transfers type selection to the owning PM using the original card and prepared basis; continue through dispatch_worker. " +
			"For gate_route follow its instruction. Otherwise available=false is matter-scoped, NOT a global PM stop: the gated action stays blocked — do NOT guess, do NOT work around it — " +
			'report "blocked on decision <dp>" with the concrete decision_feedback gap; a same-matter repeat returns the existing feedback (matter_suppressed=true) with no new DP request, and independent legal tools may continue. ' +
			"Only a real host user-stop/parent-cancel/authority/budget/role/write-face fact stops wider work. " +
			"The failure line also carries escalated_reason; local material validation reports material_issues with exact rules/counts and missing_fields only for absent fields. A claim/key-binding refusal instead carries claim_diagnosis " +
			"(reason/message/recovery) with a reason-specific safe next step: worker/unknown-role diagnoses " +
			"do not advise PM claim/switch; it is a local identity check failure, NOT a missing MATERIAL field — " +
			"do NOT add meta.key to material, do NOT retry, preempt or re-claim, and do NOT write the index; " +
			"it is terminal for this round.",
		promptSnippet:
			"ask_decision(dp, trigger, material?, question?, note?) — ask the decision service before a gated action; " +
			"gate_route gives local applicability and the next step; action=pm-select-type means PM chooses the dispatch type; otherwise available=false blocks that matter only " +
			"(decision_feedback carries the concrete facts), never the whole PM.",
		promptGuidelines: [
			"Include evidence_refs in new decisions. Use [] for inline evidence, or list existing files with field, path and optional inclusive lines. Leave planned outputs in the task text. Use input_diagnostics to correct local preparation failures.",
			"Call ask_decision ONLY with a dp id from the enum and the trigger_id from your task context " +
				"(<task_key>, <task_key>#ckpt<N>, or the existing framework gate ID for a gate lookup); never invent a dp id, trigger or question id.",
			PM_TYPE_FALLBACK_DIRECTIVE,
			PM_GATE_ROUTING_RULE,
			'For decision failures other than action=pm-select-type, available=false closes THIS gated attempt only: report "blocked on decision <dp>" and the concrete ' +
				"decision_feedback gap, do not wait for a human as a general rule, and do not resend the same matter (a repeat returns matter_suppressed=true with zero DP traffic). " +
				"Two service failures never terminate the whole PM: continue other ready, independently legal tools within the existing claim/role/write-face.",
			"unavailable=input-incomplete reports material_issues for invalid material, including UTF-8 byte counts and declared limits; " +
				"missing_fields lists absent material fields or preparation/metadata problems, never a supplied invalid material value. " +
				"MATERIAL_REFS_DIAGNOSIS explains invalid references and lists allowed_fields in this request's material; " +
				"correct the named fields and retry once only after a substantive correction; " +
				"a missing field is never filled by inference. EXCEPT a claim_diagnosis refusal (a claim/key-binding " +
				"failure): meta.key is NOT a material field to add — never supplement material, retry, preempt or " +
				're-claim; report "blocked on decision <dp>" and stop, since available=false is terminal for this round.',
			"note is an L0/L1 summary (<=600 bytes): no credentials, no user quotes, no absolute paths, no code.",
			"mode=suggest only archives an advisory row; acted is the service's verdict and never your own " +
				"inference from the mode.",
			"Before submission, use preview=true on ask_decision. Correct local input issues and repeat preview before requesting a ruling. Preview never authorizes action or consumes an attempt.",
			...Object.values(DECISION_MATERIAL_PROMPTS),
			"For dp-QG include prepared criteria for pass, fix and reopen, supported by the current review material. Criteria describe when a branch applies. Keep concrete and unresolved findings separate. Run independent review of the applicable acceptance and verification criteria before asking.",
			"Prepare material, a separately timestamped basis_catalog, and model_context. Summarize the goal, deviation, event and evidence in desc. Define acronyms in terminology. " +
				"Define material codes in enum_meanings. Add named references with their text or an authorized file and inclusive line range. " +
				"For dp-QG and dp-sign-key, list the current AC/VC results in review. Define cited finding_ids and remaining_ids in reasons. " +
				"For dp-auto, state the existing allowance in background.constraints (for example, remaining 300 seconds), provide the budget and reserve, " +
				"a sourced priority, forward-only steps ending with null, and criterion and reversal evidence for every candidate pair. " +
				"Each item's material_refs is a non-empty array of existing field paths in this request's material, " +
				"without the material. prefix, not repository file path:line. For dp-auto use e.g. background.current_state; " +
				"for dp-QG use e.g. review_evidence or review_findings. Put file locations in the evidence field values. " +
				"Each item names its applicable choices. No preparation means this request is blocked; never invent evidence. An L0 note cannot substitute for pm_note.",
			"task_before is an optional local Agent report of this task BEFORE the decision, never model material. Use source=agent-report, an ISO timestamp with timezone, and null for unrecorded progress; do not substitute current state for past state or invent observations.",
			"Generated roleScope governs the entry. Only the current worker can ask dp-w-check-task; a worker is refused on PM entries and must report the block " +
				"instead of asking.",
			"After the selection: act only inside your existing authority, then call decision_receipt with the " +
				"action you really performed (executed) and, when this round is handled, settled. Never receipt what " +
				"did not happen; dp-sign-key uses the sign CLI (the sign-off writer is the CLI).",
			"dp-pm-steer handling: a narrow that changes the confirmed delivery goal still goes to the user; direct-exec " +
				"first coordinates the live worker's write surface; escalate asks the user a CONCRETE risk/authority " +
				"question. The model's choice alone never rewrites, terminates or splits a task.",
			"dp-sign-key branches: finalize is decided AND signed by the same `mw decide sign` call - the tool writes the sign-off file itself, so never ask the PM for a second approval or a second model call; continue and user-confirm write no sign-off and end with the concrete gaps to advance or the concrete items to confirm.",
		],
		parameters: ASK_DECISION_PARAMETERS,
		// Sequential: an ask changes gate state, so it must not race the tools
		// it authorizes (design Q1 §1.1).
		executionMode: "sequential",
		execute: async (_toolCallId, params, signal) => {
			// Local preflight refusals never run a child, but they are still real
			// public results: classify them with a real (possibly unbound) host
			// context so no result lacks frozen feedback.
			const refusedWithFeedback = (
				outcome: AskDecisionOutcome,
				context: DecisionHostContext,
				stage: string,
				claimReason?: string,
			): AskDecisionOutcome =>
				attachDecisionFeedback(outcome, context, {
					origin: claimReason === undefined ? "local-preflight" : "claim-binding",
					stage,
					raw: {
						unavailable: outcome.payload.available ? "" : outcome.payload.unavailable,
						raw_reason: outcome.payload.available ? "" : outcome.payload.unavailable,
						...(outcome.payload.available || outcome.payload.missing_fields === undefined
							? {}
							: { missing_fields: outcome.payload.missing_fields }),
						...(outcome.payload.available || outcome.payload.material_issues === undefined
							? {}
							: { material_issues: outcome.payload.material_issues }),
						...(claimReason === undefined ? {} : { claim_reason: claimReason }),
					},
				});
			if (Object.hasOwn(params, "parentDecisionRef") || Object.hasOwn(params, "parent_decision_ref")) {
				const refused = refusedWithFeedback(
					refusalOutcome("input-incomplete", params.dp, ["parent_decision_ref"]),
					hostContextFor(params, undefined, workerTaskKey),
					"parameter-check",
				);
				return publicResult(params.dp, refused);
			}
			const invalidDp = decisionIdRefusal(params.dp);
			if (invalidDp) {
				const refused = refusedWithFeedback(
					refusalOutcome(invalidDp, params.dp),
					hostContextFor(params, undefined, workerTaskKey),
					"registry-check",
				);
				return publicResult(params.dp, refused);
			}
			if (params.preview) {
				const preview = previewDecisionInput(
					params.dp,
					params.material,
					params.preparation,
					params.context,
					params.evidence_refs,
				);
				return { content: [{ type: "text", text: jsonText(preview) }], details: preview };
			}
			const bound = boundKey(params.key);
			if (bound.key === undefined) {
				// A window never decides under another key: the association must stay
				// exact instead of being rewritten by a model parameter (AC-010).
				// The reason is from the SAME single inspectPmClaim read as the gate.
				const refused = refusedWithFeedback(
					claimRefusalOutcome(params.dp, bound.diagnosis),
					hostContextFor(params, undefined, workerTaskKey),
					"identity-check",
					bound.diagnosis.reason,
				);
				appendDecisionTrace(
					tracePath,
					`[DECISION_UNAVAILABLE] ${new Date().toISOString()} dp=${params.dp} trigger=${params.trigger} ` +
						`reason=input-incomplete claim_reason=${bound.diagnosis.reason} count=1 max=` +
						`${ASK_DECISION_MAX_BLOCKED_PER_TURN} role=${initiatorRole}`,
				);
				return publicResult(params.dp, refused);
			}
			const stage = stageFor(bound.key);
			const requestedTask = stage === undefined ? (params.task_key ?? workerTaskKey ?? null) : stage.stageId;
			if (
				(workerTaskKey !== null && params.task_key !== undefined && params.task_key.trim() !== workerTaskKey) ||
				(stage !== undefined && params.task_key !== undefined && params.task_key !== stage.stageId)
			) {
				const refused = refusedWithFeedback(
					refusalOutcome("input-incomplete", params.dp, ["meta.task_key"]),
					hostContextFor(params, bound.key, requestedTask, bound.owner),
					"parameter-check",
				);
				return publicResult(params.dp, refused);
			}
			const baseHostContext = hostContextFor(params, bound.key, requestedTask, bound.owner);
			if (initiatorRole === "pm" && params.dp === "dp-gate-approve" && currentTrustedStop() === undefined) {
				const details = {
					available: false as const,
					gate_route: resolvePmGateRoute(projectDir, bound.key, params.trigger),
				};
				return { content: [{ type: "text", text: jsonText(details) }], details };
			}
			// A router selection (including a replay) can propose an entry, but its
			// cached decision must never stand in for today's gate queue.
			const withGateRoute = (result: ReturnType<typeof publicResult>) => {
				if (
					params.dp === "dp-route" &&
					result.details.available &&
					result.details.selection?.id === "dp-gate-approve"
				) {
					const gate_route = resolvePmGateRoute(projectDir, bound.key, params.trigger);
					result.details = { ...result.details, gate_route };
					result.content = [...result.content, { type: "text", text: jsonText({ gate_route }) }];
				}
				return result;
			};
			const baseMatterRef = baseHostContext.matterRef;
			const sourceRevision = fileRevisions.get(baseMatterRef);
			let hostContext =
				sourceRevision === undefined
					? baseHostContext
					: {
							...baseHostContext,
							matterRef: decisionMatterRef({ base: baseMatterRef, file_evidence_revision: sourceRevision }),
						};
			const configSignature = currentConfigSignature(params.dp);
			const hostSignature = currentHostSignature();
			const trustedStop = currentTrustedStop();
			// A current typed user-stop / parent-cancel is effective even on an
			// EMPTY cache: no first ask, config invalidation, material change or
			// new matter may buy a NEW DP runner call. Cached answers remain
			// zero-spawn replays; model strings never count as a stop fact and
			// no-stop config recovery still runs once.
			const cached = matterOutcomes.get(baseMatterRef);
			if (cached !== undefined && cached.configSignature !== configSignature) {
				// A REAL config/policy change is a new fact: never keep returning
				// an old disabled verdict. Only the readers can reach this branch.
				// A current trusted stop is NOT allowed to turn this invalidation
				// into a new request; the guard below returns a zero-spawn result.
				matterOutcomes.delete(baseMatterRef);
			}
			if (cached?.fileEvidence !== undefined) {
				// These paths came from Python's authorized source preparation,
				// never from a second parser over model-provided material. Check
				// aliases before hashing so a retargeted symlink cannot expand reads.
				const fileCheck = checkFileEvidence(cached.fileEvidence);
				if (fileCheck.changed) {
					fileRevisions.set(baseMatterRef, fileCheck.revision);
					hostContext = {
						...baseHostContext,
						matterRef: decisionMatterRef({ base: baseMatterRef, file_evidence_revision: fileCheck.revision }),
					};
					matterOutcomes.delete(baseMatterRef);
				}
			}
			const replay = matterOutcomes.get(baseMatterRef);
			if (replay !== undefined) {
				// The observation-time exclusions must not cancel real checks:
				// re-validate material, preparation (incl. prepared_at shape) and
				// task_before on every replay, with ZERO child traffic.
				const revalidated = prepareDecisionEnvelope(
					params.dp,
					params.material,
					buildDecisionToolMeta({
						key: bound.key,
						taskKey: requestedTask,
						initiatorRole,
						taskBefore: params.task_before,
					}),
					0,
					params.preparation,
					params.context,
				);
				if (!revalidated.ok) {
					const refused = refusedWithFeedback(
						refusalOutcome(
							revalidated.reason,
							params.dp,
							revalidated.missing,
							revalidated.material_ref_issues,
							revalidated.material_issues,
						),
						hostContext,
						"matter-recheck",
					);
					return publicResult(params.dp, refused);
				}
				// A REAL host stop/budget/authority change reclassifies the SAME
				// answer with its true scope; no new DP request is sent.
				let feedback = replay.feedback;
				if (replay.hostSignature !== hostSignature || trustedStop !== undefined) {
					const reclassified = attachDecisionFeedback(
						{
							payload: replay.payload,
							text: `${replay.firstLine}${replay.directiveSuffix}`,
							spawned: false,
							...(replay.observation === undefined ? {} : { observation: replay.observation }),
						},
						hostContext,
						replay.observation,
					);
					feedback = reclassified.decision_feedback;
					replay.feedback = feedback;
					replay.hostSignature = hostSignature;
				}
				const replayPayload = {
					...replay.payload,
					matter_suppressed: true as const,
					...(replay.payload.available || replay.details.blocked_event_id === undefined
						? {}
						: { original_blocked_event_id: replay.details.blocked_event_id }),
				};
				const feedbackLine = feedback === undefined ? "" : `\n${jsonText({ decision_feedback: feedback })}`;
				// T04B: a same-matter replay RE-PREPARES the host offer; the handle's
				// deterministic identity reuses the same offer_id (no new budget).
				const offer =
					replay.fileEvidenceRefused && options.submitHandle !== undefined
						? {
								submittable: false,
								submit_tool: "submit_decision_handoff" as const,
								gaps: ["file-evidence-metadata"],
							}
						: buildOffer(
								replay.payload,
								feedback,
								params,
								hostContext,
								bound.key,
								requestedTask,
								replay.fileEvidence,
							);
				const offerLine = offer === undefined ? "" : `\n${jsonText({ submit_offer: offer })}`;
				const blockedEventId = recordBlockedAttempt(params.dp, replayPayload, feedback, replay.observation);
				const replayDetails: AskDecisionToolDetails = {
					...replay.details,
					matter_suppressed: true,
					...(replayPayload.original_blocked_event_id === undefined
						? {}
						: { original_blocked_event_id: replayPayload.original_blocked_event_id }),
					...(feedback === undefined ? {} : { decision_feedback: feedback }),
					...(offer === undefined ? {} : { submit_offer: offer }),
					...(blockedEventId === undefined ? {} : { blocked_event_id: blockedEventId }),
				};
				appendDecisionTrace(
					tracePath,
					`[DECISION_MATTER_SUPPRESSED] ${new Date().toISOString()} dp=${params.dp} ` +
						`trigger=${params.trigger} matter=${hostContext.matterRef} role=${initiatorRole}`,
				);
				return withGateRoute({
					content: [
						{
							type: "text",
							text: `${jsonText(replayPayload)}${feedbackLine}${offerLine}${replay.directiveSuffix}`,
						},
					],
					details: replayDetails,
				});
			}
			if (trustedStop !== undefined) {
				// Current typed cancellation forbids any NEW DP request —
				// including a first-ever ask, config invalidation or a
				// substantive material change.
				// This is a local zero-spawn refusal with real host facts, never
				// a fabricated DP answer or a global PM termination.
				const stopped = unavailable("upstream-error", params.dp, false, {
					observation: {
						origin: "host-stop-guard",
						stage: "pre-transport",
						raw: {
							unavailable: "upstream-error",
							raw_reason: trustedStop.kind,
							stop_signal_ref: trustedStop.signal_ref,
						},
					},
				});
				return publicResult(params.dp, attachDecisionFeedback(stopped, hostContext));
			}
			const matter = hostContext.matterRef;
			const logicalId =
				!isolatedChild &&
				initiatorRole === "pm" &&
				params.dp !== "dp-sign-key" &&
				hostContext.binding.owner !== undefined &&
				hostContext.binding.owner === hostContext.binding.claim_id
					? `${matter.slice(0, 8)}-${matter.slice(8, 12)}-8${matter.slice(13, 16)}-8${matter.slice(17, 20)}-${matter.slice(20)}`
					: undefined;
			let outcome = await runAskDecision({
				projectDir,
				logicalId,
				dp: params.dp,
				trigger: params.trigger,
				question: params.question,
				note: params.note,
				material: params.material,
				preparation: params.preparation,
				evidenceRefs: params.evidence_refs,
				context: params.context,
				key: bound.key,
				taskKey: requestedTask,
				taskBefore: params.task_before,
				initiatorRole,
				runner: options.runner,
				lifecycleRunner: options.lifecycleRunner,
				signRunner: options.signRunner,
				timeoutMs: options.timeoutMs,
				signal,
				hostContext,
				configReader: options.configReader,
				hostFacts: options.hostFacts,
			});
			const childRaw = isRecord(outcome.observation?.raw) ? outcome.observation.raw : undefined;
			let fileEvidence = parseFileEvidence(childRaw);
			const metadataRefused = fileEvidence === null || (fileEvidence === undefined && childRaw?.available === true);
			if (metadataRefused) {
				outcome = attachDecisionFeedback(
					unavailable("bad-response", params.dp, outcome.spawned, {
						missing_fields: ["file_evidence"],
						observation: outcome.observation,
					}),
					hostContext,
				);
				// Cache the refusal without any file dependencies. Malformed
				// metadata authorizes no reads and never buys a same-fact retry.
				fileEvidence = [];
			}
			// T04B: prepare the host offer for THIS ask result (available OR not),
			// as an independent field; undefined leaves the legacy result intact.
			const offer =
				metadataRefused && options.submitHandle !== undefined
					? {
							submittable: false,
							submit_tool: "submit_decision_handoff" as const,
							gaps: ["file-evidence-metadata"],
						}
					: buildOffer(
							outcome.payload,
							outcome.decision_feedback,
							params,
							hostContext,
							bound.key,
							requestedTask,
							fileEvidence ?? undefined,
						);
			const publicOutcome = publicResult(params.dp, outcome, offer);
			const firstLine = jsonText(outcome.payload);
			const unresolvedSources =
				fileEvidence === undefined &&
				((typeof childRaw?.detail === "string" && childRaw.detail.includes("file evidence preparation failed")) ||
					(Array.isArray(childRaw?.problems) &&
						childRaw.problems.some(
							(item) => typeof item === "string" && item.includes("file evidence preparation failed"),
						)));
			// Malformed metadata replays only its stable refusal. A source refusal
			// from an older child without dependency metadata must be locally
			// prepared again rather than trapping a repaired missing file forever.
			if (!unresolvedSources)
				matterOutcomes.set(baseMatterRef, {
					payload: outcome.payload,
					firstLine,
					directiveSuffix: outcome.text.startsWith(firstLine) ? outcome.text.slice(firstLine.length) : "",
					details: publicOutcome.details,
					feedback: outcome.decision_feedback,
					observation: outcome.observation,
					configSignature,
					hostSignature,
					...(fileEvidence == null ? {} : { fileEvidence }),
					...(metadataRefused ? { fileEvidenceRefused: true as const } : {}),
				});
			const iso = new Date().toISOString();
			if (outcome.payload.available) {
				counter.clear(params.dp);
				if (isMaterialDp(params.dp) && outcome.meta !== undefined) {
					// Same decision, same logical_id: the receipt joins the consume row.
					asked.set(outcome.payload.decision_id, { meta: outcome.meta, dp: params.dp });
				}
				appendDecisionTrace(
					tracePath,
					`[DECISION] ${iso} dp=${params.dp} trigger=${params.trigger} ` +
						`decision_id=${outcome.payload.decision_id} mode=${outcome.payload.mode ?? "-"} ` +
						`acted=${String(outcome.payload.acted)} source=${outcome.payload.confidence_source} ` +
						`latency_ms=${outcome.payload.latency_ms} role=${initiatorRole}` +
						(outcome.payload.selection !== undefined ? ` selection=${outcome.payload.selection.id}` : "") +
						(outcome.payload.feedback !== undefined
							? ` feedback=${outcome.payload.feedback.stage}:${outcome.payload.feedback.status}`
							: ""),
				);
				return withGateRoute(publicOutcome);
			}

			const reason = outcome.payload.unavailable;
			const escalated =
				outcome.payload.escalated_reason !== undefined
					? ` escalated_reason=${outcome.payload.escalated_reason}`
					: "";
			const blocks = counter.recordBlock(params.dp);
			appendDecisionTrace(
				tracePath,
				`[DECISION_UNAVAILABLE] ${iso} dp=${params.dp} trigger=${params.trigger} reason=${reason}` +
					`${escalated} count=${blocks} max=${ASK_DECISION_MAX_BLOCKED_PER_TURN} role=${initiatorRole}`,
			);
			// r2: the old `terminate:true` after two failures is GONE. A repeated
			// matter is suppressed by `matterOutcomes` above and reported as a
			// concrete feedback/gap; independent legal tools remain callable.
			if (blocks >= ASK_DECISION_MAX_BLOCKED_PER_TURN) {
				appendDecisionTrace(
					tracePath,
					`[DECISION_MATTER_SUPPRESSED] ${iso} dp=${params.dp} trigger=${params.trigger} reason=${reason} ` +
						`count=${blocks} max=${ASK_DECISION_MAX_BLOCKED_PER_TURN} matter=${hostContext.matterRef} ` +
						`role=${initiatorRole}`,
				);
			}
			return publicOutcome;
		},
	});

	// The receipt op: `consumed` is automatic (the asker received the selection);
	// `executed`/`settled` are only ever recorded here, after the real action.
	pi.registerTool<typeof DECISION_RECEIPT_PARAMETERS, DecisionReceiptDetails>({
		name: DECISION_RECEIPT_TOOL,
		label: DECISION_RECEIPT_TOOL,
		description:
			"Record what really happened with a decision this window asked: executed (the action happened) " +
			"and settled (this round of handling finished). Returns ONE line of JSON " +
			"{stage, status, decision_id}; status=failed means the feedback ledger rejected the write — the " +
			"action itself is not undone. An unknown decision id or action is NOT recorded.",
		promptSnippet:
			"decision_receipt(decision_id, stage, action?, result?, outcome?, reason?) — record the real action/closure.",
		promptGuidelines: [
			"Call decision_receipt AFTER the action really happened, with the same decision_id the ask returned.",
			"executed needs one closed action: type-read, pm-handoff, clarify, narrow, split, direct-exec, " +
				"escalate, continue, user-confirm, record.",
			"settled needs one closed outcome: pending, ok, rework, rollback, inconclusive. settled is this round, " +
				"not the whole task.",
			"Never receipt an action you did not perform; a failed receipt is reported, not retried with a new action.",
			"task_after is an optional local Agent report AFTER the actual handling, for this decision's exact task. It does not execute work. Use source=agent-report and the actual observation time; missing progress is null, not guessed. Round ok is not task done.",
		],
		parameters: DECISION_RECEIPT_PARAMETERS,
		executionMode: "sequential",
		execute: async (_toolCallId, params) => {
			const refusal = (
				reason: string,
				dp: string | null,
				missing?: string[],
				claim?: ClaimDiagnosis,
			): { content: Array<{ type: "text"; text: string }>; details: DecisionReceiptDetails } => {
				const refused =
					claim !== undefined
						? claimRefusalOutcome(dp ?? "unknown", claim)
						: refusalOutcome(reason, dp ?? "unknown", missing);
				return {
					content: [{ type: "text", text: refused.text }],
					details: {
						decision_id: params.decision_id,
						dp,
						stage: params.stage,
						status: "refused",
						unavailable: reason,
						...(claim !== undefined ? { claim_diagnosis: claim } : {}),
					},
				};
			};
			const known = asked.get(params.decision_id);
			if (known === undefined) return refusal(ASK_DECISION_REASON_UNKNOWN_DECISION, null);
			const boundReceipt = boundKey(known.meta.key);
			if (boundReceipt.key !== known.meta.key) {
				// A valid binding can only equal the stored key; otherwise it is
				// undefined and carries the single-read diagnosis. The string case
				// is an unreachable defensive fallback, never a fabricated claim.
				const diagnosis: ClaimDiagnosis =
					boundReceipt.key === undefined ? boundReceipt.diagnosis : claimDiagnosis("worker-key-mismatch");
				return refusal(ASK_DECISION_REASON_INPUT_INCOMPLETE, known.dp, undefined, diagnosis);
			}
			if (
				params.task_after !== undefined &&
				(known.meta.task_key === null || !isTaskStateSnapshot(params.task_after))
			)
				return refusal(ASK_DECISION_REASON_INPUT_INCOMPLETE, known.dp);
			const eventId = params.event_id ?? randomUUID();
			let envelope: DecisionLifecycleEnvelope;
			if (params.stage === "executed") {
				const action = params.action ?? "";
				if (!DECISION_EXECUTED_ACTIONS.includes(action)) {
					// "未知动作只未记录": no row, no guessing at a nearby label.
					return refusal(ASK_DECISION_REASON_UNKNOWN_ACTION, known.dp);
				}
				envelope = {
					meta: known.meta,
					decision_id: params.decision_id,
					dp: known.dp,
					stage: "executed",
					event_id: eventId,
					action,
				};
				if (params.result !== undefined) envelope.result = params.result;
				if (params.reason !== undefined) envelope.reason = params.reason;
			} else {
				const outcome = params.outcome ?? "";
				if (!DECISION_OUTCOMES.includes(outcome)) {
					return refusal(ASK_DECISION_REASON_UNKNOWN_ACTION, known.dp);
				}
				envelope = {
					meta: known.meta,
					decision_id: params.decision_id,
					dp: known.dp,
					stage: "settled",
					event_id: eventId,
					outcome,
				};
				if (params.reason !== undefined) envelope.reason = params.reason;
			}
			if (params.task_after !== undefined) envelope.task_after = copyTaskState(params.task_after);
			const feedback = await writeDecisionLifecycle(projectDir, envelope, options.lifecycleRunner ?? runLifecycleMw);
			appendDecisionTrace(
				tracePath,
				`[DECISION_RECEIPT] ${new Date().toISOString()} dp=${known.dp} stage=${feedback.stage} ` +
					`status=${feedback.status} decision_id=${params.decision_id} role=${initiatorRole}`,
			);
			const details: DecisionReceiptDetails = {
				decision_id: params.decision_id,
				dp: known.dp,
				stage: feedback.stage,
				status: feedback.status,
			};
			return { content: [{ type: "text", text: JSON.stringify(details) }], details };
		},
	});

	// Active-set append (spec §5.3 / design Q5 §5.2): runs after the worker's
	// own before_agent_start recomputation, so every role sees the tools without
	// touching TOOL_ALLOWLISTS. Idempotent — a repeated append is a no-op.
	pi.on("before_agent_start", () => {
		const active = pi.getActiveTools();
		const missing = [ASK_DECISION_TOOL, DECISION_RECEIPT_TOOL].filter((name) => !active.includes(name));
		if (missing.length === 0) return;
		pi.setActiveTools([...active, ...missing]);
	});

	return { projectDir, tracePath, counter };
}
