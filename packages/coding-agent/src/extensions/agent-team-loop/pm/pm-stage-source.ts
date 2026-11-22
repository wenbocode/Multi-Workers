/** T15-J — typed, sender-origin PM STAGE admission from the authenticated
 *  same-OS `PmChannel` spool.
 *
 *  BOUNDARY: a receipt, a message id, copied text, an assistant observation or
 *  a JSON file in a workspace is NOT a machine grant. Only a request written by
 *  the private channel sender, carrying the closed `PmStageGrantV1` metadata,
 *  with its original receipt, the current window/session binding, the live
 *  authoritative claim, an exact pinned stage card and an unexpired finite
 *  deadline can become a `PmStageDirection`. The source is labelled
 *  `user-delegated-duty-pm`: never a direct-user signature, DP approval,
 *  human-only capability or P0 authority.
 *
 *  The ledger is a REPLAY-RESISTANT lifecycle, not a budget grant. It never
 *  resets counters, never borrows the producer's expired allowance and never
 *  accepts a second event id for an existing stage. The frozen runtime budget
 *  controller owns step/cost/no-progress accounting through the same session
 *  observations as every other registered source.
 */

import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { gatesDir, parseGateFile } from "../autopilot/status-model.ts";
import { sha256EolNormalizedBytes } from "../shared/card-digest.ts";
import { currentClaimId } from "../shared/implementation-gate.ts";
import { IndexStore, keyNameRefusal, normalizeKey } from "../shared/index-store.ts";
import { agenticdocRoot } from "../shared/paths.ts";
import { currentDutyRequest, grantDigest, PmChannel, type PmStageGrantV1, parsePmStageGrant } from "./codex-channel.ts";

/** One product scope, NOT an event/project/key bypass. */
export const PM_STAGE_SCOPE = "pm-stage-source-qg-repair-v1";
export const PM_STAGE_MAX_STEPS = 4;
export const PM_STAGE_MAX_COST = 3;
export const PM_STAGE_MAX_NO_PROGRESS = 2;
export const PM_STAGE_MAX_WINDOW_MS = 90 * 60_000;
export const PM_STAGE_ENTRY_TYPE = "mw-pm-stage-v1";
/** Session-authored typed source record, bound to the digest of the direction. */
export const PM_STAGE_SOURCE_ENTRY_TYPE = "mw-pm-stage-source-v1";
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const MAX_FILE_BYTES = 1024 * 1024;

export type PmStageRead<T> = { ok: true; value: T } | { ok: false; gaps: string[]; reason: string; eventId?: string };

/** Everything a host needs to register a REAL PM stage. No worker dispatch/run,
 *  no model parameter and no direct-user/DP signature is implied. */
export interface PmStageDirection {
	authority_kind: "user-delegated-duty-pm";
	event_id: string;
	key: string;
	claim_id: string;
	binding: string;
	session_id: string;
	received_at: number;
	observed_at: number;
	started_at: string;
	stage_id: string;
	scope_ref: string;
	matter_ref: string;
	parent_matter_ref?: string;
	card_path: string;
	card_sha256: string;
	write_face: string[];
	max_steps: number;
	remaining_cost: number;
	no_progress_limit: number;
	deadline: string;
	grant_digest: string;
	stage_ref: string;
	request_ref: string;
	receipt_ref: string;
	window_ref: string;
	grant: PmStageGrantV1;
}

export interface PmStageDiscoveryInput {
	projectDir: string;
	home?: string;
	sessionId: string;
	claimId?: string;
	/** Bound review/investigation of one exact event; production omits it. */
	eventId?: string;
	nowMs?: number;
	expectedScope?: string;
	/** Read-only revalidation after the native phase transition to VERIFY. */
	terminalProof?: boolean;
}

function fail<T>(reason: string, gaps: string[], eventId?: string): PmStageRead<T> {
	return { ok: false, gaps, reason, ...(eventId === undefined ? {} : { eventId }) };
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}
function nonblank(value: unknown): value is string {
	return typeof value === "string" && value.trim() !== "";
}
function safeInt(value: unknown): value is number {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
function canonicalIso(value: unknown): value is string {
	if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)) return false;
	const ms = Date.parse(value);
	return (
		Number.isSafeInteger(ms) &&
		(new Date(ms).toISOString() === value || new Date(ms).toISOString().replace(".000Z", "Z") === value)
	);
}

