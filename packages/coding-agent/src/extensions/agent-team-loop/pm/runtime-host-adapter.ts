/**
 * T06 — the PRODUCTION trusted-host adapter for the frozen local store.
 *
 * BOUNDARY — read this before changing anything here:
 *  - This module is the only implementation of `readTrustedContext` /
 *    `verifyExecution` for a real runtime. It reads REAL files only: the
 *    authoritative `_index.parallel` row (via `IndexStore`), the worker
 *    `run.json`, the dispatched `task.md` head and the pinned dispatch card
 *    (byte-verified with the recorded `card_sha256`).
 *  - It NEVER invents facts. A model self-report, `source: "pm"`, a PID, an
 *    `output.md`, a DP receipt, a selection or "the file exists" is NOT
 *    provenance. Every unreadable / ambiguous / missing fact is a concrete gap
 *    and the call yields `undefined` ⇒ the store fails closed
 *    (`trusted-context-refused`), never a default grant.
 *  - It does NOT fork the frozen schema: the card ceiling and host accounting
 *    snapshot are validated as `MatterBudgetV1`; missing host policy/accounting
 *    sources refuse. The stop kinds/scopes and proof use frozen contracts.
 *  - It does not write anything except through the store's single writer, does
 *    not dispatch, does not sign, does not decide, and never claims a business
 *    L2/VC pass. The target verifier proves TARGET BYTES ONLY.
 */

import { spawnSync } from "node:child_process";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import {
	type ExtensionAPI,
	type ExtensionContext,
	isToolCallEventType,
	type ToolCallEvent,
	type ToolCallEventResult,
	type ToolResultEvent,
} from "../../../core/extensions/types.ts";
import { sha256EolNormalizedBytes } from "../shared/card-digest.ts";
import type {
	HostBinding,
	HostRole,
	LocalSource,
	MatterBudgetV1,
	PmDisposition,
	StopSignal,
	ToolName,
} from "../shared/decision-handoff.ts";
import {
	DECISION_HANDOFF_SCHEMA_ID,
	DECISION_HANDOFF_SCHEMA_VERSION,
	parseBudgetReservationResult,
	validateMatterBudget,
} from "../shared/decision-handoff.ts";
import type { IndexEntry } from "../shared/index-store.ts";
import { IndexStore, keyNameRefusal, normalizeKey } from "../shared/index-store.ts";
import type {
	CommitSelectionRequest,
	ExecutedActionTerminalProof,
	ExecutionProof,
	ExecutionVerificationRequest,
	ExpectedHostFacts,
	LocalSelectionHostAdapter,
	TrustedContextRequest,
	TrustedHostContext,
} from "../shared/local-selection-store.ts";
import { LocalSelectionStore } from "../shared/local-selection-store.ts";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.ts";
import { agenticdocRoot as controlRoot } from "../shared/paths.ts";
import type { RunState } from "../shared/run-store.ts";
import { isTerminalRunStatus, readRunState } from "../shared/run-store.ts";
import { readWorkerDeadline } from "../shared/worker-deadline.ts";
import { PmChannel } from "./codex-channel.ts";
import {
	evaluateLocalQg,
	LOCAL_QG_VERIFIER,
	type LocalQgDisposition,
	type LocalQgExecutionObservation,
	type LocalQgInput,
	type LocalQgReview,
	type LocalQgReviewProvenance,
	type LocalQgStageSource,
	localQgReviewDigest,
} from "./local-qg-consumer.ts";
import {
	findPmStageDirection,
	PM_STAGE_ENTRY_TYPE,
	PM_STAGE_MAX_COST,
	PM_STAGE_MAX_NO_PROGRESS,
	PM_STAGE_MAX_STEPS,
	PM_STAGE_MAX_WINDOW_MS,
	PM_STAGE_SOURCE_ENTRY_TYPE,
	type PmStageDirection,
	PmStageLedger,
	type PmStageSession,
	stageSourceDigest,
} from "./pm-stage-source.ts";
import {
	createRuntimeBudgetController,
	type RuntimeBudgetAuthorization,
	type RuntimeBudgetBinding,
	type RuntimeBudgetController,
	type RuntimeBudgetSnapshot as RuntimeBudgetControllerSnapshot,
	type RuntimeBudgetEvidence,
	type RuntimeBudgetEvidenceDigest,
	type RuntimeBudgetHistory,
	type RuntimeBudgetReplayEvent,
} from "./runtime-budget.ts";
import {
	RuntimeExecutionController,
	type RuntimeExecutionResult,
	type RuntimeTargetAuthorization,
	type RuntimeToolCall,
	type RuntimeToolResult,
	runtimeExecutionExecutor,
} from "./runtime-execution.ts";

export const RUNTIME_ADAPTER_VERSION = "t06-r1";

/** The r2 identity of the FIRST supported target verifier. */
export const TARGET_DIGEST_VERIFIER_ID = `target-digest-v1@${RUNTIME_ADAPTER_VERSION}`;

/** `task.md` records the card bytes it was generated from; the adapter re-reads
 *  the card and refuses on any byte drift. A bound, never an unlimited read. */
const MAX_CARD_BYTES = 1024 * 1024;

/** The card/run fact that makes a worker run unbindable. These are the ONLY
 *  statuses treated as a real `parent-cancel` stop; any other non-`running`
 *  status is "no trusted running run" (a gap), never an invented stop kind. */
const STOP_RUN_STATUSES: readonly string[] = ["canceled", "stopped", "failed-by-stop"];

function workerRunCancelled(run: RunState): boolean {
	return STOP_RUN_STATUSES.includes(run.status) || (run.status === "failed" && run.aborted === true);
}

/** Worker host roles, derived from the run kind (never from model text). */
const WORKER_ROLES: readonly HostRole[] = ["coding", "research", "review"];

/** The matter version of a local selection matter (same as the submit tool). */
export const MATTER_VERSION = `${DECISION_HANDOFF_SCHEMA_ID}:local-selection-v1`;

/** The heading a dispatch card uses to carry its machine-readable budget facts. */
const BUDGET_HEADING = /^##\s*事项预算事实\s*$/;

export type RuntimeFactRead<T> = { ok: true; value: T } | { ok: false; gaps: string[]; reason: string };

function fail<T>(reason: string, gaps: string[]): RuntimeFactRead<T> {
	return { ok: false, gaps: gaps.length ? gaps : ["fact"], reason };
}

/** Reads reject redirected components before AND after reading the original bytes. */
function safeFile(root: string, file: string): boolean {
	const relative = path.relative(path.resolve(root), path.resolve(file));
	if (!relative || relative.split(path.sep).includes("..") || path.isAbsolute(relative)) return false;
	try {
		let cursor = path.resolve(root);
		if (fs.lstatSync(cursor).isSymbolicLink()) return false;
		for (const segment of relative.split(path.sep)) {
			cursor = path.join(cursor, segment);
			if (fs.lstatSync(cursor).isSymbolicLink()) return false;
		}
		const real = fs.realpathSync(file);
		const lexical = path.resolve(file);
		return process.platform === "win32" ? real.toLowerCase() === lexical.toLowerCase() : real === lexical;
	} catch {
		return false;
	}
}

function readBytes(root: string, file: string): RuntimeFactRead<Buffer> {
	if (!safeFile(root, file)) return fail("file path is missing or redirected", ["file"]);
	try {
		const before = fs.lstatSync(file);
		if (!before.isFile() || before.size > MAX_CARD_BYTES) return fail("file is not bounded regular bytes", ["file"]);
		const bytes = fs.readFileSync(file);
		const after = fs.lstatSync(file);
		if (
			!safeFile(root, file) ||
			before.ino !== after.ino ||
			before.mtimeMs !== after.mtimeMs ||
			bytes.length !== before.size
		)
			return fail("file changed during read", ["file"]);
		return { ok: true, value: bytes };
	} catch {
		return fail("file could not be read", ["file"]);
	}
}

/** Titles and blank lines are legal; the first section heading ends metadata.
 * Duplicate fields, even equal duplicates, are ambiguous, never last-wins. */
