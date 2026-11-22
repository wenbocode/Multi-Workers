/**
 * T02 — dedicated tests for `shared/local-selection-store.ts`.
 *
 * FIXTURE BOUNDARY (read before interpreting results):
 *  - Every `LocalSelectionHostAdapter` here is an L1 HOST INJECTION fixture over
 *    a real temp directory. It is NOT production host wiring (that belongs to
 *    T04..T15) and these assertions are NOT product L2 / VC PASS. The store
 *    fails closed when the fixture is omitted; it never treats a model string,
 *    a boolean or "file exists" as provenance.
 *  - Real disk, real O_EXCL locks, real tmp/fsync/rename are used. The ONLY
 *    injected faults are the `atomic_write` seam (deterministic write/rename
 *    failure) and the trusted-host adapter facts — never a full mock of the FS.
 *  - Physical naming and record shapes are shared with the frozen schema v1
 *    contract (`decision-handoff.ts`) and T03; this test never forks them.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
	parseLocalExecutionRecord,
	parseLocalSelectionRecord,
	SCHEMA_V1,
} from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import {
	type AppendExecutionRequest,
	atomicWriteJson,
	type CommitSelectionRequest,
	DISPOSITION_FILE_SUFFIX,
	EXECUTION_FILE_SUFFIX,
	type ExecutionProof,
	encodeLocalRef,
	type LocalSelectionHostAdapter,
	LocalSelectionStore,
	type LocalStoreConfig,
	MAX_LOCAL_REF_BYTES,
	SELECTION_FILE_SUFFIX,
	SHARED_INTENT_LOCK_BASENAME,
	sharedIntentLockPath,
	storedRecordPath,
	type TrustedHostContext,
} from "../../src/extensions/agent-team-loop/shared/local-selection-store.ts";

// ── Fixed fixtures ─────────────────────────────────────────────────────────

const KEY = "mw-pm-dp-continuity";
const CLAIM = "WENBOZHOU-PC5:13148";
// A legitimate fixture must be CURRENT: `NOW` is the real host clock at module
// load and `DEADLINE` is a real future deadline. A past snapshot/deadline may
// never be used to obtain authorization (TS02). The store defaults to Date.now;
// the `clock` config seam is injected only for deterministic boundaries.
const NOW = new Date().toISOString();
const DEADLINE = new Date(Date.now() + 30 * 60 * 1000).toISOString();
const MATTER = "matter:T01";
const LOCAL_REF = "local:T01:1";
const WORKER_TASK = "pm-dp-r2-local-store";
const WORKER_RUN = "run-2026-11-12-a";

let tmp: string;
let root: string;

beforeEach(() => {
	tmp = fs.mkdtempSync(path.join(os.tmpdir(), "t02-store-"));
	root = path.join(tmp, ".agenticdoc");
	fs.mkdirSync(root, { recursive: true });
	fs.mkdirSync(path.join(root, "..", ".mw"), { recursive: true });
	writeIndex(defaultIndex());
});

afterEach(() => {
	fs.rmSync(tmp, { recursive: true, force: true });
});

interface IndexRow {
	key: string;
	status: string;
	phase: string;
	claimId: string;
	updated: string;
}

function defaultIndex(): IndexRow[] {
	return [{ key: KEY, status: "active", phase: "EXECUTE", claimId: CLAIM, updated: "2026-11-12T12:00:00Z" }];
}

function writeIndex(rows: IndexRow[]): void {
	const header =
		"# Index Parallel\n| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |\n| --- | --- | --- | --- | --- | --- | --- |\n";
	const lines = rows.map(
		(row) => `| ${row.key} | ${row.status} | ${row.phase} | ${row.claimId} |  |  | ${row.updated} |`,
	);
	fs.writeFileSync(path.join(root, "_index.parallel"), `${header}${lines.join("\n")}\n`, "utf8");
	// _index.md is only a projection; the store must never consult it as authority.
	fs.writeFileSync(path.join(root, "_index.md"), `# AgenticTask Index\n\nactive_keys: []\n`, "utf8");
}

function trustedContext(overrides: Partial<TrustedHostContext> = {}): TrustedHostContext {
	return {
		self_claim_id: CLAIM,
		binding_version: "v3",
		role: "pm",
		observed_at: NOW,
		expected: {
			matter_ref: MATTER,
			matter_version: "mv1",
			material_digest: "sha256:material",
			basis_digest: "sha256:basis",
			budget_ref: "budget:T01",
		},
		budget: {
			schema_version: 1,
			budget_ref: "budget:T01",
			matter_ref: MATTER,
			deadline: DEADLINE,
			max_steps: 3,
			no_progress_limit: 2,
			remaining_cost: 5,
			steps_consumed: 1,
			cost_consumed: 1,
			no_progress_count: 0,
			source_refs: ["tasks/T02:timeout=55", "run.json:remaining"],
		},
		budget_preflight: {
			granted: true,
			reserved_steps: 1,
			reserved_cost: 1,
			remaining_after_steps: 2,
			remaining_after_cost: 4,
			reason: "granted",
		},
		...overrides,
	};
}

function executionProof(overrides: Partial<ExecutionProof> = {}): ExecutionProof {
	return {
		action_ref: "tool_call:read:7",
		result_ref: "tool_result:read:7",
		verifier_ref: "target-verifier:1",
		target_digest: "sha256:target",
		observed_effect: "two reads recorded",
		effect_state: "known",
		local_ref: LOCAL_REF,
		executor: "pm-orchestrator",
		...overrides,
	};
}

interface AdapterOptions {
	ctx?: TrustedHostContext | undefined;
	/** Return undefined from the verifier (no proof). */
	noProof?: boolean;
	/** Omit the verifier method entirely. */
	noVerifier?: boolean;
	proof?: ExecutionProof;
}

/** L1 HOST INJECTION fixture — not production host wiring, not a VC. */
function hostAdapter(opts: AdapterOptions = {}): LocalSelectionHostAdapter {
	const adapter: LocalSelectionHostAdapter = {
		readTrustedContext: async () => (opts.ctx === undefined ? trustedContext() : opts.ctx),
	};
	if (!opts.noVerifier) {
		adapter.verifyExecution = async () => (opts.noProof ? undefined : (opts.proof ?? executionProof()));
	}
	return adapter;
}

function selectionFields(overrides: Record<string, unknown> = {}): CommitSelectionRequest["selection"] {
	return {
		matter_ref: MATTER,
		matter_version: "mv1",
		material: {
			material_ref: "mat:1",
			fields: { task_goal: "g", task_requirements: "r", task_deliverables: "d" },
			digest: "sha256:material",
			evidence_refs: ["card:1"],
		},
		preparation: {
			prepared_at: NOW,
			digest: "sha256:basis",
			basis_catalog: [
				{ id: "b1", text: "basis one", material_refs: ["task_goal"], applies_to: ["continue"] },
				{ id: "b2", text: "basis two", material_refs: ["task_goal"], applies_to: ["narrow"] },
			],
		},
		candidates: { version: "v1", ids: ["continue", "narrow"] },
		selected_action: "continue",
		selected_basis_id: "b1",
		created_at: NOW,
		...overrides,
	} as CommitSelectionRequest["selection"];
}

function commitRequest(overrides: Partial<CommitSelectionRequest> = {}): CommitSelectionRequest {
	return { source: "pm", local_ref: LOCAL_REF, selection: selectionFields(), ...overrides };
}

function execRequest(overrides: Partial<AppendExecutionRequest> = {}): AppendExecutionRequest {
	return {
		source: "pm",
		local_ref: LOCAL_REF,
		action_ref: "tool_call:read:7",
		result_ref: "tool_result:read:7",
		executor: "pm-orchestrator",
		observed_effect: "two reads recorded",
		created_at: "2026-11-12T12:45:00+08:00",
		...overrides,
	};
}

function dispositionValue(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		schema_version: 1,
		disposition_ref: "disp:T01:1",
		feedback_ref: "fb:1",
		matter_ref: MATTER,
		kind: "collect-evidence",
		owner: CLAIM,
		binding: {
			role: "pm",
			owner: CLAIM,
			claim_id: CLAIM,
			key: KEY,
			binding_version: "v3",
			observed_at: NOW,
		},
		goal_ref: "goal:1",
		gap_refs: ["gap:1"],
		planned_action: { tool: "read", scope_ref: "scope:1", read_only: true },
		expected_result: "read the card",
		result_consumer: "pm-orchestrator:ack",
		budget_ref: "budget:T01",
		status: "planned",
		...overrides,
	};
}

function makeStore(config: Partial<LocalStoreConfig> = {}): LocalSelectionStore {
	return new LocalSelectionStore({
		agenticdoc_root: root,
		key: KEY,
		host_adapter: hostAdapter(),
		lock_options: { retries: 14, baseDelayMs: 3 },
		...config,
	});
}

function selectionFile(ref = LOCAL_REF): string {
	return storedRecordPath(root, KEY, "pm", undefined, ref, SELECTION_FILE_SUFFIX);
}

function executionFile(ref = LOCAL_REF): string {
	return storedRecordPath(root, KEY, "pm", undefined, ref, EXECUTION_FILE_SUFFIX);
}

async function commitOk(store: LocalSelectionStore, req = commitRequest()): Promise<void> {
	const result = await store.commitSelection(req);
	expect(result.code, result.reason).toBe("written");
}

// ── Physical naming / ref encoding ─────────────────────────────────────────

