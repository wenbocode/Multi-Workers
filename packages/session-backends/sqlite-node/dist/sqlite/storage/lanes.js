import { SessionError } from "@earendil-works/pi-agent-core";
export function createInitialLane(db, sessionId, lane = "main", leafId = null) {
    db.prepare("INSERT INTO lanes (session_id, lane, leaf_id) VALUES (?, ?, ?)").run(sessionId, lane, leafId);
}
export function readLanes(db, sessionId) {
    const rows = db
        .prepare(`SELECT
				l.session_id,
				l.lane,
				l.leaf_id,
				(l.leaf_id IS NULL OR EXISTS (
					SELECT 1 FROM entries AS e WHERE e.session_id = l.session_id AND e.id = l.leaf_id
				)) AS leaf_exists
			FROM lanes AS l
			WHERE l.session_id = ?
			ORDER BY l.lane`)
        .all(sessionId);
    for (const row of rows) {
        if (row.leaf_exists === 0) {
            throw new SessionError("storage", `Lane ${row.lane} points at missing entry ${row.leaf_id}`);
        }
    }
    return rows.map(({ session_id, lane, leaf_id }) => ({ session_id, lane, leaf_id }));
}
export function readLane(db, sessionId, lane) {
    return db
        .prepare("SELECT session_id, lane, leaf_id FROM lanes WHERE session_id = ? AND lane = ?")
        .get(sessionId, lane);
}
export function readLaneHead(db, sessionId, lane) {
    const row = db
        .prepare(`SELECT
				l.leaf_id,
				(l.leaf_id IS NULL OR EXISTS (
					SELECT 1 FROM entries AS e WHERE e.session_id = l.session_id AND e.id = l.leaf_id
				)) AS leaf_exists
			FROM lanes AS l
			WHERE l.session_id = ? AND l.lane = ?`)
        .get(sessionId, lane);
    if (!row)
        throw new SessionError("invalid_lane", `Lane not found: ${lane}`);
    if (row.leaf_exists === 0)
        throw new SessionError("storage", `Entry ${row.leaf_id} not found`);
    return { leafId: row.leaf_id };
}
export function createLane(db, sessionId, seq, lane, leafId) {
    db.prepare("INSERT INTO lanes (session_id, lane, leaf_id) VALUES (?, ?, ?)").run(sessionId, lane, leafId);
    appendLaneMove(db, sessionId, seq, lane, leafId);
}
export function moveLane(db, sessionId, seq, lane, leafId) {
    const result = db
        .prepare("UPDATE lanes SET leaf_id = ? WHERE session_id = ? AND lane = ?")
        .run(leafId, sessionId, lane);
    if (result.changes !== 1)
        throw new SessionError("invalid_lane", `Lane not found: ${lane}`);
    appendLaneMove(db, sessionId, seq, lane, leafId);
}
export function setLaneLeaf(db, sessionId, lane, leafId) {
    const result = db
        .prepare("UPDATE lanes SET leaf_id = ? WHERE session_id = ? AND lane = ?")
        .run(leafId, sessionId, lane);
    if (result.changes !== 1)
        throw new SessionError("invalid_lane", `Lane not found: ${lane}`);
}
export function readLaneMoveRows(db, sessionId, options = {}) {
    const predicates = ["session_id = ?"];
    const params = [sessionId];
    if (options.afterSeq !== undefined) {
        predicates.push("seq > ?");
        params.push(options.afterSeq);
    }
    return db
        .prepare(`SELECT session_id, seq, lane, leaf_id
			FROM lane_moves
			WHERE ${predicates.join(" AND ")}
			ORDER BY seq`)
        .all(...params);
}
export function deleteLaneRows(db, sessionId) {
    db.prepare("DELETE FROM lane_moves WHERE session_id = ?").run(sessionId);
    db.prepare("DELETE FROM lanes WHERE session_id = ?").run(sessionId);
}
function appendLaneMove(db, sessionId, seq, lane, leafId) {
    db.prepare("INSERT INTO lane_moves (session_id, seq, lane, leaf_id) VALUES (?, ?, ?, ?)").run(sessionId, seq, lane, leafId);
}
//# sourceMappingURL=lanes.js.map