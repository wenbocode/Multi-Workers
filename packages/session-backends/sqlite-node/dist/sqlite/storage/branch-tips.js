export function readBranchTipIds(db, sessionId) {
    return db
        .prepare("SELECT tip_id FROM branch_tips WHERE session_id = ? ORDER BY tip_id")
        .all(sessionId)
        .map((row) => row.tip_id);
}
export function readBranchTipBranchId(db, sessionId, tipId) {
    const tip = db
        .prepare("SELECT branch_id FROM branch_tips WHERE session_id = ? AND tip_id = ?")
        .get(sessionId, tipId);
    return tip?.branch_id;
}
export function insertBranchTip(db, sessionId, tipId, branchId) {
    db.prepare("INSERT INTO branch_tips (session_id, tip_id, branch_id) VALUES (?, ?, ?)").run(sessionId, tipId, branchId);
}
export function updateBranchTip(db, sessionId, branchId, oldTipId, newTipId) {
    const result = db
        .prepare("UPDATE branch_tips SET tip_id = ? WHERE session_id = ? AND branch_id = ? AND tip_id = ?")
        .run(newTipId, sessionId, branchId, oldTipId);
    return result.changes === 1;
}
export function deleteBranchTips(db, sessionId) {
    db.prepare("DELETE FROM branch_tips WHERE session_id = ?").run(sessionId);
}
//# sourceMappingURL=branch-tips.js.map