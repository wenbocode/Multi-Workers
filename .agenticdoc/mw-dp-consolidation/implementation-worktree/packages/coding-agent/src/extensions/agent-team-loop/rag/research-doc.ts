/**
 * rag/research-doc.ts — `rag-research` research-document validator
 * (mw-rag-integration T-09 / AC-014, VC-018).
 *
 * The single standard for the deliverable of a `rag-research` task is the
 * `§调研文档格式` section of the framework skill under
 * `packages/multi-workers/skills/mw-rag/` (its `SKILL.md`):
 * the doc lives at `.agenticdoc/<key>/rag/<server>-<slug>.md` and carries the
 * six fixed sections `## 查询` / `## 结论` / `## 引用` / `## 未解决` / `## 快照`
 * / `## 影响面`. Every citation in `## 引用` must parse under the D-004
 * grammar (`parseCitation`), and at least one must be the `::` role-prefixed
 * shape (the reference service emits `engine::path/to/file.cpp`).
 *
 * This module is pure decision logic (read-only): it turns a key directory
 * into a `ResearchDocReport` and, when the doc is absent or non-compliant,
 * into the shared `rag-required-missing` evidence line (T-05's
 * `ragRequiredMissingLine`) — the same mechanism T-10's required-citation
 * check uses, so there is never a second trace/output writer.
 *
 * Local `exists` / `local_path` verification of each citation is the audit
 * surface (`mw rag audit`, T-10); this validator stays filesystem-light — it
 * checks the doc structure and citation grammar only.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { parseCitation } from "./adapter.ts";
import { ragRequiredMissingLine } from "./evidence.ts";

/** The six fixed section titles, verbatim from the SKILL.md standard. */
export const RESEARCH_DOC_SECTIONS = ["查询", "结论", "引用", "未解决", "快照", "影响面"] as const;

export type ResearchDocSection = (typeof RESEARCH_DOC_SECTIONS)[number];

/** The rendered headings (`## <title>`), in the required order. */
export const RESEARCH_DOC_HEADINGS: readonly string[] = RESEARCH_DOC_SECTIONS.map((section) => `## ${section}`);

export interface ResearchDocReport {
	/** True when a `<server>-<slug>.md` doc exists and passes every check. */
	ok: boolean;
	/** Absolute path of the validated doc, or null when none was found. */
	docPath: string | null;
	/** Required headings present in the doc. */
	headings: string[];
	/** Required section titles missing from the doc. */
	missingSections: string[];
	/** Citation tokens found in `## 引用` that parse under D-004. */
	citations: string[];
	/** Citation-looking tokens that do NOT parse under D-004. */
	unparseable: string[];
	/** At least one parsed citation carries the `::` role prefix. */
	hasDoubleColon: boolean;
	/** Human-readable failure reasons (empty when `ok`). */
	findings: string[];
}

/** `rag/` directory under a key dir (`.agenticdoc/<key>/rag`). */
export function researchDocDir(keyDir: string): string {
	return path.join(keyDir, "rag");
}

function listResearchDocs(keyDir: string): string[] {
	let names: string[];
	try {
		names = fs.readdirSync(researchDocDir(keyDir));
	} catch {
		return [];
	}
	return names
		.filter((name) => name.endsWith(".md") && !name.startsWith("."))
		.map((name) => path.join(researchDocDir(keyDir), name))
		.sort();
}

/** Section title -> its body lines; headings are matched at `##` depth only. */
export function splitResearchDocSections(text: string): Map<string, string[]> {
	const sections = new Map<string, string[]>();
	let current: string | null = null;
	for (const raw of text.split(/\r?\n/)) {
		const match = /^##\s+(.+?)\s*$/.exec(raw.trim());
		if (match !== null) {
			current = match[1] ?? "";
			if (!sections.has(current)) sections.set(current, []);
			continue;
		}
		if (current !== null) sections.get(current)?.push(raw);
	}
	return sections;
}

