/**
 * shared/issue-store.ts — T-03 of key `mw-issue-feedback`: the UNIQUE TS host
 * store for MW product-feedback cards, development progress, reporter replies
 * and each same-machine project's own minimal ID/pending index.
 *
 * Design anchors: `spec.md` AC-001/002/003/004/006; `design.md` D-002, D-003,
 * §2, §4, §5 and §7; DRQ-2's append-only / O_EXCL / client-ID idempotency.
 * This module CONSUMES the accepted pure model (`issue-model.ts`) and the
 * explicit dev-root resolver (`issue-root.ts`); it does not fork their schema,
 * state vocabulary, preview, redaction, projection or root-discovery logic.
 *
 * Physical layout (all paths are derived from validated canonical roots, never
 * from a caller-supplied target file):
 *   <devRepo>/.agenticdoc/mw-issue-feedback/authority/
 *     authority.lock
 *     events/<feedback-id>.jsonl         append-only hash-chained event log
 *   <project>/.agenticdoc/mw-issue-feedback/
 *     index.lock
 *     index.json                        IDs + minimal pending/ack metadata
 *     pending/<feedback-id>.json        confirmed, redacted copy (offline only)
 *
 * Invariants:
 *  - One feedback ID has one authority log, whose FIRST and ONLY `created`
 *    event carries the confirmed redacted card. A same-ID/same-digest replay
 *    appends nothing; a same-ID/different-content replay refuses without
 *    overwriting either authority bytes or a local pending copy.
 *  - Authority writes and local ack are deliberately NOT a cross-file
 *    transaction. Before an authority attempt the local state is `in-flight`;
 *    if the ACK is lost, the user sees `待核实` and the next retry verifies by
 *    ID against the authority before marking `submitted`. An unavailable or
 *    ambiguous authority leaves a confirmed redacted pending copy and says
 *    `未提交`, never `已提交`.
 *  - All authority updates are serialized by a token-owned O_EXCL lock. Every
 *    event carries `seq`, `prev_sha256`, `sha256`, a tz-aware `at`, a trusted
 *    entry `source` and `by`. `dev_update` additionally carries a validated
 *    `DevUpdate`; `reporter_reply` carries a validated `ReporterReply`.
 *  - Any malformed UTF-8/JSON, duplicate JSON key, broken hash chain, wrong
 *    schema/key set, digest mismatch, missing authority row for a submitted
 *    local row, link/junction redirect or out-of-tree path is an explicit
 *    `IssueStoreError`. Corrupt bytes are NEVER filtered, rewritten or repaired.
 *  - Reads by project consult that project's local index FIRST. A foreign ID
 *    is not read from the authority; a no-ID list never enumerates authority
 *    files. When the authority is unavailable, status/list refuse to present
 *    any stale cached development state.
 *  - Writes require a trusted project/dev PM actor, a non-worker environment,
 *    a real confirmation and a canonical root match. This is an MW ENTRY-PATH
 *    gate only: a same-OS-user process that writes these files directly is
 *    outside this module's security guarantee. It is not an OS sandbox or ACL.
 *
 * No service, no network, no cwd discovery, no credential/env scan, no
 * automatic log/source upload, no auto-repair, no ID generation inside the pure
 * model, no cross-machine sync, no installation/restart and no UI wiring.
 * T-04 owns the trusted TUI confirmation and injectable-store command surface.
 */

import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import {
	appendDevUpdate,
	appendReporterReply,
	type Confirmation,
	type ConfirmedFragment,
	type ConfirmedIssue,
	canonicalPayload,
	confirmIssue,
	DEV_STATUSES,
	type DevStateView,
	type DevStatus,
	type DevUpdate,
	type EnvironmentFacts,
	type IssueCard,
	type IssueListRow,
	type IssuePreparation,
	isInstant,
	type LocalEffectiveResult,
	type LocalEvidence,
	latestDevState,
	listIssuesForProject,
	type Observation,
	type ObservedEnvironmentFacts,
	pendingQuestion,
	projectForUser,
	REDACTION_MARK,
	REPRODUCTION_FREQUENCIES,
	type ReporterReply,
	redactSecrets,
	renderPreview,
	SOURCE_TAGS,
	type SourceTag,
	summarizeForList,
	UNKNOWN,
	type UserProjection,
	withQuestionIdentities,
} from "./issue-model.ts";
import {
	formatIssueDevRootFailure,
	type IssueDevRootFailure,
	type IssueDevRootResolved,
	resolveIssueDevRoot,
} from "./issue-root.ts";

// ── Frozen vocabulary and on-disk naming ───────────────────────────────────

export const ISSUE_STORE_SCHEMA = 1;
export const ISSUE_ID_PREFIX = "fb-";
export const ISSUE_ID_PATTERN = /^fb-[0-9a-f]{32}$/;
export const ISSUE_LOCAL_DIR_PARTS = [".agenticdoc", "mw-issue-feedback"] as const;
export const ISSUE_AUTHORITY_DIR_PARTS = [".agenticdoc", "mw-issue-feedback", "authority"] as const;
export const ISSUE_EVENTS_DIR_BASENAME = "events";
export const ISSUE_PENDING_DIR_BASENAME = "pending";
export const ISSUE_LOCAL_INDEX_BASENAME = "index.json";
export const ISSUE_LOCAL_LOCK_BASENAME = "index.lock";
export const ISSUE_AUTHORITY_LOCK_BASENAME = "authority.lock";
export const ISSUE_LOCAL_INDEX_KIND = "mw-issue-local-index";
export const ISSUE_PENDING_COPY_KIND = "mw-issue-pending-copy";
export const ISSUE_AUTHORITY_EVENT_KIND = "mw-issue-authority-event";
export const GENESIS_SHA256 = "0".repeat(64);
export const ZERO_INSTANT = "1970-01-01T00:00:00.000Z";

export const ISSUE_DISPLAY_SUBMITTED = "已提交";
export const ISSUE_DISPLAY_VERIFY_PENDING = "待核实";
export const ISSUE_DISPLAY_NOT_SUBMITTED = "未提交";
export const ISSUE_DISPLAY_CONFLICT = "冲突";
export const ISSUE_DISPLAY_REFUSED = "拒绝";
export const ISSUE_DISPLAY_UNKNOWN = "未知";
export const ISSUE_AUTHORITY_UNAVAILABLE_TEXT = "权威记录入口不可达，状态无法更新";

/** Explicit boundary statement for the command/UI and independent reviewers. */
export const ISSUE_STORE_ENTRY_ONLY_NOTICE =
	"MW entry-path write gate only; it does not stop a same-OS-user process from directly editing the pointer, authority files or a project's local index.";

export const ISSUE_LOCAL_STATES = ["pending", "in-flight", "submitted", "conflict"] as const;
export type IssueLocalState = (typeof ISSUE_LOCAL_STATES)[number];
export type IssueDisplayState = IssueLocalState | "none";

export const ISSUE_LAST_ERROR_KINDS = [
	"unavailable",
	"lock-busy",
	"duplicate-conflict",
	"ack-lost",
	"corrupt",
	"authority-missing",
	"pending-copy-missing",
] as const;
export type IssueLastErrorKind = (typeof ISSUE_LAST_ERROR_KINDS)[number] | null;

export const ISSUE_EVENT_KINDS = ["created", "dev_update", "reporter_reply"] as const;
export type IssueEventKind = (typeof ISSUE_EVENT_KINDS)[number];

export const ISSUE_EVENT_SOURCES = ["project-pm", "dev-pm"] as const;
export type IssueEventSource = (typeof ISSUE_EVENT_SOURCES)[number];

export const ISSUE_ACTOR_ROLES = ["pm", "worker", "unknown"] as const;
export type IssueActorRole = (typeof ISSUE_ACTOR_ROLES)[number];

export const ISSUE_ACTOR_SCOPES = ["project", "dev"] as const;
export type IssueActorScope = (typeof ISSUE_ACTOR_SCOPES)[number];

export const ISSUE_OPERATION_CODES = [
	"submitted",
	"already-submitted",
	"pending",
	"ack-lost",
	"duplicate-conflict",
	"unconfirmed",
	"credential-detected",
	"invalid-input",
	"worker-forbidden",
	"untrusted-window",
	"foreign-project",
	"authority-unavailable",
	"authority-missing",
	"pending-copy-missing",
	"missing-local-record",
	"not-owned",
	"lock-busy",
	"corrupt",
	"written",
	"ok",
] as const;
export type IssueOperationCode = (typeof ISSUE_OPERATION_CODES)[number];

export const ISSUE_STORE_ERROR_CODES = [
	"E-ISSUE-STORE-INVALID_INPUT",
	"E-ISSUE-STORE-CORRUPT",
	"E-ISSUE-STORE-LOCK_BUSY",
	"E-ISSUE-STORE-LOCK_RELEASE_FAILED",
	"E-ISSUE-STORE-WRITE_FAILED",
	"E-ISSUE-STORE-AUTHORITY_MISSING",
] as const;
export type IssueStoreErrorCode = (typeof ISSUE_STORE_ERROR_CODES)[number];

/** Hard integrity / I/O failures. Business refusals use structured results. */
export class IssueStoreError extends Error {
	readonly code: IssueStoreErrorCode;
	readonly target: string | null;

	constructor(code: IssueStoreErrorCode, message: string, target: string | null = null) {
		super(`${code}: ${message}${target === null ? "" : ` (${target})`}`);
		this.name = "IssueStoreError";
		this.code = code;
		this.target = target;
	}
}

// ── Public request / actor contracts (T-04 consumes this frozen surface) ───

/** Host-observed actor facts. `role`, `trustedWindow` and `writeAuthorized`
 * are NOT model claims and are not OS authentication: T-04 passes them only
 * after a real TUI confirmation in a PM window. `PI_WORKER_TASK` is checked by
 * the store independently so a worker cannot self-promote with actor fields. */
export interface IssueStoreActor {
	role: IssueActorRole;
	scope: IssueActorScope;
	projectRoot: string;
	projectLabel: string;
	by: string;
	trustedWindow: boolean;
	writeAuthorized: boolean;
}

export interface IssueLockOptions {
	retries?: number;
	baseDelayMs?: number;
}

export interface IssueAuthorityCommit {
	event: IssueAuthorityEvent;
	created: boolean;
	verifiedById: boolean;
}

/** Deterministic fault seams for offline fixtures. Production leaves these
 * undefined; all locks, real file reads/writes and strict parsers still run. */
export interface IssueStoreHooks {
	afterAuthorityCommit?: (commit: IssueAuthorityCommit) => void;
	beforeLocalAck?: (commit: IssueAuthorityCommit) => void;
}

export interface IssueStoreOptions {
	/** Absolute current-project root. No cwd fallback and no caller path. */
	projectRoot: string;
	/** Injected for offline fixtures; worker detection uses the SAME env. */
	env?: NodeJS.ProcessEnv;
	home?: string;
	pointerFile?: string;
	crossCheckRoots?: readonly string[];
	lockOptions?: IssueLockOptions;
	hooks?: IssueStoreHooks;
}

export interface IssueSubmitRequest {
	actor: IssueStoreActor;
	/** The complete model preparation shown to the user, never an IssueDraft. */
	preparation: IssuePreparation;
	/** Real TUI confirmation of the full redacted preview. */
	confirmation: Confirmation;
	/** Transient known secrets for fail-closed verification; NEVER persisted. */
	knownSecrets?: readonly string[];
}

export interface IssueRetryRequest {
	actor: IssueStoreActor;
	id: string;
}

export interface IssueProgressFields {
	status: DevStatus;
	statusNote: string;
	nextAction: string | null;
	fixCommit: string | null;
	releaseVersion: string | null;
	questionToReporter: string | null;
}

export interface IssueProgressRequest {
	actor: IssueStoreActor;
	id: string;
	update: IssueProgressFields;
	/** Complete redacted preview of exactly the fields written. */
	preview: string;
	confirmation: Confirmation;
	knownSecrets?: readonly string[];
}

export interface IssueReplyFields {
	text: string;
	/** Project replies are confirmed user statements, not window guesses. */
	source: SourceTag;
	inReplyTo: string | null;
}

export interface IssueReplyRequest {
	actor: IssueStoreActor;
	id: string;
	reply: IssueReplyFields;
	preview: string;
	confirmation: Confirmation;
	knownSecrets?: readonly string[];
}

export interface IssueStatusRequest {
	actor: IssueStoreActor;
	id: string;
	/** T-04 supplies real local evidence; absent means explicit unknown. */
	localEvidence?: LocalEvidence;
}

export interface IssueListRequest {
	actor: IssueStoreActor;
}

// ── Public record contracts ─────────────────────────────────────────────────

export interface IssueAuthorityAck {
	seq: number;
	event_sha256: string;
	at: string;
	verified_at: string;
}

export interface IssueLocalRecord {
	id: string;
	submission_digest: string;
	card_sha256: string;
	project_label: string;
	state: IssueLocalState;
	attempts: number;
	created_at: string;
	updated_at: string;
	last_error_kind: IssueLastErrorKind;
	authority_ack: IssueAuthorityAck | null;
}

export interface IssueLocalIndex {
	schema: 1;
	kind: "mw-issue-local-index";
	project_fingerprint: string;
	updated_at: string;
	records: IssueLocalRecord[];
}

export interface IssuePendingCopy {
	schema: 1;
	kind: "mw-issue-pending-copy";
	id: string;
	submission_digest: string;
	card_sha256: string;
	preview_sha256: string;
	confirmed_at: string;
	confirmed_by: string;
	project_label: string;
	card: IssueCard;
}

interface IssueEventBase {
	schema: 1;
	kind: IssueEventKind;
	id: string;
	seq: number;
	prev_sha256: string;
	sha256: string;
	submission_digest: string;
	project_label: string;
	at: string;
	source: IssueEventSource;
	by: string;
}

export interface IssueCreatedEvent extends IssueEventBase {
	kind: "created";
	card_sha256: string;
	preview_sha256: string;
	confirmed_at: string;
	confirmed_by: string;
	card: IssueCard;
}

export interface IssueDevUpdateEvent extends IssueEventBase {
	kind: "dev_update";
	update: DevUpdate;
}

export interface IssueReporterReplyEvent extends IssueEventBase {
	kind: "reporter_reply";
	reply: ReporterReply;
}

export type IssueAuthorityEvent = IssueCreatedEvent | IssueDevUpdateEvent | IssueReporterReplyEvent;
export type IssueAuthorityEventDraft =
	| Omit<IssueCreatedEvent, "sha256">
	| Omit<IssueDevUpdateEvent, "sha256">
	| Omit<IssueReporterReplyEvent, "sha256">;

export interface IssueAuthorityState {
	exists: boolean;
	id: string;
	events: IssueAuthorityEvent[];
	created: IssueCreatedEvent | null;
	card: IssueCard | null;
	submissionDigest: string | null;
	cardSha256: string | null;
	projectLabel: string | null;
	lastSha256: string;
	lastSeq: number;
}

interface IssueOperationBase {
	ok: boolean;
	code: IssueOperationCode;
	id: string;
	state: IssueDisplayState;
	submitted: boolean;
	authorityReachable: boolean;
	display: string;
	message: string;
	reason: string;
	attempts: number;
	rootFailure: IssueDevRootFailure | null;
}

export interface IssueSubmitResult extends IssueOperationBase {
	created: boolean;
	verifiedById: boolean;
	event: IssueAuthorityEvent | null;
	localRecord: IssueLocalRecord | null;
}

export interface IssueMutationResult {
	ok: boolean;
	code: IssueOperationCode;
	id: string;
	authorityReachable: boolean;
	message: string;
	reason: string;
	event: IssueAuthorityEvent | null;
	card: IssueCard | null;
	seq: number;
	rootFailure: IssueDevRootFailure | null;
}

export interface IssueStoreListRow extends IssueListRow {
	localState: IssueLocalState;
	submitted: boolean;
	authorityVerified: boolean;
}

export interface IssueListResult {
	ok: boolean;
	code: IssueOperationCode;
	authorityReachable: boolean;
	rows: IssueStoreListRow[];
	message: string;
	reason: string;
	rootFailure: IssueDevRootFailure | null;
}

export interface IssueStatusResult {
	ok: boolean;
	code: IssueOperationCode;
	id: string;
	authorityReachable: boolean;
	authorityVerifiedById: boolean;
	localAck: boolean;
	localState: IssueDisplayState;
	submitted: boolean;
	display: string;
	message: string;
	reason: string;
	text: string;
	localRecord: IssueLocalRecord | null;
	card: IssueCard | null;
	projection: UserProjection | null;
	development: DevStateView | null;
	pendingQuestion: string | null;
	localEffective: LocalEffectiveResult | null;
	events: IssueAuthorityEvent[];
	rootFailure: IssueDevRootFailure | null;
}

// ── Dev-authority incoming read (T-09B, D002): dev-window only, pure read ──

/** Explicitly typed requests for the dev authority's own inbox. They are NOT
 * IssueListRequest/IssueStatusRequest: an incoming read must never carry (or
 * fabricate) localEvidence, a project local index, an ACK or a local state. */
export interface IssueIncomingListRequest {
	actor: IssueStoreActor;
}

export interface IssueIncomingReadRequest {
	actor: IssueStoreActor;
	id: string;
}

