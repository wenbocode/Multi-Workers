/**
 * Host-only action provenance for the frozen LocalSelectionStore. This is NOT
 * a tool, a second writer, a business validator or a durable event ledger.
 * Register these closures in the host, never expose them to model params or
 * tool-result details. Losing the observations on restart fails closed.
 */
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import type {
	HostBinding,
	LocalExecutionRecordV1,
	LocalSelectionRecordV1,
	LocalSource,
	PmDisposition,
	ToolName,
} from "../shared/decision-handoff.ts";
import type {
	AppendExecutionRequest,
	CommitSelectionRequest,
	ExecutionProof,
	ExecutionVerificationRequest,
	LocalReadResult,
	LocalSelectionStore,
	LocalWriteResult,
	SaveDispositionRequest,
} from "../shared/local-selection-store.ts";

export interface RuntimeTargetEntry {
	path: string;
	state: "file" | "absent";
	sha256?: string;
}

/** Exact project-relative POSIX paths, not globs. All targets are hashed, not
 * just the first. Host policy must supply the COMPLETE affected target set. */
export interface RuntimeTargetAuthorization {
	run_id: string;
	targets: readonly string[];
	write_face: readonly string[];
}

export interface RuntimeToolCall {
	source: LocalSource;
	local_ref: string;
	toolCallId: string;
	tool: ToolName;
}

export interface RuntimeToolResult {
	toolCallId: string;
	local_ref: string;
	run_id: string;
	executor: string;
	result_ref: string;
	isError: boolean;
	/** Host event completion, not an assessment of business correctness. */
	completion: "complete" | "unknown";
}

export interface RuntimeExecutionConfig {
	store: LocalSelectionStore;
	project_root: string;
	/** Current identity from the host's authoritative binding reader. */
	readBinding(): HostBinding | undefined;
	/** Live registered host policy; veto expired authority/budget before returning
	 * the complete target set. NEVER derive authority from params/details. */
	readAuthorization(
		selection: Readonly<LocalSelectionRecordV1>,
		call: Readonly<RuntimeToolCall>,
	): RuntimeTargetAuthorization | undefined;
	/** Host-built disposition from real handling facts, not a model payload.
	 * Only observed collect-evidence/reconcile are supported here; final QG,
	 * gate, sign and business correctness remain with their own consumers. */
	readDisposition?(
		context: Readonly<{
			selection: LocalSelectionRecordV1;
			call: RuntimeToolCall;
			proof: ExecutionProof;
			disposition_ref: string;
		}>,
	): PmDisposition | undefined;
	clock?: () => number;
}

export type RuntimeExecutionCode =
	| "selection-bound"
	| "call-observed"
	| "result-observed"
	| "duplicate"
	| "selection-unproven"
	| "binding-drift"
	| "authorization-gap"
	| "target-invalid"
	| "target-drift"
	| "unknown-call"
	| "out-of-order"
	| "call-conflict"
	| "result-conflict"
	| "result-missing"
	| "result-error"
	| "result-unknown"
	| "result-mismatch"
	| "store-result"
	| "submission-in-flight"
	| "reconciliation-required"
	| "disposition-unproven";

export interface RuntimeExecutionResult {
	code: RuntimeExecutionCode;
	effect_state: "known" | "unknown";
	gaps: string[];
	/** Always false: this API can only observe/read or write frozen records. */
	replay_allowed: false;
	store_result?: LocalWriteResult;
	recovery?: RuntimeExecutionRecovery;
}

export interface RuntimeExecutionRecovery {
	selection: LocalReadResult<LocalSelectionRecordV1>;
	execution: LocalReadResult<LocalExecutionRecordV1>;
	disposition?: LocalReadResult<PmDisposition>;
	/** A read-only CURRENT snapshot; not by itself evidence of execution. */
	current_targets?: readonly RuntimeTargetEntry[];
	gaps: string[];
}