function currentOfflineGateScope(
	projectDir: string,
	key: string,
	matterRef: string,
	gateId: string,
	gateDigest: string,
): boolean {
	try {
		const doc = agenticdocRoot(projectDir);
		const file = path.join(gatesDir(projectDir), `${gateId}.md`);
		const relative = path.relative(doc, file);
		if (
			relative.startsWith("..") ||
			path.isAbsolute(relative) ||
			fs.lstatSync(doc).isSymbolicLink() ||
			fs.realpathSync(file) !== path.join(fs.realpathSync(doc), relative)
		)
			return false;
		const stat = fs.lstatSync(file);
		if (!stat.isFile() || stat.size > MAX_FILE_BYTES) return false;
		const bytes = fs.readFileSync(file);
		if (createHash("sha256").update(bytes).digest("hex") !== gateDigest) return false;
		const gate = parseGateFile(bytes.toString("utf8"), file);
		const decision = gate.decision;
		return (
			gate.key === key &&
			gate.id === gateId &&
			(gate.kind === "stage-confirm" || gate.kind === "stage-close") &&
			gate.authorizes.length === 0 &&
			decision !== undefined &&
			decision.transport !== "answered" &&
			decision.decisionRef === null &&
			decision.matterRef === matterRef &&
			(decision.effect === "not-started" || decision.effect === "blocked")
		);
	} catch {
		return false;
	}
}

/** Bounded, redirect-free read from the PRIVATE channel root. No workspace copy
 *  can satisfy this path check, and no symlinked component is followed. */
function readPrivateJson(root: string, file: string): Record<string, unknown> | undefined {
	const rel = path.relative(root, file);
	if (!rel || rel.startsWith("..") || path.isAbsolute(rel)) return undefined;
	try {
		let cursor = root;
		if (fs.lstatSync(cursor).isSymbolicLink()) return undefined;
		for (const part of rel.split(path.sep)) {
			cursor = path.join(cursor, part);
			if (fs.lstatSync(cursor).isSymbolicLink()) return undefined;
		}
		const real = fs.realpathSync(file);
		const lexical = path.resolve(file);
		if (process.platform === "win32" ? real.toLowerCase() !== lexical.toLowerCase() : real !== lexical)
			return undefined;
		const before = fs.lstatSync(file);
		if (!before.isFile() || before.size > MAX_FILE_BYTES) return undefined;
		const parsed: unknown = JSON.parse(fs.readFileSync(file, "utf8"));
		return isRecord(parsed) ? parsed : undefined;
	} catch {
		return undefined;
	}
}

function cardPinOf(projectDir: string, key: string, cardPath: string): string | undefined {
	if (keyNameRefusal(key) !== null || !/^tasks\/(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]+\.md$/.test(cardPath))
		return undefined;
	if (cardPath.split("/").some((part) => part === "." || part === "..")) return undefined;
	const root = agenticdocRoot(projectDir);
	const file = path.join(root, key, cardPath);
	const rel = path.relative(root, file);
	if (!rel || rel.startsWith("..") || path.isAbsolute(rel)) return undefined;
	try {
		let cursor = root;
		for (const part of rel.split(path.sep)) {
			cursor = path.join(cursor, part);
			if (fs.lstatSync(cursor).isSymbolicLink()) return undefined;
		}
		const before = fs.lstatSync(file);
		if (!before.isFile() || before.size > MAX_FILE_BYTES) return undefined;
		const bytes = fs.readFileSync(file);
		const after = fs.lstatSync(file);
		if (before.ino !== after.ino || before.mtimeMs !== after.mtimeMs || bytes.length !== before.size)
			return undefined;
		return sha256EolNormalizedBytes(bytes);
	} catch {
		return undefined;
	}
}

/** Scan the authenticated private spool for ONE current, machine-verifiable
 *  stage direction. A plain-text/receipt-only event produces the concrete
 *  `channel.typed-stage-grant-missing` refusal; it is never reinterpreted. */