export type IssueIncomingCode =
	| "ok"
	| "invalid-input"
	| "worker-forbidden"
	| "untrusted-window"
	| "foreign-project"
	| "authority-unavailable"
	| "authority-missing"
	| "corrupt";

/** One row of the dev authority's events directory. `needsReply` comes from
 * the model's stable dev_update.sha256 question identity, never from the last
 * dev update's questionToReporter field. No localState/submitted/ACK columns:
 * the dev window has no evidence about any project's installed artifact. */
export interface IssueIncomingRow extends IssueListRow {
	projectLabel: string;
}

export interface IssueIncomingListResult {
	ok: boolean;
	code: IssueIncomingCode;
	rows: IssueIncomingRow[];
	message: string;
	reason: string;
	rootFailure: IssueDevRootFailure | null;
}

export interface IssueIncomingReadResult {
	ok: boolean;
	code: IssueIncomingCode;
	id: string;
	message: string;
	reason: string;
	/** Complete, control-neutralized card render + explicit pending question.
	 * No local-effectiveness claim: dev status is never any project's install. */
	text: string;
	projectLabel: string | null;
	/** In-memory replay ONLY (carries the store's questionEventHashes
	 * projection). Never persisted: JSON.stringify of a replayed card WOULD
	 * include that enumerable projection, so no digest/preview/persistence path
	 * may consume this card as canonical bytes. */
	card: IssueCard | null;
	events: IssueAuthorityEvent[];
	development: DevStateView | null;
	/** Explicit single newest unanswered question by event sha256. */
	pendingQuestion: string | null;
	rootFailure: IssueDevRootFailure | null;
}

// ── Generic helpers ─────────────────────────────────────────────────────────

function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

/** Stable, key-sorted serialization for event hash chains (NOT the model's
 * insertion-order `canonicalPayload`, which is used for the card digest). */
function stableStringify(value: unknown): string {
	if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
	if (Array.isArray(value)) return `[${value.map((item) => stableStringify(item)).join(",")}]`;
	const obj = value as Record<string, unknown>;
	return `{${Object.keys(obj)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${stableStringify(obj[key])}`)
		.join(",")}}`;
}

export function issueTextSha256(text: string): string {
	return sha256(text);
}

/** The model's 16-hex submission digest, recomputed from the canonical card. */
export function issueSubmissionDigest(card: IssueCard): string {
	return sha256(canonicalPayload(card)).slice(0, 16);
}

export function issueCardSha256(card: IssueCard): string {
	return sha256(canonicalPayload(card));
}

export function newIssueId(): string {
	return `${ISSUE_ID_PREFIX}${randomUUID().replaceAll("-", "")}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonblank(value: unknown): value is string {
	return typeof value === "string" && value.trim() !== "";
}

