export function entryPayload(entry) {
    const { type: _type, id: _id, seq: _seq, parentId: _parentId, timestamp: _timestamp, ...payload } = entry;
    return payload;
}
function orderedSql(order) {
    return order === "oldestFirst" ? "ASC" : "DESC";
}
export function insertEntryRow(db, sessionId, entry) {
    db.prepare("INSERT INTO entries (session_id, id, seq, parent_id, type, timestamp, payload) VALUES (?, ?, ?, ?, ?, ?, ?)").run(sessionId, entry.id, entry.seq, entry.parentId, entry.type, entry.timestamp, entry.payload);
}
export function readEntryRow(db, sessionId, entryId) {
    return db
        .prepare("SELECT session_id, seq, id, parent_id, type, timestamp, payload FROM entries WHERE session_id = ? AND id = ?")
        .get(sessionId, entryId);
}
export function readEntryRows(db, sessionId, options = {}) {
    const predicates = ["session_id = ?"];
    const params = [sessionId];
    if (options.afterSeq !== undefined) {
        predicates.push("seq > ?");
        params.push(options.afterSeq);
    }
    return db
        .prepare(`SELECT session_id, seq, id, parent_id, type, timestamp, payload
			FROM entries
			WHERE ${predicates.join(" AND ")}
			ORDER BY seq ${orderedSql(options.order)}`)
        .all(...params);
}
export function idExistsInEntries(db, sessionId, id) {
    return !!db
        .prepare("SELECT 1 AS found FROM entries WHERE session_id = ? AND id = ? LIMIT 1")
        .get(sessionId, id);
}
export function deleteEntryRows(db, sessionId) {
    db.prepare("DELETE FROM entries WHERE session_id = ?").run(sessionId);
}
//# sourceMappingURL=entries.js.map