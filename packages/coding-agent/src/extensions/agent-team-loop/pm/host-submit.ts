/** T04B: local PLANNED selection entry — ask → host offer → submit_decision_handoff
 * → the single frozen `LocalSelectionStore.commitSelection`.
 *
 * This module is deliberately a thin HOST-side bridge:
 *  - The ONLY externally callable tool is `submit_decision_handoff` with three
 *    non-blank string params `{offer_id, choice, basis_id}` and
 *    additionalProperties=false. No model parameter can mint a host/key/role/
 *    source/claim/task/run/parent/budget/proof authority.
 *  - An immutable host-signed OFFER is a preparation SNAPSHOT, never a DP
 *    answer and never a capability. `offer_id`/`local_ref` are opaque host
 *    values, physically separate from any DP decision_id. A real parent DP is
 *    referenced ONLY by the frozen `{kind:'dp',decision_id}` ref.
 *  - A successful submit writes ONLY through the frozen store's
 *    `commitSelection`, and returns `planned / business_completed=false`.
 *    It never writes an execution, DP lifecycle/local receipt, gate/QG/sign/Done.
 *  - The default adapter exists but supplies NO grant without explicit host
 *    authorization and live accounting hooks. This bridge freezes the pin/unit
 *    binding per offer; C/D/I supply real accounting and action observations.
 */

import { createHash } from "node:crypto";
import * as path from "node:path";
import { Type } from "typebox";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import {
	type DecisionPreparation,
	decisionActorAllowed,
	type PreparedBasis,
	preparationProblems,
	selectedDecisionBasis,
	validateDecisionMaterial,
} from "../shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.ts";
import {
	DECISION_HANDOFF_SCHEMA_ID,
	type HostRole,
	isJsonValue,
	type JsonValue,
	type LocalSelectionRecordV1,
	type LocalSource,
} from "../shared/decision-handoff.ts";
import {
	type CommitSelectionRequest,
	type LocalSelectionHostAdapter,
	LocalSelectionStore,
	type LocalWriteResult,
} from "../shared/local-selection-store.ts";
import { agenticdocRoot, controlRootFromTaskPath } from "../shared/paths.ts";
import type { LocalTrustedOfferCertificate, LocalTrustedOfferProvenance } from "./decision-followup.ts";
import {
	createRuntimeHostAdapter,
	type RuntimeHostAdapterConfig,
	type RuntimeHostAuthorization,
	type RuntimeHostToolRuntimeSource,
	type RuntimeOfferExpected,
} from "./runtime-host-adapter.ts";
import { canonicalStateJson } from "./triage-client.ts";

// ── Tool surface ───────────────────────────────────────────────────────────

/** The ONE external submit entry. */
export const SUBMIT_DECISION_HANDOFF_TOOL = "submit_decision_handoff";

/** Strict external parameters — three non-empty strings, nothing else. */
export const SUBMIT_DECISION_HANDOFF_PARAMETERS = Type.Object(
	{
		offer_id: Type.String({ minLength: 1, description: "Opaque host-signed offer id from a prior ask" }),
		choice: Type.String({ minLength: 1, description: "One current candidate id" }),
		basis_id: Type.String({ minLength: 1, description: "One prepared basis id that applies to the choice" }),
	},
	{ additionalProperties: false },
);

// ── Host-only typed inputs/outputs (never tool parameters) ─────────────────

/** Structural identity of the registering window, derived in CODE from the
 *  live PM claim / worker card+run. A model parameter can never set these. */
export interface OfferHostIdentity {
	source: LocalSource;
	key: string;
	role: HostRole;
	claimId?: string;
	owner?: string;
	taskKey?: string;
	runId?: string;
	/** Host-derived PM stage coordinates; never model parameters. */
	stageId?: string;
	scopeRef?: string;
}

/** Re-derived by the ask host closure at prepare AND submit time. It is the
 *  ONLY source for drift revalidation; never a model string. */
export interface OfferRevalidation {
	configSignature: string;
	hostSignature: string;
	identity: OfferHostIdentity;
	trustedStop: boolean;
	/** Stable typed stage matter; a changed value cannot reuse an old offer. */
	stageMatterRef?: string;
}

/** Explicit parent→successor join from the host's authoritative gate/lifecycle
 *  reader. Never derived from an offer id, local_ref or a fallback parent ref. */
export interface OfferParentJoin {
	decision_id: string;
	logical_id: string;
	matter_ref: string;
	matter_version: string;
}

export interface PrepareOfferInput {
	dp: string;
	identity: OfferHostIdentity;
	material?: Record<string, unknown>;
	preparation?: DecisionPreparation;
	context?: Record<string, unknown>;
	/** A REAL available DP decision_id only; absent otherwise (never a local_ref). */
	parentDecisionId?: string;
	/** Optional explicit parent→successor join for the local follow-up consumer. */
	parentJoin?: OfferParentJoin;
	/** Stable matter identity from the ask host context (turn/trigger-free). */
	matterRef: string;
	/** Host-derived stable stage matter identity, when this is a PM stage offer. */
	stageMatterRef?: string;
	/** Frozen T01 classification effect_state === "unknown" marker. */
	feedbackEffectUnknown: boolean;
	/** Host-only thunk re-deriving current config/host/identity/stop facts. */
	revalidate: () => OfferRevalidation;
}

