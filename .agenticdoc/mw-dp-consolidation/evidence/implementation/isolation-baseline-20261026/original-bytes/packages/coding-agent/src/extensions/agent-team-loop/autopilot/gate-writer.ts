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
import { acquireLock, type LockOptions } from "../shared/file-lock.ts";
import { AUTHORIZES_ACTIONS } from "./status-model.ts";

export interface AnswerGateOptions {
	/** Path of the gate .md file to answer. */
	gateFile: string;
	/** The `.mw/gates.lock` path (O_CREAT|O_EXCL). */
	lockFile: string;
	decision: "approve" | "reject";
	/** Free-form single-line answer note. Omitted → the note field is
	 * cleared (rewritten to its empty form). */
	note?: string;
	/** Audit identity written to `answered_by` — the answering window's
	 * claimId (host:pid). */
	answeredBy: string;
	/** Timestamp override for `answered_at`. Defaults to now at second
	 * precision in the `...Z` form gates.py _check_iso explicitly accepts. */
	answeredAt?: string;
	/** G3 (D-011/D-012): action types this answer authorizes, from the closed
	 * set {@link AUTHORIZES_ACTIONS} `{retry, contract-change}`. Values outside
	 * the set are refused fail-closed and nothing is written. Omitted or empty
	 * → the existing `authorizes:` line is left untouched. The line must
	 * already exist (the conductor materializes `authorizes: []` for new
	 * gates): this writer only rewrites existing lines and refuses otherwise. */
	authorizes?: string[];
	/** Lock retry options (tests inject small values). */
	lockOpts?: LockOptions;
}

export type AnswerGateResult =
	| { ok: true; gateFile: string; status: "approved" | "rejected" }
	| { ok: false; error: string };

const GATE_FIELD_LINE_RE = /^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*))?[ \t]*$/;

/** The frontmatter fields an answer may rewrite (gates.py FRONTMATTER_FIELDS
 * members plus the recognized `authorizes` extension field, whose line is
 * materialized by the conductor). Only already-existing lines are rewritten;
 * `authorizes` is additionally refused when its line is absent. */
const ANSWER_FIELDS = ["status", "answered_at", "answered_by", "note", "authorizes"] as const;

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
export function renderScalar(value: string): string {
	if (!AMBIGUOUS_SCALARS.has(value) && PLAIN_SCALAR_RE.test(value)) return value;
	return `'${value.replaceAll("'", "''")}'`;
}

/** Now at UTC second precision in the Z form (`2026-09-08T12:00:00Z`) — the
 * trailing-Z ISO shape gates.py _check_iso explicitly accepts. */