describe("frozen physical naming (freeze §Common physical naming)", () => {
	it("base64url encodes the FULL UTF-8 ref with no padding and no Windows colon", () => {
		expect(encodeLocalRef("local:T01:1")).toBe("bG9jYWw6VDAxOjE");
		expect(encodeLocalRef("local:T01:1")).not.toContain(":");
		expect(encodeLocalRef("local:T01:1")).not.toContain("=");
		expect(Buffer.from(encodeLocalRef("a/b\\c:d") as string, "base64url").toString("utf8")).toBe("a/b\\c:d");
	});

	it("rejects blank, NUL, overlong and non-canonical refs without truncation", () => {
		expect(encodeLocalRef("")).toBeUndefined();
		expect(encodeLocalRef("a\u0000b")).toBeUndefined();
		expect(encodeLocalRef("x".repeat(MAX_LOCAL_REF_BYTES + 1))).toBeUndefined();
		expect(encodeLocalRef(123 as unknown)).toBeUndefined();
		// A truncated ref would collide; overlong refs are a concrete failure instead.
		expect(encodeLocalRef("x".repeat(40))).not.toBe(encodeLocalRef("x".repeat(41)));
	});

	it("derives distinct selection/execution/disposition paths and the shared intent lock", () => {
		expect(selectionFile()).not.toBe(executionFile());
		expect(selectionFile()).toMatch(/decision-handoffs/);
		expect(executionFile()).toMatch(/\.execution\.json$/);
		expect(sharedIntentLockPath(root)).toBe(path.join(root, "..", ".mw", SHARED_INTENT_LOCK_BASENAME));
		expect(storedRecordPath(root, KEY, "pm", undefined, "disp:1", DISPOSITION_FILE_SUFFIX)).toMatch(
			/\.disposition\.json$/,
		);
	});

	it("refuses illegal key/task names and arbitrary target paths (no traversal)", async () => {
		const badKey = new LocalSelectionStore({
			agenticdoc_root: root,
			key: "../escape",
			host_adapter: hostAdapter(),
		});
		expect((await badKey.commitSelection(commitRequest())).code).toBe("target-path-invalid");
		const badTask = makeStore();
		const workerReq = commitRequest({
			source: "worker-local",
			task_key: "../../evil",
			run_id: WORKER_RUN,
		});
		expect((await badTask.commitSelection(workerReq)).code).toBe("target-path-invalid");
		const longRef = makeStore();
		expect((await longRef.commitSelection(commitRequest({ local_ref: "y".repeat(300) }))).code).toBe(
			"target-path-invalid",
		);
	});
});

// ── Legit writes and strict selection/execution separation ─────────────────

describe("legit selection / execution", () => {
	it("commits a planned selection atomically and reads it back shape-only", async () => {
		const store = makeStore();
		const result = await store.commitSelection(commitRequest());
		expect(result.code, result.reason).toBe("written");
		expect(result.ok).toBe(true);
		expect(result.host_source_verified).toBe(true);
		expect(result.verification).toBe("host-context-checked");
		expect(fs.existsSync(selectionFile())).toBe(true);
		const parsed = parseLocalSelectionRecord(JSON.parse(fs.readFileSync(selectionFile(), "utf8")));
		expect(parsed.ok).toBe(true);
		const read = store.readSelection({ source: "pm", ref: LOCAL_REF });
		expect(read.status).toBe("ok");
		expect(read.verification).toBe("shape-only");
		expect(read.host_source_verified).toBe(false); // pure read NEVER source-verified
		expect(read.record?.action_state).toBe("planned");
		expect(read.record?.business_completed).toBe(false);
		expect(read.record).not.toHaveProperty("action_ref"); // selection carries no execution facts
	});

	it("appends a real execution (physically separate) only after a verifier proof", async () => {
		const store = makeStore();
		await commitOk(store);
		const result = await store.appendExecution(execRequest());
		expect(result.code, result.reason).toBe("written");
		expect(result.effect_state).toBe("known");
		expect(fs.existsSync(executionFile())).toBe(true);
		expect(executionFile()).not.toBe(selectionFile());
		const onDisk = parseLocalExecutionRecord(JSON.parse(fs.readFileSync(executionFile(), "utf8")));
		expect(onDisk.ok).toBe(true);
		const read = store.readExecution({ source: "pm", ref: LOCAL_REF });
		expect(read.status).toBe("ok");
		expect(read.verification).toBe("shape-only");
		expect(read.host_source_verified).toBe(false);
		expect(read.record?.verified_by).toBe("target-verifier:1");
		// Selection file is unchanged (still a plan, not an execution).
		const sel = parseLocalSelectionRecord(JSON.parse(fs.readFileSync(selectionFile(), "utf8")));
		expect(sel.ok).toBe(true);
	});

	it("a selection cannot be read as an execution and vice versa", async () => {
		const store = makeStore();
		await commitOk(store);
		expect(store.readExecution({ source: "pm", ref: LOCAL_REF }).status).toBe("absent");
		// Write an execution-shaped object at the selection path: strict read rejects it.
		fs.writeFileSync(selectionFile(), JSON.stringify({ kind: "local-execution", schema_version: 1 }), "utf8");
		expect(store.readSelection({ source: "pm", ref: LOCAL_REF }).status).toBe("invalid-shape");
	});

	it("persists a necessary disposition to its own file", async () => {
		const store = makeStore();
		const result = await store.saveDisposition({
			source: "pm",
			disposition_ref: "disp:T01:1",
			disposition: dispositionValue(),
		});
		expect(result.code, result.reason).toBe("written");
		const dispFile = storedRecordPath(root, KEY, "pm", undefined, "disp:T01:1", DISPOSITION_FILE_SUFFIX);
		expect(fs.existsSync(dispFile)).toBe(true);
		expect(store.readDisposition({ source: "pm", ref: "disp:T01:1" }).host_source_verified).toBe(false);
	});
});

// ── duplicate / conflict / existing integrity ──────────────────────────────

describe("duplicate / conflict / damaged existing", () => {
	it("semantically identical replay returns duplicate; JSON key order is not a conflict", async () => {
		const store = makeStore();
		await commitOk(store);
		// Rewrite the existing record with reversed key order (same values).
		const original = JSON.parse(fs.readFileSync(selectionFile(), "utf8")) as Record<string, unknown>;
		const reversed: Record<string, unknown> = {};
		for (const key of Object.keys(original).reverse()) reversed[key] = original[key];
		fs.writeFileSync(selectionFile(), JSON.stringify(reversed), "utf8");
		const result = await store.commitSelection(commitRequest());
		expect(result.code, result.reason).toBe("duplicate");
		expect(result.ok).toBe(true);
		expect(result.host_source_verified).toBe(true);
	});

	it("a different choice/basis/material returns conflict and never overwrites", async () => {
		const store = makeStore();
		await commitOk(store);
		const before = fs.readFileSync(selectionFile(), "utf8");
		const conflict = await store.commitSelection(
			commitRequest({ selection: selectionFields({ selected_action: "narrow", selected_basis_id: "b2" }) }),
		);
		expect(conflict.code, conflict.reason).toBe("conflict");
		expect(fs.readFileSync(selectionFile(), "utf8")).toBe(before);
	});

	it("bad JSON / wrong shape / unknown keys / DP-field existing are never overwritten", async () => {
		for (const [label, payload, expected] of [
			["bad-json", "{not json", "existing-corrupt"],
			["wrong-shape", JSON.stringify({ schema_version: 1, kind: "local-selection" }), "existing-invalid"],
			[
				"unknown-key",
				JSON.stringify({ schema_version: 1, kind: "local-selection", surprise: 1 }),
				"existing-invalid",
			],
			[
				"dp-field",
				JSON.stringify({ schema_version: 1, kind: "local-selection", decision_id: "dp-auto:x", available: true }),
				"existing-invalid",
			],
		] as const) {
			const store = makeStore();
			const file = selectionFile(`local:${label}`);
			fs.mkdirSync(path.dirname(file), { recursive: true });
			fs.writeFileSync(file, payload, "utf8");
			const result = await store.commitSelection(commitRequest({ local_ref: `local:${label}` }));
			expect(result.code, `${label}: ${result.reason}`).toBe(expected);
			expect(fs.readFileSync(file, "utf8")).toBe(payload); // unchanged
		}
	});

	it("two competing commits yield exactly one unique selection", async () => {
		const store = makeStore();
		const [a, b] = await Promise.all([
			store.commitSelection(commitRequest()),
			store.commitSelection(commitRequest()),
		]);
		const codes = [a.code, b.code].sort();
		expect(codes).toEqual(["duplicate", "written"]);
		expect(
			fs.readdirSync(path.dirname(selectionFile())).filter((name) => name.endsWith(SELECTION_FILE_SUFFIX)),
		).toHaveLength(1);
	});

	it("an existing file with duplicate JSON keys is never overwritten (store's own byte check)", async () => {
		const store = makeStore();
		const ref = "local:dupkeys";
		const file = selectionFile(ref);
		fs.mkdirSync(path.dirname(file), { recursive: true });
		// JSON.parse collapses duplicate keys; the raw scan must still refuse the bytes.
		const payload = '{"schema_version":1,"schema_version":1,"kind":"local-selection"}';
		fs.writeFileSync(file, payload, "utf8");
		const result = await store.commitSelection(commitRequest({ local_ref: ref }));
		expect(result.code, result.reason).toBe("existing-corrupt");
		expect(result.ok).toBe(false);
		expect(result.host_source_verified).toBe(false);
		expect(store.readSelection({ source: "pm", ref }).status).toBe("corrupt");
		expect(fs.readFileSync(file, "utf8")).toBe(payload);
	});

	it("a foreign local lock is never cleaned and lock-busy submits no controlled effect", async () => {
		const store = makeStore({ lock_options: { retries: 2, baseDelayMs: 1 } });
		const file = selectionFile();
		fs.mkdirSync(path.dirname(file), { recursive: true });
		const foreignLock = `${file}.lock`;
		fs.writeFileSync(foreignLock, "foreign", "utf8");
		const result = await store.commitSelection(commitRequest());
		expect(result.code).toBe("lock-busy");
		expect(fs.readFileSync(foreignLock, "utf8")).toBe("foreign"); // not cleaned
		expect(fs.existsSync(file)).toBe(false); // no controlled effect
	});

	it("old-run/foreign existing record is a read-only recovery clue, never replayed or overwritten", async () => {
		const store = makeStore();
		await commitOk(store);
		const before = fs.readFileSync(selectionFile(), "utf8");
		// Bump the trusted binding_version so the existing record is from an old snapshot.
		const drifted = makeStore({
			host_adapter: hostAdapter({ ctx: trustedContext({ binding_version: "v4" }) }),
		});
		const result = await drifted.commitSelection(commitRequest());
		expect(result.code, result.reason).toBe("recovery-clue");
		expect(result.recovery_clue?.record).toBeDefined();
		expect(result.host_source_verified).toBe(false);
		expect(fs.readFileSync(selectionFile(), "utf8")).toBe(before); // not overwritten
	});
});

