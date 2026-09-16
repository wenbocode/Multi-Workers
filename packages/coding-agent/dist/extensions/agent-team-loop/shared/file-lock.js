import * as fs from "node:fs";
import * as path from "node:path";
// Acquire an exclusive file lock using O_CREAT|O_EXCL semantics (wx flag).
// Returns a release function that deletes the lock file.
// Throws after exhausting retries with exponential backoff.
export async function acquireLock(lockPath, opts = {}) {
    const retries = opts.retries ?? 10;
    const baseDelayMs = opts.baseDelayMs ?? 50;
    const dir = path.dirname(lockPath);
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const fd = fs.openSync(lockPath, "wx");
            fs.closeSync(fd);
            return () => {
                try {
                    fs.unlinkSync(lockPath);
                }
                catch {
                    // Already removed — not an error
                }
            };
        }
        catch (err) {
            const isExist = err instanceof Error && "code" in err && err.code === "EEXIST";
            if (!isExist)
                throw err;
            if (attempt === retries) {
                throw new Error(`Could not acquire lock at ${lockPath} after ${retries} retries`);
            }
            await sleep(baseDelayMs * 2 ** attempt);
        }
    }
    // Unreachable, but satisfies TypeScript control-flow
    throw new Error(`Could not acquire lock at ${lockPath}`);
}
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
//# sourceMappingURL=file-lock.js.map