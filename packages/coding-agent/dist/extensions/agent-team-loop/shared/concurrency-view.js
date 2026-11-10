import * as path from "node:path";
import { readConcurrencyState } from "./model-concurrency.js";
/** Read-only: malformed state must be visible, never interpreted as zero usage. */
export function readConcurrencySnapshot(directory) {
    try {
        const state = readConcurrencyState(directory);
        const routes = new Set([...Object.keys(state.limits), ...state.requests.map((r) => r.route)]);
        const rows = [...routes].sort().map((route) => {
            const aggregate = `${route.slice(0, route.indexOf("/"))}/*`;
            const caps = [state.limits[route], state.limits[aggregate]].filter((n) => n !== undefined);
            const requests = state.requests.filter((r) => route.endsWith("/*") ? r.route.startsWith(route.slice(0, -1)) : r.route === route);
            return {
                route,
                limit: caps.length ? Math.min(...caps) : null,
                active: requests.filter((r) => r.phase === "active").length,
                waiting: requests.filter((r) => r.phase === "waiting").length,
            };
        });
        return { rows, requests: state.requests };
    }
    catch (error) {
        return { rows: [], requests: [], error: error instanceof Error ? error.message : String(error) };
    }
}
function normalizedPath(value) {
    const resolved = path.resolve(value);
    return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}
export function taskQueueStatus(snapshot, taskPath, nowMs) {
    if (snapshot.error)
        return "LLM queue unavailable";
    return snapshot.requests
        .filter((r) => r.phase === "waiting" && r.taskPath && normalizedPath(r.taskPath) === normalizedPath(taskPath))
        .map((r) => `LLM queued: ${r.route} ${Math.max(0, Math.floor((nowMs - r.createdAt) / 1000))}s (pid=${r.pid})`)
        .join("; ");
}
export function renderConcurrencyLines(snapshot, nowMs) {
    if (snapshot.error)
        return [`LLM concurrency: unavailable — ${snapshot.error}`];
    const lines = ["LLM concurrency: all projects (same OS user; provider/* rows are totals)"];
    if (!snapshot.rows.length)
        lines.push("  No limits configured; no tracked requests.");
    for (const row of snapshot.rows) {
        const counts = `limit=${row.limit ?? "unlimited"} active=${row.active} waiting=${row.waiting}`;
        if (row.route.length + counts.length > 100)
            lines.push(`  ${row.route}`, `    ${counts}`);
        else
            lines.push(`  ${row.route}: ${counts}`);
    }
    for (const request of snapshot.requests.filter((r) => r.phase === "waiting")) {
        const age = Math.max(0, Math.floor((nowMs - request.createdAt) / 1000));
        lines.push(`  queued ${age}s pid=${request.pid} ${request.route}`);
        lines.push(`    ${request.taskPath ?? request.project ?? "caller unknown"}`);
    }
    return lines;
}
//# sourceMappingURL=concurrency-view.js.map