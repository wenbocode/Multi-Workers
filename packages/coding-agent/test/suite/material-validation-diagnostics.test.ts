import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { describe, expect, it, vi } from "vitest";
import { registerAskDecisionTool, runAskDecision } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { validateDecisionMaterial } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { createHarness, getMessageText } from "./harness.ts";

// Original UEPerformanceFlow request, 2026-11-14T20:54:54.044Z. This is a
// public regression fixture; the test never reads a user's sessions or calls DP.
const ORIGINAL_BASIS_ISSUE =
	"The review identifies explicit unmet requirements, not merely absent runtime evidence: post-disarm paths can escape without restoring HOLD; terminal evidence checks do not enforce required identity/summary consistency; diagnostic formatting can bypass independent poll; selected context mismatch does not fail closed. Proposed cases also cannot exercise the actual filesystem/default consumer behaviors they claim. These substantive P1 defects require repair and new independent review before any later isolated run is considered.";

function qgRequest(fields: Record<string, unknown> = {}) {
	return {
		projectDir: ".",
		dp: "dp-QG",
		trigger: "material-diagnosis-regression",
		key: "fixture",
		initiatorRole: "pm" as const,
		material: {
			review_requirements: "All required checks must pass",
			review_evidence: ["src/check.ts:42"],
			review_findings: "Private implementation finding",
			uncovered_scope: "None",
			...fields,
		} as Record<string, unknown>,
		preparation: {
			prepared_at: "2026-11-15T10:00:00Z",
			basis_catalog: [
				{
					id: "review",
					text: "The review facts support the selected branch",
					material_refs: ["review_findings"],
					applies_to: ["pass", "fix", "reopen"],
				},
			],
		},
	};
}

