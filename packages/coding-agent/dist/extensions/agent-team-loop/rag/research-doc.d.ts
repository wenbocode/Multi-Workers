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
/** The six fixed section titles, verbatim from the SKILL.md standard. */
export declare const RESEARCH_DOC_SECTIONS: readonly ["查询", "结论", "引用", "未解决", "快照", "影响面"];
export type ResearchDocSection = (typeof RESEARCH_DOC_SECTIONS)[number];
/** The rendered headings (`## <title>`), in the required order. */
export declare const RESEARCH_DOC_HEADINGS: readonly string[];
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
export declare function researchDocDir(keyDir: string): string;
/** Section title -> its body lines; headings are matched at `##` depth only. */
export declare function splitResearchDocSections(text: string): Map<string, string[]>;
/**
 * Parseable D-004 citations anywhere in a free-form text (the worker's own
 * deliverable, not just a `## 引用` section). `parseCitation` is still the only
 * parser; this is the shared scan T-14's worker-finalize check uses, so the
 * trace is not the first place a citation token is judged.
 */
export declare function scanCitations(text: string): string[];
/**
 * Validate the research document of one key directory. `ok` requires: a
 * `<server>-<slug>.md` exists under `<keyDir>/rag/`, all six fixed sections
 * are present, every `## 引用` entry parses under D-004, and at least one
 * citation carries the `::` role prefix.
 */
export declare function validateResearchDoc(keyDir: string): ResearchDocReport;
/**
 * Shared `rag-required-missing` evidence line for a non-compliant research
 * doc, or null when the doc validates. T-10's required-citation path emits
 * the same line kind, so the trace has one mechanism, not two.
 */
export declare function researchDocEvidence(report: ResearchDocReport, role: string, phase: string, server: string): string | null;
/** Compact `[VERIFY] VC-018`-shaped summary of one report. */
export declare function summarizeResearchDoc(report: ResearchDocReport): string;
//# sourceMappingURL=research-doc.d.ts.map