/**
 * shared/issue-model.ts — T-01 of key `mw-issue-feedback`: the SINGLE domain
 * model for MW product-issue scene facts, development progress and the
 * reporter-facing views.
 *
 * Design anchors: `design.md` D-001 (guided scene form, not a pasted log),
 * D-002 / §2 (one ID, development progress + supplement question/reply), §2
 * card fields and §3 flows; `spec.md` §3 AC-001/002/004/005. The store
 * (`shared/issue-store.ts`, T-03), the root locator (T-02) and the pi window
 * (`pm/issue-command.ts`, T-04) own all I/O; this module owns none.
 *
 * Invariants enforced here (all pure, deterministic, in-memory):
 *
 * - Three distinct times: failure occurrence (reporter-stated), submission and
 *   environment capture (window-recorded). A current reading NEVER fills a
 *   failure-time field; `observed` values in the failure-time environment are
 *   downgraded to unknown, and an `observed` value without a legal capture
 *   time is downgraded too (D-001: "当前实测不可冒充故障时快照").
 * - Every value carries `source = observed|user|unknown` and an observation
 *   time. A missing value is an explicit unknown; nothing is guessed or
 *   truncated. Reproduction may be unknown ("复现未知/仅发生一次").
 * - Known credentials and high-confidence token shapes are scrubbed from
 *   every text field that can enter the persistent payload. Only explicitly
 *   selected diagnostic fragments enter it. The full redacted preview is a
 *   complete render of exactly that payload (no summary, no truncation).
 * - Unconfirmed input stays in the in-memory `IssueDraft`/`IssuePreparation`.
 *   `confirmIssue` is the only producer of `ConfirmedIssue` and requires an
 *   explicit confirmation plus the digest of the complete preview. It performs
 *   no write, generates no ID and calls no clock: the caller (store/command)
 *   owns persistence, ID creation and the human confirmation UI.
 * - No role/approval gate is added here. AC-006 (reject an unauthorized worker
 *   write) belongs to the command/store write gate, not to the value model.
 *
 * Leaf module: `node:crypto` (hashing only) and `Date.parse` (pure) are the
 * only runtime facilities. No filesystem access, no network, no environment
 * lookup, no wall-clock call, no inline/dynamic imports.
 */

import { createHash } from "node:crypto";

import {
	escapeIssueIdentity,
	escapeUntrustedText,
	ISSUE_CONTROL_ESCAPE_PREFIX,
	ISSUE_CONTROL_ESCAPE_SUFFIX,
	ISSUE_RAW_TEXT_RULE,
	type IssueTextMode,
	normalizeIssueText,
} from "./issue-text.ts";

// ── Vocabulary ────────────────────────────────────────────────────────────────

export const SOURCE_TAGS = ["observed", "user", "unknown"] as const;
/** Where a value came from. `unknown` is a first-class value, never a guess. */
export type SourceTag = (typeof SOURCE_TAGS)[number];

/** spec §2 state vocabulary; no reject/duplicate/withdrawn words are added. */
export const DEV_STATUSES = ["待分诊", "修复中", "已修复", "已发布"] as const;
export type DevStatus = (typeof DEV_STATUSES)[number];

export const REPRODUCTION_FREQUENCIES = ["每次", "偶发", "未知"] as const;
export type ReproductionFrequency = (typeof REPRODUCTION_FREQUENCIES)[number];

export const LOCAL_EFFECTIVE_STATES = ["verified", "not-verified", "unknown"] as const;
export type LocalEffective = (typeof LOCAL_EFFECTIVE_STATES)[number];

/** Explicit missing-value label in every user-visible rendering. */
export const UNKNOWN = "未知";
export const REDACTION_MARK = "[REDACTED]";
export const VERIFIED_PHRASE = "本项目已验证已用上修复";
export const NOT_VERIFIED_PHRASE = "本项目未验证已用上修复";

// ── Values with provenance ────────────────────────────────────────────────────

/** A scene value: text OR a tz-aware ISO instant (for time fields). `null`
 * means unknown. `at` is the observation/statement/capture time. */
export interface Observation {
	value: string | null;
	source: SourceTag;
	/** tz-aware ISO-8601 instant, or null when the time itself is unknown. */
	at: string | null;
}

export function unknownObservation(): Observation {
	return { value: null, source: "unknown", at: null };
}

/** Reporter-stated value. `at` is the statement time when known. */
export function userObservation(value: string | null, at: string | null = null): Observation {
	return value === null ? unknownObservation() : { value, source: "user", at };
}

/** Window-measured value; `at` is mandatory at normalization time. */
export function observedObservation(value: string | null, at: string | null): Observation {
	return value === null ? unknownObservation() : { value, source: "observed", at };
}

const INSTANT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/;

/** A legal tz-aware ISO instant. Naive local times are refused: design §2
 * requires "均含时区或说明未知" (`unknown` is represented by null). */
export function isInstant(value: string | null | undefined): value is string {
	if (typeof value !== "string" || !INSTANT_RE.test(value)) return false;
	return !Number.isNaN(Date.parse(value));
}

// ── Redaction (AC-002 model half) ─────────────────────────────────────────────

const ASSIGNMENT_SECRET_RE =
	/(\b(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|password|passwd|pwd|secret|client[_-]?secret|authorization)\s*[:=]\s*)("[^"]+"|'[^']+'|[^\s,;]+)/gi;
const TOKEN_SECRET_RE =
	/\b(?:Bearer\s+[A-Za-z0-9._~+/=-]{12,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})/gi;

export interface RedactionResult {
	text: string;
	/** Number of replacements actually made (for the preparation notes). */
	redactions: number;
}

