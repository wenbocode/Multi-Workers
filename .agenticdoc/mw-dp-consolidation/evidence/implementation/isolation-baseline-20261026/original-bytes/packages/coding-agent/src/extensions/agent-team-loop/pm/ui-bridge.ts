import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Type } from "typebox";
import { VERSION } from "../../../config.ts";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../../core/extensions/types.ts";
import type { ModelRegistry } from "../../../core/model-registry.ts";
import { validateRagEnabled } from "../rag/tools.ts";
import type { AckStore } from "../shared/ack-store.ts";
import { runAgenticScript } from "../shared/agentic-scripts.ts";
import { cardDigest } from "../shared/card-digest.ts";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.ts";
import {
	CLAIM_GATE_DEFAULT,
	CLAIM_TYPES,
	type Claim,
	claimBudgetCaps,
	claimsGaps,
	ENVELOPE_HEADING_FAMILIES,
	ENVELOPE_SECTION_LABELS,
	type EnvelopeSection,
	parseClaimsBlock,
	readEnvelope,
	seedItemsMissing,
	typeExtrasMissing,
} from "../shared/dispatch-card.ts";
import {
	DISPATCHABLE_TYPES,
	detectImageNeed,
	modelImageCapability,
	readRoleModel,
	roleForTaskType,
	validateModelValue,
} from "../shared/dispatch-models.ts";
import { acquireLock } from "../shared/file-lock.ts";
import { formatHeartbeatAge, HEARTBEAT_STALE_MS, readTaskProgress } from "../shared/heartbeat.ts";
import {
	type IndexStore,
	isScratchKey,
	type KeyNameRefusal,
	keyNameRefusal,
	normalizeKey,
	parseSyntheticClaim,
	RESERVED_INDEX_NAMES,
	readIndexMdActive,
	syntheticClaimLive,
} from "../shared/index-store.ts";
import type { DoctorJson, MwCliResult } from "../shared/mw-runner.ts";
import {
	buildMw,
	decideMw,
	doctorMw,
	getMwStatus,
	initMw,
	modelMw,
	partitionMw,
	RAG_SUBCOMMANDS,
	ragMw,
	restartMw,
	serveStaleness,
	startMw,
	statsMw,
	stopMw,
	targetMw,
	updateEnvMw,
} from "../shared/mw-runner.ts";
import { readLastProductSectionBody } from "../shared/output-sections.ts";
import { SCRATCH_WORKERS_KEY, workerTaskDir } from "../shared/paths.ts";
import { DOC_GATE_HINT, dispatchDocGaps, formatDocsBadge, readPhaseDocs } from "../shared/phase-docs.ts";
import { type PmStateClaimSyncResult, syncPmStateClaimId } from "../shared/pm-state-claim.ts";
import { PHASE_ORDER, phaseAuditWarnings } from "../shared/pm-state-guard.ts";
import { type RunDetachedOptions, type RunDetachedResult, runDetachedMw } from "../shared/run-detached.ts";
import type { WorkerEntry, WorkerStatus, WorkerStore } from "../shared/worker-store.ts";
import {
	classifyWriteTargetShape,
	judgeWriteTarget as judgeSharedWriteTarget,
	WORKER_FILE_NAME_RE,
	type WriteTargetShape,
} from "../shared/write-surface.ts";
import { RECOVERY_CONTRACT_HEADING, recoveryContractSection } from "../worker/output-sections.ts";
import { isSameOrUnder } from "../worker/read-scope.ts";

// W1 (mw-worker-output-contract): shape classification and the basename
// whitelist moved to the write-surface single source; these re-exports keep the
// existing `pm/ui-bridge.ts` importers byte-compatible.
export { classifyWriteTargetShape, type WriteTargetShape } from "../shared/write-surface.ts";

import { isShellRole, isWritelessRole } from "../worker/worker-mode.ts";
import { captureDecisionTaskState, copyTaskState, type TaskStateSnapshot } from "./decision-task-state.ts";
import { type DecisionLifecycleEnvelope, type LifecycleRunner, writeDecisionLifecycle } from "./decision-tool.ts";
import { formatDispatchAlarm, recordDispatchAlarm } from "./pm-orchestrator.ts";
import { planReviewSplitGate } from "./review-split-gate.ts";
import { StateManager } from "./state-manager.ts";
import { type DispatchRefusal, dispatchTask } from "./task-dispatcher.ts";
import {
	canonicalStateBytes,
	type DecidePolicy,
	type DecideRunner,
	type DecisionEnvelopeMeta,
	DP1_ID,
	type Dp1TaskMaterial,
	formatTriageLedgerDetail,
	formatTriageReceipt,
	newDecisionMeta,
	readDecidePolicy,
	TRIAGE_REASON_INPUT_OVERSIZE,
	type TriageResult,
	triageDispatchEnvelope,
} from "./triage-client.ts";

export { captureDecisionTaskState };

/** Owner key for a worker task — this window's own claim first, the shared
 * active pointer second. Explicit key wins (deliberate choice — no warning).
 * Otherwise, when this window watches a key whose _index.parallel row it
 * holds (claimId === this window's host:pid), dispatches land under that key
 * even when another window's later takeover made a different row the
 * globally-latest active one: single-active demote flips the shared pointer
 * between windows, but ownership does not move. A stale or foreign watch
 * (no claim held) falls back to the global active row — but never one held
 * live by another window (injecting work into another window's key is the
 * cross-window dispatch bug this guards); that case degrades to _scratch
 * with a warning. Then the degraded _index.md `active:` pointer, then
 * _scratch. */
export function resolveOwnerKeyWithSync(
	pi: ExtensionAPI,
	indexStore: IndexStore,
	watch: PmWatchState,
	explicit: string | undefined,
	agenticdocRoot: string,
): string {
	const explicitKey = (explicit ?? "").trim();
	if (explicitKey) return explicitKey;
	const self = windowClaimId();
	if (watch.key) {
		// _scratch is watchable but never indexed; a window watching it means
		// its ad-hoc dispatches belong there.
		if (isScratchKey(watch.key)) return SCRATCH_WORKERS_KEY;
		if (indexStore.findByKey(watch.key)?.claimId === self) return watch.key;
	}
	const active = indexStore.activeEntry();
	if (active && claimHeldByAnotherWriter(claimState(active.claimId, self))) {
		warnForeignActiveOnce(pi, active.key);
		return SCRATCH_WORKERS_KEY;
	}
	// `_index.md active:` is a degraded pointer that carries NO claim column, so
	// it cannot be trusted by itself (A7): resolve it back to the
	// `_index.parallel` row and apply the SAME name + liveness gate as the
	// active-row branch. A foreign live value and a reserved/illegal name both
	// degrade to _scratch with a warning instead of silently becoming an owner
	// key in another window's namespace.
	const fallbackKey = active?.key ?? readIndexMdActive(agenticdocRoot);
	if (fallbackKey) {
		if (keyNameRefusal(fallbackKey)) {
			warnForeignActiveOnce(pi, fallbackKey);
			return SCRATCH_WORKERS_KEY;
		}
		const row = indexStore.findByKey(fallbackKey);
		if (row && claimHeldByAnotherWriter(claimState(row.claimId, self))) {
			warnForeignActiveOnce(pi, fallbackKey);
			return SCRATCH_WORKERS_KEY;
		}
		if (watch.key && normalizeKey(watch.key) !== normalizeKey(fallbackKey)) {
			warnOwnerMismatchOnce(pi, watch.key, fallbackKey);
		}
		return fallbackKey;
	}
	if (watch.key) warnOwnerMismatchOnce(pi, watch.key, SCRATCH_WORKERS_KEY);
	return SCRATCH_WORKERS_KEY;
}

/** Warned (watch -> owner) pairs this session. displaySummary persists the
 * warning to the transcript (LLM-visible), so once per pair is enough. */
const warnedOwnerMismatches = new Set<string>();

function warnOwnerMismatchOnce(pi: ExtensionAPI, watchKey: string, ownerKey: string): void {
	const pair = `${watchKey}->${ownerKey}`;
	if (warnedOwnerMismatches.has(pair)) return;
	warnedOwnerMismatches.add(pair);
	displaySummary(
		pi,
		`[mw] owner-key mismatch: this window watches '${watchKey}' but holds no claim on it, and the active key is '${ownerKey}' — ` +
			`dispatching under '${ownerKey}'. Run /pm-key switch ${ownerKey} to align the window.`,
	);
}

/** Warned foreign active keys this session (same once-per-pair rationale as
 * warnedOwnerMismatches). */
const warnedForeignActives = new Set<string>();

function warnForeignActiveOnce(pi: ExtensionAPI, activeKey: string): void {
	if (warnedForeignActives.has(activeKey)) return;
	warnedForeignActives.add(activeKey);
	displaySummary(
		pi,
		`[mw] active key '${activeKey}' is claimed by another live window — not dispatching under it; ` +
			`using '${SCRATCH_WORKERS_KEY}' instead. Pass an explicit key, or switch_key in this window first.`,
	);
}

export function displaySummary(pi: ExtensionAPI, summary: string): void {
	pi.sendMessage({
		customType: "agent-team-loop:worker-summary",
		content: summary,
		display: true,
		details: summary,
	});
}

/** Deliver a message into the conversation AND trigger a PM turn — the
 * shared "wake the PM" channel (finish calls and mid-run escalations).
 * `pi.sendMessage` without `triggerTurn` only injects the message into LLM
 * context: it displays in the transcript, but an idle PM never wakes up.
 * With `triggerTurn: true` an idle PM starts an LLM turn immediately; a
 * streaming PM gets the text steered into the current turn. Informational
 * notices (init, mw start, gate skips) stay passive via displaySummary —
 * they must not spend agent turns. */
export function deliverPmAlert(pi: ExtensionAPI, text: string): void {
	pi.sendMessage(
		{
			customType: "agent-team-loop:worker-summary",
			content: text,
			display: true,
			details: text,
		},
		{ triggerTurn: true },
	);
}

/** Deliver a terminal worker result (the "finish call" of dispatch →
 * monitor → finish call → pm run). See deliverPmAlert for the channel. */
export function deliverWorkerResult(pi: ExtensionAPI, summary: string): void {
	deliverPmAlert(pi, summary);
}

// ── DP-1 pre-dispatch triage (mw-jev-provider-integration T-03) ────────────

/** DP-1 advice attached to one dispatch plan (design D-005/D-006). `null`
 * means the decision feature is fully off — the dispatch must then stay
 * byte-identical to the pre-T-03 behaviour. */
export interface DispatchTriage {
	result: TriageResult;
	alertOnDisagreement: boolean;
	notifyOnUnavailable: boolean;
	/** The type actually dispatched — never rewritten by the advice. */
	dispatchedType: string;
	disagreement: boolean;
	/** One-line receipt echo; "" when there is nothing to show. */
	receipt: string;
	/** T-04c (D-041): the decision this dispatch CONSUMES, i.e. the one whose
	 * `decision:` head line `writeDispatchTaskMd` may write. Only an authorized
	 * (`mode=auto`) usable answer whose `triage_type` MATCHES the dispatched type
	 * and that carries a `decision_id` produces it; `suggest` / a disagreement /
	 * unavailable / an anonymous answer leave it undefined, which keeps the
	 * pre-T-08 task.md bytes. */
	decision?: DispatchDecision;
	/** T03: the local envelope of the decision this dispatch created, when the
	 * producer really called the service. `undefined` on a skipped path — there is
	 * no decision record to join lifecycle feedback to. */
	meta?: DecisionEnvelopeMeta;
	/** T03: `material` = the `{material, meta}` envelope really went on the wire;
	 * `skipped` = no call was made (role outside dp1's taxonomy / missing
	 * material / over budget). */
	statePath: "material" | "skipped";
	/** T03: the one audit line the dispatch writes into the task's `trace.log`
	 * (`[DECISION] dp1 state=material bytes=<N>` / `state=skipped
	 * reason=<unsupported-type|missing-material|oversize>`). Never silent. */
	stateTrace: string;
}

/** The decision a dp1 dispatch CONSUMES from one usable triage result.
 *
 * D-041 makes adoption a consuming-side fact: Python's `acted=false` only says
 * it did not execute an action itself (an `answer` intent never executes), not
 * that the answer was rejected. The dispatch side therefore adopts the triage
 * type itself — but ONLY when the child actually authorized it (`mode=auto`),
 * delivered a `triage_type` and a `decision_id`, AND that type is the one this
 * dispatch actually uses. Task.md has exactly three states:
 *
 * | mode | `triage_type` vs dispatched | acted | `decision:` head line |
 * | --- | --- | --- | --- |
 * | `auto` | equal (agree) | `true` | written |
 * | `auto` | different (disagree) | `false` | not written |
 * | `suggest` (any) | either | `false` | not written |
 *
 * AC-014: the dispatch never rewrites its `type:` from the advice, so a
 * disagreeing answer was NOT adopted (T-04c adoption = "the dispatcher took
 * this type"). Counting it as adopted would push a disagreement into the
 * agreement-rate numerator, so it stays un-correlated exactly like `suggest`:
 * the answer and its `decision_id` remain observable in the {@link TriageResult}
 * (the ledger/report channel), only the head line is withheld. A missing or
 * empty dispatched type also fails closed (never "unknown means adopted").
 * An unavailable result and an answer without an id are undefined too, so the
 * task.md bytes stay byte-identical to the pre-T-08 shape. This never reads
 * `.mw/decide-points.json` (D-036). */
function dispatchDecisionOf(result: TriageResult, dispatchedType: string): DispatchDecision | undefined {
	if (!result.available || result.mode !== "auto" || result.triage_type === undefined) return undefined;
	// AC-014 disagreement gate: an advice naming another type was not adopted.
	if (result.triage_type !== dispatchedType) return undefined;
	const decisionId = (result.decision_id ?? "").trim();
	if (decisionId === "") return undefined;
	return { decisionId, acted: true };
}

/** Dispatch-plan facts the dp1 business material is built from (T03).
 *
 * The material is the dispatch card's own 上下文 / 要求 / 交付格式 bodies — no
 * summary, no risk label, no audit identity (mw-decision-context design §2).
 * `sections` is the judged card's seed extraction (`readDispatchCard`); `key`
 * and `taskKey` are the REAL ids this dispatch already reserved, so the decision
 * is associated with them instead of guessing "the latest task". */
export interface Dp1DispatchPlan {
	/** AgenticTask key the task lands under. */
	key?: string;
	/** The reserved, REAL task id (`dispatch_worker` mints it before the decision
	 * runs). Absent/null = a PM decision with no task. */
	taskKey?: string | null;
	/** The dispatched `type:` (never rewritten by the advice). */
	taskType?: string;
	/** Card seed sections; absent means the producer has no original material. */
	sections?: CardSections;
	taskBefore?: TaskStateSnapshot;
}

/** Call-site facts only the dispatch entry knows. */
export type Dp1DispatchFacts = Pick<Dp1DispatchPlan, "key" | "taskKey" | "sections" | "taskBefore">;

const DP1_TYPE_CHOICES: readonly string[] = ["coding", "research", "review"];

/** Build result for one dp1 material envelope. The builder itself never
 * truncates or summarises (the transport refuses over-budget material as a
 * whole); `unsupported-type` means the role is outside dp1's three-value
 * taxonomy and the dispatch must ask no decision at all. */
export type Dp1MaterialBuild =
	| { ok: true; material: Dp1TaskMaterial; bytes: number }
	| { ok: false; reason: "unsupported-type" | "missing-material" };

/** Build the dp1 business material from the dispatch card (T03).
 *
 * Exactly the registry's `modelStateFields` for dp1 — `task_goal`,
 * `task_requirements`, `task_deliverables` — each the card's ORIGINAL body
 * (上下文 / 要求 / 交付格式), verbatim. No summary, no risk label, no identity
 * fields: those ride on the local envelope (`newDecisionMeta`). */
export function buildDp1DecisionMaterial(plan: Dp1DispatchPlan): Dp1MaterialBuild {
	const taskType = plan.taskType ?? "";
	if (!DP1_TYPE_CHOICES.includes(taskType)) return { ok: false, reason: "unsupported-type" };
	const sections = plan.sections;
	const material: Dp1TaskMaterial = {
		task_goal: (sections?.context ?? "").trim(),
		task_requirements: (sections?.requirements ?? "").trim(),
		task_deliverables: (sections?.deliverables ?? "").trim(),
	};
	if (Object.values(material).some((value) => value === "")) return { ok: false, reason: "missing-material" };
	return { ok: true, material, bytes: canonicalStateBytes(material) };
}

/** Local-envelope metadata for one dp1 dispatch. The PM is the initiating role;
 * `task_key` is the id the dispatch already reserved (never inferred). The role
 * is T02's lowercase `pm` — the writer's closed vocabulary has a single
 * spelling and a producer never carries a second one. */
export function dp1DecisionMeta(plan: Dp1DispatchPlan): DecisionEnvelopeMeta {
	return newDecisionMeta({
		key: plan.key ?? "",
		taskKey: plan.taskKey ?? null,
		initiatorRole: "pm",
		taskBefore: plan.taskBefore,
	});
}

/** One stage of the consumer's lifecycle feedback for a dp1 decision.
 *
 * The extension never appends a ledger row itself (the Python writer is the
 * single lifecycle writer, T05): {@link writeDp1Lifecycle} derives the
 * structural fact and hands it to `mw decide lifecycle --stdin --json`.
 * `consumed` is emitted only when an answer really arrived, so "received" can
 * never be claimed for a failed call. */
export type Dp1ConsumerStage = "consumed" | "executed" | "settled";

/** What really happened at one consumer stage (never derived from a receipt). */
export interface Dp1ConsumerFact {
	/** `consumed`: the answer the PM received (dp1's `triage_type`). */
	answer?: string;
	/** `executed`: the CLOSED T02 action label the consumer really performed. */
	action?: string;
	/** `executed`: what the result was based on. */
	result?: string;
	/** `settled`: the CLOSED T02 outcome of this round. */
	outcome?: string;
	reason?: string;
	taskAfter?: TaskStateSnapshot;
}

/**
 * One lifecycle fact for the dp1 consumer, in the shape T05's
 * `mw decide lifecycle --stdin --json` accepts (`{meta, decision_id, dp, stage,
 * event_id, ...}`).
 *
 * `undefined` means "no fact may be written": there is no real decision
 * (skipped producer / no logical_id / no decision_id), or `consumed` was
 * requested without an answer that really arrived. Stage fields follow T02's
 * closed sets exactly: `consumed` carries only `answer`, `executed` only
 * `action`+`result`, `settled` only `outcome` — mixing them is refused by the
 * writer, so it is refused here instead of being silently dropped.
 *
 * `event_id` is deterministic per (logical_id, stage): a retry of the SAME write
 * replays the same event and the writer reports `duplicate`, never a second
 * business fact.
 */
export function buildDp1LifecycleFact(
	triage: DispatchTriage | null,
	stage: Dp1ConsumerStage,
	fact: Dp1ConsumerFact,
): DecisionLifecycleEnvelope | undefined {
	const logicalId = triage?.meta?.logical_id;
	const decisionId = triage?.result.decision_id ?? "";
	if (triage === null || triage.meta === undefined) return undefined;
	if (logicalId === undefined || logicalId === "" || decisionId === "") return undefined;
	const envelope: DecisionLifecycleEnvelope = {
		meta: triage.meta,
		decision_id: decisionId,
		dp: DP1_ID,
		stage,
		event_id: `dp1:${logicalId}:${stage}`,
	};
	if (fact.reason !== undefined) envelope.reason = fact.reason;
	if (stage !== "consumed" && triage.meta.task_key !== null && fact.taskAfter !== undefined)
		envelope.task_after = copyTaskState(fact.taskAfter);
	if (stage === "consumed") {
		// "Received" is only a fact when the service really answered.
		if (!triage.result.available) return undefined;
		if (fact.answer === undefined || fact.answer === "") return undefined;
		envelope.answer = fact.answer;
		return envelope;
	}
	if (stage === "executed") {
		if (fact.action === undefined || fact.action === "") return undefined;
		envelope.action = fact.action;
		if (fact.result !== undefined) envelope.result = fact.result;
		return envelope;
	}
	if (fact.outcome === undefined || fact.outcome === "") return undefined;
	envelope.outcome = fact.outcome;
	return envelope;
}

/** Write one dp1 consumer fact through the single Python lifecycle writer.
 *
 * The dispatch action is NEVER re-run from here: a failed write is reported as
 * `failed` (the action itself is not undone), which is why the caller appends
 * the writer's own verdict to the receipt instead of assuming success.
 */
export async function writeDp1Lifecycle(
	projectDir: string,
	triage: DispatchTriage | null,
	stage: Dp1ConsumerStage,
	fact: Dp1ConsumerFact,
	runner?: LifecycleRunner,
): Promise<{ stage: Dp1ConsumerStage; status: "written" | "duplicate" | "failed"; recorded: boolean }> {
	const envelope = buildDp1LifecycleFact(triage, stage, fact);
	if (envelope === undefined) return { stage, status: "failed", recorded: false };
	const result = await writeDecisionLifecycle(projectDir, envelope, runner);
	return { stage: result.stage, status: result.status, recorded: result.recorded };
}

/** The receipt line the dp1 consumer reports, derived ONLY from the writer's
 * own answers (`written`/`duplicate`/`failed`). Empty when there was no real
 * decision to report, so a skipped producer adds no bytes to the receipt. */
export function formatDp1ConsumerReceipt(results: Array<{ stage: string; status: string }>): string {
	if (results.length === 0) return "";
	return `[decision] dp1 ${results.map((result) => `${result.stage}=${result.status}`).join(" ")}`;
}

/**
 * Write the dp1 consumer feedback for ONE dispatch that already asked dp1.
 *
 * Order is the real order of facts: the answer was `consumed`; then either the
 * dispatch was refused (`settled` rework, no `executed`), or it really
 * dispatched (`executed` type-read + `settled` ok). `executed`'s result records
 * the dispatch it did, and a disagreement keeps the original type
 * (`kept-type:<type>`) because the advice never rewrites the dispatch.
 *
 * A failed write is REPORTED (`failed`), never retried with a different action
 * and never re-run as a dispatch.
 */
export async function writeDp1DispatchFeedback(input: {
	projectDir: string;
	triage: DispatchTriage | null;
	lifecycleRun?: LifecycleRunner;
	taskKey: string;
	dispatchedType: string;
	refused: boolean;
	taskAfter?: TaskStateSnapshot;
}): Promise<Array<{ stage: Dp1ConsumerStage; status: "written" | "duplicate" | "failed" }>> {
	const { projectDir, triage, lifecycleRun, taskKey, dispatchedType, refused } = input;
	const results: Array<{ stage: Dp1ConsumerStage; status: "written" | "duplicate" | "failed" }> = [];
	if (triage !== null && triage.statePath === "material" && triage.result.available) {
		const answer = triage.result.triage_type;
		if (answer !== undefined && answer !== "") {
			results.push(await writeDp1Lifecycle(projectDir, triage, "consumed", { answer }, lifecycleRun));
		}
	}
	if (results.length === 0) return results;
	if (refused) {
		results.push(
			await writeDp1Lifecycle(
				projectDir,
				triage,
				"settled",
				{ outcome: "rework", reason: "dispatch-refused", taskAfter: input.taskAfter },
				lifecycleRun,
			),
		);
		return results;
	}
	const keptType = triage?.disagreement ?? false;
	results.push(
		await writeDp1Lifecycle(
			projectDir,
			triage,
			"executed",
			{ action: "type-read", result: keptType ? `kept-type:${dispatchedType}` : `dispatched:${taskKey}` },
			lifecycleRun,
		),
	);
	results.push(
		await writeDp1Lifecycle(
			projectDir,
			triage,
			"settled",
			{ outcome: "ok", taskAfter: input.taskAfter },
			lifecycleRun,
		),
	);
	return results;
}

function readDottedPath(state: Record<string, unknown>, dotted: string): unknown {
	let current: unknown = state;
	for (const part of dotted.split(".")) {
		if (current === null || typeof current !== "object" || Array.isArray(current)) return undefined;
		current = (current as Record<string, unknown>)[part];
	}
	return current;
}

function isBlankStateValue(value: unknown): boolean {
	return value === undefined || value === null || (typeof value === "string" && value.trim() === "");
}

/** The only top-level key a registry state may carry beyond its required set
 * (`assertStateMatchesRegistry`; other DPs use it for engineered context). */
const STATE_CONTEXT_KEY = "context";

/** Assert one built state matches its registry row (W6: the registry is the
 * field-list authority, so a producer may never send a second hand-written
 * list). Missing required paths AND uncontrolled keys throw; `context` is the
 * only extra top-level key and its slots must be in the dp's `contextSlots`.
 *
 * The extras check is deliberately top-level: the registry lists required paths
 * only, while a dp may also carry OPTIONAL L1 children (dp2's
 * `progress.writes`/`trend`), which must not read as drift. */
export function assertStateMatchesRegistry(dpId: string, state: Record<string, unknown>): void {
	const entry = DECIDE_REGISTRY[dpId];
	if (entry === undefined) throw new Error(`decide registry: unknown dp '${dpId}'`);
	const required = entry.requiredStateFields.map((field) => field.name);
	const missing = required.filter((path) => isBlankStateValue(readDottedPath(state, path)));
	const allowedTopLevel = new Set(required.map((path) => path.split(".")[0] ?? path));
	// A registry-declared optional L1 field is legal material too (dp2's
	// `worker_execution`): it is not drift, so it must not read as `extra`.
	for (const field of entry.optionalStateFields) {
		allowedTopLevel.add(field.name.split(".")[0] ?? field.name);
	}
	allowedTopLevel.add(STATE_CONTEXT_KEY);
	const extra = Object.keys(state).filter((key) => !allowedTopLevel.has(key));
	const context = state[STATE_CONTEXT_KEY];
	if (context !== undefined) {
		if (context === null || typeof context !== "object" || Array.isArray(context)) {
			extra.push(`${STATE_CONTEXT_KEY}:<not-an-object>`);
		} else {
			for (const slot of Object.keys(context as Record<string, unknown>)) {
				if (!entry.contextSlots.includes(slot)) extra.push(`${STATE_CONTEXT_KEY}.${slot}`);
			}
		}
	}
	if (missing.length === 0 && extra.length === 0) return;
	const problems: string[] = [];
	if (missing.length > 0) problems.push(`missing=${missing.join(",")}`);
	if (extra.length > 0) problems.push(`extra=${extra.join(",")}`);
	throw new Error(`dp ${dpId} state does not match the registry: ${problems.join("; ")}`);
}

/** Compute the dp1 decision advice for one dispatch. Reads `.mw/decide.json`
 * (read-only) and asks the decision client with the card's ORIGINAL material on
 * the local envelope; `null` on the default-off path so nothing changes.
 * Never throws.
 *
 * T03: the request shape is `{material, meta}` (dp1 model state = the three
 * business strings; identity only in `meta`). A role outside the three-value
 * taxonomy, missing material or over-budget material is a ZERO-spawn skip,
 * recorded in {@link DispatchTriage.stateTrace} (never silent) — the old
 * `{state}` / string fallback branches, which also asked a `triage_risk`
 * question and truncated the task text, are gone (spec §1.7). */
export function computeDispatchTriage(input: {
	projectDir: string;
	dispatchedType: string;
	run?: DecideRunner;
	/** Dispatch-plan facts; omitted (direct API callers) = no decision call. */
	dp1?: Dp1DispatchPlan;
	/** Pre-read policy (tests); read from disk when omitted. */
	policy?: DecidePolicy;
}): DispatchTriage | null {
	const policy = input.policy ?? readDecidePolicy(input.projectDir);
	if (!policy.enabled || !policy.dp1Enabled) return null;
	let statePath: "material" | "skipped" = "skipped";
	let skipReason: "unsupported-type" | "missing-material" | "oversize" = "missing-material";
	let materialBytes = 0;
	let meta: DecisionEnvelopeMeta | undefined;
	let result: TriageResult;
	const plan = input.dp1;
	const candidate = plan === undefined ? undefined : dp1DecisionMeta(plan);
	const built = plan === undefined ? undefined : buildDp1DecisionMaterial(plan);
	if (built === undefined || !built.ok) {
		skipReason = built === undefined ? "missing-material" : built.reason;
		result = {
			available: false,
			reason: skipReason === "unsupported-type" ? "unsupported-type" : "input-incomplete",
			confidences: {},
			confidence_source: "unknown",
			latency_ms: 0,
		};
	} else {
		materialBytes = built.bytes;
		const decision = triageDispatchEnvelope({
			projectDir: input.projectDir,
			dpId: DP1_ID,
			material: built.material,
			meta: candidate as DecisionEnvelopeMeta,
			policy,
			run: input.run,
		});
		result = decision;
		if (decision.available === false && decision.escalate_to_human === true) {
			// Zero-spawn refusal from the transport: no decision record was created.
			skipReason = decision.reason === TRIAGE_REASON_INPUT_OVERSIZE ? "oversize" : "missing-material";
		} else {
			// The call really happened (also when it degraded): the record exists, so
			// its id is the association key for later feedback.
			statePath = "material";
			meta = candidate;
		}
	}
	const stateTrace =
		statePath === "material"
			? `[DECISION] dp1 state=material bytes=${materialBytes}`
			: `[DECISION] dp1 state=skipped reason=${skipReason}`;
	return {
		result,
		alertOnDisagreement: policy.alertOnDisagreement,
		notifyOnUnavailable: policy.notifyOnUnavailable,
		dispatchedType: input.dispatchedType,
		disagreement: result.available && result.triage_type !== undefined && result.triage_type !== input.dispatchedType,
		receipt: formatTriageReceipt(result),
		decision: dispatchDecisionOf(result, input.dispatchedType),
		meta,
		statePath,
		stateTrace,
	};
}

