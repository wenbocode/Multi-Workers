import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";
import { previewDecisionInput, runAskDecision } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import type { DecisionPreparation } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";

it.each(Object.entries(DECIDE_REGISTRY))("prepares the registered choices for %s", (dp, entry) => {
	const material = { handling_options: [{ id: "inspect" }, { id: "finish" }] };
	const expected = entry.kind === "dynamic-candidates" ? ["inspect", "finish"] : entry.fixedChoiceIds;
	const basis = { id: "basis", text: "basis", material_refs: ["handling_options"], applies_to: ["invalid-choice"] };
	const preparation = { prepared_at: "2026-11-21T00:00:00Z", basis_catalog: [basis] };
	expect(previewDecisionInput(dp, material, preparation)).toMatchObject({
		allowed_choices: expected,
		issues: expect.arrayContaining([
			{
				field: "preparation.basis_catalog[0].applies_to[0]",
				code: "enum",
				received_choice: "invalid-choice",
				allowed_choices: expected,
				rule: expect.any(String),
			},
		]),
	});
	for (const choice of expected) {
		basis.applies_to = [choice];
		expect(
			previewDecisionInput(dp, material, preparation).issues.filter((i) => i.field.includes("applies_to")),
		).toEqual([]);
	}
});

it.each(["Gaze", "RenderPerformance"])(
	"replays the %s window request and repairs only invalid bindings",
	async (name) => {
		const request: {
			dp: string;
			trigger: string;
			material: Record<string, unknown>;
			preparation: DecisionPreparation;
			evidence_refs: { field: string; path: string }[];
		} = JSON.parse(
			readFileSync(
				process.env.MW_CONTRACT_REPLAY_DIR
					? `${process.env.MW_CONTRACT_REPLAY_DIR}/${name}-contract-real.json`
					: new URL(`./fixtures/decision-contract/${name}.json`, import.meta.url),
				"utf8",
			),
		);
		const { dp, material, preparation, evidence_refs } = request;
		const preview = () => previewDecisionInput(dp, material, preparation, undefined, evidence_refs);
		const rejected = preview();
		expect(
			rejected.issues.filter((issue) => issue.field.startsWith("evidence_refs")).map((issue) => issue.field),
		).toEqual(evidence_refs.map((_, i) => `evidence_refs[${i}].field`));
		if (name === "Gaze") {
			const runner = vi.fn();
			const result = await runAskDecision({
				...request,
				projectDir: ".",
				key: "fixture",
				initiatorRole: "pm",
				evidenceRefs: evidence_refs,
				runner,
			});
			expect(result.payload).toMatchObject({
				available: false,
				material_issues: [
					{
						code: "enum",
						field: "preparation.basis_catalog[1].applies_to[0]",
						received_choice: "continue",
						allowed_choices: ["narrow", "split", "direct-exec", "escalate"],
					},
				],
			});
			expect(result.payload).not.toHaveProperty("missing_fields");
			expect(result.text).toContain("evidence_refs[4].field");
			expect(runner).not.toHaveBeenCalled();
			preparation.basis_catalog[1].applies_to = ["escalate"];
		}
		for (const ref of evidence_refs) {
			ref.field = ref.field === "review_evidence" ? "material.review_evidence[0]" : `material.${ref.field}`;
			expect(rejected.evidence_fields).toContain(ref.field);
		}
		expect(preview()).toMatchObject({ preview: true, transport: "not-sent", issues: [] });
	},
);