function includesClosed<T extends string>(values: readonly T[], value: unknown): value is T {
	return typeof value === "string" && (values as readonly string[]).includes(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
	const actual = Object.keys(value).sort();
	const wanted = [...expected].sort();
	return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}

function isHex(value: unknown, length: number): value is string {
	return typeof value === "string" && new RegExp(`^[0-9a-f]{${length}}$`).test(value);
}

export function isIssueId(value: unknown): value is string {
	return typeof value === "string" && ISSUE_ID_PATTERN.test(value);
}

/** Strict events-directory basename: a stray file, a link or a directory is an
 * explicit error, never a silently filtered row of an \"complete\" list. */
const ISSUE_INCOMING_LOG_RE = /^(fb-[0-9a-f]{32})\.jsonl$/;

function isInstantValue(value: unknown): value is string {
	return typeof value === "string" && isInstant(value);
}

function isNullableInstant(value: unknown): value is string | null {
	return value === null || isInstantValue(value);
}

function isSafeInteger(value: unknown, minimum: number): value is number {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum;
}

function nullableText(value: unknown): value is string | null {
	return value === null || typeof value === "string";
}

function corrupt(message: string, target: string): never {
	throw new IssueStoreError("E-ISSUE-STORE-CORRUPT", message, target);
}

function invalid(message: string, target: string | null = null): never {
	throw new IssueStoreError("E-ISSUE-STORE-INVALID_INPUT", message, target);
}

function nodeErrorCode(error: unknown): string | null {
	if (typeof error !== "object" || error === null || !("code" in error)) return null;
	const code = (error as { code?: unknown }).code;
	return typeof code === "string" ? code : null;
}

function errorText(error: unknown): string {
	return error instanceof Error ? error.message : String(error);
}

/** Authority write-entry failures that occur before any event can be appended.
 * Only these preflight I/O failures may degrade a confirmed submission to a
 * local pending copy; CORRUPT/conflict/ACK-loss errors stay visible. */
const AUTHORITY_PREFLIGHT_IO_CODES = new Set(["EACCES", "EPERM", "EROFS", "ENOSPC", "EIO"]);
const authorityPreflightFailures = new WeakSet<object>();

function markAuthorityPreflight(error: unknown): void {
	if (typeof error === "object" && error !== null) authorityPreflightFailures.add(error);
}

function isAuthorityPreflightFailure(error: unknown): boolean {
	return typeof error === "object" && error !== null && authorityPreflightFailures.has(error);
}

function isAuthorityPreflightIoFailure(error: unknown): boolean {
	if (error instanceof IssueStoreError && error.code === "E-ISSUE-STORE-CORRUPT") return false;
	const code = nodeErrorCode(error);
	return code !== null && AUTHORITY_PREFLIGHT_IO_CODES.has(code);
}

function redactionMarkerNeutralized(text: string): string {
	const escapedMarker = REDACTION_MARK.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	const assignment =
		"\\b(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|password|passwd|pwd|secret|client[_-]?secret|authorization)\\s*[:=]\\s*";
	return text.replace(new RegExp(`(${assignment})${escapedMarker}`, "gi"), "redacted-assignment-marker");
}

/** `redactSecrets` runs high-confidence pattern rules even with an empty
 * known-secret list. JSON escaping would hide a caller-known credential that
 * contains a quote, backslash or newline, so check raw string leaves and keys
 * before the serialized-object check. The exact completed-redaction marker is
 * neutralized in both forms; ordinary control characters are not credentials. */
function hasNoSecrets(value: unknown, knownSecrets: readonly string[]): boolean {
	const seen = new Set<object>();
	const rawTextIsClean = (text: string): boolean =>
		redactSecrets(redactionMarkerNeutralized(text), knownSecrets).redactions === 0;
	const visit = (node: unknown): boolean => {
		if (typeof node === "string") return rawTextIsClean(node);
		if (node === null || typeof node !== "object") return true;
		if (seen.has(node)) return true;
		seen.add(node);
		if (Array.isArray(node)) return node.every(visit);
		for (const [key, child] of Object.entries(node)) {
			if (!rawTextIsClean(key) || !visit(child)) return false;
		}
		return true;
	};
	if (!visit(value)) return false;
	const serialized = redactionMarkerNeutralized(stableStringify(value));
	return redactSecrets(serialized, knownSecrets).redactions === 0;
}

function assertStoredNoSecrets(value: unknown, label: string, target: string): void {
	if (!hasNoSecrets(value, [])) corrupt(`${label} contains credential-shaped text`, target);
}

// ── Canonical path safety: no cwd, no caller target, no link/junction escape ─

function stripDevicePrefix(value: string): string {
	if (process.platform !== "win32") return value;
	if (value.startsWith("\\\\?\\UNC\\")) return `\\\\${value.slice(8)}`;
	if (value.startsWith("\\\\?\\")) return value.slice(4);
	return value;
}

function fold(value: string): string {
	const normalized = path.normalize(stripDevicePrefix(value));
	return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

function isInside(root: string, candidate: string): boolean {
	const foldedRoot = fold(root).replace(/[\\/]+$/, "");
	const foldedCandidate = fold(candidate);
	return foldedCandidate === foldedRoot || foldedCandidate.startsWith(`${foldedRoot}${path.sep}`);
}

function canonicalDir(raw: string): string {
	if (typeof raw !== "string" || !path.isAbsolute(raw)) invalid("root must be an absolute path");
	const normalized = stripDevicePrefix(path.normalize(raw));
	try {
		const stat = fs.statSync(normalized);
		if (!stat.isDirectory()) invalid("root is not a directory", normalized);
	} catch (error) {
		if (nodeErrorCode(error) === "ENOENT") invalid("root does not exist", normalized);
		throw error;
	}
	const canonical = stripDevicePrefix(fs.realpathSync.native(normalized));
	if (!path.isAbsolute(canonical)) invalid("root canonicalization was not absolute", normalized);
	return canonical;
}

function assertSafeSegment(segment: string): void {
	if (!/^[A-Za-z0-9._-]+$/.test(segment) || segment === "." || segment === "..") {
		invalid(`unsafe path segment: ${segment}`);
	}
}

/** Validate each existing segment without following links out of the canonical
 * root. `create` is true only on a write path; read paths never mkdir. */
function validateSafeDirectory(root: string, parts: readonly string[], create: boolean): string | null {
	const canonicalRoot = canonicalDir(root);
	let cursor = canonicalRoot;
	for (const part of parts) {
		assertSafeSegment(part);
		cursor = path.join(cursor, part);
		let stat: fs.Stats;
		try {
			stat = fs.lstatSync(cursor);
		} catch (error) {
			if (nodeErrorCode(error) !== "ENOENT") throw error;
			if (!create) return null;
			try {
				fs.mkdirSync(cursor);
				stat = fs.lstatSync(cursor);
			} catch (mkdirError) {
				if (nodeErrorCode(mkdirError) !== "EEXIST") throw mkdirError;
				stat = fs.lstatSync(cursor);
			}
		}
		if (stat.isSymbolicLink() || !stat.isDirectory()) {
			corrupt("directory segment is a symbolic link/junction or non-directory", cursor);
		}
		const real = stripDevicePrefix(fs.realpathSync.native(cursor));
		if (!isInside(canonicalRoot, real)) corrupt("directory segment resolves outside its root", cursor);
	}
	return cursor;
}

function assertSafeRegularFile(parent: string, file: string): boolean {
	if (!fs.existsSync(parent)) return false;
	let stat: fs.Stats;
	try {
		stat = fs.lstatSync(file);
	} catch (error) {
		if (nodeErrorCode(error) === "ENOENT") return false;
		throw error;
	}
	if (stat.isSymbolicLink() || !stat.isFile()) corrupt("target is a symbolic link/junction or non-file", file);
	let real: string;
	try {
		real = stripDevicePrefix(fs.realpathSync.native(file));
	} catch (error) {
		if (nodeErrorCode(error) === "ENOENT") return false;
		throw error;
	}
	if (!isInside(parent, real)) corrupt("target resolves outside its parent", file);
	return true;
}

export function issueLocalBasePath(projectRoot: string): string {
	return path.join(canonicalDir(projectRoot), ...ISSUE_LOCAL_DIR_PARTS);
}

export function issueLocalIndexPath(projectRoot: string): string {
	return path.join(issueLocalBasePath(projectRoot), ISSUE_LOCAL_INDEX_BASENAME);
}

export function issueLocalLockPath(projectRoot: string): string {
	return path.join(issueLocalBasePath(projectRoot), ISSUE_LOCAL_LOCK_BASENAME);
}

export function issuePendingCopyPath(projectRoot: string, id: string): string {
	if (!isIssueId(id)) invalid("feedback ID must be fb- plus 32 lowercase hex characters", id);
	return path.join(issueLocalBasePath(projectRoot), ISSUE_PENDING_DIR_BASENAME, `${id}.json`);
}

export function issueAuthorityBasePath(devRoot: string): string {
	return path.join(canonicalDir(devRoot), ...ISSUE_AUTHORITY_DIR_PARTS);
}

export function issueAuthorityLockPath(devRoot: string): string {
	return path.join(issueAuthorityBasePath(devRoot), ISSUE_AUTHORITY_LOCK_BASENAME);
}

export function issueAuthorityLogPath(devRoot: string, id: string): string {
	if (!isIssueId(id)) invalid("feedback ID must be fb- plus 32 lowercase hex characters", id);
	return path.join(issueAuthorityBasePath(devRoot), ISSUE_EVENTS_DIR_BASENAME, `${id}.jsonl`);
}

// ── Strict JSON: UTF-8, LF, duplicate keys, no BOM and no silent repair ─────

interface JsonObjectFrame {
	object: boolean;
	keys: Set<string>;
	expectKey: boolean;
}

/** Reject duplicate object keys anywhere in a document. JSON.parse resolves
 * duplicates by last-wins; this scanner makes those bytes fail explicitly. */
function findDuplicateJsonKey(raw: string): string | null {
	const stack: JsonObjectFrame[] = [];
	let index = 0;
	while (index < raw.length) {
		const char = raw[index];
		if (char === '"') {
			let end = index + 1;
			let escaped = false;
			for (; end < raw.length; end += 1) {
				if (escaped) escaped = false;
				else if (raw[end] === "\\") escaped = true;
				else if (raw[end] === '"') break;
			}
			let token: string | null = null;
			try {
				const parsed: unknown = JSON.parse(raw.slice(index, end + 1));
				if (typeof parsed === "string") token = parsed;
			} catch {
				token = null;
			}
			const frame = stack.length > 0 ? stack[stack.length - 1] : null;
			if (token !== null && frame !== null && frame.object && frame.expectKey) {
				if (frame.keys.has(token)) return token;
				frame.keys.add(token);
				frame.expectKey = false;
			}
			index = end + 1;
			continue;
		}
		if (char === "{" || char === "[") {
			stack.push({ object: char === "{", keys: new Set<string>(), expectKey: char === "{" });
		} else if (char === "}" || char === "]") {
			stack.pop();
		} else if (char === "," && stack.length > 0 && stack[stack.length - 1].object) {
			stack[stack.length - 1].expectKey = true;
		}
		index += 1;
	}
	return null;
}

function parseJsonDocument(raw: string, target: string): unknown {
	if (raw.charCodeAt(0) === 0xfeff) corrupt("UTF-8 BOM is not allowed", target);
	if (raw.includes("\r")) corrupt("CR/CRLF is not allowed: LF-only UTF-8 JSON required", target);
	if (!raw.endsWith("\n")) corrupt("JSON document must end with exactly one LF", target);
	const duplicate = findDuplicateJsonKey(raw);
	if (duplicate !== null) corrupt(`duplicate JSON object key: ${duplicate}`, target);
	try {
		const parsed: unknown = JSON.parse(raw);
		return parsed;
	} catch (error) {
		corrupt(`invalid JSON: ${errorText(error)}`, target);
	}
}

function readStrictJsonFile(file: string, parent: string): unknown | null {
	if (!assertSafeRegularFile(parent, file)) return null;
	const raw = fs.readFileSync(file, "utf8");
	return parseJsonDocument(raw, file);
}

function parseText(value: unknown, label: string, target: string): string {
	if (typeof value !== "string") corrupt(`${label} must be a string`, target);
	return value;
}

function parseNonblank(value: unknown, label: string, target: string): string {
	if (!nonblank(value)) corrupt(`${label} must be a nonblank string`, target);
	return value;
}

function parseNullableText(value: unknown, label: string, target: string): string | null {
	if (!nullableText(value)) corrupt(`${label} must be a string or null`, target);
	return value;
}

function parseInstant(value: unknown, label: string, target: string): string {
	if (!isInstantValue(value)) corrupt(`${label} must be a tz-aware ISO instant`, target);
	return value;
}

function parseNullableInstant(value: unknown, label: string, target: string): string | null {
	if (!isNullableInstant(value)) corrupt(`${label} must be null or a tz-aware ISO instant`, target);
	return value;
}

function parseHex(value: unknown, length: number, label: string, target: string): string {
	if (!isHex(value, length)) corrupt(`${label} must be ${length} lowercase hex characters`, target);
	return value;
}

function parseClosed<T extends string>(value: unknown, values: readonly T[], label: string, target: string): T {
	if (!includesClosed(values, value)) corrupt(`${label} has an unknown value`, target);
	return value;
}

// ── Strict parsing of the accepted model's on-disk shapes ─────────────────

const TIME_OBSERVATION_SOURCES = ["user", "unknown"] as const;
const OBSERVED_TIME_SOURCES = ["observed", "unknown"] as const;
const ENVIRONMENT_SOURCES = ["user", "unknown"] as const;
const OBSERVED_ENVIRONMENT_SOURCES = ["observed", "unknown"] as const;
const DIAGNOSTIC_KINDS = ["log", "error", "attachment-ref"] as const;

function parseObservation(
	value: unknown,
	label: string,
	target: string,
	allowedSources: readonly SourceTag[],
	timeValue = false,
): Observation {
	if (!isRecord(value) || !hasExactKeys(value, ["value", "source", "at"])) {
		corrupt(`${label} must have exactly value/source/at`, target);
	}
	const observedValue = parseNullableText(value.value, `${label}.value`, target);
	const source = parseClosed(value.source, allowedSources, `${label}.source`, target);
	const at = parseNullableInstant(value.at, `${label}.at`, target);
	if (source === "unknown" && (observedValue !== null || at !== null)) {
		corrupt(`${label} unknown observation must be null/null`, target);
	}
	if (source === "observed" && (observedValue === null || at === null)) {
		corrupt(`${label} observed observation needs a value and tz-aware time`, target);
	}
	if (source === "user" && observedValue === null) corrupt(`${label} user observation needs a value`, target);
	if (timeValue && observedValue !== null && !isInstant(observedValue)) {
		corrupt(`${label} time observation must be null or a tz-aware ISO instant`, target);
	}
	return { value: observedValue, source, at };
}

function parseEnvironmentFacts(value: unknown, label: string, target: string): EnvironmentFacts {
	if (!isRecord(value) || !hasExactKeys(value, ["mwVersion", "piVersion", "platform", "windowType"])) {
		corrupt(`${label} must have exactly four observation fields`, target);
	}
	return {
		mwVersion: parseObservation(value.mwVersion, `${label}.mwVersion`, target, ENVIRONMENT_SOURCES),
		piVersion: parseObservation(value.piVersion, `${label}.piVersion`, target, ENVIRONMENT_SOURCES),
		platform: parseObservation(value.platform, `${label}.platform`, target, ENVIRONMENT_SOURCES),
		windowType: parseObservation(value.windowType, `${label}.windowType`, target, ENVIRONMENT_SOURCES),
	};
}

function parseObservedEnvironmentFacts(value: unknown, label: string, target: string): ObservedEnvironmentFacts {
	if (
		!isRecord(value) ||
		!hasExactKeys(value, ["mwVersion", "piVersion", "platform", "windowType", "bundleStatus", "serveStatus"])
	) {
		corrupt(`${label} must have exactly six observation fields`, target);
	}
	return {
		mwVersion: parseObservation(value.mwVersion, `${label}.mwVersion`, target, OBSERVED_ENVIRONMENT_SOURCES),
		piVersion: parseObservation(value.piVersion, `${label}.piVersion`, target, OBSERVED_ENVIRONMENT_SOURCES),
		platform: parseObservation(value.platform, `${label}.platform`, target, OBSERVED_ENVIRONMENT_SOURCES),
		windowType: parseObservation(value.windowType, `${label}.windowType`, target, OBSERVED_ENVIRONMENT_SOURCES),
		bundleStatus: parseObservation(value.bundleStatus, `${label}.bundleStatus`, target, OBSERVED_ENVIRONMENT_SOURCES),
		serveStatus: parseObservation(value.serveStatus, `${label}.serveStatus`, target, OBSERVED_ENVIRONMENT_SOURCES),
	};
}

function parseConfirmedFragment(value: unknown, label: string, target: string): ConfirmedFragment {
	if (!isRecord(value) || !hasExactKeys(value, ["id", "kind", "text", "source"])) {
		corrupt(`${label} must have exactly id/kind/text/source`, target);
	}
	const kind = parseClosed(value.kind, DIAGNOSTIC_KINDS, `${label}.kind`, target);
	const source = parseClosed(value.source, SOURCE_TAGS, `${label}.source`, target);
	if (source !== "user") corrupt(`${label} must come from a confirmed user selection`, target);
	return {
		id: parseNonblank(value.id, `${label}.id`, target),
		kind,
		text: parseText(value.text, `${label}.text`, target),
		source,
	};
}

function parseDevUpdate(value: unknown, label: string, target: string): DevUpdate {
	if (
		!isRecord(value) ||
		!hasExactKeys(value, [
			"at",
			"by",
			"status",
			"statusNote",
			"nextAction",
			"fixCommit",
			"releaseVersion",
			"questionToReporter",
		])
	) {
		corrupt(`${label} has an unknown or missing field`, target);
	}
	const update: DevUpdate = {
		at: parseInstant(value.at, `${label}.at`, target),
		by: parseNonblank(value.by, `${label}.by`, target),
		status: parseClosed(value.status, DEV_STATUSES, `${label}.status`, target),
		statusNote: parseText(value.statusNote, `${label}.statusNote`, target),
		nextAction: parseNullableText(value.nextAction, `${label}.nextAction`, target),
		fixCommit: parseNullableText(value.fixCommit, `${label}.fixCommit`, target),
		releaseVersion: parseNullableText(value.releaseVersion, `${label}.releaseVersion`, target),
		questionToReporter: parseNullableText(value.questionToReporter, `${label}.questionToReporter`, target),
	};
	assertStoredNoSecrets(update, label, target);
	return update;
}

function parseReporterReply(value: unknown, label: string, target: string): ReporterReply {
	if (!isRecord(value) || !hasExactKeys(value, ["at", "text", "source", "inReplyTo"])) {
		corrupt(`${label} must have exactly at/text/source/inReplyTo`, target);
	}
	const reply: ReporterReply = {
		at: parseInstant(value.at, `${label}.at`, target),
		text: parseNonblank(value.text, `${label}.text`, target),
		source: parseClosed(value.source, SOURCE_TAGS, `${label}.source`, target),
		inReplyTo: parseNullableText(value.inReplyTo, `${label}.inReplyTo`, target),
	};
	assertStoredNoSecrets(reply, label, target);
	return reply;
}

function parseIssueCard(value: unknown, label: string, target: string, checkStoredSecrets = true): IssueCard {
	if (
		!isRecord(value) ||
		!hasExactKeys(value, [
			"schema",
			"id",
			"title",
			"projectLabel",
			"component",
			"occurredAt",
			"submittedAt",
			"environmentObservedAt",
			"scene",
			"diagnostics",
			"devTimeline",
			"reporterReplies",
		])
	) {
		corrupt(`${label} has an unknown or missing field`, target);
	}
	if (value.schema !== ISSUE_STORE_SCHEMA) corrupt(`${label}.schema must be 1`, target);
	const id = parseNonblank(value.id, `${label}.id`, target);
	if (!isIssueId(id)) corrupt(`${label}.id must be fb- plus 32 lowercase hex characters`, target);
	if (
		!isRecord(value.scene) ||
		!hasExactKeys(value.scene, [
			"trigger",
			"precondition",
			"expected",
			"actual",
			"impact",
			"reproductionSteps",
			"reproductionFrequency",
			"errorExcerpt",
			"environmentAtFailure",
			"observedEnvironment",
		])
	) {
		corrupt(`${label}.scene has an unknown or missing field`, target);
	}
	if (!Array.isArray(value.diagnostics)) corrupt(`${label}.diagnostics must be an array`, target);
	const diagnostics: ConfirmedFragment[] = value.diagnostics.map((fragment, index) =>
		parseConfirmedFragment(fragment, `${label}.diagnostics[${index}]`, target),
	);
	const diagnosticIds = new Set<string>();
	for (const fragment of diagnostics) {
		if (diagnosticIds.has(fragment.id)) corrupt(`${label} has duplicate diagnostic IDs`, target);
		diagnosticIds.add(fragment.id);
	}
	if (!Array.isArray(value.devTimeline)) corrupt(`${label}.devTimeline must be an array`, target);
	if (!Array.isArray(value.reporterReplies)) corrupt(`${label}.reporterReplies must be an array`, target);
	const card: IssueCard = {
		schema: ISSUE_STORE_SCHEMA,
		id,
		title: parseNonblank(value.title, `${label}.title`, target),
		projectLabel: parseNonblank(value.projectLabel, `${label}.projectLabel`, target),
		component: parseObservation(value.component, `${label}.component`, target, SOURCE_TAGS),
		occurredAt: parseObservation(value.occurredAt, `${label}.occurredAt`, target, TIME_OBSERVATION_SOURCES, true),
		submittedAt: parseObservation(value.submittedAt, `${label}.submittedAt`, target, OBSERVED_TIME_SOURCES, true),
		environmentObservedAt: parseObservation(
			value.environmentObservedAt,
			`${label}.environmentObservedAt`,
			target,
			OBSERVED_TIME_SOURCES,
			true,
		),
		scene: {
			trigger: parseObservation(value.scene.trigger, `${label}.scene.trigger`, target, SOURCE_TAGS),
			precondition: parseObservation(value.scene.precondition, `${label}.scene.precondition`, target, SOURCE_TAGS),
			expected: parseObservation(value.scene.expected, `${label}.scene.expected`, target, SOURCE_TAGS),
			actual: parseObservation(value.scene.actual, `${label}.scene.actual`, target, SOURCE_TAGS),
			impact: parseObservation(value.scene.impact, `${label}.scene.impact`, target, SOURCE_TAGS),
			reproductionSteps: parseObservation(
				value.scene.reproductionSteps,
				`${label}.scene.reproductionSteps`,
				target,
				SOURCE_TAGS,
			),
			reproductionFrequency: parseClosed(
				value.scene.reproductionFrequency,
				REPRODUCTION_FREQUENCIES,
				`${label}.scene.reproductionFrequency`,
				target,
			),
			errorExcerpt: parseObservation(value.scene.errorExcerpt, `${label}.scene.errorExcerpt`, target, SOURCE_TAGS),
			environmentAtFailure: parseEnvironmentFacts(
				value.scene.environmentAtFailure,
				`${label}.scene.environmentAtFailure`,
				target,
			),
			observedEnvironment: parseObservedEnvironmentFacts(
				value.scene.observedEnvironment,
				`${label}.scene.observedEnvironment`,
				target,
			),
		},
		diagnostics,
		devTimeline: value.devTimeline.map((update, index) =>
			parseDevUpdate(update, `${label}.devTimeline[${index}]`, target),
		),
		reporterReplies: value.reporterReplies.map((reply, index) =>
			parseReporterReply(reply, `${label}.reporterReplies[${index}]`, target),
		),
	};
	if (checkStoredSecrets) assertStoredNoSecrets(card, label, target);
	return card;
}

function assertFreshCard(card: IssueCard, target: string): void {
	if (card.devTimeline.length !== 0 || card.reporterReplies.length !== 0) {
		corrupt("created card must contain only the confirmed scene", target);
	}
}

// ── Per-project local index and confirmed redacted pending copy ─────────────

function projectFingerprint(root: string): string {
	return sha256(fold(canonicalDir(root)));
}

function emptyLocalIndex(root: string): IssueLocalIndex {
	return {
		schema: ISSUE_STORE_SCHEMA,
		kind: ISSUE_LOCAL_INDEX_KIND,
		project_fingerprint: projectFingerprint(root),
		updated_at: ZERO_INSTANT,
		records: [],
	};
}

function parseLocalAck(value: unknown, target: string): IssueAuthorityAck | null {
	if (value === null) return null;
	if (!isRecord(value) || !hasExactKeys(value, ["seq", "event_sha256", "at", "verified_at"])) {
		corrupt("authority_ack has an unknown or missing field", target);
	}
	if (!isSafeInteger(value.seq, 1)) corrupt("authority_ack.seq must be a positive integer", target);
	return {
		seq: value.seq,
		event_sha256: parseHex(value.event_sha256, 64, "authority_ack.event_sha256", target),
		at: parseInstant(value.at, "authority_ack.at", target),
		verified_at: parseInstant(value.verified_at, "authority_ack.verified_at", target),
	};
}

function parseLocalRecord(value: unknown, label: string, target: string): IssueLocalRecord {
	if (
		!isRecord(value) ||
		!hasExactKeys(value, [
			"id",
			"submission_digest",
			"card_sha256",
			"project_label",
			"state",
			"attempts",
			"created_at",
			"updated_at",
			"last_error_kind",
			"authority_ack",
		])
	) {
		corrupt(`${label} has an unknown or missing field`, target);
	}
	const id = parseNonblank(value.id, `${label}.id`, target);
	if (!isIssueId(id)) corrupt(`${label}.id must be fb- plus 32 lowercase hex characters`, target);
	if (!isSafeInteger(value.attempts, 0)) corrupt(`${label}.attempts must be a non-negative integer`, target);
	const lastError =
		value.last_error_kind === null
			? null
			: parseClosed(value.last_error_kind, ISSUE_LAST_ERROR_KINDS, `${label}.last_error_kind`, target);
	const record: IssueLocalRecord = {
		id,
		submission_digest: parseHex(value.submission_digest, 16, `${label}.submission_digest`, target),
		card_sha256: parseHex(value.card_sha256, 64, `${label}.card_sha256`, target),
		project_label: parseNonblank(value.project_label, `${label}.project_label`, target),
		state: parseClosed(value.state, ISSUE_LOCAL_STATES, `${label}.state`, target),
		attempts: value.attempts,
		created_at: parseInstant(value.created_at, `${label}.created_at`, target),
		updated_at: parseInstant(value.updated_at, `${label}.updated_at`, target),
		last_error_kind: lastError,
		authority_ack: parseLocalAck(value.authority_ack, target),
	};
	assertStoredNoSecrets(record, label, target);
	return record;
}

function parseLocalIndex(value: unknown, root: string, target: string): IssueLocalIndex {
	if (!isRecord(value) || !hasExactKeys(value, ["schema", "kind", "project_fingerprint", "updated_at", "records"])) {
		corrupt("local index has an unknown or missing field", target);
	}
	if (value.schema !== ISSUE_STORE_SCHEMA) corrupt("local index schema must be 1", target);
	if (value.kind !== ISSUE_LOCAL_INDEX_KIND) corrupt("local index kind mismatch", target);
	const fingerprint = parseHex(value.project_fingerprint, 64, "project_fingerprint", target);
	if (fingerprint !== projectFingerprint(root)) corrupt("local index belongs to another project root", target);
	if (!Array.isArray(value.records)) corrupt("local index records must be an array", target);
	const records = value.records.map((record, index) => parseLocalRecord(record, `records[${index}]`, target));
	const ids = new Set<string>();
	for (const record of records) {
		if (ids.has(record.id)) corrupt("local index has duplicate feedback IDs", target);
		ids.add(record.id);
	}
	const index: IssueLocalIndex = {
		schema: ISSUE_STORE_SCHEMA,
		kind: ISSUE_LOCAL_INDEX_KIND,
		project_fingerprint: fingerprint,
		updated_at: parseInstant(value.updated_at, "updated_at", target),
		records,
	};
	assertStoredNoSecrets(index, "local index", target);
	return index;
}

function readLocalIndex(root: string): IssueLocalIndex {
	const parent = validateSafeDirectory(root, ISSUE_LOCAL_DIR_PARTS, false);
	if (parent === null) return emptyLocalIndex(root);
	const file = issueLocalIndexPath(root);
	const value = readStrictJsonFile(file, parent);
	if (value === null) return emptyLocalIndex(root);
	return parseLocalIndex(value, root, file);
}

function parsePendingCopy(value: unknown, root: string, target: string): IssuePendingCopy {
	if (
		!isRecord(value) ||
		!hasExactKeys(value, [
			"schema",
			"kind",
			"id",
			"submission_digest",
			"card_sha256",
			"preview_sha256",
			"confirmed_at",
			"confirmed_by",
			"project_label",
			"card",
		])
	) {
		corrupt("pending copy has an unknown or missing field", target);
	}
	if (value.schema !== ISSUE_STORE_SCHEMA) corrupt("pending copy schema must be 1", target);
	if (value.kind !== ISSUE_PENDING_COPY_KIND) corrupt("pending copy kind mismatch", target);
	const id = parseNonblank(value.id, "id", target);
	if (!isIssueId(id)) corrupt("pending copy ID must be fb- plus 32 lowercase hex characters", target);
	const card = parseIssueCard(value.card, "card", target);
	assertFreshCard(card, target);
	const digest = issueSubmissionDigest(card);
	const cardSha = sha256(canonicalPayload(card));
	const previewSha = sha256(renderPreview(card));
	const pending: IssuePendingCopy = {
		schema: ISSUE_STORE_SCHEMA,
		kind: ISSUE_PENDING_COPY_KIND,
		id,
		submission_digest: parseHex(value.submission_digest, 16, "submission_digest", target),
		card_sha256: parseHex(value.card_sha256, 64, "card_sha256", target),
		preview_sha256: parseHex(value.preview_sha256, 64, "preview_sha256", target),
		confirmed_at: parseInstant(value.confirmed_at, "confirmed_at", target),
		confirmed_by: parseNonblank(value.confirmed_by, "confirmed_by", target),
		project_label: parseNonblank(value.project_label, "project_label", target),
		card,
	};
	if (pending.id !== card.id) corrupt("pending copy ID does not match its card", target);
	if (pending.project_label !== card.projectLabel)
		corrupt("pending copy project label does not match its card", target);
	if (pending.submission_digest !== digest) corrupt("pending copy submission digest mismatch", target);
	if (pending.card_sha256 !== cardSha) corrupt("pending copy card hash mismatch", target);
	if (pending.preview_sha256 !== previewSha) corrupt("pending copy preview hash mismatch", target);
	assertStoredNoSecrets(pending, "pending copy", target);
	void root;
	return pending;
}

function readPendingCopy(root: string, id: string): IssuePendingCopy | null {
	const parts = [...ISSUE_LOCAL_DIR_PARTS, ISSUE_PENDING_DIR_BASENAME];
	const parent = validateSafeDirectory(root, parts, false);
	if (parent === null) return null;
	const file = issuePendingCopyPath(root, id);
	const value = readStrictJsonFile(file, parent);
	if (value === null) return null;
	return parsePendingCopy(value, root, file);
}

/** Atomic same-directory write. No fixed `.tmp`, no `fs.writeFile` overwrite,
 * no deletion of another writer's temp; only this process's own `wx` temp is
 * cleaned up. UTF-8 payload is exactly JSON + one LF (no BOM, no CRLF). */
function atomicWriteJson(file: string, parent: string, value: unknown): void {
	assertSafeRegularFile(parent, file);
	const serialized = JSON.stringify(value, null, 2);
	if (typeof serialized !== "string") {
		throw new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", "value is not JSON-serializable", file);
	}
	const text = `${serialized}\n`;
	const temporary = path.join(parent, `.tmp-${randomUUID()}`);
	let fd: number | null = null;
	let ownTemp = false;
	try {
		fd = fs.openSync(temporary, "wx", 0o600);
		ownTemp = true;
		fs.writeFileSync(fd, text, "utf8");
		fs.fsyncSync(fd);
		fs.closeSync(fd);
		fd = null;
		fs.renameSync(temporary, file);
		ownTemp = false;
	} catch (error) {
		if (fd !== null) {
			try {
				fs.closeSync(fd);
			} catch {
				// The original write error remains authoritative.
			}
			fd = null;
		}
		if (ownTemp) {
			try {
				fs.unlinkSync(temporary);
			} catch (cleanupError) {
				throw new IssueStoreError(
					"E-ISSUE-STORE-WRITE_FAILED",
					`${errorText(error)}; own temp cleanup failed: ${errorText(cleanupError)}`,
					temporary,
				);
			}
		}
		throw new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", errorText(error), file);
	}
}

function writeLocalIndex(root: string, index: IssueLocalIndex): void {
	const parent = validateSafeDirectory(root, ISSUE_LOCAL_DIR_PARTS, true);
	if (parent === null) throw new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", "local parent unavailable", root);
	atomicWriteJson(issueLocalIndexPath(root), parent, index);
}

interface PendingCopyWriteResult {
	ok: boolean;
	copy: IssuePendingCopy | null;
	reason: string;
}

function writePendingCopy(root: string, pending: IssuePendingCopy): PendingCopyWriteResult {
	const parts = [...ISSUE_LOCAL_DIR_PARTS, ISSUE_PENDING_DIR_BASENAME];
	const parent = validateSafeDirectory(root, parts, true);
	if (parent === null) throw new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", "pending parent unavailable", root);
	const file = issuePendingCopyPath(root, pending.id);
	if (assertSafeRegularFile(parent, file)) {
		const value = readStrictJsonFile(file, parent);
		if (value === null) corrupt("pending copy disappeared during write", file);
		const existing = parsePendingCopy(value, root, file);
		const same =
			existing.id === pending.id &&
			existing.card_sha256 === pending.card_sha256 &&
			existing.submission_digest === pending.submission_digest &&
			canonicalPayload(existing.card) === canonicalPayload(pending.card);
		if (!same)
			return { ok: false, copy: existing, reason: "a different confirmed pending copy already owns this ID" };
		return { ok: true, copy: existing, reason: "existing identical pending copy kept unchanged" };
	}
	atomicWriteJson(file, parent, pending);
	return { ok: true, copy: pending, reason: "confirmed redacted pending copy written" };
}

function removePendingCopy(root: string, id: string): void {
	const parts = [...ISSUE_LOCAL_DIR_PARTS, ISSUE_PENDING_DIR_BASENAME];
	const parent = validateSafeDirectory(root, parts, false);
	if (parent === null) return;
	const file = issuePendingCopyPath(root, id);
	if (!assertSafeRegularFile(parent, file)) return;
	fs.unlinkSync(file);
}

// ── Append-only SHA-256-chained authority event log ─────────────────────────

function authorityEventHash(draft: IssueAuthorityEventDraft): string {
	return sha256(`${draft.prev_sha256}\n${stableStringify(draft)}`);
}

function parseAuthorityEvent(
	value: unknown,
	id: string,
	expectedSeq: number,
	expectedPrevSha: string,
	target: string,
): IssueAuthorityEvent {
	if (!isRecord(value)) corrupt("authority event must be an object", target);
	const kind = parseClosed(value.kind, ISSUE_EVENT_KINDS, "kind", target);
	const baseKeys = [
		"schema",
		"kind",
		"id",
		"seq",
		"prev_sha256",
		"sha256",
		"submission_digest",
		"project_label",
		"at",
		"source",
		"by",
	];
	const extraKeys: readonly string[] =
		kind === "created"
			? ["card_sha256", "preview_sha256", "confirmed_at", "confirmed_by", "card"]
			: kind === "dev_update"
				? ["update"]
				: ["reply"];
	if (!hasExactKeys(value, [...baseKeys, ...extraKeys]))
		corrupt("authority event has an unknown or missing field", target);
	if (value.schema !== ISSUE_STORE_SCHEMA) corrupt("authority event schema must be 1", target);
	const eventId = parseNonblank(value.id, "id", target);
	if (eventId !== id || !isIssueId(eventId)) corrupt("authority event ID mismatch", target);
	if (!isSafeInteger(value.seq, 1)) corrupt("seq must be a positive integer", target);
	if (value.seq !== expectedSeq) corrupt(`seq must be ${expectedSeq}`, target);
	const prevSha = parseHex(value.prev_sha256, 64, "prev_sha256", target);
	if (prevSha !== expectedPrevSha) corrupt("prev_sha256 does not match the previous event", target);
	const eventSha = parseHex(value.sha256, 64, "sha256", target);
	const withoutHash: Record<string, unknown> = { ...value };
	delete withoutHash.sha256;
	if (sha256(`${prevSha}\n${stableStringify(withoutHash)}`) !== eventSha) {
		corrupt("authority event hash chain mismatch", target);
	}
	const base: IssueEventBase = {
		schema: ISSUE_STORE_SCHEMA,
		kind,
		id: eventId,
		seq: value.seq,
		prev_sha256: prevSha,
		sha256: eventSha,
		submission_digest: parseHex(value.submission_digest, 16, "submission_digest", target),
		project_label: parseNonblank(value.project_label, "project_label", target),
		at: parseInstant(value.at, "at", target),
		source: parseClosed(value.source, ISSUE_EVENT_SOURCES, "source", target),
		by: parseNonblank(value.by, "by", target),
	};
	if (kind === "created") {
		const card = parseIssueCard(value.card, "created.card", target);
		assertFreshCard(card, target);
		const digest = issueSubmissionDigest(card);
		const cardSha = sha256(canonicalPayload(card));
		const previewSha = sha256(renderPreview(card));
		const confirmedAt = parseInstant(value.confirmed_at, "confirmed_at", target);
		const confirmedBy = parseNonblank(value.confirmed_by, "confirmed_by", target);
		const event: IssueCreatedEvent = {
			...base,
			kind: "created",
			card_sha256: parseHex(value.card_sha256, 64, "card_sha256", target),
			preview_sha256: parseHex(value.preview_sha256, 64, "preview_sha256", target),
			confirmed_at: confirmedAt,
			confirmed_by: confirmedBy,
			card,
		};
		if (base.source !== "project-pm") corrupt("created event source must be project-pm", target);
		if (base.at !== confirmedAt || base.by !== confirmedBy) corrupt("created event time/by mismatch", target);
		if (base.project_label !== card.projectLabel) corrupt("created event project label mismatch", target);
		if (base.submission_digest !== digest) corrupt("created event submission digest mismatch", target);
		if (event.card_sha256 !== cardSha) corrupt("created event card hash mismatch", target);
		if (event.preview_sha256 !== previewSha) corrupt("created event preview hash mismatch", target);
		assertStoredNoSecrets(event, "created event", target);
		return event;
	}
	if (kind === "dev_update") {
		const update = parseDevUpdate(value.update, "dev_update.update", target);
		const event: IssueDevUpdateEvent = { ...base, kind: "dev_update", update };
		if (base.source !== "dev-pm") corrupt("dev_update event source must be dev-pm", target);
		if (update.at !== base.at || update.by !== base.by) corrupt("dev_update time/by mismatch", target);
		assertStoredNoSecrets(event, "dev_update event", target);
		return event;
	}
	const reply = parseReporterReply(value.reply, "reporter_reply.reply", target);
	const event: IssueReporterReplyEvent = { ...base, kind: "reporter_reply", reply };
	if (base.source !== "project-pm") corrupt("reporter_reply event source must be project-pm", target);
	if (reply.at !== base.at || reply.source !== "user") corrupt("reporter_reply time/source mismatch", target);
	assertStoredNoSecrets(event, "reporter_reply event", target);
	return event;
}

function emptyAuthorityState(id: string): IssueAuthorityState {
	return {
		exists: false,
		id,
		events: [],
		created: null,
		card: null,
		submissionDigest: null,
		cardSha256: null,
		projectLabel: null,
		lastSha256: GENESIS_SHA256,
		lastSeq: 0,
	};
}

function readAuthorityState(devRoot: string, id: string): IssueAuthorityState {
	const parts = [...ISSUE_AUTHORITY_DIR_PARTS, ISSUE_EVENTS_DIR_BASENAME];
	const parent = validateSafeDirectory(devRoot, parts, false);
	const file = issueAuthorityLogPath(devRoot, id);
	if (parent === null || !assertSafeRegularFile(parent, file)) return emptyAuthorityState(id);
	const raw = fs.readFileSync(file, "utf8");
	if (raw.charCodeAt(0) === 0xfeff) corrupt("UTF-8 BOM is not allowed", file);
	if (raw.includes("\r")) corrupt("CR/CRLF is not allowed: LF-only UTF-8 JSONL required", file);
	if (!raw.endsWith("\n")) corrupt("authority JSONL must end with exactly one LF", file);
	const lines = raw.split("\n");
	lines.pop();
	if (lines.length === 0) corrupt("authority JSONL has no events", file);
	const events: IssueAuthorityEvent[] = [];
	let expectedPrevSha = GENESIS_SHA256;
	for (let index = 0; index < lines.length; index += 1) {
		const line = lines[index];
		if (line.length === 0) corrupt(`authority event ${index + 1} is empty`, file);
		const value = parseJsonDocument(`${line}\n`, file);
		const event = parseAuthorityEvent(value, id, index + 1, expectedPrevSha, file);
		events.push(event);
		expectedPrevSha = event.sha256;
	}
	const createdEvents = events.filter((event): event is IssueCreatedEvent => event.kind === "created");
	if (events[0].kind !== "created" || createdEvents.length !== 1) {
		corrupt("authority log must start with exactly one created event", file);
	}
	const created = createdEvents[0];
	let card = created.card;
	let devUpdates = 0;
	let replies = 0;
	// Stable authority-event identity for each dev_update, in replay order (1:1
	// with card.devTimeline). Attached to the in-memory projection AFTER the
	// chain has been fully verified, so pendingQuestion can bind a reply to the
	// exact question event by hash instead of a clock. Never persisted here.
	const devUpdateEventHashes: string[] = [];
	for (const event of events.slice(1)) {
		if (event.submission_digest !== created.submission_digest || event.project_label !== created.project_label) {
			corrupt("authority event is bound to a different submission", file);
		}
		try {
			if (event.kind === "dev_update") {
				const before = card.devTimeline.length;
				card = appendDevUpdate(card, event.update, [], "canonical");
				const added = card.devTimeline[before];
				if (added === undefined || stableStringify(added) !== stableStringify(event.update)) {
					corrupt("dev_update did not reproduce its stored update", file);
				}
				devUpdateEventHashes.push(event.sha256);
				devUpdates += 1;
			} else if (event.kind === "reporter_reply") {
				const before = card.reporterReplies.length;
				card = appendReporterReply(card, event.reply, [], "canonical");
				const added = card.reporterReplies[before];
				if (added === undefined || stableStringify(added) !== stableStringify(event.reply)) {
					corrupt("reporter_reply did not reproduce its stored reply", file);
				}
				replies += 1;
			} else {
				corrupt("duplicate created event in authority log", file);
			}
		} catch (error) {
			if (error instanceof IssueStoreError) throw error;
			corrupt(`model replay failed: ${errorText(error)}`, file);
		}
	}
	if (card.devTimeline.length !== devUpdates || card.reporterReplies.length !== replies) {
		corrupt("replayed card has an unexpected event count", file);
	}
	// Projection-only: hand the verified hash-chain identities to the model so
	// pendingQuestion / summarizeForList / status / list agree on the same
	// stable question identity. This annotates the in-memory card only; the
	// created bytes and every stored event stay untouched.
	card = withQuestionIdentities(card, devUpdateEventHashes);
	const last = events[events.length - 1];
	return {
		exists: true,
		id,
		events,
		created,
		card,
		submissionDigest: created.submission_digest,
		cardSha256: created.card_sha256,
		projectLabel: created.project_label,
		lastSha256: last.sha256,
		lastSeq: last.seq,
	};
}

/** Caller holds the authority O_EXCL lock and has already read/validated the
 * current chain. `wx` creates a new per-ID log; `O_APPEND` never overwrites. */
function appendAuthorityEvent(devRoot: string, id: string, draft: IssueAuthorityEventDraft): IssueAuthorityEvent {
	const parts = [...ISSUE_AUTHORITY_DIR_PARTS, ISSUE_EVENTS_DIR_BASENAME];
	const parent = validateSafeDirectory(devRoot, parts, true);
	if (parent === null)
		throw new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", "authority parent unavailable", devRoot);
	const file = issueAuthorityLogPath(devRoot, id);
	const exists = assertSafeRegularFile(parent, file);
	const eventSha = authorityEventHash(draft);
	const event = { ...draft, sha256: eventSha } as IssueAuthorityEvent;
	const text = `${JSON.stringify(event)}\n`;
	let fd: number | null = null;
	try {
		fd = fs.openSync(file, exists ? "a" : "wx", 0o600);
		const before = fs.fstatSync(fd).size;
		fs.writeFileSync(fd, text, "utf8");
		fs.fsyncSync(fd);
		const after = fs.fstatSync(fd).size;
		if (after !== before + Buffer.byteLength(text, "utf8")) {
			throw new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", "non-cooperative concurrent append detected", file);
		}
	} catch (error) {
		if (error instanceof IssueStoreError) throw error;
		throw new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", errorText(error), file);
	} finally {
		if (fd !== null) fs.closeSync(fd);
	}
	return event;
}

// ── Token-owned exclusive locks: O_EXCL, no stale-lock cleanup ─────────────

function sleep(milliseconds: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

interface LockFileIdentity {
	dev: number;
	ino: number;
	birthtimeMs: number;
}

interface OwnedLock {
	token: string;
	identity: LockFileIdentity;
	tokenWritten: boolean;
}

function lockIdentityFromStat(stat: fs.Stats): LockFileIdentity {
	return { dev: stat.dev, ino: stat.ino, birthtimeMs: stat.birthtimeMs };
}

function sameLockIdentity(a: LockFileIdentity, b: LockFileIdentity): boolean {
	return a.dev === b.dev && a.ino === b.ino && a.birthtimeMs === b.birthtimeMs;
}

/** A lock path still names THIS process's wx-created file: same file identity,
 * regular file (never a link) and either the exact token or, before a complete
 * token write, an empty/prefix-only partial token. */
function ownLockStillAtPath(lockPath: string, owned: OwnedLock): boolean {
	let stat: fs.Stats;
	try {
		stat = fs.lstatSync(lockPath);
	} catch {
		return false;
	}
	if (stat.isSymbolicLink() || !stat.isFile()) return false;
	if (!sameLockIdentity(owned.identity, lockIdentityFromStat(stat))) return false;
	let content: string;
	try {
		content = fs.readFileSync(lockPath, "utf8");
	} catch {
		return false;
	}
	if (owned.tokenWritten) return content === owned.token;
	return content === "" || owned.token.startsWith(content);
}

/** Close an acquisition fd and remove only the lock this call just created.
 * A failed close is retried once so a single injected close error cannot keep
 * the fd open on Windows; a replaced path is never unlinked. */
function cleanupFailedAcquisition(lockPath: string, fd: number | null, owned: OwnedLock | null): string | null {
	let cleanupError: string | null = null;
	if (fd !== null) {
		try {
			fs.closeSync(fd);
		} catch (error) {
			cleanupError = `lock fd close failed: ${errorText(error)}`;
			try {
				fs.closeSync(fd);
			} catch {
				// Already closed or still unclosable; the original error remains authoritative.
			}
		}
	}
	if (owned !== null) {
		if (!ownLockStillAtPath(lockPath, owned)) {
			const prefix = cleanupError === null ? "" : `${cleanupError}; `;
			cleanupError = `${prefix}own lock path was replaced; left untouched`;
		} else {
			try {
				fs.unlinkSync(lockPath);
			} catch (error) {
				const prefix = cleanupError === null ? "" : `${cleanupError}; `;
				cleanupError = `${prefix}own lock cleanup failed: ${errorText(error)}`;
			}
		}
	}
	return cleanupError;
}

async function withExclusiveLock<T>(
	lockPath: string,
	parent: string,
	options: IssueLockOptions,
	callback: () => T | Promise<T>,
	preflightScope: "authority" | null = null,
): Promise<T> {
	const retries = options.retries ?? 100;
	const baseDelayMs = options.baseDelayMs ?? 5;
	const token = `${process.pid}:${randomUUID()}`;
	const tagAuthorityPreflight = (failure: unknown): void => {
		if (
			preflightScope === "authority" &&
			!(failure instanceof IssueStoreError && failure.code === "E-ISSUE-STORE-CORRUPT")
		) {
			markAuthorityPreflight(failure);
		}
	};
	const acquisitionFailure = (error: unknown): never => {
		const failure =
			error instanceof IssueStoreError
				? error
				: new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", errorText(error), lockPath);
		tagAuthorityPreflight(failure);
		throw failure;
	};
	try {
		assertSafeRegularFile(parent, lockPath);
	} catch (error) {
		acquisitionFailure(error);
	}
	let owned: OwnedLock | null = null;
	for (let attempt = 0; attempt <= retries; attempt += 1) {
		let fd: number | null = null;
		let attemptOwned: OwnedLock | null = null;
		try {
			fd = fs.openSync(lockPath, "wx", 0o600);
			let identity: LockFileIdentity;
			try {
				identity = lockIdentityFromStat(fs.fstatSync(fd));
			} catch {
				identity = lockIdentityFromStat(fs.lstatSync(lockPath));
			}
			attemptOwned = { token, identity, tokenWritten: false };
			fs.writeFileSync(fd, token, "utf8");
			attemptOwned.tokenWritten = true;
			fs.fsyncSync(fd);
			fs.closeSync(fd);
			fd = null;
			owned = attemptOwned;
			break;
		} catch (error) {
			const cleanupError = cleanupFailedAcquisition(lockPath, fd, attemptOwned);
			if (nodeErrorCode(error) === "EEXIST") {
				if (attempt < retries) {
					await sleep(Math.min(25, baseDelayMs * (attempt + 1)));
					continue;
				}
				throw new IssueStoreError("E-ISSUE-STORE-LOCK_BUSY", "foreign lock still present", lockPath);
			}
			let failure =
				error instanceof IssueStoreError
					? error
					: new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", errorText(error), lockPath);
			if (cleanupError !== null) {
				failure = new IssueStoreError(
					"E-ISSUE-STORE-WRITE_FAILED",
					`${errorText(failure)}; ${cleanupError}`,
					lockPath,
				);
			}
			tagAuthorityPreflight(failure);
			throw failure;
		}
	}
	if (owned === null) throw new IssueStoreError("E-ISSUE-STORE-LOCK_BUSY", "foreign lock still present", lockPath);
	let outcome: { ok: true; value: T } | { ok: false; error: unknown };
	try {
		outcome = { ok: true, value: await callback() };
	} catch (error) {
		outcome = { ok: false, error };
	}
	let releaseFailure: IssueStoreError | null = null;
	try {
		if (!ownLockStillAtPath(lockPath, owned)) {
			throw new IssueStoreError(
				"E-ISSUE-STORE-LOCK_RELEASE_FAILED",
				"own lock identity or token changed during critical section",
				lockPath,
			);
		}
		fs.unlinkSync(lockPath);
	} catch (error) {
		if (error instanceof IssueStoreError) {
			releaseFailure = error;
		} else if (nodeErrorCode(error) === "ENOENT") {
			releaseFailure = new IssueStoreError(
				"E-ISSUE-STORE-LOCK_RELEASE_FAILED",
				"own lock disappeared during critical section",
				lockPath,
			);
		} else {
			releaseFailure = new IssueStoreError("E-ISSUE-STORE-LOCK_RELEASE_FAILED", errorText(error), lockPath);
		}
	}
	if (!outcome.ok) throw outcome.error;
	if (releaseFailure !== null) throw releaseFailure;
	return outcome.value;
}

async function withAuthorityLock<T>(
	devRoot: string,
	options: IssueLockOptions,
	callback: () => T | Promise<T>,
): Promise<T> {
	let parent: string | null;
	try {
		parent = validateSafeDirectory(devRoot, ISSUE_AUTHORITY_DIR_PARTS, true);
	} catch (error) {
		if (isAuthorityPreflightIoFailure(error)) markAuthorityPreflight(error);
		throw error;
	}
	if (parent === null) {
		const failure = new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", "authority parent unavailable", devRoot);
		markAuthorityPreflight(failure);
		throw failure;
	}
	return withExclusiveLock(issueAuthorityLockPath(devRoot), parent, options, callback, "authority");
}

async function withLocalLock<T>(
	projectRoot: string,
	options: IssueLockOptions,
	callback: () => T | Promise<T>,
): Promise<T> {
	const parent = validateSafeDirectory(projectRoot, ISSUE_LOCAL_DIR_PARTS, true);
	if (parent === null)
		throw new IssueStoreError("E-ISSUE-STORE-WRITE_FAILED", "local parent unavailable", projectRoot);
	return withExclusiveLock(issueLocalLockPath(projectRoot), parent, options, callback);
}

// ── Root resolution, complete previews and input gates ─────────────────────

interface RootResolution {
	ok: boolean;
	resolved: IssueDevRootResolved | null;
	failure: IssueDevRootFailure | null;
}

function rootFailureText(failure: IssueDevRootFailure): string {
	return formatIssueDevRootFailure(failure);
}

export interface IssueProgressPreviewContext {
	id: string;
	at: string;
	source: IssueEventSource;
	by: string;
}

export interface IssueReplyPreviewContext {
	id: string;
	at: string;
	source: IssueEventSource;
	by: string;
}

/** Full (never truncated) preview of exactly the progress fields written.
 * The caller MUST already have desensitized the text. The store rejects any
 * credential-shaped content rather than silently redacting a confirmation. */
export function renderDevUpdatePreview(fields: IssueProgressFields, context: IssueProgressPreviewContext): string {
	const nullable = (value: string | null): string => value ?? UNKNOWN;
	return [
		"# MW 反馈开发进展（完整脱敏预览）",
		`- 反馈 ID: ${context.id}`,
		`- 时间: ${context.at}`,
		`- 来源: ${context.source} (${context.by})`,
		`- 状态: ${fields.status}`,
		`- 状态说明: ${fields.statusNote}`,
		`- 下一步: ${nullable(fields.nextAction)}`,
		`- 修复提交: ${nullable(fields.fixCommit)}`,
		`- 发布版本: ${nullable(fields.releaseVersion)}`,
		`- 向反馈方追问: ${nullable(fields.questionToReporter)}`,
		"以上字段将写入同一反馈 ID；未知项保留「未知」，不推断本地是否生效。",
	].join("\n");
}

export function renderReporterReplyPreview(fields: IssueReplyFields, context: IssueReplyPreviewContext): string {
	return [
		"# MW 反馈项目回复（完整脱敏预览）",
		`- 反馈 ID: ${context.id}`,
		`- 时间: ${context.at}`,
		`- 写入来源: ${context.source} (${context.by})`,
		`- 内容来源: ${fields.source}`,
		`- 回复对象: ${fields.inReplyTo ?? UNKNOWN}`,
		`- 回复正文: ${fields.text}`,
		"以上为将写入的完整正文；不会创建新反馈 ID。",
	].join("\n");
}

interface PreviewConfirmationResult {
	ok: boolean;
	code: IssueOperationCode;
	reason: string;
}

function validatePreviewConfirmation(
	preview: string,
	expectedPreview: string,
	confirmation: Confirmation,
	value: unknown,
	knownSecrets: readonly string[],
): PreviewConfirmationResult {
	if (!confirmation.confirmed) return { ok: false, code: "unconfirmed", reason: "user did not confirm the preview" };
	if (!isInstant(confirmation.confirmedAt)) {
		return { ok: false, code: "unconfirmed", reason: "confirmation needs a tz-aware time" };
	}
	if (preview !== expectedPreview) {
		return { ok: false, code: "unconfirmed", reason: "preview is not the complete exact payload to be written" };
	}
	if (confirmation.previewSha256 !== issueTextSha256(expectedPreview)) {
		return { ok: false, code: "unconfirmed", reason: "confirmation digest does not match the complete preview" };
	}
	if (!hasNoSecrets(value, knownSecrets)) {
		return {
			ok: false,
			code: "credential-detected",
			reason: "credential-shaped text is not accepted without an approved redaction",
		};
	}
	return { ok: true, code: "ok", reason: "complete redacted preview confirmed" };
}

function defaultLocalEvidence(): LocalEvidence {
	return {
		localVersion: null,
		bundleStale: null,
		serveStale: null,
		entrypointInstalled: null,
		collectedAt: null,
	};
}

interface ActorGate {
	ok: boolean;
	code: IssueOperationCode;
	reason: string;
}

function canonicalizedActorRoot(actor: IssueStoreActor): string | null {
	try {
		return canonicalDir(actor.projectRoot);
	} catch {
		return null;
	}
}

function actorHasNoSecrets(actor: IssueStoreActor): boolean {
	return hasNoSecrets({ role: actor.role, scope: actor.scope, projectLabel: actor.projectLabel, by: actor.by }, []);
}

function gateProjectRead(actor: IssueStoreActor, localRoot: string): ActorGate {
	const actorRoot = canonicalizedActorRoot(actor);
	if (actorRoot === null || fold(actorRoot) !== fold(localRoot)) {
		return { ok: false, code: "foreign-project", reason: "actor root does not match the current project" };
	}
	if (!nonblank(actor.projectLabel) || !nonblank(actor.by) || !actorHasNoSecrets(actor)) {
		return { ok: false, code: "invalid-input", reason: "actor label/by is missing or credential-shaped" };
	}
	return { ok: true, code: "ok", reason: "project read actor accepted" };
}

function gateWrite(
	actor: IssueStoreActor,
	expectedScope: IssueActorScope,
	expectedRoot: string,
	env: NodeJS.ProcessEnv,
): ActorGate {
	if (nonblank(env.PI_WORKER_TASK)) {
		return {
			ok: false,
			code: "worker-forbidden",
			reason: "PI_WORKER_TASK is present; MW worker writes are forbidden",
		};
	}
	if (actor.role !== "pm" || actor.scope !== expectedScope || !actor.writeAuthorized) {
		return { ok: false, code: "worker-forbidden", reason: "write requires an authorized PM in the matching scope" };
	}
	if (!actor.trustedWindow) {
		return { ok: false, code: "untrusted-window", reason: "write requires a trusted, confirmed TUI window" };
	}
	const actorRoot = canonicalizedActorRoot(actor);
	if (actorRoot === null || fold(actorRoot) !== fold(expectedRoot)) {
		return { ok: false, code: "foreign-project", reason: "actor root does not match the required canonical root" };
	}
	if (!nonblank(actor.projectLabel) || !nonblank(actor.by) || !actorHasNoSecrets(actor)) {
		return { ok: false, code: "invalid-input", reason: "actor label/by is missing or credential-shaped" };
	}
	return { ok: true, code: "ok", reason: "PM write actor accepted" };
}

// ── Result builders and local-index transitions ─────────────────────────────

interface SubmitResultOptions {
	ok: boolean;
	code: IssueOperationCode;
	id: string;
	state: IssueDisplayState;
	submitted: boolean;
	authorityReachable: boolean;
	display: string;
	message: string;
	reason: string;
	attempts: number;
	rootFailure?: IssueDevRootFailure | null;
	created?: boolean;
	verifiedById?: boolean;
	event?: IssueAuthorityEvent | null;
	localRecord?: IssueLocalRecord | null;
}

function makeSubmitResult(options: SubmitResultOptions): IssueSubmitResult {
	return {
		ok: options.ok,
		code: options.code,
		id: options.id,
		state: options.state,
		submitted: options.submitted,
		authorityReachable: options.authorityReachable,
		display: options.display,
		message: options.message,
		reason: options.reason,
		attempts: options.attempts,
		rootFailure: options.rootFailure ?? null,
		created: options.created ?? false,
		verifiedById: options.verifiedById ?? false,
		event: options.event ?? null,
		localRecord: options.localRecord ?? null,
	};
}

function submitRefusal(id: string, code: IssueOperationCode, reason: string, message: string): IssueSubmitResult {
	return makeSubmitResult({
		ok: false,
		code,
		id,
		state: "none",
		submitted: false,
		authorityReachable: false,
		display: ISSUE_DISPLAY_REFUSED,
		message,
		reason,
		attempts: 0,
	});
}

interface MutationResultOptions {
	ok: boolean;
	code: IssueOperationCode;
	id: string;
	authorityReachable: boolean;
	message: string;
	reason: string;
	event?: IssueAuthorityEvent | null;
	card?: IssueCard | null;
	seq?: number;
	rootFailure?: IssueDevRootFailure | null;
}

function makeMutationResult(options: MutationResultOptions): IssueMutationResult {
	return {
		ok: options.ok,
		code: options.code,
		id: options.id,
		authorityReachable: options.authorityReachable,
		message: options.message,
		reason: options.reason,
		event: options.event ?? null,
		card: options.card ?? null,
		seq: options.seq ?? 0,
		rootFailure: options.rootFailure ?? null,
	};
}

interface StatusResultOptions {
	ok: boolean;
	code: IssueOperationCode;
	id: string;
	authorityReachable: boolean;
	authorityVerifiedById: boolean;
	localAck: boolean;
	localState: IssueDisplayState;
	submitted: boolean;
	display: string;
	message: string;
	reason: string;
	text: string;
	localRecord?: IssueLocalRecord | null;
	card?: IssueCard | null;
	projection?: UserProjection | null;
	development?: DevStateView | null;
	pendingQuestion?: string | null;
	localEffective?: LocalEffectiveResult | null;
	events?: IssueAuthorityEvent[];
	rootFailure?: IssueDevRootFailure | null;
}

function makeStatusResult(options: StatusResultOptions): IssueStatusResult {
	return {
		ok: options.ok,
		code: options.code,
		id: options.id,
		authorityReachable: options.authorityReachable,
		authorityVerifiedById: options.authorityVerifiedById,
		localAck: options.localAck,
		localState: options.localState,
		submitted: options.submitted,
		display: options.display,
		message: options.message,
		reason: options.reason,
		text: options.text,
		localRecord: options.localRecord ?? null,
		card: options.card ?? null,
		projection: options.projection ?? null,
		development: options.development ?? null,
		pendingQuestion: options.pendingQuestion ?? null,
		localEffective: options.localEffective ?? null,
		events: options.events ?? [],
		rootFailure: options.rootFailure ?? null,
	};
}

function findLocalRecord(index: IssueLocalIndex, id: string): IssueLocalRecord | null {
	return index.records.find((record) => record.id === id) ?? null;
}

function localRecordMatches(record: IssueLocalRecord, pending: IssuePendingCopy): boolean {
	return (
		record.submission_digest === pending.submission_digest &&
		record.card_sha256 === pending.card_sha256 &&
		record.project_label === pending.project_label
	);
}

function authorityMatches(state: IssueAuthorityState, pending: IssuePendingCopy): boolean {
	if (
		!state.exists ||
		!state.created ||
		!state.card ||
		!state.submissionDigest ||
		!state.cardSha256 ||
		!state.projectLabel
	) {
		return false;
	}
	return (
		state.submissionDigest === pending.submission_digest &&
		state.cardSha256 === pending.card_sha256 &&
		state.projectLabel === pending.project_label &&
		canonicalPayload(state.created.card) === canonicalPayload(pending.card)
	);
}

interface UpsertedLocal {
	index: IssueLocalIndex;
	record: IssueLocalRecord;
}

function upsertFromRecord(
	index: IssueLocalIndex,
	base: IssueLocalRecord,
	at: string,
	state: IssueLocalState,
	lastError: IssueLastErrorKind,
	ack: IssueAuthorityAck | null,
	incrementAttempts: boolean,
): UpsertedLocal {
	const existing = findLocalRecord(index, base.id);
	const record: IssueLocalRecord = {
		id: base.id,
		submission_digest: base.submission_digest,
		card_sha256: base.card_sha256,
		project_label: base.project_label,
		state,
		attempts: (existing?.attempts ?? 0) + (incrementAttempts ? 1 : 0),
		created_at: existing?.created_at ?? at,
		updated_at: at,
		last_error_kind: lastError,
		authority_ack: ack,
	};
	const records = existing
		? index.records.map((item) => (item.id === base.id ? record : item))
		: [...index.records, record];
	return {
		index: {
			schema: ISSUE_STORE_SCHEMA,
			kind: ISSUE_LOCAL_INDEX_KIND,
			project_fingerprint: index.project_fingerprint,
			updated_at: at,
			records,
		},
		record,
	};
}

function upsertLocalRecord(
	index: IssueLocalIndex,
	pending: IssuePendingCopy,
	at: string,
	state: IssueLocalState,
	lastError: IssueLastErrorKind,
	ack: IssueAuthorityAck | null,
	incrementAttempts: boolean,
): UpsertedLocal {
	return upsertFromRecord(
		index,
		{
			id: pending.id,
			submission_digest: pending.submission_digest,
			card_sha256: pending.card_sha256,
			project_label: pending.project_label,
			state,
			attempts: 0,
			created_at: at,
			updated_at: at,
			last_error_kind: lastError,
			authority_ack: ack,
		},
		at,
		state,
		lastError,
		ack,
		incrementAttempts,
	);
}

function createdDraftFromPending(pending: IssuePendingCopy): IssueAuthorityEventDraft {
	return {
		schema: ISSUE_STORE_SCHEMA,
		kind: "created",
		id: pending.id,
		seq: 1,
		prev_sha256: GENESIS_SHA256,
		submission_digest: pending.submission_digest,
		project_label: pending.project_label,
		at: pending.confirmed_at,
		source: "project-pm",
		by: pending.confirmed_by,
		card_sha256: pending.card_sha256,
		preview_sha256: pending.preview_sha256,
		confirmed_at: pending.confirmed_at,
		confirmed_by: pending.confirmed_by,
		card: pending.card,
	};
}

function ackFromEvent(event: IssueAuthorityEvent): IssueAuthorityAck {
	return {
		seq: event.seq,
		event_sha256: event.sha256,
		at: event.at,
		verified_at: event.at,
	};
}

function runHook(
	hook: ((commit: IssueAuthorityCommit) => void) | undefined,
	commit: IssueAuthorityCommit,
): string | null {
	if (hook === undefined) return null;
	try {
		hook(commit);
		return null;
	} catch (error) {
		return errorText(error);
	}
}

function displayForLocalState(state: IssueDisplayState, localAck: boolean, authorityVerifiedById: boolean): string {
	if (localAck || state === "submitted") return ISSUE_DISPLAY_SUBMITTED;
	if (state === "conflict") return ISSUE_DISPLAY_CONFLICT;
	if (state === "in-flight" || (state === "pending" && authorityVerifiedById)) return ISSUE_DISPLAY_VERIFY_PENDING;
	if (state === "pending") return ISSUE_DISPLAY_NOT_SUBMITTED;
	return ISSUE_DISPLAY_UNKNOWN;
}

// ── The injectable store ─────────────────────────────────────────────────────

export class IssueStore {
	readonly projectRoot: string;
	readonly env: NodeJS.ProcessEnv;
	readonly home: string | undefined;
	readonly pointerFile: string | undefined;
	readonly crossCheckRoots: readonly string[] | undefined;
	readonly lockOptions: IssueLockOptions;
	readonly hooks: IssueStoreHooks;

	constructor(options: IssueStoreOptions) {
		this.projectRoot = canonicalDir(options.projectRoot);
		this.env = options.env ?? process.env;
		this.home = options.home;
		this.pointerFile = options.pointerFile;
		this.crossCheckRoots = options.crossCheckRoots;
		this.lockOptions = options.lockOptions ?? {};
		this.hooks = options.hooks ?? {};
	}

	/** The explicit resolved dev root is the ONLY authority root; a resolver
	 * failure is surfaced verbatim with no cwd/installed-script fallback. */
	resolveRoot(): RootResolution {
		const resolved = resolveIssueDevRoot({
			projectRoot: this.projectRoot,
			env: this.env,
			home: this.home,
			pointerFile: this.pointerFile,
			crossCheckRoots: this.crossCheckRoots,
		});
		if (!resolved.ok) return { ok: false, resolved: null, failure: resolved };
		if (fold(resolved.projectRoot) !== fold(this.projectRoot)) {
			throw new IssueStoreError(
				"E-ISSUE-STORE-INVALID_INPUT",
				"resolved project root does not match the store's canonical project root",
			);
		}
		return { ok: true, resolved, failure: null };
	}

	validateSubmission(request: IssueSubmitRequest): {
		result: IssueSubmitResult | null;
		pending: IssuePendingCopy | null;
	} {
		const actorGate = gateWrite(request.actor, "project", this.projectRoot, this.env);
		if (!actorGate.ok) {
			return {
				result: submitRefusal("", actorGate.code, actorGate.reason, `拒绝写入：${actorGate.reason}`),
				pending: null,
			};
		}
		const { preparation, confirmation } = request;
		const knownSecrets = request.knownSecrets ?? [];
		const id = isRecord(preparation) && isIssueId(preparation.card?.id) ? preparation.card.id : "";
		if (id === "") {
			return {
				result: submitRefusal(
					"",
					"invalid-input",
					"preparation has no store-generated feedback ID",
					"反馈 ID 无效",
				),
				pending: null,
			};
		}
		let confirmed: ConfirmedIssue | null = null;
		try {
			confirmed = confirmIssue(preparation, confirmation);
		} catch (error) {
			return {
				result: submitRefusal(
					id,
					"unconfirmed",
					`confirmIssue rejected input: ${errorText(error)}`,
					"确认无效，拒绝写入",
				),
				pending: null,
			};
		}
		if (confirmed === null || confirmed.approvedForPersistence !== true) {
			return {
				result: submitRefusal(
					id,
					"unconfirmed",
					"confirmIssue did not approve persistence",
					"用户未确认完整脱敏预览，拒绝写入",
				),
				pending: null,
			};
		}
		let card: IssueCard;
		try {
			card = parseIssueCard(preparation.card, "submitted card", id, false);
			assertFreshCard(card, id);
		} catch (error) {
			return {
				result: submitRefusal(
					id,
					"invalid-input",
					`submitted card is invalid: ${errorText(error)}`,
					"提交卡片结构无效，拒绝写入",
				),
				pending: null,
			};
		}
		const expectedPreview = renderPreview(card);
		const expectedPreviewSha = sha256(expectedPreview);
		const digest = issueSubmissionDigest(card);
		const cardSha = sha256(canonicalPayload(card));
		if (
			preparation.preview !== expectedPreview ||
			preparation.previewSha256 !== expectedPreviewSha ||
			preparation.submissionDigest !== digest ||
			confirmed.submissionDigest !== digest ||
			confirmation.previewSha256 !== expectedPreviewSha ||
			!isInstant(confirmed.confirmedAt)
		) {
			return {
				result: submitRefusal(
					id,
					"unconfirmed",
					"preparation/digest/preview binding mismatch",
					"完整脱敏预览或摘要不匹配，拒绝写入",
				),
				pending: null,
			};
		}
		if (!hasNoSecrets({ card, by: request.actor.by, projectLabel: request.actor.projectLabel }, knownSecrets)) {
			return {
				result: submitRefusal(
					id,
					"credential-detected",
					"credential-shaped text reached the store",
					"检测到疑似凭证，拒绝写入",
				),
				pending: null,
			};
		}
		if (request.actor.projectLabel !== card.projectLabel) {
			return {
				result: submitRefusal(
					id,
					"foreign-project",
					"actor project label does not match the card",
					"项目标签不匹配，拒绝写入",
				),
				pending: null,
			};
		}
		const pending: IssuePendingCopy = {
			schema: ISSUE_STORE_SCHEMA,
			kind: ISSUE_PENDING_COPY_KIND,
			id,
			submission_digest: digest,
			card_sha256: cardSha,
			preview_sha256: expectedPreviewSha,
			confirmed_at: confirmed.confirmedAt,
			confirmed_by: request.actor.by,
			project_label: card.projectLabel,
			card,
		};
		return { result: null, pending };
	}

	conflictSubmission(
		identity: Pick<IssuePendingCopy, "id" | "submission_digest" | "card_sha256">,
		reason: string,
		state: IssueDisplayState,
		attempts: number,
	): IssueSubmitResult {
		return makeSubmitResult({
			ok: false,
			code: "duplicate-conflict",
			id: identity.id,
			state,
			submitted: state === "submitted",
			authorityReachable: false,
			display: ISSUE_DISPLAY_CONFLICT,
			message: `同 ID 不同内容，拒绝覆盖：${reason}`,
			reason,
			attempts,
		});
	}

	authorityMatchesRecord(state: IssueAuthorityState, record: IssueLocalRecord): boolean {
		if (!state.exists || !state.submissionDigest || !state.cardSha256 || !state.projectLabel) return false;
		return (
			state.submissionDigest === record.submission_digest &&
			state.cardSha256 === record.card_sha256 &&
			state.projectLabel === record.project_label
		);
	}

	async writeOfflinePending(
		pending: IssuePendingCopy,
		code: IssueOperationCode,
		reason: string,
		rootFailure: IssueDevRootFailure | null,
		lastError: IssueLastErrorKind,
	): Promise<IssueSubmitResult> {
		try {
			return await withLocalLock(this.projectRoot, this.lockOptions, () => {
				const index = readLocalIndex(this.projectRoot);
				const existing = findLocalRecord(index, pending.id);
				if (existing && (!localRecordMatches(existing, pending) || existing.state === "conflict")) {
					return this.conflictSubmission(
						pending,
						"local index owns this ID with different content",
						existing.state,
						existing.attempts,
					);
				}
				const diskPending = readPendingCopy(this.projectRoot, pending.id);
				if (
					diskPending !== null &&
					(diskPending.card_sha256 !== pending.card_sha256 ||
						diskPending.submission_digest !== pending.submission_digest ||
						canonicalPayload(diskPending.card) !== canonicalPayload(pending.card))
				) {
					return this.conflictSubmission(
						pending,
						"confirmed pending copy owns this ID with different content",
						existing?.state ?? "none",
						existing?.attempts ?? 0,
					);
				}
				const previousAck = existing?.authority_ack ?? null;
				if (existing?.state === "submitted") {
					const kept = upsertLocalRecord(
						index,
						pending,
						pending.confirmed_at,
						"submitted",
						lastError,
						previousAck,
						true,
					);
					writeLocalIndex(this.projectRoot, kept.index);
					return makeSubmitResult({
						ok: false,
						code,
						id: pending.id,
						state: "submitted",
						submitted: true,
						authorityReachable: false,
						display: ISSUE_DISPLAY_SUBMITTED,
						message: "已提交（本地回执）；权威状态无法更新",
						reason,
						attempts: kept.record.attempts,
						rootFailure,
						localRecord: kept.record,
					});
				}
				const written = writePendingCopy(this.projectRoot, pending);
				if (!written.ok) {
					return this.conflictSubmission(
						pending,
						written.reason,
						existing?.state ?? "none",
						existing?.attempts ?? 0,
					);
				}
				const upserted = upsertLocalRecord(
					index,
					pending,
					pending.confirmed_at,
					"pending",
					lastError,
					previousAck,
					true,
				);
				writeLocalIndex(this.projectRoot, upserted.index);
				return makeSubmitResult({
					ok: false,
					code,
					id: pending.id,
					state: "pending",
					submitted: false,
					authorityReachable: false,
					display: ISSUE_DISPLAY_NOT_SUBMITTED,
					message:
						code === "lock-busy"
							? "未提交（权威/本地锁忙，请稍后同 ID 重试）"
							: "未提交：权威记录入口不可达，状态无法更新",
					reason,
					attempts: upserted.record.attempts,
					rootFailure,
					localRecord: upserted.record,
				});
			});
		} catch (error) {
			if (error instanceof IssueStoreError && error.code === "E-ISSUE-STORE-LOCK_BUSY") {
				return makeSubmitResult({
					ok: false,
					code: "lock-busy",
					id: pending.id,
					state: "none",
					submitted: false,
					authorityReachable: false,
					display: ISSUE_DISPLAY_NOT_SUBMITTED,
					message: "未提交（本地锁忙，请稍后同 ID 重试）",
					reason: error.message,
					attempts: 0,
					rootFailure,
				});
			}
			throw error;
		}
	}

	async submit(request: IssueSubmitRequest): Promise<IssueSubmitResult> {
		const validated = this.validateSubmission(request);
		if (validated.result !== null || validated.pending === null) {
			return (
				validated.result ??
				submitRefusal("", "invalid-input", "submission validation produced no result", "提交无效")
			);
		}
		const pending = validated.pending;
		const root = this.resolveRoot();
		if (!root.ok || root.resolved === null) {
			const failure = root.failure;
			return this.writeOfflinePending(
				pending,
				"authority-unavailable",
				failure === null ? "authority root is unavailable" : rootFailureText(failure),
				failure,
				"unavailable",
			);
		}
		const devRoot = root.resolved.canonicalRoot;
		try {
			return await withAuthorityLock(devRoot, this.lockOptions, async () => {
				const state = readAuthorityState(devRoot, pending.id);
				if (state.exists && !authorityMatches(state, pending)) {
					return this.conflictSubmission(pending, "authority log owns this ID with different content", "none", 0);
				}
				return withLocalLock(this.projectRoot, this.lockOptions, () => {
					const index = readLocalIndex(this.projectRoot);
					const existing = findLocalRecord(index, pending.id);
					if (existing && (!localRecordMatches(existing, pending) || existing.state === "conflict")) {
						return this.conflictSubmission(
							pending,
							"local index owns this ID with different content",
							existing.state,
							existing.attempts,
						);
					}
					const diskPending = readPendingCopy(this.projectRoot, pending.id);
					if (
						diskPending !== null &&
						(diskPending.card_sha256 !== pending.card_sha256 ||
							diskPending.submission_digest !== pending.submission_digest ||
							canonicalPayload(diskPending.card) !== canonicalPayload(pending.card))
					) {
						return this.conflictSubmission(
							pending,
							"confirmed pending copy owns this ID with different content",
							existing?.state ?? "none",
							existing?.attempts ?? 0,
						);
					}
					if (!state.exists && existing?.state === "submitted" && existing.authority_ack !== null) {
						throw new IssueStoreError(
							"E-ISSUE-STORE-AUTHORITY_MISSING",
							"local ACK says submitted but the authority log is missing",
							issueAuthorityLogPath(devRoot, pending.id),
						);
					}
					if (state.exists && existing?.state === "submitted" && state.created !== null) {
						return makeSubmitResult({
							ok: true,
							code: "already-submitted",
							id: pending.id,
							state: "submitted",
							submitted: true,
							authorityReachable: true,
							display: ISSUE_DISPLAY_SUBMITTED,
							message: "已提交（本地回执已确认，权威按 ID 查证，无新增记录）",
							reason: "same ID and same canonical card already have an authority created event",
							attempts: existing.attempts,
							verifiedById: true,
							event: state.created,
							localRecord: existing,
						});
					}
					const written = writePendingCopy(this.projectRoot, pending);
					if (!written.ok) {
						return this.conflictSubmission(
							pending,
							written.reason,
							existing?.state ?? "none",
							existing?.attempts ?? 0,
						);
					}
					const inFlight = upsertLocalRecord(
						index,
						pending,
						pending.confirmed_at,
						"in-flight",
						null,
						existing?.authority_ack ?? null,
						true,
					);
					writeLocalIndex(this.projectRoot, inFlight.index);
					let event: IssueAuthorityEvent;
					let created = false;
					let verifiedById = false;
					if (state.exists && state.created !== null) {
						event = state.created;
						verifiedById = true;
					} else {
						event = appendAuthorityEvent(devRoot, pending.id, createdDraftFromPending(pending));
						created = true;
					}
					const commit: IssueAuthorityCommit = { event, created, verifiedById };
					const hookLoss =
						runHook(this.hooks.afterAuthorityCommit, commit) ?? runHook(this.hooks.beforeLocalAck, commit);
					if (hookLoss !== null) {
						return makeSubmitResult({
							ok: false,
							code: "ack-lost",
							id: pending.id,
							state: "in-flight",
							submitted: false,
							authorityReachable: true,
							display: ISSUE_DISPLAY_VERIFY_PENDING,
							message: "待核实：权威写入已发生或已按 ID 查到，但本地回执未确认；请用同一 ID 重试",
							reason: `local ACK fault: ${hookLoss}`,
							attempts: inFlight.record.attempts,
							created,
							verifiedById,
							event,
							localRecord: inFlight.record,
						});
					}
					const final = upsertLocalRecord(
						inFlight.index,
						pending,
						event.at,
						"submitted",
						null,
						ackFromEvent(event),
						false,
					);
					writeLocalIndex(this.projectRoot, final.index);
					removePendingCopy(this.projectRoot, pending.id);
					return makeSubmitResult({
						ok: true,
						code: created ? "submitted" : "already-submitted",
						id: pending.id,
						state: "submitted",
						submitted: true,
						authorityReachable: true,
						display: ISSUE_DISPLAY_SUBMITTED,
						message: created ? "已提交（权威记录已创建）" : "已提交（按 ID 查证，权威未新增记录）",
						reason: created
							? "one created event appended under the authority lock"
							: "existing created event verified by ID",
						attempts: final.record.attempts,
						created,
						verifiedById,
						event,
						localRecord: final.record,
					});
				});
			});
		} catch (error) {
			if (error instanceof IssueStoreError && error.code === "E-ISSUE-STORE-LOCK_BUSY") {
				return this.writeOfflinePending(pending, "lock-busy", error.message, null, "lock-busy");
			}
			if (isAuthorityPreflightFailure(error)) {
				return this.writeOfflinePending(
					pending,
					"authority-unavailable",
					`authority write entry failed before any event was appended: ${errorText(error)}`,
					null,
					"unavailable",
				);
			}
			throw error;
		}
	}

	async retry(request: IssueRetryRequest): Promise<IssueSubmitResult> {
		const { id, actor } = request;
		if (!isIssueId(id)) return submitRefusal(id, "invalid-input", "invalid feedback ID", "反馈 ID 无效");
		const gate = gateWrite(actor, "project", this.projectRoot, this.env);
		if (!gate.ok) return submitRefusal(id, gate.code, gate.reason, `拒绝重试：${gate.reason}`);
		const initialIndex = readLocalIndex(this.projectRoot);
		const initial = findLocalRecord(initialIndex, id);
		if (initial === null) {
			return submitRefusal(
				id,
				"missing-local-record",
				"this project has no local record for the ID",
				"本项目未登记该反馈 ID",
			);
		}
		if (initial.project_label !== actor.projectLabel) {
			return submitRefusal(
				id,
				"foreign-project",
				"local record belongs to another project label",
				"项目标签不匹配，拒绝重试",
			);
		}
		if (initial.state === "conflict") {
			return this.conflictSubmission(initial, "local state is conflict", "conflict", initial.attempts);
		}
		const root = this.resolveRoot();
		if (!root.ok || root.resolved === null) {
			const failure = root.failure;
			try {
				return await withLocalLock(this.projectRoot, this.lockOptions, () => {
					const index = readLocalIndex(this.projectRoot);
					const current = findLocalRecord(index, id);
					if (current === null)
						return submitRefusal(id, "missing-local-record", "record disappeared", "本项目未登记该反馈 ID");
					const nextState = current.state === "submitted" ? "submitted" : "pending";
					const updated = upsertFromRecord(
						index,
						current,
						current.updated_at,
						nextState,
						"unavailable",
						current.authority_ack,
						true,
					);
					writeLocalIndex(this.projectRoot, updated.index);
					const localAck = current.state === "submitted" && current.authority_ack !== null;
					return makeSubmitResult({
						ok: false,
						code: "authority-unavailable",
						id,
						state: nextState,
						submitted: localAck,
						authorityReachable: false,
						display: displayForLocalState(nextState, localAck, false),
						message: localAck
							? "已提交（本地回执）；权威状态无法更新"
							: "未提交：权威记录入口不可达，状态无法更新",
						reason: failure === null ? "authority root is unavailable" : rootFailureText(failure),
						attempts: updated.record.attempts,
						rootFailure: failure,
						localRecord: updated.record,
					});
				});
			} catch (error) {
				if (error instanceof IssueStoreError && error.code === "E-ISSUE-STORE-LOCK_BUSY") {
					return submitRefusal(id, "lock-busy", error.message, "本地锁忙，未提交");
				}
				throw error;
			}
		}
		const devRoot = root.resolved.canonicalRoot;
		try {
			return await withAuthorityLock(devRoot, this.lockOptions, async () => {
				const state = readAuthorityState(devRoot, id);
				if (state.exists && !this.authorityMatchesRecord(state, initial)) {
					return this.conflictSubmission(
						initial,
						"authority log content differs from the local record",
						initial.state,
						initial.attempts,
					);
				}
				const pendingCopy = readPendingCopy(this.projectRoot, id);
				if (
					pendingCopy !== null &&
					(pendingCopy.submission_digest !== initial.submission_digest ||
						pendingCopy.card_sha256 !== initial.card_sha256 ||
						pendingCopy.project_label !== initial.project_label)
				) {
					return this.conflictSubmission(
						pendingCopy,
						"confirmed pending copy differs from the local record",
						initial.state,
						initial.attempts,
					);
				}
				if (!state.exists && pendingCopy === null) {
					return makeSubmitResult({
						ok: false,
						code: "pending-copy-missing",
						id,
						state: initial.state,
						submitted: false,
						authorityReachable: true,
						display: displayForLocalState(initial.state, false, false),
						message: "待核实：本地待发副本缺失，拒绝重新构造一条反馈",
						reason: "no authority event exists and no confirmed pending copy is available",
						attempts: initial.attempts,
						localRecord: initial,
					});
				}
				return withLocalLock(this.projectRoot, this.lockOptions, () => {
					const index = readLocalIndex(this.projectRoot);
					const current = findLocalRecord(index, id);
					if (current === null)
						return submitRefusal(id, "missing-local-record", "record disappeared", "本项目未登记该反馈 ID");
					if (current.project_label !== actor.projectLabel) {
						return submitRefusal(
							id,
							"foreign-project",
							"local record belongs to another project label",
							"项目标签不匹配，拒绝重试",
						);
					}
					if (!state.exists && current.state === "submitted" && current.authority_ack !== null) {
						throw new IssueStoreError(
							"E-ISSUE-STORE-AUTHORITY_MISSING",
							"local ACK says submitted but the authority log is missing",
							issueAuthorityLogPath(devRoot, id),
						);
					}
					if (state.exists && state.created !== null) {
						const event = state.created;
						const final = upsertFromRecord(
							index,
							current,
							event.at,
							"submitted",
							null,
							ackFromEvent(event),
							true,
						);
						writeLocalIndex(this.projectRoot, final.index);
						removePendingCopy(this.projectRoot, id);
						return makeSubmitResult({
							ok: true,
							code: "already-submitted",
							id,
							state: "submitted",
							submitted: true,
							authorityReachable: true,
							display: ISSUE_DISPLAY_SUBMITTED,
							message: "已提交（按 ID 查证，权威未新增记录）",
							reason: "existing created event verified by ID; local ACK repaired only from authority evidence",
							attempts: final.record.attempts,
							verifiedById: true,
							event,
							localRecord: final.record,
						});
					}
					if (pendingCopy === null) {
						return submitRefusal(
							id,
							"pending-copy-missing",
							"confirmed pending copy missing",
							"待发副本缺失，拒绝写入",
						);
					}
					const inFlight = upsertFromRecord(
						index,
						current,
						pendingCopy.confirmed_at,
						"in-flight",
						null,
						current.authority_ack,
						true,
					);
					writeLocalIndex(this.projectRoot, inFlight.index);
					const event = appendAuthorityEvent(devRoot, id, createdDraftFromPending(pendingCopy));
					const commit: IssueAuthorityCommit = { event, created: true, verifiedById: false };
					const hookLoss =
						runHook(this.hooks.afterAuthorityCommit, commit) ?? runHook(this.hooks.beforeLocalAck, commit);
					if (hookLoss !== null) {
						return makeSubmitResult({
							ok: false,
							code: "ack-lost",
							id,
							state: "in-flight",
							submitted: false,
							authorityReachable: true,
							display: ISSUE_DISPLAY_VERIFY_PENDING,
							message: "待核实：权威写入已发生，但本地回执未确认；请用同一 ID 重试",
							reason: `local ACK fault: ${hookLoss}`,
							attempts: inFlight.record.attempts,
							created: true,
							event,
							localRecord: inFlight.record,
						});
					}
					const final = upsertFromRecord(
						inFlight.index,
						current,
						event.at,
						"submitted",
						null,
						ackFromEvent(event),
						false,
					);
					writeLocalIndex(this.projectRoot, final.index);
					removePendingCopy(this.projectRoot, id);
					return makeSubmitResult({
						ok: true,
						code: "submitted",
						id,
						state: "submitted",
						submitted: true,
						authorityReachable: true,
						display: ISSUE_DISPLAY_SUBMITTED,
						message: "已提交（权威记录已创建）",
						reason: "one created event appended from the confirmed pending copy under the authority lock",
						attempts: final.record.attempts,
						created: true,
						event,
						localRecord: final.record,
					});
				});
			});
		} catch (error) {
			if (error instanceof IssueStoreError && error.code === "E-ISSUE-STORE-LOCK_BUSY") {
				return submitRefusal(id, "lock-busy", error.message, "权威/本地锁忙，重试未写入");
			}
			if (isAuthorityPreflightFailure(error)) {
				const current = findLocalRecord(readLocalIndex(this.projectRoot), id);
				if (current === null)
					return submitRefusal(id, "missing-local-record", "record disappeared", "本项目未登记该反馈 ID");
				const localAck = current.state === "submitted" && current.authority_ack !== null;
				const uncertain = current.state === "in-flight" || current.state === "submitted";
				const display =
					uncertain && !localAck
						? ISSUE_DISPLAY_VERIFY_PENDING
						: displayForLocalState(current.state, localAck, false);
				return makeSubmitResult({
					ok: false,
					code: "authority-unavailable",
					id,
					state: current.state,
					submitted: localAck,
					authorityReachable: false,
					display,
					message: uncertain
						? localAck
							? "已提交（本地回执）；权威写入入口暂不可用，状态无法更新"
							: "待核实：权威写入结果未确认，入口暂不可用；请用同一 ID 重试"
						: "未提交：权威记录入口不可达，状态无法更新",
					reason: `authority write entry failed before a new event could be appended: ${errorText(error)}`,
					attempts: current.attempts,
					localRecord: current,
				});
			}
			throw error;
		}
	}

	async appendProgress(request: IssueProgressRequest): Promise<IssueMutationResult> {
		const { id, actor, update, preview, confirmation } = request;
		if (!isIssueId(id))
			return makeMutationResult({
				ok: false,
				code: "invalid-input",
				id,
				authorityReachable: false,
				message: "反馈 ID 无效",
				reason: "invalid feedback ID",
			});
		const knownSecrets = request.knownSecrets ?? [];
		const at = isInstant(confirmation.confirmedAt) ? confirmation.confirmedAt : ZERO_INSTANT;
		const source: IssueEventSource = "dev-pm";
		const context: IssueProgressPreviewContext = { id, at, source, by: actor.by };
		const expectedPreview = renderDevUpdatePreview(update, context);
		const fullUpdate: DevUpdate = { at, by: actor.by, ...update };
		const previewGate = validatePreviewConfirmation(
			preview,
			expectedPreview,
			confirmation,
			{ update: fullUpdate, context },
			knownSecrets,
		);
		if (!previewGate.ok) {
			return makeMutationResult({
				ok: false,
				code: previewGate.code,
				id,
				authorityReachable: false,
				message: "开发进展未写入",
				reason: previewGate.reason,
			});
		}
		const root = this.resolveRoot();
		if (!root.ok || root.resolved === null) {
			const failure = root.failure;
			return makeMutationResult({
				ok: false,
				code: "authority-unavailable",
				id,
				authorityReachable: false,
				message: "开发进展未写入：权威记录入口不可达，状态无法更新",
				reason: failure === null ? "authority root is unavailable" : rootFailureText(failure),
				rootFailure: failure,
			});
		}
		const devRoot = root.resolved.canonicalRoot;
		const gate = gateWrite(actor, "dev", devRoot, this.env);
		if (!gate.ok) {
			return makeMutationResult({
				ok: false,
				code: gate.code,
				id,
				authorityReachable: true,
				message: "拒绝开发进展写入",
				reason: gate.reason,
			});
		}
		try {
			return await withAuthorityLock(devRoot, this.lockOptions, () => {
				const state = readAuthorityState(devRoot, id);
				if (
					!state.exists ||
					!state.created ||
					!state.card ||
					state.submissionDigest === null ||
					state.projectLabel === null
				) {
					throw new IssueStoreError(
						"E-ISSUE-STORE-AUTHORITY_MISSING",
						"development progress cannot create a new issue",
						issueAuthorityLogPath(devRoot, id),
					);
				}
				const draft: IssueAuthorityEventDraft = {
					schema: ISSUE_STORE_SCHEMA,
					kind: "dev_update",
					id,
					seq: state.lastSeq + 1,
					prev_sha256: state.lastSha256,
					submission_digest: state.submissionDigest,
					project_label: state.projectLabel,
					at,
					source,
					by: actor.by,
					update: fullUpdate,
				};
				let nextCard: IssueCard;
				try {
					nextCard = appendDevUpdate(state.card, fullUpdate, [], "canonical");
				} catch (error) {
					throw new IssueStoreError(
						"E-ISSUE-STORE-CORRUPT",
						`model rejected update: ${errorText(error)}`,
						issueAuthorityLogPath(devRoot, id),
					);
				}
				const event = appendAuthorityEvent(devRoot, id, draft);
				return makeMutationResult({
					ok: true,
					code: "written",
					id,
					authorityReachable: true,
					message: "开发进展已写入同一反馈 ID（附时间与来源）",
					reason: `seq ${event.seq} appended`,
					event,
					card: nextCard,
					seq: event.seq,
				});
			});
		} catch (error) {
			if (error instanceof IssueStoreError && error.code === "E-ISSUE-STORE-LOCK_BUSY") {
				return makeMutationResult({
					ok: false,
					code: "lock-busy",
					id,
					authorityReachable: true,
					message: "开发进展未写入：锁忙",
					reason: error.message,
				});
			}
			throw error;
		}
	}

	async reply(request: IssueReplyRequest): Promise<IssueMutationResult> {
		const { id, actor, reply, preview, confirmation } = request;
		if (!isIssueId(id))
			return makeMutationResult({
				ok: false,
				code: "invalid-input",
				id,
				authorityReachable: false,
				message: "反馈 ID 无效",
				reason: "invalid feedback ID",
			});
		const gate = gateWrite(actor, "project", this.projectRoot, this.env);
		if (!gate.ok) {
			return makeMutationResult({
				ok: false,
				code: gate.code,
				id,
				authorityReachable: false,
				message: "拒绝项目回复",
				reason: gate.reason,
			});
		}
		if (reply.source !== "user" || !nonblank(reply.text) || !nullableText(reply.inReplyTo)) {
			return makeMutationResult({
				ok: false,
				code: "invalid-input",
				id,
				authorityReachable: false,
				message: "回复必须来自已确认用户且带有效引用",
				reason: "reply fields invalid",
			});
		}
		const local = findLocalRecord(readLocalIndex(this.projectRoot), id);
		if (local === null) {
			return makeMutationResult({
				ok: false,
				code: "not-owned",
				id,
				authorityReachable: false,
				message: "当前项目未登记该反馈 ID",
				reason: "reply cannot read a foreign authority ID",
			});
		}
		if (local.project_label !== actor.projectLabel) {
			return makeMutationResult({
				ok: false,
				code: "foreign-project",
				id,
				authorityReachable: false,
				message: "项目标签不匹配",
				reason: "reply belongs to another project",
			});
		}
		const knownSecrets = request.knownSecrets ?? [];
		const at = isInstant(confirmation.confirmedAt) ? confirmation.confirmedAt : ZERO_INSTANT;
		const source: IssueEventSource = "project-pm";
		const context: IssueReplyPreviewContext = { id, at, source, by: actor.by };
		const expectedPreview = renderReporterReplyPreview(reply, context);
		const fullReply: ReporterReply = { at, text: reply.text, source: reply.source, inReplyTo: reply.inReplyTo };
		const previewGate = validatePreviewConfirmation(
			preview,
			expectedPreview,
			confirmation,
			{ reply: fullReply, context },
			knownSecrets,
		);
		if (!previewGate.ok) {
			return makeMutationResult({
				ok: false,
				code: previewGate.code,
				id,
				authorityReachable: false,
				message: "项目回复未写入",
				reason: previewGate.reason,
			});
		}
		const root = this.resolveRoot();
		if (!root.ok || root.resolved === null) {
			const failure = root.failure;
			return makeMutationResult({
				ok: false,
				code: "authority-unavailable",
				id,
				authorityReachable: false,
				message: "项目回复未写入：权威记录入口不可达，状态无法更新",
				reason: failure === null ? "authority root is unavailable" : rootFailureText(failure),
				rootFailure: failure,
			});
		}
		const devRoot = root.resolved.canonicalRoot;
		try {
			return await withAuthorityLock(devRoot, this.lockOptions, () => {
				const state = readAuthorityState(devRoot, id);
				if (!state.exists || !state.card || state.submissionDigest === null || state.projectLabel === null) {
					throw new IssueStoreError(
						"E-ISSUE-STORE-AUTHORITY_MISSING",
						"a project reply cannot create a new issue",
						issueAuthorityLogPath(devRoot, id),
					);
				}
				if (!this.authorityMatchesRecord(state, local)) {
					return makeMutationResult({
						ok: false,
						code: "duplicate-conflict",
						id,
						authorityReachable: true,
						message: "回复未写入：权威内容与本地 ID 冲突",
						reason: "authority digest/hash/project label differs from the local record",
					});
				}
				if (reply.inReplyTo !== null) {
					const known = state.events.some(
						(event) => event.sha256 === reply.inReplyTo || event.at === reply.inReplyTo,
					);
					if (!known) {
						return makeMutationResult({
							ok: false,
							code: "invalid-input",
							id,
							authorityReachable: true,
							message: "回复对象不是该反馈的已知事件",
							reason: "inReplyTo must reference an event hash or time",
						});
					}
				}
				const draft: IssueAuthorityEventDraft = {
					schema: ISSUE_STORE_SCHEMA,
					kind: "reporter_reply",
					id,
					seq: state.lastSeq + 1,
					prev_sha256: state.lastSha256,
					submission_digest: state.submissionDigest,
					project_label: state.projectLabel,
					at,
					source,
					by: actor.by,
					reply: fullReply,
				};
				let nextCard: IssueCard;
				try {
					nextCard = appendReporterReply(state.card, fullReply, [], "canonical");
				} catch (error) {
					throw new IssueStoreError(
						"E-ISSUE-STORE-CORRUPT",
						`model rejected reply: ${errorText(error)}`,
						issueAuthorityLogPath(devRoot, id),
					);
				}
				const event = appendAuthorityEvent(devRoot, id, draft);
				return makeMutationResult({
					ok: true,
					code: "written",
					id,
					authorityReachable: true,
					message: "项目回复已写入同一反馈 ID（附时间与来源，未新建问题）",
					reason: `seq ${event.seq} appended`,
					event,
					card: nextCard,
					seq: event.seq,
				});
			});
		} catch (error) {
			if (error instanceof IssueStoreError && error.code === "E-ISSUE-STORE-LOCK_BUSY") {
				return makeMutationResult({
					ok: false,
					code: "lock-busy",
					id,
					authorityReachable: true,
					message: "项目回复未写入：锁忙",
					reason: error.message,
				});
			}
			throw error;
		}
	}

	status(request: IssueStatusRequest): IssueStatusResult {
		const { id, actor } = request;
		if (!isIssueId(id)) {
			return makeStatusResult({
				ok: false,
				code: "invalid-input",
				id,
				authorityReachable: false,
				authorityVerifiedById: false,
				localAck: false,
				localState: "none",
				submitted: false,
				display: ISSUE_DISPLAY_UNKNOWN,
				message: "反馈 ID 无效",
				reason: "invalid feedback ID",
				text: "反馈 ID 无效",
			});
		}
		const gate = gateProjectRead(actor, this.projectRoot);
		if (!gate.ok) {
			return makeStatusResult({
				ok: false,
				code: gate.code,
				id,
				authorityReachable: false,
				authorityVerifiedById: false,
				localAck: false,
				localState: "none",
				submitted: false,
				display: ISSUE_DISPLAY_REFUSED,
				message: `拒绝查询：${gate.reason}`,
				reason: gate.reason,
				text: `拒绝查询：${gate.reason}`,
			});
		}
		const local = findLocalRecord(readLocalIndex(this.projectRoot), id);
		if (local === null) {
			return makeStatusResult({
				ok: false,
				code: "not-owned",
				id,
				authorityReachable: false,
				authorityVerifiedById: false,
				localAck: false,
				localState: "none",
				submitted: false,
				display: ISSUE_DISPLAY_UNKNOWN,
				message: "当前项目未登记该反馈 ID",
				reason: "foreign or unknown ID is not read from authority",
				text: "当前项目未登记该反馈 ID",
			});
		}
		if (local.project_label !== actor.projectLabel) {
			return makeStatusResult({
				ok: false,
				code: "foreign-project",
				id,
				authorityReachable: false,
				authorityVerifiedById: false,
				localAck: false,
				localState: "none",
				submitted: false,
				display: ISSUE_DISPLAY_REFUSED,
				message: "项目标签不匹配",
				reason: "local record belongs to another project",
				text: "项目标签不匹配",
			});
		}
		const localAck = local.state === "submitted" && local.authority_ack !== null;
		const root = this.resolveRoot();
		if (!root.ok || root.resolved === null) {
			const failure = root.failure;
			const display = displayForLocalState(local.state, localAck, false);
			return makeStatusResult({
				ok: false,
				code: "authority-unavailable",
				id,
				authorityReachable: false,
				authorityVerifiedById: false,
				localAck,
				localState: local.state,
				submitted: localAck,
				display,
				message: localAck ? "已提交（本地回执）；权威状态无法更新" : "未提交：权威记录入口不可达，状态无法更新",
				reason: failure === null ? "authority root is unavailable" : rootFailureText(failure),
				text: `${ISSUE_AUTHORITY_UNAVAILABLE_TEXT}；不展示过期开发进展。本地状态：${display}`,
				localRecord: local,
				rootFailure: failure,
			});
		}
		const devRoot = root.resolved.canonicalRoot;
		const state = readAuthorityState(devRoot, id);
		if (!state.exists || state.card === null) {
			if (localAck) {
				throw new IssueStoreError(
					"E-ISSUE-STORE-AUTHORITY_MISSING",
					"local ACK says submitted but the authority log is missing",
					issueAuthorityLogPath(devRoot, id),
				);
			}
			const display = displayForLocalState(local.state, false, false);
			return makeStatusResult({
				ok: false,
				code: "authority-missing",
				id,
				authorityReachable: true,
				authorityVerifiedById: false,
				localAck: false,
				localState: local.state,
				submitted: false,
				display,
				message: "未提交/待核实：权威尚无该 ID 的记录",
				reason: "no created event exists for this local ID",
				text: `权威尚无该 ID 的记录；本地状态：${display}。不展示过期开发进展。`,
				localRecord: local,
			});
		}
		if (!this.authorityMatchesRecord(state, local)) {
			return makeStatusResult({
				ok: false,
				code: "duplicate-conflict",
				id,
				authorityReachable: true,
				authorityVerifiedById: true,
				localAck,
				localState: local.state,
				submitted: localAck,
				display: ISSUE_DISPLAY_CONFLICT,
				message: "冲突：权威内容与本地 ID 不一致，拒绝覆盖",
				reason: "authority digest/hash/project label differs from the local record",
				text: "冲突：权威内容与本地 ID 不一致；不展示过期开发进展。",
				localRecord: local,
			});
		}
		const evidence = request.localEvidence ?? defaultLocalEvidence();
		const projection = projectForUser(state.card, evidence);
		const display = displayForLocalState(local.state, localAck, true);
		const message = localAck
			? "已提交（本地回执已确认）"
			: "待核实：权威已按 ID 查到，但本地回执未确认；请同 ID 重试";
		return makeStatusResult({
			ok: true,
			code: "ok",
			id,
			authorityReachable: true,
			authorityVerifiedById: true,
			localAck,
			localState: local.state,
			submitted: localAck,
			display,
			message,
			reason: "live authority event log replayed through the accepted model",
			text: `- 本地回执: ${display}\n${projection.text}`,
			localRecord: local,
			card: state.card,
			projection,
			development: latestDevState(state.card),
			pendingQuestion: pendingQuestion(state.card),
			localEffective: projection.localEffective,
			events: state.events,
		});
	}

	list(request: IssueListRequest): IssueListResult {
		const { actor } = request;
		const gate = gateProjectRead(actor, this.projectRoot);
		if (!gate.ok) {
			return {
				ok: false,
				code: gate.code,
				authorityReachable: false,
				rows: [],
				message: `拒绝查询：${gate.reason}`,
				reason: gate.reason,
				rootFailure: null,
			};
		}
		const index = readLocalIndex(this.projectRoot);
		if (index.records.length === 0) {
			return {
				ok: true,
				code: "ok",
				authorityReachable: false,
				rows: [],
				message: "本项目未登记反馈 ID",
				reason: "empty local index",
				rootFailure: null,
			};
		}
		const root = this.resolveRoot();
		if (!root.ok || root.resolved === null) {
			const failure = root.failure;
			const rows: IssueStoreListRow[] = index.records.map((record) => ({
				id: record.id,
				title: UNKNOWN,
				status: UNKNOWN,
				updatedAt: null,
				needsReply: false,
				localState: record.state,
				submitted: record.state === "submitted" && record.authority_ack !== null,
				authorityVerified: false,
			}));
			return {
				ok: false,
				code: "authority-unavailable",
				authorityReachable: false,
				rows,
				message: "仅列本项目登记的 ID；权威状态无法更新",
				reason: failure === null ? "authority root is unavailable" : rootFailureText(failure),
				rootFailure: failure,
			};
		}
		const devRoot = root.resolved.canonicalRoot;
		const rows: IssueStoreListRow[] = [];
		const cards: IssueCard[] = [];
		for (const record of index.records) {
			const state = readAuthorityState(devRoot, record.id);
			const submitted = record.state === "submitted" && record.authority_ack !== null;
			if (!state.exists || state.card === null) {
				if (submitted) {
					throw new IssueStoreError(
						"E-ISSUE-STORE-AUTHORITY_MISSING",
						"local ACK says submitted but the authority log is missing",
						issueAuthorityLogPath(devRoot, record.id),
					);
				}
				rows.push({
					id: record.id,
					title: UNKNOWN,
					status: UNKNOWN,
					updatedAt: null,
					needsReply: false,
					localState: record.state,
					submitted: false,
					authorityVerified: false,
				});
				continue;
			}
			if (!this.authorityMatchesRecord(state, record)) {
				corrupt("authority record differs from the local index", issueAuthorityLogPath(devRoot, record.id));
			}
			if (state.card.projectLabel !== actor.projectLabel) {
				corrupt("authority card belongs to another project", issueAuthorityLogPath(devRoot, record.id));
			}
			const summary = summarizeForList(state.card);
			cards.push(state.card);
			rows.push({
				...summary,
				localState: record.state,
				submitted,
				authorityVerified: true,
			});
		}
		const projected = listIssuesForProject(cards, actor.projectLabel);
		const expected = cards.map((card) => summarizeForList(card));
		if (stableStringify(projected) !== stableStringify(expected)) {
			corrupt("model project-list projection dropped or added a foreign ID", issueAuthorityBasePath(devRoot));
		}
		return {
			ok: true,
			code: "ok",
			authorityReachable: true,
			rows,
			message: "仅列本项目登记的 ID；开发状态来自实时权威回放",
			reason: `local_ids=${index.records.length} authority_cards=${cards.length} foreign=0`,
			rootFailure: null,
		};
	}

	// ── T-09B: dev-authority incoming reads (D002), read-only, dev window only ─

	/** Dev read identity: the store's canonical current-project root must BE the
	 * explicitly bound + marker-validated dev root (`mode=local`). An ordinary
	 * project that merely holds a pointer resolves `mode=external` and is refused
	 * here; a worker env, a non-PM/dev/untrusted actor and a foreign actor root
	 * are refused BEFORE any authority file is read. No wrong-root fallback. */
	private incomingGate(
		actor: IssueStoreActor,
	):
		| { ok: true; devRoot: string }
		| { ok: false; code: IssueIncomingCode; reason: string; rootFailure: IssueDevRootFailure | null } {
		if (nonblank(this.env.PI_WORKER_TASK)) {
			return {
				ok: false,
				code: "worker-forbidden",
				reason: "PI_WORKER_TASK is present; worker/headless windows cannot read the dev inbox",
				rootFailure: null,
			};
		}
		if (actor.role !== "pm" || actor.scope !== "dev" || actor.trustedWindow !== true) {
			return {
				ok: false,
				code: "untrusted-window",
				reason:
					"incoming reads require a real PM/TUI dev window; an ordinary project or a model claim is not a dev read identity",
				rootFailure: null,
			};
		}
		if (!nonblank(actor.projectLabel) || !nonblank(actor.by) || !actorHasNoSecrets(actor)) {
			return {
				ok: false,
				code: "invalid-input",
				reason: "actor label/by is missing or credential-shaped",
				rootFailure: null,
			};
		}
		const actorRoot = canonicalizedActorRoot(actor);
		if (actorRoot === null || fold(actorRoot) !== fold(this.projectRoot)) {
			return {
				ok: false,
				code: "foreign-project",
				reason: "dev actor root does not equal the store's canonical current project root",
				rootFailure: null,
			};
		}
		let root: RootResolution;
		try {
			root = this.resolveRoot();
		} catch (error) {
			return {
				ok: false,
				code: "corrupt",
				reason: `explicit dev root resolution failed: ${errorText(error)}`,
				rootFailure: null,
			};
		}
		if (!root.ok || root.resolved === null) {
			const failure = root.failure;
			return {
				ok: false,
				code: "authority-unavailable",
				reason: failure === null ? "authority root is unavailable" : rootFailureText(failure),
				rootFailure: failure,
			};
		}
		const devRoot = root.resolved.canonicalRoot;
		if (root.resolved.mode !== "local" || fold(devRoot) !== fold(this.projectRoot)) {
			return {
				ok: false,
				code: "foreign-project",
				reason:
					"the current canonical root is not the explicitly validated MW dev repo root (mode=external); an ordinary project's pointer is not a dev read identity",
				rootFailure: null,
			};
		}
		return { ok: true, devRoot };
	}

	/** Read-only events directory derived ONLY from the validated dev root. No
	 * mkdir, no lock, no repair: a link/junction/outside-tree segment throws an
	 * explicit E-ISSUE-STORE-CORRUPT. */
	private incomingEventsParent(devRoot: string): string | null {
		return validateSafeDirectory(devRoot, [...ISSUE_AUTHORITY_DIR_PARTS, ISSUE_EVENTS_DIR_BASENAME], false);
	}

	/** Enumerate the dev authority's incoming cards. Each entry is strictly
	 * validated and fully replayed through the accepted hash chain: ONE bad
	 * entry or card makes the WHOLE enumeration fail, never a silently filtered
	 * \"complete\" list. No project local index, ACK, state or install claim. */
	listIncoming(request: IssueIncomingListRequest): IssueIncomingListResult {
		const gate = this.incomingGate(request.actor);
		if (!gate.ok) return incomingListRefusal(gate.code, "拒绝读取开发收件箱", gate.reason, gate.rootFailure);
		try {
			const parent = this.incomingEventsParent(gate.devRoot);
			if (parent === null) {
				return incomingListRefusal(
					"authority-unavailable",
					"无法枚举权威收件：events 目录缺失或不可达（纯读未创建任何目录）",
					"incoming events directory is missing or unreachable; no directory/lock/index was created",
				);
			}
			const entries = fs.readdirSync(parent, { withFileTypes: true });
			entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
			const rows: IssueIncomingRow[] = [];
			for (const entry of entries) {
				const match = ISSUE_INCOMING_LOG_RE.exec(entry.name);
				if (match === null || entry.isSymbolicLink() || !entry.isFile()) {
					return incomingListRefusal(
						"corrupt",
						"收件目录含非法项，拒绝把剩余卡当作完整列表",
						`incoming events entry '${entry.name}' is not a strict <fb-...>.jsonl regular file (link/directory/stray name refused)`,
					);
				}
				const id = match[1] ?? "";
				if (!isIssueId(id))
					corrupt("incoming log basename is not a valid feedback ID", path.join(parent, entry.name));
				const file = issueAuthorityLogPath(gate.devRoot, id);
				if (!assertSafeRegularFile(parent, file)) {
					corrupt("incoming authority log is not a safe regular file inside the events directory", file);
				}
				const state = readAuthorityState(gate.devRoot, id);
				if (!state.exists || state.card === null || state.projectLabel === null) {
					corrupt("incoming authority log has no verified created event", file);
				}
				rows.push({ ...summarizeForList(state.card), projectLabel: state.projectLabel });
			}
			return {
				ok: true,
				code: "ok",
				rows,
				message: `权威收件：${rows.length} 张问题卡（仅经核验开发窗口；只读 events 目录）`,
				reason: `incoming_ids=${rows.length} authority_source=events pure_read=1 local_index_writes=0`,
				rootFailure: null,
			};
		} catch (error) {
			if (error instanceof IssueStoreError) {
				return incomingListRefusal("corrupt", "收件卡/目录损坏，未执行任何静默修复", error.message);
			}
			throw error;
		}
	}

	/** Read ONE incoming card + its whole verified timeline. The ID/path is
	 * derived from the validated dev root, never from a caller-supplied target;
	 * a missing/broken/linked log is an explicit unknown/error with no fallback
	 * to a foreign project's cwd, local index or a stored snapshot. */
	readIncoming(request: IssueIncomingReadRequest): IssueIncomingReadResult {
		const { id } = request;
		if (!isIssueId(id)) {
			return incomingReadRefusal(id, "invalid-input", "反馈 ID 无效", "invalid feedback ID");
		}
		const gate = this.incomingGate(request.actor);
		if (!gate.ok) {
			return incomingReadRefusal(id, gate.code, "拒绝读取开发收件箱", gate.reason, gate.rootFailure);
		}
		try {
			const parent = this.incomingEventsParent(gate.devRoot);
			if (parent === null) {
				return incomingReadRefusal(
					id,
					"authority-unavailable",
					"无法打开权威收件：events 目录缺失或不可达（纯读未创建任何目录）",
					"incoming events directory is missing or unreachable; no directory/lock/index was created",
				);
			}
			const file = issueAuthorityLogPath(gate.devRoot, id);
			if (!assertSafeRegularFile(parent, file)) {
				return incomingReadRefusal(
					id,
					"authority-missing",
					"权威收件箱无该 ID 的问题卡（显式未知）",
					"no verified incoming authority log for this ID; no local index/cwd/ACK fallback",
				);
			}
			const state = readAuthorityState(gate.devRoot, id);
			if (!state.exists || state.card === null) {
				corrupt("incoming authority log has no verified created event", file);
			}
			// In-memory replay ONLY: questionEventHashes is an enumerable projection
			// that JSON.stringify WOULD include, so this card is never hashed,
			// previewed as canonical bytes or persisted by this read path.
			const card = state.card;
			const pending = pendingQuestion(card);
			const text = [
				"以下为权威事件链严格回放后的完整脱敏问题卡（与用户确认时同一确定性渲染；仅内存投影，原始 created 字节与事件链未改动）：",
				renderPreview(card),
			].join("\n");
			return {
				ok: true,
				code: "ok",
				id,
				message: "已只读打开权威问题卡与时间线",
				reason: `events=${state.events.length} pending_question=${pending === null ? "none" : "present"} pure_read=1`,
				text,
				projectLabel: state.projectLabel,
				card,
				events: state.events,
				development: latestDevState(card),
				pendingQuestion: pending,
				rootFailure: null,
			};
		} catch (error) {
			if (error instanceof IssueStoreError) {
				return incomingReadRefusal(id, "corrupt", "收件卡/目录损坏，未执行任何静默修复", error.message);
			}
			throw error;
		}
	}
}

function incomingListRefusal(
	code: IssueIncomingCode,
	message: string,
	reason: string,
	rootFailure: IssueDevRootFailure | null = null,
): IssueIncomingListResult {
	return { ok: false, code, rows: [], message, reason, rootFailure };
}

function incomingReadRefusal(
	id: string,
	code: IssueIncomingCode,
	message: string,
	reason: string,
	rootFailure: IssueDevRootFailure | null = null,
): IssueIncomingReadResult {
	return {
		ok: false,
		code,
		id,
		message,
		reason,
		text: [
			`# MW 开发仓收件箱 — ${message}`,
			`- 反馈 ID: ${id}`,
			`- 结果: ${code}`,
			`- 原因: ${reason}`,
			"- 纯读：未创建目录/锁/本地索引，未修改权威或时间线；不回退错根。",
			rootFailure === null ? "" : `- 权威根定位失败: ${rootFailureText(rootFailure)}`,
		].join("\n"),
		projectLabel: null,
		card: null,
		events: [],
		development: null,
		pendingQuestion: null,
		rootFailure,
	};
}