interface FileIdentity {
	dev: number;
	ino: number;
}
interface TargetSnapshot {
	manifest: RuntimeTargetEntry[];
	digest: string;
	ancestors: Map<string, FileIdentity>;
	files: Map<string, FileIdentity>;
}
interface ActionObservation {
	selection: LocalSelectionRecordV1;
	call: RuntimeToolCall;
	authorization: RuntimeTargetAuthorization;
	before: TargetSnapshot;
	after?: TargetSnapshot;
	result?: RuntimeToolResult;
	gap?: RuntimeExecutionCode;
	write_failed: boolean;
	recorded: boolean;
	submitting: boolean;
}

const BINDING_FIELDS = ["role", "owner", "claim_id", "key", "task_key", "run_id", "binding_version"] as const;

function bindingMatches(a: HostBinding, b: HostBinding | undefined): boolean {
	return (
		b !== undefined &&
		!!b.key &&
		!!b.owner &&
		b.owner === b.claim_id &&
		BINDING_FIELDS.every((field) => a[field] === b[field])
	);
}

function sameIdentity(a: FileIdentity, b: FileIdentity): boolean {
	return a.dev === b.dev && a.ino === b.ino;
}

function pathKey(value: string): string {
	return process.platform === "win32" ? value.toLowerCase() : value;
}

function canonicalPaths(paths: readonly string[]): string[] {
	if (!paths.length) throw new Error("host target/write-face set is empty");
	const seen = new Set<string>();
	for (const name of paths) {
		if (
			typeof name !== "string" ||
			!name ||
			path.posix.normalize(name) !== name ||
			path.posix.isAbsolute(name) ||
			name
				.split("/")
				.some(
					(part) =>
						!part ||
						part === "." ||
						part === ".." ||
						/[\\:*?"<>|\u0000-\u001f]|[. ]$/.test(part) ||
						/^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)/i.test(part),
				)
		)
			throw new Error("target is not a canonical project-relative path");
		const key = pathKey(name);
		if (seen.has(key)) throw new Error("duplicate/aliased host target");
		seen.add(key);
	}
	return [...paths].sort();
}

function authorizationSnapshot(value: RuntimeTargetAuthorization | undefined): RuntimeTargetAuthorization {
	if (!value || typeof value.run_id !== "string" || !value.run_id.trim()) throw new Error("host run missing");
	const targets = canonicalPaths(value.targets);
	const writeFace = canonicalPaths(value.write_face);
	const face = new Set(writeFace.map(pathKey));
	if (targets.some((target) => !face.has(pathKey(target)))) throw new Error("target outside host write face");
	return { run_id: value.run_id, targets, write_face: writeFace };
}

/** Collision-free association; no call-id regex is an execution proof. */
export function runtimeExecutionExecutor(runId: string, toolCallId: string): string {
	return JSON.stringify([runId, toolCallId]);
}

function outcome(code: RuntimeExecutionCode, gap?: string): RuntimeExecutionResult {
	return { code, effect_state: "unknown", gaps: gap ? [gap] : [], replay_allowed: false };
}

/** The controller captures actual observations in its private closure. A
 * shape-only store read, old action ref, or file bytes cannot populate it. */
export class RuntimeExecutionController {
	private readonly config: RuntimeExecutionConfig;
	private readonly root: string;
	private readonly selections = new Map<string, LocalSelectionRecordV1>();
	private readonly actions = new Map<string, ActionObservation>();
	private readonly selectionCalls = new Map<string, string>();
	private readonly orphanResults = new Set<string>();
	private readonly resultCalls = new Map<string, string>();
	private readonly failedDispositions = new Set<string>();
	private readonly pendingDispositions = new Set<string>();

	constructor(config: RuntimeExecutionConfig) {
		this.config = { ...config };
		this.root = path.resolve(config.project_root);
	}

