import { assertJsonSerializable, SessionError } from "@earendil-works/pi-agent-core";
function parseMetadata(metadata, sessionId) {
    if (metadata === null)
        return undefined;
    let parsed;
    try {
        parsed = JSON.parse(metadata);
    }
    catch (error) {
        throw new SessionError("storage", `Invalid SQLite session ${sessionId}: metadata is not valid JSON`, error instanceof Error ? error : undefined);
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new SessionError("storage", `Invalid SQLite session ${sessionId}: metadata must be an object`);
    }
    return parsed;
}
export function sessionExists(db, sessionId) {
    return !!db.prepare("SELECT 1 AS found FROM sessions WHERE id = ?").get(sessionId);
}
function serializeMetadata(metadata) {
    if (metadata === undefined)
        return null;
    if (typeof metadata !== "object" || metadata === null || Array.isArray(metadata)) {
        throw new SessionError("invalid_payload", "SQLite session metadata must be an object");
    }
    assertJsonSerializable(metadata);
    return JSON.stringify(metadata);
}
export function insertSessionRow(db, session) {
    db.prepare("INSERT INTO sessions (id, created_at, metadata, cwd, parent_session_id) VALUES (?, ?, ?, ?, ?)").run(session.id, session.createdAt, serializeMetadata(session.metadata), session.cwd, session.parentSessionId ?? null);
}
export function readSessionRow(db, sessionId) {
    return db
        .prepare("SELECT id, created_at, metadata, cwd, parent_session_id FROM sessions WHERE id = ?")
        .get(sessionId);
}
export function readSessionRows(db, options = {}) {
    return options.cwd
        ? db
            .prepare("SELECT id, created_at, metadata, cwd, parent_session_id FROM sessions WHERE cwd = ? ORDER BY created_at DESC")
            .all(options.cwd)
        : db
            .prepare("SELECT id, created_at, metadata, cwd, parent_session_id FROM sessions ORDER BY created_at DESC")
            .all();
}
export function deleteSessionRow(db, sessionId) {
    db.prepare("DELETE FROM sessions WHERE id = ?").run(sessionId);
}
export function rowToMetadata(row, path) {
    return {
        id: row.id,
        createdAt: Date.parse(row.created_at),
        cwd: row.cwd,
        path,
        parentSessionId: row.parent_session_id ?? undefined,
        metadata: parseMetadata(row.metadata, row.id),
    };
}
//# sourceMappingURL=sessions.js.map