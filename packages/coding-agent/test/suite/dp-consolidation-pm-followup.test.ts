import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	type DecisionFollowupIntent,
	markDecisionFollowupExecuted,
	resumeDecisionFollowup,
} from "../../src/extensions/agent-team-loop/pm/decision-followup.ts";
import { PYTHON_EXE } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";

const roots: string[] = [];
afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

function fixture(overrides: Partial<DecisionFollowupIntent> = {}): { root: string; file: string } {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "decision-followup-"));
	roots.push(root);
	const file = path.join(root, "followup.json");
	const intent: DecisionFollowupIntent = {
		schema_version: 1,
		parent_ref: "gate:matter-v1",
		parent_logical_id: "11111111-1111-4111-8111-111111111111",
		parent_decision_id: "dp-gate-approve:gate-v1",
		parent_matter_version: "matter-v1",
		target_dp: "dp-pm-steer",
		material_version: "material-v1",
		basis_version: "basis-v1",
		owner_key: "owner",
		task_key: "task",
		prepared_by: { role: "pm", key: "owner", window_id: "window-1" },
		restricted_action: "split",
		restricted_executor: "pm:window-1",
		status: "prepared",
		request_ref: null,
		answer: null,
		failure_reason: null,
		...overrides,
	};
	fs.writeFileSync(file, `${JSON.stringify(intent, null, 2)}\n`);
	return { root, file };
}

const boundPm = { role: "pm" as const, key: "owner", window_id: "window-1" };
const expected = {
	parent_ref: "gate:matter-v1",
	parent_logical_id: "11111111-1111-4111-8111-111111111111",
	parent_decision_id: "dp-gate-approve:gate-v1",
	parent_matter_version: "matter-v1",
	material_version: "material-v1",
	basis_version: "basis-v1",
	target_dp: "dp-pm-steer" as const,
	owner_key: "owner",
	task_key: "task",
	restricted_action: "split",
	restricted_executor: "pm:window-1",
};

// Drive the real T08 client through its established local HTTP double and the
// real T10 store. The execution fact is produced only after two scoped task
// artifacts actually exist. No provider or live project is used.
function recordFixture(
	root: string,
	stage: "parent" | "successor" | "action" | "narrow",
	parentChoice = "steer",
	parentId = expected.parent_logical_id,
): string {
	const mw = path.resolve("../multi-workers");
	vi.stubEnv("MW_PY", path.join(mw, "mw.py"));
	const python = `
import pathlib, sys
import pytest
import decision_lifecycle as lifecycle
import decision_wire as wire
import test_dp_consolidation_materials as f
root, stage = pathlib.Path(sys.argv[1]), sys.argv[2]
parent = stage == "parent"
dp = "dp-gate-approve" if parent else "dp-pm-steer"
decision_id = "dp-gate-approve:gate-v1" if parent else "dp-pm-steer:successor-1"
logical = sys.argv[4] if parent else "22222222-2222-4222-8222-222222222222"
meta = lifecycle.DecisionMeta.create("owner", task_key="task", initiator_role="pm", logical_id=logical)
scope = lifecycle.LifecycleStore.test(root, project_id="fixture", redact=wire.SubstringRedactor([f.API_KEY]))
actor = ("system", "pm:window-1")
if stage in ("action", "narrow"):
    if stage == "action":
        for name in ("task-a.md", "task-b.md"):
            (root / name).write_text("Nonoverlapping local fixture task: " + name, encoding="utf-8")
        action, result, event_id = "split", "task-a.md and task-b.md created", "split-done"
    else:
        (root / "focus.md").write_text("Finish the remaining test; retain all deliverables.", encoding="utf-8")
        action, result, event_id = "narrow", "focus.md created", "narrow-done"
    effect = lifecycle.record_executed(scope, meta, decision_id=decision_id, dp=dp, actor=actor,
                                       action=action, result=result, event_id=event_id)
    assert effect.recorded
    print(effect.event_id)
else:
    assert lifecycle.record_start(scope, meta, decision_id=decision_id, actor=actor).recorded
    material = f._material(dp)
    prep = f._preparation(dp, material)
    answers = f._legal_answers(dp, material)
    answers[f.BUSINESS_QIDS[dp]] = f._choice_answer(sys.argv[3] if parent else "split")
    with pytest.MonkeyPatch.context() as patch:
        fake = f.FakeHttp(lambda *args: f._body(dp, answers))
        patch.setattr(f.backends, "_http_post", fake)
        client = f._make_client(root, patch)
        answer = client.request_prepared(dp, material, prep, actor_role="pm")
        assert len(fake.calls) == 1 and answer["business_decisions"] == 1
        receipt = lifecycle.record_request(scope, meta, decision_id=decision_id, result=answer, material=material,
                    preparation=prep, parent_ref=None if parent else "dp-gate-approve:gate-v1", actor=actor)
        assert receipt.recorded
        print(answer["choice"])
`;
	return execFileSync(PYTHON_EXE, ["-B", "-X", "utf8", "-c", python, root, stage, parentChoice, parentId], {
		cwd: mw,
		encoding: "utf8",
		windowsHide: true,
	}).trim();
}

