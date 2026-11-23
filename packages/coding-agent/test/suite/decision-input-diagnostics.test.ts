import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { expect, it, vi } from "vitest";
import {
	formatInputDiagnostics,
	readInputDiagnostics,
} from "../../src/extensions/agent-team-loop/pm/decision-input-diagnostics.ts";
import { registerAskDecisionTool, runAskDecision } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { createHarness, getMessageText } from "./harness.ts";

it("shows the contract header or material field used by a preparation diagnostic", () => {
	const diagnostics = readInputDiagnostics({
		stage: "evidence-preparation",
		transport: "not-sent",
		truncated: false,
		issues: [
			{
				field: "model_context.references.VC-002",
				code: "criterion-reference-unresolved",
				path: ".agenticdoc/context/design.md",
				source_line: 89,
			},
			{
				field: "preparation.model_context.terminology.XRAY",
				code: "undefined-term",
				source_field: "preparation.basis_catalog[1].text",
			},
		],
	});
	expect(diagnostics).toBeDefined();
	if (diagnostics) {
		const text = formatInputDiagnostics(diagnostics);
		expect(text).toContain(".agenticdoc/context/design.md:89");
		expect(text).toContain("preparation.basis_catalog[1].text");
	}
});

it("admits a public quality request with zero findings and no fix placeholder", async () => {
	const runner = vi.fn(async (_request: { input: string }) => ({
		status: 0,
		timedOut: false,
		stderr: "",
		stdout: JSON.stringify({ available: false, reason: "entry-unavailable" }),
	}));
	await runAskDecision({
		dp: "dp-QG",
		trigger: "current-review",
		projectDir: ".",
		key: "fixture",
		initiatorRole: "pm",
		runner,
		material: {
			review_requirements: "The export remains readable.",
			review_evidence: ["The readback result is pending."],
			review_findings: "No product findings.",
			uncovered_scope: "A further independent check is pending.",
		},
		preparation: {
			prepared_at: "2026-11-23T00:00:00Z",
			model_context: { reasons: {} },
			basis_catalog: [
				{
					id: "satisfied",
					text: "Apply when independent review meets the contract.",
					applies_to: ["pass"],
					material_refs: ["review_requirements"],
				},
				{
					id: "basis-gap",
					text: "Apply when the contract itself is inconsistent.",
					applies_to: ["reopen"],
					material_refs: ["review_requirements"],
				},
			],
		},
	});
	expect(runner).toHaveBeenCalledOnce();
	expect(JSON.parse(runner.mock.calls[0][0].input).preparation.model_context.reasons).toEqual({});
});

it("shows a bounded, safe evidence refusal and sends explicit refs in the local envelope", async () => {
	const evidenceRefs = [
		{
			field: "material.decision_object",
			path: "review.md",
			lines: { start: 8, end: 24 },
		},
	];
	const correctedRefs = [{ ...evidenceRefs[0], lines: { start: 8, end: 21 } }];
	const receiptId = "17c2c45f-84c9-4a6e-9ca1-3ea5087afd95";
	const runner = vi.fn(async (_request: { input: string }) => {
		return {
			status: 0,
			timedOut: false,
			stderr: "",
			stdout: JSON.stringify({
				available: false,
				reason: "input-incomplete",
				escalated_reason: "input-incomplete",
				blocked_event_id: receiptId,
				input_diagnostics: {
					stage: "evidence-preparation",
					transport: "not-sent",
					truncated: false,
					allowed_fields: [
						"material.review_evidence[0]",
						"material.review_findings",
						"preparation.basis_catalog[0].text",
						"material.bad\nlabel",
					],
					issues: [
						{
							field: "material.decision_object",
							code: "evidence-range-out-of-bounds",
							path: "review.md",
							requested_lines: { start: 8, end: 24 },
							file_line_count: 21,
							raw_material: "internal request",
						},
						{ field: "evidence_refs[1].path", code: "evidence-file-unresolved", path: "E:/private/secret.md" },
						{ field: "evidence_refs[2].field", code: "invalid-evidence-reference" },
						{ field: "material.question", code: "unrecognized", path: "no-display.md" },
					],
				},
			}),
		};
	});
	const lifecycleRunner = vi.fn();
	const h = await createHarness({
		extensionFactories: [
			(pi) => {
				registerAskDecisionTool(pi, { key: "fixture", initiatorRole: "pm", runner, lifecycleRunner });
			},
		],
	});
	try {
		let replayed = false;
		for (const [iteration, refs] of [evidenceRefs, evidenceRefs, correctedRefs].entries()) {
			const priorCalls = runner.mock.calls.length;
			h.setResponses([
				fauxAssistantMessage(
					[
						fauxToolCall("ask_decision", {
							dp: "dp-route",
							trigger: "verify-route",
							material: {
								decision_actor: "PM",
								decision_object: "Evidence review",
								question: "Which entry applies?",
							},
							preparation: {
								prepared_at: "2026-11-20T12:00:00Z",
								basis_catalog: [
									{
										id: "scope",
										text: "Review the evidence",
										applies_to: ["dp-pm-steer"],
										material_refs: ["decision_object"],
									},
								],
							},
							evidence_refs: refs,
						}),
					],
					{ stopReason: "toolUse" },
				),
				fauxAssistantMessage("Read the local refusal"),
			]);
			await h.session.prompt("Check the route");
			const result = h.session.messages.filter((message) => message.role === "toolResult").at(-1);
			const details = result?.details as { blocked_event_id?: string; matter_suppressed?: true } | undefined;
			if (iteration === 1 && details?.matter_suppressed) {
				replayed = true;
				expect(runner).toHaveBeenCalledTimes(priorCalls);
				expect(details).toMatchObject({ original_blocked_event_id: receiptId });
				expect(details.blocked_event_id).not.toBe(receiptId);
			} else {
				expect(runner).toHaveBeenCalledTimes(priorCalls + 1);
				expect(JSON.parse(runner.mock.calls[priorCalls][0].input).evidence_refs).toEqual(refs);
				expect(details?.blocked_event_id).toBe(receiptId);
			}
			const body = getMessageText(result);
			expect(body).toContain("Lines 8–24, file has 21 lines.");
			expect(body).toContain("Request was not sent.");
			expect(body).toContain(
				"Available evidence_refs.field paths: material.review_evidence[0], material.review_findings, preparation.basis_catalog[0].text.",
			);
			expect(body).not.toMatch(/internal request|private\/secret|no-display|material\.bad/);
			expect(result?.details).toMatchObject({
				available: false,
				input_diagnostics: {
					allowed_fields: [
						"material.review_evidence[0]",
						"material.review_findings",
						"preparation.basis_catalog[0].text",
					],
					issues: [
						{ field: "material.decision_object", code: "evidence-range-out-of-bounds", path: "review.md" },
						{ field: "evidence_refs[1].path", code: "evidence-file-unresolved" },
						{ field: "evidence_refs[2].field", code: "invalid-evidence-reference" },
					],
				},
			});
		}
		expect(runner).toHaveBeenCalledTimes(replayed ? 2 : 3);
		expect(lifecycleRunner).not.toHaveBeenCalled();
	} finally {
		h.cleanup();
	}
});