/** Durable + wake channel for one triage outcome (design D-005 item 3).
 * Best-effort: the ledger writer never throws; `deliverPmAlert` (one PM turn)
 * fires ONLY on a disagreement the config did not mute. Unavailable advice is
 * completely silent unless `triage_notify_on_unavailable=true`. */
export function emitDispatchTriage(pi: ExtensionAPI, agenticdocRoot: string, triage: DispatchTriage | null): void {
	if (!triage) return;
	// A skipped producer asked no decision: there is no advice to record and no
	// unavailable *call* to notice (T03). The trace line already carries the skip.
	if (triage.statePath === "skipped") return;
	if (triage.result.available) {
		const detail = formatTriageLedgerDetail(triage.result, triage.dispatchedType);
		recordDispatchAlarm(agenticdocRoot, { kind: "triage-suggestion", count: 1, detail });
		if (triage.disagreement && triage.alertOnDisagreement) {
			deliverPmAlert(pi, formatDispatchAlarm({ kind: "triage-suggestion", count: 1, detail }));
		}
		return;
	}
	if (triage.notifyOnUnavailable) {
		recordDispatchAlarm(agenticdocRoot, {
			kind: "triage-unavailable",
			count: 1,
			detail: `dp=dp1 reason=${triage.result.reason ?? "unknown"}`,
		});
	}
}

/** Append the triage receipt line to a dispatch receipt. Byte-identical when
 * there is no advice to show (default-off equivalence, T-03 requirement 5). */
export function appendTriageReceipt(text: string, triage: DispatchTriage | null): string {
	const line = triage?.receipt ?? "";
	return line === "" ? text : `${text}\n${line}`;
}

/** The acted decision a triage result carries, or undefined.
 *
 * Design D-036 makes the child (`mw decide run --dp <id> --json`) the single
 * authority for `decision_id` / `mode` / `acted`; the triage result type only
 * declares the legacy fields today, so this reads the additive keys
 * structurally and stays undefined until the client forwards them. It never
 * infers `acted` from the mode or from `.mw/decide-points.json` (that mirror is
 * exactly what D-036 forbids), and a non-`acted` answer is dropped here. */
export function actedDecisionOf(triage: DispatchTriage | null): DispatchDecision | undefined {
	const carried: unknown = triage?.result;
	if (typeof carried !== "object" || carried === null) return undefined;
	const record = carried as Record<string, unknown>;
	const decisionId = typeof record.decision_id === "string" ? record.decision_id.trim() : "";
	if (record.acted !== true || decisionId === "") return undefined;
	return { decisionId, acted: true };
}

// ── Per-window watch state + bottom progress widget ────────────────────────

export interface PmWatchState {
	/** AgenticTask key this window explicitly executes; undefined = not watching. */
	key: string | undefined;
	/** Task keys THIS window dispatched in this process (mw-task-scope-isolation).
	 * Optional so callers that only track the watch key keep building the state
	 * as a plain literal. Needed because the owner key is not always the watched
	 * key: an explicit `key:` dispatch is honoured without warning
	 * (resolveOwnerKeyWithSync) and the global-active fallback lands elsewhere
	 * too, yet both are this window's work for list_tasks / ack. Process-local by
	 * design — never persisted, never shared between windows. */
	dispatchedTaskKeys?: Set<string>;
}

export interface PmUiHolder {
	/** Latest ExtensionContext, captured on session_start so background timers
	 * can render UI. Undefined before session start or in headless runs. */
	ctx: ExtensionContext | undefined;
}

/** Session entry type persisting this window's watched key across restarts. */
export const WATCH_ENTRY_TYPE = "agent-team-loop:watch";

// ── Window claim identity (_index.parallel claimId) ─────────────────────────

/** This window's claim identity: host:pid. Written into _index.parallel so
 * another window can tell whether a key's claim is still held by a live
 * process (pid check) before taking it over. */
export function windowClaimId(): string {
	return `${os.hostname()}:${process.pid}`;
}

interface ClaimInfo {
	host: string;
	pid: number;
}

/** Parse a `host:pid` claim; anything else (e.g. legacy timestamp claims) is
 * unparseable and treated as stale. */
function parseClaim(claimId: string): ClaimInfo | undefined {
	const m = claimId.match(/^([^:]+):(\d+)$/);
	if (!m) return undefined;
	const pid = Number(m[2]);
	if (!Number.isInteger(pid) || pid <= 0) return undefined;
	return { host: m[1] ?? "", pid };
}

function isPidAlive(pid: number): boolean {
	try {
		process.kill(pid, 0);
		return true;
	} catch (err) {
		// EPERM: process exists but is not ours — still alive. ESRCH: gone.
		return (err as NodeJS.ErrnoException).code === "EPERM";
	}
}

export type ClaimState = "free" | "held-live" | "held-stale" | "held-conductor";

/** Who holds a key's `_index.parallel` claim — deliberately a HOLDER verdict,
 * not a takeover verdict (the two differ for exactly one holder):
 *  - "held-live": another live window (or a foreign host whose liveness we
 *    cannot verify) holds it. A takeover needs `--force`.
 *  - "held-conductor": THIS host's autopilot conductor holds it through its
 *    synthetic claim `autopilot@<host>:<pid>` (T-16). The conductor yields to
 *    a human takeover on its next tick, so `takeOverKey` succeeds WITHOUT
 *    `--force` (T-16b requirement 1).
 *  - "held-stale": the holder is gone; "free": nobody (or this window).
 *
 * The synthetic branch is decided by index-store's shared parser
 * (`parseSyntheticClaim` + `syntheticClaimLive`), never by a prefix test
 * repeated here: the TS takeover guard and the Python conductor can then only
 * drift through that one predicate (T-16b requirement 4). */
export function claimState(claimId: string, self: string): ClaimState {
	const trimmed = claimId.trim();
	if (!trimmed || trimmed === self) return "free";
	// Local conductor-owned claim (T-16). A synthetic claim from ANOTHER host is
	// a different machine's conductor: it must not be stolen without --force, so
	// it falls through to the ordinary foreign-host rule below (parseClaim reads
	// "autopilot@host" as a host name and returns "held-live").
	const synthetic = parseSyntheticClaim(trimmed);
	if (synthetic !== undefined && synthetic.host === os.hostname()) {
		return syntheticClaimLive(trimmed) ? "held-conductor" : "held-stale";
	}
	const c = parseClaim(trimmed);
	if (!c) return "free"; // legacy/unparseable claim — stale
	if (c.host !== os.hostname()) return "held-live"; // cannot verify liveness
	return isPidAlive(c.pid) ? "held-live" : "held-stale";
}

/** Is the key held by someone OTHER than this window — a live human window
 * ("held-live") or this host's conductor ("held-conductor")? Both keep the
 * namespace foreign for the cross-key read/write guard (AC-024) and for
 * owner-key resolution: the conductor is YIELDABLE, but only through the
 * explicit `takeOverKey` path — never by a silent write into its key. */
function claimHeldByAnotherWriter(state: ClaimState): boolean {
	return state === "held-live" || state === "held-conductor";
}

/** Machine-readable refusal code for a cross-key write (AC-024). */
export const CROSS_KEY_READ_ONLY = "cross-key-read-only";

/** Writer surfaces the cross-key guard actually fences, in refusal-text order.
 * Single declaration source (AC-003/VC-011): the refusal body below is built
 * from this array, and the coverage test asserts every entry maps to a real
 * guard call site — the text can never again claim a surface the code does not
 * guard (the pre-AC-003 gap: it named `/worker` while only dispatch_worker and
 * advance_phase called the guard). */
export const CROSS_KEY_READ_ONLY_SURFACES = ["dispatch_worker", "/worker", "advance_phase"] as const;

/** Row-ack addendum of the refusal text: `ack_worker_result` filters rows by
 * ownership instead of calling the guard, so it is named in the text but is
 * deliberately NOT part of {@link CROSS_KEY_READ_ONLY_SURFACES} (which is the
 * call-site set VC-011 compares against). */
export const CROSS_KEY_READ_ONLY_ACK_NOTE = "acking its rows";

/** Cross-key write guard (AC-024): a key whose `_index.parallel` row is held
 * live by ANOTHER window is READ-ONLY for this window. Reading it stays global
 * and unrestricted (`list_tasks` scope "all"/"key", `mw_status`, `mw doctor`,
 * the watch panel); the WRITER surfaces refuse with the stable
 * {@link CROSS_KEY_READ_ONLY} code instead of silently touching another
 * window's namespace. Writable: this window's own claim, an unclaimed key
 * (new-key bootstrap: write spec.md -> advance -> dispatch), and `_scratch`.
 * Returns null when the write is allowed. */
export function foreignLiveClaimRefusal(indexStore: IndexStore, key: string): string | null {
	const trimmed = key.trim();
	if (!trimmed || isScratchKey(trimmed)) return null;
	// Explicit name gate (A5): reserved framework names and illegal shapes are
	// refused unconditionally. The pre-AC-006 `_`/`.` prefix exemption returned
	// null BEFORE findByKey, so a live `_tmp` key passed and reserved files could
	// be used as key namespaces — there is no such bypass left.
	const nameRefusal = keyNameRefusal(trimmed);
	if (nameRefusal) return reservedKeyRefusal(trimmed, nameRefusal);
	const claim = indexStore.findByKey(trimmed)?.claimId.trim() ?? "";
	if (!claim) return null;
	const state = claimState(claim, windowClaimId());
	if (!claimHeldByAnotherWriter(state)) return null;
	// The holder is named exactly: a human window needs --force to be displaced
	// from, while the conductor yields to a plain (non-forced) takeover. The
	// refusal code is the same for both, so callers/tests keep one contract.
	const holder =
		state === "held-conductor"
			? `by this host's autopilot conductor (synthetic claim ${claim})`
			: `live by another window (claim ${claim})`;
	const escapeHint =
		state === "held-conductor"
			? `switch_key { key: "${trimmed}" } (no force needed — the conductor yields to a human claim)`
			: `switch_key { key: "${trimmed}" } (ask the user before stealing a live claim)`;
	return (
		`[${CROSS_KEY_READ_ONLY}] key '${trimmed}' is held ${holder} — ` +
		"this window's view of it is read-only.\n" +
		`Allowed: list_tasks { scope: "all" } or { scope: "key", key: "${trimmed}" }, mw_status, mw doctor, the watch panel.\n` +
		`Refused: ${CROSS_KEY_READ_ONLY_SURFACES.join(", ")}, ${CROSS_KEY_READ_ONLY_ACK_NOTE}.\n` +
		`To act on it, take it over first: ${escapeHint}`
	);
}

/** Refusal text for a key NAME that fails the shape/reserved gate (AC-006):
 * there is no owner to negotiate with — the name itself is unusable, so the
 * cross-key escape hatch (switch_key) does not apply. */
function reservedKeyRefusal(key: string, refusal: KeyNameRefusal): string {
	return (
		`[${CROSS_KEY_READ_ONLY}] key '${key}' is refused (${refusal.code}): ${refusal.message}.\n` +
		`Allowed: names matching ^[A-Za-z0-9][A-Za-z0-9._-]*$ that are not reserved framework names (${RESERVED_INDEX_NAMES.join(", ")}).\n` +
		`Refused: ${CROSS_KEY_READ_ONLY_SURFACES.join(", ")}, ${CROSS_KEY_READ_ONLY_ACK_NOTE}.`
	);
}

export interface TakeoverResult {
	ok: boolean;
	/** Present when ok=false: the live claim that blocked the takeover. */
	blockedBy?: string;
	claimId: string;
	/** True when the key row was auto-created (key was unknown to _index.parallel). */
	created: boolean;
	/** Phase-chain audit warnings for the claimed key (empty = clean):
	 * two-source divergence + gate-evidence gaps for phases the pm-state
	 * claims to have passed. Non-blocking — claiming a broken key to fix it
	 * is legitimate; the warnings make the breakage visible immediately. */
	audit: string[];
	/** Present when ok=false: the key NAME was refused by the shared
	 * shape/reserved gate (AC-006, stable `keyNameRefusal` code) rather than a
	 * live foreign claim. */
	refusal?: string;
	/** Result of mirroring the claim into {key}/pm-state.md's '- Claim-Id:'
	 * line (mw-worker-visibility-gate D-107/D-108); undefined when the claim
	 * itself failed. A failed mirror never flips `ok` — the index row is
	 * authoritative, pm-state.md is only its mirror. */
	claimSync?: PmStateClaimSyncResult;
}

/** Claim a key for this window — shared by /pm-key switch, /pm-key new and
 * the spec-write auto-takeover. Routes through IndexStore.claim so the
 * liveness check, demote, and write are one atomic step under the index
 * lock: racing windows cannot both believe they claimed. Also runs the
 * phase-chain audit on success (audit_phase.py's TS-side mirror). */
export async function takeOverKey(
	indexStore: IndexStore,
	key: string,
	force: boolean,
	agenticdocRoot: string,
): Promise<TakeoverResult> {
	const self = windowClaimId();
	const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", { force });
	const audit = outcome.ok ? phaseAuditWarnings(agenticdocRoot, key, outcome.entry.phase) : [];
	// Case-variant audit (design-role-key-identity §5.1 / DD-07d): the claim hit a
	// stored row spelled differently only by case, so the window now owns
	// `<stored>` while the user typed `<key>`. Surface it on the existing audit
	// channel (every takeOverKey caller already notifies `result.audit`) instead
	// of letting the substitution stay invisible.
	if (outcome.caseVariantOf) {
		audit.push(`[KEY] case-variant '${key}' -> stored '${outcome.caseVariantOf}'`);
	}
	// Mirror the claim into {key}/pm-state.md's '- Claim-Id:' line (D-108):
	// every path that flips the index row's Claim column must also sync the
	// mirror, or the two sources diverge. Failure is non-fatal by design.
	const claimSync = outcome.ok ? syncPmStateClaimId(agenticdocRoot, key, self) : undefined;
	return {
		ok: outcome.ok,
		blockedBy: outcome.blockedBy,
		refusal: outcome.refusal,
		claimId: self,
		created: outcome.created,
		audit,
		claimSync,
	};
}

/** One-line warning for a claim whose pm-state.md mirror sync failed
 * (D-108): the claim itself succeeded — the index row is authoritative — so
 * this only makes the divergence visible to the user/agent. "" when the
 * sync succeeded or never ran (nothing to warn about). */
export function claimSyncWarningText(key: string, sync?: PmStateClaimSyncResult): string {
	if (sync?.ok !== false) return "";
	return `WARNING: claim succeeded but ${key}/pm-state.md was not synced (${sync.reason}). The index row is authoritative.`;
}

const WATCH_WIDGET_KEY = "agent-team-loop-watch";
/** History rows kept in the widget (D-003): done rows and acked terminal
 * rows are processed history — newest five shown, the rest folded into
 * `+N more`. Live (running/pending) and unhandled (failed/nc awaiting ack)
 * rows are never folded. */
const WATCH_HISTORY_MAX = 5;
const WATCH_LINE_MAX = 110;

const STATUS_GLYPH: Record<WorkerStatus, string> = {
	pending: ".",
	running: ">",
	done: "+",
	failed: "x",
	"needs-clarification": "?",
	// Product says the run started but its process is gone and the outcome is
	// unknown (D-022/T-20) — loud on purpose: a `lost` row needs a human look.
	lost: "!",
};

function trunc(s: string, max: number): string {
	return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

/** Owner key of a queue row: the first taskPath segment below the agenticdoc
 * root ({key}/workers/<task>/task.md → key). Legacy root-level rows resolve to
 * their own task key and simply never match a watched key. */
export function ownerKeyOf(entry: WorkerEntry, agenticdocRoot: string): string {
	const rel = path.relative(agenticdocRoot, path.normalize(entry.taskPath));
	return rel.split(path.sep)[0] ?? "";
}

/** Does THIS window own the queue row (mw-task-scope-isolation)? True when the
 * row sits under the watched key, or when this process dispatched the task
 * (explicit cross-key dispatch, or the global-active fallback — see
 * resolveOwnerKeyWithSync). Fail-closed: with no watch key and no dispatch
 * record the row belongs to another window. Shared by list_tasks and both ack
 * entry points, so what the tools act on matches what the bottom watch widget
 * shows (it scopes by ownerKeyOf alone). */
export function ownedByThisWindow(entry: WorkerEntry, watch: PmWatchState, agenticdocRoot: string): boolean {
	return ownerKeyOf(entry, agenticdocRoot) === watch.key || watch.dispatchedTaskKeys?.has(entry.taskKey) === true;
}

/** Body of a `## <section>` block in output.md (first match), trimmed;
 * undefined when the file or section is missing. Generic reader behind
 * readOutputSummary and the terminal-detail fallback chains (D-004): `##
 * TL;DR`, `## Exit Reason`, `## Questions`. The section literal is regex-escaped
 * so a future caller-side string with metacharacters can never inject. */
export function readOutputSection(taskDir: string, section: string): string | undefined {
	let content: string;
	try {
		content = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
	} catch {
		return undefined;
	}
	const m = content.match(
		new RegExp(`## ${section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\n+([\\s\\S]*?)(?=\\n## |$)`),
	);
	return m ? m[1].trim() : undefined;
}

/** `## Summary` body — the legacy detail source, now the done-row fallback
 * when no `## TL;DR` exists (old output.md files, AC-009). */
export function readOutputSummary(taskDir: string): string | undefined {
	return readOutputSection(taskDir, "Summary");
}

/** Cap for terminal readback bodies (AC-014). */
export const OUTPUT_READBACK_MAX = 20_000;

/** Full output.md body for terminal readback (AC-014): worker results are
 * delivered into the watching window's conversation so the PM processes
 * them without manual file reads. Over-cap reports are truncated with a
 * pointer to the file. */
export function readOutputBody(taskDir: string): string | undefined {
	const outputPath = path.join(taskDir, "output.md");
	let content: string;
	try {
		content = fs.readFileSync(outputPath, "utf8").trim();
	} catch {
		return undefined;
	}
	if (!content) return undefined;
	if (content.length <= OUTPUT_READBACK_MAX) return content;
	return `${content.slice(0, OUTPUT_READBACK_MAX)}\n\n…(truncated — full report: ${outputPath})`;
}

/** Last `[launcher] spawn failed …` line from worker.log, if any. Spawn-failure
 * logs are tiny (the CLI never ran — the launcher writes exactly this line and
 * nothing else); a large log means the worker actually ran, so ignore it. */
export function readSpawnFailure(taskDir: string): string | undefined {
	const logPath = path.join(taskDir, "worker.log");
	try {
		const stat = fs.statSync(logPath);
		if (stat.size > 64 * 1024) return undefined;
		const lines = fs.readFileSync(logPath, "utf8").split("\n");
		for (let i = lines.length - 1; i >= 0; i--) {
			const line = lines[i].trim();
			if (line.startsWith("[launcher] spawn failed")) return line;
		}
		return undefined;
	} catch {
		return undefined;
	}
}

/** worker.log read guard for the needs-clarification fallback: larger logs
 * mean the worker actually ran (D-004) — skip the read entirely. */
const WORKER_LOG_TAIL_MAX = 256 * 1024;

/** Last non-empty worker.log line, or undefined. The needs-clarification
 * fallback for tasks that never wrote an output.md (claude/codex workers,
 * old bundles) — their last logged line names what they were asking about. */
export function readWorkerLogTail(taskDir: string): string | undefined {
	try {
		const stat = fs.statSync(path.join(taskDir, "worker.log"));
		if (stat.size > WORKER_LOG_TAIL_MAX) return undefined;
		const lines = fs.readFileSync(path.join(taskDir, "worker.log"), "utf8").split("\n");
		for (let i = lines.length - 1; i >= 0; i--) {
			const line = lines[i].trim();
			if (line !== "") return line;
		}
		return undefined;
	} catch {
		return undefined;
	}
}

/** First non-empty line of a section body, trimmed, leading markdown
 * markers stripped so terminal details never start with `#`/`**`/`- `/`> `
 * (AC-007). Mirrors HEADLINE_MARKER_RE in worker/output-writer. */
const DETAIL_MARKER_RE = /^(?:#{1,6}\s+|\*\*|[-*]\s+|>\s+)/;

function firstLine(body: string | undefined): string | undefined {
	let line = body?.split("\n")[0]?.trim() ?? "";
	while (DETAIL_MARKER_RE.test(line)) {
		line = line.replace(DETAIL_MARKER_RE, "").trim();
	}
	return line === "" ? undefined : line;
}

/** Widget detail line for a terminal worker row (D-004): the glyph/status
 * says what happened, this says why it stuck or what it concluded.
 *  - failed: spawn-failure reason (launcher prefix stripped, timestamp-free)
 *    ?? `## Exit Reason` first line
 *  - needs-clarification: `## Questions` first line ?? worker.log tail ??
 *    explicit no-output hint (claude/codex tasks write no output.md at all)
 *  - lost (D-022/T-20): the run's process is gone with no verified outcome —
 *    same evidence ladder as a failure (Exit Reason, then the log tail), so the
 *    PM reads the scene instead of a synthesized conclusion
 *  - done: `## TL;DR` first line ?? `## Summary` first line (old output.md
 *    files). AC-010: the LAST non-placeholder TL;DR/Summary block, not the
 *    first — append-only multi-run files lead with crash placeholders.
 * Returns "" when nothing informative exists (caller renders the key only).
 * Line-width truncation stays with the caller (WATCH_LINE_MAX). */
export function readTerminalDetail(taskDir: string, status: WorkerStatus): string {
	if (status === "failed") {
		const spawn = readSpawnFailure(taskDir);
		if (spawn !== undefined) {
			const reason = spawn.match(/^\[launcher\] spawn failed \([^)]*\):\s*(.*)$/);
			return (reason?.[1] ?? spawn).trim();
		}
		return firstLine(readLastProductSectionBody(taskDir, ["Exit Reason"])) ?? "";
	}
	if (status === "needs-clarification") {
		return (
			firstLine(readLastProductSectionBody(taskDir, ["Questions"])) ?? readWorkerLogTail(taskDir) ?? "no output.md"
		);
	}
	if (status === "lost") {
		return (
			firstLine(readLastProductSectionBody(taskDir, ["Exit Reason"])) ??
			readWorkerLogTail(taskDir) ??
			"run lost: process gone, outcome unverified — inspect the task dir"
		);
	}
	if (status === "done") {
		// AC-010: last non-placeholder block, same placeholder oracle as
		// hasDeliverableEvidence (contract C5) — a first-match here would show the
		// leading crash stub of an append-only multi-run output.md.
		return firstLine(readLastProductSectionBody(taskDir, ["TL;DR", "Summary"])) ?? "";
	}
	return "";
}

/** Terminal worker statuses (queue semantics; mirrors pm-orchestrator's
 * isTerminal — shared by the ack validation path). `lost` is terminal for the
 * ledger (the run is over) while still being unhandled until acked: it must be
 * absorbed, never re-run (D-022). */
function isTerminalStatus(status: WorkerStatus): boolean {
	return status === "done" || status === "failed" || status === "needs-clarification" || status === "lost";
}

/** Statuses that stay in the widget's unhandled section until the PM acks them
 * (D-002/D-022): everything terminal except a clean `done`. */
function isUnhandledStatus(status: WorkerStatus): boolean {
	return status === "failed" || status === "needs-clarification" || status === "lost";
}

/** Shared ack validation + write path behind /mw ack and the ack_worker_result
 * tool (D-002). `"all"` expands to every terminal row not yet acked;
 * individual keys must reference an existing terminal row — running/pending
 * rows are rejected and nothing is written for them (AC-004).
 *
 * `scope` (mw-task-scope-isolation) narrows the write path to this window: the
 * ack sidecar is a PROJECT-level file, so without it any window could ack (and
 * silently clear) another window's unhandled rows. When given, `"all"` only
 * covers rows this window owns and an explicit foreign key is rejected with the
 * owning key. Omitted = unscoped (callers that are not a PM window). */
export async function ackTasks(
	workerStore: WorkerStore,
	ackStore: AckStore,
	targets: string[] | "all",
	scope?: { watch: PmWatchState; agenticdocRoot: string },
): Promise<{ acked: string[]; rejected: Array<{ key: string; reason: string }> }> {
	const entries = workerStore.readAll();
	const owns = (e: WorkerEntry): boolean =>
		scope === undefined || ownedByThisWindow(e, scope.watch, scope.agenticdocRoot);
	if (targets === "all") {
		const alreadyAcked = new Set(ackStore.readAll().keys());
		const keys = entries
			.filter((e) => owns(e) && isTerminalStatus(e.status) && !alreadyAcked.has(e.taskKey))
			.map((e) => e.taskKey);
		if (keys.length === 0) return { acked: [], rejected: [] };
		return { acked: (await ackStore.ack(keys)).acked, rejected: [] };
	}
	const byKey = new Map(entries.map((e) => [e.taskKey, e]));
	const acked: string[] = [];
	const rejected: Array<{ key: string; reason: string }> = [];
	for (const key of targets) {
		const entry = byKey.get(key);
		if (entry === undefined) {
			rejected.push({ key, reason: "no such task in the worker queue" });
		} else if (!isTerminalStatus(entry.status)) {
			rejected.push({
				key,
				reason: `not terminal (status: ${entry.status}) — only done/failed/needs-clarification/lost rows can be acked`,
			});
		} else if (!owns(entry)) {
			const owner = scope === undefined ? "?" : ownerKeyOf(entry, scope.agenticdocRoot);
			const mine = scope?.watch.key ?? "(none)";
			rejected.push({
				key,
				reason:
					`owned by key '${owner}' — this window owns '${mine}'; ` +
					`run /pm-key switch ${owner} to align, or ack it from the window that dispatched it`,
			});
		} else {
			acked.push(key);
		}
	}
	const written = acked.length > 0 ? await ackStore.ack(acked) : { acked: [], rejected: [] };
	return { acked: written.acked, rejected };
}

/** Live bottom-widget lines for the watched key, in three sections (D-003):
 *  1. live — running then pending, all shown, never folded
 *  2. unhandled — failed/needs-clarification rows the PM has not acked
 *     (/mw ack), all shown, never folded; header carries the count
 *  3. history — done rows ∪ acked terminal rows, newest-first, capped at
 *     WATCH_HISTORY_MAX with a `+N more` fold line
 * Terminal-row details come from readTerminalDetail (D-004).
 * `extraTaskKeys` (mw-worker-visibility-gate D-105) optionally names tasks
 * THIS window dispatched that landed under a different key: they render as
 * ONE aggregate tail line (`  ~ N elsewhere: …`, D-106) instead of rows, so
 * cross-key work stays visible without drowning the panel. Omitted or empty
 * keeps the output identical to the pre-aggregate panel (AC-007). */
export function renderWatchLines(
	indexStore: IndexStore,
	workerStore: WorkerStore,
	ackStore: AckStore,
	agenticdocRoot: string,
	key: string,
	extraTaskKeys?: ReadonlySet<string>,
): string[] {
	const counts: Record<WorkerStatus, number> = {
		pending: 0,
		running: 0,
		done: 0,
		failed: 0,
		"needs-clarification": 0,
		lost: 0,
	};
	const acked = new Set(ackStore.readAll().keys());
	// One queue read shared by the own-key rows and the cross-key aggregate —
	// the aggregate must not add a second full readAll() (§9).
	const all = workerStore.readAll();
	const owned = all.filter((e) => ownerKeyOf(e, agenticdocRoot) === key);
	const aggregate = elsewhereAggregateLine(all, extraTaskKeys, key, agenticdocRoot);
	for (const e of owned) counts[e.status]++;
	// Unhandled = terminal-but-not-done rows not yet acked — the PM's explicit
	// to-do list; ack moves a row out of this section into history.
	const unhandled = owned.filter((e) => isUnhandledStatus(e.status) && !acked.has(e.taskKey));

	const idx = indexStore.findByKey(key);
	const phase = idx
		? `phase=${idx.phase}`
		: key === SCRATCH_WORKERS_KEY
			? "manual tasks"
			: "key not in _index.parallel";
	const badge = key === SCRATCH_WORKERS_KEY ? undefined : formatDocsBadge(readPhaseDocs(agenticdocRoot, key));
	const parts: string[] = [];
	if (counts.running > 0) parts.push(`${counts.running} running`);
	if (counts.pending > 0) parts.push(`${counts.pending} pending`);
	if (counts.done > 0) parts.push(`${counts.done} done`);
	if (counts.failed > 0) parts.push(`${counts.failed} failed`);
	if (counts["needs-clarification"] > 0) parts.push(`${counts["needs-clarification"]} needs-clarification`);
	if (counts.lost > 0) parts.push(`${counts.lost} lost`);
	if (unhandled.length > 0) parts.push(`${unhandled.length} unhandled`);
	const header = `[mw] ${key} | ${phase}${badge ? ` | docs ${badge}` : ""} | ${
		parts.length > 0 ? parts.join(" / ") : "no workers"
	}`;

	if (owned.length === 0) {
		return aggregate === undefined ? [header, "  (no worker tasks)"] : [header, "  (no worker tasks)", aggregate];
	}

	// One rendered row per entry; detail per status (live heartbeat vs D-04
	// terminal sources). Width truncation is uniform (WATCH_LINE_MAX).
	// D-116: every row carries the worker's model in a [id] badge — running
	// and terminal rows read the pi-resolved id from trace.log [START]
	// (launcher defaults included); pending rows fall back to the dispatch-time
	// override from the queue row (no trace.log yet).
	const rowLine = (e: WorkerEntry): string => {
		let detail = "";
		let model = "";
		if (e.status === "running") {
			// Heartbeat-derived live progress (design D-008): phase counter + age
			// of the last [HEARTBEAT] line, refreshed on every poll tick. Old
			// bundles without heartbeats get a visible (no-hb) placeholder.
			// [START] adds elapsed runtime ("up 6m") and the last [TOOL] line
			// names what the worker is currently doing.
			const prog = readTaskProgress(path.dirname(e.taskPath));
			model = prog?.model ?? "";
			const hb = prog?.heartbeat;
			if (hb) {
				const ph = hb.phase === "-" ? "ph -" : `ph ${hb.phase}/${hb.phaseTotal}`;
				const up = prog?.elapsedMs !== undefined ? ` up ${formatHeartbeatAge(prog.elapsedMs)}` : "";
				const stale = hb.ageMs > HEARTBEAT_STALE_MS ? " STALE" : "";
				detail = `${ph}${up} hb ${formatHeartbeatAge(hb.ageMs)}${stale}`;
			} else {
				detail = "(no-hb)";
			}
			// Convergence checkpoint badge (AC-005): past the checkpoint time the
			// running line carries the machine risk verdict — the PM's divergence
			// radar at a glance. Non-low risks get a warning glyph.
			const ck = prog?.checkpoint;
			if (ck) {
				detail += ` ck${Math.round(ck.elapsedS / 60)}m${ck.risk !== "low" ? ` ${ck.risk}⚠` : ""}`;
			}
			if (prog?.lastAction) detail += ` · ${prog.lastAction}`;
		} else if (e.status === "pending") {
			// Dispatch-time --model override; the effective id lands in trace.log
			// [START] once the worker spawns.
			model = e.model;
		} else {
			// Terminal detail per status (D-004): spawn reason / Exit Reason /
			// Questions / TL;DR with their fallback chains.
			model = readTaskProgress(path.dirname(e.taskPath))?.model ?? "";
			detail = readTerminalDetail(path.dirname(e.taskPath), e.status);
		}
		const badge = model ? ` [${model}]` : "";
		return trunc(`  ${STATUS_GLYPH[e.status]} ${e.taskKey}${badge}${detail ? ` — ${detail}` : ""}`, WATCH_LINE_MAX);
	};

	const newestFirst = (a: WorkerEntry, b: WorkerEntry): number => (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
	const live = [
		...owned.filter((e) => e.status === "running").sort(newestFirst),
		...owned.filter((e) => e.status === "pending").sort(newestFirst),
	];
	const history = owned.filter((e) => e.status === "done" || acked.has(e.taskKey)).sort(newestFirst);

	const lines = [header];
	for (const e of live) lines.push(rowLine(e));
	for (const e of [...unhandled].sort(newestFirst)) lines.push(rowLine(e));
	for (const e of history.slice(0, WATCH_HISTORY_MAX)) lines.push(rowLine(e));
	if (history.length > WATCH_HISTORY_MAX) lines.push(`  ... +${history.length - WATCH_HISTORY_MAX} more`);
	// The cross-key aggregate is a never-folded tail line (D-106): it rides
	// after the history fold, never inside it.
	if (aggregate !== undefined) lines.push(aggregate);
	return lines;
}

/** Status order inside one owner group of the aggregate line (D-106): the
 * fixed sequence running/pending/done/failed/needs-clarification, only
 * non-zero entries rendered. */
const AGGREGATE_STATUS_ORDER: readonly WorkerStatus[] = [
	"running",
	"pending",
	"done",
	"failed",
	"needs-clarification",
	"lost",
];

/** The single cross-key aggregate line for the watch panel (D-105/D-106):
 * `  ~ <N> elsewhere: <owner>(<c1> running, <c2> failed, …; risk=high:<K>)`.
 *
 * `extraTaskKeys` are the task keys THIS window dispatched; rows among them
 * owned by a DIFFERENT key than the watched one are summarized here instead
 * of rendered as rows (cross-key rows must not be misread as the watched
 * key's own output). Returns undefined when `extraTaskKeys` is omitted or
 * holds no cross-key row — the caller then keeps the pre-aggregate output
 * line for line (AC-007/VC-007).
 *
 * Shape (D-106): one line; owner groups joined with ", " sorted by (row
 * count desc, owner name asc); per group only non-zero statuses in the fixed
 * order; `; risk=high:<K>` appended when K >= 1 of the group's running rows
 * carries a high convergence checkpoint (same readTaskProgress source as the
 * own-key rows). Over-long lines are truncated to WATCH_LINE_MAX like every
 * other panel line. Reuses the caller's single workerStore.readAll() result
 * — no second queue read (§9). */
function elsewhereAggregateLine(
	all: WorkerEntry[],
	extraTaskKeys: ReadonlySet<string> | undefined,
	watchKey: string,
	agenticdocRoot: string,
): string | undefined {
	if (extraTaskKeys === undefined) return undefined;
	const elsewhere = all.filter(
		(e) => extraTaskKeys.has(e.taskKey) === true && ownerKeyOf(e, agenticdocRoot) !== watchKey,
	);
	if (elsewhere.length === 0) return undefined;
	const groups = new Map<string, WorkerEntry[]>();
	for (const e of elsewhere) {
		const owner = ownerKeyOf(e, agenticdocRoot);
		const group = groups.get(owner);
		if (group === undefined) groups.set(owner, [e]);
		else group.push(e);
	}
	const owners = [...groups.keys()].sort((a, b) => {
		const byRows = (groups.get(b)?.length ?? 0) - (groups.get(a)?.length ?? 0);
		return byRows !== 0 ? byRows : a < b ? -1 : a > b ? 1 : 0;
	});
	const parts: string[] = [];
	for (const owner of owners) {
		const group = groups.get(owner) ?? [];
		const counts: Record<WorkerStatus, number> = {
			pending: 0,
			running: 0,
			done: 0,
			failed: 0,
			"needs-clarification": 0,
			lost: 0,
		};
		for (const e of group) counts[e.status]++;
		const countText = AGGREGATE_STATUS_ORDER.filter((s) => counts[s] > 0)
			.map((s) => `${counts[s]} ${s}`)
			.join(", ");
		let highRisk = 0;
		for (const e of group) {
			if (e.status === "running" && readTaskProgress(path.dirname(e.taskPath))?.checkpoint?.risk === "high") {
				highRisk++;
			}
		}
		parts.push(`${owner}(${countText}${highRisk > 0 ? `; risk=high:${highRisk}` : ""})`);
	}
	return trunc(`  ~ ${elsewhere.length} elsewhere: ${parts.join(", ")}`, WATCH_LINE_MAX);
}

/** Render (or clear) the bottom watch widget on a UI-capable context. */
export function setWatchWidget(ctx: ExtensionContext, lines: string[] | undefined): void {
	if (!ctx.hasUI) return;
	// order 10 keeps the watch panel BELOW the autopilot monitor (order 0) in the
	// same belowEditor placement, independent of which poller refreshed last.
	ctx.ui.setWidget(WATCH_WIDGET_KEY, lines, { placement: "belowEditor", order: 10 });
}

/** Render (or clear) the widget via the session_start-captured context.
 * No-op before session start or in headless runs. */
export function applyWatchWidget(ui: PmUiHolder, lines: string[] | undefined): void {
	if (!ui.ctx) return;
	setWatchWidget(ui.ctx, lines);
}

/** Set this window's watched key, persist it in the session file (survives
 * restart/resume), and refresh the bottom widget immediately. `claimed` marks
 * watches that came with a key takeover. */
function setWindowWatch(
	pi: ExtensionAPI,
	watch: PmWatchState,
	refresh: (ctx: ExtensionContext) => void,
	ctx: ExtensionCommandContext,
	key: string | undefined,
	claimed: boolean,
): void {
	watch.key = key;
	pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed });
	refresh(ctx);
}

