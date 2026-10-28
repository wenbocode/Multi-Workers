// SYNTHETIC FIXTURE ONLY: parser input, not the T04 triage-client, no wiring proof.
const UNIVERSAL_REQUIRED_FIELDS = [
	"schema_version",
	"decision_point",
	"key",
	"phase",
	"task_type",
	"risk",
	"risk_source",
	"authority_tier",
	"questions_version",
];
export const DP1_ID = "dp1-dispatch-type";
export const REQUIRED_FIELDS_BY_DP: Record<string, string[]> = {
	"dp4-failure-handling": ["failure.kind"],
	"dp5-test-triage": ["failure.kind", "failure.test_name", "failure.baseline_known"],
	"dp6-qg-verdict": ["closure"],
	"dp13-commit-release": ["closure"],
};