	/** Calls the SAME injected store, retaining only its successful verified
	 * result. Unknown existing commits are recovery clues, NOT fresh permission
	 * to execute. I must route the original commit through this wrapper; only
	 * duplicates already observed by THIS controller can be rebound. */
	async commitSelection(request: CommitSelectionRequest): Promise<RuntimeExecutionResult> {
		const result = await this.config.store.commitSelection(request);
		const record = result.record;
		if (
			!result.ok ||
			!result.host_source_verified ||
			(result.code !== "written" && result.code !== "duplicate") ||
			!record ||
			!("kind" in record) ||
			record.kind !== "local-selection" ||
			!bindingMatches(record.host_binding, this.currentBinding())
		)
			return { ...outcome("selection-unproven", "current verified store selection required"), store_result: result };
		const key = this.selectionKey(record.source, record.local_ref);
		const old = this.selections.get(key);
		if (result.code === "duplicate" && !old) {
			return {
				...outcome(
					"reconciliation-required",
					"existing selection has no live commit observation; do not replay on restart",
				),
				store_result: result,
			};
		}
		if (old && !bindingMatches(old.host_binding, record.host_binding)) {
			return { ...outcome("binding-drift", "old selection observations cannot be rebound"), store_result: result };
		}
		this.selections.set(key, structuredClone(record));
		return { ...outcome("selection-bound"), store_result: result };
	}

	/** Synchronous: run at the real tool_call boundary BEFORE executing tool.
	 * A refusal must veto that call in I; this module never executes it. */
	observeToolCall(event: RuntimeToolCall): RuntimeExecutionResult {
		const previous = this.actions.get(event.toolCallId);
		if (previous) {
			return JSON.stringify(previous.call) === JSON.stringify(event)
				? outcome("duplicate", "call already observed; do not execute again")
				: outcome("call-conflict", "toolCallId already belongs to another action");
		}
		if (!event.toolCallId?.trim()) return outcome("unknown-call", "real toolCallId missing");
		if (this.orphanResults.has(event.toolCallId))
			return outcome("out-of-order", "result preceded call; cannot repair by replay");
		const key = this.selectionKey(event.source, event.local_ref);
		const selection = this.selections.get(key);
		if (!selection) return outcome("selection-unproven", "no verified committed selection in this host lifetime");
		if (this.selectionCalls.has(key))
			return outcome("call-conflict", "one frozen execution slot per local_ref; no repeated business action");
		if (!this.selectionCurrent(selection))
			return outcome("binding-drift", "current binding or committed selection changed before action");
		const existing = this.config.store.readExecution({
			source: selection.source,
			ref: selection.local_ref,
			task_key: selection.host_binding.task_key,
		});
		if (existing.status !== "absent") {
			return outcome(
				"reconciliation-required",
				"existing execution/unknown/corrupt record is read-only; never repeat the tool",
			);
		}
		let authorization: RuntimeTargetAuthorization;
		try {
			authorization = authorizationSnapshot(this.config.readAuthorization(structuredClone(selection), { ...event }));
			if (event.source === "worker-local" && authorization.run_id !== selection.host_binding.run_id) {
				return outcome("authorization-gap", "authorization run differs from worker binding");
			}
		} catch {
			return outcome("authorization-gap", "missing/invalid host target set, write face or run");
		}
		try {
			const before = this.snapshot(authorization.targets, true);
			this.actions.set(event.toolCallId, {
				selection: structuredClone(selection),
				call: { ...event },
				authorization,
				before,
				write_failed: false,
				recorded: false,
				submitting: false,
			});
			this.selectionCalls.set(key, event.toolCallId);
			return outcome("call-observed");
		} catch {
			return outcome("target-invalid", "target path unreadable, redirected, linked or outside project");
		}
	}

