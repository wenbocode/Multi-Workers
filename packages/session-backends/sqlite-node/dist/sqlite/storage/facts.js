export function appendFact(db, sessionId, seq, kind, key, value) {
    db.prepare("INSERT INTO facts (session_id, seq, kind, key, value) VALUES (?, ?, ?, ?, ?)").run(sessionId, seq, kind, key, value);
}
export function readLatestFact(db, sessionId, kind, key) {
    return db
        .prepare(`SELECT session_id, seq, kind, key, value
			FROM facts
			WHERE session_id = ? AND kind = ? AND key IS ?
			ORDER BY seq DESC
			LIMIT 1`)
        .get(sessionId, kind, key);
}
export function readLatestLabelFacts(db, sessionId) {
    return db
        .prepare(`SELECT key, value FROM (
				SELECT key, value, ROW_NUMBER() OVER (PARTITION BY key ORDER BY seq DESC) AS rank
				FROM facts
				WHERE session_id = ? AND kind = 'label'
			)
			WHERE rank = 1 AND value IS NOT NULL
			ORDER BY key`)
        .all(sessionId);
}
export function readFactRows(db, sessionId, options = {}) {
    const predicates = ["session_id = ?"];
    const params = [sessionId];
    if (options.afterSeq !== undefined) {
        predicates.push("seq > ?");
        params.push(options.afterSeq);
    }
    return db
        .prepare(`SELECT session_id, seq, kind, key, value
			FROM facts
			WHERE ${predicates.join(" AND ")}
			ORDER BY seq`)
        .all(...params);
}
export function deleteFactRows(db, sessionId) {
    db.prepare("DELETE FROM facts WHERE session_id = ?").run(sessionId);
}
//# sourceMappingURL=facts.js.map