export interface SubmitOfferMetadata {
	submittable: boolean;
	submit_tool: typeof SUBMIT_DECISION_HANDOFF_TOOL;
	offer_id?: string;
	local_ref?: string;
	dp?: string;
	candidates?: string[];
	basis_ids?: string[];
	gaps?: string[];
}

export type PrepareOfferResult =
	| { prepared: true; metadata: SubmitOfferMetadata }
	| { prepared: false; metadata: SubmitOfferMetadata };

/** Minimal host-observed expected projection for the T06/L1 adapter junction.
 *  `budget_ref` is owned by the adapter (it appears in both budget and expected). */
export interface OfferExpected {
	/** Detached host identity and raw matter, independent from model submit. */
	identity?: OfferHostIdentity;
	matter_identity?: string;
	stage_matter_ref?: string;
	matter_ref: string;
	matter_version: string;
	material_digest: string;
	basis_digest: string;
	parent_decision_id?: string;
}

/** A real successful submit, joinable ONLY by its actual toolCallId. */
export interface CommittedSelection {
	toolCallId: string;
	offerId: string;
	localRef: string;
	choice: string;
	basisId: string;
	code: "written" | "duplicate";
	record: LocalSelectionRecordV1;
}

/** The typed host handle shared between ask (prepareOffer) and T05
 *  (readCommittedSelection). Not a capability; host-only object. */
/** Scope values are PM-consumer LOCATORS/equality constraints only. The
 *  certificate fields are built from the host's current FrozenOffer. */
/** Locator fields only. The real taskKey comes from the frozen offer's host
 *  identity and is returned in the certificate, not supplied by the consumer. */
export interface CurrentOfferCertificateScope {
	key: string;
	source: LocalSource;
	claim_id: string;
	parent_ref: string;
	parent_decision_id: string;
	parent_logical_id: string;
	parent_matter_version: string;
	target_dp: string;
	material_version: string;
	basis_version: string;
	restricted_action: string;
}

export interface CurrentOfferCertificate extends LocalTrustedOfferCertificate {
	identity_task_key: string;
	provenance: LocalTrustedOfferProvenance;
}

export interface SubmitDecisionHostHandle {
	prepareOffer(input: PrepareOfferInput): PrepareOfferResult;
	readCommittedSelection(toolCallId: string): CommittedSelection | undefined;
	/** Host-only junction for the trusted adapter to read the frozen expected
	 *  projection for an offer's local_ref. Never a model tool parameter. */
	hostExpectedFor(localRef: string): OfferExpected | undefined;
	/** Optional production junction supplied by registerSubmitDecisionHandoffTool. */
	currentOfferCertificateFor?(
		localRef: string,
		scope: CurrentOfferCertificateScope,
	): CurrentOfferCertificate | undefined;
	/** The ONE production host object shared with PM/worker lifecycle. */
	runtimeHost?: RuntimeHostToolRuntimeSource;
}

export interface SubmitDecisionToolConfig {
	/** Control workspace root. Derived from PI_WORKER_TASK / cwd when omitted. */
	projectDir?: string;
	/** T06 production adapter / L1 fixture. Omitted ⇒ controlled write fails closed. */
	hostAdapter?: LocalSelectionHostAdapter;
	/** Host-only A/C/D/I integration hooks, never business tool parameters.
	 * Missing authorization or live accounting keeps default runtime refused. */
	runtimeHost?: Pick<RuntimeHostAdapterConfig, "authorizationFor" | "budgetSnapshotFor" | "verifyExecution"> & {
		authorizationGapsFor?: (expected: RuntimeOfferExpected) => string[];
	};
	/** ONE host object / frozen store / C / D for this activated window. */
	hostRuntime?: RuntimeHostToolRuntimeSource;
	/** Deterministic test clock; production uses the real host clock. */
	clock?: () => number;
	/** Isolated test agenticdoc root; production derives from projectDir. */
	agenticdocRootOverride?: string;
}

export interface SubmitDecisionHandoffDetails {
	status: "planned" | "refused";
	business_completed: false;
	/** True only for a store verified planned selection. */
	selection_written: boolean;
	offer_id: string;
	choice: string;
	basis_id: string;
	local_ref?: string;
	code?: string;
	kind?: string;
	gaps: string[];
	reason: string;
}

