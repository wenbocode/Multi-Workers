/**
 * pm/review-split-gate.ts — the `plan`-tier dispatch short-circuit (card T-11,
 * key `claim-driven-review-orchestration`; design §2.2, spec AC-S2).
 *
 * The `plan` tier promises "visible, reversible, ZERO side effects": produce
 * the split manifest plus ONE receipt line and dispatch nothing. Both dispatch
 * entries in `pm/ui-bridge.ts` write the task directory/task.md
 * (`writeDispatchTaskMd`) and then the queue row (`dispatchTask`), so the
 * short-circuit has to sit BETWEEN `readDispatchCard` and
 * `writeDispatchTaskMd` — earlier refusals would lose the card verdict, later
 * ones would already have created `workers/<taskKey>/` and a `_workers.parallel`
 * row (GC-3).
 *
 * What this gate may write: exactly one file,
 * `<agenticdocRoot>/<ownerKey>/evidence/split/review-<taskKey>-manifest.json`
 * (`mkdirSync` + `.tmp` + `rename`). It never creates `workers/<taskKey>/`,
 * never writes a `task.md`, and never touches a queue file — those bytes are
 * the difference between `plan` and `on`.
 *
 * What this gate may READ: the card (once) and
 * `<agenticdocRoot>/<ownerKey>/spec.md` (at most once, only to build the AC
 * index of card T-12 — an absent spec is an empty index, never an error). No
 * other file, no command, no model call.
 *
 * `off` and `on` are not this module's business: `off` returns `null` (the
 * dispatch proceeds byte-identically, AC-007) and `on` is a later stage.
 *
 * Total by construction (P-048): nothing here throws. A card that cannot be
 * read, an unwritable manifest directory, or any unexpected error degrades to
 * `[review-split] mode=plan error=<code>` so the dispatch is still stopped (the
 * mode was `plan`) and the operator sees why. A non-`review` card and a card of
 * an unreadable type return `null` silently — the gate only speaks for review
 * cards, and a `coding` dispatch under `plan` keeps today's behaviour.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { inspectEnvelope } from "../shared/dispatch-card.js";
import { resolveReviewSplit } from "../shared/review-split.js";
import { buildSplitManifest, serializeSplitManifest, } from "../shared/split-manifest.js";
import { canonicalizeLocator, planReviewSplit } from "./review-split-plan.js";
// ── constants ───────────────────────────────────────────────────────────────
/** Directory of the split evidence, relative to the owner key (design §2.3). */
export const REVIEW_SPLIT_MANIFEST_DIR = "evidence/split";
/** The only card type the `plan` gate splits. */
export const REVIEW_SPLIT_CARD_TYPE = "review";
/** File (under the owner key) the AC index is read from — the ONLY other read. */
export const REVIEW_SPLIT_SPEC_FILE = "spec.md";
/** `AC-<nnn>` occurrence (first line of an id wins in the index). */
const AC_ID_SOURCE = "AC-\\d{3}";
/** Errno shape (`ENOENT`, `EACCES`, `ENOTDIR`, …) — the only codes reported
 * verbatim; anything else is an internal failure. */
const ERRNO_RE = /^E[A-Z0-9_]+$/;
// ── paths ───────────────────────────────────────────────────────────────────
/** `evidence/split/review-<taskKey>-manifest.json` under the owner key. */
export function reviewSplitManifestPath(input) {
    return path.join(input.agenticdocRoot, input.ownerKey, REVIEW_SPLIT_MANIFEST_DIR, `review-${input.taskKey}-manifest.json`);
}
/**
 * The receipt's manifest reference: `relative(projectDir, manifestPath)` with
 * posix separators (a grep-able, checkout-stable string), falling back to the
 * basename when the manifest sits outside the project root.
 */
function manifestReceiptPath(projectDir, manifestPath) {
    const rel = path.relative(projectDir, manifestPath);
    if (rel === "" || rel.startsWith("..") || path.isAbsolute(rel))
        return path.basename(manifestPath);
    return rel.split(path.sep).join("/");
}
// ── manifest write (the ONLY side effect of this module) ─────────────────────
/**
 * Write `text` to `manifestPath` atomically: `mkdirSync(recursive)` for the key's
 * evidence dir, then `.tmp` + `rename` so a reader never sees a half-written
 * manifest. A failed rename removes the temp file and rethrows; the caller
 * degrades it to an `error=<code>` receipt (never a throw out of the gate).
 * Re-running with the same input rewrites identical bytes (idempotent).
 */