export function findPmStageDirection(input: PmStageDiscoveryInput): PmStageRead<PmStageDirection> {
	const nowMs = input.nowMs ?? Date.now();
	if (!safeInt(nowMs)) return fail("stage clock is not finite", ["clock"]);
	const claimId = input.claimId ?? currentClaimId();
	if (!nonblank(input.sessionId)) return fail("current session id is unavailable", ["channel.session"]);
	let channel: PmChannel;
	try {
		channel = new PmChannel(input.projectDir, input.home);
	} catch {
		return fail("trusted channel root is unavailable", ["channel.root"]);
	}
	let rows: ReturnType<IndexStore["readAuthorityRows"]>;
	try {
		rows = channel.index.readAuthorityRows();
	} catch {
		return fail("authoritative index is unreadable", ["index"]);
	}
	const owned = rows.filter((row) => row.status === "active" && row.claimId === claimId);
	if (owned.length !== 1) return fail("no unique active exact-self claim", ["index.claim"]);
	const row = owned[0];
	if (
		!row ||
		(row.phase !== "EXECUTE" && !(input.terminalProof && row.phase === "VERIFY")) ||
		keyNameRefusal(row.key) !== null
	)
		return fail("stage lifecycle is not an active EXECUTE key", ["index.phase"]);
	const key = row.key;
	const keyDir = path.join(channel.dir, normalizeKey(key));
	let bindingDirs: string[];
	try {
		bindingDirs = fs
			.readdirSync(keyDir, { withFileTypes: true })
			.filter((entry) => entry.isDirectory() && UUID.test(entry.name))
			.map((entry) => entry.name)
			.sort();
	} catch {
		return fail("no authenticated channel window for this key", ["channel.window"]);
	}
	const refusals: Array<{ gaps: string[]; reason: string; eventId: string; at: number }> = [];
	for (const binding of bindingDirs) {
		let names: string[];
		try {
			names = fs
				.readdirSync(path.join(keyDir, binding))
				.filter((name) => name.endsWith(".request.json"))
				.sort();
		} catch {
			continue;
		}
		for (const name of names.slice(0, 64)) {
			const eventId = name.slice(0, -".request.json".length);
			if (!UUID.test(eventId) || (input.eventId !== undefined && input.eventId !== eventId)) continue;
			const reject = (reason: string, gaps: string[], at = 0): void => {
				refusals.push({ gaps, reason, eventId, at });
			};
			let requestFile: string;
			let receiptFile: string;
			try {
				requestFile = channel.messagePath(key, binding, eventId, "request");
				receiptFile = channel.messagePath(key, binding, eventId, "receipt");
			} catch {
				reject("invalid channel event id", ["channel.event_id"]);
				continue;
			}
			const request = readPrivateJson(channel.dir, requestFile);
			const receipt = readPrivateJson(channel.dir, receiptFile);
			if (request === undefined || receipt === undefined) {
				reject("original request/receipt unavailable", ["channel.request", "channel.receipt"]);
				continue;
			}
			if (
				request.id !== eventId ||
				request.key !== key ||
				request.claim !== claimId ||
				request.binding !== binding ||
				!safeInt(request.at) ||
				!nonblank(request.text) ||
				receipt.id !== eventId ||
				receipt.key !== key ||
				receipt.claim !== claimId ||
				receipt.binding !== binding ||
				receipt.session !== input.sessionId ||
				!safeInt(receipt.receivedAt) ||
				!safeInt(receipt.observedAt) ||
				(receipt.receivedAt as number) > nowMs ||
				(receipt.observedAt as number) < (receipt.receivedAt as number) ||
				(request.at as number) > (receipt.receivedAt as number)
			) {
				reject(
					"request/receipt/current-session/claim binding mismatch",
					["channel.binding", "channel.session", "index.claim"],
					safeInt(request.at) ? (request.at as number) : 0,
				);
				continue;
			}
			if (receipt.state !== "started") {
				reject(
					"stage receipt is not started or has been revoked",
					["channel.receipt-not-started"],
					request.at as number,
				);
				continue;
			}
			if (request.duty !== undefined && !currentDutyRequest(input.projectDir, key, request.duty)) {
				reject("delegated duty source was revoked or expired", ["stage.revoked"], request.at as number);
				continue;
			}
			if (request.stage === undefined) {
				reject(
					"original channel event has no sender-origin typed stage grant; plain text/receipt/eventId is not a grant",
					["channel.typed-stage-grant-missing"],
					request.at as number,
				);
				continue;
			}
			const parsedGrant = parsePmStageGrant(request.stage);
			if (!parsedGrant.ok) {
				reject("sender-origin typed stage grant is invalid", parsedGrant.gaps, request.at as number);
				continue;
			}
			const grant = parsedGrant.value;
			const digest = grantDigest(grant);
			if (receipt.stage_digest !== digest) {
				reject(
					"typed grant does not match the original authenticated receipt",
					["stage.grant-digest"],
					request.at as number,
				);
				continue;
			}
			const windowFile = channel.windowPath(key, claimId);
			const window = readPrivateJson(channel.dir, windowFile);
			if (
				window === undefined ||
				window.claim !== claimId ||
				window.binding !== binding ||
				window.session !== input.sessionId ||
				!safeInt(window.at) ||
				(window.at as number) < (receipt.receivedAt as number) - 15_000 ||
				(window.at as number) > nowMs ||
				nowMs - (window.at as number) >= 15_000
			) {
				reject("authenticated window heartbeat/session does not match this delivery", ["channel.window"]);
				continue;
			}
			const receivedAt = receipt.receivedAt as number;
			const observedAt = receipt.observedAt as number;
			const deadlineMs = Date.parse(grant.deadline);
			const gateScope = /^(gate-\d+)\.([a-f0-9]{64})$/.exec(grant.scope_ref);
			const validScope =
				(input.expectedScope === undefined || grant.scope_ref === input.expectedScope) &&
				(gateScope === null
					? grant.scope_ref === (input.expectedScope ?? PM_STAGE_SCOPE)
					: currentOfflineGateScope(input.projectDir, key, grant.matter_ref, gateScope[1]!, gateScope[2]!));
			if (
				grant.project_ref !== path.basename(channel.dir) ||
				grant.key !== key ||
				!validScope ||
				grant.matter_ref === grant.parent_matter_ref ||
				grant.card_path.split("/").some((part) => part === "." || part === "..")
			) {
				reject(
					"project/key/scope/matter or card range is wrong for this stage",
					["stage.wrong-scope", "stage.wrong-matter"],
					receivedAt,
				);
				continue;
			}
			if (
				!canonicalIso(grant.deadline) ||
				deadlineMs <= receivedAt ||
				deadlineMs > receivedAt + PM_STAGE_MAX_WINDOW_MS ||
				nowMs >= deadlineMs ||
				nowMs - receivedAt > PM_STAGE_MAX_WINDOW_MS
			) {
				reject(
					"stage grant is expired or exceeds the bounded receivedAt+90m window",
					["grant-expired"],
					receivedAt,
				);
				continue;
			}
			if (
				grant.max_steps > PM_STAGE_MAX_STEPS ||
				grant.remaining_cost > PM_STAGE_MAX_COST ||
				grant.no_progress_limit > PM_STAGE_MAX_NO_PROGRESS ||
				grant.max_steps < 1 ||
				grant.remaining_cost < 1 ||
				grant.no_progress_limit < 1
			) {
				reject("stage grant exceeds finite 4/3/2 limits", ["stage.limits"], receivedAt);
				continue;
			}
			const actualPin = cardPinOf(input.projectDir, key, grant.card_path);
			if (actualPin === undefined || actualPin !== grant.card_sha256) {
				reject("pinned stage card bytes do not match the typed grant", ["stage.card-pin"], receivedAt);
				continue;
			}
			return {
				ok: true,
				value: {
					authority_kind: "user-delegated-duty-pm",
					event_id: eventId,
					key,
					claim_id: claimId,
					binding,
					session_id: input.sessionId,
					received_at: receivedAt,
					observed_at: observedAt,
					started_at: new Date(receivedAt).toISOString(),
					stage_id: grant.stage_id,
					scope_ref: grant.scope_ref,
					matter_ref: grant.matter_ref,
					...(grant.parent_matter_ref === undefined ? {} : { parent_matter_ref: grant.parent_matter_ref }),
					card_path: grant.card_path,
					card_sha256: grant.card_sha256,
					write_face: [...grant.write_face].sort(),
					max_steps: grant.max_steps,
					remaining_cost: grant.remaining_cost,
					no_progress_limit: grant.no_progress_limit,
					deadline: grant.deadline,
					grant_digest: digest,
					stage_ref: `pm-channel://${eventId}#request+receipt`,
					request_ref: path.relative(channel.dir, requestFile).replace(/\\/g, "/"),
					receipt_ref: path.relative(channel.dir, receiptFile).replace(/\\/g, "/"),
					window_ref: path.relative(channel.dir, windowFile).replace(/\\/g, "/"),
					grant,
				},
			};
		}
	}
	refusals.sort((a, b) => b.at - a.at);
	const first = refusals[0];
	return first === undefined
		? fail("no authenticated channel stage event for the current claim/session", ["channel.stage-event"])
		: fail(first.reason, first.gaps, first.eventId);
}

