import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Check } from "typebox/value";
import { describe, expect, it, vi } from "vitest";
import {
	ASK_DECISION_PARAMETERS,
	previewDecisionInput,
	registerAskDecisionTool,
	runAskDecision,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	preparationProblems,
	validateDecisionMaterial,
} from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { createHarness, getMessageText } from "./harness.ts";

it("encodes a candidate pair with a single string item schema and exact cardinality", () => {
	const pair =
		ASK_DECISION_PARAMETERS.properties.preparation.properties.model_context.properties.auto_comparison.properties
			.pairs.items.properties.candidates;
	expect(JSON.parse(JSON.stringify(pair))).toEqual({
		type: "array",
		items: { type: "string" },
		minItems: 2,
		maxItems: 2,
	});
	expect(Check(pair, ["retry", "diagnose"])).toBe(true);
	for (const invalid of [["retry"], ["retry", "diagnose", "stop"], ["retry", 2]]) {
		expect(Check(pair, invalid)).toBe(false);
	}
});

function qgRequest(refs: string[]) {
	return {
		projectDir: ".",
		dp: "dp-QG",
		trigger: "refs-regression",
		key: "fixture",
		initiatorRole: "pm" as const,
		material: {
			review_requirements: "All acceptance checks pass",
			review_evidence: ["src/check.ts:42"],
			review_findings: "Private finding text must not appear in diagnostic",
			uncovered_scope: "None",
		},
		preparation: {
			prepared_at: "2026-11-13T03:00:00Z",
			basis_catalog: [
				{ id: "evidence", text: "Review facts", material_refs: refs, applies_to: ["fix"] },
				{
					id: "pass-criterion",
					text: "If current independent evidence covers all applicable checks",
					material_refs: ["review_requirements"],
					applies_to: ["pass"],
				},
				{
					id: "reopen-criterion",
					text: "If the review finds a substantive conflict in the acceptance standard",
					material_refs: ["review_requirements"],
					applies_to: ["reopen"],
				},
			],
		},
	};
}

