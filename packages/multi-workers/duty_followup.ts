import { createHash, randomUUID } from "node:crypto";
import {
	closeSync,
	existsSync,
	lstatSync,
	mkdirSync,
	opendirSync,
	openSync,
	readFileSync,
	readSync,
	realpathSync,
	renameSync,
	rmSync,
	type Stats,
	writeFileSync,
} from "node:fs";
import { basename, isAbsolute, join, relative, sep } from "node:path";
import { MW_FOLLOWUP_SOURCE, type PmChannel } from "../coding-agent/src/extensions/agent-team-loop/pm/codex-channel.ts";
import { keyNameRefusal, normalizeKey } from "../coding-agent/src/extensions/agent-team-loop/shared/index-store.ts";
import {
	type WorkerEntry,
	workerOwnerKey,
} from "../coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts";
import { StopWatch } from "./pm_watch.ts";

export interface FollowupTarget {
	project: string;
	key: string;
	claim: string;
	binding: string;
	session: string;
}

export type FollowupNoticeKind = "stop" | "no-progress" | "suspended";

export interface FollowupNotice {
	id: string;
	kind: FollowupNoticeKind;
	summary: string;
}

export interface FollowupEvidenceCandidate {
	path: string;
	sha256: string;
	size: number;
	mtimeMs: number;
}

export interface FollowupStop {
	id: string;
	state: string;
	detail: string;
	fingerprint: string;
	evidenceFingerprint: string;
	evidence: FollowupEvidenceCandidate[];
	stableSince: number;
	createdAt: number;
	noticeCreated: boolean;
	noticeEmitted: boolean;
	noProgressCreated: boolean;
	noProgressEmitted: boolean;
	followUpId?: string;
}

export interface FollowupOutbox {
	id: string;
	stopId: string;
	pinned: string;
	body: string;
	createdAt: number;
	updatedAt: number;
	attempts: number;
	transport: string;
	receiptState: string;
	uncertain: boolean;
	lastError?: string;
}

export interface FollowupNoticeRecord {
	notice: FollowupNotice;
	stopId: string | null;
	createdAt: number;
	emitted: boolean;
	emittedAt?: number;
	emitError?: string;
	cancelled?: boolean;
}

export interface FollowupDiagnosis {
	id: string;
	reason: string;
	createdAt: number;
	emitted: boolean;
}

interface FollowupLedger {
	schema: string;
	version: number;
	pinned: string;
	activeStopId: string | null;
	stableSince: number | null;
	lastState: string | null;
	lastDetail: string;
	stops: FollowupStop[];
	outbox: FollowupOutbox[];
	notices: FollowupNoticeRecord[];
	diagnoses: FollowupDiagnosis[];
}

export interface FollowupStopView {
	id: string;
	state: string;
	detail: string;
	fingerprint: string;
	evidenceFingerprint: string;
	evidenceCandidates: string[];
	stableSince: number;
	createdAt: number;
	noticeEmitted: boolean;
	noProgressEmitted: boolean;
	followUpId: string | null;
}

export interface FollowupOutboxView {
	id: string;
	stopId: string;
	transport: string;
	receiptState: string;
	uncertain: boolean;
	attempts: number;
	createdAt: number;
	updatedAt: number;
	body: string;
	lastError: string | null;
}

export interface FollowupReceiptView {
	id: string;
	stopId: string;
	state: string;
	transport: string;
	uncertain: boolean;
	requestPath: string;
	receiptPath: string;
	businessProgress: "unverified";
}

export interface FollowupStatus {
	mode: "followup";
	target: FollowupTarget;
	pinned: string;
	observedState: string;
	state: string;
	detail: string;
	activity: string;
	stableSince: number | null;
	stableMs: number;
	idleSince: number | null;
	idleMs: number;
	sendAllowed: boolean;
	suspended: boolean;
	diagnosis: string | null;
	businessProgress: "unverified";
	activeStopId: string | null;
	stop: FollowupStopView | null;
	notices: FollowupNotice[];
	pendingNotices: FollowupNotice[];
	emittedNotices: FollowupNotice[];
	outbox: FollowupOutboxView[];
	receipts: FollowupReceiptView[];
	evidenceCandidates: string[];
	evidenceFingerprint: string;
	evidenceObservation: {
		partial: boolean;
		scannedEntries: number;
		maxCandidates: number;
		maxScanEntries: number;
		maxDepth: number;
		largeFilePrefixBytes: number;
		fullFileLimitBytes: number;
	};
	deliveryBlockedBy: string | null;
	ledgerPath: string;
	source: typeof MW_FOLLOWUP_SOURCE;
}

export interface FollowupSendResult {
	ok: boolean;
	id: string;
	stopId: string;
	requestPath: string;
	body: string;
	source: typeof MW_FOLLOWUP_SOURCE;
	transport: string;
	receiptState: string;
	receipt: Record<string, unknown> | null;
	uncertain: boolean;
	idempotent: boolean;
	businessProgress: "unverified";
	message: string;
}

interface LiveIdentity {
	key: string;
	status: string;
	phase: string;
	claim: string;
	connected: boolean;
	binding: string | undefined;
	session: string | undefined;
	activity: string;
}

interface SampleView {
	state: string;
	detail: string;
}

interface EvidenceSnapshot {
	partial: boolean;
	scannedEntries: number;
	fingerprint: string;
	candidates: FollowupEvidenceCandidate[];
	queueFacts: string[];
	paths: string[];
}

interface ValidatedReceipt {
	id: string;
	key: string;
	binding: string;
	state: string;
	raw: Record<string, unknown>;
}

type PmChannelStatus = ReturnType<PmChannel["status"]>;
type WatchSample = ReturnType<StopWatch["sample"]>;

