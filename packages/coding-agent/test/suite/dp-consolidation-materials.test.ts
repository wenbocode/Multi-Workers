import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { describe, expect, it, vi } from "vitest";
import {
	ASK_DECISION_DP_IDS,
	ASK_DECISION_PARAMETERS,
	buildDecisionEnvelope,
	registerAskDecisionTool,
	runAskDecision,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	newDecisionMeta,
	triageDispatch,
	triageDispatchEnvelope,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import {
	DECIDE_REGISTRY,
	DECIDE_REGISTRY_RETIRED,
} from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import { createHarness } from "./harness.ts";

it.each(["finalize", "continue", "user-confirm"])(
	"maps the real Python sign producer through the faux tool for %s",
	async (choice) => {
		const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
		const helper = path.join(
			root,
			".agenticdoc/mw-dp-consolidation/evidence/implementation/T24-Codex-sign-tests-r2/sign_transport.py",
		);
		const projectDir = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-sign-seam-"));
		const { input } = currentRequest("dp-sign-key", choice);
		fs.mkdirSync(path.join(projectDir, ".agenticdoc"), { recursive: true });
		fs.mkdirSync(path.join(projectDir, ".mw"));
		fs.writeFileSync(
			path.join(projectDir, ".agenticdoc/_index.parallel"),
			`| fixture | active | EXECUTE | ${os.hostname()}:${process.pid} | — | fixture | now |\n`,
		);
		fs.writeFileSync(path.join(projectDir, ".mw/decide.json"), JSON.stringify({ enabled: true }));
		const lifecycleRunner = vi.fn(input.lifecycleRunner);
		const signRunner = vi.fn(async (request: { key: string; input: string }) => {
			const env: NodeJS.ProcessEnv = {};
			for (const name of ["PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"]) {
				if (process.env[name] !== undefined) env[name] = process.env[name];
			}
			for (const name of ["HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"]) {
				const dir = path.join(projectDir, name);
				fs.mkdirSync(dir, { recursive: true });
				env[name] = dir;
			}
			env.PYTHONDONTWRITEBYTECODE = "1";
			env.PYTHONUTF8 = "1";
			const child = spawnSync(
				"python",
				["-B", helper, "decide", "sign", request.key, `--project=${projectDir}`, "--stdin", "--json"],
				{ input: request.input, encoding: "utf8", env, timeout: 20000 },
			);
			expect(child.error, `Python spawn failed: ${child.error?.message}`).toBeUndefined();
			expect(
				() => JSON.parse(child.stdout ?? ""),
				`Python status=${child.status}; stderr=${child.stderr}; stdout=${child.stdout}`,
			).not.toThrow();
			console.info(
				JSON.stringify({ seam: choice, status: child.status, stdout: child.stdout, stderr: child.stderr }),
			);
			return {
				status: child.status,
				stdout: child.stdout ?? "",
				stderr: child.stderr ?? "",
				timedOut: child.error?.message.includes("ETIMEDOUT") ?? false,
			};
		});
		const h = await createHarness({
			extensionFactories: [
				(pi) => {
					registerAskDecisionTool(pi, {
						projectDir,
						key: "fixture",
						initiatorRole: "pm",
						signRunner,
						lifecycleRunner,
					});
				},
			],
		});
		try {
			h.setResponses([
				fauxAssistantMessage(
					[
						fauxToolCall("ask_decision", {
							dp: "dp-sign-key",
							trigger: "sign-seam",
							material: input.material,
							preparation: input.preparation,
						}),
					],
					{ stopReason: "toolUse" },
				),
				fauxAssistantMessage("Done"),
			]);
			await h.session.prompt("Submit the prepared sign material");
			expect(signRunner).toHaveBeenCalledTimes(1);
			const result = h.session.messages.find((message) => message.role === "toolResult");
			expect(result?.role === "toolResult" && result.details).toMatchObject({
				available: true,
				selection: { id: choice },
				basis: input.preparation.basis_catalog[0],
				signoff: { second_approval: 0, status: choice === "finalize" ? "written" : "not-required" },
			});
			expect(fs.existsSync(path.join(projectDir, ".agenticdoc/fixture/evidence/review/sign-final.md"))).toBe(
				choice === "finalize",
			);
			expect(lifecycleRunner).not.toHaveBeenCalled();
		} finally {
			h.cleanup();
			fs.rmSync(projectDir, { recursive: true, force: true });
		}
	},
);

describe("active decision contracts", () => {
	it("registers exactly the eight generated entries", () => {
		expect(ASK_DECISION_DP_IDS).toEqual(Object.keys(DECIDE_REGISTRY));
		expect(ASK_DECISION_PARAMETERS.properties.dp.anyOf.map((item) => item.const)).toEqual(
			Object.keys(DECIDE_REGISTRY),
		);
	});
	it("rejects retired IDs before replay, runners or feedback, at both client entries", async () => {
		const runner = vi.fn(() => {
			throw new Error("unexpected call");
		});
		for (const { id } of DECIDE_REGISTRY_RETIRED) {
			const result = await runAskDecision({
				dp: id,
				projectDir: ".",
				trigger: "replay",
				retryOf: "abc",
				runner,
				lifecycleRunner: runner,
				signRunner: runner,
			});
			expect(result.payload).toMatchObject({ available: false, unavailable: "retired" });
			expect(triageDispatch({ dp: id, projectDir: ".", state: {}, run: runner })).toMatchObject({
				available: false,
				reason: "retired",
			});
		}
		expect(runner).not.toHaveBeenCalled();
	});
});

const materialFor: Record<string, Record<string, unknown>> = {
	"dp-w-type": {
		task_goal: "Review the patch",
		task_requirements: "Check the tests",
		task_deliverables: "File comments",
	},
	"dp-pm-steer": {
		task_goal: "Finish the task",
		task_requirements: "Honor the budget",
		task_deliverables: "One patch",
		pm_decision_background: "The current scope exceeds the remaining budget",
	},
	"dp-w-check-task": {
		task_goal: "Review",
		reachability_facts: "Two files left",
		completed: "Read the patch",
		remaining: "Run tests",
		blockers: "None",
		constraints: "One minute",
		investigation: {
			unknown: "Is the fixture present?",
			evidence_source: "fixture path",
			budget: "30s",
			stop_condition: "File contents or missing",
		},
	},
	"dp-QG": {
		review_requirements: "Each check passes",
		review_evidence: ["report:2"],
		review_findings: "Gate result",
		uncovered_scope: "none",
	},
	"dp-gate-approve": {
		gate_background: "Ready for local run",
		current_state: "Patch prepared",
		condition_evidence: ["review:2"],
		pm_note: {
			subject: "Local run",
			planned_action: "Run scoped test",
			basis: { goal: "Verify work", evidence: "review:2", budget: "One run", authority: "Task card" },
		},
	},
	"dp-sign-key": {
		delivery_goal: "Complete review",
		actual_completion: "Reviewed",
		verification_evidence: { verified: [], unverified: [] },
		unfinished_impact: [],
	},
	"dp-auto": {
		question: "Which source to inspect?",
		background: {
			task_goal: "Verify",
			current_state: "One failure",
			tried: "Logged stdout",
			unknowns: "Cause",
			constraints: "Read-only",
		},
		handling_options: Array.from({ length: 6 }, (_, i) => ({
			id: `inspect-${i}`,
			label: `Inspect ${i}`,
			description: `Read source ${i}`,
			consequence: "One observation",
			risk: "Missing log",
			conditions: "Read access",
		})),
	},
	"dp-route": {
		decision_actor: "Current PM",
		decision_object: "Pending code review",
		question: "Which review applies?",
	},
};

function currentRequest(dp: string, choice: string) {
	const entry = DECIDE_REGISTRY[dp];
	const material = { ...materialFor[dp] };
	if (dp === "dp-QG" && choice === "reopen") material.basis_issue = "The acceptance condition omits Windows";
	const reference = entry.requiredStateFields[0].name;
	const preparation = {
		prepared_at: "2026-10-25T07:10:00Z",
		basis_catalog: [
			{
				id: "basis-42",
				text: "The referenced facts support this conclusion",
				material_refs: [reference],
				applies_to: [choice],
			},
		],
	};
	const runner = vi.fn(async (request: { input: string }) => {
		const { meta } = JSON.parse(request.input);
		return {
			status: 0,
			timedOut: false,
			stderr: "",
			stdout: JSON.stringify({
				dp,
				key: meta.key,
				logical_id: meta.logical_id,
				decision_id: `${dp}:${meta.logical_id}`,
				available: true,
				mode: "suggest",
				acted: false,
				conclusion: choice,
				basis_id: "basis-42",
				second_approval: 0,
				signoff_status: choice === "finalize" ? "written" : "not-required",
				answers: { [entry.businessQuestionId]: { value: choice }, basis_id: { value: "basis-42" } },
			}),
		};
	});
	const lifecycleRunner = vi.fn(async () => ({
		status: 0,
		stdout: JSON.stringify({ status: "written", recorded: true }),
		stderr: "",
		timedOut: false,
	}));
	const input = {
		dp,
		key: "fixture",
		taskKey: entry.roleScope === "worker" ? "real-task" : null,
		projectDir: ".",
		trigger: "review",
		initiatorRole: entry.roleScope === "worker" ? ("review" as const) : ("pm" as const),
		preparation,
		material,
		runner,
		signRunner: runner,
		lifecycleRunner,
	};
	return { input, runner, lifecycleRunner };
}

describe.each(Object.entries(materialFor))("%s at the registered transport boundary", (dp) => {
	const entry = DECIDE_REGISTRY[dp];
	const choices =
		entry.kind === "dynamic-candidates" ? Array.from({ length: 6 }, (_, i) => `inspect-${i}`) : entry.fixedChoiceIds;
	it.each(choices)("accepts the submitted business choice %s and its same-call prepared basis", async (choice) => {
		const { input, runner, lifecycleRunner } = currentRequest(dp, choice);
		const result = await runAskDecision(input);
		expect(result.payload).toMatchObject({
			available: true,
			selection: { id: choice, question: entry.businessQuestionId },
			basis: input.preparation.basis_catalog[0],
		});
		expect(runner).toHaveBeenCalledTimes(1);
		const envelope = JSON.parse(runner.mock.calls[0][0].input);
		expect(envelope).toEqual({
			material: input.material,
			preparation: input.preparation,
			meta: expect.objectContaining({
				key: "fixture",
				task_key: input.taskKey,
				initiator_role: input.initiatorRole,
			}),
		});
		if (dp === "dp-sign-key") expect(lifecycleRunner).not.toHaveBeenCalled();
		else {
			expect(result.payload).toMatchObject({ acted: false });
			expect(lifecycleRunner).toHaveBeenCalledTimes(1);
		}
	});
	it("blocks missing, forged and cross-role inputs before any child", async () => {
		const { input, runner, lifecycleRunner } = currentRequest(dp, choices[0]);
		for (const change of [
			{ material: {} },
			{ material: { ...input.material, role: "pm" } },
			{ preparation: undefined },
			{ preparation: { ...input.preparation, prepared_at: "2026-10-25" } },
			{
				preparation: {
					...input.preparation,
					basis_catalog: [{ ...input.preparation.basis_catalog[0], material_refs: ["invented"] }],
				},
			},
			{ context: { basis_catalog: input.preparation.basis_catalog } },
			{ initiatorRole: entry.roleScope === "worker" ? ("pm" as const) : ("coding" as const) },
		]) {
			const result = await runAskDecision({ ...input, ...change });
			expect(result.payload).toMatchObject({ available: false, action: "blocked-ask-human" });
			expect(result.spawned).toBe(false);
		}
		expect(runner).not.toHaveBeenCalled();
		expect(lifecycleRunner).not.toHaveBeenCalled();
	});
	it("blocks unavailable service, missing choice and missing or mismatched basis without consuming a receipt", async () => {
		const { input, lifecycleRunner } = currentRequest(dp, choices[0]);
		for (const problem of ["outage", "choice", "missing-basis", "mismatch"]) {
			const child = vi.fn(async (request: { input: string }) => {
				const base = await input.runner(request);
				const payload = JSON.parse(base.stdout);
				if (problem === "outage") return { ...base, status: 1, stdout: "" };
				if (problem === "choice") {
					delete payload.answers[entry.businessQuestionId];
					delete payload.conclusion;
				}
				if (problem === "missing-basis") {
					delete payload.answers.basis_id;
					delete payload.basis_id;
				}
				if (problem === "mismatch") {
					payload.answers.basis_id.value = "unknown basis";
					payload.basis_id = "unknown basis";
				}
				return { ...base, stdout: JSON.stringify(payload) };
			});
			const result = await runAskDecision({ ...input, runner: child, signRunner: child });
			expect(result.payload).toMatchObject({ available: false, action: "blocked-ask-human" });
			expect(child).toHaveBeenCalledTimes(1);
		}
		expect(lifecycleRunner).not.toHaveBeenCalled();
	});
});

it("preserves allowed context separately and keeps an external L0 note outside the submitted PM gate note", async () => {
	const auto = currentRequest("dp-auto", "inspect-2");
	const context = { error_excerpt: "fixture check failed" };
	await runAskDecision({ ...auto.input, context });
	expect(JSON.parse(auto.runner.mock.calls[0][0].input)).toMatchObject({
		context,
		preparation: auto.input.preparation,
	});
	const gate = currentRequest("dp-gate-approve", "steer");
	const material = { ...gate.input.material };
	delete material.pm_note;
	const refused = await runAskDecision({ ...gate.input, material, note: "external text" });
	expect(refused.spawned).toBe(false);
	expect(gate.runner).not.toHaveBeenCalled();
});

it("projects a verified basis from the synchronous PM dispatch and rejects a reply from another request", () => {
	const { input } = currentRequest("dp-w-type", "research");
	const meta = newDecisionMeta({ key: "fixture", taskKey: "reserved-task", initiatorRole: "pm" });
	const policy = {
		enabled: true,
		dp1Enabled: true,
		alertOnDisagreement: false,
		notifyOnUnavailable: false,
		timeoutMs: 20000,
	};
	const response = {
		available: true,
		acted: false,
		mode: "suggest",
		decision_id: `dp-w-type:${meta.logical_id}`,
		dp: input.dp,
		logical_id: meta.logical_id,
		answers: { triage_type: { value: "research" }, basis_id: { value: "basis-42" } },
	};
	const run = vi.fn(() => ({ status: 0, stderr: "", stdout: JSON.stringify(response), timedOut: false }));
	const projectDir = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-sync-triage-"));
	try {
		fs.mkdirSync(path.join(projectDir, ".agenticdoc"));
		const dispatch = {
			dpId: input.dp,
			projectDir,
			meta,
			material: input.material,
			preparation: input.preparation,
			policy,
			run,
		};
		expect(triageDispatchEnvelope(dispatch)).toMatchObject({ available: false, reason: "role-forbidden" });
		expect(run).not.toHaveBeenCalled();
		fs.writeFileSync(
			path.join(projectDir, ".agenticdoc", "_index.parallel"),
			`| fixture | active | EXECUTE | ${os.hostname()}:${process.pid} | — | fixture | now |`,
		);
		expect(triageDispatchEnvelope(dispatch)).toMatchObject({
			available: true,
			triage_type: "research",
			basis: input.preparation.basis_catalog[0],
		});
		response.logical_id = "another-task";
		expect(triageDispatchEnvelope(dispatch)).toMatchObject({ available: false, reason: "bad-response" });
		expect(run).toHaveBeenCalledTimes(2);
	} finally {
		fs.rmSync(projectDir, { recursive: true, force: true });
	}
});

it("passes a trusted follow-up parent only on the local stdin envelope", async () => {
	const { input, runner } = currentRequest("dp-auto", "inspect-1");
	const parentDecisionRef = "gate:matter-v1";
	const out = await runAskDecision({ ...input, parentDecisionRef });
	expect(out.payload.available).toBe(true);
	const envelope = JSON.parse(runner.mock.calls[0][0].input);
	expect(envelope.parent_decision_ref).toBe(parentDecisionRef);
	for (const local of [envelope.meta, envelope.material, envelope.preparation])
		expect(JSON.stringify(local)).not.toContain(parentDecisionRef);
	const built = buildDecisionEnvelope({
		dp: input.dp,
		material: input.material,
		meta: envelope.meta,
		preparation: input.preparation,
		parentDecisionRef,
	});
	expect(built).toEqual(envelope);
	const refused = await runAskDecision({ ...input, parentDecisionRef: "  " });
	expect(refused.spawned).toBe(false);
	expect(runner).toHaveBeenCalledTimes(1);
});
it("prevents the model tool from supplying a parent decision reference", async () => {
	const { input, runner } = currentRequest("dp-auto", "inspect-1");
	const h = await createHarness({
		extensionFactories: [
			(pi) => {
				registerAskDecisionTool(pi, {
					projectDir: ".",
					key: "fixture",
					initiatorRole: "pm",
					runner,
					lifecycleRunner: input.lifecycleRunner,
				});
			},
		],
	});
	try {
		for (const key of ["parentDecisionRef", "parent_decision_ref"]) {
			h.setResponses([
				fauxAssistantMessage(
					[
						fauxToolCall("ask_decision", {
							dp: input.dp,
							trigger: "site",
							material: input.material,
							preparation: input.preparation,
							[key]: "gate:spoof",
						}),
					],
					{ stopReason: "toolUse" },
				),
				fauxAssistantMessage("Done"),
			]);
			await h.session.prompt("Submit");
		}
		expect(runner).not.toHaveBeenCalled();
		const schema = JSON.stringify(ASK_DECISION_PARAMETERS);
		expect(schema).not.toContain("parent_decision_ref");
		expect(schema).not.toContain("parentDecisionRef");
	} finally {
		h.cleanup();
	}
});
