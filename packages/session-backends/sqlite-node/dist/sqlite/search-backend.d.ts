import type { SessionSearch } from "@earendil-works/pi-agent-core";
import type { SqliteDatabaseFactory, SqliteSessionMetadata, SqliteSessionRepositoryEnv } from "./types.ts";
export interface SqliteSessionSearchOptions {
    env: Pick<SqliteSessionRepositoryEnv, "absolutePath" | "createDir">;
    sqlite: SqliteDatabaseFactory;
    databasePath: string;
}
export declare function createSqliteSessionSearch(options: SqliteSessionSearchOptions): SessionSearch<SqliteSessionMetadata>;
//# sourceMappingURL=search-backend.d.ts.map