/** Scrub exact known credential values (caller-supplied; they are NEVER stored
 * in the card) plus high-confidence token/assignment shapes. Pure string work:
 * no file or environment reading. The caller must pass real known secrets, not
 * short fragments that occur inside ordinary words. */
export function redactSecrets(text: string, knownSecrets: readonly string[] = []): RedactionResult {
	let result = text;
	let redactions = 0;
	for (const secret of knownSecrets) {
		if (!secret.trim()) continue;
		const parts = result.split(secret);
		if (parts.length > 1) {
			redactions += parts.length - 1;
			result = parts.join(REDACTION_MARK);
		}
	}
	result = result.replace(ASSIGNMENT_SECRET_RE, (_whole, prefix: string) => {
		redactions++;
		return `${prefix}${REDACTION_MARK}`;
	});
	result = result.replace(TOKEN_SECRET_RE, () => {
		redactions++;
		return REDACTION_MARK;
	});
	return { text: result, redactions };
}

// ── Draft (in-memory only) and card (persistable) ─────────────────────────────

export interface EnvironmentFacts {
	mwVersion: Observation;
	piVersion: Observation;
	platform: Observation;
	windowType: Observation;
}

export interface ObservedEnvironmentFacts extends EnvironmentFacts {
	bundleStatus: Observation;
	serveStatus: Observation;
}

export interface DiagnosticCandidate {
	id: string;
	kind: "log" | "error" | "attachment-ref";
	/** Raw candidate text. Only selected ids (after redaction) reach the card. */
	text: string;
}

export interface ConfirmedFragment {
	id: string;
	kind: "log" | "error" | "attachment-ref";
	/** Redacted full text; never truncated. */
	text: string;
	/** Only the user can select a diagnostic fragment. */
	source: "user";
}

/** In-memory report form. NEVER persist this type: candidate fragment text and
 * unconfirmed values live here only. `id` is supplied by the store (this model
 * generates no ID), `title` is the one-line phenomenon. */
export interface IssueDraft {
	id: string;
	title: string;
	/** Non-sensitive identifier of the reporting project. */
	projectLabel: string;
	/** MW component/entry; unknown renders as "待分诊", never a guessed locator. */
	component: Observation;
	/** Failure occurrence time (reporter-stated, value is an ISO instant). */
	occurredAt: Observation;
	trigger: Observation;
	precondition: Observation;
	expected: Observation;
	actual: Observation;
	impact: Observation;
	reproductionSteps: Observation;
	reproductionFrequency: ReproductionFrequency | null;
	/** Verbatim key error text chosen by the user; no summary truncation. */
	errorExcerpt: Observation;
	/** Environment AS REPORTED for the failure moment: user/unknown only. */
	environmentAtFailure: EnvironmentFacts;
	/** Environment MEASURED NOW by the window: observed/unknown only. */
	observedEnvironment: ObservedEnvironmentFacts;
	diagnosticCandidates: readonly DiagnosticCandidate[];
	selectedFragmentIds: readonly string[];
}

export interface DevUpdate {
	/** tz-aware update time. */
	at: string;
	/** Author label (bookkeeping, NOT an approval/role gate). */
	by: string;
	status: DevStatus;
	/** Triage conclusion / status reason (development-side explanation). */
	statusNote: string;
	nextAction: string | null;
	/** Fix commit, kept separate from the release version (design §2). */
	fixCommit: string | null;
	/** Published version, kept separate from the fix commit. */
	releaseVersion: string | null;
	/** Concrete supplement question to the reporter, under the same ID. */
	questionToReporter: string | null;
}

export interface ReporterReply {
	at: string;
	/** Confirmed + redacted; appended, never overwriting the original scene. */
	text: string;
	source: SourceTag;
	inReplyTo: string | null;
}

/** The single persistent payload shape: normalized, source-tagged, redacted. */
export interface IssueCard {
	schema: 1;
	id: string;
	title: string;
	projectLabel: string;
	component: Observation;
	/** 故障发生时间 (user / unknown). */
	occurredAt: Observation;
	/** 提交时间 (window-recorded observed / unknown). */
	submittedAt: Observation;
	/** 环境采集时间 (window-recorded observed / unknown). */
	environmentObservedAt: Observation;
	scene: {
		trigger: Observation;
		precondition: Observation;
		expected: Observation;
		actual: Observation;
		impact: Observation;
		reproductionSteps: Observation;
		reproductionFrequency: ReproductionFrequency;
		errorExcerpt: Observation;
		environmentAtFailure: EnvironmentFacts;
		observedEnvironment: ObservedEnvironmentFacts;
	};
	diagnostics: ConfirmedFragment[];
	devTimeline: DevUpdate[];
	reporterReplies: ReporterReply[];
	/** In-memory projection ONLY, NEVER persisted: `questionEventHashes[i]` is
	 * the sha256 of the dev_update authority event that produced
	 * `devTimeline[i]`. Attached by the store after replaying the hash chain
	 * (see `withQuestionIdentities`); a created card (empty timeline) and every
	 * stored event never carry it, and it never enters canonicalPayload, the
	 * preview or any digest. `appendDevUpdate` clears it because a dev-timeline
	 * change invalidates the 1:1 alignment. `pendingQuestion` uses these stable
	 * identities to decide whether a reply answers a specific question, instead
	 * of comparing reply clocks. */
	questionEventHashes?: string[];
}

// ── Preparation / confirmation (AC-002, D-001) ───────────────────────────────

export interface PrepareOptions {
	/** Window-recorded submission instant (NOT the failure occurrence time). */
	submittedAt: string | null;
	/** Window-recorded environment capture instant. */
	environmentObservedAt: string | null;
	/** Known credential values; used transiently, never stored in the card. */
	knownSecrets?: readonly string[];
	/** Explicit in-memory text boundary: raw ingress or canonical replay/render. */
	textMode?: IssueTextMode;
}

