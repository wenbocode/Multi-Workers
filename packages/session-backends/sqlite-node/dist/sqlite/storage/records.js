export function appendRecordRow(db, sessionId, record) {
    db.prepare(`INSERT INTO records
			(session_id, seq, id, lane, run_id, type, op_kind, timestamp, payload)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(sessionId, record.seq, record.id, record.lane, record.runId ?? null, record.type, record.opKind ?? null, record.timestamp, record.payload);
}
export function idExistsInRecords(db, sessionId, id) {
    return !!db
        .prepare("SELECT 1 AS found FROM records WHERE session_id = ? AND id = ? LIMIT 1")
        .get(sessionId, id);
}
export function deleteRecordRows(db, sessionId) {
    db.prepare("DELETE FROM records WHERE session_id = ?").run(sessionId);
}
export function readRecordRows(db, sessionId, query = {}) {
    const predicates = ["session_id = ?"];
    const params = [sessionId];
    if (query.lane !== undefined) {
        predicates.push("lane = ?");
        params.push(query.lane);
    }
    if (query.type !== undefined) {
        predicates.push("type = ?");
        params.push(query.type);
    }
    if (query.runId !== undefined) {
        predicates.push("run_id = ?");
        params.push(query.runId);
    }
    if (query.operationKind !== undefined) {
        predicates.push("op_kind = ?");
        params.push(query.operationKind);
    }
    if (query.afterSeq !== undefined) {
        predicates.push("seq > ?");
        params.push(query.afterSeq);
    }
    const limit = query.limit === undefined ? "" : " LIMIT ?";
    if (query.limit !== undefined)
        params.push(query.limit);
    const direction = query.order === "oldestFirst" ? "ASC" : "DESC";
    return db
        .prepare(`SELECT session_id, seq, id, lane, run_id, type, op_kind, timestamp, payload
			FROM records
			WHERE ${predicates.join(" AND ")}
			ORDER BY seq ${direction}${limit}`)
        .all(...params);
}
export function readOpenOperationRows(db, sessionId, lane, options = {}) {
    const params = [sessionId, lane];
    const limit = options.limit === undefined ? "" : " LIMIT ?";
    if (options.limit !== undefined)
        params.push(options.limit);
    return db
        .prepare(`SELECT started.session_id, started.seq, started.id, started.lane, started.run_id,
				started.type, started.op_kind, started.timestamp, started.payload
			FROM records AS started
			WHERE started.session_id = ?
				AND started.lane = ?
				AND started.type = 'operation_started'
				AND NOT EXISTS (
					SELECT 1
					FROM records AS finished
					WHERE finished.session_id = started.session_id
						AND finished.lane = started.lane
						AND finished.run_id = started.id
						AND finished.type = 'operation_finished'
						AND finished.seq > started.seq
				)
			ORDER BY started.seq DESC${limit}`)
        .all(...params);
}
//# sourceMappingURL=records.js.map