// ── Path redirects / symlinks / junctions / escape ─────────────────────────

describe("redirect / symlink / junction / escape", () => {
	it("rejects a junction placed at the record directory", async () => {
		const outside = path.join(tmp, "outside");
		fs.mkdirSync(outside, { recursive: true });
		fs.mkdirSync(path.join(root, KEY, "evidence"), { recursive: true });
		const junction = path.join(root, KEY, "evidence", "decision-handoffs");
		fs.symlinkSync(outside, junction, "junction");
		const result = await makeStore().commitSelection(commitRequest());
		expect(result.code).toBe("redirect-detected");
		expect(fs.existsSync(path.join(outside, path.basename(selectionFile())))).toBe(false);
	});

	it("rejects a symlinked record file", async () => {
		const file = selectionFile();
		fs.mkdirSync(path.dirname(file), { recursive: true });
		const outside = path.join(tmp, "out.json");
		fs.writeFileSync(outside, "{}", "utf8");
		fs.symlinkSync(outside, file, "file");
		const read = makeStore().readSelection({ source: "pm", ref: LOCAL_REF });
		expect(read.status).toBe("refused");
		expect(read.code).toBe("redirect-detected");
	});

	it("reads never create directories (pure shape-only read)", () => {
		const freshRoot = path.join(tmp, "fresh", ".agenticdoc");
		const store = new LocalSelectionStore({ agenticdoc_root: freshRoot, key: KEY });
		const read = store.readSelection({ source: "pm", ref: LOCAL_REF });
		expect(read.status).toBe("absent");
		expect(fs.existsSync(path.join(freshRoot, KEY))).toBe(false);
	});
});

// ── Trusted host binding: 0 / multiple / foreign / old claim-run ───────────

describe("authoritative binding (unique active exact-self, not _index.md)", () => {
	it("0 active exact-self rows are refused", async () => {
		writeIndex([{ key: KEY, status: "idle", phase: "EXECUTE", claimId: CLAIM, updated: "2026-11-12T12:00:00Z" }]);
		expect((await makeStore().commitSelection(commitRequest())).code).toBe("binding-no-unique-active");
	});

	it("multiple active exact-self rows are refused", async () => {
		writeIndex([
			{ key: KEY, status: "active", phase: "EXECUTE", claimId: CLAIM, updated: "2026-11-12T12:00:00Z" },
			{ key: KEY, status: "active", phase: "EXECUTE", claimId: CLAIM, updated: "2026-11-12T12:05:00Z" },
		]);
		expect((await makeStore().commitSelection(commitRequest())).code).toBe("binding-ambiguous");
	});

	it("a foreign (other-window) active claim is refused", async () => {
		writeIndex([
			{ key: KEY, status: "active", phase: "EXECUTE", claimId: "OTHER:999", updated: "2026-11-12T12:00:00Z" },
		]);
		expect((await makeStore().commitSelection(commitRequest())).code).toBe("binding-foreign");
	});

	it("a stale/old claim id in the trusted context is refused", async () => {
		const store = makeStore({ host_adapter: hostAdapter({ ctx: trustedContext({ self_claim_id: "OLD:111" }) }) });
		expect((await store.commitSelection(commitRequest())).code).toBe("binding-foreign");
	});

	it("wrong host role for the source is refused", async () => {
		const store = makeStore({ host_adapter: hostAdapter({ ctx: trustedContext({ role: "coding" }) }) });
		expect((await store.commitSelection(commitRequest())).code).toBe("binding-foreign");
	});

	it("old worker run/task drift is refused", async () => {
		const ctx = trustedContext({ role: "coding", task_key: WORKER_TASK, run_id: WORKER_RUN });
		const store = makeStore({ host_adapter: hostAdapter({ ctx }) });
		const req = commitRequest({ source: "worker-local", task_key: WORKER_TASK, run_id: "run-OLD" });
		expect((await store.commitSelection(req)).code).toBe("binding-stale-run");
	});

	it("_index.md is only a projection and never an authority source", async () => {
		// A projection that lists the key cannot rescue a missing authoritative row.
		writeIndex([]);
		fs.writeFileSync(path.join(root, "_index.md"), `# AgenticTask Index\n\nactive_keys: ["${KEY}"]\n`, "utf8");
		expect((await makeStore().commitSelection(commitRequest())).code).toBe("binding-no-unique-active");
	});

	it("worker-local records land under workers/<task>/local-decisions", async () => {
		const ctx = trustedContext({ role: "coding", task_key: WORKER_TASK, run_id: WORKER_RUN });
		const store = makeStore({ host_adapter: hostAdapter({ ctx }) });
		const req = commitRequest({ source: "worker-local", task_key: WORKER_TASK, run_id: WORKER_RUN });
		const result = await store.commitSelection(req);
		expect(result.code, result.reason).toBe("written");
		expect(result.path).toContain(path.join("workers", WORKER_TASK, "local-decisions"));
	});
});

// ── Trust boundary: fail closed, never model-supplied provenance ───────────

describe("trusted host adapter / verifier (fail closed)", () => {
	it("missing adapter ⇒ trusted-context-missing, no write", async () => {
		const store = makeStore({ host_adapter: undefined });
		const result = await store.commitSelection(commitRequest());
		expect(result.code).toBe("trusted-context-missing");
		expect(result.host_source_verified).toBe(false);
		expect(fs.existsSync(selectionFile())).toBe(false);
	});

	it("refused/throwing trusted context fails closed", async () => {
		const refused = makeStore({ host_adapter: hostAdapter({ ctx: undefined }) });
		// ctx===undefined means "return the default"; use a throwing adapter for the throw path.
		const throwing = makeStore({
			host_adapter: { readTrustedContext: async () => undefined },
		});
		expect((await throwing.commitSelection(commitRequest())).code).toBe("trusted-context-refused");
		const boom = makeStore({
			host_adapter: {
				readTrustedContext: async () => {
					throw new Error("host unavailable");
				},
			},
		});
		expect((await boom.commitSelection(commitRequest())).code).toBe("trusted-context-refused");
		expect(refused).toBeDefined();
	});

	it("material / basis / parent / matter expectation drift is refused", async () => {
		for (const [field, value, expected] of [
			["material_digest", "sha256:OTHER", "material-drift"],
			["basis_digest", "sha256:OTHER", "basis-drift"],
			["matter_version", "mv2", "matter-drift"],
			["parent_decision_id", "dp-auto:x", "parent-drift"],
		] as const) {
			const base = trustedContext();
			const ctx = trustedContext({ expected: { ...base.expected, [field]: value } });
			const result = await makeStore({ host_adapter: hostAdapter({ ctx }) }).commitSelection(commitRequest());
			expect(result.code, `${field}: ${result.reason}`).toBe(expected);
		}
	});

	it("no execution verifier ⇒ verifier-missing, no execution file", async () => {
		const store = makeStore({ host_adapter: hostAdapter({ noVerifier: true }) });
		await commitOk(store);
		const result = await store.appendExecution(execRequest());
		expect(result.code).toBe("verifier-missing");
		expect(fs.existsSync(executionFile())).toBe(false);
	});

	it("verifier returns no proof ⇒ verifier-unproven; model self-report cannot force known", async () => {
		const store = makeStore({ host_adapter: hostAdapter({ noProof: true }) });
		await commitOk(store);
		const result = await store.appendExecution(execRequest({ claimed_effect_state: "known" }));
		expect(result.code).toBe("verifier-unproven");
		expect(fs.existsSync(executionFile())).toBe(false);
	});

	it("verifier proof that does not correlate is refused (no boolean self-proof)", async () => {
		const store = makeStore({
			host_adapter: hostAdapter({ proof: executionProof({ action_ref: "tool_call:OTHER" }) }),
		});
		await commitOk(store);
		expect((await store.appendExecution(execRequest())).code).toBe("verifier-unproven");
		expect(fs.existsSync(executionFile())).toBe(false);
	});

	it("execution requires the original selection and current consistent binding", async () => {
		const store = makeStore();
		// No selection committed yet.
		expect((await store.appendExecution(execRequest())).code).toBe("selection-invalid");
	});

	it("execution verifier with unknown effect writes effect_state=unknown", async () => {
		const store = makeStore({
			host_adapter: hostAdapter({ proof: executionProof({ effect_state: "unknown" }) }),
		});
		await commitOk(store);
		const result = await store.appendExecution(execRequest());
		expect(result.code, result.reason).toBe("written");
		expect(result.effect_state).toBe("unknown");
	});

	it("target digest drift is refused", async () => {
		const base = trustedContext();
		const ctx = trustedContext({ expected: { ...base.expected, target_digest: "sha256:expected-target" } });
		const store = makeStore({
			host_adapter: hostAdapter({ ctx, proof: executionProof({ target_digest: "sha256:other" }) }),
		});
		await commitOk(store);
		expect((await store.appendExecution(execRequest())).code).toBe("target-drift");
	});
});

// ── Budget: finite, real preflight, no default grant, no ledger ─────────────

