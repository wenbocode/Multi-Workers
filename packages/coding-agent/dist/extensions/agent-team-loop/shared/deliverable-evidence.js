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
import * as fs from "node:fs";
import * as path from "node:path";
import { readRunState } from "./run-store.js";
// W1 (mw-worker-output-contract): the basename whitelist now lives in the
// write-surface single source; importing it from worker-file-tool would pull the
// tool module into the evidence reader.
import { WORKER_FILE_NAME_RE } from "./write-surface.js";
/**
 * The 16 placeholder/default strings the writer harness can emit
 * (`worker/output-writer.ts` + `worker/worker-mode.ts` exit paths; `(none)`
 * and idle/wall collapse to one documented entry each). A section body that
 * equals one of these verbatim carries no delivery — it is what the framework
 * writes when the agent produced nothing.
 */
export const DELIVERABLE_PLACEHOLDERS = new Set([
    "(no conclusion)",
    "(no summary)",
    "(none)",
    "(no questions provided)",
    "Task completed successfully.",
    "Task failed.",
    "Task was cancelled (exit 130).",
    "(worker exited without writing output)",
    "Process exited before output.md was written (crash or unexpected exit).",
    "Task refused at startup (fail-closed).",
    "Task refused (image capability).",
    "Worker timed out (idle).",
    "Worker timed out (wall).",
    "Task failed during output writing.",
    "Task completed.",
    "See task output for details.",
]);
/** Is one section body a harness placeholder (or blank)? */
export function isPlaceholderBody(body) {
    const trimmed = body.trim();
    return trimmed === "" || DELIVERABLE_PLACEHOLDERS.has(trimmed);
}
/** Machine-readable delivery signals (line start or inline, spec §3.1 2(a)). */
const MACHINE_SIGNAL_RE = /\[VERIFY\]|VERDICT=|TASKS=|\[CHECKPOINT\]/;
/** `evidence/<rel>.md` references, forward or backslash separated. */
const EVIDENCE_REF_RE = /evidence[\\/]([A-Za-z0-9._\-\\/]+?\.md)/g;
function readTextFile(file) {
    try {
        return fs.readFileSync(file, "utf8");
    }
    catch {
        return "";
    }
}
/** Non-empty `report.md` / `report-<slug>.md` in the task dir, if any. Uses the
 * `worker_file` basename whitelist (minus `progress.md`) as the single source of
 * truth — `collectArtifacts` does not list `report-<slug>.md` (design R3). */
export function findNonEmptyReport(taskDir) {
    let names;
    try {
        names = fs.readdirSync(taskDir);
    }
    catch {
        return undefined;
    }
    for (const name of names.sort()) {
        if (name === "progress.md" || !WORKER_FILE_NAME_RE.test(name))
            continue;
        if (readTextFile(path.join(taskDir, name)).trim() === "")
            continue;
        return name;
    }
    return undefined;
}
/** All `## <one of names>` section bodies, in file order. */
function sectionBodies(text, names) {
    const out = [];
    let heading;
    let buf = [];
    const flush = () => {
        if (heading !== undefined && names.includes(heading))
            out.push(buf.join("\n"));
        buf = [];
    };
    for (const line of text.split(/\r?\n/)) {
        const match = /^##\s+(.+?)\s*$/.exec(line);
        if (match) {
            flush();
            heading = match[1];
            continue;
        }
        buf.push(line);
    }
    flush();
    return out;
}
/** Does the product text carry at least one real (non-placeholder) TL;DR or
 * Summary body? Free text without section headings counts as one body. */
export function hasNonPlaceholderProduct(text) {
    const bodies = sectionBodies(text, ["TL;DR", "Summary"]);
    const candidates = bodies.length > 0 ? bodies : [text];
    return candidates.some((body) => !isPlaceholderBody(body));
}
/** `evidence/**.md` referenced by the text that resolves under the owner key's
 * `evidence/` dir (never the worker's own dir), is non-empty and — when the run
 * record exists — not older than the run start (design R1 anti-forgery). */
export function findReferencedEvidence(taskDir, text) {
    const keyDir = path.dirname(path.dirname(taskDir));
    const startedAt = readRunState(taskDir)?.started_at;
    const startedAtMs = typeof startedAt === "string" ? Date.parse(startedAt) : Number.NaN;
    for (const match of text.matchAll(EVIDENCE_REF_RE)) {
        const rel = match[1].replace(/\\/g, "/");
        if (rel === "" || rel.includes(".."))
            continue;
        const candidate = path.join(keyDir, "evidence", rel);
        let stat;
        try {
            stat = fs.statSync(candidate);
        }
        catch {
            continue;
        }
        if (!stat.isFile() || stat.size === 0)
            continue;
        if (Number.isFinite(startedAtMs) && stat.mtimeMs < startedAtMs)
            continue;
        return `evidence/${rel}`;
    }
    return undefined;
}
/** `run.json.artifacts` entries other than `output.md` (forward-only channel). */
export function nonOutputArtifacts(taskDir) {
    const artifacts = readRunState(taskDir)?.artifacts;
    if (!Array.isArray(artifacts))
        return [];
    return artifacts.filter((name) => name !== "output.md");
}
/**
 * The AC-006 verdict. `outputText` is the agent's final reply (what will become
 * the new `## Summary`); it is consulted only while `output.md` is still
 * empty/missing, so an existing placeholder-only product stays authoritative
 * (a crashed run is not rescued by a later chatty reply).
 */
export function hasDeliverableEvidence(taskDir, outputText = "") {
    // Channel 1 — a written report is the strongest possible evidence.
    const report = findNonEmptyReport(taskDir);
    if (report !== undefined) {
        return { delivered: true, channel: "report", detail: report };
    }
    // Channel 2 — the product text (on-disk output.md wins over the reply).
    const existing = readTextFile(path.join(taskDir, "output.md"));
    const productText = existing.trim() !== "" ? existing : outputText;
    if (productText.trim() === "") {
        return { delivered: false, channel: "none", detail: "no report file and no output text" };
    }
    if (!hasNonPlaceholderProduct(productText)) {
        return { delivered: false, channel: "none", detail: "output.md carries only placeholder sections" };
    }
    const machine = MACHINE_SIGNAL_RE.exec(productText)?.[0];
    if (machine !== undefined) {
        return { delivered: true, channel: "output", detail: `output.md machine line ${machine}` };
    }
    const referenced = findReferencedEvidence(taskDir, productText);
    if (referenced !== undefined) {
        return { delivered: true, channel: "output", detail: `references existing ${referenced}` };
    }
    const artifacts = nonOutputArtifacts(taskDir);
    if (artifacts.length > 0) {
        return { delivered: true, channel: "artifact", detail: `artifacts: ${artifacts.join(", ")}` };
    }
    return {
        delivered: false,
        channel: "none",
        detail: "output.md has no machine line, no referenced evidence and no artifacts",
    };
}
//# sourceMappingURL=deliverable-evidence.js.map