export interface IssuePreparation {
	/** In-memory candidate payload. NOT approved for persistence. */
	card: IssueCard;
	/** Full redacted preview of exactly the payload that would be sent. */
	preview: string;
	previewSha256: string;
	/** Stable content digest (sha256 of the canonical payload, 16 hex chars)
	 * for the store's same-ID idempotency check (T-03). */
	submissionDigest: string;
	redactions: number;
	/** Human-readable downgrades/drops; no raw sensitive text. */
	notes: string[];
}

export interface Confirmation {
	confirmed: boolean;
	/** tz-aware instant of the human confirmation. */
	confirmedAt: string | null;
	/** Digest of the COMPLETE preview the user actually saw. */
	previewSha256: string;
}

export interface ConfirmedIssue {
	/** Explicit hand-off marker for the store; the model itself writes nothing. */
	readonly approvedForPersistence: true;
	card: IssueCard;
	submissionDigest: string;
	confirmedAt: string;
}

function digest(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

/** Stable serialization for the store's byte/idempotency comparisons. Field
 * insertion order is fixed by the constructors in this module. */
export function canonicalPayload(card: IssueCard): string {
	return JSON.stringify(card);
}

interface NormalizeContext {
	readonly clean: (text: string) => string;
	readonly notes: string[];
}

const ALL_SOURCES: readonly SourceTag[] = SOURCE_TAGS;
const REPORTER_SOURCES: readonly SourceTag[] = ["user", "unknown"];
const WINDOW_SOURCES: readonly SourceTag[] = ["observed", "unknown"];

/** Normalize one observation: drop empty values, refuse provenance that is not
 * valid for the field, require a legal capture time for `observed`, and scrub
 * secrets. Every downgrade is recorded in the notes (fail closed, never guess). */
function normalizeObservation(
	raw: Observation | undefined,
	allowed: readonly SourceTag[],
	label: string,
	ctx: NormalizeContext,
): Observation {
	if (!raw) return unknownObservation();
	const rawValue = typeof raw.value === "string" && raw.value.trim() !== "" ? raw.value : null;
	if (rawValue === null) return unknownObservation();
	if (!allowed.includes(raw.source)) {
		ctx.notes.push(`${label}: 来源 ${raw.source} 不适用于该字段，按未知处理`);
		return unknownObservation();
	}
	if (raw.source === "unknown") return unknownObservation();
	const atValid = isInstant(raw.at);
	if (raw.source === "observed" && !atValid) {
		ctx.notes.push(`${label}: 窗口实测缺合法采集时间，按未知处理（不得冒充现场实测）`);
		return unknownObservation();
	}
	if (!atValid && raw.at !== null && raw.at !== undefined) {
		ctx.notes.push(`${label}: 附带时间缺时区或非法，已置为未知`);
	}
	return { value: ctx.clean(rawValue), source: raw.source, at: atValid ? raw.at : null };
}

/** Time-valued observation: the VALUE must itself be a tz-aware instant. */
function normalizeTimeObservation(
	raw: Observation | undefined,
	allowed: readonly SourceTag[],
	label: string,
	ctx: NormalizeContext,
): Observation {
	const normalized = normalizeObservation(raw, allowed, label, ctx);
	if (normalized.value === null) return normalized;
	if (!isInstant(normalized.value)) {
		ctx.notes.push(`${label}: 时间值缺时区或非法，按未知处理`);
		return unknownObservation();
	}
	return normalized;
}

function observedTimePoint(instant: string | null | undefined, label: string, ctx: NormalizeContext): Observation {
	if (!isInstant(instant)) {
		ctx.notes.push(`${label}: 窗口未提供合法带时区时间，按未知处理`);
		return unknownObservation();
	}
	return { value: instant, source: "observed", at: instant };
}

function normalizeEnvironmentFacts(
	facts: EnvironmentFacts | undefined,
	allowed: readonly SourceTag[],
	prefix: string,
	ctx: NormalizeContext,
): EnvironmentFacts {
	return {
		mwVersion: normalizeObservation(facts?.mwVersion, allowed, `${prefix} MW 版本`, ctx),
		piVersion: normalizeObservation(facts?.piVersion, allowed, `${prefix} pi 版本`, ctx),
		platform: normalizeObservation(facts?.platform, allowed, `${prefix} 平台`, ctx),
		windowType: normalizeObservation(facts?.windowType, allowed, `${prefix} 窗口类型`, ctx),
	};
}

/** Build the in-memory candidate card + full redacted preview + digests. No I/O,
 * no clock, no ID generation, no persistence, no mutation of the draft. */
export function prepareIssue(draft: IssueDraft, options: PrepareOptions): IssuePreparation {
	const notes: string[] = [];
	let redactions = 0;
	let escapedControls = 0;
	const knownSecrets = options.knownSecrets ?? [];
	const textMode = options.textMode ?? "canonical";
	// Credential scrubbing stays EXACTLY redactSecrets (its signature/count/
	// semantics are D's raw-leaf store check contract). Redaction runs first so
	// credentials are matched on raw bytes. The caller's explicit mode selects
	// one raw encoding or the canonical fixed point; replacements are NEVER
	// counted as secret hits. Nothing infers a source by matching token text.
	const clean = (text: string): string => {
		const result = redactSecrets(text, knownSecrets);
		redactions += result.redactions;
		const normalized = normalizeIssueText(result.text, textMode, REDACTION_MARK);
		escapedControls += normalized.count;
		return normalized.text;
	};
	const ctx: NormalizeContext = { clean, notes };

	const failureEnv = normalizeEnvironmentFacts(draft.environmentAtFailure, REPORTER_SOURCES, "故障时环境", ctx);
	const observedEnvBase = normalizeEnvironmentFacts(draft.observedEnvironment, WINDOW_SOURCES, "窗口实测环境", ctx);
	const observedEnvironment: ObservedEnvironmentFacts = {
		...observedEnvBase,
		bundleStatus: normalizeObservation(
			draft.observedEnvironment?.bundleStatus,
			WINDOW_SOURCES,
			"窗口实测 bundle 状态",
			ctx,
		),
		serveStatus: normalizeObservation(
			draft.observedEnvironment?.serveStatus,
			WINDOW_SOURCES,
			"窗口实测 serve 状态",
			ctx,
		),
	};

	const frequency = draft.reproductionFrequency;
	const reproductionFrequency: ReproductionFrequency = REPRODUCTION_FREQUENCIES.includes(
		frequency as ReproductionFrequency,
	)
		? (frequency as ReproductionFrequency)
		: "未知";
	if (frequency !== null && frequency !== undefined && reproductionFrequency !== frequency) {
		notes.push("复现频率取值无效，按未知处理");
	}

	const selected = new Set(draft.selectedFragmentIds ?? []);
	const diagnostics: ConfirmedFragment[] = [];
	let unselected = 0;
	const seen = new Set<string>();
	for (const candidate of draft.diagnosticCandidates ?? []) {
		if (!selected.has(candidate.id)) {
			unselected++;
			continue;
		}
		if (seen.has(candidate.id)) {
			notes.push("重复选择的诊断片段 id 已忽略");
			continue;
		}
		seen.add(candidate.id);
		const text = clean(candidate.text);
		if (!text.trim()) {
			notes.push("空诊断片段已忽略");
			continue;
		}
		// Candidate IDs are host-generated identifiers, not raw report text.
		diagnostics.push({ id: candidate.id, kind: candidate.kind, text, source: "user" });
	}
	for (const id of selected) {
		if (!seen.has(id)) notes.push("选择的诊断片段 id 不在候选列表中，已忽略");
	}
	if (unselected > 0) notes.push(`${unselected} 个未选择的诊断片段仅保留在内存，未进入载荷`);
	if (redactions > 0) notes.push(`脱敏：替换 ${redactions} 处已知凭证/令牌形状`);
	if (escapedControls > 0) {
		notes.push(
			`外来控制字节已转为可见转义 ${ISSUE_CONTROL_ESCAPE_PREFIX}XXXX${ISSUE_CONTROL_ESCAPE_SUFFIX} 共 ${escapedControls} 处；原文未删除、可逐字核对，预览/载荷/摘要使用同一确定性表示`,
		);
	}
	if (textMode === "raw") notes.push(`raw 文本边界：${ISSUE_RAW_TEXT_RULE}`);

	const card: IssueCard = {
		schema: 1,
		// Identities are exact host/store values. Only raw report fields go through
		// `clean`; their terminal representation is handled separately at render time.
		id: draft.id,
		title: clean(draft.title),
		projectLabel: draft.projectLabel,
		component: normalizeObservation(draft.component, ALL_SOURCES, "MW 组件/入口", ctx),
		occurredAt: normalizeTimeObservation(draft.occurredAt, REPORTER_SOURCES, "故障发生时间", ctx),
		submittedAt: observedTimePoint(options.submittedAt, "提交时间", ctx),
		environmentObservedAt: observedTimePoint(options.environmentObservedAt, "环境采集时间", ctx),
		scene: {
			trigger: normalizeObservation(draft.trigger, ALL_SOURCES, "触发操作", ctx),
			precondition: normalizeObservation(draft.precondition, ALL_SOURCES, "前置条件", ctx),
			expected: normalizeObservation(draft.expected, ALL_SOURCES, "预期结果", ctx),
			actual: normalizeObservation(draft.actual, ALL_SOURCES, "实际结果", ctx),
			impact: normalizeObservation(draft.impact, ALL_SOURCES, "影响", ctx),
			reproductionSteps: normalizeObservation(draft.reproductionSteps, ALL_SOURCES, "复现步骤", ctx),
			reproductionFrequency,
			errorExcerpt: normalizeObservation(draft.errorExcerpt, ALL_SOURCES, "关键错误片段", ctx),
			environmentAtFailure: failureEnv,
			observedEnvironment,
		},
		diagnostics,
		devTimeline: [],
		reporterReplies: [],
	};

	const preview = renderPreview(card);
	return {
		card,
		preview,
		previewSha256: digest(preview),
		submissionDigest: digest(canonicalPayload(card)).slice(0, 16),
		redactions,
		notes,
	};
}

/** The ONLY producer of a payload approved for persistence. Refusal, an invalid
 * confirmation time, a preview mismatch, or a forged preparation all yield
 * `null` — i.e. nothing the store could write (AC-002: 拒绝确认共享端新增=0). */
export function confirmIssue(prep: IssuePreparation, confirmation: Confirmation): ConfirmedIssue | null {
	if (!confirmation.confirmed) return null;
	if (!isInstant(confirmation.confirmedAt)) return null;
	if (digest(prep.preview) !== prep.previewSha256) return null;
	if (confirmation.previewSha256 !== prep.previewSha256) return null;
	return {
		approvedForPersistence: true,
		card: prep.card,
		submissionDigest: prep.submissionDigest,
		confirmedAt: confirmation.confirmedAt,
	};
}

// ── Development progress / replies (design §2, AC-004) ───────────────────────

/** Append a development-side update; pure (returns a new card). All free text
 * is redacted. The original scene is never overwritten. */
export function appendDevUpdate(
	card: IssueCard,
	update: DevUpdate,
	knownSecrets: readonly string[] = [],
	textMode: IssueTextMode = "raw",
): IssueCard {
	if (!isInstant(update.at)) throw new Error("dev update requires a tz-aware ISO instant");
	if (!DEV_STATUSES.includes(update.status)) throw new Error(`unknown dev status: ${update.status}`);
	const clean = (text: string): string =>
		normalizeIssueText(redactSecrets(text, knownSecrets).text, textMode, REDACTION_MARK).text;
	const next: DevUpdate = {
		at: update.at,
		by: clean(update.by),
		status: update.status,
		statusNote: clean(update.statusNote),
		nextAction: update.nextAction === null ? null : clean(update.nextAction),
		fixCommit: update.fixCommit === null ? null : clean(update.fixCommit),
		releaseVersion: update.releaseVersion === null ? null : clean(update.releaseVersion),
		questionToReporter: update.questionToReporter === null ? null : clean(update.questionToReporter),
	};
	// A dev-timeline change invalidates the in-memory authority-event identity
	// projection; the store recomputes it from the hash chain after replay.
	const result: IssueCard = { ...card, devTimeline: [...card.devTimeline, next] };
	delete result.questionEventHashes;
	return result;
}

/** Append a reporter reply under the SAME ID; pure and redacted. */
export function appendReporterReply(
	card: IssueCard,
	reply: ReporterReply,
	knownSecrets: readonly string[] = [],
	textMode: IssueTextMode = "raw",
): IssueCard {
	if (!isInstant(reply.at)) throw new Error("reporter reply requires a tz-aware ISO instant");
	if (!SOURCE_TAGS.includes(reply.source)) throw new Error(`unknown reply source: ${reply.source}`);
	const clean = (text: string): string =>
		normalizeIssueText(redactSecrets(text, knownSecrets).text, textMode, REDACTION_MARK).text;
	const next: ReporterReply = {
		at: reply.at,
		text: clean(reply.text),
		source: reply.source,
		inReplyTo: reply.inReplyTo === null ? null : clean(reply.inReplyTo),
	};
	return { ...card, reporterReplies: [...card.reporterReplies, next] };
}

export interface DevStateView {
	status: DevStatus | typeof UNKNOWN;
	/** Development-side reason/triage conclusion; never a reporter fact. */
	statusNote: string;
	nextAction: string;
	/** Folded last non-null fix commit (separate from releaseVersion). */
	fixCommit: string;
	/** Folded last non-null release version. */
	releaseVersion: string;
	questionToReporter: string;
	updatedAt: string | null;
	by: string;
}

/** Latest visible development state. Status/note/next/question come from the
 * LAST update; fix commit and release version are folded across the timeline
 * (they are registered at different moments, design §2). Absent values are
 * explicit "未知". */
export function latestDevState(card: IssueCard): DevStateView {
	const timeline = card.devTimeline;
	if (timeline.length === 0) {
		return {
			status: UNKNOWN,
			statusNote: UNKNOWN,
			nextAction: UNKNOWN,
			fixCommit: UNKNOWN,
			releaseVersion: UNKNOWN,
			questionToReporter: UNKNOWN,
			updatedAt: null,
			by: UNKNOWN,
		};
	}
	let fixCommit: string | null = null;
	let releaseVersion: string | null = null;
	for (const update of timeline) {
		if (update.fixCommit !== null && update.fixCommit.trim() !== "") fixCommit = update.fixCommit;
		if (update.releaseVersion !== null && update.releaseVersion.trim() !== "") releaseVersion = update.releaseVersion;
	}
	const last = timeline[timeline.length - 1];
	return {
		status: last.status,
		statusNote: last.statusNote || UNKNOWN,
		nextAction: last.nextAction ?? UNKNOWN,
		fixCommit: fixCommit ?? UNKNOWN,
		releaseVersion: releaseVersion ?? UNKNOWN,
		questionToReporter: last.questionToReporter ?? UNKNOWN,
		updatedAt: last.at,
		by: last.by || UNKNOWN,
	};
}

/** Attach the stable authority-event identities to an in-memory replayed card.
 * Pure: returns a NEW card. `devUpdateEventHashes[i]` is the sha256 of the
 * dev_update authority event that produced `devTimeline[i]` (all real chain
 * hashes; nothing is forged here). This is projection metadata for
 * question/reply matching, NOT persistent schema: a created card (empty
 * timeline) and every stored event never carry it, and it never enters
 * canonicalPayload / preview / any digest. `appendDevUpdate` clears it because
 * a dev-timeline change invalidates the alignment. Only the store calls this,
 * after replaying the full hash chain, so the identities are authentic. */
export function withQuestionIdentities(card: IssueCard, devUpdateEventHashes: readonly string[]): IssueCard {
	if (devUpdateEventHashes.length !== card.devTimeline.length) {
		throw new Error("question identity map must align 1:1 with the dev timeline");
	}
	return { ...card, questionEventHashes: [...devUpdateEventHashes] };
}

/** The most recent supplement question still lacking its own answer, or null.
 *
 * The pending question is the SINGLE newest question-bearing dev_update (the
 * original single-latest-question rule is preserved: older questions are
 * superseded once a newer question is asked, matching latestDevState and the
 * window's reply target). Later dev updates with no question are skipped, so
 * they never swallow that pending question.
 *
 * "Answered" is decided by STABLE EVENT IDENTITY, never by a clock: that
 * newest question is cleared ONLY when some reply's `inReplyTo` equals the
 * sha256 of the exact dev_update event that owns it. Intentional consequences
 * (F3):
 *  - A late reply bound to an OLD question's event hash does not clear the
 *    newer pending question, even if the reply's time is later; only a reply
 *    naming the newest question's event clears it ("晚回复 Q1 不清 Q2 /
 *    明确回 Q2 才清 Q2").
 *  - Two questions sharing a timestamp stay distinguishable by their distinct
 *    event hashes.
 *  - null / created / no-question-update / time-based / unknown / foreign
 *    references are mere supplements: they never equal the question's event
 *    hash, so they clear nothing. A reply's clock is never consulted.
 *  - Old questions are NOT re-surfaced after the newest one is answered; the
 *    rule is applied uniformly here, in summarizeForList.needsReply and in
 *    store.status.pendingQuestion (all share this single projection).
 *  - A card with no identity projection (a pure in-memory card never replayed
 *    from an authority chain) resolves nothing, so it fail-closed keeps its
 *    newest question pending; it never infers "answered" from times. */
export function pendingQuestion(card: IssueCard): string | null {
	const hashes = card.questionEventHashes;
	const answered = new Set<string>();
	for (const reply of card.reporterReplies) {
		if (reply.inReplyTo !== null) answered.add(reply.inReplyTo);
	}
	for (let i = card.devTimeline.length - 1; i >= 0; i--) {
		const question = card.devTimeline[i].questionToReporter;
		if (question === null || question.trim() === "") continue;
		const identity = hashes?.[i] ?? null;
		return identity !== null && answered.has(identity) ? null : question;
	}
	return null;
}

export interface IssueListRow {
	id: string;
	title: string;
	status: DevStatus | typeof UNKNOWN;
	updatedAt: string | null;
	/** Whether the reporter still owes a supplement answer. */
	needsReply: boolean;
}

export function summarizeForList(card: IssueCard): IssueListRow {
	const state = latestDevState(card);
	return {
		id: card.id,
		title: card.title,
		status: state.status,
		updatedAt: state.updatedAt,
		needsReply: pendingQuestion(card) !== null,
	};
}

/** Pure, no-ID list projection: ONLY cards of the current project are listed
 * (AC-004 "无 ID 时只列本项目登记的反馈"). Cross-project record access and the
 * worker write gate remain store/command responsibilities. */
export function listIssuesForProject(cards: readonly IssueCard[], projectLabel: string): IssueListRow[] {
	return cards.filter((card) => card.projectLabel === projectLabel).map(summarizeForList);
}

// ── Local effectiveness (AC-005, fail-closed) ────────────────────────────────

export interface LocalEvidence {
	/** Installed/running MW version; null = unknown. */
	localVersion: string | null;
	/** null = unknown (not verified either way). */
	bundleStale: boolean | null;
	serveStale: boolean | null;
	entrypointInstalled: boolean | null;
	/** When the local evidence was collected (tz-aware), null = unknown. */
	collectedAt: string | null;
}

export interface LocalEffectiveResult {
	state: LocalEffective;
	/** Exact user-facing phrase. Every result produced in this phase uses
	 * NOT_VERIFIED_PHRASE; VERIFIED_PHRASE (and the `verified` state) stay
	 * reserved for a future phase that supplies a verifiable identity chain. */
	phrase: string;
	reason: string;
}

export function parseVersion(value: string | null): { major: number; minor: number; patch: number } | null {
	if (typeof value !== "string") return null;
	const match = /^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.+-]+)?$/.exec(value.trim());
	if (!match) return null;
	const major = Number(match[1]);
	const minor = Number(match[2]);
	const patch = Number(match[3]);
	// 0.0.0 / "unknown" / empty are the documented incomparable sentinels.
	if (major === 0 && minor === 0 && patch === 0) return null;
	return { major, minor, patch };
}