// ── Replay-resistant finite stage lifecycle ─────────────────────────────────

export interface PmStageSessionEntry {
	id?: string;
	type?: string;
	customType?: string;
	data?: unknown;
}
export interface PmStageSession {
	read(): { entries: readonly PmStageSessionEntry[] };
	append(customType: string, data: unknown): void;
}
export interface PmStageGenesis {
	id: string;
	kind: "genesis";
	authority_kind: "user-delegated-duty-pm";
	event_id: string;
	grant_digest: string;
	stage_id: string;
	matter_ref: string;
	parent_matter_ref?: string;
	scope_ref: string;
	card_path: string;
	card_sha256: string;
	claim_id: string;
	key: string;
	session_id: string;
	started_at: string;
	deadline: string;
	max_steps: number;
	remaining_cost: number;
	no_progress_limit: number;
	producer_matter_ref?: string;
	producer_steps_consumed?: number;
	producer_expired: boolean;
}

function parseGenesis(value: unknown): PmStageGenesis | undefined {
	if (!isRecord(value)) return undefined;
	const genesis = value as unknown as PmStageGenesis;
	const ok =
		genesis.kind === "genesis" &&
		genesis.authority_kind === "user-delegated-duty-pm" &&
		nonblank(genesis.id) &&
		UUID.test(genesis.event_id) &&
		nonblank(genesis.grant_digest) &&
		nonblank(genesis.stage_id) &&
		nonblank(genesis.matter_ref) &&
		nonblank(genesis.scope_ref) &&
		nonblank(genesis.card_path) &&
		/^[a-f0-9]{64}$/.test(genesis.card_sha256) &&
		nonblank(genesis.claim_id) &&
		nonblank(genesis.key) &&
		nonblank(genesis.session_id) &&
		canonicalIso(genesis.started_at) &&
		canonicalIso(genesis.deadline) &&
		Number.isSafeInteger(genesis.max_steps) &&
		Number.isSafeInteger(genesis.remaining_cost) &&
		Number.isSafeInteger(genesis.no_progress_limit) &&
		typeof genesis.producer_expired === "boolean";
	return ok ? genesis : undefined;
}