const SCHEMA = "mw-duty-followup-v1";
const IDLE_MS = 45_000;
const MAX_NOTE_BYTES = 1_600;
const MAX_BODY_BYTES = 16_384;
const MAX_SUMMARY_BYTES = 700;
const MAX_ERROR_BYTES = 300;
const MAX_EVIDENCE_FILE_BYTES = 256 * 1024;
const MAX_EVIDENCE_READ_BYTES = 64 * 1024;
const MAX_CANDIDATES = 128;
const MAX_SCAN_ENTRIES = 512;
const MAX_SCAN_DEPTH = 4;
const MAX_STOPS = 64;
const MAX_OUTBOX = 64;
const MAX_NOTICES = 64;
const MAX_DIAGNOSES = 16;
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const HEX64 = /^[a-f0-9]{64}$/;
const NOTICE_KINDS: readonly string[] = ["stop", "no-progress", "suspended"];
const RECEIPT_STATES: readonly string[] = ["queued", "received", "started", "failed", "unconfirmed", "rejected"];
const TRANSPORT_STATES: readonly string[] = ["reserved", ...RECEIPT_STATES, "uncertain", "conflict", "refused"];
const RECEIPT_FIELDS: readonly string[] = [
	"id",
	"key",
	"binding",
	"claim",
	"session",
	"state",
	"receivedAt",
	"observedAt",
	"observation",
	"stage_digest",
];
const TERMINAL_WORKER_STATUSES: readonly string[] = ["done", "failed", "needs-clarification", "lost", "cancelled"];
const STOP_ELIGIBLE_STATES = new Set(["idle", "worker-lost"]);
const SUSPENDED_SAMPLE_STATES = new Set(["offline", "binding-changed", "finished", "unobservable"]);
const SHARING_CODES = new Set(["EPERM", "EACCES", "EBUSY"]);
const SKIP_DIRECTORIES = new Set([".git", ".mw", ".mw-pm-channel", "dist", "node_modules"]);

function errorText(error: unknown): string {
	return error instanceof Error ? error.message : String(error);
}