function versionAtLeast(
	local: { major: number; minor: number; patch: number },
	fix: { major: number; minor: number; patch: number },
): boolean {
	if (local.major !== fix.major) return local.major > fix.major;
	if (local.minor !== fix.minor) return local.minor > fix.minor;
	return local.patch >= fix.patch;
}

/**
 * Development-side "已修复/已发布" NEVER implies the local project uses the
 * fix (AC-005, D-005, VC-005; fail-closed).
 *
 * A comparable fix version, a comparable local version at or above it, an
 * installed entrypoint, fresh bundle/serve and a legal evidence collection
 * time are necessary but NOT sufficient to prove that the artifact built from
 * the dev-side fix is exactly what is installed AND loaded by the running MW
 * process: the same version string can belong to a different source tree, a
 * dirty tree, or a long-lived process that never reloaded the new bundle. The
 * first-phase `LocalEvidence` contract carries no verifiable
 * fix-artifact -> installed-artifact -> running-process identity chain (no
 * artifact digest, no loaded-module fingerprint), and this pure model must not
 * read the filesystem/process to invent one. Claiming `verified` from version
 * + staleness flags alone would be a guess, so this phase NEVER returns
 * `verified`: every outcome is `not-verified` or `unknown`, rendered with
 * NOT_VERIFIED_PHRASE, with an explicit reason and the version hint retained.
 * `verified` / VERIFIED_PHRASE stay reserved for a future phase that can
 * supply cryptographically bound, independently testable identity evidence.
 */