function genesisOf(direction: PmStageDirection): PmStageGenesis {
	return {
		id: randomUUID(),
		kind: "genesis",
		authority_kind: "user-delegated-duty-pm",
		event_id: direction.event_id,
		grant_digest: direction.grant_digest,
		stage_id: direction.stage_id,
		matter_ref: direction.matter_ref,
		...(direction.parent_matter_ref === undefined ? {} : { parent_matter_ref: direction.parent_matter_ref }),
		scope_ref: direction.scope_ref,
		card_path: direction.card_path,
		card_sha256: direction.card_sha256,
		claim_id: direction.claim_id,
		key: direction.key,
		session_id: direction.session_id,
		started_at: direction.started_at,
		deadline: direction.deadline,
		max_steps: direction.max_steps,
		remaining_cost: direction.remaining_cost,
		no_progress_limit: direction.no_progress_limit,
		...(direction.grant.producer_history === undefined
			? {}
			: {
					producer_matter_ref: direction.grant.producer_history.matter_ref,
					producer_steps_consumed: direction.grant.producer_history.steps_consumed,
				}),
		producer_expired: true,
	};
}

function sameGenesis(a: PmStageGenesis, b: PmStageGenesis): boolean {
	const volatile = (value: PmStageGenesis): string => JSON.stringify({ ...value, id: "" });
	return volatile(a) === volatile(b);
}