describe("finite budget / real reservation preflight", () => {
	it("non-finite budget is refused (no default unlimited value)", async () => {
		const ctx = trustedContext({
			budget: {
				...(trustedContext().budget as Record<string, unknown>),
				remaining_cost: Number.POSITIVE_INFINITY,
			},
		});
		expect((await makeStore({ host_adapter: hostAdapter({ ctx }) }).commitSelection(commitRequest())).code).toBe(
			"budget-invalid",
		);
	});

	it("missing preflight returns a fillable gap, not a default grant", async () => {
		const ctx = trustedContext({ budget_preflight: undefined });
		const result = await makeStore({ host_adapter: hostAdapter({ ctx }) }).commitSelection(commitRequest());
		expect(result.code).toBe("budget-preflight-missing");
		expect(result.gaps).toContain("budget_preflight");
		expect(fs.existsSync(selectionFile())).toBe(false);
	});

	it("denied / exhausted / mis-shaped preflight is refused", async () => {
		const denied = trustedContext({
			budget_preflight: {
				granted: false,
				reserved_steps: 0,
				reserved_cost: 0,
				remaining_after_steps: 3,
				remaining_after_cost: 5,
				reason: "insufficient-remaining",
			},
		});
		expect(
			(await makeStore({ host_adapter: hostAdapter({ ctx: denied }) }).commitSelection(commitRequest())).code,
		).toBe("budget-preflight-denied");
		const malformed = trustedContext({ budget_preflight: { granted: "yes" } });
		expect(
			(await makeStore({ host_adapter: hostAdapter({ ctx: malformed }) }).commitSelection(commitRequest())).code,
		).toBe("budget-preflight-missing");
		const exhausted = trustedContext({
			budget: { ...(trustedContext().budget as Record<string, unknown>), remaining_cost: 0 },
		});
		expect(
			(await makeStore({ host_adapter: hostAdapter({ ctx: exhausted }) }).commitSelection(commitRequest())).code,
		).toBe("budget-exhausted");
	});

	it("reserved is never faked as cost_consumed; no ledger schema is created", async () => {
		const store = makeStore();
		await commitOk(store);
		const raw = JSON.parse(fs.readFileSync(selectionFile(), "utf8")) as Record<string, unknown>;
		expect(raw).not.toHaveProperty("cost_consumed");
		expect(raw).not.toHaveProperty("reserved_cost");
		// No new ledger-like file appears under .mw or the handoff base.
		const mwFiles = fs.readdirSync(path.join(root, "..", ".mw"));
		expect(mwFiles.filter((name) => /ledger|budget/i.test(name))).toHaveLength(0);
	});
});

// ── Stop scope / diagnostic isolation / write-rename failure ────────────────

describe("stop scope, diagnostics and write/rename failure", () => {
	it("user-global / pm-or-key / matter stops block new writes; read-only clue still available", async () => {
		const ctx = trustedContext({ stop_signals: [{ signal_ref: "stop:1", kind: "user-stop" }] });
		const store = makeStore({ host_adapter: hostAdapter({ ctx }) });
		const result = await store.commitSelection(commitRequest());
		expect(result.code).toBe("stop-scope-blocked");
		expect(fs.existsSync(selectionFile())).toBe(false);
		// Pure read stays available (shape-only), even under a stop.
		expect(store.readSelection({ source: "pm", ref: LOCAL_REF }).verification).toBe("shape-only");
	});

	it("service timeout does not stop the PM; worker deadline does not stop a pm", async () => {
		const service = makeStore({
			host_adapter: hostAdapter({
				ctx: trustedContext({ stop_signals: [{ signal_ref: "s", kind: "service-timeout" }] }),
			}),
		});
		expect((await service.commitSelection(commitRequest())).code).toBe("written");
		const workerDeadline = makeStore({
			host_adapter: hostAdapter({
				ctx: trustedContext({ stop_signals: [{ signal_ref: "d", kind: "worker-deadline" }] }),
			}),
		});
		expect(
			(await workerDeadline.commitSelection(commitRequest({ local_ref: "local:T01:workerdeadline" }))).code,
		).toBe("written");
	});

	it("worker deadline DOES stop a worker-local source (scope respected)", async () => {
		const ctx = trustedContext({
			role: "coding",
			task_key: WORKER_TASK,
			run_id: WORKER_RUN,
			stop_signals: [{ signal_ref: "d", kind: "worker-deadline" }],
		});
		const store = makeStore({ host_adapter: hostAdapter({ ctx }) });
		const req = commitRequest({ source: "worker-local", task_key: WORKER_TASK, run_id: WORKER_RUN });
		expect((await store.commitSelection(req)).code).toBe("stop-scope-blocked");
	});

	it("diagnostic log failure never stops the PM (best-effort)", async () => {
		const diag = path.join(tmp, "diag-as-dir");
		fs.mkdirSync(diag, { recursive: true }); // appendFileSync on a directory throws
		const store = makeStore({ diagnostic_log: diag });
		expect((await store.commitSelection(commitRequest())).code).toBe("written");
		expect((await store.appendExecution(execRequest())).code).toBe("written");
	});

	it("mandatory selection write failure ⇒ write-failed, no controlled effect", async () => {
		const store = makeStore({
			atomic_write: () => {
				throw Object.assign(new Error("simulated EIO"), { code: "EIO" });
			},
		});
		const result = await store.commitSelection(commitRequest());
		expect(result.code).toBe("write-failed");
		expect(result.ok).toBe(false);
		expect(result.host_source_verified).toBe(false);
		expect(fs.existsSync(selectionFile())).toBe(false);
	});

	it("a real rename failure on execution ⇒ effect-unknown (needs reconciliation, not written/unexecuted)", async () => {
		const store = makeStore({
			atomic_write: (file, value) => {
				// Real disk fault: a directory at the target makes fs.renameSync fail.
				fs.mkdirSync(file, { recursive: true });
				atomicWriteJson(file, value);
			},
		});
		await commitOk(
			new LocalSelectionStore({
				agenticdoc_root: root,
				key: KEY,
				host_adapter: hostAdapter(),
				lock_options: { retries: 14, baseDelayMs: 3 },
			}),
		);
		const result = await store.appendExecution(execRequest());
		expect(result.code).toBe("effect-unknown");
		expect(result.effect_state).toBe("unknown");
		expect(result.host_source_verified).toBe(false);
	});
});

// ── Reuse of the frozen contract (no schema fork) ──────────────────────────

describe("reuses the frozen schema v1 contract", () => {
	it("records use schema_version 1 and the frozen field/category lists", async () => {
		const store = makeStore();
		await commitOk(store);
		const raw = JSON.parse(fs.readFileSync(selectionFile(), "utf8")) as Record<string, unknown>;
		expect(raw.schema_version).toBe(1);
		for (const field of SCHEMA_V1.local_selection_fields) {
			if (field in raw) expect(SCHEMA_V1.local_selection_fields).toContain(field);
		}
		expect(SCHEMA_V1.verification_scope).toBe("shape-only");
		expect(SCHEMA_V1.host_source_verified).toBe(false);
	});

	it("a shape-only parse of a selection is still not source verified", async () => {
		const store = makeStore();
		await commitOk(store);
		const parsed = parseLocalSelectionRecord(JSON.parse(fs.readFileSync(selectionFile(), "utf8")));
		expect(parsed.ok).toBe(true);
		if (parsed.ok) {
			expect(parsed.verification).toBe("shape-only");
			expect(parsed.host_source_verified).toBe(false);
		}
	});
});

// ── R1 acceptance repairs: TS01..TS05 red probes; TS06 stays green ────────

