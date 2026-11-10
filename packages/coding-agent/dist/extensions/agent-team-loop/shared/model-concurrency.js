import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { controlRootFromTaskPath } from "./paths.js";
export function concurrencyDirectory() {
    return process.env.MW_CONCURRENCY_DIR || path.join(os.homedir(), ".mw", "concurrency");
}
/** Public dispatch prefixes and pi provider IDs must consume the same slots. */
export function concurrencyRoute(value) {
    const slash = value.indexOf("/");
    const provider = value.slice(0, slash).toLowerCase();
    const model = value.slice(slash + 1);
    if (slash < 1 ||
        !/^[a-z0-9][a-z0-9._-]*$/.test(provider) ||
        !model ||
        /[\s\x00-\x1f\x7f]/.test(model) ||
        (model.includes("*") && model !== "*") ||
        ["codex_cli", "claude_cli"].includes(provider)) {
        throw new Error("Expected provider/model or provider/* (pi providers only)");
    }
    const aliases = {
        "openai-codex": "codex",
        "openai-codex-local": "codex",
        anthropic: "claude",
        "zai-coding-cn": "zai",
    };
    return `${aliases[provider] ?? provider}/${model}`;
}
function alive(pid) {
    try {
        process.kill(pid, 0);
        return true;
    }
    catch (error) {
        // EPERM/unknown cannot prove death: retain the slot rather than oversubscribe.
        return !(error instanceof Error && "code" in error && error.code === "ESRCH");
    }
}
export function readConcurrencyState(directory = concurrencyDirectory()) {
    let value;
    try {
        value = JSON.parse(fs.readFileSync(path.join(directory, "state.json"), "utf8"));
    }
    catch (error) {
        if (error instanceof Error && "code" in error && error.code === "ENOENT")
            return { version: 1, limits: {}, requests: [] };
        throw new Error(`Cannot read concurrency state in ${directory}`, { cause: error });
    }
    if (value?.version !== 1 ||
        !value.limits ||
        typeof value.limits !== "object" ||
        Array.isArray(value.limits) ||
        !Array.isArray(value.requests) ||
        Object.entries(value.limits).some(([route, limit]) => concurrencyRoute(route) !== route || !Number.isSafeInteger(limit) || limit < 1) ||
        value.requests.some((request) => !request ||
            typeof request.id !== "string" ||
            !request.id ||
            !Number.isSafeInteger(request.pid) ||
            request.pid < 1 ||
            typeof request.route !== "string" ||
            concurrencyRoute(request.route) !== request.route ||
            !Number.isFinite(request.createdAt) ||
            !["active", "waiting"].includes(request.phase) ||
            (request.project !== undefined && typeof request.project !== "string") ||
            (request.taskPath !== undefined && typeof request.taskPath !== "string"))) {
        throw new Error(`Invalid concurrency state in ${directory}; refusing unmetered requests`);
    }
    value.requests = value.requests.filter((request) => alive(request.pid));
    return value;
}
/** Short transactions only. An orphaned transaction lock fails closed; never steal by age. */
async function transaction(directory, mutate, signal) {
    fs.mkdirSync(directory, { recursive: true });
    const lock = path.join(directory, "state.lock");
    const deadline = Date.now() + 3000;
    let fd;
    for (;;) {
        signal?.throwIfAborted();
        try {
            fd = fs.openSync(lock, "wx", 0o600);
            break;
        }
        catch (error) {
            if (!(error instanceof Error && "code" in error && error.code === "EEXIST"))
                throw error;
            if (Date.now() >= deadline)
                throw new Error(`Concurrency lock busy: ${lock}. Check for an interrupted configuration transaction.`);
            await delay(25, undefined, { signal });
        }
    }
    const temporary = path.join(directory, `${randomUUID()}.tmp`);
    try {
        fs.writeFileSync(fd, JSON.stringify({ pid: process.pid }));
        const state = readConcurrencyState(directory);
        const result = mutate(state);
        fs.writeFileSync(temporary, JSON.stringify(state), { flag: "wx", mode: 0o600 });
        fs.renameSync(temporary, path.join(directory, "state.json"));
        return result;
    }
    finally {
        fs.closeSync(fd);
        fs.rmSync(temporary, { force: true });
        fs.unlinkSync(lock);
    }
}
export async function setConcurrencyLimit(value, limit, directory = concurrencyDirectory()) {
    const route = concurrencyRoute(value);
    if (limit !== undefined && (!Number.isSafeInteger(limit) || limit < 1))
        throw new Error("Concurrency limit must be a positive integer; use clear to remove a limit");
    await transaction(directory, (state) => {
        if (limit === undefined)
            delete state.limits[route];
        else
            state.limits[route] = limit;
    });
}
function matches(rule, route) {
    return rule === route || rule === `${route.slice(0, route.indexOf("/"))}/*`;
}
/** The lease covers the provider stream, not subsequent local tool execution. */
export async function acquireModelSlot(value, options = {}) {
    const route = concurrencyRoute(value);
    const directory = options.directory ?? concurrencyDirectory();
    options.signal?.throwIfAborted();
    if (!fs.existsSync(path.join(directory, "state.json")))
        return async () => { };
    const id = randomUUID();
    const taskPath = options.taskPath ?? (process.env.PI_WORKER_TASK || undefined);
    const project = options.project ?? (taskPath ? controlRootFromTaskPath(taskPath) : process.cwd());
    const deadline = Date.now() + (options.waitMs ?? 120_000);
    const signal = AbortSignal.any([
        AbortSignal.timeout(options.waitMs ?? 120_000),
        ...(options.signal ? [options.signal] : []),
    ]);
    let registered = false;
    let notified = false;
    const release = async () => {
        if (!registered)
            return;
        await transaction(directory, (state) => {
            state.requests = state.requests.filter((request) => request.id !== id);
        });
        registered = false;
    };
    try {
        for (;;) {
            signal.throwIfAborted();
            const admitted = await transaction(directory, (state) => {
                let current = state.requests.find((request) => request.id === id);
                if (!current) {
                    current = { id, pid: process.pid, route, phase: "waiting", createdAt: Date.now(), project, taskPath };
                    state.requests.push(current);
                }
                const earlier = state.requests.slice(0, state.requests.indexOf(current));
                const available = Object.entries(state.limits)
                    .filter(([rule]) => matches(rule, route))
                    .every(([rule, limit]) => state.requests.filter((request) => request.phase === "active" && matches(rule, request.route))
                    .length < limit &&
                    !earlier.some((request) => request.phase === "waiting" && matches(rule, request.route)));
                if (available)
                    current.phase = "active";
                return available;
            }, signal);
            registered = true;
            if (admitted) {
                signal.throwIfAborted();
                return release;
            }
            if (!notified) {
                notified = true;
                options.onWait?.();
            }
            await delay(Math.min(200, Math.max(1, deadline - Date.now())), undefined, { signal });
        }
    }
    catch (error) {
        await release();
        if (!options.signal?.aborted && signal.aborted)
            throw new Error(`Concurrency queue timed out for ${route}; inspect /mw concurrency show`);
        throw error;
    }
}
export function formatConcurrencyState(state) {
    const lines = ["LLM concurrency: this OS user, all projects"];
    for (const [rule, limit] of Object.entries(state.limits).sort(([a], [b]) => a.localeCompare(b))) {
        const requests = state.requests.filter((request) => matches(rule, request.route));
        lines.push(`${rule}: limit=${limit} active=${requests.filter((r) => r.phase === "active").length} waiting=${requests.filter((r) => r.phase === "waiting").length}`);
    }
    if (!Object.keys(state.limits).length)
        lines.push("No limits configured.");
    return lines.join("\n");
}
//# sourceMappingURL=model-concurrency.js.map