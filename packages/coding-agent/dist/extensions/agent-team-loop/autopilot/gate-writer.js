/**
 * gate-writer.ts — the `/autopilot gate <id> approve|reject` answer writer
 * (goal-autopilot T-15, design D-105, AC-016).
 *
 * Answering a gate = rewriting four frontmatter fields of the gate file —
 * `status` / `answered_at` / `answered_by` (the answering window's claimId,
 * for audit) / `note` — plus, when the human passes `--authorizes` (G3/D-011),
 * the already-materialized `authorizes:` JSON-list line — under
 * `.mw/gates.lock` (O_CREAT|O_EXCL, the shared file-lock protocol). EVERY
 * other line is preserved byte-for-byte, including a trailing CR when the
 * source line had one, so hand-edited gate files keep their exact shape
 * across an answer.
 *
 * Creation is conductor-only (gates.py); this module never creates gates and
 * never reorders or synthesizes fields — conductor-created gates always
 * carry all 12 frontmatter fields (gates.py FRONTMATTER_FIELDS), so the
 * rewrite targets existing lines only. Manual file edits remain equally
 * legal answers (the file is the source of truth); this writer is just the
 * audited path. All paths are explicit parameters — nothing is derived
 * here, so tests drive the writer without a project layout.
 */
import * as fs from "node:fs";
import { DECIDE_REGISTRY } from "../shared/decide-registry.generated.js";
import { acquireLock } from "../shared/file-lock.js";
import { AUTHORIZES_ACTIONS, parseGateFile } from "./status-model.js";
const GATE_FIELD_LINE_RE = /^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*))?[ \t]*$/;
const LINE_SEPARATOR = /[\r\n\v\f\u001c-\u001e\u0085\u2028\u2029]/u;
const DECISION_FIELDS = new Set([
    "transport",
    "business",
    "effect",
    "decision_ref",
    "matter_ref",
    "substantive_version",
    "pm_note",
    "model_basis",
    "closure_kind",
]);
/** Scalars safe to render unquoted (no YAML indicators, no spaces, no
 * quotes) — identical charset to gates.py _PLAIN_SCALAR_RE. */
const PLAIN_SCALAR_RE = /^[A-Za-z0-9][A-Za-z0-9_./:+@()-]*$/;
/** Bare forms that would read back as null/bool under the gates.py subset,
 * so the renderer must quote them. */
const AMBIGUOUS_SCALARS = new Set([
    "",
    "-",
    "~",
    "null",
    "Null",
    "NULL",
    "true",
    "True",
    "TRUE",
    "false",
    "False",
    "FALSE",
    "yes",
    "Yes",
    "YES",
    "no",
    "No",
    "NO",
    "on",
    "On",
    "off",
    "Off",
]);
/** Render one YAML-subset scalar exactly like gates.py _render_scalar: plain
 * when unambiguous, single-quoted (with '' escaping) otherwise. */
export function renderScalar(value) {
    if (!AMBIGUOUS_SCALARS.has(value) && PLAIN_SCALAR_RE.test(value))
        return value;
    return `'${value.replaceAll("'", "''")}'`;
}
/** Now at UTC second precision in the Z form (`2026-09-08T12:00:00Z`) — the
 * trailing-Z ISO shape gates.py _check_iso explicitly accepts. */
function isoNowSeconds() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}
/** Parse under the lock. Exclude the decision extension only from the legacy
 * schema pass; keep every original line and its ending for the atomic rewrite. */