describe("R1 acceptance repairs (five PM red probes)", () => {
	// TS01 — strict byte-level existing JSON, both read and controlled write.
	it("TS01 a COMPLETE valid record with an injected duplicate key is not a verified duplicate", async () => {
		const store = makeStore();
		await commitOk(store);
		const file = selectionFile();
		const raw = fs.readFileSync(file, "utf8");
		const injected = raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1');
		expect(injected).not.toBe(raw); // a real complete record, not an incomplete shape
		fs.writeFileSync(file, injected, "utf8");
		const result = await store.commitSelection(commitRequest());
		expect(result.code, result.reason).toBe("existing-corrupt");
		expect(result.ok).toBe(false);
		expect(result.host_source_verified).toBe(false);
		expect(result.reason).toMatch(/duplicate JSON object key/);
		expect(fs.readFileSync(file, "utf8")).toBe(injected);
		const read = store.readSelection({ source: "pm", ref: LOCAL_REF });
		expect(read.status).toBe("corrupt");
		expect(read.verification).toBe("shape-only");
		expect(read.host_source_verified).toBe(false);
	});

	it("TS01 nested and escaped-equivalent duplicate keys are refused; execution existing too", async () => {
		const store = makeStore();
		await commitOk(store);
		const file = selectionFile();
		const validRaw = fs.readFileSync(file, "utf8");
		const escapedKey = `"${String.fromCharCode(0x5c)}u0073chema_version"`;
		const variants = [
			validRaw.replace('"host_binding": {', '"host_binding": { "role": "pm",'),
			validRaw.replace('"schema_version": 1', `"schema_version": 1, ${escapedKey}: 1`),
		];
		for (const payload of variants) {
			expect(payload).not.toBe(validRaw);
			fs.writeFileSync(file, payload, "utf8");
			const result = await store.commitSelection(commitRequest());
			expect(result.code, result.reason).toBe("existing-corrupt");
			expect(store.readSelection({ source: "pm", ref: LOCAL_REF }).status).toBe("corrupt");
			expect(fs.readFileSync(file, "utf8")).toBe(payload);
		}
		fs.writeFileSync(file, validRaw, "utf8");
		expect((await store.appendExecution(execRequest())).code).toBe("written");
		const execFile = executionFile();
		const execRaw = fs.readFileSync(execFile, "utf8");
		fs.writeFileSync(
			execFile,
			execRaw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
			"utf8",
		);
		const replay = await store.appendExecution(execRequest());
		expect(replay.ok).toBe(false);
		expect(replay.code).toBe("existing-corrupt");
	});

	// TS02 — real/injectable current clock, never an old snapshot as authorization.
	it("TS02 a past snapshot with a past deadline cannot authorize a commit today", async () => {
		const base = trustedContext();
		const ctx = trustedContext({
			observed_at: "2000-01-01T00:00:00Z",
			budget: { ...(base.budget as Record<string, unknown>), deadline: "2000-01-02T00:00:00Z" },
		});
		const store = makeStore({ host_adapter: hostAdapter({ ctx }) }); // production default: real clock
		const result = await store.commitSelection(commitRequest());
		expect(result.code, result.reason).toBe("trusted-context-refused");
		expect(result.ok).toBe(false);
		expect(fs.existsSync(selectionFile())).toBe(false);
	});

	it("TS02 stale / future snapshots and an expired deadline are refused", async () => {
		const stale = makeStore({
			host_adapter: hostAdapter({ ctx: trustedContext({ observed_at: "2000-01-01T00:00:00Z" }) }),
		});
		expect((await stale.commitSelection(commitRequest())).code).toBe("trusted-context-refused");
		const future = makeStore({
			host_adapter: hostAdapter({
				ctx: trustedContext({ observed_at: new Date(Date.now() + 3600_000).toISOString() }),
			}),
		});
		expect((await future.commitSelection(commitRequest())).code).toBe("trusted-context-refused");
		const base = trustedContext();
		const expired = makeStore({
			host_adapter: hostAdapter({
				ctx: trustedContext({
					budget: {
						...(base.budget as Record<string, unknown>),
						deadline: new Date(Date.now() - 60_000).toISOString(),
					},
				}),
			}),
		});
		expect((await expired.commitSelection(commitRequest())).code).toBe("budget-exhausted");
		expect(fs.existsSync(selectionFile())).toBe(false);
	});

	it("TS02 a finite injected clock is deterministic; a non-finite clock fails closed", async () => {
		const fixed = Date.parse(NOW);
		expect((await makeStore({ clock: () => fixed }).commitSelection(commitRequest())).code).toBe("written");
		const near = new Date(fixed + 60_000).toISOString();
		const ctx = trustedContext({
			budget: { ...(trustedContext().budget as Record<string, unknown>), deadline: near },
		});
		const beyond = makeStore({ host_adapter: hostAdapter({ ctx }), clock: () => fixed + 61_000 });
		expect((await beyond.commitSelection(commitRequest({ local_ref: "local:TS02:late" }))).code).toBe(
			"budget-exhausted",
		);
		for (const bad of [Number.POSITIVE_INFINITY, Number.NaN]) {
			const ref = "local:TS02:badclock";
			const result = await makeStore({ clock: () => bad }).commitSelection(commitRequest({ local_ref: ref }));
			expect(result.code).toBe("trusted-context-refused");
			expect(result.host_source_verified).toBe(false);
			expect(fs.existsSync(selectionFile(ref))).toBe(false);
		}
	});

	// TS03 — current-key authority ambiguity, without misrejecting other keys.
	it("TS03 one self plus one foreign active row for the SAME key is ambiguous", async () => {
		writeIndex([
			{ key: KEY, status: "active", phase: "EXECUTE", claimId: CLAIM, updated: "2026-11-12T12:00:00Z" },
			{ key: KEY, status: "active", phase: "EXECUTE", claimId: "OTHER:999", updated: "2026-11-12T12:00:00Z" },
		]);
		const result = await makeStore().commitSelection(commitRequest());
		expect(result.code, result.reason).toBe("binding-ambiguous");
		expect(result.ok).toBe(false);
		expect(fs.existsSync(selectionFile())).toBe(false);
		const twoForeign = makeStore();
		writeIndex([
			{ key: KEY, status: "active", phase: "EXECUTE", claimId: "OTHER:1", updated: "2026-11-12T12:00:00Z" },
			{ key: KEY, status: "active", phase: "EXECUTE", claimId: "OTHER:2", updated: "2026-11-12T12:00:00Z" },
		]);
		expect((await twoForeign.commitSelection(commitRequest())).code).toBe("binding-ambiguous");
	});

	it("TS03 unrelated active rows for OTHER keys never cause a false refusal", async () => {
		writeIndex([
			{ key: KEY, status: "active", phase: "EXECUTE", claimId: CLAIM, updated: "2026-11-12T12:00:00Z" },
			{
				key: "other-key",
				status: "active",
				phase: "EXECUTE",
				claimId: "OTHER:999",
				updated: "2026-11-12T12:00:00Z",
			},
			{
				key: "third-key",
				status: "active",
				phase: "EXECUTE",
				claimId: "OTHER:888",
				updated: "2026-11-12T12:00:00Z",
			},
		]);
		const result = await makeStore().commitSelection(commitRequest());
		expect(result.code, result.reason).toBe("written");
		expect(result.host_source_verified).toBe(true);
	});

	// TS04 — exact request <-> record <-> trusted identity, absent<->present drift.
	it("TS04 an original selection for ANOTHER ref at the requested filename is refused", async () => {
		const store = makeStore();
		await commitOk(store);
		const file = selectionFile();
		const record = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
		record.local_ref = "local:OTHER";
		fs.writeFileSync(file, JSON.stringify(record), "utf8");
		const result = await store.appendExecution(execRequest());
		expect(result.code, result.reason).toBe("selection-invalid");
		expect(result.ok).toBe(false);
		expect(result.host_source_verified).toBe(false);
		expect(fs.existsSync(executionFile())).toBe(false);
	});

	it("TS04 source / key / task / run drift in a valid original selection is refused", async () => {
		const store = makeStore();
		await commitOk(store);
		const file = selectionFile();
		const validRaw = fs.readFileSync(file, "utf8");
		const mutations: { label: string; mutate: (record: Record<string, unknown>) => void }[] = [
			{
				label: "source",
				mutate: (r) => {
					r.source = "worker-local";
				},
			},
			{
				label: "key",
				mutate: (r) => {
					(r.host_binding as Record<string, unknown>).key = "other-key";
				},
			},
			{
				label: "task",
				mutate: (r) => {
					(r.host_binding as Record<string, unknown>).task_key = WORKER_TASK;
				},
			},
			{
				label: "run",
				mutate: (r) => {
					(r.host_binding as Record<string, unknown>).run_id = WORKER_RUN;
				},
			},
		];
		for (const { label, mutate } of mutations) {
			const record = JSON.parse(validRaw) as Record<string, unknown>;
			mutate(record);
			fs.writeFileSync(file, JSON.stringify(record), "utf8");
			const result = await store.appendExecution(execRequest());
			expect(result.code, `${label}: ${result.reason}`).toBe("selection-invalid");
			expect(fs.existsSync(executionFile()), label).toBe(false);
		}
	});

	it("TS04 a proof correlated to another local_ref is refused; worker-local run is required", async () => {
		const wrongProof = makeStore({
			host_adapter: hostAdapter({ proof: executionProof({ local_ref: "local:OTHER" }) }),
		});
		await commitOk(wrongProof);
		expect((await wrongProof.appendExecution(execRequest())).code).toBe("verifier-unproven");
		expect(fs.existsSync(executionFile())).toBe(false);

		const ctx = trustedContext({ role: "coding", task_key: WORKER_TASK, run_id: WORKER_RUN });
		const worker = makeStore({ host_adapter: hostAdapter({ ctx }) });
		await commitOk(worker, commitRequest({ source: "worker-local", task_key: WORKER_TASK, run_id: WORKER_RUN }));
		const exact = await worker.appendExecution(
			execRequest({ source: "worker-local", task_key: WORKER_TASK, run_id: WORKER_RUN }),
		);
		expect(exact.code, exact.reason).toBe("written");
		const missingRun = await worker.appendExecution(
			execRequest({ source: "worker-local", task_key: WORKER_TASK, run_id: undefined }),
		);
		expect(missingRun.code, missingRun.reason).toBe("selection-invalid");
	});

	// TS05 — re-read trusted context / index / paths / clock AFTER the await.
	it("TS05 basis drift during the awaited verifier refuses the write without claiming unexecuted", async () => {
		const ctx = trustedContext();
		const adapter: LocalSelectionHostAdapter = {
			readTrustedContext: async () => ctx, // SAME object: an in-place mutation must not hide the drift
			verifyExecution: async () => {
				ctx.expected.basis_digest = "sha256:CHANGED";
				return executionProof();
			},
		};
		const store = makeStore({ host_adapter: adapter });
		await commitOk(store);
		const result = await store.appendExecution(execRequest());
		expect(result.code, result.reason).toBe("trusted-context-refused");
		expect(result.ok).toBe(false);
		expect(result.host_source_verified).toBe(false);
		expect(result.reason).toMatch(/action may already have been performed/);
		expect(result.reason).toMatch(/not a known-unexecuted result/);
		expect(fs.existsSync(executionFile())).toBe(false);
	});

	it("TS05 material / basis / budget / stop / run / target drift during the verifier is refused", async () => {
		const drifts: { label: string; mutate: (ctx: TrustedHostContext) => void }[] = [
			{
				label: "material",
				mutate: (ctx) => {
					ctx.expected.material_digest = "sha256:OTHER";
				},
			},
			{
				label: "basis",
				mutate: (ctx) => {
					ctx.expected.basis_digest = "sha256:OTHER";
				},
			},
			{
				label: "budget",
				mutate: (ctx) => {
					ctx.budget = { ...(ctx.budget as Record<string, unknown>), max_steps: 1 };
				},
			},
			{
				label: "stop",
				mutate: (ctx) => {
					ctx.stop_signals = [{ signal_ref: "stop:1", kind: "user-stop" }];
				},
			},
			{
				label: "run",
				mutate: (ctx) => {
					ctx.run_id = "run:OTHER";
				},
			},
			{
				label: "target",
				mutate: (ctx) => {
					ctx.expected.target_digest = "sha256:OTHER";
				},
			},
		];
		for (const { label, mutate } of drifts) {
			for (const file of [selectionFile(), executionFile()]) {
				if (fs.existsSync(file)) fs.unlinkSync(file);
			}
			const ctx = trustedContext();
			const adapter: LocalSelectionHostAdapter = {
				readTrustedContext: async () => ctx,
				verifyExecution: async () => {
					mutate(ctx);
					return executionProof();
				},
			};
			const store = makeStore({ host_adapter: adapter });
			await commitOk(store);
			const result = await store.appendExecution(execRequest());
			expect(result.ok, `${label}: ${result.reason}`).toBe(false);
			expect(result.host_source_verified, label).toBe(false);
			expect(fs.existsSync(executionFile()), label).toBe(false);
		}
	});

	it("TS05 missing/throwing verifier context, index drift and clock drift all fail closed", async () => {
		const resetFiles = (): void => {
			writeIndex(defaultIndex());
			for (const file of [selectionFile(), executionFile()]) {
				if (fs.lstatSync(file, { throwIfNoEntry: false }) !== undefined) fs.unlinkSync(file);
			}
		};
		let available = true;
		const disappearing: LocalSelectionHostAdapter = {
			readTrustedContext: async () => (available ? trustedContext() : undefined),
			verifyExecution: async () => {
				available = false;
				return executionProof();
			},
		};
		const noContext = makeStore({ host_adapter: disappearing });
		await commitOk(noContext);
		const lost = await noContext.appendExecution(execRequest());
		expect(lost.code, lost.reason).toBe("trusted-context-refused");
		expect(fs.existsSync(executionFile())).toBe(false);

		resetFiles();
		const throwing = makeStore({
			host_adapter: {
				readTrustedContext: async () => trustedContext(),
				verifyExecution: async () => {
					throw new Error("verifier unavailable");
				},
			},
		});
		await commitOk(throwing);
		expect((await throwing.appendExecution(execRequest())).code).toBe("verifier-unproven");

		resetFiles();
		const indexDrift: LocalSelectionHostAdapter = {
			readTrustedContext: async () => trustedContext(),
			verifyExecution: async () => {
				writeIndex([
					{ key: KEY, status: "active", phase: "EXECUTE", claimId: CLAIM, updated: "2026-11-12T12:00:00Z" },
					{ key: KEY, status: "active", phase: "EXECUTE", claimId: "OTHER:999", updated: "2026-11-12T12:00:00Z" },
				]);
				return executionProof();
			},
		};
		const driftedIndex = makeStore({ host_adapter: indexDrift });
		await commitOk(driftedIndex);
		const indexResult = await driftedIndex.appendExecution(execRequest());
		expect(indexResult.ok, indexResult.reason).toBe(false);
		expect(fs.existsSync(executionFile())).toBe(false);

		resetFiles();
		const fixed = Date.parse(NOW);
		const near = new Date(fixed + 60_000).toISOString();
		const ctx = trustedContext({
			budget: { ...(trustedContext().budget as Record<string, unknown>), deadline: near },
		});
		let late = false;
		const clockDrift = makeStore({
			host_adapter: {
				readTrustedContext: async () => ctx,
				verifyExecution: async () => {
					late = true;
					return executionProof();
				},
			},
			clock: () => (late ? fixed + 61_000 : fixed),
		});
		await commitOk(clockDrift);
		const lateResult = await clockDrift.appendExecution(execRequest());
		expect(lateResult.code, lateResult.reason).toBe("budget-exhausted");
		expect(fs.existsSync(executionFile())).toBe(false);
	});

	it("TS05 a symlink created during the verifier is refused; no drift still writes and replays", async () => {
		const adapter: LocalSelectionHostAdapter = {
			readTrustedContext: async () => trustedContext(),
			verifyExecution: async () => {
				const outside = path.join(tmp, "during-verifier.json");
				fs.renameSync(selectionFile(), outside);
				fs.symlinkSync(outside, selectionFile(), "file");
				return executionProof();
			},
		};
		const store = makeStore({ host_adapter: adapter });
		await commitOk(store);
		const result = await store.appendExecution(execRequest());
		expect(result.ok, result.reason).toBe(false);
		expect(result.code).toBe("redirect-detected");
		expect(fs.existsSync(executionFile())).toBe(false);

		fs.unlinkSync(selectionFile()); // remove the symlink created during the verifier
		const clean = makeStore();
		await commitOk(clean);
		expect((await clean.appendExecution(execRequest())).code).toBe("written");
		expect((await clean.appendExecution(execRequest())).code).toBe("duplicate");
	});

	// TS06 (green in the PM probe) must stay green.
	it("TS06 a symlinked original selection is rejected by appendExecution", async () => {
		const store = makeStore();
		await commitOk(store);
		const outside = path.join(tmp, "outside-selection.json");
		fs.renameSync(selectionFile(), outside);
		fs.symlinkSync(outside, selectionFile(), "file");
		const result = await store.appendExecution(execRequest());
		expect(result.code, result.reason).toBe("redirect-detected");
		expect(result.host_source_verified).toBe(false);
		expect(fs.existsSync(executionFile())).toBe(false);
	});
});