export function parseHead(text: string): RuntimeFactRead<Record<string, string>> {
	const fields: Record<string, string> = {};
	for (const line of text.split(/\r?\n/)) {
		if (/^##\s/.test(line)) break;
		const match = /^([a-z_][a-z0-9_-]*):\s*(.*)$/.exec(line);
		if (match === null) continue;
		const key = match[1];
		if (key === undefined) continue;
		if (Object.hasOwn(fields, key)) return fail("duplicate card/envelope header", [key]);
		fields[key] = (match[2] ?? "").trim();
	}
	return { ok: true, value: fields };
}

export interface RuntimeBudgetDeclaration {
	budget_ref: string;
	matter_ref: string;
	parent_matter_ref?: string;
	/** `deadline` expressed as `<run start> + N minutes` in the card. */
	wall_minutes?: number;
	/** `deadline` expressed as an absolute ISO instant in the card. */
	deadline_iso?: string;
	max_steps: number;
	no_progress_limit: number;
	remaining_cost: number;
	steps_consumed: number;
	cost_consumed: number;
	no_progress_count: number;
	source_refs: string[];
}

/** Parse field-local declarations. Only colon-delimited keys begin fields;
 * mentions of `cost_consumed` in a unit contract are not numeric declarations. */
function budgetBlockOf(cardText: string): RuntimeFactRead<Map<string, string>> {
	const sections = cardText.split(/\r?\n/);
	const starts = sections.flatMap((line, index) => (BUDGET_HEADING.test(line) ? [index] : []));
	if (starts.length !== 1) return fail("missing or duplicate budget section", ["budget"]);
	const fields = new Map<string, string>();
	for (const line of sections.slice((starts[0] ?? 0) + 1)) {
		if (/^##\s/.test(line)) break;
		if (!line.trim()) continue;
		const shared =
			/^-\s*`steps_consumed`\s*\/\s*`no_progress_count`\s*[:：]\s*(?:本运行|实施时从 run\/trace 真实调用与写入记录得出，)初始 (0)\s*$/.exec(
				line,
			);
		if (shared !== null) {
			for (const key of ["steps_consumed", "no_progress_count"]) {
				if (fields.has(key)) return fail("duplicate budget field", [key]);
				fields.set(key, shared[1] ?? "");
			}
			continue;
		}
		const matches = [...line.matchAll(/`([a-z_]+)`\s*[:：]\s*/g)];
		if (!/^-\s*`/.test(line) || matches.length === 0) return fail("unrecognized budget declaration", ["budget"]);
		for (let index = 0; index < matches.length; index += 1) {
			const match = matches[index];
			if (match === undefined) continue;
			const key = match[1] ?? "";
			if (fields.has(key)) return fail("duplicate budget field", [key]);
			const end = matches[index + 1]?.index ?? line.length;
			fields.set(
				key,
				line
					.slice((match.index ?? 0) + match[0].length, end)
					.replace(/[；;]\s*$/, "")
					.trim(),
			);
		}
	}
	return { ok: true, value: fields };
}

function refValue(text: string | undefined): string | undefined {
	if (text === undefined) return undefined;
	const match = /^`([^`\s]+)`(?:\s*\+\s*(?:其 |卡 )?SHA)?$/.exec(text);
	return match?.[1];
}

/** Whole numeric token plus an optional Chinese explanatory suffix. Fractions,
 * signs, exponent notation, unsafe values and other tokens cannot be truncated. */
function numericValue(text: string | undefined, integer: boolean): number | undefined {
	if (text === undefined) return undefined;
	const match = /^(\d+(?:\.\d+)?)(?:[（，].*)?$/.exec(text);
	if (match === null) return undefined;
	const value = Number(match[1]);
	if (!Number.isFinite(value) || value > Number.MAX_SAFE_INTEGER || (integer && !Number.isSafeInteger(value)))
		return undefined;
	return value;
}

function isoMillis(value: string): number | undefined {
	if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)) return undefined;
	const ms = Date.parse(value);
	if (!Number.isSafeInteger(ms)) return undefined;
	const canonical = new Date(ms).toISOString();
	return canonical === value || canonical.replace(".000Z", "Z") === value ? ms : undefined;
}

/** Card declaration is an initial ceiling, NOT a live accounting source. */
export function buildMatterBudgetFromCard(
	cardText: string,
	input: { cardRef: string; cardSha256: string; runStartedAt?: string; runRef: string; indexRef: string },
): RuntimeFactRead<{ budget: MatterBudgetV1; declaration: RuntimeBudgetDeclaration }> {
	const block = budgetBlockOf(cardText);
	if (!block.ok) return block;
	const fields = block.value;
	const gaps: string[] = [];
	const budgetRef = refValue(fields.get("budget_ref"));
	const matterRef = refValue(fields.get("matter_ref"));
	const parentMatterRef = refValue(fields.get("parent_matter_ref"));
	if (budgetRef === undefined || budgetRef !== `${input.cardRef}#事项预算事实`) gaps.push("budget_ref");
	if (matterRef === undefined) gaps.push("matter_ref");
	if (fields.has("parent_matter_ref") && parentMatterRef === undefined) gaps.push("parent_matter_ref");
	const maxSteps = numericValue(fields.get("max_steps"), true);
	const noProgressLimit = numericValue(fields.get("no_progress_limit"), true);
	const remainingCost = numericValue(fields.get("remaining_cost"), false);
	const stepsConsumed = numericValue(fields.get("steps_consumed"), true);
	const noProgressCount = numericValue(fields.get("no_progress_count"), true);
	const unitText = `${fields.get("remaining_cost") ?? ""} ${fields.get("cost_unit") ?? ""}`;
	const stepCostUnit = /(?:^|[（；;\s])1 cost unit\s*[≡=]\s*1 tool call(?:[；;）\s]|$)/.test(unitText);
	if (!stepCostUnit) gaps.push("cost_unit");
	const costConsumed = fields.has("cost_consumed")
		? numericValue(fields.get("cost_consumed"), false)
		: /`cost_consumed` 与 `steps_consumed` 同单位/.test(unitText) && stepCostUnit
			? stepsConsumed
			: undefined;
	if (costConsumed !== undefined && stepsConsumed !== undefined && costConsumed !== stepsConsumed)
		gaps.push("cost_consumed");
	for (const [key, value] of Object.entries({
		max_steps: maxSteps,
		no_progress_limit: noProgressLimit,
		remaining_cost: remainingCost,
		steps_consumed: stepsConsumed,
		cost_consumed: costConsumed,
		no_progress_count: noProgressCount,
	})) {
		if (value === undefined) gaps.push(key);
	}
	const sources = fields.get("source_refs");
	if (sources === undefined || !sources.trim() || !/SHA/.test(sources) || !/`[^`]+`/.test(sources))
		gaps.push("source_refs");
	const deadlineText = fields.get("deadline") ?? "";
	const relative = /^`run\.json\.started_at \+ (\d+(?:\.\d+)?)m`(?:（[^\r\n]*）)?$/.exec(deadlineText);
	const absolute = /^`([^`]+)`(?:（[^\r\n]*）)?$/.exec(deadlineText);
	let deadline: string | undefined;
	let wallMinutes: number | undefined;
	let deadlineIso: string | undefined;
	if (relative !== null) {
		wallMinutes = numericValue(relative[1], false);
		const startedMs = input.runStartedAt === undefined ? undefined : isoMillis(input.runStartedAt);
		const ms = startedMs === undefined || wallMinutes === undefined ? NaN : startedMs + wallMinutes * 60_000;
		if (
			wallMinutes !== undefined &&
			wallMinutes > 0 &&
			Number.isSafeInteger(ms) &&
			Math.abs(ms) <= 8_640_000_000_000_000
		)
			deadline = new Date(ms).toISOString();
	} else if (absolute?.[1] !== undefined && isoMillis(absolute[1]) !== undefined) {
		deadline = absolute[1];
		deadlineIso = deadline;
	}
	if (deadline === undefined) gaps.push("deadline");
	if (gaps.length) return fail("card budget facts incomplete or invalid", gaps);
	const budget: MatterBudgetV1 = {
		schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
		budget_ref: budgetRef as string,
		matter_ref: matterRef as string,
		...(parentMatterRef === undefined ? {} : { parent_matter_ref: parentMatterRef }),
		deadline: deadline as string,
		max_steps: maxSteps as number,
		no_progress_limit: noProgressLimit as number,
		remaining_cost: remainingCost as number,
		steps_consumed: stepsConsumed as number,
		cost_consumed: costConsumed as number,
		no_progress_count: noProgressCount as number,
		source_refs: [`${input.cardRef}#sha256:${input.cardSha256}`, input.runRef, input.indexRef, sources as string],
	};
	const checked = validateMatterBudget(budget);
	if (!checked.ok)
		return fail(
			"card budget validation failed",
			checked.gaps.length ? checked.gaps : checked.issues.map((issue) => issue.field),
		);
	const declaration: RuntimeBudgetDeclaration = {
		...budget,
		...(wallMinutes === undefined ? {} : { wall_minutes: wallMinutes }),
		...(deadlineIso === undefined ? {} : { deadline_iso: deadlineIso }),
	};
	return { ok: true, value: { budget: checked.value, declaration } };
}

/** Same-snapshot reservation preflight. IMPORTANT: the store already holds the
 *  shared intent lock while this runs, so this must not take it again (that
 *  would self-refuse `lock-busy`). It reserves ONE step / ONE cost unit against
 *  the FINITE remaining budget; `reserved_*` is a reservation, NEVER
 *  `cost_consumed`, and nothing is persisted. Absent budget ⇒ no grant. */
export function preflightReservation(
	budget: MatterBudgetV1,
	nowMs = Date.now(),
): RuntimeFactRead<Record<string, unknown>> {
	const checked = validateMatterBudget(budget);
	if (!checked.ok || !Number.isSafeInteger(nowMs) || isoMillis(budget.deadline) === undefined)
		return fail("invalid budget or current clock", ["budget"]);
	const steps = 1;
	const cost = 1;
	const stepsLeft = budget.max_steps - budget.steps_consumed;
	const exhausted =
		budget.remaining_cost < cost ||
		stepsLeft < steps ||
		budget.no_progress_count >= budget.no_progress_limit ||
		Date.parse(budget.deadline) <= nowMs;
	const granted = !exhausted;
	return {
		ok: true,
		value: {
			granted,
			reserved_steps: granted ? steps : 0,
			reserved_cost: granted ? cost : 0,
			remaining_after_steps: granted ? stepsLeft - steps : stepsLeft,
			remaining_after_cost: granted ? budget.remaining_cost - cost : budget.remaining_cost,
			reason: granted ? "granted" : "budget-exhausted",
		},
	};
}

interface RuntimeAuthority {
	claimId: string;
	bindingVersion: string;
	role: HostRole;
	taskKey?: string;
	runId?: string;
	cardPath: string;
	cardSha256: string;
	budget: MatterBudgetV1;
	stopSignals: StopSignal[];
}

/** Why the authority read produced no facts: every entry is a concrete gap. */
export type RuntimeAuthorityRead = RuntimeFactRead<RuntimeAuthority>;

function workerRoleFor(kind: string | undefined): HostRole | undefined {
	const role = WORKER_ROLES.find((candidate) => candidate === kind);
	return role;
}

function readKeyRows(root: string, key: string): RuntimeFactRead<{ claimId: string; updated: string; phase: string }> {
	let rows: IndexEntry[];
	try {
		const indexFile = path.join(root, "_index.parallel");
		const before = readBytes(root, indexFile);
		if (!before.ok) return fail("authoritative index path is unavailable or redirected", ["index"]);
		rows = new IndexStore(root).readAuthorityRows();
		const after = readBytes(root, indexFile);
		if (!after.ok || !before.value.equals(after.value)) return fail("authority changed during index read", ["index"]);
	} catch {
		return fail("authoritative index is unreadable", ["index"]);
	}
	const matches = rows.filter((row) => normalizeKey(row.key) === normalizeKey(key));
	if (matches.length !== 1) return fail("missing or duplicate target authority row", ["index.claim"]);
	const active = matches.filter((row) => row.status === "active");
	if (active.length === 0) return fail("no active exact-self row for this key", ["index.claim"]);
	if (active.length > 1) return fail("multiple active rows for this key; authority is ambiguous", ["index.claim"]);
	const row = active[0];
	if (row === undefined) return fail("no active exact-self row for this key", ["index.claim"]);
	if (row.claimId.trim() === "" || row.claimId === "—" || row.claimId === "-")
		return fail("the active row carries no claim id", ["index.claim"]);
	return { ok: true, value: { claimId: row.claimId, updated: row.updated, phase: row.phase } };
}

/** Explicit host-only identity/pin. The PM never scans tasks to guess one.
 * localRef binds this authorization to the FULL frozen offer identity (including
 * material/basis/parent), while authorizationUnit remains the stable card unit. */
export interface RuntimeHostAuthorization {
	localRef: string;
	key: string;
	source: TrustedContextRequest["source"];
	role: HostRole;
	owningPmClaim: string;
	taskKey?: string;
	runId?: string;
	cardPath: string;
	cardSha256: string;
	budgetStartedAt: string;
	authorizationUnit: string;
	matterRef: string;
	/** Present only for a REAL PM stage admitted from the typed private channel.
	 *  It is never a worker dispatch/run and never a second budget grant. */
	stageRef?: string;
}

/** Read authority, declaration and stops. For worker stop-only reads, the
 * dispatched envelope is the host pin; controlled submissions ALSO require
 * an independently registered RuntimeHostAuthorization. */
export function readRuntimeAuthority(input: {
	agenticdocRoot: string;
	key: string;
	source: TrustedContextRequest["source"];
	taskKey?: string;
	runId?: string;
	clockMs?: number;
	authorization?: RuntimeHostAuthorization;
}): RuntimeAuthorityRead {
	if (keyNameRefusal(input.key) !== null) return fail("invalid key", ["key"]);
	const row = readKeyRows(input.agenticdocRoot, input.key);
	if (!row.ok) return row;
	const keyDir = path.join(input.agenticdocRoot, input.key);
	const authorization = input.authorization;
	if (
		authorization !== undefined &&
		(authorization.key !== input.key ||
			authorization.source !== input.source ||
			authorization.taskKey !== input.taskKey ||
			authorization.runId !== input.runId ||
			authorization.owningPmClaim !== row.value.claimId ||
			!authorization.owningPmClaim.trim() ||
			isoMillis(authorization.budgetStartedAt) === undefined)
	)
		return fail("host identity or budget start drift", ["host.authorization"]);
	let run: RunState | undefined;
	let runRef = `_index.parallel#${input.key}`;
	let cardPath: string | undefined = authorization?.cardPath;
	let pinnedSha: string | undefined = authorization?.cardSha256;
	let startedAt = authorization?.budgetStartedAt;
	if (input.source === "worker-local") {
		if (input.taskKey === undefined || keyNameRefusal(input.taskKey) !== null || !input.runId?.trim())
			return fail("worker-local requires a legal task and run", ["task_key", "run_id"]);
		const taskDir = path.join(keyDir, "workers", input.taskKey);
		if (!safeFile(input.agenticdocRoot, path.join(taskDir, "run.json")))
			return fail("run path unavailable or redirected", ["run"]);
		run = readRunState(taskDir);
		if (run === undefined) return fail("run.json is missing or invalid", ["run"]);
		if (run.task_key !== input.taskKey) return fail("run.json task_key drift", ["run.task_key"]);
		if (run.run_id !== input.runId) return fail("run.json run_id drift", ["run.run_id"]);
		if (typeof run.owner_key !== "string" || normalizeKey(run.owner_key) !== normalizeKey(input.key))
			return fail("run.json owner_key drift", ["run.owner_key"]);
		runRef = `workers/${input.taskKey}/run.json`;
		const envelope = readBytes(input.agenticdocRoot, path.join(taskDir, "task.md"));
		if (!envelope.ok) return fail("task.md unavailable or redirected", ["task.md"]);
		const head = parseHead(envelope.value.toString("utf8"));
		if (!head.ok) return head;
		if (
			authorization !== undefined &&
			(head.value.card_path !== cardPath || head.value.card_sha256 !== pinnedSha || run.started_at !== startedAt)
		)
			return fail("dispatched pin/start does not match host authorization", [
				"card_path",
				"card_sha256",
				"started_at",
			]);
		cardPath = head.value.card_path;
		pinnedSha = head.value.card_sha256;
		startedAt = run.started_at;
	} else if (authorization === undefined) {
		return fail("PM requires explicit host card pin and start", ["host.authorization"]);
	}
	if (
		typeof cardPath !== "string" ||
		!/^tasks\/(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]+\.md$/.test(cardPath) ||
		cardPath.split("/").some((part) => part === "." || part === "..")
	)
		return fail("card must be within this key's tasks range", ["card_path"]);
	if (typeof pinnedSha !== "string" || !/^[a-f0-9]{64}$/.test(pinnedSha))
		return fail("missing or invalid card SHA", ["card_sha256"]);
	if (typeof startedAt !== "string" || isoMillis(startedAt) === undefined)
		return fail("missing or invalid budget start", ["started_at"]);
	const card = readBytes(input.agenticdocRoot, path.join(keyDir, cardPath));
	if (!card.ok) return fail("pinned card unavailable or redirected", ["card"]);
	// The generated `card_sha256` pin is CRLF->LF normalized over RAW bytes
	// (frozen shared/card-digest.ts recipe). Hash those same raw bytes with the
	// frozen recipe; never decode/re-encode UTF-8 (invalidUTF8 bytes are preserved
	// by the latin1 round-trip). A raw-Buffer SHA here would reject every legal
	// CRLF dispatch card. A raw preservation SHA is a DIFFERENT value and is
	// deliberately NOT mixed with this generated normalized pin.
	const actualSha = sha256EolNormalizedBytes(card.value);
	if (actualSha !== pinnedSha) return fail("card bytes drifted from pin", ["card_sha256"]);
	const cardText = card.value.toString("utf8");
	const head = parseHead(cardText);
	if (!head.ok) return head;
	if (head.value.owning_pm_claim !== row.value.claimId)
		return fail("card PM owner does not match live claim", ["card.owning_pm_claim"]);
	const role = input.source === "pm" ? "pm" : workerRoleFor(run?.kind);
	if (role === undefined || (authorization !== undefined && authorization.role !== role))
		return fail("host/run role drift", ["role"]);
	const stopSignals: StopSignal[] = [];
	const deadlineStop = run?.status === "failed" && run.stop_kind === "worker-deadline";
	if (run !== undefined) {
		if (workerRunCancelled(run))
			stopSignals.push({
				signal_ref: `${runRef}#${run.aborted ? "aborted=true" : `status=${run.status}`}`,
				kind: "parent-cancel",
			});
		else if (deadlineStop)
			stopSignals.push({ signal_ref: `${runRef}#stop_kind=worker-deadline`, kind: "worker-deadline" });
		else if (run.status !== "running") return fail("there is no running run for this task/run", ["run.status"]);
	}
	const budgetRead = buildMatterBudgetFromCard(cardText, {
		cardRef: cardPath,
		cardSha256: actualSha,
		runStartedAt: startedAt,
		runRef,
		indexRef: "_index.parallel",
	});
	if (!budgetRead.ok) return budgetRead;
	const budget = budgetRead.value.budget;
	if (authorization !== undefined && authorization.authorizationUnit !== budget.matter_ref)
		return fail("authorization unit does not match pinned card", ["authorization_unit"]);
	if (!deadlineStop && role !== "pm" && input.clockMs !== undefined && run?.status === "running") {
		const live = readWorkerDeadline(
			input.agenticdocRoot,
			path.join(keyDir, "workers", run.task_key),
			run,
			input.clockMs,
		);
		if (live?.stop === "authority-revoked")
			return fail("live worker authorization revoked", ["host.worker-deadline"]);
		const kind = live?.stop === "budget-exhausted" ? "key-budget" : live?.stop;
		if (kind) stopSignals.push({ signal_ref: `${runRef}#live-deadline`, kind });
		else if (input.clockMs >= Math.min(Date.parse(budget.deadline), live?.deadline ?? Infinity))
			stopSignals.push({ signal_ref: `${budget.budget_ref}#deadline`, kind: "worker-deadline" });
	}
	if (
		role === "pm" &&
		authorization?.stageRef !== undefined &&
		input.clockMs !== undefined &&
		input.clockMs >= Date.parse(budget.deadline)
	)
		stopSignals.push({ signal_ref: `${budget.budget_ref}#stage-deadline`, kind: "key-budget" });
	return {
		ok: true,
		value: {
			claimId: row.value.claimId,
			bindingVersion: `runtime-${RUNTIME_ADAPTER_VERSION}:${row.value.claimId}:${actualSha}`,
			role,
			...(input.taskKey === undefined ? {} : { taskKey: input.taskKey }),
			...(input.runId === undefined ? {} : { runId: input.runId }),
			cardPath,
			cardSha256: actualSha,
			budget,
			stopSignals,
		},
	};
}

/** What the host expects a reviewer's terminal verdict to bind. Every value is
 *  a CURRENT fact of the implementer's own verified action; a reviewer cannot
 *  attest a different action and a PM cannot attest its own work. */
export interface CurrentReviewExpected {
	ownerKey: string;
	localRef: string;
	executionRef: string;
	toolCallRef: string;
	materialDigest: string;
	basisDigest: string;
	implementerTaskKey: string;
	implementerRunId: string;
}

export interface CurrentReviewRequest {
	agenticdocRoot: string;
	/** The key that owns BOTH runs (same key, distinct tasks/runs). */
	key: string;
	reviewerTaskKey: string;
	reviewerRunId: string;
	expected: CurrentReviewExpected;
	clockMs?: number;
}

const REVIEW_ARTIFACT = "review-verdict.json";

function stringList(value: unknown): string[] | undefined {
	if (!Array.isArray(value)) return undefined;
	return value.every((item): item is string => typeof item === "string" && item.trim() !== "")
		? [...value]
		: undefined;
}

interface TerminalReviewDispatch {
	claimId: string;
	cardPath: string;
	cardSha256: string;
}

/** The REVIEWER side of the same verifier primitives, for a TERMINAL run. A
 *  finished review run is legitimate evidence; a live/unknown/cancelled run is
 *  not. Nothing here relaxes the reviewer card pin or the live PM claim. */
function readTerminalReviewDispatch(
	root: string,
	key: string,
	reviewerTaskKey: string,
	reviewerRunId: string,
): RuntimeFactRead<TerminalReviewDispatch> {
	if (keyNameRefusal(key) !== null) return fail("invalid key", ["key"]);
	if (keyNameRefusal(reviewerTaskKey) !== null) return fail("invalid reviewer task", ["reviewer_task_key"]);
	const row = readKeyRows(root, key);
	if (!row.ok) return row;
	const taskDir = path.join(root, key, "workers", reviewerTaskKey);
	if (!safeFile(root, path.join(taskDir, "run.json")))
		return fail("reviewer run path unavailable or redirected", ["review.run"]);
	const run = readRunState(taskDir);
	if (run === undefined) return fail("reviewer run.json is missing or invalid", ["review.run"]);
	if (run.task_key !== reviewerTaskKey) return fail("reviewer run.json task_key drift", ["review.run.task_key"]);
	if (run.run_id !== reviewerRunId) return fail("reviewer run.json run_id drift", ["review.run.run_id"]);
	if (typeof run.owner_key !== "string" || normalizeKey(run.owner_key) !== normalizeKey(key))
		return fail("reviewer run.json owner_key drift", ["review.run.owner_key"]);
	if (run.status !== "done" || run.exit !== 0)
		return fail("the review run did not terminate successfully; an unfinished review is no verdict", [
			"review.terminal",
		]);
	if (workerRoleFor(run.kind) !== "review") return fail("the referencing run is not a review run", ["review.role"]);
	const envelope = readBytes(root, path.join(taskDir, "task.md"));
	if (!envelope.ok) return fail("reviewer task.md unavailable or redirected", ["task.md"]);
	const head = parseHead(envelope.value.toString("utf8"));
	if (!head.ok) return head;
	const cardPath = head.value.card_path;
	const pinnedSha = head.value.card_sha256;
	if (
		typeof cardPath !== "string" ||
		!/^tasks\/(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]+\.md$/.test(cardPath) ||
		cardPath.split("/").some((part) => part === "." || part === "..")
	)
		return fail("reviewer card must be within this key's tasks range", ["card_path"]);
	if (typeof pinnedSha !== "string" || !/^[a-f0-9]{64}$/.test(pinnedSha))
		return fail("missing or invalid reviewer card SHA", ["card_sha256"]);
	const card = readBytes(root, path.join(root, key, cardPath));
	if (!card.ok) return fail("reviewer pinned card unavailable or redirected", ["card"]);
	const actualSha = sha256EolNormalizedBytes(card.value);
	if (actualSha !== pinnedSha) return fail("reviewer card bytes drifted from pin", ["card_sha256"]);
	const cardHead = parseHead(card.value.toString("utf8"));
	if (!cardHead.ok) return cardHead;
	if (cardHead.value.owning_pm_claim !== row.value.claimId)
		return fail("reviewer card PM owner does not match the live claim", ["owning_pm_claim"]);
	return { ok: true, value: { claimId: row.value.claimId, cardPath, cardSha256: actualSha } };
}

/**
 * Reads the REAL terminal artifact of a separately dispatched REVIEW run and
 * refuses unless the reviewer's own dispatch pin, run record, card pin and
 * artifact bytes are all current and bound to this exact implementer action.
 *
 * Trust comes only from these production facts. The verdict file alone is an
 * editable JSON blob: it is accepted solely after the separate review card/run
 * exist, the reviewer role is `review`, the reviewer's run/card/artifact hashes
 * verify, the reviewer is NOT the implementer run, and every bound field equals
 * the expected current facts. A missing/self/forged/stale/partial review yields
 * a concrete gap, never a PASS.
 */
export function readCurrentIndependentReview(input: CurrentReviewRequest): RuntimeFactRead<LocalQgReview> {
	const expected = input.expected;
	if (input.reviewerTaskKey === expected.implementerTaskKey || input.reviewerRunId === expected.implementerRunId)
		return fail("a reviewer must be a distinct task and run from the implementer", ["review.identity"]);
	// The reviewer's own dispatch facts are verified from real bytes: live claim,
	// terminal review run, card pin and card owner. A running/unknown run is not a
	// verdict, and the reviewer must be a distinct task/run from the implementer.
	const dispatch = readTerminalReviewDispatch(
		input.agenticdocRoot,
		input.key,
		input.reviewerTaskKey,
		input.reviewerRunId,
	);
	if (!dispatch.ok) return dispatch;
	const reviewerFacts = dispatch.value;
	const keyDir = path.join(input.agenticdocRoot, input.key);
	const taskDir = path.join(keyDir, "workers", input.reviewerTaskKey);
	const run = readRunState(taskDir);
	if (run === undefined) return fail("reviewer run.json is missing or invalid", ["review.run"]);
	if (run.status !== "done" || run.exit !== 0)
		return fail("the review run did not terminate successfully; an unfinished review is no verdict", [
			"review.terminal",
		]);
	if (!run.artifacts.includes(REVIEW_ARTIFACT))
		return fail("the review run's terminal record does not list a verdict artifact", ["review.artifact"]);
	const bytes = readBytes(input.agenticdocRoot, path.join(taskDir, REVIEW_ARTIFACT));
	if (!bytes.ok) return fail(`review verdict artifact is not readable: ${bytes.reason}`, ["review.artifact"]);
	const artifactSha = crypto.createHash("sha256").update(bytes.value).digest("hex");
	let parsed: unknown;
	try {
		parsed = JSON.parse(bytes.value.toString("utf8"));
	} catch {
		return fail("review verdict artifact is not valid JSON", ["review.artifact"]);
	}
	if (!isRecord(parsed)) return fail("review verdict artifact is not an object", ["review.artifact"]);
	const reviewer = isRecord(parsed.reviewer) ? parsed.reviewer : undefined;
	const bound = isRecord(parsed.bound) ? parsed.bound : undefined;
	if (reviewer === undefined || bound === undefined)
		return fail("review verdict does not carry reviewer/bound provenance", ["review.provenance"]);
	if (
		parsed.schema_version !== 1 ||
		parsed.kind !== "independent-review-verdict" ||
		reviewer.role !== "review" ||
		reviewer.task_key !== input.reviewerTaskKey ||
		reviewer.run_id !== input.reviewerRunId ||
		reviewer.card_path !== reviewerFacts.cardPath ||
		reviewer.card_sha256 !== reviewerFacts.cardSha256 ||
		reviewer.reviewer_claim_id !== reviewerFacts.claimId
	)
		return fail("review verdict provenance does not match the verified review dispatch", ["review.provenance"]);
	if (
		bound.owner_key !== expected.ownerKey ||
		bound.local_ref !== expected.localRef ||
		bound.execution_ref !== expected.executionRef ||
		bound.tool_call_ref !== expected.toolCallRef ||
		bound.material_digest !== expected.materialDigest ||
		bound.basis_digest !== expected.basisDigest ||
		bound.implementer_task_key !== expected.implementerTaskKey ||
		bound.implementer_run_id !== expected.implementerRunId
	)
		return fail("review verdict is not bound to the current implementer action", ["review.bound"]);
	const verdict = parsed.verdict;
	if (verdict !== "fix" && verdict !== "partial" && verdict !== "pass" && verdict !== "empty")
		return fail("review verdict value is not a supported business verdict", ["review.verdict"]);
	const typedVerdict: LocalQgReview["verdict"] = verdict;
	const findings = stringList(parsed.findings);
	const unresolved = stringList(parsed.unresolved_findings);
	const refs = stringList(parsed.refs);
	if (findings === undefined || unresolved === undefined || refs === undefined)
		return fail("review findings/refs are not typed string lists", ["review.findings"]);
	if (typeof parsed.reviewed_at !== "string" || isoMillis(parsed.reviewed_at) === undefined)
		return fail("review reviewed_at is not a current ISO instant", ["review.reviewed_at"]);
	// The reviewer's own instant must be bounded by the host clock that requested
	// this read; a verdict dated in the future is not an observation.
	if (input.clockMs !== undefined) {
		if (!Number.isFinite(input.clockMs)) return fail("review read has no valid host clock", ["review.clock"]);
		if ((isoMillis(parsed.reviewed_at) ?? Number.POSITIVE_INFINITY) > input.clockMs)
			return fail("review reviewed_at is later than the host clock", ["review.future"]);
	}
	if (parsed.verifier_ref !== LOCAL_QG_VERIFIER)
		return fail("review verifier is not the current-ref business verifier", ["review.verifier"]);
	const provenance: LocalQgReviewProvenance = {
		kind: "production-review-run",
		owner_key: expected.ownerKey,
		review_kind: "review",
		reviewer_task_key: input.reviewerTaskKey,
		reviewer_run_id: input.reviewerRunId,
		reviewer_card_path: reviewerFacts.cardPath,
		reviewer_card_sha256: reviewerFacts.cardSha256,
		artifact_ref: `workers/${input.reviewerTaskKey}/${REVIEW_ARTIFACT}`,
		artifact_sha256: artifactSha,
		implementer_task_key: expected.implementerTaskKey,
		implementer_run_id: expected.implementerRunId,
		bound_local_ref: expected.localRef,
		bound_execution_ref: expected.executionRef,
		bound_tool_call_ref: expected.toolCallRef,
		bound_material_digest: expected.materialDigest,
		bound_basis_digest: expected.basisDigest,
	};
	const body = {
		origin: "independent-review" as const,
		verdict: typedVerdict,
		selection_ref: expected.localRef,
		execution_ref: expected.executionRef,
		tool_call_ref: expected.toolCallRef,
		verifier_ref: LOCAL_QG_VERIFIER,
		reviewed_at: parsed.reviewed_at,
		findings,
		unresolved_findings: unresolved,
		refs,
		provenance,
	};
	return { ok: true, value: { ...body, source_digest: localQgReviewDigest(body) } };
}

interface NativeReviewRequest extends CurrentReviewRequest {
	parentRunId: string;
	executionCreatedAt: string;
	budgetDeadline: string;
}

/** A disk artifact is only a locator. Read the live launcher's witnessed
 * review and match it to the PM's independently verified execution. */
export function readLauncherIndependentReview(input: NativeReviewRequest): RuntimeFactRead<LocalQgReview> {
	const { agenticdocRoot, key, reviewerTaskKey, reviewerRunId, expected } = input;
	if (
		process.platform !== "win32" ||
		key !== expected.ownerKey ||
		reviewerTaskKey === expected.implementerTaskKey ||
		reviewerRunId === expected.implementerRunId
	)
		return fail("a separate native review is unavailable", ["review.identity"]);
	const dispatch = readTerminalReviewDispatch(agenticdocRoot, key, reviewerTaskKey, reviewerRunId);
	if (!dispatch.ok) return dispatch;
	const now = input.clockMs ?? Date.now();
	const created = isoMillis(input.executionCreatedAt);
	const deadline = isoMillis(input.budgetDeadline);
	if (created === undefined || deadline === undefined || !Number.isFinite(now) || now >= deadline)
		return fail("the owning execution clock or deadline is invalid", ["review.lifecycle"]);
	const workerDir = path.join(agenticdocRoot, key, "workers", reviewerTaskKey);
	const envelope = readBytes(agenticdocRoot, path.join(workerDir, "task.md"));
	const report = readBytes(agenticdocRoot, path.join(workerDir, "report.md"));
	const goal = readBytes(agenticdocRoot, path.join(agenticdocRoot, "goal.md"));
	if (!envelope.ok || !report.ok || !goal.ok)
		return fail("terminal review inputs are unavailable", ["review.artifact"]);
	const mw = findMwPy();
	if (!mw) return fail("the native launcher reader is unavailable", ["review.channel"]);
	const readback = spawnSync(
		PYTHON_EXE,
		["-B", path.join(path.dirname(mw), "review_observation.py"), "read", path.dirname(agenticdocRoot)],
		{
			input: JSON.stringify([key, reviewerTaskKey, reviewerRunId]),
			encoding: "utf8",
			windowsHide: true,
			timeout: 2_500,
			maxBuffer: 1024 * 1024,
		},
	);
	if (readback.error || readback.status !== 0)
		return fail("the native launcher reader did not complete", ["review.channel"]);
	let observed: unknown;
	try {
		observed = JSON.parse(readback.stdout);
	} catch {
		return fail("the launcher did not return a review witness", ["review.channel"]);
	}
	if (!isRecord(observed) || !isRecord(observed.dispatch))
		return fail("no current launcher witness matches the terminal review", ["review.native-witness"]);
	const pin = observed.dispatch;
	const hash = (data: Buffer) => crypto.createHash("sha256").update(data).digest("hex");
	const reportSha = hash(report.value);
	if (
		observed.owner_key !== key ||
		observed.task_key !== reviewerTaskKey ||
		observed.run_id !== reviewerRunId ||
		observed.report_sha256 !== reportSha ||
		pin.claim_id !== dispatch.value.claimId ||
		pin.card_path !== dispatch.value.cardPath ||
		pin.card_sha256 !== dispatch.value.cardSha256 ||
		pin.envelope_sha256 !== hash(envelope.value) ||
		pin.goal_digest !== hash(goal.value) ||
		pin.parent_run_id !== input.parentRunId ||
		pin.execution_created_at !== input.executionCreatedAt ||
		pin.budget_deadline !== input.budgetDeadline ||
		pin.local_ref !== expected.localRef ||
		pin.execution_ref !== expected.executionRef ||
		pin.tool_call_ref !== expected.toolCallRef ||
		pin.material_digest !== expected.materialDigest ||
		pin.basis_digest !== expected.basisDigest ||
		pin.implementer_task_key !== expected.implementerTaskKey ||
		pin.implementer_run_id !== expected.implementerRunId
	)
		return fail("the launcher witness does not match the current execution and dispatch", ["review.bound"]);
	const verdict = observed.verdict;
	const reviewedAt = typeof observed.reviewed_at === "string" ? observed.reviewed_at : "";
	const reviewed = isoMillis(reviewedAt);
	const findings = stringList(observed.findings);
	const unresolved = stringList(observed.unresolved_findings);
	const refs = stringList(observed.refs);
	if (
		(verdict !== "pass" && verdict !== "fix" && verdict !== "partial") ||
		observed.verifier_ref !== LOCAL_QG_VERIFIER ||
		reviewed === undefined ||
		reviewed < created ||
		reviewed >= deadline ||
		reviewed > now ||
		findings === undefined ||
		unresolved === undefined ||
		refs === undefined
	)
		return fail("the launcher witness contains an invalid review conclusion", ["review.verdict"]);
	const provenance: LocalQgReviewProvenance = {
		kind: "production-review-run",
		owner_key: key,
		review_kind: "review",
		reviewer_task_key: reviewerTaskKey,
		reviewer_run_id: reviewerRunId,
		reviewer_card_path: dispatch.value.cardPath,
		reviewer_card_sha256: dispatch.value.cardSha256,
		artifact_ref: `workers/${reviewerTaskKey}/report.md`,
		artifact_sha256: reportSha,
		implementer_task_key: expected.implementerTaskKey,
		implementer_run_id: expected.implementerRunId,
		bound_local_ref: expected.localRef,
		bound_execution_ref: expected.executionRef,
		bound_tool_call_ref: expected.toolCallRef,
		bound_material_digest: expected.materialDigest,
		bound_basis_digest: expected.basisDigest,
	};
	const body: Omit<LocalQgReview, "source_digest"> = {
		origin: "independent-review",
		verdict,
		selection_ref: expected.localRef,
		execution_ref: expected.executionRef,
		tool_call_ref: expected.toolCallRef,
		verifier_ref: LOCAL_QG_VERIFIER,
		reviewed_at: reviewedAt,
		findings,
		unresolved_findings: unresolved,
		refs,
		provenance,
	};
	return { ok: true, value: { ...body, source_digest: localQgReviewDigest(body) } };
}

// ── Target verifier (`target-digest-v1`) ───────────────────────────────────

/** Real, non-redirecting digest of ONE target file. A missing file, a
 *  directory, a symlink or a path outside the project is refused: a digest is
 *  only ever computed over real bytes. */
export function targetFileDigest(projectRoot: string, target: string): RuntimeFactRead<string> {
	if (target.trim() === "") return fail("target path is empty", ["target"]);
	if (path.isAbsolute(target)) return fail("target path must be project-relative", ["target"]);
	const resolved = path.resolve(projectRoot, target);
	if (!safeFile(projectRoot, resolved)) return fail("target path is redirected or unavailable", ["target"]);
	let real: string;
	let realRoot: string;
	try {
		realRoot = fs.realpathSync(projectRoot);
		real = fs.realpathSync(resolved);
	} catch {
		return fail("target file does not exist", ["target"]);
	}
	const rel = path.relative(realRoot, real);
	if (rel === "" || rel.startsWith("..") || path.isAbsolute(rel))
		return fail("target escapes the project root", ["target"]);
	const stat = fs.statSync(real, { throwIfNoEntry: false });
	if (stat === undefined || !stat.isFile()) return fail("target is not a regular file", ["target"]);
	let bytes: Buffer;
	try {
		bytes = fs.readFileSync(real);
	} catch {
		return fail("target bytes could not be read", ["target"]);
	}
	return { ok: true, value: crypto.createHash("sha256").update(bytes).digest("hex") };
}

/** Canonical `target_digest`: sha256 over the sorted `path:sha256` lines. */
export function targetSetDigest(projectRoot: string, targets: readonly string[]): RuntimeFactRead<string> {
	if (targets.length === 0) return fail("no target file was declared", ["target"]);
	const lines: string[] = [];
	for (const target of [...new Set(targets)].sort()) {
		const digest = targetFileDigest(projectRoot, target);
		if (!digest.ok) return digest;
		lines.push(`${target.replace(/\\/g, "/")}:${digest.value}`);
	}
	return { ok: true, value: crypto.createHash("sha256").update(lines.join("\n"), "utf8").digest("hex") };
}

/** A tool-call-id-shaped action ref. The adapter CANNOT prove the id came from
 *  a real observation; it only refuses obviously non-identifier values so a
 *  model-written sentence cannot masquerade as an action identity. The evidence
 *  must carry the real `toolCallId`. */
function actionRefLooksReal(actionRef: string): boolean {
	return /^[A-Za-z0-9_.:@-]{6,}$/.test(actionRef);
}

/** The frozen `effect_state` has only `known`/`unknown`; a drift can therefore
 *  never be reported as a third state. Drift returns NO proof (the store then
 *  refuses with `target-drift` / `verifier-unproven`). */
export function verifyTargetProof(input: {
	projectRoot: string;
	resultRef: string;
	actionRef: string;
	executor: string;
	observedEffect: string;
	expectedTargetDigest?: string;
}): RuntimeFactRead<ExecutionProof> {
	if (!actionRefLooksReal(input.actionRef)) return fail("action_ref is not a real action identity", ["action_ref"]);
	if (input.executor.trim() === "") return fail("executor identity is missing", ["executor"]);
	const digest = targetFileDigest(input.projectRoot, input.resultRef);
	if (!digest.ok) return digest;
	if (input.expectedTargetDigest !== undefined && input.expectedTargetDigest !== digest.value)
		return fail("target bytes drifted from the expected digest", ["target_digest"]);
	const observed = `sha256:${digest.value}`;
	if (input.observedEffect !== observed)
		return fail("observed_effect does not match the target bytes", ["observed_effect"]);
	return {
		ok: true,
		value: {
			action_ref: input.actionRef,
			result_ref: input.resultRef,
			// The correlated record id is filled by `verifyExecution`, which owns it.
			local_ref: input.resultRef,
			verifier_ref: TARGET_DIGEST_VERIFIER_ID,
			target_digest: digest.value,
			observed_effect: observed,
			effect_state: "known",
			executor: input.executor,
		},
	};
}

/** Resolve the project root that a relative target path is anchored at. The
 *  control root is `<project>/.agenticdoc`; any other layout is refused. */
export function projectRootFromControlRoot(agenticdocRoot: string): string | undefined {
	const resolved = path.resolve(agenticdocRoot);
	if (path.basename(resolved) !== ".agenticdoc") return undefined;
	return path.dirname(resolved);
}

// ── The adapter ────────────────────────────────────────────────────────────

/** What the host offer contributes to the trusted expectation. The budget
 *  identity is NOT part of an offer: it is read from the pinned card by this
 *  adapter (`budget.budget_ref`), because the card is the only source of the
 *  authorized budget. Material/basis digests and the parent DP stay
 *  offer-derived. */
export type RuntimeOfferExpected = Omit<ExpectedHostFacts, "budget_ref"> & {
	budget_ref?: string;
	/** Raw business identity from the ask HOST closure, not the model params. */
	matter_identity?: string;
	/** Stable typed PM stage matter, host-derived; a new label cannot evade counters. */
	stage_matter_ref?: string;
	identity?: {
		key: string;
		source: TrustedContextRequest["source"];
		role: HostRole;
		claimId?: string;
		owner?: string;
		taskKey?: string;
		runId?: string;
		stageId?: string;
		scopeRef?: string;
	};
};

export interface RuntimeBudgetSnapshotRequest {
	request: TrustedContextRequest;
	authorization: RuntimeHostAuthorization;
	expected: RuntimeOfferExpected;
	/** Initial card ceiling. Not live consumption. */
	cardBudget: MatterBudgetV1;
	nowMs: number;
}

export interface RuntimeBudgetSnapshot {
	budget: MatterBudgetV1;
	preflight: unknown;
	/** Concrete host observation/history source; absent history must refuse. */
	observationRef: string;
	/** Present only for an exactly proven already-executed terminal action. */
	executed_action?: ExecutedActionTerminalProof;
}

export interface RuntimeHostAdapterConfig {
	agenticdocRoot: string;
	expectedFor?: (localRef: string) => RuntimeOfferExpected | undefined;
	/** Host registration policy must bind a SPECIFIC frozen offer to a pin and
	 * stable authorization unit. This is never exposed as a business tool. */
	authorizationFor?: (localRef: string, expected: RuntimeOfferExpected) => RuntimeHostAuthorization | undefined;
	/** C/I junction: a read-only snapshot of real accounting/reservation facts.
	 * Both store context reads must observe the same semantic snapshot. */
	budgetSnapshotFor?: (input: RuntimeBudgetSnapshotRequest) => RuntimeFactRead<RuntimeBudgetSnapshot>;
	/** D/I junction; absent real action observation yields no execution proof. */
	verifyExecution?: (request: ExecutionVerificationRequest) => Promise<ExecutionProof | undefined>;
	clock?: () => number;
}

/** Build the production adapter. When the runtime facts cannot be established
 *  `readTrustedContext` returns `undefined` ⇒ the store refuses
 *  `trusted-context-refused`; when no adapter is wired at all the store refuses
 *  `trusted-context-missing`. Both are fail-closed. */
export function createRuntimeHostAdapter(config: RuntimeHostAdapterConfig): LocalSelectionHostAdapter {
	const clock = config.clock ?? (() => Date.now());
	return {
		async readTrustedContext(request: TrustedContextRequest): Promise<TrustedHostContext | undefined> {
			const nowMs = clock();
			if (!Number.isSafeInteger(nowMs) || Math.abs(nowMs) > 8_640_000_000_000_000) return undefined;
			const expected = config.expectedFor?.(request.ref);
			if (expected === undefined || !expected.matter_ref.trim() || !expected.matter_identity?.trim())
				return undefined;
			const authorization = config.authorizationFor?.(request.ref, expected);
			const identity = expected.identity;
			// R1 exact-task join. For `pm` the frozen store's buildBinding
			// deliberately records NO task_key/run_id in a selection's
			// host_binding, and the frozen `originalVerdict` (appendExecution)
			// REQUIRES the execution/disposition request to carry task_key/run_id
			// === undefined to match that binding; the FIRST submit carries the
			// real task. The AUTHORIZED task is therefore resolved ONLY from the
			// trusted per-call identity (expected.identity, already cross-checked
			// against the exact registered source by authorizationFor) - never
			// from a missing binding field or a first-matching source. A pm
			// request may omit task/run (execution/disposition join) OR carry the
			// exact trusted values; a foreign task is still refused. Worker-local
			// keeps its strict exact equality (its binding includes task/run).
			const pmTaskJoinOk =
				(request.task_key === undefined || request.task_key === identity?.taskKey) &&
				(request.run_id === undefined || request.run_id === identity?.runId);
			if (
				authorization === undefined ||
				identity === undefined ||
				authorization.localRef !== request.ref ||
				authorization.matterRef !== expected.matter_identity ||
				identity.key !== request.key ||
				identity.source !== request.source ||
				authorization.key !== identity.key ||
				authorization.source !== identity.source ||
				authorization.role !== identity.role ||
				authorization.taskKey !== identity.taskKey ||
				authorization.runId !== identity.runId ||
				(request.source === "pm"
					? !pmTaskJoinOk
					: identity.taskKey !== request.task_key || identity.runId !== request.run_id) ||
				(request.source === "pm" && identity.claimId !== authorization.owningPmClaim) ||
				(request.source === "worker-local" && identity.owner !== request.key)
			)
				return undefined;
			const authority = readRuntimeAuthority({
				agenticdocRoot: config.agenticdocRoot,
				key: request.key,
				source: request.source,
				...(identity?.taskKey === undefined ? {} : { taskKey: identity.taskKey }),
				...(identity?.runId === undefined ? {} : { runId: identity.runId }),
				clockMs: nowMs,
				authorization,
			});
			if (!authority.ok) return undefined;
			const value = authority.value;
			const cardBudget = value.budget;
			if (expected.budget_ref !== undefined && expected.budget_ref !== cardBudget.budget_ref) return undefined;
			// No snapshot source means no live accounting. Never reuse the card's
			// initial zeroes as current counters, even on the first submission.
			let snapshot: RuntimeFactRead<RuntimeBudgetSnapshot> | undefined;
			try {
				snapshot = config.budgetSnapshotFor?.({ request, authorization, expected, cardBudget, nowMs });
			} catch {
				return undefined;
			}
			if (snapshot === undefined || !snapshot.ok) return undefined;
			const checked = validateMatterBudget(snapshot.value.budget);
			const reservation = parseBudgetReservationResult(snapshot.value.preflight);
			if (!checked.ok || !reservation.ok || !snapshot.value.observationRef.trim()) return undefined;
			const budget = checked.value;
			if (
				budget.budget_ref !== cardBudget.budget_ref ||
				budget.matter_ref !== expected.matter_ref ||
				budget.parent_matter_ref !== cardBudget.parent_matter_ref ||
				budget.deadline !== cardBudget.deadline ||
				budget.max_steps > cardBudget.max_steps ||
				budget.no_progress_limit > cardBudget.no_progress_limit ||
				budget.remaining_cost > cardBudget.remaining_cost ||
				budget.steps_consumed < cardBudget.steps_consumed ||
				budget.cost_consumed < cardBudget.cost_consumed ||
				budget.cost_consumed + budget.remaining_cost > cardBudget.cost_consumed + cardBudget.remaining_cost ||
				budget.no_progress_count < cardBudget.no_progress_count ||
				!cardBudget.source_refs.every((source) => budget.source_refs.includes(source)) ||
				!budget.source_refs.includes(snapshot.value.observationRef)
			)
				return undefined;
			const finitePreflight = preflightReservation(budget, nowMs);
			if (!finitePreflight.ok || (reservation.value.granted && finitePreflight.value.granted !== true))
				return undefined;
			if (
				reservation.value.granted &&
				(reservation.value.reserved_steps < 1 ||
					reservation.value.reserved_cost < 1 ||
					reservation.value.remaining_after_steps !==
						budget.max_steps - budget.steps_consumed - reservation.value.reserved_steps ||
					reservation.value.remaining_after_cost !== budget.remaining_cost - reservation.value.reserved_cost)
			)
				return undefined;
			return {
				self_claim_id: value.claimId,
				binding_version: value.bindingVersion,
				role: value.role,
				observed_at: new Date(nowMs).toISOString(),
				// Stable immutable binding identity for this run (the real
				// dispatch start, never a frozen clock). Persisted into
				// host_binding.observed_at by LocalSelectionStore.buildBinding so
				// all three records of one action correlate byte-for-byte. The
				// fresh `observed_at` above still drives every freshness/deadline
				// check and the last-await finalRecheck; this value never does.
				binding_established_at: authorization.budgetStartedAt,
				...(value.taskKey === undefined ? {} : { task_key: value.taskKey }),
				...(value.runId === undefined ? {} : { run_id: value.runId }),
				expected: { ...expected, budget_ref: budget.budget_ref },
				budget,
				budget_preflight: reservation.value,
				stop_signals: value.stopSignals,
				...(snapshot.value.executed_action === undefined
					? {}
					: { executed_action: snapshot.value.executed_action }),
			};
		},
		async verifyExecution(request: ExecutionVerificationRequest): Promise<ExecutionProof | undefined> {
			// A byte-shaped claim is not an observed action. Only the registered
			// D/I observer may produce a proof; absent observer stays fail-closed.
			return config.verifyExecution?.(request);
		},
	};
}

/** Boundary recheck used by the worker before it treats a tool call as real
 *  progress (T05 debt: a stop that appears AFTER a successful commit must stop
 *  the NEXT tool call, and must not be recorded as activity). Single-sourced
 *  with the commit path so the worker and the store can never disagree about
 *  which facts are a stop. Unreadable facts are NOT "no stop": they are
 *  reported as gaps and the caller must treat them as blocking. */
export function readRuntimeStopFacts(input: {
	agenticdocRoot: string;
	key: string;
	taskKey: string;
	runId: string;
	clockMs?: number;
}): { stop_signals: StopSignal[]; gaps: string[] } {
	const authority = readRuntimeAuthority({
		agenticdocRoot: input.agenticdocRoot,
		key: input.key,
		source: "worker-local",
		taskKey: input.taskKey,
		runId: input.runId,
		// A boundary recheck is about NOW: a deadline that passed before this
		// tool is a real stop fact and must not silently become "no signal".
		clockMs: input.clockMs ?? Date.now(),
	});
	if (!authority.ok) return { stop_signals: [], gaps: authority.gaps };
	return { stop_signals: authority.value.stopSignals, gaps: [] };
}

/** A successor names the exact run. Completed runs may still have successors. */
export function dispatchParentRunRefusal(root: string, key: string, child: string, ref: string): string | undefined {
	const task = ref.split("@", 1)[0] ?? "";
	const invalid = `parent-run-unavailable: ${ref || "empty binding"}`;
	if (keyNameRefusal(key) !== null || keyNameRefusal(task) !== null || task === child) return invalid;
	const taskDir = path.join(root, key, "workers", task);
	if (!safeFile(root, path.join(taskDir, "run.json"))) return invalid;
	const run = readRunState(taskDir);
	if (
		!run ||
		run.run_id !== ref ||
		run.task_key !== task ||
		run.owner_key !== key ||
		isoMillis(run.started_at) === undefined ||
		isoMillis(ref.slice(task.length + 1)) === undefined
	)
		return invalid;
	if (workerRunCancelled(run)) return `parent-cancel: ${ref}`;
	if (run.status === "failed" && run.stop_kind === "worker-deadline") return `worker-deadline: ${ref}`;
	return run.status === "running" || isTerminalRunStatus(run.status) ? undefined : invalid;
}

// ── ONE production host composition (T06-J) ──────────────────────────────────

/** Existing pi session custom-entry channel. These entries are observations of
 *  real host events, never a second selection/execution/DP store or ledger. */
export const RUNTIME_BUDGET_ENTRY_TYPE = "mw-runtime-budget-v1";

interface EntryData {
	id: string;
	kind: "genesis" | "event";
	unit: string;
	parent: string;
	at: number;
	/** Exact pinned source facts, never copied from a model parameter. */
	source_pin: string;
	started_at: string;
	key: string;
	task_key: string;
	run_id: string;
	claim_id: string;
	event?: RuntimeBudgetReplayEvent;
}

interface SessionLikeEntry {
	type?: string;
	id?: string;
	customType?: string;
	data?: unknown;
	timestamp?: string;
	message?: { role?: string };
}

interface SessionReader {
	read(): {
		entries: readonly SessionLikeEntry[];
		file: string | undefined;
		id: string;
	};
	append(customType: string, data: unknown): void;
}

interface RegisteredPmStage {
	eventId: string;
	grantDigest: string;
	stageId: string;
	scopeRef: string;
	matterRef: string;
	parentMatterRef?: string;
	authorityKind: "user-delegated-duty-pm";
	stageRef: string;
	receivedAt: number;
	deadline: string;
	genesisRef: string;
}

interface RegisteredSource {
	key: string;
	source: LocalSource;
	role: HostRole;
	claimId: string;
	taskKey: string;
	runId?: string;
	executionRunId: string;
	cardPath: string;
	sourcePin: string;
	budgetStartedAt: string;
	authorizationUnit: string;
	parentBudgetRef: string;
	matterRef: string;
	costUnit: string;
	writeFace: string[];
	initial: MatterBudgetV1;
	cardBudget: MatterBudgetV1;
	bindingVersion: string;
	stage?: RegisteredPmStage;
}

interface PendingCall {
	localRef: string;
	callId: string;
	source: RegisteredSource;
	terminalRefs: Set<string>;
}

/** Host-owned proof of ONE real final action. It is captured from the same
 *  reservation/observation session events and never grants a new effect. */
interface TerminalArchivalRecord {
	proof: ExecutedActionTerminalProof;
	archiveStarted: boolean;
	archived: boolean;
}

interface Controllers {
	store: LocalSelectionStore;
	budget: RuntimeBudgetController;
	execution: RuntimeExecutionController;
}

export interface RuntimeHostToolRuntime {
	key: string;
	commitSelection(request: CommitSelectionRequest): Promise<RuntimeExecutionResult>;
}

/** Locator fields only. The real task_key/run_id/toolCallId are read from the
 *  host's private active source, never supplied by a PM-owned watch value. */
export interface RuntimeExecutionCertificateScope {
	key: string;
	source: LocalSource;
	claim_id: string;
}

/** Host-only readonly correlation of the CURRENT active local_ref with the
 *  actual toolCallId/run_id observed in this host lifetime. The committed
 *  execution record is compared, never used as the source of the executor. */
export interface RuntimeCurrentExecutionCertificate {
	current: true;
	local_ref: string;
	run_id: string;
	tool_call_id: string;
	task_key: string;
	executor: string;
	action_ref: string;
	result_ref: string;
	effect_state: "known";
	verifier_ref: string;
	target_digest: string;
	binding: HostBinding;
	observed_at: string;
}

export interface RuntimeHostToolRuntimeSource {
	bindExpectedFor(reader: (localRef: string) => RuntimeOfferExpected | undefined): void;
	toolRuntime(): RuntimeHostToolRuntime | undefined;
	currentExecutionCertificateFor?(
		localRef: string,
		scope: RuntimeExecutionCertificateScope,
	): RuntimeCurrentExecutionCertificate | undefined;
}

export interface RuntimeHostAdapterHooks
	extends Pick<RuntimeHostAdapterConfig, "authorizationFor" | "budgetSnapshotFor" | "verifyExecution"> {
	authorizationGapsFor?: (expected: RuntimeOfferExpected) => string[];
}

export interface RuntimeHostDispatchObservation {
	key: string;
	taskKey: string;
	claimId: string;
	taskMdPath: string;
	dispatchedAt: string;
}

export interface RuntimeHostWorkerActivation {
	agenticdocRoot: string;
	key: string;
	taskKey: string;
	runId: string;
	startedAt: string;
	kind: string;
	taskContent: string;
	writeFaceEntries?: readonly string[];
}

export interface RuntimeHostCounts {
	registered: number;
	reserves: number;
	observes: number;
	unknowns: number;
	blocks: number;
	/** Pre-body ADMISSION vetoes: refused before any allowance was reserved. */
	vetoes: number;
	appends: number;
	dispositions: number;
	childReserves: number;
	childSettles: number;
	selectionCommits: number;
	recordedWithDisposition: number;
	recordedWithoutDisposition: number;
	duplicateNoReplay: number;
	childBlockedInsufficient: number;
	busyIdleTransitions: number;
	duplicateShutdown: number;
	newCardTurnRefreshes: number;
	replayedActionRefs: number;
	stageAdmissions: number;
	stageRejections: number;
	shutdownOutcome: string;
	idleDisposition: boolean;
}

export interface RuntimeHostContinuationInput {
	agenticdocRoot: string;
	key: string;
	taskKey: string;
	runId: string;
	localRef: string;
	claimId: string;
	bindingVersion: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}
function nonblank(value: unknown): value is string {
	return typeof value === "string" && value.trim() !== "";
}
function canonicalRelative(root: string, target: string): string | undefined {
	const rel = path.relative(path.resolve(root), path.resolve(root, target)).replace(/\\/g, "/");
	return rel && !rel.startsWith("../") && rel !== ".." && !path.posix.isAbsolute(rel) ? rel : undefined;
}
function writeFaceOf(head: Record<string, string>, declared?: readonly string[]): string[] {
	const raw = declared ?? (head.write_face ?? "").split(",");
	return [
		...new Set(raw.map((entry) => entry.trim().replace(/\\/g, "/")).filter((entry) => entry !== "" && entry !== "-")),
	];
}
function entryData(value: unknown): EntryData | undefined {
	if (!isRecord(value) || !nonblank(value.id) || !nonblank(value.unit) || !nonblank(value.parent)) return undefined;
	if (value.kind !== "genesis" && value.kind !== "event") return undefined;
	if (typeof value.at !== "number" || !Number.isSafeInteger(value.at)) return undefined;
	if (!nonblank(value.source_pin) || !nonblank(value.started_at) || !nonblank(value.key)) return undefined;
	if (!nonblank(value.task_key) || !nonblank(value.run_id) || !nonblank(value.claim_id)) return undefined;
	return value as unknown as EntryData;
}
function replayEvent(value: unknown, source: RegisteredSource): RuntimeBudgetReplayEvent | undefined {
	if (!isRecord(value) || typeof value.at !== "number" || !Number.isSafeInteger(value.at)) return undefined;
	if (!isRecord(value.request)) return undefined;
	const binding = value.request;
	if (
		binding.authorization_unit !== source.authorizationUnit ||
		binding.parent_budget_ref !== source.parentBudgetRef ||
		!nonblank(binding.matter_ref)
	)
		return undefined;
	if (value.kind === "reserve" || value.kind === "observe") {
		if (!Array.isArray(value.evidence)) return undefined;
		if (!value.evidence.every((item) => isRecord(item) && nonblank(item.ref) && nonblank(item.sha256)))
			return undefined;
	}
	if (
		value.kind === "reserve" ||
		value.kind === "observe" ||
		value.kind === "reserve-child" ||
		value.kind === "settle"
	)
		return value as unknown as RuntimeBudgetReplayEvent;
	return undefined;
}

/** Digest over the same canonical target manifest shape as the real byte
 *  verifier, built only from host-captured evidence attached to the reserve and
 *  observe session events. Absent or duplicate refs fail closed. */
function terminalEvidenceDigest(evidence: readonly RuntimeBudgetEvidenceDigest[]): string | undefined {
	if (evidence.length === 0) return undefined;
	const seen = new Set<string>();
	const manifest: { path: string; state: "file"; sha256: string }[] = [];
	for (const item of [...evidence].sort((a, b) => a.ref.localeCompare(b.ref))) {
		if (!nonblank(item.ref) || seen.has(item.ref) || !/^[a-f0-9]{64}$/.test(item.sha256)) return undefined;
		seen.add(item.ref);
		manifest.push({ path: item.ref, state: "file", sha256: item.sha256 });
	}
	return `sha256:${crypto.createHash("sha256").update(JSON.stringify(manifest), "utf8").digest("hex")}`;
}

/** The ONLY exhausted state that permits terminal bookkeeping: the last
 *  authorized step/cost was consumed by the observed action, with no hold,
 *  in-flight call, overrun, no-progress stop, deadline expiry or replenishment. */
function exactTerminalExhaustion(
	snapshot: RuntimeBudgetControllerSnapshot,
	source: RegisteredSource,
	at: number,
): boolean {
	return (
		snapshot.blocked === "budget-exhausted" &&
		snapshot.available_steps === 0 &&
		snapshot.available_cost === 0 &&
		snapshot.held_steps === 0 &&
		snapshot.held_cost === 0 &&
		snapshot.in_flight === 0 &&
		snapshot.budget.steps_consumed === snapshot.budget.max_steps &&
		snapshot.budget.remaining_cost === 0 &&
		snapshot.budget.no_progress_count < snapshot.budget.no_progress_limit &&
		snapshot.budget.deadline === source.initial.deadline &&
		snapshot.budget.cost_consumed + snapshot.budget.remaining_cost ===
			source.initial.cost_consumed + source.initial.remaining_cost &&
		at < Date.parse(snapshot.budget.deadline)
	);
}

/** One host object per activated extension window. All authority is registered
 *  from exact dispatch/activation observations; ask parameters only join it. */
export class ProductionRuntimeHost implements RuntimeHostToolRuntimeSource {
	private readonly projectRoot: string;
	private readonly root: string;
	private readonly clock: () => number;
	private readonly sourcesByTask = new Map<string, RegisteredSource>();
	private readonly sourcesByUnit = new Map<string, RegisteredSource>();
	private readonly pendingCalls = new Map<string, PendingCall>();
	private readonly observedResults = new Set<string>();
	private readonly settledUnknown = new Set<string>();
	private readonly counts: RuntimeHostCounts = {
		registered: 0,
		reserves: 0,
		observes: 0,
		unknowns: 0,
		blocks: 0,
		vetoes: 0,
		appends: 0,
		dispositions: 0,
		childReserves: 0,
		childSettles: 0,
		selectionCommits: 0,
		recordedWithDisposition: 0,
		recordedWithoutDisposition: 0,
		duplicateNoReplay: 0,
		childBlockedInsufficient: 0,
		busyIdleTransitions: 0,
		duplicateShutdown: 0,
		newCardTurnRefreshes: 0,
		replayedActionRefs: 0,
		stageAdmissions: 0,
		stageRejections: 0,
		shutdownOutcome: "none",
		idleDisposition: false,
	};
	private expectedFor: ((localRef: string) => RuntimeOfferExpected | undefined) | undefined;
	private session: SessionReader | undefined;
	private controllers: Controllers | undefined;
	private frozenKey: string | undefined;
	private activeLocalRef: string | undefined;
	private activeSource: LocalSource | undefined;
	private activeMatterRef: string | undefined;
	/** Submission context is not an executable selection binding. */
	private committingSource: RegisteredSource | undefined;
	private selectionAttempted = false;
	private lastLocalRef: string | undefined;
	private lastToolCallId: string | undefined;
	private lastDispositionRef: string | undefined;
	/** R1 authentic disposition_ref -> offer local_ref joins, registered only
	 *  at finish() for real finishing actions. Never a synthetic trusted ref. */
	private readonly dispositionRefToLocalRef = new Map<string, string>();
	private shutdownClosed = false;
	private historyFailed: string | undefined;
	private observationFailed = false;
	private controlBlocked = false;
	private terminalArchival: TerminalArchivalRecord | undefined;
	private stageDirection: PmStageDirection | undefined;
	private stageChannel: { projectDir: string; home?: string; claimId?: string; nowMs?: number } | undefined;
	private stageRefusal: { gaps: string[]; reason: string; eventId?: string } | undefined;
	private stageGenesisRef: string | undefined;
	private readonly observedToolResults = new Map<
		string,
		LocalQgExecutionObservation & { target?: RuntimeBudgetEvidenceDigest }
	>();
	/** Locator from the terminal Worker readback. The launcher authenticates the run. */
	private currentReviewer: { taskKey: string; runId: string } | undefined;

	constructor(projectDir: string, clock: () => number = () => Date.now()) {
		this.projectRoot = path.resolve(projectDir);
		this.root = path.resolve(controlRoot(projectDir));
		this.clock = clock;
	}

	bindExpectedFor(reader: (localRef: string) => RuntimeOfferExpected | undefined): void {
		this.expectedFor = reader;
	}

	countsSnapshot(): RuntimeHostCounts {
		const state = this.storeRecordState();
		return {
			...this.counts,
			recordedWithDisposition: state.withDisposition,
			recordedWithoutDisposition: state.withoutDisposition,
			idleDisposition: state.withDisposition > 0 || state.withoutDisposition > 0,
		};
	}

	/** Real session shutdown: ONE busy → idle transition; no finalization on an
	 *  ordinary agent_end/turn boundary. A duplicate shutdown is counted, never
	 *  replayed as another disposition. */
	onAgentEnd(reason: string): void {
		if (reason !== "shutdown") return;
		if (this.shutdownClosed) {
			this.counts.duplicateShutdown += 1;
			return;
		}
		this.shutdownClosed = true;
		this.settleUnknown();
		const state = this.storeRecordState();
		this.counts.busyIdleTransitions += 1;
		this.counts.shutdownOutcome =
			state.withDisposition > 0 ? "ok" : state.withoutDisposition > 0 ? "reconciliation-required" : "idle";
		this.counts.idleDisposition = state.withDisposition > 0 || state.withoutDisposition > 0;
	}

	private storeRecordState(): { withDisposition: number; withoutDisposition: number } {
		const source = this.activeSourceFor() ?? [...this.sourcesByUnit.values()][0];
		if (source === undefined || this.lastLocalRef === undefined || this.controllers === undefined)
			return { withDisposition: 0, withoutDisposition: 0 };
		const request = { source: source.source, ref: this.lastLocalRef, task_key: source.taskKey };
		const execution = this.controllers.store.readExecution(request);
		if (execution.status !== "ok" || execution.record === undefined)
			return { withDisposition: 0, withoutDisposition: 0 };
		const executionValue = execution.record as { executor?: unknown };
		let toolCallId = this.lastToolCallId;
		if (toolCallId === undefined && typeof executionValue.executor === "string") {
			try {
				const parsed: unknown = JSON.parse(executionValue.executor);
				if (Array.isArray(parsed) && typeof parsed[1] === "string") toolCallId = parsed[1];
			} catch {
				toolCallId = undefined;
			}
		}
		const dispositionRef =
			this.lastDispositionRef ?? (toolCallId === undefined ? undefined : `disposition:${toolCallId}`);
		if (dispositionRef === undefined) return { withDisposition: 0, withoutDisposition: 1 };
		const disposition = this.controllers.store.readDisposition({
			...request,
			ref: dispositionRef,
		});
		return disposition.status === "ok"
			? { withDisposition: 1, withoutDisposition: 0 }
			: { withDisposition: 0, withoutDisposition: 1 };
	}

	toolRuntime(): RuntimeHostToolRuntime | undefined {
		if (this.frozenKey === undefined) return undefined;
		return {
			key: this.frozenKey,
			commitSelection: async (request) => this.commitSelection(request),
		};
	}

	/** Read the host's PRIVATE current action observation and correlate it with
	 *  the single frozen store's committed execution. The executor, run and
	 *  toolCallId come from host state; the record fields are equality checks.
	 *  The strict RuntimeExecutionController verifier remains a separate
	 *  boundary and is not replaced or relaxed here. */
	currentExecutionCertificateFor(
		localRef: string,
		scope: RuntimeExecutionCertificateScope,
	): RuntimeCurrentExecutionCertificate | undefined {
		const source = this.activeSourceFor();
		const toolCallId = this.lastToolCallId;
		if (
			source === undefined ||
			toolCallId === undefined ||
			this.activeLocalRef !== localRef ||
			scope.key !== source.key ||
			scope.source !== source.source ||
			scope.claim_id !== source.claimId
		)
			return undefined;
		const executor = runtimeExecutionExecutor(source.executionRunId, toolCallId);
		const resultRef = `tool_result:${toolCallId}`;
		const observation = this.observedToolResults.get(toolCallId);
		if (
			observation === undefined ||
			observation.local_ref !== localRef ||
			observation.result_ref !== resultRef ||
			observation.run_id !== source.executionRunId ||
			observation.executor !== executor ||
			observation.is_error ||
			observation.completion !== "complete"
		)
			return undefined;
		const read = this.controllers?.store.readExecution({
			source: source.source,
			ref: localRef,
			task_key: source.taskKey,
		});
		if (read?.status !== "ok" || read.record === undefined) return undefined;
		const record = read.record;
		if (
			record.source !== source.source ||
			record.local_ref !== localRef ||
			record.action_ref !== toolCallId ||
			record.result_ref !== resultRef ||
			record.executor !== executor ||
			record.effect_state !== "known" ||
			!record.verified_by.trim() ||
			!record.target_digest.trim()
		)
			return undefined;
		const binding = this.readBinding();
		if (
			binding === undefined ||
			binding.key !== scope.key ||
			binding.owner !== scope.claim_id ||
			binding.claim_id !== scope.claim_id ||
			binding.role !== source.role ||
			record.host_binding.key !== binding.key ||
			record.host_binding.owner !== binding.owner ||
			record.host_binding.claim_id !== binding.claim_id ||
			record.host_binding.binding_version !== binding.binding_version
		)
			return undefined;
		return {
			current: true,
			local_ref: localRef,
			run_id: source.executionRunId,
			tool_call_id: toolCallId,
			task_key: source.taskKey,
			executor,
			action_ref: toolCallId,
			result_ref: resultRef,
			effect_state: "known",
			verifier_ref: record.verified_by,
			target_digest: record.target_digest,
			binding: structuredClone(record.host_binding),
			observed_at: new Date(this.clock()).toISOString(),
		};
	}

	adapterHooks(): RuntimeHostAdapterHooks {
		return {
			authorizationFor: (localRef, expected) => this.authorizationFor(localRef, expected),
			authorizationGapsFor: (expected) => this.authorizationGapsFor(expected),
			budgetSnapshotFor: (input) => this.budgetSnapshotFor(input),
			verifyExecution: async (request) => this.controllers?.execution.verifyExecution(request),
		};
	}

	/** PM session_start composition: read the ORIGINAL private channel request +
	 *  receipt, verify typed sender-origin scope and admit a REAL PM stage. A
	 *  plain-text historical event records a concrete refusal; it never grants. */
	admitPmStageFromChannel(input: {
		projectDir: string;
		sessionId: string;
		home?: string;
		claimId?: string;
		nowMs?: number;
	}): RuntimeFactRead<RegisteredSource> {
		this.stageChannel = input;
		const read = findPmStageDirection({
			...input,
			eventId: this.stageDirection?.event_id,
			nowMs: input.nowMs ?? this.clock(),
		});
		if (!read.ok) {
			this.stageRefusal = {
				gaps: [...read.gaps],
				reason: read.reason,
				...(read.eventId === undefined ? {} : { eventId: read.eventId }),
			};
			this.counts.stageRejections += 1;
			return { ok: false, gaps: [...read.gaps], reason: read.reason };
		}
		const registered = this.registerPmStage(read.value);
		if (!registered.ok) {
			this.stageRefusal = { gaps: [...registered.gaps], reason: registered.reason, eventId: read.value.event_id };
			this.counts.stageRejections += 1;
		}
		return registered;
	}

	/** Host-only registration of a verified stage direction. No worker dispatch,
	 *  no run.json, no fake source and no model-supplied grant. The same stage
	 *  across turn/card/offer/restart reuses the SAME session ledger/unit. */
	private registerPmStage(direction: PmStageDirection): RuntimeFactRead<RegisteredSource> {
		if (keyNameRefusal(direction.key) !== null || !direction.stage_id.trim())
			return { ok: false, gaps: ["stage.key", "stage.stage_id"], reason: "invalid PM stage identity" };
		if (this.stageDirection !== undefined) {
			if (this.stageDirection.event_id !== direction.event_id)
				return { ok: false, gaps: ["stage-lifecycle-replay"], reason: "a second event cannot reset this stage" };
			if (
				this.stageDirection.grant_digest !== direction.grant_digest ||
				this.stageDirection.card_sha256 !== direction.card_sha256 ||
				this.stageDirection.matter_ref !== direction.matter_ref ||
				this.stageDirection.scope_ref !== direction.scope_ref ||
				this.stageDirection.deadline !== direction.deadline
			)
				return { ok: false, gaps: ["stage-replay-drift"], reason: "replayed genesis changed under the same event" };
		}
		const card = readBytes(this.root, path.join(this.root, direction.key, direction.card_path));
		if (!card.ok) return card;
		const head = parseHead(card.value.toString("utf8"));
		if (
			!head.ok ||
			head.value.owning_pm_claim !== direction.claim_id ||
			sha256EolNormalizedBytes(card.value) !== direction.card_sha256
		)
			return {
				ok: false,
				gaps: ["stage.card-pin", "card.owning_pm_claim"],
				reason: "stage pin or card owner drifted before genesis",
			};
		const parsed = buildMatterBudgetFromCard(card.value.toString("utf8"), {
			cardRef: direction.card_path,
			cardSha256: direction.card_sha256,
			runStartedAt: direction.started_at,
			runRef: direction.stage_ref,
			indexRef: "_index.parallel",
		});
		if (!parsed.ok) return parsed;
		const budget = parsed.value.budget;
		const deadlineMs = Date.parse(budget.deadline);
		if (
			budget.matter_ref !== direction.matter_ref ||
			budget.parent_matter_ref !== direction.parent_matter_ref ||
			budget.budget_ref !== `${direction.card_path}#事项预算事实` ||
			budget.max_steps > direction.max_steps ||
			budget.remaining_cost > direction.remaining_cost ||
			budget.no_progress_limit > direction.no_progress_limit ||
			budget.max_steps > PM_STAGE_MAX_STEPS ||
			budget.remaining_cost > PM_STAGE_MAX_COST ||
			budget.no_progress_limit > PM_STAGE_MAX_NO_PROGRESS ||
			deadlineMs <= direction.received_at ||
			deadlineMs > Date.parse(direction.deadline) ||
			Date.parse(direction.deadline) > direction.received_at + PM_STAGE_MAX_WINDOW_MS ||
			this.clock() >= deadlineMs
		)
			return {
				ok: false,
				gaps: ["stage.card-budget", "stage.limits", "grant-expired"],
				reason: "pinned card budget/deadline is not a bounded subset of the typed stage grant",
			};
		if (direction.parent_matter_ref !== undefined) {
			const history = direction.grant.producer_history;
			if (
				history === undefined ||
				history.matter_ref !== direction.parent_matter_ref ||
				Date.parse(history.deadline) >= direction.received_at
			)
				return {
					ok: false,
					gaps: ["stage.producer-attribution"],
					reason: "expired producer history must be separately reported, never borrowed or renewed",
				};
		}
		const sourceRead = this.pmStageSource(direction);
		if (!sourceRead.ok) return sourceRead;
		const ledger = new PmStageLedger();
		const admitted = ledger.admit(this.session as PmStageSession | undefined, direction);
		if (!admitted.ok) return { ok: false, gaps: [...admitted.gaps], reason: admitted.reason };
		const registered = this.registerSource({
			key: direction.key,
			source: "pm",
			role: "pm",
			claimId: direction.claim_id,
			taskKey: direction.stage_id,
			executionRunId: `pm-stage:${direction.stage_id}@${direction.started_at}`,
			cardPath: direction.card_path,
			sourcePin: direction.card_sha256,
			budgetStartedAt: direction.started_at,
			writeFace: direction.write_face,
			stageRef: direction.stage_ref,
			stage: {
				eventId: direction.event_id,
				grantDigest: direction.grant_digest,
				stageId: direction.stage_id,
				scopeRef: direction.scope_ref,
				matterRef: direction.matter_ref,
				...(direction.parent_matter_ref === undefined ? {} : { parentMatterRef: direction.parent_matter_ref }),
				authorityKind: direction.authority_kind,
				stageRef: direction.stage_ref,
				receivedAt: direction.received_at,
				deadline: direction.deadline,
				genesisRef: admitted.value.genesisRef,
			},
		});
		if (!registered.ok) return registered;
		this.stageDirection = direction;
		this.stageGenesisRef = admitted.value.genesisRef;
		this.stageRefusal = undefined;
		if (!admitted.value.replayed) this.counts.stageAdmissions += 1;
		return registered;
	}

	/** Current host-derived stage identity for ask/offer. Re-reads the live claim,
	 *  current session and absolute deadline on EVERY ask; a stale stage is gone. */
	stageIdentity(
		terminalProof = false,
	):
		| { key: string; claimId: string; stageId: string; scopeRef: string; matterRef: string; grantDigest: string }
		| undefined {
		const direction = this.stageDirection;
		const phaseOnlyRefusal =
			terminalProof && this.stageRefusal?.gaps.length === 1 && this.stageRefusal.gaps[0] === "index.phase";
		if (
			direction === undefined ||
			(this.stageRefusal !== undefined && !phaseOnlyRefusal) ||
			this.stageChannel === undefined
		)
			return undefined;
		const current = findPmStageDirection({
			...this.stageChannel,
			sessionId: this.session?.read().id ?? "",
			eventId: direction.event_id,
			nowMs: this.stageChannel.nowMs ?? this.clock(),
			terminalProof,
		});
		if (!current.ok || current.value.grant_digest !== direction.grant_digest) return undefined;
		if (this.session?.read().id !== direction.session_id) return undefined;
		if (this.clock() >= Date.parse(direction.deadline)) return undefined;
		const row = readKeyRows(this.root, direction.key);
		if (
			!row.ok ||
			row.value.claimId !== direction.claim_id ||
			(row.value.phase !== "EXECUTE" && !(terminalProof && row.value.phase === "VERIFY"))
		)
			return undefined;
		const source = [...this.sourcesByUnit.values()].find((item) => item.stage?.eventId === direction.event_id);
		if (source?.stage === undefined) return undefined;
		return {
			key: direction.key,
			claimId: direction.claim_id,
			stageId: direction.stage_id,
			scopeRef: direction.scope_ref,
			matterRef: direction.matter_ref,
			grantDigest: direction.grant_digest,
		};
	}

	/** Exact refusal/attribution for the PM report; no source facts are invented. */
	stageAdmissionState(): {
		admitted: boolean;
		refusal?: { gaps: string[]; reason: string; eventId?: string };
		attribution?: ReturnType<typeof PmStageLedger.attribution>;
		genesisRef?: string;
	} {
		if (this.stageDirection === undefined)
			return { admitted: false, ...(this.stageRefusal === undefined ? {} : { refusal: { ...this.stageRefusal } }) };
		return {
			admitted: this.stageIdentity() !== undefined,
			...(this.stageRefusal === undefined ? {} : { refusal: { ...this.stageRefusal } }),
			attribution: PmStageLedger.attribution(this.stageDirection),
			...(this.stageGenesisRef === undefined ? {} : { genesisRef: this.stageGenesisRef }),
		};
	}

	/** Register the dispatched REVIEW run the PM arranged for this stage. A
	 *  registration alone produces no verdict; the producer still verifies it. */
	setCurrentReviewer(reviewer: { taskKey: string; runId: string } | undefined): void {
		this.currentReviewer = reviewer;
	}

	consumeTerminalLocalReview(key: string, taskKey: string): void {
		const source = this.activeSourceFor();
		const localRef = this.activeLocalRef;
		const actionToolCallId = this.lastToolCallId;
		if (
			!source?.stage ||
			source.key !== key ||
			!localRef ||
			!actionToolCallId ||
			this.shutdownClosed ||
			this.controlBlocked ||
			this.observationFailed ||
			!this.stageIdentity() ||
			keyNameRefusal(taskKey) !== null
		)
			return;
		const taskDir = path.join(this.root, key, "workers", taskKey);
		const run = readRunState(taskDir);
		if (!run || run.kind !== "review" || run.status !== "done" || run.exit !== 0) return;
		const dispatch = readTerminalReviewDispatch(this.root, key, taskKey, run.run_id);
		if (!dispatch.ok) return;
		const card = readBytes(this.root, path.join(this.root, key, dispatch.value.cardPath));
		if (!card.ok || !/^```mw-local-qg[ \t]*\r?$/m.test(card.value.toString("utf8"))) return;
		this.setCurrentReviewer({ taskKey, runId: run.run_id });
		this.recordLocalQg(source, localRef, actionToolCallId);
	}

	currentOfflineGateExecution(
		localRef: string,
		scope: RuntimeExecutionCertificateScope,
		expected: RuntimeOfferExpected,
		action: string,
	):
		| (RuntimeCurrentExecutionCertificate & {
				qg_refs: string[];
				qg_sha256: string;
				review_run_id: string;
				review_artifact_ref: string;
				review_artifact_sha256: string;
		  })
		| undefined {
		if (this.shutdownClosed || this.controlBlocked || this.observationFailed) return undefined;
		const current = this.currentExecutionCertificateFor(localRef, scope);
		const selection = this.controllers?.store.readSelection({ source: "pm", ref: localRef });
		const record = selection?.record;
		if (
			!current ||
			selection?.status !== "ok" ||
			!record ||
			record.parent_decision_ref != null ||
			record.selected_action !== action ||
			record.matter_ref !== expected.matter_ref ||
			record.matter_version !== expected.matter_version ||
			record.material_digest !== expected.material_digest ||
			record.basis_digest !== expected.basis_digest
		)
			return undefined;
		const stage = this.stageIdentity(true);
		if (!stage || expected.identity?.scopeRef !== stage.scopeRef || expected.stage_matter_ref !== stage.matterRef)
			return undefined;
		const input = this.localQgInput({ localRef, actionToolCallId: current.tool_call_id }, true);
		const qg = evaluateLocalQg(input);
		const provenance = input.review?.provenance;
		return qg.qg_pass && input.review && provenance
			? {
					...current,
					qg_refs: qg.basis_refs,
					qg_sha256: input.review.source_digest,
					review_run_id: provenance.reviewer_run_id,
					review_artifact_ref: provenance.artifact_ref,
					review_artifact_sha256: provenance.artifact_sha256,
				}
			: undefined;
	}

	/** Typed QG consumer. It reads the frozen records and the REAL tool_call/
	 *  tool_result observation; no PASS/gate/sign/Done can be produced here.
	 *  The review is ALWAYS the registered producer's terminal artifact: there is
	 *  no caller-supplied review parameter, so a crafted typed verdict cannot
	 *  bypass `readCurrentIndependentReview`. */
	evaluateLocalQg(input: { localRef: string; actionToolCallId: string; clockMs?: number }): LocalQgDisposition {
		return evaluateLocalQg(this.localQgInput(input));
	}

	private localQgInput(
		input: { localRef: string; actionToolCallId: string; clockMs?: number },
		terminalProof = false,
	): LocalQgInput {
		const source = this.activeSourceFor();
		const stage: LocalQgStageSource | undefined =
			source?.stage !== undefined && this.stageIdentity(terminalProof) !== undefined
				? {
						authority_kind: "user-delegated-duty-pm",
						key: source.key,
						claim_id: source.claimId,
						stage_id: source.stage.stageId,
						scope_ref: source.stage.scopeRef,
						matter_ref: source.stage.matterRef,
						grant_digest: source.stage.grantDigest,
					}
				: undefined;
		let selection: Parameters<typeof evaluateLocalQg>[0]["selection"];
		let execution: Parameters<typeof evaluateLocalQg>[0]["execution"];
		try {
			selection = this.controllers?.store.readSelection({ source: "pm", ref: input.localRef }).record;
			execution = this.controllers?.store.readExecution({ source: "pm", ref: input.localRef }).record;
		} catch {
			selection = undefined;
			execution = undefined;
		}
		return {
			stage,
			selection,
			execution,
			observation: this.observedToolResults.get(input.actionToolCallId),
			review: this.readRegisteredReview({ stage, selection, execution, terminalProof }),
			nowMs: input.clockMs ?? Date.now(),
		};
	}

	/** Production attachment: read the registered reviewer's terminal artifact.
	 *  Any refusal yields `undefined`, which the consumer already refuses -- a
	 *  failed read is never upgraded into a PASS. */
	private readRegisteredReview(input: {
		stage: LocalQgStageSource | undefined;
		selection: Parameters<typeof evaluateLocalQg>[0]["selection"];
		execution: Parameters<typeof evaluateLocalQg>[0]["execution"];
		terminalProof: boolean;
	}): LocalQgReview | undefined {
		const reviewer = this.currentReviewer;
		const source = this.activeSourceFor();
		const { stage, selection, execution } = input;
		if (
			reviewer === undefined ||
			stage === undefined ||
			selection === undefined ||
			execution === undefined ||
			!source?.stage
		)
			return undefined;
		if (
			!this.currentExecutionCertificateFor(selection.local_ref, {
				key: stage.key,
				source: "pm",
				claim_id: stage.claim_id,
			})
		)
			return undefined;
		const target = this.observedToolResults.get(execution.action_ref)?.target;
		if (!target || source.writeFace.length !== 1 || source.writeFace[0] !== target.ref) return undefined;
		const currentTarget = targetFileDigest(this.projectRoot, target.ref);
		if (!currentTarget.ok || currentTarget.value !== target.sha256) return undefined;
		const read = readLauncherIndependentReview({
			agenticdocRoot: this.root,
			key: stage.key,
			reviewerTaskKey: reviewer.taskKey,
			reviewerRunId: reviewer.runId,
			clockMs: this.clock(),
			parentRunId: source.executionRunId,
			executionCreatedAt: execution.created_at,
			budgetDeadline: source.stage.deadline,
			expected: {
				ownerKey: stage.key,
				localRef: selection.local_ref,
				executionRef: execution.result_ref,
				toolCallRef: execution.action_ref,
				materialDigest: selection.material_digest,
				basisDigest: selection.basis_digest,
				implementerTaskKey: source.taskKey,
				implementerRunId: source.executionRunId,
			},
		});
		const targetAfter = targetFileDigest(this.projectRoot, target.ref);
		return read.ok && targetAfter.ok && targetAfter.value === target.sha256 && this.stageIdentity(input.terminalProof)
			? read.value
			: undefined;
	}

	/** The PM's authored typed session source must carry the host-derived
	 *  direction digest. Copied request text, an assistant observation or a
	 *  byte proof cannot mint a session-backed source. */
	private pmStageSource(direction: PmStageDirection): RuntimeFactRead<{ sourceRef: string }> {
		const session = this.session;
		if (session === undefined)
			return { ok: false, gaps: ["stage.session"], reason: "stage source session is not attached" };
		const entries = session
			.read()
			.entries.filter((entry) => entry.type === "custom" && entry.customType === PM_STAGE_SOURCE_ENTRY_TYPE);
		if (entries.length === 0) {
			try {
				session.append(PM_STAGE_SOURCE_ENTRY_TYPE, {
					event_id: direction.event_id,
					stage_digest: direction.grant_digest,
					source_digest: stageSourceDigest(direction),
					source_text:
						"authenticated private-channel request + started receipt + current claim/session/window + pinned card",
				});
				entries.push(
					...session
						.read()
						.entries.filter(
							(entry) => entry.type === "custom" && entry.customType === PM_STAGE_SOURCE_ENTRY_TYPE,
						),
				);
			} catch {
				return {
					ok: false,
					gaps: ["stage.source-observation-unknown"],
					reason: "production typed source append failed",
				};
			}
		}
		if (entries.length !== 1)
			return { ok: false, gaps: ["stage.source"], reason: "exactly one typed PM stage source record is required" };
		const data = entries[0]?.data;
		if (
			!isRecord(data) ||
			data.event_id !== direction.event_id ||
			data.stage_digest !== direction.grant_digest ||
			data.source_digest !== stageSourceDigest(direction) ||
			typeof data.source_text !== "string" ||
			!data.source_text.trim()
		)
			return {
				ok: false,
				gaps: ["stage.source-digest"],
				reason: "typed session source does not match the verified direction",
			};
		return { ok: true, value: { sourceRef: `${PM_STAGE_SOURCE_ENTRY_TYPE}#${direction.event_id}` } };
	}

	private stageStop(source: RegisteredSource): { stop_signals: StopSignal[]; gaps: string[] } {
		if (source.stage === undefined || this.stageIdentity() === undefined)
			return { stop_signals: [], gaps: ["host.stage-source-revoked-or-drifted"] };
		const row = readKeyRows(this.root, source.key);
		if (!row.ok || row.value.claimId !== source.claimId) return { stop_signals: [], gaps: ["index.claim"] };
		if (this.clock() >= Date.parse(source.stage.deadline))
			return { stop_signals: [{ signal_ref: `${source.stage.stageRef}#deadline`, kind: "key-budget" }], gaps: [] };
		return { stop_signals: [], gaps: [] };
	}

	attachSession(ctx: ExtensionContext, append: (customType: string, data: unknown) => void): void {
		this.session = {
			read: () => ({
				entries: ctx.sessionManager.getEntries() as readonly SessionLikeEntry[],
				file: ctx.sessionManager.getSessionFile(),
				id: ctx.sessionManager.getSessionId(),
			}),
			append,
		};
		for (const source of this.sourcesByUnit.values()) this.attachSource(source);
	}

	registerWorkerActivation(input: RuntimeHostWorkerActivation): RuntimeFactRead<RegisteredSource> {
		if (path.resolve(input.agenticdocRoot) !== this.root)
			return { ok: false, gaps: ["agenticdocRoot"], reason: "activation control root drift" };
		const head = parseHead(input.taskContent);
		if (!head.ok) return head;
		const cardPath = head.value.card_path;
		const sourcePin = head.value.card_sha256;
		if (cardPath === undefined || sourcePin === undefined)
			return { ok: false, gaps: ["card_path", "card_sha256"], reason: "dispatched pin missing" };
		const role = WORKER_ROLES.find((candidate) => candidate === input.kind);
		if (role === undefined) return { ok: false, gaps: ["role"], reason: "unsupported worker kind" };
		return this.registerSource({
			key: input.key,
			source: "worker-local",
			role,
			taskKey: input.taskKey,
			runId: input.runId,
			executionRunId: input.runId,
			cardPath,
			sourcePin,
			budgetStartedAt: input.startedAt,
			writeFace: writeFaceOf(head.value, input.writeFaceEntries),
		});
	}

	registerPmDispatch(input: RuntimeHostDispatchObservation): RuntimeFactRead<RegisteredSource> {
		let taskContent: string;
		try {
			taskContent = fs.readFileSync(input.taskMdPath, "utf8");
		} catch {
			return { ok: false, gaps: ["task.md"], reason: "dispatched envelope unavailable" };
		}
		const head = parseHead(taskContent);
		if (!head.ok) return head;
		const cardPath = head.value.card_path;
		const sourcePin = head.value.card_sha256;
		if (cardPath === undefined || sourcePin === undefined)
			return { ok: false, gaps: ["card_path", "card_sha256"], reason: "dispatched pin missing" };
		return this.registerSource({
			key: input.key,
			source: "pm",
			role: "pm",
			claimId: input.claimId,
			taskKey: input.taskKey,
			executionRunId: `${input.taskKey}@${input.dispatchedAt}`,
			cardPath,
			sourcePin,
			budgetStartedAt: input.dispatchedAt,
			writeFace: writeFaceOf(head.value),
		});
	}

	/** Exact canonical card locator into observations made by registerPmDispatch.
	 * A locator never registers a source or supplies task/claim/budget authority.
	 * Every read rechecks the pin, live authority/stops and existing accounting;
	 * neither the budget start nor its counters are changed here. */
	readPmDispatchSource(input: {
		key: string;
		claimId: string;
		cardPath: string;
	}): RuntimeFactRead<{ identity: RuntimeOfferExpected["identity"]; matterRef: string; signature: string }> {
		if (!/^tasks\/[\w-][\w.-]*\.md$/.test(input.cardPath) || input.cardPath.includes(".."))
			return fail("noncanonical source card", ["source_card"]);
		const matches = [...this.sourcesByTask.values()].filter(
			(source) =>
				source.source === "pm" &&
				source.stage === undefined &&
				source.key === input.key &&
				source.claimId === input.claimId &&
				source.cardPath === input.cardPath,
		);
		const source = matches[0];
		if (
			matches.length !== 1 ||
			source === undefined ||
			this.controllers === undefined ||
			this.controlBlocked ||
			this.shutdownClosed ||
			this.observationFailed ||
			this.historyFailed !== undefined
		)
			return fail("unique live registered dispatch required", ["host.registered-dispatch"]);
		const identity = {
			source: "pm" as const,
			key: source.key,
			role: "pm" as const,
			claimId: source.claimId,
			taskKey: source.taskKey,
		};
		const authorization = this.authorizationFor("source-read", {
			identity,
			matter_identity: source.matterRef,
			matter_ref: source.matterRef,
			matter_version: MATTER_VERSION,
			material_digest: "read",
			basis_digest: "read",
		});
		if (authorization === undefined) return fail("dispatch binding drift", ["host.authorization"]);
		const authority = readRuntimeAuthority({
			agenticdocRoot: this.root,
			key: source.key,
			source: "pm",
			taskKey: source.taskKey,
			clockMs: this.clock(),
			authorization,
		});
		if (!authority.ok) return authority;
		if (authority.value.stopSignals.length > 0) return fail("trusted stop", ["trusted-stop"]);
		const snapshot = this.controllers.budget.snapshot(this.binding(source));
		const preflight = this.controllers.budget.preflight({
			...this.binding(source),
			call_id: "source-read",
			max_cost: 1,
			cost_unit: source.costUnit,
		});
		if (!snapshot.ok) return fail("existing dispatch budget unavailable", [snapshot.code]);
		if (!preflight.ok) return fail("existing dispatch budget unavailable", [preflight.code]);
		// A source read is a currentness/VALIDITY read: it reserves nothing and
		// returns no permission to act. It is admitted either with a still-free
		// unit, or — for evidence-only correlation/archival — when the ONLY
		// accepted exhaustion is the exact terminal one: the last authorized
		// unit was consumed by the observed action and nothing is held or in
		// flight. A plain hold (including the request's own reservation), an
		// overrun, a no-progress stop or a passed deadline keeps its refusal.
		const terminalEvidenceRead =
			!preflight.value.granted &&
			preflight.value.reason === "budget-exhausted" &&
			exactTerminalExhaustion(snapshot.value, source, this.clock());
		if (!preflight.value.granted && !terminalEvidenceRead)
			return fail("existing dispatch budget unavailable", ["budget-exhausted"]);
		return {
			ok: true,
			value: {
				identity,
				matterRef: source.matterRef,
				signature: JSON.stringify([
					source.key,
					source.claimId,
					source.taskKey,
					source.executionRunId,
					source.cardPath,
					source.sourcePin,
					source.budgetStartedAt,
					source.authorizationUnit,
					source.bindingVersion,
				]),
			},
		};
	}

	readContinuationFacts(input: RuntimeHostContinuationInput): { stop_signals: StopSignal[]; gaps: string[] } {
		const facts = readRuntimeStopFacts({
			agenticdocRoot: input.agenticdocRoot,
			key: input.key,
			taskKey: input.taskKey,
			runId: input.runId,
			clockMs: this.clock(),
		});
		if (facts.stop_signals.length > 0) return { stop_signals: facts.stop_signals, gaps: [] };
		if (facts.gaps.length > 0) return facts;
		const source = this.sourcesByTask.get(input.taskKey);
		if (!source || this.activeLocalRef !== input.localRef || this.observationFailed)
			return {
				stop_signals: [],
				gaps: this.observationFailed ? ["session-observation-unknown"] : ["host.authorization"],
			};
		const snapshot = this.controllers?.budget.snapshot(this.binding(source));
		if (!snapshot?.ok) return { stop_signals: [], gaps: [snapshot?.code ?? "budget-not-open"] };
		if (snapshot.value.blocked) return { stop_signals: [], gaps: [snapshot.value.blocked] };
		return { stop_signals: [], gaps: [] };
	}

	reserveDispatchedChild(
		key: string,
		task: string,
		pin: string,
		parent: string,
		budget: MatterBudgetV1,
		reservationId = `fixed:${JSON.stringify([key, task, pin])}`,
	): string {
		const source = this.sourcesByUnit.get(parent);
		if (
			!source ||
			source.key !== key ||
			source.source !== "pm" ||
			this.controlBlocked ||
			this.shutdownClosed ||
			this.observationFailed ||
			this.historyFailed
		)
			return "parent-budget-unavailable";
		const row = readKeyRows(this.root, key);
		if (!row.ok || row.value.claimId !== source.claimId) return "parent-claim-drift";
		if (source.stage !== undefined) {
			const stop = this.stageStop(source);
			if (stop.gaps.length || stop.stop_signals.length) return "parent-stage-unavailable";
		}
		const result = this.reserveChild({
			taskKey: source.taskKey,
			reservationId,
			steps: budget.max_steps - budget.steps_consumed,
			cost: budget.remaining_cost,
			deadline: budget.deadline,
		});
		return result.ok ? "" : result.reason;
	}

	reserveDeadlineSuccessor(
		key: string,
		task: string,
		pin: string,
		parent: string,
		budget: MatterBudgetV1,
		claim: string,
		envelope: string,
	) {
		const direction = this.stageDirection;
		const channelInput = this.stageChannel;
		const parentSource = this.sourcesByUnit.get(parent);
		const sessionFile = this.session?.read().file;
		if (
			!direction ||
			!channelInput ||
			!sessionFile ||
			!fs.existsSync(sessionFile) ||
			!this.stageIdentity() ||
			direction.key !== key ||
			direction.claim_id !== claim ||
			parentSource?.stage?.eventId !== direction.event_id ||
			this.clock() >= Date.parse(budget.deadline)
		) {
			return { ok: false as const, reason: "deadline successor requires the live, durable PM stage budget" };
		}
		const head = parseHead(envelope);
		if (!head.ok || writeFaceOf(head.value).some((target) => !direction.write_face.includes(target))) {
			return { ok: false as const, reason: "deadline successor write scope exceeds the authorized PM stage" };
		}
		const channel = new PmChannel(channelInput.projectDir, channelInput.home);
		const request = readBytes(channel.dir, path.join(channel.dir, direction.request_ref));
		if (!request.ok) return { ok: false as const, reason: request.reason };
		const reason = this.reserveDispatchedChild(
			key,
			task,
			pin,
			parent,
			budget,
			`deadline:${JSON.stringify([key, pin])}`,
		);
		if (reason) return { ok: false as const, reason };
		return {
			ok: true as const,
			authority: {
				channel: channel.dir,
				request: direction.request_ref,
				request_sha256: crypto.createHash("sha256").update(request.value).digest("hex"),
				receipt: direction.receipt_ref,
				session: sessionFile,
				session_id: direction.session_id,
				event_id: direction.event_id,
				grant_digest: direction.grant_digest,
				unit: parentSource.authorizationUnit,
				stage_card: direction.card_path,
				stage_pin: direction.card_sha256,
			},
		};
	}

	reserveChild(request: {
		taskKey: string;
		reservationId: string;
		steps: number;
		cost: number;
		deadline: string;
	}): RuntimeFactRead<{ status: string }> {
		const source = this.sourcesByTask.get(request.taskKey);
		if (!source || !this.controllers) return { ok: false, gaps: ["host.authorization"], reason: "unit not open" };
		const child = {
			...this.binding(source),
			reservation_id: request.reservationId,
			steps: request.steps,
			cost: request.cost,
			cost_unit: source.costUnit,
			deadline: request.deadline,
		};
		const result = this.controllers.budget.reserveChild(child);
		if (!result.ok) {
			if (result.code === "insufficient-remaining" || result.gap.includes("insufficient"))
				this.counts.childBlockedInsufficient += 1;
			return { ok: false, gaps: [result.code], reason: result.gap };
		}
		if (result.value.status === "duplicate") return { ok: true, value: { status: result.value.status } };
		const event = { kind: "reserve-child" as const, at: this.clock(), request: child };
		if (!this.appendEvent(source, event))
			return { ok: false, gaps: ["session-observation-unknown"], reason: "reservation observation failed" };
		this.counts.childReserves += 1;
		return { ok: true, value: { status: result.value.status } };
	}

	settleChild(taskKey: string, reservationId: string, terminalRef: string): RuntimeFactRead<{ status: string }> {
		if (reservationId.startsWith("fixed:"))
			return { ok: false, gaps: ["fixed-allocation"], reason: "fixed child allocation is nonrefundable" };
		const source = this.sourcesByTask.get(taskKey);
		if (!source || !this.controllers || !this.observedResults.has(terminalRef))
			return { ok: false, gaps: ["terminal-result"], reason: "no real terminal result" };
		const request = { ...this.binding(source), reservation_id: reservationId };
		const result = this.controllers.budget.settle(request);
		if (!result.ok) return { ok: false, gaps: [result.code], reason: result.gap };
		const event = { kind: "settle" as const, at: this.clock(), request };
		if (!this.appendEvent(source, event))
			return { ok: false, gaps: ["session-observation-unknown"], reason: "settlement observation failed" };
		if (result.value.status !== "duplicate") this.counts.childSettles += 1;
		return { ok: true, value: { status: result.value.status } };
	}

	/** Capture ONE terminal proof only after the real final action's budget
	 *  observation, session event and host evidence are all present. This does
	 *  not reserve, grant, replay or execute anything. */
	private captureTerminalArchival(pending: PendingCall, callId: string, resultRef: string): void {
		if (
			this.terminalArchival !== undefined ||
			this.controlBlocked ||
			this.shutdownClosed ||
			this.observationFailed ||
			this.historyFailed !== undefined
		)
			return;
		const source = pending.source;
		if (source.source !== this.activeSource || pending.localRef !== this.activeLocalRef) return;
		const expected = this.expectedFor?.(pending.localRef);
		if (expected === undefined || !nonblank(expected.matter_ref)) return;
		const at = this.clock();
		const snapshot = this.controllers?.budget.snapshot(this.binding(source));
		if (!snapshot?.ok || !exactTerminalExhaustion(snapshot.value, source, at)) return;
		const preflight = this.controllers?.budget.preflight({
			...this.binding(source),
			call_id: `terminal-probe:${callId}`,
			max_cost: 1,
			cost_unit: source.costUnit,
		});
		if (!preflight?.ok || preflight.value.granted || preflight.value.reason !== "budget-exhausted") return;
		const history = this.historyFor(source);
		if (!history.ok) return;
		const reserves = history.value.events.filter(
			(event) => event.kind === "reserve" && event.request.call_id === callId,
		);
		const observations = history.value.events.filter(
			(event) =>
				event.kind === "observe" && event.request.call_id === callId && event.request.result_ref === resultRef,
		);
		const reserve = reserves[0];
		const observe = observations[0];
		if (
			reserves.length !== 1 ||
			observations.length !== 1 ||
			reserve?.kind !== "reserve" ||
			observe?.kind !== "observe"
		)
			return;
		if (observe.request.outcome !== "success" || observe.request.actual_cost !== 1) return;
		const beforeDigest = terminalEvidenceDigest(reserve.evidence);
		const afterDigest = terminalEvidenceDigest(observe.evidence);
		if (beforeDigest === undefined || afterDigest === undefined || beforeDigest === afterDigest) return;
		const proof: ExecutedActionTerminalProof = Object.freeze({
			kind: "executed-action-terminal" as const,
			source: source.source,
			key: source.key,
			role: source.role,
			claim_id: source.claimId,
			task_key: source.taskKey,
			run_id: source.executionRunId,
			card_path: source.cardPath,
			card_sha256: source.sourcePin,
			budget_started_at: source.budgetStartedAt,
			authorization_unit: source.authorizationUnit,
			budget_ref: source.parentBudgetRef,
			matter_ref: expected.matter_ref,
			local_ref: pending.localRef,
			action_ref: callId,
			result_ref: resultRef,
			disposition_ref: `disposition:${callId}`,
			executor: runtimeExecutionExecutor(source.executionRunId, callId),
			observed_effect: `byte-manifest:${beforeDigest}->${afterDigest};business-correctness=unverified`,
			before_digest: beforeDigest,
			after_digest: afterDigest,
			reservation_ref: `${history.value.origin_ref}#reserve:${callId}`,
			observation_ref: `${history.value.through_ref}#observe:${resultRef}`,
			exhaustion_code: "budget-exhausted" as const,
			preflight_reason: "budget-exhausted" as const,
			available_steps: snapshot.value.available_steps,
			available_cost: snapshot.value.available_cost,
			held_steps: snapshot.value.held_steps,
			held_cost: snapshot.value.held_cost,
			in_flight: snapshot.value.in_flight,
			steps_consumed: snapshot.value.budget.steps_consumed,
			max_steps: snapshot.value.budget.max_steps,
			cost_consumed: snapshot.value.budget.cost_consumed,
			remaining_cost: snapshot.value.budget.remaining_cost,
			no_progress_count: snapshot.value.budget.no_progress_count,
			no_progress_limit: snapshot.value.budget.no_progress_limit,
			deadline: snapshot.value.budget.deadline,
		});
		const record: TerminalArchivalRecord = { proof, archiveStarted: false, archived: false };
		this.terminalArchival = record;
		const validationRequest: TrustedContextRequest = {
			key: source.key,
			source: source.source,
			ref: pending.localRef,
			task_key: source.taskKey,
			run_id: source.runId,
			write_kind: "execution",
		};
		if (this.terminalArchivalFor(validationRequest) === undefined) this.terminalArchival = undefined;
	}

	/** Re-read the live source, stop, authority, current snapshot and exact
	 *  action join on EVERY terminal use. A second archive or a foreign ref is
	 *  refused; there is no blanket zero-budget exemption. */
	private terminalArchivalFor(
		request: TrustedContextRequest,
		authorization?: RuntimeHostAuthorization,
	): ExecutedActionTerminalProof | undefined {
		const record = this.terminalArchival;
		if (
			record === undefined ||
			record.archived ||
			this.controlBlocked ||
			this.shutdownClosed ||
			this.observationFailed ||
			this.historyFailed !== undefined ||
			(request.write_kind !== "execution" && request.write_kind !== "disposition")
		)
			return undefined;
		const proof = record.proof;
		const source = this.activeSourceFor();
		if (
			source === undefined ||
			this.activeLocalRef !== proof.local_ref ||
			source.source !== request.source ||
			source.key !== request.key ||
			source.source !== proof.source ||
			source.key !== proof.key ||
			source.role !== proof.role ||
			source.claimId !== proof.claim_id ||
			source.taskKey !== proof.task_key ||
			source.executionRunId !== proof.run_id ||
			source.cardPath !== proof.card_path ||
			source.sourcePin !== proof.card_sha256 ||
			source.budgetStartedAt !== proof.budget_started_at ||
			source.authorizationUnit !== proof.authorization_unit ||
			source.parentBudgetRef !== proof.budget_ref ||
			(request.task_key !== undefined && request.task_key !== source.taskKey) ||
			(request.run_id !== undefined && request.run_id !== (source.runId ?? source.executionRunId)) ||
			!this.observedResults.has(proof.result_ref) ||
			this.settledUnknown.has(proof.action_ref)
		)
			return undefined;
		const expectedRef = request.write_kind === "disposition" ? proof.disposition_ref : proof.local_ref;
		if (request.ref !== expectedRef) return undefined;
		const expected = this.expectedFor?.(proof.local_ref);
		if (expected === undefined || expected.matter_ref !== proof.matter_ref) return undefined;
		if (
			authorization !== undefined &&
			(authorization.key !== proof.key ||
				authorization.source !== proof.source ||
				authorization.role !== proof.role ||
				authorization.owningPmClaim !== proof.claim_id ||
				authorization.taskKey !== source.taskKey ||
				(authorization.runId ?? undefined) !== (source.runId ?? undefined) ||
				authorization.cardPath !== proof.card_path ||
				authorization.cardSha256 !== proof.card_sha256 ||
				authorization.budgetStartedAt !== proof.budget_started_at ||
				authorization.authorizationUnit !== proof.authorization_unit)
		)
			return undefined;
		if (this.readBinding() === undefined) return undefined;
		if (source.source === "worker-local") {
			if (source.runId === undefined) return undefined;
			const stop = readRuntimeStopFacts({
				agenticdocRoot: this.root,
				key: source.key,
				taskKey: source.taskKey,
				runId: source.runId,
				clockMs: this.clock(),
			});
			if (stop.stop_signals.length > 0 || stop.gaps.length > 0) return undefined;
		}
		const snapshot = this.controllers?.budget.snapshot(this.binding(source));
		if (!snapshot?.ok || !exactTerminalExhaustion(snapshot.value, source, this.clock())) return undefined;
		return proof;
	}

	beforeToolCall(event: ToolCallEvent): ToolCallEventResult | undefined {
		// These tools cannot spend the controlled write allowance. Leave their
		// normal read-scope/role guards in charge even when this runtime failed.
		if (["read", "ls", "find", "grep"].includes(event.toolName)) return undefined;
		if (this.committingSource !== undefined) {
			this.counts.blocks += 1;
			return { block: true, reason: "selection-in-flight" };
		}
		if (this.activeLocalRef === undefined) {
			if (this.selectionAttempted && ["write", "edit", "bash"].includes(event.toolName)) {
				this.counts.blocks += 1;
				return { block: true, reason: "selection-unproven" };
			}
			return undefined;
		}
		const source = this.activeSourceFor();
		if (source === undefined || this.observationFailed || this.controlBlocked || this.historyFailed !== undefined) {
			this.counts.blocks += 1;
			return {
				block: true,
				reason: this.historyFailed ?? (this.controlBlocked ? "host-stop-or-error" : "host-authorization-missing"),
			};
		}
		if (event.toolName === "bash") {
			this.counts.blocks += 1;
			return { block: true, reason: "unbounded-command-target-policy" };
		}
		if (event.toolName === "edit") {
			this.counts.blocks += 1;
			return { block: true, reason: "unsupported-controlled-tool" };
		}
		if (event.toolName !== "write") return undefined;
		if (this.expectedFor?.(this.activeLocalRef) === undefined) {
			this.counts.blocks += 1;
			return { block: true, reason: "offer-source-not-current" };
		}
		if (!isToolCallEventType("write", event)) {
			this.counts.blocks += 1;
			return { block: true, reason: "unsupported-tool-shape" };
		}
		const target = canonicalRelative(this.projectRoot, event.input.path);
		if (target === undefined || !source.writeFace.includes(target)) {
			this.counts.blocks += 1;
			return { block: true, reason: "target-outside-complete-write-face" };
		}
		const stop =
			source.source === "worker-local"
				? readRuntimeStopFacts({
						agenticdocRoot: this.root,
						key: source.key,
						taskKey: source.taskKey,
						runId: source.executionRunId,
						clockMs: this.clock(),
					})
				: source.stage !== undefined
					? this.stageStop(source)
					: { stop_signals: [] as StopSignal[], gaps: [] as string[] };
		if (stop.stop_signals.length > 0 || stop.gaps.length > 0) {
			this.controlBlocked = stop.stop_signals.length > 0;
			this.counts.blocks += 1;
			return { block: true, reason: stop.stop_signals.length > 0 ? "host-stop" : stop.gaps.join(";") };
		}
		const action = { ...this.binding(source), call_id: event.toolCallId, max_cost: 1, cost_unit: source.costUnit };
		const preflight = this.controllers?.budget.preflight(action);
		if (!preflight?.ok || !preflight.value.granted) {
			this.counts.blocks += 1;
			return { block: true, reason: preflight?.ok ? "budget-exhausted" : (preflight?.code ?? "budget-not-open") };
		}
		const evidence = this.evidence(source);
		const call: RuntimeToolCall = {
			source: source.source,
			local_ref: this.activeLocalRef,
			toolCallId: event.toolCallId,
			tool: "write",
		};
		// Pre-body ADMISSION runs BEFORE any allowance is reserved: the real
		// run/toolCallId authorization revalidates the fresh offer/source/parent.
		// A refusal here is a KNOWN no-effect veto, so it must not create, spend,
		// refund or release a reservation, and it never settles an unknown. Its
		// own call leaves no hold; every other call's accounting is untouched.
		// The reservation below still exists before the tool body (and before
		// pendingCalls.set), so no action can execute unreserved.
		const observed = this.controllers?.execution.observeToolCall(call);
		if (observed?.code !== "call-observed") {
			this.counts.vetoes += 1;
			this.counts.blocks += 1;
			return { block: true, reason: observed?.code ?? "execution-observation-missing" };
		}
		const reserveEvent = { kind: "reserve" as const, at: this.clock(), request: action, evidence };
		if (!this.appendEvent(source, reserveEvent)) {
			this.counts.blocks += 1;
			return { block: true, reason: "session-observation-unknown" };
		}
		const reserved = this.controllers?.budget.reserve(action);
		if (!reserved?.ok || !reserved.value.execute) {
			// Nothing was reserved by this call (its own reservation attempt failed)
			// and the observed-but-unreserved action can never verify or append.
			this.counts.vetoes += 1;
			this.counts.blocks += 1;
			return { block: true, reason: reserved?.ok ? "duplicate-call" : (reserved?.code ?? "reserve-failed") };
		}
		this.pendingCalls.set(event.toolCallId, {
			localRef: this.activeLocalRef,
			callId: event.toolCallId,
			source,
			terminalRefs: new Set(),
		});
		this.counts.reserves += 1;
		return undefined;
	}

	async afterToolResult(event: ToolResultEvent): Promise<void> {
		const pending = this.pendingCalls.get(event.toolCallId);
		if (pending === undefined) return;
		this.pendingCalls.delete(event.toolCallId);
		const details = isRecord(event.details) ? event.details : undefined;
		const unknown = event.isError || details?.completion === "unknown";
		const resultRef = `tool_result:${event.toolCallId}`;
		this.observedResults.add(resultRef);
		const outcome = event.isError ? "error" : unknown ? "unknown" : "success";
		const observation = {
			...this.binding(pending.source),
			call_id: event.toolCallId,
			result_ref: resultRef,
			outcome,
			actual_cost: 1,
			cost_unit: pending.source.costUnit,
		} as const;
		const evidence = this.evidence(pending.source);
		const observeEvent = { kind: "observe" as const, at: this.clock(), request: observation, evidence };
		const observed = unknown
			? this.controllers?.budget.settleUnknown(this.binding(pending.source), event.toolCallId, resultRef)
			: this.controllers?.budget.observe(observation);
		const appendOk = this.appendEvent(pending.source, observeEvent);
		if (!unknown && !event.isError && appendOk && observed?.ok && observed.value.status === "observed")
			this.captureTerminalArchival(pending, event.toolCallId, resultRef);
		const result: RuntimeToolResult = {
			toolCallId: event.toolCallId,
			local_ref: pending.localRef,
			run_id: pending.source.executionRunId,
			executor: runtimeExecutionExecutor(pending.source.executionRunId, event.toolCallId),
			result_ref: resultRef,
			isError: event.isError,
			completion: unknown ? "unknown" : "complete",
		};
		// Host-owned observation of a REAL tool_call/tool_result pair. It is not
		// copied from tool result details and cannot be forged by a byte proof.
		this.observedToolResults.set(event.toolCallId, {
			tool_call_id: event.toolCallId,
			local_ref: pending.localRef,
			result_ref: resultRef,
			executor: result.executor,
			run_id: result.run_id,
			is_error: event.isError,
			completion: result.completion,
			...(pending.source.stage !== undefined && evidence.length === 1 && evidence[0] !== undefined
				? { target: evidence[0] }
				: {}),
		});
		const dResult = this.controllers?.execution.observeToolResult(result);
		if (unknown) this.counts.unknowns += 1;
		if (!appendOk || !observed?.ok || dResult?.code !== "result-observed") {
			this.controlBlocked = true;
			this.counts.blocks += 1;
			return;
		}
		this.counts.observes += 1;
		if (event.isError || unknown) this.controlBlocked = true;
		await this.finish(event.toolCallId);
		this.setCurrentReviewer(undefined);
		this.recordLocalQg(pending.source, pending.localRef, event.toolCallId);
	}

	private recordLocalQg(source: RegisteredSource, localRef: string, actionToolCallId: string): void {
		if (!source.stage) return;
		const disposition = this.evaluateLocalQg({ localRef, actionToolCallId });
		const id = crypto.randomUUID();
		try {
			this.session?.append("mw-local-qg-result-v1", {
				id,
				at: this.clock(),
				event_id: source.stage.eventId,
				stage_id: source.stage.stageId,
				matter_ref: source.stage.matterRef,
				grant_digest: source.stage.grantDigest,
				run_id: source.executionRunId,
				local_ref: localRef,
				tool_call_id: actionToolCallId,
				review_source:
					this.currentReviewer === undefined || disposition.verdict === "insufficient"
						? "missing-independent-current-stage-review"
						: `production-review-run:${this.currentReviewer.runId}`,
				disposition,
			});
			if (!this.session?.read().entries.some((entry) => isRecord(entry.data) && entry.data.id === id))
				this.observationFailed = true;
		} catch {
			this.observationFailed = true;
		}
	}

	settleUnknown(): void {
		for (const callId of [...this.pendingCalls.keys()]) this.settleUnknownCall(callId);
	}

	private async commitSelection(request: CommitSelectionRequest): Promise<RuntimeExecutionResult> {
		if (!this.controllers) throw new Error("runtime host store is not composed");
		this.selectionAttempted = true;
		// The store needs the candidate source to validate its binding, but a
		// refused/thrown/duplicate submit must not replace the active selection.
		const source = [...this.sourcesByUnit.values()].find(
			(item) =>
				item.key === this.frozenKey &&
				item.source === request.source &&
				item.taskKey === request.task_key &&
				(request.run_id === undefined || item.runId === request.run_id),
		);
		const previousSource = this.committingSource;
		this.committingSource = source;
		try {
			const result = await this.controllers.execution.commitSelection(request);
			// R10: a semantically identical re-submit is classified by the frozen
			// store as an idempotent `duplicate` (no second selection write). It is a
			// planned-fact read, NOT a new selection commit or business replay, so it
			// must not be counted as a fresh selectionCommits. Only a real `written`
			// selection binds the active local_ref/source/matter and increments.
			const duplicate = result.code === "reconciliation-required" || result.store_result?.code === "duplicate";
			if (duplicate) this.counts.duplicateNoReplay += 1;
			if (result.code === "selection-bound" && !duplicate && source !== undefined) {
				this.counts.selectionCommits += 1;
				this.lastLocalRef = request.local_ref;
				this.activeLocalRef = request.local_ref;
				this.activeSource = request.source;
				this.activeMatterRef = source.authorizationUnit;
			}
			return result;
		} finally {
			this.committingSource = previousSource;
		}
	}

	private async finish(toolCallId: string): Promise<void> {
		this.lastToolCallId = toolCallId;
		const dispositionRef = `disposition:${toolCallId}`;
		// R1 ref join: bind this real action's disposition ref to the EXACT offer
		// local_ref that authorized it (activeLocalRef was set from the verified
		// commit for this very selection). Only this authentic join is registered;
		// a synthetic/unregistered ref cannot be resolved to an offer.
		if (this.activeLocalRef !== undefined) this.dispositionRefToLocalRef.set(dispositionRef, this.activeLocalRef);
		this.lastDispositionRef = dispositionRef;
		const terminal = this.terminalArchival?.proof.action_ref === toolCallId ? this.terminalArchival : undefined;
		if (terminal !== undefined) {
			if (terminal.archiveStarted || terminal.archived) return;
			terminal.archiveStarted = true;
		}
		try {
			const appended = await this.controllers?.execution.appendExecution(toolCallId);
			if (appended?.store_result?.ok) this.counts.appends += 1;
			const saved = await this.controllers?.execution.saveDisposition(toolCallId, dispositionRef);
			if (saved?.store_result?.ok) this.counts.dispositions += 1;
		} finally {
			// One terminal record may be attempted only once. A failed or thrown
			// archive is read-only reconciliation, never a replay or a retry.
			if (terminal !== undefined) terminal.archived = true;
		}
	}

	private settleUnknownCall(callId: string): void {
		if (this.settledUnknown.has(callId)) return;
		this.settledUnknown.add(callId);
		const pending = this.pendingCalls.get(callId);
		if (!pending) return;
		this.pendingCalls.delete(callId);
		const resultRef = `unknown_result:${callId}`;
		this.observedResults.add(resultRef);
		const request = {
			...this.binding(pending.source),
			call_id: callId,
			result_ref: resultRef,
			outcome: "unknown" as const,
			actual_cost: 1,
			cost_unit: pending.source.costUnit,
		};
		this.appendEvent(pending.source, { kind: "observe", at: this.clock(), request, evidence: [] });
		this.controllers?.budget.settleUnknown(this.binding(pending.source), callId, resultRef);
		this.controllers?.execution.observeToolResult({
			toolCallId: callId,
			local_ref: pending.localRef,
			run_id: pending.source.executionRunId,
			executor: runtimeExecutionExecutor(pending.source.executionRunId, callId),
			result_ref: resultRef,
			isError: false,
			completion: "unknown",
		});
		this.counts.unknowns += 1;
		this.controlBlocked = true;
	}

	private activeSourceFor(): RegisteredSource | undefined {
		if (this.activeMatterRef === undefined) return undefined;
		const source = this.sourcesByUnit.get(this.activeMatterRef);
		return source?.source === this.activeSource ? source : undefined;
	}

	private binding(source: RegisteredSource): RuntimeBudgetBinding {
		return {
			authorization_unit: source.authorizationUnit,
			parent_budget_ref: source.parentBudgetRef,
			matter_ref: source.authorizationUnit,
		};
	}

	private registerSource(input: {
		key: string;
		source: LocalSource;
		role: HostRole;
		claimId?: string;
		taskKey: string;
		runId?: string;
		executionRunId: string;
		cardPath: string;
		sourcePin: string;
		budgetStartedAt: string;
		writeFace: string[];
		stage?: RegisteredPmStage;
		stageRef?: string;
	}): RuntimeFactRead<RegisteredSource> {
		if (this.frozenKey !== undefined && this.frozenKey !== input.key)
			return { ok: false, gaps: ["key"], reason: "one window cannot own two frozen stores" };
		if (keyNameRefusal(input.key) !== null || !input.taskKey.trim() || input.writeFace.length === 0)
			return { ok: false, gaps: ["key", "task_key", "write_face"], reason: "incomplete exact host source" };
		const row = readKeyRows(this.root, input.key);
		if (!row.ok) return row;
		const claimId = input.claimId ?? row.value.claimId;
		if (claimId !== row.value.claimId)
			return { ok: false, gaps: ["index.claim"], reason: "dispatch claim does not match live index" };
		const cardFile = path.join(this.root, input.key, input.cardPath);
		const card = readBytes(this.root, cardFile);
		if (!card.ok) return card;
		const actualPin = sha256EolNormalizedBytes(card.value);
		if (actualPin !== input.sourcePin)
			return { ok: false, gaps: ["card_sha256"], reason: "pinned card bytes drifted" };
		const runRef =
			input.stageRef ??
			(input.source === "worker-local" ? `workers/${input.taskKey}/run.json` : `_workers.parallel#${input.taskKey}`);
		const parsed = buildMatterBudgetFromCard(card.value.toString("utf8"), {
			cardRef: input.cardPath,
			cardSha256: actualPin,
			runStartedAt: input.budgetStartedAt,
			runRef,
			indexRef: "_index.parallel",
		});
		if (!parsed.ok) return parsed;
		const cardBudget = parsed.value.budget;
		const existing = this.sourcesByUnit.get(cardBudget.matter_ref);
		if (existing !== undefined) {
			if (
				(existing.stage === undefined) !== (input.stage === undefined) ||
				(existing.stage !== undefined &&
					input.stage !== undefined &&
					(existing.stage.eventId !== input.stage.eventId ||
						existing.stage.grantDigest !== input.stage.grantDigest ||
						existing.stage.scopeRef !== input.stage.scopeRef ||
						existing.stage.matterRef !== input.stage.matterRef ||
						existing.stage.deadline !== input.stage.deadline))
			)
				return {
					ok: false,
					gaps: ["stage-lifecycle-replay"],
					reason: "same matter cannot mint a second stage grant or reset counters",
				};
			if (
				existing.sourcePin !== actualPin ||
				existing.budgetStartedAt !== input.budgetStartedAt ||
				existing.claimId !== claimId ||
				existing.key !== input.key
			) {
				this.counts.newCardTurnRefreshes += 1;
				return {
					ok: false,
					gaps: ["source_pin", "started_at", "index.claim"],
					reason: "new card/run cannot refresh an authorization unit",
				};
			}
			return { ok: true, value: existing };
		}
		const authorization: RuntimeHostAuthorization = {
			localRef: "unbound",
			key: input.key,
			source: input.source,
			role: input.role,
			owningPmClaim: claimId,
			...(input.taskKey === undefined ? {} : { taskKey: input.taskKey }),
			...(input.runId === undefined ? {} : { runId: input.runId }),
			cardPath: input.cardPath,
			cardSha256: actualPin,
			budgetStartedAt: input.budgetStartedAt,
			authorizationUnit: cardBudget.matter_ref,
			matterRef: cardBudget.matter_ref,
			...(input.stageRef === undefined ? {} : { stageRef: input.stageRef }),
		};
		const authority = readRuntimeAuthority({
			agenticdocRoot: this.root,
			key: input.key,
			source: input.source,
			...(input.taskKey === undefined ? {} : { taskKey: input.taskKey }),
			...(input.runId === undefined ? {} : { runId: input.runId }),
			clockMs: this.clock(),
			authorization,
		});
		if (!authority.ok) return authority;
		const source: RegisteredSource = {
			key: input.key,
			source: input.source,
			role: authority.value.role,
			claimId,
			taskKey: input.taskKey,
			...(input.runId === undefined ? {} : { runId: input.runId }),
			executionRunId: input.executionRunId,
			cardPath: input.cardPath,
			sourcePin: actualPin,
			budgetStartedAt: input.budgetStartedAt,
			authorizationUnit: cardBudget.matter_ref,
			parentBudgetRef: cardBudget.budget_ref,
			matterRef: cardBudget.matter_ref,
			costUnit: "1 cost unit ≡ 1 tool call",
			writeFace: [...input.writeFace].sort(),
			initial: {
				...cardBudget,
				steps_consumed: 0,
				cost_consumed: 0,
				no_progress_count: 0,
			},
			cardBudget,
			bindingVersion: authority.value.bindingVersion,
			...(input.stage === undefined ? {} : { stage: input.stage }),
		};
		this.frozenKey = input.key;
		this.sourcesByTask.set(input.taskKey, source);
		this.sourcesByUnit.set(source.authorizationUnit, source);
		this.counts.registered += 1;
		this.ensureControllers();
		if (this.session !== undefined) this.attachSource(source);
		return { ok: true, value: source };
	}

	private ensureControllers(): void {
		if (this.controllers !== undefined || this.frozenKey === undefined) return;
		const adapter = createRuntimeHostAdapter({
			agenticdocRoot: this.root,
			// R1 ref join: a disposition_ref is not an offer local_ref. Resolve it
			// ONLY through the authentic association registered at finish() for
			// the real finishing action, then look up the genuine offer. An
			// unregistered/forged ref stays unresolved and fails closed.
			expectedFor: (ref) => this.expectedFor?.(this.dispositionRefToLocalRef.get(ref) ?? ref),
			authorizationFor: (localRef, expected) => this.authorizationFor(localRef, expected),
			budgetSnapshotFor: (input) => this.budgetSnapshotFor(input),
			verifyExecution: async (request) => this.controllers?.execution.verifyExecution(request),
			clock: this.clock,
		});
		const store = new LocalSelectionStore({
			agenticdoc_root: this.root,
			key: this.frozenKey,
			host_adapter: adapter,
			clock: this.clock,
		});
		const execution = new RuntimeExecutionController({
			store,
			project_root: this.projectRoot,
			readBinding: () => this.readBinding(),
			readAuthorization: (selection, call) => this.readTargetAuthorization(selection, call),
			readDisposition: (context) => this.readDisposition(context),
			clock: this.clock,
		});
		const budget = createRuntimeBudgetController({
			clock: this.clock,
			readAuthorization: (binding) => this.readBudgetAuthorization(binding),
			captureEvidence: (binding) => this.captureEvidence(binding),
		});
		this.controllers = { store, execution, budget };
	}

	private authorizationFor(localRef: string, expected: RuntimeOfferExpected): RuntimeHostAuthorization | undefined {
		const identity = expected.identity;
		const taskKey = identity?.taskKey;
		if (!nonblank(localRef) || identity === undefined || !nonblank(taskKey) || !nonblank(expected.matter_identity))
			return undefined;
		const source = this.sourcesByTask.get(taskKey);
		if (!source || source.key !== identity.key || source.source !== identity.source || source.role !== identity.role)
			return undefined;
		if ((source.runId ?? undefined) !== (identity.runId ?? undefined)) return undefined;
		if (source.source === "pm" && identity.claimId !== source.claimId) return undefined;
		if (source.source === "worker-local" && identity.owner !== source.key) return undefined;
		if (source.stage !== undefined) {
			const stage = this.stageIdentity();
			if (
				stage === undefined ||
				stage.stageId !== source.stage.stageId ||
				stage.scopeRef !== source.stage.scopeRef ||
				stage.matterRef !== source.stage.matterRef ||
				stage.grantDigest !== source.stage.grantDigest ||
				identity.stageId !== stage.stageId ||
				identity.scopeRef !== stage.scopeRef ||
				expected.stage_matter_ref !== stage.matterRef ||
				expected.matter_identity !== expected.matter_identity?.trim()
			)
				return undefined;
		}
		return {
			localRef,
			key: source.key,
			source: source.source,
			role: source.role,
			owningPmClaim: source.claimId,
			taskKey: source.taskKey,
			...(source.runId === undefined ? {} : { runId: source.runId }),
			cardPath: source.cardPath,
			cardSha256: source.sourcePin,
			budgetStartedAt: source.budgetStartedAt,
			authorizationUnit: source.authorizationUnit,
			matterRef: expected.matter_identity,
		};
	}

	authorizationGapsFor(expected: RuntimeOfferExpected): string[] {
		const identity = expected.identity;
		if (this.stageRefusal !== undefined && this.stageDirection === undefined) return [...this.stageRefusal.gaps];
		if (expected.stage_matter_ref !== undefined && this.stageDirection === undefined)
			return ["host.pm-stage-source-missing"];
		if (!identity?.taskKey?.trim()) return ["host.pm-task-attachment-missing"];
		if (!this.sourcesByTask.has(identity.taskKey)) return ["host.registered-dispatch-pin-missing"];
		if (this.authorizationFor("gap-probe", expected) === undefined) return ["host.authorization-binding-drift"];
		return [];
	}

	private budgetSnapshotFor(input: RuntimeBudgetSnapshotRequest): RuntimeFactRead<RuntimeBudgetSnapshot> {
		const source = this.sourcesByUnit.get(input.authorization.authorizationUnit);
		if (!source || !this.controllers || this.observationFailed || this.historyFailed !== undefined)
			return {
				ok: false,
				gaps: ["host.authorization", "history"],
				reason: this.historyFailed ?? "runtime host not composed",
			};
		const history = this.historyFor(source);
		if (!history.ok) return { ok: false, gaps: history.gaps, reason: history.reason };
		const binding = this.binding(source);
		const snapshot = this.controllers.budget.snapshot(binding);
		const preflight = this.controllers.budget.preflight({
			...binding,
			call_id: `submit:${input.authorization.localRef}`,
			max_cost: 1,
			cost_unit: source.costUnit,
		});
		const archivalIntent = input.request.write_kind === "execution" || input.request.write_kind === "disposition";
		const exactExhausted = snapshot.ok && exactTerminalExhaustion(snapshot.value, source, input.nowMs);
		const deniedForTerminal =
			preflight.ok && !preflight.value.granted && preflight.value.reason === "budget-exhausted";
		const terminalIntent =
			archivalIntent &&
			((snapshot.ok && snapshot.value.blocked !== null) || (preflight.ok && !preflight.value.granted));
		const terminalProof = terminalIntent ? this.terminalArchivalFor(input.request, input.authorization) : undefined;
		if (terminalIntent && (terminalProof === undefined || !exactExhausted || !deniedForTerminal))
			return {
				ok: false,
				gaps: ["host.terminal-proof"],
				reason: "no narrowly proven already-executed terminal action",
			};
		if (!snapshot.ok || (snapshot.value.blocked && !(terminalIntent && exactExhausted)))
			return {
				ok: false,
				gaps: [snapshot.ok ? (snapshot.value.blocked ?? "blocked") : snapshot.code],
				reason: "live budget unavailable",
			};
		if (
			!preflight.ok ||
			((!preflight.value.granted || preflight.value.reason !== "granted") && !(terminalIntent && deniedForTerminal))
		)
			return {
				ok: false,
				gaps: [preflight.ok ? "budget-exhausted" : preflight.code],
				reason: "no live reservation preflight",
			};
		const budget: MatterBudgetV1 = {
			...snapshot.value.budget,
			matter_ref: input.expected.matter_ref,
			// The store validates a granted preflight against the same allowance.
			// Child and in-flight holds lower availability without recording spend.
			...(preflight.value.granted
				? {
						max_steps: snapshot.value.budget.steps_consumed + snapshot.value.available_steps,
						remaining_cost: snapshot.value.available_cost,
					}
				: {}),
			source_refs: [...input.cardBudget.source_refs, history.value.through_ref],
		};
		const executedAction =
			terminalIntent && terminalProof !== undefined
				? { ...terminalProof, matter_ref: input.expected.matter_ref }
				: undefined;
		return {
			ok: true,
			value: {
				budget,
				preflight: preflight.value,
				observationRef: history.value.through_ref,
				...(executedAction === undefined ? {} : { executed_action: executedAction }),
			},
		};
	}

	private readBudgetAuthorization(binding: RuntimeBudgetBinding): RuntimeBudgetAuthorization | undefined {
		const source = this.sourcesByUnit.get(binding.authorization_unit);
		if (!source || binding.parent_budget_ref !== source.parentBudgetRef) return undefined;
		const history = this.historyFor(source);
		if (!history.ok) return undefined;
		return {
			authorization_unit: source.authorizationUnit,
			parent_budget_ref: source.parentBudgetRef,
			initial: { ...source.initial },
			cost_unit: source.costUnit,
			started_at: source.budgetStartedAt,
			history: history.value,
		};
	}

	private readBinding(): HostBinding | undefined {
		const source = this.committingSource ?? this.activeSourceFor();
		if (!source) return undefined;
		const authorization: RuntimeHostAuthorization = {
			localRef: this.activeLocalRef ?? "unbound",
			key: source.key,
			source: source.source,
			role: source.role,
			owningPmClaim: source.claimId,
			taskKey: source.taskKey,
			...(source.runId === undefined ? {} : { runId: source.runId }),
			cardPath: source.cardPath,
			cardSha256: source.sourcePin,
			budgetStartedAt: source.budgetStartedAt,
			authorizationUnit: source.authorizationUnit,
			matterRef: source.authorizationUnit,
			...(source.stage === undefined ? {} : { stageRef: source.stage.stageRef }),
		};
		const authority = readRuntimeAuthority({
			agenticdocRoot: this.root,
			key: source.key,
			source: source.source,
			taskKey: source.taskKey,
			...(source.runId === undefined ? {} : { runId: source.runId }),
			clockMs: this.clock(),
			authorization,
		});
		if (!authority.ok) return undefined;
		return {
			role: authority.value.role,
			owner: source.claimId,
			claim_id: source.claimId,
			key: source.key,
			...(source.source === "worker-local"
				? { task_key: source.taskKey, ...(source.runId === undefined ? {} : { run_id: source.runId }) }
				: {}),
			binding_version: authority.value.bindingVersion,
			observed_at: new Date(this.clock()).toISOString(),
		};
	}

	private readTargetAuthorization(
		selection: Readonly<{ local_ref: string; host_binding: HostBinding }>,
		call: Readonly<RuntimeToolCall>,
	): RuntimeTargetAuthorization | undefined {
		const source = this.activeSourceFor();
		if (
			!source ||
			call.tool !== "write" ||
			selection.local_ref !== this.activeLocalRef ||
			call.local_ref !== this.activeLocalRef ||
			this.expectedFor?.(selection.local_ref) === undefined
		)
			return undefined;
		const binding = this.readBinding();
		if (!binding || binding.binding_version !== selection.host_binding.binding_version) return undefined;
		const snapshot = this.controllers?.budget.snapshot(this.binding(source));
		if (!snapshot?.ok) return undefined;
		if (snapshot.value.blocked) {
			const proof = this.terminalArchivalFor({
				key: source.key,
				source: source.source,
				ref: selection.local_ref,
				task_key: source.taskKey,
				run_id: source.runId,
				write_kind: "execution",
			});
			// A call that already has a REAL host-observed result is not a new
			// business action: at exact terminal exhaustion, re-reading its target
			// authorization only re-checks currentness of the stored proof. It
			// grants nothing (a new call has no observation, and reserve/preflight
			// stay exhausted), so it cannot become a zero-budget bypass.
			const completedActionReRead =
				this.observedToolResults.has(call.toolCallId) &&
				exactTerminalExhaustion(snapshot.value, source, this.clock());
			if (
				!completedActionReRead &&
				(proof === undefined ||
					proof.action_ref !== call.toolCallId ||
					proof.local_ref !== selection.local_ref ||
					proof.local_ref !== call.local_ref)
			)
				return undefined;
			return { run_id: source.executionRunId, targets: [...source.writeFace], write_face: [...source.writeFace] };
		}
		return { run_id: source.executionRunId, targets: [...source.writeFace], write_face: [...source.writeFace] };
	}

	private readDisposition(
		context: Readonly<{
			selection: { host_binding: HostBinding; matter_ref: string; budget_ref: string };
			call: RuntimeToolCall;
			proof: ExecutionProof;
			disposition_ref: string;
		}>,
	): PmDisposition | undefined {
		const owner = context.selection.host_binding.owner;
		if (!nonblank(owner)) return undefined;
		const tool: ToolName = context.call.tool;
		return {
			schema_version: DECISION_HANDOFF_SCHEMA_VERSION,
			disposition_ref: context.disposition_ref,
			feedback_ref: `feedback:${context.call.toolCallId}`,
			matter_ref: context.selection.matter_ref,
			kind: "collect-evidence",
			owner,
			binding: context.selection.host_binding,
			goal_ref: "goal:observed-byte-manifest",
			gap_refs: [],
			basis_refs: [context.call.toolCallId, context.proof.result_ref],
			planned_action: { tool, scope_ref: "host-complete-write-face", read_only: false },
			expected_result: "target byte manifest",
			result_consumer: "owning-pm:review",
			budget_ref: context.selection.budget_ref,
			status: "observed",
		};
	}

	private captureEvidence(binding: RuntimeBudgetBinding): readonly RuntimeBudgetEvidence[] | undefined {
		const source = this.sourcesByUnit.get(binding.authorization_unit);
		if (!source) return undefined;
		const entries: RuntimeBudgetEvidence[] = [];
		for (const target of source.writeFace) {
			const abs = path.resolve(this.projectRoot, ...target.split("/"));
			try {
				const stat = fs.lstatSync(abs);
				if (!stat.isFile() || stat.isSymbolicLink()) return undefined;
				entries.push({ ref: target, bytes: fs.readFileSync(abs) });
			} catch {
				return undefined;
			}
		}
		return entries;
	}

	private evidence(source: RegisteredSource): RuntimeBudgetEvidenceDigest[] {
		const captured = this.captureEvidence(this.binding(source));
		return (captured ?? []).map((entry) => ({
			ref: entry.ref,
			sha256: crypto.createHash("sha256").update(entry.bytes).digest("hex"),
		}));
	}

	private appendObservation(
		source: RegisteredSource,
		kind: EntryData["kind"],
		event?: RuntimeBudgetReplayEvent,
	): boolean {
		if (!this.session || this.observationFailed) return false;
		const data: EntryData = {
			id: crypto.randomUUID(),
			kind,
			unit: source.authorizationUnit,
			parent: source.parentBudgetRef,
			at: this.clock(),
			source_pin: source.sourcePin,
			started_at: source.budgetStartedAt,
			key: source.key,
			task_key: source.taskKey,
			run_id: source.executionRunId,
			claim_id: source.claimId,
			...(event === undefined ? {} : { event }),
		};
		try {
			this.session.append(RUNTIME_BUDGET_ENTRY_TYPE, data);
			const seen = this.session.read().entries.some((entry) => isRecord(entry.data) && entry.data.id === data.id);
			if (!seen) this.observationFailed = true;
			return seen && !this.observationFailed;
		} catch {
			this.observationFailed = true;
			return false;
		}
	}

	private appendEvent(source: RegisteredSource, event: RuntimeBudgetReplayEvent): boolean {
		return this.appendObservation(source, "event", event);
	}

	private attachSource(source: RegisteredSource): void {
		const first = this.historyFor(source);
		if (!first.ok && first.gaps.includes("genesis")) {
			if (!this.appendObservation(source, "genesis")) {
				this.historyFailed = "session-genesis-observation-unknown";
				return;
			}
		}
		const history = this.historyFor(source);
		if (!history.ok) {
			this.historyFailed = history.reason;
			return;
		}
		this.counts.replayedActionRefs += history.value.events.length;
		const open = this.controllers?.budget.open(this.binding(source));
		if (!open?.ok) this.historyFailed = open?.ok ? "budget-open-failed" : (open?.code ?? "budget-not-composed");
	}

	private historyFor(source: RegisteredSource): RuntimeFactRead<RuntimeBudgetHistory> {
		if (!this.session) return { ok: false, gaps: ["session"], reason: "session history channel is not attached" };
		if (this.observationFailed)
			return { ok: false, gaps: ["session-observation-unknown"], reason: "observation write is unknown" };
		const snapshot = this.session.read();
		const own = snapshot.entries.flatMap((entry) => {
			if (entry.type !== "custom" || entry.customType !== RUNTIME_BUDGET_ENTRY_TYPE) return [];
			const data = entryData(entry.data);
			return data !== undefined && data.unit === source.authorizationUnit ? [{ entry, data }] : [];
		});
		const stageBoundary =
			source.stage === undefined
				? -1
				: snapshot.entries.findIndex(
						(entry) =>
							entry.type === "custom" &&
							entry.customType === PM_STAGE_ENTRY_TYPE &&
							isRecord(entry.data) &&
							entry.data.event_id === source.stage?.eventId &&
							entry.data.grant_digest === source.stage?.grantDigest &&
							entry.data.session_id === snapshot.id &&
							entry.data.card_sha256 === source.sourcePin,
					);
		const genesisIndex = own.findIndex((item) => item.data.kind === "genesis");
		if (genesisIndex < 0) {
			// Only a freshly verified PM stage may start after earlier session
			// activity. Worker/legacy units retain their original prior-activity rule.
			if (stageBoundary >= 0 && own.length === 0)
				return { ok: false, gaps: ["genesis"], reason: "new authenticated PM stage has no budget genesis" };
			const messagesBefore = snapshot.entries.some(
				(entry) =>
					entry.type === "message" &&
					(entry.message?.role === "user" ||
						entry.message?.role === "assistant" ||
						entry.message?.role === "toolResult"),
			);
			return {
				ok: false,
				gaps: messagesBefore ? ["history-unverified"] : ["genesis"],
				reason: messagesBefore ? "existing activity without verified genesis" : "fresh unit has no genesis",
			};
		}
		const genesis = own[genesisIndex];
		if (genesis === undefined || genesisIndex !== 0)
			return { ok: false, gaps: ["genesis-order"], reason: "genesis is not the first observation for this unit" };
		if (
			genesis.data.parent !== source.parentBudgetRef ||
			genesis.data.source_pin !== source.sourcePin ||
			genesis.data.started_at !== source.budgetStartedAt ||
			genesis.data.key !== source.key ||
			genesis.data.task_key !== source.taskKey ||
			genesis.data.run_id !== source.executionRunId ||
			genesis.data.claim_id !== source.claimId
		)
			return { ok: false, gaps: ["genesis-drift"], reason: "genesis does not match exact pinned source" };
		const budgetBoundary = snapshot.entries.findIndex((entry) => entry.id === genesis.entry.id);
		if (source.stage !== undefined && (stageBoundary < 0 || stageBoundary >= budgetBoundary))
			return {
				ok: false,
				gaps: ["stage-genesis-order"],
				reason: "PM stage genesis must precede its budget genesis",
			};
		const beforeGenesis = new Set(
			snapshot.entries.slice(stageBoundary < 0 ? 0 : stageBoundary + 1, budgetBoundary).map((entry) => entry.id),
		);
		if (
			snapshot.entries.some(
				(entry) => beforeGenesis.has(entry.id) && entry.type === "message" && entry.message?.role === "assistant",
			)
		)
			return { ok: false, gaps: ["prior-activity"], reason: "assistant activity predates unit genesis" };
		const events: RuntimeBudgetReplayEvent[] = [];
		for (const item of own.slice(1)) {
			const event = replayEvent(item.data.event, source);
			if (event === undefined)
				return { ok: false, gaps: ["history-event"], reason: "malformed host budget observation" };
			events.push(event);
		}
		if (snapshot.file !== undefined && fs.existsSync(snapshot.file)) {
			try {
				const lines = fs.readFileSync(snapshot.file, "utf8").split(/\r?\n/).filter(Boolean);
				const ids = new Set<string>();
				for (const line of lines) {
					const parsed = JSON.parse(line) as SessionLikeEntry;
					if (parsed.type === "custom" && parsed.customType === RUNTIME_BUDGET_ENTRY_TYPE && nonblank(parsed.id))
						ids.add(parsed.id);
				}
				const hasAssistant = snapshot.entries.some(
					(entry) => entry.type === "message" && entry.message?.role === "assistant",
				);
				if (hasAssistant && own.some((item) => item.entry.id !== undefined && !ids.has(item.entry.id)))
					return {
						ok: false,
						gaps: ["session-file"],
						reason: "custom observation missing from persisted session",
					};
			} catch {
				return { ok: false, gaps: ["session-file"], reason: "persisted session history unreadable" };
			}
		}
		const last = own.at(-1)?.entry.id ?? genesis.entry.id ?? "unknown";
		return {
			ok: true,
			value: {
				kind: events.length === 0 ? "verified-empty" : "verified-replay",
				origin_ref: `session://${snapshot.id}/entry/${genesis.entry.id ?? "unknown"}`,
				through_ref: `session://${snapshot.id}/entry/${last}`,
				events,
			},
		};
	}
}

/** Register the SAME host object's event observers. No model-callable tool is
 *  added; the existing three-string submit and ask tools remain the surface. */
export function registerProductionRuntimeEvents(
	pi: ExtensionAPI,
	host: ProductionRuntimeHost,
	options?: { pmStage?: { projectDir: string; home?: string; claimId?: string; nowMs?: number } },
): void {
	const refresh = (ctx: ExtensionContext): void => {
		if (options?.pmStage === undefined || process.env.PI_WORKER_TASK !== undefined) return;
		host.admitPmStageFromChannel({ ...options.pmStage, sessionId: ctx.sessionManager.getSessionId() });
	};
	pi.on("session_start", (_event, ctx) => {
		host.attachSession(ctx, (customType, data) => pi.appendEntry(customType, data));
		refresh(ctx);
	});
	pi.on("tool_call", (event, ctx) => {
		// All assistant message_end handlers (including receipt STARTED) finish
		// before tool dispatch. Unlike a message_end observer, this is independent
		// of channel/host registration order and works in an already-running PM.
		refresh(ctx);
		return host.beforeToolCall(event);
	});
	pi.on("tool_result", async (event) => {
		await host.afterToolResult(event);
	});
	pi.on("agent_settled", () => {
		host.settleUnknown();
	});
	pi.on("session_shutdown", () => {
		host.onAgentEnd("shutdown");
	});
}
