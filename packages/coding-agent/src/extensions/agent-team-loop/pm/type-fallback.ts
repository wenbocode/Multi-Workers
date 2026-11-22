import {
	claimedPmKey,
	type DecisionPreparation,
	preparationProblems,
	validateDecisionMaterial,
} from "../shared/decide-policy.ts";

/** Classification failure transfers judgment to the owning PM, never to a worker.
 * This does not authorize any other decision point or replace dispatch guards. */
export function canPmSelectType(input: {
	projectDir: string;
	dp: string;
	key: string | undefined;
	role: string | undefined;
	reason: string;
	material: unknown;
	preparation: DecisionPreparation | undefined;
	context?: Record<string, unknown>;
}): boolean {
	if (
		input.dp !== "dp-w-type" ||
		input.role !== "pm" ||
		process.env.PI_WORKER_TASK ||
		!input.key ||
		claimedPmKey(input.projectDir, input.key) !== input.key ||
		![
			"disabled",
			// r2 T04A zero-network pre-transport fact: a missing/unconfigured
			// `.mw/decide.json` is a KNOWN off state, not an unknown reply. The
			// same claim/role/material/preparation checks still apply; this adds
			// no dispatch permission and never accepts an arbitrary reason.
			"unconfigured",
			"entry-unavailable",
			"provider-unavailable",
			"timeout",
			"rate-limited",
			"upstream-error",
			"bad-response",
			"budget-exhausted",
			"input-incomplete",
			"input-oversize",
		].includes(input.reason)
	)
		return false;
	const validated = validateDecisionMaterial(input.dp, input.material);
	return (
		validated.ok && preparationProblems(input.dp, validated.material, input.preparation, input.context).length === 0
	);
}

export const PM_TYPE_FALLBACK_DIRECTIVE =
	"dp-w-type unavailable: PM must select coding/research/review/vision from the original task card and prepared basis, " +
	"then call dispatch_worker with the matching type, card_path and decision_preparation. " +
	"Record source=pm and the reason; do not wait for a human to choose the type or retry the failed classifier. " +
	"Fix verifiable missing material first; never invent evidence or a DP decision_id. " +
	"Claim, role, image capability and write-surface checks still apply.";