// ── R2 final-boundary repairs: four gaps × three write APIs ────────────────
//
// The store now calls `readTrustedContext` TWICE per write (initial +
// finalRecheck). These L1 host fixtures inject the boundary on the LAST awaited
// callback (call 2). `fingerprint` is an immutable STRING captured at read time
// and excludes the volatile `observed_at`; freshness/deadline are still checked
// against the REAL current clock on every `verifyTrusted` read.

interface StagedHostOptions {
	transform?: (n: number, base: TrustedHostContext) => TrustedHostContext;
	sideEffect?: (n: number, base: TrustedHostContext) => void;
	withVerifier?: boolean;
}

/** Multi-call-site L1 host fixture: call 1 = initial, call 2 = finalRecheck. */
function stagedAdapter(opts: StagedHostOptions = {}): {
	adapter: LocalSelectionHostAdapter;
	calls: () => number;
} {
	const base = trustedContext();
	let n = 0;
	const adapter: LocalSelectionHostAdapter = {
		readTrustedContext: async () => {
			n += 1;
			opts.sideEffect?.(n, base);
			return opts.transform === undefined ? base : opts.transform(n, base);
		},
	};
	if (opts.withVerifier === true) adapter.verifyExecution = async () => executionProof();
	return { adapter, calls: () => n };
}

function dispFile(ref = "disp:R2:1"): string {
	return storedRecordPath(root, KEY, "pm", undefined, ref, DISPOSITION_FILE_SUFFIX);
}

function dispReq(ref = "disp:R2:1"): {
	source: "pm";
	disposition_ref: string;
	disposition: Record<string, unknown>;
} {
	return { source: "pm" as const, disposition_ref: ref, disposition: dispositionValue({ disposition_ref: ref }) };
}

