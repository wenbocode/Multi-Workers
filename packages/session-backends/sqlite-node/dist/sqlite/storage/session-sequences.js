import { SessionError } from "@earendil-works/pi-agent-core";
export function createSequence(db, sessionId, nextSeq = 1) {
    db.prepare("INSERT INTO session_sequences (session_id, next_seq) VALUES (?, ?)").run(sessionId, nextSeq);
}
export function getNextSequence(db, sessionId) {
    const sequenceRow = db
        .prepare("SELECT next_seq FROM session_sequences WHERE session_id = ?")
        .get(sessionId);
    if (!sequenceRow) {
        throw new SessionError("storage", `Missing sequence row for session ${sessionId}`);
    }
    return sequenceRow.next_seq;
}
export function setNextSequence(db, sessionId, nextSeq) {
    db.prepare("UPDATE session_sequences SET next_seq = ? WHERE session_id = ?").run(nextSeq, sessionId);
}
export function advanceSequence(db, sessionId, seq) {
    setNextSequence(db, sessionId, seq + 1);
}
export function deleteSequence(db, sessionId) {
    db.prepare("DELETE FROM session_sequences WHERE session_id = ?").run(sessionId);
}
//# sourceMappingURL=session-sequences.js.map