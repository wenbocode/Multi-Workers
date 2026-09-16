import { DatabaseSync } from "node:sqlite";
function isNamedParameters(value) {
    if (value === null || typeof value !== "object")
        return false;
    if (Array.isArray(value) || ArrayBuffer.isView(value))
        return false;
    return true;
}
function isAsyncResult(value) {
    return value !== null && (typeof value === "object" || typeof value === "function") && "then" in value;
}
class NodeSqliteStatement {
    statement;
    constructor(statement) {
        this.statement = statement;
    }
    run(...params) {
        const [first, ...rest] = params;
        const result = isNamedParameters(first)
            ? this.statement.run(first, ...rest)
            : this.statement.run(...params);
        return {
            changes: Number(result.changes),
            lastInsertRowid: result.lastInsertRowid === undefined ? undefined : Number(result.lastInsertRowid),
        };
    }
    get(...params) {
        const [first, ...rest] = params;
        return (isNamedParameters(first)
            ? this.statement.get(first, ...rest)
            : this.statement.get(...params));
    }
    all(...params) {
        const [first, ...rest] = params;
        return (isNamedParameters(first)
            ? this.statement.all(first, ...rest)
            : this.statement.all(...params));
    }
}
class NodeSqliteDatabase {
    db;
    constructor(db) {
        this.db = db;
    }
    exec(sql) {
        this.db.exec(sql);
    }
    prepare(sql) {
        return new NodeSqliteStatement(this.db.prepare(sql));
    }
    transaction(fn) {
        this.db.exec("BEGIN IMMEDIATE");
        try {
            const result = fn();
            if (isAsyncResult(result)) {
                throw new TypeError("SQLite transaction callbacks must be synchronous");
            }
            this.db.exec("COMMIT");
            return result;
        }
        catch (error) {
            try {
                this.db.exec("ROLLBACK");
            }
            catch {
                // Ignore rollback errors to rethrow original error.
            }
            throw error;
        }
    }
    close() {
        this.db.close();
    }
}
export function wrapNodeSqliteDatabase(db) {
    return new NodeSqliteDatabase(db);
}
export function createNodeSqliteFactory() {
    return {
        async open(path) {
            return new NodeSqliteDatabase(new DatabaseSync(path));
        },
    };
}
// Re-export the SQLite session backend and types so this package is a complete node-sqlite backend.
export * from "./sqlite/index.js";
//# sourceMappingURL=index.js.map