	/** Capture immediately on the REAL result event, including error results.
	 * Result refs/executor come from host event identity, never result.details. */
	observeToolResult(event: RuntimeToolResult): RuntimeExecutionResult {
		const action = this.actions.get(event.toolCallId);
		if (!action) {
			this.orphanResults.add(event.toolCallId);
			return outcome("unknown-call", "result has no observed call; read-only reconciliation only");
		}
		if (action.result) {
			if (JSON.stringify(action.result) === JSON.stringify(event))
				return outcome("duplicate", "result already observed");
			action.gap = "result-conflict";
			return outcome("result-conflict", "conflicting repeated result; original observation retained");
		}
		action.result = { ...event };
		const previousResultCall = this.resultCalls.get(event.result_ref);
		if (event.result_ref?.trim() && previousResultCall === undefined) {
			this.resultCalls.set(event.result_ref, event.toolCallId);
		}
		if (
			event.local_ref !== action.selection.local_ref ||
			event.run_id !== action.authorization.run_id ||
			event.executor !== runtimeExecutionExecutor(action.authorization.run_id, action.call.toolCallId) ||
			!event.result_ref?.trim() ||
			(previousResultCall !== undefined && previousResultCall !== event.toolCallId) ||
			typeof event.isError !== "boolean"
		)
			action.gap = "result-mismatch";
		else if (event.isError) action.gap = "result-error";
		else if (event.completion !== "complete") action.gap = "result-unknown";
		else if (!this.current(action)) action.gap = "binding-drift";
		try {
			action.after = this.snapshot(action.authorization.targets, false);
			if (!this.ancestorsMatch(action.before, action.after)) action.gap = "target-drift";
		} catch {
			action.gap ??= "target-invalid";
		}
		return action.gap
			? outcome(action.gap, "observed action/result is unproven; never replay the business tool")
			: outcome("result-observed");
	}

	/** Independent byte re-read, suitable as LocalSelectionHostAdapter.verifyExecution.
	 * A current matching observation is mandatory even when bytes already exist. */
	async verifyExecution(request: ExecutionVerificationRequest): Promise<ExecutionProof | undefined> {
		const action = this.actions.get(request.action_ref);
		if (!action || !action.result || action.gap || !action.after || !this.current(action)) return undefined;
		const { selection, result, after } = action;
		if (
			request.key !== selection.host_binding.key ||
			request.source !== selection.source ||
			request.local_ref !== selection.local_ref ||
			request.result_ref !== result.result_ref ||
			request.executor !== result.executor ||
			!bindingMatches(selection.host_binding, request.binding) ||
			request.observed_effect !== this.observedEffect(action) ||
			(request.expected_target_digest !== undefined && request.expected_target_digest !== after.digest)
		)
			return undefined;
		try {
			const independent = this.snapshot(action.authorization.targets, false);
			if (
				independent.digest !== after.digest ||
				!this.ancestorsMatch(after, independent) ||
				[...after.files].some(
					([name, identity]) => !sameIdentity(identity, independent.files.get(name) ?? { dev: -1, ino: -1 }),
				)
			) {
				action.gap = "target-drift";
				return undefined;
			}
		} catch {
			action.gap = "target-invalid";
			return undefined;
		}
		return {
			action_ref: action.call.toolCallId,
			result_ref: result.result_ref,
			verifier_ref: "target-digest-v1@runtime-execution-1",
			target_digest: after.digest,
			observed_effect: this.observedEffect(action),
			effect_state: "known",
			local_ref: selection.local_ref,
			executor: result.executor,
		};
	}

	/** Record only; does NOT execute or repeat a tool. Failed attempts latch to
	 * read-only recovery. A success can be rechecked by the store as duplicate. */
	async appendExecution(toolCallId: string): Promise<RuntimeExecutionResult> {
		const action = this.actions.get(toolCallId);
		if (!action) return outcome("unknown-call", "no host observation; no execution submitted");
		if (action.submitting)
			return {
				...outcome("submission-in-flight", "record submission pending"),
				recovery: this.reconcile(toolCallId),
			};
		if (action.write_failed)
			return {
				...outcome("reconciliation-required", "prior store refusal/write failure; no automatic retry"),
				recovery: this.reconcile(toolCallId),
			};
		if (!action.result || action.gap || !action.after || !this.current(action)) {
			return {
				...outcome(
					action.gap ?? (action.result ? "binding-drift" : "result-missing"),
					"no proven completion; read only, never replay",
				),
				recovery: this.reconcile(toolCallId),
			};
		}
		const now = (this.config.clock ?? Date.now)();
		if (!Number.isFinite(now) || Math.abs(now) > 8.64e15) {
			return {
				...outcome("reconciliation-required", "invalid host record timestamp; no submission or business retry"),
				recovery: this.reconcile(toolCallId),
			};
		}
		const request: AppendExecutionRequest = {
			source: action.selection.source,
			local_ref: action.selection.local_ref,
			task_key: action.selection.host_binding.task_key,
			run_id: action.selection.host_binding.run_id,
			action_ref: toolCallId,
			result_ref: action.result.result_ref,
			executor: action.result.executor,
			observed_effect: this.observedEffect(action),
			created_at: new Date(now).toISOString(),
		};
		action.submitting = true;
		try {
			const result = await this.config.store.appendExecution(request);
			action.write_failed = !result.ok;
			action.recorded =
				result.ok &&
				result.host_source_verified &&
				result.record !== undefined &&
				"kind" in result.record &&
				result.record.kind === "local-execution";
			return {
				...outcome("store-result"),
				effect_state:
					action.recorded && result.record && "effect_state" in result.record
						? result.record.effect_state
						: "unknown",
				store_result: result,
				recovery: this.reconcile(toolCallId),
			};
		} catch {
			action.write_failed = true;
			return {
				...outcome(
					"reconciliation-required",
					"execution store threw; effect remains unknown, read only before any repair",
				),
				recovery: this.reconcile(toolCallId),
			};
		} finally {
			action.submitting = false;
		}
	}