/** Doc-gate notifier scoped to this window's watched key (AC-011): the scan
 * evaluates gates for every undocumented key (blocking stays global), but a
 * gate event is only BROADCAST here when it is this window's own key — other
 * keys' gates belong to their owning windows. A window watching nothing
 * stays silent. */
export function makeScopedDocGateNotifier(
	pi: ExtensionAPI,
	watch: PmWatchState,
): (key: string, gaps: string[]) => boolean {
	return (key, gaps) => {
		if (!watch.key || key !== watch.key) return false;
		displaySummary(
			pi,
			`[mw] skipped dispatch for '${key}' — missing phase docs: ${gaps.join("; ")}. ` +
				"Generate spec/design + evidence/research notes (agentic-task workflows), or move ad-hoc work under _scratch.",
		);
		return true;
	};
}

export function registerPmKeyCommands(
	pi: ExtensionAPI,
	indexStore: IndexStore,
	watch: PmWatchState,
	refreshWatch: (ctx: ExtensionContext) => void,
	agenticdocRoot: string,
): void {
	pi.registerCommand("pm-key", {
		description: "Manage PM keys: new / switch (take over + watch) / list",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const [sub, ...rest] = args.trim().split(/\s+/);
			const flags = rest.filter((t) => t.startsWith("--"));
			const positional = rest.filter((t) => !t.startsWith("--"));
			const keyName = positional[0] ?? "";
			const force = flags.includes("--force");

			if (sub === "list") {
				const entries = indexStore.readAll();
				if (entries.length === 0) {
					ctx.ui.notify("No keys found.", "info");
					return;
				}
				const table = entries.map((e) => `${e.key} | ${e.status} | ${e.phase} | ${e.claimId}`).join("\n");
				ctx.ui.notify(table, "info");
				return;
			}

			if (sub === "new") {
				if (!keyName) {
					ctx.ui.notify("Usage: /pm-key new <key-name>", "warning");
					return;
				}
				if (indexStore.findByKey(keyName)) {
					ctx.ui.notify(
						`Key '${keyName}' already exists — use /pm-key switch ${keyName} to take it over.`,
						"warning",
					);
					return;
				}
				// Name gate (AC-006): a reserved/illegal name must never be registered,
				// so it is refused here (before the claim) with a readable code.
				const newNameRefusal = keyNameRefusal(keyName);
				if (newNameRefusal) {
					ctx.ui.notify(
						`Key '${keyName}' is refused (${newNameRefusal.code}): ${newNameRefusal.message}.`,
						"warning",
					);
					return;
				}
				// Route through the atomic claim: auto-create + demote other active
				// rows (single-active discipline) in one locked step.
				const result = await takeOverKey(indexStore, keyName, false, agenticdocRoot);
				// Executing a key in this window also watches it (bottom progress widget).
				setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
				ctx.ui.notify(`Created and claimed key: ${keyName} (${result.claimId})`, "info");
				if (result.audit.length > 0) ctx.ui.notify(result.audit.join("\n"), "warning");
				// pm-state.md mirror sync failure is visible but non-fatal (D-108):
				// the claim itself succeeded; the index row stays authoritative.
				const createdSyncWarning = claimSyncWarningText(keyName, result.claimSync);
				if (createdSyncWarning !== "") ctx.ui.notify(createdSyncWarning, "warning");
				return;
			}

			if (sub === "switch") {
				if (!keyName) {
					ctx.ui.notify("Usage: /pm-key switch <key-name> [--force]", "warning");
					return;
				}
				const target = indexStore.findByKey(keyName);
				if (!target) {
					ctx.ui.notify(`Key not found: ${keyName}`, "error");
					return;
				}
				const result = await takeOverKey(indexStore, keyName, force, agenticdocRoot);
				if (!result.ok) {
					if (result.refusal) {
						ctx.ui.notify(
							`Key '${keyName}' is refused (${result.refusal}): reserved framework names and illegal key shapes cannot be claimed.`,
							"warning",
						);
						return;
					}
					ctx.ui.notify(
						`Key '${keyName}' is claimed by another live window (${result.blockedBy}). Use /pm-key switch ${keyName} --force to take it over.`,
						"warning",
					);
					return;
				}
				// Switching keys in this window also switches what it watches.
				setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
				ctx.ui.notify(`Took over key: ${keyName} (claim ${result.claimId})`, "info");
				if (result.audit.length > 0) ctx.ui.notify(result.audit.join("\n"), "warning");
				const switchSyncWarning = claimSyncWarningText(keyName, result.claimSync);
				if (switchSyncWarning !== "") ctx.ui.notify(switchSyncWarning, "warning");
				return;
			}

			ctx.ui.notify("Usage: /pm-key new|switch|list [key-name] [--force]", "warning");
		},
	});
}

/** Insert a session-snapshot section at the top of {key}/pm-state.md's Notes
 * area. Machine-interface lines (- Phase: / - Claim-Id:) are owned by the
 * framework scripts and stay byte-identical: the snapshot is inserted under
 * "## Notes" only, never rewriting the rest of the file (pm-state-guard
 * principle, framework-side write with the same lock protocol as
 * StateManager). Returns the path written. */
export async function writeSessionSnapshot(agenticdocRoot: string, key: string, lines: string[]): Promise<string> {
	const statePath = path.join(agenticdocRoot, key, "pm-state.md");
	const content = fs.existsSync(statePath) ? fs.readFileSync(statePath, "utf8") : `# PM State: ${key}\n\n## Notes\n`;
	const section = [
		`### Session Snapshot — ${new Date().toISOString()} (${windowClaimId()})`,
		...lines.map((l) => (l ? `- ${l}` : "")),
		"",
	].join("\n");
	const NOTES_HEADING = /^## Notes[ \t]*$/m;
	const next = NOTES_HEADING.test(content)
		? content.replace(NOTES_HEADING, `## Notes\n\n${section}`)
		: `${content.trimEnd()}\n\n## Notes\n\n${section}`;
	fs.mkdirSync(path.dirname(statePath), { recursive: true });
	const release = await acquireLock(`${statePath}.lock`);
	try {
		const tmpPath = `${statePath}.tmp`;
		fs.writeFileSync(tmpPath, next, "utf8");
		fs.renameSync(tmpPath, statePath);
	} finally {
		release();
	}
	return statePath;
}

/** /pm-save — persist this window's working context into the watched key's
 * pm-state.md so a restarted pi window (e.g. after a framework rebuild) can
 * pick the work back up. The handler writes the mechanical snapshot (watch
 * key, index row, worker counts, free note) itself; the conversational
 * context (what we are doing, decisions, next steps) can only be summarized
 * by the agent, so the handler asks it to — the user invoked the command, so
 * this is a user-requested action, not a framework-injected nudge. */
export function registerPmSaveCommand(
	pi: ExtensionAPI,
	indexStore: IndexStore,
	workerStore: WorkerStore,
	watch: PmWatchState,
	agenticdocRoot: string,
): void {
	pi.registerCommand("pm-save", {
		description: "Save this window's working context to {watched key}/pm-state.md for restart pickup",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const note = args.trim();
			if (!watch.key) {
				ctx.ui.notify(
					"Not watching any key — /pm-key switch <key> (take over) or /mw-watch <key> (display only) first.",
					"warning",
				);
				return;
			}
			const key = watch.key;
			const row = indexStore.findByKey(key);
			const owned = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot) === key);
			const ORDER = ["pending", "running", "done", "failed", "needs-clarification", "lost"] as const;
			const counts = new Map<string, number>();
			for (const e of owned) counts.set(e.status, (counts.get(e.status) ?? 0) + 1);
			const workerSummary =
				owned.length === 0
					? "no workers"
					: ORDER.filter((s) => counts.get(s))
							.map((s) => `${counts.get(s)} ${s}`)
							.join(" / ");
			const lines = [
				`Watch: ${key} (window ${windowClaimId()})`,
				row
					? `Index: status=${row.status} phase=${row.phase}${row.desc ? ` — ${row.desc}` : ""}`
					: "Index: (not in _index.parallel)",
				`Workers: ${workerSummary}`,
			];
			if (note) lines.push(`Note: ${note}`);
			lines.push("(agent: fill in below — 当前工作脉络 / 关键决策 / 进行中 / 下一步)");
			const statePath = await writeSessionSnapshot(agenticdocRoot, key, lines);
			ctx.ui.notify(
				`Saved session snapshot to ${path.relative(agenticdocRoot, statePath)} — asking the agent to fill in the working context.`,
				"info",
			);
			pi.sendUserMessage(
				`[agent-team-loop] /pm-save：已在 ${key}/pm-state.md 的 Notes 区写入会话快照。请立即把当前对话的上下文状态补全到该快照小节：当前工作脉络、关键决策、进行中的事项、下一步动作。只编辑 ${key}/pm-state.md 的 Notes 区，不要动 - Phase: / - Claim-Id: 机器接口行。写完简短确认。`,
			);
		},
	});
}

/** /mw-watch — toggle this window's bottom progress widget for one key.
 * Display-only observation: no claim is taken. Use /pm-key switch to take
 * over a key while developing it.
 *
 * Usage: /mw-watch <key>   watch a key (widget appears below the editor)
 *        /mw-watch off     stop watching (widget cleared)
 *        /mw-watch         show current watch state
 */
export function registerWatchCommand(
	pi: ExtensionAPI,
	watch: PmWatchState,
	refreshWatch: (ctx: ExtensionContext) => void,
	indexStore: IndexStore,
): void {
	const USAGE = "Usage: /mw-watch <key> | off   (display only — /pm-key switch takes over a key)";
	pi.registerCommand("mw-watch", {
		description: "Show one key's live worker progress in a bottom widget (/mw-watch <key> | off)",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const arg = args.trim();
			if (!arg) {
				ctx.ui.notify(watch.key ? `Watching: ${watch.key}. ${USAGE}` : `Not watching anything. ${USAGE}`, "info");
				return;
			}
			if (arg === "off" || arg === "none") {
				watch.key = undefined;
				pi.appendEntry(WATCH_ENTRY_TYPE, { key: undefined, claimed: false });
				refreshWatch(ctx);
				ctx.ui.notify("Watch disabled — bottom widget cleared.", "info");
				return;
			}
			if (arg !== SCRATCH_WORKERS_KEY && !indexStore.findByKey(arg)) {
				ctx.ui.notify(
					`Key '${arg}' not found in _index.parallel (or use ${SCRATCH_WORKERS_KEY}). ${USAGE}`,
					"warning",
				);
				return;
			}
			setWindowWatch(pi, watch, refreshWatch, ctx, arg, false);
			ctx.ui.notify(`Watching '${arg}' — worker progress shown below the editor.`, "info");
		},
	});
}

export function registerMwTools(pi: ExtensionAPI, projectDir: string): void {
	pi.registerTool({
		name: "mw_status",
		label: "mw_status",
		description:
			"Check whether the multi-worker background service (mw serve) is running. Returns PID if running, or 'not running' if stopped.",
		parameters: Type.Object({}),
		execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
			const s = getMwStatus(projectDir);
			return {
				content: [
					{
						type: "text",
						text: s.running
							? `mw is running (PID ${s.pid}). Workers are being dispatched and monitored.`
							: "mw is not running. Workers will not be dispatched. Use /mw start or ask the user to start it.",
					},
				],
				details: undefined,
			};
		},
	});
}

/** Resolve the task type for one dispatch: an explicit value must be one of
 * DISPATCHABLE_TYPES, an omitted one keeps the legacy cli-derived mapping
 * (pi -> coding, claude -> review, codex -> codex) so pre-existing dispatches
 * stay byte-identical. */
export function resolveDispatchType(
	cli: string,
	requested: string,
): { ok: true; type: string } | { ok: false; message: string } {
	const trimmed = requested.trim();
	if (!trimmed) {
		const legacy = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
		return { ok: true, type: legacy };
	}
	if (!(DISPATCHABLE_TYPES as readonly string[]).includes(trimmed)) {
		return {
			ok: false,
			message: `Invalid type '${trimmed}'. Must be one of: ${DISPATCHABLE_TYPES.join(", ")}.`,
		};
	}
	return { ok: true, type: trimmed };
}

/** Collapse a model-override reason to the single line a task.md frontmatter
 * entry can hold (design D-003). */
function oneLineReason(raw: string): string {
	return raw.replace(/\s*\r?\n\s*/g, " ").trim();
}

/** Current phase of the owner key from its pm-state.md `- Phase:` line, or
 * "" when the owner is `_scratch` / the key has no readable phase. The phase
 * axis (`required = role.require OR phase.require`, T-14) must never be
 * guessed, so an unknown phase writes no `phase:` header at all. pm-state.md is
 * owned by advance_phase.py — read-only here. */
function dispatchPhase(agenticdocRoot: string, ownerKey: string): string {
	if (ownerKey === SCRATCH_WORKERS_KEY) return "";
	return new StateManager(agenticdocRoot, ownerKey).read().phase ?? "";
}

/** Build the task.md frontmatter (type / phase / images / model / model-reason)
 * for one dispatch and the echo line that tells the PM which layer supplies the model
 * (design D-001~D-007). Shared by the dispatch_worker tool and /worker so the
 * two entries can never drift.
 *
 * Refusals (no task file must be written): an unknown model id for a pi route
 * (validateModelValue), and an override of a configured dispatch.yml role
 * default without a reason. */
export function planDispatchFrontmatter(input: {
	cwd: string;
	cli: string;
	provider: string;
	taskType: string;
	/** Owner key's current phase (T-14): non-empty appends `phase: <P>` right
	 * after `type:`; ""/undefined keeps the pre-T-14 bytes unchanged. */
	phase?: string;
	/** Declared image capability (T-05): `"yes"`/`"no"` appends `images: <v>`
	 * right after `phase:` and before `model:`; `undefined` (undeclared) keeps
	 * the pre-T-05 bytes unchanged. */
	images?: "yes" | "no";
	/** Task body, scanned for an image-file reference when `images` is
	 * undeclared (T-06 auto-detection). Optional (T-17): callers that only
	 * exercise the phase/model path omit it, matching `phase?: string`. */
	description?: string;
	model: string;
	modelReason: string;
	registry: ModelRegistry | undefined;
	/** Test seam for the DP-1 child (T-03): production callers omit it and the
	 * triage client spawns the real `mw decide run`. */
	triageRun?: DecideRunner;
	/** T-04d dispatch facts for the dp1 STRUCTURED state (owning key + the
	 * card's write face). Omitted / incomplete falls back to the legacy string
	 * state, and the fallback is traced (`[DECISION] dp1 state=legacy ...`). */
	dp1?: Dp1DispatchFacts;
}): { ok: true; frontmatter: string; echo: string; triage: DispatchTriage | null } | { ok: false; message: string } {
	const role = roleForTaskType(input.taskType);
	const configured = readRoleModel(input.cwd, role) ?? "";
	const requested = input.model.trim();
	const reason = oneLineReason(input.modelReason);
	// Image requirement (T-06, three-state, verbatim precedence): an explicit
	// `images: "no"` short-circuits to "no image" WITHOUT calling the filesystem
	// detector (the exemption is unconditional and must stay cheap); an explicit
	// `images: "yes"` forces the requirement; otherwise the description is
	// scanned for a reference to an existing image file.
	const imagesRequested =
		input.images === "no"
			? false
			: input.images === "yes"
				? true
				: detectImageNeed(input.cwd, input.description ?? "");
	// Write side (D-013): a detected need writes `images: yes` too, so the
	// worker's runtime fallback covers auto-detected tasks.
	const imagesField: "yes" | "no" | undefined = input.images === "no" ? "no" : imagesRequested ? "yes" : undefined;
	const headLines = [`type: ${input.taskType}`];
	if (input.phase !== undefined && input.phase.length > 0) headLines.push(`phase: ${input.phase}`);
	if (imagesField !== undefined) headLines.push(`images: ${imagesField}`);
	const typeLines = `${headLines.join("\n")}\n`;

	// The value that will actually run: an explicit request wins, else the
	// configured role default (which the launcher would pick next). Either way
	// it must name a model the pi route can resolve.
	let effective = requested || configured;
	if (effective) {
		const validation = validateModelValue(input.registry, input.cli, input.provider, effective);
		if (!validation.ok) return { ok: false, message: validation.message };
	}

	// Auto-route (T-07, AC-016/AC-017): an un-pinned task that needs images while
	// its role default is a definite "no" moves to the `vision` role's model when
	// that model is a definite "yes". ONLY the model value moves — `type:` (and
	// with it the worker tool allowlist) is deliberately left untouched (D-004).
	// An explicit `model:` is never rewritten (it walks the capability gate
	// below), and a missing / non-"yes" `vision` value leaves `effective` on the
	// role default so the gate still owns the refusal. Runs BEFORE the gate:
	// otherwise the gate would refuse before routing could take effect.
	let autoRouteSource = "";
	if (!requested && imagesRequested) {
		const roleCapability = modelImageCapability(input.registry, input.cli, input.provider, effective);
		if (roleCapability === "no") {
			const visionValue = readRoleModel(input.cwd, "vision") ?? "";
			if (visionValue && modelImageCapability(input.registry, input.cli, input.provider, visionValue) === "yes") {
				effective = visionValue;
				autoRouteSource = role;
			}
		}
	}

	// Capability gate (T-06, AC-006/AC-008): only a definite "no" refuses, and
	// only when the task really needs images. "unknown" fails open by design —
	// never turn an undecidable registry lookup into a refused dispatch.
	if (imagesRequested) {
		const capability = modelImageCapability(input.registry, input.cli, input.provider, effective);
		if (capability === "no") {
			return {
				ok: false,
				message:
					`Task declares images (or references an image file) but model '${effective}' cannot take image input. ` +
					"Use 'mw model set vision <provider/model>' to configure a vision role, or declare 'images: no' if the task does not need the image.",
			};
		}
	}

	// DP-1 advisory triage (T-03/D-006): computed inside this shared plan point —
	// before any dispatch fs write — and attached to the result. It NEVER mutates
	// the frontmatter/echo below: the default-off path returns null and changes
	// nothing, and the suggestion never rewrites type/role/model/cli.
	// T03: the request carries the card's ORIGINAL goal/requirements/deliverables
	// on the local envelope (`{material, meta}`); identity and the reserved task
	// id ride in `meta` only.
	const triage = computeDispatchTriage({
		projectDir: input.cwd,
		dispatchedType: input.taskType,
		run: input.triageRun,
		dp1: {
			key: input.dp1?.key,
			taskKey: input.dp1?.taskKey,
			taskBefore: input.dp1?.taskBefore,
			taskType: input.taskType,
			sections: input.dp1?.sections,
		},
	});

	// Auto-route result: the vision model is pinned (the role default cannot take
	// image input) and the machine-readable source rides both the task
	// frontmatter (`model-reason`) and the echo (`model-source`). `type:` stays
	// untouched. Checked before the no-override branch below, which would
	// otherwise emit a frontmatter without the routed `model:` line.
	if (autoRouteSource) {
		const routeReason = reason
			? `${reason}; auto-route: ${autoRouteSource} -> vision`
			: `auto-route: ${autoRouteSource} -> vision`;
		const routeLines = [...headLines, `model: ${effective}`, `model-reason: ${routeReason}`];
		return {
			ok: true,
			frontmatter: `${routeLines.join("\n")}\n`,
			echo: `model: dispatch.yml vision=${effective} (model-source: auto-route, ${autoRouteSource} -> vision)`,
			triage,
		};
	}

	if (!requested) {
		return {
			ok: true,
			frontmatter: typeLines,
			echo: configured
				? `model: dispatch.yml ${role}=${configured}`
				: `model: route default (no dispatch.yml ${role} default)`,
			triage,
		};
	}

	// Requested value equals the configured default: leave the line out so the
	// config stays the single source of truth (a later config change applies).
	if (configured && requested === configured) {
		return {
			ok: true,
			frontmatter: typeLines,
			echo: `model: dispatch.yml ${role}=${configured} (requested value matches the configured default; not pinned)`,
			triage,
		};
	}

	if (configured && !reason) {
		return {
			ok: false,
			message:
				`Model override for role '${role}' needs model_reason: dispatch.yml ${role}=${configured}, requested=${requested}. ` +
				"Omit the model to use the configured default, or re-dispatch with model_reason explaining the deviation.",
		};
	}

	const lines = [...headLines];
	if (requested) lines.push(`model: ${requested}`);
	if (reason) lines.push(`model-reason: ${reason}`);
	return {
		ok: true,
		frontmatter: `${lines.join("\n")}\n`,
		echo: configured
			? `model override: role default ${role}=${configured} -> ${requested} (reason: ${reason})`
			: `model: ${requested} (no dispatch.yml ${role} default)`,
		triage,
	};
}

// ── AC-005a: dispatch-time write-surface satisfiability (T-02) ──────────────

/** Paired markers of the dispatch-injected write-surface contract (contract
 * C2, producer T-02 → consumer T-03). The runtime consumer only greps for
 * these markers; the three lines between them are for the worker and PM. */
