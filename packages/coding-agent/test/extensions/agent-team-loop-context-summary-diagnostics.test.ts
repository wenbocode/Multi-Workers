import { describe, expect, it } from "vitest";
import { formatProviderError, normalizeProviderError } from "../../../ai/src/utils/error-body.ts";
import { projectSummaryFailure } from "../../src/extensions/agent-team-loop/shared/context-summary-diagnostics.ts";

describe("safe summary failure projection", () => {
	it.each([
		["Unsupported parameter: reasoning_effort", "parameter"],
		["invalid_request_error: Unsupported value: temperature", "parameter"],
		["context_length_exceeded", "context"],
		["maximum context length exceeded", "context"],
		["model_not_found", "model"],
		["The model private-model does not exist or you do not have access", "model"],
		["invalid_json", "request_format"],
		["Invalid messages: tool results must follow tool calls", "request_format"],
		["tool_call_id must match a prior tool call", "request_format"],
		["An assistant message with tool_calls must be followed by tool messages", "request_format"],
		["invalid_request_error", "bad_request"],
		["Bad Request", "bad_request"],
	])("classifies HTTP 400 %s without retaining upstream details", (reason, category) => {
		const projected = projectSummaryFailure({
			errorMessage: `OpenAI API error (400): ${reason} PRIVATE-KEY https://private.invalid`,
		});
		expect(projected).toMatchObject({ category, httpStatus: 400 });
		expect(Object.keys(projected).every((field) => ["category", "httpStatus", "errorType"].includes(field))).toBe(
			true,
		);
		expect(JSON.stringify(projected)).not.toMatch(/PRIVATE|https|temperature|reasoning_effort|private-model/);
	});
	it("classifies nested 400 codes and keeps specific auth or quota evidence", () => {
		expect(projectSummaryFailure({ status: 400, error: { code: "invalid_parameter", message: "PRIVATE" } })).toEqual({
			category: "parameter",
			httpStatus: 400,
			errorType: "invalid_parameter",
		});
		expect(projectSummaryFailure({ status: 400, error: { code: "invalid_api_key" } }).category).toBe("auth");
		expect(projectSummaryFailure({ status: 400, error: { code: "insufficient_quota" } }).category).toBe("quota");
		expect(projectSummaryFailure({ status: 400 })).toEqual({ category: "bad_request", httpStatus: 400 });
	});
	it.each(["OpenAI API error", "Azure OpenAI API error"])(
		"recognizes real %s formatting without retaining the body",
		(prefix) => {
			const sdkError = Object.assign(new Error("gateway failure"), {
				status: 429,
				error: { code: "insufficient_quota", message: "Bearer sk-secret https://private?key=task-secret" },
			});
			const errorMessage = formatProviderError(normalizeProviderError(sdkError), prefix);
			expect(errorMessage).toContain(`${prefix} (429):`);
			const projected = projectSummaryFailure({ errorMessage });
			expect(projected).toEqual({ category: "quota", httpStatus: 429, errorType: "insufficient_quota" });
			expect(JSON.stringify(projected)).not.toMatch(/secret|Bearer|https|gateway/);
			const authMessage = formatProviderError(
				normalizeProviderError(Object.assign(new Error("no body"), { status: 401 })),
				prefix,
			);
			expect(projectSummaryFailure({ errorMessage: authMessage })).toEqual({ category: "auth", httpStatus: 401 });
		},
	);
	it.each([
		[
			{ errorMessage: "HTTP 429 insufficient_quota" },
			{ category: "quota", httpStatus: 429, errorType: "insufficient_quota" },
		],
		[{ status: 429 }, { category: "rate_limit", httpStatus: 429 }],
		[{ error: { code: "rate_limit_exceeded" } }, { category: "rate_limit", errorType: "rate_limit_exceeded" }],
		[{ statusCode: 401 }, { category: "auth", httpStatus: 401 }],
		[{ code: "context_length_exceeded" }, { category: "context", errorType: "context_length_exceeded" }],
		[new Error("fetch failed"), { category: "network" }],
		[{ cause: { code: "ECONNRESET" } }, { category: "network", errorType: "ECONNRESET" }],
		[{ message: "unknown failure" }, { category: "unknown" }],
		[{ message: "connect https://host/429?key=secret" }, { category: "unknown" }],
		[{ status: "429" }, { category: "unknown" }],
		[{ message: "429 apples" }, { category: "unknown" }],
		[{ message: "quota is available" }, { category: "unknown" }],
		[{ message: "HTTP 503 upstream unavailable" }, { category: "unknown", httpStatus: 503 }],
	])("projects only supported evidence from %j", (input, expected) => {
		expect(projectSummaryFailure(input)).toEqual(expected);
	});
	it("reads allowed diagnostic fields without leaking any upstream strings", () => {
		const input = {
			errorMessage: "Bearer sk-secret https://private?key=task-secret\nstack private task body",
			diagnostics: [{ type: "provider", details: { status: 429, code: "insufficient_quota", body: "task-secret" } }],
			content: [{ type: "text", text: "private result" }],
		};
		const projected = projectSummaryFailure(input);
		expect(projected).toEqual({ category: "quota", httpStatus: 429, errorType: "insufficient_quota" });
		expect(JSON.stringify(projected)).not.toMatch(/secret|Bearer|https|stack|private/);
		expect(JSON.stringify(projected).length).toBeLessThan(128);
	});
	it("ignores arbitrary fields, getter code, cycles, oversized text and diagnostic tails", () => {
		const hostile: Record<string, unknown> = Object.defineProperty(
			{ body: "insufficient_quota", self: null },
			"message",
			{
				get() {
					throw new Error("must never execute");
				},
			},
		);
		hostile.self = hostile;
		expect(projectSummaryFailure(hostile)).toEqual({ category: "unknown" });
		const revoked = Proxy.revocable({}, {});
		revoked.revoke();
		expect(projectSummaryFailure({ diagnostics: revoked.proxy })).toEqual({ category: "unknown" });
		const sparse = new Array(1_000_000_000);
		sparse[999_999_999] = { details: { code: "insufficient_quota" } };
		expect(projectSummaryFailure({ diagnostics: sparse })).toEqual({ category: "unknown" });
		expect(projectSummaryFailure({ errorMessage: `${"x".repeat(4096)} insufficient_quota` })).toEqual({
			category: "unknown",
		});
		expect(
			projectSummaryFailure({
				diagnostics: [...Array.from({ length: 8 }, () => ({})), { details: { code: "insufficient_quota" } }],
			}),
		).toEqual({ category: "unknown" });
	});
});