function sha256(value: unknown): string {
	return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function bounded(value: string, maxBytes: number): string {
	const bytes = Buffer.from(value, "utf8");
	if (bytes.byteLength <= maxBytes) return value;
	let result = bytes.subarray(0, maxBytes).toString("utf8");
	while (Buffer.byteLength(result, "utf8") > maxBytes) result = result.slice(0, -1);
	return result;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactRecord(value: unknown, allowed: readonly string[], label: string): Record<string, unknown> {
	if (!isRecord(value)) throw Error(`Malformed follow-up ${label}: expected an object`);
	for (const key of Object.keys(value))
		if (!allowed.includes(key)) throw Error(`Malformed follow-up ${label}: unexpected field ${key}`);
	return value;
}

function strictString(record: Record<string, unknown>, key: string, label: string): string {
	const value = record[key];
	if (typeof value !== "string") throw Error(`Malformed follow-up ${label}.${key}: expected string`);
	return value;
}

function optionalString(record: Record<string, unknown>, key: string, label: string): string | undefined {
	const value = record[key];
	if (value === undefined) return undefined;
	if (typeof value !== "string") throw Error(`Malformed follow-up ${label}.${key}: expected string`);
	return value;
}

function nullableString(record: Record<string, unknown>, key: string, label: string): string | null {
	const value = record[key];
	if (value === null) return null;
	if (typeof value !== "string") throw Error(`Malformed follow-up ${label}.${key}: expected string or null`);
	return value;
}

function strictNumber(record: Record<string, unknown>, key: string, label: string): number {
	const value = record[key];
	if (typeof value !== "number" || !Number.isFinite(value))
		throw Error(`Malformed follow-up ${label}.${key}: expected finite number`);
	return value;
}

function strictInteger(record: Record<string, unknown>, key: string, label: string): number {
	const value = strictNumber(record, key, label);
	if (!Number.isSafeInteger(value) || value < 0)
		throw Error(`Malformed follow-up ${label}.${key}: expected non-negative integer`);
	return value;
}

function nullableNumber(record: Record<string, unknown>, key: string, label: string): number | null {
	const value = record[key];
	if (value === null) return null;
	if (typeof value !== "number" || !Number.isFinite(value))
		throw Error(`Malformed follow-up ${label}.${key}: expected finite number or null`);
	return value;
}

function optionalNumber(record: Record<string, unknown>, key: string, label: string): number | undefined {
	const value = record[key];
	if (value === undefined) return undefined;
	if (typeof value !== "number" || !Number.isFinite(value))
		throw Error(`Malformed follow-up ${label}.${key}: expected finite number`);
	return value;
}

function strictBoolean(record: Record<string, unknown>, key: string, label: string): boolean {
	const value = record[key];
	if (typeof value !== "boolean") throw Error(`Malformed follow-up ${label}.${key}: expected boolean`);
	return value;
}

function optionalBoolean(record: Record<string, unknown>, key: string, label: string): boolean | undefined {
	const value = record[key];
	if (value === undefined) return undefined;
	if (typeof value !== "boolean") throw Error(`Malformed follow-up ${label}.${key}: expected boolean`);
	return value;
}

function parseArray<T>(value: unknown, label: string, item: (input: unknown, at: string) => T): T[] {
	if (!Array.isArray(value)) throw Error(`Malformed follow-up ${label}: expected array`);
	return value.map((entry, index) => item(entry, `${label}[${index}]`));
}

function parseNotice(value: unknown, label: string): FollowupNotice {
	const record = exactRecord(value, ["id", "kind", "summary"], label);
	const id = strictString(record, "id", label);
	const kind = strictString(record, "kind", label);
	const summary = strictString(record, "summary", label);
	if (!id || !NOTICE_KINDS.includes(kind) || !summary) throw Error(`Malformed follow-up ${label}: invalid notice`);
	return { id, kind: kind as FollowupNoticeKind, summary };
}

function parseEvidence(value: unknown, label: string): FollowupEvidenceCandidate {
	const record = exactRecord(value, ["path", "sha256", "size", "mtimeMs"], label);
	const candidate: FollowupEvidenceCandidate = {
		path: strictString(record, "path", label),
		sha256: strictString(record, "sha256", label),
		size: strictInteger(record, "size", label),
		mtimeMs: strictNumber(record, "mtimeMs", label),
	};
	if (
		!candidate.path ||
		isAbsolute(candidate.path) ||
		candidate.path.startsWith("../") ||
		candidate.path.includes("\\") ||
		!HEX64.test(candidate.sha256)
	)
		throw Error(`Malformed follow-up ${label}: invalid evidence candidate`);
	return candidate;
}

function parseStop(value: unknown, label: string): FollowupStop {
	const record = exactRecord(
		value,
		[
			"id",
			"state",
			"detail",
			"fingerprint",
			"evidenceFingerprint",
			"evidence",
			"stableSince",
			"createdAt",
			"noticeCreated",
			"noticeEmitted",
			"noProgressCreated",
			"noProgressEmitted",
			"followUpId",
		],
		label,
	);
	const stop: FollowupStop = {
		id: strictString(record, "id", label),
		state: strictString(record, "state", label),
		detail: strictString(record, "detail", label),
		fingerprint: strictString(record, "fingerprint", label),
		evidenceFingerprint: strictString(record, "evidenceFingerprint", label),
		evidence: parseArray(record.evidence, `${label}.evidence`, parseEvidence),
		stableSince: strictNumber(record, "stableSince", label),
		createdAt: strictNumber(record, "createdAt", label),
		noticeCreated: strictBoolean(record, "noticeCreated", label),
		noticeEmitted: strictBoolean(record, "noticeEmitted", label),
		noProgressCreated: strictBoolean(record, "noProgressCreated", label),
		noProgressEmitted: strictBoolean(record, "noProgressEmitted", label),
	};
	const followUpId = optionalString(record, "followUpId", label);
	if (followUpId !== undefined) stop.followUpId = followUpId;
	if (
		!UUID.test(stop.id) ||
		!stop.state ||
		!HEX64.test(stop.fingerprint) ||
		!HEX64.test(stop.evidenceFingerprint) ||
		(followUpId !== undefined && !UUID.test(followUpId))
	)
		throw Error(`Malformed follow-up ${label}: invalid stop identity`);
	return stop;
}

function parseOutbox(value: unknown, label: string): FollowupOutbox {
	const record = exactRecord(
		value,
		[
			"id",
			"stopId",
			"pinned",
			"body",
			"createdAt",
			"updatedAt",
			"attempts",
			"transport",
			"receiptState",
			"uncertain",
			"lastError",
		],
		label,
	);
	const outbox: FollowupOutbox = {
		id: strictString(record, "id", label),
		stopId: strictString(record, "stopId", label),
		pinned: strictString(record, "pinned", label),
		body: strictString(record, "body", label),
		createdAt: strictNumber(record, "createdAt", label),
		updatedAt: strictNumber(record, "updatedAt", label),
		attempts: strictInteger(record, "attempts", label),
		transport: strictString(record, "transport", label),
		receiptState: strictString(record, "receiptState", label),
		uncertain: strictBoolean(record, "uncertain", label),
	};
	const lastError = optionalString(record, "lastError", label);
	if (lastError !== undefined) outbox.lastError = lastError;
	if (
		!UUID.test(outbox.id) ||
		!UUID.test(outbox.stopId) ||
		!HEX64.test(outbox.pinned) ||
		!outbox.body ||
		Buffer.byteLength(outbox.body, "utf8") > MAX_BODY_BYTES ||
		!TRANSPORT_STATES.includes(outbox.transport) ||
		!(
			RECEIPT_STATES.includes(outbox.receiptState) ||
			outbox.receiptState === "reserved" ||
			outbox.receiptState === "none"
		)
	)
		throw Error(`Malformed follow-up ${label}: invalid outbox record`);
	return outbox;
}

function parseNoticeRecord(value: unknown, label: string): FollowupNoticeRecord {
	const record = exactRecord(
		value,
		["notice", "stopId", "createdAt", "emitted", "emittedAt", "emitError", "cancelled"],
		label,
	);
	const noticeRecord: FollowupNoticeRecord = {
		notice: parseNotice(record.notice, `${label}.notice`),
		stopId: nullableString(record, "stopId", label),
		createdAt: strictNumber(record, "createdAt", label),
		emitted: strictBoolean(record, "emitted", label),
	};
	const emittedAt = optionalNumber(record, "emittedAt", label);
	const emitError = optionalString(record, "emitError", label);
	const cancelled = optionalBoolean(record, "cancelled", label);
	if (emittedAt !== undefined) noticeRecord.emittedAt = emittedAt;
	if (emitError !== undefined) noticeRecord.emitError = emitError;
	if (cancelled !== undefined) noticeRecord.cancelled = cancelled;
	return noticeRecord;
}

function parseDiagnosis(value: unknown, label: string): FollowupDiagnosis {
	const record = exactRecord(value, ["id", "reason", "createdAt", "emitted"], label);
	const diagnosis: FollowupDiagnosis = {
		id: strictString(record, "id", label),
		reason: strictString(record, "reason", label),
		createdAt: strictNumber(record, "createdAt", label),
		emitted: strictBoolean(record, "emitted", label),
	};
	if (!UUID.test(diagnosis.id) || !diagnosis.reason) throw Error(`Malformed follow-up ${label}: invalid diagnosis`);
	return diagnosis;
}

function parseLedger(value: unknown, expectedPinned: string): FollowupLedger {
	const label = "ledger";
	const record = exactRecord(
		value,
		[
			"schema",
			"version",
			"pinned",
			"activeStopId",
			"stableSince",
			"lastState",
			"lastDetail",
			"stops",
			"outbox",
			"notices",
			"diagnoses",
		],
		label,
	);
	const version = strictNumber(record, "version", label);
	const pinned = strictString(record, "pinned", label);
	if (strictString(record, "schema", label) !== SCHEMA || version !== 1 || pinned !== expectedPinned)
		throw Error("Malformed or rebound follow-up ledger; reconcile pinned target identity");
	const ledger: FollowupLedger = {
		schema: SCHEMA,
		version: 1,
		pinned,
		activeStopId: nullableString(record, "activeStopId", label),
		stableSince: nullableNumber(record, "stableSince", label),
		lastState: nullableString(record, "lastState", label),
		lastDetail: strictString(record, "lastDetail", label),
		stops: parseArray(record.stops, "ledger.stops", parseStop),
		outbox: parseArray(record.outbox, "ledger.outbox", parseOutbox),
		notices: parseArray(record.notices, "ledger.notices", parseNoticeRecord),
		diagnoses: parseArray(record.diagnoses, "ledger.diagnoses", parseDiagnosis),
	};
	if (
		ledger.stops.length > MAX_STOPS ||
		ledger.outbox.length > MAX_OUTBOX ||
		ledger.notices.length > MAX_NOTICES ||
		ledger.diagnoses.length > MAX_DIAGNOSES
	)
		throw Error("Follow-up ledger exceeds bounded history; reconcile manually");
	const stopIds = new Set(ledger.stops.map((stop) => stop.id));
	const outboxIds = new Set(ledger.outbox.map((entry) => entry.id));
	if (
		stopIds.size !== ledger.stops.length ||
		outboxIds.size !== ledger.outbox.length ||
		(ledger.activeStopId !== null && !stopIds.has(ledger.activeStopId))
	)
		throw Error("Malformed follow-up ledger: duplicate or dangling stop identity");
	for (const entry of ledger.outbox)
		if (!stopIds.has(entry.stopId) || entry.pinned !== pinned || entry.id !== entry.stopId)
			throw Error("Malformed follow-up ledger: outbox is not bound to its stable stop");
	return ledger;
}

function freshLedger(pinned: string): FollowupLedger {
	return {
		schema: SCHEMA,
		version: 1,
		pinned,
		activeStopId: null,
		stableSince: null,
		lastState: null,
		lastDetail: "",
		stops: [],
		outbox: [],
		notices: [],
		diagnoses: [],
	};
}

function queueFacts(rows: readonly WorkerEntry[], targetKey: string): string[] {
	return rows
		.filter((row) => normalizeKey(workerOwnerKey(row)) === targetKey && TERMINAL_WORKER_STATUSES.includes(row.status))
		.map((row) => [row.taskKey, row.status, row.dispatchedAt, row.updatedAt, row.model, row.taskPath].join("|"))
		.sort();
}

function controllerPath(candidate: string): boolean {
	// Input is relative to the key root, never the project/key prefix.
	const lower = candidate.replace(/\\/g, "/").toLowerCase();
	const parts = lower.split("/");
	const name = basename(lower);
	return (
		parts[0] === "duty-followup" ||
		parts[0] === "duty-ledger" ||
		parts.includes(".mw-pm-channel") ||
		name === "heartbeat.json" ||
		name === "run.json" ||
		name === "worker.log" ||
		name.endsWith(".request.json") ||
		name.endsWith(".receipt.json") ||
		name.endsWith(".tmp")
	);
}

function evidenceFile(name: string): boolean {
	return /\.(?:md|txt|log|json|yml|yaml|parallel)$/i.test(name);
}

function sampleView(sample: WatchSample): SampleView {
	return { state: sample.state, detail: sample.detail ?? "" };
}

function stopView(stop: FollowupStop): FollowupStopView {
	return {
		id: stop.id,
		state: stop.state,
		detail: stop.detail,
		fingerprint: stop.fingerprint,
		evidenceFingerprint: stop.evidenceFingerprint,
		evidenceCandidates: stop.evidence.map((entry) => entry.path),
		stableSince: stop.stableSince,
		createdAt: stop.createdAt,
		noticeEmitted: stop.noticeEmitted,
		noProgressEmitted: stop.noProgressEmitted,
		followUpId: stop.followUpId ?? null,
	};
}

function outboxView(entry: FollowupOutbox): FollowupOutboxView {
	return {
		id: entry.id,
		stopId: entry.stopId,
		transport: entry.transport,
		receiptState: entry.receiptState,
		uncertain: entry.uncertain,
		attempts: entry.attempts,
		createdAt: entry.createdAt,
		updatedAt: entry.updatedAt,
		body: entry.body,
		lastError: entry.lastError ?? null,
	};
}

/** Persistent bounded follow-up controller. The caller holds the exclusive
 *  monitor/send target leases; this class never creates duty/stage authority. */
export class DutyFollowup {
	readonly target: FollowupTarget;
	readonly watch: StopWatch;
	private readonly directory: string;
	private readonly file: string;
	private readonly pinned: string;

	constructor(target: FollowupTarget, home?: string) {
		const project = realpathSync.native(target.project);
		const key = normalizeKey(target.key);
		const claim = target.claim.trim();
		const binding = target.binding.trim();
		const session = target.session.trim();
		if (keyNameRefusal(key) !== null || !UUID.test(binding) || !claim || !session)
			throw Error("Invalid follow-up target identity");
		this.target = Object.freeze({ project, key, claim, binding, session });
		this.watch = new StopWatch(project, key, claim, binding, home);
		this.directory = join(this.watch.channel.dir, key, "duty-followup");
		this.file = join(this.directory, "ledger.json");
		this.pinned = sha256([
			process.platform === "win32" ? project.toLowerCase() : project,
			key,
			claim,
			binding,
			session,
		]);
		this.readLedger();
	}

	poll(now: number, emit: (notice: FollowupNotice) => void): void {
		const ledger = this.readLedger();
		this.reconcileReceipts(ledger, now);
		let live: LiveIdentity;
		let sample: SampleView;
		let evidence: EvidenceSnapshot | undefined;
		let evidenceError: string | undefined;
		try {
			live = this.live();
			sample = sampleView(this.watch.sample());
			evidence = this.collectEvidence();
		} catch (error) {
			live = {
				key: this.target.key,
				status: "unknown",
				phase: "unknown",
				claim: "",
				connected: false,
				binding: undefined,
				session: undefined,
				activity: "unknown",
			};
			sample = { state: "unobservable", detail: errorText(error) };
			evidenceError = errorText(error);
		}
		const diagnosis = evidenceError
			? `Unreadable target state: ${bounded(evidenceError, MAX_ERROR_BYTES)}`
			: this.suspensionReason(live, sample);
		if (diagnosis || !evidence) {
			this.suspend(ledger, now, diagnosis ?? "Unobservable target state", evidence?.paths ?? [], emit);
			return;
		}
		this.resume(ledger);
		const eligible = STOP_ELIGIBLE_STATES.has(sample.state);
		const fingerprint = sha256([sample.state, sample.detail, evidence.fingerprint]);
		this.invalidateNotices(ledger, eligible ? fingerprint : null);
		const active = ledger.stops.find((stop) => stop.id === ledger.activeStopId);
		if (!eligible || active?.fingerprint !== fingerprint) ledger.activeStopId = null;

		if (ledger.lastState !== sample.state) {
			ledger.lastState = sample.state;
			ledger.lastDetail = sample.detail;
			ledger.stableSince = now;
		} else {
			ledger.stableSince ??= now;
			ledger.lastDetail = sample.detail;
		}
		if (
			sample.state === "working" ||
			sample.state === "waiting-for-worker" ||
			!STOP_ELIGIBLE_STATES.has(sample.state)
		) {
			ledger.stableSince = null;
			this.writeLedger(ledger);
			return;
		}
		if (sample.state === "idle" && now - (ledger.stableSince ?? now) < IDLE_MS) {
			this.writeLedger(ledger);
			return;
		}
		// Resolve the original transport outcome before allocating ANY successor stop.
		if (ledger.outbox.some((entry) => entry.uncertain || entry.transport === "reserved")) {
			this.writeLedger(ledger);
			return;
		}
		const stop = this.ensureStop(ledger, now, sample, evidence);
		if (!stop.noticeCreated) {
			stop.noticeCreated = true;
			ledger.notices.push({
				notice: {
					id: stop.id,
					kind: "stop",
					summary: this.stopSummary(stop),
				},
				stopId: stop.id,
				createdAt: now,
				emitted: false,
			});
			this.writeLedger(ledger);
		}
		this.emitPending(ledger, now, emit);

		const outbox = ledger.outbox.find((entry) => entry.stopId === stop.id);
		if (
			outbox &&
			!stop.noProgressCreated &&
			sample.state === "idle" &&
			ledger.stableSince !== null &&
			now - ledger.stableSince >= IDLE_MS &&
			now - outbox.createdAt >= IDLE_MS &&
			evidence.fingerprint === stop.evidenceFingerprint
		) {
			stop.noProgressCreated = true;
			ledger.notices.push({
				notice: {
					id: `no-progress:${stop.id}`,
					kind: "no-progress",
					summary: this.noProgressSummary(stop, outbox),
				},
				stopId: stop.id,
				createdAt: now,
				emitted: false,
			});
			this.writeLedger(ledger);
			this.emitPending(ledger, now, emit);
		}
	}

	status(now: number = Date.now()): FollowupStatus {
		const ledger = this.readLedger();
		const receipts = this.reconcileReceipts(ledger, now);
		let live: LiveIdentity;
		let sample: SampleView;
		let evidence: EvidenceSnapshot | undefined;
		let evidenceError: string | undefined;
		try {
			live = this.live();
			sample = sampleView(this.watch.sample());
			evidence = this.collectEvidence();
		} catch (error) {
			live = {
				key: this.target.key,
				status: "unknown",
				phase: "unknown",
				claim: "",
				connected: false,
				binding: undefined,
				session: undefined,
				activity: "unknown",
			};
			sample = { state: "unobservable", detail: errorText(error) };
			evidenceError = errorText(error);
		}
		const diagnosis = evidenceError
			? `Unreadable target state: ${bounded(evidenceError, MAX_ERROR_BYTES)}`
			: this.suspensionReason(live, sample);
		const visible = ledger.notices.filter((entry) => !entry.cancelled).map((entry) => entry.notice);
		const activeStop = ledger.activeStopId
			? (ledger.stops.find((stop) => stop.id === ledger.activeStopId) ?? null)
			: null;
		const unresolved = ledger.outbox.find((entry) => entry.uncertain || entry.transport === "reserved");
		const currentEligible =
			activeStop !== null &&
			activeStop.noticeEmitted &&
			evidence !== undefined &&
			STOP_ELIGIBLE_STATES.has(sample.state) &&
			activeStop.fingerprint === sha256([sample.state, sample.detail, evidence.fingerprint]) &&
			(sample.state !== "idle" || (ledger.stableSince !== null && now - ledger.stableSince >= IDLE_MS));
		return {
			mode: "followup",
			target: this.target,
			pinned: this.pinned,
			observedState: sample.state,
			state: sample.state,
			detail: sample.detail,
			activity: live.activity,
			stableSince: ledger.stableSince,
			stableMs: ledger.stableSince === null ? 0 : Math.max(0, now - ledger.stableSince),
			idleSince: sample.state === "idle" ? ledger.stableSince : null,
			idleMs: sample.state === "idle" && ledger.stableSince !== null ? Math.max(0, now - ledger.stableSince) : 0,
			sendAllowed: diagnosis === null && currentEligible && unresolved === undefined,
			suspended: diagnosis !== null,
			diagnosis: diagnosis === null ? null : bounded(diagnosis, MAX_SUMMARY_BYTES),
			businessProgress: "unverified",
			activeStopId: ledger.activeStopId,
			stop: activeStop ? stopView(activeStop) : null,
			notices: visible,
			pendingNotices: ledger.notices
				.filter((entry) => !entry.emitted && !entry.cancelled)
				.map((entry) => entry.notice),
			emittedNotices: ledger.notices
				.filter((entry) => entry.emitted && !entry.cancelled)
				.map((entry) => entry.notice),
			outbox: ledger.outbox.map(outboxView),
			receipts,
			evidenceCandidates: evidence?.paths ?? [],
			evidenceFingerprint: evidence?.fingerprint ?? "",
			evidenceObservation: {
				partial: evidence?.partial ?? true,
				scannedEntries: evidence?.scannedEntries ?? 0,
				maxCandidates: MAX_CANDIDATES,
				maxScanEntries: MAX_SCAN_ENTRIES,
				maxDepth: MAX_SCAN_DEPTH,
				largeFilePrefixBytes: MAX_EVIDENCE_READ_BYTES,
				fullFileLimitBytes: MAX_EVIDENCE_FILE_BYTES,
			},
			deliveryBlockedBy: unresolved?.id ?? null,
			ledgerPath: this.file,
			source: MW_FOLLOWUP_SOURCE,
		};
	}

	send(id: string, note: string, now: number = Date.now()): FollowupSendResult {
		const ledger = this.readLedger();
		this.reconcileReceipts(ledger, now);
		const evidence = this.collectEvidence();
		this.assertLiveIdentity();
		const sample = sampleView(this.watch.sample());
		const reason = this.suspensionReason(this.live(), sample);
		if (reason) throw Error(`Follow-up refused: ${reason}`);
		const stop = ledger.stops.find((entry) => entry.id === id);
		if (!stop) throw Error("Unknown follow-up stop ID; arbitrary IDs cannot create stops");
		if (!stop.noticeEmitted) throw Error("Follow-up stop notice has not been emitted");
		const existing = ledger.outbox.find((entry) => entry.id === id);
		if (!existing) {
			if (
				ledger.activeStopId !== id ||
				!STOP_ELIGIBLE_STATES.has(sample.state) ||
				stop.fingerprint !== sha256([sample.state, sample.detail, evidence.fingerprint]) ||
				(sample.state === "idle" && (ledger.stableSince === null || now - ledger.stableSince < IDLE_MS))
			)
				throw Error("Stale follow-up stop ID: current state/evidence is not eligible");
			if (ledger.outbox.some((entry) => entry.uncertain || entry.transport === "reserved"))
				throw Error("Unresolved original delivery; reconcile its exact ID before any successor");
		}
		if (
			!note.trim() ||
			Buffer.byteLength(note, "utf8") > MAX_NOTE_BYTES ||
			/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(note)
		)
			throw Error("Follow-up note must contain 1–1600 UTF-8 bytes without control characters");
		const body = this.messageBody(stop, note);
		if (Buffer.byteLength(body, "utf8") > MAX_BODY_BYTES) throw Error("Follow-up body exceeds channel limit");
		if (existing) {
			if (existing.stopId !== stop.id || existing.pinned !== this.pinned)
				throw Error("Follow-up outbox identity conflict; reconcile manually");
			if (existing.body !== body) throw Error("Follow-up ID/body conflict; the exact original body is required");
		}
		this.assertLiveIdentity();
		let outbox = existing;
		const idempotent = outbox !== undefined;
		if (!outbox) {
			if (ledger.outbox.length >= MAX_OUTBOX) throw Error("Follow-up outbox exceeds bounded history");
			outbox = {
				id,
				stopId: stop.id,
				pinned: this.pinned,
				body,
				createdAt: now,
				updatedAt: now,
				attempts: 0,
				transport: "reserved",
				receiptState: "reserved",
				uncertain: false,
			};
			ledger.outbox.push(outbox);
			stop.followUpId = id;
			this.writeLedger(ledger);
		}
		const requestPath = this.watch.channel.messagePath(this.target.key, this.target.binding, id, "request");
		const attempts = outbox.attempts + 1;
		try {
			this.assertLiveIdentity();
			const receiptValue: unknown = this.watch.channel.send(
				this.target.key,
				this.target.binding,
				id,
				body,
				undefined,
				undefined,
				MW_FOLLOWUP_SOURCE,
			);
			const receipt = this.parseReceipt(receiptValue, id);
			outbox.attempts = attempts;
			outbox.updatedAt = now;
			outbox.receiptState = receipt.state;
			outbox.lastError = undefined;
			if (outbox.uncertain && receipt.state === "queued") outbox.transport = "uncertain";
			else {
				outbox.transport = receipt.state;
				outbox.uncertain = false;
			}
			this.writeLedger(ledger);
			return {
				ok: !outbox.uncertain,
				id,
				stopId: stop.id,
				requestPath,
				body,
				source: MW_FOLLOWUP_SOURCE,
				transport: outbox.transport,
				receiptState: outbox.receiptState,
				receipt: receipt.raw,
				uncertain: outbox.uncertain,
				idempotent,
				businessProgress: "unverified",
				message: outbox.uncertain
					? "Transport outcome remains uncertain for this stable ID; no successor ID was created"
					: "Stable-ID follow-up sent or reconciled; engineering progress remains unverified",
			};
		} catch (error) {
			const message = errorText(error);
			outbox.attempts = attempts;
			outbox.updatedAt = now;
			outbox.lastError = bounded(message, MAX_ERROR_BYTES);
			const knownRefusal =
				/conflict|unavailable|refused|invalid|identity|session|binding|phase|offline|receipt/i.test(message);
			if (knownRefusal) {
				outbox.transport = /conflict/i.test(message) ? "conflict" : "refused";
				outbox.uncertain = false;
			} else {
				outbox.transport = "uncertain";
				outbox.uncertain = true;
			}
			this.writeLedger(ledger);
			if (knownRefusal) throw Error(`Follow-up refused: ${message}`);
			return {
				ok: false,
				id,
				stopId: stop.id,
				requestPath,
				body,
				source: MW_FOLLOWUP_SOURCE,
				transport: "uncertain",
				receiptState: outbox.receiptState,
				receipt: null,
				uncertain: true,
				idempotent,
				businessProgress: "unverified",
				message: `Transport outcome uncertain; same stable ID retained: ${outbox.lastError}`,
			};
		}
	}

	private readLedger(): FollowupLedger {
		if (!existsSync(this.file)) return freshLedger(this.pinned);
		let contents: string;
		try {
			contents = readFileSync(this.file, "utf8");
		} catch (error) {
			throw Error(`Unreadable follow-up ledger: ${errorText(error)}`);
		}
		let value: unknown;
		try {
			value = JSON.parse(contents);
		} catch {
			throw Error("Malformed follow-up ledger: invalid JSON");
		}
		return parseLedger(value, this.pinned);
	}

	private writeLedger(ledger: FollowupLedger): void {
		const pending = ledger.notices.filter((entry) => !entry.emitted && !entry.cancelled);
		const closed = ledger.notices.filter((entry) => entry.emitted || entry.cancelled).slice(-32);
		if (pending.length > MAX_NOTICES - closed.length) throw Error("Follow-up pending notices exceed bounded history");
		ledger.notices = [...closed, ...pending];
		if (ledger.stops.length > MAX_STOPS || ledger.outbox.length > MAX_OUTBOX)
			throw Error("Follow-up ledger exceeds bounded history");
		mkdirSync(this.directory, { recursive: true, mode: 0o700 });
		const tmp = `${this.file}.${randomUUID()}.tmp`;
		writeFileSync(tmp, JSON.stringify(ledger), { flag: "wx", mode: 0o600 });
		try {
			for (let attempt = 0; ; attempt++) {
				try {
					renameSync(tmp, this.file);
					break;
				} catch (error) {
					const code = (error as NodeJS.ErrnoException).code ?? "";
					if (!SHARING_CODES.has(code) || attempt === 3) throw error;
					Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10 * (attempt + 1));
				}
			}
		} finally {
			rmSync(tmp, { force: true });
		}
	}

	private live(): LiveIdentity {
		const raw: PmChannelStatus = this.watch.channel.status(this.target.key);
		return {
			key: raw.key,
			status: raw.status,
			phase: raw.phase,
			claim: raw.claim,
			connected: raw.connected,
			binding: typeof raw.binding === "string" ? raw.binding : undefined,
			session: "session" in raw && typeof raw.session === "string" ? raw.session : undefined,
			activity: "activity" in raw && typeof raw.activity === "string" ? raw.activity : "unknown",
		};
	}

	private suspensionReason(live: LiveIdentity, sample: SampleView): string | null {
		if (live.phase.toUpperCase() === "DONE" || live.status !== "active")
			return `Target phase ${live.phase || "unknown"} / status ${live.status || "unknown"} is finished or inactive`;
		if (!live.connected) return "Original PM receiver is offline";
		if (normalizeKey(live.key) !== this.target.key) return "Target key authority changed";
		if (live.claim !== this.target.claim) return "Original PM owner changed";
		if (live.binding !== this.target.binding) return "Original PM binding changed";
		if (live.session !== this.target.session) return "Original PM session changed";
		if (SUSPENDED_SAMPLE_STATES.has(sample.state))
			return `Observed ${sample.state}: ${bounded(sample.detail || "unreadable target state", MAX_ERROR_BYTES)}`;
		return null;
	}

	private assertLiveIdentity(): LiveIdentity {
		const live = this.live();
		const queue = this.watch.workers.readQueue();
		if (queue.version > 2 || queue.unparsable.length) throw Error("Follow-up refused: unreadable worker queue");
		const reason = this.suspensionReason(live, { state: "idle", detail: "" });
		if (reason) throw Error(`Follow-up refused: ${reason}`);
		return live;
	}

	private collectEvidence(): EvidenceSnapshot {
		const keyRoot = join(this.target.project, ".agenticdoc", this.target.key);
		if (!existsSync(keyRoot) || !lstatSync(keyRoot).isDirectory())
			throw Error("Target key evidence directory is missing or unreadable");
		const candidates: FollowupEvidenceCandidate[] = [];
		const seen = new Set<string>();
		let partial = false;
		let scannedEntries = 0;
		const addFile = (absolute: string): void => {
			const rel = relative(this.target.project, absolute).split(sep).join("/");
			const keyRelative = relative(keyRoot, absolute).split(sep).join("/");
			if (
				!rel ||
				isAbsolute(rel) ||
				rel === ".." ||
				rel.startsWith("../") ||
				controllerPath(keyRelative) ||
				!evidenceFile(basename(rel)) ||
				seen.has(rel)
			)
				return;
			if (candidates.length >= MAX_CANDIDATES) {
				partial = true;
				return;
			}
			let stat: Stats;
			try {
				stat = lstatSync(absolute);
			} catch (error) {
				if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
				throw Error(`Unreadable target evidence ${rel}: ${errorText(error)}`);
			}
			if (!stat.isFile() || stat.isSymbolicLink()) return;
			const hash = createHash("sha256");
			if (stat.size <= MAX_EVIDENCE_FILE_BYTES) hash.update(readFileSync(absolute));
			else {
				partial = true;
				const fd = openSync(absolute, "r");
				try {
					const buffer = Buffer.allocUnsafe(MAX_EVIDENCE_READ_BYTES);
					const length = readSync(fd, buffer, 0, buffer.length, 0);
					if (length > 0) hash.update(buffer.subarray(0, length));
				} finally {
					closeSync(fd);
				}
				hash.update(String(stat.size));
			}
			hash.update(String(Math.trunc(stat.mtimeMs)));
			seen.add(rel);
			candidates.push({ path: rel, sha256: hash.digest("hex"), size: stat.size, mtimeMs: Math.trunc(stat.mtimeMs) });
		};
		// Read authority anchors before a bounded directory-prefix sample can fill up.
		for (const name of ["pm-state.md", "spec.md", "design.md", "plan.md", "achieved.md"])
			addFile(join(keyRoot, name));
		const scan = (directory: string, relativeDirectory: string, depth: number): void => {
			if (depth > MAX_SCAN_DEPTH) {
				partial = true;
				return;
			}
			const handle = opendirSync(directory);
			try {
				while (true) {
					if (scannedEntries >= MAX_SCAN_ENTRIES || candidates.length >= MAX_CANDIDATES) {
						partial = true;
						break;
					}
					const entry = handle.readSync();
					if (!entry) break;
					scannedEntries++;
					const childRelative = relativeDirectory ? `${relativeDirectory}/${entry.name}` : entry.name;
					const absolute = join(directory, entry.name);
					if (entry.isDirectory()) {
						if (!SKIP_DIRECTORIES.has(entry.name.toLowerCase()) && !controllerPath(childRelative))
							scan(absolute, childRelative, depth + 1);
					} else if (entry.isFile()) addFile(absolute);
				}
			} finally {
				handle.closeSync();
			}
		};
		scan(keyRoot, "", 0);
		if (!existsSync(this.watch.workers.queuePath)) throw Error("Worker queue is missing or unreadable");
		const queue = this.watch.workers.readQueue();
		if (queue.version > 2 || queue.unparsable.length) throw Error("Worker queue has unreadable rows");
		const facts = queueFacts(queue.rows, this.target.key);
		candidates.sort((left, right) => left.path.localeCompare(right.path));
		return {
			partial,
			scannedEntries,
			fingerprint: sha256([candidates.map((entry) => [entry.path, entry.sha256, entry.size, entry.mtimeMs]), facts]),
			candidates,
			queueFacts: facts,
			paths: candidates.map((entry) => entry.path),
		};
	}

	private ensureStop(
		ledger: FollowupLedger,
		now: number,
		sample: SampleView,
		evidence: EvidenceSnapshot,
	): FollowupStop {
		const fingerprint = sha256([sample.state, sample.detail, evidence.fingerprint]);
		const existing = [...ledger.stops].reverse().find((stop) => stop.fingerprint === fingerprint);
		if (existing) {
			ledger.activeStopId = existing.id;
			return existing;
		}
		if (ledger.stops.length >= MAX_STOPS) throw Error("Follow-up stop history exceeds bounded limit");
		const stop: FollowupStop = {
			id: randomUUID(),
			state: sample.state,
			detail: sample.detail,
			fingerprint,
			evidenceFingerprint: evidence.fingerprint,
			evidence: evidence.candidates,
			stableSince: ledger.stableSince ?? now,
			createdAt: now,
			noticeCreated: false,
			noticeEmitted: false,
			noProgressCreated: false,
			noProgressEmitted: false,
		};
		ledger.stops.push(stop);
		ledger.activeStopId = stop.id;
		return stop;
	}

	private stopSummary(stop: FollowupStop): string {
		const inspect = stop.evidence.slice(0, 4).map((entry) => entry.path);
		return bounded(
			`Bounded follow-up stop ${stop.id} for ${this.target.key}: ${stop.state}` +
				`${stop.detail ? ` (${stop.detail})` : ""}. ` +
				`Inspect ${inspect.length ? inspect.join(", ") : `.agenticdoc/${this.target.key}/pm-state.md`}. ` +
				"Original PM must verify facts and remain inside existing authority, budget and gates. " +
				"Business progress unverified.",
			MAX_SUMMARY_BYTES,
		);
	}

	private noProgressSummary(stop: FollowupStop, outbox: FollowupOutbox): string {
		const inspect = stop.evidence.slice(0, 4).map((entry) => entry.path);
		return bounded(
			`No verified progress for ${stop.id}: ${this.target.key} is still ${stop.state}; ` +
				`receipt ${outbox.receiptState}, transport ${outbox.transport}, unchanged sampled evidence candidates (not complete coverage). ` +
				`Inspect ${inspect.length ? inspect.join(", ") : `.agenticdoc/${this.target.key}/pm-state.md`}. ` +
				"queued/received/started and working are not engineering acceptance; no automatic resend.",
			MAX_SUMMARY_BYTES,
		);
	}

	private messageBody(stop: FollowupStop, note: string): string {
		const inspect = stop.evidence.slice(0, 8).map((entry) => entry.path);
		return [
			`MW/pi bounded follow-up for ${this.target.key} / ${stop.id}.`,
			"Original PM remains the owner. Verify current facts in the listed target evidence before acting.",
			"Continue only inside the existing authorization, budget, deadline and gates. This is not a duty, stage grant, approval, receipt or new work authorization.",
			`Observed state: ${stop.state}${stop.detail ? ` (${stop.detail})` : ""}.`,
			`Inspect: ${inspect.length ? inspect.join("; ") : `.agenticdoc/${this.target.key}/pm-state.md`}.`,
			"Report concrete evidence paths. queued/received/started and working are not verified engineering progress.",
			`Follow-up note: ${note}`,
		].join("\n");
	}

	private suspend(
		ledger: FollowupLedger,
		now: number,
		reason: string,
		paths: readonly string[],
		emit: (notice: FollowupNotice) => void,
	): void {
		const boundedReason = bounded(reason, MAX_SUMMARY_BYTES);
		ledger.lastState = "suspended";
		ledger.lastDetail = boundedReason;
		ledger.stableSince = null;
		this.invalidateNotices(ledger, null);
		const existing = ledger.diagnoses.find((entry) => entry.reason === boundedReason);
		if (!existing) {
			if (ledger.diagnoses.length >= MAX_DIAGNOSES) throw Error("Follow-up diagnosis history exceeds bounded limit");
			const id = randomUUID();
			ledger.diagnoses.push({ id, reason: boundedReason, createdAt: now, emitted: false });
			ledger.notices.push({
				notice: {
					id,
					kind: "suspended",
					summary: bounded(
						`Follow-up suspended for ${this.target.key}: ${boundedReason}. Sends are refused; ` +
							"original owner, budget, deadline and gates are unchanged. " +
							`Inspect ${paths.slice(0, 4).join(", ") || `.agenticdoc/${this.target.key}/pm-state.md`}. ` +
							"Do not silently rebind.",
						MAX_SUMMARY_BYTES,
					),
				},
				stopId: null,
				createdAt: now,
				emitted: false,
			});
		}
		this.writeLedger(ledger);
		this.emitPending(ledger, now, emit);
	}

	private invalidateNotices(ledger: FollowupLedger, fingerprint: string | null): void {
		for (const entry of ledger.notices) {
			if (entry.emitted || entry.cancelled || !entry.stopId) continue;
			const stop = ledger.stops.find((candidate) => candidate.id === entry.stopId);
			if (stop && stop.fingerprint === fingerprint) continue;
			entry.cancelled = true;
			if (stop) {
				if (entry.notice.kind === "stop") stop.noticeCreated = false;
				if (entry.notice.kind === "no-progress") stop.noProgressCreated = false;
			}
		}
	}

	private resume(ledger: FollowupLedger): void {
		for (const entry of ledger.notices)
			if (!entry.emitted && entry.notice.kind === "suspended") entry.cancelled = true;
		ledger.diagnoses = [];
	}

	private emitPending(ledger: FollowupLedger, now: number, emit: (notice: FollowupNotice) => void): boolean {
		const pending = ledger.notices
			.filter((entry) => !entry.emitted && !entry.cancelled)
			.sort((left, right) => left.createdAt - right.createdAt)[0];
		if (!pending) return false;
		try {
			emit(pending.notice);
		} catch (error) {
			pending.emitError = bounded(errorText(error), MAX_ERROR_BYTES);
			this.writeLedger(ledger);
			return true;
		}
		pending.emitted = true;
		pending.emittedAt = now;
		pending.emitError = undefined;
		if (pending.stopId) {
			const stop = ledger.stops.find((entry) => entry.id === pending.stopId);
			if (stop) {
				if (pending.notice.kind === "stop") stop.noticeEmitted = true;
				if (pending.notice.kind === "no-progress") stop.noProgressEmitted = true;
			}
		}
		const diagnosis = ledger.diagnoses.find((entry) => entry.id === pending.notice.id);
		if (diagnosis) diagnosis.emitted = true;
		this.writeLedger(ledger);
		return true;
	}

	private reconcileReceipts(ledger: FollowupLedger, now: number): FollowupReceiptView[] {
		const before = JSON.stringify(ledger);
		const views: FollowupReceiptView[] = [];
		for (const outbox of ledger.outbox) {
			// A durable reservation does not establish whether publication completed.
			if (outbox.transport === "reserved") outbox.uncertain = true;
			const requestPath = this.watch.channel.messagePath(this.target.key, this.target.binding, outbox.id, "request");
			const receiptPath = this.watch.channel.messagePath(this.target.key, this.target.binding, outbox.id, "receipt");
			if (!existsSync(requestPath)) {
				if (!["reserved", "uncertain", "refused", "conflict"].includes(outbox.transport))
					throw Error("Follow-up request is missing; reconcile before retry");
				views.push({
					id: outbox.id,
					stopId: outbox.stopId,
					state: "unknown",
					transport: outbox.transport,
					uncertain: true,
					requestPath,
					receiptPath,
					businessProgress: "unverified",
				});
				continue;
			}
			const receipt = this.parseReceipt(
				this.watch.channel.receipt(this.target.key, this.target.binding, outbox.id),
				outbox.id,
			);
			outbox.receiptState = receipt.state;
			outbox.updatedAt = now;
			if (outbox.uncertain && receipt.state === "queued") outbox.transport = "uncertain";
			else {
				outbox.transport = receipt.state;
				outbox.uncertain = false;
			}
			views.push({
				id: outbox.id,
				stopId: outbox.stopId,
				state: receipt.state,
				transport: outbox.transport,
				uncertain: outbox.uncertain,
				requestPath,
				receiptPath,
				businessProgress: "unverified",
			});
		}
		if (JSON.stringify(ledger) !== before) this.writeLedger(ledger);
		return views;
	}

	private parseReceipt(value: unknown, expectedId: string): ValidatedReceipt {
		const record = exactRecord(value, RECEIPT_FIELDS, "receipt");
		const receipt: ValidatedReceipt = {
			id: strictString(record, "id", "receipt"),
			key: strictString(record, "key", "receipt"),
			binding: strictString(record, "binding", "receipt"),
			state: strictString(record, "state", "receipt"),
			raw: record,
		};
		const claim = optionalString(record, "claim", "receipt");
		const session = optionalString(record, "session", "receipt");
		if (
			receipt.id !== expectedId ||
			normalizeKey(receipt.key) !== this.target.key ||
			receipt.binding !== this.target.binding ||
			(claim !== undefined && claim !== this.target.claim) ||
			(session !== undefined && session !== this.target.session) ||
			!RECEIPT_STATES.includes(receipt.state)
		)
			throw Error("Follow-up receipt identity mismatch");
		return receipt;
	}
}
