import { SessionError } from "@earendil-works/pi-agent-core";
import { uuidv7 } from "@earendil-works/pi-ai";
import { copyBranchEntriesThroughSeq, deleteBranchEntries, insertBranchEntriesForPath, insertBranchEntry, readBranchContainingEntry, } from "./storage/branch-entries.js";
import { deleteBranchTips, insertBranchTip, readBranchTipBranchId, updateBranchTip } from "./storage/branch-tips.js";
export function deleteBranchCache(db, sessionId) {
    deleteBranchTips(db, sessionId);
    deleteBranchEntries(db, sessionId);
}
export function rebuildBranchCache(db, sessionId) {
    const tips = db
        .prepare(`SELECT leaf.id
			FROM entries AS leaf
			WHERE leaf.session_id = ?
				AND NOT EXISTS (
					SELECT 1 FROM entries AS child WHERE child.session_id = leaf.session_id AND child.parent_id = leaf.id
				)
			ORDER BY leaf.seq`)
        .all(sessionId);
    deleteBranchCache(db, sessionId);
    for (const tip of tips)
        buildCachedBranch(db, sessionId, tip.id);
}
export function buildCachedBranch(db, sessionId, leafId) {
    db.exec("SAVEPOINT build_branch_cache");
    try {
        const branchId = uuidv7();
        insertBranchEntriesForPath(db, sessionId, branchId, leafId);
        insertBranchTip(db, sessionId, leafId, branchId);
        db.exec("RELEASE SAVEPOINT build_branch_cache");
    }
    catch (error) {
        try {
            db.exec("ROLLBACK TO SAVEPOINT build_branch_cache");
            db.exec("RELEASE SAVEPOINT build_branch_cache");
        }
        catch {
            // Preserve the original build failure.
        }
        if (error instanceof SessionError)
            throw error;
        throw new SessionError("storage", `Failed to build SQLite branch cache at entry ${leafId}`, error instanceof Error ? error : undefined);
    }
}
function extendBranch(db, sessionId, branchId, parentId, entryId, entrySeq, entryType, customType) {
    insertBranchEntry(db, sessionId, branchId, entryId, entrySeq, entryType, customType);
    if (!updateBranchTip(db, sessionId, branchId, parentId, entryId)) {
        throw new SessionError("invalid_entry", `Branch tip ${parentId} changed during append`);
    }
}
export function appendEntryToBranchCache(db, sessionId, entryId, entrySeq, entryType, customType, parentId) {
    if (parentId === null) {
        const branchId = uuidv7();
        insertBranchEntry(db, sessionId, branchId, entryId, entrySeq, entryType, customType);
        insertBranchTip(db, sessionId, entryId, branchId);
        return;
    }
    const tipBranchId = readBranchTipBranchId(db, sessionId, parentId);
    if (tipBranchId !== undefined) {
        extendBranch(db, sessionId, tipBranchId, parentId, entryId, entrySeq, entryType, customType);
        return;
    }
    const source = readBranchContainingEntry(db, sessionId, parentId);
    if (!source) {
        throw new SessionError("invalid_entry", `Branch cache has no branch containing parent entry ${parentId}`);
    }
    const branchId = uuidv7();
    copyBranchEntriesThroughSeq(db, sessionId, branchId, source.branchId, source.entrySeq);
    insertBranchEntry(db, sessionId, branchId, entryId, entrySeq, entryType, customType);
    insertBranchTip(db, sessionId, entryId, branchId);
}
//# sourceMappingURL=branch-cache.js.map