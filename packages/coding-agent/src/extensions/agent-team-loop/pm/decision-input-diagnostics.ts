const messages = {
	"invalid-evidence-reference": "Use an existing field, a literal path and an optional ordered line range.",
	"evidence-file-unresolved": "Check the file path relative to the control workspace.",
	"evidence-range-out-of-bounds": "Choose lines within the file.",
	"evidence-preparation-failed": "Verify the cited evidence and its read scope.",
	"evidence-read-denied": "Select evidence within the configured read scope.",
	"evidence-file-unreadable": "Select a readable UTF-8 evidence file.",
	"evidence-budget-exceeded": "Use a narrower line range or a smaller evidence file.",
	"evidence-protocol-unsupported": "Reload using a release with a compatible MW Python CLI.",
	"missing-candidates": "Add prepared criteria for every missing candidate.",
	"criterion-reference-unresolved": "Check the current criterion and its definition in the bound contract.",
	"criterion-reference-other-object": "Use the current key's own contract and evidence for this review.",
	"undefined-term": "Define the term in preparation.model_context.terminology or omit irrelevant prose.",
} as const;

type IssueCode = keyof typeof messages;

interface InputIssue {
	field: string;
	code: IssueCode;
	path?: string;
	requested_lines?: { start: number; end: number };
	file_line_count?: number;
	source_field?: string;
	source_line?: number;
	choices?: string[];
}

export interface DecisionInputDiagnostics {
	stage: "evidence-preparation";
	transport: "not-sent";
	issues: InputIssue[];
	truncated: boolean;
	allowed_fields?: string[];
	allowed_fields_truncated?: boolean;
}

const MAX_ALLOWED_FIELDS = 64;
const bindingHint =
	/^(?:material(?:\.[A-Za-z_][A-Za-z0-9_-]*(?:\[\d{1,6}\])*)+|preparation\.basis_catalog\[\d{1,6}\]\.text)$/;

function record(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

function lineNumber(value: unknown): value is number {
	return typeof value === "number" && Number.isSafeInteger(value) && value > 0 && value <= 2 ** 31 - 1;
}

export function readInputDiagnostics(value: unknown): DecisionInputDiagnostics | undefined {
	if (
		!record(value) ||
		value.stage !== "evidence-preparation" ||
		value.transport !== "not-sent" ||
		!Array.isArray(value.issues) ||
		typeof value.truncated !== "boolean"
	)
		return undefined;
	const issues: InputIssue[] = [];
	for (const item of value.issues) {
		if (
			!record(item) ||
			typeof item.field !== "string" ||
			!/^(?:material\.[A-Za-z0-9_.[\]-]{1,140}|preparation\.basis_catalog(?:\[\d+\]\.(?:text|finding_ids|remaining_ids))?|preparation\.model_context\.(?:terminology\.[A-Z0-9-]{1,100}|review\.(?:AC|VC)-\d{3}\.evidence)|model_context\.references(?:\.(?:AC|VC)-\d{3})?|evidence_refs(?:\[\d+\](?:\.(?:field|path|lines))?)?|evidence_sources)$/.test(
				item.field,
			) ||
			typeof item.code !== "string" ||
			!Object.hasOwn(messages, item.code)
		)
			continue;
		const issue: InputIssue = { field: item.field, code: item.code as IssueCode };
		if (issue.code === "missing-candidates" && Array.isArray(item.choices)) {
			issue.choices = item.choices.filter(
				(choice): choice is string =>
					typeof choice === "string" && /^[A-Za-z][A-Za-z0-9-]{0,63}$/.test(choice) && !/^sk-/i.test(choice),
			);
		}
		if (
			typeof item.path === "string" &&
			/^[A-Za-z0-9_./-]{1,240}$/.test(item.path) &&
			!item.path.startsWith("/") &&
			!item.path.split("/").some((part) => !part || part === ".." || /^sk-/i.test(part))
		) {
			issue.path = item.path;
		}
		if (
			record(item.requested_lines) &&
			lineNumber(item.requested_lines.start) &&
			lineNumber(item.requested_lines.end)
		) {
			issue.requested_lines = { start: item.requested_lines.start, end: item.requested_lines.end };
		}
		if (lineNumber(item.file_line_count)) issue.file_line_count = item.file_line_count;
		if (lineNumber(item.source_line)) issue.source_line = item.source_line;
		if (
			typeof item.source_field === "string" &&
			/^(?:material|preparation|state|questions)(?:\.[A-Za-z0-9_-]+(?:\[\d+\])*)+$/.test(item.source_field) &&
			item.source_field.length <= 200
		)
			issue.source_field = item.source_field;
		issues.push(issue);
	}
	if (!issues.length) return undefined;
	const allowedFields =
		issues.some(
			(issue) => issue.code === "invalid-evidence-reference" && /^evidence_refs\[\d+\]\.field$/.test(issue.field),
		) && Array.isArray(value.allowed_fields)
			? [
					...new Set(
						value.allowed_fields
							.slice(0, MAX_ALLOWED_FIELDS)
							.filter(
								(field): field is string =>
									typeof field === "string" && field.length <= 160 && bindingHint.test(field),
							),
					),
				]
			: undefined;
	return {
		stage: "evidence-preparation",
		transport: "not-sent",
		issues,
		truncated: value.truncated,
		...(allowedFields === undefined
			? {}
			: {
					allowed_fields: allowedFields,
					allowed_fields_truncated:
						value.allowed_fields_truncated === true ||
						(Array.isArray(value.allowed_fields) && value.allowed_fields.length > MAX_ALLOWED_FIELDS),
				}),
	};
}

export function formatInputDiagnostics(value: DecisionInputDiagnostics): string {
	return [
		"Request was not sent.",
		...value.issues.map((issue) => {
			const location =
				issue.path && issue.source_line !== undefined
					? `${issue.path}:${issue.source_line}`
					: (issue.path ?? issue.source_field);
			const target = location ? ` (${location})` : "";
			const range =
				issue.requested_lines && issue.file_line_count
					? ` Lines ${issue.requested_lines.start}–${issue.requested_lines.end}, file has ${issue.file_line_count} lines.`
					: "";
			const choices = issue.choices?.length ? ` Missing: ${issue.choices.join(", ")}.` : "";
			return `${issue.field}${target}: ${messages[issue.code]}${choices}${range}`;
		}),
		...(value.allowed_fields?.length
			? [`Available evidence_refs.field paths: ${value.allowed_fields.join(", ")}.`]
			: []),
		...(value.allowed_fields_truncated ? ["Additional field paths were omitted."] : []),
		...(value.truncated ? ["Additional evidence issues were omitted."] : []),
	].join("\n");
}
