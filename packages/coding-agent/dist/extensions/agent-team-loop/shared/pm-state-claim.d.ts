/** Result of a pm-state.md Claim-Id sync. `reason` is set exactly when `ok`
 * is false (missing file, missing interface lines, or refused write). */
export interface PmStateClaimSyncResult {
    ok: boolean;
    reason?: string;
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
export declare function syncPmStateClaimId(agenticdocRoot: string, key: string, claimId: string): PmStateClaimSyncResult;
//# sourceMappingURL=pm-state-claim.d.ts.map