export const WRITE_SURFACE_MARKER = "<!-- mw-write-surface: v1 -->";
export const WRITE_SURFACE_MARKER_END = "<!-- /mw-write-surface: v1 -->";

/** Machine-readable refusal code for an unsatisfiable write requirement. */
export const WORKER_WRITE_SURFACE = "worker-write-surface";

/** Write verbs a task book can use to order a file write (AC-005a). Exported so
 * the rule is enumerable by the unit matrix and by the corpus replay.
 * `写到文件` before `写到` so the longest form wins. */
export const WRITE_INTENT_VERBS: readonly string[] = [
	"写到文件",
	"写到",
	"写入",
	"落盘",
	"输出到",
	"保存",
	"创建",
	"生成",
	"追加",
	"覆盖",
	"write",
	"save",
	"create",
	"append",
	"output to",
	"into",
];

/** Allow-guards (AC-005a), stable names for the test matrix. A hit matching
 * any guard is a legitimate mention, never an unsatisfiable write order. */
export const WRITE_INTENT_GUARDS: readonly string[] = [
	"negation",
	"read-marker",
	"fenced-code",
	"quotation",
	"pm-attribution",
];

/** Upper bound (chars) between a write verb and its path. The matcher is
 * deliberately stricter: only whitespace and at most one quote may separate
 * the two, which is what keeps prose like "追加而非重写 achieved.md" out while
 * still satisfying the ≤32 bound. */
export const WRITE_INTENT_PATH_WINDOW = 32;

/** Framework-owned basenames: naming one means "the framework already provides
 * this channel" (reply text lands in output.md), not an external write order. */
const FRAMEWORK_TASK_BASENAMES: readonly string[] = ["task.md", "trace.log", "output.md", "run.json", "worker.log"];

const WRITE_INTENT_NEGATIONS: readonly string[] = [
	"不要",
	"不得",
	"禁止",
	"勿",
	"无需",
	"不准",
	"do not",
	"don't",
	"never",
	"must not",
];
const WRITE_INTENT_READ_MARKERS: readonly string[] = [
	"读取",
	"作为输入",
	"参考",
	"输入",
	"引用",
	"依据",
	"来源",
	"现有",
	"已有",
	"核对",
	"扫描",
	"以…为输入",
	"read",
	"rg",
	"grep",
	"current",
	"existing",
	"input",
	"from",
];
const WRITE_INTENT_PM_ATTRIBUTIONS: readonly string[] = ["pm 会", "由 pm", "pm 收录", "框架会", "交给 pm", "pm 将在"];
const WRITE_INTENT_QUOTE_PAIRS: ReadonlyArray<readonly [string, string]> = [
	['"', '"'],
	["'", "'"],
	["「", "」"],
];
const WRITE_INTENT_ENGLISH_VERBS = new Set(["write", "save", "create", "append", "output to", "into"]);

/** Anchored token after a write verb (A3 fix, AC-004): a wide character class
 * with NO extension enumeration — the shape judge below decides whether a
 * candidate is a path. New languages/config types cannot re-open the leak. */
const WRITE_INTENT_TOKEN_RE = /^[A-Za-z0-9_.\\/~:-]+/;

const WRITE_SURFACE_SECTION_RE = new RegExp(
	`${WRITE_SURFACE_MARKER.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[\\s\\S]*?${WRITE_SURFACE_MARKER_END.replace(
		/[.*+?^${}()|[\]\\]/g,
		"\\$&",
	)}\n*`,
	"g",
);

export interface WriteIntentHit {
	verb: string;
	path: string;
	clause: string;
}

/** Verdict of the target axis (AC-003/AC-004). `rule` exists only when
 * allowed=false: `deny` = the deny prefix table fired, `scope` = a path-shaped
 * target outside the write surface. */
export interface WriteTargetJudge {
	allowed: boolean;
	shape: WriteTargetShape;
	rule?: "deny" | "scope";
	detail?: string;
}

/** Write-surface context for judgeWriteTarget (AC-003/AC-004). `keyDir` and
 * `trueRoot` activate the deny prefix table (same table as worker-mode.ts);
 * omitted, only containment + shape evaluation run. */
export interface PmWriteSurfaceCtx {
	taskDir: string;
	projectRoot: string;
	keyDir?: string;
	trueRoot?: string;
}

/** Find `verb` in `clause`; English verbs match on word boundaries so
 * `output-writer.ts` never reads as a `write` order. */
function findWriteIntentVerb(clause: string, verb: string): number {
	const low = clause.toLowerCase();
	const needle = verb.toLowerCase();
	if (WRITE_INTENT_ENGLISH_VERBS.has(needle)) {
		const re = new RegExp(`(?<![A-Za-z0-9_])${needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![A-Za-z0-9_])`);
		const m = re.exec(low);
		return m ? m.index : -1;
	}
	return low.indexOf(needle);
}

/** Is `pathToken` inside a quotation span (guard ④)? */
function pathInsideQuotation(clause: string, pathToken: string): boolean {
	const at = clause.indexOf(pathToken);
	if (at === -1) return false;
	for (const [open, close] of WRITE_INTENT_QUOTE_PAIRS) {
		let start = clause.indexOf(open);
		while (start !== -1 && start < at) {
			const end = clause.indexOf(close, start + 1);
			if (end === -1) break;
			if (at > start && at + pathToken.length <= end) return true;
			start = clause.indexOf(open, start + 1);
		}
	}
	return false;
}

/** Write-intent hits that survive the five allow-guards (AC-005a). Pure over
 * text so the corpus replay and the unit cases share one implementation.
 *
 * HTML comments are stripped structurally (AC-010 / C-29) before any verb or
 * token matching: the framework's own injected markers
 * (`<!-- mw-write-surface: v1 -->` / `<!-- /mw-write-surface: v1 -->`) contain
 * the English verb `write`, whose anchored token scan would otherwise read
 * `-surface:` as a colon-shaped target and refuse the producer's honest
 * artifact. Stripping the whole comment span (inline and multi-line) removes
 * every comment-borne mention — never a marker-name special case. */