/** ONE genesis per stage lifecycle. A repeated restart/reload of the SAME event
 *  is a continuation (replayed), never a reset; a second event id or changed
 *  pin/scope/limits/deadline for the same stage is refused. */
export class PmStageLedger {
	admit(
		session: PmStageSession | undefined,
		direction: PmStageDirection,
	): PmStageRead<{ genesisRef: string; replayed: boolean }> {
		if (session === undefined) return fail("stage lifecycle session is not attached", ["stage.session"]);
		const genesis = genesisOf(direction);
		const existing = session
			.read()
			.entries.filter((entry) => entry.type === "custom" && entry.customType === PM_STAGE_ENTRY_TYPE)
			.map((entry) => parseGenesis(entry.data))
			.filter((entry): entry is PmStageGenesis => entry !== undefined);
		for (const prior of existing) {
			if (prior.stage_id !== direction.stage_id && prior.matter_ref !== direction.matter_ref) continue;
			if (prior.event_id !== direction.event_id)
				return fail(
					"second event id cannot reset an existing stage lifecycle",
					["stage-lifecycle-replay"],
					direction.event_id,
				);
			if (!sameGenesis(prior, genesis))
				return fail(
					"replayed event changed genesis scope/pin/budget/history",
					["stage-replay-drift"],
					direction.event_id,
				);
			return { ok: true, value: { genesisRef: `${PM_STAGE_ENTRY_TYPE}#${prior.id}`, replayed: true } };
		}
		try {
			session.append(PM_STAGE_ENTRY_TYPE, genesis);
			const observed = session.read().entries.some((entry) => isRecord(entry.data) && entry.data.id === genesis.id);
			if (!observed)
				return fail("stage genesis observation is unknown", ["stage.observation-unknown"], direction.event_id);
		} catch {
			return fail("stage genesis observation failed", ["stage.observation-unknown"], direction.event_id);
		}
		return { ok: true, value: { genesisRef: `${PM_STAGE_ENTRY_TYPE}#${genesis.id}`, replayed: false } };
	}

	/** Attribution report only. The expired producer allowance is NEVER used as
	 *  the current stage budget, reset or renewed. */
	static attribution(direction: PmStageDirection): {
		authority_kind: "user-delegated-duty-pm";
		stage_matter_ref: string;
		stage_deadline: string;
		limits: { max_steps: number; remaining_cost: number; no_progress_limit: number };
		producer: { matter_ref?: string; steps_consumed?: number; expired: true; immutable: true; borrowed: false };
	} {
		return {
			authority_kind: "user-delegated-duty-pm",
			stage_matter_ref: direction.matter_ref,
			stage_deadline: direction.deadline,
			limits: {
				max_steps: direction.max_steps,
				remaining_cost: direction.remaining_cost,
				no_progress_limit: direction.no_progress_limit,
			},
			producer: {
				...(direction.grant.producer_history === undefined
					? {}
					: {
							matter_ref: direction.grant.producer_history.matter_ref,
							steps_consumed: direction.grant.producer_history.steps_consumed,
						}),
				expired: true,
				immutable: true,
				borrowed: false,
			},
		};
	}
}

/** Stable digest over sender-origin typed stage metadata. */
export function stageSourceDigest(direction: PmStageDirection): string {
	return createHash("sha256")
		.update(
			JSON.stringify([
				direction.authority_kind,
				direction.event_id,
				direction.claim_id,
				direction.key,
				direction.session_id,
				direction.grant_digest,
				direction.card_sha256,
				direction.matter_ref,
				direction.scope_ref,
			]),
		)
		.digest("hex");
}

/** Required shared index type is referenced here so a future store/schema fork
 *  is visible at this boundary; the live row is always re-read by the reader. */
export function stageIndexRoot(projectDir: string): IndexStore {
	return new IndexStore(agenticdocRoot(projectDir));
}
