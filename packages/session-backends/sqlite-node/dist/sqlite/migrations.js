import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
async function loadMigrationSql(relativePath) {
    return readFile(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}
export async function loadMigrations() {
    return [
        {
            id: "001_initial.sql",
            order: 1,
            sql: await loadMigrationSql("./migrations/001_initial.sql"),
        },
    ];
}
function ensureMigrationsTable(db) {
    db.exec(`
CREATE TABLE IF NOT EXISTS migrations (
	id TEXT PRIMARY KEY,
	applied_at TEXT NOT NULL
);
`);
}
export async function applyMigrations(db) {
    ensureMigrationsTable(db);
    const migrations = await loadMigrations();
    const appliedRows = db.prepare("SELECT id FROM migrations ORDER BY applied_at, id").all();
    const applied = new Set(appliedRows.map((row) => row.id));
    for (const migration of migrations) {
        if (applied.has(migration.id))
            continue;
        db.transaction(() => {
            db.exec(migration.sql);
            db.prepare("INSERT INTO migrations (id, applied_at) VALUES (?, ?)").run(migration.id, new Date().toISOString());
        });
        applied.add(migration.id);
    }
}
//# sourceMappingURL=migrations.js.map