describe("local material validation diagnostics", () => {
	it("identifies the original 530-byte value as over-limit rather than missing with zero child calls", async () => {
		const runner = vi.fn(async () => {
			throw new Error("Invalid material must not reach a child");
		});
		expect(Buffer.byteLength(ORIGINAL_BASIS_ISSUE)).toBe(530);
		const result = await runAskDecision({ ...qgRequest({ basis_issue: ORIGINAL_BASIS_ISSUE }), runner });
		expect(result.spawned).toBe(false);
		expect(runner).not.toHaveBeenCalled();
		expect(result.payload).toMatchObject({
			available: false,
			unavailable: "input-incomplete",
			action: "blocked-ask-human",
			material_issues: [{ field: "basis_issue", code: "max-bytes", actual: 530, limit: 512 }],
		});
		expect(result.payload).not.toHaveProperty("missing_fields");
		expect(result.text).toContain("UTF-8 bytes");
		expect(result.text).not.toContain(ORIGINAL_BASIS_ISSUE);
		expect(result.text).toContain("不要用别的工具绕过");
		process.stdout.write("[VERIFY] VC-001: actual=530 limit=512 spawned=false missing=false\n");
	});

	it.each([
		{ value: "a".repeat(512), bytes: 512, valid: true },
		{ value: "a".repeat(513), bytes: 513, valid: false },
		{ value: `${"界".repeat(170)}ab`, bytes: 512, valid: true },
		{ value: "界".repeat(171), bytes: 513, valid: false },
	])("enforces the existing UTF-8 boundary at $bytes bytes, valid=$valid", ({ value, bytes, valid }) => {
		expect(Buffer.byteLength(value)).toBe(bytes);
		const result = validateDecisionMaterial("dp-QG", qgRequest({ basis_issue: value }).material);
		expect(result.ok).toBe(valid);
		if (!result.ok)
			expect(result.issues).toMatchObject([{ field: "basis_issue", code: "max-bytes", actual: bytes, limit: 512 }]);
	});

	it.each([
		{ value: null, code: "type" },
		{ value: 42, code: "type" },
		{ value: false, code: "type" },
		{ value: {}, code: "type" },
		{ value: [], code: "type" },
		{ value: "", code: "blank" },
		{ value: "   ", code: "blank" },
	])("distinguishes a supplied invalid value from an absent field ($code)", async ({ value, code }) => {
		const runner = vi.fn(async () => {
			throw new Error("Invalid material must not reach a child");
		});
		const result = await runAskDecision({ ...qgRequest({ basis_issue: value }), runner });
		expect(result.payload).toMatchObject({ material_issues: [{ field: "basis_issue", code }] });
		expect(result.payload).not.toHaveProperty("missing_fields");
		expect(runner).not.toHaveBeenCalled();
	});

	it("reports a truly absent required field as missing and permits absent optional basis_issue", async () => {
		const request = qgRequest();
		expect(validateDecisionMaterial(request.dp, request.material).ok).toBe(true);
		delete request.material.review_findings;
		const runner = vi.fn(async () => {
			throw new Error("Incomplete material must not reach a child");
		});
		const result = await runAskDecision({ ...request, runner });
		expect(result.payload).toMatchObject({
			missing_fields: ["review_findings"],
			material_issues: [{ field: "review_findings", code: "missing" }],
		});
		expect(runner).not.toHaveBeenCalled();
		process.stdout.write("[VERIFY] VC-002: utf8-boundaries=true missing-distinct=true\n");
	});

	it("does not echo unknown field names or submitted values in a local refusal", async () => {
		const unknownKey = "private-api-key-must-not-be-echoed";
		const unknownValue = "private-field-value-must-not-be-echoed";
		const runner = vi.fn(async () => {
			throw new Error("Unknown material must not reach a child");
		});
		const result = await runAskDecision({ ...qgRequest({ [unknownKey]: unknownValue }), runner });
		expect(result.payload).toMatchObject({ material_issues: [{ field: "material", code: "unknown-field" }] });
		expect(result.text).not.toContain(unknownKey);
		expect(result.text).not.toContain(unknownValue);
		expect(result.text).not.toContain("Private implementation finding");
		expect(runner).not.toHaveBeenCalled();
	});

	it.each([
		{ choice: "pass", fields: {}, available: true },
		{ choice: "fix", fields: {}, available: true },
		{ choice: "fix", fields: { basis_issue: "A concrete basis problem" }, available: true },
		{ choice: "reopen", fields: { basis_issue: "Acceptance criteria conflict" }, available: true },
		{ choice: "pass", fields: { basis_issue: "Acceptance criteria conflict" }, available: false },
		{ choice: "reopen", fields: {}, available: false },
	])("keeps the existing $choice branch contract, available=$available", async ({ choice, fields, available }) => {
		const request = qgRequest(fields);
		const runner = vi.fn(async (call: { input: string }) => {
			const envelope = JSON.parse(call.input);
			expect(envelope.material).toEqual(request.material);
			return {
				status: 0,
				timedOut: false,
				stderr: "",
				stdout: JSON.stringify({
					available: true,
					decision_id: `dp-QG:${envelope.meta.logical_id}`,
					mode: "suggest",
					acted: false,
					file_evidence: [],
					answers: { qg_verdict: { value: choice }, basis_id: { value: "review" } },
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
		expect(result.payload.available, JSON.stringify(result.payload)).toBe(available);
		if (!available) expect(result.payload).toMatchObject({ unavailable: "bad-response" });
		expect(runner).toHaveBeenCalledTimes(1);
		expect(lifecycleRunner).toHaveBeenCalledTimes(available ? 1 : 0);
	});

	it("preserves precise diagnostics through the registered tool and same-matter recheck", async () => {
		const projectDir = fs.mkdtempSync(path.join(os.tmpdir(), "material-diagnosis-regression-"));
		const request = qgRequest({ basis_issue: ORIGINAL_BASIS_ISSUE });
		const runner = vi.fn(async () => ({
			status: 0,
			stderr: "",
			stdout: JSON.stringify({ available: false, reason: "entry-unavailable" }),
			timedOut: false,
		}));
		const h = await createHarness({
			extensionFactories: [
				(pi) => {
					registerAskDecisionTool(pi, { projectDir, key: "fixture", initiatorRole: "pm", runner });
				},
			],
		});
		try {
			for (const basisIssue of [ORIGINAL_BASIS_ISSUE, ORIGINAL_BASIS_ISSUE, "Acceptance criteria conflict"]) {
				h.setResponses([
					fauxAssistantMessage(
						[
							fauxToolCall("ask_decision", {
								dp: request.dp,
								trigger: request.trigger,
								material: { ...request.material, basis_issue: basisIssue },
								preparation: request.preparation,
							}),
						],
						{ stopReason: "toolUse" },
					),
					fauxAssistantMessage("Recorded the local result"),
				]);
				await h.session.prompt("Check the prepared material");
			}
			const results = h.session.messages.filter((message) => message.role === "toolResult");
			expect(results).toHaveLength(3);
			for (const result of results.slice(0, 2)) {
				const payload = JSON.parse(getMessageText(result).split("\n")[0]);
				expect(payload).toMatchObject({
					material_issues: [{ field: "basis_issue", code: "max-bytes", actual: 530, limit: 512 }],
				});
				expect(payload).not.toHaveProperty("missing_fields");
				expect(getMessageText(result)).not.toContain(ORIGINAL_BASIS_ISSUE);
			}
			expect(runner).toHaveBeenCalledTimes(1);
			process.stdout.write("[VERIFY] VC-003: registered-diagnosis=true repeated-invalid-zero-child=true\n");
		} finally {
			h.cleanup();
			fs.rmSync(projectDir, { recursive: true, force: true });
		}
	});
});