export function collectWriteIntentHits(text: string): WriteIntentHit[] {
	const body = text.replace(/<!--[\s\S]*?-->/g, "").replace(/```[\s\S]*?```/g, "");
	const hits: WriteIntentHit[] = [];
	for (const line of body.split(/\r?\n/)) {
		for (const clause of line.split(/[。；！？;]/)) {
			const low = clause.toLowerCase();
			for (const verb of WRITE_INTENT_VERBS) {
				const pos = findWriteIntentVerb(clause, verb);
				if (pos < 0) continue;
				const after = clause.slice(pos + verb.length);
				const gap = /^\s*[`"']?\s*/.exec(after);
				const gapLen = gap ? gap[0].length : 0;
				if (gapLen > WRITE_INTENT_PATH_WINDOW) continue;
				// Anchored token discovery (A3 fix, AC-004): no extension enumeration and
				// no `pm.index !== 0` discard branch. A non-matching token means only
				// that this verb has no candidate in this clause — never that the whole
				// clause is abandoned, and never a forward scan into later prose.
				const pm = WRITE_INTENT_TOKEN_RE.exec(after.slice(gapLen));
				if (pm === null) continue;
				const pathToken = pm[0].replace(/[.]+$/, "");
				if (pathToken === "") continue;
				const before = low.slice(Math.max(0, pos - 20), pos);
				if (WRITE_INTENT_NEGATIONS.some((n) => before.includes(n))) continue;
				if (WRITE_INTENT_READ_MARKERS.some((r) => low.includes(r))) continue;
				if (WRITE_INTENT_PM_ATTRIBUTIONS.some((a) => low.includes(a))) continue;
				if (pathInsideQuotation(clause, pathToken)) continue;
				hits.push({ verb, path: pathToken, clause: clause.trim() });
				break;
			}
		}
	}
	return hits;
}

/** Verdict of the target axis delegated to the shared write-surface predicate
 * (`shared/write-surface.ts::judgeWriteTarget`, design §3; AC-016). This
 * adapter only adds the two PM-only channels the predicate does not own: the
 * framework basenames (`task.md`/`trace.log`/`output.md`/`run.json`/
 * `worker.log`, which the framework itself writes) and the `WriteTargetJudge`
 * shape/rule vocabulary. Evaluation order matches the historical one:
 *   1. deny prefixes + own task dir + own-key `<key>/evidence/**` + worker_file
 *      basenames + path-shape refusal — all from the shared predicate
 *   2. framework basenames — PM prose channel only
 *   3. non-candidate prose => pass untouched
 * The `!hasDirComponent` precondition (not `shape === "bare"`) is load-bearing:
 * `output.md`/`report.md` are `ext`-shaped and must still use the channel. */
export function judgeWriteTarget(pathToken: string, ctx: PmWriteSurfaceCtx): WriteTargetJudge {
	const shape = classifyWriteTargetShape(pathToken, ctx);
	const verdict = judgeSharedWriteTarget(pathToken, ctx);
	if (verdict.allowed) return { allowed: true, shape };
	if (verdict.rule === "deny") return { allowed: false, shape, rule: "deny", detail: verdict.detail };
	const hasDirComponent = /[\\/]/.test(pathToken);
	if (!hasDirComponent && (WORKER_FILE_NAME_RE.test(pathToken) || FRAMEWORK_TASK_BASENAMES.includes(pathToken))) {
		return { allowed: true, shape };
	}
	return { allowed: false, shape, rule: "scope", detail: verdict.detail ?? "outside-write-surface" };
}

/** Boolean wrapper of {@link judgeWriteTarget} (AC-003/AC-004): may this role
 * legitimately write `pathToken`? */
export function isWhitelistedWriteTarget(pathToken: string, ctx: PmWriteSurfaceCtx): boolean {
	return judgeWriteTarget(pathToken, ctx).allowed;
}

export interface WriteIntentVerdict {
	ok: boolean;
	/** Guard-surviving hits, before the whitelist (AC-005a corpus metric). */
	hits: WriteIntentHit[];
	/** Hits whose target the role cannot reach (the refusal set). */
	violations: WriteIntentHit[];
}

/** Judgement entry point: only a writeless role without a shell is judged — a
 * write role passes untouched, a shell role (`research`) is handled by the
 * AC-005b runtime guard instead. `allowForeignWrite` is the escape hatch. */
export function judgeWriteIntent(input: {
	type: string;
	description: string;
	taskDir: string;
	projectRoot: string;
	allowForeignWrite?: boolean;
	/** Own key dir (`.agenticdoc/<key>`); activates the deny prefix table. */
	keyDir?: string;
	/** TRUE `.agenticdoc` root; activates the deny prefix table. */
	trueRoot?: string;
}): WriteIntentVerdict {
	if (!isWritelessRole(input.type) || isShellRole(input.type)) return { ok: true, hits: [], violations: [] };
	const hits = collectWriteIntentHits(input.description);
	const ctx: PmWriteSurfaceCtx = {
		taskDir: input.taskDir,
		projectRoot: input.projectRoot,
		keyDir: input.keyDir,
		trueRoot: input.trueRoot,
	};
	const violations = input.allowForeignWrite ? [] : hits.filter((hit) => !isWhitelistedWriteTarget(hit.path, ctx));
	return { ok: violations.length === 0, hits, violations };
}

/** Refusal text for an unsatisfiable write order (AC-005a): names the code, the
 * role, the path, and the three ways forward. */
export function writeIntentRefusal(input: { taskKey: string; type: string; path: string }): string {
	return (
		`[${WORKER_WRITE_SURFACE}] task '${input.taskKey}' has type '${input.type}', which has no write/edit/bash tool, ` +
		`but its task book requires writing to '${input.path}' — unsatisfiable for this role.\n` +
		"Fix (pick one):\n" +
		'1. Put the deliverable in the task\'s own dir: worker_file file="report.md" (progress.md / report-<slug>.md also work); the PM collects it afterwards.\n' +
		"2. Re-dispatch with allow_foreign_write: true — recorded in task.md frontmatter (allow_foreign_write: true) for audit; use it only when a human accepted the external path.\n" +
		"3. Use a role with write tools: type: coding | repair | vision."
	);
}

/** Default `write_scope:` line for a shell role (contract C1): the task's own
 * dir plus the key's evidence tree. Absent for non-shell roles. */
export function renderDefaultWriteScope(ownerKey: string, taskKey: string): string {
	return `write_scope: .agenticdoc/${ownerKey}/workers/${taskKey}, .agenticdoc/${ownerKey}/evidence`;
}

/** The injected 3-line contract section (contract C2), marker-paired. */
export function renderWriteSurfaceContract(type: string, writeScope: string | undefined): string {
	const scope = (writeScope ?? "").trim().replace(/^write_scope:\s*/, "");
	const allowed = scope
		? `本任务目录下的 worker_file（progress.md | report.md | report-<slug>.md）；write_scope: ${scope}`
		: "本任务目录下的 worker_file（progress.md | report.md | report-<slug>.md）";
	const denied =
		"本任务目录之外的任何路径（pm-state.md、workers/_workers*、_index.parallel、其他 key、packages/**、.git/**）";
	const consequence = isShellRole(type)
		? "运行期 bash 写面守卫 block + [TOOL_ERR] + trace 审计行"
		: "运行期写面守卫拒绝；回复文本仍会被框架写入 output.md";
	return [
		WRITE_SURFACE_MARKER,
		`- 允许写：${allowed}`,
		`- 不得写：${denied}`,
		`- 越界后果：${consequence}`,
		WRITE_SURFACE_MARKER_END,
	].join("\n");
}

/** Idempotent contract-section application (contract C2, VC-019): any existing
 * marker region is removed, then the canonical section is inserted right after
 * the leading frontmatter block. Applying it twice is a byte-level fixed point
 * and leaves exactly one marker pair. */
export function applyWriteSurfaceContract(taskMdText: string, type: string, writeScope: string | undefined): string {
	const section = renderWriteSurfaceContract(type, writeScope);
	const cleaned = taskMdText.replace(WRITE_SURFACE_SECTION_RE, "");
	const blank = cleaned.search(/\n\s*\n/);
	if (blank === -1) return `${section}\n\n${cleaned}`;
	const head = cleaned.slice(0, blank).replace(/\n+$/, "");
	const rest = cleaned.slice(blank).replace(/^\n+/, "");
	return `${head}\n\n${section}\n\n${rest}`;
}

/** Merge the claims-derived `read_scope:` head block (T-02, design §4). Same
 * carrier as the Python renderer (`dispatch.py::render_task_md`): a YAML block
 * list of scope entries, then the two scalar caps, in that fixed order. `
 * `readScope` absent/empty writes NOTHING at all: `read_scope:` is what turns
 * the worker's read interceptor on (`worker/read-scope.ts`), so a card without
 * a claims block must keep both its bytes and its interception behaviour
 * (AC-007). A cap is rendered only when it is a positive number, so a partially
 * derived pair still yields the exact field order. */
function mergeReadScope(
	frontmatter: string,
	readScope: string[] | undefined,
	fileCap: number | undefined,
	byteCap: number | undefined,
): string {
	const items = (readScope ?? []).map((item) => item.trim()).filter((item) => item !== "");
	if (items.length === 0) return frontmatter;
	const lines = ["read_scope:", ...items.map((item) => `  - ${item}`)];
	if (fileCap !== undefined && Number.isFinite(fileCap) && fileCap > 0) {
		lines.push(`l2_read_file_cap: ${Math.trunc(fileCap)}`);
	}
	if (byteCap !== undefined && Number.isFinite(byteCap) && byteCap > 0) {
		lines.push(`l2_read_byte_cap: ${Math.trunc(byteCap)}`);
	}
	return `${frontmatter.replace(/\r?\n$/, "")}\n${lines.join("\n")}\n`;
}

/** Merge the audit-visible escape-hatch line (AC-005a) into frontmatter. */
function mergeAllowForeignWrite(frontmatter: string, allowed: boolean | undefined): string {
	if (!allowed || /^allow_foreign_write:/m.test(frontmatter)) return frontmatter;
	return `${frontmatter.replace(/\r?\n$/, "")}\nallow_foreign_write: true\n`;
}

/** Append a rendered `write_scope:` line to planned frontmatter (contract
 * C1/C4). Same shape as the existing `read_scope:`/`deny_globs:` headers — one
 * line, never an empty value: undefined/blank scope leaves the frontmatter
 * bytes untouched. */
function mergeWriteScope(frontmatter: string, writeScope: string | undefined): string {
	const line = (writeScope ?? "").trim();
	if (!line) return frontmatter;
	return `${frontmatter.replace(/\r?\n$/, "")}\n${line}\n`;
}

// ── Decision correlation header (T-08 / spec §6.1, design D-012) ────────────

/** The decision that authorized this dispatch, carried into task.md as the
 * `decision:` head line. `decision_id` is `"<dp>:<trigger_id>"` (spec §6.1);
 * the PM settle path reverse-looks it up from the task file, so the line is the
 * ONLY link between a run and the decision it executes. */
export interface DispatchDecision {
	decisionId: string;
	/** Only an acted decision authorizes the dispatch (AC-015): a `suggest`
	 * answer is archived with `acted=false` and must never be settled against
	 * this task, so it never gets a head line. */
	acted: boolean;
}

/** `<dp>:<trigger_id>` — dp ids are kebab-case registry ids, trigger ids are
 * task keys / `task_key#ckpt<N>` / ISO stamps (design D-023: the trigger may
 * contain `:`, the split is on the FIRST one). Anchored so a free-text value
 * can never be written into the machine-readable header. */
const DECISION_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]*:\S+$/;

/** Merge the `decision:` correlation line into the frontmatter at the END of
 * the merge chain (last head line before the body). `acted`-gated by contract:
 * `suggest` advice, a missing decision and a malformed `decision_id` all leave
 * the frontmatter bytes untouched (a broken correlation key is never written;
 * settle then treats the task as un-associated instead of guessing). */
export function mergeDecisionHeader(frontmatter: string, decision: DispatchDecision | undefined): string {
	if (!decision?.acted) return frontmatter;
	const decisionId = decision.decisionId.trim();
	if (!DECISION_ID_RE.test(decisionId)) return frontmatter;
	if (/^decision:/m.test(frontmatter)) return frontmatter;
	return `${frontmatter.replace(/\r?\n$/, "")}\ndecision: ${decisionId}\n`;
}

// ── Dispatch-card envelope injection (T-02, contract C3) ────────────────────

/** Machine-readable refusal code for a missing/incomplete dispatch card. */
export const DISPATCH_CARD_CODE = "dispatch-card";

/** Machine-readable refusal code for a card whose claims block cannot be used
 * (T-02, design §3.2). Deliberately NOT `dispatch-card`: `card_audit` and the
 * PM read the code to tell an incomplete envelope apart from a declared-but-
 * unusable claims table. */
export const DISPATCH_CLAIMS_CODE = "dispatch-claims";

/** One of the two refusal codes {@link dispatchCardRefusal} renders. */
export type DispatchCardRefusalCode = typeof DISPATCH_CARD_CODE | typeof DISPATCH_CLAIMS_CODE;

/** Claims-gate mode (D-006 grey release): the calibrated default from
 * `shared/dispatch-card.ts`, upgraded to `enforce` by `MW_CLAIM_GATE`. */
export type ClaimGateMode = typeof CLAIM_GATE_DEFAULT | "enforce";

/**
 * Runtime claims-gate mode (T-02 requirement 4, D-006): `MW_CLAIM_GATE`
 * overrides {@link CLAIM_GATE_DEFAULT}. The name and the two values are the
 * same on both sides of the TS/Python pair (`dispatch.py::claim_gate`), so a
 * grey release flips one env var. An unknown/blank value falls back to the
 * default instead of blocking a dispatch: the gate is opt-in, and a typo must
 * neither silently enforce nor stall the loop (same fail-open rule as the
 * Python side).
 */
export function claimGateMode(): ClaimGateMode {
	const raw = (process.env.MW_CLAIM_GATE ?? CLAIM_GATE_DEFAULT).trim().toLowerCase();
	return raw === "enforce" ? "enforce" : CLAIM_GATE_DEFAULT;
}

/** The `read_scope:` entries of one claims-backed dispatch (T-02, design §4):
 * the owner key's own tree, the project goal anchor (the pair the key's
 * conductor dispatches already carry), and — the part a claim-driven review
 * cannot do without — the files the claims point at. A locator names the file
 * the claim is about (optionally with a `:line` / `:a-b` span suffix), so the
 * scope is exactly "the claims plus their anchors": the worker reads what it
 * must falsify and nothing else, which is the whole point of pricing a review
 * by claims instead of by repo size. Absolute paths and `..` escapes are
 * dropped, so a card cannot widen its own scope out of the project root.
 * Rendered only when the card declares claims, because `read_scope:` switches
 * the worker's read interceptor on. */
export function claimReadScope(ownerKey: string, claims: Claim[]): string[] {
	const scope = [`.agenticdoc/${ownerKey}`, ".agenticdoc/goal.md"];
	const seen = new Set(scope.map((entry) => entry.toLowerCase()));
	for (const claim of claims) {
		const entry = claim.locator
			.trim()
			.replace(/:\d+(?:-\d+)?$/, "")
			// D-005 writes a `cmd` locator as `evidence/claims/<file>#<claim-id>`; the
			// fragment names the row inside the file, not a path of its own.
			.replace(/#.*$/, "")
			.replaceAll("\\", "/")
			.replace(/^\.\//, "");
		if (entry === "" || path.isAbsolute(entry) || entry.split("/").includes("..")) continue;
		if (seen.has(entry.toLowerCase())) continue;
		seen.add(entry.toLowerCase());
		scope.push(entry);
	}
	return scope;
}

/** Markers of the card's claims block (design §2.1); the injected copy keeps
 * them verbatim so the settle path can re-parse `task.md` without the card
 * (D-002). */
const CLAIMS_OPEN_RE = /^<!--\s*mw-claims\s*:\s*v1\s*-->$/i;
const CLAIMS_CLOSE_RE = /^<!--\s*\/\s*mw-claims\s*-->$/i;
const CLAIMS_STOP_H2_RE = /^##(?!#)\s+/;
const CLAIMS_FENCE_RE = /^(`{3,}|~{3,})(.*)$/;
const CLAIMS_BLOCK_CLOSE = "<!-- /mw-claims -->";

/**
 * LF-normalized lines of `text` plus the `[start, end)` line range of the card's
 * `<!-- mw-claims: v1 -->` block; `start = -1` when the card has none. The
 * range follows the shared parser's fence/H2 semantics: an unterminated block
 * ends at the next H2 or EOF (`end` is exclusive either way).
 */
function claimsBlockRange(text: string): { lines: string[]; start: number; end: number } {
	const lines = text.replace(/\r\n?/g, "\n").split("\n");
	let fence: { char: string; len: number } | undefined;
	let start = -1;
	for (let i = 0; i < lines.length; i++) {
		const line = lines[i] ?? "";
		const fenceMatch = CLAIMS_FENCE_RE.exec(line);
		if (fenceMatch !== null) {
			const marker = fenceMatch[1] ?? "";
			const rest = fenceMatch[2] ?? "";
			const char = marker[0] ?? "";
			if (fence === undefined) fence = { char, len: marker.length };
			else if (char === fence.char && marker.length >= fence.len && rest.trim() === "") fence = undefined;
			continue;
		}
		if (fence !== undefined) continue;
		if (start < 0) {
			if (CLAIMS_OPEN_RE.test(line)) start = i;
			continue;
		}
		if (CLAIMS_CLOSE_RE.test(line)) return { lines, start, end: i + 1 };
		if (CLAIMS_STOP_H2_RE.test(line)) return { lines, start, end: i };
	}
	return { lines, start, end: start < 0 ? -1 : lines.length };
}

/**
 * Verbatim text of the card's `<!-- mw-claims: v1 -->` block (T-02 requirement
 * 2), `""` when the card has none.
 *
 * The card seed only injects heading slices, so an HTML comment block would
 * never reach `task.md` reliably (RQ-2 §2.3) — and the settle layer must read
 * the claims from `task.md`, never from the (mutable) card file (D-002). The
 * slice is taken between the markers with the same fence/H2 semantics as the
 * shared parser; an unterminated block gets the close marker appended, so the
 * injected copy cannot swallow the seed disclaimer or the task body after it.
 */
export function extractClaimsBlockText(text: string): string {
	const { lines, start, end } = claimsBlockRange(text);
	if (start < 0) return "";
	const block = lines.slice(start, end);
	if (block.length === 0 || !CLAIMS_CLOSE_RE.test(block[block.length - 1] ?? "")) block.push(CLAIMS_BLOCK_CLOSE);
	return block.join("\n");
}

/** Card text with the claims block removed (T-02): the block is delivered once,
 * by {@link renderCardSeedSections}, so it must not also ride inside a §1.2
 * extra body (a card that puts it under an H2 would otherwise emit the rows
 * twice and the settle parser would see duplicated claims). */
function stripClaimsBlockText(text: string): string {
	const { lines, start, end } = claimsBlockRange(text);
	if (start < 0) return text;
	return [...lines.slice(0, start), ...lines.slice(end)].join("\n");
}

/** Paired markers around the card-derived body section (idempotent injection,
 * same "strip old region → reinsert" mechanism as the write-surface contract). */
export const CARD_SEED_MARKER = "<!-- mw-dispatch-card: v1 -->";
export const CARD_SEED_MARKER_END = "<!-- /mw-dispatch-card: v1 -->";

/** The mandatory seed disclaimer demanded by design §2.2: the injected card is
 * a seed, never an upper bound on what the worker may read. */
export const CARD_SEED_DISCLAIMER = "以上为种子，不是探索上界；可自行检索补充上下文";

/** One card section the envelope judge does not classify: the §1.2 per-type
 * extras (`写入允许面` / `写入禁止面` / `验收命令` / `改动历史`). Kept so the seed
 * can inject them into the derived task.md (T-12/F-02). */
export interface CardExtraSection {
	title: string;
	body: string;
}

/** The three envelope bodies injected into the generated task.md, plus the
 * card's unclassified sections (the §1.2 type extras) so the derived task.md
 * passes the SAME extras judge the service layer (G-3) runs. */
export interface CardSections {
	context: string;
	requirements: string;
	deliverables: string;
	/** Card sections outside the three envelope families, in document order. */
	extras: CardExtraSection[];
	/** T-02/design §4: the card's claims block, verbatim, injected inside the
	 * seed marker region so the settle layer reads it from `task.md` (D-002).
	 * Absent for a card without a claims block — every pre-claims byte shape
	 * (and the read-interception behaviour) stays unchanged (AC-007). */
	claims?: string;
	/** T-05/AC-003: the card's declared `type:`, set only by {@link readDispatchCard}
	 * (a directly constructed `CardSections` carries no type, so callers keep the
	 * pre-T-05 bytes). It drives the `## 交付段契约（本角色）` checklist in
	 * {@link renderCardSeedSections}. */
	type?: string;
}

const CARD_HEADING_RE = /^(#{2,6})\s+(.*)$/;

/** Strip a leading `1.` / `1.2.` / `(2)` / `A.` / `一、` numbering prefix
 * (same rule as `shared/dispatch-card.ts::stripNumbering`). */
function stripCardHeadingNumbering(text: string): string {
	let out = text.trim();
	out = out.replace(/^[（(]\s*[0-9A-Za-z一二三四五六七八九十]+\s*[)）]\s*/, "");
	out = out.replace(/^[0-9]+(?:\.[0-9]+)*\s*[.、)）]\s*/, "");
	out = out.replace(/^[A-Za-z]\s*[.、)）]\s*/, "");
	out = out.replace(/^[一二三四五六七八九十]+\s*[、.)）]\s*/, "");
	return out.trim();
}

/** First heading family a card heading belongs to (same vocabulary/order as
 * T-01's `classifyHeading`, so extraction can never disagree with the gate). */
function classifyCardHeading(heading: string): EnvelopeSection | undefined {
	const lower = heading.toLowerCase();
	for (const [section, tokens] of ENVELOPE_HEADING_FAMILIES) {
		for (const token of tokens) {
			if (lower.startsWith(token.toLowerCase())) return section;
		}
	}
	return undefined;
}

/**
 * Extract the three envelope bodies from a card (T-02, contract C3).
 *
 * Heading-based slicing mirrors T-01's judgement: the first heading of a family
 * with a non-empty body wins, body runs to the next heading of the same or
 * higher level. A section T-01 accepted only through the wide semantic fallback
 * (headingless card) has no slice to take, so the whole post-prologue card body
 * is used as its content — the seed is delivered rather than dropped. This
 * never re-judges the envelope; `readEnvelope` already owns the verdict.
 */
export function extractCardSections(cardText: string): CardSections {
	const raw = cardText.replace(/\r\n?|[\u2028\u2029]/g, "\n").split("\n");
	const lines = raw.map((line) => line.trim());
	const headings: Array<{ level: number; text: string; line: number }> = [];
	for (let i = 0; i < lines.length; i++) {
		const match = CARD_HEADING_RE.exec(lines[i] ?? "");
		if (match)
			headings.push({ level: match[1]?.length ?? 2, text: stripCardHeadingNumbering(match[2] ?? ""), line: i });
	}
	const out: CardSections = { context: "", requirements: "", deliverables: "", extras: [] };
	/** Body of heading `index` (to the next same-or-higher heading). */
	const bodyOf = (index: number): string => {
		const heading = headings[index];
		if (heading === undefined) return "";
		let end = lines.length;
		for (let j = index + 1; j < headings.length; j++) {
			const next = headings[j];
			if (next !== undefined && next.level <= heading.level) {
				end = next.line;
				break;
			}
		}
		return raw
			.slice(heading.line + 1, end)
			.join("\n")
			.trim();
	};
	const used = new Set<number>();
	for (let i = 0; i < headings.length; i++) {
		const heading = headings[i];
		if (heading === undefined) continue;
		const section = classifyCardHeading(heading.text);
		if (section === undefined || out[section] !== "") continue;
		const body = bodyOf(i);
		if (body !== "") {
			out[section] = body;
			used.add(i);
		}
	}
	// T-12/F-02: every remaining card heading with a body is a §1.2 extra. It is
	// injected into the derived task.md verbatim so the service-layer extras judge
	// sees the same declaration and a compliant card is not false-rejected.
	for (let i = 0; i < headings.length; i++) {
		const heading = headings[i];
		if (heading === undefined || used.has(i)) continue;
		const body = bodyOf(i);
		if (body !== "") out.extras.push({ title: heading.text, body });
	}
	const firstHeading = headings[0];
	const fallback = raw
		.slice(firstHeading === undefined ? 0 : firstHeading.line + 1)
		.join("\n")
		.trim();
	for (const section of ["context", "requirements", "deliverables"] as const) {
		if (out[section] === "") out[section] = fallback;
	}
	return out;
}

/** Render the marker-paired card seed block (T-02, contract C3).
 *
 * T-05/AC-003 (S2 TS half): for a card-backed render whose role is a
 * card-declared WRITELESS report role, the role's `## 交付段契约（本角色）`
 * checklist is appended inside the seed block (each required section as a
 * copyable `## <name>`). The presence guard makes a card that already declares
 * the heading a byte-level fixed point, so re-rendering (or the Python
 * producer's identical `dispatch.py::_envelope_card_body` injection) cannot
 * double-render the section.
 *
 * Scope note (2026-10-14, T-05; widened 2026-10-15, T-13/D-015 option C): the
 * gate is now "the card declares a `type:`" — `recoveryContractSection` already
 * returns `""` for types outside `RECOVERY_CONTRACT_TYPES` (no contract role
 * stays byte-identical), so the checklist reaches every contract role the TS
 * dispatch path produces, `coding` included. The `dispatch-card-injection.test.ts`
 * coding fixture now carries the checklist in its pinned expected bytes. */
export function renderCardSeedSections(sections: CardSections): string {
	const parts = [
		CARD_SEED_MARKER,
		"## 上下文",
		"",
		sections.context.trim(),
		"",
		"## 要求",
		"",
		sections.requirements.trim(),
		"",
		"## 交付格式",
		"",
		sections.deliverables.trim(),
		"",
	];
	for (const extra of sections.extras) {
		parts.push(`## ${extra.title}`, "", extra.body.trim(), "");
	}
	const contract = sections.type !== undefined ? recoveryContractSection(sections.type) : "";
	if (contract !== "" && !parts.includes(RECOVERY_CONTRACT_HEADING)) {
		parts.push(contract, "");
	}
	// T-02/design §4 + D-002: the claims block rides inside the seed marker
	// region, so the settle path reads it from task.md instead of the (mutable)
	// card file. The seed only slices headings, so without this the block would
	// never reach the derived task.md.
	const claims = (sections.claims ?? "").trim();
	if (claims !== "") parts.push(claims, "");
	parts.push(CARD_SEED_DISCLAIMER, CARD_SEED_MARKER_END);
	return parts.join("\n");
}

/** Card-seed region matcher for idempotent re-application (marker → marker). */
const CARD_SEED_SECTION_RE = new RegExp(
	`${CARD_SEED_MARKER.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[\\s\\S]*?${CARD_SEED_MARKER_END.replace(
		/[.*+?^${}()|[\]\\]/g,
		"\\$&",
	)}\n*`,
	"g",
);

/** Idempotent card-seed application: any existing marker region is removed,
 * then the canonical block is prepended to the body. Applying it twice is a
 * byte-level fixed point and leaves exactly one marker pair. */
export function applyCardSeedSections(bodyText: string, sections: CardSections): string {
	const cleaned = bodyText.replace(CARD_SEED_SECTION_RE, "").replace(/^\n+/, "");
	return `${renderCardSeedSections(sections)}\n\n${cleaned}`;
}

/** T-18 (VC-003 producer identity): this generator's id for the task.md header.
 *
 * The service layer (`launcher.py` `producer_identity`, T-14/AC-009) reads
 * `envelope_producer: <producer-id>@<version>` to tell a *stale producer* (an
 * old framework copy whose task.md shape predates the current envelope/extras
 * contract) apart from a genuinely missing section. The id names this tool
 * path so it is distinct from the Python conductor's `autopilot-conductor`
 * (`dispatch.py` `PRODUCER_NAME`). */
export const DISPATCH_PRODUCER_ID = "agent-team-loop-pm";
/** Machine-readable key of the identity line (`dispatch.py` `PRODUCER_IDENTITY_KEY`). */
export const ENVELOPE_PRODUCER_KEY = "envelope_producer";

/** `<producer-id>@<version>` for the header line.
 *
 * The version is the pi release train's own, read at module load from
 * `packages/coding-agent/package.json` through `config.ts` `VERSION` — the same
 * existing version source `dispatch.py::producer_version()` prefers (and the
 * lockstep version `launcher.py` compares a dotted-numeric producer version
 * against); never a new constant. Shape is byte-compatible with the Python
 * renderer (`f"{PRODUCER_IDENTITY_KEY}: {producer_identity()}"`) and the service
 * parser (`^[ \t]*envelope_producer[ \t]*:[ \t]*(\S+)[ \t]*$`). */
export function envelopeProducerIdentity(): string {
	return `${DISPATCH_PRODUCER_ID}@${VERSION}`;
}

/** Card section heading whose entries become the task.md `write_face:` head
 * (`dispatch.py` `WRITE_FACE_CARD_SECTION`, design D-001). */
export const WRITE_FACE_CARD_SECTION = "写入允许面";

/** First backtick span of an entry line (`dispatch.py` `_BACKTICK_SPAN_RE`). */
const WRITE_FACE_BACKTICK_SPAN_RE = /`([^`]+)`/;

/** Raw entries of a card's `## 写入允许面` section — the TS mirror of
 * `dispatch.py::_card_write_face_entries` (W-03), reading the card sections
 * this file already extracted ({@link CardSections.extras}) instead of
 * re-parsing the card.
 *
 * `null` = the section is absent (undeclared; no `write_face:` line is
 * rendered). A present-but-entry-less section yields `[]` (the renderer then
 * writes the `-` undeclared marker, D-001/§3.3). Entries keep the author's
 * single-`/` syntax verbatim — the renderer must not transform what the
 * parser will normalize, or the two would stop being the same source. */
export function cardWriteFaceEntries(sections: CardSections): string[] | null {
	for (const extra of sections.extras) {
		const title = (extra.title ?? "").trim();
		if (!title.startsWith(WRITE_FACE_CARD_SECTION)) continue;
		const entries: string[] = [];
		for (const raw of (extra.body ?? "").split(/\r\n|\r|\n/)) {
			let item = raw.trim();
			if (item === "") continue;
			if ("-*+".includes(item[0] ?? "")) item = item.slice(1).trim();
			const span = WRITE_FACE_BACKTICK_SPAN_RE.exec(item);
			if (span !== null) {
				item = (span[1] ?? "").trim();
			} else {
				item = (item.split(/[\s（(]/, 1)[0] ?? "").trim();
			}
			if (item !== "" && item !== "-") entries.push(item);
		}
		return entries;
	}
	return null;
}

/** The task.md `write_face:` head value for a non-empty entry list — the TS
 * mirror of `dispatch.py::render_write_face_line` (D-113).
 *
 * No entry contains `,` -> the historical single line `write_face: a, b`; any
 * entry contains `,` -> the design §3.1 block-list carrier
 * `write_face:\n  - a\n  - b` (one entry per item), because `,` is an
 * unconditional single-line separator that brackets/braces never shield.
 * `entries` is non-empty by contract — the caller writes `write_face: -` for a
 * declared-but-empty face. */
export function renderWriteFaceLine(entries: readonly string[]): string {
	const values = entries.map((entry) => entry.trim());
	if (values.some((entry) => entry.includes(","))) {
		return `write_face:\n${values.map((entry) => `  - ${entry}`).join("\n")}`;
	}
	return `write_face: ${values.join(", ")}`;
}

/** Merge the bare `card_path:` / `card_sha256:` / `envelope_producer:` header
 * lines into the same header region as `type:` (no `---` fence — the live PM
 * convention). The identity line is appended last so the existing
 * `card_path:` / `card_sha256:` line positions other suites pin stay fixed.
 *
 * W-08 (D-001): when the card declares a `## 写入允许面` section, its entries
 * are rendered as the task.md `write_face:` head line, byte-identical to
 * `dispatch.py::render_write_face_line` (a declared-but-empty section renders
 * the `-` undeclared marker; the block-list carrier is used when an entry
 * contains `,`). A card without the section keeps the pre-W-08 bytes. */
function mergeCardHeader(frontmatter: string, cardPath: string, cardSha256: string, sections: CardSections): string {
	const header = frontmatter.replace(/\r?\n$/, "");
	const writeFaceEntries = cardWriteFaceEntries(sections);
	const writeFaceLine =
		writeFaceEntries === null
			? ""
			: `${writeFaceEntries.length > 0 ? renderWriteFaceLine(writeFaceEntries) : "write_face: -"}\n`;
	return (
		`${header}\ncard_path: ${cardPath}\ncard_sha256: ${cardSha256}\n` +
		`${ENVELOPE_PRODUCER_KEY}: ${envelopeProducerIdentity()}\n${writeFaceLine}`
	);
}

/** D-008 zero side effects for the tool/command dispatch channel: the caller
 * created this task dir in the SAME invocation (an existing dir is refused
 * earlier / the key is `manual-<timestamp>`), and the gate runs before any
 * profile injection, so removing it restores the pre-dispatch state. */
function cleanupRefusedTaskDir(taskPath: string): void {
	try {
		fs.rmSync(path.dirname(taskPath), { recursive: true, force: true });
	} catch {
		// Best effort: the refusal report is what matters.
	}
}

/** Render a write-face refusal / D-003 deferral for the user-facing channel
 * (D-008: the PM audit channel is the dispatch return value). */
function writeFaceRefusalText(taskKey: string, refusal: DispatchRefusal): string {
	if (refusal.code === "write-face-undeclared") {
		return (
			`Worker dispatch of '${taskKey}' held serial-only: the card declares no 写入允许面` +
			` (write_face undeclared, D-003) and ${refusal.inFlight ?? 0} same-key worker(s) are in flight. ` +
			"Nothing was queued. Re-dispatch once the in-flight worker reaches a terminal status, or declare the card's 写入允许面."
		);
	}
	return (
		`Worker dispatch of '${taskKey}' refused: ${refusal.reason}. ` +
		"Nothing was written (no task dir, no queue row). Narrow the card's 写入允许面 so it does not overlap an in-flight same-key worker, then re-dispatch."
	);
}

/**
 * Normalize a dispatch's card reference to the key-relative `tasks/<name>.md`
 * form the traceability audit (T-06 `card_audit.py`) reads. A card outside the
 * owner key's `tasks/` dir falls back to a repo-relative posix path; the last
 * resort is the bare basename so a header is always written.
 */
export function normalizeCardPathForHeader(
	cardPathInput: string,
	ownerKey: string,
	agenticdocRoot: string,
	projectDir: string,
): string {
	const resolved = path.isAbsolute(cardPathInput)
		? path.resolve(cardPathInput)
		: path.resolve(projectDir, cardPathInput);
	const keyTasksDir = path.join(agenticdocRoot, ownerKey, "tasks");
	if (isSameOrUnder(keyTasksDir, resolved)) return `tasks/${path.basename(resolved)}`;
	const rel = path.relative(projectDir, resolved);
	if (rel !== "" && !rel.startsWith("..") && !path.isAbsolute(rel)) return rel.split(path.sep).join("/");
	return path.basename(resolved);
}

/** Resolved dispatch-card gate result (T-02, contract C3). */
export interface DispatchCardGate {
	ok: boolean;
	/** Which refusal code this verdict carries (T-02/design §3.2): the envelope /
	 * extras / seed judge (`dispatch-card`) or the claims judge
	 * (`dispatch-claims`). */
	code: DispatchCardRefusalCode;
	/** Absolute path the reference resolved to (named in every refusal). */
	resolvedPath: string;
	/** Missing envelope items, `readEnvelope` keys and/or §1.2 extra names; for a
	 * `dispatch-claims` verdict the claim gap items (`claim:<id>:<element>`,
	 * `claims:<rule>:<detail>`). */
	missing: string[];
	/** Normalized `tasks/<name>.md` header value (empty when ok=false). */
	headerPath: string;
	/** EOL-normalized sha256 (empty when ok=false). */
	sha256: string;
	/** Extracted seed bodies (empty strings when ok=false). */
	sections: CardSections;
	/** Parsed claims of the card, `[]` when it declares no claims block. */
	claims: Claim[];
	/** Read-budget caps derived from the claims (design §4), `null` when the card
	 * declares no claims (the dispatch then keeps the historical cap behaviour
	 * and writes no `read_scope:`/cap lines). */
	caps: { fileCap: number; byteCap: number } | null;
	/** Advisory findings (D-006): the dispatch proceeds, but these items would be
	 * gaps under `MW_CLAIM_GATE=enforce`. Empty in enforce mode (they are refused
	 * instead) and for a card without a claims block. */
	warnings: string[];
	/** A `<!-- mw-claims: v1 -->` block was seen on the card, even if no row parsed.
	 * The receipt needs this to tell "no claims block" (silent, byte-identical)
	 * apart from "a claims block that produced zero claims" (must shout: the
	 * worker will otherwise run with no verdict scope and no read budget). */
	claimsDeclared: boolean;
}

const EMPTY_CARD_SECTIONS: CardSections = { context: "", requirements: "", deliverables: "", extras: [] };

/**
 * G-1 tool-layer gate (design §4): resolve the card path, judge the envelope
 * with T-01's `readEnvelope`, then the per-type §1.2 extras on the CARD TEXT
 * (the same `typeExtrasMissing` the service layer runs on the derived task.md,
 * T-12/F-02) and the seed minimum (`seedItemsMissing`, T-12/F-05), and only
 * then digest + extract the seed. Never judges content quality; a refusal is a
 * plain report the caller turns into text (zero side effects).
 *
 * The claims judge (T-02, design §5 G1) runs LAST, on the same card text, so a
 * card that already fails the envelope keeps its historical refusal byte for
 * byte and its `dispatch-card` code:
 *
 *  - `MW_CLAIM_GATE=enforce` (D-006) merges EVERY finding — the unusable rows
 *    that `claimsGaps` always reports plus the soft ones it only reports under
 *    enforce — into `missing`, and the verdict carries `dispatch-claims`;
 *  - `advisory` (the calibrated default) refuses NOTHING: every finding,
 *    structural or soft, rides along as a `warnings` entry on the receipt and
 *    the dispatch proceeds. A gray-release gate that could still reject a card
 *    would be a new way to lose a dispatch on a table typo, which is the exact
 *    failure mode P-048 measured (an over-strict schema produced consecutive
 *    false refusals); `enforce` is the only mode that judges.
 *
 * A card without a claims block yields `claims=[]`, `caps=null`, `warnings=[]`
 * and not a single changed byte downstream (AC-007).
 */
export function readDispatchCard(input: {
	cardPath: string;
	ownerKey: string;
	agenticdocRoot: string;
	projectDir: string;
}): DispatchCardGate {
	const raw = input.cardPath.trim();
	const resolvedPath = path.isAbsolute(raw) ? path.resolve(raw) : path.resolve(input.projectDir, raw);
	const empty: DispatchCardGate = {
		ok: false,
		code: DISPATCH_CARD_CODE,
		resolvedPath,
		missing: [],
		headerPath: "",
		sha256: "",
		sections: EMPTY_CARD_SECTIONS,
		claims: [],
		caps: null,
		warnings: [],
		claimsDeclared: false,
	};
	if (raw === "") return { ...empty, missing: ["card_path"] };
	const envelope = readEnvelope(resolvedPath);
	if (!envelope.ok) return { ...empty, missing: envelope.missing };
	let text: string;
	try {
		text = fs.readFileSync(resolvedPath, "utf8");
	} catch {
		return { ...empty, missing: ["file"] };
	}
	// T-12/F-02: judge the per-type extras on the CARD TEXT here so G-1 and G-3
	// are the same criterion (the derived task.md carries these sections too).
	// T-12/F-05: the seed minimum is a G-1 requirement. Any gap refuses and names
	// the item; nothing is written.
	const missing = [...(envelope.type === "" ? [] : typeExtrasMissing(envelope.type, text)), ...seedItemsMissing(text)];
	if (missing.length > 0) return { ...empty, missing };
	const claimBlock = parseClaimsBlock(text);
	const enforce = claimGateMode() === "enforce";
	// One call per mode: `enforce:false` is the structural set, `enforce:true` is
	// structural + soft. Advisory takes the union as warnings and refuses nothing
	// (D-006 gray release); enforce turns the union into the refusal list.
	const audit = claimsGaps(claimBlock, { projectDir: input.projectDir, enforce: true });
	const claimsMissing = enforce ? [...claimBlock.errors, ...audit] : [];
	const warnings = enforce ? [] : [...claimBlock.errors, ...audit];
	const caps = claimBlock.claims.length > 0 ? claimBudgetCaps(claimBlock.claims) : null;
	if (claimsMissing.length > 0) {
		return {
			...empty,
			code: DISPATCH_CLAIMS_CODE,
			missing: claimsMissing,
			claims: claimBlock.claims,
			caps,
			claimsDeclared: claimBlock.present,
		};
	}
	const sections: CardSections = {
		// T-05/AC-003: carry the card's `type:` into the seed so the S2 checklist
		// can be rendered (a `CardSections` built directly from card text has no
		// type and stays byte-identical).
		...extractCardSections(claimBlock.present ? stripClaimsBlockText(text) : text),
		type: envelope.type,
	};
	// T-02: the claims block rides into task.md verbatim (D-002) — set only when
	// the card actually declares one, so a pre-claims card keeps its bytes.
	const claimsText = claimBlock.present ? extractClaimsBlockText(text) : "";
	if (claimsText !== "") sections.claims = claimsText;
	return {
		ok: true,
		code: DISPATCH_CARD_CODE,
		resolvedPath,
		missing: [],
		headerPath: normalizeCardPathForHeader(raw, input.ownerKey, input.agenticdocRoot, input.projectDir),
		sha256: cardDigest(resolvedPath),
		sections,
		claims: claimBlock.claims,
		caps,
		warnings,
		claimsDeclared: claimBlock.present,
	};
}

/** Refusal text for an incomplete card (AC-007 fail-closed): names the code,
 * the missing items and the exact card path; says nothing was written. A
 * claims verdict (T-02/design §3.2) keeps the same structure under its own
 * code, `missing=[claim:C2:locator, claims:budget-sum:48>40]` as parsed. */
export function dispatchCardRefusal(gate: DispatchCardGate): string {
	if (gate.code === DISPATCH_CLAIMS_CODE) {
		return (
			`[${DISPATCH_CLAIMS_CODE}] dispatch refused: card '${gate.resolvedPath}' declares a claims block that cannot be used ` +
			`(missing=[${gate.missing.join(", ")}]).\n` +
			`Required per claim row: 类型 ∈ ${CLAIM_TYPES.join(" | ")}, 陈述, 反证条件, 定位, 判据 (its prefix must match the type: cmd: / grep: / shape: / manual:), 预算 (a non-negative integer); Σ预算 ≤ 40 with 类型 manual counted twice.\n` +
			"Fix the <!-- mw-claims: v1 --> block at that path (or remove it entirely), then re-dispatch; nothing was written."
		);
	}
	const labels = gate.missing
		.filter((item): item is EnvelopeSection => item in ENVELOPE_SECTION_LABELS)
		.map((item) => ENVELOPE_SECTION_LABELS[item]);
	return (
		`[${DISPATCH_CARD_CODE}] dispatch refused: card '${gate.resolvedPath}' is not a complete dispatch envelope ` +
		`(missing=[${gate.missing.join(", ")}]).\n` +
		(labels.length > 0 ? `Missing sections: ${labels.join(" / ")}.\n` : "") +
		"Required: type + 上下文/要求/交付格式; per type: coding(写入允许面/写入禁止面/验收命令/改动历史), research(唯一证据文件), review(审计目标/未覆盖面声明); seeds: a goal.md reference and at least one path:line reference.\n" +
		"Fix the card at that path (or pass a different card_path), then re-dispatch; nothing was written."
	);
}

/** The advisory claims receipt line (design §5 G1): appended ONLY when the card
 * declares claims, so a pre-claims card's receipt stays byte-identical
 * (`triage-dispatch.test.ts` pins the full string).
 *
 * A declared block that parses to ZERO claims is the dangerous case (T-07): the
 * claim ids are `C-<2+ digits>`, so an id like `C-A1` silently drops every row,
 * which means no `read_scope`, no caps and — without this line — no signal at
 * all. It therefore reports `claims=0(unparsed)` plus the row errors rather
 * than staying quiet. */
export function claimsReceiptLine(gate: DispatchCardGate): string {
	if (!gate.claimsDeclared && gate.claims.length === 0) return "";
	const caps = gate.caps === null ? "caps=none" : `caps=${gate.caps.fileCap}/${gate.caps.byteCap}`;
	const warnings = gate.warnings.length > 0 ? gate.warnings.join(", ") : "none";
	const count = gate.claims.length > 0 ? String(gate.claims.length) : "0(unparsed)";
	return `\n[claims] ${claimGateMode()} claims=${count} ${caps} warnings=[${warnings}]`;
}

/** Single write point for one dispatch's task.md (contract C4). Both dispatch
 * entries — the `dispatch_worker` tool and the `/worker` command — go through
 * here so the pipeline (frontmatter merge, contract-section injection, mkdir,
 * writeFileSync) has exactly one implementation. The T-01 extraction is
 * byte-for-byte equivalent to the inline writes it replaced: with no
 * `writeScope` and no injection hook the file content is
 * `${frontmatter}\n${body}\n` and only the mkdir/write order is shared. T-02
 * fills in the write-surface contract section (C2) and `injected` reports
 * whether this call wrote one. */
export function writeDispatchTaskMd(
	deps: { agenticdocRoot: string; ownerKey: string },
	input: {
		taskKey: string;
		type: string;
		body: string;
		frontmatter: string;
		/** Rendered `write_scope:` line (T-02, contract C1); undefined keeps the
		 * pre-C1 frontmatter bytes. */
		writeScope?: string;
		/** AC-005a (contract C2): inject the write-surface contract section.
		 * Opt-in so the pre-C2 byte shape stays available (T-01/T-03 callers). */
		injectWriteSurface?: boolean;
		/** AC-005a escape hatch: record `allow_foreign_write: true` for audit. */
		allowForeignWrite?: boolean;
		/** T-02 (contract C3): the judged dispatch card. Adds the bare
		 * `card_path:` / `card_sha256:` header lines (plus the T-18
		 * `envelope_producer:` identity line) and prepends the card-derived
		 * `## 上下文` / `## 要求` / `## 交付格式` seed block (idempotent). Omitted
		 * keeps the pre-T-02 byte shape for direct callers. */
		card?: { headerPath: string; sha256: string; sections: CardSections };
		/** T-08 (spec §6.1, design D-012): the decision that authorized this
		 * dispatch. Injected as the `decision:` head line ONLY when `acted=true`;
		 * omitted keeps the pre-T-08 byte shape. */
		decision?: DispatchDecision;
		/** T-04d: the one `[DECISION] dp1 state=…` audit line this dispatch writes
		 * into the task's `trace.log` (structured path vs legacy fallback). Omitted
		 * (direct callers / triage off) writes nothing. */
		decisionTrace?: string;
		/** T-02 (design §4): the claims-derived read scope. Rendered as a
		 * `read_scope:` block list (plus the two cap scalars); omitted/empty keeps
		 * the pre-T-02 bytes AND the worker's read interceptor off (AC-007). */
		readScope?: string[];
		/** `l2_read_file_cap` value from `claimBudgetCaps`; renders only when
		 * `readScope` is non-empty and the value is a positive number. */
		readFileCap?: number;
		/** `l2_read_byte_cap` value from `claimBudgetCaps`, same rule as
		 * {@link readFileCap}. */
		readByteCap?: number;
	},
): { ok: true; path: string; injected: boolean } {
	let frontmatter = mergeAllowForeignWrite(
		mergeWriteScope(
			mergeReadScope(input.frontmatter, input.readScope, input.readFileCap, input.readByteCap),
			input.writeScope,
		),
		input.allowForeignWrite,
	);
	if (input.card) {
		frontmatter = mergeCardHeader(frontmatter, input.card.headerPath, input.card.sha256, input.card.sections);
	}
	// T-08: merge chain end — the decision id is the last head line, so the
	// existing `card_path:` / `write_face:` positions other suites pin stay fixed.
	frontmatter = mergeDecisionHeader(frontmatter, input.decision);
	const taskDir = workerTaskDir(deps.agenticdocRoot, deps.ownerKey, input.taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	const taskMdPath = path.join(taskDir, "task.md");
	const body = input.card ? applyCardSeedSections(input.body, input.card.sections) : input.body;
	const plain = `${frontmatter}\n${body}\n`;
	const content = input.injectWriteSurface ? applyWriteSurfaceContract(plain, input.type, input.writeScope) : plain;
	fs.writeFileSync(taskMdPath, content, "utf8");
	// T-04d: the dp1 state path is recorded in the SAME trace the worker appends
	// to, so a legacy fallback is auditable instead of silent. Best-effort by
	// design: a trace failure must never fail a dispatch whose task.md already
	// landed.
	if (input.decisionTrace !== undefined) {
		try {
			fs.appendFileSync(path.join(taskDir, "trace.log"), `${input.decisionTrace}\n`, "utf8");
		} catch {
			// Diagnostic only — the task.md write is the dispatch's contract.
		}
	}
	return { ok: true, path: taskMdPath, injected: input.injectWriteSurface === true };
}

/**
 * Register agent-callable tools for worker dispatch and task listing.
 * These complement the slash commands in registerWorkerCommands.
 */
export function registerWorkerTools(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	ackStore: AckStore,
	indexStore: IndexStore,
	agenticdocRoot: string,
	watch: PmWatchState,
	projectDir: string = path.dirname(agenticdocRoot),
	/** T-03 test seam for the DP-1 child; production omits it. */
	triageRun?: DecideRunner,
	/** T-08 test seam for the dp1 feedback writer; production omits it (the real
	 * `mw decide lifecycle` child is the single write face). */
	lifecycleRun?: LifecycleRunner,
): void {
	// dispatch_worker: create a task.md and immediately dispatch it to the worker queue.
	pi.registerTool({
		name: "dispatch_worker",
		label: "dispatch_worker",
		description:
			"Dispatch a task to a background worker agent. Creates .agenticdoc/<owner key>/workers/<task_key>/task.md and queues it for execution by the mw worker service. Returns the task key on success. " +
			'Cross-key writes are refused: a key another window holds live is READ-ONLY here — read it with list_tasks { scope: "all" } and take it over with switch_key before writing into it.',
		parameters: Type.Object({
			task_key: Type.String({
				description:
					"Unique kebab-case key for this task (e.g. 'fix-login-bug', 'add-auth-endpoint'). Must be unique across tasks in this project.",
			}),
			card_path: Type.String({
				description:
					"REQUIRED. Path to the dispatch card (task book) this worker is generated from — relative to the repo root or absolute, e.g. '.agenticdoc/<key>/tasks/T-02-slug.md'. The card must carry the dispatch envelope (type + 上下文 / 要求 / 交付格式), the per-type extras (coding: 写入允许面/写入禁止面/验收命令/改动历史; research: 唯一证据文件; review: 审计目标/未覆盖面声明), and the seed minimum (a goal.md reference plus at least one path:line reference); an incomplete or missing card refuses the dispatch with zero side effects. The card's envelope, extras and context are injected as the seed (not an upper bound on what the worker may read) and recorded via card_path/card_sha256 in task.md for traceability.",
			}),
			description: Type.String({
				description: "Full task description and instructions for the worker agent.",
			}),
			cli: Type.Optional(
				Type.String({
					description:
						"Worker CLI: 'pi' (default for all task types incl. review/research), 'claude' (explicit override — requires claude credentials, fails per-task when missing), 'codex' (codex tasks).",
				}),
			),
			model: Type.Optional(
				Type.String({
					description:
						"Optional model override for this worker (e.g. 'timi/gpt-5.6-sol'). Deviating from the configured .mw/dispatch.yml role default requires model_reason; a value equal to that default is not pinned (the config stays the source of truth).",
				}),
			),
			model_reason: Type.Optional(
				Type.String({
					description:
						"Why this task deviates from the .mw/dispatch.yml role default. Required when model is set and the role has a configured default with a different value; recorded in task.md as model-reason.",
				}),
			),
			type: Type.Optional(
				Type.String({
					description:
						"Task type: 'coding' | 'review' | 'research' | 'rag-research' | 'vision' | 'decide_prepare'. Selects the dispatch.yml role (and the worker tool allowlist). Use 'vision' for tasks that must read image files (screenshots/mockups). Default: derived from cli (pi -> coding, claude -> review, codex -> codex).",
				}),
			),
			images: Type.Optional(
				Type.Union([Type.Literal("yes"), Type.Literal("no")], {
					description:
						"Declare the image requirement: 'yes' means this task must look at images (refused when the effective model cannot take image input), 'no' exempts it. Omit to auto-detect an existing image file referenced in the description.",
				}),
			),
			allow_foreign_write: Type.Optional(
				Type.Boolean({
					description:
						"AC-005a escape hatch: dispatch a writeless role even when its task book names an external write target. Recorded in task.md as `allow_foreign_write: true` for audit; use only when a human accepted the external path.",
				}),
			),
			key: Type.Optional(
				Type.String({
					description:
						"AgenticTask key owning this worker task. Default: this window's claimed key (the one it watches and holds in _index.parallel), else the active key when no other live window holds it, else _scratch.",
				}),
			),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
			const {
				task_key,
				card_path,
				description,
				cli = "pi",
				model,
				model_reason,
				type,
				images,
				key,
				allow_foreign_write,
			} = params as {
				task_key: string;
				card_path: string;
				description: string;
				cli?: string;
				model?: string;
				model_reason?: string;
				type?: string;
				images?: "yes" | "no";
				key?: string;
				allow_foreign_write?: boolean;
			};
			// RAG dispatcher gate (VC-003): an unusable rag config (e.g. `enabled`
			// naming an undefined server) must refuse BEFORE any task.md is created
			// and before the queue row lands.
			const ragCheck = validateRagEnabled(projectDir);
			if (!ragCheck.ok) {
				return { content: [{ type: "text", text: ragCheck.message }], details: undefined };
			}
			const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, key, agenticdocRoot);

			// Cross-key write guard (AC-024/AC-006): unconditional (DD-07e) — the
			// guard is the single write gate for every dispatch, explicit key or not.
			// resolveOwnerKeyWithSync already degrades a foreign-live or reserved
			// value to _scratch, so the implicit path gains no new refusal.
			const refusal = foreignLiveClaimRefusal(indexStore, ownerKey);
			if (refusal) return { content: [{ type: "text", text: refusal }], details: undefined };

			const validCli = ["pi", "claude", "codex"];
			if (!validCli.includes(cli)) {
				return {
					content: [{ type: "text", text: `Invalid cli '${cli}'. Must be one of: ${validCli.join(", ")}.` }],
					details: undefined,
				};
			}

			// Task type is declarable (mw-dispatch-role-escape): without it a pi
			// worker could never reach the review/research dispatch.yml role or tool
			// allowlist, which is what forced hand-written model overrides.
			const typeResolution = resolveDispatchType(cli, type ?? "");
			if (!typeResolution.ok) {
				return { content: [{ type: "text", text: typeResolution.message }], details: undefined };
			}
			const provider = cli === "pi" ? "timi" : "";

			// Docs gate, phase-tiered (mw-worker-visibility-gate): the owner key's
			// CURRENT phase picks the tier — SPEC (or placeholder/unknown) needs the
			// spec-side chain; from DESIGN onward the full six-item chain. One
			// phase read, reused by the task.md frontmatter below.
			const ownerPhase = dispatchPhase(agenticdocRoot, ownerKey);
			const docGaps = dispatchDocGaps(agenticdocRoot, ownerKey, ownerPhase);
			if (docGaps.length > 0) {
				return {
					content: [
						{
							type: "text",
							text:
								`Worker dispatch blocked: key '${ownerKey}' is missing phase documentation.\n` +
								`${docGaps.map((g) => `- ${g}`).join("\n")}\n${DOC_GATE_HINT}`,
						},
					],
					details: undefined,
				};
			}

			// Worker tasks live under {ownerKey}/workers/<task_key>/ (never at the
			// agenticdoc root - that namespace belongs to AgenticTask keys).
			const taskDir = workerTaskDir(agenticdocRoot, ownerKey, task_key);
			if (fs.existsSync(taskDir)) {
				return {
					content: [
						{
							type: "text",
							text: `Task '${task_key}' already exists at ${taskDir}. Choose a different task_key or check existing tasks with list_tasks.`,
						},
					],
					details: undefined,
				};
			}

			const typeField = typeResolution.type;

			// AC-005a (T-02): a role with neither write/edit nor bash cannot reach a
			// path outside its own task dir, so a task book ordering one is
			// unsatisfiable. Refused here — after the cross-key guard, before the
			// frontmatter plan and decisively before mkdir/task.md/queue — so the
			// refusal has zero side effects. `research` (writeless but shell-capable)
			// is NOT refused; it only gets the contract section + write_scope header.
			const writelessRole = isWritelessRole(typeField);
			const allowForeignWrite = allow_foreign_write === true;
			if (writelessRole) {
				const verdict = judgeWriteIntent({
					type: typeField,
					description,
					taskDir,
					projectRoot: projectDir,
					keyDir: path.join(agenticdocRoot, ownerKey),
					trueRoot: agenticdocRoot,
					allowForeignWrite,
				});
				if (!verdict.ok) {
					return {
						content: [
							{
								type: "text",
								text: writeIntentRefusal({
									taskKey: task_key,
									type: typeField,
									path: verdict.violations[0]?.path ?? "",
								}),
							},
						],
						details: undefined,
					};
				}
			}

			// G-1 tool-layer envelope gate (T-02, design §4): the card must exist and
			// carry the §1 envelope + §1.2 type extras BEFORE any task.md is written
			// or a queue row lands. Placed after the earlier guards so their own
			// refusals stay byte-identical; still decisively before mkdir/queue.
			const cardGate = readDispatchCard({
				cardPath: card_path ?? "",
				ownerKey,
				agenticdocRoot,
				projectDir,
			});
			if (!cardGate.ok) {
				return { content: [{ type: "text", text: dispatchCardRefusal(cardGate) }], details: undefined };
			}

			// T-11/M1: `plan` stops BEFORE task.md/queue (zero side effects, GC-3).
			// biome-ignore format: one object, kept on a single property line (card T-11: ≤6 lines per entry)
			const splitGate = planReviewSplitGate({
				cardPath: card_path ?? "", taskKey: task_key, ownerKey, agenticdocRoot, projectDir,
			});
			if (splitGate !== null) return { content: [{ type: "text", text: splitGate.text }], details: undefined };

			// Model plan: validate the effective value and enforce the override
			// reason BEFORE any filesystem write (a refusal must leave no task dir).
			const modelPlan = planDispatchFrontmatter({
				cwd: projectDir,
				cli,
				provider,
				taskType: typeField,
				phase: ownerPhase,
				description,
				images,
				model: model ?? "",
				modelReason: model_reason ?? "",
				registry: _context?.modelRegistry,
				triageRun,
				// T03: owning key + the REAL reserved task id + the judged card's
				// envelope bodies are the dp1 material/association facts.
				dp1: {
					key: ownerKey,
					taskKey: task_key,
					sections: cardGate.sections,
					taskBefore: captureDecisionTaskState(workerStore, ownerKey, task_key),
				},
			});
			if (!modelPlan.ok) {
				return { content: [{ type: "text", text: modelPlan.message }], details: undefined };
			}
			// DP-1 ledger + (on disagreement) the one PM wake for this dispatch.
			emitDispatchTriage(pi, agenticdocRoot, modelPlan.triage);

			const written = writeDispatchTaskMd(
				{ agenticdocRoot, ownerKey },
				{
					taskKey: task_key,
					type: typeField,
					body: description,
					frontmatter: modelPlan.frontmatter,
					writeScope:
						writelessRole && isShellRole(typeField) ? renderDefaultWriteScope(ownerKey, task_key) : undefined,
					// T-02/design §4: claims-backed read budget. `caps=null` (no claims
					// block) leaves both the bytes and the interception behaviour alone.
					readScope: cardGate.caps === null ? undefined : claimReadScope(ownerKey, cardGate.claims),
					readFileCap: cardGate.caps?.fileCap,
					readByteCap: cardGate.caps?.byteCap,
					injectWriteSurface: writelessRole,
					allowForeignWrite,
					card: { headerPath: cardGate.headerPath, sha256: cardGate.sha256, sections: cardGate.sections },
					// T-08/T-04c: the decision this dispatch ADOPTED (D-041). `suggest` and
					// unavailable advice carry no decision, so the bytes stay pre-T-08.
					decision: modelPlan.triage?.decision,
					// T-04d: record which dp1 state shape the child actually received.
					decisionTrace: modelPlan.triage?.stateTrace,
				},
			);
			const taskMdPath = written.path;

			const outcome = await dispatchTask(
				{ taskKey: task_key, status: "pending", cli, provider, model: model ?? "", taskPath: taskMdPath },
				workerStore,
			);
			if (!outcome.ok) {
				cleanupRefusedTaskDir(taskMdPath);
				// The refused dispatch is still a real outcome of the decision: the
				// consumed fact stands, the round settles as `rework`, and NO executed
				// fact is written (nothing was executed).
				const dp1Feedback = formatDp1ConsumerReceipt(
					await writeDp1DispatchFeedback({
						projectDir,
						triage: modelPlan.triage,
						lifecycleRun,
						taskKey: task_key,
						dispatchedType: typeField,
						refused: true,
						taskAfter: captureDecisionTaskState(workerStore, ownerKey, task_key),
					}),
				);
				return {
					content: [
						{
							type: "text",
							text: writeFaceRefusalText(task_key, outcome) + (dp1Feedback === "" ? "" : `\n${dp1Feedback}`),
						},
					],
					details: undefined,
				};
			}

			// Record the dispatch on this window's state (mw-task-scope-isolation) so
			// list_tasks / ack keep owning tasks that did NOT land under the watched
			// key (explicit cross-key dispatch, or the global-active fallback).
			if (watch.dispatchedTaskKeys === undefined) watch.dispatchedTaskKeys = new Set();
			watch.dispatchedTaskKeys.add(task_key);

			// The dispatch really landed: the consumer reports executed + settled
			// through the single Python writer. A failed feedback write never undoes
			// or repeats the dispatch — the receipt says `failed`.
			const dp1Feedback = formatDp1ConsumerReceipt(
				await writeDp1DispatchFeedback({
					projectDir,
					triage: modelPlan.triage,
					lifecycleRun,
					taskKey: task_key,
					dispatchedType: typeField,
					refused: false,
					taskAfter: captureDecisionTaskState(workerStore, ownerKey, task_key),
				}),
			);

			return {
				content: [
					{
						type: "text",
						text:
							appendTriageReceipt(
								`Dispatched worker '${task_key}' (type: ${typeField}, role: ${roleForTaskType(typeField)}, ${modelPlan.echo}) under key '${ownerKey}'. Task file: ${taskMdPath}. Check mw_status to confirm the service is running.`,
								modelPlan.triage,
							) +
							claimsReceiptLine(cardGate) +
							(dp1Feedback === "" ? "" : `\n${dp1Feedback}`),
					},
				],
				details: undefined,
			};
		},
	});

	// ack_worker_result: the agent-side ack channel (AC-005) — equivalent to
	// /mw ack. Registered here (PM activation path only); worker mode never
	// registers tools, so workers cannot ack their own results.
	pi.registerTool({
		name: "ack_worker_result",
		label: "ack_worker_result",
		description:
			"Acknowledge a worker's terminal result (done/failed/needs-clarification) after absorbing it: the row moves out of the watch widget's unhandled section into folded history. task_key acks one task; 'all' acks every unacked terminal task THIS WINDOW owns (its watched key plus tasks it dispatched) — another window's rows are refused, never silently cleared.",
		promptGuidelines: [
			"After absorbing a terminal worker result (the readback body / output.md), call ack_worker_result with its task_key — or 'all' after a batch — so the widget's unhandled section clears; unacked failed/needs-clarification rows stay listed until acked.",
		],
		parameters: Type.Object({
			task_key: Type.String({ description: "Worker task key to ack, or 'all' for every unacked terminal task." }),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
			const { task_key } = params as { task_key: string };
			const target = task_key.trim();
			if (!target) {
				return { content: [{ type: "text", text: "task_key is required (or 'all')." }], details: undefined };
			}
			const result = await ackTasks(workerStore, ackStore, target === "all" ? "all" : [target], {
				watch,
				agenticdocRoot,
			});
			const parts: string[] = [];
			if (result.acked.length > 0) parts.push(`Acked ${result.acked.length} task(s): ${result.acked.join(", ")}.`);
			for (const r of result.rejected) parts.push(`NOT acked: ${r.key} — ${r.reason}.`);
			if (parts.length === 0) parts.push("No unacked terminal tasks.");
			return { content: [{ type: "text", text: parts.join("\n") }], details: undefined };
		},
	});

	// list_tasks: worker queue view, scoped to this window by default
	// (mw-task-scope-isolation); terminal rows carry an `acked` badge when
	// acknowledged (AC-011) and every row carries its owning key.
	pi.registerTool({
		name: "list_tasks",
		label: "list_tasks",
		description:
			"List worker tasks with their current status (pending / running / done / failed / needs-clarification); every row carries its owning key. " +
			'scope "mine" (default) lists only this window\'s tasks — its watched key plus tasks it dispatched; scope "key" lists one key (pass key); scope "all" lists the whole project. ' +
			"Acked terminal tasks are badged 'acked'. " +
			'READING is never restricted by the cross-key write guard: scope "all"/"key" cover other windows\' keys, so use them to inspect status before deciding anything. ' +
			"Acks are refused for another window's rows.",
		parameters: Type.Object({
			scope: Type.Optional(
				Type.String({ description: '"mine" (default, this window) | "key" (with key) | "all" (whole project).' }),
			),
			key: Type.Optional(Type.String({ description: 'Owner key to list when scope is "key".' })),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
			const { scope = "mine", key = "" } = (params ?? {}) as { scope?: string; key?: string };
			const reply = (text: string): { content: Array<{ type: "text"; text: string }>; details: undefined } => ({
				content: [{ type: "text", text }],
				details: undefined,
			});
			const acked = new Set(ackStore.readAll().keys());
			const format = (e: WorkerEntry): string => {
				const base =
					`${ownerKeyOf(e, agenticdocRoot)} :: ${e.taskKey} | ${e.status} | ${e.cli}` +
					`${e.model ? ` | model: ${e.model}` : ""}`;
				return acked.has(e.taskKey) ? `${base} | acked` : base;
			};
			const rows = (entries: WorkerEntry[], emptyText: string): string =>
				entries.length === 0 ? emptyText : entries.map(format).join("\n");

			if (scope === "all") {
				return reply(rows(workerStore.readAll(), "No tasks found."));
			}
			if (scope === "key") {
				const wanted = key.trim();
				if (!wanted) {
					return reply('scope "key" requires key — pass the owner key, e.g. { scope: "key", key: "mw-foo" }.');
				}
				const entries = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot) === wanted);
				return reply(rows(entries, `No tasks found for key '${wanted}'.`));
			}
			if (scope !== "mine") {
				return reply(
					`Unknown scope '${scope}'. Use "mine" (this window), "key" (with key), or "all" (whole project).`,
				);
			}
			const mine = workerStore.readAll().filter((e) => ownedByThisWindow(e, watch, agenticdocRoot));
			if (mine.length > 0) {
				return reply(rows(mine, "No tasks found."));
			}
			return reply(
				`No tasks found for this window (watched key: ${watch.key ?? "(none)"}).\n` +
					'scope "mine" covers the watched key plus tasks this window dispatched; other windows\' tasks are never listed.\n' +
					"- switch_key a key to take it over and watch its workers, or\n" +
					'- list_tasks with scope: "all" to see every key in this project.',
			);
		},
	});
}

/** Register the agent-callable switch_key tool: same takeover as
 * /pm-key switch, callable mid-conversation. Tool description + prompt
 * guidelines teach the agent when to call it (explicit user request, or
 * starting real task work on a key — ask the user first in that case). */
export function registerSwitchKeyTool(
	pi: ExtensionAPI,
	indexStore: IndexStore,
	watch: PmWatchState,
	refreshWatch: (ctx: ExtensionContext) => void,
	agenticdocRoot: string,
): void {
	pi.registerTool({
		name: "switch_key",
		label: "switch_key",
		description:
			"Take over (claim + watch) an AgenticTask key in this window: marks it active in _index.parallel with this window's claim (host:pid) and shows its live worker progress in the bottom widget. " +
			"Call it when the user asks to take over or switch to a key, or when you are about to execute a key's tasks in this window. " +
			"Writing .agenticdoc/{key}/spec.md, design.md, or plan.md switches automatically — no call needed. " +
			"If another live window holds the key's claim, the call fails unless force is true; tell the user and let them decide.",
		promptGuidelines: [
			"Before doing real work on an AgenticTask key (executing its tasks), make sure this window has taken it over via switch_key; if the user has not asked for that key, ask them first whether to switch.",
		],
		parameters: Type.Object({
			key: Type.String({ description: "The AgenticTask key to take over." }),
			force: Type.Optional(
				Type.Boolean({
					description:
						"Steal the claim even if another live window holds it. Only with the user's explicit confirmation.",
				}),
			),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => {
			const { key, force = false } = params as { key: string; force?: boolean };
			const trimmed = key.trim();
			if (!trimmed) {
				return { content: [{ type: "text", text: "key is required." }], details: undefined };
			}
			const result = await takeOverKey(indexStore, trimmed, force, agenticdocRoot);
			if (!result.ok) {
				if (result.refusal) {
					return {
						content: [
							{
								type: "text",
								text: `Key '${trimmed}' is refused (${result.refusal}): reserved framework names and illegal key shapes cannot be claimed.`,
							},
						],
						details: undefined,
					};
				}
				return {
					content: [
						{
							type: "text",
							text: `Key '${trimmed}' is claimed by another live window (${result.blockedBy}). The takeover was NOT performed. Tell the user; they can decide on a forced takeover (force=true).`,
						},
					],
					details: undefined,
				};
			}
			watch.key = trimmed;
			pi.appendEntry(WATCH_ENTRY_TYPE, { key: trimmed, claimed: true });
			refreshWatch(ctx);
			const auditNote =
				result.audit.length > 0
					? `\n\nPHASE-CHAIN AUDIT WARNINGS for this key (fix before continuing; phase changes go through advance_phase.py only):\n${result.audit.join("\n")}`
					: "";
			// pm-state.md mirror sync failure is visible but non-fatal (D-108).
			const syncNote = claimSyncWarningText(trimmed, result.claimSync);
			return {
				content: [
					{
						type: "text",
						text:
							`Took over key '${trimmed}' (claim ${result.claimId})` +
							`${result.created ? " — new key registered in _index.parallel" : ""}. ` +
							"This window now watches it; the bottom widget shows its live progress. Previously active keys were marked idle." +
							auditNote +
							(syncNote === "" ? "" : `\n\n${syncNote}`),
					},
				],
				details: undefined,
			};
		},
	});
}

/** Register the agent-callable advance_phase tool: the shell-free path
 * through the AgenticTask phase gates. The guard blocks hand-edits of
 * pm-state.md's '- Phase:' line and points at advance_phase.py; running that
 * via the bash tool was the only route, so a window whose shell resolution
 * or in-shell `python` differs (fresh machines: WSL-only bash, Store-stub
 * python, python3-only Linux) had NO way to advance a phase — it deadlocked
 * with "no shell, cannot execute advance_phase.py / update_index.py". This
 * tool spawns the script directly (list args, no shell); gate semantics stay
 * in the Python script, the single source of truth audit_phase.py replays. */
export function registerAdvancePhaseTool(pi: ExtensionAPI, projectDir: string, indexStore: IndexStore): void {
	const ladder = PHASE_ORDER.map((p) => p.toLowerCase());
	pi.registerTool({
		name: "advance_phase",
		label: "advance_phase",
		description:
			"Advance an AgenticTask key to the target phase by running the framework gate script (advance_phase.py): checks the phase-gate evidence (spec/design/plan/tasks/execute/done prerequisites), updates pm-state.md, and syncs _index.parallel. Runs the Python script directly without a shell — prefer this over `python .../advance_phase.py` via the bash tool. This is the only sanctioned way to change a key's phase; hand-editing pm-state.md's '- Phase:' line is blocked. " +
			"Cross-key writes are refused: another window's live key is READ-ONLY here (read its phase with list_tasks, take it over with switch_key first).",
		promptGuidelines: [
			"Change phases only through this tool (or the equivalent python script when the shell works); when the result reports GATE BLOCKED, fix the listed evidence gaps before retrying.",
		],
		parameters: Type.Object({
			key: Type.String({ description: "AgenticTask key to advance (not _scratch)." }),
			target_phase: Type.String({
				description: "Target phase (any case): spec | design | plan | tasks | execute | verify | done.",
			}),
			summary: Type.Optional(
				Type.String({
					description:
						"Required when target_phase is done: one-line closing summary (what was added/changed + impact surface) recorded in _project_log.md as the cross-key summary row.",
				}),
			),
			supersedes: Type.Optional(
				Type.String({
					description: "Key this one supersedes, recorded in _project_log.md when advancing to done.",
				}),
			),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
			const { key, target_phase, summary, supersedes } = params as {
				key: string;
				target_phase: string;
				summary?: string;
				supersedes?: string;
			};
			const trimmedKey = key.trim();
			const target = target_phase.trim().toLowerCase();
			if (!trimmedKey || !target) {
				return { content: [{ type: "text", text: "key and target_phase are required." }], details: undefined };
			}
			// Same name gate as the guard and IndexStore.claim (AC-006, direction
			// consistent): reserved names (incl. _scratch) and illegal shapes are not
			// phase-tracked keys. `_scratch` keeps its historical wording.
			const nameRefusal = keyNameRefusal(trimmedKey);
			if (nameRefusal) {
				const reason =
					nameRefusal.code === "reserved-key-name" ? "has a reserved prefix" : `is refused (${nameRefusal.code})`;
				return {
					content: [
						{
							type: "text",
							text: `Key '${trimmedKey}' ${reason} and is not a phase-tracked AgenticTask key.`,
						},
					],
					details: undefined,
				};
			}
			if (!ladder.includes(target)) {
				return {
					content: [
						{ type: "text", text: `Unknown phase '${target_phase.trim()}'. Valid: ${ladder.join(" | ")}.` },
					],
					details: undefined,
				};
			}
			// done 汇总契约（advance_phase.py 同步校验，exit 2）：--summary 是
			// _project_log.md 汇总列唯一数据源，缺失不允许推进。工具层先拦，
			// 错误信息比脚本退出码可读。
			if (target === "done" && !(summary ?? "").trim()) {
				return {
					content: [
						{
							type: "text",
							text: "Advancing to done requires a non-empty summary — one line on what was added/changed and the impact surface (written to _project_log.md as the cross-key summary row).",
						},
					],
					details: undefined,
				};
			}

			const args = [trimmedKey, target];
			if (summary) args.push("--summary", summary);
			if (supersedes) args.push("--supersedes", supersedes);
			// Cross-key write guard (AC-024): advancing another live window's key
			// rewrites ITS pm-state.md + _index.parallel row, so it is refused before
			// the gate script runs. An unclaimed key still advances (new-key
			// bootstrap), and this window's own claim is untouched by the guard.
			const crossKeyRefusal = foreignLiveClaimRefusal(indexStore, trimmedKey);
			if (crossKeyRefusal) return { content: [{ type: "text", text: crossKeyRefusal }], details: undefined };
			const result = runAgenticScript(projectDir, "advance_phase.py", args);
			return { content: [{ type: "text", text: result.output }], details: undefined };
		},
	});
}

/**
 * Spawn a worker directly from the pi window.
 * Usage: /worker <claude|codex|pi> [--type <t>] [--model <id>] [--reason <text>] [--key <name>] <desc>
 */
export function registerWorkerCommands(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	indexStore: IndexStore,
	agenticdocRoot: string,
	watch: PmWatchState,
	projectDir: string = path.dirname(agenticdocRoot),
	/** T-03 test seam for the DP-1 child; production omits it. */
	triageRun?: DecideRunner,
	/** T-08 test seam for the dp1 feedback writer; production omits it. */
	lifecycleRun?: LifecycleRunner,
): void {
	const USAGE =
		"Usage: /worker <claude|codex|pi> --card <card-path> [--type coding|review|research|rag-research|vision] [--model <id>] [--reason <text>] [--key <name>] [--allow-foreign-write] <task description>";
	pi.registerCommand("worker", {
		description:
			"Spawn a worker: /worker <claude|codex|pi> --card <card-path> [--type <t>] [--model <id>] [--reason <text>] <task description>",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const parts = args.trim().split(/\s+/);
			const cli = (parts[0] ?? "").toLowerCase();

			// Optional flags right after the cli; everything else is the description.
			let idx = 1;
			let model = "";
			let modelReason = "";
			let typeArg = "";
			let keyArg = "";
			let cardArg = "";
			let imagesArg: "yes" | "no" | undefined;
			let allowForeignWriteArg = false;
			while (
				["--card", "--model", "--type", "--reason", "--key", "--images", "--allow-foreign-write"].includes(
					parts[idx] ?? "",
				)
			) {
				const flag = parts[idx];
				if (flag === "--allow-foreign-write") {
					allowForeignWriteArg = true;
					idx += 1;
					continue;
				}
				const value = parts[idx + 1] ?? "";
				idx += 2;
				if (!value) {
					ctx.ui.notify(USAGE, "warning");
					return;
				}
				if (flag === "--card") cardArg = value;
				else if (flag === "--model") model = value;
				else if (flag === "--type") typeArg = value;
				else if (flag === "--reason") modelReason = value;
				else if (flag === "--images") {
					if (value !== "yes" && value !== "no") {
						ctx.ui.notify("--images must be 'yes' or 'no'.", "warning");
						return;
					}
					imagesArg = value;
				} else keyArg = value;
			}
			const description = parts.slice(idx).join(" ");

			const validCli = ["claude", "codex", "pi"];
			if (!validCli.includes(cli)) {
				ctx.ui.notify(USAGE, "warning");
				return;
			}
			if (!description) {
				ctx.ui.notify("Task description is required.", "warning");
				return;
			}

			// Task type: declarable, else the legacy cli-derived mapping.
			const typeResolution = resolveDispatchType(cli, typeArg);
			if (!typeResolution.ok) {
				ctx.ui.notify(typeResolution.message, "warning");
				return;
			}
			const typeField = typeResolution.type;
			const provider = cli === "pi" ? "timi" : "";

			// RAG dispatcher gate (VC-003): refuse before creating any task.md.
			const ragCheck = validateRagEnabled(projectDir);
			if (!ragCheck.ok) {
				ctx.ui.notify(ragCheck.message, "warning");
				return;
			}

			// Create task directory and task.md under {ownerKey}/workers/ (persist
			// type/model/model-reason so they are visible + re-parseable)
			const taskKey = `manual-${Date.now()}`;
			const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, keyArg, agenticdocRoot);
			// Cross-key write guard (AC-003): the SAME decision function the
			// dispatch_worker tool uses. A key another window holds live must be refused
			// before the docs gate, the frontmatter plan and — decisively — before any
			// mkdir/task.md/queue write, so a refusal is zero-side-effect. The implicit
			// path never reaches here with a foreign key (resolveOwnerKeyWithSync degrades
			// to _scratch); an explicit `--key` is what makes this reachable, exactly like
			// the tool's explicit-key branch.
			const crossKeyRefusal = foreignLiveClaimRefusal(indexStore, ownerKey);
			if (crossKeyRefusal) {
				ctx.ui.notify(crossKeyRefusal, "warning");
				return;
			}
			// AC-005a (T-02): the SAME write-intent judgement the dispatch_worker
			// tool runs — a writeless role without bash cannot satisfy an external
			// write order, so it is refused before mkdir/task.md/queue. A shell role
			// (`research`) is never refused here. Escape hatch: --allow-foreign-write.
			const writelessRole = isWritelessRole(typeField);
			const taskDir = workerTaskDir(agenticdocRoot, ownerKey, taskKey);
			if (writelessRole) {
				const verdict = judgeWriteIntent({
					type: typeField,
					description,
					taskDir,
					projectRoot: projectDir,
					keyDir: path.join(agenticdocRoot, ownerKey),
					trueRoot: agenticdocRoot,
					allowForeignWrite: allowForeignWriteArg,
				});
				if (!verdict.ok) {
					ctx.ui.notify(
						writeIntentRefusal({ taskKey, type: typeField, path: verdict.violations[0]?.path ?? "" }),
						"warning",
					);
					return;
				}
			}
			// Docs gate, phase-tiered (mw-worker-visibility-gate): same tier rule as
			// dispatch_worker — one phase read, reused by the frontmatter below.
			const ownerPhase = dispatchPhase(agenticdocRoot, ownerKey);
			const docGaps = dispatchDocGaps(agenticdocRoot, ownerKey, ownerPhase);
			if (docGaps.length > 0) {
				ctx.ui.notify(
					`Worker dispatch blocked ('${ownerKey}'): ${docGaps.join("; ")}. Generate the phase docs first or dispatch under _scratch.`,
					"warning",
				);
				return;
			}
			// G-1 tool-layer envelope gate (T-02): same decision function as the
			// dispatch_worker tool — an incomplete/missing card refuses before
			// mkdir/task.md/queue with zero side effects.
			const cardGate = readDispatchCard({
				cardPath: cardArg,
				ownerKey,
				agenticdocRoot,
				projectDir,
			});
			if (!cardGate.ok) {
				ctx.ui.notify(dispatchCardRefusal(cardGate), "warning");
				return;
			}
			// T-11/M1: `plan` stops BEFORE task.md/queue (zero side effects, GC-3).
			const splitGate = planReviewSplitGate({ cardPath: cardArg, taskKey, ownerKey, agenticdocRoot, projectDir });
			if (splitGate !== null) return ctx.ui.notify(splitGate.text, "info");
			// Model plan before any write: a refusal must leave no task dir.
			const modelPlan = planDispatchFrontmatter({
				cwd: projectDir,
				cli,
				provider,
				taskType: typeField,
				phase: ownerPhase,
				description,
				images: imagesArg,
				model,
				modelReason,
				registry: ctx.modelRegistry,
				triageRun,
				// T03: same material/association facts as dispatch_worker.
				dp1: {
					key: ownerKey,
					taskKey,
					sections: cardGate.sections,
					taskBefore: captureDecisionTaskState(workerStore, ownerKey, taskKey),
				},
			});
			if (!modelPlan.ok) {
				ctx.ui.notify(modelPlan.message, "warning");
				return;
			}
			// DP-1 ledger + (on disagreement) the one PM wake for this dispatch.
			emitDispatchTriage(pi, agenticdocRoot, modelPlan.triage);
			const written = writeDispatchTaskMd(
				{ agenticdocRoot, ownerKey },
				{
					taskKey,
					type: typeField,
					body: description,
					frontmatter: modelPlan.frontmatter,
					writeScope:
						writelessRole && isShellRole(typeField) ? renderDefaultWriteScope(ownerKey, taskKey) : undefined,
					// T-02/design §4: same claims-backed read budget as dispatch_worker.
					readScope: cardGate.caps === null ? undefined : claimReadScope(ownerKey, cardGate.claims),
					readFileCap: cardGate.caps?.fileCap,
					readByteCap: cardGate.caps?.byteCap,
					injectWriteSurface: writelessRole,
					allowForeignWrite: allowForeignWriteArg,
					card: { headerPath: cardGate.headerPath, sha256: cardGate.sha256, sections: cardGate.sections },
					// T-08/T-04c: the decision this dispatch ADOPTED (D-041). `suggest` and
					// unavailable advice carry no decision, so the bytes stay pre-T-08.
					decision: modelPlan.triage?.decision,
					// T-04d: record which dp1 state shape the child actually received.
					decisionTrace: modelPlan.triage?.stateTrace,
				},
			);
			const taskMdPath = written.path;

			// Dispatch directly to _workers.parallel
			const outcome = await dispatchTask(
				{ taskKey, status: "pending", cli, provider, model, taskPath: taskMdPath },
				workerStore,
			);
			if (!outcome.ok) {
				cleanupRefusedTaskDir(taskMdPath);
				const dp1Feedback = formatDp1ConsumerReceipt(
					await writeDp1DispatchFeedback({
						projectDir,
						triage: modelPlan.triage,
						lifecycleRun,
						taskKey,
						dispatchedType: typeField,
						refused: true,
						taskAfter: captureDecisionTaskState(workerStore, ownerKey, taskKey),
					}),
				);
				ctx.ui.notify(
					writeFaceRefusalText(taskKey, outcome) + (dp1Feedback === "" ? "" : `\n${dp1Feedback}`),
					"warning",
				);
				return;
			}

			const dp1Feedback = formatDp1ConsumerReceipt(
				await writeDp1DispatchFeedback({
					projectDir,
					triage: modelPlan.triage,
					lifecycleRun,
					taskKey,
					dispatchedType: typeField,
					refused: false,
					taskAfter: captureDecisionTaskState(workerStore, ownerKey, taskKey),
				}),
			);
			ctx.ui.notify(
				appendTriageReceipt(
					`Dispatched ${cli} worker (${taskKey}) under key '${ownerKey}' [type: ${typeField}, role: ${roleForTaskType(typeField)}, ${modelPlan.echo}].`,
					modelPlan.triage,
				) +
					claimsReceiptLine(cardGate) +
					(dp1Feedback === "" ? "" : `\n${dp1Feedback}`),
				"info",
			);
		},
	});
}

/**
 * Render the RAG row exactly like `mw.py:_format_rag_doctor_line` (D-308): an
 * `error` wins, an empty `enabled` list yields the not-enabled form, otherwise
 * `enabled=<a, b>; probe=<name=reachable|unreachable, ...>; fingerprint=<first
 * 12>; skill=<status>` plus `; required_missing=N` when N > 0. Probe names are
 * sorted the same way (`sorted(probe.items())`). Pure, so the cross-language
 * text can be asserted byte-for-byte against the Python line for one JSON.
 */
export function formatRagDoctorLine(rag: NonNullable<DoctorJson["rag"]>): string {
	if (rag.error) return `rag: ERROR - ${rag.error}`;
	const enabled = rag.enabled ?? [];
	const skillStatus = rag.skill?.status ?? "unknown";
	if (enabled.length === 0) return `rag: not enabled (skill ${skillStatus})`;
	const probe = rag.probe ?? {};
	const state = Object.keys(probe)
		.sort()
		.map((name) => `${name}=${probe[name]?.reachable ? "reachable" : "unreachable"}`)
		.join(", ");
	const fingerprint = (rag.fingerprint ?? "").slice(0, 12);
	const rawRequired = rag.required_missing ?? 0;
	const requiredMissing = Number.isFinite(rawRequired) ? Math.trunc(rawRequired) : 0;
	const required = requiredMissing ? `; required_missing=${requiredMissing}` : "";
	return `rag: enabled=${enabled.join(", ")}; probe=${state}; fingerprint=${fingerprint}; skill=${skillStatus}${required}`;
}

/**
 * `mw.py doctor` prints its RAG row only when `mw.py:523` sees
 * `rag.exists or rag.enabled`. `_doctor_rag` always returns a dict, so a
 * presence test alone would add a `not enabled` row to a project with no RAG
 * config at all. Mirroring that gate keeps the window text equal to the
 * terminal text in both directions (D-308/AC-304).
 */
export function shouldShowRagDoctorRow(rag: DoctorJson["rag"]): rag is NonNullable<DoctorJson["rag"]> {
	return rag !== undefined && (rag.exists === true || (rag.enabled?.length ?? 0) > 0);
}

/** Format a doctor JSON report as a readable Chinese summary (same data as
 * the CLI text output — the TS side never re-implements checks, AC-007). */
export function formatDoctorReport(report: DoctorJson, fix: boolean): string {
	const lines: string[] = [];
	const svc = report.service;
	lines.push(svc?.running ? `服务: 运行中 (PID ${svc.pid ?? "?"})` : "服务: 未运行");

	const proxyParts = (report.proxy ?? []).map(
		(p) => `${p.route ?? "?"}/${p.port ?? "?"} ${p.listening ? "监听中" : "未监听"}`,
	);
	if (proxyParts.length > 0) lines.push(`代理端口: ${proxyParts.join("; ")}`);

	const orphan = report.orphan_proxy;
	if (orphan?.detected) {
		const ports = (orphan.ports ?? []).map((p) => `${p.port} (PID ${(p.owner_pids ?? []).join(",") || "?"})`);
		lines.push(`孤儿代理: ${ports.join("; ")}（mw 未运行但端口被占，可启动 mw 接管或处置占用进程）`);
	}

	const log = report.launcher_log;
	if (log?.exists) {
		lines.push(`launcher 日志: ${log.error_count ?? 0} 个错误行${log.fatal ? "（含 FATAL）" : ""}`);
	} else {
		lines.push("launcher 日志: 无日志文件");
	}

	const queue = report.queue;
	lines.push(
		`队列: ${queue?.non_terminal?.length ?? 0} 个进行中任务，${
			queue?.stale_count ?? 0
		} 个 stale，${queue?.archived_total ?? 0} 条已归档`,
	);

	// Worker liveness (mw doctor worker_liveness section — informational).
	// Stale workers are named so the PM sees which task is suspected hung.
	const liveness = report.worker_liveness ?? [];
	if (liveness.length > 0) {
		const alive = liveness.filter((v) => v.verdict === "alive").length;
		const stale = liveness.filter((v) => v.verdict === "stale").map((v) => v.task_key ?? "?");
		const noHb = liveness.filter((v) => v.verdict === "no-heartbeat").length;
		const parts = [`存活 ${alive}`];
		if (stale.length > 0) parts.push(`疑似挂起: ${stale.join(", ")}`);
		if (noHb > 0) parts.push(`无心跳 ${noHb}`);
		lines.push(`worker 活性: ${parts.join("; ")}`);
	}

	const credParts = (report.credentials?.routes ?? []).map(
		(r) => `${r.route ?? "?"} ${r.available ? "可用" : "缺凭证"}`,
	);
	if (credParts.length > 0) lines.push(`路由凭证: ${credParts.join("; ")}（以 mw 进程 env 为准）`);

	const bundle = report.bundle;
	if (bundle?.available) {
		lines.push(bundle.stale ? "扩展 bundle: 源码较新，建议 /mw build 重建" : "扩展 bundle: 最新");
	}

	// pi shellPath row (fresh-machine shell bootstrap; non-Windows reports
	// not-applicable and stays silent here).
	const piShell = report.pi_shell;
	if (piShell?.status === "ok") {
		lines.push(`pi shell: ${piShell.shell_path ?? "?"}`);
	} else if (piShell?.status && piShell.status !== "not-applicable") {
		lines.push(`pi shell: ${piShell.status} — ${piShell.detail ?? ""}`);
	}

	// Dispatch model defaults row (silent when nothing is configured).
	const dispatch = report.dispatch;
	if (dispatch?.exists) {
		if (dispatch.error) {
			lines.push(`派发模型: 配置错误 — ${dispatch.error}`);
		} else {
			const capabilities = dispatch.images ?? {};
			const roles = Object.entries(dispatch.models ?? {})
				.map(([role, value]) => `${role}=${value} images=${capabilities[role] || "unknown"}`)
				.join("; ");
			const window = dispatch.window_model || "（未记录）";
			lines.push(`派发模型: ${roles || "未设角色"}; 窗口模型 ${window}`);
		}
	}

	// RAG row (D-308), verbatim like the `mw.py doctor` text line. An older
	// mw.py without the `rag` key renders nothing here (and never throws).
	if (shouldShowRagDoctorRow(report.rag)) lines.push(formatRagDoctorLine(report.rag));

	if (fix) {
		const applied = report.fix?.applied;
		lines.push(Array.isArray(applied) && applied.length > 0 ? `已自动修复: ${applied.join("; ")}` : "无可自动修复项");
	}

	const summary = report.summary;
	if (summary?.healthy) {
		lines.push("整体: 健康");
	} else {
		const issues = Array.isArray(summary?.issues) ? (summary?.issues as string[]) : [];
		lines.push(issues.length > 0 ? `整体: ${issues.length} 个问题 — ${issues.join("; ")}` : "整体: 未知");
	}
	const suggestions = Array.isArray(summary?.suggestions) ? (summary?.suggestions as string[]) : [];
	for (const s of suggestions) lines.push(`建议: ${s}`);
	return lines.join("\n");
}

/** Split a command line on whitespace, honoring double-quoted segments
 * (Windows paths with spaces). Exported for tests. */
export function splitCommandLine(line: string): string[] {
	const out: string[] = [];
	let cur = "";
	let inQuote = false;
	let has = false;
	for (const ch of line) {
		if (ch === '"') {
			inQuote = !inQuote;
			has = true;
		} else if (!inQuote && /\s/.test(ch)) {
			if (has) {
				out.push(cur);
				cur = "";
				has = false;
			}
		} else {
			cur += ch;
			has = true;
		}
	}
	if (has) out.push(cur);
	return out;
}

/** Parsed /mw target set flags. */
export interface TargetSetFlags {
	game: string;
	engine?: string;
	vcs?: string;
	uproject?: string;
}

/** Parse the flag tail of `/mw target set`. null when --game is missing or a
 * known flag has no value (unknown flags are ignored — mw.py validates). */
export function parseTargetSetFlags(parts: string[]): TargetSetFlags | null {
	const flags: TargetSetFlags = { game: "" };
	for (let i = 0; i < parts.length; i++) {
		const m = /^--(game|engine|vcs|uproject)$/.exec(parts[i]);
		if (!m) continue;
		const value = parts[i + 1];
		if (value === undefined || value.startsWith("--")) return null;
		flags[m[1] as keyof TargetSetFlags] = value;
		i++;
	}
	if (!flags.game) return null;
	return flags;
}

/** /mw target — dual-workspace config from the pi window. Thin wrapper over
 * `mw.py target` (single source of parsing/validation/rendering); the runner
 * is injectable for tests. set/clear remind that dual mode applies on the
 * NEXT worker spawn — no serve restart needed (launcher resolves per spawn). */
export async function runMwTargetCommand(
	ctx: ExtensionCommandContext,
	projectDir: string,
	argsText: string,
	runner: (projectDir: string, args: string[]) => MwCliResult = targetMw,
): Promise<void> {
	const parts = splitCommandLine(argsText);
	const action = parts[0] ?? "";
	if (action === "show" || action === "clear" || action === "on" || action === "off") {
		const r = runner(projectDir, [action]);
		ctx.ui.notify(
			r.ok ? r.output || `mw target ${action}: ok` : `mw target ${action} failed: ${r.error}`,
			r.ok ? "info" : "error",
		);
		return;
	}
	if (action === "set") {
		const flags = parseTargetSetFlags(parts.slice(1));
		if (!flags) {
			ctx.ui.notify(
				"Usage: /mw target set --game <dir> [--engine <dir>] [--vcs git|p4|none] [--uproject <file>] — quote paths containing spaces",
				"warning",
			);
			return;
		}
		const args = ["set", `--game=${flags.game}`];
		if (flags.engine !== undefined) args.push(`--engine=${flags.engine}`);
		if (flags.vcs !== undefined) args.push(`--vcs=${flags.vcs}`);
		if (flags.uproject !== undefined) args.push(`--uproject=${flags.uproject}`);
		const r = runner(projectDir, args);
		ctx.ui.notify(
			r.ok
				? `${r.output}\nDual mode takes effect on the next worker spawn (no serve restart needed).`
				: `mw target set failed: ${r.error}`,
			r.ok ? "info" : "error",
		);
		return;
	}
	ctx.ui.notify(
		"Usage: /mw target show | set --game <dir> [--engine <dir>] [--vcs git|p4|none] [--uproject <file>] | clear | on | off",
		"warning",
	);
}

/** Parsed /mw partition set flags. `roots` keeps the raw NAME=DIR values in
 * command-line order (repeatable flag — order is forwarded verbatim). */
export interface PartitionSetFlags {
	parent: string;
	partition?: string;
	vcs?: string;
	roots: string[];
}

/** Parse the flag tail of `/mw partition set`. null when --parent is missing
 * or a known flag has no value (unknown flags are ignored — mw.py validates). */
export function parsePartitionSetFlags(parts: string[]): PartitionSetFlags | null {
	const flags: PartitionSetFlags = { parent: "", roots: [] };
	for (let i = 0; i < parts.length; i++) {
		const m = /^(--parent|--partition|--vcs|--root)$/.exec(parts[i]);
		if (!m) continue;
		const value = parts[i + 1];
		if (value === undefined || value.startsWith("--")) return null;
		if (m[1] === "--root") {
			flags.roots.push(value);
		} else {
			flags[m[1].slice(2) as "parent" | "partition" | "vcs"] = value;
		}
		i++;
	}
	if (!flags.parent) return null;
	return flags;
}

/** /mw partition — partition-workspace config from the pi window (mw-target-
 * partition D-010). Thin wrapper over `mw.py partition` (single source of
 * parsing/validation/rendering — the same entry point a direct CLI run hits,
 * so identical args ⇒ identical target.yml bytes); the runner is injectable
 * for tests. set/on remind that the mode applies on the NEXT worker spawn —
 * no serve restart needed (launcher resolves per spawn). */
export async function runMwPartitionCommand(
	ctx: ExtensionCommandContext,
	projectDir: string,
	argsText: string,
	runner: (projectDir: string, args: string[]) => MwCliResult = partitionMw,
): Promise<void> {
	const parts = splitCommandLine(argsText);
	const action = parts[0] ?? "";
	if (action === "show" || action === "clear" || action === "on" || action === "off") {
		const r = runner(projectDir, [action]);
		ctx.ui.notify(
			r.ok ? r.output || `mw partition ${action}: ok` : `mw partition ${action} failed: ${r.error}`,
			r.ok ? "info" : "error",
		);
		return;
	}
	if (action === "set") {
		const flags = parsePartitionSetFlags(parts.slice(1));
		if (!flags) {
			ctx.ui.notify(
				"Usage: /mw partition set --parent <dir> [--partition <dir>] [--root name=<dir> ...] [--vcs git|p4|none] — quote paths containing spaces",
				"warning",
			);
			return;
		}
		const args = ["set", `--parent=${flags.parent}`];
		if (flags.partition !== undefined) args.push(`--partition=${flags.partition}`);
		if (flags.vcs !== undefined) args.push(`--vcs=${flags.vcs}`);
		for (const root of flags.roots) args.push(`--root=${root}`);
		const r = runner(projectDir, args);
		ctx.ui.notify(
			r.ok
				? `${r.output}\nPartition mode takes effect on the next worker spawn (no serve restart needed).`
				: `mw partition set failed: ${r.error}`,
			r.ok ? "info" : "error",
		);
		return;
	}
	ctx.ui.notify(
		"Usage: /mw partition show | set --parent <dir> [--partition <dir>] [--root name=<dir> ...] [--vcs git|p4|none] | clear | on | off",
		"warning",
	);
}

/** /mw model — dispatch model defaults from the pi window. Thin wrapper over
 * `mw.py model` (single source of parsing/validation/rendering); the runner is
 * injectable for tests. set/clear remind when the change takes effect:
 * worker roles on the next spawn (launcher resolves per spawn, no serve
 * restart), `main` at the next window start (session_start application).
 * `set-fallback`/`clear-fallback` edit the ordered per-task-type fallback
 * chain (mw-model-fallback-cli); the window face takes effect on the next
 * worker spawn too, since the launcher reads the chain per spawn. */
export async function runMwModelCommand(
	ctx: ExtensionCommandContext,
	projectDir: string,
	argsText: string,
	runner: (projectDir: string, args: string[]) => MwCliResult = modelMw,
): Promise<void> {
	const parts = splitCommandLine(argsText);
	const action = parts[0] ?? "show";
	if (action === "show") {
		const r = runner(projectDir, ["show"]);
		ctx.ui.notify(
			r.ok ? r.output || "mw model show: ok" : `mw model show failed: ${r.error}`,
			r.ok ? "info" : "error",
		);
		return;
	}
	if (action === "set") {
		const role = parts[1];
		const value = parts[2];
		if (!role || !value || parts.length > 3) {
			ctx.ui.notify(
				"Usage: /mw model set <role> <prefix/model> — roles: main, coding, review, research, vision, decide_prepare (e.g. /mw model set review timi/gpt-5.6-sol)",
				"warning",
			);
			return;
		}
		// Earliest catch for a bad id (design D-010): a prefixed value names its
		// own route, so the registry can check it before Python writes the file
		// (a bare id keeps the task's route — not checkable here). Python stays
		// the single source for role/schema validation.
		const validation = validateModelValue(ctx.modelRegistry, "pi", "", value);
		if (!validation.ok) {
			ctx.ui.notify(validation.message, "error");
			return;
		}
		const r = runner(projectDir, ["set", role, value]);
		ctx.ui.notify(
			r.ok
				? `${r.output}\nWorker roles apply on the next spawn (no serve restart); main applies at the next window start.`
				: `mw model set failed: ${r.error}`,
			r.ok ? "info" : "error",
		);
		return;
	}
	if (action === "clear") {
		const role = parts[1];
		if (!role || parts.length > 2) {
			ctx.ui.notify("Usage: /mw model clear <role|all>", "warning");
			return;
		}
		const r = runner(projectDir, ["clear", role]);
		ctx.ui.notify(
			r.ok ? r.output || "mw model clear: ok" : `mw model clear failed: ${r.error}`,
			r.ok ? "info" : "error",
		);
		return;
	}
	if (action === "set-fallback" || action === "clear-fallback") {
		const taskType = parts[1];
		const expectsChain = action === "set-fallback";
		const chain = parts[2];
		if (!taskType || (expectsChain && (!chain || parts.length > 3)) || (!expectsChain && parts.length > 2)) {
			ctx.ui.notify(
				expectsChain
					? "Usage: /mw model set-fallback <task-type> <prefix/model[,prefix/model...]> - 1..4 models, tried in order (e.g. /mw model set-fallback review timi/deepseek-v4.1-flash,zai/glm-5.3)"
					: "Usage: /mw model clear-fallback <task-type>",
				"warning",
			);
			return;
		}
		// Thin wrapper: Python owns role/schema validation (same as set/clear).
		const args = expectsChain ? [action, taskType, chain] : [action, taskType];
		const r = runner(projectDir, args);
		ctx.ui.notify(
			r.ok ? r.output || `mw model ${action}: ok` : `mw model ${action} failed: ${r.error}`,
			r.ok ? "info" : "error",
		);
		return;
	}
	ctx.ui.notify(
		"Usage: /mw model show | set <role> <prefix/model> | clear <role|all> | set-fallback <task-type> <chain> | clear-fallback <task-type>",
		"warning",
	);
}

/** /mw command description (exported so the registration test can assert the
 * RAG branch stays documented — VC-311). */
export const MW_COMMAND_DESCRIPTION =
	"Control mw: build / init / start / stop / restart / status / doctor / update / target / partition / model / decide / rag / stats / run-detached / ack";

/** Lines of `mw rag` output shown before truncation (D-307): the notify channel
 * is narrow, and `rag list` / `rag audit` outputs can be long. */
export const RAG_OUTPUT_MAX_LINES = 30;

/** Truncation footer (D-307): hand the user the exact command for the full
 * output instead of dropping it silently. `<sub>` / `<dir>` stay placeholders —
 * formatRagOutput only ever sees the output text. */
export const RAG_FULL_OUTPUT_HINT = "完整输出：python mw.py rag <sub> --project <dir>";

/**
 * Parse `/mw rag <raw>` into the subcommand and its verbatim argument tail.
 * Pure and CLI-free (VC-307): an empty or unknown sub returns the usage text
 * naming every RAG_SUBCOMMANDS entry, so the caller can reject before any
 * spawn. Arguments after the sub pass through untouched — Python stays the
 * single source of argument semantics.
 */
export function parseRagArgs(raw: string): { sub: string; rest: string[] } | { usage: string } {
	const usage = `Usage: /mw rag <sub> [args...] — sub: ${RAG_SUBCOMMANDS.join(
		" | ",
	)}. Arguments are forwarded to mw.py rag verbatim.`;
	const parts = splitCommandLine(raw);
	const sub = parts[0] ?? "";
	if (!(RAG_SUBCOMMANDS as readonly string[]).includes(sub)) return { usage };
	return { sub, rest: parts.slice(1) };
}

/**
 * Map a `mw.py rag` exit code to the notify level and shorten long output
 * (D-307): 0=info, 1=warning (audit findings are expected), anything else
 * error. Output over RAG_OUTPUT_MAX_LINES is truncated with the full-command
 * hint appended so nothing is lost.
 */
export function formatRagOutput(output: string, code: number): { text: string; level: "info" | "warning" | "error" } {
	const level = code === 0 ? "info" : code === 1 ? "warning" : "error";
	const text = output.replace(/\r\n/g, "\n").trim();
	if (text === "") return { text: code === 0 ? "mw rag: ok" : `mw rag exited with code ${code}`, level };
	const lines = text.split("\n");
	if (lines.length <= RAG_OUTPUT_MAX_LINES) return { text, level };
	return { text: `${lines.slice(0, RAG_OUTPUT_MAX_LINES).join("\n")}\n… ${RAG_FULL_OUTPUT_HINT}`, level };
}

/** /mw rag — thin wrapper over `mw.py rag` (single source of parsing,
 * validation and rendering); the runner is injectable for tests so the
 * unknown-sub path can be proven spawn-free (VC-307). The output content is
 * never parsed — only the exit code selects the notify level. */
export async function runMwRagCommand(
	ctx: ExtensionCommandContext,
	projectDir: string,
	raw: string,
	runner: (projectDir: string, args: string[]) => { ok: boolean; code: number; output: string } = ragMw,
): Promise<void> {
	const parsed = parseRagArgs(raw);
	if ("usage" in parsed) {
		ctx.ui.notify(parsed.usage, "warning");
		return;
	}
	const result = runner(projectDir, [parsed.sub, ...parsed.rest]);
	const formatted = formatRagOutput(result.output, result.code);
	ctx.ui.notify(formatted.text, formatted.level);
}

/** Parsed `/mw run-detached` flags + command argv (D-005/AC-008). */
export interface RunDetachedCommandFlags {
	cwd?: string;
	run_dir?: string;
	timeout_min?: number;
	heartbeat_s?: number;
	cmd: string[];
}

/**
 * Parse `/mw run-detached [--cwd <dir>] [--run-dir <dir>]
 * [--timeout-min <n>] [--heartbeat-s <n>] -- <cmd...>`. Pure and CLI-free
 * (the rag VC-307 precedent): a missing `--`, an empty command, an unknown
 * flag, or a flag without a value returns a structured usage error so the
 * caller rejects before any spawn. The argv after `--` passes through
 * verbatim — shared/run-detached.ts (and Python) stays the single source of
 * flag semantics.
 */
export function parseRunDetachedArgs(
	raw: string,
): { ok: true; flags: RunDetachedCommandFlags } | { ok: false; error: string } {
	const parts = splitCommandLine(raw);
	const flags: RunDetachedCommandFlags = { cmd: [] };
	let i = 0;
	let afterSep = false;
	while (i < parts.length) {
		const part = parts[i] ?? "";
		if (afterSep) {
			flags.cmd.push(part);
			i++;
			continue;
		}
		if (part === "--") {
			afterSep = true;
			i++;
			continue;
		}
		const eq = part.indexOf("=");
		const flag = eq === -1 ? part : part.slice(0, eq);
		const inline = eq === -1 ? undefined : part.slice(eq + 1);
		if (flag === "--cwd" || flag === "--run-dir" || flag === "--timeout-min" || flag === "--heartbeat-s") {
			const value = inline ?? parts[i + 1];
			if (value === undefined || value === "") {
				return { ok: false, error: `Usage: /mw run-detached: ${flag} needs a value` };
			}
			if (flag === "--cwd") flags.cwd = value;
			else if (flag === "--run-dir") flags.run_dir = value;
			else if (flag === "--timeout-min") {
				const n = Number(value);
				if (Number.isNaN(n)) {
					return { ok: false, error: `Usage: /mw run-detached: --timeout-min needs a number, got '${value}'` };
				}
				flags.timeout_min = n;
			} else {
				const n = Number(value);
				if (Number.isNaN(n)) {
					return { ok: false, error: `Usage: /mw run-detached: --heartbeat-s needs a number, got '${value}'` };
				}
				flags.heartbeat_s = n;
			}
			i += eq === -1 ? 2 : 1;
			continue;
		}
		return {
			ok: false,
			error: `Usage: /mw run-detached: unknown option '${part}' — use --cwd/--run-dir/--timeout-min/--heartbeat-s and put the command after '--'`,
		};
	}
	if (!afterSep || flags.cmd.length === 0) {
		return { ok: false, error: "Usage: /mw run-detached: no command after '--'" };
	}
	return { ok: true, flags };
}

/** /mw run-detached — background command dispatch (D-005/AC-008). Thin wrapper
 * over shared/run-detached.ts; the runner is injectable for tests (the rag
 * precedent). The 4-field handoff summary matches the mw_run_detached tool
 * 文案 byte for byte; failures notify a structured error and never throw. */
export async function runMwRunDetachedCommand(
	ctx: ExtensionCommandContext,
	projectDir: string,
	raw: string,
	runner: (opts: RunDetachedOptions) => RunDetachedResult = runDetachedMw,
): Promise<void> {
	const parsed = parseRunDetachedArgs(raw);
	if (!parsed.ok) {
		ctx.ui.notify(parsed.error, "warning");
		return;
	}
	const result = runner({ ...parsed.flags, cwd: parsed.flags.cwd ?? projectDir });
	if (!result.ok) {
		ctx.ui.notify(result.error, "error");
		return;
	}
	const { pid, marker, heartbeat, log } = result.handle;
	ctx.ui.notify(`dispatched pid=${pid} marker=${marker} heartbeat=${heartbeat} log=${log}`, "info");
}

/** /mw stats — thin wrapper over `mw.py stats` (mw-usage-monitor T-04/AC-006).
 * The window owns no aggregation: the raw argument tail passes through
 * untouched (`--since / --key / --type / --model / --source / --json` are
 * parsed by Python), the report is rendered by Python, and the runner is
 * injectable for tests (the rag precedent). A failure notifies at `error` with
 * the Python text verbatim — runMwCliRaw merges stderr into it, so the reason
 * (`invalid --since`, bad `--source`) is never swallowed. A thrown runner
 * (spawn-level bug) is reported the same way instead of escaping the command. */
export async function runMwStatsCommand(
	ctx: ExtensionCommandContext,
	projectDir: string,
	raw: string,
	runner: (projectDir: string, args: string[]) => MwCliResult = statsMw,
): Promise<void> {
	const args = splitCommandLine(raw);
	let result: MwCliResult;
	try {
		result = runner(projectDir, args);
	} catch (err) {
		ctx.ui.notify(`mw stats failed: ${err instanceof Error ? err.message : String(err)}`, "error");
		return;
	}
	ctx.ui.notify(
		result.ok ? result.output || "mw stats: ok" : `mw stats failed: ${result.error}`,
		result.ok ? "info" : "error",
	);
}

/** Conclusions the sign-off records (mirror of the Python
 * `decide_signoff.CONCLUSIONS`). The window never picks one — the decision model
 * produces it during the write — so the list only drives the read-only preview
 * rendering (one verdict line per conclusion). */
export const DECIDE_CONCLUSIONS = ["continue", "narrow", "revoke"] as const;

/** Usage line of the window face (the `--key` flag only exists on `sign`).
 * `sign` takes no conclusion: the decision model produces it during the write,
 * so no caller-supplied positional remains to validate. The second line
 * documents the read-only forwards (T12a): they need no key and therefore split
 * off before the watched-key requirement. */
export const DECIDE_USAGE =
	"Usage: /mw decide show | sign [--allow-empty] [--key <key>]\n" +
	"       /mw decide dp list | dp show <id> | dp export | monitor   (read-only, no key needed)";

/** The four closed read-only forwards of the window face (T12a/AC-001/AC-017).
 * Python stays the single source of parsing, rendering and of the (zero) writes. */
export type DecideForwardAction = "dp-list" | "dp-show" | "dp-export" | "monitor";

/** Parsed `/mw decide` arguments. Pure and spawn-free (the rag precedent). */
export type ParsedDecideArgs =
	| { action: "show" }
	| { action: "sign"; allowEmpty: boolean; key?: string }
	| { action: "dp-list" }
	| { action: "dp-show"; dp: string }
	| { action: "dp-export" }
	| { action: "monitor" }
	| { action: "usage"; error: string };

/** Notify label of a read-only forward. */
const DECIDE_FORWARD_LABELS: Record<DecideForwardAction, string> = {
	"dp-list": "dp list",
	"dp-show": "dp show",
	"dp-export": "dp export",
	monitor: "monitor",
};

/** One accepted read-only forward: the action plus the exact Python argv. */
export interface DecideForward {
	action: DecideForwardAction;
	argv: string[];
}

/**
 * Python argv of a read-only forward, or null when the parsed input is not one.
 *
 * This is the SINGLE argv mapping of the window face: the caller forwards the
 * returned vector verbatim, so `--write`, `--json`, `--live`, `--rows`, output
 * paths and monitor status/stop arguments are structurally unrepresentable —
 * a crafted tail can never reach Python (design §5.1: only dp list/show/export
 * and bare monitor are allowed in the window).
 */
export function decideForwardArgs(parsed: ParsedDecideArgs): DecideForward | null {
	switch (parsed.action) {
		case "dp-list":
			return { action: parsed.action, argv: ["dp", "list"] };
		case "dp-show":
			return { action: parsed.action, argv: ["dp", "show", parsed.dp] };
		case "dp-export":
			return { action: parsed.action, argv: ["dp", "export"] };
		case "monitor":
			return { action: parsed.action, argv: ["monitor"] };
		default:
			return null;
	}
}

/**
 * Parse `/mw decide [show | sign [flags] | dp list|show <id>|export | monitor]`.
 *
 * `""` / `show` is the read-only preview; bare `sign` (optionally
 * `--allow-empty`, `--key <key>`) triggers the decision model and writes what it
 * decides, so there is no conclusion positional to validate. The four read-only
 * forwards are a closed set with no free-form tail (T12a, §5.1 of the dashboard
 * design). Everything else (unknown sub, a flag without a value, a stray
 * positional, a refused dp/monitor face) returns a usage error so the caller
 * rejects without a spawn — Python stays the single source of the verdict and
 * of the machine lines.
 */
export function parseDecideArgs(argsText: string): ParsedDecideArgs {
	const parts = splitCommandLine(argsText);
	const sub = parts[0] ?? "";
	if (sub === "" || sub === "show") {
		if (parts.length > 1) {
			return { action: "usage", error: `${DECIDE_USAGE} — \`show\` takes no arguments` };
		}
		return { action: "show" };
	}
	// Read-only faces (T12a) split off BEFORE the `sign` guard and before the
	// watched-key requirement: `dp list`/`dp export` are project-level views and
	// `dp show <id>` takes its id explicitly, so a key-less window can still list
	// the same dp set as the CLI (AC-001) while every write/act face is refused
	// here, before any spawn (AC-017).
	if (sub === "dp") {
		const dpSub = parts[1];
		if (dpSub === "list" || dpSub === "export") {
			if (parts.length > 2) {
				return {
					action: "usage",
					error: `${DECIDE_USAGE} — \`dp ${dpSub}\` takes no arguments (read-only window face; --write/--json/paths are CLI-only)`,
				};
			}
			return dpSub === "list" ? { action: "dp-list" } : { action: "dp-export" };
		}
		if (dpSub === "show") {
			const dp = parts[2];
			if (dp === undefined || dp === "" || dp.startsWith("-")) {
				return { action: "usage", error: `${DECIDE_USAGE} — \`dp show\` needs a dp id` };
			}
			if (parts.length > 3) {
				return {
					action: "usage",
					error: `${DECIDE_USAGE} — \`dp show\` takes exactly one dp id (read-only window face; flags are CLI-only)`,
				};
			}
			return { action: "dp-show", dp };
		}
		const refused = dpSub === undefined ? "needs a sub" : `\`dp ${dpSub}\` is not a read-only window face`;
		return {
			action: "usage",
			error: `${DECIDE_USAGE} — ${refused} (window: dp list | dp show <id> | dp export; write/act faces are CLI-only)`,
		};
	}
	if (sub === "monitor") {
		if (parts.length > 1) {
			return {
				action: "usage",
				error: `${DECIDE_USAGE} — the window only forwards bare \`monitor\`; run mw decide monitor status|stop in the terminal`,
			};
		}
		return { action: "monitor" };
	}
	if (sub !== "sign") {
		return { action: "usage", error: `${DECIDE_USAGE} — unknown sub '${sub}'` };
	}
	let allowEmpty = false;
	let key: string | undefined;
	for (let i = 1; i < parts.length; i++) {
		const part = parts[i] ?? "";
		if (part === "--allow-empty") {
			allowEmpty = true;
			continue;
		}
		if (part === "--key") {
			const value = parts[i + 1];
			if (value === undefined || value === "" || value.startsWith("--")) {
				return { action: "usage", error: `${DECIDE_USAGE} — --key needs a value` };
			}
			key = value;
			i++;
			continue;
		}
		return { action: "usage", error: `${DECIDE_USAGE} — unexpected argument '${part}'` };
	}
	return { action: "sign", allowEmpty, key };
}

/** `facts` block of the `mw decide sign --json` preview (only what the window
 * renders; Python owns every other field). */
export interface DecidePreviewFacts {
	counted_rows?: number;
	n_available?: number;
	n_acted?: number;
	n_escalated?: number;
	engines?: Record<string, number>;
	sha256?: string;
	chain_ok?: boolean;
	p0_open?: string[];
	p0_source?: string;
}

/** `mw decide sign --json` payload. The preview leaves `conclusion`/`path`
 * null and carries every conclusion's verdict; a signed write carries the
 * conclusion, the written `path` and (when Python reports it) `signed_via`; an
 * unsigned write carries `note` (decision model unavailable) or the plain line
 * Python prints before the payload (`signoff: disable`). */
export interface DecidePreview {
	ok?: boolean | null;
	conclusion?: string | null;
	problems?: string[];
	facts?: DecidePreviewFacts;
	note?: string;
	path?: string | null;
	signed_via?: string | null;
	verdicts?: Record<string, { ok?: boolean; problems?: string[] }>;
}

/** Lines of raw preview output shown when the JSON cannot be parsed. */
export const DECIDE_ERROR_TAIL_LINES = 6;

function tailLines(text: string, max = DECIDE_ERROR_TAIL_LINES): string {
	const lines = text.replace(/\r\n/g, "\n").trim().split("\n");
	return lines.slice(-max).join("\n");
}

/** Tolerant JSON read: the whole output first, then the outermost `{...}` — a
 * banner line before the JSON must not turn into an error notification. */
function parseDecidePreview(output: string): DecidePreview | null {
	const text = output.trim();
	const candidates = [text];
	const first = text.indexOf("{");
	const last = text.lastIndexOf("}");
	if (first !== -1 && last > first) candidates.push(text.slice(first, last + 1));
	for (const candidate of candidates) {
		try {
			const parsed: unknown = JSON.parse(candidate);
			if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
				return parsed as DecidePreview;
			}
		} catch {
			// try the next candidate
		}
	}
	return null;
}

/** Render the preview facts the way `/mw decide show` prints them: the four
 * counts, the engine histogram, one verdict line per conclusion, the first 12
 * characters of `rows_sha256` and the open-P0 list. */
export function formatDecidePreview(payload: DecidePreview): string {
	const facts = payload.facts ?? {};
	const engines = Object.entries(facts.engines ?? {});
	const lines = [
		`counted_rows=${facts.counted_rows ?? 0} available=${facts.n_available ?? 0} acted=${facts.n_acted ?? 0} escalated=${facts.n_escalated ?? 0}`,
		`engines: ${engines.length > 0 ? engines.map(([name, count]) => `${name}=${count}`).join(", ") : "-"}`,
	];
	for (const conclusion of DECIDE_CONCLUSIONS) {
		const verdict = payload.verdicts?.[conclusion];
		if (verdict === undefined) {
			lines.push(`verdict ${conclusion}: (mw decide sign --json reported none)`);
			continue;
		}
		lines.push(`verdict ${conclusion}: ${verdict.ok === false ? "REFUSED" : "ok"}`);
		for (const problem of verdict.problems ?? []) lines.push(`  - ${problem}`);
	}
	lines.push(`rows_sha256: ${(facts.sha256 ?? "").slice(0, 12) || "-"}`);
	lines.push(`p0-open: ${(facts.p0_open ?? []).join(", ") || "-"}`);
	return lines.join("\n");
}

/** Injectable collaborators of `runMwDecideCommand` (tests use a stub runner
 * and a fixed watch key; production passes `decideMw` and `watch.key`). */
export interface DecideCommandDeps {
	runner?: (projectDir: string, args: string[]) => MwCliResult;
	watchKey?: () => string | undefined;
}

/** The read-only preview argv: `--dry-run` is what makes it strictly zero-write
 * (no decision-model call, no archive row, no sign-off file). `--allow-empty`
 * rides along so the reported verdicts match the intended sign-off. */
function decidePreviewArgs(key: string, allowEmpty: boolean): string[] {
	const args = ["sign", "--key", key, "--dry-run", "--json"];
	if (allowEmpty) args.push("--allow-empty");
	return args;
}

/** What a completed `mw decide sign` did. `ok`/`exit 0` alone is not enough:
 * the same exit code covers "the decision model was unavailable" and
 * "`signoff: disable`", both of which write no file. */
export interface DecideSignOutcome {
	signed: boolean;
	signedVia?: string;
	conclusion?: string;
	path?: string;
}

const SIGNED_VIA_LINE = /^[ \t]*signed_via:[ \t]*(\S+)[ \t]*$/m;
const CONCLUSION_LINE = /^[ \t]*conclusion:[ \t]*(\S+)[ \t]*$/m;
const WROTE_LINE = /^[ \t]*wrote[ \t]+(.+?)[ \t]*$/m;

/** The write-side `signed_via` vocabulary (a single value since
 * mw-signoff-decide-only, mirror of `decide_signoff.SIGNED_VIA_VALUES`). The
 * `--json` write payload proves the write with `path` but does not repeat the
 * field, so a signed JSON run is labelled with this value instead of dropping
 * the line the text face prints. */
const SIGNED_VIA_AUTO = "auto-decide";

/** Read a write result. The text face prints `signed_via: <value>` (and the
 * `conclusion:` machine line) only after the file landed; the `--json` face
 * proves the same with a non-null `path` and carries the conclusion. Nothing
 * else counts as signed — a run that wrote no file must never display as a
 * signature (AC-005). */
export function parseDecideSignOutcome(output: string): DecideSignOutcome {
	const text = output.replace(/\r\n/g, "\n");
	const payload = parseDecidePreview(text);
	const jsonSignedVia = payload?.signed_via;
	const signedVia =
		SIGNED_VIA_LINE.exec(text)?.[1] ??
		(typeof jsonSignedVia === "string" && jsonSignedVia !== "" ? jsonSignedVia : undefined);
	const jsonPath = payload?.path;
	const wroteLine = WROTE_LINE.exec(text)?.[1];
	const path =
		typeof jsonPath === "string" && jsonPath !== ""
			? jsonPath
			: wroteLine !== undefined && wroteLine !== ""
				? wroteLine
				: undefined;
	const jsonConclusion = payload?.conclusion;
	const conclusion =
		CONCLUSION_LINE.exec(text)?.[1] ??
		(typeof jsonConclusion === "string" && jsonConclusion !== "" ? jsonConclusion : undefined);
	return { signed: signedVia !== undefined || path !== undefined, signedVia, conclusion, path };
}

/** Human reason of an unsigned run: the JSON `note` (decision model unavailable)
 * or the plain line Python prints before the payload (`signoff: disable`). */
export function parseDecideUnsignedReason(output: string, payload: DecidePreview | null): string {
	if (typeof payload?.note === "string" && payload.note !== "") return payload.note;
	const firstJson = output.indexOf("{");
	const head = (firstJson === -1 ? output : output.slice(0, firstJson)).replace(/\r\n/g, "\n").trim();
	return head !== "" ? head : "decision model unavailable / sign-off not required";
}

/** One result of the decide face: notify when a UI exists, and hand the same
 * text back so the command handler can put it into the transcript when there is
 * none — `ctx.ui.notify` is a no-op in headless `-p`/worker sessions, and the
 * result must not be lost there (AC-007). */
function reportDecide(ctx: ExtensionCommandContext, text: string, level: "info" | "warning" | "error"): string {
	if (ctx.hasUI) ctx.ui.notify(text, level);
	return text;
}

/**
 * One read-only forward (T12a): Python owns argument validation, rendering and
 * the (zero) writes — the window only relays `argv` and displays the text.
 * A thrown runner (spawn-level bug) is reported like a failed spawn instead of
 * escaping the command, so a broken mw.py never takes the window down.
 *
 * `monitor` is routing only: the service lifetime and the Chromium app window
 * belong to the Python side, so a failure here reports Python's reason and
 * never claims that a window opened (AC-006 is not asserted by this face).
 *
 * Returns the text it displayed so a headless caller can put it into the
 * transcript (see `reportDecide`).
 */
async function forwardDecideReadOnly(
	ctx: ExtensionCommandContext,
	projectDir: string,
	forward: DecideForward,
	runner: (projectDir: string, args: string[]) => MwCliResult,
): Promise<string> {
	const { action, argv } = forward;
	const label = DECIDE_FORWARD_LABELS[action];
	let result: MwCliResult;
	try {
		result = runner(projectDir, argv);
	} catch (err) {
		return reportDecide(
			ctx,
			`mw decide ${label} failed: ${err instanceof Error ? err.message : String(err)}`,
			"error",
		);
	}
	if (!result.ok) {
		const hint =
			action === "monitor"
				? "\n(窗口只转发 `mw decide monitor`；服务与开窗由 Python 侧负责 — status|stop 请在终端跑 mw decide monitor status|stop)"
				: "";
		return reportDecide(ctx, `mw decide ${label} failed: ${result.error}${hint}`, "error");
	}
	return reportDecide(ctx, result.output || `mw decide ${label}: ok`, "info");
}

/**
 * `/mw decide show|sign` — the window face of the decision-model sign-off
 * (mw-signoff-decide-only: the decision model signs, nothing else does).
 *
 * `show` runs the read-only preview (`mw decide sign --key <k> --dry-run
 * --json`, strictly zero-write) and prints the facts. `sign` runs the same
 * preview as a read-only pre-check, then forwards `mw decide sign --key <k>
 * --json` once: no dialog, and the window supplies no conclusion — Python asks
 * the decision model and writes only when it answers. Guard rails, in order:
 *   1. the four read-only forwards (`dp list|show|export`, `monitor`) split off
 *      first: no dialog and no key are involved, so a key-less window can still
 *      read the dp table while the write/act tail is refused before any spawn;
 *   2. the key is `--key` > the watched key > a usage error (never guessed);
 *   3. Python stays authoritative: its verdict (exit 2, zero writes) still runs
 *      on the write call, and `exit 0` is split into signed (`signed_via:` line /
 *      non-null `path`) vs unsigned (decision model unavailable / `signoff:
 *      disable`) so a run that wrote nothing never displays as a signature.
 * No `--auto` and no `--project` are forwarded: `--auto` would persist
 * `signoff: auto` over a project's `signoff: disable`, and `decideMw` appends
 * the control root. The runner is injectable so every branch is provable
 * without a spawn.
 *
 * Every result is also returned as text: `ctx.ui.notify` is a no-op without a
 * UI (headless / `-p` / worker), so the `/mw` handler puts the return value into
 * the transcript instead (AC-007 — no silent loss).
 */
export async function runMwDecideCommand(
	ctx: ExtensionCommandContext,
	projectDir: string,
	argsText: string,
	deps: DecideCommandDeps = {},
): Promise<string> {
	const parsed = parseDecideArgs(argsText);
	if (parsed.action === "usage") return reportDecide(ctx, parsed.error, "warning");
	// Read-only faces first (T12a/AC-001): `dp list|show|export` and `monitor`
	// need neither an interactive dialog nor a watched key, so they are resolved
	// before the key guard. `decideForwardArgs` returns the exact Python argv — no
	// caller-supplied flag survives (AC-017).
	const forward = decideForwardArgs(parsed);
	if (forward !== null) {
		return await forwardDecideReadOnly(ctx, projectDir, forward, deps.runner ?? decideMw);
	}
	// Exhaustiveness guard, not a live branch: every parsed action other than
	// `show`/`sign` has a forward argv, so this only keeps the compiler's
	// narrowing honest (`parsed` is the sign face below) and fails closed with
	// the usage line if a future variant forgets an argv mapping.
	if (parsed.action !== "show" && parsed.action !== "sign") {
		return reportDecide(ctx, DECIDE_USAGE, "warning");
	}
	const key = (parsed.action === "sign" ? parsed.key : undefined) ?? deps.watchKey?.();
	if (!key) {
		return reportDecide(
			ctx,
			`${DECIDE_USAGE} — 无法确定 key，请给 --key <key>（或先 /worker watch <key>）`,
			"warning",
		);
	}
	const runner = deps.runner ?? decideMw;

	let preview: MwCliResult;
	try {
		preview = runner(projectDir, decidePreviewArgs(key, parsed.action === "sign" ? parsed.allowEmpty : false));
	} catch (err) {
		return reportDecide(ctx, `mw decide 预览失败: ${err instanceof Error ? err.message : String(err)}`, "error");
	}
	if (!preview.ok) return reportDecide(ctx, `mw decide 预览失败: ${preview.error}`, "error");
	const payload = parseDecidePreview(preview.output);
	if (payload === null) {
		return reportDecide(ctx, `mw decide 预览输出不是 JSON，原文尾部:\n${tailLines(preview.output)}`, "error");
	}

	if (parsed.action === "show") {
		return reportDecide(
			ctx,
			`${formatDecidePreview(payload)}\n(preview only — nothing written; /mw decide sign 触发决策模型判定，判据通过时写入)`,
			"info",
		);
	}

	// The write argv: Python asks the decision model and writes what it answers.
	// No `--auto` (it would persist `signoff: auto` over a project's
	// `signoff: disable`), no caller-supplied conclusion, no exemption flag, and
	// no `--project` (`decideMw` appends the control root).
	let written: MwCliResult;
	try {
		written = runner(projectDir, ["sign", "--key", key, "--json"]);
	} catch (err) {
		return reportDecide(
			ctx,
			`mw decide sign ${key} 写入失败: ${err instanceof Error ? err.message : String(err)}`,
			"error",
		);
	}
	if (!written.ok) return reportDecide(ctx, `mw decide sign ${key} 写入失败: ${written.error}`, "error");

	const outcome = parseDecideSignOutcome(written.output);
	if (!outcome.signed) {
		const reason = parseDecideUnsignedReason(written.output, parseDecidePreview(written.output));
		return reportDecide(
			ctx,
			`未签收 ${key}：${reason}\n` +
				`(decision model unavailable / sign-off not required — 未写 ${key}/evidence/review/sign-final.md)`,
			"info",
		);
	}
	const lines = [`已签收 ${key} → ${outcome.path ?? `${key}/evidence/review/sign-final.md`}`];
	lines.push(`signed_via: ${outcome.signedVia ?? SIGNED_VIA_AUTO}`);
	if (outcome.conclusion !== undefined) lines.push(`conclusion: ${outcome.conclusion}`);
	lines.push("authority-change 档案行已追加。");
	return reportDecide(ctx, lines.join("\n"), "info");
}

export function registerMwCommands(
	pi: ExtensionAPI,
	projectDir: string,
	workerStore: WorkerStore,
	ackStore: AckStore,
	watch: PmWatchState,
	agenticdocRoot: string,
): void {
	pi.registerCommand("mw", {
		description: MW_COMMAND_DESCRIPTION,
		handler: async (_args: string, ctx: ExtensionCommandContext) => {
			const trimmed = _args.trim();
			const sub = trimmed.split(/\s+/)[0] ?? "status";

			if (sub === "build") {
				ctx.ui.notify("Rebuilding extension bundle (bash-free)…", "info");
				const r = buildMw();
				if (r.ok) {
					ctx.ui.notify(`mw build OK — reinstalled globally. Restart pi windows to load it.\n${r.output}`, "info");
				} else {
					ctx.ui.notify(`mw build failed: ${r.error}`, "error");
				}
				return;
			}

			if (sub === "init") {
				const result = initMw(projectDir);
				if (result.ok) {
					ctx.ui.notify("mw init complete — .agenticdoc/ .mw/ .pi/extensions/ created.", "info");
				} else {
					ctx.ui.notify(result.error, "error");
				}
				return;
			}

			if (sub === "doctor") {
				const fix = _args.trim().split(/\s+/)[1]?.toLowerCase() === "fix";
				const r = doctorMw(projectDir, fix);
				if (r.ok) {
					ctx.ui.notify(formatDoctorReport(r.report, fix), "info");
				} else {
					ctx.ui.notify(`mw doctor 执行失败: ${r.error}`, "error");
				}
				return;
			}

			if (sub === "update") {
				// Incremental self-check over the update anchors (UPDATE.md §1):
				// bundle / pi dist / serve / framework propagation. Python stays
				// the single source of the checks; --apply runs the safe fixes.
				const apply = _args.trim().split(/\s+/)[1]?.toLowerCase() === "--apply";
				ctx.ui.notify(
					apply
						? "mw update-env --apply running (bundle/dist rebuild + reinstall can take a minute)…"
						: "mw update-env checking anchors…",
					"info",
				);
				const r = updateEnvMw(projectDir, apply);
				ctx.ui.notify(r.ok ? r.output : `mw update-env 执行失败: ${r.error}`, r.ok ? "info" : "error");
				return;
			}

			if (sub === "status") {
				const s = getMwStatus(projectDir);
				if (!s.running) {
					ctx.ui.notify("mw not running", "info");
					return;
				}
				const stale = serveStaleness(projectDir);
				ctx.ui.notify(
					stale?.stale
						? `mw running (PID ${s.pid}) — STALE CODE (${stale.detail}). Run /mw restart.`
						: `mw running (PID ${s.pid})`,
					stale?.stale ? "warning" : "info",
				);
				return;
			}

			if (sub === "start") {
				const s = getMwStatus(projectDir);
				if (s.running) {
					ctx.ui.notify(`mw already running (PID ${s.pid})`, "info");
					return;
				}
				const ok = startMw(projectDir);
				ctx.ui.notify(
					ok ? "mw starting in background…" : "Could not find mw.py — set MW_PY env var.",
					ok ? "info" : "error",
				);
				return;
			}

			if (sub === "stop") {
				const s = getMwStatus(projectDir);
				if (!s.running) {
					ctx.ui.notify("mw is not running", "info");
					return;
				}
				stopMw(projectDir);
				ctx.ui.notify("mw stop signal sent", "info");
				return;
			}

			if (sub === "restart") {
				ctx.ui.notify("mw restarting (graceful stop, then start)...", "info");
				const r = await restartMw(projectDir);
				if (r === "restarted") {
					const s = getMwStatus(projectDir);
					ctx.ui.notify(
						`mw restarted (PID ${s.pid ?? "?"}) — in-flight workers are adopted by the new launcher's orphan reconcile.`,
						"info",
					);
				} else if (r === "stop-failed") {
					ctx.ui.notify("mw restart failed: serve did not exit in time — run /mw doctor.", "error");
				} else {
					ctx.ui.notify("mw restart failed: serve did not come up — run /mw doctor.", "error");
				}
				return;
			}

			if (sub === "target") {
				// Dual-workspace config (mw.py target show/set/clear/on/off) — thin
				// wrapper, Python stays the single source of parsing and validation.
				await runMwTargetCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
				return;
			}

			if (sub === "partition") {
				// Partition-workspace config (mw.py partition set/show/clear/on/off) —
				// thin wrapper, Python stays the single source of parsing and validation.
				await runMwPartitionCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
				return;
			}

			if (sub === "model") {
				// Dispatch model defaults + fallback chains (mw.py model show/set/clear/
				// set-fallback/clear-fallback) — thin wrapper, Python stays the single
				// source of parsing and validation.
				await runMwModelCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
				return;
			}

			if (sub === "decide") {
				// Decision archive + sign-off: `show` is the read-only preview; `sign`
				// forwards the decision-model sign-off — no dialog, no caller conclusion,
				// no exemption flag: Python asks the model and writes what it answers (or
				// reports that the decision model was unavailable). The returned text
				// goes to the transcript when there is no UI (headless `-p` / worker),
				// where ctx.ui.notify is a no-op (AC-007).
				// T12a adds the closed read-only set (dp list/show/export, monitor),
				// resolved inside runMwDecideCommand before the watched-key guard.
				const text = await runMwDecideCommand(ctx, projectDir, trimmed.slice(sub.length).trim(), {
					watchKey: () => watch.key,
				});
				if (!ctx.hasUI) displaySummary(pi, text);
				return;
			}

			if (sub === "rag") {
				// RAG subcommands (list / probe / audit / sync / init) — thin wrapper,
				// Python stays the single source of parsing and validation; the exit
				// code keeps its 0/1/2 meaning (audit 1 = findings, not failure).
				await runMwRagCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
				return;
			}

			if (sub === "stats") {
				// Usage monitor (mw-usage-monitor AC-006): token + wall-clock
				// attribution over a time window — thin wrapper, Python owns the
				// ledger scan, the filters and the text report.
				await runMwStatsCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
				return;
			}

			if (sub === "run-detached") {
				// Background command dispatch (D-005/AC-008) — thin wrapper over
				// shared/run-detached.ts; parsing stays here (usage-first), the
				// handoff contract and spawn stay in the shared single source.
				await runMwRunDetachedCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
				return;
			}

			if (sub === "ack") {
				// Ack terminal worker results (AC-004): <task-key> acks one row,
				// all acks every unacked terminal row THIS WINDOW owns
				// (mw-task-scope-isolation — the sidecar is project-level, so an
				// unscoped "all" would clear another window's unhandled rows).
				// Running/pending rows are rejected with the reason — nothing is
				// written for them; foreign rows are rejected with the owning key.
				const target = _args.trim().split(/\s+/)[1] ?? "";
				if (!target) {
					ctx.ui.notify("Usage: /mw ack <task-key> | all", "warning");
					return;
				}
				const result = await ackTasks(workerStore, ackStore, target === "all" ? "all" : [target], {
					watch,
					agenticdocRoot,
				});
				if (result.acked.length > 0) {
					ctx.ui.notify(`Acked ${result.acked.length} task(s): ${result.acked.join(", ")}`, "info");
				}
				for (const r of result.rejected) ctx.ui.notify(`Not acked: ${r.key} — ${r.reason}`, "warning");
				if (result.acked.length === 0 && result.rejected.length === 0) {
					ctx.ui.notify("No unacked terminal tasks.", "info");
				}
				return;
			}

			ctx.ui.notify(
				"Usage: /mw build|init|start|stop|status|doctor [fix] | update [--apply] | target show|set|clear|on|off | partition show|set|clear|on|off | model show|set|clear|set-fallback|clear-fallback | decide show|sign [--allow-empty] [--key <k>] | decide dp list|show <id>|export | decide monitor | rag <sub> | stats [--since <window>] [--key <k>] [--type <t>] [--model <m>] [--source worker|pm] [--json] | run-detached [--cwd <dir>] [--run-dir <dir>] [--timeout-min <n>] [--heartbeat-s <n>] -- <cmd...> | ack <task-key>|all",
				"warning",
			);
		},
	});
}
