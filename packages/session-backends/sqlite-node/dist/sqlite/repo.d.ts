import { type ForkOptions, Session, type SessionRepo as SessionRepository } from "@earendil-works/pi-agent-core";
import type { SqliteDatabaseFactory, SqliteSessionCreateOptions, SqliteSessionListOptions, SqliteSessionMetadata, SqliteSessionRepositoryEnv } from "./types.ts";
export interface SqliteWriterLeaseOptions {
    /** Time without a successful heartbeat before another writer may take over. Default: 30 seconds. */
    ttlMs?: number;
    /** Idle heartbeat cadence. Default: 10 seconds. Must be less than ttlMs. */
    heartbeatIntervalMs?: number;
}
export interface SqliteSessionRepositoryOptions {
    env: SqliteSessionRepositoryEnv;
    sqlite: SqliteDatabaseFactory;
    databasePath: string;
    writerLease?: SqliteWriterLeaseOptions;
}
export declare class SqliteSessionRepository implements SessionRepository<SqliteSessionMetadata, SqliteSessionCreateOptions, SqliteSessionListOptions>, AsyncDisposable {
    private databasePath;
    private database;
    private databasePromise;
    private readonly operations;
    private readonly activeStorages;
    private readonly options;
    private readonly leaseOptions;
    constructor(options: SqliteSessionRepositoryOptions);
    private releaseStoragesForSession;
    private sessionFromLease;
    private claimSession;
    create(options: SqliteSessionCreateOptions): Promise<Session<SqliteSessionMetadata>>;
    open(metadata: SqliteSessionMetadata): Promise<Session<SqliteSessionMetadata>>;
    /** Rebuilds this session's private branch-read cache from canonical entry parent links. */
    repairBranchCache(metadata: SqliteSessionMetadata): Promise<void>;
    list(options?: SqliteSessionListOptions): Promise<SqliteSessionMetadata[]>;
    delete(metadata: SqliteSessionMetadata): Promise<void>;
    fork(source: SqliteSessionMetadata, options: ForkOptions & SqliteSessionCreateOptions): Promise<Session<SqliteSessionMetadata>>;
    close(): Promise<void>;
    [Symbol.asyncDispose](): Promise<void>;
    private getDatabasePath;
    private getDatabase;
    private openDatabase;
}
//# sourceMappingURL=repo.d.ts.map