function readAnswerFields(content, gateFile) {
    const lines = content.split("\n");
    const end = lines.findIndex((line, i) => i > 0 && line.trim() === "---");
    if (lines[0]?.trim() !== "---" || end < 0)
        throw new Error(`${gateFile}: invalid gate frontmatter`);
    const positions = new Map();
    const decision = new Map();
    let consumed = false;
    const base = [lines[0]];
    for (let i = 1; i < end; i++) {
        const raw = lines[i].replace(/\r$/, "");
        if (LINE_SEPARATOR.test(raw))
            throw new Error(`${gateFile}: invalid line separator`);
        const match = GATE_FIELD_LINE_RE.exec(raw);
        if (match) {
            const name = match[1];
            if (positions.has(name))
                throw new Error(`${gateFile}: duplicate ${name} field`);
            positions.set(name, i);
            if ((name === "consumed_at" || name === "consumed_seq") &&
                !/^(?:|''|~|-|null|Null|NULL)$/.test(match[2] ?? "")) {
                consumed = true;
            }
            if (DECISION_FIELDS.has(name)) {
                const scalar = match[2] ?? "";
                if (scalar.startsWith('"') || (scalar.startsWith("'") && !/^'(?:[^']|'')*'$/.test(scalar))) {
                    throw new Error(`${gateFile}: invalid ${name} scalar`);
                }
                const value = scalar.startsWith("'") ? scalar.slice(1, -1).replaceAll("''", "'") : scalar;
                decision.set(name, /^(?:~|-|null|Null|NULL)$/.test(scalar) ? "" : value);
                continue;
            }
        }
        base.push(raw);
    }
    if (!positions.has("status"))
        throw new Error(`${gateFile}: no 'status:' line in frontmatter`);
    base.push("---");
    return { lines, positions, decision, consumed, gate: parseGateFile(base.join("\n"), gateFile) };
}
/** Answer one gate: take `.mw/gates.lock`, read the gate file, rewrite
 * status/answered_at/answered_by/note, and atomically replace the file
 * (tmp + rename). The read-modify-write happens under the lock so a
 * concurrent lock-respecting writer (the conductor creating gates, another
 * window answering) can never interleave with ours. */
export function answerGate(opts) {
    return writeAnswer(opts, "human");
}
/** Deposit an answer for the PM-prepared matter only. Caller authorization
 * and the actual decision evidence are verified by the producer. This writer
 * records the answer without granting authority or recording an effect. */