	/** Save an observed evidence/reconciliation disposition through the SAME
	 * store, only after its execution record and independent proof agree. */
	async saveDisposition(toolCallId: string, dispositionRef: string): Promise<RuntimeExecutionResult> {
		const action = this.actions.get(toolCallId);
		const attemptKey = JSON.stringify([toolCallId, dispositionRef]);
		if (action && (this.failedDispositions.has(attemptKey) || this.pendingDispositions.has(attemptKey))) {
			const recovery = this.reconcile(toolCallId);
			recovery.disposition = this.config.store.readDisposition({
				source: action.selection.source,
				ref: dispositionRef,
				task_key: action.selection.host_binding.task_key,
			});
			return {
				...outcome(
					this.failedDispositions.has(attemptKey) ? "reconciliation-required" : "submission-in-flight",
					"disposition attempt is unresolved; read only, never replay",
				),
				recovery,
			};
		}
		if (
			!action?.result ||
			!action.after ||
			action.gap ||
			action.write_failed ||
			!action.recorded ||
			!this.current(action)
		) {
			return outcome("disposition-unproven", "real current observed execution required");
		}
		const proof = await this.verifyExecution({
			key: action.selection.host_binding.key ?? "",
			source: action.selection.source,
			local_ref: action.selection.local_ref,
			action_ref: toolCallId,
			result_ref: action.result.result_ref,
			executor: action.result.executor,
			observed_effect: this.observedEffect(action),
			binding: action.selection.host_binding,
		});
		const recovered = this.reconcile(toolCallId);
		const execution = recovered.execution.record;
		if (
			!proof ||
			!execution ||
			execution.effect_state !== "known" ||
			execution.action_ref !== proof.action_ref ||
			execution.result_ref !== proof.result_ref ||
			execution.executor !== proof.executor ||
			execution.target_digest !== proof.target_digest ||
			execution.observed_effect !== proof.observed_effect ||
			execution.verified_by !== proof.verifier_ref ||
			!bindingMatches(execution.host_binding, this.currentBinding())
		) {
			return {
				...outcome("disposition-unproven", "matching persisted execution and current byte proof required"),
				recovery: recovered,
			};
		}
		let disposition: PmDisposition | undefined;
		try {
			disposition = this.config.readDisposition?.({
				selection: structuredClone(action.selection),
				call: { ...action.call },
				proof: { ...proof },
				disposition_ref: dispositionRef,
			});
		} catch {
			return outcome("disposition-unproven", "host disposition facts unavailable");
		}
		if (
			!disposition ||
			disposition.disposition_ref !== dispositionRef ||
			!bindingMatches(action.selection.host_binding, disposition.binding) ||
			disposition.owner !== action.selection.host_binding.owner ||
			disposition.matter_ref !== action.selection.matter_ref ||
			disposition.budget_ref !== action.selection.budget_ref ||
			disposition.status !== "observed" ||
			!["collect-evidence", "reconcile"].includes(disposition.kind) ||
			disposition.planned_action.tool !== action.call.tool ||
			!disposition.basis_refs?.includes(toolCallId) ||
			!disposition.basis_refs.includes(action.result.result_ref)
		) {
			return outcome(
				"disposition-unproven",
				"host disposition must match observed tool/result, binding, matter and budget; no gate/QG/sign",
			);
		}
		const request: SaveDispositionRequest = {
			source: action.selection.source,
			disposition_ref: dispositionRef,
			task_key: action.selection.host_binding.task_key,
			run_id: action.selection.host_binding.run_id,
			disposition: structuredClone(disposition),
		};
		if (this.pendingDispositions.has(attemptKey) || this.failedDispositions.has(attemptKey)) {
			return {
				...outcome(
					this.failedDispositions.has(attemptKey) ? "reconciliation-required" : "submission-in-flight",
					"disposition attempt began during verification; read only",
				),
				recovery: this.reconcile(toolCallId),
			};
		}
		this.pendingDispositions.add(attemptKey);
		try {
			const result = await this.config.store.saveDisposition(request);
			if (!result.ok) this.failedDispositions.add(attemptKey);
			const recovery = this.reconcile(toolCallId);
			recovery.disposition = this.config.store.readDisposition({
				source: action.selection.source,
				ref: dispositionRef,
				task_key: action.selection.host_binding.task_key,
			});
			return { ...outcome("store-result"), store_result: result, recovery };
		} catch {
			this.failedDispositions.add(attemptKey);
			return {
				...outcome("reconciliation-required", "disposition store threw; not known-unexecuted"),
				recovery: this.reconcile(toolCallId),
			};
		} finally {
			this.pendingDispositions.delete(attemptKey);
		}
	}

