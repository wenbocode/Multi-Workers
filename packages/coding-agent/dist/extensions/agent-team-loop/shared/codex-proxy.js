import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { findMwPy, PYTHON_EXE } from "./mw-runner.js";
import { controlRootFromTaskPath } from "./paths.js";
export const LOCAL_CODEX_PROVIDER = "openai-codex-local";
export function proxyProject(cwd = process.cwd()) {
    return process.env.PI_WORKER_TASK ? controlRootFromTaskPath(process.env.PI_WORKER_TASK) : cwd;
}
export function relayUrl(value) {
    const url = new URL(value);
    if (url.protocol !== "http:" ||
        url.hostname !== "127.0.0.1" ||
        !url.port ||
        url.username ||
        url.password ||
        url.search ||
        url.hash ||
        url.pathname !== "/")
        throw new Error("MW_CODEX_LOCAL_URL must be http://127.0.0.1:<port>");
    return url.origin;
}
export function readProxyConfig(project) {
    const file = path.join(project, ".mw", "codex-local.json");
    let value;
    if (fs.existsSync(file)) {
        try {
            value = JSON.parse(fs.readFileSync(file, "utf8"));
        }
        catch {
            throw new Error("Invalid .mw/codex-local.json; repair the proxy configuration");
        }
        if (value?.version !== 1)
            throw new Error("Unsupported local proxy configuration version");
    }
    else {
        if (!process.env.MW_CODEX_LOCAL_URL)
            return undefined;
        value = { url: process.env.MW_CODEX_LOCAL_URL, token: process.env.MW_CODEX_LOCAL_TOKEN };
    }
    if (typeof value.url !== "string" || typeof value.token !== "string" || value.token.length < 24) {
        throw new Error("Local proxy URL and token (at least 24 characters) are required");
    }
    return { url: relayUrl(value.url), token: value.token };
}
const snapshots = new Map();
export function proxySnapshot(project) {
    return snapshots.get(project);
}
export function setProxySnapshot(project, status) {
    snapshots.set(project, status);
}
export async function checkProxy(config, options = {}) {
    const signal = AbortSignal.any([
        AbortSignal.timeout(options.login ? 8000 : 3000),
        ...(options.signal ? [options.signal] : []),
    ]);
    const response = await (options.fetch ?? fetch)(`${relayUrl(config.url)}/${options.login ? "check" : "status"}`, {
        headers: { Authorization: `Bearer ${config.token}` },
        signal,
        redirect: "error",
    });
    if (!response.ok)
        throw new Error(`Local Codex proxy check HTTP ${response.status}`);
    const status = (await response.json());
    if (status.backend !== "codex-cli" || status.protocol !== 2 || !Array.isArray(status.active)) {
        throw new Error("Incompatible Codex proxy; update and restart the service");
    }
    return { ...status, checkedAt: Date.now() };
}
export async function refreshProxy(project, login = false) {
    let status;
    try {
        const config = readProxyConfig(project);
        status = config ? await checkProxy(config, { login }) : { status: "not configured", checkedAt: Date.now() };
    }
    catch (error) {
        status = {
            status: "offline/error",
            error: error instanceof Error ? error.message : "Proxy check failed",
            checkedAt: Date.now(),
        };
    }
    status.request = snapshots.get(project)?.request;
    snapshots.set(project, status);
    return status;
}
export function formatProxyStatus(status, now = Date.now()) {
    if (!status)
        return [];
    const stale = status.checkedAt !== undefined && now - status.checkedAt > 12_000;
    const lines = [
        `codex proxy: ${stale ? "STALE " : ""}${status.status} | active ${status.active?.length ?? "?"}/${status.concurrency ?? "?"}`,
    ];
    if (status.error)
        lines.push(`  ${status.error}`);
    if (status.login)
        lines.push(`  login=${status.login} | model=${status.model_check ?? "not checked"}`);
    for (const request of status.active ?? [])
        lines.push(`  ${request.caller ?? "unknown"} ${request.model} waiting ${Math.floor(request.age_s)}s / ${status.timeout_s ?? "?"}s`);
    if (status.request) {
        const r = status.request;
        lines.push(`  this window: ${r.phase} ${Math.floor((now - r.startedAt) / 1000)}s | heartbeat ${Math.floor((now - r.heartbeatAt) / 1000)}s ago | remaining ${Math.max(0, Math.ceil((r.deadline - now) / 1000))}s`);
    }
    if (status.last_success)
        lines.push(`  last success ${new Date(status.last_success.at * 1000).toISOString()} (${status.last_success.duration_s.toFixed(1)}s)`);
    if (status.last_error)
        lines.push(`  last error ${new Date(status.last_error.at * 1000).toISOString()}: ${status.last_error.error}`);
    return lines;
}
/** Arguments are a closed set; no shell or user-supplied executable. */
export async function manageProxy(project, action, model, deep = false) {
    if (!["start", "stop", "status", "check"].includes(action))
        throw new Error("Unknown proxy action");
    const mw = findMwPy();
    if (!mw)
        throw new Error("Could not find mw.py; set MW_PY to its path");
    const args = [path.join(path.dirname(mw), "codex_proxy.py"), action, "--project", project];
    if (deep) {
        if (!model || action !== "check")
            throw new Error("Select a Codex model before check --deep");
        args.push("--deep", "--model", model);
    }
    return new Promise((resolve, reject) => {
        const child = spawn(PYTHON_EXE, args, { windowsHide: true, stdio: ["ignore", "pipe", "ignore"] });
        let output = "";
        const timer = setTimeout(() => {
            child.kill();
            reject(new Error("Proxy command timed out"));
        }, deep ? 210_000 : 25_000);
        child.stdout.on("data", (chunk) => {
            output += chunk.toString("utf8");
            if (output.length > 1024 * 1024)
                child.kill();
        });
        child.on("error", () => {
            clearTimeout(timer);
            reject(new Error("Failed to start Python proxy manager"));
        });
        child.on("close", (code) => {
            clearTimeout(timer);
            try {
                const result = JSON.parse(output);
                result.checkedAt = Date.now();
                snapshots.set(project, result);
                if (code !== 0)
                    reject(new Error(result.error ??
                        `Proxy check failed: login=${result.login}, model=${result.model_check ?? "not checked"}`));
                else
                    resolve(result);
            }
            catch (error) {
                reject(error instanceof SyntaxError ? new Error(`Proxy manager failed (exit ${code})`) : error);
            }
        });
    });
}
//# sourceMappingURL=codex-proxy.js.map