describe("material_refs contract and local diagnosis", () => {
	it("refuses an incomplete QG menu in preview and before spawning the decision CLI", async () => {
		const request = qgRequest(["review_findings"]);
		request.preparation.basis_catalog.pop();
		const runner = vi.fn(async () => {
			throw new Error("Incomplete criteria must not reach the CLI");
		});
		const preview = previewDecisionInput(request.dp, request.material, request.preparation);
		expect(preview.issues).toMatchObject([
			{ field: "preparation.basis_catalog", code: "missing", rule: "missing prepared criteria for reopen" },
		]);
		const result = await runAskDecision({ ...request, runner });
		expect(result.payload).toMatchObject({ available: false, unavailable: "input-incomplete" });
		expect(runner).not.toHaveBeenCalled();
	});

	it("describes field paths at the actual tool parameter", () => {
		const refs =
			ASK_DECISION_PARAMETERS.properties.preparation.properties.basis_catalog.items.properties.material_refs;
		const schemaText = JSON.stringify(refs);
		expect(schemaText).toMatch(/field paths?/i);
		expect(schemaText).toContain("material.");
		expect(schemaText).toContain("path:line");
	});

	it.each([
		["src/check.ts:42"],
		["E:\\repo\\src\\check.ts:42"],
		["material.review_evidence"],
		["background.current_state"],
		["review_missing"],
		["review_evidence[0]"],
		["review_evidence", "src/check.ts:42"],
		[],
	])("rejects %j without a child and explains the current QG fields", async (...refs) => {
		const runner = vi.fn(async () => {
			throw new Error("Unexpected child call");
		});
		const request = qgRequest(refs);
		const result = await runAskDecision({ ...request, runner });
		expect(result.spawned).toBe(false);
		expect(runner).not.toHaveBeenCalled();
		expect(result.payload).toEqual({
			available: false,
			unavailable: "input-incomplete",
			action: "blocked-ask-human",
			missing_fields: ["preparation.basis_catalog[0].material_refs"],
		});
		const diagnosisLine = result.text.split("\n").find((line) => line.startsWith("MATERIAL_REFS_DIAGNOSIS:"));
		expect(diagnosisLine).toBeDefined();
		expect(diagnosisLine).toContain("review_evidence");
		expect(diagnosisLine).toContain("review_findings");
		expect(diagnosisLine).toContain("path:line");
		expect(diagnosisLine).not.toContain(request.material.review_findings);
		expect(diagnosisLine).not.toContain(request.material.review_evidence[0]);
		expect(diagnosisLine).not.toContain("background.current_state");
	});

	it("diagnoses the bad element while retaining the original missing_fields path", async () => {
		const result = await runAskDecision({
			...qgRequest(["review_evidence", "material.review_findings"]),
			runner: vi.fn(async () => {
				throw new Error("Unexpected child call");
			}),
		});
		expect(result.text).toContain("preparation.basis_catalog[0].material_refs[1]");
		expect(result.payload).toMatchObject({ missing_fields: ["preparation.basis_catalog[0].material_refs"] });
	});

	it.each([null, 42, {}, [null], [42], [""], ["   "]].map((refs) => ({ refs })))(
		"preserves rejection for malformed refs $refs",
		({ refs }) => {
			const request = qgRequest(["review_evidence"]);
			const preparation = {
				...request.preparation,
				basis_catalog: [
					{ ...request.preparation.basis_catalog[0], material_refs: refs },
					...request.preparation.basis_catalog.slice(1),
				],
			};
			expect(preparationProblems(request.dp, request.material, preparation, undefined)).toEqual([
				"preparation.basis_catalog[0].material_refs",
			]);
		},
	);

	it("accepts evidence field paths and forwards file positions as evidence values", async () => {
		const request = qgRequest(["review_evidence", "review_findings"]);
		const runner = vi.fn(async (call: { input: string }) => {
			const envelope = JSON.parse(call.input);
			return {
				status: 0,
				timedOut: false,
				stderr: "",
				stdout: JSON.stringify({
					available: true,
					file_evidence: [],
					decision_id: `dp-QG:${envelope.meta.logical_id}`,
					mode: "suggest",
					acted: false,
					answers: { qg_verdict: { value: "fix" }, basis_id: { value: "evidence" } },
				}),
			};
		});
		const lifecycleRunner = vi.fn(async () => ({
			status: 0,
			timedOut: false,
			stderr: "",
			stdout: JSON.stringify({ recorded: true, status: "written" }),
		}));
		const result = await runAskDecision({ ...request, runner, lifecycleRunner });
		expect(result.payload).toMatchObject({ available: true, selection: { id: "fix" } });
		expect(result.text).not.toContain("MATERIAL_REFS_DIAGNOSIS");
		expect(runner).toHaveBeenCalledTimes(1);
		expect(lifecycleRunner).toHaveBeenCalledTimes(1);
		expect(JSON.parse(runner.mock.calls[0][0].input)).toMatchObject({
			material: request.material,
			preparation: request.preparation,
		});
	});

	it.each(["background", "background.current_state", "background.constraints"])(
		"accepts the declared dp-auto reference %s",
		(ref) => {
			const material = {
				question: "Which observation should be taken?",
				background: {
					task_goal: "Find the failed check",
					current_state: "src/check.ts:42 identifies the failure",
					tried: "Read the output",
					unknowns: "Root cause",
					constraints: "Read only",
				},
				handling_options: ["inspect", "report"].map((id) => ({
					id,
					label: id,
					description: id,
					consequence: "One observation",
					risk: "Missing information",
					conditions: "Read access",
				})),
			};
			const preparation = qgRequest([ref]).preparation;
			preparation.basis_catalog = [{ ...preparation.basis_catalog[0], applies_to: ["inspect"] }];
			expect(validateDecisionMaterial("dp-auto", material).ok).toBe(true);
			expect(preparationProblems("dp-auto", material, preparation, undefined)).toEqual([]);
		},
	);

	it("keeps registered-tool diagnosis on a cached invalid request and accepts corrected material_refs", async () => {
		const projectDir = fs.mkdtempSync(path.join(os.tmpdir(), "material-refs-regression-"));
		const request = qgRequest(["src/check.ts:42"]);
		const runner = vi.fn(async () => ({
			status: 0,
			stderr: "",
			stdout: JSON.stringify({ available: false, reason: "entry-unavailable" }),
			timedOut: false,
		}));
		const h = await createHarness({
			extensionFactories: [
				(pi) => {
					const registration = vi.spyOn(pi, "registerTool");
					registerAskDecisionTool(pi, { projectDir, key: "fixture", initiatorRole: "pm", runner });
					const tool = registration.mock.calls.find(([definition]) => definition.name === "ask_decision")?.[0];
					expect(tool?.promptGuidelines?.join(" ")).toContain("path:line");
				},
			],
		});
		try {
			for (const refs of [["src/check.ts:42"], ["src/check.ts:42"], ["review_evidence"]]) {
				h.setResponses([
					fauxAssistantMessage(
						[
							fauxToolCall("ask_decision", {
								dp: request.dp,
								trigger: request.trigger,
								material: request.material,
								preparation: qgRequest(refs).preparation,
							}),
						],
						{ stopReason: "toolUse" },
					),
					fauxAssistantMessage("Recorded the local result"),
				]);
				await h.session.prompt("Check the prepared references");
			}
			const results = h.session.messages.filter((message) => message.role === "toolResult");
			expect(results).toHaveLength(3);
			for (const result of results.slice(0, 2)) {
				expect(getMessageText(result)).toContain("MATERIAL_REFS_DIAGNOSIS:");
				expect(getMessageText(result)).toContain("review_evidence");
			}
			expect(runner).toHaveBeenCalledTimes(1);
		} finally {
			h.cleanup();
			fs.rmSync(projectDir, { recursive: true, force: true });
		}
	});
});