	/** No business callbacks, writes, retries or reconstructed action history. */
	reconcile(toolCallId: string): RuntimeExecutionRecovery {
		const action = this.actions.get(toolCallId);
		if (!action) throw new Error("cannot reconcile an unbound action; use store shape-only reads with its real ref");
		const request = {
			source: action.selection.source,
			ref: action.selection.local_ref,
			task_key: action.selection.host_binding.task_key,
		};
		const recovery: RuntimeExecutionRecovery = {
			selection: this.config.store.readSelection(request),
			execution: this.config.store.readExecution(request),
			gaps: [],
		};
		try {
			recovery.current_targets = this.snapshot(action.authorization.targets, true).manifest;
		} catch {
			recovery.gaps.push("current target set unreadable/redirected; bytes are not execution proof");
		}
		if (action.gap) recovery.gaps.push(action.gap);
		return recovery;
	}

	private currentBinding(): HostBinding | undefined {
		try {
			return this.config.readBinding();
		} catch {
			return undefined;
		}
	}

	private selectionCurrent(selection: LocalSelectionRecordV1): boolean {
		if (!bindingMatches(selection.host_binding, this.currentBinding())) return false;
		const persisted = this.config.store.readSelection({
			source: selection.source,
			ref: selection.local_ref,
			task_key: selection.host_binding.task_key,
		}).record;
		return (
			persisted !== undefined &&
			bindingMatches(selection.host_binding, persisted.host_binding) &&
			(
				[
					"local_ref",
					"source",
					"matter_ref",
					"matter_version",
					"material_digest",
					"basis_digest",
					"selected_action",
					"selected_basis_id",
					"budget_ref",
					"feedback_ref",
					"result_consumer",
				] as const
			).every((field) => persisted[field] === selection[field]) &&
			persisted.parent_decision_ref?.decision_id === selection.parent_decision_ref?.decision_id
		);
	}

	private current(action: ActionObservation): boolean {
		if (!this.selectionCurrent(action.selection)) return false;
		try {
			const authorization = authorizationSnapshot(
				this.config.readAuthorization(structuredClone(action.selection), { ...action.call }),
			);
			return JSON.stringify(authorization) === JSON.stringify(action.authorization);
		} catch {
			return false;
		}
	}

	private selectionKey(source: LocalSource, localRef: string): string {
		return JSON.stringify([source, localRef]);
	}

	private observedEffect(action: ActionObservation): string {
		return `byte-manifest:${action.before.digest}->${action.after?.digest ?? "unknown"};business-correctness=unverified`;
	}

