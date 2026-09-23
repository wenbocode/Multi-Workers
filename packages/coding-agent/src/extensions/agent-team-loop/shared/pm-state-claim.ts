import * as fs from "node:fs";
import * as path from "node:path";

/** Result of a pm-state.md Claim-Id sync. `reason` is set exactly when `ok`
 * is false (missing file, missing interface lines, or refused write). */
export interface PmStateClaimSyncResult {
	ok: boolean;
	reason?: string;
}

/** The '- Claim-Id:' machine-interface line. It never consumes the line
 * terminator, so the file's own newline bytes survive the replacement. */
const CLAIM_LINE_RE = /^- Claim-Id:[^\r\n]*/m;

/** The '- Key:' machine-interface line — the insertion anchor when the
 * pm-state.md predates the Claim-Id mirror (D-111): the framework's own
 * update_index.py inserts the claim line right after it. Like
 * CLAIM_LINE_RE it never consumes the line terminator. */
const KEY_LINE_RE = /^- Key:[^\r\n]*/m;

function countSeq(haystack: string, needle: string): number {
	let count = 0;
	let at = haystack.indexOf(needle);
	while (at !== -1) {
		count++;
		at = haystack.indexOf(needle, at + needle.length);
	}
	return count;
}

/**
 * Replace the '- Claim-Id:' line of `{agenticdocRoot}/{key}/pm-state.md` with
 * `claimId` — a single-line in-place replacement (design D-107). When the
 * line is missing but a '- Key:' line exists, insert the claim line directly
 * after it instead (design D-111): every key created via the TS path
 * (switch_key → IndexStore.claim) followed by advance_phase.py's 7-section
 * template has no Claim-Id line, so without the insert the "index row ==
 * mirror" equality could never converge for the most common creation path.
 *
 * Strategy: read raw bytes → detect the dominant newline (\r\n wins whenever
 * present) → replace the first `^- Claim-Id:` line without touching its line
 * terminator, or insert `- Claim-Id: <claimId>` (prefixed with the dominant
 * newline) right after the `^- Key:` line content → atomic write via a
 * same-directory `.tmp` + rename. Every other byte (7-section framework
 * template, evidence areas, CRLF/LF style) stays identical.
 * StateManager.write() must not be reused for this: it rewrites the whole
 * file as the old 3-section template.
 *
 * Failure contract: a missing file, a file with neither a '- Claim-Id:' nor
 * a '- Key:' line, or a refused (newline-violating) write returns
 * `{ ok: false, reason }` and never creates or rewrites anything. The index
 * row stays authoritative — a mirror sync failure must not block the claim
 * itself (D-108). Purely synchronous; never throws.
 */
export function syncPmStateClaimId(agenticdocRoot: string, key: string, claimId: string): PmStateClaimSyncResult {
	const file = path.join(agenticdocRoot, key, "pm-state.md");
	try {
		if (!fs.existsSync(file)) {
			return { ok: false, reason: "pm-state.md missing" };
		}
		// latin1 decodes/encodes 1 byte <-> 1 char, so regex hits are byte-exact
		// and multibyte UTF-8 content round-trips untouched.
		const text = fs.readFileSync(file).toString("latin1");
		// Dominant-newline detection (\r\n preferred), used as the P-010 guard:
		// the replacement may not flip or add any line-ending byte (this also
		// refuses a claimId that carries a line break); a refusal reports the
		// detected style and leaves the file untouched. The insert branch
		// (D-111) must add exactly one new line, in the dominant style.
		const nl = text.includes("\r\n") ? "\r\n" : "\n";
		let next: string;
		if (CLAIM_LINE_RE.test(text)) {
			next = text.replace(CLAIM_LINE_RE, `- Claim-Id: ${claimId}`);
			if (countSeq(next, "\n") !== countSeq(text, "\n") || countSeq(next, "\r\n") !== countSeq(text, "\r\n")) {
				return {
					ok: false,
					reason: `newline invariant violated (dominant ${nl === "\r\n" ? "CRLF" : "LF"} count changed)`,
				};
			}
		} else {
			const keyMatch = KEY_LINE_RE.exec(text);
			if (keyMatch === null || keyMatch.index === undefined) {
				return { ok: false, reason: "pm-state.md has no '- Key:' or '- Claim-Id:' line" };
			}
			// Insert directly after the '- Key:' line content (update_index.py's
			// own anchor), prefixed with the dominant newline: the Key line's own
			// terminator, when present, becomes the claim line's terminator; at a
			// terminator-less EOF the inserted newline terminates the Key line and
			// the claim line takes EOF. Either way exactly one new dominant-style
			// line is added and every other byte survives.
			const insertAt = keyMatch.index + keyMatch[0].length;
			next = `${text.slice(0, insertAt)}${nl}- Claim-Id: ${claimId}${text.slice(insertAt)}`;
			if (
				countSeq(next, "\n") !== countSeq(text, "\n") + 1 ||
				countSeq(next, "\r\n") !== countSeq(text, "\r\n") + (nl === "\r\n" ? 1 : 0)
			) {
				return {
					ok: false,
					reason: `newline invariant violated (dominant ${nl === "\r\n" ? "CRLF" : "LF"} count changed)`,
				};
			}
		}
		const tmpPath = `${file}.tmp`;
		fs.writeFileSync(tmpPath, Buffer.from(next, "latin1"));
		fs.renameSync(tmpPath, file);
		return { ok: true };
	} catch (err) {
		return { ok: false, reason: err instanceof Error ? err.message : String(err) };
	}
}
