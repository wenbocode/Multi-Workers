import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	RuntimeExecutionController,
	type RuntimeExecutionResult,
	type RuntimeTargetAuthorization,
	type RuntimeToolCall,
	type RuntimeToolResult,
	runtimeExecutionExecutor,
} from "../../src/extensions/agent-team-loop/pm/runtime-execution.ts";
import type {
	HostBinding,
	LocalSource,
	PmDisposition,
} from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import {
	atomicWriteJson,
	type CommitSelectionRequest,
	type ExecutionVerificationRequest,
	LocalSelectionStore,
	type TrustedHostContext,
} from "../../src/extensions/agent-team-loop/shared/local-selection-store.ts";
import { createHarness, type Harness } from "./harness.ts";

/** Direct observer tests inject HOST facts, not production hooks. The harness
 * case additionally proves real extension call/result ordering on a faux
 * provider with real bytes and the SAME frozen store, without paid/network I/O. */
const roots: string[] = [];
const sessions: Harness[] = [];
afterEach(() => {
	vi.restoreAllMocks();
	for (const session of sessions.splice(0)) session.cleanup();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

function fixture(source: LocalSource = "pm") {
	const project = fs.mkdtempSync(path.join(os.tmpdir(), "t06-execution-"));
	roots.push(project);
	const root = path.join(project, ".agenticdoc");
	fs.mkdirSync(root);
	fs.mkdirSync(path.join(project, ".mw"));
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		"# Index Parallel\n| key-a | active | EXECUTE | host:123 | | test | now |\n",
	);
	fs.mkdirSync(path.join(project, "src"));
	fs.writeFileSync(path.join(project, "src", "a.txt"), "before-a");
	fs.writeFileSync(path.join(project, "src", "b.txt"), "before-b");
	const now = new Date().toISOString();
	let binding: HostBinding | undefined = {
		role: source === "pm" ? "pm" : "coding",
		owner: "host:123",
		claim_id: "host:123",
		key: "key-a",
		binding_version: "binding-1",
		observed_at: now,
		...(source === "worker-local" ? { task_key: "task-1", run_id: "run-1" } : {}),
	};
	let authorization: RuntimeTargetAuthorization | undefined = {
		run_id: "run-1",
		targets: ["src/b.txt", "src/a.txt"],
		write_face: ["src/a.txt", "src/b.txt"],
	};
	const context: TrustedHostContext = {
		self_claim_id: "host:123",
		binding_version: "binding-1",
		role: source === "pm" ? "pm" : "coding",
		observed_at: now,
		...(source === "worker-local" ? { task_key: "task-1", run_id: "run-1" } : {}),
		expected: {
			matter_ref: "matter-1",
			matter_version: "v1",
			material_digest: "material-1",
			basis_digest: "basis-1",
			budget_ref: "budget-1",
		},
		budget: {
			schema_version: 1,
			budget_ref: "budget-1",
			matter_ref: "matter-1",
			deadline: new Date(Date.now() + 3600000).toISOString(),
			max_steps: 100,
			steps_consumed: 0,
			no_progress_limit: 5,
			no_progress_count: 0,
			remaining_cost: 100,
			cost_consumed: 0,
			source_refs: ["host-fixture:finite-budget"],
		},
		budget_preflight: {
			granted: true,
			reserved_steps: 1,
			reserved_cost: 1,
			remaining_after_steps: 99,
			remaining_after_cost: 99,
			reason: "granted",
		},
	};
	const request: CommitSelectionRequest = {
		source,
		local_ref: "local-1",
		...(source === "worker-local" ? { task_key: "task-1", run_id: "run-1" } : {}),
		selection: {
			matter_ref: "matter-1",
			matter_version: "v1",
			material: {
				material_ref: "material",
				fields: { task_goal: "verify observed bytes" },
				digest: "material-1",
				evidence_refs: ["host-fixture:card"],
			},
			preparation: {
				prepared_at: now,
				digest: "basis-1",
				basis_catalog: [
					{ id: "b1", text: "host evidence", material_refs: ["task_goal"], applies_to: ["continue"] },
				],
			},
			candidates: { version: "v1", ids: ["continue"] },
			selected_action: "continue",
			selected_basis_id: "b1",
			created_at: now,
		},
	};
	let failExecution = false;
	let failDisposition = false;
	let failAfterExecutionWrite = false;
	let writes = 0;
	let disposition: PmDisposition | undefined;
	let controller: RuntimeExecutionController;
	const verifyRequests: ExecutionVerificationRequest[] = [];
	const store = new LocalSelectionStore({
		agenticdoc_root: root,
		key: "key-a",
		host_adapter: {
			readTrustedContext: async () => context,
			verifyExecution: async (req) => {
				verifyRequests.push(structuredClone(req));
				return controller.verifyExecution(req);
			},
		},
		atomic_write: (file, value) => {
			writes += 1;
			if (
				(failExecution && file.endsWith(".execution.json")) ||
				(failDisposition && file.endsWith(".disposition.json"))
			)
				throw new Error("fixture EIO");
			atomicWriteJson(file, value);
			if (failAfterExecutionWrite && file.endsWith(".execution.json"))
				throw new Error("fixture response lost after rename");
		},
	});
	controller = new RuntimeExecutionController({
		store,
		project_root: project,
		readBinding: () => binding,
		readAuthorization: () => authorization,
		readDisposition: (observed) =>
			disposition ?? {
				schema_version: 1,
				disposition_ref: observed.disposition_ref,
				feedback_ref: "feedback-1",
				matter_ref: "matter-1",
				kind: "collect-evidence",
				owner: "host:123",
				binding: observed.selection.host_binding,
				goal_ref: "goal:verify-bytes",
				gap_refs: ["gap:missing-evidence"],
				basis_refs: [observed.call.toolCallId, observed.proof.result_ref],
				planned_action: {
					tool: observed.call.tool,
					scope_ref: "host-write-face",
					read_only: observed.call.tool === "read",
				},
				expected_result: "actual byte manifest",
				result_consumer: "owning-pm:review",
				budget_ref: "budget-1",
				status: "observed",
			},
	});
	const call = (id = "actual-call-1"): RuntimeToolCall => ({
		source,
		local_ref: "local-1",
		toolCallId: id,
		tool: "write",
	});
	const result = (id = "actual-call-1"): RuntimeToolResult => ({
		toolCallId: id,
		local_ref: "local-1",
		run_id: "run-1",
		executor: runtimeExecutionExecutor("run-1", id),
		result_ref: `host-result:${id}`,
		isError: false,
		completion: "complete",
	});
	const mutate = () => {
		fs.writeFileSync(path.join(project, "src", "a.txt"), "after-a");
		fs.writeFileSync(path.join(project, "src", "b.txt"), "after-b");
	};
	const bind = async () => {
		const committed = await controller.commitSelection(request);
		expect(committed.code, JSON.stringify(committed)).toBe("selection-bound");
		expect(committed.store_result?.host_source_verified).toBe(true);
	};
	const observe = async () => {
		await bind();
		expect(controller.observeToolCall(call()).code).toBe("call-observed");
		mutate();
		expect(controller.observeToolResult(result()).code).toBe("result-observed");
	};
	const read = () => store.readExecution({ source, ref: "local-1", task_key: request.task_key });
	return {
		project,
		root,
		source,
		request,
		store,
		controller,
		call,
		result,
		mutate,
		bind,
		observe,
		read,
		context,
		verifyRequests,
		setBinding: (next: HostBinding | undefined) => {
			binding = next;
		},
		binding: () => structuredClone(binding),
		setAuthorization: (next: RuntimeTargetAuthorization | undefined) => {
			authorization = next;
		},
		authorization: () => structuredClone(authorization),
		setDisposition: (next: PmDisposition) => {
			disposition = next;
		},
		failExecution: () => {
			failExecution = true;
		},
		failDisposition: () => {
			failDisposition = true;
		},
		failAfterExecutionWrite: () => {
			failAfterExecutionWrite = true;
		},
		writes: () => writes,
	};
}

function manifestDigest(project: string, names = ["src/a.txt", "src/b.txt"]): string {
	const manifest = [...names].sort().map((name) => ({
		path: name,
		state: "file",
		sha256: createHash("sha256")
			.update(fs.readFileSync(path.join(project, name)))
			.digest("hex"),
	}));
	return `sha256:${createHash("sha256").update(JSON.stringify(manifest)).digest("hex")}`;
}

describe("T06-D real frozen-store action provenance", () => {
	it.each(["pm", "worker-local"] as const)(
		"%s selection → observed action/result → independent bytes → same-store execution/read",
		async (source) => {
			const f = fixture(source);
			await f.observe();
			const saved = await f.controller.appendExecution(f.call().toolCallId);
			expect(saved.store_result?.code, JSON.stringify(saved)).toBe("written");
			expect(saved.effect_state).toBe("known");
			expect(f.verifyRequests).toHaveLength(1);
			expect(f.read().record).toMatchObject({
				action_ref: f.call().toolCallId,
				result_ref: f.result().result_ref,
				executor: f.result().executor,
				target_digest: manifestDigest(f.project),
				effect_state: "known",
			});
			expect(f.read().verification).toBe("shape-only");
			expect(f.store.readSelection({ source, ref: "local-1", task_key: f.request.task_key }).record).toMatchObject({
				action_state: "planned",
				business_completed: false,
			});
			expect(f.read().record?.observed_effect).toContain("business-correctness=unverified");
		},
	);

	it("saves a real host-built observed disposition through the same store, not a QG/gate/sign", async () => {
		const f = fixture();
		await f.observe();
		expect((await f.controller.saveDisposition(f.call().toolCallId, "disp-1")).code).toBe("disposition-unproven");
		expect((await f.controller.appendExecution(f.call().toolCallId)).store_result?.ok).toBe(true);
		const saved = await f.controller.saveDisposition(f.call().toolCallId, "disp-1");
		expect(saved.store_result?.code, JSON.stringify(saved)).toBe("written");
		expect(f.store.readDisposition({ source: "pm", ref: "disp-1" }).record).toMatchObject({
			status: "observed",
			kind: "collect-evidence",
			basis_refs: [f.call().toolCallId, f.result().result_ref],
		});
		expect((await f.controller.saveDisposition(f.call().toolCallId, "disp-1")).store_result?.code).toBe("duplicate");
		expect(fs.existsSync(path.join(f.root, "_autopilot"))).toBe(false);
	});

	it("supports a genuinely new target absent at call time, not a pre-existing-file capability", async () => {
		const f = fixture();
		fs.unlinkSync(path.join(f.project, "src", "a.txt"));
		await f.observe();
		expect((await f.controller.appendExecution(f.call().toolCallId)).store_result?.code).toBe("written");
	});

	it("same-controller duplicate commit stays idempotent without issuing a new action", async () => {
		const f = fixture();
		await f.bind();
		const rebound = await f.controller.commitSelection(f.request);
		expect(rebound.store_result?.code).toBe("duplicate");
		expect(f.controller.observeToolCall(f.call()).code).toBe("call-observed");
		expect(f.controller.observeToolCall(f.call()).code).toBe("duplicate");
	});

	it("restart/lost-history duplicate selection is a recovery clue, not permission to replay", async () => {
		const f = fixture();
		expect((await f.store.commitSelection(f.request)).code).toBe("written");
		const rebound = await f.controller.commitSelection(f.request);
		expect(rebound.code).toBe("reconciliation-required");
		expect(rebound.store_result?.code).toBe("duplicate");
		expect(f.controller.observeToolCall(f.call()).code).toBe("selection-unproven");
		expect(f.read().status).toBe("absent");
	});

	it("selection alone, forged call strings and existing correct bytes never become proof", async () => {
		const f = fixture();
		await f.bind();
		const request: ExecutionVerificationRequest = {
			key: "key-a",
			source: "pm",
			local_ref: "local-1",
			action_ref: "tool_call:write:999",
			result_ref: "tool_result:999",
			executor: "looks-real",
			observed_effect: "existing bytes",
			binding: f.binding() as HostBinding,
		};
		expect(await f.controller.verifyExecution(request)).toBeUndefined();
		expect((await f.controller.appendExecution(request.action_ref)).code).toBe("unknown-call");
		expect(f.read().status).toBe("absent");
	});

	it("does not treat a shape-only recovered selection as a live observed capability", async () => {
		const f = fixture();
		expect((await f.store.commitSelection(f.request)).ok).toBe(true);
		expect(f.controller.observeToolCall(f.call()).code).toBe("selection-unproven");
		expect(f.writes()).toBe(1);
	});

	it("failed selection write cannot seed the observer", async () => {
		const f = fixture();
		f.context.stop_signals = [{ kind: "user-stop", signal_ref: "real-host-stop" }];
		expect((await f.controller.commitSelection(f.request)).store_result?.code).toBe("stop-scope-blocked");
		expect(f.controller.observeToolCall(f.call()).code).toBe("selection-unproven");
	});

	it("missing result stays unknown and reconciliation is read-only", async () => {
		const f = fixture();
		await f.bind();
		f.controller.observeToolCall(f.call());
		f.mutate();
		const before = f.writes();
		const saved = await f.controller.appendExecution(f.call().toolCallId);
		expect(saved.code).toBe("result-missing");
		expect(saved.effect_state).toBe("unknown");
		expect(saved.recovery?.current_targets).toHaveLength(2);
		expect(saved.replay_allowed).toBe(false);
		expect(f.writes()).toBe(before);
		expect(f.verifyRequests).toHaveLength(0);
	});

	it("error results retain the actual partial bytes but produce no known proof or execution", async () => {
		const f = fixture();
		await f.bind();
		f.controller.observeToolCall(f.call());
		f.mutate();
		expect(f.controller.observeToolResult({ ...f.result(), isError: true }).code).toBe("result-error");
		const saved = await f.controller.appendExecution(f.call().toolCallId);
		expect(saved.code).toBe("result-error");
		expect(saved.effect_state).toBe("unknown");
		expect(fs.readFileSync(path.join(f.project, "src/a.txt"), "utf8")).toBe("after-a");
		expect(f.read().status).toBe("absent");
	});

	it("a delivered result with unknown completion is not silently classified as unexecuted or known", async () => {
		const f = fixture();
		await f.bind();
		f.controller.observeToolCall(f.call());
		f.mutate();
		expect(f.controller.observeToolResult({ ...f.result(), completion: "unknown" }).code).toBe("result-unknown");
		const saved = await f.controller.appendExecution(f.call().toolCallId);
		expect(saved.code).toBe("result-unknown");
		expect(saved.effect_state).toBe("unknown");
		expect(saved.recovery?.current_targets).toHaveLength(2);
		expect(f.read().status).toBe("absent");
	});

	it("an old result ref cannot be reused for another observed call/selection", async () => {
		const f = fixture();
		await f.observe();
		expect((await f.controller.commitSelection({ ...f.request, local_ref: "local-2" })).code).toBe("selection-bound");
		expect(f.controller.observeToolCall({ ...f.call("actual-call-2"), local_ref: "local-2" }).code).toBe(
			"call-observed",
		);
		const oldRef = { ...f.result("actual-call-2"), local_ref: "local-2", result_ref: f.result().result_ref };
		expect(f.controller.observeToolResult(oldRef).code).toBe("result-mismatch");
		expect((await f.controller.appendExecution("actual-call-2")).effect_state).toBe("unknown");
	});

	it("thrown execution/disposition store calls latch to read-only recovery", async () => {
		const f = fixture();
		await f.observe();
		const append = vi.spyOn(f.store, "appendExecution").mockRejectedValue(new Error("unexpected host failure"));
		expect((await f.controller.appendExecution(f.call().toolCallId)).code).toBe("reconciliation-required");
		expect((await f.controller.appendExecution(f.call().toolCallId)).code).toBe("reconciliation-required");
		expect(append).toHaveBeenCalledTimes(1);
		const other = fixture();
		await other.observe();
		await other.controller.appendExecution(other.call().toolCallId);
		const save = vi
			.spyOn(other.store, "saveDisposition")
			.mockRejectedValue(new Error("unexpected disposition failure"));
		expect((await other.controller.saveDisposition(other.call().toolCallId, "disp-1")).code).toBe(
			"reconciliation-required",
		);
		expect((await other.controller.saveDisposition(other.call().toolCallId, "disp-1")).code).toBe(
			"reconciliation-required",
		);
		expect(save).toHaveBeenCalledTimes(1);
	});

	it.each(["local_ref", "run_id", "executor", "result_ref"] as const)(
		"wrong host result %s never grants known",
		async (field) => {
			const f = fixture();
			await f.bind();
			f.controller.observeToolCall(f.call());
			f.mutate();
			const result = { ...f.result(), [field]: field === "result_ref" ? "" : "foreign-value" };
			expect(f.controller.observeToolResult(result).code).toBe("result-mismatch");
			expect((await f.controller.appendExecution(f.call().toolCallId)).effect_state).toBe("unknown");
			expect(f.read().status).toBe("absent");
		},
	);

	it.each(["owner", "claim_id", "key", "task_key", "run_id", "binding_version"] as const)(
		"changed worker %s invalidates the old action",
		async (field) => {
			const f = fixture("worker-local");
			await f.observe();
			f.setBinding({ ...(f.binding() as HostBinding), [field]: "foreign-value" });
			expect((await f.controller.appendExecution(f.call().toolCallId)).effect_state).toBe("unknown");
			expect(f.read().status).toBe("absent");
		},
	);

	it("old result cannot follow a binding change and does not restore old authority", async () => {
		const f = fixture();
		await f.bind();
		f.controller.observeToolCall(f.call());
		const original = f.binding();
		f.setBinding(undefined);
		expect(f.controller.observeToolResult(f.result()).code).toBe("binding-drift");
		f.setBinding(original);
		expect((await f.controller.appendExecution(f.call().toolCallId)).code).toBe("binding-drift");
	});

	it("second-target byte drift invalidates the full manifest", async () => {
		const f = fixture();
		await f.observe();
		fs.writeFileSync(path.join(f.project, "src/b.txt"), "different second target");
		const saved = await f.controller.appendExecution(f.call().toolCallId);
		expect(saved.store_result?.code).toBe("verifier-unproven");
		expect(saved.effect_state).toBe("unknown");
		expect(f.read().status).toBe("absent");
	});

	it("authorization target-set/run/write-face drift is not accepted from any later result", async () => {
		for (const drift of [
			{ run_id: "run-2", targets: ["src/a.txt", "src/b.txt"], write_face: ["src/a.txt", "src/b.txt"] },
			{ run_id: "run-1", targets: ["src/a.txt"], write_face: ["src/a.txt", "src/b.txt"] },
			{ run_id: "run-1", targets: ["src/a.txt", "src/b.txt"], write_face: ["src/a.txt"] },
		]) {
			const f = fixture();
			await f.observe();
			f.setAuthorization(drift);
			expect((await f.controller.appendExecution(f.call().toolCallId)).effect_state).toBe("unknown");
			expect(f.read().status).toBe("absent");
		}
	});

	it.each(["../outside.txt", "/absolute", "src/../a.txt", "src\\a.txt", "src/a.txt:stream", "src/NUL", "src/a.txt."])(
		"rejects noncanonical/out-of-face target %s",
		async (target) => {
			const f = fixture();
			await f.bind();
			f.setAuthorization({ run_id: "run-1", targets: [target], write_face: [target] });
			expect(f.controller.observeToolCall(f.call()).code).toBe("authorization-gap");
			expect(f.read().status).toBe("absent");
		},
	);

	it("rejects a real existing outside file and a target not included in host write face", async () => {
		const f = fixture();
		const outsideRoot = fs.mkdtempSync(path.join(os.tmpdir(), "t06-outside-"));
		roots.push(outsideRoot);
		fs.writeFileSync(path.join(outsideRoot, "outside.txt"), "real outside bytes");
		await f.bind();
		f.setAuthorization({
			run_id: "run-1",
			targets: [path.join(outsideRoot, "outside.txt")],
			write_face: [path.join(outsideRoot, "outside.txt")],
		});
		expect(f.controller.observeToolCall(f.call()).code).toBe("authorization-gap");
		f.setAuthorization({ run_id: "run-1", targets: ["src/a.txt", "src/b.txt"], write_face: ["src/a.txt"] });
		expect(f.controller.observeToolCall(f.call()).code).toBe("authorization-gap");
	});

	it.each(["inside", "outside"] as const)(
		"rejects %s directory junction/symlink and file hardlink targets",
		async (location) => {
			const f = fixture();
			const destination =
				location === "inside" ? path.join(f.project, "real") : fs.mkdtempSync(path.join(os.tmpdir(), "t06-link-"));
			if (location === "outside") roots.push(destination);
			else fs.mkdirSync(destination);
			fs.writeFileSync(path.join(destination, "a.txt"), "linked bytes");
			fs.symlinkSync(destination, path.join(f.project, "redirect"), "junction");
			await f.bind();
			f.setAuthorization({ run_id: "run-1", targets: ["redirect/a.txt"], write_face: ["redirect/a.txt"] });
			expect(f.controller.observeToolCall(f.call()).code).toBe("target-invalid");
			fs.linkSync(path.join(destination, "a.txt"), path.join(f.project, "src/hard.txt"));
			f.setAuthorization({ run_id: "run-1", targets: ["src/hard.txt"], write_face: ["src/hard.txt"] });
			expect(f.controller.observeToolCall(f.call()).code).toBe("target-invalid");
		},
	);

	it("rejects same-byte directory redirection after call and before result", async () => {
		const f = fixture();
		await f.bind();
		f.controller.observeToolCall(f.call());
		fs.renameSync(path.join(f.project, "src"), path.join(f.project, "real-src"));
		fs.symlinkSync(path.join(f.project, "real-src"), path.join(f.project, "src"), "junction");
		expect(f.controller.observeToolResult(f.result()).effect_state).toBe("unknown");
		expect((await f.controller.appendExecution(f.call().toolCallId)).effect_state).toBe("unknown");
		expect(f.read().status).toBe("absent");
	});

	it("rejects a target replaced by a file link after the result", async () => {
		const f = fixture();
		await f.observe();
		fs.renameSync(path.join(f.project, "src/a.txt"), path.join(f.project, "src/real-a.txt"));
		fs.symlinkSync(path.join(f.project, "src/real-a.txt"), path.join(f.project, "src/a.txt"), "file");
		expect((await f.controller.appendExecution(f.call().toolCallId)).store_result?.code).toBe("verifier-unproven");
	});

	it("missing post-action target is unknown, not an unsupported delete proof", async () => {
		const f = fixture();
		await f.bind();
		f.controller.observeToolCall(f.call());
		fs.unlinkSync(path.join(f.project, "src/b.txt"));
		expect(f.controller.observeToolResult(f.result()).code).toBe("target-invalid");
		expect((await f.controller.appendExecution(f.call().toolCallId)).effect_state).toBe("unknown");
	});

	it("duplicate call/result/store append is explicit and never executes a second action", async () => {
		const f = fixture();
		await f.observe();
		expect(f.controller.observeToolCall(f.call()).code).toBe("duplicate");
		expect(f.controller.observeToolResult(f.result()).code).toBe("duplicate");
		expect((await f.controller.appendExecution(f.call().toolCallId)).store_result?.code).toBe("written");
		const before = f.writes();
		expect((await f.controller.appendExecution(f.call().toolCallId)).store_result?.code).toBe("duplicate");
		expect(f.writes()).toBe(before);
		expect(f.controller.observeToolCall(f.call("second-action")).code).toBe("call-conflict");
	});

	it("out-of-order, unknown and wrong callIds cannot be backfilled into a proof", async () => {
		const f = fixture();
		await f.bind();
		expect(f.controller.observeToolResult(f.result()).code).toBe("unknown-call");
		expect(f.controller.observeToolCall(f.call()).code).toBe("out-of-order");
		expect(f.controller.observeToolCall(f.call("real-2")).code).toBe("call-observed");
		expect(f.controller.observeToolResult(f.result("wrong-2")).code).toBe("unknown-call");
		expect((await f.controller.appendExecution("real-2")).code).toBe("result-missing");
	});

	it("conflicting repeated result permanently poisons the proof rather than replacing history", async () => {
		const f = fixture();
		await f.observe();
		expect(f.controller.observeToolResult({ ...f.result(), result_ref: "conflict" }).code).toBe("result-conflict");
		expect(f.controller.observeToolResult(f.result()).code).toBe("duplicate");
		expect((await f.controller.appendExecution(f.call().toolCallId)).code).toBe("result-conflict");
		expect(f.read().status).toBe("absent");
	});

	it.each([false, true])(
		"execution write failure afterRename=%s performs only read-only reconciliation and no automatic retry",
		async (afterRename) => {
			const f = fixture();
			await f.observe();
			if (afterRename) f.failAfterExecutionWrite();
			else f.failExecution();
			const failed = await f.controller.appendExecution(f.call().toolCallId);
			expect(failed.store_result?.code).toBe("effect-unknown");
			expect(failed.effect_state).toBe("unknown");
			expect(failed.recovery?.execution.status).toBe(afterRename ? "ok" : "absent");
			const writes = f.writes();
			const repeated = await f.controller.appendExecution(f.call().toolCallId);
			expect(repeated.code).toBe("reconciliation-required");
			expect(repeated.replay_allowed).toBe(false);
			expect(f.writes()).toBe(writes);
			expect((await f.controller.saveDisposition(f.call().toolCallId, "disp-1")).code).toBe("disposition-unproven");
		},
	);

	it("concurrent submissions are explicit, not a silent second action", async () => {
		const f = fixture();
		await f.observe();
		const first = f.controller.appendExecution(f.call().toolCallId);
		const second = await f.controller.appendExecution(f.call().toolCallId);
		expect(second.code).toBe("submission-in-flight");
		expect((await first).store_result?.code).toBe("written");
		expect(f.writes()).toBe(2);
	});

	it("verifier rejects each mismatched request association even after a legitimate action", async () => {
		const f = fixture();
		await f.observe();
		expect((await f.controller.appendExecution(f.call().toolCallId)).store_result?.code).toBe("written");
		const original = f.verifyRequests[0];
		expect(await f.controller.verifyExecution(original)).toMatchObject({ effect_state: "known" });
		for (const field of [
			"key",
			"source",
			"local_ref",
			"action_ref",
			"result_ref",
			"executor",
			"observed_effect",
			"expected_target_digest",
		] as const) {
			expect(await f.controller.verifyExecution({ ...original, [field]: "wrong" }), field).toBeUndefined();
		}
		expect(
			await f.controller.verifyExecution({ ...original, binding: { ...original.binding, binding_version: "old" } }),
		).toBeUndefined();
	});

	it("tampering with the persisted selection after commit cannot acquire a matching action proof", async () => {
		const f = fixture();
		await f.observe();
		const selected = f.store.readSelection({ source: "pm", ref: "local-1" });
		fs.writeFileSync(selected.path, JSON.stringify({ ...selected.record, selected_action: "narrow" }));
		expect((await f.controller.appendExecution(f.call().toolCallId)).effect_state).toBe("unknown");
		expect(f.read().status).toBe("absent");
	});

	it("tampering with selection before tool_call blocks the action boundary itself", async () => {
		const f = fixture();
		await f.bind();
		const selected = f.store.readSelection({ source: "pm", ref: "local-1" });
		fs.writeFileSync(selected.path, JSON.stringify({ ...selected.record, selected_basis_id: "foreign-basis" }));
		expect(f.controller.observeToolCall(f.call()).code).toBe("binding-drift");
	});

	it("disposition write failure is concrete and never reported written", async () => {
		const f = fixture();
		await f.observe();
		await f.controller.appendExecution(f.call().toolCallId);
		f.failDisposition();
		const saved = await f.controller.saveDisposition(f.call().toolCallId, "disp-1");
		expect(saved.store_result?.code).toBe("write-failed");
		expect(saved.recovery?.disposition?.status).toBe("absent");
		const writes = f.writes();
		expect((await f.controller.saveDisposition(f.call().toolCallId, "disp-1")).code).toBe("reconciliation-required");
		expect(f.writes()).toBe(writes);
		expect(f.store.readDisposition({ source: "pm", ref: "disp-1" }).status).toBe("absent");
	});

	it("refuses a model-shaped disposition with wrong kind/status/action/result association", async () => {
		const f = fixture();
		await f.observe();
		await f.controller.appendExecution(f.call().toolCallId);
		await f.controller.saveDisposition(f.call().toolCallId, "baseline-disp");
		const valid = f.store.readDisposition({ source: "pm", ref: "baseline-disp" }).record as PmDisposition;
		for (const patch of [
			{ kind: "self-decide" as const },
			{ status: "planned" as const },
			{ basis_refs: ["invented"] },
			{ owner: "foreign" },
		]) {
			f.setDisposition({ ...valid, ...patch, disposition_ref: "invalid-disp" });
			expect((await f.controller.saveDisposition(f.call().toolCallId, "invalid-disp")).code).toBe(
				"disposition-unproven",
			);
		}
		expect(f.store.readDisposition({ source: "pm", ref: "invalid-disp" }).status).toBe("absent");
	});

	it("concurrent disposition submissions produce only one store write", async () => {
		const f = fixture();
		await f.observe();
		await f.controller.appendExecution(f.call().toolCallId);
		const first = f.controller.saveDisposition(f.call().toolCallId, "disp-1");
		const second = f.controller.saveDisposition(f.call().toolCallId, "disp-1");
		const replies = await Promise.all([first, second]);
		expect(replies.map((item) => item.code).sort()).toEqual(["store-result", "submission-in-flight"]);
		expect(f.writes()).toBe(3);
	});

	it("existing unknown/corrupt execution is not treated as an unexecuted action slot", async () => {
		const f = fixture();
		await f.bind();
		const execution = f.read();
		fs.mkdirSync(path.dirname(execution.path), { recursive: true });
		fs.writeFileSync(execution.path, "{broken existing result");
		expect(f.controller.observeToolCall(f.call()).code).toBe("reconciliation-required");
		expect(f.read().status).toBe("corrupt");
	});

	it.each(["empty", "duplicate", "missing-run", "missing-host"] as const)(
		"invalid host authorization %s fails closed before any action",
		async (kind) => {
			const f = fixture();
			await f.bind();
			const original = f.authorization() as RuntimeTargetAuthorization;
			f.setAuthorization(
				kind === "missing-host"
					? undefined
					: {
							...original,
							...(kind === "empty" ? { targets: [] } : {}),
							...(kind === "duplicate" ? { targets: ["src/a.txt", "src/a.txt"] } : {}),
							...(kind === "missing-run" ? { run_id: "" } : {}),
						},
			);
			expect(f.controller.observeToolCall(f.call()).code).toBe("authorization-gap");
			expect(f.writes()).toBe(1);
		},
	);

	it("a new controller after a real executed action cannot recover permission from the old selection", async () => {
		const f = fixture();
		await f.observe();
		await f.controller.appendExecution(f.call().toolCallId);
		const restarted = new RuntimeExecutionController({
			store: f.store,
			project_root: f.project,
			readBinding: f.binding,
			readAuthorization: f.authorization,
		});
		expect((await restarted.commitSelection(f.request)).code).toBe("reconciliation-required");
		expect(restarted.observeToolCall(f.call("new-call-id")).code).toBe("selection-unproven");
		expect(f.writes()).toBe(2);
	});

	it("real harness/faux tool_call → real write → tool_result ignores forged details and persists only host proof", async () => {
		const f = fixture();
		await f.bind();
		const observations: RuntimeExecutionResult[] = [];
		let actualId = "";
		let executed = 0;
		const h = await createHarness({
			extensionFactories: [
				async (pi) => {
					pi.registerTool({
						name: "write",
						label: "Host write",
						description: "Write fixed authorized fixture targets",
						parameters: Type.Object({}),
						execute: async () => {
							executed += 1;
							f.mutate();
							return {
								content: [{ type: "text", text: "Wrote authorized targets" }],
								details: { verified: true, targets: ["../forged"], executor: "forged" },
							};
						},
					});
					pi.on("tool_call", (event) => {
						actualId = event.toolCallId;
						const observed = f.controller.observeToolCall(f.call(event.toolCallId));
						observations.push(observed);
						if (observed.code !== "call-observed") return { block: true, reason: observed.gaps.join(";") };
					});
					pi.on("tool_result", (event) => {
						observations.push(
							f.controller.observeToolResult({ ...f.result(event.toolCallId), isError: event.isError }),
						);
					});
				},
			],
		});
		sessions.push(h);
		h.setResponses([
			fauxAssistantMessage([fauxToolCall("write", {}, { id: "faux-real-tool-call" })], { stopReason: "toolUse" }),
			fauxAssistantMessage("Observed the actual fixture action."),
		]);
		await h.session.prompt("Perform the authorized fixture write.");
		expect(observations.map((item) => item.code)).toEqual(["call-observed", "result-observed"]);
		expect(executed).toBe(1);
		const saved = await f.controller.appendExecution(actualId);
		expect(saved.store_result?.code, JSON.stringify(saved)).toBe("written");
		expect(f.read().record?.executor).toBe(runtimeExecutionExecutor("run-1", actualId));
		expect(f.read().record?.target_digest).toBe(manifestDigest(f.project));
		expect((await f.controller.saveDisposition(actualId, "harness-disp")).store_result?.code).toBe("written");
	});
});