export function evaluateLocalEffective(card: IssueCard, evidence: LocalEvidence): LocalEffectiveResult {
	const state = latestDevState(card);
	const fail = (level: LocalEffective, reason: string): LocalEffectiveResult => ({
		state: level,
		phrase: NOT_VERIFIED_PHRASE,
		reason,
	});
	if (state.status !== "已修复" && state.status !== "已发布") {
		return fail("unknown", "开发侧尚未登记修复/发布状态");
	}
	if (state.releaseVersion === UNKNOWN) {
		return fail("unknown", "开发侧已登记修复但缺发布版本，无法与本地版本比对");
	}
	if (!isInstant(evidence.collectedAt)) {
		return fail("unknown", "缺少合法的本地证据采集时间");
	}
	const fix = parseVersion(state.releaseVersion);
	if (fix === null) {
		return fail("unknown", "开发侧发布版本不可解析（unknown/0.0.0）");
	}
	const local = parseVersion(evidence.localVersion);
	if (local === null) {
		return fail("unknown", "本项目运行版本缺失或不可比（unknown/0.0.0）");
	}
	if (local.major !== fix.major) {
		return fail("unknown", `本地版本 ${evidence.localVersion} 与修复版本 ${state.releaseVersion} 不同主版本，不可比`);
	}
	if (evidence.entrypointInstalled === null || evidence.bundleStale === null || evidence.serveStale === null) {
		return fail("unknown", "缺少可信的本地安装/运行证据（入口、bundle 或 serve 状态未知）");
	}
	if (evidence.entrypointInstalled === false) {
		return fail("not-verified", "MW 入口未安装，无法证明本地已用上修复");
	}
	if (!versionAtLeast(local, fix)) {
		return fail("not-verified", `本地版本 ${evidence.localVersion} 低于修复版本 ${state.releaseVersion}`);
	}
	if (evidence.bundleStale || evidence.serveStale) {
		return fail("not-verified", "本地 bundle/serve 代码陈旧，运行版本可能不含修复");
	}
	// Reached only with comparable versions, local >= fix, installed entrypoint,
	// fresh bundle/serve and a legal collection time. Still NOT `verified`: see
	// the function doc — no identity chain ties the fix artifact to the running
	// process, so version + freshness cannot rule out different source / dirty
	// tree / stale loaded process. Strongest first-phase verdict = not-verified.
	return fail(
		"not-verified",
		`本地版本 ${evidence.localVersion} 已不低于修复版本 ${state.releaseVersion}，` +
			"但版本一致、入口已安装、bundle/serve 未标陈旧均不足以证明修复产物即本地安装并运行的代码" +
			"（同版本可能为不同源码、脏树或未重载的旧进程）；缺少修复产物→安装→运行身份的可验证一致性证据，首期不声称已验证用上修复",
	);
}