describe("R2 final-boundary repairs (TS01..TS04, all three write APIs)", () => {
	// ── R1-TS01: a legal observed_at refresh is NOT semantic/material/identity
	// drift, but freshness/deadline are still enforced at the REAL clock. ──
	it("R2-TS01 fresh observed_at alone commits (semantic snapshot excludes the volatile time)", async () => {
		const t = Date.now() - 100;
		const { adapter, calls } = stagedAdapter({
			transform: (n, base) => ({ ...base, observed_at: new Date(t + n).toISOString() }),
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.commitSelection(commitRequest());
		expect(r.code, r.reason).toBe("written");
		expect(r.ok).toBe(true);
		expect(r.host_source_verified).toBe(true);
		expect(calls()).toBe(2);
	});

	it("R2-TS01 fresh observed_at alone saves a disposition (same real-clock freshness)", async () => {
		const t = Date.now() - 100;
		const { adapter, calls } = stagedAdapter({
			transform: (n, base) => ({ ...base, observed_at: new Date(t + n).toISOString() }),
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.saveDisposition(dispReq());
		expect(r.code, r.reason).toBe("written");
		expect(r.ok).toBe(true);
		expect(calls()).toBe(2);
	});

	it("R2-TS01 an in-place nested mutation at the final callback is caught by the immutable snapshot", async () => {
		// The SAME object is returned both times; a post-callback re-projection of
		// the initial context would show the mutated value too and hide the drift.
		const { adapter, calls } = stagedAdapter({
			sideEffect: (n, base) => {
				if (n === 2) base.expected.basis_digest = "sha256:MUTATED-IN-PLACE";
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.commitSelection(commitRequest());
		expect(r.ok, r.reason).toBe(false);
		expect(r.code).toBe("trusted-context-refused");
		expect(fs.existsSync(selectionFile())).toBe(false);
		expect(calls()).toBe(2);
	});

	it("R2-TS01 freshness is NOT deleted: a stale observed_at at the final read is refused", async () => {
		const { adapter } = stagedAdapter({
			transform: (n, base) => (n === 2 ? { ...base, observed_at: "2000-01-01T00:00:00Z" } : base),
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.commitSelection(commitRequest());
		expect(r.ok, r.reason).toBe(false);
		expect(r.code).toBe("trusted-context-refused");
		expect(fs.existsSync(selectionFile())).toBe(false);
	});

	it("R2-TS01 the final recheck re-reads the REAL clock against the deadline", async () => {
		const fixed = Date.parse(NOW);
		const near = new Date(fixed + 60_000).toISOString();
		const { adapter, calls } = stagedAdapter({
			transform: (_n, base) => ({
				...base,
				budget: { ...(base.budget as Record<string, unknown>), deadline: near },
			}),
		});
		const store = makeStore({ host_adapter: adapter, clock: () => (calls() >= 2 ? fixed + 61_000 : fixed) });
		const r = await store.commitSelection(commitRequest());
		expect(r.ok, r.reason).toBe(false);
		expect(r.code).toBe("budget-exhausted");
		expect(fs.existsSync(selectionFile())).toBe(false);
	});

	// ── R1-TS02: a bad existing that appears during the FINAL await is refused
	// and its bytes are preserved; no pre-await existing classification is reused. ──
	it("R2-TS02 corrupt existing appears at the final callback: commitSelection refuses, bytes kept", async () => {
		const { adapter, calls } = stagedAdapter({
			sideEffect: (n) => {
				if (n === 2) {
					const file = selectionFile();
					fs.mkdirSync(path.dirname(file), { recursive: true });
					fs.writeFileSync(file, "CORRUPT FINAL TARGET", "utf8");
				}
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.commitSelection(commitRequest());
		expect(r.code, r.reason).toBe("existing-corrupt");
		expect(r.ok).toBe(false);
		expect(r.host_source_verified).toBe(false);
		expect(fs.readFileSync(selectionFile(), "utf8")).toBe("CORRUPT FINAL TARGET");
		expect(calls()).toBe(2);
	});

	it("R2-TS02 corrupt disposition appears at the final callback: saveDisposition refuses, bytes kept", async () => {
		const { adapter } = stagedAdapter({
			sideEffect: (n) => {
				if (n === 2) {
					const file = dispFile();
					fs.mkdirSync(path.dirname(file), { recursive: true });
					fs.writeFileSync(file, "CORRUPT DISPOSITION", "utf8");
				}
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.saveDisposition(dispReq());
		expect(r.code, r.reason).toBe("existing-corrupt");
		expect(r.ok).toBe(false);
		expect(fs.readFileSync(dispFile(), "utf8")).toBe("CORRUPT DISPOSITION");
	});

	it("R2-TS02 corrupt execution existing appears at the final callback: effect-unknown is retained", async () => {
		const plain = makeStore();
		await commitOk(plain);
		const { adapter } = stagedAdapter({
			withVerifier: true,
			sideEffect: (n) => {
				if (n === 2) {
					const file = executionFile();
					fs.mkdirSync(path.dirname(file), { recursive: true });
					fs.writeFileSync(file, "CORRUPT EXECUTION", "utf8");
				}
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.appendExecution(execRequest());
		expect(r.code, r.reason).toBe("existing-corrupt");
		expect(r.ok).toBe(false);
		expect(r.reason).toMatch(/action may already have been performed/);
		expect(fs.readFileSync(executionFile(), "utf8")).toBe("CORRUPT EXECUTION");
	});

	// ── R1-TS03: a real directory rename + junction during the FINAL awaited
	// context read is refused; no outside write; no await after the final check. ──
	it("R2-TS03 rename + junction at the final callback: commitSelection refuses, no outside write", async () => {
		const out = path.join(tmp, "r2-out-commit");
		const held = path.join(tmp, "r2-held-commit");
		fs.mkdirSync(out, { recursive: true });
		const { adapter, calls } = stagedAdapter({
			sideEffect: (n) => {
				if (n === 2) {
					const base = path.dirname(selectionFile());
					fs.renameSync(base, held);
					fs.symlinkSync(out, base, "junction");
				}
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.commitSelection(commitRequest());
		expect(r.code, r.reason).toBe("redirect-detected");
		expect(r.ok).toBe(false);
		expect(fs.existsSync(path.join(out, path.basename(selectionFile())))).toBe(false);
		expect(calls()).toBe(2);
	});

	it("R2-TS03 rename + junction at the final callback: appendExecution refuses, no outside write", async () => {
		const plain = makeStore();
		await commitOk(plain);
		const out = path.join(tmp, "r2-out-exec");
		const held = path.join(tmp, "r2-held-exec");
		fs.mkdirSync(out, { recursive: true });
		const { adapter } = stagedAdapter({
			withVerifier: true,
			sideEffect: (n) => {
				if (n === 2) {
					const base = path.dirname(executionFile());
					fs.renameSync(base, held);
					fs.symlinkSync(out, base, "junction");
				}
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.appendExecution(execRequest());
		expect(r.ok, r.reason).toBe(false);
		expect(r.code).toBe("redirect-detected");
		expect(r.reason).toMatch(/action may already have been performed/);
		expect(fs.existsSync(path.join(out, path.basename(executionFile())))).toBe(false);
	});

	// ── R1-TS04: a verified DUPLICATE must still go through the final trusted
	// context / index / real clock / budget / stop / path / record recheck. ──
	it("R2-TS04 a duplicate selection still rechecks a stop at the final read (no early return)", async () => {
		const plain = makeStore();
		await commitOk(plain);
		const { adapter, calls } = stagedAdapter({
			sideEffect: (n, base) => {
				if (n === 2) base.stop_signals = [{ signal_ref: "stop:r2", kind: "user-stop" }];
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.commitSelection(commitRequest());
		expect(r.ok, r.reason).toBe(false);
		expect(r.code, r.reason).toBe("stop-scope-blocked");
		expect(r.code).not.toBe("duplicate");
		expect(calls()).toBe(2);
	});

	it("R2-TS04 a duplicate disposition still rechecks a stop at the final read", async () => {
		const plain = makeStore();
		expect((await plain.saveDisposition(dispReq())).code).toBe("written");
		const { adapter, calls } = stagedAdapter({
			sideEffect: (n, base) => {
				if (n === 2) base.stop_signals = [{ signal_ref: "stop:r2", kind: "user-stop" }];
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.saveDisposition(dispReq());
		expect(r.ok, r.reason).toBe(false);
		expect(r.code).not.toBe("duplicate");
		expect(calls()).toBe(2);
	});

	it("R2-TS04 appendExecution duplicate keeps the same ordering + effect-unknown", async () => {
		const plain = makeStore();
		await commitOk(plain);
		expect((await plain.appendExecution(execRequest())).code).toBe("written");
		const { adapter } = stagedAdapter({
			withVerifier: true,
			sideEffect: (n, base) => {
				if (n === 2) base.stop_signals = [{ signal_ref: "stop:r2", kind: "user-stop" }];
			},
		});
		const store = makeStore({ host_adapter: adapter });
		const r = await store.appendExecution(execRequest());
		expect(r.ok, r.reason).toBe(false);
		expect(r.reason).toMatch(/action may already have been performed/);
	});

	// Legal positives are preserved (no assertion downgrade).
	it("R2 positives: clean duplicate selection and disposition still pass the final recheck", async () => {
		const store = makeStore();
		await commitOk(store);
		expect((await store.commitSelection(commitRequest())).code).toBe("duplicate");
		expect((await store.saveDisposition(dispReq())).code).toBe("written");
		expect((await store.saveDisposition(dispReq())).code).toBe("duplicate");
	});
});

// ── R3 repair: immutable correlated execution proof + volatile-timestamp replay ──
//
// Two S1 R2 neighbor findings: (P1) an adapter-owned MUTABLE proof survived the
// final host await and was written directly, so the last context callback could
// swap identity / promote unknown; (P2) `observed_at` was excluded only from the
// context fingerprint, not from the record duplicate semantic key, so a legal
// cross-call freshness refresh produced a false `conflict`. Freshness/deadline/
// current-budget/stop and bad-existing protection are unchanged and re-asserted.

interface RefreshingHost {
	store: LocalSelectionStore;
	bumpObservedAt: (iso: string) => void;
}

/** L1 host fixture: `observed_at` is a live value legally refreshed BETWEEN
 *  calls (constant within one write, both context reads see the same value).
 *  `verifyExecution` returns a fresh proof; no context callback mutates it. */
function refreshingHost(): RefreshingHost {
	let observed = trustedContext().observed_at;
	const adapter: LocalSelectionHostAdapter = {
		readTrustedContext: async () => trustedContext({ observed_at: observed }),
		verifyExecution: async () => executionProof(),
	};
	return {
		store: makeStore({ host_adapter: adapter }),
		bumpObservedAt: (iso: string) => {
			observed = iso;
		},
	};
}

function freshObservedAt(): string {
	return new Date(Date.now() - 5).toISOString();
}

function diskRecord(file: string): Record<string, unknown> | null {
	return fs.existsSync(file) ? (JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>) : null;
}

describe("R3 (immutable correlated proof + volatile observed_at replay)", () => {
	// N00 — clean positive control.
	it("R3-N00 clean execution and exact replay positive control", async () => {
		const store = makeStore();
		await commitOk(store);
		const a = await store.appendExecution(execRequest());
		const b = await store.appendExecution(execRequest());
		expect([a.code, b.code]).toEqual(["written", "duplicate"]);
		expect(b.host_source_verified).toBe(true);
	});

	// N01 — selection observed_at-only cross-call refresh remains duplicate.
	it("R3-N01 observed_at-only refresh between identical selections is duplicate, bytes preserved", async () => {
		const h = refreshingHost();
		const first = await h.store.commitSelection(commitRequest());
		expect(first.code, first.reason).toBe("written");
		const before = fs.readFileSync(selectionFile(), "utf8");
		h.bumpObservedAt(freshObservedAt());
		const r = await h.store.commitSelection(commitRequest());
		expect(r.code, r.reason).toBe("duplicate");
		expect(r.host_source_verified).toBe(true);
		expect(fs.readFileSync(selectionFile(), "utf8")).toBe(before);
	});

	// N02 — execution observed_at-only cross-call refresh remains duplicate.
	it("R3-N02 observed_at-only refresh between identical executions is duplicate, bytes preserved", async () => {
		const h = refreshingHost();
		expect((await h.store.commitSelection(commitRequest())).code).toBe("written");
		const first = await h.store.appendExecution(execRequest());
		expect(first.code, first.reason).toBe("written");
		const before = fs.readFileSync(executionFile(), "utf8");
		h.bumpObservedAt(freshObservedAt());
		const r = await h.store.appendExecution(execRequest());
		expect(r.code, r.reason).toBe("duplicate");
		expect(r.host_source_verified).toBe(true);
		expect(fs.readFileSync(executionFile(), "utf8")).toBe(before);
	});

	// disposition — observed_at-only refresh replay is duplicate; a real semantic
	// field change is still conflict (the volatile timestamp was NOT dropped wholesale).
	it("R3 disposition observed_at-only refresh is duplicate; a real field change is conflict", async () => {
		const h = refreshingHost();
		const ref = "disp:R2:1";
		const first = await h.store.saveDisposition(dispReq(ref));
		expect(first.code, first.reason).toBe("written");
		const before = fs.readFileSync(dispFile(ref), "utf8");
		h.bumpObservedAt(freshObservedAt());
		const base = dispositionValue({ disposition_ref: ref });
		const refreshed = {
			...base,
			binding: { ...(base.binding as Record<string, unknown>), observed_at: freshObservedAt() },
		};
		const dup = await h.store.saveDisposition({ source: "pm", disposition_ref: ref, disposition: refreshed });
		expect(dup.code, dup.reason).toBe("duplicate");
		expect(fs.readFileSync(dispFile(ref), "utf8")).toBe(before);
		const changed = { ...refreshed, gap_refs: ["gap:CHANGED"] };
		const conflict = await h.store.saveDisposition({ source: "pm", disposition_ref: ref, disposition: changed });
		expect(conflict.code, conflict.reason).toBe("conflict");
		expect(fs.readFileSync(dispFile(ref), "utf8")).toBe(before);
	});

	// A real semantic change (not just a timestamp) is NOT swallowed as duplicate.
	it("R3-N01b a real choice change with a refreshed observed_at is still conflict, bytes preserved", async () => {
		const h = refreshingHost();
		expect((await h.store.commitSelection(commitRequest())).code).toBe("written");
		const before = fs.readFileSync(selectionFile(), "utf8");
		h.bumpObservedAt(freshObservedAt());
		const r = await h.store.commitSelection(
			commitRequest({ selection: selectionFields({ selected_action: "narrow", selected_basis_id: "b2" }) }),
		);
		expect(r.code, r.reason).toBe("conflict");
		expect(fs.readFileSync(selectionFile(), "utf8")).toBe(before);
	});

	// N03 — a context callback cannot swap the already-correlated proof identity.
	it("R3-N03 last context callback cannot swap already-correlated proof identity", async () => {
		const plain = makeStore();
		await commitOk(plain);
		const shared = executionProof();
		let n = 0;
		const adapter: LocalSelectionHostAdapter = {
			readTrustedContext: async () => {
				n += 1;
				if (n === 2)
					Object.assign(shared, {
						action_ref: "tool_call:OTHER",
						result_ref: "tool_result:OTHER",
						executor: "executor:OTHER",
					});
				return trustedContext();
			},
			verifyExecution: async () => shared,
		};
		const store = makeStore({ host_adapter: adapter });
		const r = await store.appendExecution(execRequest());
		const disk = diskRecord(executionFile());
		const identityMatches =
			disk !== null &&
			disk.action_ref === execRequest().action_ref &&
			disk.result_ref === execRequest().result_ref &&
			disk.executor === execRequest().executor;
		// Refuse, OR write the original request-correlated immutable evidence — never the swapped identity.
		expect(!r.ok || identityMatches).toBe(true);
		expect(disk?.action_ref).not.toBe("tool_call:OTHER");
		expect(disk?.executor).not.toBe("executor:OTHER");
	});

	// N04 — a context callback cannot promote a verifier-unknown proof to known.
	it("R3-N04 final callback cannot promote immutable verifier-unknown proof to known", async () => {
		const plain = makeStore();
		await commitOk(plain);
		const shared = executionProof({ effect_state: "unknown" });
		let n = 0;
		const adapter: LocalSelectionHostAdapter = {
			readTrustedContext: async () => {
				n += 1;
				if (n === 2) shared.effect_state = "known";
				return trustedContext();
			},
			verifyExecution: async () => shared,
		};
		const store = makeStore({ host_adapter: adapter });
		const r = await store.appendExecution(execRequest());
		const disk = diskRecord(executionFile());
		expect(!r.ok || disk?.effect_state === "unknown").toBe(true);
		expect(disk?.effect_state).not.toBe("known");
	});

	// A legitimate verifier-unknown proof still writes unknown (no false refusal).
	it("R3 a legitimate unknown proof still writes effect_state=unknown, then duplicates", async () => {
		const store = makeStore({ host_adapter: hostAdapter({ proof: executionProof({ effect_state: "unknown" }) }) });
		await commitOk(store);
		const a = await store.appendExecution(execRequest());
		expect(a.code, a.reason).toBe("written");
		expect(a.effect_state).toBe("unknown");
		expect(diskRecord(executionFile())?.effect_state).toBe("unknown");
		const b = await store.appendExecution(execRequest());
		expect(b.code, b.reason).toBe("duplicate");
	});

	// P2 did not relax real freshness/deadline/budget/stop checks or bad-existing protection.
	it("R3 stale/exhausted/stopped replay and corrupt existing are still refused after a refresh", async () => {
		const expiredBudget = {
			...(trustedContext().budget as Record<string, unknown>),
			deadline: new Date(Date.now() - 60_000).toISOString(),
		};
		for (const [label, ctx, expected] of [
			["stale", trustedContext({ observed_at: "2000-01-01T00:00:00Z" }), "trusted-context-refused"],
			["expired", trustedContext({ budget: expiredBudget }), "budget-exhausted"],
			["stop", trustedContext({ stop_signals: [{ signal_ref: "s", kind: "user-stop" }] }), "stop-scope-blocked"],
		] as const) {
			const ref = `local:R3:${label}`;
			expect((await makeStore().commitSelection(commitRequest({ local_ref: ref }))).code).toBe("written");
			const before = fs.readFileSync(selectionFile(ref), "utf8");
			const r = await makeStore({ host_adapter: hostAdapter({ ctx }) }).commitSelection(
				commitRequest({ local_ref: ref }),
			);
			expect(r.code, `${label}: ${r.reason}`).toBe(expected);
			expect(r.ok).toBe(false);
			expect(fs.readFileSync(selectionFile(ref), "utf8")).toBe(before);
		}
		const h = refreshingHost();
		const cref = "local:R3:corrupt";
		await h.store.commitSelection(commitRequest({ local_ref: cref }));
		h.bumpObservedAt(freshObservedAt());
		fs.writeFileSync(selectionFile(cref), "CORRUPT R3", "utf8");
		const r = await h.store.commitSelection(commitRequest({ local_ref: cref }));
		expect(r.code, r.reason).toBe("existing-corrupt");
		expect(fs.readFileSync(selectionFile(cref), "utf8")).toBe("CORRUPT R3");
	});
});

// ── R4 repair: exact request↔proof observed_effect correlation (RV1 F1) ──

describe("R4 (exact observed_effect correlation)", () => {
	it("R4-F1 a different proof observed_effect is refused after the verifier ran", async () => {
		const store = makeStore({
			host_adapter: hostAdapter({ proof: executionProof({ observed_effect: "different verified observation" }) }),
		});
		await commitOk(store);
		const r = await store.appendExecution(execRequest());
		expect(r.code, r.reason).toBe("verifier-unproven");
		expect(r.ok).toBe(false);
		expect(r.host_source_verified).toBe(false);
		expect(r.reason).toMatch(/observed_effect/);
		expect(r.reason).toMatch(/action may already have been performed/);
		expect(r.reason).toMatch(/reconcile read-only/);
		expect(fs.existsSync(executionFile())).toBe(false);
	});

	it("R4-F1 an exactly matching known proof writes known, not a model claim", async () => {
		const store = makeStore({ host_adapter: hostAdapter({ proof: executionProof() }) });
		await commitOk(store);
		const r = await store.appendExecution(execRequest({ claimed_effect_state: "unknown" }));
		expect(r.code, r.reason).toBe("written");
		expect(r.host_source_verified).toBe(true);
		expect(r.effect_state).toBe("known");
		const disk = diskRecord(executionFile());
		expect(disk?.observed_effect).toBe("two reads recorded");
		expect(disk?.effect_state).toBe("known");
	});

	it("R4-F1 an exactly matching unknown proof stays unknown, not claimed known", async () => {
		const store = makeStore({
			host_adapter: hostAdapter({ proof: executionProof({ effect_state: "unknown" }) }),
		});
		await commitOk(store);
		const r = await store.appendExecution(execRequest({ claimed_effect_state: "known" }));
		expect(r.code, r.reason).toBe("written");
		expect(r.host_source_verified).toBe(true);
		expect(r.effect_state).toBe("unknown");
		const disk = diskRecord(executionFile());
		expect(disk?.observed_effect).toBe("two reads recorded");
		expect(disk?.effect_state).toBe("unknown");
	});

	it("R4-F1 the final context callback cannot pollute the correlated effect snapshot", async () => {
		const plain = makeStore();
		await commitOk(plain);
		const shared = executionProof();
		let contextCalls = 0;
		const adapter: LocalSelectionHostAdapter = {
			readTrustedContext: async () => {
				contextCalls += 1;
				if (contextCalls === 2) shared.observed_effect = "swapped after verifier";
				return trustedContext();
			},
			verifyExecution: async () => shared,
		};
		const store = makeStore({ host_adapter: adapter });
		const r = await store.appendExecution(execRequest());
		expect(contextCalls).toBe(2);
		expect(shared.observed_effect).toBe("swapped after verifier");
		expect(r.code, r.reason).toBe("written");
		expect(r.host_source_verified).toBe(true);
		const disk = diskRecord(executionFile());
		expect(disk?.observed_effect).toBe("two reads recorded");
		expect(disk?.observed_effect).not.toBe("swapped after verifier");
		expect(disk?.effect_state).toBe("known");
	});
});
