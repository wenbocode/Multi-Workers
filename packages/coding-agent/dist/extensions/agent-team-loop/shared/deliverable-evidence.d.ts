/**
 * shared/deliverable-evidence.ts — AC-006 three-channel deliverable predicate
 * (contract C5).
 *
 * A read-only worker that settles without any product must not be recorded as
 * `done`. This module answers ONE question — "did this run deliver anything?"
 * — from the files the run left behind, and is deliberately separate from
 * `hasProductEvidence()` (`pm-orchestrator.ts`), which answers the different
 * question "did this task dir ever run?" for the IN-3 empty-queue dispatch
 * guard (AC-020). The two predicates MUST coexist (design DD-07): narrowing the
 * dispatch guard would flip `trace.log`-only / placeholder-only dirs from
 * "refuse the scan" to "re-run history".
 *
 * Channels (spec §3.1, DRQ-2 calibrated):
 *   1. `report.md` / `report-<slug>.md` non-empty ⇒ delivered (`channel=report`);
 *   2. otherwise the product text (`output.md`, or the final reply when the
 *      file is still empty) is non-empty, carries at least ONE non-placeholder
 *      `## TL;DR`/`## Summary` body, and matches one delivery signal:
 *        - a machine line (`[VERIFY]` / `VERDICT=` / `TASKS=` / `[CHECKPOINT]`),
 *          at line start or inline (`channel=output`);
 *        - a referenced `<key>/evidence/**.md` that exists (and, when run.json
 *          is present, is at least as new as the run start) (`channel=output`);
 *        - `run.json.artifacts` carrying anything other than `output.md`
 *          (`channel=artifact`, forward-only: 0/30 in the historical corpus);
 *   3. otherwise `{delivered:false, channel:"none"}` ⇒ the caller folds
 *      `exitCode=2` (needs-clarification) and records the `no-product` alarm.
 *
 * Corpus replay (30 real dirs in `.agenticdoc/mw-gate-verdict-hardening/workers`)
 * yields 28 delivered / 2 correct NC / 0 false positives. The two NCs are
 * `mwg-qg-review-20261010` (a "let me organize my work" placeholder-run with no
 * signal) and `mwg-t08b-g2-surfaces` (hard-killed before `output.md`).
 *
 * NOTE the placeholder rule is "at least one non-placeholder product section",
 * NOT "every block non-placeholder": `mgh-rq2-gate-alert` / `mwg-t16-docs-closure`
 * carry a leading crash block followed by a real report, and the corpus hard
 * criterion (28/2/0) requires them delivered (design R4). The placeholder
 * literal set here is the AC-006 oracle; T-05's `shared/output-sections.ts`
 * should import/re-export from here rather than declare a second copy.
 */
/** Delivery channel that made the verdict. */
export type DeliverableChannel = "report" | "output" | "artifact" | "none";
export interface DeliverableEvidence {
    delivered: boolean;
    channel: DeliverableChannel;
    /** Short machine-ish reason (goes into the NC `## Questions` body). */
    detail: string;
}
/**
 * The 16 placeholder/default strings the writer harness can emit
 * (`worker/output-writer.ts` + `worker/worker-mode.ts` exit paths; `(none)`
 * and idle/wall collapse to one documented entry each). A section body that
 * equals one of these verbatim carries no delivery — it is what the framework
 * writes when the agent produced nothing.
 */
export declare const DELIVERABLE_PLACEHOLDERS: ReadonlySet<string>;
/** Is one section body a harness placeholder (or blank)? */
export declare function isPlaceholderBody(body: string): boolean;
/** Non-empty `report.md` / `report-<slug>.md` in the task dir, if any. Uses the
 * `worker_file` basename whitelist (minus `progress.md`) as the single source of
 * truth — `collectArtifacts` does not list `report-<slug>.md` (design R3). */
export declare function findNonEmptyReport(taskDir: string): string | undefined;
/** Does the product text carry at least one real (non-placeholder) TL;DR or
 * Summary body? Free text without section headings counts as one body. */
export declare function hasNonPlaceholderProduct(text: string): boolean;
/** `evidence/**.md` referenced by the text that resolves under the owner key's
 * `evidence/` dir (never the worker's own dir), is non-empty and — when the run
 * record exists — not older than the run start (design R1 anti-forgery). */
export declare function findReferencedEvidence(taskDir: string, text: string): string | undefined;
/** `run.json.artifacts` entries other than `output.md` (forward-only channel). */
export declare function nonOutputArtifacts(taskDir: string): string[];
/**
 * The AC-006 verdict. `outputText` is the agent's final reply (what will become
 * the new `## Summary`); it is consulted only while `output.md` is still
 * empty/missing, so an existing placeholder-only product stays authoritative
 * (a crashed run is not rescued by a later chatty reply).
 */
export declare function hasDeliverableEvidence(taskDir: string, outputText?: string): DeliverableEvidence;
//# sourceMappingURL=deliverable-evidence.d.ts.map