function writeManifestAtomic(manifestPath, text) {
    fs.mkdirSync(path.dirname(manifestPath), { recursive: true });
    const tmpPath = `${manifestPath}.tmp`;
    fs.writeFileSync(tmpPath, text, "utf8");
    try {
        fs.renameSync(tmpPath, manifestPath);
    }
    catch (err) {
        try {
            fs.unlinkSync(tmpPath);
        }
        catch {
            // Best effort: the rename failure is what the caller must report.
        }
        throw err;
    }
}
/**
 * AC id → `"spec.md:<line>"` from `<agenticdocRoot>/<ownerKey>/spec.md`
 * (cards T-12 item 7, T-13 item 2): the deterministic bridge that lets a prose
 * ask naming `AC-013` still carry a 定位. The value is the CANONICAL form
 * ({@link canonicalizeLocator}), never a relative path: the pack unit is a 定位
 * cluster, so a key deeper in the tree would otherwise split the same card
 * differently (`evidence/m1-exit-probe-20261022.md` §6.1 defect 1). First
 * occurrence wins, line numbers are 1-based.
 * A missing/unreadable spec is an EMPTY index, never an error: a card without
 * the bridge degrades to `extract:ac-unresolved:<id>`. No other file is read and
 * no command runs (the whole index is one `readFileSync`).
 */
function buildAcIndex(input) {
    const specPath = path.join(input.agenticdocRoot, input.ownerKey, REVIEW_SPLIT_SPEC_FILE);
    const index = {};
    let text;
    try {
        text = fs.readFileSync(specPath, "utf8");
    }
    catch {
        // Absent spec = no bridge; the plan reports the unresolved ids itself.
        return index;
    }
    const idPattern = new RegExp(AC_ID_SOURCE, "g");
    for (const [offset, line] of text.split(/\r\n|\r|\n/).entries()) {
        idPattern.lastIndex = 0;
        for (;;) {
            const match = idPattern.exec(line);
            if (match === null)
                break;
            const id = match[0];
            if (index[id] === undefined)
                index[id] = canonicalizeLocator(`${specPath}:${offset + 1}`);
        }
    }
    return index;
}
/**
 * Manifest of a plan that found no claim source. `planReviewSplit` returns no
 * manifest body for that branch (`extract:no-source`), but the artifact still
 * has to exist and be readable: `ids=[]` is the fact the merge gate reads, and
 * the L0 counts come from the plan's own `l0` — `unmapped` carries EVERY ask
 * summary, so `asks - mapped === unmapped.length` holds in the artifact too
 * (card T-12: the T-10 no-source branch wrote `unmapped=[]` and broke it).
 */
function noSourceManifest(taskKey, cardText, plan) {
    const l0 = {
        asks: plan.l0.asks,
        mapped: plan.l0.mapped,
        unmapped: [...plan.l0.unmapped],
    };
    return buildSplitManifest({
        parent: taskKey,
        mode: "plan",
        parentText: cardText,
        ids: [],
        units: [],
        packing: [],
        l0,
    });
}
/** Errno code of a failure, `internal` for anything without one. */
function gateErrorCode(err) {
    const code = err?.code;
    return typeof code === "string" && ERRNO_RE.test(code) ? code : "internal";
}
// ── gate ────────────────────────────────────────────────────────────────────
/** The intercept proper; `null` means "let the dispatch run unchanged". */
function interceptReviewSplitPlan(input) {
    // 1. Cheapest and most decisive: the switch. `off`/`on` never read a card.
    if (resolveReviewSplit(input.projectDir).mode !== "plan")
        return null;
    // 2. Read the card ONCE (the dispatch's own readDispatchCard already
    //    succeeded, so this is a re-read for the gate's own inputs).
    const raw = typeof input.cardPath === "string" ? input.cardPath.trim() : "";
    const resolvedPath = path.isAbsolute(raw) ? path.resolve(raw) : path.resolve(input.projectDir, raw);
    const cardText = fs.readFileSync(resolvedPath, "utf8");
    // 3. Only a review card is split; any other type keeps today's dispatch and
    //    gets no output at all (the gate is not a receipt channel).
    if (inspectEnvelope(cardText).type !== REVIEW_SPLIT_CARD_TYPE)
        return null;
    // 4. Plan it (pure), then seal the artifact. The AC index comes from the
    //    key's `spec.md` only — the bridge of card T-12, no other read.
    const plan = planReviewSplit({
        taskKey: input.taskKey,
        projectDir: input.projectDir,
        cardText,
        mode: "plan",
        acIndex: buildAcIndex(input),
    });
    const manifest = plan.manifest ?? noSourceManifest(input.taskKey, cardText, plan);
    const manifestPath = reviewSplitManifestPath(input);
    writeManifestAtomic(manifestPath, serializeSplitManifest(manifest));
    return {
        text: `${plan.receipt}\n[review-split] manifest=${manifestReceiptPath(input.projectDir, manifestPath)}`,
        manifestPath,
    };
}
/**
 * `plan`-tier gate for one dispatch: `null` when the dispatch must proceed
 * byte-identically (`off`, `on`, non-review card), the receipt + manifest when
 * the dispatch was intercepted, and a non-throwing `error=<code>` receipt when
 * the plan could not be produced (still intercepted: `mode=plan` was explicit).
 */
export function planReviewSplitGate(input) {
    try {
        return interceptReviewSplitPlan(input);
    }
    catch (err) {
        return { text: `[review-split] mode=plan error=${gateErrorCode(err)}`, manifestPath: "" };
    }
}
//# sourceMappingURL=review-split-gate.js.map