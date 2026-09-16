export function acquireSessionLease(db, sessionId, ownerId, now, expiresAtMs) {
    const row = db
        .prepare(`INSERT INTO leases (session_id, owner_id, fence, expires_at_ms)
			VALUES (?, ?, 1, ?)
			ON CONFLICT(session_id) DO UPDATE SET
				owner_id = excluded.owner_id,
				fence = leases.fence + 1,
				expires_at_ms = excluded.expires_at_ms
			WHERE leases.expires_at_ms <= ?
			RETURNING owner_id, fence, expires_at_ms`)
        .get(sessionId, ownerId, expiresAtMs, now);
    return row === undefined ? undefined : { ownerId: row.owner_id, fence: row.fence, expiresAtMs: row.expires_at_ms };
}
export function renewSessionLease(db, sessionId, lease, now, expiresAtMs) {
    const result = db
        .prepare(`UPDATE leases
			SET expires_at_ms = ?
			WHERE session_id = ? AND owner_id = ? AND fence = ? AND expires_at_ms > ?`)
        .run(expiresAtMs, sessionId, lease.ownerId, lease.fence, now);
    if (result.changes === 1)
        lease.expiresAtMs = expiresAtMs;
    return result.changes === 1;
}
export function releaseSessionLease(db, sessionId, lease) {
    db.prepare("DELETE FROM leases WHERE session_id = ? AND owner_id = ? AND fence = ?").run(sessionId, lease.ownerId, lease.fence);
}
export function deleteSessionLease(db, sessionId) {
    db.prepare("DELETE FROM leases WHERE session_id = ?").run(sessionId);
}
//# sourceMappingURL=leases.js.map