// ── Rendering: complete redacted preview + user-readable projection ───────────

interface SceneEntry {
	label: string;
	obs: Observation;
	group: "time" | "fact" | "repro" | "failure-env" | "observed-env";
	unknownText?: string;
}

function sceneEntries(card: IssueCard): SceneEntry[] {
	const s = card.scene;
	return [
		{ label: "故障发生时间", obs: card.occurredAt, group: "time" },
		{ label: "提交时间（窗口记录，非故障时）", obs: card.submittedAt, group: "time" },
		{ label: "环境采集时间（窗口记录，非故障时）", obs: card.environmentObservedAt, group: "time" },
		{ label: "触发操作", obs: s.trigger, group: "fact" },
		{ label: "前置条件", obs: s.precondition, group: "fact" },
		{ label: "预期结果", obs: s.expected, group: "fact" },
		{ label: "实际结果", obs: s.actual, group: "fact" },
		{ label: "关键错误片段（用户选择，原文不截断）", obs: s.errorExcerpt, group: "fact" },
		{ label: "复现步骤（未知时明确标注，不编造）", obs: s.reproductionSteps, group: "repro" },
		{ label: "影响", obs: s.impact, group: "repro" },
		{ label: "故障时 MW 版本", obs: s.environmentAtFailure.mwVersion, group: "failure-env" },
		{ label: "故障时 pi 版本", obs: s.environmentAtFailure.piVersion, group: "failure-env" },
		{ label: "故障时平台", obs: s.environmentAtFailure.platform, group: "failure-env" },
		{ label: "故障时窗口类型", obs: s.environmentAtFailure.windowType, group: "failure-env" },
		{ label: "当前 MW 版本", obs: s.observedEnvironment.mwVersion, group: "observed-env" },
		{ label: "当前 pi 版本", obs: s.observedEnvironment.piVersion, group: "observed-env" },
		{ label: "当前平台", obs: s.observedEnvironment.platform, group: "observed-env" },
		{ label: "当前窗口类型", obs: s.observedEnvironment.windowType, group: "observed-env" },
		{ label: "当前 bundle 状态", obs: s.observedEnvironment.bundleStatus, group: "observed-env" },
		{ label: "当前 serve 状态", obs: s.observedEnvironment.serveStatus, group: "observed-env" },
	];
}