	private ancestorsMatch(a: TargetSnapshot, b: TargetSnapshot): boolean {
		return [...a.ancestors].every(([name, identity]) => {
			const current = b.ancestors.get(name);
			return current !== undefined && sameIdentity(identity, current);
		});
	}

	/** Reject links/junctions at EVERY component, including project ancestors.
	 * Descriptor + before/after lstat/realpath checks reject observable rename
	 * races. Node stdlib cannot promise atomic openat traversal against a hostile
	 * concurrent filesystem mutator; this is not an OS sandbox. */
	private snapshot(targets: readonly string[], allowAbsent: boolean): TargetSnapshot {
		const ancestors = new Map<string, FileIdentity>();
		const files = new Map<string, FileIdentity>();
		const manifest: RuntimeTargetEntry[] = [];
		const checkDirectories = (directory: string): boolean => {
			const absolute = path.resolve(directory);
			const parsed = path.parse(absolute);
			let cursor = parsed.root;
			for (const segment of ["", ...absolute.slice(parsed.root.length).split(path.sep).filter(Boolean)]) {
				cursor = path.join(cursor, segment);
				const stat = fs.lstatSync(cursor, { throwIfNoEntry: false });
				if (!stat) return false;
				if (!stat.isDirectory() || stat.isSymbolicLink() || pathKey(fs.realpathSync(cursor)) !== pathKey(cursor))
					throw new Error("directory redirect");
				const key = pathKey(cursor);
				const previous = ancestors.get(key);
				if (previous && !sameIdentity(previous, stat)) throw new Error("directory changed while reading manifest");
				ancestors.set(key, { dev: stat.dev, ino: stat.ino });
			}
			return true;
		};
		if (!checkDirectories(this.root)) throw new Error("project root missing");
		for (const name of canonicalPaths(targets)) {
			const absolute = path.resolve(this.root, ...name.split("/"));
			const relative = path.relative(this.root, absolute);
			if (!relative || relative.startsWith(`..${path.sep}`) || relative === ".." || path.isAbsolute(relative))
				throw new Error("target escape");
			const parentExists = checkDirectories(path.dirname(absolute));
			const before = parentExists ? fs.lstatSync(absolute, { throwIfNoEntry: false }) : undefined;
			if (!before) {
				if (!allowAbsent) throw new Error("result target missing; deletion proof unsupported");
				manifest.push({ path: name, state: "absent" });
				continue;
			}
			if (
				!before.isFile() ||
				before.isSymbolicLink() ||
				before.nlink !== 1 ||
				pathKey(fs.realpathSync(absolute)) !== pathKey(absolute)
			)
				throw new Error("file redirect/hardlink");
			const fd = fs.openSync(absolute, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
			try {
				const opened = fs.fstatSync(fd);
				if (!sameIdentity(before, opened) || !opened.isFile() || opened.nlink !== 1) throw new Error("open race");
				const bytes = fs.readFileSync(fd);
				const after = fs.fstatSync(fd);
				const current = fs.lstatSync(absolute);
				if (
					!sameIdentity(opened, after) ||
					!sameIdentity(after, current) ||
					current.isSymbolicLink() ||
					!current.isFile() ||
					current.nlink !== 1 ||
					after.size !== current.size ||
					after.mtimeMs !== current.mtimeMs ||
					after.ctimeMs !== current.ctimeMs ||
					after.nlink !== 1 ||
					before.size !== after.size ||
					before.mtimeMs !== after.mtimeMs ||
					before.ctimeMs !== after.ctimeMs ||
					!checkDirectories(path.dirname(absolute)) ||
					pathKey(fs.realpathSync(absolute)) !== pathKey(absolute)
				)
					throw new Error("read race");
				manifest.push({
					path: name,
					state: "file",
					sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
				});
				files.set(name, { dev: after.dev, ino: after.ino });
			} finally {
				fs.closeSync(fd);
			}
		}
		// Canonical JSON of the ENTIRE sorted manifest, including absent baselines.
		return {
			manifest,
			digest: `sha256:${crypto.createHash("sha256").update(JSON.stringify(manifest)).digest("hex")}`,
			ancestors,
			files,
		};
	}
}