export function answerPreparedGate(opts) {
    return writeAnswer(opts, "decision");
}
async function writeAnswer(opts, source) {
    const bound = {
        modelBasis: opts.modelBasis,
        decisionRef: opts.decisionRef,
        matterRef: opts.matterRef,
        substantiveVersion: opts.substantiveVersion,
    };
    const scalars = { answeredBy: opts.answeredBy, answeredAt: opts.answeredAt, note: opts.note, ...bound };
    for (const [name, value] of Object.entries(scalars)) {
        if (value !== undefined && (typeof value !== "string" || LINE_SEPARATOR.test(value))) {
            return { ok: false, error: `${name} must be a single line` };
        }
    }
    if (!opts.answeredBy?.trim())
        return { ok: false, error: "answeredBy is required" };
    const at = opts.answeredAt ?? isoNowSeconds();
    const localDay = at.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(at) ||
        at.startsWith("0000") ||
        Number.isNaN(Date.parse(at)) ||
        new Date(`${localDay}T00:00:00Z`).toISOString().slice(0, 10) !== localDay) {
        return { ok: false, error: "answeredAt must be an ISO timestamp with a time zone" };
    }
    if (!DECIDE_REGISTRY["dp-gate-approve"].fixedChoiceIds.includes(opts.decision)) {
        return { ok: false, error: "unknown gate decision" };
    }
    if (opts.authorizes !== undefined && !Array.isArray(opts.authorizes)) {
        return { ok: false, error: "authorizes must be a list" };
    }
    if (source === "human") {
        if ((opts.decision !== "approve" && opts.decision !== "reject") ||
            Object.values(bound).some((v) => v !== undefined)) {
            return { ok: false, error: "the human gate command cannot record a model decision" };
        }
    }
    else {
        const missing = Object.entries(bound)
            .filter(([, v]) => !v?.trim())
            .map(([name]) => name);
        if (missing.length)
            return { ok: false, error: `missing required decision field(s): ${missing.join(", ")}` };
        if (opts.authorizes?.length)
            return { ok: false, error: "a model answer cannot grant authorizes" };
    }
    // G3 closed set (D-011): validate before touching the file so an
    // out-of-set action can never be written (fail-closed, nothing to roll back).
    // Empty/omitted means "do not write authorization" (the line is untouched).
    const authorizes = opts.authorizes !== undefined && opts.authorizes.length > 0 ? [...new Set(opts.authorizes)] : undefined;
    if (authorizes !== undefined) {
        const outOfSet = authorizes.filter((action) => !AUTHORIZES_ACTIONS.includes(action));
        if (outOfSet.length > 0) {
            return {
                ok: false,
                error: `authorizes value(s) ${outOfSet.map((v) => `'${v}'`).join(", ")} are not in the closed set ` +
                    `(expected one of: ${[...AUTHORIZES_ACTIONS].sort().join(", ")})`,
            };
        }
    }
    let release;
    try {
        release = await acquireLock(opts.lockFile, opts.lockOpts);
    }
    catch (err) {
        return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
    try {
        const { lines, positions, decision, consumed, gate } = readAnswerFields(fs.readFileSync(opts.gateFile, "utf8"), opts.gateFile);
        if (gate.status !== "pending" || gate.answeredAt || gate.answeredBy || consumed) {
            return { ok: false, error: "the recorded answer is read-only" };
        }
        const replacements = new Map([
            ["answered_at", at],
            ["answered_by", opts.answeredBy],
        ]);
        let status = "pending";
        if (source === "decision") {
            if (decision.size !== DECISION_FIELDS.size)
                return { ok: false, error: "incomplete or unprepared decision gate" };
            if (gate.note ||
                decision.get("transport") !== "pending" ||
                decision.get("effect") !== "not-started" ||
                decision.get("business") ||
                decision.get("model_basis") ||
                decision.get("closure_kind")) {
                return { ok: false, error: "gate is not awaiting its first business answer" };
            }
            if (decision.get("matter_ref") !== opts.matterRef ||
                decision.get("substantive_version") !== opts.substantiveVersion ||
                (decision.get("decision_ref") && decision.get("decision_ref") !== opts.decisionRef)) {
                return { ok: false, error: "decision is for a different matter, version or request" };
            }
            const note = decision.get("pm_note");
            if (!note?.trim() || (opts.note !== undefined && opts.note !== note)) {
                return { ok: false, error: "missing or changed pre-submission PM note" };
            }
            replacements.set("transport", "answered");
            replacements.set("business", opts.decision);
            replacements.set("model_basis", opts.modelBasis ?? "");
            replacements.set("decision_ref", opts.decisionRef ?? "");
        }
        else {
            if (decision.size)
                return { ok: false, error: "operator answers cannot replace a prepared decision" };
            status = opts.decision === "approve" ? "approved" : "rejected";
            replacements.set("status", status);
            replacements.set("note", opts.note ?? "");
            if (authorizes)
                replacements.set("authorizes", JSON.stringify(authorizes));
        }
        for (const [name, value] of replacements) {
            const index = positions.get(name);
            if (index === undefined) {
                const hint = name === "authorizes" ? " (requires conductor-materialized authorizes: [])" : "";
                return { ok: false, error: `no '${name}:' line in frontmatter${hint}` };
            }
            lines[index] = `${name}:${value ? ` ${renderScalar(value)}` : ""}${lines[index].endsWith("\r") ? "\r" : ""}`;
        }
        const tmp = `${opts.gateFile}.tmp`;
        fs.writeFileSync(tmp, lines.join("\n"), "utf8");
        fs.renameSync(tmp, opts.gateFile);
        return { ok: true, gateFile: opts.gateFile, status };
    }
    catch (err) {
        return { ok: false, error: `${opts.gateFile}: ${String(err)}` };
    }
    finally {
        release();
    }
}
//# sourceMappingURL=gate-writer.js.map