function sourceLabel(obs: Observation): string {
	if (obs.source === "observed") return `[窗口实测${obs.at ? ` @ ${obs.at}` : "（采集时间未知）"}]`;
	if (obs.source === "user") return `[用户陈述${obs.at ? ` @ ${obs.at}` : ""}]`;
	return "[来源未知]";
}

function describeObservation(entry: SceneEntry): string {
	const { obs } = entry;
	if (obs.value === null || obs.source === "unknown") return `- ${entry.label}: ${entry.unknownText ?? UNKNOWN}`;
	return `- ${entry.label}: ${obs.value}  ${sourceLabel(obs)}`;
}

function renderGroup(entries: readonly SceneEntry[], group: SceneEntry["group"], heading: string): string[] {
	const body = entries.filter((entry) => entry.group === group).map(describeObservation);
	return [heading, ...body];
}

function renderScene(card: IssueCard): string[] {
	const entries = sceneEntries(card);
	const lines: string[] = [
		`\n- 反馈 ID: ${escapeIssueIdentity(card.id)}`,
		`- 来源项目（非敏感标识）: ${escapeIssueIdentity(card.projectLabel)}`,
		`- 短标题: ${card.title}`,
		`- MW 组件/入口: ${card.component.value ?? "待分诊（未定位）"}  ${
			card.component.value === null ? "[来源未知]" : sourceLabel(card.component)
		}`,
	];
	lines.push(...renderGroup(entries, "time", "\n## 现场时间（故障时 / 提交时 / 观察时分开）"));
	lines.push(...renderGroup(entries, "fact", "\n## 触发与现象（报障事实）"));
	lines.push(...renderGroup(entries, "repro", "\n## 复现与影响"));
	lines.push(`- 复现频率: ${card.scene.reproductionFrequency}`);
	lines.push(...renderGroup(entries, "failure-env", "\n## 故障时环境（用户陈述/未知；不得由当前实测替换）"));
	lines.push(
		...renderGroup(
			entries,
			"observed-env",
			`\n## 窗口实测环境（采集时间 ${card.environmentObservedAt.value ?? UNKNOWN}；不代表故障时快照）`,
		),
	);
	lines.push("\n## 诊断片段（仅用户选择、已脱敏；附件仅引用，不上传文件）");
	if (card.diagnostics.length === 0) {
		lines.push(`- ${UNKNOWN}（用户未选择诊断片段）`);
	} else {
		for (const fragment of card.diagnostics) {
			lines.push(`- [${fragment.kind}] id=${fragment.id} [用户选择]: ${fragment.text}`);
		}
	}
	return lines;
}

