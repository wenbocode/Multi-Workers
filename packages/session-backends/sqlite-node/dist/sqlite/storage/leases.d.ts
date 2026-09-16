import type { SqliteDatabase } from "../types.ts";
export interface SessionLease {
    ownerId: string;
    fence: number;
    expiresAtMs: number;
}
export declare function acquireSessionLease(db: SqliteDatabase, sessionId: string, ownerId: string, now: number, expiresAtMs: number): {
    ownerId: string;
    fence: number;
    expiresAtMs: number;
} | undefined;
export declare function renewSessionLease(db: SqliteDatabase, sessionId: string, lease: SessionLease, now: number, expiresAtMs: number): boolean;
export declare function releaseSessionLease(db: SqliteDatabase, sessionId: string, lease: SessionLease): void;
export declare function deleteSessionLease(db: SqliteDatabase, sessionId: string): void;
//# sourceMappingURL=leases.d.ts.map