// ── Deterministic helpers (no `any`, no inline imports) ────────────────────

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Canonical JSON with sorted object keys — stable across turns/serialisers. */
function stableJson(value: unknown): string {
	if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
	if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
	const record = value as Record<string, unknown>;
	return `{${Object.keys(record)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`)
		.join(",")}}`;
}

/** Deterministic SHA256 over canonical JSON of a VALID JSON value. The digest
 *  is computed by the host from the full business reference, never accepted
 *  from a model parameter and never truncated by a DP transport cap. */
function digestOf(value: JsonValue): string {
	return createHash("sha256").update(stableJson(value)).digest("hex");
}

function asJsonValue(value: unknown): JsonValue | undefined {
	try {
		const round = JSON.parse(JSON.stringify(value)) as unknown;
		return isJsonValue(round) ? round : undefined;
	} catch {
		return undefined;
	}
}

/** Flatten nested business material to dotted field paths so each
 *  `basis_catalog[].material_refs` (a field path) is a real top-level key of
 *  the MaterialEnvelope.fields object the frozen store requires. */
function flattenMaterialFields(material: Record<string, unknown>): Record<string, JsonValue> {
	const out: Record<string, JsonValue> = {};
	const walk = (obj: Record<string, unknown>, prefix: string): void => {
		for (const [key, value] of Object.entries(obj)) {
			const path = prefix === "" ? key : `${prefix}.${key}`;
			if (isRecord(value)) {
				const parent = asJsonValue(value);
				if (parent !== undefined) out[path] = parent;
				walk(value, path);
			} else {
				const leaf = asJsonValue(value);
				if (leaf !== undefined) out[path] = leaf;
			}
		}
	};
	walk(material, "");
	return out;
}

/** Candidate source is the registry's fixedChoiceIds or the validated dynamic
 *  handling_options ids — NEVER derived from basis.applies_to. */
function candidateIds(dp: string, material: Record<string, unknown>): string[] {
	const entry = DECIDE_REGISTRY[dp];
	if (entry.kind === "dynamic-candidates" && Array.isArray(material.handling_options)) {
		return material.handling_options.flatMap((item) =>
			isRecord(item) && typeof item.id === "string" && item.id.trim() !== "" ? [item.id] : [],
		);
	}
	return [...entry.fixedChoiceIds];
}

/** The frozen contract/mode version of a local selection matter. */
export const SUBMIT_MATTER_VERSION = `${DECISION_HANDOFF_SCHEMA_ID}:local-selection-v1`;

interface FrozenOffer {
	offerId: string;
	localRef: string;
	dp: string;
	identity: OfferHostIdentity;
	material: Record<string, unknown>;
	preparation: DecisionPreparation;
	context: Record<string, unknown> | undefined;
	parent?: { kind: "dp"; decision_id: string };
	parentJoin?: OfferParentJoin;
	matterRef: string;
	stageMatterRef?: string;
	matterRefHash: string;
	matterVersion: string;
	materialDigest: string;
	basisDigest: string;
	candidates: string[];
	basisIds: string[];
	configSignature: string;
	hostSignature: string;
	trustedStop: boolean;
	identitySignature: string;
	feedbackEffectUnknown: boolean;
	runtimeAuthorization?: RuntimeHostAuthorization;
	runtimeAuthorizationSignature?: string;
	runtimeAuthorizationGaps?: string[];
	revalidate: () => OfferRevalidation;
}

/** Deterministic substantive identity. Observation fields (prepared_at,
 *  observed_at, trigger, turn) are EXCLUDED, so a re-stamp reuses identity and
 *  never buys a new budget/record. Matter/material/basis/candidates/parent/
 *  config/host/identity/stop/budget changes DO change the identity. */
function offerIdentityParts(input: PrepareOfferInput, rev: OfferRevalidation): Record<string, unknown> {
	return {
		dp: input.dp,
		identity: rev.identity,
		material: input.material ?? null,
		preparation: input.preparation === undefined ? null : { basis_catalog: input.preparation.basis_catalog },
		context: input.context ?? null,
		parent: input.parentDecisionId ?? null,
		parent_join: input.parentJoin ?? null,
		matter_ref: input.matterRef,
		stage_matter_ref: input.stageMatterRef ?? null,
		config: rev.configSignature,
		host: rev.hostSignature,
		stop: rev.trustedStop,
	};
}

function identityHash(parts: Record<string, unknown>): string {
	return createHash("sha256").update(stableJson(parts)).digest("hex");
}

// ── Registration ───────────────────────────────────────────────────────────

export function registerSubmitDecisionHandoffTool(
	pi: ExtensionAPI,
	config: SubmitDecisionToolConfig,
): SubmitDecisionHostHandle {
	const taskPath = process.env.PI_WORKER_TASK;
	const projectDir = config.projectDir ?? (taskPath ? controlRootFromTaskPath(path.resolve(taskPath)) : process.cwd());
	const root = config.agenticdocRootOverride ?? agenticdocRoot(projectDir);
	// The store is built PER SUBMIT from the FROZEN offer's real bound key, so
	// the controlled write is structurally tied to the live PM claim / worker
	// card+run that produced the offer — never to a guessed registration key.
	// T06: an explicit adapter (a test fixture or a host override) always wins.
	// An isolated `agenticdocRootOverride` is by definition a host FIXTURE root:
	// it must inject its own adapter, so the historical
	// `trusted-context-missing` fail-closed contract is preserved there.
	// Production (no override) uses the real runtime adapter, which reads the
	// index row, run.json, task.md head and the pinned card and returns
	// undefined — not a default grant — when those files do not support the commit.
	const runtimeAdapter =
		(config.hostRuntime !== undefined ? undefined : config.hostAdapter) ??
		(config.hostRuntime === undefined && config.agenticdocRootOverride === undefined
			? createRuntimeHostAdapter({
					agenticdocRoot: root,
					expectedFor: (localRef) => hostExpectedFor(localRef),
					authorizationFor: (localRef, expected) => {
						const offer = [...offersById.values()].find((item) => item.localRef === localRef);
						if (offer?.runtimeAuthorization === undefined) return undefined;
						const current = config.runtimeHost?.authorizationFor?.(localRef, expected);
						if (current === undefined || stableJson(current) !== offer.runtimeAuthorizationSignature)
							return undefined;
						return structuredClone(offer.runtimeAuthorization);
					},
					budgetSnapshotFor: config.runtimeHost?.budgetSnapshotFor,
					verifyExecution: config.runtimeHost?.verifyExecution,
					clock: config.clock,
				})
			: undefined);
	const storeFor = (key: string): LocalSelectionStore | undefined =>
		config.hostRuntime !== undefined
			? undefined
			: new LocalSelectionStore({
					agenticdoc_root: root,
					key,
					...(runtimeAdapter === undefined ? {} : { host_adapter: runtimeAdapter }),
					...(config.clock === undefined ? {} : { clock: config.clock }),
				});

	const offersById = new Map<string, FrozenOffer>();
	const currentByMatter = new Map<string, string>();
	const committed = new Map<string, CommittedSelection>();
	config.hostRuntime?.bindExpectedFor((localRef) => hostExpectedFor(localRef));

	function metadataFor(offer: FrozenOffer): SubmitOfferMetadata {
		return {
			submittable: true,
			submit_tool: SUBMIT_DECISION_HANDOFF_TOOL,
			offer_id: offer.offerId,
			local_ref: offer.localRef,
			dp: offer.dp,
			candidates: offer.candidates,
			basis_ids: offer.basisIds,
		};
	}

	function prepareOffer(input: PrepareOfferInput): PrepareOfferResult {
		const gaps: string[] = [];
		const refuse = (): PrepareOfferResult => ({
			prepared: false,
			metadata: { submittable: false, submit_tool: SUBMIT_DECISION_HANDOFF_TOOL, gaps },
		});
		// Identity gate: role must be structurally eligible for this dp, and a
		// worker-local source must have its task/run association.
		if (typeof input.matterRef !== "string" || !input.matterRef.trim()) {
			gaps.push("matter_ref");
			return refuse();
		}
		if (!decisionActorAllowed(input.dp, input.identity.role)) {
			gaps.push("identity.role-forbidden");
			return refuse();
		}
		if (!isRecord(input.material)) {
			gaps.push("material");
			return refuse();
		}
		const validated = validateDecisionMaterial(input.dp, input.material);
		if (!validated.ok) {
			for (const issue of validated.issues) gaps.push(issue.field);
			return refuse();
		}
		if (!isRecord(input.preparation)) {
			gaps.push("preparation");
			return refuse();
		}
		if (
			input.parentJoin !== undefined &&
			(input.parentDecisionId !== input.parentJoin.decision_id ||
				!input.parentJoin.logical_id.trim() ||
				!input.parentJoin.matter_ref.trim() ||
				!input.parentJoin.matter_version.trim())
		) {
			gaps.push("parent-join");
			return refuse();
		}
		const prep = input.preparation as unknown as DecisionPreparation;
		const prepRecord = input.preparation as unknown as Record<string, unknown>;
		const catalog = prepRecord.basis_catalog;
		if (!Array.isArray(catalog) || catalog.length === 0) {
			gaps.push("preparation.basis_catalog");
			return refuse();
		}
		const problems = preparationProblems(input.dp, validated.material, prepRecord, input.context);
		if (problems.length > 0) {
			gaps.push(...problems);
			return refuse();
		}
		const rev = input.revalidate();
		if (rev.trustedStop) {
			gaps.push("trusted-stop");
			return refuse();
		}

		const materialJson = asJsonValue(input.material);
		const prepJson = asJsonValue({ basis_catalog: prep.basis_catalog });
		if (materialJson === undefined || prepJson === undefined) {
			gaps.push("material.json");
			return refuse();
		}
		const ctxJson = input.context === undefined ? null : asJsonValue(input.context);
		if (input.context !== undefined && ctxJson === null) {
			gaps.push("context.json");
			return refuse();
		}
		// Full local business reference, NOT truncated by any transport cap.
		const materialDigest = digestOf({ material: materialJson, context: ctxJson } as JsonValue);
		const basisDigest = digestOf(prepJson);
		const candidates = candidateIds(input.dp, validated.material);
		const basisIds = (prep.basis_catalog as PreparedBasis[]).map((item) => item.id);
		const parent =
			input.parentDecisionId === undefined
				? undefined
				: { kind: "dp" as const, decision_id: input.parentDecisionId };

		const parts = offerIdentityParts(input, rev);
		const hash = identityHash(parts);
		const offerId = `offer:${hash}`;
		const localRef = `lref:${hash.slice(0, 32)}`;
		const matterRefHash = createHash("sha256")
			.update(stableJson({ v: SUBMIT_MATTER_VERSION, m: input.matterRef }))
			.digest("hex")
			.slice(0, 32);

		const existing = offersById.get(offerId);
		if (existing !== undefined) {
			// Same substantive matter: reuse identity, no new budget/record.
			// Sticky unknown effect: once a re-prepare of this very offer observes
			// feedbackEffectUnknown=true, the old commit-capable false state must
			// NOT come back. A later false self-report cannot erase the uncertainty;
			// only a genuinely new substantive identity (which mints a fresh offer
			// below) re-prepares per the original contract. The unknown observation
			// is deliberately excluded from offerIdentityParts, so it cannot buy a
			// new id / local_ref / budget.
			if (input.feedbackEffectUnknown) existing.feedbackEffectUnknown = true;
			// P1-03: re-preparing the SAME frozen identity may reuse that identity,
			// but it can NEVER reverse a real supersession. Only a still-current (or
			// not yet superseded) identity keeps/claims the matter pointer; an older
			// offer whose matter already moved to a newer lawful offer stays
			// superseded instead of stealing currentness back from it. The reuse
			// itself stays a plain read (no new id/local_ref/budget/record).
			const currentOfferId = currentByMatter.get(existing.matterRefHash);
			if (currentOfferId === undefined || currentOfferId === existing.offerId) {
				currentByMatter.set(existing.matterRefHash, offerId);
				return { prepared: true, metadata: metadataFor(existing) };
			}
			return {
				prepared: true,
				metadata: { ...metadataFor(existing), submittable: false, gaps: ["offer-superseded"] },
			};
		}
		const offer: FrozenOffer = {
			offerId,
			localRef,
			dp: input.dp,
			identity: rev.identity,
			material: validated.material,
			preparation: prep,
			context: input.context,
			parent,
			...(input.parentJoin === undefined ? {} : { parentJoin: structuredClone(input.parentJoin) }),
			matterRef: input.matterRef,
			...(input.stageMatterRef === undefined ? {} : { stageMatterRef: input.stageMatterRef }),
			matterRefHash,
			matterVersion: SUBMIT_MATTER_VERSION,
			materialDigest,
			basisDigest,
			candidates,
			basisIds,
			configSignature: rev.configSignature,
			hostSignature: rev.hostSignature,
			trustedStop: rev.trustedStop,
			identitySignature: stableJson(rev.identity),
			feedbackEffectUnknown: input.feedbackEffectUnknown,
			revalidate: input.revalidate,
		};
		try {
			const authorization = config.runtimeHost?.authorizationFor?.(localRef, expectedProjection(offer));
			if (authorization !== undefined) {
				offer.runtimeAuthorization = structuredClone(authorization);
				offer.runtimeAuthorizationSignature = stableJson(authorization);
			}
		} catch {
			// An unavailable host policy cannot authorize the later submit. It must
			// not break independently legal decision preparation/transport.
		}
		if (offer.runtimeAuthorization === undefined) {
			const gaps = config.runtimeHost?.authorizationGapsFor?.(expectedProjection(offer));
			if (gaps !== undefined) offer.runtimeAuthorizationGaps = [...gaps];
		}
		offersById.set(offerId, offer);
		// Any older offer for this matter is superseded (material/config drift).
		currentByMatter.set(matterRefHash, offerId);
		return { prepared: true, metadata: metadataFor(offer) };
	}

	function expectedProjection(offer: FrozenOffer): RuntimeOfferExpected {
		return {
			identity: structuredClone(offer.identity),
			matter_identity: offer.matterRef,
			...(offer.stageMatterRef === undefined ? {} : { stage_matter_ref: offer.stageMatterRef }),
			matter_ref: offer.matterRefHash,
			matter_version: offer.matterVersion,
			material_digest: offer.materialDigest,
			basis_digest: offer.basisDigest,
			...(offer.parent === undefined ? {} : { parent_decision_id: offer.parent.decision_id }),
		};
	}

	function hostExpectedFor(localRef: string): OfferExpected | undefined {
		for (const offer of offersById.values()) {
			if (offer.localRef === localRef) {
				// P1-04: this projection authorizes a REAL ACTION (the adapter's
				// readTargetAuthorization / beforeToolCall / trusted store context), so
				// it shares the SAME currentness and unknown-effect boundary as submit
				// and the current-offer certificate. A superseded offer whose own
				// revalidate facts still hold must not keep an older action window open,
				// and an offer under sticky unknown feedback can never authorize a body.
				if (offer.feedbackEffectUnknown) return undefined;
				if (currentByMatter.get(offer.matterRefHash) !== offer.offerId) return undefined;
				const basis = offer.preparation.basis_catalog.find((item) =>
					item.applies_to.some((choice) => offer.candidates.includes(choice)),
				);
				const choice = basis?.applies_to.find((item) => offer.candidates.includes(item));
				try {
					if (basis === undefined || choice === undefined || revalidateOffer(offer, choice, basis.id).length > 0)
						return undefined;
					return expectedProjection(offer);
				} catch {
					return undefined;
				}
			}
		}
		return undefined;
	}

	/** Host-only readonly CURRENT offer certificate. `scope` values are equal
	 *  constraints from the registered PM consumer, never sources of authority;
	 *  all returned fields come from this host's FrozenOffer/currentByMatter,
	 *  real committed selection and freshly revalidated canonical material,
	 *  context (explicitly absent here), catalog and basis applicability. */
	function currentOfferCertificateFor(
		localRef: string,
		scope: CurrentOfferCertificateScope,
	): CurrentOfferCertificate | undefined {
		const offer = [...offersById.values()].find((item) => item.localRef === localRef);
		const committedForRef = [...committed.values()].filter((item) => item.localRef === localRef);
		if (
			offer === undefined ||
			offer.context !== undefined ||
			offer.feedbackEffectUnknown ||
			offer.trustedStop ||
			offer.parent === undefined ||
			offer.parentJoin === undefined ||
			currentByMatter.get(offer.matterRefHash) !== offer.offerId ||
			committedForRef.length === 0 ||
			committedForRef.some(
				(item) => item.choice !== committedForRef[0]?.choice || item.basisId !== committedForRef[0]?.basisId,
			)
		)
			return undefined;
		const selectedAction = committedForRef[0]?.choice;
		const selectedBasisId = committedForRef[0]?.basisId;
		if (selectedAction === undefined || selectedBasisId === undefined) return undefined;
		const validated = validateDecisionMaterial(offer.dp, offer.material);
		if (!validated.ok) return undefined;
		const basis = selectedDecisionBasis(
			offer.dp,
			validated.material,
			offer.preparation,
			selectedAction,
			selectedBasisId,
		);
		const canonicalMaterialDigest = createHash("sha256").update(canonicalStateJson(offer.material)).digest("hex");
		const canonicalCatalogDigest = createHash("sha256").update(canonicalStateJson(offer.preparation)).digest("hex");
		const materialFields = Object.keys(flattenMaterialFields(offer.material));
		const basisCatalog = structuredClone(offer.preparation.basis_catalog as PreparedBasis[]);
		const basisMaterialRefs = [...(basis?.material_refs ?? [])];
		if (
			revalidateOffer(offer, selectedAction, selectedBasisId).length > 0 ||
			basis === undefined ||
			!basis.applies_to.includes(selectedAction) ||
			basisMaterialRefs.length === 0 ||
			!basisMaterialRefs.every((ref) => materialFields.includes(ref)) ||
			scope.key !== offer.identity.key ||
			scope.source !== offer.identity.source ||
			typeof offer.identity.taskKey !== "string" ||
			!offer.identity.taskKey.trim() ||
			scope.claim_id !== offer.identity.claimId ||
			!offer.identity.claimId?.trim() ||
			offer.identity.role !== "pm" ||
			scope.parent_ref !== offer.parentJoin.matter_ref ||
			scope.parent_decision_id !== offer.parentJoin.decision_id ||
			scope.parent_decision_id !== offer.parent.decision_id ||
			scope.parent_logical_id !== offer.parentJoin.logical_id ||
			scope.parent_matter_version !== offer.parentJoin.matter_version ||
			scope.target_dp !== offer.dp ||
			scope.material_version !== canonicalMaterialDigest ||
			scope.basis_version !== canonicalCatalogDigest ||
			scope.restricted_action !== selectedAction
		)
			return undefined;
		const certificate: CurrentOfferCertificate = {
			current: true,
			current_by_matter: true,
			offer_id: offer.offerId,
			local_ref: localRef,
			parent_decision_id: offer.parentJoin.decision_id,
			parent_matter_version: offer.parentJoin.matter_version,
			matter_ref: offer.matterRefHash,
			matter_version: offer.matterVersion,
			canonical_material_digest: canonicalMaterialDigest,
			canonical_catalog_digest: canonicalCatalogDigest,
			target_dp: offer.dp,
			selected_action: selectedAction,
			selected_basis_id: selectedBasisId,
			basis_applies_to: [...basis.applies_to],
			identity_task_key: offer.identity.taskKey,
			provenance: {
				origin: "host-submit:FrozenOffer",
				material: structuredClone(offer.material) as Record<string, JsonValue>,
				context: null,
				preparation: structuredClone(offer.preparation) as unknown as Record<string, JsonValue>,
				material_fields: materialFields,
				basis_catalog: basisCatalog,
				basis_material_refs: basisMaterialRefs,
				parent_ref: offer.parentJoin.matter_ref,
				parent_logical_id: offer.parentJoin.logical_id,
				parent_decision_id: offer.parentJoin.decision_id,
				parent_matter_version: offer.parentJoin.matter_version,
				identity_task_key: offer.identity.taskKey,
				current_offer_id: offer.offerId,
			},
		};
		return structuredClone(certificate);
	}

	function readCommittedSelection(toolCallId: string): CommittedSelection | undefined {
		const stored = committed.get(toolCallId);
		if (stored === undefined) return undefined;
		// Hand out a DETACHED deep copy, never the Map's mutable object. Its
		// nested `record` (host_binding / parent_decision_ref / ...) and the
		// metadata are cloned, so a consumer mutating the returned value can
		// neither alter the trusted store nor any later trusted read-back, and
		// no authorization can be rebuilt from tool_result `details` (which
		// never carried the record). The clone is a real mutable
		// CommittedSelection, so its declared type and runtime agree.
		return structuredClone(stored);
	}

	/** Revalidate registry material / preparation / selectedDecisionBasis /
	 *  current candidates and recompute digests on EVERY submit. */
	function revalidateOffer(offer: FrozenOffer, choice: string, basisId: string): string[] {
		const gaps: string[] = [];
		const now = offer.revalidate();
		if (now.trustedStop) gaps.push("trusted-stop");
		if (now.configSignature !== offer.configSignature) gaps.push("config-drift");
		if (now.hostSignature !== offer.hostSignature) gaps.push("host-facts-drift");
		if (stableJson(now.identity) !== offer.identitySignature) gaps.push("identity-drift");
		if (now.stageMatterRef !== offer.stageMatterRef) gaps.push("stage-matter-drift");
		const validated = validateDecisionMaterial(offer.dp, offer.material);
		if (!validated.ok) {
			for (const issue of validated.issues) gaps.push(`material.${issue.field}`);
			return gaps;
		}
		const prepRecord = offer.preparation as unknown as Record<string, unknown>;
		const problems = preparationProblems(offer.dp, validated.material, prepRecord, offer.context);
		if (problems.length > 0) {
			gaps.push(...problems.map((problem) => `preparation.${problem}`));
			return gaps;
		}
		const currentCandidates = candidateIds(offer.dp, validated.material);
		if (stableJson(currentCandidates) !== stableJson(offer.candidates)) gaps.push("candidate-drift");
		const basis = selectedDecisionBasis(offer.dp, validated.material, offer.preparation, choice, basisId);
		if (basis === undefined) gaps.push("choice-or-basis-invalid");
		const materialJson = asJsonValue(offer.material);
		const prepJson = asJsonValue({ basis_catalog: offer.preparation.basis_catalog });
		const ctxJson = offer.context === undefined ? null : asJsonValue(offer.context);
		if (materialJson === undefined || prepJson === undefined) gaps.push("digest-input-invalid");
		else {
			if (digestOf({ material: materialJson, context: ctxJson } as JsonValue) !== offer.materialDigest)
				gaps.push("material-digest-drift");
			if (digestOf(prepJson) !== offer.basisDigest) gaps.push("basis-digest-drift");
		}
		return gaps;
	}

	pi.registerTool<typeof SUBMIT_DECISION_HANDOFF_PARAMETERS, SubmitDecisionHandoffDetails>({
		name: SUBMIT_DECISION_HANDOFF_TOOL,
		label: SUBMIT_DECISION_HANDOFF_TOOL,
		description:
			"Record a local PLANNED selection for a host-signed offer when the external decision service is " +
			"unavailable/disabled. Submit exactly {offer_id, choice, basis_id}; the host re-checks identity, " +
			"registry material/preparation/candidates and recomputes digests. On success it writes ONLY a planned " +
			"local-selection through the single frozen store and returns business_completed=false (never an " +
			"execution, DP receipt, sign or Done). With no production host adapter/budget it fails closed.",
		promptSnippet: "submit_decision_handoff(offer_id, choice, basis_id) — commit one planned local selection.",
		promptGuidelines: [
			"Only three non-empty strings are accepted: offer_id, choice, basis_id. Never pass key/role/source/claim/task/run/budget/parent/proof.",
			"offer_id/local_ref are opaque host values, NOT DP decision ids. A locally planned selection is not an answer and not an execution.",
			"Success returns planned/business_completed=false; it does not unblock a gate, write a sign-off, or record an execution.",
		],
		parameters: SUBMIT_DECISION_HANDOFF_PARAMETERS,
		executionMode: "sequential",
		execute: async (toolCallId, params) => {
			const base = (
				status: SubmitDecisionHandoffDetails["status"],
				reason: string,
				extra: Partial<SubmitDecisionHandoffDetails>,
			): {
				content: Array<{ type: "text"; text: string }>;
				details: SubmitDecisionHandoffDetails;
			} => {
				const details: SubmitDecisionHandoffDetails = {
					status,
					business_completed: false,
					selection_written: status === "planned",
					offer_id: typeof params.offer_id === "string" ? params.offer_id : "",
					choice: typeof params.choice === "string" ? params.choice : "",
					basis_id: typeof params.basis_id === "string" ? params.basis_id : "",
					gaps: [],
					reason,
					...extra,
				};
				return { content: [{ type: "text", text: JSON.stringify(details) }], details };
			};
			// Defensive strict parameter check (the tool schema also rejects extras).
			const keys = isRecord(params) ? Object.keys(params as Record<string, unknown>).sort() : [];
			const allowed = ["basis_id", "choice", "offer_id"];
			const strict =
				isRecord(params) &&
				typeof params.offer_id === "string" &&
				params.offer_id.trim() !== "" &&
				typeof params.choice === "string" &&
				params.choice.trim() !== "" &&
				typeof params.basis_id === "string" &&
				params.basis_id.trim() !== "" &&
				keys.length === 3 &&
				keys.every((key, index) => key === allowed[index]);
			if (!strict) return base("refused", "invalid-parameters", { gaps: ["offer_id", "choice", "basis_id"] });

			const offer = offersById.get(params.offer_id as string);
			if (offer === undefined) return base("refused", "unknown-or-unbound-offer", { gaps: ["offer_id"] });
			// An unknown-effect feedback is conservative uncertainty: never
			// replay/re-execute it into a committed planned selection. The offer
			// may still be PREPARED (unknown/malformed feedback is allowed), but a
			// commit of an unknown effect is refused, never silently rerun.
			if (offer.feedbackEffectUnknown)
				return base("refused", "effect-unknown-no-replay", { gaps: ["effect_unknown"], local_ref: offer.localRef });
			// R10: do NOT pre-empt the frozen store's semantic duplicate/conflict
			// classification with an offer-already-committed short circuit. A
			// re-submit of the SAME offer still goes to commitSelection, where the
			// store returns an idempotent `duplicate` (no second selection write)
			// for an identical selection and `conflict` (refusal) for a different
			// choice. Forbidding a second business execution never required
			// refusing one idempotent planned-fact read/submit. The `committed`
			// map is host bookkeeping only; the store remains the single writer.
			if (offer.runtimeAuthorization === undefined && offer.runtimeAuthorizationGaps !== undefined)
				return base("refused", "host-authorization-missing", {
					gaps:
						offer.runtimeAuthorizationGaps.length > 0 ? offer.runtimeAuthorizationGaps : ["host.authorization"],
					local_ref: offer.localRef,
				});
			const current = currentByMatter.get(offer.matterRefHash);
			if (current !== offer.offerId)
				return base("refused", "offer-superseded", { gaps: ["offer_id"], local_ref: offer.localRef });
			const drift = revalidateOffer(offer, params.choice as string, params.basis_id as string);
			if (drift.length > 0) return base("refused", "offer-drift", { gaps: drift, local_ref: offer.localRef });

			const materialFields = flattenMaterialFields(offer.material);
			const evidenceRefs = [
				...new Set((offer.preparation.basis_catalog as PreparedBasis[]).flatMap((item) => item.material_refs)),
			];
			if (evidenceRefs.length === 0) evidenceRefs.push(`${offer.dp}:material@${offer.materialDigest.slice(0, 16)}`);
			const selection: CommitSelectionRequest["selection"] = {
				matter_ref: offer.matterRefHash,
				matter_version: offer.matterVersion,
				material: {
					material_ref: `mat:${offer.materialDigest.slice(0, 16)}`,
					fields: materialFields,
					digest: offer.materialDigest,
					evidence_refs: evidenceRefs,
				},
				preparation: {
					prepared_at: offer.preparation.prepared_at,
					digest: offer.basisDigest,
					basis_catalog: offer.preparation.basis_catalog as PreparedBasis[],
				},
				candidates: { version: DECIDE_REGISTRY[offer.dp].questionsVersion, ids: offer.candidates },
				selected_action: params.choice as string,
				selected_basis_id: params.basis_id as string,
				created_at: new Date().toISOString(),
				...(offer.parent === undefined ? {} : { parent_decision_ref: offer.parent }),
			};
			const request: CommitSelectionRequest = {
				source: offer.identity.source,
				local_ref: offer.localRef,
				...(offer.identity.taskKey === undefined ? {} : { task_key: offer.identity.taskKey }),
				...(offer.identity.runId === undefined ? {} : { run_id: offer.identity.runId }),
				selection,
			};
			let result: LocalWriteResult;
			try {
				const runtime = config.hostRuntime?.toolRuntime();
				if (config.hostRuntime !== undefined) {
					if (runtime === undefined || runtime.key !== offer.identity.key)
						return base("refused", "host-runtime-unavailable", {
							gaps: ["hostRuntime"],
							local_ref: offer.localRef,
						});
					const committedResult = await runtime.commitSelection(request);
					if (committedResult.store_result === undefined)
						return base("refused", committedResult.code, {
							gaps: committedResult.gaps.length > 0 ? committedResult.gaps : [committedResult.code],
							local_ref: offer.localRef,
						});
					result = committedResult.store_result;
				} else {
					const store = storeFor(offer.identity.key);
					if (store === undefined)
						return base("refused", "host-runtime-unavailable", {
							gaps: ["hostRuntime"],
							local_ref: offer.localRef,
						});
					result = await store.commitSelection(request);
				}
			} catch {
				return base("refused", "store-threw", { gaps: ["commitSelection"], local_ref: offer.localRef });
			}
			const record = result.record;
			const kind = record !== undefined && isRecord(record) ? record.kind : undefined;
			const success =
				result.ok &&
				(result.code === "written" || result.code === "duplicate") &&
				result.host_source_verified === true &&
				kind === "local-selection";
			if (!success)
				return base("refused", `store-${result.code}`, {
					gaps: result.gaps.length ? result.gaps : [result.code],
					local_ref: offer.localRef,
					code: result.code,
				});
			committed.set(toolCallId, {
				toolCallId,
				offerId: offer.offerId,
				localRef: offer.localRef,
				choice: params.choice as string,
				basisId: params.basis_id as string,
				code: result.code === "duplicate" ? "duplicate" : "written",
				record: record as LocalSelectionRecordV1,
			});
			return base("planned", "local-selection-committed", {
				local_ref: offer.localRef,
				code: result.code,
				kind: "local-selection",
			});
		},
	});

	pi.on("before_agent_start", () => {
		const active = pi.getActiveTools();
		if (!active.includes(SUBMIT_DECISION_HANDOFF_TOOL)) pi.setActiveTools([...active, SUBMIT_DECISION_HANDOFF_TOOL]);
	});

	return {
		prepareOffer,
		readCommittedSelection,
		hostExpectedFor,
		currentOfferCertificateFor,
		runtimeHost: config.hostRuntime,
	};
}