function renderDevSection(card: IssueCard): string[] {
	const state = latestDevState(card);
	const lines = [
		"\n## 开发进展/反馈（开发侧解释与推测，与报障事实分栏）",
		`- 当前状态: ${state.status}`,
		`- 状态原因/分诊结论: ${state.statusNote}`,
		`- 下一步/受阻原因: ${state.nextAction}`,
		`- 修复提交: ${state.fixCommit}`,
		`- 发布版本: ${state.releaseVersion}`,
		`- 最后更新时间: ${state.updatedAt ?? UNKNOWN}`,
		`- 更新者: ${state.by}`,
		`- 待补充问题: ${state.questionToReporter}`,
		"- 原项目补充回复（追加，不覆盖原始现场）:",
	];
	if (card.devTimeline.length === 0) {
		lines.push(`- 开发进展: ${UNKNOWN}（提交时为空）`);
	} else {
		lines.push("\n### 同一 ID 的开发进展历史（仅历史；当前状态与待补充问题仍以上方投影为准）");
		for (const [index, entry] of card.devTimeline.entries()) {
			lines.push(
				`- #${index + 1} [@ ${entry.at}][${entry.by}] ${entry.status}: ${entry.statusNote || UNKNOWN}`,
				`- #${index + 1} 下一步: ${entry.nextAction ?? UNKNOWN}；修复提交: ${entry.fixCommit ?? UNKNOWN}；发布版本: ${entry.releaseVersion ?? UNKNOWN}；追问: ${entry.questionToReporter ?? UNKNOWN}`,
			);
		}
	}
	if (card.reporterReplies.length === 0) {
		lines.push(`- 回复: ${UNKNOWN}`);
	} else {
		for (const reply of card.reporterReplies) {
			lines.push(`- [@ ${reply.at}][${reply.source}] ${reply.text}`);
		}
	}
	return lines;
}

/** FULL redacted preview: a complete render of exactly the candidate payload.
 * No summary, no truncation — key error text and reproduction steps survive
 * verbatim (after redaction). Shown to the user BEFORE confirmation. */
export function renderPreview(card: IssueCard): string {
	// Idempotent final neutralization: card values are already canonicalized at
	// prepareIssue time, so this is a no-op there and a display-safety net for an
	// out-of-band card. Output is still THE canonical preview bound by
	// previewSha256/confirmation (payload === preview === hash, no A/B split).
	return escapeUntrustedText(
		[
			"# 脱敏预览（将提交的完整内容；确认前仅保存在内存）",
			...renderScene(card),
			...renderDevSection(card),
			"\n说明: 未知项均明示未知；当前实测带采集时间且不与故障时现场混写；本预览即脱敏后的提交内容。",
		].join("\n"),
	);
}

export interface ProjectedFact {
	label: string;
	value: string;
	source: SourceTag;
	at: string | null;
}

export interface UserProjection {
	id: string;
	title: string;
	/** Reporter facts with explicit provenance for machine checks. */
	facts: ProjectedFact[];
	development: DevStateView;
	localEffective: LocalEffectiveResult;
	/** Fully rendered, human-readable projection. */
	text: string;
}

/** User-readable projection for `/mw issue status [ID]`: one-line phenomenon,
 * reproduction/impact, environment with sources, diagnostics, development
 * progress, then the SEPARATE local-effectiveness verdict. */
export function projectForUser(card: IssueCard, evidence: LocalEvidence): UserProjection {
	const facts: ProjectedFact[] = sceneEntries(card).map((entry) => ({
		label: entry.label,
		value: escapeUntrustedText(entry.obs.value ?? entry.unknownText ?? UNKNOWN),
		source: entry.obs.value === null ? "unknown" : entry.obs.source,
		at: entry.obs.at,
	}));
	const development = latestDevState(card);
	const localEffective = evaluateLocalEffective(card, evidence);
	const phenomenon = card.scene.actual.value ?? card.title;
	const text = [
		`# 问题卡 ${escapeIssueIdentity(card.id)} — ${card.title}`,
		"\n## 一句话现象",
		phenomenon,
		...renderScene(card),
		...renderDevSection(card),
		"\n## 本项目使用情况（开发侧状态 ≠ 本地已生效）",
		`- 开发侧状态: ${development.status}（仅权威记录）`,
		`- 本地生效判定: ${localEffective.phrase}（state=${localEffective.state}；${localEffective.reason}）`,
		`- 修复提交: ${development.fixCommit}；发布版本: ${development.releaseVersion}（分开显示）`,
	].join("\n");
	// Idempotent: values are canonical; this keeps the status projection inert on
	// a real terminal even for an out-of-band constructed card.
	return { id: card.id, title: card.title, facts, development, localEffective, text: escapeUntrustedText(text) };
}

export function renderForUser(card: IssueCard, evidence: LocalEvidence): string {
	return projectForUser(card, evidence).text;
}