/** A bullet or table row — the shapes a `## 引用` entry can take. */
function isCitationEntryLine(line: string): boolean {
	return (
		line.startsWith("- ") ||
		line.startsWith("* ") ||
		line.startsWith("+ ") ||
		line.startsWith("|") ||
		/[`]/.test(line)
	);
}

/**
 * Candidate citation tokens on one line: backtick-quoted spans first (the
 * SKILL.md rendering), otherwise whitespace-delimited tokens with at least
 * three colons. Returns the raw tokens — `parseCitation` is the only parser.
 */
function citationCandidates(line: string): string[] {
	const backticked = [...line.matchAll(/`([^`]+)`/g)]
		.map((match) => match[1] ?? "")
		.filter((span) => colonCount(span) >= 3);
	if (backticked.length > 0) return backticked;
	const tokens: string[] = [];
	for (const token of line.split(/\s+/)) {
		if (colonCount(token) >= 3) tokens.push(token);
	}
	return tokens;
}

function colonCount(value: string): number {
	let count = 0;
	for (const char of value) if (char === ":") count += 1;
	return count;
}

/**
 * Parseable D-004 citations anywhere in a free-form text (the worker's own
 * deliverable, not just a `## 引用` section). `parseCitation` is still the only
 * parser; this is the shared scan T-14's worker-finalize check uses, so the
 * trace is not the first place a citation token is judged.
 */
export function scanCitations(text: string): string[] {
	const found: string[] = [];
	for (const line of text.split(/\r?\n/)) {
		const trimmed = line.trim();
		if (trimmed === "") continue;
		for (const candidate of citationCandidates(trimmed)) {
			if (parseCitation(candidate) !== null) found.push(candidate);
		}
	}
	return found;
}

function collectCitations(lines: string[]): { citations: string[]; unparseable: string[] } {
	const citations: string[] = [];
	const unparseable: string[] = [];
	for (const line of lines) {
		const trimmed = line.trim();
		if (trimmed === "" || trimmed.startsWith("###") || /^\|[-:\s|]+\|$/.test(trimmed)) continue;
		const candidates = citationCandidates(trimmed);
		if (candidates.length === 0) {
			if (isCitationEntryLine(trimmed)) unparseable.push(trimmed);
			continue;
		}
		for (const candidate of candidates) {
			if (parseCitation(candidate) === null) unparseable.push(candidate);
			else citations.push(candidate);
		}
	}
	return { citations, unparseable };
}

/**
 * Validate the research document of one key directory. `ok` requires: a
 * `<server>-<slug>.md` exists under `<keyDir>/rag/`, all six fixed sections
 * are present, every `## 引用` entry parses under D-004, and at least one
 * citation carries the `::` role prefix.
 */
export function validateResearchDoc(keyDir: string): ResearchDocReport {
	const findings: string[] = [];
	const docs = listResearchDocs(keyDir);
	const named = docs.filter((doc) => path.basename(doc, ".md").includes("-"));
	const docPath = named[0] ?? docs[0] ?? null;

	if (docPath === null) {
		findings.push("no research document at rag/<server>-<slug>.md");
		return {
			ok: false,
			docPath: null,
			headings: [],
			missingSections: [...RESEARCH_DOC_SECTIONS],
			citations: [],
			unparseable: [],
			hasDoubleColon: false,
			findings,
		};
	}
	if (!named.includes(docPath)) {
		findings.push(`research doc '${path.basename(docPath)}' does not match <server>-<slug>.md`);
	}

	const sections = splitResearchDocSections(fs.readFileSync(docPath, "utf8"));
	const headings: string[] = [];
	const missingSections: string[] = [];
	for (const section of RESEARCH_DOC_SECTIONS) {
		if (sections.has(section)) headings.push(`## ${section}`);
		else missingSections.push(section);
	}
	if (missingSections.length > 0) {
		findings.push(`missing section(s): ${missingSections.map((section) => `## ${section}`).join(", ")}`);
	}

	const { citations, unparseable } = collectCitations(sections.get("引用") ?? []);
	if (citations.length === 0 && unparseable.length === 0) {
		findings.push("## 引用 has no citation entry");
	}
	if (unparseable.length > 0) {
		findings.push(`citation(s) not parseable under server:source:file_path:line: ${unparseable.join(", ")}`);
	}
	const hasDoubleColon = citations.some((citation) => (parseCitation(citation)?.filePath ?? "").includes("::"));
	if (citations.length > 0 && !hasDoubleColon) {
		findings.push("no citation carries the '::' role-prefixed file_path shape");
	}

	return {
		ok:
			named.includes(docPath) &&
			missingSections.length === 0 &&
			citations.length > 0 &&
			unparseable.length === 0 &&
			hasDoubleColon,
		docPath,
		headings,
		missingSections,
		citations,
		unparseable,
		hasDoubleColon,
		findings,
	};
}

/**
 * Shared `rag-required-missing` evidence line for a non-compliant research
 * doc, or null when the doc validates. T-10's required-citation path emits
 * the same line kind, so the trace has one mechanism, not two.
 */
export function researchDocEvidence(
	report: ResearchDocReport,
	role: string,
	phase: string,
	server: string,
): string | null {
	return report.ok ? null : ragRequiredMissingLine({ role, phase, server });
}

/** Compact `[VERIFY] VC-018`-shaped summary of one report. */
export function summarizeResearchDoc(report: ResearchDocReport): string {
	const citationsParseable = report.citations.length > 0 && report.unparseable.length === 0;
	return `doc_exists=${report.docPath !== null} sections=${report.headings.length} citations_parseable=${citationsParseable}`;
}
