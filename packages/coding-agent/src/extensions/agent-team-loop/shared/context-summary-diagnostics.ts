export type SummaryFailureCategory = "quota" | "rate_limit" | "auth" | "context" | "network" | "unknown";

export interface SummaryFailure {
	category: SummaryFailureCategory;
	httpStatus?: number;
	errorType?: (typeof ERROR_TYPES)[number][0];
}

const ERROR_TYPES = [
	["insufficient_quota", "quota"],
	["quota_exceeded", "quota"],
	["rate_limit_exceeded", "rate_limit"],
	["invalid_api_key", "auth"],
	["authentication_error", "auth"],
	["permission_denied", "auth"],
	["context_length_exceeded", "context"],
	["ECONNRESET", "network"],
	["ECONNREFUSED", "network"],
	["ETIMEDOUT", "network"],
	["ENOTFOUND", "network"],
] as const satisfies ReadonlyArray<readonly [string, SummaryFailureCategory]>;

function dataField(value: unknown, field: string): unknown {
	if (typeof value !== "object" || value === null) return undefined;
	try {
		const descriptor = Object.getOwnPropertyDescriptor(value, field);
		return descriptor && "value" in descriptor ? descriptor.value : undefined;
	} catch {
		return undefined;
	}
}

/** Fixed fields, bounded scanning, and enum-only output: never serialize upstream objects. */
export function projectSummaryFailure(value: unknown): SummaryFailure {
	let httpStatus: number | undefined;
	const texts: string[] = [];
	const candidates = [value, dataField(value, "error"), dataField(value, "cause")];
	const diagnostics = dataField(value, "diagnostics");
	// Read data descriptors only, including on an array/proxy with hostile accessors.
	const length = dataField(diagnostics, "length");
	if (typeof length === "number" && Number.isSafeInteger(length) && length >= 0) {
		for (let index = 0; index < Math.min(length, 8); index++) {
			candidates.push(dataField(dataField(diagnostics, String(index)), "details"));
		}
	}
	for (const candidate of candidates) {
		for (const key of ["status", "statusCode", "httpStatus"]) {
			const status = dataField(candidate, key);
			if (
				httpStatus === undefined &&
				typeof status === "number" &&
				Number.isInteger(status) &&
				status >= 100 &&
				status <= 599
			)
				httpStatus = status;
		}
		for (const key of ["code", "type", "name", "message", "errorMessage"]) {
			const text = dataField(candidate, key);
			if (typeof text === "string") texts.push(text.slice(0, 4096));
		}
	}
	if (typeof value === "string") texts.push(value.slice(0, 4096));
	// Only explicit status syntax counts, never a bare number in a task or URL.
	for (const text of texts) {
		const match =
			/^(?:HTTP(?: error)?\s+([1-5]\d{2})\b|([1-5]\d{2})(?=:| status code\b)|(?:(?:Azure )?OpenAI )?API error\s*\(([1-5]\d{2})\))/.exec(
				text,
			);
		if (httpStatus === undefined && match) httpStatus = Number(match[1] ?? match[2] ?? match[3]);
	}
	const status = httpStatus === undefined ? {} : { httpStatus };
	for (const [errorType, category] of ERROR_TYPES) {
		const pattern = new RegExp(`\\b${errorType}\\b`, "i");
		if (texts.some((text) => pattern.test(text))) return { category, ...status, errorType };
	}
	const text = texts.join("\n");
	if (/\b(?:quota exceeded|out of budget|insufficient quota)\b/i.test(text)) return { category: "quota", ...status };
	if (/\b(?:rate limit|too many requests)\b/i.test(text) || httpStatus === 429)
		return { category: "rate_limit", ...status };
	if (httpStatus === 401 || httpStatus === 403) return { category: "auth", ...status };
	if (/\b(?:maximum context length|context window exceeded)\b/i.test(text)) return { category: "context", ...status };
	if (/\b(?:fetch failed|network error|socket hang up|connection refused)\b/i.test(text))
		return { category: "network", ...status };
	return { category: "unknown", ...status };
}