describe("prepared PM decision follow-up", () => {
	it("matches the native Python UUID and rejects a differently spelled parent record", async () => {
		const parentId = expected.parent_logical_id.replaceAll("-", "");
		const { root, file } = fixture({ parent_logical_id: parentId });
		const request = vi.fn(async () => ({ available: false as const, reason: "disabled" }));
		const invoke = () =>
			resumeDecisionFollowup({
				intent_path: file,
				expected: { ...expected, parent_logical_id: parentId },
				bound_pm: boundPm,
				observe_task: () => "not-queued",
				request,
				lifecycle: { isolatedTestRoot: root, projectId: "fixture" },
			});
		recordFixture(root, "parent");
		expect(await invoke()).toMatchObject({ state: "blocked", request_started: false });
		expect(request).not.toHaveBeenCalled();
		const separate = fixture({ parent_logical_id: parentId });
		recordFixture(separate.root, "parent", "steer", parentId);
		expect(
			await resumeDecisionFollowup({
				intent_path: separate.file,
				expected: { ...expected, parent_logical_id: parentId },
				bound_pm: boundPm,
				observe_task: () => "not-queued",
				request,
				lifecycle: { isolatedTestRoot: separate.root, projectId: "fixture" },
			}),
		).toMatchObject({ state: "failed", request_started: true });
		expect(request).toHaveBeenCalledTimes(1);
	});
	it("issues one real successor request and replays the recorded answer without a duplicate", async () => {
		const { root, file } = fixture();
		const lifecycle = { isolatedTestRoot: root, projectId: "fixture" };
		expect(recordFixture(root, "parent")).toBe("steer");
		const request = vi.fn(async () => ({
			available: true as const,
			request_ref: "dp-pm-steer:successor-1",
			answer: recordFixture(root, "successor"),
		}));
		const first = await resumeDecisionFollowup({
			intent_path: file,
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request,
			lifecycle,
		});
		const replay = await resumeDecisionFollowup({
			intent_path: file,
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request,
			lifecycle,
		});
		expect(first).toMatchObject({ state: "answered", request_started: true, parent_released: false });
		expect(replay).toMatchObject({ state: "answered", request_started: false, duplicate: true });
		expect(request).toHaveBeenCalledTimes(1);
		const stale = fixture();
		expect(
			await resumeDecisionFollowup({
				intent_path: stale.file,
				expected,
				bound_pm: boundPm,
				observe_task: () => "not-queued",
				request,
				lifecycle,
			}),
		).toMatchObject({ state: "blocked", request_started: false });
		expect(request).toHaveBeenCalledTimes(1);
	});

	it("keeps unavailable requests failed and does not infer an answer or action", async () => {
		const { root, file } = fixture({ target_dp: "dp-auto" });
		recordFixture(root, "parent", "need_fix");
		const request = vi.fn(async () => ({ available: false as const, reason: "provider-unavailable" }));
		const result = await resumeDecisionFollowup({
			intent_path: file,
			expected: { ...expected, target_dp: "dp-auto" },
			lifecycle: { isolatedTestRoot: root, projectId: "fixture" },
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request,
		});
		expect(result).toMatchObject({ state: "failed", reason: "provider-unavailable", parent_released: false });
		expect(JSON.parse(fs.readFileSync(file, "utf8"))).toMatchObject({
			status: "failed",
			request_ref: null,
			answer: null,
		});
	});

	it.each(["pending", "running"] as const)("does not request while the owning task is %s", async (status) => {
		const { file } = fixture();
		const request = vi.fn();
		const result = await resumeDecisionFollowup({
			intent_path: file,
			expected,
			bound_pm: boundPm,
			observe_task: () => status,
			request,
		});
		expect(result).toMatchObject({ state: "in-progress", reason: `task-${status}`, parent_released: false });
		expect(request).not.toHaveBeenCalled();
	});

	it("stops on unknown task state, a disappeared PM window, or changed substantive versions", async () => {
		const unknown = fixture();
		const missingWindow = fixture();
		const stale = fixture();
		const request = vi.fn();
		expect(
			await resumeDecisionFollowup({
				intent_path: unknown.file,
				expected,
				bound_pm: boundPm,
				observe_task: () => "unknown",
				request,
			}),
		).toMatchObject({ state: "unknown", reason: "task-unknown" });
		expect(
			await resumeDecisionFollowup({
				intent_path: missingWindow.file,
				expected,
				bound_pm: null,
				observe_task: () => "not-queued",
				request,
			}),
		).toMatchObject({ state: "blocked", reason: "pm-window-unbound" });
		expect(
			await resumeDecisionFollowup({
				intent_path: stale.file,
				expected: { ...expected, material_version: "material-v2" },
				bound_pm: boundPm,
				observe_task: () => "not-queued",
				request,
			}),
		).toMatchObject({ state: "blocked", reason: "version-mismatch" });
		expect(request).not.toHaveBeenCalled();
	});

	it("treats a persisted requesting state as crash-unknown instead of blindly retrying", async () => {
		const { file } = fixture({ status: "requesting" });
		const request = vi.fn();
		const result = await resumeDecisionFollowup({
			intent_path: file,
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request,
		});
		expect(result).toMatchObject({ state: "unknown", reason: "request-outcome-unknown" });
		expect(request).not.toHaveBeenCalled();
	});

	it.each([
		{ restricted_executor: "worker:other" },
		{ target_dp: "dp-auto" },
		{ task_key: "other" },
		{ owner_key: "other" },
		{ restricted_action: "commit unrelated files" },
	])("preserves a replacement intent while a request is in flight (%j)", async (replacement) => {
		const { root, file } = fixture();
		recordFixture(root, "parent");
		const response = await resumeDecisionFollowup({
			intent_path: file,
			lifecycle: { isolatedTestRoot: root, projectId: "fixture" },
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request: async (original) => {
				fs.writeFileSync(file, JSON.stringify({ ...original, ...replacement }));
				return { available: true, request_ref: "dp-pm-steer:successor-1", answer: "split" };
			},
		});
		expect(response).toMatchObject({ state: "unknown", request_started: true });
		expect(JSON.parse(fs.readFileSync(file, "utf8"))).toMatchObject({
			...replacement,
			status: "requesting",
			answer: null,
		});
	});

	it.each(["lost", "done", "failed", "needs-clarification"] as const)(
		"does not replay an unreconciled %s successor",
		async (status) => {
			const { file } = fixture();
			const request = vi.fn();
			expect(
				await resumeDecisionFollowup({
					intent_path: file,
					expected,
					bound_pm: boundPm,
					observe_task: () => status,
					request,
				}),
			).toMatchObject({ state: "unknown", request_started: false });
			expect(request).not.toHaveBeenCalled();
		},
	);

	it("keeps exception text out of the intent and result", async () => {
		const { root, file } = fixture();
		recordFixture(root, "parent");
		const result = await resumeDecisionFollowup({
			intent_path: file,
			lifecycle: { isolatedTestRoot: root, projectId: "fixture" },
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued",
			request: async () => {
				throw new Error("Authorization: Bearer test-followup-token");
			},
		});
		expect(result).toMatchObject({ state: "failed", reason: "request-threw" });
		expect(fs.readFileSync(file, "utf8")).not.toContain("test-followup-token");
	});

	it("refuses an unsubstantiated gate or an unrecorded callback result", async () => {
		const { root, file } = fixture();
		const request = vi.fn(async () => ({
			available: true as const,
			request_ref: "dp-pm-steer:successor-1",
			answer: "split",
		}));
		const input = {
			intent_path: file,
			expected,
			bound_pm: boundPm,
			observe_task: () => "not-queued" as const,
			request,
		};
		const lifecycle = { isolatedTestRoot: root, projectId: "fixture" };
		expect(await resumeDecisionFollowup(input)).toMatchObject({ state: "blocked", request_started: false });
		expect(await resumeDecisionFollowup({ ...input, lifecycle })).toMatchObject({
			state: "blocked",
			request_started: false,
		});
		expect(request).not.toHaveBeenCalled();
		recordFixture(root, "parent");
		expect(await resumeDecisionFollowup({ ...input, lifecycle })).toMatchObject({
			state: "unknown",
			request_started: true,
		});
		expect(JSON.parse(fs.readFileSync(file, "utf8")).status).toBe("requesting");
		expect(request).toHaveBeenCalledTimes(1);
	});

	it("records actual execution separately; an answer alone never releases the parent", async () => {
		const { root, file } = fixture({ status: "answered", request_ref: "dp-pm-steer:successor-1", answer: "split" });
		const lifecycle = { isolatedTestRoot: root, projectId: "fixture" };
		recordFixture(root, "parent");
		recordFixture(root, "successor");
		const input = {
			intent_path: file,
			expected,
			bound_pm: boundPm,
			request_ref: "dp-pm-steer:successor-1",
			lifecycle,
			action_evidence: "split-done",
		};
		expect(await markDecisionFollowupExecuted(input)).toMatchObject({ state: "unknown" });
		expect(recordFixture(root, "action")).toBe(input.action_evidence);
		const executed = await markDecisionFollowupExecuted(input);
		expect(executed).toMatchObject({ state: "executed", parent_released: false });
		expect(await markDecisionFollowupExecuted(input)).toMatchObject({ state: "executed", duplicate: true });
		expect(await markDecisionFollowupExecuted({ ...input, request_ref: "another-decision" })).toMatchObject({
			state: "blocked",
		});
		expect(await markDecisionFollowupExecuted({ ...input, action_evidence: "another-action" })).toMatchObject({
			state: "unknown",
		});
		expect(
			await markDecisionFollowupExecuted({ ...input, lifecycle: { ...lifecycle, projectId: "unrelated" } }),
		).toMatchObject({ state: "unknown" });
		expect(JSON.parse(fs.readFileSync(file, "utf8"))).toMatchObject({
			status: "executed",
			action_evidence: "split-done",
		});
	});

	it("refuses a real restricted action from a different selected branch", async () => {
		const { root, file } = fixture({
			status: "answered",
			answer: "split",
			request_ref: "dp-pm-steer:successor-1",
			restricted_action: "narrow",
		});
		recordFixture(root, "parent");
		recordFixture(root, "successor");
		expect(recordFixture(root, "narrow")).toBe("narrow-done");
		expect(
			await markDecisionFollowupExecuted({
				intent_path: file,
				expected: { ...expected, restricted_action: "narrow" },
				bound_pm: boundPm,
				lifecycle: { isolatedTestRoot: root, projectId: "fixture" },
				action_evidence: "narrow-done",
				request_ref: "dp-pm-steer:successor-1",
			}),
		).toMatchObject({ state: "blocked", reason: "action-not-selected" });
		expect(JSON.parse(fs.readFileSync(file, "utf8")).status).toBe("answered");
	});
});