function isoNowSeconds(): string {
	return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

type RewriteResult = { ok: true; content: string } | { ok: false; error: string };

/** Rewrite the answer fields of a gate file's frontmatter. Only the answer
 * lines change; every other line — including the body, context_refs list, and
 * any CRLF endings — is preserved byte-for-byte. A requested `authorizes`
 * whose line does not exist is refused (never silently dropped). */
function rewriteAnswerFields(content: string, replacements: Map<string, string>, gateFile: string): RewriteResult {
	const lines = content.split("\n");
	if (lines.length === 0 || lines[0].trim() !== "---") {
		return { ok: false, error: `${gateFile}: frontmatter must open with a '---' line` };
	}
	let end = -1;
	for (let i = 1; i < lines.length; i++) {
		if (lines[i].trim() === "---") {
			end = i;
			break;
		}
	}
	if (end < 0) return { ok: false, error: `${gateFile}: frontmatter never closes with a '---' line` };
	const rewritten = new Set<string>();
	for (let i = 1; i < end; i++) {
		const raw = lines[i];
		const probe = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
		const m = GATE_FIELD_LINE_RE.exec(probe);
		if (m === null) continue; // list item / prose — preserved as-is
		const name = m[1] ?? "";
		if (!(ANSWER_FIELDS as readonly string[]).includes(name) || rewritten.has(name)) continue;
		// Only fields this answer actually supplies are rewritten; a recognized
		// field with no replacement (e.g. `authorizes` when the human did not pass
		// --authorizes) keeps its existing line untouched.
		if (!replacements.has(name)) continue;
		const value = replacements.get(name) ?? "";
		// An empty value renders as the bare `field:` line — the same shape
		// gates.py create() writes for empty optionals.
		lines[i] = (value === "" ? `${name}:` : `${name}: ${value}`) + (raw.endsWith("\r") ? "\r" : "");
		rewritten.add(name);
	}
	if (!rewritten.has("status")) {
		return { ok: false, error: `${gateFile}: no 'status:' line in frontmatter — not a gate file (or corrupt)` };
	}
	// G3 boundary (D-012): an explicit authorization must never be silently
	// dropped. Only existing lines are rewritten, so a gate file without the
	// conductor-materialized `authorizes:` line cannot receive one here.
	if (replacements.has("authorizes") && !rewritten.has("authorizes")) {
		return {
			ok: false,
			error:
				`${gateFile}: no 'authorizes:' line in frontmatter — this writer only rewrites existing lines. ` +
				"The conductor materializes 'authorizes: []' for new gates; add that line manually and retry, " +
				"or answer without --authorizes.",
		};
	}
	return { ok: true, content: lines.join("\n") };
}

/** Answer one gate: take `.mw/gates.lock`, read the gate file, rewrite
 * status/answered_at/answered_by/note, and atomically replace the file
 * (tmp + rename). The read-modify-write happens under the lock so a
 * concurrent lock-respecting writer (the conductor creating gates, another
 * window answering) can never interleave with ours. */
export async function answerGate(opts: AnswerGateOptions): Promise<AnswerGateResult> {
	const status = opts.decision === "approve" ? "approved" : "rejected";
	if (opts.note !== undefined && /[\r\n]/.test(opts.note)) {
		return { ok: false, error: "note must be a single line (frontmatter scalars cannot span lines)" };
	}
	// G3 closed set (D-011): validate before touching the file so an
	// out-of-set action can never be written (fail-closed, nothing to roll back).
	// Empty/omitted means "do not write authorization" (the line is untouched).
	const authorizes =
		opts.authorizes !== undefined && opts.authorizes.length > 0 ? [...new Set(opts.authorizes)] : undefined;
	if (authorizes !== undefined) {
		const outOfSet = authorizes.filter((action) => !(AUTHORIZES_ACTIONS as readonly string[]).includes(action));
		if (outOfSet.length > 0) {
			return {
				ok: false,
				error:
					`authorizes value(s) ${outOfSet.map((v) => `'${v}'`).join(", ")} are not in the closed set ` +
					`(expected one of: ${[...AUTHORIZES_ACTIONS].sort().join(", ")})`,
			};
		}
	}
	const replacements = new Map<string, string>([
		["status", status],
		["answered_at", opts.answeredAt ?? isoNowSeconds()],
		["answered_by", opts.answeredBy === "" ? "" : renderScalar(opts.answeredBy)],
		["note", opts.note === undefined ? "" : renderScalar(opts.note)],
	]);
	if (authorizes !== undefined) replacements.set("authorizes", renderScalar(JSON.stringify(authorizes)));

	let release: () => void;
	try {
		release = await acquireLock(opts.lockFile, opts.lockOpts);
	} catch (err) {
		return { ok: false, error: err instanceof Error ? err.message : String(err) };
	}
	try {
		let content: string;
		try {
			content = fs.readFileSync(opts.gateFile, "utf8");
		} catch (err) {
			return { ok: false, error: `gate file not readable: ${opts.gateFile} (${String(err)})` };
		}
		const rewritten = rewriteAnswerFields(content, replacements, opts.gateFile);
		if (!rewritten.ok) return { ok: false, error: rewritten.error };
		try {
			const tmp = `${opts.gateFile}.tmp`;
			fs.writeFileSync(tmp, rewritten.content, "utf8");
			fs.renameSync(tmp, opts.gateFile);
		} catch (err) {
			return { ok: false, error: `cannot write ${opts.gateFile}: ${String(err)}` };
		}
		return { ok: true, gateFile: opts.gateFile, status };
	} finally {
		release();
	}
}
